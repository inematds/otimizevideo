from pathlib import Path
ARQUIVOS = [Path.home() / "projetos/openpcbotv2/.env", Path.home() / "projetos/wifi/.env"]

def key(nome):
    for f in ARQUIVOS:
        if not f.exists():
            continue
        for ln in f.read_text().splitlines():
            if ln.startswith(nome + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(f"{nome} não encontrada em {[str(a) for a in ARQUIVOS]}")
