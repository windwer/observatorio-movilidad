param(
    [Parameter(Mandatory=$true)][string]$ReleaseDirectory,
    [string]$StateDirectory,
    [string]$Python='python',
    [ValidateRange(1024,65535)][int]$Port=8874
)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
$releaseRoot=(Resolve-Path -LiteralPath $ReleaseDirectory).Path
if(-not $StateDirectory){$StateDirectory=Join-Path $repoRoot 'data\runtime'}
$null=New-Item -ItemType Directory -Path $StateDirectory -Force
$stateRoot=(Resolve-Path -LiteralPath $StateDirectory).Path
$manifest=Get-Content -LiteralPath (Join-Path $releaseRoot 'release-manifest.json') -Raw | ConvertFrom-Json
$env:OBS_DB=Join-Path $releaseRoot 'observatorio_real.sqlite3'
$env:OBS_GEOGRAPHY_DIR=Join-Path $releaseRoot 'geography'
$env:OBS_REFERENCE_CSV=Join-Path $releaseRoot 'references\eustat_2025_original.csv'
$env:OBS_STATE_DB=Join-Path $stateRoot 'state.sqlite3'
$env:OBS_DATA_RELEASE=$manifest.release_id
$env:OBS_IMMUTABLE_DATA='1'
$env:OBS_HOST='127.0.0.1'
$env:OBS_PORT=[string]$Port
$env:OBS_PUBLIC_READ='1'
& $Python (Join-Path $repoRoot 'launcher.py')
if($LASTEXITCODE -ne 0){throw 'El lanzador local ha terminado con error.'}
