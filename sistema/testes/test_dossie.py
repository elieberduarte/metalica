# -*- coding: utf-8 -*-
"""O dossiê da obra (saida/dossie.py, 09/10): pavimentos pelas camadas, o papel de cada peça e os desenhos."""
from types import SimpleNamespace

from saida import dossie


def _peca(i, camada, z0, z1, x0=0.0, x1=100.0):
    vs = [(x, y, z) for x in (x0, x1) for y in (0.0, 100.0) for z in (z0, z1)]
    return SimpleNamespace(id=i, camada=camada, vertices=vs)


def test_pavimentos_pelas_camadas_e_a_repeticao_pelas_cotas():
    """o Tipo em 3 andares (faixas de cota separadas) é ×3; o duplex com o pilar de 7 m é uma faixa só"""
    pecas = [_peca("t%d" % k, "Metálica – Tipo", 10000 + 3600 * k, 10300 + 3600 * k) for k in range(3)]
    pecas += [_peca("d1", "Metálica – Duplex", 0, 7000), _peca("d2", "Metálica – Duplex", 6800, 6900)]
    varios, pavs, pav_de = dossie.pavimentos_do_modelo(pecas)
    assert varios
    por = {p["nome"]: p for p in pavs}
    assert por["Tipo"]["repete"] == 3 and por["Duplex"]["repete"] == 1
    assert [p["nome"] for p in pavs] == ["Duplex", "Tipo"]                   # na ordem de cota
    assert pav_de["t1"] == "Tipo"


def test_camadas_de_tipo_de_peca_nao_sao_pavimentos():
    """o galpão do IFC tem as camadas Vigas, Telhas, Chapas: é obra de um pavimento"""
    pecas = [_peca("a", "Vigas", 0, 100), _peca("b", "Telhas", 0, 100), _peca("c", "Chapas", 0, 100)]
    varios, pavs, _ = dossie.pavimentos_do_modelo(pecas)
    assert not varios and pavs == []


def test_secao_e_metros():
    assert dossie._secao("TQ 250x250x6,3") == "vigas_tubo" and dossie._secao("TR 250x100x9,5") == "vigas_tubo"
    assert dossie._secao("W200X26.6") == "vigas_i" and dossie._secao("U150X50X2.28") == "vigas_u"
    assert dossie._m(2195) == "2,20 m" and dossie._m(1875) == "1,88 m" and dossie._m(6848) == "6,85 m"


def test_planta_com_eixos_e_cotas_e_o_corte_com_os_pavimentos():
    geo = {"p1": {"papel": "pilares", "seg": ((0, 0, 0), (0, 0, 6000)), "z0": 0, "z1": 6000, "verts": [(0, 0, 0), (0, 0, 6000)]},
           "v1": {"papel": "vigas_tubo", "seg": ((0, 0, 6000), (8000, 0, 6000)), "z0": 6000, "z1": 6000,
                  "verts": [(0, 0, 6000), (8000, 0, 6000)]}}
    eixos = {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 8000.0}],
             "letras": [{"nome": "A", "pos": 0.0}]}
    svg = dossie.planta_svg(geo, eixos)
    assert svg.startswith("<svg") and ">1</text>" in svg and ">2</text>" in svg and ">A</text>" in svg
    assert ">8,00</text>" in svg                                              # a cota entre os eixos 1 e 2
    pavs = [{"nome": "Duplex", "faixas": [(0.0, 6000.0)], "repete": 1, "z0": 0.0, "z1": 6000.0, "cor": "#1f6feb"}]
    corte = dossie.corte_svg(geo, pavs, {"p1": "Duplex", "v1": "Duplex"})
    assert "Duplex" in corte and "+6,00" in corte


def test_trelica_sem_cobertura_e_viga_caixote():
    """sem telha nem terça de cobertura a treliça é viga caixote: nas pranchas, na lista e nos resumos (09/10)"""
    from nucleo2d.detalhe.base import TITULO_SEM_COBERTURA, obra_tem_cobertura
    from nucleo2d import pranchas
    from saida import lista_producao
    p_telha, p_terca, p_viga = (SimpleNamespace(marca=m, classe=c) for m, c in (("P1", "telha"), ("P2", "barra"), ("P3", "barra")))
    assert obra_tem_cobertura([p_telha]) and obra_tem_cobertura([p_terca], {"P2": "terca_cobertura"})
    assert not obra_tem_cobertura([p_terca, p_viga], {"P2": "terca_lateral"})
    cel = {"titulo": "T1", "item": {"categoria": "TESOURAS", "nome": "T1", "titulo_categoria": TITULO_SEM_COBERTURA}}
    assert pranchas._titulo_da_trelica([cel]) == "Vigas caixote"
    assert pranchas._conteudo_de([cel])[0].startswith("- VIGAS CAIXOTE:")
    assert pranchas._titulo_da_trelica([{"item": {"categoria": "TESOURAS", "nome": "T1"}}]) is None
    assert lista_producao._tipo_do_conjunto({"categoria": "TESOURAS", "titulo_categoria": "Vigas caixote"}) == "Viga caixote"
    assert lista_producao._tipo_do_conjunto({"categoria": "TESOURAS"}) == "Tesoura/pórtico"


def test_fotos_com_e_sem_a_lona_de_ilustracao():
    """Kaefer (19/10): com a camada Lona no modelo, o resumo pede os pares sem/com lona nos mesmos ângulos — a "com"
    pelo modo "+telhas" do editor, que mostra a camada escondida; sem lona, nenhum par a mais"""
    doc = SimpleNamespace(entidades={"a": SimpleNamespace(camada="Pilares"), "b": SimpleNamespace(camada="Lona")})
    assert dossie.tem_lona(doc)
    assert not dossie.tem_lona(SimpleNamespace(entidades={"a": SimpleNamespace(camada="Pilares")}))
    pedidos = dossie.pedidos_de_fotos({"tem_lona": True, "dir_foto": [-0.95, 1.25, 0.8]})
    nomes = [p["nome"] for p in pedidos]
    assert nomes[:5] == ["capa", "lona-1-sem", "lona-1-com", "lona-2-sem", "lona-2-com"]
    por = {p["nome"]: p for p in pedidos}
    assert por["lona-1-com"]["angulo"].endswith("+telhas") and "+telhas" not in str(por["lona-1-sem"].get("angulo", ""))
    assert por["lona-1-sem"]["dir"] == por["lona-1-com"]["dir"] == [-0.95, 1.25, 0.8]
    assert por["lona-2-com"]["dir"][:2] == [-1.35, 0.7]                       # o mesmo lado da aérea escolhida
    assert [p["nome"] for p in dossie.pedidos_de_fotos({})] == ["capa"]


def test_cobertura_retratil_fotografa_aberta_e_o_segundo_par_retraido(monkeypatch, tmp_path):
    """Kaefer (19/10): com a cobertura retrátil, tudo é fotografado com ela aberta e o segundo par da lona com ela
    retraída, no mesmo ângulo (outra carga do modelo: ?cobertura=retraida)"""
    from saida import imagens3d
    X = {"tem_lona": True, "cobertura_movel": True, "dir_foto": [0.95, -1.25, 0.8]}
    por = {p["nome"]: p for p in dossie.pedidos_de_fotos(X)}
    assert por["lona-2-sem"]["dir"] == por["lona-1-sem"]["dir"]
    lotes = []

    def falso(porta, slug, pasta, pedidos, cobertura=None, **kw):
        lotes.append((cobertura, [p["nome"] for p in pedidos]))
        return {p["nome"]: str(tmp_path / (p["nome"] + ".jpg")) for p in pedidos}
    monkeypatch.setattr(imagens3d, "fotografar", falso)
    fotos = dossie.fotografar(1, "obra", str(tmp_path / "dossie"), X)
    assert lotes == [("aberta", ["capa", "lona-1-sem", "lona-1-com"]), ("retraida", ["lona-2-sem", "lona-2-com"])]
    assert set(fotos) == {"capa", "lona-1-sem", "lona-1-com", "lona-2-sem", "lona-2-com"}
    lotes.clear()
    dossie.fotografar(1, "obra", str(tmp_path / "dossie"), {"tem_lona": True})
    assert [c for c, _ in lotes] == [None]


def test_foto_da_retraida_com_lona_so_a_da_cobertura():
    """o usuário (19/10): "pode deixar essa foto sem as lonas laterais" — a foto da cobertura retraída com a lona oculta
    a lona das paredes (a que não é lona_cobertura); a da aberta continua com todas"""
    doc = SimpleNamespace(entidades={
        "p": SimpleNamespace(id="p", camada="Pilares", atributos={}),
        "c": SimpleNamespace(id="c", camada="Lona", atributos={"elemento": "lona_cobertura"}),
        "w": SimpleNamespace(id="w", camada="Lona", atributos={"elemento": "lona"})})
    assert dossie.lona_das_paredes(doc) == ["w"]
    X = {"tem_lona": True, "cobertura_movel": True, "lona_paredes": ["w"]}
    por = {p["nome"]: p for p in dossie.pedidos_de_fotos(X)}
    assert por["lona-2-com"]["ocultar"] == ["w"] and "ocultar" not in por["lona-1-com"] and "ocultar" not in por["lona-2-sem"]


def test_linhas_do_tipo_separadas_por_perfil():
    """Kaefer (19/10): os pilares W310×32,7, W460×52,0 e TC 180×6,3 com o mesmo comprimento saíam numa linha só
    ("18 un · 7,67 m · W 310×32,7, W 460×52,0, TC 180×6,3") e pareciam do perfil errado — perfil diferente, linha diferente"""
    from nucleo3d.modelo import Barra, Documento
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    doc = Documento(nome="quadra")
    for k, perfil in enumerate(["W 460×52,0"] * 3 + ["W 310×32,7"] * 2 + ["TC 180×6,3"]):
        doc.add(Barra(nome="P%d" % (k + 1), inicio=(0.0, 5000.0 * k, 0.0), fim=(0.0, 5000.0 * k, 7674.5), perfil=perfil, papel="pilar"))
    doc.add(Barra(nome="V", inicio=(0.0, 0.0, 7843.5), fim=(0.0, 25000.0, 7843.5), perfil="W 310×44,5", papel="viga"))
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    nomes = r.get("nomes") or {}
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "q"})
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
    R = resumos.levantar_resumos(doc, lev, lista, nomes, {})
    X = dossie.levantar(doc, lev, lista, nomes, R, None)
    pil = next(b for b in X["estrutura"] if b["chave"] == "pilares")
    linhas = {tuple(li["perfis"]): li["qtd"] for li in pil["linhas"]}
    assert linhas == {("W 460×52,0",): 3, ("W 310×32,7",): 2, ("TC 180×6,3",): 1}


def test_elevacoes_e_cores_das_linhas():
    """Kaefer (19/10): o resumo da obra com a elevação lateral e a frontal (os eixos de cada direção, níveis e cotas) e
    cada linha do tipo numa cor — a mesma na foto (pedido "cores") e na tabela —, com o resto da estrutura apagado"""
    def barra(i, a, b, papel):
        vs = [a, b]
        return i, {"papel": papel, "seg": (a, b), "z0": min(a[2], b[2]), "z1": max(a[2], b[2]), "verts": vs}
    geo = dict([barra("p1", (0, 0, 0), (0, 0, 8000), "pilares"), barra("p2", (0, 38000, 0), (0, 38000, 8000), "pilares"),
                barra("p3", (17800, 0, 0), (17800, 0, 8000), "pilares"),
                barra("v1", (0, 0, 8000), (0, 38000, 8000), "vigas_i"), barra("t1", (0, 0, 9000), (17800, 0, 9000), "cliente")])
    eixos = {"eixo_g": (1.0, 0.0), "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "4", "pos": 17800.0}],
             "letras": [{"nome": "A", "pos": 0.0}, {"nome": "I", "pos": 38000.0}]}
    lat = dossie.elevacao_svg(geo, eixos, frontal=False)
    fr = dossie.elevacao_svg(geo, eixos, frontal=True)
    assert ">A<" in lat and ">I<" in lat and ">1<" not in lat and "38,00" in lat           # olhando o lado comprido
    assert ">1<" in fr and ">4<" in fr and "17,80" in fr
    assert "+8,00" in lat and "+9,00" in lat                                             # o topo do aço e o do cliente
    b = {"chave": "pilares", "cor": "#364fc7", "ids": ["p1", "p2", "p3"],
         "linhas": [{"ids": ["p1", "p2"], "cor": dossie.CORES_LINHAS[0], "marcas": ["PL1"]},
                    {"ids": ["p3"], "cor": dossie.CORES_LINHAS[1], "marcas": ["PL2"]}]}
    pedidos = dossie.pedidos_de_fotos({"estrutura": [dict(b, kg=10.0, titulo="Pilares")]})
    tipo = next(p for p in pedidos if p["nome"] == "tipo-pilares")
    assert tipo["cores"] == {dossie.CORES_LINHAS[0]: ["p1", "p2"], dossie.CORES_LINHAS[1]: ["p3"]} and tipo["fantasma"] == "claro"
    # a etiqueta de cada linha na foto (para quem só tem o PDF): a marca, na cor da linha, nas peças dela
    assert tipo["rotulos"] == [{"texto": "PL1", "cor": dossie.CORES_LINHAS[0], "ids": ["p1", "p2"], "numero": False},
                               {"texto": "PL2", "cor": dossie.CORES_LINHAS[1], "ids": ["p3"], "numero": False}]
    # com muitas linhas (as 30+ de agulhamentos da PRATI poluíam a foto), o número da linha numa bolinha
    muitas = {"chave": "x", "cor": "#000000", "linhas": [{"ids": ["i%d" % k], "cor": "#e03131", "marcas": ["A.D.%d" % k]}
                                                          for k in range(dossie.ROTULOS_COM_MARCA + 1)]}
    rot = dossie._rotulos_das_linhas(muitas)
    assert [r["texto"] for r in rot] == [str(k) for k in range(1, dossie.ROTULOS_COM_MARCA + 2)] and all(r["numero"] for r in rot)
    assert len(set(dossie.CORES_LINHAS[:4])) == 4


def test_trelica_em_pe_nao_e_tesoura():
    """PRATI (19/10): as treliças de fechamento em pé (TV, 10,2 m de altura e 0,4 × 0,9 em planta) entravam na tabela de
    tesouras com vão de 0,20 m (a espessura) e altura igual ao comprimento; agora são "Treliças verticais", uma linha por
    marca, sem vão nem flecha"""
    from nucleo3d.modelo import Barra, Documento
    from nucleo2d.detalhar import detalhar
    from nucleo2d.detalhe.base import _categoria
    from saida import lista_producao, resumos
    doc = Documento(nome="cd")
    for k, x in enumerate((0.0, 6000.0, 12000.0)):
        conj = "TV%d" % (1 if k < 2 else 2)
        alto = 10200.0 if k < 2 else 9000.0
        at = lambda pos: {"marcas": {"posicao": pos, "conjunto": conj}}
        for y, lado in ((0.0, "E"), (600.0, "D")):
            doc.add(Barra(nome="B", inicio=(x, y, 0.0), fim=(x, y, alto), perfil="U 150×50×3,00 (FF)", papel="banzo",
                          atributos=at("BZ%s%s" % (lado, conj))))
        for j in range(8):
            z0, z1 = alto * j / 8.0, alto * (j + 1) / 8.0
            doc.add(Barra(nome="D", inicio=(x, 0.0, z0), fim=(x, 600.0, z1), perfil="L 38×3 (FF)", papel="diagonal",
                          atributos=at("D%s" % conj)))
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    nomes = r.get("nomes") or {}
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "cd"})
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
    R = resumos.levantar_resumos(doc, lev, lista, nomes, {})
    assert R["tesouras"] == []
    X = dossie.levantar(doc, lev, lista, nomes, R, None)
    chaves = [b["chave"] for b in X["estrutura"]]
    assert "tesouras" not in chaves and "trelicas_v" in chaves
    tv = next(b for b in X["estrutura"] if b["chave"] == "trelicas_v")
    assert len(tv["linhas"]) == 2 and all("vao" not in li for li in tv["linhas"])     # uma linha por marca
