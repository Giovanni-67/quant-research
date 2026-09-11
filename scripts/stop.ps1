param([string]$PythonExe)
. "$PSScriptRoot\common.ps1"
$ProcessFile = Join-Path $StateDirectory 'processes.json'
if (-not (Test-Path -LiteralPath $ProcessFile)) { Write-Output 'No saved processes.'; return }
$Existing = Get-Content -LiteralPath $ProcessFile -Raw | ConvertFrom-Json
foreach ($Item in $Existing) {
    if (Get-DeskProcess $Item.id $Item.started) {
        Stop-Process -Id $Item.id
        Write-Output "Stopped Research Desk $($Item.command)."
    }
}
Remove-Item -LiteralPath $ProcessFile
