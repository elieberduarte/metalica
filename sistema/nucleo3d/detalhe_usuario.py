# -*- coding: utf-8 -*-
"""O detalhe do usuário: a ligação montada à mão no editor 3D, salva como modelo e aplicada de novo em outras barras
(F14 da análise de 14/10/2026, Projeto/ANALISES/Editor-3D) — "o que não está na biblioteca o usuário cria uma vez e
reaproveita".

Salvar: as peças do detalhe (chapas, cantoneiras, parafusos, sólidos) e uma ou duas barras de referência (a viga em
que a chapa de topo está, o pilar da base). As peças ficam gravadas no sistema da ponta da barra de referência mais
perto delas: (u, v) os eixos da seção da barra, w para dentro dela a partir da ponta — o mesmo detalhe numa barra
igual, em qualquer lugar e direção, cai no mesmo lugar dela. Vão junto o corte da ponta da barra (a chapa de topo
corta a viga), as soldas definidas com a barra e se as peças entram no conjunto dela.

Aplicar: nas barras escolhidas (na ponta de baixo/de cima, se a referência era um pilar; na ponta pedida, se não),
devolve as entidades novas e as alterações das barras, para o editor aplicar com desfazer; as marcas se acertam pelo
numerar (a peça igual fica com a mesma posição).

A biblioteca é um arquivo da pasta de dados (detalhes-3d.json), da empresa, como o banco de detalhes.
"""
import copy
import json
import math
import os
import re
import time
from typing import Dict, List, Optional, Sequence

from nucleo.base import ErroDeDados

ARQUIVO = "detalhes-3d.json"


# ------------------------------------------------------------------ vetores e o sistema da ponta

def _sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def _add(a, b): return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def _mul(a, k): return [a[0] * k, a[1] * k, a[2] * k]
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return [a[0] / n, a[1] / n, a[2] / n] if n > 1e-12 else [0.0, 0.0, 0.0]


class _Sistema:
    """O sistema da ponta de uma barra: origem no nó, u e v da seção, w para dentro da barra (destro)."""

    def __init__(self, barra, ponta: str):
        from nucleo3d.geometria import base_local
        u, v, w = base_local(barra.direcao, barra.rotacao or 0.0)
        if ponta == "inicio":
            self.o, self.u, self.v, self.w = list(barra.inicio), list(u), list(v), list(w)
        else:                                              # girada 180° em torno de v: continua destro
            self.o, self.u, self.v, self.w = list(barra.fim), _mul(list(u), -1.0), list(v), _mul(list(w), -1.0)

    def para_local(self, p):
        d = _sub(p, self.o)
        return [round(_dot(d, self.u), 4), round(_dot(d, self.v), 4), round(_dot(d, self.w), 4)]

    def vetor_local(self, d):
        return [round(_dot(d, self.u), 6), round(_dot(d, self.v), 6), round(_dot(d, self.w), 6)]

    def para_mundo(self, q):
        return _add(self.o, _add(_add(_mul(self.u, q[0]), _mul(self.v, q[1])), _mul(self.w, q[2])))

    def vetor_mundo(self, q):
        return _add(_add(_mul(self.u, q[0]), _mul(self.v, q[1])), _mul(self.w, q[2]))


def _ponta_perto(barra, pontos) -> str:
    c = [sum(p[i] for p in pontos) / len(pontos) for i in range(3)]
    return "inicio" if math.dist(barra.inicio, c) <= math.dist(barra.fim, c) else "fim"


def _rotacao_para(direcao, u_desejado) -> float:
    """a rotação da barra de direção `direcao` cujo eixo u da seção é `u_desejado`"""
    from nucleo3d.geometria import base_local
    u0, v0, _ = base_local(direcao, 0.0)
    return round(math.degrees(math.atan2(_dot(u_desejado, v0), _dot(u_desejado, u0))) % 360.0, 4)


# ------------------------------------------------------------------ transformar uma entidade

def _transformar(d: dict, ponto, vetor) -> dict:
    """a entidade (dict) com a geometria levada por `ponto` (pontos) e `vetor` (direções)"""
    d = copy.deepcopy(d)
    t = d.get("tipo")
    if t == "barra":
        from nucleo3d.geometria import base_local
        u, _v, _w = base_local(_sub(d["fim"], d["inicio"]), float(d.get("rotacao") or 0.0))
        d["inicio"], d["fim"] = ponto(d["inicio"]), ponto(d["fim"])
        d["rotacao"] = _rotacao_para(_sub(d["fim"], d["inicio"]), vetor(list(u)))
        for k in ("cortes_inicio", "cortes_fim"):
            d[k] = [{"normal": vetor(c["normal"]), "ponto": vetor(c.get("ponto") or [0, 0, 0])} for c in (d.get(k) or [])]
    elif t == "chapa":
        d["origem"] = ponto(d["origem"])
        d["eixo_x"], d["eixo_y"] = vetor(d["eixo_x"]), vetor(d["eixo_y"])
    elif t == "solido":
        d["vertices"] = [ponto(p) for p in d.get("vertices") or []]
    a = d.get("atributos") or {}
    for chave in ("parafuso", "furo"):
        info = a.get(chave)
        if isinstance(info, dict):
            info = dict(info)
            if info.get("ponto") is not None:
                info["ponto"] = ponto(info["ponto"])
            if info.get("eixo") is not None:
                info["eixo"] = vetor(info["eixo"])
            a[chave] = info
    d["atributos"] = a
    return d


# ------------------------------------------------------------------ salvar

def montar(doc, ids_pecas: Sequence[str], ids_refs: Sequence[str], nome: str) -> dict:
    """A definição do detalhe: as peças no sistema da ponta da referência (e a segunda referência, se houver)."""
    from nucleo3d.modelo import Barra
    from nucleo3d.geometria import malha
    refs = [doc.entidades[i] for i in ids_refs if isinstance(doc.entidades.get(i), Barra)]
    if not 1 <= len(refs) <= 2:
        raise ErroDeDados("o detalhe precisa de uma ou duas barras de referência (a viga, o pilar)")
    pecas = [doc.entidades[i] for i in ids_pecas if i in doc.entidades and i not in {r.id for r in refs}]
    if not pecas:
        raise ErroDeDados("selecione as peças do detalhe (chapas, cantoneiras, parafusos) junto com a barra de referência")
    pontos = [q for e in pecas for q in malha(e)[0]]
    if len(refs) == 2:
        refs = _chegada_primeiro(*refs)                    # a referência é a que chega (a viga), a outra é o apoio
    r1 = refs[0]
    ponta = _ponta_no_eixo(r1, refs[1]) if len(refs) == 2 else _ponta_perto(r1, pontos)
    S = _Sistema(r1, ponta)
    m_r1 = (r1.atributos or {}).get("marcas") or {}
    inst_r1 = m_r1.get("instancia")
    lista = []
    for e in pecas:
        d = _transformar(e.dict(), S.para_local, S.vetor_local)
        a = d.get("atributos") or {}
        m = dict(a.get("marcas") or {})
        a["detalhe_no_conjunto"] = bool(inst_r1 and m.get("instancia") == inst_r1) or bool(
            not inst_r1 and m.get("conjunto") and m.get("conjunto") == m_r1.get("conjunto"))
        for k in ("instancia", "principal", "conjunto"):
            m.pop(k, None)
        a["marcas"] = m
        for k in ("ligacao", "marca_a_conferir", "detalhe_usuario"):
            a.pop(k, None)
        d["atributos"] = a
        d.pop("id", None)
        lista.append(d)
    pos_pecas = {((e.atributos or {}).get("marcas") or {}).get("posicao") for e in pecas} - {None, ""}
    soldas_ref = {k: v for k, v in ((r1.atributos or {}).get("soldas") or {}).items() if k in pos_pecas}
    chave_c = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ref = {"perfil": r1.perfil, "papel": r1.papel, "vertical": abs(r1.direcao[2]) > 0.7,
           "ponta_alta": (r1.inicio[2] if ponta == "inicio" else r1.fim[2]) > (r1.fim[2] if ponta == "inicio" else r1.inicio[2]) + 1.0,
           "cortes": [{"normal": S.vetor_local(c["normal"]), "ponto": S.vetor_local(c.get("ponto") or [0, 0, 0])}
                      for c in (getattr(r1, chave_c) or [])],
           "recorte": float(getattr(r1, rec) or 0.0), "soldas": soldas_ref}
    defin = {"id": _id(nome), "nome": str(nome or "Detalhe")[:120], "criado": time.strftime("%Y-%m-%dT%H:%M"),
             "pecas": lista, "ref": ref, "n_refs": len(refs)}
    if len(refs) == 2:
        r2 = refs[1]
        defin["ref2"] = {"perfil": r2.perfil, "direcao": S.vetor_local(r2.direcao), "ponto": S.para_local(list(r2.inicio))}
    return defin


def _id(nome: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(nome or "detalhe").lower()).strip("-")[:40] or "detalhe"
    return "%s-%s" % (base, time.strftime("%Y%m%d%H%M%S"))


# ------------------------------------------------------------------ aplicar

def aplicar(doc, defin: dict, ids_alvo: Sequence[str], ponta: str = "auto") -> dict:
    """O detalhe nas barras `ids_alvo` (com duas referências: a primeira é a do detalhe e a segunda diz a ponta). Não
    altera o `doc`: devolve {"novas", "alterar", "avisos"}."""
    from nucleo3d.modelo import Barra, Documento
    from nucleo3d import producao
    from nucleo3d.ligacoes3d import _copia_de_trabalho
    trabalho = _copia_de_trabalho(doc, ids_alvo)          # o recebido não muda (só as barras do detalhe copiadas a fundo)
    alvos = [trabalho.entidades[i] for i in ids_alvo if isinstance(trabalho.entidades.get(i), Barra)]
    if not alvos:
        raise ErroDeDados("selecione a barra em que o detalhe vai (a mesma função da barra de referência dele)")
    ref = defin.get("ref") or {}
    avisos: List[str] = []
    grupos = []
    if int(defin.get("n_refs") or 1) == 2:
        if len(alvos) != 2:
            raise ErroDeDados("este detalhe liga duas barras: selecione as duas (%s e %s)"
                              % (ref.get("perfil"), (defin.get("ref2") or {}).get("perfil")))
        a, b = _chegada_primeiro(*alvos)
        grupos.append((a, [_ponta_no_eixo(a, b)]))
    else:
        for a in alvos:
            if ponta in ("inicio", "fim"):
                pontas = [ponta]
            elif ponta == "ambas":
                pontas = ["inicio", "fim"]
            elif ref.get("vertical") and abs(a.direcao[2]) > 0.7:
                alta = "inicio" if a.inicio[2] > a.fim[2] else "fim"
                baixa = "fim" if alta == "inicio" else "inicio"
                pontas = [alta if ref.get("ponta_alta") else baixa]
            else:
                pontas = ["inicio"]
            grupos.append((a, pontas))
    novas, alterar = [], {}
    for alvo, pontas in grupos:
        if str(alvo.perfil) != str(ref.get("perfil")):
            avisos.append("%s: perfil %s, o detalhe foi feito numa %s — confira se as peças encaixam"
                          % (alvo.nome or alvo.id, alvo.perfil, ref.get("perfil")))
        for p in pontas:
            S = _Sistema(alvo, p)
            aplic = "D" + format(int(time.time() * 1000) % 10 ** 10, "x") + format(len(novas), "x")
            mb = dict((alvo.atributos or {}).get("marcas") or {})
            inst = mb.get("instancia")
            if any((d.get("atributos") or {}).get("detalhe_no_conjunto") for d in defin["pecas"]) and not inst and not mb.get("conjunto"):
                inst = "c" + aplic
                mb.update(instancia=inst, conjunto="")
                mb.setdefault("principal", True)
                alvo.atributos = dict(alvo.atributos or {}, marcas=mb)
                alterar.setdefault(alvo.id, {})["atributos"] = alvo.atributos
            for d0 in defin["pecas"]:
                d = _transformar(d0, S.para_mundo, S.vetor_mundo)
                a = d.get("atributos") or {}
                m = dict(a.get("marcas") or {})
                if a.pop("detalhe_no_conjunto", False):
                    if inst:
                        m.update(instancia=inst, conjunto="")
                    else:
                        m["conjunto"] = mb.get("conjunto")
                a["marcas"] = m
                a["detalhe_usuario"] = {"id": defin.get("id"), "nome": defin.get("nome"), "aplicacao": aplic, "barra": alvo.id}
                d["atributos"] = a
                e = Documento.de_dict({"entidades": [d]}).entidades
                ent = next(iter(e.values()))
                trabalho.add(ent)
                novas.append(ent)
            # a ponta da barra como a da referência (o corte da chapa de topo) e as soldas com as peças
            chave_c = "cortes_inicio" if p == "inicio" else "cortes_fim"
            rec = "recorte_inicio" if p == "inicio" else "recorte_fim"
            campos = {}
            if ref.get("cortes"):
                campos[chave_c] = [{"normal": [round(x, 6) for x in S.vetor_mundo(c["normal"])],
                                    "ponto": [round(x, 3) for x in S.vetor_mundo(c["ponto"])]} for c in ref["cortes"]]
                campos[rec] = 0.0
            elif ref.get("recorte"):
                campos[rec] = float(ref["recorte"])
            for k, v in campos.items():
                setattr(alvo, k, copy.deepcopy(v))
                alterar.setdefault(alvo.id, {})[k] = copy.deepcopy(v)
            if ref.get("soldas"):
                at = dict(alvo.atributos or {})
                at["soldas"] = dict(at.get("soldas") or {}, **copy.deepcopy(ref["soldas"]))
                alvo.atributos = at
                alterar.setdefault(alvo.id, {})["atributos"] = at
    # as marcas: a peça igual fica com a posição dela; o conjunto se acerta
    r = producao.numerar(trabalho)
    da = {e.id for e in novas} | {a.id for a, _ in grupos}
    for i, patch in r["mudancas"].items():
        if i not in da:
            continue
        e = trabalho.entidades[i]
        at = dict(e.atributos or {})
        for k, v in patch.items():
            if v is None:
                at.pop(k, None)
            else:
                at[k] = v
        e.atributos = at
        if not any(n is e for n in novas):
            alterar.setdefault(i, {})["atributos"] = at
    return {"novas": [e.dict() for e in novas], "alterar": alterar, "avisos": avisos}


def _dist_ponta_eixo(a, b) -> float:
    w = _norm(_sub(list(b.fim), list(b.inicio)))

    def dist(q):
        r = _sub(list(q), list(b.inicio))
        return math.sqrt(max(0.0, _dot(r, r) - _dot(r, w) ** 2))
    return min(dist(a.inicio), dist(a.fim))


def _chegada_primeiro(a, b):
    """(a que chega, o apoio): a barra com a ponta mais perto do eixo da outra"""
    return [a, b] if _dist_ponta_eixo(a, b) <= _dist_ponta_eixo(b, a) else [b, a]


def _ponta_no_eixo(a, b) -> str:
    """a ponta de `a` mais perto do eixo de `b` (a ponta da viga que chega no pilar)"""
    w = _norm(_sub(list(b.fim), list(b.inicio)))

    def dist(q):
        r = _sub(list(q), list(b.inicio))
        return math.sqrt(max(0.0, _dot(r, r) - _dot(r, w) ** 2))
    return "inicio" if dist(a.inicio) <= dist(a.fim) else "fim"


# ------------------------------------------------------------------ a biblioteca

def _arquivo(pasta: str) -> str:
    return os.path.join(pasta, ARQUIVO)


def lista(pasta: str) -> List[dict]:
    try:
        with open(_arquivo(pasta), encoding="utf-8") as f:
            return list((json.load(f) or {}).get("detalhes") or [])
    except (OSError, ValueError):
        return []


def resumo(pasta: str) -> List[dict]:
    """os detalhes sem as peças (para a lista do editor)"""
    return [{"id": d["id"], "nome": d.get("nome"), "criado": d.get("criado"), "n_refs": d.get("n_refs", 1),
             "perfil": (d.get("ref") or {}).get("perfil"), "pecas": len(d.get("pecas") or [])} for d in lista(pasta)]


def _gravar(pasta: str, detalhes: List[dict]) -> None:
    os.makedirs(pasta, exist_ok=True)
    tmp = _arquivo(pasta) + ".parcial"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"formato": 1, "detalhes": detalhes}, f, ensure_ascii=False)
    os.replace(tmp, _arquivo(pasta))


def salvar(pasta: str, defin: dict) -> dict:
    ds = [d for d in lista(pasta) if d.get("id") != defin["id"]]
    ds.append(defin)
    _gravar(pasta, ds)
    return defin


def obter(pasta: str, did: str) -> dict:
    d = next((x for x in lista(pasta) if x.get("id") == did), None)
    if d is None:
        raise ErroDeDados("detalhe %s não encontrado na biblioteca" % did)
    return d


def excluir(pasta: str, did: str) -> bool:
    ds = lista(pasta)
    fica = [d for d in ds if d.get("id") != did]
    if len(fica) == len(ds):
        return False
    _gravar(pasta, fica)
    return True
