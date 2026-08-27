import json, os, shutil, subprocess

# --- teto de memória para o ffmpeg -----------------------------------------
# Em 2026-08-27 um render de um fonte de 20 min chegou a 60,9 GB de RSS e travou o host
# inteiro (a máquina não respondia mais; o kernel nem chegou a disparar o OOM killer).
# A causa foi corrigida em render.py (um input por segmento), mas um teto continua sendo
# o cinto de segurança: com ele, quem morre é o ffmpeg, nunca a máquina.
# Fail-open: se systemd-run não existir ou não funcionar aqui, roda direto, sem teto.
MEMMAX = os.environ.get("OTV_FFMPEG_MEMMAX", "16G")
_scope = None


def _prefixo_scope():
    """Prefixo systemd-run que põe o ffmpeg num scope com MemoryMax. [] se indisponível."""
    global _scope
    if _scope is None:
        _scope = []
        if MEMMAX.lower() not in ("", "0", "off", "none") and shutil.which("systemd-run"):
            teste = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                     "-p", f"MemoryMax={MEMMAX}", "-p", f"MemorySwapMax={MEMMAX}", "true"]
            try:
                if subprocess.run(teste, capture_output=True, timeout=15).returncode == 0:
                    _scope = teste[:-1]
            except (OSError, subprocess.SubprocessError):
                pass
    return _scope


def run(cmd):
    alvo = list(cmd)
    if alvo and alvo[0] in ("ffmpeg", "ffprobe"):
        alvo = _prefixo_scope() + alvo
    r = subprocess.run(alvo, capture_output=True, text=True)
    if r.returncode != 0:
        # 137 = SIGKILL: quase sempre o MemoryMax do scope batendo. Sem esta dica a
        # mensagem seria só "ffmpeg falhou:" com stderr vazio.
        dica = (f" (morto por SIGKILL — provavelmente o teto de memória OTV_FFMPEG_MEMMAX={MEMMAX};"
                f" suba o teto ou reduza o render)" if r.returncode == -9 or r.returncode == 137 else "")
        raise RuntimeError(f"{cmd[0]} falhou{dica}: {r.stderr[-800:]}")
    return r.stdout

def probe(video):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)])
    j = json.loads(out); s = j["streams"][0]; num, den = s["r_frame_rate"].split("/")
    return {"duracao_s": float(j["format"]["duration"]), "fps": round(int(num) / int(den), 3),
            "largura": s["width"], "altura": s["height"]}

def extrair_audio(video, out, kbps=32):
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-c:a", "libopus", "-b:a", f"{kbps}k", str(out)])

def thumb(video, t, out, largura=512):
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={largura}:-2", "-q:v", "3", str(out)])
