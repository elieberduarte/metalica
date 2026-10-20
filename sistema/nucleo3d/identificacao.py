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
