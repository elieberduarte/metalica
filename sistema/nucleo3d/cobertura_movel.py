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
from typing import Optional

from nucleo3d.modelo import Barra, Chapa, Documento, Solido, novo_id

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


def aplicar(doc: Documento, par: Optional[dict] = None, situacao: str = "aberta") -> dict:
    """troca no `doc` as tesouras lançadas (e as geradas antes) pelas da cobertura retrátil na `situacao`; devolve o
    resumo. Erro de dados se o modelo não tem a tesoura molde apoiada nas vigas"""
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
    for k in fora:
        doc.remover(k)
    planta = next(((e.atributos or {}).get("planta") for e in molde if (e.atributos or {}).get("planta")), None)
    n_pecas = 0
    for k, t in enumerate(mv["tesouras"]):
        dt = (t["t"] - mv["t0"]) * 1000.0
        d = (n[0] * dt, n[1] * dt, 0.0)
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
    # a sanfona, pelos mesmos nós da análise
    nos = M["nos"]
    ns = 0
    for k, (t1, t2) in enumerate(zip(mv["tesouras"], mv["tesouras"][1:])):
        for (top1, bot1), (top2, bot2) in zip(t1["lados"], t2["lados"]):
            for a, b in ((top1, bot2), (bot1, top2)):
                A, B = tuple(float(v) * 1000.0 for v in nos[a]), tuple(float(v) * 1000.0 for v in nos[b])
                if sum((A[j] - B[j]) ** 2 for j in range(3)) < 1.0:
                    continue
                at = {"elemento": "sanfona", "cobertura_movel": {"k": k, "situacao": situacao}}
                if planta:
                    at["planta"] = planta
                doc.add(Barra(nome="Sanfona %d-%d" % (k + 1, k + 2), camada="Contraventamento", inicio=A, fim=B,
                              perfil=P.get("perfil_sanfona") or "TQ 50×50×2,0", papel="contraventamento", atributos=at))
                ns += 1
    return {"situacao": situacao, "tesouras": len(mv["tesouras"]), "pecas_tesouras": n_pecas, "sanfona": ns,
            "passo_m": mv["passo_m"], "comprimento_m": mv["comprimento_m"], "saiu": len(fora),
            "peso_tesoura_kg": mv["peso_tesoura_kg"], "planta": planta}


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
