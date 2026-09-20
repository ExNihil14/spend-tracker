#!/usr/bin/env sh
# Spendtrack — одна команда установки (macOS/Linux/WSL).
#   sh install.sh                       # из git-репозитория
#   sh install.sh ./dist/spendtrack-0.1.0-py3-none-any.whl
#   sh install.sh --no-serve            # только установить
set -eu

SOURCE="git+https://github.com/ExNihil14/spend-tracker"
SERVE=1
for arg in "$@"; do
  case "$arg" in
    --no-serve) SERVE=0 ;;
    *) SOURCE="$arg" ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  echo "uv не найден — ставлю официальным установщиком astral.sh ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv установлен, но не виден в PATH — откройте новый терминал и повторите" >&2
    exit 1
  fi
fi

echo "Устанавливаю spendtrack из $SOURCE ..."
uv tool install --force "$SOURCE"
PATH="$HOME/.local/bin:$PATH"
export PATH

if [ "$SERVE" -eq 0 ]; then
  echo "Готово. Запуск: spendtrack serve --open"
  exit 0
fi

if command -v spendtrack >/dev/null 2>&1; then
  exec spendtrack serve --open
fi
echo "Готово. Запуск: spendtrack serve --open"
