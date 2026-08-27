import json, os, re, shutil, time
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
        tmp_video = d / "video.part.mp4"
        if fonte.startswith("http"):
            run(["yt-dlp", "-q", "--no-warnings", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]",
                 "--merge-output-format", "mp4", "-o", str(tmp_video), fonte])
        else:
            shutil.copy(fonte, tmp_video)
        os.replace(tmp_video, video)
    audio = d / "audio.opus"
    if not audio.exists() or forcar:
        tmp_audio = d / "audio.part.opus"
        extrair_audio(video, tmp_audio)
        os.replace(tmp_audio, audio)
    meta_path = d / "metadata.json"
    if meta_path.exists() and not forcar:
        titulo = json.loads(meta_path.read_text()).get("titulo") or Path(fonte).stem
    else:
        titulo = Path(fonte).stem
        if fonte.startswith("http"):
            try:
                titulo = run(["yt-dlp", "--skip-download", "--print", "%(title)s", fonte]).strip() or titulo
            except RuntimeError:
                pass
    meta = {"id": d.name, "fonte": fonte, "titulo": titulo, **probe(video),
            "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    registrar(d, "ingest", {"segundos": round(time.time() - t0, 1)})
    return d
