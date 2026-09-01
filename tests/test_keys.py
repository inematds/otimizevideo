import pytest
from otv.util import keys

def test_key_le_dos_arquivos(tmp_path, monkeypatch):
    f = tmp_path / ".env"; f.write_text('FOO_KEY="abc"\nBAR=1\n')
    monkeypatch.setattr(keys, "ARQUIVOS", [f])
    assert keys.key("FOO_KEY") == "abc"

def test_key_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "ARQUIVOS", [tmp_path / "x.env"])
    with pytest.raises(KeyError):
        keys.key("NADA")

def test_ambiente_vence_arquivo(tmp_path, monkeypatch):
    f = tmp_path / ".env"; f.write_text("FOO_KEY=do-arquivo\n")
    monkeypatch.setattr(keys, "ARQUIVOS", [f])
    monkeypatch.setenv("FOO_KEY", "do-ambiente")
    assert keys.key("FOO_KEY") == "do-ambiente"

def test_ambiente_vazio_cai_pro_arquivo(tmp_path, monkeypatch):
    f = tmp_path / ".env"; f.write_text("FOO_KEY=do-arquivo\n")
    monkeypatch.setattr(keys, "ARQUIVOS", [f])
    monkeypatch.setenv("FOO_KEY", "   ")
    assert keys.key("FOO_KEY") == "do-arquivo"

def test_otv_env_file(tmp_path, monkeypatch):
    f = tmp_path / "custom.env"; f.write_text("FOO_KEY=custom\n")
    monkeypatch.setattr(keys, "ARQUIVOS", [])
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.setenv("OTV_ENV_FILE", str(f))
    assert keys.key("FOO_KEY") == "custom"

def test_ignora_comentario_e_aceita_export(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# FOO_KEY=comentada\nexport FOO_KEY='exportada'\n")
    monkeypatch.setattr(keys, "ARQUIVOS", [f])
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.delenv("OTV_ENV_FILE", raising=False)
    assert keys.key("FOO_KEY") == "exportada"

def test_erro_lista_as_fontes(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "ARQUIVOS", [tmp_path / "x.env"])
    monkeypatch.delenv("NADA", raising=False)
    monkeypatch.delenv("OTV_ENV_FILE", raising=False)
    with pytest.raises(KeyError) as e:
        keys.key("NADA")
    assert "x.env" in str(e.value) and "variável de ambiente" in str(e.value)
