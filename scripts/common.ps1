$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) {
    $BundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $BundledPython) { $PythonExe = $BundledPython }
    else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
$RunPath = Join-Path $ProjectRoot 'run.py'
$StateDirectory = Join-Path $ProjectRoot 'var'
New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null

function Get-DeskProcess($ProcessId, $ExpectedStart) {
    $ProcessRecord = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($ProcessRecord -and $ProcessRecord.Path -eq $PythonExe -and
        $ProcessRecord.StartTime.ToUniversalTime().Ticks.ToString() -eq $ExpectedStart) {
        return $ProcessRecord
    }
    return $null
}
