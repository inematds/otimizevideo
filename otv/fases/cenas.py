import json, time
from pathlib import Path
from otv.util.ffmpeg import run, thumb, probe
from otv.util.custos import registrar

_MODELO_ROSTO = Path(__file__).resolve().parents[1] / "modelos" / "blaze_face_short_range.tflite"

VISUAIS_VALIDOS = ("talking_head", "slide", "demo_tela", "grafico", "outro")


def proxy_cenas(video, destino, altura=360):
    """Proxy H.264 pequeno para a detecção de cena. Reaproveita um já existente.

    O PySceneDetect lê o vídeo pelo OpenCV, e o OpenCV desta máquina NÃO decodifica AV1
    (que é o que o yt-dlp entrega em 1080p): em 2026-08-27 um vídeo AV1 de 20 min deu
    ZERO cenas, e o fallback silencioso de "uma cena cobrindo o vídeo inteiro" fez o
    modo B/C e o A+ ficarem sem nenhuma cena pra classificar. O ffmpeg decodifica AV1
    sem problema, então transcodificamos uma vez para 360p H.264 e detectamos em cima
    disso — de quebra é bem mais rápido que detectar em 1080p.
    """
    destino = Path(destino)
    if not destino.exists():
        tmp = destino.with_suffix(".parte.mp4")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-an", "-vf", f"scale=-2:{altura}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(tmp)])
        tmp.replace(destino)
    return destino


def detectar_cenas(video, proxy=None):
    from scenedetect import detect, AdaptiveDetector
    alvo = proxy_cenas(video, proxy) if proxy else video
    lista = detect(str(alvo), AdaptiveDetector())
    if not lista:
        dur = probe(video)["duracao_s"]
        if dur > 120:
            # Uma cena só num vídeo de mais de 2 min quase sempre significa que o
            # decodificador do OpenCV não leu o arquivo (ver proxy_cenas) — não um vídeo
            # de plano único. Falhar alto: o silêncio aqui vira "nenhum talking_head"
            # lá na frente, sem sinal nenhum de que a detecção não rodou.
            raise RuntimeError(
                f"detecção de cena não achou nenhum corte em {dur:.0f}s de vídeo ({alvo}) — "
                "provavelmente o OpenCV não decodificou esse codec; confira se o proxy H.264 foi gerado")
        return [(0.0, dur)]
    return [(s.seconds, e.seconds) for s, e in lista]  # get_seconds() está deprecated na 0.7.1


_det = None


def _detector():
    """Detector de rosto em cache (mediapipe.tasks — API nova, mediapipe>=0.10).

    A máquina de desenvolvimento tem mediapipe 1.0.1, que NÃO expõe mais
    `mp.solutions.face_detection` (API antiga). Usamos `mediapipe.tasks.python.vision`
    com o modelo blaze_face_short_range.tflite baixado em otv/modelos/.
    """
    global _det
    if _det is None:
        if not _MODELO_ROSTO.exists():
            raise RuntimeError(
                f"modelo de rosto não encontrado em {_MODELO_ROSTO} — "
                "copie blaze_face_short_range.tflite para otv/modelos/"
            )
        from mediapipe.tasks.python import vision
        from mediapipe.tasks import python as mpp
        try:
            base_options = mpp.BaseOptions(model_asset_path=str(_MODELO_ROSTO))
            options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
            _det = vision.FaceDetector.create_from_options(options)
        except Exception as e:
            raise RuntimeError(f"falha ao carregar modelo de rosto em {_MODELO_ROSTO}: {e}") from e
    return _det


def rosto_pct(jpg):
    """Fração de área (largura relativa × altura relativa) do maior rosto na imagem.

    A API nova do mediapipe devolve o bounding box em PIXELS (origin_x, origin_y,
    width, height), não em fração como a API antiga (`relative_bounding_box`).
    Por isso dividimos explicitamente pela largura/altura da imagem — sem isso o
    contrato de "fração de área" quebra e o limiar de 0.08 do classificar_local
    fica sem sentido.
    """
    import mediapipe as mp, cv2
    det = _detector()
    img_bgr = cv2.imread(str(jpg))
    if img_bgr is None:
        return 0.0
    h, w = img_bgr.shape[:2]
    if h == 0 or w == 0:
        return 0.0
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = det.detect(mp_img)
    if not res.detections:
        return 0.0
    bb = max(res.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height).bounding_box
    frac = (max(0.0, bb.width) / w) * (max(0.0, bb.height) / h)
    return round(max(0.0, frac), 4)


def classificar_local(rosto):
    return "talking_head" if rosto >= 0.08 else "outro"


def cenas(dir, cfg, forcar=False):
    dir = Path(dir)
    out = dir / "scenes.json"
    if out.exists() and not forcar:
        return out
    t0 = time.time()
    (dir / "thumbs").mkdir(exist_ok=True)
    lista = []
    for i, (ini, fim) in enumerate(detectar_cenas(dir / "video.mp4", proxy=dir / "video_360p.mp4")):
        jpg = dir / "thumbs" / f"{i:03d}.jpg"
        thumb(dir / "video.mp4", ini + min(1.0, (fim - ini) / 2), jpg)
        r = rosto_pct(jpg)
        lista.append({
            "id": i, "ini": round(ini, 3), "fim": round(fim, 3), "thumb": f"thumbs/{i:03d}.jpg",
            "rosto_pct": r, "visual": classificar_local(r), "descricao": None, "pip": False,
        })
    out.write_text(json.dumps({"cenas": lista}, ensure_ascii=False, indent=0))
    registrar(dir, "cenas", {"quantidade": len(lista), "segundos": round(time.time() - t0, 1)})
    return out


def classificar(dir, cfg, provedor=None, forcar=False):
    from otv.provedores.llm import criar_llm
    dir = Path(dir)
    sc = json.loads((dir / "scenes.json").read_text())
    lista = sc["cenas"]
    if all(c.get("descricao") for c in lista) and not forcar:
        return dir / "scenes.json"
    llm = criar_llm(cfg, provedor or cfg["visual"])
    t0 = time.time()
    uso_total = {}
    tpl = (Path(__file__).resolve().parents[2] / "prompts/classificar.md").read_text()
    for k in range(0, len(lista), 20):
        lote = lista[k:k + 20]
        resp, uso = llm.chat_json(tpl.format(n=len(lote)), imagens=[dir / c["thumb"] for c in lote])
        for r in resp.get("cenas", []):
            i = int(r.get("i", -1))
            if 0 <= i < len(lote) and r.get("visual") in VISUAIS_VALIDOS:
                c = lote[i]
                c["visual"] = "talking_head" if c["rosto_pct"] >= 0.15 else r["visual"]  # rosto grande vence
                c["descricao"] = str(r.get("descricao", ""))[:80]
                c["pip"] = bool(r.get("pip", False))
        for kk, v in (uso or {}).items():
            if isinstance(v, (int, float)):
                uso_total[kk] = uso_total.get(kk, 0) + v
    (dir / "scenes.json").write_text(json.dumps(sc, ensure_ascii=False, indent=0))
    registrar(dir, "classificar", {"provedor": llm.nome, "uso": uso_total, "segundos": round(time.time() - t0, 1)})
    return dir / "scenes.json"
