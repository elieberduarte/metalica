# -*- coding: utf-8 -*-
"""Bases de pilar: placa de base, chumbadores e chave de cisalhamento.

Normas de referência:
    NBR 8800:2008, item 6.3.3 — aço dos chumbadores (mesmas fórmulas de parafuso)
    NBR 8800:2008, item 5.4.2 — plastificação da faixa de 1 cm da placa
    NBR 6118:2014, item 21.2  — pressão de contato em área reduzida
    ACI 318, cap. 17          — cone de arrancamento do concreto (a NBR 8800 e a
                                NBR 6118 não trazem o modelo de cone; é declarado
                                explicitamente em cada verificação)

Unidades internas: força kN · momento kN·cm · tensão kN/cm² · comprimento cm.
As dimensões do catálogo de perfis chegam em mm e são convertidas aqui.
"""
import math
from typing import Dict, Optional, Tuple

from .base import (GAMA_A1, GAMA_A2, GAMA_C, GAMA_W2, ErroDeDados, Resultado,
                   Verificacao, fmt)
from . import materiais as mat
from . import ligacoes as lig
from .perfis import Perfil

# Chapas grossas comerciais para placa de base (Tabela 10.4 do manual), em cm.
CHAPAS_COMERCIAIS = [1.27, 1.60, 1.90, 2.24, 2.54, 3.15, 3.80, 4.45, 5.08]
ESPESSURA_MINIMA_GALPAO = 1.27      # 1/2" — mínimo prático (item 10.5.3)
ESPESSURA_MINIMA_ENGASTADA = 1.60   # 5/8" — mínimo em base engastada

# Furos da placa de base e arruelas de chapa (Tabela 10.2 — prática AISC DG 1).
# nome do diâmetro -> (furo mm, lado da arruela mm, espessura da arruela mm)
FUROS_PLACA_BASE: Dict[str, Tuple[float, float, float]] = {
    '5/8"': (29.0, 50.0, 8.0),
    '3/4"': (33.0, 50.0, 8.0),
    '7/8"': (40.0, 65.0, 10.0),
    '1"': (46.0, 75.0, 12.5),
    '1.1/4"': (52.0, 75.0, 12.5),
    '1.1/2"': (59.0, 90.0, 16.0),
}

# Coeficiente de atrito placa–grout (item 10.10.1 do manual; valores indicativos).
ATRITO_BASE = {"grout / concreto lançado depois": 0.40,
               "concreto rugoso apicoado": 0.50}

# Fator de minoração do ACI 318 para arrancamento do cone (φ = 0,70, condição B).
PHI_CONE = 0.70


def _perfil(p) -> dict:
    """Normaliza `Perfil`, nome ou dict para dimensões em mm."""
    if isinstance(p, Perfil):
        return {"nome": p.nome, "d": p.d, "bf": p.bf, "tw": p.tw, "tf": p.tf, "A": p.A}
    if isinstance(p, str):
        from .perfis import perfil as _pf
        return _perfil(_pf(p))
    if isinstance(p, dict):
        faltando = [k for k in ("d", "bf") if k not in p]
        if faltando:
            raise ErroDeDados("perfil do pilar sem as dimensões "
                              f"{', '.join(faltando)} (em mm)")
        q = dict(p)
        q.setdefault("tf", 0.0)
        q.setdefault("tw", 0.0)
        return q
    raise ErroDeDados(f"perfil do pilar não reconhecido: {p!r}")


def fck_kN_cm2(valor) -> float:
    """Normaliza o f_ck para kN/cm², aceitando número, "C25" ou `materiais.Concreto`.

    ATENÇÃO — 1 kN/cm² = 10 MPa, logo C25 → f_ck = 2,5 kN/cm². O dicionário
    `materiais.CONCRETOS` foi montado com f_ck = 0,25 para o C25 (dez vezes menor):
    `Concreto.fck_MPa` devolve 2,5 MPa em vez de 25 MPa. Esta função corrige a
    escala quando recebe um `Concreto` ou um número claramente fora de faixa, em
    vez de propagar silenciosamente um erro de uma ordem de grandeza.
    """
    if isinstance(valor, mat.Concreto):
        valor = valor.fck
    elif isinstance(valor, str):
        nome = valor.strip().upper().lstrip("C")
        try:
            return float(nome) / 10.0          # "C25" → 25 MPa → 2,5 kN/cm²
        except ValueError:
            raise ErroDeDados(f"concreto desconhecido: {valor}. Use 'C25' ou o "
                              "f_ck em kN/cm² (C25 → 2,5).")
    v = float(valor)
    if v <= 0:
        raise ErroDeDados("f_ck tem de ser positivo, em kN/cm² (C25 → 2,5)")
    if v < 1.0:
        # 0,20 a 0,50 é a escala (errada, dez vezes menor) de materiais.CONCRETOS
        if 0.15 <= v <= 0.60:
            return v * 10.0
        raise ErroDeDados(f"f_ck = {v} kN/cm² é baixo demais para concreto "
                          "estrutural; o mínimo usual é C20 → 2,0 kN/cm².")
    if v > 10.0:
        raise ErroDeDados(f"f_ck = {v} parece estar em MPa; use kN/cm² "
                          "(C25 → 2,5 kN/cm²).")
    return v


def chapa_comercial(t_necessaria: float, minimo: float = ESPESSURA_MINIMA_GALPAO,
                    utilizacao_maxima: float = 1.0) -> float:
    """Menor chapa comercial ≥ t_necessária (e ≥ `minimo`), em cm.

    `utilizacao_maxima` < 1 exige folga adicional: a chapa escolhida terá
    t_necessária/t ≤ utilizacao_maxima (a utilização em momento é o quadrado
    dessa razão), útil para absorver tolerâncias de execução.
    """
    alvo = max(t_necessaria / max(utilizacao_maxima, 1e-6) ** 0.5, minimo) \
        if utilizacao_maxima < 1.0 else max(t_necessaria, minimo)
    for t in CHAPAS_COMERCIAIS:
        if t >= alvo - 1e-9:
            return t
    raise ErroDeDados(f"espessura necessária {alvo*10:.1f} mm acima da maior chapa "
                      f"comercial do catálogo ({CHAPAS_COMERCIAIS[-1]*10:.1f} mm): "
                      "aumente a placa, use enrijecedores ou aço de maior f_y.")


# ---------------------------------------------------------------------------
# 1. Pressão de contato no concreto
# ---------------------------------------------------------------------------

def fator_confinamento(A1: float, A2: float) -> float:
    """√(A₂/A₁) limitado a 2,0 (NBR 6118, item 21.2 / AISC 360, item J8)."""
    if A1 <= 0:
        raise ErroDeDados("a área da placa A₁ tem de ser positiva")
    if A2 < A1:
        raise ErroDeDados(f"A₂ = {A2:.0f} cm² menor que A₁ = {A1:.0f} cm²: A₂ é a "
                          "maior área homotética e concêntrica com a placa que cabe "
                          "no topo do pedestal e nunca é menor que a própria placa.")
    return min(math.sqrt(A2 / A1), 2.0)


def area_A2(B: float, L: float, B_pedestal: float, L_pedestal: float) -> Tuple[float, float]:
    """Área A₂ homotética e concêntrica com a placa dentro do pedestal.

    A₂ não é a área cheia do pedestal: é a maior área com a mesma proporção B:L da
    placa que cabe no topo do pedestal (item 10.4.2 do manual). Devolve (A₂, k),
    com k = √(A₂/A₁) antes do limite de 2,0.
    """
    if B <= 0 or L <= 0:
        raise ErroDeDados("as dimensões da placa têm de ser positivas")
    if B_pedestal < B or L_pedestal < L:
        raise ErroDeDados(f"a placa {B:.0f}×{L:.0f} cm não cabe no pedestal "
                          f"{B_pedestal:.0f}×{L_pedestal:.0f} cm")
    k = min(B_pedestal / B, L_pedestal / L)
    return k * B * k * L, k


def pressao_concreto(fck: float, A1: float, A2: float,
                     N_Sd: float = 0.0) -> Verificacao:
    """Pressão de contato resistente do concreto sob a placa de base.

        σ_c,Rd = 0,85·f_ck·√(A₂/A₁)/γ_c  ≤  1,70·f_cd

    A₁ = área da placa em contato com o concreto (ou com o grout).
    A₂ = maior área do topo do pedestal geometricamente semelhante (homotética) e
         concêntrica com A₁; exige altura de pedestal suficiente para o
         espalhamento 1:2 dentro do concreto.

    Escrita "do aço" (AISC 360, item J8, com os coeficientes brasileiros), adotada
    no manual. A NBR 6118, item 21.2, escreve σ_c,Rd = f_cd·√(A₂/A₁) ≤ 3,3·f_cd,
    que é até 1,65 vez mais permissiva e se aplica a apoios localizados armados,
    não a placa de base de pilar.
    """
    fck = fck_kN_cm2(fck)
    fcd = fck / GAMA_C
    k = fator_confinamento(A1, A2)
    sigma = min(0.85 * fck * k / GAMA_C, 1.70 * fcd)
    sigma_Sd = N_Sd / A1 if A1 else 0.0

    v = Verificacao("Pressão de contato no concreto",
                    norma="NBR 6118:2014, item 21.2 / AISC 360, item J8",
                    Sd=sigma_Sd, Rd=sigma, unidade="kN/cm²")
    v.passo("Resistência de cálculo do concreto",
            formula="f<sub>cd</sub> = f<sub>ck</sub>/γ<sub>c</sub>",
            conta=f"{fmt(fck,3)}/{fmt(GAMA_C,2)}", valor=fmt(fcd, 3, "kN/cm²"))
    v.passo("Fator de confinamento",
            formula="√(A₂/A₁) ≤ 2,0",
            conta=f"√({fmt(A2,0)}/{fmt(A1,0)})", valor=fmt(k, 3))
    v.passo("Pressão resistente",
            formula="σ<sub>c,Rd</sub> = 0,85·f<sub>ck</sub>·√(A₂/A₁)/γ<sub>c</sub> ≤ 1,70·f<sub>cd</sub>",
            conta=f"0,85·{fmt(fck,3)}·{fmt(k,3)}/{fmt(GAMA_C,2)} "
                  f"(limite {fmt(1.70*fcd,3)})",
            valor=fmt(sigma, 3, "kN/cm²") + f" = {fmt(sigma*10, 1)} MPa")
    if N_Sd:
        v.passo("Pressão solicitante",
                formula="σ<sub>Sd</sub> = N<sub>Sd</sub>/A₁",
                conta=f"{fmt(N_Sd,0)}/{fmt(A1,0)}",
                valor=fmt(sigma_Sd, 3, "kN/cm²") + f" = {fmt(sigma_Sd*10, 2)} MPa")
    if k >= 2.0 - 1e-9:
        v.observacao = ("Confinamento no limite (√(A₂/A₁) = 2,0). Confira se o "
                        "pedestal tem altura para o espalhamento 1:2 da carga.")
    return v


# ---------------------------------------------------------------------------
# 2. Placa de base centrada (base rotulada / carga axial)
# ---------------------------------------------------------------------------

def vaos_balanco(d: float, bf: float, B: float, L: float, N_Sd: float,
                 sigma_c_Rd: float) -> dict:
    """Vãos dos balanços da placa (item 10.5 do manual, modelo AISC).

        m = (L − 0,95·d)/2      n = (B − 0,80·b_f)/2
        n′ = √(d·b_f)/4         λ = 2·√X/(1 + √(1−X)) ≤ 1,0
        X = [4·d·b_f/(d+b_f)²]·N_Sd/(σ_c,Rd·B·L)
        ℓ = máx(m ; n ; λ·n′)

    Dimensões em cm. `L` é a dimensão paralela à altura d do perfil.
    """
    m = (L - 0.95 * d) / 2.0
    n = (B - 0.80 * bf) / 2.0
    n_linha = math.sqrt(d * bf) / 4.0
    X = (4.0 * d * bf / (d + bf) ** 2) * N_Sd / (sigma_c_Rd * B * L) if sigma_c_Rd else 1.0
    X = min(X, 1.0)
    lam = 2.0 * math.sqrt(X) / (1.0 + math.sqrt(max(0.0, 1.0 - X))) if X > 0 else 0.0
    lam = min(lam, 1.0)
    ell = max(m, n, lam * n_linha)
    return {"m": m, "n": n, "n_linha": n_linha, "X": X, "lambda": lam,
            "l_balanco": lam * n_linha, "ell": ell}


def espessura_placa(ell: float, sigma: float, fy: float) -> float:
    """Espessura necessária da placa pelo modelo dos balanços (eq. 10.5).

        t ≥ ℓ·√(2·σ·γ_a1/f_y)

    σ é a pressão real de cálculo sob a placa (N_Sd/A₁, ou σ_máx quando há
    momento), não σ_c,Rd.
    """
    if sigma < 0:
        raise ErroDeDados("a pressão σ não pode ser negativa")
    return ell * math.sqrt(2.0 * sigma * GAMA_A1 / fy)


def espessura_por_momento(M_Sd_por_cm: float, fy: float) -> float:
    """Espessura da faixa de 1 cm a partir do momento: t ≥ √(4·M·γ_a1/f_y)."""
    return math.sqrt(4.0 * M_Sd_por_cm * GAMA_A1 / fy)


def placa_base_centrada(pilar, N_Sd: float, fck: float = 2.5,
                        pedestal: Tuple[float, float] = (60.0, 60.0),
                        aco_placa: str = "ASTM A36",
                        B: Optional[float] = None, L: Optional[float] = None,
                        folga_borda: float = 2.5,
                        diametro_chumbador: str = '3/4"',
                        borda_chumbador: float = 5.0,
                        engastada: bool = False,
                        elemento: str = "Placa de base (carga centrada)") -> Resultado:
    """Dimensiona a placa de base de um pilar sob compressão centrada.

    Roteiro do item 10.4.3 do manual:
      1. área necessária com o confinamento máximo, A₁,nec = N_Sd/(1,70·f_cd);
      2. mínimo geométrico (d + 2c) × (b_f + 2c) e espaço para os chumbadores
         fora das mesas, na linha do eixo de flexão;
      3. balanços equilibrados — para perfis com d ≈ b_f a placa quadrada já
         resolve; para perfis altos e estreitos, L = B + (0,95·d − 0,80·b_f);
      4. arredondamento para múltiplos de 10 mm e A₂ homotética real do pedestal;
      5. σ_Sd ≤ σ_c,Rd;
      6. espessura pelo modelo dos balanços, com chapa comercial.

    `B` e `L` podem ser impostos (em cm) para verificar uma placa já escolhida.
    """
    g = _perfil(pilar)
    d, bf = g["d"] / 10.0, g["bf"] / 10.0
    aco = mat.aco(aco_placa)
    fck = fck_kN_cm2(fck)
    fcd = fck / GAMA_C
    Bp, Lp = pedestal
    nome_ch, d_ch, Ab_ch, _ = lig._diam(diametro_chumbador)

    A1_nec = N_Sd / (1.70 * fcd)
    # espaço para os chumbadores: linha a um múltiplo de 5 cm fora da mesa
    x_ch = math.ceil((bf / 2.0 + 2.0) / 5.0) * 5.0
    B_anc = 2.0 * (x_ch + borda_chumbador)
    B_geom = bf + 2 * folga_borda
    L_geom = d + 2 * folga_borda
    delta = (0.95 * d - 0.80 * bf) / 2.0

    automatica = B is None and L is None
    if automatica:
        B0 = max(B_geom, B_anc, math.sqrt(A1_nec))
        if abs(delta) <= 0.10 * B0:
            # perfil "quadrado": placa quadrada já dá balanços quase iguais
            B = L = math.ceil(max(B0, L_geom, math.sqrt(A1_nec)))
        else:
            # perfil alto e estreito: L = B + 2Δ minimiza a espessura
            B = max(B0, -delta + math.sqrt(delta ** 2 + A1_nec))
            L = max(L_geom, B + 2 * delta)
            B, L = math.ceil(B), math.ceil(L)
    elif B is None or L is None:
        raise ErroDeDados("informe as duas dimensões da placa (B e L) ou nenhuma")

    A1 = B * L
    A2, k_bruto = area_A2(B, L, Bp, Lp)
    sigma_Sd = N_Sd / A1

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_placa)
    v_press = pressao_concreto(fck, A1, A2, N_Sd)
    sigma_c_Rd = v_press.Rd
    r.add(v_press)

    bal = vaos_balanco(d, bf, B, L, N_Sd, sigma_c_Rd)
    t_nec = espessura_placa(bal["ell"], sigma_Sd, aco.fy)
    t_min = ESPESSURA_MINIMA_ENGASTADA if engastada else ESPESSURA_MINIMA_GALPAO
    t = chapa_comercial(t_nec, minimo=t_min)

    M_Sd = sigma_Sd * bal["ell"] ** 2 / 2.0
    M_Rd = (t ** 2 / 4.0) * aco.fy / GAMA_A1
    v = Verificacao("Flexão da placa — faixa de 1 cm em balanço",
                    norma="NBR 8800:2008, item 5.4.2 (plastificação da chapa)",
                    Sd=M_Sd, Rd=M_Rd, unidade="kN·cm/cm")
    v.passo("Vãos dos balanços",
            formula="m = (L − 0,95·d)/2 ; n = (B − 0,80·b<sub>f</sub>)/2",
            conta=f"m = ({fmt(L,1)} − 0,95·{fmt(d,2)})/2 ; "
                  f"n = ({fmt(B,1)} − 0,80·{fmt(bf,2)})/2",
            valor=f"m = {fmt(bal['m'],2)} cm ; n = {fmt(bal['n'],2)} cm")
    v.passo("Vão interno",
            formula="n′ = √(d·b<sub>f</sub>)/4 ; λ = 2√X/(1+√(1−X))",
            conta=f"n′ = {fmt(bal['n_linha'],2)} ; X = {fmt(bal['X'],4)} ; "
                  f"λ = {fmt(bal['lambda'],3)}",
            valor=f"λ·n′ = {fmt(bal['l_balanco'],2)} cm")
    v.passo("Vão de cálculo",
            formula="ℓ = máx(m ; n ; λ·n′)",
            conta=f"máx({fmt(bal['m'],2)} ; {fmt(bal['n'],2)} ; {fmt(bal['l_balanco'],2)})",
            valor=fmt(bal["ell"], 2, "cm"))
    v.passo("Momento na faixa de 1 cm",
            formula="M<sub>Sd</sub> = σ·ℓ²/2",
            conta=f"{fmt(sigma_Sd,4)}·{fmt(bal['ell'],2)}²/2",
            valor=fmt(M_Sd, 2, "kN·cm/cm"))
    v.passo("Espessura necessária",
            formula="t ≥ ℓ·√(2·σ·γ<sub>a1</sub>/f<sub>y</sub>)",
            conta=f"{fmt(bal['ell'],2)}·√(2·{fmt(sigma_Sd,4)}·{fmt(GAMA_A1,2)}/"
                  f"{fmt(aco.fy,1)})",
            valor=fmt(t_nec, 3, "cm") + f" = {fmt(t_nec*10, 1)} mm")
    v.passo("Chapa comercial adotada",
            formula="t", conta=f"mínimo prático {fmt(t_min*10,1)} mm",
            valor=fmt(t * 10, 1, "mm"), norma="Tabela 10.4 do manual")
    if t < d_ch - 0.05:
        v.observacao = (f"t = {t*10:.1f} mm menor que o diâmetro do chumbador "
                        f"({d_ch*10:.1f} mm): verificação rápida do item 10.5.3 do "
                        "manual não atendida — reveja a espessura ou o diâmetro.")
    v.passo("Momento resistente da faixa",
            formula="M<sub>Rd</sub> = (t²/4)·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"({fmt(t,2)}²/4)·{fmt(aco.fy,1)}/{fmt(GAMA_A1,2)}",
            valor=fmt(M_Rd, 2, "kN·cm/cm"))
    r.add(v)

    peso = A1 * t * 7.85e-3       # kg (ρ = 7 850 kg/m³)
    r.dados.update({
        "B": B, "L": L, "t": t, "t_mm": t * 10, "t_necessaria_mm": t_nec * 10,
        "A1": A1, "A2": A2, "k": min(k_bruto, 2.0), "sigma_Sd": sigma_Sd,
        "sigma_c_Rd": sigma_c_Rd, "A1_necessaria": A1_nec,
        "pedestal": (Bp, Lp), "fck": fck, "aco_placa": aco_placa,
        "peso_kg": peso, "dimensionamento_automatico": automatica,
        "x_chumbador": x_ch, "borda_chumbador": borda_chumbador,
        "diametro_chumbador": nome_ch,
        "furo_placa_mm": FUROS_PLACA_BASE.get(nome_ch, (None, None, None))[0],
        "arruela_chapa_mm": FUROS_PLACA_BASE.get(nome_ch, (None, None, None))[1:],
        "pilar": g.get("nome", ""),
    })
    r.dados.update(bal)
    return r


# ---------------------------------------------------------------------------
# 3. Placa de base com momento
# ---------------------------------------------------------------------------

def placa_base_com_momento(pilar, N_Sd: float, M_Sd: float, B: float, L: float,
                           f_chumbador: float, fck: float = 2.5,
                           pedestal: Tuple[float, float] = (60.0, 60.0),
                           aco_placa: str = "ASTM A36",
                           n_chumbadores_tracionados: int = 2,
                           engastada: bool = True,
                           elemento: str = "Placa de base com momento") -> Resultado:
    """Placa de base sob N e M: os três regimes de excentricidade (item 10.7).

        e = M_Sd/N_Sd  comparado com o núcleo central L/6

        e ≤ L/6   : toda a placa comprimida, diagrama trapezoidal
                    σ = N/(B·L) ± 6M/(B·L²) ;  T = 0
        e = L/6   : triangular, σ_máx = 2N/(B·L)
        L/6 < e < L/2 : triangular sobre Y = 3·(L/2 − e), T = 0
        e ≥ L/2   : tração nos chumbadores; T pelo método do binário (eq. 10.8),
                    conferido pelo modelo triangular (eq. 10.6)

    `f_chumbador` é a distância do eixo do pilar à linha dos chumbadores
    tracionados (cm). `L` é a dimensão da placa na direção do momento.

    A espessura sai do maior momento entre o balanço comprimido (pressão
    triangular exata sobre o balanço) e o balanço tracionado (força do chumbador).
    """
    g = _perfil(pilar)
    d, bf, tf = g["d"] / 10.0, g["bf"] / 10.0, g["tf"] / 10.0
    aco = mat.aco(aco_placa)
    fck = fck_kN_cm2(fck)
    Bp, Lp = pedestal
    A1 = B * L
    A2, k_bruto = area_A2(B, L, Bp, Lp)

    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_placa)
    v_press = pressao_concreto(fck, A1, A2)
    sigma_c_Rd = v_press.Rd

    if N_Sd <= 0:
        raise ErroDeDados("N_Sd tem de ser uma compressão positiva; para tração pura "
                          "na base use `chumbadores` diretamente")
    e = M_Sd / N_Sd
    nucleo = L / 6.0
    dados = {"e": e, "nucleo_central": nucleo, "B": B, "L": L, "A1": A1, "A2": A2,
             "sigma_c_Rd": sigma_c_Rd, "f_chumbador": f_chumbador, "fck": fck,
             "pedestal": (Bp, Lp), "N_Sd": N_Sd, "M_Sd": M_Sd,
             "pilar": g.get("nome", "")}

    T = 0.0
    C = N_Sd
    if e <= nucleo:
        regime = "e ≤ L/6 — trapezoidal, toda a placa comprimida"
        sig_max = N_Sd / A1 + 6 * M_Sd / (B * L * L)
        sig_min = N_Sd / A1 - 6 * M_Sd / (B * L * L)
        Y = L
    elif e < L / 2.0:
        regime = "L/6 < e < L/2 — triangular parcial, sem tração nos chumbadores"
        Y = 3.0 * (L / 2.0 - e)
        sig_max = 2.0 * N_Sd / (B * Y)
        sig_min = 0.0
    else:
        regime = "e ≥ L/2 — tração nos chumbadores"
        sig_min = 0.0
        # método do binário (eq. 10.8) — do lado seguro, dimensiona o chumbador
        x_C = L / 2.0 - d / 2.0 + tf / 2.0        # centro da mesa comprimida
        d_linha = (L / 2.0 + f_chumbador) - x_C
        C = (M_Sd + N_Sd * f_chumbador) / d_linha
        T = C - N_Sd
        Y_eq = 2.0 * C / (sigma_c_Rd * B)         # comprimento comprimido equivalente
        sig_max = sigma_c_Rd
        # O diagrama de pressões (e, com ele, a flexão do balanço comprimido) vem do
        # modelo triangular com o concreto no limite; o binário concentra C sob a
        # mesa e, por construção, não deixa balanço comprimido — misturar os dois
        # daria uma espessura fictícia.
        tri = modelo_triangular(N_Sd, M_Sd, B, L, f_chumbador, sigma_c_Rd)
        dados["modelo_triangular"] = tri
        Y = tri["Y"] if tri["Y"] else Y_eq
        dados.update({"x_C": x_C, "d_linha": d_linha, "Y_equivalente": Y_eq})

    dados.update({"regime": regime, "Y": Y, "sigma_max": sig_max,
                  "sigma_min": sig_min, "T": T, "C": C})

    v_press.Sd = sig_max
    v_press.passo("Excentricidade",
                  formula="e = M<sub>Sd</sub>/N<sub>Sd</sub> ; núcleo central = L/6",
                  conta=f"{fmt(M_Sd,0)}/{fmt(N_Sd,1)} = {fmt(e,2)} cm ; "
                        f"L/6 = {fmt(nucleo,2)} cm",
                  valor=regime)
    if e < L / 2.0:
        v_press.passo("Comprimento comprimido e pressão máxima",
                      formula=("Y = L ; σ = N/(B·L) ± 6M/(B·L²)" if e <= nucleo
                               else "Y = 3·(L/2 − e) ; σ<sub>máx</sub> = 2·N/(B·Y)"),
                      conta=(f"Y = {fmt(Y,2)} cm"),
                      valor=fmt(sig_max, 4, "kN/cm²") + f" = {fmt(sig_max*10,2)} MPa")
    r.add(v_press)

    # --- tração nos chumbadores ---
    if T > 0:
        v = Verificacao("Tração no grupo de chumbadores (método do binário)",
                        norma="AISC Design Guide 1, eq. do binário (item 10.7.3 do "
                              "manual); a NBR 8800 não prescreve o modelo",
                        Sd=T, Rd=T, unidade="kN", dispensada=True)
        v.passo("Centro da mesa comprimida (da borda comprimida)",
                formula="x<sub>C</sub> = L/2 − d/2 + t<sub>f</sub>/2",
                conta=f"{fmt(L/2,2)} − {fmt(d/2,2)} + {fmt(tf/2,2)}",
                valor=fmt(dados["x_C"], 2, "cm"))
        v.passo("Braço do binário",
                formula="d′ = (L/2 + f) − x<sub>C</sub>",
                conta=f"({fmt(L/2,2)} + {fmt(f_chumbador,2)}) − {fmt(dados['x_C'],2)}",
                valor=fmt(dados["d_linha"], 2, "cm"))
        v.passo("Compressão resultante",
                formula="C = (M<sub>Sd</sub> + N<sub>Sd</sub>·f)/d′",
                conta=f"({fmt(M_Sd,0)} + {fmt(N_Sd,1)}·{fmt(f_chumbador,2)})/"
                      f"{fmt(dados['d_linha'],2)}",
                valor=fmt(C, 1, "kN"))
        v.passo("Tração no grupo tracionado",
                formula="T = C − N<sub>Sd</sub>",
                conta=f"{fmt(C,1)} − {fmt(N_Sd,1)}", valor=fmt(T, 1, "kN"))
        v.passo(f"Por chumbador ({n_chumbadores_tracionados})",
                formula="T/n", conta=f"{fmt(T,1)}/{n_chumbadores_tracionados}",
                valor=fmt(T / n_chumbadores_tracionados, 1, "kN"))
        r.add(v)
        dados["T_por_chumbador"] = T / n_chumbadores_tracionados

        # conferência pelo modelo triangular (eq. 10.6)
        v = Verificacao("Conferência pelo modelo triangular (concreto no limite)",
                        norma="AISC Design Guide 1, eq. 10.6 do manual",
                        Sd=tri.get("Y", 0.0), Rd=L, unidade="cm")
        if tri.get("Y") is None:
            v.observacao = ("A equação do 2.º grau em Y não tem raiz real: a placa é "
                            "pequena demais para o concreto trabalhar no limite. "
                            "Aumente B, L ou f_ck.")
            v.Sd = L * 2
        else:
            v.passo("Força de compressão por unidade de comprimento",
                    formula="q = σ<sub>c,Rd</sub>·B",
                    conta=f"{fmt(sigma_c_Rd,4)}·{fmt(B,1)}",
                    valor=fmt(tri["q"], 2, "kN/cm"))
            v.passo("Equação do comprimento comprimido",
                    formula="Y² − 3·(L/2 + f)·Y + 6·(M + N·f)/q = 0",
                    conta=f"Y² − {fmt(3*(L/2+f_chumbador),1)}·Y + "
                          f"{fmt(6*(M_Sd+N_Sd*f_chumbador)/tri['q'],1)} = 0",
                    valor=fmt(tri["Y"], 2, "cm"))
            v.passo("Compressão e tração",
                    formula="C = q·Y/2 ; T = C − N",
                    conta=f"{fmt(tri['q'],2)}·{fmt(tri['Y'],2)}/2",
                    valor=f"C = {fmt(tri['C'],1)} kN ; T = {fmt(tri['T'],1)} kN")
            v.observacao = ("O método do binário dá "
                            f"{100*(T/max(tri['T'],1e-9) - 1):.0f} % mais tração "
                            "porque não admite o concreto no limite. Dimensione o "
                            "chumbador pelo binário e verifique o concreto pelo "
                            "triangular.")
        r.add(v)

    # --- espessura: balanço comprimido ---
    m = (L - 0.95 * d) / 2.0
    n = (B - 0.80 * bf) / 2.0
    if Y >= L - 1e-9:
        # pressão trapezoidal: usa a pressão média sobre o balanço, exata
        sig_borda = sig_max
        sig_critica = sig_max - (sig_max - sig_min) * m / L
        M_comp = sig_critica * m ** 2 / 2.0 + (sig_borda - sig_critica) * m ** 2 / 3.0
    elif m <= Y:
        # pressão triangular sobre o balanço inteiro (exato, eq. do item 10.7.4)
        M_comp = sig_max * (m ** 2 / 2.0 - m ** 3 / (6.0 * Y))
    else:
        # a compressão não alcança a seção crítica: resultante parcial
        M_comp = sig_max * Y / 2.0 * (m - Y / 3.0)
    M_n = sig_max * n ** 2 / 2.0
    M_comp = max(M_comp, M_n)

    t_comp = espessura_por_momento(M_comp, aco.fy)
    v = Verificacao("Flexão da placa — balanço comprimido",
                    norma="NBR 8800:2008, item 5.4.2 (plastificação da chapa)",
                    Sd=M_comp, Rd=0.0, unidade="kN·cm/cm")
    v.passo("Vãos dos balanços",
            formula="m = (L − 0,95·d)/2 ; n = (B − 0,80·b<sub>f</sub>)/2",
            conta=f"({fmt(L,1)} − 0,95·{fmt(d,2)})/2 ; ({fmt(B,1)} − 0,80·{fmt(bf,2)})/2",
            valor=f"m = {fmt(m,2)} cm ; n = {fmt(n,2)} cm")
    if Y < L and m <= Y:
        v.passo("Momento com a pressão triangular exata sobre o balanço",
                formula="M<sub>Sd</sub> = σ<sub>máx</sub>·[m²/2 − m³/(6·Y)]",
                conta=f"{fmt(sig_max,4)}·({fmt(m**2/2,2)} − {fmt(m**3/(6*Y),2)})",
                valor=fmt(M_comp, 2, "kN·cm/cm"))
    else:
        v.passo("Momento na seção crítica",
                formula="M<sub>Sd</sub> = ∫σ(x)·x dx",
                conta="", valor=fmt(M_comp, 2, "kN·cm/cm"))
    v.passo("Espessura necessária",
            formula="t ≥ √(4·M<sub>Sd</sub>·γ<sub>a1</sub>/f<sub>y</sub>)",
            conta=f"√(4·{fmt(M_comp,2)}·{fmt(GAMA_A1,2)}/{fmt(aco.fy,1)})",
            valor=fmt(t_comp, 3, "cm") + f" = {fmt(t_comp*10, 1)} mm")

    # --- espessura: balanço tracionado ---
    t_trac = 0.0
    M_trac = 0.0
    if T > 0:
        x_critico = L / 2.0 + 0.95 * d / 2.0          # da borda comprimida
        braco_t = (L / 2.0 + f_chumbador) - x_critico
        if braco_t > 0:
            M_trac = T * braco_t / B
            t_trac = espessura_por_momento(M_trac, aco.fy)
        dados.update({"braco_tracionado": braco_t, "M_tracionado": M_trac})

    t_nec = max(t_comp, t_trac)
    t_min = ESPESSURA_MINIMA_ENGASTADA if engastada else ESPESSURA_MINIMA_GALPAO
    t = chapa_comercial(t_nec, minimo=t_min)
    v.Rd = (t ** 2 / 4.0) * aco.fy / GAMA_A1
    v.passo("Chapa comercial adotada", formula="t", conta="",
            valor=fmt(t * 10, 1, "mm"), norma="Tabela 10.4 do manual")
    r.add(v)

    if T > 0:
        vt = Verificacao("Flexão da placa — balanço tracionado",
                         norma="NBR 8800:2008, item 5.4.2",
                         Sd=M_trac, Rd=(t ** 2 / 4.0) * aco.fy / GAMA_A1,
                         unidade="kN·cm/cm")
        vt.passo("Seção crítica do lado tracionado (da borda comprimida)",
                 formula="x = L/2 + 0,95·d/2",
                 conta=f"{fmt(L/2,2)} + 0,95·{fmt(d,2)}/2",
                 valor=fmt(L / 2.0 + 0.95 * d / 2.0, 2, "cm"))
        vt.passo("Braço da força do chumbador",
                 formula="(L/2 + f) − x",
                 conta=f"{fmt(L/2+f_chumbador,2)} − {fmt(L/2+0.95*d/2,2)}",
                 valor=fmt(dados["braco_tracionado"], 2, "cm"))
        vt.passo("Momento distribuído na largura da placa",
                 formula="M<sub>Sd</sub> = T·braço/B",
                 conta=f"{fmt(T,1)}·{fmt(dados['braco_tracionado'],2)}/{fmt(B,1)}",
                 valor=fmt(M_trac, 2, "kN·cm/cm"))
        vt.passo("Espessura necessária",
                 formula="t ≥ √(4·M·γ<sub>a1</sub>/f<sub>y</sub>)",
                 conta="", valor=fmt(t_trac, 3, "cm") + f" = {fmt(t_trac*10,1)} mm")
        vt.observacao = ("Governa o lado comprimido." if t_comp >= t_trac
                         else "Governa o lado tracionado: afastar os chumbadores "
                              "reduz T mas engrossa a placa — é um compromisso.")
        r.add(vt)

    dados.update({"m": m, "n": n, "t": t, "t_mm": t * 10,
                  "t_necessaria_mm": t_nec * 10, "t_comprimido_mm": t_comp * 10,
                  "t_tracionado_mm": t_trac * 10,
                  "peso_kg": A1 * t * 7.85e-3, "aco_placa": aco_placa,
                  "n_chumbadores_tracionados": n_chumbadores_tracionados})
    r.dados.update(dados)
    return r


def modelo_triangular(N_Sd: float, M_Sd: float, B: float, L: float,
                      f_chumbador: float, sigma_c_Rd: float) -> dict:
    """Distribuição triangular com o concreto no limite (eq. 10.6 do manual).

        Y² − 3·(L/2 + f)·Y + 6·(M + N·f)/q = 0,   q = σ_c,Rd·B
        C = q·Y/2 ;  T = C − N

    Devolve dict com q, Y (menor raiz positiva ou None), C e T.
    """
    q = sigma_c_Rd * B
    b = 3.0 * (L / 2.0 + f_chumbador)
    c = 6.0 * (M_Sd + N_Sd * f_chumbador) / q
    disc = b * b - 4.0 * c
    if disc < 0:
        return {"q": q, "Y": None, "C": None, "T": None}
    Y = (b - math.sqrt(disc)) / 2.0
    C = q * Y / 2.0
    return {"q": q, "Y": Y, "C": C, "T": C - N_Sd}


# ---------------------------------------------------------------------------
# 4. Chumbadores
# ---------------------------------------------------------------------------

def cone_arrancamento(fck: float, h_ef: float, n_tracionados: int = 1,
                      espacamento: float = 0.0, borda: Optional[float] = None,
                      borda_oposta: Optional[float] = None,
                      borda_lateral: Optional[float] = None,
                      borda_lateral_oposta: Optional[float] = None) -> dict:
    """Arrancamento do cone de concreto (ACI 318, cap. 17) — grupo de chumbadores.

        N_b = 10·√f_ck·h_ef^1,5            (N; f_ck em MPa; h_ef em mm)
        A_Nco = 9·h_ef²
        N_cbg = (A_Nc/A_Nco)·ψ_ed·N_b ,  ψ_ed = 0,7 + 0,3·c_min/(1,5·h_ef) ≤ 1,0

    O cone abre a ≈ 35° com a vertical (1,5·h_ef de projeção horizontal). Distâncias
    em cm; devolve forças em kN. Chumbadores alinhados numa fila espaçada de
    `espacamento`, com `borda` a distância à borda mais próxima perpendicular à fila.

    A NBR 8800 e a NBR 6118 não trazem o modelo de cone: a verificação é do ACI 318
    (ou EN 1992-4) e é responsabilidade do projetista de fundações.
    """
    fck = fck_kN_cm2(fck)
    if h_ef <= 0:
        raise ErroDeDados("o embutimento h_ef tem de ser positivo, em cm")
    hef_mm = h_ef * 10.0
    fck_MPa = fck * 10.0
    Nb = 10.0 * math.sqrt(fck_MPa) * hef_mm ** 1.5 / 1000.0      # kN
    proj = 1.5 * h_ef
    ANco = 9.0 * h_ef ** 2

    # extensão da área projetada na direção da fila
    lado_a = min(proj, borda_lateral) if borda_lateral is not None else proj
    lado_b = min(proj, borda_lateral_oposta) if borda_lateral_oposta is not None else proj
    Lx = lado_a + (n_tracionados - 1) * min(espacamento, 3.0 * h_ef) + lado_b
    # extensão perpendicular à fila
    lado_c = min(proj, borda) if borda is not None else proj
    lado_d = min(proj, borda_oposta) if borda_oposta is not None else proj
    Ly = lado_c + lado_d
    ANc = Lx * Ly

    bordas = [x for x in (borda, borda_oposta, borda_lateral, borda_lateral_oposta)
              if x is not None]
    c_min = min(bordas) if bordas else proj
    psi_ed = 1.0 if c_min >= proj else 0.7 + 0.3 * c_min / proj

    Ncbg = (ANc / ANco) * psi_ed * Nb
    return {"Nb": Nb, "ANco": ANco, "ANc": ANc, "razao": ANc / ANco,
            "psi_ed": psi_ed, "Ncbg": Ncbg, "Ncbg_Rd": PHI_CONE * Ncbg,
            "c_min": c_min, "projecao": proj,
            "sobreposicao": (n_tracionados > 1 and espacamento < 3.0 * h_ef),
            "cortado_pela_borda": c_min < proj}


def comprimento_aderencia(fck: float, d_barra: float, fy: float = 25.0,
                          eta1: float = 1.0) -> dict:
    """Comprimento de ancoragem por aderência (NBR 6118, item 9.4.2.4).

        l_b = ø·f_yd/(4·f_bd),  f_bd = η₁·η₂·η₃·f_ctd
        f_ctd = f_ctk,inf/γ_c = 0,7·0,3·f_ck^(2/3)/γ_c

    η₁ = 1,0 barra lisa (ou roscada comum), 1,4 entalhada, 2,25 nervurada;
    η₂ = 1,0 (boa aderência: barra vertical em pedestal); η₃ = 1,0 para ø < 32 mm.
    Dimensões em cm, tensões em kN/cm².
    """
    fck_MPa = fck_kN_cm2(fck) * 10.0
    fctm = 0.3 * fck_MPa ** (2.0 / 3.0)                 # MPa
    fctd = 0.7 * fctm / GAMA_C                          # MPa
    fbd = eta1 * 1.0 * 1.0 * fctd                       # MPa
    fyd = fy / GAMA_A1                                  # kN/cm²
    lb = d_barra * fyd / (4.0 * fbd / 10.0)             # cm
    return {"fctm_MPa": fctm, "fctd_MPa": fctd, "fbd_MPa": fbd, "fyd": fyd,
            "lb": lb, "lb_em_diametros": lb / d_barra}


def chumbadores(T_Sd: float, V_Sd: float, N_Sd: float = 0.0,
                diametro: str = '3/4"', aco: str = "ASTM F1554 Gr.36",
                n: int = 2, n_tracionados: Optional[int] = None,
                fck: float = 2.5, h_ef: Optional[float] = None,
                espacamento: float = 0.0, borda: Optional[float] = None,
                borda_oposta: Optional[float] = None,
                borda_lateral: Optional[float] = None,
                borda_lateral_oposta: Optional[float] = None,
                com_chapa_de_ancoragem: bool = True,
                elemento: str = "Chumbadores") -> Resultado:
    """Verifica o grupo de chumbadores: aço, ancoragem e distâncias.

    `T_Sd` é a tração TOTAL do grupo tracionado e `V_Sd` o cortante total que se
    decide levar pelos chumbadores (zero quando há chave de cisalhamento).
    `N_Sd` é a compressão simultânea, informativa (alivia a tração).

    Verificações:
      * tração e cisalhamento do aço (NBR 8800, item 6.3.3, γ_a2 = 1,35);
      * interação tração–cisalhamento (item 6.3.3.3);
      * ancoragem: por aderência (NBR 6118) e pelo cone a ≈ 35° (ACI 318, cap. 17),
        avisando quando os cones se sobrepõem ou são cortados pela borda;
      * distância à borda (≥ 5·d e ≥ 100 mm) e espaçamento (≥ 8·d).
    """
    nome_d, d, Ab, _ = lig._diam(diametro)
    fck = fck_kN_cm2(fck)
    n_t = n_tracionados if n_tracionados is not None else max(1, n // 2)
    T_por = T_Sd / n_t if n_t else 0.0
    V_por = V_Sd / n if n else 0.0
    h_ef = h_ef if h_ef is not None else max(15.0 * d, 30.0)

    r = Resultado(elemento, perfil=f"{n} × ø {nome_d}", material=aco)
    r.add(lig.tracao_parafuso(nome_d, aco, Ft_Sd=T_por))
    r.add(lig.cisalhamento_parafuso(nome_d, aco, planos=1, rosca_no_plano=True,
                                    Fv_Sd=V_por))
    if T_por > 0 and V_por > 0:
        r.add(lig.interacao_tracao_cisalhamento(nome_d, aco, T_por, V_por))

    # --- ancoragem por aderência ---
    ader = comprimento_aderencia(fck, d, mat.aco("ASTM A36").fy,
                                 eta1=1.0)
    v = Verificacao("Ancoragem por aderência (sem chapa na ponta)",
                    norma="NBR 6118:2014, item 9.4.2.4",
                    Sd=ader["lb"], Rd=h_ef, unidade="cm",
                    dispensada=com_chapa_de_ancoragem)
    v.passo("Resistência de aderência",
            formula="f<sub>bd</sub> = η₁·η₂·η₃·f<sub>ctd</sub>",
            conta=f"η₁ = 1,0 (barra lisa/roscada comum); f<sub>ctd</sub> = "
                  f"{fmt(ader['fctd_MPa'],3)} MPa",
            valor=fmt(ader["fbd_MPa"], 3, "MPa"))
    v.passo("Comprimento de ancoragem",
            formula="l<sub>b</sub> = ø·f<sub>yd</sub>/(4·f<sub>bd</sub>)",
            conta=f"{fmt(d,3)}·{fmt(ader['fyd'],2)}/(4·{fmt(ader['fbd_MPa']/10,4)})",
            valor=fmt(ader["lb"], 0, "cm") + f" = {fmt(ader['lb_em_diametros'],0)}·d")
    if com_chapa_de_ancoragem:
        v.observacao = ("Chumbador reto com chapa de ancoragem na ponta: a força não "
                        "depende da aderência; o estado-limite é o cone de "
                        "arrancamento. Embutimento usual 12·d a 17·d "
                        f"({12*d:.0f} a {17*d:.0f} cm).")
    r.add(v)

    # --- cone de arrancamento ---
    cone = cone_arrancamento(fck, h_ef, n_t, espacamento, borda, borda_oposta,
                             borda_lateral, borda_lateral_oposta)
    v = Verificacao("Arrancamento do cone de concreto (grupo)",
                    norma="ACI 318, cap. 17 — fora do escopo da NBR 8800; "
                          "verificação do projetista de fundações",
                    Sd=T_Sd, Rd=cone["Ncbg_Rd"], unidade="kN")
    v.passo("Resistência do chumbador isolado",
            formula="N<sub>b</sub> = 10·√f<sub>ck</sub>·h<sub>ef</sub>^1,5  (N, MPa, mm)",
            conta=f"10·√{fmt(fck*10,0)}·{fmt(h_ef*10,0)}^1,5",
            valor=fmt(cone["Nb"], 0, "kN"))
    v.passo("Áreas projetadas do cone (35° com a vertical)",
            formula="A<sub>Nco</sub> = 9·h<sub>ef</sub>² ; A<sub>Nc</sub> (grupo, cortada pelas bordas)",
            conta=f"{fmt(cone['ANco'],0)} cm² ; {fmt(cone['ANc'],0)} cm²",
            valor=f"A<sub>Nc</sub>/A<sub>Nco</sub> = {fmt(cone['razao'],3)}")
    v.passo("Fator de borda",
            formula="ψ<sub>ed</sub> = 0,7 + 0,3·c<sub>mín</sub>/(1,5·h<sub>ef</sub>) ≤ 1,0",
            conta=f"c<sub>mín</sub> = {fmt(cone['c_min'],1)} cm ; "
                  f"1,5·h<sub>ef</sub> = {fmt(cone['projecao'],1)} cm",
            valor=fmt(cone["psi_ed"], 3))
    v.passo("Resistência característica do grupo",
            formula="N<sub>cbg</sub> = (A<sub>Nc</sub>/A<sub>Nco</sub>)·ψ<sub>ed</sub>·N<sub>b</sub>",
            conta=f"{fmt(cone['razao'],3)}·{fmt(cone['psi_ed'],3)}·{fmt(cone['Nb'],0)}",
            valor=fmt(cone["Ncbg"], 0, "kN"))
    v.passo("Resistência de cálculo",
            formula="φ·N<sub>cbg</sub>", conta=f"{fmt(PHI_CONE,2)}·{fmt(cone['Ncbg'],0)}",
            valor=fmt(cone["Ncbg_Rd"], 0, "kN"), norma="ACI 318, φ = 0,70 (condição B)")
    avisos = []
    if cone["sobreposicao"]:
        avisos.append(f"os cones se sobrepõem (espaçamento {espacamento:.0f} cm < "
                      f"3·h_ef = {3*h_ef:.0f} cm)")
    if cone["cortado_pela_borda"]:
        avisos.append(f"o cone é cortado pela borda do pedestal (c = "
                      f"{cone['c_min']:.0f} cm < 1,5·h_ef = {cone['projecao']:.0f} cm)")
    if T_Sd > cone["Ncbg_Rd"]:
        avisos.append("O CONCRETO SIMPLES DO PEDESTAL NÃO ANCORA ESSA BASE: é preciso "
                      "armadura de suspensão (barras verticais e estribos que costurem "
                      "o cone) ou um pedestal maior. Encaminhe ao projetista de "
                      "fundações a tração POR CHUMBADOR, o diâmetro, o embutimento e "
                      "a geometria do grupo")
    v.observacao = "; ".join(avisos)
    r.add(v)

    # --- distâncias mínimas (Tabela 10.8) ---
    borda_min = max(5.0 * d, 10.0)
    esp_min = 8.0 * d
    v = Verificacao("Distâncias mínimas do chumbador",
                    norma="prática AISC Design Guide 1 / NBR 6118 (cobrimento)",
                    Sd=borda_min, Rd=(cone["c_min"] if borda is not None else borda_min),
                    unidade="cm")
    v.passo("Distância mínima à borda do pedestal",
            formula="≥ 5·d e ≥ 100 mm",
            conta=f"5·{fmt(d,3)} = {fmt(5*d,1)} cm",
            valor=fmt(borda_min, 1, "cm"))
    v.passo("Espaçamento mínimo entre chumbadores",
            formula="≥ 8·d (ideal 3·h<sub>ef</sub>)",
            conta=f"8·{fmt(d,3)} = {fmt(esp_min,1)} cm ; 3·h<sub>ef</sub> = "
                  f"{fmt(3*h_ef,0)} cm",
            valor=fmt(esp_min, 1, "cm"))
    v.passo("Embutimento mínimo absoluto",
            formula="h<sub>ef</sub> ≥ 300 mm", conta=f"adotado {fmt(h_ef*10,0)} mm",
            valor=fmt(h_ef * 10, 0, "mm"))
    if espacamento and espacamento < esp_min:
        v.observacao = (f"espaçamento adotado {espacamento:.1f} cm menor que o mínimo "
                        f"{esp_min:.1f} cm")
    r.add(v)

    furo, arr_lado, arr_t = FUROS_PLACA_BASE.get(nome_d, (None, None, None))
    r.dados.update({"diametro": nome_d, "d": d, "Ab": Ab, "n": n,
                    "n_tracionados": n_t, "T_Sd": T_Sd, "T_por_chumbador": T_por,
                    "V_Sd": V_Sd, "V_por_chumbador": V_por, "N_Sd": N_Sd,
                    "h_ef": h_ef, "h_ef_mm": h_ef * 10, "aco": aco,
                    "cone": cone, "aderencia": ader,
                    "furo_placa_mm": furo, "arruela_chapa_mm": arr_lado,
                    "arruela_espessura_mm": arr_t,
                    "borda_minima": borda_min, "espacamento_minimo": esp_min,
                    "chapa_ancoragem_mm": (3 * d * 10, 0.5 * d * 10)
                    if com_chapa_de_ancoragem else None,
                    "sobra_rosqueada_mm": 100.0, "trecho_rosqueado_mm": 150.0})
    return r


# ---------------------------------------------------------------------------
# 5. Transferência da força horizontal
# ---------------------------------------------------------------------------

def transferencia_horizontal(H_Sd: float, N_Sd_min: float, mu: float = 0.40,
                             diametro_chumbador: str = '3/4"',
                             aco_chumbador: str = "ASTM F1554 Gr.36",
                             n_chumbadores: int = 4,
                             arruelas_soldadas: bool = False,
                             B_placa: float = 45.0, fck: float = 2.5,
                             t_grout: float = 3.0, aco_chave: str = "ASTM A36",
                             w_chave: Optional[float] = None,
                             h_emb: Optional[float] = None,
                             h_emb_minimo: float = 8.0,
                             eletrodo: str = "E70XX",
                             utilizacao_maxima: float = 0.90,
                             lado_pedestal: Optional[float] = None,
                             elemento: str = "Transferência da força horizontal"
                             ) -> Resultado:
    """Escolhe e dimensiona o mecanismo de transferência de H para o concreto.

    Os três mecanismos do item 10.10 do manual NÃO SE SOMAM — cada um exige um
    deslocamento diferente e o mais rígido toma toda a carga. A função escolhe um:

      1. atrito placa–grout : H_Rd = μ·N_Sd,mín  (μ = 0,40 sobre grout)
      2. cisalhamento nos chumbadores : n·0,40·A_b·f_ub/γ_a2, só com as arruelas de
         chapa soldadas à placa (a folga do furo é de 13 a 21 mm)
      3. chave de cisalhamento : apoio direto da chapa contra o concreto
             σ = H_Sd/(w·h_emb) ≤ 0,85·f_ck/γ_c        (sem confinamento)
             M_Sd = H_Sd·(t_grout + h_emb/2) ≤ (w·t_k²/4)·f_y/γ_a1

    `N_Sd_min` é a MENOR compressão simultânea com H (combinação de vento), não a
    compressão de gravidade — este é o erro mais comum.
    """
    r = Resultado(elemento, material=aco_chave)
    fck = fck_kN_cm2(fck)
    nome_d, d_ch, Ab_ch, _ = lig._diam(diametro_chumbador)
    ac = mat.aco(aco_chave)

    # --- mecanismo 1: atrito ---
    H_atrito = mu * max(N_Sd_min, 0.0)
    v1 = Verificacao("Mecanismo 1 — atrito placa–grout",
                     norma="item 10.10.1 do manual (prática AISC Design Guide 1)",
                     Sd=H_Sd, Rd=H_atrito, unidade="kN")
    v1.passo("Resistência por atrito",
             formula="H<sub>Rd</sub> = μ·N<sub>Sd,mín</sub>",
             conta=f"{fmt(mu,2)}·{fmt(N_Sd_min,1)}", valor=fmt(H_atrito, 1, "kN"))
    v1.observacao = ("N_Sd,mín é a menor compressão SIMULTÂNEA com H — normalmente a "
                     "combinação com vento de sucção, não a de gravidade.")

    # --- mecanismo 2: chumbadores ---
    Fv1 = 0.40 * Ab_ch * mat.parafuso(aco_chumbador).fub / GAMA_A2
    H_chumb = n_chumbadores * Fv1
    v2 = Verificacao("Mecanismo 2 — cisalhamento nos chumbadores",
                     norma="NBR 8800:2008, item 6.3.3.1",
                     Sd=H_Sd, Rd=H_chumb if arruelas_soldadas else 0.0, unidade="kN")
    v2.passo("Resistência ao corte por chumbador",
             formula="F<sub>v,Rd</sub> = 0,40·A<sub>b</sub>·f<sub>ub</sub>/γ<sub>a2</sub>",
             conta=f"0,40·{fmt(Ab_ch,3)}·{fmt(mat.parafuso(aco_chumbador).fub,1)}/"
                   f"{fmt(GAMA_A2,2)}", valor=fmt(Fv1, 1, "kN"))
    v2.passo(f"{n_chumbadores} chumbadores",
             formula="n·F<sub>v,Rd</sub>", conta=f"{n_chumbadores}·{fmt(Fv1,1)}",
             valor=fmt(H_chumb, 1, "kN"))
    if not arruelas_soldadas:
        v2.observacao = (f"Com a folga do furo da placa (13 a 21 mm para ø {nome_d}) "
                         "os chumbadores não encostam juntos: só é legítimo contar "
                         "com eles se as arruelas de chapa forem soldadas à placa "
                         "depois do alinhamento do pilar (arruelas_soldadas=True). "
                         "Resistência considerada nula.")
    else:
        v2.observacao = ("Conte no máximo ≈ 30 % da resistência tabelada sem "
                         "verificação adicional: o chumbador flete no vão livre do "
                         "grout e o concreto lasca junto ao topo do pedestal.")

    dados = {"H_Sd": H_Sd, "N_Sd_min": N_Sd_min, "mu": mu,
             "H_Rd_atrito": H_atrito, "H_Rd_chumbadores": H_chumb,
             "arruelas_soldadas": arruelas_soldadas}

    if H_atrito >= H_Sd:
        r.add(v1)
        v2.dispensada = True
        r.add(v2)
        dados["mecanismo"] = "atrito"
        r.dados.update(dados)
        return r

    v1.dispensada = True
    v1.observacao += " Atrito insuficiente: descartado."
    r.add(v1)

    if arruelas_soldadas and H_chumb >= H_Sd:
        r.add(v2)
        dados["mecanismo"] = "chumbadores com arruelas soldadas"
        r.dados.update(dados)
        return r

    v2.dispensada = True
    r.add(v2)

    # --- mecanismo 3: chave de cisalhamento ---
    sigma_Rd = 0.85 * fck / GAMA_C
    A_nec = H_Sd / sigma_Rd
    w = w_chave if w_chave is not None else max(math.floor((B_placa - 5.0) / 5.0) * 5.0,
                                                10.0)
    h = h_emb if h_emb is not None else max(math.ceil(A_nec / w), h_emb_minimo)
    sigma = H_Sd / (w * h)

    v3 = Verificacao("Mecanismo 3 — chave de cisalhamento: apoio no concreto",
                     norma="item 10.10.3 do manual; NBR 6118 sem confinamento",
                     Sd=sigma, Rd=sigma_Rd, unidade="kN/cm²")
    v3.passo("Pressão resistente (sem confinamento)",
             formula="σ<sub>Rd</sub> = 0,85·f<sub>ck</sub>/γ<sub>c</sub>",
             conta=f"0,85·{fmt(fck,3)}/{fmt(GAMA_C,2)}",
             valor=fmt(sigma_Rd, 4, "kN/cm²") + f" = {fmt(sigma_Rd*10,1)} MPa")
    v3.passo("Área necessária",
             formula="A<sub>nec</sub> = H<sub>Sd</sub>/σ<sub>Rd</sub>",
             conta=f"{fmt(H_Sd,1)}/{fmt(sigma_Rd,4)}", valor=fmt(A_nec, 1, "cm²"))
    v3.passo("Chave adotada",
             formula="A = w·h<sub>emb</sub>",
             conta=f"{fmt(w,1)}·{fmt(h,1)}", valor=fmt(w * h, 0, "cm²"))
    v3.passo("Pressão de cálculo",
             formula="σ = H<sub>Sd</sub>/(w·h<sub>emb</sub>)",
             conta=f"{fmt(H_Sd,1)}/{fmt(w*h,0)}",
             valor=fmt(sigma, 4, "kN/cm²") + f" = {fmt(sigma*10,1)} MPa")
    v3.observacao = ("Não se usa √(A₂/A₁) na face vertical de um rasgo: não há "
                     "confinamento.")
    r.add(v3)

    braco = t_grout + h / 2.0
    M_chave = H_Sd * braco
    tk_nec = math.sqrt(4.0 * M_chave * GAMA_A1 / (w * ac.fy))
    tk = chapa_comercial(tk_nec, minimo=ESPESSURA_MINIMA_GALPAO,
                         utilizacao_maxima=utilizacao_maxima)
    Z = w * tk ** 2 / 4.0
    M_Rd = Z * ac.fy / GAMA_A1
    v4 = Verificacao("Chave de cisalhamento — flexão da chapa",
                     norma="NBR 8800:2008, item 5.4.2 (plastificação da chapa)",
                     Sd=M_chave, Rd=M_Rd, unidade="kN·cm")
    v4.passo("Braço do momento",
             formula="t<sub>grout</sub> + h<sub>emb</sub>/2",
             conta=f"{fmt(t_grout,1)} + {fmt(h,1)}/2", valor=fmt(braco, 1, "cm"))
    v4.passo("Momento solicitante",
             formula="M<sub>Sd</sub> = H<sub>Sd</sub>·(t<sub>grout</sub> + h<sub>emb</sub>/2)",
             conta=f"{fmt(H_Sd,1)}·{fmt(braco,1)}", valor=fmt(M_chave, 0, "kN·cm"))
    v4.passo("Espessura necessária",
             formula="t<sub>k</sub> ≥ √(4·M<sub>Sd</sub>·γ<sub>a1</sub>/(w·f<sub>y</sub>))",
             conta=f"√(4·{fmt(M_chave,0)}·{fmt(GAMA_A1,2)}/({fmt(w,1)}·{fmt(ac.fy,1)}))",
             valor=fmt(tk_nec, 3, "cm") + f" = {fmt(tk_nec*10,1)} mm")
    v4.passo("Chapa comercial adotada",
             formula="M<sub>Rd</sub> = (w·t<sub>k</sub>²/4)·f<sub>y</sub>/γ<sub>a1</sub>",
             conta=f"({fmt(w,1)}·{fmt(tk,3)}²/4)·{fmt(ac.fy,1)}/{fmt(GAMA_A1,2)}",
             valor=fmt(M_Rd, 0, "kN·cm") + f" (t = {fmt(tk*10,1)} mm)")
    r.add(v4)

    V_Rd_chave = 0.6 * ac.fy * (w * tk) / GAMA_A1
    v5 = Verificacao("Chave de cisalhamento — cisalhamento da chapa",
                     norma="NBR 8800:2008, item 5.4.3.5",
                     Sd=H_Sd, Rd=V_Rd_chave, unidade="kN")
    v5.passo("Resistência ao cisalhamento",
             formula="V<sub>Rd</sub> = 0,6·f<sub>y</sub>·w·t<sub>k</sub>/γ<sub>a1</sub>",
             conta=f"0,6·{fmt(ac.fy,1)}·{fmt(w,1)}·{fmt(tk,3)}/{fmt(GAMA_A1,2)}",
             valor=fmt(V_Rd_chave, 0, "kN"))
    r.add(v5)

    # solda da chave à placa: dois filetes longitudinais, momento + cortante
    S = 2.0 * w * (tk / 2.0)
    f_M = M_chave / S
    f_V = H_Sd / (2.0 * w)
    f_res = math.hypot(f_M, f_V)
    el = mat.eletrodo(eletrodo)
    r_por_cm_perna = 0.6 * el.fw * 0.707 / GAMA_W2
    perna_nec = f_res / r_por_cm_perna
    perna = max(math.ceil(perna_nec * 10) / 10.0, mat.perna_minima(tk))
    v6 = lig.filete(perna, w, eletrodo, ac.fy, t_base=tk, F_Sd=f_res * w,
                    n_cordoes=2, nome="chave × placa de base (2 filetes)")
    v6.passo("Módulo do grupo de soldas",
             formula="S = 2·w·(t<sub>k</sub>/2)",
             conta=f"2·{fmt(w,1)}·({fmt(tk,3)}/2)", valor=fmt(S, 1, "cm²"))
    v6.passo("Força por cm devida ao momento",
             formula="f<sub>M</sub> = M/S", conta=f"{fmt(M_chave,0)}/{fmt(S,1)}",
             valor=fmt(f_M, 2, "kN/cm"))
    v6.passo("Força por cm devida ao cortante",
             formula="f<sub>V</sub> = H/(2·w)", conta=f"{fmt(H_Sd,1)}/(2·{fmt(w,1)})",
             valor=fmt(f_V, 2, "kN/cm"))
    v6.passo("Resultante e perna necessária",
             formula="f = √(f<sub>M</sub>² + f<sub>V</sub>²) ; b = f/(0,6·f<sub>w</sub>·0,707/γ<sub>w2</sub>)",
             conta=f"√({fmt(f_M,2)}² + {fmt(f_V,2)}²) = {fmt(f_res,2)} ; "
                   f"{fmt(f_res,2)}/{fmt(r_por_cm_perna,2)}",
             valor=fmt(perna_nec, 3, "cm") + f" → filete de {fmt(perna*10,0)} mm")
    r.add(v6)

    # concreto disponível à frente da chave, medido a partir da largura da chave
    concreto_frente = (lado_pedestal - w) / 2.0 if lado_pedestal else None
    dados.update({"mecanismo": "chave de cisalhamento",
                  "sigma_Rd_chave": sigma_Rd, "A_necessaria_chave": A_nec,
                  "w_chave": w, "h_emb": h, "sigma_chave": sigma,
                  "t_chave": tk, "t_chave_mm": tk * 10,
                  "t_chave_necessaria_mm": tk_nec * 10,
                  "altura_total_chave": h + t_grout,
                  "altura_total_chave_mm": (h + t_grout) * 10,
                  "M_chave": M_chave, "perna_solda_chave": perna,
                  "perna_solda_chave_mm": perna * 10,
                  "rasgo_mm": ((w + 4.0) * 10, (h + t_grout + 3.0) * 10),
                  "t_grout": t_grout})
    if concreto_frente is not None:
        dados["concreto_a_frente"] = concreto_frente
        v7 = Verificacao("Concreto à frente da chave",
                         norma="prática de detalhamento (item 10.10.3 do manual)",
                         Sd=15.0, Rd=concreto_frente, unidade="cm")
        v7.passo("Mínimo de concreto à frente da chave, na direção da força",
                 formula="≥ 150 mm", conta=f"disponível {fmt(concreto_frente,1)} cm",
                 valor=fmt(concreto_frente, 1, "cm"))
        v7.observacao = ("Com menos concreto à frente, ele lasca em cunha antes de "
                         "mobilizar o apoio.")
        r.add(v7)
    r.dados.update(dados)
    return r


# ---------------------------------------------------------------------------
# 6. Orquestrador
# ---------------------------------------------------------------------------

def dimensionar_base(pilar, N_Sd: float, M_Sd: float = 0.0, H_Sd: float = 0.0,
                     N_Sd_min: Optional[float] = None, fck: float = 2.5,
                     pedestal: Tuple[float, float] = (60.0, 60.0),
                     aco_placa: str = "ASTM A36",
                     diametro_chumbador: str = '3/4"',
                     aco_chumbador: str = "ASTM F1554 Gr.36",
                     n_chumbadores: int = 4, B: Optional[float] = None,
                     L: Optional[float] = None,
                     f_chumbador: Optional[float] = None,
                     h_ef: Optional[float] = None, t_grout: float = 3.0,
                     mu: float = 0.40, borda_chumbador: float = 5.0,
                     elemento: str = "Base de pilar") -> Resultado:
    """Dimensiona a base completa e devolve a geometria para o desenho.

    Orquestra:
      * placa de base (centrada ou com momento);
      * chumbadores (tração do binário ou apenas construtivos) e ancoragem;
      * transferência da força horizontal (atrito, chumbadores ou chave);
    e reúne em `dados` a geometria, o grout, o pedestal e a lista de material.
    """
    g = _perfil(pilar)
    fck = fck_kN_cm2(fck)
    N_min = N_Sd_min if N_Sd_min is not None else N_Sd
    r = Resultado(elemento, perfil=g.get("nome", ""), material=aco_placa)

    if M_Sd > 0:
        if B is None or L is None:
            # pré-dimensiona pela compressão e alarga na direção do momento
            pre = placa_base_centrada(pilar, N_Sd, fck, pedestal, aco_placa,
                                      borda_chumbador=borda_chumbador,
                                      diametro_chumbador=diametro_chumbador,
                                      engastada=True)
            B = B or pre.dados["B"]
            L = L or max(pre.dados["L"],
                         math.ceil((g["d"] / 10.0 + 4 * borda_chumbador) / 5.0) * 5.0)
        f_ch = f_chumbador if f_chumbador is not None else L / 2.0 - borda_chumbador
        placa = placa_base_com_momento(pilar, N_min, M_Sd, B, L, f_ch, fck, pedestal,
                                       aco_placa,
                                       n_chumbadores_tracionados=n_chumbadores // 2,
                                       engastada=True)
        # e a combinação de N máximo, que governa o concreto e a espessura
        placa_Nmax = placa_base_com_momento(pilar, N_Sd, M_Sd, B, L, f_ch, fck,
                                            pedestal, aco_placa,
                                            n_chumbadores_tracionados=n_chumbadores // 2,
                                            engastada=True,
                                            elemento="Placa — combinação N máximo")
        for v in placa_Nmax.verificacoes:
            v.titulo += " (N máximo)"
            r.add(v)
        T = placa.dados.get("T", 0.0)
        t_placa = max(placa.dados["t"], placa_Nmax.dados["t"])
        r.dados["placa_N_maximo"] = placa_Nmax.dados
    else:
        placa = placa_base_centrada(pilar, N_Sd, fck, pedestal, aco_placa, B, L,
                                    diametro_chumbador=diametro_chumbador,
                                    borda_chumbador=borda_chumbador)
        T = 0.0
        t_placa = placa.dados["t"]
        f_ch = f_chumbador if f_chumbador is not None else \
            placa.dados.get("x_chumbador", placa.dados["B"] / 2.0 - borda_chumbador)

    for v in placa.verificacoes:
        r.add(v)
    r.dados.update(placa.dados)
    r.dados["t"] = t_placa
    r.dados["t_mm"] = t_placa * 10

    B_f, L_f = r.dados["B"], r.dados["L"]
    nome_d, d_ch, _, _ = lig._diam(diametro_chumbador)
    h_ef_f = h_ef if h_ef is not None else max(math.ceil(15 * d_ch / 5.0) * 5.0, 30.0)
    espac = r.dados.get("espacamento_chumbadores", min(B_f, L_f) - 2 * borda_chumbador)

    ch = chumbadores(T, 0.0, N_min, diametro_chumbador, aco_chumbador,
                     n=n_chumbadores, n_tracionados=max(1, n_chumbadores // 2),
                     fck=fck, h_ef=h_ef_f, espacamento=espac,
                     borda=(pedestal[1] - L_f) / 2.0 + (L_f / 2.0 - f_ch),
                     borda_oposta=None,
                     borda_lateral=(pedestal[0] - espac) / 2.0,
                     borda_lateral_oposta=(pedestal[0] - espac) / 2.0)
    for v in ch.verificacoes:
        r.add(v)
    r.dados["chumbadores"] = ch.dados

    if H_Sd:
        tr = transferencia_horizontal(H_Sd, N_min, mu, diametro_chumbador,
                                      aco_chumbador, n_chumbadores,
                                      B_placa=B_f, fck=fck, t_grout=t_grout,
                                      lado_pedestal=pedestal[0])
        for v in tr.verificacoes:
            r.add(v)
        r.dados["transferencia_horizontal"] = tr.dados

    # --- geometria e lista de material ---
    aco = mat.aco(aco_placa)
    peso_placa = B_f * L_f * t_placa * 7.85e-3
    material = [{"peca": "placa de base",
                 "descricao": f"{B_f*10:.0f} × {L_f*10:.0f} × {t_placa*10:.1f} mm "
                              f"({aco_placa})",
                 "quantidade": 1, "peso_kg": round(peso_placa, 1)},
                {"peca": "chumbador",
                 "descricao": f"ø {nome_d} {aco_chumbador}, embutido "
                              f"{h_ef_f*10:.0f} mm, com chapa de ancoragem",
                 "quantidade": n_chumbadores,
                 # comprimento total ≈ embutimento + grout + placa + sobra de 100 mm
                 "peso_kg": round(n_chumbadores * math.pi * d_ch ** 2 / 4 *
                                  (h_ef_f + t_grout + t_placa + 10.0) * 7.85e-3, 1)},
                {"peca": "arruela de chapa",
                 "descricao": f"{FUROS_PLACA_BASE.get(nome_d, ('','',''))[1]} × "
                              f"{FUROS_PLACA_BASE.get(nome_d, ('','',''))[1]} × "
                              f"{FUROS_PLACA_BASE.get(nome_d, ('','',''))[2]} mm",
                 "quantidade": n_chumbadores, "peso_kg": None},
                {"peca": "grout", "descricao": f"espessura {t_grout*10:.0f} mm, "
                                               "f_ck ≥ 40 MPa, retração compensada",
                 "quantidade": 1, "peso_kg": None}]
    if r.dados.get("transferencia_horizontal", {}).get("mecanismo") == \
            "chave de cisalhamento":
        tc = r.dados["transferencia_horizontal"]
        material.append({"peca": "chave de cisalhamento",
                         "descricao": f"{tc['w_chave']*10:.0f} × "
                                      f"{tc['altura_total_chave_mm']:.0f} × "
                                      f"{tc['t_chave_mm']:.1f} mm, filete "
                                      f"{tc['perna_solda_chave_mm']:.0f} mm 2 lados",
                         "quantidade": 1,
                         "peso_kg": round(tc['w_chave'] * tc['altura_total_chave'] *
                                          tc['t_chave'] * 7.85e-3, 1)})
    r.dados.update({"lista_material": material, "t_grout": t_grout,
                    "furo_placa_mm": FUROS_PLACA_BASE.get(nome_d, (None,))[0],
                    "n_chumbadores": n_chumbadores, "f_chumbador": f_ch,
                    "h_ef": h_ef_f, "pedestal": pedestal, "fck": fck,
                    "geometria": {"B_mm": B_f * 10, "L_mm": L_f * 10,
                                  "t_mm": t_placa * 10,
                                  "pedestal_mm": (pedestal[0] * 10, pedestal[1] * 10),
                                  "grout_mm": t_grout * 10,
                                  "chumbador_x_mm": f_ch * 10,
                                  "h_ef_mm": h_ef_f * 10}})
    return r
