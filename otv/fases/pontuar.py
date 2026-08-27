import json, time
from pathlib import Path
from otv.provedores.llm import criar_llm
from otv.contratos import validar_notas
from otv.util.custos import registrar

MODOS = {"A": "condensado com a fala original: priorize o que se entende só ouvindo.",
         "B": "sem o apresentador: a narração será refeita; priorize unidades cujo tipo de imagem é demo_tela, grafico ou slide, pois é a imagem que vai ficar.",
         "C": "só demonstrações e gráficos: priorize demo_tela e grafico."}

def montar_lista(unidades):
    return "\n".join(f"[{u['id']:03d}] {u['dur']:.1f}s {u.get('visual', 'outro')} \"{u['texto']}\"" for u in unidades)

def montar_prompt(unidades, modo, alvo_s, titulo, duracao_s):
    tpl = (Path(__file__).resolve().parents[2] / "prompts/pontuar.md").read_text()
    return tpl.format(minutos=round(duracao_s / 60), titulo=titulo, alvo=int(alvo_s), modo_desc=MODOS[modo],
                      n=len(unidades), lista=montar_lista(unidades))

def pontuar(dir, cfg, modo="A", alvo_s=None, provedor=None, forcar=False):
    dir = Path(dir); out = dir / "notas.json"
    if out.exists() and not forcar:
        return out
    us = json.loads((dir / "unidades.json").read_text())["unidades"]
    meta = json.loads((dir / "metadata.json").read_text())
    llm = criar_llm(cfg, provedor or cfg["pontuacao"]); t0 = time.time()
    raw, uso = llm.chat_json(montar_prompt(us, modo, alvo_s or cfg["selecao"]["alvo_s"], meta["titulo"], meta["duracao_s"]))
    notas = validar_notas(raw, len(us))
    notas["provedor"] = llm.nome; notas["uso"] = uso; notas["modo"] = modo
    out.write_text(json.dumps(notas, ensure_ascii=False, indent=0))
    registrar(dir, "pontuar", {"provedor": llm.nome, "uso": uso, "segundos": round(time.time() - t0, 1)})
    return out
