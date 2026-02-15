param(
    [switch]$RemoveRules
)

$rules = @(
    @{ Name = "MDR-HTTP-80"; Port = 80; Action = "Allow" },
    @{ Name = "MDR-HTTPS-443"; Port = 443; Action = "Allow" },
    @{ Name = "MDR-BLOCK-8000"; Port = 8000; Action = "Block" },
    @{ Name = "MDR-BLOCK-5432"; Port = 5432; Action = "Block" }
)

function Ensure-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script in an elevated PowerShell session (Run as Administrator)."
    }
}

Ensure-Admin

if ($RemoveRules) {
    foreach ($rule in $rules) {
        Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    }
    Write-Host "MDR firewall rules removed."
    exit 0
}

foreach ($rule in $rules) {
    Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule `
        -DisplayName $rule.Name `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $rule.Port `
        -Action $rule.Action | Out-Null
}

Write-Host "MDR firewall rules applied successfully."
