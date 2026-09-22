# -*- coding: utf-8 -*-
"""Detalhamento de peças e conjuntos para produção, a partir do modelo 3D do projeto.

Entrada: o `Documento` do editor 3D (o `modelo.json` do projeto), com as peças que vieram
do IFC — cada `Solido` traz `atributos["tipo_ifc"]` (IfcPlate, IfcBeam…) e
`atributos["marcas"]` (posição e conjunto do TecnoMETAL/Tekla). Saída: desenhos 2D
(`nucleo2d.desenho.Desenho`) que vão para o CAD do projeto, no formato do desenho de
detalhamento que a fábrica usa:

* **Posições** (Part Mark): uma célula por posição, com título "P12 – 112x", perfil ou
  chapa, material e espessura, contorno com furos e cotas de fabricação; seção da barra ao
  lado; vista de topo quando há furo na mesa. As peças iguais são contadas, não repetidas.
* **Conjuntos** (Assembly Mark): elevação do conjunto (a tesoura, a viga de painel, a viga
  de rigidez), com a cadeia de cotas dos nós, comprimento e altura, título "M2 – 5x" e a
  lista de perfis que o compõem. As instâncias de um conjunto são separadas por
  conectividade espacial e contadas.
* **Regra da furação das terças** (padrão da máquina da fábrica): terça com menos de 200 mm
  de altura fura a 50 mm na vertical e 60 mm na horizontal; com 200 mm ou mais, 100 × 60.
  A regra vale para tudo o que compõe a ligação da terça (suportes, chapinhas): o que tiver
  a mesma furação original da terça recebe a mesma substituição. O centro de cada grupo de
  furos é mantido; o desenho diz que a furação segue o padrão de fábrica.

A análise geométrica de cada peça (eixos, contorno, furos, seção, comprimento, peso) é a
de `saida/detalhamento.py`; aqui ela é chamada com a malha que já está no modelo, e o
desenho sai em entidades do CAD (cota, texto, polilinha), editáveis.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo3d import geometria as _geo
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO,
                                _arestas_dos_furos, _ordem_natural, _autovetores)
from saida.desenhos import Estilo, _mm

__all__ = ["detalhar", "GRUPOS", "regra_furacao_terca"]

Ponto = Tuple[float, float, float]

#: Grupos de desenho: chave, título, escala do desenho e classes de posição que entram.
GRUPOS = collections.OrderedDict([
    ("chapas", {"titulo": "Detalhamento – chapas", "escala": 10.0,
                "classes": ("chapa", "chapa_dobrada")}),
    ("barras", {"titulo": "Detalhamento – barras e terças", "escala": 25.0,
                "classes": ("barra", "barra_conformada")}),
    ("tirantes", {"titulo": "Detalhamento – tirantes e barras redondas", "escala": 25.0,
                  "classes": ("barra_redonda",)}),
    ("telhas", {"titulo": "Detalhamento – telhas", "escala": 50.0, "classes": ("telha",)}),
    ("conjuntos", {"titulo": "Detalhamento – conjuntos", "escala": 50.0, "classes": ()}),
    ("localizacao", {"titulo": "Detalhamento – localização", "escala": 100.0, "classes": ()}),
])

TIPOS_PECA = {"IfcBeam", "IfcColumn", "IfcMember", "IfcPlate", "IfcPlateStandardCase",
              "IfcMemberStandardCase", "IfcBeamStandardCase", "IfcColumnStandardCase"}
TIPOS_ACESSORIO = {"IfcMechanicalFastener", "IfcDiscreteAccessory", "IfcFastener",
                   "IfcBuildingElementProxy"}

#: Regra da furação das terças: altura limite e (vertical, horizontal) em mm.
LIMITE_TERCA = 200.0
FURACAO_TERCA_BAIXA = (50.0, 60.0)
FURACAO_TERCA_ALTA = (100.0, 60.0)


# ============================================================ vetores
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


# ============================================================ papel
class _Papel:
    """Adapta a API de `saida.dxf.Desenho` (linha, polilinha, círculo, arco, texto, seta)
    às entidades do CAD, para reaproveitar a silhueta e os furos de `saida.detalhamento`.

    Alturas de texto chegam em mm de modelo e viram mm de papel pela escala do desenho."""
    CAMADAS = {"ACO": "VISTA", "ACO-FINO": "VISTA-FINA"}

    def __init__(self, desenho: Desenho, atributos: dict, dx: float = 0.0, dy: float = 0.0):
        self.d = desenho
        self.atr = atributos
        self.dx, self.dy = dx, dy
        self.pontos: List[Tuple[float, float]] = []

    def _p(self, x, y):
        p = (round(x + self.dx, 2), round(y + self.dy, 2))
        self.pontos.append(p)
        return p

    def _cam(self, camada):
        return self.CAMADAS.get(camada, camada)

    def linha(self, x1, y1, x2, y2, camada="ACO"):
        self.d.add(Linha(camada=self._cam(camada), a=self._p(x1, y1), b=self._p(x2, y2),
                         atributos=dict(self.atr)))

    def polilinha(self, pontos, fechada=False, camada="ACO"):
        pts = [self._p(x, y) for x, y in pontos]
        if len(pts) == 2:
            self.linha(pontos[0][0], pontos[0][1], pontos[1][0], pontos[1][1], camada)
        elif len(pts) > 2:
            self.d.add(Polilinha(camada=self._cam(camada), vertices=pts, fechada=bool(fechada),
                                 atributos=dict(self.atr)))

    def retangulo(self, x, y, larg, alt, camada="ACO"):
        self.polilinha([(x, y), (x + larg, y), (x + larg, y + alt), (x, y + alt)], True, camada)

    def circulo(self, xc, yc, raio, camada="FURO"):
        c = self._p(xc, yc)
        self._p(xc - raio, yc - raio)
        self._p(xc + raio, yc + raio)
        self.d.add(Circulo(camada=self._cam(camada), centro=c, raio=round(raio, 3),
                           atributos=dict(self.atr)))

    def arco(self, xc, yc, raio, ang_ini, ang_fim, camada="ACO"):
        c = self._p(xc, yc)
        self._p(xc - raio, yc - raio)
        self._p(xc + raio, yc + raio)
        self.d.add(Arco(camada=self._cam(camada), centro=c, raio=round(raio, 3),
                        inicio=float(ang_ini), fim=float(ang_fim), atributos=dict(self.atr)))

    def texto(self, x, y, texto, altura=2.5, camada="TEXTO", angulo=0.0, alinhamento="esquerda"):
        self.d.add(Texto(camada=self._cam(camada), posicao=self._p(x, y), texto=str(texto),
                         altura=round(altura / self.d.escala, 2), angulo=float(angulo),
                         alinhamento=alinhamento, atributos=dict(self.atr)))
        # largura estimada do texto entra nos extremos da célula, para o vizinho não
        # ser desenhado por cima do título
        larg = 0.75 * altura * len(str(texto))
        if angulo == 0.0:
            x0 = x - larg / 2 if alinhamento == "centro" else x - larg if alinhamento == "direita" else x
            self._p(x0, y)
            self._p(x0 + larg, y + altura)

    def seta(self, x, y, angulo_graus, tamanho=3.0, camada="COTA"):
        a = math.radians(angulo_graus)
        pts = [(x - tamanho * math.cos(a + 0.26), y - tamanho * math.sin(a + 0.26)), (x, y),
               (x - tamanho * math.cos(a - 0.26), y - tamanho * math.sin(a - 0.26))]
        self.polilinha(pts, False, camada)

    def solido(self, p1, p2, p3, p4=None, camada="HACHURA"):
        self.polilinha([p1, p2, p3] + ([p4] if p4 else []), True, camada)

    # cotas nativas (editáveis no CAD); afastamentos em mm de papel
    def cota_h(self, x1, x2, y, desl_papel, texto=None):
        if abs(x2 - x1) < 0.05:
            return
        self.d.add(Cota(modo="h", p1=self._p(x1, y), p2=self._p(x2, y),
                        deslocamento=float(desl_papel), texto=texto, atributos=dict(self.atr)))
        self._p(x1, y + desl_papel * self.d.escala)

    def cota_v(self, y1, y2, x, desl_papel, texto=None):
        """`desl_papel > 0` joga a cota para a direita."""
        if abs(y2 - y1) < 0.05:
            return
        self.d.add(Cota(modo="v", p1=self._p(x, y1), p2=self._p(x, y2),
                        deslocamento=-float(desl_papel), texto=texto, atributos=dict(self.atr)))
        self._p(x + desl_papel * self.d.escala, y1)

    def _cabe(self, vals) -> bool:
        """Cadeia só quando cada parcial tem espaço para o número (3 alturas de texto);
        senão os textos se atropelam e a cota total, sozinha, é mais legível."""
        minimo = 3.0 * 2.5 * self.d.escala
        return all(vals[i + 1] - vals[i] >= minimo for i in range(len(vals) - 1))

    def cadeia_h(self, xs, y, desl_papel):
        xs = sorted(set(round(x, 1) for x in xs))
        if not self._cabe(xs):
            return False
        for i in range(len(xs) - 1):
            self.cota_h(xs[i], xs[i + 1], y, desl_papel)
        return True

    def cadeia_v(self, ys, x, desl_papel):
        ys = sorted(set(round(y, 1) for y in ys))
        if not self._cabe(ys):
            return False
        for i in range(len(ys) - 1):
            self.cota_v(ys[i], ys[i + 1], x, desl_papel)
        return True

    @property
    def extremos(self):
        if not self.pontos:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in self.pontos]
        ys = [p[1] for p in self.pontos]
        return (min(xs), min(ys), max(xs), max(ys))


# ============================================================ posições
def _tipo_ifc(ent) -> str:
    return str((ent.atributos or {}).get("tipo_ifc") or "")


def _marcas(ent) -> dict:
    return (ent.atributos or {}).get("marcas") or {}


def _material(ent) -> str:
    props = (ent.atributos or {}).get("propriedades") or {}
    for pset in props.values():
        if isinstance(pset, dict):
            for k in ("Grade", "Material", "MATERIAL"):
                v = pset.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return str(getattr(ent, "material", "") or "")


def _pecas(doc: Documento):
    """Sólidos do modelo que são peças de produção, e os acessórios contados."""
    pecas, acessorios = [], collections.Counter()
    for ent in doc.entidades.values():
        if isinstance(ent, Chapa):
            if (_tipo_ifc(ent) or "IfcPlate") in TIPOS_PECA:
                try:
                    pecas.append(_proxy_da_chapa(ent))
                except Exception:                     # noqa: BLE001 — chapa degenerada não derruba o lote
                    pass
            continue
        if not isinstance(ent, Solido):
            continue
        t = _tipo_ifc(ent)
        if t in TIPOS_PECA:
            pecas.append(ent)
        elif t in TIPOS_ACESSORIO:
            acessorios[ent.nome or t] += 1
    return pecas, dict(acessorios)


def _proxy_da_chapa(ch: Chapa) -> Solido:
    """Sólido equivalente a uma Chapa paramétrica (mesmo id e atributos), com a malha
    gerada dos parâmetros; `parametrica` aponta para a chapa."""
    verts, faces = _geo.malha_chapa(ch)
    s = Solido(id=ch.id, nome=ch.nome, camada=ch.camada, material=ch.material, visivel=ch.visivel,
               bloqueada=ch.bloqueada, grupo=ch.grupo, atributos=dict(ch.atributos or {}),
               vertices=[tuple(float(x) for x in v) for v in verts], faces=[list(f) for f in faces])
    s.atributos.setdefault("tipo_ifc", "IfcPlate")
    s.parametrica = ch
    return s


def _furo_dict(f: Furo) -> dict:
    return {"tipo": f.tipo, "x": round(f.x, 3), "y": round(f.y, 3), "d": round(f.d, 3),
            "larg": round(f.larg, 3), "alt": round(f.alt, 3), "pontos": [list(p) for p in f.pontos]}


def _posicao_de_chapa(pos: Posicao, ch: Chapa):
    """Posição medida direto dos parâmetros da Chapa (contorno, espessura, furos), no
    sistema da própria chapa: é o que garante que um furo mexido no desenho volta para
    o lugar certo no 3D. O desenho parte do canto inferior esquerdo do contorno."""
    cont = [(float(x), float(y)) for x, y in (ch.contorno or [])]
    if len(cont) < 3:
        pos.classe = "indefinida"
        pos.observacoes.append("chapa sem contorno")
        return
    u0, v0 = min(x for x, _ in cont), min(y for _, y in cont)
    pos.contorno = [(x - u0, y - v0) for x, y in cont]
    pos.L = max(x for x, _ in pos.contorno)
    pos.H = max(y for _, y in pos.contorno)
    pos.T = float(ch.espessura)
    pos.espessura = pos.T
    pos.comprimento = pos.L
    pos.furos = []
    for f in ch.furos or []:
        d = float(f.get("diametro", 0) or 0)
        x, y = float(f.get("x", 0) or 0) - u0, float(f.get("y", 0) or 0) - v0
        if d > 0:
            pos.furos.append(Furo("redondo", x, y, d))
        elif float(f.get("largura", 0) or 0) > 0 and float(f.get("altura", 0) or 0) > 0:
            pos.furos.append(Furo("oblongo", x, y, larg=float(f["largura"]), alt=float(f["altura"])))
    pos.classe = "chapa"
    pos.volume = max(ch.area, 0.0) * pos.T
    pos.peso = pos.volume * RHO_ACO
    ex, ey = _norm(tuple(float(k) for k in ch.eixo_x)), _norm(tuple(float(k) for k in ch.eixo_y))
    pos.eixos = (ex, ey, _norm(_cruz(ex, ey)))
    pos.origem_chapa = (u0, v0)


def _posicoes_de(pecas: Sequence[Solido]) -> Tuple[List[Posicao], Dict[str, str]]:
    """Agrupa por posição e analisa a geometria de uma peça de cada."""
    por_marca: Dict[str, Posicao] = collections.OrderedDict()
    camadas: Dict[str, str] = {}
    for ent in pecas:
        m = _marcas(ent)
        marca = str(m.get("posicao") or ent.nome or ent.id)
        pos = por_marca.get(marca)
        if pos is None:
            t = _tipo_ifc(ent)
            pos = Posicao(marca=marca, tipo_ifc="IfcPlate" if t.startswith("IfcPlate") else t,
                          perfil=re.sub(r"\s+", " ", str(m.get("perfil") or ent.nome or "")),
                          material=_material(ent),
                          vertices=[tuple(v) for v in ent.vertices], faces=[list(f) for f in ent.faces])
            por_marca[marca] = pos
            camadas[marca] = ent.camada or ""
        pos.quantidade += 1
        pos.global_ids.append(ent.id)
        conj = str(m.get("conjunto") or "")
        if conj and conj not in pos.conjuntos:
            pos.conjuntos.append(conj)
    primeiro: Dict[str, Solido] = {}
    for ent in pecas:
        m = _marcas(ent)
        primeiro.setdefault(str(m.get("posicao") or ent.nome or ent.id), ent)
    for marca, pos in por_marca.items():
        try:
            ch = getattr(primeiro.get(marca), "parametrica", None)
            if isinstance(ch, Chapa):
                _posicao_de_chapa(pos, ch)
            else:
                analisar(pos)
        except Exception as e:                      # noqa: BLE001 — uma peça não derruba o lote
            pos.classe = "indefinida"
            pos.observacoes.append("falha na análise: %s" % e)
    return list(por_marca.values()), camadas


# ============================================================ regra das terças
def _eh_terca(pos: Posicao, camada: str) -> bool:
    """Terça: barra U/C/Z de 50 a 400 mm, comprida, que viaja solta (é o próprio conjunto —
    marca de posição igual à de conjunto). O banzo U de uma tesoura tem o mesmo perfil,
    mas pertence a um conjunto maior, e fica de fora."""
    if pos.classe != "barra":
        return False
    if re.search(r"ter[cç]a", camada or "", re.I):
        return True
    perfil_u = bool(re.match(r"^\s*(2\s*)?[CUZ]\s*\d", pos.perfil or "", re.I))
    solta = not pos.conjuntos or pos.conjuntos == [pos.marca]
    return perfil_u and solta and 50.0 <= pos.H <= 400.0 and pos.L >= 1500.0


def _eixos_da_assinatura(ass) -> Tuple[Tuple[int, float], ...]:
    """Grupo de furos sem orientação: {(n, passo)} por eixo — a chapinha do suporte tem
    a furação da terça girada de 90°."""
    nc, nl, dx, dy = ass
    return tuple(sorted(((nc, dx), (nl, dy))))


def _grupos_de_furos(furos: Sequence[Furo], raio: float = 160.0) -> List[List[Furo]]:
    """Furos redondos da vista de frente agrupados por proximidade (uma ligação cada)."""
    lista = [f for f in furos if f.vista == "frente" and f.tipo == "redondo"]
    grupos: List[List[Furo]] = []
    for f in sorted(lista, key=lambda f: (f.x, f.y)):
        for g in grupos:
            if any(math.hypot(f.x - o.x, f.y - o.y) <= raio for o in g):
                g.append(f)
                break
        else:
            grupos.append([f])
    return grupos


def _assinatura(grupo: Sequence[Furo]) -> Optional[Tuple[int, int, float, float]]:
    """(n colunas, n linhas, passo horizontal, passo vertical) de um grupo em grade."""
    xs = sorted({round(f.x, 0) for f in grupo})
    ys = sorted({round(f.y, 0) for f in grupo})
    xs2, ys2 = [xs[0]], [ys[0]]
    for x in xs[1:]:
        if x - xs2[-1] > 2.0:
            xs2.append(x)
    for y in ys[1:]:
        if y - ys2[-1] > 2.0:
            ys2.append(y)
    if len(xs2) * len(ys2) != len(grupo) or len(grupo) < 2:
        return None
    dx = (xs2[-1] - xs2[0]) / (len(xs2) - 1) if len(xs2) > 1 else 0.0
    dy = (ys2[-1] - ys2[0]) / (len(ys2) - 1) if len(ys2) > 1 else 0.0
    return (len(xs2), len(ys2), round(dx), round(dy))


def _reposicionar(grupo: Sequence[Furo], passo_h: float, passo_v: float):
    """Refaz o grupo como grade centrada no centro original, com os passos dados."""
    xs = sorted({round(f.x, 0) for f in grupo})
    ys = sorted({round(f.y, 0) for f in grupo})
    cx = sum(f.x for f in grupo) / len(grupo)
    cy = sum(f.y for f in grupo) / len(grupo)
    cols = sorted(set(xs))
    lins = sorted(set(ys))
    nc, nl = len(cols), len(lins)
    for f in grupo:
        ic = min(range(nc), key=lambda i: abs(cols[i] - f.x))
        il = min(range(nl), key=lambda i: abs(lins[i] - f.y))
        f.x = cx + (ic - (nc - 1) / 2.0) * passo_h
        f.y = cy + (il - (nl - 1) / 2.0) * passo_v


def regra_furacao_terca(posicoes: Sequence[Posicao], camadas: Dict[str, str]) -> dict:
    """Aplica a furação padrão de fábrica às terças e ao que compõe a ligação delas.

    Devolve {marca: descrição} do que mudou."""
    mudadas: Dict[str, str] = {}
    # furação original da terça, sem orientação -> quantas terças pedem cada substituição
    # (nc, nl, dx, dy, novo_h, novo_v); terças de alturas diferentes com a mesma furação
    # original pedem passos diferentes, e o suporte segue a maioria, com aviso
    assinaturas: Dict[tuple, collections.Counter] = collections.defaultdict(collections.Counter)
    tercas = [p for p in posicoes if _eh_terca(p, camadas.get(p.marca, ""))]
    for pos in tercas:
        passo_v, passo_h = FURACAO_TERCA_BAIXA if pos.H < LIMITE_TERCA else FURACAO_TERCA_ALTA
        alterou = []
        for g in _grupos_de_furos(pos.furos):
            ass = _assinatura(g)
            if ass is None:
                continue
            nc, nl, dx, dy = ass
            novo_h = passo_h if nc > 1 else 0.0
            novo_v = passo_v if nl > 1 else 0.0
            if (nc > 1 and abs(dx - novo_h) > 0.5) or (nl > 1 and abs(dy - novo_v) > 0.5):
                assinaturas[_eixos_da_assinatura(ass)][(nc, nl, dx, dy, novo_h, novo_v)] += pos.quantidade
                _reposicionar(g, novo_h, novo_v)
                alterou.append("%dx%d %s x %s -> %s x %s" % (nc, nl, _mm(dx), _mm(dy), _mm(novo_h), _mm(novo_v)))
        if alterou:
            txt = "furacao no padrao de fabrica (%s x %s mm): %s" % (
                _mm(passo_h), _mm(passo_v), "; ".join(sorted(set(alterou))))
            pos.observacoes.append(txt)
            mudadas[pos.marca] = txt
    # o que compõe a ligação (suporte, chapinha): mesma furação original que alguma terça,
    # em qualquer orientação; cada eixo recebe o passo novo do eixo da terça com o mesmo
    # (n furos, passo original). Padrão quadrado (80 × 80) é ambíguo e fica anotado.
    for pos in posicoes:
        if pos.marca in mudadas or pos.classe == "indefinida":
            continue
        alterou = []
        for g in _grupos_de_furos(pos.furos):
            ass = _assinatura(g)
            if ass is None:
                continue
            opcoes = assinaturas.get(_eixos_da_assinatura(ass))
            if not opcoes:
                continue
            nc_t, nl_t, dx_t, dy_t, novo_h_t, novo_v_t = opcoes.most_common(1)[0][0]
            nc, nl, dx, dy = ass
            mapa = {(nc_t, dx_t): novo_h_t, (nl_t, dy_t): novo_v_t}
            ambiguo = (nc_t, dx_t) == (nl_t, dy_t) or len(opcoes) > 1
            novo_h = mapa.get((nc, dx), 0.0) if nc > 1 else 0.0
            novo_v = mapa.get((nl, dy), 0.0) if nl > 1 else 0.0
            if (nc_t, dx_t) == (nl_t, dy_t):    # padrão quadrado: mesma orientação da terça
                novo_h, novo_v = novo_h_t, novo_v_t
            _reposicionar(g, novo_h, novo_v)
            alterou.append("%dx%d %s x %s -> %s x %s%s" % (nc, nl, _mm(dx), _mm(dy), _mm(novo_h), _mm(novo_v),
                                                          " (conferir: orientacao ou terca de outra altura)" if ambiguo else ""))
        if alterou:
            txt = "furacao no padrao de fabrica (ligacao de terca): %s" % "; ".join(sorted(set(alterou)))
            pos.observacoes.append(txt)
            mudadas[pos.marca] = txt
    return mudadas


# ============================================================ célula da posição
def _rotulo_espessura(pos: Posicao) -> str:
    t = pos.espessura or pos.T
    pol = t / 25.4
    for den in (16, 8, 4, 2):
        n = round(pol * den)
        if n and abs(n / den - pol) < 0.04:
            g = math.gcd(n, den)
            return '#%d/%d"' % (n // g, den // g) if den // g > 1 else '#%d"' % (n // g)
    return "#%s mm" % _mm(t, 1)


def _cabecalho(pos: Posicao) -> List[str]:
    linhas = ["%s – %02dx" % (pos.marca, pos.quantidade)]
    if pos.classe == "chapa_dobrada" and pos.desenvolvimento:
        linhas.append("%s  %s  %s  desenv. %s x %s mm" % (pos.perfil, _rotulo_espessura(pos), pos.material,
                                                          _mm(pos.desenvolvimento[0]), _mm(pos.desenvolvimento[1])))
    elif pos.classe in ("chapa", "chapa_dobrada"):
        linhas.append("%s  %s  %s" % (pos.perfil, _rotulo_espessura(pos), pos.material))
    elif pos.classe == "barra_conformada":
        linhas.append("%s  L desenv. %s mm  %s" % (pos.perfil, _mm(pos.comprimento), pos.material))
    elif pos.classe == "indefinida":
        linhas.append(pos.perfil)
    else:
        linhas.append("%s  L = %s mm  %s" % (pos.perfil, _mm(pos.comprimento), pos.material))
    detalhes = []
    if pos.furos:
        detalhes.append(pos.rotulo_furos())
    if pos.peso:
        detalhes.append("%s kg/pç  total %s kg" % (_mm(pos.peso, 2), _mm(pos.peso_total, 1)))
    if detalhes:
        linhas.append("  ".join(detalhes))
    if pos.conjuntos and pos.conjuntos != [pos.marca]:
        linhas.append("conj. " + ", ".join(pos.conjuntos[:6]) + (" …" if len(pos.conjuntos) > 6 else ""))
    return linhas


def _furos_editaveis(p: "_Papel", atr: dict, furos: Sequence[Furo]):
    """Cada furo é uma entidade só (círculo ou polilinha fechada) marcada com `furo`:
    mover, apagar ou desenhar outra na camada FURO é o que "Aplicar furos ao 3D" lê."""
    for i, f in enumerate(furos):
        p.atr = dict(atr, furo=i, tipo_furo=f.tipo)
        if f.tipo == "redondo":
            p.circulo(f.x, f.y, f.d / 2, "FURO")
        elif f.tipo == "oblongo":
            p.atr.update(larg=f.larg, alt=f.alt)
            p.polilinha(_geo.contorno_oblongo(f.x, f.y, f.larg, f.alt), fechada=True, camada="FURO")
        elif f.pontos:
            p.polilinha(list(f.pontos), fechada=True, camada="FURO")
    p.atr = atr


def desenho_da_posicao(pos: Posicao, desenho: Desenho, dx: float, dy: float,
                       editavel: bool = False) -> Tuple[float, float, float, float]:
    """Célula da posição em `desenho`, com a vista de frente em (dx, dy). Devolve os
    extremos. `editavel`: furos da chapa como entidades marcadas (ver _furos_editaveis)."""
    atr = {"posicao": pos.marca, "perfil": pos.perfil, "classe": pos.classe, "detalhe": "posicao"}
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    est = Estilo(escala=esc)
    off, off2, off3 = 10.0, 20.0, 30.0            # mm de papel
    if pos.classe == "indefinida":
        p.texto(0, 0, "%s – %02dx  %s  (sem geometria reconhecida)" % (pos.marca, pos.quantidade, pos.perfil), 3.0 * esc)
        return p.extremos
    L, H = pos.L, pos.H
    furos_frente = [f for f in pos.furos if f.vista == "frente"]
    furos_topo = [f for f in pos.furos if f.vista == "topo"]

    if pos.classe == "chapa":
        p.polilinha(pos.contorno, fechada=True, camada="ACO")
        if editavel:
            _furos_editaveis(p, atr, furos_frente)
        else:
            _desenhar_furos(p, est, furos_frente, 0, 0)
    else:
        ignorar = _arestas_dos_furos(pos, 2, +1.0, (0, 1)) if furos_frente else set()
        _vista(p, pos, (0, 1), 2, +1.0, 0, 0, ignorar)
        _desenhar_furos(p, est, furos_frente, 0, 0)
    # cotas: cadeia dos furos junto da peça, total mais afastada
    xs = sorted({round(f.x, 1) for f in furos_frente})
    ys = sorted({round(f.y, 1) for f in furos_frente})
    cadeia = bool(xs) and p.cadeia_h([0.0] + xs + [L], 0, -off)
    p.cota_h(0, L, 0, -(off2 if cadeia else off))
    cadeia = bool(ys) and p.cadeia_v([0.0] + ys + [H], L, off)
    p.cota_v(0, H, L, off2 if cadeia else off)

    x_dir = L + (off3 + off) * esc
    if pos.classe in ("barra", "barra_redonda", "telha") and pos.secao:
        w_min = min(q[1] for l in pos.secao for q in l)
        w_max = max(q[1] for l in pos.secao for q in l)
        for laco in pos.secao:
            p.polilinha([(x_dir + (w - w_min), v) for v, w in laco], fechada=True, camada="ACO")
        p.cota_h(x_dir, x_dir + (w_max - w_min), 0, -off)
        p.cota_v(0, H, x_dir + (w_max - w_min), off)
        p.texto(x_dir, H + 3.0 * esc, "SEÇÃO", 2.0 * esc)
    if pos.classe == "chapa_dobrada" and pos.local:
        w_min = min(q[2] for q in pos.local)
        _vista(p, pos, (2, 1), 0, +1.0, x_dir - w_min, 0)
        p.cota_h(x_dir, x_dir + pos.T, 0, -off)
        if pos.desenvolvimento:
            # planificação: retângulo largura × desenvolvimento, à direita da vista lateral
            larg_d, comp_d = pos.desenvolvimento
            x_pl = x_dir + pos.T + (off3 + off) * esc
            p.retangulo(x_pl, 0, comp_d, larg_d, "ACO-FINO")
            p.cota_h(x_pl, x_pl + comp_d, 0, -off)
            p.cota_v(0, larg_d, x_pl + comp_d, off)
            p.texto(x_pl, larg_d + 3.0 * esc, "DESENVOLVIMENTO (linha média)", 2.0 * esc)
    if (furos_topo or pos.vista_topo or pos.classe == "barra_conformada") and pos.local:
        w_min = min(q[2] for q in pos.local)
        w_max = max(q[2] for q in pos.local)
        y_topo = -((off3 + off) * esc + (w_max - w_min) + (w_min if w_min > 0 else 0))
        ignorar_t = _arestas_dos_furos(pos, 1, -1.0, (0, 2)) if furos_topo else set()
        _vista(p, pos, (0, 2), 1, -1.0, 0, y_topo, ignorar_t)
        _desenhar_furos(p, est, furos_topo, 0, y_topo)
        if furos_topo:
            p.cadeia_h([0.0] + sorted({round(f.x, 1) for f in furos_topo}) + [L], y_topo + w_min, -off)
        p.cota_v(y_topo + w_min, y_topo + w_max, L, off)

    # título acima da peça
    y = H + (off + 2.0) * esc
    linhas = _cabecalho(pos)
    obs = pos.observacoes[:3]
    for i, txt in enumerate(reversed(obs)):
        p.texto(0, y + i * 3.2 * esc, "* " + txt, 2.0 * esc)
    y += len(obs) * 3.2 * esc
    for i, txt in enumerate(reversed(linhas)):
        alt = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt * esc)
        y += (alt + 1.2) * esc
    return p.extremos


# ============================================================ detalhe de uma posição
def detalhar_posicao(doc: Documento, marca: str, editavel: bool = True) -> Tuple[Desenho, Posicao]:
    """Desenho "Detalhe – <marca>" com a célula da posição. Chapa paramétrica sai com os
    furos editáveis e `metadados.detalhe_posicao` guarda o que "Aplicar furos" precisa."""
    pecas, _ = _pecas(doc)
    lista = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) == marca]
    if not lista:
        raise ErroDeDados("não há peça com a posição %s no modelo." % marca)
    posicoes, camadas = _posicoes_de(lista)
    pos = posicoes[0]
    escala = {"chapa": 10.0, "chapa_dobrada": 10.0, "telha": 50.0}.get(pos.classe, 25.0)
    d = Desenho(nome="Detalhe – %s" % marca, escala=escala)
    parametrica = all(isinstance(getattr(e, "parametrica", None), Chapa) for e in lista)
    edit = bool(editavel and parametrica and pos.classe == "chapa")
    ext = desenho_da_posicao(pos, d, 0.0, 0.0, editavel=edit)
    d.metadados["celulas"] = [[round(v, 1) for v in ext]]
    d.metadados["detalhamento"] = {
        "grupo": "posicao", "posicoes": [marca],
        "itens": {marca: {"quantidade": pos.quantidade, "perfil": pos.perfil, "material": pos.material,
                          "comprimento": round(pos.comprimento), "espessura": round(pos.espessura or pos.T, 1),
                          "peso": round(pos.peso, 2), "classe": CLASSES.get(pos.classe, pos.classe),
                          "categoria": _categoria(pos, camadas.get(marca, ""))}}}
    d.metadados["detalhe_posicao"] = {
        "marca": marca, "classe": pos.classe, "editavel": edit, "parametrica": parametrica,
        "L": round(pos.L, 3), "H": round(pos.H, 3), "T": round(pos.T, 3),
        "pecas": [e.id for e in lista],
        "furos": [_furo_dict(f) for f in pos.furos if f.vista == "frente"]}
    return d, pos


def converter_chapas(doc: Documento, marca: str) -> int:
    """Sólidos de chapa plana (IfcPlate) da posição viram entidades Chapa paramétricas —
    mesmo id, nome, camada e atributos; contorno, espessura e furos medidos da malha, no
    sistema da própria peça. Devolve quantas foram convertidas."""
    n = 0
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Solido) or _tipo_ifc(ent) != "IfcPlate":
            continue
        m = _marcas(ent)
        if str(m.get("posicao") or ent.nome or ent.id) != marca:
            continue
        pos = Posicao(marca=marca, tipo_ifc="IfcPlate", perfil=re.sub(r"\s+", " ", str(m.get("perfil") or ent.nome or "")),
                      material=_material(ent), vertices=[tuple(v) for v in ent.vertices], faces=[list(f) for f in ent.faces])
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "chapa" or not pos.contorno or not pos.eixos:
            continue
        e1, e2, e3 = pos.eixos
        c, _ = _autovetores(pos.vertices)
        P = [(_dot(_sub(v, c), e1), _dot(_sub(v, c), e2), _dot(_sub(v, c), e3)) for v in pos.vertices]
        u0, v0 = min(q[0] for q in P), min(q[1] for q in P)
        w0 = (min(q[2] for q in P) + max(q[2] for q in P)) / 2
        base = w0 - pos.T / 2
        origem = tuple(c[i] + e1[i] * u0 + e2[i] * v0 + e3[i] * base for i in range(3))
        furos = []
        for f in pos.furos:
            if f.vista != "frente":
                continue
            if f.tipo == "redondo":
                furos.append({"x": round(f.x, 3), "y": round(f.y, 3), "diametro": round(f.d, 3)})
            elif f.tipo == "oblongo":
                furos.append({"x": round(f.x, 3), "y": round(f.y, 3), "largura": round(f.larg, 3), "altura": round(f.alt, 3)})
        atributos = dict(ent.atributos or {})
        atributos["convertida_de"] = "solido"
        ch = Chapa(id=ent.id, nome=ent.nome, camada=ent.camada, material=ent.material, visivel=ent.visivel,
                   bloqueada=ent.bloqueada, grupo=ent.grupo, atributos=atributos,
                   origem=tuple(round(x, 3) for x in origem), eixo_x=tuple(round(x, 6) for x in e1),
                   eixo_y=tuple(round(x, 6) for x in e2),
                   contorno=[(round(x, 3), round(y, 3)) for x, y in pos.contorno],
                   espessura=round(pos.T, 3), centrada=False, furos=furos, aco=ent.material or _material(ent))
        doc.entidades[ent.id] = ch
        n += 1
    return n


def _simetria(originais, atuais, L: float, H: float, tol: float = 1.5):
    """Transformação (x, y) → (x', y') do sistema do desenho para o da chapa: a mesma
    posição pode estar montada espelhada, e a análise de cada peça escolhe os eixos
    por si; a que leva os furos originais do desenho sobre os furos atuais da peça é
    a certa. Sem furos para comparar, identidade."""
    cands = [lambda x, y: (x, y), lambda x, y: (L - x, y), lambda x, y: (x, H - y), lambda x, y: (L - x, H - y)]
    if not originais or len(originais) != len(atuais):
        return cands[0]
    for f in cands:
        mapeados = [f(x, y) for x, y in originais]
        if all(min(math.hypot(mx - ax, my - ay) for ax, ay in atuais) <= tol for mx, my in mapeados):
            return f
    return cands[0]


def aplicar_furos(doc: Documento, marca: str, furos: Sequence[dict], originais: Sequence[dict]) -> dict:
    """Escreve nas chapas paramétricas da posição os furos vindos do desenho de detalhe
    (coordenadas do desenho: canto inferior esquerdo do contorno = 0,0)."""
    chapas = [e for e in doc.entidades.values() if isinstance(e, Chapa)
              and str(_marcas(e).get("posicao") or e.nome or e.id) == marca]
    if not chapas:
        raise ErroDeDados("a posição %s não tem chapa paramétrica no modelo (abra o detalhe pela peça no 3D primeiro)." % marca)
    orig = [(float(f["x"]), float(f["y"])) for f in originais]
    for ch in chapas:
        cont = [(float(x), float(y)) for x, y in (ch.contorno or [])]
        u0, v0 = min(x for x, _ in cont), min(y for _, y in cont)
        L, H = max(x for x, _ in cont) - u0, max(y for _, y in cont) - v0
        atuais = [(float(f.get("x", 0) or 0) - u0, float(f.get("y", 0) or 0) - v0) for f in (ch.furos or [])]
        mapa = _simetria(orig, atuais, L, H)
        novos = []
        for f in furos:
            x, y = mapa(float(f["x"]), float(f["y"]))
            reg = {"x": round(x + u0, 3), "y": round(y + v0, 3)}
            if f.get("tipo") == "oblongo" and float(f.get("larg", 0) or 0) > 0:
                reg.update(largura=round(float(f["larg"]), 3), altura=round(float(f.get("alt", 0) or 0), 3))
            else:
                reg["diametro"] = round(float(f.get("d", 0) or 0), 3)
            if reg.get("diametro", 0) > 0 or reg.get("largura", 0) > 0:
                novos.append(reg)
        ch.furos = novos
    return {"chapas": len(chapas), "furos": len(furos)}


def furos_do_desenho(d: Desenho) -> List[dict]:
    """Os furos de um desenho de detalhe editável: círculos e polilinhas fechadas da
    camada FURO (as marcadas com `furo` e as que o usuário desenhou depois)."""
    fora = []
    for e in d.entidades.values():
        if getattr(e, "camada", "") != "FURO":
            continue
        a = e.atributos or {}
        if isinstance(e, Circulo):
            fora.append({"tipo": "redondo", "x": e.centro[0], "y": e.centro[1], "d": 2 * e.raio})
        elif isinstance(e, Polilinha) and e.fechada and len(e.vertices) >= 3:
            xs = [p[0] for p in e.vertices]
            ys = [p[1] for p in e.vertices]
            larg, alt = max(xs) - min(xs), max(ys) - min(ys)
            cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            if a.get("tipo_furo") == "oblongo" or abs(larg - alt) > 0.5:
                fora.append({"tipo": "oblongo", "x": cx, "y": cy, "larg": float(a.get("larg") or larg), "alt": float(a.get("alt") or alt)})
            else:
                fora.append({"tipo": "redondo", "x": cx, "y": cy, "d": (larg + alt) / 2})
    return fora


# ============================================================ conjuntos
def _caixa(ent: Solido):
    vs = ent.vertices
    return tuple((min(v[i] for v in vs), max(v[i] for v in vs)) for i in range(3))


def _instancias(pecas: Sequence[Solido], folga: float = 8.0) -> List[List[Solido]]:
    """Separa as peças de um conjunto em instâncias por conectividade das caixas."""
    caixas = [_caixa(e) for e in pecas]
    n = len(pecas)
    pai = list(range(n))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    ordem = sorted(range(n), key=lambda i: caixas[i][0][0])
    for a in range(n):
        i = ordem[a]
        for b in range(a + 1, n):
            j = ordem[b]
            if caixas[j][0][0] - folga > caixas[i][0][1]:
                break
            ci, cj = caixas[i], caixas[j]
            if all(ci[k][0] - folga <= cj[k][1] and cj[k][0] - folga <= ci[k][1] for k in range(3)):
                pai[raiz(i)] = raiz(j)
    grupos = collections.defaultdict(list)
    for i in range(n):
        grupos[raiz(i)].append(pecas[i])
    return sorted(grupos.values(), key=lambda g: (min(_caixa(e)[0][0] for e in g), min(_caixa(e)[0][1] for e in g)))


def _multiplo(grupo: Sequence[Solido], unidade: collections.Counter) -> int:
    """k quando a composição do grupo é exatamente k × unidade; senão 0."""
    cont = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in grupo)
    if set(cont) != set(unidade) or not unidade:
        return 0
    ks = {cont[m] / unidade[m] for m in unidade}
    if len(ks) != 1:
        return 0
    k = next(iter(ks))
    return int(k) if k == int(k) and k >= 1 else 0


def _dividir(grupo: Sequence[Solido], k: int, unidade: collections.Counter) -> List[List[Solido]]:
    """Separa um grupo com k unidades encostadas (águas de um pórtico na cumeeira) em k
    partes de mesmo tamanho ao longo do eixo mais comprido do grupo; devolve as partes só
    quando cada uma tem a composição unitária, senão lista vazia."""
    if k <= 1 or len(grupo) % k:
        return []
    verts = [v for e in grupo for v in e.vertices]
    c, pca = _autovetores(verts)
    e1 = pca[0]

    def t_de(e):
        ce = [sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)]
        return _dot(_sub(ce, c), e1)
    ordenado = sorted(grupo, key=t_de)
    tam = len(grupo) // k
    partes = [ordenado[i * tam:(i + 1) * tam] for i in range(k)]
    if all(collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in p) == unidade for p in partes):
        return partes
    return []


def _centro(grupo: Sequence[Solido]):
    vs = [v for e in grupo for v in e.vertices]
    return tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))


def _instancias_do_conjunto(lista: Sequence[Solido], unidade: collections.Counter, folga: float = 60.0) -> List[List[Solido]]:
    """Instâncias de um conjunto: grupos por conectividade das caixas; grupo com k unidades
    encostadas é dividido; fragmentos (composição contida na unitária, mas incompleta —
    a chapinha que não encosta em nada) juntam-se ao fragmento mais próximo enquanto a
    soma couber na composição unitária."""
    def comp(g):
        return collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in g)

    def cabe(c):
        return all(unidade.get(k, 0) >= q for k, q in c.items())
    grupos: List[List[Solido]] = []
    for g in _instancias(lista, folga=folga):
        k = _multiplo(g, unidade)
        partes = _dividir(g, k, unidade) if k > 1 else []
        grupos.extend(partes or [g])
    completos = [g for g in grupos if comp(g) == unidade or not cabe(comp(g))]
    frag = [g for g in grupos if comp(g) != unidade and cabe(comp(g))]
    centros = [_centro(g) for g in frag]
    comps = [comp(g) for g in frag]
    for _ in range(len(frag)):
        melhor = None
        for i in range(len(frag)):
            for j in range(i + 1, len(frag)):
                if not cabe(comps[i] + comps[j]):
                    continue
                d = sum((centros[i][k] - centros[j][k]) ** 2 for k in range(3))
                if melhor is None or d < melhor[0]:
                    melhor = (d, i, j)
        if melhor is None:
            break
        _, i, j = melhor
        frag[i] = frag[i] + frag[j]
        comps[i] = comps[i] + comps[j]
        centros[i] = _centro(frag[i])
        del frag[j], comps[j], centros[j]
    return completos + frag


def _eixos_do_conjunto(pecas: Sequence[Solido]):
    """(centro, u, v, w): w é a direção de menor espalhamento (normal da elevação), v o
    mais vertical dos outros dois eixos, u = v × w."""
    verts = [v for e in pecas for v in e.vertices]
    c, pca = _autovetores(verts)
    # Convenção do gerador de vistas (Vista.eixos): observador em -w, direita = w × v.
    # Aqui u é escolhido primeiro e w = v × u fecha o triedro nessa convenção.
    ext = []
    for e_ in pca:
        ts = [_dot(_sub(p, c), e_) for p in verts]
        ext.append(max(ts) - min(ts))

    def para_direita(u):
        return (-u[0], -u[1], -u[2]) if (u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0)) else u
    z = (0.0, 0.0, 1.0)
    # conjunto linear (tirante com as chapinhas, viga de uma barra): sai deitado na
    # horizontal, para o comprimento total ser lido direto
    if ext[0] > 0 and ext[1] < 0.12 * ext[0]:
        u = para_direita(pca[0])
        if abs(pca[2][2]) > 0.8 and abs(u[2]) < 0.3:
            # deitado no plano horizontal (tirante de cobertura com as chapinhas): visto de cima
            w = (0.0, 0.0, -1.0)
            v = _norm(_cruz(u, w))
            return c, u, v, w
        if abs(_dot(u, z)) < 0.95:
            v = _norm(tuple(z[i] - _dot(z, u) * u[i] for i in range(3)))
        else:
            v = _norm(tuple(pca[1][i] - _dot(pca[1], u) * u[i] for i in range(3)))
        w = _norm(_cruz(v, u))
        return c, u, v, w
    # a normal da vista é o eixo mais fino do conjunto; a vertical do desenho é a
    # vertical da obra projetada nesse plano — a tesoura sai inclinada como está
    # montada, o pilar em pé. Conjunto deitado no plano horizontal (contraventamento
    # de cobertura) não tem vertical: o eixo mais comprido vai para a horizontal.
    w = pca[2]
    if abs(w[2]) > 0.8:
        u = para_direita(pca[0])
        v = _norm(_cruz(w, u))
        if v[1] < 0 and abs(v[1]) > abs(v[0]):
            v = (-v[0], -v[1], -v[2])
        w = _norm(_cruz(v, u))
        return c, u, v, w
    v = _norm(tuple(z[i] - _dot(z, w) * w[i] for i in range(3)))
    u = para_direita(_norm(_cruz(v, w)))
    w = _norm(_cruz(v, u))
    return c, u, v, w


def _eixo_da_peca(ent: Solido):
    """Extremos do eixo de uma barra (PCA) em 3D, ou None para chapas."""
    verts = ent.vertices
    if len(verts) < 4:
        return None
    c, pca = _autovetores(verts)
    e1 = pca[0]
    ts = [_dot(_sub(v, c), e1) for v in verts]
    return (tuple(c[i] + e1[i] * min(ts) for i in range(3)), tuple(c[i] + e1[i] * max(ts) for i in range(3)))


def _assinatura_conjunto(instancia: Sequence[Solido]) -> tuple:
    """Composição + extensões principais + posição relativa de cada peça (a 10 mm):
    conjuntos com marcas diferentes e assinatura igual são o mesmo detalhe."""
    verts = [v for e in instancia for v in e.vertices]
    c, pca = _autovetores(verts)
    ext = []
    for e_ in pca:
        ts = [_dot(_sub(v, c), e_) for v in verts]
        ext.append(round((max(ts) - min(ts)) / 10.0))
    pecas = []
    for e in instancia:
        m = _marcas(e)
        ce = [sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)]
        d = _sub(ce, c)
        pecas.append((str(m.get("posicao") or e.nome), round(abs(_dot(d, pca[0])) / 10.0), round(abs(_dot(d, pca[1])) / 10.0)))
    return (tuple(ext), tuple(sorted(pecas)))


def _sobrepoe(a, b, folga=0.0) -> bool:
    return a[0] < b[2] + folga and b[0] < a[2] + folga and a[1] < b[3] + folga and b[1] < a[3] + folga


def _rotular_barras(p: "_Papel", rotulos, esc: float, altura_papel: float = 1.8):
    """Rótulo de posição ao lado do meio de cada barra, deslocado na perpendicular da
    barra; quando cai em cima de outro rótulo, afasta-se mais um passo (até quatro)."""
    h = altura_papel * esc
    caixas = []
    for txt, (x, y), ang in rotulos:
        a = ang if ang <= 90 else ang - 180
        ra = math.radians(a)
        nx, ny = -math.sin(ra), math.cos(ra)
        larg = 0.75 * h * len(txt)
        meia = max(larg, h) / 2
        caixa = None
        for passo in range(4):
            d = (1.6 + 2.4 * passo) * esc
            cx, cy = x + nx * d, y + ny * d
            caixa = (cx - meia, cy - h / 2, cx + meia, cy + h / 2)
            if not any(_sobrepoe(caixa, cb, 0.3 * h) for cb in caixas):
                break
        caixas.append(caixa)
        p.texto(cx, cy - h / 2, txt, h, "TEXTO", angulo=a, alinhamento="centro")


def desenho_do_conjunto(doc: Documento, marca: str, instancia: Sequence[Solido], n_instancias: int,
                        desenho: Desenho, dx: float, dy: float, rotular: bool = True) -> Tuple[float, float, float, float]:
    """Elevação do conjunto com cotas de nós, título e lista de perfis, em (dx, dy)."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    # observador em -w (convenção do motor de vistas): origem atrás de tudo
    ws = [_dot(_sub(p, c), w) for e in instancia for p in e.vertices]
    origem = tuple(c[i] + w[i] * (min(ws) - 10.0) for i in range(3))
    vista = _vistas.Vista(origem=origem, normal=w, acima=v, profundidade=None, cortar=False,
                          entidades=[e.id for e in instancia], rotular=False,
                          nome="Conjunto %s" % marca, tipo="conjunto")
    u, v, w = vista.eixos()          # exatamente os eixos com que a vista é desenhada
    antes = set(desenho.entidades)
    _vistas.gerar(doc, vista, desenho, (dx, dy))
    info = desenho.vistas[-1]
    larg, alt = info["largura"], info["altura"]
    novas = [desenho.entidades[k] for k in desenho.entidades if k not in antes]
    for e in novas:
        e.atributos["conjunto"] = marca
        e.atributos["detalhe"] = "conjunto"
    # extremos reais em (u, v) do que foi desenhado: canto inferior esquerdo = (dx, dy)
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in instancia for p in e.vertices]
    u0, v0 = min(us), min(vs)
    atr = {"conjunto": marca, "detalhe": "conjunto"}
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, off2 = 10.0, 20.0
    # eixos das barras em (u, v); banzos são as barras quase horizontais e compridas
    barras = []
    rotulos = []
    for e in instancia:
        if _tipo_ifc(e).startswith("IfcPlate"):
            continue
        eixo = _eixo_da_peca(e)
        if not eixo:
            continue
        a, b = eixo
        pa = (_dot(_sub(a, origem), u) - u0, _dot(_sub(a, origem), v) - v0)
        pb = (_dot(_sub(b, origem), u) - u0, _dot(_sub(b, origem), v) - v0)
        comp = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if comp < 40.0:
            continue
        ang = abs(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))) % 180
        barras.append((pa, pb, comp, ang))
        m = _marcas(e)
        if rotular and m.get("posicao"):
            rotulos.append((m["posicao"], ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), ang))
    banzos = [b for b in barras if (b[3] < 25.0 or b[3] > 155.0) and b[2] > 0.25 * larg]
    diagonais = [b for b in barras if b not in banzos]
    # nós: interseção do eixo de cada diagonal/montante com o eixo de cada banzo, perto da
    # ponta da diagonal (a ponta em si é cortada em ângulo e cai fora do nó)
    nos_baixo, nos_cima = {0.0, larg}, {0.0, larg}
    alturas = {0.0, alt}

    def intersecao(p1, p2, q1, q2):
        d1 = (p2[0] - p1[0], p2[1] - p1[1])
        d2 = (q2[0] - q1[0], q2[1] - q1[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            return None
        t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
        return (p1[0] + d1[0] * t, p1[1] + d1[1] * t), t
    v_medio = sum((b[0][1] + b[1][1]) / 2 for b in banzos) / len(banzos) if banzos else alt / 2
    for pa, pb, comp, ang in diagonais:
        for qa, qb, _, _ in banzos:
            r = intersecao(pa, pb, qa, qb)
            if r is None:
                continue
            (x, y), t = r
            if -0.15 <= t <= 1.15 and min(qa[0], qb[0]) - 50 <= x <= max(qa[0], qb[0]) + 50:
                em_cima = (qa[1] + qb[1]) / 2 > v_medio
                (nos_cima if em_cima else nos_baixo).add(round(x, 1))
    for qa, qb, _, _ in banzos:
        for q in (qa, qb):
            alturas.add(round(q[1], 1))

    def fundir(vals, tol=60.0, fixos=()):
        """Nós a menos de `tol` viram um só, na média: as duas diagonais que chegam ao mesmo
        nó cruzam o eixo do banzo com alguns centímetros de excentricidade. Os extremos
        (0 e o comprimento) não se movem."""
        vals = sorted(vals)
        grupos = [[vals[0]]]
        for x in vals[1:]:
            if x - grupos[-1][-1] > tol:
                grupos.append([x])
            else:
                grupos[-1].append(x)
        fora = []
        for g in grupos:
            fixo = [x for x in g if x in fixos]
            fora.append(fixo[0] if fixo else round(sum(g) / len(g), 1))
        return fora
    nos_baixo = fundir(nos_baixo, fixos=(0.0, larg))
    nos_cima = fundir(nos_cima, fixos=(0.0, larg))
    alturas = fundir(alturas, tol=30.0, fixos=(0.0, alt))
    cadeia = len(nos_baixo) > 2 and p.cadeia_h(nos_baixo, 0, -off)
    p.cota_h(0, larg, 0, -(off2 if cadeia else off))
    cadeia_cima = len(nos_cima) > 2 and nos_cima != nos_baixo and p.cadeia_h(nos_cima, alt, off)
    cadeia = len(alturas) > 2 and p.cadeia_v(alturas, larg, off)
    p.cota_v(0, alt, larg, off2 if cadeia else off)
    _rotular_barras(p, rotulos, esc)
    # título e lista de perfis
    comp = collections.Counter()
    perfis = collections.Counter()
    for e in instancia:
        m = _marcas(e)
        comp[str(m.get("posicao") or e.nome)] += 1
        perfis[str(m.get("perfil") or e.nome)] += 1
    y = alt + ((off2 if cadeia_cima else off) + 2.0) * esc
    lista = ["%s x%d" % (k, n) for k, n in sorted(perfis.items(), key=lambda kv: (-kv[1], _ordem_natural(kv[0])))]
    posic = ["%s x%d" % (k, n) for k, n in sorted(comp.items(), key=lambda kv: _ordem_natural(kv[0]))]

    def quebrar(prefixo, itens, largura=64):
        fora, atual = [], prefixo
        for it in itens:
            if len(atual) + len(it) + 2 > largura and atual != prefixo:
                fora.append(atual.rstrip(", "))
                atual = " " * len(prefixo)
            atual += it + ", "
        fora.append(atual.rstrip(", "))
        return fora
    linhas = ["%s – %02dx" % (marca, n_instancias)] + quebrar("Perfis: ", lista) + quebrar("Posicoes: ", posic)
    for i, txt in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt_t * esc)
        y += (alt_t + 1.2) * esc
    ext = p.extremos
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


# ============================================================ localização
def _casco(pts: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Casco convexo 2D (cadeia monótona de Andrew)."""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) <= 2:
        return pts

    def cruz2(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo: List[Tuple[float, float]] = []
    for p in pts:
        while len(baixo) >= 2 and cruz2(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    cima: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(cima) >= 2 and cruz2(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


def _itens_de_localizacao(pecas: Sequence[Solido]) -> List[Tuple[str, List[Solido]]]:
    """(rótulo, peças) por instância de conjunto; peça solta (marca = conjunto, ou sem
    conjunto) vale por si."""
    por_conj: Dict[str, List[Solido]] = collections.OrderedDict()
    soltas: List[Solido] = []
    for e in pecas:
        m = _marcas(e)
        conj = str(m.get("conjunto") or "")
        pos = str(m.get("posicao") or "")
        if conj and conj != pos:
            por_conj.setdefault(conj, []).append(e)
        else:
            soltas.append(e)
    itens: List[Tuple[str, List[Solido]]] = []
    for conj, lista in por_conj.items():
        total = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in lista)
        n = 0
        for q in total.values():
            n = math.gcd(n, q)
        n = max(n, 1)
        unidade = collections.Counter({k: q // n for k, q in total.items()})
        for g in _instancias_do_conjunto(lista, unidade):
            itens.append((conj, g))
    for e in soltas:
        m = _marcas(e)
        itens.append((str(m.get("posicao") or e.nome or ""), [e]))
    return itens


#: Item menor que isto (chapinha solta, conjunto de chapas) não ganha marca na planta.
MENOR_ITEM_LOCALIZACAO = 500.0


def desenho_de_localizacao(doc: Documento, pecas: Sequence[Solido], titulo: str = "Detalhamento – localização",
                           ignorar: Sequence[str] = ()) -> Desenho:
    """Planta e duas elevações esquemáticas do modelo inteiro (cada peça é o contorno
    convexo da sua projeção, em linha fina) com a marca de cada conjunto e de cada peça
    solta escrita no lugar em que está montada: é a planta de montagem que diz onde vai
    cada item detalhado. `ignorar`: marcas de posição que ficam fora (telhas)."""
    from nucleo2d.pranchas import escala_normalizada
    fora = set(ignorar or ())
    pecas = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome) not in fora]
    if not pecas:
        raise ErroDeDados("sem peças para localizar.")
    itens = _itens_de_localizacao(pecas)
    todos = [v for e in pecas for v in e.vertices]
    minimo = [min(v[i] for v in todos) for i in range(3)]
    maximo = [max(v[i] for v in todos) for i in range(3)]
    ext = [maximo[i] - minimo[i] for i in range(3)]
    # a planta fica com o lado comprido na horizontal; a elevação longitudinal embaixo
    # dela partilha o eixo horizontal; a transversal vai à direita
    comprido_em_y = ext[1] > ext[0]
    if comprido_em_y:
        # de cima (observador em +z, w = -z): direita = y, cima do papel = -x
        u_pl, v_pl, w_pl = (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)      # vista de +x
        u_tr, v_tr, w_tr = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
    else:
        u_pl, v_pl, w_pl = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)
        u_lo, v_lo, w_lo = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)       # vista de -y
        u_tr, v_tr, w_tr = (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)      # vista de -x
    vistas = [("PLANTA DE LOCALIZAÇÃO", "topo", u_pl, v_pl, w_pl),
              ("ELEVAÇÃO LONGITUDINAL", "frente", u_lo, v_lo, w_lo),
              ("ELEVAÇÃO TRANSVERSAL", "lateral", u_tr, v_tr, w_tr)]

    def extensao(u, v):
        us = [_dot(p, u) for p in todos]
        vs = [_dot(p, v) for p in todos]
        return max(us) - min(us), max(vs) - min(vs)
    l_pl, a_pl = extensao(u_pl, v_pl)
    l_lo, a_lo = extensao(u_lo, v_lo)
    l_tr, a_tr = extensao(u_tr, v_tr)
    folga_papel = 45.0
    # papel útil de uma A1 deitada, descontados carimbo e margens
    esc = escala_normalizada(max((l_pl + folga_papel * 0 + max(l_tr, 0.0)) / 760.0,
                                 (a_pl + a_lo + 2 * folga_papel) / 520.0, 1.0))
    d = Desenho(nome=titulo, escala=esc)
    folga = folga_papel * esc
    atr_base = {"detalhe": "localizacao"}
    h_txt = 2.5 * esc
    posicoes_vistas = [(0.0, a_lo + folga), (0.0, 0.0), (l_lo + folga, 0.0)]
    for (nome, tipo, u, v, w), (x0, y0) in zip(vistas, posicoes_vistas):
        us = [_dot(p, u) for p in todos]
        vs = [_dot(p, v) for p in todos]
        u0, v0 = min(us), min(vs)
        p = _Papel(d, dict(atr_base, vista=nome), x0, y0)
        n_pecas = 0
        # contornos
        for e in pecas:
            pts = [(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices]
            casco = _casco(pts)
            if len(casco) >= 3:
                m = _marcas(e)
                atr = dict(atr_base, vista=nome, origem=e.id, nome=e.nome or "")
                if m.get("posicao"):
                    atr["posicao"] = str(m["posicao"])
                if m.get("conjunto"):
                    atr["conjunto"] = str(m["conjunto"])
                pp = _Papel(d, atr, x0, y0)
                pp.polilinha(casco, fechada=True, camada="ACO-FINO")
                p.pontos.extend(pp.pontos)
                n_pecas += 1
        # rótulos no centro de cada item; quem está de topo (extensão projetada pequena
        # perante a extensão 3D) não é rotulado nesta vista
        caixas = []
        rotulos = []
        for rotulo, lista in itens:
            if not rotulo:
                continue
            vv = [q for e in lista for q in e.vertices]
            pu = [_dot(q, u) - u0 for q in vv]
            pv = [_dot(q, v) - v0 for q in vv]
            ext3 = max(max(q[i] for q in vv) - min(q[i] for q in vv) for i in range(3))
            ext2 = max(max(pu) - min(pu), max(pv) - min(pv))
            if ext3 < MENOR_ITEM_LOCALIZACAO or (ext3 > 0 and ext2 < 0.3 * ext3):
                continue
            rotulos.append((rotulo, (sum(pu) / len(pu), sum(pv) / len(pv))))
        rotulos.sort(key=lambda r: (r[1][1], r[1][0]))
        postos: List[Tuple[str, float, float]] = []
        for rotulo, (cx, cy) in rotulos:
            # a mesma marca já escrita ali perto (terças vistas de ponta, uma sobre a
            # outra) não se repete
            if any(t == rotulo and math.hypot(cx - x_, cy - y_) < 6.0 * h_txt for t, x_, y_ in postos):
                continue
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
            postos.append((rotulo, cx, cy))
            p.texto(cx, caixa[1], rotulo, h_txt, "TEXTO", alinhamento="centro")
        larg_v, alt_v = max(us) - u0, max(vs) - v0
        p.cota_h(0, larg_v, 0, -10.0)
        p.cota_v(0, alt_v, larg_v, 10.0)
        p.texto(0, -(10.0 + 8.0) * esc, nome, 3.5 * esc)
        p.texto(0, -(10.0 + 8.0 + 4.5) * esc, "escala 1:%s · marcas de conjunto no lugar de montagem; peça solta com a própria marca" % (int(esc) if float(esc).is_integer() else esc), 2.0 * esc)
        ext_c = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext_c])
        d.vistas.append({"origem": [minimo[0], minimo[1], minimo[2]], "normal": list(w), "acima": list(v),
                         "profundidade": None, "cortar": False, "entidades": None, "rotular": True,
                         "nome": nome, "tipo": tipo, "pecas_cortadas": 0, "pecas_projetadas": n_pecas,
                         "largura": round(larg_v, 1), "altura": round(alt_v, 1), "canto": [x0, y0], "avisos": []})
    d.metadados["detalhamento"] = {"grupo": "localizacao", "posicoes": [], "itens": {}}
    return d


# ============================================================ montagem
#: Quadros das pranchas, na ordem em que aparecem.
CATEGORIAS = collections.OrderedDict([
    ("TESOURAS", "Tesouras e pórticos"), ("CONJUNTOS", "Conjuntos menores"), ("TERÇAS", "Terças"),
    ("BARRAS", "Barras"), ("CHAPAS", "Chapas"), ("TIRANTES", "Tirantes e barras redondas"),
    ("TELHAS", "Telhas"), ("VISTAS", "Vistas e cortes"), ("OUTROS", "Outros"),
])


def _categoria(pos: Posicao, camada: str) -> str:
    if pos.classe in ("chapa", "chapa_dobrada"):
        return "CHAPAS"
    if pos.classe == "telha":
        return "TELHAS"
    if pos.classe == "barra_redonda" or (pos.classe == "barra_conformada" and _eh_redonda_perfil(pos.perfil)):
        return "TIRANTES"
    if _eh_terca(pos, camada):
        return "TERÇAS"
    return "BARRAS"


def _eh_redonda_perfil(perfil: str) -> bool:
    return bool(re.search(r"FE\s*RED|BARRA\s*ROSC|REDOND|\bFR\b|Ø\s*\d|VERG", perfil or "", re.I))


def _ordenar(posicoes: Sequence[Posicao]) -> List[Posicao]:
    ordem = {c: i for i, c in enumerate(CLASSES)}
    return sorted(posicoes, key=lambda p: (ordem.get(p.classe, 99), _ordem_natural(p.perfil), _ordem_natural(p.marca)))


def _mover(e, dx: float, dy: float):
    """Translada uma entidade do CAD no lugar."""
    mv = lambda p: (round(p[0] + dx, 2), round(p[1] + dy, 2))    # noqa: E731
    if isinstance(e, Linha):
        e.a, e.b = mv(e.a), mv(e.b)
    elif isinstance(e, Polilinha):
        e.vertices = [mv(p) for p in e.vertices]
    elif isinstance(e, (Circulo, Arco)):
        e.centro = mv(e.centro)
    elif isinstance(e, Texto):
        e.posicao = mv(e.posicao)
    elif isinstance(e, Cota):
        e.p1, e.p2 = mv(e.p1), mv(e.p2)
    elif hasattr(e, "contornos"):
        e.contornos = [[mv(p) for p in c] for c in e.contornos]
    elif hasattr(e, "alvo"):
        e.alvo, e.posicao = mv(e.alvo), mv(e.posicao)


def _empilhar(desenho: Desenho, celulas, largura_max_papel: float = 800.0):
    """Coloca células (função que desenha em (dx, dy) e devolve extremos) em prateleiras.

    Medir antes de desenhar não dá (o título e as cotas só existem depois), então cada
    célula é desenhada na posição corrente e, se estourar a largura da prateleira, o que
    acabou de ser desenhado é movido para o começo da prateleira de baixo."""
    esc = desenho.escala
    largura_max = largura_max_papel * esc
    folga = 12.0 * esc
    x = y = 0.0                # y é o canto inferior esquerdo da peça; a linha desce daí
    fundo_linha = 0.0          # quanto a prateleira atual desce abaixo de y (cotas)
    limite = None              # topo permitido para a linha atual (fundo da linha de cima − folga)
    chaves_linha: List[str] = []
    celulas_meta = desenho.metadados.setdefault("celulas", [])
    inicio_linha = len(celulas_meta)
    for desenhar in celulas:
        antes = set(desenho.entidades)
        ext = desenhar(x, y)
        novas = [k for k in desenho.entidades if k not in antes]
        if x > 0 and ext[2] > largura_max:
            limite = y - fundo_linha - folga
            novo_y = limite - (ext[3] - y)       # título desta célula sob as cotas da linha de cima
            ddx, ddy = -x, novo_y - y
            for k in novas:
                _mover(desenho.entidades[k], ddx, ddy)
            ext = (ext[0] + ddx, ext[1] + ddy, ext[2] + ddx, ext[3] + ddy)
            x, y = 0.0, novo_y
            fundo_linha = 0.0
            chaves_linha = []
            inicio_linha = len(celulas_meta)
        elif limite is not None and ext[3] > limite + 1e-6:
            # esta célula é mais alta que a primeira da linha: a linha inteira desce
            ddy = limite - ext[3]
            for k in chaves_linha + novas:
                _mover(desenho.entidades[k], 0.0, ddy)
            for i in range(inicio_linha, len(celulas_meta)):
                celulas_meta[i][1] = round(celulas_meta[i][1] + ddy, 1)
                celulas_meta[i][3] = round(celulas_meta[i][3] + ddy, 1)
            ext = (ext[0], ext[1] + ddy, ext[2], ext[3] + ddy)
            y += ddy                             # fundo_linha é relativo a y e não muda
        chaves_linha.extend(novas)
        x = ext[2] + folga
        fundo_linha = max(fundo_linha, y - ext[1])
        celulas_meta.append([round(v, 1) for v in ext])
    return desenho


def levantar(doc: Documento, regra_tercas: bool = True, avisar=None) -> dict:
    """Só o levantamento: as peças de produção do modelo agrupadas em posições, com a
    geometria analisada e a regra das terças aplicada — sem desenhar nada. É o que a
    lista de materiais usa. Devolve {"pecas", "acessorios", "posicoes", "camadas",
    "regra_tercas", "categorias": {marca: categoria}}."""
    avisar = avisar or (lambda *a: None)
    pecas, acessorios = _pecas(doc)
    if not pecas:
        raise ErroDeDados("o modelo não tem peças com marcas de IFC (IfcBeam, IfcPlate…) para detalhar.")
    posicoes, camadas = _posicoes_de(pecas)
    avisar("%d peças em %d posições" % (len(pecas), len(posicoes)))
    mudadas = regra_furacao_terca(posicoes, camadas) if regra_tercas else {}
    return {"pecas": pecas, "acessorios": acessorios, "posicoes": posicoes, "camadas": camadas,
            "regra_tercas": mudadas,
            "categorias": {p.marca: _categoria(p, camadas.get(p.marca, "")) for p in posicoes}}


def detalhar(doc: Documento, grupos: Optional[Sequence[str]] = None, regra_tercas: bool = True,
             rotular: bool = True, avisar=None) -> dict:
    """Gera os desenhos de detalhamento do modelo. Devolve
    {"desenhos": {chave: Desenho}, "posicoes": [...], "conjuntos": [...], "acessorios": {},
     "regra_tercas": {marca: texto}, "avisos": [...]}."""
    avisar = avisar or (lambda *a: None)
    grupos = list(grupos or GRUPOS.keys())
    lev = levantar(doc, regra_tercas=regra_tercas, avisar=avisar)
    pecas, acessorios, posicoes, camadas, mudadas = (lev["pecas"], lev["acessorios"], lev["posicoes"],
                                                     lev["camadas"], lev["regra_tercas"])
    desenhos: Dict[str, Desenho] = collections.OrderedDict()
    avisos: List[str] = []

    for chave in grupos:
        g = GRUPOS.get(chave)
        if not g or chave in ("conjuntos", "localizacao"):
            continue
        lista = [p for p in _ordenar(posicoes) if p.classe in g["classes"]]
        if not lista:
            continue
        d = Desenho(nome=g["titulo"], escala=g["escala"])
        d.metadados["detalhamento"] = {
            "grupo": chave, "posicoes": [p.marca for p in lista],
            # o que a tabela de posições da prancha lista para cada célula
            "itens": {p.marca: {"quantidade": p.quantidade, "perfil": p.perfil, "material": p.material,
                                "comprimento": round(p.comprimento), "espessura": round(p.espessura or p.T, 1),
                                "peso": round(p.peso, 2), "classe": CLASSES.get(p.classe, p.classe),
                                "categoria": _categoria(p, camadas.get(p.marca, ""))}
                      for p in lista}}
        celulas = [(lambda x, y, p=p: desenho_da_posicao(p, d, x, y)) for p in lista]
        _empilhar(d, celulas)
        desenhos[chave] = d

    conjuntos_info = []
    if "conjuntos" in grupos:
        por_conj: Dict[str, List[Solido]] = collections.defaultdict(list)
        for e in pecas:
            conj = str(_marcas(e).get("conjunto") or "")
            if conj:
                por_conj[conj].append(e)
        classe_de = {p.marca: p.classe for p in posicoes}
        candidatos = []
        for conj, lista in por_conj.items():
            total = collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in lista)
            # instâncias iguais: o máximo divisor comum das quantidades por posição
            # (8 pórticos M2 = 80 P10, 64 P11, 64 P12, 56 P4 → mdc 8)
            n = 0
            for q in total.values():
                n = math.gcd(n, q)
            n = max(n, 1)
            unidade = collections.Counter({k: q // n for k, q in total.items()})
            # conjuntos de uma peça só (terça = marca) não são elevação: já estão nas
            # posições; telhas também não
            if sum(unidade.values()) < 2 or all(classe_de.get(k) == "telha" for k in unidade):
                continue
            # a instância desenhada: um agrupamento espacial com exatamente a composição
            # unitária; sem um, o conjunto inteiro quando n = 1, senão o maior agrupamento
            insts = _instancias_do_conjunto(lista, unidade)
            inst = next((i for i in insts if collections.Counter(
                str(_marcas(e).get("posicao") or e.nome) for e in i) == unidade), None)
            aviso = ""
            if inst is None:
                inst = lista if n == 1 else max(insts, key=len)
                aviso = ("conjunto %s: %d instâncias pela composição, mas nenhum agrupamento "
                         "espacial bate com a composição unitária; desenhado o maior" % (conj, n))
            candidatos.append((conj, lista, inst, n, unidade, aviso))
        candidatos.sort(key=lambda c: (-len(c[1]), _ordem_natural(c[0])))
        # marcas diferentes com a mesma geometria (o TecnoMETAL numera por pórtico) viram
        # uma célula só: "M17 / M46 – 08x"
        por_assinatura: Dict[tuple, list] = collections.OrderedDict()
        for cand in candidatos:
            por_assinatura.setdefault(_assinatura_conjunto(cand[2]), []).append(cand)
        if candidatos:
            g = GRUPOS["conjuntos"]
            d = Desenho(nome=g["titulo"], escala=g["escala"])
            celulas = []
            for grupo in por_assinatura.values():
                conj, lista, inst, n, unidade, aviso = grupo[0]
                marcas = sorted((c[0] for c in grupo), key=_ordem_natural)
                total_inst = sum(c[3] for c in grupo)
                total_pecas = sum(len(c[1]) for c in grupo)
                rotulo = " / ".join(marcas)
                celulas.append((lambda x, y, rotulo=rotulo, inst=inst, n=total_inst:
                                desenho_do_conjunto(doc, rotulo, inst, n, d, x, y, rotular)))
                conjuntos_info.append({"marca": rotulo, "marcas": marcas, "pecas": total_pecas, "instancias": total_inst,
                                       "iguais": not aviso, "composicao": dict(unidade),
                                       "categoria": "TESOURAS" if sum(q for k, q in unidade.items() if classe_de.get(k, "").startswith("barra")) >= 8 else "CONJUNTOS"})
                for c in grupo:
                    if c[5]:
                        avisos.append(c[5])
                if len(marcas) > 1:
                    avisos.append("conjuntos %s têm a mesma geometria: detalhados numa célula só (%d no total)" % (", ".join(marcas), total_inst))
            _empilhar(d, celulas, largura_max_papel=1400.0)
            d.metadados["detalhamento"] = {
                "grupo": "conjuntos", "conjuntos": [c["marca"] for c in conjuntos_info],
                "itens": {c["marca"]: {"quantidade": c["instancias"], "perfil": "conjunto de %d peças" % sum(c["composicao"].values()),
                                       "material": "", "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                                       "categoria": c["categoria"], "marcas": c["marcas"]}
                          for c in conjuntos_info}}
            desenhos["conjuntos"] = d

    if "localizacao" in grupos:
        try:
            desenhos["localizacao"] = desenho_de_localizacao(doc, pecas, GRUPOS["localizacao"]["titulo"],
                                                             ignorar=[p.marca for p in posicoes if p.classe == "telha"])
        except ErroDeDados as e:
            avisos.append("planta de localização não gerada: %s" % e)

    resumo_pos = []
    for p in _ordenar(posicoes):
        resumo_pos.append({"marca": p.marca, "classe": CLASSES.get(p.classe, p.classe), "perfil": p.perfil,
                           "material": p.material, "quantidade": p.quantidade, "comprimento": round(p.comprimento),
                           "largura": round(p.H), "espessura": round(p.espessura or p.T, 1), "furos": p.rotulo_furos(),
                           "peso": round(p.peso, 3), "peso_total": round(p.peso_total, 2),
                           "conjuntos": list(p.conjuntos), "observacoes": list(p.observacoes)})
    return {"desenhos": desenhos, "posicoes": resumo_pos, "conjuntos": conjuntos_info,
            "acessorios": acessorios, "regra_tercas": mudadas, "avisos": avisos,
            "peso_total": round(sum(p.peso_total for p in posicoes), 1),
            "objetos_posicoes": posicoes, "objetos_pecas": pecas, "camadas": camadas}
