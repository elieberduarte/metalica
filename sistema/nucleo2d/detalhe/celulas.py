# -*- coding: utf-8 -*-
"""Parte "celulas" do detalhamento (nucleo2d/detalhar.py é a fachada)."""
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

from nucleo2d.detalhe.base import (  # noqa: E402
    TIPOS_NOME,
    TIPOS_PECA,
    _Papel,
    _caixa,
    _categoria,
    _centros_dos_fixadores,
    _cruz,
    _dot,
    _eixos_dos_fixadores,
    _fixadores,
    _furo_de_dict,
    _furo_dict,
    _marcas,
    _material,
    _norm,
    _pecas,
    _posicoes_de,
    _rotulo_espessura,
    compra_da_telha,
    _sub,
    _tipo_ifc,
    aplicar_ajustes_de_furos,
    fundir_posicoes_iguais,
    inferir_furos_de_parafusos,
    marcas_de,
    oblongar_tercas)
from nucleo2d.detalhe.nomes import (  # noqa: E402
    aplicar_nomes)

from saida.dobras import com_bitola  # noqa: E402


def _cabecalho(pos: Posicao) -> List[str]:
    """Legenda enxuta, só o principal: nome e quantidade com o comprimento no título, o
    perfil, os parafusos e o peso. O tipo da peça fica no título do quadro; a marca do
    TecnoMETAL, o material, a contagem de furos, os conjuntos e as observações ficam nos
    metadados e na lista de produção (na célula só poluíam)."""
    titulo = "%s – %02dx" % (pos.nome or pos.marca, pos.quantidade)
    if pos.classe == "chapa_dobrada" and pos.desenvolvimento:
        linhas = [titulo, "%s  %s  desenv. %s x %s mm" % (pos.perfil, _rotulo_espessura(pos),
                                                          _mm(pos.desenvolvimento[0]), _mm(pos.desenvolvimento[1]))]
    elif pos.classe in ("chapa", "chapa_dobrada"):
        linhas = [titulo, "%s  %s" % (pos.perfil, _rotulo_espessura(pos))]
    elif pos.classe == "barra_conformada":
        linhas = [titulo + "   L desenv. %s mm" % _mm(pos.comprimento), com_bitola(pos.perfil)]
    elif pos.classe == "telha":
        c = compra_da_telha(pos)
        return [titulo + "   L = %s mm" % _mm(c["comprimento"]),
                "%s  chapa inteira %s x %s mm (útil %s)" % (pos.perfil, _mm(c["comprimento"]), _mm(c["largura_total"]),
                                                            _mm(c["largura"])),
                "%s kg/pç  total %s kg" % (_mm(c["peso"], 2), _mm(c["peso"] * pos.quantidade, 1))
                + ("  ·  corte em obra (pontilhado)" if c["cortada"] else "")]
    elif pos.classe == "indefinida":
        linhas = [titulo, pos.perfil]
    else:
        linhas = [titulo + "   L = %s mm" % _mm(pos.comprimento), com_bitola(pos.perfil)]
    furos = pos.rotulo_furos() if pos.classe not in ("telha", "indefinida") else ""
    if furos:
        # um furo só: "furo Ø17"; vários: "furos: 4x Ø14, 2x OBL 14x26"
        linhas.append(("furo " + furos[3:]) if (furos.startswith("1x ") and ", " not in furos) else ("furos: " + furos))
    if pos.parafusos or pos.porcas or getattr(pos, "passantes", None):
        linhas.append(("parafusos: " if pos.parafusos else "fixação: ") + pos.rotulo_parafusos())
    if pos.peso:
        linhas.append("%s kg/pç  total %s kg" % (_mm(pos.peso, 2), _mm(pos.peso_total, 1)))
    return linhas


def _cotas_da_terca(p: "_Papel", furos: Sequence[Furo], L: float, off: float, off2: float):
    """Cotas da terça como a máquina de furar trabalha: primeiro a cadeia dos furos duplos
    (duas furações na mesma abscissa — a ligação ao suporte), de ponta a ponta; depois
    cada furo simples (tirante, esticador) cotado a partir do furo duplo mais próximo,
    numa segunda linha. Devolve False sem furo duplo (vale a cadeia comum), True com a
    linha dos duplos só, "dupla" quando também há a linha dos simples."""
    colunas: List[List[float]] = []
    for x in sorted(f.x for f in furos):
        if colunas and x - colunas[-1][-1] <= 2.0:
            colunas[-1].append(x)
        else:
            colunas.append([x])
    duplos = [sum(c) / len(c) for c in colunas if len(c) >= 2]
    simples = [c[0] for c in colunas if len(c) < 2]
    if not duplos:
        return False
    p.cadeia_h([0.0] + duplos + [L], 0, -off, exigir_espaco=False)
    # a linha dos simples fica a 6 mm a mais: o número de um trecho curto da cadeia (60)
    # sai por baixo da linha dela e cairia em cima dos números dos simples
    por_duplo: Dict[float, Dict[float, List[float]]] = collections.defaultdict(lambda: {-1.0: [], 1.0: []})
    for x in simples:
        xd = min(duplos, key=lambda d: abs(d - x))
        por_duplo[xd][1.0 if x > xd else -1.0].append(x)
    extra = 0
    for xd, lados in por_duplo.items():
        esq = sorted(lados[-1.0], key=lambda x: xd - x)
        dir_ = sorted(lados[1.0], key=lambda x: x - xd)
        # o simples mais perto de cada lado numa cadeia só (100 | 100 do furo duplo do meio):
        # uma linha, e os números dos trechos curtos saem para fora, um para cada lado
        p.cadeia_h(esq[:1] + [xd] + dir_[:1], 0, -(off2 + FOLGA_COTA_TERCA), exigir_espaco=False)
        # um 2º simples do mesmo lado (raro) desce uma linha
        for k, x in enumerate(esq[1:] + dir_[1:], 1):
            p.cadeia_h([xd, x], 0, -(off2 + FOLGA_COTA_TERCA + 7.0 * k), exigir_espaco=False)
            extra = max(extra, k)
    return ("dupla", extra) if simples else True


#: Na terça, quanto a linha dos furos simples e a total descem a mais (mm de papel).
FOLGA_COTA_TERCA = 6.0


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
    if pos.nome:
        atr["nome"] = pos.nome                  # o grupo da peça no DXF leva o nome de produção
    p = _Papel(desenho, atr, dx, dy, camada_peca=pos.camada_2d or "")
    esc = desenho.escala
    est = Estilo(escala=esc)
    off, off2, off3 = 10.0, 20.0, 30.0            # mm de papel
    if pos.classe == "indefinida":
        p.texto(0, 0, "%s – %02dx  %s  (sem geometria reconhecida)" % (pos.marca, pos.quantidade, pos.perfil), 3.0 * esc)
        return p.extremos
    if pos.classe == "telha":
        return _desenho_da_telha(pos, p, esc, off, off2, off3)
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
        if editavel and pos.classe == "barra":
            _furos_editaveis(p, atr, furos_frente)     # os da alma; os da mesa (topo) ficam fixos
        else:
            _desenhar_furos(p, est, furos_frente, 0, 0)
    # cotas: cadeia dos furos junto da peça, total mais afastada
    xs = sorted({round(f.x, 1) for f in furos_frente})
    ys = sorted({round(f.y, 1) for f in furos_frente})
    # as cotas dos furos saem sempre (a produção precisa delas), mesmo quando um trecho
    # curto — 35 mm da ponta numa terça em 1:25 — deixa os textos apertados
    terca = pos.tipo_nome in ("terca_cobertura", "terca_marquise")
    cadeia = bool(xs) and ((terca and _cotas_da_terca(p, furos_frente, L, off, off2))
                           or p.cadeia_h([0.0] + xs + [L], 0, -off, exigir_espaco=False))
    if isinstance(cadeia, tuple):                 # terça com a linha dos simples
        p.cota_h(0, L, 0, -(off3 + FOLGA_COTA_TERCA + 7.0 * cadeia[1]))
    else:
        p.cota_h(0, L, 0, -(off3 if cadeia == "dupla" else off2 if cadeia else off))
    # na terça a altura dos furos é o padrão da máquina de corte (50 ou 100 mm): a cadeia
    # vertical só atrapalha; ficam a altura da peça e as cotas horizontais
    cadeia = bool(ys) and not terca and p.cadeia_v([0.0] + ys + [H], L, off, exigir_espaco=False)
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

    if pos.tipo_nome == "gancho" and pos.local:
        _rosca_do_gancho(p, pos, esc, off)

    # título acima da peça (as observações ficam nos metadados e na lista de produção)
    y = H + (off + 2.0) * esc
    linhas = _cabecalho(pos)
    for i, txt in enumerate(reversed(linhas)):
        alt = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, alt * esc)
        y += (alt + 1.2) * esc
    return p.extremos


#: Rosca do gancho (regra da fábrica), na ponta reta, em mm.
ROSCA_GANCHO = 100.0


def _rosca_do_gancho(p, pos: Posicao, esc: float, off: float):
    """A rosca do gancho na ponta reta (a oposta à dobra): as duas linhas finas do fundo
    da rosca ao longo de ROSCA_GANCHO e a cota "ROSCA 100"."""
    L = max(q[0] for q in pos.local)          # a ponta desenhada (pos.L pode ser o desenvolvido)
    perto = lambda u0: [q[1] for q in pos.local if abs(q[0] - u0) <= 30.0]    # noqa: E731
    a, b = perto(0.0), perto(L)
    if not a or not b:
        return
    # a ponta do gancho espalha mais na altura; a reta é a outra
    reta_no_fim = (max(b) - min(b)) <= (max(a) - min(a))
    vs = b if reta_no_fim else a
    vs_ponta = [q[1] for q in pos.local if abs(q[0] - (L if reta_no_fim else 0.0)) <= 2.0] or vs
    v0, v1 = min(vs_ponta), max(vs_ponta)
    d = v1 - v0
    vc = (v0 + v1) / 2.0
    comp = min(ROSCA_GANCHO, 0.9 * L)
    u1, u2 = (L - comp, L) if reta_no_fim else (0.0, comp)
    for s in (-1.0, 1.0):
        p.linha(u1, vc + s * d * 0.32, u2, vc + s * d * 0.32, "ACO-FINO")
    p.linha(u1, v0, u1, v1, "ACO-FINO")
    p.cota_h(u1, u2, v1, 4.0, texto="ROSCA %d" % round(comp))   # rente à barra: o título vem logo acima


class _PapelPontilhado:
    """Recebe as linhas de `_vista` e as põe na camada OCULTA (tracejada), com a largura
    da peça escalada para a largura comercial."""
    def __init__(self, p, k):
        self.p, self.k = p, k

    def linha(self, x1, y1, x2, y2, camada="ACO"):
        self.p.linha(x1, y1 * self.k, x2, y2 * self.k, "OCULTA")


def _desenho_da_telha(pos: Posicao, p: "_Papel", esc: float, off: float, off2: float, off3: float):
    """A telha como vai para a compra: a chapa inteira (comprimento × largura comercial)
    em traço cheio, com as ondas de ponta a ponta; o corte que a peça do modelo tem (ângulo
    do beiral, curva do canto) em pontilhado, porque é feito na obra. A largura do modelo
    (1031 na TP40) vira a comercial (980): o desenho inteiro é escalado nessa direção."""
    c = compra_da_telha(pos)
    L, H = c["comprimento"], float(pos.H or c["largura"])
    B = c["largura_total"]                   # a chapa inteira, com os transpasses
    k = B / H if H > 0 else 1.0
    p.retangulo(0, 0, L, B, "ACO")
    # ondas: pelos vértices da peça inteira (y = largura, z = altura da onda), não pela
    # seção de uma ponta — na peça cortada em diagonal a ponta pega só parte da largura
    grupos: List[List[Tuple[float, float]]] = []
    for y, z in sorted((q[1], q[2]) for q in (pos.local or [])):
        if grupos and y - grupos[-1][-1][0] <= 3.0:
            grupos[-1].append((y, z))
        else:
            grupos.append([(y, z)])
    perfil_onda = [(sum(q[0] for q in g) / len(g), sorted(q[1] for q in g)[len(g) // 2]) for g in grupos]
    for v, _ in perfil_onda:
        if 3.0 < v < H - 3.0:
            p.linha(0, v * k, L, v * k, "ACO-FINO")
    if c["cortada"]:
        _vista(_PapelPontilhado(p, k), pos, (0, 1), 2, +1.0, 0, 0)
    p.cota_h(0, L, 0, -off)
    p.cota_v(0, c["largura"], L, off)          # útil (a que cobre)
    p.cota_v(0, B, L, off2)                    # total, com os transpasses
    x_dir = L + (off3 + off2) * esc
    if len(perfil_onda) >= 2:
        # a onda na largura inteira (linha média da chapa fina)
        w_min = min(w for _, w in perfil_onda)
        w_max = max(w for _, w in perfil_onda)
        p.polilinha([(x_dir + (w - w_min), v * k) for v, w in perfil_onda], fechada=False, camada="ACO")
        p.cota_h(x_dir, x_dir + (w_max - w_min), 0, -off)
        p.cota_v(0, B, x_dir + (w_max - w_min), off)
        p.texto(x_dir, B + 3.0 * esc, "SEÇÃO", 2.0 * esc)
    y = B + (off + 2.0) * esc
    linhas = _cabecalho(pos)
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
    edit = bool(editavel and ((parametrica and pos.classe == "chapa") or pos.classe == "barra"))
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


def aplicar_furos_nas_barras(doc: Documento, ajustes: Optional[dict], marcas: Optional[Sequence[str]] = None,
                             limite: float = LIMITE_DESLOCAMENTO_FURO) -> dict:
    """Leva a furação guardada às malhas das barras, repetindo a passada até assentar: os
    eixos da barra saem da nuvem de vértices e giram um pouco quando os furos andam, então
    a medida seguinte ainda acha um resto de 1–2 mm; em duas ou três passadas zera."""
    total = _aplicar_furos_nas_barras_uma_vez(doc, ajustes, marcas, limite)
    alvo = list(total["posicoes"])
    for _ in range(4):
        if not alvo:
            break
        r = _aplicar_furos_nas_barras_uma_vez(doc, ajustes, alvo, limite)
        if not r["furos"]:
            break
        alvo = list(r["posicoes"])
    return total


def _aplicar_furos_nas_barras_uma_vez(doc: Documento, ajustes: Optional[dict], marcas: Optional[Sequence[str]] = None,
                                      limite: float = LIMITE_DESLOCAMENTO_FURO) -> dict:
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
        if pares is None or any(math.hypot(alvos[k].x - f.x, alvos[k].y - f.y) > limite for f, _, _, k in pares):
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


def _indices_do_furo(ent, laco, eixo, raio):
    """Vértices de um furo da malha: os do laço e os que estão no mesmo cilindro (a outra
    face e a parede) — perto do eixo do furo e no nível da chapa do laço."""
    centro = tuple(sum(ent.vertices[i][j] for i in laco) / len(laco) for j in range(3))
    nivel = _dot(centro, eixo)
    idx = set(laco)
    for i, v in enumerate(ent.vertices):
        d = _sub(v, centro)
        t = _dot(d, eixo)
        lateral = math.sqrt(max(0.0, _dot(d, d) - t * t))
        if lateral <= raio and abs(_dot(v, eixo) - nivel) <= 15.0:
            idx.add(i)
    return centro, idx


def padronizar_furos_das_chapas(doc: Documento, posicoes: Sequence[Posicao]) -> dict:
    """A furação padrão de fábrica (a regra das terças: 60 × 50 mm até 200 mm de altura)
    também nas chapas paramétricas do modelo 3D — o suporte de terça, a chapinha de
    ligação. A regra corrigia só o desenho; no 3D a chapa ficava com os 80 × 60 do IFC e a
    terça, que segue a chapa, também. Cada linha e cada coluna da grade de furos da chapa
    (no sistema dela) vai para o passo novo do mesmo (nº de furos, passo original), em volta
    do mesmo centro. Devolve {"chapas", "furos", "posicoes"}."""
    saida = {"chapas": 0, "furos": 0, "posicoes": []}
    mapa: Dict[str, dict] = {}
    for p in posicoes:
        passos = getattr(p, "regra_passos", None)
        if passos and p.classe in ("chapa", "chapa_dobrada"):
            for m in marcas_de(p):
                mapa[m] = passos

    fixadores = _fixadores(doc)
    movidos: set = set()

    def fileiras(vals):
        grupos = []
        for v in sorted(vals):
            if grupos and v - grupos[-1][-1] <= 1.0:
                grupos[-1].append(v)
            else:
                grupos.append([v])
        return [sum(g) / len(g) for g in grupos]
    for ch in doc.entidades.values():
        if not isinstance(ch, Chapa) or not ch.furos:
            continue
        passos = mapa.get(str(_marcas(ch).get("posicao") or ""))
        if not passos:
            continue
        novos = [dict(f) for f in ch.furos]
        mudou = False
        for eixo in ("x", "y"):
            fil = fileiras([float(f.get(eixo, 0) or 0) for f in novos])
            if len(fil) < 2:
                continue
            passo = fil[1] - fil[0]
            if any(abs((fil[i + 1] - fil[i]) - passo) > 1.0 for i in range(len(fil) - 1)):
                continue                                  # passos desiguais: fica como está
            novo = passos.get((len(fil), int(round(passo))))
            if not novo or abs(novo - passo) < 0.5:
                continue
            centro = (fil[0] + fil[-1]) / 2
            alvo = {k: centro + (k - (len(fil) - 1) / 2) * novo for k in range(len(fil))}
            for f in novos:
                v = float(f.get(eixo, 0) or 0)
                k = min(range(len(fil)), key=lambda i: abs(fil[i] - v))
                f[eixo] = round(alvo[k], 2)
            mudou = True
        if mudou:
            # o parafuso (e a porca, a arruela) que atravessa cada furo anda com ele
            for f0, f1 in zip(ch.furos, novos):
                x0, y0 = float(f0.get("x", 0) or 0), float(f0.get("y", 0) or 0)
                dxl, dyl = float(f1["x"]) - x0, float(f1["y"]) - y0
                if abs(dxl) > 0.01 or abs(dyl) > 0.01:
                    raio = max(float(f0.get("diametro", 0) or 0), float(f0.get("largura", 0) or 0), 14.0) / 2.0 + 4.0
                    _mover_fixadores(ch, (x0, y0), (dxl, dyl), raio, fixadores, movidos)
            ch.furos = novos
            saida["chapas"] += 1
            saida["furos"] += len(novos)
            m = str(_marcas(ch).get("posicao") or "")
            if m not in saida["posicoes"]:
                saida["posicoes"].append(m)
    return saida


def alinhar_furos_das_barras_as_chapas(doc: Documento, limite: float = LIMITE_DESLOCAMENTO_FURO) -> dict:
    """Os furos das barras (terças) seguem os da chapa parafusada nelas: cada furo da malha
    da barra que tem, a menos de `limite` mm e encostado nela, um furo de uma chapa
    paramétrica (o suporte) vai para o centro desse furo — e, se o da chapa é oblongo,
    vira oblongo do mesmo tamanho e no mesmo sentido. É pela geometria, então vale para
    qualquer furação mexida na chapa (redonda ou oblonga, pelo CAD ou pelo 3D), e repetir
    não muda nada. Devolve {"barras", "furos", "oblongos", "posicoes"}."""
    saida = {"barras": 0, "furos": 0, "oblongos": 0, "posicoes": []}
    furos_ch = []
    for ch in doc.entidades.values():
        if not isinstance(ch, Chapa) or not ch.furos:
            continue
        ex, ey = _norm(tuple(ch.eixo_x)), _norm(tuple(ch.eixo_y))
        n = _norm(_cruz(ex, ey))
        for f in ch.furos:
            x, y = float(f.get("x", 0) or 0), float(f.get("y", 0) or 0)
            c = tuple(ch.origem[i] + ex[i] * x + ey[i] * y for i in range(3))
            d = float(f.get("diametro", 0) or 0)
            L, A = float(f.get("largura", 0) or 0), float(f.get("altura", 0) or 0)
            rasgo = None if d > 0 or L <= 0 or A <= 0 else ((ex if L >= A else ey), max(L, A), min(L, A))
            furos_ch.append((c, n, float(ch.espessura or 0), rasgo))
    if not furos_ch:
        return saida
    # grade espacial (500 mm) para achar os furos de chapa perto de cada barra
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for k, fc in enumerate(furos_ch):
        grade[tuple(int(math.floor(v / 500.0)) for v in fc[0])].append(k)
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Solido) or _tipo_ifc(ent) not in TIPOS_PECA or len(ent.vertices or []) < 8:
            continue
        lo = [min(v[i] for v in ent.vertices) - 60.0 for i in range(3)]
        hi = [max(v[i] for v in ent.vertices) + 60.0 for i in range(3)]
        perto = set()
        for gx in range(int(math.floor(lo[0] / 500.0)), int(math.floor(hi[0] / 500.0)) + 1):
            for gy in range(int(math.floor(lo[1] / 500.0)), int(math.floor(hi[1] / 500.0)) + 1):
                for gz in range(int(math.floor(lo[2] / 500.0)), int(math.floor(hi[2] / 500.0)) + 1):
                    for k in grade.get((gx, gy, gz), ()):
                        c = furos_ch[k][0]
                        if all(lo[i] <= c[i] <= hi[i] for i in range(3)):
                            perto.add(k)
        if not perto:
            continue
        marca = str(_marcas(ent).get("posicao") or ent.nome or ent.id)
        pos = _posicao_bruta(ent, marca)
        pos.tipo_ifc = _tipo_ifc(ent)
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "barra" or not pos.eixos:
            continue
        e1, e2, e3 = pos.eixos
        mexeu = 0
        # pares furo da barra × furo da chapa, do mais perto para o mais longe, cada um
        # usado uma vez: furo a furo, um furo a mais da barra (sem uso) perto da ligação
        # "roubava" o furo da chapa do furo certo
        furos_b = []
        pares = []
        for hi, (f, laco, vista) in enumerate(_furos_da_malha(pos)):
            eixo = e3 if vista == "frente" else e2
            centro, idx = _indices_do_furo(ent, laco, eixo, f.d / 2 + 1.0)
            furos_b.append((f, laco, vista, eixo, centro, idx))
            for k in perto:
                c, n, esp, rasgo = furos_ch[k]
                if abs(_dot(n, eixo)) < 0.95:
                    continue                          # chapa em outro plano
                d = _sub(c, centro)
                normal_ = _dot(d, eixo)
                if abs(normal_) > esp / 2.0 + 15.0:
                    continue                          # não encosta na barra
                plano = math.sqrt(max(0.0, _dot(d, d) - normal_ * normal_))
                if plano < limite:
                    pares.append((plano, hi, k))
        pares.sort()
        par_de: Dict[int, int] = {}
        usados = set()
        for plano, hi, k in pares:
            if hi in par_de or k in usados:
                continue
            par_de[hi] = k
            usados.add(k)
        for hi, (f, laco, vista, eixo, centro, idx) in enumerate(furos_b):
            if hi not in par_de:
                continue
            c, n, esp, rasgo = furos_ch[par_de[hi]]
            d = _sub(c, centro)
            delta = tuple(d[i] - eixo[i] * _dot(d, eixo) for i in range(3))
            movido = False
            if math.sqrt(_dot(delta, delta)) > 0.6:
                ent.vertices = [tuple(v[j] + delta[j] for j in range(3)) if i in idx else tuple(v) for i, v in enumerate(ent.vertices)]
                centro = tuple(centro[j] + delta[j] for j in range(3))
                movido = True
            if rasgo is not None:
                # o furo vira oblongo como o da chapa: as duas metades se afastam no sentido
                # do rasgo até o comprimento dele
                u_ = rasgo[0]
                u_ = _norm(tuple(u_[i] - eixo[i] * _dot(u_, eixo) for i in range(3)))
                ts = [_dot(_sub(ent.vertices[i], centro), u_) for i in laco]
                s = (rasgo[1] - (max(ts) - min(ts))) / 2.0
                if s > 0.5:
                    novos = list(ent.vertices)
                    for i in idx:
                        t = _dot(_sub(novos[i], centro), u_)
                        if abs(t) > 0.01:
                            sg = 1.0 if t > 0 else -1.0
                            novos[i] = tuple(novos[i][j] + u_[j] * s * sg for j in range(3))
                    ent.vertices = novos
                    saida["oblongos"] += 1
                    movido = True
            if movido:
                mexeu += 1
        if mexeu:
            saida["barras"] += 1
            saida["furos"] += mexeu
            if marca not in saida["posicoes"]:
                saida["posicoes"].append(marca)
    return saida


#: Até quanto (mm) o furo da barra anda para ir ao parafuso que ficou sem furo.
LIMITE_FURO_SEGUE_PARAFUSO = 250.0


def alinhar_furos_das_barras_aos_parafusos(doc: Documento, ids: Optional[Sequence[str]] = None,
                                           limite: float = LIMITE_FURO_SEGUE_PARAFUSO) -> dict:
    """O furo da barra segue o parafuso: numa ligação mexida à mão (a chapa esticada, os
    parafusos levados a outro lugar), a barra fica com um furo onde não passa parafuso e um
    parafuso passando onde ela não tem furo. Cada furo sem parafuso vai para o parafuso sem
    furo mais perto (no plano da face, mesmo sentido de eixo, até `limite` mm), do par mais
    perto para o mais longe. `alinhar_furos_das_barras_as_chapas` faz o ajuste fino (até
    40 mm, e o oblongo); este cobre o deslocamento grande. `ids`: só essas barras.
    Devolve {"barras", "furos", "posicoes"}."""
    saida = {"barras": 0, "furos": 0, "posicoes": []}
    eixos_fix = _eixos_dos_fixadores(_fixadores(doc))
    parafusos = [(c, a, meio) for c, a, meio, _ext, porca in eixos_fix.values() if not porca]
    if not parafusos:
        return saida
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for k, (c, a, meio) in enumerate(parafusos):
        grade[tuple(int(math.floor(v / 500.0)) for v in c)].append(k)
    alvo = set(ids) if ids else None
    for ent in list(doc.entidades.values()):
        if alvo is not None and ent.id not in alvo:
            continue
        if not isinstance(ent, Solido) or _tipo_ifc(ent) not in TIPOS_PECA or len(ent.vertices or []) < 8:
            continue
        lo = [min(v[i] for v in ent.vertices) - 40.0 for i in range(3)]
        hi = [max(v[i] for v in ent.vertices) + 40.0 for i in range(3)]
        perto = []
        for gx in range(int(math.floor(lo[0] / 500.0)), int(math.floor(hi[0] / 500.0)) + 1):
            for gy in range(int(math.floor(lo[1] / 500.0)), int(math.floor(hi[1] / 500.0)) + 1):
                for gz in range(int(math.floor(lo[2] / 500.0)), int(math.floor(hi[2] / 500.0)) + 1):
                    perto += [k for k in grade.get((gx, gy, gz), ()) if all(lo[i] <= parafusos[k][0][i] <= hi[i] for i in range(3))]
        if not perto:
            continue
        marca = str(_marcas(ent).get("posicao") or ent.nome or ent.id)
        pos = _posicao_bruta(ent, marca)
        pos.tipo_ifc = _tipo_ifc(ent)
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if not pos.classe.startswith("barra") or not pos.eixos:
            continue
        e1, e2, e3 = pos.eixos
        v0_, l0_ = pos.vertices[0], pos.local[0]

        def dentro_da_barra(q):
            # no sistema da peça: dentro do comprimento e da altura (a alma), ou da
            # largura (a mesa) — o parafuso da terça vizinha, no transpasse, fica fora
            d_ = _sub(q, v0_)
            u_, v_, w_ = l0_[0] + _dot(d_, e1), l0_[1] + _dot(d_, e2), l0_[2] + _dot(d_, e3)
            ws_ = [p_[2] for p_ in pos.local]
            return (1.0 < u_ < pos.L - 1.0 and -1.0 < v_ < pos.H + 1.0 and min(ws_) - 1.0 < w_ < max(ws_) + 1.0)
        furos = []
        for f, laco, vista in _furos_da_malha(pos):
            eixo = e3 if vista == "frente" else e2
            raio = max(f.d, f.alt or 0.0) / 2.0 if f.d or f.alt else 7.0
            centro, idx = _indices_do_furo(ent, laco, eixo, raio + 1.0)
            furos.append({"eixo": eixo, "centro": centro, "idx": idx, "raio": raio})

        def passa(k, centro, eixo, raio):
            """O eixo do parafuso k passa pelo furo (centro, eixo, raio)?"""
            c, a, meio = parafusos[k]
            if abs(_dot(a, eixo)) < 0.95:
                return False
            d = _sub(centro, c)
            t = _dot(d, a)
            lateral = math.sqrt(max(0.0, _dot(d, d) - t * t))
            return lateral <= raio + 3.0 and abs(t) <= meio + 20.0
        sem_parafuso = [h for h, fu in enumerate(furos) if not any(passa(k, fu["centro"], fu["eixo"], fu["raio"]) for k in perto)]
        if not sem_parafuso:
            continue
        pares = []
        for k in perto:
            c, a, meio = parafusos[k]
            if any(passa(k, fu["centro"], fu["eixo"], fu["raio"]) for fu in furos):
                continue                              # já tem furo
            for h in sem_parafuso:
                fu = furos[h]
                if abs(_dot(a, fu["eixo"])) < 0.95:
                    continue
                # onde o eixo do parafuso cruza o plano do furo
                t = _dot(_sub(fu["centro"], c), fu["eixo"]) / _dot(a, fu["eixo"])
                if abs(t) > meio + 20.0:
                    continue                          # o parafuso não chega à face
                q = tuple(c[i] + a[i] * t for i in range(3))
                if not dentro_da_barra(q):
                    continue
                dd = math.dist(q, fu["centro"])
                if 0.6 < dd <= limite:
                    pares.append((dd, h, k, q))
        pares.sort()
        usados_h, usados_k = set(), set()
        mexeu = 0
        for dd, h, k, q in pares:
            if h in usados_h or k in usados_k:
                continue
            usados_h.add(h)
            usados_k.add(k)
            fu = furos[h]
            delta = _sub(q, fu["centro"])
            delta = tuple(delta[i] - fu["eixo"][i] * _dot(delta, fu["eixo"]) for i in range(3))
            ent.vertices = [tuple(v[j] + delta[j] for j in range(3)) if i in fu["idx"] else tuple(v) for i, v in enumerate(ent.vertices)]
            mexeu += 1
        if mexeu:
            saida["barras"] += 1
            saida["furos"] += mexeu
            if marca not in saida["posicoes"]:
                saida["posicoes"].append(marca)
    return saida


#: Um furo "tem uso" se a superfície do parafuso ou da barra que passa nele fica a no
#: máximo meio furo + esta folga (mm) do centro do furo.
FOLGA_USO_FURO = 3.0


def _dist_ponto_triangulo(p, a, b, c) -> float:
    """Distância de um ponto a um triângulo 3D (Ericson, Real-Time Collision Detection)."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return math.dist(p, a)
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return math.dist(p, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return math.dist(p, tuple(a[i] + ab[i] * v for i in range(3)))
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return math.dist(p, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return math.dist(p, tuple(a[i] + ac[i] * w for i in range(3)))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return math.dist(p, tuple(b[i] + (c[i] - b[i]) * w for i in range(3)))
    den = 1.0 / (va + vb + vc)
    v, w = vb * den, vc * den
    return math.dist(p, tuple(a[i] + ab[i] * v + ac[i] * w for i in range(3)))


def _dist_ponto_malha(p, ent, limite: float) -> float:
    """Menor distância de `p` à superfície da malha (para quando passa de `limite`)."""
    P = ent.vertices
    melhor = float("inf")
    for f in ent.faces:
        for i in range(1, len(f) - 1):
            d = _dist_ponto_triangulo(p, P[f[0]], P[f[i]], P[f[i + 1]])
            if d < melhor:
                melhor = d
                if melhor <= limite:
                    return melhor
    return melhor


def _limpar_faces(ent, tol: float = 0.01) -> int:
    """Tira da malha o que um furo fechado deixa para trás: no polígono da alma (no IFC, uma
    face só com os furos recortados por "pontes"), os pontos repetidos e as pontas (vai e
    volta ao mesmo ponto); e as faces da parede do furo, que viraram linhas. Sem isso o
    3D triangula errado e o furo fechado aparece como um risco. Devolve quantas faces mudaram."""
    P = ent.vertices
    chave = lambda i: (round(P[i][0] / tol), round(P[i][1] / tol), round(P[i][2] / tol))   # noqa: E731
    novas, mudou = [], 0
    for f in ent.faces:
        g = list(f)
        while True:
            antes = len(g)
            # pontos seguidos no mesmo lugar
            h = []
            for i in g:
                if not h or chave(h[-1]) != chave(i):
                    h.append(i)
            while len(h) > 1 and chave(h[0]) == chave(h[-1]):
                h.pop()
            # pontas: A, X, A → A
            k = 0
            while len(h) >= 3 and k < len(h):
                a, b = h[k - 1], h[(k + 1) % len(h)]
                if chave(a) == chave(b):
                    del h[k]
                    if k < len(h):
                        del h[k]                      # o A repetido logo depois
                    k = max(k - 1, 0)
                else:
                    k += 1
            g = h
            if len(g) == antes:
                break
        if len(g) >= 3:
            s = [0.0, 0.0, 0.0]
            for i in range(1, len(g) - 1):
                c_ = _cruz(_sub(P[g[i]], P[g[0]]), _sub(P[g[i + 1]], P[g[0]]))
                s = [s[0] + c_[0], s[1] + c_[1], s[2] + c_[2]]
            area = math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2) / 2.0
        else:
            area = 0.0
        if area < 1e-3:
            mudou += 1                                # parede do furo fechado: sai
            continue
        if len(g) != len(f):
            mudou += 1
        novas.append(g)
    if mudou:
        ent.faces = novas
    return mudou


#: Furo oblongo da terça, pela regra da fábrica (comprimento no sentido da barra × largura).
OBLONGO_TERCA = (25.0, 13.0)


def oblongar_furos_das_tercas(doc: Documento) -> dict:
    """Regra da fábrica no 3D: todo furo de ligação da terça (vista de frente, até 18 mm) é
    oblongo 25×13 com o rasgo no sentido da barra — o detalhamento já desenhava assim, a
    malha ficava redonda. O furo redondo da chapa parafusada nele (suporte de agulhamento,
    de terça) vira oblongo igual, no mesmo sentido. Repetir não muda nada. Devolve
    {"tercas", "furos", "chapas": furos de chapa}."""
    from nucleo2d.detalhe.base import _eh_terca
    comp, larg = OBLONGO_TERCA
    saida = {"tercas": 0, "furos": 0, "chapas": 0}
    oblongos = []                                     # (centro, eixo do furo, sentido do rasgo)
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Solido) or _tipo_ifc(ent) not in TIPOS_PECA or len(ent.vertices or []) < 8:
            continue
        m = _marcas(ent)
        marca = str(m.get("posicao") or ent.nome or ent.id)
        pos = _posicao_bruta(ent, marca)
        pos.tipo_ifc = _tipo_ifc(ent)
        conj = str(m.get("conjunto") or "")
        pos.conjuntos = [conj] if conj else []
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "barra" or not pos.eixos or not _eh_terca(pos, ent.camada or ""):
            continue
        e1, e2, e3 = pos.eixos
        mexeu = 0
        for f, laco, vista in _furos_da_malha(pos):
            if vista != "frente":
                continue
            centro, idx = _indices_do_furo(ent, laco, e3, f.d / 2 + 1.0)
            ts = [_dot(_sub(ent.vertices[i], centro), e1) for i in laco]
            ws = [_dot(_sub(ent.vertices[i], centro), e2) for i in laco]
            ext_l, ext_w = max(ts) - min(ts), max(ws) - min(ws)
            novos = list(ent.vertices)
            girou = False
            if ext_w > ext_l + 3.0 and ext_w <= comp + 3.0 and ext_l <= 18.0:
                # oblongo em pé (copiado de uma chapa com o rasgo atravessado): as metades
                # voltam para o centro na altura, e o rasgo vai para o sentido da barra
                s2 = (ext_w - ext_l) / 2.0
                for i in idx:
                    t2 = _dot(_sub(novos[i], centro), e2)
                    novo_t2 = math.copysign(max(0.0, abs(t2) - s2), t2)
                    novos[i] = tuple(novos[i][j] + e2[j] * (novo_t2 - t2) for j in range(3))
                ext_w = ext_l
                girou = True
            if ext_w > 18.0:
                continue                              # furo grande: não é de parafuso de terça
            oblongos.append((centro, e3, e1))
            s = (comp - ext_l) / 2.0
            if s <= 0.5 and not girou:
                continue
            for i in idx:
                t = _dot(_sub(novos[i], centro), e1)
                if abs(t) > 0.01:
                    sg = 1.0 if t > 0 else -1.0
                    novos[i] = tuple(novos[i][j] + e1[j] * s * sg for j in range(3))
            ent.vertices = novos
            mexeu += 1
        if mexeu:
            saida["tercas"] += 1
            saida["furos"] += mexeu
    # a chapa parafusada no furo da terça acompanha
    if oblongos:
        grade: Dict[tuple, list] = collections.defaultdict(list)
        for k, (c, _, _) in enumerate(oblongos):
            grade[tuple(int(math.floor(v / 200.0)) for v in c)].append(k)
        for ch in doc.entidades.values():
            if not isinstance(ch, Chapa) or not ch.furos:
                continue
            ex, ey = _norm(tuple(ch.eixo_x)), _norm(tuple(ch.eixo_y))
            n = _norm(_cruz(ex, ey))
            novos, mexeu = [], False
            for f in ch.furos:
                d = float(f.get("diametro", 0) or 0)
                L_, A_ = float(f.get("largura", 0) or 0), float(f.get("altura", 0) or 0)
                oblongo = d <= 0 and L_ > 0 and A_ > 0 and min(L_, A_) <= 18.0
                if not (0 < d <= 18.0) and not oblongo:
                    novos.append(f)
                    continue
                x, y = float(f.get("x", 0) or 0), float(f.get("y", 0) or 0)
                c = tuple(ch.origem[i] + ex[i] * x + ey[i] * y for i in range(3))
                g = tuple(int(math.floor(v / 200.0)) for v in c)
                achou = None
                for gx in (g[0] - 1, g[0], g[0] + 1):
                    for gy in (g[1] - 1, g[1], g[1] + 1):
                        for gz in (g[2] - 1, g[2], g[2] + 1):
                            for k in grade.get((gx, gy, gz), ()):
                                co, eixo, sentido = oblongos[k]
                                if abs(_dot(n, eixo)) < 0.95:
                                    continue
                                dv = _sub(c, co)
                                nrm = _dot(dv, eixo)
                                plano = math.sqrt(max(0.0, _dot(dv, dv) - nrm * nrm))
                                if plano <= 3.0 and abs(nrm) <= float(ch.espessura or 0) / 2.0 + 15.0:
                                    achou = sentido
                if achou is None:
                    novos.append(f)
                    continue
                ao_longo_x = abs(_dot(achou, ex)) >= abs(_dot(achou, ey))
                g2 = {k: v for k, v in f.items() if k != "diametro"}
                g2.update(largura=comp if ao_longo_x else larg, altura=larg if ao_longo_x else comp)
                if oblongo and abs(L_ - g2["largura"]) < 0.5 and abs(A_ - g2["altura"]) < 0.5:
                    novos.append(f)                   # já é o oblongo certo, no sentido certo
                    continue
                novos.append(g2)
                mexeu = True
                saida["chapas"] += 1
            if mexeu:
                ch.furos = novos
    return saida


def retirar_furos_sem_uso(doc: Documento, so_tercas: bool = True) -> dict:
    """Tira das terças (malha 3D) os furos em que não passa nada — nenhum parafuso nem
    barra (tirante, corrente, chumbador): furação padronizada do IFC que a produção furaria
    à toa (a máquina da fábrica não é automática). O furo some fechando a malha nele: os
    vértices do furo vão para o eixo dele, e o detalhamento seguinte já não o vê. Repetir
    não muda nada. Devolve {"barras", "furos", "posicoes": {marca: n}}."""
    from nucleo2d.detalhe.base import _fixadores, _eh_terca, _eh_redonda_perfil
    saida = {"barras": 0, "furos": 0, "posicoes": {}}
    pecas, _ = _pecas(doc)
    # parafusos e barras que podem passar num furo; a caixa só pré-seleciona — a de um
    # tirante em diagonal cobre metros de terça, e o furo tem de estar na barra de verdade
    passantes_e = [f for f in _fixadores(doc)]
    passantes_e += [e for e in pecas if _eh_redonda_perfil(str(_marcas(e).get("perfil") or e.nome or ""))]
    passantes = [_caixa(e) for e in passantes_e]
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for k, cx in enumerate(passantes):
        for gx in range(int(cx[0][0] // 500), int(cx[0][1] // 500) + 1):
            for gy in range(int(cx[1][0] // 500), int(cx[1][1] // 500) + 1):
                for gz in range(int(cx[2][0] // 500), int(cx[2][1] // 500) + 1):
                    grade[(gx, gy, gz)].append(k)
    tol = FOLGA_USO_FURO
    for ent in list(doc.entidades.values()):
        if not isinstance(ent, Solido) or _tipo_ifc(ent) not in TIPOS_PECA or len(ent.vertices or []) < 8:
            continue
        m = _marcas(ent)
        marca = str(m.get("posicao") or ent.nome or ent.id)
        pos = _posicao_bruta(ent, marca)
        pos.tipo_ifc = _tipo_ifc(ent)
        conj = str(m.get("conjunto") or "")
        pos.conjuntos = [conj] if conj else []
        try:
            analisar(pos)
        except Exception:                             # noqa: BLE001
            continue
        if pos.classe != "barra" or not pos.eixos or (so_tercas and not _eh_terca(pos, ent.camada or "")):
            continue
        e1, e2, e3 = pos.eixos
        fechados = 0
        for f, laco, vista in _furos_da_malha(pos):
            eixo = e3 if vista == "frente" else e2
            c, idx = _indices_do_furo(ent, laco, eixo, f.d / 2 + 1.0)
            chave = (int(c[0] // 500), int(c[1] // 500), int(c[2] // 500))
            raio = min(f.d, f.larg or f.d, f.alt or f.d) / 2.0 if (f.larg and f.alt) else f.d / 2.0
            if any(all(passantes[k][i][0] - tol <= c[i] <= passantes[k][i][1] + tol for i in range(3))
                   and _dist_ponto_malha(c, passantes_e[k], raio + tol) <= raio + tol
                   for k in grade.get(chave, ())):
                continue                              # tem parafuso ou barra passando: fica
            ent.vertices = [tuple(c[j] + eixo[j] * _dot(_sub(v, c), eixo) for j in range(3)) if i in idx else tuple(v)
                            for i, v in enumerate(ent.vertices)]
            fechados += 1
        # tira da malha o furo fechado (agora e os que versões anteriores fecharam só
        # juntando os pontos, e que o 3D mostrava como risco)
        if _limpar_faces(ent):
            saida["limpas"] = saida.get("limpas", 0) + 1
        if fechados:
            saida["barras"] += 1
            saida["furos"] += fechados
            saida["posicoes"][marca] = saida["posicoes"].get(marca, 0) + fechados
    return saida


def regenerar_celula(d: Desenho, doc: Documento, marca: str, ajustes: Optional[dict] = None,
                     nomes_producao: Optional[dict] = None) -> Tuple[float, float, float, float]:
    """Redesenha, no mesmo lugar de um desenho geral, a célula da posição (depois de os
    furos ou o tamanho terem mudado no modelo): apaga o que tem a marca e desenha de
    novo, com furos editáveis, a partir do canto onde estava."""
    cont_antigo, origem = contorno_do_desenho(d, marca)
    if cont_antigo is None:
        origem = _origem_da_celula(d, marca)
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
    ext = desenho_da_posicao(pos, d, origem[0], origem[1], editavel=pos.classe in ("chapa", "barra"))
    meta = d.metadados.setdefault("detalhamento", {})
    if pos.classe in ("chapa", "barra"):
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


def _origem_da_celula(d: Desenho, marca: str) -> Tuple[float, float]:
    """Canto inferior esquerdo da peça numa célula sem contorno fechado (barra): o mínimo
    dos traços da peça (vista de frente começa em 0,0 na célula)."""
    xs, ys = [], []
    for e in d.entidades.values():
        a = e.atributos or {}
        if a.get("detalhe") != "posicao" or str(a.get("posicao")) != marca:
            continue
        if getattr(e, "camada", "") in ("COTA", "TEXTO", "EIXO", "FURO", "AUXILIAR"):
            continue
        for x, y in (e.pontos() if hasattr(e, "pontos") else []):
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys)) if xs else (0.0, 0.0)


def aplicar_furos_de_barra(doc: Documento, marca: str, furos_desenho: Sequence[dict], ajustes: dict,
                           limite: float = 300.0) -> dict:
    """Furos da alma lidos do desenho da barra viram a furação da posição: guardados em
    `ajustes` (o que o detalhamento seguinte usa) e levados às malhas do 3D
    (`aplicar_furos_nas_barras`, furo a furo até `limite` mm). Os furos da mesa (topo)
    continuam os da malha. Devolve {"furos", "marcas", "barras3d"}."""
    pecas, _ = _pecas(doc)
    nomes = [m.strip() for m in str(marca).split(" / ") if m.strip()]
    lista = [e for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) in nomes]
    if not lista:
        raise ErroDeDados("a posição %s não está no modelo." % marca)
    posicoes, _ = _posicoes_de(lista, _fixadores(doc))
    topo = [f for p in posicoes[:1] for f in p.furos if f.vista == "topo"]
    frente = []
    for f in furos_desenho:
        reg = {"tipo": f.get("tipo", "redondo"), "x": round(float(f["x"])), "y": round(float(f["y"])),
               "d": round(float(f.get("d", 0) or 0), 1), "larg": round(float(f.get("larg", 0) or 0), 1),
               "alt": round(float(f.get("alt", 0) or 0), 1), "pontos": [], "vista": "frente"}
        if reg["d"] > 0 or reg["larg"] > 0:
            frente.append(reg)
    reg = {"furos": frente + [_furo_dict(f) for f in topo], "origem": "detalhe editado no CAD"}
    for m in nomes:
        ajustes[m] = reg
    r3 = aplicar_furos_nas_barras(doc, {m: reg for m in nomes}, nomes, limite=limite)
    return {"furos": len(frente), "marcas": nomes, "barras3d": r3, "chapas": 0, "contornos": 0, "parafusos": 0}


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
