[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$PackagePath
)

$ErrorActionPreference = 'Stop'

function Resolve-PackageRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $candidate = (Resolve-Path -LiteralPath $Path).Path
    $directDb = Join-Path $candidate 'data\real\observatorio_real.sqlite3'
    if (Test-Path -LiteralPath $directDb -PathType Leaf) {
        return $candidate
    }

    $nested = Get-ChildItem -LiteralPath $candidate -Directory -Force |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'data\real\observatorio_real.sqlite3') } |
        Select-Object -First 1
    if ($null -ne $nested) {
        return $nested.FullName
    }

    throw "No se encontró data\real\observatorio_real.sqlite3 bajo '$candidate'."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedInput = (Resolve-Path -LiteralPath $PackagePath).Path
$temporaryRoot = $null

try {
    if ((Get-Item -LiteralPath $resolvedInput).PSIsContainer) {
        $sourceRoot = Resolve-PackageRoot -Path $resolvedInput
    } elseif ([IO.Path]::GetExtension($resolvedInput) -ieq '.zip') {
        $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("observatorio-runtime-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
        Expand-Archive -LiteralPath $resolvedInput -DestinationPath $temporaryRoot -Force
        $sourceRoot = Resolve-PackageRoot -Path $temporaryRoot
    } else {
        throw "PackagePath debe ser una carpeta de paquete o un archivo .zip: '$resolvedInput'."
    }

    $sourceData = Join-Path $sourceRoot 'data\real'
    $targetData = Join-Path $repoRoot 'data\real'
    New-Item -ItemType Directory -Path $targetData -Force | Out-Null

    $database = Join-Path $sourceData 'observatorio_real.sqlite3'
    if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
        throw "Falta la base histórica: '$database'."
    }
    Copy-Item -LiteralPath $database -Destination (Join-Path $targetData 'observatorio_real.sqlite3') -Force

    foreach ($directoryName in @('originals', 'history_imports', 'geography')) {
        $sourceDirectory = Join-Path $sourceData $directoryName
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            $targetDirectory = Join-Path $targetData $directoryName
            New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
            Get-ChildItem -LiteralPath $sourceDirectory -Force |
                Copy-Item -Destination $targetDirectory -Recurse -Force
        }
    }

    $dbSize = (Get-Item -LiteralPath (Join-Path $targetData 'observatorio_real.sqlite3')).Length
    $gtfsCount = @(Get-ChildItem -LiteralPath (Join-Path $targetData 'originals') -Filter '*.zip' -File -ErrorAction SilentlyContinue).Count
    Write-Host "Datos históricos preparados en '$targetData'."
    Write-Host ("SQLite: {0:N0} bytes; ZIP GTFS: {1}" -f $dbSize, $gtfsCount)
    Write-Host 'Siguiente paso: EJECUTAR_OBSERVATORIO_HISTORICO_v1.bat'
} finally {
    if ($null -ne $temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
