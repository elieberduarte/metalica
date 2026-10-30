# -*- coding: utf-8 -*-
"""A obra piloto do módulo de arquitetura: a casa alto padrão (30/10/2026).

As medidas são as do chat OBRA · CASA ALTO PADRÃO (`Projeto/OBRAS/Casa-alto-padrao/medidas.md`):
- casa de 14,0 × 11,0 m, com x ao longo da frente e y para os fundos;
- vidro do térreo em y 1800 e do superior em y 600;
- piso do superior em +3,35, cobertura em +7,00 e platibanda até +8,20;
- entrada pivotante na lateral direita, porta do serviço para a garagem e porta do estar íntimo para o terraço.

A divisão dos ambientes é a sugestão de planta aprovada para a demonstração (prova da fase 1, pág. 5). Só demonstração:
nada aqui é projeto aprovado. A garagem, o estúdio, a escada e os guarda-corpos ficam para as próximas etapas.
"""
from nucleo3d.modelo import Documento

from . import modelo as M

NOME_PROJETO = "ARQUITETURA - CASA PILOTO"

NIVEIS = [
    {"nome": "Térreo", "cota": 0, "laje": 100},
    {"nome": "Superior", "cota": 3350, "laje": 350},
    {"nome": "Cobertura", "cota": 7000, "laje": 650},
    {"nome": "Platibanda", "cota": 8200, "laje": 0},
]


def _pj(u, L, h=2700):
    return {"tipo": "portajanela", "u": u, "largura": L, "altura": h}


def _j(u, L, h, peitoril):
    return {"tipo": "janela", "u": u, "largura": L, "altura": h, "peitoril": peitoril}


def _p(u, L, h=2100):
    return {"tipo": "porta", "u": u, "largura": L, "altura": h}


def _passagem(u, L, h=2100):
    return {"tipo": "passagem", "u": u, "largura": L, "altura": h}


def terreo(doc: Documento):
    t, s = "Térreo", "Superior"
    M.nova_parede(doc, (400, 1900), (13600, 1900), "EXT20", t, s, nome="Fachada frontal — térreo",
                  vaos=[_pj(300, 4000), _pj(4600, 4000), _pj(8900, 4000)])
    M.nova_parede(doc, (500, 1800), (500, 11000), "EXT20", t, s, nome="Fachada esquerda — térreo",
                  vaos=[_pj(500, 4600)])
    M.nova_parede(doc, (13500, 1800), (13500, 11000), "EXT20", t, s, nome="Fachada direita — térreo",
                  vaos=[_p(1400, 1400, 2700), _p(7250, 900, 2400)])            # entrada pivotante; serviço → garagem
    M.nova_parede(doc, (400, 10900), (13600, 10900), "EXT20", t, s, nome="Fachada dos fundos — térreo",
                  vaos=[_j(2600, 600, 600, 1600), _j(6600, 1800, 1200, 1100), _j(10600, 1200, 1000, 1200)])
    M.nova_parede(doc, (500, 7400), (13500, 7400), "INT15", t, s, nome="Fundo da sala",
                  vaos=[_passagem(300, 1200), _p(2700, 700), _p(4400, 800), _p(7100, 900), _p(10300, 900)])
    for x in (2800, 4400, 6400, 9800):
        M.nova_parede(doc, (x, 7400), (x, 10900), "INT15", t, s, nome=f"Divisa x {x / 1000:.1f} — térreo")
    M.nova_laje(doc, [(400, 1800), (13600, 1800), (13600, 11000), (400, 11000)], t, nome="Piso do térreo")
    for nome, r, piso in [("Estar / jantar / cozinha", (400, 13600, 1800, 7400), "porcelanato"),
                          ("Escada", (400, 2800, 7400, 11000), ""), ("Lavabo", (2800, 4400, 7400, 11000), "porcelanato"),
                          ("Despensa", (4400, 6400, 7400, 11000), "porcelanato"),
                          ("Escritório", (6400, 9800, 7400, 11000), "madeira"),
                          ("Serviço", (9800, 13600, 7400, 11000), "cerâmica")]:
        M.novo_ambiente(doc, nome, r, t, piso)


def superior(doc: Documento):
    s, c = "Superior", "Cobertura"
    M.nova_parede(doc, (100, 700), (13900, 700), "EXT20", s, c, nome="Fachada frontal — superior",
                  vaos=[_pj(800, 3200), _pj(4900, 4000), _pj(9900, 3200)])
    M.nova_parede(doc, (100, 700), (100, 10900), "EXT20", s, c, nome="Fachada esquerda — superior",
                  vaos=[_j(5600, 800, 600, 1500)])
    M.nova_parede(doc, (13900, 700), (13900, 10900), "EXT20", s, c, nome="Fachada direita — superior",
                  vaos=[_j(5600, 800, 600, 1500), _pj(7900, 1800)])            # banho S2; estar íntimo → terraço
    M.nova_parede(doc, (100, 10900), (13900, 10900), "EXT20", s, c, nome="Fachada dos fundos — superior",
                  vaos=[_pj(4100, 3600)])                                     # estar íntimo → varanda dos fundos
    M.nova_parede(doc, (100, 5400), (13900, 5400), "INT15", s, c, nome="Fundo dos quartos",
                  vaos=[_passagem(2600, 900), _passagem(4900, 900), _p(7950, 700), _passagem(9500, 900)])
    M.nova_parede(doc, (100, 8000), (13900, 8000), "INT15", s, c, nome="Circulação",
                  vaos=[_p(2950, 800), _p(5050, 900), _p(9550, 800)])
    M.nova_parede(doc, (4600, 700), (4600, 8000), "INT15", s, c, nome="Quarto 3 × suíte master")
    M.nova_parede(doc, (9400, 700), (9400, 8000), "INT15", s, c, nome="Suíte master × suíte 2")
    M.nova_parede(doc, (2400, 5400), (2400, 8000), "INT15", s, c, nome="Banho Q3", vaos=[_p(800, 700)])
    M.nova_parede(doc, (7000, 5400), (7000, 8000), "INT15", s, c, nome="Closet × banho master")
    M.nova_parede(doc, (11000, 5400), (11000, 8000), "INT15", s, c, nome="Banho S2", vaos=[_p(800, 700)])
    M.nova_parede(doc, (2800, 8000), (2800, 10900), "INT15", s, c, nome="Escada", vaos=[_passagem(300, 1100)])
    M.nova_laje(doc, [(0, -1800), (14000, -1800), (14000, 11000), (9400, 11000), (9400, 12400), (3000, 12400),
                      (3000, 11000), (0, 11000)], s, furos=[[(500, 7550), (2700, 7550), (2700, 10750), (500, 10750)]],
                nome="Laje do superior (com as varandas)")
    for nome, r, piso in [("Quarto 3", (0, 4600, 600, 5400), "madeira"),
                          ("Suíte master", (4600, 9400, 600, 5400), "madeira"),
                          ("Suíte 2", (9400, 14000, 600, 5400), "madeira"),
                          ("Banho Q3", (0, 2400, 5400, 8000), "porcelanato"),
                          ("Closet", (4600, 7000, 5400, 8000), "madeira"),
                          ("Banho master", (7000, 9400, 5400, 8000), "porcelanato"),
                          ("Banho S2", (11000, 14000, 5400, 8000), "porcelanato"),
                          ("Escada", (0, 2800, 8000, 11000), ""),
                          ("Circulação / estar íntimo", (2800, 14000, 8000, 11000), "madeira")]:
        M.novo_ambiente(doc, nome, r, s, piso)


def cobertura(doc: Documento):
    c, p = "Cobertura", "Platibanda"
    M.nova_laje(doc, [(0, 0), (14000, 0), (14000, 11000), (0, 11000)], c, nome="Laje da cobertura")
    for a, b, nome in [((0, 100), (14000, 100), "frente"), ((13900, 0), (13900, 11000), "direita"),
                       ((0, 10900), (14000, 10900), "fundos"), ((100, 0), (100, 11000), "esquerda")]:
        M.nova_parede(doc, a, b, "EXT20", c, p, nome=f"Platibanda — {nome}")


def montar_casa() -> Documento:
    doc = Documento(nome=NOME_PROJETO)
    M.definir_niveis(doc, NIVEIS)
    terreo(doc)
    superior(doc)
    cobertura(doc)
    resumo = M.regenerar(doc)
    M.so_camadas_da_arquitetura(doc)
    doc.metadados["arquitetura"]["piloto"] = {"origem": "OBRA · CASA ALTO PADRÃO (medidas.md) + sugestão de planta da "
                                                        "prova da fase 1", "resumo": resumo}
    return doc
