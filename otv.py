#!/usr/bin/env python3
"""otv — condensa vídeos longos em ~2 min. Fases com JSON entre elas; provedores em config.yaml."""
import argparse, json, sys
from pathlib import Path
from otv.config import carregar_config
from otv.fases import ingest as F_ing, transcrever as F_tr, unidades as F_un, cenas as F_ce, pontuar as F_po, selecionar as F_se, render as F_re, narrar as F_na, substituir as F_su, abertura as F_ab

ARTEFATOS = ["video.mp4", "audio.opus", "metadata.json", "transcript.json", "scenes.json", "unidades.json", "notas.json", "plan.json", "abertura.mp4", "output.mp4"]

def pasta(cfg, id_):
    d = Path(cfg["trabalho"]) / id_
    if not d.exists():
        sys.exit(f"pasta de trabalho não encontrada: {d}")
    return d

def cmd_run(a, cfg):
    visual = a.visual or cfg["visual"]
    visual_e_modelo = visual in cfg["modelos"]
    # CORREÇÃO 1+2 (rodada 1 de revisão): "local" (ou qualquer valor fora de cfg["modelos"])
    # não é slot de modelo — criar_llm() levanta ValueError pra ele. Modo B/C sem
    # classificação visual por modelo nunca vai ter unidade elegível (a guarda de
    # selecionar()/VISUAL_MODO garante isso), então falha AQUI, antes de qualquer I/O ou
    # chamada paga (ingest baixa vídeo, transcrever custa Groq, pontuar custa LLM) — não
    # depois de já ter gasto tudo isso pra travar só no 'selecionar'. A condição não faz
    # I/O nenhum: só olha a.modo e o slot resolvido.
    # o modo N narra por cima do vídeo inteiro: não filtra por tipo de imagem, então não
    # depende de classificação visual (igual ao A). Só B e C dependem.
    if a.modo in ("B", "C") and not visual_e_modelo:
        sys.exit(f"modo {a.modo} precisa de classificação visual por modelo — visual={visual!r} "
                  "não é um slot de modelo (use --visual glm, --visual gemini ou --visual claude_cli)")
    d = F_ing.ingest(a.fonte, cfg["trabalho"], forcar=a.forcar); print(f"[ingest] {d}")
    F_tr.transcrever(d, cfg, a.transcricao, forcar=a.forcar); print("[transcrever] ok")
    F_ce.cenas(d, cfg, forcar=a.forcar); print("[cenas] ok")
    if visual_e_modelo:
        F_ce.classificar(d, cfg, visual, forcar=a.forcar); print("[classificar] ok")
    F_un.unidades(d, cfg, forcar=True); print("[unidades] ok")
    F_po.pontuar(d, cfg, a.modo, a.alvo, a.pontuacao, forcar=a.forcar); print("[pontuar] ok")
    F_se.selecionar(d, cfg, a.modo, a.alvo); print("[selecionar] ok")
    if a.substituir == "gerado":
        F_su.substituir(d, cfg, a.imagem, forcar=a.forcar); print("[substituir] ok")
    if a.modo in ("B", "N"):
        F_na.narrar(d, cfg, a.tts); print("[narrar] ok")
    if a.abertura:
        F_ab.abertura(d, cfg, forcar=a.forcar); print("[abertura] ok")
    out = F_re.render(d, cfg, rapido=a.rapido, sem_audio_original=False if a.com_cama else None); print(f"[render] {out}")
    cmd_status(a, cfg, d)

def cmd_status(a, cfg, d=None):
    d = d or pasta(cfg, a.id)
    for f in ARTEFATOS:
        print(f"  {'✔' if (d / f).exists() else '·'} {f}")
    if (d / "plan.json").exists():
        p = json.loads((d / "plan.json").read_text())
        print(f"  plan: modo {p['modo']} · {p['total_s']}s em {len(p['segmentos'])} segmentos (alvo {p['alvo_s']}s)")
        if p.get("manchete"):
            print(f"  manchete: {p['manchete']}")
        for s in p["segmentos"]:
            # marca o que o modo A+ já trocou por ilustração (Adendo, Task 12a)
            marca = "→img " if s.get("substituir") else ""
            print(f"    {s['in']:7.1f}–{s['out']:7.1f} ({s['out'] - s['in']:4.1f}s) {s.get('visual', '?'):12s} {marca}{s.get('texto', '')[:70]}")
        th = [k for k, s in enumerate(p["segmentos"]) if s.get("visual") == "talking_head"]
        if th:
            trocados = [k for k in th if p["segmentos"][k].get("substituir")]
            print(f"  talking_head: {th} ({len(trocados)}/{len(th)} substituídos)")

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
        s_.add_argument("--modo", choices="ABCN", default="A"); s_.add_argument("--alvo", type=float, default=None)
        s_.add_argument("--transcricao"); s_.add_argument("--visual"); s_.add_argument("--pontuacao"); s_.add_argument("--tts")
        s_.add_argument("--rapido", action="store_true"); s_.add_argument("--sem-audio-original", action="store_true")
        # com narração o áudio original sai por padrão; --com-cama traz de volta a -18 dB
        s_.add_argument("--com-cama", action="store_true")
        # modo A+ (Task 10b): troca os trechos de apresentador por ilustração gerada,
        # mantendo o áudio original. Só 'gerado' por enquanto ('broll' ficou adiado).
        s_.add_argument("--substituir", choices=["gerado"]); s_.add_argument("--imagem")
        # chamada de ~12s (capa editorial + promessas) colada ANTES do conteúdo
        s_.add_argument("--abertura", action="store_true")
        s_.add_argument("--forcar", action="store_true")
    i = sub.add_parser("ingest"); i.add_argument("fonte"); i.add_argument("--forcar", action="store_true")
    # CORREÇÃO 4 (rodada 1 de revisão): só declara --provedor/--forcar no subcomando que de
    # fato os repassa pra fase (ver main(), abaixo) — antes o loop dava as duas flags pra
    # todo mundo, inclusive status/custo (que nunca as usam) e selecionar/render/narrar
    # (cujas fases não têm parâmetro forcar exposto no CLI), o que aparecia morto no --help.
    USA_PROVEDOR = {"transcrever", "cenas", "pontuar", "narrar", "substituir", "abertura"}
    USA_FORCAR = {"transcrever", "cenas", "pontuar", "substituir", "abertura"}
    for nome in ("transcrever", "cenas", "pontuar", "selecionar", "substituir", "abertura", "render", "narrar", "status", "custo"):
        sp = sub.add_parser(nome); sp.add_argument("id")
        if nome in USA_PROVEDOR: sp.add_argument("--provedor")
        if nome in USA_FORCAR: sp.add_argument("--forcar", action="store_true")
        if nome == "cenas": sp.add_argument("--classificar", action="store_true")
        if nome in ("pontuar", "selecionar"): sp.add_argument("--modo", choices="ABCN", default="A"); sp.add_argument("--alvo", type=float)
        if nome == "render": sp.add_argument("--rapido", action="store_true"); sp.add_argument("--sem-audio-original", action="store_true"); sp.add_argument("--com-cama", action="store_true")
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
    elif a.cmd == "substituir": print(F_su.substituir(d, cfg, a.provedor, forcar=a.forcar))
    elif a.cmd == "abertura": print(F_ab.abertura(d, cfg, a.provedor, forcar=a.forcar))
    elif a.cmd == "render": print(F_re.render(d, cfg, rapido=a.rapido, sem_audio_original=False if a.com_cama else None))
    elif a.cmd == "narrar": print(F_na.narrar(d, cfg, a.provedor))

if __name__ == "__main__":
    main()
