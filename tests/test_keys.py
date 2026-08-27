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
