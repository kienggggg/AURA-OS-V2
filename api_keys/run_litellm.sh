#!/usr/bin/env bash
# Khởi động LiteLLM proxy cho AURA tại http://localhost:4000
cd "$(dirname "$0")/.." || exit 1
set -a
[ -f litellm/keys.env ] && . litellm/keys.env
set +a
echo "Khởi động LiteLLM proxy: http://localhost:4000 (Ctrl+C để dừng)"
exec venv/Scripts/litellm.exe --config litellm/config.yaml --port 4000
