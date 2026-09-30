# -*- coding: utf-8 -*-
"""Testes do orquestrador do galpão.

O caso de referência é o galpão do Capítulo 16 do manual (20 m de vão, 40 m de
comprimento, pé-direito 6 m, pórticos a cada 5 m, V0 = 40 m/s, categoria II, classe B),
cujos resultados foram conferidos por revisão dedicada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados
from nucleo.galpao import dimensionar
from nucleo.modelo_galpao import DadosGalpao


def _cap16(**ajustes) -> DadosGalpao:
    base = dict(nome="Galpão do Capítulo 16", vao=20.0, comprimento=40.0,
                pe_direito=6.0, espacamento_porticos=5.0, inclinacao=10.0,
                v0=40.0, categoria_rugosidade="II", classe="B",
                telha="trapezoidal 0,50 mm", sobrecarga_cobertura=0.25)
    base.update(ajustes)
    return DadosGalpao(**base)


# ----------------------------------------------------------- caso de referência

def test_galpao_referencia_fecha_sem_erro():
    p = dimensionar(_cap16())
    assert p.erros == [], p.erros
    assert p.ok, [v.titulo for e in p.elementos if not e.ok
                  for v in e.resultado.verificacoes if not v.ok]


def test_vento_coerente_com_a_norma():
    """S2 pela NBR 6123 na altura real da edificação.

    O Capítulo 16 do manual adota S2 = 0,98, que corresponde a z = 10 m; o sistema usa
    a altura real da cumeeira (7 m neste galpão), como manda o item 5.3 da norma, e
    chega a 0,949. A diferença é de 3 % na velocidade e cerca de 6 % na pressão, e o
    valor do manual é o conservador dos dois.
    """
    p = dimensionar(_cap16())
    from nucleo.cargas import fator_s2
    assert abs(p.vento["S2"] - fator_s2("II", "B", 7.0)) < 0.005, p.vento["S2"]
    assert 0.80 <= p.vento["q"] <= 0.95, p.vento["q"]
    assert 36.0 <= p.vento["Vk"] <= 40.0, p.vento["Vk"]


def test_peso_proprio_da_cobertura():
    """Telha + terças + acessórios ficam na faixa de 0,10 a 0,20 kN/m²."""
    p = dimensionar(_cap16())
    assert 0.10 <= p.cargas["g_cobertura"] <= 0.20, p.cargas["g_cobertura"]


def test_consumo_na_faixa_usual():
    """O manual chega a 29,3 kg/m² para este galpão; a faixa usual é 18 a 35."""
    p = dimensionar(_cap16())
    consumo = p.resumo_pesos["kg_por_m2"]
    assert 18.0 <= consumo <= 38.0, consumo


def test_momentos_do_portico_na_ordem_de_grandeza_do_manual():
    """Manual: joelho ≈ 95 kN·m na gravidade e ≈ 190 kN·m na sucção."""
    p = dimensionar(_cap16())
    joelho = p.esforcos["joelho_kNm"]
    assert 60.0 <= joelho <= 260.0, joelho


def test_succao_governa_a_terca():
    """Em galpão leve a sucção do vento governa a terça, não a gravidade."""
    p = dimensionar(_cap16())
    terca = p.elemento("Terça")
    assert terca is not None and terca.ok
    assert "suc" in terca.resultado.critica.titulo.lower(), terca.resultado.critica.titulo


def test_perfis_adotados_sao_do_catalogo():
    p = dimensionar(_cap16())
    from nucleo.perfis import banco
    nomes = set(banco().perfis)
    for e in p.elementos:
        if e.perfil.startswith(("W ", "Ue ", "U ")):
            assert e.perfil in nomes, e.perfil


# ----------------------------------------------------------- comportamento

def test_succao_do_vento_alivia_o_portico():
    """A combinação de sucção tem de aliviar o pórtico, nunca carregá-lo.

    A tabela de vento guarda pressão positiva e sucção negativa; no modelo de análise,
    carga "perpendicular" positiva aponta para fora da água. Sem inverter o sinal, a
    sucção entrava empurrando a cobertura para baixo: a combinação de sucção somava com
    a gravidade, a reação vertical crescia em vez de cair, e o caso de arrancamento —
    que costuma governar galpão leve — desaparecia do dimensionamento.
    """
    from nucleo import analise
    p = dimensionar(_cap16())
    modelo = p.esforcos["modelo"]
    vertical = lambda caso: analise.resolver(modelo, caso).soma_reacoes()[1]  # noqa: E731
    gravidade = vertical("C1 gravidade")
    succao = min(vertical(c) for c in p.esforcos["combinacoes"] if c.startswith("C2"))
    assert succao < gravidade, (succao, gravidade)


def test_succao_inverte_o_momento_da_viga():
    """Sob sucção a viga flete ao contrário — é o que comprime a mesa inferior."""
    p = dimensionar(_cap16())
    b = p.esforcos["envoltoria"].barra("viga_esq")
    assert b.M_max.valor > 0 and b.M_min.valor < 0, b.resumo()
    assert "C2" in b.absoluto("M").caso or "C3" in b.absoluto("M").caso, b.resumo()


def test_base_engastada_reduz_o_deslocamento():
    rot = dimensionar(_cap16(base_rotulada=True))
    eng = dimensionar(_cap16(base_rotulada=False))
    assert eng.esforcos["deslocamento"]["u_cm"] < rot.esforcos["deslocamento"]["u_cm"]


def test_vento_mais_forte_pesa_mais():
    leve = dimensionar(_cap16(v0=30.0))
    forte = dimensionar(_cap16(v0=50.0))
    assert forte.resumo_pesos["total_kg"] > leve.resumo_pesos["total_kg"]


def test_vao_maior_pesa_mais_por_metro_quadrado():
    pequeno = dimensionar(_cap16(vao=12.0))
    grande = dimensionar(_cap16(vao=30.0, espacamento_porticos=6.0))
    assert grande.resumo_pesos["kg_por_m2"] > pequeno.resumo_pesos["kg_por_m2"]


def test_criterio_de_deslocamento_mais_folgado_economiza():
    severo = dimensionar(_cap16(desloc_horizontal=300))
    folgado = dimensionar(_cap16(desloc_horizontal=150))
    assert folgado.resumo_pesos["total_kg"] <= severo.resumo_pesos["total_kg"]


def test_lista_de_material_fecha_com_o_resumo():
    p = dimensionar(_cap16())
    soma = sum(x.peso_total_kg for x in p.lista_material)
    assert abs(soma - p.resumo_pesos["total_kg"]) < 1.0
    assert p.custo["total"] > 0
    marcas = {x.marca for x in p.lista_material}
    for esperada in ("P1", "V1", "T1"):
        assert esperada in marcas, marcas


def test_memoria_de_calculo_presente():
    """Toda verificação precisa de passos, senão o memorial sai vazio."""
    p = dimensionar(_cap16())
    for e in p.elementos:
        for v in e.resultado.verificacoes:
            if not v.dispensada:
                assert v.passos, f"{e.nome} / {v.titulo} sem memória de cálculo"


def test_serializa_para_a_interface():
    p = dimensionar(_cap16())
    import json
    d = p.para_json()
    texto = json.dumps(d, ensure_ascii=False, default=str)
    assert len(texto) > 5000
    assert d["elementos"] and d["lista_material"]


# ----------------------------------------------------------- robustez

def test_varredura_de_geometrias():
    """Nenhuma combinação usual pode levantar erro, nem reprovar em silêncio.

    Reprovar é legítimo — um pórtico de 30 m com base engastada pede uma base fora do
    que o catálogo de chumbadores alcança. O que não pode é reprovar sem dizer por quê,
    nem um elemento passar sem ter sido verificado.
    """
    problemas = []
    for vao in (8, 16, 25, 30):
        for pe in (4, 6, 8):
            for rotulada in (True, False):
                p = dimensionar(_cap16(vao=vao, pe_direito=pe, comprimento=36.0,
                                       espacamento_porticos=6.0,
                                       base_rotulada=rotulada))
                caso = (vao, pe, rotulada)
                if p.erros:
                    problemas.append(caso + (p.erros[0],))
                    continue
                crit = [v.titulo for e in p.elementos if not e.ok
                        for v in e.resultado.verificacoes if not v.ok]
                if crit:
                    problemas.append(caso + (crit[:1],))
                elif not p.ok and not p.avisos:
                    problemas.append(caso + ("reprovou sem aviso",))
    assert not problemas, problemas


def test_base_engastada_e_dimensionada():
    """Base engastada tem de sair com placa e chumbadores, não em branco.

    A placa é retangular: alargar na direção do momento dá braço ao chumbador, alargar
    na outra só aumenta o balanço da chapa. Enquanto a busca só testava placa quadrada
    grande, nenhuma base engastada fechava e o projeto ainda se dizia aprovado.
    """
    p = dimensionar(_cap16(vao=16, pe_direito=6, comprimento=36.0,
                           espacamento_porticos=6.0, base_rotulada=False))
    assert p.base is not None, "base engastada ficou sem dimensionamento"
    assert p.base.dados.get("L", 0) > p.base.dados.get("B", 0), "placa devia ser retangular"
    assert p.base.ok


def test_entrada_invalida_tem_mensagem_clara():
    for ajuste, trecho in ((dict(vao=200.0), "Vão"),
                           (dict(pe_direito=1.0), "Pé-direito"),
                           (dict(v0=5.0), "vento"),
                           (dict(classe="Z"), "Classe")):
        try:
            dimensionar(_cap16(**ajuste))
        except ErroDeDados as e:
            assert trecho.lower() in str(e).lower(), (ajuste, str(e))
        else:
            raise AssertionError(f"entrada {ajuste} deveria ter sido recusada")


# ------------------------------------------------ auditoria 30/09, leva 1 (C1, C3, C4, N1–N3)

def test_vento_entra_em_toda_situacao_de_abertura():
    """C1 — cada situação de abertura da tela gera os seus casos de vento no pórtico.

    Antes os casos eram fixos em C_pi = +0,2 e −0,3 (duas faces opostas); qualquer outra
    escolha não encontrava a pressão, devolvia 0,0 e o pórtico saía sem vento.
    """
    import pytest
    from nucleo import cargas, galpao
    referencia = None
    for aberturas in cargas.ABERTURAS:
        p = dimensionar(_cap16(aberturas=aberturas))
        assert p.erros == [], (aberturas, p.erros)
        vg = p.vento["objeto"]
        casos = [c for c in p.esforcos["casos_modelo"] if c.startswith("C2")]
        assert len(casos) == len(vg.casos_cpi) >= 1, (aberturas, casos)
        assert p.cargas["succao_telhado"] < -0.3, (aberturas, p.cargas["succao_telhado"])
        assert p.esforcos["pilar"]["M"] > 0
        if aberturas == "duas faces opostas":
            referencia = p
    # portão aberto a barlavento: C_pi = +0,8 (o caso mais severo), com aviso, e a sucção
    # do telhado é maior que a da situação padrão
    p = dimensionar(_cap16(aberturas="abertura dominante a barlavento"))
    assert [c.valor for c in p.vento["objeto"].casos_cpi] == [0.8]
    assert any("C_pi = +0,8" in a for a in p.avisos)
    assert p.cargas["succao_telhado"] < referencia.cargas["succao_telhado"]
    # a sotavento: C_pi = C_e da face B (transversal) e D (longitudinal), e o vento
    # entrando pela mesma abertura quando sopra do lado dela (+0,8)
    p = dimensionar(_cap16(aberturas="abertura dominante a sotavento"))
    coef = p.vento["objeto"].coeficientes
    esperados = {coef.busca("parede lateral sotavento", "transversal").Ce,
                 coef.busca("oitão sotavento", "longitudinal").Ce, 0.8}
    assert {c.valor for c in p.vento["objeto"].casos_cpi} == esperados
    # a pressão que falta é erro, nunca zero
    p = dimensionar(_cap16())
    p.vento["objeto"].pressoes = [x for x in p.vento["objeto"].pressoes
                                  if "sotavento" not in x.superficie]
    with pytest.raises(ErroDeDados, match="não encontrada"):
        galpao._pressoes_criticas(p)


def test_s3_da_tela_entra_no_vento():
    """C3 — o S3 escolhido na tela (grupo da Tabela 4 da NBR 6123:2023) entra em V_k."""
    p1 = dimensionar(_cap16())
    p2 = dimensionar(_cap16(fator_estatistico=0.95))
    assert p1.vento["S3"] == 1.0 and p1.vento["grupo"] == 3
    assert p2.vento["S3"] == 0.95 and p2.vento["grupo"] == 4
    assert abs(p2.vento["q"] / p1.vento["q"] - 0.95 ** 2) < 1e-6
    p3 = dimensionar(_cap16(fator_estatistico=1.11))
    assert p3.vento["grupo"] == 1 and p3.esforcos["pilar"]["M"] > p1.esforcos["pilar"]["M"]


def test_sobrecarga_minima_da_6120_no_telhado_plano():
    """C4 — telhado com 2 % de inclinação: a sobrecarga mínima é 0,50 kN/m², não 0,25."""
    p = dimensionar(_cap16(inclinacao=2.0, sobrecarga_cobertura=0.25))
    assert p.erros == [], p.erros
    assert p.cargas["sobrecarga"] == 0.50 and p.cargas["sobrecarga_minima_6120"] == 0.50
    assert any("NBR 6120" in a for a in p.avisos)
    p = dimensionar(_cap16())                      # 10 % → 0,25 vale
    assert p.cargas["sobrecarga"] == 0.25
    assert not any("NBR 6120" in a for a in p.avisos)


def test_terca_e_banzo_verificados_com_1_kN():
    """C4 — a carga concentrada de 1 kN (NBR 6120, 6.4) entra na terça e no banzo superior."""
    p = dimensionar(_cap16())
    t = p.elemento("Terça")
    assert t.resultado.dados["Mx_concentrada_kNcm"] > 0
    assert "carga_concentrada" in [h.chave for h in t.resultado.hipoteses]
    # vão curto: o 1 kN governa o momento de gravidade da terça
    p = dimensionar(_cap16(espacamento_porticos=3.0, comprimento=30.0))
    t = p.elemento("Terça")
    d = t.resultado.dados
    assert d["Mx_concentrada_kNcm"] > d["Mx_gravidade_distribuida_kNcm"]
    assert d["Mx_gravidade_kNcm"] == d["Mx_concentrada_kNcm"]
    # na tesoura, a combinação C6 com o 1 kN no meio de cada painel do banzo
    p = dimensionar(_cap16(tipo_portico="treliçado", base_rotulada=False))
    assert p.erros == [], p.erros
    assert "C6 carga concentrada" in p.esforcos["casos_modelo"]
    assert "C6 carga concentrada" not in dimensionar(_cap16()).esforcos["casos_modelo"]


def test_pilar_com_k_igual_a_1_e_cb_do_diagrama():
    """N3 — K = 1,0 com os esforços amplificados por B2; C_b lido no diagrama."""
    p = dimensionar(_cap16())
    pil = p.elemento("Pilar")
    assert pil.geometria["Kx"] == 1.0
    assert 1.0 <= pil.geometria["Cb"] <= 3.0
    viga = p.elemento("Viga do pórtico")
    assert 1.0 <= viga.geometria["Cb"] <= 3.0
    p = dimensionar(_cap16(base_rotulada=False))
    assert p.elemento("Pilar").geometria["Kx"] == 1.0
    p = dimensionar(_cap16(tipo_portico="treliçado", base_rotulada=False))
    assert p.elemento("Pilar").geometria["Kx"] == 1.0
    assert 1.0 <= p.elemento("Pilar").geometria["Cb"] <= 3.0


def test_viga_com_a_normal_da_mesma_combinacao():
    """N2 — a viga do pórtico é verificada à flexão composta com o N do caso que dá o M."""
    p = dimensionar(_cap16())
    viga = p.elemento("Viga do pórtico")
    assert viga.esforcos["N_kN"] > 0 and viga.esforcos["tipo_N"] in ("compressao", "tracao")
    assert any("Interação" in v.titulo for v in viga.resultado.verificacoes)
    assert "flexao_composta" in [h.chave for h in viga.resultado.hipoteses]


def test_base_recebe_o_arrancamento():
    """N1 — a base é conferida com o N mínimo (arrancamento na sucção), não só a compressão."""
    p = dimensionar(_cap16())
    pil = p.elemento("Pilar")
    assert pil.esforcos["N_min_kN"] < pil.esforcos["N_kN"]
    assert pil.esforcos["caso_N_min"].startswith("C2")
    assert p.base is not None
    assert abs(p.base.dados["N_Sd_min"] - pil.esforcos["N_min_kN"]) < 0.05
    if pil.esforcos["N_min_kN"] < 0:
        assert p.base.dados["T_arrancamento"] > 0
        assert p.base.dados["T_chumbadores"] >= p.base.dados["T_arrancamento"]
        assert p.base.dados["transferencia_horizontal"]["mecanismo"] != "atrito placa–grout"


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)


def test_recusa_o_que_nao_calcula():
    """O que o programa não calcula é recusado com mensagem, em vez de sair outra coisa.

    O pórtico treliçado passou a ser calculado (`nucleo/tesouras.py`); o que continua
    fora é a ponte rolante, o formato de pórtico desconhecido e a tesoura sem
    estabilidade no plano.
    """
    import pytest
    from nucleo.base import ErroDeDados
    from nucleo.modelo_galpao import DadosGalpao
    with pytest.raises(ErroDeDados, match="Ponte rolante"):
        DadosGalpao(ponte_rolante=True, capacidade_ponte_t=5).validar()
    with pytest.raises(ErroDeDados, match="alma cheia"):
        DadosGalpao(tipo_portico="arco atirantado").validar()
    # tesoura apoiada sobre pilar de base rotulada é mecanismo: tem de ser recusada
    with pytest.raises(ErroDeDados, match="estabilidade"):
        DadosGalpao(tipo_portico="treliçado", ligacao_tesoura="apoiada",
                    base_rotulada=True).validar()
    with pytest.raises(ErroDeDados, match="[Ff]ormato"):
        DadosGalpao(tipo_portico="treliçado", formato_tesoura="arco",
                    base_rotulada=False).validar()
    DadosGalpao().validar()
    DadosGalpao(tipo_portico="treliçado", base_rotulada=False).validar()
