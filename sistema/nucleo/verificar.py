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

`ligacao` (opcional) descreve a ligação da extremidade da barra, para o Ct da ruptura da
seção líquida: dicionário com "lc" (cm, comprimento da ligação na direção da força: do
primeiro ao último parafuso da linha, ou o cordão de solda longitudinal), "n_parafusos",
"d_parafuso" (cm), "soldada" (bool), "fonte" (texto curto para o memorial) e "ponta_ligada"
(bool; False = trecho corrido de banzo contínuo: sem ligação de ponta, a ruptura da seção
líquida não se aplica e fica só o escoamento). Sem ela, a cantoneira e o U ligados por um
elemento só recebem o Ct conservador adotado, registrado como hipótese no `Resultado`:
Ac/Ag (piso da NBR 8800:2024) nos laminados; 0,50 no U/Ue formado a frio e 0,40 na
cantoneira formada a frio (os menores da NBR 14762 para a ligação soldada). Achados N1 e
N11, 14/10/2026: antes saía Ct = 1,0 na NBR 8800 e a NBR 14762 nem verificava a ruptura.
"""
from __future__ import annotations

from typing import List, Optional

from . import materiais as mat, nbr8800, nbr14762, perfis_fabrica
from .base import ErroDeDados, Resultado, Verificacao, fmt, nao_verificada
from .perfis import Perfil

__all__ = ["verificar_membro", "verificar_frio", "verificar_laminado",
           "serializar_resultado", "tracao_ruptura_frio", "ct_sem_ligacao_frio"]

#: γ da ruptura da seção líquida na região da ligação (NBR 14762:2010, item 9.6.2-c)
GAMA_RUPTURA_LIGACAO_FRIO = 1.65

#: Limites do Ct na NBR 14762:2010, item 9.6.2-c) (p. 35–36): "devendo, no entanto, ser
#: usado 0,9 como limite superior, e não se permitindo o uso de ligações que resultem em um
#: valor inferior a 0,4" — cantoneira e U parafusados e cantoneira soldada — ou "a 0,5" — U
#: com soldas longitudinais
CT_MAX_FRIO = 0.90
CT_MIN_FRIO_PARAFUSADA = 0.40
CT_MIN_FRIO_CANTONEIRA_SOLDADA = 0.40
CT_MIN_FRIO_SOLDADA_U = 0.50

#: Ct adotado quando a ligação do perfil formado a frio não está no modelo (decisão do
#: usuário, 14/10/2026): o menor que a NBR 14762 admite para a ligação soldada, o caso usual
#: das tesouras — 0,50 no U/Ue; na cantoneira a norma admite soldada até 0,40, e é esse o
#: valor adotado (0,50 seria maior que o mínimo da norma, contra a segurança).
CT_SEM_LIGACAO_FRIO_U = CT_MIN_FRIO_SOLDADA_U
CT_SEM_LIGACAO_FRIO_CANTONEIRA = CT_MIN_FRIO_CANTONEIRA_SOLDADA


def ct_sem_ligacao_frio(cantoneira: bool = False) -> float:
    """O Ct adotado na ruptura da seção líquida do formado a frio sem a ligação no modelo."""
    return CT_SEM_LIGACAO_FRIO_CANTONEIRA if cantoneira else CT_SEM_LIGACAO_FRIO_U


def _furo_padrao_frio(d: float) -> float:
    """Diâmetro do furo-padrão, cm (NBR 14762:2010, Tabela 15): d + 0,8 mm para d < 12,5 mm,
    d + 1,5 mm para d ≥ 12,5 mm."""
    return d + (0.08 if d < 1.25 else 0.15)


def tracao_ruptura_frio(sec, a, N_Sd: float, ligacao: Optional[dict] = None,
                        r: Optional[Resultado] = None, cantoneira: bool = False) -> Verificacao:
    """Ruptura da seção líquida na região da ligação do perfil formado a frio —
    NBR 14762:2010, item 9.6.2-c): Nt,Rd = Ct·An·fu/γ, γ = 1,65.

    `sec` precisa de A (cm²), t (cm), xc (cm: x, a distância do centroide ao plano de
    cisalhamento da ligação — a face externa da alma do U, a da aba ligada da cantoneira) e
    nome. U (o Ue entra como U: liga pela alma, nem todos os elementos conectados) ou
    cantoneira (`cantoneira=True`):

    * parafusada, 2 ou mais parafusos na linha: Ct = 1 − 1,2·x/L ≤ 0,9 (ligação com Ct < 0,4
      não é permitida); An = 0,9·(A − nf·df·t), um furo na seção, df pela Tabela 15;
    * parafusada, um parafuso só: chapa equivalente, Ct = 2,5·d/g ≤ 1,0, g = largura bruta
      da chapa equivalente (A/t);
    * soldada (soldas longitudinais): U, Ct = 1 − 0,36·x/L ≤ 0,9 (não se permite < 0,5);
      cantoneira, Ct = 1 − 1,2·x/L ≤ 0,9 (não se permite < 0,4); An = A;
    * sem a ligação no modelo: Ct = `ct_sem_ligacao_frio` adotado (hipótese em `r`), An = A.

    `r`, quando dado, recebe a hipótese do Ct e os dados (Ct, An, N_Rd_ruptura).
    """
    lig = nbr8800.ler_ligacao(ligacao)
    A, t, x = sec.A, sec.t, sec.xc
    v = Verificacao("Tração — ruptura da seção líquida", norma="NBR 14762:2010, item 9.6.2-c)",
                    Sd=N_Sd, unidade="kN")
    lc = lig.get("lc") or 0.0
    n_par = lig.get("n_parafusos") or 0
    fonte = lig.get("fonte", "")
    ct_min = None
    fonte_hip = "modelo"
    item = "NBR 14762:2010, item 9.6.2-c)"
    peca = "cantoneira" if cantoneira else "U"
    plano = "aba ligada" if cantoneira else "alma"
    passo_x = ("Excentricidade da ligação", "x", "de G à face externa da %s" % plano,
               fmt(x, 2, "cm"), item + ", Figura 4")
    if n_par:
        d = lig["d_parafuso"]
        df = _furo_padrao_frio(d)
        An = 0.9 * (A - 1 * df * t)
        v.passo("Furo-padrão", "d<sub>f</sub> = d + 0,8 mm (d < 12,5 mm) ou d + 1,5 mm (d ≥ 12,5 mm)",
                "%s + %s" % (fmt(d, 3), fmt(df - d, 2)), fmt(df, 3, "cm"), "NBR 14762:2010, Tabela 15")
        v.passo("Área líquida na região da ligação (um furo na seção)",
                "A<sub>n</sub> = 0,9·(A − n<sub>f</sub>·d<sub>f</sub>·t)",
                "0,9 × (%s − 1 × %s × %s)" % (fmt(A, 3), fmt(df, 3), fmt(t, 3)), fmt(An, 3, "cm²"), item)
        if n_par == 1:
            g = A / t
            Ct = min(1.0, 2.5 * d / g)
            v.passo("Um parafuso só: perfil como chapa equivalente (g = largura bruta, A/t)",
                    "C<sub>t</sub> = 2,5·d/g ≤ 1,0", "2,5 × %s / (%s / %s)" % (fmt(d, 3), fmt(A, 3), fmt(t, 3)),
                    fmt(Ct, 3), item + ", perfis com ligações parafusadas")
            hip = "C<sub>t</sub> = %s: ligação com um parafuso só (%s)" % (fmt(Ct, 3), fonte)
        elif lc > 0:
            Ct = min(CT_MAX_FRIO, 1.0 - 1.2 * x / lc)
            ct_min = CT_MIN_FRIO_PARAFUSADA
            v.passo(*passo_x)
            v.passo("C<sub>t</sub> de %s parafusado (%d parafusos, %s)" % (peca, n_par, fonte),
                    "C<sub>t</sub> = 1 − 1,2·x/L ≤ 0,9", "1 − 1,2 × %s / %s" % (fmt(x, 2), fmt(lc, 1)),
                    fmt(Ct, 3), item + ", perfis com ligações parafusadas")
            hip = ("C<sub>t</sub> = %s pela ligação parafusada (%s): L = %s cm, x = %s cm"
                   % (fmt(Ct, 3), fonte, fmt(lc, 1), fmt(x, 2)))
        else:
            Ct = CT_MIN_FRIO_PARAFUSADA
            fonte_hip = "rotina"
            v.passo("C<sub>t</sub> = 0,40 adotado: parafusos sem o comprimento da ligação "
                    "(hipótese conservadora; NBR 14762, item 9.6.2-c)",
                    "C<sub>t</sub> = 0,40", "menor C<sub>t</sub> admitido para %s parafusado" % peca, fmt(Ct, 3), item)
            hip = ("C<sub>t</sub> = 0,40 adotado: %d parafusos (%s) sem o comprimento L da ligação"
                   % (n_par, fonte))
    elif lig.get("soldada") and lc > 0:
        An = A
        v.passo("Ligação soldada", "A<sub>n</sub> = A", fmt(A, 3), fmt(An, 3, "cm²"), item)
        v.passo(*passo_x)
        if cantoneira:
            Ct = min(CT_MAX_FRIO, 1.0 - 1.2 * x / lc)
            ct_min = CT_MIN_FRIO_CANTONEIRA_SOLDADA
            v.passo("C<sub>t</sub> de cantoneira com soldas longitudinais (%s)" % fonte,
                    "C<sub>t</sub> = 1 − 1,2·x/L ≤ 0,9", "1 − 1,2 × %s / %s" % (fmt(x, 2), fmt(lc, 1)),
                    fmt(Ct, 3), item + ", perfis com ligações soldadas")
        else:
            Ct = min(CT_MAX_FRIO, 1.0 - 0.36 * x / lc)
            ct_min = CT_MIN_FRIO_SOLDADA_U
            v.passo("C<sub>t</sub> de U com soldas longitudinais (%s)" % fonte,
                    "C<sub>t</sub> = 1 − 0,36·x/L ≤ 0,9", "1 − 0,36 × %s / %s" % (fmt(x, 2), fmt(lc, 1)),
                    fmt(Ct, 3), item + ", perfis com ligações soldadas")
        hip = ("C<sub>t</sub> = %s pela ligação soldada (%s): L = %s cm, x = %s cm"
               % (fmt(Ct, 3), fonte, fmt(lc, 1), fmt(x, 2)))
    else:
        An = A
        fonte_hip = "rotina"
        Ct = ct_sem_ligacao_frio(cantoneira)
        motivo = ("ligação soldada (%s) sem o comprimento do cordão" % fonte if lig.get("soldada")
                  else "a ligação da barra não está no modelo")
        v.passo("C<sub>t</sub> = %s adotado: %s (hipótese conservadora; NBR 14762, item 9.6.2-c)"
                % (fmt(Ct, 2), motivo),
                "C<sub>t</sub> = %s" % fmt(Ct, 2),
                "menor C<sub>t</sub> que a norma admite para %s com soldas longitudinais, o caso usual "
                "das tesouras" % ("cantoneira" if cantoneira else "U"),
                fmt(Ct, 3), item)
        hip = ("C<sub>t</sub> = %s adotado na tração: %s em %s (o menor C<sub>t</sub> que a NBR 14762 admite "
               "para %s soldado); com a ligação desenhada, C<sub>t</sub> = 1 − 1,2·x/L (parafusos) ou %s "
               "(solda), x = %s cm" % (fmt(Ct, 2), motivo, sec.nome, peca,
                                       "1 − 1,2·x/L" if cantoneira else "1 − 0,36·x/L", fmt(x, 2)))
        v.passo("Área líquida (sem furos conhecidos na ligação)", "A<sub>n</sub> = A", fmt(A, 3),
                fmt(An, 3, "cm²"), item)
    v.Rd = Ct * An * a.fu / GAMA_RUPTURA_LIGACAO_FRIO
    v.passo("Força resistente à ruptura da seção líquida na ligação",
            "N<sub>t,Rd</sub> = C<sub>t</sub>·A<sub>n</sub>·f<sub>u</sub>/γ (γ = 1,65)",
            "%s × %s × %s / 1,65" % (fmt(Ct, 3), fmt(An, 3), fmt(a.fu)), fmt(v.Rd, 1, "kN"), item)
    if ct_min is not None and Ct < ct_min:
        # a norma não permite essa ligação: a verificação não passa, qualquer que seja o esforço
        v.observacao = ("Ct = %s < %s: a NBR 14762 (item 9.6.2-c) não permite essa ligação; "
                        "aumente o comprimento da ligação" % (fmt(Ct, 3), fmt(ct_min, 2)))
        v.Rd = 0.0
    if r is not None:
        r.hipotese("ct_ligacao", hip, fonte_hip)
        r.dados.update({"Ct": Ct, "An": An, "N_Rd_ruptura": v.Rd,
                        "Ct_adotado_sem_ligacao": fonte_hip == "rotina"})
    return v


TEXTO_SEM_PONTA = "trecho corrido de banzo contínuo: sem ligação de ponta, a seção líquida não se aplica"


def verificar_frio(perfil: Perfil, aco: str, Nc: float, Nt: float, M: float,
                   Lx: float, Ly: float, n: int, elemento: str,
                   ligacao: Optional[dict] = None) -> Resultado:
    """U/Ue formado a frio: compressão e flexão pelo MRD, tração pelo escoamento da seção
    bruta e pela ruptura da seção líquida na ligação (NBR 14762, item 9.6.2; esta só com a
    ponta ligada) e a interação linear N–M (NBR 14762, item 9.8.2.4). Esforços por peça (já
    divididos por n)."""
    sec = perfis_fabrica.secao_frio(perfil)
    a = mat.aco(aco)
    lig = nbr8800.ler_ligacao(ligacao)
    r = Resultado(elemento, perfil=perfil.nome, material=a.nome)
    Nc, Nt, M = abs(Nc) / n, abs(Nt) / n, abs(M) / n
    vc = None
    if Nc > 1e-6:
        # NBR 14762, item 9.7.4: KL/r ≤ 200 (antes o U 92×40 com 6 m, L/r = 484, passava)
        lam_x = Lx / perfil.rx if perfil.rx else 0.0
        lam_y = Ly / perfil.ry if perfil.ry else 0.0
        ve = Verificacao("Esbeltez da barra comprimida", norma="NBR 14762:2010, item 9.7.4",
                         Sd=max(lam_x, lam_y), Rd=nbr14762.ESBELTEZ_MAX_COMPRESSAO, unidade="")
        ve.passo("KL/r ≤ 200", "K<sub>x</sub>L<sub>x</sub>/r<sub>x</sub>; K<sub>y</sub>L<sub>y</sub>/r<sub>y</sub>",
                 "%s/%s; %s/%s" % (fmt(Lx, 0), fmt(perfil.rx), fmt(Ly, 0), fmt(perfil.ry)),
                 "%s; %s" % (fmt(lam_x, 1), fmt(lam_y, 1)), "item 9.7.4")
        r.add(ve)
        vc = nbr14762.compressao_mrd(sec, a, N_Sd=Nc, KxLx=Lx, KyLy=Ly, KtLt=Ly)
        r.add(vc)
    NRd_t = None
    if Nt > 1e-6:
        vt = Verificacao("Tração — escoamento da seção bruta", norma="NBR 14762:2010, item 9.6.2-a)",
                         Sd=Nt, Rd=sec.A * a.fy / nbr14762.GAMA, unidade="kN")
        vt.passo("N<sub>t,Rd</sub> = A·f<sub>y</sub>/γ", "", "%s × %s / 1,10" % (fmt(sec.A), fmt(a.fy)), fmt(vt.Rd, 1, "kN"))
        r.add(vt)
        NRd_t = vt.Rd
        if lig["ponta_ligada"]:
            # achado N11 (14/10/2026): a ruptura da seção líquida na ligação não era verificada
            vr = r.add(tracao_ruptura_frio(sec, a, Nt, ligacao, r))
            NRd_t = min(NRd_t, vr.Rd)
        else:
            vt.passo("Ruptura da seção líquida não verificada: " + TEXTO_SEM_PONTA, "—",
                     "ligação de ponta: não (%s)" % lig.get("fonte", ""), "vale o escoamento da seção bruta",
                     "NBR 14762:2010, item 9.6.2")
            vt.observacao = TEXTO_SEM_PONTA
            r.dados.update({"Ct": None, "Ct_adotado_sem_ligacao": False})
    r.dados["ponta_ligada"] = bool(lig["ponta_ligada"])
    vm = None
    if M > 1e-6:
        vm = nbr14762.flexao_mrd(sec, a, M_Sd=M, Lb=Ly, Lt=Ly)
        r.add(vm)
    if vm is not None and (vc is not None or Nt > 1e-6):
        # tração: Nt,Rd é o menor entre o escoamento e a ruptura (NBR 14762, item 9.6.2)
        NRd = vc.Rd if vc is not None else NRd_t
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
                       avisos: Optional[List[str]] = None, ligacao: Optional[dict] = None) -> Resultado:
    """Laminado, tubo, cantoneira ou barra redonda pela NBR 8800. `ligacao`: ver o topo do
    módulo (Ct da cantoneira e do U pela NBR 8800:2024, item 5.2.5-c; a cantoneira formada a
    frio tem a ruptura da seção líquida pela NBR 14762, item 9.6.2-c, dentro de `nbr8800.tracao`)."""
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
        rt = nbr8800.tracao(perfil, a, N_Sd=Nt, L=max(Lx, Ly), elemento=elemento, ligacao=ligacao)
        r.verificacoes.extend(rt.verificacoes)
        r.hipoteses.extend(rt.hipoteses)
        r.dados.update({"Ct": rt.dados["Ct"], "N_Rd_tracao": rt.dados["N_Rd"],
                        "Ct_adotado_sem_ligacao": rt.dados["Ct_adotado_sem_ligacao"],
                        "ponta_ligada": rt.dados["ponta_ligada"]})
    if not r.verificacoes:
        r.add(Verificacao("Sem esforço", Sd=0.0, Rd=1.0, unidade="—"))
    r.dados.update({"N_c": Nc * n, "N_t": Nt * n, "M": M * n, "Lx": Lx, "Ly": Ly, "n": n, "norma": "NBR 8800"})
    return r


def verificar_membro(perfil: Perfil, aco: str, Nc, Nt, M, Lx, Ly, n, elemento,
                     avisos: Optional[List[str]] = None, ligacao: Optional[dict] = None) -> Resultado:
    """Escolhe a norma pelo perfil e devolve o resultado; erro de dados vira 'não verificada'.
    `ligacao`: a ligação da extremidade para o Ct da tração (ver o topo do módulo)."""
    try:
        if perfis_fabrica.tipo_de_verificacao(perfil) == "frio":
            return verificar_frio(perfil, aco, Nc, Nt, M, Lx, Ly, n, elemento, ligacao=ligacao)
        return verificar_laminado(perfil, aco, Nc, Nt, M, Lx, Ly, n, elemento, avisos, ligacao=ligacao)
    except ErroDeDados as exc:
        r = Resultado(elemento, perfil=perfil.nome, material=aco)
        r.add(nao_verificada(exc))
        r.dados["erro"] = str(exc)
        return r


def serializar_resultado(r: Resultado) -> dict:
    """Resultado em dicionário simples, do jeito que a interface web consome."""
    return {"elemento": r.elemento, "perfil": r.perfil, "material": r.material, "razao": round(r.razao, 3),
            "ok": bool(r.ok), "indeterminada": bool(r.indeterminada),
            "verificacoes": [{"titulo": v.titulo, "norma": v.norma, "Sd": round(v.Sd, 3), "Rd": round(v.Rd, 3),
                              "unidade": v.unidade, "razao": round(v.razao, 3), "ok": bool(v.ok),
                              "indeterminada": bool(v.indeterminada),
                              "observacao": getattr(v, "observacao", "") or "",
                              "passos": [{"texto": p.texto, "formula": p.formula, "conta": p.conta, "valor": p.valor,
                                          "norma": p.norma} for p in v.passos]}
                             for v in r.verificacoes if not v.dispensada],
            "dados": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.dados.items()
                      if isinstance(v, (int, float, str, bool)) or v is None},
            "hipoteses": [{"chave": h.chave, "texto": h.texto, "fonte": h.fonte} for h in r.hipoteses],
            "cargas": [{"texto": p.texto, "formula": p.formula, "conta": p.conta, "valor": p.valor,
                        "norma": p.norma} for p in r.cargas]}
