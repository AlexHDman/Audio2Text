# CACHE_MANAGER_V1 — Audio2Text 2.0.5

Status: IMPLEMENTED / automated safety PASS / LIVE visual acceptance NOT TESTED.

## Delivered

Header action **Кэш** before Settings opens **КЭШ ПРОЕКТОВ** without changing the existing lower panels, forest, assets or motion. Rows use the existing LivingCheck component. Selection, select all completed, selected count/bytes, total known project bytes, refresh, delete selected and close are implemented.

One source path + source SHA256 is one project. Its processing variants are combined; deletion confirmation covers all displayed variants. Filename is primary; internal directory IDs are only service data. Latest variant supplies date (explicit UTC), duration and languages; variant count is shown. Same filename with changed content is a separate project. COMPLETED means the processing/export checkpoint finished, including exported PARTIAL/review results; it does not certify translation quality.

Live read-only inventory: **1 project / 2 processing variants / 22,138,389 bytes (21.1 MiB)**. One protected service/unknown entry: temp/v157/runtime. Unknown bytes are explicitly excluded, never silently counted as zero.

## Ownership and deletion

Service: cache_manager_v205.py. Rust UI invokes it using the selected Python executable, argument arrays, bounded asynchronous work and JSON stdin/stdout. It validates existing schema 2 using the unchanged engine validator; it performs no model loading/inference.

Approved roots are exactly APP_ROOT/temp/v157 and APP_ROOT/cache/jobs. Names must match source SHA256 prefix + processing fingerprint prefix, optionally an engine fresh/recovery suffix. Checksum-valid source/processing metadata and known flat contents are required. Only resume.json and prepared.wav can be removed. run.lock protects active or stale/uncertain jobs. Unexpected files/subdirectories, symlinks/junctions/reparse points, hardlinked files, wrong ownership and changed selection fail closed.

Deletion re-discovers all selected variants, verifies selection tokens, pins Windows ancestor directories with read handles denying delete sharing, acquires the same exclusive create-new run.lock as the engine, then revalidates. Only known files are unlinked; the final directory removal is nonrecursive. Windows directory replacement protection was physically exercised in a synthetic fixture. Failure never invokes a broader cleanup fallback.

COMPLETED requires complete export with export.at equal to updated_at, finished diarization and all ASR units finished. An old export marker after a later checkpoint is INCOMPLETE. Resume availability additionally checks prepared.wav SHA256. INCOMPLETE selection requires a second explicit confirmation about loss of resume. The normal deletion confirmation lists filenames, count and bytes and states that output remains.

While the current frontend backend worker is alive, deletion is disabled; catalog rows are conservatively protected during discovery. OS close is held while a cache operation is running. Existing backend cancellation/job-object behavior remains intact.

## Protected data

No cleanup code enumerates a generic user-selected root. input, output, assets, frontend, models, runtime, ffmpeg, venv, Hugging Face caches, cache/system, old version namespaces, publication state and unrelated logs are outside the allowlist. Real jobs were only read during this task; deletion tests used tests/.runtime temporary fixtures.

17/17 safety tests: completed cleanup, incomplete confirmation, active/stale/new locks, modified snapshot, unknown files, corrupt checksum, ownership mismatch, traversal/absolute/protected roots, future layout, grouping, missing variants/confirmation, reparse attribute, hardlinks, directory pinning, stale export, prepared checksum. Test source and logs are under tests/test_cache_manager_v205.py and dev/validation_v205/cache_tests.log.

## Exit policy

Prepared configuration key: logs/frontend_v2_settings.json -> cache_exit_policy.
Values: ask (default/fallback), always_clean_completed, never. Rust validates and preserves it when settings are saved.

**Execution of exit cleanup is deliberately deferred.** No automatic deletion occurs for ANY value in this candidate. No close dialog or automatic-clean preference is exposed until its integration with cancellation/process ownership is LIVE tested. Required future dialog: “Очистить временные данные текущего задания? Готовые результаты в output останутся.” Actions: Очистить / Оставить / Отмена; incomplete jobs recommend KEEP.

## Portable layout and migration

cache/jobs is ready as an additional discovery root; cache/system is protected. The current production TEMP config remains temp/v157, unchanged. Future portable packaging must explicitly configure TEMP=cache/jobs, because the frozen portable default is _internal/temp/v157.

No current cache was migrated. Source/model identities include absolute paths and model metadata: moving a cache to another drive does not guarantee reuse. A future migration requires separate manifests, copy-only preparation, original retention and validation on the new drive. Unknown content remains protected, never “fixed” by deleting it.
