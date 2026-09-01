# otv — otimizevideo

CLI que pega um vídeo longo (aula, podcast, palestra — 20 a 30 min) e devolve um corte de
**~2 minutos** com o melhor conteúdo, cortado com precisão de palavra.

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/otimizevideo/guia/**

## 1. O que faz

`otv` roda um vídeo por um pipeline de fases (transcrição → detecção de cena →
classificação visual → pontuação → seleção → render) e produz um `output.mp4` condensado.
A regra de ouro do projeto, e o que o diferencia de "manda o vídeo pro modelo e pede um
corte": **o modelo nunca escolhe timestamps**. Ele só vê a transcrição fatiada em unidades
numeradas por id (`[042] 4.2s talking_head "texto da unidade"`) e devolve uma nota de 0 a 10
por id. É o código — não o modelo — que converte id → tempo (`ini`/`fim` em segundos, vindos
direto da transcrição com timestamp por palavra) e faz o corte.

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

`otv` nunca escreve chave de API em `config.yaml` nem em qualquer arquivo deste projeto —
elas são lidas em **runtime** (`otv/util/keys.py`), na primeira fonte que tiver a variável:

1. **variável de ambiente** — `GROQ_API_KEY=... python3 otv.py run ...`, systemd, Docker
2. o arquivo apontado por **`OTV_ENV_FILE`**, se definido
3. **`.env` na raiz do projeto** (está no `.gitignore`)
4. **`~/.config/otv/.env`**
5. os `.env` da máquina de origem — `~/projetos/openpcbotv2/.env`, `~/projetos/wifi/.env`

As opções 1–4 tornam o projeto portável para outra máquina ou VPS sem editar código
(seção 15). Linhas com `#` são ignoradas e `export NOME=valor` é aceito.

Configure `GROQ_API_KEY`, `OPENROUTER_API_KEY` e, se for usar ElevenLabs,
`ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` (mais `FAL_KEY` para o modo A+). Nenhuma key é
impressa, logada ou gravada em disco por este projeto.

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

Há ainda dois modos derivados, documentados no fim deste README: **A+** (mantém a fala
original mas troca o vídeo do apresentador por ilustração gerada — seção 13) e **N** (mantém
o vídeo inteiro na tela e regrava só o áudio como narração — seção 14).

**B e C dependem de classificação visual por modelo.** A detecção local (`visual: local`) só
sabe dizer "tem rosto grande" (`talking_head`) ou "não" (`outro`) — ela nunca produz
`demo_tela`, `slide` ou `grafico`. Sem passar `--visual glm`, `--visual gemini` ou
`--visual claude_cli` (ou rodar `otv cenas <id> --classificar` manualmente), `otv run
--modo B` (ou `C`) segue em frente com um aviso e falha depois, na fase de seleção, com uma
mensagem clara dizendo que não há unidade com o visual necessário.

## 5. Slots do `config.yaml`

O `config.yaml` na raiz define, por slot, qual provedor usar por padrão. Todo slot pode ser
sobreposto por linha de comando (`--transcricao`, `--visual`, `--pontuacao`, `--tts` em
`otv run`; `--provedor` em `otv transcrever`/`cenas`/`pontuar`/`narrar`), e o arquivo inteiro
pode ser trocado com `--config outro.yaml`.

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
python3 otv.py substituir <id> --provedor fal     # modo A+: troca o apresentador por ilustração
python3 otv.py render <id> --rapido
python3 otv.py narrar <id> --provedor inemavox

# inventário de artefatos + resumo do plano de corte
python3 otv.py status <id>

# gasto acumulado por fase, lido de trabalho/<id>/custos.json
python3 otv.py custo <id>
```

## 8. Rodar fase por fase e reaproveitar trabalho

Cada fase escreve seu próprio JSON em `trabalho/<id>/` (`transcript.json`, `scenes.json`,
`unidades.json`, `notas.json`, `plan.json`, `custos.json`...) e a maioria é **idempotente**:
se o artefato já existe, a fase não roda de novo — só devolve o que já está no disco.
`--forcar` obriga a refazer.

**Três exceções sempre refazem, mesmo sem `--forcar`:** `selecionar` (assina o plano de novo
toda vez — é o comportamento certo pra poder rodar `otv selecionar <id> --modo B --alvo 90`
repetidas vezes até achar a combinação boa, sem editar código), `render` (não tem noção de
"já existe" — sempre re-renderiza a partir do `plan.json` atual, é assim que a seção 9
funciona) e `narrar` (idem — sempre gera os wavs de novo a partir do `plan.json` atual). As
fases `ingest`, `transcrever`, `cenas`, `pontuar` são as que de fato pulam quando o artefato
já existe.

Isso economiza dinheiro de verdade: se a pontuação (`otv pontuar`) já rodou e custou
uma chamada de LLM, você pode rodar `otv selecionar` várias vezes com `--modo`/`--alvo`
diferentes, ou `otv render` de novo depois de editar o plano à mão (seção 9), sem pagar
nenhuma chamada de modelo outra vez — `selecionar`/`render`/`narrar` refazerem sempre não
custa nada, porque não chamam LLM nenhum. Só refaça `ingest`/`transcrever`/`cenas`/`pontuar`
com `--forcar` quando precisar mesmo de um resultado novo dela (ex.: transcrição errada,
classificação visual desatualizada depois de trocar de provedor).

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
`otv selecionar` de novo (ele reescreve o `plan.json` do zero, sempre — ver seção 8) — vá
direto pro render:

```bash
python3 otv.py render <id>
```

**Cuidado com `otv run` na mesma pasta.** `otv run <fonte>` sem `--forcar` pula
`ingest`/`transcrever`/`cenas`/`pontuar` se os artefatos já existirem, mas ele sempre chama
`selecionar` internamente — que, como a seção 8 explica, reescreve o `plan.json` mesmo sem
`--forcar`. Rodar `otv run` de novo na mesma pasta depois de editar o `plan.json` à mão
**apaga a edição em silêncio**. Depois de editar o plano, o comando certo é `otv render <id>`
isolado (acima), nunca `otv run` de novo.

## 10. Consumo de LLM e custo real

O pipeline chama LLM em **quatro pontos**, e só um deles roda no caminho padrão (modo A):

| Fase | Chamadas por vídeo de ~25 min | O que manda pro modelo | Quando roda |
|---|---|---|---|
| `pontuar` | **1** | a transcrição inteira fatiada em unidades numeradas (texto puro) | sempre |
| `cenas --classificar` | **1 por lote de 20 thumbnails** (`otv/fases/cenas.py`) — ~378 cenas ≈ **19 chamadas**, multimodal, imagens em base64 | as thumbs das cenas | só modos **B/C** (e `--visual glm/gemini/claude_cli`) |
| `narrar` | **1** | o texto do plano, pra reescrever pra locução | modos **B/C/N** |
| `abertura` | **1** | título + manchete + lista curta de cenas | quando a abertura é montada |

### Números medidos (não estimados)

Vídeo real de ~25 min (`trabalho/dQYKcjvXhIY/custos.json`), slot `glm` =
`z-ai/glm-5.3-flash` via OpenRouter:

| Fase | prompt tokens | completion tokens | Custo | Tempo |
|---|---|---|---|---|
| `pontuar` | 8.933 | 6.475 | **US$0,0046** | 85 s |
| `classificar` | 83.001 | 10.047 | **US$0,0099** | 195 s |
| `narrar` | 2.116 | 740 | **US$0,0007** | 303 s |
| `abertura` | 784 | 116 | **US$0,0002** | 101 s |
| **Total de LLM (pipeline inteiro)** | | | **US$0,0154** | |

**A classificação visual é 90% do consumo de tokens** — são imagens em base64, ~4,4k tokens
por lote de 20 thumbs. É o único ponto multimodal do projeto, e é exatamente o que o modo A
não usa.

### Custo por modo

| Modo | LLM que roda | Custo de LLM | Total com transcrição |
|---|---|---|---|
| **A** (default, `visual: local`) | só `pontuar` (+ `abertura`) | **~US$0,005** | **≈ US$0,025** |
| **N** | `pontuar` + `narrar` (+ `abertura`) | ~US$0,006 | ≈ US$0,026 |
| **B / C** | `pontuar` + `classificar` + `narrar` (+ `abertura`) | ~US$0,015 | ≈ US$0,035 |

A transcrição no Groq entra com ~US$0,02 em todos eles (o Groq não reporta custo em `$`;
estimativa de ~US$0,04 por hora de áudio). Cenas, detecção de rosto, seleção, render e TTS
local são R$0.

### O que zera ou reduz

- **Re-cortes e re-renders são R$0.** `selecionar`, `render` e `narrar` (o TTS em si) não
  chamam LLM pago; `pontuar` e `cenas` gravam o artefato e não repetem sem `--forcar`
  (seção 8).
- `--pontuacao ollama` ou `--visual ollama` tira o custo em `$` (roda local em
  `qwen3.8:27b`, precisa do daemon).
- `--pontuacao claude_cli` / `--visual claude_cli` sai da **assinatura** do Claude Code, sem
  API key — o custo é registrado como `0.0` no `custos.json`.

### Atenção: retry pode dobrar o consumo

Cada chamada tem **2 tentativas** se a resposta não vier em JSON válido (`chat_json` em
`otv/provedores/llm.py`) e até **3 tentativas** no HTTP para erros 5xx/429. Na pior hipótese
uma fase consome o dobro do que a tabela acima mostra.

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


## 13. Modo A+ — substituir o apresentador por ilustração

`--substituir gerado` (no `run`) ou a fase `otv substituir <id>` gera uma ilustração 16:9 por
segmento marcado como `talking_head` e troca **só o vídeo** desses trechos: o áudio continua
sendo o original, então a fala não muda em nada. Só faz sentido depois que o visual foi
classificado (`otv cenas --classificar`), porque é o campo `visual` do plano que decide o que
é apresentador.

```bash
python3 otv.py run <url> --modo A --visual glm --substituir gerado
```

As imagens ficam em `trabalho/<id>/subst/seg_NN.png` e o caminho relativo é anotado em cada
segmento do `plan.json` (`"substituir": "subst/seg_00.png"`). A fase é idempotente: um PNG que
já existe é reaproveitado sem nova chamada paga — use `--forcar` para regerar. O render monta
esses trechos com `movie=…,zoompan` (Ken Burns lento) na mesma geometria do vídeo, e o
`otv status <id>` marca com `→img` o que já foi trocado.

Provedor de imagem: `imagem: fal` no `config.yaml` (flux-2-klein via fal.ai, `FAL_KEY` lida dos
`.env` de sempre). É o único provedor implementado — trocar é escrever outra classe com o mesmo
método `gerar(prompt, destino)` em `otv/provedores/imagem.py`.


## 14. Modo N — narração sobre o conteúdo inteiro

O modo A mantém a fala original, e por isso os cortes deixam saltos: a pessoa muda de assunto e
de entonação sem transição. O modo B resolve a fluência, mas descarta o apresentador e só fica
com slide, demo e gráfico. O **modo N** é o meio-termo: mantém o vídeo inteiro na tela (como o A)
e substitui o áudio por uma narração reescrita (como o B).

```bash
python3 otv.py run <url> --modo N
```

A narração **não é conteúdo novo**: o prompt (`prompts/narrar_n.md`) manda traduzir e dar fluência
ao que já foi dito — tirar hesitação, ligar o salto que o corte deixou, manter número e nome
próprio exatamente como estão — e proíbe acrescentar fato, data ou conclusão que não esteja na
fala. O `roteiro.md` é o ponto de revisão antes do render.

Diferente dos outros modos, o N **não precisa de classificação visual** (não filtra por tipo de
imagem) e usa um teto de congelamento maior: **6 s** em vez de 3 s. Português é mais prolixo que
inglês, então a narração costuma passar da duração do trecho — em vez de truncar a frase, o
último quadro congela e espera a fala terminar, e o próximo trecho entra depois.

## 15. Rodar sem Claude Code e sem Codex (VPS headless)

**Sim — o pipeline inteiro roda numa VPS sem nenhum agente de código instalado.** O `otv` é
um CLI Python normal; `claude_cli` é só *um dos provedores opcionais* dos slots `visual` e
`pontuacao`, nunca uma dependência. Codex não é usado em lugar nenhum do projeto.

O que a VPS precisa de verdade:

| Item | Obrigatório? | Observação |
|---|---|---|
| Python 3 + `requirements.txt` | sim | `requests`, `pyyaml`, `yt-dlp`, `scenedetect`, `opencv-python`, `mediapipe` |
| `ffmpeg` / `ffprobe` no `PATH` | sim | corte, thumbs, mux |
| `yt-dlp` | só se a fonte for URL | arquivo local dispensa |
| `GROQ_API_KEY` | sim (default de transcrição) | ou trocar por `whisper_local`/`whisperx` |
| `OPENROUTER_API_KEY` | sim (default de pontuação) | ou trocar por `ollama` |
| GPU | **não** | `visual: local` (mediapipe) e a detecção de cena rodam em CPU |
| daemon `inemavox` (:8010) | só modos B/C/N | TTS — sem ele, use `--tts elevenlabs` |
| daemon Ollama (:11434) | só se escolher `ollama` | |
| binário `claude` | **não** | só se escolher `--pontuacao claude_cli` / `--visual claude_cli` |

Config mínima 100% cloud, sem daemon nenhum e sem GPU:

```yaml
transcricao: groq
visual: local        # modo A; para B/C use glm (também cloud)
pontuacao: glm
tts: elevenlabs      # evita depender do inemavox local
```

Duas ressalvas de VPS pequena:

- **`opencv-python` + `mediapipe` puxam bibliotecas de sistema.** Em imagem slim/headless,
  instale `libgl1` e `libglib2.0-0`, ou troque por `opencv-python-headless`.
- **A detecção de cena é CPU-bound**: 130 s para um vídeo de 25 min na máquina de referência.
  Numa VPS de 1 vCPU conte com bem mais, mas ela roda uma vez só e é idempotente.

**As keys não exigem os caminhos da máquina de origem.** Na VPS, use qualquer uma das
fontes portáveis (seção 2 → *Keys*): variáveis de ambiente no systemd/Docker, um `.env` na
raiz do projeto, `~/.config/otv/.env`, ou `OTV_ENV_FILE` apontando pra onde você quiser.

```bash
# opção 1: ambiente (nada em disco)
GROQ_API_KEY=... OPENROUTER_API_KEY=... python3 otv.py run <url> --modo A

# opção 2: .env na raiz do projeto (ignorado pelo git)
printf 'GROQ_API_KEY=...\nOPENROUTER_API_KEY=...\n' > .env
```

## 16. Painel web — mandar e ver o que já rodou

```bash
./start.sh                 # sobe o painel; ./start.sh 9000 usa outra porta
./stop.sh                  # para (recusa se houver job rodando)
```

`start.sh` faz a pré-checagem antes de subir — `ffmpeg`/`ffprobe` no `PATH`, os módulos
Python do `requirements.txt`, `yt-dlp`, e se as keys estão achando (só avisa, não bloqueia) —
porque falhar aqui é mais barato que falhar no meio de um job já pago. Depois roda com
`setsid`, então **o painel sobrevive ao fechar o terminal**, e grava `trabalho/.painel/painel.pid`.

Recusa subir se já houver painel rodando **em qualquer porta**: duas instâncias
compartilhariam `trabalho/.painel/` e a segunda sobrescreveria o histórico de jobs da
primeira. `./stop.sh` **se recusa a parar com job em andamento** (`--forcar` mata o job
junto). Opções: `./start.sh --local` prende em `127.0.0.1`; `./start.sh --token` gera um
token e exige `?t=…`.

Sem os scripts, o comando cru é `python3 otv.py painel [--porta 8022] [--host 0.0.0.0]`.

Sobe um servidor da **stdlib** (sem Flask, sem dependência nova) que escuta em `0.0.0.0`,
então qualquer aparelho da LAN abre pelo IP da máquina. Ele roda **dentro do projeto**: usa o
mesmo `config.yaml` e a mesma pasta `trabalho/`, e dispara o próprio `otv.py` como
subprocesso — não existe caminho paralelo, o painel não sabe fazer nada que o CLI não faça.

Na tela:

- **Mandar** — cola a URL do YouTube *ou o caminho de um vídeo local*, escolhe o modo (cada
  opção traz a descrição do que sai: `A — fala original`, `N — vídeo inteiro, narração
  regravada`, `B — sem apresentador`, `C — só demo e gráfico`), alvo, slot visual e o
  checkbox **A+** (trocar o apresentador por ilustração gerada), e clica em Rodar. Uma linha
  de dica embaixo do formulário explica o modo escolhido e **avisa quando a combinação vai
  falhar** — B, C e A+ precisam de `Visual = glm`, porque a detecção `local` não sabe o que é
  slide/demo/gráfico. A fila é **serial, um job por vez** (detecção de cena é
  CPU-bound; dois jobs paralelos só se atrapalham).
- **Acompanhar** — o log ao vivo é o stdout das fases (`[ingest] ok`, `[pontuar] ok`…), gravado
  em `trabalho/.painel/painel-<job>.log`. O job é subprocesso, então **continua rodando se você
  fechar o browser** — reabrir reengata no log.
- **Ver o que já rodou** — cada rodada de `trabalho/` com thumb, título, duração original,
  modo, duração do corte, manchete, custo em US$ e os artefatos que existem. Quem já tem
  `output.mp4` ganha player inline (com `Range`, então dá pra dar seek).
- **Re-cortar de graça** — botões `re-selecionar` (pede outro alvo/modo) e `re-render` em cada
  rodada. Nenhum dos dois chama LLM: US$0, quantas vezes quiser (seção 8).

### Onde ele fica acessível

Ao subir, o painel imprime todos os endereços IPv4 por onde responde:

```
painel: http://localhost:8022
        http://192.168.1.172:8022
        http://100.70.253.64:8022  (tailscale — alcançável fora da LAN)
```

**Repare no endereço Tailscale.** Numa máquina com tailnet, "LAN" não é o limite: o painel
responde para qualquer aparelho do tailnet, inclusive fora de casa. Se o firewall bloquear a
porta (não é o caso na máquina de referência), libere com `sudo ufw allow 8022/tcp`; para
prender só na máquina local, `--host 127.0.0.1`.

### Segurança

Sem autenticação por padrão — a premissa é LAN doméstica. Defina `OTV_PAINEL_TOKEN` para
exigir token (`http://…:8022/?t=<token>`):

```bash
OTV_PAINEL_TOKEN=$(openssl rand -hex 16) python3 otv.py painel
```

Duas travas existem porque isto fica exposto na rede, e não devem ser removidas:

- **todo comando vai pro `Popen` como lista de argumentos, nunca por shell** — sem isso o
  campo de fonte viraria execução de comando arbitrário para qualquer um da LAN;
- **todo id é resolvido e conferido contra a raiz de `trabalho/`** antes de virar caminho de
  arquivo, e as fases disparáveis são uma lista branca (`selecionar`, `render`, `narrar`,
  `abertura`, `substituir`) — sem isso `../../etc/passwd` viraria download.

Lembre que **qualquer aparelho que alcance a máquina pode disparar um job pago** (~US$0,03
por vídeo) — LAN e tailnet incluídos. O painel avisa no start quando sobe sem token. Se
isso incomodar, defina `OTV_PAINEL_TOKEN` ou use `--host 127.0.0.1`.
