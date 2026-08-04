# UCM-20 - bring the runtime services up, adding the GPU overlay if Docker has one.
#
#   .\scripts\up.ps1                      # detect, then `up -d`
#   .\scripts\up.ps1 -Cpu                 # force the portable path
#   .\scripts\up.ps1 -Cpu logs -f ollama  # anything else goes straight to compose
#
# Never refuses to start: no GPU means the CPU stack. COMPOSE_FILE, if you set it,
# wins over detection.
#
# ASCII only: PowerShell 5.1 reads a .ps1 as ANSI without a BOM, so an accent here
# is a parse error on exactly the machines this exists to support.

[CmdletBinding()]
param(
    [switch]$Cpu,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArgs
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

# Asking the daemon, not the host: a card Docker cannot reach is one the model
# cannot use. Covers WSL2, rootless and remote contexts alike.
function Test-GpuRuntime {
    try {
        $runtimes = docker info --format '{{json .Runtimes}}'
    } catch {
        return $false
    }
    if ($LASTEXITCODE -ne 0) { return $false }
    return ($runtimes -match '"nvidia"')
}

# -f flags, not COMPOSE_FILE: that variable splits on the platform's path separator
# (';' on Windows, ':' elsewhere).
if ($Cpu) {
    Write-Host "==> forced to CPU (-Cpu): the portable path, the one reproducibility rests on"
    $files = @('-f', 'docker-compose.yml')
} elseif ($env:COMPOSE_FILE) {
    Write-Host "==> COMPOSE_FILE is already set; leaving it alone: $($env:COMPOSE_FILE)"
    $files = @()
} elseif (Test-GpuRuntime) {
    Write-Host "==> Docker exposes the 'nvidia' runtime: adding docker-compose.gpu.yml"
    Write-Host "    (check afterwards with: curl localhost:11434/api/ps - size_vram > 0)"
    $files = @('-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml')
} else {
    Write-Host "==> no GPU reachable from Docker: starting on CPU, which works anywhere"
    Write-Host "    (reading a description takes longer; nothing else changes)"
    $files = @('-f', 'docker-compose.yml')
}

if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
    $ComposeArgs = @('up', '-d')
}

$all = $files + $ComposeArgs
Write-Host "==> docker compose $($all -join ' ')"
& docker compose @all
exit $LASTEXITCODE
