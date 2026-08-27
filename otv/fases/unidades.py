import json, re, time
from pathlib import Path
from otv.util.custos import registrar

def montar_unidades(palavras, fins_segmento, pausa_s=0.4, max_dur_s=12.0):
    fins = set(round(float(f), 3) for f in fins_segmento)
    brutas = []; cur = []
    def fechar():
        if cur:
            brutas.append({"ini": cur[0]["ini"], "fim": cur[-1]["fim"], "texto": " ".join(w["t"] for w in cur)})
            cur.clear()
    for i, w in enumerate(palavras):
        cur.append(w)
        nxt = palavras[i + 1] if i + 1 < len(palavras) else None
        pausa = (nxt["ini"] - w["fim"]) if nxt else 99
        fim_frase = bool(re.search(r"[.!?]$", w["t"])) or round(w["fim"], 3) in fins
        longa = (w["fim"] - cur[0]["ini"]) >= max_dur_s
        if fim_frase or pausa >= pausa_s or (longa and pausa >= 0.15):
            fechar()
    fechar()
    unidades = []
    for u in brutas:
        curta = (u["fim"] - u["ini"]) < 0.8 or len(u["texto"].split()) < 3
        if unidades and curta:
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
                         pausa_s=cfg["selecao"]["pausa_fronteira_ms"] / 1000)
    sc = dir / "scenes.json"
    if sc.exists():
        atribuir_cenas(us, json.loads(sc.read_text())["cenas"])
    out.write_text(json.dumps({"unidades": us}, ensure_ascii=False))
    registrar(dir, "unidades", {"quantidade": len(us), "media_s": round(sum(u["dur"] for u in us) / max(1, len(us)), 2)})
    return out
