import json, subprocess
from otv.fases.narrar import narrar, ajustar_extensao
import otv.fases.narrar as Nn

def test_ajustar_extensao():
    segs = [{"in": 0, "out": 5.0}, {"in": 10, "out": 14.0}]
    ajustar_extensao(segs, [4.0, 6.5])          # narração 4 s cabe; 6.5 s excede 2.5 s
    assert segs[0]["estender_s"] == 0 and segs[1]["estender_s"] == 2.5

def test_narrar_gera_wavs_e_atualiza_plan(tmp_path, monkeypatch):
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "B", "alvo_s": 10, "total_s": 8.0, "narracao": None,
        "segmentos": [{"in": 0, "out": 4.0, "unidades": [0], "texto": "a", "estender_s": 0},
                      {"in": 6, "out": 10.0, "unidades": [2], "texto": "c", "estender_s": 0}]}))
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": [{"id": i, "texto": t, "ini": i * 3, "fim": i * 3 + 2} for i, t in enumerate("abc")]}))
    class FakeLLM:
        nome = "fake"
        def chat_json(self, p, imagens=None): return {"narracao": [{"k": 0, "texto": "um"}, {"k": 1, "texto": "dois"}]}, {}
    def fake_tts(texto, out, cfg, provedor=None):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300", "-t", "3", str(out)], check=True); return out
    monkeypatch.setattr(Nn, "criar_llm", lambda cfg, slot: FakeLLM())
    monkeypatch.setattr(Nn, "tts", fake_tts)
    narrar(tmp_path, {"pontuacao": "glm", "tts": "inemavox"})
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["narracao"]["arquivos"] == ["narracao/seg_00.wav", "narracao/seg_01.wav"]
    assert (tmp_path / "roteiro.md").exists() and all(s["estender_s"] == 0 for s in plan["segmentos"])

def test_narrar_segmento_sem_texto_gera_wav_silencioso(tmp_path, monkeypatch):
    # Correção obrigatória 2: narracao["arquivos"] nunca tem None — segmento sem texto de
    # narração ainda produz um wav (silencioso) na lista, na mesma posição, pra não
    # desalinhar os índices [k+1:a] que o render monta 1:1 por segmento.
    (tmp_path / "plan.json").write_text(json.dumps({"modo": "B", "alvo_s": 8, "total_s": 8.0, "narracao": None,
        "segmentos": [{"in": 0, "out": 4.0, "unidades": [0], "texto": "a", "estender_s": 0},
                      {"in": 6, "out": 10.0, "unidades": [2], "texto": "c", "estender_s": 0}]}))
    (tmp_path / "unidades.json").write_text(json.dumps({"unidades": [{"id": i, "texto": t, "ini": i * 3, "fim": i * 3 + 2} for i, t in enumerate("abc")]}))
    class FakeLLM:
        nome = "fake"
        # LLM só devolve texto pro segmento 0 — segmento 1 fica sem narração (texto vazio)
        def chat_json(self, p, imagens=None): return {"narracao": [{"k": 0, "texto": "um"}]}, {}
    chamadas = []
    def fake_tts(texto, out, cfg, provedor=None):
        chamadas.append(texto)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300", "-t", "3", str(out)], check=True); return out
    monkeypatch.setattr(Nn, "criar_llm", lambda cfg, slot: FakeLLM())
    monkeypatch.setattr(Nn, "tts", fake_tts)
    narrar(tmp_path, {"pontuacao": "glm", "tts": "inemavox"})
    plan = json.loads((tmp_path / "plan.json").read_text())
    arquivos = plan["narracao"]["arquivos"]
    assert len(arquivos) == 2 and all(a is not None for a in arquivos)
    assert (tmp_path / arquivos[1]).exists()          # wav de silêncio existe de verdade
    assert chamadas == ["um"]                          # tts só foi chamado pro segmento com texto
    dur1 = Nn.duracao_wav(tmp_path / arquivos[1])
    assert abs(dur1 - 4.0) < 0.1                        # silêncio do tamanho do segmento (10-6=4s)
