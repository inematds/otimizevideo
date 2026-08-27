import json, subprocess
import pytest
from otv.fases.cenas import detectar_cenas, classificar_local, rosto_pct, cenas, classificar
from otv.provedores import llm as L


def test_detecta_corte_duro(tmp_path):
    p = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=25:duration=3",
        "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=25:duration=3",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", str(p)], check=True)
    c = detectar_cenas(p)
    assert len(c) == 2 and abs(c[1][0] - 3.0) < 0.2


def test_classificar_local():
    assert classificar_local(0.2) == "talking_head" and classificar_local(0.01) == "outro"


def test_rosto_pct_em_imagem_sem_rosto(tmp_path):
    p = tmp_path / "x.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:size=320x240",
                    "-frames:v", "1", str(p)], check=True)
    assert rosto_pct(p) == 0.0


def _gerar_face_sintetica(p):
    """Face desenhada com PIL — cabeça oval, olhos, sobrancelhas, nariz e boca.
    Detectada de forma estável pelo BlazeFace (verificado manualmente antes de
    virar teste)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 400), (200, 180, 160))
    d = ImageDraw.Draw(img)
    d.ellipse([100, 60, 300, 320], fill=(230, 200, 170), outline=(150, 110, 90), width=3)
    d.ellipse([140, 150, 180, 180], fill=(255, 255, 255), outline=(0, 0, 0))
    d.ellipse([220, 150, 260, 180], fill=(255, 255, 255), outline=(0, 0, 0))
    d.ellipse([155, 160, 170, 175], fill=(30, 20, 10))
    d.ellipse([235, 160, 250, 175], fill=(30, 20, 10))
    d.line([135, 140, 185, 135], fill=(80, 50, 30), width=4)
    d.line([215, 135, 265, 140], fill=(80, 50, 30), width=4)
    d.polygon([(200, 180), (190, 230), (210, 230)], fill=(210, 170, 140))
    d.arc([160, 240, 240, 290], start=0, end=180, fill=(150, 50, 50), width=5)
    img.save(p, quality=95)


def test_rosto_pct_em_imagem_com_rosto_normaliza_por_pixels(tmp_path):
    p = tmp_path / "face.jpg"
    _gerar_face_sintetica(p)
    r = rosto_pct(p)
    assert r > 0.08  # discrimina o limiar do classificar_local
    assert classificar_local(r) == "talking_head"
    assert r <= 1.0


def test_cenas_gera_scenes_json_e_thumbs(tmp_path, video_teste):
    from otv.config import carregar_config
    cfg = carregar_config()
    d = tmp_path / "proj"
    d.mkdir()
    (d / "video.mp4").write_bytes(video_teste.read_bytes())
    out = cenas(d, cfg)
    assert out == d / "scenes.json"
    dados = json.loads(out.read_text())
    assert "cenas" in dados and len(dados["cenas"]) >= 1
    for c in dados["cenas"]:
        assert set(c) == {"id", "ini", "fim", "thumb", "rosto_pct", "visual", "descricao", "pip"}
        assert (d / c["thumb"]).exists()
        assert c["descricao"] is None
        assert c["pip"] is False
        assert c["visual"] in ("talking_head", "outro")
    assert (d / "custos.json").exists()


def test_cenas_idempotente(tmp_path, video_teste):
    from otv.config import carregar_config
    cfg = carregar_config()
    d = tmp_path / "proj2"
    d.mkdir()
    (d / "video.mp4").write_bytes(video_teste.read_bytes())
    out1 = cenas(d, cfg)
    conteudo1 = out1.read_text()
    out2 = cenas(d, cfg)  # forcar=False -> não reprocessa
    assert out2.read_text() == conteudo1


class _FakeLLM:
    nome = "fake/vlm"

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def chat_json(self, prompt, imagens=None):
        self.chamadas.append((prompt, imagens))
        return self.respostas.pop(0), {"cost": 0.01, "prompt_tokens": 10}


def _scenes_json(n, rosto_pcts=None):
    rosto_pcts = rosto_pcts or [0.01] * n
    return {"cenas": [
        {"id": i, "ini": float(i), "fim": float(i + 1), "thumb": f"thumbs/{i:03d}.jpg",
         "rosto_pct": rosto_pcts[i], "visual": "outro", "descricao": None, "pip": False}
        for i in range(n)
    ]}


def test_classificar_com_llm_mockado_em_lotes_de_20(tmp_path, monkeypatch):
    from otv.config import carregar_config
    cfg = carregar_config()
    d = tmp_path / "proj3"
    d.mkdir()
    (d / "scenes.json").write_text(json.dumps(_scenes_json(25)))

    resp_lote1 = {"cenas": [{"i": i, "visual": "slide", "pip": False, "descricao": f"desc {i}"} for i in range(20)]}
    resp_lote2 = {"cenas": [{"i": i, "visual": "demo_tela", "pip": False, "descricao": f"desc {i}"} for i in range(5)]}
    fake = _FakeLLM([resp_lote1, resp_lote2])
    monkeypatch.setattr(L, "criar_llm", lambda cfg, slot: fake)

    out = classificar(d, cfg, provedor="glm")
    assert out == d / "scenes.json"
    assert len(fake.chamadas) == 2
    assert len(fake.chamadas[0][1]) == 20 and len(fake.chamadas[1][1]) == 5

    dados = json.loads(out.read_text())["cenas"]
    assert dados[0]["visual"] == "slide" and dados[0]["descricao"] == "desc 0"
    assert dados[20]["visual"] == "demo_tela" and dados[20]["descricao"] == "desc 0"
    assert (d / "custos.json").exists()
    custos = json.loads((d / "custos.json").read_text())
    assert custos["classificar"]["provedor"] == "fake/vlm"
    assert custos["classificar"]["uso"]["cost"] == pytest.approx(0.02)


def test_classificar_rosto_grande_vence_vlm(tmp_path, monkeypatch):
    from otv.config import carregar_config
    cfg = carregar_config()
    d = tmp_path / "proj4"
    d.mkdir()
    # cena 0: rosto grande (>=0.15) -> deve virar talking_head mesmo se o VLM disser slide
    # cena 1: rosto pequeno -> segue o VLM
    (d / "scenes.json").write_text(json.dumps(_scenes_json(2, rosto_pcts=[0.2, 0.05])))
    resp = {"cenas": [
        {"i": 0, "visual": "slide", "pip": False, "descricao": "algo"},
        {"i": 1, "visual": "grafico", "pip": True, "descricao": "outro algo"},
    ]}
    fake = _FakeLLM([resp])
    monkeypatch.setattr(L, "criar_llm", lambda cfg, slot: fake)

    out = classificar(d, cfg, provedor="glm")
    dados = json.loads(out.read_text())["cenas"]
    assert dados[0]["visual"] == "talking_head"
    assert dados[1]["visual"] == "grafico"
    assert dados[1]["pip"] is True


def test_classificar_idempotente_nao_chama_llm_de_novo(tmp_path, monkeypatch):
    from otv.config import carregar_config
    cfg = carregar_config()
    d = tmp_path / "proj5"
    d.mkdir()
    dados = _scenes_json(1)
    dados["cenas"][0]["descricao"] = "já classificada"
    (d / "scenes.json").write_text(json.dumps(dados))

    def _boom(cfg, slot):
        raise AssertionError("não deveria chamar criar_llm quando já está classificado")

    monkeypatch.setattr(L, "criar_llm", _boom)
    out = classificar(d, cfg, provedor="glm")
    assert json.loads(out.read_text())["cenas"][0]["descricao"] == "já classificada"
