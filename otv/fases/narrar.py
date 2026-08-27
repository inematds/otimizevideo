import json, time
from pathlib import Path
from otv.provedores.llm import criar_llm
from otv.provedores.tts import tts
from otv.util.ffmpeg import run
from otv.util.custos import registrar

PPM = 2.5  # palavras por segundo (~150 ppm)

def duracao_wav(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).strip())

def ajustar_extensao(segmentos, duracoes, max_freeze=3.0):
    for s, d in zip(segmentos, duracoes):
        s["estender_s"] = round(min(max_freeze, max(0.0, d - (s["out"] - s["in"]))), 2)

def roteiro_por_segmento(segmentos, unidades, llm):
    por_id = {u["id"]: u for u in unidades}
    def ctx(s):
        ids = s["unidades"]; viz = [por_id[j]["texto"] for j in (ids[0] - 2, ids[0] - 1, ids[-1] + 1, ids[-1] + 2) if j in por_id]
        return " … ".join(viz)
    lista = "\n".join(f"[{k}] {s['out'] - s['in']:.1f}s | dito: \"{s['texto']}\" | contexto: \"{ctx(s)}\"" for k, s in enumerate(segmentos))
    tpl = (Path(__file__).resolve().parents[2] / "prompts/narrar.md").read_text()
    resp, uso = llm.chat_json(tpl.format(ppm=PPM, ex=int(PPM * 8), n=len(segmentos), lista=lista))
    textos = [""] * len(segmentos)
    for r in resp.get("narracao", []):
        k = int(r.get("k", -1))
        if 0 <= k < len(segmentos):
            textos[k] = str(r.get("texto", "")).strip()
    return textos, uso

def narrar(dir, cfg, provedor=None):
    dir = Path(dir); plan = json.loads((dir / "plan.json").read_text()); segs = plan["segmentos"]
    us = json.loads((dir / "unidades.json").read_text())["unidades"]
    llm = criar_llm(cfg, cfg["pontuacao"]); t0 = time.time()
    textos, uso = roteiro_por_segmento(segs, us, llm)
    (dir / "narracao").mkdir(exist_ok=True); arquivos = []; durs = []
    for k, (s, txt) in enumerate(zip(segs, textos)):
        wav = dir / "narracao" / f"seg_{k:02d}.wav"
        if txt:
            tts(txt, wav, cfg, provedor)
        else:  # silêncio do tamanho do segmento: um wav por segmento, sempre — nunca null
            # (o render monta as entradas do ffmpeg 1:1 por índice de segmento; pular um
            # segmento sem narração desalinharia todos os [k+1:a] seguintes silenciosamente)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{s['out'] - s['in']:.3f}", str(wav)])
        arquivos.append(f"narracao/seg_{k:02d}.wav"); durs.append(duracao_wav(wav))
    ajustar_extensao(segs, durs)
    plan["narracao"] = {"arquivos": arquivos, "provedor": provedor or cfg.get("tts", "inemavox"), "llm": llm.nome}
    (dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (dir / "roteiro.md").write_text("\n\n".join(f"## Segmento {k} ({s['in']:.1f}–{s['out']:.1f}s)\n\n{t}" for k, (s, t) in enumerate(zip(segs, textos))))
    registrar(dir, "narrar", {"llm": llm.nome, "uso": uso, "tts": plan["narracao"]["provedor"], "segundos": round(time.time() - t0, 1)})
    return dir / "plan.json"
