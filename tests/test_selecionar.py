from otv.fases.selecionar import selecionar_plan, filtrar_modo, snap

SEL = {"alvo_s": 20, "tolerancia": 0.25, "min_segmento_s": 3, "min_segmento_ideal_s": 6,
       "folga_ms": 120, "cota_topico_pct": 60, "nota_minima": 5}

def U(i, ini, dur, visual="outro"):
    return {"id": i, "ini": ini, "fim": round(ini + dur, 3), "dur": dur, "texto": f"u{i}", "visual": visual, "cena": None}

def N(notas, topicos=None, gancho=None, fecho=None):
    return {"notas": [{"id": i, "nota": n, "motivo": ""} for i, n in enumerate(notas)],
            "topicos": topicos or [{"nome": "t", "de": 0, "ate": len(notas) - 1}], "gancho": gancho or [], "fecho": fecho or []}

def test_escolhe_por_nota_ate_o_teto_em_ordem_cronologica():
    us = [U(i, i * 5.0, 4.0) for i in range(8)]                 # 8 unidades de 4 s com pausa de 1 s
    plan = selecionar_plan(us, N([9, 2, 8, 2, 10, 2, 7, 2]), [], {**SEL, "tolerancia": 0.4}, "A", 20)
    ids = [i for s in plan["segmentos"] for i in s["unidades"]]
    assert ids == sorted(ids) and 4 in ids and 0 in ids and 1 not in ids
    assert plan["total_s"] <= 20 * 1.25

def test_cota_por_topico():
    us = [U(i, i * 5.0, 4.0) for i in range(8)]
    notas = N([10, 10, 10, 10, 6, 6, 6, 6], topicos=[{"nome": "a", "de": 0, "ate": 3}, {"nome": "b", "de": 4, "ate": 7}])
    plan = selecionar_plan(us, notas, [], {**SEL, "cota_topico_pct": 40}, "A", 20)   # cota = 8 s → no máx 2 unidades de 'a'
    ids = [i for s in plan["segmentos"] for i in s["unidades"]]
    assert len([i for i in ids if i <= 3]) <= 2 and any(i >= 4 for i in ids)

def test_coesao_estende_para_vizinho_razoavel_e_funde_contiguos():
    us = [U(i, i * 4.0, 3.9) for i in range(6)]                 # quase contíguas
    plan = selecionar_plan(us, N([9, 4, 9, 0, 0, 0]), [], {**SEL, "min_segmento_ideal_s": 8}, "A", 12)
    assert len(plan["segmentos"]) == 1 and plan["segmentos"][0]["unidades"] == [0, 1, 2]

def test_gancho_forcado_no_inicio():
    us = [U(i, i * 5.0, 4.0) for i in range(6)]
    plan = selecionar_plan(us, N([3, 3, 9, 9, 9, 9], gancho=[0]), [], SEL, "A", 12)
    assert plan["segmentos"][0]["unidades"][0] == 0

def test_fecho_forcado_e_estendido():
    us = [U(i, i * 3.0, 2.1) for i in range(8)]                 # unidades de 2.1 s (< mínimo 3 s)
    plan = selecionar_plan(us, N([9, 9, 9, 9, 9, 0, 6, 8], fecho=[7]), [], {**SEL, "alvo_s": 12}, "A", 12)
    ultimo = plan["segmentos"][-1]["unidades"]
    assert 7 in ultimo and 6 in ultimo                          # fecho puxou a vizinha 6 pra cumprir 3 s

def test_modo_B_descarta_talking_head():
    us = [U(0, 0, 5, "talking_head"), U(1, 6, 5, "demo_tela"), U(2, 12, 5, "grafico")]
    assert [u["id"] for u in filtrar_modo(us, "B")] == [1, 2]
    assert [u["id"] for u in filtrar_modo(us, "C")] == [1, 2]
    assert len(filtrar_modo(us, "A")) == 3

def test_min_segmento_aplicado_depois_do_snap():
    us = [U(0, 0, 4.0), U(1, 4.2, 2.9), U(2, 7.2, 4.0)]        # unidade 1 tem 2.9 s (< 3) mas snap dá folga
    plan = selecionar_plan(us, N([0, 9, 0]), [], SEL, "A", 5)
    assert plan["segmentos"] and plan["segmentos"][0]["unidades"] == [1]

def test_snap_recua_para_pausa_e_alinha_em_corte_de_cena():
    us = [U(0, 0, 4.0), U(1, 5.0, 4.0)]                          # pausa de 1 s entre elas
    segs = snap([{"in": 5.0, "out": 9.0, "unidades": [1]}], us, cortes_cena=[4.8], folga_s=0.12)
    assert segs[0]["in"] == 4.8                                  # corte de cena a < 0.3 s vence
    segs = snap([{"in": 5.0, "out": 9.0, "unidades": [1]}], us, cortes_cena=[], folga_s=0.12)
    assert segs[0]["in"] == 4.6 and segs[0]["out"] == 9.12       # recua até metade da pausa (máx 0.4)
