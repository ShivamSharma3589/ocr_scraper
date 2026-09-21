#!/usr/bin/env bash
# Starts the user-local Ollama server (installed without sudo under ~/.local/ollama).
export PATH="$HOME/.local/ollama/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/.local/ollama/lib:$LD_LIBRARY_PATH"
export OLLAMA_HOST=127.0.0.1:11434

if curl -s http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "ollama already running"
else
    nohup ollama serve > "$HOME/.ollama/serve.log" 2>&1 &
    echo "ollama started"
fi
