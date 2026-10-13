# Audio2Text — v2.0.5 source baseline

**Release Baseline · DEVELOPMENT: PAUSED · validation: PARTIAL**

## Русский

Локальное Windows-приложение для расшифровки аудио и видео: интерфейс Rust/Slint v2.0.5 и замороженный Python backend v1.5.7. FFmpeg извлекает звук, faster-whisper распознаёт речь, pyannote выделяет говорящих, NLLB переводит на русский. Результаты: TXT, JSON и DOCX. Включены словари TCM и возобновление обработки. В рабочей конфигурации перевод остаётся на CPU.

Это исходный код, а не готовый portable-пакет. Разработка интерфейса приостановлена. Эксперименты v2.0.6, бинарные сборки и release/tag не опубликованы.

### Локальная среда

Нужны отдельно подготовленные Python venv, FFmpeg/FFprobe, совместимые NVIDIA/CUDA библиотеки, разрешённые загрузки моделей и `vendor/text_lid/langid` 1.1.6. Модели, vendor, venv, input/output, кэши, логи и личная конфигурация исключены из Git. Токен Hugging Face хранится только в локальном окружении. Инвентаризация ниже не является инструкцией воспроизводимой установки с нуля.

Для текущего backend используется локальная копия `config_v157.example.json` под именем `config_v157.json`; существующую конфигурацию не перезаписывайте. Старые тесты могут требовать аналогичные копии v155/v156. Приватные роли говорящих и словари храните вне Git. Сборке UI нужны Rust и Windows SDK resource compiler; Cargo.lock включён.

### Проверки и лицензирование

Rust: **34 PASS / 1 GUI-тест пропущен**, fmt и Clippy PASS; есть предупреждение компилятора о замене hardlink на копирование. Последняя проверка включённых Python-тестов: **155 PASS / 1 ошибка окружения**, всего 156; создание hardlink завершается WinError 5. При публикации Python/backend не изменялись. LIVE GUI, перенос на другой компьютер и portable gate не подтверждены. Полная автономная проверка чистого clone не заявляется; некоторые тесты требуют локальной среды. Не запускайте пропущенный Explorer-тест без отдельного разрешения.

**LICENSE собственного кода отсутствует: владелец отложил решение.** Публикация не означает предоставление проектом открытой лицензии. Зависимости и модели сохраняют собственные условия. Slint требует выбора и соблюдения подходящей лицензии, включая атрибуцию при Royalty-Free варианте. Веса NLLB используют CC-BY-NC-4.0. Бинарные зависимости и модели не распространяются. Подробности: [аудит лицензий](docs/DEPENDENCY_LICENSES.md).

## English

Local Windows audio/video transcription with a Rust/Slint v2.0.5 interface and frozen Python v1.5.7 backend. FFmpeg extracts audio, faster-whisper transcribes speech, pyannote assigns speakers, and NLLB translates into Russian. TXT, JSON and DOCX exports, TCM terminology dictionaries and resumable processing are included. Production translation remains on CPU.

This is a source baseline, not a ready-to-run portable package. UI development is paused. v2.0.6 experiments, compiled binaries and release tags are not published.

### Local environment

Supply a separately provisioned Python venv, FFmpeg/FFprobe, compatible NVIDIA/CUDA libraries, authorized model downloads and `vendor/text_lid/langid` 1.1.6. Models, vendor payloads, environments, input/output, caches, logs and private configuration are excluded. Keep Hugging Face credentials in the local environment. The inventory below is observational, not a complete lock or verified fresh-install recipe.

Use a local copy of `config_v157.example.json` named `config_v157.json`; preserve any existing configuration. Older tests may need equivalent v155/v156 copies. Keep private speaker roles and dictionaries outside Git. UI builds require Rust and the Windows SDK resource compiler; Cargo.lock is included.

### Validation and licensing

Rust: **34 PASS / 1 GUI test ignored**, fmt and Clippy PASS, with compiler warnings about hardlink-to-copy fallback. Latest included Python regression run: **155 PASS / 1 environment error**, 156 executed; hardlink creation fails with WinError 5. Python/backend code did not change during publication. LIVE GUI, fresh-machine deployment and full portable acceptance remain unverified. Some tests require the local runtime; a self-contained clean-clone test suite is not claimed. Do not run the ignored Explorer test without separate authorization.

**No project LICENSE has been selected; the owner deferred that decision.** Publication does not grant an open-source license from this project. Dependencies and models retain their own terms. Slint requires an appropriate license route and compliance, including attribution under its Royalty-Free option. NLLB weights use CC-BY-NC-4.0. Neither dependency binaries nor model weights are distributed here. See the [license audit](docs/DEPENDENCY_LICENSES.md) for scope and outstanding binary-distribution checks.

## Observed runtime inventory / Локальная среда

Python 3.12.10; NVIDIA RTX 5060 / driver 616.92; torch/torchaudio 2.11.0+cu128; faster-whisper 1.2.1; ctranslate2 4.8.1; pyannote.audio 4.0.7; transformers 5.0.0; sentencepiece 0.2.1; numpy 2.4.6; librosa 0.11.0; soundfile 0.14.0; python-docx 1.2.0; psutil 7.2.2.

Required UI source artwork is included; compiled artifacts are not. `.gitattributes` preserves exact bytes for frozen-source SHA256 validation. Included dictionaries contain generic terminology mappings. Private regression media and its dedicated test remain outside Git. Test scratch data belongs in ignored `tests/.runtime`.

## Project records / Документы

- [Current checkpoint](docs/EXPC_CHECKPOINT.md)
- [Paused backlog](docs/EXPC_BACKLOG.md)
- [Public audit](docs/PUBLIC_AUDIT_V205.md)
- [Dependency licenses](docs/DEPENDENCY_LICENSES.md)
- [Windows Rust dependency inventory](docs/DEPENDENCY_LICENSES_WINDOWS.json)
- [Baseline validation](docs/GIT_BASELINE_V205.md)
- [Source SHA256 manifest](docs/V205_SOURCE_SHA256.json)
