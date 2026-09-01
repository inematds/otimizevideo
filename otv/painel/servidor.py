"""Servidor HTTP do painel — stdlib, sem framework.

Escuta em 0.0.0.0 por padrão (acessível na LAN). Sem autenticação a menos que
OTV_PAINEL_TOKEN esteja definido, e nesse caso todo request precisa de ?t=<token>.

Duas travas que existem porque isto fica exposto na rede:
- todo comando é lista de argumentos pro Popen, NUNCA string de shell (ver fila.py);
- todo id de pasta é resolvido e conferido contra a raiz de trabalho antes de virar caminho
  de arquivo, senão '../../etc/passwd' viraria download.
"""
import json, mimetypes, os, re, secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from otv.painel import leitura
from otv.painel.fila import Fila
from otv.painel.plano import Invalido, salvar as salvar_plano

AQUI = Path(__file__).resolve().parent
ID_OK = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class Painel:
    """Estado do painel: config, raiz de trabalho e a fila. Um por processo."""

    def __init__(self, cfg, config_path=None):
        self.cfg = cfg
        self.trabalho = Path(cfg["trabalho"]).expanduser().resolve()
        self.fila = Fila(self.trabalho, config_path)
        self.token = os.environ.get("OTV_PAINEL_TOKEN") or None

    def dir_de(self, id_):
        """Caminho da rodada, ou None se o id for inválido/fora da raiz (path traversal)."""
        if not id_ or not ID_OK.match(id_) or id_.startswith("."):
            return None
        d = (self.trabalho / id_).resolve()
        if d.parent != self.trabalho or not d.is_dir():
            return None
        return d


class Handler(BaseHTTPRequestHandler):
    painel = None
    server_version = "otv-painel"

    def log_message(self, fmt, *args):
        pass  # o log útil é o dos jobs, não o de acesso

    # ---- helpers -------------------------------------------------------------
    def _json(self, obj, codigo=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, codigo, msg):
        self._json({"erro": msg}, codigo)

    def _autorizado(self, q):
        t = self.painel.token
        if not t:
            return True
        dado = (q.get("t") or [""])[0] or self.headers.get("X-Painel-Token", "")
        return secrets.compare_digest(dado, t)

    def _corpo_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except (ValueError, UnicodeDecodeError):
            return {}

    def _arquivo(self, caminho, parcial=True):
        """Serve um arquivo com suporte a Range — sem isso o player não deixa dar seek."""
        caminho = Path(caminho)
        if not caminho.is_file():
            return self._erro(404, "arquivo não encontrado")
        tam = caminho.stat().st_size
        tipo = mimetypes.guess_type(str(caminho))[0] or "application/octet-stream"
        faixa = self.headers.get("Range", "") if parcial else ""
        ini, fim = 0, tam - 1
        m = re.match(r"bytes=(\d*)-(\d*)", faixa)
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                ini = min(int(m.group(1)), max(tam - 1, 0))
                if m.group(2):
                    fim = min(int(m.group(2)), tam - 1)
            else:                                   # sufixo: últimos N bytes
                ini = max(tam - int(m.group(2)), 0)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
        else:
            self.send_response(200)
        n = fim - ini + 1
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(n))
        self.end_headers()
        with open(caminho, "rb") as f:
            f.seek(ini)
            resta = n
            while resta > 0:
                pedaco = f.read(min(65536, resta))
                if not pedaco:
                    break
                try:
                    self.wfile.write(pedaco)
                except (BrokenPipeError, ConnectionResetError):
                    return          # player fechou/pulou: normal, não é erro
                resta -= len(pedaco)

    # ---- rotas ---------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        if not self._autorizado(q):
            return self._erro(401, "token inválido (use ?t=…)")
        P = self.painel

        if p in ("/", "/index.html"):
            return self._arquivo(AQUI / "ui.html", parcial=False)
        if p == "/api/rodadas":
            return self._json({"rodadas": leitura.listar(P.trabalho),
                               "jobs": P.fila.lista(),
                               "cfg": {"alvo_s": P.cfg["selecao"]["alvo_s"],
                                       "visual": P.cfg["visual"], "pontuacao": P.cfg["pontuacao"]}})
        if p.startswith("/api/rodada/"):
            d = P.dir_de(p[len("/api/rodada/"):])
            return self._json(leitura.detalhe(d)) if d else self._erro(404, "rodada não encontrada")
        if p.startswith("/api/log/"):
            j = P.fila.buscar(p[len("/api/log/"):])
            if not j:
                return self._erro(404, "job não encontrado")
            desde = int((q.get("desde") or ["0"])[0] or 0)
            texto, pos = j.texto_log(desde)
            return self._json({**j.dict(), "texto": texto, "pos": pos})
        if p.startswith("/video/") or p.startswith("/thumb/"):
            partes = p.split("/", 3)
            if len(partes) < 4:
                return self._erro(400, "caminho incompleto")
            d = P.dir_de(partes[2])
            if not d:
                return self._erro(404, "rodada não encontrada")
            alvo = (d / partes[3]).resolve()
            if d not in alvo.parents:
                return self._erro(403, "fora da pasta da rodada")
            return self._arquivo(alvo)
        return self._erro(404, "rota desconhecida")

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._autorizado(q):
            return self._erro(401, "token inválido")
        P, corpo = self.painel, self._corpo_json()
        try:
            if u.path == "/api/rodar":
                fonte = (corpo.get("fonte") or "").strip()
                if not fonte:
                    return self._erro(400, "informe a URL ou o caminho do vídeo")
                cmd = P.fila.cmd_run(fonte, corpo.get("modo", "A"), corpo.get("alvo"),
                                     corpo.get("visual"), bool(corpo.get("abertura")),
                                     bool(corpo.get("forcar")), bool(corpo.get("substituir")))
                return self._json(P.fila.enfileirar(cmd, f"run {fonte[:60]}").dict())
            if u.path == "/api/refazer":
                d = P.dir_de(corpo.get("id"))
                if not d:
                    return self._erro(404, "rodada não encontrada")
                fase = corpo.get("fase", "selecionar")
                cmd = P.fila.cmd_fase(fase, d.name, corpo.get("modo"), corpo.get("alvo"))
                return self._json(P.fila.enfileirar(cmd, f"{fase} {d.name}", d.name).dict())
            if u.path == "/api/plano":
                d = P.dir_de(corpo.get("id"))
                if not d:
                    return self._erro(404, "rodada não encontrada")
                novo, avisos = salvar_plano(d, corpo)
                resp = {"ok": True, "avisos": avisos, "total_s": novo["total_s"],
                        "segmentos": len(novo["segmentos"])}
                # "salvar e renderizar" numa tacada: render não chama LLM, custa US$0
                if corpo.get("renderizar"):
                    cmd = P.fila.cmd_fase("render", d.name)
                    resp["job"] = P.fila.enfileirar(cmd, f"render {d.name}", d.name).dict()
                return self._json(resp)
            if u.path == "/api/cancelar":
                j = P.fila.cancelar(corpo.get("job"))
                return self._json(j.dict()) if j else self._erro(404, "job não encontrado")
        except Invalido as e:
            return self._erro(400, str(e))
        except ValueError as e:
            return self._erro(400, str(e))
        return self._erro(404, "rota desconhecida")


def servir(cfg, host="0.0.0.0", porta=8020, config_path=None):
    Handler.painel = Painel(cfg, config_path)
    httpd = ThreadingHTTPServer((host, porta), Handler)
    httpd.daemon_threads = True
    return httpd
