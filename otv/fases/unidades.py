import json, re
from pathlib import Path
from otv.util.custos import registrar

def montar_unidades(palavras, fins_segmento, pausa_s=0.4, max_dur_s=12.0):
    fins = set(round(float(f), 3) for f in fins_segmento)
    brutas = []; cur = []
    def fechar(ate=None):
        if not cur:
            return
        segmento = cur[:ate] if ate is not None else cur[:]
        if segmento:
            brutas.append({"ini": segmento[0]["ini"], "fim": segmento[-1]["fim"],
                            "texto": " ".join(w["t"] for w in segmento)})
        if ate is None:
            cur.clear()
        else:
            del cur[:ate]
    for i, w in enumerate(palavras):
        cur.append(w)
        # corte forçado: assim que `cur` atinge o teto, corta na maior pausa
        # interna existente nele, mesmo que seja minúscula (spec §4.1.2) — ANTES
        # de checar fechamento natural (pontuação/pausa/fim de segmento), senão
        # um fechamento natural que coincida com o cruzamento do teto (ex.: um fim
        # de segmento bem na palavra que faz `cur` passar de 12 s) fecharia a
        # unidade já estourada. Um único corte pode não bastar (a maior pausa pode
        # estar perto do início de `cur`, deixando o resto ainda acima do teto) —
        # repete até o resto caber, ou sobrar só 1 palavra (sem pausa interna pra
        # cortar). `w` nunca é removido por esses cortes (o ponto de corte é
        # sempre um índice interno, antes do último elemento).
        while len(cur) >= 2 and (cur[-1]["fim"] - cur[0]["ini"]) >= max_dur_s:
            # candidatos: pontos de corte cujo primeiro pedaço (cur[:j+1]) fica
            # abaixo do teto — nunca deixamos a unidade fechada estourar. Entre
            # os que empatam na maior pausa (comum em fala corrida, onde muitos
            # gaps são 0), preferimos o ÚLTIMO (o que aproveita mais o teto) em
            # vez do primeiro — `max()` sozinho ia sempre para o primeiro empate
            # e cortava palavra a palavra desde o início de `cur`.
            cands = [j for j in range(len(cur) - 1) if cur[j]["fim"] - cur[0]["ini"] < max_dur_s] \
                    or list(range(len(cur) - 1))
            maior = max(cur[j + 1]["ini"] - cur[j]["fim"] for j in cands)
            k = max(j for j in cands if cur[j + 1]["ini"] - cur[j]["fim"] == maior)
            fechar(ate=k + 1)
        nxt = palavras[i + 1] if i + 1 < len(palavras) else None
        pausa = (nxt["ini"] - w["fim"]) if nxt else 99
        fim_frase = bool(re.search(r"[.!?]$", w["t"])) or round(w["fim"], 3) in fins
        if fim_frase or pausa >= pausa_s:
            fechar()
    fechar()
    unidades = []
    for u in brutas:
        curta = (u["fim"] - u["ini"]) < 0.8 or len(u["texto"].split()) < 3
        # A fusão de uma bruta curta na anterior (spec §4.1 item 3) NÃO pode
        # furar o teto que o corte forçado (item 2) acabou de garantir — senão
        # o item 3 desfaz a garantia do item 2. Divergência deliberada da spec
        # (que manda fundir sem condição): decisão do controlador é que o teto
        # vence, porque é o invariante que protege a mochila da Task 8 — uma
        # unidade curta solta é só estética, uma unidade gigante descarta
        # conteúdo bom de uma vez. Se fundir estourasse o teto, a bruta curta
        # fica como unidade própria em vez de fundir.
        caberia = unidades and (u["fim"] - unidades[-1]["ini"]) <= max_dur_s
        if unidades and curta and caberia:
            unidades[-1]["fim"] = u["fim"]; unidades[-1]["texto"] += " " + u["texto"]
        else:
            unidades.append(u)
    for k, u in enumerate(unidades):
        u["id"] = k; u["dur"] = round(u["fim"] - u["ini"], 2); u.setdefault("cena", None); u.setdefault("visual", "outro")
    return unidades

def atribuir_cenas(unidades, cenas):
    for u in unidades:
        meio = (u["ini"] + u["fim"]) / 2
        c = next((c for c in cenas if c["ini"] <= meio < c["fim"]), None)
        u["cena"] = c["id"] if c else None
        u["visual"] = c.get("visual", "outro") if c else "outro"
    return unidades

def unidades(dir, cfg, forcar=False):
    dir = Path(dir); out = dir / "unidades.json"
    if out.exists() and not forcar:
        return out
    t = json.loads((dir / "transcript.json").read_text())
    us = montar_unidades(t["palavras"], t.get("fins_segmento", []),
                         pausa_s=cfg["selecao"]["pausa_fronteira_ms"] / 1000,
                         max_dur_s=cfg["selecao"]["max_unidade_s"])
    sc = dir / "scenes.json"
    if sc.exists():
        atribuir_cenas(us, json.loads(sc.read_text())["cenas"])
    out.write_text(json.dumps({"unidades": us}, ensure_ascii=False))
    registrar(dir, "unidades", {"quantidade": len(us), "media_s": round(sum(u["dur"] for u in us) / max(1, len(us)), 2)})
    return out
