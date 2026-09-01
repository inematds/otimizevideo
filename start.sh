#!/usr/bin/env bash
# start.sh — sobe o painel do otv, destacado do terminal.
#
#   ./start.sh              # porta 8022, acessível na rede
#   ./start.sh 9000         # outra porta
#   ./start.sh --local      # só nesta máquina (127.0.0.1)
#   ./start.sh --token      # gera um token e exige ?t=… no acesso
#
# O painel roda com setsid: sobrevive ao fechar o terminal. Um job em andamento é
# subprocesso dele — por isso o stop.sh se recusa a matar o painel com job rodando.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PORTA=8022; HOST=0.0.0.0; USAR_TOKEN=0
for arg in "$@"; do
  case "$arg" in
    --local) HOST=127.0.0.1 ;;
    --token) USAR_TOKEN=1 ;;
    ''|*[!0-9]*) echo "argumento não reconhecido: $arg" >&2; exit 2 ;;
    *) PORTA="$arg" ;;
  esac
done

ESTADO=trabalho/.painel
PID_FILE="$ESTADO/painel.pid"
LOG="$ESTADO/servidor.log"
mkdir -p "$ESTADO"

# --- já está no ar? ---------------------------------------------------------
# Um painel por projeto, em qualquer porta: duas instâncias compartilhariam
# trabalho/.painel/ (pid, log e jobs.json) e a segunda sobrescreveria o histórico da
# primeira. Por isso a checagem é por processo, não por porta.
outro=$(pgrep -f "otv\.py painel" | head -1 || true)
if [ -n "$outro" ]; then
  # a porta vem do processo, não do log: o log pode ser de outra execução
  porta_atual=$(ss -ltnp 2>/dev/null | grep -oP "[0-9.]+:\K[0-9]+(?=.*pid=$outro,)" | head -1 || true)
  echo "painel já está rodando (pid $outro${porta_atual:+, porta $porta_atual})."
  echo "Use ./stop.sh antes de subir de novo."
  exit 0
fi
rm -f "$PID_FILE"

# --- pré-checagem: falhar aqui é mais barato que falhar no meio de um job ----
falta=0
for b in ffmpeg ffprobe; do
  command -v "$b" >/dev/null || { echo "FALTA: $b não está no PATH (corte e render dependem dele)"; falta=1; }
done
command -v yt-dlp >/dev/null || echo "aviso: yt-dlp ausente — só vai dar pra processar arquivo local, não URL"
python3 - <<'PY' || falta=1
import importlib.util as u, sys
faltando = [m for m in ("yaml", "requests", "scenedetect", "cv2", "mediapipe") if u.find_spec(m) is None]
if faltando:
    print("FALTA: módulos Python:", ", ".join(faltando), "— rode: pip install -r requirements.txt")
    sys.exit(1)
PY
python3 - <<'PY' || true
from otv.util.keys import key
for k, p in (("GROQ_API_KEY", "transcrição"), ("OPENROUTER_API_KEY", "pontuação")):
    try:
        key(k)
    except KeyError:
        print(f"aviso: {k} não encontrada — a fase de {p} vai falhar (ver README, seção 2)")
PY
[ "$falta" = 0 ] || { echo "não subi: resolva os itens FALTA acima."; exit 1; }

# --- porta livre? -----------------------------------------------------------
if command -v ss >/dev/null && ss -ltn "sport = :$PORTA" 2>/dev/null | grep -q LISTEN; then
  echo "porta $PORTA já está ocupada por outro processo. Use ./start.sh <outra-porta>."
  exit 1
fi

if [ "$USAR_TOKEN" = 1 ]; then
  OTV_PAINEL_TOKEN=$(python3 -c "import secrets;print(secrets.token_hex(16))")
  export OTV_PAINEL_TOKEN
  echo "$OTV_PAINEL_TOKEN" > "$ESTADO/token"
  chmod 600 "$ESTADO/token"
fi

setsid nohup python3 otv.py painel --porta "$PORTA" --host "$HOST" > "$LOG" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
sleep 2

if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "o painel morreu ao subir — log:"; tail -20 "$LOG"; rm -f "$PID_FILE"; exit 1
fi

cat "$LOG"
[ "$USAR_TOKEN" = 1 ] && echo "token:  ?t=$(cat "$ESTADO/token")   (guardado em $ESTADO/token)"
echo "pid $(cat "$PID_FILE")  ·  log: $LOG  ·  parar: ./stop.sh"
