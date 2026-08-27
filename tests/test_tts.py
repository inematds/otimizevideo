import pytest
import otv.provedores.tts as T


class _FakeResp:
    def __init__(self, dados, status_code=200):
        self._dados, self.status_code, self.content = dados, status_code, b""
    def json(self):
        return self._dados
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


# --- Achado 2 da rodada de correção 1: status desconhecido desiste rápido -------------

def test_tts_inemavox_status_desconhecido_desiste_rapido_sem_esperar_timeout(monkeypatch):
    chamadas_get = []

    def fake_post(url, json=None, timeout=None):
        return _FakeResp({"id": "job1"})

    def fake_get(url, timeout=None):
        chamadas_get.append(url)
        return _FakeResp({"status": "cancelled"})  # fora de STATUS_OK/STATUS_ERRO/STATUS_EM_ANDAMENTO

    monkeypatch.setattr(T.requests, "post", fake_post)
    monkeypatch.setattr(T.requests, "get", fake_get)
    monkeypatch.setattr(T.time, "sleep", lambda s: None)  # não esperar de verdade no teste

    with pytest.raises(RuntimeError, match="desconhecido"):
        T.tts_inemavox("oi", "/tmp/nao_deve_existir.wav")

    # desistiu depois de N_DESCONHECIDO polls consecutivos com o MESMO status desconhecido
    # -- não rodou os 600 polls (~20min) do timeout normal.
    assert len(chamadas_get) == T.N_DESCONHECIDO


def test_tts_inemavox_status_em_andamento_nao_conta_como_desconhecido(monkeypatch, tmp_path):
    # "running"/"queued" são esperados durante o processamento normal -- não podem disparar
    # a desistência rápida, só um status realmente fora do vocabulário conhecido.
    sequencia = ["queued"] * 5 + ["running"] * 5 + ["completed"]
    chamadas_get = []

    def fake_post(url, json=None, timeout=None):
        return _FakeResp({"id": "job2"})

    def fake_get(url, timeout=None):
        st = sequencia[len(chamadas_get)]
        chamadas_get.append(url)
        return _FakeResp({"status": st})

    def fake_get_audio(url, timeout=None):
        return _FakeResp({}, status_code=200)

    monkeypatch.setattr(T.requests, "post", fake_post)
    monkeypatch.setattr(T.requests, "get", lambda url, timeout=None: (
        fake_get_audio(url, timeout) if url.endswith("/audio") else fake_get(url, timeout)
    ))
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    monkeypatch.setattr(T, "run", lambda cmd: "")  # evita chamar ffmpeg de verdade

    out_path = tmp_path / "saida.wav"
    out = T.tts_inemavox("oi", out_path)
    assert out == out_path
    assert len(chamadas_get) == 11  # 5 queued + 5 running + 1 completed, sem desistência
