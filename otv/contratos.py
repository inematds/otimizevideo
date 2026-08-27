def validar_notas(raw, n_unidades):
    if not isinstance(raw, dict) or not isinstance(raw.get("notas"), list) or not raw["notas"]:
        raise ValueError("notas.json sem lista 'notas'")
    por_id = {}
    for n in raw["notas"]:
        try:
            i = int(n["id"]); v = int(float(n["nota"]))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n_unidades:
            por_id[i] = {"id": i, "nota": max(0, min(10, v)), "motivo": str(n.get("motivo", ""))[:80]}
    notas = [por_id.get(i, {"id": i, "nota": 0, "motivo": "sem nota"}) for i in range(n_unidades)]
    topicos = []
    for t in raw.get("topicos") or []:
        try:
            de, ate = int(t["de"]), int(t["ate"])
        except (KeyError, TypeError, ValueError):
            continue
        de, ate = max(0, de), min(n_unidades - 1, ate)
        if de <= ate:
            topicos.append({"nome": str(t.get("nome", "?"))[:60], "de": de, "ate": ate})

    def _lista_ids(campo):
        return [int(g) for g in (raw.get(campo) or [])
                if str(g).lstrip("-").isdigit() and 0 <= int(g) < n_unidades][:2]

    gancho = _lista_ids("gancho")
    fecho = _lista_ids("fecho")
    manchete = str(raw.get("manchete", ""))[:80]
    return {"topicos": topicos, "notas": notas, "gancho": gancho, "fecho": fecho, "manchete": manchete}

def validar_plan(plan):
    if plan.get("modo") not in ("A", "B", "C"):
        raise ValueError("modo inválido")
    for s in plan.get("segmentos", []):
        if not (0 <= s["in"] < s["out"]):
            raise ValueError(f"segmento inválido: {s}")
        if not s.get("unidades"):
            raise ValueError(f"segmento sem unidades: {s}")
