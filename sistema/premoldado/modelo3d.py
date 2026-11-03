# -*- coding: utf-8 -*-
"""O galpão pré-moldado no modelo 3D do programa (nucleo3d: mm, Z para cima, X no comprimento,
Y no vão): os pilares como sólidos extrudados (do fundo do cálice ao topo), os cálices como o
colarinho vazado, os consolos, as vigas longitudinais (calha ou travamento) e as vigas de cobertura,
com a peça, a armadura e o peso nos atributos — o editor 3D, o IFC e a lista de peças do programa
leem daí."""
from __future__ import annotations

import math
from typing import List

from nucleo.base import fmt
from nucleo3d.geometria import extrudar
from nucleo3d.modelo import Camada, Documento, Material

from .concreto import cobrimento

from .galpao import SUFIXO, ProjetoGalpaoPM

CAMADA_PILARES = "Pilares pré-moldados"
CAMADA_CALICES = "Cálices"
CAMADA_VIGAS = "Vigas pré-moldadas"
CAMADA_CONSOLOS = "Consolos"
CAMADA_FUNDACOES = "Fundações"


def _retangulo_xy(dx: float, dy: float) -> List[tuple]:
    """o retângulo centrado com dx no X global e dy no Y global para a extrusão vertical (a base local
    da extrusão em Z põe o 1º eixo do contorno no Y global e o 2º no X — nucleo3d.geometria.base_local)"""
    return [(-dy / 2, -dx / 2), (dy / 2, -dx / 2), (dy / 2, dx / 2), (-dy / 2, dx / 2)]


#: A camada das armaduras dos pilares: começa desligada (Ver → Armaduras liga e deixa o concreto translúcido).
CAMADA_ARMADURAS = "Armaduras"


def _armadura_do_pilar(doc: Documento, p: ProjetoGalpaoPM, pil, x: float, y: float, z0: float, z1: float, eixo: str) -> int:
    """as barras longitudinais e os estribos de um pilar calculado, no lugar dele (mm): as barras nas faces como no
    corte A-A do detalhe (detalhe2d._corte: n_h barras nas faces de h, n_b entre elas nas de b), os estribos no
    espaçamento calculado, do pé ao topo, dentro do cobrimento. Devolve quantas peças entraram."""
    d = p.dados
    arm = pil.armadura
    if arm is None:
        return 0
    c = cobrimento(d.caa, "pilar", pre_fabricado=True) * 10.0
    fi_t, s_t = pil.estribos[0], pil.estribos[1] * 10.0
    fi = arm.bitola
    B, Hh = pil.b * 10.0, pil.h * 10.0
    cb = c + fi_t + fi / 2
    atr = {"peca": "P-%s" % SUFIXO[pil.tipo], "eixo": eixo, "pre_moldado": True, "funcao": "armadura",
           "armadura": arm.texto(), "estribos": "ø%s c/ %s" % (fmt(fi_t, 1), fmt(pil.estribos[1], 1))}
    pts = []
    for xh in (cb, Hh - cb):
        for i in range(arm.n_h):
            pts.append((xh, cb + i * (B - 2 * cb) / max(arm.n_h - 1, 1)))
    for yb in (cb, B - cb):
        for i in range(1, arm.n_b + 1):
            pts.append((cb + i * (Hh - 2 * cb) / (arm.n_b + 1), yb))
    n = 0
    circ = [(fi / 2 * math.cos(2 * math.pi * k / 8), fi / 2 * math.sin(2 * math.pi * k / 8)) for k in range(8)]
    za, zb = z0 + c, z1 - c
    for xh, yb in pts:
        barra = extrudar(circ, (0.0, 0.0, 1.0), zb - za, origem=(x - B / 2 + yb, y - Hh / 2 + xh, za), nome="Barra ø%s" % fmt(fi, 1))
        doc.add(_marcar(barra, CAMADA_ARMADURAS, dict(atr, posicao="N1"), material="Armadura"))
        n += 1
    ext = _retangulo_xy(B - 2 * c, Hh - 2 * c)
    inn = _retangulo_xy(B - 2 * c - 2 * fi_t, Hh - 2 * c - 2 * fi_t)
    n_est = int(math.floor((zb - za) / s_t)) + 1
    for k in range(n_est):
        z = za + k * s_t
        est = extrudar((ext, [inn]), (0.0, 0.0, 1.0), fi_t, origem=(x, y, z - fi_t / 2), nome="Estribo ø%s" % fmt(fi_t, 1))
        doc.add(_marcar(est, CAMADA_ARMADURAS, dict(atr, posicao="N2"), material="Armadura"))
        n += 1
    return n


def _barra_reta(a, b, fi: float, nome: str):
    """uma barra de diâmetro fi (mm) de a a b (mm, 3D), octogonal"""
    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    L = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    circ = [(fi / 2 * math.cos(2 * math.pi * k / 8), fi / 2 * math.sin(2 * math.pi * k / 8)) for k in range(8)]
    return extrudar(circ, d, L, origem=a, nome=nome)


def _anel(cx: float, cy: float, z: float, lx: float, ly: float, fi: float, nome: str):
    """um laço retangular (estribo, laço do cálice) de eixo lx × ly (mm) centrado em (cx, cy), na cota z"""
    ext = _retangulo_xy(lx + fi, ly + fi)
    inn = _retangulo_xy(lx - fi, ly - fi)
    return extrudar((ext, [inn]), (0.0, 0.0, 1.0), fi, origem=(cx, cy, z - fi / 2), nome=nome)


def _armadura_do_calice(doc: Documento, r, x: float, y: float, Lc: float, peca: str, eixo: str, barras: dict = None) -> int:
    """as armaduras do colarinho (NBR 9062, 7.7.3.5, como o cálculo adota): os laços horizontais principais na faixa
    de cima (0,2·Lemb), as horizontais secundárias no resto da altura e as verticais nos quatro cantos, no meio da
    parede; das duas direções, as barras maiores"""
    dd = r.dados                                                    # a geometria, sempre a da direção x (externo: X, Y)
    barras = barras or dd.get("barras") or {}
    if not barras:
        return 0
    c = 30.0                                                        # mm: o cobrimento do colarinho (a conferir)
    ext_b, ext_h = dd["externo"][0] * 10, dd["externo"][1] * 10
    ep = dd["parede"] * 10
    lx, ly = ext_b - ep, ext_h - ep                                 # o eixo das paredes
    atr = {"peca": peca, "eixo": eixo, "pre_moldado": True, "funcao": "armadura"}
    n = 0
    n_h, fi_h = barras["horizontal_principal"]
    n_hs, fi_hs = barras["horizontal_secundaria"]
    n_v, fi_v = barras["vertical"]
    faixa = 0.2 * dd["Lemb_adotado"] * 10
    topo, pe = -c - fi_h / 2, -Lc + c
    for k in range(n_h):
        z = topo - k * (faixa - c) / max(n_h - 1, 1)
        doc.add(_marcar(_anel(x, y, z, lx, ly, fi_h, "Laço do cálice ø%s" % fmt(fi_h, 1)), CAMADA_ARMADURAS,
                        dict(atr, posicao="horizontal principal"), material="Armadura"))
        n += 1
    z_ini = topo - faixa
    for k in range(n_hs):
        z = z_ini - (k + 1) * (z_ini - pe) / (n_hs + 1)
        doc.add(_marcar(_anel(x, y, z, lx, ly, fi_hs, "Laço do cálice ø%s" % fmt(fi_hs, 1)), CAMADA_ARMADURAS,
                        dict(atr, posicao="horizontal secundária"), material="Armadura"))
        n += 1
    por_canto = max(n_v // 4, 1)
    passo = max(2 * fi_v, 50.0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = x + sx * lx / 2, y + sy * ly / 2
            for k in range(por_canto):
                # a primeira no canto, as outras ao longo das duas paredes, alternando
                dx = -sx * passo * ((k + 1) // 2) if k % 2 else 0.0
                dy = -sy * passo * (k // 2) if k % 2 == 0 and k else 0.0
                doc.add(_marcar(_barra_reta((cx + dx, cy + dy, pe), (cx + dx, cy + dy, -c), fi_v, "Barra do cálice ø%s" % fmt(fi_v, 1)),
                                CAMADA_ARMADURAS, dict(atr, posicao="vertical"), material="Armadura"))
                n += 1
    return n


def _armadura_da_fundacao(doc: Documento, dd: dict, x: float, y: float, z_fundo: float, peca: str, eixo: str) -> int:
    """a malha da sapata (as duas direções no fundo, dentro do cobrimento) ou os tirantes do bloco (as faixas de
    barras sobre as estacas, acima da cabeça delas)"""
    barras = dd.get("barras") or {}
    if not barras:
        return 0
    c = float(dd.get("cobrimento") or 3.0) * 10
    ah, ab = dd["ah"] * 10, dd["ab"] * 10
    atr = {"peca": peca, "eixo": eixo, "pre_moldado": True, "funcao": "armadura"}
    n = 0
    if dd.get("tipo") == "sapata":
        fh, eh, nh = barras["h"]
        fb, eb, nb = barras["b"]
        z1 = z_fundo + c + fh / 2
        z2 = z1 + fh / 2 + fb / 2
        for k in range(nh):                                     # correm no vão (Y), espalhadas em X
            xx = x - ab / 2 + c + k * (ab - 2 * c) / max(nh - 1, 1)
            doc.add(_marcar(_barra_reta((xx, y - ah / 2 + c, z1), (xx, y + ah / 2 - c, z1), fh, "Barra da sapata ø%s" % fmt(fh, 1)),
                            CAMADA_ARMADURAS, dict(atr, posicao="malha do vão"), material="Armadura"))
            n += 1
        for k in range(nb):                                     # correm no comprimento (X), espalhadas em Y
            yy = y - ah / 2 + c + k * (ah - 2 * c) / max(nb - 1, 1)
            doc.add(_marcar(_barra_reta((x - ab / 2 + c, yy, z2), (x + ab / 2 - c, yy, z2), fb, "Barra da sapata ø%s" % fmt(fb, 1)),
                            CAMADA_ARMADURAS, dict(atr, posicao="malha do comprimento"), material="Armadura"))
            n += 1
        return n
    # o bloco: faixas sobre as estacas (largura 1,2·ø da estaca), acima da cabeça (10 cm dentro do bloco)
    est = dd.get("estacas") or []
    fi_e = float(dd.get("estaca_diametro") or 30.0) * 10
    z = z_fundo + 100.0 + 20.0
    for chave, ao_longo_y in (("h", True), ("b", False)):
        if chave not in barras:
            continue
        nb, fb = barras[chave]
        zz = z + fb / 2 + (0.0 if chave == "h" else fb)
        linhas = sorted({round(pb if ao_longo_y else ph, 1) for ph, pb in est})
        s = min(1.2 * fi_e / max(nb, 1), 60.0)
        for lin in linhas:
            for k in range(nb):
                off = lin * 10 + (k - (nb - 1) / 2) * s
                if ao_longo_y:
                    a, b = (x + off, y - ah / 2 + c, zz), (x + off, y + ah / 2 - c, zz)
                else:
                    a, b = (x - ab / 2 + c, y + off, zz), (x + ab / 2 - c, y + off, zz)
                doc.add(_marcar(_barra_reta(a, b, fb, "Tirante do bloco ø%s" % fmt(fb, 1)), CAMADA_ARMADURAS,
                                dict(atr, posicao="tirante do %s" % ("vão" if ao_longo_y else "comprimento")), material="Armadura"))
                n += 1
    return n


def _ao_longo_de_x(contorno_yz: List[tuple], x0: float, comprimento: float, nome: str):
    """o contorno no plano YZ (coordenadas globais, mm) extrudado de x0 no sentido +X (a base local da
    extrusão em X põe o 1º eixo do contorno no Y global e o 2º no Z)"""
    return extrudar(contorno_yz, (1.0, 0.0, 0.0), comprimento, origem=(x0, 0.0, 0.0), nome=nome)


def _caixa(x0, x1, y0, y1, z0, z1, nome):
    return _ao_longo_de_x([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], x0, x1 - x0, nome)


def _marcar(sol, camada, atributos, material: str = "Concreto"):
    sol.camada = camada
    sol.material = material
    sol.atributos = atributos
    return sol


def documento(p: ProjetoGalpaoPM) -> Documento:
    d = p.dados
    doc = Documento(nome=d.nome)
    doc.camadas[CAMADA_PILARES] = Camada(nome=CAMADA_PILARES, cor="#9aa3ad")
    doc.camadas[CAMADA_CALICES] = Camada(nome=CAMADA_CALICES, cor="#c9b99a")
    # as armaduras dos pilares: desligadas ao abrir (Ver → Armaduras); o material próprio, em laranja de vergalhão
    doc.camadas[CAMADA_ARMADURAS] = Camada(nome=CAMADA_ARMADURAS, cor="#d35400", visivel=False)
    doc.materiais["Armadura"] = Material(nome="Armadura", cor="#d35400", metalico=0.55, rugosidade=0.5)
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v * 1000.0)
    ys = [0.0, d.vao * 1000.0]
    por_tipo = {q.tipo: q for q in p.pilares}
    fund = {r.dados.get("tipo_pilar"): r for r in p.fundacoes if "ah" in r.dados}
    if fund:
        doc.camadas[CAMADA_FUNDACOES] = Camada(nome=CAMADA_FUNDACOES, cor="#a89f91")
    calices = {}
    for r in p.calices:
        if r.dados.get("direcao") == "x":
            calices[r.dados.get("tipo_pilar") or next(t for t in ("canto", "oitão", "intermediário") if t in r.elemento)] = r
    H = d.altura_pilar * 1000.0
    tipo_de = lambda i, j=0: ("canto" if i in (0, len(xs) - 1) else "intermediário") + (" B" if j == 1 and d.filas_diferentes else "")
    posicoes = [(i, x, j, y, tipo_de(i, j)) for i, x in enumerate(xs) for j, y in enumerate(ys)]
    posicoes += [(int(e) - 1, xs[int(e) - 1], None, yy * 1000.0, "oitão") for e, yy in (d.pilares_oitao or [])
                 if 1 <= int(e) <= len(xs) and "oitão" in por_tipo]
    for i, x, j, y, tipo in posicoes:
        pil = por_tipo.get(tipo)
        if pil is None:
            continue
        Hp = (d.altura_oitao(y / 1000.0) if tipo == "oitão" else d.altura_tipo(tipo)) * 1000.0
        Lemb = (pil.comprimento_total - d.altura_tipo(tipo)) * 1000.0
        rot = "AB"[j] if j is not None else "oitão %s" % fmt(y / 1000.0, 2)
        # o pilar: b na direção X (comprimento), h na direção Y (vão)
        sol = extrudar(_retangulo_xy(pil.b * 10, pil.h * 10), (0.0, 0.0, 1.0), Hp + Lemb, origem=(x, y, -Lemb),
                       nome="Pilar %s %s × %s" % (tipo, int(pil.b), int(pil.h)))
        vol = pil.b * pil.h / 1e4 * pil.comprimento_total
        doc.add(_marcar(sol, CAMADA_PILARES, {
            "peca": "P-%s" % SUFIXO[tipo], "tipo_ifc": "IfcColumn",
            "armadura": pil.armadura.texto(), "estribos": "ø%s c/ %s" % pil.estribos,
            "volume_m3": round(vol, 3), "peso_peca_kg": round(vol * 2500.0, 0), "topo_mm": round(Hp),
            "eixo": "%d/%s" % (i + 1, rot), "pre_moldado": True, **_da_planta(d, "%d/%s" % (i + 1, rot))}))
        _armadura_do_pilar(doc, p, pil, x, y, -Lemb, Hp, "%d/%s" % (i + 1, rot))
        r = calices.get(tipo)
        if r is not None:
            ext_b, ext_h = r.dados["externo"]
            int_b, int_h = r.dados["interno"]
            Lc = r.dados["Lemb_adotado"] * 10.0
            fundo = r.dados["fundo"] * 10.0
            # o colarinho: da base do bloco (abaixo do fundo do pilar) à boca do cálice (z = 0), com o
            # vazio do pilar e do enchimento
            cal = extrudar((_retangulo_xy(ext_b * 10, ext_h * 10), [_retangulo_xy(int_b * 10, int_h * 10)]), (0.0, 0.0, 1.0), Lc,
                           origem=(x, y, -Lc), nome="Cálice %s" % tipo)
            atr = {"peca": "CL-%s" % SUFIXO[tipo], "tipo_ifc": "IfcFooting",
                   "eixo": "%d/%s" % (i + 1, rot), "pre_moldado": True}
            doc.add(_marcar(cal, CAMADA_CALICES, atr))
            maior = _barras_do_calice(p, tipo)
            _armadura_do_calice(doc, r, x, y, Lc, atr["peca"], atr["eixo"], maior.dados["barras"] if maior else None)
            f = fund.get(tipo)
            if f is not None:
                _fundacao(doc, f, x, y, Lc, i, rot)
                continue
            base = extrudar(_retangulo_xy(ext_b * 10, ext_h * 10), (0.0, 0.0, 1.0), fundo, origem=(x, y, -Lc - fundo),
                            nome="Fundo do cálice %s" % tipo)
            doc.add(_marcar(base, CAMADA_CALICES, dict(atr)))
    _vigas(doc, p, xs, ys, H, por_tipo, tipo_de)
    _consolos_ponte(doc, p, xs, ys, por_tipo, tipo_de)
    doc.metadados["premoldado"] = {"eixos_x_mm": xs, "eixos_y_mm": ys, "altura_mm": H}
    return doc


def _da_planta(d, eixo: str) -> dict:
    """o id e a marca do elemento da planta de lançamento deste pilar (R5: a ida e volta)"""
    o = (getattr(d, "origem_planta", None) or {}).get(eixo)
    return {"origem_2d": o["id"], "marca_planta": o.get("marca", "")} if o else {}


def _barras_do_calice(p: ProjetoGalpaoPM, tipo: str):
    """o cálice do tipo com as barras maiores das duas direções (x e y), para o desenho das armaduras"""
    rs = [r for r in p.calices if (r.dados.get("tipo_pilar") or "") == tipo and r.dados.get("barras")]
    if not rs:
        return None
    area = lambda r: sum(n * fi * fi for n, fi in r.dados["barras"].values())      # noqa: E731
    return max(rs, key=area)


def _cilindro(raio: float, comprimento: float, origem, nome: str, lados: int = 16):
    pts = [(raio * math.cos(2 * math.pi * k / lados), raio * math.sin(2 * math.pi * k / lados)) for k in range(lados)]
    return extrudar(pts, (0.0, 0.0, 1.0), comprimento, origem=origem, nome=nome)


def _fundacao(doc: Documento, f, x: float, y: float, Lc: float, i: int, rot: str) -> None:
    """a sapata ou o bloco sob o colarinho (ah no vão = Y, ab no comprimento = X) e as estacas (1ª parte, 3 m:
    o comprimento vem da sondagem)"""
    dd = f.dados
    ah, ab, hf = dd["ah"] * 10, dd["ab"] * 10, dd["hf"] * 10
    suf = SUFIXO[dd["tipo_pilar"]]
    eixo = "%d/%s" % (i + 1, rot)
    sol = extrudar(_retangulo_xy(ab, ah), (0.0, 0.0, 1.0), hf, origem=(x, y, -Lc - hf),
                   nome="%s %s" % ("Sapata" if dd["tipo"] == "sapata" else "Bloco", dd["tipo_pilar"]))
    doc.add(_marcar(sol, CAMADA_FUNDACOES, {"peca": "%s-%s" % ("SP" if dd["tipo"] == "sapata" else "BL", suf), "tipo_ifc": "IfcFooting",
                                            "armadura": dd.get("armadura", ""), "volume_m3": round(dd["volume"], 3), "eixo": eixo,
                                            "moldado_no_local": True}))
    _armadura_da_fundacao(doc, dd, x, y, -Lc - hf, "%s-%s" % ("SP" if dd["tipo"] == "sapata" else "BL", suf), eixo)
    if dd["tipo"] == "estacas":
        for (ph, pb) in dd["estacas"]:
            est = _cilindro(dd["estaca_diametro"] * 5, 3000.0, (x + pb * 10, y + ph * 10, -Lc - hf - 3000.0 + 100.0),
                            "Estaca ø%d" % int(dd["estaca_diametro"]))
            doc.add(_marcar(est, CAMADA_FUNDACOES, {"peca": "EST-%s" % suf, "tipo_ifc": "IfcPile", "eixo": eixo,
                                                    "comprimento": "pela sondagem (desenhados 3 m)"}))


def _tercas(doc: Documento, p: ProjetoGalpaoPM, v, xs, ys, H, atr) -> None:
    """as terças T sobre as vigas de cobertura, nas linhas da água (de eixo a eixo dos pórticos)"""
    d = p.dados
    cob = next((w for w in p.vigas if w.funcao == "viga de cobertura"), None)
    if cob is None:
        return
    th = math.radians(d.inclinacao_graus)
    h0 = cob.secao_apoio.h * 10
    L = ys[-1] - ys[0]
    linhas = p.cargas_vigas.get("tercas_linhas", 0)
    if linhas < 2:
        return
    contorno = [(px * 10, py * 10) for px, py in v.secao.contorno()]
    passo = (L / 2) / ((linhas - 1) / 2)
    for k in range(linhas):
        y = ys[0] + k * passo
        z = (d.altura_oitao((y - ys[0]) / 1000.0) * 1000.0 + h0) if d.uma_agua else H + h0 + min(y - ys[0], ys[-1] - y) * math.tan(th)
        for i in range(len(xs) - 1):
            sol = _ao_longo_de_x([(y + cy, z + cz) for cy, cz in contorno], xs[i] + 10.0, xs[i + 1] - xs[i] - 20.0, "Terça %s" % v.marca)
            doc.add(_marcar(sol, CAMADA_VIGAS, dict(atr, peca=v.marca, vao="%d-%d" % (i + 1, i + 2))))


def _consolos_ponte(doc: Documento, p: ProjetoGalpaoPM, xs, ys, por_tipo, tipo_de) -> None:
    """o consolo da ponte rolante na face de dentro de cada pilar (na direção do vão), com o topo na
    altura do apoio da viga de rolamento"""
    d = p.dados
    if not d.ponte_rolante:
        return
    doc.camadas.setdefault(CAMADA_CONSOLOS, Camada(nome=CAMADA_CONSOLOS, cor="#9aa3ad"))
    zt = d.pr_altura * 1000.0
    hc = d.consolo_pr_altura * 10
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            pil = por_tipo.get(tipo_de(i, j))
            if pil is None:
                continue
            comp = (d.pr_excentricidade - pil.h / 2 + 20.0) * 10             # 20 cm além do eixo do trilho
            dentro = 1 if j == 0 else -1
            ya = y + dentro * pil.h * 5
            yb = ya + dentro * comp
            sol = _caixa(x - pil.b * 5, x + pil.b * 5, min(ya, yb), max(ya, yb), zt - hc, zt, "Consolo da ponte rolante")
            doc.add(_marcar(sol, CAMADA_CONSOLOS, {"peca": "P-%s" % SUFIXO[tipo_de(i, j)], "tipo_ifc": "IfcMember",
                                                    "pre_moldado": True, "eixo": "%d/%s" % (i + 1, "AB"[j]), "funcao": "consolo da ponte rolante"}))


def eixos(p: ProjetoGalpaoPM) -> dict:
    """os eixos do galpão no formato do projeto (nucleo3d.eixos.de_dict): os pórticos numerados ao
    longo de X e as duas filas de pilares A e B no vão — o 3D e as plantas mostram estes, em vez dos
    identificados pela geometria (feitos para as treliças metálicas)"""
    d = p.dados
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v * 1000.0)
    return {"eixo_g": [1.0, 0.0], "numeros": [{"nome": str(i + 1), "pos": round(x, 1)} for i, x in enumerate(xs)],
            "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": round(d.vao * 1000.0, 1)}], "z_base": 0.0,
            "origem": "premoldado"}


def _vigas(doc: Documento, p: ProjetoGalpaoPM, xs, ys, H, por_tipo, tipo_de) -> None:
    d = p.dados
    if not p.vigas:
        return
    doc.camadas[CAMADA_VIGAS] = Camada(nome=CAMADA_VIGAS, cor="#b8c4d6")
    marcas = {l["comprimento_m"]: l["marca"] for l in p.lista if l["marca"].startswith(("VC", "VT"))}
    for v in p.vigas:
        atr = {"tipo_ifc": "IfcBeam", "armadura": v.texto_armadura(), "funcao": v.funcao, "pre_moldado": True}
        if v.funcao == "terça":
            _tercas(doc, p, v, xs, ys, H, atr)
            continue
        if v.funcao == "viga de cobertura":
            s0, sm = v.secao_apoio, v.secao
            bf, hf, bw = sm.parametros["bf"] * 10, sm.parametros["hf"] * 10, sm.parametros["bw"] * 10
            h_pil = max(q.h for q in p.pilares) * 10 if p.pilares else 0.0
            y0, y1, ym = ys[0] - h_pil / 2, ys[-1] + h_pil / 2, (ys[0] + ys[-1]) / 2
            h0, hm = s0.h * 10, sm.h * 10
            HA, HB = d.altura_pilar * 1000.0, d.altura_b * 1000.0
            for i, x in enumerate(xs):
                nome = "Viga de cobertura %s" % v.marca
                a = dict(atr, peca=v.marca, eixo=str(i + 1), volume_m3=round(v.volume, 3), peso_peca_kg=round(v.peso_kN * 100.0, 0))
                if d.uma_agua:
                    # a viga reta de A a B, com a altura constante, sentada nos dois topos
                    pares = [((y0, HA), (y1, HB))]
                    mesa_inf = _ao_longo_de_x([(y0, HA), (y1, HB), (y1, HB + hf), (y0, HA + hf)], x - bf / 2, bf, nome + " — mesa de baixo")
                    alma = _ao_longo_de_x([(y0, HA + hf), (y1, HB + hf), (y1, HB + h0 - hf), (y0, HA + h0 - hf)], x - bw / 2, bw, nome + " — alma")
                    mesas = [((y0, HA + h0), (y1, HB + h0))]
                else:
                    mesa_inf = _ao_longo_de_x([(y0, H), (y1, H), (y1, H + hf), (y0, H + hf)], x - bf / 2, bf, nome + " — mesa de baixo")
                    alma = _ao_longo_de_x([(y0, H + hf), (y1, H + hf), (y1, H + h0 - hf), (ym, H + hm - hf), (y0, H + h0 - hf)],
                                          x - bw / 2, bw, nome + " — alma")
                    mesas = [((y0, H + h0), (ym, H + hm)), ((ym, H + hm), (y1, H + h0))]
                doc.add(_marcar(mesa_inf, CAMADA_VIGAS, a))
                doc.add(_marcar(alma, CAMADA_VIGAS, dict(a)))
                for (ya, za), (yb, zb) in mesas:
                    mesa = _ao_longo_de_x([(ya, za - hf), (yb, zb - hf), (yb, zb), (ya, za)], x - bf / 2, bf, nome + " — mesa de cima")
                    doc.add(_marcar(mesa, CAMADA_VIGAS, dict(a)))
            continue
        # longitudinais: nos consolos, com o topo no topo do pilar, entre as faces dos pilares
        doc.camadas.setdefault(CAMADA_CONSOLOS, Camada(nome=CAMADA_CONSOLOS, cor="#9aa3ad"))
        hv = v.secao.h * 10
        contorno = [(px * 10, py * 10) for px, py in v.secao.contorno()]
        z_apoio_fila = [d.altura_pilar * 1000.0 - hv - 10.0, d.altura_b * 1000.0 - hv - 10.0]     # 10 mm de elastômero
        for k in range(len(xs) - 1):
            pa, pb = por_tipo.get(tipo_de(k)), por_tipo.get(tipo_de(k + 1))
            if pa is None or pb is None:
                continue
            x0 = xs[k] + pa.b * 5 + 10.0
            x1 = xs[k + 1] - pb.b * 5 - 10.0
            comp = math.floor((d.vaos_longitudinais[k] - max(q.b for q in p.pilares) / 100.0 - 0.02) * 100.0 + 1e-6) / 100.0
            for j, y in enumerate(ys):
                z_apoio = z_apoio_fila[j]
                sol = _ao_longo_de_x([(y + cy, z_apoio + 10.0 + cz) for cy, cz in contorno], x0, x1 - x0, "%s %s" % (v.funcao, v.marca))
                vol = v.secao.A / 1e4 * (x1 - x0) / 1000.0
                doc.add(_marcar(sol, CAMADA_VIGAS, dict(atr, peca=marcas.get(comp, v.marca), volume_m3=round(vol, 3),
                                                         peso_peca_kg=round(vol * 2500.0, 0), vao="%d-%d" % (k + 1, k + 2))))
        # os consolos: nas faces dos pilares voltadas para os vãos, 2a de comprimento
        comp_c = 2 * d.consolo_a * 10
        hc = d.consolo_altura * 10
        for i, x in enumerate(xs):
            lados = ([1] if i < len(xs) - 1 else []) + ([-1] if i > 0 else [])
            for j, y in enumerate(ys):
                pil = por_tipo.get(tipo_de(i, j))
                if pil is None:
                    continue
                z_apoio = z_apoio_fila[j]
                for lado in lados:
                    xa = x + lado * pil.b * 5
                    xb = xa + lado * comp_c
                    sol = _caixa(min(xa, xb), max(xa, xb), y - pil.h * 5, y + pil.h * 5, z_apoio - hc, z_apoio, "Consolo")
                    doc.add(_marcar(sol, CAMADA_CONSOLOS, {"peca": "P-%s" % SUFIXO[tipo_de(i, j)],
                                                            "tipo_ifc": "IfcMember", "pre_moldado": True, "eixo": str(i + 1)}))
