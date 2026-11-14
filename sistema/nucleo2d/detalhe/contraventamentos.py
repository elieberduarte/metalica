# -*- coding: utf-8 -*-
"""Contraventamentos: tirantes, roscas e as chapas de ponta.

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
    _classificar_pecas_do_conjunto,
    _eixos_do_conjunto)


# ============================================================ contraventamentos
#: Redondo mais curto que isto (mm) não é o tirante do contraventamento (gancho, esticador).
MENOR_TIRANTE = 600.0


def _tirante_principal(instancia: Sequence[Solido]):
    """A barra redonda mais comprida do conjunto (o tirante), ou None."""
    melhor, comp = None, 0.0
    for e in instancia:
        if not _eh_redonda_perfil(str(_marcas(e).get("perfil") or e.nome or "")):
            continue
        cx = _caixa(e)
        ext = max(cx[i][1] - cx[i][0] for i in range(3))
        if ext > comp:
            melhor, comp = e, ext
    return melhor if comp >= MENOR_TIRANTE else None


def _barra_mais_longa(instancia: Sequence[Solido]):
    """A peça mais comprida do conjunto (a barra do contraventamento que não é redonda); a principal escolhida no 3D
    vence."""
    escolhida = next((e for e in instancia if _marcas(e).get("principal")), None)
    if escolhida is not None:
        return escolhida
    melhor, comp = None, 0.0
    for e in instancia:
        cx = _caixa(e)
        ext = max(cx[i][1] - cx[i][0] for i in range(3))
        if ext > comp:
            melhor, comp = e, ext
    return melhor


def _bitola(perfil: str) -> str:
    """A bitola em polegadas escrita no perfil da barra redonda: "FE RED 3/8''" → '3/8"'."""
    m = re.search(r"(\d+(?:[ .\-]\d+/\d+|/\d+)?)\s*(?:''|\"|”)", perfil)
    return (m.group(1).strip() + '"') if m else ""


def _roscas(doc: Documento, inst: Sequence[Solido], origem, u, v, u0: float, v0: float, comprimento: float) -> List[tuple]:
    """As roscas do conjunto na vista (u, v): cada porca (ou arruela) solta perto da instância vai
    para a peça redonda em que ela está — o tirante, o gancho da agulha (G.1), a barra roscada do
    esticador — e a rosca é a ponta dessa peça mais perto da porca, `comprimento` mm (a barra
    roscada, inteira). Devolve [(peça, u0, u1, v do eixo, diâmetro)], uma por ponta roscada."""
    from nucleo2d.detalhe.base import _fixadores, _so_parafusos, _nome_do_parafuso, _autovetores
    from nucleo.perfis_fabrica import polegadas_mm
    redondas = []
    for e in inst:
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        if not _eh_redonda_perfil(perfil) or not getattr(e, "vertices", None):
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        pv = [_dot(_sub(q, origem), v) - v0 for q in e.vertices]
        d = polegadas_mm(_bitola(perfil)) or 10.0
        redondas.append((e, pu, pv, d, "ROSCAD" in perfil.upper()))
    if not redondas:
        return []
    caixas = [_caixa(e) for e in inst if getattr(e, "vertices", None)]
    minimo = [min(cx[i][0] for cx in caixas) - 200.0 for i in range(3)]
    maximo = [max(cx[i][1] for cx in caixas) + 200.0 for i in range(3)]
    fora, feitas, porcas_da = [], set(), {}
    for f in _so_parafusos(_fixadores(doc)):
        cc = tuple(sum(q[i] for q in f.vertices) / len(f.vertices) for i in range(3))
        if not all(minimo[i] <= cc[i] <= maximo[i] for i in range(3)):
            continue
        # só a porca e a arruela soltas (o parafuso de verdade — o M16 da castanha — traz a dele),
        # pela forma, como a legenda do conjunto as conta
        ext = []
        _, pca = _autovetores(f.vertices)
        for ax in pca:
            ts = [_dot(_sub(q, cc), ax) for q in f.vertices]
            ext.append(max(ts) - min(ts))
        _nome, pela_porca = _nome_do_parafuso(f, ext)
        if not (pela_porca or ext[0] <= 1.5 * ext[1]):
            continue
        fu = _dot(_sub(cc, origem), u) - u0
        fv = _dot(_sub(cc, origem), v) - v0
        # a peça redonda que passa pela porca: a que a contém no comprimento (a porca da agulha fica
        # além da ponta do ferro, no gancho; a do contravento, na barra roscada do esticador, não no
        # ferro liso soldado nela) e no eixo; só sem nenhuma, a de ponta até 40 mm dela
        no_eixo = [r for r in redondas if min(r[2]) - 15.0 <= fv <= max(r[2]) + 15.0]
        cand = ([r for r in no_eixo if min(r[1]) <= fu <= max(r[1])]
                or [r for r in no_eixo if min(r[1]) - 40.0 <= fu <= max(r[1]) + 40.0])
        if not cand:
            continue
        e, pu, pv, d, roscada = min(cand, key=lambda r: min(abs(fu - min(r[1])), abs(fu - max(r[1]))))
        a_, b_ = min(pu), max(pu)
        if roscada:
            x_a, x_b = a_, b_
        elif fu - a_ <= b_ - fu:
            x_a, x_b = a_, a_ + min(comprimento, 0.9 * (b_ - a_))
        else:
            x_a, x_b = b_ - min(comprimento, 0.9 * (b_ - a_)), b_
        # a porca e a arruela da mesma ponta contam uma vez; na barra roscada, cada grupo de porcas
        # (as duas pontas do esticador) é uma ponta roscada, com a rosca desenhada uma vez só
        if roscada:
            # as porcas a até 40 mm umas das outras são da mesma ponta
            ja = porcas_da.setdefault(e.id, [])
            if any(abs(fu - x) <= 40.0 for x in ja):
                continue
            ja.append(fu)
        else:
            chave = (e.id, round(x_a))
            if chave in feitas:
                continue
            feitas.add(chave)
        if roscada and any(r[0] is e for r in fora):
            fora.append((e, None, None, None, d))     # conta a ponta, sem desenhar de novo
            continue
        # o eixo na ponta roscada: os vértices do anel da ponta (o gancho da outra ponta espalha)
        ponta = x_a if abs(fu - x_a) <= abs(fu - x_b) else x_b
        anel = [q for q_u, q in zip(pu, pv) if abs(q_u - ponta) <= 15.0]
        v_c = (min(anel) + max(anel)) / 2 if anel and max(anel) - min(anel) <= 2.5 * d else fv
        fora.append((e, x_a, x_b, v_c, d))
    return fora


def _comprimento_na_vista(peca: Solido, instancia: Sequence[Solido]) -> float:
    """Extensão da peça ao longo do comprimento da vista do conjunto dela."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    us = [_dot(_sub(p, c), u) for p in peca.vertices]
    return max(us) - min(us)


def _extensao_do_conjunto(instancia: Sequence[Solido]) -> Tuple[float, float]:
    """(comprimento, altura) da instância na vista em que é desenhada."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    us = [_dot(_sub(p, c), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, c), v) for e in instancia for p in e.vertices]
    return max(us) - min(us), max(vs) - min(vs)


def _direcao_pelas_arestas(e) -> Optional[Tuple[float, float, float]]:
    """A direção da barra pelas arestas compridas da malha dela (as do comprimento, paralelas ao eixo),
    somadas no mesmo sentido; None sem faces."""
    vs, fs = getattr(e, "vertices", None) or [], getattr(e, "faces", None) or []
    arestas = []
    for f in fs:
        for i in range(len(f)):
            a, b = vs[f[i]], vs[f[(i + 1) % len(f)]]
            d = _sub(b, a)
            L = math.sqrt(_dot(d, d))
            if L > 1e-6:
                arestas.append((L, d))
    if not arestas:
        return None
    Lmax = max(L for L, _d in arestas)
    longas = [d for L, d in arestas if L >= 0.9 * Lmax]
    ref = longas[0]
    soma = [0.0, 0.0, 0.0]
    for d in longas:
        sg = 1.0 if _dot(d, ref) >= 0 else -1.0
        for i in range(3):
            soma[i] += sg * d[i]
    return _norm(tuple(soma))


def desenho_de_contraventamentos(doc: Documento, membros: Sequence[tuple], desenho: Desenho, dx: float, dy: float,
                                 nomes: Dict[str, str], nomes_conj: Dict[str, str], fundidas: Dict[str, str],
                                 comprimentos: Dict[str, float], rotular: bool = True) -> Tuple[float, float, float, float]:
    """Detalhe típico dos conjuntos que só diferem no comprimento da barra principal (mesmas
    peças de ponta): contraventamentos e agulhas. A elevação do mais comprido com o nome das
    peças de ponta embaixo e, no estilo do projeto do Posto (pedido do usuário, 28/09), as cotas
    empilhadas debaixo dela, todas do tamanho da barra desenhada, com o nome, o comprimento e a
    quantidade no meio — "CV.3 COMP=5150mm – 02X"; a rosca desenhada e cotada nas pontas da
    barra que têm porca. `membros` = [(rotulo do grupo, instância, nº de instâncias)]."""
    membros = sorted(membros, key=lambda m: _ordem_natural(nomes_conj.get(m[0], m[0])))

    def barra_de(inst_m):
        return _tirante_principal(inst_m) or _barra_mais_longa(inst_m)

    def comp_barra(inst_m):
        b_ = barra_de(inst_m)
        if b_ is None:
            return _extensao_do_conjunto(inst_m)[0]
        cx_ = _caixa(b_)
        return max(cx_[i][1] - cx_[i][0] for i in range(3))
    # o desenhado é o da barra mais comprida
    maior = max(membros, key=lambda m: comp_barra(m[1]))
    rotulo, inst, _ = maior
    rotulo_celula = " / ".join(m[0] for m in membros)
    c, u, v, w = _eixos_do_conjunto(inst)
    # a barra deitada no papel, como a das agulhas (o agulhamento lateral fica em pé no galpão): as cotas
    # empilhadas são do tamanho dela
    b0 = barra_de(inst)
    eixo_b = _eixo_da_peca(b0) if b0 is not None else None
    if eixo_b:
        # sempre na direção da barra: o eixo do conjunto (com as chapas das pontas) sai uns graus fora dela
        # e o montante lateral A.L. saía torto, com as cotas retas (pedido do usuário, 29/09)
        # a direção pelas arestas compridas da própria barra: o eixo pela média dos vértices saía uns graus
        # torto quando os furos ficam numa ponta (o montante lateral A.L., 3°), e alinhar a x/y/z entortava a
        # cantoneira A.C. que segue o caimento do telhado (29/09)
        a_ = _direcao_pelas_arestas(b0) or _norm(_sub(eixo_b[1], eixo_b[0]))
        if _dot(a_, u) < 0:
            a_ = tuple(-k for k in a_)
        a_ = _norm(_sub(a_, tuple(w[i] * _dot(a_, w) for i in range(3))))
        if _dot(a_, a_) > 0.5:
            u, v = a_, _norm(_cruz(a_, w))
    ws = [_dot(_sub(p, c), w) for e in inst for p in e.vertices]
    origem = tuple(c[i] + w[i] * (min(ws) - 10.0) for i in range(3))
    vista = _vistas.Vista(origem=origem, normal=w, acima=v, profundidade=None, cortar=False,
                          entidades=[e.id for e in inst], rotular=False, nome="Contraventamento %s" % rotulo_celula, tipo="conjunto")
    u, v, w = vista.eixos()
    antes = set(desenho.entidades)
    _vistas.gerar(doc, vista, desenho, (dx, dy))
    info = desenho.vistas[-1]
    larg, alt = info["largura"], info["altura"]
    camada_de = _classificar_pecas_do_conjunto(inst, (u, v, origem))
    _registrar_camadas_de_pecas(desenho)
    for e in (desenho.entidades[k] for k in desenho.entidades if k not in antes):
        e.atributos["conjunto"] = rotulo_celula
        e.atributos["detalhe"] = "conjunto"
        if e.camada in ("VISTA", "CORTE") and e.atributos.get("origem") in camada_de:
            e.camada = camada_de[e.atributos["origem"]]
    us = [_dot(_sub(p, origem), u) for e in inst for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in inst for p in e.vertices]
    u0, v0 = min(us), min(vs)
    atr = {"conjunto": rotulo_celula, "detalhe": "conjunto"}
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, passo = 10.0, 8.0
    tirante = _tirante_principal(inst) or _barra_mais_longa(inst)

    def nome_de(marca_ifc):
        f = fundidas.get(str(marca_ifc), str(marca_ifc))
        return nomes.get(f) or f
    # peças de ponta cotadas embaixo: barra roscada e chapa na 1ª linha, cantoneiras na 2ª
    extremos_pecas = []
    for e in inst:
        if e is tirante:
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        ext = max(pu) - min(pu)
        if ext < 20.0:
            continue
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        extremos_pecas.append([min(pu), max(pu), 0, nome_de(_marcas(e).get("posicao") or e.nome), perfil])
    # uma linha de cota por peça de cada ponta (as cantoneiras vizinhas não se atropelam),
    # com o nome da peça no texto: "150  B.7"
    extremos_pecas.sort(key=lambda r_: r_[0])
    meio = larg / 2.0
    for lado_ in (False, True):
        k = 0
        for r_ in extremos_pecas:
            if ((r_[0] + r_[1]) / 2 > meio) != lado_:
                continue
            k += 1
            r_[2] = k
    # as peças de ponta (gancho, chapas, barra roscada do esticador) são detalhe padrão,
    # iguais em todos: aqui só o nome embaixo de cada uma — as medidas estão no detalhe dela
    h_nome = 1.8 * esc
    for a_, b_, linha, nome_p, perfil in extremos_pecas:
        p.texto((a_ + b_) / 2, -(3.0 + 3.0 * (linha - 1)) * esc - h_nome, nome_p, h_nome, "TEXTO", alinhamento="centro")
    # cotas empilhadas por contraventamento: o tamanho da BARRA (sem as peças de ponta),
    # a partir da ponta dela no desenho
    if tirante is not None:
        pu_t = [_dot(_sub(q, origem), u) - u0 for q in tirante.vertices]
        pv_t = [_dot(_sub(q, origem), v) - v0 for q in tirante.vertices]
        t0, t1 = min(pu_t), max(pu_t)
    else:
        t0, t1 = 0.0, larg
    # a rosca nas pontas da barra que têm porca (o fixador perto da ponta, no eixo): as linhas
    # do fundo da rosca e os traços dos filetes ao longo de ROSCA_GANCHO, "ROSCA" embaixo e a
    # cota do comprimento em cima, como o Posto desenha (pedido do usuário, 28/09)
    linhas_lado = {False: 0, True: 0}
    n_roscas = 0
    for r_ in extremos_pecas:
        lado_ = (r_[0] + r_[1]) / 2 > meio
        linhas_lado[lado_] = max(linhas_lado[lado_], r_[2])
    from nucleo2d.detalhe.celulas import ROSCA_GANCHO
    bitola_rosca = ""
    for peca_r, x_a, x_b, v_c, d_b in _roscas(doc, inst, origem, u, v, u0, v0, ROSCA_GANCHO):
        if x_a is None:
            n_roscas += 1                             # outra ponta da mesma barra roscada
            continue
        from nucleo2d.detalhe.celulas import desenhar_rosca
        desenhar_rosca(p, x_a, x_b, v_c, d_b, esc)
        p.cota_h(x_a, x_b, v_c + d_b / 2, 4.0)
        n_roscas += 1
        lado_ = (x_a + x_b) / 2 > meio
        linhas_lado[lado_] += 1
        p.texto((x_a + x_b) / 2, -(3.0 + 3.0 * (linhas_lado[lado_] - 1)) * esc - h_nome, "ROSCA", h_nome, "TEXTO", alinhamento="centro")
        bitola_rosca = bitola_rosca or _bitola(str(_marcas(peca_r).get("perfil") or peca_r.nome or ""))
    # as cotas empilhadas debaixo da peça, uma por conjunto, todas do tamanho da barra desenhada
    # (o comprimento de cada uma vai no texto, no meio): "CV.1 COMP=4258mm – 08X", como o Posto
    y_base = -(3.0 + 3.0 * max(linhas_lado.values() or [0]) + 4.0) * esc - h_nome
    passo_c = 6.0
    from saida.lista_producao import BARRAS_COMERCIAIS
    longos = []                                       # os que passam da barra comercial (a A.C.5 de 18 m, 29/09)
    for i, (rot, inst_m, n_inst) in enumerate(membros):
        tir_m = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        marca_m = (fundidas.get(str(_marcas(tir_m).get("posicao") or tir_m.nome), str(_marcas(tir_m).get("posicao") or tir_m.nome))
                   if tir_m is not None else None)
        comp_m = (comprimentos.get(marca_m) if marca_m else None) or (
            _comprimento_na_vista(tir_m, inst_m) if tir_m is not None else _extensao_do_conjunto(inst_m)[0])
        nome_m = nomes_conj.get(rot, rot)
        if comp_m > max(BARRAS_COMERCIAIS) + 0.5:
            longos.append(nome_m)
        y_c = y_base - passo_c * i * esc
        txt = "%s COMP=%dmm – %02dx" % (nome_m, round(comp_m), n_inst)
        # a cota de cada um leva o conjunto dele (não o da célula inteira): escolhida no 2D, o 3D destaca só os
        # daquele comprimento — antes vinham os 198 do detalhe típico (pedido do usuário, 06/10)
        p.atr = dict(atr, conjunto=rot)
        p.cota_h(round(t0), round(t1), y_c, 0.0, texto=txt)
        for x_ in (round(t0), round(t1)):
            p.linha(x_, y_c - 1.5 * esc, x_, y_c + 1.5 * esc, "COTA")
        p.atr = atr
    # a dobra da barra (gancho na ponta): a altura da perna, cotada na própria ponta — só na barra redonda (a
    # aba da cantoneira do agulhamento lateral não é gancho)
    if tirante is not None and _eh_redonda_perfil(str(_marcas(tirante).get("perfil") or tirante.nome or "")):
        corpo = [pv for pu_, pv in zip(pu_t, pv_t) if t0 + 0.3 * (t1 - t0) < pu_ < t1 - 0.3 * (t1 - t0)]
        diam = (max(corpo) - min(corpo)) if corpo else 0.0
        for lado_esq in (True, False):
            ponta = [(pu_, pv) for pu_, pv in zip(pu_t, pv_t) if (pu_ < t0 + 250.0 if lado_esq else pu_ > t1 - 250.0)]
            if not ponta:
                continue
            vmin, vmax = min(q[1] for q in ponta), max(q[1] for q in ponta)
            if vmax - vmin - diam < 15.0:
                continue                              # ponta reta
            x_ = t0 if lado_esq else t1
            p.cota_v(vmin, vmax, x_, -off if lado_esq else off)
            # o trecho da dobra ao longo da barra (onde a perna começa)
            perna = [q[0] for q in ponta if (q[1] > max(corpo) + 2.0 or q[1] < min(corpo) - 2.0)] if corpo else []
            if perna:
                if lado_esq:
                    p.cota_h(t0, max(perna), vmax, 4.0)
                else:
                    p.cota_h(min(perna), t1, vmax, 4.0)
    # rótulos: tirante pelo perfil no meio; peças de ponta pelo nome
    if rotular:
        h = 1.8 * esc
        if tirante is not None:
            pu = [_dot(_sub(q, origem), u) - u0 for q in tirante.vertices]
            p.texto((min(pu) + max(pu)) / 2, alt + 2.0 * esc, str(_marcas(tirante).get("perfil") or tirante.nome or ""), h, "TEXTO", alinhamento="centro")
        pass
    # as chapas de ponta desenhadas de frente, à direita da ponta da barra, na escala dela, com o nome embaixo — uma
    # por chapa diferente do típico, e a quais conjuntos serve quando muda de um para outro (pedido do usuário, 01/10:
    # "nome e representação da chapa", desenhado à mão ao lado da A.C.1)
    # de que ponta é cada chapa: pela posição dela ao longo da barra, no conjunto desenhado
    x_das_chapas = {}
    for e in inst:
        if e is not tirante:
            pu_ = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
            x_das_chapas.setdefault(str(nome_de(_marcas(e).get("posicao") or e.nome) or ""), []).append((min(pu_) + max(pu_)) / 2.0)
    _chapas_de_ponta(p, membros, nome_de, nomes_conj, esc, larg, alt,
                     ((min(pv_t) + max(pv_t)) / 2.0) if tirante is not None else alt / 2.0, x_das_chapas)
    # título: tipo, nomes e, por contraventamento, o tirante com o comprimento de corte
    total = sum(m[2] for m in membros)
    linhas = ["%s – %02dx" % (" / ".join(nomes_conj.get(m[0], m[0]) for m in membros), total)]
    # a barra de cada um (nome e perfil); o comprimento de corte está na cota empilhada
    barras_ = collections.OrderedDict()
    for rot, inst_m, n_inst in membros:
        tir = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        if tir is None:
            continue
        marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
        nome_b = nomes.get(marca_t) or marca_t
        lista_b = barras_.setdefault(str(_marcas(tir).get("perfil") or tir.nome or ""), [])
        if nome_b not in lista_b:
            lista_b.append(nome_b)
    for perfil_b, nomes_b in barras_.items():
        linhas.append("Barra %s: %s" % (perfil_b, ", ".join(nomes_b)))
    if longos:
        linhas.append("%s maior que a barra comercial de %s m: prever emenda"
                      % (", ".join(longos), _mm(max(BARRAS_COMERCIAIS) / 1000.0)))
    # o padrão da fábrica na ponta roscada: 1 porca e 2 arruelas (pedido do usuário, 28/09) — não
    # o que o modelo tem (o projetista põe porcas e arruelas soltas, lidas pela forma)
    if n_roscas:
        bitola = (" Ø%s" % bitola_rosca) if bitola_rosca else ""
        linhas.append("Por ponta roscada: 1 porca sextavada%s + 2 arruelas lisas%s (%d ponta%s por unidade)"
                      % (bitola, bitola, n_roscas, "s" if n_roscas > 1 else ""))
    # as peças de ponta; quando mudam de um conjunto para outro (as chapas dos agulhamentos laterais),
    # por conjunto: "A.L.1: CH18 x2; A.L.2, DP.1: CH8 x2"
    por_ponta = collections.OrderedDict()
    for rot, inst_m, _n in membros:
        tir_m = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        cont = collections.Counter(nome_de(_marcas(e).get("posicao") or e.nome) for e in inst_m if e is not tir_m)
        chave_p = tuple(sorted(cont.items(), key=lambda kv: _ordem_natural(kv[0])))
        por_ponta.setdefault(chave_p, []).append(nomes_conj.get(rot, rot))
    txt_p = lambda ch: ", ".join("%s x%d" % (k, q) for k, q in ch)    # noqa: E731
    if len(por_ponta) == 1 and next(iter(por_ponta)):
        linhas.append("Peças de ponta (por unidade): " + txt_p(next(iter(por_ponta))))
    elif len(por_ponta) > 1:
        linhas.append("Peças de ponta (por unidade): " + "; ".join(
            "%s: %s" % (", ".join(nomes_m), txt_p(ch)) for ch, nomes_m in por_ponta.items() if ch))
    y = alt + (off + 4.0) * esc
    atr0 = p.atr
    for i, txt in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        p.atr = dict(atr0, cabecalho=len(linhas) - 1 - i)     # o bloco do título, para a caixa da prancha (29/09)
        p.texto(0, y, txt, alt_t * esc)
        y += (alt_t + 1.2) * esc
    p.atr = atr0
    ext = p.extremos
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


#: Entre a ponta da barra (e o que está desenhado nela) e a primeira chapa de ponta, e entre uma chapa e a outra (mm de
#: papel).
VAO_CHAPA_DE_PONTA = 8.0


def _chapas_de_ponta(p, membros, nome_de, nomes_conj, esc: float, larg: float, alt: float, v_eixo: float,
                     x_das_chapas: Optional[dict] = None) -> int:
    """No detalhe típico (contraventos, agulhas, cantoneiras A.C./A.L.), o SUPORTE MONTADO de cada ponta: as chapas
    daquela ponta juntas, na posição em que vão soldadas, na vista em que o conjunto aparece maior, na escala da barra,
    ao lado da ponta em que ele fica, com os nomes embaixo ("CH16 + CH17"). A chapa uma a uma vai no detalhamento de
    chaparia (pedido do usuário, 01/10: "pode montar o suporte montado, não as chapas — as chapas vão no projeto de
    chaparia"). Quando o suporte muda de um conjunto para outro, o nome diz a quais serve. Devolve quantos desenhou."""
    from nucleo2d.detalhe.montagens import _eh_chapa
    from saida.detalhamento import _autovetores
    x_das_chapas = x_das_chapas or {}
    suportes = collections.OrderedDict()               # (lado, nomes) → [peças, eixos da barra, [conjuntos]]
    for rot, inst_m, _n in membros:
        tir_m = _tirante_principal(inst_m) or _barra_mais_longa(inst_m)
        if tir_m is None:
            continue
        c_b, eix_b = _autovetores(tir_m.vertices)
        u3 = tuple(eix_b[0])
        s_b = [_dot(_sub(q, c_b), u3) for q in tir_m.vertices]
        meio_b = (min(s_b) + max(s_b)) / 2.0
        pontas = {0: [], 1: []}
        for e in inst_m:
            if e is tir_m:
                continue
            nome = str(nome_de(_marcas(e).get("posicao") or e.nome) or "")
            if not (_eh_chapa(e) or re.match(r"CH\s*\d", nome, re.I)):
                continue
            s_e = sum(_dot(_sub(q, c_b), u3) for q in e.vertices) / max(1, len(e.vertices))
            pontas[1 if s_e > meio_b else 0].append((nome, e))
        for k, pecas in pontas.items():
            if not pecas:
                continue
            nomes = tuple(sorted({n for n, _e in pecas}, key=_ordem_natural))
            # o mesmo suporte nas duas pontas (a cantoneira com a CH18 em cada uma) sai uma vez, à direita; o de uma
            # ponta só, do lado dela no conjunto desenhado (a CH15 da agulha, com o gancho)
            xs_n = [x for n in nomes for x in x_das_chapas.get(n, [])]
            lado = "esq" if xs_n and all(x < larg / 2.0 for x in xs_n) else "dir"
            if any(k_[1] == nomes for k_ in suportes):
                ent = suportes[next(k_ for k_ in suportes if k_[1] == nomes)]
                n_c = nomes_conj.get(rot, rot)
                if n_c not in ent[2]:
                    ent[2].append(n_c)
                continue
            ent = suportes.setdefault((lado, nomes), [[e for _n, e in pecas], eix_b, []])
            n_c = nomes_conj.get(rot, rot)
            if n_c not in ent[2]:
                ent[2].append(n_c)
    if not suportes:
        return 0
    todos = [nomes_conj.get(m[0], m[0]) for m in membros]
    ext = p.extremos
    h_nome = 1.8 * esc
    direita = max(larg, ext[2] - p.dx) + VAO_CHAPA_DE_PONTA * esc
    esquerda = min(0.0, ext[0] - p.dx) - VAO_CHAPA_DE_PONTA * esc
    feitos = 0
    for (lado, nomes), (pecas, eix_b, conj) in suportes.items():
        # a vista em que o suporte aparece maior: o plano de dois dos eixos da barra
        planos = ((0, 1), (0, 2), (1, 2))

        def casco_em(pl, e):
            a_, b_ = tuple(eix_b[pl[0]]), tuple(eix_b[pl[1]])
            return _casco([(_dot(q, a_), _dot(q, b_)) for q in e.vertices])

        def area(poly):
            return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                           for i in range(len(poly)))) / 2.0 if len(poly) >= 3 else 0.0
        pl = max(planos, key=lambda pl_: sum(area(casco_em(pl_, e)) for e in pecas))
        cascos = [c_ for c_ in (casco_em(pl, e) for e in pecas) if len(c_) >= 3]
        if not cascos:
            continue
        if pl == (1, 2):
            # de frente (olhando ao longo da barra): o conjunto endireitado pelas bordas — os eixos da cantoneira L
            # ficam na diagonal e a chapa saía girada 45° (01/10, "torto")
            uniao = _casco([q for c_ in cascos for q in c_])
            melhor = None
            for i_ in range(len(uniao)):
                (xa, ya), (xb, yb) = uniao[i_], uniao[(i_ + 1) % len(uniao)]
                ang = math.atan2(yb - ya, xb - xa)
                co, si = math.cos(-ang), math.sin(-ang)
                rq = [(q[0] * co - q[1] * si, q[0] * si + q[1] * co) for q in uniao]
                ar = (max(q[0] for q in rq) - min(q[0] for q in rq)) * (max(q[1] for q in rq) - min(q[1] for q in rq))
                if melhor is None or ar < melhor[0] - 1e-6:
                    melhor = (ar, co, si)
            if melhor:
                _a, co, si = melhor
                cascos = [[(q[0] * co - q[1] * si, q[0] * si + q[1] * co) for q in c_] for c_ in cascos]
                ax_ = [q[0] for c_ in cascos for q in c_]
                ay_ = [q[1] for c_ in cascos for q in c_]
                if max(ax_) - min(ax_) > max(ay_) - min(ay_) + 1e-6:
                    cascos = [[(-q[1], q[0]) for q in c_] for c_ in cascos]
        if pl == (0, 1) or pl == (0, 2):
            # o eixo da barra deitado, e para fora da ponta: na esquerda, espelhado
            if lado == "esq":
                cascos = [[(-q[0], q[1]) for q in c_] for c_ in cascos]
        allx = [q[0] for c_ in cascos for q in c_]
        ally = [q[1] for c_ in cascos for q in c_]
        w_, h_ = max(allx) - min(allx), max(ally) - min(ally)
        txt = " + ".join(nomes) + ("" if set(conj) == set(todos) else " (%s)" % ", ".join(conj))
        vaga = max(w_, 0.6 * h_nome * len(txt))
        if lado == "esq":
            x = esquerda - vaga
            esquerda = x - VAO_CHAPA_DE_PONTA * esc
        else:
            x = direita
            direita = x + vaga + VAO_CHAPA_DE_PONTA * esc
        x0_, y0_ = min(allx) - (vaga - w_) / 2.0, (min(ally) + max(ally)) / 2.0
        for c_ in cascos:
            p.polilinha([(x + q[0] - x0_, v_eixo + q[1] - y0_) for q in c_], fechada=True, camada="CHAPAS")
        p.texto(x + vaga / 2.0, v_eixo - h_ / 2.0 - 3.0 * esc - h_nome, txt, h_nome, "TEXTO", alinhamento="centro")
        feitos += 1
    return feitos
