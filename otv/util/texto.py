"""Texto desenhado como imagem (PIL), para sobrepor no vídeo com `overlay`.

POR QUE NÃO `drawtext`: o `drawtext` do ffmpeg 6.1.1 desta máquina trunca o texto pelo
número de BYTES e não de caracteres — cada letra acentuada come uma letra do fim. Medido em
2026-09-01: "ÁÉÍDEF" (3 bytes extras) sai como "ÁÉÍ", e a manchete real
"IA e bilionários estão tentando vencer o envelhecimento" saiu no vídeo como
"...vencer o envelhecimen" (perdeu o "to", 2 bytes extras de "á" e "ã").

Não é problema de escape: acontece igual com `textfile=`, com `expansion=none`, com
`text_shaping=0` e com fontfile explícito, e encher de espaço no fim não adianta (o ffmpeg
apara espaço à direita antes de contar). Em PT-BR quase toda manchete tem acento, então a
falha era a regra, não a exceção — e silenciosa, porque o vídeo sai com código 0.

Aqui o texto é rasterizado pelo PIL, que trabalha em caracteres, e o resultado entra no
filtro como imagem. De quebra dá quebra de linha por largura real e controle de tipografia.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# DejaVu vem com a maioria das distros e cobre acento latino. A lista é uma ordem de
# preferência: a primeira que existir vence.
FONTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
AMBAR = (226, 162, 59, 255)


def fonte(tamanho_px):
    for f in FONTES:
        if Path(f).exists():
            return ImageFont.truetype(f, tamanho_px)
    return ImageFont.load_default(tamanho_px)


def quebrar(texto, fnt, largura_max, max_linhas=3):
    """Quebra por largura REAL do glifo, não por contagem de caracteres."""
    palavras = (texto or "").split()
    linhas, atual = [], ""
    for p in palavras:
        tentativa = f"{atual} {p}".strip()
        if atual and fnt.getlength(tentativa) > largura_max:
            linhas.append(atual)
            atual = p
            if len(linhas) == max_linhas:
                break
        else:
            atual = tentativa
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    return linhas or [""]


def desenhar(texto, destino, largura, altura=None, tamanho_px=None, cor=(255, 255, 255, 255),
             margem_pct=0.08, regua=False, centrado=True):
    """Rasteriza `texto` num PNG transparente de `largura` px. Devolve (caminho, altura).

    `altura=None` recorta na altura do texto (bom pra manchete no topo); com altura fixa o
    bloco fica centrado verticalmente (bom pra cartela de tela cheia).
    """
    tamanho_px = int(tamanho_px or largura * 0.045)
    fnt = fonte(tamanho_px)
    margem = int(largura * margem_pct)
    linhas = quebrar(texto, fnt, largura - 2 * margem)
    passo = int(tamanho_px * 1.28)
    alto_texto = passo * len(linhas)
    alt = int(altura or alto_texto + int(tamanho_px * 0.5))
    img = Image.new("RGBA", (largura, alt), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y0 = (alt - alto_texto) // 2
    for i, linha in enumerate(linhas):
        w = fnt.getlength(linha)
        x = (largura - w) / 2 if centrado else margem
        d.text((x, y0 + i * passo), linha, font=fnt, fill=cor)
    if regua:
        lw, lh = int(largura * 0.07), max(2, int(alt * 0.006))
        ly = y0 + alto_texto + int(tamanho_px * 0.42)
        d.rectangle([(largura - lw) // 2, ly, (largura + lw) // 2, ly + lh], fill=AMBAR)
    destino = Path(destino)
    img.save(destino)
    return destino, alt
