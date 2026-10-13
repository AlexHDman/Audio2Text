"""Project cache management. No inference, migrations or automatic cleanup."""
from __future__ import annotations
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOTS = ("temp/v157", "cache/jobs")
POLICIES = ("ask", "always_clean_completed", "never")
JOB_NAME = re.compile(r"[0-9a-f]{20}-[0-9a-f]{20}(?:-(?:fresh|recovery)-[0-9a-f]{8})?\Z")
OWNED_FILES = {"resume.json", "prepared.wav", "run.lock"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checked(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("reparse_point")
    return info


@contextlib.contextmanager
def pin_directory(path):
    """Deny directory replacement during deletion, including junction swaps."""
    info = checked(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("not_directory")
    if os.name != "nt":
        raise ValueError("deletion_requires_windows_directory_pinning")
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(path), 0x80000000, 3, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "cannot_pin_directory")
    try:
        again = checked(path)
        if (info.st_dev, info.st_ino) != (again.st_dev, again.st_ino):
            raise ValueError("directory_changed")
        yield
    finally:
        close(handle)


def safe_job(root, relative):
    root = Path(root).absolute()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 3:
        raise ValueError("invalid_job_path")
    if rel.parent.as_posix() not in ROOTS or not JOB_NAME.fullmatch(rel.name):
        raise ValueError("unapproved_job_root")
    current = root
    for ancestor in reversed((root, *root.parents)):
        checked(ancestor)
    for part in rel.parts:
        current /= part
        checked(current)
    resolved = current.resolve(strict=True)
    if resolved != current or not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("canonical_path_mismatch")
    return current


def inventory(folder):
    records = []
    for child in sorted(folder.iterdir()):
        info = checked(child)
        if child.name not in OWNED_FILES or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("unrecognized_job_content")
        if child.name != "run.lock":
            records.append([child.name, info.st_size, info.st_mtime_ns, info.st_ino])
    return records


def inspect_job(root, relative):
    import audio_pipeline_cuda_v156 as engine
    folder = safe_job(root, relative)
    files = inventory(folder)
    resume = folder / "resume.json"
    if resume.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("resume_too_large")
    data = json.loads(resume.read_text(encoding="utf-8"))
    engine.validate_cache(data, data["source"], data["processing_fingerprint"])
    source_hash = data["source"]["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("invalid_source_hash")
    expected = source_hash[:20] + "-" + data["processing_fingerprint"][:20]
    if not (folder.name == expected or folder.name.startswith(expected + "-")):
        raise ValueError("ownership_mismatch")
    source = data["source"]["path"]
    if not isinstance(source, str) or not source:
        raise ValueError("missing_source")
    export = data.get("export", {})
    completed = (export.get("status") == "complete" and export.get("at") is not None
                 and export["at"] == data.get("updated_at") and data["diarization_done"]
                 and bool(data["units"]) and all(u["asr_done"] for u in data["units"]))
    state = "ACTIVE" if (folder / "run.lock").exists() else "COMPLETED" if completed else "INCOMPLETE"
    languages = data["processing"].get("config", {}).get("ALLOWED_SOURCE_LANGUAGES")
    if not languages:
        languages = sorted({s["language"].upper() for s in data["segments"]})
    return {
        "id": relative, "filename": Path(source).name, "source": source,
        "source_hash": source_hash, "status": state,
        "updated": str(data.get("updated_at", data.get("created_at", "unknown"))),
        "duration": data["duration"], "languages": languages,
        "bytes": sum(item[1] for item in files),
        "resume": ((folder / "prepared.wav").is_file() and bool(data.get("prepared_sha256"))
                   and engine.file_hash(folder / "prepared.wav") == data["prepared_sha256"]),
        "token": digest([data["state_sha256"], files]),
    }


def discover(root):
    root = Path(root).absolute()
    variants, unknown = [], []
    for namespace in ROOTS:
        base = root / namespace
        if not base.exists():
            continue
        try:
            for ancestor in (root, base.parent, base):
                checked(ancestor)
            children = sorted(base.iterdir())
        except (OSError, ValueError) as error:
            unknown.append({"label": "Недоступный корень кэша", "reason": str(error)})
            continue
        for folder in children:
            relative = folder.relative_to(root).as_posix()
            try:
                variants.append(inspect_job(root, relative))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                unknown.append({"label": "Служебный / неизвестный кэш — защищён", "reason": type(error).__name__})
    grouped = {}
    for job in variants:
        key = digest([job["source"].casefold(), job["source_hash"]])
        grouped.setdefault(key, []).append(job)
    projects = []
    for key, jobs in grouped.items():
        newest = max(jobs, key=lambda j: j["updated"])
        state = ("ACTIVE" if any(j["status"] == "ACTIVE" for j in jobs) else
                 "COMPLETED" if all(j["status"] == "COMPLETED" for j in jobs) else "INCOMPLETE")
        projects.append({**newest, "id": key, "status": state,
                         "bytes": sum(j["bytes"] for j in jobs), "variants": jobs,
                         "resume": any(j["resume"] for j in jobs)})
    return {"projects": sorted(projects, key=lambda j: j["updated"], reverse=True),
            "unknown": unknown, "total_bytes": sum(j["bytes"] for j in variants),
            "total_complete": not unknown}


def delete_variant(root, selected, allow_incomplete=False):
    """Revalidate selection; use the engine's exclusive create-new run.lock."""
    folder = safe_job(root, selected["id"])
    with contextlib.ExitStack() as stack:
        for ancestor in reversed((folder, *folder.parents)):
            stack.enter_context(pin_directory(ancestor))
        before = inspect_job(root, selected["id"])
        if before["token"] != selected["token"]:
            raise ValueError("cache_changed_refresh_required")
        if before["status"] == "ACTIVE":
            raise ValueError("active_job_protected")
        if before["status"] != "COMPLETED" and not allow_incomplete:
            raise ValueError("explicit_resume_loss_confirmation_required")
        lock = folder / "run.lock"
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "owner": "cache_manager_v205"}))
        try:
            if inspect_job(root, selected["id"])["token"] != selected["token"]:
                raise ValueError("cache_changed_refresh_required")
            for name in ("prepared.wav", "resume.json"):
                file = folder / name
                if file.exists():
                    checked(file)
                    file.unlink()
        finally:
            lock.unlink()
    try:
        folder.rmdir()
    except OSError:
        pass  # Nonrecursive: any newly started job is preserved.


def delete_selected(root, request):
    if request.get("confirmation") != "delete_selected":
        raise ValueError("explicit_confirmation_required")
    selected = request.get("projects", [])
    if not isinstance(selected, list) or not selected:
        raise ValueError("empty_selection")
    current = {j["id"]: j for j in discover(root)["projects"]}
    allow = request.get("resume_confirmation") == "lose_resume"
    variants = []
    for project in selected:
        live = current.get(project.get("id"))
        if not live or live["status"] == "ACTIVE":
            raise ValueError("unknown_or_active_project")
        if live["status"] != "COMPLETED" and not allow:
            raise ValueError("explicit_resume_loss_confirmation_required")
        expected = {(v["id"], v["token"]) for v in live["variants"]}
        actual = {(v["id"], v["token"]) for v in project.get("variants", [])}
        if not actual or actual != expected:
            raise ValueError("selection_changed_refresh_required")
        variants.extend(project["variants"])
    deleted, errors = [], []
    for variant in variants:
        try:
            delete_variant(root, variant, allow)
            deleted.append(variant["id"])
        except (OSError, ValueError, KeyError) as error:
            errors.append({"id": variant["id"], "reason": str(error)})
    return {"deleted": deleted, "errors": errors, "catalog": discover(root)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("operation", choices=["list", "delete"])
    args = parser.parse_args()
    try:
        result = (discover(args.app_root) if args.operation == "list" else
                  delete_selected(args.app_root, json.load(sys.stdin)))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
