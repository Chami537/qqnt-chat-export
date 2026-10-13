param(
    [Parameter(Mandatory = $true)]
    [string]$BuildRoot,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
$systemRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath("$env:SystemDrive\"))
if ([IO.Path]::GetPathRoot($BuildRoot) -ieq $systemRoot) {
    throw "构建目录不能位于系统盘"
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$env:TEMP = Join-Path $BuildRoot "tmp"
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PYINSTALLER_CONFIG_DIR | Out-Null

Push-Location $repoRoot
try {
    & $PythonExe -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name qqnt-export-gui `
        --distpath (Join-Path $BuildRoot "dist") `
        --workpath (Join-Path $BuildRoot "work") `
        --specpath (Join-Path $BuildRoot "spec") `
        --collect-all sqlcipher3 `
        --collect-data qqnt_export `
        "src/qqnt_export/gui/__main__.py"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }
    Copy-Item -LiteralPath (Join-Path $repoRoot "THIRD_PARTY_NOTICES.md") `
        -Destination (Join-Path $BuildRoot "dist/qqnt-export-gui/THIRD_PARTY_NOTICES.md")
} finally {
    Pop-Location
}

Write-Output (Join-Path $BuildRoot "dist/qqnt-export-gui/qqnt-export-gui.exe")
