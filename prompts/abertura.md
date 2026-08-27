Você escreve a ABERTURA (chamada) de um vídeo condensado, em português do Brasil. Ela vem ANTES do
conteúdo e existe para uma coisa só: fazer a pessoa ficar. Não é resumo, não é índice, não é
introdução educada.

O vídeo se chama "{titulo}" e a manchete escolhida foi: "{manchete}".
O que o vídeo de fato mostra, em ordem:

{lista}

Escreva exatamente {n} blocos. O bloco 0 é a CAPA (o gancho); os outros são as promessas do que
vem — cada um sobre uma coisa concreta que aparece na lista acima.

Para cada bloco:
- **`titulo`**: o texto GARRAFAL que aparece na tela. No máximo 4 palavras, em caixa alta,
  sem ponto final. É manchete de capa de revista: concreta, forte, sem adjetivo vazio.
  Nada de "INCRÍVEL", "VOCÊ PRECISA VER", "IMPERDÍVEL".
- **`fala`**: a narração desse bloco, 1 frase, entre 8 e 16 palavras. Ela conversa com o
  espectador e emenda no bloco seguinte. Não repita o texto garrafal palavra por palavra.

Não invente fato: só prometa o que está na lista acima. Números e nomes próprios exatamente como
aparecem lá.

O bloco 0 tem que provocar uma pergunta na cabeça de quem assiste. O último bloco entrega a
promessa maior e emenda no conteúdo — termine em suspensão, sem "vamos lá" nem "confira".

Responda SOMENTE JSON: {{"blocos":[{{"k":0,"titulo":"...","fala":"..."}}, ...]}} com os {n} blocos, na ordem.
