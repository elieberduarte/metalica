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

Fora das tesouras e das terças (0.8.9): pilares, longarinas, contraventamentos, correntes e
travamentos do banzo inferior pelos modelos simples do galpão (`_verificar_complementares`).
O topo dos pilares do modelo é o apoio da tesoura (o do meio também).

Limites desta versão (declarados em `avisos`): o IFC não traz solda nem classe de parafuso,
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
from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt, nao_verificada
from nucleo.perfis import Perfil
from nucleo3d.modelo import Chapa, Documento, Solido
from nucleo3d.mapa_esforcos import (ENVOLTORIA, ESTACOES, GRANDEZAS, UNIDADES,
                                    _amostrar, _combinacoes, _envoltoria)

__all__ = ["calcular", "dimensionar", "aplicar_perfis", "PARAMETROS_PADRAO", "geometria_do_modelo"]

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
    "correntes_longarina": None,     # linhas de correntes por vão de longarina; None = nenhuma
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
TOL_PILAR_PLANO = 600.0  # pilar a menos disto do plano da tesoura é pilar dela

#: Papel gravado na barra (modelo desenhado em 2D) → tipo do cálculo.
TIPO_DO_PAPEL = {"pilar": "pilar", "longarina": "longarina", "contraventamento": "contraventamento",
                 "tirante": "contraventamento", "corrente": "corrente", "terça": "terca_cobertura",
                 "terca": "terca_cobertura"}
#: Papéis que são da treliça; os outros ficam fora da tesoura mesmo com a marca de conjunto dela.
PAPEIS_DA_TRELICA = {"banzo": "BANZOS", "montante": "MONTANTES", "diagonal": "DIAGONAIS"}
#: Tipos que nunca são terça nem travamento do banzo, mesmo cruzando o plano da tesoura.
TIPOS_NAO_TERCA = {"pilar", "longarina", "contraventamento", "corrente", "gancho", "chumbador",
                   "barra_roscada", "suporte_contraventamento"}
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
    if p is None and troca:
        p = _perfil_do_catalogo(troca)
    if p is None:
        try:
            p = perfis_fabrica.perfil_de_fabrica(nome)
        except Exception:
            p = None
    if p is None:
        p = _perfil_do_catalogo(nome)
    cache[chave] = p
    return p


def _perfil_do_catalogo(nome: str) -> Optional[Perfil]:
    """O perfil pelo catálogo de peças (barra redonda, laminados dos fornecedores, os
    nomes que o 2D → 3D grava)."""
    try:
        from nucleo import catalogo
        return catalogo.perfil_de(nome)
    except Exception:
        return None


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
        # o papel gravado na barra (pilar, longarina, contraventamento…) vale mais que o
        # tipo que o nomeador deu pela forma: ele veio do desenho
        tipo = TIPO_DO_PAPEL.get(b.papel or "") or str(tipos.get(str(m.get("posicao") or "")) or b.papel or "")
        pecas.append(_Peca(_CorpoDaBarra(b, perfil), str(m.get("posicao") or b.id),
                           str(m.get("conjunto") or ""), b.perfil, perfil,
                           b.aco or _aco_da_peca(b, perfil, par), tipo,
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
        if not tipo and str((getattr(e, "atributos", None) or {}).get("tipo_ifc") or "") == "IfcColumn":
            tipo = "pilar"
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
        # horizontal — uma tesoura montada em pé. A barra desenhada já diz o que é
        # (banzo, montante, diagonal); o sólido do IFC é classificado pela forma.
        if ents and all(isinstance(e, _CorpoDaBarra) for e in ents) and \
                any(e.barra.papel in PAPEIS_DA_TRELICA for e in ents):
            classes = {e.id: PAPEIS_DA_TRELICA.get(e.barra.papel, "") for e in ents}
        else:
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
            # a inclinação do telhado é a do banzo comprido; o joelho da tesoura (peça curta e
            # quase vertical que o canto quebrado deixa como banzo) não entra na média — com
            # ele, a Sala dos Compressores saía com 44° em vez de 11°, e o vento, a sobrecarga
            # e a flexão no eixo fraco de todas as terças iam junto
            def ang(m):
                return abs(math.degrees(math.atan2(m.b[1] - m.a[1], m.b[0] - m.a[0])))

            def comp(m):
                return math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1])
            ref = ang(max(sup, key=comp))
            iguais = [m for m in sup if abs(ang(m) - ref) <= 20.0] or sup
            peso = sum(comp(m) for m in iguais) or 1.0
            self.theta = sum(ang(m) * comp(m) for m in iguais) / peso

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

    def definir_apoios(self, pontos_apoio, modo: str, origem: str = "informados"):
        """Apoios: nos nós mais próximos dos pontos (mm, 3D) — os informados ou o topo dos
        pilares do modelo; o ponto que cai no meio de um painel do banzo ganha um nó ali.
        Sem pontos, o nó mais baixo de cada extremidade da treliça (é onde ela assenta)."""
        usados = self.nos_usados()
        cands = []
        for c in pontos_apoio or []:
            if self.dist_plano(c) > 600.0:
                continue
            P = self.p2(c)
            i = min(usados, key=lambda k: math.dist(self.nos[k], P))
            if math.dist(self.nos[i], P) > TOL_APOIO:
                # nenhum nó perto (o poste do oitão no meio do painel): o banzo ganha um nó;
                # havendo nó até TOL_APOIO, o pilar chega nele, como na obra
                novo = self._no_no_banzo(P)
                if novo is not None:
                    i = novo
                    usados = self.nos_usados()
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
                self.avisos.append("%s: pontos de apoio %s não caem em nós; apoios nos nós de extremidade"
                                   % (self.chave, origem))
        cands.sort(key=lambda i: self.nos[i][0])
        self.apoios = cands
        self.vao_mm = self.nos[cands[-1]][0] - self.nos[cands[0]][0]
        self.modo_apoio = modo
        # uma água: todo o banzo superior cai para o mesmo lado
        sup = [m for m in self.membros if m.tipo == "banzo" and m.posicao == "superior"]
        sinais = {1 if (m.b[1] - m.a[1]) > 20.0 else (-1 if (m.b[1] - m.a[1]) < -20.0 else 0) for m in sup}
        self.uma_agua = len(sinais - {0}) <= 1

    def _no_no_banzo(self, P) -> Optional[int]:
        """Divide o trecho de banzo mais perto de P (até TOL_APOIO) com um nó novo no pé
        da perpendicular; devolve o índice do nó, ou None."""
        melhor = None
        for k, b in enumerate(self.barras):
            if self.membros[b["membro"]].tipo != "banzo":
                continue
            A, B = self.nos[b["ni"]], self.nos[b["nf"]]
            L = math.dist(A, B)
            if L < 1.0:
                continue
            ex, ey = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            t = (P[0] - A[0]) * ex + (P[1] - A[1]) * ey
            d = abs(-(P[0] - A[0]) * ey + (P[1] - A[1]) * ex)
            if 30.0 < t < L - 30.0 and d <= TOL_APOIO and (melhor is None or d < melhor[0]):
                melhor = (d, k, t, A, ex, ey)
        if melhor is None:
            return None
        _d, k, t, A, ex, ey = melhor
        self.nos.append((A[0] + ex * t, A[1] + ey * t))
        i = len(self.nos) - 1
        b = self.barras[k]
        self.barras[k:k + 1] = [dict(b, nf=i), dict(b, ni=i)]
        return i

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


def _fora_da_trelica(p: _Peca) -> bool:
    """Barra desenhada com papel de fora da treliça (pilar, longarina, contraventamento):
    num modelo gerado antes da 0.8.9 ela vinha com a marca de conjunto da tesoura."""
    return isinstance(p.ent, _CorpoDaBarra) and bool(TIPO_DO_PAPEL.get(p.ent.barra.papel or ""))


def _eh_pilar(p: _Peca) -> bool:
    d = _unit(_sub(p.b, p.a))
    return p.tipo == "pilar" and abs(d[2]) >= 0.9


def _apoios_nos_pilares(t: "_Tesoura", pilares: Sequence[_Peca]) -> List[Tuple[float, float, float]]:
    """Topo dos pilares que estão no plano da tesoura e debaixo dela: são os apoios."""
    xs = [t.nos[i][0] for i in t.nos_usados()]
    if not xs:
        return []
    pts = []
    for p in pilares:
        base, topo = sorted((p.a, p.b), key=lambda q: q[2])
        if t.dist_plano(topo) > TOL_PILAR_PLANO or t.dist_plano(base) > TOL_PILAR_PLANO:
            continue
        x = t.p2(topo)[0]
        if min(xs) - 600.0 <= x <= max(xs) + 600.0:
            pts.append(tuple(topo))
    return pts if len(pts) >= 2 else []


def _definir_apoios(tes: List["_Tesoura"], pecas: List[_Peca], par: dict):
    pilares = [p for p in pecas if _eh_pilar(p)]
    for t in tes:
        if par.get("apoios"):
            t.definir_apoios(par["apoios"], par["apoio"])
        else:
            t.definir_apoios(_apoios_nos_pilares(t, pilares), par["apoio"], origem="nos pilares")


def _tesouras(pecas: List[_Peca], nomes: dict, chapas_por_conjunto, avisos) -> List[_Tesoura]:
    from nucleo2d.detalhe.conjuntos import _instancias
    tipos_conj = _mapas_de_nomes(nomes)[1]
    conjuntos = sorted({p.conjunto for p in pecas if p.conjunto and tipos_conj.get(p.conjunto) == "tesoura"})
    saida: List[_Tesoura] = []
    for conj in conjuntos:
        do_conj = [p for p in pecas if p.conjunto == conj and not _fora_da_trelica(p)]
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
        if p.tipo in TIPOS_NAO_TERCA:
            continue
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
            # uma linha de corrente é um ponto da terça: a corrente feita em trechos (um de
            # cada lado da terça, como o galpão monta) encosta duas vezes no mesmo lugar
            n, ultimo = 0, None
            for t in sorted(t for t in toques if t0 + 150.0 < t < t1 - 150.0):
                if ultimo is None or t - ultimo > 150.0:
                    n += 1
                ultimo = t
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
        pares = []
        for c in vg.casos_cpi:
            pA = [l["p (kN/m²)"] for l in tab if l["direção"] == "transversal" and abs(l["Cpi"] - c.valor) < 1e-6
                  and "parede lateral barlavento" in l["superfície"].lower()]
            pB = [l["p (kN/m²)"] for l in tab if l["direção"] == "transversal" and abs(l["Cpi"] - c.valor) < 1e-6
                  and "parede lateral sotavento" in l["superfície"].lower()]
            if pA and pB:
                pares.append((max(pA), min(pB)))
        lat = [l["p (kN/m²)"] for l in tab if "parede lateral" in l["superfície"].lower()]
        oit = [l["p (kN/m²)"] for l in tab if "oitão" in l["superfície"].lower()]
        paredes = {"pares": pares or [(0.8 * vg.q, -0.5 * vg.q)],
                   "lateral_pressao": max(lat + [0.0]), "lateral_succao": min(lat + [0.0]),
                   "oitao_pressao": max(oit + [0.0]), "oitao_succao": min(oit + [0.0])}
        memoria = {"V0": vg.V0, "S1": vg.S1, "S2": round(vg.S2, 3), "S3": vg.S3, "Vk": round(vg.Vk, 2),
                   "q": round(vg.q, 4), "b": round(b, 2), "a": round(a, 2), "h": round(hb, 2),
                   "theta": round(theta, 2), "categoria": vg.categoria, "classe": vg.classe,
                   "casos": {k: {"esq": round(v["esq"], 4), "dir": round(v["dir"], 4), "descricao": v["descricao"]} for k, v in casos.items()},
                   "observacoes": list(vg.observacoes)}
    else:
        q = 0.613 * (par["v0"] ** 2) / 1000.0
        casos["V cpi+0.2"] = {"esq": -1.1 * q, "dir": -0.6 * q, "descricao": "sucção de referência"}
        memoria = {"V0": par["v0"], "q": round(q, 4), "b": b, "a": a, "h": hb, "theta": theta, "casos": casos}
        paredes = {"pares": [(1.0 * q, -0.8 * q)], "lateral_pressao": 1.0 * q, "lateral_succao": -1.1 * q,
                   "oitao_pressao": 1.0 * q, "oitao_succao": -1.1 * q}
    return {"casos": casos, "memoria": memoria, "theta": theta, "b": b, "a": a, "h": hb, "paredes": paredes}


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
    from nucleo.galpao import _somar, combinacoes_com_vento
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
        for nome_c, parcelas, texto in combinacoes_com_vento(caso):
            nome_c = "%s %d" % (nome_c, i)
            m.caso(nome_c)
            _somar(m, nome_c, parcelas)
            combos[nome_c] = "%s (%s)" % (texto, v["descricao"])
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
            elif len(t.apoios) > 2 and i != t.apoios[0]:
                # vários pilares: travar todos na horizontal faria da tesoura um arco que não
                # existe (o pilar cede); um fixo, os outros só na vertical
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


# ------------------------------------------------------------------ fora das tesouras

def _valores_da_terca(ent: dict, ultimas: List[str], servico: List[str]) -> Dict[str, dict]:
    """M e V de uma terça (viga biapoiada) em cada combinação: as de gravidade (C1, C3 e a
    rara de serviço) com q_g, as de sucção (C2 e a de vento) com q_s."""
    L = float(ent["vao_m"])

    def mv(q):
        return {"M": round(q * L * L / 8.0, 2), "V": round(q * L / 2.0, 2), "N": 0.0}
    saida = {}
    for c in ultimas + servico + [ENVOLTORIA]:
        if c == ENVOLTORIA:
            q = max(ent.get("q_g", 0.0), ent.get("q_s", 0.0))
        elif c.startswith("C2"):
            q = ent.get("q_s", 0.0)
        elif c.startswith("S vento"):
            q = ent.get("q_ss", 0.0)
        elif c.startswith("S"):
            q = ent.get("q_gs", 0.0)
        else:
            q = ent.get("q_g", 0.0)
        saida[c] = mv(float(q or 0.0))
    return saida


def _hipoteses_da_terca(r: Resultado, par: dict, marca: str, reg: dict, vao: float, larg: float, theta: float,
                        pp: float, g_cob: float, g_telha: float, sc: float, p_min: float, p_max: float,
                        vento: dict, n_corr: int, g: float, q_sc: float, q_v: float,
                        q_g: float, q_s: float, q_gs: float, q_ss: float):
    """As decisões que o cálculo do IFC toma antes de chamar a rotina da terça — medidas no
    modelo ou vindas do diálogo — escritas por extenso, e os passos que levam da carga por m²
    à carga por metro. Entram antes das hipóteses e dos passos da própria rotina."""
    from nucleo.base import Hipotese, Passo
    n_vaos = int(reg.get("n") or 0)
    casos = vento.get("casos") or {}
    caso_min = min(casos.items(), key=lambda kv: min(kv[1]["esq"], kv[1]["dir"]))[1]["descricao"] if casos else ""
    caso_max = max(casos.items(), key=lambda kv: max(kv[1]["esq"], kv[1]["dir"]))[1]["descricao"] if casos else ""
    mem = vento.get("memoria") or {}
    q_vs = abs(min(p_min, 0.0)) * larg
    hip = [
        Hipotese("vao", "Vão L = %s m: a maior distância entre duas tesouras consecutivas que esta terça "
                        "cruza no modelo (%d cruzamento(s) com tesoura na posição %s). Cada vão é verificado "
                        "como biapoiado." % (fmt(vao, 2), n_vaos, marca), "modelo"),
        Hipotese("largura", "Largura tributária %s m: metade da distância até a terça vizinha de cada lado, "
                            "medida ao longo do banzo (no beiral, até a ponta do banzo). É a faixa de telhado "
                            "que descarrega nesta terça." % fmt(larg, 3), "modelo"),
        Hipotese("inclinacao", "Inclinação do telhado θ = %s°, média das tesouras do modelo." % fmt(theta, 2), "modelo"),
        Hipotese("cargas_area",
                 "Cargas por m² de telhado: telha %s kN/m² %s%s; sobrecarga de uso %s kN/m² em projeção "
                 "horizontal (mínimo da NBR 8800, Anexo B, para coberturas leves); peso próprio da terça "
                 "%s kgf/m = %s kN/m (massa do perfil)."
                 % (fmt(g_telha, 3), "(informada no diálogo)" if par.get("telha") else "(pela espessura no nome da telha)",
                    (" + %s kN/m² de carga extra" % fmt(float(par.get("carga_extra") or 0.0), 3)) if par.get("carga_extra") else "",
                    fmt(sc, 2), fmt(pp * 100, 1), fmt(pp, 4)),
                 "parametro"),
        Hipotese("vento",
                 "Vento pela NBR 6123 com V<sub>0</sub> = %s m/s, categoria %s, classe %s, S<sub>1</sub> = %s, "
                 "S<sub>2</sub> = %s, S<sub>3</sub> = %s → q = %s kN/m²; galpão b = %s m, a = %s m, h = %s m. "
                 "Entre todos os casos de vento e de pressão interna, a terça recebe a pior sucção do telhado "
                 "(%s kN/m², caso '%s') e a pior pressão (%s kN/m²%s). O vento age perpendicular ao telhado."
                 % (fmt(mem.get("V0", par.get("v0")), 0), mem.get("categoria", par.get("categoria")),
                    mem.get("classe", par.get("classe")), fmt(mem.get("S1", 1.0), 2), fmt(mem.get("S2", 1.0), 3),
                    fmt(mem.get("S3", 1.0), 2), fmt(mem.get("q", 0.0), 4), fmt(mem.get("b", 0.0), 2),
                    fmt(mem.get("a", 0.0), 2), fmt(mem.get("h", 0.0), 2), fmt(p_min, 4), caso_min,
                    fmt(max(p_max, 0.0), 4),
                    (", caso '%s'" % caso_max) if p_max > 0 else ", nenhum caso comprime a cobertura"),
                 "parametro"),
        Hipotese("combinacoes",
                 "Combinações últimas da NBR 8681/8800: gravidade 1,25·PP + 1,5·SC + 0,84·V<sub>pressão</sub> "
                 "(sobrecarga principal) e 1,25·PP + 1,2·SC + 1,4·V<sub>pressão</sub> (vento principal), valendo a "
                 "maior; sucção 1,0·PP + 1,4·V<sub>sucção</sub>, com o peso próprio favorável entrando com 1,0 "
                 "(ele segura a terça contra o vento, por isso não se majora). Serviço: PP + SC e PP + V<sub>sucção</sub>.",
                 "norma"),
        Hipotese("correntes",
                 ("%d linha(s) de correntes no vão, informada(s) no diálogo." % n_corr) if par.get("correntes") is not None
                 else ("%d linha(s) de correntes no vão, contadas no modelo: barras curtas (até 3,5 m) fora das "
                       "tesouras cuja ponta encosta no eixo desta terça entre duas tesouras; com vãos diferentes "
                       "vale a mediana." % n_corr),
                 "parametro" if par.get("correntes") is not None else "modelo"),
        Hipotese("flecha_limite", "Limite de flecha na gravidade L/%d (diálogo); na sucção L/120, fixo da rotina."
                 % int(par["flecha_terca"]), "parametro"),
    ]
    r.hipoteses[0:0] = hip
    passos = [
        Passo("Carga permanente por metro", "g = (telha + extra)·largura + peso próprio",
              "%s × %s + %s" % (fmt(g_cob, 3), fmt(larg, 3), fmt(pp, 4)), fmt(g, 3, "kN/m"), "NBR 6120"),
        Passo("Sobrecarga por metro (projeção horizontal → telhado inclinado)", "q<sub>sc</sub> = SC·largura·cos θ",
              "%s × %s × cos %s°" % (fmt(sc, 2), fmt(larg, 3), fmt(theta, 2)), fmt(q_sc, 3, "kN/m"), "NBR 8800, Anexo B"),
        Passo("Vento por metro", "q<sub>v,pressão</sub> = p<sub>máx</sub>·largura; q<sub>v,sucção</sub> = |p<sub>mín</sub>|·largura",
              "%s × %s; %s × %s" % (fmt(max(p_max, 0.0), 4), fmt(larg, 3), fmt(abs(min(p_min, 0.0)), 4), fmt(larg, 3)),
              "%s kN/m; %s kN/m" % (fmt(q_v, 3), fmt(q_vs, 3)), "NBR 6123"),
        Passo("Carga de cálculo, gravidade (a maior das duas combinações)",
              "q<sub>g</sub> = máx(1,25·g + 1,5·q<sub>sc</sub> + 0,84·q<sub>v</sub>; 1,25·g + 1,2·q<sub>sc</sub> + 1,4·q<sub>v</sub>)",
              "máx(1,25×%s + 1,5×%s + 0,84×%s; 1,25×%s + 1,2×%s + 1,4×%s)"
              % (fmt(g, 3), fmt(q_sc, 3), fmt(q_v, 3), fmt(g, 3), fmt(q_sc, 3), fmt(q_v, 3)),
              fmt(q_g, 3, "kN/m"), "NBR 8681, Tabela 1"),
        Passo("Carga de cálculo, sucção (peso próprio favorável)",
              "q<sub>s</sub> = 1,4·|p<sub>mín</sub>|·largura − 1,0·g",
              "1,4 × %s × %s − %s" % (fmt(abs(min(p_min, 0.0)), 4), fmt(larg, 3), fmt(g, 3)), fmt(q_s, 3, "kN/m"),
              "NBR 8681, Tabela 1"),
        Passo("Cargas de serviço (para as flechas)",
              "q<sub>g,ser</sub> = g + q<sub>sc</sub>; q<sub>s,ser</sub> = |p<sub>mín</sub>|·largura − g",
              "%s + %s; %s − %s" % (fmt(g, 3), fmt(q_sc, 3), fmt(q_vs, 3), fmt(g, 3)),
              "%s kN/m; %s kN/m" % (fmt(q_gs, 3), fmt(q_ss, 3)), "NBR 8681, item 5.1.3"),
    ]
    r.cargas[0:0] = passos


def _elemento_extra(marca: str, nome: str, tit: str, tipo: str, r: Resultado, perfil: Perfil, aco: str,
                    dimensionamento: dict, entrada: dict, comprimento_total: Dict[str, float]) -> dict:
    crit = r.critica
    L_tot = comprimento_total.get(marca, 0.0)
    return {
        "nome": nome, "titulo": tit, "tipo": tipo, "posicao": "",
        "perfil": perfil.nome, "material": aco, "n": 1,
        "aproveitamento": round(r.razao, 3), "ok": bool(r.ok), "indeterminada": bool(r.indeterminada),
        "governa": crit.titulo if crit else "", "norma": getattr(crit, "norma", "") if crit else "",
        "Sd": round(crit.Sd, 2) if crit else 0.0, "Rd": round(crit.Rd, 2) if crit else 0.0,
        "unidade": getattr(crit, "unidade", "") if crit else "",
        "barras": [], "no_portico": False, "dimensionamento": dimensionamento, "entrada": entrada,
        "comprimento_total_m": round(L_tot, 2), "peso_kg": round(perfil.massa * L_tot, 1),
        "diagrama": None, "valores": {},
    }


def _verificar_tirante(perfil: Perfil, aco: str, Nc: float, Nt: float, L_cm: float, elemento: str) -> Resultado:
    """Tirante: barra redonda com esticador (rosqueada, pré-tensionada — NBR 8800 5.2.8
    dispensa o L/r ≤ 300) só à tração; outro perfil (cantoneira) pela verificação de barra."""
    if perfil.tipo == "barra":
        return nbr8800.tracao(perfil, aco, N_Sd=Nt, L=L_cm, rosqueada=True, pretensionada=True, elemento=elemento)
    return _verificar_membro(perfil, aco, Nc, Nt, 0.0, L_cm, L_cm, 1, elemento, [])


def _verificar_pilar(perfil: Perfil, aco: str, Nc: float, Nt: float, M: float, H_cm: float, K: float,
                     Ly_cm: float, elemento: str, avisos: List[str]) -> Resultado:
    """Pilar: flexo-compressão com K no plano (NBR 8800) ou pelo MRD (formado a frio, com
    K·H); a tração e a esbeltez dela com o comprimento real, não com K·H."""
    try:
        if perfis_fabrica.tipo_de_verificacao(perfil) == "frio":
            return verificar.verificar_frio(perfil, aco, Nc, Nt, M, K * H_cm, Ly_cm, 1, elemento)
        a = mat.aco(aco)
        r = Resultado(elemento, perfil=perfil.nome, material=a.nome)
        if Nc > 1e-6 and M > 1e-6:
            rc = nbr8800.flexao_composta(perfil, a, N_Sd=Nc, Mx_Sd=M, Lx=H_cm, Ly=Ly_cm, Kx=K, Ky=1.0,
                                         Lb=Ly_cm, Cb=1.0, elemento=elemento)
            r.verificacoes.extend(rc.verificacoes)
        elif Nc > 1e-6:
            rc = nbr8800.compressao(perfil, a, Lx=K * H_cm, Ly=Ly_cm, N_Sd=Nc, elemento=elemento)
            r.verificacoes.extend(rc.verificacoes)
        elif M > 1e-6:
            rf = nbr8800.flexao(perfil, a, M_Sd=M, Lb=Ly_cm, elemento=elemento)
            r.verificacoes.extend(rf.verificacoes)
        if Nt > 1e-6:
            rt = nbr8800.tracao(perfil, a, N_Sd=Nt, L=max(H_cm, Ly_cm), elemento=elemento)
            r.verificacoes.extend(rt.verificacoes)
        if not r.verificacoes:
            r.add(Verificacao("Sem esforço", Sd=0.0, Rd=1.0, unidade="—"))
        return r
    except ErroDeDados as exc:
        r = Resultado(elemento, perfil=perfil.nome, material=aco)
        r.add(nao_verificada(exc))
        return r


def _travamento_do_pilar(p: _Peca, longarinas: Sequence[_Peca]) -> float:
    """Maior trecho do pilar (mm) sem longarina encostada: é o comprimento destravado
    fora do plano."""
    base, topo = sorted((p.a, p.b), key=lambda q: q[2])
    zs = [base[2], topo[2]]
    for o in longarinas:
        ax, ay, bx, by = o.a[0], o.a[1], o.b[0], o.b[1]
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        if L2 < 1.0:
            continue
        t = max(0.0, min(1.0, ((base[0] - ax) * (bx - ax) + (base[1] - ay) * (by - ay)) / L2))
        d = math.hypot(ax + (bx - ax) * t - base[0], ay + (by - ay) * t - base[1])
        z = (o.a[2] + o.b[2]) / 2.0
        if d <= 400.0 and base[2] + 50.0 < z < topo[2] - 50.0:
            zs.append(z)
    zs.sort()
    return max(b - a for a, b in zip(zs, zs[1:]))


def _verificar_complementares(tes: List[_Tesoura], soltas: List[_Peca], cruz: Dict[str, List[dict]],
                              correntes: Dict[str, int], vento: dict, par: dict, g_cob: float, sc: float,
                              nomes_pos: dict, comprimento_total: Dict[str, float], por_marca: Dict[str, dict],
                              avisos: List[str]) -> Tuple[Dict[str, dict], List[dict]]:
    """Pilares, longarinas, contraventamentos, correntes e travamentos do banzo inferior —
    as peças fora das tesouras e das terças, pelos modelos simples do galpão (`nucleo.galpao`):

    * **pilar** debaixo de um apoio da tesoura: N = reação da tesoura (a maior compressão
      entre as combinações últimas) + peso próprio; o de fachada lateral é engastado na base
      e tem a tesoura como escora rotulada no topo (dois pilares ligados: X = 3·H·(w₁ − w₂)/16),
      K = 2,0; o do oitão é biapoiado (base e tesoura) sob o vento no oitão, M = q·H²/8; o
      interno leva só a normal. Fora do plano, o trecho entre longarinas. A maior compressão
      entra com o maior momento (a favor da segurança);
    * **longarina**: a verificação da terça com a pressão do vento no lugar da gravidade,
      na faixa de parede entre as vizinhas (o peso próprio no eixo fraco vai às correntes);
    * **contraventamento** (tirante): o da cobertura é a treliça horizontal que leva metade
      do vento no oitão até os beirais (cortante = F/2, N = cortante·L/profundidade); o da
      parede lateral leva esse cortante até a base; o do oitão, o vento transversal da faixa
      do pórtico da ponta. Barra redonda só à tração;
    * **corrente**: a componente do peso da cobertura ao longo da água, na faixa entre
      correntes (mínimo 2 kN);
    * **travamento do banzo inferior**: 2 % da maior compressão do banzo (NBR 8800, 4.11).
    """
    elementos: Dict[str, dict] = {}
    verificacoes: List[dict] = []
    w0 = tes[0].w
    paredes = vento.get("paredes") or {}
    pares = paredes.get("pares") or [(0.0, 0.0)]
    h = float(vento.get("h") or 6.0)
    b = float(vento.get("b") or 10.0)
    theta = float(vento.get("theta") or 0.0)
    z_top = max((t.p3(*t.nos[i])[2] for t in tes for i in t.nos_usados()), default=h * 1000.0)
    hc = max(z_top / 1000.0, h)
    ws = sorted({round(_dot(t.c, w0)) for t in tes})

    def faixa_w(pos: float) -> float:
        antes = [x for x in ws if x < pos - 200.0]
        depois = [x for x in ws if x > pos + 200.0]
        if not antes and not depois:
            return 5000.0
        return ((pos - antes[-1]) / 2.0 if antes else 0.0) + ((depois[0] - pos) / 2.0 if depois else 0.0)

    def titulo(marca, tipo_txt, perfil):
        nome = nomes_pos.get(marca, "")
        return nome, "%s%s · %s · %s" % (marca, (" " + nome) if nome else "", tipo_txt, perfil.nome)

    pilares = [p for p in soltas if _eh_pilar(p)]
    longarinas = [p for p in soltas if p.tipo == "longarina"]
    z_chao = min((min(p.a[2], p.b[2]) for p in pilares), default=0.0)

    # ---- pilares
    regs: Dict[str, dict] = {}
    sem_tesoura = collections.Counter()
    for p in pilares:
        base, topo = sorted((p.a, p.b), key=lambda q: q[2])
        H = topo[2] - base[2]
        achado = None
        for t in tes:
            if t.env is None or t.dist_plano(topo) > TOL_PILAR_PLANO or t.dist_plano(base) > TOL_PILAR_PLANO:
                continue
            P2 = t.p2(topo)
            for i in t.apoios:
                d = math.dist(t.nos[i], P2)
                if d <= TOL_APOIO + 150.0 and (achado is None or d < achado[0]):
                    achado = (d, t, i)
        if achado is None:
            sem_tesoura[p.marca] += 1
            continue
        _d, t, i = achado
        rea = t.env.reacoes.get(i) or {}
        Ry_max = rea["Ry_max"].valor if "Ry_max" in rea else 0.0
        Ry_min = rea["Ry_min"].valor if "Ry_min" in rea else 0.0
        pp = p.perfil.massa * G * H / 1000.0
        Nc = max(Ry_max, 0.0) + 1.25 * pp
        Nt = max(-Ry_min - pp, 0.0)
        Hm = H / 1000.0
        xs = [t.nos[k][0] for k in t.nos_usados()]
        x = t.nos[i][0]
        pos = _dot(t.c, w0)
        if x <= min(xs) + 300.0 or x >= max(xs) - 300.0:
            trib = faixa_w(pos) / 1000.0
            M = 0.0
            for pA, pB in pares:
                w1 = 1.4 * max(pA, 0.0) * trib
                w2 = 1.4 * max(-pB, 0.0) * trib
                X = 3.0 * Hm * (w1 - w2) / 16.0
                M = max(M, abs(w1 * Hm * Hm / 2.0 - X * Hm), abs(w2 * Hm * Hm / 2.0 + X * Hm))
            K, modelo = 2.0, "fachada lateral: base engastada, tesoura rotulada no topo, vento na parede"
            V = max((1.4 * max(pA, 0.0) * trib * Hm for pA, _pB in pares), default=0.0)
        elif pos <= ws[0] + 200.0 or pos >= ws[-1] - 200.0:
            aps = sorted(t.nos[k][0] for k in t.apoios)
            esq = [a for a in aps if a < x - 10.0]
            dir_ = [a for a in aps if a > x + 10.0]
            trib_u = (((x - esq[-1]) / 2.0 if esq else 0.0) + ((dir_[0] - x) / 2.0 if dir_ else 0.0)) / 1000.0
            q = 1.4 * max(paredes.get("oitao_pressao", 0.0), abs(min(paredes.get("oitao_succao", 0.0), 0.0))) * trib_u
            M, V = q * Hm * Hm / 8.0, q * Hm / 2.0
            K, modelo = 1.0, "oitão: biapoiado na base e na tesoura, vento no oitão"
        else:
            M, V, K, modelo = 0.0, 0.0, 1.0, "interno: só a reação da tesoura"
        Ly = _travamento_do_pilar(p, longarinas)
        reg = regs.setdefault(p.marca, {"peca": p, "Nc": 0.0, "Nt": 0.0, "M": 0.0, "V": 0.0, "Lx": 0.0, "Ly": 0.0,
                                        "H": 0.0, "K": K, "modelo": modelo})
        reg["Nc"] = max(reg["Nc"], Nc)
        reg["Nt"] = max(reg["Nt"], Nt)
        if M * 100.0 >= reg["M"]:
            reg["M"], reg["K"], reg["modelo"] = M * 100.0, K, modelo
        reg["V"] = max(reg["V"], V)
        reg["Lx"] = max(reg["Lx"], K * H / 10.0)
        reg["Ly"] = max(reg["Ly"], Ly / 10.0)
        reg["H"] = max(reg["H"], H)
    for marca, reg in sorted(regs.items()):
        p = reg["peca"]
        nome, tit = titulo(marca, "pilar", p.perfil)
        r = _verificar_pilar(p.perfil, p.aco, reg["Nc"], reg["Nt"], reg["M"], reg["H"] / 10.0, reg["K"],
                             reg["Ly"], tit, avisos)
        r.dados["observacao"] = "pilar " + reg["modelo"]
        elementos[marca] = _elemento_extra(
            marca, nome, tit, "pilar", r, p.perfil, p.aco,
            {"M": round(reg["M"] / 100.0, 2), "V": round(reg["V"], 2), "N": round(max(reg["Nc"], reg["Nt"]), 2),
             "caso": "reação da tesoura + vento", "modelo": reg["modelo"], "altura_m": round(reg["H"] / 1000.0, 2),
             "K": reg["K"], "Lx_cm": round(reg["Lx"], 1), "Ly_cm": round(reg["Ly"], 1)},
            {"tipo": "pilar", "Nc": round(reg["Nc"], 3), "Nt": round(reg["Nt"], 3), "M_kNcm": round(reg["M"], 3),
             "H_cm": round(reg["H"] / 10.0, 2), "K": reg["K"], "Ly_cm": round(reg["Ly"], 2), "aco": p.aco},
            comprimento_total)
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo="pilar"))
    if sem_tesoura:
        avisos.append("pilar(es) sem tesoura apoiada no topo, fora do cálculo: %s"
                      % ", ".join(sorted(sem_tesoura)))

    # ---- longarinas
    regs = {}
    for p in longarinas:
        d = _unit(_sub(p.b, p.a))
        if abs(d[2]) > 0.3:
            continue
        lateral = abs(_dot(d, w0)) >= 0.7
        z = (p.a[2] + p.b[2]) / 2.0
        dp = math.hypot(d[0], d[1]) or 1.0
        zs = [z]
        for o in longarinas:
            if o is p:
                continue
            do = _unit(_sub(o.b, o.a))
            if abs(_dot(do, d)) < 0.95:
                continue
            mx, my = (o.a[0] + o.b[0]) / 2.0 - p.a[0], (o.a[1] + o.b[1]) / 2.0 - p.a[1]
            if abs(-mx * d[1] + my * d[0]) / dp <= 500.0:
                zs.append((o.a[2] + o.b[2]) / 2.0)
        niveis: List[float] = []
        for zz in sorted(zs):
            if not niveis or zz - niveis[-1] > 100.0:
                niveis.append(zz)
        k = min(range(len(niveis)), key=lambda j: abs(niveis[j] - z))
        abaixo = niveis[k - 1] if k > 0 else z_chao
        acima = niveis[k + 1] if k + 1 < len(niveis) else max(h * 1000.0, z)
        faixa = max((acima - abaixo) / 2.0 / 1000.0, 0.3)
        pres = paredes.get("lateral_pressao" if lateral else "oitao_pressao", 0.0)
        suc = paredes.get("lateral_succao" if lateral else "oitao_succao", 0.0)
        reg = regs.setdefault(p.marca, {"peca": p, "vao": 0.0, "faixa": 0.0, "pres": 0.0, "suc": 0.0,
                                        "parede": "lateral" if lateral else "oitão"})
        reg["vao"] = max(reg["vao"], p.L / 1000.0)
        reg["faixa"] = max(reg["faixa"], faixa)
        reg["pres"] = max(reg["pres"], max(pres, 0.0))
        reg["suc"] = min(reg["suc"], min(suc, 0.0))
    # o modelo desenhado raramente traz as correntes da parede: sem informar, uma linha
    # por vão (a do galpão), dita no aviso e trocável no diálogo
    n_corr = int(par["correntes_longarina"]) if par.get("correntes_longarina") is not None else 1
    for marca, reg in sorted(regs.items()):
        p = reg["peca"]
        nome, tit = titulo(marca, "longarina (%s)" % reg["parede"], p.perfil)
        vao, faixa = reg["vao"], reg["faixa"]
        q_p, q_s = 1.4 * reg["pres"] * faixa, 1.4 * abs(reg["suc"]) * faixa
        q_ps, q_ss = reg["pres"] * faixa, abs(reg["suc"]) * faixa
        try:
            if perfis_fabrica.tipo_de_verificacao(p.perfil) == "frio":
                r = nbr14762.terca(perfis_fabrica.secao_frio(p.perfil), p.aco, vao, q_p, q_s, n_corr, inclinacao=0.0,
                                   carga_servico_gravidade=q_ps, carga_servico_succao=q_ss,
                                   limite_flecha_gravidade=float(par["flecha_terca"]), elemento=tit)
            else:
                r = nbr8800.verificar_viga(p.perfil, p.aco, L=vao * 100, q_Sd=max(q_p, q_s) / 100.0,
                                           q_servico=max(q_ps, q_ss) / 100.0, limite="L/%d" % int(par["flecha_terca"]),
                                           elemento=tit)
            for v in r.verificacoes:
                v.titulo = v.titulo.replace("gravidade", "pressão do vento")
        except ErroDeDados as exc:
            r = Resultado(tit, perfil=p.perfil.nome, material=p.aco)
            r.add(nao_verificada(exc))
        q = max(q_p, q_s)
        elementos[marca] = _elemento_extra(
            marca, nome, tit, "longarina", r, p.perfil, p.aco,
            {"M": round(q * vao * vao / 8.0, 2), "V": round(q * vao / 2.0, 2), "N": 0.0,
             "caso": "pressão do vento" if q_p >= q_s else "sucção", "vao_m": round(vao, 2),
             "faixa_m": round(faixa, 3), "parede": reg["parede"], "correntes": n_corr},
            {"tipo": "terca", "vao_m": round(vao, 4), "largura_m": round(faixa, 4), "q_g": round(q_p, 4),
             "q_s": round(q_s, 4), "q_gs": round(q_ps, 4), "q_ss": round(q_ss, 4), "theta": 0.0, "aco": p.aco,
             "correntes": n_corr, "flecha": int(par["flecha_terca"])},
            comprimento_total)
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo="longarina"))

    # ---- contraventamentos e correntes (tirantes)
    q_oit = max(paredes.get("oitao_pressao", 0.0), abs(min(paredes.get("oitao_succao", 0.0), 0.0)))
    area_oitao = b * (h + (hc - h) / 2.0) / 2.0
    F_oitao = 1.4 * q_oit * area_oitao
    cortante = F_oitao / 2.0
    esp_ponta = (ws[1] - ws[0]) / 1000.0 if len(ws) > 1 else 5.0
    p_soma = max((max(pA, 0.0) + max(-pB, 0.0) for pA, pB in pares), default=0.0)
    F_trans = 1.4 * p_soma * (esp_ponta / 2.0) * (h / 2.0)
    vaos_terca = sorted(r_.get("vao", 0.0) for lista in cruz.values() for r_ in lista if r_.get("vao"))
    vao_terca = vaos_terca[len(vaos_terca) // 2] / 1000.0 if vaos_terca else esp_ponta
    ns_corr = sorted(correntes.values()) if correntes else []
    n_linhas = max(ns_corr[len(ns_corr) // 2] if ns_corr else 1, 1)
    agua = (b / 2.0) / max(math.cos(math.radians(theta)), 0.5)
    N_corrente = max(2.0, (1.25 * g_cob + 1.5 * sc) * math.sin(math.radians(theta)) * (vao_terca / (n_linhas + 1)) * agua)
    # a treliça horizontal da cobertura vence o vão entre os beirais: o cortante vai de
    # F/2 no apoio a zero no meio, e o painel leva o da ponta mais perto do apoio
    t0 = tes[0]
    xs0 = [t0.nos[i][0] for i in t0.nos_usados()]
    x_esq, x_dir = (min(xs0), max(xs0)) if xs0 else (0.0, b * 1000.0)
    meio_vao = max((x_dir - x_esq) / 2.0, 1.0)
    regs = {}
    for p in soltas:
        if p.tipo not in ("contraventamento", "corrente"):
            continue
        d = _sub(p.b, p.a)
        L = p.L
        Lh = math.hypot(d[0], d[1])
        zm = (p.a[2] + p.b[2]) / 2.0
        if p.tipo == "corrente":
            plano, N = "corrente", N_corrente
        elif abs(d[2]) <= 0.35 * L and zm >= 0.6 * h * 1000.0:
            plano = "cobertura"
            dist_apoio = min(min(t0.p2(q)[0] - x_esq, x_dir - t0.p2(q)[0]) for q in (p.a, p.b))
            V = cortante * max(1.0 - max(dist_apoio, 0.0) / meio_vao, 0.1)
            N = V * L / max(abs(_dot(d, w0)), 0.2 * L)
        elif Lh > 1.0 and abs(_dot(_unit((d[0], d[1], 0.0)), w0)) >= 0.5:
            plano = "parede lateral"
            N = cortante * L / max(Lh, 0.2 * L)
        else:
            plano = "oitão"
            N = F_trans * L / max(Lh, 0.2 * L)
        reg = regs.setdefault(p.marca, {"peca": p, "N": 0.0, "L": 0.0, "planos": set()})
        reg["N"] = max(reg["N"], N)
        reg["L"] = max(reg["L"], L)
        reg["planos"].add(plano)
    for marca, reg in sorted(regs.items()):
        p = reg["peca"]
        tipo_txt = "corrente" if reg["planos"] == {"corrente"} else "contraventamento (%s)" % ", ".join(sorted(reg["planos"]))
        nome, tit = titulo(marca, tipo_txt, p.perfil)
        r = _verificar_tirante(p.perfil, p.aco, 0.0, reg["N"], reg["L"] / 10.0, tit)
        elementos[marca] = _elemento_extra(
            marca, nome, tit, "corrente" if reg["planos"] == {"corrente"} else "contraventamento", r, p.perfil, p.aco,
            {"M": 0.0, "V": 0.0, "N": round(reg["N"], 2), "caso": "vento no oitão" if "cobertura" in reg["planos"] else "",
             "comprimento_m": round(reg["L"] / 1000.0, 2), "planos": sorted(reg["planos"]),
             "F_oitao_kN": round(F_oitao, 2), "cortante_kN": round(cortante, 2)},
            {"tipo": "tirante", "Nt": round(reg["N"], 3), "Nc": 0.0, "L_cm": round(reg["L"] / 10.0, 2), "aco": p.aco},
            comprimento_total)
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo="contraventamento"))

    # ---- travamento do banzo inferior (as barras que cruzam o banzo inferior)
    Nc_inf = max((reg["Nc"] for reg in por_marca.values() if reg.get("tipo") == "banzo" and reg.get("posicao") == "inferior"),
                 default=0.0)
    regs = {}
    for t in tes:
        for tr in t.travas:
            p = tr["peca"]
            if p.marca in elementos:
                continue
            reg = regs.setdefault(p.marca, {"peca": p, "L": 0.0})
            reg["L"] = max(reg["L"], p.L)
    for marca, reg in sorted(regs.items()):
        p = reg["peca"]
        N = max(0.02 * Nc_inf, 2.0)
        nome, tit = titulo(marca, "travamento do banzo inferior", p.perfil)
        if p.perfil.tipo == "barra":
            r = _verificar_tirante(p.perfil, p.aco, 0.0, N, reg["L"] / 10.0, tit)
            entrada = {"tipo": "tirante", "Nt": round(N, 3), "Nc": 0.0, "L_cm": round(reg["L"] / 10.0, 2), "aco": p.aco}
        else:
            r = _verificar_membro(p.perfil, p.aco, N, N, 0.0, reg["L"] / 10.0, reg["L"] / 10.0, 1, tit, avisos)
            entrada = {"tipo": "barra", "Nc": round(N, 3), "Nt": round(N, 3), "M_kNcm": 0.0,
                       "Lx_cm": round(reg["L"] / 10.0, 2), "Ly_cm": round(reg["L"] / 10.0, 2), "n": 1, "aco": p.aco}
        elementos[marca] = _elemento_extra(
            marca, nome, tit, "travamento", r, p.perfil, p.aco,
            {"M": 0.0, "V": 0.0, "N": round(N, 2), "caso": "2 % da compressão do banzo inferior (NBR 8800, 4.11)",
             "comprimento_m": round(reg["L"] / 1000.0, 2)},
            entrada, comprimento_total)
        verificacoes.append(dict(_serializar_resultado(r), marca=marca, nome=nome, tipo="travamento"))
    if elementos:
        avisos.append("pilares, longarinas e contraventamentos verificados pelos modelos simples do galpão: pilar de "
                      "fachada engastado na base com a tesoura de escora (K = 2), pilar do oitão biapoiado, "
                      "contraventamento em X só à tração com o vento no oitão, longarina como terça sob o vento "
                      "(%d linha(s) de correntes por vão%s)" % (
                          n_corr, "" if par.get("correntes_longarina") is not None else ", adotada — informe no diálogo"))
    return elementos, verificacoes


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
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok), "indeterminada": bool(r.indeterminada),
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
        r.add(nao_verificada(exc))
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
    _definir_apoios(tes, pecas, par)
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
    _definir_apoios(tes, pecas, par)
    for t in tes:
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
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok), "indeterminada": bool(r.indeterminada),
            "governa": crit.titulo if crit else "", "norma": getattr(crit, "norma", "") if crit else "",
            "Sd": round(crit.Sd, 2) if crit else 0.0, "Rd": round(crit.Rd, 2) if crit else 0.0,
            "unidade": getattr(crit, "unidade", "") if crit else "",
            "barras": [], "no_portico": True, "sem_trava": bool(reg.get("sem_trava")),
            "conjuntos": sorted(reg["tesouras"]),
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
        q_sc = sc * larg * math.cos(math.radians(theta))
        q_v = max(0.0, p_max * larg)
        q_g = max(1.25 * g + 1.5 * q_sc + 1.4 * 0.6 * q_v,            # SC principal
                  1.25 * g + 1.5 * 0.8 * q_sc + 1.4 * q_v)            # vento principal (pressão)
        q_s = max(0.0, 1.4 * abs(min(p_min, 0.0)) * larg - 1.0 * g)
        q_gs = g + sc * larg * math.cos(math.radians(theta))
        q_ss = max(0.0, abs(min(p_min, 0.0)) * larg - g)
        tit = "%s%s · terça · %s" % (marca, (" " + nome) if nome else "", p.perfil.nome)
        n_corr = int(par["correntes"]) if par.get("correntes") is not None else int(correntes.get(marca, 0))
        try:
            if perfis_fabrica.tipo_de_verificacao(p.perfil) == "frio":
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
            r.add(nao_verificada(exc))
        _hipoteses_da_terca(r, par, marca, reg, vao, larg, theta, pp, g_cob, g_telha, sc, p_min, p_max,
                            vento, n_corr, g, q_sc, q_v, q_g, q_s, q_gs, q_ss)
        crit = r.critica
        caso = "gravidade" if q_g >= q_s else "sucção"
        q = max(q_g, q_s)
        passos = [i / (ESTACOES - 1) for i in range(ESTACOES)]
        elementos[marca] = {
            "nome": nome, "titulo": tit, "tipo": "terca", "posicao": "",
            "perfil": p.perfil.nome, "material": p.aco, "n": 1,
            "aproveitamento": round(r.razao, 3), "ok": bool(r.ok), "indeterminada": bool(r.indeterminada),
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

    # pilares, longarinas, contraventamentos, correntes e travamentos
    avisar("verificando pilares, longarinas e contraventamentos…")
    el_extra, ver_extra = _verificar_complementares(tes, soltas, cruz, correntes, vento, par, g_cob, sc, nomes_pos,
                                                    comprimento_total, por_marca, avisos)
    for m_, e_ in el_extra.items():
        elementos.setdefault(m_, e_)
    verificacoes.extend(ver_extra)

    # o que ficou sem verificação
    ids_verif = set(por_marca) | set(por_terca) | set(el_extra)
    outras = collections.Counter()
    for p in soltas:
        if p.marca not in ids_verif:
            outras[(p.marca, p.tipo or "barra", p.perfil.nome)] += 1
    nao_verificadas = [{"marca": m, "nome": nomes_pos.get(m, ""), "tipo": tp, "perfil": pf, "pecas": n}
                       for (m, tp, pf), n in sorted(outras.items())]
    if nao_verificadas:
        avisos.append("%d posição(ões) não foram verificadas (consoles, suportes, peças sem papel reconhecido): "
                      "ver a lista" % len(nao_verificadas))

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
            ent = el.get("entrada") or {}
            if ent.get("tipo") == "terca" and ent.get("vao_m"):
                # a terça não passa pela análise de pórtico: cada combinação leva o momento da
                # carga dela (gravidade ou sucção), não o da envoltória — o painel do 3D mostrava
                # o mesmo M em todas
                el["valores"] = _valores_da_terca(ent, ultimas, servico)
                continue
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


def alternativas(calculo: dict, marca: str, limite: int = 10, todas: bool = False,
                 limite_catalogo: int = 90, so_padrao: bool = False) -> dict:
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
        candidatos = catalogo.alternativas(atual, modo="todos", limite=limite_catalogo)
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
        if so_padrao and c.get("fornecedor"):
            continue                  # o dimensionamento automático fica nas séries padrão
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
        elif entrada.get("tipo") == "pilar":
            r = _verificar_pilar(perfil, entrada["aco"], float(entrada["Nc"]), float(entrada["Nt"]),
                                 float(entrada["M_kNcm"]), float(entrada["H_cm"]), float(entrada["K"]),
                                 float(entrada["Ly_cm"]), el.get("titulo", ""), [])
        elif entrada.get("tipo") == "tirante":
            r = _verificar_tirante(perfil, entrada["aco"], float(entrada.get("Nc") or 0.0), float(entrada["Nt"]),
                                   float(entrada["L_cm"]), el.get("titulo", ""))
        else:
            r = _verificar_membro(perfil, entrada["aco"], float(entrada["Nc"]), float(entrada["Nt"]),
                                  float(entrada["M_kNcm"]), float(entrada["Lx_cm"]), float(entrada["Ly_cm"]),
                                  int(entrada.get("n") or 1), el.get("titulo", ""), [])
    except Exception:
        return None
    crit = r.critica
    return (r.razao, crit.titulo if crit else "", getattr(crit, "norma", "") if crit else "", r.ok)


# ------------------------------------------------------------------ dimensionamento

def _aceito_no_automatico(nome: str, el: dict) -> bool:
    """As regras que o dimensionamento da tesoura do galpão segue (`nucleo.tesouras`):
    barra de tesoura com parede de pelo menos 2 mm (o que a fábrica dobra e chega à obra
    sem amassar) e esbeltez até 200 na compressão e 300 na tração; no pilar, K·L/r ≤ 200."""
    from nucleo import catalogo, tesouras
    p = catalogo.perfil_de(nome)
    if p is None:
        return False
    tipo = el.get("tipo")
    ent = el.get("entrada") or {}
    r_min = min(getattr(p, "rx", 0.0) or 1e9, getattr(p, "ry", 0.0) or 1e9)
    if tipo in ("banzo", "diagonal", "montante", "travamento"):
        esp = tesouras._espessura(p)
        if 0 < esp < tesouras.MIN_ESPESSURA:
            return False
        L = max(float(ent.get("Lx_cm") or 0.0), float(ent.get("Ly_cm") or 0.0))
        limite = 200.0 if float(ent.get("Nc") or 0.0) > 1e-6 else 300.0
        return not (r_min and L / r_min > limite)
    if tipo == "pilar":
        rx, ry = getattr(p, "rx", 0.0) or 1e9, getattr(p, "ry", 0.0) or 1e9
        KL = float(ent.get("K") or 1.0) * float(ent.get("H_cm") or 0.0)
        return KL / rx <= 200.0 and float(ent.get("Ly_cm") or 0.0) / ry <= 200.0
    return True


def _grupo_do_elemento(marca: str, el: dict) -> tuple:
    """Banzo: cada linha (superior, inferior) leva um perfil só em todas as tesouras — é
    uma peça contínua, e é assim que o galpão dimensiona; os pedaços escolhem juntos. O
    resto escolhe sozinho."""
    if el.get("tipo") == "banzo":
        return ("banzo", el.get("posicao") or "")
    return ("posicao", marca)


def dimensionar(doc: Documento, nomes: dict, parametros: Optional[dict] = None, avisar=None,
                max_rodadas: int = 6) -> dict:
    """O perfil mais leve do catálogo que passa, em cada posição verificada.

    Cada rodada calcula a estrutura com os perfis da rodada anterior e escolhe o primeiro
    candidato de `alternativas` que passa (na barra e na ligação) — elas vêm do mais leve
    ao mais pesado —, nas séries padrão e dentro das regras de `_aceito_no_automatico`. O
    banzo escolhe por linha (`_grupo_do_elemento`): o mais leve que passa em todos os
    pedaços. Quando nenhum passa, fica o que chegou mais perto. Trocar um perfil muda a
    rigidez e redistribui os esforços da treliça, por isso repete-se até a escolha devolver
    os mesmos perfis que a geraram; num ciclo, fica o mais pesado de cada posição.

    Posição sem esforço fica como está; banzo inferior que só não passa por falta de
    travamento lateral no modelo vai para `pendentes` (é o usuário quem diz onde trava).

    Devolve {trocas: {marca: perfil}, calculo, rodadas, mudancas, pendentes, reprovadas,
    reprovadas_antes, peso_antes_kg, peso_depois_kg}."""
    from nucleo import catalogo
    avisar = avisar or (lambda *a: None)
    par = dict(parametros or {})
    originais: Dict[str, str] = {}
    trocas: Dict[str, str] = {}
    historico = []
    pendentes: Dict[str, str] = {}
    antes = r = None
    rodadas = 0
    convergiu = False
    for rodada in range(1, max_rodadas + 1):
        rodadas = rodada
        avisar("dimensionando: rodada %d de até %d…" % (rodada, max_rodadas))
        r = calcular(doc, nomes, dict(par, trocas=dict(trocas)), avisar=lambda *a: None)
        if rodada == 1:
            antes = r
            originais = {m: el["perfil"] for m, el in r["elementos"].items()}
        pendentes = {}
        grupos: Dict[tuple, List[str]] = collections.defaultdict(list)
        for marca, el in r["elementos"].items():
            if not el.get("entrada") or not (el.get("aproveitamento") or 0.0) > 1e-3:
                continue                       # sem esforço: fica o perfil do modelo
            if el.get("sem_trava") and not el.get("ok"):
                pendentes[marca] = ("banzo inferior sem travamento lateral no modelo: informe o espaçamento dos "
                                    "travamentos (Travamento do banzo inferior) e dimensione de novo")
                continue
            grupos[_grupo_do_elemento(marca, el)].append(marca)
        novas = dict(trocas)
        for _chave, marcas in grupos.items():
            opcoes: Dict[str, List[dict]] = {}
            for marca in marcas:
                el = r["elementos"][marca]
                try:
                    alt = alternativas(r, marca, limite=400, limite_catalogo=600, so_padrao=True).get("alternativas") or []
                except ErroDeDados:
                    alt = []
                # o perfil atual disputa também: sem ele, quem já era o mais leve que passa
                # trocava pelo vizinho e voltava na rodada seguinte
                atual = {"nome": el["perfil"], "massa": getattr(catalogo.perfil_de(el["perfil"]), "massa", 0.0) or 0.0,
                         "ok": bool(el.get("ok")), "aproveitamento": el.get("aproveitamento") or 0.0}
                lista = [a for a in alt if _aceito_no_automatico(a["nome"], el)]
                if _aceito_no_automatico(atual["nome"], el) or not atual["ok"]:
                    lista.append(atual)
                lista.sort(key=lambda a: (not a["ok"], (a["massa"] or 0.0) if a["ok"] else a["aproveitamento"]))
                opcoes[marca] = lista
            passam = {m: {a["nome"]: a["massa"] or 0.0 for a in lista if a["ok"]} for m, lista in opcoes.items()}
            comuns = set.intersection(*(set(v) for v in passam.values())) if passam and all(passam.values()) else set()
            if comuns:
                escolha = min(comuns, key=lambda n: (passam[marcas[0]][n], n))
            else:
                # nada serve para todos: vale a escolha da posição mais solicitada
                pior = max(marcas, key=lambda m: r["elementos"][m].get("aproveitamento") or 0.0)
                lista = opcoes.get(pior) or []
                ok = [a for a in lista if a["ok"]]
                if ok:
                    escolha = ok[0]["nome"]
                elif all(r["elementos"][m].get("ok") for m in marcas):
                    continue                   # passa e nada mais leve serve: fica
                elif lista:
                    escolha = lista[0]["nome"]  # nada passa: o que chegou mais perto
                else:
                    continue
            for marca in marcas:
                if escolha == originais.get(marca):
                    novas.pop(marca, None)
                else:
                    novas[marca] = escolha
        if novas == trocas:
            convergiu = True
            break
        chave = tuple(sorted(novas.items()))
        if chave in historico:
            # ciclo: o mais pesado de cada posição entre as duas escolhas
            for marca in set(novas) | set(trocas):
                a_, b_ = trocas.get(marca, originais.get(marca)), novas.get(marca, originais.get(marca))
                pa, pb = catalogo.perfil_de(a_), catalogo.perfil_de(b_)
                pesado = a_ if (pa and pb and (pa.massa or 0) >= (pb.massa or 0)) else b_
                if pesado == originais.get(marca):
                    novas.pop(marca, None)
                else:
                    novas[marca] = pesado
            trocas = novas
            r = calcular(doc, nomes, dict(par, trocas=dict(trocas)), avisar=lambda *a: None)
            convergiu = True
            break
        historico.append(chave)
        trocas = novas
    else:
        avisar("dimensionando: conferindo a última escolha…")
        r = calcular(doc, nomes, dict(par, trocas=dict(trocas)), avisar=lambda *a: None)
    mudancas = []
    for marca, novo in sorted(trocas.items()):
        el = r["elementos"].get(marca) or {}
        el0 = antes["elementos"].get(marca) or {}
        mudancas.append({"marca": marca, "nome": el.get("nome", ""), "tipo": el.get("tipo", ""),
                         "de": originais.get(marca, ""), "para": novo,
                         "aproveitamento_antes": el0.get("aproveitamento"), "aproveitamento": el.get("aproveitamento"),
                         "ok": el.get("ok"), "delta_kg": round((el.get("peso_kg") or 0.0) - (el0.get("peso_kg") or 0.0), 1)})
    res = r.get("resumo") or {}
    return {"trocas": trocas, "calculo": r, "rodadas": rodadas, "convergiu": convergiu, "mudancas": mudancas,
            "pendentes": [{"marca": m, "motivo": motivo, "perfil": (r["elementos"].get(m) or {}).get("perfil", ""),
                           "aproveitamento": (r["elementos"].get(m) or {}).get("aproveitamento")}
                          for m, motivo in sorted(pendentes.items())],
            "reprovadas": list(res.get("reprovadas") or []),
            # o que continua reprovado sem ser pendência: nada das séries padrão passa, e ficou o
            # que chegou mais perto
            "sem_solucao": [{"marca": m, "perfil": (r["elementos"].get(m) or {}).get("perfil", ""),
                             "aproveitamento": (r["elementos"].get(m) or {}).get("aproveitamento"),
                             "tipo": (r["elementos"].get(m) or {}).get("tipo", "")}
                            for m in sorted(res.get("reprovadas") or []) if m not in pendentes],
            "reprovadas_antes": list((antes.get("resumo") or {}).get("reprovadas") or []),
            "peso_antes_kg": (antes.get("resumo") or {}).get("peso_verificado_kg"),
            "peso_depois_kg": res.get("peso_verificado_kg")}


def aplicar_perfis(doc: Documento, trocas: Dict[str, str]) -> dict:
    """Põe no modelo os perfis escolhidos: cada `Barra` da posição troca de perfil (e de
    peso), guardando o perfil original e o histórico da troca, como o "Trocar perfil" do
    3D. Sólido do IFC não se refaz aqui: a posição fica como perfil de cálculo.

    Devolve {barras: quantas mudaram, posicoes: [...], so_calculo: {marca: perfil}}."""
    import time as _time
    from nucleo import catalogo
    hoje = _time.strftime("%Y-%m-%d")
    mudou = collections.Counter()
    for b in doc.barras:
        m = _marcas(b)
        marca = str(m.get("posicao") or b.id)
        novo = trocas.get(marca)
        if not novo or novo == b.perfil:
            continue
        p = catalogo.perfil_de(novo)
        nome = p.nome if p is not None else novo
        antigo = b.perfil
        if b.nome == antigo:
            b.nome = nome
        b.perfil = nome
        at = dict(b.atributos or {})
        marcas = dict(at.get("marcas") or {})
        marcas.setdefault("perfil_original", antigo)
        marcas["perfil"] = nome
        at["marcas"] = marcas
        at["trocas_de_perfil"] = list(at.get("trocas_de_perfil") or []) + [
            {"de": antigo, "para": nome, "data": hoje, "por": "dimensionamento"}]
        if p is not None:
            at["peso_kg"] = round((p.massa or 0.0) * _norma(_sub(b.fim, b.inicio)) / 1000.0, 3)
        b.atributos = at
        mudou[marca] += 1
    so_calculo = {m: v for m, v in trocas.items() if m not in mudou}
    return {"barras": sum(mudou.values()), "posicoes": sorted(mudou), "so_calculo": so_calculo}


def nomes_das_barras(doc: Documento) -> dict:
    """Classificação mínima de um modelo desenhado (sem detalhamento): o conjunto que tem
    banzo é tesoura. É o que o cálculo precisa para começar; o resto sai do papel das barras."""
    tesouras = sorted({str(_marcas(b).get("conjunto") or "") for b in doc.barras
                       if b.papel == "banzo" and _marcas(b).get("conjunto")})
    return {"tipos_conjuntos": {c: "tesoura" for c in tesouras}, "tipos": {}} if tesouras else {}


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
