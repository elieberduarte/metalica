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
            "peso_tesoura_kg": mv["peso_tesoura_kg"]}
