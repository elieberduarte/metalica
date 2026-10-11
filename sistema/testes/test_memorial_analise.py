# -*- coding: utf-8 -*-
"""O memorial da análise estrutural e o quadro de comparação com o engenheiro (saida/memorial_analise.py, etapa 6,
11/10/2026). Pórtico de aço de 4 pilares W 250×32,7 e 4 vigas W 200×35,9 (6 × 5 m, 6 m de altura), bases engastadas:
o quadro leva a carga total do peso próprio (o peso dos perfis), as reações da envoltória, os esforços por grupo, as
peças e as bases; o memorial traz cada seção e a conta da peça que governa."""
import json

import numpy as np
import pytest

from nucleo3d import analise_estrutural as AE
from nucleo3d.modelo import Barra, Documento
from saida import memorial_analise as MA

G = 9.80665


def _portico():
    doc = Documento(nome="pórtico")
    k = 0
    for x in (0.0, 6000.0):
        for y in (0.0, 5000.0):
            k += 1
            doc.add(Barra(inicio=(x, y, 0.0), fim=(x, y, 6000.0), perfil="W 250×32,7", papel="pilar", rotacao=0.0,
                          atributos={"elemento": "pilar", "marca": "P%d" % k}))
    for y in (0.0, 5000.0):
        doc.add(Barra(inicio=(0.0, y, 6000.0), fim=(6000.0, y, 6000.0), perfil="W 200×35,9", papel="viga", rotacao=0.0,
                      atributos={"elemento": "viga", "marca": "V1"}))
    for x in (0.0, 6000.0):
        doc.add(Barra(inicio=(x, 0.0, 6000.0), fim=(x, 5000.0, 6000.0), perfil="W 200×35,9", papel="viga", rotacao=0.0,
                      atributos={"elemento": "viga", "marca": "V2"}))
    return doc


@pytest.fixture(scope="module")
def an():
    r = AE.calcular(_portico(), {"vento": False})
    conv = lambda o: o.tolist() if isinstance(o, np.ndarray) else float(o) if isinstance(o, np.floating) else int(o)
    return json.loads(json.dumps(r, default=conv))       # como sai do analise_estrutural.json gravado


def _linhas(an):
    return {ln["chave"]: ln for s in MA.linhas_comparacao(an) for ln in s["linhas"]}


def test_carga_total_do_peso_proprio_e_o_peso_dos_perfis(an):
    L = _linhas(an)
    peso = (32.7 * 6.0 * 4 + 35.9 * (6.0 * 2 + 5.0 * 2)) * G / 1000          # kN
    assert abs(L["carga|PP|Fz"]["nosso"] - peso) < 0.02 * peso                # + para baixo
    assert L["carga|PP|Fz"]["un"] == "F"


def test_reacoes_do_quadro_sao_as_da_envoltoria(an):
    L = _linhas(an)
    for e in an["reacoes_envoltoria"]:
        assert L["reacao|%s|Fz_max" % e["chave"]]["nosso"] == e["Fz_max"][0]
        assert L["reacao|%s|M_max" % e["chave"]]["un"] == "M"
    soma = sum(e["Fz_max"][0] for e in an["reacoes_envoltoria"])
    assert soma > L["carga|PP|Fz"]["nosso"]                                  # ELU: com os coeficientes


def test_esforcos_pecas_e_bases_no_quadro(an):
    L = _linhas(an)
    assert L["esforco|pilar|W 250×32,7|Nc"]["nosso"] > 0
    assert "esforco|viga|W 200×35,9|M" in L
    assert L["peca|pilar|W 250×32,7|perfil"]["nosso"] == "W 250×32,7"
    assert 0 < L["peca|pilar|W 250×32,7|uso"]["nosso"] < 100
    tps = [k for k in L if k.startswith("base|") and k.endswith("|tp")]
    assert tps and all(L[k]["nosso"] > 0 for k in tps)


def test_memorial_tem_as_secoes_e_a_conta(an):
    h = MA.html_memorial(an, {"nome": "pórtico de teste", "local": "Cascavel / PR"}, comparacao=MA.ler_comparacao("/nao/existe"))
    for t in ("Premissas", "Casos de carga", "Combinações", "2ª ordem", "Verificação das peças", "Reações nas bases",
              "Bases dos pilares", "Ligações viga–pilar", "Apontamentos", "Comparação com o engenheiro"):
        assert t in h, t
    assert "N<sub>c,Rd</sub>" in h and "5.5.1.2" in h                       # a conta da peça, como na tela
    assert "Tabela 18" in h                                                  # a conta da base
    assert "pórtico de teste" in h and "Cascavel / PR" in h


def test_gravar_e_ler_a_comparacao(tmp_path):
    c = MA.gravar_comparacao(str(tmp_path), {"unidade": "tf", "engenheiro": "Eng. X", "valores": {"carga|PP|Fz": "1,6", "a": "2"}})
    assert c["unidade"] == "tf" and c["valores"] == {"carga|PP|Fz": "1,6", "a": "2"}
    c = MA.gravar_comparacao(str(tmp_path), {"unidade": "lb", "valores": {"a": ""}})       # vazio apaga; unidade inválida fica
    assert c["unidade"] == "tf" and c["valores"] == {"carga|PP|Fz": "1,6"} and c["engenheiro"] == "Eng. X"
    assert MA.ler_comparacao(str(tmp_path))["valores"] == {"carga|PP|Fz": "1,6"}


def test_numero_digitado_e_diferenca():
    assert MA.numero("1.234,5") == 1234.5 and MA.numero("−12,3") == -12.3 and MA.numero("12.5") == 12.5
    assert MA.numero("") is None and MA.numero("abc") is None
    assert MA.diferenca(110.0, 100.0) == pytest.approx(0.10)
    assert MA.diferenca(-55.0, -50.0) == pytest.approx(-0.10)               # arrancamento: compara com o sinal
    assert MA.diferenca(1.0, 0.0) is None and MA.diferenca("W", 1.0) is None
    assert MA.na_unidade(G * 10, "F", "tf") == pytest.approx(10.0) and MA.na_unidade(5.0, "mm", "tf") == 5.0


def test_quadro_mostra_a_diferenca_na_unidade_dele(an):
    L = _linhas(an)
    pp = L["carga|PP|Fz"]["nosso"]
    comp = {"unidade": "tf", "valores": {"carga|PP|Fz": ("%.3f" % (pp / G * 0.8)).replace(".", ","),
                                         "peca|pilar|W 250×32,7|perfil": "W 250 × 32,7"}}
    h = MA.html_comparacao(MA.linhas_comparacao(an), comp)
    assert "+25,0%" in h                                                     # nosso ÷ (0,8 × nosso) − 1
    assert ">igual<" in h                                                    # o perfil, sem olhar os espaços
    assert "2 de " in h


def test_memorial_do_premoldado_sai_sem_as_secoes_de_aco():
    from testes.test_pecas_analise import _portico as portico_de_concreto
    _, an = portico_de_concreto()
    h = MA.html_memorial(an, {"nome": "concreto"})
    assert "Premissas" in h and "Reações nas bases" in h
    assert "Bases dos pilares" not in h                                      # a base de concreto não é a 6.7
