#!/usr/bin/env bash
# v2.4 · Arranca todo con un solo comando: gateway del LLM (8001), backend (8000) e interfaz (5173).
# Uso, desde la carpeta del repositorio:   ./iniciar.sh        (Ctrl+C detiene los tres; el estado del agente queda en SQLite)
# Antes: entorno .venv creado, agente/.env con las claves y Ollama abierto (ver README → Ejecutarlo).
set -eo pipefail
cd "$(dirname "$0")"

[ -f .venv/bin/activate ] || { echo "Falta el entorno .venv (README → Ejecutarlo, paso 1)."; exit 1; }
[ -f agente/.env ] || { echo "Falta agente/.env: copia agente/.env.example y escribe las claves."; exit 1; }
source .venv/bin/activate
curl -s -m 3 http://127.0.0.1:11434/api/tags >/dev/null || echo "Aviso: Ollama no responde en el puerto 11434. Ábrelo antes del ciclo diario."
[ -d agente/frontend/node_modules ] || (cd agente/frontend && npm install)
mkdir -p agente/logs

pids=()
detener() { echo; echo "Deteniendo gateway, backend e interfaz…"; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; echo "Listo."; exit 0; }
trap detener INT TERM

(cd agente/backend && exec uvicorn gateway.main:app --host 127.0.0.1 --port 8001) > agente/logs/gateway.log 2>&1 & pids+=($!)
sleep 2
(cd agente/backend && exec uvicorn app.main:app --host 127.0.0.1 --port 8000) > agente/logs/backend.log 2>&1 & pids+=($!)
(cd agente/frontend && exec node node_modules/vite/bin/vite.js) > agente/logs/interfaz.log 2>&1 & pids+=($!)

echo "Laboratorio DL corriendo:"
echo "  Interfaz  http://127.0.0.1:5173"
echo "  Backend   http://127.0.0.1:8000  (documentación de la API en /docs)"
echo "  Gateway   http://127.0.0.1:8001"
echo "Registros en agente/logs/. Ctrl+C para detener todo."
wait
