param(
    [string]$TaskName = "MDR-Docker-Startup",
    [string]$WslDistro = "Ubuntu-22.04",
    [string]$ProjectPath = "/opt/mdr_app"
)

function Ensure-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script in an elevated PowerShell session (Run as Administrator)."
    }
}

Ensure-Admin

$wslCmd = "docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d"
$arguments = "-d $WslDistro --cd $ProjectPath -e sh -lc `"$wslCmd`""

$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' registered successfully."
Write-Host "Command: wsl.exe $arguments"
