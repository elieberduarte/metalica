# -*- coding: utf-8 -*-
"""Furos das faces costuradas do IFC abertos no modo ver (e no pacote do celular).

Usuário, 22/10, ME Sooro Depósito Químico (IFC do ST-DEVELOPER v12): no modo ver, os furos das terças
"sumiram" — o contorno do oblongo desenhado e a face da alma fechada por cima. O IFC grava a alma furada
como uma face só, com cada furo ligado ao contorno por uma ponte (índices repetidos na face); o *ear
clipping* direto sobre essa face se perdia quando a ponte não volta pelo mesmo caminho (a lasca da
U 200) ou o furo fica na diagonal que divide a alma (C 200), e tampava furos. Agora a face é desmontada
em contorno e furos (`geometria.lacos_da_face`) e triangulada com as pontes conferidas.

As faces de `dados_ifc/faces_costuradas_me_sooro.json` são as do arquivo do usuário, como vieram.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.geometria import area_assinada, lacos_da_face                     # noqa: E402
from saida.pacote_celular import _triangulos, gerar_3d, ler_cabecalho            # noqa: E402

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_ifc", "faces_costuradas_me_sooro.json")


def _faces():
    with open(DADOS, encoding="utf-8") as f:
        d = json.load(f)
    return [(nome, v) for nome, v in d.items() if not nome.startswith("_")]


def _cobre(P, tris, p):
    """Algum triângulo (pontos 2D) tem o ponto `p` dentro (estritamente)?"""
    def cr(o, u, w):
        return (u[0] - o[0]) * (w[1] - o[1]) - (u[1] - o[1]) * (w[0] - o[0])
    for a, b, c in tris:
        d = (cr(P[a], P[b], p), cr(P[b], P[c], p), cr(P[c], P[a], p))
        if all(x > 1e-9 for x in d) or all(x < -1e-9 for x in d):
            return True
    return False


def test_furos_da_alma_do_ifc_ficam_abertos():
    for nome, d in _faces():
        V, F, (i, j) = d["vertices"], d["face"], d["eixos"]
        P = [(v[i], v[j]) for v in V]
        tris = _triangulos(V, F)
        tampados = [h for h in d["furos"] if _cobre(P, tris, h)]
        assert not tampados, (nome, "furos tampados", tampados)
        # e a alma inteira continua lá: a área dos triângulos é a da face (menos os furos), sem sobra
        area = sum(abs(area_assinada([P[a], P[b], P[c]])) for a, b, c in tris)
        face = abs(area_assinada([P[k] for k in F]))
        assert abs(area - face) <= 1e-3 * face, (nome, area, face)


def test_lacos_da_face_costurada():
    for nome, d in _faces():
        lacos = lacos_da_face(d["face"])
        assert len(lacos) >= len(d["furos"]) + 1, (nome, len(lacos))
    # o quadrado com um furo quadrado e a ponte 0→4: dois laços, o contorno e o furo
    face = [0, 4, 5, 6, 7, 4, 0, 1, 2, 3]
    assert sorted(len(l) for l in lacos_da_face(face)) == [4, 4]


def test_modo_ver_leva_o_furo_aberto():
    """O .mcel do modo ver (gerar_3d): a alma da U 200 como peça, vista no arquivo — nenhum triângulo no plano dela
    por cima dos furos (a forma de modelo em que apareceu: IFC importado, longe da origem)."""
    nome, d = _faces()[0]
    V, F, (i, j) = d["vertices"], d["face"], d["eixos"]
    eixo = 3 - i - j
    desloc = [137526.0, 72917.0, 6427.0]                    # o IFC do Sooro: a 137 m da origem
    base = [[v[0] + desloc[0], v[1] + desloc[1], v[2] + desloc[2]] for v in V]
    costas = [list(p) for p in base]
    for p in costas:
        p[eixo] -= 2.25                                     # a outra face da alma, 2,25 mm atrás
    n = len(base)
    ent = {"id": "u200", "tipo": "solido", "nome": "U200X50X2.25", "camada": "Vigas", "material": "",
           "vertices": base + costas, "faces": [F, [k + n for k in reversed(F)]],
           "atributos": {"marcas": {"perfil": "U200X50X2.25", "posicao": "M1"}}}
    modelo = {"nome": "sooro", "unidade": "mm", "entidades": [ent],
              "camadas": {"Vigas": {"nome": "Vigas", "cor": "#0b3d91", "visivel": True}}, "materiais": {}}
    binario, _fichas, _num = gerar_3d(modelo)
    cab = ler_cabecalho(binario)
    o = cab["origem"]
    (b,) = cab["blocos"]
    q = struct.unpack_from("<%dH" % (b["vertices"]["n"] * 4), binario, b["vertices"]["ofs"])
    pts = [tuple(b["min"][k] + q[4 * m + k] * b["esc"][k] + o[k] for k in range(3)) for m in range(b["vertices"]["n"])]
    idx = struct.unpack_from("<%d%s" % (b["indices"]["n"], "H" if b["indices"]["tipo"] == "u16" else "I"),
                             binario, b["indices"]["ofs"])
    plano = base[F[0]][eixo]
    tris = [tuple(idx[k:k + 3]) for k in range(0, len(idx), 3)]
    na_face = [t for t in tris if all(abs(pts[m][eixo] - plano) < 0.5 for m in t)]
    assert na_face
    P = [(p[i], p[j]) for p in pts]
    furos = [(h[0] + desloc[i], h[1] + desloc[j]) for h in d["furos"]]
    tampados = [h for h in furos if _cobre(P, na_face, h)]
    assert not tampados, ("furos tampados no modo ver", tampados)
