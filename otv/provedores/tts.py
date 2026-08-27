import time, requests
from pathlib import Path
from otv.util.keys import key
from otv.util.ffmpeg import run

# Verificado em 2026-08-27 com o daemon de pé em :8010 (CUDA), chamada real ponta a ponta
# (ver task-10-report.md pro detalhe). CAMPO_ID="id" e "completed" em STATUS_OK bateram com
# o brief. UMA divergência: GET /api/jobs/{id}/download devolve 404 — quem entrega o áudio
# de verdade é GET /api/jobs/{id}/audio (200, audio/wav). Por isso ENDPOINT_AUDIO="audio",
# não "download".
INEMAVOX = "http://localhost:8010"; CAMPO_ID = "id"; STATUS_OK = {"completed", "done", "finished"}; STATUS_ERRO = {"failed", "error"}
ENDPOINT_AUDIO = "audio"
STATUS_EM_ANDAMENTO = {"queued", "running", "pending", "processing"}
# Achado 2 (rodada de correção 1): um status fora de STATUS_OK ∪ STATUS_ERRO ∪
# STATUS_EM_ANDAMENTO (ex.: "cancelled", "crashed", campo ausente) hoje só derruba no
# timeout de 600×2s (~20min) — desperdício operacional real, mesmo não sendo um hang
# infinito. Se o MESMO status desconhecido se repetir N_DESCONHECIDO vezes seguidas,
# desiste rápido com o status observado na mensagem.
N_DESCONHECIDO = 15  # ~30s (intervalo de poll de 2s) antes de desistir de um status não reconhecido

def tts_inemavox(texto, out, voz="rachel", engine="chatterbox"):
    r = requests.post(f"{INEMAVOX}/api/jobs/tts", json={"text": texto, "engine": engine, "voice": voz, "lang": "pt"}, timeout=60)
    r.raise_for_status(); jid = r.json()[CAMPO_ID]
    ultimo_desconhecido, repeticoes = None, 0
    for _ in range(600):
        j = requests.get(f"{INEMAVOX}/api/jobs/{jid}", timeout=30).json()
        st = str(j.get("status", "")).lower()
        if st in STATUS_OK:
            break
        if st in STATUS_ERRO:
            raise RuntimeError(f"inemavox falhou: {j.get('error') or j}")
        if st in STATUS_EM_ANDAMENTO:
            ultimo_desconhecido, repeticoes = None, 0
        else:
            repeticoes = repeticoes + 1 if st == ultimo_desconhecido else 1
            ultimo_desconhecido = st
            if repeticoes >= N_DESCONHECIDO:
                raise RuntimeError(f"inemavox: status desconhecido {st!r} repetido {repeticoes}x seguidas (job {jid}) — desistindo")
        time.sleep(2)
    else:
        raise RuntimeError("inemavox: timeout")
    a = requests.get(f"{INEMAVOX}/api/jobs/{jid}/{ENDPOINT_AUDIO}", timeout=120); a.raise_for_status()
    bruto = Path(out).with_suffix(".bin"); bruto.write_bytes(a.content)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(bruto), "-ar", "48000", "-ac", "1", str(out)]); bruto.unlink()
    return Path(out)

def tts_elevenlabs(texto, out, voz=None):
    vid = voz or key("ELEVENLABS_VOICE_ID")
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                      headers={"xi-api-key": key("ELEVENLABS_API_KEY")},
                      json={"text": texto, "model_id": "eleven_multilingual_v2"}, timeout=300)
    r.raise_for_status(); mp3 = Path(out).with_suffix(".mp3"); mp3.write_bytes(r.content)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(out)]); mp3.unlink()
    return Path(out)

def tts(texto, out, cfg, provedor=None):
    p = provedor or cfg.get("tts", "inemavox")
    return tts_elevenlabs(texto, out) if p == "elevenlabs" else tts_inemavox(texto, out)
