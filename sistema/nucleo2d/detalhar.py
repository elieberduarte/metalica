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
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
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

    def __init__(self, desenho: Desenho, atributos: dict, dx: float = 0.0, dy: float = 0.0, camada_peca: str = ""):
        self.d = desenho
        self.atr = atributos
        self.dx, self.dy = dx, dy
        self.pontos: List[Tuple[float, float]] = []
        self.camada_peca = camada_peca          # TERCAS, DIAGONAIS…: o traço forte da peça vai nela
        if camada_peca:
            _registrar_camadas_de_pecas(desenho)

    def _p(self, x, y):
        p = (round(x + self.dx, 2), round(y + self.dy, 2))
        self.pontos.append(p)
        return p

    def _cam(self, camada):
        if camada == "ACO" and self.camada_peca:
            return self.camada_peca
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
        # a fábrica não trabalha com décimos: os extremos da cota vão ao milímetro
        # inteiro (o desvio de até 0,5 mm em relação ao traço não se vê no papel)
        x1, x2 = float(round(x1)), float(round(x2))
        if abs(x2 - x1) < 0.05:
            return
        self.d.add(Cota(modo="h", p1=self._p(x1, y), p2=self._p(x2, y),
                        deslocamento=float(desl_papel), texto=texto, atributos=dict(self.atr)))
        self._p(x1, y + desl_papel * self.d.escala)

    def cota_v(self, y1, y2, x, desl_papel, texto=None):
        """`desl_papel > 0` joga a cota para a direita."""
        y1, y2 = float(round(y1)), float(round(y2))
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

    def cadeia_alinhada(self, linha, xs, desl_papel, exigir_espaco=True):
        """Cadeia de cotas ao longo da reta `linha` = (a, b) (o banzo inclinado): cada
        nó de abscissa x vai para o ponto da reta nessa abscissa e a cota é a distância
        medida na própria reta, ao milímetro — o que a produção marca no banzo.
        `desl_papel > 0` joga a cota para a esquerda do sentido a→b (acima, quando a reta
        vai para a direita)."""
        (ax, ay), (bx, by) = linha
        dx, dy = bx - ax, by - ay
        comp = math.hypot(dx, dy)
        if comp < 1e-6:
            return self.cadeia_h(xs, ay, desl_papel)
        ux, uy = dx / comp, dy / comp
        ts = sorted(set(float(round((x - ax) / ux)) for x in xs)) if abs(ux) > 1e-9 else []
        if len(ts) < 2 or (exigir_espaco and not self._cabe(ts)):
            return False
        for i in range(len(ts) - 1):
            p1 = (ax + ux * ts[i], ay + uy * ts[i])
            p2 = (ax + ux * ts[i + 1], ay + uy * ts[i + 1])
            self.d.add(Cota(modo="alinhada", p1=self._p(*p1), p2=self._p(*p2),
                            deslocamento=float(desl_papel), atributos=dict(self.atr)))
            self._p(p1[0] - uy * desl_papel * self.d.escala, p1[1] + ux * desl_papel * self.d.escala)
        return True

    def cadeia_h(self, xs, y, desl_papel, exigir_espaco=True):
        """Cadeia de cotas. Sem `exigir_espaco`, trechos curtos demais para o número
        saem em duas linhas alternadas (os textos não se atropelam); devolve "dupla"."""
        xs = sorted(set(float(round(x)) for x in xs))
        if exigir_espaco and not self._cabe(xs):
            return False
        dupla = not self._cabe(xs)
        for i in range(len(xs) - 1):
            self.cota_h(xs[i], xs[i + 1], y, desl_papel * (2 if dupla and i % 2 else 1))
        return "dupla" if dupla else True

    def cadeia_v(self, ys, x, desl_papel, exigir_espaco=True):
        ys = sorted(set(float(round(y)) for y in ys))
        if exigir_espaco and not self._cabe(ys):
            return False
        dupla = not self._cabe(ys)
        for i in range(len(ys) - 1):
            self.cota_v(ys[i], ys[i + 1], x, desl_papel * (2 if dupla and i % 2 else 1))
        return "dupla" if dupla else True

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


#: Camadas do desenho por tipo de peça — a mesma paleta das camadas do modelo 3D (chapas
#: douradas, vigas/terças azuis, tirantes verdes, pilares cinza), com tons que se leem nos
#: dois temas do CAD; banzos, diagonais e montantes ganham cores próprias.
CAMADAS_PECAS = collections.OrderedDict([
    ("TERCAS", ("#3b82f6", 0.35)), ("BANZOS", ("#22a7c2", 0.35)), ("DIAGONAIS", ("#e67e22", 0.35)),
    ("MONTANTES", ("#a855f7", 0.35)), ("CHAPAS", ("#d4a017", 0.35)), ("TIRANTES", ("#2eaf63", 0.35)),
    ("PILARES", ("#8b95a5", 0.35)), ("VIGAS", ("#5b7db1", 0.35)), ("TELHAS", ("#9aa4b2", 0.25)),
])


def _registrar_camadas_de_pecas(d: Desenho):
    from nucleo2d.desenho import Camada2D
    for nome, (cor, esp) in CAMADAS_PECAS.items():
        if nome not in d.camadas:
            d.camadas[nome] = Camada2D(nome, cor, espessura=esp)


def _classificar_pecas_do_conjunto(instancia: Sequence[Solido], eixos=None) -> Dict[str, str]:
    """{id da peça: camada} numa instância de conjunto: chapas, pilares e redondos pelo
    tipo; barras pela posição na elevação — banzo (quase horizontal e comprida),
    montante (quase vertical) ou diagonal. `eixos` = (u, v, origem) da vista; sem eles,
    os eixos do conjunto."""
    if eixos is None:
        c, u, v, w = _eixos_do_conjunto(instancia)
        u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
        origem = c
    else:
        u, v, origem = eixos
    fora: Dict[str, str] = {}
    barras = []
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    larg = (max(us) - min(us)) if us else 0.0
    for e in instancia:
        t = _tipo_ifc(e)
        perfil = str(_marcas(e).get("perfil") or e.nome or "")
        if t.startswith("IfcPlate") or isinstance(getattr(e, "parametrica", None), Chapa):
            fora[e.id] = "CHAPAS"
        elif _eh_redonda_perfil(perfil):
            fora[e.id] = "TIRANTES"
        else:
            # IfcColumn não quer dizer pilar: o TecnoMETAL exporta montantes e diagonais
            # assim; o que decide é a posição da barra na elevação
            eixo = _eixo_da_peca(e)
            if not eixo:
                fora[e.id] = "VIGAS"
                continue
            a, b = eixo
            pa = (_dot(_sub(a, origem), u), _dot(_sub(a, origem), v))
            pb = (_dot(_sub(b, origem), u), _dot(_sub(b, origem), v))
            comp = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            ang = abs(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))) % 180
            barras.append((e.id, comp, ang))
    for eid, comp, ang in barras:
        if (ang < 25.0 or ang > 155.0) and comp > 0.25 * larg:
            fora[eid] = "BANZOS"
        elif 75.0 <= ang <= 105.0:
            fora[eid] = "MONTANTES"
        else:
            fora[eid] = "DIAGONAIS"
    return fora


def _camada_da_posicao(pos: Posicao, tipo: str, votos: Optional[Dict[str, collections.Counter]] = None) -> str:
    """Camada 2D de uma posição: pelo tipo de produção (terça, tirante, chapa, telha) ou,
    para a barra de conjunto, pelo que ela é na elevação (banzo, diagonal, montante —
    a classificação mais votada entre as instâncias); pilar do IFC é PILARES."""
    if pos.classe in ("chapa", "chapa_dobrada"):
        return "CHAPAS"
    if pos.classe == "telha":
        return "TELHAS"
    if tipo in ("contraventamento", "barra_roscada", "gancho") or pos.classe == "barra_redonda" or (pos.classe == "barra_conformada" and _eh_redonda_perfil(pos.perfil)):
        return "TIRANTES"
    if tipo in ("terca_cobertura", "terca_marquise"):
        return "TERCAS"
    if votos:
        for m in marcas_de(pos):
            if votos.get(m):
                return votos[m].most_common(1)[0][0]
    # barra solta em pé e comprida é pilar (IfcColumn sozinho não basta: o TecnoMETAL
    # exporta montantes de tesoura como IfcColumn)
    if pos.eixos and abs(pos.eixos[0][2]) > 0.7 and pos.comprimento >= 1500.0:
        return "PILARES"
    return "VIGAS"


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
            "larg": round(f.larg, 3), "alt": round(f.alt, 3), "pontos": [list(p) for p in f.pontos],
            "vista": f.vista}


def _furo_de_dict(f: dict) -> Furo:
    return Furo(str(f.get("tipo") or "redondo"), float(f.get("x", 0) or 0), float(f.get("y", 0) or 0),
                float(f.get("d", 0) or 0), float(f.get("larg", 0) or 0), float(f.get("alt", 0) or 0),
                [tuple(p) for p in (f.get("pontos") or [])], str(f.get("vista") or "frente"))


# ============================================================ furos pelos parafusos
#: Porca sextavada: entre faces (mm) → rosca métrica.
_PORCAS = ((10, 6), (13, 8), (16, 10), (18, 12), (19, 12), (21, 14), (24, 16), (27, 18), (30, 20), (34, 22), (36, 24))


def _fixadores(doc: Documento) -> List[Solido]:
    return [e for e in doc.entidades.values() if isinstance(e, Solido) and _tipo_ifc(e) in TIPOS_ACESSORIO and len(e.vertices) >= 4]


def _diametro_do_fixador(ent: Solido, ext) -> Tuple[float, bool]:
    """Diâmetro nominal do parafuso: do nome ("BOLT 12x35" → 12) ou, sem tamanho no nome
    ("BOLT () 0x0"), da porca (entre faces → rosca). Devolve (d, inferido_da_porca)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*\d", ent.nome or "")
    if m:
        d = float(m.group(1).replace(",", "."))
        if d > 0:
            return d, False
    transversais = sorted(ext)[1:]                       # as duas maiores extensões da porca
    af = min(transversais) if transversais else 0.0
    melhor = 12.0
    for entre_faces, rosca in _PORCAS:
        if af >= entre_faces - 0.6:
            melhor = float(rosca)
    return melhor, True


def _ponto_no_poligono(x: float, y: float, poligono, folga: float = 1.0) -> bool:
    dentro = False
    n = len(poligono)
    for i in range(n):
        (x1, y1), (x2, y2) = poligono[i], poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                dentro = not dentro
    if dentro:
        return True
    return any(math.hypot(x - px, y - py) <= folga for px, py in poligono)


def _centros_dos_fixadores(fixadores: Sequence[Solido]) -> Dict[str, Tuple[float, float, float]]:
    """Centro (média dos vértices) de cada fixador, calculado uma vez para o lote todo:
    conferir 1.300 parafusos contra 650 chapas era o que dominava a conversão."""
    return {f.id: tuple(sum(v[i] for v in f.vertices) / len(f.vertices) for i in range(3)) for f in fixadores if f.vertices}


def inferir_furos_de_parafusos(pos: Posicao, ent: Solido, fixadores: Sequence[Solido], centros=None) -> int:
    """Chapa que veio do IFC sem o furo modelado: cada parafuso (ou chumbador) que
    atravessa a chapa vira um furo redondo de d + 1 mm no ponto em que o eixo cruza o
    plano médio. Devolve quantos furos entraram; a célula ganha a observação.
    `centros`: {id do fixador: centro}, de _centros_dos_fixadores (opcional)."""
    if pos.classe != "chapa" or not pos.eixos or not pos.contorno or not fixadores:
        return 0
    if centros is None:
        centros = _centros_dos_fixadores(fixadores)
    e1, e2, e3 = pos.eixos
    c, _ = _autovetores(pos.vertices)
    P = [(_dot(_sub(v, c), e1), _dot(_sub(v, c), e2), _dot(_sub(v, c), e3)) for v in pos.vertices]
    u0, v0 = min(q[0] for q in P), min(q[1] for q in P)
    w0 = (min(q[2] for q in P) + max(q[2] for q in P)) / 2
    centro_plano = tuple(c[i] + e3[i] * w0 for i in range(3))
    caixa = _caixa(ent)
    folga = 40.0
    novos, porca = 0, False
    for f in fixadores:
        cf = centros.get(f.id)
        if cf is None or not all(caixa[i][0] - folga <= cf[i] <= caixa[i][1] + folga for i in range(3)):
            continue
        cc, pca = _autovetores(f.vertices)
        ext = []
        for ax in pca:
            ts = [_dot(_sub(v, cc), ax) for v in f.vertices]
            ext.append(max(ts) - min(ts))
        # parafuso comprido: eixo é o maior; só a porca (achatada): eixo é o menor
        eixo = pca[0] if ext[0] > 1.5 * ext[1] else pca[2]
        alcance = (ext[0] if ext[0] > 1.5 * ext[1] else ext[2]) / 2 + pos.T + folga
        den = _dot(eixo, e3)
        if abs(den) < 0.7:
            continue
        t = _dot(_sub(centro_plano, cc), e3) / den
        if abs(t) > alcance:
            continue
        p = tuple(cc[i] + eixo[i] * t for i in range(3))
        u, v = _dot(_sub(p, c), e1) - u0, _dot(_sub(p, c), e2) - v0
        if not _ponto_no_poligono(u, v, pos.contorno, 1.0):
            continue
        d, inferido = _diametro_do_fixador(f, ext)
        d_furo = d + 1.0
        if any(math.hypot(u - g.x, v - g.y) < max(d_furo, g.d, g.larg) for g in pos.furos):
            continue                                     # o furo já está na malha
        pos.furos.append(Furo("redondo", float(round(u)), float(round(v)), d_furo))
        novos += 1
        porca = porca or inferido
    if novos:
        pos.observacoes.append("%d furo(s) pelo parafuso do modelo (a chapa veio sem furo no IFC)%s"
                               % (novos, "; diametro pela porca, conferir" if porca else ""))
    return novos


def aplicar_ajustes_de_furos(posicoes: Sequence[Posicao], ajustes: Optional[dict]) -> List[str]:
    """Furação guardada no projeto (vínculo chapa → terça) substitui a medida da malha."""
    if not ajustes:
        return []
    aplicadas = []
    for pos in posicoes:
        for m in marcas_de(pos):
            reg = ajustes.get(m)
            if not reg or not isinstance(reg, dict):
                continue
            pos.furos = [_furo_de_dict(f) for f in (reg.get("furos") or [])]
            pos.observacoes.append("furacao vinculada a %s" % (reg.get("origem") or "ajuste do projeto"))
            aplicadas.append(pos.marca)
            break
    return aplicadas


def vincular_furos_de_ligacao(posicoes: Sequence[Posicao], camadas: Dict[str, str], marca_chapa: str,
                              originais: Sequence[dict], novos: Sequence[dict]) -> Dict[str, dict]:
    """A chapinha do suporte mudou de furação (passos): as terças cuja furação original
    era a mesma (em qualquer orientação) recebem os passos novos, como na regra de
    fábrica. Devolve {marca da terça: {"furos": [...], "origem": ...}} para guardar."""
    def grade(furos):
        g = [Furo("redondo", float(f["x"]), float(f["y"]), float(f.get("d", 0) or 0)) for f in furos if f.get("tipo", "redondo") == "redondo"]
        return _assinatura(g) if len(g) >= 2 else None
    ass_o, ass_n = grade(originais), grade(novos)
    if not ass_o or not ass_n or ass_o[:2] != ass_n[:2] or ass_o == ass_n:
        return {}
    nc_o, nl_o, dx_o, dy_o = ass_o
    _, _, dx_n, dy_n = ass_n
    fora: Dict[str, dict] = {}
    for pos in posicoes:
        if pos.classe != "barra" or not _eh_terca(pos, camadas.get(pos.marca, "")):
            continue
        mudou = []
        for g in _grupos_de_furos(pos.furos):
            ass = _assinatura(g)
            if not ass:
                continue
            nc, nl, dx, dy = ass
            if (nc, dx) == (nc_o, dx_o) and (nl, dy) == (nl_o, dy_o):
                _reposicionar(g, dx_n, dy_n)
                mudou.append("%dx%d %s x %s -> %s x %s" % (nc, nl, _mm(dx), _mm(dy), _mm(dx_n), _mm(dy_n)))
            elif (nc, dx) == (nl_o, dy_o) and (nl, dy) == (nc_o, dx_o):
                _reposicionar(g, dy_n, dx_n)
                mudou.append("%dx%d %s x %s -> %s x %s" % (nc, nl, _mm(dx), _mm(dy), _mm(dy_n), _mm(dx_n)))
        if mudou:
            for f in pos.furos:
                f.x, f.y = float(round(f.x)), float(round(f.y))
            reg = {"furos": [_furo_dict(f) for f in pos.furos], "origem": "chapa %s (%s)" % (marca_chapa, "; ".join(sorted(set(mudou))))}
            for m in marcas_de(pos):
                fora[m] = reg
    return fora


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


def marcas_de(pos: Posicao) -> List[str]:
    """As marcas do IFC que a posição representa (várias quando iguais foram fundidas)."""
    return list(getattr(pos, "marcas", None) or [pos.marca])


def _assinatura_posicao(p: Posicao) -> tuple:
    furos = tuple(sorted((f.tipo, f.vista, round(f.x), round(f.y), round(f.d, 1), round(f.larg, 1), round(f.alt, 1),
                          tuple((round(x), round(y)) for x, y in f.pontos)) for f in p.furos))
    dev = tuple(round(v) for v in p.desenvolvimento) if p.desenvolvimento else ()
    # barra redonda (tirante): a "altura" é o gancho da ponta e a "espessura" é o polígono
    # da malha, que variam décimos de peça para peça; reta ou com gancho, é o mesmo item
    # quando o comprimento de corte é o mesmo
    redonda = p.classe in ("barra_redonda", "barra_conformada") and _eh_redonda_perfil(p.perfil)
    classe = "redonda" if redonda else p.classe
    altura = None if redonda else round(p.H)
    espessura = None if redonda else round(p.T, 1)
    return (classe, re.sub(r"\s+", "", p.perfil or "").upper(), re.sub(r"\s+", "", p.material or "").upper(),
            altura, espessura, furos, dev)


#: Comprimentos até esta diferença (mm) são a mesma peça.
TOLERANCIA_COMPRIMENTO = 1.0


def fundir_posicoes_iguais(posicoes: Sequence[Posicao], camadas: Dict[str, str]) -> List[Posicao]:
    """Marcas diferentes com a mesma peça (o TecnoMETAL numera por conjunto, e décimos de
    milímetro separavam tirantes iguais) viram uma posição só: "P64 / P65 / P66", com
    as quantidades somadas e os conjuntos reunidos. `marcas_de(pos)` guarda as originais."""
    chaves: Dict[tuple, List[Posicao]] = collections.OrderedDict()
    fora: List[Posicao] = []
    for p in posicoes:
        p.marcas = [p.marca]
        if p.classe == "indefinida":
            fora.append(p)
            continue
        chaves.setdefault(_assinatura_posicao(p), []).append(p)
    # dentro da mesma assinatura, comprimentos a até 1 mm um do outro são a mesma peça
    grupos: List[List[Posicao]] = []
    for lista in chaves.values():
        lista.sort(key=lambda q: q.comprimento)
        atual = [lista[0]]
        for q in lista[1:]:
            if q.comprimento - atual[-1].comprimento <= TOLERANCIA_COMPRIMENTO:
                atual.append(q)
            else:
                grupos.append(atual)
                atual = [q]
        grupos.append(atual)
    for grupo in grupos:
        if len(grupo) == 1:
            fora.append(grupo[0])
            continue
        grupo.sort(key=lambda q: _ordem_natural(q.marca))
        base = grupo[0]
        base.marcas = [q.marca for q in grupo]
        base.marca = " / ".join(base.marcas)
        base.quantidade = sum(q.quantidade for q in grupo)
        conjuntos: List[str] = []
        for q in grupo:
            for c in q.conjuntos:
                if c not in conjuntos:
                    conjuntos.append(c)
            if q is not base:
                base.global_ids.extend(q.global_ids)
                for obs in q.observacoes:
                    if obs not in base.observacoes:
                        base.observacoes.append(obs)
        base.conjuntos = conjuntos
        if any(q.classe == "barra_redonda" for q in grupo) and _eh_redonda_perfil(base.perfil):
            base.classe = "barra_redonda"              # tirante: vai para o grupo dos tirantes
        # o comprimento da peça fundida é o mais frequente (peso das quantidades)
        cont = collections.Counter()
        for q in grupo:
            cont[q.comprimento] += q.quantidade
        total_q = sum(cont.values()) or 1
        media = sum(c * n for c, n in cont.items()) / total_q
        # empate: o mais perto da média ponderada e, ainda empatado, o menor (2529,5 e 2530,3 → 2530)
        base.comprimento = max(cont, key=lambda c: (cont[c], -abs(c - media), -c))
        if base.classe in ("barra", "barra_redonda", "barra_conformada", "telha"):
            base.L = base.comprimento
        camadas[base.marca] = camadas.get(base.marcas[0], "")
        fora.append(base)
    return fora


def _posicoes_de(pecas: Sequence[Solido], fixadores: Optional[Sequence[Solido]] = None) -> Tuple[List[Posicao], Dict[str, str]]:
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
    centros = _centros_dos_fixadores(fixadores) if fixadores else {}
    for marca, pos in por_marca.items():
        try:
            ch = getattr(primeiro.get(marca), "parametrica", None)
            if isinstance(ch, Chapa):
                _posicao_de_chapa(pos, ch)
            else:
                analisar(pos)
                if fixadores:
                    inferir_furos_de_parafusos(pos, primeiro[marca], fixadores, centros)
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
    solta = not pos.conjuntos or set(pos.conjuntos) <= set(marcas_de(pos))
    return perfil_u and solta and 50.0 <= pos.H <= 400.0 and pos.L >= 1500.0


def _eixos_da_assinatura(ass) -> Tuple[Tuple[int, float], ...]:
    """Grupo de furos sem orientação: {(n, passo)} por eixo — a chapinha do suporte tem
    a furação da terça girada de 90°."""
    nc, nl, dx, dy = ass
    return tuple(sorted(((nc, dx), (nl, dy))))


def _grupos_de_furos(furos: Sequence[Furo], raio: float = 160.0) -> List[List[Furo]]:
    """Furos redondos da vista de frente agrupados por proximidade (uma ligação cada)."""
    # redondos, e os oblongos que têm par na mesma coluna (furos de ligação já oblongados
    # pelo padrão da fábrica); o oblongo isolado é o do tirante e não entra
    frente = [f for f in furos if f.vista == "frente"]
    lista = [f for f in frente if f.tipo == "redondo"
             or (f.tipo == "oblongo" and any(g is not f and abs(g.x - f.x) <= 2.0 for g in frente))]
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


#: Rasgo do furo oblongo da terça: comprimento = diâmetro + isto (Ø13 → 25x13).
RASGO_OBLONGO_TERCA = 12.0


def _oblongar(grupo: Sequence[Furo]) -> int:
    """Furos redondos do grupo viram oblongos no sentido da barra; devolve quantos."""
    n = 0
    for f in grupo:
        if f.tipo == "redondo" and f.d > 0:
            f.tipo, f.larg, f.alt = "oblongo", float(round(f.d + RASGO_OBLONGO_TERCA)), float(f.d)
            n += 1
    return n


def oblongar_tercas(posicoes: Sequence[Posicao], camadas: Dict[str, str]) -> List[str]:
    """Padrão da fábrica: todos os furos redondos da terça na vista de frente (ligação
    aos suportes, esticador, tirante) são oblongos, com o rasgo no sentido da barra.
    Vale depois da regra e dos ajustes do projeto. Devolve as marcas alteradas."""
    fora = []
    for pos in posicoes:
        if not _eh_terca(pos, camadas.get(pos.marca, "")):
            continue
        frente = [f for f in pos.furos if f.vista == "frente"]
        n = _oblongar([f for f in frente if f.tipo == "redondo"])
        if n:
            pos.observacoes.append("furos da ligacao oblongos (%s): padrao de fabrica" % ", ".join(sorted({f.rotulo() for f in frente if f.tipo == "oblongo"})))
            fora.append(pos.marca)
    return fora


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
        oblongados = 0
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
        if alterou or oblongados:
            txt = "furacao no padrao de fabrica (%s x %s mm%s)%s" % (
                _mm(passo_h), _mm(passo_v), ", furos oblongos" if oblongados else "",
                (": " + "; ".join(sorted(set(alterou)))) if alterou else "")
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
    titulo = "%s – %02dx" % (pos.nome or pos.marca, pos.quantidade)
    if pos.nome:
        titulo += "  (%s)" % pos.marca                  # a marca do TecnoMETAL fica rastreável
    linhas = [titulo]
    if pos.tipo_nome and pos.tipo_nome != "parte":
        linhas.insert(0, TIPOS_NOME.get(pos.tipo_nome, pos.tipo_nome).upper())   # "TERÇA DE COBERTURA"
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
    p = _Papel(desenho, atr, dx, dy, camada_peca=pos.camada_2d or "")
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
    # as cotas dos furos saem sempre (a produção precisa delas), mesmo quando um trecho
    # curto — 35 mm da ponta numa terça em 1:25 — deixa os textos apertados
    cadeia = bool(xs) and p.cadeia_h([0.0] + xs + [L], 0, -off, exigir_espaco=False)
    p.cota_h(0, L, 0, -(off3 if cadeia == "dupla" else off2 if cadeia else off))
    cadeia = bool(ys) and p.cadeia_v([0.0] + ys + [H], L, off, exigir_espaco=False)
    p.cota_v(0, H, L, off3 if cadeia == "dupla" else off2 if cadeia else off)

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
            p.cadeia_h([0.0] + sorted({round(f.x, 1) for f in furos_topo}) + [L], y_topo + w_min, -off, exigir_espaco=False)
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
def detalhar_posicao(doc: Documento, marca: str, editavel: bool = True, ajustes: Optional[dict] = None,
                     nomes: Optional[dict] = None) -> Tuple[Desenho, Posicao]:
    """Desenho "Detalhe – <marca>" com a célula da posição. Chapa paramétrica sai com os
    furos editáveis e `metadados.detalhe_posicao` guarda o que "Aplicar furos" precisa."""
    pecas, _ = _pecas(doc)
    lista = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) == marca]
    if not lista:
        raise ErroDeDados("não há peça com a posição %s no modelo." % marca)
    posicoes, camadas = _posicoes_de(lista, _fixadores(doc))
    aplicar_ajustes_de_furos(posicoes, ajustes)
    oblongar_tercas(posicoes, camadas)
    aplicar_nomes(posicoes, nomes)
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
                          "categoria": _categoria(pos, camadas.get(marca, "")), "nome": pos.nome}}}
    d.metadados["detalhe_posicao"] = {
        "marca": marca, "classe": pos.classe, "editavel": edit, "parametrica": parametrica,
        "L": round(pos.L, 3), "H": round(pos.H, 3), "T": round(pos.T, 3),
        "pecas": [e.id for e in lista],
        "furos": [_furo_dict(f) for f in pos.furos if f.vista == "frente"]}
    return d, pos


def _posicao_bruta(ent: Solido, marca: str) -> Posicao:
    m = _marcas(ent)
    return Posicao(marca=marca, tipo_ifc="IfcPlate", perfil=re.sub(r"\s+", " ", str(m.get("perfil") or ent.nome or "")),
                   material=_material(ent), vertices=[tuple(v) for v in ent.vertices], faces=[list(f) for f in ent.faces])


def _custo_forma(A: Sequence[Tuple[float, float]], B: Sequence[Tuple[float, float]], celula: float = 4.0, teto: float = 8.0) -> float:
    """Distância média (mm) de cada ponto de A ao ponto mais próximo de B e vice-versa,
    com grade de `celula` mm e distâncias acima de `teto` saturadas: mede se dois
    conjuntos de vértices projetados têm a mesma forma."""
    def grade(P):
        g: Dict[Tuple[int, int], List[Tuple[float, float]]] = collections.defaultdict(list)
        for p in P:
            g[(int(math.floor(p[0] / celula)), int(math.floor(p[1] / celula)))].append(p)
        return g

    def lado(P, gq):
        total = 0.0
        for p in P:
            i, j = int(math.floor(p[0] / celula)), int(math.floor(p[1] / celula))
            m = teto
            for di in (-2, -1, 0, 1, 2):
                for dj in (-2, -1, 0, 1, 2):
                    for q in gq.get((i + di, j + dj), ()):
                        d = math.hypot(p[0] - q[0], p[1] - q[1])
                        if d < m:
                            m = d
            total += m
        return total / max(1, len(P))
    return (lado(A, grade(B)) + lado(B, grade(A))) / 2.0


def _pontuacao_vista(eixos) -> int:
    """Quanto o triedro segue a vista natural (ver _orientar_para_vista): desempate."""
    e1, _, e3 = eixos
    ax = max(range(3), key=lambda i: abs(e3[i]))
    alvo = {2: 1.0, 1: -1.0, 0: 1.0}[ax]
    ax1 = max(range(3), key=lambda i: abs(e1[i]))
    return (2 if e3[ax] * alvo > 0 else 0) + (1 if e1[ax1] > 0 else 0)


def _eixos_pela_forma(pos_ref: Posicao, pos: Posicao):
    """Triedro (direito) desta instância que projeta os vértices dela sobre a forma da
    referência: entre ±e1, ±e2 (e os eixos trocados numa chapa quase quadrada), o de
    menor custo de forma. Furo fora do centro decide o sentido; quando a forma é
    simétrica e sobra empate, vale a vista natural — assim TODAS as instâncias da
    posição recebem o furo mexido do mesmo lado, e do lado que se vê no 3D. Devolve
    (eixos, conferida) ou None quando a forma nem bate (peça diferente)."""
    if not pos.eixos or not pos_ref.local or not pos.vertices:
        return None
    ref2 = [(u, v) for u, v, _ in pos_ref.local]
    e1, e2, _ = pos.eixos
    c, _ = _autovetores(pos.vertices)
    quadrada = abs(pos.L - pos.H) < 0.05 * max(pos.L, pos.H, 1.0)
    cands = []
    for trocar in ((False, True) if quadrada else (False,)):
        a, b = (e2, e1) if trocar else (e1, e2)
        for s1 in (1.0, -1.0):
            for s2 in (1.0, -1.0):
                f1 = tuple(s1 * x for x in a)
                f2 = tuple(s2 * x for x in b)
                f3 = _norm(_cruz(f1, f2))
                P = [(_dot(_sub(v, c), f1), _dot(_sub(v, c), f2)) for v in pos.vertices]
                u0, v0 = min(p[0] for p in P), min(p[1] for p in P)
                cands.append((_custo_forma(ref2, [(u - u0, v - v0) for u, v in P]), (f1, f2, f3)))
    cands.sort(key=lambda t: t[0])
    melhor = cands[0][0]
    if melhor > 2.0:
        return None
    empatados = [e for custo, e in cands if custo - melhor <= 0.3]
    return max(empatados, key=_pontuacao_vista), True


def _orientar_para_vista(eixos):
    """Sinais dos eixos da chapa de referência pela vista natural: chapa deitada é vista
    de cima (normal +z), chapa em pé de frente (normal −y) ou da direita (+x); o eixo
    do comprimento aponta para +x (ou +y, +z). O desenho fica previsível e, com as
    instâncias no mesmo sistema, o furo mexido cai no mesmo lugar em todas."""
    e1, e2, e3 = eixos
    ax = max(range(3), key=lambda i: abs(e3[i]))
    alvo = {2: 1.0, 1: -1.0, 0: 1.0}[ax]
    if e3[ax] * alvo < 0:
        e3 = tuple(-x for x in e3)
    ax1 = max(range(3), key=lambda i: abs(e1[i]))
    if e1[ax1] < 0:
        e1 = tuple(-x for x in e1)
    e2 = _norm(_cruz(e3, e1))
    e1 = _norm(_cruz(e2, e3))
    return (e1, e2, e3)


def _chapa_de_posicao(ent: Solido, pos: Posicao, espelhada: bool = False, conferida: bool = True) -> Chapa:
    """Chapa paramétrica com os parâmetros medidos em `pos` (mesmo id e atributos do
    sólido). `espelhada`: os eixos são um triedro esquerdo (instância espelhada) e a
    origem vai para a outra face, para a espessura crescer para o lado certo."""
    e1, e2, e3 = pos.eixos
    c, _ = _autovetores(pos.vertices)
    P = [(_dot(_sub(v, c), e1), _dot(_sub(v, c), e2), _dot(_sub(v, c), e3)) for v in pos.vertices]
    u0, v0 = min(q[0] for q in P), min(q[1] for q in P)
    w0 = (min(q[2] for q in P) + max(q[2] for q in P)) / 2
    base = w0 + pos.T / 2 if espelhada else w0 - pos.T / 2
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
    atributos["eixos_conferidos"] = bool(conferida)
    if getattr(ent, "origem_ifc", ""):
        atributos["origem_ifc"] = ent.origem_ifc
    return Chapa(id=ent.id, nome=ent.nome, camada=ent.camada, material=ent.material, visivel=ent.visivel,
                 bloqueada=ent.bloqueada, grupo=ent.grupo, atributos=atributos,
                 origem=tuple(round(x, 3) for x in origem), eixo_x=tuple(round(x, 6) for x in e1),
                 eixo_y=tuple(round(x, 6) for x in e2),
                 contorno=[(round(x, 3), round(y, 3)) for x, y in pos.contorno],
                 espessura=round(pos.T, 3), centrada=False, furos=furos, aco=ent.material or _material(ent))


def converter_chapas(doc: Documento, marca: str, referencia: Optional[str] = None) -> int:
    """Sólidos de chapa plana (IfcPlate) da posição viram entidades Chapa paramétricas —
    mesmo id, nome, camada e atributos; contorno, espessura e furos medidos da malha.

    Todas as instâncias saem no MESMO sistema: a de referência (`referencia` = id da
    peça clicada, senão a primeira) tem os eixos pela vista natural, e cada outra recebe
    o triedro que põe a forma dela sobre a forma da referência (ver _eixos_pela_forma)
    — uma chapa montada virada ou espelhada fica com o furo do desenho no mesmo canto
    físico que as demais. Quando nem a forma bate (`eixos_conferidos` = False), a
    instância é medida sozinha e "Aplicar furos" volta a decidir o espelhamento pelos
    furos originais. Devolve quantas foram convertidas."""
    lista = [ent for ent in doc.entidades.values() if isinstance(ent, Solido) and _tipo_ifc(ent) == "IfcPlate"
             and str(_marcas(ent).get("posicao") or ent.nome or ent.id) == marca]
    if not lista:
        return 0
    ref = next((e for e in lista if e.id == referencia), lista[0])
    fixadores = _fixadores(doc)
    centros = _centros_dos_fixadores(fixadores)
    pos_ref = _posicao_bruta(ref, marca)
    try:
        analisar(pos_ref)
        if pos_ref.classe == "chapa" and pos_ref.contorno and pos_ref.eixos:
            analisar(pos_ref, eixos=_orientar_para_vista(pos_ref.eixos))
            inferir_furos_de_parafusos(pos_ref, ref, fixadores, centros)
    except Exception:                                 # noqa: BLE001
        pos_ref.classe = "indefinida"
    if pos_ref.classe != "chapa" or not pos_ref.contorno or not pos_ref.eixos:
        return 0
    n = 0
    for ent in lista:
        if ent is ref:
            pos, espelhada, conferida = pos_ref, False, True
        else:
            pos = _posicao_bruta(ent, marca)
            espelhada, conferida = False, False
            try:
                analisar(pos)
                if pos.classe == "chapa" and pos.eixos:
                    r = _eixos_pela_forma(pos_ref, pos)
                    if r:
                        eixos, conferida = r
                        analisar(pos, eixos=eixos)
                    else:
                        analisar(pos, eixos=_orientar_para_vista(pos.eixos))
                inferir_furos_de_parafusos(pos, ent, fixadores, centros)
            except Exception:                         # noqa: BLE001
                continue
            if pos.classe != "chapa" or not pos.contorno or not pos.eixos:
                continue
        doc.entidades[ent.id] = _chapa_de_posicao(ent, pos, espelhada, conferida)
        n += 1
    return n


def _mundo_da_chapa(ch: Chapa):
    """(origem da face de baixo, ex, ey, normal) da chapa, no mundo."""
    ex, ey = _norm(tuple(float(k) for k in ch.eixo_x)), _norm(tuple(float(k) for k in ch.eixo_y))
    nz = _norm(_cruz(ex, ey))
    o = tuple(float(k) for k in ch.origem)
    if ch.centrada:
        o = tuple(o[i] - nz[i] * float(ch.espessura) / 2.0 for i in range(3))
    return o, ex, ey, nz


def _ponto_da_chapa(ch: Chapa, x: float, y: float):
    """Ponto (x, y) do sistema da chapa no plano médio, no mundo."""
    o, ex, ey, nz = _mundo_da_chapa(ch)
    t = float(ch.espessura) / 2.0
    return tuple(o[i] + ex[i] * x + ey[i] * y + nz[i] * t for i in range(3))


def _local_na_chapa(ch: Chapa, p) -> Tuple[float, float]:
    o, ex, ey, _ = _mundo_da_chapa(ch)
    d = _sub(p, o)
    return _dot(d, ex), _dot(d, ey)


def _caixa_da_chapa(ch: Chapa):
    o, ex, ey, nz = _mundo_da_chapa(ch)
    t = float(ch.espessura)
    pts = [tuple(o[i] + ex[i] * x + ey[i] * y + nz[i] * w for i in range(3)) for x, y in (ch.contorno or []) for w in (0.0, t)]
    if not pts:
        return None
    return tuple((min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3))


def reorientar_chapas(doc: Documento, doc_ifc: Documento) -> dict:
    """Migração das chapas convertidas antes da 0.6.6 (eixos escolhidos peça a peça,
    `eixos_conferidos` ausente): refaz a conversão a partir das malhas do IFC de origem
    (`doc_ifc`), com a primeira chapa da posição como referência — foi ela que gerou o
    desenho —, e escreve em TODAS as instâncias a furação e o contorno atuais dessa
    referência, no sistema novo. Os parafusos de cada instância vão atrás do furo que
    mudou de lugar. Devolve {"posicoes", "chapas", "parafusos", "sem_origem": [ids]}."""
    por_pos: Dict[str, List[Chapa]] = collections.OrderedDict()
    for e in doc.entidades.values():
        a = e.atributos or {}
        if isinstance(e, Chapa) and a.get("convertida_de") == "solido" and not a.get("eixos_conferidos"):
            por_pos.setdefault(str((a.get("marcas") or {}).get("posicao") or e.nome or e.id), []).append(e)
    saida = {"posicoes": 0, "chapas": 0, "parafusos": 0, "sem_origem": []}
    if not por_pos:
        return saida
    solidos_pos: Dict[str, List[Solido]] = collections.defaultdict(list)
    por_gid: Dict[str, Solido] = {}
    for s in doc_ifc.entidades.values():
        if isinstance(s, Solido) and _tipo_ifc(s) == "IfcPlate":
            solidos_pos[str(_marcas(s).get("posicao") or s.nome or s.id)].append(s)
            if s.origem_ifc:
                por_gid[s.origem_ifc] = s
    fixadores = _fixadores(doc)
    movidos: set = set()
    for marca, chapas in por_pos.items():
        pares = []
        for ch in chapas:
            s = por_gid.get(str((ch.atributos or {}).get("origem_ifc") or ""))
            if s is None:
                cx = _caixa_da_chapa(ch)
                melhor, dist = None, 5.0
                for cand in solidos_pos.get(marca, []):
                    cb = _caixa(cand)
                    if cx is None:
                        break
                    d = max(abs((cb[i][0] + cb[i][1]) - (cx[i][0] + cx[i][1])) / 2.0 for i in range(3))
                    if d < dist:
                        melhor, dist = cand, d
                s = melhor
            if s is None:
                saida["sem_origem"].append(ch.id)
                continue
            pares.append((ch, s))
        if not pares:
            continue
        aux = Documento(nome="reorientar")
        for _, s in pares:
            aux.entidades[s.id] = s
        converter_chapas(aux, marca, referencia=pares[0][1].id)
        novas = {s.id: aux.entidades[s.id] for _, s in pares if isinstance(aux.entidades.get(s.id), Chapa)}
        ref_velha, ref_s = pares[0]
        ref_nova = novas.get(ref_s.id)
        if ref_nova is None:
            saida["sem_origem"].extend(ch.id for ch, _ in pares)
            continue
        # furação e contorno atuais da referência (com o que o usuário já aplicou), levados
        # ao sistema novo: mesmo ponto físico
        _, ex_v, ey_v, _ = _mundo_da_chapa(ref_velha)
        _, ex_n, _, _ = _mundo_da_chapa(ref_nova)
        girado = abs(_dot(ex_v, ex_n)) < 0.7          # eixos novos a 90° dos velhos
        furos_novos = []
        for f in ref_velha.furos or []:
            x, y = _local_na_chapa(ref_nova, _ponto_da_chapa(ref_velha, float(f.get("x", 0) or 0), float(f.get("y", 0) or 0)))
            reg = dict(f)
            reg.update(x=round(x, 3), y=round(y, 3))
            if girado and reg.get("largura") and reg.get("altura"):
                reg["largura"], reg["altura"] = reg["altura"], reg["largura"]
            furos_novos.append(reg)
        contorno_novo = [tuple(round(v, 3) for v in _local_na_chapa(ref_nova, _ponto_da_chapa(ref_velha, float(x), float(y))))
                         for x, y in (ref_velha.contorno or [])]
        for ch, s in pares:
            nova = novas.get(s.id)
            if nova is None:
                saida["sem_origem"].append(ch.id)
                continue
            nova.id = ch.id
            nova.nome, nova.camada, nova.material = ch.nome, ch.camada, ch.material
            nova.visivel, nova.bloqueada, nova.grupo, nova.aco = ch.visivel, ch.bloqueada, ch.grupo, ch.aco
            atributos = dict(ch.atributos or {})
            atributos.update({k: v for k, v in (nova.atributos or {}).items() if k in ("eixos_conferidos", "origem_ifc", "convertida_de")})
            nova.atributos = atributos
            nova.furos = [dict(f) for f in furos_novos]
            if contorno_novo:
                nova.contorno = contorno_novo
            # cada furo antigo desta instância vai para o furo novo mais perto (no mundo);
            # os parafusos junto dele acompanham
            antigos = [(f, _ponto_da_chapa(ch, float(f.get("x", 0) or 0), float(f.get("y", 0) or 0))) for f in (ch.furos or [])]
            novos_w = [_ponto_da_chapa(nova, float(f["x"]), float(f["y"])) for f in nova.furos]
            livres = list(range(len(novos_w)))
            _, _, _, nz = _mundo_da_chapa(ch)
            for f, pa in sorted(antigos, key=lambda t: t[1]):
                if not livres:
                    break
                k = min(livres, key=lambda i: math.dist(novos_w[i], pa))
                livres.remove(k)
                delta = _sub(novos_w[k], pa)
                if math.sqrt(_dot(delta, delta)) > 0.05:
                    raio = max(float(f.get("diametro", 0) or 0), float(f.get("largura", 0) or 0), 13.0) / 2 + 6.0
                    saida["parafusos"] += _mover_fixadores_mundo(pa, nz, delta, raio, fixadores, movidos)
            doc.entidades[ch.id] = nova
            saida["chapas"] += 1
        saida["posicoes"] += 1
    return saida


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


def furos_da_chapa(ch: Chapa) -> List[dict]:
    """Furos de uma Chapa no sistema do desenho (canto inferior esquerdo do contorno = 0,0)."""
    cont = [(float(x), float(y)) for x, y in (ch.contorno or [])]
    if not cont:
        return []
    u0, v0 = min(x for x, _ in cont), min(y for _, y in cont)
    fora = []
    for f in ch.furos or []:
        x, y = float(f.get("x", 0) or 0) - u0, float(f.get("y", 0) or 0) - v0
        if float(f.get("diametro", 0) or 0) > 0:
            fora.append({"tipo": "redondo", "x": x, "y": y, "d": float(f["diametro"])})
        else:
            fora.append({"tipo": "oblongo", "x": x, "y": y, "larg": float(f.get("largura", 0) or 0), "alt": float(f.get("altura", 0) or 0)})
    return fora


def aplicar_furos(doc: Documento, marca: str, furos: Sequence[dict], originais: Sequence[dict],
                  contorno: Optional[Sequence[Tuple[float, float]]] = None) -> dict:
    """Escreve nas chapas paramétricas da posição os furos vindos do desenho (coordenadas
    do desenho: canto inferior esquerdo do contorno = 0,0) e, se `contorno` veio
    diferente do da chapa (tamanho ajustado no desenho), o contorno também."""
    nomes = [m.strip() for m in str(marca).split(" / ") if m.strip()]
    chapas = [e for e in doc.entidades.values() if isinstance(e, Chapa)
              and str(_marcas(e).get("posicao") or e.nome or e.id) in nomes]
    if not chapas:
        raise ErroDeDados("a posição %s não tem chapa paramétrica no modelo (abra o detalhe pela peça no 3D primeiro)." % marca)
    orig = [(float(f["x"]), float(f["y"])) for f in originais]
    contornos = 0
    fixadores = _fixadores(doc)
    movidos: set = set()
    parafusos = 0
    for ch in chapas:
        cont = [(float(x), float(y)) for x, y in (ch.contorno or [])]
        u0, v0 = min(x for x, _ in cont), min(y for _, y in cont)
        L, H = max(x for x, _ in cont) - u0, max(y for _, y in cont) - v0
        atuais = [(float(f.get("x", 0) or 0) - u0, float(f.get("y", 0) or 0) - v0) for f in (ch.furos or [])]
        # instâncias no mesmo sistema (conversão com correspondência de vértices): o furo
        # do desenho vai direto; só a chapa medida sozinha ainda adivinha o espelhamento
        mapa = (lambda x, y: (x, y)) if (ch.atributos or {}).get("eixos_conferidos") else _simetria(orig, atuais, L, H)
        if contorno:
            atual_norm = [(x - u0, y - v0) for x, y in cont]
            novo = [(float(x), float(y)) for x, y in contorno]
            mudou = len(novo) != len(atual_norm) or any(
                math.hypot(a[0] - b[0], a[1] - b[1]) > 0.05 for a, b in zip(atual_norm, novo))
            if mudou:
                ch.contorno = [(round(mx + u0, 3), round(my + v0, 3)) for mx, my in (mapa(x, y) for x, y in novo)]
                contornos += 1
        novos = []
        antigos = list(ch.furos or [])
        for f in furos:
            x, y = mapa(float(f["x"]), float(f["y"]))
            reg = {"x": round(x + u0, 3), "y": round(y + v0, 3)}
            # o furo que já existia e andou leva o parafuso junto
            i = f.get("furo")
            if isinstance(i, int) and 0 <= i < len(antigos):
                velho = antigos[i]
                ddx, ddy = reg["x"] - float(velho.get("x", 0) or 0), reg["y"] - float(velho.get("y", 0) or 0)
                if math.hypot(ddx, ddy) > 0.05:
                    raio = max(float(velho.get("diametro", 0) or 0), float(velho.get("largura", 0) or 0), 13.0) / 2 + 6.0
                    parafusos += _mover_fixadores(ch, (float(velho.get("x", 0) or 0), float(velho.get("y", 0) or 0)), (ddx, ddy), raio, fixadores, movidos)
            if f.get("tipo") == "oblongo" and float(f.get("larg", 0) or 0) > 0:
                reg.update(largura=round(float(f["larg"]), 3), altura=round(float(f.get("alt", 0) or 0), 3))
            else:
                reg["diametro"] = round(float(f.get("d", 0) or 0), 3)
            if reg.get("diametro", 0) > 0 or reg.get("largura", 0) > 0:
                novos.append(reg)
        ch.furos = novos
    return {"chapas": len(chapas), "furos": len(furos), "contornos": contornos, "parafusos": parafusos}


def _mover_fixadores(ch: Chapa, furo_local, delta_local, raio: float, fixadores: Sequence[Solido], movidos: set) -> int:
    """Parafuso, porca e arruela que atravessam o furo (eixo perto do centro do furo,
    até 120 mm acima ou abaixo da chapa) andam o mesmo tanto que o furo, no plano da chapa."""
    o, ex, ey, nz = _mundo_da_chapa(ch)
    centro = tuple(o[i] + ex[i] * furo_local[0] + ey[i] * furo_local[1] + nz[i] * float(ch.espessura) / 2.0 for i in range(3))
    delta = tuple(ex[i] * delta_local[0] + ey[i] * delta_local[1] for i in range(3))
    return _mover_fixadores_mundo(centro, nz, delta, raio, fixadores, movidos)


def _mover_fixadores_mundo(centro, nz, delta, raio: float, fixadores: Sequence[Solido], movidos: set,
                           alcance: float = 120.0) -> int:
    """Fixadores cujo centro está a menos de `raio` do eixo `nz` que passa por `centro`
    (e a menos de `alcance` ao longo dele) transladam de `delta`; cada um só uma vez."""
    n = 0
    for f in fixadores:
        if f.id in movidos:
            continue
        cf = tuple(sum(v[i] for v in f.vertices) / len(f.vertices) for i in range(3))
        d = _sub(cf, centro)
        t = _dot(d, nz)
        lateral = math.sqrt(max(0.0, _dot(d, d) - t * t))
        if lateral <= raio and abs(t) <= alcance:
            f.vertices = [tuple(v[i] + delta[i] for i in range(3)) for v in f.vertices]
            movidos.add(f.id)
            n += 1
    return n


def _furos_da_malha(pos: Posicao) -> List[Tuple[Furo, List[int], str]]:
    """Os furos de uma barra analisada com os índices dos vértices do laço de cada um
    (alma = vista de frente, mesa = vista de topo), na ordem de `pos.furos`."""
    fora = []
    for eixo, sinal, ij, vista in ((2, +1.0, (0, 1), "frente"), (1, -1.0, (0, 2), "topo")):
        lacos = _lacos_2d(pos, eixo, sinal, ij)
        for laco, pts in lacos[1:]:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            fora.append((Furo("redondo", (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2,
                              d=max(max(xs) - min(xs), max(ys) - min(ys)), vista=vista), list(laco), vista))
    return fora


#: Um furo do ajuste a mais que isto (mm) do furo da malha não é o mesmo furo: a barra fica.
LIMITE_DESLOCAMENTO_FURO = 40.0


def aplicar_furos_nas_barras(doc: Documento, ajustes: Optional[dict], marcas: Optional[Sequence[str]] = None) -> dict:
    """Leva ao 3D a furação guardada no projeto para as barras (terças vinculadas ao
    suporte): em cada sólido da posição, os vértices de cada furo da malha (parede do
    furo e as duas faces) transladam, no plano da alma ou da mesa, até a posição do
    furo correspondente do ajuste. Repetir não muda nada (o furo já está lá). Devolve
    {"barras": n, "furos": n, "posicoes": [...]}."""
    saida = {"barras": 0, "furos": 0, "posicoes": []}
    if not ajustes:
        return saida
    alvo = set(marcas) if marcas else set(ajustes)
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Solido) or _tipo_ifc(ent) not in TIPOS_PECA:
            continue
        marca = str(_marcas(ent).get("posicao") or ent.nome or ent.id)
        reg = ajustes.get(marca) if marca in alvo else None
        if not reg or not isinstance(reg, dict) or not reg.get("furos"):
            continue
        pos = _posicao_bruta(ent, marca)
        pos.tipo_ifc = _tipo_ifc(ent)
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "barra" or not pos.eixos:
            continue
        e1, e2, e3 = pos.eixos
        atuais = _furos_da_malha(pos)
        alvos = [_furo_de_dict(f) for f in reg["furos"]]
        # o ajuste só muda passos de furação: a malha tem de ter os mesmos furos, cada um
        # a poucos centímetros do alvo; outra geometria com a mesma marca fica intocada
        if len(atuais) != len(alvos):
            saida.setdefault("ignoradas", []).append(marca)
            continue
        livres = list(range(len(alvos)))
        pares = []
        for f, laco, vista in atuais:
            cands = [i for i in livres if alvos[i].vista == vista]
            if not cands:
                pares = None
                break
            k = min(cands, key=lambda i: math.hypot(alvos[i].x - f.x, alvos[i].y - f.y))
            livres.remove(k)
            pares.append((f, laco, vista, k))
        if pares is None or any(math.hypot(alvos[k].x - f.x, alvos[k].y - f.y) > LIMITE_DESLOCAMENTO_FURO for f, _, _, k in pares):
            saida.setdefault("ignoradas", []).append(marca)
            continue
        movidos_aqui = 0
        for f, laco, vista, k in pares:
            ddx, ddy = alvos[k].x - f.x, alvos[k].y - f.y
            # o ajuste guarda milímetros inteiros e a malha tem meios milímetros: furo que
            # só difere pelo arredondamento fica; a medição depois de mover pode
            # oscilar um décimo (a origem local é o vértice extremo), e isso também fica
            if max(abs(ddx), abs(ddy)) <= 0.6:
                continue
            # o furo de frente vive no plano (e1, e2); o de topo, no plano (e1, e3)
            delta = tuple(e1[i] * ddx + (e2[i] if vista == "frente" else e3[i]) * ddy for i in range(3))
            # vértices do furo: os do laço e os que estão no mesmo cilindro (a outra face
            # e a parede): perto do eixo do furo e no nível da chapa do laço
            eixo = e3 if vista == "frente" else e2
            centro = tuple(sum(ent.vertices[i][j] for i in laco) / len(laco) for j in range(3))
            raio = f.d / 2 + 1.0
            nivel = _dot(centro, eixo)
            idx = set(laco)
            for i, v in enumerate(ent.vertices):
                d = _sub(v, centro)
                t = _dot(d, eixo)
                lateral = math.sqrt(max(0.0, _dot(d, d) - t * t))
                if lateral <= raio and abs(_dot(v, eixo) - nivel) <= 15.0:
                    idx.add(i)
            ent.vertices = [tuple(v[j] + delta[j] for j in range(3)) if i in idx else tuple(v) for i, v in enumerate(ent.vertices)]
            movidos_aqui += 1
        if movidos_aqui:
            saida["barras"] += 1
            saida["furos"] += movidos_aqui
            if marca not in saida["posicoes"]:
                saida["posicoes"].append(marca)
    return saida


def regenerar_celula(d: Desenho, doc: Documento, marca: str, ajustes: Optional[dict] = None,
                     nomes_producao: Optional[dict] = None) -> Tuple[float, float, float, float]:
    """Redesenha, no mesmo lugar de um desenho geral, a célula da posição (depois de os
    furos ou o tamanho terem mudado no modelo): apaga o que tem a marca e desenha de
    novo, com furos editáveis, a partir do canto onde estava."""
    cont_antigo, origem = contorno_do_desenho(d, marca)
    caixa = None
    if cont_antigo:
        caixa = (origem[0] - 5.0, origem[1] - 5.0, origem[0] + max(x for x, _ in cont_antigo) + 5.0,
                 origem[1] + max(y for _, y in cont_antigo) + 5.0)
    ids = []
    for k, e in d.entidades.items():
        a = e.atributos or {}
        if a.get("detalhe") == "posicao" and str(a.get("posicao")) == marca:
            ids.append(k)
        elif getattr(e, "camada", "") == "FURO" and a.get("posicao") is None and caixa:
            # furo desenhado à mão dentro da célula: já foi para o modelo, sai daqui para
            # não ficar em dobro com o regenerado
            pts = e.pontos() if hasattr(e, "pontos") else []
            if pts and all(caixa[0] <= p[0] <= caixa[2] and caixa[1] <= p[1] <= caixa[3] for p in pts):
                ids.append(k)
    for k in ids:
        d.remover(k) if hasattr(d, "remover") else d.entidades.pop(k, None)
    pecas, _ = _pecas(doc)
    nomes = [m.strip() for m in str(marca).split(" / ") if m.strip()]
    lista = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) in nomes]
    if not lista:
        raise ErroDeDados("a posição %s não está mais no modelo." % marca)
    posicoes, camadas_ = _posicoes_de(lista, _fixadores(doc))
    posicoes = fundir_posicoes_iguais(posicoes, camadas_)
    aplicar_ajustes_de_furos(posicoes, ajustes)
    oblongar_tercas(posicoes, camadas_)
    aplicar_nomes(posicoes, nomes_producao)
    pos = next((p for p in posicoes if p.marca == marca), posicoes[0])
    pos.marca = marca
    ext = desenho_da_posicao(pos, d, origem[0], origem[1], editavel=pos.classe == "chapa")
    meta = d.metadados.setdefault("detalhamento", {})
    if pos.classe == "chapa":
        meta.setdefault("furos_originais", {})[marca] = [_furo_dict(f) for f in pos.furos if f.vista == "frente"]
        if marca not in meta.setdefault("editaveis", []):
            meta["editaveis"].append(marca)
    itens = meta.setdefault("itens", {})
    if marca in itens:
        itens[marca].update(comprimento=round(pos.comprimento), espessura=round(pos.espessura or pos.T, 1), peso=round(pos.peso, 2))
    # a caixa da célula que continha o canto antigo passa a ser a nova
    cels = d.metadados.get("celulas") or []
    for i, c in enumerate(cels):
        if c[0] - 1 <= origem[0] <= c[2] + 1 and c[1] - 1 <= origem[1] <= c[3] + 1:
            cels[i] = [round(v, 1) for v in ext]
            break
    return ext


#: Camadas em que o contorno de uma chapa pode estar num desenho de detalhamento.
CAMADAS_DE_CONTORNO = ("VISTA", "CHAPAS")


def contorno_do_desenho(d: Desenho, marca: Optional[str] = None):
    """(contorno, origem) da chapa num desenho: a maior polilinha fechada da camada
    VISTA marcada com a posição; o contorno volta com o canto inferior esquerdo em (0, 0)."""
    melhor, area = None, -1.0
    for e in d.entidades.values():
        a = e.atributos or {}
        if not isinstance(e, Polilinha) or not e.fechada or getattr(e, "camada", "") not in CAMADAS_DE_CONTORNO:
            continue
        if a.get("detalhe") != "posicao" or (marca is not None and str(a.get("posicao")) != marca) or "furo" in a:
            continue
        ar = abs(_area_2d(e.vertices))
        if ar > area:
            melhor, area = e, ar
    if melhor is None:
        return None, (0.0, 0.0)
    xs = [p[0] for p in melhor.vertices]
    ys = [p[1] for p in melhor.vertices]
    x0, y0 = min(xs), min(ys)
    return [(round(x - x0, 3), round(y - y0, 3)) for x, y in melhor.vertices], (x0, y0)


def furos_do_desenho(d: Desenho, marca: Optional[str] = None, origem=(0.0, 0.0)) -> List[dict]:
    """Os furos de um desenho editável: círculos e polilinhas fechadas da camada FURO
    (as marcadas com `furo` e as que o usuário desenhou depois). Com `marca`, só os da
    célula dessa posição (ou sem posição nenhuma, dentro da caixa do contorno dela);
    `origem` é o canto da chapa no desenho, descontado das coordenadas."""
    fora = []
    caixa = None
    if marca is not None:
        cont, org = contorno_do_desenho(d, marca)
        if cont:
            caixa = (org[0] - 5.0, org[1] - 5.0, org[0] + max(x for x, _ in cont) + 5.0, org[1] + max(y for _, y in cont) + 5.0)
    for e in d.entidades.values():
        if getattr(e, "camada", "") != "FURO":
            continue
        a = e.atributos or {}
        if marca is not None:
            pos_e = a.get("posicao")
            if pos_e is not None and str(pos_e) != marca:
                continue
            if pos_e is None:
                pts = e.pontos() if hasattr(e, "pontos") else []
                if not caixa or not pts or not all(caixa[0] <= p[0] <= caixa[2] and caixa[1] <= p[1] <= caixa[3] for p in pts):
                    continue
        indice = a.get("furo") if isinstance(a.get("furo"), int) else None
        if isinstance(e, Circulo):
            fora.append({"tipo": "redondo", "x": e.centro[0] - origem[0], "y": e.centro[1] - origem[1], "d": 2 * e.raio, "furo": indice})
        elif isinstance(e, Polilinha) and e.fechada and len(e.vertices) >= 3:
            xs = [p[0] for p in e.vertices]
            ys = [p[1] for p in e.vertices]
            larg, alt = max(xs) - min(xs), max(ys) - min(ys)
            cx, cy = (max(xs) + min(xs)) / 2 - origem[0], (max(ys) + min(ys)) / 2 - origem[1]
            if a.get("tipo_furo") == "oblongo" or abs(larg - alt) > 0.5:
                fora.append({"tipo": "oblongo", "x": cx, "y": cy, "larg": float(a.get("larg") or larg), "alt": float(a.get("alt") or alt), "furo": indice})
            else:
                fora.append({"tipo": "redondo", "x": cx, "y": cy, "d": (larg + alt) / 2, "furo": indice})
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


def _assinatura_conjunto(instancia: Sequence[Solido], fundidas: Optional[Dict[str, str]] = None) -> dict:
    """O que identifica o detalhe de um conjunto: composição (por posição fundida),
    extensões principais, posição relativa de cada peça e o lado para que a tesoura
    sobe no desenho. Comparar com _conjuntos_iguais, que usa tolerâncias — décimos de
    milímetro não separam duas tesouras iguais."""
    fundidas = fundidas or {}
    verts = [v for e in instancia for v in e.vertices]
    c, pca = _autovetores(verts)
    ext = []
    for e_ in pca:
        ts = [_dot(_sub(v, c), e_) for v in verts]
        ext.append(max(ts) - min(ts))
    pecas: Dict[str, List[Tuple[float, float]]] = collections.defaultdict(list)
    for e in instancia:
        m = _marcas(e)
        marca = str(m.get("posicao") or e.nome)
        ce = [sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3)]
        d = _sub(ce, c)
        pecas[fundidas.get(marca, marca)].append((abs(_dot(d, pca[0])), abs(_dot(d, pca[1]))))
    return {"ext": tuple(ext), "pecas": {k: sorted(v) for k, v in pecas.items()}, "lado": _lado_do_conjunto(instancia)}


def _lado_do_conjunto(instancia: Sequence[Solido]) -> int:
    """+1 quando o conjunto sobe para a direita no desenho, −1 para a esquerda, 0 quando
    é simétrico ou reto: a água esquerda e a direita de um pórtico são espelhadas, e o
    usuário quer um detalhe de cada lado."""
    try:
        c, u, v, w = _eixos_do_conjunto(instancia)
        u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    except Exception:                                 # noqa: BLE001
        return 0
    # pelos vértices (não pelos centros das peças): um conjunto de poucas peças, com a
    # barra atravessando tudo, ainda tem o que comparar em cada quarto
    pontos = [(_dot(_sub(p, c), u), _dot(_sub(p, c), v)) for e in instancia for p in e.vertices]
    if not pontos:
        return 0
    us = [q[0] for q in pontos]
    vs = [q[1] for q in pontos]
    L, H = max(us) - min(us), max(vs) - min(vs)
    if L <= 0 or H <= 0:
        return 0
    esq = [cv for cu, cv in pontos if cu < -0.25 * L]
    dir_ = [cv for cu, cv in pontos if cu > 0.25 * L]
    if not esq or not dir_:
        return 0
    dif = sum(dir_) / len(dir_) - sum(esq) / len(esq)
    if abs(dif) < 0.15 * H:
        return 0
    return 1 if dif > 0 else -1


#: Tolerâncias (mm) para dois conjuntos serem o mesmo detalhe.
TOLERANCIA_CONJUNTO_EXT = 3.0
TOLERANCIA_CONJUNTO_PECA = 8.0


def _conjuntos_iguais(a: dict, b: dict) -> bool:
    if a["lado"] != b["lado"] or set(a["pecas"]) != set(b["pecas"]):
        return False
    if any(abs(x - y) > TOLERANCIA_CONJUNTO_EXT for x, y in zip(a["ext"], b["ext"])):
        return False
    for marca, lista in a["pecas"].items():
        outra = list(b["pecas"][marca])
        if len(outra) != len(lista):
            return False
        for du, dv in lista:
            k = min(range(len(outra)), key=lambda i: abs(outra[i][0] - du) + abs(outra[i][1] - dv))
            if abs(outra[k][0] - du) > TOLERANCIA_CONJUNTO_PECA or abs(outra[k][1] - dv) > TOLERANCIA_CONJUNTO_PECA:
                return False
            outra.pop(k)
    return True


#: Conjuntos com as mesmas dimensões (a esta tolerância, mm) e pelo menos esta fração
#: de peças em comum são o mesmo detalhe, com a diferença de composição anotada.
TOLERANCIA_CONJUNTO_SEMELHANTE = 20.0
FRACAO_COMUM_CONJUNTO = 0.75


def _conjuntos_semelhantes(a: dict, b: dict) -> bool:
    """Mesmo lado, mesmas dimensões principais e composição quase igual: a tesoura de
    ponta com outra chapa de base ou uma diagonal a menos vai para a célula da tesoura
    corrente (pedido do usuário: um detalhe por lado), com a diferença escrita."""
    if a["lado"] != b["lado"]:
        return False
    # 20 mm ou 3 % da dimensão: a chapa de base maior deixa a tesoura de ponta 28 mm
    # mais alta e ela continua sendo a mesma tesoura
    if any(abs(x - y) > max(TOLERANCIA_CONJUNTO_SEMELHANTE, 0.03 * max(x, y)) for x, y in zip(a["ext"][:2], b["ext"][:2])):
        return False
    ca = collections.Counter({k: len(v) for k, v in a["pecas"].items()})
    cb = collections.Counter({k: len(v) for k, v in b["pecas"].items()})
    comum = sum(min(ca[k], cb.get(k, 0)) for k in ca)
    return comum >= FRACAO_COMUM_CONJUNTO * max(sum(ca.values()), sum(cb.values()), 1)


def _diferenca_de_composicao(lider: dict, outra: dict) -> str:
    """"+P26 x1; -P1 x1": o que `outra` tem a mais e a menos que o conjunto líder."""
    a = collections.Counter({k: len(v) for k, v in outra["pecas"].items()})
    b = collections.Counter({k: len(v) for k, v in lider["pecas"].items()})
    mais = sorted((k for k in a if a[k] > b.get(k, 0)), key=_ordem_natural)
    menos = sorted((k for k in b if b[k] > a.get(k, 0)), key=_ordem_natural)
    partes = []
    if mais:
        partes.append("+" + ", ".join("%s x%d" % (k, a[k] - b.get(k, 0)) for k in mais))
    if menos:
        partes.append("-" + ", ".join("%s x%d" % (k, b[k] - a.get(k, 0)) for k in menos))
    return "; ".join(partes)


def _agrupar_conjuntos_iguais(candidatos, fundidas: Optional[Dict[str, str]] = None) -> List[Tuple[dict, list]]:
    """Candidatos (conj, lista, inst, n, unidade, aviso) iguais (a menos das tolerâncias)
    ou semelhantes (mesmas dimensões, composição quase igual) na mesma célula; a ordem
    dos candidatos manda (o primeiro lidera). Devolve [(assinatura do líder, grupo)];
    cada candidato do grupo ganha um 7º campo: a diferença de composição para o líder."""
    grupos: List[Tuple[dict, list]] = []
    for cand in candidatos:
        ass = _assinatura_conjunto(cand[2], fundidas)
        for ass_g, grupo in grupos:
            if _conjuntos_iguais(ass_g, ass) or _conjuntos_semelhantes(ass_g, ass):
                grupo.append(tuple(cand) + (_diferenca_de_composicao(ass_g, ass),))
                break
        else:
            grupos.append((ass, [tuple(cand) + ("",)]))
    return grupos


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
                        desenho: Desenho, dx: float, dy: float, rotular: bool = True,
                        fundidas: Optional[Dict[str, str]] = None, nota=None,
                        nomes: Optional[Dict[str, str]] = None, nome: str = "", tipo: str = "") -> Tuple[float, float, float, float]:
    """Elevação do conjunto com cotas de nós, título e lista de perfis, em (dx, dy).
    `fundidas`: marca do IFC → posição fundida; `nomes`: posição fundida → nome de
    produção (rótulos e composição com o mesmo nome que as células de posição);
    `nome`: o do conjunto (T1, S.T.2…)."""
    fundidas = fundidas or {}
    nomes = nomes or {}

    def nome_de(marca_ifc):
        f = fundidas.get(str(marca_ifc), str(marca_ifc))
        return nomes.get(f) or f
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
    camada_de = _classificar_pecas_do_conjunto(instancia, (u, v, origem))
    _registrar_camadas_de_pecas(desenho)
    for e in novas:
        e.atributos["conjunto"] = marca
        e.atributos["detalhe"] = "conjunto"
        # silhueta (VISTA/CORTE) na camada da peça: terças, banzos, diagonais…; as
        # arestas finas ficam finas
        if e.camada in ("VISTA", "CORTE") and e.atributos.get("origem") in camada_de:
            e.camada = camada_de[e.atributos["origem"]]
    # extremos reais em (u, v) do que foi desenhado: canto inferior esquerdo = (dx, dy)
    us = [_dot(_sub(p, origem), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, origem), v) for e in instancia for p in e.vertices]
    u0, v0 = min(us), min(vs)
    atr = {"conjunto": marca, "detalhe": "conjunto"}
    p = _Papel(desenho, atr, dx, dy)
    esc = desenho.escala
    off, off2, off3 = 10.0, 20.0, 30.0
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
            rotulos.append((nome_de(m["posicao"]), ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), ang))
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
    # a cadeia de cada banzo acompanha a caída da cobertura: banzo inclinado (mais de 2°)
    # ganha cotas alinhadas à própria reta, com as distâncias medidas nela — é o que se
    # marca na barra; banzo horizontal fica com a cadeia horizontal
    def reta_do_banzo(em_cima):
        lados = [b for b in banzos if ((b[0][1] + b[1][1]) / 2 > v_medio) == em_cima]
        pts = [q for b in lados for q in (b[0], b[1])]
        if not pts:
            return None
        a_, b_ = min(pts, key=lambda q: q[0]), max(pts, key=lambda q: q[0])
        if b_[0] - a_[0] < 1e-6 or abs(math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))) < 2.0:
            return None
        return a_, b_

    def cadeia_do_banzo(nos, em_cima):
        reta = reta_do_banzo(em_cima)
        if reta is None:
            return p.cadeia_h(nos, alt if em_cima else 0.0, off if em_cima else -off)
        return p.cadeia_alinhada(reta, nos, off if em_cima else -off)
    cadeia = len(nos_baixo) > 2 and cadeia_do_banzo(nos_baixo, False)
    p.cota_h(0, larg, 0, -(off2 if cadeia else off))
    cadeia_cima = len(nos_cima) > 2 and nos_cima != nos_baixo and cadeia_do_banzo(nos_cima, True)
    # suportes de terça (chapinhas/cantoneiras curtas encostadas no banzo de cima): a
    # cadeia do espaçamento deles, alinhada ao banzo, acima da cadeia dos nós
    suportes = []
    reta_cima = reta_do_banzo(True)
    for e in instancia:
        if camada_de.get(e.id) != "CHAPAS":
            continue
        pu = [_dot(_sub(q, origem), u) - u0 for q in e.vertices]
        pv = [_dot(_sub(q, origem), v) - v0 for q in e.vertices]
        # o suporte é a chapa em pé (alta e estreita na elevação); o gusset deitado
        # e o enrijecedor ao lado dele não contam
        if max(pu) - min(pu) > 40.0 or max(pv) - min(pv) < 100.0:
            continue
        cx, cy = sum(pu) / len(pu), sum(pv) / len(pv)
        if reta_cima is not None:
            (ax_, ay_), (bx_, by_) = reta_cima
            dist = abs((bx_ - ax_) * (ay_ - cy) - (ax_ - cx) * (by_ - ay_)) / max(math.hypot(bx_ - ax_, by_ - ay_), 1e-9)
        else:
            dist = abs(cy - alt)
        if dist <= 150.0:
            suportes.append(cx)
    cadeia_suportes = False
    if len(suportes) >= 2:
        sup = fundir(set(round(s, 1) for s in suportes) | {0.0, larg}, tol=60.0, fixos=(0.0, larg))
        # a cadeia dos suportes só se repete quando é exatamente a dos nós (terça em todo
        # nó); terça de dois em dois nós tem espaçamento próprio, e é ele que se cota
        iguais = len(sup) == len(nos_cima) and all(abs(s - n_) <= 20.0 for s, n_ in zip(sorted(sup), sorted(nos_cima)))
        if not iguais and len(sup) > 2:
            # a folga da ponta ao primeiro suporte é curta (uns 120 mm): a cadeia sai mesmo
            # assim — é a medida que a fábrica marca no banzo
            desl = off2 if cadeia_cima else off
            cadeia_suportes = (p.cadeia_alinhada(reta_cima, sup, desl, exigir_espaco=False) if reta_cima is not None
                               else p.cadeia_h(sup, alt, desl, exigir_espaco=False))
    cadeia = len(alturas) > 2 and p.cadeia_v(alturas, larg, off)
    p.cota_v(0, alt, larg, off2 if cadeia else off)
    _rotular_barras(p, rotulos, esc)
    # título e lista de perfis
    comp = collections.Counter()
    perfis = collections.Counter()
    for e in instancia:
        m = _marcas(e)
        comp[nome_de(m.get("posicao") or e.nome)] += 1
        perfis[str(m.get("perfil") or e.nome)] += 1
    y = alt + (((off3 if cadeia_cima else off2) if cadeia_suportes else (off2 if cadeia_cima else off)) + 2.0) * esc
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
    titulo = "%s – %02dx" % (nome or marca, n_instancias) + ("  (%s)" % marca if nome else "")
    linhas = [titulo] + quebrar("Perfis: ", lista) + quebrar("Pecas: " if nomes else "Posicoes: ", posic)
    if tipo:
        linhas.insert(0, TIPOS_NOME.get(tipo, tipo).upper())
    for txt in ([nota] if isinstance(nota, str) else list(nota or [])):
        if not txt:
            continue
        # nota quebrada por palavras, com recuo
        atual = "* "
        for palavra in txt.split(" "):
            if len(atual) + len(palavra) + 1 > 72 and atual.strip() != "*":
                linhas.append(atual.rstrip())
                atual = "  "
            atual += palavra + " "
        linhas.append(atual.rstrip())
    for i, txt in enumerate(reversed(linhas)):
        alt_t = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt_t * esc)
        y += (alt_t + 1.2) * esc
    ext = p.extremos
    return (min(ext[0], dx), min(ext[1], dy), max(ext[2], dx + larg), max(ext[3], dy + alt))


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


def _extensao_do_conjunto(instancia: Sequence[Solido]) -> Tuple[float, float]:
    """(comprimento, altura) da instância na vista em que é desenhada."""
    c, u, v, w = _eixos_do_conjunto(instancia)
    u, v, w = _vistas.Vista(origem=c, normal=w, acima=v).eixos()
    us = [_dot(_sub(p, c), u) for e in instancia for p in e.vertices]
    vs = [_dot(_sub(p, c), v) for e in instancia for p in e.vertices]
    return max(us) - min(us), max(vs) - min(vs)


def desenho_de_contraventamentos(doc: Documento, membros: Sequence[tuple], desenho: Desenho, dx: float, dy: float,
                                 nomes: Dict[str, str], nomes_conj: Dict[str, str], fundidas: Dict[str, str],
                                 comprimentos: Dict[str, float], rotular: bool = True) -> Tuple[float, float, float, float]:
    """Detalhe limpo dos contraventamentos que só diferem no comprimento do tirante
    (mesmas peças de ponta): a elevação do mais comprido, as cotas empilhadas — uma por
    contraventamento, "C.V.3 (02x) – 5150" — e, embaixo, as cotas das peças de ponta
    (barra roscada do esticador, cantoneiras, chapa). `membros` = [(rotulo do grupo,
    instância, nº de instâncias)]."""
    membros = sorted(membros, key=lambda m: _ordem_natural(nomes_conj.get(m[0], m[0])))
    maior = max(membros, key=lambda m: _extensao_do_conjunto(m[1])[0])
    rotulo, inst, _ = maior
    rotulo_celula = " / ".join(m[0] for m in membros)
    c, u, v, w = _eixos_do_conjunto(inst)
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
    tirante = _tirante_principal(inst)

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
    for a_, b_, linha, nome_p, perfil in extremos_pecas:
        p.cota_h(a_, b_, 0, -(off * linha), texto="%d  %s" % (round(b_ - a_), nome_p))
    # cotas empilhadas por contraventamento, a partir da ponta esquerda
    for i, (rot, inst_m, n_inst) in enumerate(membros):
        comp_m, _ = _extensao_do_conjunto(inst_m)
        nome_m = nomes_conj.get(rot, rot)
        p.cota_h(0, round(comp_m), alt, off + passo * i, texto="%s (%02dx) – %d" % (nome_m, n_inst, round(comp_m)))
    # rótulos: tirante pelo perfil no meio; peças de ponta pelo nome
    if rotular:
        h = 1.8 * esc
        if tirante is not None:
            pu = [_dot(_sub(q, origem), u) - u0 for q in tirante.vertices]
            p.texto((min(pu) + max(pu)) / 2, alt + 2.0 * esc, str(_marcas(tirante).get("perfil") or tirante.nome or ""), h, "TEXTO", alinhamento="centro")
        pass
    # título: tipo, nomes e, por contraventamento, o tirante com o comprimento de corte
    total = sum(m[2] for m in membros)
    linhas = ["CONTRAVENTAMENTO", "%s – %02dx" % (" / ".join(nomes_conj.get(m[0], m[0]) for m in membros), total)]
    marcas_txt, atual = [], "("
    for mk in rotulo_celula.split(" / "):
        if len(atual) + len(mk) + 3 > 72 and atual != "(":
            marcas_txt.append(atual.rstrip(" /"))
            atual = " "
        atual += mk + " / "
    marcas_txt.append(atual.rstrip(" /") + ")")
    linhas.extend(marcas_txt)
    for rot, inst_m, n_inst in membros:
        tir = _tirante_principal(inst_m)
        if tir is None:
            continue
        marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
        comp_t = comprimentos.get(marca_t)
        nome_t = nomes.get(marca_t) or marca_t
        linhas.append("%s – %02dx: tirante %s%s%s" % (nomes_conj.get(rot, rot), n_inst,
                                                    "" if nome_t == nomes_conj.get(rot, rot) else nome_t + " ",
                                                    str(_marcas(tir).get("perfil") or tir.nome or ""),
                                                    "  L = %d mm" % round(comp_t) if comp_t else ""))
    pecas_ponta = collections.Counter(nome_de(_marcas(e).get("posicao") or e.nome) for e in inst if e is not tirante)
    if pecas_ponta:
        linhas.append("Pecas de ponta (por unidade): " + ", ".join("%s x%d" % (k, q) for k, q in sorted(pecas_ponta.items(), key=lambda kv: _ordem_natural(kv[0]))))
    y = alt + (off + passo * len(membros) + 4.0) * esc
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
                           ignorar: Sequence[str] = (), nomes: Optional[Dict[str, str]] = None,
                           camadas_pecas: Optional[Dict[str, str]] = None) -> Desenho:
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
                cam = (camadas_pecas or {}).get(str(m.get("posicao") or ""), "")
                if cam:
                    _registrar_camadas_de_pecas(d)
                pp.polilinha(casco, fechada=True, camada=cam or "ACO-FINO")
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
            rotulos.append(((nomes or {}).get(rotulo) or rotulo, (sum(pu) / len(pu), sum(pv) / len(pv))))
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


# ============================================================ nomes de produção
#: Prefixo do nome de produção por tipo de item (padrão dos desenhos da fábrica).
PREFIXO_NOME = collections.OrderedDict([
    ("tesoura", "T"), ("terca_cobertura", "T.C."), ("terca_marquise", "T.M."), ("suporte_terca", "S.T."),
    ("agulhamento", "A.G."), ("suporte_agulhamento", "S.A.G."), ("contraventamento", "C.V."),
    ("suporte_contraventamento", "S.C.V."), ("castanha", "C.S."), ("chapa", "CH."),
    ("barra_roscada", "B.R."), ("gancho", "G."), ("barra", "B."), ("telha", "TL."), ("conjunto", "CJ."), ("parte", ""),
])
TIPOS_NOME = {
    "tesoura": "Tesoura", "terca_cobertura": "Terça de cobertura", "terca_marquise": "Terça de marquise",
    "suporte_terca": "Suporte de terça", "agulhamento": "Agulhamento", "suporte_agulhamento": "Suporte de agulhamento",
    "contraventamento": "Contraventamento", "suporte_contraventamento": "Suporte de contraventamento",
    "castanha": "Castanha", "chapa": "Chapa", "barra": "Barra", "telha": "Telha", "conjunto": "Conjunto",
    "barra_roscada": "Barra roscada", "gancho": "Gancho", "parte": "Parte de conjunto",
}
#: Terça cujo centro fica além disto (mm) da caixa dos pilares em planta é de marquise.
FOLGA_MARQUISE = 300.0


def _assinaturas_de_terca(posicoes: Sequence[Posicao], camadas: Dict[str, str]) -> set:
    fora = set()
    for p in posicoes:
        if _eh_terca(p, camadas.get(p.marca, "")):
            for g in _grupos_de_furos(p.furos):
                a = _assinatura(g)
                if a and len(g) >= 2:
                    fora.add(_eixos_da_assinatura(a))
    return fora


def _tem_furacao_de_terca(pos: Posicao, assinaturas: set) -> bool:
    for g in _grupos_de_furos(pos.furos):
        a = _assinatura(g)
        if a and len(g) >= 2 and _eixos_da_assinatura(a) in assinaturas:
            return True
    return False


#: Chapa a menos disto (mm) da ponta de uma terça é o suporte dela.
ALCANCE_SUPORTE_TERCA = 200.0


def _chapas_onde_a_terca_encosta(pecas: Sequence[Solido], marcas_terca: set) -> set:
    """Marcas das chapas que têm a ponta de alguma terça a menos de ALCANCE_SUPORTE_TERCA
    do seu centro: são os suportes de terça, seja qual for a furação."""
    pontas = collections.defaultdict(list)
    cel = 500.0
    for e in pecas:
        if str(_marcas(e).get("posicao") or e.nome or e.id) not in marcas_terca:
            continue
        eixo = _eixo_da_peca(e)
        if not eixo:
            continue
        for p in eixo:
            pontas[tuple(int(math.floor(p[i] / cel)) for i in range(3))].append(p)
    fora = set()
    for e in pecas:
        if not (_tipo_ifc(e).startswith("IfcPlate") or isinstance(getattr(e, "parametrica", None), Chapa)) or not e.vertices:
            continue
        c = tuple(sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3))
        k = tuple(int(math.floor(c[i] / cel)) for i in range(3))
        perto = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for p in pontas.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if math.dist(p, c) <= ALCANCE_SUPORTE_TERCA:
                            perto = True
                            break
                    if perto:
                        break
                if perto:
                    break
            if perto:
                break
        if perto:
            fora.add(str(_marcas(e).get("posicao") or e.nome or e.id))
    return fora


def _caixa_dos_pilares(pecas: Sequence[Solido]):
    """(x0, y0, x1, y1) em planta dos pilares (IfcColumn com mais de 1 m de altura)."""
    xs, ys = [], []
    for e in pecas:
        if _tipo_ifc(e) == "IfcColumn" and e.vertices:
            cx = _caixa(e)
            if cx[2][1] - cx[2][0] > 1000.0:
                xs.extend((cx[0][0], cx[0][1]))
                ys.extend((cx[1][0], cx[1][1]))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _nome_numero(nome: str, prefixo: str):
    """("T.C.2-A", "T.C.") → (2, "A"); None quando o nome não tem esse prefixo."""
    m = re.match(re.escape(prefixo) + r"(\d+)(?:-([A-Z]))?$", nome or "")
    return (int(m.group(1)), m.group(2) or "") if m else None


def nomear(posicoes: Sequence[Posicao], camadas: Dict[str, str], pecas: Sequence[Solido],
           conjuntos_info: Sequence[dict], anteriores: Optional[dict] = None) -> dict:
    """Nome de produção de cada posição e conjunto, no padrão da fábrica:

    * tesouras (conjuntos com 8+ barras) T1, T2…; terças de cobertura T.C.n (mesmo
      perfil e comprimento = mesma família; furação diferente = T.C.n-A, -B…) e de
      marquise T.M.n (centro fora da caixa dos pilares em planta); suportes de terça
      S.T.n (chapa/cantoneira com a furação de alguma terça, ou o conjunto que a
      contém); agulhamentos A.G.n (barra solta comprida que não é terça, ou o conjunto
      de uma barra com chapas); contraventamentos C.V.n (barras redondas e os conjuntos
      com elas); castanhas C.S.n (chapa pequena presa a contraventamento); as demais
      chapas CH.n, barras B.n, telhas TL.n e conjuntos CJ.n;
    * a peça que só existe dentro de um conjunto (que não seja tesoura) chama-se pelo
      conjunto: S.T.1.1, S.T.1.2…

    Numeração por quantidade decrescente. `anteriores` ({"posicoes": {marca: nome},
    "conjuntos": {...}}, o nomes.json do projeto) mantém os nomes já dados: uma peça
    nova não renumera as outras. Devolve {"posicoes", "conjuntos", "tipos",
    "tipos_conjuntos", "ifc" (marca do IFC → nome), "ifc_conjuntos"} e escreve
    `pos.nome` em cada posição."""
    anteriores = anteriores or {}
    ant_pos = anteriores.get("posicoes") or {}
    ant_conj = anteriores.get("conjuntos") or {}
    ass_terca = _assinaturas_de_terca(posicoes, camadas)
    caixa_pil = _caixa_dos_pilares(pecas)
    centros: Dict[str, List[Tuple[float, float]]] = collections.defaultdict(list)
    for e in pecas:
        m = str(_marcas(e).get("posicao") or e.nome or e.id)
        if e.vertices:
            centros[m].append((sum(v[0] for v in e.vertices) / len(e.vertices), sum(v[1] for v in e.vertices) / len(e.vertices)))
    fundidas = {m: p.marca for p in posicoes for m in marcas_de(p)}
    conj_de_marca: Dict[str, str] = {}
    for c in conjuntos_info:
        for m in c.get("marcas") or [c["marca"]]:
            conj_de_marca[m] = c["marca"]
    tesouras = {c["marca"] for c in conjuntos_info if c.get("categoria") == "TESOURAS"}

    def conjuntos_de(p: Posicao) -> set:
        proprias = set(marcas_de(p))
        return {conj_de_marca.get(c, c) for c in p.conjuntos if c not in proprias}

    # ---- tipo de cada posição
    tipo: Dict[str, str] = {}
    marcas_terca = {m for p in posicoes for m in marcas_de(p) if p.classe == "barra" and _eh_terca(p, camadas.get(p.marca, ""))}
    suportes = _chapas_onde_a_terca_encosta(pecas, marcas_terca)
    for p in posicoes:
        cls = p.classe
        if cls in ("chapa", "chapa_dobrada"):
            # suporte de terça é a chapa em que a terça encosta (geometria), não a que
            # tem a furação parecida: a chapinha de ponta do agulhamento tem os mesmos furos
            t = "suporte_terca" if any(m in suportes for m in marcas_de(p)) else "chapa"
        elif cls == "telha":
            t = "telha"
        elif re.search(r"BARRA\s*ROSC", p.perfil or "", re.I):
            t = "barra_roscada"                      # o pedaço roscado do esticador, não o tirante
        elif cls == "barra_redonda" or (cls == "barra_conformada" and _eh_redonda_perfil(p.perfil)):
            t = "contraventamento" if p.comprimento >= MENOR_TIRANTE else "gancho"
        elif cls == "barra" and _eh_terca(p, camadas.get(p.marca, "")):
            t = "terca_cobertura"
            pts = [q for m in marcas_de(p) for q in centros.get(m, [])]
            if caixa_pil and pts:
                cx = sum(q[0] for q in pts) / len(pts)
                cy = sum(q[1] for q in pts) / len(pts)
                if (cx < caixa_pil[0] - FOLGA_MARQUISE or cx > caixa_pil[2] + FOLGA_MARQUISE
                        or cy < caixa_pil[1] - FOLGA_MARQUISE or cy > caixa_pil[3] + FOLGA_MARQUISE):
                    t = "terca_marquise"
        elif cls in ("barra", "barra_conformada"):
            t = "agulhamento" if (p.comprimento >= 1500.0 and not conjuntos_de(p)) else "barra"
        else:
            t = "barra"
        tipo[p.marca] = t

    # ---- tipo de cada conjunto pela composição
    tipo_conj: Dict[str, str] = {}
    for c in conjuntos_info:
        if c.get("categoria") == "TESOURAS":
            tipo_conj[c["marca"]] = "tesoura"
            continue
        comp = c.get("composicao") or {}
        cont = collections.Counter()
        for m, q in comp.items():
            cont[tipo.get(fundidas.get(m, m), "")] += q
        n = sum(comp.values())
        barras_conj = [fundidas.get(m, m) for m, q in comp.items() if tipo.get(fundidas.get(m, m)) in ("barra", "agulhamento") for _ in range(q)]
        if cont.get("contraventamento"):
            tipo_conj[c["marca"]] = "contraventamento"
        elif len(barras_conj) == 1 and n <= 6 and n == len(barras_conj) + cont.get("chapa", 0) + cont.get("suporte_terca", 0):
            # uma barra com chapinhas de ponta: agulhamento (a barra é a agulha)
            tipo_conj[c["marca"]] = "agulhamento"
            tipo[barras_conj[0]] = "agulhamento"
        elif cont.get("suporte_terca") and n <= 6:
            tipo_conj[c["marca"]] = "suporte_terca"
        else:
            tipo_conj[c["marca"]] = "conjunto"
    for p in posicoes:
        cs = conjuntos_de(p)
        if not cs:
            continue
        if tipo[p.marca] == "chapa" and p.L <= 250.0 and any(tipo_conj.get(c) == "contraventamento" for c in cs):
            tipo[p.marca] = "castanha"
        elif tipo[p.marca] in ("chapa", "suporte_terca") and all(tipo_conj.get(c) == "agulhamento" for c in cs):
            tipo[p.marca] = "suporte_agulhamento"          # as chapinhas de ponta da agulha
        elif tipo[p.marca] in ("chapa", "barra") and all(tipo_conj.get(c) == "contraventamento" for c in cs):
            tipo[p.marca] = "suporte_contraventamento"     # cantoneiras e chapas de ponta do tirante

    def anterior(mapa, chaves, prefixo):
        for k in chaves:
            n = mapa.get(k)
            if n and _nome_numero(n, prefixo):
                return n
        return ""

    # ---- conjuntos: por tipo, quantidade decrescente, mantendo os nomes anteriores
    nomes_conj: Dict[str, str] = {}
    usados_por_prefixo: Dict[str, set] = collections.defaultdict(set)   # conjuntos e posições não repetem nome
    por_tipo: Dict[str, list] = collections.defaultdict(list)
    for c in conjuntos_info:
        por_tipo[tipo_conj[c["marca"]]].append(c)
    for t, lista in por_tipo.items():
        prefixo = PREFIXO_NOME[t]
        usados, pendentes = usados_por_prefixo[prefixo], []
        for c in sorted(lista, key=lambda c: (-c.get("instancias", 0), _ordem_natural(c["marca"]))):
            n = anterior(ant_conj, [c["marca"]] + list(c.get("marcas") or []), prefixo)
            num = _nome_numero(n, prefixo)[0] if n else None
            if num is not None and num not in usados:
                nomes_conj[c["marca"]] = "%s%d" % (prefixo, num)
                usados.add(num)
            else:
                pendentes.append(c)
        k = 1
        for c in pendentes:
            while k in usados:
                k += 1
            nomes_conj[c["marca"]] = "%s%d" % (prefixo, k)
            usados.add(k)

    # ---- posições que só existem dentro de um conjunto (não tesoura): nome do conjunto + .k
    nomes_pos: Dict[str, str] = {}
    partes: Dict[str, List[Posicao]] = collections.defaultdict(list)
    for p in posicoes:
        cs = {c for c in conjuntos_de(p) if c in nomes_conj}
        if len(cs) == 1 and conjuntos_de(p) == cs:
            c = next(iter(cs))
            if tipo_conj.get(c) != "tesoura":
                partes[c].append(p)
    principais = {"contraventamento": "contraventamento", "agulhamento": "agulhamento"}
    for c, lista in partes.items():
        if tipo_conj.get(c) in principais:
            for p in lista:
                if tipo[p.marca] == principais[tipo_conj[c]]:
                    nomes_pos[p.marca] = nomes_conj[c]      # o tirante é o C.V.n; a agulha é o A.G.n
            continue
        for i, p in enumerate(sorted(lista, key=lambda q: _ordem_natural(q.marca)), 1):
            nomes_pos[p.marca] = "%s.%d" % (nomes_conj[c], i)
            tipo[p.marca] = "parte"

    # ---- as demais por tipo; terças em famílias (perfil + comprimento) com variantes
    por_tipo = collections.defaultdict(list)
    for p in posicoes:
        if p.marca not in nomes_pos:
            por_tipo[tipo[p.marca]].append(p)
    for t, lista in por_tipo.items():
        prefixo = PREFIXO_NOME.get(t) or "P."
        familias: Dict[object, List[Posicao]] = collections.OrderedDict()
        for p in lista:
            chave = (re.sub(r"\s+", "", p.perfil or "").upper(), round(p.comprimento)) if t in ("terca_cobertura", "terca_marquise") else p.marca
            familias.setdefault(chave, []).append(p)
        ordem = sorted(familias.values(), key=lambda l: (-sum(q.quantidade for q in l), _ordem_natural(l[0].marca)))
        for l in ordem:
            l.sort(key=lambda q: (-q.quantidade, _ordem_natural(q.marca)))

        def atribuir(l, num):
            letras = set()
            for q in l:
                n = anterior(ant_pos, [q.marca] + marcas_de(q), prefixo)
                if n and _nome_numero(n, prefixo)[0] == num and _nome_numero(n, prefixo)[1] not in letras:
                    nomes_pos[q.marca] = n
                    letras.add(_nome_numero(n, prefixo)[1])
            j = 0
            for q in l:
                if q.marca in nomes_pos:
                    continue
                while True:
                    letra = "" if j == 0 else chr(64 + j)
                    j += 1
                    if letra not in letras:
                        break
                letras.add(letra)
                nomes_pos[q.marca] = "%s%d%s" % (prefixo, num, "-" + letra if letra else "")
        usados, pendentes = usados_por_prefixo[prefixo], []
        for l in ordem:
            n = anterior(ant_pos, [l[0].marca] + marcas_de(l[0]), prefixo)
            num = _nome_numero(n, prefixo)[0] if n else None
            if num is not None and num not in usados:
                usados.add(num)
                atribuir(l, num)
            else:
                pendentes.append(l)
        k = 1
        for l in pendentes:
            while k in usados:
                k += 1
            usados.add(k)
            atribuir(l, k)
    for p in posicoes:
        p.nome = nomes_pos.get(p.marca, "")
        p.tipo_nome = tipo.get(p.marca, "")
    ifc: Dict[str, str] = {}
    ifc_conj: Dict[str, str] = {}
    for c in conjuntos_info:
        for m in c.get("marcas") or [c["marca"]]:
            ifc_conj[m] = nomes_conj.get(c["marca"], "")
    ifc.update(ifc_conj)
    for p in posicoes:
        for m in marcas_de(p):
            if p.nome:
                ifc[m] = p.nome
    return {"posicoes": nomes_pos, "conjuntos": nomes_conj, "tipos": tipo, "tipos_conjuntos": tipo_conj,
            "ifc": ifc, "ifc_conjuntos": ifc_conj}


def aplicar_nomes(posicoes: Sequence[Posicao], nomes: Optional[dict]):
    """Escreve `pos.nome` a partir do nomes.json do projeto (por marca fundida ou por
    qualquer das marcas originais); sem registro, o nome fica vazio."""
    mapa = (nomes or {}).get("posicoes") or {}
    cam = (nomes or {}).get("camadas_2d") or {}
    tipos = (nomes or {}).get("tipos") or {}
    for p in posicoes:
        p.nome = mapa.get(p.marca) or next((mapa[m] for m in marcas_de(p) if mapa.get(m)), "")
        p.tipo_nome = tipos.get(p.marca) or next((tipos[m] for m in marcas_de(p) if tipos.get(m)), "")
        p.camada_2d = cam.get(p.marca) or next((cam[m] for m in marcas_de(p) if cam.get(m)), "")
        if not p.camada_2d and nomes:
            p.camada_2d = _camada_da_posicao(p, (nomes.get("tipos") or {}).get(p.marca, ""))


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


def levantar(doc: Documento, regra_tercas: bool = True, avisar=None, ajustes: Optional[dict] = None,
             nomes: Optional[dict] = None) -> dict:
    """Só o levantamento: as peças de produção do modelo agrupadas em posições, com a
    geometria analisada e a regra das terças aplicada — sem desenhar nada. É o que a
    lista de materiais usa. Devolve {"pecas", "acessorios", "posicoes", "camadas",
    "regra_tercas", "categorias": {marca: categoria}}."""
    avisar = avisar or (lambda *a: None)
    pecas, acessorios = _pecas(doc)
    if not pecas:
        raise ErroDeDados("o modelo não tem peças com marcas de IFC (IfcBeam, IfcPlate…) para detalhar.")
    posicoes, camadas = _posicoes_de(pecas, _fixadores(doc))
    posicoes = fundir_posicoes_iguais(posicoes, camadas)
    avisar("%d peças em %d posições" % (len(pecas), len(posicoes)))
    mudadas = regra_furacao_terca(posicoes, camadas) if regra_tercas else {}
    ajustadas = aplicar_ajustes_de_furos(posicoes, ajustes)
    if regra_tercas:
        oblongar_tercas(posicoes, camadas)
    aplicar_nomes(posicoes, nomes)
    return {"pecas": pecas, "acessorios": acessorios, "posicoes": posicoes, "camadas": camadas,
            "regra_tercas": mudadas, "ajustes": ajustadas,
            "categorias": {p.marca: _categoria(p, camadas.get(p.marca, "")) for p in posicoes}}


def converter_chapas_planas(doc: Documento, posicoes: Sequence[Posicao], pecas: Sequence[Solido]) -> int:
    """Toda posição de chapa plana ainda sólida vira Chapa paramétrica (ver converter_chapas)."""
    parametricas = {str(_marcas(e).get("posicao") or e.nome or e.id) for e in pecas if getattr(e, "parametrica", None) is not None}
    n = 0
    for p in posicoes:
        if p.classe == "chapa" and p.tipo_ifc == "IfcPlate":
            for m in marcas_de(p):
                if m not in parametricas:
                    n += converter_chapas(doc, m)
    return n


def detalhar(doc: Documento, grupos: Optional[Sequence[str]] = None, regra_tercas: bool = True,
             rotular: bool = True, avisar=None, converter: bool = True, ajustes: Optional[dict] = None,
             nomes: Optional[dict] = None) -> dict:
    """Gera os desenhos de detalhamento do modelo. Devolve
    {"desenhos": {chave: Desenho}, "posicoes": [...], "conjuntos": [...], "acessorios": {},
     "regra_tercas": {marca: texto}, "avisos": [...]}."""
    avisar = avisar or (lambda *a: None)
    grupos = list(grupos or GRUPOS.keys())
    lev = levantar(doc, regra_tercas=regra_tercas, avisar=avisar, ajustes=ajustes)
    convertidas = 0
    if converter:
        # chapas planas viram paramétricas: a célula sai com furos editáveis e "Aplicar
        # furos ao modelo 3D" funciona a partir do desenho geral
        convertidas = converter_chapas_planas(doc, lev["posicoes"], lev["pecas"])
        if convertidas:
            lev = levantar(doc, regra_tercas=regra_tercas, ajustes=ajustes)
    pecas, acessorios, posicoes, camadas, mudadas = (lev["pecas"], lev["acessorios"], lev["posicoes"],
                                                     lev["camadas"], lev["regra_tercas"])
    parametricas: Dict[str, bool] = {}
    for e in pecas:
        m_ = str(_marcas(e).get("posicao") or e.nome or e.id)
        parametricas[m_] = parametricas.get(m_, True) and getattr(e, "parametrica", None) is not None
    desenhos: Dict[str, Desenho] = collections.OrderedDict()
    avisos: List[str] = []

    conjuntos_info = []
    if pecas:            # sempre levantados: os nomes de produção dependem dos conjuntos
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
        fundidas = {m: p.marca for p in posicoes for m in marcas_de(p)}
        grupos_iguais = _agrupar_conjuntos_iguais(candidatos, fundidas)
        celulas = []
        if candidatos:
            for ass, grupo in grupos_iguais:
                conj, lista, inst, n, unidade, aviso, _ = grupo[0]
                marcas = sorted((c[0] for c in grupo), key=_ordem_natural)
                total_inst = sum(c[3] for c in grupo)
                total_pecas = sum(len(c[1]) for c in grupo)
                rotulo = " / ".join(marcas)
                # variantes: os conjuntos da célula cuja composição difere da do líder
                variantes = [{"marca": c[0], "instancias": c[3], "difere": c[6]} for c in grupo[1:] if c[6]]
                nota = ["%s – %02dx: %s" % (v_["marca"], v_["instancias"], v_["difere"]) for v_ in variantes]
                if nota:
                    nota.insert(0, "desenhado o %s; os demais diferem so no anotado" % conj)
                celulas.append((rotulo, inst, total_inst, nota))
                conjuntos_info.append({"marca": rotulo, "marcas": marcas, "pecas": total_pecas, "instancias": total_inst,
                                       "iguais": not aviso, "composicao": dict(unidade), "variantes": variantes,
                                       "categoria": "TESOURAS" if sum(q for k, q in unidade.items() if classe_de.get(k, "").startswith("barra")) >= 8 else "CONJUNTOS"})
                for c in grupo:
                    if c[5]:
                        avisos.append(c[5])
                if len(marcas) > 1:
                    avisos.append("conjuntos %s têm a mesma geometria: detalhados numa célula só (%d no total)%s"
                                  % (", ".join(marcas), total_inst,
                                     "; " + "; ".join("%s difere: %s" % (v_["marca"], v_["difere"]) for v_ in variantes) if variantes else ""))
    # nomes de produção (S.T.1, T.C.2-A, T1…) de posições e conjuntos, estáveis entre
    # gerações quando `nomes` traz os anteriores
    nomeacao = nomear(posicoes, camadas, pecas, conjuntos_info, anteriores=nomes)
    nomes_pos, nomes_conj = nomeacao["posicoes"], nomeacao["conjuntos"]
    for c in conjuntos_info:
        c["nome"] = nomes_conj.get(c["marca"], "")
    # camada 2D de cada posição: barra de conjunto pelo que ela é na elevação (votos
    # das instâncias desenhadas), o resto pelo tipo
    votos: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ass, grupo in grupos_iguais:
        for c in grupo:
            try:
                for eid, cam in _classificar_pecas_do_conjunto(c[2]).items():
                    e_ = doc.entidades.get(eid)
                    if e_ is not None:
                        votos[str(_marcas(e_).get("posicao") or e_.nome or eid)][cam] += 1
            except Exception:                         # noqa: BLE001
                continue
    for p in posicoes:
        p.camada_2d = _camada_da_posicao(p, nomeacao["tipos"].get(p.marca, ""), votos)
    nomeacao["camadas_2d"] = {p.marca: p.camada_2d for p in posicoes}
    camadas_ifc = {m: p.camada_2d for p in posicoes for m in marcas_de(p)}
    if celulas and "conjuntos" in grupos:
        g = GRUPOS["conjuntos"]
        d = Desenho(nome=g["titulo"], escala=g["escala"])
        tipos_conj = nomeacao["tipos_conjuntos"]
        comprimentos = {p.marca: p.comprimento for p in posicoes}
        # contraventamentos com as mesmas peças de ponta: um detalhe só, cotas empilhadas
        cv: Dict[tuple, list] = collections.OrderedDict()
        fns = []
        for rotulo, inst, n, nota in celulas:
            tir = _tirante_principal(inst) if tipos_conj.get(rotulo) == "contraventamento" else None
            if tir is not None:
                marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
                chave = tuple(sorted((fundidas.get(m, m), q) for m, q in collections.Counter(
                    str(_marcas(e).get("posicao") or e.nome) for e in inst).items() if fundidas.get(m, m) != marca_t))
                cv.setdefault(chave, []).append((rotulo, inst, n))
                continue
            fns.append(lambda x, y, rotulo=rotulo, inst=inst, n=n, nota=nota:
                       desenho_do_conjunto(doc, rotulo, inst, n, d, x, y, rotular, fundidas=fundidas, nota=nota,
                                           nomes=nomes_pos, nome=nomes_conj.get(rotulo, ""), tipo=tipos_conj.get(rotulo, "")))
        itens_cv = {}
        for membros in cv.values():
            membros.sort(key=lambda m: _ordem_natural(nomes_conj.get(m[0], m[0])))   # mesma ordem do rótulo da célula
            fns.append(lambda x, y, membros=membros: desenho_de_contraventamentos(
                doc, membros, d, x, y, nomes_pos, nomes_conj, fundidas, comprimentos, rotular))
            chave_cel = " / ".join(m[0] for m in membros)
            itens_cv[chave_cel] = {"quantidade": sum(m[2] for m in membros), "perfil": "contraventamentos %s" % " / ".join(nomes_conj.get(m[0], m[0]) for m in membros),
                                   "material": "", "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                                   "categoria": "CONJUNTOS", "marcas": [mk for m in membros for mk in m[0].split(" / ")],
                                   "nome": " / ".join(nomes_conj.get(m[0], m[0]) for m in membros)}
        _empilhar(d, fns, largura_max_papel=1400.0)
        itens = {c["marca"]: {"quantidade": c["instancias"], "perfil": "conjunto de %d peças" % sum(c["composicao"].values()),
                              "material": "", "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                              "categoria": c["categoria"], "marcas": c["marcas"], "nome": c["nome"]}
                 for c in conjuntos_info}
        itens.update(itens_cv)
        d.metadados["detalhamento"] = {"grupo": "conjuntos", "conjuntos": [c["marca"] for c in conjuntos_info], "itens": itens}
        desenhos["conjuntos"] = d

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
                                "categoria": _categoria(p, camadas.get(p.marca, "")), "marcas": marcas_de(p),
                                "nome": p.nome}
                      for p in lista}}
        editaveis = [p.marca for p in lista if p.classe == "chapa" and all(parametricas.get(m, False) for m in marcas_de(p))]
        celulas = [(lambda x, y, p=p: desenho_da_posicao(p, d, x, y, editavel=p.marca in editaveis)) for p in lista]
        _empilhar(d, celulas)
        d.metadados["detalhamento"]["editaveis"] = editaveis
        d.metadados["detalhamento"]["furos_originais"] = {
            p.marca: [_furo_dict(f) for f in p.furos if f.vista == "frente"] for p in lista if p.marca in editaveis}
        desenhos[chave] = d

    if "localizacao" in grupos:
        try:
            desenhos["localizacao"] = desenho_de_localizacao(doc, pecas, GRUPOS["localizacao"]["titulo"],
                                                             ignorar=[p.marca for p in posicoes if p.classe == "telha"],
                                                             nomes=nomeacao["ifc"], camadas_pecas=camadas_ifc)
        except ErroDeDados as e:
            avisos.append("planta de localização não gerada: %s" % e)

    resumo_pos = []
    for p in _ordenar(posicoes):
        resumo_pos.append({"marca": p.marca, "nome": p.nome, "tipo": nomeacao["tipos"].get(p.marca, ""),
                           "marcas": marcas_de(p), "classe": CLASSES.get(p.classe, p.classe), "perfil": p.perfil,
                           "material": p.material, "quantidade": p.quantidade, "comprimento": round(p.comprimento),
                           "largura": round(p.H), "espessura": round(p.espessura or p.T, 1), "furos": p.rotulo_furos(),
                           "peso": round(p.peso, 3), "peso_total": round(p.peso_total, 2),
                           "conjuntos": list(p.conjuntos), "observacoes": list(p.observacoes)})
    return {"desenhos": desenhos, "posicoes": resumo_pos, "conjuntos": conjuntos_info,
            "acessorios": acessorios, "regra_tercas": mudadas, "avisos": avisos,
            "peso_total": round(sum(p.peso_total for p in posicoes), 1),
            "objetos_posicoes": posicoes, "objetos_pecas": pecas, "camadas": camadas,
            "convertidas": convertidas, "nomes": nomeacao}
