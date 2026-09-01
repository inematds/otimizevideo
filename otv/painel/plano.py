"""Edição do plan.json pelo painel.

O README (seção 9) sempre disse que dá pra editar o `plan.json` na mão e re-renderizar sem
chamar modelo nenhum — é o que dá controle editorial sobre a escolha automática. Este módulo
é essa mesma edição, pela tela, com as validações que um editor de texto não faz.

Duas garantias que existem porque a entrada vem da rede:
- só `in`, `out` e a inclusão do segmento (mais a manchete) são editáveis; todo o resto do
  segmento (`unidades`, `visual`, `substituir`, `texto`) é preservado do plano original,
  casando por índice. Assim um POST malformado não consegue inventar campo nem apagar o que
  o pipeline calculou;
- o plano antigo é copiado para `plan.bak.json` antes de gravar, então uma edição ruim é
  reversível sem re-rodar nada.
"""
import json, shutil
from pathlib import Path

MIN_SEG_S = 0.3


class Invalido(ValueError):
    """Edição recusada — a mensagem vai direto pro usuário na tela."""


def _num(v, campo, i):
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        raise Invalido(f"segmento {i}: '{campo}' precisa ser número (recebi {v!r})")


def aplicar(plano, edicao, duracao_s=None):
    """Devolve o plano novo. Não escreve nada — quem escreve é salvar()."""
    segs = plano.get("segmentos") or []
    pedidos = edicao.get("segmentos")
    if pedidos is None:
        novos = list(segs)
    else:
        if not isinstance(pedidos, list):
            raise Invalido("'segmentos' precisa ser uma lista")
        novos = []
        for p in pedidos:
            if not isinstance(p, dict):
                raise Invalido("cada segmento precisa ser um objeto")
            i = p.get("i")
            if not isinstance(i, int) or not 0 <= i < len(segs):
                raise Invalido(f"índice de segmento fora do plano: {i!r}")
            if p.get("incluir") is False:
                continue
            base = dict(segs[i])                      # preserva unidades/visual/substituir/texto
            base["in"] = _num(p.get("in", base.get("in")), "in", i)
            base["out"] = _num(p.get("out", base.get("out")), "out", i)
            if base["out"] - base["in"] < MIN_SEG_S:
                raise Invalido(f"segmento {i}: fim ({base['out']}s) precisa ser pelo menos "
                               f"{MIN_SEG_S}s depois do início ({base['in']}s)")
            if base["in"] < 0:
                raise Invalido(f"segmento {i}: início negativo ({base['in']}s)")
            if duracao_s and base["out"] > duracao_s + 0.5:
                raise Invalido(f"segmento {i}: fim ({base['out']}s) passa da duração do "
                               f"vídeo ({duracao_s:.1f}s)")
            novos.append(base)
        if not novos:
            raise Invalido("o corte ficaria vazio — mantenha pelo menos um segmento")

    saida = dict(plano)
    saida["segmentos"] = novos
    saida["total_s"] = round(sum(s["out"] - s["in"] for s in novos), 2)
    if "manchete" in edicao:
        m = edicao["manchete"]
        if m is not None and not isinstance(m, str):
            raise Invalido("manchete precisa ser texto")
        saida["manchete"] = (m or "").strip() or None
    # a narração foi gerada para os segmentos ANTIGOS: um wav por segmento, casado por
    # posição. Mexer na lista invalida esse casamento, e o render falha com uma mensagem
    # sobre contagem de arquivos. Melhor limpar aqui e dizer o que fazer.
    if saida.get("narracao") and pedidos is not None and len(novos) != len(segs):
        saida["narracao"] = None
        saida["narracao_invalidada"] = True
    return saida


def salvar(dir, edicao):
    """Aplica a edição no plan.json da pasta. Devolve (plano_novo, avisos)."""
    dir = Path(dir)
    arq = dir / "plan.json"
    if not arq.exists():
        raise Invalido("esta rodada não tem plan.json — rode a seleção antes")
    plano = json.loads(arq.read_text())
    meta = {}
    if (dir / "metadata.json").exists():
        try:
            meta = json.loads((dir / "metadata.json").read_text())
        except json.JSONDecodeError:
            meta = {}
    novo = aplicar(plano, edicao, meta.get("duracao_s"))
    avisos = []
    if novo.pop("narracao_invalidada", False):
        avisos.append("a narração foi descartada porque o número de segmentos mudou — "
                      "rode 'narrar' de novo antes do render se o modo for B ou N")
    shutil.copy(arq, dir / "plan.bak.json")
    arq.write_text(json.dumps(novo, ensure_ascii=False, indent=1))
    return novo, avisos
