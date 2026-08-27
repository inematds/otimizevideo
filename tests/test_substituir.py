import json
import pytest
from otv.fases.substituir import substituir, montar_prompt


class GeradorFake:
    """Escreve um PNG sólido no destino e registra os prompts (nenhuma chamada paga)."""
    nome = "fake/flux"

    def __init__(self):
        self.prompts = []

    def gerar(self, prompt, destino):
        from otv.util.ffmpeg import run
        self.prompts.append(prompt)
        destino.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x36",
             "-frames:v", "1", str(destino)])
        return {"provedor": self.nome, "cost": 0.0}


def _pasta(tmp_path, segmentos, cenas=None, notas=None):
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "A", "alvo_s": 10, "total_s": 10.0,
                                                    "narracao": None, "segmentos": segmentos}))
    (tmp_path / "scenes.json").write_text(json.dumps({"cenas": cenas or []}))
    (tmp_path / "notas.json").write_text(json.dumps(notas or {}))
    return tmp_path


def test_montar_prompt_usa_a_fala_e_nao_a_descricao_do_apresentador():
    # a descrição da cena, num trecho talking_head, descreve o apresentador -- usá-la como
    # prompt gerava outro apresentador (falha real de 2026-08-27, primeira rodada da 10b)
    p = montar_prompt("ratos cegos voltaram a enxergar depois de três genes",
                      "envelhecimento", descricao="homem de terno falando para a câmera")
    assert p.startswith("ratos cegos voltaram a enxergar depois de três genes, envelhecimento")
    assert "homem de terno" not in p
    assert "no text" in p and "no person speaking to camera" in p


def test_montar_prompt_cai_na_descricao_so_sem_texto():
    assert montar_prompt("", "", descricao="gráfico de barras subindo").startswith("gráfico de barras subindo,")
    # campos vazios não deixam vírgula solta
    assert montar_prompt(None, "").startswith("editorial illustration")


def test_substituir_gera_so_os_talking_head_e_anota_no_plan(tmp_path):
    d = _pasta(tmp_path,
               [{"in": 0.0, "out": 4.0, "unidades": [0], "visual": "talking_head", "texto": "a fala do gancho"},
                {"in": 10.0, "out": 14.0, "unidades": [5], "visual": "grafico"},
                {"in": 20.0, "out": 24.0, "unidades": [9], "visual": "talking_head"}],
               cenas=[{"ini": 0.0, "fim": 30.0, "descricao": "apresentador no estúdio"}],
               notas={"topicos": [{"nome": "imortalidade", "de": 0, "ate": 9}]})
    g = GeradorFake()
    substituir(d, {}, gerador=g)
    plan = json.loads((d / "plan.json").read_text())
    assert plan["segmentos"][0]["substituir"] == "subst/seg_00.png"
    assert "substituir" not in plan["segmentos"][1]          # gráfico fica com o vídeo original
    assert plan["segmentos"][2]["substituir"] == "subst/seg_02.png"
    assert (d / "subst" / "seg_00.png").exists() and (d / "subst" / "seg_02.png").exists()
    assert len(g.prompts) == 2
    assert "a fala do gancho" in g.prompts[0] and "imortalidade" in g.prompts[0]
    assert "apresentador no estúdio" not in g.prompts[0]


def test_substituir_e_idempotente_nao_regera_png_existente(tmp_path):
    d = _pasta(tmp_path, [{"in": 0.0, "out": 4.0, "unidades": [0], "visual": "talking_head"}])
    g = GeradorFake()
    substituir(d, {}, gerador=g)
    substituir(d, {}, gerador=g)                              # segunda rodada: reaproveita
    assert len(g.prompts) == 1
    assert json.loads((d / "custos.json").read_text())["substituir"]["gerados"] == 0
    substituir(d, {}, gerador=g, forcar=True)                 # --forcar regera
    assert len(g.prompts) == 2


def test_substituir_sem_talking_head_falha_antes_de_gastar(tmp_path):
    # falha explícita em vez de gerar zero imagens e seguir em silêncio -- e antes de
    # instanciar qualquer provedor pago.
    d = _pasta(tmp_path, [{"in": 0.0, "out": 4.0, "unidades": [0], "visual": "grafico"}])
    with pytest.raises(RuntimeError, match="talking_head"):
        substituir(d, {}, gerador=GeradorFake())
