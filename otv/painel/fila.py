"""Fila serial de jobs do painel — um por vez.

Cada job é um subprocesso `python3 otv.py ...` com stdout+stderr indo pra um arquivo de log.
Subprocesso (e não import direto) por três motivos: um crash de ffmpeg/mediapipe não derruba
o servidor, o log já sai pronto dos print() das fases, e o job continua vivo se o browser
fechar. A fila é serial de propósito — a detecção de cena é CPU-bound e dois jobs em paralelo
só se atrapalham.
"""
import json, os, subprocess, sys, threading, time, uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MODOS = ("A", "B", "C", "N")
FASES_ISOLADAS = ("selecionar", "render", "narrar", "abertura", "substituir")


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Job:
    def __init__(self, cmd, rotulo, id_alvo, log_dir):
        self.id = uuid.uuid4().hex[:8]
        self.cmd, self.rotulo, self.id_alvo = cmd, rotulo, id_alvo
        self.estado = "na_fila"        # na_fila | rodando | ok | erro | cancelado
        self.criado_em, self.iniciado_em, self.terminado_em = _agora(), None, None
        self.codigo = None
        self.log = Path(log_dir) / f"painel-{self.id}.log"
        self._proc = None

    def dict(self):
        return {"job": self.id, "estado": self.estado, "rotulo": self.rotulo, "id": self.id_alvo,
                "cmd": self.cmd, "criado_em": self.criado_em, "iniciado_em": self.iniciado_em,
                "terminado_em": self.terminado_em, "codigo": self.codigo, "log": str(self.log)}

    def texto_log(self, desde=0):
        try:
            with open(self.log, "r", errors="replace") as f:
                f.seek(desde)
                return f.read(), f.tell()
        except OSError:
            return "", desde


class Fila:
    def __init__(self, trabalho, config=None):
        self.trabalho = Path(trabalho)
        self.config = config
        self.jobs = []
        self._lock = threading.Lock()
        self._pendentes = []
        self._worker = None
        self.estado_dir = self.trabalho / ".painel"

    # ---- montagem de comando (nunca via shell) -------------------------------
    def _base(self):
        cmd = [sys.executable, str(RAIZ / "otv.py")]
        if self.config:
            cmd += ["--config", str(self.config)]
        return cmd

    def cmd_run(self, fonte, modo="A", alvo=None, visual=None, abertura=False, forcar=False):
        if modo not in MODOS:
            raise ValueError(f"modo inválido: {modo!r}")
        cmd = self._base() + ["run", str(fonte), "--modo", modo]
        if alvo:
            cmd += ["--alvo", str(float(alvo))]
        if visual:
            cmd += ["--visual", str(visual)]
        if abertura:
            cmd += ["--abertura"]
        if forcar:
            cmd += ["--forcar"]
        return cmd

    def cmd_fase(self, fase, id_, modo=None, alvo=None):
        if fase not in FASES_ISOLADAS:
            raise ValueError(f"fase não permitida pelo painel: {fase!r}")
        cmd = self._base() + [fase, str(id_)]
        if fase == "selecionar":
            if modo:
                if modo not in MODOS:
                    raise ValueError(f"modo inválido: {modo!r}")
                cmd += ["--modo", modo]
            if alvo:
                cmd += ["--alvo", str(float(alvo))]
        return cmd

    # ---- fila ----------------------------------------------------------------
    def enfileirar(self, cmd, rotulo, id_alvo=None):
        self.estado_dir.mkdir(parents=True, exist_ok=True)
        j = Job(cmd, rotulo, id_alvo, self.estado_dir)
        with self._lock:
            self.jobs.append(j)
            self._pendentes.append(j)
            self._garantir_worker()
        self.salvar()
        return j

    def _garantir_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._rodar_tudo, daemon=True)
            self._worker.start()

    def _rodar_tudo(self):
        while True:
            with self._lock:
                if not self._pendentes:
                    self._worker = None
                    return
                j = self._pendentes.pop(0)
            if j.estado == "cancelado":
                continue
            self._rodar(j)

    def _rodar(self, j):
        j.estado, j.iniciado_em = "rodando", _agora()
        self.salvar()
        try:
            with open(j.log, "w", buffering=1, errors="replace") as f:
                f.write(f"$ {' '.join(j.cmd)}\n\n")
                f.flush()
                j._proc = subprocess.Popen(j.cmd, cwd=str(RAIZ), stdout=f, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL,
                                           env={**os.environ, "PYTHONUNBUFFERED": "1"})
                j.codigo = j._proc.wait()
            j.estado = "ok" if j.codigo == 0 else "erro"
        except Exception as e:                      # noqa: BLE001 — o painel não pode morrer por causa de um job
            j.estado, j.codigo = "erro", -1
            try:
                with open(j.log, "a") as f:
                    f.write(f"\n[painel] falha ao executar: {e}\n")
            except OSError:
                pass
        finally:
            j.terminado_em = _agora()
            j._proc = None
            self.salvar()

    def cancelar(self, job_id):
        with self._lock:
            j = self.buscar(job_id)
            if not j:
                return None
            if j.estado == "na_fila":
                j.estado = "cancelado"
                if j in self._pendentes:
                    self._pendentes.remove(j)
            elif j.estado == "rodando" and j._proc:
                j._proc.terminate()
                j.estado = "cancelado"
        self.salvar()
        return j

    def buscar(self, job_id):
        return next((x for x in self.jobs if x.id == job_id), None)

    def atual(self):
        return next((x for x in self.jobs if x.estado == "rodando"), None)

    def lista(self):
        return [j.dict() for j in reversed(self.jobs)]

    def salvar(self):
        """Histórico em disco pra sobreviver a restart. Best-effort: nunca quebra um job."""
        try:
            self.estado_dir.mkdir(parents=True, exist_ok=True)
            (self.estado_dir / "jobs.json").write_text(
                json.dumps(self.lista(), ensure_ascii=False, indent=1))
        except OSError:
            pass
