"""Modo A+ (`--substituir gerado`, Task 10b): troca os trechos de apresentador por
ilustração gerada, mantendo o áudio original.

Só o VÍDEO é substituído — `[0:a]atrim` continua vindo do arquivo original, então a
fala segue exatamente a mesma. A fase só marca `segmento["substituir"]` no plan.json;
quem monta o filtro é o render.
"""
import json, time
from pathlib import Path
from otv.provedores.imagem import criar_imagem
from otv.util.custos import registrar

# "no text/no words/no letters": o flux escreve letreiro garrancho se deixar. "no person
# speaking to camera": a primeira rodada (2026-08-27) montava o prompt a partir da DESCRIÇÃO
# da cena -- que descreve justamente o apresentador -- e gerava outro apresentador, ou seja,
# substituía talking head por talking head. O assunto tem que vir do que está sendo DITO.
# Negação não funciona: "no people" no prompt positivo do flux é ignorado -- ele desenhava um
# rosto sempre que a fala citava alguém (Bezos, Altman, "o cientista"), e a substituição só
# trocava um rosto por outro. O que funciona é dizer o que DEVE aparecer, então o prompt vira
# uma diretiva de natureza-morta conceitual, com o assunto entrando como TEMA e não como cena.
PREFIXO_PROMPT = ("Conceptual editorial illustration, dark cinematic still life. "
                  "Depict only objects, environments and abstract forms — laboratory glassware, "
                  "molecular structures, machinery, instruments, landscapes, geometry. "
                  "Empty of any person. Theme: ")
SUFIXO_PROMPT = "Moody low-key lighting, muted palette, unlettered, no signage."
MAX_TEXTO = 240


def _cena_de(cenas, t):
    for c in cenas:
        if c["ini"] <= t <= c["fim"]:
            return c
    return None


def _topico_de(notas, unidades_ids):
    for tp in (notas.get("topicos") or []):
        if any(tp["de"] <= i <= tp["ate"] for i in unidades_ids):
            return tp.get("nome", "")
    return ""


def montar_prompt(texto, topico, descricao=None):
    """Prompt da ilustração: o ASSUNTO vem da fala do segmento (`texto`) e do tópico.

    A `descricao` da cena entra só como último recurso (segmento sem texto): num trecho
    talking_head ela descreve o apresentador, e usar isso como prompt gera outro
    apresentador -- exatamente o que o modo A+ existe para eliminar.
    """
    assunto = (texto or "").strip()[:MAX_TEXTO] or (descricao or "").strip()
    tema = ". ".join(p for p in (assunto, (topico or "").strip()) if p)
    return f"{PREFIXO_PROMPT}{tema}. {SUFIXO_PROMPT}"


def substituir(dir, cfg, provedor=None, gerador=None, forcar=False):
    """Gera subst/seg_NN.png para cada segmento talking_head e anota no plan.json.

    Idempotente: um PNG já existente é reaproveitado sem nova chamada paga (a menos de
    `forcar`), no mesmo espírito das outras fases.
    """
    dir = Path(dir); plan = json.loads((dir / "plan.json").read_text())
    cenas = (json.loads((dir / "scenes.json").read_text()) if (dir / "scenes.json").exists() else {}).get("cenas", [])
    notas = json.loads((dir / "notas.json").read_text()) if (dir / "notas.json").exists() else {}
    alvos = [k for k, s in enumerate(plan["segmentos"]) if s.get("visual") == "talking_head"]
    if not alvos:
        raise RuntimeError("nenhum segmento com visual 'talking_head' no plan.json — "
                           "nada a substituir (rode 'otv cenas --classificar' se o visual não foi classificado)")
    gerador = gerador or criar_imagem(cfg, provedor)
    t0 = time.time(); gerados = 0
    for k in alvos:
        s = plan["segmentos"][k]
        rel = f"subst/seg_{k:02d}.png"; png = dir / rel
        if forcar or not png.exists():
            cena = _cena_de(cenas, (s["in"] + s["out"]) / 2) or {}
            gerador.gerar(montar_prompt(s.get("texto"), _topico_de(notas, s.get("unidades", [])),
                                        cena.get("descricao")), png)
            gerados += 1
        s["substituir"] = rel
    (dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    registrar(dir, "substituir", {"segundos": round(time.time() - t0, 1), "provedor": getattr(gerador, "nome", "?"),
                                  "segmentos": len(alvos), "gerados": gerados})
    return dir / "plan.json"
