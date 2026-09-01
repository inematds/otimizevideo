import json
import pytest
from otv.painel.plano import aplicar, salvar, Invalido

BASE = {"modo": "A", "alvo_s": 120, "total_s": 20.0, "manchete": "antiga",
        "segmentos": [
            {"in": 0.0, "out": 10.0, "unidades": [0, 1], "visual": "talking_head",
             "texto": "um", "substituir": "subst/seg_00.png"},
            {"in": 10.0, "out": 20.0, "unidades": [2], "visual": "outro", "texto": "dois"}]}


def test_remover_segmento_recalcula_total():
    n = aplicar(BASE, {"segmentos": [{"i": 0, "incluir": True}, {"i": 1, "incluir": False}]})
    assert len(n["segmentos"]) == 1 and n["total_s"] == 10.0


def test_editar_in_out_preserva_campos_do_pipeline():
    """A tela só manda in/out/incluir — unidades, visual e substituir não podem sumir."""
    n = aplicar(BASE, {"segmentos": [{"i": 0, "in": 2.0, "out": 8.0, "incluir": True}]})
    s = n["segmentos"][0]
    assert (s["in"], s["out"]) == (2.0, 8.0)
    assert s["unidades"] == [0, 1] and s["visual"] == "talking_head"
    assert s["substituir"] == "subst/seg_00.png"


def test_campo_desconhecido_e_ignorado():
    """Um POST não pode injetar chave nova nem sobrescrever o que o pipeline calculou."""
    n = aplicar(BASE, {"segmentos": [{"i": 0, "incluir": True, "visual": "grafico",
                                      "texto": "hackeado", "malicioso": 1}]})
    s = n["segmentos"][0]
    assert s["visual"] == "talking_head" and s["texto"] == "um" and "malicioso" not in s


def test_segmento_invertido_recusado():
    with pytest.raises(Invalido):
        aplicar(BASE, {"segmentos": [{"i": 0, "in": 9.0, "out": 1.0, "incluir": True}]})


def test_fim_depois_da_duracao_recusado():
    with pytest.raises(Invalido):
        aplicar(BASE, {"segmentos": [{"i": 0, "in": 0.0, "out": 900.0, "incluir": True}]}, duracao_s=60)


def test_indice_fora_do_plano_recusado():
    with pytest.raises(Invalido):
        aplicar(BASE, {"segmentos": [{"i": 99, "incluir": True}]})


def test_corte_vazio_recusado():
    with pytest.raises(Invalido):
        aplicar(BASE, {"segmentos": [{"i": 0, "incluir": False}, {"i": 1, "incluir": False}]})


def test_valor_nao_numerico_recusado():
    with pytest.raises(Invalido):
        aplicar(BASE, {"segmentos": [{"i": 0, "in": "abc", "out": 5, "incluir": True}]})


def test_manchete_vazia_vira_none():
    assert aplicar(BASE, {"manchete": "   "})["manchete"] is None
    assert aplicar(BASE, {"manchete": "nova"})["manchete"] == "nova"


def test_narracao_invalidada_quando_muda_a_contagem():
    com_narr = {**BASE, "narracao": {"arquivos": ["a.wav", "b.wav"]}}
    n = aplicar(com_narr, {"segmentos": [{"i": 0, "incluir": True}, {"i": 1, "incluir": False}]})
    assert n["narracao"] is None and n["narracao_invalidada"]
    # mexer só em in/out mantém o casamento wav<->segmento
    igual = aplicar(com_narr, {"segmentos": [{"i": 0, "in": 1.0, "out": 9.0, "incluir": True},
                                             {"i": 1, "incluir": True}]})
    assert igual["narracao"] is not None


def test_salvar_faz_backup_e_grava(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps(BASE))
    (tmp_path / "metadata.json").write_text(json.dumps({"duracao_s": 100}))
    novo, avisos = salvar(tmp_path, {"segmentos": [{"i": 1, "incluir": True}], "manchete": "x"})
    assert json.loads((tmp_path / "plan.bak.json").read_text())["total_s"] == 20.0
    assert json.loads((tmp_path / "plan.json").read_text())["total_s"] == 10.0
    assert novo["manchete"] == "x" and avisos == []


def test_salvar_sem_plano_recusa(tmp_path):
    with pytest.raises(Invalido):
        salvar(tmp_path, {"manchete": "x"})
