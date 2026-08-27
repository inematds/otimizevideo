import json, shutil
import pytest
from otv.fases.render import montar_filtro, render
from otv.util.ffmpeg import probe, thumb


def _preparar(tmp_path, video_teste, id_, plan):
    """Setup comum aos testes de render real: copia o vídeo da fixture, escreve
    metadata.json e plan.json. Retorna tmp_path (mesma pasta que os testes já usavam)."""
    shutil.copy(video_teste, tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(json.dumps({"id": id_}))
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    return tmp_path


def _pixels_glifo(video, t, tmp_path, tag=""):
    """Conta pixels quase-brancos (>200 em escala de cinza) na faixa dos 16% superiores
    do quadro em t. Usado pra confirmar que o TEXTO da manchete realmente apareceu — o
    drawbox sozinho escurece a faixa mesmo com o texto em branco (bug do '%'), então
    contar glifo é o critério certo, não só brilho médio da faixa."""
    from PIL import Image
    frame = tmp_path / f"frame_{tag}_{t}.png"
    thumb(video, t, frame)
    img = Image.open(frame).convert("L")
    w, h = img.size
    faixa = img.crop((0, 0, w, int(h * 0.16)))
    return sum(1 for p in faixa.getdata() if p > 200)


def test_montar_filtro_dois_segmentos():
    f = montar_filtro([{"in": 1.0, "out": 3.0, "estender_s": 0}, {"in": 4.0, "out": 5.5, "estender_s": 0}])
    # Um input por segmento (índice = número do segmento), com o corte já feito por
    # -ss/-t na entrada -- por isso o trim aqui é relativo (0:duração), não absoluto.
    # Ver a docstring de montar_filtro: com um input só, os quadros crus dos segmentos
    # ainda não consumidos empilhavam nas filas do concat (60,9 GB / host travado).
    assert "[0:v]trim=0:2.0,setpts=PTS-STARTPTS[v0]" in f
    assert "[1:v]trim=0:1.5,setpts=PTS-STARTPTS[v1]" in f
    assert "[1:a]atrim=0:1.5" in f
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
    _preparar(tmp_path, video_teste, "t", {"modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0}, {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15
    assert (tmp_path / "saida" / "t" / "output.mp4").exists()


# --- adendo: manchete desenhada na abertura -------------------------------

def test_montar_filtro_manchete_escapa_dois_pontos():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}], manchete="A:B")
    # requisito, verbatim: dois-pontos escapado logo após "drawtext=text='...'"
    # (fontfile= e expansion=none, quando presentes, vão no fim das opções do drawtext)
    assert "drawtext=text='A\\:B'" in f
    # sem manchete, o caminho continua sendo o null simples
    sem = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}])
    assert "[vc]null[v]" in sem and "drawtext=" not in sem


def test_montar_filtro_manchete_caracteres_perigosos_string():
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}], manchete="A:B's \\ fim")
    # dois pontos escapados, aspa simples virou aspa tipográfica (não quebra o 'texto' do ffmpeg),
    # barra invertida duplicada
    assert "A\\:B’s \\\\ fim" in f


def test_montar_filtro_manchete_tem_expansion_none():
    # Achado 1 da rodada de correção 1: sem expansion=none, "%" solto (ex.: "100% de
    # desconto") vira "%{...}" pro drawtext (expansion=normal é o default) — gera um
    # WARNING silencioso ("Stray %"), não erro, e o texto some do vídeo sem sinal de
    # falha nenhum (run() só olha returncode, que continua 0). expansion=none elimina
    # essa classe de bug inteira em vez de tentar escapar cada '%' (testado à parte que
    # nem "%%" resolve tudo).
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0}], manchete="100% de certeza")
    assert ":expansion=none" in f
    assert "100% de certeza" in f  # não escapamos o '%' -- expansion=none dispensa isso


def test_montar_filtro_sem_audio_original_muda_de_verdade():
    # bug real: "volume=0dB" é ganho unitário (não muda nada); "volume=0" (fator linear
    # zero) é que silencia. sem_audio_original=True tem que emitir o segundo, não o primeiro.
    seg = [{"in": 0.0, "out": 2.0, "estender_s": 0}]
    com_cama = montar_filtro(seg, narracao=["a.wav"], sem_audio_original=False)
    mudo = montar_filtro(seg, narracao=["a.wav"], sem_audio_original=True)
    assert "volume=-18dB[o0]" in com_cama
    assert "volume=0[o0]" in mudo and "volume=0dB" not in mudo


def test_render_manchete_renderiza_de_verdade(video_teste, tmp_path):
    # total 5.5s (> os 4s da tarja) pra dar pra comparar um instante com tarja ativa (t=1)
    # e outro já sem ela (t=5), dentro da fixture video_teste de 6s.
    _preparar(tmp_path, video_teste, "manchete", {
        "modo": "A", "alvo_s": 5.5, "total_s": 5.5, "narracao": None, "manchete": "A grande tese do vídeo",
        "segmentos": [{"in": 0.0, "out": 3.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 5.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 5.5) < 0.15

    # Achado 2 da rodada de correção 1: brilho médio da faixa não detecta manchete em
    # branco, porque o drawbox continua desenhando (escurecendo o topo) mesmo sem
    # nenhum glifo. O critério certo é contar pixels quase-brancos (o texto em si), e
    # afirmar que há uma quantidade significativa deles -- não comparar com t=5, porque
    # o fundo sintético (testsrc) já tem barras claras sem tarja nenhuma, o que tornaria
    # essa comparação um falso positivo/negativo dependendo do padrão de fundo.
    glifo_com_tarja = _pixels_glifo(out, 1.0, tmp_path, "com")   # dentro dos 4s, texto tem que aparecer
    assert glifo_com_tarja > 200, f"poucos pixels de glifo em t=1 (tarja ativa): {glifo_com_tarja}"
    print(f"GLIFO_PIXELS t=1(com manchete): {glifo_com_tarja}")


def test_render_manchete_com_porcentagem_nao_apaga_o_texto(video_teste, tmp_path):
    # Regressão do Achado 1: manchete plausível em PT-BR vinda de LLM ("50% de desconto",
    # "aumentou 30%") não pode sumir silenciosamente. Confirma que o glifo aparece de
    # verdade (não só que o ffmpeg não falhou).
    _preparar(tmp_path, video_teste, "percentual", {
        "modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "manchete": "100% de certeza de verdade",
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    glifo = _pixels_glifo(out, 1.0, tmp_path, "pct")
    assert glifo > 200, f"manchete com '%' sumiu (bug do Stray % voltou): pixels de glifo = {glifo}"
    print(f"GLIFO_PIXELS_COM_PERCENTUAL t=1: {glifo}")


def test_render_manchete_caracteres_perigosos_render_de_verdade(video_teste, tmp_path):
    _preparar(tmp_path, video_teste, "perigo", {
        "modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "manchete": "Título: 'assim' e \\barra",
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert out.exists()
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15


# --- Achados 4 e 5 da rodada de correção 1 --------------------------------

def test_montar_filtro_narracao_tem_fade_out():
    # Achado 1 da rodada de correção 1 da Task 10: a Task 10 já trunca o roteiro pelo
    # orçamento de palavras antes do TTS, mas a duração real do wav não é perfeitamente
    # previsível a partir da contagem de palavras -- este afade=t=out na trilha de narração
    # ([n{k}]) é a rede de segurança contra um corte abrupto no atrim=0:{d+ext}, com a
    # mesma duração de 0.04s que a trilha original já usa.
    seg = [{"in": 0.0, "out": 2.0, "estender_s": 0.5}]
    f = montar_filtro(seg, narracao=["a.wav"])
    assert "afade=t=out:st=2.460:d=0.04[n0]" in f  # d+ext=2.5 -> st=2.5-0.04=2.46
    # com 1 segmento, os inputs de vídeo ocupam o índice 0 e a narração começa no 1;
    # com 2 segmentos ela começa no 2 -- é esse deslocamento que render() tem que casar.
    f2 = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 0},
                        {"in": 3.0, "out": 5.0, "estender_s": 0}], narracao=["a.wav", "b.wav"])
    assert "[2:a]apad" in f2 and "[3:a]apad" in f2


def test_render_narracao_com_null_falha_com_mensagem_clara(video_teste, tmp_path):
    # Achado 4: pular o None desalinharia todos os índices [k+1:a] seguintes,
    # silenciosamente -- falhar rápido e alto é o comportamento certo. O que faltava era
    # uma mensagem clara (a Task 10 é quem gera esse arquivo, tem que ser 1 wav/segmento).
    _preparar(tmp_path, video_teste, "narr-null", {
        "modo": "A", "alvo_s": 3, "total_s": 3.0,
        "narracao": {"arquivos": ["seg_00.wav", None]},
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    with pytest.raises(RuntimeError, match="nunca null"):
        render(tmp_path, {"saida": str(tmp_path / "saida")})


def test_render_rapido_produz_mp4_legivel(video_teste, tmp_path):
    # Achado 5: --rapido (concat demuxer + -c copy) sem cobertura nenhuma. Smoke test
    # barato -- NÃO afirma duração exata: esse caminho corta em keyframe e é aproximado
    # de propósito (pode variar por até um GOP inteiro), afirmar duração exata criaria
    # um teste frágil.
    _preparar(tmp_path, video_teste, "rapido", {
        "modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")}, rapido=True)
    assert out.exists()
    d = probe(out)["duracao_s"]
    assert d > 0


# --- regressão do travamento do host (2026-08-27) --------------------------

def test_render_nao_bufferiza_video_inteiro(video_teste, tmp_path):
    """Segmentos esparsos ao longo do fonte não podem custar o vídeo inteiro em RAM.

    O bug: com `[0:v]trim` N vezes sobre um input único, o ffmpeg decodifica linearmente
    e empilha os quadros crus dos segmentos 1..N-1 nas filas do concat enquanto ele
    consome o segmento 0 -- num fonte de 20 min foram 60,9 GB e o host travou. O teste
    afirma o INVARIANTE que evita isso (um `-i` por segmento, trims relativos), porque
    medir RSS de verdade exigiria um fonte grande e um teste lento e frágil.
    """
    plan = {"modo": "A", "alvo_s": 2, "total_s": 2.0, "narracao": None,
            "segmentos": [{"in": 0.0, "out": 1.0, "unidades": [0], "estender_s": 0},
                          {"in": 5.0, "out": 6.0, "unidades": [1], "estender_s": 0}]}
    _preparar(tmp_path, video_teste, "esparso", plan)
    f = montar_filtro(plan["segmentos"])
    assert "[1:v]" in f, "segundo segmento tem que vir de um input próprio, não de [0:v]"
    assert "trim=0:" in f and "trim=5.0" not in f, "trim tem que ser relativo ao input já seekado"
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    # e o corte esparso continua correto: 1s do início + 1s a partir dos 5s = 2s
    assert abs(probe(out)["duracao_s"] - 2.0) < 0.15


def test_run_ffmpeg_tem_teto_de_memoria():
    """Cinto de segurança: o ffmpeg roda dentro de um scope com MemoryMax quando dá.

    Fail-open de propósito (sem systemd-run, roda sem teto), então o teste aceita as duas
    saídas -- o que ele guarda é que, quando o prefixo existe, ele carrega o MemoryMax.
    """
    from otv.util.ffmpeg import _prefixo_scope, MEMMAX
    pref = _prefixo_scope()
    if pref:
        assert pref[0] == "systemd-run" and f"MemoryMax={MEMMAX}" in pref
    else:
        assert pref == []


# --- Task 10b: modo A+ (segmento talking_head trocado por ilustração) ------

def _png_solido(path, cor="red", w=320, h=180):
    from otv.util.ffmpeg import run
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={cor}:s={w}x{h}",
         "-frames:v", "1", str(path)])
    return path


def test_montar_filtro_substituir_usa_movie_e_mantem_audio_original(tmp_path):
    # O vídeo do segmento 0 vem da imagem (movie=...,zoompan), mas o áudio continua sendo
    # o [0:a] do input original -- é isso que faz o modo A+ preservar a fala.
    segs = [{"in": 0.0, "out": 2.0, "estender_s": 0, "substituir": "subst/seg_00.png"},
            {"in": 5.0, "out": 7.0, "estender_s": 0}]
    f = montar_filtro(segs, dir=tmp_path, tamanho=(1920, 1080, 25))
    assert f"movie={tmp_path / 'subst/seg_00.png'}" in f
    assert "zoompan=" in f and "d=50:" in f          # 2.0s * 25fps
    assert "[0:v]trim=" not in f                      # o vídeo original do seg 0 não é usado
    assert "[0:a]atrim=0:2.0" in f                    # ...mas o áudio dele, sim
    assert "[1:v]trim=0:2.0" in f                     # segmento não-substituído segue igual


def test_montar_filtro_substituir_absorve_a_extensao_sem_tpad(tmp_path):
    # zoompan gera d=N quadros a partir de uma imagem só, então ele já cobre d+ext --
    # tpad (que clona o último quadro de um vídeo) não faz sentido aqui.
    f = montar_filtro([{"in": 0.0, "out": 2.0, "estender_s": 1.0, "substituir": "s.png"}],
                      dir=tmp_path, tamanho=(1920, 1080, 25))
    assert "d=75:" in f and "tpad=" not in f          # (2.0+1.0)*25
    assert "apad=pad_dur=1.0" in f                    # o áudio ainda é esticado


def test_render_substituir_troca_o_video_e_preserva_duracao(video_teste, tmp_path):
    (tmp_path / "subst").mkdir()
    _png_solido(tmp_path / "subst" / "seg_00.png", "red")
    _preparar(tmp_path, video_teste, "subst", {
        "modo": "A", "alvo_s": 3, "total_s": 3.0, "narracao": None,
        "segmentos": [{"in": 0.5, "out": 2.0, "unidades": [0], "estender_s": 0, "substituir": "subst/seg_00.png"},
                      {"in": 3.0, "out": 4.5, "unidades": [1], "estender_s": 0}]})
    out = render(tmp_path, {"saida": str(tmp_path / "saida")})
    assert abs(probe(out)["duracao_s"] - 3.0) < 0.15
    # em t=0.7 (dentro do segmento substituído) o quadro tem que ser vermelho chapado,
    # não o testsrc colorido da fixture
    from PIL import Image
    frame = tmp_path / "f_subst.png"; thumb(out, 0.7, frame)
    r, g, b = Image.open(frame).convert("RGB").resize((1, 1)).getpixel((0, 0))
    assert r > 150 and g < 80 and b < 80, f"segmento não foi substituído pela imagem: RGB={(r, g, b)}"
