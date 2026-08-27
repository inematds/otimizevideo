#!/usr/bin/env python3
"""otv — condensa vídeos longos em ~2 min. Fases com JSON entre elas; provedores em config.yaml."""
import argparse, json, sys
from pathlib import Path
from otv.config import carregar_config
from otv.fases import ingest as F_ing, transcrever as F_tr, unidades as F_un, cenas as F_ce, pontuar as F_po, selecionar as F_se, render as F_re, narrar as F_na

ARTEFATOS = ["video.mp4", "audio.opus", "metadata.json", "transcript.json", "scenes.json", "unidades.json", "notas.json", "plan.json", "output.mp4"]

def pasta(cfg, id_):
    d = Path(cfg["trabalho"]) / id_
    if not d.exists():
        sys.exit(f"pasta de trabalho não encontrada: {d}")
    return d

def cmd_run(a, cfg):
    d = F_ing.ingest(a.fonte, cfg["trabalho"], forcar=a.forcar); print(f"[ingest] {d}")
    F_tr.transcrever(d, cfg, a.transcricao, forcar=a.forcar); print("[transcrever] ok")
    F_ce.cenas(d, cfg, forcar=a.forcar); print("[cenas] ok")
    visual = a.visual or cfg["visual"]
    # CORREÇÃO 1: "local" não é slot de modelo (criar_llm levanta ValueError pra ele) —
    # só chama classificar() quando `visual` for um slot de modelo de verdade. Com
    # visual=local e modo B/C, não dá pra classificar; avisa e segue — a guarda de
    # selecionar() (VISUAL_MODO) levanta um erro útil se faltar unidade com o visual certo.
    if visual == "local":
        if a.modo != "A":
            print(f"[classificar] aviso: visual=local não classifica por modelo — modo {a.modo} "
                  "precisa de classificação visual (--visual glm, --visual gemini ou --visual claude_cli). "
                  "Seguindo sem classificar; 'selecionar' falha com uma mensagem clara se faltar unidade do visual certo.")
    else:
        F_ce.classificar(d, cfg, visual, forcar=a.forcar); print("[classificar] ok")
    F_un.unidades(d, cfg, forcar=True); print("[unidades] ok")
    F_po.pontuar(d, cfg, a.modo, a.alvo, a.pontuacao, forcar=a.forcar); print("[pontuar] ok")
    F_se.selecionar(d, cfg, a.modo, a.alvo); print("[selecionar] ok")
    if a.modo == "B":
        F_na.narrar(d, cfg, a.tts); print("[narrar] ok")
    out = F_re.render(d, cfg, rapido=a.rapido, sem_audio_original=a.sem_audio_original); print(f"[render] {out}")
    cmd_status(a, cfg, d)

def cmd_status(a, cfg, d=None):
    d = d or pasta(cfg, a.id)
    for f in ARTEFATOS:
        print(f"  {'✔' if (d / f).exists() else '·'} {f}")
    if (d / "plan.json").exists():
        p = json.loads((d / "plan.json").read_text())
        print(f"  plan: modo {p['modo']} · {p['total_s']}s em {len(p['segmentos'])} segmentos (alvo {p['alvo_s']}s)")
        for s in p["segmentos"]:
            print(f"    {s['in']:7.1f}–{s['out']:7.1f} ({s['out'] - s['in']:4.1f}s) {s.get('visual', '?'):12s} {s.get('texto', '')[:70]}")

def cmd_custo(a, cfg):
    d = pasta(cfg, a.id); c = json.loads((d / "custos.json").read_text()) if (d / "custos.json").exists() else {}
    total = 0.0
    for fase, v in c.items():
        if not isinstance(v, dict):  # custos.json legado/malformado (chave -> escalar): pula em vez de quebrar
            continue
        usd = (v.get("uso") or {}).get("cost") or 0; total += usd
        print(f"  {fase:12s} {v.get('segundos', '-'):>7} s  US${usd:.4f}  {v.get('provedor', v.get('llm', ''))}")
    print(f"  total US${total:.4f} (transcrição Groq não reporta custo: ~US$0,04/h)")

def main():
    p = argparse.ArgumentParser(prog="otv", description=__doc__)
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="pipeline completo"); r.add_argument("fonte")
    for s_ in (r,):
        s_.add_argument("--modo", choices="ABC", default="A"); s_.add_argument("--alvo", type=float, default=None)
        s_.add_argument("--transcricao"); s_.add_argument("--visual"); s_.add_argument("--pontuacao"); s_.add_argument("--tts")
        s_.add_argument("--rapido", action="store_true"); s_.add_argument("--sem-audio-original", action="store_true")
        s_.add_argument("--forcar", action="store_true")
    i = sub.add_parser("ingest"); i.add_argument("fonte"); i.add_argument("--forcar", action="store_true")
    for nome in ("transcrever", "cenas", "pontuar", "selecionar", "render", "narrar", "status", "custo"):
        sp = sub.add_parser(nome); sp.add_argument("id")
        sp.add_argument("--provedor"); sp.add_argument("--forcar", action="store_true")
        if nome == "cenas": sp.add_argument("--classificar", action="store_true")
        if nome in ("pontuar", "selecionar"): sp.add_argument("--modo", choices="ABC", default="A"); sp.add_argument("--alvo", type=float)
        if nome == "render": sp.add_argument("--rapido", action="store_true"); sp.add_argument("--sem-audio-original", action="store_true")
    a = p.parse_args(); cfg = carregar_config(a.config)
    if a.cmd == "run": return cmd_run(a, cfg)
    if a.cmd == "ingest": return print(F_ing.ingest(a.fonte, cfg["trabalho"], forcar=a.forcar))
    if a.cmd == "status": return cmd_status(a, cfg)
    if a.cmd == "custo": return cmd_custo(a, cfg)
    d = pasta(cfg, a.id)
    if a.cmd == "transcrever": print(F_tr.transcrever(d, cfg, a.provedor, forcar=a.forcar))
    elif a.cmd == "cenas":
        print(F_ce.cenas(d, cfg, forcar=a.forcar))
        if a.classificar: print(F_ce.classificar(d, cfg, a.provedor, forcar=a.forcar))
        F_un.unidades(d, cfg, forcar=True)
    elif a.cmd == "pontuar": F_un.unidades(d, cfg, forcar=False); print(F_po.pontuar(d, cfg, a.modo, a.alvo, a.provedor, forcar=a.forcar))
    elif a.cmd == "selecionar": print(F_se.selecionar(d, cfg, a.modo, a.alvo)); cmd_status(a, cfg, d)
    elif a.cmd == "render": print(F_re.render(d, cfg, rapido=a.rapido, sem_audio_original=a.sem_audio_original))
    elif a.cmd == "narrar": print(F_na.narrar(d, cfg, a.provedor))

if __name__ == "__main__":
    main()
