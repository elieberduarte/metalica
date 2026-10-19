"""A cobertura retrátil no modelo 3D — as mesmas tesouras e a mesma sanfona da análise, aberta ou retraída.

O pedido (06/10, Kaefer): "trazer as mesmas configurações do modelo estrutural para o 3D e ter uma forma de visualizar
ela aberta e retraída… até para ver como as cargas se comportam em ambas as situações". A conta das posições é a da
análise (`analise_estrutural._cobertura_movel`): a tesoura lançada é o molde, copiada nas n posições ao longo das
vigas-trilho (aberta: o comprimento todo; retraída: empilhada na ponta), e a sanfona é o X entre tesouras vizinhas nos
dois planos laterais (topo do montante externo ↔ apoio da vizinha). Assim o 3D, as listas e a análise falam da mesma
cobertura: 38 × T1 nas duas situações — só a posição muda.

As peças geradas levam `atributos["cobertura_movel"] = {"k", "situacao"}`; as tesouras guardam a planta de onde o molde
veio, para a sincronização da planta trocá-las junto (e gerar de novo). A análise usa só a primeira (k = 0) como molde.
"""
from __future__ import annotations

import copy
import re
from typing import List, Optional, Sequence, Tuple

from nucleo3d.modelo import Barra, Camada, Chapa, Documento, Solido, novo_id

SITUACOES = ("aberta", "retraida")


def _mover(ent, d):
    """a entidade deslocada de d (mm)"""
    soma = lambda p: (p[0] + d[0], p[1] + d[1], p[2] + d[2])
    if isinstance(ent, Barra):
        ent.inicio, ent.fim = soma(ent.inicio), soma(ent.fim)
    elif isinstance(ent, Chapa):
        ent.origem = soma(ent.origem)
    elif isinstance(ent, Solido):
        ent.vertices = [soma(v) for v in ent.vertices]


def gerada(ent) -> bool:
    return bool((getattr(ent, "atributos", None) or {}).get("cobertura_movel"))


def aplicar(doc: Documento, par: Optional[dict] = None, situacao: str = "aberta", lona: Optional[bool] = None) -> dict:
    """troca no `doc` as tesouras lançadas (e as geradas antes) pelas da cobertura retrátil na `situacao`; devolve o
    resumo. Erro de dados se o modelo não tem a tesoura molde apoiada nas vigas. `lona`: True gera a lona da cobertura
    (ilustração, `lona_da_cobertura`), False a tira; None mantém como estava — a que já havia é gerada de novo na posição
    das tesouras (Kaefer, 19/10: "a lona não segue o modelo retraído")"""
    from nucleo.base import ErroDeDados
    from nucleo3d import analise_estrutural as AE
    if situacao not in SITUACOES:
        raise ErroDeDados("situação da cobertura: aberta ou retraida")
    P = dict(AE.PARAMETROS_PADRAO, **(par or {}))
    P.update(cobertura_movel=True, configuracao=situacao)
    base = AE._sem_copias_da_cobertura(doc)          # o molde na posição da planta (a primeira cópia levada de volta)
    M = AE.montar(base, P)
    mv = M.get("movel")
    if not mv:
        avisos = [a for a in M["avisos"] if "cobertura retrátil" in a]
        raise ErroDeDados(avisos[0] if avisos else "o modelo não tem a tesoura da cobertura retrátil")
    molde = [base.entidades[i] for i in mv["molde_ids"] if i in base.entidades]
    if not molde:
        raise ErroDeDados("não achei no 3D as peças da tesoura molde")
    n = mv["n_dir"]
    # fora: as tesouras (lançadas e geradas) e a sanfona gerada antes
    fora = [k for k, e in doc.entidades.items()
            if (e.atributos or {}).get("elemento") == "trelica" or (gerada(e) and (e.atributos or {}).get("elemento") == "sanfona")]
    lonas = [e for e in doc.entidades.values() if (e.atributos or {}).get("elemento") == LONA]
    camada_lona = lonas[0].camada if lonas else CAMADA_LONA
    if lona is None:
        lona = bool(lonas)
    fora += [e.id for e in lonas]
    for k in fora:
        doc.remover(k)
    planta = next(((e.atributos or {}).get("planta") for e in molde if (e.atributos or {}).get("planta")), None)
    n_pecas = 0
    desl = []
    for k, t in enumerate(mv["tesouras"]):
        dt = (t["t"] - mv["t0"]) * 1000.0
        d = (n[0] * dt, n[1] * dt, 0.0)
        desl.append(d)
        for e in molde:
            c = copy.deepcopy(e)
            c.id = novo_id()
            _mover(c, d)
            at = dict(c.atributos or {})
            if at.get("origem_2d"):
                at["origem_2d"] = "%s#%d" % (str(at["origem_2d"]).split("#")[0], k)
            at["cobertura_movel"] = {"k": k, "situacao": situacao, "d": [round(v, 3) for v in d]}
            c.atributos = at
            doc.add(c)
            n_pecas += 1
    # a sanfona, pelos mesmos nós da análise — mas no 3D a ponta de baixo fica no pé da tesoura: o nó de cálculo do
    # apoio desce até o eixo da viga (a W410 da Kaefer do engenheiro, 15/10: a sanfona entrava 204 mm na viga)
    nos = M["nos"]
    z_pe = min(min(e.inicio[2], e.fim[2]) for e in molde if isinstance(e, Barra)) if any(isinstance(e, Barra) for e in molde) else None
    ns = 0
    for k, (t1, t2) in enumerate(zip(mv["tesouras"], mv["tesouras"][1:])):
        for (top1, bot1), (top2, bot2) in zip(t1["lados"], t2["lados"]):
            for a, b in ((top1, bot2), (bot1, top2)):
                A, B = tuple(float(v) * 1000.0 for v in nos[a]), tuple(float(v) * 1000.0 for v in nos[b])
                if z_pe is not None:
                    A, B = (A[0], A[1], max(A[2], z_pe)), (B[0], B[1], max(B[2], z_pe))
                if sum((A[j] - B[j]) ** 2 for j in range(3)) < 1.0:
                    continue
                at = {"elemento": "sanfona", "cobertura_movel": {"k": k, "situacao": situacao}}
                if planta:
                    at["planta"] = planta
                doc.add(Barra(nome="Sanfona %d-%d" % (k + 1, k + 2), camada="Contraventamento", inicio=A, fim=B,
                              perfil=P.get("perfil_sanfona") or "TQ 50×50×2,0", papel="contraventamento", atributos=at))
                ns += 1
    n_lona = lona_da_cobertura(doc, molde, n, desl, situacao, camada_lona) if lona else 0
    return {"situacao": situacao, "tesouras": len(mv["tesouras"]), "pecas_tesouras": n_pecas, "sanfona": ns, "lona": n_lona,
            "passo_m": mv["passo_m"], "comprimento_m": mv["comprimento_m"], "saiu": len(fora),
            "peso_tesoura_kg": mv["peso_tesoura_kg"], "planta": planta}


# ------------------------------------------------------------------ a lona da cobertura (ilustração)

LONA = "lona_cobertura"
CAMADA_LONA = "Lona"
#: a lona fica fora das tesouras: acima do banzo de cima, além das pontas e das tesouras das extremidades (mm)
FOLGA_LONA = 30.0
ESPESSURA_LONA = 3.0


def _prisma(secao: Sequence[Tuple[float, float, float]], v: Sequence[float]) -> Tuple[List[tuple], List[List[int]]]:
    """vértices e faces do prisma da seção plana (convexa) extrudada por v, as faces anti-horárias vistas de fora"""
    m = len(secao)
    nrm = [sum((secao[i][a] - secao[(i + 1) % m][a]) * (secao[i][b] + secao[(i + 1) % m][b]) for i in range(m))
           for a, b in ((1, 2), (2, 0), (0, 1))]
    if sum(nrm[i] * v[i] for i in range(3)) < 0:
        secao = list(secao)[::-1]
    vs = [tuple(p) for p in secao] + [tuple(p[k] + v[k] for k in range(3)) for p in secao]
    faces = [list(range(m))[::-1], list(range(m, 2 * m))] + [[i, (i + 1) % m, m + (i + 1) % m, m + i] for i in range(m)]
    return vs, faces


def _juntar(pecas) -> Tuple[List[tuple], List[List[int]]]:
    """os prismas num sólido só (cascas separadas)"""
    vs, fs = [], []
    for v, f in pecas:
        base = len(vs)
        vs.extend(v)
        fs.extend([[base + i for i in face] for face in f])
    return vs, fs


def _meia_altura(perfil: str) -> float:
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(perfil or ""))
    return float(m.group(1).replace(",", ".")) / 2.0 if m else 25.0


def lona_da_cobertura(doc: Documento, molde, n, desl, situacao: str, camada: str = CAMADA_LONA) -> int:
    """A lona da cobertura retrátil (Kaefer, 19/10), só para ilustrar (fora da lista de materiais e do IFC): um sólido por
    vão entre tesouras vizinhas, pelo arco do banzo de cima de cada uma, descendo nas pontas até o pé da tesoura, e o
    arco fechado nas duas tesouras das extremidades. Segue a situação: aberta, nos vãos do comprimento todo; retraída,
    dobrada nos vãos curtos da pilha. Devolve quantos sólidos."""
    sup = [e for e in molde if isinstance(e, Barra) and (e.atributos or {}).get("papel_trelica") == "banzo_sup"]
    barras = [e for e in molde if isinstance(e, Barra)]
    if not sup or not desl:
        return 0
    u = (-n[1], n[0], 0.0)                                     # ao longo do vão da tesoura
    h = max(_meia_altura(e.perfil) for e in sup)
    pts = {}
    for e in sup:
        for p in (e.inicio, e.fim):
            pts[round(p[0] * u[0] + p[1] * u[1], 1)] = p
    arco = [pts[k] for k in sorted(pts)]
    z_pe = min(min(e.inicio[2], e.fim[2]) for e in barras)
    G = FOLGA_LONA
    # o arco por cima do banzo (meia altura do tubo) e esticado 30 mm além de cada ponta
    arco = [(p[0], p[1], p[2] + h) for p in arco]
    arco = [(arco[0][0] - u[0] * G, arco[0][1] - u[1] * G, arco[0][2])] + arco + \
           [(arco[-1][0] + u[0] * G, arco[-1][1] + u[1] * G, arco[-1][2])]
    # as tesouras na ordem ao longo do trilho; o primeiro e o último vão passam 30 mm das tesouras das extremidades
    s = sorted(d[0] * n[0] + d[1] * n[1] for d in desl)
    trechos = [[a, b] for a, b in zip(s, s[1:])] or [[s[0], s[0]]]
    trechos[0][0] -= G
    trechos[-1][1] += G
    if camada not in doc.camadas:
        doc.camadas[camada] = Camada(camada, "#eef1f4", visivel=False)
    T = ESPESSURA_LONA
    at = {"elemento": LONA, "exportar": False, "ilustracao": True,
          "obs": "lona da cobertura retrátil, só ilustração: fora da lista de materiais e do IFC"}

    def em(p, sn):
        return (p[0] + n[0] * sn, p[1] + n[1] * sn, p[2])

    for k, (a, b) in enumerate(trechos):
        v = (n[0] * (b - a), n[1] * (b - a), 0.0)
        pecas = []
        for p, q in zip(arco, arco[1:]):
            p0, q0 = em(p, a), em(q, a)
            pecas.append(_prisma([p0, q0, (q0[0], q0[1], q0[2] + T), (p0[0], p0[1], p0[2] + T)], v))
        for p, sg in ((arco[0], -1.0), (arco[-1], 1.0)):      # as pontas da tesoura, até o pé
            q = em(p, a)
            fora = (q[0] + sg * u[0] * T, q[1] + sg * u[1] * T)
            pecas.append(_prisma([(q[0], q[1], z_pe), (q[0], q[1], p[2]), (fora[0], fora[1], p[2]), (fora[0], fora[1], z_pe)], v))
        vs, fs = _juntar(pecas)
        doc.add(Solido(nome="Lona %d-%d" % (k + 1, k + 2), camada=camada, vertices=vs, faces=fs, material="Lona PVC",
                       atributos=dict(at, lona_movel={"vao": k, "situacao": situacao})))
    # o arco fechado nas duas extremidades
    for sn, sg in ((trechos[0][0], -1.0), (trechos[-1][1], 1.0)):
        sec = [em((arco[0][0], arco[0][1], z_pe), sn)] + [em(p, sn) for p in arco] + [em((arco[-1][0], arco[-1][1], z_pe), sn)]
        vs, fs = _prisma(sec, (n[0] * sg * T, n[1] * sg * T, 0.0))
        doc.add(Solido(nome="Lona frontão", camada=camada, vertices=vs, faces=fs, material="Lona PVC",
                       atributos=dict(at, lona_movel={"frontao": sg, "situacao": situacao})))
    return len(trechos) + 2


# ------------------------------------------------------------------ a planta (o 2D acompanha o 3D)

CAMADA_PLANTA = "COBERTURA RETRÁTIL"
CAMADA_MOLDE = "TESOURAS LANÇADAS (molde)"


def na_planta(des, doc: Documento) -> bool:
    """a cobertura retrátil do 3D desenhada na planta de lançamento (pedido de 06/10: "ajustar junto o modelo 2D quando
    altera para aberta e retraída"): uma linha por tesoura, na posição da situação, na camada COBERTURA RETRÁTIL, e um
    texto com o resumo; as tesouras lançadas (o molde, com o desenho delas) e os rótulos vão para a camada do molde,
    escondida — continuam elementos da planta. Ids fixos: sem mudança, nada muda. Devolve se a planta mudou."""
    from nucleo2d.desenho import Camada2D, Linha, Texto
    antes = _impressao_planta(des)
    for k in [k for k, e in des.entidades.items() if (e.atributos or {}).get("cobertura_movel")]:
        del des.entidades[k]
    copias = {}
    for e in doc.entidades.values():
        at = e.atributos or {}
        cm = at.get("cobertura_movel")
        if cm and at.get("elemento") == "trelica" and at.get("origem_2d"):
            copias.setdefault(int(cm.get("k", 0)), (str(at["origem_2d"]).split("#")[0], cm, at.get("marca") or ""))
    linhas = []
    for k, (base, cm, marca) in sorted(copias.items()):
        m = des.entidades.get(base)
        if not isinstance(m, Linha):
            continue
        d = cm.get("d") or (0.0, 0.0, 0.0)
        ln = Linha(id="cobertura-movel-%02d" % k, camada=CAMADA_PLANTA, a=(m.a[0] + d[0], m.a[1] + d[1]),
                   b=(m.b[0] + d[0], m.b[1] + d[1]), atributos={"cobertura_movel": {"k": k, "situacao": cm.get("situacao")}})
        des.add(ln)
        linhas.append((ln, marca, cm.get("situacao")))
    if linhas:
        if CAMADA_PLANTA not in des.camadas:
            des.camadas[CAMADA_PLANTA] = Camada2D(CAMADA_PLANTA, "#0e9f6e", espessura=0.35)
        if CAMADA_MOLDE not in des.camadas:
            des.camadas[CAMADA_MOLDE] = Camada2D(CAMADA_MOLDE, "#c0392b", visivel=False, tipo_linha="DASHED")
        trel = {e.id for e in des.entidades.values() if (e.atributos or {}).get("elemento") == "trelica"}
        for e in des.entidades.values():
            a = e.atributos or {}
            if e.id in trel or a.get("rotulo_de") in trel:
                e.camada = CAMADA_MOLDE
        ln0, marca, sit = linhas[0]
        ys = [l.a[1] for l, _m, _s in linhas]
        passo = (max(ys) - min(ys)) / max(1, len(linhas) - 1) / 1000.0
        des.add(Texto(id="cobertura-movel-texto", camada=CAMADA_PLANTA, posicao=(min(ln0.a[0], ln0.b[0]), min(ys) - 900.0),
                      texto="COBERTURA RETRÁTIL %s: %d × %s a cada %s m" % ("ABERTA" if sit == "aberta" else "RETRAÍDA", len(linhas),
                                                                         marca or "tesoura", ("%.3f" % passo).replace(".", ",")),
                      altura=3.0, atributos={"cobertura_movel": {"texto": True}}))
    return _impressao_planta(des) != antes


def _impressao_planta(des) -> str:
    import json
    from dataclasses import asdict
    sel = sorted((e.id, e.camada, json.dumps(asdict(e), sort_keys=True, default=str))
                 for e in des.entidades.values()
                 if (e.atributos or {}).get("cobertura_movel") or (e.atributos or {}).get("elemento") == "trelica"
                 or (e.atributos or {}).get("rotulo_de"))
    return json.dumps([sel, sorted(des.camadas)], default=str)
