param([switch]$Offline, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$cargoArgs = @('--locked', '--manifest-path', (Join-Path $projectRoot 'frontend/Cargo.toml'))
if ($Offline) { $cargoArgs += '--offline' }
if ($CheckOnly) {
    & cargo check @cargoArgs
} else {
    & cargo build --release @cargoArgs
}
if ($LASTEXITCODE -ne 0) { throw "Cargo failed: $LASTEXITCODE" }
# No copying over an existing EXE, GUI launch, model download or package creation.
