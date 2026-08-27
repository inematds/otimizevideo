import pytest
from otv.contratos import validar_notas, validar_plan

def test_validar_notas_limpa_ids_invalidos_e_completa_faltantes():
    raw = {"topicos": [{"nome": "a", "de": 0, "ate": 2}],
           "notas": [{"id": 0, "nota": 9, "motivo": "x"}, {"id": 7, "nota": 5}, {"id": "1", "nota": "11"}],
           "gancho": [0, 99]}
    n = validar_notas(raw, 3)
    assert {x["id"]: x["nota"] for x in n["notas"]} == {0: 9, 1: 10, 2: 0}
    assert n["gancho"] == [0]
    assert n["topicos"] == [{"nome": "a", "de": 0, "ate": 2}]

def test_validar_notas_sem_notas_falha():
    with pytest.raises(ValueError):
        validar_notas({"topicos": []}, 3)

def test_validar_notas_fecho_e_manchete():
    n = validar_notas({"notas": [{"id": 0, "nota": 1}], "fecho": [0, 5], "manchete": "IA contra o envelhecimento"}, 2)
    assert n["fecho"] == [0] and n["manchete"] == "IA contra o envelhecimento"

def test_validar_notas_gancho_e_fecho_limitam_em_dois_ids():
    raw = {"notas": [{"id": 0, "nota": 5}, {"id": 1, "nota": 5}, {"id": 2, "nota": 5}],
           "gancho": [0, 1, 2], "fecho": [2, 1, 0]}
    n = validar_notas(raw, 3)
    assert n["gancho"] == [0, 1]
    assert n["fecho"] == [2, 1]

def test_validar_notas_trunca_motivo_e_manchete_em_80_chars():
    motivo_longo = "m" * 100
    manchete_longa = "x" * 100
    raw = {"notas": [{"id": 0, "nota": 5, "motivo": motivo_longo}], "manchete": manchete_longa}
    n = validar_notas(raw, 1)
    assert n["notas"][0]["motivo"] == motivo_longo[:80]
    assert len(n["notas"][0]["motivo"]) == 80
    assert n["manchete"] == manchete_longa[:80]
    assert len(n["manchete"]) == 80

def test_validar_plan_ok_e_erro():
    validar_plan({"modo": "A", "alvo_s": 120, "total_s": 5.0,
                  "segmentos": [{"in": 1.0, "out": 6.0, "unidades": [0]}], "narracao": None})
    with pytest.raises(ValueError):
        validar_plan({"modo": "A", "segmentos": [{"in": 6.0, "out": 1.0, "unidades": [0]}]})

def test_validar_plan_modo_invalido():
    with pytest.raises(ValueError):
        validar_plan({"modo": "Z", "segmentos": []})

def test_validar_plan_segmento_sem_unidades():
    with pytest.raises(ValueError):
        validar_plan({"modo": "A", "segmentos": [{"in": 1.0, "out": 2.0, "unidades": []}]})
