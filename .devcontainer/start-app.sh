#!/usr/bin/env bash
# Идемпотентный старт spendtrack для Codespaces (вызывается из postStart/postAttach).
# Всё пишет в /tmp/spendtrack.log; повторный вызов не поднимает второй сервер.
set -u
cd "$(dirname "$0")/.." || exit 0
UV="${HOME}/.local/bin/uv"
LOG=/tmp/spendtrack.log
ts() { date -Is; }

echo "[$(ts)] start-app: begin" >> "$LOG"
if curl -sf --max-time 2 http://localhost:8766/health >/dev/null 2>&1; then
  echo "[$(ts)] already running - skip" >> "$LOG"
  exit 0
fi
if [ ! -x "$UV" ]; then
  echo "[$(ts)] ERROR: uv not found at $UV" >> "$LOG"
  exit 1
fi
"$UV" sync >> "$LOG" 2>&1 || echo "[$(ts)] WARN: uv sync failed (пробуем запуститься)" >> "$LOG"
setsid nohup "$UV" run uvicorn spendtrack.main:app --host 0.0.0.0 --port 8766 >> "$LOG" 2>&1 < /dev/null &
echo "[$(ts)] uvicorn started (log: $LOG)" >> "$LOG"
