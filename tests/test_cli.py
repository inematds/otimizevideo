import subprocess, sys

def test_help_lista_subcomandos():
    r = subprocess.run([sys.executable, "otv.py", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    for c in ("run", "ingest", "transcrever", "cenas", "pontuar", "selecionar", "render", "narrar", "status", "custo"):
        assert c in r.stdout

def test_status_pasta_inexistente():
    r = subprocess.run([sys.executable, "otv.py", "status", "nao-existe"], capture_output=True, text=True)
    assert r.returncode != 0 and "não encontrada" in (r.stdout + r.stderr)
