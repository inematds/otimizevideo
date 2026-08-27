import json
from pathlib import Path
import pytest
from otv.provedores.transcricao import normalizar_palavras, de_groq, PROVEDORES
from otv.fases.transcrever import transcrever

def test_normalizar_torna_monotonico():
    p = normalizar_palavras([{"t": "a", "ini": 0.0, "fim": 0.5}, {"t": "b", "ini": 0.4, "fim": 0.9},
                             {"t": "c", "ini": 1.85, "fim": 1.7}])
    assert p[1]["ini"] == 0.5                 # não começa antes da anterior terminar
    assert p[2]["fim"] >= p[2]["ini"] + 0.05  # fim nunca antes do início

def test_de_groq_contrato():
    t = de_groq(json.loads(Path("tests/fixtures/groq_resp.json").read_text()))
    assert t["idioma"] == "en" and t["provedor"] == "groq/whisper-large-v3-turbo"
    assert [w["t"] for w in t["palavras"]] == ["Hello", "world.", "Second", "one."]
    assert t["fins_segmento"] == [0.9, 2.1]
    assert t["palavras"][1]["ini"] == 0.5

@pytest.mark.parametrize("segments", [None, [], "ausente"])
def test_de_groq_sobrevive_sem_segments(segments):
    resp = {"language": "en", "words": [{"word": "oi", "start": 0.0, "end": 0.3}]}
    if segments != "ausente":
        resp["segments"] = segments
    t = de_groq(resp)
    assert t["fins_segmento"] == []
    assert t["palavras"][0]["t"] == "oi"

def test_transcrever_idempotente(tmp_path):
    (tmp_path / "transcript.json").write_text('{"idioma": "en", "provedor": "x", "palavras": [], "fins_segmento": []}')
    out = transcrever(tmp_path, cfg={}, provedor="naoexiste", forcar=False)
    assert out == tmp_path / "transcript.json"

def test_transcrever_chama_provedor_e_registra_custo(tmp_path, monkeypatch):
    palavras = [{"t": str(i), "ini": float(i), "fim": float(i) + 0.5} for i in range(60)]
    fake = {"idioma": "pt", "provedor": "fake", "palavras": palavras, "fins_segmento": [59.5]}
    monkeypatch.setitem(PROVEDORES, "groq", lambda a, cfg: fake)
    out = transcrever(tmp_path, cfg={"transcricao": "groq"}, forcar=True)
    assert out == tmp_path / "transcript.json"
    assert json.loads(out.read_text())["palavras"] == palavras
    custos = json.loads((tmp_path / "custos.json").read_text())
    assert custos["transcrever"]["palavras"] == 60

def test_transcrever_poucas_palavras_estoura(tmp_path, monkeypatch):
    fake = {"idioma": "pt", "provedor": "fake", "palavras": [{"t": "oi", "ini": 0.0, "fim": 0.3}], "fins_segmento": []}
    monkeypatch.setitem(PROVEDORES, "groq", lambda a, cfg: fake)
    with pytest.raises(RuntimeError):
        transcrever(tmp_path, cfg={"transcricao": "groq"}, forcar=True)
    assert not (tmp_path / "transcript.json").exists()
