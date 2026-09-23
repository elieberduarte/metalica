# -*- coding: utf-8 -*-
"""Parte "base" do detalhamento (nucleo2d/detalhar.py é a fachada)."""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Barra, Chapa, Documento, Solido
from nucleo3d import geometria as _geo
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import Estilo, _mm


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
    # tudo num desenho só, em faixas, para navegar sem trocar de desenho
    ("completo", {"titulo": "Detalhamento – completo", "escala": 25.0, "classes": ()}),
])
#: Ordem e título das faixas do desenho completo.
FAIXAS_COMPLETO = [("chapas", "CHAPAS"), ("barras", "BARRAS E TERÇAS"), ("tirantes", "TIRANTES E BARRAS REDONDAS"),
                   ("telhas", "TELHAS"), ("conjuntos", "CONJUNTOS"), ("localizacao", "PLANTA DE LOCALIZAÇÃO")]

TIPOS_PECA = {"IfcBeam", "IfcColumn", "IfcMember", "IfcPlate", "IfcPlateStandardCase",
              "IfcMemberStandardCase", "IfcBeamStandardCase", "IfcColumnStandardCase"}
TIPOS_ACESSORIO = {"IfcMechanicalFastener", "IfcDiscreteAccessory", "IfcFastener",
                   "IfcBuildingElementProxy"}

#: Regra da furação das terças: altura limite e (vertical, horizontal) em mm.
LIMITE_TERCA = 200.0

#: Largura comercial da telha (mm): é por ela que a telha é comprada, qualquer que seja a
#: largura total que o modelo traz (a TP40 do TecnoMETAL vem com 1031, com a sobreposição).
LARGURA_COMPRA_TELHA = 980.0


def _area_casco(pontos) -> float:
    """Área do casco convexo de pontos 2D (cadeia monótona)."""
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pontos))
    if len(pts) < 3:
        return 0.0

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo, cima = [], []
    for p in pts:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pts):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    casco = baixo[:-1] + cima[:-1]
    return abs(sum(casco[i][0] * casco[(i + 1) % len(casco)][1] - casco[(i + 1) % len(casco)][0] * casco[i][1]
                   for i in range(len(casco)))) / 2.0


def compra_da_telha(pos) -> dict:
    """A telha como é comprada: chapa inteira no comprimento da peça e na largura
    comercial; os cortes em ângulo ou em curva são feitos na obra. `cortada` diz se a peça
    do modelo tem corte (área da vista menor que o retângulo); `peso` é o da chapa inteira
    (o da peça × retângulo / área cortada)."""
    L, H = float(pos.L or pos.comprimento or 0.0), float(pos.H or 0.0)
    area = _area_casco([(q[0], q[1]) for q in (pos.local or [])]) if pos.local else 0.0
    cheia = L * H
    cortada = bool(area and cheia and area < 0.995 * cheia)
    peso = pos.peso * cheia / area if cortada and area > 0.2 * cheia else pos.peso
    return {"comprimento": L, "largura": LARGURA_COMPRA_TELHA, "cortada": cortada, "peso": peso}
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
    """Sólidos do modelo que são peças de produção, e os acessórios contados.

    Chapa e barra paramétricas (modelo desenhado em 2D ou gerado do galpão) entram como
    o sólido equivalente, com a malha montada dos próprios parâmetros: daí para a frente
    o detalhamento não distingue de onde a peça veio.
    """
    pecas, acessorios = [], collections.Counter()
    for ent in doc.entidades.values():
        if isinstance(ent, Barra):
            if (_tipo_ifc(ent) or ent.tipo_ifc()) in TIPOS_PECA:
                try:
                    pecas.append(_proxy_da_barra(ent))
                except Exception:                     # noqa: BLE001 — barra degenerada não derruba o lote
                    pass
            continue
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


def _proxy_da_barra(b: Barra) -> Solido:
    """Sólido equivalente a uma `Barra` (mesmo id e atributos), com a malha do perfil.

    O comprimento já sai com os recortes de ponta aplicados, como o 3D desenha; o perfil
    vem do catálogo pelo nome, então um nome de fábrica (U92X40X2.25) também funciona.
    """
    verts, faces = _geo.malha_barra(b)
    s = Solido(id=b.id, nome=b.nome or b.perfil, camada=b.camada, material=b.material,
               visivel=b.visivel, bloqueada=b.bloqueada, grupo=b.grupo,
               atributos=dict(b.atributos or {}),
               vertices=[tuple(float(x) for x in v) for v in verts], faces=[list(f) for f in faces])
    s.atributos.setdefault("tipo_ifc", b.tipo_ifc())
    marcas = dict(s.atributos.get("marcas") or {})
    marcas.setdefault("perfil", b.perfil)
    s.atributos["marcas"] = marcas
    s.parametrica = b
    return s


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


def _eixos_dos_fixadores(fixadores: Sequence[Solido]) -> Dict[str, tuple]:
    """{id: (centro, eixo unitário, meio comprimento ao longo do eixo, é_porca)} de cada
    fixador, uma vez para o lote: parafuso comprido tem o eixo no maior espalhamento; a
    porca (achatada) no menor."""
    fora = {}
    for f in fixadores:
        if len(f.vertices) < 4:
            continue
        cc, pca = _autovetores(f.vertices)
        ext = []
        for ax in pca:
            ts = [_dot(_sub(v, cc), ax) for v in f.vertices]
            ext.append(max(ts) - min(ts))
        comprido = ext[0] > 1.5 * ext[1]
        eixo = pca[0] if comprido else pca[2]
        meio = (ext[0] if comprido else ext[2]) / 2
        fora[f.id] = (cc, eixo, meio, ext, not comprido)
    return fora


def _nome_do_parafuso(f: Solido, ext) -> Tuple[str, bool]:
    """"M12x35" a partir de "BOLT (A) 12x35"; (rosca pela porca, True) sem tamanho no nome."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)", f.nome or "")
    if m and float(m.group(1).replace(",", ".")) > 0:
        d = m.group(1).replace(",", ".")
        d = d[:-2] if d.endswith(".0") else d
        return "M%s x %s" % (d, m.group(2)), False
    d, _ = _diametro_do_fixador(f, ext)
    return "M%d" % round(d), True


def parafusos_da_posicao(pos: Posicao, ent: Solido, fixadores: Sequence[Solido], eixos_fix: Optional[dict] = None) -> None:
    """Conta os fixadores cujo eixo atravessa um furo desta peça (uma instância):
    `pos.parafusos` = {"M12 x 35": 4} e `pos.porcas` = fixadores sem tamanho no nome
    (porca, arruela) junto dos furos. Chapa sem furo e sem parafuso é soldada, e ganha
    a nota."""
    pos.parafusos, pos.porcas = {}, 0
    if not pos.eixos or not fixadores or pos.classe == "indefinida":
        if pos.classe == "chapa" and not pos.furos:
            pos.observacoes.append("sem furo e sem parafuso: chapa soldada")
        return
    if eixos_fix is None:
        eixos_fix = _eixos_dos_fixadores(fixadores)
    e1, e2, e3 = pos.eixos
    c, _ = _autovetores(pos.vertices)
    P = [(_dot(_sub(v, c), e1), _dot(_sub(v, c), e2), _dot(_sub(v, c), e3)) for v in pos.vertices]
    u0, v0 = min(q[0] for q in P), min(q[1] for q in P)
    w0 = (min(q[2] for q in P) + max(q[2] for q in P)) / 2
    caixa = _caixa(ent)
    folga = 60.0
    frente = [f for f in pos.furos if f.vista == "frente"]
    topo = [f for f in pos.furos if f.vista == "topo"]
    if not frente and not topo:
        if pos.classe == "chapa":
            pos.observacoes.append("sem furo e sem parafuso: chapa soldada")
        return
    contagem: Dict[str, int] = collections.Counter()
    porcas = 0
    for f in fixadores:
        info = eixos_fix.get(f.id)
        if info is None:
            continue
        cc, eixo, meio, ext, porca = info
        if not all(caixa[i][0] - folga <= cc[i] <= caixa[i][1] + folga for i in range(3)):
            continue
        u, v, w = _dot(_sub(cc, c), e1) - u0, _dot(_sub(cc, c), e2) - v0, _dot(_sub(cc, c), e3) - w0
        bate = False
        # furo de frente: eixo do fixador ao longo de e3, centro perto do furo no plano (e1, e2)
        if frente and abs(_dot(eixo, e3)) > 0.7 and abs(w) <= meio + pos.T / 2 + 20.0:
            bate = any(math.hypot(u - g.x, v - g.y) <= max(g.d, g.larg, g.alt, 10.0) / 2 + 3.0 for g in frente)
        # furo de topo (mesa): eixo ao longo de e2, centro perto do furo no plano (e1, e3)
        if not bate and topo and abs(_dot(eixo, e2)) > 0.7:
            wt = _dot(_sub(cc, c), e3) - min(q[2] for q in P)
            bate = any(math.hypot(u - g.x, wt - g.y) <= max(g.d, g.larg, g.alt, 10.0) / 2 + 3.0 for g in topo)
        if not bate:
            continue
        nome, pela_porca = _nome_do_parafuso(f, ext)
        if porca or pela_porca:
            porcas += 1
        else:
            contagem[nome] += 1
    pos.parafusos = dict(contagem)
    pos.porcas = porcas


def parafusos_no_conjunto(doc: Documento, instancia: Sequence[Solido]) -> Tuple[Dict[str, int], int]:
    """Fixadores dentro da caixa da instância do conjunto: ({"M12 x 35": 32}, porcas)."""
    if not instancia:
        return {}, 0
    caixas = [_caixa(e) for e in instancia]
    minimo = [min(cx[i][0] for cx in caixas) - 20.0 for i in range(3)]
    maximo = [max(cx[i][1] for cx in caixas) + 20.0 for i in range(3)]
    contagem: Dict[str, int] = collections.Counter()
    porcas = 0
    for f in _fixadores(doc):
        cc = tuple(sum(v[i] for v in f.vertices) / len(f.vertices) for i in range(3))
        if not all(minimo[i] <= cc[i] <= maximo[i] for i in range(3)):
            continue
        ext = []
        _, pca = _autovetores(f.vertices)
        for ax in pca:
            ts = [_dot(_sub(v, cc), ax) for v in f.vertices]
            ext.append(max(ts) - min(ts))
        nome, pela_porca = _nome_do_parafuso(f, ext)
        if pela_porca or ext[0] <= 1.5 * ext[1]:
            porcas += 1
        else:
            contagem[nome] += 1
    return dict(contagem), porcas


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
    eixos_fix = _eixos_dos_fixadores(fixadores) if fixadores else {}
    for marca, pos in por_marca.items():
        try:
            ch = getattr(primeiro.get(marca), "parametrica", None)
            if isinstance(ch, Chapa):
                _posicao_de_chapa(pos, ch)
            else:
                analisar(pos)
                if fixadores:
                    inferir_furos_de_parafusos(pos, primeiro[marca], fixadores, centros)
            if fixadores:
                parafusos_da_posicao(pos, primeiro[marca], fixadores, eixos_fix)
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
        # até 200 mm (inclusive) é 50 mm na vertical; só acima de 200 vai a 100
        passo_v, passo_h = FURACAO_TERCA_BAIXA if pos.H <= LIMITE_TERCA else FURACAO_TERCA_ALTA
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


# ============================================================ conjuntos
def _caixa(ent: Solido):
    vs = ent.vertices
    return tuple((min(v[i] for v in vs), max(v[i] for v in vs)) for i in range(3))


def _eixo_da_peca(ent: Solido):
    """Extremos do eixo de uma barra (PCA) em 3D, ou None para chapas."""
    verts = ent.vertices
    if len(verts) < 4:
        return None
    c, pca = _autovetores(verts)
    e1 = pca[0]
    ts = [_dot(_sub(v, c), e1) for v in verts]
    return (tuple(c[i] + e1[i] * min(ts) for i in range(3)), tuple(c[i] + e1[i] * max(ts) for i in range(3)))


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
