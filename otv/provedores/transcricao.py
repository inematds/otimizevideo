import json, time, requests
from pathlib import Path
from otv.util.keys import key

def normalizar_palavras(palavras):
    # Nota: ini/fim são arredondados a cada palavra ANTES da checagem do gap mínimo
    # (e não depois) porque round(x, 3) pode ficar a um ULP abaixo do valor bruto
    # ini + 0.05 (ex.: round(1.85+0.05, 3) == 1.9, mas 1.9 < 1.85+0.05 em float
    # puro). Arredondar antes e revalidar o invariante no domínio já arredondado
    # evita esse falso-negativo de ponto flutuante sem mudar a semântica do gap.
    out = []; fim_ant = 0.0
    for w in palavras:
        ini = round(max(float(w["ini"]), fim_ant), 3)
        fim = round(max(float(w["fim"]), ini + 0.05), 3)
        if fim < ini + 0.05:
            fim = round(ini + 0.051, 3)
        out.append({"t": str(w["t"]).strip(), "ini": ini, "fim": fim})
        fim_ant = fim
    return out

def de_groq(resp):
    palavras = normalizar_palavras([{"t": w["word"], "ini": w["start"], "fim": w["end"]} for w in resp["words"]])
    fins = sorted({round(float(s["end"]), 3) for s in (resp.get("segments") or [])})
    return {"idioma": resp.get("language"), "provedor": "groq/whisper-large-v3-turbo",
            "palavras": palavras, "fins_segmento": fins}

def transcrever_groq(audio):
    for tentativa in range(3):
        with open(audio, "rb") as f:
            r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key('GROQ_API_KEY')}"},
                files={"file": (Path(audio).name, f, "audio/ogg")},
                data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json",
                      "timestamp_granularities[]": ["word", "segment"]}, timeout=900)
        if r.status_code < 500 and r.status_code != 429:
            break
        time.sleep(5 * (tentativa + 1))
    r.raise_for_status()
    return de_groq(r.json())

def transcrever_whisper_local(audio, modelo="turbo"):
    import whisper  # openai-whisper, já instalado na máquina
    m = whisper.load_model(modelo)
    res = m.transcribe(str(audio), word_timestamps=True)
    palavras = [{"t": w["word"], "ini": w["start"], "fim": w["end"]} for s in res["segments"] for w in s.get("words", [])]
    return {"idioma": res.get("language"), "provedor": f"whisper_local/{modelo}",
            "palavras": normalizar_palavras(palavras),
            "fins_segmento": sorted({round(float(s["end"]), 3) for s in res["segments"]})}

def transcrever_whisperx(audio, modelo="large-v3"):
    import whisperx, torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = whisperx.load_model(modelo, dev)
    res = m.transcribe(str(audio))
    al, meta = whisperx.load_align_model(language_code=res["language"], device=dev)
    res = whisperx.align(res["segments"], al, meta, str(audio), dev)
    palavras = [{"t": w["word"], "ini": w["start"], "fim": w["end"]} for s in res["segments"]
                for w in s.get("words", []) if "start" in w]
    return {"idioma": res.get("language"), "provedor": f"whisperx/{modelo}",
            "palavras": normalizar_palavras(palavras),
            "fins_segmento": sorted({round(float(s["end"]), 3) for s in res["segments"]})}

PROVEDORES = {"groq": lambda a, cfg: transcrever_groq(a),
              "whisper_local": lambda a, cfg: transcrever_whisper_local(a, cfg["modelos"]["whisper_local"]),
              "whisperx": lambda a, cfg: transcrever_whisperx(a)}
