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
* **viga entre pilares** — a viga no nível pedido ligando os pilares escolhidos, na ordem em que estão em planta.

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
    return {"novas": [x.dict() for x in novas], "resumo": {"paineis": paineis, "pecas": len(novas)}, "avisos": []}


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
