import json, threading, time, urllib.request, urllib.error, sys
import pytest
from pathlib import Path
from otv.painel import leitura
from otv.painel.fila import Fila
from otv.painel.servidor import servir


@pytest.fixture
def trab(tmp_path):
    d = tmp_path / "trabalho" / "vid1"
    (d / "thumbs").mkdir(parents=True)
    (d / "metadata.json").write_text(json.dumps({"id": "vid1", "titulo": "Aula X", "duracao_s": 600,
                                                 "fonte": "https://y/1", "criado_em": "2026-09-01T10:00:00"}))
    (d / "plan.json").write_text(json.dumps({"modo": "A", "alvo_s": 120, "total_s": 131.4, "manchete": "olha isso",
                                             "segmentos": [{"in": 1.0, "out": 9.5, "visual": "talking_head",
                                                            "texto": "oi", "motivo": "gancho"}]}))
    (d / "custos.json").write_text(json.dumps({"pontuar": {"provedor": "glm", "segundos": 8,
                                                           "uso": {"cost": 0.004}},
                                               "render_s": 12.0}))
    (d / "output.mp4").write_bytes(b"0123456789")
    (d / "thumbs" / "000.jpg").write_bytes(b"j")
    return d.parent


# ---- leitura ---------------------------------------------------------------
def test_resumo_le_plano_e_custo(trab):
    r = leitura.resumo(trab / "vid1")
    assert r["titulo"] == "Aula X" and r["tem_saida"] and r["usd"] == 0.004
    assert r["plano"]["segmentos"] == 1 and r["plano"]["manchete"] == "olha isso"
    assert r["thumb"] == "thumbs/000.jpg"

def test_custo_total_ignora_entrada_escalar(trab):
    # custos.json tem "render_s": 12.0 (escalar, formato legado) — não pode quebrar a soma
    assert leitura.custo_total(json.loads((trab / "vid1" / "custos.json").read_text())) == 0.004

def test_resumo_de_pasta_incompleta(tmp_path):
    d = tmp_path / "so-ingest"; d.mkdir()
    r = leitura.resumo(d)
    assert r["titulo"] == "so-ingest" and "plano" not in r and not r["tem_saida"]

def test_listar_ignora_pasta_interna(trab):
    (trab / ".painel").mkdir()
    assert [r["id"] for r in leitura.listar(trab)] == ["vid1"]


# ---- fila ------------------------------------------------------------------
def test_cmd_run_monta_lista_de_argumentos(trab):
    cmd = Fila(trab).cmd_run("https://y/1", "B", 90, visual="glm")
    assert cmd[-6:] == ["run", "https://y/1", "--modo", "B", "--alvo", "90.0"] or "--visual" in cmd
    assert all(isinstance(x, str) for x in cmd)

def test_fase_fora_da_lista_branca_e_recusada(trab):
    with pytest.raises(ValueError):
        Fila(trab).cmd_fase("rm -rf /", "vid1")

def test_modo_invalido_recusado(trab):
    with pytest.raises(ValueError):
        Fila(trab).cmd_run("x", "Z")

def test_job_roda_e_grava_log(trab):
    f = Fila(trab)
    j = f.enfileirar([sys.executable, "-c", "print('oi do job')"], "teste")
    for _ in range(100):
        if j.estado in ("ok", "erro"):
            break
        time.sleep(0.05)
    assert j.estado == "ok" and j.codigo == 0
    assert "oi do job" in j.texto_log()[0]
    assert json.loads((trab / ".painel" / "jobs.json").read_text())[0]["estado"] == "ok"

def test_job_que_falha_vira_erro(trab):
    f = Fila(trab)
    j = f.enfileirar([sys.executable, "-c", "raise SystemExit(3)"], "falha")
    for _ in range(100):
        if j.estado in ("ok", "erro"):
            break
        time.sleep(0.05)
    assert j.estado == "erro" and j.codigo == 3


# ---- servidor --------------------------------------------------------------
@pytest.fixture
def srv(trab, monkeypatch):
    monkeypatch.delenv("OTV_PAINEL_TOKEN", raising=False)
    cfg = {"trabalho": str(trab), "visual": "local", "pontuacao": "glm", "selecao": {"alvo_s": 120}}
    httpd = servir(cfg, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def pega(base, caminho, cabecalhos=None):
    req = urllib.request.Request(base + caminho, headers=cabecalhos or {})
    return urllib.request.urlopen(req, timeout=5)


def test_rodadas_json(srv):
    d = json.load(pega(srv, "/api/rodadas"))
    assert [r["id"] for r in d["rodadas"]] == ["vid1"] and d["cfg"]["alvo_s"] == 120

def test_pagina_serve_html(srv):
    assert b"<title>otv" in pega(srv, "/").read()

def test_detalhe_traz_segmentos(srv):
    d = json.load(pega(srv, "/api/rodada/vid1"))
    assert d["segmentos"][0]["dur"] == 8.5

def test_video_com_range(srv):
    r = pega(srv, "/video/vid1/output.mp4", {"Range": "bytes=2-5"})
    assert r.status == 206 and r.read() == b"2345"

def test_path_traversal_bloqueado(srv):
    for caminho in ("/api/rodada/..", "/video/..%2f..%2fetc/passwd", "/video/vid1/../../../etc/passwd"):
        with pytest.raises(urllib.error.HTTPError) as e:
            pega(srv, caminho)
        assert e.value.code in (400, 403, 404)

def test_rodar_sem_fonte_da_400(srv):
    req = urllib.request.Request(srv + "/api/rodar", data=b"{}",
                                 headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400

def test_token_bloqueia_quando_definido(trab, monkeypatch):
    monkeypatch.setenv("OTV_PAINEL_TOKEN", "segredo")
    cfg = {"trabalho": str(trab), "visual": "local", "pontuacao": "glm", "selecao": {"alvo_s": 120}}
    httpd = servir(cfg, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            pega(base, "/api/rodadas")
        assert e.value.code == 401
        assert json.load(pega(base, "/api/rodadas?t=segredo"))["rodadas"]
    finally:
        httpd.shutdown()


def test_cmd_run_com_substituir_vira_modo_a_mais(trab):
    cmd = Fila(trab).cmd_run("https://y/1", "A", visual="glm", substituir=True)
    assert cmd[-2:] == ["--substituir", "gerado"]

def test_sem_substituir_nao_manda_a_flag(trab):
    assert "--substituir" not in Fila(trab).cmd_run("https://y/1", "A")

def test_rota_rodar_repassa_substituir(srv, monkeypatch):
    """O checkbox A+ da tela tem que chegar no comando — sem enfileirar job de verdade."""
    from otv.painel.servidor import Handler
    capturado = {}

    class JobFalso:
        def dict(self):
            return {"job": "x", "estado": "na_fila"}

    def fake(cmd, rotulo, id_alvo=None):
        capturado["cmd"] = cmd
        return JobFalso()

    monkeypatch.setattr(Handler.painel.fila, "enfileirar", fake)
    corpo = json.dumps({"fonte": "https://y/1", "modo": "A", "visual": "glm",
                        "substituir": True}).encode()
    req = urllib.request.Request(srv + "/api/rodar", data=corpo,
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=5)
    assert capturado["cmd"][-2:] == ["--substituir", "gerado"]
    assert "--visual" in capturado["cmd"]


def test_rota_plano_edita_e_faz_backup(srv, trab):
    corpo = json.dumps({"id": "vid1", "manchete": "editada na tela",
                        "segmentos": [{"i": 0, "in": 2.0, "out": 8.0, "incluir": True}]}).encode()
    req = urllib.request.Request(srv + "/api/plano", data=corpo,
                                 headers={"Content-Type": "application/json"}, method="POST")
    r = json.load(urllib.request.urlopen(req, timeout=5))
    assert r["ok"] and r["segmentos"] == 1 and r["total_s"] == 6.0
    plano = json.loads((trab / "vid1" / "plan.json").read_text())
    assert plano["manchete"] == "editada na tela" and plano["segmentos"][0]["in"] == 2.0
    assert (trab / "vid1" / "plan.bak.json").exists()


def test_rota_plano_recusa_edicao_invalida(srv):
    corpo = json.dumps({"id": "vid1",
                        "segmentos": [{"i": 0, "in": 9.0, "out": 1.0, "incluir": True}]}).encode()
    req = urllib.request.Request(srv + "/api/plano", data=corpo,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400


def test_rota_plano_rodada_inexistente(srv):
    corpo = json.dumps({"id": "nao-existe", "manchete": "x"}).encode()
    req = urllib.request.Request(srv + "/api/plano", data=corpo,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 404
