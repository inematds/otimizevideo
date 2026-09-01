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
    # moeda com prefixo ANTES do "$" solto, senão "US$ 1.500" perde o "US" pelo caminho e
    # o TTS lê "USmil e quinhentos dólares" (achado de 2026-09-01)
    (r"\bUS\s?\$\s?([\d.,]+)", r"\1 dólares"),
    (r"\bR\s?\$\s?([\d.,]+)", r"\1 reais"),
    (r"\$\s?([\d.,]+)", r"\1 dólares"),
    (r"([\d.,]+)\s?US\$", r"\1 dólares"),
]


# --- números por extenso ----------------------------------------------------
# REGRA DO USUÁRIO (2026-09-01): número e valor não podem sair com pronúncia misturada. O
# TTS lia dígito cru com a fonética que bem entendia — no vídeo de 2026-09-01 conviviam
# "92%", "2025", "223 milhões" e "83" na mesma narração, cada um dito de um jeito. Escrever
# por extenso tira a decisão do fonemizador: "noventa e dois por cento" só tem uma leitura.
UNI = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
       "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
       "setecentos", "oitocentos", "novecentos"]


def _ate_999(n):
    if n < 20:
        return UNI[n]
    if n < 100:
        d, r = divmod(n, 10)
        return DEZ[d] + (f" e {UNI[r]}" if r else "")
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    return CEM[c] + (f" e {_ate_999(r)}" if r else "")


def extenso(n):
    """Inteiro em português. Vai até trilhões — muito além do que uma narração usa."""
    n = int(n)
    if n < 0:
        return "menos " + extenso(-n)
    if n < 1000:
        return _ate_999(n)
    for div, sing, plur in ((10 ** 12, "trilhão", "trilhões"), (10 ** 9, "bilhão", "bilhões"),
                            (10 ** 6, "milhão", "milhões"), (1000, "mil", "mil")):
        if n >= div:
            q, r = divmod(n, div)
            cab = ("mil" if div == 1000 and q == 1 else
                   f"{_ate_999(q)} {sing if q == 1 else plur}" if div > 1000 else
                   f"{_ate_999(q)} mil")
            if not r:
                return cab
            # "e" só antes de resto curto: "mil e duzentos", mas "mil duzentos e trinta"
            lig = " e " if (r < 100 or (r < 1000 and r % 100 == 0)) else " "
            return cab + lig + extenso(r)
    return str(n)


def _numero(m):
    """Um número do texto -> extenso. Trata milhar com ponto e decimal com vírgula."""
    bruto = m.group(0)
    inteiro, _, decimal = bruto.partition(",")
    inteiro = inteiro.replace(".", "")
    if not inteiro.isdigit():
        return bruto
    if len(inteiro) > 15:            # não é número de fala: id, código, telefone
        return bruto
    saida = extenso(int(inteiro))
    if decimal and decimal.isdigit():
        # "0,83" -> "zero vírgula oitenta e três" (como se lê em PT-BR falado)
        saida += " vírgula " + (extenso(int(decimal)) if decimal[0] != "0" or len(decimal) == 1
                                else " ".join(UNI[int(d)] for d in decimal))
    return saida


# Número com separador de milhar (1.500) ou decimal (0,83). Roda DEPOIS das expansões de
# símbolo, pra "US$ 1.500" já ter virado "1.500 dólares" antes de o número ser convertido.
_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")

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
    t = _NUMERO.sub(_numero, t)
    # termos compostos primeiro ("machine learning" antes de "learning" isolado)
    for de, para in sorted((lexico or LEXICO).items(), key=lambda kv: -len(kv[0])):
        t = _trocar(t, de, para)
    return re.sub(r"\s{2,}", " ", t).strip()
