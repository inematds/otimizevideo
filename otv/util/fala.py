"""Forma-fala: reescreve o texto ANTES de ir pro TTS.

Regra aprendida das skills `video-explicativo`/`videoprodutor` (`revisao-texto.md`): cada
frase tem duas formas. A de **tela** mantém o termo em inglês na grafia original; a de
**fala** troca pela grafia fonética em PT-BR, e expande siglas e URLs. O fonemizador do TTS
lê a partir da grafia escrita — "deploy" vira "dê-plô-i", "AlphaFold" vira "al-fa-fól-di".

Isto é código determinístico de propósito, não instrução de prompt: um léxico fixo é
testável e não varia entre chamadas do modelo. O prompt cobre o que sobra (nomes próprios
que não estão aqui); o léxico cobre o que se repete.
"""
import re

# Termos de tecnologia/IA que aparecem o tempo todo no conteúdo do usuário.
# Base: a tabela de `video-explicativo/references/revisao-texto.md`, mais os termos de
# biotech/IA que apareceram no vídeo de exemplo (AlphaFold, DeepMind…).
LEXICO = {
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
    (r"\bIA\b", "I A"),
    (r"\bAI\b", "I A"),
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
