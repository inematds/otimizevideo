import json, subprocess
from pathlib import Path

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falhou: {r.stderr[-800:]}")
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
