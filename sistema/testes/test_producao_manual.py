# -*- coding: utf-8 -*-
"""Produção feita à mão no editor 3D (onda 1, 14/10/2026): numerar, conjunto por instância e solda definida.

Projeto/ANALISES/Editor-3D/Ferramentas-que-faltam-editor-3D-2026-10-14.pdf: a peça desenhada à mão saía do detalhamento
sem marca, sem conjunto e sem solda — o editor não tinha onde escrever essas informações."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Chapa, Documento  # noqa: E402
from nucleo3d import producao  # noqa: E402

W = "W 310×38,7"


def _base(x, lado=400.0):
    """chapa de base deitada sob o pilar em (x, 0): o topo dela em z = 0"""
    return Chapa(origem=(x - lado / 2, -lado / 2, -25.0), eixo_x=(1, 0, 0), eixo_y=(0, 1, 0),
                 contorno=[(0, 0), (lado, 0), (lado, lado), (0, lado)], espessura=25.0, centrada=False)


def _pilar(x, altura=3000.0):
    return Barra(inicio=(x, 0, 0), fim=(x, 0, altura), perfil=W, papel="pilar")


def _doc(*ents):
    d = Documento()
    for e in ents:
        d.add(e)
    return d


def _aplicar(doc, r):
    """o que o editor faz com a resposta: junta os campos nos atributos (None apaga)"""
    for i, patch in r["mudancas"].items():
        e = doc.entidades[i]
        a = dict(e.atributos or {})
        for k, v in patch.items():
            if v is None:
                a.pop(k, None)
            else:
                a[k] = v
        e.atributos = a


def _pos(e):
    return e.atributos["marcas"]["posicao"]


def _conj(e):
    return e.atributos["marcas"]["conjunto"]


def test_numerar_junta_pecas_iguais_e_separa_as_diferentes():
    p1, p2, p3 = _pilar(0), _pilar(5000), _pilar(10000, 3500)
    b1, b2, b3 = _base(0), _base(5000), _base(10000)
    doc = _doc(p1, p2, p3, b1, b2, b3)
    r = producao.numerar(doc)
    _aplicar(doc, r)
    assert _pos(p1) == _pos(p2) != _pos(p3)
    assert _pos(b1) == _pos(b2) == _pos(b3)
    # peça solta: o conjunto dela mesma, um por posição
    assert _conj(p1) == _conj(p2) and _conj(p1) != _conj(b1)
    assert p1.atributos["marcas"]["perfil"] == W and b1.atributos["marcas"]["perfil"] == "CH 25"
    assert r["resumo"]["posicoes"] == 3
    # numerar de novo não muda nada
    assert producao.numerar(doc)["mudancas"] == {}


def test_peca_alterada_ganha_marca_propria_e_a_original_fica():
    p1, p2 = _pilar(0), _pilar(5000)
    doc = _doc(p1, p2)
    _aplicar(doc, producao.numerar(doc))
    antes = _pos(p1)
    p2.fim = (5000, 0, 3600)                              # o Empurrar/Puxar esticou a cópia
    p2.atributos["marca_a_conferir"] = True
    r = producao.numerar(doc)
    _aplicar(doc, r)
    assert _pos(p1) == antes and _pos(p2) != antes
    assert "marca_a_conferir" not in p2.atributos
    assert r["resumo"]["separadas"] == [[antes, _pos(p2)]]
    # a cópia esticada de volta é a mesma peça: volta à marca da original
    p2.fim = (5000, 0, 3000)
    p2.atributos["marca_a_conferir"] = True
    _aplicar(doc, producao.numerar(doc))
    assert _pos(p2) == antes


def test_peca_nova_igual_a_uma_posicao_existente_recebe_a_marca_dela():
    p1 = _pilar(0)
    doc = _doc(p1)
    _aplicar(doc, producao.numerar(doc))
    p1.atributos["marcas"]["posicao"] = "P40"           # marca que veio do IFC
    novo = _pilar(8000)
    doc.add(novo)
    _aplicar(doc, producao.numerar(doc))
    assert _pos(novo) == "P40"


def test_conjunto_por_instancia_iguais_mesma_marca():
    p1, p2, p3 = _pilar(0), _pilar(5000), _pilar(10000)
    b1, b2, b3 = _base(0), _base(5000), _base(10000, lado=500)
    doc = _doc(p1, p2, p3, b1, b2, b3)
    for i, es in (("i1", (p1, b1)), ("i2", (p2, b2)), ("i3", (p3, b3))):
        for e in es:
            e.atributos["marcas"] = {"instancia": i, "conjunto": ""}
    p1.atributos["marcas"]["principal"] = True
    _aplicar(doc, producao.numerar(doc))
    assert _conj(p1) == _conj(b1) == _conj(p2) == _conj(b2)
    assert _conj(p3) == _conj(b3) != _conj(p1)           # a base maior: outra composição
    assert p1.atributos["marcas"]["principal"] is True   # o que o editor gravou fica


def test_detalhamento_le_o_conjunto_feito_a_mao():
    from nucleo2d.detalhar import detalhar
    p1, p2 = _pilar(0), _pilar(5000)
    b1, b2 = _base(0), _base(5000)
    doc = _doc(p1, p2, b1, b2)
    for i, es in (("i1", (p1, b1)), ("i2", (p2, b2))):
        for e in es:
            e.atributos["marcas"] = {"instancia": i, "conjunto": ""}
    _aplicar(doc, producao.numerar(doc))
    r = detalhar(doc, regra_tercas=False, converter=False)
    conj = [c for c in r.get("conjuntos") or [] if _conj(p1) in c.get("marcas", [c.get("marca")])]
    assert conj and conj[0]["instancias"] == 2


def test_compactar_renumera_e_respeita_a_trava():
    p1, p2 = _pilar(0), _pilar(5000, 3300)
    doc = _doc(p1, p2)
    p1.atributos["marcas"] = {"posicao": "P17", "conjunto": "M9"}
    p2.atributos["marcas"] = {"posicao": "P30", "conjunto": "M12"}
    p1.atributos["soldas"] = {"P30": {"tipo": "filete", "perna": 5, "lados": 2, "local": "fabrica"}}
    r = producao.numerar(doc, compactar=True)
    _aplicar(doc, r)
    assert {_pos(p1), _pos(p2)} == {"P1", "P2"}
    assert {_conj(p1), _conj(p2)} == {"M1", "M2"}
    assert list(p1.atributos["soldas"]) == [_pos(p2)]      # a solda segue a marca nova da outra peça
    doc.metadados["numeracao"] = {"travada": True}
    with pytest.raises(ValueError):
        producao.numerar(doc, compactar=True)
    producao.numerar(doc)                                  # o numerar comum continua valendo


def test_contato_pilar_base_e_perfil_sobre_perfil():
    p1, b1 = _pilar(0), _base(0)
    banzo = Barra(inicio=(20000, 0, 0), fim=(23000, 0, 0), perfil=W, papel="viga")
    montante = Barra(inicio=(21500, 0, 155), fim=(21500, 0, 1155), perfil=W, papel="pilar")
    doc = _doc(p1, b1, banzo, montante)
    cs = producao.contatos(doc, [p1.id, b1.id, banzo.id, montante.id])
    pares = {frozenset((c["a"], c["b"])): c for c in cs}
    assert set(pares) == {frozenset((p1.id, b1.id)), frozenset((banzo.id, montante.id))}
    pb = pares[frozenset((p1.id, b1.id))]
    assert pb["comprimento"] > 600 and pb["perna"] > 0     # o contorno do I sobre a base
    pp = pares[frozenset((banzo.id, montante.id))]
    assert pp["cordoes"][0]["tipo"] == "contorno" and pp["comprimento"] > 600


def test_solda_definida_manda_no_detalhamento():
    from nucleo2d.detalhe.soldas import soldas_do_conjunto
    p1, b1 = _pilar(0), _base(0)
    doc = _doc(p1, b1)
    for e in (p1, b1):
        e.atributos["marcas"] = {"instancia": "i1", "conjunto": ""}
    _aplicar(doc, producao.numerar(doc))
    pecas = [producao._proxy(p1), producao._proxy(b1)]
    deduzidas = soldas_do_conjunto(pecas)
    assert deduzidas and not any(c.get("definida") for c in deduzidas)
    d = producao.normalizar_definicao({"tipo": "filete", "perna": 8, "lados": 1, "local": "fabrica",
                                       "intermitente": {"l": 50, "passo": 150}})
    p1.atributos["soldas"] = {_pos(b1): d}
    pecas = [producao._proxy(p1), producao._proxy(b1)]
    cs = soldas_do_conjunto(pecas)
    assert cs and all(c["definida"] and c["perna"] == 8.0 and c["intermitente"] == (50.0, 150.0) for c in cs)
    assert all(abs(c["comprimento"] - c["comprimento_total"] / 3.0) < 0.2 for c in cs)
    # "sem solda": a dedução sai
    p1.atributos["soldas"] = {_pos(b1): producao.normalizar_definicao({"local": "nenhuma"})}
    assert soldas_do_conjunto([producao._proxy(p1), producao._proxy(b1)]) == []


def test_solda_definida_entre_perfis_entra_no_conjunto():
    from nucleo2d.detalhe.soldas import soldas_do_conjunto, soldas_de_obra
    banzo = Barra(inicio=(0, 0, 0), fim=(3000, 0, 0), perfil=W, papel="viga")
    montante = Barra(inicio=(1500, 0, 155), fim=(1500, 0, 1155), perfil=W, papel="pilar")
    doc = _doc(banzo, montante)
    _aplicar(doc, producao.numerar(doc))
    assert soldas_do_conjunto([producao._proxy(banzo), producao._proxy(montante)]) == []   # perfil × perfil não é deduzido
    montante.atributos["soldas"] = {_pos(banzo): producao.normalizar_definicao({"tipo": "filete", "perna": 6, "lados": 1})}
    cs = soldas_do_conjunto([producao._proxy(banzo), producao._proxy(montante)])
    assert len(cs) == 1 and cs[0]["tipo"] == "contorno" and cs[0]["perna"] == 6.0
    montante.atributos["soldas"][_pos(banzo)]["local"] = "obra"
    pecas = [producao._proxy(banzo), producao._proxy(montante)]
    assert soldas_do_conjunto(pecas) == []
    obra = soldas_de_obra(pecas)
    assert len(obra) == 1 and obra[0]["quantidade"] == 1


def test_definicao_recusa_valores_sem_sentido():
    with pytest.raises(ValueError):
        producao.normalizar_definicao({"tipo": "filete", "perna": 0})
    with pytest.raises(ValueError):
        producao.normalizar_definicao({"tipo": "filete", "perna": 5, "intermitente": {"l": 200, "passo": 150}})
    with pytest.raises(ValueError):
        producao.normalizar_definicao({"tipo": "tampao", "perna": 5})


def test_prancha_do_conjunto_mostra_a_solda_definida():
    from nucleo2d.detalhar import detalhar
    p1, p2, b1, b2 = _pilar(0), _pilar(5000), _base(0), _base(5000)
    doc = _doc(p1, p2, b1, b2)
    for i, es in (("i1", (p1, b1)), ("i2", (p2, b2))):
        for e in es:
            e.atributos["marcas"] = {"instancia": i, "conjunto": ""}
    p1.atributos["marcas"]["principal"] = True
    _aplicar(doc, producao.numerar(doc))
    d = producao.normalizar_definicao({"tipo": "penetracao", "perna": 8, "lados": 1,
                                       "intermitente": {"l": 50, "passo": 150}})
    for e, o in ((p1, b1), (p2, b2)):
        e.atributos["soldas"] = {_pos(o): d}
    r = detalhar(doc, regra_tercas=False, converter=False)
    textos = [e.texto for e in r["desenhos"]["conjuntos"].entidades.values()
              if getattr(e, "camada", "") == "SOLDA" and hasattr(e, "texto")]
    assert "50-150" in textos and "8" in textos
    assert any(t.startswith("Solda de fábrica: conforme os símbolos") for t in textos)


def test_solido_feito_a_mao_vira_chapa_parametrica():
    from nucleo3d.modelo import Solido
    vs = [(0, 0, 0), (300, 0, 0), (300, 200, 0), (0, 200, 0), (0, 0, 12.5), (300, 0, 12.5), (300, 200, 12.5), (0, 200, 12.5)]
    fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    placa = Solido(vertices=vs, faces=fs, nome="placa")
    viga = _pilar(5000)
    doc = _doc(placa, viga)
    r = producao.converter_em_chapa(doc, [placa.id, viga.id])
    ch = r["chapas"][placa.id]
    assert ch["tipo"] == "chapa" and ch["espessura"] == 12.5 and len(ch["contorno"]) == 4
    assert ch["atributos"]["tipo_ifc"] == "IfcPlate"
    assert viga.id in r["recusadas"]
    assert doc.entidades[placa.id] is placa                # o modelo do servidor não muda
