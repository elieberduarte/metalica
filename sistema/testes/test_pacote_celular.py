# -*- coding: utf-8 -*-
"""O 3D leve e o pacote do projeto para o celular (saida/pacote_celular.py).

O binário tem de devolver a geometria do modelo: cada vértice, desfeita a quantização (no
bloco, pela caixa; na cópia, pela matriz), cai a menos de meio passo de onde estava. As cópias
são as do editor (mesma malha só movida ou girada). O pacote só leva a lista fechada de
arquivos: a pasta comercial nunca vai para o celular."""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida.pacote_celular import gerar_3d, gerar_pacote, ler_cabecalho, MAX_VERTS_BLOCO   # noqa: E402


def _caixa_solido(id_, x, y, z, a=100.0, b=50.0, c=8.0, camada="Chapas", girar=0.0):
    """Paralelepípedo a×b×c com o canto em (x, y, z), girado `girar` graus em torno de z."""
    cs, sn = math.cos(math.radians(girar)), math.sin(math.radians(girar))
    base = [(0, 0, 0), (a, 0, 0), (a, b, 0), (0, b, 0), (0, 0, c), (a, 0, c), (a, b, c), (0, b, c)]
    vs = [[x + p[0] * cs - p[1] * sn, y + p[0] * sn + p[1] * cs, z + p[2]] for p in base]
    fs = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return {"id": id_, "tipo": "solido", "nome": id_, "camada": camada, "material": "Aço", "vertices": vs, "faces": fs,
            "atributos": {"marcas": {"perfil": "PL", "posicao": "P1"}}}


def _cilindro(id_, x, y, lados=40, r=8.0, h=30.0):
    vs, fs = [], []
    for k in range(lados):
        t = 2 * math.pi * k / lados
        vs.append([x + r * math.cos(t), y + r * math.sin(t), 0.0])
    for k in range(lados):
        t = 2 * math.pi * k / lados
        vs.append([x + r * math.cos(t), y + r * math.sin(t), h])
    fs.append(list(range(lados - 1, -1, -1)))
    fs.append(list(range(lados, 2 * lados)))
    for k in range(lados):
        j = (k + 1) % lados
        fs.append([k, j, j + lados, k + lados])
    return {"id": id_, "tipo": "solido", "nome": "BOLT", "camada": "Parafusos", "material": "Aço", "vertices": vs, "faces": fs}


def _modelo():
    ents = [_caixa_solido("c%d" % i, 1000.0 * i, 0.0, 0.0, a=100 + i) for i in range(5)]       # todas diferentes
    # 60 parafusos iguais, girados de vários jeitos: viram cópias (78 triângulos × 59 > 2000)
    for i in range(60):
        e = _cilindro("p%d" % i, 200.0 * i, 3000.0)
        ang = math.radians(7 * i)
        c, s = math.cos(ang), math.sin(ang)
        cx, cy = 200.0 * i, 3000.0
        e["vertices"] = [[cx + (v[0] - cx) * c - (v[2]) * s, v[1], (v[0] - cx) * s + v[2] * c + 500] for v in e["vertices"]]
        ents.append(e)
    ents.append({"id": "b1", "tipo": "barra", "nome": "viga", "camada": "Vigas", "material": "Aço",
                 "inicio": [0, -2000, 0], "fim": [6000, -2000, 0], "perfil": "W 200×22,5", "rotacao": 0.0})
    ents.append({"id": "h1", "tipo": "chapa", "nome": "chapa de base", "camada": "Chapas", "material": "Aço",
                 "origem": [0, 0, 1000], "eixo_x": [1, 0, 0], "eixo_y": [0, 1, 0], "contorno": [[0, 0], [300, 0], [300, 300], [0, 300]],
                 "espessura": 12.5, "centrada": False, "furos": [{"x": 150, "y": 150, "diametro": 22}]})
    ents.append({"id": "t1", "tipo": "solido", "nome": "cota", "camada": "Chapas", "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                 "faces": [[0, 1, 2]], "atributos": {"tipo": "cota"}})
    camadas = {n: {"nome": n, "cor": "#888888", "visivel": n != "Parafusos"} for n in ("Chapas", "Parafusos", "Vigas")}
    return {"nome": "teste", "unidade": "mm", "entidades": ents, "camadas": camadas, "materiais": {"Aço": {"nome": "Aço", "cor": "#8a94a6"}}}


def _vertices_de(binario, cab):
    """Todos os vértices do arquivo, de volta em mm (relativos à origem), por número de peça."""
    por_peca = {}
    for b in cab["blocos"]:
        v = struct.unpack_from("<%dH" % (b["vertices"]["n"] * 4), binario, b["vertices"]["ofs"])
        for k in range(b["vertices"]["n"]):
            q = v[4 * k:4 * k + 4]
            p = tuple(b["min"][i] + q[i] * b["esc"][i] for i in range(3))
            por_peca.setdefault(b["id0"] + q[3], []).append(p)
    for f in cab["formas"]:
        v = struct.unpack_from("<%dH" % (f["vertices"]["n"] * 4), binario, f["vertices"]["ofs"])
        inst = struct.unpack_from("<%df" % (f["copias"]["n"] * 13), binario, f["copias"]["ofs"])
        for c in range(f["copias"]["n"]):
            m = inst[13 * c:13 * c + 13]
            pts = []
            for k in range(f["vertices"]["n"]):
                x, y, z = v[4 * k:4 * k + 3]
                pts.append((m[0] * x + m[1] * y + m[2] * z + m[3], m[4] * x + m[5] * y + m[6] * z + m[7],
                            m[8] * x + m[9] * y + m[10] * z + m[11]))
            por_peca[int(m[12])] = pts
    return por_peca


def test_cabecalho_e_trechos_dentro_do_arquivo():
    binario, fichas, num = gerar_3d(_modelo())
    cab = ler_cabecalho(binario)
    assert binario[:4] == b"MCEL" and cab["versao"] == 1
    assert num["pecas"] == len(fichas["pecas"]) == 5 + 60 + 2          # a cota fica de fora
    for item in cab["blocos"] + cab["formas"]:
        for chave in ("vertices", "indices", "arestas", "copias"):
            if chave in item:
                assert item[chave]["ofs"] % 4 == 0
                assert item[chave]["ofs"] < len(binario)
    for b in cab["blocos"]:
        assert b["vertices"]["n"] <= MAX_VERTS_BLOCO
        idx = struct.unpack_from("<%dH" % b["indices"]["n"], binario, b["indices"]["ofs"])
        assert max(idx) < b["vertices"]["n"] and len(idx) % 3 == 0
    # os parafusos viraram uma forma só, com as 60 cópias
    assert num["formas"] == 1 and num["copias"] == 60


def test_vertices_voltam_ao_lugar():
    m = _modelo()
    binario, fichas, _num = gerar_3d(m)
    cab = ler_cabecalho(binario)
    o = cab["origem"]
    por_peca = _vertices_de(binario, cab)
    por_id = {e["id"]: e for e in m["entidades"]}
    for i, f in enumerate(fichas["pecas"]):
        e = por_id[f["id"]]
        if e["tipo"] != "solido":
            continue
        orig = [(v[0] - o[0], v[1] - o[1], v[2] - o[2]) for v in e["vertices"]]
        volta = por_peca[i]
        assert len(volta) == len(orig)
        erro = max(math.dist(a, b) for a, b in zip(orig, volta))
        assert erro < 0.5, (f["id"], erro)            # meio milímetro: a quantização de 16 bits na caixa


def test_fichas_camadas_e_peso():
    binario, fichas, _num = gerar_3d(_modelo())
    cab = ler_cabecalho(binario)
    nomes = [c["nome"] for c in cab["camadas"]]
    vis = {c["nome"]: c["visivel"] for c in cab["camadas"]}
    assert vis["Parafusos"] is False and vis["Vigas"] is True
    viga = next(f for f in fichas["pecas"] if f["id"] == "b1")
    assert nomes[viga["c"]] == "Vigas" and viga["p"] == "W 200×22,5"
    assert 120 < viga["kg"] < 150                     # W200×22,5 × 6 m ≈ 135 kg
    chapa = next(f for f in fichas["pecas"] if f["id"] == "h1")
    assert 8.0 < chapa["kg"] < 9.0                    # 300×300×12,5 com furo de 22 ≈ 8,8 kg
    assert next(f for f in fichas["pecas"] if f["id"] == "c0")["pos"] == "P1"
    for c in cab["camadas"]:
        if c["pecas"]:
            assert len(c["caixa"]) == 2


def test_pacote_lista_fechada_sem_comercial(tmp_path):
    proj = tmp_path / "obra"
    (proj / "detalhamento").mkdir(parents=True)
    (proj / "comercial").mkdir()
    (proj / "comercial" / "Proposta.pdf").write_bytes(b"%PDF-1.4 proposta")
    (proj / "detalhamento" / "resumo-da-obra.pdf").write_bytes(b"%PDF-1.4 resumo")
    (proj / "projeto.json").write_text(json.dumps({"nome": "Obra Teste", "dados_resumo": {"revisao": "R02"}}), encoding="utf-8")
    (proj / "modelo.json").write_text(json.dumps(_modelo()), encoding="utf-8")
    (proj / "detalhamento" / "lista-de-materiais.json").write_text(json.dumps({
        "gerado": "2026-10-05 18:00", "totais": {"peso": 1234.5, "pecas": 10, "posicoes": 3, "conjuntos": 1},
        "posicoes": [{"marca": "P1", "perfil": "PL", "quantidade": 2, "peso": 1.0, "peso_total": 2.0, "custo": 99}],
        "perfis": [], "chapas": [], "telhas": [], "conjuntos": [], "acessorios": []}), encoding="utf-8")
    dest = tmp_path / "pacote"
    m = gerar_pacote(str(proj), str(dest), "obra")
    nomes = sorted(a["nome"] for a in m["arquivos"])
    assert nomes == ["modelo3d.mcel", "pecas.json", "quantitativos.json", "resumo-da-obra.pdf"]
    assert not any("ropost" in n or "comercial" in n for n in os.listdir(dest))
    assert m["formato"] == 1 and m["projeto"]["revisao"] == "R02" and m["numeros"]["pecas"] == 67
    q = json.loads((dest / "quantitativos.json").read_text(encoding="utf-8"))
    assert "custo" not in q["posicoes"][0]           # só os campos da lista fechada
    # refazer sem mudar o modelo não regrava o 3D (o pacote acompanha o modelo, não o relógio)
    antes = os.path.getmtime(dest / "modelo3d.mcel")
    gerar_pacote(str(proj), str(dest), "obra")
    assert os.path.getmtime(dest / "modelo3d.mcel") == antes
