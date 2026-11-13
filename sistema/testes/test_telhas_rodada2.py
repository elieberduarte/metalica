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

from nucleo2d.desenho import Cota, Desenho, Linha, Polilinha, Texto     # noqa: E402
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


def test_detalhamento_velho_pede_detalhar_de_novo():
    """Depósito Químico, 12/11: só remontar as pranchas (sem Detalhar) não trazia a relação dos parafusos nem a TL nova — o
    detalhamento das telhas leva a edição dele, e o de antes da rodada 2 faz a montagem avisar"""
    from nucleo2d.detalhar import detalhar
    r = detalhar(_doc(), grupos=["telhas"], converter=False)
    d = next(d for k, d in r["desenhos"].items() if "telha" in k)
    assert d.metadados["detalhamento"]["edicao_telhas"] == T.EDICAO_TELHAS
    assert not T.detalhamento_de_telhas_velho(d)
    del d.metadados["detalhamento"]["edicao_telhas"]                     # como o de antes de 12/11
    assert T.detalhamento_de_telhas_velho(d)


def _textos_do_beiral(c, t):
    d = Desenho(nome="t", escala=50.0)
    T.desenho_do_corte_do_beiral(c, d, 0.0, 0.0, "MD1", "TL18")
    return [str(getattr(e, "texto", "") or "") for e in _ents(d)], d


def test_detalhe_do_beiral_exemplo_a():
    """o detalhe novo (usuário, 12/11: "Criar um novo com a tesoura e a telha no recorte"; escolhido o exemplo A): a ponta
    da tesoura, a 1ª terça e as longarinas cortadas, a MD1 e a TL18, as cotas da telha, a 1:20"""
    pecas = _pecas(_doc())
    t = T.multidobras(pecas)["telhas"][0]
    c = T.corte_do_beiral(pecas, t)
    assert c is not None
    perfis = {pc["perfil"] for pc in c["pecas_cortadas"]}
    assert "U150X50X2.28" in perfis and "C150X50X17X2.25" in perfis, perfis
    textos, d = _textos_do_beiral(c, t)
    assert T.TITULO_CORTE_BEIRAL in textos
    for esperado in ("556", "transpasse 350", "150", "saia 150"):
        assert esperado in textos, (esperado, textos)
    assert any(x.startswith("TERÇA ") and "U150×50×2,28" in x for x in textos), textos
    assert any(x.startswith("LONGARINA ") and "C150×50×17×2,25" in x for x in textos), textos
    assert any(x.startswith("R450 int.") for x in textos)
    assert any(x.startswith("TL18 – telha reta") for x in textos) and any(x.startswith("MD1 – multidobra") for x in textos)
    amp = {(e.atributos or {}).get("ampliacao") for e in _ents(d)}
    assert 2.5 in amp                                                    # 1:50 ampliado = 1:20


def test_detalhe_do_beiral_com_terca_que_termina_na_tesoura():
    """na Sala as terças e as longarinas são uma peça por vão e terminam no eixo da tesoura: o plano da tesoura passava
    entre elas e o detalhe saía sem a terça e sem as longarinas (sem os nomes e sem a saia)"""
    pecas = _pecas(_doc())
    t = T.multidobras(pecas)["telhas"][0]
    c0 = T.corte_do_beiral(pecas, t)
    n, d = c0["normal"], c0["plano"]
    ids_md = set(t["ids"])
    for e in pecas:
        if e.id in ids_md:
            continue
        pn = [sum(v[i] * n[i] for i in range(3)) for v in e.vertices]
        if max(pn) - min(pn) > 400.0 and min(pn) < d < max(pn):
            # a peça começa logo depois do plano da tesoura (um vão por peça)
            e.vertices = [tuple(v[i] + n[i] * (max(x, d + 1.0) - x) for i in range(3)) for v, x in zip(e.vertices, pn)]
    c = T.corte_do_beiral(pecas, t)
    perfis = {pc["perfil"] for pc in c["pecas_cortadas"]}
    assert "U150X50X2.28" in perfis and "C150X50X17X2.25" in perfis, perfis
    textos, _d = _textos_do_beiral(c, t)
    assert "saia 150" in textos and any(x.startswith("TERÇA ") for x in textos)


def test_multidobra_sem_a_cota_da_corda():
    """a cota da corda da MD1 (1790,07 por dentro, 1841,1 por fora), com as linhas de chamada longas por fora do canto,
    parecia a sombra do recorte da telha (usuário, 13/11: "tem duas linhas externas representando a sombra do recorte
    da telha"); escolhido tirar. As retas, o raio e o ângulo continuam."""
    t = T.multidobras(_pecas(_doc()))["telhas"][0]
    d = Desenho(nome="t", escala=50.0)
    T.desenho_da_multidobra(t, d, 0.0, 0.0, "MD1")
    cotas = [e for e in _ents(d) if isinstance(e, Cota)]
    textos = {str(c.texto or "") for c in cotas}
    assert "560" in textos and "990" in textos                          # as retas
    import math
    numeros = [float(x.replace(",", ".")) for x in textos if re.match(r"^\d+(,\d+)?$", x)]
    assert not any(abs(v - t["corda"]) < 1.0 for v in numeros), (numeros, t["corda"])   # nenhuma com o tamanho da corda
    # a cota mais longa do desenho é a da reta maior (990 × ampliação), não a corda de ~1800
    amp = max(float((e.atributos or {}).get("ampliacao") or 1.0) for e in _ents(d))
    maior = max(math.dist(c.p1, c.p2) for c in cotas) / amp
    assert maior < 0.9 * t["corda"], (maior, t["corda"])


def _recorte(nome):
    with gzip.open(os.path.join(os.path.dirname(RECORTE), nome), "rt", encoding="utf-8") as f:
        return _pecas(Documento.de_dict(json.load(f)))


def test_corte_da_cobertura_da_sala():
    """o CORTE DA COBERTURA (usuário, 13/11, pelo SOORO N.2: "um corte da cobertura com as telhas na tesoura, completo … para
    ver todos os transpasses"; escolhido o exemplo B — o corte com os comprimentos e os transpasses nos detalhes)"""
    pecas = _pecas(_doc())
    md = T.multidobras(pecas)
    for t in md["telhas"]:
        t["nome"], t["nome_c"] = "MD1", "TL18"
    for cm in md["cumeeiras"]:
        cm["nome"] = "CU1"
    c = T.corte_da_cobertura(pecas, md)
    assert c is not None and len(c["aguas"]) == 1 and abs(c["aguas"][0]["a"] - 0.2) < 0.01        # 11,3°
    assert len(c["multidobras"]) == 1 and c["cumeeira"]["perna"] == 500.0 and not c["emendas"]
    d = Desenho(nome="t", escala=50.0)
    T.desenho_do_corte_da_cobertura(c, d, 0.0, 0.0)
    textos = [str(getattr(e, "texto", "") or "") for e in _ents(d)]
    assert T.TITULO_CORTE_COBERTURA in textos
    assert "TL18 – 8050" in textos and "MD1" in textos and "CU1 (500 + 500)" in textos
    assert "1" in textos and "2" in textos                                  # os balões dos detalhes
    d2 = Desenho(nome="t", escala=50.0)
    T.desenho_do_detalhe_da_cumeeira(c, d2, 0.0, 0.0)
    cotas = [e for e in _ents(d2) if isinstance(e, Cota)]
    assert cotas and all(e.texto == "500" for e in cotas)
    assert any((e.atributos or {}).get("ampliacao") == 5.0 for e in _ents(d2))         # 1:50 ampliado = 1:10


def test_corte_da_cobertura_sem_multidobra_pela_telha_da_agua():
    """no Depósito (sem multidobra) a largura da telha, que dá o plano do corte, vinha de uma telha de FACHADA — no plano
    da tesoura — e o corte não saía; agora vem de uma telha da água"""
    c = T.corte_da_cobertura(_recorte("deposito_quimico_canto.json.gz"), {"telhas": [], "cumeeiras": []})
    assert c is not None and len(c["aguas"]) == 1 and abs(abs(c["aguas"][0]["a"]) - 0.071) < 0.005
    pecas = _recorte("deposito_quimico_cumeeira.json.gz")
    md = T.multidobras(pecas)
    c = T.corte_da_cobertura(pecas, md)
    assert len(c["aguas"]) == 2 and c["cumeeira"] and not c["multidobras"]
    assert not c["emendas"]
    # a vizinha da telha, sobreposta 70 mm na largura (o transpasse lateral): o plano corta as duas, com o mesmo comprimento —
    # não é emenda (no Depósito saíam "emendas" de 10.270 mm)
    import copy as _copy
    n = c["normal"]
    tl = next(e for e in pecas if "TELHA" in str(e.nome).upper() and e.id not in {i for cm in md["cumeeiras"] for i in cm["ids"]}
              and min(sum(v[i] * n[i] for i in range(3)) for v in e.vertices) < c["plano"] < max(sum(v[i] * n[i] for i in range(3)) for v in e.vertices))
    viz = _copy.deepcopy(tl)
    viz.id = tl.id + "-vizinha"
    m0 = min(sum(v[i] * n[i] for i in range(3)) for v in tl.vertices)
    desloc = max(c["plano"] - m0 - 35.0, 1.0)                 # a vizinha começa logo antes do plano: o corte pega as duas
    viz.vertices = [tuple(v[i] + n[i] * desloc for i in range(3)) for v in tl.vertices]
    c2 = T.corte_da_cobertura(pecas + [viz], md)
    assert not c2["emendas"], [(e["de"], e["para"], round(e["transpasse"])) for e in c2["emendas"]]


def test_corte_da_cobertura_telhas_de_fachada_externa_e_interna_sem_encavalar():
    """a platibanda do Depósito (13/11): a telha externa e a interna a 150 mm; os nomes deitados em cima de cada uma saíam um
    sobre o outro ("TL1 TL2 550 30"). Agora de pé, ao longo da telha: a de fora com o nome por fora, a de dentro por dentro"""
    def telha_de_pe(nome, x, comp):
        segs = [((x, 0.0), (x, comp)), ((x + 1.0, 0.0), (x + 1.0, comp))]
        return {"nome": nome, "segs": segs, "comp": comp, "caixa": (x, 0.0, x + 1.0, comp)}
    c = {"segs": [], "multidobras": [], "emendas": [],
         "telhas": [telha_de_pe("TL1", 0.0, 1550.0), telha_de_pe("TL2", 150.0, 830.0)],
         "aguas": [{"lado": -1.0, "a": 0.075, "b": 800.0, "x_ponta": 0.0}],
         "cumeeira": {"ponto": (10000.0, 1550.0), "perna": 500.0, "nome": "CU1"}}
    d = Desenho(nome="t", escala=75.0)
    T.desenho_do_corte_da_cobertura(c, d, 0.0, 0.0)
    nomes = {e.texto: e for e in _ents(d) if isinstance(e, Texto) and str(e.texto).startswith(("TL1", "TL2"))}
    tl1, tl2 = nomes["TL1 – 1550"], nomes["TL2 – 830"]
    assert (tl1.angulo or 0.0) == 90.0 and (tl2.angulo or 0.0) == 90.0
    # de pé a 90°, a letra fica entre (x − altura) e x da base: TL1 toda à esquerda da externa, TL2 toda à direita da interna
    x_ext = min(q[0] for e in _ents(d) if isinstance(e, Linha) for q in (e.a, e.b))
    assert tl1.posicao[0] <= x_ext + 0.01
    assert tl2.posicao[0] - tl2.altura * 75.0 >= x_ext + 150.0 - 0.01
