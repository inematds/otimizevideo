import json
from otv.fases.render import montar_filtro, render
from otv.util.ffmpeg import probe


def test_montar_filtro_dois_segmentos():
    f = montar_filtro([{"in": 1.0, "out": 3.0, "estender_s": 0}, {"in": 4.0, "out": 5.5, "estender_s": 0}])
    assert "[0:v]trim=1.0:3.0,setpts=PTS-STARTPTS[v0]" in f
    assert "atrim=4.0:5.5" in f
    # nota: a asserção do brief ("concat=...[v][a]") está desatualizada — o filtro
    # concatena para os rótulos intermediários [vc][ac] e só depois deriva [a] (via
    # loudnorm) e [v] (via null, ou drawtext quando há manchete).
    assert "concat=n=2:v=1:a=1[vc][ac]" in f
    # os rótulos finais que os -map do render() consomem têm que estar expostos: o filtro
    # termina produzindo [v] (do null, sem manchete) depois de já ter produzido [a] (loudnorm)
    assert "[ac]loudnorm=I=-16:TP=-1.5[a]" in f
    assert f.endswith("[v]")


def test_montar_filtro_estende_com_freeze():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 1.5}])
    assert "tpad=stop_mode=clone:stop_duration=1.5" in f and "apad=pad_dur=1.5" in f


def test_render_duracao_bate(video_teste, tmp_path):
    import shutil
    shutil.copy(video_teste, tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(json.dumps({"id": "t"}))
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0}, {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]}))
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15
    assert (tmp_path / "saida" / "t" / "output.mp4").exists()


# --- adendo: manchete desenhada na abertura -------------------------------

def test_montar_filtro_manchete_escapa_dois_pontos():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}], manchete="A:B")
    # requisito, verbatim: dois-pontos escapado logo após "drawtext=text='...'"
    # (fontfile=, quando presente, vai no fim das opções do drawtext, não aqui na frente)
    assert "drawtext=text='A\\:B'" in f
    # sem manchete, o caminho continua sendo o null simples
    sem = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}])
    assert "[vc]null[v]" in sem and "drawtext=" not in sem


def test_montar_filtro_manchete_caracteres_perigosos_string():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}], manchete="A:B's \\ fim")
    # dois pontos escapados, aspa simples virou aspa tipográfica (não quebra o 'texto' do ffmpeg),
    # barra invertida duplicada
    assert "A\\:B’s \\\\ fim" in f


def test_montar_filtro_sem_audio_original_muda_de_verdade():
    # bug real: "volume=0dB" é ganho unitário (não muda nada); "volume=0" (fator linear
    # zero) é que silencia. sem_audio_original=True tem que emitir o segundo, não o primeiro.
    seg = [{"in": 0.0, "out": 2.0, "estender_s": 0}]
    com_cama = montar_filtro(seg, narracao=["a.wav"], sem_audio_original=False)
    mudo = montar_filtro(seg, narracao=["a.wav"], sem_audio_original=True)
    assert "volume=-18dB[o0]" in com_cama
    assert "volume=0[o0]" in mudo and "volume=0dB" not in mudo


def test_render_manchete_renderiza_de_verdade(video_teste, tmp_path):
    import shutil
    from PIL import Image

    shutil.copy(video_teste, tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(json.dumps({"id": "manchete"}))
    # total 5.5s (> os 4s da tarja) pra dar pra comparar um instante com tarja ativa (t=1)
    # e outro já sem ela (t=5), dentro da fixture video_teste de 6s.
    (tmp_path / "plan.json").write_text(json.dumps({
        "modo": "A", "alvo_s": 5.5, "total_s": 5.5, "narracao": None, "manchete": "A grande tese do vídeo",
        "segmentos": [{"in": 0.0, "out": 3.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 5.5, "unidades": [1], "estender_s": 0}]}))
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 5.5) < 0.15

    def brilho_topo(t):
        frame = tmp_path / f"frame_{t}.png"
        from otv.util.ffmpeg import thumb
        thumb(out, t, frame)
        img = Image.open(frame).convert("L")
        w, h = img.size
        faixa = img.crop((0, 0, w, int(h * 0.16)))
        return sum(faixa.getdata()) / (faixa.size[0] * faixa.size[1])

    b1 = brilho_topo(1.0)  # dentro dos 4s da tarja
    b5 = brilho_topo(5.0)  # fora (tarja já sumiu bem antes)
    assert abs(b1 - b5) > 10, f"brilho do topo não mudou o suficiente: t=1 -> {b1}, t=5 -> {b5}"
    print(f"BRILHO_TOPO t=1: {b1:.2f}  t=5: {b5:.2f}")


def test_render_manchete_caracteres_perigosos_render_de_verdade(video_teste, tmp_path):
    import shutil
    shutil.copy(video_teste, tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(json.dumps({"id": "perigo"}))
    (tmp_path / "plan.json").write_text(json.dumps({
        "modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "manchete": "Título: 'assim' e \\barra",
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]}))
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert out.exists()
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15
