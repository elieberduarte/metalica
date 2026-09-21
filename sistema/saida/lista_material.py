# -*- coding: utf-8 -*-
"""Lista de material, romaneio, resumo de compra e orçamento do galpão.

Produz, em `pasta`:

* `romaneio.csv`          — uma linha por marca (CSV ; com BOM, abre no Excel brasileiro)
* `resumo-perfis.csv`     — quanto comprar de cada perfil, em barras de 6 e 12 m
* `orcamento.csv`         — material, fabricação, pintura, montagem e total
* `Lista_de_material.pdf` — os mesmos quadros em PDF, no padrão do memorial

Nada aqui é dimensionamento: a lista sai da geometria de `DadosGalpao` e dos perfis já
escolhidos em `ProjetoGalpao.elementos`. Quando o orquestrador ainda não preencheu
`projeto.lista_material`, este módulo a monta e registra um aviso, para que o documento
diga com todas as letras que o romaneio é uma estimativa de projeto básico, e não o
detalhamento de fabricação.

Referências dos percentuais e índices adotados (todos **indicativos**, marcados como tal
no documento): manual, Capítulo 16, itens 16.11 (lista de material) e 16.12 (custo), e
Capítulo 12 (acabamento).
"""
import csv
import math
import os
import re
import sys
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo.base import fmt                                        # noqa: E402
from nucleo.modelo_galpao import DadosGalpao, Peca, ProjetoGalpao  # noqa: E402
from nucleo.perfis import Perfil, perfil as _busca_perfil          # noqa: E402

# =====================================================================================
# Constantes adotadas — todas documentadas e indicativas
# =====================================================================================

#: Massa específica do aço, kg/m³ (NBR 8800:2008, item 4.5).
RHO_ACO = 7850.0

#: Comprimentos comerciais de barra usados na compra (m).
COMPRIMENTOS_COMERCIAIS = (6.0, 12.0)

#: Espessura de corte perdida por serrada (m) — 5 mm por corte, prática de oficina.
PERDA_SERRA = 0.005

#: Chapas de ligação, enrijecedores, gussets e placas de base, em % do peso dos perfis.
#: Manual, item 16.11 (galpões parafusados; conferir no detalhamento).
PERC_CHAPAS = 0.05

#: Parafusos, chumbadores, esticadores, porcas e arruelas, em % do peso dos perfis.
PERC_PARAFUSOS = 0.03

#: Repartição do custo por kg instalado (manual, Tabela 16.6 — valores indicativos do
#: mercado brasileiro, ordem de grandeza 2025–2026, sem impostos específicos, telhas,
#: fundações e piso). As frações somam 1,00 e são aplicadas sobre `dados.custo_kg`.
REPARTICAO_CUSTO = [
    ("Material (perfis, chapas, parafusos)", 7.50 / 17.00,
     "Perfis W ≈ 6,5–8; Ue galvanizado ≈ 8–9; parafusos e chumbadores ≈ 20–30 R$/kg"),
    ("Fabricação (corte, furação, solda, montagem em oficina)", 4.50 / 17.00,
     "3–6 R$/kg; peças repetitivas e parafusadas baixam o valor"),
    ("Pintura / galvanização", 2.00 / 17.00,
     "1,5–3 R$/kg conforme o sistema (C2: 1,5; C3 epóxi/PU: 2,5–3)"),
    ("Transporte e montagem", 3.00 / 17.00,
     "2,5–4 R$/kg; distância e altura influem"),
]

#: Esquema de pintura adotado na estimativa de tinta (manual, item 16.13; ISO 12944 C3).
#: (demão, espessura seca µm, sólidos em volume, perda de aplicação)
ESQUEMA_PINTURA = [
    ("Primer epóxi bicomponente", 80.0, 0.60, 0.30),
    ("Acabamento poliuretano acrílico alifático", 60.0, 0.55, 0.30),
]

#: Peças entregues galvanizadas (não entram na área de pintura) — manual, item 16.13.
GALVANIZADOS = ("terça", "longarina", "corrente", "tirante", "mão-francesa",
                "mao-francesa", "chapa de terça")


# =====================================================================================
# Utilidades
# =====================================================================================

def _sem_acento(t: str) -> str:
    tab = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
    return t.translate(tab)


def _perfil(nome) -> Optional[Perfil]:
    """Perfil do catálogo, ou `None` quando o nome não é um perfil tabelado."""
    if isinstance(nome, Perfil):
        return nome
    if not nome:
        return None
    texto = str(nome).strip()
    try:
        return _busca_perfil(texto)
    except Exception:
        pass
    # nomes anotados ("W 360×32,9 cortado", "Ue 200×75×20×2,65 galvanizado"):
    # tenta de novo tirando as palavras finais, uma a uma
    partes = texto.split()
    while len(partes) > 1:
        partes = partes[:-1]
        try:
            return _busca_perfil(" ".join(partes))
        except Exception:
            continue
    return None


def _diametro_mm(nome: str) -> float:
    """Diâmetro de uma barra redonda citada no nome ('Barra ø 20 mm', 'ø 12,5')."""
    m = re.search(r"(?:ø|Ø|diam\.?|d\s*=)\s*([\d]+(?:[.,]\d+)?)", str(nome))
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"redond[ao].*?([\d]+(?:[.,]\d+)?)", str(nome), re.I)
    return float(m.group(1).replace(",", ".")) if m else 0.0


def massa_kg_m(nome) -> float:
    """Massa linear (kg/m) do perfil: do catálogo, ou da geometria da barra redonda."""
    p = _perfil(nome)
    if p is not None and p.massa:
        return float(p.massa)
    d = _diametro_mm(nome)
    if d > 0:
        # barra redonda maciça: ρ·π·d²/4
        return RHO_ACO * math.pi * (d / 1000.0) ** 2 / 4.0
    return 0.0


def perimetro_mm(nome) -> float:
    """Perímetro externo (mm) da seção, para a área de pintura."""
    p = _perfil(nome)
    if p is None:
        d = _diametro_mm(nome)
        return math.pi * d if d > 0 else 0.0
    d, bf, tw, tf = p.d, p.bf, p.tw, p.tf
    if p.tipo == "tubo":
        if str(p.dados.get("tipo", "")).startswith("redond") or not bf:
            return math.pi * d
        return 2.0 * (d + bf)
    if p.tipo == "I":
        # contorno do I: 2·d na vertical e 4·bf − 2·tw na horizontal
        return 2.0 * d + 4.0 * bf - 2.0 * tw
    if p.tipo in ("U", "Ue"):
        # perfil aberto: duas faces de cada parede
        lab = float(p.dados.get("D") or p.dados.get("lab") or 0.0)
        return 2.0 * (d + 2.0 * bf + 2.0 * lab)
    if p.tipo == "L":
        return 2.0 * (d + bf)
    if p.A:                                   # caso genérico: perímetro por área/espessura
        return 4.0 * math.sqrt(p.A * 100.0)   # cm² → mm²; quadrado equivalente
    return 0.0


def area_pintura_m2_m(nome) -> float:
    """Área de pintura por metro de peça (m²/m)."""
    return perimetro_mm(nome) / 1000.0


def _galvanizada(descricao: str) -> bool:
    d = _sem_acento(str(descricao)).lower()
    return any(_sem_acento(g).lower() in d for g in GALVANIZADOS)


def br(x, casas: int = 2) -> str:
    """Número no padrão brasileiro com separador de milhar, sem notação científica.

    `nucleo.base.fmt` passa para notação científica acima de 10⁵, o que não serve
    para valores de orçamento (R$ 411 225,00 e não 4,11e+05).
    """
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    return f"{float(x):,.{casas}f}".replace(",", " ").replace(".", ",")


def _num(x, casas=2) -> str:
    """Número no padrão brasileiro, sem separador de milhar (para o CSV)."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    return f"{float(x):.{casas}f}".replace(".", ",")


# =====================================================================================
# 1. Romaneio — monta a lista quando o orquestrador não a preencheu
# =====================================================================================

def _perfis_do_projeto(projeto: ProjetoGalpao) -> Dict[str, str]:
    """Perfil de cada família de peça, do projeto ou do padrão dos desenhos."""
    try:
        from saida import desenhos
        return dict(desenhos._perfis_galpao(projeto, projeto.dados))
    except Exception:
        d = projeto.dados
        base = {"pilar": "W 360×44,6", "viga": "W 360×32,9",
                "terca": "Ue 200×75×20×2,65", "longarina": "Ue 200×75×20×2,65",
                "coluna_oitao": "W 250×25,3", "diagonal": 'L 3"×1/4"',
                "escora": "TC 88,9×3,2"}
        for chave, alvo in (("pilar", "pilar"), ("viga", "viga"),
                            ("terça", "terca"), ("longarina", "longarina")):
            el = projeto.elemento(chave)
            if el and el.perfil:
                base[alvo] = el.perfil
        _ = d
        return base


def _peca(marca, descricao, perfil_nome, material, qtd, comp_m, obs="",
          massa_unitaria=None, pintada=True) -> Peca:
    """Monta uma `Peca` já com peso e área de pintura calculados."""
    kg_m = massa_unitaria if massa_unitaria is not None else massa_kg_m(perfil_nome)
    peso_unit = kg_m * comp_m
    area = 0.0 if not pintada else area_pintura_m2_m(perfil_nome) * comp_m * qtd
    return Peca(marca=marca, descricao=descricao, perfil=str(perfil_nome),
                material=material, quantidade=int(qtd), comprimento_m=round(comp_m, 3),
                peso_unit_kg=round(peso_unit, 2),
                peso_total_kg=round(peso_unit * qtd, 1),
                area_pintura_m2=round(area, 2), observacao=obs)


def montar_pecas(projeto: ProjetoGalpao) -> Tuple[List[Peca], List[str]]:
    """Romaneio estimado a partir da geometria e dos perfis adotados.

    Reproduz a montagem do Capítulo 16, item 16.11 do manual: pórticos, mísulas,
    terças, longarinas, correntes, contraventamento de cobertura e vertical, escoras,
    colunas de oitão e mãos-francesas, mais as parcelas de chapas (5 %) e parafusos
    (3 %) do peso dos perfis.
    """
    d = projeto.dados
    pf = _perfis_do_projeto(projeto)
    avisos: List[str] = []
    pecas: List[Peca] = []

    n_port = d.n_porticos
    n_vaos = max(1, n_port - 1)
    L_agua = d.comprimento_agua                      # m, meia-viga inclinada
    L_mis = d.comprimento_misula if d.com_misula else 0.0
    aco_p, aco_t, aco_c = d.aco_perfis, d.aco_tercas, d.aco_chapas

    # --- pórticos ---------------------------------------------------------------
    pecas.append(_peca("P1", "Pilar do pórtico", pf["pilar"], aco_p,
                       2 * n_port, d.pe_direito,
                       obs=f"{n_port} pórticos × 2 pilares"))
    pecas.append(_peca("V1", "Viga do pórtico (rafter)", pf["viga"], aco_p,
                       2 * n_port, L_agua,
                       obs=f"meia-viga inclinada {fmt(d.angulo_telhado, 1)}°"))
    if L_mis > 0:
        p_viga = _perfil(pf["viga"])
        kg_m_mis = (p_viga.massa * 0.5) if p_viga else massa_kg_m(pf["viga"]) * 0.5
        pecas.append(_peca("M1", "Mísula (meia peça do rafter)",
                           pf["viga"] + " cortado", aco_p, 2 * n_port, L_mis,
                           obs="corte diagonal de peça igual à viga; massa ≈ 50 %",
                           massa_unitaria=kg_m_mis))

    # --- terças -----------------------------------------------------------------
    n_terca_agua = max(2, int(math.ceil(L_agua / d.espacamento_tercas)) + 1)
    n_linhas_terca = 2 * n_terca_agua
    pecas.append(_peca("T1", "Terça de cobertura", pf["terca"], aco_t,
                       n_linhas_terca * n_vaos, d.espacamento_porticos,
                       obs=f"{n_linhas_terca} linhas × {n_vaos} vãos; "
                           f"espaçamento real {fmt(L_agua / (n_terca_agua - 1), 2)} m",
                       pintada=False))

    # --- longarinas de fechamento ----------------------------------------------
    h_fech = d.altura_fechamento or d.pe_direito
    n_long_lateral = max(2, int(math.ceil(h_fech / 2.0)) + 1)
    pecas.append(_peca("L1", "Longarina lateral", pf["longarina"], aco_t,
                       2 * n_long_lateral * n_vaos, d.espacamento_porticos,
                       obs=f"2 laterais × {n_long_lateral} linhas × {n_vaos} vãos",
                       pintada=False))
    n_long_oitao = max(2, int(math.ceil(h_fech / 2.0)) + 1)
    pecas.append(_peca("L2", "Longarina de oitão", pf["longarina"], aco_t,
                       2 * n_long_oitao, d.vao / 2.0,
                       obs="2 oitões; peças entre colunas de oitão", pintada=False))

    # --- correntes e tirantes ---------------------------------------------------
    n_corr = max(0, int(d.linhas_correntes))
    if n_corr:
        n_pecas_corr = 2 * n_corr * n_vaos * n_terca_agua
        pecas.append(_peca("C1", "Corrente de terça", "Barra ø 12,5 mm", aco_c,
                           n_pecas_corr, d.espacamento_porticos * 0.75,
                           obs="tirante entre terças; comprimento médio adotado",
                           pintada=False))
        pecas.append(_peca("C2", "Tirante de cumeeira", "Barra ø 16,0 mm", aco_c,
                           2 * n_vaos, d.espacamento_tercas,
                           obs="liga as terças de cumeeira das duas águas",
                           pintada=False))

    # --- contraventamento de cobertura (X em barra redonda) ---------------------
    n_vaos_contrav = 2 if n_vaos <= 4 else (2 + (n_vaos - 4) // 5)
    diag_cob = math.hypot(d.espacamento_porticos, d.vao / 2.0 / 2.0)
    n_diag_cob = n_vaos_contrav * 8
    pecas.append(_peca("X1", "Diagonal do contraventamento de cobertura",
                       "Barra ø 20,0 mm", aco_p, n_diag_cob, diag_cob,
                       obs=f"{n_vaos_contrav} vãos contraventados × 8 diagonais; "
                           "com esticador"))
    # --- escoras longitudinais --------------------------------------------------
    n_escoras = n_vaos_contrav * n_terca_agua
    pecas.append(_peca("E1", "Escora longitudinal", pf["escora"], aco_p,
                       n_escoras, d.espacamento_porticos,
                       obs="fecha o X de cobertura contra os pórticos vizinhos"))

    # --- contraventamento vertical (X em cantoneira) ----------------------------
    diag_vert = math.hypot(d.espacamento_porticos, d.pe_direito)
    n_diag_vert = n_vaos_contrav * 2 * 2
    pecas.append(_peca("X2", "Diagonal do contraventamento vertical",
                       pf["diagonal"], aco_p, n_diag_vert, diag_vert,
                       obs=f"{n_vaos_contrav} vãos × 2 laterais × 2 diagonais"))

    # --- colunas de oitão -------------------------------------------------------
    n_col_oitao = 2 * max(1, int(round(d.vao / 5.0)) - 1)
    h_media_oitao = d.pe_direito + d.vao / 4.0 * (d.inclinacao / 100.0)
    pecas.append(_peca("O1", "Coluna de oitão", pf["coluna_oitao"], aco_p,
                       n_col_oitao, h_media_oitao,
                       obs="altura média entre o joelho e a cumeeira"))

    # --- mãos-francesas ---------------------------------------------------------
    n_mf = 2 * n_port * n_long_lateral
    pecas.append(_peca("F1", "Mão-francesa de longarina", 'L 1½"×3/16"', aco_c,
                       n_mf, 0.60,
                       obs="trava a mesa interna do pilar a cada longarina",
                       pintada=False))

    peso_perfis = sum(p.peso_total_kg for p in pecas)
    area_perfis = sum(p.area_pintura_m2 for p in pecas)

    # --- chapas e parafusos (percentuais indicativos) ---------------------------
    peso_chapas = peso_perfis * PERC_CHAPAS
    pecas.append(Peca(
        marca="CH", descricao="Chapas de ligação, enrijecedores, gussets, placas de base "
                              "e chapas de terça",
        perfil=f"≈ {PERC_CHAPAS * 100:.0f} % do peso dos perfis", material=aco_c,
        quantidade=1, comprimento_m=0.0, peso_unit_kg=round(peso_chapas, 1),
        peso_total_kg=round(peso_chapas, 1),
        area_pintura_m2=round(area_perfis * PERC_CHAPAS * 2.0, 1),
        observacao="estimativa de projeto básico (manual, item 16.11); "
                   "conferir no detalhamento de fabricação"))
    peso_paraf = peso_perfis * PERC_PARAFUSOS
    pecas.append(Peca(
        marca="PA", descricao="Parafusos, chumbadores, esticadores, porcas e arruelas",
        perfil=f"≈ {PERC_PARAFUSOS * 100:.0f} % do peso dos perfis",
        material=d.parafuso, quantidade=1, comprimento_m=0.0,
        peso_unit_kg=round(peso_paraf, 1), peso_total_kg=round(peso_paraf, 1),
        area_pintura_m2=0.0,
        observacao="galvanizados; estimativa de projeto básico (manual, item 16.11)"))

    avisos.append(
        "Romaneio montado pelo módulo de saída a partir da geometria e dos perfis "
        "adotados: é uma estimativa de projeto básico. As quantidades de chapas "
        f"({PERC_CHAPAS * 100:.0f} %) e parafusos ({PERC_PARAFUSOS * 100:.0f} %) são "
        "percentuais típicos do manual (item 16.11) e devem ser substituídas pelo "
        "romaneio do detalhamento de fabricação.")
    return pecas, avisos


# =====================================================================================
# 2. Resumos
# =====================================================================================

def resumo_por_tipo(pecas: Sequence[Peca], area_coberta: float) -> List[dict]:
    """Peso por família de peça, com a participação no total e o índice kg/m²."""
    grupos: Dict[str, float] = {}
    ordem: List[str] = []
    for p in pecas:
        chave = p.descricao.split("(")[0].strip()
        if chave not in grupos:
            grupos[chave] = 0.0
            ordem.append(chave)
        grupos[chave] += p.peso_total_kg
    total = sum(grupos.values()) or 1.0
    return [{"tipo": k, "peso_kg": grupos[k], "perc": 100.0 * grupos[k] / total,
             "kg_m2": grupos[k] / area_coberta if area_coberta else 0.0}
            for k in ordem]


def _empacotar(comprimentos: Sequence[float], barra: float) -> Optional[int]:
    """Quantas barras de `barra` metros são precisas, cortando as peças dadas.

    Primeiro-que-serve em ordem decrescente (first-fit decreasing), a mesma regra
    que o cortador usa na serra: começa pelas peças longas e aproveita a sobra de
    cada barra nas peças menores. Cada corte consome `PERDA_SERRA` de material.
    Devolve `None` quando alguma peça é mais longa que a barra.
    """
    restos: List[float] = []
    for L in sorted(comprimentos, reverse=True):
        if L > barra + 1e-9:
            return None
        for i, r in enumerate(restos):
            if r >= L - 1e-9:
                restos[i] = r - L - PERDA_SERRA
                break
        else:
            restos.append(barra - L - PERDA_SERRA)
    return len(restos)


def compra_por_perfil(pecas: Sequence[Peca]) -> List[dict]:
    """Quanto comprar de cada perfil, em barras comerciais de 6 e 12 m.

    Todas as peças do mesmo perfil são cortadas juntas (assim a sobra de uma barra
    serve a outra peça), e entre a barra de 6 m e a de 12 m fica a que compra menos
    metro. Peças mais longas que 12 m são compradas em barras de 12 m com emenda, e
    isso é dito na observação.
    """
    fam: Dict[Tuple[str, str], dict] = {}
    for p in pecas:
        if p.comprimento_m <= 0 or not p.quantidade:
            continue
        k = (p.perfil, p.material)
        f = fam.setdefault(k, {"perfil": p.perfil, "material": p.material,
                               "itens": [], "peso_kg": 0.0, "kg_m": 0.0})
        f["itens"].append((p.comprimento_m, p.quantidade))
        f["peso_kg"] += p.peso_total_kg
        f["kg_m"] = f["kg_m"] or massa_kg_m(p.perfil)

    Lmax = max(COMPRIMENTOS_COMERCIAIS)
    saida = []
    for f in fam.values():
        necessario = sum(L * q for L, q in f["itens"])
        barras = {c: 0 for c in COMPRIMENTOS_COMERCIAIS}
        emendas = 0
        cortar: List[float] = []
        for L, q in f["itens"]:
            if L > Lmax:                          # peça maior que a barra: emenda
                barras[Lmax] += int(math.ceil(L / Lmax)) * q
                emendas += q
            else:
                cortar.extend([L] * int(q))
        if cortar:
            melhor = None
            for Lcom in COMPRIMENTOS_COMERCIAIS:
                n = _empacotar(cortar, Lcom)
                if n is None:
                    continue
                if melhor is None or n * Lcom < melhor[0] - 1e-9:
                    melhor = (n * Lcom, Lcom, n)
            if melhor is None:                    # nenhuma barra comercial serve
                barras[Lmax] += len(cortar)
            else:
                barras[melhor[1]] += melhor[2]
        comprado = sum(c * n for c, n in barras.items())
        perda = 100.0 * (comprado - necessario) / necessario if necessario else 0.0
        kg_m = f["kg_m"]
        obs = []
        if emendas:
            obs.append(f"{emendas} peça(s) acima de {fmt(Lmax, 0)} m — prever emenda")
        if perda > 35.0:
            obs.append("perda alta: avaliar compra em comprimento especial")
        saida.append({
            "perfil": f["perfil"], "material": f["material"],
            "kg_m": kg_m, "comprimento_m": necessario,
            "peso_kg": f["peso_kg"],
            "barras_6m": barras.get(6.0, 0), "barras_12m": barras.get(12.0, 0),
            "comprado_m": comprado, "peso_comprado_kg": comprado * kg_m,
            "perda_perc": perda, "observacao": "; ".join(obs),
        })
    saida.sort(key=lambda r: -r["peso_kg"])
    return saida


def consumo(projeto: ProjetoGalpao, pecas: Sequence[Peca]) -> dict:
    """Peso total, kg/m², área de pintura e volume de tinta por demão."""
    d = projeto.dados
    peso = sum(p.peso_total_kg for p in pecas)
    area_pint = sum(p.area_pintura_m2 for p in pecas)
    area_galv = sum(area_pintura_m2_m(p.perfil) * p.comprimento_m * p.quantidade
                    for p in pecas if p.area_pintura_m2 == 0 and p.comprimento_m > 0)
    demaos = []
    for nome, esp_um, solidos, perda in ESQUEMA_PINTURA:
        # espessura úmida = espessura seca / teor de sólidos; consumo prático inclui
        # a perda de aplicação (respingo, névoa, sobreposição)
        litros_m2 = (esp_um / 1000.0) / solidos * (1.0 + perda)
        demaos.append({"demao": nome, "espessura_seca_um": esp_um,
                       "solidos": solidos, "perda": perda,
                       "litros_m2": litros_m2, "litros": litros_m2 * area_pint})
    return {
        "peso_total_kg": peso,
        "area_coberta_m2": d.area_coberta,
        "kg_m2": peso / d.area_coberta if d.area_coberta else 0.0,
        "area_pintura_m2": area_pint,
        "area_galvanizada_m2": area_galv,
        "demaos": demaos,
        "tinta_total_l": sum(x["litros"] for x in demaos),
    }


def orcamento(projeto: ProjetoGalpao, peso_kg: float) -> dict:
    """Custo por parcela, a partir de `dados.custo_kg` e da repartição típica."""
    custo_kg = float(projeto.dados.custo_kg or 0.0)
    parcelas = []
    for nome, fracao, obs in REPARTICAO_CUSTO:
        rs_kg = custo_kg * fracao
        parcelas.append({"parcela": nome, "rs_kg": rs_kg, "valor": rs_kg * peso_kg,
                         "perc": 100.0 * fracao, "observacao": obs})
    total = sum(p["valor"] for p in parcelas)
    area = projeto.dados.area_coberta
    return {"custo_kg": custo_kg, "parcelas": parcelas, "total": total,
            "rs_m2": total / area if area else 0.0,
            "nota": "Valores indicativos (manual, Tabela 16.6): mercado brasileiro, "
                    "ordem de grandeza 2025–2026, sem impostos específicos e sem "
                    "telhas, fundações e piso. Não substitui cotação."}


# =====================================================================================
# 3. Montagem completa
# =====================================================================================

def montar(projeto: ProjetoGalpao) -> dict:
    """Romaneio, resumos, consumo e orçamento. Idempotente para o mesmo projeto."""
    cache = getattr(projeto, "_saida_lista", None)
    if cache is not None:
        return cache

    avisos: List[str] = []
    pecas = list(projeto.lista_material)
    if not pecas:
        pecas, avisos = montar_pecas(projeto)
        projeto.lista_material = pecas
        for a in avisos:
            if a not in projeto.avisos:
                projeto.avisos.append(a)

    for p in pecas:                              # completa o que veio sem peso
        if not p.peso_total_kg and p.comprimento_m and p.quantidade:
            kg_m = massa_kg_m(p.perfil)
            p.peso_unit_kg = round(kg_m * p.comprimento_m, 2)
            p.peso_total_kg = round(p.peso_unit_kg * p.quantidade, 1)
        if not p.area_pintura_m2 and p.comprimento_m and not _galvanizada(p.descricao):
            p.area_pintura_m2 = round(
                area_pintura_m2_m(p.perfil) * p.comprimento_m * p.quantidade, 2)

    cons = consumo(projeto, pecas)
    res_tipo = resumo_por_tipo(pecas, projeto.dados.area_coberta)
    res_perfil = compra_por_perfil(pecas)
    orc = orcamento(projeto, cons["peso_total_kg"])

    # idem para os pesos: o detalhamento por tipo entra sem apagar total_kg,
    # kg_por_m2 e area_pintura_m2, que vêm do orquestrador
    por_tipo = {r["tipo"]: round(r["peso_kg"], 1) for r in res_tipo}
    pesos = dict(projeto.resumo_pesos or {})
    pesos.update(por_tipo)
    pesos["total_kg"] = round(cons["peso_total_kg"], 1)
    pesos["TOTAL"] = round(cons["peso_total_kg"], 1)
    area = getattr(projeto.dados, "area_coberta", 0.0)
    if area:
        pesos["kg_por_m2"] = round(cons["peso_total_kg"] / area, 2)
    projeto.resumo_pesos = pesos
    # acrescenta o detalhamento por parcela sem apagar as chaves canônicas do
    # orquestrador (custo_kg, material, fabricacao, pintura, montagem, total, por_m2),
    # que a interface e o memorial leem
    detalhe = {p["parcela"]: round(p["valor"], 2) for p in orc["parcelas"]}
    detalhe["TOTAL"] = round(orc["total"], 2)
    base = dict(projeto.custo or {})
    base.setdefault("total", round(orc["total"], 2))
    base["parcelas"] = detalhe
    projeto.custo = base

    dados = {"pecas": pecas, "resumo_tipo": res_tipo, "resumo_perfil": res_perfil,
             "consumo": cons, "orcamento": orc, "avisos": avisos}
    try:
        projeto._saida_lista = dados
    except Exception:
        pass
    return dados


# =====================================================================================
# 4. CSV
# =====================================================================================

COLUNAS_ROMANEIO = ["Marca", "Descrição", "Perfil", "Material", "Quantidade",
                    "Comprimento (m)", "Peso unitário (kg)", "Peso total (kg)",
                    "Área de pintura (m²)", "Observação"]

COLUNAS_PERFIS = ["Perfil", "Material", "Massa (kg/m)", "Comprimento necessário (m)",
                  "Peso (kg)", "Barras de 6 m", "Barras de 12 m",
                  "Comprimento comprado (m)", "Peso comprado (kg)",
                  "Perda de corte (%)", "Observação"]

COLUNAS_ORCAMENTO = ["Parcela", "R$/kg", "Valor (R$)", "% do total", "Observação"]


def _grava_csv(caminho: str, colunas: Sequence[str], linhas: Sequence[Sequence]) -> str:
    """CSV com separador ';' e UTF-8 com BOM — abre direto no Excel brasileiro."""
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                       lineterminator="\r\n")
        w.writerow(colunas)
        for linha in linhas:
            w.writerow(linha)
    return os.path.abspath(caminho)


def _linhas_romaneio(pecas: Sequence[Peca]) -> List[list]:
    linhas = [[p.marca, p.descricao, p.perfil, p.material, p.quantidade,
               _num(p.comprimento_m, 3), _num(p.peso_unit_kg, 2),
               _num(p.peso_total_kg, 1), _num(p.area_pintura_m2, 2), p.observacao]
              for p in pecas]
    linhas.append(["", "TOTAL", "", "", "", "", "",
                   _num(sum(p.peso_total_kg for p in pecas), 1),
                   _num(sum(p.area_pintura_m2 for p in pecas), 2), ""])
    return linhas


# =====================================================================================
# 5. PDF
# =====================================================================================

def _esc(t) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _tabela(caption, colunas, linhas, classes="tab small", larguras=None) -> str:
    cols = ""
    if larguras:
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in larguras) + \
               "</colgroup>"
    th = "".join(f"<th>{_esc(c)}</th>" for c in colunas)
    corpo = []
    for linha in linhas:
        tds = []
        for cel in linha:
            if isinstance(cel, tuple):
                valor, cls = cel
            else:
                valor, cls = cel, ("r" if isinstance(cel, (int, float)) else "l")
            tds.append(f'<td class="{cls}">{_esc(valor)}</td>')
        corpo.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<table class="{classes}">'
            + (f"<caption>{_esc(caption)}</caption>" if caption else "")
            + cols + f"<thead><tr>{th}</tr></thead><tbody>"
            + "".join(corpo) + "</tbody></table>")


def _html(projeto: ProjetoGalpao, m: dict) -> str:
    d = projeto.dados
    pecas, cons, orc = m["pecas"], m["consumo"], m["orcamento"]
    hoje = date.today().strftime("%d/%m/%Y")

    cab = f"""
<div class="cabdoc">
  <h1 class="cap"><span class="tit">Lista de material e orçamento</span></h1>
  <table class="tab auto" style="font-size:9pt">
    <tbody>
      <tr><td class="l b" style="width:22%">Obra</td><td class="l">{_esc(d.nome)}</td>
          <td class="l b" style="width:18%">Cliente</td><td class="l">{_esc(d.cliente or '—')}</td></tr>
      <tr><td class="l b">Local</td><td class="l">{_esc(d.local or '—')}</td>
          <td class="l b">Data</td><td class="l">{hoje}</td></tr>
      <tr><td class="l b">Galpão</td>
          <td class="l">{fmt(d.vao, 1)} × {fmt(d.comprimento, 1)} m, pé-direito
              {fmt(d.pe_direito, 1)} m — {fmt(d.area_coberta, 0)} m²</td>
          <td class="l b">Responsável</td><td class="l">{_esc(d.responsavel or '—')}</td></tr>
    </tbody></table>
</div>"""

    romaneio = _tabela(
        "Quadro 1 — Romaneio por marca",
        ["Marca", "Descrição", "Perfil", "Material", "Qtd.", "Comp. (m)",
         "Peso un. (kg)", "Peso tot. (kg)", "Pintura (m²)"],
        [[(p.marca, "c b"), (p.descricao, "l"), (p.perfil, "l"), (p.material, "l"),
          (p.quantidade, "c"), (fmt(p.comprimento_m, 2) if p.comprimento_m else "—", "r"),
          (fmt(p.peso_unit_kg, 1), "r"), (fmt(p.peso_total_kg, 0), "r b"),
          (fmt(p.area_pintura_m2, 1) if p.area_pintura_m2 else "—", "r")]
         for p in pecas]
        + [[("", "c"), ("TOTAL", "l b"), ("", "l"), ("", "l"), ("", "c"), ("", "r"),
            ("", "r"), (fmt(cons["peso_total_kg"], 0), "r b"),
            (fmt(cons["area_pintura_m2"], 0), "r b")]],
        classes="tab small romaneio",
        larguras=["7%", "26%", "17%", "12%", "7%", "8%", "8%", "8%", "7%"])

    obs_rom = "".join(
        f"<li><b>{_esc(p.marca)}</b> — {_esc(p.observacao)}</li>"
        for p in pecas if p.observacao)
    if obs_rom:
        romaneio += ('<p class="pequeno"><b>Observações do romaneio</b></p>'
                     f'<ul class="pequeno">{obs_rom}</ul>')

    r_tipo = _tabela(
        "Quadro 2 — Resumo por tipo de peça",
        ["Tipo de peça", "Peso (kg)", "% do total", "kg/m²"],
        [[(r["tipo"], "l"), (fmt(r["peso_kg"], 0), "r"), (fmt(r["perc"], 1), "c"),
          (fmt(r["kg_m2"], 2), "r")] for r in m["resumo_tipo"]]
        + [[("TOTAL", "l b"), (fmt(cons["peso_total_kg"], 0), "r b"),
            ("100,0", "c b"), (fmt(cons["kg_m2"], 2), "r b")]],
        larguras=["52%", "16%", "16%", "16%"])

    r_perfil = _tabela(
        "Quadro 3 — Resumo de compra por perfil (barras comerciais de 6 e 12 m)",
        ["Perfil", "Material", "kg/m", "Necessário (m)", "Barras 6 m", "Barras 12 m",
         "Comprado (m)", "Peso comprado (kg)", "Perda de corte"],
        [[(r["perfil"], "l"), (r["material"], "l"), (fmt(r["kg_m"], 2), "r"),
          (fmt(r["comprimento_m"], 1), "r"), (r["barras_6m"], "c"),
          (r["barras_12m"], "c"), (fmt(r["comprado_m"], 1), "r"),
          (fmt(r["peso_comprado_kg"], 0), "r"), (fmt(r["perda_perc"], 1) + " %", "c")]
         for r in m["resumo_perfil"]],
        larguras=["19%", "13%", "7%", "11%", "8%", "8%", "11%", "12%", "11%"])

    linhas_tinta = [
        [(x["demao"], "l"), (fmt(x["espessura_seca_um"], 0) + " µm", "c"),
         (fmt(100 * x["solidos"], 0) + " %", "c"), (fmt(100 * x["perda"], 0) + " %", "c"),
         (fmt(x["litros_m2"], 3), "r"), (fmt(x["litros"], 0), "r")]
        for x in cons["demaos"]]
    tinta = _tabela(
        "Quadro 5 — Volume de tinta estimado por demão",
        ["Demão", "Espessura seca", "Sólidos (vol.)", "Perda de aplicação",
         "L/m²", "Volume (L)"],
        linhas_tinta + [[("TOTAL", "l b"), ("", "c"), ("", "c"), ("", "c"), ("", "r"),
                         (fmt(cons["tinta_total_l"], 0), "r b")]],
        larguras=["36%", "13%", "13%", "15%", "11%", "12%"])

    r_consumo = _tabela(
        "Quadro 4 — Resumo de consumo",
        ["Grandeza", "Valor"],
        [[("Peso total da estrutura", "l"), (br(cons["peso_total_kg"], 0) + " kg", "r")],
         [("Área coberta", "l"), (fmt(cons["area_coberta_m2"], 0) + " m²", "r")],
         [("Consumo de aço", "l"), (fmt(cons["kg_m2"], 1) + " kg/m²", "r")],
         [("Área a pintar (peças pintadas)", "l"),
          (fmt(cons["area_pintura_m2"], 0) + " m²", "r")],
         [("Área galvanizada (terças, longarinas, correntes)", "l"),
          (fmt(cons["area_galvanizada_m2"], 0) + " m²", "r")],
         [("Volume total de tinta (todas as demãos)", "l"),
          (fmt(cons["tinta_total_l"], 0) + " L", "r")]],
        larguras=["68%", "32%"])

    linhas_orc = [
        [(p["parcela"], "l"), (br(p["rs_kg"], 2), "r"),
         (br(p["valor"], 2), "r"), (fmt(p["perc"], 0) + " %", "c"),
         (p["observacao"], "l")] for p in orc["parcelas"]]
    linhas_orc.append([("TOTAL da estrutura", "l b"), (br(orc["custo_kg"], 2), "r b"),
                       (br(orc["total"], 2), "r b"), ("100 %", "c b"),
                       (f"≈ R$ {br(orc['rs_m2'], 0)}/m² de área coberta", "l b")])
    orcamento_html = _tabela(
        "Quadro 6 — Estimativa de custo da estrutura",
        COLUNAS_ORCAMENTO, linhas_orc,
        larguras=["27%", "9%", "14%", "8%", "42%"])

    avisos = ""
    lista_avisos = [a for a in projeto.avisos if a]
    if lista_avisos:
        avisos = ('<div class="box atencao"><div class="t">Avisos</div><ul>'
                  + "".join(f"<li>{_esc(a)}</li>" for a in lista_avisos) + "</ul></div>")

    return f"""{cab}
{avisos}
<h2>1. Romaneio por marca</h2>
{romaneio}
<h2>2. Resumo por tipo de peça</h2>
{r_tipo}
<h2>3. Resumo de compra por perfil</h2>
<p>Comprimentos comerciais de {fmt(COMPRIMENTOS_COMERCIAIS[0], 0)} e
{fmt(COMPRIMENTOS_COMERCIAIS[1], 0)} m. Para cada comprimento de peça adota-se a barra
que deixa a menor sobra, contando {fmt(PERDA_SERRA * 1000, 0)} mm de espessura de corte
por serrada. A coluna "perda de corte" é a diferença entre o que se compra e o que a
estrutura consome.</p>
{r_perfil}
<h2>4. Consumo e pintura</h2>
{r_consumo}
{tinta}
<p class="pequeno">Esquema de pintura adotado na estimativa (ISO 12944, categoria C3 —
manual, item 16.13): jateamento Sa 2½, primer epóxi 80 µm e acabamento poliuretano
acrílico alifático 60 µm. Terças, longarinas, correntes e parafusos entregues
galvanizados, e por isso fora da área a pintar.</p>
<h2>5. Orçamento</h2>
{orcamento_html}
<div class="box norma"><div class="t">Natureza dos valores</div>
<p>{_esc(orc['nota'])} A repartição por parcela segue a Tabela 16.6 do manual
(material {REPARTICAO_CUSTO[0][1] * 100:.0f} %, fabricação
{REPARTICAO_CUSTO[1][1] * 100:.0f} %, pintura {REPARTICAO_CUSTO[2][1] * 100:.0f} % e
montagem {REPARTICAO_CUSTO[3][1] * 100:.0f} %) aplicada sobre o custo unitário informado
no projeto, de R$ {br(orc['custo_kg'], 2)}/kg instalado.</p></div>
<p class="pequeno">Documento gerado em {hoje}. Quantidades de projeto básico: o romaneio
de fabricação prevalece sobre esta lista.</p>
"""


def gerar_pdf(projeto: ProjetoGalpao, pasta: str, m: Optional[dict] = None) -> str:
    """Grava a lista de material em PDF (mesma identidade visual do memorial)."""
    from . import printpdf
    m = m or montar(projeto)
    os.makedirs(os.path.abspath(pasta), exist_ok=True)
    css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "memorial.css"),
               encoding="utf-8").read()
    corpo = _html(projeto, m)
    doc = printpdf.envelope(f'<div class="lista-doc">{corpo}</div>', css,
                            f"Lista de material — {projeto.dados.nome}")
    doc = doc.replace("<body>", '<body class="lista">')
    # a lista não tem capa: o cabeçalho corrido recebe o nome da obra por CSS
    doc = doc.replace("</style>", f"""
.cabdoc .tit {{ string-set: capitulo content() }}
@page {{
  @top-left {{ content: "{_esc(projeto.dados.nome)}" }}
  @bottom-left {{ content: "Lista de material — quantidades de projeto básico; "
                           "o romaneio de fabricação prevalece." }}
  @bottom-right {{ content: counter(page) }}
}}
</style>""")
    html_path = os.path.join(pasta, "lista_material.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)
    pdf_path = os.path.join(pasta, "Lista_de_material.pdf")
    printpdf.imprimir(html_path, pdf_path)
    return os.path.abspath(pdf_path)


# =====================================================================================
# 6. Entrada do orquestrador
# =====================================================================================

def gerar(projeto: ProjetoGalpao, pasta: str) -> List[dict]:
    """Grava romaneio, resumos e orçamento em CSV e PDF. Devolve o que foi criado."""
    os.makedirs(os.path.abspath(pasta), exist_ok=True)
    m = montar(projeto)
    saida: List[dict] = []

    saida.append({"arquivo": _grava_csv(os.path.join(pasta, "romaneio.csv"),
                                        COLUNAS_ROMANEIO, _linhas_romaneio(m["pecas"])),
                  "titulo": "Romaneio por marca"})

    linhas = [[r["perfil"], r["material"], _num(r["kg_m"], 2),
               _num(r["comprimento_m"], 2), _num(r["peso_kg"], 1),
               r["barras_6m"], r["barras_12m"], _num(r["comprado_m"], 2),
               _num(r["peso_comprado_kg"], 1), _num(r["perda_perc"], 1),
               r["observacao"]] for r in m["resumo_perfil"]]
    saida.append({"arquivo": _grava_csv(os.path.join(pasta, "resumo-perfis.csv"),
                                        COLUNAS_PERFIS, linhas),
                  "titulo": "Resumo de compra por perfil"})

    orc = m["orcamento"]
    linhas = [[p["parcela"], _num(p["rs_kg"], 2), _num(p["valor"], 2),
               _num(p["perc"], 1), p["observacao"]] for p in orc["parcelas"]]
    linhas.append(["TOTAL", _num(orc["custo_kg"], 2), _num(orc["total"], 2),
                   "100,0", orc["nota"]])
    saida.append({"arquivo": _grava_csv(os.path.join(pasta, "orcamento.csv"),
                                        COLUNAS_ORCAMENTO, linhas),
                  "titulo": "Estimativa de custo"})

    try:
        saida.append({"arquivo": gerar_pdf(projeto, pasta, m),
                      "titulo": "Lista de material e orçamento (PDF)"})
    except Exception as e:                      # o PDF depende do Chrome; o CSV não
        projeto.avisos.append(f"Lista de material em PDF não gerada: {e}")
    return saida


if __name__ == "__main__":                      # python -m saida.lista_material [pasta]
    p = ProjetoGalpao(dados=DadosGalpao())
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_RAIZ, "projetos", "_lista")
    for item in gerar(p, destino):
        print(f"{item['titulo']:<44} {item['arquivo']}")
