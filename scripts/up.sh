#!/bin/sh
# UCM-20 - bring the runtime services up, adding the GPU overlay if Docker has one.
#
#   ./scripts/up.sh                      # detect, then `up -d`
#   ./scripts/up.sh --cpu                # force the portable path
#   ./scripts/up.sh --cpu logs -f ollama # anything after the flag goes to compose
#
# Never refuses to start: no GPU means the CPU stack. COMPOSE_FILE, if you set it,
# wins over detection.
set -eu

cd "$(dirname "$0")/.."

FORCE_CPU=0
if [ "${1:-}" = "--cpu" ]; then
  FORCE_CPU=1
  shift
fi

# Asking the daemon, not the host: a card Docker cannot reach is one the model
# cannot use. Covers WSL2, rootless and remote contexts alike.
has_gpu_runtime() {
  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
}

# -f flags, not COMPOSE_FILE: that variable splits on the platform's path separator
# (';' on Windows, ':' elsewhere).
if [ "$FORCE_CPU" -eq 1 ]; then
  echo "==> forced to CPU (--cpu): the portable path, the one reproducibility rests on"
  set -- -f docker-compose.yml "$@"
elif [ -n "${COMPOSE_FILE:-}" ]; then
  echo "==> COMPOSE_FILE is already set; leaving it alone: ${COMPOSE_FILE}"
elif has_gpu_runtime; then
  echo "==> Docker exposes the 'nvidia' runtime: adding docker-compose.gpu.yml"
  echo "    (check afterwards with: curl localhost:11434/api/ps - size_vram > 0)"
  set -- -f docker-compose.yml -f docker-compose.gpu.yml "$@"
else
  echo "==> no GPU reachable from Docker: starting on CPU, which works anywhere"
  echo "    (reading a description takes longer; nothing else changes)"
  set -- -f docker-compose.yml "$@"
fi

# `up -d` is the default verb, but it has to come *after* the -f flags.
case " $* " in
  *" up "*|*" down "*|*" logs "*|*" ps "*|*" config "*|*" restart "*|*" stop "*|*" pull "*)
    ;;
  *)
    set -- "$@" up -d
    ;;
esac

echo "==> docker compose $*"
exec docker compose "$@"
