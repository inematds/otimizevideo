import json, shutil, time
from pathlib import Path
from otv.util.ffmpeg import probe, run
from otv.util.custos import registrar

# Fonte usada pela manchete (drawtext). Passamos `fontfile=` explicitamente sempre que ela
# existir neste sistema, em vez de confiar no fontconfig padrão do ffmpeg: em ambientes sem
# fonte "default" configurada (containers mínimos, outra máquina) um drawtext sem fontfile=
# falha em runtime — e isso não aparece num teste que só confere a string do filtro. Já
# confirmado nesta máquina que a DejaVu Sans está aqui; se um dia não estiver, cai pra sem
# fontfile= (deixa o ffmpeg tentar resolver via fontconfig) em vez de quebrar a montagem do filtro.
FONTE_MANCHETE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def montar_filtro(segmentos, narracao=None, cama_db=-18, sem_audio_original=True, manchete=None,
                  dir=None, tamanho=None, fade_s=0.0):
    """Filtro do render: UM input de vídeo por segmento (índices 0..N-1), narração depois.

    Por que um input por segmento e não `[0:v]trim` N vezes sobre um único input: com um
    input só, o ffmpeg decodifica o arquivo LINEARMENTE uma vez e alimenta todos os ramos
    ao mesmo tempo, enquanto o `concat` consome apenas o ramo 0. Os quadros CRUS dos
    segmentos 1..N-1 ficam empilhados nas filas do concat até chegar a vez deles — o vídeo
    inteiro em RAM descomprimido. Em 2026-08-27 isso deu 60,9 GB de RSS num fonte de 20
    min e travou o host (ver FALHAS.md). Com um input por segmento (`-ss`/`-t` na entrada),
    o ffmpeg só lê de um input quando o filtergraph pede quadros dele: o concat puxa o
    segmento 0, os outros decodificadores ficam parados, e a memória fica limitada a
    alguns quadros por ramo. Mesmo resultado, mesma precisão de quadro, um encode só.

    `render()` é quem monta os `-i` na ordem que os índices aqui assumem — os dois têm que
    mudar juntos.

    Modo A+ (Task 10b): quando um segmento traz `substituir` (caminho relativo de um PNG),
    o VÍDEO dele vem da imagem com Ken Burns lento em vez do trecho original — mas o input
    `[k:a]` continua sendo lido, porque o ÁUDIO segue sendo o original. `dir` resolve o
    caminho relativo e `tamanho` é (largura, altura, fps) do fonte: o filtro `concat` exige
    tamanho e SAR iguais em todos os ramos, então a imagem tem que entrar na geometria do vídeo.
    """
    W, H, FPS = tamanho or (1920, 1080, 25)
    fc = []; entradas = []
    n = len(segmentos)
    for k, s in enumerate(segmentos):
        d = s["out"] - s["in"]; ext = float(s.get("estender_s") or 0)
        subst = s.get("substituir")
        if subst:
            # zoompan produz d=N quadros a partir da imagem única, então ele já cobre a
            # extensão (d+ext) — nada de tpad aqui (tpad clona o último quadro de um vídeo).
            # z sobe devagar até 1.12 com o centro fixo: Ken Burns lento, sem deriva.
            caminho = str(Path(dir) / subst) if dir else str(subst)
            nq = max(1, round((d + ext) * FPS))
            v = (f"movie={caminho},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                 f"zoompan=z='min(zoom+0.0004,1.12)':d={nq}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                 f"s={W}x{H}:fps={FPS},setsar=1,format=yuv420p,setpts=PTS-STARTPTS")
        else:
            # o input k já vem cortado por -ss/-t, com timestamps começando em 0; o trim=0:d é
            # a garantia de duração exata (o -t da entrada pode arredondar por quadro).
            v = f"[{k}:v]trim=0:{d},setpts=PTS-STARTPTS"
        a = f"[{k}:a]atrim=0:{d},asetpts=PTS-STARTPTS,afade=t=in:d=0.04,afade=t=out:st={max(0, d - 0.04):.3f}:d=0.04"
        if ext > 0:
            if not subst:
                v += f",tpad=stop_mode=clone:stop_duration={ext}"
            a += f",apad=pad_dur={ext}"
        if narracao and narracao[k]:
            # sem_audio_original=True precisa silenciar de verdade: "volume=0dB" é ganho
            # unitário (não muda nada), não mudo. "volume=0" (fator linear zero) é que zera.
            ganho = "volume=0" if sem_audio_original else f"volume={cama_db}dB"
            # Achado 1 (rodada de correção 1 da Task 10): a Task 10 já trunca o roteiro pelo
            # orçamento de palavras ANTES do TTS, mas a duração real do wav ainda não é
            # perfeitamente previsível a partir da contagem de palavras — este afade=t=out é
            # a rede de segurança: se o wav ainda chegar até o teto d+ext, ele desvanece em
            # vez de cortar no meio de uma sílaba (mesma duração de 0.04s da trilha original).
            a += (f",{ganho}[o{k}];[{n + k}:a]apad=whole_dur={d + ext:.3f},atrim=0:{d + ext:.3f},"
                  f"afade=t=out:st={max(0, d + ext - 0.04):.3f}:d=0.04[n{k}];[o{k}][n{k}]amix=inputs=2:normalize=0")
        fc.append(v + f"[v{k}]"); fc.append(a + f"[a{k}]"); entradas.append(f"[v{k}][a{k}]")
    fc.append("".join(entradas) + f"concat=n={len(segmentos)}:v=1:a=1[vc][ac]")
    total = sum((s["out"] - s["in"]) + float(s.get("estender_s") or 0) for s in segmentos)
    # fade de saída: sem ele o corte termina no talo, no meio da respiração da última
    # frase. Fica ANTES do CTA (que é concatenado depois), então o vídeo "fecha" e o
    # card entra limpo, em vez de o conteúdo ser interrompido.
    af = f",afade=t=out:st={max(0.0, total - fade_s):.3f}:d={fade_s}" if fade_s > 0 else ""
    fc.append(f"[ac]loudnorm=I=-16:TP=-1.5{af}[a]")
    vfade = f",fade=t=out:st={max(0.0, total - fade_s):.3f}:d={fade_s}" if fade_s > 0 else ""
    if manchete:
        texto = manchete.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
        # fontfile= vai no FIM das opções do drawtext (a ordem não importa pro ffmpeg) pra
        # não quebrar a string exigida no requisito: "drawtext=text='...'" logo após o "=".
        fontfile = f":fontfile={FONTE_MANCHETE}" if Path(FONTE_MANCHETE).exists() else ""
        # expansion=none: sem isso o drawtext roda com expansion=normal (o default) e
        # interpreta "%{...}" — um "%" solto (ex.: "100% de certeza", plausível numa
        # manchete em PT-BR vinda de LLM) gera só um WARNING ("Stray %"), não erro. Como
        # render() chama o ffmpeg com "-v error", esse warning é engolido: o processo sai
        # com código 0 e o output.mp4 fica sem manchete nenhuma, sem qualquer sinal de
        # falha. expansion=none elimina a classe inteira do problema (dispensa escapar %).
        fc.append(f"[vc]drawbox=y=0:h=ih*0.16:color=black@0.55:t=fill:enable='lt(t,4)',"
                  f"drawtext=text='{texto}':fontcolor=white:fontsize=h*0.055:x=(w-text_w)/2:y=h*0.05:"
                  f"alpha='if(lt(t,0.5),t*2,if(lt(t,3.5),1,(4-t)*2))':enable='lt(t,4)':expansion=none{fontfile}{vfade}[v]")
    else:
        fc.append(f"[vc]null{vfade}[v]")
    return ";".join(fc)


def concatenar_cta(corpo, cfg, tamanho=None):
    """Cola o clipe fixo de CTA no fim do vídeo, se ele existir.

    Reencoda em vez de usar `-c copy`: o corpo sai do otv em 1920x1080/25fps e o áudio do
    fonte pode vir em qualquer taxa (o vídeo de exemplo tem AAC a 96 kHz), enquanto o CTA é
    um render próprio. Concat sem reencode exige parâmetros idênticos nos dois — já quebrou
    duas vezes hoje com "parameters do not match". O `aresample=async=1` e o `fps` no ramo
    de vídeo normalizam os dois lados antes do concat.
    """
    cta = Path(cfg.get("cta", "assets/cta.mp4")).expanduser()
    if not cta.exists():
        return corpo
    corpo = Path(corpo)
    W, H, FPS = tamanho or (1920, 1080, 25)
    tmp = corpo.with_name(corpo.stem + ".comcta.mp4")
    fc = (f"[0:v]scale={W}:{H},setsar=1,fps={FPS},format=yuv420p[v0];"
          f"[1:v]scale={W}:{H},setsar=1,fps={FPS},format=yuv420p[v1];"
          f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
          f"[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
          f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(corpo), "-i", str(cta), "-filter_complex", fc,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)])
    tmp.replace(corpo)
    return corpo


def render(dir, cfg, rapido=False, sem_audio_original=None):
    """Renderiza plan.json -> output.mp4.

    Caminho normal (rapido=False): trim/atrim + concat re-encodando (libx264 -crf 20).
    Corte com precisão de quadro — exato, cada corte cai em qualquer amostra, não só em
    keyframe.

    Caminho --rapido (rapido=True): concat demuxer com `-c copy`. É bem mais rápido
    porque não reencoda, mas por isso os cortes só acontecem em keyframe — a duração e o
    ponto exato de corte são APROXIMADOS de propósito (pode variar por até um GOP inteiro
    dos valores `in`/`out` do plan.json). Não usar quando precisão de corte importa. Os
    dois caminhos não se misturam: --rapido não desenha manchete nem mixa narração.
    """
    dir = Path(dir); plan = json.loads((dir / "plan.json").read_text()); segs = plan["segmentos"]
    out = dir / "output.mp4"; t0 = time.time()
    if not segs:
        raise RuntimeError("plan.json sem segmentos")
    if rapido:
        lista = dir / "concat.txt"
        lista.write_text("".join(f"file 'video.mp4'\ninpoint {s['in']}\noutpoint {s['out']}\n" for s in segs))
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(out)])
    else:
        narr = plan.get("narracao")
        if narr:
            arqs = narr["arquivos"]
            if len(arqs) != len(segs) or any(a is None for a in arqs):
                # Mantém a falha explícita em vez de pular o None: pular desalinharia todos
                # os índices [k+1:a] seguintes em montar_filtro, silenciosamente. A Task 10
                # é quem gera plan["narracao"]["arquivos"] e tem que entregar um wav por
                # segmento (silencioso quando o segmento não tem narração), nunca null.
                raise RuntimeError(
                    "plan['narracao']['arquivos'] precisa ter um wav por segmento (silencioso "
                    f"quando o segmento não tem narração), nunca null — recebi {len(arqs)} "
                    f"entrada(s) para {len(segs)} segmento(s) (Task 10 gera esse arquivo)"
                )
            wavs = [dir / w for w in arqs]
        else:
            wavs = None
        # Um input por segmento: `-ss`/`-t` ANTES do `-i` recortam já na entrada, cada um com
        # seu próprio decodificador. É isso que impede o ffmpeg de empilhar o vídeo inteiro
        # descomprimido nas filas do concat (o travamento de 60,9 GB de 2026-08-27).
        # `-accurate_seek` é o padrão, então o corte continua com precisão de quadro.
        video = str(dir / "video.mp4")
        cmd = ["ffmpeg", "-v", "error", "-y"]
        for s in segs:
            cmd += ["-ss", f"{s['in']}", "-t", f"{s['out'] - s['in']}", "-i", video]
        for w in (wavs or []):
            cmd += ["-i", str(w)]
        # geometria vem do ARQUIVO, não do metadata.json: o concat exige que a imagem do
        # modo A+ entre com o mesmo tamanho/SAR dos ramos de vídeo, e metadata.json pode não
        # ter esses campos (spike antigo, pasta montada à mão) — aí o default silencioso
        # estouraria o render com "parameters do not match".
        i = probe(video)
        tamanho = (i["largura"], i["altura"], i["fps"])
        # Default MUDO quando há narração: -18 dB de FALA continua inteligível e briga com
        # a narração (dois idiomas no mesmo canal). A cama a -18 dB faz sentido pra música
        # e ambiência, não pra voz — por isso virou opt-in (--com-cama), não o padrão.
        mudo = True if sem_audio_original is None else sem_audio_original
        cmd += ["-filter_complex", montar_filtro(segs, wavs, sem_audio_original=mudo,
                                                 manchete=plan.get("manchete"), dir=dir, tamanho=tamanho,
                                                 fade_s=float(cfg.get("fade_final_s", 0.8))),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
        run(cmd)
    concatenar_cta(out, cfg, tamanho if not rapido else None)
    vid = json.loads((dir / "metadata.json").read_text()).get("id", dir.name)
    dest = Path(cfg["saida"]).expanduser() / vid; dest.mkdir(parents=True, exist_ok=True)
    for f in ("output.mp4", "plan.json", "notas.json", "unidades.json", "custos.json"):
        if (dir / f).exists():
            shutil.copy(dir / f, dest / f)
    registrar(dir, "render", {"rapido": rapido, "segundos": round(time.time() - t0, 1), "saida": str(dest / "output.mp4")})
    return out
