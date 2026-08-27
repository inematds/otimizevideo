import json, time
from pathlib import Path

def registrar(dir, fase, dados):
    p = Path(dir) / "custos.json"
    atual = json.loads(p.read_text()) if p.exists() else {}
    atual[fase] = {**dados, "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p.write_text(json.dumps(atual, ensure_ascii=False, indent=1))
