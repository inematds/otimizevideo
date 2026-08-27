# Classificação visual — o gargalo (anotado em 2026-08-27, nada implementado)

> Anotação, não plano. O pipeline está bom o bastante hoje; isto é onde investir quando o
> assunto voltar. Três dos quatro defeitos encontrados na validação de 2026-08-27 nasceram
> aqui, e nenhum deles no núcleo de corte.

## Por que é o gargalo

A classificação decide **três coisas de uma vez**, e nenhuma delas é opcional:

- o que o **modo B/C** pode selecionar (`VISUAL_MODO` filtra por `slide|demo_tela|grafico`);
- o que o **modo A+** substitui (só o que está marcado `talking_head`);
- de onde a **abertura** tira b-roll (`sem_apresentador()`).

Se ela erra, os três erram junto — e erram em silêncio, porque nada no pipeline questiona um
rótulo depois que ele é escrito no `scenes.json`.

## Como funciona hoje

```
PySceneDetect (proxy 360p) → 378 cenas (mediana 2,3 s, máxima 20,8 s)
  → 1 miniatura por cena, tirada em ini + min(1, dur/2)
    → mediapipe BlazeFace nessa miniatura → rosto_pct (fração de área do maior rosto)
    → VLM (lote de 20 miniaturas) → visual + descricao + pip
      → rosto_pct >= 0.08 sobrepõe o rótulo do VLM
```

## As seis falhas estruturais

1. **Um quadro por cena é uma janela cega.** 72 das 378 cenas passam de 5 s. Se o apresentador
   entra no segundo 4, a miniatura do segundo 1 não vê nada e a cena inteira fica "sem rosto".
   Foi exatamente o caso do 1:29 (cenas 118/119, 7,3 s e 3,8 s, `rosto_pct` 0,0).
2. **O VLM herda a mesma cegueira.** Ele julga a cena pela mesma miniatura única — não é uma
   segunda opinião independente, é a mesma amostra com outro classificador em cima.
3. **Rótulo binário para cena mista.** Uma cena com apresentador *e* demonstração de tela tem
   que escolher um rótulo. Não existe "parcialmente".
4. **`pip` não é verificado.** O flag de apresentador em janelinha vem só do VLM; o detector de
   rosto nunca confirma.
5. **Tamanho de rosto é um proxy frouxo.** Uma pessoa ao fundo de uma imagem de laboratório
   dispara; um apresentador filmado de longe não dispara.
6. **Granularidade de cena ≠ granularidade de corte.** Um segmento atravessa várias cenas com
   rótulos diferentes e fica com `max(rótulo não-"outro")` — escolha arbitrária. É por isso
   que "tirar só o apresentador" de um segmento misto não tem resposta boa hoje.

## Ideias, do mais barato ao mais caro

**A. Amostrar 3–5 quadros por cena.** Detecção local, CPU, sem chamada paga. Densidade
proporcional à duração (≈1 quadro a cada 2 s, teto de 6). Resolve a falha 1 — teria pego o
1:29. Custo: ~4× o tempo da fase `cenas` (hoje ~2 min neste vídeo). **É a de maior retorno.**

**B. Guardar uma linha do tempo de rosto, não um rótulo por cena.** Em vez de um número por
cena, guardar `rosto` por instante amostrado. Aí qualquer consumidor pergunta "este intervalo
exato tem rosto?" na granularidade do corte, não da cena. Dissolve a falha 6 e permite resposta
parcial. Muda o contrato do `scenes.json` — é a mudança estrutural do conjunto.

**C. Quebrar a cena quando o estado muda no meio.** Se a linha do tempo de rosto vira no meio de
uma cena, dividir a cena ali. Torna os rótulos honestos e dá fronteiras mais finas ao cortador.

**D. Confiança e abstenção.** Hoje toda cena recebe rótulo. Onde o detector de rosto e o VLM
discordam, marcar `incerto` e deixar de fora do B/C em vez de incluir em silêncio.

**E. Sinais determinísticos antes do VLM.** Densidade de bordas/texto para slide e demo de tela,
variação de histograma para gráfico, magnitude de movimento. De graça, testável, e sobra pro VLM
só o resto ambíguo — que é onde ele de fato ajuda.

**F. Contact sheet como artefato de revisão.** Um PNG único com a grade das miniaturas e seus
rótulos. Dá pra varrer 378 cenas com o olho em 10 segundos e pegar erro de classificação
**antes** de gastar render. Encaixa na ideia mais geral de "artefato de revisão por fase" — o
`roteiro.md` já faz isso para a narração; o visual não tem equivalente.

**G. Conjunto de calibração.** Rotular ~40 cenas à mão, uma vez, e usar como teste de regressão
de qualquer mudança no classificador. Transforma "acho que melhorou" em número.

## O que NÃO resolve

- Mexer no limiar de rosto. Já foi unificado em 0,08; o problema restante é **medição**, não
  julgamento.
- Trocar o modelo de visão ou refinar o prompt de classificação. Ele não está errando por
  incompetência — está julgando com uma amostra insuficiente.
- Substituir segmento inteiro quando ele é misto. Isso é decisão de edição (perder a demo junto
  com o apresentador), não correção de bug.


---

# Anotado à parte — redundância no arranque (2026-08-27)

Nos primeiros ~20 s a mesma ideia aparece três vezes: o bloco de capa da chamada, a tarja de
manchete desenhada sobre o corpo, e o gancho do vídeo. A causa é estrutural — o gerador da
chamada recebe a **manchete** como insumo e naturalmente a parafraseia, e a manchete por sua vez
foi extraída do gancho.

Duas saídas, nenhuma implementada: (a) o prompt da chamada passa a receber a manchete como
"isto já está na tela, não repita"; ou (b) **a tarja de manchete não é desenhada quando existe
abertura**, já que a capa da chamada cumpre esse papel melhor. A segunda parece mais certa —
dois letreiros com a mesma frase a 13 s de distância é redundância de layout, não só de texto.

Também anotado: `"As of this year, it is."` traduzido literalmente vira `"A partir deste ano,
é."` — gramaticalmente completo, mas termina num monossílabo átono e soa cortado. O inglês apoia
o peso no "it **is**"; o português não tem onde apoiar. Casos assim pedem uma reescrita com
verbo pleno ("passou a ser"), não uma tradução mais fiel.
