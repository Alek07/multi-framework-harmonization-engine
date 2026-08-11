# UCM-20 — starts the whole system. Twin of start.sh; see README.md.
# UTF-8 *with BOM*: PowerShell 5.1 reads a BOM-less script as ANSI and mangles
# every accent in the Spanish output.

[CmdletBinding()]
param(
    [switch]$Cpu,
    [switch]$Gpu,
    [switch]$Build,
    [switch]$Down,
    [switch]$Logs,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Project = 'tfm-harmonization-engine'

function Say {
    param([string]$Text = '', [string]$Colour = $null)
    if ($Colour) { Write-Host $Text -ForegroundColor $Colour } else { Write-Host $Text }
}

if ($Help) {
    Say ""
    Say "Uso: .\scripts\start.ps1 [opción]"
    Say ""
    Say "  (sin opción)   Detecta el hardware, arranca los cuatro contenedores, espera a"
    Say "                 que estén listos y comprueba dónde quedó el modelo."
    Say "  -Cpu           Fuerza la ruta portable (CPU). Es la ruta reproducible."
    Say "  -Gpu           Fuerza la ruta GPU. Falla si Docker no puede ceder una tarjeta."
    Say "  -Build         Reconstruye las imágenes de frontend y backend antes de"
    Say "                 arrancar. Sin esto, Docker reutiliza la imagen ya construida"
    Say "                 y los cambios en el código no llegan al contenedor."
    Say "  -Down          Para el sistema. Los volúmenes se conservan."
    Say "  -Logs          Sigue los registros de los cuatro servicios."
    Say "  -Help          Esta ayuda."
    Say ""
    Say "Se pueden combinar: .\scripts\start.ps1 -Cpu -Build"
    Say "Más información: README.md"
    Say ""
    exit 0
}

if ($Down) { & docker compose -p $Project down; exit $LASTEXITCODE }
if ($Logs) { & docker compose -p $Project logs -f; exit $LASTEXITCODE }

& docker info --format '{{.ServerVersion}}' > $null
if ($LASTEXITCODE -ne 0) {
    Say ""
    Say "  Docker no responde." 'Red'
    Say "  Arranca Docker Desktop y vuelve a intentarlo."
    Say ""
    exit 1
}

$composeVersion = & docker compose version --short
if ($LASTEXITCODE -ne 0) { $composeVersion = '?' }

# Ask the daemon, not the host: a card Docker cannot pass through is unusable.
function Test-GpuRuntime {
    $runtimes = & docker info --format '{{json .Runtimes}}'
    if ($LASTEXITCODE -ne 0) { return $false }
    return ($runtimes -match '"nvidia"')
}

function Get-GpuName {
    $name = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { return $null }
    if ($name -is [array]) { return $name[0] }
    return $name
}

function Get-GpuVramGb {
    $mib = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits
    if ($LASTEXITCODE -ne 0) { return 0 }
    if ($mib -is [array]) { $mib = $mib[0] }
    return [math]::Floor([double]$mib / 1024)
}

$files = @('-f', 'docker-compose.yml')
$pathLabel = 'CPU'

if ($Cpu) {
    $pathLabel = 'CPU (forzada)'
} elseif ($Gpu) {
    if (-not (Test-GpuRuntime)) {
        Say ""
        Say "  Se pidió -Gpu, pero Docker no expone el runtime 'nvidia'." 'Red'
        Say "  Sin ese runtime la reserva de dispositivo hace fallar el arranque entero."
        Say "  Arranca sin la opción (o con -Cpu) para usar la ruta portable."
        Say ""
        exit 1
    }
    $files = @('-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml')
    $pathLabel = 'GPU (forzada)'
} elseif (Test-GpuRuntime) {
    $files = @('-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml')
    $pathLabel = 'GPU'
}

# Docker's MemTotal, not the host's: on Docker Desktop the VM's share is what binds.
$memGb = 0
$memBytes = & docker info --format '{{.MemTotal}}'
if ($LASTEXITCODE -eq 0) { $memGb = [math]::Floor([double]$memBytes / 1GB) }

$model = 'qwen2.5:7b-instruct-q4_K_M'
if (Test-Path '.env') {
    $line = Get-Content '.env' | Where-Object { $_ -match '^LLM_MODEL=' } | Select-Object -Last 1
    if ($line) { $model = ($line -replace '^LLM_MODEL=', '').Trim() }
}

Say ""
Say "  Motor de armonización multi-marco"
Say ""
Say ("  Docker         ok  Compose {0}, {1} GB de memoria" -f $composeVersion, $memGb)
if ($pathLabel -like 'GPU*') {
    $card = Get-GpuName
    if (-not $card) { $card = 'tarjeta NVIDIA accesible desde Docker' }
    Say ("  Hardware       ok  {0}" -f $card)
} elseif (Test-GpuRuntime) {
    # A card present but unused must not read as absent, or -Cpu looks broken.
    $card = Get-GpuName
    if (-not $card) { $card = 'tarjeta NVIDIA' }
    Say ("  Hardware       {0} (disponible, sin usar por elección)" -f $card)
} else {
    Say "  Hardware       sin GPU accesible desde Docker"
}
Say ("  Ruta           {0}  {1}" -f $pathLabel, ($files -join ' '))
Say ("  Modelo         {0}" -f $model)

# On GPU the weights live in VRAM, so the RAM Docker got is the wrong yardstick.
if ($pathLabel -like 'GPU*') {
    $haveGb = Get-GpuVramGb
    $where = 'en la tarjeta'
} else {
    $haveGb = $memGb
    $where = 'disponibles para Docker'
}

# Recommend only: picking weights by machine size would break invariant 3.
if ($model -like '*7b*' -and $haveGb -gt 0 -and $haveGb -le 6) {
    Say ""
    Say ("  Aviso          el modelo fijado (7B) necesita ~6 GB residentes y hay {0} GB {1}." -f $haveGb, $where) 'Yellow'
    Say "                 El fallback documentado para máquinas pequeñas son estas dos"
    Say "                 líneas en el fichero .env:"
    Say ""
    Say "                   LLM_MODEL=qwen2.5:3b-instruct-q4_K_M" 'DarkGray'
    Say "                   LLM_MODEL_DIGEST=357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b" 'DarkGray'
    Say ""
    Say "                 Se continúa con el 7B: unos pesos distintos dan un borrador"
    Say "                 distinto, así que ese cambio lo decide una persona."
}

Say ""
if ($Build) { Say "  Reconstruyendo las imágenes y arrancando cuatro contenedores..." }
else        { Say "  Arrancando cuatro contenedores..." }

# `--progress quiet`, not a redirect: in PS 5.1 redirecting a native command's
# stderr wraps each line in an ErrorRecord, which aborts the script.
$upArgs = @('up', '-d')
$progress = @('--progress', 'quiet')
# A build is worth watching: a quiet progress bar would hide a compile error.
if ($Build) { $upArgs += '--build'; $progress = @() }

& docker compose -p $Project @files @progress @upArgs
if ($LASTEXITCODE -ne 0) {
    Say ""
    Say "  El arranque ha fallado." 'Red'
    exit 1
}

$started = Get-Date

function Get-ServiceHealth {
    param([string]$Service)
    try {
        $out = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$Project-$Service"
    } catch {
        return 'missing'
    }
    if ($LASTEXITCODE -ne 0) { return 'missing' }
    if ($out -is [array]) { return $out[0] }
    return $out
}

# `Note` prints once, past `After` seconds, so a long first pull explains itself.
function Wait-Healthy {
    param([string]$Service, [int]$After = 0, [string]$Note = '')
    $noted = $false
    while ($true) {
        $status = Get-ServiceHealth -Service $Service
        if ($status -eq 'healthy') { break }
        if ($status -eq 'missing') {
            Say ("    {0,-12} no existe" -f $Service) 'Red'
            return $false
        }
        $elapsed = [int]((Get-Date) - $started).TotalSeconds
        if ($Note -and -not $noted -and $elapsed -ge $After) {
            Say ("    {0,-12} {1}" -f $Service, $Note) 'DarkGray'
            $noted = $true
        }
        Start-Sleep -Seconds 3
    }
    $secs = [int]((Get-Date) - $started).TotalSeconds
    Say ("    {0,-12} listo   ({1} s)" -f $Service, $secs) 'Green'
    return $true
}

if (-not (Wait-Healthy -Service 'qdrant')) { exit 1 }
if (-not (Wait-Healthy -Service 'backend' -After 20 -Note 'arrancando (el primer arranque descarga ~1,1 GB de embeddings)')) { exit 1 }
if (-not (Wait-Healthy -Service 'frontend')) { exit 1 }
if (-not (Wait-Healthy -Service 'ollama' -After 20 -Note 'preparando el modelo (la primera vez descarga ~4,7 GB)')) { exit 1 }

Say ""

$ollamaPort = if ($env:OLLAMA_PORT) { $env:OLLAMA_PORT } else { '11434' }
$ollamaUrl = "http://localhost:$ollamaPort"

function Get-LoadedModels {
    try { return Invoke-RestMethod -Uri "$ollamaUrl/api/ps" -TimeoutSec 10 } catch { return $null }
}

$psData = Get-LoadedModels

# `/api/ps` lists only loaded models, and OLLAMA_KEEP_ALIVE evicts them. Preload
# with an empty prompt (Ollama's documented no-op) so there is something to check
# and the operator's first read does not pay the ~185 s load.
if (-not $psData -or -not $psData.models -or $psData.models.Count -eq 0) {
    $keep = '30m'
    if (Test-Path '.env') {
        $kline = Get-Content '.env' | Where-Object { $_ -match '^OLLAMA_KEEP_ALIVE=' } | Select-Object -Last 1
        if ($kline) { $keep = ($kline -replace '^OLLAMA_KEEP_ALIVE=', '').Trim() }
    }
    Say "  Precargando    llevando los pesos a memoria (segundos en GPU, ~3 min en CPU)..."
    $body = @{ model = $model; prompt = ''; keep_alive = $keep } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "$ollamaUrl/api/generate" -Method Post -Body $body `
            -ContentType 'application/json' -TimeoutSec 900 | Out-Null
    } catch { }
    $psData = Get-LoadedModels
}

# Applying the overlay is not the same as the weights reaching the card.
if ($psData -and $psData.models -and $psData.models.Count -gt 0) {
    $size = [double]$psData.models[0].size
    $vram = [double]$psData.models[0].size_vram
    if ($size -gt 0) {
        $pct = [int](($vram * 100) / $size)
        $sizeGb = '{0:N2}' -f ($size / 1GB)
        $vramGb = '{0:N2}' -f ($vram / 1GB)
        if ($pct -ge 99) {
            Say ("  Verificado     modelo residente en GPU: {0} GB de {1} GB ({2} %)" -f $vramGb, $sizeGb, $pct) 'Green'
        } elseif ($pct -gt 0) {
            Say ("  Verificado     sólo el {0} % del modelo en GPU; el resto en CPU" -f $pct) 'Yellow'
        } else {
            Say "  Verificado     modelo en CPU (size_vram = 0)"
            if ($pathLabel -like 'GPU*') {
                Say "  Atención       se pidió la ruta GPU y el modelo no ha entrado en la tarjeta." 'Yellow'
                Say "                 Suele ser un driver del host más antiguo que el runtime CUDA"
                Say "                 del contenedor: 'docker compose logs ollama' lo dice."
            }
        }
    }
}

$frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '8080' }
$backendPort  = if ($env:BACKEND_PORT)  { $env:BACKEND_PORT }  else { '8000' }

Say ""
Say "  Listo."
Say ("    Interfaz       http://localhost:{0}" -f $frontendPort)
Say ("    API y Swagger  http://localhost:{0}/docs" -f $backendPort)
Say ""

# Named out loud so choosing the GPU stays a declared act, not a silent one.
if ($pathLabel -like 'GPU*') {
    Say "  Nota: esta ejecución usa GPU. Las medidas de la evaluación se tomaron en" 'DarkGray'
    Say "  CPU y el borrador del parseo puede diferir; lo que viene después de" 'DarkGray'
    Say "  revisarlo es idéntico. Ruta reproducible:  .\scripts\start.ps1 -Cpu" 'DarkGray'
    Say ""
}
