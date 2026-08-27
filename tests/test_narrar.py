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


# --- Achado 1 da rodada de correção 1: truncagem no orçamento ANTES do TTS ------------

def test_orcamento_palavras_bate_com_o_calculo_da_revisao():
    # segmento médio real (8.65s, do aviso da Task 8): 2.5 * (8.65 + 3.0) = 29.125 -> 29
    assert Nn.orcamento_palavras(8.65) == 29
    assert Nn.orcamento_palavras(2.0) == 12   # 2.5 * (2.0 + 3.0) = 12.5 -> 12 (round-half-even)


def test_truncar_por_orcamento_corta_na_ultima_frase_completa():
    texto = ("Isso é a frase um. Isso é a frase dois que também é curta. "
             "Aqui vem uma frase três bem mais longa cheia de palavras extras que estouram o orçamento.")
    # 1ª frase = 5 palavras, 2ª frase = 9 palavras (5+9=14) -- orçamento de 14 inclui as
    # duas primeiras frases inteiras e descarta a 3ª (que sozinha já estoura o orçamento).
    resultado = Nn.truncar_por_orcamento(texto, 14)
    palavras_originais = texto.split()
    palavras_resultado = resultado.split()
    assert len(palavras_resultado) <= 14
    assert palavras_originais[:len(palavras_resultado)] == palavras_resultado  # prefixo exato, sem palavra cortada
    assert resultado.rstrip()[-1] in ".!?"                                    # terminou em frase completa
    assert resultado == "Isso é a frase um. Isso é a frase dois que também é curta."


def test_truncar_por_orcamento_cai_pra_fronteira_de_palavra_quando_nem_a_1a_frase_cabe():
    texto = "Palavra1 palavra2 palavra3 palavra4 palavra5 palavra6 palavra7 palavra8 palavra9 palavra10 palavra11."
    resultado = Nn.truncar_por_orcamento(texto, 5)
    assert resultado == "Palavra1 palavra2 palavra3 palavra4 palavra5"
    assert len(resultado.split()) == 5


def test_truncar_por_orcamento_nao_mexe_quando_ja_cabe():
    texto = "Frase curta que cabe fácil."
    assert Nn.truncar_por_orcamento(texto, 20) == texto


def test_roteiro_por_segmento_trunca_texto_que_estoura_orcamento():
    # segmento de 2.0s -> orçamento de 12 palavras (Nn.orcamento_palavras(2.0)). O LLM
    # devolve uma única frase de 50 palavras (estoura o orçamento por larga margem, e como
    # é uma frase só, nem ela cabe inteira -> cai pra fronteira de palavra).
    segmentos = [{"in": 0, "out": 2.0, "unidades": [0], "texto": "a"}]
    unidades = [{"id": 0, "texto": "x", "ini": 0, "fim": 1}]
    texto_longo = " ".join(f"palavra{i}" for i in range(1, 51)) + "."  # 50 palavras
    class FakeLLM:
        nome = "fake"
        def chat_json(self, p, imagens=None):
            return {"narracao": [{"k": 0, "texto": texto_longo}]}, {}
    textos, _ = Nn.roteiro_por_segmento(segmentos, unidades, FakeLLM())
    orcamento = Nn.orcamento_palavras(2.0)
    assert orcamento == 12
    assert len(textos[0].split()) == orcamento          # truncado exatamente no orçamento
    assert textos[0] == " ".join(f"palavra{i}" for i in range(1, orcamento + 1))  # prefixo exato


def test_narrar_manda_forma_fala_pro_tts_e_grava_a_de_tela(tmp_path, monkeypatch):
    # roteiro.md guarda a grafia original (forma de TELA); o TTS recebe a fonética.
    import json
    import otv.fases.narrar as N
    (tmp_path / "plan.json").write_text(json.dumps({
        "modo": "B", "alvo_s": 10, "total_s": 6.0,
        "segmentos": [{"in": 0.0, "out": 6.0, "unidades": [0], "texto": "x", "visual": "grafico"}]}))
    (tmp_path / "unidades.json").write_text(json.dumps(
        {"unidades": [{"id": 0, "ini": 0.0, "fim": 6.0, "dur": 6.0, "texto": "x", "visual": "grafico"}]}))
    recebidos = []

    class LLMFake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            return {"narracao": [{"k": 0, "texto": "A DeepMind usou o AlphaFold."}]}, {"cost": 0.0}

    monkeypatch.setattr(N, "criar_llm", lambda cfg, slot: LLMFake())
    monkeypatch.setattr(N, "tts", lambda txt, wav, cfg, prov: (recebidos.append(txt),
                        N.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                               "anullsrc=r=48000:cl=mono", "-t", "2", str(wav)]))[0])
    N.narrar(tmp_path, {"pontuacao": "fake", "tts": "fake", "selecao": {"alvo_s": 120}})

    assert "DipMáind" in recebidos[0] and "AlfaFôld" in recebidos[0]        # foi pro TTS
    roteiro = (tmp_path / "roteiro.md").read_text()
    assert "DeepMind" in roteiro and "AlphaFold" in roteiro                  # tela intacta
    assert "DipMáind" not in roteiro


def test_modo_n_usa_o_prompt_proprio_e_teto_de_freeze_maior(tmp_path, monkeypatch):
    # o prompt do modo N proíbe inventar fato e o teto de freeze sobe pra 6s (o usuário
    # pediu que o clipe pare e espere a fala terminar, em vez de truncar a frase).
    import json
    import otv.fases.narrar as N
    fala = " ".join(["palavra"] * 40)          # ~40 palavras num segmento de 6s
    (tmp_path / "plan.json").write_text(json.dumps({
        "modo": "N", "alvo_s": 10, "total_s": 6.0,
        "segmentos": [{"in": 0.0, "out": 6.0, "unidades": [0], "texto": "x", "visual": "outro"}]}))
    (tmp_path / "unidades.json").write_text(json.dumps(
        {"unidades": [{"id": 0, "ini": 0.0, "fim": 6.0, "dur": 6.0, "texto": "x", "visual": "outro"}]}))
    prompts = []

    class LLMFake:
        nome = "fake"
        def chat_json(self, prompt, imagens=None):
            prompts.append(prompt)
            return {"narracao": [{"k": 0, "texto": fala}]}, {"cost": 0.0}

    monkeypatch.setattr(N, "criar_llm", lambda cfg, slot: LLMFake())
    monkeypatch.setattr(N, "tts", lambda txt, wav, cfg, prov:
                        N.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                               "anullsrc=r=48000:cl=mono", "-t", "9", str(wav)]))
    N.narrar(tmp_path, {"pontuacao": "fake", "tts": "fake", "selecao": {"alvo_s": 120}})

    assert "não invente nada" in prompts[0] or "não acrescenta fato" in prompts[0].lower()
    # orçamento com teto de 6s: 2.5 * (6+6) = 30 palavras (com o teto de 3s seriam 22)
    assert len((tmp_path / "roteiro.md").read_text().split("palavra")) - 1 == 30
    # wav de 9s num segmento de 6s -> freeze de 3s... o teto de 6 deixa passar
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["segmentos"][0]["estender_s"] == 3.0
