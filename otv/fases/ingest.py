import json, re, shutil, time
from pathlib import Path
from otv.util.ffmpeg import probe, extrair_audio, run
from otv.util.custos import registrar

def id_de(fonte):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", fonte)
    if m:
        return m.group(1)
    nome = Path(fonte).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", nome).strip("-")[:40]

def ingest(fonte, raiz, forcar=False):
    d = Path(raiz) / id_de(fonte); d.mkdir(parents=True, exist_ok=True)
    video = d / "video.mp4"; t0 = time.time()
    if not video.exists() or forcar:
        if fonte.startswith("http"):
            run(["yt-dlp", "-q", "--no-warnings", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]",
                 "--merge-output-format", "mp4", "-o", str(video), fonte])
        else:
            shutil.copy(fonte, video)
    if not (d / "audio.opus").exists() or forcar:
        extrair_audio(video, d / "audio.opus")
    titulo = Path(fonte).stem
    if fonte.startswith("http"):
        titulo = run(["yt-dlp", "--skip-download", "--print", "%(title)s", fonte]).strip() or titulo
    meta = {"id": d.name, "fonte": fonte, "titulo": titulo, **probe(video),
            "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (d / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    registrar(d, "ingest", {"segundos": round(time.time() - t0, 1)})
    return d
