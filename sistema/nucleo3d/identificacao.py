# -*- coding: utf-8 -*-
"""Identificação para modelagem: o projeto recebido lido do Original, etapa por etapa, até o modelo 3D.

Pedido do usuário (20/10/2026, depois do Hangar Almayer — Projeto/OBRAS/Hangar-Almayer/Caminho-DXF-para-3D-Hangar-
Almayer-2026-10-20.pdf): "a primeira importação poderia ser somente a leitura, quando o projeto estiver dentro do sistema
vamos começar a parte da identificação para modelagem, e deixar esse projeto importado como original que não é mexido …
o sistema faz uma varredura no desenho e tenta identificar essa planta de locação, nessa o usuário pode fazer os ajustes,
corrigir os eixos e níveis … após isso vai para as tesouras … depois as terças … o usuário pede para montar o modelo 3D".
Escolhas dele: painel de etapas na Montagem; uma varredura só, que preenche todas as etapas como sugestão; o caminho
antigo (ler e já gerar o 3D) sai do menu.

Fase 1: o que a importação leu, para a tela mostrar antes de qualquer modelagem — as folhas do projeto e a unidade em
que as cotas estão escritas (no Hangar, cotas em centímetro sobre o desenho em milímetro: a leitura antiga tomou "495"
como 495 mm e as vistas saíram 10 vezes menores).

Fase 2 (`varrer`): a varredura única do Original, que preenche todas as etapas como sugestão — a planta de locação (a
folha, os eixos nas duas direções e os níveis escritos), as tesouras (os tipos, a melhor vista de cada um e os eixos em
que a locação as põe) e as folhas de terças e contraventos. Nada é gravado aqui: o painel da Montagem mostra e o
usuário confirma etapa por etapa. O desenho é separado por FOLHA (a moldura com o carimbo "FOLHA 12/36 - …"), não pelas
"vistas" do reconhecimento antigo, que no Hangar juntavam e partiam as folhas de fabricação.
"""
from __future__ import annotations

import collections
import math
import re
from typing import Dict, List, Optional

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Arco, Circulo, Cota, Desenho, Linha, Polilinha, Texto

_FOLHA = re.compile(r"FOLHA\s*(\d+)\s*/\s*(\d+)", re.I)
_NUMERO = re.compile(r"^\s*[\d.,]+\s*$")
#: a unidade das cotas pela razão medida no desenho (mm) ÷ número escrito
UNIDADES = ((1.0, "mm", "milímetro"), (10.0, "cm", "centímetro"), (1000.0, "m", "metro"))


def _valor(texto: str) -> Optional[float]:
    t = str(texto or "").strip()
    t = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", t)                 # códigos de formatação do MTEXT
    if not _NUMERO.match(t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def _medida(c: Cota) -> float:
    dx, dy = c.p2[0] - c.p1[0], c.p2[1] - c.p1[1]
    if c.modo == "h":
        return abs(dx)
    if c.modo == "v":
        return abs(dy)
    return math.hypot(dx, dy)


def unidade_das_cotas(des: Desenho) -> Optional[dict]:
    """Em que unidade os números das cotas estão escritos, pela medida no desenho (em mm reais) ÷ o número: a mais
    votada entre mm, cm e m. A cota sem texto escrito (o CAD mostra a medida) não conta. None sem cota legível."""
    votos: Dict[str, int] = collections.Counter()
    exemplo: Dict[str, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Cota) or not e.texto:
            continue
        v = _valor(e.texto)
        L = _medida(e)
        if not v or L < 1.0:
            continue
        r = math.log10(L / v)
        fator, sigla, _nome = min(UNIDADES, key=lambda u: abs(math.log10(u[0]) - r))
        if abs(math.log10(fator) - r) > 0.05:                  # mais de 12 % fora: escala própria (detalhe ampliado)
            continue
        votos[sigla] += 1
        if sigla not in exemplo or v > exemplo[sigla]["texto_num"]:
            exemplo[sigla] = {"texto": str(e.texto).strip(), "texto_num": v, "mede_mm": round(L, 1)}
    if not votos:
        return None
    sigla, n = votos.most_common(1)[0]
    fator, _s, nome = next(u for u in UNIDADES if u[1] == sigla)
    ex = dict(exemplo[sigla]); ex.pop("texto_num", None)
    return {"sigla": sigla, "nome": nome, "fator": fator, "votos": dict(votos), "amostras": sum(votos.values()),
            "exemplo": ex}


def folhas(des: Desenho) -> dict:
    """As folhas do projeto pelos carimbos ("FOLHA 12/36 - PLANTA DE LOCAÇÃO"): o número, o título e quantas são."""
    achadas: Dict[int, str] = {}
    total = 0
    for e in des.entidades.values():
        if not isinstance(e, Texto):
            continue
        m = _FOLHA.search(e.texto or "")
        if not m:
            continue
        n, t = int(m.group(1)), int(m.group(2))
        total = max(total, t)
        titulo = re.sub(r"\s+", " ", (e.texto or "")[m.end():]).strip(" -–|")
        if titulo and len(titulo) > len(achadas.get(n, "")):
            achadas[n] = titulo
        else:
            achadas.setdefault(n, titulo)
    return {"total": total, "achadas": len(achadas),
            "lista": [{"folha": n, "titulo": achadas[n]} for n in sorted(achadas)]}


def resumo_da_leitura(des: Desenho) -> dict:
    """O que a importação leu, para a tela "O que o programa leu" (antes de qualquer modelagem)."""
    por_tipo = collections.Counter(e.tipo for e in des.entidades.values())
    return {"folhas": folhas(des), "cotas": unidade_das_cotas(des),
            "textos": por_tipo.get("texto", 0), "n_cotas": por_tipo.get("cota", 0)}


# ---------------------------------------------------------------------------------------------------- Fase 2: varredura

_TIPO_TESOURA = re.compile(r"\b(T\d{1,2}(?:-[A-Z])?)\b")
_NIVEL = re.compile(r"^\s*(?:N[ÍI]V(?:EL|\.)?|EL\.?|COTA|TOPO[^+−±\-\d]*|BASE[^+−±\-\d]*|APOIO[^+−±\-\d]*)?\s*"
                    r"([+−±\-])\s?(\d{1,3}[,.]\d{2,3})\s*(?:m)?\s*$", re.I)
#: o que cada folha de tesoura mostra, na ordem de preferência para modelar (a vista geral é a tesoura montada)
_FOLHA_TESOURA = (("vista geral", re.compile(r"VISTA\s+GERAL|ELEVA[CÇ][AÃ]O", re.I)),
                  ("gabarito", re.compile(r"GABARITO|TRELI[CÇ]AMENTO", re.I)),
                  ("marcas", re.compile(r"MARCAS|COMPRIMENTOS?\s+DE\s+CORTE", re.I)),
                  ("mãos-francesas", re.compile(r"M[ÃA]OS?-?FRANCESAS?|POSI[CÇ][AÃ]O", re.I)))


def _dentro(e, caixa) -> bool:
    (x0, y0), (x1, y1) = caixa
    ps = e.pontos()
    return bool(ps) and all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in ps)


def _retangulo(e) -> Optional[list]:
    """A caixa da polilinha que é um retângulo alinhado (a moldura da folha), ou None."""
    if not isinstance(e, Polilinha):
        return None
    vs = list(e.vertices)
    if len(vs) == 5 and math.dist(vs[0], vs[-1]) < 1e-6:
        vs = vs[:4]
    elif not e.fechada:
        return None
    if len(vs) != 4:
        return None
    xs, ys = sorted({round(v[0], 3) for v in vs}), sorted({round(v[1], 3) for v in vs})
    if len(xs) != 2 or len(ys) != 2:
        return None
    return [[xs[0], ys[0]], [xs[1], ys[1]]]


def folhas_com_moldura(des: Desenho) -> List[dict]:
    """Cada carimbo "FOLHA n/N - TÍTULO" com a menor moldura retangular que o contém: {folha, total, titulo, caixa}.
    A folha sem moldura achada fica sem caixa (o painel mostra, mas não varre dentro dela)."""
    rets = [r for r in (_retangulo(e) for e in des.entidades.values()) if r]
    saida: Dict[int, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Texto):
            continue
        m = _FOLHA.search(e.texto or "")
        if not m:
            continue
        n, total = int(m.group(1)), int(m.group(2))
        titulo = re.sub(r"\s+", " ", (e.texto or "")[m.end():]).strip(" -–|")
        x, y = e.posicao
        dentro = [r for r in rets if r[0][0] <= x <= r[1][0] and r[0][1] <= y <= r[1][1]
                  and (r[1][0] - r[0][0]) * (r[1][1] - r[0][1]) > 1e6]
        caixa = min(dentro, key=lambda r: (r[1][0] - r[0][0]) * (r[1][1] - r[0][1])) if dentro else None
        if n not in saida or (caixa and not saida[n]["caixa"]):
            saida[n] = {"folha": n, "total": total, "titulo": titulo, "caixa": caixa}
    return [saida[k] for k in sorted(saida)]


def _linhas_de_eixo(des: Desenho, caixa) -> List[dict]:
    from nucleo3d.lancamento import _camada_de_eixo, _juntar_tracejados
    (x0, y0), (x1, y1) = caixa
    minimo = 0.15 * max(x1 - x0, y1 - y0)
    pedacos = []
    for e in des.entidades.values():
        if not _camada_de_eixo(e.camada) or not _dentro(e, caixa):
            continue
        if isinstance(e, Linha):
            a, b = e.a, e.b
        elif isinstance(e, Polilinha) and len(e.vertices) == 2:
            a, b = e.vertices
        else:
            continue
        L = math.dist(a, b)
        if L > 1e-6:
            pedacos.append({"a": tuple(a), "b": tuple(b), "L": L, "ang": math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi, "nome": ""})
    return [l for l in _juntar_tracejados(pedacos) if l["L"] >= minimo]


def _nome_do_balao(l: dict, baloes: List[tuple]) -> str:
    """O nome escrito DENTRO do balão que está na continuação de uma das pontas da linha (o texto só perto da ponta
    não vale: no Hangar o "A" do balão vizinho batizava a última linha das tesouras)."""
    (ax, ay), (bx, by) = l["a"], l["b"]
    L = math.hypot(bx - ax, by - ay) or 1.0
    u = ((bx - ax) / L, (by - ay) / L)
    for (cx, cy), r, nome in baloes:
        t = (cx - ax) * u[0] + (cy - ay) * u[1]
        d = abs((cx - ax) * u[1] - (cy - ay) * u[0])
        if d <= 1.2 * r and (-4 * r <= t <= 0.5 * r or L - 0.5 * r <= t <= L + 4 * r):
            return nome
    return ""


def eixos_da_area(des: Desenho, caixa) -> dict:
    """Os eixos da planta de locação dentro de `caixa`, nas duas direções, no formato da Implantação ({eixo_g, numeros,
    letras}: o numerado é a linha das tesouras, g perpendicular a ele). A família sem balão no projeto é numerada pelo
    programa em ordem (`auto`: confira) — o Hangar tem só A e B com balão e as 6 linhas das tesouras sem nome."""
    avisos: List[str] = []
    linhas = _linhas_de_eixo(des, caixa)
    if len(linhas) < 2:
        return {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [], "letras": [],
                "avisos": ["a planta de locação não tem linhas de eixo (camada EIXO): dê os vãos na Implantação."]}
    textos = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, caixa) and 0 < len((e.texto or "").strip()) <= 4]
    baloes = []
    for c in des.entidades.values():
        if isinstance(c, Circulo) and _dentro(c, caixa):
            dentro = [t for t in textos if math.dist(t.posicao, c.centro) <= 1.2 * c.raio]
            if dentro:
                baloes.append((tuple(c.centro), c.raio, re.sub(r"^0+(?=\d)", "", dentro[0].texto.strip().upper())))
    for l in linhas:
        l["nome"] = _nome_do_balao(l, baloes)

    def dif(a1, a2):
        d = abs(a1 - a2) % math.pi
        return min(d, math.pi - d)
    familias: List[List[dict]] = []
    for l in sorted(linhas, key=lambda l: -l["L"]):
        for f in familias:
            if dif(f[0]["ang"], l["ang"]) < math.radians(2.0):
                f.append(l)
                break
        else:
            familias.append([l])
    familias.sort(key=lambda f: -len(f))
    f1 = familias[0]
    outras = [f for f in familias[1:] if abs(dif(f[0]["ang"], f1[0]["ang"]) - math.pi / 2) < math.radians(1.5)]
    f2 = outras[0] if outras else []
    if len(familias) > 1 + (1 if f2 else 0):
        avisos.append("há linhas de eixo fora das duas direções da malha: ficaram de fora.")

    def tipo(f):
        nomes = [l["nome"] for l in f if l["nome"]]
        n = sum(1 for x in nomes if re.match(r"^\d", x))
        return "numeros" if nomes and n > len(nomes) - n else ("letras" if nomes else "")
    t1, t2 = tipo(f1), (tipo(f2) if f2 else "")
    if t1 == "letras" or t2 == "numeros":
        fn, fl = f2, f1
    elif t1 == "numeros" or t2 == "letras":
        fn, fl = f1, f2
    else:
        fn, fl = (f1, f2) if len(f1) >= len(f2) else (f2, f1)      # sem nome nenhum: a família com mais linhas é a das tesouras
    if not fn or not fl:
        avisos.append("os eixos estão numa direção só: faltam os da outra direção — desenhe-os ou dê os vãos.")
    an = (fn or fl)[0]["ang"]
    if not fn:
        an += math.pi / 2                                           # só a família com letra: a das tesouras é a atravessada
    g = (-math.sin(an), math.cos(an))
    if g[0] < -1e-9 or (abs(g[0]) <= 1e-9 and g[1] < 0):
        g = (-g[0], -g[1])
    p = (-g[1], g[0])

    def posicoes(f, eixo):
        vistos: List[dict] = []
        for l in f:
            m = ((l["a"][0] + l["b"][0]) / 2, (l["a"][1] + l["b"][1]) / 2)
            pos = m[0] * eixo[0] + m[1] * eixo[1]
            if any(abs(pos - v["pos"]) < 50.0 for v in vistos):         # a mesma linha duas vezes
                continue
            vistos.append({"pos": round(pos, 1), "nome": l["nome"], "a": [round(v, 1) for v in l["a"]], "b": [round(v, 1) for v in l["b"]]})
        return sorted(vistos, key=lambda v: v["pos"])
    nums = posicoes(fn, g) if fn else []
    lets = posicoes(fl, p) if fl else []
    for lista, gerar, rotulo in ((nums, lambda i: str(i + 1), "numerados"), (lets, lambda i: chr(ord("A") + i), "com letra")):
        if lista and not any(v["nome"] for v in lista):
            for i, v in enumerate(lista):
                v["nome"], v["auto"] = gerar(i), True
            avisos.append("os eixos %s (%d) não têm balão no projeto: o programa os chamou de %s, em ordem — confira."
                          % (rotulo, len(lista), ", ".join(v["nome"] for v in lista)))
        elif any(not v["nome"] for v in lista):
            sem = [v for v in lista if not v["nome"]]
            avisos.append("%d linha(s) de eixo %s sem balão ficaram de fora." % (len(sem), rotulo))
            lista[:] = [v for v in lista if v["nome"]]
    return {"eixo_g": [round(g[0], 6), round(g[1], 6)], "perp_g": [round(p[0], 6), round(p[1], 6)],
            "numeros": nums, "letras": lets, "avisos": avisos}


def niveis_escritos(des: Desenho, caixa=None) -> List[dict]:
    """Os níveis escritos no projeto ("+5,00", "EL. +4,20", "TOPO DO PILAR +7,50"): {cota (mm), texto}, um por valor."""
    achados: Dict[int, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Texto) or (caixa and not _dentro(e, caixa)):
            continue
        m = _NIVEL.match(e.texto or "")
        if not m:
            continue
        v = float(m.group(2).replace(",", ".")) * 1000.0
        if m.group(1) in "−-":
            v = -v
        achados.setdefault(int(round(v / 10.0)) * 10, {"cota": round(v), "texto": e.texto.strip()})
    return [achados[k] for k in sorted(achados)]


def _o_que_mostra(titulo: str) -> str:
    for nome, rx in _FOLHA_TESOURA:
        if rx.search(titulo):
            return nome
    return ""


def tesouras(des: Desenho, folhas_: List[dict], locacao: Optional[dict]) -> List[dict]:
    """Os tipos de tesoura pelos títulos das folhas e pelas marcas da locação; para cada tipo, as folhas em que aparece
    (a preferida para modelar é a vista geral — gabarito, marcas e mãos-francesas são referência) e os eixos em que a
    locação o põe (o texto "T2" junto da linha do eixo numerado)."""
    tipos: Dict[str, dict] = {}

    def tipo(t):
        return tipos.setdefault(t, {"tipo": t, "folhas": [], "eixos": []})
    ordem = [n for n, _ in _FOLHA_TESOURA]
    for f in folhas_:
        achados = _TIPO_TESOURA.findall(f["titulo"])
        if not achados:
            continue
        mostra = _o_que_mostra(f["titulo"])
        for t in dict.fromkeys(achados):
            tipo(t)["folhas"].append({"folha": f["folha"], "titulo": f["titulo"], "caixa": f["caixa"], "mostra": mostra})
    nums = ((locacao or {}).get("eixos") or {}).get("numeros") or []
    if locacao and locacao.get("caixa") and nums:
        g = locacao["eixos"]["eixo_g"]
        for e in des.entidades.values():
            if not isinstance(e, Texto) or not _dentro(e, locacao["caixa"]):
                continue
            m = re.match(r"^\s*(T\d{1,2}(?:-[A-Z])?)\b", e.texto or "")
            if not m:
                continue
            pos = e.posicao[0] * g[0] + e.posicao[1] * g[1]
            perto = min(nums, key=lambda v: abs(v["pos"] - pos))
            if abs(perto["pos"] - pos) <= 1000.0:
                lst = tipo(m.group(1))["eixos"]
                if perto["nome"] not in lst:
                    lst.append(perto["nome"])
    nomes = [v["nome"] for v in nums]
    for t in tipos.values():
        t["folhas"].sort(key=lambda f: (ordem.index(f["mostra"]) if f["mostra"] in ordem else len(ordem), f["folha"]))
        t["vista"] = t["folhas"][0] if t["folhas"] else None
        t["eixos"].sort(key=lambda n: nomes.index(n) if n in nomes else 99)
    return sorted(tipos.values(), key=lambda t: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", t["tipo"])])


def _locacao(des: Desenho, folhas_: List[dict]) -> dict:
    """A folha da planta de locação: o título com LOCAÇÃO (a PLANTA DE LOCAÇÃO antes da locação dos chumbadores); sem
    título, a folha com mais linhas de eixo; sem folhas, a malha de eixos que for uma planta só; senão {caixa: None,
    marcar: True} — o painel pede para o usuário marcar a planta no Original."""
    def nota(f):
        t = f["titulo"].upper()
        return (3 if re.search(r"LOCA[CÇ][AÃ]O", t) else 0) + (2 if "PLANTA" in t else 0) - (2 if "CHUMBADOR" in t else 0)
    com_caixa = [f for f in folhas_ if f["caixa"]]
    melhor = max(com_caixa, key=nota, default=None)
    if melhor is None or nota(melhor) <= 0:
        cands = [(len(_linhas_de_eixo(des, f["caixa"])), f) for f in com_caixa]
        cands = [c for c in cands if c[0] >= 2]
        melhor = max(cands, key=lambda c: c[0])[1] if cands else None
    if melhor is None:
        melhor = _malha_sem_folha(des)
        if melhor is not None:
            # a malha só vale se for UMA planta: nome de eixo repetido é sinal de duas plantas emendadas (o Posto, 20/10:
            # locação, nível 6,00, terças e caixa d'água ligadas pelas linhas compridas)
            ex = eixos_da_area(des, melhor["caixa"])
            nomes = [v["nome"] for v in ex["numeros"]] + [v["nome"] for v in ex["letras"]]
            if len(nomes) != len(set(nomes)) or not ex["numeros"] or not ex["letras"]:
                melhor = None
    if melhor is None:
        return {"folha": None, "titulo": "", "caixa": None, "marcar": True}
    return {"folha": melhor["folha"], "titulo": melhor["titulo"], "caixa": melhor["caixa"]}


def _malha_sem_folha(des: Desenho) -> Optional[dict]:
    """O projeto sem carimbo de folha (a Portaria, o Posto: as vistas soltas num desenho só): a planta de locação é o
    grupo de linhas de eixo que se cruzam — a malha —, o de mais balões (e perto de um título com LOCAÇÃO)."""
    from nucleo3d.lancamento import _cruzam
    linhas = [l for l in _linhas_de_eixo_todas(des) if l["L"] >= 1500.0]
    if len(linhas) < 2:
        return None
    pai = list(range(len(linhas)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(len(linhas)):
        for j in range(i + 1, len(linhas)):
            if _cruzam(linhas[i], linhas[j]):
                pai[raiz(i)] = raiz(j)
    grupos: Dict[int, List[dict]] = collections.defaultdict(list)
    for i, l in enumerate(linhas):
        grupos[raiz(i)].append(l)
    circulos = [c for c in des.entidades.values() if isinstance(c, Circulo)]
    titulos = [t for t in des.entidades.values() if isinstance(t, Texto) and re.search(r"LOCA[CÇ][AÃ]O", t.texto or "", re.I)]
    melhor, nota_m = None, None
    for g in grupos.values():
        if len(g) < 3:
            continue
        xs = [p[0] for l in g for p in (l["a"], l["b"])]
        ys = [p[1] for l in g for p in (l["a"], l["b"])]
        folga = 0.12 * max(max(xs) - min(xs), max(ys) - min(ys))
        cx = [[min(xs) - folga, min(ys) - folga], [max(xs) + folga, max(ys) + folga]]
        n_bal = sum(1 for c in circulos if cx[0][0] <= c.centro[0] <= cx[1][0] and cx[0][1] <= c.centro[1] <= cx[1][1])
        perto = any(cx[0][0] - folga <= t.posicao[0] <= cx[1][0] + folga and cx[0][1] - 2 * folga <= t.posicao[1] <= cx[1][1] + 2 * folga
                    for t in titulos)
        nota = (1 if perto else 0, min(n_bal, len(g)), len(g))
        if nota_m is None or nota > nota_m:
            melhor, nota_m = {"folha": None, "titulo": "a malha de eixos do desenho" + (" (PLANTA DE LOCAÇÃO)" if perto else ""),
                              "caixa": [[round(v, 1) for v in cx[0]], [round(v, 1) for v in cx[1]]]}, nota
    return melhor


def _linhas_de_eixo_todas(des: Desenho) -> List[dict]:
    """Todas as linhas das camadas de eixo do desenho, com os tracejados juntos (sem o mínimo de comprimento da área)."""
    from nucleo3d.lancamento import _camada_de_eixo, _juntar_tracejados
    pedacos = []
    for e in des.entidades.values():
        if not _camada_de_eixo(e.camada):
            continue
        if isinstance(e, Linha):
            a, b = e.a, e.b
        elif isinstance(e, Polilinha) and len(e.vertices) == 2:
            a, b = e.vertices
        else:
            continue
        L = math.dist(a, b)
        if L > 1e-6:
            pedacos.append({"a": tuple(a), "b": tuple(b), "L": L, "ang": math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi, "nome": ""})
    return _juntar_tracejados(pedacos)


def varrer(des: Desenho, avisar=None) -> dict:
    """A varredura única do Original: locação (folha, eixos, níveis), tesouras e as folhas das etapas seguintes."""
    def av(t):
        if avisar:
            avisar(t)
    av("separando as folhas…")
    fs = folhas_com_moldura(des)
    av("procurando a planta de locação…")
    loc = _locacao(des, fs)
    if loc["caixa"]:
        loc["eixos"] = eixos_da_area(des, loc["caixa"])
    else:
        loc["eixos"] = {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [], "letras": [],
                        "avisos": ["não achei a planta de locação sozinho (o desenho não tem folhas com carimbo): marque-a no "
                                   "Original e os eixos dela são lidos."]}
    av("procurando os níveis…")
    loc["niveis"] = niveis_escritos(des)
    if not loc["niveis"]:
        loc["eixos"]["avisos"].append("o projeto não escreve níveis (+5,00…): informe a altura de apoio das tesouras.")
    av("procurando as tesouras…")
    ts = tesouras(des, fs, loc)

    def das(rx):
        return [f for f in fs if re.search(rx, f["titulo"], re.I)]
    return {"folhas": fs, "locacao": loc, "tesouras": ts,
            "tercas": das(r"TER[CÇ]AS"), "contraventos": das(r"CONTRAVENT|AGULHAMENT"),
            "outras": das(r"VIGA|PILAR|BEIRAL|CUMEEIRA")}


def eixos_marcados(des: Desenho, caixa) -> dict:
    """Os eixos da área que o usuário marcou no Original (o projeto sem folhas com carimbo, como o Posto): pela camada
    EIXO; sem ela, as linhas compridas com o nome no balão, em qualquer camada (o leitor do lançamento)."""
    ex = eixos_da_area(des, caixa)
    if ex["numeros"] and ex["letras"]:
        return ex
    from nucleo3d import lancamento
    sub = Desenho(nome="area", escala=des.escala)
    sub.camadas = des.camadas
    for e in des.entidades.values():
        if _dentro(e, caixa):
            sub.add(e)
    try:
        r = lancamento.eixos_do_desenho(sub, qualquer_camada=True)
    except Exception as erro:                                       # noqa: BLE001 — a mensagem do leitor vai para a tela
        ex["avisos"].append(str(erro))
        return ex
    return {"eixo_g": list(r.get("eixo_g") or [1.0, 0.0]), "perp_g": list(r.get("perp_g") or [0.0, 1.0]),
            "numeros": [{"nome": v["nome"], "pos": round(v["pos"], 1)} for v in r.get("numeros") or []],
            "letras": [{"nome": v["nome"], "pos": round(v["pos"], 1)} for v in r.get("letras") or []],
            "avisos": list(r.get("avisos") or [])}


# ---------------------------------------------------------------------------------------------------- Fase 3: tesouras

#: camadas que não são barra da tesoura (cotas, textos, telha, terças e suportes, chapas, marcas, a moldura, o concreto)
_NAO_BARRA = re.compile(r"cota|dim|texto|text|telha|lantern|ter[cç]a|hach|corrente|eixo|tracej|chapa|marca|folha|t[ií]tulo|"
                        r"concreto|suporte|longarina|parafuso|furo|solda|auxiliar|oculta|tabela|definir|legenda", re.I)


def _segmentos_de(e) -> List[tuple]:
    if isinstance(e, Linha):
        return [(tuple(e.a), tuple(e.b))]
    if isinstance(e, Polilinha):
        vs = [tuple(v) for v in e.vertices]
        segs = list(zip(vs, vs[1:]))
        if e.fechada and len(vs) > 2:
            segs.append((vs[-1], vs[0]))
        return segs
    ps = e.pontos() if hasattr(e, "pontos") else []
    return list(zip(ps, ps[1:]))


def _dist_seg(p, a, b) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _cruzam_seg(a, b, c, d) -> bool:
    def lado(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = lado(c, d, a), lado(c, d, b), lado(a, b, c), lado(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def tesoura_da_folha(des: Desenho, caixa, tol: float = 30.0) -> dict:
    """O desenho da tesoura na folha da vista geral: o maior grupo de barras ligadas (banzo, diagonal, montante — sem
    cotas, terças, chapas, telha, concreto) e os textos em volta dele (a legenda de perfis, que o "Tesoura…" lê). O ponto
    de referência é o meio de baixo do grupo: a tesoura é colada centrada entre os eixos com letra, no nível do apoio, sem
    esticar (seguir o projeto: o que não casar com o vão vira aviso). {entidades, caixa, ref, largura, altura, camadas}."""
    from dataclasses import asdict
    ents = [e for e in des.entidades.values() if _dentro(e, caixa) and not _NAO_BARRA.search(e.camada or "")
            and isinstance(e, (Linha, Polilinha, Arco))]
    if not ents:
        return {"entidades": [], "avisos": ["a folha não tem barras (banzo, diagonal, montante) nas camadas dela."]}
    segs = [(i, s) for i, e in enumerate(ents) for s in _segmentos_de(e)]
    cel = 500.0
    grade: Dict[tuple, List[int]] = collections.defaultdict(list)
    for k, (i, (a, b)) in enumerate(segs):
        for cx in range(int(math.floor((min(a[0], b[0]) - tol) / cel)), int(math.floor((max(a[0], b[0]) + tol) / cel)) + 1):
            for cy in range(int(math.floor((min(a[1], b[1]) - tol) / cel)), int(math.floor((max(a[1], b[1]) + tol) / cel)) + 1):
                grade[(cx, cy)].append(k)
    pai = list(range(len(ents)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for lst in grade.values():
        for x in range(len(lst)):
            i, (a, b) = segs[lst[x]]
            for y in range(x + 1, len(lst)):
                j, (c, d) = segs[lst[y]]
                if raiz(i) == raiz(j):
                    continue
                if (_cruzam_seg(a, b, c, d) or min(_dist_seg(a, c, d), _dist_seg(b, c, d), _dist_seg(c, a, b), _dist_seg(d, a, b)) <= tol):
                    pai[raiz(i)] = raiz(j)
    grupos: Dict[int, List[int]] = collections.defaultdict(list)
    for i in range(len(ents)):
        grupos[raiz(i)].append(i)

    def cx_de(ids):
        ps = [p for i in ids for p in ents[i].pontos()]
        return min(p[0] for p in ps), min(p[1] for p in ps), max(p[0] for p in ps), max(p[1] for p in ps)
    melhor = max(grupos.values(), key=lambda ids: (lambda c: (c[2] - c[0]) * max(1.0, c[3] - c[1]))(cx_de(ids)))
    x0, y0, x1, y1 = cx_de(melhor)
    folga = 0.08 * (x1 - x0)
    textos = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, caixa)
              and x0 - folga <= e.posicao[0] <= x1 + folga and y0 - folga <= e.posicao[1] <= y1 + folga]
    escolhidas = [ents[i] for i in melhor]
    camadas = collections.Counter(e.camada for e in escolhidas)
    fora = len(ents) - len(melhor)
    saida = _alma_nas_faces([asdict(e) for e in escolhidas])
    return {"entidades": saida + [asdict(e) for e in textos], "caixa": [[round(x0, 1), round(y0, 1)], [round(x1, 1), round(y1, 1)]],
            "ref": [round((x0 + x1) / 2, 1), round(y0, 1)], "largura": round(x1 - x0, 1), "altura": round(y1 - y0, 1),
            "camadas": dict(camadas), "barras": len(melhor),
            "avisos": (["%d linha(s) solta(s) da folha ficaram de fora (outros desenhos, a legenda)." % fora] if fora else [])}


def _dentro_poligono(p, poli) -> bool:
    x, y = p
    dentro = False
    for i in range(len(poli)):
        (x1, y1), (x2, y2) = poli[i], poli[(i + 1) % len(poli)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro


def _fora_dos_poligonos(a, b, polis, minimo: float = 20.0) -> List[tuple]:
    """Os pedaços do segmento a–b fora dos polígonos (o que atravessa o banzo desenhado em contorno sai)."""
    ts = [0.0, 1.0]
    r = (b[0] - a[0], b[1] - a[1])
    for poli in polis:
        for i in range(len(poli)):
            c, d = poli[i], poli[(i + 1) % len(poli)]
            s = (d[0] - c[0], d[1] - c[1])
            den = r[0] * s[1] - r[1] * s[0]
            if abs(den) < 1e-9:
                continue
            t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
            u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
            if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                ts.append(min(1.0, max(0.0, t)))
    ts = sorted(set(round(t, 9) for t in ts))
    pedacos = []
    for t0, t1 in zip(ts, ts[1:]):
        m = (a[0] + r[0] * (t0 + t1) / 2, a[1] + r[1] * (t0 + t1) / 2)
        if any(_dentro_poligono(m, p) for p in polis):
            continue
        P, Q = (a[0] + r[0] * t0, a[1] + r[1] * t0), (a[0] + r[0] * t1, a[1] + r[1] * t1)
        if math.dist(P, Q) >= minimo:
            pedacos.append((P, Q))
    return pedacos


def _alma_nas_faces(ents: List[dict]) -> List[dict]:
    """O banzo desenhado como contorno fechado (o retângulo do U127 no Hangar) com a alma em linha simples que o atravessa
    de face externa a face externa: a linha da alma é cortada nas faces dos banzos — como o detalhista desenha e como o
    leitor da tesoura (o do Posto) espera. No Hangar, a T2 passou de 13 para 47 barras lidas (20/10)."""
    polis = [[tuple(v) for v in e["vertices"]] for e in ents if e.get("tipo") == "polilinha" and e.get("fechada") and len(e.get("vertices") or []) >= 3]
    if not polis:
        return ents
    # a alma em zigue-zague numa polilinha aberta só (a viga de rigidez VC01 do Hangar): um trecho por lado, cada um cortado
    abertas = []
    for e in ents:
        if e.get("tipo") == "polilinha" and not e.get("fechada") and len(e.get("vertices") or []) >= 3:
            vs = e["vertices"]
            for i, (P, Q) in enumerate(zip(vs, vs[1:])):
                abertas.append(dict({k: v for k, v in e.items() if k not in ("vertices", "fechada", "tipo")}, tipo="linha",
                                    a=list(P), b=list(Q), id="%s-z%d" % (e.get("id") or "p", i)))
    if abertas:
        ents = [e for e in ents if not (e.get("tipo") == "polilinha" and not e.get("fechada") and len(e.get("vertices") or []) >= 3)] + abertas
    saida = []
    for e in ents:
        if e.get("tipo") != "linha":
            saida.append(e)
            continue
        pedacos = _fora_dos_poligonos(tuple(e["a"]), tuple(e["b"]), polis)
        if len(pedacos) == 1 and math.dist(pedacos[0][0], tuple(e["a"])) < 1e-6 and math.dist(pedacos[0][1], tuple(e["b"])) < 1e-6:
            saida.append(e)
            continue
        for i, (P, Q) in enumerate(pedacos):
            n = dict(e, a=[round(P[0], 2), round(P[1], 2)], b=[round(Q[0], 2), round(Q[1], 2)])
            if i:
                n["id"] = "%s-%d" % (e.get("id") or "l", i)
            saida.append(n)
    return saida


# ---------------------------------------------------------------------------------------------------- Fase 4: terças

_LINHA_TERCA = re.compile(r"^\s*(T\.?\s*[CL]\.?\s*\d+(?:\s*-\s*[A-Z])?)\s*-\s*(\d+)\s*P[ÇC]\.?\s*-\s*L\s*=\s*([\d.,]+)\s*\(([^)]+)\)", re.I)


def _marca_terca(t: str) -> str:
    """"T.C. 2 - A" → "T.C.2-A" (a marca como o projeto escreve, sem espaços)"""
    return re.sub(r"\s+", "", t.upper())


def tabela_de_tercas(des: Desenho, folhas_: List[dict]) -> Dict[str, dict]:
    """As terças das folhas de detalhe ("T.C.1 - 14 PÇ - L = 546 (U127x50#2,25)"): {marca: {qtd, L (o número escrito),
    perfil (o nome do catálogo), texto}}."""
    from nucleo2d.reconhecer import perfil_do_texto
    caixas = [f["caixa"] for f in folhas_ if f["caixa"] and re.search(r"TER[CÇ]A", f["titulo"], re.I)]
    tab: Dict[str, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Texto) or (caixas and not any(_dentro(e, c) for c in caixas)):
            continue
        m = _LINHA_TERCA.match(e.texto or "")
        if not m:
            continue
        p = perfil_do_texto(m.group(4))
        tab[_marca_terca(m.group(1))] = {"qtd": int(m.group(2)), "L": _valor(m.group(3)), "perfil": p["perfil"] if p else None,
                                          "escrito": m.group(4).strip(), "texto": e.texto.strip()}
    return tab


def _grade_da_folha(des: Desenho, caixa) -> Optional[dict]:
    """As linhas de eixo de uma folha nas duas direções, em ordem: {"h": [pos y…], "v": [pos x…]} (as horizontais pela
    altura, as verticais pela abscissa) — para casar a malha de uma planta com a da locação pela ordem das linhas."""
    hs, vs = [], []
    for l in _linhas_de_eixo(des, caixa):
        (ax, ay), (bx, by) = l["a"], l["b"]
        if abs(by - ay) <= 0.02 * l["L"]:
            hs.append((ay + by) / 2)
        elif abs(bx - ax) <= 0.02 * l["L"]:
            vs.append((ax + bx) / 2)

    def unicos(xs):
        out = []
        for x in sorted(xs):
            if not out or x - out[-1] > 50.0:
                out.append(x)
        return out
    return {"h": unicos(hs), "v": unicos(vs)}


def _secoes_de_terca(des: Desenho, caixa_folha, caixa_tesoura) -> List[tuple]:
    """As terças desenhadas em corte em cima do banzo, na vista da tesoura: [(s, pé)] — s do canto de baixo à esquerda
    da tesoura até o meio da seção, pé a face de baixo dela acima da base da tesoura (a camada da terça, não a do
    suporte)."""
    (x0, y0), (x1, y1) = caixa_tesoura
    out = []
    for e in des.entidades.values():
        if not isinstance(e, Polilinha) or not re.search(r"TER[CÇ]A", e.camada or "", re.I) or re.search(r"SUPORTE", e.camada or "", re.I):
            continue
        if not _dentro(e, caixa_folha):
            continue
        xs, ys = [v[0] for v in e.vertices], [v[1] for v in e.vertices]
        if max(xs) - min(xs) > 400 or max(ys) - min(ys) > 400:
            continue
        cx = (min(xs) + max(xs)) / 2
        if x0 - 200 <= cx <= x1 + 200 and y0 - 200 <= min(ys) <= y1 + 400:
            out.append((round(cx - x0, 1), round(min(ys) - y0, 1)))
    return sorted(out)


def tercas_da_planta(des: Desenho, caixa_planta, locacao: dict, gravados: dict, tesouras_: List[dict], apoio: float,
                     folhas_: List[dict]) -> dict:
    """As terças da planta de terças, nos eixos gravados (20/10/2026, Fase 4 da Identificação para modelagem):

    · a malha da planta casa com a da locação pela ordem das linhas (a mesma folha-modelo do projetista: as horizontais
      com as horizontais, as verticais com as verticais) — cada peça de terça vai para o sistema dos eixos gravados;
    · as pontas da peça caem nos eixos numerados mais perto (a T.C.1 do Hangar vai do 1 ao 3, passando pelo 2);
    · a cota: o pé da terça desenhada em corte na vista geral da tesoura daquele eixo, com a tesoura posta como foi
      colada (centrada entre os eixos com letra, a base no apoio); sem corte perto, a peça sai sem cota (aviso);
    · a marca é o texto junto da peça (T.C.1…), o perfil e o comprimento vêm da tabela das folhas de terças; o
      comprimento medido que não casa com o escrito vira aviso — nada é esticado (seguir o projeto).

    Devolve {pecas: [{marca, perfil, eixo_a, eixo_b, g_a, g_b, p, z_pe, L, u}], tabela, avisos}."""
    avisos: List[str] = []
    tab = tabela_de_tercas(des, folhas_)
    gp = _grade_da_folha(des, caixa_planta)
    gl = _grade_da_folha(des, locacao["caixa"])
    nums = sorted(gravados.get("numeros") or [], key=lambda e: e["pos"])
    lets = sorted(gravados.get("letras") or [], key=lambda e: e["pos"])
    if not gp or len(gp["h"]) != len(gl["h"]) or len(gp["v"]) != len(gl["v"]):
        return {"pecas": [], "tabela": tab, "avisos": ["a malha de eixos da planta de terças (%d × %d linhas) não é a da locação (%d × %d): "
                                                       "as terças não têm como ir para os eixos." % (len(gp["h"]), len(gp["v"]), len(gl["h"]), len(gl["v"]))]}
    # a planta → a locação: a mesma posição relativa às linhas (média das diferenças, nas duas direções)
    dx = sum(b - a for a, b in zip(gp["v"], gl["v"])) / len(gl["v"])
    dy = sum(b - a for a, b in zip(gp["h"], gl["h"])) / len(gl["h"])
    ex = locacao["eixos"]
    g, p = ex["eixo_g"], ex["perp_g"]
    # as linhas da locação, em ordem de posição, ↔ os eixos gravados em ordem de posição
    lnums = sorted(ex.get("numeros") or [], key=lambda v: v["pos"])
    llets = sorted(ex.get("letras") or [], key=lambda v: v["pos"])
    if len(lnums) != len(nums) or len(llets) != len(lets):
        avisos.append("os eixos gravados não são os da varredura (%d e %d contra %d e %d): confira as terças." % (len(nums), len(lets), len(lnums), len(llets)))
    nome_num = {round(v["pos"], 1): (nums[i]["nome"] if i < len(nums) else v["nome"]) for i, v in enumerate(lnums)}
    pos_num = {nums[i]["nome"]: nums[i]["pos"] for i in range(len(nums))}
    letras_nome = sorted(lets, key=lambda e: str(e["nome"]))
    pA = letras_nome[0]["pos"] if letras_nome else 0.0
    sentido = -1.0 if len(letras_nome) > 1 and letras_nome[-1]["pos"] < pA else 1.0
    uB = abs(letras_nome[-1]["pos"] - pA) if len(letras_nome) > 1 else 0.0
    # o tipo de tesoura de cada eixo e as terças em corte na vista dele (s, pé), com a tesoura posta centrada
    secao_do_eixo: Dict[str, tuple] = {}
    for t in tesouras_:
        if not t.get("caixa"):
            continue
        r = tesoura_da_folha(des, t["caixa"])
        if not r.get("entidades"):
            continue
        cortes = _secoes_de_terca(des, t["caixa"], r["caixa"])
        u_esq = uB / 2.0 - r["largura"] / 2.0
        for n in t.get("eixos") or []:
            secao_do_eixo[n] = (t["tipo"], u_esq, cortes)
    textos = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, caixa_planta)
              and re.match(r"^\s*T\.?\s*[CL]\.?\s*\d", e.texto or "")]
    pecas, sem_cota, sem_tabela = [], 0, set()
    medidas_ruins = collections.Counter()
    for e in des.entidades.values():
        if not _dentro(e, caixa_planta) or not re.search(r"TER[CÇ]A", e.camada or "", re.I) or re.search(r"SUPORTE", e.camada or "", re.I):
            continue
        if isinstance(e, Polilinha):
            xs, ys = [v[0] for v in e.vertices], [v[1] for v in e.vertices]
        elif isinstance(e, Linha):
            xs, ys = [e.a[0], e.b[0]], [e.a[1], e.b[1]]
        else:
            continue
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if max(w, h) < 1000 or min(w, h) > 400:
            continue
        if h >= w:
            P = ((min(xs) + max(xs)) / 2, min(ys))
            Q = ((min(xs) + max(xs)) / 2, max(ys))
        else:
            P = (min(xs), (min(ys) + max(ys)) / 2)
            Q = (max(xs), (min(ys) + max(ys)) / 2)
        # na locação (a mesma folha-modelo, deslocada)
        Pl, Ql = (P[0] + dx, P[1] + dy), (Q[0] + dx, Q[1] + dy)
        ga, gb = Pl[0] * g[0] + Pl[1] * g[1], Ql[0] * g[0] + Ql[1] * g[1]
        pp = (Pl[0] * p[0] + Pl[1] * p[1] + Ql[0] * p[0] + Ql[1] * p[1]) / 2
        perto = lambda gv: min(lnums, key=lambda v: abs(v["pos"] - gv)) if lnums else None   # noqa: E731
        na, nb = perto(min(ga, gb)), perto(max(ga, gb))
        if not na or not nb or na is nb:
            continue
        ea, eb = nome_num[round(na["pos"], 1)], nome_num[round(nb["pos"], 1)]
        # a marca: entre os textos ao lado da peça, o que tem na tabela o comprimento dela; senão o mais perto (no Hangar,
        # o "T.L.1" da terça lateral ficava mais perto da terça da borda, T.C.1 — 5,46 m contra os 4,84 m do T.L.1)
        mx, my = (P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2
        L = math.dist(P, Q)
        raio = 0.6 * max(w, h)
        perto_ = [t for t in textos if math.hypot(t.posicao[0] - mx, t.posicao[1] - my) < raio]

        def casa(t):
            i = tab.get(_marca_terca(t.texto)) or {}
            return bool(i.get("L")) and (abs(L - i["L"] * 10.0) <= 20.0 or abs(L - i["L"]) <= 20.0)
        txt = min(perto_, key=lambda t: (0 if casa(t) else 1, math.hypot(t.posicao[0] - mx, t.posicao[1] - my)), default=None)
        marca = _marca_terca(txt.texto) if txt else ""
        info = tab.get(marca) or {}
        if marca and not info:
            sem_tabela.add(marca)
        if info.get("L") and abs(L - info["L"] * 10.0) > 20.0 and abs(L - info["L"]) > 20.0:
            medidas_ruins[marca] += 1
        u = (pp - pA) * sentido
        z = None
        sec = secao_do_eixo.get(ea) or secao_do_eixo.get(eb)
        if sec:
            _tipo, u_esq, cortes = sec
            if cortes:
                s_, pe = min(cortes, key=lambda c: abs(u_esq + c[0] - u))
                if abs(u_esq + s_ - u) <= 150.0:
                    z = round(apoio + pe, 1)
        if z is None:
            sem_cota += 1
        pecas.append({"marca": marca, "perfil": info.get("perfil"), "eixo_a": ea, "eixo_b": eb, "g_a": pos_num.get(ea), "g_b": pos_num.get(eb),
                      "p": round(pp, 1), "u": round(u, 1), "z_pe": z, "L": round(L, 1)})
    if sem_cota:
        avisos.append("%d terça(s) sem corte na vista da tesoura do eixo delas: ficaram sem cota (no apoio) — confira." % sem_cota)
    if sem_tabela:
        avisos.append("marca(s) sem linha na tabela das folhas de terças (perfil padrão): %s." % ", ".join(sorted(sem_tabela)))
    for m, n in sorted(medidas_ruins.items()):
        avisos.append("%s: %d peça(s) com o comprimento desenhado diferente do escrito na tabela (L = %s) — confira o projeto." % (m, n, tab[m]["L"]))
    contagem = collections.Counter(pc["marca"] for pc in pecas)
    laterais = sorted(m for m in tab if m.startswith("T.L") and not contagem.get(m))
    if laterais:
        avisos.append("terças laterais da tabela fora da planta de terças (são do fechamento): %s — %d peça(s)."
                      % (", ".join(laterais), sum(tab[m]["qtd"] for m in laterais)))
    for m, info in sorted(tab.items()):
        if m.startswith("T.C") and contagem.get(m, 0) != info["qtd"]:
            avisos.append("%s: %d na planta, %d na tabela." % (m, contagem.get(m, 0), info["qtd"]))
    return {"pecas": sorted(pecas, key=lambda pc: (pc["u"], pc["g_a"] or 0)), "tabela": tab, "avisos": avisos}


# ---------------------------------------------------------------------------------- Etapa 4: contraventos e outras peças

_MARCA_PECA = re.compile(r"^\s*((?:CV|AG|CR|TR|VC|VT|VB|VU|MF)\s*\d*(?:-[A-Z])?)\b", re.I)
_TAB_PECA = re.compile(r"^\s*((?:CV|AG|CR|TR)\s*\d+)\s*-\s*(.+?)\s*L\s*=\s*([\d.,]+)\s*-\s*(\d+)\s*P", re.I)


def _papel_da_legenda(texto: str) -> Optional[str]:
    t = texto.upper()
    if re.search(r"CONTRAVENT", t):
        return "contraventamento"
    if re.search(r"AGULHAMENT|CORRENTE", t):
        return "corrente"
    if re.search(r"A\s+DEFINIR", t):
        return "a definir"
    return None


def _legenda_de_cores(des: Desenho, caixa, fora_de) -> Dict[str, dict]:
    """A legenda de cores da folha: a linha curta de cada camada, fora da planta (à direita da malha), com o texto ao lado
    ("Ø1/2 - contraventos") → {camada: {texto, perfil, papel}}."""
    from nucleo2d.reconhecer import perfil_do_texto
    textos = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, caixa)]
    out: Dict[str, dict] = {}
    for e in des.entidades.values():
        if not isinstance(e, Linha) or not _dentro(e, caixa) or min(e.a[0], e.b[0]) < fora_de:
            continue
        if abs(e.a[1] - e.b[1]) > 1 or not 300 <= abs(e.b[0] - e.a[0]) <= 3000:
            continue
        x1, y = max(e.a[0], e.b[0]), e.a[1]
        ao_lado = [t for t in textos if 0 <= t.posicao[0] - x1 <= 2500 and abs(t.posicao[1] - y) <= 250]
        if not ao_lado:
            continue
        t = min(ao_lado, key=lambda t: abs(t.posicao[1] - y)).texto.strip()
        p = perfil_do_texto(t.split(" - ")[0])
        out[e.camada] = {"texto": t, "perfil": p["perfil"] if p else None, "papel": _papel_da_legenda(t)}
    return out


class _Tesouras:
    """As tesouras dos eixos (o tipo e a vista geral de cada eixo numerado), postas como foram coladas — centradas entre
    os eixos com letra, a base no apoio —, para dar a cota de um ponto da cobertura: o eixo do banzo de cima ou de baixo
    e o pé das terças, em cada u (ao longo da tesoura, do eixo A)."""

    def __init__(self, des: Desenho, tesouras_: List[dict], uB: float, apoio: float):
        self.apoio = apoio
        self.por_eixo: Dict[str, dict] = {}
        for t in tesouras_:
            if not t.get("caixa"):
                continue
            r = tesoura_da_folha(des, t["caixa"])
            if not r.get("entidades"):
                continue
            x0, y0 = r["caixa"][0]
            polis = [[(v[0] - x0, v[1] - y0) for v in e["vertices"]] for e in r["entidades"]
                     if e.get("tipo") == "polilinha" and e.get("fechada") and len(e.get("vertices") or []) >= 3
                     and max(v[0] for v in e["vertices"]) - min(v[0] for v in e["vertices"]) > 1000]
            info = {"tipo": t["tipo"], "u_esq": uB / 2.0 - r["largura"] / 2.0, "polis": polis,
                    "cortes": _secoes_de_terca(des, t["caixa"], r["caixa"])}
            for n in t.get("eixos") or []:
                self.por_eixo[n] = info

    def _faixas(self, info, s):
        """os banzos (contornos fechados) na abscissa s: [(y de baixo, y de cima)], de baixo para cima"""
        out = []
        for poli in info["polis"]:
            ys = []
            for (ax, ay), (bx, by) in zip(poli, poli[1:] + poli[:1]):
                if (ax - s) * (bx - s) <= 0 and abs(bx - ax) > 1e-9:
                    ys.append(ay + (by - ay) * (s - ax) / (bx - ax))
            if len(ys) >= 2:
                out.append((min(ys), max(ys)))
        return sorted(out)

    def banzo(self, eixo: str, u: float, qual: str) -> Optional[float]:
        info = self.por_eixo.get(eixo)
        if not info:
            return None
        fx = self._faixas(info, u - info["u_esq"])
        if not fx:
            return None
        lo, hi = fx[-1] if qual == "sup" else fx[0]
        return round(self.apoio + (lo + hi) / 2.0, 1)

    def terca(self, eixo: str, u: float, h_terca: float) -> Optional[float]:
        """o eixo da terça em u: o pé pela terça em corte mais perto (ou entre as duas vizinhas) + meia altura dela"""
        info = self.por_eixo.get(eixo)
        if not info or not info["cortes"]:
            return None
        cs = sorted((info["u_esq"] + s_, pe) for s_, pe in info["cortes"])
        perto = min(cs, key=lambda c: abs(c[0] - u))
        if abs(perto[0] - u) <= 150:
            pe = perto[1]
        else:
            antes = [c for c in cs if c[0] <= u]
            depois = [c for c in cs if c[0] >= u]
            if not antes or not depois:
                pe = perto[1]
            else:
                a, b = antes[-1], depois[0]
                pe = a[1] + (b[1] - a[1]) * (u - a[0]) / ((b[0] - a[0]) or 1.0)
        return round(self.apoio + pe + h_terca / 2.0, 1)


def _membros_em_barras(lt: dict) -> Optional[dict]:
    """a leitura da tesoura (leitura_quadros.ler_tesoura) no formato do desenho da treliça da planta — o mesmo de
    implantacao.js _desenhoDaLeitura: [u0, v0, u1, v1, papel] com a origem no canto de baixo à esquerda"""
    ms = [m for m in lt.get("membros") or [] if not m.get("moldura")]
    if len(ms) < 3:
        return None
    bz = [m for m in ms if m["papel"] == "banzo"]

    def h_em(m, s):
        return min(m["h0"], m["h1"]) if abs(m["s1"] - m["s0"]) < 1e-6 else m["h0"] + (m["h1"] - m["h0"]) * (s - m["s0"]) / (m["s1"] - m["s0"])
    barras = []
    for m in ms:
        papel = m["papel"] if m["papel"] in ("montante", "diagonal") else "diagonal"
        if m["papel"] == "banzo":
            s = (m["s0"] + m["s1"]) / 2
            h = h_em(m, s)
            outros = [h_em(o, s) for o in bz if o is not m and min(o["s0"], o["s1"]) - 1 <= s <= max(o["s0"], o["s1"]) + 1]
            abaixo, acima = any(x < h - 50 for x in outros), any(x > h + 50 for x in outros)
            papel = "diagonal" if abaixo and acima else "banzo_sup" if abaixo else "banzo_inf"
        barras.append([m["s0"], m["h0"], m["s1"], m["h1"], papel])
    s0 = min(min(b[0], b[2]) for b in barras)
    h0 = min(min(b[1], b[3]) for b in barras)
    out = [[round(b[0] - s0, 1), round(b[1] - h0, 1), round(b[2] - s0, 1), round(b[3] - h0, 1), b[4]] for b in barras]
    return {"barras": out, "vao": round(max(max(b[0], b[2]) for b in out), 1), "altura": round(max(max(b[1], b[3]) for b in out), 1)}


#: a alma da viga treliçada sem perfil escrito (a VC do Hangar só escreve o banzo): a menor cantoneira que o projeto usa
ALMA_PADRAO = "L 25×25"


def _meia_altura(perfil: Optional[str]) -> float:
    from nucleo3d.de_planta_estrutura import _altura_do_perfil
    try:
        return _altura_do_perfil(perfil) / 2.0 if perfil else 63.5
    except Exception:                                                # noqa: BLE001
        return 63.5


def _vigas_das_folhas(des: Desenho, folhas_: List[dict]) -> Dict[str, dict]:
    """As vigas das folhas "VIGA … VC01 - 2 PÇ": {sigla: {folha, qtd, perfil, trelica (o desenho, se for treliçada)}}."""
    from nucleo2d.reconhecer import perfil_do_texto
    from nucleo3d import leitura_quadros as LQ
    out: Dict[str, dict] = {}
    for f in folhas_:
        m = re.match(r"\s*VIGA\b.*?\b((?:VC|VT|VB|VR|VP)\d*)\s*-\s*(\d+)\s*P", f["titulo"], re.I)
        if not m or not f["caixa"]:
            continue
        sigla = m.group(1).upper()
        perfil = None
        for e in des.entidades.values():
            if isinstance(e, Texto) and _dentro(e, f["caixa"]) and re.search(r"L\s*=", e.texto or ""):
                p = perfil_do_texto(e.texto)
                if p:
                    perfil = p["perfil"]
                    break
        r = tesoura_da_folha(des, f["caixa"])
        trelica = None
        if r.get("entidades") and (r.get("altura") or 0) > 300:
            lt, _ap, _el = LQ.ler_tesoura({"id": "v", "tipo": "tesoura", "nome": sigla, "escala": 1, "x": 0.0, "y": 0.0}, r["entidades"])
            trelica = _membros_em_barras(lt)
        out[sigla] = {"folha": f["folha"], "qtd": int(m.group(2)), "perfil": perfil, "trelica": trelica,
                      "largura": r.get("largura"), "altura": r.get("altura")}
    return out


def outras_pecas(des: Desenho, folhas_: List[dict], locacao: dict, gravados: dict, tesouras_: List[dict], apoio: float,
                 h_terca: float = 127.0) -> dict:
    """A etapa 4 da Identificação para modelagem (20/10/2026): o que a planta de contraventos e a locação desenham além das
    tesouras e das terças, nos eixos gravados.

    · Contraventos (CV) das plantas de contraventamento, no plano do banzo de cima ou do de baixo (pelo título da folha):
      cada ponta na cota do eixo daquele banzo, na tesoura do eixo mais perto — o contravento inclinado como o telhado;
    · agulhamentos (AG) e correntes, no plano das terças (o eixo da terça em cada ponta);
    · o perfil pela legenda de cores da folha (a camada → "Ø1/2 - contraventos"); a camada "A DEFINIR" do projetista
      vai com o perfil das correntes e vira aviso; a marca pelo texto ao lado (CV1, AG3…);
    · as vigas das folhas "VIGA … VC01 - 2 PÇ" postas onde a locação marca a sigla: a treliçada (a viga de rigidez VC,
      em pé entre as tesouras, a base na base delas) pelo desenho da folha dela; a simples (VT) no plano do banzo de baixo.

    Devolve {barras: [{marca, papel, perfil, g_a, p_a, z_a, g_b, p_b, z_b}], trelicas: [{marca, g_a, g_b, p, z_base,
    desenho, perfil}], avisos}."""
    avisos: List[str] = []
    ex = locacao["eixos"]
    g, p = ex["eixo_g"], ex["perp_g"]
    gl = _grade_da_folha(des, locacao["caixa"])
    nums = sorted(gravados.get("numeros") or [], key=lambda e: e["pos"])
    lets = sorted(gravados.get("letras") or [], key=lambda e: str(e["nome"]))
    lnums = sorted(ex.get("numeros") or [], key=lambda v: v["pos"])
    nome_num = {round(v["pos"], 1): (nums[i]["nome"] if i < len(nums) else v["nome"]) for i, v in enumerate(lnums)}
    pA = lets[0]["pos"] if lets else 0.0
    sentido = -1.0 if len(lets) > 1 and lets[-1]["pos"] < pA else 1.0
    uB = abs(lets[-1]["pos"] - pA) if len(lets) > 1 else 0.0
    T = _Tesouras(des, tesouras_, uB, apoio)

    def no_sistema(pt, dx, dy):
        x, y = pt[0] + dx, pt[1] + dy
        return x * g[0] + y * g[1], x * p[0] + y * p[1]

    def eixo_perto(gv):
        v = min(lnums, key=lambda v: abs(v["pos"] - gv)) if lnums else None
        return nome_num[round(v["pos"], 1)] if v else None

    barras, a_definir, sem_cota = [], 0, 0
    for f in folhas_:
        if not f["caixa"] or not re.search(r"CONTRAVENT", f["titulo"], re.I) or not re.search(r"PLANTA", f["titulo"], re.I):
            continue                                     # só as plantas (as folhas de peças e de aletas são detalhe)
        plano = "inf" if re.search(r"INFERIOR", f["titulo"], re.I) else "sup"
        gp = _grade_da_folha(des, f["caixa"])
        if len(gp["h"]) != len(gl["h"]) or len(gp["v"]) != len(gl["v"]):
            avisos.append("folha %d: a malha não é a da locação — os contraventos dela ficaram de fora." % f["folha"])
            continue
        dx = sum(b - a for a, b in zip(gp["v"], gl["v"])) / len(gl["v"])
        dy = sum(b - a for a, b in zip(gp["h"], gl["h"])) / len(gl["h"])
        xmax = max(gp["v"]) if gp["v"] else f["caixa"][1][0]
        leg = _legenda_de_cores(des, f["caixa"], xmax + 1500)
        corrente = next((v["perfil"] for v in leg.values() if v["papel"] == "corrente" and v["perfil"] and "Ø" not in v["texto"]), None)
        textos = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, f["caixa"]) and _MARCA_PECA.match(e.texto or "")]
        for e in des.entidades.values():
            if not isinstance(e, Linha) or not _dentro(e, f["caixa"]) or max(e.a[0], e.b[0]) > xmax + 500:
                continue
            info = leg.get(e.camada)
            if not info or not info["papel"]:
                continue
            papel, perfil = info["papel"], info["perfil"]
            e_a_definir = papel == "a definir"
            if e_a_definir:
                a_definir += 1
                papel, perfil = "corrente", corrente
            ga, pa = no_sistema(e.a, dx, dy)
            gb, pb = no_sistema(e.b, dx, dy)
            ua, ub = (pa - pA) * sentido, (pb - pA) * sentido
            ea, eb = eixo_perto(ga), eixo_perto(gb)
            if papel == "contraventamento":
                za, zb = T.banzo(ea, ua, plano), T.banzo(eb, ub, plano)
            else:
                za, zb = T.terca(ea, ua, h_terca), T.terca(eb, ub, h_terca)
            if za is None or zb is None:
                sem_cota += 1
                za = zb = za if za is not None else (zb if zb is not None else apoio)
            mx, my = (e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2
            L = math.dist(e.a, e.b)
            txt = min(textos, key=lambda t: math.hypot(t.posicao[0] - mx, t.posicao[1] - my), default=None)
            marca = _MARCA_PECA.match(txt.texto).group(1).upper().replace(" ", "") if txt and math.hypot(txt.posicao[0] - mx, txt.posicao[1] - my) < 0.6 * L else ""
            if papel == "corrente" and not marca.startswith(("AG", "CR")):
                marca = "AG" if "AGULH" in (e.camada or "").upper() and "Ø" in (info["texto"] or "") else "CR"
            barras.append({"marca": marca, "papel": papel, "perfil": perfil, "plano": plano if papel == "contraventamento" else "terças",
                           "g_a": round(ga, 1), "p_a": round(pa, 1), "z_a": za, "g_b": round(gb, 1), "p_b": round(pb, 1), "z_b": zb,
                           **({"a_definir": True} if e_a_definir else {})})
    # as marcas das correntes pela tabela de peças ("AGULHAMENTOS DIAGONAIS - BARRA REDONDA Ø3/8" (AG3)"): perfil → marca
    from nucleo2d.reconhecer import perfil_do_texto
    marca_do_perfil: Dict[str, str] = {}
    for f in folhas_:
        if not f["caixa"] or not re.search(r"PE[CÇ]AS", f["titulo"], re.I):
            continue
        for e in des.entidades.values():
            if isinstance(e, Texto) and _dentro(e, f["caixa"]):
                m = re.search(r"\(((?:AG|CR)\d+)\)\s*$", e.texto or "")
                pf = perfil_do_texto(e.texto or "") if m else None
                if m and pf:
                    marca_do_perfil.setdefault(pf["perfil"], m.group(1).upper())

    def forma(b):
        dg, dp = abs(b["g_b"] - b["g_a"]), abs(b["p_b"] - b["p_a"])
        L = math.hypot(dg, dp)
        return ("diag" if min(dg, dp) > 0.2 * L else "reta"), L
    definidas = [b for b in barras if b["papel"] == "corrente" and not b.get("a_definir")]
    perfis_a_definir = collections.Counter()
    for b in barras:
        if b["papel"] != "corrente":
            continue
        if b.get("a_definir"):
            # a peça "A DEFINIR" do projetista vai com o perfil da definida de mesma forma (a diagonal com a diagonal, a reta
            # com a reta, comprimento parecido): no Hangar, 16 diagonais A DEFINIR iguais às AG3 Ø3/8" saíam em L 25×25
            # como corrente (o usuário, 20/10: "alguns contraventamentos de barra viraram cantoneiras")
            fb, Lb = forma(b)
            cand = [d for d in definidas if forma(d)[0] == fb and abs(forma(d)[1] - Lb) <= 0.3 * Lb]
            if cand:
                d = min(cand, key=lambda d: abs(forma(d)[1] - Lb))
                b["perfil"] = d["perfil"]
            perfis_a_definir[b["perfil"] or "o padrão"] += 1
        if not re.match(r"^(AG|CR)\d", b["marca"] or "") and b["perfil"] in marca_do_perfil:
            b["marca"] = marca_do_perfil[b["perfil"]] + ("?" if b.get("a_definir") else "")
    if a_definir:
        avisos.append("%d peça(s) na camada \"A DEFINIR\" do projetista foram com o perfil da peça definida de mesma forma (%s) — "
                      "confirme com o projetista." % (a_definir, ", ".join("%d com %s" % (n, p) for p, n in sorted(perfis_a_definir.items()))))
    if sem_cota:
        avisos.append("%d peça(s) sem a tesoura do eixo delas lida: ficaram na cota do apoio — confira." % sem_cota)

    # as vigas: as das folhas de viga, onde a locação marca a sigla
    vigas = _vigas_das_folhas(des, folhas_)
    trelicas = []
    if vigas:
        siglas = [e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, locacao["caixa"])
                  and re.match(r"^\s*(%s)\s*$" % "|".join(re.escape(s) for s in vigas), e.texto or "", re.I)]
        candidatas = []
        for e in des.entidades.values():
            if not _dentro(e, locacao["caixa"]) or re.search(r"EIXO|COTA|CONCRETO|TEXTO|MARCA|FOLHA", e.camada or "", re.I):
                continue
            if isinstance(e, Polilinha):
                xs, ys = [v[0] for v in e.vertices], [v[1] for v in e.vertices]
            elif isinstance(e, Linha):
                xs, ys = [e.a[0], e.b[0]], [e.a[1], e.b[1]]
            else:
                continue
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if max(w, h) < 1000 or min(w, h) > 300:
                continue
            P = ((min(xs) + max(xs)) / 2, min(ys)) if h >= w else (min(xs), (min(ys) + max(ys)) / 2)
            Q = ((min(xs) + max(xs)) / 2, max(ys)) if h >= w else (max(xs), (min(ys) + max(ys)) / 2)
            ga, pa = no_sistema(P, 0.0, 0.0)
            gb, pb = no_sistema(Q, 0.0, 0.0)
            if abs(pa - pb) > 50 or abs(ga - gb) < 1000:
                continue                                     # só a que corre ao longo do galpão, entre tesouras
            candidatas.append((P, Q, ga, gb, (pa + pb) / 2))
        usadas = collections.Counter()
        for t in siglas:
            sig = t.texto.strip().upper()
            perto = min(candidatas, key=lambda c: math.hypot((c[0][0] + c[1][0]) / 2 - t.posicao[0], (c[0][1] + c[1][1]) / 2 - t.posicao[1]), default=None)
            if not perto or math.hypot((perto[0][0] + perto[1][0]) / 2 - t.posicao[0], (perto[0][1] + perto[1][1]) / 2 - t.posicao[1]) > 1500:
                continue
            candidatas.remove(perto)
            _P, _Q, ga, gb, pp = perto
            v = vigas[sig]
            u = (pp - pA) * sentido
            ea, eb = eixo_perto(min(ga, gb)), eixo_perto(max(ga, gb))
            usadas[sig] += 1
            if v["trelica"]:
                trelicas.append({"marca": sig, "g_a": round(min(ga, gb), 1), "g_b": round(max(ga, gb), 1), "p": round(pp, 1), "u": round(u, 1),
                                 "perfil_alma": ALMA_PADRAO,
                                 # a base da viga na base das tesouras: o eixo do banzo de baixo meio perfil acima do apoio
                                 "z_base": round(apoio + _meia_altura(v["perfil"]), 1), "desenho": v["trelica"], "perfil": v["perfil"],
                                 "eixos": [ea, eb]})
            else:
                za, zb = T.banzo(ea, u, "inf"), T.banzo(eb, u, "inf")
                if za is None or zb is None:
                    za = zb = apoio
                barras.append({"marca": sig, "papel": "travamento", "perfil": v["perfil"], "plano": "inf",
                               "g_a": round(min(ga, gb), 1), "p_a": round(pp, 1), "z_a": za, "g_b": round(max(ga, gb), 1), "p_b": round(pp, 1), "z_b": zb})
        for sig, v in sorted(vigas.items()):
            if usadas[sig] != v["qtd"]:
                avisos.append("%s: %d na locação, %d no título da folha %d." % (sig, usadas[sig], v["qtd"], v["folha"]))
            if v["trelica"] and not v["perfil"]:
                avisos.append("%s: sem o perfil escrito na folha %d (vai o padrão)." % (sig, v["folha"]))
            if v["trelica"] and usadas[sig]:
                avisos.append("%s: a alma não tem perfil escrito na folha %d — foi com %s; confirme com o projetista." % (sig, v["folha"], ALMA_PADRAO))
    return {"barras": barras, "trelicas": trelicas, "avisos": avisos,
            "resumo": dict(collections.Counter(b["marca"] or b["papel"] for b in barras) + collections.Counter(t["marca"] for t in trelicas))}


# ------------------------------------------- a tesoura como o projeto: as pontas e os perfis (Hangar Almayer, 20/10/2026)

_MARCA_DA_PECA = re.compile(r"^\s*T\d+-([BML])\d+\s+(\S+)\s+L\s*=", re.I)


def perfis_da_tesoura(des: Desenho, tipo: str, folhas_: List[dict]) -> Dict[str, dict]:
    """Os perfis da tesoura `tipo` pelo projeto (20/10/2026, o usuário: no Hangar o modelo saiu com o U 150 e a L 50 do
    diálogo): a folha de marcas ("T2-B1 2U127x50#3,75 L=999,0 16 PÇ": B = banzo, M = montante, L = diagonal) e a legenda
    da vista geral (a diagonal que a tabela não lista: a cantoneira que sobra, fora a do suporte "(ST1)").
    {banzo|montante|diagonal: {perfil (catálogo), mult (2 = dois perfis: banzo composto, cantoneira dupla), texto}}."""
    from nucleo2d.reconhecer import perfil_do_texto
    base = tipo.split("-")[0]
    rx_tipo = re.compile(r"\b%s\b" % re.escape(base))
    out: Dict[str, dict] = {}

    def pega(chave, texto):
        p = perfil_do_texto(texto)
        if p and chave not in out:
            out[chave] = {"perfil": p["perfil"], "mult": int(p.get("mult") or 1), "texto": texto.strip()}
    nome = {"B": "banzo", "M": "montante", "L": "diagonal"}
    for f in folhas_:
        if not f["caixa"] or not rx_tipo.search(f["titulo"]) or not re.search(r"MARCAS", f["titulo"], re.I):
            continue
        for e in des.entidades.values():
            if isinstance(e, Texto) and _dentro(e, f["caixa"]):
                m = _MARCA_DA_PECA.match(e.texto or "")
                if m:
                    pega(nome[m.group(1).upper()], m.group(2))
    for f in folhas_:
        if not f["caixa"] or not rx_tipo.search(f["titulo"]) or not re.search(r"VISTA\s+GERAL", f["titulo"], re.I):
            continue
        textos = sorted((e for e in des.entidades.values() if isinstance(e, Texto) and _dentro(e, f["caixa"])), key=lambda e: -e.posicao[1])
        for e in textos:
            t = (e.texto or "").strip()
            if "(ST" in t.upper() or re.search(r"CHAPA|#\s*\d+[,.]?\d*\s*$", t, re.I) and not re.search(r"[UL]\s*\d", t):
                continue
            p = perfil_do_texto(t)
            if not p:
                continue
            if "banzo" not in out and p["perfil"].startswith(("U", "W", "TQ", "TR")):
                pega("banzo", t)
            elif p["perfil"].startswith("L") and p["perfil"] != (out.get("montante") or {}).get("perfil"):
                pega("diagonal", t)
    if "montante" not in out and "diagonal" in out:
        out["montante"] = dict(out["diagonal"])
    return out


def _pares_de_linhas(ents: List[dict], camada_rx=r"TESOURA") -> List[tuple]:
    """os pares de linhas paralelas da mesma camada a 60–320 mm (o perfil desenhado pelas duas faces): [(a, b, dist)]"""
    L = [e for e in ents if e.get("tipo") == "linha" and re.search(camada_rx, e.get("camada") or "", re.I)]
    out, usados = [], set()
    for i, a in enumerate(L):
        for j in range(i + 1, len(L)):
            b = L[j]
            if i in usados or j in usados:
                continue
            ua = (a["b"][0] - a["a"][0], a["b"][1] - a["a"][1])
            ub = (b["b"][0] - b["a"][0], b["b"][1] - b["a"][1])
            la, lb = math.hypot(*ua), math.hypot(*ub)
            if la < 1 or lb < 1 or abs(ua[0] * ub[1] - ua[1] * ub[0]) / (la * lb) > 0.02:
                continue
            n = (-ua[1] / la, ua[0] / la)
            dist = abs((b["a"][0] - a["a"][0]) * n[0] + (b["a"][1] - a["a"][1]) * n[1])
            if 60 <= dist <= 320:
                out.append((a, b, dist))
                usados |= {i, j}
    return out


def desenho_da_tesoura(des: Desenho, caixa, perfis: Optional[Dict[str, dict]] = None) -> Optional[dict]:
    """O desenho da tesoura da folha no formato da treliça da planta ([u0, v0, u1, v1, papel, perfil, seção]), já com
    as pontas como o projeto: o trecho a 45° em linha dupla é banzo (regra 1.2: o topo do painel de ponta) ligado ao
    início do banzo de cima, e a peça em pé (o contorno pequeno no apoio, "T2-B3 L=12,3") é a ponta com o perfil do
    banzo (regra 1.4), do eixo do banzo de baixo até o trecho a 45°. Sem isso o leitor deixava o trecho a 45° como
    diagonal solta e perdia a ponta (as pontas do Hangar sem ligação, 20/10). `origem` é o ponto do desenho do cliente
    que vira o (0, 0) das barras."""
    from nucleo3d import leitura_quadros as LQ
    r = tesoura_da_folha(des, caixa)
    ents = r.get("entidades") or []
    if not ents:
        return None
    lt, _ap, el = LQ.ler_tesoura({"id": "t", "tipo": "tesoura", "nome": "T", "escala": 1, "x": 0.0, "y": 0.0}, ents)
    if el is None or not lt.get("membros"):
        return None
    xe, yb = float(el.x_esq), float(el.y_base)
    ms = [dict(m) for m in lt["membros"] if not m.get("moldura")]
    bz = [m for m in ms if m["papel"] == "banzo"]

    def h_em(m, s):
        return min(m["h0"], m["h1"]) if abs(m["s1"] - m["s0"]) < 1e-6 else m["h0"] + (m["h1"] - m["h0"]) * (s - m["s0"]) / (m["s1"] - m["s0"])

    def perto_seg(p, a, b):
        return _dist_seg(p, a, b)
    extras = []
    for a, b, _d in _pares_de_linhas(ents):
        # a linha de centro do par, no sistema da leitura (s ao longo, h para cima)
        pa = ((a["a"][0] + (b["a"] if math.dist(a["a"], b["a"]) < math.dist(a["a"], b["b"]) else b["b"])[0]) / 2,
              (a["a"][1] + (b["a"] if math.dist(a["a"], b["a"]) < math.dist(a["a"], b["b"]) else b["b"])[1]) / 2)
        pb = ((a["b"][0] + (b["b"] if math.dist(a["b"], b["b"]) < math.dist(a["b"], b["a"]) else b["a"])[0]) / 2,
              (a["b"][1] + (b["b"] if math.dist(a["b"], b["b"]) < math.dist(a["b"], b["a"]) else b["a"])[1]) / 2)
        lo, hi = sorted([(pa[0] - xe, pa[1] - yb), (pb[0] - xe, pb[1] - yb)], key=lambda q: q[1])
        # sai o que o leitor fez desse par (a "diagonal" deslocada)
        ms = [m for m in ms if not (m["papel"] != "banzo" and perto_seg((m["s0"], m["h0"]), lo, hi) < 90 and perto_seg((m["s1"], m["h1"]), lo, hi) < 90)]
        # a ponta de cima no começo do banzo de cima mais perto
        cand = [(math.dist(hi, (m[k0], m[k1])), (m[k0], m[k1])) for m in bz for k0, k1 in (("s0", "h0"), ("s1", "h1"))]
        d_, q_ = min(cand, default=(1e9, hi))
        if d_ <= 150:
            hi = q_
        extras.append({"lo": lo, "hi": hi})
    # as peças em pé: os contornos pequenos da camada da tesoura junto do apoio
    for e in ents:
        if e.get("tipo") != "polilinha" or not e.get("fechada") or not re.search(r"TESOURA", e.get("camada") or "", re.I):
            continue
        xs, ys = [v[0] for v in e["vertices"]], [v[1] for v in e["vertices"]]
        if max(xs) - min(xs) > 400 or max(ys) - min(ys) > 400:
            continue
        cx = (min(xs) + max(xs)) / 2 - xe
        de_baixo = [m for m in bz if min(m["s0"], m["s1"]) - 50 <= cx <= max(m["s0"], m["s1"]) + 50]
        if not de_baixo:
            continue
        hb = min(h_em(m, min(max(cx, min(m["s0"], m["s1"])), max(m["s0"], m["s1"]))) for m in de_baixo)
        topo = max(ys) - yb
        par = min(extras, key=lambda x: abs(x["lo"][0] - cx), default=None)
        if par and abs(par["lo"][0] - cx) <= 150:
            topo = par["lo"][1]
            par["lo"] = (cx, topo)                        # o trecho a 45° nasce no topo da ponta
        if topo - hb > 20:
            extras.append({"ponta": True, "lo": (cx, hb), "hi": (cx, topo)})
            # o que o leitor achou em pé no mesmo lugar (a T3: um "montante" sobre a ponta) sai — a ponta é ela
            ms = [m for m in ms if not (m["papel"] != "banzo" and abs(m["s0"] - cx) < 40 and abs(m["s1"] - cx) < 40)]
    barras = []
    for m in ms:
        papel = m["papel"] if m["papel"] in ("montante", "diagonal") else "diagonal"
        if m["papel"] == "banzo":
            s = (m["s0"] + m["s1"]) / 2
            h = h_em(m, s)
            outros = [h_em(o, s) for o in bz if o is not m and min(o["s0"], o["s1"]) - 1 <= s <= max(o["s0"], o["s1"]) + 1]
            abaixo, acima = any(x < h - 50 for x in outros), any(x > h + 50 for x in outros)
            papel = "diagonal" if abaixo and acima else "banzo_sup" if abaixo else "banzo_inf"
        barras.append([m["s0"], m["h0"], m["s1"], m["h1"], papel])
    for x in extras:
        barras.append([x["lo"][0], x["lo"][1], x["hi"][0], x["hi"][1], "extremidade" if x.get("ponta") else "banzo_sup"])
    # os perfis do projeto em cada barra (o banzo de dois U = composto; a ponta e o trecho a 45° com o do banzo)
    perfis = perfis or {}
    # a seção do banzo: dois perfis = composto (regras_trelica 2.9); um U só é o banzo simples (2.2: a boca para dentro
    # do vão — a leitura "alma no plano" do corte T1 foi desfeita pelo usuário, 21/10)
    pb_ = perfis.get("banzo")
    sec_banzo = "composto" if pb_ and pb_["mult"] >= 2 else ""
    for b in barras:
        chave = "banzo" if b[4] in ("banzo_sup", "banzo_inf", "extremidade") else ("montante" if b[4] == "montante" else "diagonal")
        p = perfis.get(chave)
        if p:
            # [perfil, seção do banzo, vão entre os perfis, virar, cantoneira dupla] — o "2L32x32" da lista de marcas vira o
            # par (2.5 no U simples: dentro da boca, nas abas; 2.9 no composto: uma dentro de cada boca)
            b += [p["perfil"], sec_banzo if chave == "banzo" else "", None, False, chave != "banzo" and p["mult"] >= 2]
    s0 = min(min(b[0], b[2]) for b in barras)
    h0 = min(min(b[1], b[3]) for b in barras)
    out = [[round(b[0] - s0, 1), round(b[1] - h0, 1), round(b[2] - s0, 1), round(b[3] - h0, 1)] + b[4:] for b in barras]
    cont = collections.Counter(b[4] for b in out)
    return {"barras": out, "vao": round(max(max(b[0], b[2]) for b in out), 1), "altura": round(max(max(b[1], b[3]) for b in out), 1),
            "origem": [round(xe + s0, 1), round(yb + h0, 1)], "contagem": dict(cont), "pontas": sum(1 for x in extras if x.get("ponta"))}


# ------------------------------------------- os apoios das tesouras: chapas e chumbadores (Hangar Almayer, 21/10/2026)

_CHAPA_TXT = re.compile(r"\b([A-Z]{1,3}\d+)\s*#\s*(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)")
_FUROS_TXT = re.compile(r"(\d+)\s*FUROS?\s*Ø\s*(\d+(?:[.,]\d+)?)", re.I)
_CHUMB_TXT = re.compile(r"CHUMBADOR\s*Ø\s*(\d+(?:/\d+)?)\s*\"?\s*C\s*=\s*(\d+(?:[.,]\d+)?)", re.I)
_CQ_TXT = re.compile(r"\b(CQ\d+)\s*Ø\s*(\d+(?:/\d+)?)\s*\"?\s*L\s*=\s*(\d+(?:[.,]\d+)?)", re.I)
_MARCA_APOIO = re.compile(r"^\s*([A-Z]\d?)\s*-\s*([A-Z]{1,3}\d+)\s*\+\s*(\d+)\s*Ø\s*(\d+(?:/\d+)?)\"?"
                          r"(?:\s*\+\s*(\d+)\s*([A-Z]{1,3}\d+))?", re.I)


def _num(s: str) -> float:
    return float(str(s).replace(",", "."))


def _diam_pol(txt: str) -> float:
    """5/8 → 15,875 mm (as bitolas da barra redonda); sem fração = mm"""
    from nucleo.acessorios import DIAMETROS_BARRA
    d = DIAMETROS_BARRA.get(txt + '"')
    if d:
        return d
    if "/" in txt:
        a, b = txt.split("/")
        return 25.4 * float(a) / float(b)
    return float(txt)


def _caixa_pol(e) -> Optional[tuple]:
    ps = e.pontos() if hasattr(e, "pontos") else []
    if not ps:
        return None
    xs, ys = [p[0] for p in ps], [p[1] for p in ps]
    return min(xs), min(ys), max(xs), max(ys)


def _giros_90():
    """as 8 posições da folha em relação à obra: giro de 90° em 90° e espelho"""
    out = []
    for k in range(4):
        for esp in (1, -1):
            def T(p, k=k, esp=esp):
                x, y = p[0] * esp, p[1]
                for _ in range(k):
                    x, y = -y, x
                return (x, y)
            out.append(T)
    return out


def apoios_das_tesouras(des: Desenho, folhas_: List[dict], planta: Desenho, apoio: float) -> dict:
    """Os apoios das tesouras nos pilares pré-moldados pelo projeto (21/10/2026, o Hangar: "agora vamos para os detalhes,
    chapas, ligações, isso tem no projeto original"): a folha de LOCAÇÃO DOS CHUMBADORES diz onde vai cada chapa e a
    marca do apoio ("A1 - PB1 + 4 Ø5/8"", "E1 - … + 2 CQ1", pela linha de chamada); as medidas vêm dos textos das folhas
    ("PB1 #9,50 25x25", "CB1 #8,00 20x20", "CHUMBADOR Ø5/8" C=55") e a furação da planta da folha de DETALHE (os furos
    dentro da chapa do tamanho da PB). A folha é casada com os pilares da planta (`planta`, já no real) por giro/espelho
    e deslocamento. A CB vai por cima da PB onde uma tesoura apoia no pilar (a folha APOIO DAS TESOURAS: a PB embutida
    rente ao topo do pilar, a CB por cima, a tesoura nela) — então o topo do pilar fica em `apoio` − espessura da CB.
    {apoios: [{pilar, pilar_id, marca, centro, pb, cb, sob_tesoura, topo_pilar, chumbadores, cq}], chapas, avisos}"""
    from nucleo3d import de_planta_estrutura as DPE
    avisos: List[str] = []
    textos = [e for e in des.entidades.values() if isinstance(e, Texto)]

    def folha(*rx):
        return next((f for f in folhas_ if f.get("caixa") and all(re.search(r, f["titulo"], re.I) for r in rx)), None)
    f_loc = folha(r"CHUMBADOR", r"LOCA")
    f_det = folha(r"CHUMBADOR", r"DETALHE")
    if not f_loc:
        raise ErroDeDados("não achei a folha de locação dos chumbadores (título com CHUMBADORES e LOCAÇÃO)")
    # as chapas e os chumbadores escritos no projeto (em qualquer folha): a medida em cm, a espessura em mm
    chapas: Dict[str, dict] = {}
    chumb = None
    cqs: Dict[str, dict] = {}
    for t in textos:
        s = re.sub(r"\s+", " ", t.texto or "")
        for m in _CHAPA_TXT.finditer(s):
            ch = chapas.setdefault(m.group(1).upper(), {"marca": m.group(1).upper(), "espessura": _num(m.group(2)),
                                                        "largura": _num(m.group(3)) * 10.0, "altura": _num(m.group(4)) * 10.0})
            if "DEFINIR" in s.upper():
                ch.setdefault("a_definir_em", []).append(s)
        mc = _CHUMB_TXT.search(s)
        if mc and chumb is None:
            chumb = {"texto": mc.group(1) + '"', "diametro": _diam_pol(mc.group(1)), "comprimento": _num(mc.group(2)) * 10.0}
        for mq in _CQ_TXT.finditer(s):
            cqs.setdefault(mq.group(1).upper(), {"marca": mq.group(1).upper(), "texto": mq.group(2) + '"',
                                                 "diametro": _diam_pol(mq.group(2)), "comprimento": _num(mq.group(3)) * 10.0})
    # a locação: as chapas desenhadas e a marca de cada uma pela linha de chamada (a ponta na quina da chapa; a outra
    # perto do texto — na mesma altura, o mais perto na horizontal: o texto da direita é alinhado pelo fim)
    cx = f_loc["caixa"]
    ents_loc = [e for e in des.entidades.values() if _dentro(e, cx)]
    quadrados = []
    for e in ents_loc:
        if isinstance(e, Polilinha) and re.search(r"CHAPA", e.camada or "", re.I):
            c = _caixa_pol(e)
            if c and abs((c[2] - c[0]) - (c[3] - c[1])) < 5 and c[2] - c[0] > 50:
                quadrados.append({"centro": ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2), "lado": c[2] - c[0], "caixa": c})
    if not quadrados:
        raise ErroDeDados("a folha %d não tem chapas desenhadas" % f_loc["folha"])
    marcas_t = []
    for t in textos:
        if _dentro(t, cx):
            m = _MARCA_APOIO.match(re.sub(r"\s+", " ", t.texto or ""))
            if m:
                marcas_t.append({"pos": tuple(t.posicao), "marca": m.group(1).upper(), "chapa": m.group(2).upper(),
                                 "chumbadores": int(m.group(3)), "bitola": m.group(4) + '"',
                                 "extra_n": int(m.group(5)) if m.group(5) else 0, "extra": (m.group(6) or "").upper()})
    for e in ents_loc:
        if not (isinstance(e, Linha) and re.search(r"MARCA", e.camada or "", re.I)):
            continue
        for q in quadrados:
            x0, y0, x1, y1 = q["caixa"]
            for pa, pb in ((e.a, e.b), (e.b, e.a)):
                if x0 - 5 <= pa[0] <= x1 + 5 and y0 - 5 <= pa[1] <= y1 + 5:
                    cand = [mt for mt in marcas_t if abs(mt["pos"][1] - pb[1]) < 400]
                    if cand:
                        q["texto"] = min(cand, key=lambda mt: abs(mt["pos"][0] - pb[0]))
    for q in quadrados:
        if "texto" not in q and marcas_t:
            q["texto"] = min(marcas_t, key=lambda mt: math.dist(mt["pos"], q["centro"]))
            avisos.append("a chapa em (%.0f; %.0f) da folha %d não tem linha de chamada: a marca é a do texto mais perto (%s)"
                          % (q["centro"][0], q["centro"][1], f_loc["folha"], q["texto"]["marca"]))
    # os pilares da planta (no real) e as tesouras (a linha de apoio a apoio)
    pilares, tesouras = [], []
    for it in DPE.elementos(planta):
        a, e = it["atributos"], it["entidade"]
        if it["elemento"] == "pilar" and isinstance(e, Polilinha):
            c = _caixa_pol(e)
            pilares.append({"id": it["id"], "marca": str(a.get("marca") or ""), "centro": ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2),
                            "caixa": c, "nivel_topo": a.get("nivel_topo")})
        elif it["elemento"] == "trelica" and isinstance(e, Linha) and a.get("identificacao") != "outra":
            tesouras.append((tuple(e.a), tuple(e.b)))
    if not pilares:
        raise ErroDeDados("a planta não tem pilares para receber as chapas")
    # a folha casada com os pilares (ela é desenhada em mm, como a obra)
    melhor = None
    for T in _giros_90():
        cs = [T(q["centro"]) for q in quadrados]
        for c0 in cs[:4]:
            for pl in pilares:
                d = (pl["centro"][0] - c0[0], pl["centro"][1] - c0[1])
                casados, erro = 0, 0.0
                for c in cs:
                    dd = min(math.dist((c[0] + d[0], c[1] + d[1]), p["centro"]) for p in pilares)
                    if dd < 120.0:
                        casados, erro = casados + 1, erro + dd
                if melhor is None or (casados, -erro) > melhor[0]:
                    melhor = ((casados, -erro), T, d)
    (casados, _e), T, d = melhor
    if casados < len(quadrados):
        avisos.append("%d de %d chapas da folha %d casaram com os pilares da planta — confira a locação"
                      % (casados, len(quadrados), f_loc["folha"]))

    def furacao(ch: dict) -> List[dict]:
        """os furos da chapa pela planta do detalhe (relativos ao centro dela)"""
        if not f_det:
            return []
        circ = [f for f in des.entidades.values() if isinstance(f, Circulo) and re.search(r"FURO", f.camada or "", re.I)
                and _dentro(f, f_det["caixa"])]
        for e in des.entidades.values():
            if not (isinstance(e, Polilinha) and re.search(r"CHAPA", e.camada or "", re.I) and _dentro(e, f_det["caixa"])):
                continue
            c = _caixa_pol(e)
            if not c or abs((c[2] - c[0]) - ch["largura"]) > 3 or abs((c[3] - c[1]) - ch["altura"]) > 3:
                continue
            cc = ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)
            fur = [f for f in circ if c[0] < f.centro[0] < c[2] and c[1] < f.centro[1] < c[3]]
            if fur:
                return [{"dx": round(f.centro[0] - cc[0], 1), "dy": round(f.centro[1] - cc[1], 1), "diametro": round(2 * f.raio, 1)}
                        for f in fur]
        return []
    usados, out = set(), []
    for q in quadrados:
        c = T(q["centro"])
        c = (c[0] + d[0], c[1] + d[1])
        pl = min(pilares, key=lambda p: math.dist(c, p["centro"]))
        if math.dist(c, pl["centro"]) > 120.0 or pl["id"] in usados:
            continue
        usados.add(pl["id"])
        mt = q.get("texto") or {}
        pb = dict(chapas.get(mt.get("chapa") or "", {}))
        if not pb:
            avisos.append("apoio %s: a chapa %s não tem medida escrita no projeto" % (mt.get("marca"), mt.get("chapa")))
            continue
        pb.pop("a_definir_em", None)
        pb["furos"] = furacao(pb)
        if not pb["furos"]:
            avisos.append("apoio %s: a furação da %s não está desenhada na folha de detalhe — sem furos" % (mt.get("marca"), pb["marca"]))
        # a tesoura apoia neste pilar? (a linha dela passa por dentro do contorno dele)
        x0, y0, x1, y1 = pl["caixa"]
        sob = any(_dist_seg(pl["centro"], a_, b_) < min(x1 - x0, y1 - y0) / 2.0 for a_, b_ in tesouras)
        cb = None
        if sob:
            cb_marca = next((k for k in chapas if k.startswith("CB")), None)
            cb = dict(chapas[cb_marca]) if cb_marca else None
            if cb is None:
                avisos.append("apoio %s: a tesoura apoia no pilar %s, mas o projeto não escreve a chapa de apoio (CB)"
                              % (mt.get("marca"), pl["marca"]))
            else:
                cb.pop("a_definir_em", None)
                cb["furos"] = []
        extra = cqs.get(mt.get("extra") or "") if mt.get("extra_n") else None
        out.append({"pilar": pl["marca"], "pilar_id": pl["id"], "marca": mt.get("marca"),
                    "centro": [round(c[0], 1), round(c[1], 1)], "pb": pb, "cb": cb, "sob_tesoura": sob,
                    "topo_pilar": (apoio - float(cb["espessura"])) if (sob and cb) else None,
                    "nivel_topo_pilar": pl["nivel_topo"],
                    "chumbadores": dict(chumb or {}, n=mt.get("chumbadores") or len(pb["furos"])),
                    "cq": dict(extra, n=mt.get("extra_n")) if extra else None})
    for p in pilares:
        if p["id"] not in usados:
            avisos.append("pilar %s: sem chapa na locação dos chumbadores (o projeto não define o apoio dele) — apontamento ao "
                          "projetista" % p["marca"])
    for ch in chapas.values():
        for s in ch.get("a_definir_em", []):
            avisos.append("o projeto marca \"%s\" — foi usada a medida escrita na outra folha; confirme com o projetista" % s)
    if f_det and any(a_["cb"] for a_ in out):
        avisos.append("a folha %d (%s) desenha a CB 40 mm acima da PB e a PB sobre o concreto; a folha APOIO DAS TESOURAS "
                      "põe a CB direto sobre a PB, embutida rente ao topo do pilar — foi seguida esta" % (f_det["folha"], f_det["titulo"]))
    if chumb is None:
        avisos.append("o projeto não escreve o chumbador (\"CHUMBADOR Ø… C=…\")")
    cont = collections.Counter(a_["marca"] for a_ in out)
    return {"apoios": out, "chapas": chapas, "chumbador": chumb, "cq": cqs, "avisos": avisos,
            "resumo": dict(sorted(cont.items())), "folha": f_loc["folha"]}
