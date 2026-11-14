$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw 'Install CMake with Visual Studio 18 2026 generator support and add it to PATH.'
}
$vswherePath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswherePath)) {
    throw 'Install Visual Studio 2026 with the Desktop development with C++ workload.'
}
$vsInstall = & $vswherePath -latest -version '[18.0,19.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsInstall) {
    throw 'Visual Studio 2026 C++ tools were not found. Install the Desktop development with C++ workload.'
}
Push-Location $repoRoot
try {
    & cmake --preset windows-x64 -DENABLE_WHATSNEW=OFF
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
    & cmake --build --preset windows-x64
    if ($LASTEXITCODE -ne 0) { throw 'Ocal Record build failed.' }
    $runDirectory = Join-Path $repoRoot 'build_x64/rundir/RelWithDebInfo'
    $executable = Join-Path $runDirectory 'bin/64bit/obs64.exe'
    if (-not (Test-Path -LiteralPath $executable)) { throw "Built executable not found: $executable" }
    New-Item -ItemType File -Path (Join-Path $runDirectory 'portable_mode.txt') -Force | Out-Null
    Write-Output "Ocal Record built successfully: $executable"
} finally {
    Pop-Location
}
