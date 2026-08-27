# otimizevideo — Spec de design

**Data:** 2026-08-27 · **Status:** aguardando revisão do usuário

## 1. Objetivo

Pegar um vídeo longo (20–30 min: aula, tutorial, palestra, demo) e produzir uma versão enxuta
(~2 min) que preserve o que importa. A IA transcreve e analisa o conteúdo falado, e — de forma
barata — o visual, pra decidir o que fica. O corte final é feito por ffmpeg a partir de uma lista
de tempos (EDL). Cada fase tem provedor trocável por configuração.

**O núcleo do projeto é a técnica de seleção (seção 4).** Todo o resto é encanamento.

## 2. Premissas assumidas (defaults — corrigir se estiver errado)

| Item | Assumido |
|---|---|
| Fonte | URL (YouTube via yt-dlp) ou arquivo local |
| Idioma | PT-BR predominante; inglês suportado (Whisper detecta) |
| Ordem de entrega dos modos | A (condensado) → B (sem apresentador) → C (só gráficos/demos) |
| Duração alvo | 120 s, tolerância ±25 % (parâmetro `--alvo`) |
| Formato de saída | 16:9 igual ao original; 9:16 fica pra depois |
| Narração (modo B) | inemavox / chatterbox, voz `rachel` (default global) |
| Forma de entrega | CLI Python em fases (`otv`) nesta pasta; skill fina por cima depois |
| Saída | `~/projetos/output/otimizevideo/<id>/` |
| Lote | um vídeo por vez (lista/playlist depois) |
| Keys | carregadas em runtime de `~/projetos/openpcbotv2/.env` / `~/projetos/wifi/.env`; nunca copiadas nem impressas |

## 3. Arquitetura: o contrato entre fases

Cada fase lê arquivos JSON da pasta de trabalho, chama no máximo um provedor, e escreve um JSON.
Nenhuma fase conhece o provedor da outra. Tudo é inspecionável e editável à mão entre fases.

```
fonte ─▶ 1 ingest ─▶ video.mp4 · audio.opus · metadata.json
             │
             ├─▶ 2 transcrever ─▶ transcript.json     (palavras com ini/fim)
             │        └─▶ 2b unidades (código) ─▶ unidades.json  (frases cortáveis)
             │
             └─▶ 3 cenas (código) ─▶ scenes.json      (cortes visuais + tag por cena)
                      └─▶ 3b classificar (VLM, opcional) ─▶ scenes.json enriquecido
                                       │
        unidades + scenes ─▶ 4 pontuar (LLM, 1 chamada) ─▶ notas.json
                                       │
        notas + regras + alvo ─▶ 5 selecionar (código) ─▶ plan.json   ◀── edição manual
                                       │
                          6 render (ffmpeg) ─▶ output.mp4
                                       ▲
        [modo B] 7 narrar (LLM roteiro + TTS) ─▶ narracao.wav + roteiro.md
```

### 3.1 Contratos (arquivos)

**`metadata.json`** — `{id, fonte, titulo, duracao_s, fps, largura, altura, criado_em}`

**`transcript.json`** — formato compatível com a skill `talking-head-recut`:
```json
{"idioma": "pt", "provedor": "groq/whisper-large-v3-turbo",
 "palavras": [{"t": "então", "ini": 12.34, "fim": 12.61}, …]}
```

**`unidades.json`** — a unidade cortável (frase). Gerada por código, sem modelo.
```json
{"unidades": [
  {"id": 17, "ini": 312.40, "fim": 318.62, "dur": 6.22,
   "texto": "então o que acontece com a retenção quando a gente muda o gancho",
   "cena": 41, "visual": "slide"}
]}
```

**`scenes.json`**
```json
{"cenas": [
  {"id": 41, "ini": 305.0, "fim": 331.2, "thumb": "thumbs/041.jpg",
   "rosto_pct": 0.31, "visual": "talking_head",
   "descricao": null}
]}
```
`visual ∈ {talking_head, slide, demo_tela, grafico, outro}`. `rosto_pct` vem da detecção local;
`descricao` só existe se a fase 3b (VLM) rodou.

**`notas.json`** — saída do LLM, **só ids** (nunca timestamps):
```json
{"provedor": "openrouter/z-ai/glm-5.3-flash",
 "topicos": [{"nome": "gancho e retenção", "de": 12, "ate": 58}],
 "notas": [{"id": 17, "nota": 8, "motivo": "define o problema central"}]}
```

**`plan.json`** — a EDL. Código gera, humano pode editar, render consome.
```json
{"modo": "A", "alvo_s": 120, "total_s": 118.4,
 "segmentos": [
   {"in": 312.28, "out": 331.32, "unidades": [17, 18, 19],
    "visual": "demo_tela", "motivo": "…", "estender_s": 0}
 ],
 "narracao": null}
```

### 3.2 `config.yaml` — slots de provedor

```yaml
transcricao: groq          # groq | whisper_local | whisperx
visual:      local         # local (rosto+cena, R$0) | claude_cli | glm | gemini | gemini_video
pontuacao:   claude_cli    # claude_cli (Claude Code headless, assinatura) | glm | gemini | ollama
tts:         inemavox      # inemavox | elevenlabs | fish
modelos:
  claude_cli: sonnet       # `claude -p --model sonnet`; opus se quiser mais qualidade
  glm:    z-ai/glm-5.3-flash
  gemini: google/gemini-2.5-flash-lite
  ollama: qwen3.8:27b
selecao:
  alvo_s: 120
  tolerancia: 0.25
  min_segmento_s: 3
  pausa_fronteira_ms: 400
  folga_ms: 120
  cota_topico_pct: 40
  nota_minima: 5
```

Trocar provedor = mudar uma linha ou passar `--provedor` na fase. Nenhuma outra fase muda.

## 4. A técnica de seleção (núcleo)

Princípio: **o modelo nunca vê o vídeo; vê texto numerado.** Escolhe por id, não por tempo.
O tempo é responsabilidade do código, que é determinístico e grátis.

### 4.1 Unidades cortáveis (fase 2b, código)

1. Percorre `palavras` em ordem.
2. Fecha uma unidade quando: a palavra termina com `. ! ?` **ou** a pausa até a próxima palavra
   é ≥ `pausa_fronteira_ms` **ou** a unidade já tem ≥ 12 s (corte forçado na maior pausa interna).
3. Unidades com < 0,8 s ou < 3 palavras são fundidas com a vizinha anterior.
4. Cada unidade recebe `cena` (a cena que contém seu ponto médio) e herda `visual` dela.

Resultado: 300–500 unidades num vídeo de 25 min, cada uma com fronteira em pausa natural.
**Por isso o corte nunca cai no meio de palavra.**

### 4.2 Pontuação (fase 4, uma chamada de LLM)

Entrada pro modelo — lista numerada compacta (≈ 8–12k tokens pra 25 min):
```
[017] 6.2s slide      "então o que acontece com a retenção quando a gente muda o gancho"
[018] 3.1s demo_tela  "olha aqui no gráfico"
[019] 9.8s grafico    "a curva cai 40% nos primeiros 3 segundos"
```
Instrução (resumo): *"Este é um vídeo de N min sobre <título>. Vamos condensar em ~2 min no
modo <A|B|C>. Para CADA unidade devolva nota 0–10 de 'quanto isso é essencial pro espectador
entender o conteúdo' e um motivo de até 10 palavras. Devolva também a lista de tópicos (id
inicial → id final). Responda só JSON."*

Regras de robustez:
- Saída validada por schema; ids desconhecidos são descartados; ids faltantes recebem nota 0.
- Se o modelo devolver JSON inválido, 1 retry com a mensagem de erro; depois falha a fase.
- Modo B/C: o prompt diz explicitamente que unidades `talking_head` valem menos — mas o filtro
  duro é aplicado na seleção, não confiado ao modelo.

Custo: ~10k tokens de entrada + ~4k de saída no glm-5.3-flash ≈ **US$0,002**.

### 4.3 Seleção (fase 5, código puro)

Entrada: `unidades`, `notas`, `scenes`, `config.selecao`, `modo`. Sem modelo.

1. **Filtro por modo**
   - A: todas as unidades.
   - B: só unidades com `visual ∈ {demo_tela, grafico, slide}` (talking_head descartado).
   - C: só `visual ∈ {demo_tela, grafico}`.
2. **Corte por nota mínima** (`nota_minima`).
3. **Mochila gulosa por densidade**: ordena por `nota` desc (desempate: unidade mais curta), vai
   incluindo enquanto `total ≤ alvo × (1 + tolerancia)`.
4. **Cota por tópico**: nenhum tópico pode ocupar > `cota_topico_pct` do alvo — evita 2 min de um
   assunto só. Unidade que estoura a cota é pulada.
5. **Fusão de vizinhos**: se `id` e `id+2` entraram e `id+1` tem nota ≥ `nota_minima − 2`, inclui
   `id+1` (evita picotado). Depois, unidades adjacentes viram um único segmento.
6. **Mínimo por segmento**: segmento < `min_segmento_s` é removido (e o tempo liberado volta pro
   passo 3 pra tentar incluir a próxima melhor).
7. **Ordem cronológica sempre** — resumo extrativo, nunca reordena.
8. **Snap de fronteiras** (o detalhe que faz o corte parecer profissional):
   - `in` recua até o fim da pausa anterior (início do silêncio + metade dele), limitado a 400 ms.
   - `out` avança até `fim` da última palavra + `folga_ms`, sem invadir a próxima palavra.
   - Se `in` cair a < 300 ms de um corte de cena, alinha no corte de cena (evita flash de 5 frames
     da cena anterior).

Saída: `plan.json`. **Mudar alvo, modo ou regras re-roda só esta fase — R$0, < 1 s.**

### 4.4 Modo B — sem o apresentador

1. Seleção com filtro B produz segmentos só visuais, somando `T` segundos.
2. LLM recebe **só o texto** das unidades escolhidas + o texto vizinho (contexto) e escreve uma
   narração em PT-BR de ~`T × 2,5` palavras (≈150 ppm) dividida por segmento. Uma chamada.
3. TTS gera `narracao_<n>.wav` por segmento (inemavox).
4. Ajuste de duração por segmento, no render, sem chamar modelo:
   - narração mais curta que o vídeo → mantém vídeo, silêncio no fim;
   - narração mais longa → `estender_s` = diferença; render aplica `tpad` (freeze do último frame)
     até 3 s, ou `setpts` slow até 1,5× — o que ficar mais natural (freeze pra tela/gráfico
     estático, slow pra demo em movimento).
5. Áudio original vira cama a −18 dB (ou é removido com `--sem-audio-original`).

### 4.5 Camada visual barata (fase 3)

- **3 (local, R$0, sempre roda):** PySceneDetect `AdaptiveDetector` → cortes de cena. Uma
  miniatura 512 px por cena (`ffmpeg -ss … -frames:v 1`). MediaPipe Face Detector na miniatura →
  `rosto_pct` = área da maior caixa / área do frame. Heurística: `rosto_pct ≥ 0,08` → `talking_head`;
  senão `outro` (a classificação fina vem da 3b ou do texto).
- **3b (VLM, opcional, centavos):** manda as miniaturas em lotes de 20 pro modelo `visual` com a
  pergunta "classifique cada imagem em slide / demo_tela / grafico / talking_head / outro e
  descreva em ≤ 8 palavras". ~150 cenas × ~300 tokens ≈ 45k tokens ≈ US$0,004 no glm-5.3-flash.
- **3c (vídeo inteiro, opcional):** `visual: gemini_video` manda o `video.mp4` via Files API a 0,5
  fps e pede a mesma classificação com timestamps. ~US$0,05. Só quando a imagem importa mais que
  a fala (demos silenciosas).

Modo A funciona só com 3. Modos B e C precisam de 3b ou 3c.

## 5. Fases restantes (encanamento)

- **1 ingest:** yt-dlp (`-f "bv*[height<=1080]+ba"`) ou cópia do arquivo; `ffprobe` → metadata;
  `ffmpeg -vn -c:a libopus -b:a 32k` → `audio.opus` (25 min ≈ 6 MB, cabe no limite de 25 MB do Groq).
- **2 transcrever:** `groq` (whisper-large-v3-turbo, `timestamp_granularities=["word"]`) |
  `whisper_local` (já instalado) | `whisperx` (alinhamento fonético, mais preciso). Todos
  normalizam pro contrato `transcript.json`.
- **6 render:** `filter_complex` com `trim/atrim + concat` (um re-encode, frame-accurate,
  `-c:v libx264 -crf 20 -preset medium`, `-c:a aac`). `--rapido` usa concat demuxer com
  `inpoint/outpoint` e `-c copy` (corta em keyframe, sem re-encode). Fade de áudio de 40 ms nas
  fronteiras (`afade`) pra evitar clique. Loudness final `loudnorm`.
- **7 narrar:** `inemavox` (HTTP local, chatterbox, `rachel`) | `elevenlabs` | `fish`. Contrato:
  texto → wav 48 kHz.

## 6. CLI

```
otv run <url|arquivo> [--modo A|B|C] [--alvo 120] [--visual local|glm|gemini_video] [--rapido]
otv ingest <fonte>            otv transcrever <id> [--provedor groq]
otv cenas <id> [--classificar]  otv pontuar <id> [--provedor glm]
otv selecionar <id> [--alvo 90] [--modo B]     otv render <id>
otv narrar <id>               otv status <id>   otv custo <id>
```
`run` encadeia tudo; cada fase pula se o artefato já existe (`--forcar` refaz). `custo` soma
tokens/segundos reportados por cada provedor num `custos.json`.

## 7. Estrutura

```
otimizevideo/
  otv.py  config.yaml  requirements.txt  README.md
  otv/  fases/{ingest,transcrever,unidades,cenas,pontuar,selecionar,render,narrar}.py
        provedores/{base,groq_whisper,whisper_local,whisperx,openrouter,gemini_video,inemavox,elevenlabs}.py
        contratos.py  (dataclasses + validação dos JSONs)   util/{ffmpeg,keys,custos}.py
  prompts/{pontuar.md,classificar.md,narrar.md}
  tests/  (fixtures pequenas: transcript sintético, notas sintéticas → plan esperado)
  docs/superpowers/{specs,plans}/   docs/pesquisa-provedores-2026-08-27.md
  trabalho/<id>/   (artefatos intermediários; saída final copiada pra ~/projetos/output/otimizevideo/<id>/)
```

## 8. Erros e limites

- Provedor falhou (rede, 5xx, rate limit): 3 tentativas com backoff; depois a fase falha com
  mensagem clara e o `run` para — artefatos anteriores ficam, basta re-rodar.
- Transcrição vazia ou < 50 palavras: aborta com aviso (vídeo sem fala → só modo C faz sentido).
- Seleção não atinge 50 % do alvo (tudo com nota baixa): avisa e entrega o que tem; sugere baixar
  `nota_minima`.
- Modo B sem nenhuma cena visual: aborta com aviso "vídeo é só talking head; use modo A".
- Arquivo de áudio > limite do provedor: re-encoda a 24k ou fatia em 2 partes com offset.

## 9. Testes

- **Unitários (sem rede):** `unidades` (fronteiras em pausa/pontuação, fusão de curtas),
  `selecionar` (mochila, cota, fusão de vizinhos, mínimo por segmento, snap, ordem), parsers de
  cada provedor (fixtures de resposta gravada), montagem do comando ffmpeg.
- **Integração (com rede, manual):** `otv run` no vídeo de exemplo do usuário; conferir `plan.json`
  antes do render; comparar `--visual local` × `glm` × `gemini_video` no mesmo vídeo.
- **Critério de aceite do spike:** olhando o `plan.json` do vídeo de exemplo, o usuário concorda
  que ≥ 70 % dos segmentos escolhidos são "os que ele escolheria".

## 10. Fora de escopo (por enquanto)

Reframe 9:16, legendas embutidas, lote/playlist, interface web, remoção da pessoa por crop/blur
dentro do frame (só descarte de cena por enquanto), diarização.

## 11. Aprendizados do spike (2026-08-27, vídeo dQYKcjvXhIY, 20 min, inglês)

Spike descartável rodou ingest → Groq → unidades → pontuação → seleção → ffmpeg. Resultado:
**1206 s → 113,5 s, 18 segmentos, custo ≈ US$0,03, render 45 s.** Saída em
`~/projetos/output/otimizevideo/dQYKcjvXhIY/output.mp4`. O que muda no design:

1. **`z-ai/glm-5.3-flash` no OpenRouter não permite desligar reasoning** ("Reasoning is mandatory
   for this endpoint"). Sem controle, levou > 13 min e não respondeu. Com `reasoning: {effort: "low"}`
   respondeu em 64 s, US$0,004, JSON válido, 325/325 notas. → O provedor `openrouter` sempre manda
   `reasoning.effort = low` (configurável). `max_tokens` ≥ 20000 pra 325 unidades.
2. **`google/gemini-2.5-flash-lite`**: 33 s, US$0,006, JSON válido — alternativa de mesmo nível.
   `google/gemini-3.7-flash`: 57 s, US$0,024. `qwen/qwen3.5-flash-02-23` devolveu vazio → fora.
3. **Concordância entre modelos:** GLM e Gemini-lite escolheram 21 unidades cada, 14 em comum
   (Jaccard 0,50). O núcleo converge; a borda varia. Não precisa de painel de modelos.
4. **Timestamps do Whisper-turbo (Groq) se sobrepõem** entre palavras vizinhas (ex.: unidade N
   começa 0,4 s antes da N−1 terminar). Consequências e correções:
   - `transcrever` normaliza: `ini = max(ini, fim_anterior)`, `fim = max(fim, ini + 0,05)`.
   - `min_segmento_s` é aplicado **depois** do snap, não antes.
   - `whisperx` como slot de precisão continua valendo.
5. **Tempo descartado não volta:** a mochila encheu 150 s de unidades, o filtro de mínimo removeu
   ~35 s e a saída ficou em 113 s. → Seleção em duas passadas: (a) mochila, (b) fusão/filtro,
   (c) se `total < alvo × (1 − tolerancia)`, repete a mochila só com candidatos que **estendem
   segmentos existentes** (vizinhos), até fechar o alvo.
6. **Picotado:** média de 6 s por segmento. → Regra de coesão: depois da mochila, cada segmento é
   estendido pros vizinhos com `nota ≥ nota_minima − 2` até atingir `min_segmento_ideal_s` (8 s),
   se couber no teto. Menos cortes, mais fôlego.
7. **Gancho:** a unidade 0 ("You've been told that aging is inevitable…") teve nota 7 e ficou de
   fora; o vídeo abriu na unidade 2. → O prompt pede também `"gancho": [ids]` (1–2 unidades que
   melhor abrem o vídeo) e a seleção força a inclusão do gancho no início.
8. **Unidades:** 325 unidades, média 3,8 s, fronteiras em pontuação/pausa funcionaram bem —
   nenhum corte no meio de palavra ao ouvir a saída. `fins_segmento` do Whisper ajuda porque as
   `words` não trazem pontuação; pedir `timestamp_granularities=[word, segment]`.
9. **Ollama local (`qwen3.8:27b`, think off)** funciona como slot `pontuacao: ollama` (R$0): 325/325
   notas, 408 s (6,8 min) com GPU a 94 %, seleção de 20 segmentos / 131,8 s. Concordância com o GLM:
   11 de 22 unidades (Jaccard 0,34) — menor que GLM×Gemini (0,50). Vale como fallback offline, não default.

## 11b. Ajustes após revisão do usuário no spike (2026-08-27)

10. **Onde está o apresentador:** detecção de rosto nos 18 trechos do spike achou o apresentador em 7
    (trechos 0, 1, 6, 12, 13, 14, 17). O `plan.json` marca cada segmento com `visual` e o usuário decide
    o que fazer com os `talking_head`. Além de **descartar** (modo B), entra a opção **substituir**:
    `--substituir gerado` troca a imagem do trecho por uma ilustração gerada (flux2-klein, prompt = a
    `descricao` do tópico) mantendo o áudio original; `--substituir broll` reaproveita uma cena `outro|demo|grafico`
    do mesmo tópico no próprio vídeo. Fica como modo **A+** (áudio original, sem rosto). Só descartar e
    substituir-por-gerado entram no primeiro plano; `broll` depois.
11. **Fecho cortado:** a conclusão do vídeo ([319] nota 7 + [320] "As of this year, it is." nota 8) ficou de
    fora porque [320] tem 2,1 s e o mínimo por segmento a removeu sem puxar a vizinha. → O prompt devolve
    também `"fecho": [ids]`; a seleção força gancho no início e fecho no final, e **estende gancho/fecho
    pros vizinhos** (nota ≥ nota_minima − 3) até cumprir `min_segmento_s`, antes de qualquer filtro.
12. **Manchete no topo:** o prompt devolve `"manchete"` (≤ 8 palavras). O render escreve a manchete sobre
    os primeiros 4 s (ffmpeg `drawtext`, faixa escura semitransparente no topo, fade in/out), em
    `plan.json → "manchete"`; o usuário pode editar o texto antes de renderizar.
13. Prompts finais em `prompts/pontuar.md`, `prompts/classificar.md`, `prompts/narrar.md`
    (versão com manchete/gancho/fecho e escala de notas explícita).

## 12. Custo por vídeo de 25 min (defaults)

| Fase | Custo |
|---|---|
| Transcrição Groq | ~US$0,02 |
| Cenas + rosto (local) | R$0 |
| Classificação VLM (3b) | ~US$0,004 |
| Pontuação (1 chamada) | ~US$0,002 |
| Seleção / render / TTS inemavox | R$0 |
| **Total** | **≈ US$0,03** (re-cortes: R$0) |
