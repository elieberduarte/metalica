# -*- coding: utf-8 -*-
"""Rodada 2 da prancha padrão de telhas (usuário, 12/11, pelo OBRA · SOORO COMPRESSORES N.2, sobre a prancha 13 da ME
Sooro · Sala de Compressores; vale para as duas obras da Sooro e para o padrão):

* C — a telha reta que continua a multidobra saía "MD1-C" ("MD-C? esse nome acho que não está certo"): é uma TL, com
  marca própria (o número seguinte ao maior TL das posições), no 2D, na lista e nos nomes guardados;
* B — na planta dos tipos o nome da multidobra ("MD1 2,22 m") ficava dentro da faixa estreita dela, encavalado:
  "Colocar esse nome para fora do desenho";
* D — no forro em anel (FACE 1 da Sala) cada uma das 100 chapas tinha a cota 960 e o nome fora: "Como são valores que se
  repetem vamos deixar apenas as cotas nas pontas e colocar o nome TL dentro da telha";
* a relação dos parafusos de telha (OA/OB/costura, a mesma do resumo de materiais) entra no detalhamento das telhas.

Os dados: o recorte da Sala (uma MD1 com a reta que a continua, as terças e as longarinas em volta e uma cumeeira) e,
para o anel, uma face pequena montada aqui no formato de faces_de_telhas."""
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Cota, Desenho, Polilinha, Texto     # noqa: E402
from nucleo2d.detalhe import telhas as T                         # noqa: E402
from nucleo3d.modelo import Documento                            # noqa: E402

RECORTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "sala_compressores_md1.json.gz")


def _doc():
    with gzip.open(RECORTE, "rt", encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def _pecas(doc):
    return [e for e in doc.entidades.values() if getattr(e, "vertices", None)]


def _ents(d):
    return list(d.entidades.values()) if isinstance(d.entidades, dict) else list(d.entidades)


def test_complemento_da_multidobra_e_uma_tl():
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao
    doc = _doc()
    r = detalhar(doc, grupos=["telhas"], converter=False)
    nomes = r["nomes"]["telhas"]
    tl_pos = {str(v) for v in r["nomes"]["posicoes"].values() if re.match(r"^TL\d+$", str(v))}
    nome_c = nomes.get("M115-C")
    assert nome_c and re.match(r"^TL\d+$", nome_c), nomes
    assert nome_c not in tl_pos                                         # marca própria, não a de outra posição
    textos = [str(getattr(e, "texto", "") or "") for d in r["desenhos"].values() for e in _ents(d)]
    assert not any("MD1-C" in t for t in textos), [t for t in textos if "-C" in t][:5]
    assert any(t.startswith("telha complementar %s:" % nome_c) for t in textos)
    # a lista diz o mesmo nome que as pranchas
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], nomes_telhas=nomes)
    comp = [li for li in lista["posicoes"] if li.get("classe") == "Telha (complemento da multi-dobra)"]
    assert comp and all(li["nome"] == nome_c for li in comp), comp
    # estável: o Detalhar seguinte, com os nomes guardados, dá o mesmo
    r2 = detalhar(_doc(), grupos=["telhas"], converter=False, nomes=r["nomes"])
    assert r2["nomes"]["telhas"]["M115-C"] == nome_c


def test_nome_da_multidobra_fora_da_planta():
    doc = _doc()
    pecas = _pecas(doc)
    md = T.multidobras(pecas)
    for t in md["telhas"]:
        t["nome"], t["nome_c"] = "MD1", "TL18"
    faces = T.faces_de_telhas(pecas, md)
    d = Desenho(nome="t", escala=50.0)
    T.desenho_da_planta_das_telhas(faces, None, d, 0.0, 0.0)
    ents = _ents(d)
    xs = [q[0] for e in ents if isinstance(e, Polilinha) for q in e.vertices]
    ys = [q[1] for e in ents if isinstance(e, Polilinha) for q in e.vertices]
    md_t = [e for e in ents if isinstance(e, Texto) and str(e.texto).startswith("MD1  ")]
    assert md_t, [e.texto for e in ents if isinstance(e, Texto)]
    for e in md_t:                          # fora da planta, ao lado da fileira
        assert (e.posicao[0] < min(xs) or e.posicao[0] > max(xs) or e.posicao[1] < min(ys) or e.posicao[1] > max(ys)), e.posicao
    # a reta que continua a multidobra é a TL, dentro da planta
    assert any(str(e.texto).startswith("TL18  ") for e in ents if isinstance(e, Texto))


def _anel(n_x=10, n_y=8, comp=960.0, passo=980.0):
    """um forro em anel como o da Sala: fileiras de baixo e de cima com a onda em y (em pé) e as laterais com a onda em
    x (deitadas)"""
    chapas = []
    largura = n_x * passo
    altura = n_y * passo + 2 * comp
    for i in range(n_x):
        x0 = i * passo
        for y0 in (0.0, altura - comp):
            chapas.append({"contorno": [(x0, y0), (x0 + passo, y0), (x0 + passo, y0 + comp), (x0, y0 + comp)],
                           "comprimento": comp, "nome": "TL2", "x": x0 + passo / 2, "y0": y0, "y1": y0 + comp, "alinhada": True})
    for j in range(n_y):
        y0 = comp + j * passo
        for x0 in (0.0, largura - comp):
            chapas.append({"contorno": [(x0, y0), (x0 + comp, y0), (x0 + comp, y0 + passo), (x0, y0 + passo)],
                           "comprimento": comp, "nome": "TL2", "x": x0 + comp / 2, "y0": y0, "y1": y0 + passo, "alinhada": False})
    return {"chapas": chapas, "tipo": "cobertura", "inclinacao": 0.0}, n_x, n_y


def test_forro_em_anel_cota_nas_pontas_e_nome_dentro():
    face, n_x, n_y = _anel()
    d = Desenho(nome="t", escala=50.0)
    T.desenho_da_paginacao(face, d, 0.0, 0.0, 1)
    ents = _ents(d)
    cotas_960 = [e for e in ents if isinstance(e, Cota) and e.texto == "960"]
    assert len(cotas_960) == 8, len(cotas_960)                          # a 1ª e a última de cada um dos 4 lados
    nomes = [e for e in ents if isinstance(e, Texto) and e.texto == "TL2"]
    assert len(nomes) == 2 * n_x + 2 * n_y                              # todas com o nome
    # cada nome dentro de uma chapa (e não abaixo ou ao lado dela)
    rets = [((min(q[0] for q in ch["contorno"]) - 60, min(q[1] for q in ch["contorno"]) - 60),
             (max(q[0] for q in ch["contorno"]) + 60, max(q[1] for q in ch["contorno"]) + 60)) for ch in face["chapas"]]
    for e in nomes:
        assert any(a[0] <= e.posicao[0] <= b[0] and a[1] <= e.posicao[1] <= b[1] for a, b in rets), e.posicao
    # o número da cota fica fixo (texto_pos) do outro lado do nome da chapa: girada a face na prancha, não se encontram
    for c in cotas_960:
        assert c.texto_pos is not None
        nome_ = min(nomes, key=lambda e: (e.posicao[0] - c.texto_pos[0]) ** 2 + (e.posicao[1] - c.texto_pos[1]) ** 2)
        assert ((nome_.posicao[0] - c.texto_pos[0]) ** 2 + (nome_.posicao[1] - c.texto_pos[1]) ** 2) ** 0.5 > 300.0


def test_relacao_dos_parafusos_no_detalhamento_das_telhas():
    from nucleo2d.detalhar import detalhar
    doc = _doc()
    doc.metadados["telha_dos_dados"] = "Telha TP40 0,50 galvalume pré-pintada bege RAL 1015"
    r = detalhar(doc, grupos=["telhas"], converter=False)
    textos = [str(getattr(e, "texto", "") or "") for d in r["desenhos"].values() for e in _ents(d)]
    assert T.TITULO_PARAFUSOS_TELHAS in textos
    assert any(t.startswith("OA ") for t in textos) and any(t.startswith('Costura 7/8"') for t in textos)
    assert any("bege" in t for t in textos)
