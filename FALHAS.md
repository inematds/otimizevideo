# Changelog de falhas — otimizevideo

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-08-27 | Gemini API nativa: 503 em todos os modelos 3.x (3 rodadas, 30 s entre elas); 2.5 desligados p/ contas novas | tentar mais tarde; slot `gemini_video` fica opcional, GLM via OpenRouter cobre a etiqueta visual | infra |
| 2026-08-27 | `z-ai/glm-5.3-flash` via OpenRouter travou > 13 min pontuando 325 unidades (reasoning ilimitado; não pode ser desligado no endpoint) | mandar `reasoning: {effort: "low"}` + `max_tokens: 20000` → 64 s | infra |
| 2026-08-27 | Groq `verbose_json` com `timestamp_granularities=[word]` devolve `segments: null` → TypeError no spike | pedir `[word, segment]` e tratar `segments or []` | infra |
| 2026-08-27 | `normalizar_palavras` do brief da Task 3 arredondava fim/ini só no fim: `round(1.85+0.05,3)==1.9`, mas `1.9 < 1.85+0.05` em float puro (1 ULP) → o próprio teste do brief falhava | arredondar ini/fim por palavra ANTES de checar o gap mínimo, e revalidar/"bumpar" (+0.051) no domínio já arredondado | prompt |
