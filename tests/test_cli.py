import subprocess, sys

def test_help_lista_subcomandos():
    r = subprocess.run([sys.executable, "otv.py", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    for c in ("run", "ingest", "transcrever", "cenas", "pontuar", "selecionar", "render", "narrar", "status", "custo"):
        assert c in r.stdout

def test_status_pasta_inexistente():
    r = subprocess.run([sys.executable, "otv.py", "status", "nao-existe"], capture_output=True, text=True)
    assert r.returncode != 0 and "não encontrada" in (r.stdout + r.stderr)

def test_run_modo_b_com_visual_local_falha_antes_de_gastar():
    # config.yaml default (visual: local) + modo B sem --visual explícito: precisa falhar
    # ANTES de qualquer I/O (ingest/transcrever/pontuar) — nada de rede ou custo aqui, então
    # roda offline e rápido, igual aos outros testes de CLI deste arquivo.
    r = subprocess.run([sys.executable, "otv.py", "run", "fonte-qualquer", "--modo", "B"], capture_output=True, text=True)
    assert r.returncode != 0
    saida = r.stdout + r.stderr
    assert "classificação visual" in saida
    assert "[ingest]" not in saida  # confirma que não chegou a rodar nenhuma fase
