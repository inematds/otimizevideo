import pytest
from otv.util.ffmpeg import probe, extrair_audio, thumb

def test_probe(video_teste):
    m = probe(video_teste)
    assert abs(m["duracao_s"] - 6) < 0.2 and m["largura"] == 320 and m["fps"] == 25

def test_extrair_audio_e_thumb(video_teste, tmp_path):
    extrair_audio(video_teste, tmp_path / "a.opus")
    thumb(video_teste, 1.0, tmp_path / "t.jpg")
    assert (tmp_path / "a.opus").stat().st_size > 1000
    assert (tmp_path / "t.jpg").stat().st_size > 500

def test_extrair_audio_falha_nao_deixa_arquivo_parcial(tmp_path):
    entrada_invalida = tmp_path / "nao-existe.mp4"
    saida = tmp_path / "audio.opus"
    with pytest.raises(RuntimeError):
        extrair_audio(entrada_invalida, saida)
    assert not saida.exists()
