#!/usr/bin/env bash
# Lance Correcteur Auto (une seule instance)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
export PATH="${HOME}/.local/bin:${PATH}"
export LD_LIBRARY_PATH="${HOME}/.local/lib/ollama:${LD_LIBRARY_PATH:-}"

RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
unset AT_SPI_BUS_ADDRESS
if [[ -S "$RUNTIME/at-spi/bus_0" ]]; then
  export AT_SPI_BUS_ADDRESS="unix:path=$RUNTIME/at-spi/bus_0"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Environnement manquant. Lance d'abord : ./install.sh" >&2
  exit 1
fi

mapfile -t OLD < <(pgrep -f "$ROOT/.venv/bin/python -m correcteur" || true)
if ((${#OLD[@]})); then
  echo "Correcteur Auto tourne déjà (PID: ${OLD[*]})."
  exit 0
fi

OLLAMA_BIN="$(command -v ollama 2>/dev/null || true)"
if [[ -n "$OLLAMA_BIN" ]]; then
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    "$OLLAMA_BIN" serve >/tmp/ollama-correcteur.log 2>&1 &
    sleep 1
  fi
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
exec "$VENV/bin/python" -m correcteur
