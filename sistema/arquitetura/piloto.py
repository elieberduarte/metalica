# -*- coding: utf-8 -*-
"""A obra piloto do módulo de arquitetura: a casa alto padrão (30/10/2026; atualizada em 02/11 com o estudo de 30/10).

As medidas são as do chat OBRA · CASA ALTO PADRÃO (`Projeto/OBRAS/Casa-alto-padrao/medidas.md`):
- casa de 14,0 × 11,0 m, com x ao longo da frente e y para os fundos;
- vidro do térreo em y 1800 e do superior em y 600;
- piso do superior em +3,35;
- as aberturas das laterais e dos fundos ("Fachadas laterais e fundos");
- a garagem de 3 vagas a −0,35 com o terraço em cima, e o estúdio ("Garagem, terraço e estúdio");
- o telhado em 2 águas a 10% escondido pela platibanda até +8,20, e a casinha das caixas d'água até +9,00 ("Cobertura");
- a escada em U de 19 espelhos.

A divisão dos ambientes é a sugestão de planta aprovada para a demonstração (prova da fase 1, pág. 5). Só demonstração:
nada aqui é projeto aprovado.
"""
from nucleo3d.modelo import Documento

from . import modelo as M

NOME_PROJETO = "ARQUITETURA - CASA PILOTO"

NIVEIS = [
    {"nome": "Garagem", "cota": -350, "laje": 100},
    {"nome": "Térreo", "cota": 0, "laje": 100},
    {"nome": "Estúdio", "cota": 3000, "laje": 150},
    {"nome": "Superior", "cota": 3350, "laje": 350},
    {"nome": "Cobertura", "cota": 7000, "laje": 650},
    {"nome": "Platibanda", "cota": 8200, "laje": 0},
    {"nome": "Casinha", "cota": 9150, "laje": 150},
]


def _pj(u, L, h=2700):
    return {"tipo": "portajanela", "u": u, "largura": L, "altura": h}


def _j(u, L, h, peitoril):
    return {"tipo": "janela", "u": u, "largura": L, "altura": h, "peitoril": peitoril}


def _p(u, L, h=2100):
    return {"tipo": "porta", "u": u, "largura": L, "altura": h}


def _passagem(u, L, h=2100):
    return {"tipo": "passagem", "u": u, "largura": L, "altura": h}


def _ambientes(doc, nivel, lista):
    for nome, r, piso in lista:
        M.novo_ambiente(doc, nome, r, nivel, piso)


def terreo(doc: Documento):
    t, s = "Térreo", "Superior"
    # as laterais na face da casa (x 0 e 14 000), alinhadas com o superior, como no estudo; o vidro da frente em y 1800
    M.nova_parede(doc, (100, 1900), (13900, 1900), "EXT20", t, s, nome="Fachada frontal — térreo",
                  vaos=[_pj(600, 4000), _pj(4900, 4000), _pj(9200, 4000)])
    M.nova_parede(doc, (100, 1900), (100, 10900), "EXT20", t, s, nome="Fachada esquerda — térreo",
                  vaos=[_pj(700, 4000), _j(6500, 1000, 2300, 400)])                 # correr da sala; escada
    M.nova_parede(doc, (13900, 1900), (13900, 10900), "EXT20", t, s, nome="Fachada direita — térreo",
                  vaos=[_p(1300, 1400, 2900), _pj(2800, 500), _p(7150, 900, 2400)])  # pivotante, fixo, garagem
    M.nova_parede(doc, (100, 10900), (13900, 10900), "EXT20", t, s, nome="Fachada dos fundos — térreo",
                  vaos=[_j(2900, 800, 600, 1900), _j(4700, 1200, 600, 1900), _j(6600, 2800, 2200, 500),
                        _p(10350, 800), _j(11700, 1400, 1200, 1100)])
    M.nova_parede(doc, (100, 7400), (13900, 7400), "INT15", t, s, nome="Fundo da sala",
                  vaos=[_passagem(700, 1200), _p(3100, 700), _p(4800, 800), _p(7500, 900), _p(10700, 900)])
    for x in (2800, 4400, 6400, 9800):
        M.nova_parede(doc, (x, 7400), (x, 10900), "INT15", t, s, nome=f"Divisa x {x / 1000:.1f} — térreo")
    M.nova_laje(doc, [(0, 1800), (14000, 1800), (14000, 11000), (0, 11000)], t, nome="Piso do térreo")
    M.nova_escada(doc, [{"p0": [1500, 7550], "dir": [0, 1], "largura": 1000, "espelhos": 10},
                        {"p0": [1700, 10070], "dir": [0, -1], "largura": 1000, "espelhos": 9}], t, s,
                  patamares=[{"ret": [500, 2700, 10070, 10750], "apos": 10}], nome="Escada em U")
    _ambientes(doc, t, [("Estar / jantar / cozinha", (0, 14000, 1800, 7400), "porcelanato"),
                        ("Escada", (0, 2800, 7400, 11000), ""), ("Lavabo", (2800, 4400, 7400, 11000), "porcelanato"),
                        ("Despensa", (4400, 6400, 7400, 11000), "porcelanato"),
                        ("Escritório", (6400, 9800, 7400, 11000), "madeira"),
                        ("Serviço", (9800, 14000, 7400, 11000), "cerâmica")])


def superior(doc: Documento):
    s, c = "Superior", "Cobertura"
    M.nova_parede(doc, (100, 700), (13900, 700), "EXT20", s, c, nome="Fachada frontal — superior",
                  vaos=[_pj(800, 3200), _pj(4900, 4000), _pj(9900, 3200)])
    M.nova_parede(doc, (100, 700), (100, 10900), "EXT20", s, c, nome="Fachada esquerda — superior",
                  vaos=[_j(1100, 2600, 1800, 900), _j(5300, 1400, 700, 1900), _j(7700, 1000, 2400, 300)])
    M.nova_parede(doc, (13900, 700), (13900, 10900), "EXT20", s, c, nome="Fachada direita — superior",
                  vaos=[_pj(900, 3000), _j(5300, 1400, 700, 1900), _pj(7900, 1800)])   # S2, banho S2, terraço
    M.nova_parede(doc, (100, 10900), (13900, 10900), "EXT20", s, c, nome="Fachada dos fundos — superior",
                  vaos=[_j(500, 1800, 1500, 900), _pj(3100, 6000), _j(9700, 3400, 1500, 900)])
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
    _ambientes(doc, s, [("Quarto 3", (0, 4600, 600, 5400), "madeira"),
                        ("Suíte master", (4600, 9400, 600, 5400), "madeira"),
                        ("Suíte 2", (9400, 14000, 600, 5400), "madeira"),
                        ("Banho Q3", (0, 2400, 5400, 8000), "porcelanato"),
                        ("Closet", (4600, 7000, 5400, 8000), "madeira"),
                        ("Banho master", (7000, 9400, 5400, 8000), "porcelanato"),
                        ("Banho S2", (11000, 14000, 5400, 8000), "porcelanato"),
                        ("Escada", (0, 2800, 8000, 11000), ""),
                        ("Circulação / estar íntimo", (2800, 14000, 8000, 11000), "madeira")])


def garagem_e_estudio(doc: Documento):
    g, s = "Garagem", "Superior"
    M.nova_parede(doc, (14000, 5300), (20900, 5300), "EXT20", g, s, nome="Garagem — lado da entrada")
    M.nova_parede(doc, (20900, 5300), (20900, 13600), "EXT20", g, s, nome="Garagem — portão",
                  vaos=[_passagem(400, 7700, 2600)])
    M.nova_parede(doc, (14100, 13600), (20900, 13600), "EXT20", g, s, nome="Garagem — fundo")
    M.nova_parede(doc, (14100, 11000), (14100, 13600), "EXT20", g, s, nome="Garagem — junto da casa")
    M.nova_laje(doc, [(14000, 5200), (21000, 5200), (21000, 13700), (14000, 13700)], g, nome="Piso da garagem")
    M.nova_laje(doc, [(14000, 2900), (21000, 2900), (21000, 13700), (14000, 13700)], s,
                nome="Laje do terraço e marquise da entrada")
    _ambientes(doc, g, [("Garagem (3 vagas)", (14000, 21000, 5200, 13700), "cimento queimado")])

    t, e = "Térreo", "Estúdio"
    M.nova_parede(doc, (14400, 14200), (20200, 14200), "EXT20", t, e, nome="Estúdio — sul")
    M.nova_parede(doc, (20200, 14200), (20200, 18000), "EXT20", t, e, nome="Estúdio — leste")
    M.nova_parede(doc, (20200, 18000), (14400, 18000), "EXT20", t, e, nome="Estúdio — norte")
    M.nova_parede(doc, (14400, 18000), (14400, 14200), "EXT20", t, e, nome="Estúdio — vidro para o jardim",
                  vaos=[_pj(300, 3200, 2600)])
    M.nova_laje(doc, [(14300, 14100), (20300, 14100), (20300, 18100), (14300, 18100)], t, nome="Piso do estúdio")
    M.nova_laje(doc, [(14300, 14100), (20300, 14100), (20300, 18100), (14300, 18100)], e, nome="Laje do estúdio")
    _ambientes(doc, t, [("Estúdio", (14300, 20300, 14100, 18100), "madeira")])


def cobertura(doc: Documento):
    c, p, k = "Cobertura", "Platibanda", "Casinha"
    M.nova_laje(doc, [(0, 0), (14000, 0), (14000, 11000), (0, 11000)], c, nome="Laje da cobertura (forro)")
    M.nova_parede(doc, (100, 100), (13900, 100), "EXT20", c, p, nome="Platibanda — frente")
    M.nova_parede(doc, (13900, 100), (13900, 10900), "EXT20", c, p, nome="Platibanda — direita")
    M.nova_parede(doc, (13900, 10900), (3800, 10900), "EXT20", c, p, nome="Platibanda — fundos")
    M.nova_parede(doc, (100, 7700), (100, 100), "EXT20", c, p, nome="Platibanda — esquerda")
    # a casinha das caixas d'água sobre a escada: a platibanda continua nela, mais alta
    M.nova_parede(doc, (100, 7700), (3800, 7700), "EXT20", c, k, nome="Casinha — frente")
    M.nova_parede(doc, (3800, 7700), (3800, 10900), "EXT20", c, k, nome="Casinha — lado do telhado",
                  vaos=[_p(1400, 800, 1800)])
    M.nova_parede(doc, (3800, 10900), (100, 10900), "EXT20", c, k, nome="Casinha — fundos")
    M.nova_parede(doc, (100, 10900), (100, 7700), "EXT20", c, k, nome="Casinha — esquerda")
    M.nova_laje(doc, [(-200, 7400), (4100, 7400), (4100, 11200), (-200, 11200)], k, nome="Laje da casinha")
    # telhas termoacústicas em 2 águas a 10%, cumeeira em y 5500, beirais a +7,30 junto das calhas das platibandas
    M.novo_telhado(doc, [
        {"ret": [200, 13800, 200, 5500], "beiral_y": 200, "z_beiral": 7300, "inclinacao": 0.10},
        {"ret": [3900, 13800, 5500, 10800], "beiral_y": 10800, "z_beiral": 7300, "inclinacao": 0.10},
        {"ret": [200, 3900, 5500, 7600], "beiral_y": 10800, "z_beiral": 7300, "inclinacao": 0.10},
    ], nome="Telhado termoacústico — 2 águas a 10%")


def terreno(doc: Documento):
    """o lote do medidas.md (30,5 × 34,8 m) e o jardim em volta do deck da piscina (de x −3500 a 20500, até y 2200), da
    casa, da garagem com a rampa e o caminho da entrada, e do estúdio com o deck do ofurô. Estimativa do estudo"""
    M.novo_lote(doc, [(-8000, -14800), (22500, -14800), (22500, 20000), (-8000, 20000)], permeaveis=[
        [(-8000, -14800), (22500, -14800), (22500, -12500), (-8000, -12500)],     # canteiros da frente
        [(-8000, -12500), (-3500, -12500), (-3500, 20000), (-8000, 20000)],       # lateral esquerda
        [(-3500, 2200), (0, 2200), (0, 20000), (-3500, 20000)],
        [(0, 11000), (11900, 11000), (11900, 20000), (0, 20000)],                 # fundos da casa
        [(11900, 18100), (22500, 18100), (22500, 20000), (11900, 20000)],         # atrás do estúdio
        [(20300, 13700), (22500, 13700), (22500, 18100), (20300, 18100)],
        [(20500, -12500), (22500, -12500), (22500, 2900), (20500, 2900)],         # lateral direita do deck
    ], nome="Lote 30,5 × 34,8 m")


def montar_casa() -> Documento:
    doc = Documento(nome=NOME_PROJETO)
    M.definir_niveis(doc, NIVEIS)
    terreno(doc)
    terreo(doc)
    superior(doc)
    garagem_e_estudio(doc)
    cobertura(doc)
    resumo = M.regenerar(doc)
    M.so_camadas_da_arquitetura(doc)
    doc.metadados["arquitetura"]["piloto"] = {"origem": "OBRA · CASA ALTO PADRÃO (medidas.md) + sugestão de planta da "
                                                        "prova da fase 1", "resumo": resumo}
    return doc
