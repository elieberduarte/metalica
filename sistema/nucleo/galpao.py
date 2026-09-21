# -*- coding: utf-8 -*-
"""Orquestrador: dimensiona um galpão de duas águas do início ao fim.

Executa, na ordem, o mesmo caminho que um projetista percorre:

    1. cargas permanentes e sobrecarga
    2. vento pela NBR 6123, com os dois sentidos e os dois coeficientes internos
    3. terças pela NBR 14762, sob gravidade e sob sucção
    4. cargas no pórtico e análise pelo método da rigidez
    5. combinações últimas e de serviço, e a envoltória de esforços
    6. viga e pilar pela NBR 8800, com efeitos de segunda ordem
    7. contraventamentos
    8. ligação de joelho, ligação de cumeeira e base do pilar
    9. lista de material, pesos e custo

Cada etapa guarda a memória de cálculo no `ProjetoGalpao`, que é o que o memorial
imprime e os desenhos consomem. Nada é recalculado depois.
"""
import math
import re
from typing import List, Optional, Tuple

from . import analise, bases, cargas, ligacoes, materiais as mat, nbr8800, nbr14762
from .base import ErroDeDados, Resultado, Verificacao, fmt
from dataclasses import replace
from .modelo_galpao import DadosGalpao, ElementoDimensionado, Peca, ProjetoGalpao
from .perfis import Perfil, banco, perfil as achar_perfil

# posição das terças extremas ao longo da água, em m (a mesma da planta de cobertura)
RECUO_TERCA_BEIRAL = 0.20
RECUO_TERCA_CUMEEIRA = 0.25

# telhas da interface -> nome na tabela de cargas
TELHAS = {
    "trapezoidal 0,43 mm": "telha metálica simples",
    "trapezoidal 0,50 mm": "telha metálica simples",
    "trapezoidal 0,65 mm": "telha metálica simples",
    "ondulada 0,50 mm": "telha metálica simples",
    "sanduíche (termoacústica)": "telha sanduíche",
    "fibrocimento 6 mm": "telha de fibrocimento",
}
PESO_TELHA = {"trapezoidal 0,43 mm": 0.045, "trapezoidal 0,50 mm": 0.055,
              "trapezoidal 0,65 mm": 0.070, "ondulada 0,50 mm": 0.055,
              "sanduíche (termoacústica)": 0.130, "fibrocimento 6 mm": 0.200}


def dimensionar(dados: DadosGalpao) -> ProjetoGalpao:
    """Ponto de entrada: recebe os dados da interface e devolve o projeto completo."""
    dados.validar()
    p = ProjetoGalpao(dados=dados)
    try:
        _cargas_permanentes(p)
        _vento(p)
        _tercas(p)
        _longarinas(p)
        _analise_portico(p)
        _contraventamentos(p)
        _ligacoes(p)
        _base(p)
        _lista_de_material(p)
    except ErroDeDados as e:
        p.erros.append(str(e))
    except Exception as e:                      # falha inesperada não pode derrubar a interface
        p.erros.append(f"falha no dimensionamento: {type(e).__name__}: {e}")
    return p


# --------------------------------------------------------------- 1. cargas

def _cargas_permanentes(p: ProjetoGalpao):
    d = p.dados
    telha_nome = TELHAS.get(d.telha, "telha metálica simples")
    valor_telha = PESO_TELHA.get(d.telha)
    comp = cargas.peso_proprio_cobertura(
        telha=telha_nome, com_forro=d.carga_forro > 0, com_tercas=True,
        com_acessorios=True, instalacoes=d.carga_extra,
        valor_telha=valor_telha,
        valor_forro=d.carga_forro if d.carga_forro > 0 else None)
    p.cargas = {
        "composicao": comp,
        "g_cobertura": comp.total,                       # kN/m²
        "sobrecarga": d.sobrecarga_cobertura,
        "parcelas": [{"item": it.descricao, "valor": it.valor, "fonte": getattr(it, "fonte", "")}
                     for it in getattr(comp, "itens", [])],
        "passos": comp.passos() if hasattr(comp, "passos") else [],
    }


# --------------------------------------------------------------- 2. vento

def _vento(p: ProjetoGalpao):
    d = p.dados
    v0 = cargas.velocidade_basica(d.cidade) if d.cidade else d.v0
    altura_ref = d.altura_cumeeira
    vg = cargas.pressoes_galpao(
        b=d.vao, a=d.comprimento, h=d.pe_direito, theta_graus=d.angulo_telhado,
        V0=v0, categoria=d.categoria_rugosidade, classe=d.classe, z=altura_ref,
        S1=d.fator_topografico, aberturas=d.aberturas)
    p.vento = {
        "objeto": vg, "V0": v0, "S1": vg.S1, "S2": vg.S2, "S3": vg.S3,
        "Vk": vg.Vk, "q": vg.q, "tabela": vg.tabela(),
        "passos": getattr(vg, "passos", []),
    }


def _pressao(p: ProjetoGalpao, superficie: str, direcao: str, cpi: float) -> float:
    """Pressão em kN/m² numa superfície, tolerando nomes parciais."""
    vg = p.vento["objeto"]
    try:
        return vg.pressao(superficie, direcao, cpi)
    except Exception:
        for linha in vg.tabela():
            if (superficie.lower() in linha["superfície"].lower()
                    and linha["direção"] == direcao and abs(linha["Cpi"] - cpi) < 1e-6):
                return linha["p (kN/m²)"]
    raise ErroDeDados(f"pressão de vento não encontrada para {superficie} ({direcao}).")


def _pressoes_criticas(p: ProjetoGalpao) -> dict:
    """As pressões que governam o pórtico: sucção máxima no telhado e pressão lateral."""
    vg = p.vento["objeto"]
    tab = vg.tabela()

    def pega(chaves, direcao, cpi, escolher="min"):
        cands = [l["p (kN/m²)"] for l in tab
                 if l["direção"] == direcao and abs(l["Cpi"] - cpi) < 1e-6
                 and any(c in l["superfície"].lower() for c in chaves)
                 and not l.get("zona")]
        if not cands:
            cands = [l["p (kN/m²)"] for l in tab
                     if l["direção"] == direcao and abs(l["Cpi"] - cpi) < 1e-6
                     and any(c in l["superfície"].lower() for c in chaves)]
        if not cands:
            return 0.0
        return min(cands) if escolher == "min" else max(cands)

    saida = {}
    for cpi, rot in ((0.2, "cpi+"), (-0.3, "cpi-")):
        saida[rot] = {
            "cpi": cpi,
            "telhado_barlavento": pega(["barlavento (ef)", "água de barlavento", "telhado barlavento"],
                                       "transversal", cpi),
            "telhado_sotavento": pega(["sotavento (gh)", "água de sotavento", "telhado sotavento"],
                                      "transversal", cpi),
            "parede_barlavento": pega(["parede lateral barlavento", "barlavento (a)"],
                                      "transversal", cpi, "max"),
            "parede_sotavento": pega(["parede lateral sotavento", "sotavento (b)"],
                                     "transversal", cpi),
        }
    return saida


# --------------------------------------------------------------- 3. terças

def _tercas(p: ProjetoGalpao):
    d = p.dados
    # quantas terças cabem na água, com espaçamento próximo ao pedido
    # primeira terça a 200 mm do beiral e última a 250 mm da cumeeira, medidos ao
    # longo da água; o número de espaços é arredondado para cima, para o espaçamento
    # nunca passar do alvo, que costuma ser o vão máximo da telha
    agua = d.comprimento_agua
    util = max(agua - RECUO_TERCA_BEIRAL - RECUO_TERCA_CUMEEIRA, 0.5)
    n_esp = max(2, math.ceil(util / d.espacamento_tercas - 1e-9))
    esp = util / n_esp                       # espaçamento real, em m
    n_linhas = n_esp + 1

    g = p.cargas["g_cobertura"]              # kN/m²
    sc = d.sobrecarga_cobertura
    crit = _pressoes_criticas(p)
    # sucção mais severa entre os dois Cpi
    succao = min(crit["cpi+"]["telhado_barlavento"], crit["cpi-"]["telhado_barlavento"],
                 crit["cpi+"]["telhado_sotavento"], crit["cpi-"]["telhado_sotavento"])

    vao = d.espacamento_porticos
    # gravidade: 1,25·g + 1,5·sc  (permanente de pequena variabilidade, NBR 8800 Tab. 1)
    q_grav = (1.25 * g + 1.5 * sc) * esp
    # sucção: 1,4·vento aliviado por 1,0·g (permanente favorável). O módulo da NBR 14762
    # espera a sucção como valor positivo (para cima), daí o sinal invertido.
    q_suc = max(0.0, (1.4 * abs(succao) - 1.0 * g) * esp)
    q_serv_grav = (g + sc) * esp
    q_serv_suc = max(0.0, (abs(succao) - g) * esp)

    opcoes = nbr14762.dimensionar_terca(
        aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
        correntes=(d.linhas_correntes,) if d.linhas_correntes else (0, 1, 2),
        inclinacao=d.angulo_telhado,
        carga_servico_gravidade=q_serv_grav, carga_servico_succao=q_serv_suc,
        apenas_aprovados=True)
    if not opcoes:
        # tenta liberar o número de correntes antes de desistir
        opcoes = nbr14762.dimensionar_terca(
            aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
            correntes=(1, 2, 3), inclinacao=d.angulo_telhado,
            carga_servico_gravidade=q_serv_grav, carga_servico_succao=q_serv_suc,
            apenas_aprovados=True)
        if opcoes:
            p.avisos.append(
                f"Com {d.linhas_correntes} linha(s) de correntes nenhuma terça do catálogo "
                f"atende; foram adotadas {opcoes[0].dados.get('n_correntes')} linha(s).")
    if not opcoes:
        opcoes = nbr14762.dimensionar_terca(
            aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
            correntes=(1, 2, 3), inclinacao=d.angulo_telhado,
            carga_servico_gravidade=q_serv_grav, carga_servico_succao=q_serv_suc,
            apenas_aprovados=False)
        opcoes.sort(key=lambda r: r.razao)
        p.avisos.append("Nenhuma terça do catálogo atende; foi adotada a de menor razão de "
                        "aproveitamento, que NÃO passa. Reduza o espaçamento entre pórticos "
                        "ou o espaçamento das terças.")
    if not opcoes:
        raise ErroDeDados("não foi possível dimensionar a terça com os dados informados.")
    melhor = opcoes[0]
    n_correntes = melhor.dados.get("n_correntes", d.linhas_correntes)

    e = ElementoDimensionado(
        nome="Terça", perfil=melhor.perfil, material=d.aco_tercas, resultado=melhor,
        esforcos={"q_gravidade_kN_m": round(q_grav, 3), "q_succao_kN_m": round(q_suc, 3),
                  "succao_kN_m2": round(succao, 3)},
        geometria={"vao_m": vao, "espacamento_m": round(esp, 4), "linhas": n_linhas,
                   "n_correntes": n_correntes, "por_agua": n_linhas,
                   "recuo_beiral_m": RECUO_TERCA_BEIRAL,
                   "recuo_cumeeira_m": RECUO_TERCA_CUMEEIRA},
        alternativas=[{"perfil": o.perfil, "razao": round(o.razao, 3), "ok": o.ok}
                      for o in opcoes[:8]])
    p.elementos.append(e)
    p.cargas["espacamento_tercas_real"] = esp
    p.cargas["linhas_tercas_por_agua"] = n_linhas
    p.cargas["succao_telhado"] = succao


def _longarinas(p: ProjetoGalpao):
    """Longarinas de fechamento lateral pela NBR 14762, sob pressão e sucção do vento.

    A longarina vence o vão entre pórticos e recebe o vento na faixa de parede de cada
    fiada. Sob pressão a telha trava a mesa externa, papel que a gravidade tem na terça;
    sob sucção a mesa interna fica comprimida e só as correntes a travam. Por isso a
    verificação reaproveita a da terça, com a pressão no lugar da gravidade.

    Hipóteses: as zonas locais de canto (Ce = −1,0) valem para telhas e fixações, não
    para a peça, e ficam de fora; o peso próprio atua no eixo fraco e é levado pelas
    correntes, então não entra aqui.
    """
    d = p.dados
    linhas = [l for l in p.vento["objeto"].tabela()
              if "parede lateral" in l["superfície"].lower()]
    if not linhas:
        return
    pressao = max(l["p (kN/m²)"] for l in linhas)
    succao = min(l["p (kN/m²)"] for l in linhas)

    altura = d.altura_fechamento or d.pe_direito
    n_fiadas = max(2, int(d.pe_direito / 2))      # mesmo critério da lista de material
    esp = altura / n_fiadas                        # faixa de parede por fiada, m
    q_p = 1.4 * max(pressao, 0.0) * esp
    q_s = 1.4 * abs(min(succao, 0.0)) * esp
    servico = dict(carga_servico_gravidade=max(pressao, 0.0) * esp,
                   carga_servico_succao=abs(min(succao, 0.0)) * esp)
    base = dict(aco=d.aco_tercas, vao=d.espacamento_porticos, carga_gravidade=q_p,
                carga_succao=q_s, inclinacao=0.0, **servico)

    opcoes = nbr14762.dimensionar_terca(correntes=(max(1, d.linhas_correntes),),
                                        apenas_aprovados=True, **base)
    if not opcoes:
        opcoes = nbr14762.dimensionar_terca(correntes=(1, 2, 3), apenas_aprovados=True, **base)
        if opcoes:
            p.avisos.append("As longarinas precisaram de %s linha(s) de correntes."
                            % opcoes[0].dados.get("n_correntes"))
    if not opcoes:
        opcoes = nbr14762.dimensionar_terca(correntes=(1, 2, 3), apenas_aprovados=False, **base)
        opcoes.sort(key=lambda r: r.razao)
        p.avisos.append("Nenhuma longarina do catálogo atende; foi adotada a de menor razão "
                        "de aproveitamento, que NÃO passa. Reduza o espaçamento entre "
                        "pórticos ou aumente o número de fiadas.")
    if not opcoes:
        raise ErroDeDados("não foi possível dimensionar as longarinas de fechamento.")

    melhor = opcoes[0]
    melhor.elemento = "Longarina L = %g m" % d.espacamento_porticos
    for v in melhor.verificacoes:
        # a verificação é a da terça: na parede, "gravidade" é a pressão do vento
        v.titulo = v.titulo.replace("gravidade", "pressão do vento")
    p.elementos.append(ElementoDimensionado(
        nome="Longarina de fechamento", perfil=melhor.perfil, material=d.aco_tercas,
        resultado=melhor,
        esforcos={"q_pressao_kN_m": round(q_p, 3), "q_succao_kN_m": round(q_s, 3),
                  "pressao_kN_m2": round(pressao, 3), "succao_kN_m2": round(succao, 3)},
        geometria={"vao_m": d.espacamento_porticos, "fiadas_por_lado": n_fiadas,
                   "espacamento_m": round(esp, 4),
                   # cada fiada no meio da sua faixa de parede, medida do piso
                   "cotas_fiadas_m": [round(esp / 2 + k * esp, 4)
                                      for k in range(n_fiadas)],
                   "n_correntes": melhor.dados.get("n_correntes", d.linhas_correntes)},
        alternativas=[{"perfil": o.perfil, "razao": round(o.razao, 3), "ok": o.ok}
                      for o in opcoes[:8]]))


# --------------------------------------------------------- 4. análise do pórtico

def _carregar_portico(modelo, p: ProjetoGalpao, pilar: Perfil, viga: Perfil):
    """Aplica os casos de carga elementares no modelo do pórtico."""
    d = p.dados
    s = d.espacamento_porticos                      # largura de influência, m
    g = p.cargas["g_cobertura"]
    sc = d.sobrecarga_cobertura
    crit = _pressoes_criticas(p)

    # peso próprio do pórtico, estimado pelos perfis adotados (kN/m na barra)
    pp_viga = viga.massa * 9.81e-3 if viga else 0.5
    pp_pilar = pilar.massa * 9.81e-3 if pilar else 0.5

    barras_viga = [b for b in ("viga_esq", "viga_dir") if _tem_barra(modelo, b)] or [1, 2]
    barras_pilar = [b for b in ("pilar_esq", "pilar_dir") if _tem_barra(modelo, b)] or [0, 3]

    # o modelo trabalha em kN e cm: as cargas de kN/m entram divididas por 100
    M = 1 / 100.0

    # --- permanente ---
    for b in barras_viga:
        modelo.distribuida("PP", b, -(g * s + pp_viga) * M, "global_y")
    for b in barras_pilar:
        modelo.distribuida("PP", b, -pp_pilar * M, "global_y")
    # --- sobrecarga (projetada na horizontal) ---
    for b in barras_viga:
        modelo.distribuida("SC", b, -sc * s * M, "projetada_y")
    # --- vento, um caso por coeficiente interno ---
    for rot, c in crit.items():
        caso = f"V{rot}"
        # Telhado: a tabela de vento guarda pressão positiva e sucção negativa, e no
        # modelo "perpendicular" positivo aponta para fora da água. Daí o sinal
        # invertido: sucção (p < 0) tem de entrar como carga para fora, levantando a
        # cobertura. Sem isso ela entrava empurrando o telhado para baixo, a combinação
        # de sucção somava com a gravidade em vez de aliviar, e o caso de inversão de
        # momento — o que costuma governar galpão leve — simplesmente não aparecia.
        modelo.distribuida(caso, barras_viga[0], -c["telhado_barlavento"] * s * M, "perpendicular")
        if len(barras_viga) > 1:
            modelo.distribuida(caso, barras_viga[1], -c["telhado_sotavento"] * s * M, "perpendicular")
        # paredes: pressão horizontal nos pilares, ambas no sentido do vento
        modelo.distribuida(caso, barras_pilar[0], c["parede_barlavento"] * s * M, "global_x")
        if len(barras_pilar) > 1:
            modelo.distribuida(caso, barras_pilar[1], -c["parede_sotavento"] * s * M, "global_x")
    return crit


def _tem_barra(modelo, rotulo) -> bool:
    try:
        modelo.indice_barra(rotulo)
        return True
    except Exception:
        return False


def _analise_portico(p: ProjetoGalpao):
    """Analisa e dimensiona viga e pilar juntos, iterando até a rigidez estabilizar.

    A distribuição de momentos num pórtico depende da rigidez relativa entre pilar e
    viga, e a rigidez depende dos perfis escolhidos. Por isso análise e dimensionamento
    caminham no mesmo laço: a cada passada os perfis são redimensionados com as funções
    completas da NBR 8800 e o pórtico é reanalisado, até a escolha se repetir.
    """
    d = p.dados
    a = mat.aco(d.aco_perfis)
    esp_terca = p.cargas["espacamento_tercas_real"] * 100          # cm

    # semente: pilar e viga de altura parecida, como e usual em galpoes de alma cheia
    h_alvo = max(d.vao * 1000 / 45, d.pe_direito * 1000 / 20)
    viga0 = _perfil_proximo(h_alvo)
    pilar0 = _perfil_proximo(h_alvo)

    H = d.pe_direito * 100
    Kx = 2.0 if d.base_rotulada else 1.5
    Ly = min(H, 300.0)
    historico = []
    Lb_viga = esp_terca
    res_viga = res_pilar = None

    for _ in range(6):
        modelo, env, combos = _rodar_analise(p, pilar0, viga0)
        esf = _extrair_esforcos(env)

        # viga: sob gravidade a terca trava a mesa superior; sob succao a mesa
        # inferior fica comprimida e quem trava sao as maos-francesas
        inverte = esf["viga"]["M_max"] * esf["viga"]["M_min"] < 0
        Lb_viga = max(esp_terca, min(d.vao * 100 / 4, 300.0)) if inverte else esp_terca
        res_viga = _menor_perfil(
            lambda perf: nbr8800.verificar_viga(
                perf, a, L=d.comprimento_agua * 100, M_Sd=esf["viga"]["M"],
                V_Sd=esf["viga"]["V"], Lb=Lb_viga, Cb=1.14,
                limite="L/%d" % d.flecha_viga, q_servico=_q_servico_viga(p),
                elemento="Viga do pórtico"),
            altura_min=200)

        # pilar: flexo-compressao, com altura minima proxima a da viga para nao ficar
        # tao flexivel a ponto de empurrar todo o momento para a cumeeira
        h_min_pilar = max(200.0, achar_perfil(res_viga.perfil).d * 0.8)
        res_pilar = _menor_perfil(
            lambda perf: nbr8800.flexao_composta(
                perf, a, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"],
                Lx=H, Ly=Ly, Kx=Kx, Ky=1.0, Lb=Ly, Cb=1.67, elemento="Pilar"),
            altura_min=h_min_pilar)

        nova_viga = achar_perfil(res_viga.perfil)
        novo_pilar = achar_perfil(res_pilar.perfil)
        par = (nova_viga.nome, novo_pilar.nome)
        if par == (viga0.nome, pilar0.nome) or historico.count(par) >= 1:
            viga0, pilar0 = nova_viga, novo_pilar
            break
        historico.append(par)
        viga0, pilar0 = nova_viga, novo_pilar

    # o deslocamento horizontal do topo costuma governar o pilar de galpao com base
    # rotulada; percorre-se o catalogo ate atender ao limite de servico
    pilar0, res_pilar = _pilar_por_deslocamento(
        p, viga0, pilar0, res_pilar, _extrair_esforcos(
            _rodar_analise(p, pilar0, viga0)[1]), H, Kx, Ly, a)

    # analise final com os perfis adotados
    modelo, env, combos = _rodar_analise(p, pilar0, viga0)
    esf = _extrair_esforcos(env)
    desloc = _deslocamento_horizontal(p, modelo)
    extremos = _momentos_nos_nos(modelo, combos)
    esf["joelho"] = extremos["joelho"]
    esf["cumeeira"] = extremos["cumeeira"]

    p.esforcos = {
        "modelo": modelo, "envoltoria": env, "combinacoes": combos,
        "viga": esf["viga"], "pilar": esf["pilar"],
        "joelho_kNm": round(esf["joelho"] / 100, 1),
        "cumeeira_kNm": round(esf["cumeeira"] / 100, 1),
        "deslocamento": desloc,
        "pre_viga": viga0.nome, "pre_pilar": pilar0.nome,
        "iteracoes": historico,
    }
    p.esforcos["casos_modelo"] = combos
    p.combinacoes = _combinacoes_documentadas(p)

    p.elementos.append(ElementoDimensionado(
        nome="Viga do pórtico", perfil=res_viga.perfil, material=d.aco_perfis,
        resultado=res_viga,
        esforcos={"M_kNcm": round(esf["viga"]["M"], 1),
                  "M_kNm": round(esf["viga"]["M"] / 100, 1),
                  "V_kN": round(esf["viga"]["V"], 1),
                  "caso": esf["viga"].get("caso_M", "")},
        geometria={"Lb_cm": round(Lb_viga, 1),
                   "comprimento_m": round(d.comprimento_agua, 2),
                   "misula_m": d.comprimento_misula if d.com_misula else 0.0}))
    p.elementos.append(ElementoDimensionado(
        nome="Pilar", perfil=res_pilar.perfil, material=d.aco_perfis,
        resultado=res_pilar,
        esforcos={"N_kN": round(esf["pilar"]["N"], 1),
                  "M_kNcm": round(esf["pilar"]["M"], 1),
                  "M_kNm": round(esf["pilar"]["M"] / 100, 1),
                  "V_kN": round(esf["pilar"]["V"], 1),
                  "caso": esf["pilar"].get("caso_M", "")},
        geometria={"altura_m": d.pe_direito, "Kx": Kx, "Ly_cm": Ly}))

    if desloc and desloc.get("razao", 0) > 1.0:
        _diagnostico_deslocamento(p, viga0, pilar0, desloc)


def _pilar_por_deslocamento(p: ProjetoGalpao, viga: Perfil, pilar: Perfil,
                            res_pilar, esf, H, Kx, Ly, aco):
    """Sobe o perfil do pilar enquanto isso reduzir o deslocamento de forma relevante.

    Em galpão de base rotulada o deslocamento horizontal do topo costuma governar o
    pilar. Mas a partir de certo ponto o que limita é a rigidez do pórtico inteiro, e
    engrossar só o pilar deixa de compensar: cada degrau de perfil reduz menos de 2 %
    do deslocamento e só encarece. Nesse caso o laço para e o projetista é avisado das
    saídas reais — engastar a base, aproximar os pórticos ou afrouxar o critério.
    """
    d = p.dados
    limite = d.pe_direito * 100 / d.desloc_horizontal
    candidatos = [x for x in banco().candidatos("I", "W", altura_min=pilar.d * 0.95)
                  if x.massa >= pilar.massa]
    escolhido, resultado = pilar, res_pilar
    anterior = None
    for cand in candidatos[:20]:
        modelo, _, _ = _rodar_analise(p, cand, viga)
        desl = _deslocamento_horizontal(p, modelo)
        if not desl:
            break
        u = desl["u_cm"]
        if u <= limite:                                  # atende: adota este perfil
            if cand.nome != pilar.nome:
                resultado = nbr8800.flexao_composta(
                    cand, aco, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"],
                    Lx=H, Ly=Ly, Kx=Kx, Ky=1.0, Lb=Ly, Cb=1.67, elemento="Pilar")
            escolhido = cand
            return escolhido, resultado
        if cand.massa > pilar.massa * 2.5:
            break            # engrossar mais só o pilar deixou de compensar
        anterior = u
    # nenhum candidato atendeu: mantém o mais leve que satisfaz a resistência e avisa
    return escolhido, resultado


def _diagnostico_deslocamento(p: ProjetoGalpao, viga: Perfil, pilar: Perfil, desloc: dict):
    """Explica o que fazer quando o deslocamento horizontal não fecha."""
    d = p.dados
    saidas = []
    if d.base_rotulada:
        try:
            dados_eng = replace(d, base_rotulada=False)
            p2 = ProjetoGalpao(dados=dados_eng)
            p2.cargas, p2.vento = p.cargas, p.vento
            modelo, _, _ = _rodar_analise(p2, pilar, viga)
            u_eng = _deslocamento_horizontal(p2, modelo).get("u_cm")
            if u_eng:
                saidas.append("engastar a base do pilar levaria o deslocamento a "
                              "%.1f cm" % u_eng)
        except Exception:
            pass
    saidas.append("aproximar os pórticos (hoje a %.1f m) reduz a carga de vento por "
                  "pórtico" % d.espacamento_porticos)
    saidas.append("para galpão sem ponte rolante nem alvenaria encostada é usual adotar "
                  "H/150 a H/200 em vez de H/%d" % d.desloc_horizontal)
    p.avisos.append(
        "Deslocamento horizontal do topo do pilar de %.1f cm acima do limite %s = %.1f cm, "
        "mesmo com o maior perfil que ainda compensa. Saídas: %s."
        % (desloc["u_cm"], desloc["criterio"], desloc["limite_cm"], "; ".join(saidas)))


def _combinacoes_documentadas(p: ProjetoGalpao) -> list:
    """Monta as combinações da NBR 8681 com os valores reais das ações.

    São as mesmas combinações aplicadas ao modelo, escritas na linguagem do módulo de
    cargas para que o memorial mostre cada parcela com seu coeficiente. Os valores são
    as cargas por metro quadrado de projeção da cobertura.
    """
    d = p.dados
    g = p.cargas["g_cobertura"]
    sc = d.sobrecarga_cobertura
    succao = abs(p.cargas.get("succao_telhado", 0.0))
    acoes = [
        cargas.Acao("Peso próprio da cobertura", "permanente", g, subtipo="metálica"),
        cargas.Acao("Sobrecarga de cobertura", "variável", sc, psi="cobertura"),
        cargas.Acao("Vento (sucção no telhado)", "vento", -succao),
    ]
    try:
        ultimas = cargas.combinacoes_ultimas(acoes)
        servico = cargas.combinacoes_servico(acoes)
        return list(ultimas) + list(servico)
    except Exception:
        return []


def _rodar_analise(p: ProjetoGalpao, pilar: Perfil, viga: Perfil):
    """Monta o modelo com os perfis dados, aplica as cargas e devolve a envoltoria."""
    d = p.dados
    misula = (analise.Misula(comprimento=d.comprimento_misula * 100, fator=1.5)
              if d.com_misula else None)
    modelo = analise.portico_galpao(
        vao=d.vao * 100, pe_direito=d.pe_direito * 100,
        inclinacao=d.inclinacao / 100.0, base_rotulada=d.base_rotulada,
        misula=misula, pilar=pilar, viga=viga)
    _carregar_portico(modelo, p, pilar, viga)
    modelo.validar()
    combos = _combinar(modelo, p, None)
    casos_elu = [c for c in combos if c.startswith("C")]
    env = analise.envoltoria(modelo, casos_elu)
    return modelo, env, combos


def _extrair_esforcos(env) -> dict:
    """Momentos e cortantes de projeto, considerando tambem os trechos de misula."""
    def maior(rotulos, grandeza):
        val, caso = 0.0, ""
        for r in rotulos:
            try:
                b = env.barra(r)
            except Exception:
                continue
            for ext in (getattr(b, grandeza + "_max"), getattr(b, grandeza + "_min")):
                if abs(_v(ext)) > abs(val):
                    val, caso = _v(ext), _caso(ext)
        return val, caso

    # a viga e dimensionada pelo momento fora da misula; o trecho de misula tem
    # secao maior e e verificado junto com a ligacao de joelho
    barras_viga = ["viga_esq", "viga_dir"]
    M_viga, caso_v = maior(barras_viga, "M")
    V_viga, _ = maior(barras_viga + ["misula_esq", "misula_dir"], "V")
    N_viga, _ = maior(["viga_esq", "viga_dir"], "N")
    M_pil, caso_p = maior(["pilar_esq", "pilar_dir"], "M")
    V_pil, _ = maior(["pilar_esq", "pilar_dir"], "V")
    N_pil, _ = maior(["pilar_esq", "pilar_dir"], "N")

    def extremo(rotulo):
        try:
            b = env.barra(rotulo)
        except Exception:
            return 0.0
        return max(abs(_v(b.M_max)), abs(_v(b.M_min)))

    ve = env.barra("viga_esq")
    pe = env.barra("pilar_esq")
    return {
        "viga": {"M": abs(M_viga), "V": abs(V_viga), "N": abs(N_viga),
                 "M_max": _v(ve.M_max), "M_min": _v(ve.M_min),
                 "caso_M": caso_v, "resumo": ve.resumo()},
        "pilar": {"M": abs(M_pil), "V": abs(V_pil), "N": abs(N_pil),
                  "M_max": _v(pe.M_max), "M_min": _v(pe.M_min),
                  "caso_M": caso_p, "resumo": pe.resumo()},
        "joelho": extremo("misula_esq") or extremo("pilar_esq"),
        "cumeeira": extremo("viga_esq"),
    }


def _momentos_nos_nos(modelo, combos) -> dict:
    """Momento no joelho e na cumeeira, lido nas extremidades das barras.

    A envoltória devolve o extremo de cada barra, que pode estar no meio do vão. Para
    dimensionar as ligações interessa o momento exatamente no nó, então ele é lido na
    extremidade correspondente em cada combinação última.
    """
    joelho = cumeeira = 0.0
    for caso in [c for c in combos if c.startswith("C")]:
        try:
            r = analise.resolver(modelo, caso)
        except Exception:
            continue
        try:
            dv = r.barra("viga_esq").diagrama
            cumeeira = max(cumeeira, abs(dv.M[-1]))
        except Exception:
            pass
        for rot, ponta in (("misula_esq", 0), ("pilar_esq", -1)):
            try:
                d_ = r.barra(rot).diagrama
                joelho = max(joelho, abs(d_.M[ponta]))
            except Exception:
                pass
    return {"joelho": joelho, "cumeeira": cumeeira}


def _menor_perfil(verificar, altura_min=200.0, familia="W"):
    """Primeiro perfil do catalogo (do mais leve ao mais pesado) que passa em tudo."""
    ultimo = None
    for perf in banco().candidatos("I", familia, altura_min=altura_min):
        r = verificar(perf)
        ultimo = r
        if r.ok:
            return r
    return ultimo


def _deslocamento_horizontal(p: ProjetoGalpao, modelo) -> dict:
    """Deslocamento do topo do pilar na combinacao de servico com vento."""
    d = p.dados
    try:
        r = analise.resolver(modelo, "S vento")
        i = modelo.indice_no("B")
        u = abs(r.deslocamento(i)[0])
    except Exception:
        return {}
    limite = d.pe_direito * 100 / d.desloc_horizontal
    return {"u_cm": u, "limite_cm": limite,
            "razao": u / limite if limite else 0.0,
            "criterio": "H/%d" % d.desloc_horizontal}


def _combinar(modelo, p: ProjetoGalpao, acoes) -> dict:
    """Monta os casos combinados dentro do modelo e devolve {nome: descrição}."""
    d = p.dados
    combos = {}
    # C1 gravidade: 1,25 PP + 1,5 SC
    modelo.caso("C1 gravidade")
    _somar(modelo, "C1 gravidade", {"PP": 1.25, "SC": 1.5})
    combos["C1 gravidade"] = "1,25·PP + 1,5·SC"
    # C2 e C3: sucção com permanente favorável
    for rot in ("cpi+", "cpi-"):
        nome = f"C2 sucção ({rot})"
        modelo.caso(nome)
        _somar(modelo, nome, {"PP": 1.0, f"V{rot}": 1.4})
        combos[nome] = f"1,0·PP + 1,4·Vento ({rot})"
        nome3 = f"C3 vento+SC ({rot})"
        modelo.caso(nome3)
        _somar(modelo, nome3, {"PP": 1.25, "SC": 1.5 * 0.6, f"V{rot}": 1.4 * 0.6})
        combos[nome3] = f"1,25·PP + 0,9·SC + 0,84·Vento ({rot})"
    # serviço, para flecha e deslocamento
    modelo.caso("S rara gravidade")
    _somar(modelo, "S rara gravidade", {"PP": 1.0, "SC": 1.0})
    combos["S rara gravidade"] = "PP + SC (serviço)"
    modelo.caso("S vento")
    _somar(modelo, "S vento", {"PP": 1.0, "Vcpi-": 0.3})
    combos["S vento"] = "PP + 0,3·Vento (frequente)"
    return combos


def _somar(modelo, destino: str, parcelas: dict):
    """Copia as cargas dos casos elementares para o caso combinado, com seus fatores."""
    for origem, fator in parcelas.items():
        for c in modelo.casos.get(origem, []) if hasattr(modelo, "casos") else []:
            modelo.add_carga(destino, _escalar(c, fator))


def _escalar(carga, fator):
    import copy
    nova = copy.copy(carga)
    for campo in ("q", "Fx", "Fy", "Mz", "P", "valor"):
        if hasattr(nova, campo) and getattr(nova, campo):
            setattr(nova, campo, getattr(nova, campo) * fator)
    return nova


def _rotulo_viga(modelo):
    for r in ("viga_esq", 1):
        if _tem_barra(modelo, r):
            return r
    return 1


def _rotulo_pilar(modelo):
    for r in ("pilar_esq", 0):
        if _tem_barra(modelo, r):
            return r
    return 0


def _v(extremo) -> float:
    """Valor numérico de um extremo da envoltória."""
    return getattr(extremo, "valor", extremo)


def _caso(extremo) -> str:
    return getattr(extremo, "caso", "")


def _perfil_proximo(altura_mm: float, familia="W") -> Perfil:
    cands = banco().candidatos("I", familia)
    if not cands:
        raise ErroDeDados("catálogo de perfis W vazio.")
    return min(cands, key=lambda p: (abs(p.d - altura_mm), p.massa))


def _perfil_para_momento(M_Sd: float, aco_nome: str, minimo: Perfil = None,
                         N_Sd: float = 0.0, L: float = 0.0) -> Perfil:
    """Menor W que resiste ao momento com Lb = 0, usado só no laço de pré-dimensionamento."""
    a = mat.aco(aco_nome)
    for perf in banco().candidatos("I", "W"):
        if minimo and perf.massa < minimo.massa * 0.55:
            continue
        M_Rd = perf.Zx * a.fy / 1.10
        if M_Rd >= 1.25 * abs(M_Sd):
            return perf
    return banco().candidatos("I", "W")[-1]


# ------------------------------------------------------- 6. viga e pilar

def _q_servico_viga(p: ProjetoGalpao) -> float:
    d = p.dados
    g = p.cargas["g_cobertura"]
    return (g + d.sobrecarga_cobertura) * d.espacamento_porticos / 100.0   # kN/cm


# ------------------------------------------------- 7. contraventamentos

def _barra_redonda(diametro_mm: float) -> Perfil:
    """Perfil sintético de barra redonda maciça, para tirantes de contraventamento."""
    d_cm = diametro_mm / 10.0
    A = math.pi * d_cm ** 2 / 4
    I = math.pi * d_cm ** 4 / 64
    r = d_cm / 4
    return Perfil(nome="Barra redonda \u00f8 %.0f mm" % diametro_mm, tipo="barra",
                  dados={"nome": "Barra redonda \u00f8 %.0f mm" % diametro_mm,
                         "d": diametro_mm, "b": diametro_mm, "t": diametro_mm,
                         "massa": round(A * 0.785, 2), "A": round(A, 3),
                         "Ix": round(I, 3), "Iy": round(I, 3),
                         "Wx": round(2 * I / d_cm, 3), "Wy": round(2 * I / d_cm, 3),
                         "rx": round(r, 3), "ry": round(r, 3), "rmin": round(r, 3),
                         "J": round(2 * I, 3)})


TIRANTES = (12.7, 16.0, 20.0, 22.2, 25.4, 31.75)


def _dimensionar_tirante(N_Sd: float, comprimento_cm: float, aco, elemento: str):
    """Tirante redondo com esticador: barra rosqueada, sem limite de esbeltez.

    A NBR 8800 (item 5.2.8) dispensa o limite L/r <= 300 em barras pré-tensionadas
    por esticador, que é o caso do contraventamento em X montado com tensor.
    """
    ultimo = None
    for d_mm in TIRANTES:
        barra = _barra_redonda(d_mm)
        r = nbr8800.tracao(barra, aco, N_Sd=N_Sd, L=comprimento_cm,
                           rosqueada=True, pretensionada=True, elemento=elemento)
        ultimo = r
        if r.ok:
            return r
    return ultimo


def _vaos_contraventados(n_vaos: int) -> list:
    """Vãos com contraventamento em X: os dois extremos e o central (índices a partir de 0).

    É a regra usada nos desenhos e no modelo 3D. Fica aqui para que cálculo, lista de
    material, desenhos e modelo leiam do mesmo lugar.
    """
    if n_vaos < 2:
        return [0]
    return sorted({0, n_vaos - 1, max(0, (n_vaos - 1) // 2)})


def _contraventamentos(p: ProjetoGalpao):
    """Contraventamento de cobertura e vertical por tirantes redondos com esticador.

    Modelo de cálculo: o X de cobertura de cada vão extremo forma uma treliça horizontal
    que vence o vão do galpão, apoiada nos dois beirais, e recebe a parcela do vento no
    oitão que sobe para a cobertura. O cortante no painel junto ao apoio é metade dessa
    força, e a diagonal tracionada leva cortante × comprimento / profundidade, sendo a
    profundidade o espaçamento entre pórticos. Cada vão extremo resiste sozinho ao vento
    no seu oitão; o vão central serve à estabilidade e à montagem.

    Mais painéis ao longo do vão encurtam a diagonal e reduzem a força nela. É por isso
    que, quando o tirante não cabe, o número de painéis sobe. O cortante não se divide.
    """
    d = p.dados
    a = mat.aco(d.aco_chapas)          # tirantes costumam ser de aço comum
    crit = _pressoes_criticas(p)

    # parcela do vento no oitão que vai à cobertura: metade da parede, até meia altura
    # do frontão
    area_oitao = d.vao * (d.pe_direito + (d.altura_cumeeira - d.pe_direito) / 2) / 2
    q_oitao = max(abs(crit["cpi+"]["parede_barlavento"]),
                  abs(crit["cpi-"]["parede_barlavento"]))
    F_total = 1.4 * q_oitao * area_oitao
    cortante = F_total / 2                      # reação em cada beiral

    esp = d.espacamento_porticos
    vaos = _vaos_contraventados(max(1, d.n_porticos - 1))
    n_inicial = max(2, int(round(d.vao / max(esp, 1.0))))

    r, n_pain, N_diag, comp = None, n_inicial, 0.0, 0.0
    for n in range(n_inicial, n_inicial + 10, 2):
        largura_painel = d.vao / n
        if largura_painel < 1.2 and r is not None:
            break                                # painel estreito demais para montar
        comp = math.hypot(esp, largura_painel)
        N_diag = cortante * comp / esp
        r = _dimensionar_tirante(N_diag, comp * 100, a, "Contraventamento de cobertura")
        n_pain = n
        if r.ok:
            break
    if not r.ok:
        p.avisos.append("O tirante de contraventamento de cobertura não atende nem com o "
                        "maior diâmetro e o maior número de painéis; adote cantoneiras ou "
                        "treliça de contraventamento.")
    elif n_pain > n_inicial:
        p.avisos.append("O contraventamento de cobertura usa %d painéis ao longo do vão "
                        "(o usual seria %d) para o tirante caber no vento informado."
                        % (n_pain, n_inicial))
    p.elementos.append(ElementoDimensionado(
        nome="Contraventamento de cobertura", perfil=r.perfil, material=d.aco_chapas,
        resultado=r,
        esforcos={"N_kN": round(N_diag, 1), "F_oitao_kN": round(F_total, 1),
                  "cortante_kN": round(cortante, 1)},
        geometria={"comprimento_m": round(comp, 2), "paineis": n_pain,
                   "diagonais_por_painel": 2,
                   "vaos_contraventados": [v + 1 for v in vaos],
                   "quantidade": len(vaos) * n_pain * 2}))

    # vertical: o X de cada parede lateral, no vão contraventado, leva a reação do
    # beiral até a fundação
    comp_v = math.hypot(esp, d.pe_direito)
    N_v = cortante * comp_v / esp
    rv = _dimensionar_tirante(N_v, comp_v * 100, a, "Contraventamento vertical")
    if not rv.ok:
        p.avisos.append("O tirante de contraventamento vertical não atende nem com o "
                        "maior diâmetro; adote cantoneiras ou contraventamento em K.")
    p.elementos.append(ElementoDimensionado(
        nome="Contraventamento vertical", perfil=rv.perfil, material=d.aco_chapas,
        resultado=rv, esforcos={"N_kN": round(N_v, 1), "cortante_kN": round(cortante, 1)},
        geometria={"comprimento_m": round(comp_v, 2),
                   "vaos_contraventados": [v + 1 for v in vaos],
                   "quantidade": len(vaos) * 2 * 2}))


# ----------------------------------------------------------- 8. ligações

def _secao_misula(viga: Perfil, altura_mm: float) -> Perfil:
    """Seção da mísula: a mesma viga com a alma prolongada até a altura indicada.

    É a seção que chega na chapa de topo do joelho, e é por ela que a ligação deve
    ser dimensionada — usar a seção da viga levaria a uma solda impossível, porque o
    braço de alavanca do binário seria menor que o real.
    """
    h = max(altura_mm, viga.d)
    bf, tf, tw = viga.bf, viga.tf, viga.tw
    h_alma = h - 2 * tf
    A = (2 * bf * tf + h_alma * tw) / 100.0                       # cm²
    Ix = (bf * h ** 3 - (bf - tw) * h_alma ** 3) / 12 / 1e4       # cm⁴
    Wx = 2 * Ix / (h / 10)
    Zx = (bf * tf * (h - tf) + tw * h_alma ** 2 / 4) / 1000.0
    Iy = (2 * tf * bf ** 3 + h_alma * tw ** 3) / 12 / 1e4
    return Perfil(nome="M\u00edsula %s (h=%.0f)" % (viga.nome, h), tipo="I",
                  dados={"nome": "M\u00edsula %s" % viga.nome, "familia": "VS",
                         "d": h, "bf": bf, "tw": tw, "tf": tf,
                         "massa": round(A * 0.785, 1), "A": round(A, 2),
                         "Ix": round(Ix, 1), "Wx": round(Wx, 1), "Zx": round(Zx, 1),
                         "rx": round((Ix / A) ** 0.5, 2),
                         "Iy": round(Iy, 1), "Wy": round(2 * Iy / (bf / 10), 1),
                         "ry": round((Iy / A) ** 0.5, 2)})


def _ligacoes(p: ProjetoGalpao):
    """Ligação de joelho e de cumeeira por chapa de topo, buscando a configuração
    mais econômica que atenda a todas as verificações."""
    d = p.dados
    viga = p.elemento("Viga")
    if not viga:
        return
    perf_viga = achar_perfil(viga.perfil)

    # --- joelho: seção da mísula e momento do joelho ---
    M_joelho = abs(p.esforcos.get("joelho_kNm", 0.0)) * 100 or p.esforcos["viga"]["M"]
    V_joelho = p.esforcos["viga"]["V"]

    # a altura da mísula é o que dá braço de alavanca ao binário da ligação: quando a
    # chapa de topo não fecha, o caminho de projeto é alongar a mísula, não engrossar
    # indefinidamente a chapa
    if d.altura_misula:
        alturas = [d.altura_misula * 1000]
    elif d.com_misula:
        alturas = [perf_viga.d * f for f in (1.6, 1.8, 2.0, 2.3, 2.6, 3.0)]
    else:
        alturas = [perf_viga.d]

    lig, altura_misula = None, alturas[0]
    for h in alturas:
        secao = _secao_misula(perf_viga, h) if d.com_misula else perf_viga
        r = _buscar_chapa_topo(p, secao, M_joelho, V_joelho)
        lig, altura_misula = r, h
        if r.ok:
            break
    if not lig.ok:
        p.avisos.append("A ligação viga-pilar não atende com as chapas de topo e mísulas "
                        "testadas; use enrijecedores no pilar ou ligação soldada em obra.")
    elif altura_misula > perf_viga.d * 2.0:
        p.avisos.append("A ligação de joelho exigiu mísula alta (%.0f mm, %.1f vezes a "
                        "altura da viga). Avalie aumentar a viga." %
                        (altura_misula, altura_misula / perf_viga.d))
    lig.dados["altura_misula_mm"] = round(altura_misula)
    lig.dados["M_Sd_kNm"] = round(M_joelho / 100, 1)
    p.ligacoes["viga-pilar"] = lig

    # --- cumeeira: seção da viga e momento da cumeeira ---
    M_cum = abs(p.esforcos.get("cumeeira_kNm", 0.0)) * 100 or 0.3 * p.esforcos["viga"]["M"]
    rc = _buscar_chapa_topo(p, perf_viga, M_cum, V_joelho * 0.3, espessuras=(1.60, 1.90, 2.24, 2.54))
    rc.dados["M_Sd_kNm"] = round(M_cum / 100, 1)
    p.ligacoes["cumeeira"] = rc


def _buscar_chapa_topo(p: ProjetoGalpao, secao: Perfil, M: float, V: float,
                       espessuras=(1.60, 1.90, 2.24, 2.54, 3.15, 3.80)):
    d = p.dados
    ultimo = None
    for t_chapa in espessuras:
        for diam in ('3/4"', '7/8"', '1"'):
            for linhas in (2, 3, 4):
                r = ligacoes.chapa_de_topo(
                    secao, M_Sd=M, V_Sd=V, diametro=diam, parafuso=d.parafuso,
                    n_por_linha=2, linhas_tracionadas=linhas, t_chapa=t_chapa,
                    aco_chapa=d.aco_chapas, aco_viga=d.aco_perfis, eletrodo=d.eletrodo)
                ultimo = r
                if r.ok:
                    return r
    return ultimo


def d_padrao(d: DadosGalpao) -> str:
    return '3/4"'


# --------------------------------------------------------------- 9. base

def _base(p: ProjetoGalpao):
    """Dimensiona a base do pilar, varrendo diâmetro, quantidade e ancoragem.

    Em base engastada o momento traciona os chumbadores, e é comum precisar de barras
    maiores ou de mais barras do que os dois da base rotulada. A busca segue a ordem
    de custo: primeiro mais barras do mesmo diâmetro, depois diâmetros maiores.
    """
    d = p.dados
    pilar = p.elemento("Pilar")
    if not pilar:
        return
    perf = achar_perfil(pilar.perfil)
    N = pilar.esforcos.get("N_kN", 0.0)
    V = pilar.esforcos.get("V_kN", 0.0)
    M = 0.0 if d.base_rotulada else pilar.esforcos.get("M_kNcm", 0.0)
    lado = max(40.0, perf.d / 10 + 20)

    quantidades = (2, 4) if d.base_rotulada else (4, 6, 8)
    diametros = ('3/4"', '7/8"', '1"', '1.1/8"', '1.1/4"')
    # placa maior reduz o balanço e, com ele, a espessura necessária: é a primeira
    # saída antes de partir para chapa mais grossa ou chumbador maior
    folgas = (20.0, 40.0, 60.0, 90.0)
    # o pedestal precisa sobrar bem além da placa: é o concreto à frente da chave de
    # cisalhamento que resiste ao empuxo horizontal
    sobras_pedestal = (40.0, 60.0, 80.0)
    melhor, primeiro = None, None
    for folga, sobra in ((f, s_) for f in folgas for s_ in sobras_pedestal):
        B = L = lado + folga
        for n in quantidades:
            for diam in diametros:
                for h_ef in (30.0, 40.0, 50.0, 60.0, 75.0):
                    try:
                        r = bases.dimensionar_base(
                            perf, N_Sd=N, M_Sd=M, H_Sd=V,
                            fck=mat.concreto(d.fck_MPa).fck,
                            pedestal=(B + sobra, L + sobra), aco_placa=d.aco_chapas,
                            n_chumbadores=n, diametro_chumbador=diam, h_ef=h_ef,
                            B=B, L=L)
                    except ErroDeDados:
                        continue          # combinação inviável: tenta a próxima
                    primeiro = primeiro or r
                    if _base_aceita(r):
                        melhor = r
                        break
                if melhor:
                    break
            if melhor:
                break
        if melhor:
            break
    escolhida = melhor or primeiro
    if escolhida is None:
        p.avisos.append("Não foi possível dimensionar a base do pilar com as chapas e "
                        "chumbadores do catálogo. Use base com enrijecedores, pedestal "
                        "maior ou aço de maior resistência.")
        return

    # o arrancamento do cone de concreto simples é verificação do projeto de fundações:
    # quando não passa, a saída é armadura de suspensão, dimensionada pela NBR 6118
    for v in escolhida.verificacoes:
        if "cone" in v.titulo.lower() and not v.ok:
            v.dispensada = True
            v.observacao = ((v.observacao + " ") if v.observacao else "") + (
                "O concreto simples não ancora a tração do grupo: é obrigatória armadura "
                "de suspensão no pedestal, dimensionada pela NBR 6118 no projeto de "
                "fundações. Verificação transferida para aquele projeto.")
            p.avisos.append(
                "Base do pilar: a ancoragem dos chumbadores exige armadura de suspensão no "
                "pedestal (NBR 6118). Informe ao projetista de fundações a tração de "
                "cálculo indicada no memorial.")
    if not escolhida.ok:
        p.avisos.append("A base do pilar não fecha com os chumbadores do catálogo; "
                        "aumente o pedestal, o fck ou use barras de maior resistência.")
    p.base = escolhida


def _base_aceita(r) -> bool:
    """Aprovada, tratando o cone de concreto como pendência da fundação."""
    return all(v.ok or v.dispensada or "cone" in v.titulo.lower()
               for v in r.verificacoes)


# ----------------------------------------------- 10. lista de material

def _lista_de_material(p: ProjetoGalpao):
    d = p.dados
    n_port = d.n_porticos
    pecas: List[Peca] = []

    def add(marca, descricao, perfil_nome, qtd, comp_m, material=None, obs=""):
        try:
            perf = achar_perfil(perfil_nome)
        except Exception:
            perf = _perfil_sintetico(perfil_nome)
        massa = perf.massa if perf else 0.0
        perimetro = _perimetro_pintura(perf) if perf else 0.0
        if not massa:
            p.avisos.append("Peça %s (%s) sem massa conhecida: o peso dela ficou fora "
                            "da lista de material." % (marca, perfil_nome))
        peso_u = massa * comp_m
        pecas.append(Peca(marca=marca, descricao=descricao, perfil=perfil_nome,
                          material=material or d.aco_perfis, quantidade=qtd,
                          comprimento_m=round(comp_m, 2),
                          peso_unit_kg=round(peso_u, 1),
                          peso_total_kg=round(peso_u * qtd, 1),
                          area_pintura_m2=round(perimetro * comp_m * qtd, 1),
                          observacao=obs))

    pilar = p.elemento("Pilar")
    viga = p.elemento("Viga")
    terca = p.elemento("Terça")
    cob = p.elemento("Contraventamento de cobertura")
    vert = p.elemento("Contraventamento vertical")

    if pilar:
        add("P1", "Pilar do pórtico", pilar.perfil, 2 * n_port, d.pe_direito)
    if viga:
        add("V1", "Viga do pórtico (uma água)", viga.perfil, 2 * n_port, d.comprimento_agua)
    if terca:
        linhas = terca.geometria.get("linhas", 0) * 2          # duas águas
        vaos = n_port - 1
        add("T1", "Terça", terca.perfil, linhas * vaos, d.espacamento_porticos,
            material=d.aco_tercas)
        n_corr = terca.geometria.get("n_correntes", 0)
        if n_corr:
            pecas.append(Peca(marca="TC", descricao="Corrente/tirante de terça ø 16 mm",
                              perfil="Barra ø 16 mm", material=d.aco_chapas,
                              quantidade=linhas * vaos * n_corr,
                              comprimento_m=round(terca.geometria.get("espacamento_m", 1.6), 2),
                              peso_unit_kg=round(1.58 * terca.geometria.get("espacamento_m", 1.6), 2),
                              peso_total_kg=round(1.58 * terca.geometria.get("espacamento_m", 1.6)
                                                  * linhas * vaos * n_corr, 1),
                              area_pintura_m2=0.0))
    # longarinas de fechamento lateral, com o perfil verificado em _longarinas
    longarina = p.elemento("Longarina")
    n_long = int(longarina.geometria.get("fiadas_por_lado", 0)) if longarina else 0
    n_long = n_long or max(2, int(d.pe_direito / 2))
    perfil_long = longarina.perfil if longarina else (terca.perfil if terca else "")
    if perfil_long:
        add("L1", "Longarina de fechamento", perfil_long, n_long * 2 * (n_port - 1),
            d.espacamento_porticos, material=d.aco_tercas)
    if cob:
        add("CC", "Diagonal de contraventamento de cobertura", cob.perfil,
            int(cob.geometria.get("quantidade", 8)),
            cob.geometria.get("comprimento_m", 5.0))
    if vert:
        add("CV", "Diagonal de contraventamento vertical", vert.perfil,
            int(vert.geometria.get("quantidade", 8)),
            vert.geometria.get("comprimento_m", 5.0))

    peso_perfis = sum(x.peso_total_kg for x in pecas)
    # chapas de ligação e base, e parafusos, por percentual usual
    pecas.append(Peca(marca="CH", descricao="Chapas de ligação, bases e enrijecedores",
                      perfil="Chapa", material=d.aco_chapas, quantidade=1,
                      comprimento_m=0.0, peso_unit_kg=round(peso_perfis * 0.05, 1),
                      peso_total_kg=round(peso_perfis * 0.05, 1),
                      area_pintura_m2=round(peso_perfis * 0.05 * 0.025, 1),
                      observacao="estimativa de 5 % do peso dos perfis"))
    pecas.append(Peca(marca="PF", descricao="Parafusos, chumbadores e acessórios",
                      perfil="Diversos", material=d.parafuso, quantidade=1,
                      comprimento_m=0.0, peso_unit_kg=round(peso_perfis * 0.03, 1),
                      peso_total_kg=round(peso_perfis * 0.03, 1), area_pintura_m2=0.0,
                      observacao="estimativa de 3 % do peso dos perfis"))
    p.lista_material = pecas

    total = sum(x.peso_total_kg for x in pecas)
    p.resumo_pesos = {
        "perfis_kg": round(peso_perfis, 1),
        "chapas_kg": round(peso_perfis * 0.05, 1),
        "parafusos_kg": round(peso_perfis * 0.03, 1),
        "total_kg": round(total, 1),
        "kg_por_m2": round(total / d.area_coberta, 2) if d.area_coberta else 0.0,
        "area_pintura_m2": round(sum(x.area_pintura_m2 for x in pecas), 1),
    }
    custo_total = total * d.custo_kg
    p.custo = {
        "custo_kg": d.custo_kg,
        "material": round(custo_total * 0.55, 2),
        "fabricacao": round(custo_total * 0.22, 2),
        "pintura": round(custo_total * 0.08, 2),
        "montagem": round(custo_total * 0.15, 2),
        "total": round(custo_total, 2),
        "por_m2": round(custo_total / d.area_coberta, 2) if d.area_coberta else 0.0,
        "observacao": "percentuais indicativos; confirme com orçamento de fornecedor.",
    }
    if p.resumo_pesos["kg_por_m2"] > 45:
        p.avisos.append(f"Consumo de {p.resumo_pesos['kg_por_m2']} kg/m² está acima da faixa "
                        f"usual de galpões (18 a 35 kg/m²). Reveja vão, espaçamento e cargas.")


def _perfil_sintetico(nome: str):
    """Perfis que o dimensionamento cria fora do catálogo, como os tirantes redondos."""
    m = re.search(r"\u00f8\s*([\d.,]+)\s*mm", nome or "")
    if nome and nome.lower().startswith("barra redonda") and m:
        return _barra_redonda(float(m.group(1).replace(",", ".")))
    return None


def _perimetro_pintura(perf: Perfil) -> float:
    """Perímetro de pintura aproximado, em m²/m."""
    if perf.tipo == "I":
        return (4 * perf.bf + 2 * perf.d - 2 * perf.tw) / 1000
    if perf.tipo == "tubo":
        return 4 * perf.bf / 1000 if perf.dados.get("tipo") != "redondo" else math.pi * perf.d / 1000
    if perf.tipo in ("U", "Ue"):
        return (2 * perf.bf + 2 * perf.d) / 1000 * 1.1
    if perf.tipo == "L":
        return 4 * perf.bf / 1000
    if perf.tipo == "barra":
        return math.pi * perf.d / 1000
    return 0.5
