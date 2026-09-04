#!/usr/bin/env bash
# UCM-20 — starts the whole system. See README.md.
set -eu

cd "$(dirname "$0")/.."

readonly PROJECT=tfm-harmonization-engine

if [ -t 1 ]; then
  B='\033[1m'; DIM='\033[2m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RED='\033[1;31m'; R='\033[0m'
else
  B=''; DIM=''; GREEN=''; YELLOW=''; RED=''; R=''
fi

say() { printf "$@"; printf '\n'; }

usage() {
  cat <<'EOF'
Uso: ./scripts/start.sh [opción]

  (sin opción)   Detecta el hardware, arranca los cuatro contenedores, espera a
                 que estén listos y comprueba dónde quedó el modelo.
  --cpu          Fuerza la ruta portable (CPU). Es la ruta reproducible.
  --gpu          Fuerza la ruta NVIDIA (CUDA). Falla si Docker no expone el runtime.
  --rocm         Fuerza la ruta AMD (ROCm, sólo Linux). Falla si no hay /dev/kfd.
  --build        Reconstruye las imágenes de frontend y backend antes de
                 arrancar. Sin esto, Docker reutiliza la imagen ya construida y
                 los cambios en el código no llegan al contenedor.
  --down         Para el sistema. Los volúmenes se conservan.
  --logs         Sigue los registros de los cuatro servicios.
  -h, --help     Esta ayuda.

Se pueden combinar: ./scripts/start.sh --cpu --build

Más información: README.md
EOF
}

MODE=auto
BUILD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --cpu)   MODE=cpu ;;
    --gpu)   MODE=gpu ;;
    --rocm)  MODE=rocm ;;
    --build) BUILD="--build" ;;
    --down)  exec docker compose -p "$PROJECT" down ;;
    --logs)  exec docker compose -p "$PROJECT" logs -f ;;
    -h|--help) usage; exit 0 ;;
    *) say "Opción desconocida: %s\n" "$1"; usage; exit 1 ;;
  esac
  shift
done

if ! docker info >/dev/null 2>&1; then
  say "${RED}Docker no responde.${R}"
  say "Arranca Docker Desktop (o el demonio de Docker) y vuelve a intentarlo."
  exit 1
fi

compose_version=$(docker compose version --short 2>/dev/null || echo '?')

# Ask the daemon, not the host: a card Docker cannot pass through is unusable.
has_gpu_runtime() {
  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
}

gpu_name() {
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1
}

# The card may be physically present yet invisible to Docker (toolkit missing): a
# fixable setup, worth telling apart from having no GPU at all.
has_nvidia_host() {
  nvidia-smi -L >/dev/null 2>&1
}

# AMD ROCm has no Docker runtime to ask; the amdgpu kernel driver exposes these nodes,
# and their absence (Windows/macOS VM, no driver) is exactly when the overlay would fail.
has_amd_gpu() {
  [ -e /dev/kfd ] && [ -e /dev/dri ]
}

gpu_vram_gb() {
  mib=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
  [ -n "${mib:-}" ] && echo $(( mib / 1024 )) || echo 0
}

FILES="-f docker-compose.yml"
PATH_LABEL="CPU"
case "$MODE" in
  cpu)
    PATH_LABEL="CPU (forzada)"
    ;;
  gpu)
    if ! has_gpu_runtime; then
      say "${RED}Se pidió --gpu, pero Docker no expone el runtime 'nvidia'.${R}"
      say "Sin ese runtime la reserva de dispositivo hace fallar el arranque entero."
      say "Arranca sin la opción (o con --cpu) para usar la ruta portable."
      exit 1
    fi
    FILES="-f docker-compose.yml -f docker-compose.gpu.yml"
    PATH_LABEL="GPU NVIDIA (forzada)"
    ;;
  rocm)
    if ! has_amd_gpu; then
      say "${RED}Se pidió --rocm, pero el host no expone /dev/kfd + /dev/dri.${R}"
      say "ROCm sólo funciona en Linux con el driver amdgpu; en Windows/macOS no hay paso."
      say "Arranca sin la opción (o con --cpu) para usar la ruta portable."
      exit 1
    fi
    FILES="-f docker-compose.yml -f docker-compose.rocm.yml"
    PATH_LABEL="GPU AMD (forzada)"
    ;;
  auto)
    # NVIDIA first (works on every OS Docker runs on), then AMD (Linux only), then CPU.
    if has_gpu_runtime; then
      FILES="-f docker-compose.yml -f docker-compose.gpu.yml"
      PATH_LABEL="GPU NVIDIA"
    elif has_amd_gpu; then
      FILES="-f docker-compose.yml -f docker-compose.rocm.yml"
      PATH_LABEL="GPU AMD"
    fi
    ;;
esac

# Docker's MemTotal, not the host's: on Docker Desktop the VM's share is what binds.
mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
mem_gb=$(( mem_bytes / 1024 / 1024 / 1024 ))

model=$(grep -E '^LLM_MODEL=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)
[ -n "${model:-}" ] || model="qwen2.5:7b-instruct-q4_K_M"

say ""
say "  ${B}Motor de armonización multi-marco${R}"
say ""
say "  Docker         ${GREEN}ok${R}  Compose %s, %s GB de memoria" "$compose_version" "$mem_gb"
case "$PATH_LABEL" in
  "GPU NVIDIA"*)
    card=$(gpu_name)
    say "  Hardware       ${GREEN}ok${R}  %s" "${card:-tarjeta NVIDIA accesible desde Docker}"
    ;;
  "GPU AMD"*)
    say "  Hardware       ${GREEN}ok${R}  GPU AMD (ROCm) vía /dev/kfd"
    ;;
  *)
    # CPU. A card present but unused must not read as absent (--cpu would look broken);
    # and a card present but invisible to Docker must say *why*, or a one-command fix
    # reads as 'no hay GPU' and the operator waits minutes for nothing.
    if has_gpu_runtime; then
      card=$(gpu_name)
      say "  Hardware       %s ${DIM}(disponible, sin usar por elección)${R}" \
        "${card:-tarjeta NVIDIA}"
    elif has_amd_gpu; then
      say "  Hardware       GPU AMD ${DIM}(disponible, sin usar por elección)${R}"
    elif has_nvidia_host; then
      card=$(gpu_name)
      say "  ${YELLOW}Hardware${R}       %s detectada, pero Docker no la expone." "${card:-tarjeta NVIDIA}"
      say "                 Instala el NVIDIA Container Toolkit y reinicia Docker para"
      say "                 pasar de minutos a segundos por parseo:"
      say "                 ${DIM}https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html${R}"
    else
      say "  Hardware       sin GPU utilizable desde Docker (se usa CPU)"
    fi
    ;;
esac
say "  Ruta           ${B}%s${R}  %s" "$PATH_LABEL" "$FILES"
say "  Modelo         %s" "$model"

# On NVIDIA the weights live in VRAM, so the RAM Docker got is the wrong yardstick.
# (nvidia-smi cannot read an AMD card, so ROCm falls back to the RAM measure.)
case "$PATH_LABEL" in
  "GPU NVIDIA"*) have_gb=$(gpu_vram_gb); where="en la tarjeta" ;;
  *)             have_gb=$mem_gb;        where="disponibles para Docker" ;;
esac

# Recommend only: picking weights by machine size would break invariant 3.
case "$model" in
  *7b*)
    if [ "$have_gb" -gt 0 ] && [ "$have_gb" -le 6 ]; then
      say ""
      say "  ${YELLOW}Aviso${R}          el modelo fijado (7B) necesita ~6 GB residentes y hay"
      say "                 %s GB %s. El fallback documentado para máquinas" "$have_gb" "$where"
      say "                 pequeñas son estas dos líneas en el fichero .env:"
      say ""
      say "                   ${DIM}LLM_MODEL=qwen2.5:3b-instruct-q4_K_M${R}"
      say "                   ${DIM}LLM_MODEL_DIGEST=357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b${R}"
      say ""
      say "                 Se continúa con el 7B: unos pesos distintos dan un borrador"
      say "                 distinto, así que ese cambio lo decide una persona."
    fi
    ;;
esac

say ""
if [ -n "$BUILD" ]; then
  say "  Reconstruyendo las imágenes y arrancando cuatro contenedores..."
else
  say "  Arrancando cuatro contenedores..."
fi

# Let compose show its usual output — the pull, the layer bars, the per-service
# "Created/Started" lines. It is what the operator expects to see, and on a build
# it is the only place a compile error surfaces.
# shellcheck disable=SC2086 -- FILES and BUILD are deliberate flag lists.
if ! docker compose -p "$PROJECT" $FILES up -d $BUILD; then
  say ""
  say "  ${RED}El arranque ha fallado.${R}"
  exit 1
fi

started=$(date +%s)

health_of() {
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "${PROJECT}-$1" 2>/dev/null || echo missing
}

# `note` prints once, past `after` seconds, so a long first pull explains itself.
wait_healthy() {
  service=$1; after=${2:-0}; note=${3:-}
  noted=0
  while :; do
    status=$(health_of "$service")
    case "$status" in
      healthy) break ;;
      missing) say "    %-12s ${RED}no existe${R}" "$service"; return 1 ;;
    esac
    elapsed=$(( $(date +%s) - started ))
    if [ -n "$note" ] && [ "$noted" -eq 0 ] && [ "$elapsed" -ge "$after" ]; then
      say "    %-12s ${DIM}%s${R}" "$service" "$note"
      noted=1
    fi
    sleep 3
  done
  say "    %-12s ${GREEN}listo${R}   ${DIM}(%s s)${R}" "$service" "$(( $(date +%s) - started ))"
}

wait_healthy qdrant   || exit 1
wait_healthy backend  20 "arrancando (el primer arranque descarga ~1,1 GB de embeddings)" || exit 1
wait_healthy frontend || exit 1
wait_healthy ollama   20 "preparando el modelo (la primera vez descarga ~4,7 GB)" || exit 1

say ""
OLLAMA_URL="http://localhost:${OLLAMA_PORT:-11434}"
ps_json=$(curl -fsS "$OLLAMA_URL/api/ps" 2>/dev/null || true)

# `/api/ps` lists only loaded models, and OLLAMA_KEEP_ALIVE evicts them. Preload
# with an empty prompt (Ollama's documented no-op) so there is something to check
# and the operator's first read does not pay the ~185 s load.
case "$ps_json" in
  *'"models":[]'*|'')
    keep=$(grep -E '^OLLAMA_KEEP_ALIVE=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)
    [ -n "${keep:-}" ] || keep=30m
    say "  Precargando    llevando los pesos a memoria (segundos en GPU, ~3 min en CPU)..."
    curl -fsS -m 900 "$OLLAMA_URL/api/generate" \
      -d "{\"model\":\"${model}\",\"prompt\":\"\",\"keep_alive\":\"${keep}\"}" >/dev/null 2>&1 || true
    ps_json=$(curl -fsS "$OLLAMA_URL/api/ps" 2>/dev/null || true)
    ;;
esac

# Applying the overlay is not the same as the weights reaching the card.
if [ -n "$ps_json" ]; then
  size=$(printf '%s' "$ps_json"  | grep -o '"size":[0-9]*'      | head -1 | cut -d: -f2)
  vram=$(printf '%s' "$ps_json"  | grep -o '"size_vram":[0-9]*' | head -1 | cut -d: -f2)
  if [ -n "${size:-}" ] && [ -n "${vram:-}" ] && [ "$size" -gt 0 ]; then
    pct=$(( vram * 100 / size ))
    gb() { awk "BEGIN{printf \"%.2f\", $1/1073741824}"; }
    if [ "$pct" -ge 99 ]; then
      say "  Verificado     modelo residente en GPU: $(gb "$vram") GB de $(gb "$size") GB (%s %%)" "$pct"
    elif [ "$pct" -gt 0 ]; then
      say "  ${YELLOW}Verificado${R}     sólo el %s %% del modelo en GPU; el resto en CPU" "$pct"
    else
      say "  Verificado     modelo en CPU (size_vram = 0)"
      case "$PATH_LABEL" in
        GPU*)
          say "  ${YELLOW}Atención${R}       se pidió la ruta GPU y el modelo no ha entrado en la tarjeta."
          say "                 Míralo con 'docker compose logs ollama'. En NVIDIA suele ser un"
          say "                 driver del host más antiguo que el runtime CUDA; en AMD, una ISA"
          say "                 que ROCm no trae (prueba HSA_OVERRIDE_GFX_VERSION en el overlay)."
          ;;
      esac
    fi
  fi
fi

say ""
say "  ${B}Listo.${R}"
say "    Interfaz       http://localhost:${FRONTEND_PORT:-8080}"
say "    API y Swagger  http://localhost:${BACKEND_PORT:-8000}/docs"
say ""

# Named out loud so choosing the GPU stays a declared act, not a silent one.
case "$PATH_LABEL" in
  GPU*)
    say "  ${DIM}Nota: esta ejecución usa GPU. Las medidas de la evaluación se tomaron${R}"
    say "  ${DIM}en CPU y el borrador del parseo puede diferir; lo que viene después de${R}"
    say "  ${DIM}revisarlo es idéntico. Ruta reproducible:  ./scripts/start.sh --cpu${R}"
    say ""
    ;;
esac
