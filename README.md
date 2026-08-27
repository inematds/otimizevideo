# otv — otimizevideo

CLI que pega um vídeo longo (aula, podcast, palestra — 20 a 30 min) e devolve um corte de
**~2 minutos** com o melhor conteúdo, cortado com precisão de palavra.

## 1. O que faz

`otv` roda um vídeo por um pipeline de fases (transcrição → detecção de cena →
classificação visual → pontuação → seleção → render) e produz um `output.mp4` condensado.
A regra de ouro do projeto, e o que o diferencia de "manda o vídeo pro modelo e pede um
corte": **o modelo nunca escolhe timestamps**. Ele só vê a transcrição fatiada em unidades
numeradas por id (`[042] 4.2s "texto da unidade"`) e devolve uma nota de 0 a 10 por id. É o
código — não o modelo — que converte id → tempo (`ini`/`fim` em segundos, vindos direto da
transcrição com timestamp por palavra) e faz o corte.

Isso importa por dois motivos: (1) o corte nunca cai no meio de uma palavra, porque a
fronteira de cada unidade já é uma fronteira de palavra/pausa real da transcrição, nunca um
timestamp inventado pelo modelo; e (2) o resultado é reproduzível — rodar a mesma seleção
duas vezes com o mesmo `notas.json` dá o mesmo `plan.json`, porque a lógica de escolha
(mochila por nota, cota por tópico, gancho/fecho, coesão) é determinística e vive no código,
não numa alucinação do LLM.

## 2. Instalação

```bash
pip install -r requirements.txt
```

O Python do sistema nesta máquina é PEP 668 (ambiente "externally managed") — se o comando
acima falhar com `error: externally-managed-environment`, use:

```bash
pip install --user --break-system-packages -r requirements.txt
```

Também precisam estar no `PATH`:

- **ffmpeg** e **ffprobe** (corte, extração de áudio, thumbnails, mux final)
- **yt-dlp** (baixar vídeo de URL — só necessário se `otv run <url>`, não para arquivo local)

`whisper_local`, `whisperx` e `ollama` (provedores opcionais, ver tabela na seção 5) trazem
dependências pesadas (`openai-whisper`, `whisperx`, `torch`) que **não** estão em
`requirements.txt` — instale-as só se for usar esses provedores.

### Keys

`otv` nunca lê nem escreve chave de API em `config.yaml` ou em qualquer arquivo deste
projeto. As keys são lidas em **runtime** de `~/projetos/openpcbotv2/.env` ou
`~/projetos/wifi/.env` (primeiro arquivo que tiver a variável, nessa ordem — ver
`otv/util/keys.py`). Configure lá `GROQ_API_KEY`, `OPENROUTER_API_KEY` e, se for usar
ElevenLabs, `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`. Nenhuma key é impressa, logada ou
gravada em disco por este projeto.

## 3. Uso rápido

```bash
python3 otv.py run <url-ou-caminho-do-video> --modo A --alvo 120
```

Isso roda o pipeline inteiro (ingest → transcrever → cenas → pontuar → selecionar → render)
e escreve o resultado em `~/projetos/output/otimizevideo/<id>/output.mp4` (o `<id>` é o
ID do vídeo do YouTube, ou o nome do arquivo normalizado, quando a fonte é local). O mesmo
`output.mp4`, junto com `plan.json`, `notas.json`, `unidades.json` e `custos.json`, também
fica em `trabalho/<id>/` (pasta de trabalho intermediária).

## 4. Os três modos

| Modo | O que sai | Quando usar | O que exige |
|---|---|---|---|
| **A** | Condensado com a **fala original** do apresentador (talking head incluso) | Padrão — preserva o tom e a voz de quem gravou | Nada além da transcrição; roda 100% com `visual: local` |
| **B** | **Sem** o apresentador — corta pra tela/gráfico/slide e **regrava a narração** (TTS) por cima | Quando o rosto/olho no vídeo original não importa e você quer um corte mais "editorial" | Classificação visual por modelo (as cenas precisam estar marcadas como `demo_tela`, `slide` ou `grafico` — a detecção local só distingue "tem rosto" de "não tem") |
| **C** | Só **demonstrações e gráficos** — o modo mais restrito | Vídeo é majoritariamente demo/gráfico e você quer só isso, sem qualquer talking head | Mesma exigência do modo B |

**B e C dependem de classificação visual por modelo.** A detecção local (`visual: local`) só
sabe dizer "tem rosto grande" (`talking_head`) ou "não" (`outro`) — ela nunca produz
`demo_tela`, `slide` ou `grafico`. Sem passar `--visual glm`, `--visual gemini` ou
`--visual claude_cli` (ou rodar `otv cenas <id> --classificar` manualmente), `otv run
--modo B` (ou `C`) segue em frente com um aviso e falha depois, na fase de seleção, com uma
mensagem clara dizendo que não há unidade com o visual necessário.

## 5. Slots do `config.yaml`

O `config.yaml` na raiz define, por slot, qual provedor usar por padrão. Todo slot pode ser
sobreposto por linha de comando (`--transcricao`, `--visual`, `--pontuacao`, `--tts` em
`otv run`; `--provedor` nos subcomandos de fase), e o arquivo inteiro pode ser trocado com
`--config outro.yaml`.

| Slot | Provedores | Custo/exigência | Default |
|---|---|---|---|
| `transcricao` | `groq` | Cloud, precisa de `GROQ_API_KEY`. Não reporta custo em `$`; ~US$0,04/hora de áudio | **default** |
| | `whisper_local` | GPU/CPU local, grátis, mas precisa de `openai-whisper` instalado (fora do `requirements.txt`) | |
| | `whisperx` | GPU local (CUDA se disponível), grátis, precisa de `whisperx`+`torch` instalados | |
| `visual` | `local` | Grátis, sem key — heurística por área de rosto (mediapipe). Só distingue `talking_head`/`outro`, nunca `demo_tela`/`slide`/`grafico` | **default** |
| | `glm` (`z-ai/glm-5.3-flash` via OpenRouter) | Precisa de `OPENROUTER_API_KEY`. Barato (~US$0,004 por vídeo de 25 min) | |
| | `gemini` (`google/gemini-2.5-flash-lite` via OpenRouter) | Precisa de `OPENROUTER_API_KEY` | |
| | `claude_cli` (Claude Code headless, `claude -p --model sonnet`) | Sai da **assinatura** do usuário — sem API key, mas precisa do binário `claude` no `PATH` e logado | |
| `pontuacao` | `glm` (`z-ai/glm-5.3-flash` via OpenRouter) | Precisa de `OPENROUTER_API_KEY`. ~US$0,002 por vídeo de 25 min (1 chamada, `reasoning_effort: low`) | **default** |
| | `gemini` (`google/gemini-2.5-flash-lite` via OpenRouter) | Precisa de `OPENROUTER_API_KEY` | |
| | `ollama` (`qwen3.8:27b`) | Local, grátis, mas precisa de **daemon Ollama** rodando (`http://localhost:11434`) | |
| | `claude_cli` (Claude Code headless) | Sai da assinatura — sem API key, precisa do `claude` no `PATH` | |
| `tts` | `inemavox` | Local, grátis, mas precisa do **daemon inemavox** rodando (`http://localhost:8010`) | **default** |
| | `elevenlabs` | Cloud, precisa de `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID`; cobra por caractere | |

Os modelos concretos de cada slot de LLM (`glm`, `gemini`, `ollama`, `claude_cli`, e o
`turbo` do `whisper_local`) ficam em `config.yaml → modelos:` — trocar o modelo não muda o
slot, só o que aquele slot chama.

## 6. Parâmetros de `selecao` (`config.yaml → selecao:`)

| Parâmetro | Default | Efeito prático |
|---|---|---|
| `alvo_s` | 120 | Duração alvo, em segundos, do vídeo final (mesmo valor que `--alvo` sobrepõe) |
| `tolerancia` | 0.25 | Faixa aceitável ao redor do alvo: teto = `alvo_s × 1.25`, piso = `alvo_s × 0.75`. A seleção usa esse teto como orçamento extra para coesão/gancho/fecho depois que a mochila principal já saturou o `alvo_s` puro |
| `min_segmento_s` | 3 | Qualquer segmento final com menos que isso (depois do corte/snap) é descartado — evita cortes de fração de segundo |
| `min_segmento_ideal_s` | 8 | Meta de "coesão": cada segmento tenta puxar vizinhos com nota razoável até atingir esse tamanho, pra não virar uma sequência de picadinhos |
| `cota_topico_pct` | 40 | Teto, em % do `alvo_s`, que um único tópico pode ocupar na mochila principal — evita que o corte vire "só a parte mais falada", garantindo diversidade de assunto |
| `nota_minima` | 5 | Nota mínima (0–10) pra uma unidade entrar na mochila principal. Gancho/fecho e as extensões de coesão toleram um pouco menos (nota_minima − 2 ou − 3) pra poder completar o segmento |
| `folga_ms` | 120 | Margem extra, em milissegundos, deixada depois do fim da última unidade de um segmento ao fazer o snap — evita cortar em cima da última sílaba |
| `pausa_fronteira_ms` | 400 | Pausa mínima entre palavras (na fase de `unidades`) que já conta como fronteira natural de unidade — junto com pontuação (`.`/`!`/`?`) e fim de segmento da transcrição, é um dos critérios que fecha uma unidade |
| `max_unidade_s` | 12 | Teto de duração de uma unidade cortável — mesmo sem pausa nem pontuação (fala corrida), o código força um corte na maior pausa interna disponível antes de estourar esse teto |

## 7. Todos os subcomandos

```bash
# pipeline completo
python3 otv.py run <url-ou-caminho> --modo A --alvo 120

# só baixa/copia o vídeo e extrai áudio, sem processar nada
python3 otv.py ingest <url-ou-caminho>

# fases individuais, sobre uma pasta já ingerida (o <id> é o nome da pasta em trabalho/)
python3 otv.py transcrever <id> --provedor groq
python3 otv.py cenas <id> --classificar --provedor glm
python3 otv.py pontuar <id> --modo A --alvo 120 --provedor glm
python3 otv.py selecionar <id> --modo A --alvo 120
python3 otv.py render <id> --rapido
python3 otv.py narrar <id> --provedor inemavox

# inventário de artefatos + resumo do plano de corte
python3 otv.py status <id>

# gasto acumulado por fase, lido de trabalho/<id>/custos.json
python3 otv.py custo <id>
```

## 8. Rodar fase por fase e reaproveitar trabalho

Cada fase escreve seu próprio JSON em `trabalho/<id>/` (`transcript.json`, `scenes.json`,
`unidades.json`, `notas.json`, `plan.json`, `custos.json`...) e é **idempotente**: se o
artefato já existe, a fase não roda de novo — só devolve o que já está no disco.
`--forcar` obriga a refazer.

Isso economiza dinheiro de verdade: se a pontuação (`otv pontuar`) já rodou e custou
uma chamada de LLM, você pode rodar `otv selecionar` várias vezes com `--modo`/`--alvo`
diferentes, ou `otv render` de novo depois de editar o plano à mão (seção 9), sem pagar
nenhuma chamada de modelo outra vez. Só refaça uma fase com `--forcar` quando precisar
mesmo de um resultado novo dela (ex.: transcrição errada, classificação visual desatualizada
depois de trocar de provedor).

## 9. Editar `plan.json` na mão e re-renderizar

`plan.json` é texto — dá pra editar o corte final sem chamar nenhum modelo. É esse recurso
que dá controle editorial ao usuário sobre a escolha automática.

Um segmento tem este formato:

```json
{
  "in": 175.1,
  "out": 182.5,
  "unidades": [58, 59, 60],
  "visual": "talking_head",
  "motivo": "explica o resultado do experimento",
  "texto": "The judges said that the 50-year-old problem was essentially solved.",
  "estender_s": 0
}
```

Dá pra remover um segmento inteiro da lista `segmentos`, ajustar `in`/`out` manualmente
(cuidado: `unidades` deixa de bater exatamente com o novo intervalo, mas o render só usa
`in`/`out`), ou editar o texto de `manchete` no topo do JSON. Depois de editar, **não** rode
`otv selecionar` de novo (ele reescreveria o arquivo do zero) — vá direto pro render:

```bash
python3 otv.py render <id>
```

## 10. Custo típico

Para um vídeo de ~25 min, com os defaults (`transcricao: groq`, `visual: local` no modo A,
`pontuacao: glm`, `tts: inemavox`):

| Fase | Custo |
|---|---|
| Transcrição (Groq) | ~US$0,02 (Groq não reporta custo em `$`; estimativa ~US$0,04/hora de áudio) |
| Cenas + detecção de rosto (local) | R$0 |
| Classificação visual por modelo (só modo B/C) | ~US$0,004 |
| Pontuação (1 chamada) | ~US$0,002 |
| Seleção / render / TTS local | R$0 |
| **Total (modo A)** | **≈ US$0,03** — e re-cortes/re-render depois são R$0 |

Veja o gasto real de uma pasta já processada com:

```bash
python3 otv.py custo <id>
```

## 11. Solução de problemas

Casos reais já encontrados neste projeto (changelog completo em `FALHAS.md`):

- **`inemavox` (TTS): `GET /api/jobs/{id}/download` devolve 404.** O endpoint certo é
  `GET /api/jobs/{id}/audio` — já corrigido no código (`otv/provedores/tts.py`), mas se você
  estiver apontando pra outra versão do daemon inemavox, confira o endpoint.
- **Manchete sumindo do vídeo sem erro nenhum.** Um `%` solto no texto da manchete (comum em
  "100% de certeza" vindo de LLM) fazia o `drawtext` do ffmpeg interpretar `expansion=normal`
  e falhar silenciosamente (warning engolido por `-v error`, processo sai com código 0 e sem
  manchete). Corrigido com `expansion=none` — se você mexer em `render.py`, não tire essa flag.
- **`sem_audio_original=True` não estava silenciando nada.** `volume=0dB` é ganho unitário
  (não muda nada); o ganho real-zero é `volume=0`. Já corrigido.
- **Fala corrida sem pontuação nem pausa gerava unidades gigantes** (uma chegou a 30s, ~25%
  do orçamento de um corte de 120s). O corte forçado por `max_unidade_s` resolve isso — se
  você notar unidades grandes de novo, confira se `selecao.max_unidade_s` não foi removido ou
  aumentado demais no `config.yaml`.
- **Gemini via API nativa devolvendo 503 nos modelos 3.x, e 2.5 desligado pra contas novas.**
  É limite de conta/infra da Google, não bug daqui — o slot `gemini` usa OpenRouter, não a API
  nativa, exatamente para não depender disso.
- **`glm` via OpenRouter travando mais de 13 minutos numa pontuação.** O modelo tem
  `reasoning` que não pode ser desligado nesse endpoint; a correção foi mandar
  `reasoning: {effort: "low"}` + `max_tokens: 20000` (já no `config.yaml → openrouter:`) — sem
  isso a chamada pode nunca voltar em tempo hábil.
- **Groq devolvendo `segments: null`** quando `timestamp_granularities` só pedia `word`. A
  correção foi pedir `[word, segment]` e tratar `segments or []` — já no código
  (`otv/provedores/transcricao.py`).

## 12. Links

- Spec de design: [`docs/superpowers/specs/2026-08-27-otimizevideo-design.md`](docs/superpowers/specs/2026-08-27-otimizevideo-design.md)
- Plano de implementação (tasks): [`docs/superpowers/plans/2026-08-27-otimizevideo.md`](docs/superpowers/plans/2026-08-27-otimizevideo.md)
- Pesquisa de provedores (preços, modelos, comparação): [`docs/pesquisa-provedores-2026-08-27.md`](docs/pesquisa-provedores-2026-08-27.md)
- Changelog de falhas: [`FALHAS.md`](FALHAS.md)
