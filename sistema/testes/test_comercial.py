# -*- coding: utf-8 -*-
"""Área comercial (saida/comercial.py, comercial_servico.py, proposta_html.py, contrato_docs.py, docx_simples.py):
valores por extenso, parcelas, proposta inicial, cláusulas do contrato, avisos, etapas, financeiro, Word e o fluxo
do serviço (com a impressão do PDF simulada)."""
import json
import os
import sys
import tempfile
import zipfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import comercial as C                 # noqa: E402
from saida import comercial_servico as CS        # noqa: E402
from saida import contrato_docs as CD            # noqa: E402
from saida import proposta_html as PH            # noqa: E402

LISTA = {"posicoes": [{"marca": "T1", "classe": "Barra", "perfil": "U150X50X2.25", "categoria": "TERÇAS", "quantidade": 10, "comprimento": 6000, "peso_total": 300},
                      {"marca": "R1", "classe": "Barra redonda", "perfil": "FE RED 3/8''", "categoria": "TIRANTES", "quantidade": 10, "comprimento": 1500, "peso_total": 8}],
         "acessorios": [{"nome": "CHUMBADOR 25x600", "quantidade": 8}]}
ORC = {"cabecalho": {"area_m2": 412.5}, "totais": {"aco_kg": 6022.5, "fechamento": 165000.0, "telhas_ml": 835},
       "linhas": [{"grupo": "telhas", "descricao": "Telha TP40 0.50MM"}, {"grupo": "telhas", "descricao": "Cumeeira"}]}
NUM = {"numeros": {"tesouras": 7}, "dimensoes": {"trechos": [{"nome": "Galpão", "vao": 14700, "projecao": [27500, 15000]}]}}
EMPRESA = dict(C.EMPRESA_PADRAO, razao_social="EMPRESA TESTE LTDA", cnpj="00.000.000/0001-00", cidade="Cascavel", uf="PR",
               banco={"banco": "Banco X", "agencia": "1", "conta": "2"}, representante={"nome": "Fulano", "qualificacao": "sócio"})


def test_extenso_e_parcelas():
    assert C.extenso_reais(42250) == "quarenta e dois mil, duzentos e cinquenta reais"
    assert C.extenso_reais(2060000) == "dois milhões e sessenta mil reais"
    assert C.extenso_reais(1000000) == "um milhão de reais"
    assert C.extenso_reais(198000.5) == "cento e noventa e oito mil reais e cinquenta centavos"
    assert C.extenso_reais(1) == "um real" and C.extenso_reais(1100) == "mil e cem reais"
    assert C.reais(1234567.891) == "R$ 1.234.567,89"
    ps = C.gerar_parcelas(100000, 10, 3, date(2026, 1, 31))
    assert [p["valor"] for p in ps] == [10000.0, 30000.0, 30000.0, 30000.0]
    assert [p["vencimento"] for p in ps] == ["31/01/2026", "28/02/2026", "31/03/2026", "30/04/2026"]   # fim de mês ajustado
    ps = C.gerar_parcelas(100000, 0, 3, date(2026, 5, 10))
    assert abs(sum(p["valor"] for p in ps) - 100000) < 0.001 and ps[-1]["valor"] == 33333.34      # a última leva os centavos


def test_proposta_inicial_e_avisos():
    projeto = {"nome": "Galpão X", "cliente": "Cliente Y", "local": "Toledo - PR", "tipo": "ifc"}
    P = C.proposta_inicial(projeto, LISTA, ORC, NUM, EMPRESA, numero="2026-007", hoje=date(2026, 10, 3))
    assert P["numero"] == "2026-007" and P["data"] == "03/10/2026" and P["validade_dias"] == 15
    assert P["cliente"]["cidade"] == "Toledo" and P["cliente"]["uf"] == "PR" and P["projeto_por"] == "cliente"
    assert P["investimento"]["valor"] == 165000.0 and P["investimento"]["notas"] == []            # obra no PR: sem DIFAL
    assert P["geometria"] == [{"nome": "Galpão", "largura": 15.0, "comprimento": 27.5, "area": 412.5}]
    textos = [i["texto"] for i in P["escopo"][0]["itens"]]
    assert textos[0].startswith("Fabricação de toda a estrutura metálica conforme projetos")
    assert any(t.startswith("Placas de apoio e chumbadores") for t in textos)
    assert any(t.startswith("07 Tesouras metálicas treliçadas com 14,70m") for t in textos)
    assert any("Agulhamento" in t for t in textos) and any("Terças em perfil U" in t for t in textos)
    telha = [i for i in P["escopo"][0]["itens"] if i["texto"].startswith("Telha trapezoidal TP40 0,50mm")]
    assert telha and telha[0]["destaque"]
    assert C.PROJETO_CLIENTE in P["condicoes"]
    av = C.avisos_proposta(P)
    assert any("imagens" in a for a in av) and not any("valor" in a.lower() for a in av)
    fora = C.proposta_inicial(dict(projeto, local="Chapecó - SC"), LISTA, ORC, NUM, EMPRESA)
    assert fora["investimento"]["notas"] and "de Santa Catarina" in fora["investimento"]["notas"][0]


def test_clausulas_do_contrato():
    P = C.proposta_inicial({"nome": "Obra", "cliente": "Cli", "local": "Cascavel - PR", "tipo": "galpao"}, LISTA, ORC, NUM, EMPRESA, numero="2026-001")
    Cn = C.contrato_inicial(P, EMPRESA)
    Cn.update(valor=40000, arras=50000, parcelas=C.gerar_parcelas(40000, 0, 2, date(2027, 1, 10)))
    cl = C.clausulas_contrato(P, Cn, EMPRESA)
    titulos = [c["titulo"] for c in cl]
    assert titulos[:3] == ["OBJETO DO CONTRATO", "PREÇO", "PRAZO"] and titulos[-1] == "DO FORO"
    texto = json.dumps(cl, ensure_ascii=False)
    assert "CLÁUSULA SEGUNDA deste contrato refere-se ao material aplicado" in texto and "CLÁUSULA QUINTA" not in texto
    assert "R$ 40.000,00 (quarenta mil reais) como arras" in texto                  # arras limitadas ao valor
    assert "Elaborar todos os projetos" in texto                                     # projeto da contratada
    assert "Condições Gerais" not in texto and "Acordo de Confidencialidade" not in texto
    assert "noventa) dias a contar da data de liberação de montagem" in texto
    resp = next(c for c in cl if c["titulo"] == "RESPONSABILIDADES DA CONTRATANTE")["paragrafos"][0]["lista"]
    assert any("seguro da obra" in r for r in resp) and any("rigging" in r.lower() for r in resp)
    assert sum(1 for r in resp if "rigging" in r.lower()) == 1                       # a exclusão não se repete
    Cn["garantia"] = True
    assert any(c["titulo"] == "DA GARANTIA" for c in C.clausulas_contrato(P, Cn, EMPRESA))
    P["projeto_por"] = "cliente"
    assert "Seguir em sua totalidade o projeto executivo" in json.dumps(C.clausulas_contrato(P, Cn, EMPRESA), ensure_ascii=False)


def test_avisos_contrato_etapas_e_financeiro():
    P = {"investimento": {"valor": 100000}, "revisoes": [{"revisao": "R00"}]}
    Cn = {"valor": 95000, "data": "03/10/2026", "contratante": {"cnpj": "123"},
          "parcelas": [{"valor": 50000, "vencimento": "01/09/2026", "paga": True}, {"valor": 40000, "vencimento": "01/01/2099"}],
          "aditivos": [{"valor": 5000}], "testemunhas": [{}, {}], "situacao": "assinado"}
    av = " | ".join(C.avisos_contrato(P, Cn))
    assert "fora do formato" in av and "somam R$ 90.000,00" in av and "antes da data do contrato" in av and "-5,0%" in av
    F = C.resumo_financeiro(Cn, hoje=date(2026, 10, 3))
    assert F["total"] == 100000 and F["recebido"] == 50000 and F["a_receber"] == 50000 and F["atrasado"] == 0
    assert F["proxima"]["vencimento"] == "01/01/2099"
    with tempfile.TemporaryDirectory() as tmp:
        et = {e["chave"]: e for e in C.etapas({"proposta": P, "contrato": Cn, "etapas": {"projeto": {"situacao": "andamento"}}}, tmp)}
    assert et["contrato"]["situacao"] == "concluida" and et["contrato"]["automatica"]
    assert et["sinal"]["situacao"] == "concluida" and et["projeto"]["situacao"] == "andamento" and not et["projeto"]["automatica"]
    assert et["orcamento"]["situacao"] == "pendente"


def test_documentos_word_e_html():
    P = C.proposta_inicial({"nome": "Obra <A>", "cliente": "Cli", "local": "Cascavel - PR"}, LISTA, ORC, NUM, EMPRESA, numero="2026-002")
    Cn = C.contrato_inicial(P, EMPRESA)
    Cn["contratante"].update(razao_social="Cliente S.A.", cnpj="11.222.333/0001-44")
    with tempfile.TemporaryDirectory() as tmp:
        cam = CD.contrato_docx(P, Cn, EMPRESA, os.path.join(tmp, "c.docx"))
        with zipfile.ZipFile(cam) as z:
            doc = z.read("word/document.xml").decode("utf-8")
            assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml", "_rels/.rels"} <= set(z.namelist())
        assert "CONTRATO DE EMPREITADA GLOBAL" in doc and "CLIENTE S.A." in doc and "CLÁUSULA DÉCIMA" in doc
    corpo, css = PH.html_proposta(P, EMPRESA, NUM, ORC)
    assert "Obra &lt;A&gt;" in corpo and "Investimento total" in corpo and "R$ 165.000,00" in corpo
    assert "(Cento e sessenta e cinco mil reais)" in corpo and "Lei Antidumping" in corpo and "De acordo" in corpo
    assert "@page capa" in css


def test_fluxo_do_servico(monkeypatch):
    from saida import printpdf
    impressos = []

    def falso(h, pdf, **k):
        impressos.append(open(h, encoding="utf-8").read())
        open(pdf, "wb").write(b"%PDF-1.4 teste")
        return 1
    monkeypatch.setattr(printpdf, "imprimir", falso)
    with tempfile.TemporaryDirectory() as dados:
        pasta = os.path.join(dados, "obra")
        os.makedirs(os.path.join(pasta, "detalhamento"))
        json.dump(NUM, open(os.path.join(pasta, "detalhamento", "resumo-numeros.json"), "w", encoding="utf-8"))
        ctx = CS.Contexto("obra", pasta, dados, {"nome": "Obra Teste", "cliente": "Cli", "local": "Cascavel - PR", "tipo": "galpao"},
                          lambda: LISTA, lambda: ORC, lambda cam: {"nome": os.path.basename(cam), "url": "/saida/" + os.path.basename(cam)})
        S = CS.tratar(ctx, "", None)
        assert S["proposta_nova"] and S["empresa_incompleta"] and S["proposta"]["investimento"]["valor"] == 165000.0
        S = CS.tratar(ctx, "", {"proposta": S["proposta"]})
        assert S["proposta"]["numero"] == "%d-001" % date.today().year and not S["proposta_nova"]
        S = CS.tratar(ctx, "proposta-pdf", {})
        assert S["proposta"]["revisoes"][0]["revisao"] == "R00" and S["gerado"]["pdf"]["nome"].startswith("Proposta_")
        assert "Investimento total" in impressos[-1]
        S = CS.tratar(ctx, "nova-revisao", {})
        assert S["proposta"]["revisao"] == "R01"
        S = CS.tratar(ctx, "contrato", {})
        assert S["tem_contrato"] and S["contrato"]["valor"] == 165000.0
        Cn = S["contrato"]
        Cn["parcelas"] = CS.tratar(ctx, "parcelas", {"valor": 165000, "entrada_pct": 20, "n": 4, "primeira": "10/11/2026"})["parcelas"]
        Cn["aditivos"] = [{"data": "01/12/2026", "descricao": "Marquise", "valor": 9000, "prazo_dias": 5}]
        S = CS.tratar(ctx, "contrato-docs", {"contrato": Cn})
        assert S["gerado"]["docx"]["nome"].endswith(".docx") and S["gerado"]["pdf"]["nome"].endswith(".pdf")
        Cn = S["contrato"]
        Cn["parcelas"][0]["paga"] = True
        Cn["situacao"] = "assinado"
        S = CS.tratar(ctx, "", {"contrato": Cn})
        assert S["financeiro"]["recebido"] == 33000.0 and S["financeiro"]["total"] == 174000.0
        assert any("assinado" in h["texto"] for h in S["historico"])
        S = CS.tratar(ctx, "aditivo", {"indice": 0})
        assert "1º TERMO ADITIVO" in impressos[-1] and "nove mil reais" in impressos[-1]
        S = CS.tratar(ctx, "termo-aceite", {"data_vistoria": "10/02/2027", "pendencias": "Retoque\n"})
        assert "TERMO DE ACEITE" in impressos[-1] and "Retoque" in impressos[-1]
        etapas = S["etapas"]
        etapas[6]["situacao"] = "concluida"
        etapas[6]["automatica"] = False
        S = CS.tratar(ctx, "", {"etapas": etapas})
        assert S["etapas"][6]["situacao"] == "concluida" and S["etapas"][6]["realizado"]
        nomes = sorted(a["nome"] for a in S["arquivos"])
        assert len([n for n in nomes if n.endswith(".pdf")]) == 4 and any(n.endswith(".docx") for n in nomes)
        try:
            CS.tratar(ctx, "inexistente", {})
            assert False
        except ValueError:
            pass
