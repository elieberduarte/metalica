# -*- coding: utf-8 -*-
"""As ferramentas de modelagem estrutural do editor 3D, por seleção + diálogo, como as do Revit e do Tekla (pedido do
usuário, 14/10/2026: "intuitiva de usar e modelar como o SketchUp e versátil e moderna cheia de informações como um
Revit"; e o foco nas ferramentas de modelagem). As ferramentas de mouse (desenhar, mover, empurrar) moram em
web/editor3d/ferramentas; aqui ficam as que montam a estrutura em poucos cliques:

* **terças por espaçamento** — escolhidas as tesouras/vigas da cobertura, as terças igualmente espaçadas (nunca acima
  do espaçamento pedido) entre o beiral e a cumeeira, sentadas no topo dos apoios, com o eixo forte perpendicular à
  água (a convenção do gerador do galpão: uma terça por vão, ou contínua);
* **treliça entre banzos** — montantes e diagonais (Pratt, Howe, Warren) entre os dois banzos escolhidos, nos nós
  igualmente espaçados, com o encaixe das almas nos banzos;
* **contraventamento em X** — as duas diagonais entre duas barras paralelas (pilares de uma parede, banzos de duas
  tesouras), num ou em vários painéis;
* **pilares nos eixos** — um pilar em cada cruzamento de eixos da obra escolhido, da base ao nível do topo;
* **viga entre pilares** — a viga no nível pedido ligando os pilares escolhidos, na ordem em que estão em planta;
* **longarinas de fechamento** — as fiadas na face de fora dos pilares de uma parede (alma na horizontal, boca para baixo)
  e, no oitão, a terça inclinada pelo topo dos pilares;
* **correntes entre terças** — no meio (ou nos terços) de cada vão, de centro a centro das terças;
* **mão-francesa** — da alma da terça à mesa de baixo do apoio, a 45°, nos dois lados de cada apoio.

Nada altera o documento recebido: cada função devolve {"novas": [entidades (dict)], "alterar": {...}, "avisos"} para o
editor aplicar com desfazer.
"""
import math
from typing import Dict, List, Optional, Sequence

from nucleo.base import ErroDeDados


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cruz(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    if n < 1e-9:
        raise ErroDeDados("direção degenerada")
    return (a[0] / n, a[1] / n, a[2] / n)


def _r(p, casas=2):
    return tuple(round(float(x), casas) for x in p)


def _barras(doc, ids):
    from nucleo3d.modelo import Barra
    return [doc.entidades[i] for i in ids if isinstance(doc.entidades.get(i), Barra)]


def _perfil(nome):
    from nucleo3d.geometria import resolver_perfil
    try:
        return resolver_perfil(nome)
    except Exception as exc:                              # noqa: BLE001
        raise ErroDeDados("perfil %s fora do catálogo: %s" % (nome, exc))


def _rotacao_para_v(direcao, v_desejado) -> float:
    """a rotação da barra de direção `direcao` cujo eixo forte (v da seção, a altura) aponta para `v_desejado`"""
    from nucleo3d.geometria import base_local
    u0, v0, _ = base_local(direcao, 0.0)
    # v(rot) = −u0·sen + v0·cos
    return round(math.degrees(math.atan2(-_dot(v_desejado, u0), _dot(v_desejado, v0))) % 360.0, 3)


def _u_da_barra(direcao, rot):
    from nucleo3d.geometria import base_local
    return base_local(direcao, rot)[0]


def _topo(barra, n):
    """o maior valor da malha da barra ao longo de n (a face de cima no sentido n)"""
    from nucleo3d.geometria import malha_barra
    vs, _ = malha_barra(barra)
    return max(_dot(q, n) for q in vs)


# ------------------------------------------------------------------ terças por espaçamento

def tercas(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """As terças sobre as tesouras/vigas escolhidas (pelo menos duas, lado a lado em planta)."""
    from nucleo3d.modelo import Barra
    from nucleo3d.geometria import base_local
    p = dict(p or {})
    apoios = _barras(doc, ids)
    if len(apoios) < 2:
        raise ErroDeDados("selecione pelo menos duas tesouras ou vigas da cobertura (os apoios das terças)")
    perfil = str(p.get("perfil") or "Ue 150×60×20×2,25")
    pt = _perfil(perfil)
    esp = float(p.get("espacamento") or 1500.0)
    d_beiral = float(p.get("beiral") or 200.0)
    d_cumeeira = float(p.get("cumeeira") or 250.0)
    balanco = float(p.get("balanco") or 0.0)
    folga = float(p.get("folga") or 0.0)
    continua = str(p.get("continua") or "nao") == "sim"
    boca = str(p.get("boca") or "cumeeira")
    # a direção da água: de cada apoio, da ponta baixa para a alta (a do primeiro manda no sentido dos horizontais)
    t0 = None
    infos = []
    for a in apoios:
        baixa, alta = (a.inicio, a.fim) if a.inicio[2] <= a.fim[2] else (a.fim, a.inicio)
        t = _norm(_sub(alta, baixa))
        if t0 is None:
            t0 = t
        elif _dot(t, t0) < 0 and abs(alta[2] - baixa[2]) < 1.0:
            baixa, alta, t = alta, baixa, _mul(t, -1.0)
        if abs(t[2]) > 0.7:
            raise ErroDeDados("o apoio %s está em pé: as terças vão sobre tesouras ou vigas" % (a.nome or a.id))
        infos.append((a, baixa, alta, t))
    perp = _norm(_cruz((0.0, 0.0, 1.0), (t0[0], t0[1], 0.0)))
    infos.sort(key=lambda x: _dot(x[1], perp))
    if any(abs(_dot((x[3][0], x[3][1], 0.0), perp)) > 0.2 for x in infos):
        raise ErroDeDados("os apoios não estão paralelos em planta: selecione as tesouras de uma água")
    # a normal da água (para cima)
    nr = _norm(_cruz(perp, t0))
    if nr[2] < 0:
        nr = _mul(nr, -1.0)
    L = min(math.dist(b, a_) for _a, b, a_, _t in infos)
    util = L - d_beiral - d_cumeeira
    if util <= 0:
        raise ErroDeDados("o beiral e a cumeeira somam mais que o comprimento dos apoios")
    n = max(1, int(math.ceil(util / esp - 1e-6)))
    passo = util / n
    ss = [d_beiral + k * passo for k in range(n + 1)]
    novas = []
    # o eixo forte perpendicular à água; a boca do U para a cumeeira (ou o beiral)
    wter = perp
    rot = _rotacao_para_v(wter, nr)
    u = _u_da_barra(wter, rot)
    if (boca == "cumeeira" and _dot(u, t0) < 0) or (boca == "beiral" and _dot(u, t0) > 0):
        rot = round((rot + 180.0) % 360.0, 3)
    d_t = float(pt.d or 150.0)
    for k, s in enumerate(ss):
        centros = []
        for a, baixa, _alta, t in infos:
            P = _add(baixa, _mul(t, s))
            # o topo do apoio na normal da água (a face de cima, pela malha) e o centro da terça em cima dele
            nb = nr
            topo = _topo(a, nb)
            C = _add(P, _mul(nb, topo - _dot(P, nb) + d_t / 2.0 + folga))
            centros.append(C)
        trechos = [(centros[0], centros[-1])] if continua else list(zip(centros[:-1], centros[1:]))
        for i, (c0, c1) in enumerate(trechos):
            dirt = _norm(_sub(c1, c0))
            if i == 0 and balanco:
                c0 = _sub(c0, _mul(dirt, balanco))
            if i == len(trechos) - 1 and balanco:
                c1 = _add(c1, _mul(dirt, balanco))
            b = Barra(nome="Terça", inicio=_r(c0), fim=_r(c1), perfil=perfil, rotacao=_rotacao_para_v(dirt, nr) if not continua else rot,
                      papel="terça", camada="Terças", material="Aço",
                      atributos={"tipo_ifc": "IfcMember", "linha_terca": k + 1, "vao": i + 1})
            # a mesma boca em todas (o giro achado na direção comum)
            ub = _u_da_barra(dirt, b.rotacao)
            if (boca == "cumeeira" and _dot(ub, t0) < 0) or (boca == "beiral" and _dot(ub, t0) > 0):
                b.rotacao = round((b.rotacao + 180.0) % 360.0, 3)
            novas.append(b)
    return {"novas": [b.dict() for b in novas],
            "resumo": {"linhas": len(ss), "passo": round(passo, 1), "pecas": len(novas)},
            "avisos": [] if passo <= esp + 1e-6 else ["espaçamento acima do pedido"]}


# ------------------------------------------------------------------ treliça entre banzos

def trelica(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """Montantes e diagonais entre os dois banzos escolhidos, nos nós igualmente espaçados no trecho comum."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    bs = _barras(doc, ids)
    if len(bs) != 2:
        raise ErroDeDados("selecione os dois banzos da treliça (o de cima e o de baixo)")
    sup, inf = sorted(bs, key=lambda b: -(b.inicio[2] + b.fim[2]))
    tipo = str(p.get("tipo") or "pratt")
    paineis = int(p.get("paineis") or 0)
    passo_max = float(p.get("passo") or 1500.0)
    perfil_m = str(p.get("perfil_montante") or sup.perfil)
    perfil_d = str(p.get("perfil_diagonal") or perfil_m)
    # o trecho comum, pela direção do banzo de baixo
    w = _norm(_sub(inf.fim, inf.inicio))
    def s_de(q):
        return _dot(_sub(q, inf.inicio), w)
    s0 = max(min(s_de(inf.inicio), s_de(inf.fim)), min(s_de(sup.inicio), s_de(sup.fim)))
    s1 = min(max(s_de(inf.inicio), s_de(inf.fim)), max(s_de(sup.inicio), s_de(sup.fim)))
    if s1 - s0 < 300.0:
        raise ErroDeDados("os dois banzos quase não correm juntos")
    n = paineis or max(1, int(math.ceil((s1 - s0) / passo_max - 1e-6)))
    if tipo != "warren" and n % 2:
        n += 1                                            # Pratt e Howe: número par de painéis (simetria no meio)

    def ponto_no(b, s):
        """o ponto do eixo da barra `b` na estação s (medida ao longo do banzo de baixo)"""
        d = _sub(b.fim, b.inicio)
        L2 = _dot(d, d)
        # a reta perpendicular a w pela estação s: a interseção com o eixo da barra
        den = _dot(d, w)
        if abs(den) < 1e-9:
            raise ErroDeDados("o banzo está em pé")
        tt = (s - _dot(_sub(b.inicio, inf.inicio), w)) / den
        return _add(b.inicio, _mul(d, tt))
    baixo = [ponto_no(inf, s0 + (s1 - s0) * k / n) for k in range(n + 1)]
    cima = [ponto_no(sup, s0 + (s1 - s0) * k / n) for k in range(n + 1)]
    membros = []                                          # (p0, p1, papel)
    if tipo == "warren":
        for k in range(n):
            if k % 2 == 0:
                membros.append((baixo[k], cima[k + 1], "diagonal"))
                membros.append((cima[k + 1], baixo[k + 2] if k + 2 <= n else baixo[n], "diagonal"))
        membros = [(a, b, r) for a, b, r in membros if math.dist(a, b) > 1.0]
        if str(p.get("montantes") or "nao") == "sim":
            membros += [(baixo[k], cima[k], "montante") for k in range(n + 1)]
    else:
        membros += [(baixo[k], cima[k], "montante") for k in range(n + 1)]
        meio = n // 2
        for k in range(n):
            esquerda = k < meio
            # Pratt: as diagonais descem para o meio (tracionadas); Howe: sobem para o meio
            if (tipo == "pratt") == esquerda:
                membros.append((cima[k], baixo[k + 1], "diagonal"))
            else:
                membros.append((baixo[k], cima[k + 1], "diagonal"))
    # tira o montante de comprimento zero (banzos que se encontram na ponta)
    membros = [(a, b, r) for a, b, r in membros if math.dist(a, b) > 1.0]
    novas = []
    # o bloco da treliça: o dos banzos, quando já têm (as almas encaixam nas faces deles), ou o nome pedido
    peca = next((str((b.atributos or {}).get("origem", {}).get("peca")) for b in (sup, inf)
                 if ((b.atributos or {}).get("origem") or {}).get("peca")), None) or str(p.get("nome") or "TRELIÇA")
    for a, b, papel in membros:
        novas.append(Barra(nome=papel.capitalize(), inicio=_r(a), fim=_r(b), perfil=perfil_m if papel == "montante" else perfil_d,
                           papel=papel, camada="Treliças", material="Aço",
                           atributos={"tipo_ifc": "IfcMember", "origem": {"peca": peca}}))
    # os banzos entram na mesma treliça (o bloco e o encaixe das almas nas faces deles)
    alterar = {}
    avisos_bloco = []
    for b, papel in ((sup, "banzo"), (inf, "banzo")):
        at = dict(b.atributos or {})
        orig = dict(at.get("origem") or {})
        if not orig.get("peca"):
            orig["peca"] = peca
            at["origem"] = orig
            alterar[b.id] = {"atributos": at, "papel": papel}
        elif orig.get("peca") != peca:
            avisos_bloco.append("os dois banzos estão em blocos diferentes (%s): as almas foram no de %s" % (orig["peca"], peca))
        elif b.papel != "banzo":
            alterar[b.id] = {"papel": "banzo"}
    avisos = avisos_bloco
    # o encaixe das almas no banzo (a meia-esquadria e o recorte na face), como na montagem pela planta
    try:
        from nucleo3d.modelo import Documento
        from nucleo3d import alma_na_face
        tmp = Documento.de_dict(doc.dict())
        for bid, campos in alterar.items():
            for k_, v_ in campos.items():
                setattr(tmp.entidades[bid], k_, v_)
        for b in novas:
            tmp.add(b)
        alma_na_face.encaixar(tmp.entidades.values())
        novas = [tmp.entidades[b.id] for b in novas]
    except Exception as exc:                              # noqa: BLE001 — sem o encaixe, as almas vão de nó a nó
        avisos.append("as almas ficaram de eixo a eixo (o encaixe nas faces não foi feito: %s)" % exc)
    return {"novas": [b.dict() for b in novas], "alterar": alterar,
            "resumo": {"paineis": n, "pecas": len(novas), "tipo": tipo}, "avisos": avisos}


# ------------------------------------------------------------------ contraventamento em X

def contravento_x(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """As diagonais em X entre duas barras paralelas (dois pilares, dois banzos), em `paineis` painéis iguais."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    bs = _barras(doc, ids)
    if len(bs) != 2:
        raise ErroDeDados("selecione as duas barras do vão contraventado (dois pilares, ou os banzos de duas tesouras)")
    a, b = bs
    wa, wb = _norm(_sub(a.fim, a.inicio)), _norm(_sub(b.fim, b.inicio))
    if abs(_dot(wa, wb)) < 0.98:
        raise ErroDeDados("as duas barras não são paralelas")
    if _dot(wa, wb) < 0:
        b0, b1 = b.fim, b.inicio
    else:
        b0, b1 = b.inicio, b.fim
    perfil = str(p.get("perfil") or "FE RED 1/2''")
    paineis = max(1, int(p.get("paineis") or 1))
    # o trecho comum, pela direção da primeira
    def s_de(q):
        return _dot(_sub(q, a.inicio), wa)
    s0 = max(0.0, min(s_de(b0), s_de(b1)))
    s1 = min(math.dist(a.inicio, a.fim), max(s_de(b0), s_de(b1)))
    margem = float(p.get("margem") or 0.0)
    s0, s1 = s0 + margem, s1 - margem
    if s1 - s0 < 300.0:
        raise ErroDeDados("as duas barras quase não correm juntas")

    def em_a(s):
        return _add(a.inicio, _mul(wa, s))

    def em_b(s):
        L = _dot(_sub(b1, b0), wa) or 1.0
        return _add(b0, _mul(_sub(b1, b0), (s - _dot(_sub(b0, a.inicio), wa)) / L))
    novas = []
    papel = str(p.get("papel") or "contraventamento")
    for k in range(paineis):
        sa, sb = s0 + (s1 - s0) * k / paineis, s0 + (s1 - s0) * (k + 1) / paineis
        for p0, p1 in ((em_a(sa), em_b(sb)), (em_b(sa), em_a(sb))):
            novas.append(Barra(nome="Contraventamento", inicio=_r(p0), fim=_r(p1), perfil=perfil, papel=papel,
                               camada="Contraventamento", material="Aço", atributos={"tipo_ifc": "IfcMember"}))
    if str(p.get("suporte") or "nenhum") == "sc1":
        return _com_suporte_sc1(doc, a, b, novas, paineis)
    return {"novas": [x.dict() for x in novas], "resumo": {"paineis": paineis, "pecas": len(novas)}, "avisos": []}


def _com_suporte_sc1(doc, a, b, diagonais, paineis) -> dict:
    """As diagonais do contravento de cobertura já nos suportes SC1 (a ligação suporte_contravento da biblioteca, a
    mesma do Aplicar ligação): uma ligação por tirante, cada uma vendo as anteriores. O nó em que chegam dois tirantes
    (entre dois painéis) ganha dois SC1 no mesmo ponto — não se inventa o suporte de dois furos: vai como aviso."""
    from nucleo3d import ligacoes3d
    from nucleo3d.modelo import Documento
    if abs(_norm(_sub(a.fim, a.inicio))[2]) > 0.7:
        raise ErroDeDados("o suporte SC1 é do contravento de cobertura (a cantoneira no topo do banzo): "
                          "entre pilares, lance sem suporte e aplique a ligação depois")
    base = doc.dict()
    base["entidades"] = list(base["entidades"]) + [d.dict() for d in diagonais]
    por_id = {e["id"]: e for e in base["entidades"]}
    novos_ids = [d.id for d in diagonais]
    alterar: Dict[str, dict] = {}
    for d in diagonais:
        r = ligacoes3d.aplicar(Documento.de_dict(base), "suporte_contravento", [d.id, a.id, b.id])
        for e in r["novas"]:
            base["entidades"].append(e)
            por_id[e["id"]] = e
            novos_ids.append(e["id"])
        for i, campos in r["alterar"].items():
            por_id[i].update({k: (list(v) if isinstance(v, tuple) else v) for k, v in campos.items()})
            if i not in novos_ids:
                alterar.setdefault(i, {}).update(campos)
    novas = [por_id[i] for i in novos_ids]
    # os nós com dois suportes no mesmo lugar
    scs = [e for e in novas if e.get("papel") == "suporte"]
    juntos = sum(1 for i, x in enumerate(scs) for y in scs[i + 1:] if math.dist(x["inicio"], y["inicio"]) < 60.0)
    avisos = ["%d nó(s) com dois tirantes chegando: dois SC1 no mesmo ponto — defina o suporte desse nó (um de dois "
              "furos, ou afaste os tirantes)" % juntos] if juntos else []
    return {"novas": novas, "alterar": alterar,
            "resumo": {"paineis": paineis, "pecas": len(novas), "suportes": len(scs)}, "avisos": avisos}


# ------------------------------------------------------------------ pilares nos eixos

def _cruzamentos(eixos: Sequence[dict]) -> List[dict]:
    """os cruzamentos dos eixos da obra (em planta): [{nome "A-2", x, y}]"""
    fora = []
    for i in range(len(eixos)):
        for j in range(i + 1, len(eixos)):
            e1, e2 = eixos[i], eixos[j]
            a1, b1, a2, b2 = e1["a"], e1["b"], e2["a"], e2["b"]
            d1 = (b1[0] - a1[0], b1[1] - a1[1])
            d2 = (b2[0] - a2[0], b2[1] - a2[1])
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 1e-6 * math.hypot(*d1) * math.hypot(*d2):
                continue                                  # paralelos
            t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
            u_ = ((a2[0] - a1[0]) * d1[1] - (a2[1] - a1[1]) * d1[0]) / den
            if -0.01 <= t <= 1.01 and -0.01 <= u_ <= 1.01:
                n1, n2 = str(e1.get("nome") or ""), str(e2.get("nome") or "")
                nome = "%s-%s" % ((n1, n2) if n1.isalpha() else (n2, n1))
                fora.append({"nome": nome, "x": round(a1[0] + d1[0] * t, 1), "y": round(a1[1] + d1[1] * t, 1),
                             "eixos": [n1, n2]})
    return sorted(fora, key=lambda c: (c["nome"]))


def pilares_nos_eixos(eixos: Sequence[dict], cruzamentos: Sequence[str], p: Optional[dict] = None) -> dict:
    """Um pilar em cada cruzamento escolhido ("A-2"), da base ao topo, com a alma no plano do eixo pedido."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    perfil = str(p.get("perfil") or "W 250×32,7")
    _perfil(perfil)
    z0 = float(p.get("base") or 0.0)
    z1 = float(p.get("topo") or 6000.0)
    if z1 - z0 < 100.0:
        raise ErroDeDados("o topo do pilar precisa estar acima da base")
    alma = str(p.get("alma") or "numerados")             # a alma no plano dos eixos numerados (o pórtico) ou com letra
    todos = {c["nome"]: c for c in _cruzamentos(eixos)}
    escolhidos = [todos[n] for n in cruzamentos if n in todos] if cruzamentos else list(todos.values())
    if not escolhidos:
        raise ErroDeDados("nenhum cruzamento de eixos escolhido (os eixos da obra estão gravados? Ver → Arquitetônico, eixos e níveis)")
    por_nome = {str(e.get("nome")): e for e in eixos}
    novas = []
    for c in escolhidos:
        # a direção do eixo cujo plano recebe a alma: o d do pilar ao longo dele
        e_alma = next((por_nome.get(n) for n in c["eixos"] if (n.isdigit() if alma == "numerados" else n.isalpha())), None)
        b = Barra(nome="Pilar %s" % c["nome"], inicio=(c["x"], c["y"], z0), fim=(c["x"], c["y"], z1), perfil=perfil,
                  papel="pilar", camada="Pilares", material="Aço",
                  atributos={"tipo_ifc": "IfcColumn", "eixo": c["nome"]})
        if e_alma is not None:
            d = (e_alma["b"][0] - e_alma["a"][0], e_alma["b"][1] - e_alma["a"][1], 0.0)
            # o v da seção (a altura d) ao longo do eixo
            b.rotacao = _rotacao_para_v((0.0, 0.0, 1.0), _norm(d))
        novas.append(b)
    return {"novas": [x.dict() for x in novas], "resumo": {"pilares": len(novas)}, "avisos": []}


# ------------------------------------------------------------------ viga entre pilares

def viga_entre_pilares(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """A viga no nível pedido ligando os pilares escolhidos, na ordem em planta (um trecho entre cada par vizinho),
    com o topo da viga no nível."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    pilares = [b for b in _barras(doc, ids) if abs(_norm(_sub(b.fim, b.inicio))[2]) > 0.7]
    if len(pilares) < 2:
        raise ErroDeDados("selecione dois ou mais pilares")
    perfil = str(p.get("perfil") or "W 310×38,7")
    pv = _perfil(perfil)
    nivel = p.get("nivel")
    if nivel in (None, ""):
        nivel = min(max(b.inicio[2], b.fim[2]) for b in pilares)        # o topo do pilar mais baixo
    nivel = float(nivel)
    z = nivel - float(pv.d or 300) / 2.0                 # o topo da viga no nível
    pts = [(b.inicio[0], b.inicio[1]) for b in pilares]
    # a ordem em planta: ao longo da maior extensão
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    k = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
    ordem = sorted(pilares, key=lambda b: b.inicio[k])
    continua = str(p.get("continua") or "nao") == "sim"
    trechos = [(ordem[0], ordem[-1])] if continua else list(zip(ordem[:-1], ordem[1:]))
    novas = []
    for a, b in trechos:
        p0 = (a.inicio[0], a.inicio[1], z)
        p1 = (b.inicio[0], b.inicio[1], z)
        novas.append(Barra(nome="Viga", inicio=_r(p0), fim=_r(p1), perfil=perfil, papel="viga", camada="Vigas",
                           material="Aço", atributos={"tipo_ifc": "IfcBeam"}))
    avisos = [] if all(max(b.inicio[2], b.fim[2]) >= nivel - 1.0 for b in pilares) else \
        ["algum pilar termina abaixo do nível da viga: confira o topo dos pilares"]
    return {"novas": [x.dict() for x in novas], "resumo": {"vigas": len(novas), "nivel": nivel}, "avisos": avisos}


# ------------------------------------------------------------------ longarinas de fechamento

def longarinas(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """As fiadas de longarinas na face de fora dos pilares escolhidos (uma parede), como o gerador do galpão: a alma na
    horizontal (o eixo forte contra o vento), a boca para baixo (não junta água nem pó), igualmente espaçadas entre a
    primeira e a última fiada, uma por vão ou contínuas."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    pilares = [b for b in _barras(doc, ids) if abs(_norm(_sub(b.fim, b.inicio))[2]) > 0.7]
    if len(pilares) < 2:
        raise ErroDeDados("selecione dois ou mais pilares de uma parede: as longarinas vão de um ao outro")
    perfil = str(p.get("perfil") or "Ue 150×60×20×2,25")
    pl = _perfil(perfil)
    esp = float(p.get("espacamento") or 1900.0)
    base = max(min(b.inicio[2], b.fim[2]) for b in pilares)
    topo = min(max(b.inicio[2], b.fim[2]) for b in pilares)
    # no oitão os pilares sobem até a água: a fiada só entra no vão em que os dois chegam acima dela (folga)
    folga_topo = float(p.get("folga_topo") or 300.0)
    topo_max = max(max(b.inicio[2], b.fim[2]) for b in pilares)
    z0 = float(p["primeira"]) if p.get("primeira") not in (None, "") else base + esp
    z1 = float(p["ultima"]) if p.get("ultima") not in (None, "") else topo_max - folga_topo
    balanco = float(p.get("balanco") or 0.0)
    continua = str(p.get("continua") or "nao") == "sim"
    boca = str(p.get("boca") or "baixo")
    # a linha da parede em planta: a direção dos dois pilares mais afastados
    pes = [(b, (b.inicio[0], b.inicio[1], 0.0)) for b in pilares]
    a_, b_ = max(((x, y) for x in pes for y in pes), key=lambda xy: math.dist(xy[0][1], xy[1][1]))
    w = _norm(_sub(b_[1], a_[1]))
    nw = (-w[1], w[0], 0.0)
    for _b, q in pes:
        if abs(_dot(_sub(q, a_[1]), nw)) > 300.0:
            raise ErroDeDados("os pilares não estão numa linha: selecione os de uma parede só")
    pes.sort(key=lambda x: _dot(x[1], w))
    # o lado de fora: para longe do meio do modelo
    outros = [e for e in doc.entidades.values() if getattr(e, "tipo", "") == "barra" and e.id not in set(ids)]
    if outros:
        cx = sum((e.inicio[0] + e.fim[0]) / 2 for e in outros) / len(outros)
        cy = sum((e.inicio[1] + e.fim[1]) / 2 for e in outros) / len(outros)
        if _dot(_sub((cx, cy, 0.0), a_[1]), nw) > 0:
            nw = _mul(nw, -1.0)
    if str(p.get("lado") or "fora") == "dentro":
        nw = _mul(nw, -1.0)
    # o plano das longarinas: a face mais saliente dos pilares (o plano do fechamento fica reto)
    face = max(_topo(b, nw) - _dot(q, nw) for b, q in pes)
    d_l = float(pl.d or 150.0)
    off = face + d_l / 2.0
    if z1 < z0:
        zs, passo = [z0], 0.0
    else:
        n = max(1, int(math.ceil((z1 - z0) / esp - 1e-6)))
        passo = (z1 - z0) / n
        zs = [z0 + k * passo for k in range(n + 1)]
    novas = []
    alto = [max(b_.inicio[2], b_.fim[2]) for b_, _q in pes]
    for j, z in enumerate(zs):
        cs = [(q[0] + nw[0] * off, q[1] + nw[1] * off, z) for _b, q in pes]
        # os pilares que passam da fiada (com a folga): os trechos ficam entre pilares vizinhos que passam
        ok_ = [h >= z + folga_topo - 1e-6 for h in alto]
        if continua:
            # contínua: o maior trecho de pilares seguidos que passam
            blocos, atual = [], []
            for k in range(len(cs)):
                if ok_[k]:
                    atual.append(k)
                else:
                    if len(atual) >= 2:
                        blocos.append(atual)
                    atual = []
            if len(atual) >= 2:
                blocos.append(atual)
            trechos = [(cs[bl[0]], cs[bl[-1]]) for bl in blocos]
        else:
            trechos = [(cs[k], cs[k + 1]) for k in range(len(cs) - 1) if ok_[k] and ok_[k + 1]]
        for i, (c0, c1) in enumerate(trechos):
            dirt = _norm(_sub(c1, c0))
            if i == 0 and balanco:
                c0 = _sub(c0, _mul(dirt, balanco))
            if i == len(trechos) - 1 and balanco:
                c1 = _add(c1, _mul(dirt, balanco))
            rot = _rotacao_para_v(dirt, nw)
            ub = _u_da_barra(dirt, rot)
            if (boca == "baixo" and ub[2] > 0) or (boca == "cima" and ub[2] < 0):
                rot = round((rot + 180.0) % 360.0, 3)
            novas.append(Barra(nome="Longarina", inicio=_r(c0), fim=_r(c1), perfil=perfil, rotacao=rot,
                               papel="longarina", camada="Terças", material="Aço galvanizado",
                               atributos={"tipo_ifc": "IfcMember", "fiada": j + 1, "vao": i + 1}))
    # a terça no topo (a "terça de oitão inclinada", decisão do usuário 15/10): de pilar a pilar pela linha dos topos,
    # no plano das longarinas, com a borda de cima `abaixo_topo` abaixo do topo dos pilares — inclinada no oitão,
    # reta na parede lateral
    oitao = topo_max - topo > 300.0
    n_topo = 0
    if str(p.get("topo") or ("sim" if oitao else "nao")) == "sim":
        abaixo = float(p.get("abaixo_topo") or 0.0)
        for k in range(len(pes) - 1):
            (_b0, q0), (_b1, q1) = pes[k], pes[k + 1]
            c0 = (q0[0] + nw[0] * off, q0[1] + nw[1] * off, alto[k])
            c1 = (q1[0] + nw[0] * off, q1[1] + nw[1] * off, alto[k + 1])
            dirt = _norm(_sub(c1, c0))
            rot = _rotacao_para_v(dirt, nw)
            ub = _u_da_barra(dirt, rot)
            if (boca == "baixo" and ub[2] > 0) or (boca == "cima" and ub[2] < 0):
                rot = round((rot + 180.0) % 360.0, 3)
            t = Barra(nome="Terça de oitão" if abs(alto[k] - alto[k + 1]) > 1.0 else "Longarina de topo",
                      inicio=_r(c0), fim=_r(c1), perfil=perfil, rotacao=rot, papel="longarina", camada="Terças",
                      material="Aço galvanizado", atributos={"tipo_ifc": "IfcMember", "topo": True, "vao": k + 1})
            # a borda de cima na linha dos topos (a malha manda: o Ue não é simétrico)
            dz = (max(alto[k], alto[k + 1]) - abaixo) - _topo(t, (0.0, 0.0, 1.0))
            t.inicio = _r(_add(t.inicio, (0.0, 0.0, dz)))
            t.fim = _r(_add(t.fim, (0.0, 0.0, dz)))
            novas.append(t)
            n_topo += 1
    avisos = []
    if passo and passo > esp + 1e-6:
        avisos.append("espaçamento acima do pedido")
    if zs[0] < base:
        avisos.append("fiada abaixo do pé dos pilares: confira a primeira")
    if oitao and not n_topo:
        avisos.append("pilares de alturas diferentes (oitão): cada fiada só vai entre os pilares que passam dela; "
                      "a terça inclinada do topo ficou desligada")
    return {"novas": [b.dict() for b in novas],
            "resumo": {"linhas": len(zs), "passo": round(passo, 1), "pecas": len(novas), "topo": n_topo}, "avisos": avisos}


# ------------------------------------------------------------------ correntes entre terças

def _estacoes_de_apoio(doc, ids, w, ref_a, ref_z) -> List[float]:
    """as estações (ao longo de w, a partir de 0) em que outra barra cruza por baixo da linha de terça (ref_a + s·w), em
    planta: as tesouras e as vigas que apoiam as terças"""
    fora = []
    sel = set(ids)
    for e in doc.entidades.values():
        if getattr(e, "tipo", "") != "barra" or e.id in sel:
            continue
        d = _sub(e.fim, e.inicio)
        if math.hypot(d[0], d[1]) < 1.0 or abs(_dot(_norm((d[0], d[1], 0.0)), w)) > 0.5:
            continue                                      # em pé ou paralela às terças
        den = w[0] * d[1] - w[1] * d[0]
        if abs(den) < 1e-9:
            continue
        rx, ry = e.inicio[0] - ref_a[0], e.inicio[1] - ref_a[1]
        s = (rx * d[1] - ry * d[0]) / den
        t = (rx * w[1] - ry * w[0]) / den
        if not (-0.01 <= t <= 1.01):
            continue
        z = e.inicio[2] + d[2] * t
        if 0.0 <= ref_z - z <= 1500.0:                   # por baixo da terça
            fora.append(s + _dot(ref_a, w))
    return fora


def _cumeeira_entre(pts, nw) -> Optional[int]:
    """o índice i do par de linhas (i, i+1) que passa pela cumeeira — onde a inclinação quebra: sobe até a linha i e
    desce depois da i+1 (ou, sem linha de um dos lados, deixa de subir) —, ou None (uma água só, cobertura plana)"""
    n = len(pts)
    if n < 3:
        return None
    c = [_dot(q, nw) for q in pts]
    z = [q[2] for q in pts]

    def m(j):                                             # a inclinação entre as linhas j e j+1
        return (z[j + 1] - z[j]) / ((c[j + 1] - c[j]) or 1e-9)
    TOL = 0.005                                           # 0,5 %
    for i in range(n - 1):
        esq = m(i - 1) if i >= 1 else None
        dir_ = m(i + 1) if i + 2 < n else None
        if esq is not None and dir_ is not None:
            if esq > TOL and dir_ < -TOL:
                return i
        elif esq is not None:
            if esq > TOL and m(i) < esq / 2.0:
                return i
        elif dir_ is not None:
            if dir_ < -TOL and m(i) > dir_ / 2.0:
                return i
    return None


def _ponto_da_cumeeira(pts, i, nw, w, xv):
    """o encontro dos planos dos centros das terças das duas águas (a cumeeira), na estação xv ao longo das terças"""
    c = [_dot(q, nw) for q in pts]
    z = [q[2] for q in pts]
    linhas = []
    if i >= 1:
        linhas.append((c[i - 1], z[i - 1], c[i], z[i]))
    if i + 2 < len(pts):
        linhas.append((c[i + 2], z[i + 2], c[i + 1], z[i + 1]))
    cm = (c[i] + c[i + 1]) / 2.0
    zm = max(z[i], z[i + 1])
    if len(linhas) == 2:
        (a0, b0, a1, b1), (e0, f0, e1, f1) = linhas
        m1 = (b1 - b0) / ((a1 - a0) or 1e-9)
        m2 = (f1 - f0) / ((e1 - e0) or 1e-9)
        if abs(m1 - m2) > 1e-9:
            cx = (f0 - b0 + m1 * a0 - m2 * e0) / (m1 - m2)
            if min(c[i], c[i + 1]) - 1.0 <= cx <= max(c[i], c[i + 1]) + 1.0:
                cm, zm = cx, b0 + m1 * (cx - a0)
    elif linhas:
        a0, b0, a1, b1 = linhas[0]
        zm = b0 + (b1 - b0) / ((a1 - a0) or 1e-9) * (cm - a0)
    return (w[0] * xv + nw[0] * cm, w[1] * xv + nw[1] * cm, zm)


def correntes(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """As correntes entre as linhas de terças escolhidas (as duas águas, se quiser): `linhas` por vão (1 = no meio,
    2 = nos terços), de centro a centro das terças, como o gerador do galpão. Os vãos vêm dos apoios que cruzam por
    baixo das terças (tesouras, vigas) e das pontas delas. Com as duas águas, a ligação pela cumeeira fecha em V
    (`cumeeira` = "v", o tirante de cumeeira do gerador) ou vai reta ("reta")."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    tercas = [b for b in _barras(doc, ids) if abs(_norm(_sub(b.fim, b.inicio))[2]) < 0.7]
    if len(tercas) < 2:
        raise ErroDeDados("selecione as terças (duas linhas ou mais): as correntes vão de uma à outra")
    perfil = str(p.get("perfil") or "Barra ø 16 mm")
    _perfil(perfil)
    n_lin = max(1, int(p.get("linhas") or 1))
    em_v = str(p.get("cumeeira") or "v") == "v"
    d0 = _sub(tercas[0].fim, tercas[0].inicio)
    w = _norm((d0[0], d0[1], 0.0))
    nw = (-w[1], w[0], 0.0)
    segs = []
    for b in tercas:
        a, c = b.inicio, b.fim
        d = _sub(c, a)
        if abs(_dot(_norm((d[0], d[1], 0.0)), w)) < 0.98:
            raise ErroDeDados("as terças escolhidas não são paralelas")
        if _dot(d, w) < 0:
            a, c = c, a
        segs.append((b, a, c, _dot(a, w), _dot(c, w), _dot(_mul(_add(a, c), 0.5), nw)))
    # as estações dos vãos: as pontas das terças e os apoios por baixo delas
    est = [s[3] for s in segs] + [s[4] for s in segs]
    for s in segs:
        est += [x for x in _estacoes_de_apoio(doc, ids, w, s[1], (s[1][2] + s[2][2]) / 2.0) if s[3] - 1 <= x <= s[4] + 1]
    juntas = []
    for x in sorted(est):
        if not juntas or x - juntas[-1] > 100.0:
            juntas.append(x)

    def no_eixo(seg, s):
        _b, a, c, sa, sc, _n = seg
        t = (s - sa) / ((sc - sa) or 1.0)
        return _add(a, _mul(_sub(c, a), t))
    novas = []
    n_vaos = 0
    for sa, sb in zip(juntas[:-1], juntas[1:]):
        linhas = sorted((s for s in segs if s[3] <= sa + 1.0 and s[4] >= sb - 1.0), key=lambda s: s[5])
        unicas = []                                       # duas peças na mesma linha contam uma vez
        for s in linhas:
            if not unicas or s[5] - unicas[-1][5] > 30.0:
                unicas.append(s)
        if len(unicas) < 2:
            continue
        n_vaos += 1
        for k in range(1, n_lin + 1):
            xc = sa + (sb - sa) * k / (n_lin + 1.0)
            pts = [no_eixo(s, xc) for s in unicas]
            kc = _cumeeira_entre(pts, nw) if em_v else None
            for i, (q0, q1) in enumerate(zip(pts[:-1], pts[1:])):
                at = {"tipo_ifc": "IfcMember", "vao": n_vaos, "linha_corrente": k}
                if i != kc:
                    novas.append(Barra(nome="Corrente de terça", inicio=_r(q0), fim=_r(q1), perfil=perfil, papel="corrente",
                                       camada="Terças", material="Aço", atributos=at))
                    continue
                # o tirante de cumeeira em V, como o gerador do galpão: as duas terças de cima vão ao mesmo ponto da
                # cumeeira (no plano dos centros das terças), adiantado 6 % do vão ao longo dela
                adiante = 0.06 * (sb - sa)
                xv = xc + adiante if xc + adiante <= sb else xc - adiante
                C = _ponto_da_cumeeira(pts, kc, nw, w, xv)
                for q in (q0, q1):
                    novas.append(Barra(nome="Tirante de cumeeira", inicio=_r(q), fim=_r(C), perfil=perfil, papel="corrente",
                                       camada="Terças", material="Aço", atributos=dict(at, cumeeira=True)))
    if not novas:
        raise ErroDeDados("nenhum vão com duas linhas de terças lado a lado")
    return {"novas": [b.dict() for b in novas], "resumo": {"vaos": n_vaos, "linhas": n_lin, "pecas": len(novas)},
            "avisos": []}


# ------------------------------------------------------------------ mão-francesa

def _cruzamento_em_planta(a0, a1, b0, b1):
    """(t, u) da interseção em planta das retas a0→a1 e b0→b1 (parâmetros de 0 a 1 em cada), ou None se paralelas"""
    da = (a1[0] - a0[0], a1[1] - a0[1])
    db = (b1[0] - b0[0], b1[1] - b0[1])
    den = da[0] * db[1] - da[1] * db[0]
    if abs(den) < 1e-9 * max(1.0, math.hypot(*da) * math.hypot(*db)):
        return None
    rx, ry = b0[0] - a0[0], b0[1] - a0[1]
    return (rx * db[1] - ry * db[0]) / den, (rx * da[1] - ry * da[0]) / den


def mao_francesa(doc, ids: Sequence[str], p: Optional[dict] = None) -> dict:
    """A mão-francesa da terça à mesa de baixo do apoio (a tesoura de alma cheia, a viga), nos dois lados de cada apoio:
    a cantoneira no plano vertical da terça, a `angulo` graus da horizontal, com uma aba deitada nesse plano (encosta
    na alma da terça). Selecionadas só as terças, os apoios são as barras que cruzam por baixo delas; selecionados
    também os apoios, só esses."""
    from nucleo3d.modelo import Barra
    p = dict(p or {})
    bs = [b for b in _barras(doc, ids) if abs(_norm(_sub(b.fim, b.inicio))[2]) < 0.7]
    tercas = [b for b in bs if str(b.papel).lower() in ("terça", "terca", "longarina")]
    apoios = [b for b in bs if b not in tercas]
    if not tercas:
        raise ErroDeDados("selecione as terças (e, se quiser, os apoios): a mão-francesa vai da terça à mesa de baixo do apoio")
    if not apoios:
        sel = set(ids)
        apoios = [e for e in doc.entidades.values() if getattr(e, "tipo", "") == "barra" and e.id not in sel
                  and str(getattr(e, "papel", "")).lower() not in ("terça", "terca", "corrente", "longarina", "contraventamento")
                  and abs(_norm(_sub(e.fim, e.inicio))[2]) < 0.7]
    perfil = str(p.get("perfil") or "L 1 1/2'' X 1/8''")
    _perfil(perfil)
    ang = math.radians(float(p.get("angulo") or 45.0))
    if not (math.radians(20) <= ang <= math.radians(70)):
        raise ErroDeDados("o ângulo da mão-francesa fica entre 20° e 70°")
    recuo = float(p.get("recuo") or 30.0)
    lados = str(p.get("lados") or "ambos")
    novas = []
    pares = 0
    for t in tercas:
        wt = _norm(_sub(t.fim, t.inicio))
        Lt = math.dist(t.inicio, t.fim)
        for a in apoios:
            r = _cruzamento_em_planta(t.inicio, t.fim, a.inicio, a.fim)
            if r is None:
                continue
            st, sa = r
            if not (-0.001 <= st <= 1.001 and -0.001 <= sa <= 1.001):
                continue
            N = _add(t.inicio, _mul(_sub(t.fim, t.inicio), st))
            A = _add(a.inicio, _mul(_sub(a.fim, a.inicio), sa))
            if not (0.0 < N[2] - A[2] <= 1500.0):
                continue                                  # o apoio não está logo abaixo da terça
            # para baixo no plano da terça (perpendicular a ela) e a meia altura dela nessa direção
            dt = _norm(_sub((0.0, 0.0, -1.0), _mul(wt, -wt[2])))
            e_t = _topo(t, dt) - _dot(N, dt)
            T0 = _add(N, _mul(dt, e_t - recuo))
            # a mesa de baixo do apoio, na vertical do cruzamento
            wa = _norm(_sub(a.fim, a.inicio))
            da_ = _norm(_sub((0.0, 0.0, -1.0), _mul(wa, -wa[2])))
            e_a = _topo(a, da_) - _dot(A, da_)
            desce = (e_a - recuo) / max(abs(da_[2]), 0.2)
            B = (A[0], A[1], A[2] - desce)
            h = T0[2] - B[2]
            if h < 50.0:
                continue                                  # sem altura para a mão-francesa
            dist = h / math.tan(ang)
            # o plano vertical da terça: a normal horizontal (uma aba da L deitada nele)
            n_p = _norm(_cruz(wt, (0.0, 0.0, 1.0)))
            pares += 1
            for s in ((1.0, -1.0) if lados == "ambos" else (1.0,)):
                if not (0.0 <= st * Lt + s * dist <= Lt):
                    continue                              # a terça acaba antes: deste lado não cabe
                T = _add(T0, _mul(wt, s * dist))
                d = _norm(_sub(B, T))
                novas.append(Barra(nome="Mão-francesa", inicio=_r(T), fim=_r(B), perfil=perfil,
                                   rotacao=_rotacao_para_v(d, n_p), papel="mão-francesa", camada="Terças",
                                   material="Aço galvanizado",
                                   atributos={"tipo_ifc": "IfcMember", "terca": t.id, "apoio": a.id}))
    if not novas:
        raise ErroDeDados("nenhum apoio logo abaixo das terças escolhidas (até 1,5 m) com altura para a mão-francesa")
    return {"novas": [b.dict() for b in novas], "resumo": {"apoios": pares, "pecas": len(novas)},
            "avisos": ["a fixação (o parafuso na alma da terça, a chapinha na mesa do apoio) vem pelo Aplicar ligação ou por um detalhe"]}
