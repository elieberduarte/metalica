# -*- coding: utf-8 -*-
"""Dimensionamento de barras de aço laminado e soldado — NBR 8800:2008.

Cobre os estados-limites do Capítulo 7 do manual:

    classificar()        classificação local da seção (Anexos F e G)
    tracao()             item 5.2
    compressao()         item 5.3 + Anexos E e F
    flexao()             item 5.4.2 + Anexo G
    cisalhamento()       item 5.4.3
    flexao_composta()    item 5.5.1.2
    flecha()             Anexo C (estado-limite de serviço)
    dimensionar_viga()   busca do perfil mais leve que atende
    dimensionar_pilar()

Unidades (obrigatórias em todo o sistema):
    força      kN
    momento    kN·cm
    tensão     kN/cm²
    dimensão   cm   (as dimensões do catálogo, `Perfil.d/.bf/.tw/.tf`, estão em mm
                     e são convertidas explicitamente aqui)
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

from .base import (Verificacao, Resultado, Passo, ErroDeDados, fmt,
                   E, G, GAMA_A1, GAMA_A2)
from . import materiais as mat
from .perfis import Perfil, banco

# ---------------------------------------------------------------------------
# utilitários internos
# ---------------------------------------------------------------------------


def _raiz_E_fy(fy: float) -> float:
    """√(E/fy) — aparece em quase todos os limites de esbeltez."""
    if fy <= 0:
        raise ErroDeDados("fy deve ser positivo (kN/cm²); recebido %r" % fy)
    return math.sqrt(E / fy)


def _aco(aco) -> "mat.Aco":
    """Aceita o objeto Aco ou o nome do aço."""
    return mat.aco(aco) if isinstance(aco, str) else aco


def _perfil_obj(p) -> Perfil:
    """Aceita o objeto Perfil ou o nome do perfil no catálogo."""
    return banco()[p] if isinstance(p, str) else p


def _regime(lam: float, lam_p: Optional[float], lam_r: float) -> str:
    """compacta / semicompacta / esbelta (NBR 8800, item 5.4.2.2).

    Em compressão axial não existe λp (a norma só define o limite acima do qual
    Q < 1): o elemento é "compacta" enquanto λ ≤ λr e "esbelta" acima disso.
    """
    if lam_p is None:
        return "compacta" if lam <= lam_r else "esbelta"
    if lam <= lam_p:
        return "compacta"
    if lam <= lam_r:
        return "semicompacta"
    return "esbelta"


def _circular(p: Perfil) -> bool:
    return p.tipo == "tubo" and p.dados.get("tipo") == "redondo"


def _h_alma_cm(p: Perfil) -> float:
    """Altura livre da alma, em cm.

    Perfil I: h = d − 2tf (a norma permite medir entre os raios de concordância;
    d − 2tf é ligeiramente a favor da segurança). Tubo retangular: h − 3t, como
    manda a Tabela F.1 para seções tubulares. Perfil U: d − 2t.
    """
    if p.tipo == "I":
        return p.h_alma / 10.0
    if p.tipo == "tubo" and not _circular(p):
        return (p.d - 3 * p.tw) / 10.0
    if p.tipo in ("U", "Ue"):
        return (p.d - 2 * p.tf) / 10.0
    return p.d / 10.0


def _b_mesa_cm(p: Perfil) -> float:
    """Largura do elemento comprimido da mesa, em cm (b da relação b/t)."""
    if p.tipo == "I":
        return p.bf / 20.0                      # metade da mesa (elemento AL)
    if p.tipo == "tubo" and not _circular(p):
        return (p.bf - 3 * p.tw) / 10.0         # parede AA: b = B − 3t
    if p.tipo in ("U", "Ue"):
        return p.bf / 10.0                      # mesa inteira (elemento AL)
    if p.tipo == "L":
        return p.bf / 10.0                      # aba inteira (elemento AL)
    return p.bf / 10.0


def _kc(p: Perfil) -> float:
    """Coeficiente kc de perfis soldados (NBR 8800, Tabela F.1, nota)."""
    lam_alma = _h_alma_cm(p) / (p.tw / 10.0)
    return min(0.76, max(0.35, 4.0 / math.sqrt(lam_alma))) if lam_alma > 0 else 0.76


def _cw_x0_U(p: Perfil) -> Tuple[float, float]:
    """Cw (cm⁶) e x0 (cm) de um perfil U, pela teoria de paredes finas.

    O catálogo de perfis U não traz Cw nem a posição do centro de cisalhamento;
    aqui eles são estimados com as expressões clássicas de Timoshenko para seção
    aberta de parede fina. É uma estimativa — fica registrada na observação da
    verificação que a usa.
    """
    tf = p.tf / 10.0
    tw = p.tw / 10.0
    bf = p.bf / 10.0
    d = p.d / 10.0
    b = bf - tw / 2.0                 # mesa medida do plano médio da alma
    h = d - tf                        # distância entre centros das mesas
    if min(b, h, tf, tw) <= 0:
        return 0.0, 0.0
    e = 3.0 * tf * b ** 2 / (6.0 * b * tf + h * tw)
    Cw = (tf * b ** 3 * h ** 2 / 12.0) * ((3.0 * b * tf + 2.0 * h * tw) /
                                          (6.0 * b * tf + h * tw))
    # centro de gravidade medido da face externa da alma
    A_alma = d * tw
    A_mesas = 2.0 * (bf - tw) * tf
    if A_alma + A_mesas <= 0:
        return Cw, 0.0
    xbar = (A_alma * tw / 2.0 + A_mesas * (tw + (bf - tw) / 2.0)) / (A_alma + A_mesas)
    x0 = e + (xbar - tw / 2.0)
    return Cw, x0


# ---------------------------------------------------------------------------
# 1. Classificação de seções (NBR 8800, Anexos F e G)
# ---------------------------------------------------------------------------


@dataclass
class Classe:
    """Classificação de um elemento (chapa) da seção."""
    elemento: str                    # "mesa", "alma", "parede", "aba"
    grupo: str                       # "AL" (apoiado-livre) ou "AA" (apoiado-apoiado)
    lam: float                       # esbeltez b/t
    lam_p: Optional[float]           # limite de seção compacta (None em compressão)
    lam_r: float                     # limite de seção semicompacta
    classe: str                      # compacta / semicompacta / esbelta
    norma: str = ""
    observacao: str = ""
    passos: List[Passo] = field(default_factory=list)

    @property
    def compacta(self) -> bool:
        return self.classe == "compacta"

    @property
    def esbelta(self) -> bool:
        return self.classe == "esbelta"


def _classe_para_verificacao(c: Classe, titulo: str) -> Verificacao:
    """Transforma a classificação num `Verificacao` (Sd = λ, Rd = λr)."""
    v = Verificacao(titulo, norma=c.norma, Sd=c.lam, Rd=c.lam_r, unidade="")
    for p in c.passos:
        v.passos.append(p)
    extra = ""
    if c.esbelta:
        extra = (" — λ > λr não é falha: a seção é esbelta e entra no cálculo "
                 "com Q < 1 (compressão) ou com o momento crítico elástico (flexão)")
    v.observacao = ((c.observacao + " " if c.observacao else "")
                    + f"classe: {c.classe}" + extra)
    return v


def classificar_mesa(perfil, aco, solicitacao: str = "flexao",
                     fabricacao: str = "laminado") -> Classe:
    """Classifica a mesa (ou a parede/aba equivalente) — NBR 8800, Tabelas F.1 e G.1.

    solicitacao: "flexao" (FLM) ou "compressao" (fator Qs / Qa).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    fy = a.fy
    r = _raiz_E_fy(fy)
    passos: List[Passo] = []

    if _circular(p):
        lam = (p.d / 10.0) / (p.tw / 10.0)
        if solicitacao == "flexao":
            lam_p, lam_r = 0.07 * E / fy, 0.31 * E / fy
            norma = "NBR 8800, Tabela G.1, caso 7 (tubo circular)"
        else:
            lam_p, lam_r = None, 0.11 * E / fy
            norma = "NBR 8800, item F.2 (tubo circular comprimido)"
        passos.append(Passo("Esbeltez da parede do tubo circular",
                            formula="λ = D/t",
                            conta=f"{fmt(p.d/10.0)} / {fmt(p.tw/10.0)}",
                            valor=fmt(lam), norma=norma))
        return Classe("parede", "AA", lam, lam_p, lam_r,
                      _regime(lam, lam_p, lam_r), norma, passos=passos)

    b = _b_mesa_cm(p)
    t = p.tf / 10.0
    if t <= 0:
        raise ErroDeDados(f"espessura da mesa nula no perfil {p.nome}")
    lam = b / t

    if p.tipo == "tubo":                     # parede AA de tubo retangular
        grupo, elemento = "AA", "parede (mesa)"
        if solicitacao == "flexao":
            lam_p, lam_r = 1.12 * r, 1.40 * r
            norma = "NBR 8800, Tabela G.1, caso 5 (mesa de tubo retangular)"
        else:
            lam_p, lam_r = None, 1.40 * r
            norma = "NBR 8800, Tabela F.1, grupo 6 (parede de tubo retangular)"
        formula = "λ = (B − 3t)/t"
    elif p.tipo == "L":
        grupo, elemento = "AL", "aba"
        if solicitacao == "flexao":
            lam_p, lam_r = 0.54 * r, 0.91 * r
            norma = ("NBR 8800 não cobre a flexão de cantoneira simples; "
                     "limites do AISC 360, item F10")
        else:
            lam_p, lam_r = None, 0.45 * r
            norma = "NBR 8800, Tabela F.1, grupo 3 (aba de cantoneira)"
        formula = "λ = b/t"
    else:                                    # I, H, U — mesa AL
        grupo, elemento = "AL", "mesa"
        formula = "λ = b<sub>f</sub>/(2t<sub>f</sub>)" if p.tipo == "I" else "λ = b<sub>f</sub>/t<sub>f</sub>"
        if solicitacao == "flexao":
            lam_p = 0.38 * r
            if fabricacao == "soldado":
                kc = _kc(p)
                lam_r = 0.95 * math.sqrt(E / (0.7 * fy / kc))
                norma = "NBR 8800, Tabela G.1, caso 2 (mesa de perfil soldado, σr = 0,3fy)"
            else:
                lam_r = 0.83 * math.sqrt(E / (0.7 * fy))
                norma = "NBR 8800, Tabela G.1, caso 1 (mesa de perfil laminado, σr = 0,3fy)"
        else:
            lam_p = None
            if fabricacao == "soldado":
                kc = _kc(p)
                lam_r = 0.64 * math.sqrt(E / (fy / kc))
                norma = "NBR 8800, Tabela F.1, grupo 2 (mesa de perfil soldado)"
            else:
                lam_r = 0.56 * r
                norma = "NBR 8800, Tabela F.1, grupo 1 (mesa de perfil laminado)"

    passos.append(Passo(f"Esbeltez da {elemento} (elemento {grupo})",
                        formula=formula,
                        conta=f"{fmt(b)} cm / {fmt(t)} cm",
                        valor=fmt(lam), norma=norma))
    if lam_p is not None:
        passos.append(Passo("Limite de seção compacta",
                            formula="λ<sub>p</sub> = %s·√(E/f<sub>y</sub>)" %
                                    ("0,38" if p.tipo not in ("tubo", "L") else
                                     ("1,12" if p.tipo == "tubo" else "0,54")),
                            conta=f"{fmt(lam_p/r, 3)} × {fmt(r)}",
                            valor=fmt(lam_p), norma=norma))
    passos.append(Passo("Limite de seção semicompacta",
                        formula="λ<sub>r</sub>",
                        conta=f"{fmt(lam_r/r, 3)} × √(E/f<sub>y</sub>) = {fmt(lam_r/r, 3)} × {fmt(r)}",
                        valor=fmt(lam_r), norma=norma))
    classe = _regime(lam, lam_p, lam_r)
    passos.append(Passo("Classificação da mesa", formula="λ vs λ<sub>p</sub>, λ<sub>r</sub>",
                        conta=f"{fmt(lam)} vs {fmt(lam_p) if lam_p else '—'} / {fmt(lam_r)}",
                        valor=classe, norma=norma))
    return Classe(elemento, grupo, lam, lam_p, lam_r, classe, norma, passos=passos)


def classificar_alma(perfil, aco, solicitacao: str = "flexao",
                     fabricacao: str = "laminado") -> Optional[Classe]:
    """Classifica a alma — NBR 8800, Tabelas F.1 e G.1.

    Devolve None para seções sem alma definida (tubo circular, cantoneira).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    fy = a.fy
    r = _raiz_E_fy(fy)
    if _circular(p) or p.tipo == "L":
        return None

    h = _h_alma_cm(p)
    tw = p.tw / 10.0
    if tw <= 0:
        raise ErroDeDados(f"espessura da alma nula no perfil {p.nome}")
    lam = h / tw

    if p.tipo == "tubo":
        if solicitacao == "flexao":
            lam_p, lam_r = 2.42 * r, 5.70 * r
            norma = "NBR 8800, Tabela G.1, caso 5 (alma de tubo retangular)"
        else:
            lam_p, lam_r = None, 1.40 * r
            norma = "NBR 8800, Tabela F.1, grupo 6 (parede de tubo retangular)"
        formula = "λ = (H − 3t)/t"
    else:
        if solicitacao == "flexao":
            lam_p, lam_r = 3.76 * r, 5.70 * r
            norma = "NBR 8800, Tabela G.1, casos 1 e 2 (alma em flexão)"
        else:
            lam_p, lam_r = None, 1.49 * r
            norma = "NBR 8800, Tabela F.1, grupo 5 (alma em compressão axial)"
        formula = "λ = h/t<sub>w</sub>"

    passos = [Passo("Esbeltez da alma (elemento AA)", formula=formula,
                    conta=f"{fmt(h)} cm / {fmt(tw)} cm", valor=fmt(lam), norma=norma)]
    if lam_p is not None:
        passos.append(Passo("Limite de seção compacta",
                            formula="λ<sub>p</sub>",
                            conta=f"{fmt(lam_p/r, 2)} × {fmt(r)}",
                            valor=fmt(lam_p), norma=norma))
    passos.append(Passo("Limite de seção semicompacta", formula="λ<sub>r</sub>",
                        conta=f"{fmt(lam_r/r, 2)} × {fmt(r)}", valor=fmt(lam_r), norma=norma))
    classe = _regime(lam, lam_p, lam_r)
    passos.append(Passo("Classificação da alma", formula="λ vs λ<sub>p</sub>, λ<sub>r</sub>",
                        conta=f"{fmt(lam)} vs {fmt(lam_p) if lam_p else '—'} / {fmt(lam_r)}",
                        valor=classe, norma=norma))
    return Classe("alma", "AA", lam, lam_p, lam_r, classe, norma, passos=passos)


_ORDEM_CLASSE = {"compacta": 0, "semicompacta": 1, "esbelta": 2}


def classificar(perfil, aco, solicitacao: str = "flexao",
                fabricacao: str = "laminado") -> Resultado:
    """Classificação da seção quanto à flambagem local (NBR 8800, Anexos F e G).

    solicitacao = "flexao" ou "compressao". A classe da seção é a pior entre a
    da mesa e a da alma. `r.dados` traz os objetos `Classe` de cada elemento.

    As verificações devolvidas são informativas (Sd = λ, Rd = λr): ultrapassar
    λr não é uma falha, apenas leva a seção esbelta ao cálculo com Q < 1
    (compressão) ou com o momento crítico elástico (flexão).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    if solicitacao not in ("flexao", "compressao"):
        raise ErroDeDados("solicitação deve ser 'flexao' ou 'compressao'; "
                          f"recebido {solicitacao!r}")
    r = Resultado(f"Classificação da seção ({solicitacao})", perfil=p.nome, material=a.nome)
    mesa = classificar_mesa(p, a, solicitacao, fabricacao)
    alma = classificar_alma(p, a, solicitacao, fabricacao)
    r.add(_classe_para_verificacao(mesa, f"Flambagem local da mesa — {solicitacao}"))
    if alma is not None:
        r.add(_classe_para_verificacao(alma, f"Flambagem local da alma — {solicitacao}"))
    classes = [mesa.classe] + ([alma.classe] if alma else [])
    geral = max(classes, key=lambda c: _ORDEM_CLASSE[c])
    r.dados.update({"mesa": mesa, "alma": alma, "classe": geral,
                    "solicitacao": solicitacao, "fabricacao": fabricacao})
    return r


# ---------------------------------------------------------------------------
# 2. Barras tracionadas (NBR 8800, item 5.2)
# ---------------------------------------------------------------------------

ESBELTEZ_MAX_TRACAO = 300.0      # item 5.2.8
ESBELTEZ_MAX_COMPRESSAO = 200.0  # item 5.3.4


def area_liquida(Ag: float, t: float, n_furos: int = 0, d_furo: float = 0.0,
                 ziguezague: Sequence[Tuple[float, float]] = ()) -> Tuple[float, List[Passo]]:
    """Área líquida An (cm²) — NBR 8800, item 5.2.4.

    Ag, t em cm; `d_furo` já acrescido dos 2 mm de dano de puncionamento
    (use `desconto_furo()`). `ziguezague` = pares (s, g) em cm dos trechos
    inclinados da linha de ruptura, que devolvem s²/(4g) à largura.
    """
    passos: List[Passo] = []
    desc = n_furos * d_furo * t
    zig = sum(s ** 2 / (4.0 * g) for s, g in ziguezague) * t if ziguezague else 0.0
    An = Ag - desc + zig
    passos.append(Passo("Área líquida da seção",
                        formula="A<sub>n</sub> = A<sub>g</sub> − Σ(d+3,5 mm)·t + Σ s²/(4g)·t",
                        conta=f"{fmt(Ag)} − {n_furos} × {fmt(d_furo)} × {fmt(t)}"
                              + (f" + {fmt(zig / t if t else 0.0, 3)} × {fmt(t)}" if zig else ""),
                        valor=fmt(An, 2, "cm²"), norma="NBR 8800, item 5.2.4.2"))
    if An > Ag:
        An = Ag
        passos.append(Passo("Limite An <= Ag", formula="A<sub>n</sub> ≤ A<sub>g</sub>",
                            conta="a linha em ziguezague recuperou mais do que a seção bruta",
                            valor=fmt(An, 2, "cm²"), norma="NBR 8800, item 5.2.4.2"))
    return An, passos


def desconto_furo(d_parafuso: float = 0.0, d_furo: float = None) -> float:
    """Largura descontada por furo, em cm (NBR 8800, item 5.2.4.2).

    Furo-padrão: d_furo = d_parafuso + 1,5 mm; a norma manda ainda somar 2 mm
    pelo dano do puncionamento, de modo que o desconto é d_parafuso + 3,5 mm.
    """
    if d_furo is not None:
        return d_furo + 0.2
    if d_parafuso <= 0:
        return 0.0
    return d_parafuso + 0.35


def coeficiente_Ct(Ct: float = None, ec: float = None, lc: float = None,
                   todos_elementos_ligados: bool = False) -> Tuple[float, Passo]:
    """Coeficiente Ct de área líquida efetiva (NBR 8800, item 5.2.5)."""
    if Ct is not None:
        return float(Ct), Passo("Coeficiente Ct (valor adotado)", formula="C<sub>t</sub>",
                                conta="valor informado", valor=fmt(Ct, 3),
                                norma="NBR 8800, item 5.2.5")
    if todos_elementos_ligados:
        return 1.0, Passo("Coeficiente Ct", formula="C<sub>t</sub> = 1,0",
                          conta="todos os elementos da seção ligados",
                          valor="1,000", norma="NBR 8800, item 5.2.5.1")
    if ec is not None and lc is not None:
        if lc <= 0:
            raise ErroDeDados("comprimento da ligação lc deve ser positivo (cm)")
        Ct_calc = 1.0 - ec / lc
        return Ct_calc, Passo("Coeficiente Ct pela excentricidade da ligação",
                              formula="C<sub>t</sub> = 1 − e<sub>c</sub>/ℓ<sub>c</sub>",
                              conta=f"1 − {fmt(ec)} / {fmt(lc)}", valor=fmt(Ct_calc, 3),
                              norma="NBR 8800, item 5.2.5.2")
    raise ErroDeDados("informe Ct, ou ec e lc (NBR 8800, item 5.2.5), ou "
                      "todos_elementos_ligados=True")


def tracao(perfil, aco, N_Sd: float = 0.0, L: float = 0.0, n_furos: int = 0,
           d_parafuso: float = 0.0, d_furo: float = None, t_furo: float = None,
           ziguezague: Sequence[Tuple[float, float]] = (), Ct: float = None,
           ec: float = None, lc: float = None, rosqueada: bool = False,
           pretensionada: bool = False, elemento: str = "Barra tracionada") -> Resultado:
    """Barra tracionada — NBR 8800, item 5.2.

    Nt,Rd = Ag·fy/γa1 (escoamento da seção bruta) e Nt,Rd = Ae·fu/γa2 com
    Ae = Ct·An (ruptura da seção líquida). Verifica ainda L/r <= 300
    (item 5.2.8), dispensado em barras redondas pré-tensionadas.

    Comprimentos em cm, esforços em kN, `ziguezague` = pares (s, g) em cm.
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    Ag = p.A
    if Ag <= 0:
        raise ErroDeDados(f"área bruta nula ou ausente no perfil {p.nome}")
    if n_furos and not (d_parafuso or d_furo):
        raise ErroDeDados("com n_furos > 0 informe d_parafuso ou d_furo, em cm")
    r = Resultado(elemento, perfil=p.nome, material=a.nome)

    # --- escoamento da seção bruta (eq. 7.2) ---
    N_esc = Ag * a.fy / GAMA_A1
    v1 = Verificacao("Tração — escoamento da seção bruta",
                     norma="NBR 8800:2008, item 5.2.2 (a)",
                     Sd=N_Sd, Rd=N_esc, unidade="kN")
    v1.passo("Força resistente ao escoamento da seção bruta",
             formula="N<sub>t,Rd</sub> = A<sub>g</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
             conta=f"{fmt(Ag)} × {fmt(a.fy)} / {fmt(GAMA_A1)}",
             valor=fmt(N_esc, 1, "kN"), norma="item 5.2.2 (a)")
    r.add(v1)

    # --- ruptura da seção líquida (eq. 7.3) ---
    t = t_furo if t_furo is not None else (p.tw / 10.0)
    if rosqueada:
        An, Ct_ef = Ag, 1.0
        Ae = 0.75 * Ag
        passos = [Passo("Área efetiva da parte rosqueada",
                        formula="A<sub>e</sub> = 0,75·A<sub>g</sub>",
                        conta=f"0,75 × {fmt(Ag)}", valor=fmt(Ae, 2, "cm²"),
                        norma="NBR 8800, item 5.2.8 (barras redondas rosqueadas)")]
    else:
        d_desc = desconto_furo(d_parafuso, d_furo)
        An, passos = area_liquida(Ag, t, n_furos, d_desc, ziguezague)
        if n_furos:
            passos.insert(0, Passo("Desconto por furo",
                                   formula="d<sub>desc</sub> = d + 3,5 mm",
                                   conta=f"{fmt(d_parafuso)} + 0,35",
                                   valor=fmt(d_desc, 2, "cm"),
                                   norma="NBR 8800, item 5.2.4.2"))
        todos = (n_furos == 0 and Ct is None and ec is None)
        Ct_ef, passo_ct = coeficiente_Ct(Ct, ec, lc, todos_elementos_ligados=todos)
        passos.append(passo_ct)
        Ae = Ct_ef * An
        passos.append(Passo("Área líquida efetiva",
                            formula="A<sub>e</sub> = C<sub>t</sub>·A<sub>n</sub>",
                            conta=f"{fmt(Ct_ef, 3)} × {fmt(An)}",
                            valor=fmt(Ae, 2, "cm²"), norma="NBR 8800, item 5.2.3"))
    N_rup = Ae * a.fu / GAMA_A2
    v2 = Verificacao("Tração — ruptura da seção líquida",
                     norma="NBR 8800:2008, item 5.2.2 (b)",
                     Sd=N_Sd, Rd=N_rup, unidade="kN")
    for passo in passos:
        v2.passos.append(passo)
    v2.passo("Força resistente à ruptura da seção líquida",
             formula="N<sub>t,Rd</sub> = A<sub>e</sub>·f<sub>u</sub>/γ<sub>a2</sub>",
             conta=f"{fmt(Ae)} × {fmt(a.fu)} / {fmt(GAMA_A2)}",
             valor=fmt(N_rup, 1, "kN"), norma="item 5.2.2 (b)")
    r.add(v2)

    # --- esbeltez (item 5.2.8) ---
    rmin = p.rmin
    v3 = Verificacao("Esbeltez da barra tracionada",
                     norma="NBR 8800:2008, item 5.2.8", unidade="")
    if pretensionada:
        v3.dispensada = True
        v3.observacao = ("barra redonda pré-tensionada por esticador: a norma "
                         "dispensa o limite L/r <= 300")
    elif L > 0 and rmin > 0:
        v3.Sd, v3.Rd = L / rmin, ESBELTEZ_MAX_TRACAO
        v3.passo("Índice de esbeltez", formula="L/r ≤ 300",
                 conta=f"{fmt(L)} / {fmt(rmin)}", valor=fmt(L / rmin, 0),
                 norma="item 5.2.8")
    else:
        v3.dispensada = True
        v3.observacao = "comprimento não informado — esbeltez não verificada"
    r.add(v3)

    N_Rd = min(N_esc, N_rup)
    r.dados.update({"Ag": Ag, "An": An, "Ae": Ae, "Ct": Ct_ef, "N_Rd": N_Rd,
                    "N_Rd_escoamento": N_esc, "N_Rd_ruptura": N_rup,
                    "governa": "escoamento" if N_esc < N_rup else "ruptura",
                    "esbeltez": (L / rmin) if (L > 0 and rmin > 0) else None})
    return r


# ---------------------------------------------------------------------------
# 3. Barras comprimidas (NBR 8800, item 5.3 e Anexos E e F)
# ---------------------------------------------------------------------------


def largura_efetiva(b: float, t: float, fy: float, sigma: float = None,
                    ca: float = 0.34) -> float:
    """Largura efetiva bef de um elemento AA comprimido (NBR 8800, eq. F.4).

    bef = 1,92·t·√(E/σ)·[1 − (ca/(b/t))·√(E/σ)] ≤ b, com σ = tensão que pode
    atuar no elemento (aqui, conservadoramente, σ = fy) e ca = 0,34 para almas
    e 0,38 para paredes de tubos retangulares.
    """
    s = sigma if sigma else fy
    if t <= 0 or b <= 0:
        return b
    raiz = math.sqrt(E / s)
    bef = 1.92 * t * raiz * (1.0 - (ca / (b / t)) * raiz)
    return min(b, max(0.0, bef))


def fator_Q(perfil, aco, sigma: float = None,
            fabricacao: str = "laminado") -> Tuple[float, float, float, List[Passo]]:
    """Fator de redução por flambagem local Q = Qs·Qa (NBR 8800, Anexo F).

    Devolve (Q, Qs, Qa, passos). Qs reduz a tensão nos elementos AL; Qa reduz a
    área dos elementos AA pela largura efetiva (eq. F.4).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    fy = a.fy
    raiz = _raiz_E_fy(fy)
    passos: List[Passo] = []

    # --- tubo circular: a norma dá Q diretamente (item F.2) ---
    if _circular(p):
        lam = (p.d / 10.0) / (p.tw / 10.0)
        lim1, lim2 = 0.11 * E / fy, 0.45 * E / fy
        if lam > lim2:
            raise ErroDeDados(
                f"tubo circular com D/t = {lam:.1f} acima do limite 0,45E/fy = "
                f"{lim2:.1f}: fora do campo de aplicação da NBR 8800 (item F.2)")
        if lam <= lim1:
            Q = 1.0
            conta = f"D/t = {fmt(lam)} ≤ 0,11·E/f_y = {fmt(lim1)}"
        else:
            Q = 0.038 * E / (fy * lam) + 2.0 / 3.0
            conta = f"0,038 × {fmt(E, 0)} / ({fmt(fy)} × {fmt(lam)}) + 2/3"
        passos.append(Passo("Fator Q do tubo circular",
                            formula="Q = 0,038·E/(f<sub>y</sub>·D/t) + 2/3",
                            conta=conta, valor=fmt(Q, 3),
                            norma="NBR 8800, item F.2"))
        return Q, Q, 1.0, passos

    # --- Qs: elementos AL ---
    Qs = 1.0
    if p.tipo in ("I", "U", "Ue", "L"):
        b = _b_mesa_cm(p)
        t = p.tf / 10.0
        lam = b / t
        if p.tipo == "L":
            lim1, lim2 = 0.45 * raiz, 0.91 * raiz
            norma = "NBR 8800, item F.1 (grupo 3 — abas de cantoneira)"
            if lam <= lim1:
                Qs = 1.0
            elif lam <= lim2:
                Qs = 1.340 - 0.76 * lam * math.sqrt(fy / E)
            else:
                Qs = 0.53 * E / (fy * lam ** 2)
        elif fabricacao == "soldado":
            kc = _kc(p)
            lim1 = 0.64 * math.sqrt(E / (fy / kc))
            lim2 = 1.17 * math.sqrt(E / (fy / kc))
            norma = "NBR 8800, item F.1 (grupo 2 — mesas de perfis soldados)"
            if lam <= lim1:
                Qs = 1.0
            elif lam <= lim2:
                Qs = 1.415 - 0.65 * lam * math.sqrt(fy / (kc * E))
            else:
                Qs = 0.90 * E * kc / (fy * lam ** 2)
        else:
            lim1, lim2 = 0.56 * raiz, 1.03 * raiz
            norma = "NBR 8800, item F.1 (grupo 1 — mesas de perfis laminados)"
            if lam <= lim1:
                Qs = 1.0
            elif lam <= lim2:
                Qs = 1.415 - 0.74 * lam * math.sqrt(fy / E)
            else:
                Qs = 0.69 * E / (fy * lam ** 2)
        passos.append(Passo("Fator Qs (elemento AL — mesa/aba)",
                            formula="Q<sub>s</sub> = 1,0 se b/t ≤ λ<sub>1</sub>; "
                                    "expressão do Anexo F acima disso",
                            conta=f"b/t = {fmt(lam)}; λ<sub>1</sub> = {fmt(lim1)}; "
                                  f"λ<sub>2</sub> = {fmt(lim2)}",
                            valor=fmt(Qs, 3), norma=norma))

    # --- Qa: elementos AA ---
    Ag = p.A
    if Ag <= 0:
        raise ErroDeDados(f"área bruta nula ou ausente no perfil {p.nome}")
    perda = 0.0
    elementos: List[Tuple[str, float, float, float]] = []   # (nome, b, t, ca)
    if p.tipo == "tubo":
        t = p.tw / 10.0
        elementos = [("mesa do tubo", _b_mesa_cm(p), t, 0.38),
                     ("mesa do tubo", _b_mesa_cm(p), t, 0.38),
                     ("alma do tubo", _h_alma_cm(p), t, 0.38),
                     ("alma do tubo", _h_alma_cm(p), t, 0.38)]
        lim_AA = 1.40 * raiz
    elif p.tipo in ("I", "U", "Ue"):
        elementos = [("alma", _h_alma_cm(p), p.tw / 10.0, 0.34)]
        lim_AA = 1.49 * raiz
    else:
        lim_AA = None

    for nome, b, t, ca in elementos:
        lam = b / t if t else 0.0
        if lam <= lim_AA:
            passos.append(Passo(f"Elemento AA — {nome}: totalmente efetivo",
                                formula="b/t ≤ λ<sub>lim</sub>",
                                conta=f"{fmt(lam)} ≤ {fmt(lim_AA)}",
                                valor="b<sub>ef</sub> = b",
                                norma="NBR 8800, item F.3"))
            continue
        bef = largura_efetiva(b, t, fy, sigma, ca)
        perda += (b - bef) * t
        s = sigma if sigma else fy
        passos.append(Passo(f"Largura efetiva do elemento AA — {nome}",
                            formula="b<sub>ef</sub> = 1,92·t·√(E/σ)·[1 − (c<sub>a</sub>/(b/t))·√(E/σ)] ≤ b",
                            conta=f"1,92 × {fmt(t)} × {fmt(math.sqrt(E / s))} × "
                                  f"[1 − ({fmt(ca, 2)}/{fmt(lam)}) × {fmt(math.sqrt(E / s))}]",
                            valor=fmt(bef, 2, "cm"), norma="NBR 8800, eq. F.4"))

    Aef = Ag - perda
    Qa = Aef / Ag
    if elementos:
        passos.append(Passo("Fator Qa (área efetiva)",
                            formula="Q<sub>a</sub> = A<sub>ef</sub>/A<sub>g</sub>, "
                                    "A<sub>ef</sub> = A<sub>g</sub> − Σ(b − b<sub>ef</sub>)·t",
                            conta=f"({fmt(Ag)} − {fmt(perda)}) / {fmt(Ag)}",
                            valor=fmt(Qa, 3), norma="NBR 8800, item F.3"))
    Q = Qs * Qa
    passos.append(Passo("Fator de flambagem local",
                        formula="Q = Q<sub>s</sub>·Q<sub>a</sub>",
                        conta=f"{fmt(Qs, 3)} × {fmt(Qa, 3)}", valor=fmt(Q, 3),
                        norma="NBR 8800, Anexo F"))
    return Q, Qs, Qa, passos


def fator_chi(lambda_0: float) -> float:
    """Fator de redução da força axial de compressão resistente (item 5.3.3).

    χ = 0,658^(λ0²) para λ0 ≤ 1,5 e χ = 0,877/λ0² para λ0 > 1,5.
    """
    if lambda_0 < 0:
        raise ErroDeDados("λ0 não pode ser negativo")
    if lambda_0 == 0:
        return 1.0
    if lambda_0 <= 1.5:
        return 0.658 ** (lambda_0 ** 2)
    return 0.877 / lambda_0 ** 2


def forcas_flambagem_elastica(perfil, Lx: float, Ly: float = None, Kx: float = 1.0,
                              Ky: float = 1.0, Lt: float = None, Kt: float = 1.0,
                              x0: float = None, y0: float = None
                              ) -> Tuple[dict, List[Passo]]:
    """Forças axiais de flambagem elástica Ne por todos os modos (Anexo E).

    Devolve um dicionário com Nex, Ney, Nez (torção) e Neyz/Nexz (flexo-torção,
    quando a seção tem um só eixo de simetria), e a memória de cálculo.
    Comprimentos em cm; o comprimento de torção KtLt, quando não informado,
    é tomado como o maior entre KxLx e KyLy (a favor da segurança).
    """
    p = _perfil_obj(perfil)
    Ly = Lx if Ly is None else Ly
    if Lx <= 0 or Ly <= 0:
        raise ErroDeDados("comprimentos de flambagem devem ser positivos (cm)")
    passos: List[Passo] = []
    KLx, KLy = Kx * Lx, Ky * Ly
    KLt = (Kt * Lt) if Lt else max(KLx, KLy)

    Nex = math.pi ** 2 * E * p.Ix / KLx ** 2
    Ney = math.pi ** 2 * E * p.Iy / KLy ** 2
    passos.append(Passo("Flambagem elástica por flexão em x",
                        formula="N<sub>ex</sub> = π²·E·I<sub>x</sub>/(K<sub>x</sub>L<sub>x</sub>)²",
                        conta=f"π² × {fmt(E, 0)} × {fmt(p.Ix, 0)} / {fmt(KLx, 0)}²",
                        valor=fmt(Nex, 0, "kN"), norma="NBR 8800, item E.1.1"))
    passos.append(Passo("Flambagem elástica por flexão em y",
                        formula="N<sub>ey</sub> = π²·E·I<sub>y</sub>/(K<sub>y</sub>L<sub>y</sub>)²",
                        conta=f"π² × {fmt(E, 0)} × {fmt(p.Iy, 0)} / {fmt(KLy, 0)}²",
                        valor=fmt(Ney, 0, "kN"), norma="NBR 8800, item E.1.1"))
    modos = {"Nex": Nex, "Ney": Ney}

    # --- torção e flexo-torção ---
    J = p.J
    Cw = p.Cw
    obs_estimado = False
    if p.tipo in ("U", "Ue") and (Cw <= 0 or x0 is None):
        Cw_est, x0_est = _cw_x0_U(p)
        Cw = Cw if Cw > 0 else Cw_est
        x0 = x0 if x0 is not None else x0_est
        obs_estimado = True
    x0 = x0 or 0.0
    y0 = y0 or 0.0

    if J > 0 and p.A > 0:
        r0_2 = (p.Ix + p.Iy) / p.A + x0 ** 2 + y0 ** 2
        Nez = (math.pi ** 2 * E * Cw / KLt ** 2 + G * J) / r0_2
        modos["Nez"] = Nez
        passos.append(Passo("Flambagem elástica por torção",
                            formula="N<sub>ez</sub> = [π²·E·C<sub>w</sub>/(K<sub>z</sub>L<sub>z</sub>)² "
                                    "+ G·J] / r<sub>0</sub>²",
                            conta=f"[π² × {fmt(E, 0)} × {fmt(Cw, 0)} / {fmt(KLt, 0)}² + "
                                  f"{fmt(G, 0)} × {fmt(J)}] / {fmt(r0_2)}",
                            valor=fmt(Nez, 0, "kN"),
                            norma="NBR 8800, item E.1.1" +
                                  (" (Cw e x0 estimados pela teoria de paredes finas)"
                                   if obs_estimado else "")))
        # flexo-torção: seções com um eixo de simetria (U com x0 ≠ 0)
        if abs(x0) > 1e-9:
            H = 1.0 - (x0 ** 2 + y0 ** 2) / r0_2
            soma = Nex + Nez
            Nexz = (soma / (2.0 * H)) * (1.0 - math.sqrt(max(0.0,
                     1.0 - 4.0 * Nex * Nez * H / soma ** 2)))
            modos["Nexz"] = Nexz
            passos.append(Passo("Flambagem elástica por flexo-torção",
                                formula="N<sub>exz</sub> = (N<sub>ex</sub>+N<sub>ez</sub>)/(2H)·"
                                        "[1 − √(1 − 4·N<sub>ex</sub>·N<sub>ez</sub>·H/(N<sub>ex</sub>+N<sub>ez</sub>)²)]",
                                conta=f"H = {fmt(H, 3)}; N<sub>ex</sub> = {fmt(Nex, 0)}; "
                                      f"N<sub>ez</sub> = {fmt(Nez, 0)}",
                                valor=fmt(Nexz, 0, "kN"), norma="NBR 8800, item E.1.2"))
            # no modo acoplado, Nex deixa de valer isoladamente
            modos.pop("Nex")
            modos.pop("Nez")
    else:
        passos.append(Passo("Flambagem por torção",
                            formula="N<sub>ez</sub>",
                            conta="constante de torção J não disponível no catálogo",
                            valor="não verificada", norma="NBR 8800, item E.1.1"))
    return modos, passos


def esbeltez_equivalente_cantoneira(perfil, L: float) -> Tuple[float, Passo]:
    """(KL/r)ef de cantoneira simples ligada por uma aba (NBR 8800, item E.1.4)."""
    p = _perfil_obj(perfil)
    rx = p.rx or p.rmin
    if rx <= 0:
        raise ErroDeDados(f"raio de giração indisponível no perfil {p.nome}")
    lam = L / rx
    if lam <= 80:
        ef = 60.0 + 0.8 * lam
        conta = f"60 + 0,8 × {fmt(lam)}"
    else:
        ef = 45.0 + lam
        conta = f"45 + {fmt(lam)}"
    return ef, Passo("Esbeltez equivalente da cantoneira ligada por uma aba",
                     formula="(KL/r)<sub>ef</sub> = 60 + 0,8·L/r<sub>x</sub> (L/r<sub>x</sub> ≤ 80); "
                             "45 + L/r<sub>x</sub> (acima)",
                     conta=conta, valor=fmt(ef), norma="NBR 8800, item E.1.4")


def compressao(perfil, aco, Lx: float, Ly: float = None, Kx: float = 1.0, Ky: float = 1.0,
               Lt: float = None, Kt: float = 1.0, N_Sd: float = 0.0,
               x0: float = None, y0: float = None, fabricacao: str = "laminado",
               cantoneira_simplificada: bool = False,
               elemento: str = "Barra comprimida") -> Resultado:
    """Barra comprimida — NBR 8800, item 5.3.

    Nc,Rd = χ·Q·Ag·fy/γa1, com λ0 = √(Q·Ag·fy/Ne), Ne = menor força de flambagem
    elástica entre os modos aplicáveis (flexão em x, flexão em y, torção e
    flexo-torção) e χ pela curva única do item 5.3.3. Verifica KL/r ≤ 200.

    Comprimentos em cm, forças em kN. `Lt` é o comprimento destravado à torção;
    se não informado, adota-se o maior entre KxLx e KyLy (a favor da segurança).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    Ly = Lx if Ly is None else Ly
    Ag, fy = p.A, a.fy
    if Ag <= 0:
        raise ErroDeDados(f"área bruta nula ou ausente no perfil {p.nome}")
    r = Resultado(elemento, perfil=p.nome, material=a.nome)

    # --- fator Q ---
    Q, Qs, Qa, passos_Q = fator_Q(p, a, fabricacao=fabricacao)

    # --- esbeltez ---
    rx, ry = p.rx, p.ry
    lam_x = Kx * Lx / rx if rx else 0.0
    lam_y = Ky * Ly / ry if ry else 0.0
    if cantoneira_simplificada:
        lam_ef, passo_ef = esbeltez_equivalente_cantoneira(p, Lx)
        lam_max = lam_ef
    else:
        passo_ef = None
        lam_max = max(lam_x, lam_y)
    v_esb = Verificacao("Esbeltez da barra comprimida",
                        norma="NBR 8800:2008, item 5.3.4",
                        Sd=lam_max, Rd=ESBELTEZ_MAX_COMPRESSAO, unidade="")
    v_esb.passo("Índice de esbeltez em x", formula="K<sub>x</sub>L<sub>x</sub>/r<sub>x</sub>",
                conta=f"{fmt(Kx, 2)} × {fmt(Lx, 0)} / {fmt(rx)}", valor=fmt(lam_x, 1),
                norma="item 5.3.4")
    v_esb.passo("Índice de esbeltez em y", formula="K<sub>y</sub>L<sub>y</sub>/r<sub>y</sub>",
                conta=f"{fmt(Ky, 2)} × {fmt(Ly, 0)} / {fmt(ry)}", valor=fmt(lam_y, 1),
                norma="item 5.3.4")
    if passo_ef:
        v_esb.passos.append(passo_ef)
    r.add(v_esb)

    # --- forças de flambagem elástica ---
    if cantoneira_simplificada:
        Ne = math.pi ** 2 * E * Ag / lam_max ** 2
        modos = {"Ne (esbeltez equivalente)": Ne}
        passos_Ne = [Passo("Força de flambagem elástica pela esbeltez equivalente",
                           formula="N<sub>e</sub> = π²·E·A<sub>g</sub>/(KL/r)<sub>ef</sub>²",
                           conta=f"π² × {fmt(E, 0)} × {fmt(Ag)} / {fmt(lam_max)}²",
                           valor=fmt(Ne, 0, "kN"), norma="NBR 8800, item E.1.4")]
    else:
        modos, passos_Ne = forcas_flambagem_elastica(p, Lx, Ly, Kx, Ky, Lt, Kt, x0, y0)
        Ne = min(modos.values())
    modo_critico = min(modos, key=lambda k: modos[k])

    lambda_0 = math.sqrt(Q * Ag * fy / Ne)
    chi = fator_chi(lambda_0)
    Nc_Rd = chi * Q * Ag * fy / GAMA_A1

    v = Verificacao("Compressão — flambagem global",
                    norma="NBR 8800:2008, item 5.3.3", Sd=N_Sd, Rd=Nc_Rd, unidade="kN")
    for passo in passos_Q:
        v.passos.append(passo)
    for passo in passos_Ne:
        v.passos.append(passo)
    v.passo("Força de flambagem elástica adotada",
            formula="N<sub>e</sub> = menor entre os modos",
            conta="; ".join(f"{k} = {fmt(val, 0)}" for k, val in modos.items()),
            valor=f"{fmt(Ne, 0, 'kN')} ({modo_critico})", norma="NBR 8800, Anexo E")
    v.passo("Índice de esbeltez reduzido",
            formula="λ<sub>0</sub> = √(Q·A<sub>g</sub>·f<sub>y</sub>/N<sub>e</sub>)",
            conta=f"√({fmt(Q, 3)} × {fmt(Ag)} × {fmt(fy)} / {fmt(Ne, 0)})",
            valor=fmt(lambda_0, 3), norma="item 5.3.3")
    v.passo("Fator de redução χ",
            formula=("χ = 0,658<sup>λ0²</sup>" if lambda_0 <= 1.5 else "χ = 0,877/λ<sub>0</sub>²"),
            conta=(f"0,658^{fmt(lambda_0 ** 2, 3)}" if lambda_0 <= 1.5
                   else f"0,877 / {fmt(lambda_0 ** 2, 3)}"),
            valor=fmt(chi, 3), norma="item 5.3.3")
    v.passo("Força axial resistente de cálculo",
            formula="N<sub>c,Rd</sub> = χ·Q·A<sub>g</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(chi, 3)} × {fmt(Q, 3)} × {fmt(Ag)} × {fmt(fy)} / {fmt(GAMA_A1)}",
            valor=fmt(Nc_Rd, 0, "kN"), norma="item 5.3.2")
    if p.tipo == "L" and not cantoneira_simplificada:
        v.observacao = ("cantoneira simples: a flambagem por flexo-torção depende da "
                        "posição do centro de cisalhamento, que o catálogo não traz. "
                        "Para diagonais de treliça ligadas por uma aba use "
                        "cantoneira_simplificada=True (NBR 8800, item E.1.4)")
    r.add(v)

    r.dados.update({"Q": Q, "Qs": Qs, "Qa": Qa, "Ne": Ne, "modos_Ne": modos,
                    "modo_critico": modo_critico, "lambda_0": lambda_0, "chi": chi,
                    "N_Rd": Nc_Rd, "esbeltez": lam_max, "lambda_x": lam_x,
                    "lambda_y": lam_y, "Lx": Lx, "Ly": Ly, "Kx": Kx, "Ky": Ky})
    return r


# ---------------------------------------------------------------------------
# 4. Vigas: flexão (NBR 8800, item 5.4.2 e Anexo G)
# ---------------------------------------------------------------------------

# Valores de Cb tabelados para os diagramas usuais (manual, Tabela 7.7)
CB_TABELADO = {
    "uniforme": 1.00,
    "distribuida": 1.14,
    "distribuida_travada_meio": 1.30,
    "distribuida_travada_tercos": 1.01,
    "concentrada_meio": 1.32,
    "linear_ate_zero": 1.67,
    "curvatura_reversa": 2.27,
    "balanco": 1.00,
}


def calcular_cb(momentos: Sequence[float]) -> float:
    """Fator de modificação Cb (NBR 8800, item 5.4.2.3; eq. 7.16 do manual).

    Cb = 12,5·Mmáx / (2,5·Mmáx + 3·MA + 4·MB + 3·MC) ≤ 3,0

    `momentos` pode ser:
      * 4 valores — (Mmáx, MA, MB, MC) no trecho destravado;
      * 5 valores — os momentos em 0, L/4, L/2, 3L/4 e L do trecho destravado
        (Mmáx é o maior valor absoluto entre eles).
    Todos os momentos entram em valor absoluto.
    """
    m = [abs(float(x)) for x in momentos]
    if len(m) == 4:
        Mmax, MA, MB, MC = m
    elif len(m) == 5:
        MA, MB, MC = m[1], m[2], m[3]
        Mmax = max(m)
    else:
        raise ErroDeDados("informe 4 momentos (Mmáx, MA, MB, MC) ou 5 momentos "
                          "ao longo do trecho destravado")
    den = 2.5 * Mmax + 3 * MA + 4 * MB + 3 * MC
    if den <= 0:
        return 1.0
    return min(3.0, 12.5 * Mmax / den)


def cb_tabelado(caso: str) -> float:
    """Cb dos diagramas usuais (manual, Tabela 7.7)."""
    if caso not in CB_TABELADO:
        raise ErroDeDados(f"caso de Cb desconhecido: {caso}. "
                          f"Disponíveis: {', '.join(CB_TABELADO)}")
    return CB_TABELADO[caso]


def comprimento_Lp(perfil, aco) -> float:
    """Lp = 1,76·ry·√(E/fy) (NBR 8800, Tabela G.1; eq. 7.13 do manual), em cm."""
    p, a = _perfil_obj(perfil), _aco(aco)
    return 1.76 * p.ry * _raiz_E_fy(a.fy)


def comprimento_Lr(perfil, aco) -> float:
    """Lr completo do Anexo G para perfil I/U fletido em x (eq. 7.14), em cm."""
    p, a = _perfil_obj(perfil), _aco(aco)
    J, Cw, Iy, Wx, ry = p.J, p.Cw, p.Iy, p.Wx, p.ry
    if p.tipo in ("U", "Ue") and Cw <= 0:
        Cw = _cw_x0_U(p)[0]
    if J <= 0 or Cw <= 0 or Iy <= 0:
        raise ErroDeDados(f"perfil {p.nome} sem J/Cw/Iy para calcular Lr")
    beta1 = 0.7 * a.fy * Wx / (E * J)
    lam_r = (1.38 * math.sqrt(Iy * J) / (ry * J * beta1)) * \
        math.sqrt(1.0 + math.sqrt(1.0 + 27.0 * Cw * beta1 ** 2 / Iy))
    return lam_r * ry


def _teto_flexao(Mn: float, W: float, fy: float) -> Tuple[float, Optional[Passo]]:
    """Teto Mn ≤ 1,5·W·fy (NBR 8800, item 5.4.2.1)."""
    teto = 1.5 * W * fy
    if Mn <= teto:
        return Mn, None
    return teto, Passo("Teto de momento resistente",
                       formula="M<sub>Rd</sub> ≤ 1,5·W·f<sub>y</sub>/γ<sub>a1</sub>",
                       conta=f"1,5 × {fmt(W, 0)} × {fmt(fy)}",
                       valor=fmt(teto, 0, "kN·cm"), norma="NBR 8800, item 5.4.2.1")


def _interpolar(Mpl: float, Mr: float, lam: float, lam_p: float, lam_r: float) -> float:
    """Regime inelástico: interpolação linear entre Mpl e Mr (eq. 7.12)."""
    return Mpl - (Mpl - Mr) * (lam - lam_p) / (lam_r - lam_p)


def _verificacao_flm(p, a, eixo, W, Z, Mpl, M_Sd, fabricacao) -> Verificacao:
    """Flambagem local da mesa comprimida (FLM) — Anexo G."""
    fy = a.fy
    c = classificar_mesa(p, a, "flexao", fabricacao)
    v = Verificacao("Flexão — flambagem local da mesa (FLM)",
                    norma="NBR 8800:2008, Anexo G (Tabela G.1)", Sd=M_Sd, unidade="kN·cm")
    for passo in c.passos:
        v.passos.append(passo)
    lam, lam_p, lam_r = c.lam, c.lam_p, c.lam_r
    if _circular(p):
        Mr = 0.0
        if lam <= lam_p:
            Mn = Mpl
        elif lam <= lam_r:
            Mn = (0.021 * E / lam + fy) * W
        else:
            Mn = 0.33 * E * W / lam
    else:
        Mr = (fy if p.tipo == "tubo" else 0.7 * fy) * W
        if lam <= lam_p:
            Mn = Mpl
        elif lam <= lam_r:
            Mn = _interpolar(Mpl, Mr, lam, lam_p, lam_r)
        else:
            if p.tipo == "tubo":
                # largura efetiva da mesa comprimida (Tabela G.1, nota)
                t = p.tw / 10.0
                bef = largura_efetiva(_b_mesa_cm(p), t, fy, ca=0.38)
                Wef = W * (1.0 - (_b_mesa_cm(p) - bef) * t / p.A)
                Mn = Wef * fy
                v.observacao = ("mesa esbelta: módulo resistente efetivo estimado "
                                "pela largura efetiva da mesa comprimida")
            elif fabricacao == "soldado":
                Mn = 0.90 * E * _kc(p) * W / lam ** 2
            else:
                Mn = 0.69 * E * W / lam ** 2
    v.passo("Momento de plastificação",
            formula="M<sub>pl</sub> = Z·f<sub>y</sub>",
            conta=f"{fmt(Z, 0)} × {fmt(fy)}", valor=fmt(Mpl, 0, "kN·cm"),
            norma="NBR 8800, item 5.4.2.2")
    if Mr:
        v.passo("Momento de início de escoamento com tensões residuais",
                formula="M<sub>r</sub> = (f<sub>y</sub> − σ<sub>r</sub>)·W" if p.tipo != "tubo"
                        else "M<sub>r</sub> = f<sub>y</sub>·W",
                conta=f"{fmt(0.7 * fy if p.tipo != 'tubo' else fy)} × {fmt(W, 0)}",
                valor=fmt(Mr, 0, "kN·cm"), norma="Tabela G.1")
    v.passo(f"Momento nominal (regime {c.classe})",
            formula="M<sub>n</sub> conforme a faixa de λ",
            conta=f"λ = {fmt(lam)}; λ<sub>p</sub> = {fmt(lam_p)}; λ<sub>r</sub> = {fmt(lam_r)}",
            valor=fmt(Mn, 0, "kN·cm"), norma="Anexo G, eq. G.2/G.3")
    Mn, passo_teto = _teto_flexao(Mn, W, fy)
    if passo_teto:
        v.passos.append(passo_teto)
    v.Rd = Mn / GAMA_A1
    v.passo("Momento resistente de cálculo",
            formula="M<sub>Rd</sub> = M<sub>n</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Mn, 0)} / {fmt(GAMA_A1)}", valor=fmt(v.Rd, 0, "kN·cm"),
            norma="item 5.4.2.1")
    return v


def _verificacao_fla(p, a, eixo, W, Z, Mpl, M_Sd, fabricacao) -> Verificacao:
    """Flambagem local da alma (FLA) — Anexo G."""
    fy = a.fy
    v = Verificacao("Flexão — flambagem local da alma (FLA)",
                    norma="NBR 8800:2008, Anexo G (Tabela G.1)", Sd=M_Sd, unidade="kN·cm")
    c = classificar_alma(p, a, "flexao", fabricacao)
    if c is None or eixo == "y":
        v.dispensada = True
        v.observacao = ("seção sem alma comprimida em flexão neste eixo" if eixo == "y"
                        else "seção sem alma definida (tubo circular ou cantoneira)")
        v.Rd = _teto_flexao(Mpl, W, fy)[0] / GAMA_A1
        return v
    for passo in c.passos:
        v.passos.append(passo)
    Mr = fy * W
    if c.lam <= c.lam_p:
        Mn = Mpl
    elif c.lam <= c.lam_r:
        Mn = _interpolar(Mpl, Mr, c.lam, c.lam_p, c.lam_r)
    else:
        # alma esbelta: fora do Anexo G (a norma remete ao Anexo H).
        aw = min(10.0, (_h_alma_cm(p) * p.tw / 10.0) / (p.bf / 10.0 * p.tf / 10.0))
        Rpg = min(1.0, 1.0 - aw / (1200.0 + 300.0 * aw) *
                  (c.lam - 5.70 * _raiz_E_fy(fy)))
        Mn = Rpg * fy * W
        v.observacao = ("alma esbelta: caso fora do Anexo G. Adotado o "
                        "procedimento simplificado de viga de alma esbelta "
                        "(Anexo H), com R_pg reduzindo M_r; verificar o Anexo H "
                        "na íntegra antes do projeto final")
    v.passo(f"Momento nominal (regime {c.classe})",
            formula="M<sub>n</sub> = M<sub>pl</sub> − (M<sub>pl</sub>−M<sub>r</sub>)·"
                    "(λ−λ<sub>p</sub>)/(λ<sub>r</sub>−λ<sub>p</sub>)",
            conta=f"λ = {fmt(c.lam)}; λ<sub>p</sub> = {fmt(c.lam_p)}; "
                  f"λ<sub>r</sub> = {fmt(c.lam_r)}; M<sub>r</sub> = {fmt(Mr, 0)}",
            valor=fmt(Mn, 0, "kN·cm"), norma="Anexo G, Tabela G.1")
    Mn, passo_teto = _teto_flexao(Mn, W, fy)
    if passo_teto:
        v.passos.append(passo_teto)
    v.Rd = Mn / GAMA_A1
    v.passo("Momento resistente de cálculo",
            formula="M<sub>Rd</sub> = M<sub>n</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Mn, 0)} / {fmt(GAMA_A1)}", valor=fmt(v.Rd, 0, "kN·cm"),
            norma="item 5.4.2.1")
    return v


def _verificacao_flt(p, a, eixo, W, Z, Mpl, M_Sd, Lb, Cb) -> Verificacao:
    """Flambagem lateral com torção (FLT) — Anexo G."""
    fy = a.fy
    v = Verificacao("Flexão — flambagem lateral com torção (FLT)",
                    norma="NBR 8800:2008, Anexo G (Tabela G.1)", Sd=M_Sd, unidade="kN·cm")
    if Lb <= 0 or eixo == "y" or _circular(p):
        v.dispensada = True
        v.Rd = _teto_flexao(Mpl, W, fy)[0] / GAMA_A1
        v.observacao = ("mesa comprimida contida continuamente (Lb = 0)" if Lb <= 0
                        else "flexão em torno do eixo de menor inércia ou seção "
                             "circular: não há FLT")
        return v

    ry = p.ry
    lam = Lb / ry
    lam_p = 1.76 * _raiz_E_fy(fy)
    v.passo("Esbeltez do trecho destravado", formula="λ = L<sub>b</sub>/r<sub>y</sub>",
            conta=f"{fmt(Lb, 0)} / {fmt(ry)}", valor=fmt(lam), norma="Tabela G.1")
    v.passo("Comprimento destravado para plastificação",
            formula="L<sub>p</sub> = 1,76·r<sub>y</sub>·√(E/f<sub>y</sub>)",
            conta=f"1,76 × {fmt(ry)} × {fmt(_raiz_E_fy(fy))}",
            valor=fmt(lam_p * ry, 0, "cm"), norma="Tabela G.1 (eq. 7.13)")

    if p.tipo == "tubo":                       # seção fechada — Tabela G.1, caso 5
        J, Ag = p.J, p.A
        if J <= 0:
            raise ErroDeDados(f"tubo {p.nome} sem constante de torção J no catálogo")
        Mr = fy * W
        raizJA = math.sqrt(J * Ag)
        lam_p = 0.13 * E * raizJA / Mpl
        lam_r = 2.0 * E * raizJA / Mr
        if lam <= lam_p:
            Mn = Mpl
        elif lam <= lam_r:
            Mn = min(Mpl, Cb * _interpolar(Mpl, Mr, lam, lam_p, lam_r))
        else:
            Mn = min(Mpl, 2.0 * Cb * E * raizJA / lam)
        norma_caso = "Tabela G.1, caso 5 (seção tubular retangular)"
    else:                                      # perfil I bissimétrico ou U
        J, Cw, Iy = p.J, p.Cw, p.Iy
        if p.tipo in ("U", "Ue") and Cw <= 0:
            Cw = _cw_x0_U(p)[0]
            v.observacao = ("C<sub>w</sub> estimado pela teoria de paredes finas "
                            "(o catálogo de perfis U não traz o valor)")
        if J <= 0 or Cw <= 0:
            raise ErroDeDados(f"perfil {p.nome} sem J/Cw para verificar a FLT")
        Mr = 0.7 * fy * W
        beta1 = 0.7 * fy * W / (E * J)
        lam_r = (1.38 * math.sqrt(Iy * J) / (ry * J * beta1)) * \
            math.sqrt(1.0 + math.sqrt(1.0 + 27.0 * Cw * beta1 ** 2 / Iy))
        v.passo("Parâmetro β1",
                formula="β<sub>1</sub> = 0,7·f<sub>y</sub>·W<sub>x</sub>/(E·J)",
                conta=f"0,7 × {fmt(fy)} × {fmt(W, 0)} / ({fmt(E, 0)} × {fmt(J)})",
                valor=fmt(beta1, 5, "cm⁻¹"), norma="Tabela G.1")
        v.passo("Comprimento destravado limite (regime elástico)",
                formula="λ<sub>r</sub> = [1,38·√(I<sub>y</sub>·J)/(r<sub>y</sub>·J·β<sub>1</sub>)]·"
                        "√(1 + √(1 + 27·C<sub>w</sub>·β<sub>1</sub>²/I<sub>y</sub>))",
                conta=f"I<sub>y</sub> = {fmt(Iy, 0)}; J = {fmt(J)}; C<sub>w</sub> = {fmt(Cw, 0)}",
                valor=f"λ<sub>r</sub> = {fmt(lam_r)} → L<sub>r</sub> = {fmt(lam_r * ry, 0, 'cm')}",
                norma="Tabela G.1 (eq. 7.14)")
        if lam <= lam_p:
            Mn = Mpl
        elif lam <= lam_r:
            Mn = min(Mpl, Cb * _interpolar(Mpl, Mr, lam, lam_p, lam_r))
        else:
            Mcr = Cb * (math.pi ** 2 * E * Iy / Lb ** 2) * \
                math.sqrt((Cw / Iy) * (1.0 + 0.039 * J * Lb ** 2 / Cw))
            Mn = min(Mpl, Mcr)
            v.passo("Momento crítico elástico",
                    formula="M<sub>cr</sub> = C<sub>b</sub>·(π²·E·I<sub>y</sub>/L<sub>b</sub>²)·"
                            "√((C<sub>w</sub>/I<sub>y</sub>)·(1 + 0,039·J·L<sub>b</sub>²/C<sub>w</sub>))",
                    conta=f"C<sub>b</sub> = {fmt(Cb, 2)}; π²·E·I<sub>y</sub>/L<sub>b</sub>² = "
                          f"{fmt(math.pi ** 2 * E * Iy / Lb ** 2)}",
                    valor=fmt(Mcr, 0, "kN·cm"), norma="Tabela G.1 (eq. 7.15)")
        norma_caso = "Tabela G.1, caso 1 (perfil I bissimétrico / U fletido em x)"

    regime = "compacta" if lam <= lam_p else ("semicompacta" if lam <= lam_r else "esbelta")
    v.passo(f"Momento nominal (regime {regime})",
            formula="M<sub>n</sub> = C<sub>b</sub>·[M<sub>pl</sub> − (M<sub>pl</sub>−M<sub>r</sub>)·"
                    "(λ−λ<sub>p</sub>)/(λ<sub>r</sub>−λ<sub>p</sub>)] ≤ M<sub>pl</sub>",
            conta=f"C<sub>b</sub> = {fmt(Cb, 2)}; λ = {fmt(lam)}; λ<sub>p</sub> = {fmt(lam_p)}; "
                  f"λ<sub>r</sub> = {fmt(lam_r)}; M<sub>pl</sub> = {fmt(Mpl, 0)}; "
                  f"M<sub>r</sub> = {fmt(Mr, 0)}",
            valor=fmt(Mn, 0, "kN·cm"), norma=norma_caso)
    Mn, passo_teto = _teto_flexao(Mn, W, fy)
    if passo_teto:
        v.passos.append(passo_teto)
    v.Rd = Mn / GAMA_A1
    v.passo("Momento resistente de cálculo",
            formula="M<sub>Rd</sub> = M<sub>n</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Mn, 0)} / {fmt(GAMA_A1)}", valor=fmt(v.Rd, 0, "kN·cm"),
            norma="item 5.4.2.1")
    v.dados_flt = {"Lp": lam_p * ry, "Lr": lam_r * ry, "lambda": lam, "Mn": Mn}
    return v


def flexao(perfil, aco, M_Sd: float = 0.0, Lb: float = 0.0, Cb: float = 1.0,
           eixo: str = "x", fabricacao: str = "laminado",
           elemento: str = "Viga") -> Resultado:
    """Momento fletor resistente — NBR 8800, item 5.4.2 e Anexo G.

    Devolve as três verificações separadas (FLA, FLM e FLT), de modo que o
    memorial mostre qual estado-limite governa. Momentos em kN·cm, Lb em cm.

    Perfis cobertos: I bissimétrico (laminado ou soldado), U, tubo retangular e
    tubo circular. Cb ≥ 1,0 (use `calcular_cb()` ou `cb_tabelado()`).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    if eixo not in ("x", "y"):
        raise ErroDeDados("eixo deve ser 'x' ou 'y'")
    if Lb < 0:
        raise ErroDeDados("Lb não pode ser negativo (cm)")
    if Cb < 1.0:
        raise ErroDeDados("Cb deve ser ≥ 1,0 (NBR 8800, item 5.4.2.3)")
    if p.tipo == "L":
        raise ErroDeDados("a NBR 8800 não cobre a flexão de cantoneira simples; "
                          "use o AISC 360 item F10 ou evite o caso no projeto")
    W = p.Wx if eixo == "x" else p.Wy
    Z = p.Zx if eixo == "x" else p.Zy
    if W <= 0 or Z <= 0:
        raise ErroDeDados(f"perfil {p.nome} sem módulo resistente no eixo {eixo}")
    Mpl = Z * a.fy

    r = Resultado(elemento, perfil=p.nome, material=a.nome)
    v_fla = _verificacao_fla(p, a, eixo, W, Z, Mpl, M_Sd, fabricacao)
    v_flm = _verificacao_flm(p, a, eixo, W, Z, Mpl, M_Sd, fabricacao)
    v_flt = _verificacao_flt(p, a, eixo, W, Z, Mpl, M_Sd, Lb, Cb)
    r.add(v_fla)
    r.add(v_flm)
    r.add(v_flt)
    M_Rd = min(v.Rd for v in (v_fla, v_flm, v_flt))
    # o estado-limite que governa é procurado entre as verificações que se
    # aplicam; as dispensadas carregam apenas o teto Mpl (ou 1,5·W·fy)
    ativos = [v for v in (v_fla, v_flm, v_flt) if not v.dispensada]
    governa = min(ativos or [v_fla, v_flm, v_flt], key=lambda v: v.Rd).titulo
    r.dados.update({"Mpl": Mpl, "M_Rd": M_Rd, "W": W, "Z": Z, "Lb": Lb, "Cb": Cb,
                    "eixo": eixo, "governa": governa,
                    "M_Rd_FLA": v_fla.Rd, "M_Rd_FLM": v_flm.Rd, "M_Rd_FLT": v_flt.Rd})
    if not v_flt.dispensada and p.tipo != "tubo":
        r.dados["Lp"] = comprimento_Lp(p, a)
        try:
            r.dados["Lr"] = comprimento_Lr(p, a)
        except ErroDeDados:
            r.dados["Lr"] = None
    return r


# ---------------------------------------------------------------------------
# 5. Cisalhamento (NBR 8800, item 5.4.3)
# ---------------------------------------------------------------------------


def coeficiente_kv(h: float, tw: float, a_enrij: float = None) -> Tuple[float, Passo]:
    """Coeficiente de flambagem por cisalhamento kv (NBR 8800, item 5.4.3.1)."""
    if a_enrij is None or h <= 0 or a_enrij / h > 3.0:
        return 5.0, Passo("Coeficiente de flambagem por cisalhamento",
                          formula="k<sub>v</sub> = 5,0",
                          conta="alma sem enrijecedores transversais (ou a/h > 3)",
                          valor="5,00", norma="NBR 8800, item 5.4.3.1")
    razao = a_enrij / h
    kv = 5.0 + 5.0 / razao ** 2
    return kv, Passo("Coeficiente de flambagem por cisalhamento",
                     formula="k<sub>v</sub> = 5 + 5/(a/h)²",
                     conta=f"5 + 5/({fmt(razao, 2)})²", valor=fmt(kv),
                     norma="NBR 8800, item 5.4.3.1")


def cisalhamento(perfil, aco, V_Sd: float = 0.0, a_enrij: float = None,
                 Aw: float = None, elemento: str = "Viga") -> Verificacao:
    """Força cortante resistente — NBR 8800, item 5.4.3.

    Vpl = 0,60·Aw·fy com Aw = d·tw; λ = h/tw, λp = 1,10√(kv·E/fy) e
    λr = 1,37√(kv·E/fy); três regimes (plástico, inelástico e elástico).
    `a_enrij` = espaçamento dos enrijecedores transversais, em cm.
    """
    p = _perfil_obj(perfil)
    ac = _aco(aco)
    fy = ac.fy
    Aw = p.Aw if Aw is None else Aw
    if Aw <= 0:
        raise ErroDeDados(f"área de cisalhamento nula no perfil {p.nome}")
    h = _h_alma_cm(p)
    tw = p.tw / 10.0
    lam = h / tw

    v = Verificacao("Cortante — força cortante resistente",
                    norma="NBR 8800:2008, item 5.4.3", Sd=V_Sd, unidade="kN")
    Vpl = 0.60 * Aw * fy
    v.passo("Força cortante de plastificação da alma",
            formula="V<sub>pl</sub> = 0,60·A<sub>w</sub>·f<sub>y</sub>, A<sub>w</sub> = d·t<sub>w</sub>",
            conta=f"0,60 × {fmt(Aw)} × {fmt(fy)}", valor=fmt(Vpl, 0, "kN"),
            norma="item 5.4.3.1 (eq. 7.17)")
    kv, passo_kv = coeficiente_kv(h, tw, a_enrij)
    v.passos.append(passo_kv)
    lam_p = 1.10 * math.sqrt(kv * E / fy)
    lam_r = 1.37 * math.sqrt(kv * E / fy)
    v.passo("Esbeltez da alma e limites",
            formula="λ = h/t<sub>w</sub>; λ<sub>p</sub> = 1,10√(k<sub>v</sub>E/f<sub>y</sub>); "
                    "λ<sub>r</sub> = 1,37√(k<sub>v</sub>E/f<sub>y</sub>)",
            conta=f"λ = {fmt(h)}/{fmt(tw)} = {fmt(lam)}; λ<sub>p</sub> = {fmt(lam_p)}; "
                  f"λ<sub>r</sub> = {fmt(lam_r)}",
            valor=fmt(lam), norma="item 5.4.3.1 (eq. 7.18)")
    if lam <= lam_p:
        Vn, regime = Vpl, "plástico (escoamento da alma)"
        conta = f"{fmt(Vpl, 0)}"
        formula = "V<sub>n</sub> = V<sub>pl</sub>"
    elif lam <= lam_r:
        Vn, regime = (lam_p / lam) * Vpl, "inelástico"
        conta = f"({fmt(lam_p)}/{fmt(lam)}) × {fmt(Vpl, 0)}"
        formula = "V<sub>n</sub> = (λ<sub>p</sub>/λ)·V<sub>pl</sub>"
    else:
        Vn, regime = 1.24 * (lam_p / lam) ** 2 * Vpl, "elástico (flambagem da alma)"
        conta = f"1,24 × ({fmt(lam_p)}/{fmt(lam)})² × {fmt(Vpl, 0)}"
        formula = "V<sub>n</sub> = 1,24·(λ<sub>p</sub>/λ)²·V<sub>pl</sub>"
    v.passo(f"Força cortante nominal — regime {regime}", formula=formula,
            conta=conta, valor=fmt(Vn, 0, "kN"), norma="item 5.4.3.1 (eq. 7.19)")
    v.Rd = Vn / GAMA_A1
    v.passo("Força cortante resistente de cálculo",
            formula="V<sub>Rd</sub> = V<sub>n</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Vn, 0)} / {fmt(GAMA_A1)}", valor=fmt(v.Rd, 0, "kN"),
            norma="item 5.4.3.1")
    v.observacao = f"regime {regime}; k_v = {kv:.2f}".replace(".", ",")
    return v


# ---------------------------------------------------------------------------
# 6. Flexão composta (NBR 8800, item 5.5.1.2)
# ---------------------------------------------------------------------------


def flexao_composta(perfil, aco, N_Sd: float = 0.0, Mx_Sd: float = 0.0, My_Sd: float = 0.0,
                    tipo_axial: str = "compressao", Lx: float = 0.0, Ly: float = None,
                    Kx: float = 1.0, Ky: float = 1.0, Lt: float = None, Kt: float = 1.0,
                    Lb: float = 0.0, Cb: float = 1.0, N_Rd: float = None,
                    Mx_Rd: float = None, My_Rd: float = None,
                    fabricacao: str = "laminado", tracao_kwargs: dict = None,
                    elemento: str = "Barra sob flexão composta") -> Resultado:
    """Flexão composta — NBR 8800, item 5.5.1.2 (eqs. 7.20 e 7.21 do manual).

    Para N_Sd/N_Rd ≥ 0,2:  N/N_Rd + (8/9)·(Mx/Mx,Rd + My/My,Rd) ≤ 1,0
    Para N_Sd/N_Rd < 0,2:  N/(2·N_Rd) + (Mx/Mx,Rd + My/My,Rd) ≤ 1,0

    As resistências são calculadas aqui (compressão ou tração e flexão nos dois
    eixos) a menos que sejam informadas em N_Rd, Mx_Rd e My_Rd. Os esforços
    solicitantes devem chegar já com os efeitos de 2ª ordem (B1 e B2).
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    if tipo_axial not in ("compressao", "tracao"):
        raise ErroDeDados("tipo_axial deve ser 'compressao' ou 'tracao'")
    r = Resultado(elemento, perfil=p.nome, material=a.nome)

    if N_Rd is None:
        if tipo_axial == "compressao":
            res_n = compressao(p, a, Lx, Ly, Kx, Ky, Lt, Kt, N_Sd=abs(N_Sd),
                               fabricacao=fabricacao)
        else:
            res_n = tracao(p, a, N_Sd=abs(N_Sd), L=Lx, **(tracao_kwargs or {}))
        for v in res_n.verificacoes:
            r.add(v)
        N_Rd = res_n.dados["N_Rd"]
        r.dados.update({k: val for k, val in res_n.dados.items() if k != "governa"})
    if Mx_Rd is None and Mx_Sd:
        res_mx = flexao(p, a, M_Sd=abs(Mx_Sd), Lb=Lb, Cb=Cb, eixo="x",
                        fabricacao=fabricacao)
        for v in res_mx.verificacoes:
            r.add(v)
        Mx_Rd = res_mx.dados["M_Rd"]
    if My_Rd is None and My_Sd:
        res_my = flexao(p, a, M_Sd=abs(My_Sd), Lb=Lb, Cb=Cb, eixo="y",
                        fabricacao=fabricacao)
        for v in res_my.verificacoes:
            r.add(v)
        My_Rd = res_my.dados["M_Rd"]

    if not N_Rd:
        raise ErroDeDados("força axial resistente nula ou não calculada")
    razao_n = abs(N_Sd) / N_Rd
    termo_mx = abs(Mx_Sd) / Mx_Rd if Mx_Sd else 0.0
    termo_my = abs(My_Sd) / My_Rd if My_Sd else 0.0

    v = Verificacao(f"Interação força axial ({tipo_axial}) + momentos",
                    norma="NBR 8800:2008, item 5.5.1.2", Rd=1.0, unidade="")
    v.passo("Razão da força axial",
            formula="N<sub>Sd</sub>/N<sub>Rd</sub>",
            conta=f"{fmt(abs(N_Sd), 1)} / {fmt(N_Rd, 1)}", valor=fmt(razao_n, 3),
            norma="item 5.5.1.2")
    if razao_n >= 0.2:
        valor = razao_n + (8.0 / 9.0) * (termo_mx + termo_my)
        formula = ("N<sub>Sd</sub>/N<sub>Rd</sub> + (8/9)·(M<sub>x,Sd</sub>/M<sub>x,Rd</sub> "
                   "+ M<sub>y,Sd</sub>/M<sub>y,Rd</sub>) ≤ 1,0")
        conta = f"{fmt(razao_n, 3)} + (8/9) × ({fmt(termo_mx, 3)} + {fmt(termo_my, 3)})"
        ramo = "N/N_Rd ≥ 0,2 (eq. 7.20)"
    else:
        valor = razao_n / 2.0 + (termo_mx + termo_my)
        formula = ("N<sub>Sd</sub>/(2·N<sub>Rd</sub>) + (M<sub>x,Sd</sub>/M<sub>x,Rd</sub> "
                   "+ M<sub>y,Sd</sub>/M<sub>y,Rd</sub>) ≤ 1,0")
        conta = f"{fmt(razao_n, 3)}/2 + ({fmt(termo_mx, 3)} + {fmt(termo_my, 3)})"
        ramo = "N/N_Rd < 0,2 (eq. 7.21)"
    v.Sd = valor
    v.passo(f"Equação de interação — ramo {ramo}", formula=formula, conta=conta,
            valor=fmt(valor, 3), norma="item 5.5.1.2")
    r.add(v)
    r.dados.update({"N_Rd": N_Rd, "Mx_Rd": Mx_Rd, "My_Rd": My_Rd,
                    "razao_N": razao_n, "razao_Mx": termo_mx, "razao_My": termo_my,
                    "interacao": valor, "ramo": ramo})
    return r


# ---------------------------------------------------------------------------
# 7. Estados-limites de serviço (NBR 8800, Anexo C)
# ---------------------------------------------------------------------------

# Deslocamentos máximos do Anexo C (Tabela C.1) — denominador de L
LIMITES_FLECHA = {
    "travessa": 120,
    "terca": 180,
    "terca_total": 250,
    "viga_cobertura": 250,
    "viga_piso": 350,
    "viga_alvenaria": 500,
    "viga_rolamento": 600,
    "viga_rolamento_pesada": 800,
    "pilar_topo": 300,
    "entre_pisos": 400,
}

CASOS_FLECHA = {
    "biapoiada_distribuida": ("δ = 5·q·L⁴/(384·E·I)", lambda q, P, L, I: 5.0 * q * L ** 4 / (384.0 * E * I)),
    "biapoiada_concentrada": ("δ = P·L³/(48·E·I)", lambda q, P, L, I: P * L ** 3 / (48.0 * E * I)),
    "balanco_distribuida": ("δ = q·L⁴/(8·E·I)", lambda q, P, L, I: q * L ** 4 / (8.0 * E * I)),
    "balanco_concentrada": ("δ = P·L³/(3·E·I)", lambda q, P, L, I: P * L ** 3 / (3.0 * E * I)),
    "biengastada_distribuida": ("δ = q·L⁴/(384·E·I)", lambda q, P, L, I: q * L ** 4 / (384.0 * E * I)),
    "biengastada_concentrada": ("δ = P·L³/(192·E·I)", lambda q, P, L, I: P * L ** 3 / (192.0 * E * I)),
    "engastada_apoiada_distribuida": ("δ = q·L⁴/(185·E·I)", lambda q, P, L, I: q * L ** 4 / (185.0 * E * I)),
}


def flecha_caso(caso: str, L: float, I: float, q: float = 0.0,
                P: float = 0.0) -> Tuple[float, str, str]:
    """Flecha elástica dos casos usuais, em cm (resistência dos materiais).

    L em cm, I em cm⁴, q em kN/cm, P em kN. Devolve (δ, fórmula, conta).
    """
    if caso not in CASOS_FLECHA:
        raise ErroDeDados(f"caso de flecha desconhecido: {caso}. "
                          f"Disponíveis: {', '.join(CASOS_FLECHA)}")
    if L <= 0 or I <= 0:
        raise ErroDeDados("vão e momento de inércia devem ser positivos (cm, cm⁴)")
    formula, func = CASOS_FLECHA[caso]
    d = func(q, P, L, I)
    carga = f"q = {fmt(q, 4)} kN/cm" if "distribuida" in caso else f"P = {fmt(P, 1)} kN"
    conta = f"{carga}; L = {fmt(L, 0)} cm; E = {fmt(E, 0)}; I = {fmt(I, 0)} cm⁴"
    return d, formula, conta


def limite_flecha(limite, L: float) -> Tuple[float, float]:
    """Interpreta o limite de flecha; devolve (δ_limite em cm, denominador)."""
    if isinstance(limite, (int, float)):
        den = float(limite)
    elif isinstance(limite, str):
        s = limite.strip().replace(" ", "")
        if s.upper().startswith("L/"):
            den = float(s[2:].replace(",", "."))
        elif s in LIMITES_FLECHA:
            den = float(LIMITES_FLECHA[s])
        else:
            raise ErroDeDados(f"limite de flecha desconhecido: {limite}. Use 'L/350', "
                              f"um número, ou um de: {', '.join(LIMITES_FLECHA)}")
    else:
        raise ErroDeDados("limite de flecha deve ser um número ou uma string 'L/n'")
    if den <= 0:
        raise ErroDeDados("denominador do limite de flecha deve ser positivo")
    return L / den, den


def flecha(perfil, L: float, caso: str = "biapoiada_distribuida", q: float = 0.0,
           P: float = 0.0, limite="L/350", Ix: float = None, contraflecha: float = 0.0,
           elemento: str = "Viga") -> Verificacao:
    """Estado-limite de serviço de deslocamento — NBR 8800, Anexo C.

    Cargas de serviço (sem majoração) e rigidez elástica. Em balanços o vão
    equivalente é 2L, como manda a Tabela C.1. `limite` aceita "L/250", "L/350",
    "L/180", o nome do elemento ("viga_piso", "terca"...) ou o denominador.
    """
    p = _perfil_obj(perfil) if not isinstance(perfil, (int, float)) else None
    I = Ix if Ix is not None else (p.Ix if p else 0.0)
    d, formula, conta = flecha_caso(caso, L, I, q, P)
    d = max(0.0, d - contraflecha)
    L_ref = 2.0 * L if caso.startswith("balanco") else L
    d_lim, den = limite_flecha(limite, L_ref)

    v = Verificacao("Deslocamento vertical (ELS)",
                    norma="NBR 8800:2008, Anexo C (Tabela C.1)",
                    Sd=d, Rd=d_lim, unidade="cm")
    v.passo("Flecha sob carga de serviço", formula=formula, conta=conta,
            valor=fmt(d, 2, "cm"), norma="análise elástica")
    if contraflecha:
        v.passo("Contraflecha descontada", formula="δ<sub>ef</sub> = δ − δ<sub>contraflecha</sub>",
                conta=f"− {fmt(contraflecha, 2)} cm", valor=fmt(d, 2, "cm"),
                norma="NBR 8800, Anexo C")
    v.passo("Deslocamento máximo admitido",
            formula=f"δ<sub>lim</sub> = L/{den:.0f}",
            conta=f"{fmt(L_ref, 0)} / {den:.0f}"
                  + (" (vão equivalente 2L, balanço)" if caso.startswith("balanco") else ""),
            valor=fmt(d_lim, 2, "cm"), norma="Anexo C, Tabela C.1")
    if p is not None:
        v.observacao = f"perfil {p.nome}, I = {fmt(I, 0)} cm⁴"
    return v


# ---------------------------------------------------------------------------
# 8. Verificação completa e busca automática de perfil
# ---------------------------------------------------------------------------


def esforcos_viga(caso: str, L: float, q: float = 0.0, P: float = 0.0) -> Tuple[float, float]:
    """Momento (kN·cm) e cortante (kN) máximos dos casos usuais.

    L em cm, q em kN/cm, P em kN.
    """
    if caso == "biapoiada_distribuida":
        return q * L ** 2 / 8.0, q * L / 2.0
    if caso == "biapoiada_concentrada":
        return P * L / 4.0, P / 2.0
    if caso == "balanco_distribuida":
        return q * L ** 2 / 2.0, q * L
    if caso == "balanco_concentrada":
        return P * L, P
    if caso == "biengastada_distribuida":
        return q * L ** 2 / 12.0, q * L / 2.0
    if caso == "biengastada_concentrada":
        return P * L / 8.0, P / 2.0
    if caso == "engastada_apoiada_distribuida":
        return q * L ** 2 / 8.0, 5.0 * q * L / 8.0
    raise ErroDeDados(f"caso de viga desconhecido: {caso}")


def verificar_viga(perfil, aco, L: float, q_Sd: float = 0.0, P_Sd: float = 0.0,
                   q_servico: float = 0.0, P_servico: float = 0.0,
                   M_Sd: float = None, V_Sd: float = None, Lb: float = None,
                   Cb: float = 1.0, limite: Union[str, float] = "L/350",
                   caso: str = "biapoiada_distribuida", a_enrij: float = None,
                   contraflecha: float = 0.0, fabricacao: str = "laminado",
                   elemento: str = "Viga") -> Resultado:
    """Verificação completa de uma viga: flexão, cortante e flecha.

    L em cm; q em kN/cm; P em kN; momentos em kN·cm. `Lb = None` adota
    Lb = L (nenhuma contenção lateral intermediária), a favor da segurança.
    """
    p = _perfil_obj(perfil)
    a = _aco(aco)
    if L <= 0:
        raise ErroDeDados("o vão L deve ser positivo (cm)")
    M_calc, V_calc = esforcos_viga(caso, L, q_Sd, P_Sd)
    M_Sd = M_calc if M_Sd is None else M_Sd
    V_Sd = V_calc if V_Sd is None else V_Sd
    Lb_ef = L if Lb is None else Lb

    r = Resultado(elemento, perfil=p.nome, material=a.nome)
    res_flex = flexao(p, a, M_Sd=M_Sd, Lb=Lb_ef, Cb=Cb, fabricacao=fabricacao)
    for v in res_flex.verificacoes:
        r.add(v)
    r.add(cisalhamento(p, a, V_Sd=V_Sd, a_enrij=a_enrij))
    if q_servico or P_servico:
        r.add(flecha(p, L, caso=caso, q=q_servico, P=P_servico, limite=limite,
                     contraflecha=contraflecha))
    r.dados.update(res_flex.dados)
    r.dados.update({"M_Sd": M_Sd, "V_Sd": V_Sd, "L": L, "Lb": Lb_ef,
                    "massa": p.massa, "caso": caso})
    if Lb is None:
        r.dados["aviso_Lb"] = ("Lb adotado igual ao vão (sem contenção lateral "
                               "intermediária); informe Lb se houver travamento")
    return r


def verificar_pilar(perfil, aco, N_Sd: float, Lx: float, Ly: float = None,
                    Kx: float = 1.0, Ky: float = 1.0, Lt: float = None, Kt: float = 1.0,
                    Mx_Sd: float = 0.0, My_Sd: float = 0.0, Lb: float = None,
                    Cb: float = 1.0, fabricacao: str = "laminado",
                    elemento: str = "Pilar") -> Resultado:
    """Verificação completa de um pilar: compressão e, se houver momentos,
    flexão composta (item 5.5.1.2)."""
    p = _perfil_obj(perfil)
    a = _aco(aco)
    Ly = Lx if Ly is None else Ly
    Lb_ef = Ly if Lb is None else Lb
    if Mx_Sd or My_Sd:
        r = flexao_composta(p, a, N_Sd=N_Sd, Mx_Sd=Mx_Sd, My_Sd=My_Sd,
                            tipo_axial="compressao", Lx=Lx, Ly=Ly, Kx=Kx, Ky=Ky,
                            Lt=Lt, Kt=Kt, Lb=Lb_ef, Cb=Cb, fabricacao=fabricacao,
                            elemento=elemento)
    else:
        r = compressao(p, a, Lx, Ly, Kx, Ky, Lt, Kt, N_Sd=N_Sd,
                       fabricacao=fabricacao, elemento=elemento)
    r.dados.update({"massa": p.massa, "N_Sd": N_Sd, "Mx_Sd": Mx_Sd, "My_Sd": My_Sd})
    return r


def _tabela_candidatos(resultados: List[Tuple[Perfil, Resultado, Optional[str]]]) -> List[dict]:
    linhas = []
    for p, res, erro in resultados:
        if erro:
            linhas.append({"perfil": p.nome, "massa": p.massa, "razao": None,
                           "ok": False, "governa": None, "erro": erro})
        else:
            c = res.critica
            linhas.append({"perfil": p.nome, "massa": p.massa, "razao": res.razao,
                           "ok": res.ok, "governa": c.titulo if c else None,
                           "erro": None})
    return linhas


def _buscar(candidatos, verificar) -> Tuple[Optional[Resultado], List[dict]]:
    testados: List[Tuple[Perfil, Resultado, Optional[str]]] = []
    escolhido: Optional[Resultado] = None
    for p in candidatos:
        try:
            res = verificar(p)
        except ErroDeDados as e:
            testados.append((p, None, str(e)))
            continue
        testados.append((p, res, None))
        if res.ok and escolhido is None:
            escolhido = res
    if escolhido is None:
        validos = [(p, res) for p, res, erro in testados if res is not None]
        if validos:
            escolhido = min(validos, key=lambda t: t[1].razao)[1]
            escolhido.dados["encontrado"] = False
    else:
        escolhido.dados["encontrado"] = True
    return escolhido, _tabela_candidatos(testados)


def dimensionar_viga(aco, L: float, q_Sd: float = 0.0, P_Sd: float = 0.0,
                     q_servico: float = 0.0, P_servico: float = 0.0,
                     M_Sd: float = None, V_Sd: float = None, Lb: float = None,
                     Cb: float = 1.0, limite: Union[str, float] = "L/350",
                     caso: str = "biapoiada_distribuida", tipo: str = "I",
                     familia: str = "W", altura_min: float = None,
                     altura_max: float = None, massa_max: float = None,
                     a_enrij: float = None, contraflecha: float = 0.0,
                     elemento: str = "Viga") -> Resultado:
    """Busca o perfil mais leve do catálogo que atende a viga.

    Devolve o `Resultado` completo do perfil adotado, com a lista de candidatos
    testados em `r.dados["candidatos"]` (nome, massa, razão, se passou e qual
    verificação governa). Se nenhum perfil atende, devolve o de menor razão com
    `r.dados["encontrado"] = False`.
    """
    a = _aco(aco)
    candidatos = banco().candidatos(tipo=tipo, familia=familia, massa_max=massa_max,
                                    altura_min=altura_min, altura_max=altura_max)
    if not candidatos:
        raise ErroDeDados(f"nenhum perfil {familia or ''} do tipo {tipo} no catálogo "
                          "com os filtros informados")

    def verificar(p):
        return verificar_viga(p, a, L, q_Sd=q_Sd, P_Sd=P_Sd, q_servico=q_servico,
                              P_servico=P_servico, M_Sd=M_Sd, V_Sd=V_Sd, Lb=Lb,
                              Cb=Cb, limite=limite, caso=caso, a_enrij=a_enrij,
                              contraflecha=contraflecha, elemento=elemento)

    escolhido, tabela = _buscar(candidatos, verificar)
    if escolhido is None:
        raise ErroDeDados("nenhum perfil do catálogo pôde ser verificado com os "
                          "dados informados")
    escolhido.dados["candidatos"] = tabela
    return escolhido


def dimensionar_pilar(aco, N_Sd: float, Lx: float, Ly: float = None, Kx: float = 1.0,
                      Ky: float = 1.0, Lt: float = None, Kt: float = 1.0,
                      Mx_Sd: float = 0.0, My_Sd: float = 0.0, Lb: float = None,
                      Cb: float = 1.0, tipo: str = "I", familia: str = "W",
                      altura_min: float = None, altura_max: float = None,
                      massa_max: float = None, elemento: str = "Pilar") -> Resultado:
    """Busca o pilar mais leve do catálogo que atende aos esforços.

    Mesmo contrato de `dimensionar_viga`: devolve o `Resultado` do perfil
    adotado com a lista de candidatos em `r.dados["candidatos"]`.
    """
    a = _aco(aco)
    candidatos = banco().candidatos(tipo=tipo, familia=familia, massa_max=massa_max,
                                    altura_min=altura_min, altura_max=altura_max)
    if not candidatos:
        raise ErroDeDados(f"nenhum perfil {familia or ''} do tipo {tipo} no catálogo "
                          "com os filtros informados")

    def verificar(p):
        return verificar_pilar(p, a, N_Sd=N_Sd, Lx=Lx, Ly=Ly, Kx=Kx, Ky=Ky, Lt=Lt,
                               Kt=Kt, Mx_Sd=Mx_Sd, My_Sd=My_Sd, Lb=Lb, Cb=Cb,
                               elemento=elemento)

    escolhido, tabela = _buscar(candidatos, verificar)
    if escolhido is None:
        raise ErroDeDados("nenhum perfil do catálogo pôde ser verificado com os "
                          "dados informados")
    escolhido.dados["candidatos"] = tabela
    return escolhido
