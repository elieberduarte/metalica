# -*- coding: utf-8 -*-
"""A quantidade de cada camada no painel Camadas é a do RESUMO DA OBRA (usuário, 06/11: "preciso que ambos sejam iguais, não
posso mostrar para o fornecedor um peso na apresentação e na proposta outro").

O resumo da obra reparte o que ele soma pela camada de cada peça do modelo — o aço das posições (kg), as telhas (m²) e a
funilaria (m), as lançadas no modelo pela mesma conta do Quadro 8 — e grava em detalhamento/resumo-numeros.json; a rota
GET /api/projetos/<s>/camadas-quantidade devolve isso, se o resumo é mais novo que o modelo, e o arquitetônico (fora da
proposta) pela conta do 3D.

No modelo da Hora Certa · Galpão Novo inteiro (06/11, 25.750 peças) a soma das camadas deu 428.010,749 kg (resumo
428.010,751: o arredondamento de cada camada a 3 casas), 9.344,9 m² e 623,9 m — os números do resumo gravado em 05/11.
Aqui, uma amostra do mesmo modelo (testes/dados_editor/hora_certa_gn_amostra.json)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AMOSTRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_editor", "hora_certa_gn_amostra.json")


def _resumo():
    """A conta da rota POST /resumos (app.py), sem PDF nem fotos."""
    from nucleo3d.modelo import Documento
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    m = json.load(open(AMOSTRA, encoding="utf-8"))
    doc = Documento.de_dict({"entidades": m["entidades"], "camadas": m["camadas"]})
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    nomes = r.get("nomes") or {}
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "gn"},
                                  nomes_telhas=nomes.get("telhas"), fixadores=r.get("objetos_fixadores"))
    lista["pre_moldados"] = r.get("fora_do_aco") or []
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"],
           "fora_por_camada": r.get("fora_por_camada") or {}}
    return m, resumos.levantar_resumos(doc, lev, lista, nomes, {})


def test_a_soma_das_camadas_e_o_numero_do_resumo():
    m, R = _resumo()
    C, n = R["camadas"], R["numeros"]
    assert abs(sum(q["kg"] for q in C.values()) - n["peso_aco"]) < 0.01, (C, n["peso_aco"])
    assert abs(sum(q["m2"] for q in C.values()) - n["m2_telhas"]) < 0.01, (C, n["m2_telhas"])
    assert abs(sum(q["m"] for q in C.values()) - sum(f["ml"] for f in R["funilaria"])) < 0.01, (C, R["funilaria"])
    # cada coisa na camada dela
    assert C["Pilares"]["kg"] > 0 and C["Placas de base"]["kg"] > 0 and C["Terças da cobertura"]["kg"] > 0
    assert C["Telhas"]["m2"] > 0 and not C["Telhas"]["kg"]
    assert C["Calhas"]["m"] > 0 and C["Cumeeiras"]["m"] > 0
    # o arquitetônico não é do resumo (nem da proposta)
    assert not any(c.startswith("ARQ") for c in C), list(C)
    # o peso dos pilares é o das posições deles: o mesmo da lista de materiais, não o do 3D
    assert n["peso_aco"] > 0


def test_a_rota_le_o_resumo_e_diz_se_o_modelo_mudou(tmp_path, monkeypatch):
    import app
    from saida import resumos
    m, R = _resumo()
    pasta = tmp_path / "gn"
    (pasta / "detalhamento").mkdir(parents=True)
    (pasta / "projeto.json").write_text(json.dumps({"nome": "gn"}), encoding="utf-8")
    (pasta / "modelo.json").write_text(json.dumps({"nome": "gn", "unidade": "mm", "entidades": m["entidades"], "camadas": m["camadas"]},
                                                  ensure_ascii=False), encoding="utf-8")
    time.sleep(0.05)
    R.update({"projeto": {"nome": "gn"}, "dados": {}})
    resumos.gerar_resumos(str(pasta / "detalhamento"), R, imprimir_pdf=False)   # o resumo grava as camadas no resumo-numeros
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    q = app.quantidade_das_camadas("gn")
    assert q["resumo"]["tem_camadas"] and q["resumo"]["atual"] and q["resumo"]["gerado"]
    assert abs(sum(c["kg"] for c in q["camadas"].values()) - R["numeros"]["peso_aco"]) < 0.01
    # o rodapé do modo ver (usuário, 10/11: "Área obra - Altura - Qtd peças - Peso estrutura"): a área e o peso são os do resumo
    assert abs(q["obra"]["peso_aco"] - R["numeros"]["peso_aco"]) < 0.1, q["obra"]
    assert abs(q["obra"]["area_m2"] - R["dimensoes"]["area_m2"]) < 0.01, (q["obra"], R["dimensoes"])
    # o arquitetônico pela conta do 3D: as paredes em m², o pilar em unidade
    assert q["arq"]["ARQ — Paredes de fachada"]["m2"] > 0 and q["arq"]["ARQ — Pilares do arquitetônico"]["un"] == 1
    # o modelo gravado depois do resumo: os números ficam (os da proposta), com o aviso
    futuro = time.time() + 5
    os.utime(pasta / "modelo.json", (futuro, futuro))
    q2 = app.quantidade_das_camadas("gn")
    assert not q2["resumo"]["atual"] and q2["camadas"] == q["camadas"]
    # o resumo de antes das camadas (sem a chave): a rota diz, e o painel pede o resumo de novo
    d = json.loads((pasta / "detalhamento" / resumos.ARQ_NUMEROS).read_text(encoding="utf-8"))
    d.pop("camadas")
    (pasta / "detalhamento" / resumos.ARQ_NUMEROS).write_text(json.dumps(d), encoding="utf-8")
    assert not app.quantidade_das_camadas("gn")["resumo"]["tem_camadas"]
