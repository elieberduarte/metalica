# -*- coding: utf-8 -*-
"""O estudo do configurador de galpões direto ao orçamento (usuário, 20/10: "direto ao orçamento").

O galpão do configurador é dimensionado em segundos (``nucleo.galpao``); para orçar não precisa passar pelo
detalhamento. Aqui a lista de material do cálculo vira a lista de materiais no formato que o orçamento lê
(``saida/orcamento.py``: ``posicoes`` com classe, perfil, quantidade, comprimento e peso), mais o que o cálculo
não tem como peça e o orçamento cobra:

* **telhas** — da cobertura (as duas águas, no comprimento da água), do fechamento lateral e dos oitões
  (quando o fechamento é de telha), em peças de largura útil ``LARGURA_UTIL_TELHA``; a **cumeeira** por peça;
* **chapas** — o cálculo as leva como 5 % do peso dos perfis: uma linha de chapa de espessura estimada;
* **parafusos, chumbadores e acessórios** — 3 % do peso: ficam fora do aço, com aviso (o dono preenche).

Tudo marcado ESTUDO: quando o projeto for detalhado, vale a lista do detalhamento.
"""
import math
from datetime import datetime
from typing import List

#: Largura útil da telha (m) para contar as peças do estudo (trapezoidal TP40/TP25 ~ 1,0 m útil).
LARGURA_UTIL_TELHA = 1.0
#: Comprimento útil da peça de cumeeira (m).
PECA_CUMEEIRA = 1.0
#: Espessura (mm) com que a chapa estimada (5 % do aço) vai ao preço.
ESPESSURA_CHAPA_ESTUDO = 12.5
#: Marcas da lista do cálculo que são estimativa percentual.
MARCA_CHAPAS, MARCA_DIVERSOS = "CH", "PF"

ORIGEM = "estudo do configurador de galpões"


def _posicao(marca, nome, classe, perfil, material, qtd, comp_m, peso_u, esp=0.0, largura_mm=0.0, obs=()):
    """Uma posição como as do levantamento do modelo (`saida.detalhamento.Posicao`)."""
    from saida.detalhamento import Posicao
    comp = comp_m * 1000.0
    p = Posicao(marca=marca, tipo_ifc="IfcMember", perfil=perfil, material=material, quantidade=int(qtd))
    p.classe, p.L, p.comprimento, p.peso = classe, comp, comp, float(peso_u)
    p.H = float(largura_mm)
    p.espessura = float(esp)
    p.nome = nome
    p.observacoes = list(obs)
    return p


#: Categoria da lista (nucleo2d.detalhe.base.CATEGORIAS) pela marca do cálculo do galpão.
CATEGORIA_DA_MARCA = {"P1": "TESOURAS", "P2": "TESOURAS", "V1": "TESOURAS", "VO": "TESOURAS", "PO": "TESOURAS",
                      "BS": "TESOURAS", "BI": "TESOURAS", "T1": "TERÇAS", "T2": "TERÇAS", "L1": "TERÇAS",
                      "L2": "TERÇAS", "LO": "TERÇAS", "CH": "CHAPAS"}


def _telhas(projeto) -> list:
    """As telhas, a cumeeira e o fechamento pelas medidas do galpão."""
    from nucleo.galpao import PESO_TELHA
    d = projeto.dados
    kn = PESO_TELHA.get(d.telha)
    if kn is None:
        try:
            from nucleo import cargas
            kn = cargas.peso(d.telha).valor
        except Exception:
            kn = 0.05
    kg_m2 = kn * 1000.0 / 9.81
    nome = d.telha if str(d.telha).lower().startswith("telha") else "Telha %s" % d.telha
    obs = ["estimativa do estudo: peças de %s m úteis" % str(LARGURA_UTIL_TELHA).replace(".", ",")]
    larg = LARGURA_UTIL_TELHA * 1000.0
    saida = []
    n_c = math.ceil(d.comprimento / LARGURA_UTIL_TELHA)
    agua = d.comprimento_agua
    saida.append(_posicao("TL", "Telha da cobertura (duas águas)", "telha", nome, "Telha", 2 * n_c, agua,
                          kg_m2 * agua * LARGURA_UTIL_TELHA, largura_mm=larg, obs=obs))
    saida.append(_posicao("CU", "Cumeeira", "Cumeeira", "Cumeeira", "Telha", math.ceil(d.comprimento / PECA_CUMEEIRA),
                          PECA_CUMEEIRA, 0.0, obs=["estimativa do estudo"]))
    if "telha" in str(d.fechamento_lateral or "").lower():
        h = d.altura_fechamento or d.altura_beiral
        saida.append(_posicao("TF", "Telha do fechamento lateral", "telha", nome, "Telha", 2 * n_c, h,
                              kg_m2 * h * LARGURA_UTIL_TELHA, largura_mm=larg, obs=obs))
        n_o = math.ceil(d.vao / LARGURA_UTIL_TELHA)
        h_o = d.altura_beiral + (d.altura_cumeeira - d.altura_beiral) / 2.0
        saida.append(_posicao("TO", "Telha dos oitões (altura média)", "telha", nome, "Telha", 2 * n_o, h_o,
                              kg_m2 * h_o * LARGURA_UTIL_TELHA, largura_mm=larg, obs=obs))
    return saida


def lista_do_estudo(projeto, identificacao: dict = None) -> dict:
    """A lista de materiais do estudo: as posições do cálculo pelo mesmo montador da lista de produção
    (``saida.lista_producao.montar``: romaneio, resumo por perfil com as barras de compra, chapas, telhas)."""
    from saida import lista_producao
    posicoes, categorias, diversos_kg = [], {}, 0.0
    for pc in projeto.lista_material:
        if pc.marca == MARCA_DIVERSOS:
            diversos_kg += pc.peso_total_kg
            continue
        if pc.marca == MARCA_CHAPAS:
            p = _posicao(pc.marca, pc.descricao, "chapa", "Chapa # %s mm (estimada)" % str(ESPESSURA_CHAPA_ESTUDO).replace(".", ","),
                         pc.material, 1, 0.0, pc.peso_total_kg, esp=ESPESSURA_CHAPA_ESTUDO,
                         obs=["estimativa do estudo: 5 % do peso dos perfis"])
        else:
            redonda = "ø" in str(pc.perfil)
            p = _posicao(pc.marca, pc.descricao, "barra_redonda" if redonda else "barra", pc.perfil, pc.material,
                         pc.quantidade, pc.comprimento_m, pc.peso_unit_kg)
        # a mesma marca com comprimentos diferentes (os pilares de oitão): uma posição por comprimento
        n = sum(1 for q in posicoes if q.marca.split("-")[0] == pc.marca)
        if n:
            p.marca = "%s-%d" % (pc.marca, n + 1)
        posicoes.append(p)
        categorias[p.marca] = "TIRANTES" if p.classe == "barra_redonda" else CATEGORIA_DA_MARCA.get(pc.marca, "BARRAS")
    for p in _telhas(projeto):
        posicoes.append(p)
        categorias[p.marca] = "TELHAS"
    lista = lista_producao.montar(posicoes, categorias, {}, projeto=identificacao or {"nome": projeto.dados.nome})
    lista.update(estudo=True, origem=ORIGEM, diversos_kg=round(diversos_kg, 1),
                 gerado=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return lista


def aviso_do_estudo(lista: dict) -> dict:
    """O aviso que acompanha o orçamento feito pela lista do estudo."""
    return {"nivel": "alto", "texto": (
        "ESTUDO: a lista vem do configurador de galpões (o dimensionamento), antes do detalhamento — telhas pelas "
        "medidas, chapas estimadas em 5 %% do aço e parafusos/chumbadores (~%s kg) fora, para o dono preencher. "
        "Quando o projeto for detalhado, vale a lista do detalhamento." % str(lista.get("diversos_kg") or 0).replace(".", ","))}
