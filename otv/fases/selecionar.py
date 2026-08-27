import json
from pathlib import Path
from otv.contratos import validar_plan
from otv.util.custos import registrar

# None = sem filtro de imagem (escolhe em todo o vídeo). O modo N narra por cima do
# conteúdo inteiro, então ele filtra tão pouco quanto o A — o que muda no N é o áudio,
# não a seleção.
VISUAL_MODO = {"A": None, "N": None, "B": {"demo_tela", "grafico", "slide"}, "C": {"demo_tela", "grafico"}}

def filtrar_modo(unidades, modo):
    permitidos = VISUAL_MODO[modo]
    return [u for u in unidades if permitidos is None or u.get("visual") in permitidos]

def _topicos(notas, n):
    t = {}
    for tp in notas.get("topicos", []):
        for i in range(tp["de"], tp["ate"] + 1):
            t[i] = tp["nome"]
    return {i: t.get(i, "?") for i in range(n)}

def mochila(cands, teto, cota, topico_de, ja=None, total=0.0, por_topico=None):
    """cands: unidades já ordenadas por prioridade. Retorna (ids, total, por_topico)."""
    esc = set(ja or []); por_topico = dict(por_topico or {})
    for u in cands:
        if u["id"] in esc:
            continue
        tp = topico_de.get(u["id"], "?")
        if total + u["dur"] > teto or por_topico.get(tp, 0) + u["dur"] > cota:
            continue
        esc.add(u["id"]); total += u["dur"]; por_topico[tp] = por_topico.get(tp, 0) + u["dur"]
    return esc, total, por_topico

def segmentar(ids, unidades):
    por_id = {u["id"]: u for u in unidades}; segs = []
    for i in sorted(ids):
        u = por_id[i]
        if segs and segs[-1]["unidades"][-1] == i - 1:
            segs[-1]["unidades"].append(i); segs[-1]["out"] = u["fim"]
        else:
            segs.append({"in": u["ini"], "out": u["fim"], "unidades": [i]})
    return segs

def snap(segs, unidades, cortes_cena, folga_s):
    por_id = {u["id"]: u for u in unidades}
    for s in segs:
        u0 = por_id[s["unidades"][0]]; u1 = por_id[s["unidades"][-1]]
        prev_fim = por_id[u0["id"] - 1]["fim"] if u0["id"] > 0 and (u0["id"] - 1) in por_id else 0.0
        pausa = max(0.0, u0["ini"] - prev_fim)
        ini = max(prev_fim, u0["ini"] - min(0.4, pausa / 2))
        perto = [c for c in cortes_cena if abs(c - ini) < 0.3 and c >= prev_fim]
        if perto:
            ini = min(perto, key=lambda c: abs(c - ini))
        nxt_ini = por_id[u1["id"] + 1]["ini"] if (u1["id"] + 1) in por_id else u1["fim"] + folga_s
        s["in"] = round(ini, 3); s["out"] = round(min(u1["fim"] + folga_s, nxt_ini), 3)
    return segs

def selecionar_plan(unidades, notas, cenas, sel, modo, alvo_s):
    nota = {x["id"]: x["nota"] for x in notas["notas"]}
    motivo = {x["id"]: x.get("motivo", "") for x in notas["notas"]}
    for u in unidades:
        u["nota"] = nota.get(u["id"], 0)
    topico_de = _topicos(notas, len(unidades))
    teto = alvo_s * (1 + sel["tolerancia"]); piso = alvo_s * (1 - sel["tolerancia"])
    cota = alvo_s * sel["cota_topico_pct"] / 100; nmin = sel["nota_minima"]
    elegiveis = filtrar_modo(unidades, modo)
    por_id = {u["id"]: u for u in unidades}; eleg_ids = {u["id"] for u in elegiveis}
    def _dur(ids): return sum(por_id[i]["dur"] for i in ids)
    # 1. âncoras: gancho (início) e fecho (fim), estendidas pros vizinhos até o mínimo
    def ancorar(ids):
        nonlocal esc, total
        ids = [i for i in ids if i in eleg_ids]
        for i in ids:
            esc.add(i); total += por_id[i]["dur"]
        bloco = sorted(ids)
        while bloco and _dur(bloco) < sel["min_segmento_s"]:
            viz = [j for j in (bloco[0] - 1, bloco[-1] + 1) if j in eleg_ids and j not in esc and por_id[j]["nota"] >= nmin - 3]
            if not viz:
                break
            j = max(viz, key=lambda j: por_id[j]["nota"]); esc.add(j); total += por_id[j]["dur"]; bloco = sorted(bloco + [j])
    esc, total, por_topico = set(), 0.0, {}
    ancorar(notas.get("gancho", [])); ancorar(notas.get("fecho", []))
    # 2. mochila por nota (desempate: mais curta) — âncoras ficam fora da cota por tópico.
    # Teto aqui é `alvo_s` puro (não `teto`, que já inclui a tolerância) — a folga de
    # tolerância fica reservada para coesão/sanduíche/completar (passos 3, 4 e 6), que
    # continuam podendo ir até `teto`. Ver Achado 2 da revisão da Task 8: com a mochila
    # saturando o `teto` cheio, a coesão nunca tinha orçamento sobrando para agir.
    cands = sorted([u for u in elegiveis if u["nota"] >= nmin], key=lambda u: (-u["nota"], u["dur"]))
    esc, total, por_topico = mochila(cands, alvo_s, cota, topico_de, esc, total, por_topico)
    # 3. coesão: estende cada segmento pros vizinhos razoáveis até min_segmento_ideal_s
    for s in segmentar(esc, unidades):
        ids = list(s["unidades"])
        while _dur(ids) < sel["min_segmento_ideal_s"]:
            viz = [j for j in (ids[0] - 1, ids[-1] + 1) if j in eleg_ids and j not in esc and por_id[j]["nota"] >= nmin - 2]
            viz = [j for j in viz if total + por_id[j]["dur"] <= teto]
            if not viz:
                break
            j = max(viz, key=lambda j: por_id[j]["nota"]); esc.add(j); total += por_id[j]["dur"]
            ids = sorted(ids + [j])
    # 4. vizinho sanduichado (id-1 e id+1 dentro) entra se razoável
    for u in elegiveis:
        i = u["id"]
        if i not in esc and (i - 1) in esc and (i + 1) in esc and u["nota"] >= nmin - 2 and total + u["dur"] <= teto:
            esc.add(i); total += u["dur"]
    # 5. segmentar + snap + mínimo (depois do snap)
    cortes = [c["ini"] for c in cenas]
    segs = snap(segmentar(esc, unidades), unidades, cortes, sel["folga_ms"] / 1000)
    segs = [s for s in segs if s["out"] - s["in"] >= sel["min_segmento_s"]]
    # 6. completar: se ficou abaixo do piso, repete a mochila só com vizinhos dos segmentos existentes
    esc = {i for s in segs for i in s["unidades"]}
    total = sum(s["out"] - s["in"] for s in segs)
    if total < piso:
        viz = sorted([por_id[j] for s in segs for j in (s["unidades"][0] - 1, s["unidades"][-1] + 1)
                      if j in eleg_ids and j not in esc and por_id[j]["nota"] >= nmin - 3], key=lambda u: -u["nota"])
        esc, total, _ = mochila(viz, teto, 1e9, topico_de, esc, total)
        segs = snap(segmentar(esc, unidades), unidades, cortes, sel["folga_ms"] / 1000)
        segs = [s for s in segs if s["out"] - s["in"] >= sel["min_segmento_s"]]
    for s in segs:
        s["visual"] = max((por_id[i].get("visual", "outro") for i in s["unidades"]), key=lambda v: 0 if v == "outro" else 1)
        s["motivo"] = "; ".join(dict.fromkeys(motivo[i] for i in s["unidades"] if motivo.get(i)))[:160]
        s["texto"] = " ".join(por_id[i]["texto"] for i in s["unidades"]); s["estender_s"] = 0
    plan = {"modo": modo, "alvo_s": alvo_s, "total_s": round(sum(s["out"] - s["in"] for s in segs), 1),
            "segmentos": segs, "narracao": None, "manchete": notas.get("manchete", "")}
    validar_plan(plan)
    return plan

def selecionar(dir, cfg, modo="A", alvo_s=None, forcar=True):
    dir = Path(dir); out = dir / "plan.json"
    if out.exists() and not forcar:
        return out
    us = json.loads((dir / "unidades.json").read_text())["unidades"]
    notas = json.loads((dir / "notas.json").read_text())
    cenas = json.loads((dir / "scenes.json").read_text())["cenas"] if (dir / "scenes.json").exists() else []
    alvo = alvo_s or cfg["selecao"]["alvo_s"]
    if VISUAL_MODO[modo] and not any(u.get("visual") in VISUAL_MODO[modo] for u in us):
        raise RuntimeError(f"nenhuma unidade com visual {sorted(VISUAL_MODO[modo])} — vídeo é só talking head? use modo A ou rode 'otv cenas --classificar'")
    plan = selecionar_plan(us, notas, cenas, cfg["selecao"], modo, alvo)
    if plan["total_s"] < 0.5 * alvo:
        print(f"aviso: só {plan['total_s']}s selecionados de {alvo}s — considere baixar selecao.nota_minima")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    registrar(dir, "selecionar", {"modo": modo, "alvo_s": alvo, "total_s": plan["total_s"], "segmentos": len(plan["segmentos"])})
    return out
