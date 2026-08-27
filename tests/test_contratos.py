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

def test_validar_plan_ok_e_erro():
    validar_plan({"modo": "A", "alvo_s": 120, "total_s": 5.0,
                  "segmentos": [{"in": 1.0, "out": 6.0, "unidades": [0]}], "narracao": None})
    with pytest.raises(ValueError):
        validar_plan({"modo": "A", "segmentos": [{"in": 6.0, "out": 1.0, "unidades": [0]}]})
