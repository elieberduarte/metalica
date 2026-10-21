# -*- coding: utf-8 -*-
"""Reanalisar estrutura: o modelo antigo passa pelas regras de hoje, sem remontar (19/10/2026).

O usuário, no CD Bom Dia (19/10): "a ideia principal dessa reanálise é pegar esse tipo de erro de concepção que já
corrigimos em outros modelos". O modelo montado antes das regras novas fica com os defeitos que elas já evitam nos modelos
novos — e remontar perde as edições do 3D. Aqui o modelo como está passa, em ordem, por:

1. peças repetidas — duas barras iguais (mesmo perfil, mesmo giro) com as duas pontas no mesmo lugar: fica uma;
2. tocos soltos — o pedaço de alma de treliça (montante, diagonal) que não encosta em nada nas duas pontas, curto: sai
   (no CD Bom Dia: as sobras de 278–453 mm abaixo do banzo de baixo e acima do de cima, nos oitões);
3. alma com a ponta solta — a ponta não encosta em nada: se a peça atravessa um banzo antes da ponta, é cortada no eixo
   dele (a diagonal passando do banzo); se a ponta solta está dentro do painel (entre os banzos) e a peça é curta, sai (as
   diagonais de 532 mm penduradas nos nós da TF1); fora disso só aponta (a ponta pode estar num apoio que não está no
   modelo — o pilar de concreto);
4. as regras de montagem das tesouras (nucleo3d/regras_trelica.corrigir_modelo: boca do U, lado da cantoneira, encaixe no
   banzo, nó no eixo, degrau, terça torcida, perfil do banzo na ponta);
5. o peso gravado nas barras pela regra de hoje (o peso dos dobrados de 14/10: a lista já sai certa, o 3D mostrava o
   antigo).

E aponta, sem mudar: as almas que se cruzam no meio do painel (o X que não é contraventamento) e o que ainda sobra no
Verificar apoios (peça voando, ponta sem apoio, terça em balanço…).

Peça bloqueada no 3D não é tocada. A função muda o documento recebido (a cópia do servidor) e devolve as mudanças
({"novas", "alterar", "remover"}) para o editor aplicar numa entrada só de desfazer, mais a prévia por regra.
"""
from __future__ import annotations

import collections
import datetime
import math
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from nucleo3d.conferencia_3d import CRUZAM_POR_PROJETO, _dist_seg, _seg_seg, repetidas as _pares_repetidos

#: a versão das regras: sobe quando entra regra nova aqui (o modelo grava a que passou — metadados.reanalise.versao)
VERSAO_REGRAS = 4        # 2 (21/10): a 2.9 — o banzo 2U composto (Hangar), que a versão 1 pulava; 3 (21/10): o U simples
                         # com alma 2L volta à 2.2 + 2.5 (a leitura "alma no plano" desfeita) e a ponta do composto no final;
                         # 4 (21/10): a presilha segue o par (3.3 — no Posto, 731 de 7 mil tortas ou furando as abas)

#: (chave, título, "corrige" | "aponta", explicação)
REGRAS = [
    ("repetidas", "Peças repetidas no mesmo lugar", "corrige",
     "duas barras iguais (mesmo perfil e giro) com as duas pontas no mesmo lugar: fica uma (a que tem marca)"),
    ("tocos", "Tocos de alma soltos", "corrige",
     "pedaço de montante ou diagonal que não encosta em nada nas duas pontas: sai"),
    ("pontas_soltas", "Alma com a ponta solta", "corrige",
     "a diagonal que passa do banzo é cortada no eixo dele; a sobra pendurada dentro do painel sai"),
    ("tesouras", "Regras de montagem das tesouras", "corrige",
     "boca do U (também o 2U composto, 2.9), lado da cantoneira, encaixe no banzo, nó no eixo do banzo, "
     "degrau, terça torcida, perfil da ponta, presilha no par (3.3)"),
    ("peso", "Peso das barras pela regra de hoje", "corrige",
     "o peso gravado em cada barra refeito pelo catálogo (peso dos dobrados de 14/10)"),
    ("cruzadas", "Almas cruzadas no meio do painel", "aponta",
     "duas peças da alma se atravessando longe dos nós: conferir com o projeto"),
    ("fora_dos_nos", "Alma com a ponta fora de nó (a conferir)", "aponta",
     "a ponta cai no meio de outra alma, sem banzo ali: sobra ou escora de projeto — escolha o grupo para ver as peças"),
    ("pontas_a_conferir", "Alma com a ponta solta (a conferir)", "aponta",
     "a ponta não encosta em nada, mas a peça é longa ou a ponta está fora do painel: pode ser apoio fora do modelo"),
    ("apoios", "Ainda no Verificar apoios", "aponta",
     "o que sobra depois das correções: peça voando, ponta sem apoio, terça em balanço…"),
]
CORRIGE = [k for k, _t, tipo, _e in REGRAS if tipo == "corrige"]

ALMA = {"montante", "diagonal", "extremidade"}
TOL_ENCOSTA = 100.0      # mm: a ponta a até isso do eixo de outra peça encosta nela (o nó; a 3.2 leva ao eixo até 100)
TOCO_MAX = 1000.0        # mm: o pedaço solto até esse tamanho é sobra; maior, só aponta
SOBRA_MIN = 30.0         # mm: o que passa do banzo menos que isso não é sobra (a face do perfil)
MAX_ACHADOS = 400        # por regra, na prévia


def _barras(doc) -> list:
    from nucleo3d.modelo import Barra
    return [e for e in doc.entidades.values() if isinstance(e, Barra)]


def _livre(e) -> bool:
    return not getattr(e, "bloqueada", False)


def _papel_alma(e) -> Optional[str]:
    a = getattr(e, "atributos", None) or {}
    if a.get("secao_dupla") or a.get("um_lado_so"):
        return None
    pt = str(a.get("papel_trelica") or "")
    if pt in ALMA:
        return pt
    pp = str(getattr(e, "papel", "") or "")
    return pp if pp in ALMA else None


def _e_banzo(e) -> bool:
    a = getattr(e, "atributos", None) or {}
    return str(a.get("papel_trelica") or "").startswith("banzo") or str(getattr(e, "papel", "") or "") == "banzo"


def _nome(e) -> str:
    return str(e.nome or e.papel or "barra")


def _pt(p) -> List[int]:
    return [round(v) for v in p]


class _Grade:
    """as barras numa grade de 2 m no plano, para achar as vizinhas de um ponto sem olhar o modelo inteiro"""
    CEL = 2000.0

    def __init__(self, barras: Sequence, outras: Sequence = ()):
        self.g: Dict[tuple, list] = collections.defaultdict(list)
        for e in barras:
            self._por(e, (e.inicio, e.fim))
        # chapas e sólidos: a caixa deles (a ponta que encosta numa chapa de ligação está ligada)
        self.caixas: Dict[tuple, list] = collections.defaultdict(list)
        for e in outras:
            cx = _caixa(e)
            if cx is None:
                continue
            lo, hi = cx
            for gx in range(int(lo[0] // self.CEL), int(hi[0] // self.CEL) + 1):
                for gy in range(int(lo[1] // self.CEL), int(hi[1] // self.CEL) + 1):
                    self.caixas[(gx, gy)].append((e, lo, hi))

    def _por(self, e, pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        for gx in range(int(min(xs) // self.CEL), int(max(xs) // self.CEL) + 1):
            for gy in range(int(min(ys) // self.CEL), int(max(ys) // self.CEL) + 1):
                self.g[(gx, gy)].append(e)

    def perto(self, p) -> list:
        cx, cy = int(p[0] // self.CEL), int(p[1] // self.CEL)
        vistos, out = set(), []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for e in self.g.get((cx + dx, cy + dy), ()):
                    if id(e) not in vistos:
                        vistos.add(id(e))
                        out.append(e)
        return out

    def na_caixa(self, p, tol: float) -> bool:
        cx, cy = int(p[0] // self.CEL), int(p[1] // self.CEL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for _e, lo, hi in self.caixas.get((cx + dx, cy + dy), ()):
                    if all(lo[k] - tol <= p[k] <= hi[k] + tol for k in range(3)):
                        return True
        return False


def _caixa(e):
    from nucleo3d.modelo import Chapa, Solido
    try:
        if isinstance(e, Solido) and e.vertices:
            vs = e.vertices
        elif isinstance(e, Chapa):
            from nucleo3d.geometria import malha_chapa
            vs = malha_chapa(e)[0]
        else:
            return None
        lo = [min(v[k] for v in vs) for k in range(3)]
        hi = [max(v[k] for v in vs) for k in range(3)]
        return lo, hi
    except Exception:                                    # noqa: BLE001 — a peça sem malha não liga nada
        return None


def _encosta(p, e, grade: _Grade, fora: set, zmin: float) -> bool:
    """a ponta p (da barra e) encosta em alguma outra peça: outra barra a até TOL_ENCOSTA do eixo, a caixa de uma chapa
    ou sólido, ou o chão"""
    if p[2] <= zmin + 5.0:
        return True
    for o in grade.perto(p):
        if o is e or id(o) in fora:
            continue
        if _dist_seg(p, o.inicio, o.fim) <= TOL_ENCOSTA:
            return True
    return grade.na_caixa(p, TOL_ENCOSTA)


def _corte_no_banzo(e, k_solta: int, grade: _Grade, fora: set) -> Optional[tuple]:
    """a peça atravessa o eixo de um banzo antes da ponta solta (k_solta): (ponto no eixo do banzo, quanto passa, banzo)
    — o banzo cruzado no miolo dele (longe das pontas: a ponta da treliça, onde o montante de extremidade desce até o
    apoio, não conta)"""
    a, b = (e.fim, e.inicio) if k_solta == 0 else (e.inicio, e.fim)     # a = a ponta presa, b = a solta
    L = math.dist(a, b)
    melhor = None
    for o in grade.perto(b):
        if o is e or id(o) in fora or not _e_banzo(o):
            continue
        d, s, t, c = _seg_seg(a, b, o.inicio, o.fim)
        Lo = math.dist(o.inicio, o.fim)
        if d > TOL_ENCOSTA or Lo < 1.0 or s * L < TOL_ENCOSTA or s >= 1.0 or min(t * Lo, (1.0 - t) * Lo) < 150.0:
            continue                                       # (a ponta presa no próprio banzo é o caso de sair do nó)
        passa = (1.0 - s) * L
        if passa < SOBRA_MIN:
            continue
        if melhor is None or s < melhor[1]:
            melhor = (tuple(round(v, 3) for v in c), s, round(passa), o)
    return (melhor[0], melhor[2], melhor[3]) if melhor else None


def _no_miolo_do_banzo(p, grade: _Grade, fora: set) -> bool:
    """o ponto está num nó de banzo (a até 1,5 × TOL_ENCOSTA do eixo) e o banzo continua dos dois lados dele (300 mm
    para cada lado, em qualquer trecho — a emenda de dois trechos é miolo; a ponta da treliça, onde o montante de
    extremidade desce até o apoio, não é)"""
    def tem_banzo(q) -> bool:
        return any(id(o) not in fora and _e_banzo(o) and _dist_seg(q, o.inicio, o.fim) <= 1.5 * TOL_ENCOSTA
                   for o in grade.perto(q))
    for o in grade.perto(p):
        if id(o) in fora or not _e_banzo(o):
            continue
        a, b = o.inicio, o.fim
        L = math.dist(a, b)
        if L < 1.0 or _dist_seg(p, a, b) > 1.5 * TOL_ENCOSTA:
            continue
        u = [(b[k] - a[k]) / L for k in range(3)]
        if tem_banzo([p[k] + 300.0 * u[k] for k in range(3)]) and tem_banzo([p[k] - 300.0 * u[k] for k in range(3)]):
            return True
    return False


def _entre_banzos(p, grade: _Grade, fora: set) -> bool:
    """o ponto está dentro do painel: há banzo passando acima e abaixo dele (na planta, a até 150 mm da linha do banzo)"""
    acima = abaixo = False
    for o in grade.perto(p):
        if id(o) in fora or not _e_banzo(o):
            continue
        a, b = o.inicio, o.fim
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 < 1.0:
            continue
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
        if not (0.0 <= t <= 1.0):
            continue
        qx, qy = a[0] + dx * t, a[1] + dy * t
        if math.hypot(p[0] - qx, p[1] - qy) > 150.0:
            continue
        z = a[2] + (b[2] - a[2]) * t
        if z > p[2] + 20.0:
            acima = True
        elif z < p[2] - 20.0:
            abaixo = True
    return acima and abaixo


def _achado(e, texto, ponto=None, ids=None) -> dict:
    return {"ids": list(ids or [e.id]), "texto": texto, "ponto": _pt(ponto if ponto is not None else e.inicio)}


# ------------------------------------------------------------------ as regras que corrigem
def _repetidas(doc, achados: list) -> None:
    barras = [e for e in _barras(doc)]
    tirar = set()
    for r in _pares_repetidos(barras):
        e, f = (doc.entidades.get(i) for i in r["ids"])
        if e is None or f is None or e.id in tirar or f.id in tirar:
            continue
        if str(e.perfil) != str(f.perfil):
            continue                                       # perfis diferentes: decisão do projeto (o Verificar aponta)
        ae, af = e.atributos or {}, f.atributos or {}
        if any(x.get(k) for x in (ae, af) for k in ("cantoneira_dupla", "secao_dupla", "perfil_duplo")):
            continue                                       # o par de cantoneiras / o perfil duplo: são duas de propósito
        if abs(((float(e.rotacao or 0) - float(f.rotacao or 0)) + 180.0) % 360.0 - 180.0) > 1.0:
            continue                                       # o mesmo perfil girado (2U costas com costas)
        marca = lambda x: bool(((x.atributos or {}).get("marcas") or {}).get("posicao"))  # noqa: E731
        sai = f if (marca(e) or not marca(f)) else e
        if not _livre(sai):
            sai = e if sai is f else f
            if not _livre(sai):
                continue
        tirar.add(sai.id)
        fica = f if sai is e else e
        achados.append(_achado(sai, "%s repetida sobre %s (%s)" % (_nome(sai), _nome(fica), sai.perfil),
                               r["ponto"], [sai.id, fica.id]))
    for i in tirar:
        doc.entidades.pop(i, None)


def _soltas(doc, achados_tocos: list, achados_pontas: list, achados_conferir: list,
            tocos: bool = True, pontas: bool = True) -> None:
    """as regras 2 e 3 juntas, em duas passadas (tirar um toco pode soltar a ponta de outro); a regra não escolhida
    não muda nada (e não aponta)"""
    from nucleo3d.modelo import Barra
    outras = [e for e in doc.entidades.values() if not isinstance(e, Barra)]
    conferir_ids = set()
    for _passada in range(2):
        barras = _barras(doc)
        if not barras:
            return
        zmin = min(min(e.inicio[2], e.fim[2]) for e in barras)
        grade = _Grade(barras, outras)
        fora: set = set()
        tirar, cortar = [], []
        for e in barras:
            if not _livre(e) or _papel_alma(e) is None or id(e) in fora:
                continue
            L = math.dist(e.inicio, e.fim)
            if L < 1.0:
                continue
            soltas = [k for k, p in ((0, e.inicio), (1, e.fim)) if not _encosta(p, e, grade, fora, zmin)]
            if len(soltas) == 2:
                if not tocos:
                    continue
                if L <= TOCO_MAX:
                    fora.add(id(e))
                    tirar.append(e)
                    achados_tocos.append(_achado(e, "%s (%s, %d mm): não encosta em nada" % (_nome(e), e.perfil, L),
                                                 _meio(e)))
                elif e.id not in conferir_ids:
                    conferir_ids.add(e.id)
                    achados_conferir.append(_achado(e, "%s (%d mm): as duas pontas não encostam em nada" % (_nome(e), L),
                                                    _meio(e)))
                continue
            if len(soltas) != 1 or not pontas:
                continue
            k = soltas[0]
            p = e.inicio if k == 0 else e.fim
            corte = _corte_no_banzo(e, k, grade, fora)
            if corte:
                ponto, passa, banzo = corte
                cortar.append((e, k, ponto))
                achados_pontas.append(_achado(e, "%s: passava %d mm do %s — cortada no eixo do banzo"
                                              % (_nome(e), passa, _nome(banzo)), p))
            elif L <= TOCO_MAX and _entre_banzos(p, grade, fora):
                fora.add(id(e))
                tirar.append(e)
                achados_pontas.append(_achado(e, "%s (%d mm): pendurada, a ponta solta no meio do painel" % (_nome(e), L), p))
            elif L <= TOCO_MAX and _no_miolo_do_banzo(e.fim if k == 0 else e.inicio, grade, fora):
                # sai do nó para fora da treliça (a diagonal de 939 mm abaixo do banzo de baixo da TC1, a de 278 mm
                # da TF1): a ponta presa no miolo de um banzo, a solta fora do painel — longe da ponta da treliça, onde o
                # montante de extremidade desce até o apoio
                fora.add(id(e))
                tirar.append(e)
                achados_pontas.append(_achado(e, "%s (%d mm): sai do nó para fora da treliça, a ponta solta" % (_nome(e), L), p))
            elif e.id not in conferir_ids:
                conferir_ids.add(e.id)
                achados_conferir.append(_achado(e, "%s (%d mm): a ponta não encosta em nada" % (_nome(e), L), p))
        for e in tirar:
            doc.entidades.pop(e.id, None)
        for e, k, ponto in cortar:
            if k == 0:
                e.inicio = ponto
                e.cortes_inicio = []
            else:
                e.fim = ponto
                e.cortes_fim = []
        if not tirar and not cortar:
            break
    vivos = set(doc.entidades)
    achados_conferir[:] = [a for a in achados_conferir if a["ids"][0] in vivos]


def _meio(e):
    return tuple((e.inicio[k] + e.fim[k]) / 2.0 for k in range(3))


def _tesouras(doc, achados: list) -> dict:
    from nucleo3d import regras_trelica
    travadas = {e.id: (e, e.dict()) for e in doc.entidades.values() if not _livre(e)}
    antes = {e.id: e.dict() for e in _barras(doc)}
    r = regras_trelica.corrigir_modelo(doc)
    # o que o corrigir_modelo mudou nos atributos (marca a conferir, trocas de perfil) vem na resposta: volta à peça
    for i, campos in (r.get("alterar") or {}).items():
        e = doc.entidades.get(i)
        if e is not None and "atributos" in campos:
            e.atributos = dict(campos["atributos"])
    # a peça bloqueada volta como estava (o corrigir_modelo não sabe de bloqueio)
    for i, (e, d) in travadas.items():
        doc.entidades[i] = e
        for k, v in d.items():
            if k not in ("tipo", "id") and hasattr(e, k):
                setattr(e, k, v)
    for i, d0 in antes.items():
        if i in travadas:
            continue
        e = doc.entidades.get(i)
        if e is None:
            achados.append(_achado_d(d0, "trecho de alma todo dentro do banzo — sai (regra 3.1b)"))
            continue
        d1 = e.dict()
        o_que = []
        if d1.get("perfil") != d0.get("perfil"):
            o_que.append("perfil %s → %s (1.2/1.4: o topo do painel e a ponta com o perfil do banzo)"
                         % (d0.get("perfil"), d1.get("perfil")))
        if d1.get("rotacao") != d0.get("rotacao"):
            o_que.append("girada (boca do U / lado da cantoneira / terça torcida)")
        if d1.get("inicio") != d0.get("inicio") or d1.get("fim") != d0.get("fim"):
            o_que.append("ponta levada ao nó (eixo do banzo, degrau, face da platibanda)")
        if d1.get("cortes_inicio") != d0.get("cortes_inicio") or d1.get("cortes_fim") != d0.get("cortes_fim"):
            o_que.append("encaixada no banzo (3.1)")
        if o_que:
            achados.append(_achado_d(d0, "; ".join(o_que)))
    return r.get("resumo") or {}


def _achado_d(d: dict, o_que: str) -> dict:
    """o achado de uma peça pelo dicionário dela (a que saiu do modelo não tem mais objeto)"""
    ini, fim = d.get("inicio") or (0, 0, 0), d.get("fim") or (0, 0, 0)
    return {"ids": [d["id"]], "ponto": _pt([(ini[k] + fim[k]) / 2.0 for k in range(3)]),
            "texto": "%s (%s): %s" % (d.get("nome") or d.get("papel") or "peça", d.get("perfil") or "", o_que)}


def _peso(doc, achados: list) -> None:
    from nucleo3d.geometria import peso_barra
    for e in _barras(doc):
        a = e.atributos or {}
        if "peso_kg" not in a or not _livre(e):
            continue
        try:
            novo = round(peso_barra(e), 2)
            velho = float(a.get("peso_kg") or 0.0)
        except Exception:                                # noqa: BLE001 — perfil fora do catálogo: fica como está
            continue
        if novo <= 0.0 or abs(novo - velho) <= max(0.05, 0.005 * novo):
            continue
        a = dict(a)
        a["peso_kg"] = novo
        e.atributos = a
        achados.append(_achado(e, "%s (%s): %.2f → %.2f kg" % (_nome(e), e.perfil, velho, novo), _meio(e)))


# ------------------------------------------------------------------ as que só apontam
def _cruzadas(doc, achados: list) -> None:
    almas = [e for e in _barras(doc) if _papel_alma(e) and str(e.papel or "") not in CRUZAM_POR_PROJETO]
    grade = _Grade(almas)
    vistos = set()
    for e in almas:
        for o in grade.perto(_meio(e)):
            if o is e or (id(o), id(e)) in vistos or (id(e), id(o)) in vistos:
                continue
            vistos.add((id(e), id(o)))
            d, s, t, c = _seg_seg(e.inicio, e.fim, o.inicio, o.fim)
            if d > 20.0:
                continue
            Le, Lo = math.dist(e.inicio, e.fim), math.dist(o.inicio, o.fim)
            if min(s * Le, (1 - s) * Le) < 150.0 or min(t * Lo, (1 - t) * Lo) < 150.0:
                continue                                   # no nó (ponta com ponta, ponta no meio da outra)
            wa = [(e.fim[k] - e.inicio[k]) / Le for k in range(3)]
            wb = [(o.fim[k] - o.inicio[k]) / Lo for k in range(3)]
            if abs(sum(wa[k] * wb[k] for k in range(3))) > 0.995:
                continue                                   # paralelas (a repetida / o trecho é de outra regra)
            achados.append(_achado(e, "%s cruza %s no meio do painel" % (_nome(e), _nome(o)), c, [e.id, o.id]))


def _fora_dos_nos(doc, achados: list) -> None:
    """a alma com a ponta no meio de outra alma, sem banzo ali e sem ser a ponta de outra peça — fora de nó (as diagonais
    de 532 mm da TF1 do CD Bom Dia, do nó da emenda até o meio da diagonal vizinha). Pode ser de projeto (a escora do
    painel em K): só aponta, em grupos de peças iguais (perfil e tamanho) para escolher o grupo inteiro"""
    barras = _barras(doc)
    if not barras:
        return
    grade = _Grade(barras)
    for e in barras:
        if _papel_alma(e) is None:
            continue
        L = math.dist(e.inicio, e.fim)
        if L < 1.0:
            continue
        for p in (e.inicio, e.fim):
            perto = [o for o in grade.perto(p) if o is not e and _dist_seg(p, o.inicio, o.fim) <= TOL_ENCOSTA]
            if not perto or any(_e_banzo(o) or _papel_alma(o) is None for o in perto):
                continue                                   # solta (outra regra), num banzo, ou numa peça de fora (pilar)
            if any(min(math.dist(p, o.inicio), math.dist(p, o.fim)) <= TOL_ENCOSTA for o in perto):
                continue                                   # na ponta de outra alma: o nó da alma (o K, o montante partido)
            a = _achado(e, "%s (%s, %d mm): a ponta cai no meio de %s, fora de nó"
                        % (_nome(e), e.perfil, L, _nome(perto[0])), p)
            a["grupo"] = "%s · %s · %d mm" % (str(e.nome or "").split(" ")[0], e.perfil, round(L / 10.0) * 10)
            achados.append(a)
            break


def _apoios(doc, achados: list) -> None:
    from nucleo3d import apoios
    try:
        v = apoios.verificar(doc, posicao=False)
    except Exception as ex:                              # noqa: BLE001
        achados.append({"ids": [], "ponto": [0, 0, 0], "texto": "o Verificar apoios não rodou: %s" % ex})
        return
    for a in v.get("achados") or []:
        if a.get("regra") in ("posicao_trelica", "repetida"):
            continue                                       # as duas já são regras daqui
        achados.append({"ids": list(a.get("ids") or []), "ponto": list(a.get("ponto") or [0, 0, 0]),
                        "texto": a.get("texto") or a.get("regra"), "regra": a.get("regra")})


# ------------------------------------------------------------------ a reanálise
def reanalisar(doc, quais: Optional[Iterable[str]] = None, avisar: Optional[Callable[[str, float], None]] = None) -> dict:
    """passa o modelo pelas regras escolhidas (`quais`: as chaves de REGRAS que corrigem; None = todas) e devolve
    {"regras": [{chave, titulo, tipo, explicacao, n, achados, grupos}], "novas": [], "alterar": {id: campos},
     "remover": [ids], "resumo": {...}, "carimbo"}. O documento recebido muda (é a cópia do servidor). `avisar(etapa,
    fração)` conta o andamento (a barra das telas); as regras das tesouras são a parte demorada (~80 % do tempo)"""
    sel = set(CORRIGE if quais is None else quais)
    av = avisar or (lambda _e, _f: None)
    antes = {i: e.dict() for i, e in doc.entidades.items()}
    ach: Dict[str, list] = {k: [] for k, *_ in REGRAS}
    resumo_tes = {}
    if "repetidas" in sel:
        av("peças repetidas (1 de 6)…", 0.01)
        _repetidas(doc, ach["repetidas"])
    if sel & {"tocos", "pontas_soltas"}:
        av("tocos e pontas soltas das treliças (2 de 6)…", 0.03)
        t, p, c = [], [], []
        _soltas(doc, t, p, c, tocos="tocos" in sel, pontas="pontas_soltas" in sel)
        ach["tocos"], ach["pontas_soltas"], ach["pontas_a_conferir"] = t, p, c
    if "tesouras" in sel:
        av("regras de montagem das tesouras (3 de 6) — a parte demorada…", 0.08)
        resumo_tes = _tesouras(doc, ach["tesouras"])
    if "peso" in sel:
        av("peso das barras (4 de 6)…", 0.8)
        _peso(doc, ach["peso"])
    av("almas cruzadas e fora de nó (5 de 6)…", 0.82)
    _cruzadas(doc, ach["cruzadas"])
    _fora_dos_nos(doc, ach["fora_dos_nos"])
    av("o que ainda sobra no Verificar apoios (6 de 6)…", 0.86)
    _apoios(doc, ach["apoios"])
    # as mudanças, peça por peça
    remover = [i for i in antes if i not in doc.entidades]
    alterar = {}
    for i, e in doc.entidades.items():
        d0 = antes.get(i)
        if d0 is None:
            continue
        d1 = e.dict()
        mud = {k: v for k, v in d1.items() if k not in ("id", "tipo") and d0.get(k) != v}
        if mud:
            alterar[i] = mud
    novas = [e.dict() for i, e in doc.entidades.items() if i not in antes]
    regras = []
    for k, titulo, tipo, expl in REGRAS:
        lista = ach[k]
        grupos: Dict[str, list] = collections.OrderedDict()
        for a in lista:
            if a.get("grupo"):
                grupos.setdefault(a["grupo"], []).extend(a["ids"][:1])
        regras.append({"chave": k, "titulo": titulo, "tipo": tipo, "explicacao": expl, "n": len(lista),
                       "achados": lista[:MAX_ACHADOS], "mais": max(0, len(lista) - MAX_ACHADOS),
                       # os grupos de peças iguais, inteiros (a prévia escolhe o grupo de uma vez)
                       "grupos": sorted(({"grupo": g, "n": len(ids), "ids": ids} for g, ids in grupos.items()),
                                        key=lambda x: -x["n"])})
    return {"regras": regras, "novas": novas, "alterar": alterar, "remover": remover, "versao": VERSAO_REGRAS,
            "resumo": {"pecas": len(antes), "alteradas": len(alterar), "removidas": len(remover),
                       "tesouras": resumo_tes,
                       "corrigir": sum(len(ach[k]) for k in CORRIGE if k in sel),
                       "apontar": sum(len(ach[k]) for k, _t, tipo, _e in REGRAS if tipo == "aponta")},
            "carimbo": {"versao": VERSAO_REGRAS, "em": datetime.date.today().isoformat(), "regras": sorted(sel)}}


def precisa(doc_ou_metadados) -> bool:
    """o modelo passou pelas regras de hoje? (metadados.reanalise.versao)"""
    md = doc_ou_metadados if isinstance(doc_ou_metadados, dict) else getattr(doc_ou_metadados, "metadados", {}) or {}
    try:
        return int((md.get("reanalise") or {}).get("versao") or 0) < VERSAO_REGRAS
    except (TypeError, ValueError):
        return True
