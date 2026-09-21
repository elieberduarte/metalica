# -*- coding: utf-8 -*-
"""Ligações parafusadas e soldadas.

Normas de referência:
    NBR 8800:2008, item 6.2  — soldas (Tabela 8, Tabela 10, item 6.2.6)
    NBR 8800:2008, item 6.3  — parafusos (6.3.2 furos, 6.3.3 resistências, 6.3.4 atrito)
    NBR 8800:2008, item 6.5.6 — colapso por rasgamento (bloco de cisalhamento)

Unidades internas (ver GUIA_SISTEMA.md):
    força kN · momento kN·cm · tensão kN/cm² · comprimento cm

Os diâmetros de parafuso e os eletrodos vêm de `materiais.py`; as dimensões de perfil
do catálogo estão em mm e são convertidas explicitamente aqui.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

from .base import (E, GAMA_A1, GAMA_A2, GAMA_W2, ErroDeDados, Resultado,
                   Verificacao, fmt)
from . import materiais as mat
from .perfis import Perfil

# ---------------------------------------------------------------------------
# 1. Tabelas de apoio: furos, espaçamentos e distâncias à borda
# ---------------------------------------------------------------------------

# Folga do furo-padrão (NBR 8800, Tabela 11), em cm.
FOLGA_FURO_PADRAO = 0.15            # d ≤ 24 mm
FOLGA_FURO_PADRAO_GRANDE = 0.20     # d > 24 mm
# O cap. 8 do manual (Tabela 8.2) registra 3 mm acima de 24 mm, seguindo a prática do
# AISC (d + 1/8"). Use `folga_grande=0.30` quando quiser reproduzir aquela tabela.

TIPOS_FURO = ("padrão", "alargado", "oblongo curto", "oblongo longo")

# Distância mínima do centro do furo-padrão à borda (NBR 8800, Tabela 14), em mm:
#   nome do diâmetro -> (borda laminada ou cortada com serra, borda cortada a maçarico)
BORDA_MINIMA_MM: Dict[str, Tuple[float, float]] = {
    '1/2"': (19, 22),
    '5/8"': (22, 28),
    '3/4"': (26, 32),
    '7/8"': (28, 38),
    '1"': (31, 44),
    '1.1/8"': (38, 51),
    '1.1/4"': (41, 57),
    "M16": (22, 28),
    "M20": (26, 34),
    "M22": (28, 38),
    "M24": (30, 42),
    "M27": (34, 48),
    "M30": (38, 52),
}
# M12 não consta da Tabela 14 da NBR 8800. Adota-se 1,5·d (prática de detalhamento
# registrada na Tabela 8.1 do manual), o que é declarado na observação da verificação.
BORDA_MINIMA_NAO_TABELADA = {"M12": (18, 22)}

# Coeficiente de atrito por classe de superfície (NBR 8800, item 6.3.4) — vem de
# materiais.ATRITO. Fator C_h de tipo de furo (manual, eq. 8.1):
CH_FURO = {"padrão": 1.00, "alargado": 0.85, "oblongo curto": 0.85,
           "oblongo longo ⊥": 0.70, "oblongo longo ∥": 0.60}


def _diam(diametro) -> Tuple[str, float, float, float]:
    """Aceita o nome do diâmetro ('3/4"', 'M20') e devolve (nome, d, Ab, Ae) em cm."""
    if isinstance(diametro, str):
        d, Ab, Ae = mat.diametro(diametro)
        return diametro, d, Ab, Ae
    raise ErroDeDados(
        "informe o diâmetro pelo nome comercial, por exemplo '3/4\"' ou 'M20'; "
        f"recebido: {diametro!r}")


def _parafuso(parafuso) -> mat.Parafuso:
    return parafuso if isinstance(parafuso, mat.Parafuso) else mat.parafuso(parafuso)


def fub_efetivo(parafuso, d_cm: float) -> float:
    """f_ub do parafuso, em kN/cm².

    O ASTM A325 tem f_ub = 825 MPa até d = 24 mm e 725 MPa acima (ASTM A325 / NBR 8855),
    conforme a nota da Tabela 8.6 do manual.
    """
    p = _parafuso(parafuso)
    if p.nome == "ASTM A325" and d_cm > 2.4:
        return 72.5
    return p.fub


def diametro_furo(d_cm: float, tipo: str = "padrão",
                  folga_grande: float = FOLGA_FURO_PADRAO_GRANDE) -> Tuple[float, float]:
    """Dimensões do furo (largura × comprimento), em cm — NBR 8800, Tabela 11.

    Furo-padrão: d + 1,5 mm até 24 mm e d + `folga_grande` acima.
    """
    if tipo not in TIPOS_FURO:
        raise ErroDeDados(f"tipo de furo desconhecido: {tipo}. "
                          f"Use um de: {', '.join(TIPOS_FURO)}")
    folga = FOLGA_FURO_PADRAO if d_cm <= 2.4 else folga_grande
    largura = d_cm + folga
    if tipo == "padrão":
        return largura, largura
    if tipo == "alargado":
        dh = d_cm + (0.5 if d_cm <= 2.4 else 0.8)
        return dh, dh
    if tipo == "oblongo curto":
        return largura, d_cm + (0.6 if d_cm <= 2.4 else 1.0)
    return largura, 2.5 * d_cm          # oblongo longo


def furo_padrao(d_cm: float, folga_grande: float = FOLGA_FURO_PADRAO_GRANDE) -> float:
    """Diâmetro do furo-padrão, em cm."""
    return diametro_furo(d_cm, "padrão", folga_grande)[0]


def espacamento_minimo(d_cm: float) -> float:
    """Distância mínima entre centros de furos: 2,7·d (NBR 8800, item 6.3.9)."""
    return 2.7 * d_cm


def espacamento_recomendado(d_cm: float) -> float:
    """Distância recomendada entre centros de furos: 3·d (NBR 8800, item 6.3.9)."""
    return 3.0 * d_cm


def espacamento_maximo(t_cm: float, patinavel_exposto: bool = False) -> float:
    """Distância máxima entre centros de furos (NBR 8800, item 6.3.10), em cm.

    24·t ≤ 300 mm em geral; 14·t ≤ 180 mm em aço patinável exposto.
    """
    if patinavel_exposto:
        return min(14.0 * t_cm, 18.0)
    return min(24.0 * t_cm, 30.0)


def distancia_borda_minima(nome_diametro: str, borda: str = "laminada") -> Tuple[float, str]:
    """Distância mínima do centro do furo à borda (NBR 8800, Tabela 14), em cm.

    `borda`: "laminada" (laminada ou cortada com serra) ou "maçarico" (cortada com
    tesoura ou maçarico). Devolve (valor em cm, observação).
    """
    i = 0 if borda.startswith("lamin") or borda.startswith("serra") else 1
    if nome_diametro in BORDA_MINIMA_MM:
        return BORDA_MINIMA_MM[nome_diametro][i] / 10.0, ""
    if nome_diametro in BORDA_MINIMA_NAO_TABELADA:
        return (BORDA_MINIMA_NAO_TABELADA[nome_diametro][i] / 10.0,
                f"{nome_diametro} não consta da Tabela 14 da NBR 8800; adotado 1,5·d, "
                "valor de detalhamento corrente (Tabela 8.1 do manual).")
    _, d, _, _ = _diam(nome_diametro)
    return (1.5 * d, f"{nome_diametro} não consta da Tabela 14 da NBR 8800; "
                     "adotado 1,5·d, valor de detalhamento corrente.")


def distancia_borda_maxima(t_cm: float) -> float:
    """Distância máxima do centro do furo à borda: 12·t ≤ 150 mm (NBR 8800, 6.3.12)."""
    return min(12.0 * t_cm, 15.0)


def largura_desconto_furo(dh_cm: float) -> float:
    """Largura a descontar por furo no cálculo de área líquida: d_h + 2 mm (6.3.2)."""
    return dh_cm + 0.2


# ---------------------------------------------------------------------------
# 2. Parafusos — NBR 8800, item 6.3
# ---------------------------------------------------------------------------

def cisalhamento_parafuso(diametro: str, parafuso: str = "ASTM A325", planos: int = 1,
                          rosca_no_plano: bool = True, Fv_Sd: float = 0.0,
                          n: int = 1) -> Verificacao:
    """Força resistente ao cisalhamento de parafuso (NBR 8800, item 6.3.3.1).

        F_v,Rd = 0,4·A_b·f_ub/γ_a2   (rosca no plano de corte, ou parafuso A307)
        F_v,Rd = 0,5·A_b·f_ub/γ_a2   (rosca fora do plano de corte)

    multiplicada pelo número de planos de corte e pelo número `n` de parafusos.
    """
    nome, d, Ab, _ = _diam(diametro)
    p = _parafuso(parafuso)
    fub = fub_efetivo(p, d)
    if planos < 1:
        raise ErroDeDados("o número de planos de corte tem de ser ≥ 1")
    # O A307 usa sempre 0,4: a rosca pode estar em qualquer posição (item 6.3.3.1).
    comum = not p.alta_resistencia
    coef = 0.4 if (rosca_no_plano or comum) else 0.5
    Fv1 = coef * Ab * fub / GAMA_A2
    Rd = Fv1 * planos * n

    v = Verificacao(f"Cisalhamento do parafuso {nome} {p.nome}",
                    norma="NBR 8800:2008, item 6.3.3.1", Sd=Fv_Sd, Rd=Rd, unidade="kN")
    if comum and not rosca_no_plano:
        v.observacao = (f"{p.nome} é parafuso comum: a NBR 8800 adota sempre o "
                        "coeficiente 0,4, independentemente da posição da rosca.")
    if p.nome == "ASTM A325" and d > 2.4:
        v.observacao += (" f_ub reduzido para 72,5 kN/cm² (725 MPa), valor do A325 "
                         "para d > 24 mm.")
    v.passo("Área bruta do parafuso",
            formula="A<sub>b</sub> = π·d²/4",
            conta=f"π·{fmt(d, 3)}²/4",
            valor=fmt(Ab, 3, "cm²"), norma="Tabela 8.1 do manual")
    v.passo("Resistência por plano de corte",
            formula=f"F<sub>v,Rd</sub> = {fmt(coef, 1)}·A<sub>b</sub>·f<sub>ub</sub>/γ<sub>a2</sub>",
            conta=f"{fmt(coef, 1)}·{fmt(Ab, 3)}·{fmt(fub, 1)}/{fmt(GAMA_A2, 2)}",
            valor=fmt(Fv1, 1, "kN"), norma="item 6.3.3.1")
    v.passo(f"{planos} plano(s) de corte × {n} parafuso(s)",
            formula="R<sub>d</sub> = F<sub>v,Rd</sub>·n<sub>planos</sub>·n",
            conta=f"{fmt(Fv1, 1)}·{planos}·{n}",
            valor=fmt(Rd, 1, "kN"))
    return v


def tracao_parafuso(diametro: str, parafuso: str = "ASTM A325", Ft_Sd: float = 0.0,
                    n: int = 1) -> Verificacao:
    """Força resistente à tração de parafuso (NBR 8800, item 6.3.3.2).

        F_t,Rd = 0,75·A_b·f_ub/γ_a2

    O coeficiente 0,75 já embute a relação entre a área na rosca e a área bruta.
    """
    nome, d, Ab, Ae = _diam(diametro)
    p = _parafuso(parafuso)
    fub = fub_efetivo(p, d)
    Ft1 = 0.75 * Ab * fub / GAMA_A2
    Rd = Ft1 * n

    v = Verificacao(f"Tração do parafuso {nome} {p.nome}",
                    norma="NBR 8800:2008, item 6.3.3.2", Sd=Ft_Sd, Rd=Rd, unidade="kN")
    v.passo("Resistência à tração por parafuso",
            formula="F<sub>t,Rd</sub> = 0,75·A<sub>b</sub>·f<sub>ub</sub>/γ<sub>a2</sub>",
            conta=f"0,75·{fmt(Ab, 3)}·{fmt(fub, 1)}/{fmt(GAMA_A2, 2)}",
            valor=fmt(Ft1, 1, "kN"), norma="item 6.3.3.2")
    if n > 1:
        v.passo(f"{n} parafusos tracionados",
                formula="R<sub>d</sub> = n·F<sub>t,Rd</sub>",
                conta=f"{n}·{fmt(Ft1, 1)}", valor=fmt(Rd, 1, "kN"))
    v.passo("Área na rosca (informativa)", formula="A<sub>e</sub>",
            conta=f"{fmt(Ae, 3)} cm² = {fmt(100*Ae/Ab, 0)} % de A<sub>b</sub>",
            valor=fmt(Ae, 3, "cm²"))
    return v


def interacao_tracao_cisalhamento(diametro: str, parafuso: str, Ft_Sd: float,
                                  Fv_Sd: float, planos: int = 1,
                                  rosca_no_plano: bool = True) -> Verificacao:
    """Interação tração–cisalhamento no parafuso (NBR 8800, item 6.3.3.3).

        (F_t,Sd/F_t,Rd)² + (F_v,Sd/F_v,Rd)² ≤ 1,0

    Por parafuso. A verificação é apresentada com Sd = valor da soma dos quadrados e
    Rd = 1,0, de modo que a razão da `Verificacao` é o próprio índice de interação.
    """
    vt = tracao_parafuso(diametro, parafuso)
    vv = cisalhamento_parafuso(diametro, parafuso, planos=planos,
                               rosca_no_plano=rosca_no_plano)
    rt = Ft_Sd / vt.Rd if vt.Rd else 0.0
    rv = Fv_Sd / vv.Rd if vv.Rd else 0.0
    indice = rt ** 2 + rv ** 2

    nome, _, _, _ = _diam(diametro)
    v = Verificacao(f"Interação tração–cisalhamento — {nome} {_parafuso(parafuso).nome}",
                    norma="NBR 8800:2008, item 6.3.3.3", Sd=indice, Rd=1.0, unidade="—")
    v.passo("Resistência à tração",
            formula="F<sub>t,Rd</sub>", conta="", valor=fmt(vt.Rd, 1, "kN"))
    v.passo("Resistência ao cisalhamento",
            formula="F<sub>v,Rd</sub>", conta="", valor=fmt(vv.Rd, 1, "kN"))
    v.passo("Índice de interação",
            formula="(F<sub>t,Sd</sub>/F<sub>t,Rd</sub>)² + (F<sub>v,Sd</sub>/F<sub>v,Rd</sub>)²",
            conta=f"({fmt(Ft_Sd, 1)}/{fmt(vt.Rd, 1)})² + ({fmt(Fv_Sd, 1)}/{fmt(vv.Rd, 1)})²"
                  f" = {fmt(rt**2, 3)} + {fmt(rv**2, 3)}",
            valor=fmt(indice, 3), norma="item 6.3.3.3")
    if min(rt, rv) <= 0.20:
        v.observacao = ("Uma das solicitações está abaixo de 20 % da resistência "
                        "correspondente: a NBR 8800 permite desprezar a interação.")
    return v


def esmagamento(diametro: str, t_chapa: float, fu: float,
                distancia_borda: Optional[float] = None,
                espacamento: Optional[float] = None,
                furo: str = "padrão", Fc_Sd: float = 0.0,
                deformacao_limitante: bool = True,
                direcao_rasgo: str = "perpendicular",
                n_borda: int = 1, n_interno: int = 0,
                nome_chapa: str = "") -> Verificacao:
    """Esmagamento e rasgamento da chapa no furo (NBR 8800, item 6.3.3.3 / Tabela 12).

        F_c,Rd = 1,2·l_f·t·f_u/γ_a2  ≤  2,4·d·t·f_u/γ_a2      (deformação limitante)
        F_c,Rd = 1,5·l_f·t·f_u/γ_a2  ≤  3,0·d·t·f_u/γ_a2      (deformação não limitante)
        F_c,Rd = 1,0·l_f·t·f_u/γ_a2  ≤  2,0·d·t·f_u/γ_a2      (oblongo longo, carga ⊥)

    `l_f` é a distância livre na direção da força:
        parafuso de borda : l_f = e₁ − d_h/2
        parafuso interno  : l_f = s − d_h
    `n_borda` e `n_interno` permitem somar a contribuição de uma linha de parafusos.
    """
    nome, d, _, _ = _diam(diametro)
    largura, comprimento = diametro_furo(d, furo)
    # dimensão do furo medida na direção da força
    dh = comprimento if (furo.startswith("oblongo") and direcao_rasgo == "paralelo") else largura

    if furo == "oblongo longo" and direcao_rasgo == "perpendicular":
        c1, c2 = 1.0, 2.0
        criterio = "furo oblongo longo com carga perpendicular ao rasgo"
    elif deformacao_limitante:
        c1, c2 = 1.2, 2.4
        criterio = "deformação do furo em serviço é limitação de projeto"
    else:
        c1, c2 = 1.5, 3.0
        criterio = "deformação do furo em serviço não é limitação de projeto"

    limite = c2 * d * t_chapa * fu / GAMA_A2

    def _por_parafuso(lf):
        return min(c1 * lf * t_chapa * fu / GAMA_A2, limite)

    titulo = "Esmagamento/rasgamento" + (f" — {nome_chapa}" if nome_chapa else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, item 6.3.3.3 e Tabela 12",
                    Sd=Fc_Sd, Rd=0.0, unidade="kN")
    v.passo("Diâmetro do furo",
            formula="d<sub>h</sub>", conta=f"furo {furo}, d = {fmt(d, 3)} cm",
            valor=fmt(dh, 3, "cm"), norma="Tabela 11")
    v.passo("Limite superior por parafuso",
            formula=f"{fmt(c2,1)}·d·t·f<sub>u</sub>/γ<sub>a2</sub>",
            conta=f"{fmt(c2,1)}·{fmt(d,3)}·{fmt(t_chapa,2)}·{fmt(fu,1)}/{fmt(GAMA_A2,2)}",
            valor=fmt(limite, 1, "kN"), norma=criterio)

    Rd = 0.0
    if n_borda:
        if distancia_borda is None:
            raise ErroDeDados("informe `distancia_borda` (e₁, em cm) para o parafuso "
                              "de borda, ou use n_borda=0")
        lf_b = distancia_borda - dh / 2.0
        if lf_b <= 0:
            raise ErroDeDados(
                f"distância à borda e₁ = {distancia_borda:.2f} cm menor que d_h/2 = "
                f"{dh/2:.2f} cm: o furo sai da chapa. Aumente e₁.")
        Fb = _por_parafuso(lf_b)
        Rd += n_borda * Fb
        v.passo(f"Parafuso(s) de borda ({n_borda}): distância livre",
                formula="l<sub>f</sub> = e₁ − d<sub>h</sub>/2",
                conta=f"{fmt(distancia_borda, 2)} − {fmt(dh, 3)}/2",
                valor=fmt(lf_b, 2, "cm"))
        v.passo("Resistência do(s) parafuso(s) de borda",
                formula=f"{fmt(c1,1)}·l<sub>f</sub>·t·f<sub>u</sub>/γ<sub>a2</sub> ≤ limite",
                conta=f"{fmt(c1,1)}·{fmt(lf_b,2)}·{fmt(t_chapa,2)}·{fmt(fu,1)}/"
                      f"{fmt(GAMA_A2,2)} = {fmt(c1*lf_b*t_chapa*fu/GAMA_A2, 1)}",
                valor=fmt(Fb, 1, "kN") + (f" × {n_borda}" if n_borda > 1 else ""))
    if n_interno:
        if espacamento is None:
            raise ErroDeDados("informe `espacamento` (s, em cm) para os parafusos "
                              "internos, ou use n_interno=0")
        lf_i = espacamento - dh
        if lf_i <= 0:
            raise ErroDeDados(
                f"espaçamento s = {espacamento:.2f} cm menor que d_h = {dh:.2f} cm: "
                "os furos se tocam. Use s ≥ 2,7·d.")
        Fi = _por_parafuso(lf_i)
        Rd += n_interno * Fi
        v.passo(f"Parafuso(s) interno(s) ({n_interno}): distância livre",
                formula="l<sub>f</sub> = s − d<sub>h</sub>",
                conta=f"{fmt(espacamento, 2)} − {fmt(dh, 3)}",
                valor=fmt(lf_i, 2, "cm"))
        v.passo("Resistência do(s) parafuso(s) interno(s)",
                formula=f"{fmt(c1,1)}·l<sub>f</sub>·t·f<sub>u</sub>/γ<sub>a2</sub> ≤ limite",
                conta=f"{fmt(c1,1)}·{fmt(lf_i,2)}·{fmt(t_chapa,2)}·{fmt(fu,1)}/"
                      f"{fmt(GAMA_A2,2)} = {fmt(c1*lf_i*t_chapa*fu/GAMA_A2, 1)}",
                valor=fmt(Fi, 1, "kN") + (f" × {n_interno}" if n_interno > 1 else ""))
    v.Rd = Rd
    v.passo("Resistência total da chapa ao esmagamento",
            formula="R<sub>d</sub> = Σ F<sub>c,Rd</sub>",
            conta="", valor=fmt(Rd, 1, "kN"))
    return v


def deslizamento(diametro: str, parafuso: str = "ASTM A325", planos: int = 1,
                 superficie: str = "A (jateada, sem pintura)", furo: str = "padrão",
                 estado_limite: str = "serviço", Fv_Sd: float = 0.0,
                 Ft_Sd: float = 0.0, n: int = 1) -> Verificacao:
    """Resistência ao deslizamento de ligação por atrito (NBR 8800, item 6.3.4).

        F_f,Rd = 1,13·μ·C_h·F_Tb·n_s/γ

    γ = 1,20 no estado-limite de serviço e 1,35 no estado-limite último (furos
    alargados ou oblongos). A protensão mínima F_Tb vem de `materiais.PROTENSAO`
    (NBR 8800, Tabela 15). Havendo tração simultânea, a resistência é multiplicada
    por (1 − F_t,Sd/(1,13·F_Tb)) (item 6.3.4.2).
    """
    nome, d, Ab, _ = _diam(diametro)
    p = _parafuso(parafuso)
    if not p.alta_resistencia:
        raise ErroDeDados(f"ligação por atrito exige parafuso de alta resistência "
                          f"protendido (A325 ou A490); recebido {p.nome}")
    if p.nome not in mat.PROTENSAO or nome not in mat.PROTENSAO[p.nome]:
        raise ErroDeDados(f"protensão mínima não tabelada para {p.nome} {nome} "
                          "(NBR 8800, Tabela 15)")
    FTb = mat.PROTENSAO[p.nome][nome]
    if superficie not in mat.ATRITO:
        raise ErroDeDados(f"classe de superfície desconhecida: {superficie}. "
                          f"Disponíveis: {', '.join(mat.ATRITO)}")
    mu = mat.ATRITO[superficie]
    Ch = CH_FURO.get(furo, CH_FURO["padrão"])
    gama = 1.20 if estado_limite.startswith("serv") else 1.35

    Ff1 = 1.13 * mu * Ch * FTb * planos / gama
    fator_tracao = 1.0
    if Ft_Sd > 0:
        fator_tracao = max(0.0, 1.0 - Ft_Sd / (1.13 * FTb))
        Ff1 *= fator_tracao
    Rd = Ff1 * n

    v = Verificacao(f"Deslizamento (ligação por atrito) — {nome} {p.nome}",
                    norma="NBR 8800:2008, item 6.3.4", Sd=Fv_Sd, Rd=Rd, unidade="kN")
    v.passo("Protensão mínima do parafuso",
            formula="F<sub>Tb</sub> = 0,70·A<sub>e</sub>·f<sub>ub</sub>",
            conta=f"{p.nome} {nome}", valor=fmt(FTb, 0, "kN"), norma="Tabela 15")
    v.passo("Coeficiente de atrito da superfície",
            formula="μ", conta=superficie, valor=fmt(mu, 2), norma="item 6.3.4.1")
    v.passo("Fator do tipo de furo",
            formula="C<sub>h</sub>", conta=f"furo {furo}", valor=fmt(Ch, 2))
    v.passo("Resistência ao deslizamento por parafuso",
            formula="F<sub>f,Rd</sub> = 1,13·μ·C<sub>h</sub>·F<sub>Tb</sub>·n<sub>s</sub>/γ",
            conta=f"1,13·{fmt(mu,2)}·{fmt(Ch,2)}·{fmt(FTb,0)}·{planos}/{fmt(gama,2)}",
            valor=fmt(Ff1, 1, "kN"), norma=f"estado-limite de {estado_limite}")
    if Ft_Sd > 0:
        v.passo("Redução pela tração simultânea",
                formula="(1 − F<sub>t,Sd</sub>/(1,13·F<sub>Tb</sub>))",
                conta=f"1 − {fmt(Ft_Sd,1)}/(1,13·{fmt(FTb,0)})",
                valor=fmt(fator_tracao, 3), norma="item 6.3.4.2")
    if n > 1:
        v.passo(f"{n} parafusos", formula="R<sub>d</sub> = n·F<sub>f,Rd</sub>",
                conta=f"{n}·{fmt(Ff1,1)}", valor=fmt(Rd, 1, "kN"))
    v.observacao = ("O atrito não substitui a verificação por apoio: o corte do "
                    "parafuso e o esmagamento da chapa continuam obrigatórios no "
                    "estado-limite último (NBR 8800, item 6.3.4).")
    return v


def bloco_cisalhamento(Agv: float, Anv: float, Agt: float, Ant: float,
                       fy: float, fu: float, Cts: float = 1.0, Sd: float = 0.0,
                       nome: str = "") -> Verificacao:
    """Colapso por rasgamento — bloco de cisalhamento (NBR 8800, item 6.5.6).

        R_d = (0,6·f_u·A_nv + C_ts·f_u·A_nt)/γ_a2
            ≤ (0,6·f_y·A_gv + C_ts·f_u·A_nt)/γ_a2

    Áreas em cm²; C_ts = 1,0 quando a tensão de tração é uniforme e 0,5 quando não.
    `Agt` (área bruta tracionada) não entra na fórmula da NBR 8800; é registrada
    apenas para o memorial e o desenho.
    """
    if Cts not in (0.5, 1.0):
        raise ErroDeDados("C_ts vale 1,0 (tração uniforme) ou 0,5 (não uniforme) — "
                          f"recebido {Cts}")
    ruptura = (0.6 * fu * Anv + Cts * fu * Ant) / GAMA_A2
    escoamento = (0.6 * fy * Agv + Cts * fu * Ant) / GAMA_A2
    Rd = min(ruptura, escoamento)

    titulo = "Bloco de cisalhamento" + (f" — {nome}" if nome else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, item 6.5.6", Sd=Sd, Rd=Rd, unidade="kN")
    v.passo("Áreas do bloco",
            formula="A<sub>gv</sub> / A<sub>nv</sub> / A<sub>gt</sub> / A<sub>nt</sub>",
            conta=f"{fmt(Agv,2)} / {fmt(Anv,2)} / {fmt(Agt,2)} / {fmt(Ant,2)}",
            valor="cm²")
    v.passo("Ruptura na face cisalhada",
            formula="(0,6·f<sub>u</sub>·A<sub>nv</sub> + C<sub>ts</sub>·f<sub>u</sub>·A<sub>nt</sub>)/γ<sub>a2</sub>",
            conta=f"(0,6·{fmt(fu,1)}·{fmt(Anv,2)} + {fmt(Cts,1)}·{fmt(fu,1)}·{fmt(Ant,2)})"
                  f"/{fmt(GAMA_A2,2)}",
            valor=fmt(ruptura, 1, "kN"))
    v.passo("Escoamento na face cisalhada",
            formula="(0,6·f<sub>y</sub>·A<sub>gv</sub> + C<sub>ts</sub>·f<sub>u</sub>·A<sub>nt</sub>)/γ<sub>a2</sub>",
            conta=f"(0,6·{fmt(fy,1)}·{fmt(Agv,2)} + {fmt(Cts,1)}·{fmt(fu,1)}·{fmt(Ant,2)})"
                  f"/{fmt(GAMA_A2,2)}",
            valor=fmt(escoamento, 1, "kN"))
    v.passo("Governa o menor",
            formula="R<sub>d</sub> = mín(ruptura ; escoamento)",
            conta=f"mín({fmt(ruptura,1)} ; {fmt(escoamento,1)})",
            valor=fmt(Rd, 1, "kN"))
    v.observacao = ("Governa o escoamento na face cisalhada."
                    if escoamento < ruptura else
                    "Governa a ruptura na face cisalhada.")
    return v


# ---------------------------------------------------------------------------
# 2b. Grupo de parafusos — distribuição elástica dos esforços
# ---------------------------------------------------------------------------

def coordenadas_grupo(linhas: int, colunas: int, passo: float,
                      gabarito: float) -> List[Tuple[float, float]]:
    """Coordenadas (x, y) dos parafusos, em cm, com origem no centro do grupo.

    `linhas` = número de parafusos numa coluna vertical (passo = espaçamento vertical);
    `colunas` = número de linhas verticais de parafusos (gabarito = espaçamento horizontal).
    """
    if linhas < 1 or colunas < 1:
        raise ErroDeDados("o grupo precisa de pelo menos 1 linha e 1 coluna de parafusos")
    pts = []
    for i in range(colunas):
        x = (i - (colunas - 1) / 2.0) * gabarito
        for j in range(linhas):
            y = (j - (linhas - 1) / 2.0) * passo
            pts.append((x, y))
    return pts


def esforcos_no_grupo(pontos: Sequence[Tuple[float, float]], V_Sd: float = 0.0,
                      N_Sd: float = 0.0, M_Sd: float = 0.0,
                      excentricidade: float = 0.0) -> dict:
    """Distribuição elástica dos esforços num grupo de parafusos.

    Cisalhamento direto V/n e N/n somados vetorialmente à parcela de torção
    M·r/I_p, com I_p = Σ(x² + y²) o momento polar de inércia do grupo em relação
    ao seu centro de gravidade (método elástico — NBR 8800 não prescreve o método;
    o elástico é o clássico e conservador em relação ao centro instantâneo).

    `excentricidade` (cm) é o braço do cortante V em relação ao CG do grupo; o
    momento total é M_Sd + V_Sd·e.
    """
    n = len(pontos)
    Ip = sum(x * x + y * y for x, y in pontos)
    M = M_Sd + V_Sd * excentricidade
    fx_dir = N_Sd / n
    fy_dir = V_Sd / n
    pior = 0.0
    forcas = []
    for x, y in pontos:
        if Ip > 0:
            fx = fx_dir - M * y / Ip
            fy = fy_dir + M * x / Ip
        else:
            fx, fy = fx_dir, fy_dir
        f = math.hypot(fx, fy)
        forcas.append((x, y, fx, fy, f))
        pior = max(pior, f)
    return {"n": n, "Ip": Ip, "M_total": M, "forcas": forcas,
            "F_max": pior, "fx_direto": fx_dir, "fy_direto": fy_dir}


def verificar_grupo_parafusos(diametro: str, parafuso: str, linhas: int, colunas: int,
                              passo: float, gabarito: float,
                              chapas: Sequence[dict], V_Sd: float = 0.0,
                              N_Sd: float = 0.0, M_Sd: float = 0.0,
                              excentricidade: float = 0.0, planos: int = 1,
                              rosca_no_plano: bool = True, furo: str = "padrão",
                              elemento: str = "Grupo de parafusos",
                              atrito: Optional[dict] = None) -> Resultado:
    """Verifica um grupo de parafusos sob V, N e M no plano (método elástico).

    `chapas` é uma lista de dicionários, um por chapa atravessada:
        {"nome": "alma da viga", "t": 0.72, "fu": 40.0, "fy": 25.0,
         "borda": 3.5,          # e₁ na direção da força, cm
         "n_borda": 1,          # parafusos que descarregam contra a borda
         "planos": 2}           # opcional: planos de corte vistos por esta chapa
    `atrito` opcional: {"superficie": ..., "estado_limite": "serviço"}.

    Devolve `Resultado` com todas as verificações e, em `dados`, a geometria e a
    distribuição de forças para o desenho.
    """
    nome_d, d, Ab, _ = _diam(diametro)
    p = _parafuso(parafuso)
    pontos = coordenadas_grupo(linhas, colunas, passo, gabarito)
    dist = esforcos_no_grupo(pontos, V_Sd, N_Sd, M_Sd, excentricidade)
    n = dist["n"]
    F_max = dist["F_max"]

    r = Resultado(elemento, perfil=f"{n} × {nome_d} {p.nome}", material=p.nome)
    r.dados.update({"diametro": nome_d, "parafuso": p.nome, "n": n,
                    "linhas": linhas, "colunas": colunas, "passo": passo,
                    "gabarito": gabarito, "furo": furo,
                    "d_furo": diametro_furo(d, furo)[0],
                    "pontos": pontos, "Ip": dist["Ip"], "M_total": dist["M_total"],
                    "F_max_parafuso": F_max, "forcas": dist["forcas"],
                    "V_Sd": V_Sd, "N_Sd": N_Sd, "M_Sd": M_Sd,
                    "excentricidade": excentricidade})

    # --- geometria ---
    vg = Verificacao("Espaçamento mínimo entre furos",
                     norma="NBR 8800:2008, item 6.3.9",
                     Sd=espacamento_minimo(d), Rd=min(passo, gabarito) if colunas > 1
                     else passo, unidade="cm")
    vg.passo("Mínimo normativo", formula="s<sub>mín</sub> = 2,7·d",
             conta=f"2,7·{fmt(d,3)}", valor=fmt(espacamento_minimo(d), 2, "cm"))
    vg.passo("Recomendado", formula="s = 3·d", conta=f"3·{fmt(d,3)}",
             valor=fmt(espacamento_recomendado(d), 2, "cm"))
    vg.passo("Adotado", formula="passo × gabarito",
             conta=f"{fmt(passo,2)} × {fmt(gabarito,2)}", valor="cm")
    r.add(vg)

    # --- cisalhamento do parafuso mais solicitado ---
    r.add(cisalhamento_parafuso(nome_d, p, planos=planos,
                                rosca_no_plano=rosca_no_plano, Fv_Sd=F_max))

    # --- esmagamento em cada chapa ---
    for ch in chapas:
        planos_ch = ch.get("planos", 1)
        n_borda = ch.get("n_borda", colunas if passo else 1)
        n_interno = ch.get("n_interno", n - n_borda)
        # força que a chapa transfere por parafuso: F_max dividido pelos planos que
        # a chapa "enxerga" (chapa central de corte duplo recebe o dobro de uma tala)
        Fc = F_max * planos_ch / max(planos, 1) if planos_ch else F_max
        v = esmagamento(nome_d, ch["t"], ch["fu"],
                        distancia_borda=ch.get("borda"), espacamento=passo,
                        furo=furo, Fc_Sd=Fc * n if n_borda + n_interno == n else Fc,
                        n_borda=n_borda, n_interno=n_interno,
                        nome_chapa=ch.get("nome", ""))
        r.add(v)
        if "bloco" in ch:
            b = ch["bloco"]
            r.add(bloco_cisalhamento(b["Agv"], b["Anv"], b.get("Agt", 0.0), b["Ant"],
                                     ch["fy"], ch["fu"], b.get("Cts", 1.0),
                                     Sd=b.get("Sd", V_Sd), nome=ch.get("nome", "")))

    # --- atrito, se pedido ---
    if atrito:
        r.add(deslizamento(nome_d, p, planos=planos,
                           superficie=atrito.get("superficie", "A (jateada, sem pintura)"),
                           furo=furo,
                           estado_limite=atrito.get("estado_limite", "serviço"),
                           Fv_Sd=F_max))
    return r


# ---------------------------------------------------------------------------
# 3. Soldas — NBR 8800, item 6.2
# ---------------------------------------------------------------------------

def garganta(perna: float, processo: str = "SMAW", perna2: Optional[float] = None) -> float:
    """Garganta efetiva do filete, em cm (NBR 8800, item 6.2.6.1).

    a = 0,707·b para pernas iguais; a = b₁·b₂/√(b₁²+b₂²) para pernas desiguais.
    No arco submerso (SAW) a NBR 8800 admite a = b para b ≤ 10 mm e
    a = 0,707·b + 3 mm acima, pela penetração garantida na raiz.
    """
    if perna2 and abs(perna2 - perna) > 1e-9:
        return perna * perna2 / math.hypot(perna, perna2)
    if processo.upper() == "SAW":
        return perna if perna <= 1.0 else 0.707 * perna + 0.30
    return 0.707 * perna


def comprimento_efetivo_filete(comprimento: float, perna: float) -> Tuple[float, float]:
    """Comprimento efetivo do filete (NBR 8800, item 6.2.6.2.3). Devolve (L_ef, β)."""
    if perna <= 0:
        raise ErroDeDados("a perna do filete tem de ser positiva")
    razao = comprimento / perna
    if razao <= 100:
        return comprimento, 1.0
    if razao <= 300:
        beta = min(1.0, 1.2 - 0.002 * razao)
        return beta * comprimento, beta
    return 180.0 * perna, 180.0 * perna / comprimento


def resistencia_filete_cm(perna: float, eletrodo: str = "E70XX", fy_base: float = 25.0,
                          processo: str = "SMAW") -> Tuple[float, float, float]:
    """Resistência do filete por centímetro de cordão (NBR 8800, Tabela 8).

        metal da solda : 0,6·f_w·a/γ_w2
        metal base     : 0,6·f_y·b/γ_a1

    Devolve (r_solda, r_base, r_adotada) em kN/cm. Reproduz a Tabela 9.5 do manual.
    """
    el = eletrodo if isinstance(eletrodo, mat.Eletrodo) else mat.eletrodo(eletrodo)
    a = garganta(perna, processo)
    r_solda = 0.6 * el.fw * a / GAMA_W2
    r_base = 0.6 * fy_base * perna / GAMA_A1
    return r_solda, r_base, min(r_solda, r_base)


def filete(perna: float, comprimento: float, eletrodo: str = "E70XX",
           fy_base: float = 25.0, t_base: Optional[float] = None,
           t_outra: Optional[float] = None, F_Sd: float = 0.0, n_cordoes: int = 1,
           processo: str = "SMAW", nome: str = "") -> Verificacao:
    """Solda de filete: metal da solda e metal base (NBR 8800, item 6.2 e Tabela 8).

        F_w,Rd  = 0,6·f_w·(0,707·b)·L_ef/γ_w2     (ruptura do metal da solda)
        F_MB,Rd = 0,6·f_y·b·L_ef/γ_a1             (escoamento do metal base)

    `t_base` é a espessura da chapa mais grossa (perna mínima, Tabela 10) e
    `t_outra` a da chapa cuja borda recebe o cordão (perna máxima, item 6.2.6.2.2).
    Não é aplicada a majoração (1 + 0,5·sen^1,5 θ) do filete transversal — a favor
    da segurança, como no manual.
    """
    el = eletrodo if isinstance(eletrodo, mat.Eletrodo) else mat.eletrodo(eletrodo)
    a = garganta(perna, processo)
    Lef, beta = comprimento_efetivo_filete(comprimento, perna)
    r_solda, r_base, r = resistencia_filete_cm(perna, el, fy_base, processo)
    Rd = r * Lef * n_cordoes

    titulo = "Solda de filete" + (f" — {nome}" if nome else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, item 6.2.6 e Tabela 8",
                    Sd=F_Sd, Rd=Rd, unidade="kN")
    v.passo("Garganta efetiva",
            formula="a = 0,707·b", conta=f"0,707·{fmt(perna, 2)}",
            valor=fmt(a, 4, "cm"), norma="item 6.2.6.1")
    v.passo("Resistência do metal da solda por cm",
            formula="0,6·f<sub>w</sub>·a/γ<sub>w2</sub>",
            conta=f"0,6·{fmt(el.fw,1)}·{fmt(a,4)}/{fmt(GAMA_W2,2)}",
            valor=fmt(r_solda, 2, "kN/cm"), norma=el.nome)
    v.passo("Resistência do metal base por cm",
            formula="0,6·f<sub>y</sub>·b/γ<sub>a1</sub>",
            conta=f"0,6·{fmt(fy_base,1)}·{fmt(perna,2)}/{fmt(GAMA_A1,2)}",
            valor=fmt(r_base, 2, "kN/cm"))
    v.passo("Governa o menor",
            formula="r = mín(metal da solda ; metal base)",
            conta=f"mín({fmt(r_solda,2)} ; {fmt(r_base,2)})",
            valor=fmt(r, 2, "kN/cm"))
    if beta < 1.0:
        v.passo("Redução de cordão longo",
                formula="β = 1,2 − 0,002·L/b",
                conta=f"L/b = {fmt(comprimento/perna, 0)}",
                valor=fmt(beta, 3), norma="item 6.2.6.2.3")
    v.passo(f"Resistência total ({n_cordoes} cordão(ões) de {fmt(comprimento,1)} cm)",
            formula="R<sub>d</sub> = r·L<sub>ef</sub>·n",
            conta=f"{fmt(r,2)}·{fmt(Lef,1)}·{n_cordoes}", valor=fmt(Rd, 1, "kN"))

    obs = []
    if t_base is not None:
        bmin = mat.perna_minima(t_base)
        if perna < bmin - 1e-9:
            obs.append(f"perna {perna*10:.0f} mm menor que a mínima {bmin*10:.0f} mm "
                       f"para chapa de {t_base*10:.1f} mm (NBR 8800, Tabela 10)")
    if t_outra is not None:
        bmax = mat.perna_maxima(t_outra)
        if perna > bmax + 1e-9:
            obs.append(f"perna {perna*10:.0f} mm maior que a máxima {bmax*10:.0f} mm "
                       f"na borda de chapa de {t_outra*10:.1f} mm (item 6.2.6.2.2)")
    Lmin = max(4 * perna, 4.0)
    if comprimento < Lmin - 1e-9:
        obs.append(f"comprimento {comprimento*10:.0f} mm menor que o mínimo "
                   f"{Lmin*10:.0f} mm (4·b e ≥ 40 mm, item 6.2.6.2.3)")
    v.observacao = "; ".join(obs)
    return v


def penetracao_total(t_chapa: float, comprimento: float, fy_base: float,
                     fu_base: Optional[float] = None, solicitacao: str = "tração",
                     F_Sd: float = 0.0, nome: str = "") -> Verificacao:
    """Solda de penetração total (NBR 8800, Tabela 8).

    Com metal de solda compatível, a junta tem a resistência do metal base: não se
    verifica a solda, verifica-se a chapa.
        tração/compressão normal : f_y·A_MB/γ_a1
        cisalhamento             : 0,6·f_y·A_MB/γ_a1
    """
    A = t_chapa * comprimento
    if solicitacao.startswith("cis"):
        Rd = 0.6 * fy_base * A / GAMA_A1
        formula = "0,6·f<sub>y</sub>·A<sub>MB</sub>/γ<sub>a1</sub>"
        conta = f"0,6·{fmt(fy_base,1)}·{fmt(A,2)}/{fmt(GAMA_A1,2)}"
    else:
        Rd = fy_base * A / GAMA_A1
        formula = "f<sub>y</sub>·A<sub>MB</sub>/γ<sub>a1</sub>"
        conta = f"{fmt(fy_base,1)}·{fmt(A,2)}/{fmt(GAMA_A1,2)}"

    titulo = "Solda de penetração total" + (f" — {nome}" if nome else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, Tabela 8", Sd=F_Sd, Rd=Rd, unidade="kN")
    v.passo("Área do metal base", formula="A<sub>MB</sub> = t·L",
            conta=f"{fmt(t_chapa,2)}·{fmt(comprimento,1)}", valor=fmt(A, 2, "cm²"))
    v.passo(f"Resistência ({solicitacao})", formula=formula, conta=conta,
            valor=fmt(Rd, 1, "kN"))
    v.observacao = ("Metal de solda compatível: a junta tem a resistência do metal "
                    "base; exige ensaio por ultrassom nas juntas tracionadas.")
    return v


def penetracao_parcial(garganta_efetiva: float, comprimento: float,
                       eletrodo: str = "E70XX", fy_base: float = 25.0,
                       solicitacao: str = "tração", F_Sd: float = 0.0,
                       nome: str = "") -> Verificacao:
    """Solda de penetração parcial (NBR 8800, Tabela 8).

        tração/compressão normal à solda : 0,6·f_w·E·L/γ_w2  (solda)
                                           f_y·E·L/γ_a1      (metal base)
        cisalhamento                     : 0,6·f_w·E·L/γ_w2  (solda)
                                           0,6·f_y·E·L/γ_a1  (metal base)

    `garganta_efetiva` (E, em cm) é a profundidade do chanfro, descontados 3 mm em
    chanfros em V ou ½V de 45° soldados por SMAW em posição vertical ou sobre-cabeça.
    """
    el = eletrodo if isinstance(eletrodo, mat.Eletrodo) else mat.eletrodo(eletrodo)
    A = garganta_efetiva * comprimento
    R_solda = 0.6 * el.fw * A / GAMA_W2
    if solicitacao.startswith("cis"):
        R_base = 0.6 * fy_base * A / GAMA_A1
    else:
        R_base = fy_base * A / GAMA_A1
    Rd = min(R_solda, R_base)

    titulo = "Solda de penetração parcial" + (f" — {nome}" if nome else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, Tabela 8", Sd=F_Sd, Rd=Rd, unidade="kN")
    v.passo("Área efetiva", formula="A<sub>w</sub> = E·L",
            conta=f"{fmt(garganta_efetiva,2)}·{fmt(comprimento,1)}",
            valor=fmt(A, 2, "cm²"))
    v.passo("Metal da solda", formula="0,6·f<sub>w</sub>·A<sub>w</sub>/γ<sub>w2</sub>",
            conta=f"0,6·{fmt(el.fw,1)}·{fmt(A,2)}/{fmt(GAMA_W2,2)}",
            valor=fmt(R_solda, 1, "kN"))
    v.passo("Metal base", formula="f<sub>y</sub>·A<sub>w</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(fy_base,1)}·{fmt(A,2)}/{fmt(GAMA_A1,2)}",
            valor=fmt(R_base, 1, "kN"))
    v.passo("Governa o menor", formula="R<sub>d</sub> = mín",
            conta=f"mín({fmt(R_solda,1)} ; {fmt(R_base,1)})", valor=fmt(Rd, 1, "kN"))
    v.observacao = ("A NBR 8800 não permite penetração parcial em junta de topo sob "
                    "tração cíclica.")
    return v


def grupo_solda_excentrico(cordoes: Sequence[Tuple[float, float, float, float]],
                           P_x: float = 0.0, P_y: float = 0.0,
                           ponto_aplicacao: Tuple[float, float] = (0.0, 0.0),
                           perna: float = 0.6, eletrodo: str = "E70XX",
                           fy_base: float = 25.0, n_amostras: int = 41,
                           nome: str = "") -> Verificacao:
    """Grupo de soldas sob carga excêntrica — método elástico (NBR 8800, item 6.2.7).

    Cada cordão é um segmento (x1, y1, x2, y2), em cm, tratado como linha de
    espessura unitária. Calcula-se:
        f_v = P/L_total                        (força direta por cm)
        f_m = M·r/I_p , I_p = I_x + I_y        (torção no plano)
    e soma-se vetorialmente no ponto mais solicitado. Devolve a `Verificacao` com
    Sd = força resultante por cm e Rd = resistência do filete por cm.
    """
    if not cordoes:
        raise ErroDeDados("informe pelo menos um cordão de solda")
    # comprimento total e centro de gravidade da linha de solda
    Lt = 0.0
    sx = sy = 0.0
    for x1, y1, x2, y2 in cordoes:
        L = math.hypot(x2 - x1, y2 - y1)
        if L <= 0:
            raise ErroDeDados("cordão de solda com comprimento nulo")
        Lt += L
        sx += L * (x1 + x2) / 2.0
        sy += L * (y1 + y2) / 2.0
    xc, yc = sx / Lt, sy / Lt

    # momento polar de inércia da linha (espessura unitária)
    Ip = 0.0
    for x1, y1, x2, y2 in cordoes:
        L = math.hypot(x2 - x1, y2 - y1)
        mx, my = (x1 + x2) / 2.0 - xc, (y1 + y2) / 2.0 - yc
        dx, dy = (x2 - x1) / L, (y2 - y1) / L
        # inércia própria do segmento em torno do seu centro: L³/12 projetada
        Ip += L ** 3 / 12.0 + L * (mx * mx + my * my)

    ex, ey = ponto_aplicacao
    M = P_y * (ex - xc) - P_x * (ey - yc)
    fvx, fvy = P_x / Lt, P_y / Lt

    pior = 0.0
    ponto_pior = (xc, yc)
    for x1, y1, x2, y2 in cordoes:
        for k in range(n_amostras):
            s = k / (n_amostras - 1.0)
            x, y = x1 + s * (x2 - x1), y1 + s * (y2 - y1)
            rx, ry = x - xc, y - yc
            fx = fvx - M * ry / Ip if Ip else fvx
            fy = fvy + M * rx / Ip if Ip else fvy
            f = math.hypot(fx, fy)
            if f > pior:
                pior, ponto_pior = f, (x, y)

    r_solda, r_base, r = resistencia_filete_cm(perna, eletrodo, fy_base)
    titulo = "Grupo de soldas sob excentricidade" + (f" — {nome}" if nome else "")
    v = Verificacao(titulo, norma="NBR 8800:2008, item 6.2 (método elástico)",
                    Sd=pior, Rd=r, unidade="kN/cm")
    v.passo("Comprimento total e CG da linha de solda",
            formula="L<sub>t</sub> ; (x<sub>c</sub>, y<sub>c</sub>)",
            conta=f"{fmt(Lt,1)} cm ; ({fmt(xc,2)} ; {fmt(yc,2)})", valor=fmt(Lt, 1, "cm"))
    v.passo("Momento polar de inércia da linha",
            formula="I<sub>p</sub> = Σ(L³/12 + L·r²)", conta="",
            valor=fmt(Ip, 1, "cm³"))
    v.passo("Momento em relação ao CG",
            formula="M = P<sub>y</sub>·(e<sub>x</sub>−x<sub>c</sub>) − P<sub>x</sub>·(e<sub>y</sub>−y<sub>c</sub>)",
            conta=f"{fmt(P_y,1)}·({fmt(ex,2)}−{fmt(xc,2)}) − {fmt(P_x,1)}·({fmt(ey,2)}−{fmt(yc,2)})",
            valor=fmt(M, 1, "kN·cm"))
    v.passo("Força direta por cm",
            formula="f<sub>v</sub> = P/L<sub>t</sub>",
            conta=f"√({fmt(P_x,1)}² + {fmt(P_y,1)}²)/{fmt(Lt,1)}",
            valor=fmt(math.hypot(fvx, fvy), 2, "kN/cm"))
    v.passo("Resultante no ponto mais solicitado",
            formula="f<sub>res</sub> = √(f<sub>x</sub>² + f<sub>y</sub>²)",
            conta=f"ponto ({fmt(ponto_pior[0],2)} ; {fmt(ponto_pior[1],2)})",
            valor=fmt(pior, 2, "kN/cm"))
    v.passo(f"Resistência do filete de {fmt(perna*10,0)} mm por cm",
            formula="mín(0,6·f<sub>w</sub>·a/γ<sub>w2</sub> ; 0,6·f<sub>y</sub>·b/γ<sub>a1</sub>)",
            conta=f"mín({fmt(r_solda,2)} ; {fmt(r_base,2)})", valor=fmt(r, 2, "kN/cm"))
    return v


def solda_composicao(V_Sd: float, Q: float, I: float, perna: float,
                     eletrodo: str = "E70XX", fy_base: float = 25.0,
                     n_filetes: int = 2, trecho: Optional[float] = None,
                     passo: Optional[float] = None, t_alma: Optional[float] = None,
                     nome: str = "solda alma–mesa") -> Verificacao:
    """Fluxo de cisalhamento longitudinal na solda de composição (NBR 8800, 6.2).

        q = V·Q/I   (kN/cm, total, dividido entre os `n_filetes`)

    Com `trecho` e `passo` verifica-se a solda intermitente, cuja capacidade média
    é r·(trecho/passo). O passo é limitado a 24·t_alma e a 300 mm (item 6.3.10,
    aplicado por analogia à composição — a NBR 8800 usa o mesmo limite de contato).
    """
    if I <= 0:
        raise ErroDeDados("o momento de inércia I tem de ser positivo")
    q = V_Sd * Q / I
    q_filete = q / n_filetes
    r_solda, r_base, r = resistencia_filete_cm(perna, eletrodo, fy_base)
    capacidade = r
    if trecho and passo:
        capacidade = r * trecho / passo

    v = Verificacao(f"Fluxo de cisalhamento — {nome}",
                    norma="NBR 8800:2008, item 6.2 (composição de perfil soldado)",
                    Sd=q_filete, Rd=capacidade, unidade="kN/cm")
    v.passo("Fluxo de cisalhamento longitudinal",
            formula="q = V<sub>Sd</sub>·Q/I",
            conta=f"{fmt(V_Sd,1)}·{fmt(Q,1)}/{fmt(I,0)}", valor=fmt(q, 2, "kN/cm"))
    v.passo(f"Dividido entre {n_filetes} filete(s)",
            formula="q/n", conta=f"{fmt(q,2)}/{n_filetes}",
            valor=fmt(q_filete, 2, "kN/cm"))
    v.passo(f"Resistência do filete de {fmt(perna*10,0)} mm",
            formula="mín(metal da solda ; metal base)",
            conta=f"mín({fmt(r_solda,2)} ; {fmt(r_base,2)})", valor=fmt(r, 2, "kN/cm"))
    if trecho and passo:
        v.passo("Solda intermitente",
                formula="r<sub>méd</sub> = r·L/P",
                conta=f"{fmt(r,2)}·{fmt(trecho,1)}/{fmt(passo,1)}",
                valor=fmt(capacidade, 2, "kN/cm"))
        obs = []
        if trecho < max(4 * perna, 4.0):
            obs.append(f"trecho {trecho*10:.0f} mm menor que 4·b e 40 mm")
        if t_alma:
            pmax = min(24 * t_alma, 30.0)
            if passo > pmax:
                obs.append(f"passo {passo*10:.0f} mm maior que 24·t = {pmax*10:.0f} mm")
        obs.append("não usar solda intermitente em ambiente agressivo nem sob fadiga")
        v.observacao = "; ".join(obs)
    return v


# ---------------------------------------------------------------------------
# 4. Ligações típicas completas
# ---------------------------------------------------------------------------

def _perfil_mm(p) -> dict:
    """Normaliza um `Perfil` ou dicionário para (d, bf, tw, tf) em mm e A em cm²."""
    if isinstance(p, Perfil):
        return {"nome": p.nome, "d": p.d, "bf": p.bf, "tw": p.tw, "tf": p.tf,
                "A": p.A, "Ix": p.Ix, "Zx": p.Zx, "Wx": p.Wx}
    if isinstance(p, dict):
        faltando = [k for k in ("d", "bf", "tw", "tf") if k not in p]
        if faltando:
            raise ErroDeDados(f"perfil informado sem as dimensões {', '.join(faltando)} "
                              "(em mm)")
        return dict(p)
    if isinstance(p, str):
        from .perfis import perfil as _p
        return _perfil_mm(_p(p))
    raise ErroDeDados(f"perfil não reconhecido: {p!r}")


def dupla_cantoneira(viga, V_Sd: float, n_parafusos: int = 3,
                     diametro: str = '3/4"', parafuso: str = "ASTM A325",
                     t_cantoneira: float = 0.79, aba: float = 7.6,
                     gabarito: float = 4.4, passo: float = 7.6,
                     borda_vertical: float = 3.0, dist_extremidade_viga: float = 3.5,
                     aco_viga: str = "ASTM A36", aco_cantoneira: str = "ASTM A36",
                     rosca_no_plano: bool = True, furo: str = "padrão",
                     recorte: bool = False, borda_recorte: float = 4.0,
                     t_apoio: Optional[float] = None, fu_apoio: Optional[float] = None,
                     elemento: str = "Ligação flexível com dupla cantoneira"
                     ) -> Resultado:
    """Ligação flexível viga–viga ou viga–pilar com duas cantoneiras de alma.

    Caminho da carga: alma da viga → parafusos em corte duplo → cantoneiras →
    parafusos em corte simples (um por aba) → mesa do pilar ou alma da viga principal.

    Reproduz o Exemplo 8.1 do cap. 8 do manual. Geometria (cm):
        `aba`              largura da aba da cantoneira
        `gabarito`         g, do talão à linha de furos
        `passo`            espaçamento vertical entre furos
        `borda_vertical`   distância da ponta da cantoneira ao primeiro furo
        `dist_extremidade_viga`  da extremidade da viga ao primeiro furo, na alma
    """
    g = _perfil_mm(viga)
    tw = g["tw"] / 10.0
    av, ac = mat.aco(aco_viga), mat.aco(aco_cantoneira)
    nome_d, d, Ab, _ = _diam(diametro)
    dh = diametro_furo(d, furo)[0]
    L_cant = 2 * borda_vertical + (n_parafusos - 1) * passo

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_cantoneira)
    r.dados.update({
        "viga": g.get("nome", ""), "tw_viga": tw, "V_Sd": V_Sd,
        "n_parafusos": n_parafusos, "diametro": nome_d, "parafuso": parafuso,
        "cantoneira_t": t_cantoneira, "cantoneira_aba": aba,
        "cantoneira_L": L_cant, "gabarito": gabarito, "passo": passo,
        "borda_vertical": borda_vertical, "d_furo": dh,
        "dist_extremidade_viga": dist_extremidade_viga, "recorte": recorte,
        "furacao_mm": [borda_vertical * 10] + [passo * 10] * (n_parafusos - 1)
                      + [borda_vertical * 10],
    })

    # 1. parafusos na alma da viga — corte duplo
    v = cisalhamento_parafuso(nome_d, parafuso, planos=2,
                              rosca_no_plano=rosca_no_plano, Fv_Sd=V_Sd,
                              n=n_parafusos)
    v.titulo = f"Parafusos na alma da viga (corte duplo) — {n_parafusos} × {nome_d}"
    r.add(v)

    # 2. parafusos no apoio — corte simples, n por aba, 2 abas
    v = cisalhamento_parafuso(nome_d, parafuso, planos=1,
                              rosca_no_plano=rosca_no_plano, Fv_Sd=V_Sd,
                              n=2 * n_parafusos)
    v.titulo = (f"Parafusos no apoio (corte simples) — {2*n_parafusos} × {nome_d}")
    v.observacao = ("A excentricidade do cortante em relação a esta linha (g = "
                    f"{gabarito*10:.0f} mm) gera pequena tração nos parafusos "
                    "superiores; em ligação flexível com g ≤ 65 mm ela é absorvida "
                    "pela flexibilidade das abas (item 8.7.1 do manual).")
    r.add(v)

    # 3. esmagamento na alma da viga
    r.add(esmagamento(nome_d, tw, av.fu, distancia_borda=dist_extremidade_viga,
                      espacamento=passo, furo=furo, Fc_Sd=V_Sd,
                      n_borda=1, n_interno=n_parafusos - 1,
                      nome_chapa="alma da viga"))

    # 4. esmagamento nas cantoneiras (2)
    v = esmagamento(nome_d, t_cantoneira, ac.fu, distancia_borda=borda_vertical,
                    espacamento=passo, furo=furo, Fc_Sd=V_Sd,
                    n_borda=1, n_interno=n_parafusos - 1,
                    nome_chapa="cantoneiras (2)")
    v.Rd *= 2
    v.passo("Duas cantoneiras", formula="R<sub>d</sub> = 2 × (por cantoneira)",
            conta=f"2 × {fmt(v.Rd/2, 1)}", valor=fmt(v.Rd, 1, "kN"))
    r.add(v)

    # 5. bloco de cisalhamento nas cantoneiras
    Lv = borda_vertical + (n_parafusos - 1) * passo       # ponta ao último furo
    w = largura_desconto_furo(dh)
    n_furos_v = (n_parafusos - 1) + 0.5                   # meio furo na extremidade
    Agv = Lv * t_cantoneira
    Anv = (Lv - n_furos_v * w) * t_cantoneira
    bt = aba - gabarito                                   # linha de furos à borda da aba
    Agt = bt * t_cantoneira
    Ant = (bt - w / 2.0) * t_cantoneira
    v = bloco_cisalhamento(Agv, Anv, Agt, Ant, ac.fy, ac.fu, Cts=1.0,
                           Sd=V_Sd / 2.0, nome="cantoneira (aba na alma)")
    Rd1 = v.Rd
    v.Rd = 2 * Rd1
    v.Sd = V_Sd
    v.passo("Duas cantoneiras", formula="R<sub>d</sub> = 2 × (por cantoneira)",
            conta=f"2 × {fmt(Rd1, 1)}", valor=fmt(v.Rd, 1, "kN"))
    r.add(v)
    r.dados["bloco_cantoneira_por_peca"] = Rd1

    # 6. bloco de cisalhamento na alma da viga (só com recorte de mesa)
    if recorte:
        Lv2 = dist_extremidade_viga + (n_parafusos - 1) * passo
        Agv2 = Lv2 * tw
        Anv2 = (Lv2 - n_furos_v * w) * tw
        Ant2 = (borda_recorte - w / 2.0) * tw
        r.add(bloco_cisalhamento(Agv2, Anv2, borda_recorte * tw, Ant2,
                                 av.fy, av.fu, Cts=0.5, Sd=V_Sd,
                                 nome="alma da viga recortada"))
    else:
        v = Verificacao("Bloco de cisalhamento na alma da viga",
                        norma="NBR 8800:2008, item 6.5.6", dispensada=True)
        v.observacao = ("Viga sem recorte de mesa: a alma não tem bloco livre para "
                        "arrancar. Com recorte (ligação viga–viga), o estado-limite "
                        "passa a ser crítico — use recorte=True.")
        r.add(v)

    # 7. cisalhamento das cantoneiras — seção bruta e líquida
    Ag = L_cant * t_cantoneira
    An = (L_cant - n_parafusos * w) * t_cantoneira
    Rd_bruta = 2 * 0.6 * ac.fy * Ag / GAMA_A1
    Rd_liq = 2 * 0.6 * ac.fu * An / GAMA_A2
    v = Verificacao("Cisalhamento das cantoneiras",
                    norma="NBR 8800:2008, itens 5.4.3.5 e 6.5.5",
                    Sd=V_Sd, Rd=min(Rd_bruta, Rd_liq), unidade="kN")
    v.passo("Escoamento da seção bruta (2 cantoneiras)",
            formula="2·0,6·f<sub>y</sub>·A<sub>g</sub>/γ<sub>a1</sub>",
            conta=f"2·0,6·{fmt(ac.fy,1)}·{fmt(Ag,2)}/{fmt(GAMA_A1,2)}",
            valor=fmt(Rd_bruta, 0, "kN"))
    v.passo("Ruptura da seção líquida (2 cantoneiras)",
            formula="2·0,6·f<sub>u</sub>·A<sub>n</sub>/γ<sub>a2</sub>",
            conta=f"2·0,6·{fmt(ac.fu,1)}·{fmt(An,2)}/{fmt(GAMA_A2,2)}",
            valor=fmt(Rd_liq, 0, "kN"))
    r.add(v)

    # 8. esmagamento na peça de apoio, quando informada
    if t_apoio and fu_apoio:
        v = esmagamento(nome_d, t_apoio, fu_apoio,
                        distancia_borda=borda_vertical, espacamento=passo,
                        furo=furo, Fc_Sd=V_Sd, n_borda=2, n_interno=2*(n_parafusos-1),
                        nome_chapa="mesa do pilar / alma da viga principal")
        r.add(v)

    r.dados["comprimento_cantoneira_mm"] = L_cant * 10
    return r


def chapa_simples(viga, V_Sd: float, n_parafusos: int = 3, diametro: str = '3/4"',
                  parafuso: str = "ASTM A325", t_chapa: float = 0.95,
                  altura_chapa: Optional[float] = None, largura_chapa: float = 10.0,
                  a_excentricidade: float = 6.0, passo: float = 7.6,
                  borda_vertical: float = 3.0, borda_horizontal: float = 3.5,
                  aco_chapa: str = "ASTM A36", aco_viga: str = "ASTM A36",
                  perna_solda: float = 0.6, eletrodo: str = "E70XX",
                  rosca_no_plano: bool = True, furo: str = "padrão",
                  elemento: str = "Ligação com chapa simples") -> Resultado:
    """Chapa simples (*single plate*) soldada ao pilar e parafusada na alma da viga.

    A chapa é soldada de fábrica com filete dos dois lados e a viga é parafusada em
    obra com uma linha vertical de parafusos a `a_excentricidade` da face do apoio.
    Verifica-se o corte excêntrico dos parafusos (método elástico), o esmagamento
    na chapa e na alma, a chapa à flexão e ao cisalhamento, o bloco de cisalhamento
    da chapa e a solda ao pilar (cortante + momento V·a).
    """
    g = _perfil_mm(viga)
    tw = g["tw"] / 10.0
    ach, av = mat.aco(aco_chapa), mat.aco(aco_viga)
    nome_d, d, Ab, _ = _diam(diametro)
    dh = diametro_furo(d, furo)[0]
    h = altura_chapa or (2 * borda_vertical + (n_parafusos - 1) * passo)
    M_exc = V_Sd * a_excentricidade

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_chapa)
    r.dados.update({"t_chapa": t_chapa, "altura_chapa": h, "largura_chapa": largura_chapa,
                    "a": a_excentricidade, "n_parafusos": n_parafusos, "passo": passo,
                    "diametro": nome_d, "d_furo": dh, "perna_solda": perna_solda,
                    "V_Sd": V_Sd, "M_excentrico": M_exc,
                    "desvio_alma_mm": (t_chapa + tw) / 2 * 10})

    # 1. parafusos: corte direto + excentricidade (método elástico)
    pontos = coordenadas_grupo(n_parafusos, 1, passo, 0.0)
    dist = esforcos_no_grupo(pontos, V_Sd=V_Sd, excentricidade=a_excentricidade)
    F_max = dist["F_max"]
    v = cisalhamento_parafuso(nome_d, parafuso, planos=1,
                              rosca_no_plano=rosca_no_plano, Fv_Sd=F_max)
    v.titulo = f"Parafuso mais solicitado (corte excêntrico) — {nome_d}"
    v.passo("Momento de excentricidade",
            formula="M = V<sub>Sd</sub>·a", conta=f"{fmt(V_Sd,1)}·{fmt(a_excentricidade,1)}",
            valor=fmt(M_exc, 0, "kN·cm"))
    v.passo("Momento polar de inércia do grupo",
            formula="I<sub>p</sub> = Σ(x² + y²)", conta="",
            valor=fmt(dist["Ip"], 1, "cm²"))
    v.passo("Força no parafuso mais solicitado",
            formula="F = √((V/n)² + (M·r/I<sub>p</sub>)²)",
            conta=f"V/n = {fmt(dist['fy_direto'],1)} kN", valor=fmt(F_max, 1, "kN"))
    r.add(v)
    r.dados["F_max_parafuso"] = F_max
    r.dados["Ip"] = dist["Ip"]

    # 2. esmagamento na chapa e na alma
    for nome_ch, t, aco in (("chapa", t_chapa, ach), ("alma da viga", tw, av)):
        r.add(esmagamento(nome_d, t, aco.fu, distancia_borda=borda_horizontal,
                          espacamento=passo, furo=furo, Fc_Sd=F_max * n_parafusos,
                          n_borda=1, n_interno=n_parafusos - 1, nome_chapa=nome_ch))

    # 3. chapa: cisalhamento bruto e líquido
    Ag = h * t_chapa
    An = (h - n_parafusos * largura_desconto_furo(dh)) * t_chapa
    Rd_v = min(0.6 * ach.fy * Ag / GAMA_A1, 0.6 * ach.fu * An / GAMA_A2)
    v = Verificacao("Cisalhamento da chapa", norma="NBR 8800:2008, itens 5.4.3.5 e 6.5.5",
                    Sd=V_Sd, Rd=Rd_v, unidade="kN")
    v.passo("Escoamento da seção bruta",
            formula="0,6·f<sub>y</sub>·A<sub>g</sub>/γ<sub>a1</sub>",
            conta=f"0,6·{fmt(ach.fy,1)}·{fmt(Ag,2)}/{fmt(GAMA_A1,2)}",
            valor=fmt(0.6*ach.fy*Ag/GAMA_A1, 0, "kN"))
    v.passo("Ruptura da seção líquida",
            formula="0,6·f<sub>u</sub>·A<sub>n</sub>/γ<sub>a2</sub>",
            conta=f"0,6·{fmt(ach.fu,1)}·{fmt(An,2)}/{fmt(GAMA_A2,2)}",
            valor=fmt(0.6*ach.fu*An/GAMA_A2, 0, "kN"))
    r.add(v)

    # 4. chapa à flexão pela excentricidade (seção líquida, plastificação)
    Z_liq = t_chapa * h * h / 4.0
    for y in [abs(p[1]) for p in pontos]:
        Z_liq -= t_chapa * largura_desconto_furo(dh) * y
    Z_liq = max(Z_liq, 0.1)
    M_Rd = Z_liq * ach.fy / GAMA_A1
    v = Verificacao("Flexão da chapa pela excentricidade",
                    norma="NBR 8800:2008, item 5.4.2 (seção compacta)",
                    Sd=M_exc, Rd=M_Rd, unidade="kN·cm")
    v.passo("Módulo plástico líquido da chapa",
            formula="Z = t·h²/4 − Σ t·(d<sub>h</sub>+2)·y<sub>i</sub>",
            conta=f"t = {fmt(t_chapa,2)} cm, h = {fmt(h,1)} cm",
            valor=fmt(Z_liq, 1, "cm³"))
    v.passo("Momento resistente", formula="M<sub>Rd</sub> = Z·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Z_liq,1)}·{fmt(ach.fy,1)}/{fmt(GAMA_A1,2)}",
            valor=fmt(M_Rd, 0, "kN·cm"))
    r.add(v)

    # 5. bloco de cisalhamento na chapa
    w = largura_desconto_furo(dh)
    Lv = borda_vertical + (n_parafusos - 1) * passo
    Agv = Lv * t_chapa
    Anv = (Lv - ((n_parafusos - 1) + 0.5) * w) * t_chapa
    Agt = borda_horizontal * t_chapa
    Ant = (borda_horizontal - w / 2.0) * t_chapa
    r.add(bloco_cisalhamento(Agv, Anv, Agt, Ant, ach.fy, ach.fu, Cts=1.0,
                             Sd=V_Sd, nome="chapa simples"))

    # 6. solda da chapa ao pilar: dois filetes verticais com cortante + momento
    v = grupo_solda_excentrico([(0.0, -h / 2, 0.0, h / 2),
                                (t_chapa, -h / 2, t_chapa, h / 2)],
                               P_y=V_Sd, ponto_aplicacao=(a_excentricidade, 0.0),
                               perna=perna_solda, eletrodo=eletrodo,
                               fy_base=min(ach.fy, av.fy),
                               nome="chapa ao pilar (2 filetes verticais)")
    r.add(v)
    return r


def t_stub_espessura_minima(T_por_parafuso: float, b: float, p: float, fy: float,
                            d_parafuso: float) -> Tuple[float, float]:
    """Espessura mínima da chapa que elimina o efeito alavanca (Exemplo 8.3 do manual).

        t_min = √(4·T·b'·γ_a1/(p·f_y)),   b' = b − d/2

    `b` é a distância do eixo do parafuso à face da alma/mesa e `p` a largura
    tributária por parafuso (cm). Devolve (t_min, b').

    Origem: AISC (modelo T-stub), adaptada ao formato da NBR 8800 com escoamento
    da chapa e γ_a1. A NBR 8800 não traz expressão própria para o efeito alavanca.
    """
    b_linha = b - d_parafuso / 2.0
    if b_linha <= 0:
        raise ErroDeDados("b' = b − d/2 resultou não positivo: aproxime menos o "
                          "parafuso da alma")
    t_min = math.sqrt(4.0 * T_por_parafuso * b_linha * GAMA_A1 / (p * fy))
    return t_min, b_linha


def forca_alavanca(T_por_parafuso: float, t_chapa: float, b: float, a: float,
                   p: float, fy: float, d_parafuso: float,
                   d_furo: float) -> dict:
    """Força de alavanca Q (*prying*) numa chapa tracionada — modelo T-stub.

    Formulação de Thornton/AISC (Manual, Part 9), fora do escopo da NBR 8800:
        b' = b − d/2 ;  a' = mín(a ; 1,25·b) + d/2 ;  ρ = b'/a'
        δ = 1 − d_h/p
        t_c = √(4·T·b'·γ_a1/(p·f_y))            (espessura que anula Q)
        α = [(t_c/t)² − 1]/δ ,  limitado a 0 ≤ α ≤ 1
        Q = T·δ·α·ρ/(1 + δ·α)

    Devolve dict com t_c, b', a', ρ, δ, α e Q. Com t ≥ t_c resulta α = 0 e Q = 0.
    """
    t_c, b_linha = t_stub_espessura_minima(T_por_parafuso, b, p, fy, d_parafuso)
    a_linha = min(a, 1.25 * b) + d_parafuso / 2.0
    rho = b_linha / a_linha
    delta = 1.0 - d_furo / p
    if delta <= 0:
        raise ErroDeDados("δ = 1 − d_h/p não positivo: a largura tributária p é "
                          "menor que o furo")
    if t_chapa <= 0:
        raise ErroDeDados("a espessura da chapa tem de ser positiva")
    alfa = ((t_c / t_chapa) ** 2 - 1.0) / delta
    alfa = max(0.0, min(1.0, alfa))
    Q = T_por_parafuso * delta * alfa * rho / (1.0 + delta * alfa)
    return {"t_c": t_c, "b_linha": b_linha, "a_linha": a_linha, "rho": rho,
            "delta": delta, "alfa": alfa, "Q": Q, "T_total": T_por_parafuso + Q}


def chapa_de_topo(viga, M_Sd: float, V_Sd: float = 0.0, N_Sd: float = 0.0,
                  diametro: str = '3/4"', parafuso: str = "ASTM A325",
                  n_por_linha: int = 2, linhas_tracionadas: int = 2,
                  t_chapa: float = 1.9, largura_chapa: Optional[float] = None,
                  gabarito: float = 10.0, b_alavanca: Optional[float] = None,
                  a_alavanca: Optional[float] = None,
                  passo_linhas: float = 9.0,
                  aco_chapa: str = "ASTM A36", aco_viga: str = "ASTM A36",
                  pilar=None, aco_pilar: str = "ASTM A36",
                  perna_alma: float = 0.6, eletrodo: str = "E70XX",
                  penetracao_nas_mesas: bool = True, furo: str = "padrão",
                  elemento: str = "Ligação rígida com chapa de topo") -> Resultado:
    """Ligação rígida viga–pilar com chapa de topo (*end plate*).

    Modelo (item 8.6.3 do manual):
      * o momento é transmitido pelo binário das mesas: T = C = M/(d − t_f);
      * a tração T é dividida igualmente entre os parafusos das linhas tracionadas
        (hipótese usual de chapa estendida com parafusos protendidos);
      * o efeito alavanca é avaliado pelo modelo T-stub (`forca_alavanca`) e somado
        à tração do parafuso; com t ≥ t_c, Q = 0;
      * a espessura da chapa vem do mesmo modelo T-stub (flexão da faixa tributária);
      * solda: penetração total nas mesas (ou filete dimensionado para T) e filete
        na alma para o cortante;
      * a alma e a mesa do pilar são verificadas às forças localizadas (item 5.7),
        indicando se o enrijecedor é necessário.
    """
    g = _perfil_mm(viga)
    d_v, tf_v, tw_v, bf_v = g["d"] / 10.0, g["tf"] / 10.0, g["tw"] / 10.0, g["bf"] / 10.0
    ach, av = mat.aco(aco_chapa), mat.aco(aco_viga)
    nome_d, d_par, Ab, _ = _diam(diametro)
    dh = diametro_furo(d_par, furo)[0]
    bch = largura_chapa or max(bf_v + 3.0, gabarito + 6.0 * d_par)
    b_al = b_alavanca if b_alavanca is not None else (gabarito - tw_v) / 2.0
    a_al = a_alavanca if a_alavanca is not None else min((bch - gabarito) / 2.0, 1.25 * b_al)

    braco = d_v - tf_v
    T = M_Sd / braco + N_Sd / 2.0
    n_trac = n_por_linha * linhas_tracionadas
    T_par = T / n_trac
    p_trib = passo_linhas if linhas_tracionadas > 1 else bch / n_por_linha

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_chapa)
    r.dados.update({"M_Sd": M_Sd, "V_Sd": V_Sd, "N_Sd": N_Sd, "braco": braco,
                    "T": T, "C": T, "n_tracionados": n_trac, "T_por_parafuso": T_par,
                    "t_chapa": t_chapa, "largura_chapa": bch, "gabarito": gabarito,
                    "passo_linhas": passo_linhas, "diametro": nome_d, "d_furo": dh,
                    "b_alavanca": b_al, "a_alavanca": a_al, "p_tributario": p_trib})

    # 1. binário
    v = Verificacao("Binário do momento nas mesas",
                    norma="NBR 8800:2008, item 6.1 (equilíbrio da ligação)",
                    Sd=T, Rd=T, unidade="kN")
    v.passo("Braço do binário", formula="d − t<sub>f</sub>",
            conta=f"{fmt(d_v,2)} − {fmt(tf_v,2)}", valor=fmt(braco, 2, "cm"))
    v.passo("Tração na mesa superior",
            formula="T = M<sub>Sd</sub>/(d − t<sub>f</sub>) + N<sub>Sd</sub>/2",
            conta=f"{fmt(M_Sd,0)}/{fmt(braco,2)} + {fmt(N_Sd,1)}/2",
            valor=fmt(T, 1, "kN"))
    v.passo(f"Dividida entre {n_trac} parafusos tracionados",
            formula="T/n", conta=f"{fmt(T,1)}/{n_trac}", valor=fmt(T_par, 1, "kN"))
    v.dispensada = True   # é o passo de equilíbrio, não um estado-limite
    r.add(v)

    # 2. efeito alavanca
    al = forca_alavanca(T_par, t_chapa, b_al, a_al, p_trib, ach.fy, d_par, dh)
    r.dados["alavanca"] = al
    T_total = al["T_total"]
    v = Verificacao("Efeito alavanca na chapa de topo (modelo T-stub)",
                    norma="fora do escopo da NBR 8800 — formulação AISC (Thornton)",
                    Sd=al["Q"], Rd=max(T_par, 1e-9), unidade="kN")
    v.passo("Espessura que anula a alavanca",
            formula="t<sub>c</sub> = √(4·T·b'·γ<sub>a1</sub>/(p·f<sub>y</sub>))",
            conta=f"√(4·{fmt(T_par,1)}·{fmt(al['b_linha'],2)}·{fmt(GAMA_A1,2)}/"
                  f"({fmt(p_trib,1)}·{fmt(ach.fy,1)}))",
            valor=fmt(al["t_c"], 2, "cm"))
    v.passo("Parâmetros do modelo",
            formula="ρ = b'/a' ; δ = 1 − d<sub>h</sub>/p ; α",
            conta=f"ρ = {fmt(al['rho'],3)} ; δ = {fmt(al['delta'],3)}",
            valor=f"α = {fmt(al['alfa'], 3)}")
    v.passo("Força de alavanca",
            formula="Q = T·δ·α·ρ/(1 + δ·α)",
            conta=f"{fmt(T_par,1)}·{fmt(al['delta'],3)}·{fmt(al['alfa'],3)}·"
                  f"{fmt(al['rho'],3)}/(1 + {fmt(al['delta']*al['alfa'],3)})",
            valor=fmt(al["Q"], 1, "kN"))
    v.passo("Tração total no parafuso",
            formula="T + Q", conta=f"{fmt(T_par,1)} + {fmt(al['Q'],1)}",
            valor=fmt(T_total, 1, "kN"))
    v.observacao = ("A NBR 8800 não traz expressão para o efeito alavanca; adotou-se "
                    "o modelo T-stub do AISC com escoamento da chapa e γ_a1. "
                    + ("Chapa espessa o bastante: Q = 0." if al["alfa"] <= 0 else
                       "Chapa flexível: a alavanca aumenta a tração no parafuso em "
                       f"{100*al['Q']/max(T_par,1e-9):.0f} %."))
    v.dispensada = True
    r.add(v)

    # 3. tração dos parafusos, com alavanca
    r.add(tracao_parafuso(nome_d, parafuso, Ft_Sd=T_total))

    # 4. cisalhamento e interação (o cortante é dividido por todos os parafusos)
    n_total = n_por_linha * (linhas_tracionadas + 2)
    V_par = V_Sd / n_total if n_total else 0.0
    r.dados["n_total_parafusos"] = n_total
    r.add(cisalhamento_parafuso(nome_d, parafuso, planos=1, rosca_no_plano=True,
                                Fv_Sd=V_par))
    r.add(interacao_tracao_cisalhamento(nome_d, parafuso, T_total, V_par))

    # 5. espessura da chapa pelo modelo T-stub
    v = Verificacao("Espessura da chapa de topo (flexão — modelo T-stub)",
                    norma="modelo T-stub (AISC), formato NBR 8800 com γ_a1",
                    Sd=al["t_c"], Rd=t_chapa, unidade="cm")
    v.passo("Espessura necessária para eliminar a alavanca",
            formula="t<sub>min</sub> = √(4·T·b'·γ<sub>a1</sub>/(p·f<sub>y</sub>))",
            conta=f"b' = {fmt(al['b_linha'],2)} cm ; p = {fmt(p_trib,1)} cm",
            valor=fmt(al["t_c"], 2, "cm"))
    v.passo("Espessura adotada", formula="t", conta="",
            valor=fmt(t_chapa * 10, 1, "mm"))
    r.add(v)

    # 6. soldas
    if penetracao_nas_mesas:
        r.add(penetracao_total(tf_v, bf_v, av.fy, solicitacao="tração", F_Sd=T,
                               nome="mesa tracionada × chapa de topo"))
    else:
        perna_mesa = max(mat.perna_minima(max(tf_v, t_chapa)), 0.6)
        r.add(filete(perna_mesa, 2 * bf_v, eletrodo, min(av.fy, ach.fy),
                     t_base=max(tf_v, t_chapa), F_Sd=T, n_cordoes=1,
                     nome="mesa tracionada (filete dos dois lados)"))
    h_alma = d_v - 2 * tf_v
    r.add(filete(perna_alma, h_alma, eletrodo, min(av.fy, ach.fy),
                 t_base=max(tw_v, t_chapa), t_outra=tw_v, F_Sd=V_Sd, n_cordoes=2,
                 nome="alma da viga × chapa de topo"))

    # 7. alma e mesa do pilar sob a força localizada T (e C)
    if pilar is not None:
        gp = _perfil_mm(pilar)
        ap = mat.aco(aco_pilar)
        twp, tfp, dp = gp["tw"] / 10.0, gp["tf"] / 10.0, gp["d"] / 10.0
        k = tfp + 1.0            # mesa + raio de concordância estimado (1 cm)
        lb = tf_v + 2 * t_chapa  # extensão da carga aplicada
        h_p = dp - 2 * tfp

        Rd_mesa = 6.25 * tfp ** 2 * ap.fy / GAMA_A1
        v = Verificacao("Flexão local da mesa do pilar (lado tracionado)",
                        norma="NBR 8800:2008, item 5.7.2", Sd=T, Rd=Rd_mesa, unidade="kN")
        v.passo("Resistência à flexão local da mesa",
                formula="R<sub>d</sub> = 6,25·t<sub>f</sub>²·f<sub>y</sub>/γ<sub>a1</sub>",
                conta=f"6,25·{fmt(tfp,2)}²·{fmt(ap.fy,1)}/{fmt(GAMA_A1,2)}",
                valor=fmt(Rd_mesa, 0, "kN"))
        r.add(v)

        Rd_esc = (5 * k + lb) * twp * ap.fy / GAMA_A1
        v = Verificacao("Escoamento local da alma do pilar",
                        norma="NBR 8800:2008, item 5.7.3", Sd=T, Rd=Rd_esc, unidade="kN")
        v.passo("Resistência ao escoamento local",
                formula="R<sub>d</sub> = (5·k + l<sub>b</sub>)·t<sub>w</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
                conta=f"(5·{fmt(k,2)} + {fmt(lb,2)})·{fmt(twp,2)}·{fmt(ap.fy,1)}/{fmt(GAMA_A1,2)}",
                valor=fmt(Rd_esc, 0, "kN"))
        r.add(v)

        Rd_enr = (0.66 * twp ** 2 *
                  (1 + 3 * (lb / h_p) * (twp / tfp) ** 1.5) *
                  math.sqrt(E * ap.fy * tfp / twp) / GAMA_A1)
        v = Verificacao("Enrugamento da alma do pilar (lado comprimido)",
                        norma="NBR 8800:2008, item 5.7.4", Sd=T, Rd=Rd_enr, unidade="kN")
        v.passo("Resistência ao enrugamento",
                formula="R<sub>d</sub> = 0,66·t<sub>w</sub>²·[1+3(l<sub>b</sub>/h)(t<sub>w</sub>/t<sub>f</sub>)^1,5]·"
                        "√(E·f<sub>y</sub>·t<sub>f</sub>/t<sub>w</sub>)/γ<sub>a1</sub>",
                conta=f"t<sub>w</sub> = {fmt(twp,2)} cm ; l<sub>b</sub>/h = {fmt(lb/h_p,3)}",
                valor=fmt(Rd_enr, 0, "kN"))
        r.add(v)

        Rd_cis = 0.6 * ap.fy * dp * twp / GAMA_A1
        v = Verificacao("Cisalhamento do painel de alma do pilar",
                        norma="NBR 8800:2008, item 5.4.3.5", Sd=T, Rd=Rd_cis, unidade="kN")
        v.passo("Resistência ao cisalhamento do painel",
                formula="V<sub>Rd</sub> = 0,6·f<sub>y</sub>·d·t<sub>w</sub>/γ<sub>a1</sub>",
                conta=f"0,6·{fmt(ap.fy,1)}·{fmt(dp,2)}·{fmt(twp,2)}/{fmt(GAMA_A1,2)}",
                valor=fmt(Rd_cis, 0, "kN"))
        r.add(v)

        precisa = any(vv.razao > 1.0 for vv in (r.verificacoes[-4:]))
        r.dados["enrijecedor_necessario"] = precisa
        r.dados["pilar"] = gp.get("nome", "")
        v = Verificacao("Enrijecedores na alma do pilar",
                        norma="NBR 8800:2008, item 5.7.7", dispensada=not precisa,
                        Sd=T if precisa else 0.0,
                        Rd=T if precisa else 0.0, unidade="kN")
        v.observacao = ("Enrijecedores alinhados com as mesas da viga são NECESSÁRIOS: "
                        "algum estado-limite de força localizada foi ultrapassado."
                        if precisa else
                        "O pilar resiste às forças localizadas sem enrijecedor; ainda "
                        "assim, para a ligação ser efetivamente rígida a prática "
                        "recomenda enrijecer (item 8.6.3 do manual).")
        r.add(v)
    return r


def gusset_contraventamento(N_Sd: float, t_gusset: float, largura_ligacao: float,
                            comprimento_ligacao: float, aco_gusset: str = "ASTM A36",
                            diametro: Optional[str] = None,
                            parafuso: str = "ASTM A325", n_parafusos: int = 0,
                            passo: float = 5.7, borda: float = 3.5,
                            gabarito_barra: float = 4.4,
                            t_barra: Optional[float] = None,
                            aco_barra: str = "ASTM A36",
                            perna_solda: float = 0.6, eletrodo: str = "E70XX",
                            comprimento_solda: float = 0.0, n_cordoes: int = 2,
                            angulo_whitmore: float = 30.0,
                            furo: str = "padrão",
                            elemento: str = "Chapa gusset de contraventamento"
                            ) -> Resultado:
    """Chapa gusset com barra tracionada (diagonal de contraventamento).

    Verificações: seção de Whitmore (escoamento do gusset na largura efetiva),
    bloco de cisalhamento no gusset, solda gusset–pilar/viga (ou parafusos),
    esmagamento e corte dos parafusos quando a ligação é parafusada.

    `largura_ligacao` é a largura da barra/aba ligada (cm) e `comprimento_ligacao`
    o comprimento da ligação na direção da força (cm) — o comprimento dos cordões
    longitudinais ou a distância do primeiro ao último parafuso.
    """
    ag = mat.aco(aco_gusset)
    r = Resultado(elemento, material=aco_gusset)
    tg30 = math.tan(math.radians(angulo_whitmore))
    bw = largura_ligacao + 2.0 * comprimento_ligacao * tg30
    Aw = bw * t_gusset
    Rd_w = min(Aw * ag.fy / GAMA_A1, Aw * ag.fu / GAMA_A2)

    r.dados.update({"t_gusset": t_gusset, "largura_whitmore": bw, "A_whitmore": Aw,
                    "N_Sd": N_Sd, "comprimento_ligacao": comprimento_ligacao,
                    "largura_ligacao": largura_ligacao})

    v = Verificacao("Seção de Whitmore do gusset",
                    norma="prática AISC (não coberta pela NBR 8800); escoamento "
                          "conforme NBR 8800, item 5.2.2",
                    Sd=N_Sd, Rd=Rd_w, unidade="kN")
    v.passo("Largura efetiva de Whitmore",
            formula=f"b<sub>w</sub> = w + 2·l·tg {fmt(angulo_whitmore,0)}°",
            conta=f"{fmt(largura_ligacao,1)} + 2·{fmt(comprimento_ligacao,1)}·{fmt(tg30,4)}",
            valor=fmt(bw, 2, "cm"))
    v.passo("Área efetiva", formula="A<sub>w</sub> = b<sub>w</sub>·t",
            conta=f"{fmt(bw,2)}·{fmt(t_gusset,2)}", valor=fmt(Aw, 2, "cm²"))
    v.passo("Escoamento da seção de Whitmore",
            formula="A<sub>w</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Aw,2)}·{fmt(ag.fy,1)}/{fmt(GAMA_A1,2)}",
            valor=fmt(Aw * ag.fy / GAMA_A1, 0, "kN"))
    r.add(v)

    if n_parafusos and diametro:
        nome_d, d, Ab, _ = _diam(diametro)
        dh = diametro_furo(d, furo)[0]
        w = largura_desconto_furo(dh)
        r.add(cisalhamento_parafuso(nome_d, parafuso, planos=1, Fv_Sd=N_Sd,
                                    n=n_parafusos))
        r.add(esmagamento(nome_d, t_gusset, ag.fu, distancia_borda=borda,
                          espacamento=passo, furo=furo, Fc_Sd=N_Sd,
                          n_borda=1, n_interno=n_parafusos - 1, nome_chapa="gusset"))
        if t_barra:
            ab = mat.aco(aco_barra)
            r.add(esmagamento(nome_d, t_barra, ab.fu, distancia_borda=borda,
                              espacamento=passo, furo=furo, Fc_Sd=N_Sd,
                              n_borda=1, n_interno=n_parafusos - 1,
                              nome_chapa="barra / cantoneira"))
        Lv = borda + (n_parafusos - 1) * passo
        Agv = Lv * t_gusset
        Anv = (Lv - ((n_parafusos - 1) + 0.5) * w) * t_gusset
        Agt = gabarito_barra * t_gusset
        Ant = (gabarito_barra - w / 2.0) * t_gusset
        r.add(bloco_cisalhamento(Agv, Anv, Agt, Ant, ag.fy, ag.fu, Cts=1.0,
                                 Sd=N_Sd, nome="gusset"))
        r.dados["d_furo"] = dh
    if comprimento_solda:
        r.add(filete(perna_solda, comprimento_solda, eletrodo, ag.fy,
                     t_base=max(t_gusset, t_barra or t_gusset),
                     t_outra=t_barra or t_gusset,
                     F_Sd=N_Sd, n_cordoes=n_cordoes, nome="barra × gusset"))
    return r


def emenda_viga(viga, M_Sd: float, V_Sd: float, diametro: str = '3/4"',
                parafuso: str = "ASTM A325",
                t_tala_mesa: float = 0.95, largura_tala_mesa: Optional[float] = None,
                n_parafusos_mesa: int = 4, passo_mesa: float = 7.0,
                gabarito_mesa: float = 10.0, borda_mesa: float = 3.5,
                t_tala_alma: float = 0.95, altura_tala_alma: Optional[float] = None,
                n_parafusos_alma: int = 3, passo_alma: float = 7.6,
                colunas_alma: int = 2, gabarito_alma: float = 7.0,
                borda_alma: float = 3.5, excentricidade_alma: float = 3.5,
                aco_viga: str = "ASTM A36", aco_talas: str = "ASTM A36",
                rosca_no_plano: bool = True, furo: str = "padrão",
                elemento: str = "Emenda parafusada de viga") -> Resultado:
    """Emenda de viga com talas de mesa (momento) e talas duplas de alma (cortante).

    Modelo clássico: as talas de mesa transmitem o binário do momento,
    T = M/(d − t_f), e as talas de alma o cortante mais a parcela de momento da
    alma, tratada pelo método elástico com a excentricidade dos parafusos ao eixo
    da emenda. Cada parafuso de mesa tem 1 plano de corte (tala externa) e cada
    parafuso de alma, 2 planos (talas duplas).
    """
    g = _perfil_mm(viga)
    d_v, tf_v, tw_v, bf_v = g["d"] / 10.0, g["tf"] / 10.0, g["tw"] / 10.0, g["bf"] / 10.0
    av, at = mat.aco(aco_viga), mat.aco(aco_talas)
    nome_d, d_par, Ab, _ = _diam(diametro)
    dh = diametro_furo(d_par, furo)[0]
    wdesc = largura_desconto_furo(dh)
    b_tala = largura_tala_mesa or bf_v
    h_tala = altura_tala_alma or (d_v - 2 * tf_v - 4.0)

    braco = d_v - tf_v
    T_mesa = M_Sd / braco

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_talas)
    r.dados.update({"M_Sd": M_Sd, "V_Sd": V_Sd, "braco": braco, "T_mesa": T_mesa,
                    "t_tala_mesa": t_tala_mesa, "largura_tala_mesa": b_tala,
                    "t_tala_alma": t_tala_alma, "altura_tala_alma": h_tala,
                    "n_parafusos_mesa": n_parafusos_mesa,
                    "n_parafusos_alma": n_parafusos_alma * colunas_alma,
                    "diametro": nome_d, "d_furo": dh})

    # --- mesa ---
    v = cisalhamento_parafuso(nome_d, parafuso, planos=1, rosca_no_plano=rosca_no_plano,
                              Fv_Sd=T_mesa, n=n_parafusos_mesa)
    v.titulo = f"Parafusos da tala de mesa — {n_parafusos_mesa} × {nome_d}"
    v.passo("Tração/compressão na mesa",
            formula="T = M<sub>Sd</sub>/(d − t<sub>f</sub>)",
            conta=f"{fmt(M_Sd,0)}/{fmt(braco,2)}", valor=fmt(T_mesa, 1, "kN"))
    r.add(v)

    n_furos_larg = 2 if gabarito_mesa else 1
    An_tala = (b_tala - n_furos_larg * wdesc) * t_tala_mesa
    Ag_tala = b_tala * t_tala_mesa
    Rd_tala = min(Ag_tala * at.fy / GAMA_A1, An_tala * at.fu / GAMA_A2)
    v = Verificacao("Tala de mesa — tração", norma="NBR 8800:2008, item 5.2",
                    Sd=T_mesa, Rd=Rd_tala, unidade="kN")
    v.passo("Escoamento da seção bruta",
            formula="A<sub>g</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(Ag_tala,2)}·{fmt(at.fy,1)}/{fmt(GAMA_A1,2)}",
            valor=fmt(Ag_tala * at.fy / GAMA_A1, 0, "kN"))
    v.passo("Ruptura da seção líquida",
            formula="A<sub>n</sub>·f<sub>u</sub>/γ<sub>a2</sub>",
            conta=f"{fmt(An_tala,2)}·{fmt(at.fu,1)}/{fmt(GAMA_A2,2)}",
            valor=fmt(An_tala * at.fu / GAMA_A2, 0, "kN"))
    r.add(v)

    n_lado = max(1, n_parafusos_mesa // 2)
    n_fila = max(1, n_lado // n_furos_larg)
    r.add(esmagamento(nome_d, min(tf_v, t_tala_mesa),
                      min(av.fu, at.fu), distancia_borda=borda_mesa,
                      espacamento=passo_mesa, furo=furo, Fc_Sd=T_mesa,
                      n_borda=n_furos_larg, n_interno=n_lado - n_furos_larg,
                      nome_chapa="mesa / tala de mesa"))

    # --- alma ---
    pontos = coordenadas_grupo(n_parafusos_alma, colunas_alma, passo_alma, gabarito_alma)
    dist = esforcos_no_grupo(pontos, V_Sd=V_Sd, excentricidade=excentricidade_alma)
    F_max = dist["F_max"]
    v = cisalhamento_parafuso(nome_d, parafuso, planos=2, rosca_no_plano=rosca_no_plano,
                              Fv_Sd=F_max)
    v.titulo = (f"Parafusos da alma (corte duplo, {len(pontos)} × {nome_d}) — "
                "parafuso mais solicitado")
    v.passo("Momento de excentricidade da emenda",
            formula="M = V<sub>Sd</sub>·e",
            conta=f"{fmt(V_Sd,1)}·{fmt(excentricidade_alma,1)}",
            valor=fmt(dist["M_total"], 0, "kN·cm"))
    v.passo("Momento polar do grupo", formula="I<sub>p</sub> = Σ(x²+y²)",
            conta="", valor=fmt(dist["Ip"], 1, "cm²"))
    r.add(v)
    r.dados["F_max_alma"] = F_max
    r.dados["Ip_alma"] = dist["Ip"]

    Ag_a = h_tala * t_tala_alma * 2
    An_a = (h_tala - n_parafusos_alma * wdesc) * t_tala_alma * 2
    Rd_a = min(0.6 * at.fy * Ag_a / GAMA_A1, 0.6 * at.fu * An_a / GAMA_A2)
    v = Verificacao("Talas de alma — cisalhamento (2 chapas)",
                    norma="NBR 8800:2008, itens 5.4.3.5 e 6.5.5",
                    Sd=V_Sd, Rd=Rd_a, unidade="kN")
    v.passo("Escoamento da seção bruta",
            formula="0,6·f<sub>y</sub>·A<sub>g</sub>/γ<sub>a1</sub>",
            conta=f"0,6·{fmt(at.fy,1)}·{fmt(Ag_a,2)}/{fmt(GAMA_A1,2)}",
            valor=fmt(0.6 * at.fy * Ag_a / GAMA_A1, 0, "kN"))
    v.passo("Ruptura da seção líquida",
            formula="0,6·f<sub>u</sub>·A<sub>n</sub>/γ<sub>a2</sub>",
            conta=f"0,6·{fmt(at.fu,1)}·{fmt(An_a,2)}/{fmt(GAMA_A2,2)}",
            valor=fmt(0.6 * at.fu * An_a / GAMA_A2, 0, "kN"))
    r.add(v)

    r.add(esmagamento(nome_d, tw_v, av.fu, distancia_borda=borda_alma,
                      espacamento=passo_alma, furo=furo,
                      Fc_Sd=F_max * len(pontos), n_borda=colunas_alma,
                      n_interno=len(pontos) - colunas_alma,
                      nome_chapa="alma da viga"))

    Lv = borda_alma + (n_parafusos_alma - 1) * passo_alma
    Agv = Lv * t_tala_alma * 2
    Anv = (Lv - ((n_parafusos_alma - 1) + 0.5) * wdesc) * t_tala_alma * 2
    Agt = borda_alma * t_tala_alma * 2
    Ant = (borda_alma - wdesc / 2.0) * t_tala_alma * 2
    r.add(bloco_cisalhamento(Agv, Anv, Agt, Ant, at.fy, at.fu, Cts=1.0,
                             Sd=V_Sd, nome="talas de alma"))
    return r
