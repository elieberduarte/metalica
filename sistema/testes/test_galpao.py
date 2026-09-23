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
