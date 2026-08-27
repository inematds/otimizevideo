import json, re, time
from pathlib import Path
from otv.provedores.llm import criar_llm
from otv.provedores.tts import tts
from otv.util.fala import forma_fala
from otv.util.ffmpeg import run
from otv.util.custos import registrar

PPM = 2.5       # palavras por segundo (~150 ppm)
MAX_FREEZE = 3.0  # teto de freeze em segundos — mesmo valor usado por ajustar_extensao()
# No modo N a narração cobre o vídeo inteiro e é uma reescrita da MESMA fala, então ela
# tende a ficar mais longa que o trecho (português é mais prolixo que inglês). O usuário
# pediu explicitamente que o clipe pare e espere a fala terminar — por isso o teto de
# freeze é maior aqui: prefere-se congelar o quadro a truncar a frase.
MAX_FREEZE_N = 6.0
PROMPTS = {"N": "prompts/narrar_n.md"}   # os outros modos usam prompts/narrar.md

def duracao_wav(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).strip())

def ajustar_extensao(segmentos, duracoes, max_freeze=MAX_FREEZE):
    for s, d in zip(segmentos, duracoes):
        s["estender_s"] = round(min(max_freeze, max(0.0, d - (s["out"] - s["in"]))), 2)

def orcamento_palavras(duracao_s, max_freeze=MAX_FREEZE):
    """Teto de palavras que ainda cabe no segmento mesmo com o freeze máximo esticando
    o vídeo até o limite — é o mesmo teto que ajustar_extensao() aplica depois, calculado
    ANTES do TTS pra não pagar (nem truncar às cegas) áudio que nunca vai caber."""
    return int(round(PPM * (duracao_s + max_freeze)))

def truncar_por_orcamento(texto, orcamento):
    """Corta `texto` pra caber em `orcamento` palavras. Prioridade: última frase completa
    que couber; se nem a primeira frase couber, cai pra fronteira de palavra. Nunca corta
    no meio de uma palavra — é isso que faz a diferença entre um corte editorial (aceitável)
    e o áudio estourando o `atrim` do render.py no meio de uma sílaba (Achado 1)."""
    palavras = texto.split()
    if len(palavras) <= orcamento or orcamento <= 0:
        return texto if orcamento > 0 else ""
    sentencas = [p for p in re.split(r"(?<=[.!?])\s+", texto.strip()) if p]
    acc, usadas = [], 0
    for sent in sentencas:
        n = len(sent.split())
        if usadas + n > orcamento:
            break
        acc.append(sent); usadas += n
    if acc:
        return " ".join(acc)
    return " ".join(palavras[:orcamento])  # nem a 1ª frase coube: fronteira de palavra

def roteiro_por_segmento(segmentos, unidades, llm, modo="B", max_freeze=MAX_FREEZE):
    por_id = {u["id"]: u for u in unidades}
    def ctx(s):
        ids = s["unidades"]; viz = [por_id[j]["texto"] for j in (ids[0] - 2, ids[0] - 1, ids[-1] + 1, ids[-1] + 2) if j in por_id]
        return " … ".join(viz)
    lista = "\n".join(f"[{k}] {s['out'] - s['in']:.1f}s | dito: \"{s['texto']}\" | contexto: \"{ctx(s)}\"" for k, s in enumerate(segmentos))
    raiz = Path(__file__).resolve().parents[2]
    tpl = (raiz / PROMPTS.get(modo, "prompts/narrar.md")).read_text()
    resp, uso = llm.chat_json(tpl.format(ppm=PPM, ex=int(PPM * 8), n=len(segmentos), lista=lista))
    textos = [""] * len(segmentos)
    for r in resp.get("narracao", []):
        k = int(r.get("k", -1))
        if 0 <= k < len(segmentos):
            textos[k] = str(r.get("texto", "")).strip()
    # Achado 1 (rodada de correção 1): trunca ANTES do TTS no orçamento de palavras do
    # segmento (PPM × (duração + MAX_FREEZE)) — sem isso, um texto do LLM que estoura o
    # orçamento vira um wav mais longo que d+ext, e o atrim=0:{d+ext} de montar_filtro
    # corta o áudio sem fade, provavelmente no meio de uma palavra.
    for k, s in enumerate(segmentos):
        if textos[k]:
            textos[k] = truncar_por_orcamento(textos[k], orcamento_palavras(s["out"] - s["in"], max_freeze))
    return textos, uso

def narrar(dir, cfg, provedor=None):
    dir = Path(dir); plan = json.loads((dir / "plan.json").read_text()); segs = plan["segmentos"]
    us = json.loads((dir / "unidades.json").read_text())["unidades"]
    modo = plan.get("modo", "B")
    max_freeze = MAX_FREEZE_N if modo == "N" else float(cfg.get("max_freeze_s", MAX_FREEZE))
    llm = criar_llm(cfg, cfg["pontuacao"]); t0 = time.time()
    textos, uso = roteiro_por_segmento(segs, us, llm, modo, max_freeze)
    (dir / "narracao").mkdir(exist_ok=True); arquivos = []; durs = []
    for k, (s, txt) in enumerate(zip(segs, textos)):
        wav = dir / "narracao" / f"seg_{k:02d}.wav"
        if txt:
            # o roteiro.md guarda a forma de TELA (grafia original); só o TTS recebe a
            # forma-fala (termo em inglês foneticamente, sigla e URL expandidas). Sem isso
            # a rachel lê "AlphaFold"/"deploy" com fonemização portuguesa -- foi o que
            # aconteceu no primeiro dublado (2026-08-27).
            tts(forma_fala(txt), wav, cfg, provedor)
        else:  # silêncio do tamanho do segmento: um wav por segmento, sempre — nunca null
            # (o render monta as entradas do ffmpeg 1:1 por índice de segmento; pular um
            # segmento sem narração desalinharia todos os [k+1:a] seguintes silenciosamente)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{s['out'] - s['in']:.3f}", str(wav)])
        arquivos.append(f"narracao/seg_{k:02d}.wav"); durs.append(duracao_wav(wav))
    ajustar_extensao(segs, durs, max_freeze)
    plan["narracao"] = {"arquivos": arquivos, "provedor": provedor or cfg.get("tts", "inemavox"), "llm": llm.nome}
    (dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (dir / "roteiro.md").write_text("\n\n".join(f"## Segmento {k} ({s['in']:.1f}–{s['out']:.1f}s)\n\n{t}" for k, (s, t) in enumerate(zip(segs, textos))))
    registrar(dir, "narrar", {"llm": llm.nome, "uso": uso, "tts": plan["narracao"]["provedor"], "segundos": round(time.time() - t0, 1)})
    return dir / "plan.json"
