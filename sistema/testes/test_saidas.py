# -*- coding: utf-8 -*-
"""Testes dos módulos de saída: memorial, pranchas e lista de material.

O teste monta um `ProjetoGalpao` de demonstração **completo e coerente** — o galpão
20 × 40 m, pé-direito 6 m, do Capítulo 16 do manual — usando os próprios módulos de
cálculo do sistema, de modo que todas as verificações saem com memória de cálculo real.
Esse projeto serve de exemplo para os demais módulos:

    from testes.test_saidas import projeto_demonstracao
    projeto = projeto_demonstracao()

Além de conferir que os arquivos existem e abrem, o teste renderiza as páginas em PNG
(`--png`) para a conferência visual:

    python testes/test_saidas.py            roda os testes
    python testes/test_saidas.py --png      gera tudo e grava os PNG das páginas
    python -m pytest testes/test_saidas.py -q
"""
import csv
import math
import os
import shutil
import sys
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo import analise as AN                              # noqa: E402
from nucleo import bases as BS                                # noqa: E402
from nucleo import cargas as CG                               # noqa: E402
from nucleo import ligacoes as LG                             # noqa: E402
from nucleo import materiais as mat                           # noqa: E402
from nucleo import nbr8800 as N8                              # noqa: E402
from nucleo import nbr14762 as N14                            # noqa: E402
from nucleo.base import Verificacao, fmt                      # noqa: E402
from nucleo.modelo_galpao import (DadosGalpao, ElementoDimensionado,  # noqa: E402
                                  ProjetoGalpao)
from nucleo.perfis import perfil                              # noqa: E402
from saida import lista_material, memorial, pranchas          # noqa: E402


# =====================================================================================
# Projeto de demonstração — galpão 20 × 40 m (manual, Capítulo 16)
# =====================================================================================

def dados_demonstracao() -> DadosGalpao:
    """Entrada do galpão-exemplo do Capítulo 16 do manual."""
    return DadosGalpao(
        nome="Galpão Industrial Modelo — Centro de Distribuição",
        cliente="Metalúrgica Exemplo Ltda.",
        local="Joinville — SC",
        responsavel="Eng.ª Civil Ana Paula Ribeiro",
        vao=20.0, comprimento=40.0, pe_direito=6.0,
        espacamento_porticos=5.0, inclinacao=10.0, balanco_lateral=0.0,
        tipo_portico="alma cheia", base_rotulada=True,
        com_misula=True, comprimento_misula=1.8,
        aco_perfis="ASTM A572 Gr.50", aco_tercas="CF-26 (NBR 6650)",
        aco_chapas="ASTM A36", parafuso="ASTM A325", eletrodo="E70XX",
        fck_MPa=25.0,
        telha="trapezoidal 0,50 mm", espacamento_tercas=1.6, linhas_correntes=1,
        fechamento_lateral="telha metálica", altura_fechamento=6.0,
        sobrecarga_cobertura=0.25, carga_forro=0.0, carga_extra=0.0,
        cidade="Joinville", v0=40.0, categoria_rugosidade="II", classe="B",
        fator_topografico=1.0, fator_estatistico=1.0,
        aberturas="duas faces opostas igualmente permeáveis",
        flecha_terca=180, flecha_viga=250, desloc_horizontal=300, custo_kg=17.0,
    ).validar()


def _cargas(projeto: ProjetoGalpao) -> dict:
    """Peso próprio e sobrecarga, com a composição parcela a parcela."""
    d = projeto.dados
    pp = CG.peso_proprio_cobertura(telha="telha metálica simples", com_tercas=True,
                                   com_acessorios=True)
    sc = CG.Composicao("Sobrecarga de cobertura", norma="NBR 8800:2008, item B.5.1")
    sc.add("sobrecarga mínima de cobertura", d.sobrecarga_cobertura,
           "NBR 8800:2008, item B.5.1 (0,25 kN/m²)")
    fech = CG.Composicao("Peso próprio do fechamento lateral")
    fech.add("telha trapezoidal 0,50 mm", 0.05, "NBR 6120:2019, Tabela 3")
    fech.add("longarinas Ue", 0.05, "estimativa de projeto (manual, Tabela 5.1)")
    return {
        "peso_proprio_cobertura": pp,
        "sobrecarga_cobertura": sc,
        "fechamento_lateral": fech,
        "peso_proprio_kN_m2": round(pp.total, 3),
        "sobrecarga_kN_m2": round(sc.total, 3),
        "carga_por_portico_permanente_kN_m": round(pp.total * d.espacamento_porticos, 3),
        "carga_por_portico_sobrecarga_kN_m": round(sc.total * d.espacamento_porticos, 3),
    }


def _vento(projeto: ProjetoGalpao) -> CG.VentoGalpao:
    d = projeto.dados
    # z = 10 m: altura de referência de S₂ adotada como no Capítulo 16 do manual
    # (item 16.2.2), a favor da segurança para um galpão de 7 m de cumeeira
    return CG.pressoes_galpao(b=d.vao, a=d.comprimento, h=d.pe_direito,
                              theta_graus=d.angulo_telhado, V0=d.v0,
                              categoria=d.categoria_rugosidade, classe=d.classe,
                              z=10.0, S1=d.fator_topografico, grupo=2,
                              aberturas="duas faces opostas")


#: Nomes das combinações, iguais nos casos de carga do modelo e no capítulo 4 do
#: memorial. Seguem as três combinações que governam um galpão leve (manual, Tabela
#: 16.3) mais as duas de serviço.
NOMES_COMBINACOES = {
    "C1": "C1 — gravidade",
    "C2": "C2 — sucção (peso próprio favorável)",
    "C3": "C3 — vento + gravidade",
    "S1": "S1 — serviço, flecha (rara)",
    "S2": "S2 — serviço, deslocamento horizontal (frequente)",
}


def _coeficientes():
    """γ_f e ψ de cada parcela, lidos do módulo de cargas (NBR 8800, Tabelas 1 e 2)."""
    return {
        "g_desf": CG.gama_f("permanente", "metálica"),
        "g_fav": CG.gama_f("permanente", "metálica", favoravel=True),
        "q": CG.gama_f("variavel", "sobrecarga"),
        "v": CG.gama_f("vento"),
        "psi0_q": CG.psi("cobertura")[0],
        "psi1_v": CG.psi("vento")[1],
    }


def _fatores_combinacoes():
    """Fator de cada ação em cada combinação: {combinação: {ação: fator}}."""
    c = _coeficientes()
    return {
        "C1": {"G": c["g_desf"], "Q": c["q"]},
        "C2": {"G": c["g_fav"], "V+0,2": c["v"]},
        "C3": {"G": c["g_desf"], "V−0,3": c["v"], "Q": c["q"] * c["psi0_q"]},
        "S1": {"G": 1.0, "Q": 1.0},
        "S2": {"G": 1.0, "V−0,3": c["psi1_v"]},
    }


def _combinacoes(g_k: float, q_k: float, v_k: float):
    """Objetos `Combinacao` do memorial, com o valor característico de cada ação.

    Os valores são as cargas por metro de pórtico (kN/m): `g_k` e `q_k` verticais,
    `v_k` a sucção normal ao telhado (negativa, porque alivia a gravidade).
    """
    c = _coeficientes()
    valores = {"G": g_k, "Q": q_k, "V+0,2": v_k, "V−0,3": v_k * 0.56}
    papeis = {"G": "permanente", "Q": "variável", "V+0,2": "vento",
              "V−0,3": "vento"}
    normas = {"G": "NBR 8800:2008, Tabela 1 (estrutura metálica)",
              "Q": "NBR 8800:2008, Tabelas 1 e 2 (sobrecarga de cobertura)",
              "V+0,2": "NBR 8800:2008, Tabela 1 (vento)",
              "V−0,3": "NBR 8800:2008, Tabela 1 (vento)"}
    principais = {"C1": "Sobrecarga", "C2": "Vento (sucção)",
                  "C3": "Vento (pressão nas paredes)", "S1": "Sobrecarga",
                  "S2": "Vento"}
    tipos = {"C1": "última normal", "C2": "última normal", "C3": "última normal",
             "S1": "serviço rara", "S2": "serviço frequente"}
    saida = []
    for chave, fatores in _fatores_combinacoes().items():
        parcelas = []
        for acao, fator in fatores.items():
            if acao == "G":
                gama, psi = fator, 1.0
                papel = ("permanente favorável" if abs(fator - c["g_fav"]) < 1e-9
                         else "permanente desfavorável")
            elif acao == "Q":
                gama = c["q"] if chave in ("C1", "C3") else 1.0
                psi = fator / gama if gama else 1.0
                papel = ("variável principal" if abs(psi - 1.0) < 1e-9
                         else "variável secundária (ψ₀)")
            else:
                gama = c["v"] if chave in ("C2", "C3") else 1.0
                psi = fator / gama if gama else 1.0
                papel = ("vento principal" if abs(psi - 1.0) < 1e-9
                         else "vento com ψ₁ (combinação frequente)")
            parcelas.append(CG.Parcela(f"{papeis[acao].capitalize()} — {acao}",
                                       gama, psi, valores[acao], papel,
                                       normas[acao]))
        saida.append(CG.Combinacao(NOMES_COMBINACOES[chave], tipos[chave], "+",
                                   principais[chave], parcelas))
    return saida


def _modelo_e_esforcos(projeto: ProjetoGalpao, g_k: float, q_k: float,
                       vento: CG.VentoGalpao):
    """Pórtico plano, combinações como casos de carga e envoltória.

    Cada caso de carga do modelo já é uma **combinação**: as ações entram
    multiplicadas pelo γ_f (e pelo ψ, quando é o caso), como na Tabela 16.3 do
    manual. Assim a envoltória sai direto em valores de cálculo, e as duas
    situações de C_pi (+0,2 e −0,3) nunca se misturam — cada uma é um carregamento
    fisicamente coerente.
    """
    d = projeto.dados
    pilar = perfil("W 360×44,6")
    viga = perfil("W 360×32,9")
    m = AN.portico_galpao(vao=d.vao * 100, pe_direito=d.pe_direito * 100,
                          inclinacao=d.inclinacao / 100.0, base_rotulada=True,
                          misula=(d.comprimento_misula * 100, 2.0),
                          pilar=pilar, viga=viga, nome="Pórtico transversal P1")
    barras_viga = m.dados["barras_viga"]
    e = d.espacamento_porticos
    peso_pilar = pilar.massa * 9.81e-3 + 0.10 * e        # kN/m (perfil + fechamento)

    # pressões efetivas por superfície, separadas por caso de C_pi (kN/m²)
    p = {}
    for rotulo, cpi in (("V+0,2", 0.2), ("V−0,3", -0.3)):
        p[rotulo] = {
            "telhado_bar": vento.pressao("telhado barlavento", "transversal", cpi),
            "telhado_sot": vento.pressao("telhado sotavento", "transversal", cpi),
            "parede_bar": vento.pressao("parede lateral barlavento", "transversal", cpi),
            "parede_sot": vento.pressao("parede lateral sotavento", "transversal", cpi),
        }

    def aplicar(caso: str, acao: str, fator: float):
        if acao in ("G", "Q"):
            q = (g_k if acao == "G" else q_k) * fator
            for b in barras_viga:
                m.distribuida(caso, b, -q / 100.0, "projetada_y")
            if acao == "G":
                for b in ("pilar_esq", "pilar_dir"):
                    m.distribuida(caso, b, -peso_pilar * fator / 100.0, "global_y")
        else:
            pr = p[acao]
            for b in barras_viga:
                pv = pr["telhado_bar"] if "esq" in b else pr["telhado_sot"]
                # sucção (pv < 0) é positiva no eixo local y, que aponta para fora
                m.distribuida(caso, b, -pv * e * fator / 100.0, "perpendicular")
            # as duas paredes empurram o pórtico no mesmo sentido (+x)
            m.distribuida(caso, "pilar_esq",
                          pr["parede_bar"] * e * fator / 100.0, "global_x")
            m.distribuida(caso, "pilar_dir",
                          -pr["parede_sot"] * e * fator / 100.0, "global_x")

    for chave, fatores in _fatores_combinacoes().items():
        caso = NOMES_COMBINACOES[chave]
        m.caso(caso)
        for acao, fator in fatores.items():
            aplicar(caso, acao, fator)

    elu = [NOMES_COMBINACOES[k] for k in ("C1", "C2", "C3")]
    env = AN.envoltoria(m, elu)
    servico = {k: AN.resolver(m, NOMES_COMBINACOES[k]) for k in ("S1", "S2")}
    return m, env, servico


def _elementos(projeto: ProjetoGalpao, env, vento: CG.VentoGalpao, servico,
               g_k: float, q_k: float):
    """Pilar, viga, terça e contraventamento verificados pelos módulos de cálculo."""
    d = projeto.dados
    aco = mat.aco(d.aco_perfis)
    elementos = []

    # ---- esforços de cálculo: a envoltória já é de combinações (ver acima) ----
    b_pilar = env.barra("pilar_esq")
    b_joelho = env.barra("misula_esq")           # trecho da mísula, junto ao joelho
    b_viga = env.barra("viga_esq")               # seção corrente W 360×32,9
    N_pilar = abs(b_pilar.absoluto("N").valor)
    M_pilar = abs(b_pilar.absoluto("M").valor)
    V_pilar = abs(b_pilar.absoluto("V").valor)
    M_joelho = abs(b_joelho.absoluto("M").valor)
    V_joelho = abs(b_joelho.absoluto("V").valor)
    M_viga = abs(b_viga.absoluto("M").valor)
    V_viga = abs(b_viga.absoluto("V").valor)
    N_viga = abs(b_viga.absoluto("N").valor)

    # ---- pilar: flexão composta, Kx = 2,0 (nós deslocáveis), Lb = 2,0 m ----
    H = d.pe_direito * 100.0
    r_pilar = N8.verificar_pilar("W 360×44,6", aco, N_Sd=N_pilar, Lx=H, Ly=H,
                                 Kx=2.0, Ky=1.0, Mx_Sd=M_pilar, Lb=200.0, Cb=1.0,
                                 elemento="Pilar P1")
    r_pilar.add(N8.cisalhamento(perfil("W 360×44,6"), aco, V_Sd=V_pilar))
    r_pilar.dados.update({
        "Kx adotado": 2.0, "Lb (cm)": 200.0,
        "travamento": "longarinas com mãos-francesas a cada 2,0 m",
        "N_Sd (kN)": round(N_pilar, 1), "Mx_Sd (kN·cm)": round(M_pilar, 0)})
    alternativas_pilar = _alternativas(
        ["W 310×38,7", "W 360×44,6", "W 360×51,0"],
        lambda p: N8.verificar_pilar(p, aco, N_Sd=N_pilar, Lx=H, Ly=H, Kx=2.0,
                                     Ky=1.0, Mx_Sd=M_pilar, Lb=200.0))
    elementos.append(ElementoDimensionado(
        nome="Pilar do pórtico", perfil="W 360×44,6", material=d.aco_perfis,
        resultado=r_pilar,
        esforcos={"N_Sd (kN)": round(N_pilar, 1),
                  "Mx_Sd (kN·m)": round(M_pilar / 100, 1),
                  "V_Sd (kN)": round(V_pilar, 1)},
        geometria={"Altura (cm)": H, "Kx": 2.0, "Ky": 1.0, "Lb (cm)": 200.0},
        alternativas=alternativas_pilar))

    # ---- viga do pórtico: flexão composta com a mísula ----
    Lb_viga = 320.0            # terças a cada 1,60 m travam a mesa superior
    r_viga = N8.flexao_composta("W 360×32,9", aco, N_Sd=N_viga, Mx_Sd=M_viga,
                                tipo_axial="compressao",
                                Lx=d.comprimento_agua * 100, Ly=Lb_viga,
                                Kx=1.0, Ky=1.0, Lb=Lb_viga, Cb=1.14,
                                elemento="Viga do pórtico V1")
    r_viga.add(N8.cisalhamento(perfil("W 360×32,9"), aco, V_Sd=V_viga))
    flecha_lim = d.vao * 100 / d.flecha_viga
    # flecha na cumeeira, lida da combinação de serviço S1 do próprio pórtico
    flecha_s1 = abs(servico["S1"].deslocamento("C")[1])
    v_flecha = Verificacao(
        "Flecha vertical da cumeeira (ELS)",
        norma="NBR 8800:2008, Anexo C (combinação rara de serviço)",
        Sd=flecha_s1, Rd=flecha_lim, unidade="cm")
    v_flecha.passo("Flecha da combinação S1 (G + Q), lida do pórtico plano",
                   formula="δ = deslocamento vertical do nó C",
                   conta=f"análise matricial, caso "
                         f"«{NOMES_COMBINACOES['S1']}»",
                   valor=fmt(flecha_s1, 2, "cm"),
                   norma="método da rigidez (nucleo/analise.py)")
    v_flecha.passo("Limite adotado",
                   formula=f"δ<sub>lim</sub> = L/{d.flecha_viga}",
                   conta=f"{fmt(d.vao * 100, 0)}/{d.flecha_viga}",
                   valor=fmt(flecha_lim, 2, "cm"),
                   norma="NBR 8800:2008, Tabela C.1")
    r_viga.add(v_flecha)
    r_viga.dados.update({"Lb (cm)": Lb_viga, "Cb": 1.14,
                         "mísula (m)": d.comprimento_misula,
                         "flecha limite (cm)": round(flecha_lim, 2)})
    alternativas_viga = _alternativas(
        ["W 310×28,3", "W 360×32,9", "W 410×38,8"],
        lambda p: N8.flexao_composta(p, aco, N_Sd=N_viga, Mx_Sd=M_viga,
                                     Lx=d.comprimento_agua * 100, Ly=Lb_viga,
                                     Lb=Lb_viga, Cb=1.14))
    elementos.append(ElementoDimensionado(
        nome="Viga do pórtico (rafter)", perfil="W 360×32,9", material=d.aco_perfis,
        resultado=r_viga,
        esforcos={"Mx_Sd (kN·m)": round(M_viga / 100, 1),
                  "V_Sd (kN)": round(V_viga, 1), "N_Sd (kN)": round(N_viga, 1)},
        geometria={"Vão inclinado (m)": round(d.comprimento_agua, 2),
                   "Lb (cm)": Lb_viga, "Mísula (m)": d.comprimento_misula},
        alternativas=alternativas_viga))

    # ---- terça: NBR 14762, gravidade e sucção ----
    succao = abs(vento.critica().p)
    q_grav = (0.15 + d.sobrecarga_cobertura) * d.espacamento_tercas * 1.4
    q_suc = succao * d.espacamento_tercas * 1.4 - 0.15 * d.espacamento_tercas * 1.0
    r_terca = N14.terca("Ue 200×75×20×2,65", d.aco_tercas,
                        vao=d.espacamento_porticos,
                        carga_gravidade=q_grav, carga_succao=max(q_suc, 0.1),
                        n_correntes=d.linhas_correntes,
                        inclinacao=d.angulo_telhado,
                        limite_flecha_gravidade=float(d.flecha_terca),
                        elemento="Terça T1")
    alternativas_terca = _alternativas(
        ["Ue 150×60×20×2,65", "Ue 200×75×20×2,65", "Ue 250×85×25×3,00"],
        lambda p: N14.terca(p, d.aco_tercas, vao=d.espacamento_porticos,
                            carga_gravidade=q_grav, carga_succao=max(q_suc, 0.1),
                            n_correntes=d.linhas_correntes,
                            inclinacao=d.angulo_telhado))
    elementos.append(ElementoDimensionado(
        nome="Terça de cobertura", perfil="Ue 200×75×20×2,65",
        material=d.aco_tercas, resultado=r_terca,
        esforcos={"q gravidade (kN/m)": round(q_grav, 3),
                  "q sucção (kN/m)": round(max(q_suc, 0.1), 3),
                  "sucção de projeto (kN/m²)": round(succao, 3)},
        geometria={"Vão (m)": d.espacamento_porticos,
                   "Espaçamento (m)": d.espacamento_tercas,
                   "Linhas de correntes": d.linhas_correntes},
        alternativas=alternativas_terca))

    # ---- contraventamento de cobertura: barra redonda tracionada ----
    N_diag = 66.8              # kN — manual, item 16.10(d)
    L_diag = math.hypot(d.espacamento_porticos, d.pe_direito) * 100
    # as duas diagonais do X são parafusadas no cruzamento: o comprimento de
    # referência da esbeltez é a metade da diagonal (manual, item 16.10(d))
    L_esbeltez = L_diag / 2.0
    p_diag = perfil('L 3"×1/4"')
    r_contrav = N8.tracao(p_diag, mat.aco("ASTM A36"), N_Sd=N_diag, L=L_esbeltez,
                          n_furos=1, d_furo=2.1, Ct=0.80,
                          elemento="Diagonal do contraventamento vertical")
    v_comp = N8.compressao(p_diag, mat.aco("ASTM A36"), Lx=L_esbeltez,
                           Ly=L_esbeltez, N_Sd=0.0,
                           elemento="Diagonal comprimida").verificacoes[-1]
    v_comp.observacao = (
        "No X de contraventamento a diagonal comprimida é desprezada (N_Sd = 0): "
        "admite-se que ela flamba e que toda a força vai para a diagonal tracionada, "
        "hipótese usual e a favor da segurança para barras esbeltas (manual, item "
        "16.10).")
    r_contrav.add(v_comp)
    r_contrav.dados.update({
        "esbeltez limite (tração)": 300.0,
        "L da diagonal (cm)": round(L_diag, 1),
        "L de referência da esbeltez (cm)": round(L_esbeltez, 1),
        "observação": "diagonais parafusadas no cruzamento do X"})
    elementos.append(ElementoDimensionado(
        nome="Contraventamento vertical", perfil='L 3"×1/4"',
        material="ASTM A36", resultado=r_contrav,
        esforcos={"N_Sd (kN)": N_diag},
        geometria={"Comprimento (m)": round(L_diag / 100, 2),
                   "Ângulo com a horizontal (°)":
                       round(math.degrees(math.atan(d.pe_direito
                                                    / d.espacamento_porticos)), 1)},
        alternativas=_alternativas(
            ['L 2½"×1/4"', 'L 3"×1/4"', 'L 3"×5/16"'],
            lambda p: N8.tracao(p, mat.aco("ASTM A36"), N_Sd=N_diag,
                                L=L_esbeltez, n_furos=1, d_furo=2.1, Ct=0.80))))
    return elementos, M_joelho, V_joelho, N_pilar, M_pilar


def _alternativas(nomes, verificar):
    """Tabela de perfis testados, no formato que o memorial imprime."""
    saida = []
    for nome in nomes:
        try:
            r = verificar(nome)
            c = r.critica
            p = perfil(nome)
            saida.append({"perfil": nome, "massa (kg/m)": p.massa,
                          "aproveitamento (S_d/R_d)": round(r.razao, 3),
                          "atende": "sim" if r.ok else "não",
                          "verificação que governa": c.titulo if c else "—"})
        except Exception as e:                    # perfil fora do catálogo, etc.
            saida.append({"perfil": nome, "massa (kg/m)": None,
                          "aproveitamento (S_d/R_d)": None,
                          "atende": "—",
                          "verificação que governa": f"não verificado: {e}"})
    return saida


def _ligacoes_e_base(projeto: ProjetoGalpao, M_joelho, V_joelho, N_pilar, M_pilar,
                     env):
    d = projeto.dados
    viga = perfil("W 360×32,9")
    # no joelho a seção é a da mísula: altura da viga mais a altura da mísula
    # (o corte diagonal de uma peça igual à viga), como no desenho 04
    misula = {"nome": "Mísula (W 360×32,9 + meia peça)",
              "d": viga.d * 2.0, "bf": viga.bf, "tw": viga.tw, "tf": viga.tf,
              "A": viga.A, "Ix": viga.Ix, "Zx": viga.Zx, "Wx": viga.Wx}
    ligacoes = {}
    ligacoes["viga-pilar"] = LG.chapa_de_topo(
        misula, M_Sd=M_joelho, V_Sd=V_joelho, diametro='3/4"',
        parafuso=d.parafuso, n_por_linha=2, linhas_tracionadas=2, t_chapa=2.54,
        aco_chapa=d.aco_chapas, aco_viga=d.aco_perfis, pilar="W 360×44,6",
        aco_pilar=d.aco_perfis, eletrodo=d.eletrodo,
        elemento="Ligação viga–pilar com chapa de topo (joelho)")
    b_cum = env.barra("viga_esq")
    ligacoes["cumeeira"] = LG.chapa_de_topo(
        "W 360×32,9", M_Sd=abs(b_cum.absoluto("M").valor),
        V_Sd=abs(b_cum.absoluto("V").valor), diametro='3/4"',
        parafuso=d.parafuso, n_por_linha=2, linhas_tracionadas=2, t_chapa=2.54,
        aco_chapa=d.aco_chapas, aco_viga=d.aco_perfis, eletrodo=d.eletrodo,
        elemento="Ligação de cumeeira com chapa de topo")
    ligacoes["contraventamento"] = LG.gusset_contraventamento(
        N_Sd=66.8, t_gusset=0.95, largura_ligacao=7.62, comprimento_ligacao=7.0,
        aco_gusset=d.aco_chapas, diametro='3/4"', parafuso=d.parafuso,
        n_parafusos=2, t_barra=0.635, aco_barra=d.aco_chapas,
        elemento="Chapa gusset do contraventamento vertical")

    reacao = env.reacao("A")
    N_base = max(reacao["Ry_max"].valor, 1.0)
    N_base_min = min(reacao["Ry_min"].valor, 0.0)
    H_base = max(abs(reacao["Rx_max"].valor), abs(reacao["Rx_min"].valor))
    base = BS.dimensionar_base("W 360×44,6", N_Sd=N_base, M_Sd=0.0, H_Sd=H_base,
                               N_Sd_min=N_base_min, fck=d.fck_MPa / 10.0,
                               pedestal=(60.0, 70.0), aco_placa=d.aco_chapas,
                               diametro_chumbador='3/4"', n_chumbadores=2,
                               B=30.0, L=40.0)
    if getattr(base, "elemento", ""):
        base.elemento = "Base rotulada do pilar P1"

    _enrijecedores_do_pilar(ligacoes["viga-pilar"], M_joelho, d)
    return ligacoes, base


def _enrijecedores_do_pilar(resultado, M_Sd: float, d: DadosGalpao,
                            t_enr: float = 1.0):
    """Enrijecedores do pilar no joelho, alinhados com as mesas da viga.

    `ligacoes.chapa_de_topo` verifica a mesa e a alma do pilar **sem** enrijecedor e
    avisa quando eles são necessários — é o caso aqui. O detalhe adotado (desenho
    04) tem enrijecedores de 10 mm nos dois níveis; esta função acrescenta a
    verificação deles e dispensa as verificações sem enrijecedor, deixando-as no
    memorial com a observação de por que não se aplicam.
    """
    pilar = perfil("W 360×44,6")
    viga = perfil("W 360×32,9")
    aco = mat.aco(d.aco_perfis)
    braco = (2.0 * viga.d - viga.tf) / 10.0               # cm — altura da mísula
    T = M_Sd / braco
    b_enr = (pilar.bf / 10.0 - pilar.tw / 10.0) / 2.0 - 1.0   # cm, com recorte de 10 mm
    A_enr = 2.0 * b_enr * t_enr
    from nucleo.base import GAMA_A1
    Rd = A_enr * aco.fy / GAMA_A1
    v = Verificacao("Enrijecedores do pilar alinhados com as mesas da viga",
                    norma="NBR 8800:2008, item 5.7.7", Sd=T, Rd=Rd, unidade="kN")
    v.passo("Força transmitida pela mesa da viga",
            formula="T = M<sub>Sd</sub>/(d − t<sub>f</sub>)",
            conta=f"{fmt(M_Sd, 0)}/{fmt(braco, 1)}", valor=fmt(T, 1, "kN"),
            norma="binário das mesas (item 8.6.3 do manual)")
    v.passo("Área dos dois enrijecedores",
            formula="A<sub>enr</sub> = 2·b<sub>enr</sub>·t<sub>enr</sub>",
            conta=f"2·{fmt(b_enr, 1)}·{fmt(t_enr, 1)}",
            valor=fmt(A_enr, 1, "cm²"),
            norma=f"chapa {fmt(t_enr * 10, 0)} mm em cada lado da alma")
    v.passo("Resistência ao escoamento dos enrijecedores",
            formula="R<sub>d</sub> = A<sub>enr</sub>·f<sub>y</sub>/γ<sub>a1</sub>",
            conta=f"{fmt(A_enr, 1)}·{fmt(aco.fy, 1)}/{fmt(GAMA_A1, 2)}",
            valor=fmt(Rd, 0, "kN"), norma="NBR 8800:2008, item 5.7.7")
    v.observacao = ("Com os enrijecedores a força da mesa da viga é transferida "
                    "diretamente às mesas do pilar; as verificações de força "
                    "localizada sem enrijecedor deixam de governar.")
    resultado.add(v)
    for antiga in resultado.verificacoes:
        if antiga is v:
            continue
        if any(chave in antiga.titulo.lower() for chave in
               ("mesa do pilar", "alma do pilar", "painel de alma do pilar")):
            antiga.dispensada = True
            antiga.observacao = (
                (antiga.observacao + " ") if antiga.observacao else ""
            ) + ("Não se aplica ao detalhe adotado: há enrijecedores de "
                 f"{fmt(t_enr * 10, 0)} mm alinhados com as duas mesas da viga "
                 "(ver a verificação dos enrijecedores, adiante, e o desenho da "
                 "ligação). O valor calculado acima é o do pilar sem enrijecedor, "
                 "e está no memorial para mostrar por que eles são obrigatórios.")
    resultado.dados["enrijecedores_mm"] = t_enr * 10
    return resultado


def projeto_demonstracao() -> ProjetoGalpao:
    """Galpão 20 × 40 m completo: cargas, vento, combinações, esforços e elementos."""
    projeto = ProjetoGalpao(dados=dados_demonstracao())
    d = projeto.dados

    projeto.cargas = _cargas(projeto)
    vento = _vento(projeto)
    projeto.vento = {"galpao": vento, "V0 (m/s)": vento.V0, "S2": round(vento.S2, 3),
                     "Vk (m/s)": round(vento.Vk, 2), "q (kN/m²)": round(vento.q, 3),
                     "maior sucção (kN/m²)": round(vento.critica().p, 3)}

    pp = projeto.cargas["peso_proprio_kN_m2"]
    sc = projeto.cargas["sobrecarga_kN_m2"]
    # carga vertical por metro de pórtico: cobertura + peso próprio do rafter
    g_k = pp * d.espacamento_porticos + perfil("W 360×32,9").massa * 9.81e-3
    q_k = sc * d.espacamento_porticos
    v_k = vento.critica().p * d.espacamento_porticos
    projeto.cargas["g_k por pórtico (kN/m)"] = round(g_k, 3)
    projeto.cargas["q_k por pórtico (kN/m)"] = round(q_k, 3)
    projeto.cargas["sucção característica no telhado (kN/m)"] = round(v_k, 3)
    projeto.combinacoes = _combinacoes(g_k, q_k, v_k)

    modelo, env, servico = _modelo_e_esforcos(projeto, g_k, q_k, vento)
    desloc_h = abs(servico["S2"].deslocamento("B")[0])
    flecha_c = abs(servico["S1"].deslocamento("C")[1])
    lim_h = d.pe_direito * 100 / d.desloc_horizontal
    lim_f = d.vao * 100 / d.flecha_viga
    projeto.esforcos = {
        "envoltoria": env,
        "modelo": modelo,
        "servico": servico,
        "Deslocamento horizontal do joelho (S2, ψ₁ = 0,3) (cm)": round(desloc_h, 2),
        "Limite H/%d (cm)" % d.desloc_horizontal: round(lim_h, 2),
        "Deslocamento horizontal: situação":
            "atende" if desloc_h <= lim_h else "NÃO ATENDE",
        "Flecha vertical da cumeeira (S1) (cm)": round(flecha_c, 2),
        "Limite L/%d (cm)" % d.flecha_viga: round(lim_f, 2),
        "Flecha: situação": "atende" if flecha_c <= lim_f else "NÃO ATENDE",
        "Combinações analisadas (ELU)": ", ".join(env.casos),
    }

    elementos, M_joelho, V_joelho, N_pilar, M_pilar = _elementos(
        projeto, env, vento, servico, g_k, q_k)
    projeto.elementos = elementos
    projeto.ligacoes, projeto.base = _ligacoes_e_base(
        projeto, M_joelho, V_joelho, N_pilar, M_pilar, env)

    lista_material.montar(projeto)          # preenche lista, pesos e custo
    projeto.avisos.append(
        "Projeto de demonstração: os esforços vêm de uma análise de 1ª ordem do "
        "pórtico plano, sem amplificação B1/B2 e sem ponte rolante.")
    return projeto


# =====================================================================================
# Testes
# =====================================================================================

_SAIDAS = {}


def saidas() -> dict:
    """Gera memorial, pranchas e lista **uma única vez** para todos os testes.

    Gerar o memorial custa alguns segundos (o Chrome precisa paginar o documento
    inteiro), então o resultado fica em cache no módulo; a pasta temporária é
    apagada no fim da sessão, a menos que se passe `--manter`.
    """
    if _SAIDAS:
        return _SAIDAS
    pasta = tempfile.mkdtemp(prefix="saidas_galpao_")
    projeto = projeto_demonstracao()
    _SAIDAS.update(
        pasta=pasta,
        projeto=projeto,
        lista=lista_material.gerar(projeto, os.path.join(pasta, "lista")),
        pranchas=pranchas.gerar(projeto, os.path.join(pasta, "pranchas")),
        memorial=memorial.gerar(projeto, os.path.join(pasta, "memorial")),
    )
    if "--manter" not in sys.argv:
        import atexit
        atexit.register(shutil.rmtree, pasta, True)
    else:
        print(f"saídas mantidas em {pasta}")
    return _SAIDAS


class BaseSaidas(unittest.TestCase):
    """Compartilha as saídas geradas uma única vez entre todas as classes."""

    @classmethod
    def setUpClass(cls):
        s = saidas()
        cls.pasta = s["pasta"]
        cls.projeto = s["projeto"]
        cls.lista_gerada = s["lista"]
        cls.pranchas_geradas = s["pranchas"]
        cls.memorial_pdf = s["memorial"]


class TestProjetoDemonstracao(BaseSaidas):

    def test_projeto_coerente(self):
        p = self.projeto
        self.assertEqual(len(p.elementos), 4)
        self.assertEqual(len(p.ligacoes), 3)
        self.assertIsNotNone(p.base)
        for e in p.elementos:
            self.assertIsNotNone(e.resultado, e.nome)
            self.assertTrue(e.resultado.verificacoes, e.nome)
            passos = sum(len(v.passos) for v in e.resultado.verificacoes)
            self.assertGreater(passos, 5, f"{e.nome} sem memória de cálculo")
        self.assertTrue(p.combinacoes)
        self.assertIn("envoltoria", p.esforcos)
        self.assertGreater(p.peso_total_kg, 10000)
        self.assertTrue(15 < p.consumo_kg_m2 < 45,
                        f"kg/m² fora da faixa esperada: {p.consumo_kg_m2}")

    def test_vento_bate_com_o_manual(self):
        """Cap. 16, item 16.2.2: q ≈ 0,94 kN/m² para V₀ = 40 m/s."""
        v = self.projeto.vento["galpao"]
        self.assertAlmostEqual(v.q, 0.94, delta=0.06)


class TestMemorial(BaseSaidas):

    def test_pdf_existe_e_abre(self):
        import pymupdf
        self.assertTrue(os.path.isfile(self.memorial_pdf))
        tamanho = os.path.getsize(self.memorial_pdf)
        self.assertGreater(tamanho, 120 * 1024, "memorial pequeno demais")
        doc = pymupdf.open(self.memorial_pdf)
        try:
            self.assertGreaterEqual(doc.page_count, 25,
                                    "memorial curto demais para ser auditável")
            self.assertLessEqual(doc.page_count, 200)
            # a capa tem de trazer a identificação da obra
            capa = doc[0].get_text()
            self.assertIn("Memorial de cálculo", capa)
            self.assertIn(self.projeto.dados.cliente, capa)
            # nenhuma página em branco
            vazias = [i + 1 for i, pg in enumerate(doc)
                      if len(pg.get_text().strip()) < 5 and not pg.get_drawings()]
            self.assertFalse(vazias, f"páginas em branco: {vazias}")
        finally:
            doc.close()

    def test_conteudo_obrigatorio(self):
        import pymupdf
        doc = pymupdf.open(self.memorial_pdf)
        try:
            texto = "\n".join(pg.get_text() for pg in doc)
        finally:
            doc.close()
        for termo in ("Sumário", "Dados de entrada", "Normas adotadas",
                      "Ações e cargas", "Combinações de ações",
                      "Esforços solicitantes", "Dimensionamento dos elementos",
                      "Ligações e base", "Lista de material",
                      "Conclusão", "CREA", "ART",
                      "NBR 8800", "NBR 6123", "NBR 14762"):
            self.assertIn(termo, texto, f"falta '{termo}' no memorial")
        # a memória de cálculo tem de estar lá, passo a passo
        # o CSS imprime o cabeçalho em maiúsculas, então a busca ignora a caixa
        self.assertIn("com os números", texto.lower())
        for e in self.projeto.elementos:
            self.assertIn(e.perfil.split()[0], texto)

    def test_nada_estoura_a_margem(self):
        """Nenhum bloco de texto pode passar da margem útil da página A4."""
        import pymupdf
        doc = pymupdf.open(self.memorial_pdf)
        try:
            estouros = []
            for i, pg in enumerate(doc):
                larg = pg.rect.width
                limite_dir = larg - 8.0 * 72 / 25.4      # margem de 16 mm, 8 de folga
                for bloco in pg.get_text("blocks"):
                    x0, y0, x1, y1 = bloco[:4]
                    if x1 > limite_dir + 1 or x0 < 4:
                        estouros.append((i + 1, round(x0, 1), round(x1, 1),
                                         bloco[4][:40].replace("\n", " ")))
            self.assertFalse(estouros[:6], f"texto fora da margem: {estouros[:6]}")
        finally:
            doc.close()


class TestPranchas(BaseSaidas):

    def test_arquivos_e_formatos(self):
        import pymupdf
        self.assertGreaterEqual(len(self.pranchas_geradas), 4)
        formatos = set()
        for item in self.pranchas_geradas:
            self.assertTrue(os.path.isfile(item["arquivo"]), item)
            self.assertGreater(os.path.getsize(item["arquivo"]), 8 * 1024)
            doc = pymupdf.open(item["arquivo"])
            try:
                self.assertEqual(doc.page_count, 1)
                pg = doc[0]
                larg = pg.rect.width / 72 * 25.4
                alt = pg.rect.height / 72 * 25.4
                esperado = pranchas.FOLHAS[item["formato"]]
                self.assertAlmostEqual(larg, esperado[0], delta=1.0)
                self.assertAlmostEqual(alt, esperado[1], delta=1.0)
                formatos.add(item["formato"])
                texto = pg.get_text()
                for termo in ("OBRA", "CLIENTE", "TÍTULO DO DESENHO", "ESCALA",
                              "PRANCHA", "REV.", "RESPONSÁVEL TÉCNICO", "CREA",
                              "engenheiro habilitado"):
                    self.assertIn(termo, texto,
                                  f"carimbo sem '{termo}' em {item['arquivo']}")
                self.assertIn(self.projeto.dados.nome[:20], texto)
            finally:
                doc.close()
        # pranchas gerais em A1; o nó de contraventamento sobe do A3 declarado para o
        # A2, porque o tirante é cotado em 1:5
        self.assertIn("A1", formatos)
        self.assertTrue(formatos <= set(pranchas.FORMATOS_EMITIDOS), formatos)
        self.assertGreaterEqual(len(formatos), 2, formatos)

    def test_desenho_dentro_da_folha(self):
        """Nada pode ser desenhado fora do quadro da prancha."""
        import pymupdf
        for item in self.pranchas_geradas:
            doc = pymupdf.open(item["arquivo"])
            try:
                pg = doc[0]
                W, H = pg.rect.width, pg.rect.height
                margem = 4.0 * 72 / 25.4        # 4 mm de tolerância
                fora = []
                for bloco in pg.get_text("blocks"):
                    x0, y0, x1, y1 = bloco[:4]
                    if x0 < margem - 1 or x1 > W - margem + 1 or \
                            y0 < margem - 1 or y1 > H - margem + 1:
                        fora.append(bloco[4][:30].replace("\n", " "))
                self.assertFalse(fora[:5],
                                 f"{os.path.basename(item['arquivo'])}: {fora[:5]}")
            finally:
                doc.close()

    def test_escala_real(self):
        """Uma prancha 1:100 tem de ter o desenho na medida certa da folha."""
        tmp = tempfile.mkdtemp(prefix="prancha_escala_")
        try:
            from saida.dxf import Desenho
            d = Desenho("quadrado")
            d.retangulo(0.0, 0.0, 10000.0, 5000.0)      # 10 × 5 m
            v = pranchas.Vista(d, "Quadrado de teste", 100.0, "TESTE")
            caminho = os.path.join(tmp, "escala.pdf")
            r = pranchas.prancha([v], caminho, "A1",
                                 pranchas._info_base(self.projeto, "Teste", "01/01"))
            self.assertEqual(r["escala"], "1:100")
            import pymupdf
            doc = pymupdf.open(caminho)
            try:
                # o retângulo de 10 000 mm em 1:100 mede 100 mm na folha
                larguras = []
                for caminho_desenho in doc[0].get_drawings():
                    r_ = caminho_desenho["rect"]
                    larguras.append(round(r_.width / 72 * 25.4, 1))
                self.assertTrue(any(abs(x - 100.0) < 1.5 for x in larguras),
                                f"nenhum traço com 100 mm na folha: {larguras}")
            finally:
                doc.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestListaMaterial(BaseSaidas):

    def test_arquivos_gerados(self):
        nomes = {os.path.basename(i["arquivo"]) for i in self.lista_gerada}
        for esperado in ("romaneio.csv", "resumo-perfis.csv", "orcamento.csv",
                         "Lista_de_material.pdf"):
            self.assertIn(esperado, nomes, f"falta {esperado}")
        for item in self.lista_gerada:
            self.assertTrue(os.path.isfile(item["arquivo"]))
            self.assertGreater(os.path.getsize(item["arquivo"]), 200)

    def test_csv_abre_com_as_colunas_certas(self):
        caminho = [i["arquivo"] for i in self.lista_gerada
                   if i["arquivo"].endswith("romaneio.csv")][0]
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0], lista_material.COLUNAS_ROMANEIO)
        self.assertGreater(len(linhas), 8)
        self.assertEqual(linhas[-1][1], "TOTAL")
        for linha in linhas[1:-1]:
            self.assertEqual(len(linha), len(lista_material.COLUNAS_ROMANEIO))
            self.assertTrue(linha[0], "marca vazia no romaneio")
        # números no padrão brasileiro (vírgula decimal)
        self.assertIn(",", linhas[1][7])

        caminho = [i["arquivo"] for i in self.lista_gerada
                   if i["arquivo"].endswith("resumo-perfis.csv")][0]
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0], lista_material.COLUNAS_PERFIS)
        self.assertGreater(len(linhas), 3)

        caminho = [i["arquivo"] for i in self.lista_gerada
                   if i["arquivo"].endswith("orcamento.csv")][0]
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0], lista_material.COLUNAS_ORCAMENTO)
        self.assertEqual(linhas[-1][0], "TOTAL")

    def test_bom_utf8(self):
        caminho = [i["arquivo"] for i in self.lista_gerada
                   if i["arquivo"].endswith("romaneio.csv")][0]
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(3), b"\xef\xbb\xbf")

    def test_compra_cobre_o_necessario(self):
        m = lista_material.montar(self.projeto)
        for r in m["resumo_perfil"]:
            self.assertGreaterEqual(r["comprado_m"] + 1e-6, r["comprimento_m"],
                                    f"{r['perfil']}: compra menor que o necessário")
            self.assertGreaterEqual(r["perda_perc"], -1e-6)

    def test_pdf_da_lista(self):
        import pymupdf
        caminho = [i["arquivo"] for i in self.lista_gerada
                   if i["arquivo"].endswith(".pdf")][0]
        doc = pymupdf.open(caminho)
        try:
            self.assertGreaterEqual(doc.page_count, 2)
            texto = "\n".join(pg.get_text() for pg in doc)
        finally:
            doc.close()
        for termo in ("Romaneio por marca", "Resumo de compra por perfil",
                      "Orçamento", "kg/m²", "Volume de tinta"):
            self.assertIn(termo, texto, f"falta '{termo}' na lista em PDF")


# =====================================================================================
# Conferência visual
# =====================================================================================

def gerar_png(destino: str = None) -> str:
    """Gera tudo e grava os PNG das páginas, para conferência visual."""
    import pymupdf
    destino = destino or os.path.join(_RAIZ, "projetos", "_conferencia")
    os.makedirs(destino, exist_ok=True)
    projeto = projeto_demonstracao()
    arquivos = []
    arquivos += [i["arquivo"] for i in lista_material.gerar(
        projeto, os.path.join(destino, "lista"))]
    arquivos += [i["arquivo"] for i in pranchas.gerar(
        projeto, os.path.join(destino, "pranchas"))]
    arquivos.append(memorial.gerar(projeto, os.path.join(destino, "memorial")))

    pasta_png = os.path.join(destino, "png")
    os.makedirs(pasta_png, exist_ok=True)
    for f in os.listdir(pasta_png):
        os.remove(os.path.join(pasta_png, f))
    for caminho in arquivos:
        if not caminho.lower().endswith(".pdf"):
            continue
        base = os.path.splitext(os.path.basename(caminho))[0][:28]
        doc = pymupdf.open(caminho)
        for k, pg in enumerate(doc, 1):
            dpi = 80 if pg.rect.width < 1000 else 60
            pg.get_pixmap(dpi=dpi).save(
                os.path.join(pasta_png, f"{base}_{k:03d}.png"))
        doc.close()
    print(f"PNG em {pasta_png}")
    return pasta_png


if __name__ == "__main__":
    if "--png" in sys.argv:
        gerar_png(sys.argv[sys.argv.index("--png") + 1]
                  if len(sys.argv) > sys.argv.index("--png") + 1
                  and not sys.argv[sys.argv.index("--png") + 1].startswith("-")
                  else None)
    else:
        unittest.main(argv=[a for a in sys.argv if not a.startswith("--")],
                      verbosity=2)
