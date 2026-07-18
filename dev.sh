#!/usr/bin/env bash
set -Eeuo pipefail

DAU_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAU_TOOLS_DIR="$DAU_ROOT/.tools"
DAU_CACHE_DIR="$DAU_ROOT/.cache"
DAU_API_LOG="$DAU_CACHE_DIR/api.log"
DAU_WEB_LOG="$DAU_CACHE_DIR/web.log"

export UV_CACHE_DIR="$DAU_CACHE_DIR/uv"
export UV_PYTHON_INSTALL_DIR="$DAU_TOOLS_DIR/python"
mkdir -p "$DAU_TOOLS_DIR" "$DAU_CACHE_DIR/numba" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR"

if command -v uv >/dev/null 2>&1; then
  DAU_UV="$(command -v uv)"
else
  if ! command -v curl >/dev/null 2>&1; then
    echo "Dấu needs either uv or curl to install its Python runtime." >&2
    exit 1
  fi

  echo "Installing uv into $DAU_TOOLS_DIR..."
  curl -LsSf https://astral.sh/uv/install.sh | env \
    UV_INSTALL_DIR="$DAU_TOOLS_DIR" \
    INSTALLER_NO_MODIFY_PATH=1 \
    sh
  DAU_UV="$DAU_TOOLS_DIR/uv"
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Dấu needs Node.js 22 or newer with npm." >&2
  exit 1
fi

DAU_NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( DAU_NODE_MAJOR < 22 )); then
  echo "Dấu needs Node.js 22 or newer. Found $(node --version)." >&2
  exit 1
fi

install_api() {
  "$DAU_UV" python install 3.11 --no-bin
  if [[ -f "$DAU_ROOT/api/uv.lock" ]]; then
    "$DAU_UV" sync --project "$DAU_ROOT/api" --python 3.11 --frozen
  else
    "$DAU_UV" sync --project "$DAU_ROOT/api" --python 3.11
  fi
}

install_web() {
  if [[ -f "$DAU_ROOT/web/package-lock.json" ]]; then
    npm --prefix "$DAU_ROOT/web" ci --no-audit --no-fund
  else
    npm --prefix "$DAU_ROOT/web" install --no-audit --no-fund
  fi
}

echo "Preparing Dấu dependencies..."
install_api &
DAU_API_INSTALL_PID=$!
install_web &
DAU_WEB_INSTALL_PID=$!

DAU_INSTALL_STATUS=0
wait "$DAU_API_INSTALL_PID" || DAU_INSTALL_STATUS=$?
wait "$DAU_WEB_INSTALL_PID" || DAU_INSTALL_STATUS=$?
if (( DAU_INSTALL_STATUS != 0 )); then
  echo "Dependency setup failed. Review the output above." >&2
  exit "$DAU_INSTALL_STATUS"
fi

DAU_PYTHON="$DAU_ROOT/api/.venv/bin/python"
DAU_UVICORN="$DAU_ROOT/api/.venv/bin/uvicorn"
DAU_VITE="$DAU_ROOT/web/node_modules/.bin/vite"
if [[ ! -x "$DAU_PYTHON" || ! -x "$DAU_UVICORN" || ! -x "$DAU_VITE" ]]; then
  echo "The local API or web runtime did not install correctly." >&2
  exit 1
fi

echo "Warming the local pYIN pitch tracker..."
NUMBA_CACHE_DIR="$DAU_CACHE_DIR/numba" "$DAU_PYTHON" \
  -c 'import numpy as np, librosa; sr=22050; t=np.arange(int(sr*0.35))/sr; y=(0.12*np.sin(2*np.pi*220*t)).astype(np.float32); librosa.pyin(y, fmin=65, fmax=650, sr=sr, frame_length=1024, hop_length=256)'

DAU_API_PID=""
DAU_WEB_PID=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "$DAU_API_PID" ]] && kill "$DAU_API_PID" 2>/dev/null || true
  [[ -n "$DAU_WEB_PID" ]] && kill "$DAU_WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

: > "$DAU_API_LOG"
: > "$DAU_WEB_LOG"

if [[ -f "$DAU_ROOT/.env.local" ]]; then
  NUMBA_CACHE_DIR="$DAU_CACHE_DIR/numba" "$DAU_UVICORN" dau.app:app \
    --app-dir "$DAU_ROOT/api" \
    --host 127.0.0.1 \
    --port 8000 \
    --env-file "$DAU_ROOT/.env.local" \
    >"$DAU_API_LOG" 2>&1 &
else
  NUMBA_CACHE_DIR="$DAU_CACHE_DIR/numba" "$DAU_UVICORN" dau.app:app \
    --app-dir "$DAU_ROOT/api" \
    --host 127.0.0.1 \
    --port 8000 \
    >"$DAU_API_LOG" 2>&1 &
fi
DAU_API_PID=$!

"$DAU_VITE" "$DAU_ROOT/web" \
  --host 127.0.0.1 \
  --port 5173 \
  --strictPort \
  >"$DAU_WEB_LOG" 2>&1 &
DAU_WEB_PID=$!

DAU_READY=0
for _ in $(seq 1 240); do
  if ! kill -0 "$DAU_API_PID" 2>/dev/null; then
    echo "The Dấu API stopped during startup:" >&2
    sed -n '1,160p' "$DAU_API_LOG" >&2
    exit 1
  fi
  if ! kill -0 "$DAU_WEB_PID" 2>/dev/null; then
    echo "The Dấu web app stopped during startup:" >&2
    sed -n '1,160p' "$DAU_WEB_LOG" >&2
    exit 1
  fi

  if curl -fsS http://127.0.0.1:8000/api/healthz >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1; then
    DAU_READY=1
    break
  fi
  sleep 0.5
done

if (( DAU_READY == 0 )); then
  echo "Dấu did not become ready within 120 seconds." >&2
  echo "API log:" >&2
  sed -n '1,160p' "$DAU_API_LOG" >&2
  echo "Web log:" >&2
  sed -n '1,160p' "$DAU_WEB_LOG" >&2
  exit 1
fi

echo "READY http://localhost:5173"
echo "API and web logs: $DAU_CACHE_DIR"

while kill -0 "$DAU_API_PID" 2>/dev/null && kill -0 "$DAU_WEB_PID" 2>/dev/null; do
  sleep 1
done

DAU_EXIT_STATUS=0
if ! kill -0 "$DAU_API_PID" 2>/dev/null; then
  wait "$DAU_API_PID" || DAU_EXIT_STATUS=$?
else
  wait "$DAU_WEB_PID" || DAU_EXIT_STATUS=$?
fi
exit "$DAU_EXIT_STATUS"
