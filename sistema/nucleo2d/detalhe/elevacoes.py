# -*- coding: utf-8 -*-
"""As elevações das fachadas.

Parte do detalhamento dos conjuntos (nucleo2d/detalhe/conjuntos.py é a fachada; dividido do conjuntos.py em
13/11/2026, sem mudar a lógica)."""
import collections
import heapq
import math
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto
from nucleo2d.desenho import Cota as _Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import _mm
from saida.dobras import com_bitola, com_bitola_e_mm

from nucleo2d.detalhe.base import (
    parafusos_posicionados, largura_da_chamada,  # noqa: E402
    ALTURA_CHAMADA,
    ALTURA_COTA,
    CAMADAS_PECAS,
    TIPOS_NOME,
    _Papel,
    _caixa,
    _cruz,
    _dot,
    _eh_redonda_perfil,
    _eixo_da_peca,
    _marcas,
    _norm,
    _registrar_camadas_de_pecas,
    _sub,
    _tipo_ifc,
    parafusos_no_conjunto)
from nucleo2d.detalhe.conjuntos_grupos import (  # noqa: E402
    _casco,
    _sobrepoe)
from nucleo2d.detalhe.localizacao import (  # noqa: E402
    MENOR_ITEM_LOCALIZACAO,
    _eixos_do_modelo,
    _itens_de_localizacao)


# ------------------------------------------------------------------ as elevações das fachadas
#: A faixa de parede que entra numa elevação (mm, medida do plano de fora): as treliças, as terças e o painel interno da
#: parede ficam a até isto; a parede do outro lado fica fora.
FAIXA_ELEVACAO = 1500.0


#: Parede com menos peças que esta fração do modelo não ganha elevação (o oitão aberto do PRATI, com duas treliças de canto).
MINIMO_ELEVACAO = 0.08


def desenho_de_elevacoes(doc: Documento, pecas: Sequence[Solido], titulo: str = "Detalhamento – elevações",
                         ignorar: Sequence[str] = (), nomes: Optional[Dict[str, str]] = None,
                         camadas_pecas: Optional[Dict[str, str]] = None, eixos: Optional[dict] = None,
                         nomes_producao: Optional[dict] = None) -> Desenho:
    """Cada parede do modelo vista de fora, inteira — não o corte do pórtico típico da localização (pedido do usuário,
    14/10: "trazer as elevações laterais e frontal"; o corte "parece estar incompleto"). As peças da faixa da parede
    (FAIXA_ELEVACAO do plano de fora) projetadas pelo contorno convexo, a marca de cada conjunto no lugar, a peça solta
    marcada uma vez por elevação, os eixos que cruzam a fachada e as cotas (total e entre eixos). Lados com poucas peças
    (MINIMO_ELEVACAO) não saem."""
    from nucleo2d.pranchas import escala_normalizada
    fora = set(ignorar or ())
    pecas = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome) not in fora and e.vertices]
    if not pecas:
        raise ErroDeDados("sem peças para as elevações.")
    todos = [v for e in pecas for v in e.vertices]
    minimo = [min(v[i] for v in todos) for i in range(3)]
    maximo = [max(v[i] for v in todos) for i in range(3)]
    centro_de = {e.id: tuple(sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)) for e in pecas}
    # (nome do lado, w = para onde o observador olha, u = direita no papel, a coordenada da parede, o sinal para dentro)
    lados = [("Y mín", (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), 1, minimo[1], 1.0),
             ("Y máx", (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), 1, maximo[1], -1.0),
             ("X mín", (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0, minimo[0], 1.0),
             ("X máx", (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 0, maximo[0], -1.0)]
    v = (0.0, 0.0, 1.0)
    itens = _itens_de_localizacao(pecas)
    # os eixos com os nomes de produção, como a localização e a chumbação: sem eles a identificação achava outra malha
    # (1–16 × A–M na ME-Sooro, contra 1–7 × A–E das plantas — R02 da 2ª rodada do primeiro uso IFC, 16/10)
    ex_modelo = _eixos_do_modelo(doc, eixos, nomes_producao)
    segs = []
    if ex_modelo:
        from nucleo3d.eixos import segmentos
        segs = segmentos(ex_modelo)
    vistas = []
    for nome_lado, w, u, k_coord, plano, sinal in lados:
        faixa = [e for e in pecas if 0.0 <= sinal * (centro_de[e.id][k_coord] - plano) <= FAIXA_ELEVACAO]
        if len(faixa) < MINIMO_ELEVACAO * len(pecas):
            continue
        # o nome da fachada: o eixo cuja linha corre dentro da faixa, paralela à parede
        nome_eixo = ""
        for s_ in segs:
            dir_ = _norm(_sub(s_["b"], s_["a"]))
            if abs(_dot(dir_, u)) > 0.9 and 0.0 <= sinal * (s_["a"][k_coord] - plano) <= FAIXA_ELEVACAO + 600.0:
                nome_eixo = s_["nome"]
                break
        vistas.append((nome_lado, nome_eixo, w, u, faixa, k_coord, plano, sinal))
    if not vistas:
        raise ErroDeDados("nenhuma parede com peças suficientes para uma elevação.")
    # a escala pela fachada mais larga e pela soma das alturas (todas numa coluna)
    medidas = []
    for nome_lado, nome_eixo, w, u, faixa, k_coord, plano, sinal in vistas:
        vv = [q for e in faixa for q in e.vertices]
        us = [_dot(q, u) for q in vv]
        vs = [_dot(q, v) for q in vv]
        medidas.append((max(us) - min(us), max(vs) - min(vs)))
    folga_papel = 45.0
    esc = escala_normalizada(max(max(m[0] for m in medidas) / 760.0,
                                 (sum(m[1] for m in medidas) + folga_papel * len(medidas)) / 520.0, 1.0))
    d = Desenho(nome=titulo, escala=esc)
    folga = folga_papel * esc
    h_txt = 2.5 * esc
    atr_base = {"detalhe": "elevacao"}
    y0 = 0.0
    for (nome_lado, nome_eixo, w, u, faixa, k_coord, plano, sinal), (larg_v, alt_v) in zip(reversed(vistas), reversed(medidas)):
        nome = "ELEVAÇÃO – EIXO %s" % nome_eixo if nome_eixo else "ELEVAÇÃO – LADO %s" % nome_lado
        vv = [q for e in faixa for q in e.vertices]
        u0, v0 = min(_dot(q, u) for q in vv), min(_dot(q, v) for q in vv)
        p = _Papel(d, dict(atr_base, vista=nome), 0.0, y0)
        ids_faixa = {e.id for e in faixa}
        n_pecas = 0
        for e in faixa:
            pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices]
            casco = _casco(pts)
            if len(casco) < 3:
                continue
            m = _marcas(e)
            atr = dict(atr_base, vista=nome, origem=e.id, nome=e.nome or "")
            if m.get("posicao"):
                atr["posicao"] = str(m["posicao"])
            if m.get("conjunto"):
                atr["conjunto"] = str(m["conjunto"])
            pp = _Papel(d, atr, 0.0, y0)
            cam = (camadas_pecas or {}).get(str(m.get("posicao") or ""), "")
            if cam:
                _registrar_camadas_de_pecas(d)
            pp.polilinha(casco, fechada=True, camada=cam or "ACO-FINO")
            p.pontos.extend(pp.pontos)
            n_pecas += 1
        # as marcas: cada conjunto no lugar; a peça solta uma vez por elevação (as terças e as agulhas repetem em todo vão)
        caixas: List[tuple] = []
        rotulos = []
        ja = set()
        for rotulo, lista in itens:
            lista_f = [e for e in lista if e.id in ids_faixa]
            if not rotulo or not lista_f:
                continue
            nome_r = (nomes or {}).get(rotulo) or rotulo
            solta = len(lista) == 1 and str(_marcas(lista[0]).get("conjunto") or "") in ("", str(_marcas(lista[0]).get("posicao") or ""))
            if solta:
                if nome_r in ja:
                    continue
                ja.add(nome_r)
            vc = [q for e in lista_f for q in e.vertices]
            ext3 = max(max(q[i] for q in vc) - min(q[i] for q in vc) for i in range(3))
            if ext3 < MENOR_ITEM_LOCALIZACAO:
                continue
            pu = [_dot(q, u) - u0 for q in vc]
            pv = [_dot(q, v) - v0 for q in vc]
            rotulos.append((nome_r, (sum(pu) / len(pu), sum(pv) / len(pv))))
        rotulos.sort(key=lambda r: (r[1][1], r[1][0]))
        for rotulo, (cx, cy) in rotulos:
            larg = 0.75 * h_txt * len(rotulo)
            caixa = None
            livre = False
            for passo in range(4):
                dy = passo * 1.3 * h_txt
                caixa = (cx - larg / 2, cy + dy - h_txt / 2, cx + larg / 2, cy + dy + h_txt / 2)
                if not any(_sobrepoe(caixa, cb, 0.2 * h_txt) for cb in caixas):
                    livre = True
                    break
            if not livre:
                continue
            caixas.append(caixa)
            p.texto(cx, caixa[1], rotulo, h_txt, "TEXTO", alinhamento="centro")
        # os eixos que cruzam a fachada: linha vertical com a bolinha e o nome em cima
        xs_eixos = []
        if segs:
            r = 4.5 * esc
            h_e = 3.5 * esc
            for s_ in segs:
                dir_ = _norm(_sub(s_["b"], s_["a"]))
                if abs(_dot(dir_, w)) < 0.9:
                    continue
                xe = _dot(s_["a"], u) - u0
                if xe < -2.0 * r or xe > larg_v + 2.0 * r:
                    continue
                xs_eixos.append((xe, s_["nome"]))
                p.linha(xe, -4.0 * esc, xe, alt_v + 6.0 * esc, camada="EIXO")
                p.circulo(xe, alt_v + 6.0 * esc + r, r, camada="EIXO")
                p.texto(xe, alt_v + 6.0 * esc + r - 0.35 * h_e, s_["nome"], h_e, "EIXO", alinhamento="centro")
        xs_eixos.sort()
        if len(xs_eixos) >= 2:
            p.cadeia_h([x_ for x_, _n in xs_eixos], 0, -10.0, exigir_espaco=False)
            p.cota_h(0, larg_v, 0, -18.0)
        else:
            p.cota_h(0, larg_v, 0, -10.0)
        p.cota_v(0, alt_v, larg_v, 10.0)
        y_tit = p.extremos[1] - p.dy - 6.0 * esc
        atr_t = p.atr
        p.atr = dict(atr_t, cabecalho=0)
        p.texto(0, y_tit, nome, 3.5 * esc)
        p.atr = dict(atr_t, cabecalho=1)
        p.texto(0, y_tit - 4.5 * esc, "a parede inteira vista de fora (peças a até %s m do plano de fora); marca do conjunto no "
                "lugar de montagem, peça solta marcada uma vez" % ("%.1f" % (FAIXA_ELEVACAO / 1000.0)).replace(".", ","), 2.0 * esc)
        p.atr = atr_t
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": nome, "tipo": "elevacao", "pecas_cortadas": 0, "pecas_projetadas": n_pecas,
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [0.0, y0], "avisos": [],
                         "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})
        y0 = ext_c[3] + folga          # a próxima elevação acima desta (a lista está invertida: a primeira fica no topo)
    d.metadados["detalhamento"] = {"grupo": "elevacoes", "posicoes": [], "itens": {}}
    return d
