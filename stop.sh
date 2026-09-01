#!/usr/bin/env bash
# stop.sh — para o painel do otv.
#
#   ./stop.sh           # para o painel; recusa se houver job rodando
#   ./stop.sh --forcar  # para o painel E mata o job em andamento
#
# Sem --forcar, um job em andamento é preservado: ele é subprocesso do painel e continua
# vivo mesmo sem o painel, mas você perde a fila e o acompanhamento — melhor esperar.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ESTADO=trabalho/.painel
PID_FILE="$ESTADO/painel.pid"
FORCAR=0
[ "${1:-}" = "--forcar" ] && FORCAR=1

pid=""
[ -f "$PID_FILE" ] && pid=$(cat "$PID_FILE")
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  pid=$(pgrep -f "otv\.py painel" | head -1 || true)
fi
if [ -z "$pid" ]; then
  echo "o painel não está rodando."; rm -f "$PID_FILE"; exit 0
fi

# job em andamento? o filho é 'otv.py run|selecionar|render|...' pendurado no painel
jobs_vivos=$(pgrep -P "$pid" -f "otv\.py (run|selecionar|render|narrar|abertura|substituir|cenas|pontuar|transcrever|ingest)" || true)
if [ -n "$jobs_vivos" ] && [ "$FORCAR" = 0 ]; then
  echo "há job rodando (pid: $(echo "$jobs_vivos" | tr '\n' ' ')) — não parei nada."
  echo "espere terminar, ou use ./stop.sh --forcar para matar o job junto."
  exit 1
fi

if [ -n "$jobs_vivos" ]; then
  echo "matando job em andamento: $(echo "$jobs_vivos" | tr '\n' ' ')"
  kill $jobs_vivos 2>/dev/null || true
fi

kill "$pid" 2>/dev/null || true
for _ in $(seq 20); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.25
done
if kill -0 "$pid" 2>/dev/null; then
  echo "não saiu no TERM, mandando KILL"; kill -9 "$pid" 2>/dev/null || true
fi
rm -f "$PID_FILE"
echo "painel parado (pid $pid)."
