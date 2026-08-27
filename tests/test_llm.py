import json, pytest
from otv.provedores import llm as L

def test_extrair_json_tolerante():
    assert L.extrair_json('```json\n{"a":1}\n```') == {"a": 1}
    assert L.extrair_json('bla {"a": [1,2]} fim') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        L.extrair_json("nada aqui")

def test_openrouter_manda_reasoning_low_e_retorna_json(monkeypatch):
    chamadas = []
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": '{"ok":1}'}}], "usage": {"cost": 0.001}}
        def raise_for_status(self): pass
    def fake_post(url, headers=None, json=None, timeout=None):
        chamadas.append(json); return R()
    monkeypatch.setattr(L.requests, "post", fake_post)
    monkeypatch.setattr(L, "key", lambda n: "k")
    m = L.OpenRouter("z-ai/glm-5.3-flash", effort="low", max_tokens=20000)
    resp, uso = m.chat_json("oi")
    assert resp == {"ok": 1} and uso["cost"] == 0.001
    assert chamadas[0]["reasoning"] == {"effort": "low"} and chamadas[0]["max_tokens"] == 20000
    assert chamadas[0]["response_format"] == {"type": "json_object"}

def test_retry_em_json_invalido(monkeypatch):
    respostas = iter(['isso não é json', '{"ok":2}'])
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": next(respostas)}}], "usage": {}}
        def raise_for_status(self): pass
    monkeypatch.setattr(L.requests, "post", lambda *a, **k: R())
    monkeypatch.setattr(L, "key", lambda n: "k")
    resp, _ = L.OpenRouter("x").chat_json("oi")
    assert resp == {"ok": 2}

def test_criar_llm_slots():
    cfg = {"modelos": {"glm": "z-ai/glm-5.3-flash", "gemini": "g", "ollama": "q", "claude_cli": "sonnet"},
           "openrouter": {"reasoning_effort": "low", "max_tokens": 1}}
    assert L.criar_llm(cfg, "glm").nome == "openrouter/z-ai/glm-5.3-flash"
    assert L.criar_llm(cfg, "ollama").nome == "ollama/q"
    assert L.criar_llm(cfg, "claude_cli").nome == "claude_cli/sonnet"

def test_criar_llm_slot_desconhecido_levanta_valueerror_com_slots_validos():
    cfg = {"modelos": {"glm": "g", "gemini": "x", "ollama": "q", "claude_cli": "sonnet"},
           "openrouter": {}}
    with pytest.raises(ValueError) as e:
        L.criar_llm(cfg, "visual")
    msg = str(e.value)
    assert "visual" in msg
    for slot in ("glm", "gemini", "ollama", "claude_cli"):
        assert slot in msg

def test_claude_cli_chama_binario_e_parseia(monkeypatch):
    class R: returncode = 0; stdout = '{"ok":3}'; stderr = ""
    chamadas = []
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: (chamadas.append((cmd, kw["input"])), R())[1])
    resp, uso = L.ClaudeCLI("sonnet").chat_json("oi")
    assert resp == {"ok": 3} and chamadas[0][0][:4] == ["claude", "-p", "--model", "sonnet"] and uso["cost"] == 0.0

def test_claude_cli_erro_de_processo_levanta_runtimeerror(monkeypatch):
    class R: returncode = 1; stdout = ""; stderr = "algo deu errado"
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: R())
    with pytest.raises(RuntimeError):
        L.ClaudeCLI("sonnet").chat_json("oi")

def test_claude_cli_com_imagens_cita_caminhos_no_prompt(monkeypatch, tmp_path):
    img = tmp_path / "cena0.jpg"
    img.write_bytes(b"fake")
    chamadas = []
    class R: returncode = 0; stdout = '{"ok":1}'; stderr = ""
    def fake_run(cmd, **kw):
        chamadas.append((cmd, kw["input"]))
        return R()
    monkeypatch.setattr(L.subprocess, "run", fake_run)
    L.ClaudeCLI("sonnet").chat_json("descreva", imagens=[img])
    cmd, prompt_enviado = chamadas[0]
    assert str(img.resolve()) in prompt_enviado
    assert "--allowedTools" in cmd and "Read" in cmd
