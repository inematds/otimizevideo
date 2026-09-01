"""Leitura de chaves de API em runtime.

Nenhuma key é gravada, logada ou impressa por este projeto — só devolvida a quem chamou.

Ordem de busca (a primeira fonte que tiver a variável vence):

1. variável de ambiente (`GROQ_API_KEY=... python3 otv.py ...`, systemd, Docker)
2. o arquivo apontado por `OTV_ENV_FILE`, se definido
3. `.env` na raiz do projeto
4. `~/.config/otv/.env`
5. os `.env` da máquina de origem (`~/projetos/openpcbotv2/.env`, `~/projetos/wifi/.env`)

Os dois últimos caminhos não existem numa VPS — por isso 1–4, que tornam o projeto portável
sem editar código.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

ARQUIVOS = [
    RAIZ / ".env",
    Path.home() / ".config/otv/.env",
    Path.home() / "projetos/openpcbotv2/.env",
    Path.home() / "projetos/wifi/.env",
]


def _arquivos():
    extra = os.environ.get("OTV_ENV_FILE")
    return ([Path(extra).expanduser()] if extra else []) + list(ARQUIVOS)


def _do_arquivo(f, nome):
    try:
        linhas = f.read_text().splitlines()
    except OSError:
        return None
    for ln in linhas:
        ln = ln.strip()
        if ln.startswith("export "):
            ln = ln[7:].lstrip()
        if not ln or ln.startswith("#") or not ln.startswith(nome + "="):
            continue
        return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def key(nome):
    do_ambiente = os.environ.get(nome)
    if do_ambiente and do_ambiente.strip():
        return do_ambiente.strip()
    for f in _arquivos():
        if not f.exists():
            continue
        v = _do_arquivo(f, nome)
        if v:
            return v
    raise KeyError(
        f"{nome} não encontrada. Defina a variável de ambiente {nome}, ou coloque "
        f"{nome}=... em um destes arquivos: " + ", ".join(str(a) for a in _arquivos())
    )
