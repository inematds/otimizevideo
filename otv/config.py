from pathlib import Path
import copy, yaml

DEFAULTS = {
    "transcricao": "groq", "visual": "local", "pontuacao": "glm", "tts": "inemavox",
    "modelos": {"glm": "z-ai/glm-5.3-flash", "gemini": "google/gemini-2.5-flash-lite",
                "ollama": "qwen3.8:27b", "whisper_local": "turbo", "claude_cli": "sonnet"},
    "openrouter": {"reasoning_effort": "low", "max_tokens": 20000},
    "selecao": {"alvo_s": 120, "tolerancia": 0.25, "min_segmento_s": 3, "min_segmento_ideal_s": 8,
                "pausa_fronteira_ms": 400, "folga_ms": 120, "cota_topico_pct": 40, "nota_minima": 5,
                "max_unidade_s": 12},
    "saida": "~/projetos/output/otimizevideo", "trabalho": "trabalho",
}

def _merge(base, novo):
    out = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def carregar_config(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.yaml"
    dados = yaml.safe_load(path.read_text()) if path.exists() else {}
    return _merge(DEFAULTS, dados)
