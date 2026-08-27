from pathlib import Path
from otv.config import carregar_config

def test_defaults_sem_arquivo(tmp_path):
    cfg = carregar_config(tmp_path / "nao_existe.yaml")
    assert cfg["selecao"]["alvo_s"] == 120
    assert cfg["pontuacao"] == "glm"

def test_yaml_sobrescreve(tmp_path):
    (tmp_path / "c.yaml").write_text("pontuacao: ollama\nselecao:\n  alvo_s: 90\n")
    cfg = carregar_config(tmp_path / "c.yaml")
    assert cfg["pontuacao"] == "ollama"
    assert cfg["selecao"]["alvo_s"] == 90
    assert cfg["selecao"]["nota_minima"] == 5   # default preservado no merge
