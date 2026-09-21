# -*- coding: utf-8 -*-
"""Exportação do documento 3D para IFC4 (ISO-10303-21, parte 21 — formato STEP).

O arquivo gerado é escrito à mão, sem dependência externa: o sistema inteiro roda
só com a biblioteca padrão e `pymupdf` (GUIA_SISTEMA.md). Escrever STEP é escrever
texto; o que faz o arquivo ser aceito pelos visualizadores não é a biblioteca, e sim
o cuidado com quatro coisas:

    GlobalId      22 caracteres na base 64 do IFC (alfabeto `0-9A-Za-z_$`), derivado
                  de um UUID de 128 bits. É o erro mais comum e o que mais faz
                  visualizador recusar arquivo.
    hierarquia    IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey → elementos,
                  amarrada por IfcRelAggregates e IfcRelContainedInSpatialStructure.
    unidades      IfcUnitAssignment declarando milímetro, m², m³, grau, quilograma e
                  newton. Sem isso o visualizador adivinha — e adivinha metro.
    contextos     IfcGeometricRepresentationContext 3D com precisão, e um
                  IfcGeometricRepresentationSubContext 'Body' com MODEL_VIEW.

Geometria por tipo de entidade:

    Barra    IfcBeam / IfcColumn / IfcMember, com IfcExtrudedAreaSolid sobre perfil
             **paramétrico** sempre que o catálogo permite (IfcIShapeProfileDef,
             IfcUShapeProfileDef, IfcLShapeProfileDef, IfcRectangleHollowProfileDef,
             IfcCircleHollowProfileDef). Perfil paramétrico é o que faz o modelo
             chegar com informação útil no software do cliente: o Tekla, o Revit e o
             Solibri leem as dimensões da seção, não um amontoado de triângulos.
             Formados a frio (Ue, cartola) viram IfcArbitraryClosedProfileDef com
             IfcPolyline, porque o IFC4 não tem perfil paramétrico com enrijecedor
             de borda.
    Chapa    IfcPlate, com IfcArbitraryProfileDefWithVoids quando há furos (os furos
             saem como vazios de verdade, não como desenho) ou
             IfcArbitraryClosedProfileDef quando não há.
    Solido   IfcBuildingElementProxy (ou o tipo em `atributos["tipo_ifc"]`) com
             IfcFacetedBrep. Ver a justificativa em `_forma_solido`.
    Grupo    IfcElementAssembly agregando os filhos por IfcRelAggregates.

Aparência (contrato com `ifc/importar.py`):

    camada   um IfcPresentationLayerWithStyle por camada usada: Name = nome,
             LayerOn = visivel, LayerFrozen = .F., LayerBlocked = bloqueada
             (bloqueada = visível mas não editável; congelada o IFC4 reserva
             para camada não regenerada, que visualizador pode esconder),
             LayerStyles = IfcSurfaceStyle com a cor da camada, AssignedItems =
             as IfcShapeRepresentation dos elementos da camada.
    cor      IfcStyledItem no item de geometria, com IfcSurfaceStyle +
             IfcSurfaceStyleRendering na cor e opacidade do material de
             aparência (um estilo por material, reaproveitado).
    reserva  `Camada` e `MaterialAparencia` no Pset_MetalicaCalculo, para o
             visualizador que descarta camadas.

Unidades: o documento 3D está em milímetro e grau (GUIA_3D.md), que é exatamente o
que o arquivo declara. Nenhuma conversão de coordenada acontece aqui. As únicas
conversões são as do catálogo de perfis, que guarda dimensões em mm e propriedades
de seção em cm (GUIA_SISTEMA.md), e as das quantidades, pedidas em m² e m³.

Uso:

    from ifc.exportar import exportar, para_texto
    exportar(doc, "saida/galpao.ifc", projeto_nome="Galpão 20×40",
             autor="Fulano", organizacao="Beltrano Engenharia")
"""
from __future__ import annotations

import datetime
import math
import os
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados, E as E_ACO, NU as NU_ACO, RHO as RHO_ACO
from nucleo import materiais as mat
from nucleo.perfis import Perfil
from nucleo3d.modelo import (Barra, Chapa, Documento, Entidade, Grupo, Ponto,
                             Solido, normalizar, produto_vetorial, subtrair)
# a forma e a orientação das seções são do módulo de geometria; importadas,
# nunca copiadas, para o IFC não divergir do que o editor desenha
from nucleo3d.geometria import base_local
from nucleo3d.geometria import resolver_perfil as _resolver_geo
from nucleo3d.geometria import secao as _secao_geo

__all__ = ["exportar", "para_texto", "guid_ifc", "comprimir_guid", "expandir_guid"]

VERSAO = "1.0"
APLICACAO = "Metalica"
NOME_COMPLETO = "Sistema de dimensionamento de estruturas metálicas"
DESENVOLVEDOR = "Schneider e Costa Engenharia"

#: massa específica do aço em kg/mm³ (7850 kg/m³ = 7,85e-6 kg/mm³)
RHO_MM3 = RHO_ACO * 1e-9

#: tolerância do contexto geométrico, em milímetro
PRECISAO = 1e-5

#: número de lados usados para aproximar um furo circular por polilinha
LADOS_FURO = 32


# =========================================================== GlobalId (IfcGloballyUniqueId)

#: alfabeto da base 64 do IFC. **Não** é a base64 do RFC 4648: a ordem é outra e os
#: dois últimos caracteres são `_` e `$`.
ALFABETO = ("0123456789"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "_$")

_INDICE = {c: i for i, c in enumerate(ALFABETO)}


def comprimir_guid(u: uuid.UUID) -> str:
    """UUID de 128 bits → os 22 caracteres do IfcGloballyUniqueId.

    O algoritmo da própria norma divide o UUID em 6 grupos (1 byte + 5×3 bytes) e
    converte cada grupo para a base 64 com 2, 4, 4, 4, 4 e 4 dígitos. Isso é
    aritmeticamente idêntico a escrever o inteiro de 128 bits inteiro na base 64
    com 22 dígitos, que é o que se faz abaixo — o primeiro dígito carrega só 2 bits,
    então ele sempre cai entre '0' e '3'.
    """
    n = u.int
    saida = [""] * 22
    for i in range(21, -1, -1):
        n, resto = divmod(n, 64)
        saida[i] = ALFABETO[resto]
    return "".join(saida)


def expandir_guid(texto: str) -> uuid.UUID:
    """Os 22 caracteres de volta ao UUID. Serve ao importador e aos testes."""
    if len(texto) != 22:
        raise ErroDeDados(f"GlobalId deve ter 22 caracteres, recebido {len(texto)}")
    n = 0
    for c in texto:
        if c not in _INDICE:
            raise ErroDeDados(f"caractere fora do alfabeto do IFC no GlobalId: {c!r}")
        n = n * 64 + _INDICE[c]
    if n >= 1 << 128:
        raise ErroDeDados("GlobalId excede 128 bits")
    return uuid.UUID(int=n)


def guid_ifc() -> str:
    """Um GlobalId novo, aleatório."""
    return comprimir_guid(uuid.uuid4())


# =========================================================== codificação STEP

def _real(v) -> str:
    """Número real na sintaxe da parte 21: sempre com ponto decimal."""
    v = float(v)
    if v == 0.0:
        return "0."
    # 12 algarismos significativos: limpa o ruído do ponto flutuante
    # (0.1+0.2 → 0.3) sem perder precisão de coordenada nem de fator de conversão.
    v = float(f"{v:.12g}")
    if abs(v) >= 1e-6 and abs(v) < 1e15:
        if v == int(v):
            return f"{int(v)}."
        texto = repr(v)
        if "e" in texto or "E" in texto:
            return _cientifico(texto)
        return texto
    return _cientifico(repr(v))


def _cientifico(texto: str) -> str:
    texto = texto.replace("e", "E")
    if "E" not in texto:
        return texto if "." in texto else texto + "."
    mantissa, expoente = texto.split("E")
    if "." not in mantissa:
        mantissa += "."
    return f"{mantissa}E{int(expoente)}"


def _inteiro(v) -> str:
    return str(int(v))


def _texto(s: Optional[str]) -> str:
    """String da parte 21, com o escape \\X2\\…\\X0\\ para o que não é ASCII.

    O IFC é um arquivo ASCII; 'W 310×38,7' e 'Terça' só atravessam se o × e o ç
    forem escritos em UTF-16 dentro de um \\X2\\. Ignorar isso produz arquivo que
    abre torto (ou não abre) fora do Brasil.
    """
    if s is None:
        return "$"
    partes: List[str] = []
    acumulado: List[str] = []

    def descarregar():
        if acumulado:
            partes.append("\\X2\\" + "".join(acumulado) + "\\X0\\")
            acumulado.clear()

    for c in str(s):
        o = ord(c)
        if o < 128:
            descarregar()
            if c == "'":
                partes.append("''")
            elif c == "\\":
                partes.append("\\\\")
            elif o < 32:
                partes.append(" ")
            else:
                partes.append(c)
        elif o <= 0xFFFF:
            acumulado.append(f"{o:04X}")
        else:                                   # fora do plano básico: par substituto
            o -= 0x10000
            acumulado.append(f"{0xD800 + (o >> 10):04X}")
            acumulado.append(f"{0xDC00 + (o & 0x3FF):04X}")
    descarregar()
    return "'" + "".join(partes) + "'"


def _lista(refs: Sequence[str]) -> str:
    return "(" + ",".join(refs) + ")"


def _opcional_texto(s: Optional[str]) -> str:
    return _texto(s) if s else "$"


# =========================================================== o arquivo

class _Arquivo:
    """Acumulador de linhas da seção DATA, com numeração e reaproveitamento.

    Entidades sem identidade própria (ponto, direção, propriedade, perfil) são
    reaproveitadas por conteúdo: um galpão tem milhares de pontos repetidos e
    centenas de terças idênticas, e sem isso o arquivo cresce sem motivo.
    """

    def __init__(self):
        self._linhas: List[str] = []
        self._cache: Dict[str, str] = {}
        self._chaveados: Dict[tuple, str] = {}

    # ---- primitivas ----
    def add(self, texto: str) -> str:
        self._linhas.append(texto)
        return f"#{len(self._linhas)}"

    def cache(self, texto: str) -> str:
        ref = self._cache.get(texto)
        if ref is None:
            ref = self.add(texto)
            self._cache[texto] = ref
        return ref

    def por_chave(self, chave: tuple, fabrica) -> str:
        """Reaproveita por uma chave explícita (para entidades com GlobalId)."""
        ref = self._chaveados.get(chave)
        if ref is None:
            ref = fabrica()
            self._chaveados[chave] = ref
        return ref

    def linhas(self) -> List[str]:
        return [f"#{i + 1}= {t};" for i, t in enumerate(self._linhas)]

    # ---- geometria básica ----
    def ponto(self, x: float, y: float, z: Optional[float] = None) -> str:
        if z is None:
            return self.cache(f"IFCCARTESIANPOINT(({_real(x)},{_real(y)}))")
        return self.cache(f"IFCCARTESIANPOINT(({_real(x)},{_real(y)},{_real(z)}))")

    def direcao(self, x: float, y: float, z: Optional[float] = None) -> str:
        if z is None:
            return self.cache(f"IFCDIRECTION(({_real(x)},{_real(y)}))")
        return self.cache(f"IFCDIRECTION(({_real(x)},{_real(y)},{_real(z)}))")

    def eixo3(self, origem: Ponto = (0.0, 0.0, 0.0),
              eixo_z: Optional[Ponto] = None,
              eixo_x: Optional[Ponto] = None) -> str:
        loc = self.ponto(*origem)
        z = self.direcao(*eixo_z) if eixo_z else "$"
        x = self.direcao(*eixo_x) if eixo_x else "$"
        return self.cache(f"IFCAXIS2PLACEMENT3D({loc},{z},{x})")

    def eixo2(self, origem=(0.0, 0.0), eixo_x: Optional[Tuple[float, float]] = None) -> str:
        loc = self.ponto(origem[0], origem[1])
        x = self.direcao(*eixo_x) if eixo_x else "$"
        return self.cache(f"IFCAXIS2PLACEMENT2D({loc},{x})")

    def polilinha(self, pontos: Sequence[Tuple[float, float]], fechar=True) -> str:
        pts = list(pontos)
        if fechar and (abs(pts[0][0] - pts[-1][0]) > 1e-9 or abs(pts[0][1] - pts[-1][1]) > 1e-9):
            pts.append(pts[0])
        refs = [self.ponto(p[0], p[1]) for p in pts]
        return self.cache("IFCPOLYLINE(" + _lista(refs) + ")")


# =========================================================== álgebra de eixos

def _eixos_da_barra(barra: Barra) -> Tuple[Ponto, Ponto]:
    """(eixo_z, eixo_x) do IfcAxis2Placement3D da barra, com a rotação aplicada.

    O triedro vem de `nucleo3d.geometria.base_local`, que é quem gera a malha do
    editor e dos desenhos. A regra **não** é repetida aqui: se as duas divergirem,
    o pilar aparece girado no Solibri e volta do importador com outra `rotacao`.
    Na convenção dela, com `rotacao = 0` a barra horizontal fica com o eixo forte
    vertical e a barra vertical com o eixo forte no X global (o pilar de pórtico no
    plano Y-Z pede `rotacao = 90`).

    Com Axis = w e RefDirection = u, o IFC completa y = w × u = v, que é exatamente
    o eixo forte da seção de `base_local`.
    """
    if barra.comprimento < PRECISAO:
        raise ErroDeDados(f"barra '{barra.nome or barra.id}' tem comprimento nulo")
    u, _v, w = base_local(barra.direcao, barra.rotacao or 0.0)
    return w, u


def _area_assinada(pontos: Sequence[Tuple[float, float]]) -> float:
    s = 0.0
    n = len(pontos)
    for i in range(n):
        a, b = pontos[i], pontos[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return s / 2


def _anti_horario(pontos: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    p = list(pontos)
    return p if _area_assinada(p) >= 0 else p[::-1]


def _horario(pontos: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    p = list(pontos)
    return p if _area_assinada(p) <= 0 else p[::-1]


def _circulo(cx: float, cy: float, raio: float, lados=LADOS_FURO) -> List[Tuple[float, float]]:
    return [(cx + raio * math.cos(2 * math.pi * i / lados),
             cy + raio * math.sin(2 * math.pi * i / lados)) for i in range(lados)]


# =========================================================== seções de perfil
#
# A forma da seção é de `nucleo3d.geometria`: o IFC tem de mostrar a mesma peça que
# a tela e o DXF. Daqui só sai o mapeamento para o perfil paramétrico do IFC4 — e,
# quando o IFC posiciona o perfil de outro jeito, o deslocamento que compensa.

def _numeros(texto: str) -> List[float]:
    """Extrai os números de '100×50×17×2,00' respeitando a vírgula decimal."""
    valores: List[float] = []
    atual = ""
    for c in texto:
        if c.isdigit() or (c in ",." and atual):
            atual += "." if c == "," else c
        else:
            if atual:
                valores.append(float(atual.rstrip(".")))
            atual = ""
    if atual:
        valores.append(float(atual.rstrip(".")))
    return valores


def _resolver_perfil(nome: str) -> Optional[Perfil]:
    """Nome → Perfil pelo catálogo e pelos perfis sintéticos do 3D.

    `geometria.resolver_perfil` conhece o catálogo e o registro dos perfis que o
    orquestrador cria fora dele ("Barra redonda ø 20 mm", "Barra chata …", mísulas).
    """
    try:
        return _resolver_geo(nome)
    except ErroDeDados:
        return None


def _centro_da_caixa(p: Perfil) -> Tuple[float, float]:
    """Centro da caixa envolvente da seção de `geometria`, no sistema dela.

    `geometria` centra a seção no centroide da área; o IFC4 posiciona o
    IfcUShapeProfileDef e o IfcLShapeProfileDef pelo centro da caixa envolvente.
    Em perfil assimétrico a diferença é de vários milímetros, e é ela que vai no
    `Position` do perfil para as duas geometrias coincidirem.
    """
    pts = _secao_geo(p)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return (0.0 if abs(cx) < 1e-6 else cx, 0.0 if abs(cy) < 1e-6 else cy)


def _perfil_ifc(arq: _Arquivo, nome: str) -> Tuple[str, Perfil]:
    """Nome do perfil → IfcProfileDef, paramétrico sempre que o IFC4 permitir.

    Os eixos seguem a seção de `geometria`: X é a largura da mesa (ou da barra
    chata), Y é a altura (eixo forte).
    """
    p = _resolver_perfil(nome)
    if p is None:
        return _perfil_avulso(arq, nome), _PERFIL_VAZIO
    rotulo = _texto(p.nome)
    pos = arq.eixo2()
    subtipo_barra = p.dados.get("tipo") if p.tipo == "barra" else None
    if subtipo_barra == "redonda":
        # barra redonda maciça (tirante, corrente)
        texto = (f"IFCCIRCLEPROFILEDEF(.AREA.,{rotulo},{pos},"
                 f"{_real((p.dados.get('d') or 0.0) / 2)})")
    elif subtipo_barra == "chata":
        # barra chata: largura em X, espessura em Y, como em geometria._dims
        texto = (f"IFCRECTANGLEPROFILEDEF(.AREA.,{rotulo},{pos},"
                 f"{_real(p.dados.get('b') or 0.0)},{_real(p.dados.get('t') or 0.0)})")
    elif p.tipo == "I":
        raio = p.dados.get("r")
        texto = (f"IFCISHAPEPROFILEDEF(.AREA.,{rotulo},{pos},{_real(p.bf)},{_real(p.d)},"
                 f"{_real(p.tw)},{_real(p.tf)},"
                 f"{_real(raio) if raio else '$'},$,$)")
    elif p.tipo == "U":
        # o catálogo laminado traz uma espessura só; alma e mesa saem iguais.
        pos = arq.eixo2(_centro_da_caixa(p))
        texto = (f"IFCUSHAPEPROFILEDEF(.AREA.,{rotulo},{pos},{_real(p.d)},{_real(p.bf)},"
                 f"{_real(p.tw)},{_real(p.tf)},$,$,$)")
    elif p.tipo == "L":
        largura = p.dados.get("b2") or p.bf
        pos = arq.eixo2(_centro_da_caixa(p))
        texto = (f"IFCLSHAPEPROFILEDEF(.AREA.,{rotulo},{pos},{_real(p.d or p.bf)},"
                 f"{_real(largura)},{_real(p.tw)},$,$,$)")
    elif p.tipo == "tubo":
        if p.dados.get("tipo") == "redondo":
            texto = (f"IFCCIRCLEHOLLOWPROFILEDEF(.AREA.,{rotulo},{pos},"
                     f"{_real(p.d / 2)},{_real(p.tw)})")
        else:
            texto = (f"IFCRECTANGLEHOLLOWPROFILEDEF(.AREA.,{rotulo},{pos},"
                     f"{_real(p.bf)},{_real(p.d)},{_real(p.tw)},$,$)")
    else:
        # Ue, U formado a frio e qualquer seção sem paramétrico no IFC4: o contorno
        # que a geometria desenha, como polilinha fechada.
        curva = arq.polilinha(_anti_horario(_secao_geo(p)))
        texto = f"IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,{rotulo},{curva})"
    return arq.cache(texto), p


_PERFIL_VAZIO = Perfil(nome="", tipo="", dados={})


def _perfil_avulso(arq: _Arquivo, nome: str) -> str:
    """Perfis que não estão no catálogo: chapa/barra chata e barra redonda.

    Qualquer outra coisa é erro de dados — melhor recusar do que exportar um perfil
    inventado que o cliente vai fabricar (princípio 4 do GUIA_SISTEMA).
    """
    texto = (nome or "").strip()
    baixo = texto.lower().replace("ø", "o ").replace("φ", "o ")
    nums = _numeros(texto)
    pos = arq.eixo2()
    redondo = (baixo.startswith("o ") or baixo.startswith("br ")
               or baixo.startswith("barra redonda") or baixo.startswith("r "))
    chata = (baixo.startswith("ch ") or baixo.startswith("chapa")
             or baixo.startswith("bc ") or baixo.startswith("fb ")
             or baixo.startswith("barra chata"))
    if redondo and len(nums) >= 1:
        return arq.cache(f"IFCCIRCLEPROFILEDEF(.AREA.,{_texto(texto)},{pos},"
                         f"{_real(nums[0] / 2)})")
    if chata and len(nums) >= 2:
        return arq.cache(f"IFCRECTANGLEPROFILEDEF(.AREA.,{_texto(texto)},{pos},"
                         f"{_real(nums[0])},{_real(nums[1])})")
    raise ErroDeDados(
        f"perfil não encontrado no catálogo e não reconhecido como chapa ou barra "
        f"redonda: {nome!r}. Use um nome do catálogo (ex.: 'W 310×38,7'), "
        f"'CH 200×12,7' para barra chata ou 'Ø20' para barra redonda.")


# =========================================================== o exportador

class _Exportador:

    def __init__(self, documento: Documento, projeto_nome=None, autor=None,
                 organizacao=None, incluir_propriedades=True, incluir_quantidades=True,
                 solidos_como="brep", sitio_nome=None, predio_nome=None,
                 pavimento_nome=None, descricao=None, data=None):
        self.doc = documento
        self.arq = _Arquivo()
        self.projeto_nome = projeto_nome or documento.nome or "Projeto"
        self.autor = autor or "Engenheiro"
        self.organizacao = organizacao or DESENVOLVEDOR
        self.incluir_propriedades = incluir_propriedades
        self.incluir_quantidades = incluir_quantidades
        self.solidos_como = solidos_como
        self.sitio_nome = sitio_nome or "Terreno"
        self.predio_nome = predio_nome or (documento.nome or "Edificação")
        self.pavimento_nome = pavimento_nome or "Nível 0"
        self.descricao = descricao or "Modelo estrutural gerado pelo sistema"
        self.data = data or datetime.datetime.now()

        self.dono = ""                       # IfcOwnerHistory
        self.contexto = ""
        self.corpo = ""                      # subcontexto 'Body'
        self.unidades: Dict[str, str] = {}
        self.pav_placement = ""
        self.atual = ""                      # elemento sendo escrito
        # acumuladores de relacionamento (emitidos no fim, agrupados)
        self._materiais: Dict[str, str] = {}
        self._por_material: Dict[str, List[str]] = {}
        self._por_pset: Dict[str, List[str]] = {}
        self._no_pavimento: List[str] = []
        self._grupos_ref: Dict[str, str] = {}
        self._por_camada: Dict[str, List[str]] = {}   # camada -> representações

    # ------------------------------------------------------------ atalhos
    def add(self, texto: str) -> str:
        return self.arq.add(texto)

    def raiz(self, entidade: str, *campos: str) -> str:
        """Entidade derivada de IfcRoot: GlobalId e OwnerHistory na frente."""
        return self.add(f"{entidade}({_texto(guid_ifc())},{self.dono}," + ",".join(campos) + ")")

    # ------------------------------------------------------------ cabeçalho do modelo
    def _unidades(self) -> str:
        a = self.arq
        mm = a.add("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)")
        m2 = a.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
        m3 = a.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
        kg = a.add("IFCSIUNIT(*,.MASSUNIT.,.KILO.,.GRAM.)")
        n = a.add("IFCSIUNIT(*,.FORCEUNIT.,$,.NEWTON.)")
        s = a.add("IFCSIUNIT(*,.TIMEUNIT.,$,.SECOND.)")
        rad = a.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
        # grau: unidade de conversão sobre o radiano, como manda o IFC4
        exp = a.add("IFCDIMENSIONALEXPONENTS(0,0,0,0,0,0,0)")
        fator = a.add(f"IFCMEASUREWITHUNIT(IFCPLANEANGLEMEASURE({_real(math.pi / 180)}),{rad})")
        grau = a.add(f"IFCCONVERSIONBASEDUNIT({exp},.PLANEANGLEUNIT.,{_texto('degree')},{fator})")
        # unidades auxiliares, usadas só dentro das propriedades de material
        mpa = a.add("IFCSIUNIT(*,.PRESSUREUNIT.,.MEGA.,.PASCAL.)")
        metro = a.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
        e_kg = a.add(f"IFCDERIVEDUNITELEMENT({kg},1)")
        e_m3 = a.add(f"IFCDERIVEDUNITELEMENT({metro},-3)")
        dens = a.add(f"IFCDERIVEDUNIT(({e_kg},{e_m3}),.MASSDENSITYUNIT.,$)")
        self.unidades = {"mm": mm, "m2": m2, "m3": m3, "kg": kg, "N": n,
                         "grau": grau, "MPa": mpa, "densidade": dens}
        return a.add("IFCUNITASSIGNMENT("
                     + _lista([mm, m2, m3, kg, n, s, grau]) + ")")

    def _dono(self) -> str:
        a = self.arq
        nomes = self.autor.split()
        familia = nomes[-1] if len(nomes) > 1 else self.autor
        dado = " ".join(nomes[:-1]) if len(nomes) > 1 else None
        pessoa = a.add(f"IFCPERSON($,{_texto(familia)},{_opcional_texto(dado)},$,$,$,$,$)")
        org = a.add(f"IFCORGANIZATION($,{_texto(self.organizacao)},$,$,$)")
        po = a.add(f"IFCPERSONANDORGANIZATION({pessoa},{org},$)")
        dev = a.add(f"IFCORGANIZATION($,{_texto(DESENVOLVEDOR)},$,$,$)")
        app = a.add(f"IFCAPPLICATION({dev},{_texto(VERSAO)},{_texto(NOME_COMPLETO)},"
                    f"{_texto(APLICACAO)})")
        ts = int(self.data.timestamp())
        return a.add(f"IFCOWNERHISTORY({po},{app},$,.ADDED.,{ts},{po},{app},{ts})")

    def _contextos(self):
        a = self.arq
        wcs = a.eixo3()
        norte = a.direcao(0.0, 1.0)
        self.contexto = a.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,{_texto('Model')},3,"
                              f"{_real(PRECISAO)},{wcs},{norte})")
        self.corpo = a.add(f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT({_texto('Body')},"
                           f"{_texto('Model')},*,*,*,*,{self.contexto},$,.MODEL_VIEW.,$)")

    def _hierarquia(self, unidades: str):
        a = self.arq
        projeto = self.raiz("IFCPROJECT", _texto(self.projeto_nome),
                            _texto(self.descricao), "$", "$", "$",
                            _lista([self.contexto]), unidades)
        # modelo importado de coordenadas de obra foi trazido para a origem; a posição
        # original volta aqui, na colocação do sítio, com a geometria local intacta
        desloc = self.doc.metadados.get("deslocamento_mm") or (0.0, 0.0, 0.0)
        try:
            origem_sitio = tuple(float(v) for v in desloc)[:3]
            if len(origem_sitio) != 3 or not all(math.isfinite(v) for v in origem_sitio):
                origem_sitio = (0.0, 0.0, 0.0)
        except (TypeError, ValueError):
            origem_sitio = (0.0, 0.0, 0.0)
        pl_sitio = a.add(f"IFCLOCALPLACEMENT($,{a.eixo3(origem_sitio)})")
        sitio = self.raiz("IFCSITE", _texto(self.sitio_nome), "$", "$", pl_sitio, "$",
                          "$", ".ELEMENT.", "$", "$", _real(0.0), "$", "$")
        pl_predio = a.add(f"IFCLOCALPLACEMENT({pl_sitio},{a.eixo3()})")
        predio = self.raiz("IFCBUILDING", _texto(self.predio_nome), "$", "$", pl_predio,
                           "$", "$", ".ELEMENT.", _real(0.0), "$", "$")
        self.pav_placement = a.add(f"IFCLOCALPLACEMENT({pl_predio},{a.eixo3()})")
        pavimento = self.raiz("IFCBUILDINGSTOREY", _texto(self.pavimento_nome), "$", "$",
                              self.pav_placement, "$", "$", ".ELEMENT.", _real(0.0))
        self.projeto, self.sitio, self.predio, self.pavimento = projeto, sitio, predio, pavimento
        self._agregar(projeto, [sitio], "Projeto")
        self._agregar(sitio, [predio], "Terreno")
        self._agregar(predio, [pavimento], "Edificação")

    def _agregar(self, pai: str, filhos: List[str], nome: str):
        if filhos:
            self.raiz("IFCRELAGGREGATES", _texto(nome), "$", pai, _lista(filhos))

    # ------------------------------------------------------------ materiais
    def _material(self, nome_aco: str) -> str:
        nome_aco = nome_aco or mat.ACO_PADRAO
        if nome_aco in self._materiais:
            return self._materiais[nome_aco]
        a = self.arq
        ref = a.add(f"IFCMATERIAL({_texto(nome_aco)},$,{_texto('Aço estrutural')})")
        aco = None
        try:
            aco = mat.aco(nome_aco)
        except Exception:
            aco = None
        props = []
        if aco is not None:
            # kN/cm² → MPa: ×10 (GUIA_SISTEMA.md, tabela de unidades)
            props.append(self._prop_valor("YieldStress", "IFCPRESSUREMEASURE",
                                          aco.fy * 10, self.unidades["MPa"],
                                          "resistência ao escoamento f_y"))
            props.append(self._prop_valor("UltimateStress", "IFCPRESSUREMEASURE",
                                          aco.fu * 10, self.unidades["MPa"],
                                          "resistência à ruptura f_u"))
        props.append(self._prop_valor("YoungModulus", "IFCPRESSUREMEASURE",
                                      E_ACO * 10, self.unidades["MPa"],
                                      "módulo de elasticidade E"))
        props.append(self._prop_valor("PoissonRatio", "IFCPOSITIVERATIOMEASURE",
                                      NU_ACO, None, "coeficiente de Poisson"))
        props.append(self._prop_valor("MassDensity", "IFCMASSDENSITYMEASURE",
                                      RHO_ACO, self.unidades["densidade"],
                                      "massa específica"))
        a.add(f"IFCMATERIALPROPERTIES({_texto('Pset_MaterialMechanical')},"
              f"{_opcional_texto(aco.norma if aco else None)},{_lista(props)},{ref})")
        self._materiais[nome_aco] = ref
        return ref

    # ------------------------------------------------------------ propriedades
    def _prop_valor(self, nome: str, tipo: str, valor, unidade: Optional[str] = None,
                    descricao: Optional[str] = None) -> str:
        if tipo == "IFCBOOLEAN":
            bruto = ".T." if valor else ".F."
        elif tipo in ("IFCLABEL", "IFCIDENTIFIER", "IFCTEXT"):
            bruto = _texto(valor)
        elif tipo == "IFCINTEGER":
            bruto = _inteiro(valor)
        else:
            bruto = _real(valor)
        return self.arq.cache(f"IFCPROPERTYSINGLEVALUE({_texto(nome)},"
                              f"{_opcional_texto(descricao)},{tipo}({bruto}),"
                              f"{unidade or '$'})")

    def _pset(self, nome: str, props: List[str], elemento: str):
        if not props:
            return
        chave = ("pset", nome, tuple(props))
        ref = self.arq.por_chave(chave, lambda: self.raiz(
            "IFCPROPERTYSET", _texto(nome), "$", _lista(props)))
        self._por_pset.setdefault(ref, []).append(elemento)

    def _quantidades(self, nome: str, quant: List[str], elemento: str):
        if not quant:
            return
        chave = ("qto", nome, tuple(quant))
        ref = self.arq.por_chave(chave, lambda: self.raiz(
            "IFCELEMENTQUANTITY", _texto(nome), "$", "$", _lista(quant)))
        self._por_pset.setdefault(ref, []).append(elemento)

    def _q(self, classe: str, nome: str, unidade: Optional[str], valor: float) -> str:
        return self.arq.cache(f"{classe}({_texto(nome)},$,{unidade or '$'},"
                              f"{_real(valor)},$)")

    # ------------------------------------------------------------ forma
    def _forma(self, itens: List[str], tipo: str, ent: Entidade) -> str:
        """IfcProductDefinitionShape com a cor no item e a representação na camada."""
        estilo = self._estilo_do_elemento(ent)
        if estilo:
            for item in itens:
                self.arq.add(f"IFCSTYLEDITEM({item},({estilo}),$)")
        rep = self.arq.add(f"IFCSHAPEREPRESENTATION({self.corpo},{_texto('Body')},"
                           f"{_texto(tipo)},{_lista(itens)})")
        if ent.camada:
            self._por_camada.setdefault(ent.camada, []).append(rep)
        return self.arq.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,{_lista([rep])})")

    # ------------------------------------------------------------ aparência
    def _estilo(self, nome: str, cor: str, opacidade: float = 1.0) -> str:
        """IfcSurfaceStyle com IfcSurfaceStyleRendering, um por (nome, cor, opacidade).

        A transparência do IFC é o complemento da opacidade do documento (0 =
        opaco). O estilo é reaproveitado: um galpão tem centenas de peças e meia
        dúzia de materiais.
        """
        r, g, b = _rgb(cor)
        op = 1.0 if opacidade is None else float(opacidade)
        transparencia = min(1.0, max(0.0, 1.0 - op))
        chave = ("estilo", nome, round(r, 6), round(g, 6), round(b, 6),
                 round(transparencia, 6))

        def fabrica():
            rgb = self.arq.cache(f"IFCCOLOURRGB($,{_real(r)},{_real(g)},{_real(b)})")
            render = self.arq.cache(
                f"IFCSURFACESTYLERENDERING({rgb},{_real(transparencia)},"
                f"$,$,$,$,$,$,.NOTDEFINED.)")
            return self.arq.add(f"IFCSURFACESTYLE({_texto(nome)},.BOTH.,({render}))")

        return self.arq.por_chave(chave, fabrica)

    def _estilo_do_elemento(self, ent: Entidade) -> str:
        """Estilo do material de aparência; sem material, o da camada."""
        material = self.doc.materiais.get(ent.material) if ent.material else None
        if material is not None:
            return self._estilo(material.nome, material.cor, material.opacidade)
        camada = self.doc.camadas.get(ent.camada) if ent.camada else None
        if camada is not None:
            return self._estilo(camada.nome, camada.cor, 1.0)
        return ""

    def _camadas(self):
        """Um IfcPresentationLayerWithStyle por camada que tem representação."""
        for nome, reps in self._por_camada.items():
            camada = self.doc.camadas.get(nome)
            cor = camada.cor if camada else "#8a94a6"
            ligada = camada.visivel if camada else True
            bloqueada = camada.bloqueada if camada else False
            estilo = self._estilo(nome, cor, 1.0)
            self.add(f"IFCPRESENTATIONLAYERWITHSTYLE({_texto(nome)},$,{_lista(reps)},$,"
                     f"{'.T.' if ligada else '.F.'},.F.,"
                     f"{'.T.' if bloqueada else '.F.'},({estilo}))")

    def _extrusao(self, perfil_ref: str, profundidade: float,
                  origem=(0.0, 0.0, 0.0)) -> str:
        if profundidade <= 0:
            raise ErroDeDados("profundidade de extrusão precisa ser positiva")
        pos = self.arq.eixo3(origem)
        dz = self.arq.direcao(0.0, 0.0, 1.0)
        return self.arq.add(f"IFCEXTRUDEDAREASOLID({perfil_ref},{pos},{dz},"
                            f"{_real(profundidade)})")

    def _placement(self, pai: str, origem: Ponto, eixo_z=None, eixo_x=None) -> str:
        return self.arq.add(f"IFCLOCALPLACEMENT({pai},"
                            f"{self.arq.eixo3(origem, eixo_z, eixo_x)})")

    # ------------------------------------------------------------ entidades
    def _marca(self, ent: Entidade) -> Optional[str]:
        return (ent.atributos.get("marca") or ent.atributos.get("tag")
                or ent.nome or None)

    def _comum(self, ent: Entidade, tipo_pset: str, extras: List[str]):
        """Pset_XxxCommon + Pset_MetalicaCalculo."""
        if not self.incluir_propriedades:
            return
        at = ent.atributos
        comum = [
            self._prop_valor("Reference", "IFCIDENTIFIER",
                             at.get("referencia") or getattr(ent, "perfil", "") or ent.nome
                             or "—"),
            self._prop_valor("IsExternal", "IFCBOOLEAN", bool(at.get("externo", False))),
            self._prop_valor("LoadBearing", "IFCBOOLEAN", bool(at.get("estrutural", True))),
            self._prop_valor("FireRating", "IFCLABEL", str(at.get("trrf", "") or "")),
        ]
        self._pset(tipo_pset, comum, self.atual)
        if extras:
            self._pset("Pset_MetalicaCalculo", extras, self.atual)

    def _calculo(self, ent: Entidade, perfil: str, aco: str, comprimento: float,
                 peso: float) -> List[str]:
        at = ent.atributos
        props = [
            self._prop_valor("Perfil", "IFCLABEL", perfil or "—"),
            self._prop_valor("Aco", "IFCLABEL", aco or "—", descricao="aço estrutural"),
            self._prop_valor("Comprimento", "IFCLENGTHMEASURE", comprimento,
                             self.unidades["mm"]),
            self._prop_valor("Peso", "IFCMASSMEASURE", peso, self.unidades["kg"]),
        ]
        razao = _primeiro(at, "razao", "razao_aproveitamento", "aproveitamento", "taxa")
        if razao is not None:
            props.append(self._prop_valor("RazaoAproveitamento", "IFCRATIOMEASURE",
                                          float(razao),
                                          descricao="Sd/Rd da verificação que governa"))
        critica = _primeiro(at, "critica", "verificacao_critica", "governante")
        if critica:
            props.append(self._prop_valor("VerificacaoCritica", "IFCLABEL", str(critica)))
        norma = _primeiro(at, "norma", "item_norma")
        if norma:
            props.append(self._prop_valor("Norma", "IFCLABEL", str(norma)))
        situacao = _primeiro(at, "situacao", "ok")
        if situacao is not None:
            texto = situacao if isinstance(situacao, str) else ("OK" if situacao else "Não passa")
            props.append(self._prop_valor("Situacao", "IFCLABEL", texto))
        papel = getattr(ent, "papel", None)
        if papel:
            props.append(self._prop_valor("Papel", "IFCLABEL", str(papel)))
        props += self._reserva_aparencia(ent)
        return props

    def _reserva_aparencia(self, ent: Entidade) -> List[str]:
        """Camada e material de aparência como propriedade: é a reserva para o
        visualizador que descarta IfcPresentationLayer e IfcStyledItem."""
        return [self._prop_valor("Camada", "IFCLABEL", ent.camada or ""),
                self._prop_valor("MaterialAparencia", "IFCLABEL", ent.material or "")]

    # ---- barra ----
    def _barra(self, barra: Barra, pai: str, deslocamento: Ponto):
        comp = barra.comprimento - (barra.recorte_inicio or 0) - (barra.recorte_fim or 0)
        if comp <= PRECISAO:
            raise ErroDeDados(
                f"barra '{barra.nome or barra.id}' fica com comprimento não positivo "
                f"({comp:.1f} mm) depois dos recortes")
        z, x = _eixos_da_barra(barra)
        origem = tuple(barra.inicio[i] + z[i] * (barra.recorte_inicio or 0)
                       - deslocamento[i] for i in range(3))
        perfil_ref, p = _perfil_ifc(self.arq, barra.perfil)
        solido = self._extrusao(perfil_ref, comp)
        forma = self._forma([solido], "SweptSolid", barra)
        placement = self._placement(pai, origem, z, x)
        classe, predefinido = _classe_barra(barra)
        self.atual = self.raiz(classe, _texto(barra.nome or barra.perfil),
                               _opcional_texto(f"{barra.perfil} — {barra.aco}"),
                               _opcional_texto(barra.papel), placement, forma,
                               _opcional_texto(self._marca(barra)), predefinido)
        peso = (p.massa or 0.0) * comp / 1000.0
        self._material(barra.aco)
        self._por_material.setdefault(self._materiais[barra.aco or mat.ACO_PADRAO],
                                      []).append(self.atual)
        self._comum(barra, _PSET_COMUM[classe],
                    self._calculo(barra, barra.perfil, barra.aco, comp, peso))
        if self.incluir_quantidades:
            area_m2 = (p.A or 0.0) * 1e-4                     # cm² → m²
            self._quantidades(_QTO[classe], [
                self._q("IFCQUANTITYLENGTH", "Length", self.unidades["mm"], comp),
                self._q("IFCQUANTITYAREA", "CrossSectionArea", self.unidades["m2"], area_m2),
                self._q("IFCQUANTITYVOLUME", "GrossVolume", self.unidades["m3"],
                        area_m2 * comp / 1000.0),
                self._q("IFCQUANTITYWEIGHT", "GrossWeight", self.unidades["kg"], peso),
            ], self.atual)
        return self.atual

    # ---- chapa ----
    def _chapa(self, chapa: Chapa, pai: str, deslocamento: Ponto):
        if len(chapa.contorno or []) < 3:
            raise ErroDeDados(f"chapa '{chapa.nome or chapa.id}' tem contorno com menos "
                              f"de três pontos")
        if chapa.espessura <= 0:
            raise ErroDeDados(f"chapa '{chapa.nome or chapa.id}' tem espessura nula")
        externo = _anti_horario([(float(a), float(b)) for a, b in chapa.contorno])
        curva = self.arq.polilinha(externo)
        rotulo = _texto(chapa.nome or f"CH {chapa.espessura:g}")
        if chapa.furos:
            vazios = [self.arq.polilinha(_horario(_circulo(
                float(f.get("x", 0.0)), float(f.get("y", 0.0)),
                float(f.get("diametro", 0.0)) / 2)))
                for f in chapa.furos if float(f.get("diametro", 0.0)) > 0]
        else:
            vazios = []
        if vazios:
            perfil_ref = self.arq.cache(
                f"IFCARBITRARYPROFILEDEFWITHVOIDS(.AREA.,{rotulo},{curva},{_lista(vazios)})")
        else:
            perfil_ref = self.arq.cache(
                f"IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,{rotulo},{curva})")
        base = (0.0, 0.0, -chapa.espessura / 2 if chapa.centrada else 0.0)
        solido = self._extrusao(perfil_ref, chapa.espessura, base)
        forma = self._forma([solido], "SweptSolid", chapa)
        origem = tuple(chapa.origem[i] - deslocamento[i] for i in range(3))
        placement = self._placement(pai, origem, chapa.normal, normalizar(chapa.eixo_x))
        self.atual = self.raiz("IFCPLATE", _texto(chapa.nome or "Chapa"),
                               _opcional_texto(f"e = {chapa.espessura:g} mm — {chapa.aco}"),
                               "$", placement, forma,
                               _opcional_texto(self._marca(chapa)), ".SHEET.")
        area_mm2 = chapa.area
        volume_mm3 = area_mm2 * chapa.espessura
        peso = volume_mm3 * RHO_MM3
        self._material(chapa.aco)
        self._por_material.setdefault(self._materiais[chapa.aco or mat.ACO_PADRAO],
                                      []).append(self.atual)
        self._comum(chapa, "Pset_PlateCommon",
                    self._calculo(chapa, f"CH {chapa.espessura:g}", chapa.aco,
                                  _maior_dimensao(externo), peso))
        if self.incluir_quantidades:
            self._quantidades("Qto_PlateBaseQuantities", [
                self._q("IFCQUANTITYLENGTH", "Width", self.unidades["mm"],
                        chapa.espessura),
                self._q("IFCQUANTITYAREA", "NetArea", self.unidades["m2"], area_mm2 * 1e-6),
                self._q("IFCQUANTITYVOLUME", "NetVolume", self.unidades["m3"],
                        volume_mm3 * 1e-9),
                self._q("IFCQUANTITYWEIGHT", "GrossWeight", self.unidades["kg"], peso),
            ], self.atual)
        return self.atual

    # ---- sólido ----
    def _forma_solido(self, solido: Solido, deslocamento: Ponto) -> str:
        """IfcFacetedBrep, por compatibilidade.

        O IFC4 tem o IfcPolygonalFaceSet, que é bem mais econômico (uma
        IfcCartesianPointList3D e índices, em vez de um IfcCartesianPoint por
        vértice de cada face). A escolha aqui é o IfcFacetedBrep mesmo assim, por
        um motivo prático: o FacetedBrep existe desde o IFC2x3 e é lido por todo
        visualizador, enquanto o PolygonalFaceSet ainda esbarra em importadores
        antigos — e o sólido livre é justamente a parte do modelo que não tem
        semântica para compensar uma falha de leitura. Quem quiser o arquivo menor
        passa `solidos_como="tesselacao"`.
        """
        a = self.arq
        pts = [tuple(v[i] - deslocamento[i] for i in range(3)) for v in solido.vertices]
        if self.solidos_como == "tesselacao":
            coords = ",".join("(" + ",".join(_real(c) for c in v) + ")" for v in pts)
            lista = a.add(f"IFCCARTESIANPOINTLIST3D(({coords}),$)")
            refs = [a.add("IFCINDEXEDPOLYGONALFACE((" +
                          ",".join(_inteiro(i + 1) for i in f) + "))")
                    for f in solido.faces]
            item = a.add(f"IFCPOLYGONALFACESET({lista},.T.,{_lista(refs)},$)")
            return self._forma([item], "Tessellation", solido)
        refs_pt = [a.ponto(*v) for v in pts]
        caras = []
        for face in solido.faces:
            if len(face) < 3:
                continue
            loop = a.add("IFCPOLYLOOP(" + _lista([refs_pt[i] for i in face]) + ")")
            limite = a.add(f"IFCFACEOUTERBOUND({loop},.T.)")
            caras.append(a.add(f"IFCFACE({_lista([limite])})"))
        if not caras:
            raise ErroDeDados(f"sólido '{solido.nome or solido.id}' não tem faces")
        casca = a.add("IFCCLOSEDSHELL(" + _lista(caras) + ")")
        return self._forma([a.add(f"IFCFACETEDBREP({casca})")], "Brep", solido)

    def _solido(self, solido: Solido, pai: str, deslocamento: Ponto):
        if not solido.vertices or not solido.faces:
            raise ErroDeDados(f"sólido '{solido.nome or solido.id}' está vazio")
        forma = self._forma_solido(solido, deslocamento)
        placement = self._placement(pai, tuple(deslocamento))
        classe = str(solido.tipo_ifc() or "IfcBuildingElementProxy").upper()
        if classe not in _TIPOS_SOLIDO:
            classe = "IFCBUILDINGELEMENTPROXY"
        predefinido = _TIPOS_SOLIDO[classe]
        self.atual = self.raiz(classe, _texto(solido.nome or "Sólido"), "$", "$",
                               placement, forma,
                               _opcional_texto(self._marca(solido)), predefinido)
        aco = self.doc.materiais.get(solido.material)
        if aco is not None and aco.aco:
            self._material(aco.aco)
            self._por_material.setdefault(self._materiais[aco.aco], []).append(self.atual)
        if self.incluir_quantidades:
            vol = solido.volume
            self._quantidades("Qto_BodyGeometryValidation", [
                self._q("IFCQUANTITYVOLUME", "GrossVolume", self.unidades["m3"], vol * 1e-9),
                self._q("IFCQUANTITYAREA", "SurfaceArea", self.unidades["m2"],
                        _area_faces(solido) * 1e-6),
                self._q("IFCQUANTITYLENGTH", "Height", self.unidades["mm"],
                        _altura(solido)),
                self._q("IFCQUANTITYWEIGHT", "GrossWeight", self.unidades["kg"],
                        vol * RHO_MM3),
            ], self.atual)
        if self.incluir_propriedades:
            self._pset("Pset_MetalicaCalculo", [
                self._prop_valor("Perfil", "IFCLABEL", "—"),
                self._prop_valor("Origem", "IFCLABEL", solido.origem_ifc or "modelado"),
            ] + self._reserva_aparencia(solido), self.atual)
        return self.atual

    # ------------------------------------------------------------ percurso
    def _deslocamento(self, ent: Entidade, memo: Dict[str, Ponto]) -> Ponto:
        """Origem acumulada dos grupos que contêm a entidade.

        O documento guarda coordenada absoluta em toda entidade. Para o
        IfcElementAssembly sair com o ponto de inserção certo **e** a geometria no
        lugar, o conjunto é colocado em `Grupo.origem` e os filhos recebem
        coordenada relativa a ele.
        """
        if not ent.grupo:
            return (0.0, 0.0, 0.0)
        if ent.grupo in memo:
            return memo[ent.grupo]
        pai = self.doc.get(ent.grupo)
        if not isinstance(pai, Grupo):
            return (0.0, 0.0, 0.0)
        avô = self._deslocamento(pai, memo)
        d = (avô[0] + pai.origem[0], avô[1] + pai.origem[1], avô[2] + pai.origem[2])
        memo[ent.grupo] = d
        return d

    def construir(self) -> str:
        self.dono = self._dono()
        unidades = self._unidades()
        self._contextos()
        self._hierarquia(unidades)

        memo: Dict[str, Ponto] = {}
        grupos = [e for e in self.doc.entidades.values() if isinstance(e, Grupo)]
        # 1) os conjuntos primeiro, do mais externo para o mais interno, para que o
        #    filho sempre encontre o IfcLocalPlacement do pai já escrito
        placements: Dict[str, str] = {}
        for g in sorted(grupos, key=lambda g: _profundidade(self.doc, g)):
            pai_pl = placements.get(g.grupo, self.pav_placement)
            pl = self._placement(pai_pl, tuple(g.origem))
            ref = self.raiz("IFCELEMENTASSEMBLY", _texto(g.nome or "Conjunto"), "$", "$",
                            pl, "$", _opcional_texto(self._marca(g)),
                            ".FACTORY.", ".NOTDEFINED.")
            placements[g.id] = pl
            self._grupos_ref[g.id] = ref
            if not g.grupo or g.grupo not in self.doc.entidades:
                self._no_pavimento.append(ref)

        # 2) elementos
        filhos: Dict[str, List[str]] = {}
        for ent in self.doc.entidades.values():
            if isinstance(ent, Grupo) or ent.atributos.get("exportar") is False:
                continue
            desl = self._deslocamento(ent, memo)
            pai_pl = placements.get(ent.grupo, self.pav_placement)
            if isinstance(ent, Barra):
                ref = self._barra(ent, pai_pl, desl)
            elif isinstance(ent, Chapa):
                ref = self._chapa(ent, pai_pl, desl)
            elif isinstance(ent, Solido):
                ref = self._solido(ent, pai_pl, desl)
            else:
                continue
            if ent.grupo and ent.grupo in placements:
                filhos.setdefault(ent.grupo, []).append(ref)
            else:
                self._no_pavimento.append(ref)

        # 3) agregação dos conjuntos, inclusive conjuntos aninhados
        for g in grupos:
            if g.grupo and g.grupo in self._grupos_ref:
                filhos.setdefault(g.grupo, []).append(self._grupos_ref[g.id])
        for gid, lista in filhos.items():
            self._agregar(self._grupos_ref[gid], lista,
                          self.doc.get(gid).nome or "Conjunto")

        # 4) contenção espacial, material e propriedades
        if self._no_pavimento:
            self.raiz("IFCRELCONTAINEDINSPATIALSTRUCTURE", _texto("Elementos"), "$",
                      _lista(self._no_pavimento), self.pavimento)
        self._camadas()
        for material, objetos in self._por_material.items():
            self.raiz("IFCRELASSOCIATESMATERIAL", _texto("Material"), "$",
                      _lista(objetos), material)
        for pset, objetos in self._por_pset.items():
            self.raiz("IFCRELDEFINESBYPROPERTIES", "$", "$", _lista(objetos), pset)

        return self._montar()

    # ------------------------------------------------------------ arquivo
    def _montar(self) -> str:
        carimbo = self.data.replace(microsecond=0).isoformat()
        linhas = [
            "ISO-10303-21;",
            "HEADER;",
            "FILE_DESCRIPTION(('ViewDefinition [DesignTransferView_V1.0]'),'2;1');",
            (f"FILE_NAME({_texto(self.projeto_nome)},{_texto(carimbo)},"
             f"({_texto(self.autor)}),({_texto(self.organizacao)}),"
             f"{_texto(NOME_COMPLETO + ' ' + VERSAO)},{_texto(APLICACAO + ' ' + VERSAO)},"
             f"{_texto(self.autor)});"),
            "FILE_SCHEMA(('IFC4'));",
            "ENDSEC;",
            "DATA;",
        ]
        linhas += self.arq.linhas()
        linhas += ["ENDSEC;", "END-ISO-10303-21;", ""]
        return "\n".join(linhas)


# =========================================================== auxiliares

_PSET_COMUM = {"IFCBEAM": "Pset_BeamCommon", "IFCCOLUMN": "Pset_ColumnCommon",
               "IFCMEMBER": "Pset_MemberCommon"}
_QTO = {"IFCBEAM": "Qto_BeamBaseQuantities", "IFCCOLUMN": "Qto_ColumnBaseQuantities",
        "IFCMEMBER": "Qto_MemberBaseQuantities"}

_PREDEFINIDO_MEMBRO = {"terça": ".PURLIN.", "terca": ".PURLIN.",
                       "contraventamento": ".BRACE.", "longarina": ".PURLIN.",
                       "tirante": ".BRACE.", "montante": ".POST.",
                       "diagonal": ".BRACE.", "banzo": ".CHORD."}


def _classe_barra(barra: Barra) -> Tuple[str, str]:
    classe = str(barra.tipo_ifc()).upper()
    if classe == "IFCCOLUMN":
        return classe, ".COLUMN."
    if classe == "IFCBEAM":
        return classe, ".BEAM."
    return "IFCMEMBER", _PREDEFINIDO_MEMBRO.get((barra.papel or "").lower(), ".MEMBER.")


#: tipos de IfcElement com a mesma assinatura de 9 atributos do IfcBuildingElementProxy
#: (…, Tag, PredefinedType). Só estes são aceitos em `atributos["tipo_ifc"]`; qualquer
#: outro vira proxy, porque escrever uma entidade com o número errado de atributos é a
#: forma mais rápida de fazer o arquivo ser recusado.
_TIPOS_SOLIDO = {
    "IFCBUILDINGELEMENTPROXY": ".NOTDEFINED.", "IFCWALL": ".NOTDEFINED.",
    "IFCSLAB": ".NOTDEFINED.", "IFCFOOTING": ".NOTDEFINED.",
    "IFCPILE": ".NOTDEFINED.", "IFCRAILING": ".NOTDEFINED.",
    "IFCCOVERING": ".NOTDEFINED.", "IFCROOF": ".NOTDEFINED.",
    "IFCSTAIR": ".NOTDEFINED.", "IFCRAMP": ".NOTDEFINED.",
    "IFCBEAM": ".BEAM.", "IFCCOLUMN": ".COLUMN.", "IFCMEMBER": ".MEMBER.",
    "IFCPLATE": ".NOTDEFINED.", "IFCDISCRETEACCESSORY": ".NOTDEFINED.",
    "IFCMECHANICALFASTENER": ".NOTDEFINED.",
}


def _profundidade(doc: Documento, ent: Entidade, limite=32) -> int:
    """Quantos grupos existem acima da entidade (com trava contra ciclo)."""
    n = 0
    atual = ent
    while atual is not None and atual.grupo and n < limite:
        atual = doc.get(atual.grupo)
        n += 1
    return n


def _rgb(cor: str, padrao=(0.54, 0.58, 0.65)) -> Tuple[float, float, float]:
    """'#rrggbb' (ou '#rgb') → componentes de 0 a 1, como pede o IfcColourRgb."""
    t = str(cor or "").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6:
        return padrao
    try:
        return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return padrao


def _primeiro(d: dict, *chaves):
    for k in chaves:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def _maior_dimensao(pontos: Sequence[Tuple[float, float]]) -> float:
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def _area_faces(solido: Solido) -> float:
    total = 0.0
    for face in solido.faces:
        for i in range(1, len(face) - 1):
            a = solido.vertices[face[0]]
            b = solido.vertices[face[i]]
            c = solido.vertices[face[i + 1]]
            total += _norma(produto_vetorial(subtrair(b, a), subtrair(c, a))) / 2
    return total


def _norma(v: Ponto) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _altura(solido: Solido) -> float:
    zs = [v[2] for v in solido.vertices]
    return max(zs) - min(zs) if zs else 0.0


# =========================================================== API pública

def para_texto(documento: Documento, **opcoes) -> str:
    """Devolve o arquivo IFC4 inteiro como texto. É o que os testes conferem."""
    if not isinstance(documento, Documento):
        raise ErroDeDados("esperado um Documento de nucleo3d.modelo")
    return _Exportador(documento, **opcoes).construir()


def exportar(documento: Documento, caminho: str, projeto_nome: str = None,
             autor: str = None, organizacao: str = None,
             incluir_propriedades: bool = True, incluir_quantidades: bool = True,
             **opcoes) -> str:
    """Grava o documento como IFC4 em `caminho` e devolve o caminho.

    Opções extras aceitas: `solidos_como` ('brep' ou 'tesselacao'), `sitio_nome`,
    `predio_nome`, `pavimento_nome`, `descricao` e `data` (datetime).
    """
    texto = para_texto(documento, projeto_nome=projeto_nome, autor=autor,
                       organizacao=organizacao,
                       incluir_propriedades=incluir_propriedades,
                       incluir_quantidades=incluir_quantidades, **opcoes)
    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta, exist_ok=True)
    # o conteúdo é ASCII puro (o não-ASCII sai em \X2\); ascii aqui é uma rede de
    # segurança: se algo escapar sem escape, o erro aparece aqui e não no cliente.
    with open(caminho, "w", encoding="ascii", newline="\n") as f:
        f.write(texto)
    return caminho
