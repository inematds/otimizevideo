"""Forma-fala: reescreve o texto ANTES de ir pro TTS.

Regra aprendida das skills `video-explicativo`/`videoprodutor` (`revisao-texto.md`): cada
frase tem duas formas. A de **tela** mantém o termo em inglês na grafia original; a de
**fala** troca pela grafia fonética em PT-BR, e expande siglas e URLs. O fonemizador do TTS
lê a partir da grafia escrita.

REGRA DO USUÁRIO (2026-08-27): **termo em inglês e sigla podem ser falados em inglês** —
nada de reescrita fonética em PT-BR. O que sobrou aqui é só o que o TTS lê *errado de
verdade* se deixado como está: "IA" (que vira "inteligência artificial", nunca soletrada),
sigla que seria lida como palavra, símbolo (%, $) e URL.

Isto é código determinístico de propósito, não instrução de prompt: uma regra fixa é
testável e não varia entre chamadas do modelo.
"""
import re

# REGRA DO USUÁRIO (2026-08-27): termo em inglês e sigla PODEM ser falados em inglês —
# nada de reescrita fonética em PT-BR. O léxico de respelling que existia aqui
# ("deploy"->"deplói", "AlphaFold"->"AlfaFôld", "design"->"dizáin", vindo do
# revisao-texto.md das skills de vídeo) foi DESLIGADO por isso: fica vazio de propósito,
# não foi esquecido. A estrutura continua no lugar caso um termo específico precise de
# ajuste pontual no futuro.
LEXICO = {}

_LEXICO_FONETICO_DESATIVADO = {
    "deploy": "deplói", "design": "dizáin", "designer": "dizáiner",
    "frontend": "frôntend", "backend": "béquend", "framework": "frêimuork",
    "software": "sóftuer", "hardware": "rárduer", "cloud": "claud",
    "update": "âpdeit", "upgrade": "âpgreid", "release": "rilís",
    "feature": "fítcher", "review": "rivíu", "bug": "bãg", "debug": "dibãg",
    "token": "tôken", "tokens": "tôkens", "dataset": "dêitaset",
    "dashboard": "déshbord", "workflow": "uórkflôu", "startup": "stártâp",
    "default": "difólt", "insight": "ínsait", "mindset": "máindset",
    "streaming": "stríming", "template": "témpleit", "skill": "skiu", "skills": "skiuz",
    "machine learning": "mâchin lârning", "deep learning": "dip lârning",
    "prompt": "prompt", "code": "coud",
    # nomes próprios recorrentes de IA / biotech
    "alphafold": "AlfaFôld", "deepmind": "DipMáind", "openai": "Ôupen A I",
    "chatgpt": "Chat G P T", "nature medicine": "Nêitcher Médicin",
    "crispr": "crísper", "protein folding": "protein fôlding",
    "google": "Gugou", "anthropic": "Antrópic", "claude": "Clód",
}

# Siglas e símbolos que o TTS lê errado se deixados como estão.
EXPANSOES = [
    # REGRA DO USUÁRIO (2026-08-27): "IA" na tela vira "inteligência artificial" na fala,
    # sempre — nunca soletrada ("I A"), que era o que a rachel dizia antes.
    (r"\bIAs\b", "inteligências artificiais"),
    (r"\bIA\b", "inteligência artificial"),
    (r"\bAI\b", "inteligência artificial"),
    (r"\bEUA\b", "E U A"),
    (r"\bCEO\b", "C E O"),
    (r"\bAPI\b", "A P I"),
    (r"\bLLM\b", "L L M"),
    (r"\bGPU\b", "G P U"),
    (r"\bDNA\b", "D N A"),
    (r"\bRNA\b", "R N A"),
    (r"\bPhD\b", "P H D"),
    (r"\bFDA\b", "F D A"),
    (r"%", " por cento"),
    (r"\$\s?([\d.,]+)", r"\1 dólares"),
    (r"([\d.,]+)\s?US\$", r"\1 dólares"),
]

# URLs: "inema.club" -> "inema ponto club" (o ponto vira pausa/abreviação no TTS).
_URL = re.compile(r"\b([a-z0-9-]+)\.(club|com|br|pro|org|net|io|ai)\b", re.I)


def _trocar(texto, de, para):
    """Troca respeitando fronteira de palavra e preservando CAIXA ALTA da origem."""
    def sub(m):
        achado = m.group(0)
        return para.upper() if achado.isupper() and len(achado) > 1 else para
    return re.sub(rf"\b{re.escape(de)}\b", sub, texto, flags=re.I)


def forma_fala(texto, lexico=None):
    """Devolve a versão do texto pronta pro TTS (a de tela fica intacta)."""
    if not texto:
        return texto
    t = _URL.sub(lambda m: f"{m.group(1)} ponto {m.group(2).lower()}", texto)
    for padrao, troca in EXPANSOES:
        t = re.sub(padrao, troca, t)
    # termos compostos primeiro ("machine learning" antes de "learning" isolado)
    for de, para in sorted((lexico or LEXICO).items(), key=lambda kv: -len(kv[0])):
        t = _trocar(t, de, para)
    return re.sub(r"\s{2,}", " ", t).strip()
