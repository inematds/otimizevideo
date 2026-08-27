"""Provedor de imagem (Task 10b) — gera a ilustração que substitui o apresentador.

Só existe um provedor real: fal.ai rodando flux-2-klein (o default pessoal do usuário
para imagem). O contrato é mínimo de propósito — `gerar(prompt, destino) -> uso` —
porque a fase `substituir` só precisa de "um PNG 16:9 neste caminho"; trocar de
provedor é escrever outra classe com esse mesmo método.
"""
import requests
from pathlib import Path
from otv.util.keys import key

FAL_MODELO = "fal-ai/flux-2/klein/9b"


class Imagem:
    nome = "?"

    def gerar(self, prompt, destino):  # -> uso (dict)
        raise NotImplementedError


class Fal(Imagem):
    def __init__(self, modelo=FAL_MODELO):
        self.modelo, self.nome = modelo, f"fal/{modelo}"

    def gerar(self, prompt, destino):
        r = requests.post(f"https://fal.run/{self.modelo}",
                          headers={"Authorization": f"Key {key('FAL_KEY')}"},
                          json={"prompt": prompt, "image_size": "landscape_16_9",
                                "num_images": 1, "output_format": "png"},
                          timeout=300)
        r.raise_for_status()
        j = r.json()
        imgs = j.get("images") or []
        if not imgs or not imgs[0].get("url"):
            raise RuntimeError(f"fal não devolveu imagem: {str(j)[:200]}")
        # download atômico: um .parte renomeado no fim, pra que um PNG truncado por
        # queda de rede nunca seja reaproveitado como "já gerado" na próxima rodada.
        destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(destino.suffix + ".parte")
        img = requests.get(imgs[0]["url"], timeout=300)
        img.raise_for_status()
        tmp.write_bytes(img.content); tmp.replace(destino)
        return {"provedor": self.nome, "cost": 0.0}


def criar_imagem(cfg, slot=None):
    slot = slot or cfg.get("imagem", "fal")
    if slot == "fal":
        return Fal(cfg.get("modelos", {}).get("fal_imagem", FAL_MODELO))
    raise ValueError(f"provedor de imagem desconhecido: {slot!r} (use 'fal')")
