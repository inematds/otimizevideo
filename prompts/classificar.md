Você recebe {n} imagens numeradas (imagem 0, imagem 1, …), uma por cena de um vídeo educativo.
Classifique CADA imagem em exatamente uma categoria:
- talking_head: uma pessoa falando para a câmera é o elemento principal da cena
- slide: slide de apresentação (título, bullets, texto grande sobre fundo liso)
- demo_tela: gravação de tela — software, terminal, site, código, app
- grafico: gráfico, tabela, diagrama, mapa, dado visual
- outro: qualquer outra coisa (b-roll, cena de filme, logo, transição, foto)
Se a pessoa aparece pequena num canto (PiP) sobre uma tela ou slide, classifique pela tela/slide e marque "pip": true.
Descreva em até 8 palavras o que aparece.

Responda SOMENTE JSON, com todas as {n} imagens, na ordem:
{{"cenas":[{{"i":0,"visual":"slide","pip":false,"descricao":"..."}}, ...]}}
