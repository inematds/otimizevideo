"""Leitura das rodadas em trabalho/ — sem lógica nova, só o que o CLI já lia.

Este módulo é a única fonte de verdade sobre "o que já rodou": tanto o `otv status`/
`otv custo` quanto o painel passam por aqui, pra não existirem duas versões que divergem.
Nada aqui escreve em disco nem chama modelo.
"""
import json
from pathlib import Path

ARTEFATOS = ["video.mp4", "audio.opus", "metadata.json", "transcript.json", "scenes.json",
             "unidades.json", "notas.json", "plan.json", "abertura.mp4", "output.mp4"]


def _json(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def custo_total(custos):
    """Soma o `uso.cost` de todas as fases. Ignora entrada malformada (custos.json legado)."""
    t = 0.0
    for v in (custos or {}).values():
        if isinstance(v, dict):
            t += (v.get("uso") or {}).get("cost") or 0
    return round(t, 4)


def fases_custo(custos):
    """[(fase, segundos, usd, provedor)] na ordem em que estão no arquivo."""
    saida = []
    for fase, v in (custos or {}).items():
        if not isinstance(v, dict):
            continue
        saida.append({"fase": fase, "segundos": v.get("segundos"),
                      "usd": (v.get("uso") or {}).get("cost") or 0,
                      "provedor": v.get("provedor") or v.get("llm") or ""})
    return saida


def resumo(dir):
    """Resumo de UMA rodada. Funciona em pasta incompleta (só ingest, sem plano)."""
    dir = Path(dir)
    meta, plan, custos = _json(dir / "metadata.json"), _json(dir / "plan.json"), _json(dir / "custos.json")
    thumbs = sorted((dir / "thumbs").glob("*.jpg")) if (dir / "thumbs").is_dir() else []
    r = {
        "id": dir.name,
        "titulo": meta.get("titulo") or dir.name,
        "fonte": meta.get("fonte", ""),
        "duracao_s": meta.get("duracao_s"),
        "criado_em": meta.get("criado_em"),
        "artefatos": {f: (dir / f).exists() for f in ARTEFATOS},
        "tem_saida": (dir / "output.mp4").exists(),
        "usd": custo_total(custos),
        "fases": fases_custo(custos),
        "thumb": f"thumbs/{thumbs[len(thumbs) // 2].name}" if thumbs else None,
    }
    if plan.get("segmentos") is not None:
        r["plano"] = {"modo": plan.get("modo"), "alvo_s": plan.get("alvo_s"),
                      "total_s": plan.get("total_s"), "manchete": plan.get("manchete"),
                      "segmentos": len(plan["segmentos"])}
    return r


def detalhe(dir):
    """resumo() + os segmentos do plano, pra tela de uma rodada só."""
    dir = Path(dir)
    r = resumo(dir)
    plan = _json(dir / "plan.json")
    r["segmentos"] = [
        {"in": s.get("in"), "out": s.get("out"), "dur": round((s.get("out") or 0) - (s.get("in") or 0), 1),
         "visual": s.get("visual"), "texto": s.get("texto", ""), "motivo": s.get("motivo", ""),
         "substituir": bool(s.get("substituir"))}
        for s in plan.get("segmentos", [])
    ]
    return r


def listar(raiz):
    """Todas as rodadas de trabalho/, mais recente primeiro. Ignora as internas (.painel)."""
    raiz = Path(raiz)
    if not raiz.is_dir():
        return []
    dirs = [d for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")]
    out = [resumo(d) for d in dirs]
    out.sort(key=lambda r: (r.get("criado_em") or "", r["id"]), reverse=True)
    return out
