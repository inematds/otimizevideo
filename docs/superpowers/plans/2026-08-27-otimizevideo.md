# otimizevideo — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI `otv` que condensa um vídeo de 20–30 min em ~2 min via transcrição → unidades cortáveis → pontuação por LLM (só ids) → seleção determinística → corte ffmpeg, com provedores trocáveis por `config.yaml`.

**Architecture:** Pipeline em fases, cada uma lê/escreve JSON numa pasta `trabalho/<id>/`; nenhuma fase conhece o provedor da outra. O núcleo (unidades + seleção + snap) é código puro e testado sem rede. Modelos entram em dois pontos apenas: pontuação (texto) e classificação visual (miniaturas), sempre por id, nunca por timestamp.

**Tech Stack:** Python 3.12, `requests`, `pyyaml`, `pytest`, `ffmpeg/ffprobe`, `yt-dlp`, `scenedetect[opencv]`, `mediapipe`; provedores: Groq (Whisper), OpenRouter (`z-ai/glm-5.3-flash`, `google/gemini-2.5-flash-lite`), Ollama local, inemavox (TTS chatterbox).

**Spec:** `docs/superpowers/specs/2026-08-27-otimizevideo-design.md`

## Global Constraints

- Keys **só** de `~/projetos/openpcbotv2/.env` e `~/projetos/wifi/.env`, lidas em runtime; nunca copiadas, logadas ou impressas.
- Todo JSON de fase segue os contratos da spec §3.1 (`metadata.json`, `transcript.json`, `unidades.json`, `scenes.json`, `notas.json`, `plan.json`).
- O LLM devolve **ids**, nunca timestamps; timestamps são sempre calculados pelo código.
- OpenRouter com modelos `z-ai/glm-5.*-flash`: sempre enviar `"reasoning": {"effort": "low"}` (reasoning não pode ser desligado) e `max_tokens ≥ 20000`.
- Timestamps de palavras são normalizados para monotônicos antes de qualquer uso (spec §11.4).
- `min_segmento_s` aplica-se **depois** do snap (spec §11.4).
- Saída final copiada para `~/projetos/output/otimizevideo/<id>/`; intermediários ficam em `trabalho/<id>/` (gitignored).
- Commits neste repo com autor `inematds <inematds@gmail.com>` (já configurado localmente). Commit ao fim de cada task.
- Testes unitários não acessam rede nem GPU; provedores externos só em testes marcados `@pytest.mark.integracao`.

---

## Estrutura de arquivos

```
otimizevideo/
  otv.py                       # CLI (argparse, subcomandos) — Task 11
  config.yaml                  # slots + parâmetros de seleção — Task 1
  requirements.txt             # Task 1
  pytest.ini                   # Task 1
  otv/
    __init__.py
    config.py                  # carregar_config() — Task 1
    contratos.py               # validação leve dos JSONs — Task 1
    util/keys.py               # key(nome) — Task 1
    util/ffmpeg.py             # probe(), extrair_audio(), thumb(), run() — Task 2
    util/custos.py             # registrar(dir, fase, dados) — Task 2
    fases/ingest.py            # Task 2
    fases/transcrever.py       # Task 3
    fases/unidades.py          # Task 4
    fases/cenas.py             # detecção + rosto + classificação — Task 5
    fases/pontuar.py           # Task 7
    fases/selecionar.py        # Task 8 (núcleo)
    fases/render.py            # Task 9
    fases/narrar.py            # Task 10
    provedores/transcricao.py  # groq, whisper_local, whisperx — Task 3
    provedores/llm.py          # OpenRouter e Ollama, chat_json() — Task 6
    provedores/tts.py          # inemavox, elevenlabs — Task 10
  prompts/pontuar.md  prompts/classificar.md  prompts/narrar.md
  tests/  (fixtures em tests/fixtures/)
```

---

### Task 1: Esqueleto, config, keys e contratos

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `config.yaml`, `otv/__init__.py`, `otv/config.py`, `otv/util/__init__.py`, `otv/util/keys.py`, `otv/contratos.py`
- Test: `tests/test_config.py`, `tests/test_keys.py`, `tests/test_contratos.py`

**Interfaces:**
- Produces: `carregar_config(path: Path|None = None) -> dict` (merge de defaults + yaml); `key(nome: str) -> str` (levanta `KeyError` se não achar); `validar_notas(raw: dict, n_unidades: int) -> dict` (retorna `{"topicos": [...], "notas": [...], "gancho": [...]}` limpos); `validar_plan(plan: dict) -> None` (levanta `ValueError`).

- [ ] **Step 1: Arquivos de base**

`requirements.txt`:
```
requests>=2.31
pyyaml>=6
pytest>=8
yt-dlp
scenedetect[opencv]>=0.6.4
mediapipe>=0.10
```
`pytest.ini`:
```ini
[pytest]
testpaths = tests
markers =
    integracao: precisa de rede/GPU/serviços externos (rodar com -m integracao)
addopts = -m "not integracao"
```
`config.yaml`:
```yaml
transcricao: groq          # groq | whisper_local | whisperx
visual: local              # local | glm | gemini
pontuacao: glm             # glm | gemini | ollama
tts: inemavox              # inemavox | elevenlabs
modelos:
  glm: z-ai/glm-5.3-flash
  gemini: google/gemini-2.5-flash-lite
  ollama: qwen3.8:27b
  whisper_local: turbo
openrouter:
  reasoning_effort: low
  max_tokens: 20000
selecao:
  alvo_s: 120
  tolerancia: 0.25
  min_segmento_s: 3
  min_segmento_ideal_s: 8
  pausa_fronteira_ms: 400
  folga_ms: 120
  cota_topico_pct: 40
  nota_minima: 5
saida: ~/projetos/output/otimizevideo
trabalho: trabalho
```
Instalar: `pip install -r requirements.txt`.

- [ ] **Step 2: Teste de config e keys (falhando)**

`tests/test_config.py`:
```python
from pathlib import Path
from otv.config import carregar_config

def test_defaults_sem_arquivo(tmp_path):
    cfg = carregar_config(tmp_path / "nao_existe.yaml")
    assert cfg["selecao"]["alvo_s"] == 120
    assert cfg["pontuacao"] == "glm"

def test_yaml_sobrescreve(tmp_path):
    (tmp_path / "c.yaml").write_text("pontuacao: ollama\nselecao:\n  alvo_s: 90\n")
    cfg = carregar_config(tmp_path / "c.yaml")
    assert cfg["pontuacao"] == "ollama"
    assert cfg["selecao"]["alvo_s"] == 90
    assert cfg["selecao"]["nota_minima"] == 5   # default preservado no merge
```
`tests/test_keys.py`:
```python
import pytest
from otv.util import keys

def test_key_le_dos_arquivos(tmp_path, monkeypatch):
    f = tmp_path / ".env"; f.write_text('FOO_KEY="abc"\nBAR=1\n')
    monkeypatch.setattr(keys, "ARQUIVOS", [f])
    assert keys.key("FOO_KEY") == "abc"

def test_key_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "ARQUIVOS", [tmp_path / "x.env"])
    with pytest.raises(KeyError):
        keys.key("NADA")
```

- [ ] **Step 3: Rodar — deve falhar com ModuleNotFoundError**

Run: `pytest tests/test_config.py tests/test_keys.py -v`

- [ ] **Step 4: Implementar**

`otv/config.py`:
```python
from pathlib import Path
import copy, yaml

DEFAULTS = {
    "transcricao": "groq", "visual": "local", "pontuacao": "glm", "tts": "inemavox",
    "modelos": {"glm": "z-ai/glm-5.3-flash", "gemini": "google/gemini-2.5-flash-lite",
                "ollama": "qwen3.8:27b", "whisper_local": "turbo"},
    "openrouter": {"reasoning_effort": "low", "max_tokens": 20000},
    "selecao": {"alvo_s": 120, "tolerancia": 0.25, "min_segmento_s": 3, "min_segmento_ideal_s": 8,
                "pausa_fronteira_ms": 400, "folga_ms": 120, "cota_topico_pct": 40, "nota_minima": 5},
    "saida": "~/projetos/output/otimizevideo", "trabalho": "trabalho",
}

def _merge(base, novo):
    out = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def carregar_config(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.yaml"
    dados = yaml.safe_load(path.read_text()) if path.exists() else {}
    return _merge(DEFAULTS, dados)
```
`otv/util/keys.py`:
```python
from pathlib import Path
ARQUIVOS = [Path.home() / "projetos/openpcbotv2/.env", Path.home() / "projetos/wifi/.env"]

def key(nome):
    for f in ARQUIVOS:
        if not f.exists():
            continue
        for ln in f.read_text().splitlines():
            if ln.startswith(nome + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeyError(f"{nome} não encontrada em {[str(a) for a in ARQUIVOS]}")
```

- [ ] **Step 5: Teste de contratos (falhando)**

`tests/test_contratos.py`:
```python
import pytest
from otv.contratos import validar_notas, validar_plan

def test_validar_notas_limpa_ids_invalidos_e_completa_faltantes():
    raw = {"topicos": [{"nome": "a", "de": 0, "ate": 2}],
           "notas": [{"id": 0, "nota": 9, "motivo": "x"}, {"id": 7, "nota": 5}, {"id": "1", "nota": "11"}],
           "gancho": [0, 99]}
    n = validar_notas(raw, 3)
    assert {x["id"]: x["nota"] for x in n["notas"]} == {0: 9, 1: 10, 2: 0}
    assert n["gancho"] == [0]
    assert n["topicos"] == [{"nome": "a", "de": 0, "ate": 2}]

def test_validar_notas_sem_notas_falha():
    with pytest.raises(ValueError):
        validar_notas({"topicos": []}, 3)

def test_validar_plan_ok_e_erro():
    validar_plan({"modo": "A", "alvo_s": 120, "total_s": 5.0,
                  "segmentos": [{"in": 1.0, "out": 6.0, "unidades": [0]}], "narracao": None})
    with pytest.raises(ValueError):
        validar_plan({"modo": "A", "segmentos": [{"in": 6.0, "out": 1.0, "unidades": [0]}]})
```

- [ ] **Step 6: Implementar `otv/contratos.py`**

```python
def validar_notas(raw, n_unidades):
    if not isinstance(raw, dict) or not isinstance(raw.get("notas"), list) or not raw["notas"]:
        raise ValueError("notas.json sem lista 'notas'")
    por_id = {}
    for n in raw["notas"]:
        try:
            i = int(n["id"]); v = int(float(n["nota"]))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n_unidades:
            por_id[i] = {"id": i, "nota": max(0, min(10, v)), "motivo": str(n.get("motivo", ""))[:80]}
    notas = [por_id.get(i, {"id": i, "nota": 0, "motivo": "sem nota"}) for i in range(n_unidades)]
    topicos = []
    for t in raw.get("topicos") or []:
        try:
            de, ate = int(t["de"]), int(t["ate"])
        except (KeyError, TypeError, ValueError):
            continue
        de, ate = max(0, de), min(n_unidades - 1, ate)
        if de <= ate:
            topicos.append({"nome": str(t.get("nome", "?"))[:60], "de": de, "ate": ate})
    gancho = [int(g) for g in (raw.get("gancho") or []) if str(g).lstrip("-").isdigit() and 0 <= int(g) < n_unidades][:2]
    return {"topicos": topicos, "notas": notas, "gancho": gancho}

def validar_plan(plan):
    if plan.get("modo") not in ("A", "B", "C"):
        raise ValueError("modo inválido")
    for s in plan.get("segmentos", []):
        if not (0 <= s["in"] < s["out"]):
            raise ValueError(f"segmento inválido: {s}")
        if not s.get("unidades"):
            raise ValueError(f"segmento sem unidades: {s}")
```

- [ ] **Step 7: Rodar tudo — PASS**

Run: `pytest -v`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini config.yaml otv tests
git commit -m "feat: esqueleto, config, keys e contratos"
```

---

### Task 2: Ingest (yt-dlp / arquivo local, ffprobe, áudio opus)

**Files:**
- Create: `otv/util/ffmpeg.py`, `otv/util/custos.py`, `otv/fases/__init__.py`, `otv/fases/ingest.py`
- Test: `tests/test_ffmpeg_util.py`, `tests/test_ingest.py`

**Interfaces:**
- Produces: `probe(video: Path) -> dict{duracao_s, fps, largura, altura}`; `extrair_audio(video, out, kbps=32)`; `thumb(video, t, out, largura=512)`; `run(cmd: list[str])` (levanta `RuntimeError` com stderr); `registrar(dir, fase, dados: dict)` (append em `custos.json`); `ingest(fonte: str, raiz: Path) -> Path` (pasta `raiz/<id>` com `video.mp4`, `audio.opus`, `metadata.json`); `id_de(fonte) -> str`.

- [ ] **Step 1: Teste do util ffmpeg com vídeo sintético (falhando)**

`tests/conftest.py`:
```python
import subprocess, pytest
from pathlib import Path

@pytest.fixture(scope="session")
def video_teste(tmp_path_factory):
    p = tmp_path_factory.mktemp("v") / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-c:a", "aac", str(p)], check=True)
    return p
```
`tests/test_ffmpeg_util.py`:
```python
from otv.util.ffmpeg import probe, extrair_audio, thumb

def test_probe(video_teste):
    m = probe(video_teste)
    assert abs(m["duracao_s"] - 6) < 0.2 and m["largura"] == 320 and m["fps"] == 25

def test_extrair_audio_e_thumb(video_teste, tmp_path):
    extrair_audio(video_teste, tmp_path / "a.opus")
    thumb(video_teste, 1.0, tmp_path / "t.jpg")
    assert (tmp_path / "a.opus").stat().st_size > 1000
    assert (tmp_path / "t.jpg").stat().st_size > 500
```

- [ ] **Step 2: Rodar — falha (módulo inexistente)**

Run: `pytest tests/test_ffmpeg_util.py -v`

- [ ] **Step 3: Implementar `otv/util/ffmpeg.py` e `otv/util/custos.py`**

```python
# otv/util/ffmpeg.py
import json, subprocess
from pathlib import Path

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falhou: {r.stderr[-800:]}")
    return r.stdout

def probe(video):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)])
    j = json.loads(out); s = j["streams"][0]; num, den = s["r_frame_rate"].split("/")
    return {"duracao_s": float(j["format"]["duration"]), "fps": round(int(num) / int(den), 3),
            "largura": s["width"], "altura": s["height"]}

def extrair_audio(video, out, kbps=32):
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-c:a", "libopus", "-b:a", f"{kbps}k", str(out)])

def thumb(video, t, out, largura=512):
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={largura}:-2", "-q:v", "3", str(out)])
```
```python
# otv/util/custos.py
import json, time
from pathlib import Path

def registrar(dir, fase, dados):
    p = Path(dir) / "custos.json"
    atual = json.loads(p.read_text()) if p.exists() else {}
    atual[fase] = {**dados, "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p.write_text(json.dumps(atual, ensure_ascii=False, indent=1))
```

- [ ] **Step 4: Teste do ingest local (falhando)**

`tests/test_ingest.py`:
```python
import json
from otv.fases.ingest import ingest, id_de

def test_id_de():
    assert id_de("https://www.youtube.com/watch?v=dQYKcjvXhIY") == "dQYKcjvXhIY"
    assert id_de("https://youtu.be/abc123XYZ_-") == "abc123XYZ_-"
    assert id_de("/x/Minha Aula 01.mp4") == "minha-aula-01"

def test_ingest_arquivo_local(video_teste, tmp_path):
    d = ingest(str(video_teste), tmp_path)
    m = json.loads((d / "metadata.json").read_text())
    assert (d / "video.mp4").exists() and (d / "audio.opus").exists()
    assert abs(m["duracao_s"] - 6) < 0.2 and m["fonte"] == str(video_teste)
```

- [ ] **Step 5: Implementar `otv/fases/ingest.py`**

```python
import json, re, shutil, time, subprocess
from pathlib import Path
from otv.util.ffmpeg import probe, extrair_audio, run
from otv.util.custos import registrar

def id_de(fonte):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", fonte)
    if m:
        return m.group(1)
    nome = Path(fonte).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", nome).strip("-")[:40]

def ingest(fonte, raiz, forcar=False):
    d = Path(raiz) / id_de(fonte); d.mkdir(parents=True, exist_ok=True)
    video = d / "video.mp4"; t0 = time.time()
    if not video.exists() or forcar:
        if fonte.startswith("http"):
            run(["yt-dlp", "-q", "--no-warnings", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]",
                 "--merge-output-format", "mp4", "-o", str(video), fonte])
        else:
            shutil.copy(fonte, video)
    if not (d / "audio.opus").exists() or forcar:
        extrair_audio(video, d / "audio.opus")
    titulo = Path(fonte).stem
    if fonte.startswith("http"):
        titulo = run(["yt-dlp", "--skip-download", "--print", "%(title)s", fonte]).strip() or titulo
    meta = {"id": d.name, "fonte": fonte, "titulo": titulo, **probe(video),
            "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (d / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    registrar(d, "ingest", {"segundos": round(time.time() - t0, 1)})
    return d
```

- [ ] **Step 6: Rodar — PASS**

Run: `pytest tests/test_ffmpeg_util.py tests/test_ingest.py -v`

- [ ] **Step 7: Commit**

```bash
git add otv tests && git commit -m "feat: ingest (yt-dlp/local), util ffmpeg e custos"
```

---

### Task 3: Transcrição (Groq, whisper local) com normalização de timestamps

**Files:**
- Create: `otv/provedores/__init__.py`, `otv/provedores/transcricao.py`, `otv/fases/transcrever.py`
- Test: `tests/test_transcricao.py`, fixture `tests/fixtures/groq_resp.json`

**Interfaces:**
- Consumes: `key()`, `registrar()`.
- Produces: `normalizar_palavras(palavras: list[dict]) -> list[dict]`; `de_groq(resp: dict) -> dict` (transcript no contrato); `transcrever_groq(audio: Path) -> dict`; `transcrever_whisper_local(audio: Path, modelo: str) -> dict`; `transcrever(dir: Path, cfg: dict, provedor: str|None = None, forcar=False) -> Path` (escreve `transcript.json`). Contrato: `{"idioma", "provedor", "palavras": [{"t","ini","fim"}], "fins_segmento": [float]}`.

- [ ] **Step 1: Fixture e teste (falhando)**

`tests/fixtures/groq_resp.json`:
```json
{"language": "en", "text": "Hello world. Second one.",
 "words": [{"word": "Hello", "start": 0.0, "end": 0.5}, {"word": "world.", "start": 0.4, "end": 0.9},
           {"word": "Second", "start": 1.5, "end": 1.9}, {"word": "one.", "start": 1.85, "end": 1.7}],
 "segments": [{"start": 0.0, "end": 0.9}, {"start": 1.5, "end": 2.1}]}
```
`tests/test_transcricao.py`:
```python
import json
from pathlib import Path
from otv.provedores.transcricao import normalizar_palavras, de_groq

def test_normalizar_torna_monotonico():
    p = normalizar_palavras([{"t": "a", "ini": 0.0, "fim": 0.5}, {"t": "b", "ini": 0.4, "fim": 0.9},
                             {"t": "c", "ini": 1.85, "fim": 1.7}])
    assert p[1]["ini"] == 0.5                 # não começa antes da anterior terminar
    assert p[2]["fim"] >= p[2]["ini"] + 0.05  # fim nunca antes do início

def test_de_groq_contrato():
    t = de_groq(json.loads(Path("tests/fixtures/groq_resp.json").read_text()))
    assert t["idioma"] == "en" and t["provedor"] == "groq/whisper-large-v3-turbo"
    assert [w["t"] for w in t["palavras"]] == ["Hello", "world.", "Second", "one."]
    assert t["fins_segmento"] == [0.9, 2.1]
    assert t["palavras"][1]["ini"] == 0.5
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_transcricao.py -v`

- [ ] **Step 3: Implementar `otv/provedores/transcricao.py`**

```python
import json, time, requests
from pathlib import Path
from otv.util.keys import key

def normalizar_palavras(palavras):
    out = []; fim_ant = 0.0
    for w in palavras:
        ini = max(float(w["ini"]), fim_ant)
        fim = max(float(w["fim"]), ini + 0.05)
        out.append({"t": str(w["t"]).strip(), "ini": round(ini, 3), "fim": round(fim, 3)})
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
```

- [ ] **Step 4: Implementar `otv/fases/transcrever.py`**

```python
import json, time
from pathlib import Path
from otv.provedores.transcricao import PROVEDORES
from otv.util.custos import registrar

def transcrever(dir, cfg, provedor=None, forcar=False):
    dir = Path(dir); out = dir / "transcript.json"
    if out.exists() and not forcar:
        return out
    prov = provedor or cfg["transcricao"]; t0 = time.time()
    t = PROVEDORES[prov](dir / "audio.opus", cfg)
    if len(t["palavras"]) < 50:
        raise RuntimeError(f"transcrição com só {len(t['palavras'])} palavras — vídeo sem fala? (só modo C faz sentido)")
    out.write_text(json.dumps(t, ensure_ascii=False))
    registrar(dir, "transcrever", {"provedor": prov, "palavras": len(t["palavras"]), "segundos": round(time.time() - t0, 1)})
    return out
```

- [ ] **Step 5: Rodar — PASS; e teste de integração manual**

Run: `pytest tests/test_transcricao.py -v`
Integração (opcional, rede): `python -c "from otv.fases.transcrever import transcrever; from otv.config import carregar_config; print(transcrever('trabalho/dQYKcjvXhIY', carregar_config(), forcar=True))"` → `transcript.json` com ~3000 palavras.

- [ ] **Step 6: Commit**

```bash
git add otv tests && git commit -m "feat: transcrição groq/whisper com normalização de timestamps"
```

---

### Task 4: Unidades cortáveis

**Files:**
- Create: `otv/fases/unidades.py`
- Test: `tests/test_unidades.py`

**Interfaces:**
- Consumes: `transcript.json`.
- Produces: `montar_unidades(palavras, fins_segmento, pausa_s=0.4, max_dur_s=12.0) -> list[dict{id,ini,fim,dur,texto}]`; `atribuir_cenas(unidades, cenas) -> list` (preenche `cena` e `visual`; sem cenas → `cena=None, visual="outro"`); `unidades(dir, cfg, forcar=False) -> Path`.

- [ ] **Step 1: Testes (falhando)**

`tests/test_unidades.py`:
```python
from otv.fases.unidades import montar_unidades, atribuir_cenas

def P(t, ini, fim): return {"t": t, "ini": ini, "fim": fim}

def test_quebra_em_pontuacao_e_pausa():
    pal = [P("Oi", 0, .3), P("tudo", .35, .6), P("bem.", .65, .9),      # frase 1 (pontuação)
           P("Sim", 1.0, 1.3), P("claro", 1.35, 1.7),                    # frase 2 (pausa de 0.6 depois)
           P("vamos", 2.3, 2.6), P("lá", 2.65, 2.9), P("agora", 2.95, 3.3)]
    u = montar_unidades(pal, [], pausa_s=0.4)
    assert [x["texto"] for x in u] == ["Oi tudo bem.", "Sim claro", "vamos lá agora"]
    assert u[0]["ini"] == 0 and u[0]["fim"] == .9 and u[0]["id"] == 0 and u[2]["id"] == 2

def test_funde_unidade_curta_na_anterior():
    pal = [P("Primeira", 0, .5), P("frase.", .55, 1.0), P("Ok.", 1.1, 1.3)]
    u = montar_unidades(pal, [])
    assert len(u) == 1 and u[0]["texto"] == "Primeira frase. Ok." and u[0]["fim"] == 1.3

def test_corta_unidade_longa_na_maior_pausa():
    pal = [P(f"p{i}", i * 1.0, i * 1.0 + 0.7) for i in range(15)]  # 15 s sem pontuação, pausas iguais de 0.3
    pal[7]["fim"] = 7.55                                              # pausa maior (0.45) depois de p7 — abaixo de 0.4? não: usa fim_segmento
    u = montar_unidades(pal, fins_segmento=[7.55], pausa_s=0.6)
    assert len(u) == 2 and u[0]["texto"].endswith("p7")

def test_atribuir_cenas():
    u = [{"id": 0, "ini": 0, "fim": 2, "dur": 2, "texto": "a"}, {"id": 1, "ini": 5, "fim": 7, "dur": 2, "texto": "b"}]
    cenas = [{"id": 0, "ini": 0, "fim": 4, "visual": "talking_head"}, {"id": 1, "ini": 4, "fim": 9, "visual": "slide"}]
    r = atribuir_cenas(u, cenas)
    assert [x["visual"] for x in r] == ["talking_head", "slide"] and r[1]["cena"] == 1
    assert atribuir_cenas(u, [])[0]["visual"] == "outro"
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_unidades.py -v`

- [ ] **Step 3: Implementar `otv/fases/unidades.py`**

```python
import json, re, time
from pathlib import Path
from otv.util.custos import registrar

def montar_unidades(palavras, fins_segmento, pausa_s=0.4, max_dur_s=12.0):
    fins = set(round(float(f), 3) for f in fins_segmento)
    brutas = []; cur = []
    def fechar():
        if cur:
            brutas.append({"ini": cur[0]["ini"], "fim": cur[-1]["fim"], "texto": " ".join(w["t"] for w in cur)})
            cur.clear()
    for i, w in enumerate(palavras):
        cur.append(w)
        nxt = palavras[i + 1] if i + 1 < len(palavras) else None
        pausa = (nxt["ini"] - w["fim"]) if nxt else 99
        fim_frase = bool(re.search(r"[.!?]$", w["t"])) or round(w["fim"], 3) in fins
        longa = (w["fim"] - cur[0]["ini"]) >= max_dur_s
        if fim_frase or pausa >= pausa_s or (longa and pausa >= 0.15):
            fechar()
    fechar()
    unidades = []
    for u in brutas:
        curta = (u["fim"] - u["ini"]) < 0.8 or len(u["texto"].split()) < 3
        if unidades and curta:
            unidades[-1]["fim"] = u["fim"]; unidades[-1]["texto"] += " " + u["texto"]
        else:
            unidades.append(u)
    for k, u in enumerate(unidades):
        u["id"] = k; u["dur"] = round(u["fim"] - u["ini"], 2); u.setdefault("cena", None); u.setdefault("visual", "outro")
    return unidades

def atribuir_cenas(unidades, cenas):
    for u in unidades:
        meio = (u["ini"] + u["fim"]) / 2
        c = next((c for c in cenas if c["ini"] <= meio < c["fim"]), None)
        u["cena"] = c["id"] if c else None
        u["visual"] = c.get("visual", "outro") if c else "outro"
    return unidades

def unidades(dir, cfg, forcar=False):
    dir = Path(dir); out = dir / "unidades.json"
    if out.exists() and not forcar:
        return out
    t = json.loads((dir / "transcript.json").read_text())
    us = montar_unidades(t["palavras"], t.get("fins_segmento", []),
                         pausa_s=cfg["selecao"]["pausa_fronteira_ms"] / 1000)
    sc = dir / "scenes.json"
    if sc.exists():
        atribuir_cenas(us, json.loads(sc.read_text())["cenas"])
    out.write_text(json.dumps({"unidades": us}, ensure_ascii=False))
    registrar(dir, "unidades", {"quantidade": len(us), "media_s": round(sum(u["dur"] for u in us) / max(1, len(us)), 2)})
    return out
```
Se `test_corta_unidade_longa_na_maior_pausa` falhar por causa da regra `longa and pausa >= 0.15`, ajuste a fixture (a intenção do teste é: com `fins_segmento` marcando 7.55, a unidade quebra ali).

- [ ] **Step 4: Rodar — PASS**

Run: `pytest tests/test_unidades.py -v`

- [ ] **Step 5: Commit**

```bash
git add otv tests && git commit -m "feat: unidades cortáveis a partir de palavras e pausas"
```

---

### Task 5: Cenas (PySceneDetect + rosto local) e classificação por VLM

**Files:**
- Create: `otv/fases/cenas.py`, `prompts/classificar.md`
- Modify: `otv/provedores/llm.py` (criado na Task 6 — **executar a Task 6 antes desta**, ou implementar só a parte local aqui e voltar na classificação)
- Test: `tests/test_cenas.py`

**Interfaces:**
- Produces: `detectar_cenas(video: Path) -> list[tuple[float,float]]`; `rosto_pct(jpg: Path) -> float`; `classificar_local(rosto: float) -> str` (`talking_head` se ≥ 0.08, senão `outro`); `cenas(dir, cfg, forcar=False) -> Path` (escreve `scenes.json` + `thumbs/NNN.jpg`); `classificar(dir, cfg, provedor=None) -> Path` (enriquece `scenes.json` com `visual` e `descricao` via VLM em lotes de 20 imagens).

- [ ] **Step 1: Teste local (falhando)**

`tests/test_cenas.py`:
```python
import subprocess
from otv.fases.cenas import detectar_cenas, classificar_local, rosto_pct

def test_detecta_corte_duro(tmp_path):
    p = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=25:duration=3",
        "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=25:duration=3",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", str(p)], check=True)
    c = detectar_cenas(p)
    assert len(c) == 2 and abs(c[1][0] - 3.0) < 0.2

def test_classificar_local():
    assert classificar_local(0.2) == "talking_head" and classificar_local(0.01) == "outro"

def test_rosto_pct_em_imagem_sem_rosto(tmp_path):
    p = tmp_path / "x.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:size=320x240", "-frames:v", "1", str(p)], check=True)
    assert rosto_pct(p) == 0.0
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_cenas.py -v`

- [ ] **Step 3: Implementar `otv/fases/cenas.py` (parte local)**

```python
import json, time
from pathlib import Path
from otv.util.ffmpeg import thumb, probe
from otv.util.custos import registrar

def detectar_cenas(video):
    from scenedetect import detect, AdaptiveDetector
    lista = detect(str(video), AdaptiveDetector())
    if not lista:
        return [(0.0, probe(video)["duracao_s"])]
    return [(s.get_seconds(), e.get_seconds()) for s, e in lista]

_det = None
def rosto_pct(jpg):
    global _det
    import mediapipe as mp, cv2
    if _det is None:
        _det = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    img = cv2.cvtColor(cv2.imread(str(jpg)), cv2.COLOR_BGR2RGB)
    res = _det.process(img)
    if not res.detections:
        return 0.0
    bb = max(res.detections, key=lambda d: d.location_data.relative_bounding_box.width).location_data.relative_bounding_box
    return round(max(0.0, bb.width) * max(0.0, bb.height), 4)

def classificar_local(rosto):
    return "talking_head" if rosto >= 0.08 else "outro"

def cenas(dir, cfg, forcar=False):
    dir = Path(dir); out = dir / "scenes.json"
    if out.exists() and not forcar:
        return out
    t0 = time.time(); (dir / "thumbs").mkdir(exist_ok=True); lista = []
    for i, (ini, fim) in enumerate(detectar_cenas(dir / "video.mp4")):
        jpg = dir / "thumbs" / f"{i:03d}.jpg"
        thumb(dir / "video.mp4", ini + min(1.0, (fim - ini) / 2), jpg)
        r = rosto_pct(jpg)
        lista.append({"id": i, "ini": round(ini, 3), "fim": round(fim, 3), "thumb": f"thumbs/{i:03d}.jpg",
                      "rosto_pct": r, "visual": classificar_local(r), "descricao": None})
    out.write_text(json.dumps({"cenas": lista}, ensure_ascii=False, indent=0))
    registrar(dir, "cenas", {"quantidade": len(lista), "segundos": round(time.time() - t0, 1)})
    return out
```
Se o `mediapipe` instalado for a API nova (`mediapipe.tasks`), adaptar `rosto_pct` para `vision.FaceDetector` com o modelo `blaze_face_short_range.tflite` baixado para `otv/modelos/`; a assinatura e o retorno não mudam.

- [ ] **Step 4: Rodar — PASS**

Run: `pytest tests/test_cenas.py -v`

- [ ] **Step 5: Classificação por VLM (depende da Task 6)**

`prompts/classificar.md`:
```
Você recebe {n} imagens numeradas, uma por cena de um vídeo educativo.
Classifique CADA imagem em exatamente uma categoria:
- talking_head: pessoa falando para a câmera ocupa a cena
- slide: slide de apresentação (título, bullets, texto grande)
- demo_tela: gravação de tela, software, terminal, site, código
- grafico: gráfico, tabela, diagrama, dado visual
- outro: qualquer outra coisa (b-roll, logo, transição)
Descreva em até 8 palavras o que aparece.
Responda SOMENTE JSON: {"cenas":[{"i":0,"visual":"slide","descricao":"..."}, ...]} com todas as {n} imagens.
```
Acrescentar em `otv/fases/cenas.py`:
```python
def classificar(dir, cfg, provedor=None, forcar=False):
    from otv.provedores.llm import criar_llm
    dir = Path(dir); sc = json.loads((dir / "scenes.json").read_text()); lista = sc["cenas"]
    if all(c.get("descricao") for c in lista) and not forcar:
        return dir / "scenes.json"
    llm = criar_llm(cfg, provedor or cfg["visual"]); t0 = time.time(); uso_total = {}
    tpl = (Path(__file__).resolve().parents[2] / "prompts/classificar.md").read_text()
    for k in range(0, len(lista), 20):
        lote = lista[k:k + 20]
        resp, uso = llm.chat_json(tpl.format(n=len(lote)), imagens=[dir / c["thumb"] for c in lote])
        for r in resp.get("cenas", []):
            i = int(r.get("i", -1))
            if 0 <= i < len(lote) and r.get("visual") in ("talking_head", "slide", "demo_tela", "grafico", "outro"):
                c = lote[i]
                c["visual"] = "talking_head" if c["rosto_pct"] >= 0.15 else r["visual"]  # rosto grande vence
                c["descricao"] = str(r.get("descricao", ""))[:80]
        for kk, v in (uso or {}).items():
            if isinstance(v, (int, float)): uso_total[kk] = uso_total.get(kk, 0) + v
    (dir / "scenes.json").write_text(json.dumps(sc, ensure_ascii=False, indent=0))
    registrar(dir, "classificar", {"provedor": llm.nome, "uso": uso_total, "segundos": round(time.time() - t0, 1)})
    return dir / "scenes.json"
```

- [ ] **Step 6: Integração manual**

Run: `python -c "from otv.fases.cenas import cenas, classificar; from otv.config import carregar_config; c=carregar_config(); cenas('trabalho/dQYKcjvXhIY', c); classificar('trabalho/dQYKcjvXhIY', c, 'glm')"` e conferir `scenes.json`: cenas com `visual` variado e `descricao` preenchida.

- [ ] **Step 7: Commit**

```bash
git add otv prompts tests && git commit -m "feat: cenas (PySceneDetect + rosto) e classificação visual por VLM"
```

---

### Task 6: Provedor LLM (OpenRouter e Ollama) com `chat_json`

**Files:**
- Create: `otv/provedores/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `class LLM` com `.nome: str` e `.chat_json(prompt: str, imagens: list[Path]|None = None) -> tuple[dict, dict]` (resposta JSON parseada, `usage`); `criar_llm(cfg, slot: str) -> LLM` onde `slot ∈ {glm, gemini, ollama}`; `extrair_json(texto: str) -> dict` (tolera cercas ```json e texto em volta).

- [ ] **Step 1: Testes (falhando) — sem rede, com `requests.post` mockado**

`tests/test_llm.py`:
```python
import json, pytest
from otv.provedores import llm as L

def test_extrair_json_tolerante():
    assert L.extrair_json('```json\n{"a":1}\n```') == {"a": 1}
    assert L.extrair_json('bla {"a": [1,2]} fim') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        L.extrair_json("nada aqui")

def test_openrouter_manda_reasoning_low_e_retorna_json(monkeypatch):
    chamadas = []
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": '{"ok":1}'}}], "usage": {"cost": 0.001}}
        def raise_for_status(self): pass
    def fake_post(url, headers=None, json=None, timeout=None):
        chamadas.append(json); return R()
    monkeypatch.setattr(L.requests, "post", fake_post)
    monkeypatch.setattr(L, "key", lambda n: "k")
    m = L.OpenRouter("z-ai/glm-5.3-flash", effort="low", max_tokens=20000)
    resp, uso = m.chat_json("oi")
    assert resp == {"ok": 1} and uso["cost"] == 0.001
    assert chamadas[0]["reasoning"] == {"effort": "low"} and chamadas[0]["max_tokens"] == 20000
    assert chamadas[0]["response_format"] == {"type": "json_object"}

def test_retry_em_json_invalido(monkeypatch):
    respostas = iter(['isso não é json', '{"ok":2}'])
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": next(respostas)}}], "usage": {}}
        def raise_for_status(self): pass
    monkeypatch.setattr(L.requests, "post", lambda *a, **k: R())
    monkeypatch.setattr(L, "key", lambda n: "k")
    resp, _ = L.OpenRouter("x").chat_json("oi")
    assert resp == {"ok": 2}

def test_criar_llm_slots():
    cfg = {"modelos": {"glm": "z-ai/glm-5.3-flash", "gemini": "g", "ollama": "q"}, "openrouter": {"reasoning_effort": "low", "max_tokens": 1}}
    assert L.criar_llm(cfg, "glm").nome == "openrouter/z-ai/glm-5.3-flash"
    assert L.criar_llm(cfg, "ollama").nome == "ollama/q"
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_llm.py -v`

- [ ] **Step 3: Implementar `otv/provedores/llm.py`**

```python
import base64, json, re, time, requests
from pathlib import Path
from otv.util.keys import key

def extrair_json(texto):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError("resposta sem JSON válido: " + texto[:200])

def _img_b64(p):
    return "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()

class LLM:
    nome = "?"
    def _chamar(self, prompt, imagens):  # -> (texto, usage)
        raise NotImplementedError
    def chat_json(self, prompt, imagens=None):
        erro = None
        for tentativa in range(2):
            texto, uso = self._chamar(prompt if tentativa == 0 else prompt + "\n\nATENÇÃO: sua resposta anterior não era JSON válido. Responda SOMENTE o JSON.", imagens)
            try:
                return extrair_json(texto), uso
            except ValueError as e:
                erro = e
        raise erro

class OpenRouter(LLM):
    def __init__(self, modelo, effort="low", max_tokens=20000):
        self.modelo, self.effort, self.max_tokens = modelo, effort, max_tokens
        self.nome = f"openrouter/{modelo}"
    def _chamar(self, prompt, imagens):
        conteudo = [{"type": "text", "text": prompt}]
        for i, p in enumerate(imagens or []):
            conteudo.append({"type": "text", "text": f"imagem {i}:"})
            conteudo.append({"type": "image_url", "image_url": {"url": _img_b64(p)}})
        corpo = {"model": self.modelo, "temperature": 0.2, "max_tokens": self.max_tokens,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "user", "content": conteudo if imagens else prompt}]}
        if self.effort:
            corpo["reasoning"] = {"effort": self.effort}
        for tentativa in range(3):
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"}, json=corpo, timeout=600)
            if r.status_code < 500 and r.status_code != 429:
                break
            time.sleep(5 * (tentativa + 1))
        r.raise_for_status(); j = r.json()
        return j["choices"][0]["message"]["content"], j.get("usage", {})

class Ollama(LLM):
    def __init__(self, modelo, host="http://localhost:11434"):
        self.modelo, self.host, self.nome = modelo, host, f"ollama/{modelo}"
    def _chamar(self, prompt, imagens):
        msg = {"role": "user", "content": prompt}
        if imagens:
            msg["images"] = [base64.b64encode(Path(p).read_bytes()).decode() for p in imagens]
        r = requests.post(f"{self.host}/api/chat", json={"model": self.modelo, "stream": False, "format": "json",
            "think": False, "options": {"num_ctx": 32768, "temperature": 0.2}, "messages": [msg]}, timeout=3600)
        r.raise_for_status(); j = r.json()
        return j["message"]["content"], {"prompt_tokens": j.get("prompt_eval_count"), "completion_tokens": j.get("eval_count")}

def criar_llm(cfg, slot):
    modelo = cfg["modelos"][slot]
    if slot == "ollama":
        return Ollama(modelo)
    o = cfg.get("openrouter", {})
    effort = o.get("reasoning_effort", "low") if "glm" in modelo else None
    return OpenRouter(modelo, effort=effort, max_tokens=o.get("max_tokens", 20000))
```

- [ ] **Step 4: Rodar — PASS**

Run: `pytest tests/test_llm.py -v`

- [ ] **Step 5: Commit**

```bash
git add otv tests && git commit -m "feat: provedor LLM (OpenRouter/Ollama) com chat_json e retry"
```

---

### Task 7: Pontuação (prompt, validação, fase)

**Files:**
- Create: `prompts/pontuar.md`, `otv/fases/pontuar.py`
- Test: `tests/test_pontuar.py`

**Interfaces:**
- Consumes: `criar_llm`, `validar_notas`, `unidades.json`, `metadata.json`.
- Produces: `montar_lista(unidades) -> str` (formato `[017] 6.2s slide "texto"`); `montar_prompt(unidades, modo, alvo_s, titulo, duracao_s) -> str`; `pontuar(dir, cfg, modo="A", alvo_s=None, provedor=None, forcar=False) -> Path` (escreve `notas.json` = saída de `validar_notas` + `provedor` + `uso`).

- [ ] **Step 1: `prompts/pontuar.md`**

```
Você é um editor de vídeo experiente. Abaixo está a transcrição de um vídeo de {minutos} minutos ("{titulo}"),
dividida em unidades numeradas, cada uma com duração e o tipo de imagem na tela.
Vamos condensar o vídeo em cerca de {alvo} segundos mantendo os trechos ORIGINAIS (corte extrativo, sem reescrever).
Modo: {modo_desc}

Tarefa:
1. Para CADA unidade, dê "nota" de 0 a 10 = quão essencial ela é para o espectador entender o conteúdo central
   (10 = tese, insight, número, resultado, demonstração-chave; 0 = saudação, patrocínio, repetição, enrolação, transição vazia)
   e um "motivo" de até 8 palavras.
2. Liste os "topicos" do vídeo com o intervalo de ids (de → ate) que cada um cobre, em ordem.
3. Indique "gancho": os ids de 1 ou 2 unidades que melhor ABREM o vídeo condensado (a frase que prende).

Responda SOMENTE com JSON válido:
{{"topicos":[{{"nome":"...","de":ID,"ate":ID}}],"gancho":[ID],"notas":[{{"id":ID,"nota":N,"motivo":"..."}}]}}
Inclua TODAS as {n} unidades em "notas", na ordem.

UNIDADES:
{lista}
```
`modo_desc`: A → "condensado com a fala original: priorize o que se entende só ouvindo."; B → "sem o apresentador: a narração será refeita; priorize unidades cujo tipo de imagem é demo_tela, grafico ou slide, pois é a imagem que vai ficar."; C → "só demonstrações e gráficos: priorize demo_tela e grafico."

- [ ] **Step 2: Testes (falhando)**

`tests/test_pontuar.py`:
```python
import json
from otv.fases.pontuar import montar_lista, montar_prompt, pontuar

U = [{"id": 0, "ini": 0, "fim": 6.2, "dur": 6.2, "texto": "abre aspas \"x\"", "visual": "slide"},
     {"id": 1, "ini": 6.2, "fim": 9.3, "dur": 3.1, "texto": "olha o gráfico", "visual": "grafico"}]

def test_montar_lista():
    assert montar_lista(U).splitlines()[1] == '[001] 3.1s grafico "olha o gráfico"'

def test_prompt_tem_modo_alvo_e_n():
    p = montar_prompt(U, "B", 90, "Título", 1200)
    assert "90 segundos" in p and "sem o apresentador" in p and "TODAS as 2 unidades" in p and "20 minutos" in p

def test_pontuar_escreve_notas_validadas(tmp_path, monkeypatch):
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": U}))
    (tmp_path / "metadata.json").write_text(json.dumps({"titulo": "T", "duracao_s": 600}))
    class Fake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            return {"topicos": [{"nome": "t", "de": 0, "ate": 1}], "gancho": [0], "notas": [{"id": 1, "nota": 9, "motivo": "m"}]}, {"cost": 0.001}
    import otv.fases.pontuar as P
    monkeypatch.setattr(P, "criar_llm", lambda cfg, slot: Fake())
    out = pontuar(tmp_path, {"pontuacao": "glm", "selecao": {"alvo_s": 120}}, modo="A")
    n = json.loads(out.read_text())
    assert [x["nota"] for x in n["notas"]] == [0, 9] and n["gancho"] == [0] and n["provedor"] == "fake"
```

- [ ] **Step 3: Rodar — falha**

Run: `pytest tests/test_pontuar.py -v`

- [ ] **Step 4: Implementar `otv/fases/pontuar.py`**

```python
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
```

- [ ] **Step 5: Rodar — PASS**

Run: `pytest tests/test_pontuar.py -v`

- [ ] **Step 6: Commit**

```bash
git add otv prompts tests && git commit -m "feat: pontuação por LLM (ids, tópicos, gancho) com validação"
```

---

### Task 8: Seleção (núcleo) — mochila, cota, coesão, gancho, snap, completar

**Files:**
- Create: `otv/fases/selecionar.py`
- Test: `tests/test_selecionar.py`

**Interfaces:**
- Consumes: `unidades.json`, `notas.json`, `scenes.json` (opcional), `cfg["selecao"]`.
- Produces: `selecionar_plan(unidades, notas, cenas, sel: dict, modo: str, alvo_s: float) -> dict` (plan no contrato); `selecionar(dir, cfg, modo="A", alvo_s=None, forcar=True) -> Path`. Funções internas testáveis: `filtrar_modo(unidades, modo)`, `mochila(cands, teto, cota, topico_de, ja=set())`, `segmentar(ids, unidades)`, `snap(segs, unidades, cortes_cena, folga_s)`.

- [ ] **Step 1: Testes (falhando)**

`tests/test_selecionar.py`:
```python
from otv.fases.selecionar import selecionar_plan, filtrar_modo, snap

SEL = {"alvo_s": 20, "tolerancia": 0.25, "min_segmento_s": 3, "min_segmento_ideal_s": 6,
       "folga_ms": 120, "cota_topico_pct": 60, "nota_minima": 5}

def U(i, ini, dur, visual="outro"):
    return {"id": i, "ini": ini, "fim": round(ini + dur, 3), "dur": dur, "texto": f"u{i}", "visual": visual, "cena": None}

def N(notas, topicos=None, gancho=None):
    return {"notas": [{"id": i, "nota": n, "motivo": ""} for i, n in enumerate(notas)],
            "topicos": topicos or [{"nome": "t", "de": 0, "ate": len(notas) - 1}], "gancho": gancho or []}

def test_escolhe_por_nota_ate_o_teto_em_ordem_cronologica():
    us = [U(i, i * 5.0, 4.0) for i in range(8)]                 # 8 unidades de 4 s com pausa de 1 s
    plan = selecionar_plan(us, N([9, 2, 8, 2, 10, 2, 7, 2]), [], SEL, "A", 20)
    ids = [i for s in plan["segmentos"] for i in s["unidades"]]
    assert ids == sorted(ids) and 4 in ids and 0 in ids and 1 not in ids
    assert plan["total_s"] <= 20 * 1.25

def test_cota_por_topico():
    us = [U(i, i * 5.0, 4.0) for i in range(8)]
    notas = N([10, 10, 10, 10, 6, 6, 6, 6], topicos=[{"nome": "a", "de": 0, "ate": 3}, {"nome": "b", "de": 4, "ate": 7}])
    plan = selecionar_plan(us, notas, [], {**SEL, "cota_topico_pct": 40}, "A", 20)   # cota = 8 s → no máx 2 unidades de 'a'
    ids = [i for s in plan["segmentos"] for i in s["unidades"]]
    assert len([i for i in ids if i <= 3]) <= 2 and any(i >= 4 for i in ids)

def test_coesao_estende_para_vizinho_razoavel_e_funde_contiguos():
    us = [U(i, i * 4.0, 3.9) for i in range(6)]                 # quase contíguas
    plan = selecionar_plan(us, N([9, 4, 9, 0, 0, 0]), [], {**SEL, "min_segmento_ideal_s": 8}, "A", 12)
    assert len(plan["segmentos"]) == 1 and plan["segmentos"][0]["unidades"] == [0, 1, 2]

def test_gancho_forcado_no_inicio():
    us = [U(i, i * 5.0, 4.0) for i in range(6)]
    plan = selecionar_plan(us, N([3, 3, 9, 9, 9, 9], gancho=[0]), [], SEL, "A", 12)
    assert plan["segmentos"][0]["unidades"][0] == 0

def test_modo_B_descarta_talking_head():
    us = [U(0, 0, 5, "talking_head"), U(1, 6, 5, "demo_tela"), U(2, 12, 5, "grafico")]
    assert [u["id"] for u in filtrar_modo(us, "B")] == [1, 2]
    assert [u["id"] for u in filtrar_modo(us, "C")] == [1, 2]
    assert len(filtrar_modo(us, "A")) == 3

def test_min_segmento_aplicado_depois_do_snap():
    us = [U(0, 0, 4.0), U(1, 4.2, 2.9), U(2, 7.2, 4.0)]        # unidade 1 tem 2.9 s (< 3) mas snap dá folga
    plan = selecionar_plan(us, N([0, 9, 0]), [], SEL, "A", 5)
    assert plan["segmentos"] and plan["segmentos"][0]["unidades"] == [1]

def test_snap_recua_para_pausa_e_alinha_em_corte_de_cena():
    us = [U(0, 0, 4.0), U(1, 5.0, 4.0)]                          # pausa de 1 s entre elas
    segs = snap([{"in": 5.0, "out": 9.0, "unidades": [1]}], us, cortes_cena=[4.8], folga_s=0.12)
    assert segs[0]["in"] == 4.8                                  # corte de cena a < 0.3 s vence
    segs = snap([{"in": 5.0, "out": 9.0, "unidades": [1]}], us, cortes_cena=[], folga_s=0.12)
    assert segs[0]["in"] == 4.6 and segs[0]["out"] == 9.12       # recua até metade da pausa (máx 0.4)
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_selecionar.py -v`

- [ ] **Step 3: Implementar `otv/fases/selecionar.py`**

```python
import json, time
from pathlib import Path
from otv.contratos import validar_plan
from otv.util.custos import registrar

VISUAL_MODO = {"A": None, "B": {"demo_tela", "grafico", "slide"}, "C": {"demo_tela", "grafico"}}

def filtrar_modo(unidades, modo):
    permitidos = VISUAL_MODO[modo]
    return [u for u in unidades if permitidos is None or u.get("visual") in permitidos]

def _topicos(notas, n):
    t = {}
    for tp in notas.get("topicos", []):
        for i in range(tp["de"], tp["ate"] + 1):
            t[i] = tp["nome"]
    return {i: t.get(i, "?") for i in range(n)}

def mochila(cands, teto, cota, topico_de, ja=None, total=0.0, por_topico=None):
    """cands: unidades já ordenadas por prioridade. Retorna (ids, total, por_topico)."""
    esc = set(ja or []); por_topico = dict(por_topico or {})
    for u in cands:
        if u["id"] in esc:
            continue
        tp = topico_de.get(u["id"], "?")
        if total + u["dur"] > teto or por_topico.get(tp, 0) + u["dur"] > cota:
            continue
        esc.add(u["id"]); total += u["dur"]; por_topico[tp] = por_topico.get(tp, 0) + u["dur"]
    return esc, total, por_topico

def segmentar(ids, unidades):
    por_id = {u["id"]: u for u in unidades}; segs = []
    for i in sorted(ids):
        u = por_id[i]
        if segs and segs[-1]["unidades"][-1] == i - 1:
            segs[-1]["unidades"].append(i); segs[-1]["out"] = u["fim"]
        else:
            segs.append({"in": u["ini"], "out": u["fim"], "unidades": [i]})
    return segs

def snap(segs, unidades, cortes_cena, folga_s):
    por_id = {u["id"]: u for u in unidades}; n = len(unidades)
    for s in segs:
        u0 = por_id[s["unidades"][0]]; u1 = por_id[s["unidades"][-1]]
        prev_fim = por_id[u0["id"] - 1]["fim"] if u0["id"] > 0 and (u0["id"] - 1) in por_id else 0.0
        pausa = max(0.0, u0["ini"] - prev_fim)
        ini = max(prev_fim, u0["ini"] - min(0.4, pausa / 2))
        perto = [c for c in cortes_cena if abs(c - ini) < 0.3 and c >= prev_fim]
        if perto:
            ini = min(perto, key=lambda c: abs(c - ini))
        nxt_ini = por_id[u1["id"] + 1]["ini"] if (u1["id"] + 1) in por_id else u1["fim"] + folga_s
        s["in"] = round(ini, 3); s["out"] = round(min(u1["fim"] + folga_s, nxt_ini), 3)
    return segs

def selecionar_plan(unidades, notas, cenas, sel, modo, alvo_s):
    nota = {x["id"]: x["nota"] for x in notas["notas"]}
    motivo = {x["id"]: x.get("motivo", "") for x in notas["notas"]}
    for u in unidades:
        u["nota"] = nota.get(u["id"], 0)
    topico_de = _topicos(notas, len(unidades))
    teto = alvo_s * (1 + sel["tolerancia"]); piso = alvo_s * (1 - sel["tolerancia"])
    cota = alvo_s * sel["cota_topico_pct"] / 100; nmin = sel["nota_minima"]
    elegiveis = filtrar_modo(unidades, modo)
    # 1. gancho forçado
    gancho = [g for g in notas.get("gancho", []) if any(u["id"] == g for u in elegiveis)]
    esc, total, por_topico = mochila([u for u in elegiveis if u["id"] in gancho], teto, 1e9, topico_de)
    # 2. mochila por nota (desempate: mais curta)
    cands = sorted([u for u in elegiveis if u["nota"] >= nmin], key=lambda u: (-u["nota"], u["dur"]))
    esc, total, por_topico = mochila(cands, teto, cota, topico_de, esc, total, por_topico)
    por_id = {u["id"]: u for u in unidades}; eleg_ids = {u["id"] for u in elegiveis}
    def _dur(ids): return sum(por_id[i]["dur"] for i in ids)
    # 3. coesão: estende cada segmento pros vizinhos razoáveis até min_segmento_ideal_s
    for s in segmentar(esc, unidades):
        ids = list(s["unidades"])
        while _dur(ids) < sel["min_segmento_ideal_s"]:
            viz = [j for j in (ids[0] - 1, ids[-1] + 1) if j in eleg_ids and j not in esc and por_id[j]["nota"] >= nmin - 2]
            viz = [j for j in viz if total + por_id[j]["dur"] <= teto]
            if not viz:
                break
            j = max(viz, key=lambda j: por_id[j]["nota"]); esc.add(j); total += por_id[j]["dur"]
            ids = sorted(ids + [j])
    # 4. vizinho sanduichado (id-1 e id+1 dentro) entra se razoável
    for u in elegiveis:
        i = u["id"]
        if i not in esc and (i - 1) in esc and (i + 1) in esc and u["nota"] >= nmin - 2 and total + u["dur"] <= teto:
            esc.add(i); total += u["dur"]
    # 5. segmentar + snap + mínimo (depois do snap)
    cortes = [c["ini"] for c in cenas]
    segs = snap(segmentar(esc, unidades), unidades, cortes, sel["folga_ms"] / 1000)
    segs = [s for s in segs if s["out"] - s["in"] >= sel["min_segmento_s"]]
    # 6. completar: se ficou abaixo do piso, repete a mochila só com vizinhos dos segmentos existentes
    esc = {i for s in segs for i in s["unidades"]}
    total = sum(s["out"] - s["in"] for s in segs)
    if total < piso:
        viz = sorted([por_id[j] for s in segs for j in (s["unidades"][0] - 1, s["unidades"][-1] + 1)
                      if j in eleg_ids and j not in esc and por_id[j]["nota"] >= nmin - 3], key=lambda u: -u["nota"])
        esc, total, _ = mochila(viz, teto, 1e9, topico_de, esc, total)
        segs = snap(segmentar(esc, unidades), unidades, cortes, sel["folga_ms"] / 1000)
        segs = [s for s in segs if s["out"] - s["in"] >= sel["min_segmento_s"]]
    for s in segs:
        s["visual"] = max((por_id[i].get("visual", "outro") for i in s["unidades"]), key=lambda v: 0 if v == "outro" else 1)
        s["motivo"] = "; ".join(dict.fromkeys(motivo[i] for i in s["unidades"] if motivo.get(i)))[:160]
        s["texto"] = " ".join(por_id[i]["texto"] for i in s["unidades"]); s["estender_s"] = 0
    plan = {"modo": modo, "alvo_s": alvo_s, "total_s": round(sum(s["out"] - s["in"] for s in segs), 1),
            "segmentos": segs, "narracao": None}
    validar_plan(plan)
    return plan

def selecionar(dir, cfg, modo="A", alvo_s=None, forcar=True):
    dir = Path(dir); out = dir / "plan.json"
    if out.exists() and not forcar:
        return out
    us = json.loads((dir / "unidades.json").read_text())["unidades"]
    notas = json.loads((dir / "notas.json").read_text())
    cenas = json.loads((dir / "scenes.json").read_text())["cenas"] if (dir / "scenes.json").exists() else []
    alvo = alvo_s or cfg["selecao"]["alvo_s"]
    if modo != "A" and not any(u.get("visual") in VISUAL_MODO[modo] for u in us):
        raise RuntimeError(f"nenhuma unidade com visual {sorted(VISUAL_MODO[modo])} — vídeo é só talking head? use modo A ou rode 'otv cenas --classificar'")
    plan = selecionar_plan(us, notas, cenas, cfg["selecao"], modo, alvo)
    if plan["total_s"] < 0.5 * alvo:
        print(f"aviso: só {plan['total_s']}s selecionados de {alvo}s — considere baixar selecao.nota_minima")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    registrar(dir, "selecionar", {"modo": modo, "alvo_s": alvo, "total_s": plan["total_s"], "segmentos": len(plan["segmentos"])})
    return out
```

- [ ] **Step 4: Rodar — PASS. Ajustar fixtures dos testes se um caso for genuinamente ambíguo, nunca afrouxar a regra.**

Run: `pytest tests/test_selecionar.py -v`

- [ ] **Step 5: Verificar no vídeo real**

Run: `python -c "from otv.fases.selecionar import selecionar; from otv.config import carregar_config; print(selecionar('trabalho/dQYKcjvXhIY', carregar_config()))"` (usa `unidades.json`/`notas.json` do spike — se o formato antigo não tiver `gancho`, `validar_notas` já tolera). Conferir: `total_s` entre 90 e 150, unidade 0 no primeiro segmento, nenhum segmento < 3 s, média por segmento ≥ 6 s.

- [ ] **Step 6: Commit**

```bash
git add otv tests && git commit -m "feat: seleção determinística (mochila, cota, coesão, gancho, snap, completar)"
```

---

### Task 9: Render ffmpeg (trim/concat frame-accurate, `--rapido`, narração e extensão)

**Files:**
- Create: `otv/fases/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `plan.json`, `video.mp4`, opcional `narracao/seg_NN.wav`.
- Produces: `montar_filtro(segmentos: list[dict]) -> str` (string do `-filter_complex`); `render(dir, cfg, rapido=False, sem_audio_original=False) -> Path` (escreve `output.mp4` e copia para `cfg["saida"]/<id>/`).

- [ ] **Step 1: Testes (falhando)**

`tests/test_render.py`:
```python
import json, subprocess
from otv.fases.render import montar_filtro, render
from otv.util.ffmpeg import probe

def test_montar_filtro_dois_segmentos():
    f = montar_filtro([{"in": 1.0, "out": 3.0, "estender_s": 0}, {"in": 4.0, "out": 5.5, "estender_s": 0}])
    assert "[0:v]trim=1.0:3.0,setpts=PTS-STARTPTS[v0]" in f
    assert "atrim=4.0:5.5" in f and "concat=n=2:v=1:a=1[v][a]" in f

def test_montar_filtro_estende_com_freeze():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 1.5}])
    assert "tpad=stop_mode=clone:stop_duration=1.5" in f and "apad=pad_dur=1.5" in f

def test_render_duracao_bate(video_teste, tmp_path):
    import shutil; shutil.copy(video_teste, tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(json.dumps({"id": "t"}))
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0}, {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]}))
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15
    assert (tmp_path / "saida" / "t" / "output.mp4").exists()
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_render.py -v`

- [ ] **Step 3: Implementar `otv/fases/render.py`**

```python
import json, shutil, time
from pathlib import Path
from otv.util.ffmpeg import run
from otv.util.custos import registrar

def montar_filtro(segmentos, narracao=None, cama_db=-18, sem_audio_original=False):
    fc = []; entradas = []
    for k, s in enumerate(segmentos):
        d = s["out"] - s["in"]; ext = float(s.get("estender_s") or 0)
        v = f"[0:v]trim={s['in']}:{s['out']},setpts=PTS-STARTPTS"
        a = f"[0:a]atrim={s['in']}:{s['out']},asetpts=PTS-STARTPTS,afade=t=in:d=0.04,afade=t=out:st={max(0, d - 0.04):.3f}:d=0.04"
        if ext > 0:
            v += f",tpad=stop_mode=clone:stop_duration={ext}"; a += f",apad=pad_dur={ext}"
        if narracao and narracao[k]:
            a += f",volume={'0' if sem_audio_original else cama_db}dB[o{k}];[{k + 1}:a]apad=whole_dur={d + ext:.3f},atrim=0:{d + ext:.3f}[n{k}];[o{k}][n{k}]amix=inputs=2:normalize=0"
        fc.append(v + f"[v{k}]"); fc.append(a + f"[a{k}]"); entradas.append(f"[v{k}][a{k}]")
    fc.append("".join(entradas) + f"concat=n={len(segmentos)}:v=1:a=1[vc][ac];[ac]loudnorm=I=-16:TP=-1.5[a];[vc]null[v]")
    return ";".join(fc)

def render(dir, cfg, rapido=False, sem_audio_original=False):
    dir = Path(dir); plan = json.loads((dir / "plan.json").read_text()); segs = plan["segmentos"]
    out = dir / "output.mp4"; t0 = time.time()
    if not segs:
        raise RuntimeError("plan.json sem segmentos")
    if rapido:
        lista = dir / "concat.txt"
        lista.write_text("".join(f"file 'video.mp4'\ninpoint {s['in']}\noutpoint {s['out']}\n" for s in segs))
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(out)])
    else:
        narr = plan.get("narracao"); wavs = [dir / w for w in narr["arquivos"]] if narr else None
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(dir / "video.mp4")]
        for w in (wavs or []):
            cmd += ["-i", str(w)]
        cmd += ["-filter_complex", montar_filtro(segs, wavs, sem_audio_original=sem_audio_original),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
        run(cmd)
    vid = json.loads((dir / "metadata.json").read_text()).get("id", dir.name)
    dest = Path(cfg["saida"]).expanduser() / vid; dest.mkdir(parents=True, exist_ok=True)
    for f in ("output.mp4", "plan.json", "notas.json", "unidades.json", "custos.json"):
        if (dir / f).exists():
            shutil.copy(dir / f, dest / f)
    registrar(dir, "render", {"rapido": rapido, "segundos": round(time.time() - t0, 1), "saida": str(dest / "output.mp4")})
    return out
```
Nota: quando há narração, o `plan["narracao"]["arquivos"]` tem um caminho por segmento (ou `null` para segmento sem narração); o índice de entrada `[k+1:a]` assume um wav por segmento **na mesma ordem** — a Task 10 garante isso gerando um wav (silencioso se preciso) para todo segmento.

- [ ] **Step 4: Rodar — PASS**

Run: `pytest tests/test_render.py -v`

- [ ] **Step 5: Commit**

```bash
git add otv tests && git commit -m "feat: render ffmpeg (trim/concat, rapido, extensão, mix de narração)"
```

---

### Task 10: Narração (modo B): roteiro por LLM, TTS inemavox/ElevenLabs, ajuste de duração

**Files:**
- Create: `prompts/narrar.md`, `otv/provedores/tts.py`, `otv/fases/narrar.py`
- Test: `tests/test_narrar.py`

**Interfaces:**
- Produces: `roteiro_por_segmento(segmentos, contexto, llm) -> list[str]`; `tts(texto, out_wav, cfg, provedor=None) -> Path`; `duracao_wav(p) -> float`; `narrar(dir, cfg, provedor=None) -> Path` (escreve `narracao/seg_NN.wav`, `roteiro.md`, e atualiza `plan.json` com `narracao: {"arquivos": [...], "provedor": ...}` e `estender_s` por segmento).
- inemavox: `POST http://localhost:8010/api/jobs/tts` body `{"text","engine":"chatterbox","voice":"rachel","lang":"pt"}` → `{"id": ...}`; poll `GET /api/jobs/{id}` até `status` final; áudio em `GET /api/jobs/{id}/download`. **Confirmar no primeiro uso os nomes exatos dos campos `id`/`status`** com `curl localhost:8010/api/jobs | head` e ajustar as constantes `CAMPO_ID`, `STATUS_OK`, `STATUS_ERRO` no topo de `tts.py`.

- [ ] **Step 1: `prompts/narrar.md`**

```
Você escreve narração em português do Brasil para um vídeo condensado SEM o apresentador: só as imagens
(demonstrações, gráficos, slides) ficaram. Abaixo estão os segmentos mantidos, com o que era dito neles e
o contexto em volta. Para CADA segmento escreva uma narração clara, direta, em 1ª pessoa do plural ou impessoal,
com no máximo {ppm} palavras por segundo × duração do segmento (ex.: segmento de 8 s → até {ex} palavras).
Não invente fatos: use só o que está nas falas. Não cumprimente, não conclua com frases vazias.
Responda SOMENTE JSON: {{"narracao":[{{"k":0,"texto":"..."}}, ...]}} com todos os {n} segmentos, na ordem.

SEGMENTOS:
{lista}
```

- [ ] **Step 2: Testes (falhando) — TTS mockado**

`tests/test_narrar.py`:
```python
import json, subprocess
from otv.fases.narrar import narrar, ajustar_extensao
import otv.fases.narrar as Nn

def test_ajustar_extensao():
    segs = [{"in": 0, "out": 5.0}, {"in": 10, "out": 14.0}]
    ajustar_extensao(segs, [4.0, 6.5])          # narração 4 s cabe; 6.5 s excede 2.5 s
    assert segs[0]["estender_s"] == 0 and segs[1]["estender_s"] == 2.5

def test_narrar_gera_wavs_e_atualiza_plan(tmp_path, monkeypatch):
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "B", "alvo_s": 10, "total_s": 8.0, "narracao": None,
        "segmentos": [{"in": 0, "out": 4.0, "unidades": [0], "texto": "a", "estender_s": 0},
                      {"in": 6, "out": 10.0, "unidades": [2], "texto": "c", "estender_s": 0}]}))
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": [{"id": i, "texto": t, "ini": i * 3, "fim": i * 3 + 2} for i, t in enumerate("abc")]}))
    class FakeLLM:
        nome = "fake"
        def chat_json(self, p, imagens=None): return {"narracao": [{"k": 0, "texto": "um"}, {"k": 1, "texto": "dois"}]}, {}
    def fake_tts(texto, out, cfg, provedor=None):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300", "-t", "3", str(out)], check=True); return out
    monkeypatch.setattr(Nn, "criar_llm", lambda cfg, slot: FakeLLM())
    monkeypatch.setattr(Nn, "tts", fake_tts)
    narrar(tmp_path, {"pontuacao": "glm", "tts": "inemavox"})
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["narracao"]["arquivos"] == ["narracao/seg_00.wav", "narracao/seg_01.wav"]
    assert (tmp_path / "roteiro.md").exists() and all(s["estender_s"] == 0 for s in plan["segmentos"])
```

- [ ] **Step 3: Rodar — falha**

Run: `pytest tests/test_narrar.py -v`

- [ ] **Step 4: Implementar `otv/provedores/tts.py`**

```python
import time, requests
from pathlib import Path
from otv.util.keys import key
from otv.util.ffmpeg import run

INEMAVOX = "http://localhost:8010"; CAMPO_ID = "id"; STATUS_OK = {"completed", "done", "finished"}; STATUS_ERRO = {"failed", "error"}

def tts_inemavox(texto, out, voz="rachel", engine="chatterbox"):
    r = requests.post(f"{INEMAVOX}/api/jobs/tts", json={"text": texto, "engine": engine, "voice": voz, "lang": "pt"}, timeout=60)
    r.raise_for_status(); jid = r.json()[CAMPO_ID]
    for _ in range(600):
        j = requests.get(f"{INEMAVOX}/api/jobs/{jid}", timeout=30).json()
        st = str(j.get("status", "")).lower()
        if st in STATUS_OK:
            break
        if st in STATUS_ERRO:
            raise RuntimeError(f"inemavox falhou: {j.get('error') or j}")
        time.sleep(2)
    else:
        raise RuntimeError("inemavox: timeout")
    a = requests.get(f"{INEMAVOX}/api/jobs/{jid}/download", timeout=120); a.raise_for_status()
    bruto = Path(out).with_suffix(".bin"); bruto.write_bytes(a.content)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(bruto), "-ar", "48000", "-ac", "1", str(out)]); bruto.unlink()
    return Path(out)

def tts_elevenlabs(texto, out, voz=None):
    vid = voz or key("ELEVENLABS_VOICE_ID")
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                      headers={"xi-api-key": key("ELEVENLABS_API_KEY")},
                      json={"text": texto, "model_id": "eleven_multilingual_v2"}, timeout=300)
    r.raise_for_status(); mp3 = Path(out).with_suffix(".mp3"); mp3.write_bytes(r.content)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(out)]); mp3.unlink()
    return Path(out)

def tts(texto, out, cfg, provedor=None):
    p = provedor or cfg.get("tts", "inemavox")
    return tts_elevenlabs(texto, out) if p == "elevenlabs" else tts_inemavox(texto, out)
```

- [ ] **Step 5: Implementar `otv/fases/narrar.py`**

```python
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
        else:  # silêncio do tamanho do segmento, pra manter um wav por segmento
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{s['out'] - s['in']:.3f}", str(wav)])
        arquivos.append(f"narracao/seg_{k:02d}.wav"); durs.append(duracao_wav(wav))
    ajustar_extensao(segs, durs)
    plan["narracao"] = {"arquivos": arquivos, "provedor": provedor or cfg.get("tts", "inemavox"), "llm": llm.nome}
    (dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (dir / "roteiro.md").write_text("\n\n".join(f"## Segmento {k} ({s['in']:.1f}–{s['out']:.1f}s)\n\n{t}" for k, (s, t) in enumerate(zip(segs, textos))))
    registrar(dir, "narrar", {"llm": llm.nome, "uso": uso, "tts": plan["narracao"]["provedor"], "segundos": round(time.time() - t0, 1)})
    return dir / "plan.json"
```

- [ ] **Step 6: Rodar — PASS**

Run: `pytest tests/test_narrar.py -v`

- [ ] **Step 7: Integração manual do inemavox (daemon em :8010 precisa estar rodando)**

Run: `python -c "from otv.provedores.tts import tts_inemavox; print(tts_inemavox('Teste de narração.', '/tmp/t.wav'))"` — se o campo do job não for `id`/`status`, ajustar `CAMPO_ID`/`STATUS_OK` conforme a resposta real de `GET /api/jobs`.

- [ ] **Step 8: Commit**

```bash
git add otv prompts tests && git commit -m "feat: narração modo B (roteiro LLM, TTS inemavox/elevenlabs, extensão)"
```

---

### Task 11: CLI `otv`, `run` encadeado, `status`, `custo`, README

**Files:**
- Create: `otv.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: subcomandos `run`, `ingest`, `transcrever`, `cenas`, `pontuar`, `selecionar`, `render`, `narrar`, `status`, `custo`. `run` executa: ingest → transcrever → cenas (`--visual` ≠ local → classificar) → unidades → pontuar → selecionar → (modo B: narrar) → render; cada fase pula se o artefato existe (`--forcar` refaz).

- [ ] **Step 1: Teste de CLI (falhando)**

`tests/test_cli.py`:
```python
import subprocess, sys

def test_help_lista_subcomandos():
    r = subprocess.run([sys.executable, "otv.py", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    for c in ("run", "ingest", "transcrever", "cenas", "pontuar", "selecionar", "render", "narrar", "status", "custo"):
        assert c in r.stdout

def test_status_pasta_inexistente():
    r = subprocess.run([sys.executable, "otv.py", "status", "nao-existe"], capture_output=True, text=True)
    assert r.returncode != 0 and "não encontrada" in (r.stdout + r.stderr)
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest tests/test_cli.py -v`

- [ ] **Step 3: Implementar `otv.py`**

```python
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
    if visual != "local" or a.modo != "A":
        F_ce.classificar(d, cfg, None if visual == "local" else visual, forcar=a.forcar); print("[classificar] ok")
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
```

- [ ] **Step 4: Rodar — PASS**

Run: `pytest -v` (suíte inteira)

- [ ] **Step 5: README.md**

Conteúdo mínimo: o que faz (1 parágrafo), instalação (`pip install -r requirements.txt`, ffmpeg/yt-dlp, keys em `~/projetos/openpcbotv2/.env`), uso (`python otv.py run <url> --modo A --alvo 120`), tabela dos slots do `config.yaml` com os provedores disponíveis, como editar `plan.json` e re-renderizar (`otv selecionar` / `otv render`), custo típico (~US$0,03/vídeo), links pra spec e pesquisa em `docs/`.

- [ ] **Step 6: Commit**

```bash
git add otv.py README.md tests && git commit -m "feat: CLI otv (run, fases, status, custo) e README"
```

---

### Task 12: Validação ponta a ponta no vídeo de exemplo (integração)

**Files:**
- Modify: `docs/superpowers/specs/2026-08-27-otimizevideo-design.md` (§11: acrescentar resultado da validação)
- Create: `FALHAS.md` (se alguma falha real ocorrer, uma linha por falha no formato `| data | o que quebrou | menor correção | prompt \| infra |`)

- [ ] **Step 1: Modo A completo com defaults**

Run: `python otv.py run "https://www.youtube.com/watch?v=dQYKcjvXhIY" --modo A --forcar`
Esperado: `[render] trabalho/dQYKcjvXhIY/output.mp4`; `status` mostra `plan` entre 90 e 150 s, primeiro segmento contendo a unidade 0 (gancho), nenhum segmento < 3 s, média ≥ 6 s por segmento. Copiado para `~/projetos/output/otimizevideo/dQYKcjvXhIY/output.mp4`.

- [ ] **Step 2: Custo**

Run: `python otv.py custo dQYKcjvXhIY` → total ≲ US$0,02 nas chamadas OpenRouter (+ Groq ≈ US$0,02).

- [ ] **Step 3: Troca de provedor sem tocar nas outras fases**

Run: `python otv.py pontuar dQYKcjvXhIY --provedor gemini --forcar && python otv.py selecionar dQYKcjvXhIY && python otv.py render dQYKcjvXhIY`
Esperado: novo `plan.json` (comparar ids com o anterior; espera-se ~50–70 % em comum), render ok.

- [ ] **Step 4: Modo B (com classificação visual)**

Run: `python otv.py run "https://www.youtube.com/watch?v=dQYKcjvXhIY" --modo B --visual glm`
Esperado: `scenes.json` com `visual` variado; `plan.json` só com segmentos `slide|demo_tela|grafico`; `roteiro.md` gerado; `narracao/seg_*.wav`; `output.mp4` com narração por cima e cama a −18 dB. Se este vídeo for majoritariamente talking head, a fase avisa e pede modo A — registrar isso na spec como comportamento esperado.

- [ ] **Step 5: Re-corte manual**

Editar `trabalho/dQYKcjvXhIY/plan.json` (remover um segmento), rodar `python otv.py render dQYKcjvXhIY` → saída reflete a edição, sem nenhuma chamada de modelo (conferir que `custos.json` não ganhou entrada nova de `pontuar`).

- [ ] **Step 6: Registrar resultados e commitar**

Adicionar em §11 da spec: durações, custos e o que foi ajustado. Se ocorreu falha real, linha em `FALHAS.md`.
```bash
git add docs FALHAS.md 2>/dev/null; git commit -m "docs: validação ponta a ponta no vídeo de exemplo"
```

---

## Self-review

- **Cobertura da spec:** §3 contratos → T1; §3.2 config → T1; §4.1 unidades → T4; §4.2 pontuação → T6+T7; §4.3 seleção (todas as 8 regras) + §11.5–11.7 (completar, coesão, gancho) → T8; §4.4 modo B → T10 + T9 (mix/extensão); §4.5 visual local/3b → T5 (3c "vídeo inteiro via Gemini Files API" fica **fora deste plano**, é slot futuro — anotado como YAGNI até aparecer vídeo onde a fala não basta); §5 ingest/transcrição/render → T2/T3/T9; §6 CLI → T11; §8 erros → distribuídos (retry em T3/T6, transcrição vazia em T3, seleção abaixo de 50 % e modo B sem cenas em T8, arquivo > limite: Groq aceita opus 32k de 30 min ≈ 7 MB, então o fatiamento não foi implementado — se um vídeo > 100 min aparecer, adicionar); §9 testes → todas as tasks; §11.1 reasoning low → T6; §11.4 normalização + mínimo pós-snap → T3/T8.
- **Placeholders:** nenhum "TBD"; o único ponto a confirmar em runtime (campos `id`/`status` do inemavox) tem instrução concreta de como confirmar e onde ajustar.
- **Consistência de nomes:** `chat_json` (T6) usado em T5/T7/T10; `criar_llm(cfg, slot)` idem; `validar_notas` (T1) em T7; `registrar` (T2) em todas; `probe/thumb/run` (T2) em T5/T9/T10; contrato de `plan["narracao"]["arquivos"]` definido em T10 e consumido em T9; `estender_s` escrito em T8 (0) e T10, lido em T9.
