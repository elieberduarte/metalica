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

from . import (analise, bases, cargas, catalogo, ligacoes, materiais as mat,
               nbr8800, nbr14762, tesouras)
from .base import ErroDeDados, Resultado, Verificacao, fmt
from . import verificar
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
        b=d.vao, a=d.comprimento, h=d.altura_beiral, theta_graus=d.angulo_telhado,
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

    forcada = d.perfil_forcado("perfil_terca")
    opcoes = nbr14762.dimensionar_terca(
        aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
        correntes=(d.linhas_correntes,) if d.linhas_correntes else (0, 1, 2),
        inclinacao=d.angulo_telhado,
        carga_servico_gravidade=q_serv_grav, carga_servico_succao=q_serv_suc,
        apenas_aprovados=True)
    catalogo_tercas = list(opcoes)
    if forcada is not None:
        # o perfil escolhido é verificado com as mesmas cargas; reprovado, ele fica e o
        # projetista vê a razão — a lista dos que passam continua disponível ao lado
        opcoes = nbr14762.dimensionar_terca(
            aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
            correntes=(d.linhas_correntes,) if d.linhas_correntes else (0, 1, 2),
            inclinacao=d.angulo_telhado, carga_servico_gravidade=q_serv_grav,
            carga_servico_succao=q_serv_suc, apenas_aprovados=False, perfis=[forcada])
        opcoes.sort(key=lambda r: (not r.ok, r.razao))
        if opcoes and not opcoes[0].ok:
            p.avisos.append("A terça escolhida (%s) não passa (aproveitamento %.2f): veja os perfis "
                            "que passam na lista do elemento." % (forcada.nome, opcoes[0].razao))
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
        alternativas=_alternativas_de_opcoes(catalogo_tercas or opcoes))
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

    altura = d.altura_fechamento or d.altura_beiral
    n_fiadas = max(2, int(d.altura_beiral / 2))   # mesmo critério da lista de material
    esp = altura / n_fiadas                        # faixa de parede por fiada, m
    q_p = 1.4 * max(pressao, 0.0) * esp
    q_s = 1.4 * abs(min(succao, 0.0)) * esp
    servico = dict(carga_servico_gravidade=max(pressao, 0.0) * esp,
                   carga_servico_succao=abs(min(succao, 0.0)) * esp)
    base = dict(aco=d.aco_tercas, vao=d.espacamento_porticos, carga_gravidade=q_p,
                carga_succao=q_s, inclinacao=0.0, **servico)

    opcoes = nbr14762.dimensionar_terca(correntes=(max(1, d.linhas_correntes),),
                                        apenas_aprovados=True, **base)
    catalogo_long = list(opcoes)
    forcada_long = d.perfil_forcado("perfil_longarina")
    if forcada_long is not None:
        # o perfil escolhido é verificado com as mesmas cargas; reprovado, ele fica e o
        # projetista vê a razão — a lista dos que passam continua ao lado
        opcoes = nbr14762.dimensionar_terca(correntes=(0, 1, 2, 3), apenas_aprovados=False,
                                            perfis=[forcada_long], **base)
        opcoes.sort(key=lambda r: (not r.ok, r.razao))
        if opcoes and not opcoes[0].ok:
            p.avisos.append("A longarina escolhida (%s) não passa (aproveitamento %.2f): veja os "
                            "perfis que passam na lista do elemento." % (forcada_long.nome, opcoes[0].razao))
    if not opcoes and forcada_long is None:
        opcoes = nbr14762.dimensionar_terca(correntes=(1, 2, 3), apenas_aprovados=True, **base)
        if opcoes:
            p.avisos.append("As longarinas precisaram de %s linha(s) de correntes."
                            % opcoes[0].dados.get("n_correntes"))
    if not opcoes and forcada_long is None:
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
        alternativas=_alternativas_de_opcoes(catalogo_long or opcoes)))


# --------------------------------------------------------- 4. análise do pórtico

def _barras_carregadas(modelo):
    """(água barlavento, água sotavento, pilar esquerdo, pilar direito), por rótulo.

    O modelo diz quais barras formam cada água e cada pilar — na tesoura são muitas, no
    pórtico de alma cheia são a viga e, junto ao joelho, a mísula. A mísula entra: ela é
    um sexto de cada água e deixá-la sem carga tirava esse tanto do telhado.
    """
    dd = getattr(modelo, "dados", None) or {}
    agua_esq = list(dd.get("barras_agua_esq") or [])
    agua_dir = list(dd.get("barras_agua_dir") or [])
    if not agua_esq:
        agua_esq = [b for b in ("misula_esq", "viga_esq") if _tem_barra(modelo, b)] or [1]
        agua_dir = [b for b in ("viga_dir", "misula_dir") if _tem_barra(modelo, b)] or [2]
    pil_esq = list(dd.get("barras_pilar_esq") or [])
    pil_dir = list(dd.get("barras_pilar_dir") or [])
    if not pil_esq:
        pil_esq = [b for b in ("pilar_esq",) if _tem_barra(modelo, b)] or [0]
        pil_dir = [b for b in ("pilar_dir",) if _tem_barra(modelo, b)] or [3]
    return agua_esq, agua_dir, pil_esq, pil_dir


def _carregar_portico(modelo, p: ProjetoGalpao, pilar: Perfil, viga: Perfil, pp=None):
    """Aplica os casos de carga elementares no modelo do pórtico.

    `pp` permite informar o peso próprio em kN/m quando ele não sai de um perfil só,
    como na tesoura: ``{"agua": q, "pilar": q, "extras": {rótulo: q}}``.
    """
    d = p.dados
    s = d.espacamento_porticos                      # largura de influência, m
    g = p.cargas["g_cobertura"]
    sc = d.sobrecarga_cobertura
    crit = _pressoes_criticas(p)

    # peso próprio do pórtico, estimado pelos perfis adotados (kN/m na barra)
    pp = pp or {}
    pp_viga = pp.get("agua", viga.massa * 9.81e-3 if viga else 0.5)
    pp_pilar = pp.get("pilar", pilar.massa * 9.81e-3 if pilar else 0.5)

    agua_esq, agua_dir, pil_esq, pil_dir = _barras_carregadas(modelo)
    barras_viga = agua_esq + agua_dir
    barras_pilar = pil_esq + pil_dir

    # o modelo trabalha em kN e cm: as cargas de kN/m entram divididas por 100
    M = 1 / 100.0

    # --- permanente ---
    for b in barras_viga:
        modelo.distribuida("PP", b, -(g * s + pp_viga) * M, "global_y")
    for b in barras_pilar:
        modelo.distribuida("PP", b, -pp_pilar * M, "global_y")
    for rot, q in (pp.get("extras") or {}).items():
        modelo.distribuida("PP", rot, -q * M, "global_y")
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
        for b in agua_esq:
            modelo.distribuida(caso, b, -c["telhado_barlavento"] * s * M, "perpendicular")
        for b in agua_dir:
            modelo.distribuida(caso, b, -c["telhado_sotavento"] * s * M, "perpendicular")
        # paredes: pressão horizontal nos pilares, ambas no sentido do vento
        for b in pil_esq:
            modelo.distribuida(caso, b, c["parede_barlavento"] * s * M, "global_x")
        for b in pil_dir:
            modelo.distribuida(caso, b, -c["parede_sotavento"] * s * M, "global_x")
    return crit


def _tem_barra(modelo, rotulo) -> bool:
    try:
        modelo.indice_barra(rotulo)
        return True
    except Exception:
        return False


def _analise_portico(p: ProjetoGalpao):
    """Analisa e dimensiona o pórtico — de alma cheia ou treliçado.

    O caminho treliçado está em `_analise_tesoura`; daqui para baixo é o pórtico de
    alma cheia, com viga e pilar.
    """
    if p.dados.eh_trelicado:
        return _analise_tesoura(p)
    return _analise_alma_cheia(p)


def _analise_alma_cheia(p: ProjetoGalpao):
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
        verificar_viga = (lambda perf, esf=esf, Lb=Lb_viga: nbr8800.verificar_viga(
            perf, a, L=d.comprimento_agua * 100, M_Sd=esf["viga"]["M"],
            V_Sd=esf["viga"]["V"], Lb=Lb, Cb=1.14,
            limite="L/%d" % d.flecha_viga, q_servico=_q_servico_viga(p),
            elemento="Viga do pórtico"))
        res_viga = _menor_perfil(verificar_viga, altura_min=200, forcado=d.perfil_forcado("perfil_viga"))

        # pilar: flexo-compressao, com altura minima proxima a da viga para nao ficar
        # tao flexivel a ponto de empurrar todo o momento para a cumeeira
        h_min_pilar = max(200.0, achar_perfil(res_viga.perfil).d * 0.8)
        verificar_pilar = (lambda perf, esf=esf: nbr8800.flexao_composta(
            perf, a, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"],
            Lx=H, Ly=Ly, Kx=Kx, Ky=1.0, Lb=Ly, Cb=1.67, elemento="Pilar"))
        res_pilar = _menor_perfil(verificar_pilar, altura_min=h_min_pilar, forcado=d.perfil_forcado("perfil_pilar"))

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
    if d.perfil_forcado("perfil_pilar") is None:
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

    # os W em volta do adotado, verificados nos esforços finais: é a lista que a tela
    # oferece para trocar o perfil sem sair do que passa
    verificar_viga_final = (lambda perf: nbr8800.verificar_viga(
        perf, a, L=d.comprimento_agua * 100, M_Sd=esf["viga"]["M"], V_Sd=esf["viga"]["V"],
        Lb=Lb_viga, Cb=1.14, limite="L/%d" % d.flecha_viga, q_servico=_q_servico_viga(p),
        elemento="Viga do pórtico"))
    verificar_pilar_final = (lambda perf: nbr8800.flexao_composta(
        perf, a, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"], Lx=H, Ly=Ly, Kx=Kx, Ky=1.0,
        Lb=Ly, Cb=1.67, elemento="Pilar"))
    p.elementos.append(ElementoDimensionado(
        nome="Viga do pórtico", perfil=res_viga.perfil, material=d.aco_perfis,
        resultado=res_viga, alternativas=_alternativas_W(verificar_viga_final, res_viga.perfil),
        esforcos={"M_kNcm": round(esf["viga"]["M"], 1),
                  "M_kNm": round(esf["viga"]["M"] / 100, 1),
                  "V_kN": round(esf["viga"]["V"], 1),
                  "caso": esf["viga"].get("caso_M", "")},
        geometria={"Lb_cm": round(Lb_viga, 1),
                   "comprimento_m": round(d.comprimento_agua, 2),
                   "misula_m": d.comprimento_misula if d.com_misula else 0.0}))
    p.elementos.append(ElementoDimensionado(
        nome="Pilar", perfil=res_pilar.perfil, material=d.aco_perfis,
        resultado=res_pilar, alternativas=_alternativas_W(verificar_pilar_final, res_pilar.perfil),
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

    # A viga é dimensionada pelo momento e pelo cortante **fora** da mísula: ali a seção
    # é maior, e o esforço daquele trecho é o que dimensiona a ligação de joelho, não a
    # viga. Por isso saem dois cortantes — o da viga e o do joelho, que a ligação usa.
    barras_viga = ["viga_esq", "viga_dir"]
    M_viga, caso_v = maior(barras_viga, "M")
    V_viga, _ = maior(barras_viga, "V")
    V_joelho_, _ = maior(barras_viga + ["misula_esq", "misula_dir"], "V")
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
        "viga": {"M": abs(M_viga), "V": abs(V_viga), "V_joelho": abs(V_joelho_),
                 "N": abs(N_viga),
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


def _menor_perfil(verificar, altura_min=200.0, familia="W", forcado=None):
    """Primeiro perfil do catalogo (do mais leve ao mais pesado) que passa em tudo.
    Com `forcado` (o perfil escolhido pelo usuário) só ele é verificado."""
    if forcado is not None:
        return verificar(forcado)
    ultimo = None
    for perf in banco().candidatos("I", familia, altura_min=altura_min):
        r = verificar(perf)
        ultimo = r
        if r.ok:
            return r
    return ultimo


def _alternativas_W(verificar, adotado: str, limite: int = 12) -> list:
    """Os W em volta do adotado, verificados nos mesmos esforços: quem passa primeiro."""
    try:
        h = achar_perfil(adotado).d
    except Exception:
        h = 0.0
    saida = []
    for perf in banco().candidatos("I", "W"):
        if h and not (0.6 * h <= perf.d <= 1.8 * h):
            continue
        try:
            r = verificar(perf)
        except ErroDeDados:
            continue
        saida.append({"perfil": perf.nome, "razao": round(r.razao, 3), "ok": bool(r.ok),
                      "massa": round(perf.massa or 0.0, 2)})
    saida.sort(key=lambda x: (not x["ok"], x["massa"] if x["ok"] else x["razao"]))
    return saida[:limite]


def _deslocamento_horizontal(p: ProjetoGalpao, modelo) -> dict:
    """Deslocamento do topo do pilar na combinacao de servico com vento."""
    d = p.dados
    try:
        r = analise.resolver(modelo, "S vento")
        i = modelo.indice_no((modelo.dados or {}).get("no_joelho") or "B")
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


# ------------------------------------------------ 6b. pórtico treliçado

#: Alvo do espaçamento entre travamentos laterais do banzo inferior, cm. Sob sucção o
#: banzo inferior comprime, e quem o segura são as linhas que ligam uma tesoura à
#: vizinha. 3,5 m equivale ao travamento a cada dois nós, que é como se detalha — e é o
#: que decide o peso do banzo inferior, porque ele entra como L_y na flambagem.
ALVO_TRAVAMENTO = 350.0

#: Relação mínima entre o comprimento do painel e a altura do perfil do banzo. É a
#: regra clássica da treliça: banzo mais alto que isso deixa de trabalhar por força
#: normal e passa a puxar para si o momento da continuidade — o nó rotulado que a
#: treliça pressupõe deixa de existir, e o dimensionamento entra em círculo (quanto mais
#: pesado o banzo, mais momento ele atrai).
PAINEL_POR_ALTURA_DO_BANZO = 8.0

#: Nome de cada família de barra da tesoura na lista de elementos.
NOME_DA_BARRA = {
    "banzo superior": "Banzo superior da tesoura",
    "banzo inferior": "Banzo inferior da tesoura",
    "diagonal": "Diagonal da tesoura",
    "montante": "Montante da tesoura",
}


def _geometria_tesoura(p: ProjetoGalpao) -> "tesouras.Tesoura":
    d = p.dados
    esp = (p.cargas.get("espacamento_tercas_real") or d.espacamento_tercas) * 100
    return tesouras.geometria(
        vao=d.vao * 100, inclinacao=d.inclinacao / 100.0,
        formato=d.formato_tesoura, diagonais=d.diagonais_tesoura,
        altura_apoio=d.altura_tesoura * 100, paineis=d.paineis_tesoura,
        espacamento_tercas=esp)


def _opcoes_de_travamento(t) -> List[Tuple[float, int]]:
    """Passos de travamento do banzo inferior, do mais espaçado ao mais cerrado.

    O banzo inferior traciona sob gravidade e **comprime sob sucção** — é o caso que
    governa o galpão leve. Fora do plano quem o segura são as linhas que ligam o banzo
    de uma tesoura ao da vizinha, e elas só podem cair num nó: por isso o passo é sempre
    um múltiplo inteiro do painel. Começa no mais espaçado que faz sentido montar
    (`ALVO_TRAVAMENTO`) e fecha até um painel — o dimensionamento escolhe o primeiro que
    deixa o banzo passar, que é a decisão que o projetista toma na prancha.
    """
    barras = t.do_papel("banzo inferior")
    if not barras:
        return [(t.vao, 0)]
    passo = t.comprimento_total("banzo inferior") / len(barras)
    maior = max(1, int(round(ALVO_TRAVAMENTO / passo)))
    saida = []
    for k in range(maior, 0, -1):
        trechos = int(math.ceil(len(barras) / float(k)))
        saida.append((k * passo, max(0, trechos - 1)))
    return saida


def _perfis_semente(t, d: DadosGalpao) -> dict:
    """Ponto de partida do laço: alturas usuais, que o dimensionamento depois corrige."""
    h_banzo = max(75.0, t.vao / 12.0)          # mm
    h_web = max(50.0, t.vao / 30.0)
    semente = {"pilar": _perfil_proximo(max(d.vao * 1000 / 45, d.pe_direito * 1000 / 20))}
    for papel in tesouras.PAPEIS:
        if not t.do_papel(papel):
            continue
        alvo = h_banzo if papel.startswith("banzo") else h_web
        semente[papel] = tesouras.perfil_proximo(tesouras.FAMILIAS_POR_PAPEL[papel], alvo)
    return semente


def _peso_proprio_tesoura(t, perfis: dict, d: Optional[DadosGalpao] = None) -> dict:
    """Peso da tesoura repartido entre os dois banzos, em kN/m de barra.

    As diagonais e os montantes não têm carga própria no modelo — o peso deles entra
    metade em cada banzo, que é onde ele de fato chega. Perfil duplo pesa o dobro."""
    massa = {papel: (perfis[papel].massa or 0.0) * (d.pecas_por_barra(papel) if d else 1)
             for papel in tesouras.PAPEIS if papel in perfis and t.do_papel(papel)}
    peso_web = sum(massa.get(x, 0.0) * t.comprimento_total(x) / 100.0
                   for x in ("diagonal", "montante"))                 # kg
    l_sup = max(t.comprimento_total("banzo superior") / 100.0, 1.0)
    l_inf = max(t.comprimento_total("banzo inferior") / 100.0, 1.0)
    q_sup = (massa.get("banzo superior", 0.0) + peso_web / 2.0 / l_sup) * 9.81e-3
    q_inf = (massa.get("banzo inferior", 0.0) + peso_web / 2.0 / l_inf) * 9.81e-3
    return {"agua": q_sup, "pilar": (perfis["pilar"].massa or 0.0) * 9.81e-3,
            "extras": {b.rotulo: q_inf for b in t.do_papel("banzo inferior")}}


def _rodar_tesoura(p: ProjetoGalpao, t, perfis: dict):
    """Monta o modelo da tesoura com os perfis dados, carrega e devolve a envoltória.
    No perfil duplo a barra entra com o dobro da área e da inércia."""
    d = p.dados
    secoes = {k: (v.A * d.pecas_por_barra(k), v.Ix * d.pecas_por_barra(k)) for k, v in perfis.items()}
    modelo = tesouras.montar(t, d.pe_direito * 100, secoes,
                             base_rotulada=d.base_rotulada, ligacao=d.ligacao_tesoura)
    _carregar_portico(modelo, p, perfis["pilar"], perfis.get("banzo superior"),
                      pp=_peso_proprio_tesoura(t, perfis, d))
    modelo.validar()
    combos = _combinar(modelo, p, None)
    env = analise.envoltoria(modelo, [c for c in combos if c.startswith("C")])
    return modelo, env, combos


def _esforcos_da_tesoura(env, modelo, t, d: DadosGalpao) -> dict:
    """Pior esforço de cada família de barras, com a barra e o caso que mandam.

    A tesoura é fabricada com um perfil por família, então o que dimensiona é o extremo
    entre todas as barras dela: a maior compressão, a maior tração e — nos banzos, que
    são contínuos — o maior momento local do trecho entre nós.
    """
    saida = {}
    pular = {"mont_esq", "mont_dir"} if d.ligacao_tesoura == "rígida" else set()
    for papel in tesouras.PAPEIS:
        barras = [b for b in t.do_papel(papel) if b.rotulo not in pular]
        if not barras:
            continue
        e = {"N_c": 0.0, "N_t": 0.0, "M": 0.0, "V": 0.0, "L": 0.0, "n": len(barras),
             "barra_N": "", "caso_N": "", "barra_M": "", "caso_M": ""}
        for b in barras:
            e["L"] = max(e["L"], t.comprimento(b))
            try:
                eb = env.barra(b.rotulo)
            except Exception:
                continue
            for ext in (eb.N_max, eb.N_min):
                v = _v(ext)
                if v < 0 and -v > e["N_c"]:
                    e["N_c"], e["barra_N"], e["caso_N"] = -v, b.rotulo, _caso(ext)
                elif v > e["N_t"]:
                    e["N_t"] = v
            for ext in (eb.M_max, eb.M_min):
                if abs(_v(ext)) > e["M"]:
                    e["M"], e["barra_M"], e["caso_M"] = abs(_v(ext)), b.rotulo, _caso(ext)
            for ext in (eb.V_max, eb.V_min):
                e["V"] = max(e["V"], abs(_v(ext)))
        saida[papel] = e

    ep = {"N_c": 0.0, "N_t": 0.0, "M": 0.0, "V": 0.0, "caso_M": "", "caso_N": ""}
    for rot in ((modelo.dados or {}).get("barras_pilar") or []):
        try:
            eb = env.barra(rot)
        except Exception:
            continue
        for ext in (eb.N_max, eb.N_min):
            v = _v(ext)
            if v < 0 and -v > ep["N_c"]:
                ep["N_c"], ep["caso_N"] = -v, _caso(ext)
            elif v > ep["N_t"]:
                ep["N_t"] = v
        for ext in (eb.M_max, eb.M_min):
            if abs(_v(ext)) > ep["M"]:
                ep["M"], ep["caso_M"] = abs(_v(ext)), _caso(ext)
        for ext in (eb.V_max, eb.V_min):
            ep["V"] = max(ep["V"], abs(_v(ext)))
    saida["pilar"] = ep
    return saida


def _flecha_tesoura(p: ProjetoGalpao, modelo, t) -> Optional[Verificacao]:
    """Flecha da tesoura na combinação de serviço, contra o limite L/flecha_viga."""
    d = p.dados
    try:
        r = analise.resolver(modelo, "S rara gravidade")
    except Exception:
        return None
    flecha = 0.0
    for n in t.nos:
        try:
            flecha = max(flecha, abs(r.deslocamento(modelo.indice_no(n.nome))[1]))
        except Exception:
            continue
    limite = d.vao * 100.0 / d.flecha_viga
    v = Verificacao("Flecha da tesoura (combinação rara de serviço)",
                    norma="NBR 8800:2008, Anexo C", Sd=flecha, Rd=limite, unidade="cm")
    v.passo("Limite adotado", "L/%d" % d.flecha_viga,
            "%s / %d" % (fmt(d.vao * 100, 0, "cm"), d.flecha_viga), fmt(limite, 2, "cm"))
    v.passo("Flecha calculada", "", "maior deslocamento vertical dos nós da tesoura",
            fmt(flecha, 2, "cm"))
    return v


def _analise_tesoura(p: ProjetoGalpao):
    """Analisa e dimensiona a tesoura e os pilares juntos, até os perfis se repetirem.

    O caminho é o mesmo do pórtico de alma cheia — análise e dimensionamento no mesmo
    laço, porque a rigidez depende do perfil e o perfil depende do esforço —, com três
    diferenças que vêm da treliça:

    * os banzos entram **contínuos**, então o banzo superior é verificado à
      flexo-compressão: a terça o carrega entre os nós;
    * cada família de barras recebe um perfil só, o mais leve do catálogo que passa em
      todas as barras dela;
    * fora do plano, o banzo superior é travado pelas terças e o banzo inferior pelas
      linhas de travamento, cujo espaçamento é o que entra como L_y.
    """
    d = p.dados
    a = mat.aco(d.aco_perfis)
    t = _geometria_tesoura(p)
    esp_terca = (p.cargas.get("espacamento_tercas_real") or d.espacamento_tercas) * 100
    opcoes_trava = _opcoes_de_travamento(t)
    trava, n_travas = opcoes_trava[0]
    perfis = _perfis_semente(t, d)
    H = d.pe_direito * 100
    Kx = 2.0 if d.base_rotulada else 1.5
    Ly_pilar = min(H, 300.0)

    def fora_do_plano(papel: str, e: dict) -> float:
        if papel == "banzo superior":
            return esp_terca
        if papel == "banzo inferior":
            return trava
        return e["L"]

    def altura_max(papel: str, e: dict) -> float:
        """Altura de seção aceita, em mm (só os banzos têm limite)."""
        if not papel.startswith("banzo"):
            return 0.0
        return max(100.0, e["L"] * 10.0 / PAINEL_POR_ALTURA_DO_BANZO)

    # o laço só fecha quando a escolha feita sobre uma análise devolve os mesmos perfis
    # que a geraram: aí a verificação final é feita sobre os esforços daquela análise, e
    # não sobre outros, que é o que deixava o perfil escolhido reprovando no fim
    historico, modelo, env, combos, esf = [], None, None, None, {}
    deslocs, subidas = [], 0
    for _ in range(12):
        modelo, env, combos = _rodar_tesoura(p, t, perfis)
        esf = _esforcos_da_tesoura(env, modelo, t, d)
        novos = dict(perfis)
        for papel in tesouras.PAPEIS:
            e = esf.get(papel)
            if not e:
                continue
            forcado = d.perfil_forcado("perfil_" + papel.replace(" ", "_"))
            n_pecas = d.pecas_por_barra(papel)
            if papel == "banzo inferior":
                # o passo do travamento é parte da escolha: fecha-se a malha de
                # travamento até o banzo passar, antes de engrossar o perfil
                perf = None
                for cand_trava, cand_linhas in opcoes_trava:
                    perf, _r = tesouras.menor_perfil(
                        tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"],
                        e["N_t"], e["M"], e["L"], cand_trava, NOME_DA_BARRA[papel],
                        altura_max=altura_max(papel, e), n=n_pecas, forcado=forcado)
                    trava, n_travas = cand_trava, cand_linhas
                    if _r is not None and _r.ok:
                        break
                if perf is not None:
                    novos[papel] = perf
                continue
            perf, _r = tesouras.menor_perfil(
                tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"], e["N_t"],
                e["M"], e["L"], fora_do_plano(papel, e), NOME_DA_BARRA[papel],
                altura_max=altura_max(papel, e), n=n_pecas, forcado=forcado)
            if perf is None:
                raise ErroDeDados(
                    "Nenhum perfil do catálogo atende ao %s da tesoura com altura de até "
                    "%s (um oitavo do painel). Aumente a altura da tesoura, reduza o vão "
                    "ou aproxime os pórticos."
                    % (papel, fmt(altura_max(papel, e), 0, "mm")))
            novos[papel] = perf
        ep = esf["pilar"]
        r_pilar = _menor_perfil(
            lambda perf: nbr8800.flexao_composta(
                perf, a, N_Sd=ep["N_c"], Mx_Sd=ep["M"], Lx=H, Ly=Ly_pilar,
                Kx=Kx, Ky=1.0, Lb=Ly_pilar, Cb=1.67, elemento="Pilar"),
            altura_min=200.0, forcado=d.perfil_forcado("perfil_pilar"))
        novos["pilar"] = achar_perfil(r_pilar.perfil)

        # Em galpão de base rotulada quem governa o pilar não é a resistência, é o
        # deslocamento do topo: sobe-se o perfil enquanto cada degrau render mais de
        # 2 % — daí em diante o que limita é a rigidez do pórtico inteiro, e engrossar
        # só o pilar encarece sem resolver.
        desloc_atual = _deslocamento_horizontal(p, modelo)
        deslocs.append(desloc_atual.get("u_cm", 0.0) if desloc_atual else 0.0)
        rendeu = len(deslocs) < 2 or deslocs[-2] <= 0 or (
            (deslocs[-2] - deslocs[-1]) / deslocs[-2] > 0.02)
        if (desloc_atual and desloc_atual.get("razao", 0) > 1.0 and subidas < 8
                and (rendeu or subidas == 0) and d.perfil_forcado("perfil_pilar") is None):
            acima = [c for c in banco().candidatos("I", "W")
                     if (c.massa or 0) > (perfis["pilar"].massa or 0)]
            if acima:
                proximo = min(acima, key=lambda c: c.massa)
                if (novos["pilar"].massa or 0) <= (perfis["pilar"].massa or 0):
                    novos["pilar"] = proximo
                    subidas += 1

        chave = tuple(sorted((k, v.nome) for k, v in novos.items()))
        if all(novos[k].nome == perfis[k].nome for k in novos):
            break                              # ponto fixo: a escolha devolveu a entrada
        if chave in historico:
            # ciclo entre dois conjuntos: fica com o mais pesado de cada família e para
            perfis = {k: max((perfis[k], novos[k]), key=lambda x: x.massa or 0.0)
                      for k in novos}
            modelo, env, combos = _rodar_tesoura(p, t, perfis)
            esf = _esforcos_da_tesoura(env, modelo, t, d)
            break
        historico.append(chave)
        perfis = novos

    desloc = _deslocamento_horizontal(p, modelo)
    flecha = _flecha_tesoura(p, modelo, t)

    ep = esf["pilar"]
    p.esforcos = {
        "modelo": modelo, "envoltoria": env, "combinacoes": combos,
        "casos_modelo": combos,
        "tesoura": t.resumo(), "geometria_tesoura": t,
        "pilar": {"N": ep["N_c"], "N_t": ep["N_t"], "M": ep["M"], "V": ep["V"],
                  "caso_M": ep["caso_M"]},
        "deslocamento": desloc,
        "travamento_banzo_inferior_m": round(trava / 100.0, 2),
        "linhas_de_travamento": n_travas,
        "iteracoes": len(historico),
    }
    for papel in tesouras.PAPEIS:
        if papel in esf:
            p.esforcos["N_c_%s_kN" % papel.replace(" ", "_")] = round(esf[papel]["N_c"], 1)
            p.esforcos["N_t_%s_kN" % papel.replace(" ", "_")] = round(esf[papel]["N_t"], 1)
    p.combinacoes = _combinacoes_documentadas(p)

    for papel in tesouras.PAPEIS:
        e = esf.get(papel)
        if not e:
            continue
        perf = perfis[papel]
        Ly = fora_do_plano(papel, e)
        n_pecas = d.pecas_por_barra(papel)
        r = verificar.verificar_membro(perf, d.aco_perfis, e["N_c"], e["N_t"], e["M"],
                                       e["L"], Ly, n_pecas, NOME_DA_BARRA[papel], p.avisos)
        alternativas = tesouras.candidatos_verificados(
            tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"], e["N_t"], e["M"],
            e["L"], Ly, NOME_DA_BARRA[papel], altura_ref=perf.d, altura_max=altura_max(papel, e),
            n=n_pecas)
        if papel == "banzo inferior" and flecha is not None:
            r.add(flecha)
        if not r.ok:
            p.avisos.append(
                "O %s não passa nem com o perfil mais pesado de altura compatível com o "
                "painel (%s, aproveitamento %s). A tesoura está rasa para o vão: aumente "
                "a altura dela, reduza o vão ou aproxime os pórticos."
                % (NOME_DA_BARRA[papel].lower(), perf.nome, fmt(r.razao, 2)))
        if papel.startswith("banzo") and perf.d >= altura_max(papel, e) - 1.0:
            p.avisos.append(
                "O %s ficou na altura máxima admitida (%s, um oitavo do painel de %s). "
                "Menos painéis por água — painel mais longo — deixam o banzo trabalhar "
                "melhor." % (NOME_DA_BARRA[papel].lower(), fmt(perf.d, 0, "mm"),
                             fmt(e["L"] / 100, 2, "m")))
        p.elementos.append(ElementoDimensionado(
            nome=NOME_DA_BARRA[papel], perfil=perf.nome, material=d.aco_perfis, resultado=r,
            alternativas=alternativas,
            esforcos={"N_compressao_kN": round(e["N_c"], 1),
                      "N_tracao_kN": round(e["N_t"], 1),
                      "M_kNm": round(e["M"] / 100, 2),
                      "barra": e["barra_N"] or e["barra_M"],
                      "caso": e["caso_N"] or e["caso_M"]},
            geometria={"barras_por_tesoura": e["n"], "pecas_por_barra": n_pecas,
                       "comprimento_max_m": round(e["L"] / 100, 2),
                       "Lx_cm": round(e["L"], 1), "Ly_cm": round(Ly, 1),
                       "comprimento_total_m": round(t.comprimento_total(papel) / 100, 2)}))

    verificar_pilar_final = (lambda perf: nbr8800.flexao_composta(
        perf, a, N_Sd=ep["N_c"], Mx_Sd=ep["M"], Lx=H, Ly=Ly_pilar,
        Kx=Kx, Ky=1.0, Lb=Ly_pilar, Cb=1.67, elemento="Pilar"))
    r_pilar = verificar_pilar_final(perfis["pilar"])
    p.elementos.append(ElementoDimensionado(
        nome="Pilar", perfil=perfis["pilar"].nome, material=d.aco_perfis, resultado=r_pilar,
        alternativas=_alternativas_W(verificar_pilar_final, perfis["pilar"].nome),
        esforcos={"N_kN": round(ep["N_c"], 1), "N_tracao_kN": round(ep["N_t"], 1),
                  "M_kNcm": round(ep["M"], 1), "M_kNm": round(ep["M"] / 100, 1),
                  "V_kN": round(ep["V"], 1), "caso": ep["caso_M"]},
        geometria={"altura_m": d.pe_direito, "Kx": Kx, "Ly_cm": Ly_pilar}))

    _travamento(p, t, esf, n_travas, trava)
    if n_travas > 6:
        p.avisos.append(
            "O banzo inferior precisou de %d linhas de travamento por tesoura, a cada %s. "
            "Tanto travamento é sinal de tesoura rasa: aumentar a altura dela sai mais "
            "barato do que a malha de travamento."
            % (n_travas, fmt(trava / 100, 2, "m")))

    if desloc and desloc.get("razao", 0) > 1.0:
        p.avisos.append(
            "O deslocamento horizontal do topo do pilar (%s) passa do limite %s. Engaste "
            "a base, aproxime os pórticos ou aumente o pilar."
            % (fmt(desloc["u_cm"], 2, "cm"), desloc.get("criterio", "")))
    if flecha is not None and not flecha.ok:
        p.avisos.append("A flecha da tesoura passa do limite adotado: aumente a altura da "
                        "tesoura, que é o que mais rende, antes de engrossar os banzos.")


def _travamento(p: ProjetoGalpao, t, esf: dict, n_linhas: int, trava: float):
    """Travamento lateral do banzo inferior: tirante redondo com esticador.

    A força vem da regra de barra de travamento (NBR 8800, item 4.11): quem trava leva
    2 % da força do que é travado. O tirante corre de tesoura a tesoura, ao longo de
    todo o galpão, e descarrega no contraventamento — o mesmo arranjo da corrente de
    terça. Sem essas linhas o L_y adotado para o banzo inferior não existe na obra, e o
    banzo comprimido sob sucção fica com o dobro ou o triplo do comprimento suposto.
    """
    d = p.dados
    e = esf.get("banzo inferior")
    if not e or n_linhas <= 0:
        return
    N = max(0.02 * e["N_c"], 2.0)
    L = d.espacamento_porticos * 100
    r = _dimensionar_tirante(N, L, mat.aco(d.aco_chapas), "Travamento do banzo inferior")
    if not r.ok:
        p.avisos.append("O tirante de travamento do banzo inferior não atende nem com o "
                        "maior diâmetro; adote cantoneira ou tubo nessa linha.")
    p.elementos.append(ElementoDimensionado(
        nome="Travamento do banzo inferior", perfil=r.perfil, material=d.aco_chapas,
        resultado=r,
        esforcos={"N_kN": round(N, 1), "N_banzo_kN": round(e["N_c"], 1),
                  "criterio": "2 % da compressão do banzo (NBR 8800, item 4.11)"},
        geometria={"linhas_por_tesoura": n_linhas,
                   "espacamento_travado_m": round(trava / 100, 2),
                   "comprimento_m": round(d.espacamento_porticos, 2),
                   "quantidade": n_linhas * max(1, d.n_porticos - 1)}))


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
    area_oitao = d.vao * (d.altura_beiral + (d.altura_cumeeira - d.altura_beiral) / 2) / 2
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
    """Ligações do pórtico: chapa de topo no de alma cheia, chapa de nó no treliçado."""
    if p.dados.eh_trelicado:
        return _ligacoes_tesoura(p)
    return _ligacoes_alma_cheia(p)


def _ligacoes_tesoura(p: ProjetoGalpao):
    """Chapa de nó da diagonal mais solicitada e ligação da tesoura ao pilar.

    São as duas ligações que decidem a tesoura. A chapa de nó (gusset) recebe a diagonal
    mais carregada e é verificada pela seção de Whitmore, pelo bloco de cisalhamento e
    pelos parafusos. A ligação ao pilar leva o cortante do pórtico e, sob sucção, a
    **tração de arrancamento** — que no galpão leve costuma ser o que manda nela.
    """
    d = p.dados
    diag = p.elemento("Diagonal da tesoura") or p.elemento("Montante da tesoura")
    if diag is not None:
        N = max(diag.esforcos.get("N_compressao_kN", 0.0),
                diag.esforcos.get("N_tracao_kN", 0.0))
        perf = catalogo.perfil_de(diag.perfil)
        largura = max(4.0, (getattr(perf, "bf", 0.0) or 50.0) / 10.0)      # cm
        t_barra = max(0.2, (tesouras._espessura(perf) if perf else 2.0) / 10.0)
        melhor = None
        # mais parafusos alargam a seção de Whitmore e aliviam a chapa: por isso a busca
        # cresce primeiro no número de parafusos e só depois na espessura
        for t_chapa in (0.63, 0.80, 0.95, 1.27, 1.60, 1.90, 2.24):
            for diam in ('5/8"', '3/4"'):
                passo = ligacoes.espacamento_recomendado(
                    1.5875 if diam == '5/8"' else 1.905)
                for n_par in (2, 3, 4, 5, 6):
                    r = ligacoes.gusset_contraventamento(
                        N_Sd=N, t_gusset=t_chapa, largura_ligacao=largura,
                        comprimento_ligacao=(n_par - 1) * passo, aco_gusset=d.aco_chapas,
                        diametro=diam, parafuso=d.parafuso, n_parafusos=n_par, passo=passo,
                        t_barra=t_barra, aco_barra=d.aco_perfis, eletrodo=d.eletrodo,
                        elemento="Chapa de nó da tesoura")
                    if melhor is None or r.razao < melhor.razao:
                        melhor = r
                    if r.ok:
                        break
                if melhor is not None and melhor.ok:
                    break
            if melhor is not None and melhor.ok:
                break
        if melhor is not None:
            melhor.dados["N_Sd_kN"] = round(N, 1)
            if not melhor.ok:
                p.avisos.append("A chapa de nó da tesoura não fecha com as espessuras "
                                "testadas: aumente a aba da diagonal ou solde a diagonal "
                                "direto no banzo.")
            p.ligacoes["nó da tesoura"] = melhor

    ep = p.esforcos.get("pilar") or {}
    Ft, Fv = abs(ep.get("N_t", 0.0)), abs(ep.get("V", 0.0))
    aco_ch = mat.aco(d.aco_chapas)
    melhor = None
    for diam in ('5/8"', '3/4"', '7/8"'):
        borda = max(ligacoes.distancia_borda_minima(diam)[0], 3.5)
        for n_par in (2, 4, 6):
            r = Resultado("Ligação tesoura–pilar", perfil="%d × %s" % (n_par, diam),
                          material=d.parafuso)
            r.add(ligacoes.interacao_tracao_cisalhamento(diam, d.parafuso,
                                                         Ft / n_par, Fv / n_par))
            r.add(ligacoes.esmagamento(diam, t_chapa=1.60, fu=aco_ch.fu,
                                       distancia_borda=borda, Fc_Sd=Fv / n_par,
                                       nome_chapa="chapa de topo do pilar"))
            r.dados.update({"n_parafusos": n_par, "diametro": diam,
                            "F_tracao_kN": round(Ft, 1), "V_kN": round(Fv, 1),
                            "t_chapa_cm": 1.60, "distancia_borda_cm": round(borda, 1)})
            melhor = r
            if r.ok:
                break
        if melhor is not None and melhor.ok:
            break
    if melhor is not None:
        if not melhor.ok:
            p.avisos.append("A ligação da tesoura no pilar não fecha com até 6 parafusos "
                            "de 7/8\": reveja o arrancamento sob sucção.")
        p.ligacoes["tesoura-pilar"] = melhor


def _ligacoes_alma_cheia(p: ProjetoGalpao):
    """Ligação de joelho e de cumeeira por chapa de topo, buscando a configuração
    mais econômica que atenda a todas as verificações."""
    d = p.dados
    viga = p.elemento("Viga")
    if not viga:
        return
    perf_viga = achar_perfil(viga.perfil)

    # --- joelho: seção da mísula e momento do joelho ---
    M_joelho = abs(p.esforcos.get("joelho_kNm", 0.0)) * 100 or p.esforcos["viga"]["M"]
    V_joelho = p.esforcos["viga"].get("V_joelho") or p.esforcos["viga"]["V"]

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

    quantidades = (2, 4) if d.base_rotulada else (4, 6, 8)
    diametros = ('3/4"', '7/8"', '1"', '1.1/8"', '1.1/4"')
    # A placa é retangular, e as duas dimensões servem a coisas diferentes: **L**, na
    # direção do momento, é o que dá braço ao chumbador tracionado, e crescer nela
    # ajuda; **B**, perpendicular, é balanço puro a partir da mesa, e crescer nela só
    # aumenta o momento na chapa. Uma placa quadrada grande, que era o que se tentava
    # antes, pedia 30 cm de espessura numa base engastada e nenhuma chapa comercial
    # servia — a base ficava sem dimensionar em todo galpão de base engastada.
    lado_L = max(25.0, perf.d / 10.0)
    lado_B = max(20.0, perf.bf / 10.0)
    tamanhos = sorted(((lado_B + fb, lado_L + fl)
                       for fb in (10.0, 15.0, 22.0) for fl in (10.0, 20.0, 30.0, 45.0)),
                      key=lambda bl: bl[0] * bl[1])
    # o pedestal precisa sobrar bem além da placa: é o concreto à frente da chave de
    # cisalhamento que resiste ao empuxo horizontal
    sobras_pedestal = (40.0, 60.0, 80.0)
    melhor, primeiro = None, None
    for (B, L), sobra in ((t_, s_) for t_ in tamanhos for s_ in sobras_pedestal):
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
    if d.eh_trelicado:
        _lista_da_tesoura(p, add, n_port)
    elif viga:
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
    n_long = n_long or max(2, int(d.altura_beiral / 2))
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


def _alternativas_de_opcoes(opcoes, limite: int = 12) -> list:
    """Lista de alternativas a partir dos `Resultado` de uma busca no catálogo."""
    saida = []
    vistos = set()
    for o in opcoes:
        if o.perfil in vistos:
            continue
        vistos.add(o.perfil)
        try:
            massa = catalogo.perfil_de(o.perfil).massa
        except Exception:
            massa = None
        saida.append({"perfil": o.perfil, "razao": round(o.razao, 3), "ok": bool(o.ok),
                      "massa": round(massa, 2) if massa else None})
    saida.sort(key=lambda x: (not x["ok"], (x["massa"] or 0.0) if x["ok"] else x["razao"]))
    return saida[:limite]


def _lista_da_tesoura(p: ProjetoGalpao, add, n_port: int):
    """Peças da tesoura: banzo por água e as barras internas agrupadas por comprimento.

    Os banzos saem inteiros por água (a emenda é na cumeeira, como se fabrica). Diagonais
    e montantes vão agrupados por comprimento, que é o romaneio que a fábrica corta —
    numa tesoura simétrica são poucos comprimentos distintos.
    """
    d = p.dados
    t = p.esforcos.get("geometria_tesoura")
    if t is None:
        return
    marca = {"banzo superior": "BS", "banzo inferior": "BI", "diagonal": "D",
             "montante": "M"}
    pular = {"mont_esq", "mont_dir"} if d.ligacao_tesoura == "rígida" else set()
    for papel in tesouras.PAPEIS:
        el = p.elemento(NOME_DA_BARRA[papel])
        barras = [b for b in t.do_papel(papel) if b.rotulo not in pular]
        if el is None or not barras:
            continue
        n_pecas = int(el.geometria.get("pecas_por_barra") or 1)
        duplo = " (perfil duplo, 2 peças por barra)" if n_pecas == 2 else ""
        if papel.startswith("banzo"):
            add(marca[papel], "%s (meia tesoura)%s" % (NOME_DA_BARRA[papel], duplo), el.perfil,
                2 * n_port * n_pecas, t.comprimento_total(papel) / 200.0)
            continue
        grupos = {}
        for b in barras:
            c = round(t.comprimento(b) / 100.0, 2)
            grupos[c] = grupos.get(c, 0) + 1
        for i, comp in enumerate(sorted(grupos, reverse=True), start=1):
            add("%s%d" % (marca[papel], i), NOME_DA_BARRA[papel] + duplo, el.perfil,
                grupos[comp] * n_port * n_pecas, comp)
    trav = p.elemento("Travamento do banzo inferior")
    if trav is not None and trav.geometria.get("quantidade"):
        add("TV", "Travamento lateral do banzo inferior", trav.perfil,
            int(trav.geometria["quantidade"]), trav.geometria.get("comprimento_m", 0.0))


def _perfil_sintetico(nome: str):
    """Perfis que o dimensionamento cria fora do catálogo: tirantes redondos e as séries
    formadas a frio da tesoura, que são montadas pelo nome."""
    m = re.search(r"\u00f8\s*([\d.,]+)\s*mm", nome or "")
    if nome and nome.lower().startswith("barra redonda") and m:
        return _barra_redonda(float(m.group(1).replace(",", ".")))
    try:
        return catalogo.perfil_de(nome)
    except Exception:
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
