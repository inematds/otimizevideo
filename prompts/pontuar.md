Você é um editor de vídeo experiente. Abaixo está a transcrição de um vídeo de {minutos} minutos ("{titulo}"),
dividida em unidades numeradas. Cada unidade traz: [id] duração tipo-de-imagem "texto falado".
Tipos de imagem: talking_head = apresentador na tela · slide · demo_tela · grafico · outro.

Vamos condensar o vídeo em cerca de {alvo} segundos mantendo os trechos ORIGINAIS (corte extrativo: nada é reescrito,
só escolhido). Modo: {modo_desc}

Tarefa — responda com 5 campos:
1. "manchete": uma frase-título de até 8 palavras que resume a tese do vídeo (vai aparecer escrita no topo da abertura).
2. "gancho": ids de 1 ou 2 unidades que melhor ABREM o vídeo condensado (a frase que prende nos primeiros segundos).
3. "fecho": ids de 1 ou 2 unidades que melhor FECHAM o vídeo (a conclusão, a frase final forte). Nunca agradecimento,
   pedido de inscrição ou despedida.
4. "topicos": os assuntos do vídeo, em ordem, com o intervalo de ids (de → ate) que cada um cobre.
5. "notas": para CADA unidade, "nota" de 0 a 10 = quão essencial ela é para o espectador entender o conteúdo central,
   e "motivo" de até 8 palavras.
   10 = tese, insight, número, resultado, demonstração-chave, conclusão
    7 = explicação necessária, exemplo forte, transição que liga ideias
    4 = contexto útil mas dispensável, repetição parcial
    0 = saudação, patrocínio, "curte e se inscreve", enrolação, transição vazia, despedida
   Regras: dê nota alta a uma unidade só se ela se entende SOZINHA (o espectador não vai ver o que veio antes).
   Prefira unidades com número, nome próprio, resultado ou afirmação forte. Não dê nota alta a duas unidades que
   dizem a mesma coisa — escolha a melhor.

Responda SOMENTE com JSON válido, sem comentários:
{{"manchete":"...","gancho":[ID],"fecho":[ID],"topicos":[{{"nome":"...","de":ID,"ate":ID}}],
  "notas":[{{"id":ID,"nota":N,"motivo":"..."}}]}}
Inclua TODAS as {n} unidades em "notas", na ordem.

UNIDADES:
{lista}
