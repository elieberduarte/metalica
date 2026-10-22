# -*- coding: utf-8 -*-
"""Localização e chumbação de prédio: o aço preso em várias lajes (as caixas de porta de cada andar, os pórticos do
duplex e da cobertura do Vicente Residence). A planta única do galpão punha os 12 tipos, os 6 penthouses e o resto uns
sobre os outros, numa linha só, com eixos inventados das caixas, e a chumbação não tinha os chumbadores químicos que a
obra fura em cada laje (usuário, 21/10: "não são informações úteis para obra").

Aqui o aço é repartido por pavimento — cada grupo de peças ligadas entre si vai para a laje mais perto do pé dele —, os
pavimentos com o mesmo aço no mesmo lugar viram um tipo ("TIPO – 10x") e saem:
- localização: a fachada com a linha e o nome de cada laje e as marcas no lugar; uma planta por tipo de pavimento, com
  os pilares do concreto como referência e as cotas até eles;
- chumbação: por tipo de pavimento, os chumbadores (o químico do modelo e a barra de chumbamento) com as chapas em que
  passam, as cadeias de cotas a partir dos pilares e quantos são por pavimento.
"""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido
from nucleo2d.desenho import Camada2D, Desenho
from nucleo2d.detalhe.base import _Papel, _dot, _marcas, _registrar_camadas_de_pecas, _tipo_ifc
from nucleo2d.detalhe.conjuntos import (MENOR_ITEM_LOCALIZACAO, _casco, _itens_de_localizacao, _sobrepoe,
                                        posicao_base)
from saida.detalhamento import _ordem_natural

#: A partir de quantos pavimentos com aço o modelo é tratado como prédio.
MINIMO_PAVIMENTOS = 3
#: Duas peças cujas caixas chegam a isto uma da outra estão ligadas (mm).
TOL_LIGADAS = 30.0
#: O grupo de peças vai para a laje mais perto do pé dele, se estiver a até isto (mm); mais longe, nível próprio.
DIST_LAJE = 2500.0
#: Lajes com o topo a até isto uma da outra são o mesmo nível (mm).
TOL_NIVEL_LAJE = 300.0
#: Sem laje no modelo: um vão maior que isto entre os pés dos grupos separa os níveis (mm).
VAO_NIVEIS = 1000.0
#: Os pilares do concreto até isto além do aço do pavimento entram na planta como referência (mm).
MARGEM_PILARES = 2500.0
#: Pavimentos iguais: mesmas peças, no mesmo lugar, a até isto (mm).
TOL_IGUAIS = 30.0
#: Chumbadores a até isto um do outro em planta são um grupo (a mesma chapa).
RAIO_GRUPO = 300.0


# ------------------------------------------------------------------ os pavimentos
def _caixa3(e) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    vs = e.vertices
    return (tuple(min(q[i] for q in vs) for i in range(3)), tuple(max(q[i] for q in vs) for i in range(3)))


def _centro(e) -> Tuple[float, float, float]:
    vs = e.vertices
    n = float(len(vs))
    return (sum(q[0] for q in vs) / n, sum(q[1] for q in vs) / n, sum(q[2] for q in vs) / n)


def _ligadas(pecas: Sequence[Solido], tol: float = TOL_LIGADAS) -> List[List[Solido]]:
    """As peças em grupos de peças que se tocam (as caixas a até `tol`), por uma grade de 2 m."""
    caixas = [_caixa3(e) for e in pecas]
    pai = list(range(len(pecas)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    passo = 2000.0
    grade: Dict[tuple, List[int]] = collections.defaultdict(list)
    for i, (a, b) in enumerate(caixas):
        faixas = [range(int(math.floor((a[k] - tol) / passo)), int(math.floor((b[k] + tol) / passo)) + 1) for k in range(3)]
        for gx in faixas[0]:
            for gy in faixas[1]:
                for gz in faixas[2]:
                    grade[(gx, gy, gz)].append(i)
    for lst in grade.values():
        for k, i in enumerate(lst):
            a, b = caixas[i]
            for j in lst[k + 1:]:
                ri, rj = raiz(i), raiz(j)
                if ri == rj:
                    continue
                c, d = caixas[j]
                if all(a[t] - tol <= d[t] and c[t] - tol <= b[t] for t in range(3)):
                    pai[ri] = rj
    grupos: Dict[int, List[Solido]] = collections.OrderedDict()
    for i, e in enumerate(pecas):
        grupos.setdefault(raiz(i), []).append(e)
    return list(grupos.values())


def _quem_toca(pecas: Sequence[Solido], tol: float = 2.0):
    """f(sólido) → a peça cuja caixa cruza a dele (a chapa que o chumbador atravessa), ou None."""
    passo = 2000.0
    caixas = [_caixa3(e) for e in pecas]
    grade: Dict[tuple, List[int]] = collections.defaultdict(list)
    for i, (a, b) in enumerate(caixas):
        for gx in range(int(math.floor(a[0] / passo)), int(math.floor(b[0] / passo)) + 1):
            for gy in range(int(math.floor(a[1] / passo)), int(math.floor(b[1] / passo)) + 1):
                grade[(gx, gy)].append(i)

    def f(c):
        a, b = _caixa3(c)
        cx, cy = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        melhor = None
        for i in grade.get((int(math.floor(cx / passo)), int(math.floor(cy / passo))), ()):
            x, y = caixas[i]
            if all(x[k] - tol <= b[k] and a[k] - tol <= y[k] for k in range(3)):
                # a chapa antes do perfil em que ela encosta
                vol = (y[0] - x[0]) * (y[1] - x[1]) * (y[2] - x[2])
                if melhor is None or vol < melhor[0]:
                    melhor = (vol, pecas[i])
        return melhor[1] if melhor else None
    return f


def _lajes(doc: Documento, ids_aco: set) -> List[Tuple[float, str]]:
    """Os níveis das lajes de concreto do modelo: (topo, nome), de baixo para cima. O nome é a camada (o pavimento do
    IFC: "Tipo1-002") quando ela é só daquele nível; senão "NÍVEL +x,xx"."""
    tops: List[Tuple[float, str]] = []
    for e in doc.entidades.values():
        if not isinstance(e, Solido) or e.id in ids_aco or not e.vertices or not getattr(e, "visivel", True):
            continue
        if _tipo_ifc(e) != "IfcSlab":
            continue
        tops.append((max(q[2] for q in e.vertices), str(e.camada or "")))
    grupos: List[List[Tuple[float, str]]] = []
    for t in sorted(tops):
        if grupos and t[0] - grupos[-1][-1][0] <= TOL_NIVEL_LAJE:
            grupos[-1].append(t)
        else:
            grupos.append([t])
    # a camada vale para o nível em que ela mais aparece (a LazerTerreo tem a laje do nível e uma rampa noutro)
    onde: Dict[str, Tuple[int, int]] = {}
    for i, g in enumerate(grupos):
        for c, q in collections.Counter(c for _z, c in g).items():
            if c and (c not in onde or q > onde[c][1]):
                onde[c] = (i, q)
    out = []
    for i, g in enumerate(grupos):
        z = max(z_ for z_, _c in g)
        cam = collections.Counter(c for _z, c in g).most_common(1)[0][0]
        out.append((z, cam if cam and onde.get(cam, (None,))[0] == i else nome_do_nivel(z)))
    return out


def nivel_txt(z: float) -> str:
    return ("%+.2f" % (z / 1000.0)).replace(".", ",")


def nome_do_nivel(z: float) -> str:
    return "NÍVEL %s" % nivel_txt(z)


def _rotulo_da_camada(c: str) -> str:
    """A camada do aço sem o prefixo do material ("Metálica – Tipo" → "Tipo")."""
    return re.sub(r"^\s*(met[aá]lica|a[cç]o|estrutura)\s*[–—-]\s*", "", str(c or ""), flags=re.I).strip()


def _assinatura(pecas: Sequence[Solido], extras: Sequence[Solido], z: float) -> List[tuple]:
    """O que há no pavimento, para achar os iguais: (marca, x, y, altura sobre o nível) de cada peça, em décimos de
    centímetro arredondados (a comparação tolera TOL_IGUAIS)."""
    out = []
    for e in list(pecas) + list(extras):
        cx, cy, _cz = _centro(e)
        z0 = min(q[2] for q in e.vertices)
        marca = posicao_base(e) if _marcas(e).get("posicao") else str(e.nome or "")
        out.append((marca, round(cx / 10.0), round(cy / 10.0), round((z0 - z) / 10.0)))
    return sorted(out)


def _iguais(a: Sequence[tuple], b: Sequence[tuple]) -> bool:
    if len(a) != len(b):
        return False
    lim = TOL_IGUAIS / 10.0
    return all(p[0] == q[0] and all(abs(p[k] - q[k]) <= lim for k in (1, 2, 3)) for p, q in zip(a, b))


def chumbadores_do_modelo(doc: Documento, pecas: Sequence[Solido], nomes_producao: Optional[dict]) -> List[Solido]:
    """Os chumbadores: as peças de produção do tipo chumbador (a barra de chumbamento, CB1) e os fixadores do modelo que
    são chumbador (o químico HIT-V, que não é peça de produção: vai na lista dos parafusos)."""
    tipos = (nomes_producao or {}).get("tipos") or {}
    out = [e for e in pecas if tipos.get(str(_marcas(e).get("posicao") or "")) == "chumbador"]
    ids = {e.id for e in pecas}
    for e in doc.entidades.values():
        if not isinstance(e, Solido) or e.id in ids or not e.vertices or not getattr(e, "visivel", True):
            continue
        a = e.atributos or {}
        if a.get("chumbador_quimico") or (
                (a.get("parafuso") or _tipo_ifc(e) == "IfcMechanicalFastener")
                and re.search(r"chumbador|ancoragem|anchor|hit-?v", str(e.nome or ""), re.I)):
            out.append(e)
    return out


def pavimentos(doc: Documento, pecas: Sequence[Solido], nomes_producao: Optional[dict] = None) -> Optional[dict]:
    """O aço repartido por pavimento, ou None quando o modelo não é prédio (menos de MINIMO_PAVIMENTOS com aço — o
    galpão, o mezanino, a cobertura sobre o pré-moldado: tudo ligado, um nível só).

    Cada grupo de peças que se tocam vai para a laje de concreto com o topo mais perto do pé dele (a caixa pendurada
    debaixo da laje é dessa laje: é nela que se fura); sem laje no modelo, os pés se agrupam pelos vãos. Os pavimentos
    com as mesmas peças no mesmo lugar (em relação ao nível) formam um tipo.

    {"niveis": [{"nome", "z", "pecas", "chumbadores"}], "tipos": [{"nome", "niveis": [índices], "rep": índice}],
     "lajes": [(z, nome)]}."""
    pecas = [e for e in pecas if e.vertices]
    if len(pecas) < MINIMO_PAVIMENTOS:
        return None
    ids_aco = {e.id for e in pecas}
    lajes = _lajes(doc, ids_aco)
    grupos = _ligadas(pecas)
    pes = [(min(q[2] for e in g for q in e.vertices), g) for g in grupos]
    niveis: Dict[float, dict] = {}
    soltos = []
    for z0, g in pes:
        perto = min(lajes, key=lambda t: abs(t[0] - z0)) if lajes else None
        if perto is not None and abs(perto[0] - z0) <= DIST_LAJE:
            niveis.setdefault(perto[0], {"nome": perto[1], "z": perto[0], "pecas": [], "chumbadores": []})["pecas"].extend(g)
        else:
            soltos.append((z0, g))
    # sem laje perto: os pés agrupados pelos vãos
    for z0, g in sorted(soltos, key=lambda t: t[0]):
        alvo = next((n for z_, n in niveis.items() if n.get("sem_laje") and abs(z_ - z0) <= VAO_NIVEIS), None)
        if alvo is None:
            alvo = niveis.setdefault(z0, {"nome": nome_do_nivel(z0), "z": z0, "pecas": [], "chumbadores": [], "sem_laje": True})
        alvo["pecas"].extend(g)
    lista = sorted(niveis.values(), key=lambda n: n["z"])
    if len(lista) < MINIMO_PAVIMENTOS:
        return None
    # os chumbadores que não são peça (o químico) vão para o pavimento com o nível mais perto; os que são peça, com o
    # grupo deles
    ids_nivel = {e.id: i for i, n in enumerate(lista) for e in n["pecas"]}
    toca = _quem_toca(pecas)
    for c in chumbadores_do_modelo(doc, pecas, nomes_producao):
        i = ids_nivel.get(c.id)
        if i is None:
            # o químico vai com a peça que ele atravessa (o do apoio no topo do pórtico do duplex é do duplex, não do
            # tipo de cima, mais perto em altura)
            e = toca(c)
            i = ids_nivel.get(e.id) if e is not None else None
        if i is None:
            zc = _centro(c)[2]
            i = min(range(len(lista)), key=lambda k: abs(lista[k]["z"] - zc))
        lista[i]["chumbadores"].append(c)
    # prédio é o aço PRESO nas lajes: sem chumbador em três ou mais pavimentos não é (o Capitão, pré-moldado com
    # 1.173 lajes, patamares e degraus de concreto e o aço só nos guarda-corpos, saía em 17 "pavimentos" de 01x, 22/10)
    if sum(1 for n in lista if n["chumbadores"]) < MINIMO_PAVIMENTOS:
        return None
    ids_cb = {c.id for n in lista for c in n["chumbadores"]}
    for n in lista:
        n["assinatura"] = _assinatura(n["pecas"], [c for c in n["chumbadores"] if c.id not in ids_aco], n["z"])
        n["pecas_sem_cb"] = [e for e in n["pecas"] if e.id not in ids_cb]
    tipos: List[dict] = []
    for i, n in enumerate(lista):
        t = next((t for t in tipos if _iguais(lista[t["rep"]]["assinatura"], n["assinatura"])), None)
        if t is None:
            tipos.append({"rep": i, "niveis": [i]})
        else:
            t["niveis"].append(i)
    # o nome do tipo pela camada do aço (o que cobre pelo menos um quinto das peças), senão "PAVIMENTO n"
    for k, t in enumerate(tipos, 1):
        cont = collections.Counter(_rotulo_da_camada(e.camada) for e in lista[t["rep"]]["pecas"])
        total = float(sum(cont.values())) or 1.0
        partes = [c for c, q in cont.most_common() if c and c != "0" and q >= 0.2 * total]
        t["nome"] = " + ".join(partes).upper() if partes else "PAVIMENTO %d" % k
    repetidos = collections.Counter(t["nome"] for t in tipos)
    letras = collections.defaultdict(int)
    for t in tipos:
        if repetidos[t["nome"]] > 1:
            letras[t["nome"]] += 1
            t["nome"] = "%s %s" % (t["nome"], chr(ord("A") + letras[t["nome"]] - 1))
    for t in tipos:
        for i in t["niveis"]:
            lista[i]["tipo"] = t["nome"]
    return {"niveis": lista, "tipos": tipos, "lajes": lajes}


# ------------------------------------------------------------------ o desenho
def _registrar_concreto(d: Desenho) -> None:
    if "CONCRETO" not in d.camadas:
        d.camadas["CONCRETO"] = Camada2D("CONCRETO", "#8a94a6", espessura=0.25)


def _pilares(doc: Documento, ids_aco: set) -> List[Solido]:
    """Os pilares do concreto (a referência da obra para medir o aço)."""
    return [e for e in doc.entidades.values()
            if isinstance(e, Solido) and e.id not in ids_aco and e.vertices and getattr(e, "visivel", True)
            and _tipo_ifc(e) == "IfcColumn"]


def _pilares_no_nivel(pilares: Sequence[Solido], z: float, pecas: Sequence[Solido]) -> List[Solido]:
    """Os pilares que chegam ao nível `z` (o do andar de baixo, que sustenta a laje, ou o que passa por ela) a até
    MARGEM_PILARES de alguma peça do aço, um por lugar — pela caixa de todo o aço, o lazer com a piscina longe trazia
    os pilares do prédio inteiro entre os dois."""
    caixas = []
    for e in pecas:
        a, b = _caixa3(e)
        caixas.append((a[0] - MARGEM_PILARES, a[1] - MARGEM_PILARES, b[0] + MARGEM_PILARES, b[1] + MARGEM_PILARES))
    out, vistos = [], set()
    for e in pilares:
        zs = [q[2] for q in e.vertices]
        if not (min(zs) <= z + 50.0 and max(zs) >= z - 1500.0):
            continue
        cx, cy, _cz = _centro(e)
        if not any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in caixas):
            continue
        chave = (round(cx / 50.0), round(cy / 50.0))
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append(e)
    return out


def _orientacao(pecas: Sequence[Solido]):
    """(planta u, v; fachada u, v, w): o lado comprido do aço do prédio na horizontal, como na localização do galpão —
    todas as plantas giram iguais."""
    todos = [q for e in pecas for q in e.vertices]
    ext_x = max(q[0] for q in todos) - min(q[0] for q in todos)
    ext_y = max(q[1] for q in todos) - min(q[1] for q in todos)
    if ext_y > ext_x:
        return ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)), ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0))
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))


def _itens(pecas: Sequence[Solido]) -> List[Tuple[str, List[Solido]]]:
    """(marca, peças) por instância de conjunto: a que o modelo diz (`marcas.instancia`) ou a da conta da localização."""
    com, sem = collections.OrderedDict(), []
    for e in pecas:
        m = _marcas(e)
        if m.get("instancia") and m.get("conjunto") and m.get("conjunto") != m.get("posicao"):
            com.setdefault((str(m["conjunto"]), str(m["instancia"])), []).append(e)
        else:
            sem.append(e)
    return [(k[0], lst) for k, lst in com.items()] + _itens_de_localizacao(sem)


def _listar_niveis(pav: dict, t: dict, largura: int = 105) -> List[str]:
    """As lajes de um tipo em linhas de até `largura` letras: "Tipo1-002 (+28,08), Tipo1-003 (+31,68), …"."""
    partes = ["%s (%s)" % (pav["niveis"][i]["nome"], nivel_txt(pav["niveis"][i]["z"])) for i in t["niveis"]]
    linhas, atual = [], ""
    for p_ in partes:
        if atual and len(atual) + len(p_) + 2 > largura:
            linhas.append(atual + ",")
            atual = p_
        else:
            atual = (atual + ", " + p_) if atual else p_
    if atual:
        linhas.append(atual)
    return linhas


def _cabecalho(p: _Papel, y: float, linhas: Sequence[str], esc: float) -> None:
    """O título (cabeçalho 0, 3,5 mm) e as linhas de baixo (2 mm): na prancha vão para o canto de cima da caixa."""
    atr = p.atr
    for k, txt in enumerate(linhas):
        p.atr = dict(atr, cabecalho=k)
        p.texto(0, y, txt, (3.5 if k == 0 else 2.0) * esc)
        y -= (4.5 if k == 0 else 3.0) * esc
    p.atr = atr


def _rotular(p: _Papel, rotulos: Sequence[Tuple[str, float, float]], h: float, h_papel: float) -> None:
    """As marcas no meio de cada item, sem uma sobre a outra (sobe até 4 linhas; não cabendo, fica sem)."""
    caixas, postos = [], []
    for rotulo, cx, cy in sorted(rotulos, key=lambda r: (r[2], r[1])):
        if any(t == rotulo and math.hypot(cx - x_, cy - y_) < 6.0 * h for t, x_, y_ in postos):
            continue
        larg = 0.75 * h * len(rotulo)
        for passo in range(4):
            dy = passo * 1.3 * h
            caixa = (cx - larg / 2, cy + dy - h / 2, cx + larg / 2, cy + dy + h / 2)
            if not any(_sobrepoe(caixa, cb, 0.2 * h) for cb in caixas):
                caixas.append(caixa)
                postos.append((rotulo, cx, cy))
                p.texto(cx, caixa[1], rotulo, h_papel, "TEXTO", alinhamento="centro")
                break


def _desenhar_pecas(d: Desenho, atr_base: dict, pecas: Sequence[Solido], u, v, u0: float, v0: float, x0: float,
                    y0: float, p: _Papel, camadas_pecas: Optional[Dict[str, str]], camada: str = "") -> int:
    n = 0
    for e in pecas:
        casco = _casco([(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices])
        if len(casco) < 3:
            continue
        m = _marcas(e)
        atr = dict(atr_base, origem=e.id, nome=e.nome or "")
        if m.get("posicao"):
            atr["posicao"] = str(m["posicao"])
        if m.get("conjunto"):
            atr["conjunto"] = str(m["conjunto"])
        pp = _Papel(d, atr, x0, y0)
        cam = camada or (camadas_pecas or {}).get(str(m.get("posicao") or ""), "") or "ACO-FINO"
        pp.polilinha(casco, fechada=True, camada=cam)
        p.pontos.extend(pp.pontos)
        n += 1
    return n


def _desenhar_pilares(p: _Papel, pilares: Sequence[Solido], u, v, u0: float, v0: float, h: float) -> List[Tuple[str, float, float]]:
    """Os pilares em cinza com o nome; devolve (nome, u, v) do centro de cada um, no papel da vista."""
    out = []
    for e in pilares:
        casco = _casco([(_dot(q, u) - u0, _dot(q, v) - v0) for q in e.vertices])
        if len(casco) < 3:
            continue
        p.polilinha(casco, fechada=True, camada="CONCRETO")
        cu = sum(q[0] for q in casco) / len(casco)
        cv = sum(q[1] for q in casco) / len(casco)
        topo = max(q[1] for q in casco)
        p.texto(cu, topo + 0.6 * h, str(e.nome or ""), h, "CONCRETO", alinhamento="centro")
        out.append((str(e.nome or ""), cu, cv))
    return out


def _vista_meta(d: Desenho, nome: str, tipo: str, u, v, w, u0: float, v0: float, larg: float, alt: float,
                x0: float, y0: float, n: int, minimo) -> None:
    d.vistas.append({"origem": list(minimo), "normal": list(w), "acima": list(v), "profundidade": None, "cortar": False,
                     "entidades": None, "rotular": True, "nome": nome, "tipo": tipo, "pecas_cortadas": 0,
                     "pecas_projetadas": n, "largura": round(larg, 1), "altura": round(alt, 1), "canto": [x0, y0],
                     "avisos": [], "ref2d": [round(u0 - _dot(minimo, u), 2), round(v0 - _dot(minimo, v), 2)]})


def _escala_das_plantas(pav: dict, u, v) -> float:
    from nucleo2d.pranchas import escala_normalizada
    maior = 1.0
    for t in pav["tipos"]:
        n = pav["niveis"][t["rep"]]
        us = [_dot(q, u) for e in n["pecas"] for q in e.vertices]
        vs = [_dot(q, v) for e in n["pecas"] for q in e.vertices]
        maior = max(maior, (max(us) - min(us)) / 400.0, (max(vs) - min(vs)) / 250.0)
    return escala_normalizada(maior)


def desenho_de_localizacao_predio(doc: Documento, pav: dict, titulo: str = "Detalhamento – localização",
                                  nomes: Optional[Dict[str, str]] = None,
                                  camadas_pecas: Optional[Dict[str, str]] = None) -> Desenho:
    """A fachada com as lajes e uma planta por tipo de pavimento (ver o módulo)."""
    from nucleo2d.pranchas import escala_normalizada
    niveis = pav["niveis"]
    todas = [e for n in niveis for e in n["pecas"]]
    (u_pl, v_pl), (u_f, v_f, w_f) = _orientacao(todas)
    w_pl = (0.0, 0.0, -1.0)
    esc = _escala_das_plantas(pav, u_pl, v_pl)
    d = Desenho(nome=titulo, escala=esc)
    _registrar_camadas_de_pecas(d)
    _registrar_concreto(d)
    todos = [q for e in todas for q in e.vertices]
    minimo = [min(q[i] for q in todos) for i in range(3)]
    ids_aco = {e.id for e in todas}
    pilares = _pilares(doc, ids_aco)
    atr_base = {"detalhe": "localizacao"}

    # a fachada: todo o aço visto de frente, uma linha por laje com o nome e o nível
    us = [_dot(q, u_f) for q in todos]
    vs = [_dot(q, v_f) for q in todos]
    u0, v0 = min(us), min(vs)
    larg_f, alt_f = max(us) - u0, max(vs) - v0
    # a fachada é alta: na prancha ela desce de escala; as marcas se afastam pelo tamanho que terão lá
    esc_f = max(esc, escala_normalizada(max(alt_f / 420.0, larg_f / 300.0, 1.0)))
    h_f = 2.5 * esc_f
    nome_f = "FACHADA – PAVIMENTOS"
    p = _Papel(d, dict(atr_base, vista=nome_f), 0.0, 0.0)
    n_f = _desenhar_pecas(d, dict(atr_base, vista=nome_f), todas, u_f, v_f, u0, v0, 0.0, 0.0, p, camadas_pecas)
    rot = []
    for rotulo, lista in _itens(todas):
        if not rotulo or len(lista) < 2:
            continue                       # as peças soltas (as fixações) ficam para a planta
        vv = [q for e in lista for q in e.vertices]
        if max(max(q[i] for q in vv) - min(q[i] for q in vv) for i in range(3)) < MENOR_ITEM_LOCALIZACAO:
            continue
        pu = [_dot(q, u_f) - u0 for q in vv]
        pv = [_dot(q, v_f) - v0 for q in vv]
        rot.append(((nomes or {}).get(rotulo) or rotulo, sum(pu) / len(pu), max(pv) + 0.4 * h_f))
    _rotular(p, rot, h_f, 2.5 * esc)
    margem = 6.0 * h_f
    for n in niveis:
        y = n["z"] - v0
        p.linha(-margem, y, larg_f + margem, y, camada="EIXO")
        p.texto(-margem - 0.5 * h_f, y - 0.4 * h_f, "%s  %s" % (n["nome"], nivel_txt(n["z"])), 2.0 * esc, "TEXTO",
                alinhamento="direita")
        p.texto(larg_f + margem + 0.5 * h_f, y - 0.4 * h_f, n.get("tipo", ""), 2.0 * esc, "TEXTO")
    _cabecalho(p, p.extremos[1] - 8.0 * esc_f,
               [nome_f, "o aço de cada laje no lugar de montagem; a linha é o topo da laje (nível)",
                "as plantas de cada tipo de pavimento ao lado"], esc)
    ext = p.extremos
    d.metadados.setdefault("celulas", []).append([round(t, 1) for t in ext])
    _vista_meta(d, nome_f, "lateral", u_f, v_f, w_f, u0, v0, larg_f, alt_f, 0.0, 0.0, n_f, minimo)

    # as plantas, uma por tipo, numa coluna à direita da fachada (de cima para baixo, como o prédio)
    x_pl = ext[2] + 20.0 * esc
    y_topo = ext[3]
    h = 2.5 * esc
    for t in sorted(pav["tipos"], key=lambda t_: -niveis[t_["rep"]]["z"]):
        n = niveis[t["rep"]]
        nome_v = "PLANTA – %s – %02dx" % (t["nome"], len(t["niveis"]))
        pecas = n["pecas"]
        vv = [q for e in pecas for q in e.vertices]
        pil = _pilares_no_nivel(pilares, n["z"], pecas)
        pts = vv + [q for e in pil for q in e.vertices]
        u0 = min(_dot(q, u_pl) for q in pts)
        v0 = min(_dot(q, v_pl) for q in pts)
        larg = max(_dot(q, u_pl) for q in pts) - u0
        alt = max(_dot(q, v_pl) for q in pts) - v0
        y0 = y_topo - alt - 32.0 * esc           # as cadeias de cotas e os nomes dos pilares vão por cima
        p = _Papel(d, dict(atr_base, vista=nome_v), x_pl, y0)
        nn = _desenhar_pecas(d, dict(atr_base, vista=nome_v), pecas, u_pl, v_pl, u0, v0, x_pl, y0, p, camadas_pecas)
        centros = _desenhar_pilares(p, pil, u_pl, v_pl, u0, v0, h)
        rot = []
        extremos_u = []
        for rotulo, lista in _itens(pecas):
            if not rotulo:
                continue
            vv_i = [q for e in lista for q in e.vertices]
            if max(max(q[i] for q in vv_i) - min(q[i] for q in vv_i) for i in range(3)) < MENOR_ITEM_LOCALIZACAO:
                continue
            pu = [_dot(q, u_pl) - u0 for q in vv_i]
            pv = [_dot(q, v_pl) - v0 for q in vv_i]
            ext3 = max(max(q[i] for q in vv_i) - min(q[i] for q in vv_i) for i in range(3))
            if max(max(pu) - min(pu), max(pv) - min(pv)) < 0.3 * ext3:
                continue                    # de topo (o pilar do pórtico visto de cima): a marca fica na fachada
            rot.append(((nomes or {}).get(rotulo) or rotulo, sum(pu) / len(pu), max(pv) + 0.5 * h))
            if len(lista) >= 2:
                extremos_u += [min(pu), max(pu)]
        _rotular(p, rot, h, h)
        # as cotas: ao longo, dos pilares às pontas dos conjuntos; na outra direção, do pilar ao aço
        aco_u = [_dot(q, u_pl) - u0 for q in vv]
        aco_v = [_dot(q, v_pl) - v0 for q in vv]
        cad_u = [c[1] for c in centros] + extremos_u
        if len(cad_u) >= 2 and not p.cadeia_h(cad_u, alt, 8.0):
            p.cadeia_h([c[1] for c in centros] + [min(aco_u), max(aco_u)], alt, 8.0, exigir_espaco=False)
        p.cota_h(min(aco_u), max(aco_u), 0.0, -8.0)
        cad_v = sorted({round(c[2]) for c in centros} | {round(min(aco_v)), round(max(aco_v))})
        if len(cad_v) >= 2:
            p.cadeia_v(cad_v, 0.0, -8.0, exigir_espaco=False)
        linhas = [nome_v] + ["lajes: " + l_ if k == 0 else l_ for k, l_ in enumerate(_listar_niveis(pav, t))]
        linhas.append("marcas no lugar de montagem; pilares do concreto em cinza (referência das cotas)")
        _cabecalho(p, p.extremos[1] - p.dy - 8.0 * esc, linhas, esc)
        ext = p.extremos
        d.metadados["celulas"].append([round(t_, 1) for t_ in ext])
        _vista_meta(d, nome_v, "topo", u_pl, v_pl, w_pl, u0, v0, larg, alt, x_pl, y0, nn, minimo)
        y_topo = ext[1] - 15.0 * esc
    d.metadados["detalhamento"] = {"grupo": "localizacao", "posicoes": [], "itens": {}}
    d.metadados["predio"] = {"tipos": [{"nome": t["nome"], "niveis": [niveis[i]["nome"] for i in t["niveis"]]}
                                       for t in pav["tipos"]]}
    return d


def _juntar(vals: Sequence[float], tol: float = 100.0) -> List[float]:
    """Os valores a até `tol` um do outro viram a média deles."""
    out: List[List[float]] = []
    for x in sorted(vals):
        if out and x - out[-1][-1] <= tol:
            out[-1].append(x)
        else:
            out.append([x])
    return [sum(g) / len(g) for g in out]


def _chapa_atravessada(c: Solido, chapas: Sequence[Solido]) -> Optional[Solido]:
    """A chapa por onde o chumbador passa (as caixas se cruzam)."""
    a, b = _caixa3(c)
    for e in chapas:
        x, y = _caixa3(e)
        if all(x[i] - 2.0 <= b[i] and a[i] - 2.0 <= y[i] for i in range(3)):
            return e
    return None


def _eh_chapa(e) -> bool:
    return _tipo_ifc(e).startswith("IfcPlate") or type(getattr(e, "parametrica", None)).__name__ == "Chapa" \
        or type(e).__name__ == "Chapa"


def _nome_do_chumbador(c: Solido, nomes: Optional[Dict[str, str]]) -> str:
    m = _marcas(c)
    if m.get("posicao"):
        return (nomes or {}).get(str(m["posicao"])) or str(m["posicao"])
    return str(c.nome or "chumbador")


def desenho_de_chumbacao_predio(doc: Documento, pav: dict, titulo: str = "Detalhamento – chumbação",
                                nomes: Optional[Dict[str, str]] = None) -> Desenho:
    """Por tipo de pavimento: os chumbadores com as chapas em que passam, o aço do pavimento em linha fina, os pilares e
    as cadeias de cotas a partir deles; no cabeçalho, quantos chumbadores de cada um por pavimento e em que laje."""
    niveis = pav["niveis"]
    todas = [e for n in niveis for e in n["pecas"]]
    (u, v), _f = _orientacao(todas)
    w = (0.0, 0.0, -1.0)
    com_cb = [t for t in pav["tipos"] if niveis[t["rep"]]["chumbadores"]]
    if not com_cb:
        from nucleo.base import ErroDeDados
        raise ErroDeDados("sem chumbadores no modelo.")
    esc = _escala_das_plantas(dict(pav, tipos=com_cb), u, v)
    d = Desenho(nome=titulo, escala=esc)
    _registrar_camadas_de_pecas(d)
    _registrar_concreto(d)
    todos = [q for e in todas for q in e.vertices]
    minimo = [min(q[i] for q in todos) for i in range(3)]
    pilares = _pilares(doc, {e.id for e in todas})
    lajes = pav.get("lajes") or []
    atr_base = {"detalhe": "chumbacao"}
    h = 2.5 * esc
    y_topo = 0.0
    total_cb = 0
    for t in sorted(com_cb, key=lambda t_: -niveis[t_["rep"]]["z"]):
        n = niveis[t["rep"]]
        cbs = n["chumbadores"]
        nome_v = "CHUMBAÇÃO – %s – %02dx" % (t["nome"], len(t["niveis"]))
        chapas = [e for e in n["pecas"] if _eh_chapa(e)]
        vv = [q for e in n["pecas"] + cbs for q in e.vertices]
        pil = _pilares_no_nivel(pilares, n["z"], list(n["pecas"]) + list(cbs))
        pts = vv + [q for e in pil for q in e.vertices]
        u0 = min(_dot(q, u) for q in pts)
        v0 = min(_dot(q, v) for q in pts)
        larg = max(_dot(q, u) for q in pts) - u0
        alt = max(_dot(q, v) for q in pts) - v0
        y0 = y_topo - alt - 32.0 * esc           # as cadeias de cotas e os nomes dos pilares vão por cima
        p = _Papel(d, dict(atr_base, vista=nome_v), 0.0, y0)
        # o aço do pavimento em linha fina, para achar o lugar; as chapas dos chumbadores e os chumbadores por cima
        atravessadas = {}
        for c in cbs:
            ch = _chapa_atravessada(c, chapas)
            if ch is not None:
                atravessadas[ch.id] = ch
        fino = [e for e in n["pecas"] if e.id not in atravessadas and e.id not in {c.id for c in cbs}]
        nn = _desenhar_pecas(d, dict(atr_base, vista=nome_v), fino, u, v, u0, v0, 0.0, y0, p, None, "ACO-FINO")
        nn += _desenhar_pecas(d, dict(atr_base, vista=nome_v), list(atravessadas.values()), u, v, u0, v0, 0.0, y0, p,
                              None, "CHAPAS-VISTA")
        centros_pil = _desenhar_pilares(p, pil, u, v, u0, v0, h)
        grupos: List[dict] = []
        for c in cbs:
            cx, cy, cz = _centro(c)
            pu, pv = _dot((cx, cy, cz), u) - u0, _dot((cx, cy, cz), v) - v0
            a, b = _caixa3(c)
            diam = max(6.0, min(b[0] - a[0], b[1] - a[1]))
            pp = _Papel(d, dict(atr_base, vista=nome_v, origem=c.id, nome=c.nome or "",
                                **({"posicao": str(_marcas(c)["posicao"])} if _marcas(c).get("posicao") else {})), 0.0, y0)
            pp.circulo(pu, pv, max(diam / 2.0, 0.6 * esc), camada="TIRANTES")
            p.pontos.extend(pp.pontos)
            ch = _chapa_atravessada(c, chapas)
            g = next((g for g in grupos if math.hypot(g["u"] - pu, g["v"] - pv) <= RAIO_GRUPO), None)
            if g is None:
                g = {"u": pu, "v": pv, "n": 0, "chapa": ch, "nomes": collections.Counter(), "su": 0.0, "sv": 0.0}
                grupos.append(g)
            g["n"] += 1
            g["su"] += pu
            g["sv"] += pv
            g["nomes"][_nome_do_chumbador(c, nomes)] += 1
            if g["chapa"] is None:
                g["chapa"] = ch
        for g in grupos:
            g["u"], g["v"] = g["su"] / g["n"], g["sv"] / g["n"]
        # a marca do grupo (a chapa, senão o chumbador) uma vez por fileira: 20 "CH1" iguais só enchiam a planta
        rot, por_chapa, postas = [], collections.Counter(), set()
        for g in sorted(grupos, key=lambda g_: (g_["u"], g_["v"])):
            ch = g["chapa"]
            marca = ((nomes or {}).get(str(_marcas(ch).get("posicao") or "")) or str(_marcas(ch).get("posicao") or "")
                     if ch is not None else "") or g["nomes"].most_common(1)[0][0]
            g["marca"] = marca
            por_chapa[marca] += 1
            if (marca, round(g["v"] / 200.0)) in postas:
                continue
            postas.add((marca, round(g["v"] / 200.0)))
            rot.append((marca, g["u"], g["v"] + 2.0 * h))
        _rotular(p, rot, h, h)
        # as cadeias: ao longo, dos pilares aos grupos; na outra direção, do pilar às fileiras
        # os grupos de uma mesma linha (a perna do pórtico, vista ao longo) contam uma vez: no canto os números se
        # amontoavam
        cad_u = [c_[1] for c_ in centros_pil] + _juntar([g["u"] for g in grupos])
        if len(cad_u) >= 2:
            p.cadeia_h(cad_u, alt, 8.0, exigir_espaco=False)
            p.cota_h(min(cad_u), max(cad_u), alt, 16.0)
        cad_v = sorted({round(c_[2]) for c_ in centros_pil} | {round(v_) for v_ in _juntar([g["v"] for g in grupos])})
        if len(cad_v) >= 2:
            p.cadeia_v(cad_v, 0.0, -8.0, exigir_espaco=False)
        # quantos de cada chumbador por pavimento, em que laje e a que altura do topo dela
        cont: Dict[str, List[Solido]] = collections.OrderedDict()
        for c in sorted(cbs, key=lambda c_: _ordem_natural(_nome_do_chumbador(c_, nomes))):
            cont.setdefault(_nome_do_chumbador(c, nomes), []).append(c)
        linhas = [nome_v] + ["lajes: " + l_ if k == 0 else l_ for k, l_ in enumerate(_listar_niveis(pav, t))]
        for nome_c, lst in cont.items():
            # a altura em relação ao nível do pavimento (o topo da laje): vale para todos os pavimentos do tipo
            zs_c = sorted({round((_centro(c)[2] - n["z"]) / 10.0) * 10.0 for c in lst})
            alt_c = nivel_txt(zs_c[0]) if len(zs_c) == 1 or zs_c[-1] - zs_c[0] < 50.0 else "%s a %s" % (
                nivel_txt(zs_c[0]), nivel_txt(zs_c[-1]))
            linhas.append("%d× %s por pavimento — o meio do chumbador a %s m do nível do pavimento" % (len(lst), nome_c, alt_c))
        if por_chapa:
            linhas.append("grupos: " + ", ".join("%d em %s" % (q, k) for k, q in sorted(por_chapa.items(),
                                                                                     key=lambda kv: _ordem_natural(kv[0]))))
        linhas.append("cotas ao centro dos pilares (cinza) e ao centro de cada grupo de chumbadores, em mm; total da obra: "
                      "%d" % (len(cbs) * len(t["niveis"])))
        total_cb += len(cbs) * len(t["niveis"])
        _cabecalho(p, p.extremos[1] - p.dy - 8.0 * esc, linhas, esc)
        ext = p.extremos
        d.metadados.setdefault("celulas", []).append([round(t_, 1) for t_ in ext])
        _vista_meta(d, nome_v, "topo", u, v, w, u0, v0, larg, alt, 0.0, y0, nn, minimo)
        y_topo = ext[1] - 15.0 * esc
    d.metadados["detalhamento"] = {"grupo": "chumbacao", "posicoes": [], "itens": {}}
    d.metadados["eixos"] = None
    d.metadados["predio"] = {"chumbadores": total_cb}
    return d
