# -*- coding: utf-8 -*-
"""Lançamento da estrutura sobre o arquitetônico do cliente.

É o meio do caminho que faltava entre a planta do cliente e o modelo que o cálculo e o
detalhamento já sabem usar:

    arquitetônico (DXF/PDF) ──► Planta de lançamento no CAD (referência travada)
                               ──► eixos (malha gerada ou desenhados na camada EIXO)
                               ──► lançar: DadosGalpao → dimensionamento → Documento 3D
                                   posto nos eixos reais, com marcas de posição e conjunto

O motor do galpão (`nucleo.galpao`) é o gerador: ele dimensiona o pórtico (alma cheia ou
treliçado) com o maior espaçamento entre eixos, que é o caso que governa, e o construtor
do 3D (`nucleo3d.de_projeto._Construtor`) monta as peças nas posições reais dos eixos.
O documento que sai é um modelo 3D comum: o cálculo do modelo (`calculo_ifc`), o
Dimensionar, o detalhamento, a lista de materiais e o IFC funcionam nele sem mudar nada.

Convenções: na planta de lançamento as coordenadas do desenho (mm) são as do modelo em
planta (x, y) e z = 0 é o nível dos eixos. Eixos numerados (1, 2, 3…) são as linhas dos
pórticos, atravessadas ao galpão; eixos com letra (A, B…) correm ao longo dele e marcam
as filas de pilares. O formato dos eixos é o de `nucleo3d.eixos` (eixo_g, perp_g,
numeros, letras, z_base), gravado em projeto.json → `eixos`.
"""
from __future__ import annotations

import collections
import copy
import math
import re
import string
from dataclasses import asdict, fields
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import (Arco, Camada2D, Chamada, Circulo, Cota, Desenho, Hachura, Linha,
                              Polilinha, Texto)

#: Nome do desenho do CAD que guarda a referência e os eixos.
DESENHO_LANCAMENTO = "Planta de lançamento"
#: Prefixo das camadas do arquitetônico (travadas, cinza).
PREFIXO_ARQ = "ARQ "
COR_ARQ = "#9aa3ae"
#: Camadas lidas como eixos.
CAMADAS_EIXO = ("EIXO", "EIXOS")
#: Quanto a linha do eixo passa do último eixo atravessado (mm).
FOLGA = 1500.0
#: Raio da bolinha do eixo e altura do nome, em mm de papel.
RAIO_BOLINHA = 5.0
ALTURA_NOME = 4.0
#: Escalas que o arquitetônico em PDF costuma ter (1:N).
ESCALAS_PDF = (20, 25, 50, 75, 100, 125, 150, 200, 250, 500)

#: Parâmetros do lançamento (o que o diálogo pergunta); o resto do galpão fica no padrão.
PADRAO = {
    "sistema": "treliçado",            # "treliçado" (tesoura) ou "alma cheia"
    "pe_direito": 6.0,                  # m, do piso ao topo do pilar
    "inclinacao": 10.0,                 # %
    "espacamento_tercas": 1.6,          # m (alvo)
    "linhas_correntes": 1,              # por vão
    # tesoura: "apoiada" no topo do pilar (com base engastada, é o arranjo que o cálculo do
    # modelo 3D representa igual ao do galpão) ou "rígida" (pilar até o banzo superior)
    "ligacao_tesoura": "apoiada",
    "base_rotulada": None,              # None = engastada na tesoura apoiada, rotulada no resto
    "formato_tesoura": "trapezoidal",
    "diagonais_tesoura": "Howe",
    "altura_tesoura": 0.0,              # m; 0 = automática
    "v0": 40.0, "categoria_rugosidade": "II", "classe": "B", "cidade": "",
    "aberturas": "duas faces opostas",
    "telha": "trapezoidal 0,50 mm",
    "sobrecarga_cobertura": 0.25, "carga_extra": 0.0,
    "aco_perfis": "ASTM A572 Gr.50", "aco_tercas": "CF-26 (NBR 6650)", "aco_chapas": "ASTM A36",
    "fechamento": False,                # telhas e paredes como sólidos (só visual)
    "dimensionar": True,                # dimensiona pelo motor do galpão antes de montar
}


# =====================================================================================
# 1. Arquitetônico: arquivo do cliente → desenho em milímetro real, travado
# =====================================================================================

def _escalar_entidade(e, k: float, dx: float = 0.0, dy: float = 0.0):
    """A entidade com a geometria multiplicada por k e deslocada (o que é de papel —
    altura de texto, deslocamento de cota, espaçamento de hachura — fica igual)."""
    n = copy.deepcopy(e)
    f = lambda q: (round(q[0] * k + dx, 3), round(q[1] * k + dy, 3))     # noqa: E731
    if isinstance(n, Linha):
        n.a, n.b = f(n.a), f(n.b)
    elif isinstance(n, Polilinha):
        n.vertices = [f(q) for q in n.vertices]
    elif isinstance(n, (Circulo, Arco)):
        n.centro = f(n.centro)
        n.raio = n.raio * k
    elif isinstance(n, Texto):
        n.posicao = f(n.posicao)
    elif isinstance(n, Cota):
        n.p1, n.p2 = f(n.p1), f(n.p2)
        if n.texto_pos:
            n.texto_pos = f(n.texto_pos)
    elif isinstance(n, Hachura):
        n.contornos = [[f(q) for q in c] for c in n.contornos]
    elif isinstance(n, Chamada):
        n.alvo, n.posicao = f(n.alvo), f(n.posicao)
    return n


def _escala_pelas_cotas(des: Desenho) -> Tuple[Optional[float], str]:
    """1:N de um PDF pelas cotas escritas (o número dividido pelo comprimento da linha
    de cota no papel), pelo mesmo leitor do projeto recebido. None quando não fecha."""
    try:
        from nucleo2d import reconhecer
        r = reconhecer.reconhecer(des, papel_unidade=True)
    except Exception:                                   # noqa: BLE001 — sem cota legível
        return None, "sem cotas legíveis"
    fatores = collections.Counter()
    fontes = {}
    for v in r.get("vistas") or []:
        origem = v.get("fator_origem")
        if origem in ("cotas", "titulo") and v.get("fator"):
            # a vista maior (a planta) pesa mais que um detalhe de canto
            (x0, y0), (x1, y1) = v.get("caixa") or ((0, 0), (0, 0))
            f = round(float(v["fator"]), 3)
            fatores[f] += 1.0 + abs(x1 - x0) * abs(y1 - y0)
            fontes.setdefault(f, origem)
    if not fatores:
        return None, "sem cotas legíveis"
    f = fatores.most_common(1)[0][0]
    return f, "pelas cotas" if fontes.get(f) == "cotas" else "pelo título da vista"


def ler_arquitetonico(dados: bytes, tipo: str, *, fator: Optional[float] = None,
                      escala_pdf: Optional[float] = None, nome: str = DESENHO_LANCAMENTO) -> Tuple[Desenho, dict]:
    """Arquivo do cliente → (desenho em mm reais, resumo).

    DXF: `fator` é mm por unidade do arquivo (None = pelo $INSUNITS). PDF vetorial: as
    linhas vêm em mm de papel e `escala_pdf` é o N de 1:N (None = pelas cotas; sem cota
    legível, 1:100 com aviso). O desenho é trazido para perto da origem (o canto de
    baixo à esquerda vai a 0,0: DWG de topografia chega com coordenadas UTM) e todas as
    camadas ganham o prefixo "ARQ ", cor cinza e trava: aparecem e dão snap, mas não se
    selecionam nem se apagam por engano."""
    tipo = (tipo or "").lower().lstrip(".")
    avisos: List[str] = []
    if tipo == "dxf":
        from nucleo2d.dxf_ler import para_desenho, texto_de_bytes
        des = Desenho(nome=nome, escala=100.0)
        des, lido = para_desenho(texto_de_bytes(dados), escala=des.escala, fator=fator, destino=des,
                                 prefixo_camada=PREFIXO_ARQ)
        escala_txt = "fator %s mm/unidade" % lido.get("fator")
        fonte = "informado" if fator else ("pelo arquivo ($INSUNITS)" if lido.get("insunits") else "milímetro (sem unidade no arquivo)")
    elif tipo == "pdf":
        from nucleo2d.pdf_ler import para_desenho
        papel = Desenho(nome=nome, escala=1.0)
        papel, lido = para_desenho(dados, destino=papel, prefixo_camada=PREFIXO_ARQ)
        avisos += list(lido.get("avisos") or [])
        fonte = "informado"
        N = float(escala_pdf) if escala_pdf else None
        if not N:
            N, fonte = _escala_pelas_cotas(papel)
            if not N:
                N, fonte = 100.0, "padrão"
                avisos.append("Não achei cotas legíveis no PDF: adotei 1:100. Confira com Calibrar escala "
                              "(dois pontos de medida conhecida) antes de lançar os eixos.")
        des = Desenho(nome=nome, escala=float(N))
        des.camadas = {k: v for k, v in papel.camadas.items()}
        for e in papel.entidades.values():
            des.add(_escalar_entidade(e, N))
        escala_txt = "1:%g" % N
    else:
        raise ErroDeDados("o arquitetônico tem de vir em DXF ou PDF (DWG: salve como DXF no CAD de origem).")
    if not des.entidades:
        raise ErroDeDados("o arquivo não trouxe linhas nem textos que o CAD leia.")
    # para perto da origem
    (x0, y0), (x1, y1) = des.caixa()
    if abs(x0) > 1.0 or abs(y0) > 1.0:
        movidas = {k: _escalar_entidade(e, 1.0, -x0, -y0) for k, e in des.entidades.items()}
        des.entidades = movidas
    # camadas do arquivo: cinza e travadas
    for k, c in list(des.camadas.items()):
        if k.startswith(PREFIXO_ARQ):
            c.cor, c.bloqueada, c.espessura = COR_ARQ, True, 0.13
    largura, altura = x1 - x0, y1 - y0
    if max(largura, altura) > 2_000_000.0:
        avisos.append("O desenho tem %s m de extensão: confira a unidade (Calibrar escala)." % _fmt_m(max(largura, altura)))
    if 0 < max(largura, altura) < 2_000.0:
        avisos.append("O desenho tem só %s m de extensão: confira a unidade (Calibrar escala)." % _fmt_m(max(largura, altura)))
    des.metadados["lancamento"] = True
    des.metadados["arquitetonico"] = {"tipo": tipo, "escala": escala_txt, "fonte_escala": fonte,
                                      "deslocamento": [round(-x0, 3), round(-y0, 3)],
                                      "largura_mm": round(largura, 1), "altura_mm": round(altura, 1)}
    resumo = {"entidades": len(des.entidades), "camadas": sorted(k for k in des.camadas if k.startswith(PREFIXO_ARQ)),
              "escala": escala_txt, "fonte_escala": fonte, "largura_m": round(largura / 1000.0, 2),
              "altura_m": round(altura / 1000.0, 2), "avisos": avisos,
              "por_tipo": dict(collections.Counter(e.tipo for e in des.entidades.values()))}
    return des, resumo


def _fmt_m(mm: float) -> str:
    return ("%.2f" % (mm / 1000.0)).replace(".", ",")


def desenho_de_lancamento(referencia: Desenho, anterior: Optional[dict] = None) -> Desenho:
    """A planta de lançamento: a referência nova mais o que já havia no desenho anterior
    fora das camadas do arquitetônico (os eixos, as notas)."""
    des = referencia
    if anterior:
        velho = Desenho.de_dict(anterior)
        for k, c in velho.camadas.items():
            if not k.startswith(PREFIXO_ARQ):
                des.camadas.setdefault(k, c)
        for e in velho.entidades.values():
            if not str(e.camada).startswith(PREFIXO_ARQ):
                des.add(e)
    des.camadas.setdefault("EIXO", Camada2D("EIXO", "#c0392b", tipo_linha="CENTER", espessura=0.18))
    des.nome = DESENHO_LANCAMENTO
    return des


def segmentos_da_referencia(des: Desenho, limite: int = 120_000) -> List[List[int]]:
    """As linhas do arquitetônico como segmentos [x1, y1, x2, y2] em mm inteiros, para o
    modelo 3D desenhar no chão. Acima de `limite`, ficam os mais compridos (paredes antes
    de hachuras de piso e mobiliário)."""
    segs: List[Tuple[float, List[int]]] = []

    def add(a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L >= 1.0:
            segs.append((L, [int(round(a[0])), int(round(a[1])), int(round(b[0])), int(round(b[1]))]))
    for e in des.entidades.values():
        if not str(e.camada).startswith(PREFIXO_ARQ):
            continue
        if isinstance(e, Linha):
            add(e.a, e.b)
        elif isinstance(e, Polilinha):
            vs = list(e.vertices)
            for a, b in zip(vs, vs[1:] + ([vs[0]] if e.fechada and len(vs) > 2 else [])):
                add(a, b)
        elif isinstance(e, (Circulo, Arco)):
            a0, a1 = (0.0, 360.0) if isinstance(e, Circulo) else (e.inicio, e.fim if e.fim > e.inicio else e.fim + 360.0)
            n = max(4, min(24, int((a1 - a0) / 15.0)))
            pts = [(e.centro[0] + e.raio * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                    e.centro[1] + e.raio * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
            for a, b in zip(pts, pts[1:]):
                add(a, b)
    if len(segs) > limite:
        segs.sort(key=lambda s: -s[0])
        segs = segs[:limite]
    return [s for _L, s in segs]


# =====================================================================================
# 2. Eixos: malha gerada e leitura das linhas da camada EIXO
# =====================================================================================

def _letra(i: int) -> str:
    letras = string.ascii_uppercase
    return letras[i] if i < 26 else letras[i // 26 - 1] + letras[i % 26]


def ler_vaos(texto) -> List[float]:
    """"5x6000", "6000 6000 7500", "3×6m + 7,5m" → [mm, …]. Aceita lista pronta."""
    if isinstance(texto, (list, tuple)):
        return [float(v) for v in texto if float(v) > 0]
    t = str(texto or "").lower().replace("×", "x").replace("+", " ").replace(";", " ")
    saida: List[float] = []
    for tok in t.split():
        m = re.fullmatch(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?", tok)
        if not m:
            raise ErroDeDados("não entendi o vão \"%s\": use 6000, 6m, 5x6000 ou 3x6m" % tok)
        n = int(m.group(1) or 1)
        v = float(m.group(2).replace(",", "."))
        un = m.group(3) or ("m" if v < 100 else "mm")
        v *= {"mm": 1.0, "cm": 10.0, "m": 1000.0}[un]
        if v <= 0:
            continue
        saida += [v] * n
    return saida


def malha_de_eixos(origem: Sequence[float], vaos_numeros, vaos_letras, *, angulo: float = 0.0,
                   escala: float = 100.0, primeiro_numero: int = 1, primeira_letra: str = "A") -> Desenho:
    """A malha de eixos desenhada: linhas na camada EIXO (traço-ponto), a bolinha com o
    nome numa ponta e as cotas entre eixos e a total por fora. `vaos_numeros` são as
    distâncias entre os eixos numerados (os pórticos, ao longo do galpão); `vaos_letras`
    entre os eixos com letra (as filas de pilares). `angulo` gira a malha (graus, anti-horário)
    em volta de `origem`, que é o cruzamento do primeiro número com a primeira letra."""
    vn, vl = ler_vaos(vaos_numeros), ler_vaos(vaos_letras)
    if not vn or not vl:
        raise ErroDeDados("informe ao menos um vão em cada direção (entre os números e entre as letras).")
    E = float(escala or 100.0)
    ang = math.radians(float(angulo or 0.0))
    g = (math.cos(ang), math.sin(ang))            # ao longo do galpão (eixos numerados se sucedem)
    p = (-g[1], g[0])                             # atravessado (letras se sucedem)
    ox, oy = float(origem[0]), float(origem[1])

    def P(s, t):
        return (round(ox + g[0] * s + p[0] * t, 2), round(oy + g[1] * s + p[1] * t, 2))
    ss = [0.0]
    for v in vn:
        ss.append(ss[-1] + v)
    ts = [0.0]
    for v in vl:
        ts.append(ts[-1] + v)
    r = RAIO_BOLINHA * E
    folga = max(FOLGA, 3.0 * r)
    des = Desenho(nome="malha", escala=E)
    for i, s in enumerate(ss):
        nome = str(primeiro_numero + i)
        des.add(Linha(camada="EIXO", a=P(s, -folga), b=P(s, ts[-1] + folga), atributos={"eixo": nome, "malha": True}))
        c = P(s, -folga - r)
        des.add(Circulo(camada="EIXO", centro=c, raio=r, atributos={"eixo": nome, "bolinha": True}))
        des.add(Texto(camada="EIXO", posicao=c, texto=nome, altura=ALTURA_NOME, alinhamento="centro", vertical="meio",
                      angulo=0.0, atributos={"eixo": nome, "nome_eixo": True}))
    base_letra = string.ascii_uppercase.index(primeira_letra.upper()[0]) if primeira_letra else 0
    for j, t in enumerate(ts):
        nome = _letra(base_letra + j)
        des.add(Linha(camada="EIXO", a=P(-folga, t), b=P(ss[-1] + folga, t), atributos={"eixo": nome, "malha": True}))
        c = P(-folga - r, t)
        des.add(Circulo(camada="EIXO", centro=c, raio=r, atributos={"eixo": nome, "bolinha": True}))
        des.add(Texto(camada="EIXO", posicao=c, texto=nome, altura=ALTURA_NOME, alinhamento="centro", vertical="meio",
                      angulo=0.0, atributos={"eixo": nome, "nome_eixo": True}))
    # cotas: entre eixos a 0,4·folga do primeiro eixo cruzado, a total a 0,75·folga (entre a
    # obra e as bolinhas; as bolinhas começam em −folga). Deslocamento em mm de papel,
    # positivo à esquerda do sentido p1→p2.
    d1, d2 = 0.4 * folga / E, 0.75 * folga / E
    for a, b in zip(ss, ss[1:]):
        des.add(Cota(p1=P(a, 0.0), p2=P(b, 0.0), deslocamento=-d1, atributos={"malha": True}))
    if len(ss) > 2:
        des.add(Cota(p1=P(ss[0], 0.0), p2=P(ss[-1], 0.0), deslocamento=-d2, atributos={"malha": True}))
    for a, b in zip(ts, ts[1:]):
        des.add(Cota(p1=P(0.0, a), p2=P(0.0, b), deslocamento=d1, atributos={"malha": True}))
    if len(ts) > 2:
        des.add(Cota(p1=P(0.0, ts[0]), p2=P(0.0, ts[-1]), deslocamento=d2, atributos={"malha": True}))
    return des


_NOME_NUM = re.compile(r"^\d{1,3}'?$")
_NOME_LETRA = re.compile(r"^[A-Z]{1,2}'?$")


def eixos_do_desenho(des: Desenho) -> dict:
    """Os eixos pelas linhas da camada EIXO (ou EIXOS) do desenho, no formato de
    `nucleo3d.eixos`. As linhas se dividem em duas famílias de direção; o nome de cada
    eixo é o texto curto (1, 2… ou A, B…) na bolinha junto de uma das pontas. A família
    de números é a dos pórticos; sem nomes, é a família com mais linhas (empate: a de
    linhas mais curtas, que atravessam o vão)."""
    linhas = []
    for e in des.entidades.values():
        if str(e.camada).upper() not in CAMADAS_EIXO:
            continue
        if isinstance(e, Linha):
            a, b = e.a, e.b
        elif isinstance(e, Polilinha) and len(e.vertices) == 2 and not e.fechada:
            a, b = e.vertices
        else:
            continue
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 500.0:
            continue
        linhas.append({"a": tuple(a), "b": tuple(b), "L": L, "ang": math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi,
                       "nome": str((e.atributos or {}).get("eixo") or "")})
    if len(linhas) < 4:
        raise ErroDeDados("a camada EIXO tem %d linha(s) de eixo: são precisas ao menos duas em cada direção "
                          "(use Malha de eixos… ou desenhe as linhas na camada EIXO)." % len(linhas))
    textos = [e for e in des.entidades.values() if isinstance(e, Texto)
              and (_NOME_NUM.match(e.texto.strip().upper()) or _NOME_LETRA.match(e.texto.strip().upper()))]
    # nomes que não vieram gravados na linha: o texto curto junto de uma ponta
    raio = max(RAIO_BOLINHA * float(des.escala or 100.0) * 2.5, 600.0)
    for ln in linhas:
        if ln["nome"]:
            continue
        melhor, dm = "", raio
        for t in textos:
            for q in (ln["a"], ln["b"]):
                d = math.hypot(t.posicao[0] - q[0], t.posicao[1] - q[1])
                if d < dm:
                    melhor, dm = t.texto.strip().upper(), d
        ln["nome"] = melhor

    # duas famílias de direção
    def dif(a1, a2):
        d = abs(a1 - a2) % math.pi
        return min(d, math.pi - d)
    ref = max(linhas, key=lambda l: l["L"])["ang"]
    f1 = [l for l in linhas if dif(l["ang"], ref) < math.radians(2.0)]
    resto = [l for l in linhas if l not in f1]
    if not resto:
        raise ErroDeDados("os eixos estão todos na mesma direção: faltam os da outra direção.")
    ref2 = max(resto, key=lambda l: l["L"])["ang"]
    f2 = [l for l in resto if dif(l["ang"], ref2) < math.radians(2.0)]
    avisos = []
    fora = len(resto) - len(f2)
    if fora:
        avisos.append("%d linha(s) da camada EIXO fora das duas direções da malha ficaram de fora." % fora)
    if abs(dif(ref, ref2) - math.pi / 2) > math.radians(1.5):
        raise ErroDeDados("as duas direções de eixos não são perpendiculares (%.1f°): o lançamento é de galpão "
                          "retangular." % math.degrees(dif(ref, ref2)))

    def tipo_fam(f):
        nomes = [l["nome"] for l in f if l["nome"]]
        n = sum(1 for x in nomes if _NOME_NUM.match(x))
        l_ = sum(1 for x in nomes if _NOME_LETRA.match(x))
        return "numeros" if n > l_ else ("letras" if l_ > n else "")
    t1, t2 = tipo_fam(f1), tipo_fam(f2)
    if t1 == "numeros" or t2 == "letras":
        fn, fl = f1, f2
    elif t1 == "letras" or t2 == "numeros":
        fn, fl = f2, f1
    elif len(f1) != len(f2):
        fn, fl = (f1, f2) if len(f1) > len(f2) else (f2, f1)
    else:
        med = lambda f: sum(l["L"] for l in f) / len(f)       # noqa: E731
        fn, fl = (f1, f2) if med(f1) <= med(f2) else (f2, f1)
    # g: perpendicular às linhas dos pórticos (numeradas), apontando para x+ (ou y+)
    an = fn[0]["ang"]
    g = (-math.sin(an), math.cos(an))
    if g[0] < -1e-9 or (abs(g[0]) <= 1e-9 and g[1] < 0):
        g = (-g[0], -g[1])
    p = (-g[1], g[0])

    def pos(l, v):
        mx, my = (l["a"][0] + l["b"][0]) / 2.0, (l["a"][1] + l["b"][1]) / 2.0
        return mx * v[0] + my * v[1]

    def lista(fam, v, auto):
        itens = sorted(({"pos": round(pos(l, v), 1), "nome": l["nome"]} for l in fam), key=lambda x: x["pos"])
        unicos: List[dict] = []
        for it in itens:
            if unicos and abs(it["pos"] - unicos[-1]["pos"]) < 50.0:     # a mesma linha duas vezes
                unicos[-1]["nome"] = unicos[-1]["nome"] or it["nome"]
                continue
            unicos.append(it)
        usados = {it["nome"] for it in unicos if it["nome"]}
        for i, it in enumerate(unicos):
            if not it["nome"]:
                cand = auto(i)
                while cand in usados:
                    cand += "'"
                it["nome"] = cand
                usados.add(cand)
        return unicos
    numeros = lista(fn, g, lambda i: str(i + 1))
    letras = lista(fl, p, _letra)
    return {"eixo_g": [round(g[0], 6), round(g[1], 6)], "perp_g": [round(p[0], 6), round(p[1], 6)],
            "numeros": numeros, "letras": letras, "z_base": 0.0, "origem": "desenho",
            "fonte_letras": "planta de lançamento", "avisos": avisos}


# =====================================================================================
# 3. Lançar: eixos + parâmetros → modelo 3D (dimensionado pelo motor do galpão)
# =====================================================================================

def geometria_dos_eixos(eixos: dict) -> dict:
    """O que os eixos dizem do galpão: posições dos pórticos (mm, a partir do primeiro),
    vão (entre a primeira e a última letra) e o maior espaçamento."""
    nums = sorted(eixos.get("numeros") or [], key=lambda e: e["pos"])
    letras = sorted(eixos.get("letras") or [], key=lambda e: e["pos"])
    if len(nums) < 2:
        raise ErroDeDados("são precisos ao menos dois eixos numerados (pórticos) para lançar.")
    if len(letras) < 2:
        raise ErroDeDados("são precisos ao menos dois eixos com letra (filas de pilares) para lançar.")
    xs = [round(n["pos"] - nums[0]["pos"], 1) for n in nums]
    esp = [b - a for a, b in zip(xs, xs[1:])]
    vao = letras[-1]["pos"] - letras[0]["pos"]
    avisos = []
    if len(letras) > 2:
        avisos.append("Eixos com letra intermediários (%s) ficam sem pilar: o lançamento é de vão livre entre %s e %s."
                      % (", ".join(l["nome"] for l in letras[1:-1]), letras[0]["nome"], letras[-1]["nome"]))
    if max(esp) - min(esp) > 1.0:
        avisos.append("Espaçamentos diferentes entre pórticos (%s m): o dimensionamento usa o maior, %s m, que governa "
                      "pórtico e terças." % (" · ".join(_fmt_m(v) for v in esp), _fmt_m(max(esp))))
    return {"xs": xs, "espacamentos": esp, "vao": vao, "comprimento": xs[-1], "esp_max": max(esp),
            "numeros": [n["nome"] for n in nums], "letras": [letras[0]["nome"], letras[-1]["nome"]],
            "origem_g": nums[0]["pos"], "origem_p": letras[0]["pos"], "avisos": avisos}


def dados_do_galpao(eixos: dict, par: Optional[dict] = None, nome: str = "Galpão"):
    """`DadosGalpao` do lançamento: vão e comprimento pelos eixos, o resto pelos parâmetros."""
    from nucleo.modelo_galpao import DadosGalpao
    p = dict(PADRAO)
    p.update({k: v for k, v in (par or {}).items() if v is not None and v != ""})
    geo = geometria_dos_eixos(eixos)
    campos = {f.name for f in fields(DadosGalpao)}
    trelicado = str(p.get("sistema", "")).lower().startswith("tre")
    d = {k: v for k, v in p.items() if k in campos}
    d.update(nome=nome or "Galpão", vao=round(geo["vao"] / 1000.0, 4), comprimento=round(geo["comprimento"] / 1000.0, 4),
             espacamento_porticos=round(geo["esp_max"] / 1000.0, 4),
             tipo_portico="treliçado (tesoura)" if trelicado else "alma cheia")
    for k in ("pe_direito", "inclinacao", "espacamento_tercas", "v0", "sobrecarga_cobertura", "carga_extra", "altura_tesoura"):
        if k in d:
            d[k] = float(str(d[k]).replace(",", "."))
    if "linhas_correntes" in d:
        d["linhas_correntes"] = int(d["linhas_correntes"])
    br = p.get("base_rotulada")
    if br is None or br == "":
        # a tesoura apoiada sobre pilar de base rotulada é um mecanismo no plano do pórtico
        br = not (trelicado and str(p.get("ligacao_tesoura", "")).lower().startswith("apoi"))
    elif isinstance(br, str):
        br = br.lower() in ("1", "true", "sim", "rotulada")
    d["base_rotulada"] = bool(br)
    p["base_rotulada"] = bool(br)
    if not trelicado:
        d.pop("ligacao_tesoura", None)
    dg = DadosGalpao(**d)
    if trelicado and str(dg.ligacao_tesoura).lower().startswith("r"):
        geo["avisos"].append("Ligação rígida da tesoura no pilar: o dimensionamento do pórtico (memorial do lançamento) "
                             "considera o pórtico inteiro; o Calcular estrutura do modelo 3D analisa a tesoura isolada, "
                             "apoiada no topo dos pilares, e tende a acusar flexão no banzo superior da ponta.")
    return dg, geo, p


def _transformar(doc, g: Sequence[float], p: Sequence[float], o: Tuple[float, float, float]):
    """Leva o modelo do galpão (X ao longo, Y no vão, Z para cima, pórtico 1 em x = 0,
    fila A em y = 0) para as coordenadas da planta: X → g, Y → p, origem no cruzamento
    do primeiro número com a primeira letra. É uma rotação em torno de z (mais translação):
    a rotação das barras em torno do próprio eixo continua valendo."""
    from nucleo3d.modelo import Barra, Chapa, Solido

    def P(q):
        return (round(o[0] + g[0] * q[0] + p[0] * q[1], 3), round(o[1] + g[1] * q[0] + p[1] * q[1], 3),
                round(o[2] + q[2], 3))

    def V(v):
        return (g[0] * v[0] + p[0] * v[1], g[1] * v[0] + p[1] * v[1], v[2])
    for e in doc.entidades.values():
        if isinstance(e, Barra):
            e.inicio, e.fim = P(e.inicio), P(e.fim)
        elif isinstance(e, Chapa):
            e.origem, e.eixo_x, e.eixo_y = P(e.origem), V(e.eixo_x), V(e.eixo_y)
        elif isinstance(e, Solido):
            e.vertices = [P(v) for v in e.vertices]


def _assinatura_chapa(ch) -> tuple:
    cont = tuple((round(x), round(y)) for x, y in ch.contorno)
    furos = tuple(sorted((round(f.get("x", 0)), round(f.get("y", 0)), round(float(f.get("diametro", 0)), 1))
                         for f in (ch.furos or [])))
    return ("chapa", round(float(ch.espessura), 2), cont, furos)


def marcar_modelo(doc) -> dict:
    """Marcas de posição (P1, P2…) e de conjunto (M1, M2…) em todas as peças de aço,
    como o IFC do TecnoMETAL traz: peças iguais têm a mesma posição; conjuntos iguais, a
    mesma marca de conjunto. Conjuntos soldados: a tesoura inteira de cada pórtico; o
    pilar com a placa de base; a viga de alma cheia com as mísulas e as chapas de topo.
    As demais peças (terças, longarinas, correntes, contraventos) são o conjunto delas."""
    from nucleo3d.modelo import Barra, Chapa
    barras = [b for b in doc.entidades.values() if isinstance(b, Barra)]
    chapas = [c for c in doc.entidades.values() if isinstance(c, Chapa)]
    for b in barras:
        el = str((b.atributos or {}).get("elemento") or "")
        if b.papel == "barra" and (el.startswith("Corrente") or el.startswith("Tirante de cumeeira")):
            b.papel = "corrente"
        # o travamento do banzo inferior não é contravento: é o que o cálculo do modelo lê
        # como ponto de contenção lateral do banzo (o contravento ele deixa de fora de propósito)
        if el.startswith("Travamento do banzo inferior"):
            b.papel = "travamento"

    def assin(e) -> tuple:
        if isinstance(e, Barra):
            L = math.dist(e.inicio, e.fim)
            return ("barra", e.perfil, e.papel, round(L))
        return _assinatura_chapa(e)
    # posições
    grupos: Dict[tuple, list] = collections.defaultdict(list)
    for e in barras + chapas:
        grupos[assin(e)].append(e)

    def ordem_pos(kv):
        chave, lista = kv
        return (-len(lista), -(chave[3] if chave[0] == "barra" else 0), str(chave))
    posicao_de = {}
    for i, (chave, lista) in enumerate(sorted(grupos.items(), key=ordem_pos), start=1):
        for e in lista:
            posicao_de[e.id] = "P%d" % i
    # instâncias dos conjuntos soldados
    inst: Dict[tuple, list] = collections.defaultdict(list)
    for e in barras + chapas:
        a = e.atributos or {}
        k = a.get("portico")
        if isinstance(e, Barra) and e.papel in ("banzo", "diagonal", "montante"):
            inst[("tesoura", k)].append(e)
        elif isinstance(e, Barra) and e.papel == "pilar":
            inst[("pilar", k, a.get("lado"))].append(e)
        elif isinstance(e, Chapa) and a.get("marca") == "CH3":                   # placa de base
            inst[("pilar", k, a.get("lado"))].append(e)
        elif isinstance(e, Barra) and e.papel == "viga":
            inst[("viga", k, a.get("agua"))].append(e)
        elif isinstance(e, Chapa) and a.get("marca") in ("M1", "M2", "CH2"):     # mísula e chapa de cumeeira
            inst[("viga", k, a.get("agua"))].append(e)
        elif isinstance(e, Chapa) and a.get("marca") == "CH1":                   # chapa de topo do joelho
            inst[("viga", k, 1 if a.get("lado") == "esquerdo" else 2)].append(e)
    no_conjunto = {e.id for lista in inst.values() for e in lista}
    conj_por_assin: Dict[tuple, str] = {}
    conjunto_de: Dict[str, str] = {}

    def marca_conj(chave) -> str:
        if chave not in conj_por_assin:
            conj_por_assin[chave] = "M%d" % (len(conj_por_assin) + 1)
        return conj_por_assin[chave]
    ordem_tipo = {"tesoura": 0, "viga": 1, "pilar": 2}
    for chave, lista in sorted(inst.items(), key=lambda kv: (ordem_tipo.get(kv[0][0], 9), str(kv[0][1:]))):
        # a instância é igual a outra quando tem as mesmas posições, na mesma quantidade
        comp = (chave[0],) + tuple(sorted(collections.Counter(posicao_de[e.id] for e in lista).items()))
        m = marca_conj(comp)
        for e in lista:
            conjunto_de[e.id] = m
    soltas = sorted({posicao_de[e.id] for e in barras + chapas if e.id not in no_conjunto},
                    key=lambda s: int(s[1:]))
    for pos in soltas:
        marca_conj(("solta", pos))
    for e in barras + chapas:
        if e.id not in conjunto_de:
            conjunto_de[e.id] = conj_por_assin[("solta", posicao_de[e.id])]
    for e in barras + chapas:
        a = dict(e.atributos or {})
        perfil = e.perfil if isinstance(e, Barra) else "CH %s" % ("%g" % round(float(e.espessura), 2)).replace(".", ",")
        a["marcas"] = {"posicao": posicao_de[e.id], "conjunto": conjunto_de[e.id], "perfil": perfil}
        a["tipo_ifc"] = e.tipo_ifc()
        e.atributos = a
    return {"posicoes": len(grupos), "conjuntos": len(conj_por_assin),
            "tesouras": len({conjunto_de[e.id] for lista in inst.values() for e in lista
                             if isinstance(e, Barra) and e.papel == "banzo"})}


def _construtor_do_lancamento():
    """O construtor do galpão com a terça sentada no nó da tesoura.

    O galpão desenha as terças a 200 mm do beiral e 250 mm da cumeeira, no passo alvo,
    mas calcula a tesoura com a carga nos nós. No modelo lançado a terça vai para o nó do
    banzo superior (é assim que a treliça trabalha: carga no nó, banzo sem flexão entre
    nós) e o centro dela fica meia altura do banzo mais meia altura da terça acima do eixo
    do banzo. No pórtico de alma cheia vale a regra do galpão."""
    from nucleo3d import de_projeto
    from saida import desenhos as dsn

    class _Construtor(de_projeto._Construtor):
        def _banzo_superior(self):
            from nucleo.galpao import NOME_DA_BARRA
            el = self._elemento(NOME_DA_BARRA["banzo superior"])
            return dsn._perfil(el.perfil) if el and el.perfil else self.viga

        def _ys_tercas(self):
            if not self.dg.eh_trelicado:
                return super()._ys_tercas()
            t = dsn._tesoura_do_projeto(self.fonte, self.dg)
            ys = sorted({round(n.x * 10.0, 1) for n in t.nos if n.banzo == "superior" and n.x * 10.0 <= self.V / 2 + 1.0})
            if len(ys) < 2:
                return super()._ys_tercas()
            return ys, max(b - a for a, b in zip(ys, ys[1:]))

        def _centro_terca(self, x, y):
            if not self.dg.eh_trelicado:
                return super()._centro_terca(x, y)
            off = self._banzo_superior().d / 2 + self.terca.d / 2
            n = self._normal_agua(y if abs(y - self.V / 2) > 1.0 else self.V / 2 - 1.0)
            return (x, y + n[1] * off, self._z_agua(y) + n[2] * off)
    return _Construtor


def _limpar_duplicadas(doc, V: float):
    """A terça da cumeeira sai das duas águas (a mesma barra duas vezes) e, com ela, o
    tirante de cumeeira vira um toco ao longo dela: fica uma de cada e sai o toco."""
    from nucleo3d.modelo import Barra
    vistas = set()
    for e in list(doc.entidades.values()):
        if not isinstance(e, Barra):
            continue
        a = tuple(round(c) for c in e.inicio)
        b = tuple(round(c) for c in e.fim)
        chave = (e.perfil, min(a, b), max(a, b))
        el = str((e.atributos or {}).get("elemento") or "")
        toco = el.startswith("Tirante de cumeeira") and abs(e.inicio[1] - V / 2) < 150.0 and abs(e.fim[1] - V / 2) < 150.0
        if chave in vistas or toco:
            doc.remover(e.id)
            continue
        vistas.add(chave)


def lancar(eixos: dict, parametros: Optional[dict] = None, nome: str = "Galpão", avisar=None) -> dict:
    """Lança a estrutura nos eixos. Devolve {doc, projeto (ProjetoGalpao ou None), dados
    (DadosGalpao), geometria, resumo, avisos}. Com `dimensionar`, o motor do galpão
    escolhe os perfis antes (pórtico, terças, longarinas, contraventos, base); sem ele, os
    perfis padrão por faixa de vão dos desenhos."""
    from nucleo3d import de_projeto
    from nucleo3d.eixos import de_dict
    avisar = avisar or (lambda *a: None)
    ex = de_dict(eixos) if "eixo_g" in (eixos or {}) else None
    if ex is None:
        raise ErroDeDados("eixos inválidos: grave os eixos da planta de lançamento antes de lançar.")
    dg, geo, par = dados_do_galpao(ex, parametros, nome)
    avisos = list(geo["avisos"])
    projeto = None
    if par.get("dimensionar", True):
        from nucleo import galpao
        avisar("dimensionando o pórtico, as terças e os contraventos…")
        projeto = galpao.dimensionar(dg)
        avisos += [a for a in (projeto.avisos or []) if isinstance(a, str)]
    avisar("montando o modelo 3D nos eixos…")
    c = _construtor_do_lancamento()(projeto if projeto is not None else dg, com_fechamento=bool(par.get("fechamento")),
                                    com_pedestais=False)
    c.xs = list(geo["xs"])
    c.C = geo["comprimento"]
    c.vaos_x = de_projeto._vaos_padrao(len(c.xs) - 1)
    c.vaos_cobertura = c.vaos_vertical = c.vaos_x
    doc = c.montar()
    _limpar_duplicadas(doc, c.V)
    doc.nome = nome or doc.nome
    g, p = ex["eixo_g"], ex["perp_g"]
    o = (g[0] * geo["origem_g"] + p[0] * geo["origem_p"], g[1] * geo["origem_g"] + p[1] * geo["origem_p"],
         float(ex.get("z_base") or 0.0))
    _transformar(doc, g, p, o)
    marcas = marcar_modelo(doc)
    from nucleo3d.de_projeto import pesos
    peso = pesos(doc)
    elementos = []
    if projeto is not None:
        for el in projeto.elementos:
            r = getattr(el, "resultado", None)
            elementos.append({"nome": el.nome, "perfil": el.perfil, "ok": bool(el.ok),
                              "aproveitamento": round(float(r.razao), 3) if r is not None else None,
                              "governa": (r.critica.titulo if r is not None and r.critica else "")})
    resumo = {"sistema": dg.tipo_portico, "vao_m": dg.vao, "comprimento_m": dg.comprimento,
              "porticos": len(geo["xs"]), "espacamentos_m": [round(v / 1000.0, 3) for v in geo["espacamentos"]],
              "eixos": {"numeros": geo["numeros"], "letras": geo["letras"]},
              "pe_direito_m": dg.pe_direito, "inclinacao_pct": dg.inclinacao,
              "barras": len(doc.barras), "chapas": len(doc.chapas), "posicoes": marcas["posicoes"],
              "conjuntos": marcas["conjuntos"], "peso_kg": peso.get("total_aco_kg", 0.0),
              "dimensionado": projeto is not None, "ok": all(e["ok"] for e in elementos) if elementos else None,
              "elementos": elementos}
    doc.metadados["lancamento"] = {"eixos": {k: ex[k] for k in ("eixo_g", "perp_g", "numeros", "letras", "z_base")},
                                   "parametros": {k: par[k] for k in PADRAO if k in par},
                                   "resumo": {k: v for k, v in resumo.items() if k != "elementos"}}
    return {"doc": doc, "projeto": projeto, "dados": dg, "geometria": geo, "resumo": resumo, "avisos": avisos,
            "parametros": {k: par[k] for k in PADRAO if k in par}}
