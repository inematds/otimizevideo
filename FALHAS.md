# Changelog de falhas — otimizevideo

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-08-27 | `z-ai/glm-5.3-flash` via OpenRouter travou > 13 min pontuando 325 unidades (reasoning ilimitado; não pode ser desligado no endpoint) | mandar `reasoning: {effort: "low"}` + `max_tokens: 20000` → 64 s | infra |
| 2026-08-27 | Groq `verbose_json` com `timestamp_granularities=[word]` devolve `segments: null` → TypeError no spike | pedir `[word, segment]` e tratar `segments or []` | infra |
