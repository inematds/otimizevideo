import subprocess, sys

def test_help_lista_subcomandos():
    r = subprocess.run([sys.executable, "otv.py", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    for c in ("run", "ingest", "transcrever", "cenas", "pontuar", "selecionar", "substituir", "render", "narrar", "status", "custo"):
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


def test_status_mostra_manchete_e_talking_head(tmp_path):
    # Adendo (Task 12a): o status tem que dizer a manchete e quais segmentos são
    # talking_head -- é por ele que se confere o modo A+ antes/depois do substituir.
    import json
    d = tmp_path / "vid"; d.mkdir()
    (d / "plan.json").write_text(json.dumps({
        "modo": "A", "alvo_s": 10, "total_s": 8.0, "manchete": "A tese central",
        "segmentos": [{"in": 0.0, "out": 4.0, "visual": "talking_head", "substituir": "subst/seg_00.png"},
                      {"in": 9.0, "out": 13.0, "visual": "talking_head"}]}))
    cfg = tmp_path / "c.yaml"; cfg.write_text(f"trabalho: {tmp_path}\n")
    r = subprocess.run([sys.executable, "otv.py", "--config", str(cfg), "status", "vid"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "manchete: A tese central" in out
    assert "talking_head: [0, 1] (1/2 substituídos)" in out
    assert "→img" in out
