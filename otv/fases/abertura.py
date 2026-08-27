"""Abertura (chamada) — os 10 a 15 segundos que vêm ANTES do conteúdo.

Estrutura: um card de CAPA editorial (manchete garrafal cobrindo parte do quadro) seguido de
blocos com trechos do próprio vídeo e um texto garrafal por cima, tudo narrado.

Por que a abertura é uma composição HTML (HyperFrames) e não `drawtext`: o `drawtext` do ffmpeg
dá conta de uma linha sóbria — foi o que fez a manchete antiga, e ficou fraca. Capa editorial
tem várias linhas, hierarquia, caixa alta condensada e bloco de cor cobrindo parte do quadro;
em `drawtext` cada quebra de linha é um filtro separado, sem controle de entrelinha e sem jeito
de conferir antes de renderizar. O mesmo motor serve pro CTA, então é um componente só.

Os trechos vêm de cenas que NÃO entraram no corte final: a chamada mostra que existe material,
sem queimar o que a pessoa vai ver em seguida.
"""
import json, re, shutil, subprocess, time
from pathlib import Path
from otv.provedores.llm import criar_llm
from otv.fases.narrar import truncar_por_orcamento
from otv.provedores.tts import tts
from otv.util.custos import registrar
from otv.util.fala import forma_fala
from otv.util.ffmpeg import probe, run, thumb

DUR_CLIPE = 2.6         # segundos de vídeo por bloco (o texto garrafal precisa de tempo de leitura)
MIN_BLOCO = 2.4         # piso de duração de um bloco, mesmo com fala curta
# O aperto da duração vive no PROMPT (fala curta), nunca num teto que corta o bloco por baixo
# do áudio. Em 2026-08-27 um teto de 4.8s sobre um wav de 6.6s fez a narração do bloco 0
# continuar tocando enquanto a do bloco 1 já tinha começado: 1,8s de duas vozes sobrepostas.
# MAX_BLOCO agora é só um alvo pra avisar quando a chamada estourou, não um corte.
ALVO_BLOCO = 4.8
MAX_PALAVRAS_FALA = 12
FOLGA_BLOCO = 0.45      # respiro depois da fala, antes de trocar de bloco
N_BLOCOS = 3            # capa + 2 promessas  ≈ 12–14 s
VISUAL_BOM = ("grafico", "demo_tela", "slide")


def _usadas(plan):
    return [(s["in"], s["out"]) for s in plan["segmentos"]]


def escolher_cenas(cenas, plan, n=N_BLOCOS - 1, dur=DUR_CLIPE):
    """Cenas visualmente interessantes que NÃO entraram no corte, espalhadas pelo vídeo."""
    usadas = _usadas(plan)
    def livre(c):
        meio = (c["ini"] + c["fim"]) / 2
        return not any(a - 1 <= meio <= b + 1 for a, b in usadas)
    cand = [c for c in cenas if c.get("visual") in VISUAL_BOM and (c["fim"] - c["ini"]) >= dur and livre(c)]
    if len(cand) < n:  # vídeo pobre de imagem: aceita qualquer cena longa o bastante
        cand = [c for c in cenas if (c["fim"] - c["ini"]) >= dur and livre(c)] or list(cenas)
    if not cand:
        return []
    # espalha: divide a linha do tempo em n faixas e pega uma cena de cada
    cand.sort(key=lambda c: c["ini"])
    passo = max(1, len(cand) // n)
    escolhidas = [cand[min(i * passo, len(cand) - 1)] for i in range(n)]
    vistos, saida = set(), []
    for c in escolhidas:
        if c["id"] not in vistos:
            vistos.add(c["id"]); saida.append(c)
    for c in cand:                                   # completa se houve id repetido
        if len(saida) >= n:
            break
        if c["id"] not in vistos:
            vistos.add(c["id"]); saida.append(c)
    return saida[:n]


def extrair_clipes(video, cenas, destino, dur=DUR_CLIPE, tamanho=(1920, 1080, 25)):
    """Recorta cada cena num MP4 curto, H.264, na geometria do vídeo.

    Recorta com ffmpeg em vez de mandar o `<video>` da composição apontar pro fonte inteiro:
    o fonte pode ser AV1 de 20 min (o Chrome do render nem sempre decodifica), e um clipe de
    2,6 s carrega instantaneamente no headless.
    """
    W, H, FPS = tamanho
    destino = Path(destino); destino.mkdir(parents=True, exist_ok=True)
    saida = []
    for i, c in enumerate(cenas):
        ini = c["ini"] + min(0.6, max(0.0, (c["fim"] - c["ini"] - dur) / 2))
        out = destino / f"clip_{i}.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ini:.3f}", "-t", f"{dur}", "-i", str(video),
             "-an", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
             "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)])
        saida.append(out)
    return saida


def roteiro(plan, notas, llm, titulo, n=N_BLOCOS):
    lista = "\n".join(f"- {s.get('texto', '')[:150]}" for s in plan["segmentos"][:10])
    tpl = (Path(__file__).resolve().parents[2] / "prompts/abertura.md").read_text()
    resp, uso = llm.chat_json(tpl.format(titulo=titulo, manchete=plan.get("manchete", ""), lista=lista, n=n))
    blocos = [{"titulo": "", "fala": ""} for _ in range(n)]
    for b in resp.get("blocos", []):
        k = int(b.get("k", -1))
        if 0 <= k < n:
            blocos[k] = {"titulo": str(b.get("titulo", ""))[:48].upper(),
                         "fala": encurtar_fala(str(b.get("fala", "")).strip(), MAX_PALAVRAS_FALA)}
    return blocos, uso


def encurtar_fala(texto, orcamento=MAX_PALAVRAS_FALA):
    """Encurta a fala SEM nunca devolver frase pela metade.

    `truncar_por_orcamento` (do narrar) corta na fronteira de palavra quando nem a primeira
    frase cabe — o que num roteiro de vários períodos é aceitável, mas aqui cada fala é UMA
    frase: o corte devolvia "...200 milhões de proteínas ganhou" e a narração parava no meio.
    Aqui a regra é outra: descarta frases inteiras do fim; se sobrar só uma e ela não couber,
    ela vai inteira mesmo assim. Bloco um pouco mais longo é melhor que frase quebrada.
    """
    if not texto:
        return texto
    sentencas = [s for s in re.split(r"(?<=[.!?])\s+", texto.strip()) if s]
    acc, usadas = [], 0
    for s in sentencas:
        n = len(s.split())
        if acc and usadas + n > orcamento:
            break
        acc.append(s); usadas += n
    return " ".join(acc)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def montar_html(blocos, capa_jpg, clipes, W=1920, H=1080):
    """Gera a composição HyperFrames da abertura (capa + blocos com vídeo e texto garrafal)."""
    total = round(sum(b["dur"] for b in blocos), 2)
    # O <video> fica no NÍVEL DA RAIZ, nunca dentro da <section> temporizada: o extrator de
    # quadros resolve o data-start do vídeo sem o offset do ancestral, então wrapper e vídeo
    # temporizados ao mesmo tempo discordam e o clipe mostra o quadro errado
    # (`video_nested_in_timed_element`). O fundo entra primeiro no DOM (fica atrás) e a
    # <section> por cima carrega só véu, faixa e texto.
    fundos, partes, anim, t_ = [], [], [], 0.0
    for k, b in enumerate(blocos):
        fim = t_ + b["dur"]
        if k == 0:
            fundos.append(f'    <img class="bg clip" id="bg{k}" src="assets/capa.jpg" alt="" '
                          f'data-start="{t_:.2f}" data-duration="{b["dur"]:.2f}" data-track-index="{10 + k}">')
        else:
            # vídeo NÃO leva class="clip" (o framework cuida de play/seek por data-start),
            # mas PRECISA de id — sem id o renderer não o descobre e o clipe sai congelado.
            fundos.append(f'    <video class="bg" id="bg{k}" src="assets/clip_{k - 1}.mp4" '
                          f'data-start="{t_:.2f}" data-duration="{b["dur"]:.2f}" '
                          f'data-track-index="{10 + k}" data-volume="0" muted></video>')
        classe = "bloco capa" if k == 0 else "bloco"
        partes.append(
            f'    <section class="{classe} clip" id="b{k}" data-start="{t_:.2f}" '
            f'data-duration="{b["dur"]:.2f}" data-track-index="{1 if k % 2 == 0 else 3}">\n'
            f'      <div class="veu"></div>\n'
            f'      <div class="faixa" id="fx{k}"></div>\n'
            f'      <div class="txt">\n'
            f'        <div class="kick" id="kk{k}">{"EM SEGUIDA" if k else "AGORA"}</div>\n'
            f'        <h1 id="tt{k}">{_esc(b["titulo"])}</h1>\n'
            f'      </div>\n'
            f'    </section>')
        partes.append(f'    <audio id="a{k}" data-start="{t_ + 0.18:.2f}" data-duration="{b["wav"]:.2f}" '
                      f'data-track-index="{30 + k}" src="assets/fala_{k}.wav"></audio>')
        anim.append(
            f'      tl.fromTo("#fx{k}",{{scaleX:0}},{{scaleX:1,duration:.42,ease:"power3.out"}},{t_ + 0.05:.2f});\n'
            f'      tl.fromTo("#kk{k}",{{opacity:0,x:-24}},{{opacity:1,x:0,duration:.4,ease:"power2.out"}},{t_ + 0.22:.2f});\n'
            f'      tl.fromTo("#tt{k}",{{opacity:0,y:44}},{{opacity:1,y:0,duration:.55,ease:"power3.out"}},{t_ + 0.30:.2f});\n'
            + (f'      tl.to("#bg{k}",{{scale:1.10,duration:{b["dur"]:.2f},ease:"none"}},{t_:.2f});\n' if k == 0 else "")
            + f'      tl.to("#b{k}",{{opacity:0,duration:.28,ease:"power2.in"}},{fim - 0.28:.2f});\n'
              f'      tl.set("#b{k}",{{opacity:0}},{fim:.2f});')
        t_ = fim
    corpo_html = chr(10).join(fundos + partes)
    css_fonts = (Path(__file__).resolve().parents[2] / "assets/fonts/fonts.css").read_text()
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>
{css_fonts}
  :root{{--bg:#0D1321;--fg:#F0EBD8;--muted:#748CAB;--accent:#FFC300;--accent2:#FCA311}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{width:{W}px;height:{H}px;overflow:hidden;background:var(--bg)}}
  body{{font-family:Inter,sans-serif;color:var(--fg)}}
  #root{{position:relative;width:{W}px;height:{H}px;background:var(--bg);overflow:hidden}}
  .bloco{{position:absolute;inset:0;overflow:hidden}}
  .bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform-origin:52% 48%}}
  /* véu: sem ele o texto garrafal briga com a imagem e some em quadro claro */
  .veu{{position:absolute;inset:0;background:
        linear-gradient(90deg,rgba(13,19,33,.94) 0%,rgba(13,19,33,.78) 46%,rgba(13,19,33,.18) 100%),
        linear-gradient(0deg,rgba(13,19,33,.90) 0%,rgba(13,19,33,0) 52%)}}
  /* a faixa âmbar é o que faz "cobrir uma parte pra parecer capa" */
  .faixa{{position:absolute;left:0;bottom:118px;width:{int(W * 0.62)}px;height:14px;transform-origin:left center;
          background:linear-gradient(90deg,var(--accent),var(--accent2))}}
  .txt{{position:absolute;left:112px;right:120px;bottom:170px}}
  .kick{{font-family:"JetBrains Mono",monospace;font-weight:700;font-size:28px;letter-spacing:.44em;
         text-transform:uppercase;color:var(--accent);margin-bottom:26px}}
  .txt h1{{font-family:Sora,sans-serif;font-weight:800;font-size:148px;line-height:.92;
           letter-spacing:-.04em;text-transform:uppercase;max-width:1420px;
           text-shadow:0 26px 80px rgba(0,0,0,.72)}}
  .capa .txt h1{{font-size:126px;color:var(--fg)}}
  .capa .kick{{color:var(--accent)}}
  #progress{{position:absolute;left:0;bottom:0;height:8px;width:100%;transform-origin:left center;
             background:linear-gradient(90deg,var(--accent),var(--accent2))}}
</style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}">
{corpo_html}
    <div id="progress" data-layout-ignore></div>
    <script src="assets/gsap.min.js"></script>
    <script>
      window.__timelines = window.__timelines || {{}};
      const TOTAL = {total};
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#progress",{{scaleX:0}},{{scaleX:1,duration:TOTAL,ease:"none"}},0);
{chr(10).join(anim)}
      tl.set({{}}, {{}}, TOTAL);
      window.__timelines["main"] = tl;
    </script>
  </div>
</body>
</html>
"""


def abertura(dir, cfg, provedor=None, forcar=False):
    """Gera abertura.mp4 (chamada de ~10–15 s) na pasta de trabalho."""
    dir = Path(dir); out = dir / "abertura.mp4"
    if out.exists() and not forcar:
        return out
    plan = json.loads((dir / "plan.json").read_text())
    notas = json.loads((dir / "notas.json").read_text()) if (dir / "notas.json").exists() else {}
    meta = json.loads((dir / "metadata.json").read_text())
    cenas = json.loads((dir / "scenes.json").read_text())["cenas"] if (dir / "scenes.json").exists() else []
    video = dir / "video.mp4"
    i = probe(video); tamanho = (i["largura"], i["altura"], i["fps"])
    t0 = time.time()

    proj = dir / "abertura"; ativos = proj / "assets"
    if ativos.exists():
        shutil.rmtree(ativos)
    ativos.mkdir(parents=True)

    escolhidas = escolher_cenas(cenas, plan)
    extrair_clipes(video, escolhidas, ativos, tamanho=tamanho)
    # capa: um quadro do primeiro segmento do corte (o gancho), escurecido pelo véu do CSS
    thumb(video, plan["segmentos"][0]["in"] + 1.0, ativos / "capa.jpg", largura=tamanho[0])

    llm = criar_llm(cfg, cfg["pontuacao"])
    blocos, uso = roteiro(plan, notas, llm, meta.get("titulo", ""), n=1 + len(escolhidas))
    for k, b in enumerate(blocos):
        wav = ativos / f"fala_{k}.wav"
        if b["fala"]:
            tts(forma_fala(b["fala"]), wav, cfg, provedor)
        else:
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                 "-t", f"{MIN_BLOCO}", str(wav)])
        b["wav"] = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(wav)]).strip())
        # a duração do bloco SEGUE o áudio: sem isso o bloco acaba antes da fala dele e a
        # narração invade o bloco seguinte, que já começou a falar (duas vozes ao mesmo tempo)
        b["dur"] = round(max(MIN_BLOCO, b["wav"] + FOLGA_BLOCO), 2)

    total = sum(b["dur"] for b in blocos)
    if total > len(blocos) * ALVO_BLOCO:
        print(f"aviso: chamada com {total:.1f}s ({len(blocos)} blocos) — acima do alvo de "
              f"{len(blocos) * ALVO_BLOCO:.1f}s; encurte as falas em prompts/abertura.md")
    raiz = Path(__file__).resolve().parents[2]
    shutil.copy(raiz / "assets" / "gsap.min.js", ativos / "gsap.min.js")
    (ativos / "fonts").mkdir(exist_ok=True)
    for f in (raiz / "assets" / "fonts").glob("*.woff2"):
        shutil.copy(f, ativos / "fonts" / f.name)
    html = montar_html(blocos, ativos / "capa.jpg", None, tamanho[0], tamanho[1])
    # o fonts.css embutido aponta pra ./<arquivo>; aqui as fontes estão em assets/fonts/
    html = html.replace("url('assets/fonts/", "url('assets/fonts/").replace("url('./", "url('assets/fonts/")
    (proj / "index.html").write_text(html)

    subprocess.run(["npx", "hyperframes", "render", "--quality", "high", "--output", str(out.resolve())],
                   cwd=str(proj), check=True, capture_output=True, text=True, timeout=1800)
    (dir / "abertura.json").write_text(json.dumps({"blocos": blocos, "cenas": [c["id"] for c in escolhidas]},
                                                  ensure_ascii=False, indent=1))
    registrar(dir, "abertura", {"llm": llm.nome, "uso": uso, "blocos": len(blocos),
                                "segundos": round(time.time() - t0, 1),
                                "duracao_s": round(sum(b["dur"] for b in blocos), 2)})
    return out
