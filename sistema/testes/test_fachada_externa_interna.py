# -*- coding: utf-8 -*-
"""Fachada com telha externa e interna em dois recortes, só a linha do corte na telha recortada, texto menor.

Depósito Químico (ME Sooro, 13/11/2026). O usuário viu a FACE 6 no DXF das telhas do fornecedor e pediu:
- "QUANDO TIVER SITUAÇÕES COMO ESSA COLOQUE UM RECORTE PARA MOSTRAR TELHA EXTERNA, DA FORMA QUE ESTÁ ATUALMENTE ESTÁ MUITO
  CONFUSO. SEPARAR UM RECORTE PARA AS EXTERNAS UM PARA AS INTERNAS, QUE AS INTERNAS TEM MUITO MAIS RECORTE";
- "Muita linha sem utilidade" / "preciso deixar apenas a linha onde a telha sela recortada";
- "Texto muito grande".
A platibanda tem a telha de fora (1.550) e a de dentro (recortada pela água) a 150 mm uma da outra; a face as juntava
(tolerância de 400 mm) num desenho só, uma por cima da outra. O "é assim?" com a FACE 6 foi aprovado ("Sim, é assim").

Os dados são o recorte do canto das fachadas do Depósito: testes/dados_telhas/deposito_quimico_canto.json.gz (y = 21,7
com TL1 1.550 por fora e TL3 885 por dentro; x = 0 com TL1 1.550 por fora e o oitão recortado por dentro)."""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.detalhe import telhas as T                      # noqa: E402
from nucleo2d.desenho import Cota, Desenho, Linha, Polilinha, Texto   # noqa: E402
from nucleo3d.modelo import Documento                         # noqa: E402

CANTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_telhas", "deposito_quimico_canto.json.gz")


def _faces():
    with gzip.open(CANTO, "rt", encoding="utf-8") as f:
        doc = Documento.de_dict(json.load(f))
    pecas = [e for e in doc.entidades.values() if getattr(e, "vertices", None)]
    return T.faces_de_telhas(pecas, T.multidobras(pecas))


def _ents(face, i=1):
    d = Desenho(nome="t", escala=50.0)
    T.desenho_da_paginacao(face, d, 0.0, 0.0, i)
    return list(d.entidades.values()) if isinstance(d.entidades, dict) else list(d.entidades)


def test_fachada_separada_em_externa_e_interna_com_o_mesmo_numero():
    faces = _faces()
    fach = [f for f in faces if f["tipo"] == "fachada"]
    assert sorted(f.get("lado") for f in fach) == ["externa", "externa", "interna", "interna"], [
        (f.get("lado"), len(f["chapas"])) for f in fach]
    for ext, inte in zip(fach[0::2], fach[1::2]):
        assert (ext["lado"], inte["lado"]) == ("externa", "interna")
        assert ext["numero"] == inte["numero"]
        # por fora só a telha inteira do fechamento; por dentro nenhuma dela
        assert {round(c["comprimento"]) for c in ext["chapas"]} == {1550}
        assert 1550 not in {round(c["comprimento"]) for c in inte["chapas"]}
    # a cobertura não muda, e cada fachada tem um número seu
    assert [f["numero"] for f in faces] == [1, 2, 2, 3, 3]
    assert all("_c" not in c and "_n" not in c for f in faces for c in f["chapas"])


def test_titulo_da_face_externa_e_interna():
    faces = _faces()
    titulos = [next(e.texto for e in _ents(f, i) if isinstance(e, Texto) and (e.atributos or {}).get("cabecalho") == 0)
               for i, f in enumerate(faces, 1)]
    assert titulos[0].startswith("FACE 1 – COBERTURA (")
    assert [t.split(" – ")[:2] for t in titulos[1:]] == [["FACE 2", "FACHADA EXTERNA"], ["FACE 2", "FACHADA INTERNA"],
                                                         ["FACE 3", "FACHADA EXTERNA"], ["FACE 3", "FACHADA INTERNA"]]


def test_so_a_linha_do_corte_de_borda_a_borda_da_chapa():
    faces = _faces()
    oitao = next(f for f in faces if f.get("lado") == "interna" and len({round(c["comprimento"]) for c in f["chapas"]}) > 1)
    ents = _ents(oitao)
    # nenhum contorno tracejado: só linhas soltas, as do corte
    assert not [e for e in ents if isinstance(e, Polilinha) and "OCULTA" in e.camada]
    cortes = [e for e in ents if isinstance(e, Linha) and "OCULTA" in e.camada]
    chapas = [e for e in ents if isinstance(e, Polilinha) and e.fechada and "OCULTA" not in e.camada]
    assert len(cortes) >= len(oitao["chapas"]) - 1, (len(cortes), len(oitao["chapas"]))
    for ln in cortes:
        # inclinada (a água), não a lateral nem a ponta da chapa
        assert abs(ln.a[0] - ln.b[0]) > 1.0, (ln.a, ln.b)
    # em cada chapa recortada, o corte vai de uma borda a outra da chapa de 1.050 (não das laterais de 980 do modelo)
    for c in chapas:
        xa, xb = min(v[0] for v in c.vertices), max(v[0] for v in c.vertices)
        dela = [ln for ln in cortes if xa - 0.01 <= min(ln.a[0], ln.b[0]) and max(ln.a[0], ln.b[0]) <= xb + 0.01]
        if dela:
            # cada ponta do corte numa borda da chapa ou no pé/topo dela (a água que chega ao pé da última chapa)
            ya, yb = min(v[1] for v in c.vertices), max(v[1] for v in c.vertices)
            pontas = [min((q for ln in dela for q in (ln.a, ln.b))), max((q for ln in dela for q in (ln.a, ln.b)))]
            for q, borda in zip(pontas, (xa, xb)):
                assert abs(q[0] - borda) < 0.01 or min(abs(q[1] - ya), abs(q[1] - yb)) < 0.01, (q, xa, xb, ya, yb)
    assert all(any(min(v[0] for v in c.vertices) - 0.01 <= min(ln.a[0], ln.b[0]) and max(ln.a[0], ln.b[0])
                   <= max(v[0] for v in c.vertices) + 0.01 for c in chapas) for ln in cortes)


def test_texto_das_chapas_com_1_5_mm():
    faces = _faces()
    ents = [e for f in faces[1:] for e in _ents(f)]
    marcas = {c["nome"] for f in faces[1:] for c in f["chapas"]}
    nomes = [e for e in ents if isinstance(e, Texto) and e.texto in marcas]
    cotas = [e for e in ents if isinstance(e, Cota) and (e.atributos or {}).get("chapa")]
    assert nomes and cotas
    assert {round(e.altura, 2) for e in nomes} == {1.5}
    assert {e.altura for e in cotas} == {1.5}
    assert T.TEXTO_PAGINACAO == 1.5


def test_fachadas_iguais_se_juntam_so_com_as_mesmas_telhas():
    """Com a externa e a interna separadas, a folha 14 do Depósito ia de 7 a 11 fachadas e a planta dos tipos caía a
    1:500. O usuário (13/11): "Juntar sempre as iguais", como a cobertura ("FACES 3 E 4 – FACHADA EXTERNA"). Só do mesmo
    lado e com as mesmas telhas e os mesmos comprimentos."""
    import copy
    from nucleo2d.pranchas import _chave_da_face
    faces = _faces()
    ext = next(f for f in faces if f.get("lado") == "externa")
    inte = next(f for f in faces if f.get("lado") == "interna")

    def cel(face):
        ents = _ents(face)
        tit = next(e.texto for e in ents if isinstance(e, Texto) and (e.atributos or {}).get("cabecalho") == 0)
        return tit.split(" – ", 1)[1], {"entidades": ents}
    a, b, c = cel(ext), cel(ext), cel(inte)
    assert _chave_da_face(*a) is not None and _chave_da_face(*a) == _chave_da_face(*b)
    assert _chave_da_face(*a) != _chave_da_face(*c)             # externa não se junta com interna
    # um comprimento diferente: não é a mesma fachada
    d = (b[0], {"entidades": [copy.copy(e) for e in b[1]["entidades"]]})
    cota = next(e for e in d[1]["entidades"] if isinstance(e, Cota) and (e.atributos or {}).get("chapa"))
    cota.texto = str(int(cota.texto) + 5)
    assert _chave_da_face(*d) != _chave_da_face(*a)
    # a cobertura continua pelo título; a face que não é de cobertura nem fachada não se junta
    assert _chave_da_face("COBERTURA (0°) – 34 chapas", {"entidades": []}) == "COBERTURA (0°) – 34 chapas"
    assert _chave_da_face("PLATIBANDA – 3 chapas", {"entidades": []}) is None
