#!/usr/bin/env bash
# bot.sh — a porta do inemaccbot para o otv.
#
#   bot.sh <url|caminho> [modo] [alvo_s]
#
# Contrato com o bot (skill `kind: function`): todo o progresso vai para o
# STDERR e a ÚLTIMA linha do STDOUT é só o caminho absoluto do MP4 final — o
# bot lê essa linha e entrega o arquivo. Nada de prosa no stdout.
#
# Por que existe: `otv run` imprime `[render] <path>` e depois o status do plano,
# e nenhuma dessas linhas é um caminho puro. Este script só traduz.
#
# O PATH ganha ~/.local/bin porque o serviço do bot roda sob systemd, que não o
# herda — e é lá que o `yt-dlp` do pip mora.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH"; export PATH ;; esac

FONTE="${1:-}"; MODO="${2:-A}"; ALVO="${3:-120}"
[ -n "$FONTE" ] || { echo "uso: bot.sh <url|caminho> [modo A|B|C|N] [alvo_s]" >&2; exit 2; }
MODO="$(echo "$MODO" | tr '[:lower:]' '[:upper:]')"
case "$MODO" in A|B|C|N) ;; *) echo "modo inválido: $MODO (use A, B, C ou N)" >&2; exit 2 ;; esac
case "$ALVO" in ''|*[!0-9.]*) echo "alvo inválido: $ALVO (segundos, ex.: 120)" >&2; exit 2 ;; esac

LOG="$(mktemp)"; trap 'rm -f "$LOG"' EXIT
# stdout do otv vai para o log E para o stderr: progresso visível, stdout limpo.
python3 otv.py run "$FONTE" --modo "$MODO" --alvo "$ALVO" 2>&1 | tee "$LOG" >&2

DIR="$(grep '^\[ingest\] ' "$LOG" | tail -1 | sed 's/^\[ingest\] //')"
[ -n "$DIR" ] && [ -d "$DIR" ] || { echo "otv terminou sem dizer a pasta de trabalho ([ingest])" >&2; exit 1; }

SAIDA="$(python3 - "$DIR" <<'PY'
import json, sys
from pathlib import Path
from otv.config import carregar_config
d = Path(sys.argv[1]); cfg = carregar_config()
try:
    vid = json.loads((d / "metadata.json").read_text()).get("id") or d.name
except Exception:
    vid = d.name
print(Path(cfg["saida"]).expanduser() / vid / "output.mp4")
PY
)"
[ -s "$SAIDA" ] || { echo "render terminou mas o MP4 não está em $SAIDA" >&2; exit 1; }
echo "$SAIDA"
