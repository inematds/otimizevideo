# Pesquisa de provedores e ferramentas — 2026-08-27

Consolidação de três pesquisas web + verificação direta na API do OpenRouter (`/api/v1/models`).
Preços em US$ por 1M tokens (entrada / saída) salvo indicação.

## 1. Modelos via OpenRouter (verificado na API em 2026-08-27)

| Modelo | Entrada | Saída | Modalidades | Contexto | Uso no projeto |
|---|---|---|---|---|---|
| **z-ai/glm-5.3-flash** | 0,075 | 0,25 | texto+imagem+vídeo | 1,3M | **default** pontuação e classificação visual |
| z-ai/glm-5.3 | 1,40 | 4,40 | só texto | 1M | opção "qualidade" na pontuação |
| z-ai/glm-5.2 | 1,19 | 3,74 | só texto | 1M | — |
| z-ai/glm-4.6v | 0,30 | 0,90 | texto+imagem+vídeo | 131k | alternativa visual |
| z-ai/glm-5v-turbo | 1,20 | 4,00 | texto+imagem+vídeo | 202k | caro, não usar |
| **google/gemini-2.5-flash-lite** | 0,10 (batch 0,05) | 0,40 | texto+imagem+vídeo+áudio | 1M | alternativa visual / vídeo inteiro |
| google/gemini-2.5-flash | 0,30 | 2,50 | idem | 1M | — |
| google/gemini-3.7-flash | 0,375 (batch 0,19) | 1,875 | idem | 1M | alternativa "qualidade" visual |
| **qwen/qwen3.5-flash-02-23** | 0,065 | 0,26 | texto+imagem+vídeo | 1M | alternativa mais barata |
| qwen/qwen3.5-9b | 0,10 | 0,15 | texto+imagem+vídeo | 262k | — |
| qwen/qwen3-vl-8b/30b/32b/235b | 0,10–0,40 | — | **só imagem** no OpenRouter | 128–262k | só na variante miniaturas |

Observação: os modelos `qwen3-vl-*` no OpenRouter **não** aceitam vídeo; os `qwen3.5-*` aceitam.

## 2. Entendimento de vídeo — outras APIs

| Opção | Vídeo nativo | Custo 25 min | Notas |
|---|---|---|---|
| Gemini 2.5 Flash-Lite (API nativa Google) | sim | ~0,045 (0,015 low-res) | Files API grátis (2 GB, 48 h), `fps` configurável, timestamps MM:SS nativos, até 1 h (3 h low-res) |
| Gemini 2.5 Flash / Pro (nativa) | sim | ~0,135 / ~1,13 | idem |
| Qwen3-VL-Flash / Plus (DashScope) | sim | ~0,013 / ~0,063 | grounding temporal forte; exige conta Alibaba Cloud, doc fraca |
| TwelveLabs Pegasus+Marengo | sim | ~0,73 + indexação | único produto feito pra timestamp exato; 35× o Gemini |
| Kimi K2.6+ | sim (`video_url`) | ~0,95 / 4,00 por M | sem doc de precisão temporal |
| OpenAI GPT-4o/5.x, Claude, Mistral Pixtral, Moondream | **não** | — | só frames extraídos por você; servem na variante miniaturas |

### Local (GB10)
- **Qwen3-VL** open-weight (2B…235B): melhor opção pra classificar miniaturas a R$0.
- InternVL3.5 (30B cabe em 1 GPU), NVIDIA Cosmos-Reason (foco físico), Llama 4 (vídeo anunciado não está nos pesos abertos).

### Sem VLM (determinístico, R$0)
- **PySceneDetect** v0.7.1 (`AdaptiveDetector` melhor pra scroll/zoom de tela) ou ffmpeg `scdet`.
- **MediaPipe** Face Detector / YuNet → talking head por área de rosto. YOLOv8/11 se precisar corpo inteiro.
- Tesseract/PaddleOCR → densidade de texto (slide × demo).

## 3. Transcrição com timestamp por palavra

| Serviço | US$/h áudio | Word ts | Diarização | Notas |
|---|---|---|---|---|
| **Groq whisper-large-v3-turbo** | **0,04** (v3 full 0,111) | sim | não | limite 25 MB free / 100 MB dev → mandar opus 32k; relatos de imprecisão no turbo (snap por silêncio resolve) |
| **WhisperX** (local, BSD) | 0 | **melhor** (alinhamento fonético, 93 % vs 85 %) | sim (pyannote) | slot "precisão" na GB10 |
| faster-whisper / whisper.cpp (local) | 0 | sim (aprox.) | não | whisper já instalado na máquina |
| AssemblyAI | 0,15–0,21 (+0,02 diar.) | sim | sim | melhor "tudo pronto" |
| Deepgram Nova-3 | 0,26–0,31 | sim | sim | PT-BR ok |
| ElevenLabs Scribe | 0,22 batch | sim | sim (32 falantes) | |
| Gemini 3.5 Transcribe (preview 26/08/2026) | ~0,30 | sim | sim | novo |
| Voxtral (Mistral, Apache 2.0) | 0,18 API ou local | sim | sim | 13 idiomas incl. PT |
| NVIDIA Parakeet/Canary (NeMo) | 0 | sim | não | CC-BY, GPU NVIDIA |
| OpenAI whisper-1 | 0,36 | sim | não | |
| OpenAI gpt-4o-transcribe | 0,18–0,36 | **não** | variante separada | descartado |
| Cloudflare Workers AI whisper | ~0,03 | — | não | trava em arquivos longos; descartado |
| Speechmatics | 0,70–1,04 | sim | sim | caro |

## 4. TTS de narração PT-BR

| Serviço | PT-BR | Clonagem | US$/1k chars | Notas |
|---|---|---|---|---|
| **Chatterbox / inemavox** (MIT, local) | sim | sim, zero-shot | 0 | **default**; venceu ElevenLabs em teste cego (65 % × 24 %) |
| Fish Audio | sim | sim (até no free) | ~0,015 | melhor cloud barato |
| Google Chirp 3 HD | sim | 0,06 extra | 0,03 | 1M chars/mês grátis permanente |
| Azure Neural | sim | aprovação | 0,016–0,022 | 500k/mês grátis |
| OpenAI gpt-4o-mini-tts | sim | não | ~0,015–0,03 | |
| MiniMax Speech 2.8 | sim | sim (10 s) | 0,06–0,10 | |
| Cartesia Sonic | sim | sim | ~0,005–0,04 | baixa latência |
| ElevenLabs | sim | sim | 0,05–0,20 | mais caro; key existe, fica como opção |
| Kokoro-82M (local, Apache) | sim | não | 0 | roda em CPU |
| Orpheus (local, Apache) | sim | sim | 0 | ~8 GB VRAM |
| Qwen3-TTS (local, Apache) | sim | sim | 0 | novo, leve |
| XTTS-v2 | sim | sim | 0 | **licença não-comercial** — evitar |
| F5-TTS, CosyVoice2 | sem PT-BR oficial | — | — | evitar |
| Dia | só inglês | — | — | evitar |

## 5. Corte / edição

| Ferramenta | Sem re-encode | API Python | Status | Uso |
|---|---|---|---|---|
| **ffmpeg** (trim/concat, silencedetect, tpad, minterpolate, zoompan) | com `-c copy` | subprocess | ativo | **base do render** |
| **PySceneDetect** 0.7.1 | opcional | sim | ativo | detecção de cena |
| auto-editor v31.5 | parcial | não (binário Nim) | ativo | atalho silêncio→corte, fallback |
| moviepy 2.2 | não | sim | ativo | lento, evitar |
| LosslessCut | sim | HTTP experimental | ativo | dependência pesada |
| MLT, editly, OpenCut, Remotion, HyperFrames | — | — | — | não servem pra corte de fonte |

### Estender cena curta (modo B)
- Freeze: `-vf "tpad=stop_mode=clone:stop_duration=2" -af "apad=pad_dur=2"`
- Slow com interpolação: `setpts=2.0*PTS,minterpolate=fps=30:mi_mode=mci`
- Ken Burns: `zoompan=z='min(zoom+0.0015,1.4)':d=125:s=1920x1080`

### Projetos open-source de referência ("long → short com LLM")
- **FunClip** (modelscope, MIT, v2.1.1 ago/2026, ~6k★): FunASR local + LLM escolhe trechos + corte. O mais maduro — abrir pra comparar com a técnica de IDs.
- AI-Youtube-Shorts-Generator (faster-whisper + LLM rankeia): ativo, sem LICENSE.
- NarratoAI (~11k★, foco narração), VideoHighlighter (100 % offline, AGPL), autoclip (imaturo).
- ClipsAI abandonado; VideoAgent acadêmico e exige Claude.

### SaaS com API ponta-a-ponta (caixa preta, não usados)
OpusClip, Vizard (API melhor documentada), Klap — US$15–50/mês. CapCut, Munch, Gling: sem API.
TwelveLabs é o único componível.

## 6. Decisões tomadas a partir da pesquisa

1. Modelo default (pontuação + miniaturas): `z-ai/glm-5.3-flash` — mais barato com vídeo, 1,3M contexto.
2. Alternativas de um clique: `google/gemini-2.5-flash-lite`, `qwen/qwen3.5-flash-02-23`; vídeo inteiro via Gemini API nativa.
3. Transcrição: Groq turbo default; WhisperX como slot de precisão local.
4. TTS: inemavox/chatterbox default; ElevenLabs e Fish como opção.
5. Visual: sempre local (PySceneDetect + MediaPipe) primeiro; VLM só nas miniaturas; vídeo inteiro só sob demanda.
