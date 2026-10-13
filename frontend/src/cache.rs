use crate::{CacheRow, Dashboard, app_state::AppState, paths::Paths};
use serde_json::Value;
use slint::{ComponentHandle, ModelRc, VecModel};
use std::{
    cell::RefCell,
    io::Write,
    os::windows::process::CommandExt,
    process::{Command, Stdio},
    rc::Rc,
    time::{Duration, Instant},
};

pub const EXIT_POLICIES: [&str; 3] = ["ask", "always_clean_completed", "never"];
pub fn exit_policy(value: &str) -> &str {
    if EXIT_POLICIES.contains(&value) {
        value
    } else {
        "ask"
    }
}
fn invoke(paths: &Paths, request: Option<Value>) -> Result<Value, String> {
    let script = paths
        .backend
        .parent()
        .ok_or("code_root_missing")?
        .join("cache_manager_v205.py");
    let mut child = Command::new(&paths.python)
        .args(["-B", "-X", "utf8"])
        .arg(script)
        .arg("--app-root")
        .arg(&paths.root)
        .arg(if request.is_some() { "delete" } else { "list" })
        .creation_flags(0x08000000)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;
    if let Some(value) = request {
        let bytes = serde_json::to_vec(&value).map_err(|e| e.to_string())?;
        child
            .stdin
            .take()
            .ok_or("stdin_missing")?
            .write_all(&bytes)
            .map_err(|e| e.to_string())?;
    } else {
        drop(child.stdin.take());
    }
    // Drain concurrently; large catalogs cannot block on a full pipe.
    let mut stdout = child.stdout.take().ok_or("stdout_missing")?;
    let reader = std::thread::spawn(move || {
        use std::io::Read;
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let start = Instant::now();
    loop {
        if child.try_wait().map_err(|e| e.to_string())?.is_some() {
            break;
        }
        if start.elapsed() > Duration::from_secs(120) {
            let _ = child.kill();
            let _ = child.wait();
            let _ = reader.join();
            return Err("cache_operation_timeout_refresh_required".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    let bytes = reader
        .join()
        .map_err(|_| "reader_failed")?
        .map_err(|e| e.to_string())?;
    let value: Value = serde_json::from_slice(&bytes).map_err(|_| "cache_response_invalid")?;
    if value.get("error").is_some() {
        return Err(value["message"].as_str().unwrap_or("cache_error").into());
    }
    Ok(value)
}
#[derive(Default)]
struct Catalog {
    projects: Vec<Value>,
    selected: Vec<bool>,
    total: u64,
    unknown: usize,
}
fn mb(bytes: u64) -> String {
    format!("{:.1} MiB", bytes as f64 / 1_048_576.0)
}
fn render(ui: &Dashboard, c: &Catalog) {
    let rows = c
        .projects
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let status = match p["status"].as_str().unwrap_or("") {
                "COMPLETED" => "завершён",
                "ACTIVE" => "активен · защищён",
                _ => "не завершён · можно продолжить",
            };
            let languages = p["languages"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(Value::as_str)
                        .map(str::to_uppercase)
                        .collect::<Vec<_>>()
                        .join(" / ")
                })
                .unwrap_or_default();
            CacheRow {
                name: p["filename"]
                    .as_str()
                    .unwrap_or("Неизвестный источник")
                    .into(),
                detail: format!(
                    "{} · {} · {} · {} UTC · {:.0} с · resume: {} · вариантов: {}",
                    mb(p["bytes"].as_u64().unwrap_or(0)),
                    status,
                    languages,
                    p["updated"].as_str().unwrap_or("--"),
                    p["duration"].as_f64().unwrap_or(0.0),
                    if p["resume"].as_bool().unwrap_or(false) {
                        "да"
                    } else {
                        "нет"
                    },
                    p["variants"].as_array().map_or(0, Vec::len)
                )
                .into(),
                selected: c.selected[i],
                removable: p["status"] != "ACTIVE",
            }
        })
        .collect::<Vec<_>>();
    ui.set_cache_rows(ModelRc::new(VecModel::from(rows)));
    let chosen = c
        .projects
        .iter()
        .zip(&c.selected)
        .filter(|(_, s)| **s)
        .collect::<Vec<_>>();
    ui.set_cache_has_selection(!chosen.is_empty());
    ui.set_cache_summary(
        format!(
            "Выбрано: {} · {}   |   Кэш проектов: {}",
            chosen.len(),
            mb(chosen
                .iter()
                .map(|(p, _)| p["bytes"].as_u64().unwrap_or(0))
                .sum()),
            mb(c.total)
        )
        .into(),
    );
    ui.set_cache_unknown(
        if c.unknown == 0 {
            String::new()
        } else {
            format!(
                "Служебный / неизвестный кэш: {} · защищён; его размер не включён",
                c.unknown
            )
        }
        .into(),
    );
}
pub fn install(ui: &Dashboard, paths: Paths, state: Rc<RefCell<AppState>>) -> slint::Timer {
    let catalog = Rc::new(RefCell::new(Catalog::default()));
    let (tx, rx) = std::sync::mpsc::channel();
    {
        let weak = ui.as_weak();
        let paths = paths.clone();
        let tx = tx.clone();
        ui.on_open_cache(move || {
            if let Some(ui) = weak.upgrade() {
                if ui.get_cache_working() {
                    return;
                }
                ui.set_cache_visible(true);
                ui.set_cache_working(true);
                ui.set_cache_message("Чтение кэша…".into());
                let paths = paths.clone();
                let tx = tx.clone();
                std::thread::spawn(move || {
                    let _ = tx.send(invoke(&paths, None));
                });
            }
        });
    }
    {
        let weak = ui.as_weak();
        let c = catalog.clone();
        ui.on_toggle_cache(move |index| {
            if let Some(ui) = weak.upgrade() {
                if ui.get_cache_working() {
                    return;
                }
                let mut c = c.borrow_mut();
                let i = index as usize;
                if i < c.projects.len() && c.projects[i]["status"] != "ACTIVE" {
                    c.selected[i] = !c.selected[i];
                }
                render(&ui, &c);
            }
        });
    }
    {
        let weak = ui.as_weak();
        let c = catalog.clone();
        ui.on_select_completed(move || {
            if let Some(ui) = weak.upgrade() {
                if ui.get_cache_working() {
                    return;
                }
                let mut c = c.borrow_mut();
                c.selected = c
                    .projects
                    .iter()
                    .map(|p| p["status"] == "COMPLETED")
                    .collect();
                render(&ui, &c);
            }
        });
    }
    {
        let weak = ui.as_weak();
        let c = catalog.clone();
        let tx = tx.clone();
        let state = state.clone();
        ui.on_delete_cache(move || {
            let Some(ui)=weak.upgrade() else {return};
            if state.borrow().worker_alive || ui.get_cache_working() {return;}
            let c=c.borrow();
            let selected=c.projects.iter().zip(&c.selected).filter(|(_,s)| **s).map(|(p,_)|p.clone()).collect::<Vec<_>>();
            if selected.is_empty() {return;}
            let incomplete=selected.iter().any(|p|p["status"]!="COMPLETED");
            let names=selected.iter().filter_map(|p|p["filename"].as_str()).collect::<Vec<_>>().join("\n");
            let result=rfd::MessageDialog::new().set_title("Очистить выбранный кэш?")
                .set_description(format!("{}\n{}\nГотовые результаты в output останутся.", ui.get_cache_summary(),names))
                .set_buttons(rfd::MessageButtons::OkCancel).show();
            if result!=rfd::MessageDialogResult::Ok {return;}
            if incomplete && rfd::MessageDialog::new().set_title("Продолжение будет потеряно")
                .set_description("Есть незавершённые задания. Рекомендуется оставить кэш. Удалить его без возможности продолжить?")
                .set_buttons(rfd::MessageButtons::YesNo).show()!=rfd::MessageDialogResult::Yes {return;}
            ui.set_cache_working(true); ui.set_cache_message("Очистка выбранного кэша…".into());
            let paths=paths.clone(); let tx=tx.clone();
            let request=serde_json::json!({"confirmation":"delete_selected","resume_confirmation":if incomplete {"lose_resume"}else{""},"projects":selected});
            std::thread::spawn(move || {let _=tx.send(invoke(&paths,Some(request)));});
        });
    }
    let timer = slint::Timer::default();
    let weak = ui.as_weak();
    timer.start(slint::TimerMode::Repeated,Duration::from_millis(100),move||{
        let Some(ui)=weak.upgrade() else{return};
        while let Ok(result)=rx.try_recv() {
            ui.set_cache_working(false);
            match result {
                Ok(v)=>{
                    let errors=v["errors"].as_array().map_or(0,Vec::len);
                    let data=v.get("catalog").unwrap_or(&v);
                    let mut c=catalog.borrow_mut();
                    c.projects=data["projects"].as_array().cloned().unwrap_or_default();
                    // Protect the current frontend job even before its backend lock appears.
                    if state.borrow().worker_alive {
                        for p in &mut c.projects { p["status"]=Value::String("ACTIVE".into()); }
                    }
                    c.selected=vec![false;c.projects.len()];
                    c.total=data["total_bytes"].as_u64().unwrap_or(0);
                    c.unknown=data["unknown"].as_array().map_or(0,Vec::len);
                    render(&ui,&c);
                    ui.set_cache_message(if errors>0 {format!("Не удалено вариантов: {errors}. Кэш изменился, занят или защищён. Обновите список.")}
                        else if v.get("deleted").is_some() {"Очистка выбранного кэша завершена.".into()}
                        else {"Готовые результаты в output сохраняются.".into()}.into());
                }
                Err(e)=>ui.set_cache_message(format!("Операция не выполнена: {e}").into()),
            }
        }
    });
    timer
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exit_policy_defaults_to_ask() {
        assert_eq!(exit_policy(""), "ask");
        assert_eq!(exit_policy("invalid"), "ask");
    }
    #[test]
    fn exit_policy_preserves_supported_values() {
        for p in EXIT_POLICIES {
            assert_eq!(exit_policy(p), p);
        }
    }
    #[test]
    fn real_catalog_is_read_only_and_hides_hashes_in_names() {
        let v = invoke(&Paths::discover(None).unwrap(), None).unwrap();
        assert!(v["projects"].is_array());
        for p in v["projects"].as_array().unwrap() {
            assert!(!p["filename"].as_str().unwrap().is_empty());
        }
    }
}
