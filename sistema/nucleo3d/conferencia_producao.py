# -*- coding: utf-8 -*-
"""A conferência do modelo antes de detalhar: colisão de verdade, execução das ligações e produção (onda 4 da análise de
14/10/2026, Projeto/ANALISES/Editor-3D).

* **Colisão (F16)** — peça contra peça pela forma, não pela linha de eixo (o "choque" de conferencia_3d só comparava os
  eixos das barras a menos de 40 mm, sem chapa nem parafuso): pontos tirados de dentro de uma peça (a 1 e a 4 mm da
  superfície) que caem dentro da outra e ficam a pelo menos `FUNDURA` da superfície das duas. Encostar (a base na mesa,
  a chapa soldada) e o encaixe com décimos de interferência do IFC (a diagonal U92 dentro do banzo U100, Sala
  Compressores) não contam; atravessar conta, com a espessura da sobreposição (3 mm ou mais = "funda"). Telha e rufo
  ficam de fora (o transpasse). Na Sala Compressores (2 mil peças, 3,6 mil pares próximos): 83 s, 44 sobreposições.
* **Execução (F17)** — a regra "como será executado?" (memória pensar-na-execucao) virando conta: em cada chapa que o
  parafuso atravessa, a distância do furo à borda (NBR 8800, Tabela 14, borda cortada) e o passo entre parafusos
  (2,7·d, 6.3.9); parafuso sem furo na chapa; furo de chapa sem parafuso nem chumbador; espaço para a chave na cabeça e
  na porca (nenhuma peça dentro do anel da chave logo além das pontas).
* **Produção (F18)** — peça sem marca, marca a conferir (a peça mudou depois de copiada), sólido de volume que fica fora
  da lista (sem tipo de peça), conjunto feito no editor sem peça principal.

Cada achado: {"regra", "texto", "ids", "ponto"} — o mesmo formato do Verificar apoios, para o editor mostrar e selecionar.
"""
import collections
import math
from typing import Dict, List, Optional, Sequence

import numpy as np

PASSO_AMOSTRA = 25.0      # mm entre os pontos tirados de cada face
MAX_PONTOS = 4000

REGRAS = {
    "colisao": "Peças se atravessando",
    "colisao_funda": "Peças se atravessando (sobreposição de 3 mm ou mais)",
    "borda": "Furo perto demais da borda da chapa (NBR 8800, Tabela 14)",
    "passo": "Parafusos perto demais um do outro (mínimo 2,7·d)",
    "parafuso_sem_furo": "Parafuso atravessando chapa sem furo",
    "furo_sem_parafuso": "Furo de chapa sem parafuso nem chumbador",
    "chave": "Parafuso sem espaço para a chave",
    "sem_marca": "Peça sem marca de posição",
    "marca_a_conferir": "Peça que mudou depois de copiada (marca a conferir)",
    "fora_da_lista": "Sólido que não entra na lista de materiais (sem tipo de peça)",
    "sem_principal": "Conjunto sem peça principal",
}


# ------------------------------------------------------------------ malha: triângulos e ponto dentro

def _cruz_lote(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """produto vetorial linha a linha, sem o np.cross (que move eixos e copia a cada chamada)"""
    return np.stack([a[:, 1] * b[:, 2] - a[:, 2] * b[:, 1], a[:, 2] * b[:, 0] - a[:, 0] * b[:, 2],
                     a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]], axis=1)


def _normal_newell(P: np.ndarray) -> np.ndarray:
    Q = np.roll(P, -1, axis=0)
    return np.array([np.sum((P[:, 1] - Q[:, 1]) * (P[:, 2] + Q[:, 2])), np.sum((P[:, 2] - Q[:, 2]) * (P[:, 0] + Q[:, 0])),
                     np.sum((P[:, 0] - Q[:, 0]) * (P[:, 1] + Q[:, 1]))])


def _convexa(vs: np.ndarray, f) -> bool:
    """a face plana é convexa? (todas as viradas do contorno para o mesmo lado da normal)"""
    P = vs[list(f)]
    n = _normal_newell(P)
    if not np.any(n):
        return False
    a = np.roll(P, 1, axis=0)
    c = np.roll(P, -1, axis=0)
    giros = _cruz_lote(P - a, c - P) @ n
    return bool(np.all(giros >= -1e-9 * max(1.0, float(np.abs(giros).max()))))


def _orelhas(vs: np.ndarray, f) -> List[tuple]:
    """a face côncava (a ponta do I, a face com o furo costurado): a triangulação do geometria, no sentido da face"""
    from nucleo3d.geometria import _projetar_no_plano, triangular
    try:
        pts2, (_u, _v, fn) = _projetar_no_plano([tuple(vs[i]) for i in f])
        fora = []
        tris = triangular(pts2)
        if not tris:
            raise ValueError("sem triângulos")
        idx = np.asarray(tris, int)
        A, B, C = vs[[f[i] for i in idx[:, 0]]], vs[[f[i] for i in idx[:, 1]]], vs[[f[i] for i in idx[:, 2]]]
        sentido = _cruz_lote(B - A, C - A) @ np.asarray(fn, float)
        for (a, b, c), s in zip(idx, sentido):
            fora.append((f[a], f[b], f[c]) if s >= 0 else (f[a], f[c], f[b]))
        return fora
    except Exception:                                      # noqa: BLE001 — face degenerada: o leque
        return [(f[0], f[k], f[k + 1]) for k in range(1, len(f) - 1)]


class _Malha:
    """A malha de uma peça triangulada uma vez, com a orientação para fora e a caixa. Os triângulos do raio (arestas,
    determinantes) ficam guardados: a mesma peça é testada contra várias vizinhas."""

    def __init__(self, ent):
        vs = np.asarray(ent.vertices, float)
        tris = []
        for f in ent.faces or []:
            if len(f) < 3:
                continue
            if len(f) == 3:
                tris.append(tuple(f))
            elif len(f) == 4 or _convexa(vs, f):
                # o retângulo do perfil e a face convexa: o leque, no sentido da face (a imensa maioria)
                tris.extend((f[0], f[k], f[k + 1]) for k in range(1, len(f) - 1))
            else:
                tris.extend(_orelhas(vs, f))
        # o mesmo triângulo duas vezes (face repetida no IFC) estraga a paridade do raio
        vistos, unicos = set(), []
        for tr in tris:
            k = tuple(sorted(tr))
            if k not in vistos and len(set(tr)) == 3:
                vistos.add(k)
                unicos.append(tr)
        self.id = ent.id
        self.v = vs
        self.t = np.asarray(unicos, int) if unicos else np.zeros((0, 3), int)
        self.caixa = (vs.min(axis=0), vs.max(axis=0)) if len(vs) else (np.zeros(3), np.zeros(3))
        self._raio = None
        if len(self.t):
            a, b, c = vs[self.t[:, 0]], vs[self.t[:, 1]], vs[self.t[:, 2]]
            n = _cruz_lote(b - a, c - a)
            vol = float(np.einsum("ij,ij->i", a, n).sum())
            if vol < 0:                                    # as faces viradas para dentro
                self.t = self.t[:, ::-1]
                n = -n
            nn = np.linalg.norm(n, axis=1)
            self.ok = nn > 1e-9
            self.n = np.where(self.ok[:, None], n / np.maximum(nn, 1e-12)[:, None], 0.0)
        else:
            self.ok = np.zeros(0, bool)
            self.n = np.zeros((0, 3))

    def _dados_do_raio(self):
        if self._raio is None:
            D = np.array([1.0, 1.3e-3, 1.7e-3])
            D = D / np.linalg.norm(D)
            V0, V1, V2 = self.v[self.t[:, 0]], self.v[self.t[:, 1]], self.v[self.t[:, 2]]
            e1, e2 = V1 - V0, V2 - V0
            pv = _cruz_lote(np.broadcast_to(D, e2.shape), e2)
            det = np.einsum("ij,ij->i", e1, pv)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            self._raio = (D, V0, e1, e2, pv, ok, inv, np.minimum(np.minimum(V0, V1), V2), np.maximum(np.maximum(V0, V1), V2))
        return self._raio

    def dentro(self, P: np.ndarray) -> np.ndarray:
        """quais pontos estão dentro da malha (raio com paridade, Möller–Trumbore em lote)"""
        if not len(self.t) or not len(P):
            return np.zeros(len(P), bool)
        D, V0a, e1a, e2a, pva, oka, inva, tmin, tmax = self._dados_do_raio()
        # o raio quase ao longo de +x (levemente torto, para não cair em aresta): só contam os triângulos que estão à
        # frente dos pontos e cobrem o y e o z deles (com a folga do desvio do raio)
        folga = 2e-3 * float(self.caixa[1][0] - min(float(P[:, 0].min()), float(self.caixa[0][0]))) + 1.0
        sel = ((tmax[:, 0] >= P[:, 0].min()) & (tmax[:, 1] >= P[:, 1].min() - 1.0) & (tmin[:, 1] <= P[:, 1].max() + folga)
               & (tmax[:, 2] >= P[:, 2].min() - 1.0) & (tmin[:, 2] <= P[:, 2].max() + folga) & oka)
        if not sel.any():
            return np.zeros(len(P), bool)
        V0, e1, e2, pv, inv = V0a[sel], e1a[sel], e2a[sel], pva[sel], inva[sel]
        dentro = np.zeros(len(P), bool)
        for i0 in range(0, len(P), 512):
            Q = P[i0:i0 + 512]
            tx = Q[:, 0:1] - V0[None, :, 0]
            ty = Q[:, 1:2] - V0[None, :, 1]
            tz = Q[:, 2:3] - V0[None, :, 2]
            u = (tx * pv[None, :, 0] + ty * pv[None, :, 1] + tz * pv[None, :, 2]) * inv
            # qv = tv × e1, escrito à mão (o np.cross em lote gastava metade do tempo em cópias)
            qx = ty * e1[None, :, 2] - tz * e1[None, :, 1]
            qy = tz * e1[None, :, 0] - tx * e1[None, :, 2]
            qz = tx * e1[None, :, 1] - ty * e1[None, :, 0]
            v = (qx * D[0] + qy * D[1] + qz * D[2]) * inv
            t = (qx * e2[None, :, 0] + qy * e2[None, :, 1] + qz * e2[None, :, 2]) * inv
            hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
            dentro[i0:i0 + 512] = (hit.sum(axis=1) % 2) == 1
        return dentro

    def distancia(self, P: np.ndarray) -> np.ndarray:
        """a menor distância de cada ponto à superfície (ponto × triângulo, o ponto mais próximo de Ericson em lote)"""
        if not len(self.t) or not len(P):
            return np.full(len(P), np.inf)
        A, B, C = self.v[self.t[:, 0]], self.v[self.t[:, 1]], self.v[self.t[:, 2]]
        lo, hi = P.min(axis=0) - 50.0, P.max(axis=0) + 50.0
        tmin = np.minimum(np.minimum(A, B), C)
        tmax = np.maximum(np.maximum(A, B), C)
        sel = np.all(tmax >= lo, axis=1) & np.all(tmin <= hi, axis=1)
        if not sel.any():
            sel = np.ones(len(A), bool)
        A, B, C = A[sel], B[sel], C[sel]
        fora = np.full(len(P), np.inf)
        for i0 in range(0, len(P), 256):
            Q = P[i0:i0 + 256][:, None, :]
            ab, ac = (B - A)[None], (C - A)[None]
            ap = Q - A[None]
            d1, d2 = np.einsum("nmj,nmj->nm", np.broadcast_to(ab, ap.shape), ap), np.einsum("nmj,nmj->nm", np.broadcast_to(ac, ap.shape), ap)
            bp = Q - B[None]
            d3, d4 = np.einsum("nmj,nmj->nm", np.broadcast_to(ab, bp.shape), bp), np.einsum("nmj,nmj->nm", np.broadcast_to(ac, bp.shape), bp)
            cp = Q - C[None]
            d5, d6 = np.einsum("nmj,nmj->nm", np.broadcast_to(ab, cp.shape), cp), np.einsum("nmj,nmj->nm", np.broadcast_to(ac, cp.shape), cp)
            va = d3 * d6 - d5 * d4
            vb = d5 * d2 - d1 * d6
            vc = d1 * d4 - d3 * d2
            den = va + vb + vc
            den = np.where(np.abs(den) < 1e-12, 1e-12, den)
            v = vb / den
            w = vc / den
            X = A[None] + ab * v[..., None] + ac * w[..., None]                       # dentro da face
            # as arestas e os vértices (as regiões de Voronoi)
            def no_seg(P0, P1):
                dseg = P1 - P0
                tt = np.clip(np.einsum("nmj,nmj->nm", Q - P0[None], np.broadcast_to(dseg[None], (Q.shape[0],) + dseg.shape)) /
                             np.maximum(np.einsum("mj,mj->m", dseg, dseg), 1e-12)[None], 0.0, 1.0)
                return P0[None] + dseg[None] * tt[..., None]
            Eab, Eac, Ebc = no_seg(A, B), no_seg(A, C), no_seg(B, C)
            dentro_face = (va >= 0) & (vb >= 0) & (vc >= 0)
            cand = [np.where(dentro_face[..., None], X, np.inf), Eab, Eac, Ebc]
            dist = np.min(np.stack([np.linalg.norm(Q - k, axis=2) for k in cand], axis=0), axis=0)
            fora[i0:i0 + 256] = dist.min(axis=1)
        return fora

    def amostras(self, lo, hi, recuo: float, conferir: bool = True) -> np.ndarray:
        """pontos das faces dentro da caixa [lo, hi], `recuo` mm para dentro da peça (conferidos dentro dela, salvo com
        `conferir=False`: a colisão confere só os poucos que caíram dentro da vizinha)"""
        if not len(self.t):
            return np.zeros((0, 3))
        V0, V1, V2 = self.v[self.t[:, 0]], self.v[self.t[:, 1]], self.v[self.t[:, 2]]
        tmin = np.minimum(np.minimum(V0, V1), V2)
        tmax = np.maximum(np.maximum(V0, V1), V2)
        sel = self.ok & np.all(tmax >= lo, axis=1) & np.all(tmin <= hi, axis=1)
        if not sel.any():
            return np.zeros((0, 3))
        a, b, c, n = V0[sel], V1[sel], V2[sel], self.n[sel]
        tam = max(float(np.max(hi - lo)), 1.0)
        passo = min(PASSO_AMOSTRA, max(3.0, tam / 6.0))
        lados = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - a, axis=1)), np.linalg.norm(c - b, axis=1))
        pts = []
        for m in np.unique(np.clip(np.ceil(lados / passo), 1, 30).astype(int)):
            k = np.nonzero(np.clip(np.ceil(lados / passo), 1, 30).astype(int) == m)[0]
            ii, jj = np.meshgrid(np.arange(m + 1), np.arange(m + 1), indexing="ij")
            w1 = ((ii + 1.0 / 3.0) / (m + 1)).ravel()
            w2 = ((jj + 1.0 / 3.0) / (m + 1)).ravel()
            boa = w1 + w2 < 1.0
            w1, w2 = w1[boa], w2[boa]
            Pk = (a[k][:, None, :] + (b[k] - a[k])[:, None, :] * w1[None, :, None] + (c[k] - a[k])[:, None, :] * w2[None, :, None]
                  - n[k][:, None, :] * recuo)
            pts.append(Pk.reshape(-1, 3))
        P = np.concatenate(pts, axis=0)
        P = P[np.all(P >= lo - 1e-6, axis=1) & np.all(P <= hi + 1e-6, axis=1)]
        if len(P) > MAX_PONTOS:
            P = P[np.linspace(0, len(P) - 1, MAX_PONTOS).astype(int)]
        # só os que caíram mesmo dentro da peça: a malha do IFC pode ter face virada, e o "para dentro" dela iria para fora
        return P[self.dentro(P)] if (conferir and len(P)) else P


def _caixas_cruzam(a, b, folga=0.0):
    return bool(np.all(a[0] - folga <= b[1]) and np.all(b[0] - folga <= a[1]))


# ------------------------------------------------------------------ colisão

#: mm: o ponto dentro das duas peças precisa estar pelo menos isto longe da superfície de cada uma — a diagonal U92
#: encaixada no banzo U100 (a boca para o miolo) encosta com décimos de interferência no IFC, e isso é o encaixe, não choque
FUNDURA = 0.4


def colisoes(pecas: Sequence, avisar=None, limite_s: float = 120.0) -> dict:
    """As peças que se atravessam: {"achados": [...], "pares": conferidos, "parcial": bool}."""
    import time
    avisar = avisar or (lambda *a: None)
    from nucleo2d.detalhe.fora_do_aco import eh_telha_ou_painel
    from ifc.importar import funilaria
    malhas = []
    for e in pecas:
        perfil = str(((e.atributos or {}).get("marcas") or {}).get("perfil") or e.nome or "")
        if eh_telha_ou_painel(e) or "TELHA" in perfil.upper() or funilaria(perfil):
            continue                                       # telha e rufo se sobrepõem de propósito (o transpasse)
        try:
            m = _Malha(e)
        except Exception:                                  # noqa: BLE001
            continue
        if len(m.t):
            malhas.append(m)
    # varredura pela coordenada x da caixa
    ordem = sorted(range(len(malhas)), key=lambda i: malhas[i].caixa[0][0])
    pares = []
    ativos: List[int] = []
    for i in ordem:
        x0 = malhas[i].caixa[0][0]
        ativos = [j for j in ativos if malhas[j].caixa[1][0] >= x0 - 1.0]
        for j in ativos:
            if _caixas_cruzam(malhas[i].caixa, malhas[j].caixa, -FUNDURA):
                pares.append((j, i))
        ativos.append(i)
    avisar("%d pares de peças próximas" % len(pares))
    achados = []
    t0 = time.time()
    feitos = 0
    for a_i, b_i in pares:
        if time.time() - t0 > limite_s:
            break
        feitos += 1
        A, B = malhas[a_i], malhas[b_i]
        lo = np.maximum(A.caixa[0], B.caixa[0])
        hi = np.minimum(A.caixa[1], B.caixa[1])
        melhor, ponto = 0.0, None
        for recuo in (1.0, 4.0):                           # a 1 mm (parede fina) e a 4 mm (mesa grossa) da superfície
            for X, Y in ((A, B), (B, A)):
                P = X.amostras(lo, hi, recuo, conferir=False)
                if not len(P):
                    continue
                d = Y.dentro(P)
                if not d.any():
                    continue
                Q = P[d]
                Q = Q[X.dentro(Q)]                         # o "para dentro" de face virada do IFC sai aqui
                if not len(Q):
                    continue
                prof = np.minimum(X.distancia(Q), Y.distancia(Q))
                k = int(np.argmax(prof))
                if prof[k] > melhor:
                    melhor, ponto = float(prof[k]), Q[k]
            if melhor >= 1.5 or (recuo == 1.0 and melhor < FUNDURA):
                break                                      # já é funda; ou nem a 1 mm há sobreposição
        if melhor >= FUNDURA:
            # a espessura da sobreposição (o dobro da distância à superfície mais perto)
            achados.append({"regra": "colisao_funda" if 2 * melhor >= 3.0 else "colisao", "ids": [A.id, B.id],
                            "ponto": [round(float(x), 1) for x in ponto], "profundidade": round(2 * melhor, 1)})
    return {"achados": achados, "pares": len(pares), "conferidos": feitos, "parcial": feitos < len(pares)}


# ------------------------------------------------------------------ execução: parafusos e furos

_NOMES_D = [(12.0, "M12"), (12.7, '1/2"'), (15.875, '5/8"'), (16.0, "M16"), (19.05, '3/4"'), (20.0, "M20"),
            (22.0, "M22"), (22.225, '7/8"'), (24.0, "M24"), (25.4, '1"'), (27.0, "M27"), (30.0, "M30")]


def borda_minima(d: float) -> float:
    """A distância mínima do centro do furo à borda cortada (NBR 8800, Tabela 14), mm"""
    from nucleo import ligacoes
    nome = min(_NOMES_D, key=lambda t: abs(t[0] - d))
    if abs(nome[0] - d) > 1.0:
        return round(1.75 * d, 1)
    tab = ligacoes.BORDA_MINIMA_MM.get(nome[1]) or ligacoes.BORDA_MINIMA_NAO_TABELADA.get(nome[1])
    return float(tab[1]) if tab else round(1.75 * d, 1)


def _parafusos(doc) -> List[dict]:
    """{id, c, a (eixo), L, d, tipo} de cada fixador do modelo: "parafuso" (o gravado pelo editor ou o medido da malha),
    "porca" (a porca solta marca o furo da barra roscada ou do chumbador), "passante" (barra roscada, chumbador,
    tirante — barra ou sólido)"""
    from nucleo2d.detalhe.base import _RE_PASSANTE, _diametro_do_fixador, _eh_furo, _eixos_dos_fixadores, _fixadores
    from nucleo3d.modelo import Barra, Solido
    fix = [f for f in _fixadores(doc) if not _eh_furo(f)]
    ids_fix = {f.id for f in fix}
    passantes_sol = [e for e in doc.entidades.values() if isinstance(e, Solido) and e.id not in ids_fix
                     and _RE_PASSANTE.search(e.nome or "") and len(e.vertices or []) >= 4]
    ids_pass = {e.id for e in passantes_sol}
    eixos = _eixos_dos_fixadores(fix + passantes_sol)
    fora = []
    for f in fix + passantes_sol:
        info = (f.atributos or {}).get("parafuso") or {}
        if info.get("ponto") and info.get("eixo") and info.get("d"):
            a = np.asarray(info["eixo"], float)
            fora.append({"id": f.id, "c": np.asarray(info["ponto"], float), "a": a / (np.linalg.norm(a) or 1.0),
                         "L": float(info.get("L") or 0.0), "d": float(info["d"]), "tipo": "parafuso"})
            continue
        e = eixos.get(f.id)
        if not e:
            continue
        cc, eixo, meio, ext, porca = e
        if f.id in ids_pass:
            tipo, d = "passante", (float(sorted(ext)[0]) if ext else 16.0)
            meio = max(meio, float(max(ext)) / 2.0 if ext else meio)
        else:
            d, _ = _diametro_do_fixador(f, ext)
            tipo = "porca" if porca else "parafuso"
        fora.append({"id": f.id, "c": np.asarray(cc, float), "a": np.asarray(eixo, float), "L": 2.0 * float(meio),
                     "d": float(d), "tipo": tipo})
    for b in doc.entidades.values():
        if isinstance(b, Barra) and (str(b.papel) == "chumbador" or _RE_PASSANTE.search(str(b.perfil) + " " + str(b.nome or ""))):
            p0, p1 = np.asarray(b.inicio, float), np.asarray(b.fim, float)
            a = p1 - p0
            L = float(np.linalg.norm(a))
            if L < 1.0:
                continue
            try:
                from nucleo3d.geometria import resolver_perfil
                d = float(resolver_perfil(b.perfil).d or 16.0)
            except Exception:                              # noqa: BLE001
                d = 16.0
            fora.append({"id": b.id, "c": (p0 + p1) / 2.0, "a": a / L, "L": L, "d": d, "tipo": "passante"})
    return fora


def _quadro(ch):
    o = np.asarray(ch.origem, float)
    ex = np.asarray(ch.eixo_x, float); ex /= np.linalg.norm(ex) or 1.0
    ey = np.asarray(ch.eixo_y, float); ey /= np.linalg.norm(ey) or 1.0
    n = np.cross(ex, ey)
    t = float(ch.espessura or 0.0)
    meio = o if ch.centrada else o + n * t / 2.0
    return o, ex, ey, n, meio, t


def execucao(doc, pecas: Sequence, malhas_por_id: Optional[Dict[str, "_Malha"]] = None) -> List[dict]:
    """Borda, passo, parafuso sem furo, furo sem parafuso e espaço da chave."""
    from shapely.geometry import Point, Polygon
    from nucleo3d.modelo import Chapa
    achados = []
    fix = _parafusos(doc)
    bolts = [b for b in fix if b["tipo"] == "parafuso"]
    if fix:
        C = np.array([b["c"] for b in fix]); A = np.array([b["a"] for b in fix])
        Lm = np.array([b["L"] for b in fix]); Dm = np.array([b["d"] for b in fix])
    chapas = [e for e in doc.entidades.values() if isinstance(e, Chapa) and len(e.contorno or []) >= 3]
    por_chapa: Dict[str, list] = collections.defaultdict(list)
    for ch in chapas:
        o, ex, ey, n, meio, t = _quadro(ch)
        furos = list(ch.furos or [])
        usados = set()
        if fix:
            den = A @ n
            ok = np.abs(den) > 0.5
            s_ = np.where(ok, ((meio - C) @ n) / np.where(ok, den, 1.0), 1e9)
            ok &= np.abs(s_) <= Lm / 2.0 + 1.0 + t / 2.0
            P = C + A * s_[:, None]
            X, Y = (P - o) @ ex, (P - o) @ ey
            cont = np.asarray(ch.contorno, float)
            ok &= ((X >= cont[:, 0].min() - 1) & (X <= cont[:, 0].max() + 1)
                   & (Y >= cont[:, 1].min() - 1) & (Y <= cont[:, 1].max() + 1))
            idx = np.nonzero(ok)[0]
        else:
            idx = []
        if len(idx):
            try:
                poli = Polygon([tuple(q) for q in ch.contorno])
                if not poli.is_valid:
                    poli = poli.buffer(0)
            except Exception:                              # noqa: BLE001
                continue
            fx = np.array([float(f.get("x", 0)) for f in furos])
            fy = np.array([float(f.get("y", 0)) for f in furos])
            fl = np.array([max(float(f.get("largura") or 0), float(f.get("diametro") or 0)) / 2.0 for f in furos])
            fa = np.array([max(float(f.get("altura") or 0), float(f.get("diametro") or 0)) / 2.0 for f in furos])
            for k in idx:
                b, x, y, d = fix[k], float(X[k]), float(Y[k]), float(Dm[k])
                pt = Point(x, y)
                if not poli.buffer(0.5).contains(pt):
                    continue
                # o furo em que o eixo cai (o raio do furo, com folga: o oblongo, a medida da malha do IFC)
                casa = np.nonzero((np.abs(x - fx) <= np.maximum(fl, 2.0)) & (np.abs(y - fy) <= np.maximum(fa, 2.0)))[0] if furos else []
                if not len(casa):
                    if b["tipo"] == "parafuso":
                        achados.append({"regra": "parafuso_sem_furo", "ids": [b["id"], ch.id], "ponto": [round(float(v), 1) for v in P[k]],
                                        "texto": "parafuso Ø%g atravessa %s sem furo" % (d, ch.nome or "a chapa")})
                    continue
                usados.update(int(c_) for c_ in casa)
                if b["tipo"] == "parafuso":
                    por_chapa[ch.id].append((b, x, y, P[k], d))
                    dist = poli.exterior.distance(pt)
                    bm = borda_minima(d)
                    if dist + 0.5 < bm:
                        achados.append({"regra": "borda", "ids": [ch.id, b["id"]], "ponto": [round(float(v), 1) for v in P[k]],
                                        "texto": "%s: furo Ø%g a %.0f mm da borda (mínimo %.0f)" % (ch.nome or "chapa", d, dist, bm)})
        livres = [k for k in range(len(furos)) if k not in usados]
        if livres and furos:
            fk = furos[livres[0]]
            p_ = o + ex * float(fk.get("x", 0)) + ey * float(fk.get("y", 0))
            achados.append({"regra": "furo_sem_parafuso", "ids": [ch.id], "ponto": [round(float(v), 1) for v in p_],
                            "texto": "%s: %d de %d furo(s) sem parafuso, barra ou chumbador" % (ch.nome or "chapa", len(livres), len(furos))})
    # passo entre parafusos da mesma chapa
    for chid, lst in por_chapa.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                bi, xi, yi, Pi, di = lst[i]
                bj, xj, yj, Pj, dj = lst[j]
                dist = math.hypot(xi - xj, yi - yj)
                minimo = 2.7 * max(di, dj)
                if 0.5 < dist < minimo - 0.5:
                    achados.append({"regra": "passo", "ids": [bi["id"], bj["id"], chid], "ponto": [round(float(v), 1) for v in (Pi + Pj) / 2],
                                    "texto": "parafusos a %.0f mm (mínimo %.0f = 2,7·d)" % (dist, minimo)})
    # espaço para a chave: um anel além de cada ponta do parafuso, sem peça dentro
    if malhas_por_id is None:
        malhas_por_id = {}
    caixas = []
    for e in pecas:
        m = malhas_por_id.get(e.id)
        if m is None:
            try:
                m = _Malha(e)
            except Exception:                              # noqa: BLE001
                continue
            malhas_por_id[e.id] = m
        if len(m.t):
            caixas.append(m)
    if caixas:
        cmin = np.array([m.caixa[0] for m in caixas])
        cmax = np.array([m.caixa[1] for m in caixas])
    for b in bolts:
        c, a, L, d = b["c"], b["a"], b["L"], b["d"]
        if L <= 0 or not caixas:
            continue
        u = np.cross(a, [0.0, 0.0, 1.0] if abs(a[2]) < 0.9 else [1.0, 0.0, 0.0]); u /= np.linalg.norm(u)
        v = np.cross(a, u)
        r = 0.9 * d + 6.0                                   # o soquete da chave em volta da porca/cabeça
        pts = []
        for lado in (-1.0, 1.0):
            ponta = c + a * lado * L / 2.0
            for ax in (6.0, 1.5 * d):
                base = ponta + a * lado * ax
                pts.append(base)
                for k in range(8):
                    ang = 2 * math.pi * k / 8
                    pts.append(base + (u * math.cos(ang) + v * math.sin(ang)) * r)
        P = np.asarray(pts)
        lo, hi = P.min(axis=0), P.max(axis=0)
        perto = np.nonzero(np.all(cmax >= lo, axis=1) & np.all(cmin <= hi, axis=1))[0]
        for k in perto:
            m = caixas[k]
            dentro = m.dentro(P)
            if dentro.any():
                achados.append({"regra": "chave", "ids": [b["id"], m.id], "ponto": [round(float(x), 1) for x in P[dentro][0]],
                                "texto": "não há espaço para a chave: a peça vizinha ocupa o lugar da cabeça ou da porca"})
                break
    return achados


# ------------------------------------------------------------------ produção

def producao(doc) -> List[dict]:
    from nucleo3d.producao import pecas_de_producao
    from nucleo3d.modelo import Solido
    from nucleo2d.detalhe.base import TIPOS_ACESSORIO, _tipo_ifc
    achados = []
    pecas = pecas_de_producao(doc)

    def centro(e):
        from nucleo3d.geometria import malha
        try:
            vs = malha(e)[0]
            return [round(sum(q[i] for q in vs) / len(vs), 1) for i in range(3)]
        except Exception:                                  # noqa: BLE001
            return [0.0, 0.0, 0.0]
    sem = [e for e in pecas if not ((e.atributos or {}).get("marcas") or {}).get("posicao")]
    if sem:
        achados.append({"regra": "sem_marca", "ids": [e.id for e in sem], "ponto": centro(sem[0]),
                        "texto": "%d peça(s) sem marca de posição — Editar → Numerar peças" % len(sem)})
    conf = [e for e in pecas if (e.atributos or {}).get("marca_a_conferir")]
    if conf:
        achados.append({"regra": "marca_a_conferir", "ids": [e.id for e in conf], "ponto": centro(conf[0]),
                        "texto": "%d peça(s) mudaram depois de copiadas — Numerar separa as que ficaram diferentes" % len(conf)})
    ids_p = {e.id for e in pecas}
    for e in doc.entidades.values():
        if not isinstance(e, Solido) or e.id in ids_p:
            continue
        a = e.atributos or {}
        if a.get("tipo") in ("cota", "construcao") or a.get("exportar") is False or a.get("furo") or _tipo_ifc(e) in TIPOS_ACESSORIO:
            continue
        if _tipo_ifc(e):
            continue                                       # telha, concreto, guarda-corpo: têm lista própria
        try:
            vol = abs(float(e.volume))
        except Exception:                                  # noqa: BLE001
            vol = 0.0
        if vol > 1000.0:
            achados.append({"regra": "fora_da_lista", "ids": [e.id], "ponto": centro(e),
                            "texto": "%s: sólido sem tipo de peça — Editar → Converter em chapa, ou dê o tipo" % (e.nome or "sólido")})
    inst = collections.defaultdict(list)
    for e in pecas:
        m = (e.atributos or {}).get("marcas") or {}
        if m.get("instancia"):
            inst[m["instancia"]].append(e)
    for k, es in inst.items():
        if not any(((x.atributos or {}).get("marcas") or {}).get("principal") for x in es):
            achados.append({"regra": "sem_principal", "ids": [x.id for x in es], "ponto": centro(es[0]),
                            "texto": "conjunto %s sem peça principal" % (((es[0].atributos or {}).get("marcas") or {}).get("conjunto") or "")})
    return achados


# ------------------------------------------------------------------ tudo

def conferir(doc, quais: Sequence[str] = ("colisao", "execucao", "producao"), ids: Optional[Sequence[str]] = None,
             avisar=None) -> dict:
    """A conferência pedida; `ids` limita a colisão e a execução às peças em volta da seleção."""
    from nucleo3d.producao import pecas_de_producao, _proxy
    pecas_ent = pecas_de_producao(doc)
    proxies = []
    for e in pecas_ent:
        try:
            proxies.append(_proxy(e))
        except Exception:                                  # noqa: BLE001
            continue
    if ids:
        alvo = [p for p in proxies if p.id in set(ids)]
        if alvo:
            lo = np.min([np.min(np.asarray(p.vertices), axis=0) for p in alvo], axis=0) - 300.0
            hi = np.max([np.max(np.asarray(p.vertices), axis=0) for p in alvo], axis=0) + 300.0
            proxies = [p for p in proxies if _caixas_cruzam((np.min(np.asarray(p.vertices), axis=0), np.max(np.asarray(p.vertices), axis=0)), (lo, hi))]
    achados, info = [], {}
    malhas: Dict[str, _Malha] = {}
    if "colisao" in quais:
        r = colisoes(proxies, avisar)
        achados += r["achados"]
        info["colisao"] = {k: r[k] for k in ("pares", "conferidos", "parcial")}
    if "execucao" in quais:
        achados += execucao(doc, proxies, malhas)
    if "producao" in quais:
        achados += producao(doc)
    nome = {e.id: e for e in doc.entidades.values()}
    for a in achados:
        if not a.get("texto"):
            ps = []
            for i in a["ids"]:
                e = nome.get(i)
                m = ((e.atributos or {}).get("marcas") or {}) if e is not None else {}
                ps.append(m.get("posicao") or (e.nome if e is not None else i) or i)
            a["texto"] = "%s × %s" % (ps[0], ps[1]) if len(ps) >= 2 else str(ps[0])
    resumo = collections.Counter(a["regra"] for a in achados)
    return {"achados": achados, "resumo": dict(resumo), "regras": REGRAS, "info": info}
