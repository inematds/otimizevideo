import json
from otv.fases.pontuar import montar_lista, montar_prompt, pontuar

U = [{"id": 0, "ini": 0, "fim": 6.2, "dur": 6.2, "texto": "abre aspas \"x\"", "visual": "slide"},
     {"id": 1, "ini": 6.2, "fim": 9.3, "dur": 3.1, "texto": "olha o gráfico", "visual": "grafico"}]

def test_montar_lista():
    assert montar_lista(U).splitlines()[1] == '[001] 3.1s grafico "olha o gráfico"'

def test_prompt_tem_modo_alvo_e_n():
    p = montar_prompt(U, "B", 90, "Título", 1200)
    assert "90 segundos" in p and "sem o apresentador" in p and "TODAS as 2 unidades" in p and "20 minutos" in p

def test_pontuar_escreve_notas_validadas(tmp_path, monkeypatch):
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": U}))
    (tmp_path / "metadata.json").write_text(json.dumps({"titulo": "T", "duracao_s": 600}))
    class Fake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            return {"topicos": [{"nome": "t", "de": 0, "ate": 1}], "gancho": [0], "notas": [{"id": 1, "nota": 9, "motivo": "m"}]}, {"cost": 0.001}
    import otv.fases.pontuar as P
    monkeypatch.setattr(P, "criar_llm", lambda cfg, slot: Fake())
    out = pontuar(tmp_path, {"pontuacao": "glm", "selecao": {"alvo_s": 120}}, modo="A")
    n = json.loads(out.read_text())
    assert [x["nota"] for x in n["notas"]] == [0, 9] and n["gancho"] == [0] and n["provedor"] == "fake"

def test_pontuar_grava_manchete_gancho_fecho(tmp_path, monkeypatch):
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": U}))
    (tmp_path / "metadata.json").write_text(json.dumps({"titulo": "T", "duracao_s": 600}))
    class Fake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            return {"manchete": "A grande tese do vídeo", "topicos": [{"nome": "t", "de": 0, "ate": 1}],
                    "gancho": [0], "fecho": [1], "notas": [{"id": 0, "nota": 5, "motivo": "m"},
                    {"id": 1, "nota": 9, "motivo": "m2"}]}, {"cost": 0.002}
    import otv.fases.pontuar as P
    monkeypatch.setattr(P, "criar_llm", lambda cfg, slot: Fake())
    out = pontuar(tmp_path, {"pontuacao": "glm", "selecao": {"alvo_s": 120}}, modo="A")
    n = json.loads(out.read_text())
    assert n["manchete"] == "A grande tese do vídeo"
    assert n["gancho"] == [0] and n["fecho"] == [1]
    assert n["uso"] == {"cost": 0.002} and n["modo"] == "A"

def test_pontuar_idempotente_sem_forcar(tmp_path, monkeypatch):
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": U}))
    (tmp_path / "metadata.json").write_text(json.dumps({"titulo": "T", "duracao_s": 600}))
    (tmp_path / "notas.json").write_text(json.dumps({"ja": "existe"}))
    def boom(cfg, slot):
        raise AssertionError("não deveria chamar criar_llm quando notas.json já existe")
    import otv.fases.pontuar as P
    monkeypatch.setattr(P, "criar_llm", boom)
    out = pontuar(tmp_path, {"pontuacao": "glm", "selecao": {"alvo_s": 120}}, modo="A")
    assert json.loads(out.read_text()) == {"ja": "existe"}


def test_pontuar_nao_reaproveita_notas_de_outro_modo(tmp_path, monkeypatch):
    # O prompt muda com o modo (MODOS[modo] entra no template) -- reaproveitar notas de
    # modo A num run de modo B validaria o modo B com julgamento do modo A.
    import json
    import otv.fases.pontuar as P
    (tmp_path / "notas.json").write_text(json.dumps({"notas": [{"id": 0, "nota": 5}], "modo": "A"}))
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": [{"id": 0, "ini": 0.0, "fim": 2.0, "dur": 2.0, "texto": "oi"}]}))
    (tmp_path / "metadata.json").write_text(json.dumps({"titulo": "t", "duracao_s": 100.0}))
    chamou = []

    class LLMFake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            chamou.append(prompt)
            return {"notas": [{"id": 0, "nota": 9}]}, {"cost": 0.0}

    monkeypatch.setattr(P, "criar_llm", lambda cfg, slot: LLMFake())
    cfg = {"pontuacao": "fake", "selecao": {"alvo_s": 120}}
    P.pontuar(tmp_path, cfg, modo="A")                    # mesmo modo: reaproveita
    assert chamou == []
    P.pontuar(tmp_path, cfg, modo="B")                    # modo diferente: re-pontua
    assert len(chamou) == 1
    assert json.loads((tmp_path / "notas.json").read_text())["modo"] == "B"
