//! Windows child ownership: suspended launch -> assign Job Object -> resume.
use std::{
    ffi::{OsStr, OsString},
    fs::File,
    io,
    os::windows::{
        ffi::OsStrExt,
        io::{FromRawHandle, RawHandle},
    },
    path::Path,
};
use windows_sys::Win32::{
    Foundation::*,
    Security::SECURITY_ATTRIBUTES,
    Storage::FileSystem::*,
    System::{JobObjects::*, Pipes::CreatePipe, Threading::*},
};

pub struct Handle(pub HANDLE);
unsafe impl Send for Handle {}
impl Drop for Handle {
    fn drop(&mut self) {
        if !self.0.is_null() && self.0 != INVALID_HANDLE_VALUE {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
}
pub struct Child {
    pub pid: u32,
    process: Handle,
    job: Handle,
}
fn wide(s: &OsStr) -> Vec<u16> {
    s.encode_wide().chain(Some(0)).collect()
}
pub fn quote(s: &OsStr) -> OsString {
    // Windows CRT command-line quoting, including trailing slashes before quote.
    let mut out = vec![34u16];
    let mut slash = 0;
    for c in s.encode_wide() {
        if c == 92 {
            slash += 1;
            continue;
        }
        if c == 34 {
            out.extend(std::iter::repeat_n(92, slash * 2 + 1));
            out.push(c);
        } else {
            out.extend(std::iter::repeat_n(92, slash));
            out.push(c);
        }
        slash = 0;
    }
    out.extend(std::iter::repeat_n(92, slash * 2));
    out.push(34);
    OsString::from_wide(&out)
}
use std::os::windows::ffi::OsStringExt;
fn pipe() -> io::Result<(Handle, Handle)> {
    unsafe {
        let (mut read, mut write) = (std::ptr::null_mut(), std::ptr::null_mut());
        let sa = SECURITY_ATTRIBUTES {
            nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: std::ptr::null_mut(),
            bInheritHandle: 1,
        };
        if CreatePipe(&mut read, &mut write, &sa, 0) == 0 {
            return Err(io::Error::last_os_error());
        }
        let read = Handle(read);
        let write = Handle(write);
        if SetHandleInformation(read.0, HANDLE_FLAG_INHERIT, 0) == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok((read, write))
    }
}
impl Child {
    pub fn spawn(exe: &Path, args: &[OsString], cwd: &Path) -> io::Result<(Self, File, File)> {
        unsafe {
            let job = Handle(CreateJobObjectW(std::ptr::null(), std::ptr::null()));
            if job.0.is_null() {
                return Err(io::Error::last_os_error());
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job.0,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
            {
                return Err(io::Error::last_os_error());
            }
            let (out_read, out_write) = pipe()?;
            let (err_read, err_write) = pipe()?;
            let sa = SECURITY_ATTRIBUTES {
                nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
                lpSecurityDescriptor: std::ptr::null_mut(),
                bInheritHandle: 1,
            };
            let input = Handle(CreateFileW(
                wide(OsStr::new("NUL")).as_ptr(),
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                &sa,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                std::ptr::null_mut(),
            ));
            if input.0 == INVALID_HANDLE_VALUE {
                return Err(io::Error::last_os_error());
            }
            let mut start: STARTUPINFOW = std::mem::zeroed();
            start.cb = std::mem::size_of_val(&start) as u32;
            start.dwFlags = STARTF_USESTDHANDLES;
            start.hStdOutput = out_write.0;
            start.hStdError = err_write.0;
            start.hStdInput = input.0;
            let mut command = quote(exe.as_os_str());
            for a in args {
                command.push(" ");
                command.push(quote(a));
            }
            let mut command = wide(&command);
            let mut info: PROCESS_INFORMATION = std::mem::zeroed();
            if CreateProcessW(
                wide(exe.as_os_str()).as_ptr(),
                command.as_mut_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
                CREATE_SUSPENDED | CREATE_NO_WINDOW,
                std::ptr::null(),
                wide(cwd.as_os_str()).as_ptr(),
                &start,
                &mut info,
            ) == 0
            {
                return Err(io::Error::last_os_error());
            }
            let process = Handle(info.hProcess);
            let thread = Handle(info.hThread);
            if AssignProcessToJobObject(job.0, process.0) == 0 {
                TerminateProcess(process.0, 1);
                return Err(io::Error::last_os_error());
            }
            if ResumeThread(thread.0) == u32::MAX {
                TerminateJobObject(job.0, 1);
                return Err(io::Error::last_os_error());
            }
            let stdout = File::from_raw_handle(out_read.0 as RawHandle);
            std::mem::forget(out_read);
            let stderr = File::from_raw_handle(err_read.0 as RawHandle);
            std::mem::forget(err_read);
            Ok((
                Self {
                    pid: info.dwProcessId,
                    process,
                    job,
                },
                stdout,
                stderr,
            ))
        }
    }
    pub fn status(&self) -> io::Result<Option<u32>> {
        unsafe {
            let mut code = 0;
            if GetExitCodeProcess(self.process.0, &mut code) == 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(if code == 259 { None } else { Some(code) })
        }
    }
    pub fn terminate(&self) -> io::Result<()> {
        unsafe {
            if TerminateJobObject(self.job.0, 130) == 0 {
                return Err(io::Error::last_os_error());
            }
            WaitForSingleObject(self.process.0, 5000);
            Ok(())
        }
    }
    pub fn process_ids(&self) -> io::Result<Vec<u32>> {
        // venv python.exe may be a launcher: locks belong to its Python child.
        let mut storage = vec![0u64; 1024];
        unsafe {
            if QueryInformationJobObject(
                self.job.0,
                JobObjectBasicProcessIdList,
                storage.as_mut_ptr() as _,
                (storage.len() * 8) as u32,
                std::ptr::null_mut(),
            ) == 0
            {
                return Err(io::Error::last_os_error());
            }
            let info = &*(storage.as_ptr() as *const JOBOBJECT_BASIC_PROCESS_ID_LIST);
            Ok(std::slice::from_raw_parts(
                info.ProcessIdList.as_ptr(),
                info.NumberOfProcessIdsInList as usize,
            )
            .iter()
            .map(|&p| p as u32)
            .collect())
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    #[test]
    fn quotes_windows_paths() {
        assert_eq!(
            quote(OsStr::new("C:\\path with space\\")).to_string_lossy(),
            "\"C:\\path with space\\\\\""
        );
    }
    #[test]
    fn real_pipes_and_exit() {
        let p = crate::paths::Paths::discover(None).unwrap();
        let (child, mut out, mut err) = Child::spawn(
            &p.python,
            &[
                "-c".into(),
                "import sys; print('stdout'); print('stderr',file=sys.stderr)".into(),
            ],
            &p.root,
        )
        .unwrap();
        let mut a = String::new();
        let mut b = String::new();
        out.read_to_string(&mut a).unwrap();
        err.read_to_string(&mut b).unwrap();
        assert!(a.contains("stdout"));
        assert!(b.contains("stderr"));
        for _ in 0..100 {
            if child.status().unwrap().is_some() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert_eq!(child.status().unwrap(), Some(0));
    }
    #[test]
    fn kill_owns_child_tree() {
        let p = crate::paths::Paths::discover(None).unwrap();
        let (child, out, _) = Child::spawn(
            &p.python,
            &["-c".into(), "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)".into()],
            &p.root,
        )
        .unwrap();
        use std::io::{BufRead, BufReader};
        let mut pid = String::new();
        BufReader::new(out).read_line(&mut pid).unwrap();
        let descendant = Handle(unsafe {
            OpenProcess(
                PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                pid.trim().parse().unwrap(),
            )
        });
        assert!(!descendant.0.is_null());
        assert!(
            child
                .process_ids()
                .unwrap()
                .contains(&pid.trim().parse().unwrap())
        );
        assert_eq!(child.status().unwrap(), None);
        child.terminate().unwrap();
        assert_eq!(child.status().unwrap(), Some(130));
        assert_eq!(
            unsafe { WaitForSingleObject(descendant.0, 5000) },
            WAIT_OBJECT_0
        );
    }
}
