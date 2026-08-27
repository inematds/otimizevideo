import json
from otv.fases.ingest import ingest, id_de

def test_id_de():
    assert id_de("https://www.youtube.com/watch?v=dQYKcjvXhIY") == "dQYKcjvXhIY"
    assert id_de("https://youtu.be/abc123XYZ_-") == "abc123XYZ_-"
    assert id_de("/x/Minha Aula 01.mp4") == "minha-aula-01"

def test_ingest_arquivo_local(video_teste, tmp_path):
    d = ingest(str(video_teste), tmp_path)
    m = json.loads((d / "metadata.json").read_text())
    assert (d / "video.mp4").exists() and (d / "audio.opus").exists()
    assert abs(m["duracao_s"] - 6) < 0.2 and m["fonte"] == str(video_teste)

def test_ingest_e_idempotente_sem_deixar_arquivos_parciais(video_teste, tmp_path):
    d1 = ingest(str(video_teste), tmp_path)
    m1 = json.loads((d1 / "metadata.json").read_text())
    d2 = ingest(str(video_teste), tmp_path)
    m2 = json.loads((d2 / "metadata.json").read_text())
    assert d1 == d2
    assert m1["titulo"] == m2["titulo"]
    assert (d2 / "video.mp4").exists() and (d2 / "audio.opus").exists()
    assert not (d2 / "video.part.mp4").exists()
    assert not (d2 / "audio.part.opus").exists()
