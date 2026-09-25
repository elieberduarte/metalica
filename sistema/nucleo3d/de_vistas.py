# -*- coding: utf-8 -*-
"""Várias vistas de um projeto recebido (DXF/PDF reconhecido) → um modelo 3D só.

    from nucleo2d import reconhecer
    from nucleo3d import de_vistas
    r = reconhecer.reconhecer(desenho)
    reconhecer.aplicar(desenho, r)
    m = reconhecer.sugerir_montagem(r)
    doc = de_vistas.modelo_das_vistas(desenho, m["montagens"])

Cada vista entra no espaço por uma **montagem**: {vista, usar, u, v, base, origens,
fator, cobertura, conjunto, cortar_nos_eixos, eixos_corte}. O ponto `base` do desenho
vai para cada origem (uma cópia por origem: as tesouras de todos os eixos saem de um
desenho só); o X do desenho segue o vetor `u` do modelo e o Y segue `v`, em mm do modelo
× `fator` (mm do modelo por unidade do desenho — a escala da vista).

Com `cobertura`, a altura de cada ponto é a do banzo superior da tesoura naquele ponto:
a planta de cobertura sobe para o telhado, e as terças apoiam em cima do banzo. Com
`cortar_nos_eixos`, as terças e longarinas são partidas nos eixos das tesouras (uma
peça por vão, como a fábrica corta).

Marcas: posição por perfil, papel e comprimento; conjunto igual para instâncias iguais,
como no IFC do TecnoMETAL — a tesoura (o que não é pilar numa vista em pé) é um
conjunto; cada pilar, terça ou contraventamento é o conjunto dele.

Linha reconhecida só pela forma (perfil vazio, com papel): o perfil vem de `perfis`
(papel → nome no catálogo), senão de `reconhecer_geo.PERFIS_PADRAO`.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo2d.desenho import Desenho
from nucleo3d.de_desenho import CAMADA_DO_PAPEL, Peca, _eh_contorno_de_chapa, _segmentos, peca_da_entidade
from nucleo3d.modelo import Barra, Camada, Documento

__all__ = ["modelo_das_vistas"]


def _vetor(v, padrao) -> Tuple[float, float, float]:
    try:
        x = [float(c) for c in (v if v is not None else padrao)][:3]
    except (TypeError, ValueError):
        x = list(padrao)
    while len(x) < 3:
        x.append(0.0)
    n = math.sqrt(sum(c * c for c in x)) or 1.0
    return (x[0] / n, x[1] / n, x[2] / n)


def _vetorial(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _cruza(p, q, a, b) -> Optional[float]:
    """Parâmetro t em p→q onde a reta a-b corta a reta do trecho, ou None (paralelas)."""
    r = (q[0] - p[0], q[1] - p[1])
    s = (b[0] - a[0], b[1] - a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    return ((a[0] - p[0]) * s[1] - (a[1] - p[1]) * s[0]) / den


class _Cobertura:
    """Altura do banzo superior da tesoura em cada ponto da planta."""

    def __init__(self, mont: dict, linhas: Sequence[Tuple[tuple, tuple, Peca]]):
        from nucleo import catalogo
        f = float(mont.get("fator") or 1.0)
        bx, by = (float(c) for c in (mont.get("base") or (0, 0)))
        self.u = _vetor(mont.get("u"), (1, 0, 0))
        o = (mont.get("origens") or [[0, 0, 0]])[0]
        self.o = tuple(float(c) for c in (list(o) + [0, 0, 0])[:3])
        self.trechos = []
        self.h_banzo = 0.0
        tem_banzo = any(p.papel == "banzo" for _a, _b, p in linhas)
        for a, b, peca in linhas:
            if peca.papel == "pilar" or (tem_banzo and peca.papel != "banzo"):
                continue
            sa, za = (a[0] - bx) * f, (a[1] - by) * f
            sb, zb = (b[0] - bx) * f, (b[1] - by) * f
            if abs(sb - sa) < 1e-6:
                continue
            self.trechos.append((min(sa, sb), max(sa, sb), sa, za, sb, zb))
            if peca.papel == "banzo":
                p = catalogo.perfil_de(peca.perfil)
                if p is not None:
                    self.h_banzo = max(self.h_banzo, float(p.d or 0))

    def z(self, x: float, y: float) -> Optional[float]:
        if not self.trechos:
            return None
        s = (x - self.o[0]) * self.u[0] + (y - self.o[1]) * self.u[1]
        s = min(max(s, min(t[0] for t in self.trechos)), max(t[1] for t in self.trechos))
        zs = [za + (zb - za) * (s - sa) / (sb - sa)
              for lo, hi, sa, za, sb, zb in self.trechos if lo - 1e-6 <= s <= hi + 1e-6]
        return self.o[2] + max(zs) if zs else None


def _linhas_por_vista(desenho: Desenho, perfis: Optional[Dict[str, str]] = None) -> Dict[int, List[tuple]]:
    from nucleo2d.reconhecer_geo import PERFIS_PADRAO
    rec = (desenho.metadados or {}).get("reconhecimento") or {}
    perfis = dict(perfis or {})
    caixas = {int(v["id"]): v.get("caixa") for v in rec.get("vistas") or []}

    def vista_de(ent) -> Optional[int]:
        r = (ent.atributos or {}).get("reconhecido") or {}
        if "vista" in r:
            return int(r["vista"])
        pts = ent.pontos()
        if not pts:
            return None
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for vid, c in caixas.items():
            if c and c[0][0] <= cx <= c[1][0] and c[0][1] <= cy <= c[1][1]:
                return vid
        return None

    out: Dict[int, List[tuple]] = collections.defaultdict(list)
    for ent in desenho.entidades.values():
        peca = peca_da_entidade(ent, desenho)
        if peca is None:
            bruto = (ent.atributos or {}).get("peca")
            if isinstance(bruto, dict) and not bruto.get("perfil") and bruto.get("papel") \
                    and bruto.get("papel") != "chapa":
                papel = str(bruto["papel"])
                nome = perfis.get(papel) or PERFIS_PADRAO.get(papel) or PERFIS_PADRAO["barra"]
                peca = Peca(perfil=nome, papel=papel, aco=str(bruto.get("aco") or ""),
                            rotacao=float(bruto.get("rotacao") or 0.0))
        if peca is None or _eh_contorno_de_chapa(ent, peca):
            continue
        vid = vista_de(ent)
        if vid is None:
            continue
        mult = int(((ent.atributos or {}).get("peca") or {}).get("mult") or 1)
        for a, b in _segmentos(ent):
            if math.dist(a, b) >= 1e-6:
                out[vid].append((tuple(a), tuple(b), peca, mult, ent))
    return out


def modelo_das_vistas(desenho: Desenho, montagens: Sequence[dict], *, aco_padrao: str = "ASTM A572 Gr.50",
                      nome: str = "", doc: Optional[Documento] = None,
                      perfis: Optional[Dict[str, str]] = None) -> Documento:
    """Documento 3D com as peças de todas as vistas usadas (veja o módulo). `perfis`:
    papel → perfil do catálogo para as linhas reconhecidas sem perfil escrito."""
    from nucleo import catalogo
    perfis = {str(k): str(v).strip() for k, v in (perfis or {}).items() if str(v).strip()}
    for papel, nome_p in perfis.items():
        if catalogo.perfil_de(nome_p) is None:
            raise ErroDeDados("perfil não encontrado no catálogo para %s: \"%s\"." % (papel, nome_p))
    doc = doc or Documento(nome=nome or desenho.nome or "Modelo")
    for nome_camada in set(CAMADA_DO_PAPEL.values()):
        doc.camadas.setdefault(nome_camada, Camada(nome=nome_camada))
    por_vista = _linhas_por_vista(desenho, perfis)
    usadas = [m for m in montagens if m.get("usar", True) and int(m["vista"]) in por_vista]
    if not usadas:
        raise ErroDeDados("nenhuma vista com peças para montar: reconheça as peças do desenho primeiro "
                          "(ou marque as linhas com \"Peça do catálogo…\").")

    def em_pe(m):
        return abs(_vetor(m.get("v"), (0, 0, 1))[2]) > 0.9

    # a cobertura sai da primeira vista em pé com banzo (senão, da primeira em pé)
    cobertura = None
    candidatas = [m for m in usadas if em_pe(m)]
    candidatas.sort(key=lambda m: not any(p.papel == "banzo" for _a, _b, p, _m, _e in por_vista[int(m["vista"])]))
    if candidatas:
        m = candidatas[0]
        cobertura = _Cobertura(m, [(a, b, p) for a, b, p, _m, _e in por_vista[int(m["vista"])]])

    pecas: List[dict] = []
    for m in usadas:
        vid = int(m["vista"])
        f = float(m.get("fator") or 1.0)
        u = _vetor(m.get("u"), (1, 0, 0))
        v = _vetor(m.get("v"), (0, 0, 1))
        n = _vetorial(u, v)
        bx, by = (float(c) for c in (m.get("base") or (0, 0)))
        origens = [tuple(float(c) for c in (list(o) + [0, 0, 0])[:3]) for o in (m.get("origens") or [[0, 0, 0]])]
        sobe = bool(m.get("cobertura")) and cobertura is not None and not em_pe(m)
        cortes = [((float(e["a"][0]), float(e["a"][1])), (float(e["b"][0]), float(e["b"][1])))
                  for e in (m.get("eixos_corte") or [])] if m.get("cortar_nos_eixos") else []
        ls = por_vista[vid]
        # vista deitada (planta) e vista de uma peça: cada peça é o conjunto dela
        sozinhas = not em_pe(m) or len(ls) <= 1
        for k, o in enumerate(origens):
            for a, b, peca, mult, ent in ls:
                trechos = [(a, b)]
                if cortes and peca.papel in ("terça", "terca", "longarina"):
                    ts = sorted(t for ea, eb in cortes for t in [_cruza(a, b, ea, eb)]
                                if t is not None and 0.02 < t < 0.98)
                    pts = [a] + [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in ts] + [b]
                    trechos = list(zip(pts, pts[1:]))
                for pa, pb in trechos:
                    def P(p, o=o):
                        x, y = (p[0] - bx) * f, (p[1] - by) * f
                        q = [o[i] + u[i] * x + v[i] * y for i in range(3)]
                        if sobe:
                            z = cobertura.z(q[0], q[1])
                            if z is not None:
                                extra = 0.0
                                if peca.papel in ("terça", "terca"):
                                    pp = catalogo.perfil_de(peca.perfil)
                                    extra = cobertura.h_banzo / 2 + (float(pp.d or 0) / 2 if pp else 0.0)
                                q[2] = z + extra
                        return tuple(round(c, 2) for c in q)
                    p0, p1 = P(pa), P(pb)
                    if math.dist(p0, p1) < 1.0:
                        continue
                    base = {"peca": peca, "vista": vid, "inst": k, "ent": ent,
                            "sozinha": sozinhas or peca.papel == "pilar"}
                    if mult > 1:
                        # perfil duplo (2U, 2L): costas com costas, com a chapa de nó entre eles
                        pp = catalogo.perfil_de(peca.perfil)
                        afast = (float(pp.bf or 50) if pp else 50.0) / 2 + 4.0
                        for sinal, rot in ((1, 0.0), (-1, 180.0)):
                            d = tuple(n[i] * afast * sinal for i in range(3))
                            pecas.append(dict(base, p0=tuple(p0[i] + d[i] for i in range(3)),
                                              p1=tuple(p1[i] + d[i] for i in range(3)), rot=rot))
                    else:
                        pecas.append(dict(base, p0=p0, p1=p1, rot=peca.rotacao))
    # a mesma barra desenhada em duas vistas (o pilar no pórtico e na fachada) entra uma vez
    vistos: Dict[tuple, dict] = {}
    unicas: List[dict] = []
    repetidas = 0
    for p in pecas:
        a = tuple(int(round(c / 10.0)) for c in p["p0"])
        b = tuple(int(round(c / 10.0)) for c in p["p1"])
        chave = (p["peca"].perfil, min(a, b), max(a, b))
        if chave in vistos:
            repetidas += 1
            continue
        vistos[chave] = p
        unicas.append(p)
    pecas = unicas
    # posições: mesmo perfil, papel e comprimento (ao mm)
    grupos: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for p in pecas:
        p["L"] = math.dist(p["p0"], p["p1"])
        p["chave"] = (p["peca"].perfil, p["peca"].papel, round(p["L"]))
        grupos[p["chave"]].append(p)
    ordem = sorted(grupos.items(), key=lambda kv: (-len(kv[1]), -kv[0][2], str(kv[0][0])))
    posicao_de = {chave: "P%d" % i for i, (chave, _l) in enumerate(ordem, start=1)}
    marca_conj: Dict[tuple, str] = {}

    def conj_de(p) -> str:
        chave = ("pos", posicao_de[p["chave"]]) if p["sozinha"] else ("vista", p["vista"])
        if chave not in marca_conj:
            marca_conj[chave] = "M%d" % (len(marca_conj) + 1)
        return marca_conj[chave]

    peso = 0.0
    for p in sorted(pecas, key=lambda p: (p["sozinha"], p["vista"], p["inst"])):
        peca = p["peca"]
        perfil = catalogo.perfil_de(peca.perfil)
        nome_perfil = perfil.nome if perfil else peca.perfil
        b = Barra(nome=nome_perfil, inicio=p["p0"], fim=p["p1"], perfil=nome_perfil, rotacao=p["rot"],
                  papel=peca.papel, aco=peca.aco or aco_padrao, camada=CAMADA_DO_PAPEL.get(peca.papel, "Vigas"),
                  material=peca.material or "")
        kg = round((perfil.massa if perfil else 0.0) * p["L"] / 1000.0, 3)
        peso += kg
        b.atributos = {
            "tipo_ifc": b.tipo_ifc(),
            "marcas": {"posicao": posicao_de[p["chave"]], "conjunto": conj_de(p), "perfil": nome_perfil},
            "origem": {"desenho": desenho.nome, "entidade": p["ent"].id, "camada_2d": p["ent"].camada,
                       "vista": p["vista"], "instancia": p["inst"]},
            "peso_kg": kg,
        }
        doc.add(b)
    doc.metadados["de_desenho"] = {
        "desenho": desenho.nome, "vistas": [int(m["vista"]) for m in usadas], "barras": len(pecas), "chapas": 0,
        "pecas": len(pecas), "posicoes": len(posicao_de), "conjuntos": len(marca_conj), "peso_kg": round(peso, 1),
        "repetidas": repetidas,
        "montagens": [dict(m) for m in usadas],
        "perfis_por_papel": perfis,
    }
    return doc
