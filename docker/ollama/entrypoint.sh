#!/bin/sh
# UCM-20 — start Ollama and guarantee the pinned model is on disk before the
# container reports healthy.
#
# The ~4.7 GB model is pulled at first start into the `ollama_models` volume and
# reused afterwards; baking it into the image is not an option (size), and
# letting the backend discover it is missing at request time is not one either.
# The readiness marker is what the compose healthcheck waits on, so dependent
# services never race the download — nor, now, the load into memory.
set -eu

MODEL="${LLM_MODEL:?LLM_MODEL must be set}"
KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}"
READY_MARKER=/tmp/model-ready

# A restarted container must not inherit the previous run's readiness.
rm -f "$READY_MARKER"

ollama serve &
serve_pid=$!

# `ollama pull` needs the daemon listening and the image has no built-in wait.
until ollama list >/dev/null 2>&1; do
  if ! kill -0 "$serve_pid" 2>/dev/null; then
    echo "ollama serve exited before becoming ready" >&2
    exit 1
  fi
  sleep 1
done

echo "==> pulling ${MODEL} (cached in the ollama_models volume after the first run)"
ollama pull "$MODEL"

# Put the digest of what was actually pulled on the record. The backend checks
# it against LLM_MODEL_DIGEST before its first parse (UCM-12): Ollama tags are
# mutable, so the tag on its own pins nothing.
echo "==> models available:"
ollama list

# Loading the weights costs ~185 s and was being paid by the operator's first
# request. An empty prompt is Ollama's documented preload: no token is decoded, so
# no output can depend on it. Never fatal — a slow first parse beats a dead container.
echo "==> preloading ${MODEL} into memory (keep_alive=${KEEP_ALIVE})"
if command -v curl >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:11434/api/generate \
    -d "{\"model\":\"${MODEL}\",\"prompt\":\"\",\"keep_alive\":\"${KEEP_ALIVE}\"}" >/dev/null \
    && echo "==> ${MODEL} resident" \
    || echo "==> preload failed; the first parse will pay the load" >&2
else
  ollama run "$MODEL" "" >/dev/null 2>&1 </dev/null \
    && echo "==> ${MODEL} resident" \
    || echo "==> preload failed; the first parse will pay the load" >&2
fi

touch "$READY_MARKER"
echo "==> ${MODEL} ready"

wait "$serve_pid"
