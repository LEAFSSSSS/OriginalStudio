param(
    [string]$PythonExecutable = "$PSScriptRoot\.venv\Scripts\python.exe",
    [switch]$IncludeAI,
    [string]$ModelPath
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath $PythonExecutable)) { throw 'Run install.bat first, or specify -PythonExecutable.' }
if ($ModelPath) {
    $resolvedModelPath = (Resolve-Path -LiteralPath $ModelPath).Path
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedModelPath 'config.json'))) { throw 'ModelPath must contain config.json.' }
    if (-not $IncludeAI) { throw 'Use -IncludeAI when bundling a model.' }
    $env:STUDIO_BUILD_MODEL = $resolvedModelPath
} else { Remove-Item Env:STUDIO_BUILD_MODEL -ErrorAction SilentlyContinue }
$env:STUDIO_BUILD_AI = if ($IncludeAI) { '1' } else { '0' }
& $PythonExecutable -m pip install --index-url https://pypi.org/simple 'pyinstaller==6.16.0'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
& $PythonExecutable -m PyInstaller --noconfirm --distpath release --workpath build OriginalStudio.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
& $PythonExecutable tools/collect_notices.py release/OriginalStudio/notices
if ($LASTEXITCODE -ne 0) { throw 'Notice collection failed.' }
Write-Output 'Build ready: release\OriginalStudio\OriginalStudio.exe. Keep the complete directory together.'
