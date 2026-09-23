# -*- coding: utf-8 -*-
"""Cálculo estrutural de um modelo **importado** (sólidos do TecnoMETAL e afins).

O modelo que chega de um IFC de fábrica não tem barras paramétricas: cada peça é um
sólido facetado com a marca, o conjunto, o perfil e o aço no Pset "Steel & Graphics
Common". Este módulo monta o modelo de cálculo a partir desses sólidos, do jeito que o
projetista calcula uma cobertura treliçada:

1. **Tesouras** (conjuntos que o nomeador classificou como `tesoura`): cada instância
   vira um pórtico plano no próprio plano — banzos contínuos divididos nos nós, diagonais
   e montantes rotulados, nós nos pontos de trabalho (interseção do eixo da diagonal com
   o eixo do banzo). Peças geminadas (dois U costa a costa) viram uma barra de seção
   dobrada. Apoios nos nós junto às castanhas com chumbador, ou nos nós de beiral.
2. **Terças**: toda barra fora das tesouras cujo eixo cruza o plano da tesoura junto ao
   banzo superior é terça e entrega ali a reação do seu trecho tributário; a que cruza
   junto ao banzo inferior é travamento (agulhamento) e conta como contenção lateral.
3. **Cargas**: peso próprio medido do modelo (barras pelo perfil, chapas pelo volume),
   telha (pela espessura do nome, ou o valor informado), sobrecarga de cobertura (NBR
   8800: 0,25 kN/m²), vento pela NBR 6123 com a geometria lida do modelo (vão, comprimento,
   inclinação) e os parâmetros informados (V₀, categoria, aberturas, altura do beiral).
   Combinações últimas e de serviço como no galpão (`nucleo.galpao._combinar`).
4. **Verificação** peça a peça, pela posição (marca) e com os piores esforços entre todas
   as instâncias: U e Ue formados a frio pela NBR 14762 (MRD, com a interação N–M linear
   do item 9.8.2.4), cantoneiras, W e tubos pela NBR 8800, terças pela rotina de terça da
   NBR 14762, redondas à tração.

O resultado sai no **mesmo formato do mapa de esforços do galpão** (`nucleo3d.mapa_esforcos`),
que o editor 3D já desenha: `elementos` (aqui por marca), `portico.barras` com as
tesouras típicas em coordenadas reais, combinações, serviço. Mais `verificacoes` (a
memória de cada peça) e `resumo` (o que foi adotado), para o relatório.

Unidades: o documento está em mm; o modelo de análise trabalha em cm e kN; as cargas de
superfície em kN/m²; o payload em mm, kN e kN·m como o editor lê.

**Ligações** (`ligacoes` no resultado): a chapa de nó lida do modelo — a `Chapa`
paramétrica do detalhamento dá espessura, contorno e furos — é verificada com a barra que
chega nela (Whitmore, bloco de cisalhamento, parafusos ou solda); sem chapa sobre a barra,
que é o caso da treliça leve com a diagonal soldada direto no banzo Ue, verifica-se a solda
da diagonal no banzo, com o contato medido pela altura do banzo e o ângulo entre os dois.
A troca de perfil reverifica a ligação com o candidato: a barra mais fina passa na barra e
pode reprovar na solda, porque a perna fica limitada pela chapa mais fina.

Limites desta versão (declarados em `avisos`): contraventamentos e tirantes não são
verificados (sem cargas de oitão no modelo); o IFC não traz solda nem classe de parafuso,
então a perna é a mínima da Tabela 10 (limitada pela chapa mais fina) e a classe é a do
parâmetro `parafuso`; a chapa de nó comprimida é verificada como escoamento de Whitmore,
sem flambagem; cantoneira formada a frio é verificada pela NBR 8800 com o fator Q
(conservador); as tabelas de vento são as de galpão fechado de duas águas.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo import analise, cargas, nbr8800, nbr14762, perfis_fabrica, verificar
from nucleo import materiais as mat
from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt
from nucleo.perfis import Perfil
from nucleo3d.modelo import Chapa, Documento, Solido
from nucleo3d.mapa_esforcos import (ENVOLTORIA, ESTACOES, GRANDEZAS, UNIDADES,
                                    _amostrar, _combinacoes, _envoltoria)

__all__ = ["calcular", "PARAMETROS_PADRAO", "geometria_do_modelo"]

PARAMETROS_PADRAO = {
    "v0": 40.0,                      # m/s
    "cidade": "",
    "categoria": "II",
    "classe": "B",
    "s1": 1.0,
    "grupo": 2,
    "aberturas": "duas faces opostas",
    "altura_beiral": None,           # m acima do solo; None = cota do apoio no modelo
    "sobrecarga": 0.25,              # kN/m² (projeção horizontal)
    "carga_extra": 0.0,              # kN/m² de cobertura (forro, instalações)
    "telha": None,                   # kN/m² de cobertura; None = pela espessura do nome
    "correntes": None,               # linhas de correntes por vão de terça; None = contadas no modelo
    "trava_inferior": None,          # m entre travamentos laterais do banzo inferior; None = os lidos no modelo
    "apoio": "rotulado",             # "rotulado" (os dois) ou "movel" (um lado só na vertical)
    "apoios": [],                    # pontos de apoio [x, y, z] mm; vazio = nós de extremidade
    "aco_frio": "CIVIL 300",
    "aco_laminado": "ASTM A36",
    "flecha_tesoura": 250,           # L/250
    "flecha_terca": 180,
    "trocas": {},                    # {marca: nome do perfil de cálculo}
    "parafuso": "ASTM A307",         # classe dos parafusos das chapas de nó (o IFC não diz)
    "eletrodo": "E70XX",             # eletrodo das soldas das chapas de nó
    "aco_chapa": None,               # aço das chapas de nó; None = o da chapa no modelo ou o laminado
}

#: Peso da telha pela espessura no nome (kN/m² de superfície).
PESO_TELHA_MM = {0.43: 0.045, 0.50: 0.055, 0.65: 0.070, 0.80: 0.085}
PESO_TELHA_PADRAO = 0.055

# tolerâncias geométricas, mm
TOL_PONTA = 320.0        # a ponta da diagonal pode ficar até isto do ponto de trabalho
TOL_NO = 100.0           # pontos a menos disto viram o mesmo nó
TOL_CHAPA = 320.0        # ponta solta a menos disto de um nó liga-se a ele (chapa de nó)
TOL_DUPLA = 45.0         # peças com eixos a menos disto são geminadas
TOL_PLANO = {"superior": 520.0, "inferior": 400.0}   # terça/trava: distância do cruzamento ao banzo
TOL_APOIO = 450.0        # ponto de apoio informado a menos disto de um nó
MARGEM_CRUZAMENTO = 260.0   # a terça/trava pode parar até isto antes do plano da tesoura
G = 9.81e-3              # kN por kg
ESTACOES_TESOURA = 11    # estações dos diagramas nas barras da treliça


# ------------------------------------------------------------------ vetores

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norma(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norma(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _marcas(e) -> dict:
    return (getattr(e, "atributos", None) or {}).get("marcas") or {}


def _grade(e) -> str:
    props = (getattr(e, "atributos", None) or {}).get("propriedades") or {}
    for pset in props.values():
        if isinstance(pset, dict):
            for k in ("Grade", "Material", "MATERIAL", "Aco", "Aço"):
                v = pset.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return ""


def _vertices(e) -> List[Tuple[float, float, float]]:
    if isinstance(e, Chapa):
        o, ex, ey = e.origem, e.eixo_x, e.eixo_y
        return [(o[0] + ex[0] * x + ey[0] * y, o[1] + ex[1] * x + ey[1] * y,
                 o[2] + ex[2] * x + ey[2] * y) for x, y in e.contorno]
    return list(getattr(e, "vertices", None) or [])


def _massa_kg(e) -> float:
    if isinstance(e, Chapa):
        return e.area * e.espessura * 7.85e-6
    if isinstance(e, Solido):
        return e.volume * 7.85e-6
    return 0.0


# ------------------------------------------------------------------ peças

class _Peca:
    """Uma barra do modelo (sólido) com o que o cálculo precisa dela."""
    __slots__ = ("ent", "marca", "conjunto", "nome_perfil", "perfil", "aco", "tipo",
                 "a", "b", "L", "id")

    def __init__(self, ent, marca, conjunto, nome_perfil, perfil, aco, tipo, eixo):
        self.ent = ent
        self.id = ent.id
        self.marca = marca
        self.conjunto = conjunto
        self.nome_perfil = nome_perfil
        self.perfil = perfil
        self.aco = aco
        self.tipo = tipo
        self.a, self.b = eixo
        self.L = _norma(_sub(self.b, self.a))


class _CorpoDaBarra:
    """Uma `Barra` vestida de sólido, para o cálculo ter um caminho só.

    O reconhecimento de tesouras, a classificação de banzo/diagonal/montante e o
    agrupamento por instância foram escritos para os sólidos facetados do IFC de fábrica
    e trabalham sobre `vertices`. Uma barra paramétrica (modelo desenhado em 2D ou gerado
    do galpão) não os tem, então aqui ela ganha os oito cantos da sua caixa — o suficiente
    para a caixa envolvente, os eixos por PCA e a posição na elevação, que é tudo o que
    aquele caminho pede.
    """
    __slots__ = ("id", "nome", "camada", "atributos", "vertices", "barra")

    def __init__(self, b, perfil):
        self.id = b.id
        self.nome = b.nome
        self.camada = b.camada
        self.atributos = dict(b.atributos or {})
        self.atributos.setdefault("tipo_ifc", b.tipo_ifc())
        self.barra = b
        h = (perfil.d or 100.0) / 2.0 if perfil else 50.0
        w = (perfil.bf or perfil.d or 100.0) / 2.0 if perfil else 50.0
        d = _unit(_sub(b.fim, b.inicio))
        cima = (0.0, 0.0, 1.0) if abs(d[2]) < 0.95 else (1.0, 0.0, 0.0)
        n = _unit(_cruz(d, cima))
        v = _unit(_cruz(n, d))
        self.vertices = [
            tuple(p[i] + v[i] * sv * h + n[i] * sn * w for i in range(3))
            for p in (b.inicio, b.fim) for sv, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]


def _eixo_pca(ent):
    from nucleo2d.detalhe.base import _eixo_da_peca
    return _eixo_da_peca(ent)


def _aco_da_peca(e, perfil: Perfil, par: dict) -> str:
    g = _grade(e)
    if g in mat.ACOS:
        return g
    if perfil.tipo == "Ue" or perfil.dados.get("formado_a_frio"):
        return par["aco_frio"]
    return par["aco_laminado"]


def _perfil_de(nome: str, marca: str, trocas: dict, cache: dict) -> Optional[Perfil]:
    chave = (marca, nome)
    if chave in cache:
        return cache[chave]
    p = None
    troca = (trocas or {}).get(marca)
    if troca:
        p = perfis_fabrica.perfil_de_fabrica(troca)
        if p is None:
            try:
                from nucleo3d import geometria
                p = geometria.resolver_perfil(troca)
            except Exception:
                p = None
    if p is None:
        try:
            p = perfis_fabrica.perfil_de_fabrica(nome)
        except Exception:
            p = None
    cache[chave] = p
    return p


def _por_marca(dic: dict) -> dict:
    """O nomes.json indexa por posição fundida ("M5 / M6"): abre para cada marca."""
    saida = {}
    for chave, valor in (dic or {}).items():
        for m in str(chave).split(" / "):
            saida[m.strip()] = valor
    return saida


def _mapas_de_nomes(nomes: dict):
    """(tipo por marca, tipo por conjunto, nome por marca de posição, nome por conjunto)."""
    tipos = _por_marca(nomes.get("tipos"))
    tipos_conj = _por_marca(nomes.get("tipos_conjuntos"))
    ifc = nomes.get("ifc") or {}
    nomes_pos = dict(_por_marca(nomes.get("posicoes")))
    nomes_pos.update({k: v for k, v in ifc.items() if k not in tipos_conj})
    nomes_conj = dict(_por_marca(nomes.get("conjuntos")))
    nomes_conj.update(nomes.get("ifc_conjuntos") or {})
    return tipos, tipos_conj, nomes_pos, nomes_conj


def _levantar_pecas(doc: Documento, nomes: dict, par: dict, avisos: List[str]):
    """Barras do modelo com perfil de cálculo, e as demais coisas de que o cálculo
    precisa (telhas, castanhas, chapas por conjunto)."""
    tipos = _mapas_de_nomes(nomes)[0]
    cache: Dict[tuple, Optional[Perfil]] = {}
    pecas: List[_Peca] = []
    sem_perfil: collections.Counter = collections.Counter()
    telhas: List[dict] = []
    castanhas: List[Tuple[float, float, float]] = []
    chapas_por_conjunto: Dict[str, List] = collections.defaultdict(list)
    # Barras de verdade (modelo desenhado em 2D ou gerado do galpão) entram direto: o
    # eixo já é o eixo, e o perfil já é do catálogo. Os sólidos do IFC de fábrica passam
    # pelo reconhecimento de nome e pelo eixo por PCA, logo abaixo.
    for b in doc.barras:
        m = _marcas(b)
        perfil = _perfil_de(b.perfil, str(m.get("posicao") or b.id), par.get("trocas") or {}, cache)
        if perfil is None:
            sem_perfil[b.perfil] += 1
            continue
        pecas.append(_Peca(_CorpoDaBarra(b, perfil), str(m.get("posicao") or b.id),
                           str(m.get("conjunto") or ""), b.perfil, perfil,
                           b.aco or _aco_da_peca(b, perfil, par),
                           str(tipos.get(str(m.get("posicao") or "")) or b.papel or ""),
                           (tuple(b.inicio), tuple(b.fim))))
    for e in list(doc.solidos) + list(doc.chapas):
        m = _marcas(e)
        marca = str(m.get("posicao") or "")
        conj = str(m.get("conjunto") or "")
        nome_perfil = str(m.get("perfil") or e.nome or "")
        tipo = str(tipos.get(marca) or "")
        cam = str(getattr(e, "camada", "") or "")
        if cam.lower().startswith("paraf") or nome_perfil.upper().startswith("BOLT"):
            continue
        if tipo == "telha" or nome_perfil.upper().startswith("TELHA") or cam.lower().startswith("telha"):
            verts = _vertices(e)
            if verts:
                telhas.append({"nome": nome_perfil, "verts": verts})
            continue
        if tipo == "castanha":
            verts = _vertices(e)
            if verts:
                castanhas.append(tuple(sum(v[i] for v in verts) / len(verts) for i in range(3)))
            continue
        if isinstance(e, Chapa) or not perfis_fabrica.eh_barra_de_calculo(nome_perfil):
            if conj:
                chapas_por_conjunto[conj].append(e)
            continue
        perfil = _perfil_de(nome_perfil, marca, par.get("trocas") or {}, cache)
        if perfil is None:
            sem_perfil[nome_perfil] += 1
            continue
        eixo = _eixo_pca(e)
        if not eixo:
            continue
        pecas.append(_Peca(e, marca, conj, nome_perfil, perfil, _aco_da_peca(e, perfil, par), tipo, eixo))
    for nome, n in sem_perfil.most_common():
        avisos.append("perfil \"%s\" não reconhecido: %d peça(s) fora do cálculo" % (nome, n))
    return pecas, telhas, castanhas, chapas_por_conjunto


# ------------------------------------------------------------------ tesoura

class _Membro:
    """Barra da tesoura no plano (mm): a, b em (x, y) do plano; n peças geminadas."""
    __slots__ = ("pecas", "tipo", "a", "b", "n", "marca", "perfil", "aco", "posicao")

    def __init__(self, peca: _Peca, tipo: str, a, b):
        self.pecas = [peca]
        self.tipo = tipo
        self.a, self.b = a, b
        self.n = 1
        self.marca = peca.marca
        self.perfil = peca.perfil
        self.aco = peca.aco
        self.posicao = ""          # "superior" / "inferior" / "" para banzos


class _Tesoura:
    def __init__(self, conjunto: str, indice: int, pecas: List[_Peca], chapas: List):
        self.conjunto = conjunto
        self.indice = indice
        self.pecas = pecas
        self.chapas = chapas
        self.avisos: List[str] = []
        self.c = (0.0, 0.0, 0.0)
        self.u = (1.0, 0.0, 0.0)
        self.v = (0.0, 0.0, 1.0)
        self.w = (0.0, 1.0, 0.0)
        self.membros: List[_Membro] = []
        self.nos: List[Tuple[float, float]] = []
        self.apoios: List[int] = []
        self.barras: List[dict] = []          # {"membro", "ni", "nf", "rotula"}
        self.tercas: List[dict] = []          # pontos de terça no banzo superior
        self.travas: List[dict] = []          # pontos de travamento no banzo inferior
        self.modelo: Optional[analise.Modelo] = None
        self.combos: Dict[str, str] = {}
        self.env = None
        self.resultados: Dict[str, analise.ResultadoAnalise] = {}
        self.vao_mm = 0.0
        self.theta = 0.0
        self.chave = "%s#%d" % (conjunto, indice + 1)

    # --- coordenadas
    def p2(self, p) -> Tuple[float, float]:
        d = _sub(p, self.c)
        return (_dot(d, self.u), _dot(d, self.v))

    def p3(self, x: float, y: float) -> Tuple[float, float, float]:
        return tuple(self.c[i] + self.u[i] * x + self.v[i] * y for i in range(3))

    def dist_plano(self, p) -> float:
        return abs(_dot(_sub(p, self.c), self.w))

    def montar_geometria(self):
        from nucleo2d.detalhe.conjuntos import _classificar_pecas_do_conjunto, _eixos_do_conjunto
        ents = [p.ent for p in self.pecas]
        self.c, self.u, self.v, self.w = _eixos_do_conjunto(ents)
        # a vertical do desenho é a vertical da obra projetada no plano; a normal
        # horizontal — uma tesoura montada em pé
        classes = _classificar_pecas_do_conjunto(ents)
        por_id = {p.id: p for p in self.pecas}
        membros: List[_Membro] = []
        for pid, classe in classes.items():
            peca = por_id.get(pid)
            if peca is None:
                continue
            if classe not in ("BANZOS", "MONTANTES", "DIAGONAIS"):
                continue
            tipo = {"BANZOS": "banzo", "MONTANTES": "montante", "DIAGONAIS": "diagonal"}[classe]
            a, b = self.p2(peca.a), self.p2(peca.b)
            if a[0] > b[0]:
                a, b = b, a
            membros.append(_Membro(peca, tipo, a, b))
        # peças geminadas: mesmo eixo → uma barra com n peças
        unicos: List[_Membro] = []
        for m in membros:
            achou = None
            for u in unicos:
                if u.tipo == m.tipo and u.marca == m.marca and \
                        math.dist(u.a, m.a) <= TOL_DUPLA and math.dist(u.b, m.b) <= TOL_DUPLA:
                    achou = u
                    break
            if achou is not None:
                achou.n += 1
                achou.pecas.append(m.pecas[0])
            else:
                unicos.append(m)
        self.membros = unicos
        self._classificar_banzos()
        self._nos_e_barras()

    def _banzos(self) -> List[_Membro]:
        return [m for m in self.membros if m.tipo == "banzo"]

    def _y_no_banzo(self, m: _Membro, x: float) -> Optional[float]:
        if not (min(m.a[0], m.b[0]) - 1.0 <= x <= max(m.a[0], m.b[0]) + 1.0):
            return None
        dx = m.b[0] - m.a[0]
        if abs(dx) < 1e-9:
            return None
        return m.a[1] + (m.b[1] - m.a[1]) * (x - m.a[0]) / dx

    def _classificar_banzos(self):
        banzos = self._banzos()
        for m in banzos:
            xm = (m.a[0] + m.b[0]) / 2.0
            ym = (m.a[1] + m.b[1]) / 2.0
            acima = abaixo = False
            for o in banzos:
                if o is m:
                    continue
                yo = self._y_no_banzo(o, xm)
                if yo is None:
                    continue
                if yo > ym + 40.0:
                    acima = True
                elif yo < ym - 40.0:
                    abaixo = True
            m.posicao = "superior" if not acima else ("inferior" if not abaixo else "meio")
        sup = [m for m in banzos if m.posicao == "superior"]
        if sup:
            angs = [abs(math.degrees(math.atan2(m.b[1] - m.a[1], m.b[0] - m.a[0]))) for m in sup]
            self.theta = sum(angs) / len(angs)

    def _ponto_de_trabalho(self, P, d, proprio: _Membro):
        """Interseção da reta (P, d) com o eixo do banzo mais próximo da ponta P."""
        melhor = None
        for m in self._banzos():
            if m is proprio:
                continue
            ax, ay = m.a
            bx, by = m.b
            ex, ey = bx - ax, by - ay
            den = d[0] * (-ey) - d[1] * (-ex)
            if abs(den) < 1e-9:
                continue
            rx, ry = ax - P[0], ay - P[1]
            s = (rx * (-ey) - ry * (-ex)) / den          # ao longo de d
            t = (d[0] * ry - d[1] * rx) / den            # ao longo do banzo
            Lm = math.hypot(ex, ey)
            if t * Lm < -120.0 or t * Lm > Lm + 120.0:
                continue
            Q = (P[0] + d[0] * s, P[1] + d[1] * s)
            dist = math.dist(P, Q)
            if dist <= TOL_PONTA and (melhor is None or dist < melhor[0]):
                melhor = (dist, Q)
        return melhor[1] if melhor else None

    def _nos_e_barras(self):
        pontos: List[Tuple[float, float]] = []
        pontas: Dict[int, List[Tuple[float, float]]] = {}
        for k, m in enumerate(self.membros):
            L = math.dist(m.a, m.b) or 1.0
            d_ab = ((m.b[0] - m.a[0]) / L, (m.b[1] - m.a[1]) / L)
            fins = []
            for P, d in ((m.a, (-d_ab[0], -d_ab[1])), (m.b, d_ab)):
                Q = self._ponto_de_trabalho(P, d, m) if m.tipo != "banzo" else None
                if Q is None and m.tipo == "banzo":
                    Q = self._ponto_de_trabalho(P, d, m)
                    if Q is not None and math.dist(P, Q) > 150.0:
                        Q = None
                fins.append(Q if Q is not None else P)
            pontas[k] = fins
            pontos.extend(fins)
        # agrupa os pontos em nós
        nos: List[List[float]] = []
        conta: List[int] = []
        indice_de: Dict[Tuple[int, int], int] = {}
        for k, fins in pontas.items():
            for j, P in enumerate(fins):
                achou = None
                for i, n in enumerate(nos):
                    if math.dist(P, (n[0], n[1])) <= TOL_NO:
                        achou = i
                        break
                if achou is None:
                    nos.append([P[0], P[1]])
                    conta.append(1)
                    achou = len(nos) - 1
                else:
                    c = conta[achou]
                    nos[achou][0] = (nos[achou][0] * c + P[0]) / (c + 1)
                    nos[achou][1] = (nos[achou][1] * c + P[1]) / (c + 1)
                    conta[achou] = c + 1
                indice_de[(k, j)] = achou
        # ponta solta (só uma barra no nó) perto de outro nó: é ligação por chapa de nó
        grau = collections.Counter(indice_de.values())
        for k in list(indice_de):
            i = indice_de[k]
            if grau[i] != 1 or len(nos) < 2:
                continue
            j = min((jj for jj in range(len(nos)) if jj != i), key=lambda jj: math.dist(nos[i], nos[jj]))
            if math.dist(nos[i], nos[j]) <= TOL_CHAPA and grau[j] >= 1:
                for kk, ii in list(indice_de.items()):
                    if ii == i:
                        indice_de[kk] = j
                grau[j] += grau[i]
                grau[i] = 0
        # os nós dos outros membros que caem sobre um banzo dividem o banzo
        self.nos = [(n[0], n[1]) for n in nos]
        barras: List[dict] = []
        for k, m in enumerate(self.membros):
            ni, nf = indice_de[(k, 0)], indice_de[(k, 1)]
            if m.tipo != "banzo":
                if ni == nf:
                    self.avisos.append("%s: %s %s com as duas pontas no mesmo nó, ignorado" % (self.chave, m.tipo, m.marca))
                    continue
                barras.append({"membro": k, "ni": ni, "nf": nf, "rotula": True})
                continue
            A, B = self.nos[ni], self.nos[nf]
            L = math.dist(A, B)
            if L < 1.0:
                continue
            ex, ey = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            sobre = []
            for i, n in enumerate(self.nos):
                t = (n[0] - A[0]) * ex + (n[1] - A[1]) * ey
                if -1.0 <= t <= L + 1.0:
                    dist = abs(-(n[0] - A[0]) * ey + (n[1] - A[1]) * ex)
                    if dist <= TOL_NO:
                        sobre.append((t, i))
            sobre.sort()
            seq = []
            for t, i in sobre:
                if not seq or seq[-1] != i:
                    seq.append(i)
            for i0, i1 in zip(seq, seq[1:]):
                barras.append({"membro": k, "ni": i0, "nf": i1, "rotula": False})
        self.barras = self._podar_pontas_livres(self._componente_principal(barras))
        # compacta: só os nós usados ficam, renumerados
        usados = sorted({i for b in self.barras for i in (b["ni"], b["nf"])})
        novo = {i: k for k, i in enumerate(usados)}
        self.nos = [self.nos[i] for i in usados]
        for b in self.barras:
            b["ni"], b["nf"] = novo[b["ni"]], novo[b["nf"]]

    def _podar_pontas_livres(self, barras: List[dict]) -> List[dict]:
        """Barra rotulada com uma ponta em nó de uma barra só é mecanismo (peça de console
        que liga à coluna, fora do modelo): sai, e repete-se até estabilizar."""
        removidas = []
        while True:
            grau = collections.Counter()
            for b in barras:
                grau[b["ni"]] += 1
                grau[b["nf"]] += 1
            soltas = [b for b in barras if b["rotula"] and (grau[b["ni"]] == 1 or grau[b["nf"]] == 1)]
            if not soltas:
                break
            removidas.extend(soltas)
            barras = [b for b in barras if b not in soltas]
        if removidas:
            marcas = sorted({self.membros[b["membro"]].marca for b in removidas})
            self.avisos.append("%s: %d barra(s) de ponta livre (console de apoio) fora do modelo (%s)" % (
                self.chave, len(removidas), ", ".join(marcas)))
        return barras

    def _componente_principal(self, barras: List[dict]) -> List[dict]:
        """Só o trecho conexo que contém os banzos; o resto (peças de console ligadas à
        coluna, que não está no modelo) fica fora, com aviso."""
        pai = list(range(len(self.nos)))

        def raiz(i):
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i
        for b in barras:
            pai[raiz(b["ni"])] = raiz(b["nf"])
        peso = collections.Counter()
        for b in barras:
            if self.membros[b["membro"]].tipo == "banzo":
                peso[raiz(b["ni"])] += 1
        if not peso:
            return barras
        principal = peso.most_common(1)[0][0]
        fora = [b for b in barras if raiz(b["ni"]) != principal]
        if fora:
            marcas = sorted({self.membros[b["membro"]].marca for b in fora})
            self.avisos.append("%s: %d barra(s) soltas da treliça ficaram fora do modelo (%s)" % (
                self.chave, len(fora), ", ".join(marcas)))
        return [b for b in barras if raiz(b["ni"]) == principal]

    def nos_usados(self) -> List[int]:
        return sorted({i for b in self.barras for i in (b["ni"], b["nf"])})

    def definir_apoios(self, pontos_apoio, modo: str):
        """Apoios: nos nós mais próximos dos pontos informados (mm, 3D); sem eles, o nó
        mais baixo de cada extremidade da treliça (é onde ela assenta)."""
        usados = self.nos_usados()
        cands = []
        for c in pontos_apoio or []:
            if self.dist_plano(c) > 600.0:
                continue
            P = self.p2(c)
            i = min(usados, key=lambda k: math.dist(self.nos[k], P))
            if math.dist(self.nos[i], P) <= TOL_APOIO and i not in cands:
                cands.append(i)
        if len(cands) < 2:
            xs = [self.nos[i][0] for i in usados]
            xmin, xmax = min(xs), max(xs)
            faixa = max(0.15 * (xmax - xmin), 400.0)
            esq = [i for i in usados if self.nos[i][0] <= xmin + faixa]
            dir_ = [i for i in usados if self.nos[i][0] >= xmax - faixa]
            # entre os nós baixos da ponta, o mais externo (vão maior, a favor da segurança)
            ye = min(self.nos[i][1] for i in esq)
            yd = min(self.nos[i][1] for i in dir_)
            cands = [min((i for i in esq if self.nos[i][1] <= ye + 250.0), key=lambda i: self.nos[i][0]),
                     max((i for i in dir_ if self.nos[i][1] <= yd + 250.0), key=lambda i: self.nos[i][0])]
            if pontos_apoio:
                self.avisos.append("%s: pontos de apoio informados não caem em nós; apoios nos nós de extremidade" % self.chave)
        cands.sort(key=lambda i: self.nos[i][0])
        self.apoios = cands
        self.vao_mm = self.nos[cands[-1]][0] - self.nos[cands[0]][0]
        self.modo_apoio = modo
        # uma água: todo o banzo superior cai para o mesmo lado
        sup = [m for m in self.membros if m.tipo == "banzo" and m.posicao == "superior"]
        sinais = {1 if (m.b[1] - m.a[1]) > 20.0 else (-1 if (m.b[1] - m.a[1]) < -20.0 else 0) for m in sup}
        self.uma_agua = len(sinais - {0}) <= 1

    # --- ligação com terças e travamentos
    def ponto_no_banzo(self, P2, posicao: str):
        """Barra (índice) e abscissa (mm) do ponto P2 sobre um banzo `posicao`."""
        melhor = None
        for k, b in enumerate(self.barras):
            m = self.membros[b["membro"]]
            if m.tipo != "banzo" or m.posicao != posicao:
                continue
            A, B = self.nos[b["ni"]], self.nos[b["nf"]]
            L = math.dist(A, B)
            if L < 1.0:
                continue
            ex, ey = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            t = (P2[0] - A[0]) * ex + (P2[1] - A[1]) * ey
            dist = abs(-(P2[0] - A[0]) * ey + (P2[1] - A[1]) * ex)
            if -TOL_NO <= t <= L + TOL_NO and dist <= TOL_PLANO[posicao]:
                if melhor is None or dist < melhor[0]:
                    melhor = (dist, k, min(max(t, 0.0), L))
        return (melhor[1], melhor[2]) if melhor else None

    def extremos_do_banzo(self, posicao: str):
        pts = []
        for b in self.barras:
            m = self.membros[b["membro"]]
            if m.tipo == "banzo" and m.posicao == posicao:
                pts.append(self.nos[b["ni"]])
                pts.append(self.nos[b["nf"]])
        if not pts:
            return None
        return min(pts, key=lambda p: p[0]), max(pts, key=lambda p: p[0])


def _tesouras(pecas: List[_Peca], nomes: dict, chapas_por_conjunto, avisos) -> List[_Tesoura]:
    from nucleo2d.detalhe.conjuntos import _instancias
    tipos_conj = _mapas_de_nomes(nomes)[1]
    conjuntos = sorted({p.conjunto for p in pecas if p.conjunto and tipos_conj.get(p.conjunto) == "tesoura"})
    saida: List[_Tesoura] = []
    for conj in conjuntos:
        do_conj = [p for p in pecas if p.conjunto == conj]
        por_id = {p.id: p for p in do_conj}
        chapas = [(c, _vertices(c)) for c in chapas_por_conjunto.get(conj, [])]
        chapas = [(c, tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))) for c, vs in chapas if vs]
        for k, inst in enumerate(_instancias([p.ent for p in do_conj], folga=12.0)):
            ps = [por_id[e.id] for e in inst if e.id in por_id]
            if len(ps) < 4:
                continue
            vs = [v for e in inst for v in e.vertices]
            cx = [(min(v[i] for v in vs) - 150.0, max(v[i] for v in vs) + 150.0) for i in range(3)]
            chs = [c for c, ctr in chapas if all(cx[i][0] <= ctr[i] <= cx[i][1] for i in range(3))]
            t = _Tesoura(conj, k, ps, chs)
            try:
                t.montar_geometria()
            except Exception as exc:              # geometria estranha: avisa e segue
                avisos.append("%s: não montei a geometria (%s)" % (t.chave, exc))
                continue
            if len(t.barras) < 3 or not t._banzos():
                avisos.append("%s: poucas barras reconhecidas, tesoura fora do cálculo" % t.chave)
                continue
            saida.append(t)
    return saida


# ------------------------------------------------------------------ terças e travamentos

def _ligar_barras_soltas(tesouras: List[_Tesoura], soltas: List[_Peca]):
    """Cruzamentos de cada barra fora das tesouras com os planos das tesouras: junto ao
    banzo superior é terça (ponto de carga), junto ao inferior é travamento."""
    cruzamentos: Dict[str, List[dict]] = collections.defaultdict(list)     # id da peça → [{t, tesoura, ...}]
    for p in soltas:
        d = _sub(p.b, p.a)
        for ti, t in enumerate(tesouras):
            den = _dot(d, t.w)
            if abs(den) < 1e-9:
                continue
            s = _dot(_sub(t.c, p.a), t.w) / den
            if s * p.L < -MARGEM_CRUZAMENTO or s * p.L > p.L + MARGEM_CRUZAMENTO:
                continue
            P = tuple(p.a[i] + d[i] * s for i in range(3))
            P2 = t.p2(P)
            achado = t.ponto_no_banzo(P2, "superior")
            if achado is not None:
                reg = {"peca": p, "t": s * p.L, "tesoura": ti, "barra": achado[0], "a": achado[1], "P2": P2, "P3": P}
                t.tercas.append(reg)
                cruzamentos[p.id].append(reg)
                continue
            achado = t.ponto_no_banzo(P2, "inferior")
            if achado is not None:
                t.travas.append({"peca": p, "barra": achado[0], "a": achado[1], "P2": P2})
    return cruzamentos


def _correntes(cruzamentos: Dict[str, List[dict]], soltas: List[_Peca]) -> Dict[str, int]:
    """Linhas de correntes por vão de cada terça (marca): barras curtas fora das tesouras
    cuja ponta encosta no eixo da terça entre dois cruzamentos com tesoura. Vale a
    mediana entre os vãos da posição."""
    tercas = {}
    for pid, lista in cruzamentos.items():
        if len(lista) >= 2:
            tercas[pid] = lista[0]["peca"]
    if not tercas:
        return {}
    curtas = [p for p in soltas if p.id not in tercas and p.L <= 3500.0]
    por_marca: Dict[str, List[int]] = collections.defaultdict(list)
    for pid, terca in tercas.items():
        d = _unit(_sub(terca.b, terca.a))
        ts = sorted(r["t"] for r in cruzamentos[pid])
        toques = []
        for c in curtas:
            for P in (c.a, c.b):
                v = _sub(P, terca.a)
                t = _dot(v, d)
                if t < -50.0 or t > terca.L + 50.0:
                    continue
                perp = _norma(tuple(v[i] - d[i] * t for i in range(3)))
                if perp <= 220.0:
                    toques.append(t)
                    break
        for t0, t1 in zip(ts, ts[1:]):
            n = sum(1 for t in toques if t0 + 150.0 < t < t1 - 150.0)
            por_marca[terca.marca].append(n)
    saida = {}
    for marca, ns in por_marca.items():
        ns.sort()
        saida[marca] = ns[len(ns) // 2]
    return saida


def _tributarias(tesouras: List[_Tesoura], cruzamentos: Dict[str, List[dict]]):
    """Largura tributária (ao longo do banzo, mm) e comprimento tributário (ao longo da
    terça, mm) de cada ponto de terça."""
    for t in tesouras:
        if not t.tercas:
            continue
        ext = t.extremos_do_banzo("superior")
        pts = sorted(t.tercas, key=lambda r: r["P2"][0])
        for i, r in enumerate(pts):
            esq = math.dist(pts[i - 1]["P2"], r["P2"]) / 2.0 if i > 0 else (math.dist(ext[0], r["P2"]) if ext else 0.0)
            dir_ = math.dist(r["P2"], pts[i + 1]["P2"]) / 2.0 if i + 1 < len(pts) else (math.dist(r["P2"], ext[1]) if ext else 0.0)
            r["largura"] = esq + dir_
    for pid, lista in cruzamentos.items():
        lista.sort(key=lambda r: r["t"])
        p = lista[0]["peca"]
        for i, r in enumerate(lista):
            esq = (r["t"] - lista[i - 1]["t"]) / 2.0 if i > 0 else r["t"]
            dir_ = (lista[i + 1]["t"] - r["t"]) / 2.0 if i + 1 < len(lista) else (p.L - r["t"])
            r["comprimento"] = max(esq, 0.0) + max(dir_, 0.0)
            r["vao"] = max((r["t"] - lista[i - 1]["t"]) if i > 0 else 0.0,
                           (lista[i + 1]["t"] - r["t"]) if i + 1 < len(lista) else 0.0)


# ------------------------------------------------------------------ cargas

def _peso_telha(telhas: List[dict], par: dict) -> float:
    if par.get("telha"):
        return float(par["telha"])
    esp = []
    for t in telhas:
        nome = t["nome"].upper().replace(",", ".")
        for tok in nome.replace("MM", " ").split():
            try:
                v = float(tok)
            except ValueError:
                continue
            if 0.3 <= v <= 1.2:
                esp.append(v)
                break
    if not esp:
        return PESO_TELHA_PADRAO
    e = max(esp)
    return PESO_TELHA_MM.get(round(e, 2), 0.055 + (e - 0.5) * 0.1)


def _vento(tesouras: List[_Tesoura], par: dict, avisos: List[str]) -> dict:
    """Pressões no telhado (kN/m²) por caso de vento, e a memória do vento."""
    vaos = [t.vao_mm for t in tesouras if t.vao_mm > 0]
    b = max(vaos) / 1000.0 if vaos else 10.0
    # comprimento: espalhamento das tesouras ao longo da normal do plano
    w = tesouras[0].w
    ws = [_dot(t.c, w) for t in tesouras]
    esp = (max(ws) - min(ws)) / max(len(tesouras) - 1, 1) if len(tesouras) > 1 else 5000.0
    a = ((max(ws) - min(ws)) + esp) / 1000.0 if len(tesouras) > 1 else b
    a = max(a, b)
    theta = sum(t.theta for t in tesouras) / len(tesouras)
    if par.get("altura_beiral"):
        h = float(par["altura_beiral"])
    else:
        zs = [t.p3(*t.nos[i])[2] for t in tesouras for i in t.apoios]
        h = max(sum(zs) / len(zs) / 1000.0, 1.0) if zs else 6.0
    hb = h
    try:
        vg = cargas.pressoes_galpao(b, a, hb, theta, V0=par["v0"] or None, cidade=par.get("cidade") or None,
                                    categoria=par["categoria"], classe=par["classe"], S1=par["s1"],
                                    grupo=par["grupo"], aberturas=par["aberturas"])
    except ErroDeDados as exc:
        avisos.append("vento: %s — adotada a sucção de referência −0,9·q" % exc)
        vg = None
    casos = {}
    if vg is not None:
        tab = vg.tabela()

        def pega(direcao, chaves, cpi):
            vals = [l["p (kN/m²)"] for l in tab if l["direção"] == direcao and abs(l["Cpi"] - cpi) < 1e-6
                    and any(c in l["superfície"].lower() for c in chaves)]
            return min(vals) if vals else 0.0
        for c in vg.casos_cpi:
            rot = "cpi%+.1f" % c.valor
            eb = pega("transversal", ["telhado barlavento"], c.valor)
            es = pega("transversal", ["telhado sotavento"], c.valor)
            lo = pega("longitudinal", ["telhado"], c.valor)
            casos["V90 esq %s" % rot] = {"esq": eb, "dir": es, "descricao": "vento perpendicular à cumeeira pela esquerda, %s" % c.nome}
            casos["V90 dir %s" % rot] = {"esq": es, "dir": eb, "descricao": "vento perpendicular à cumeeira pela direita, %s" % c.nome}
            casos["V0 %s" % rot] = {"esq": lo, "dir": lo, "descricao": "vento paralelo à cumeeira, %s" % c.nome}
        memoria = {"V0": vg.V0, "S1": vg.S1, "S2": round(vg.S2, 3), "S3": vg.S3, "Vk": round(vg.Vk, 2),
                   "q": round(vg.q, 4), "b": round(b, 2), "a": round(a, 2), "h": round(hb, 2),
                   "theta": round(theta, 2), "categoria": vg.categoria, "classe": vg.classe,
                   "casos": {k: {"esq": round(v["esq"], 4), "dir": round(v["dir"], 4), "descricao": v["descricao"]} for k, v in casos.items()},
                   "observacoes": list(vg.observacoes)}
    else:
        q = 0.613 * (par["v0"] ** 2) / 1000.0
        casos["V cpi+0.2"] = {"esq": -1.1 * q, "dir": -0.6 * q, "descricao": "sucção de referência"}
        memoria = {"V0": par["v0"], "q": round(q, 4), "b": b, "a": a, "h": hb, "theta": theta, "casos": casos}
    return {"casos": casos, "memoria": memoria, "theta": theta, "b": b, "a": a, "h": hb}


def _carregar_tesoura(t: _Tesoura, g_cob: float, sc: float, vento: dict, par: dict):
    """Casos elementares no modelo da tesoura: PP, SC e um por caso de vento."""
    m = t.modelo
    M = 1 / 100.0                                   # kN/m → kN/cm
    m.caso("PP")
    m.caso("SC")
    # peso próprio das barras (kN/m) + chapas de nó rateadas pelo comprimento
    massa_chapas = sum(_massa_kg(c) for c in t.chapas)
    L_total = sum(math.dist(t.nos[b["ni"]], t.nos[b["nf"]]) for b in t.barras) / 1000.0 or 1.0
    extra = massa_chapas * G / L_total
    for k, b in enumerate(t.barras):
        mb = t.membros[b["membro"]]
        pp = mb.perfil.massa * mb.n * G + extra
        m.distribuida("PP", k, -pp * M, "global_y")
    for caso in vento["casos"]:
        m.caso(caso)
    theta = math.radians(t.theta)
    cos = math.cos(theta)
    xm = sum(n[0] for n in t.nos) / len(t.nos)
    for r in t.tercas:
        area = (r.get("largura", 0.0) / 1000.0) * (r.get("comprimento", 0.0) / 1000.0)      # m² de superfície
        if area <= 0:
            continue
        pp_terca = r["peca"].perfil.massa * G * (r.get("comprimento", 0.0) / 1000.0)
        Pg = g_cob * area + pp_terca
        Ps = sc * area * cos
        k, a = r["barra"], r["a"] / 10.0
        a = min(max(a, 0.0), m.comprimento(k))          # arredondamento mm → cm
        m.concentrada("PP", k, -Pg, a, "global_y")
        m.concentrada("SC", k, -Ps, a, "global_y")
        # normal externa da água no ponto
        A, B = t.nos[t.barras[k]["ni"]], t.nos[t.barras[k]["nf"]]
        L = math.dist(A, B) or 1.0
        ex, ey = (B[0] - A[0]) / L, (B[1] - A[1]) / L
        nx, ny = -ey, ex
        if ny < 0:
            nx, ny = -nx, -ny
        lado = "esq" if r["P2"][0] < xm else "dir"
        for caso, v in vento["casos"].items():
            p = min(v["esq"], v["dir"]) if getattr(t, "uma_agua", False) else v[lado]
            F = -p * area                            # sucção (p<0) puxa para fora
            m.concentrada(caso, k, F * nx, a, "global_x")
            m.concentrada(caso, k, F * ny, a, "global_y")


def _combinar(t: _Tesoura, vento: dict) -> Dict[str, str]:
    from nucleo.galpao import _somar
    m = t.modelo
    combos: Dict[str, str] = {}
    m.caso("C1 gravidade")
    _somar(m, "C1 gravidade", {"PP": 1.25, "SC": 1.5})
    combos["C1 gravidade"] = "1,25·PP + 1,5·SC"
    for i, (caso, v) in enumerate(vento["casos"].items(), 1):
        n2 = "C2 sucção %d" % i
        m.caso(n2)
        _somar(m, n2, {"PP": 1.0, caso: 1.4})
        combos[n2] = "1,0·PP + 1,4·Vento (%s)" % v["descricao"]
        n3 = "C3 vento+SC %d" % i
        m.caso(n3)
        _somar(m, n3, {"PP": 1.25, "SC": 1.5 * 0.6, caso: 1.4 * 0.6})
        combos[n3] = "1,25·PP + 0,9·SC + 0,84·Vento (%s)" % v["descricao"]
    m.caso("S rara gravidade")
    _somar(m, "S rara gravidade", {"PP": 1.0, "SC": 1.0})
    combos["S rara gravidade"] = "PP + SC (serviço)"
    pior = min(vento["casos"], key=lambda c: min(vento["casos"][c]["esq"], vento["casos"][c]["dir"]))
    m.caso("S vento")
    _somar(m, "S vento", {"PP": 1.0, pior: 0.3})
    combos["S vento"] = "PP + 0,3·Vento (frequente)"
    return combos


def _montar_modelo(t: _Tesoura):
    m = analise.Modelo("Tesoura %s" % t.chave)
    for i, n in enumerate(t.nos):
        apoio = None
        if i in t.apoios:
            if getattr(t, "modo_apoio", "rotulado") == "movel" and i == t.apoios[-1]:
                apoio = (False, True, False)
            else:
                apoio = (True, True, False)
        m.add_no(n[0] / 10.0, n[1] / 10.0, apoio, "n%d" % i)
    for k, b in enumerate(t.barras):
        mb = t.membros[b["membro"]]
        p = mb.perfil
        A = p.A * mb.n
        I = max(p.Ix, 1e-6) * mb.n
        m.add_barra(b["ni"], b["nf"], A, I, rotulo="%s:%d" % (t.chave, k),
                    rotula_i=b["rotula"], rotula_f=b["rotula"])
    t.modelo = m


# ------------------------------------------------------------------ verificação

# A verificação de um membro (qual norma, quais estados-limites) vive em
# `nucleo/verificar.py`, compartilhada com o dimensionamento da tesoura do galpão.
_verificar_frio = verificar.verificar_frio
_verificar_laminado = verificar.verificar_laminado
_verificar_membro = verificar.verificar_membro
_serializar_resultado = verificar.serializar_resultado


# ------------------------------------------------------------------ ligações

#: A chapa de nó fica no plano da tesoura; a chapinha de terça e a de apoio ficam fora
#: dele. Mais do que isto de distância ao plano, a chapa não é de nó (mm).
TOL_PLANO_CHAPA = 25.0
#: Sobreposição mínima da barra sobre a chapa para haver ligação medida (mm).
SOBREPOSICAO_MINIMA = 20.0
#: Até onde a sobreposição é procurada ao longo da barra, a partir do nó (mm).
ALCANCE_SOBREPOSICAO = 800.0


def _pontos_da_chapa_no_plano(t: _Tesoura, ch) -> Tuple[List[Tuple[float, float]], List[dict], float]:
    """Contorno e furos da chapa projetados no plano da tesoura (mm), e a distância do
    centro da chapa ao plano. Só para `Chapa` paramétrica (a do detalhamento)."""
    ex, ey, o = ch.eixo_x, ch.eixo_y, ch.origem

    def mundo(x, y):
        return tuple(o[i] + ex[i] * x + ey[i] * y for i in range(3))

    contorno = [t.p2(mundo(x, y)) for x, y in (ch.contorno or [])]
    furos = []
    for f in ch.furos or []:
        p = t.p2(mundo(float(f.get("x", 0.0)), float(f.get("y", 0.0))))
        d = float(f.get("diametro") or max(float(f.get("largura") or 0.0), float(f.get("altura") or 0.0)))
        furos.append({"p": p, "d": d})
    if not contorno:
        return [], [], float("inf")
    centro = mundo(sum(x for x, _ in ch.contorno) / len(ch.contorno),
                   sum(y for _, y in ch.contorno) / len(ch.contorno))
    return contorno, furos, t.dist_plano(centro)


def _chapas_de_no(t: _Tesoura) -> Dict[int, dict]:
    """{índice do nó: chapa de nó} — a chapa paramétrica no plano da tesoura mais perto
    de cada nó, dentro de TOL_CHAPA. Chapa sem contorno ou fora do plano (suporte de
    terça, chapa de apoio) fica de fora."""
    from nucleo3d.modelo import Chapa
    candidatas = []
    for ch in t.chapas:
        if not isinstance(ch, Chapa):
            continue
        contorno, furos, fora = _pontos_da_chapa_no_plano(t, ch)
        if len(contorno) < 3 or fora > max(TOL_PLANO_CHAPA, 3.0 * float(ch.espessura or 0.0)):
            continue
        cx = sum(p[0] for p in contorno) / len(contorno)
        cy = sum(p[1] for p in contorno) / len(contorno)
        candidatas.append({"ent": ch, "contorno": contorno, "furos": furos, "centro": (cx, cy)})
    saida: Dict[int, dict] = {}
    for i in t.nos_usados():
        n = t.nos[i]
        melhor = None
        for c in candidatas:
            d = math.dist(n, c["centro"])
            if d <= TOL_CHAPA and (melhor is None or d < melhor[0]):
                melhor = (d, c)
        if melhor is not None:
            saida[i] = melhor[1]
    return saida


def _sobreposicao(poligono, Q, d) -> Tuple[float, float]:
    """(início, fim) em mm, medidos do nó Q ao longo de d, do trecho em que a barra está
    sobre a chapa. (0, 0) quando não há sobreposição."""
    from nucleo3d.de_desenho import _dentro
    passo = 4.0
    dentro = [s for s in range(0, int(ALCANCE_SOBREPOSICAO / passo) + 1)
              if _dentro((Q[0] + d[0] * s * passo, Q[1] + d[1] * s * passo), poligono)]
    if not dentro:
        return 0.0, 0.0
    s0 = dentro[0] * passo
    # o trecho que conta é o contínuo a partir da primeira entrada
    fim = dentro[0]
    for s in dentro[1:]:
        if s != fim + 1:
            break
        fim = s
    return s0, fim * passo


def _contato_no_banzo(t: _Tesoura, Q, d, banzos_no_no) -> Optional[dict]:
    """Comprimento de contato da barra com o banzo que passa pelo nó (mm) e o que a
    solda precisa saber do banzo. A barra chega ao banzo num ângulo θ e encosta nele ao
    longo da altura d do perfil: contato = d/sen θ, limitado a três alturas."""
    from nucleo import tesouras
    melhor = None
    for kk, bb in banzos_no_no:
        mb = t.membros[bb["membro"]]
        A, B = t.nos[bb["ni"]], t.nos[bb["nf"]]
        L = math.dist(A, B) or 1.0
        e = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
        sen = abs(-d[0] * e[1] + d[1] * e[0])
        altura = float(mb.perfil.d or mb.perfil.bf or 100.0)
        comp = min(altura / max(sen, 0.2), 3.0 * altura)
        try:
            t_b = tesouras._espessura(mb.perfil)
        except Exception:
            t_b = 0.0
        cand = {"banzo": mb.marca, "comprimento_mm": comp, "t_banzo_mm": t_b, "aco_banzo": mb.aco,
                "angulo_graus": math.degrees(math.asin(min(sen, 1.0)))}
        if melhor is None or comp < melhor["comprimento_mm"]:
            melhor = cand
    return melhor


def _largura_ligada(perfil: Perfil) -> float:
    """Largura da parte da barra que encosta na chapa, cm: a aba da cantoneira, a alma
    do U/Ue (que é o que se solda ou parafusa numa chapa de nó)."""
    if perfil.tipo == "L":
        return max(float(perfil.bf or perfil.d or 50.0), 20.0) / 10.0
    return max(float(perfil.d or perfil.bf or 50.0), 20.0) / 10.0


def _diametro_do_furo(d_furo_mm: float) -> str:
    """Nome comercial do parafuso pelo furo: o furo padrão é d + 1,5 mm (NBR 8800)."""
    alvo = d_furo_mm - 1.5
    nomes = [n for n in mat.DIAMETROS if n.startswith("M")] + [n for n in mat.DIAMETROS if not n.startswith("M")]
    return min(nomes, key=lambda n: (abs(mat.DIAMETROS[n][0] * 10.0 - alvo), 0 if n.startswith("M") else 1))


def _ligacoes_das_tesouras(tes: List[_Tesoura], par: dict, nomes_pos: dict, elementos: Dict[str, dict],
                           avisos: List[str]) -> List[dict]:
    """Chapa de nó de cada nó da tesoura, verificada com a barra que chega nela.

    A geometria vem do modelo: a chapa paramétrica do detalhamento dá espessura, contorno
    e furos; a sobreposição da barra sobre a chapa é medida ao longo do eixo da barra a
    partir do nó. Furos dentro da faixa da barra dizem que a ligação é parafusada (o
    diâmetro sai do furo, o passo e a borda são medidos); sem furo, é soldada, com dois
    cordões de filete ao longo da sobreposição e a perna mínima da Tabela 10 da NBR 8800
    para a chapa mais grossa — que é o que se assume porque o IFC não traz a solda.

    Sem chapa sobre a barra — o caso da treliça leve, em que a diagonal é soldada direto
    no banzo Ue — a ligação é a solda da diagonal no banzo: dois cordões ao longo do
    contato, que mede a altura do banzo dividida pelo seno do ângulo entre os dois, e a
    perna limitada pela chapa mais fina (item 6.2.6.2.2), que na chapa dobrada é ela
    mesma. A chapinha de terça e a chapa de apoio, mesmo perto do nó, não recebem a
    barra e ficam de fora sozinhas: a sobreposição medida é zero.

    O resultado sai agrupado por (chapa ou banzo, barra, tipo), com o pior esforço entre
    todos os nós e tesouras — é assim que a fábrica detalha: uma ligação por posição.
    A compressão é verificada na seção de Whitmore como escoamento, sem flambagem da
    chapa: a chapa de nó no plano da tesoura tem o comprimento livre curto, e isso fica
    declarado na observação.
    """
    from nucleo import ligacoes, tesouras
    grupos: Dict[tuple, dict] = {}
    sem_ligacao = 0
    total = 0
    for t in tes:
        chapas = _chapas_de_no(t)
        for i in t.nos_usados():
            Q = t.nos[i]
            ch = chapas.get(i)
            banzos_no_no = [(kk, bb) for kk, bb in enumerate(t.barras)
                            if not bb["rotula"] and i in (bb["ni"], bb["nf"])]
            for k, b in enumerate(t.barras):
                if not b["rotula"] or i not in (b["ni"], b["nf"]):
                    continue
                total += 1
                mb = t.membros[b["membro"]]
                outro = t.nos[b["nf"] if b["ni"] == i else b["ni"]]
                L = math.dist(Q, outro) or 1.0
                d = ((outro[0] - Q[0]) / L, (outro[1] - Q[1]) / L)
                s0, s1 = _sobreposicao(ch["contorno"], Q, d) if ch is not None else (0.0, 0.0)
                if s1 - s0 < SOBREPOSICAO_MINIMA:
                    # sem chapa recebendo a barra: soldada direto no banzo
                    contato = _contato_no_banzo(t, Q, d, banzos_no_no)
                    if contato is None:
                        sem_ligacao += 1
                        continue
                    ch = None
                    s0, s1 = 0.0, contato["comprimento_mm"]
                eb = t.env.barras[k]
                Nc, Nt = -min(eb.N_min.valor, 0.0), max(eb.N_max.valor, 0.0)
                N = max(Nc, Nt)
                caso = eb.N_min.caso if Nc >= Nt else eb.N_max.caso
                largura = _largura_ligada(mb.perfil)
                # furos na faixa da barra e dentro da sobreposição
                faixa = largura * 10.0 / 2.0 + 6.0
                na_barra = []
                for f in (ch["furos"] if ch is not None else []):
                    rx, ry = f["p"][0] - Q[0], f["p"][1] - Q[1]
                    s = rx * d[0] + ry * d[1]
                    e = abs(-rx * d[1] + ry * d[0])
                    if e <= faixa and s0 - 10.0 <= s <= s1 + 20.0:
                        na_barra.append((s, f["d"]))
                na_barra.sort()
                if ch is None:
                    tipo, suporte = "soldada no banzo", contato["banzo"]
                    esp_sup, aco_sup = contato["t_banzo_mm"], contato["aco_banzo"]
                else:
                    tipo = "parafusada" if na_barra else "soldada"
                    suporte = str((getattr(ch["ent"], "atributos", {}) or {}).get("marcas", {}).get("posicao")
                                  or ch["ent"].nome or "")
                    esp_sup, aco_sup = float(ch["ent"].espessura or 0.0), str(getattr(ch["ent"], "aco", "") or "")
                chave = (suporte, mb.marca, tipo)
                g = grupos.get(chave)
                if g is None or N > g["N"]:
                    grupos[chave] = g = {
                        "chapa": suporte, "barra": mb.marca, "tipo": tipo, "tipo_barra": mb.tipo,
                        "perfil": mb.perfil, "aco_barra": mb.aco, "n": mb.n,
                        "espessura_mm": esp_sup, "aco_chapa": aco_sup,
                        "N": N, "Nc": Nc, "Nt": Nt, "caso": caso,
                        "sobreposicao_mm": s1 - s0, "largura_cm": largura,
                        "furos": [(s - s0, dd) for s, dd in na_barra], "fim_mm": s1 - s0,
                        "angulo_graus": contato["angulo_graus"] if ch is None else None,
                        "nos": 0, "tesouras": set(), "ids": [],
                    }
                g["nos"] += 1
                g["tesouras"].add(t.conjunto)
                ids_novos = ([ch["ent"].id] if ch is not None else []) + [p.id for p in mb.pecas]
                for pid in ids_novos:
                    if pid not in g["ids"] and len(g["ids"]) < 400:
                        g["ids"].append(pid)
    if sem_ligacao:
        avisos.append("%d de %d pontas de diagonal/montante sem chapa de nó nem banzo no nó: a ligação dessas "
                      "pontas não foi verificada" % (sem_ligacao, total))

    saida: List[dict] = []
    for chave in sorted(grupos):
        g = grupos[chave]
        entrada = _entrada_da_ligacao(g, par)
        r = _verificar_ligacao(g["perfil"], entrada, "Ligação %s × %s" % (g["chapa"], g["barra"]))
        crit = r.critica
        item = {
            "chave": "%s × %s" % (g["chapa"], g["barra"]), "chapa": g["chapa"],
            "nome_chapa": nomes_pos.get(g["chapa"], ""), "barra": g["barra"],
            "nome_barra": nomes_pos.get(g["barra"], ""), "tipo_barra": g["tipo_barra"],
            "tipo": g["tipo"], "perfil": g["perfil"].nome, "espessura_mm": round(g["espessura_mm"], 2),
            "aco_chapa": entrada["aco_chapa"], "N_kN": round(g["N"], 2), "caso": g["caso"],
            "sobreposicao_mm": round(g["sobreposicao_mm"], 0), "largura_cm": round(g["largura_cm"], 2),
            "n_parafusos": entrada.get("n_parafusos", 0), "diametro": entrada.get("diametro", ""),
            "perna_mm": round(entrada.get("perna_cm", 0.0) * 10.0, 1) if g["tipo"] != "parafusada" else 0.0,
            "angulo_graus": g.get("angulo_graus"),
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok),
            "governa": crit.titulo if crit else "", "norma": getattr(crit, "norma", "") if crit else "",
            "Sd": round(crit.Sd, 2) if crit else 0.0, "Rd": round(crit.Rd, 2) if crit else 0.0,
            "unidade": getattr(crit, "unidade", "") if crit else "",
            "nos": g["nos"], "tesouras": sorted(g["tesouras"]), "ids": g["ids"],
            "verificacoes": verificar.serializar_resultado(r)["verificacoes"],
            "entrada": entrada,
        }
        saida.append(item)
        # a barra guarda a pior ligação dela: é o que a troca de perfil reverifica
        el = elementos.get(g["barra"])
        if el is not None:
            atual = el.get("ligacao")
            if atual is None or item["aproveitamento"] > atual["aproveitamento"]:
                el["ligacao"] = {"chave": item["chave"], "tipo": g["tipo"], "aproveitamento": item["aproveitamento"],
                                 "ok": item["ok"], "governa": item["governa"]}
                el.setdefault("entrada", {})["ligacao"] = entrada
    return saida


def _entrada_da_ligacao(g: dict, par: dict) -> dict:
    """O que basta para verificar a ligação de novo com outro perfil de barra."""
    from nucleo import ligacoes
    t_g = g["espessura_mm"] / 10.0
    aco_chapa = g["aco_chapa"]
    try:
        mat.aco(aco_chapa)
    except Exception:
        aco_chapa = str(par.get("aco_chapa") or par.get("aco_laminado") or "ASTM A36")
    entrada = {"tipo": g["tipo"], "t_gusset_cm": round(t_g, 3), "aco_chapa": aco_chapa,
               "comprimento_cm": round(g["sobreposicao_mm"] / 10.0, 2), "largura_cm": round(g["largura_cm"], 2),
               "N": round(g["N"], 3), "aco_barra": g["aco_barra"], "n": int(g["n"]),
               "parafuso": str(par.get("parafuso") or "ASTM A307"), "eletrodo": str(par.get("eletrodo") or "E70XX")}
    if g["tipo"] == "soldada no banzo":
        t_b = 0.0
        try:
            from nucleo import tesouras
            t_b = tesouras._espessura(g["perfil"]) / 10.0
        except Exception:
            pass
        entrada.update({"t_banzo_cm": round(g["espessura_mm"] / 10.0, 3), "aco_banzo": g["aco_chapa"],
                        "angulo_graus": round(g.get("angulo_graus") or 90.0, 1),
                        "perna_cm": round(_perna_de_solda(t_g, t_b), 3)})
        return entrada
    if g["tipo"] == "parafusada":
        furos = g["furos"]
        d_furo = sum(dd for _, dd in furos) / len(furos)
        nome = _diametro_do_furo(d_furo)
        d_cm = mat.DIAMETROS[nome][0]
        passos = [b - a for (a, _), (b, _) in zip(furos, furos[1:])]
        passo = (sum(passos) / len(passos) / 10.0) if passos else ligacoes.espacamento_recomendado(d_cm)
        borda = max((g["fim_mm"] - furos[-1][0]) / 10.0, 1.2 * d_cm)
        entrada.update({"n_parafusos": len(furos), "diametro": nome, "passo_cm": round(passo, 2),
                        "borda_cm": round(borda, 2), "d_furo_mm": round(d_furo, 1)})
    else:
        t_b = 0.0
        try:
            from nucleo import tesouras
            t_b = tesouras._espessura(g["perfil"]) / 10.0
        except Exception:
            pass
        entrada["perna_cm"] = round(_perna_de_solda(t_g, t_b), 3)
    return entrada


def _perna_de_solda(t_a: float, t_b: float) -> float:
    """Perna do filete entre duas chapas, cm: a mínima da Tabela 10 para a mais grossa,
    mas nunca maior que a mais fina — na chapa dobrada de 2 mm a perna é a própria chapa
    (NBR 8800, item 6.2.6.2.2)."""
    grossa, fina = max(t_a, t_b), min(x for x in (t_a, t_b) if x > 0) if (t_a > 0 or t_b > 0) else 0.3
    perna = max(mat.perna_minima(grossa), 0.3) if grossa > 0 else 0.3
    return max(min(perna, fina), 0.15)


def _verificar_ligacao(perfil: Perfil, entrada: dict, elemento: str) -> Resultado:
    """Chapa de nó com a barra `perfil`, nos dados guardados em `entrada`."""
    from nucleo import ligacoes, tesouras
    try:
        t_b = tesouras._espessura(perfil) / 10.0
    except Exception:
        t_b = 0.0
    largura = _largura_ligada(perfil)
    N = float(entrada["N"]) / max(int(entrada.get("n") or 1), 1)
    comum = dict(N_Sd=N, t_gusset=float(entrada["t_gusset_cm"]), largura_ligacao=largura,
                 comprimento_ligacao=float(entrada["comprimento_cm"]), aco_gusset=entrada["aco_chapa"],
                 t_barra=t_b or None, aco_barra=entrada.get("aco_barra") or "ASTM A36",
                 eletrodo=entrada.get("eletrodo") or "E70XX", elemento=elemento)
    try:
        if entrada.get("tipo") == "soldada no banzo":
            t_banzo = float(entrada.get("t_banzo_cm") or 0.0)
            perna = _perna_de_solda(t_banzo, t_b)
            try:
                fy = min(mat.aco(entrada.get("aco_banzo") or "ASTM A36").fy,
                         mat.aco(entrada.get("aco_barra") or "ASTM A36").fy)
            except Exception:
                fy = 25.0
            r = Resultado(elemento, perfil=perfil.nome, material=entrada.get("aco_banzo") or "")
            v = ligacoes.filete(perna, float(entrada["comprimento_cm"]), entrada.get("eletrodo") or "E70XX",
                                fy_base=fy, t_base=max(t_banzo, t_b) or None, t_outra=min(t_banzo, t_b) or None,
                                F_Sd=N, n_cordoes=2, nome="%s × banzo" % perfil.nome)
            v.observacao = ("diagonal soldada direto no banzo: dois cordões ao longo do contato "
                            "(altura do banzo / sen %s°), perna %s — o IFC não traz a solda"
                            % (fmt(float(entrada.get("angulo_graus") or 90.0), 0), fmt(perna * 10, 1, "mm")))
            r.add(v)
            r.dados.update({"perna_cm": perna, "comprimento_cm": float(entrada["comprimento_cm"])})
        elif entrada.get("tipo") == "parafusada":
            r = ligacoes.gusset_contraventamento(
                diametro=entrada["diametro"], parafuso=entrada.get("parafuso") or "ASTM A307",
                n_parafusos=int(entrada["n_parafusos"]), passo=float(entrada["passo_cm"]),
                borda=float(entrada["borda_cm"]), gabarito_barra=max(largura / 2.0, 2.0), **comum)
        else:
            perna = float(entrada.get("perna_cm") or mat.perna_minima(max(float(entrada["t_gusset_cm"]), t_b)))
            r = ligacoes.gusset_contraventamento(
                perna_solda=perna, comprimento_solda=float(entrada["comprimento_cm"]), n_cordoes=2, **comum)
            r.dados["perna_cm"] = perna
            for v in r.verificacoes:
                if v.titulo.startswith("Solda"):
                    v.observacao = ("o IFC não traz a solda: adotados dois cordões ao longo da sobreposição, "
                                    "com a perna mínima da Tabela 10 para a chapa mais grossa")
        for v in r.verificacoes:
            if v.titulo.startswith("Seção de Whitmore"):
                v.observacao = "compressão verificada como escoamento da seção de Whitmore, sem flambagem da chapa"
    except ErroDeDados as exc:
        r = Resultado(elemento, perfil=perfil.nome, material=entrada.get("aco_chapa", ""))
        v = Verificacao("Não verificada", Sd=0.0, Rd=1.0, unidade="—")
        v.observacao = str(exc)
        r.add(v)
        r.dados["erro"] = str(exc)
    r.dados.update({"N": N, "largura_ligacao": largura, "t_barra": t_b, "tipo": entrada.get("tipo", "")})
    return r


# ------------------------------------------------------------------ orquestração

def geometria_do_modelo(doc: Documento, nomes: dict, parametros: Optional[dict] = None) -> dict:
    """Só a leitura: tesouras, terças, vão, inclinação, cota do apoio — para preencher o
    diálogo antes de calcular."""
    par = dict(PARAMETROS_PADRAO)
    par.update(parametros or {})
    avisos: List[str] = []
    pecas, telhas, castanhas, chapas_conj = _levantar_pecas(doc, nomes, par, avisos)
    tes = _tesouras(pecas, nomes, chapas_conj, avisos)
    for t in tes:
        t.definir_apoios(par.get("apoios") or [], par["apoio"])
    zs = [t.p3(*t.nos[i])[2] for t in tes for i in t.apoios]
    return {"tesouras": len(tes), "conjuntos": sorted({t.conjunto for t in tes}),
            "vao_m": round(max([t.vao_mm for t in tes] or [0]) / 1000.0, 2),
            "inclinacao_graus": round(sum(t.theta for t in tes) / len(tes), 2) if tes else 0.0,
            "cota_apoio_m": round(sum(zs) / len(zs) / 1000.0, 2) if zs else 0.0,
            "telha_kN_m2": _peso_telha(telhas, par), "telhas": len(telhas),
            "barras": len(pecas), "avisos": avisos}


def calcular(doc: Documento, nomes: dict, parametros: Optional[dict] = None, avisar=None) -> dict:
    par = dict(PARAMETROS_PADRAO)
    par.update({k: v for k, v in (parametros or {}).items() if v is not None})
    avisar = avisar or (lambda *a: None)
    avisos: List[str] = []

    avisar("lendo as peças…")
    pecas, telhas, castanhas, chapas_conj = _levantar_pecas(doc, nomes, par, avisos)
    if not pecas:
        raise ErroDeDados("nenhuma barra com perfil reconhecido no modelo")
    avisar("montando as tesouras…")
    tes = _tesouras(pecas, nomes, chapas_conj, avisos)
    if not tes:
        raise ErroDeDados("não encontrei tesouras no modelo: gere o detalhamento primeiro (é ele que "
                          "classifica os conjuntos) ou confira se o IFC tem conjuntos de treliça")
    for t in tes:
        t.definir_apoios(par.get("apoios") or [], par["apoio"])
        avisos.extend(t.avisos)
    if any(getattr(t, "uma_agua", False) for t in tes):
        avisos.append("cobertura de uma água: as pressões de vento vêm das tabelas de duas águas da "
                      "NBR 6123, com a sucção mais severa das duas águas aplicada em toda a tesoura")
    ids_tesoura = {p.id for t in tes for p in t.pecas}
    soltas = [p for p in pecas if p.id not in ids_tesoura]
    avisar("ligando terças e travamentos…")
    cruz = _ligar_barras_soltas(tes, soltas)
    _tributarias(tes, cruz)
    correntes = _correntes(cruz, soltas) if par.get("correntes") is None else {}

    avisar("cargas e vento…")
    g_telha = _peso_telha(telhas, par)
    g_cob = g_telha + float(par["carga_extra"] or 0.0)
    sc = float(par["sobrecarga"] or 0.0)
    vento = _vento(tes, par, avisos)

    avisar("analisando %d tesouras…" % len(tes))
    _, _, nomes_pos, nomes_conj = _mapas_de_nomes(nomes)
    falhas = []
    for t in tes:
        _montar_modelo(t)
        _carregar_tesoura(t, g_cob, sc, vento, par)
        try:
            t.modelo.validar()
            t.combos = _combinar(t, vento)
            elu = [c for c in t.combos if c.startswith("C")]
            t.env = analise.envoltoria(t.modelo, elu, ESTACOES)
            t.resultados = dict(t.env.resultados)
            for c in t.combos:
                if c not in t.resultados:
                    try:
                        t.resultados[c] = analise.resolver(t.modelo, c, ESTACOES)
                    except Exception:
                        pass
        except Exception as exc:
            falhas.append(t)
            avisos.append("%s: análise falhou (%s)" % (t.chave, exc))
    tes = [t for t in tes if t not in falhas]
    if not tes:
        raise ErroDeDados("nenhuma tesoura pôde ser analisada: " + "; ".join(avisos[-3:]))

    avisar("verificando as peças…")
    # Comprimento total de cada posição no modelo: é o que transforma "kg/m a menos"
    # em "kg a menos na estrutura" quando se troca o perfil.
    comprimento_total: Dict[str, float] = collections.defaultdict(float)
    for p in pecas:
        comprimento_total[p.marca] += p.L / 1000.0
    # esforços por marca entre todas as tesouras
    por_marca: Dict[str, dict] = {}
    for t in tes:
        # comprimentos de travamento lateral por banzo
        gaps = {"superior": _gaps(t, "superior", t.tercas), "inferior": _gaps(t, "inferior", t.travas)}
        for k, b in enumerate(t.barras):
            mb = t.membros[b["membro"]]
            eb = t.env.barras[k]
            L = eb.L
            reg = por_marca.setdefault(mb.marca, {"perfil": mb.perfil, "aco": mb.aco, "n": mb.n, "tipo": mb.tipo,
                                                  "Nc": 0.0, "Nt": 0.0, "M": 0.0, "Lx": 0.0, "Ly": 0.0,
                                                  "caso": "", "tesouras": set(), "posicao": mb.posicao,
                                                  "V": 0.0, "sem_trava": False})
            reg["tesouras"].add(t.conjunto)
            Nmin, Nmax = eb.N_min.valor, eb.N_max.valor
            if -Nmin > reg["Nc"]:
                reg["Nc"] = -Nmin
                reg["caso"] = eb.N_min.caso
            reg["Nt"] = max(reg["Nt"], Nmax)
            Mabs = max(abs(eb.M_max.valor), abs(eb.M_min.valor))
            reg["M"] = max(reg["M"], Mabs)
            reg["V"] = max(reg["V"], abs(eb.V_max.valor), abs(eb.V_min.valor))
            reg["Lx"] = max(reg["Lx"], L)
            if mb.tipo == "banzo":
                g = gaps.get(mb.posicao)
                if mb.posicao == "inferior" and par.get("trava_inferior"):
                    g = float(par["trava_inferior"]) * 100.0
                if g is None:
                    ext = t.extremos_do_banzo(mb.posicao)
                    g = math.dist(*ext) / 10.0 if ext else L
                    reg["sem_trava"] = True
                reg["Ly"] = max(reg["Ly"], g)
            else:
                reg["Ly"] = max(reg["Ly"], L)
    elementos: Dict[str, dict] = {}
    verificacoes: List[dict] = []
    for marca, reg in sorted(por_marca.items()):
        nome = nomes_pos.get(marca, "")
        tit = "%s%s · %s%s da tesoura %s · %s" % (
            marca, (" " + nome) if nome else "", reg["tipo"],
            (" " + reg["posicao"]) if reg["tipo"] == "banzo" and reg["posicao"] else "",
            "/".join(sorted(nomes_conj.get(c, c) for c in reg["tesouras"])), reg["perfil"].nome)
        r = _verificar_membro(reg["perfil"], reg["aco"], reg["Nc"], reg["Nt"], reg["M"], reg["Lx"], reg["Ly"],
                              reg["n"], tit, avisos)
        if reg.get("sem_trava"):
            r.dados["observacao"] = "banzo inferior sem travamento lateral no modelo: L_y = comprimento inteiro"
        crit = r.critica
        elementos[marca] = {
            "nome": nome, "titulo": tit, "tipo": reg["tipo"], "posicao": reg["posicao"],
            "perfil": reg["perfil"].nome, "material": reg["aco"], "n": reg["n"],
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok),
            "governa": crit.titulo if crit else "", "norma": getattr(crit, "norma", "") if crit else "",
            "Sd": round(crit.Sd, 2) if crit else 0.0, "Rd": round(crit.Rd, 2) if crit else 0.0,
            "unidade": getattr(crit, "unidade", "") if crit else "",
            "barras": [], "no_portico": True,
            "dimensionamento": {"M": round(reg["M"] / 100.0, 2), "V": round(reg["V"], 2),
                                "N": round(max(reg["Nc"], reg["Nt"]), 2), "caso": reg["caso"],
                                "Lx_cm": round(reg["Lx"], 1), "Ly_cm": round(reg["Ly"], 1)},
            # o que basta para verificar outro perfil nesta posição, sem refazer a análise
            "entrada": {"tipo": "barra", "Nc": round(reg["Nc"], 3), "Nt": round(reg["Nt"], 3),
                        "M_kNcm": round(reg["M"], 3), "Lx_cm": round(reg["Lx"], 2),
                        "Ly_cm": round(reg["Ly"], 2), "n": reg["n"], "aco": reg["aco"]},
            "comprimento_total_m": round(comprimento_total.get(marca, 0.0), 2),
            "peso_kg": round(reg["perfil"].massa * comprimento_total.get(marca, 0.0), 1),
            "diagrama": None, "valores": {},
        }
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo=reg["tipo"]))

    # ligações: a chapa de nó de cada nó, com a barra que chega nela
    avisar("verificando as ligações…")
    ligacoes_saida = _ligacoes_das_tesouras(tes, par, nomes_pos, elementos, avisos)

    # terças
    avisar("verificando as terças…")
    theta = vento["theta"]
    p_min = min(min(v["esq"], v["dir"]) for v in vento["casos"].values())
    p_max = max(max(v["esq"], v["dir"]) for v in vento["casos"].values())
    por_terca: Dict[str, dict] = {}
    for pid, lista in cruz.items():
        p = lista[0]["peca"]
        reg = por_terca.setdefault(p.marca, {"peca": p, "vao": 0.0, "largura": 0.0, "n": 0})
        reg["n"] += 1
        for r in lista:
            reg["vao"] = max(reg["vao"], r.get("vao", 0.0))
            reg["largura"] = max(reg["largura"], r.get("largura", 0.0))
    for marca, reg in sorted(por_terca.items()):
        p = reg["peca"]
        vao = reg["vao"] / 1000.0
        larg = reg["largura"] / 1000.0
        if vao <= 0.2 or larg <= 0:
            continue
        nome = nomes_pos.get(marca, "")
        pp = p.perfil.massa * G
        g = g_cob * larg + pp
        q_g = 1.25 * g + 1.5 * sc * larg * math.cos(math.radians(theta)) + max(0.0, 1.4 * 0.6 * p_max * larg)
        q_s = max(0.0, 1.4 * abs(min(p_min, 0.0)) * larg - 1.0 * g)
        q_gs = g + sc * larg * math.cos(math.radians(theta))
        q_ss = max(0.0, abs(min(p_min, 0.0)) * larg - g)
        tit = "%s%s · terça · %s" % (marca, (" " + nome) if nome else "", p.perfil.nome)
        try:
            if perfis_fabrica.tipo_de_verificacao(p.perfil) == "frio":
                n_corr = int(par["correntes"]) if par.get("correntes") is not None else int(correntes.get(marca, 0))
                r = nbr14762.terca(perfis_fabrica.secao_frio(p.perfil), p.aco, vao, q_g, q_s,
                                   n_corr, inclinacao=theta,
                                   carga_servico_gravidade=q_gs, carga_servico_succao=q_ss,
                                   limite_flecha_gravidade=float(par["flecha_terca"]), elemento=tit)
            else:
                r = nbr8800.verificar_viga(p.perfil, p.aco, L=vao * 100, q_Sd=max(q_g, q_s) / 100.0,
                                           q_servico=max(q_gs, q_ss) / 100.0, limite="L/%d" % int(par["flecha_terca"]),
                                           elemento=tit)
        except ErroDeDados as exc:
            r = Resultado(tit, perfil=p.perfil.nome, material=p.aco)
            v = Verificacao("Não verificada", Sd=0.0, Rd=1.0, unidade="—")
            v.observacao = str(exc)
            r.add(v)
        crit = r.critica
        caso = "gravidade" if q_g >= q_s else "sucção"
        q = max(q_g, q_s)
        passos = [i / (ESTACOES - 1) for i in range(ESTACOES)]
        elementos[marca] = {
            "nome": nome, "titulo": tit, "tipo": "terca", "posicao": "",
            "perfil": p.perfil.nome, "material": p.aco, "n": 1,
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok),
            "governa": crit.titulo if crit else "", "norma": getattr(crit, "norma", "") if crit else "",
            "Sd": round(crit.Sd, 2) if crit else 0.0, "Rd": round(crit.Rd, 2) if crit else 0.0,
            "unidade": getattr(crit, "unidade", "") if crit else "",
            "barras": [], "no_portico": False,
            "dimensionamento": {"M": round(q * vao * vao / 8.0, 2), "V": round(q * vao / 2.0, 2), "N": 0.0,
                                "caso": caso, "vao_m": round(vao, 2), "largura_m": round(larg, 3),
                                "correntes": (int(par["correntes"]) if par.get("correntes") is not None
                                              else int(correntes.get(marca, 0))),
                                "q_gravidade_kN_m": round(q_g, 3), "q_succao_kN_m": round(q_s, 3)},
            "entrada": {"tipo": "terca", "vao_m": round(vao, 4), "largura_m": round(larg, 4),
                        "q_g": round(q_g, 4), "q_s": round(q_s, 4), "q_gs": round(q_gs, 4),
                        "q_ss": round(q_ss, 4), "theta": round(theta, 3), "aco": p.aco,
                        "correntes": (int(par["correntes"]) if par.get("correntes") is not None
                                      else int(correntes.get(marca, 0))),
                        "flecha": int(par["flecha_terca"]), "g_cob": round(g_cob, 5),
                        "sc": round(sc, 5), "p_min": round(min(p_min, 0.0), 5),
                        "p_max": round(max(p_max, 0.0), 5)},
            "comprimento_total_m": round(comprimento_total.get(marca, 0.0), 2),
            "peso_kg": round(p.perfil.massa * comprimento_total.get(marca, 0.0), 1),
            "diagrama": {"modelo": "viga biapoiada", "vao_m": round(vao, 3), "caso": caso, "q_kN_m": round(q, 3),
                         "s": [round(x, 4) for x in passos],
                         "M": [round(q * vao * vao * x * (1 - x) / 2.0, 3) for x in passos],
                         "V": [round(q * vao * (0.5 - x), 3) for x in passos]},
            "valores": {},
        }
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo="terca"))

    # o que ficou sem verificação
    ids_verif = set(por_marca) | set(por_terca)
    outras = collections.Counter()
    for p in soltas:
        if p.marca not in ids_verif:
            outras[(p.marca, p.tipo or "barra", p.perfil.nome)] += 1
    nao_verificadas = [{"marca": m, "nome": nomes_pos.get(m, ""), "tipo": tp, "perfil": pf, "pecas": n}
                       for (m, tp, pf), n in sorted(outras.items())]
    if nao_verificadas:
        avisos.append("%d posição(ões) fora das tesouras e das terças não foram verificadas (contraventamentos, "
                      "agulhamentos, apoios): ver a lista" % len(nao_verificadas))

    # tesouras típicas (uma por conjunto, a mais solicitada) para os diagramas
    avisar("montando o mapa…")
    tipicas: Dict[str, _Tesoura] = {}
    for t in tes:
        pior = max((max(abs(b.N_min.valor), abs(b.N_max.valor)) for b in t.env.barras), default=0.0)
        grupo = nomes_conj.get(t.conjunto, t.conjunto)
        if grupo not in tipicas or pior > tipicas[grupo]._pior:
            t._pior = pior
            tipicas[grupo] = t
    combos_total: Dict[str, str] = {}
    for t in tes:
        combos_total.update(t.combos)
    ultimas = [c for c in combos_total if c.startswith("C")]
    servico = [c for c in combos_total if c.startswith("S")]
    barras_saida: List[dict] = []
    nos_saida: List[dict] = []
    valores: Dict[str, Dict[str, dict]] = collections.defaultdict(dict)
    for t in tipicas.values():
        for i in t.nos_usados():
            n = t.nos[i]
            nos_saida.append({"nome": "%s n%d" % (t.chave, i), "p": [round(c, 1) for c in t.p3(*n)],
                              "apoiado": i in t.apoios})
        for k, b in enumerate(t.barras):
            mb = t.membros[b["membro"]]
            A, B = t.nos[b["ni"]], t.nos[b["nf"]]
            L = math.dist(A, B) or 1.0
            ex, ey = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            nx, ny = ey, -ex                      # face tracionada pelo momento positivo
            normal = tuple(t.u[i] * nx + t.v[i] * ny for i in range(3))
            # barras curtas (painéis da treliça): 11 estações bastam e o JSON gravado no
            # projeto fica na metade
            diagramas = {}
            for caso, r in t.resultados.items():
                try:
                    diagramas[caso] = _amostrar(r.barras[k], ESTACOES_TESOURA)
                except Exception:
                    continue
            diagramas[ENVOLTORIA] = _envoltoria(diagramas, [c for c in ultimas if c in diagramas], ESTACOES_TESOURA)
            rot = "%s:%d" % (t.chave, k)
            elementos[mb.marca]["barras"].append(rot)
            barras_saida.append({"rotulo": rot, "elemento": mb.marca, "tesoura": t.chave,
                                 "ini": [round(c, 1) for c in t.p3(*A)], "fim": [round(c, 1) for c in t.p3(*B)],
                                 "normal": [round(c, 6) for c in normal], "L_mm": round(L, 1),
                                 "diagramas": diagramas})
            for caso, d in diagramas.items():
                v = valores[mb.marca].setdefault(caso, {"M": 0.0, "V": 0.0, "N": 0.0})
                if caso == ENVOLTORIA:
                    v["M"] = max(v["M"], max((abs(x) for x in d["M_max"] + d["M_min"]), default=0.0))
                    v["V"] = max(v["V"], max((abs(x) for x in d["V_max"] + d["V_min"]), default=0.0))
                    v["N"] = max(v["N"], max((abs(x) for x in d["N_max"] + d["N_min"]), default=0.0))
                else:
                    v["M"] = max(v["M"], max((abs(x) for x in d["M"]), default=0.0))
                    v["V"] = max(v["V"], max((abs(x) for x in d["V"]), default=0.0))
                    v["N"] = max(v["N"], max((abs(x) for x in d["N"]), default=0.0))
    for marca, por_caso in valores.items():
        elementos[marca]["valores"] = {c: {k: round(x, 2) for k, x in v.items()} for c, v in por_caso.items()}
    for marca, el in elementos.items():
        if not el["valores"]:
            fixo = {"M": el["dimensionamento"]["M"], "V": el["dimensionamento"]["V"], "N": el["dimensionamento"]["N"]}
            el["valores"] = {c: dict(fixo) for c in ultimas + servico + [ENVOLTORIA]}

    # serviço: flecha da tesoura
    flecha = None
    for t in tes:
        r = t.resultados.get("S rara gravidade")
        if r is None or t.vao_mm <= 0:
            continue
        u = max(abs(r.deslocamento(i)[1]) for i in t.nos_usados())
        lim = t.vao_mm / 10.0 / float(par["flecha_tesoura"])
        if flecha is None or u / lim > flecha["razao"]:
            flecha = {"u_cm": round(u, 3), "limite_cm": round(lim, 3), "razao": round(u / lim, 3),
                      "criterio": "L/%d" % int(par["flecha_tesoura"]),
                      "rotulo": "Flecha da tesoura %s" % nomes_conj.get(t.conjunto, t.conjunto),
                      "tesoura": t.chave}

    pior = max((el["aproveitamento"] for el in elementos.values() if el.get("aproveitamento") is not None), default=0.0)
    peso_verificado = sum(el.get("peso_kg") or 0.0 for el in elementos.values())
    resumo = {
        "peso_verificado_kg": round(peso_verificado, 1),
        "tesouras": len(tes), "tipos_de_tesoura": len(tipicas), "tercas": len(por_terca),
        "barras_no_modelo": len(pecas), "vao_m": round(max(t.vao_mm for t in tes) / 1000.0, 2),
        "inclinacao_graus": round(theta, 2), "telha_kN_m2": round(g_telha, 3), "sobrecarga_kN_m2": sc,
        "carga_extra_kN_m2": float(par["carga_extra"] or 0.0), "vento": vento["memoria"],
        "parametros": {k: v for k, v in par.items() if k != "trocas"}, "trocas": dict(par.get("trocas") or {}),
        "pior_aproveitamento": round(pior, 3), "reprovadas": sorted(m for m, el in elementos.items() if not el["ok"]),
        "nao_verificadas": nao_verificadas,
        "ligacoes": len(ligacoes_saida),
        "ligacoes_reprovadas": [x["chave"] for x in ligacoes_saida if not x["ok"]],
        "pior_ligacao": round(max((x["aproveitamento"] for x in ligacoes_saida), default=0.0), 3),
    }
    return {
        "ok": True,
        "origem": "ifc",
        "unidades": dict(UNIDADES),
        "grandezas": [dict(x) for x in GRANDEZAS],
        "combinacoes": _combinacoes(combos_total, ultimas, servico),
        "elementos": elementos,
        "ligacoes": ligacoes_saida,
        "portico": {"xs_mm": [0.0], "nos": nos_saida, "barras": barras_saida,
                    "tesouras": [{"chave": t.chave, "conjunto": t.conjunto, "nome": nomes_conj.get(t.conjunto, t.conjunto),
                                  "vao_m": round(t.vao_mm / 1000.0, 2), "barras": len(t.barras), "nos": len(t.nos),
                                  "tercas": len(t.tercas), "travas": len(t.travas)} for t in tipicas.values()]},
        "deformada": {},
        "cargas": {},
        "servico": {"deslocamento": flecha} if flecha else {},
        "verificacoes": verificacoes,
        "resumo": resumo,
        "avisos": avisos,
    }


def alternativas(calculo: dict, marca: str, limite: int = 10, todas: bool = False) -> dict:
    """Perfis do catálogo que podem entrar no lugar do desta posição, **verificados**.

    Usa os esforços já calculados (guardados em `elementos[marca]["entrada"]`), então
    responde na hora: não refaz a análise da tesoura. Cada candidato volta com o
    aproveitamento, a verificação que governa e quanto muda no peso da estrutura —
    o comprimento total daquela posição no modelo vezes a diferença de massa por metro.

    A ressalva que acompanha o resultado: trocar o perfil muda a rigidez e redistribui
    os esforços na treliça. Por isso o aproveitamento aqui é uma **triagem**; ao aplicar
    a troca, o cálculo inteiro é refeito (é o caminho de `trocas` em `calcular`).
    """
    from nucleo import catalogo
    el = (calculo.get("elementos") or {}).get(marca)
    if not el:
        raise ErroDeDados("posição %s não está no cálculo" % marca)
    entrada = el.get("entrada") or {}
    if not entrada:
        raise ErroDeDados("o cálculo gravado é de uma versão anterior, sem os dados para "
                          "verificar outro perfil: recalcule a estrutura")
    atual = el.get("perfil") or ""
    comprimento = float(el.get("comprimento_total_m") or 0.0)
    peso_total = float((calculo.get("resumo") or {}).get("peso_verificado_kg") or 0.0)
    try:
        # Varre a família inteira (dentro da faixa de altura): quando a peça atual não
        # passa, o que interessa é o mais leve que passa — e ele pode estar longe da
        # massa atual. A ordenação final põe quem passa na frente.
        candidatos = catalogo.alternativas(atual, modo="todos", limite=90)
    except ErroDeDados:
        # perfil de fábrica fora do catálogo (U92X40X2.25): oferece o que casa em altura
        p = catalogo.perfil_de(atual)
        alt_familia = "Ue" if (p and p.tipo == "Ue") else (p.tipo if p else "")
        altura = p.d if p else 0.0
        candidatos = [c.dict() for c in catalogo.itens(alt_familia)
                      if altura and 0.6 * altura <= c.altura <= 2.0 * altura][:90]
        for c in candidatos:
            base = p.massa if p else 0.0
            c["massa_atual"] = base
            c["delta_massa"] = round((c["massa"] or 0.0) - base, 3) if base else None
            c["delta_pct"] = round(((c["massa"] or 0.0) - base) / base * 100.0, 1) if base else None
            c["mais_leve"] = bool(base and (c["massa"] or 0.0) < base)
    saida = []
    for c in candidatos:
        perfil = catalogo.perfil_de(c["nome"])
        if perfil is None:
            continue
        r = _verificar_candidato(perfil, entrada, el)
        if r is None:
            continue
        razao, governa, norma, ok = r
        lig = None
        if entrada.get("ligacao"):
            # a barra mais leve pode passar e a chapa de nó reprovar: a lista mostra os dois
            rl = _verificar_ligacao(perfil, entrada["ligacao"], "ligação")
            cl = rl.critica
            lig = {"aproveitamento": round(rl.razao, 3), "ok": bool(rl.ok),
                   "governa": cl.titulo if cl else ""}
        delta_massa = c.get("delta_massa")
        delta_peso = round((delta_massa or 0.0) * comprimento, 1) if delta_massa is not None else None
        saida.append({
            "nome": c["nome"], "familia": c["familia"], "origem": c["origem"],
            "massa": c["massa"], "delta_massa": delta_massa, "delta_pct": c.get("delta_pct"),
            "mais_leve": c.get("mais_leve"), "aproveitamento": round(razao, 3),
            "ok": bool(ok) and (lig is None or lig["ok"]), "ok_barra": bool(ok),
            "governa": governa, "norma": norma, "ligacao": lig,
            "delta_peso_kg": delta_peso,
            "delta_peso_pct": (round(delta_peso / peso_total * 100.0, 2)
                               if delta_peso is not None and peso_total else None),
        })
    # Quem passa vem primeiro, do mais leve ao mais pesado (é o que se procura). Quem não
    # passa é ordenado pelo aproveitamento: quando nada passa, o alto da lista é o que
    # chegou mais perto, e não o mais leve do catálogo, que não serve para nada.
    saida.sort(key=lambda a: (not a["ok"], (a["massa"] or 0.0) if a["ok"] else a["aproveitamento"]))
    return {
        "marca": marca, "nome": el.get("nome", ""), "perfil": atual,
        "aproveitamento": el.get("aproveitamento"), "ok": el.get("ok"),
        "governa": el.get("governa", ""), "tipo": el.get("tipo", ""),
        "comprimento_total_m": comprimento, "peso_kg": el.get("peso_kg"),
        "peso_verificado_kg": peso_total, "ligacao": el.get("ligacao"),
        "alternativas": saida[:limite],
        "aviso": ("Triagem com os esforços do cálculo atual. Trocar o perfil muda a rigidez "
                  "e redistribui os esforços: ao aplicar, o cálculo é refeito inteiro."),
    }


def _verificar_candidato(perfil, entrada: dict, el: dict):
    """(razão, verificação que governa, norma, passou) de um perfil nos esforços guardados."""
    try:
        if entrada.get("tipo") == "terca":
            vao = float(entrada["vao_m"])
            if perfis_fabrica.tipo_de_verificacao(perfil) == "frio":
                r = nbr14762.terca(perfis_fabrica.secao_frio(perfil), entrada["aco"], vao,
                                   float(entrada["q_g"]), float(entrada["q_s"]),
                                   int(entrada.get("correntes") or 0), inclinacao=float(entrada.get("theta") or 0.0),
                                   carga_servico_gravidade=float(entrada["q_gs"]),
                                   carga_servico_succao=float(entrada["q_ss"]),
                                   limite_flecha_gravidade=float(entrada.get("flecha") or 180))
            else:
                q = max(float(entrada["q_g"]), float(entrada["q_s"]))
                r = nbr8800.verificar_viga(perfil, entrada["aco"], L=vao * 100, q_Sd=q / 100.0,
                                           q_servico=max(float(entrada["q_gs"]), float(entrada["q_ss"])) / 100.0,
                                           limite="L/%d" % int(entrada.get("flecha") or 180))
        else:
            r = _verificar_membro(perfil, entrada["aco"], float(entrada["Nc"]), float(entrada["Nt"]),
                                  float(entrada["M_kNcm"]), float(entrada["Lx_cm"]), float(entrada["Ly_cm"]),
                                  int(entrada.get("n") or 1), el.get("titulo", ""), [])
    except Exception:
        return None
    crit = r.critica
    return (r.razao, crit.titulo if crit else "", getattr(crit, "norma", "") if crit else "", r.ok)


def _gaps(t: _Tesoura, posicao: str, pontos: List[dict]) -> Optional[float]:
    """Maior vão livre (cm) entre pontos de contenção lateral ao longo de um banzo."""
    ext = t.extremos_do_banzo(posicao)
    if ext is None:
        return None
    xs = sorted([r["P2"] for r in pontos], key=lambda p: p[0])
    if not xs:
        return None
    seq = [ext[0]] + xs + [ext[1]]
    return max(math.dist(a, b) for a, b in zip(seq, seq[1:])) / 10.0
