#!/usr/bin/env bash
# Installation Correcteur Auto (Debian / Ubuntu / XFCE — session X11)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
LOCAL_ROOT="${HOME}/.local"

echo "==> Correcteur Auto — installation"
echo "    Dossier : $ROOT"

echo "==> Paquets système"
if [[ -t 0 ]] && command -v sudo >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y \
    python3 python3-venv python3-pip python3-tk \
    python3-gi gir1.2-atspi-2.0 at-spi2-core \
    libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1 \
    curl zstd xclip || true
else
  echo "    (sudo non dispo — installe si besoin :)"
  echo "    sudo apt-get install -y python3-tk python3-gi gir1.2-atspi-2.0 \\"
  echo "      libayatana-appindicator3-1 curl zstd xclip"
fi

echo "==> Environnement Python"
python3 -m venv --system-site-packages "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r "$ROOT/requirements.txt"

echo "==> Ollama (IA locale, espace utilisateur)"
mkdir -p "$LOCAL_ROOT"
export PATH="$LOCAL_ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$LOCAL_ROOT/lib/ollama:${LD_LIBRARY_PATH:-}"

if [[ ! -x "$LOCAL_ROOT/bin/ollama" ]] && ! command -v ollama >/dev/null 2>&1; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
  esac
  TMP="$(mktemp -d)"
  echo "    Téléchargement Ollama…"
  curl -fL --progress-bar "https://ollama.com/download/ollama-linux-${ARCH}.tar.zst" \
    -o "$TMP/ollama.tar.zst"
  if tar --zstd -xf "$TMP/ollama.tar.zst" -C "$LOCAL_ROOT" 2>/dev/null; then
    :
  else
    zstd -dc "$TMP/ollama.tar.zst" | tar -xf - -C "$LOCAL_ROOT"
  fi
  rm -rf "$TMP"
fi

MARKER="# correcteur-auto ollama"
if ! grep -qF "$MARKER" "$HOME/.bashrc" 2>/dev/null; then
  cat >> "$HOME/.bashrc" <<EOF

$MARKER
export PATH="\$HOME/.local/bin:\$PATH"
export LD_LIBRARY_PATH="\$HOME/.local/lib/ollama:\${LD_LIBRARY_PATH:-}"
EOF
fi

OLLAMA_BIN="$(command -v ollama 2>/dev/null || echo "$LOCAL_ROOT/bin/ollama")"
if [[ -x "$OLLAMA_BIN" ]]; then
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    "$OLLAMA_BIN" serve >/tmp/ollama-correcteur.log 2>&1 &
    sleep 2
  fi
  echo "    Modèle qwen2.5:1.5b…"
  "$OLLAMA_BIN" pull qwen2.5:1.5b || echo "    Relance plus tard : ollama pull qwen2.5:1.5b"
fi

echo "==> Raccourci menu applications"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/correcteur-auto.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Correcteur Auto
Comment=Correction orthographe FR/EN (icône systray + Ollama)
Exec=$ROOT/run.sh
Icon=accessories-character-map
Terminal=false
Categories=Utility;Office;
StartupNotify=false
EOF

chmod +x "$ROOT/run.sh" "$ROOT/install.sh"
pkill -f "$ROOT/.venv/bin/python -m correcteur" 2>/dev/null || true

echo
echo "✓ Installation terminée"
echo "  Lance :  $ROOT/run.sh"
echo "  Guide :  $ROOT/docs/tutorial.png"
echo
