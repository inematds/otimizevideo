import base64, json, re, subprocess, time, requests
from pathlib import Path
from otv.util.keys import key

def extrair_json(texto):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError("resposta sem JSON válido: " + texto[:200])

def _img_b64(p):
    return "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()

class LLM:
    nome = "?"
    def _chamar(self, prompt, imagens):  # -> (texto, usage)
        raise NotImplementedError
    def chat_json(self, prompt, imagens=None):
        erro = None
        for tentativa in range(2):
            texto, uso = self._chamar(prompt if tentativa == 0 else prompt + "\n\nATENÇÃO: sua resposta anterior não era JSON válido. Responda SOMENTE o JSON.", imagens)
            try:
                return extrair_json(texto), uso
            except ValueError as e:
                erro = e
        raise erro

class OpenRouter(LLM):
    def __init__(self, modelo, effort="low", max_tokens=20000):
        self.modelo, self.effort, self.max_tokens = modelo, effort, max_tokens
        self.nome = f"openrouter/{modelo}"
    def _chamar(self, prompt, imagens):
        conteudo = [{"type": "text", "text": prompt}]
        for i, p in enumerate(imagens or []):
            conteudo.append({"type": "text", "text": f"imagem {i}:"})
            conteudo.append({"type": "image_url", "image_url": {"url": _img_b64(p)}})
        corpo = {"model": self.modelo, "temperature": 0.2, "max_tokens": self.max_tokens,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "user", "content": conteudo if imagens else prompt}]}
        if self.effort:
            corpo["reasoning"] = {"effort": self.effort}
        for tentativa in range(3):
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"}, json=corpo, timeout=600)
            if r.status_code < 500 and r.status_code != 429:
                break
            time.sleep(5 * (tentativa + 1))
        r.raise_for_status(); j = r.json()
        return j["choices"][0]["message"]["content"], j.get("usage", {})

class Ollama(LLM):
    def __init__(self, modelo, host="http://localhost:11434"):
        self.modelo, self.host, self.nome = modelo, host, f"ollama/{modelo}"
    def _chamar(self, prompt, imagens):
        msg = {"role": "user", "content": prompt}
        if imagens:
            msg["images"] = [base64.b64encode(Path(p).read_bytes()).decode() for p in imagens]
        r = requests.post(f"{self.host}/api/chat", json={"model": self.modelo, "stream": False, "format": "json",
            "think": False, "options": {"num_ctx": 32768, "temperature": 0.2}, "messages": [msg]}, timeout=3600)
        r.raise_for_status(); j = r.json()
        return j["message"]["content"], {"prompt_tokens": j.get("prompt_eval_count"), "completion_tokens": j.get("eval_count")}

class ClaudeCLI(LLM):
    """Claude Code em modo headless: sai da assinatura do usuário, sem API key.
    Verificado nesta máquina em 2026-08-27: `echo <prompt> | claude -p --model sonnet
    --output-format text` devolve o JSON limpo.
    """
    def __init__(self, modelo="sonnet"):
        self.modelo, self.nome = modelo, f"claude_cli/{modelo}"
    def _chamar(self, prompt, imagens):
        if imagens:  # Claude Code lê imagens por caminho: cita os arquivos no prompt
            prompt = ("Leia estas imagens (uma por cena, na ordem):\n"
                      + "\n".join(f"imagem {i}: {Path(p).resolve()}" for i, p in enumerate(imagens))
                      + "\n\n" + prompt)
        cmd = ["claude", "-p", "--model", self.modelo, "--output-format", "text",
               "--allowedTools", "Read" if imagens else ""]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"claude -p falhou: {r.stderr[-400:]}")
        return r.stdout, {"provedor": "assinatura", "cost": 0.0}

def criar_llm(cfg, slot):
    modelos = cfg["modelos"]
    if slot not in modelos:
        raise ValueError(f"slot de modelo desconhecido: {slot!r} (válidos: {sorted(modelos)})")
    modelo = modelos[slot]
    if slot == "ollama":
        return Ollama(modelo)
    if slot == "claude_cli":
        return ClaudeCLI(modelo)
    o = cfg.get("openrouter", {})
    effort = o.get("reasoning_effort", "low") if "glm" in modelo else None
    return OpenRouter(modelo, effort=effort, max_tokens=o.get("max_tokens", 20000))
