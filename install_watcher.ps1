param([string]$GitDirectory = '')
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$taskName = 'ComfyUI-Gallery-Watcher'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe not found.' }
if (-not $GitDirectory) {
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($gitCommand) { $GitDirectory = Split-Path $gitCommand.Source }
    else {
        $candidates = @(
            "$env:ProgramFiles\Git\cmd",
            "$env:LOCALAPPDATA\Programs\Git\cmd",
            "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd"
        )
        $GitDirectory = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'git.exe') } | Select-Object -First 1
    }
}
if (-not $GitDirectory -or -not (Test-Path -LiteralPath (Join-Path $GitDirectory 'git.exe'))) { throw 'git.exe not found.' }
$GitDirectory = (Resolve-Path -LiteralPath $GitDirectory).Path
& $python -c 'import PIL'
if ($LASTEXITCODE -ne 0) { throw 'Pillow is missing; install requirements.txt first.' }
$runner = Join-Path $projectDirectory 'watch_background.py'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Arguments -notcontains ('"{0}" --git-dir "{1}"' -f $runner, $GitDirectory)) {
        throw "Existing task $taskName has a different action; inspect before replacing."
    }
    Stop-ScheduledTask -TaskName $taskName
}
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --git-dir "{1}"' -f $runner, $GitDirectory) -WorkingDirectory $projectDirectory
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$trigger.Delay = 'PT30S'
$recoveryTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$definition = New-ScheduledTask -Action $action -Trigger @($trigger, $recoveryTrigger) -Principal $principal -Settings $settings -Description 'ComfyUI gallery: hidden watcher with auto push; logon startup and 1-minute recovery check; no duplicate instances.'
if ($existing) { Register-ScheduledTask -TaskName $taskName -InputObject $definition -Force | Out-Null }
else { Register-ScheduledTask -TaskName $taskName -InputObject $definition | Out-Null }
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Write-Output "Log: $projectDirectory\.local\watcher.log"
