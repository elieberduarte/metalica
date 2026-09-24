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

from nucleo2d.detalhe.base import (  # noqa: E402,F401
    CAMADAS_PECAS,
    CATEGORIAS,
    FAIXAS_COMPLETO,
    FURACAO_TERCA_ALTA,
    FURACAO_TERCA_BAIXA,
    GRUPOS,
    GRUPOS_BASE,
    TITULOS_ANTIGOS,
    LIMITE_TERCA,
    PREFIXO_NOME,
    Ponto,
    RASGO_OBLONGO_TERCA,
    TIPOS_ACESSORIO,
    TIPOS_NOME,
    TIPOS_PECA,
    TOLERANCIA_COMPRIMENTO,
    _PORCAS,
    _Papel,
    _assinatura,
    _assinatura_posicao,
    _caixa,
    _camada_da_posicao,
    _categoria,
    _centros_dos_fixadores,
    _cruz,
    _diametro_do_fixador,
    _dot,
    _eh_redonda_perfil,
    _eh_terca,
    _eixo_da_peca,
    _eixos_da_assinatura,
    _eixos_dos_fixadores,
    _empilhar,
    _fixadores,
    _furo_de_dict,
    _furo_dict,
    _grupos_de_furos,
    _marcas,
    _material,
    _mover,
    _nome_do_parafuso,
    _norm,
    _oblongar,
    _ordenar,
    _pecas,
    _ponto_no_poligono,
    _posicao_de_chapa,
    _posicoes_de,
    _proxy_da_chapa,
    _registrar_camadas_de_pecas,
    _reposicionar,
    _rotulo_espessura,
    _sub,
    _tipo_ifc,
    aplicar_ajustes_de_furos,
    fundir_posicoes_iguais,
    inferir_furos_de_parafusos,
    marcas_de,
    oblongar_tercas,
    parafusos_da_posicao,
    parafusos_no_conjunto,
    regra_furacao_terca,
    vincular_furos_de_ligacao)
from nucleo2d.detalhe.conjuntos import (  # noqa: E402,F401
    FRACAO_COMUM_CONJUNTO,
    MENOR_ITEM_LOCALIZACAO,
    MENOR_TIRANTE,
    TOLERANCIA_CONJUNTO_EXT,
    TOLERANCIA_CONJUNTO_PECA,
    TOLERANCIA_CONJUNTO_SEMELHANTE,
    _agrupar_conjuntos_iguais,
    _assinatura_conjunto,
    _casco,
    _centro,
    _classificar_pecas_do_conjunto,
    _conjuntos_iguais,
    _conjuntos_semelhantes,
    _diferenca_de_composicao,
    _dividir,
    _eixos_do_conjunto,
    _extensao_do_conjunto,
    _instancias,
    _instancias_do_conjunto,
    _itens_de_localizacao,
    _lado_do_conjunto,
    _multiplo,
    _rotular_barras,
    _sobrepoe,
    _tirante_principal,
    desenho_de_contraventamentos,
    desenho_de_localizacao,
    desenho_do_conjunto,
    tesouras_montadas)
from nucleo2d.detalhe.nomes import (  # noqa: E402,F401
    ALCANCE_SUPORTE_TERCA,
    FOLGA_MARQUISE,
    _assinaturas_de_terca,
    _caixa_dos_pilares,
    _chapas_onde_a_terca_encosta,
    _nome_numero,
    _tem_furacao_de_terca,
    aplicar_nomes,
    nomear)
from nucleo2d.detalhe.celulas import (  # noqa: E402,F401
    CAMADAS_DE_CONTORNO,
    LIMITE_DESLOCAMENTO_FURO,
    _cabecalho,
    _caixa_da_chapa,
    _chapa_de_posicao,
    _custo_forma,
    _eixos_pela_forma,
    _furos_da_malha,
    _furos_editaveis,
    _local_na_chapa,
    _mover_fixadores,
    _mover_fixadores_mundo,
    _mundo_da_chapa,
    _orientar_para_vista,
    _origem_da_celula,
    _ponto_da_chapa,
    _pontuacao_vista,
    _posicao_bruta,
    _simetria,
    aplicar_furos,
    aplicar_furos_de_barra,
    aplicar_furos_nas_barras,
    alinhar_furos_das_barras_as_chapas,
    padronizar_furos_das_chapas,
    retirar_furos_sem_uso,
    oblongar_furos_das_tercas,
    contorno_do_desenho,
    converter_chapas,
    desenho_da_posicao,
    detalhar_posicao,
    furos_da_chapa,
    furos_do_desenho,
    regenerar_celula,
    reorientar_chapas)

__all__ = ["detalhar", "GRUPOS", "GRUPOS_BASE", "TITULOS_ANTIGOS", "regra_furacao_terca"]


def _extremos_de(e, esc: float) -> List[Ponto]:
    """Pontos que cercam o que a entidade ocupa no desenho — não só os que a definem: a
    linha de cota deslocada (com o número) e a largura estimada do texto. Sem isso a
    moldura de um quadro passava por cima das cotas e dos títulos das células."""
    if isinstance(e, Cota):
        (x1, y1), (x2, y2) = e.p1, e.p2
        if e.modo == "h":
            y2 = y1
        elif e.modo == "v":
            x2 = x1
        dx, dy = x2 - x1, y2 - y1
        comp = math.hypot(dx, dy)
        if comp < 1e-9:
            return [e.p1, e.p2]
        nx, ny = -dy / comp, dx / comp
        d = float(e.deslocamento or 0.0) * esc
        d2 = d + math.copysign(1.6 * float(e.altura or 2.5) * esc, d if d else 1.0)
        return [e.p1, e.p2, (x1 + nx * d, y1 + ny * d), (x2 + nx * d, y2 + ny * d),
                (x1 + nx * d2, y1 + ny * d2), (x2 + nx * d2, y2 + ny * d2)]
    if isinstance(e, Texto):
        x, y = e.posicao
        h = float(e.altura or 2.5) * esc
        larg = 0.75 * h * len(e.texto or "")
        if e.angulo:
            r = max(larg, h)
            return [(x - r, y - r), (x + r, y + r)]
        x0 = x - larg / 2 if e.alinhamento == "centro" else x - larg if e.alinhamento == "direita" else x
        return [(x0, y), (x0 + larg, y + h)]
    return e.pontos() if hasattr(e, "pontos") else []


def _anexar_faixa(dc: Desenho, banda: Desenho, titulo: str, y_topo: float, meta_faixa: Optional[dict] = None) -> float:
    """Copia as entidades de `banda` para `dc`, transladadas para ficarem abaixo de
    `y_topo` com o título da faixa por cima; funde células e metadados. Devolve o y do
    fundo da faixa."""
    import copy as _copy
    esc = dc.escala
    if not banda.entidades:
        return y_topo
    pontos = [q for e in banda.entidades.values() for q in _extremos_de(e, esc)]
    if not pontos:
        return y_topo
    x0 = min(q[0] for q in pontos)
    topo = max(q[1] for q in pontos)
    fundo = min(q[1] for q in pontos)
    y_titulo = y_topo - 12.0 * esc
    dc.add(Texto(camada="TEXTO", posicao=(0.0, y_titulo), texto=titulo, altura=5.0, atributos={"faixa": titulo}))
    dc.add(Linha(camada="AUXILIAR", a=(0.0, y_titulo - 2.0 * esc), b=(max(q[0] for q in pontos) - x0, y_titulo - 2.0 * esc), atributos={"faixa": titulo}))
    dy = (y_titulo - 6.0 * esc) - topo
    dx = -x0
    for nome, cam in banda.camadas.items():
        if nome not in dc.camadas:
            dc.camadas[nome] = _copy.deepcopy(cam)
    for e in banda.entidades.values():
        e2 = _copy.deepcopy(e)
        _mover(e2, dx, dy)
        e2.atributos = dict(e2.atributos or {}, faixa=titulo)
        dc.add(e2)
    for c in banda.metadados.get("celulas") or []:
        dc.metadados.setdefault("celulas", []).append([round(c[0] + dx, 1), round(c[1] + dy, 1), round(c[2] + dx, 1), round(c[3] + dy, 1)])
    meta = dc.metadados.setdefault("detalhamento", {"grupo": "completo", "posicoes": [], "itens": {}, "editaveis": [],
                                                    "furos_originais": {}, "conjuntos": []})
    for m in (meta_faixa, banda.metadados.get("detalhamento")):
        if not m:
            continue
        meta["posicoes"].extend(k for k in (m.get("posicoes") or []) if k not in meta["posicoes"])
        meta["itens"].update(m.get("itens") or {})
        meta["editaveis"].extend(k for k in (m.get("editaveis") or []) if k not in meta["editaveis"])
        meta["furos_originais"].update(m.get("furos_originais") or {})
        meta["conjuntos"].extend(k for k in (m.get("conjuntos") or []) if k not in meta["conjuntos"])
    for v in banda.vistas:
        v2 = dict(v)
        if v2.get("canto"):
            v2["canto"] = [v2["canto"][0] + dx, v2["canto"][1] + dy]
        dc.vistas.append(v2)
    return fundo + dy


#: Título do quadro de cada tipo de conjunto, na ordem em que os quadros saem.
QUADROS = [("tesoura", "TESOURAS"), ("viga", "VIGAS"), ("pilar", "PILARES"), ("conjunto", "CONJUNTOS"),
           ("agulhamento", "AGULHAMENTOS"), ("contraventamento", "CONTRAVENTAMENTOS"), ("chumbador", "CHUMBADORES")]


#: Título do quadro de cada tipo de posição (peça avulsa), na ordem em que saem.
QUADROS_POSICOES = [("paginacao", "PAGINAÇÃO DAS TELHAS – COMPRIMENTOS REAIS"), ("multidobra", "TELHAS MULTI-DOBRA"), ("cumeeira", "CUMEEIRAS"), ("terca_cobertura", "TERÇAS DE COBERTURA"), ("terca_marquise", "TERÇAS DE MARQUISE"),
                    ("suporte_terca", "SUPORTES DE TERÇA"), ("montagem", "PEÇAS MONTADAS – FRENTE E LATERAL"), ("agulhamento", "AGULHAMENTOS"),
                    ("suporte_agulhamento", "SUPORTES DE AGULHAMENTO"), ("contraventamento", "CONTRAVENTAMENTOS"),
                    ("suporte_contraventamento", "SUPORTES DE CONTRAVENTAMENTO"), ("castanha", "CASTANHAS"),
                    ("barra_roscada", "BARRAS ROSCADAS"), ("gancho", "GANCHOS"), ("chumbador", "CHUMBADORES"), ("cantoneira_forro", "CANTONEIRAS DE FORRO"),
                    ("perfil_fechamento", "PERFIS DE FECHAMENTO"), ("parte", "PEÇAS DE CONJUNTOS"),
                    ("barra", "BARRAS"), ("chapa", "CHAPAS"), ("telha", "TELHAS")]


#: Quadros com uma célula por linha (a terça é comprida e as iguais em tamanho se comparam).
UMA_POR_LINHA = {"terca_cobertura", "terca_marquise"}


#: Quadros do desenho completo por família: o conjunto e as peças que fazem parte dele
#: (a tesoura com as barras e as chapas de base; o agulhamento com o suporte e a barra; o
#: contraventamento com o tirante, a castanha e a barra roscada) ficam juntos.
FAMILIAS = [("tesoura", "TESOURAS"), ("viga", "VIGAS"), ("pilar", "PILARES"), ("conjunto", "CONJUNTOS"),
            ("terca", "TERÇAS E SUPORTES DE TERÇA"), ("agulhamento", "AGULHAMENTOS"),
            ("contraventamento", "CONTRAVENTAMENTOS E TIRANTES"), ("telha", "TELHAS"), ("outros", "OUTRAS PEÇAS")]


def _familia_da_posicao(p, tipo_pos: str, tipo_de_conj: Dict[str, str]) -> str:
    """Família da peça avulsa: pelo tipo de produção dela e, sendo parte de conjunto, pelo
    tipo do conjunto em que ela mais aparece."""
    if tipo_pos in ("agulhamento", "suporte_agulhamento"):
        return "agulhamento"
    if tipo_pos in ("contraventamento", "suporte_contraventamento", "castanha", "gancho", "barra_roscada"):
        return "contraventamento"
    if tipo_pos in ("terca_cobertura", "terca_marquise", "suporte_terca"):
        return "terca"
    if tipo_pos == "chumbador":
        return "tesoura"                              # junto das chapas de base das tesouras"
    if p.classe == "telha":
        return "telha"
    tipos = collections.Counter(tipo_de_conj[c] for c in (p.conjuntos or []) if tipo_de_conj.get(c))
    if tipos:
        t = tipos.most_common(1)[0][0]
        return t if t in dict(FAMILIAS) else "conjunto"
    return "outros"


def _quadros_por_tipo(d: Desenho, fns: Sequence[tuple], largura_max_papel: float = 1400.0,
                      y: float = 0.0, meta: Optional[dict] = None, titulos: Optional[Sequence[tuple]] = None) -> float:
    """Desenha as células agrupadas por tipo, cada grupo dentro de um quadro com título.

    Sem isso as tesouras, os agulhamentos e os contraventamentos saíam numa fila só, na
    ordem em que apareciam no IFC, e quem lia o desenho tinha de garimpar. Cada grupo é
    empilhado à parte (as prateleiras de um não interferem nas do outro) e depois entra no
    desenho abaixo do quadro anterior, com o título e a moldura na camada AUXILIAR.
    """
    grupos: Dict[str, list] = collections.OrderedDict()
    for tipo, f in fns:
        chave = str(tipo or "conjunto")
        grupos.setdefault(chave, []).append(f)
    lista_titulos = list(titulos or QUADROS)
    ordem = [t for t, _ in lista_titulos if t in grupos] + [t for t in grupos if t not in dict(lista_titulos)]
    titulos = dict(lista_titulos)
    for chave in ordem:
        banda = Desenho(nome=chave, escala=d.escala)
        banda.camadas = {k: v for k, v in d.camadas.items()}
        # terças: uma embaixo da outra (já vêm do menor comprimento para o maior) — as do
        # mesmo tamanho com furação diferente ficam lado a lado para conferir
        larg = 1.0 if chave in UMA_POR_LINHA else largura_max_papel
        _empilhar(banda, [(lambda x, y_, f=f: f(banda, x, y_)) for f in grupos[chave]], largura_max_papel=larg)
        titulo = titulos.get(chave) or (chave.upper() + "S")
        y = _anexar_quadro(d, banda, titulo, y, meta)
    return y


def _anexar_quadro(dc: Desenho, banda: Desenho, titulo: str, y_topo: float, meta_faixa: Optional[dict] = None) -> float:
    """Como `_anexar_faixa`, mas com a moldura fechada em volta do grupo. Devolve o y do
    fundo do quadro (o próximo começa abaixo dele). A moldura cerca a extensão real —
    linhas de cota e textos incluídos — e as células que `_empilhar` mediu."""
    esc = dc.escala
    antes = set(dc.entidades)
    n_celulas = len(dc.metadados.get("celulas") or [])
    _anexar_faixa(dc, banda, titulo, y_topo - 8.0 * esc, meta_faixa)
    novas = [dc.entidades[k] for k in dc.entidades if k not in antes]
    pontos = [q for e in novas for q in _extremos_de(e, esc)]
    for c in (dc.metadados.get("celulas") or [])[n_celulas:]:
        pontos += [(c[0], c[1]), (c[2], c[3])]
    if not pontos:
        return y_topo
    x0, x1 = min(q[0] for q in pontos) - 6.0 * esc, max(q[0] for q in pontos) + 6.0 * esc
    y1 = max(q[1] for q in pontos) + 4.0 * esc          # o título já está nos pontos (texto com altura)
    y0 = min(q[1] for q in pontos) - 6.0 * esc
    dc.add(Polilinha(camada="AUXILIAR", vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True,
                     atributos={"quadro": titulo}))
    return y0 - 12.0 * esc


def desenho_completo(faixas: Dict[str, tuple], localizacao: Optional[Desenho]) -> Desenho:
    """"Detalhamento – completo": cada grupo é um quadro (moldura com título), todos na
    escala 1:25 — as células são desenhadas de novo nessa escala, com os furos das
    chapas editáveis como no desenho do grupo; os conjuntos saem nos mesmos quadros por
    tipo do desenho de conjuntos (TESOURAS, CONJUNTOS, AGULHAMENTOS…); a planta de
    localização entra como está, no seu quadro. Serve para navegar por tudo sem trocar
    de desenho; para imprimir, as pranchas."""
    g = GRUPOS_BASE["completo"]
    dc = Desenho(nome=g["titulo"], escala=g["escala"])
    _registrar_camadas_de_pecas(dc)
    y = 0.0
    for chave, titulo in FAIXAS_COMPLETO:
        if chave == "localizacao":
            if localizacao is not None:
                y = _anexar_quadro(dc, localizacao, titulo, y)
            continue
        if "familias" in faixas:
            # quadros por família: cada conjunto junto das peças dele (a planta vem depois)
            if chave == "conjuntos":
                celulas, largura, meta = faixas["familias"][:3]
                y = _quadros_por_tipo(dc, [(fam, f) for fam, _t, f in celulas], largura_max_papel=largura, y=y,
                                      meta=meta, titulos=FAMILIAS)
            continue
        if chave not in faixas:
            continue
        celulas, largura, meta = faixas[chave][:3]
        titulos = faixas[chave][3] if len(faixas[chave]) > 3 else None
        if celulas and isinstance(celulas[0], tuple):     # (tipo, célula): um quadro por tipo
            y = _quadros_por_tipo(dc, celulas, largura_max_papel=largura, y=y, meta=meta, titulos=titulos)
            continue
        banda = Desenho(nome=titulo, escala=g["escala"])
        _empilhar(banda, [(lambda x, y_, f=f: f(banda, x, y_)) for f in celulas], largura_max_papel=largura)
        y = _anexar_quadro(dc, banda, titulo, y, meta)
    dc.metadados.setdefault("detalhamento", {"grupo": "completo", "posicoes": [], "itens": {}, "editaveis": [], "furos_originais": {}, "conjuntos": []})
    dc.metadados["detalhamento"]["grupo"] = "completo"
    return dc


def _unidade_pela_maioria(total: collections.Counter, fracao: float = 0.8):
    """(n, unidade) quando pelo menos `fracao` das posições do conjunto têm quantidade
    múltipla de um mesmo n > 1 (o maior deles); unidade = quantidade / n arredondada. None
    quando nem isso há (conjunto de fato único)."""
    if len(total) < 3:
        return None
    for n in range(max(total.values()), 1, -1):
        if sum(1 for q in total.values() if q % n == 0) >= fracao * len(total):
            unidade = collections.Counter({k: int(round(q / n)) for k, q in total.items() if round(q / n) >= 1})
            return (n, unidade) if unidade else None
    return None


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
    # telhas de fachada: saia 150 mm abaixo da última longarina (regra da fábrica)
    try:
        from nucleo2d.detalhe.telhas import aplicar_saias
        saias = aplicar_saias(posicoes, pecas)
    except Exception:                               # noqa: BLE001 — a regra não pode derrubar o levantamento
        saias = {}
    return {"pecas": pecas, "acessorios": acessorios, "posicoes": posicoes, "camadas": camadas,
            "regra_tercas": mudadas, "ajustes": ajustadas, "saias": saias,
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
    pedidos = list(grupos or GRUPOS.keys())
    # os grupos por classe (chapas, barras, tirantes, telhas, conjuntos em 1:50) são a base de
    # tudo: montados sempre por dentro; só saem como desenho quando pedidos pelo nome antigo
    antigos = [k for k in pedidos if k in GRUPOS_BASE and k not in GRUPOS]
    grupos = list(GRUPOS_BASE.keys())
    lev = levantar(doc, regra_tercas=regra_tercas, avisar=avisar, ajustes=ajustes)
    convertidas = 0
    if converter:
        # chapas planas viram paramétricas: a célula sai com furos editáveis e "Aplicar
        # furos ao modelo 3D" funciona a partir do desenho geral
        avisar("convertendo as chapas planas em chapas paramétricas…")
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
    base: Dict[str, Desenho] = {}             # os desenhos por classe (GRUPOS_BASE)
    avisos: List[str] = []

    conjuntos_info = []
    familias_completo: List[tuple] = []       # (família, tipo, célula): completo e desenhos por família
    tirantes_em_grupo: set = set()            # tirantes já cotados no detalhe do contraventamento
    tipo_de_conj: Dict[str, str] = {}         # marca de conjunto → tipo (tesoura, agulhamento…)
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
            if inst is None or n == 1:
                # uma peça a mais ou a menos numa das instâncias (29 P13 em 8 tesouras de
                # 4) derruba o mdc para 1 e o conjunto inteiro saía desenhado como se fosse
                # uma instância só (os fragmentos juntos batiam com a "unidade" = tudo); a
                # composição da maioria das posições dá a unidade
                robusta = _unidade_pela_maioria(total)
                if robusta:
                    n2, unidade2 = robusta
                    iguais = [i for i in _instancias_do_conjunto(lista, unidade2)
                              if collections.Counter(str(_marcas(e).get("posicao") or e.nome) for e in i) == unidade2]
                    if iguais:
                        difere = ["%s (%d em vez de %d)" % (k, total.get(k, 0), n2 * unidade2.get(k, 0))
                                  for k in sorted(set(total) | set(unidade2), key=_ordem_natural)
                                  if total.get(k, 0) != n2 * unidade2.get(k, 0)]
                        aviso = ("conjunto %s: %d instâncias, %d com a composição desenhada; no total diferem %s"
                                 % (conj, n2, len(iguais), ", ".join(difere)))
                        inst, n, unidade = iguais[0], n2, unidade2
            if inst is None:
                # nunca o conjunto inteiro quando ele está espalhado em vários grupos
                inst = max(insts, key=len) if len(insts) > 1 else lista
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
    avisar("nomes de produção…")
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
    faixas: Dict[str, tuple] = {}          # grupo -> (células, largura, metadados) para o desenho completo
    if celulas:
        avisar("desenhando os conjuntos (%d células)…" % len(celulas))
        g = GRUPOS_BASE["conjuntos"]
        d = Desenho(nome=g["titulo"], escala=g["escala"])
        tipos_conj = nomeacao["tipos_conjuntos"]
        comprimentos = {p.marca: p.comprimento for p in posicoes}
        pesos = {p.marca: p.peso for p in posicoes}
        conformadas = {p.marca for p in posicoes if p.classe == "barra_conformada"}
        # contraventamentos com as mesmas peças de ponta: um detalhe só, cotas empilhadas
        cv: Dict[tuple, list] = collections.OrderedDict()
        fns = []
        # tesouras montadas: as meias no mesmo plano (as duas águas) desenhadas juntas, como a
        # fábrica gabarita; as montadas iguais viram uma célula com a quantidade. A meia que
        # só aparece dentro de montadas não ganha célula própria.
        meias = []
        for ass, grupo in grupos_iguais:
            rot_g = " / ".join(sorted((c[0] for c in grupo), key=_ordem_natural))
            if tipos_conj.get(rot_g) == "tesoura":
                meias += [(rot_g, c[1], c[4]) for c in grupo]
        montadas, meias_cobertas = [], set()
        if meias:
            avisar("tesouras montadas…")
            try:
                montadas, meias_cobertas = tesouras_montadas(meias)
            except Exception as exc:                  # noqa: BLE001 — as meias saem como antes
                avisos.append("tesouras montadas não levantadas: %s" % exc)
        itens_montadas = {}
        montadas.sort(key=lambda m: _ordem_natural(" + ".join(nomes_conj.get(r, r) for r in m["rotulos"])))
        for m in montadas:
            rot_m = " + ".join(m["rotulos"])
            nome_m = " + ".join(nomes_conj.get(r, r) for r in m["rotulos"])
            fns.append(("tesoura", lambda dd, x, y, rot_m=rot_m, m=m, nome_m=nome_m:
                        desenho_do_conjunto(doc, rot_m, m["pecas"], m["n"], dd, x, y, rotular, fundidas=fundidas,
                                            nomes=nomes_pos, nome=nome_m, tipo="tesoura",
                                            conformadas=conformadas, pesos=pesos)))
            itens_montadas[rot_m] = {"quantidade": m["n"], "perfil": "tesoura montada (%s)" % nome_m, "material": "",
                                     "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                                     "categoria": "TESOURAS", "nome": nome_m,
                                     "marcas": [mk for r in m["rotulos"] for mk in r.split(" / ")]}
        for rotulo, inst, n, nota in celulas:
            if rotulo in meias_cobertas:
                continue
            tir = _tirante_principal(inst) if tipos_conj.get(rotulo) == "contraventamento" else None
            if tir is not None:
                marca_t = fundidas.get(str(_marcas(tir).get("posicao") or tir.nome), str(_marcas(tir).get("posicao") or tir.nome))
                chave = tuple(sorted((fundidas.get(m, m), q) for m, q in collections.Counter(
                    str(_marcas(e).get("posicao") or e.nome) for e in inst).items() if fundidas.get(m, m) != marca_t))
                cv.setdefault(chave, []).append((rotulo, inst, n))
                tirantes_em_grupo.add(marca_t)
                continue
            fns.append((tipos_conj.get(rotulo, ""), lambda dd, x, y, rotulo=rotulo, inst=inst, n=n, nota=nota:
                       desenho_do_conjunto(doc, rotulo, inst, n, dd, x, y, rotular, fundidas=fundidas, nota=nota,
                                           nomes=nomes_pos, nome=nomes_conj.get(rotulo, ""), tipo=tipos_conj.get(rotulo, ""),
                                           conformadas=conformadas, pesos=pesos)))
        itens_cv = {}
        for membros in cv.values():
            membros.sort(key=lambda m: _ordem_natural(nomes_conj.get(m[0], m[0])))   # mesma ordem do rótulo da célula
            fns.append(("contraventamento", lambda dd, x, y, membros=membros: desenho_de_contraventamentos(
                doc, membros, dd, x, y, nomes_pos, nomes_conj, fundidas, comprimentos, rotular)))
            chave_cel = " / ".join(m[0] for m in membros)
            itens_cv[chave_cel] = {"quantidade": sum(m[2] for m in membros), "perfil": "contraventamentos %s" % " / ".join(nomes_conj.get(m[0], m[0]) for m in membros),
                                   "material": "", "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                                   "categoria": "CONJUNTOS", "marcas": [mk for m in membros for mk in m[0].split(" / ")],
                                   "nome": " / ".join(nomes_conj.get(m[0], m[0]) for m in membros)}
        _quadros_por_tipo(d, fns, largura_max_papel=1400.0)
        itens = {c["marca"]: {"quantidade": c["instancias"], "perfil": "conjunto de %d peças" % sum(c["composicao"].values()),
                              "material": "", "comprimento": 0, "espessura": 0, "peso": 0, "classe": "Conjunto",
                              "categoria": c["categoria"], "marcas": c["marcas"], "nome": c["nome"]}
                 for c in conjuntos_info}
        itens.update(itens_cv)
        itens.update(itens_montadas)
        d.metadados["detalhamento"] = {"grupo": "conjuntos", "conjuntos": [c["marca"] for c in conjuntos_info], "itens": itens}
        faixas["conjuntos"] = (fns, 1400.0, dict(d.metadados["detalhamento"]))
        familias_completo.extend(((t if t in dict(FAMILIAS) else "conjunto") or "conjunto", t or "conjunto", f) for t, f in fns)
        for c in conjuntos_info:
            for m in c["marcas"]:
                tipo_de_conj[m] = tipos_conj.get(c["marca"], "") or "conjunto"

    # telhas multi-dobra: a fileira de facetas de um conjunto de telhas é uma peça só
    from nucleo2d.detalhe.telhas import multidobras, desenho_da_multidobra, faces_de_telhas, desenho_da_paginacao
    try:
        md = multidobras(pecas)
    except Exception as exc:                      # noqa: BLE001 — o resto do detalhamento sai
        md = {"telhas": [], "posicoes": set()}
        avisos.append("telhas multi-dobra não analisadas: %s" % exc)
    for i, t in enumerate(md["telhas"], 1):
        t["nome"] = "TMD.%d" % i
    md.setdefault("cumeeiras", [])
    for i, cm in enumerate(md["cumeeiras"], 1):
        cm["nome"] = "CM.%d" % i
    for chave in grupos:
        g = GRUPOS_BASE.get(chave)
        if not g or chave in ("conjuntos", "localizacao", "completo"):
            continue
        lista = [p for p in _ordenar(posicoes) if p.classe in g["classes"]
                 and not (p.classe == "telha" and all(m in md["posicoes"] for m in marcas_de(p)))]
        extra_md = md["telhas"] if chave == "telhas" else []
        extra_cm = md["cumeeiras"] if chave == "telhas" else []
        if not lista and not extra_md and not extra_cm:
            continue
        avisar("desenhando %s (%d posições)…" % (g["titulo"].replace("Detalhamento – ", ""), len(lista)))
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
        # terças do menor comprimento para o maior (o resto na ordem de sempre)
        lista.sort(key=lambda p: p.comprimento if (nomeacao["tipos"].get(p.marca) or p.tipo_nome) in UMA_POR_LINHA else 0.0)
        editaveis = ([p.marca for p in lista if p.classe == "chapa" and all(parametricas.get(m, False) for m in marcas_de(p))]
                     + [p.marca for p in lista if p.classe == "barra" and any(f.vista == "frente" for f in p.furos)])
        # um quadro por tipo de peça (terças, suportes de terça, chapas…), como os conjuntos
        celulas_g = []
        if chave == "telhas":
            # paginação: cada face com as chapas lado a lado, marca e comprimento real
            try:
                nome_tl = lambda m: nomes_pos.get(fundidas.get(m, m)) or fundidas.get(m, m)    # noqa: E731
                faces = faces_de_telhas(pecas, md, nome_tl, saias=lev.get("saias") or {})
            except Exception as exc:              # noqa: BLE001
                faces = []
                avisos.append("paginação das telhas não gerada: %s" % exc)
            celulas_g += [("paginacao", (lambda dd, x, y, f=f, i=i: desenho_da_paginacao(f, dd, x, y, i)))
                          for i, f in enumerate(faces, 1)]
        celulas_g += [("multidobra", (lambda dd, x, y, t=t: desenho_da_multidobra(t, dd, x, y, t["nome"]))) for t in extra_md]
        from nucleo2d.detalhe.telhas import desenho_da_cumeeira
        celulas_g += [("cumeeira", (lambda dd, x, y, t=t: desenho_da_cumeeira(t, dd, x, y, t["nome"]))) for t in extra_cm]
        n_frente = len(celulas_g)
        celulas_g += [(nomeacao["tipos"].get(p.marca) or p.tipo_nome or p.classe,
                       (lambda dd, x, y, p=p: desenho_da_posicao(p, dd, x, y, editavel=p.marca in editaveis))) for p in lista]
        # peças montadas (suporte de terça soldado, chapa de base com os chumbadores): junto
        # das chapas, com frente e lateral
        celulas_mont, familias_mont = [], []
        if chave == "chapas":
            from nucleo2d.detalhe.montagens import grupos_montados, desenho_de_montagem
            nome_pc = lambda m: nomes_pos.get(fundidas.get(m, m)) or nomes_conj.get(m) or fundidas.get(m, m)    # noqa: E731
            try:
                montagens = grupos_montados(pecas, _fixadores(doc), nome_pc)
            except Exception as exc:              # noqa: BLE001 — o resto do detalhamento sai
                montagens = []
                avisos.append("peças montadas não levantadas: %s" % exc)
            por_id = {e.id: e for e in pecas}
            for gm in montagens:
                tipos_g = {nomeacao["tipos"].get(fundidas.get(m, m)) for m in gm["marcas"]}
                titulo = "SUPORTE DE TERÇA" if "suporte_terca" in tipos_g else ""
                celulas_mont.append(("montagem", (lambda dd, x, y, gm=gm, titulo=titulo:
                                                  desenho_de_montagem(doc, gm, dd, x, y, titulo, por_id))))
                if "suporte_terca" in tipos_g:
                    familias_mont.append("terca")
                else:
                    conjs = [tipo_de_conj.get(str(_marcas(por_id[i]).get("conjunto") or "")) for i in gm["pecas"] if i in por_id]
                    familias_mont.append(next((t for t in conjs if t in dict(FAMILIAS)), "outros"))
        celulas_g += celulas_mont
        for t in extra_md:
            d.metadados["detalhamento"]["itens"][t["conjunto"]] = {
                "quantidade": t["instancias"], "perfil": "%s multi-dobra" % t["perfil"], "material": t["material"],
                "comprimento": round(t["desenv_ext"]), "espessura": 0, "peso": round(t["peso"], 2),
                "classe": "Telha multi-dobra", "categoria": "TELHAS", "marcas": [t["conjunto"]], "nome": t["nome"]}
        for t in extra_cm:
            d.metadados["detalhamento"]["itens"][t["conjunto"]] = {
                "quantidade": t["instancias"], "perfil": "%s cumeeira" % t["perfil"], "material": t["material"],
                "comprimento": round(t["desenv"]), "espessura": 0, "peso": round(t["peso"], 2),
                "classe": "Cumeeira", "categoria": "TELHAS", "marcas": [t["conjunto"]], "nome": t["nome"]}
        _quadros_por_tipo(d, celulas_g, largura_max_papel=800.0, titulos=QUADROS_POSICOES)
        d.metadados["detalhamento"]["editaveis"] = editaveis
        d.metadados["detalhamento"]["furos_originais"] = {
            p.marca: [_furo_dict(f) for f in p.furos if f.vista == "frente"] for p in lista if p.marca in editaveis}
        faixas[chave] = (celulas_g, 800.0, dict(d.metadados["detalhamento"]), QUADROS_POSICOES)
        familias_completo.extend(("telha", t, f) for t, f in celulas_g[:n_frente])
        # o tirante que já está no detalhe do contraventamento (barra, comprimento e dobra
        # cotados lá) não ganha célula própria: era o mesmo desenho repetido
        familias_completo.extend((_familia_da_posicao(p, nomeacao["tipos"].get(p.marca) or p.tipo_nome, tipo_de_conj), t, f)
                                 for p, (t, f) in zip(lista, celulas_g[n_frente:n_frente + len(lista)])
                                 if not (p.marca in tirantes_em_grupo
                                         and (nomeacao["tipos"].get(p.marca) or p.tipo_nome) == "contraventamento"))
        familias_completo.extend((fam, "montagem", f) for fam, (_, f) in zip(familias_mont, celulas_mont))
        base[chave] = d

    localizacao = None
    if "localizacao" in pedidos or "completo" in pedidos:
        avisar("planta de localização…")
        try:
            localizacao = desenho_de_localizacao(doc, pecas, GRUPOS["localizacao"]["titulo"],
                                                 ignorar=[p.marca for p in posicoes if p.classe == "telha"],
                                                 nomes=nomeacao["ifc"], camadas_pecas=camadas_ifc)
        except ErroDeDados as e:
            avisos.append("planta de localização não gerada: %s" % e)

    if familias_completo:
        # metadados de todos os grupos juntos (itens, editáveis, furos originais)
        meta_todos = {"grupo": "completo", "posicoes": [], "itens": {}, "editaveis": [], "furos_originais": {}, "conjuntos": []}
        for fx in faixas.values():
            m = fx[2] or {}
            meta_todos["posicoes"] += [k for k in (m.get("posicoes") or []) if k not in meta_todos["posicoes"]]
            meta_todos["itens"].update(m.get("itens") or {})
            meta_todos["editaveis"] += [k for k in (m.get("editaveis") or []) if k not in meta_todos["editaveis"]]
            meta_todos["furos_originais"].update(m.get("furos_originais") or {})
            meta_todos["conjuntos"] += [k for k in (m.get("conjuntos") or []) if k not in meta_todos["conjuntos"]]
        faixas["familias"] = (familias_completo, 1400.0, meta_todos)
    # os desenhos pedidos, na ordem de GRUPOS: por família, telhas, chaparias, planta, completo
    for chave, g in GRUPOS.items():
        if chave not in pedidos:
            continue
        if chave == "localizacao":
            if localizacao is not None:
                desenhos[chave] = localizacao
        elif chave == "completo":
            if faixas or localizacao is not None:
                avisar("desenho completo…")
                desenhos[chave] = desenho_completo(faixas, localizacao)
        elif g.get("base"):
            d = base.get(g["base"])
            if d is not None and g["base"] in antigos:
                import copy as _copy
                d = _copy.deepcopy(d)                 # o nome antigo também foi pedido: cada um o seu
            if d is not None:
                d.nome = g["titulo"]
                d.metadados.setdefault("detalhamento", {})["grupo"] = chave
                desenhos[chave] = d
        else:
            cels = [(t, f) for fam, t, f in familias_completo if fam in g["familias"]]
            if not cels:
                continue
            avisar("desenhando %s…" % g["titulo"].replace("Detalhamento – ", ""))
            d = Desenho(nome=g["titulo"], escala=g["escala"])
            _registrar_camadas_de_pecas(d)
            meta = dict(faixas["familias"][2]) if "familias" in faixas else {}
            meta["grupo"] = chave
            _quadros_por_tipo(d, cels, largura_max_papel=1400.0, meta=meta,
                              titulos=list(QUADROS) + [q for q in QUADROS_POSICOES if q[0] not in dict(QUADROS)])
            d.metadados["detalhamento"] = dict(d.metadados.get("detalhamento") or {}, **meta)
            desenhos[chave] = d
    # pedidos pelo nome antigo (chapas, barras, tirantes): os desenhos por classe
    for chave in antigos:
        if chave in base and chave not in desenhos:
            desenhos[chave] = base[chave]

    resumo_pos = []
    for p in _ordenar(posicoes):
        resumo_pos.append({"marca": p.marca, "nome": p.nome, "tipo": nomeacao["tipos"].get(p.marca, ""),
                           "marcas": marcas_de(p), "classe": CLASSES.get(p.classe, p.classe), "perfil": p.perfil,
                           "material": p.material, "quantidade": p.quantidade, "comprimento": round(p.comprimento),
                           "largura": round(p.H), "espessura": round(p.espessura or p.T, 1), "furos": p.rotulo_furos(),
                           "peso": round(p.peso, 3), "peso_total": round(p.peso_total, 2),
                           "conjuntos": list(p.conjuntos), "observacoes": list(p.observacoes)})
    return {"desenhos": desenhos, "posicoes": resumo_pos, "conjuntos": conjuntos_info,
            "multidobras": [{k: v for k, v in t.items() if k not in ("ids", "p1", "p2", "d1", "d2", "I", "T", "sentido")}
                            for t in md["telhas"]],
            "acessorios": acessorios, "regra_tercas": mudadas, "avisos": avisos,
            "peso_total": round(sum(p.peso_total for p in posicoes), 1),
            "objetos_posicoes": posicoes, "objetos_pecas": pecas, "camadas": camadas,
            "convertidas": convertidas, "nomes": nomeacao}
