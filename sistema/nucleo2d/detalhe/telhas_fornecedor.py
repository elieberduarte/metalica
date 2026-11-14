# -*- coding: utf-8 -*-
"""As telhas para o fornecedor: o padrão do Fábio (usuário, 13/11; briefing Projeto/BRIEFINGS/Briefing-padrao-telhas-
fabio-2026-11-13.md). Quem recebe as telhas quer:

- tudo em TAMANHO REAL ("que ele consiga tirar uma cota e conferir que o desenho está desenhado do tamanho que a cota
  mostra"): 1 unidade = 1 mm, sem escala, sem detalhe ampliado, e a cota sem número escrito por cima — mede a geometria;
- a multidobra em dois quadros (medidas internas e externas), o perfil com as duas faces e seis cotas em cada um;
- a fachada com as chapas inteiras da largura útil (980), só a cota do comprimento, a estrutura atrás em unifilar;
- o corte da cobertura sem nomes, a tesoura em unifilar e a telha na espessura real;
- nada de marca (TLn), peso, escala, observação de corte nem relação no desenho: a relação é o Word.

Os números saem dos mesmos dados do detalhamento das telhas (nucleo2d/detalhe/telhas.py: multidobras, faces_de_telhas,
corte_da_cobertura); aqui só muda o desenho. A prancha de papel do sistema não muda.
"""
import math
from typing import Optional

from nucleo2d.detalhe.telhas import _perfil_da_face

#: o tamanho dos textos e das cotas no Model: como numa folha a 1:25 (o texto de 2,5 mm de papel sai com 62,5 mm) — o
#: projeto do Fábio usa textos de 60 a 100 mm em perfis de 2 m
ESCALA_TEXTO = 25.0
#: o espaço entre os quadros e em volta dos perfis (mm de papel, × ESCALA_TEXTO)
MARGEM_QUADRO = 20.0
#: a estrutura de referência (o unifilar atrás da fachada, a tesoura e as terças do corte): camada própria, cinza e fina,
#: para o fornecedor poder desligar (GESTÃO, revisão do "é assim?", 13/11); as cotas vêm depois, por cima
CAMADA_ESTRUTURA = "ESTRUTURA-REF"


def _camada_estrutura(desenho):
    from nucleo2d.desenho import Camada2D
    if CAMADA_ESTRUTURA not in desenho.camadas:
        desenho.camadas[CAMADA_ESTRUTURA] = Camada2D(CAMADA_ESTRUTURA, "#9aa4b2", espessura=0.13)


def _m3(mm: float) -> str:
    """1995 → "1,995m" (o total da multidobra, em metros com 3 casas)"""
    return ("%.3f" % (mm / 1000.0)).replace(".", ",") + "m"


def md_das_medidas(reta1: float, reta2: float, raio_int: float, angulo: float, altura_onda: float = 40.0) -> dict:
    """Uma multidobra a partir das medidas da fábrica (as duas retas, o raio interno e o ângulo da dobra, em graus),
    no formato de telhas.multidobras — para o desenho e para os testes com os quadros do Fábio."""
    th = math.radians(angulo)
    R = raio_int + altura_onda / 2.0                       # a linha do meio da chapa
    T = R * math.tan(th / 2.0)
    d1 = (1.0, 0.0)
    d2 = (math.cos(th), math.sin(th))
    I = (0.0, 0.0)
    p1 = (I[0] - d1[0] * (T + reta1), I[1] - d1[1] * (T + reta1))
    p2 = (I[0] + d2[0] * (T + reta2), I[1] + d2[1] * (T + reta2))
    r_i, r_e = raio_int, raio_int + altura_onda
    return {"p1": p1, "p2": p2, "d1": d1, "d2": d2, "I": I, "T": T, "sentido": 1, "raio": R, "altura_onda": altura_onda,
            "reta1": reta1, "reta2": reta2, "raio_int": r_i, "raio_ext": r_e, "angulo": angulo,
            "arco_int": r_i * th, "arco_ext": r_e * th,
            "desenv_int": reta1 + reta2 + r_i * th, "desenv_ext": reta1 + reta2 + r_e * th}


def _face(md: dict, lado: float):
    """a linha de uma face do perfil: (pontos, reta1 (a, b), reta2 (a, b), arco, centro, raio)"""
    r1, arco, r2, centro, r = _perfil_da_face(md, lado)
    return [r1[0], r1[1]] + list(arco[1:-1]) + [r2[0], r2[1]], r1, r2, arco, centro, r


def desenho_da_multidobra(md: dict, desenho, dx: float = 0.0, dy: float = 0.0, lugar: str = "",
                          quantidade: Optional[int] = None):
    """A multidobra do fornecedor (o "Multidobra cobertura - 206x" do Fábio): dois quadros, "medidas internas" e
    "medidas externas", com o total em metros; em cada um o perfil com as duas faces (a espessura da onda) e seis cotas
    da face daquele quadro — as duas retas, o arco, o raio, o ângulo e a corda. Em tamanho real. Devolve os extremos."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.desenho import Cota, CotaEspecial
    esc = desenho.escala
    atr = {"conjunto": md.get("conjunto", ""), "detalhe": "multidobra_fornecedor"}
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    if md.get("raio_int") and md.get("raio_ext"):
        # as duas faces nos raios comerciais (R450 int. / R490 ext. na TP40: a onda do catálogo), não na onda medida no
        # modelo (41 na Sala: saía R491) — os mesmos raios do arco e do desenvolvido da relação
        ri, re_ = float(md["raio_int"]), float(md["raio_ext"])
        R0, R1 = float(md["raio"]), (ri + re_) / 2.0
        md = dict(md, altura_onda=re_ - ri, raio=R1, T=float(md["T"]) * R1 / R0 if R0 else md["T"])
    faces = {lado: _face(md, lado) for lado in (1.0, -1.0)}
    # a dobra em cima, como a telha fica na obra e como o Fábio desenha (o centro do arco abaixo da curva): espelhada
    # de cima para baixo quando vem ao contrário
    pts0, _r1, _r2, arco0, centro0, _r = faces[1.0]
    if centro0[1] > arco0[len(arco0) // 2][1]:
        E = lambda q: (q[0], -q[1])          # noqa: E731
        faces = {k: ([E(q) for q in f[0]], (E(f[1][0]), E(f[1][1])), (E(f[2][0]), E(f[2][1])), [E(q) for q in f[3]], E(f[4]), f[5])
                 for k, f in faces.items()}
    todos = [q for f in faces.values() for q in f[0]]
    x0 = min(q[0] for q in todos)
    y0 = min(q[1] for q in todos)
    larg = max(q[0] for q in todos) - x0
    alt = max(q[1] for q in todos) - y0
    margem = MARGEM_QUADRO * esc
    passo = larg + 3.0 * margem
    n = quantidade if quantidade is not None else md.get("instancias")
    titulo = "Multidobra%s%s" % ((" " + lugar) if lugar else "", (" - %dx" % n) if n else "")
    # internas à esquerda, externas à direita (como o Fábio)
    for k, (lado, nome_q, total) in enumerate(((-1.0, "medidas internas", md["desenv_int"]),
                                               (1.0, "medidas externas", md["desenv_ext"]))):
        ox = k * passo
        T = lambda q, ox=ox: (q[0] - x0 + ox, q[1] - y0)          # noqa: E731
        # o perfil: as duas faces e as pontas fechadas
        for f in faces.values():
            p.polilinha([T(q) for q in f[0]], camada="ACO")
        for i in (0, -1):
            p.linha(*T(faces[1.0][0][i]), *T(faces[-1.0][0][i]), "ACO")
        pts, r1, r2, arco, centro, raio = faces[lado]
        C = T(centro)

        def fora(a, b):
            """o lado da linha a→b longe do centro da dobra (+1 = à esquerda do sentido a→b)"""
            ux, uy = b[0] - a[0], b[1] - a[1]
            mx, my = (a[0] + b[0]) / 2.0 - C[0], (a[1] + b[1]) / 2.0 - C[1]
            return 1.0 if (-uy * mx + ux * my) > 0 else -1.0

        M = T(arco[len(arco) // 2])

        def longe_da_dobra(a, b):
            """o lado da linha a→b longe do meio da curva (a corda: do lado aberto, como o Fábio)"""
            ux, uy = b[0] - a[0], b[1] - a[1]
            return -1.0 if (-uy * (M[0] - a[0]) + ux * (M[1] - a[1])) > 0 else 1.0

        def cota(a, b, desl, lado_=None):
            a, b = T(a), T(b)
            sinal = lado_(a, b) if lado_ else fora(a, b)
            desenho.add(Cota(modo="alinhada", p1=p._p(*a), p2=p._p(*b), deslocamento=desl * sinal, atributos=dict(atr)))
            # a linha de cota entra nos extremos
            L = math.dist(a, b) or 1.0
            s = desl * sinal * esc
            p._p(a[0] - (b[1] - a[1]) / L * s, a[1] + (b[0] - a[0]) / L * s)
            p._p(b[0] - (b[1] - a[1]) / L * s, b[1] + (b[0] - a[0]) / L * s)
        # as duas retas (por fora da dobra) e a corda (de ponta a ponta, do lado de lá do centro)
        cota(r1[0], r1[1], 6.0)
        cota(r2[0], r2[1], 6.0)
        cota(r1[0], r2[1], 6.0, longe_da_dobra)
        # o raio: do centro ao meio do arco
        meio = T(arco[len(arco) // 2])
        desenho.add(CotaEspecial(modo="raio", centro=p._p(*C), p1=p._p(*meio), posicao=p._p(*meio), atributos=dict(atr)))
        # o ângulo da dobra: no centro, entre as tangências, por fora do arco
        a0 = math.atan2(arco[0][1] - centro[1], arco[0][0] - centro[0])
        a1 = math.atan2(arco[-1][1] - centro[1], arco[-1][0] - centro[0])
        am = a0 + ((a1 - a0 + math.pi) % (2 * math.pi) - math.pi) / 2.0
        r_ang = raio + 14.0 * esc
        pos_ang = (C[0] + r_ang * math.cos(am), C[1] + r_ang * math.sin(am))
        desenho.add(CotaEspecial(modo="angular", centro=p._p(*C), p1=p._p(*T(arco[0])), p2=p._p(*T(arco[-1])),
                                 posicao=p._p(*pos_ang), casas=0, atributos=dict(atr)))
        p._p(C[0] + (r_ang + 4.0 * esc) * math.cos(am), C[1] + (r_ang + 4.0 * esc) * math.sin(am))
        # o comprimento do arco (não há cota de arco no DXF do sistema): o número medido na própria linha, ao longo
        # dela, com o símbolo do arco — o valor é o da geometria desenhada
        comp_arco = raio * abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi)          # o arco exato, não a poligonal
        r_txt = raio + 5.0 * esc
        tx, ty = C[0] + r_txt * math.cos(am), C[1] + r_txt * math.sin(am)
        rot = math.degrees(am) % 180.0 - 90.0                 # ao longo do arco, de pé para quem lê
        txt_arco = "%d" % round(comp_arco)
        p.texto(tx, ty, txt_arco, 2.5 * esc, camada="COTA", angulo=rot, alinhamento="centro", atributos={"arco": round(comp_arco, 1)})
        # o símbolo do arco sobre o número (desenhado: a fonte do AutoCAD não tem o ⌒)
        tg = math.radians(rot)
        sx, sy = tx - math.sin(tg) * 3.2 * esc, ty + math.cos(tg) * 3.2 * esc
        p.arco(sx, sy, 1.6 * esc, rot + 25.0, rot + 155.0, camada="COTA")
        # o título do quadro e o total
        cx = ox + larg / 2.0
        p.texto(cx, alt + margem + 4.5 * esc, nome_q, 3.0 * esc, alinhamento="centro")
        p.texto(cx, alt + margem, _m3(total), 3.0 * esc, alinhamento="centro", atributos={"total": round(total, 1)})
    p.texto((passo + larg) / 2.0, alt + margem + 11.0 * esc, titulo, 4.0 * esc, alinhamento="centro")
    p.texto(passo + larg, -margem, "Cotas em mm", 2.0 * esc, alinhamento="direita")
    return p.extremos


def desenho_da_cumeeira(cm: dict, desenho, dx: float = 0.0, dy: float = 0.0, quantidade: Optional[int] = None):
    """A cumeeira do fornecedor: o perfil das duas pernas, cada perna cotada (medida da geometria), o ângulo da dobra e
    o título "Cumeeira - Nx". Em tamanho real."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.desenho import Cota, CotaEspecial
    esc = desenho.escala
    atr = {"conjunto": cm.get("conjunto", ""), "detalhe": "cumeeira_fornecedor"}
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    d1, d2 = cm["d1"], cm["d2"]
    q1 = (d1[0] * cm["perna1"], d1[1] * cm["perna1"])
    q2 = (d2[0] * cm["perna2"], d2[1] * cm["perna2"])
    x0, y0 = min(0.0, q1[0], q2[0]), min(0.0, q1[1], q2[1])
    T = lambda q: (q[0] - x0, q[1] - y0)          # noqa: E731
    topo, a1, a2 = T((0.0, 0.0)), T(q1), T(q2)
    p.polilinha([a1, topo, a2], camada="ACO")
    for pa, pb in ((a1, topo), (topo, a2)):
        sinal = 1.0 if pb[0] - pa[0] >= 0 else -1.0
        desenho.add(Cota(modo="alinhada", p1=p._p(*pa), p2=p._p(*pb), deslocamento=8.0 * sinal, atributos=dict(atr)))
    # o ângulo da dobra, por baixo do topo
    baixo = (topo[0], topo[1] - 0.35 * min(cm["perna1"], cm["perna2"]))
    desenho.add(CotaEspecial(modo="angular", centro=p._p(*topo), p1=p._p(*a1), p2=p._p(*a2), posicao=p._p(*baixo),
                             atributos=dict(atr)))
    alt = max(a1[1], a2[1], topo[1])
    n = quantidade if quantidade is not None else cm.get("instancias")
    p.texto(topo[0], alt + 14.0 * esc, "Cumeeira%s" % ((" - %dx" % n) if n else ""), 4.0 * esc, alinhamento="centro")
    p.texto(max(a1[0], a2[0]), min(a1[1], a2[1]) - 10.0 * esc, "Cotas em mm", 2.0 * esc, alinhamento="direita")
    return p.extremos


# ============================================================ fachada, oitão, lateral, água (D3)
#: a estrutura que vai atrás da face: as barras com o eixo a menos disto (mm) do plano das telhas
ESTRUTURA_ATRAS = 700.0


def estrutura_da_face(pecas, face: dict, atras: float = ESTRUTURA_ATRAS):
    """A estrutura daquele plano em unifilar (os eixos das barras perto da face, no referencial dela: x = p·v, y = p·u):
    é ela que dá a linha do telhado atrás das chapas, como no oitão do Fábio. [((x0, y0), (x1, y1))]"""
    from nucleo2d.detalhe.base import _dot
    from nucleo2d.detalhe.telhas import _eh_telha, _medidas
    from nucleo2d.detalhe.base import _marcas
    n, u, v = face["normal"], face["u"], face["v"]
    plano = face.get("plano")
    if plano is None:
        return []
    xs = [q[0] for ch in face["chapas"] for q in ch["contorno"]]
    ys = [q[1] for ch in face["chapas"] for q in ch["contorno"]]
    x0, x1, y0, y1 = min(xs) - 1500.0, max(xs) + 1500.0, min(ys) - 1500.0, max(ys) + 1500.0
    segs = []
    for e in pecas:
        V = getattr(e, "vertices", None)
        if not V or len(V) < 4 or _eh_telha(str(_marcas(e).get("perfil") or e.nome or "")):
            continue
        try:
            c, eixos, ext = _medidas(e)
        except Exception:                     # noqa: BLE001
            continue
        if ext[0] < 300.0 or ext[0] < 4.0 * max(ext[1], 1.0):
            continue                          # chapa, parafuso, ligação: não é barra
        a = tuple(c[i] - eixos[0][i] * ext[0] / 2.0 for i in range(3))
        b = tuple(c[i] + eixos[0][i] * ext[0] / 2.0 for i in range(3))
        if max(abs(_dot(a, n) - plano), abs(_dot(b, n) - plano)) > atras:
            continue
        pa, pb = (_dot(a, v), _dot(a, u)), (_dot(b, v), _dot(b, u))
        if math.dist(pa, pb) < 50.0:
            continue                          # a barra de pé na face (a terça vista de ponta)
        if max(pa[0], pb[0]) < x0 or min(pa[0], pb[0]) > x1 or max(pa[1], pb[1]) < y0 or min(pa[1], pb[1]) > y1:
            continue
        segs.append((pa, pb))
    return segs


def _base_reta(ch: dict) -> bool:
    """a ponta de baixo da chapa é reta (o corte do modelo tem a largura toda na cota mais baixa) — senão a de cima é"""
    corte = ch.get("corte") or ch["contorno"]
    ys = [q[1] for q in corte]
    xs = [q[0] for q in corte]
    larg = max(xs) - min(xs)
    em_baixo = [q[0] for q in corte if q[1] <= min(ys) + 2.0]
    em_cima = [q[0] for q in corte if q[1] >= max(ys) - 2.0]
    lb = (max(em_baixo) - min(em_baixo)) if em_baixo else 0.0
    lc = (max(em_cima) - min(em_cima)) if em_cima else 0.0
    return lb >= 0.9 * larg or lb >= lc


def _direcoes(faces):
    """(caimento, cumeeira): as direções horizontais das águas (a do caimento, a da onda) e a da cumeeira"""
    aguas = [f for f in faces if f.get("tipo") == "cobertura" and f.get("inclinacao", 0.0) >= 3.0 and f.get("u")]
    if not aguas:
        return None, None
    u = aguas[0]["u"]
    h = math.hypot(u[0], u[1]) or 1.0
    uh = (u[0] / h, u[1] / h)
    return uh, (-uh[1], uh[0])


def _posicao(face: dict, direcao) -> float:
    """onde a face (de pé) fica ao longo de uma direção horizontal: o plano dela projetado"""
    n = face["normal"]
    k = n[0] * direcao[0] + n[1] * direcao[1]
    return float(face.get("plano") or 0.0) * (1.0 if k >= 0 else -1.0)


def eixo_da_face(face: dict, eixos: Optional[dict], perto: float = 1500.0) -> Optional[str]:
    """o eixo do projeto em que a fachada está (o numerado ou o com letra mais perto do plano dela, a menos de `perto`)"""
    if not eixos or face.get("tipo") == "cobertura":
        return None
    n = face["normal"]
    nh = math.hypot(n[0], n[1]) or 1.0
    melhor = None
    for fam, dir_ in (("numeros", eixos.get("eixo_g")), ("letras", eixos.get("perp_g"))):
        if not dir_ or abs((n[0] * dir_[0] + n[1] * dir_[1]) / nh) < 0.9:
            continue
        pos = _posicao(face, dir_)
        for e in eixos.get(fam) or []:
            d = abs(float(e["pos"]) - pos)
            if d < perto and (melhor is None or d < melhor[0]):
                melhor = (d, str(e["nome"]))
    return melhor[1] if melhor else None


def _centro(face: dict):
    """o meio das chapas da face no mundo (x, y): a face guarda as chapas em (p·v, p·u) e o plano em p·n"""
    pts = [q for ch in face["chapas"] for q in ch["contorno"]]
    if not pts or "v" not in face or "u" not in face:
        return None
    a = sum(q[0] for q in pts) / len(pts)
    b = sum(q[1] for q in pts) / len(pts)
    c = float(face.get("plano") or 0.0)
    v, u, n = face["v"], face["u"], face["normal"]
    return (a * v[0] + b * u[0] + c * n[0], a * v[1] + b * u[1] + c * n[1])


def _canto(face: dict, faces, cumeeira) -> Optional[str]:
    """"CANTO FRENTE DIREITA": de que lado da metade do prédio a face enviesada fica, ao longo da cumeeira e atravessado"""
    meio = _centro(face)
    centros = [c for c in (_centro(f) for f in faces if f.get("tipo") != "cobertura" and f is not face) if c]
    if meio is None or not centros:
        return None
    direita = (cumeeira[1], -cumeeira[0])
    partes = []
    for dir_, nomes in ((cumeeira, ("FRENTE", "FUNDOS")), (direita, ("ESQUERDA", "DIREITA"))):
        ps = [c[0] * dir_[0] + c[1] * dir_[1] for c in centros]
        lo, hi = min(ps), max(ps)
        if hi - lo < 1000.0:
            continue
        p = meio[0] * dir_[0] + meio[1] * dir_[1]
        partes.append(nomes[0] if p < (lo + hi) / 2.0 else nomes[1])
    return ("CANTO " + " ".join(partes)) if partes else None


def nome_do_lugar(face: dict, faces, eixos: Optional[dict] = None) -> str:
    """O lugar da face como o Fábio escreve, sem o lado: "COBERTURA – ÁGUA n", "FORRO", "OITÃO EIXO 1", "LATERAL EIXO A";
    sem eixo, "OITÃO FRENTE/FUNDOS" (pela posição ao longo da cumeeira) e "LATERAL ESQUERDA/DIREITA" (olhando da frente)."""
    lugar = lugar_da_face(face, faces)
    if lugar == "COBERTURA":
        return "COBERTURA – ÁGUA %s" % (face.get("numero") or "")
    if lugar == "FORRO":
        return "FORRO"
    tipo = {"OITÕES": "OITÃO", "LATERAIS": "LATERAL"}.get(lugar, "FACHADA")
    eixo = eixo_da_face(face, eixos)
    if eixo:
        return "%s EIXO %s" % (tipo, eixo)
    caimento, cumeeira = _direcoes(faces)
    if caimento is None:
        return "%s %s" % (tipo, face.get("numero") or "")
    if lugar == "OITÕES":
        dir_, nomes = cumeeira, ("FRENTE", "FUNDOS")
    else:
        dir_, nomes = (cumeeira[1], -cumeeira[0]), ("ESQUERDA", "DIREITA")

    def de_frente(f):
        # a fachada de frente para a direção (a enviesada, num canto, não é a frente nem os fundos)
        n_ = f["normal"]
        return abs(n_[0] * dir_[0] + n_[1] * dir_[1]) / (math.hypot(n_[0], n_[1]) or 1.0) > 0.99
    mesmas = [f for f in faces if f.get("tipo") != "cobertura" and lugar_da_face(f, faces) == lugar and de_frente(f)]
    if not de_frente(face):
        # a fachada enviesada num canto ("Oitão 9" não é lugar para o fornecedor — GESTÃO, 13/11): o canto pela posição
        # dela entre a frente e os fundos e entre a esquerda e a direita ("CANTO FRENTE DIREITA")
        canto = _canto(face, faces, cumeeira)
        return canto or "%s %s" % (tipo, face.get("numero") or "")
    if not mesmas:
        return "%s %s" % (tipo, face.get("numero") or "")
    pos = {id(f): _posicao(f, dir_) for f in mesmas}
    lo, hi = min(pos.values()), max(pos.values())
    p = pos[id(face)]
    if hi - lo < 1000.0:
        return "%s %s" % (tipo, face.get("numero") or "")
    if p - lo < 1000.0:
        return "%s %s" % (tipo, nomes[0])
    if hi - p < 1000.0:
        return "%s %s" % (tipo, nomes[1])
    return "%s %s" % (tipo, face.get("numero") or "")


def titulo_da_face(face: dict, faces=None, eixos: Optional[dict] = None) -> str:
    """O título da vista: o lugar (sem "N chapas") e, na platibanda, a externa/interna."""
    lado = {"externa": " – EXTERNA", "interna": " – INTERNA"}.get(face.get("lado") or "", "")
    return nome_do_lugar(face, faces or [face], eixos) + lado


def desenho_da_fachada(face: dict, desenho, dx: float = 0.0, dy: float = 0.0, estrutura=(), titulo: str = ""):
    """Uma face das telhas para o fornecedor (o oitão do Fábio): cada chapa é o retângulo inteiro da largura útil (980),
    no comprimento de fabricação, topo reto; dentro dela, de pé, só a cota do comprimento (a cota mede o retângulo); as
    chapas iguais e vizinhas, uma cota só. Atrás, a estrutura em unifilar. Sem nome de chapa, sem 1050, sem linha de
    recorte, sem resumo. Em tamanho real."""
    from nucleo2d.detalhe.base import _Papel, LARGURA_COMPRA_TELHA
    from nucleo2d.detalhe.telhas import _repetidas_na_fileira
    from nucleo2d.desenho import Cota
    esc = desenho.escala
    atr = {"detalhe": "fachada_fornecedor", "face": face.get("numero")}
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    chapas = [ch for ch in face["chapas"] if not ch.get("cumeeira")]
    if not chapas:
        return None
    meia = LARGURA_COMPRA_TELHA / 2.0
    retangulos = []
    for ch in chapas:
        L = float(ch["comprimento"])
        if not ch.get("alinhada", True) and not ch.get("multidobra"):
            # deitada (a onda atravessada na face): o comprimento em x
            xs_ = [q[0] for q in ch["contorno"]]
            ys_ = [q[1] for q in ch["contorno"]]
            xa, yc = min(xs_), (min(ys_) + max(ys_)) / 2.0
            retangulos.append((ch, (xa, yc - meia, xa + L, yc + meia), "h"))
        elif ch.get("multidobra"):
            # na face só aparece a reta da multidobra (o resto desce em curva): o trecho que se vê, sem cota — a medida
            # dela está no desenho da multidobra
            retangulos.append((ch, (ch["x"] - meia, ch["y0"], ch["x"] + meia, ch["y1"]), None))
        else:
            # a ponta reta fica onde está e a sobra do arredondamento vai para a ponta cortada em obra (o oitão do Fábio:
            # a base alinhada e o topo passando da linha do telhado; a platibanda interna do Depósito: o topo alinhado e
            # a base seguindo a cobertura)
            if _base_reta(ch):
                retangulos.append((ch, (ch["x"] - meia, ch["y0"], ch["x"] + meia, ch["y0"] + L), "v"))
            else:
                topo = max(q[1] for q in (ch.get("corte") or ch["contorno"]))
                retangulos.append((ch, (ch["x"] - meia, topo - L, ch["x"] + meia, topo), "v"))
    x0 = min(r[1][0] for r in retangulos)
    y0 = min(r[1][1] for r in retangulos)
    T = lambda q: (q[0] - x0, q[1] - y0)          # noqa: E731
    # a estrutura atrás (fina), recortada no tamanho da face
    xs_f = [r[1][0] for r in retangulos] + [r[1][2] for r in retangulos]
    ys_f = [r[1][1] for r in retangulos] + [r[1][3] for r in retangulos]
    caixa = (min(xs_f) - 300.0, min(ys_f) - 300.0, max(xs_f) + 300.0, max(ys_f) + 300.0)
    from nucleo2d.detalhe.telhas import _recortar
    _camada_estrutura(desenho)
    for a, b in estrutura or ():
        r = _recortar(a, b, *caixa)
        if r is not None and math.dist(*r) > 10.0:
            p.linha(*T(r[0]), *T(r[1]), CAMADA_ESTRUTURA)
    repetidas = _repetidas_na_fileira(sorted((r[0] for r in retangulos if r[2] == "v"), key=lambda c: c["x"]))
    for ch, (xa, ya, xb, yb), cotar in retangulos:
        p.polilinha([T((xa, ya)), T((xb, ya)), T((xb, yb)), T((xa, yb))], fechada=True, camada="ACO")
        if cotar is None or id(ch) in repetidas:
            continue
        if cotar == "v":
            xm = (xa + xb) / 2.0
            desenho.add(Cota(modo="v", p1=p._p(*T((xm, ya))), p2=p._p(*T((xm, yb))), deslocamento=0.0, atributos=dict(atr)))
        else:
            ym = (ya + yb) / 2.0
            desenho.add(Cota(modo="h", p1=p._p(*T((xa, ym))), p2=p._p(*T((xb, ym))), deslocamento=0.0, atributos=dict(atr)))
    alt = max(r[1][3] for r in retangulos) - y0
    p.texto(0.0, alt + 8.0 * esc, titulo or titulo_da_face(face), 4.0 * esc)
    return p.extremos


# ============================================================ corte da cobertura (D5)
#: a altura da onda da telha trapezoidal (TP40): a "espessura real" da chapa simples no corte
ONDA_TP40 = 40.0


def nucleo_do_painel(perfil: str) -> float:
    """a espessura do isolamento do painel sanduíche pelo nome ("TELHA PIR 50" → 50); 0 = chapa simples"""
    import re
    from nucleo2d.detalhe.base import PAINEL_SANDUICHE
    if not re.search(PAINEL_SANDUICHE, str(perfil or "")):
        return 0.0
    m = re.search(r"(?i)(?:PIR|PUR|EPS|sandu[ií]che?)\D{0,6}(\d{2,3})", str(perfil))
    return float(m.group(1)) if m else 30.0


def _barras_no_plano(pecas, c: dict):
    """a tesoura em unifilar (o eixo das barras no plano do corte) e as barras cortadas (terças, longarinas) como o
    retângulo da seção — sem chapa, ligação nem parafuso. ([(a, b)], [(x0, y0, x1, y1)])"""
    from nucleo2d.detalhe.base import _dot, _norm, _cruz, _marcas
    from nucleo2d.detalhe.telhas import _eh_telha, _medidas, _corte_da_malha
    n, d = c["normal"], c["plano"]
    ex = _norm(_cruz((0.0, 0.0, 1.0), n))
    eixos_l, secoes = [], []
    for e in pecas:
        V = getattr(e, "vertices", None)
        if not V or len(V) < 4 or _eh_telha(str(_marcas(e).get("perfil") or e.nome or "")):
            continue
        try:
            ce, eixos, ext = _medidas(e)
        except Exception:                     # noqa: BLE001
            continue
        if ext[0] < 200.0 or ext[0] < 3.0 * max(ext[1], 1.0):
            continue                          # chapa, parafuso, ligação
        pn = [_dot(v, n) for v in V]
        if max(pn) - min(pn) < 400.0:
            # no plano da tesoura: o eixo
            if abs(sum(pn) / len(pn) - d) > 400.0:
                continue
            a = tuple(ce[i] - eixos[0][i] * ext[0] / 2.0 for i in range(3))
            b = tuple(ce[i] + eixos[0][i] * ext[0] / 2.0 for i in range(3))
            pa, pb = (_dot(a, ex), a[2]), (_dot(b, ex), b[2])
            if math.dist(pa, pb) > 50.0:
                eixos_l.append((pa, pb))
            continue
        planos = (d, d + 300.0, d - 300.0)
        d_e = next((x for x in planos if min(pn) + 20.0 < x < max(pn) - 20.0), None)
        if d_e is None:
            continue
        ss = [((_dot(a, ex), a[2]), (_dot(b, ex), b[2])) for a, b in _corte_da_malha(e, n, d_e)]
        if not ss:
            continue
        xs = [q[0] for s_ in ss for q in s_]
        ys = [q[1] for s_ in ss for q in s_]
        if max(xs) - min(xs) < 400.0 and max(ys) - min(ys) < 400.0:
            secoes.append((min(xs), min(ys), max(xs), max(ys)))
    return eixos_l, secoes


def _offset(pts, dist):
    """a poligonal deslocada `dist` para a esquerda do sentido dela"""
    out = []
    for i, q in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        ux, uy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ux, uy) or 1.0
        out.append((q[0] - uy / L * dist, q[1] + ux / L * dist))
    return out


def desenho_do_corte(c: dict, pecas, desenho, dx: float = 0.0, dy: float = 0.0, nucleo: float = None, titulo: str = ""):
    """O corte da cobertura do fornecedor: a tesoura em unifilar, as terças cortadas como o retângulo da seção, e as
    telhas na espessura real — a chapa simples na altura da onda (duas linhas); o painel sanduíche com a chapa de cima, o
    isolamento e a chapa de baixo, e em cada emenda o cobrimento das chapas e a junta do isolamento. Sem nomes, sem
    escala. `nucleo`: a espessura do isolamento (None = pelo nome da telha; 0 = chapa simples)."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.detalhe.telhas import _agua_de, _na_agua
    from nucleo2d.desenho import Cota
    esc = desenho.escala
    atr = {"detalhe": "corte_fornecedor"}
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    eixos_l, secoes = _barras_no_plano(pecas, c)
    if nucleo is None:
        nucleo = max([nucleo_do_painel(t.get("perfil") or "") for t in c["telhas"]] + [0.0])
    xs = [q[0] for a, b in eixos_l for q in (a, b)] + [q[0] for t in c["telhas"] for s_ in t["segs"] for q in s_]
    ys = [q[1] for a, b in eixos_l for q in (a, b)] + [q[1] for t in c["telhas"] for s_ in t["segs"] for q in s_]
    if not xs:
        return None
    x0, y0 = min(xs) - 200.0, min(ys) - 200.0
    X = lambda q: (q[0] - x0, q[1] - y0)          # noqa: E731
    _camada_estrutura(desenho)
    for a, b in eixos_l:
        p.linha(*X(a), *X(b), CAMADA_ESTRUTURA)
    for (sx0, sy0, sx1, sy1) in secoes:
        p.polilinha([X((sx0, sy0)), X((sx1, sy0)), X((sx1, sy1)), X((sx0, sy1))], fechada=True, camada=CAMADA_ESTRUTURA)
    # as telhas das águas, refeitas ao longo da água (de ponta a ponta de cada uma), na espessura real; as outras
    # (fachada, platibanda, forro) como o corte do 3D
    na_agua = set()
    faixas = []                                       # (água, s0, s1) — s ao longo da água, da cumeeira para a ponta
    for ag in c["aguas"]:
        nrm = math.hypot(ag["a"], 1.0)
        u = (ag["lado"] / nrm, ag["a"] * ag["lado"] / nrm)
        x_c, y_c = c["cumeeira"]["ponto"] if c.get("cumeeira") else (ag["x_alto"], ag["a"] * ag["x_alto"] + ag["b"])
        lst = []
        for t in c["telhas"]:
            pts = [q for s_ in t["segs"] for q in s_]
            if (sum(q[0] for q in pts) / len(pts) - x_c) * ag["lado"] <= 0:
                continue
            if not all(abs(q[1] - (ag["a"] * q[0] + ag["b"])) / nrm < 150.0 for q in pts):
                continue
            if max(q[0] for q in pts) - min(q[0] for q in pts) < 300.0:
                continue
            na_agua.add(id(t))
            ss = [(q[0] - x_c) * u[0] + (q[1] - y_c) * u[1] for q in pts]
            lst.append((min(ss), max(ss)))
        # a mesma faixa duas vezes (as duas telhas vizinhas no transpasse lateral) é uma só
        unicas = []
        for v in sorted(lst):
            if not any(abs(v[0] - w[0]) < 50.0 and abs(v[1] - w[1]) < 50.0 for w in unicas):
                unicas.append(v)
        faixas += [(ag, s0, s1) for s0, s1 in unicas]
    for t in c["telhas"]:
        if id(t) in na_agua:
            continue
        for a, b in t["segs"]:
            p.linha(*X(a), *X(b), "ACO")
    for ag in c["aguas"]:
        # da cumeeira para a ponta; na emenda a de cima (mais perto da cumeeira) passa por cima da de baixo
        fx = sorted((s0, s1) for a_, s0, s1 in faixas if a_ is ag)
        for i, (s0, s1) in enumerate(fx):
            # a chapa de cima (a onda): a telha inteira; no painel sanduíche, a parte coberta pela telha de cima (o
            # cobrimento) não aparece — a chapa de cima da outra está por cima dela
            ant = fx[i - 1] if i else None
            v0 = ant[1] if (nucleo and ant is not None and s0 < ant[1] - 5.0) else s0
            topo = [X(_na_agua(c, ag, v0)), X(_na_agua(c, ag, s1))]
            base = [X(_na_agua(c, ag, v0, -ONDA_TP40)), X(_na_agua(c, ag, s1, -ONDA_TP40))]
            p.linha(*topo[0], *topo[1], "ACO")
            p.linha(*base[0], *base[1], "ACO")
            for k in (0, 1):
                p.linha(*topo[k], *base[k], "ACO")
            if not nucleo:
                continue
            # o isolamento e a chapa de baixo: na emenda terminam na junta, de topo com os da telha de baixo (o começo
            # dela); a chapa de cima segue por cima da outra — o cobrimento
            prox = fx[i + 1] if i + 1 < len(fx) else None
            emenda = prox is not None and prox[0] < s1 - 5.0
            fim = prox[0] if emenda else s1
            b0, b1 = X(_na_agua(c, ag, s0, -ONDA_TP40)), X(_na_agua(c, ag, fim, -ONDA_TP40))
            f0, f1 = X(_na_agua(c, ag, s0, -ONDA_TP40 - nucleo)), X(_na_agua(c, ag, fim, -ONDA_TP40 - nucleo))
            p.linha(*f0, *f1, "ACO")
            p.linha(*b0, *f0, "ACO")
            p.linha(*b1, *f1, "ACO")              # a junta do isolamento (ou a ponta)
            if emenda:
                a_, b_ = X(_na_agua(c, ag, prox[0])), X(_na_agua(c, ag, s1))
                desenho.add(Cota(modo="alinhada", p1=p._p(*a_), p2=p._p(*b_), deslocamento=6.0 * ag["lado"],
                                 atributos=dict(atr, cobrimento=True)))
    # a multidobra (pela regra), na altura da onda: o caminho e o mesmo caminho a 40 mm por dentro
    for m in c["multidobras"]:
        ag = _agua_de(c, m["lado"])
        nrm = math.hypot(ag["a"], 1.0)
        up = (-ag["a"] / nrm, 1.0 / nrm)
        dirv = (-m["lado"] / nrm, -ag["a"] * m["lado"] / nrm)
        Tm = m["T"]
        ang0 = math.atan2(up[1], up[0])
        ang1 = 0.0 if m["lado"] > 0 else math.pi
        if m["lado"] < 0 and ang0 < 0:
            ang0 += 2 * math.pi
        arco = [(m["C"][0] + m["R"] * math.cos(ang0 + (ang1 - ang0) * i / 24.0),
                 m["C"][1] + m["R"] * math.sin(ang0 + (ang1 - ang0) * i / 24.0)) for i in range(25)]
        caminho = [(Tm[0] + dirv[0] * m["reta"], Tm[1] + dirv[1] * m["reta"])] + arco + [(m["xv"], m["zfim"])]
        dentro = _offset(caminho, ONDA_TP40)
        if math.dist(dentro[len(dentro) // 2], m["C"]) > math.dist(caminho[len(caminho) // 2], m["C"]):
            dentro = _offset(caminho, -ONDA_TP40)
        p.polilinha([X(q) for q in caminho], camada="ACO")
        p.polilinha([X(q) for q in dentro], camada="ACO")
        for i in (0, -1):
            p.linha(*X(caminho[i]), *X(dentro[i]), "ACO")
        if m["tl_ini"] is not None and m["nome_c"]:
            # a telha reta que continua a multidobra até a cumeeira, encaixada por cima da reta dela (1 mm acima: as
            # duas chapas na onda uma da outra) — o transpasse fica entre a ponta da reta e o começo desta
            ao = lambda dd, ac=0.0: (Tm[0] + dirv[0] * dd + up[0] * ac, Tm[1] + dirv[1] * dd + up[1] * ac)   # noqa: E731
            ponto_c = (c.get("cumeeira") or {}).get("ponto")
            if ponto_c:
                fim_s = (ponto_c[0] - Tm[0]) * dirv[0] + (ponto_c[1] - Tm[1]) * dirv[1]
            else:
                fim_s = m["tl_ini"] + m["tl_comp"]
            t0, t1 = X(ao(m["tl_ini"], 1.0)), X(ao(fim_s, 1.0))
            b0, b1 = X(ao(m["tl_ini"], 1.0 - ONDA_TP40)), X(ao(fim_s, 1.0 - ONDA_TP40))
            p.linha(*t0, *t1, "ACO")
            p.linha(*b0, *b1, "ACO")
            p.linha(*t0, *b0, "ACO")
            p.linha(*t1, *b1, "ACO")
    # a cumeeira por cima das telhas: as duas pernas
    cu = c.get("cumeeira")
    if cu:
        for ag in c["aguas"]:
            p.linha(*X(_na_agua(c, ag, 0.0, 2.0)), *X(_na_agua(c, ag, cu["perna"], 2.0)), "ACO")
    alt = max(ys) - y0 + 200.0
    p.texto(0.0, alt + 8.0 * esc, titulo or "CORTE DA COBERTURA", 4.0 * esc)
    return p.extremos


# ============================================================ a relação (D7): os números do Word
def _num(v: float, casas: int = 2) -> str:
    """7331.3 → "7.331,30" (o milhar com ponto, a vírgula decimal)"""
    t = "%.*f" % (casas, v)
    inteiro, _, dec = t.partition(".")
    neg = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return ("-" if neg else "") + ".".join(grupos) + ("," + dec if dec else "")


def descricao_da_telha(perfil: str, acabamento: str = "") -> str:
    """"TELHA TP40 ESP.0.50" / "TELHA TP40 0.50MM" → "TP40-0,50mm" (+ o acabamento e a cor, quando o projeto diz)"""
    import re
    t = re.sub(r"(?i)^\s*TELHA\s+", "", str(perfil or "")).strip()
    m = re.search(r"(?i)(?:ESP\.?\s*|#\s*)?(\d+[.,]\d+)\s*(?:MM)?\s*$", t)
    if m:
        esp = m.group(1).replace(".", ",")
        nome = t[:m.start()].strip().rstrip("-").strip()
        t = "%s-%smm" % (nome, esp)
    return (t + (" " + acabamento.strip() if acabamento and acabamento.strip() else "")).strip()


def lugar_da_face(face: dict, faces) -> str:
    """O lugar da face na relação: COBERTURA, FORRO (a face quase plana em volta), LATERAIS (as fachadas de frente para o
    caimento, ao longo da cumeeira) e OITÕES (as de topo, no plano das tesouras)."""
    if face.get("tipo") == "cobertura":
        return "FORRO" if face.get("inclinacao", 90.0) < 3.0 else "COBERTURA"
    aguas = [f for f in faces if f.get("tipo") == "cobertura" and f.get("inclinacao", 0.0) >= 3.0 and f.get("u")]
    if not aguas:
        return "FECHAMENTOS"
    u = aguas[0]["u"]
    h = math.hypot(u[0], u[1]) or 1.0
    n = face["normal"]
    nh = math.hypot(n[0], n[1]) or 1.0
    return "LATERAIS" if abs((u[0] * n[0] + u[1] * n[1]) / (h * nh)) > 0.7 else "OITÕES"


#: a ordem dos lugares na relação (a do Fábio: cobertura, cumeeira, laterais, oitões, marquise)
ORDEM_LUGARES = ("COBERTURA", "FORRO", "LATERAIS", "OITÕES", "FECHAMENTOS")


def _lugar_curto(nome: str) -> str:
    """"OITÃO EIXO 1" → "Oitão eixo 1"; "LATERAL DIREITA" → "Lateral direita" (como o Fábio: "Oitão Fundos")"""
    t = str(nome or "").strip().lower()
    return t[:1].upper() + t[1:]


def medida_do_modelo(ch: dict) -> float:
    """o comprimento da chapa no modelo, antes do arredondamento da fábrica (o corte do modelo ao longo da onda)"""
    corte = ch.get("corte") or ch["contorno"]
    if ch.get("alinhada", True):
        ys = [q[1] for q in corte]
        return max(ys) - min(ys)
    xs = [q[0] for q in corte]
    return max(xs) - min(xs)


def relacao_das_telhas(faces, md: dict, acabamento: str = "", acabamentos: Optional[dict] = None,
                       eixos: Optional[dict] = None) -> list:
    """A relação de telhas no formato do Fábio, pela mesma conta do quadro das telhas (as chapas das faces): uma lista de
    blocos {"lugar", "tipos": [{"titulo", "linhas": [{"qtd", "comp" (mm), "casas", "obs", "com"}], "total" (ml ou None)}]}.
    As retas por comprimento, do maior para o menor; a multidobra no desenvolvido externo (3 casas); a cumeeira na chapa
    dela ("com 1,00m (Aba 0,50m x 0,50m)"). Sem marca, peso nem observação de corte."""
    import collections
    from nucleo2d.detalhe.base import LARGURA_COMPRA_TELHA
    util = ("%.2f" % (LARGURA_COMPRA_TELHA / 1000.0)).replace(".", ",")
    def acab(perfil):
        return (acabamentos or {}).get(str(perfil or "")) or acabamento
    por_lugar = collections.OrderedDict((k, collections.OrderedDict()) for k in ORDEM_LUGARES)
    meta = {}                                     # o título → (a forma, o perfil): a cor entra depois (com_acabamentos)
    for f in faces:
        lugar = lugar_da_face(f, faces)
        lado = {"externa": "externa", "interna": "interna"}.get(f.get("lado") or "", "")
        onde = _lugar_curto(nome_do_lugar(f, faces, eixos))
        for ch in f["chapas"]:
            if ch.get("cumeeira") or ch.get("multidobra"):
                continue
            tipo = titulo_do_tipo("TELHA", ch.get("perfil") or "", acab(ch.get("perfil")))
            meta[tipo] = ("TELHA", str(ch.get("perfil") or ""))
            g = por_lugar[lugar].setdefault(tipo, collections.OrderedDict())
            item = g.setdefault((round(float(ch["comprimento"])), lado, onde), {"qtd": 0, "modelo": []})
            item["qtd"] += 1
            item["modelo"].append(round(medida_do_modelo(ch), 1))
    blocos = []
    for lugar, tipos in por_lugar.items():
        lista = []
        for titulo, itens in tipos.items():
            # a linha é o comprimento e o lado (externa/interna); o mesmo comprimento em mais de uma linha (lados
            # diferentes, ou uma face sem lado junto de uma externa) leva o lugar de cada uma, como o Fábio ("Oitão
            # Fundos", "Oitão Frente") — senão as linhas repetidas não se distinguem (GESTÃO, 13/11)
            por_comp = collections.defaultdict(set)
            for (c, lado, onde) in itens:
                por_comp[c].add(lado)
            linhas_d = collections.OrderedDict()
            for (c, lado, onde), it in itens.items():
                obs = lado if len(por_comp[c]) == 1 else ("%s %s" % (onde, lado)).strip()
                l_ = linhas_d.setdefault((c, obs), {"qtd": 0, "comp": float(c), "casas": 2, "obs": obs, "com": "c/.", "modelo": []})
                l_["qtd"] += it["qtd"]
                l_["modelo"] += it["modelo"]
            linhas = sorted(linhas_d.values(), key=lambda l_: (-l_["comp"], l_["obs"]))
            for l_ in linhas:
                l_["modelo"] = [min(l_["modelo"]), max(l_["modelo"])]
            lista.append({"titulo": titulo, "forma": meta[titulo][0], "perfil": meta[titulo][1], "linhas": linhas,
                          "total": sum(l_["qtd"] * l_["comp"] for l_ in linhas) / 1000.0})
        if lista:
            blocos.append({"lugar": lugar + ":", "tipos": lista})
    # a cumeeira logo depois da cobertura, sem total (como o Fábio)
    cms = list(md.get("cumeeiras") or [])
    if cms:
        tipos_cm = collections.OrderedDict()
        for cm in cms:
            tit = titulo_do_tipo("CUMEEIRA", cm.get("perfil") or "", acab(cm.get("perfil")))
            meta[tit] = ("CUMEEIRA", str(cm.get("perfil") or ""))
            p1, p2 = float(cm.get("perna1") or 0.0), float(cm.get("perna2") or 0.0)
            obs = "Aba %sm x %sm" % (_num(p1 / 1000.0), _num(p2 / 1000.0))
            tipos_cm.setdefault(tit, []).append({"qtd": int(cm.get("instancias") or 0), "comp": p1 + p2, "casas": 2,
                                                 "obs": obs, "com": "com"})
        bloco_cm = {"lugar": "", "tipos": [{"titulo": t, "forma": meta[t][0], "perfil": meta[t][1], "linhas": ls, "total": None}
                                         for t, ls in tipos_cm.items()]}
        i = next((k + 1 for k, b in enumerate(blocos) if b["lugar"] == "COBERTURA:"), 0)
        blocos.insert(i, bloco_cm)
    mds = list(md.get("telhas") or [])
    if mds:
        tipos_md = collections.OrderedDict()
        for t in mds:
            tit = titulo_do_tipo("TELHA MULTIDOBRA", t.get("perfil") or "", acab(t.get("perfil")))
            meta[tit] = ("TELHA MULTIDOBRA", str(t.get("perfil") or ""))
            tipos_md.setdefault(tit, []).append({"qtd": int(t.get("instancias") or 0), "comp": float(t["desenv_ext"]), "casas": 3,
                                                 "obs": "", "com": "c/.", "multidobra": t.get("conjunto")})
        bloco_md = {"lugar": "", "tipos": [{"titulo": t, "forma": meta[t][0], "perfil": meta[t][1], "linhas": ls,
                                           "total": sum(l_["qtd"] * l_["comp"] for l_ in ls) / 1000.0}
                                         for t, ls in tipos_md.items()]}
        i = next((k + 1 for k, b in enumerate(blocos) if b["lugar"] in ("COBERTURA:", "")), 0)
        while i < len(blocos) and blocos[i]["lugar"] == "":
            i += 1
        blocos.insert(i, bloco_md)
    return blocos


def titulo_do_tipo(forma: str, perfil: str, acabamento: str = "") -> str:
    """"TELHA TP40-0,50mm pré-pintada CINZA RAL 7035 (Tamanho útil 0,98m)"; a cumeeira e a multidobra sem o tamanho útil"""
    from nucleo2d.detalhe.base import LARGURA_COMPRA_TELHA
    t = "%s %s" % (forma, descricao_da_telha(perfil, acabamento))
    if forma == "TELHA":
        t += " (Tamanho útil %sm)" % ("%.2f" % (LARGURA_COMPRA_TELHA / 1000.0)).replace(".", ",")
    return t


def perfis_da_relacao(blocos: list) -> list:
    """os tipos de telha da relação, uma vez cada ({perfil, descricao}): o que pede o acabamento e a cor (opção da obra)"""
    vistos, out = set(), []
    for b in blocos or []:
        for t in b["tipos"]:
            p = t.get("perfil")
            if p is not None and p not in vistos:
                vistos.add(p)
                out.append({"perfil": p, "descricao": descricao_da_telha(p)})
    return out


def com_acabamentos(blocos: list, acabamentos: Optional[dict]) -> list:
    """a relação com o acabamento e a cor de cada tipo de telha (as opções da obra; usuário, 13/11: "um campo por tipo de
    telha nas opções da obra, preenchido uma vez") — o título de cada tipo refeito; o tipo sem cor fica sem"""
    import copy
    out = copy.deepcopy(blocos or [])
    for b in out:
        for t in b["tipos"]:
            if t.get("forma") and t.get("perfil") is not None:
                t["titulo"] = titulo_do_tipo(t["forma"], t["perfil"], (acabamentos or {}).get(t["perfil"]) or "")
    return out


def linha_da_relacao(l_: dict) -> str:
    """{"qtd": 4, "comp": 5700, "casas": 2} → "04 pçs c/. 5,70m"; com a obs, "(…)" no fim"""
    txt = "%02d pçs %s %sm" % (int(l_["qtd"]), l_.get("com") or "c/.", _num(float(l_["comp"]) / 1000.0, int(l_.get("casas", 2))))
    return txt + (" (%s)" % l_["obs"] if l_.get("obs") else "")


def texto_da_relacao(blocos: list, obra: str = "", local: str = "", data: str = "") -> list:
    """As linhas do Word, na ordem: [(texto, estilo)] — estilo "titulo", "data", "lugar", "tipo", "linha", "total",
    "branco". O escritor do .docx põe a formatação; o teste compara o texto com o do Fábio."""
    out = [("RELAÇÃO DE TELHAS %s%s" % (obra.upper(), (" – " + local) if local else ""), "titulo")]
    if data:
        out.append((data, "data"))
    out += [("", "branco"), ("", "branco")]
    for b in blocos:
        if b["lugar"]:
            out += [(b["lugar"], "lugar"), ("", "branco")]
        for t in b["tipos"]:
            out += [(t["titulo"], "tipo"), ("", "branco")]
            out += [(linha_da_relacao(l_), "linha") for l_ in t["linhas"]]
            if t.get("total") is not None:
                out += [("", "branco"), ("Total: %sml" % _num(t["total"]), "total")]
            out += [("", "branco"), ("", "branco")]
    return out


# ============================================================ o desenho inteiro
#: o espaço entre um desenho e outro no Model (mm)
ESPACO = 2500.0
#: o nome do desenho do fornecedor no projeto (desenhos-2d/<nome>.desenho.json) — o Detalhar grava, a saída "Telhas
#: para o fornecedor" exporta (o DXF em tamanho real e a relação em Word)
NOME_DESENHO = "Telhas para o fornecedor"


def _colar(destino, fazer, x: float, y_topo: float):
    """desenha `fazer(desenho, dx, dy)` num desenho à parte, mede e cola no destino com o canto de cima à esquerda em
    (x, y_topo); devolve a altura usada"""
    from nucleo2d.desenho import Desenho, transladar
    tmp = Desenho(nome="tmp", escala=destino.escala)
    ext = fazer(tmp, 0.0, 0.0)
    if not ext or not tmp.entidades:
        return 0.0, 0.0
    x0, y0, x1, y1 = ext
    for e in tmp.entidades.values():
        destino.add(transladar(e, x - x0, y_topo - y1))
    for k, cam in tmp.camadas.items():
        destino.camadas.setdefault(k, cam)
    return x1 - x0, y1 - y0


def desenho_para_fornecedor(faces, md: dict, corte: Optional[dict], pecas, nome: str = NOME_DESENHO,
                            lugares: Optional[dict] = None, eixos: Optional[dict] = None, acabamentos: Optional[dict] = None):
    """O desenho das telhas para o fornecedor, em tamanho real (1 un = 1 mm): na primeira fileira as multidobras e a
    cumeeira, depois o corte da cobertura e, uma embaixo da outra, as faces (cobertura, laterais, oitões, forro). Os
    números são os do detalhamento das telhas; a relação vai nos metadados ("relacao"), para o Word."""
    from nucleo2d.desenho import Desenho
    d = Desenho(nome=nome, escala=ESCALA_TEXTO)
    d.metadados["fornecedor"] = {"padrao": "Fábio 13/11", "tamanho_real": True}
    y = 0.0
    x = 0.0
    alt_l = 0.0
    for t in md.get("telhas") or []:
        lugar = (lugares or {}).get(t.get("nome")) or "cobertura"
        w, h = _colar(d, lambda dd, dx, dy, t=t, lugar=lugar: desenho_da_multidobra(t, dd, dx, dy, lugar), x, y)
        x += w + ESPACO
        alt_l = max(alt_l, h)
    for cm in md.get("cumeeiras") or []:
        w, h = _colar(d, lambda dd, dx, dy, cm=cm: desenho_da_cumeeira(cm, dd, dx, dy), x, y)
        x += w + ESPACO
        alt_l = max(alt_l, h)
    if alt_l:
        y -= alt_l + ESPACO
    if corte:
        _w, h = _colar(d, lambda dd, dx, dy: desenho_do_corte(corte, pecas, dd, dx, dy), 0.0, y)
        if h:
            y -= h + ESPACO
    ordem = {k: i for i, k in enumerate(ORDEM_LUGARES)}
    for f in sorted(faces, key=lambda f: (ordem.get(lugar_da_face(f, faces), 9), f.get("numero") or 0)):
        est = estrutura_da_face(pecas, f) if pecas else []
        _w, h = _colar(d, lambda dd, dx, dy, f=f, est=est: desenho_da_fachada(f, dd, dx, dy, est, titulo_da_face(f, faces, eixos)),
                       0.0, y)
        if h:
            y -= h + ESPACO
    d.metadados["relacao"] = relacao_das_telhas(faces, md, acabamentos=acabamentos, eixos=eixos)
    return d
