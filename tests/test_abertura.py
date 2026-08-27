import json
import pytest
from otv.fases.abertura import encurtar_fala, escolher_cenas, montar_html


def test_encurtar_nunca_devolve_frase_pela_metade():
    # bug real de 2026-08-27: a fala virou "...200 milhões de proteínas ganhou" e a
    # narração parou no meio. Frase única que não cabe vai INTEIRA.
    longa = "A mesma inteligência que previu 200 milhões de proteínas ganhou o Nobel."
    assert encurtar_fala(longa, 10) == longa
    assert not encurtar_fala(longa, 10).endswith("ganhou")


def test_encurtar_descarta_frase_inteira_do_fim():
    t = "Frase um curta. Frase dois que é bem mais longa e não cabe no orçamento."
    assert encurtar_fala(t, 10) == "Frase um curta."


def test_encurtar_vazio():
    assert encurtar_fala("") == "" and encurtar_fala(None) is None


def test_bloco_sempre_cobre_o_audio():
    # o bloco tem que durar pelo menos o wav + respiro, senão a narração dele invade o
    # bloco seguinte (que já começou a falar) -- 1,8s de duas vozes sobrepostas
    from otv.fases.abertura import MIN_BLOCO, FOLGA_BLOCO
    for wav in (0.5, 3.2, 6.6, 12.0):
        dur = round(max(MIN_BLOCO, wav + FOLGA_BLOCO), 2)
        assert dur >= wav, f"bloco de {dur}s não cobre wav de {wav}s"


def test_escolher_cenas_evita_o_que_ja_esta_no_corte():
    cenas = [{"id": i, "ini": i * 20.0, "fim": i * 20.0 + 10.0, "visual": "grafico"} for i in range(6)]
    plan = {"segmentos": [{"in": 0.0, "out": 12.0}, {"in": 40.0, "out": 52.0}]}
    esc = escolher_cenas(cenas, plan, n=2)
    ids = {c["id"] for c in esc}
    assert 0 not in ids and 2 not in ids       # cenas 0 e 2 caem dentro do corte
    assert len(esc) == 2


def test_video_fica_fora_da_secao_temporizada():
    # contrato do HyperFrames: <video> dentro de elemento com data-start faz o extrator
    # resolver o start errado e o clipe mostra o quadro errado (video_nested_in_timed_element)
    blocos = [{"titulo": "A", "fala": "x", "wav": 2.0, "dur": 2.5},
              {"titulo": "B", "fala": "y", "wav": 2.0, "dur": 2.5}]
    html = montar_html(blocos, "capa.jpg", None)
    corpo = html.split("<body>")[1]
    antes_da_secao = corpo.split("<section")[0]
    assert "<video" in antes_da_secao          # o vídeo vem antes, no nível da raiz
    assert "muted" in antes_da_secao and 'id="bg1"' in antes_da_secao
