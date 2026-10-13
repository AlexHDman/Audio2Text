#!/usr/bin/env python3
"""Audio2Text v1.5.7 — Backend Freeze. One subprocess, one job."""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from pathlib import Path

from backend_contract_v1 import AppPaths, EventStream, Telemetry, VERSION, jsonl_stdout
from backend_runtime_v157 import load_config, load_engine, run_job


class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError("invalid_arguments")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = "--ipc" in argv or any(x.startswith("--ipc=") for x in argv)
    with jsonl_stdout(machine) as stream:
        events = EventStream(stream)
        telemetry = Telemetry(events)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            stream=sys.stderr,
        )
        try:
            parser = Parser(
                description=f"Audio2Text {VERSION} Backend Freeze", add_help=False
            )
            parser.add_argument("-h", "--help", action="store_true")
            parser.add_argument("source", nargs="?", type=Path)
            parser.add_argument("--ipc", choices=["jsonl"])
            parser.add_argument("--app-root", type=Path)
            parser.add_argument("--config", type=Path)
            parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
            parser.add_argument("--force-language")
            parser.add_argument("--source-languages")
            parser.add_argument("--target-language", choices=["ru", "en"])
            parser.add_argument("--min-speakers", type=int)
            parser.add_argument("--max-speakers", type=int)
            parser.add_argument("--limit-seconds", type=float)
            parser.add_argument("--fresh", action="store_true")
            parser.add_argument("--retry-translation", action="store_true")
            parser.add_argument(
                "--require-resume",
                action="store_true",
                help="Abort before any inference or audio preparation; developer validation guard",
            )
            parser.add_argument("--validate-config", action="store_true")
            args = parser.parse_args(argv)
            if args.help:
                parser.print_help(file=sys.stderr if machine else sys.stdout)
                events.emit("app_ready", designation="Backend Freeze", journal_schema=1)
                events.emit(
                    "job_completed", status="PASS", operation="help", inference_calls={}
                )
                return 0
            paths = AppPaths.create(args.app_root)
            api = load_engine(paths)
            config = load_config(api, paths, args.config)
            for arg, key in (
                ("device", "DEVICE"),
                ("force_language", "FORCE_LANGUAGE"),
                ("min_speakers", "MIN_SPEAKERS"),
                ("max_speakers", "MAX_SPEAKERS"),
            ):
                value = getattr(args, arg)
                if value is not None:
                    config[key] = value
            api.validate_config(config)
            from language_control_v204 import configure

            configure(config, args.source_languages, args.target_language)
            if args.limit_seconds is not None and (
                not math.isfinite(args.limit_seconds) or args.limit_seconds <= 0
            ):
                raise ArgumentError("invalid_limit_seconds")
            if args.require_resume and (args.fresh or args.retry_translation):
                raise ArgumentError("resume_guard_conflicts_with_retry")
            bundled_ffmpeg = paths.root / "_internal/ffmpeg"
            if (bundled_ffmpeg / "ffmpeg.exe").is_file():
                os.environ["PATH"] = (
                    str(bundled_ffmpeg) + os.pathsep + os.environ.get("PATH", "")
                )
            bundled_hf = paths.root / "_internal/models/huggingface"
            if bundled_hf.is_dir():
                os.environ["HF_HOME"] = str(bundled_hf)
                os.environ["HF_HUB_CACHE"] = str(bundled_hf / "hub")
            events.emit(
                "app_ready",
                designation="Backend Freeze",
                journal_schema=1,
                translation_engine_status="PARTIAL",
            )
            if args.validate_config:
                logging.info("CONFIG PASS | backend %s", VERSION)
                events.emit(
                    "job_completed",
                    status="PASS",
                    operation="validate_config",
                    inference_calls={},
                )
                return 0
            source = args.source
            if source is None:
                if machine:
                    raise ArgumentError("source_required_in_ipc_mode")
                files = sorted(
                    f
                    for f in paths.resolve(config["INPUT"]).iterdir()
                    if f.is_file()
                    and f.suffix.lower() in config["SUPPORTED_EXTENSIONS"]
                )
                if not files:
                    raise ArgumentError("no_input_files")
                source = files[0]
                if len(files) > 1:
                    logging.warning(
                        "Multiple input files: using first name; pass a source explicitly."
                    )
            return run_job(
                api,
                paths,
                events,
                telemetry,
                config,
                source,
                require_resume=args.require_resume,
                fresh=args.fresh,
                retry_translation=args.retry_translation,
                limit_seconds=args.limit_seconds,
            )
        except KeyboardInterrupt:
            telemetry.stop()
            events.emit("error", code="interrupted", retryable=True)
            events.emit("job_failed", status="ERROR", code="interrupted")
            return 130
        except Exception as error:
            telemetry.stop()
            # Never forward arbitrary exceptions, model URLs, config values or headers.
            code = str(error) if isinstance(error, ArgumentError) else "backend_failure"
            logging.error(
                "%s (%s); processing stopped; checkpoints retained",
                code,
                type(error).__name__,
            )
            events.emit(
                "error", code=code, error_type=type(error).__name__, retryable=False
            )
            events.emit("job_failed", status="ERROR", code=code)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
