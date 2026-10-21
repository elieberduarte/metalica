# -*- coding: utf-8 -*-
"""O configurador de galpões direto ao orçamento (usuário, 20/10: "direto ao orçamento"): a lista do
dimensionamento vira a lista de materiais que o orçamento lê, enquanto o galpão não é detalhado."""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.galpao import dimensionar                      # noqa: E402
from nucleo.modelo_galpao import DadosGalpao               # noqa: E402
from saida import estudo_galpao as E, orcamento as O       # noqa: E402


def test_lista_do_estudo_tem_o_aco_do_calculo_e_as_telhas():
    p = dimensionar(DadosGalpao())
    lista = E.lista_do_estudo(p)
    assert lista["estudo"] and lista["origem"] == E.ORIGEM
    pos = lista["posicoes"]
    # todo o aço do cálculo, menos parafusos/chumbadores (estimativa percentual, fora, com aviso)
    aco = sum(x["peso_total"] for x in pos if x["classe"] not in ("Telha", "Cumeeira"))
    diversos = sum(x.peso_total_kg for x in p.lista_material if x.marca == E.MARCA_DIVERSOS)
    # (a lista refaz o peso pelo kg/m sem o arredondamento do unitário do cálculo: até 0,1 %)
    assert abs(aco - (p.peso_total_kg - diversos)) < 0.001 * p.peso_total_kg and lista["diversos_kg"] == round(diversos, 1)
    # telha da cobertura nas duas águas, no comprimento da água; cumeeira; fechamento e oitões (telha metálica)
    marcas = {x["marca"]: x for x in pos}
    assert marcas["TL"]["quantidade"] == 2 * 40 and marcas["TL"]["comprimento"] == round(p.dados.comprimento_agua * 1000)
    assert "CU" in marcas and "TF" in marcas and "TO" in marcas
    assert not any(x["marca"] == "TF" for x in E.lista_do_estudo(dimensionar(DadosGalpao(
        fechamento_lateral="alvenaria cerâmica 14 cm", desloc_horizontal=150)))["posicoes"])


def test_orcamento_do_estudo_classifica_por_grupo_de_preco():
    lista = E.lista_do_estudo(dimensionar(DadosGalpao()))
    R = O.montar(lista, None, {}, projeto={"nome": "Galpão"})
    ids = {li["id"] for li in R["linhas"]}
    assert "w" in ids and any(i.startswith("chapa:") for i in ids) and any(i.startswith("telha:") for i in ids)
    assert "cumeeira" in ids


def test_rota_do_orcamento_usa_o_estudo_no_galpao_sem_detalhamento():
    """Pelas rotas do servidor, numa pasta de dados temporária: o galpão com os dados do formulário e sem
    detalhamento vai ao orçamento pela lista do estudo, com o aviso; as etapas já aparecem no cartão."""
    with tempfile.TemporaryDirectory() as raiz:
        antes = os.environ.get("METALICA_DADOS")
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            s = app.criar_projeto({"nome": "Galpão estudo", "tipo": "galpao",
                                   "dados": {"nome": "Galpão estudo", "vao": 20, "comprimento": 40}})["slug"]
            if not app.COMERCIAL:
                return                                      # o programa instalado não leva a parte comercial
            R = app.rota_orcamento(s)
            assert any("ESTUDO" in a["texto"] for a in R["avisos"])
            assert any(li["id"] == "w" for li in R["linhas"])
            et = {e["chave"]: e for e in app.etapas_do_projeto(s)["etapas"]}
            assert et["engenharia"]["situacao"] == "andamento" and "comercial" in et
            # detalhado, vale a lista do detalhamento (não o estudo)
            os.makedirs(os.path.join(raiz, s, "detalhamento"))
            import json
            with open(os.path.join(raiz, s, "detalhamento", "lista-de-materiais.json"), "w", encoding="utf-8") as f:
                json.dump({"posicoes": [], "acessorios": []}, f)
            assert not app._lista_do_orcamento(s).get("estudo")
        finally:
            if antes is None:
                os.environ.pop("METALICA_DADOS", None)
            else:
                os.environ["METALICA_DADOS"] = antes
            importlib.reload(app)
