# -*- coding: utf-8 -*-
"""Várias empresas na proposta (27/10/2026): a principal continua em <dados>/fabrica/ sem mudar nada; outra empresa
(a DEZN Construtora) em <dados>/fabrica/empresas/<id>/ com marca, cores, numeração e layout próprios; a proposta
grava a escolhida; o layout compacto (o piloto C aprovado) sai em 2 páginas no caso real da WE Coqueiral; e a regra
"a proposta não entrega o estudo" (medida de perfil vira aviso)."""
import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import comercial as C                 # noqa: E402
from saida import comercial_servico as CS        # noqa: E402
from saida import proposta_compacta as PC        # noqa: E402
from saida import proposta_html as PH            # noqa: E402

HERMES = {"razao_social": "Metalúrgica Teste Ltda.", "cnpj": "00.000.000/0001-00", "cidade": "Cascavel", "uf": "PR"}
DEZN = {"nome_comercial": "DEZN Construtora", "layout": "compacto", "prefixo_numero": "DZ",
        "cores": {"primaria": "#22346E", "destaque": "#800080", "apoio": "#7F9FFF"}}

#: a WE Coqueiral R00 (aprovada 27/10), na regra genérica: perfil só pelo tipo, peso estimado e cargas ficam
WE = {
    "numero": "DZ-2026-001", "revisao": "R00", "data": "27/10/2026", "empresa": "dezn", "projeto_por": "cliente",
    "titulo": "Vigas de içamento dos elevadores",
    "ref": "Proposta para fabricação e instalação das vigas metálicas de içamento dos elevadores.",
    "cliente": {"nome": "Coqueiral Residence Inc. de Imóveis SPE Ltda.", "contato": "WE Inc."},
    "obra": {"nome": "WE Coqueiral Residence", "cidade": "Cascavel", "uf": "PR"},
    "destaques": [{"valor": "06", "texto": "vigas em perfil W"}, {"valor": "12", "texto": "ganchos de 3.000 kgf"},
                  {"valor": "295 kg", "texto": "de estrutura"}, {"valor": "RAL 1003", "texto": "pintura PU amarela"}],
    "carregamentos": [{"carga": "3.000 kgf por gancho", "descricao": "Carga pontual de içamento (12 ganchos)"},
                      {"carga": "NBR 6120:2019", "descricao": "Peso próprio e sobrecargas de norma"}],
    "geometria": [{"nome": "Vigas com vão de 1,53 m (04 un.)", "largura": None, "comprimento": 6.12, "area": None},
                  {"nome": "Vigas com vão de 1,90 m (02 un.)", "largura": None, "comprimento": 3.80, "area": None}],
    "peso_kg": 295,
    "escopo": [{"titulo": "Estrutura", "itens": [
        {"texto": "06 vigas metálicas em perfil laminado tipo W"},
        {"texto": "12 chapas de fixação das vigas na estrutura de concreto existente"},
        {"texto": "12 conjuntos de ganchos de içamento em barra redonda com chapa de fixação"},
        {"texto": "Decapagem química para preparação da estrutura"},
        {"texto": "Pintura em tinta PU, cor amarelo RAL 1003, aplicada sob alta pressão"},
        {"texto": "Parafusos e acessórios de fixação"}, {"texto": "Transporte até a obra e instalação"}]}],
    "exclusoes": ["Projeto estrutural e detalhamento das vigas e dos ganchos (projeto do cliente)",
                  "Fornecimento, instalação e içamento (grua) dos elevadores e o plano de içamento",
                  "Serviços em concreto armado e alvenaria", "Ensaios e provas de carga das vigas e dos ganchos",
                  "Itens não descritos nesta proposta (portas, escadas, guarda-corpo, forro, linha de vida…)"],
    "responsabilidades": ["Energia elétrica trifásica (220 V – 100 A) no canteiro", "Local na obra para armazenar a estrutura",
                          "Acessos nivelados e compactados", "Estrutura de concreto concluída e liberada",
                          "Poços dos elevadores com as proteções coletivas da NR-18", "Legalização da obra e dos projetos",
                          "Livre acesso dos equipamentos e da equipe", "Áreas de convívio da NR-18",
                          "Autorizações para uso da via ou do passeio público", "Segurança e vigilância do canteiro",
                          "Desligamento de rede junto à concessionária, se necessário",
                          "Seguro da obra e da estrutura, inclusive após a entrega", "Caçamba para retirada de resíduos"],
    "condicoes": ["Materiais conforme especificados no projeto do cliente.",
                  "ISSQN de 3 % sobre a mão de obra (10 % do valor total).",
                  "Havendo revisão do projeto, os valores poderão ser reajustados."],
    "seguranca": ["EPI: uniforme, botina, cinto de segurança, capacete, luvas, protetor auricular e óculos.",
                  "PGR e PCMSO conforme a legislação, em especial a NR-7."],
    "investimento": {"valor": 22500.0, "partes": [], "opcionais": [], "notas": []},
    "pagamento": "A combinar.", "prazo": "A combinar.", "parcelas": [], "prazos_etapas": {}, "imagens": [],
    "mostrar_ficha": True, "revisoes": [],
}


def _dados(com_dezn=True):
    d = tempfile.mkdtemp(prefix="mtl_emp_")
    os.makedirs(os.path.join(d, "fabrica", "marca"))
    json.dump(HERMES, open(os.path.join(d, "fabrica", "empresa.json"), "w", encoding="utf-8"))
    json.dump({str(date.today().year): 7}, open(os.path.join(d, "fabrica", "comercial-seq.json"), "w"))
    if com_dezn:
        C.gravar_empresa(d, DEZN, "dezn")
        os.makedirs(C.pasta_marca(d, "dezn"))
        with open(os.path.join(C.pasta_marca(d, "dezn"), "logo.svg"), "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#22346E"/></svg>')
    return d


def test_principal_continua_onde_estava():
    d = _dados(com_dezn=False)
    assert [e["id"] for e in C.listar_empresas(d)] == ["principal"]
    e = C.ler_empresa(d)
    assert e["razao_social"] == HERMES["razao_social"] and e["id"] == "principal" and e["layout"] == "classico"
    assert C.ler_empresa(d, "principal") == e
    # a sequência de sempre continua (fabrica/comercial-seq.json), sem prefixo
    assert C.proximo_numero(d) == "%d-008" % date.today().year
    # a proposta clássica sai igual com os campos novos da empresa (id, layout, prefixo)
    velho = {k: v for k, v in e.items() if k not in ("id", "layout", "prefixo_numero")}
    P = dict(WE, empresa="principal")
    assert PH.html_proposta(P, e) == PH.html_proposta(P, velho)


def test_cada_empresa_com_marca_numero_e_layout():
    d = _dados()
    assert [e["id"] for e in C.listar_empresas(d)] == ["principal", "dezn"]
    z = C.ler_empresa(d, "dezn")
    assert z["layout"] == "compacto" and z["cores"]["apoio"] == "#7F9FFF" and z["logo"].endswith("logo.svg")
    ano = date.today().year
    assert C.proximo_numero(d, empresa_id="dezn") == "DZ-%d-001" % ano
    assert C.proximo_numero(d) == "%d-008" % ano                       # a da principal não andou com a da DEZN
    assert C.proximo_numero(d, empresa_id="dezn") == "DZ-%d-002" % ano
    for ruim in ("../x", "A B", "x/y"):
        try:
            C.ler_empresa(d, ruim)
            assert False, ruim
        except ValueError:
            pass
    try:
        C.ler_empresa(d, "naoexiste")
        assert False
    except ValueError:
        pass


def test_compacto_da_dezn_sem_nada_da_hermes():
    d = _dados()
    corpo, css = PC.html_proposta(WE, C.ler_empresa(d, "dezn"))
    texto = corpo + css
    assert "#22346E" in css and "#800080" in css
    # 30/10 (usuário): o logo vai para o rodapé; número/revisão fora do papel; o valor uma vez só (no Investimento)
    assert "@bottom-center { content: url(\"data:image/svg+xml;base64," in css
    assert "DZ-2026-001" not in texto and "R00" not in texto
    assert corpo.count("R$ 22.500,00") == 1 and "vinte e dois mil e quinhentos reais" in corpo
    assert "Cliente" in corpo and "A/C WE Inc." in corpo and "Obra" in corpo
    for proibido in ("Metalúrgica Teste", "Hermes", "Antidumping", "A-36", "BDI", "margem", "{{", "(00) 00000"):
        assert proibido not in texto, proibido
    assert "Vigas de içamento dos elevadores" in corpo and "Dados técnicos" in corpo and "295 kg" in corpo
    sem_ficha = PC.html_proposta(dict(WE, mostrar_ficha=False), C.ler_empresa(d, "dezn"))[0]
    assert "Dados técnicos" not in sem_ficha


def test_linha_metalica_assina_sem_construtora():
    """30/10 (usuário): "não vamos utilizar construtora nas propostas de metálica" — a linha "metalica" da empresa troca
    o nome e o logo; sem ela (ou noutra linha) fica a marca de sempre"""
    d = _dados()
    with open(os.path.join(C.pasta_marca(d, "dezn"), "logo_metalica.svg"), "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><text>DEZN</text></svg>')
    C.gravar_empresa(d, dict(DEZN, linhas={"metalica": {"nome_comercial": "DEZN", "logo": "logo_metalica.svg"}}), "dezn")
    z = C.ler_empresa(d, "dezn")
    assert z["linhas"]["metalica"]["logo"].endswith("logo_metalica.svg") and os.path.isabs(z["linhas"]["metalica"]["logo"])
    m = C.empresa_da_linha(z)                               # sem linha na proposta: vale a metálica
    assert m["nome_comercial"] == "DEZN" and m["logo"].endswith("logo_metalica.svg")
    assert C.empresa_da_linha(z, "civil")["nome_comercial"] == "DEZN Construtora"
    corpo = PC.html_proposta(WE, z)[0]
    assert "<b>DEZN</b>" in corpo and "Construtora" not in corpo
    assert "DEZN Construtora" in PC.html_proposta(dict(WE, linha="civil"), z)[0]
    # gravar pela tela (aba Empresa, sem as linhas no corpo — ou com o que leu, caminhos inteiros) não perde a linha
    C.gravar_empresa(d, {"nome_comercial": "DEZN Construtora", "layout": "compacto"}, "dezn")
    assert C.ler_empresa(d, "dezn")["linhas"]["metalica"]["nome_comercial"] == "DEZN"
    C.gravar_empresa(d, C.ler_empresa(d, "dezn"), "dezn")
    with open(os.path.join(C.pasta_empresa(d, "dezn"), "empresa.json"), encoding="utf-8") as f:
        assert json.load(f)["linhas"]["metalica"]["logo"] == "logo_metalica.svg"


def test_compacto_imprime_em_duas_paginas():
    """o piloto C aprovado: a WE Coqueiral (serviço simples) fecha em 2 páginas, com a assinatura junto do valor"""
    import pymupdf
    d = _dados()
    pasta = tempfile.mkdtemp(prefix="mtl_pdf_")
    r = PC.gerar_pdf(WE, C.ler_empresa(d, "dezn"), pasta, "Proposta_WE")
    assert r.get("pdf"), r
    doc = pymupdf.open(r["pdf"])
    assert len(doc) == 2
    ultima = doc[-1].get_text()
    assert "Investimento" in ultima and "Atenciosamente" in ultima


def test_medida_de_perfil_vira_aviso():
    P = dict(WE)
    assert not [a for a in C.avisos_proposta(P) if "Medida de perfil" in a]
    for txt in ("06 vigas em perfil W200x15,0", "Terças Ue 200×75×25×2,25", "Pilares HP 250"):
        P = dict(WE, escopo=[{"titulo": "x", "itens": [{"texto": txt}]}])
        assert [a for a in C.avisos_proposta(P) if "Medida de perfil" in a], txt
    # os itens que o sistema sugere já são genéricos (perfil U, TP40)
    LISTA = {"posicoes": [{"categoria": "TERÇAS"}, {"categoria": "TIRANTES"}], "acessorios": [{"nome": "CHUMBADOR 25x600"}]}
    ORC = {"linhas": [{"grupo": "telhas", "descricao": "Telha TP40 0.50MM"}, {"grupo": "telhas", "descricao": "Calhas"}]}
    itens = C.escopo_sugerido(LISTA, ORC, {"numeros": {"tesouras": 7}, "dimensoes": {"trechos": [{"vao": 14700}]}}, "hermes")
    assert not [i for i in itens if C.PERFIL_ESPECIFICO.search(i["texto"])]


def test_servico_escolhe_a_empresa_e_renumera(monkeypatch):
    d = _dados()
    pasta = os.path.join(d, "obra")
    os.makedirs(pasta)
    ctx = CS.Contexto("obra", pasta, d, {"nome": "Obra", "cliente": "Cli", "local": "Cascavel - PR", "tipo": "galpao"},
                      lambda: {}, lambda: {}, lambda cam: {"nome": os.path.basename(cam), "url": "/x/" + os.path.basename(cam)})
    S = CS.tratar(ctx, "", None)
    assert S["proposta"]["empresa"] == "principal" and [e["id"] for e in S["empresas"]] == ["principal", "dezn"]
    S = CS.tratar(ctx, "", {"proposta": S["proposta"]})
    ano = date.today().year
    assert S["proposta"]["numero"] == "%d-008" % ano
    S = CS.tratar(ctx, "", {"proposta": dict(S["proposta"], empresa="dezn")})
    assert S["proposta"]["numero"] == "DZ-%d-001" % ano and S["empresa"]["id"] == "dezn"
    assert any("passada para a empresa" in h["texto"] for h in S["historico"])
    chamados = []
    monkeypatch.setattr(PC, "gerar_pdf", lambda P, emp, pasta_, nome, *a: chamados.append(emp["id"]) or {"erro_pdf": "simulado"})
    CS.tratar(ctx, "proposta-pdf", {})
    assert chamados == ["dezn"]                                       # o layout é o da empresa da proposta
    S = CS.tratar(ctx, "empresa", {"nova": "Construtora Nova Ltda."})
    assert S["proposta"]["empresa"] == "construtora-nova-ltda" and S["empresa"]["layout"] == "compacto"
    assert S["proposta"]["numero"] == "%d-001" % ano
