# -*- coding: utf-8 -*-
"""Verificação de uma barra de treliça ou de pórtico, qualquer que seja o perfil.

Uma barra de tesoura não é "viga" nem "pilar": ela chega com força normal (que troca de
sinal entre a gravidade e a sucção do vento) e, nos banzos contínuos, com um momento
local do trecho entre nós. Quem decide o caminho é o perfil:

* laminado e tubo → NBR 8800 (compressão, tração, flexão e flexo-compressão);
* U e Ue formados a frio → NBR 14762, pelo Método da Resistência Direta (MRD).

Está aqui, e não dentro do cálculo do IFC, porque três frentes precisam do mesmo
julgamento: a tesoura importada (`nucleo3d/calculo_ifc.py`), a tesoura gerada pelo
dimensionamento do galpão (`nucleo/tesouras.py`) e a troca de perfil da análise.

Convenção dos esforços: `Nc` compressão e `Nt` tração, ambos em módulo (kN); `M` o
momento (kN·cm); `n` o número de peças que dividem o esforço (cantoneira dupla, por
exemplo). `Lx` e `Ly` são os comprimentos de flambagem no plano e fora do plano, cm.
"""
from __future__ import annotations

from typing import List, Optional

from . import materiais as mat, nbr8800, nbr14762, perfis_fabrica
from .base import ErroDeDados, Resultado, Verificacao, fmt
from .perfis import Perfil

__all__ = ["verificar_membro", "verificar_frio", "verificar_laminado",
           "serializar_resultado"]


def verificar_frio(perfil: Perfil, aco: str, Nc: float, Nt: float, M: float,
                   Lx: float, Ly: float, n: int, elemento: str) -> Resultado:
    """U/Ue formado a frio: compressão e flexão pelo MRD, tração pela seção bruta e a
    interação linear N–M (NBR 14762, item 9.8.2.4). Esforços por peça (já divididos por n)."""
    sec = perfis_fabrica.secao_frio(perfil)
    a = mat.aco(aco)
    r = Resultado(elemento, perfil=perfil.nome, material=a.nome)
    Nc, Nt, M = abs(Nc) / n, abs(Nt) / n, abs(M) / n
    vc = None
    if Nc > 1e-6:
        vc = nbr14762.compressao_mrd(sec, a, N_Sd=Nc, KxLx=Lx, KyLy=Ly, KtLt=Ly)
        r.add(vc)
    if Nt > 1e-6:
        vt = Verificacao("Tração — escoamento da seção bruta", norma="NBR 14762:2010, item 9.6.1",
                         Sd=Nt, Rd=sec.A * a.fy / nbr14762.GAMA, unidade="kN")
        vt.passo("N<sub>t,Rd</sub> = A·f<sub>y</sub>/γ", "", "%s × %s / 1,10" % (fmt(sec.A), fmt(a.fy)), fmt(vt.Rd, 1, "kN"))
        r.add(vt)
    vm = None
    if M > 1e-6:
        vm = nbr14762.flexao_mrd(sec, a, M_Sd=M, Lb=Ly, Lt=Ly)
        r.add(vm)
    if vm is not None and (vc is not None or Nt > 1e-6):
        NRd = vc.Rd if vc is not None else sec.A * a.fy / nbr14762.GAMA
        NSd = Nc if vc is not None else Nt
        vi = Verificacao("Interação N–M", norma="NBR 14762:2010, item 9.8.2.4",
                         Sd=NSd / NRd + M / vm.Rd if NRd and vm.Rd else float("inf"), Rd=1.0, unidade="—")
        vi.passo("N<sub>Sd</sub>/N<sub>Rd</sub> + M<sub>Sd</sub>/M<sub>Rd</sub> ≤ 1", "",
                 "%s/%s + %s/%s" % (fmt(NSd, 1), fmt(NRd, 1), fmt(M, 0), fmt(vm.Rd, 0)), fmt(vi.Sd, 3))
        r.add(vi)
    if not r.verificacoes:
        r.add(Verificacao("Sem esforço", Sd=0.0, Rd=1.0, unidade="—"))
    r.dados.update({"N_c": Nc * n, "N_t": Nt * n, "M": M * n, "Lx": Lx, "Ly": Ly, "n": n,
                    "norma": "NBR 14762"})
    return r


def verificar_laminado(perfil: Perfil, aco: str, Nc: float, Nt: float, M: float,
                       Lx: float, Ly: float, n: int, elemento: str,
                       avisos: Optional[List[str]] = None) -> Resultado:
    """Laminado, tubo, cantoneira ou barra redonda pela NBR 8800."""
    a = mat.aco(aco)
    Nc, Nt, M = abs(Nc) / n, abs(Nt) / n, abs(M) / n
    cant = perfil.tipo == "L"
    if perfil.tipo == "barra":
        r = nbr8800.tracao(perfil, a, N_Sd=Nt, L=Lx, rosqueada=bool(perfil.dados.get("rosqueada")), elemento=elemento)
        if Nc > 1e-6:
            v = Verificacao("Barra redonda comprimida", norma="—", Sd=Nc, Rd=1e-9, unidade="kN")
            v.observacao = "barra redonda não resiste à compressão"
            r.add(v)
        return r
    r = Resultado(elemento, perfil=perfil.nome, material=a.nome)
    if M > 1e-6 and not cant and Nc > 1e-6:
        rc = nbr8800.flexao_composta(perfil, a, N_Sd=Nc, Mx_Sd=M, Lx=Lx, Ly=Ly, Lb=Ly, elemento=elemento)
        r.verificacoes.extend(rc.verificacoes)
        r.dados.update(rc.dados)
    else:
        if Nc > 1e-6:
            rc = nbr8800.compressao(perfil, a, Lx=Lx, Ly=Ly, N_Sd=Nc, cantoneira_simplificada=cant, elemento=elemento)
            r.verificacoes.extend(rc.verificacoes)
            r.dados.update(rc.dados)
        if M > 1e-6:
            if cant:
                # flexão de cantoneira simples: fora da NBR 8800; conferência elástica W·fy
                W = perfil.Wx or 1e-9
                v = Verificacao("Flexão da cantoneira (elástica, W·f<sub>y</sub>/γ)", norma="conferência elástica",
                                Sd=M, Rd=W * a.fy / 1.10, unidade="kN·cm")
                v.observacao = "a NBR 8800 não cobre a flexão de cantoneira simples; conferência elástica"
                r.add(v)
            else:
                rf = nbr8800.flexao(perfil, a, M_Sd=M, Lb=Ly, elemento=elemento)
                r.verificacoes.extend(rf.verificacoes)
    if Nt > 1e-6:
        rt = nbr8800.tracao(perfil, a, N_Sd=Nt, L=max(Lx, Ly), elemento=elemento)
        r.verificacoes.extend(rt.verificacoes)
    if not r.verificacoes:
        r.add(Verificacao("Sem esforço", Sd=0.0, Rd=1.0, unidade="—"))
    r.dados.update({"N_c": Nc * n, "N_t": Nt * n, "M": M * n, "Lx": Lx, "Ly": Ly, "n": n, "norma": "NBR 8800"})
    return r


def verificar_membro(perfil: Perfil, aco: str, Nc, Nt, M, Lx, Ly, n, elemento,
                     avisos: Optional[List[str]] = None) -> Resultado:
    """Escolhe a norma pelo perfil e devolve o resultado; erro de dados vira 'não verificada'."""
    try:
        if perfis_fabrica.tipo_de_verificacao(perfil) == "frio":
            return verificar_frio(perfil, aco, Nc, Nt, M, Lx, Ly, n, elemento)
        return verificar_laminado(perfil, aco, Nc, Nt, M, Lx, Ly, n, elemento, avisos)
    except ErroDeDados as exc:
        r = Resultado(elemento, perfil=perfil.nome, material=aco)
        v = Verificacao("Não verificada", Sd=0.0, Rd=1.0, unidade="—")
        v.observacao = str(exc)
        r.add(v)
        r.dados["erro"] = str(exc)
        return r


def serializar_resultado(r: Resultado) -> dict:
    """Resultado em dicionário simples, do jeito que a interface web consome."""
    return {"elemento": r.elemento, "perfil": r.perfil, "material": r.material, "razao": round(r.razao, 3),
            "ok": bool(r.ok),
            "verificacoes": [{"titulo": v.titulo, "norma": v.norma, "Sd": round(v.Sd, 3), "Rd": round(v.Rd, 3),
                              "unidade": v.unidade, "razao": round(v.razao, 3), "ok": bool(v.ok),
                              "observacao": getattr(v, "observacao", "") or "",
                              "passos": [{"texto": p.texto, "formula": p.formula, "conta": p.conta, "valor": p.valor,
                                          "norma": p.norma} for p in v.passos]}
                             for v in r.verificacoes if not v.dispensada],
            "dados": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.dados.items()
                      if isinstance(v, (int, float, str, bool)) or v is None}}
