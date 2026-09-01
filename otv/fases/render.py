import json, shutil, tempfile, time
from pathlib import Path
from otv.util.ffmpeg import probe, run
from otv.util.custos import registrar
from otv.util.texto import desenhar

# A manchete e a cartela NÃO usam drawtext: o drawtext do ffmpeg 6.1.1 trunca o texto pelo
# número de bytes, comendo uma letra do fim por caractere acentuado (medição e detalhes em
# otv/util/texto.py). O texto é rasterizado com PIL e entra no filtro como imagem.


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
        # O texto vai como IMAGEM (PIL), não como drawtext: o drawtext do ffmpeg 6.1.1
        # trunca por bytes e come uma letra do fim por caractere acentuado — a manchete
        # "IA e bilionários estão tentando vencer o envelhecimento" saiu no vídeo de
        # 2026-09-01 como "...envelhecimen". Ver otv/util/texto.py para a medição.
        base = Path(dir) if dir else Path(tempfile.gettempdir())
        png, alt = desenhar(manchete, base / "manchete.png", W, tamanho_px=int(H * 0.055),
                            margem_pct=0.06)
        # movie= em vez de um -i extra: acrescentar input aqui deslocaria os índices [k:a]
        # da narração, que render() monta contando segmentos.
        fc.append(f"movie={png},format=rgba,loop=loop=-1:size=1,setpts=N/{FPS}/TB,"
                  f"fade=t=in:st=0:d=0.5:alpha=1,fade=t=out:st=3.5:d=0.5:alpha=1[mtx]")
        # a tarja acompanha a ALTURA REAL do texto: manchete de duas linhas estourava a
        # faixa fixa de 16% e as letras de baixo ficavam sobre a imagem, ilegíveis
        topo = max(0, int(H * 0.08 - alt / 2))
        tarja = min(H, topo + alt + int(H * 0.03))
        fc.append(f"[vc]drawbox=y=0:h={tarja}:color=black@0.55:t=fill:enable='lt(t,4)'[vbx]")
        # shortest=1 é OBRIGATÓRIO: a imagem entra com loop=-1 (nunca dá EOF), então com
        # shortest=0 o overlay segue produzindo quadro pra sempre depois que o vídeo acaba
        # e o render NUNCA termina. Medido em 2026-09-01: 18 min de ffmpeg e um output.mp4
        # de 51 MB ainda crescendo, num teste cujo vídeo tem 5,5 s.
        fc.append(f"[vbx][mtx]overlay=0:{topo}:enable='lt(t,4)':shortest=1{vfade}[v]")
    else:
        fc.append(f"[vc]null{vfade}[v]")
    return ";".join(fc)


def costurar(partes, saida, tamanho=None):
    """Concatena N mp4 num só, REENCODANDO.

    Reencoda em vez de usar `-c copy` porque as partes não compartilham parâmetros: o corpo
    sai do otv na geometria do fonte (e o áudio do fonte pode vir em qualquer taxa — o vídeo
    de exemplo tem AAC a 96 kHz), enquanto a abertura e o CTA são renders do HyperFrames a
    30 fps. Concat sem reencode exige parâmetros idênticos — já quebrou duas vezes com
    "parameters do not match". O scale+fps no vídeo e o aresample no áudio normalizam tudo
    antes do concat.

    Parte sem trilha de áudio é erro explícito: concat de um ramo mudo com um ramo sonoro
    dessincroniza (ou falha) em vez de simplesmente ficar em silêncio.
    """
    partes = [Path(x) for x in partes]
    W, H, FPS = tamanho or (1920, 1080, 25)
    entradas, fc, rotulos = [], [], []
    for i, parte in enumerate(partes):
        if not run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                    "stream=index", "-of", "csv=p=0", str(parte)]).strip():
            raise RuntimeError(f"{parte} não tem trilha de áudio — gere-a (nem que seja silêncio) antes de costurar")
        entradas += ["-i", str(parte)]
        fc.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p[v{i}]")
        fc.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        rotulos.append(f"[v{i}][a{i}]")
    fc.append("".join(rotulos) + f"concat=n={len(partes)}:v=1:a=1[v][a]")
    saida = Path(saida); tmp = saida.with_name(saida.stem + ".costura.mp4")
    run(["ffmpeg", "-v", "error", "-y"] + entradas + ["-filter_complex", ";".join(fc),
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)])
    tmp.replace(saida)
    return saida


def cartela(texto, destino, tamanho, segundos=1.5):
    """Cartela de assunto: fundo escuro, o texto do assunto e uma parada.

    Entra ENTRE a abertura e o corpo. A abertura termina em ritmo alto (blocos curtos com
    fala por cima); emendar o vídeo direto nela faz as duas coisas virarem uma só pra quem
    assiste. A cartela é a respirada que separa "a chamada" do "o vídeo": 0,25 s pra entrar,
    1 s parado, 0,25 s pra sair.
    """
    W, H, FPS = tamanho
    png, _ = desenhar(texto, Path(destino).with_suffix(".png"), W, altura=H,
                      tamanho_px=int(H * 0.075), regua=True)
    entrada = saida_fade = 0.25
    fc = [f"color=c=0x0d0b08:s={W}x{H}:r={FPS}:d={segundos}[bg]",
          f"movie={png},format=rgba,loop=loop=-1:size=1,setpts=N/{FPS}/TB,"
          f"fade=t=in:st=0:d={entrada}:alpha=1,"
          f"fade=t=out:st={segundos - saida_fade}:d={saida_fade}:alpha=1[tx]",
          "[bg][tx]overlay=0:0:shortest=1,format=yuv420p[v]"]
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=48000:cl=stereo:d={segundos}",
         "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "0:a", "-t", str(segundos),
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "128k", str(destino)])
    return Path(destino)


def concatenar_cta(corpo, cfg, tamanho=None, abertura=None, assunto=None):
    """Costura abertura + cartela de assunto + corpo + CTA, pulando o que não existir."""
    caminho = cfg.get("cta", "assets/cta.mp4")
    cta = Path(caminho).expanduser() if caminho else None   # "" desliga (Path("") vira "." e existe)
    partes = []
    if abertura and Path(abertura).exists():
        partes.append(Path(abertura))
        # a cartela só faz sentido separando DUAS coisas: sem abertura não há o que quebrar
        dur = float(cfg.get("cartela_s", 1.5) or 0)
        if dur > 0 and assunto:
            partes.append(cartela(assunto, Path(corpo).with_name("cartela.mp4"),
                                  tamanho or (1920, 1080, 25), dur))
    partes.append(Path(corpo))
    if cta and cta.exists():
        partes.append(cta)
    if len(partes) == 1:
        return Path(corpo)
    return costurar(partes, Path(corpo), tamanho)


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
    concatenar_cta(out, cfg, tamanho if not rapido else None, abertura=dir / "abertura.mp4",
                   assunto=plan.get("manchete"))
    vid = json.loads((dir / "metadata.json").read_text()).get("id", dir.name)
    dest = Path(cfg["saida"]).expanduser() / vid; dest.mkdir(parents=True, exist_ok=True)
    for f in ("output.mp4", "plan.json", "notas.json", "unidades.json", "custos.json"):
        if (dir / f).exists():
            shutil.copy(dir / f, dest / f)
    registrar(dir, "render", {"rapido": rapido, "segundos": round(time.time() - t0, 1), "saida": str(dest / "output.mp4")})
    return out
