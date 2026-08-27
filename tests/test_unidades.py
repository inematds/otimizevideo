from otv.fases.unidades import montar_unidades, atribuir_cenas

def P(t, ini, fim): return {"t": t, "ini": ini, "fim": fim}

def test_quebra_em_pontuacao_e_pausa():
    pal = [P("Oi", 0, .3), P("tudo", .35, .6), P("bem.", .65, .9),                    # frase 1 (pontuação)
           P("Sim", 1.5, 1.8), P("claro", 1.85, 2.2), P("que", 2.25, 2.5), P("sim", 2.55, 2.9),  # frase 2 (pausa de 0.6 depois)
           P("vamos", 3.5, 3.8), P("lá", 3.85, 4.1), P("agora", 4.15, 4.5)]
    u = montar_unidades(pal, [], pausa_s=0.4)
    assert [x["texto"] for x in u] == ["Oi tudo bem.", "Sim claro que sim", "vamos lá agora"]
    assert u[0]["ini"] == 0 and u[0]["fim"] == .9 and u[0]["id"] == 0 and u[2]["id"] == 2

def test_funde_unidade_curta_na_anterior():
    pal = [P("Primeira", 0, .5), P("frase.", .55, 1.0), P("Ok.", 1.1, 1.3)]
    u = montar_unidades(pal, [])
    assert len(u) == 1 and u[0]["texto"] == "Primeira frase. Ok." and u[0]["fim"] == 1.3

def test_corta_unidade_longa_na_maior_pausa():
    pal = [P(f"p{i}", i * 1.0, i * 1.0 + 0.7) for i in range(15)]  # 15 s sem pontuação, pausas iguais de 0.3
    pal[7]["fim"] = 7.55                                              # pausa maior (0.45) depois de p7 — abaixo de 0.4? não: usa fim_segmento
    u = montar_unidades(pal, fins_segmento=[7.55], pausa_s=0.6)
    assert len(u) == 2 and u[0]["texto"].endswith("p7")

def test_atribuir_cenas():
    u = [{"id": 0, "ini": 0, "fim": 2, "dur": 2, "texto": "a"}, {"id": 1, "ini": 5, "fim": 7, "dur": 2, "texto": "b"}]
    cenas = [{"id": 0, "ini": 0, "fim": 4, "visual": "talking_head"}, {"id": 1, "ini": 4, "fim": 9, "visual": "slide"}]
    r = atribuir_cenas(u, cenas)
    assert [x["visual"] for x in r] == ["talking_head", "slide"] and r[1]["cena"] == 1
    assert atribuir_cenas(u, [])[0]["visual"] == "outro"
