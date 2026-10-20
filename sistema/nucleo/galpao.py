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
from .modelo_galpao import DadosGalpao, ElementoDimensionado, Peca, ProjetoGalpao, REPARTICAO_CUSTO
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
    ajustados, aviso_vaos = _vaos_iguais(dados)
    p = ProjetoGalpao(dados=ajustados, dados_entrada=dados if aviso_vaos else None)
    if aviso_vaos:
        p.avisos.append(aviso_vaos)
    try:
        _cargas_permanentes(p)
        _vento(p)
        _tercas(p)
        _longarinas(p)
        _analise_portico(p)
        _contraventamentos(p)
        _tercas_escora(p)
        _oitao(p)
        _longarinas_das_pontas(p)
        _ligacoes(p)
        _base(p)
        _lista_de_material(p)
    except ErroDeDados as e:
        p.erros.append(str(e))
    except Exception as e:                      # falha inesperada não pode derrubar a interface
        p.erros.append(f"falha no dimensionamento: {type(e).__name__}: {e}")
    return p


def _vaos_iguais(d: DadosGalpao):
    """O comprimento dividido em vãos iguais, nunca maiores que o espaçamento pedido.

    Com 42 m e 5 m, o 3D punha 8 vãos de 5 m e empurrava o último pórtico para os 42 m: o
    último vão ficava com 7 m e terças, longarinas e pórtico tinham sido verificados para 5 m.
    Devolve (dados, aviso), com o aviso só quando o espaçamento mudou."""
    if not d.vaos_iguais:
        return d, None
    n = max(1, math.ceil(d.comprimento / d.espacamento_porticos - 1e-6))
    esp = round(d.comprimento / n, 4)
    if abs(esp - d.espacamento_porticos) < 0.005:
        return d, None
    sobra = d.comprimento - (round(d.comprimento / d.espacamento_porticos) - 1) * d.espacamento_porticos
    return replace(d, espacamento_porticos=esp), (
        "Espaçamento entre pórticos ajustado de %s para %s m: os %s m de comprimento divididos em %d vãos "
        "iguais (com %s m, o último vão ficaria com %s m)."
        % (fmt(d.espacamento_porticos, 2), fmt(esp, 2), fmt(d.comprimento, 2), n,
           fmt(d.espacamento_porticos, 2), fmt(sobra, 2)))


# --------------------------------------------------------------- 1. cargas

def _cargas_permanentes(p: ProjetoGalpao):
    d = p.dados
    # nomes antigos da tela ("trapezoidal 0,50 mm") pela tabela; os de hoje ("telha sanduíche",
    # "telha cerâmica", da lista da NBR 6120) direto — antes qualquer outro nome virava telha
    # metálica de 0,05 kN/m², e a cerâmica (0,70) era calculada como metálica
    telha_nome = TELHAS.get(d.telha, d.telha or "telha metálica simples")
    valor_telha = PESO_TELHA.get(d.telha)
    comp = cargas.peso_proprio_cobertura(
        telha=telha_nome, com_forro=d.carga_forro > 0, com_tercas=True,
        com_acessorios=True, instalacoes=d.carga_extra,
        valor_telha=valor_telha,
        valor_forro=d.carga_forro if d.carga_forro > 0 else None)
    # NBR 6120:2019, item 6.4: a sobrecarga de cobertura sem acesso é 0,25 kN/m² só a
    # partir de 3 % de inclinação; em telhado mais plano ela sobe até 0,50 (auditoria C4)
    sc_min = cargas.sobrecarga_cobertura(cargas.inclinacao_em_pct(d.angulo_telhado))
    sc = d.sobrecarga_cobertura
    if sc < sc_min - 1e-9:
        p.avisos.append(
            "Sobrecarga de cobertura elevada de %s para %s kN/m²: mínimo da NBR 6120:2019 "
            "(item 6.4) para a inclinação de %s %%."
            % (fmt(sc, 2), fmt(sc_min, 2), fmt(cargas.inclinacao_em_pct(d.angulo_telhado), 1)))
        sc = sc_min
    p.cargas = {
        "composicao": comp,
        "g_cobertura": comp.total,                       # kN/m²
        "sobrecarga": sc,
        "sobrecarga_minima_6120": sc_min,
        "parcelas": [{"item": it.descricao, "valor": it.valor, "fonte": getattr(it, "fonte", "")}
                     for it in getattr(comp, "itens", [])],
        "passos": comp.passos() if hasattr(comp, "passos") else [],
    }


# --------------------------------------------------------------- 2. vento

def _vento(p: ProjetoGalpao):
    d = p.dados
    v0 = cargas.velocidade_basica(d.cidade) if d.cidade else d.v0
    altura_ref = d.altura_cumeeira
    # o S3 da tela é o valor do grupo escolhido (NBR 6123:2023, Tabela 4); antes ele era
    # lido e descartado, e o vento saía sempre com S3 = 1,00 (auditoria C3)
    s3 = float(d.fator_estatistico or 1.0)
    casos_cpi, razao = _casos_cpi_da_tela(p)
    vg = cargas.pressoes_galpao(
        b=d.vao, a=d.comprimento, h=d.altura_beiral, theta_graus=d.angulo_telhado,
        V0=v0, categoria=d.categoria_rugosidade, classe=d.classe, z=altura_ref,
        S1=d.fator_topografico, aberturas=d.aberturas, S3=s3,
        casos_cpi=casos_cpi, razao_areas=razao)
    p.vento = {
        "objeto": vg, "V0": v0, "S1": vg.S1, "S2": vg.S2, "S3": vg.S3, "grupo": vg.grupo,
        "Vk": vg.Vk, "q": vg.q, "tabela": vg.tabela(),
        "passos": getattr(vg, "passos", []),
    }


def _casos_cpi_da_tela(p: ProjetoGalpao):
    """Os casos de C_pi das situações de abertura que a tela oferece e que precisam de um
    dado a mais (NBR 6123, item 6.2.5): devolve (casos_cpi, razao_areas).

    * abertura dominante a barlavento — a tela não pede a razão de áreas; adota-se a
      faixa mais severa (≥ 6 → C_pi = +0,8) e o projetista é avisado;
    * abertura dominante a sotavento ou em face paralela — C_pi = C_e da face onde está
      a abertura, lido dos próprios coeficientes do galpão (um caso por direção de vento).
    As demais situações (duas faces opostas, quatro faces, estanque) ficam com os casos
    padrão do módulo de cargas.
    """
    d = p.dados
    k = cargas._chave(d.aberturas)
    if "dominante" not in k and "portao" not in k:
        return None, None
    if "barlavento" in k:
        p.avisos.append("Abertura dominante a barlavento sem a razão de áreas: adotado "
                        "C_pi = +0,8 (razão ≥ 6, o caso mais severo da NBR 6123, item 6.2.5).")
        return None, 6.0
    coef = cargas.coeficientes_pressao_galpao(d.vao, d.comprimento, d.altura_beiral,
                                              d.angulo_telhado)
    if "sotavento" in k:
        faces = [("parede lateral sotavento", "transversal", "B"),
                 ("oitão sotavento", "longitudinal", "D")]
        texto = "abertura dominante a sotavento"
    else:
        faces = [("parede lateral zona 1", "longitudinal", "A1/B1"),
                 ("oitão zona 1", "transversal", "C1/D1")]
        texto = "abertura dominante em face paralela ao vento"
    casos = []
    for sup, dire, letra in faces:
        ce = coef.busca(sup, dire).Ce
        casos.append(cargas.CasoCpi(ce, f"C_pi = {fmt(ce, 2)}",
                                    f"{texto}: C_pi = C_e da face {letra} (vento {dire})",
                                    "NBR 6123, item 6.2.5"))
    # o vento sopra de qualquer direção (NBR 6123, 5.1): a mesma abertura fica a barlavento
    # quando o vento vem pelo lado dela. Sem a razão de áreas, entra o caso mais severo
    # (+0,8); sem ele, a cobertura saía quase sem sucção
    casos += cargas.coeficiente_pressao_interna("abertura dominante a barlavento", razao_areas=6.0)
    p.avisos.append("Abertura dominante: além de C_pi = C_e da face (%s), foi verificado o vento "
                    "entrando pela abertura, C_pi = +0,8 (razão de áreas ≥ 6, NBR 6123, item "
                    "6.2.5)." % texto)
    # dois valores iguais viram um caso só
    unicos = []
    for c in casos:
        if not any(abs(c.valor - u.valor) < 1e-9 for u in unicos):
            unicos.append(c)
    return unicos, None


def _rotulos_cpi(casos) -> list:
    """Um rótulo curto por caso de C_pi: "cpi+" e "cpi-" quando são dois (o maior e o
    menor), senão o próprio valor ("cpi+0.5"). São os sufixos dos casos de vento do
    modelo ("Vcpi+", "Vcpi-")."""
    vals = [c.valor for c in casos]
    if len(casos) == 2 and vals[0] != vals[1]:
        return ["cpi+" if v == max(vals) else "cpi-" for v in vals]
    return ["cpi%+.1f" % v for v in vals]


def _pressoes_criticas(p: ProjetoGalpao) -> dict:
    """As pressões que governam o pórtico: sucção máxima no telhado e pressão lateral,
    uma entrada por caso de C_pi da situação de aberturas escolhida.

    Antes os casos eram fixos em +0,2 e −0,3 (as "duas faces opostas"), e qualquer outra
    escolha da tela — estanque, quatro faces, portão aberto — não encontrava a pressão e
    devolvia 0,0: o pórtico era calculado sem vento (auditoria C1). Agora a superfície
    que faltar levanta erro em vez de zerar.
    """
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
            raise ErroDeDados(
                "pressão de vento não encontrada para %s (vento %s, C_pi = %s): o pórtico "
                "não pode ser calculado sem essa pressão." % (chaves[0], direcao, fmt(cpi, 2)))
        return min(cands) if escolher == "min" else max(cands)

    saida = {}
    for caso, rot in zip(vg.casos_cpi, _rotulos_cpi(vg.casos_cpi)):
        cpi = caso.valor
        saida[rot] = {
            "cpi": cpi, "descricao": caso.nome,
            "telhado_barlavento": pega(["barlavento (ef)", "água de barlavento", "telhado barlavento"],
                                       "transversal", cpi),
            "telhado_sotavento": pega(["sotavento (gh)", "água de sotavento", "telhado sotavento"],
                                      "transversal", cpi),
            "parede_barlavento": pega(["parede lateral barlavento", "barlavento (a)"],
                                      "transversal", cpi, "max"),
            "parede_sotavento": pega(["parede lateral sotavento", "sotavento (b)"],
                                     "transversal", cpi),
        }
    if not saida:
        raise ErroDeDados("nenhum caso de pressão interna para a situação de aberturas "
                          "'%s'." % p.dados.aberturas)
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

    vao, q_grav, q_suc, succao, comuns = _cargas_da_terca(p, esp)

    def busca(correntes, apenas_aprovados, perfis=None):
        return nbr14762.dimensionar_terca(
            aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
            correntes=correntes, apenas_aprovados=apenas_aprovados, perfis=perfis, **comuns)

    forcada = d.perfil_forcado("perfil_terca")
    correntes = (d.linhas_correntes,) if d.linhas_correntes else (0, 1, 2)
    opcoes = busca(correntes, True)
    catalogo_tercas = list(opcoes)
    if forcada is not None:
        # o perfil escolhido é verificado com as mesmas cargas; reprovado, ele fica e o
        # projetista vê a razão — a lista dos que passam continua disponível ao lado
        opcoes = busca(correntes, False, perfis=[forcada])
        opcoes.sort(key=lambda r: (not r.ok, r.razao))
        if opcoes and not opcoes[0].ok:
            p.avisos.append("A terça escolhida (%s) não passa (aproveitamento %.2f): veja os perfis "
                            "que passam na lista do elemento." % (forcada.nome, opcoes[0].razao))
    if not opcoes:
        # tenta liberar o número de correntes antes de desistir
        opcoes = busca((1, 2, 3), True)
        if opcoes:
            p.avisos.append(
                f"Com {d.linhas_correntes} linha(s) de correntes nenhuma terça do catálogo "
                f"atende; foram adotadas {opcoes[0].dados.get('n_correntes')} linha(s).")
    if not opcoes:
        opcoes = busca((1, 2, 3), False)
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


def _cargas_da_terca(p: ProjetoGalpao, esp: float):
    """(vão, q gravidade, q sucção, sucção crítica, argumentos comuns) da terça a `esp` m."""
    d = p.dados
    g = p.cargas["g_cobertura"]              # kN/m²
    sc = p.cargas["sobrecarga"]
    crit = _pressoes_criticas(p)
    # sucção mais severa entre todos os casos de C_pi
    succao = min(min(c["telhado_barlavento"], c["telhado_sotavento"]) for c in crit.values())

    vao = d.espacamento_porticos
    # gravidade: 1,25·g + 1,5·sc  (permanente de pequena variabilidade, NBR 8800 Tab. 1)
    q_grav = (1.25 * g + 1.5 * sc) * esp
    # sucção: 1,4·vento aliviado por 1,0·g (permanente favorável). O módulo da NBR 14762
    # espera a sucção como valor positivo (para cima), daí o sinal invertido.
    q_suc = max(0.0, (1.4 * abs(succao) - 1.0 * g) * esp)
    q_serv_grav = (g + sc) * esp
    q_serv_suc = max(0.0, (abs(succao) - g) * esp)
    # NBR 6120:2019, item 6.4: 1 kN concentrado no meio do vão, só com a permanente
    # (auditoria C4) — governa nos vãos curtos
    comuns = dict(inclinacao=d.angulo_telhado, carga_servico_gravidade=q_serv_grav,
                  carga_servico_succao=q_serv_suc,
                  carga_concentrada=1.5 * cargas.CARGA_CONCENTRADA_COBERTURA,
                  carga_permanente=1.25 * g * esp,
                  limite_flecha_gravidade=float(d.flecha_terca))

    return vao, q_grav, q_suc, succao, comuns


#: Força de escora acima disto (kN) faz a terça ser verificada à flexo-compressão.
N_ESCORA_MIN = 0.5


def _forca_de_escora(p: ProjetoGalpao) -> float:
    """Compressão na terça que é montante da treliça do contraventamento de cobertura (kN).

    A treliça horizontal do vão contraventado vence o vão do galpão entre os beirais e recebe
    o vento do oitão nos nós (F/n em cada um); com o X só à tração, o montante interno mais
    carregado — a terça na linha do nó — leva o cortante do painel vizinho ao do apoio, F/2 −
    F/n, e nunca menos que a carga de um nó. Antes não se verificava: na análise 3D do 20×40
    (V0 45) a terça dessas linhas dava 160 % com N = 24 kN."""
    cob = p.elemento("Contraventamento de cobertura")
    if cob is None:
        return 0.0
    F = float(cob.esforcos.get("F_oitao_kN") or 0.0)
    n = int(cob.geometria.get("paineis") or 2)
    return max(F / 2.0 - F / n, F / n) if n >= 3 else F / 2.0


def _flexo_compressao_terca(p: ProjetoGalpao, perfil_nome: str, n_corr: int, N: float,
                            res_flexao=None, titulo: str = "terça como escora do contraventamento de cobertura",
                            origem: Tuple[str, str] = ("Força de escora (montante da treliça de cobertura)",
                                                       "N = F/2 − F/n")) -> Verificacao:
    """NBR 14762:2010, item 9.9: N/N_Rd + M_Sd/M_Rd ≤ 1, com o momento da sucção (o mesmo vento)
    amplificado por 1/(1 − N/N_ex). `res_flexao`: o Resultado da terça com esse perfil."""
    d = p.dados
    sec = nbr14762.secao_do_perfil(achar_perfil(perfil_nome))
    L = d.espacamento_porticos * 100.0
    Lc = L / (n_corr + 1)
    vc = nbr14762.compressao_mrd(sec, d.aco_tercas, N_Sd=N, KxLx=L, KyLy=Lc, KtLt=Lc)
    flex = next((v for v in (res_flexao.verificacoes if res_flexao else [])
                 if "sucção" in v.titulo and "Flexão Mx" in v.titulo), None)
    M_sd, M_rd = (abs(flex.Sd), abs(flex.Rd)) if flex else (0.0, 1.0)
    N_ex = math.pi ** 2 * nbr14762.E * sec.Ix / L ** 2
    amp = 1.0 / max(1e-6, 1.0 - N / N_ex)
    soma = N / vc.Rd + amp * M_sd / M_rd if vc.Rd > 0 else float("inf")
    v = Verificacao("Flexo-compressão — " + titulo,
                    norma="NBR 14762:2010, item 9.9", Sd=round(soma, 4), Rd=1.0, unidade="—")
    v.passo(origem[0], origem[1], "", fmt(N, 1, "kN"))
    v.passo("Compressão resistente", "N_c,Rd (9.8.2), KxLx = L, KyLy = KtLt = L/(correntes+1)",
            "L = %s; L/(n+1) = %s" % (fmt(L, 0, "cm"), fmt(Lc, 0, "cm")), fmt(vc.Rd, 1, "kN"))
    v.passo("Momento de sucção amplificado", "M_Sd/(1 − N/N_ex)",
            "%s / (1 − %s/%s)" % (fmt(M_sd, 1), fmt(N, 1), fmt(N_ex, 0)),
            fmt(amp * M_sd, 1, "kN·cm"))
    v.passo("Interação", "N/N_Rd + M/M_Rd ≤ 1", "%s/%s + %s/%s" % (
        fmt(N, 1), fmt(vc.Rd, 1), fmt(amp * M_sd, 1), fmt(M_rd, 1)), fmt(soma, 2))
    return v


def _mao_francesa(p: ProjetoGalpao, N: float, L_cm: float, elemento: str) -> Optional[Resultado]:
    """A cantoneira mais leve que leva N (kN) à compressão no comprimento L (cm)."""
    aco = nbr8800._aco(p.dados.aco_chapas)
    ultimo = None
    # a partir de L 1½": menor que isso não cabe o parafuso com borda (pensar na execução, 14/10)
    for perf in [c for c in banco().candidatos(tipo="L") if float(c.dados.get("b") or c.d or 0) >= 38.0]:
        try:
            r = nbr8800.compressao(perf, aco, Lx=L_cm, Ly=L_cm, N_Sd=N, cantoneira_simplificada=True,
                                   elemento=elemento)
        except ErroDeDados:
            continue
        ultimo = r
        if r.ok:
            return r
    return ultimo


def _maos_francesas_viga(p: ProjetoGalpao, Lb_cm: float, esf_viga: dict, viga: Perfil):
    """As mãos-francesas que a viga de alma cheia sob sucção supõe: o cálculo a verifica com a mesa de
    baixo travada a cada `Lb` (vão/4 até 3 m), e quem trava é a mão-francesa da terça à mesa de baixo
    — antes ela não existia no 3D nem na lista (usuário, 20/10: gerar). Uma a cada m terças, nos dois
    lados da viga; a força é 2 % da força na mesa (NBR 8800, item 4.11) ÷ cos 45°."""
    d = p.dados
    passo = float(p.cargas.get("espacamento_tercas_real") or d.espacamento_tercas)
    n_lin = int(p.cargas.get("linhas_tercas_por_agua") or 0)
    terca = p.elemento("Terça")
    if n_lin <= 0 or terca is None:
        return
    m = max(1, int(Lb_cm / 100.0 / passo + 1e-9))
    linhas = list(range(m - 1, n_lin, m))
    if not linhas:
        return
    braco = max(1.0, (viga.d - viga.tf) / 10.0)                 # cm
    N = max(0.02 * abs(esf_viga.get("M", 0.0)) / braco * math.sqrt(2.0), 2.0)
    d_t = achar_perfil(terca.perfil).d
    h = (viga.d + d_t / 2.0) / 10.0                              # cm, da mesa de baixo ao eixo da terça
    L = math.sqrt(2.0) * h
    r = _mao_francesa(p, N, L, "Mão-francesa da viga")
    if r is None:
        return
    # só nos pórticos internos: na ponta a viga leva meia faixa e a mesa de baixo é travada pelos pilaretes
    # de oitão (com o topo solto; com o apoiado a ponta é a viga de oitão)
    lados = 2 * max(0, d.n_porticos - 2)
    p.elementos.append(ElementoDimensionado(
        nome="Mão-francesa da viga", perfil=r.perfil, material=d.aco_chapas, resultado=r,
        esforcos={"N_kN": round(N, 2), "criterio": "2 % da força na mesa ÷ cos 45° (NBR 8800, item 4.11)"},
        geometria={"linhas_de_terca": [j + 1 for j in linhas], "a_cada": m, "Lb_m": round(Lb_cm / 100.0, 2),
                   "comprimento_m": round(L / 100.0, 3), "quantidade": 2 * len(linhas) * lados}))


#: Peso do fechamento lateral em telha metálica, por m² de fachada, já com a longarina (cargas.PESOS).
PESO_FECHAMENTO = 0.125


def _obliqua_com_peso(p: ProjetoGalpao, res, vao_m: float, n_corr: int, faixa_m: float) -> Verificacao:
    """Flexão oblíqua da longarina (NBR 14762, 9.8.2.5): o momento do vento no eixo forte com o peso do
    fechamento no eixo fraco, que vence de corrente a corrente. A verificação da terça reaproveitada para
    a parede não tinha o peso (inclinação 0): na análise 3D a longarina de oitão ia a 145 % por ele."""
    sec = nbr14762.secao_do_perfil(achar_perfil(res.perfil))
    Lw = vao_m / (int(n_corr) + 1)
    My = 1.25 * PESO_FECHAMENTO * faixa_m * Lw ** 2 / 8.0 * 100.0           # kN·cm
    vy = nbr14762.flexao_em_y_mrd(sec, p.dados.aco_tercas, M_Sd=My)
    mx = [v for v in res.verificacoes if v.titulo.startswith("Flexão Mx") and v.Rd]
    pior = max(mx, key=lambda v: v.razao) if mx else None
    vi = nbr14762.interacao_flexao_obliqua(pior.Sd if pior else 0.0, pior.Rd if pior else 1.0, My, vy.Rd)
    vi.titulo = "Flexão oblíqua — vento no eixo forte + peso do fechamento entre correntes"
    vi.passo("Peso no eixo fraco", "M_y = 1,25 · g · faixa · (L/(correntes+1))²/8",
             "g = %s kN/m²; faixa = %s; L/(n+1) = %s" % (fmt(PESO_FECHAMENTO, 3), fmt(faixa_m, 2, "m"),
                                                       fmt(Lw, 2, "m")), fmt(My, 1, "kN·cm"))
    return vi


def _com_peso_do_fechamento(p: ProjetoGalpao, opcoes, vao_m: float, faixa_m: float):
    """A primeira das `opcoes` (a mais leve) que passa também na flexão oblíqua com o peso; nenhuma: a
    primeira, com a verificação reprovada à vista."""
    for r in opcoes:
        v = _obliqua_com_peso(p, r, vao_m, int(r.dados.get("n_correntes") or 0), faixa_m)
        if v.ok and r.ok:
            r.add(v)
            return r
    r = opcoes[0]
    r.add(_obliqua_com_peso(p, r, vao_m, int(r.dados.get("n_correntes") or 0), faixa_m))
    return r


def _longarinas_das_pontas(p: ProjetoGalpao):
    """A longarina lateral dos vãos das pontas leva, além do vento da parede, a reação do pilar de canto,
    que dobra no eixo fraco sob o vento do oitão (meio painel de fachada) e se apoia nas fiadas: ela a
    leva comprimida até o pórtico seguinte. Na análise 3D do 20×40, 8,6 kN e 113 % — o cálculo só
    a verificava à flexão. N = 1,25 · 1,4 · w · (painel/2) · faixa da fiada (o apoio interno de uma
    viga contínua sobre as fiadas). Quando a comum não passa, só essas (L2) ganham perfil próprio."""
    d = p.dados
    lg, po = p.elemento("Longarina"), p.elemento("Pilar de oitão")
    if lg is None or po is None:
        return
    cotas = lg.geometria.get("cotas_fiadas_m") or []
    if not cotas:
        return
    pres, suc = _vento_oitao(p)
    w = max(pres, abs(suc))
    faixa = float(lg.geometria.get("espacamento_m") or (cotas[1] - cotas[0] if len(cotas) > 1 else cotas[0]))
    N = 1.25 * 1.4 * w * float(po.geometria.get("largura_m") or 0.0) / 2.0 * faixa
    if N < N_ESCORA_MIN:
        return
    n_corr = int(lg.geometria.get("n_correntes") or 0)
    titulo = "longarina do vão da ponta (reação do pilar de canto sob o vento do oitão)"
    origem = ("Reação do pilar de canto na fiada", "N = 1,25 · 1,4 · w · (painel/2) · faixa")
    v = _flexo_compressao_terca(p, lg.perfil, n_corr, N, lg.resultado, titulo, origem)
    lg.esforcos["N_ponta_kN"] = round(N, 2)
    if v.ok:
        lg.resultado.add(v)
        return
    e = lg.esforcos
    base = dict(aco=d.aco_tercas, vao=d.espacamento_porticos, carga_gravidade=e["q_pressao_kN_m"],
                carga_succao=e["q_succao_kN_m"], inclinacao=0.0,
                carga_servico_gravidade=max(e["pressao_kN_m2"], 0.0) * faixa,
                carga_servico_succao=abs(min(e["succao_kN_m2"], 0.0)) * faixa)
    for r in nbr14762.dimensionar_terca(correntes=(max(1, n_corr),), apenas_aprovados=True, **base):
        ve = _flexo_compressao_terca(p, r.perfil, n_corr, N, r, titulo, origem)
        if ve.ok and _obliqua_com_peso(p, r, d.espacamento_porticos, n_corr, faixa).ok:
            r.add(_obliqua_com_peso(p, r, d.espacamento_porticos, n_corr, faixa))
            r.add(ve)
            r.elemento = "Longarina dos vãos das pontas"
            for vv in r.verificacoes:
                vv.titulo = vv.titulo.replace("gravidade", "pressão do vento")
            p.elementos.append(ElementoDimensionado(
                nome="Longarina dos vãos das pontas", perfil=r.perfil, material=d.aco_tercas, resultado=r,
                esforcos={"N_kN": round(N, 2)},
                geometria={"vaos": [1, max(1, d.n_porticos - 1)], "quantidade": 2 * 2 * len(cotas)}))
            p.avisos.append("As longarinas laterais dos vãos das pontas levam a reação do pilar de canto (N = %s): "
                            "%s no lugar de %s." % (fmt(N, 1, "kN"), r.perfil, lg.perfil))
            return
    lg.resultado.add(v)
    p.avisos.append("A longarina do vão da ponta não passa com a reação do pilar de canto (N = %s): trave o "
                    "pilar de canto no eixo fraco ou use longarina mais pesada." % fmt(N, 1, "kN"))


def _vento_oitao(p: ProjetoGalpao) -> Tuple[float, float]:
    """(pressão, sucção) de cálculo na parede do oitão, kN/m² sem majorar: a maior pressão (vento
    longitudinal, oitão de barlavento) e a maior sucção (vento transversal, zona 1 do oitão)."""
    linhas = [l for l in p.vento["objeto"].tabela() if "oitão" in l["superfície"].lower()]
    if not linhas:
        return 0.0, 0.0
    return (max(0.0, max(l["p (kN/m²)"] for l in linhas)),
            min(0.0, min(l["p (kN/m²)"] for l in linhas)))


def altura_no_oitao(d: DadosGalpao, y: float) -> float:
    """Altura (m) do eixo da cobertura na posição y do vão (do eixo do pilar esquerdo)."""
    return d.altura_beiral + (d.inclinacao / 100.0) * min(y, d.vao - y)


def _oitao(p: ProjetoGalpao):
    """A estrutura do oitão: pilaretes nas linhas dos nós do X da cobertura e longarinas entre eles.

    O vento no oitão sobe pelos pilaretes até os nós da treliça de contraventamento da cobertura
    (é a força F do contraventamento) e desce à base; as longarinas vencem de pilarete a pilarete.
    Antes não havia nada: a análise 3D jogava o vento do oitão no pilar de canto, e a longarina de
    cima dos vãos das pontas virava escora (131 % no galpão padrão, análise de 20/10).

    Pilarete: viga biapoiada do chão ao banzo/viga, com o maior entre a pressão e a sucção do oitão
    na largura do painel; o topo é solto na vertical (furo oblongo) — não leva peso da cobertura.
    """
    d = p.dados
    cob = p.elemento("Contraventamento de cobertura")
    long_lat = p.elemento("Longarina")
    if cob is None:
        return
    n = max(2, int(cob.geometria.get("paineis") or 2))
    larg = d.vao / n
    ys = [d.vao * k / n for k in range(1, n)]
    pres, suc = _vento_oitao(p)
    w = max(pres, abs(suc))
    if w <= 0 or not ys:
        return
    alturas = [altura_no_oitao(d, y) for y in ys]
    H = max(alturas)
    cotas = list((long_lat.geometria.get("cotas_fiadas_m") or []) if long_lat else [])
    Lb = (max(b - a for a, b in zip([0.0] + cotas, cotas + [H])) if cotas else H)
    q = 1.4 * w * larg                                       # kN/m
    apoiado = d.oitao_apoiado
    N = 0.0
    if apoiado:
        N = _viga_de_oitao(p, larg)
        if N is None:
            return
    aco = nbr8800._aco(d.aco_perfis)
    r = None
    for perf in banco().candidatos(tipo="I", familia="W"):
        try:
            if apoiado:
                # flexo-compressão: o peso da viga de oitão (reação no apoio interno) com o vento do oitão —
                # as duas majoradas juntas, a favor da segurança
                ri = nbr8800.verificar_viga(perf, aco, H * 100.0, q_Sd=q / 100.0, q_servico=w * larg / 100.0,
                                            Lb=Lb * 100.0, Cb=1.0, limite="L/250", N_Sd=N, Lx=H * 100.0,
                                            Ly=Lb * 100.0, elemento="Pilar de oitão")
            else:
                ri = nbr8800.verificar_viga(perf, aco, H * 100.0, q_Sd=q / 100.0, q_servico=w * larg / 100.0,
                                            Lb=Lb * 100.0, Cb=1.0, limite="L/250", elemento="Pilar de oitão")
        except ErroDeDados:
            continue
        if ri.ok:
            r = ri
            break
    if r is None:
        p.avisos.append("Nenhum W do catálogo atende o pilar de oitão (H = %s): aproxime os pilaretes "
                        "(mais painéis no contraventamento)." % fmt(H, 2, "m"))
        return
    if apoiado:
        r.hipotese("topo", "apoia a viga de oitão (o pórtico das pontas): N = %s com o vento do oitão"
                   % fmt(N, 1, "kN"), "rotina")
    else:
        r.hipotese("topo", "topo solto na vertical (furo oblongo): só o vento do oitão, sem peso da cobertura",
                   "rotina")
    p.elementos.append(ElementoDimensionado(
        nome="Pilar de oitão", perfil=r.perfil, material=d.aco_perfis, resultado=r,
        esforcos={"q_kN_m": round(q, 3), "w_kN_m2": round(w, 3), "M_kNm": round(q * H * H / 8.0, 2),
                  "reacao_topo_kN": round(q * H / 2.0, 2), "N_kN": round(N, 2),
                  "topo": "apoiado" if apoiado else "solto"},
        geometria={"posicoes_m": [round(y, 4) for y in ys], "alturas_m": [round(h, 4) for h in alturas],
                   "largura_m": round(larg, 4), "por_oitao": len(ys), "quantidade": 2 * len(ys),
                   "Lb_m": round(Lb, 3)}))
    # longarinas do oitão: de pilarete a pilarete (e ao pilar de canto), nas fiadas do fechamento; na
    # tesoura com a ponta em viga de oitão, mais uma na altura do banzo de baixo — é onde as linhas de
    # travamento do banzo de baixo do vão da ponta se ancoram (não há mais tesoura ali)
    if not cotas:
        return
    if d.eh_trelicado and apoiado and all(abs(c - d.pe_direito) > 0.3 for c in cotas):
        cotas = sorted(cotas + [d.pe_direito])
    esp = cotas[1] - cotas[0] if len(cotas) > 1 else cotas[0] * 2
    base = dict(aco=d.aco_tercas, vao=larg, carga_gravidade=1.4 * pres * esp,
                carga_succao=1.4 * abs(suc) * esp, inclinacao=0.0,
                carga_servico_gravidade=pres * esp, carga_servico_succao=abs(suc) * esp)
    opcoes = nbr14762.dimensionar_terca(correntes=(0, 1), apenas_aprovados=True, **base) or         nbr14762.dimensionar_terca(correntes=(1, 2), apenas_aprovados=False, **base)
    if not opcoes:
        return
    melhor = _com_peso_do_fechamento(p, sorted(opcoes, key=lambda r_: (not r_.ok, 0)), larg, esp)
    melhor.elemento = "Longarina de oitão L = %s m" % fmt(larg, 2)
    for v in melhor.verificacoes:
        v.titulo = v.titulo.replace("gravidade", "pressão do vento")
    p.elementos.append(ElementoDimensionado(
        nome="Longarina de oitão", perfil=melhor.perfil, material=d.aco_tercas, resultado=melhor,
        esforcos={"pressao_kN_m2": round(pres, 3), "succao_kN_m2": round(suc, 3)},
        geometria={"vao_m": round(larg, 4), "cotas_fiadas_m": cotas, "paineis": n,
                   "n_correntes": melhor.dados.get("n_correntes", 0),
                   "quantidade": 2 * n * len(cotas)}))


def _viga_de_oitao(p: ProjetoGalpao, larg: float) -> Optional[float]:
    """A viga de oitão (o pórtico das pontas com o topo do pilarete apoiado): W contínua sobre os
    pilaretes e os pilares de canto, com meia faixa de cobertura. Gravidade com a mesa de cima
    travada pelas terças; sucção com a de baixo solta no vão entre pilaretes. Devolve a reação no
    pilarete (kN, apoio interno: 1,25·q·L), ou None quando nada passa."""
    d = p.dados
    g, sc = p.cargas["g_cobertura"], p.cargas["sobrecarga"]
    succ = abs(min(0.0, p.cargas.get("succao_telhado") or 0.0))
    faixa = d.espacamento_porticos / 2.0
    L = larg / math.cos(math.radians(d.angulo_telhado))
    passo = p.cargas.get("espacamento_tercas_real") or d.espacamento_tercas
    q_g = (1.25 * g + 1.5 * sc) * faixa + 1.25 * 0.3            # + peso próprio estimado (0,3 kN/m)
    q_s = max(0.0, (1.4 * succ - g) * faixa)
    aco = nbr8800._aco(d.aco_perfis)
    escolhido = None
    for perf in banco().candidatos(tipo="I", familia="W"):
        try:
            rg = nbr8800.verificar_viga(perf, aco, L * 100.0, q_Sd=q_g / 100.0, q_servico=(g + sc) * faixa / 100.0,
                                        Lb=passo * 100.0, limite="L/250", elemento="Viga de oitão")
            if not rg.ok:
                continue
            rs = nbr8800.verificar_viga(perf, aco, L * 100.0, q_Sd=q_s / 100.0, Lb=L * 100.0, limite="L/120",
                                        elemento="Viga de oitão")
        except ErroDeDados:
            continue
        if rs.ok:
            for v in rs.verificacoes:
                v.titulo = "Sucção — " + v.titulo
                rg.add(v)
            escolhido = rg
            break
    if escolhido is None:
        p.avisos.append("Nenhum W do catálogo atende a viga de oitão: use o topo do pilar de oitão solto.")
        return None
    escolhido.hipotese("modelo", "contínua sobre os pilaretes; verificada como biapoiada em cada vão "
                       "(qL²/8, a favor da segurança)", "rotina")
    p.elementos.append(ElementoDimensionado(
        nome="Viga de oitão", perfil=escolhido.perfil, material=d.aco_perfis, resultado=escolhido,
        esforcos={"q_gravidade_kN_m": round(q_g, 3), "q_succao_kN_m": round(q_s, 3)},
        geometria={"vao_m": round(L, 4), "quantidade": 4, "comprimento_m": round(d.comprimento_agua, 3)}))
    return 1.25 * q_g * L


def _tercas_escora(p: ProjetoGalpao):
    """A terça dos vãos contraventados que é montante da treliça de cobertura: flexo-compressão.

    Se a terça comum passa, a verificação entra nela. Senão, só as terças dessas linhas, nos
    vãos contraventados, ganham o Ue mais leve que passa (marca T2) — as outras continuam."""
    d = p.dados
    terca = p.elemento("Terça")
    cob = p.elemento("Contraventamento de cobertura")
    N = _forca_de_escora(p)
    if terca is None or cob is None or N < N_ESCORA_MIN:
        return
    n_corr = int(terca.geometria.get("n_correntes") or 0)
    v = _flexo_compressao_terca(p, terca.perfil, n_corr, N, terca.resultado)
    n_linhas = max(1, int(cob.geometria.get("paineis") or 2) - 1)
    terca.esforcos["N_escora_kN"] = round(N, 2)
    if v.ok:
        terca.resultado.add(v)
        return
    vao, q_grav, q_suc, _s, comuns = _cargas_da_terca(p, float(terca.geometria.get("espacamento_m") or 1.6))
    candidatas = nbr14762.dimensionar_terca(
        aco=d.aco_tercas, vao=vao, carga_gravidade=q_grav, carga_succao=q_suc,
        correntes=(n_corr,), apenas_aprovados=True, **comuns)
    escolhida, ve = None, None
    for r in candidatas:
        ve = _flexo_compressao_terca(p, r.perfil, n_corr, N, r)
        if ve.ok:
            escolhida = r
            break
    if escolhida is None:
        # nenhuma passa: a terça comum fica com a verificação reprovada (o galpão não passa)
        terca.resultado.add(v)
        p.avisos.append("A terça que é escora do contraventamento de cobertura (N = %s) não passa à "
                        "flexo-compressão com nenhum Ue do catálogo: adote escora própria (tubo ou "
                        "cantoneira dupla) nas linhas do X ou mais painéis." % fmt(N, 1, "kN"))
        return
    escolhida.add(ve)
    escolhida.elemento = "Terça-escora"
    vaos = cob.geometria.get("vaos_contraventados") or []
    p.elementos.append(ElementoDimensionado(
        nome="Terça-escora do contraventamento", perfil=escolhida.perfil, material=d.aco_tercas,
        resultado=escolhida, esforcos={"N_kN": round(N, 2), "q_succao_kN_m": round(q_suc, 3)},
        geometria={"vao_m": vao, "n_correntes": n_corr, "linhas_por_vao": n_linhas,
                   "vaos_contraventados": list(vaos), "quantidade": n_linhas * len(vaos)}))
    p.avisos.append("As terças nas linhas do X da cobertura (%d por vão contraventado) são escoras do "
                    "contraventamento (N = %s): %s no lugar de %s." % (
                        n_linhas, fmt(N, 1, "kN"), escolhida.perfil, terca.perfil))

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

    # a primeira (a mais leve) que passa também na flexão oblíqua com o peso do fechamento entre correntes
    melhor = _com_peso_do_fechamento(p, opcoes, d.espacamento_porticos, esp)
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
    sc = p.cargas["sobrecarga"]
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
    # --- 1 kN concentrado no meio de cada barra do banzo superior (NBR 6120:2019, item
    # 6.4: todo elemento isolado da cobertura; isolado das outras variáveis) — só faz
    # sentido na treliça, onde o banzo é um elemento entre nós; na viga de alma cheia a
    # distribuída governa de longe
    if pp:
        for b in barras_viga:
            try:
                modelo.concentrada("P1", b, -cargas.CARGA_CONCENTRADA_COBERTURA,
                                   modelo.comprimento(b) / 2.0, "global_y")
            except ErroDeDados:
                continue
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
        # tesoura apoiada: a parede sobe do topo do pilar até o beiral (a altura da tesoura no apoio)
        # e o vento dessa faixa entra no topo do pilar — antes ficava fora (0,8 m no 20×40; a
        # análise 3D dava o momento na base ~20 % maior, análise de 20/10)
        if faixa_acima_do_pilar(d) > 1e-6:
            h = faixa_acima_do_pilar(d)
            topo_esq, topo_dir = _topos_dos_pilares(modelo)
            modelo.nodal(caso, topo_esq, Fx=c["parede_barlavento"] * s * h)
            modelo.nodal(caso, topo_dir, Fx=-c["parede_sotavento"] * s * h)
    return crit


def faixa_acima_do_pilar(d: DadosGalpao) -> float:
    """Altura de parede acima do topo do pilar (m): na tesoura apoiada, do pé-direito ao beiral."""
    if d.eh_trelicado and d.ligacao_tesoura == "apoiada":
        return max(0.0, d.altura_beiral - d.pe_direito)
    return 0.0


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
    # K = 1,0 no plano: os esforços chegam amplificados por B1/B2 (Anexo D da NBR 8800,
    # com rigidez reduzida e forças nocionais), e nesse método o comprimento de
    # flambagem é o real — o K = 2,0 de antes somava a 2ª ordem duas vezes (auditoria N3)
    Kx = KX_COM_B2
    Ly = min(H, 300.0)
    historico = []
    Lb_viga = esp_terca
    res_viga = res_pilar = None
    cb_viga = cb_pilar = 1.0

    for _ in range(6):
        modelo, env, combos = _rodar_analise(p, pilar0, viga0)
        esf = _amplificar_esforcos(_extrair_esforcos(env), segunda_ordem(modelo, combos))

        # viga: sob gravidade a terca trava a mesa superior; sob succao a mesa
        # inferior fica comprimida e quem trava sao as maos-francesas
        inverte = esf["viga"]["M_max"] * esf["viga"]["M_min"] < 0
        Lb_viga = max(esp_terca, min(d.vao * 100 / 4, 300.0)) if inverte else esp_terca
        # Cb pelo diagrama do caso que governa, no trecho destravado que contém o pico
        # (NBR 8800, 5.4.2.3) — antes eram os 1,14 e 1,67 fixos (auditoria N3)
        cb_viga = _cb_do_trecho(env, esf["viga"], Lb_viga)
        cb_viga_c = _cb_do_trecho(env, _caso_c(esf["viga"]), Lb_viga)
        cb_pilar = _cb_do_trecho(env, esf["pilar"], Ly)
        verificar_viga = (lambda perf, esf=esf, Lb=Lb_viga, Cb=cb_viga, Cc=cb_viga_c:
                          _verificar_viga_portico(perf, a, p, esf["viga"], Lb, Cb, Cc))
        res_viga = _menor_perfil(verificar_viga, altura_min=200, forcado=d.perfil_forcado("perfil_viga"))

        # pilar: flexo-compressao, com altura minima proxima a da viga para nao ficar
        # tao flexivel a ponto de empurrar todo o momento para a cumeeira
        h_min_pilar = max(200.0, achar_perfil(res_viga.perfil).d * 0.8)
        verificar_pilar = (lambda perf, esf=esf, Cb=cb_pilar: nbr8800.flexao_composta(
            perf, a, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"],
            Lx=H, Ly=Ly, Kx=Kx, Ky=1.0, Lb=Ly, Cb=Cb, elemento="Pilar"))
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
        _m, _env, _c = _rodar_analise(p, pilar0, viga0)
        pilar0, res_pilar = _pilar_por_deslocamento(
            p, viga0, pilar0, res_pilar, _amplificar_esforcos(
                _extrair_esforcos(_env), segunda_ordem(_m, _c)), H, Kx, Ly, a)

    # analise final com os perfis adotados
    modelo, env, combos = _rodar_analise(p, pilar0, viga0)
    so = segunda_ordem(modelo, combos)
    esf = _extrair_esforcos(env)
    desloc = _deslocamento_horizontal(p, modelo)
    extremos = _momentos_nos_nos(modelo, combos)
    esf["joelho"] = extremos["joelho"]
    esf["cumeeira"] = extremos["cumeeira"] * so["fator_viga"]
    esf = _amplificar_esforcos(esf, so)
    _aviso_segunda_ordem(p, so)

    p.esforcos = {
        "modelo": modelo, "envoltoria": env, "combinacoes": combos,
        "viga": esf["viga"], "pilar": esf["pilar"],
        "joelho_kNm": round(esf["joelho"] / 100, 1),
        "joelho_kNm_analise": round(extremos["joelho"] / 100, 1),       # 1ª ordem, o que o diagrama cota
        "cumeeira_kNm": round(esf["cumeeira"] / 100, 1),
        "deslocamento": desloc,
        "pre_viga": viga0.nome, "pre_pilar": pilar0.nome,
        "iteracoes": historico,
        "segunda_ordem": so,
    }
    p.esforcos["casos_modelo"] = combos
    p.combinacoes = _combinacoes_documentadas(p)

    # os W em volta do adotado, verificados nos esforços finais: é a lista que a tela
    # oferece para trocar o perfil sem sair do que passa
    cb_viga = _cb_do_trecho(env, esf["viga"], Lb_viga)
    cb_viga_c = _cb_do_trecho(env, _caso_c(esf["viga"]), Lb_viga)
    cb_pilar = _cb_do_trecho(env, esf["pilar"], Ly)
    verificar_viga_final = (lambda perf: _verificar_viga_portico(
        perf, a, p, esf["viga"], Lb_viga, cb_viga, cb_viga_c))
    verificar_pilar_final = (lambda perf: nbr8800.flexao_composta(
        perf, a, N_Sd=esf["pilar"]["N"], Mx_Sd=esf["pilar"]["M"], Lx=H, Ly=Ly, Kx=Kx, Ky=1.0,
        Lb=Ly, Cb=cb_pilar, elemento="Pilar"))
    # os perfis adotados são conferidos nos esforços da análise final (o laço pode ter
    # parado num ciclo entre dois pares); o que não fecha por pouco sobe um degrau
    res_viga = verificar_viga_final(achar_perfil(res_viga.perfil))
    if not res_viga.ok and d.perfil_forcado("perfil_viga") is None:
        res_viga = _menor_perfil(verificar_viga_final, altura_min=200, forcado=None)
    res_pilar = verificar_pilar_final(achar_perfil(res_pilar.perfil))
    if not res_pilar.ok and d.perfil_forcado("perfil_pilar") is None:
        res_pilar = _menor_perfil(verificar_pilar_final,
                                  altura_min=max(200.0, achar_perfil(res_viga.perfil).d * 0.8),
                                  forcado=None)
    p.elementos.append(ElementoDimensionado(
        nome="Viga do pórtico", perfil=res_viga.perfil, material=d.aco_perfis,
        resultado=res_viga, alternativas=_alternativas_W(verificar_viga_final, res_viga.perfil),
        esforcos={"M_kNcm": round(esf["viga"]["M"], 1),
                  "M_kNm": round(esf["viga"]["M"] / 100, 1),
                  "V_kN": round(esf["viga"]["V"], 1),
                  "N_kN": round(esf["viga"]["N"], 1),
                  "tipo_N": esf["viga"]["tipo_N"],
                  "caso": esf["viga"].get("caso_M", "")},
        geometria={"Lb_cm": round(Lb_viga, 1), "Cb": round(cb_viga, 2),
                   "comprimento_m": round(d.comprimento_agua, 2),
                   "misula_m": d.comprimento_misula if d.com_misula else 0.0}))
    p.elementos.append(ElementoDimensionado(
        nome="Pilar", perfil=res_pilar.perfil, material=d.aco_perfis,
        resultado=res_pilar, alternativas=_alternativas_W(verificar_pilar_final, res_pilar.perfil),
        esforcos={"N_kN": round(esf["pilar"]["N"], 1),
                  "N_tracao_kN": round(esf["pilar"]["N_t"], 1),
                  "N_min_kN": round(esf["pilar"]["N_min"], 1),
                  "caso_N_min": esf["pilar"].get("caso_N_min", ""),
                  "M_kNcm": round(esf["pilar"]["M"], 1),
                  "M_kNm": round(esf["pilar"]["M"] / 100, 1),
                  "V_kN": round(esf["pilar"]["V"], 1),
                  "caso": esf["pilar"].get("caso_M", "")},
        geometria={"altura_m": d.pe_direito, "Kx": Kx, "Ly_cm": Ly, "Cb": round(cb_pilar, 2)}))

    if Lb_viga > esp_terca + 1.0:
        _maos_francesas_viga(p, Lb_viga, esf["viga"], achar_perfil(res_viga.perfil))
    if desloc and desloc.get("razao", 0) > 1.0:
        _diagnostico_deslocamento(p, viga0, pilar0, desloc)


def _pilar_por_deslocamento(p: ProjetoGalpao, viga: Perfil, pilar: Perfil,
                            res_pilar, esf, H, Kx, Ly, aco):
    """Sobe o perfil do pilar (W, do mais leve ao mais pesado) até o deslocamento do topo atender.

    Em galpão de base rotulada o deslocamento horizontal do topo costuma governar o
    pilar. Mas a partir de certo ponto o que limita é a rigidez do pórtico inteiro, e
    engrossar só o pilar deixa de compensar: a busca para quando o candidato passa de
    2,5× a massa do pilar da resistência (ou depois de 20 candidatos) e o pilar da
    resistência fica. As saídas reais — engastar a base, aproximar os pórticos ou
    afrouxar o critério — vêm do `_diagnostico_deslocamento`.

    Não há parada por "degrau que reduz pouco" (07/10): um degrau de ganho pequeno ainda
    pode fechar o limite um ou dois perfis adiante, e parar ali perderia a solução.
    """
    d = p.dados
    limite = d.pe_direito * 100 / d.desloc_horizontal
    candidatos = [x for x in banco().candidatos("I", "W", altura_min=pilar.d * 0.95)
                  if x.massa >= pilar.massa]
    escolhido, resultado = pilar, res_pilar
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
                    Lx=H, Ly=Ly, Kx=Kx, Ky=1.0, Lb=Ly, Cb=1.0, elemento="Pilar")
            escolhido = cand
            return escolhido, resultado
        if cand.massa > pilar.massa * 2.5:
            break            # engrossar mais só o pilar deixou de compensar
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
                saidas.append("engastar a base do pilar levaria o deslocamento a %s" % fmt(u_eng, 1, "cm"))
        except Exception:
            pass
    saidas.append("aproximar os pórticos (hoje a %s) reduz a carga de vento por "
                  "pórtico" % fmt(d.espacamento_porticos, 2, "m"))
    if fechamento_fissura(d):
        saidas.append("fechar em telha ou painel em vez de alvenaria (o deslocamento passa a ser "
                      "verificado na combinação frequente, NBR 8800:2024, B.2.4)")
    else:
        saidas.append("para galpão sem ponte rolante nem alvenaria encostada é usual adotar "
                      "H/150 a H/200 em vez de H/%d" % d.desloc_horizontal)
    p.avisos.append(
        "Deslocamento horizontal do topo do pilar de %s acima do limite %s = %s (combinação %s), "
        "mesmo com o maior perfil que ainda compensa — o galpão não passa. Saídas: %s."
        % (fmt(desloc["u_cm"], 1, "cm"), desloc["criterio"], fmt(desloc["limite_cm"], 1, "cm"),
           desloc.get("combinacao", ""), "; ".join(saidas)))


def _combinacoes_documentadas(p: ProjetoGalpao) -> list:
    """Monta as combinações da NBR 8681 com os valores reais das ações.

    São as mesmas combinações aplicadas ao modelo, escritas na linguagem do módulo de
    cargas para que o memorial mostre cada parcela com seu coeficiente. Os valores são
    as cargas por metro quadrado de projeção da cobertura.
    """
    d = p.dados
    g = p.cargas["g_cobertura"]
    sc = p.cargas["sobrecarga"]
    succao = abs(p.cargas.get("succao_telhado", 0.0))
    acoes = [
        cargas.Acao("Peso próprio da cobertura", "permanente", g, subtipo="metálica"),
        cargas.Acao("Sobrecarga de cobertura", "variável", sc, psi="cobertura"),
        cargas.Acao("Vento (sucção no telhado)", "vento", -succao),
    ]
    try:
        ultimas = list(cargas.combinacoes_ultimas(acoes))
        servico = cargas.combinacoes_servico(acoes)
    except Exception:
        return []
    # as combinações com vento e sobrecarga que o modelo resolve (combinacoes_com_vento);
    # a de sinais da função geral só junta ações do mesmo sentido e não as gera
    rotulos = {"PP": ("Peso próprio da cobertura", g, "permanente desfavorável"),
               "SC": ("Sobrecarga de cobertura", sc, None), "V": ("Vento (sucção no telhado)", -succao, None)}
    for nome_c, parcelas, _texto in combinacoes_com_vento("V"):
        principal = "Sobrecarga de cobertura" if nome_c.startswith("C3") else "Vento (sucção no telhado)"
        ps = []
        for caso, fator in parcelas.items():
            rot, valor, papel = rotulos[caso]
            if papel is None:
                papel = "variável principal" if rot == principal else "variável secundária (ψ₀)"
            gama = 1.25 if caso == "PP" else (1.5 if caso == "SC" else 1.4)
            ps.append(cargas.Parcela(rot, gama, fator / gama, valor, papel, "NBR 8800, Tabelas 1 e 2"))
        ultimas.append(cargas.Combinacao("C%d" % (len(ultimas) + 1), "última normal", "±", principal, ps))
    return ultimas + list(servico)


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


#: Comprimento de flambagem no plano quando os esforços vêm amplificados por B1/B2
#: (NBR 8800, item 4.9.4.3 e Anexo D): K = 1,0.
KX_COM_B2 = 1.0


def _x(extremo) -> float:
    return float(getattr(extremo, "x", 0.0) or 0.0)


def _normal_no_caso(env, rotulo: str, caso: str):
    """(N_c, N_t) da barra no caso dado: a maior compressão e a maior tração (kN, ≥ 0)."""
    try:
        dN = env.resultados[caso].barra(rotulo).diagrama.N
    except Exception:
        return 0.0, 0.0
    if not dN:
        return 0.0, 0.0
    return max(0.0, -min(dN)), max(0.0, max(dN))


def _cb_do_trecho(env, esf: dict, Lb: float) -> float:
    """C_b (NBR 8800, item 5.4.2.3) do trecho destravado de comprimento Lb que contém a
    seção do momento máximo, lido no diagrama do caso que governa a barra. Sem diagrama
    (ou Lb nulo) devolve 1,0, o valor a favor da segurança."""
    rot, caso, x_pico = esf.get("barra_M", ""), esf.get("caso_M", ""), esf.get("x_M", 0.0)
    try:
        rb = env.resultados[caso].barra(rot)
    except Exception:
        return 1.0
    L = float(rb.L or 0.0)
    if Lb <= 0 or L <= 0:
        return 1.0
    Lb = min(Lb, L)
    x0 = min(max(x_pico - Lb / 2.0, 0.0), L - Lb)
    ms = [rb.esforcos(x0 + Lb * k / 4.0)[2] for k in range(5)]
    return nbr8800.calcular_cb(ms)


def _caso_c(ev: dict) -> dict:
    """O caso de maior compressão da viga no formato que `_cb_do_trecho` lê."""
    return {"barra_M": ev.get("barra_c", ""), "caso_M": ev.get("caso_c", ""), "x_M": ev.get("x_c", 0.0)}


def _verificar_viga_portico(perf, a, p: ProjetoGalpao, ev: dict, Lb: float, cb: float, cb_c: float):
    """A viga do pórtico nos dois casos que podem governar a interação N–M: o de maior
    momento, com a normal dele (tração ou compressão), e o de maior compressão, com o
    momento dele. Devolve o pior dos dois (auditoria N2)."""
    d = p.dados
    comum = dict(L=d.comprimento_agua * 100, V_Sd=ev["V"], Lb=Lb, Kx=KX_COM_B2,
                 limite="L/%d" % d.flecha_viga, q_servico=_q_servico_viga(p),
                 elemento="Viga do pórtico")
    r = nbr8800.verificar_viga(perf, a, M_Sd=ev["M"], Cb=cb, N_Sd=ev["N"],
                               tipo_axial=ev["tipo_N"], **comum)
    r.dados["caso_verificado"] = ev.get("caso_M", "")
    if ev.get("N_c", 0.0) > 0 and ev.get("caso_c") and ev.get("caso_c") != ev.get("caso_M"):
        r2 = nbr8800.verificar_viga(perf, a, M_Sd=ev["M_c"], Cb=cb_c, N_Sd=ev["N_c"],
                                    tipo_axial="compressao", **comum)
        r2.dados["caso_verificado"] = ev["caso_c"]
        if r2.razao > r.razao:
            r2.hipotese("caso_da_viga",
                        f"Governa o caso de maior compressão na viga ({ev['caso_c']}: "
                        f"N = {fmt(ev['N_c'], 1)} kN, M = {fmt(ev['M_c'] / 100, 1)} kN·m), e não o de "
                        f"maior momento ({ev.get('caso_M', '')}).")
            return r2
    return r


def _extrair_esforcos(env) -> dict:
    """Momentos, cortantes e normais de projeto, considerando também os trechos de mísula.

    A viga sai com a normal **do mesmo caso** que dá o momento (a interação N–M da
    NBR 8800 é de uma combinação, não da envoltória — auditoria N2); o pilar sai com a
    maior compressão, a maior tração e a menor compressão entre os casos, que é o que a
    base precisa para o arrancamento e para o atrito (auditoria N1).
    """
    def maior(rotulos, grandeza):
        val, caso, rot_, x_ = 0.0, "", "", 0.0
        for r in rotulos:
            try:
                b = env.barra(r)
            except Exception:
                continue
            for ext in (getattr(b, grandeza + "_max"), getattr(b, grandeza + "_min")):
                if abs(_v(ext)) > abs(val):
                    val, caso, rot_, x_ = _v(ext), _caso(ext), r, _x(ext)
        return val, caso, rot_, x_

    # A viga é dimensionada pelo momento e pelo cortante **fora** da mísula: ali a seção
    # é maior, e o esforço daquele trecho é o que dimensiona a ligação de joelho, não a
    # viga. Por isso saem dois cortantes — o da viga e o do joelho, que a ligação usa.
    barras_viga = ["viga_esq", "viga_dir"]
    M_viga, caso_v, rot_v, x_v = maior(barras_viga, "M")
    V_viga, _, _, _ = maior(barras_viga, "V")
    V_joelho_, _, _, _ = maior(barras_viga + ["misula_esq", "misula_dir"], "V")
    M_pil, caso_p, rot_p, x_p = maior(["pilar_esq", "pilar_dir"], "M")
    V_pil, _, _, _ = maior(["pilar_esq", "pilar_dir"], "V")

    # viga: a normal no caso que governa o momento (compressão ou tração)
    Nc_v, Nt_v = _normal_no_caso(env, rot_v or "viga_esq", caso_v)
    tipo_N = "compressao" if Nc_v >= Nt_v else "tracao"
    N_viga = Nc_v if tipo_N == "compressao" else Nt_v
    # e o caso de maior compressão na viga (a gravidade, em geral), com o momento dele: a
    # interação N–M tem de valer nos dois, e o de maior momento costuma ser a sucção, com a
    # viga tracionada
    N_c2, caso_c = 0.0, ""
    for r in barras_viga:
        try:
            b = env.barra(r)
        except Exception:
            continue
        if -_v(b.N_min) > N_c2:
            N_c2, caso_c = -_v(b.N_min), _caso(b.N_min)
    M_c2, rot_c, x_c = 0.0, rot_v, 0.0
    if caso_c:
        for r in barras_viga:
            try:
                ext = env.resultados[caso_c].barra(r).diagrama.absoluto("M")
            except Exception:
                continue
            if abs(ext.valor) > M_c2:
                M_c2, rot_c, x_c = abs(ext.valor), r, ext.x

    # pilar: compressão máxima (com o caso), tração máxima e a menor compressão
    N_c, N_t, N_min, caso_Nc, caso_Nmin = 0.0, 0.0, math.inf, "", ""
    for r in ("pilar_esq", "pilar_dir"):
        try:
            b = env.barra(r)
        except Exception:
            continue
        vmax, vmin = _v(b.N_max), _v(b.N_min)          # + tração, − compressão
        if -vmin > N_c:
            N_c, caso_Nc = -vmin, _caso(b.N_min)
        N_t = max(N_t, vmax)
        if -vmax < N_min:
            N_min, caso_Nmin = -vmax, _caso(b.N_max)    # negativo = arrancamento
    if N_min is math.inf:
        N_min = 0.0

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
                 "N": N_viga, "tipo_N": tipo_N,
                 "M_max": _v(ve.M_max), "M_min": _v(ve.M_min),
                 "caso_M": caso_v, "barra_M": rot_v, "x_M": x_v, "resumo": ve.resumo(),
                 "N_c": N_c2, "M_c": M_c2, "caso_c": caso_c, "barra_c": rot_c, "x_c": x_c},
        "pilar": {"M": abs(M_pil), "V": abs(V_pil), "N": N_c, "N_c": N_c, "N_t": N_t,
                  "N_min": N_min, "caso_N": caso_Nc, "caso_N_min": caso_Nmin,
                  "M_max": _v(pe.M_max), "M_min": _v(pe.M_min),
                  "caso_M": caso_p, "barra_M": rot_p, "x_M": x_p, "resumo": pe.resumo()},
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


def fechamento_fissura(d: DadosGalpao) -> bool:
    """Fechamento sujeito à fissuração (alvenaria): o deslocamento excessivo é irreversível."""
    return "alvenaria" in str(d.fechamento_lateral or "").lower()


def psi_deslocamento(d: DadosGalpao) -> float:
    """Fator do vento na combinação de serviço do deslocamento horizontal — NBR 8800:2024,
    Anexo B, B.2.3 e B.2.4: fechamento que não fissura (telha, painel) é estado-limite
    reversível, combinação frequente (ψ1 = 0,3); alvenaria fissura, combinação rara (1,0)."""
    return 1.0 if fechamento_fissura(d) else 0.3


def _deslocamento_horizontal(p: ProjetoGalpao, modelo) -> dict:
    """Maior deslocamento do topo dos dois pilares, em todas as combinações de serviço com
    vento (um caso por C_pi). Antes lia só o joelho esquerdo de um caso: no galpão padrão o
    direito passava do limite com o esquerdo aprovado."""
    d = p.dados
    casos = [c for c in modelo.casos if c.startswith("S vento")]
    u, onde = 0.0, ""
    try:
        for caso in casos:
            r = analise.resolver(modelo, caso)
            for no in _topos_dos_pilares(modelo):
                ui = abs(r.deslocamento(modelo.indice_no(no))[0])
                if ui > u:
                    u, onde = ui, "%s, %s" % (caso, "pilar esquerdo" if no == _topos_dos_pilares(modelo)[0]
                                              else "pilar direito")
    except Exception:
        return {}
    if not casos:
        return {}
    limite = d.pe_direito * 100 / d.desloc_horizontal
    rara = fechamento_fissura(d)
    return {"u_cm": u, "limite_cm": limite,
            "razao": u / limite if limite else 0.0,
            "criterio": "H/%d" % d.desloc_horizontal,
            "combinacao": "rara (fechamento em alvenaria)" if rara else "frequente (ψ1 = 0,3)",
            "onde": onde}


def combinacoes_com_vento(caso_vento: str):
    """As combinações últimas com vento e sobrecarga (NBR 8681, item 5.1.3; NBR 8800,
    item 4.7.7.2), cada ação variável uma vez como principal:

        C3  1,25·PP + 1,5·SC + 1,4·ψ₀·V     (sobrecarga principal, ψ₀ do vento = 0,6)
        C4  1,25·PP + 1,4·V + 1,5·ψ₀·SC     (vento principal, ψ₀ da cobertura = 0,8)
        C5  1,25·PP + 1,4·V                  (vento com a permanente desfavorável, sem SC)

    Até a 0.8.13 havia só 1,25·PP + 0,9·SC + 0,84·V — as duas variáveis reduzidas e
    nenhuma principal —, que deixava de fora a combinação que governa o pilar.
    Devolve [(nome, {caso: fator}, texto)]."""
    psi0_v = cargas.psi("vento")[0]
    psi0_sc = cargas.psi("cobertura")[0]
    def n(x):
        return ("%.2f" % x).rstrip("0").rstrip(".").replace(".", ",")
    return [
        ("C3 SC+vento", {"PP": 1.25, "SC": 1.5, caso_vento: 1.4 * psi0_v},
         "1,25·PP + 1,5·SC + %s·Vento" % n(1.4 * psi0_v)),
        ("C4 vento+SC", {"PP": 1.25, "SC": 1.5 * psi0_sc, caso_vento: 1.4},
         "1,25·PP + 1,4·Vento + %s·SC" % n(1.5 * psi0_sc)),
        ("C5 vento+PP", {"PP": 1.25, caso_vento: 1.4}, "1,25·PP + 1,4·Vento"),
    ]


def _combinar(modelo, p: ProjetoGalpao, acoes) -> dict:
    """Monta os casos combinados dentro do modelo e devolve {nome: descrição}."""
    d = p.dados
    combos = {}
    # C1 gravidade: 1,25 PP + 1,5 SC
    modelo.caso("C1 gravidade")
    _somar(modelo, "C1 gravidade", {"PP": 1.25, "SC": 1.5})
    combos["C1 gravidade"] = "1,25·PP + 1,5·SC"
    # C2 e C3: sucção com permanente favorável, um jogo por caso de C_pi que o vento
    # trouxe (os casos "Vcpi…" do modelo)
    rots = [c[1:] for c in modelo.casos if c.startswith("Vcpi")]
    for rot in rots:
        nome = f"C2 sucção ({rot})"
        modelo.caso(nome)
        _somar(modelo, nome, {"PP": 1.0, f"V{rot}": 1.4})
        combos[nome] = f"1,0·PP + 1,4·Vento ({rot})"
        for nome_c, parcelas, texto in combinacoes_com_vento(f"V{rot}"):
            nome_c = f"{nome_c} ({rot})"
            modelo.caso(nome_c)
            _somar(modelo, nome_c, parcelas)
            combos[nome_c] = f"{texto} ({rot})"
    # C6: a carga concentrada de 1 kN da NBR 6120 (item 6.4), só com a permanente
    if "P1" in modelo.casos:
        modelo.caso("C6 carga concentrada")
        _somar(modelo, "C6 carga concentrada", {"PP": 1.25, "P1": 1.5})
        combos["C6 carga concentrada"] = "1,25·PP + 1,5·P (1 kN no meio do painel)"
    # serviço, para flecha e deslocamento
    modelo.caso("S rara gravidade")
    _somar(modelo, "S rara gravidade", {"PP": 1.0, "SC": 1.0})
    combos["S rara gravidade"] = "PP + SC (serviço)"
    psi = psi_deslocamento(d)
    for rot in rots:
        nome = f"S vento ({rot})"
        modelo.caso(nome)
        _somar(modelo, nome, {"PP": 1.0, f"V{rot}": psi})
        combos[nome] = (f"PP + 1,0·Vento ({rot}) (rara)" if psi == 1.0
                        else f"PP + 0,3·Vento ({rot}) (frequente)")
    _forcas_nocionais(modelo, [c for c in combos if c.startswith("C")])
    return combos


#: Força nocional: fração das cargas gravitacionais de cálculo (NBR 8800, item 4.9.7.1).
FRACAO_NOCIONAL = 0.003
#: Rigidez reduzida da análise que alimenta o B2 (NBR 8800, item 4.9.4.3 — média
#: deslocabilidade); adotada sempre, a favor da segurança.
RIGIDEZ_REDUZIDA = 0.8
#: R_s do B2: pórtico cuja estabilidade lateral vem da rigidez das ligações (D.2.2).
RS_PORTICO = 0.85


def _topos_dos_pilares(modelo) -> list:
    dd = modelo.dados or {}
    return [dd.get("no_apoio_esq") or "B", dd.get("no_apoio_dir") or "D"]


def _forcas_nocionais(modelo, casos) -> None:
    """0,3 % da carga gravitacional de cada combinação última, horizontal, no topo dos
    pilares, no sentido da resultante horizontal da combinação (a de gravidade, para a
    direita). Representa a imperfeição geométrica inicial (NBR 8800, item 4.9.7.1)."""
    topos = _topos_dos_pilares(modelo)
    for caso in casos:
        try:
            Fx, Fy, _ = analise.resolver(modelo, caso, 3).cargas_aplicadas()
        except Exception:
            continue
        H = FRACAO_NOCIONAL * max(0.0, -Fy)
        if H <= 0:
            continue
        sentido = -1.0 if Fx < -1e-9 else 1.0
        for no in topos:
            modelo.nodal(caso, no, Fx=sentido * H / len(topos))


def segunda_ordem(modelo, combos, barras_pilar=("pilar_esq", "pilar_dir"),
                  barras_viga=("viga_esq", "viga_dir")) -> dict:
    """Amplificação dos esforços pelo Anexo D da NBR 8800 (B1/B2), sem a análise nt:

        B2 = 1 / (1 − (1/R_s)·(Δh/h)·(ΣN_Sd/ΣH_Sd))  pela flexibilidade lateral do
             pórtico (Δh/ΣH de uma força horizontal no topo, com 0,8·EI) e o maior ΣN_Sd
             das combinações últimas;
        B1 = C_m / (1 − N_Sd1/N_e1) ≥ 1,  C_m = 1,0 e N_e1 = π²·E·I/L² (K = 1).

    Os momentos saem multiplicados por máx(B1, B2) e a normal do pilar por B2 — a
    simplificação a favor da segurança do Anexo D quando não há análise nt."""
    topos = _topos_dos_pilares(modelo)
    dd = modelo.dados or {}
    h = float(dd.get("pe_direito") or 0.0)
    caso_h = "_unitaria_horizontal"
    modelo.caso(caso_h)
    for no in topos:
        modelo.nodal(caso_h, no, Fx=1.0 / len(topos))
    try:
        r = analise.resolver(modelo, caso_h, 3)
        dh = sum(r.deslocamento(no)[0] for no in topos) / len(topos)       # cm, por 1 kN
    finally:
        modelo.casos.pop(caso_h, None)
    flex = abs(dh) / RIGIDEZ_REDUZIDA
    soma_N, caso_N = 0.0, ""
    for caso in [c for c in combos if c.startswith("C")]:
        try:
            Fy = analise.resolver(modelo, caso, 3).cargas_aplicadas()[1]
        except Exception:
            continue
        if -Fy > soma_N:
            soma_N, caso_N = -Fy, caso
    termo = flex * soma_N / (RS_PORTICO * h) if h > 0 else 0.0
    B2 = 1.0 / (1.0 - termo) if termo < 1.0 else float("inf")

    def B1(rotulos) -> float:
        pior = 1.0
        for rot in rotulos:
            try:
                k = modelo.indice_barra(rot)
            except Exception:
                continue
            b = modelo.barras[k]
            L = modelo.comprimento(rot)
            Ne1 = math.pi ** 2 * b.E * b.I / L ** 2 if L > 0 else float("inf")
            N = 0.0
            for caso in [c for c in combos if c.startswith("C")]:
                try:
                    dN = analise.resolver(modelo, caso, 5).barra(rot).diagrama.N
                except Exception:
                    continue
                N = max(N, -min(dN) if dN else 0.0)
            if N >= Ne1:
                return float("inf")
            pior = max(pior, 1.0 / (1.0 - N / Ne1))
        return pior

    B1_p, B1_v = B1(barras_pilar), B1(barras_viga)
    if B2 <= analise.LIMITE_PEQUENA:
        classe = "pequena deslocabilidade"
    elif B2 <= analise.LIMITE_MEDIA:
        classe = "média deslocabilidade"
    else:
        classe = "grande deslocabilidade"
    return {"B2": B2, "B1_pilar": B1_p, "B1_viga": B1_v,
            "fator_pilar": max(B1_p, B2), "fator_viga": max(B1_v, B2),
            "delta_por_kN_cm": abs(dh), "soma_N_kN": soma_N, "caso_N": caso_N, "h_cm": h,
            "Rs": RS_PORTICO, "classificacao": classe}


def _amplificar_esforcos(esf: dict, so: dict) -> dict:
    """Aplica `segunda_ordem` aos esforços do pilar e da viga (e aos nós da ligação)."""
    fp, fv = so["fator_pilar"], so["fator_viga"]
    for chave, f in (("pilar", fp), ("viga", fv)):
        e = esf.get(chave)
        if not e:
            continue
        for g in ("M", "M_max", "M_min", "M_c"):
            if g in e:
                e[g] = e[g] * f
        if chave == "pilar":
            for g in ("N", "N_c"):
                if g in e:
                    e[g] = e[g] * so["B2"]
    for chave in ("joelho",):
        if chave in esf and isinstance(esf[chave], (int, float)):
            esf[chave] = esf[chave] * fp
    esf["segunda_ordem"] = so
    return esf


def _aviso_segunda_ordem(p, so: dict) -> None:
    if so["classificacao"] == "grande deslocabilidade":
        p.avisos.append(
            "Pórtico de grande deslocabilidade (B2 = %s): a NBR 8800 (item 4.9.4.2) exige "
            "análise rigorosa de 2ª ordem; a amplificação B1/B2 usada aqui é só indicativa. "
            "Enrijeça o pórtico (pilar mais alto, base engastada ou contraventamento)."
            % fmt(so["B2"], 2))


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


# ------------------------------------------------------- 6. viga e pilar

def _q_servico_viga(p: ProjetoGalpao) -> float:
    d = p.dados
    g = p.cargas["g_cobertura"]
    return (g + p.cargas["sobrecarga"]) * d.espacamento_porticos / 100.0   # kN/cm


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
        if papel.startswith("banzo"):
            # banzo contínuo: a ruptura da seção líquida só nas barras de ponta (apoio e
            # emenda da cumeeira) — regra do usuário, 14/10/2026
            e["N_t_ponta"] = 0.0
        for b in barras:
            e["L"] = max(e["L"], t.comprimento(b))
            try:
                eb = env.barra(b.rotulo)
            except Exception:
                continue
            ponta = "N_t_ponta" in e and tesouras.barra_de_ponta(t, b)
            for ext in (eb.N_max, eb.N_min):
                v = _v(ext)
                if v < 0 and -v > e["N_c"]:
                    e["N_c"], e["barra_N"], e["caso_N"] = -v, b.rotulo, _caso(ext)
                elif v > e["N_t"]:
                    e["N_t"] = v
                if ponta and v > e["N_t_ponta"]:
                    e["N_t_ponta"] = v
            for ext in (eb.M_max, eb.M_min):
                if abs(_v(ext)) > e["M"]:
                    e["M"], e["barra_M"], e["caso_M"] = abs(_v(ext)), b.rotulo, _caso(ext)
            for ext in (eb.V_max, eb.V_min):
                e["V"] = max(e["V"], abs(_v(ext)))
        saida[papel] = e

    ep = {"N_c": 0.0, "N_t": 0.0, "N_min": math.inf, "M": 0.0, "V": 0.0, "caso_M": "",
          "caso_N": "", "caso_N_min": "", "barra_M": "", "x_M": 0.0}
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
        # a menor compressão (ou o arrancamento, negativo) entre os casos: é o N mínimo
        # que a base usa no atrito e no chumbador (auditoria N1)
        if -_v(eb.N_max) < ep["N_min"]:
            ep["N_min"], ep["caso_N_min"] = -_v(eb.N_max), _caso(eb.N_max)
        for ext in (eb.M_max, eb.M_min):
            if abs(_v(ext)) > ep["M"]:
                ep["M"], ep["caso_M"], ep["barra_M"], ep["x_M"] = abs(_v(ext)), _caso(ext), rot, _x(ext)
        for ext in (eb.V_max, eb.V_min):
            ep["V"] = max(ep["V"], abs(_v(ext)))
    if ep["N_min"] is math.inf:
        ep["N_min"] = 0.0
    # 2ª ordem no pilar (a tesoura é triangulada: as barras dela não se amplificam)
    pilares = (modelo.dados or {}).get("barras_pilar") or []
    if pilares:
        so = segunda_ordem(modelo, list(modelo.casos), barras_pilar=pilares, barras_viga=())
        ep["M"] *= so["fator_pilar"]
        ep["N_c"] *= so["B2"]
        saida["segunda_ordem"] = so
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
    Kx = KX_COM_B2                    # os esforços do pilar chegam amplificados por B2
    Ly_pilar = min(H, 300.0)
    cb_pilar = 1.0

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
                # travamento até o banzo passar, antes de engrossar o perfil. Antes o laço
                # parava no passo mais aberto em que *algum* perfil passava — engrossava o
                # banzo para não fechar a malha (triangular-Howe de 20 m: Ue 150×75×20×4,75
                # a 2,86 m em vez do Ue 150×60×20×3,75 a 1,43 m, e o ciclo entre os dois
                # terminava reprovando). Agora vale o perfil mais leve que passa, com o
                # passo mais aberto que o deixa passar
                escolha = None
                for cand_trava, cand_linhas in opcoes_trava:
                    perf_c, r_c = tesouras.menor_perfil(
                        tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"],
                        e["N_t"], e["M"], e["L"], cand_trava, NOME_DA_BARRA[papel],
                        altura_max=altura_max(papel, e), n=n_pecas, forcado=forcado,
                        Nt_ponta=e.get("N_t_ponta"))
                    if perf_c is None or r_c is None:
                        continue
                    chave_c = (0, perf_c.massa or 0.0) if r_c.ok else (1, r_c.razao)
                    if escolha is None or chave_c < escolha[0]:   # empate: o passo mais aberto
                        escolha = (chave_c, perf_c, cand_trava, cand_linhas)
                if escolha is not None:
                    novos[papel] = escolha[1]
                    trava, n_travas = escolha[2], escolha[3]
                continue
            perf, _r = tesouras.menor_perfil(
                tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"], e["N_t"],
                e["M"], e["L"], fora_do_plano(papel, e), NOME_DA_BARRA[papel],
                altura_max=altura_max(papel, e), n=n_pecas, forcado=forcado,
                Nt_ponta=e.get("N_t_ponta"))
            if perf is None:
                raise ErroDeDados(
                    "Nenhum perfil do catálogo atende ao %s da tesoura com altura de até "
                    "%s (um oitavo do painel). Aumente a altura da tesoura, reduza o vão "
                    "ou aproxime os pórticos."
                    % (papel, fmt(altura_max(papel, e), 0, "mm")))
            novos[papel] = perf
        ep = esf["pilar"]
        cb_pilar = _cb_do_trecho(env, ep, Ly_pilar)
        r_pilar = _menor_perfil(
            lambda perf, Cb=cb_pilar: nbr8800.flexao_composta(
                perf, a, N_Sd=ep["N_c"], Mx_Sd=ep["M"], Lx=H, Ly=Ly_pilar,
                Kx=Kx, Ky=1.0, Lb=Ly_pilar, Cb=Cb, elemento="Pilar"),
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
            # o passo do travamento ficava o da última escolha, feita sobre outra
            # análise: refaz-se para o banzo que fica, nos esforços que valem
            e = esf.get("banzo inferior")
            if e and "banzo inferior" in perfis:
                melhor = None
                for cand_trava, cand_linhas in opcoes_trava:
                    _p, r_c = tesouras.menor_perfil(
                        tesouras.FAMILIAS_POR_PAPEL["banzo inferior"], d.aco_perfis, e["N_c"],
                        e["N_t"], e["M"], e["L"], cand_trava, NOME_DA_BARRA["banzo inferior"],
                        n=d.pecas_por_barra("banzo inferior"), forcado=perfis["banzo inferior"],
                        Nt_ponta=e.get("N_t_ponta"))
                    if r_c.ok:
                        melhor = (0.0, cand_trava, cand_linhas)
                        break
                    if melhor is None or r_c.razao < melhor[0]:
                        melhor = (r_c.razao, cand_trava, cand_linhas)
                trava, n_travas = melhor[1], melhor[2]
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
        "segunda_ordem": esf.get("segunda_ordem"),
    }
    if esf.get("segunda_ordem"):
        _aviso_segunda_ordem(p, esf["segunda_ordem"])
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
        r = tesouras.verificar_barra(perf, d.aco_perfis, e["N_c"], e["N_t"], e["M"],
                                     e["L"], Ly, n_pecas, NOME_DA_BARRA[papel], p.avisos,
                                     Nt_ponta=e.get("N_t_ponta"))
        alternativas = tesouras.candidatos_verificados(
            tesouras.FAMILIAS_POR_PAPEL[papel], d.aco_perfis, e["N_c"], e["N_t"], e["M"],
            e["L"], Ly, NOME_DA_BARRA[papel], altura_ref=perf.d, altura_max=altura_max(papel, e),
            n=n_pecas, Nt_ponta=e.get("N_t_ponta"))
        if papel == "banzo inferior" and flecha is not None:
            r.add(flecha)
        if not r.ok:
            p.avisos.append(
                "O %s não passa nem com o perfil mais pesado de altura compatível com o "
                "painel (%s, aproveitamento %s). A tesoura está rasa para o vão: aumente "
                "a altura dela, reduza o vão ou aproxime os pórticos%s."
                % (NOME_DA_BARRA[papel].lower(), perf.nome, fmt(r.razao, 2),
                   "; ou marque %s duplos (2× o perfil, costas com costas)"
                   % ("banzos" if papel.startswith("banzo") else "diagonais")
                   if n_pecas == 1 and papel != "pilar" else ""))
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

    cb_pilar = _cb_do_trecho(env, ep, Ly_pilar)
    verificar_pilar_final = (lambda perf: nbr8800.flexao_composta(
        perf, a, N_Sd=ep["N_c"], Mx_Sd=ep["M"], Lx=H, Ly=Ly_pilar,
        Kx=Kx, Ky=1.0, Lb=Ly_pilar, Cb=cb_pilar, elemento="Pilar"))
    r_pilar = verificar_pilar_final(perfis["pilar"])
    p.elementos.append(ElementoDimensionado(
        nome="Pilar", perfil=perfis["pilar"].nome, material=d.aco_perfis, resultado=r_pilar,
        alternativas=_alternativas_W(verificar_pilar_final, perfis["pilar"].nome),
        esforcos={"N_kN": round(ep["N_c"], 1), "N_tracao_kN": round(ep["N_t"], 1),
                  "N_min_kN": round(ep["N_min"], 1), "caso_N_min": ep.get("caso_N_min", ""),
                  "M_kNcm": round(ep["M"], 1), "M_kNm": round(ep["M"] / 100, 1),
                  "V_kN": round(ep["V"], 1), "caso": ep["caso_M"]},
        geometria={"altura_m": d.pe_direito, "Kx": Kx, "Ly_cm": Ly_pilar,
                   "Cb": round(cb_pilar, 2)}))

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
    q_oitao = max(abs(c["parede_barlavento"]) for c in crit.values())
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
    # até o nível do X da cobertura (o beiral; na tesoura apoiada, acima do topo do pilar)
    comp_v = math.hypot(esp, d.altura_beiral)
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
    # a menor compressão entre as combinações (negativa = arrancamento na sucção): é ela
    # que vale no atrito da base e no chumbador, não a compressão de gravidade
    # (auditoria N1). Sem o valor no elemento, fica a compressão máxima, como antes.
    N_min = pilar.esforcos.get("N_min_kN")
    if N_min is None:
        N_t = pilar.esforcos.get("N_tracao_kN", 0.0) or 0.0
        N_min = -N_t if N_t > 0 else N

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
                            perf, N_Sd=N, M_Sd=M, H_Sd=V, N_Sd_min=N_min,
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

    def add(marca, descricao, perfil_nome, qtd, comp_m, material=None, obs="", pintada=True):
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
                          area_pintura_m2=round(perimetro * comp_m * qtd, 1) if pintada else 0.0,
                          observacao=obs))

    pilar = p.elemento("Pilar")
    viga = p.elemento("Viga")
    terca = p.elemento("Terça")
    cob = p.elemento("Contraventamento de cobertura")
    vert = p.elemento("Contraventamento vertical")

    # o pórtico das pontas apoiado nos pilaretes vira a viga de oitão: tesouras/vigas só nos internos
    vo = p.elemento("Viga de oitão")
    n_int = n_port - 2 if vo else n_port
    if pilar:
        if vo and d.eh_trelicado:
            # os de canto sobem ao beiral, onde apoia a viga de oitão
            add("P1", "Pilar do pórtico", pilar.perfil, 2 * n_int, d.pe_direito)
            add("P2", "Pilar de canto (até a viga de oitão)", pilar.perfil, 4, d.altura_beiral)
        else:
            add("P1", "Pilar do pórtico", pilar.perfil, 2 * n_port, d.pe_direito)
    if d.eh_trelicado:
        _lista_da_tesoura(p, add, n_int)
    elif viga:
        add("V1", "Viga do pórtico (uma água)", viga.perfil, 2 * n_int, d.comprimento_agua)
    if vo:
        add("VO", "Viga de oitão (uma água, contínua sobre os pilaretes)", vo.perfil, 4, d.comprimento_agua)
    if terca:
        linhas = terca.geometria.get("linhas", 0) * 2          # duas águas
        vaos = n_port - 1
        # terças e longarinas vêm galvanizadas (fora da área a pintar, como a lista de
        # material e o memorial dizem): antes entravam e quase dobravam a área e a tinta
        escora = p.elemento("Terça-escora do contraventamento")
        n_t2 = int(escora.geometria.get("quantidade") or 0) if escora else 0
        add("T1", "Terça", terca.perfil, linhas * vaos - n_t2, d.espacamento_porticos,
            material=d.aco_tercas, pintada=False)
        if n_t2:
            add("T2", "Terça-escora do contraventamento (linhas do X)", escora.perfil, n_t2,
                d.espacamento_porticos, material=d.aco_tercas, pintada=False)
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
        l2 = p.elemento("Longarina dos vãos das pontas")
        n_l2 = int(l2.geometria.get("quantidade") or 0) if l2 else 0
        add("L1", "Longarina de fechamento", perfil_long, n_long * 2 * (n_port - 1) - n_l2,
            d.espacamento_porticos, material=d.aco_tercas, pintada=False)
        if n_l2:
            add("L2", "Longarina dos vãos das pontas", l2.perfil, n_l2, d.espacamento_porticos,
                material=d.aco_tercas, pintada=False)
    # correntes do fechamento: a longarina foi verificada com elas (_longarinas), da fiada de baixo
    # até a terça do beiral, que leva o peso — antes ficavam fora do 3D e da lista
    n_corr_l = int(longarina.geometria.get("n_correntes") or 0) if longarina else 0
    cotas = (longarina.geometria.get("cotas_fiadas_m") or []) if longarina else []
    if n_corr_l and cotas:
        comp_cl = d.altura_beiral - min(cotas) + 0.3
        q_cl = 2 * (n_port - 1) * n_corr_l
        pecas.append(Peca(marca="CL", descricao="Corrente de longarina ø 16 mm (até a terça do beiral)",
                          perfil="Barra ø 16 mm", material=d.aco_chapas, quantidade=q_cl,
                          comprimento_m=round(comp_cl, 2), peso_unit_kg=round(1.58 * comp_cl, 2),
                          peso_total_kg=round(1.58 * comp_cl * q_cl, 1), area_pintura_m2=0.0))
    mfv = p.elemento("Mão-francesa da viga")
    if mfv:
        add("MF", "Mão-francesa da viga (até a terça)", mfv.perfil, int(mfv.geometria["quantidade"]),
            mfv.geometria["comprimento_m"], material=d.aco_chapas)
    # a estrutura do oitão (os dois): pilaretes, um por altura, e longarinas entre eles
    po = p.elemento("Pilar de oitão")
    if po:
        for h in sorted(set(po.geometria.get("alturas_m") or [])):
            q_h = 2 * sum(1 for x in po.geometria["alturas_m"] if x == h)
            add("PO", "Pilar de oitão", po.perfil, q_h, h)
    lo = p.elemento("Longarina de oitão")
    if lo:
        add("LO", "Longarina de oitão", lo.perfil, int(lo.geometria.get("quantidade") or 0),
            lo.geometria.get("vao_m", 5.0), material=d.aco_tercas, pintada=False)
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
    p.custo = {"custo_kg": d.custo_kg}
    for chave, _nome, fracao, _obs in REPARTICAO_CUSTO:
        p.custo[chave] = round(custo_total * fracao, 2)
    p.custo.update({
        "total": round(custo_total, 2),
        "por_m2": round(custo_total / d.area_coberta, 2) if d.area_coberta else 0.0,
        "observacao": "percentuais indicativos; confirme com orçamento de fornecedor.",
    })
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
