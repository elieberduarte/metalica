# -*- coding: utf-8 -*-
"""DXF de corte das chapas (Q19 do teste de primeiro uso IFC → pranchas, 16/10/2026): um DXF por posição de chapa, em
milímetro real, só com o contorno (camada CORTE) e os furos (camada FURO) — sem cota, texto nem quadro —, num ZIP com o
nome no padrão do nesting: "CH2_6,35mm_56x.dxf". A detalhista abria o "Detalhamento – chaparias" e exportava o desenho
inteiro (cotas, textos, chumbadores e tirantes juntos) e teria de limpar à mão para a plasma.

O contorno e os furos vêm do levantamento (o mesmo das pranchas): a chapa no sistema dela, a vista de frente."""
import os
import re
import tempfile
import zipfile
from typing import List, Sequence

from saida.detalhamento import Posicao

CAMADA_CORTE = "CORTE"
CAMADA_FURO = "FURO"


def _num(x: float) -> str:
    return ("%.2f" % x).rstrip("0").rstrip(".").replace(".", ",")


def nome_do_arquivo(pos: Posicao) -> str:
    """"CH2_6,35mm_56x.dxf" — o nome de produção, a espessura e a quantidade; sem caractere que o Windows recuse."""
    nome = re.sub(r'[\\/:*?"<>|\s]+', "-", str(pos.nome or pos.marca)).strip("-") or "chapa"
    return "%s_%smm_%dx.dxf" % (nome, _num(pos.espessura or pos.T or 0.0), int(pos.quantidade or 0))


def desenho_de_corte(pos: Posicao):
    """O Desenho (escala 1) de uma chapa: o contorno fechado e os furos (redondo: círculo; oblongo: dois arcos e duas
    retas; recorte: a polilinha dele)."""
    from nucleo2d.desenho import Arco, Circulo, Desenho, Linha, Polilinha
    d = Desenho(nome=pos.nome or pos.marca, escala=1.0)
    d.add(Polilinha(camada=CAMADA_CORTE, vertices=[(float(x), float(y)) for x, y in pos.contorno], fechada=True))
    for f in pos.furos:
        if getattr(f, "vista", "frente") != "frente":
            continue
        if f.tipo == "redondo" and f.d > 0:
            d.add(Circulo(camada=CAMADA_FURO, centro=(f.x, f.y), raio=f.d / 2.0))
        elif f.tipo == "oblongo" and f.larg > 0 and f.alt > 0:
            # o rasgo no sentido do maior lado: comprimento total `larg` e largura `alt`
            L, B = max(f.larg, f.alt), min(f.larg, f.alt)
            deitado = f.larg >= f.alt
            r = B / 2.0
            meio = L / 2.0 - r
            if deitado:
                c1, c2 = (f.x - meio, f.y), (f.x + meio, f.y)
                d.add(Linha(camada=CAMADA_FURO, a=(c1[0], f.y - r), b=(c2[0], f.y - r)))
                d.add(Linha(camada=CAMADA_FURO, a=(c1[0], f.y + r), b=(c2[0], f.y + r)))
                d.add(Arco(camada=CAMADA_FURO, centro=c2, raio=r, inicio=-90.0, fim=90.0))
                d.add(Arco(camada=CAMADA_FURO, centro=c1, raio=r, inicio=90.0, fim=270.0))
            else:
                c1, c2 = (f.x, f.y - meio), (f.x, f.y + meio)
                d.add(Linha(camada=CAMADA_FURO, a=(f.x - r, c1[1]), b=(f.x - r, c2[1])))
                d.add(Linha(camada=CAMADA_FURO, a=(f.x + r, c1[1]), b=(f.x + r, c2[1])))
                d.add(Arco(camada=CAMADA_FURO, centro=c2, raio=r, inicio=0.0, fim=180.0))
                d.add(Arco(camada=CAMADA_FURO, centro=c1, raio=r, inicio=180.0, fim=360.0))
        elif f.tipo == "recorte" and getattr(f, "pontos", None):
            d.add(Polilinha(camada=CAMADA_FURO, vertices=[(float(x), float(y)) for x, y in f.pontos], fechada=True))
    return d


def chapas_para_corte(posicoes: Sequence[Posicao]) -> List[Posicao]:
    """As chapas planas com contorno (a dobrada vai pela tira, outro assunto; a cantoneira é furada na fábrica)."""
    return [p for p in posicoes if p.classe == "chapa" and len(p.contorno or []) >= 3 and (p.quantidade or 0) > 0]


def gravar_zip(posicoes: Sequence[Posicao], caminho_zip: str) -> dict:
    """O ZIP com um DXF por chapa. Devolve {"arquivo", "chapas", "nomes"}."""
    from nucleo2d import dxf_cad
    chapas = chapas_para_corte(posicoes)
    nomes = []
    os.makedirs(os.path.dirname(caminho_zip), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="corte_") as tmp, zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as z:
        usados = set()
        for p in sorted(chapas, key=lambda q: str(q.nome or q.marca)):
            nome = nome_do_arquivo(p)
            base, k = nome, 2
            while nome in usados:                       # duas posições com o mesmo nome de produção
                nome = base[:-4] + "_%d.dxf" % k
                k += 1
            usados.add(nome)
            arq = os.path.join(tmp, nome)
            dxf_cad.exportar(desenho_de_corte(p), arq, escala=1.0)
            z.write(arq, nome)
            nomes.append(nome)
    return {"arquivo": caminho_zip, "chapas": len(nomes), "nomes": nomes}
