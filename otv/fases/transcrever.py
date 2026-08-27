import json, time
from pathlib import Path
from otv.provedores.transcricao import PROVEDORES
from otv.util.custos import registrar

def transcrever(dir, cfg, provedor=None, forcar=False):
    dir = Path(dir); out = dir / "transcript.json"
    if out.exists() and not forcar:
        return out
    prov = provedor or cfg["transcricao"]; t0 = time.time()
    t = PROVEDORES[prov](dir / "audio.opus", cfg)
    if len(t["palavras"]) < 50:
        raise RuntimeError(f"transcrição com só {len(t['palavras'])} palavras — vídeo sem fala? (só modo C faz sentido)")
    out.write_text(json.dumps(t, ensure_ascii=False))
    registrar(dir, "transcrever", {"provedor": prov, "palavras": len(t["palavras"]), "segundos": round(time.time() - t0, 1)})
    return out
