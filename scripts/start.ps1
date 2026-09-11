param([string]$PythonExe, [int]$Port = 8765)
. "$PSScriptRoot\common.ps1"
$ProcessFile = Join-Path $StateDirectory 'processes.json'
if (Test-Path -LiteralPath $ProcessFile) {
    $Existing = Get-Content -LiteralPath $ProcessFile -Raw | ConvertFrom-Json
    foreach ($Item in $Existing) {
        if (Get-DeskProcess $Item.id $Item.started) {
            throw 'A saved Research Desk process is still running. Use scripts/stop.ps1 before restarting.'
        }
    }
}
$Launched = @()
try {
    foreach ($Command in @('dashboard','worker')) {
        $Arguments = '"' + $RunPath + '" ' + $Command
        if ($Command -eq 'dashboard') { $Arguments += ' --port ' + $Port }
        $Child = Start-Process -FilePath $PythonExe -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $StateDirectory "$Command.log") -RedirectStandardError (Join-Path $StateDirectory "$Command.error.log")
        $Launched += @{ id = $Child.Id; command = $Command; started = $Child.StartTime.ToUniversalTime().Ticks.ToString() }
        try { $Child.PriorityClass = 'BelowNormal' } catch { Write-Warning 'Could not lower process priority; normal priority will be used.' }
    }
    $Launched | ConvertTo-Json | Set-Content -LiteralPath $ProcessFile -Encoding UTF8
    Start-Sleep -Seconds 2
    foreach ($Item in $Launched) {
        if (-not (Get-DeskProcess $Item.id $Item.started)) { throw "Research Desk $($Item.command) failed; inspect var logs." }
    }
    Write-Output "Research Desk: http://127.0.0.1:$Port"
    Write-Output 'Dashboard and worker run hidden. You can turn off the display and use the computer normally. Stop with scripts/stop.ps1.'
} catch {
    foreach ($Item in $Launched) {
        if (Get-DeskProcess $Item.id $Item.started) { Stop-Process -Id $Item.id }
    }
    throw
}
