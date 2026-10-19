# -*- coding: utf-8 -*-
"""Resumo da obra / de materiais: as regras que não dependem de um modelo inteiro — terça de
parede pela orientação da seção, porca/arruela solta pela geometria, descrição comercial
do parafuso e o HTML dos dois documentos a partir de um levantamento mínimo."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                                   # noqa: E402
from nucleo2d.detalhe.base import _parede_da_peca                    # noqa: E402
from saida import resumos                                           # noqa: E402


def _caixa(L, H, B, eixo="x", alma="z", origem=(0.0, 0.0, 0.0)):
    """Caixa L (ao longo de `eixo`) × H (ao longo de `alma`) × B, como a envolvente de um
    perfil U: a alma é a direção de H."""
    pts = []
    for a in (0.0, L):
        for h in (0.0, H):
            for b in (0.0, B):
                p = {"x": 0.0, "y": 0.0, "z": 0.0}
                p[eixo] = a
                p[alma] = h
                resto = ({"x", "y", "z"} - {eixo, alma}).pop()
                p[resto] = b
                pts.append((origem[0] + p["x"], origem[1] + p["y"], origem[2] + p["z"]))
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return Solido(nome="c", vertices=pts, faces=faces)


def test_terca_de_parede_pela_orientacao_da_secao():
    galpao = (1.0, 0.0, 0.0)
    lim = (0.0, 40000.0)
    # alma de pé (H vertical): terça de cobertura, seja qual for a altura
    assert _parede_da_peca(_caixa(6000, 150, 75, "x", "z", (10000, 0, 6100)), galpao, lim) is None
    # alma deitada, correndo ao longo do galpão: lateral; atravessada: oitão
    assert _parede_da_peca(_caixa(6000, 150, 75, "x", "y", (10000, 0, 6100)), galpao, lim) == "lateral"
    assert _parede_da_peca(_caixa(6000, 150, 75, "y", "x", (10000, 0, 6100)), galpao, lim) == "oitao"
    # seção quadrada deitada (cantoneira) não diz nada
    assert _parede_da_peca(_caixa(1500, 32, 32, "x", "y", (10000, 0, 7000)), galpao, lim) is None
    # agulhamento em pé: de parede; de oitão quando está na ponta do galpão
    assert _parede_da_peca(_caixa(500, 32, 32, "z", "x", (20000, 0, 6100)), galpao, lim) == "lateral"
    assert _parede_da_peca(_caixa(500, 32, 32, "z", "x", (500, 0, 6100)), galpao, lim) == "oitao"


def test_porca_e_arruela_soltas_pela_geometria():
    # medidas reais do IFC do TecnoMETAL (as três extensões principais, mm)
    assert resumos._fixador_solto([16, 16, 12]) == ('Porca 3/8"', 9.5, False)
    assert resumos._fixador_solto([21, 21, 2]) == ('Arruela 3/8"', 9.5, True)
    assert resumos._fixador_solto([37, 35, 24]) == ('Porca 3/4"', 19.1, False)
    assert resumos._fixador_solto([34, 34, 3]) == ('Arruela 5/8"', 15.9, True)
    assert resumos._fixador_solto([38, 38, 4]) == ('Arruela 3/4"', 19.1, True)
    assert resumos._fixador_solto([31, 29, 19]) == ('Porca 5/8"', 15.9, False)


def test_descricao_comercial_do_parafuso():
    nome, desc, d = resumos.descricao_parafuso("M12x35")
    assert nome == "Parafuso M12x35" and d == 12
    assert 'Ø1/2" x 1.1/2"' in desc and "A307" in desc
    nome, desc, d = resumos.descricao_parafuso("M16x50")
    assert "A325" in desc and 'Ø5/8" x 2"' in desc


def test_html_dos_resumos_com_levantamento_minimo():
    R = {
        "projeto": {"nome": "OBRA X", "origem_ifc": "x.R03"},
        "dados": {"revisao": "R03", "descricao": "Cobertura", "telha": "Telha TP40 #0,50", "data": "25/09/2026"},
        "numeros": {"tesouras": 2, "peso_aco": 1000.0, "ml_telhas": 100.0, "peso_telhas": 500.0, "total": 1500.0,
                    "parafusos": 40, "inclinacao": math.degrees(math.atan(0.2)), "kg_m2": 10.0},
        "dimensoes": {"eixos": "A B", "comprimento_total": 6000.0, "n_tesouras": 2, "nivel_apoio": 6613.0, "apoio_por_chapa": True,
                      "trechos": [{"nome": "Galpão", "eixos": "A a B", "vao": 12300.0, "comprimento": 6000.0, "projecao": (8000.0, 14000.0)}],
                      "projecao": (8000.0, 14000.0), "area_m2": 112.0},
        "tesouras": [{"tipo": "T1", "qtd": 2, "eixos": "A, B", "vao": 12300.0, "comprimento": 14700.0, "flecha": 1230.0, "altura": 2117.0,
                      "banzos": "U100X50X#11", "trelicamento": "U92X40X#13", "kg_un": 300.0, "kg_total": 600.0,
                      "membros": {"T1": 2}, "meias": 2, "composicao": {}, "marcas": ["M1"]}],
        "tercas": {"contagem": {k: {"pecas": 0, "tipos": 0} for k in ("cob", "lat", "oit", "marq")},
                   "linhas": [], "perfil_principal": "C150X75X20X#13", "furos": "OBL 25x13"},
        "grupos_peso": [{"grupo": "Tesouras", "kg": 600.0, "pct": 60.0}, {"grupo": "Terças e longarinas", "kg": 400.0, "pct": 40.0}],
        "telhas": {"descricao": "Telha TP40 #0,50", "itens": [], "trechos": {"cobertura": [
            {"codigo_n": "TL1", "codigo": "TL", "qtd": 10, "comprimento": 10000.0, "ml": 100.0, "kg": 500.0, "cortada": False, "perfil": "TP40"}]},
                   "ml_total": 100.0, "kg_total": 500.0, "ml_por_trecho": {"cobertura": 100.0}, "largura_util": 980.0},
        "parafusos": [{"nome": "Parafuso M12x35", "descricao": "Parafuso sextavado", "qtd": 40, "parafuso": True, "d": 12,
                       "locais": [{"local": "terça de cobertura (T.C.) x tesoura", "qtd": 40, "pecas": ["T.C.1", "T1"]}]}],
        "familias": [{"chave": "tesouras", "titulo": "Tesouras", "n": 2, "composicao": "T1 4x", "perfis": [], "kg": 600.0,
                      "sub": [{"titulo": "T1 (02x) - eixos A, B", "perfis": [{"perfil": "U100X50X#11", "kg": 600.0, "m": 100.0, "pecas": 4}]}]}],
        "chaparia": [{"rotulo": "#1/4\" (6,35 mm)", "kg": 20.0, "pecas": 4, "m2": 0.4}], "chaparia_total": {"kg": 20.0, "pecas": 4},
        "perfis_kg": 980.0, "avisos": ["conjuntos M1, M2 têm a mesma geometria", "2 posição(ões) sem peso teórico"],
    }
    obra = resumos.html_resumo_obra(R)
    assert "RESUMO DA OBRA" in obra and "2 meias-tesouras" in obra and "12,30 m" in obra and "+6,613 m" in obra
    assert "inclinação 20% (11,3°)" in obra
    assert "sem peso teórico" in obra and "mesma geometria" not in obra          # só o aviso que muda número
    materiais = resumos.html_resumo_materiais(R)
    assert "RESUMO DE MATERIAIS" in materiais and "U100X50X#11" in materiais and "Parafuso M12x35" in materiais
    # a versão paginada leva o Paged.js e o sinal de fim de paginação da impressão
    paginado = resumos.html_resumo_obra(R, paginado=True)
    assert "paged.polyfill.js" in paginado and "data-paged" in paginado
    # a identidade da proposta comercial (08/10): a faixa escura, os cartões de números; com a marca, o logo e as cores dela
    assert "faixa-topo" in obra and 'class="ficha"' in obra and "--dest: #C3D773" in obra
    R["marca"] = {"cores": {"primaria": "#112233", "escura": "#000000", "destaque": "#abcdef"}, "logo": "data:image/png;base64,AAAA",
                  "logo_claro": "", "nome": "Fábrica", "slogan": "juntos", "site": "x.com"}
    com = resumos.html_resumo_materiais(R, paginado=True)
    assert "--pri: #112233" in com and "data:image/png;base64,AAAA" in com and "juntos" in com and "documento interno" in com


def test_marca_da_empresa_sem_o_modulo_comercial(tmp_path):
    """os resumos vão no instalado e o comercial não: a marca é lida direto de fabrica/ (08/10)"""
    import json
    from saida import identidade
    assert identidade.ler_marca(str(tmp_path))["cores"] == identidade.CORES_PADRAO       # sem empresa: o padrão, sem logo
    assert identidade.ler_marca(str(tmp_path))["logo"] == ""
    (tmp_path / "fabrica" / "marca").mkdir(parents=True)
    (tmp_path / "fabrica" / "empresa.json").write_text(json.dumps({"nome_comercial": "Hermes", "cores": {"destaque": "#00ff00"}}), encoding="utf-8")
    (tmp_path / "fabrica" / "marca" / "logo.png").write_bytes(b"PNG-de-teste")
    m = identidade.ler_marca(str(tmp_path))
    assert m["nome"] == "Hermes" and m["cores"]["destaque"] == "#00ff00" and m["cores"]["primaria"] == "#35434C"
    assert m["logo"].startswith("data:image/png;base64,") and m["logo_claro"] == m["logo"]     # sem o claro, o normal


def test_descricao_da_telha_pelo_perfil_dela():
    """a multi-dobra de 0,65 saía com a descrição da obra (0,50); o "Telha TELHA" repetido sai (05/10)"""
    assert resumos.descricao_telha("TELHA TP40 0.65MM", "Telha TELHA TP40 0.50MM") == "Telha TP40 0,65 mm"
    assert resumos.descricao_telha("TELHA TP40 0.50MM", "Telha TELHA TP40 0.50MM") == "Telha TP40 0,50 mm"
    assert resumos.descricao_telha("TELHA TP40 0.50MM", "") == "Telha TP40 0,50 mm"
    # "ESP.0.65" sem o MM (depósito da SOORO, 09/10): a cobertura de 0,65 não entra na compra como a de 0,50 dos dados
    assert resumos.descricao_telha("TELHA TP40 ESP.0.65", "TELHA TP40 ESP.0.50") == "Telha TP40 0,65 mm"


def test_compra_chapas_comerciais_porcas_e_arruelas():
    """chapa de 1,20 x 3,00 pela área com a perda; cada parafuso com 1 porca e 1 arruela, as soltas somadas (05/10)"""
    lista = {"perfis": [], "chapas": [{"espessura": 3.0, "pecas": 10, "area_m2": 10.0, "peso": 235.5}]}
    pf = [{"nome": "Parafuso M12x35", "descricao": "Parafuso sextavado Ø1/2\" + porca e arruela", "qtd": 10, "parafuso": True, "d": 12},
          {"nome": "Porca 1/2\"", "descricao": "", "qtd": 4, "parafuso": False, "d": 12.7},
          {"nome": "Arruela 5/8\"", "descricao": "", "qtd": 6, "parafuso": False, "d": 15.9}]
    C = resumos._compra(lista, pf, {"itens": []}, {})
    assert C["chapas"][0]["chapas"] == 4                       # 10 m² × 1,15 / 3,6 m² = 3,2 → 4
    assert dict(C["porcas"]) == {'1/2"': 14} and dict(C["arruelas"]) == {'1/2"': 10, '5/8"': 6}
    assert resumos._compra(lista, pf, {"itens": []}, {"perda_chapas": "0"})["chapas"][0]["chapas"] == 3


def test_barra_comercial_pelo_perfil():
    """W em 12 m; os outros em 6 m (05/10), e o dobrado maior que 6 m sob medida (13/10)"""
    from saida.lista_producao import _barra_para
    assert _barra_para([3640.0], 0, "W150X13.00") == 12000.0
    assert _barra_para([5000.0], 0, "U100X50X#11") == 6000.0
    assert _barra_para([6290.0], 0, "U150X50X#13") == 6000.0


def test_pendencia_com_chave_estavel_e_resposta_no_resumo():
    """A aba Conferência (13/10): cada pendência leva uma chave que não muda quando o número dela muda (12 de 14 peças →
    13 de 14), e a resposta do usuário entra no resumo da obra como coluna, com a resolvida fora da conta."""
    a = resumos.chave_da_pendencia({"peca": "T.C.4", "o_que": "furo(s) pelo parafuso colocado no 3D em 12 de 14 peças desta posição"})
    b = resumos.chave_da_pendencia({"peca": "T.C.4", "o_que": "furo(s) pelo parafuso colocado no 3D em 13 de 14 peças desta posição"})
    c = resumos.chave_da_pendencia({"peca": "T.C.5", "o_que": "furo(s) pelo parafuso colocado no 3D em 12 de 14 peças desta posição"})
    assert a == b and a != c and len(a) == 10
    R = {"projeto": {"nome": "OBRA"}, "dados": {}, "numeros": {"tesouras": 0, "peso_aco": 0.0, "ml_telhas": 0.0, "peso_telhas": 0.0, "total": 0.0,
                                                               "parafusos": 0, "inclinacao": 0.0, "kg_m2": None},
         "dimensoes": {"eixos": "", "comprimento_total": 0.0, "n_tesouras": 0, "nivel_apoio": 0.0, "apoio_por_chapa": False, "trechos": [],
                       "projecao": (0.0, 0.0), "area_m2": 0.0},
         "tesouras": [], "tercas": {"contagem": {k: {"pecas": 0, "tipos": 0} for k in ("cob", "lat", "oit", "marq")}, "linhas": [],
                                    "perfil_principal": "", "furos": ""},
         "grupos_peso": [], "telhas": {"descricao": "", "itens": [], "trechos": {}, "ml_total": 0.0, "kg_total": 0.0, "ml_por_trecho": {}, "largura_util": 980.0},
         "parafusos": [], "familias": [], "chaparia": [], "chaparia_total": {"kg": 0.0, "pecas": 0}, "perfis_kg": 0.0, "avisos": [],
         "pendencias": [{"peca": "CH7", "perfil": "PLATE 125x110x3", "o_que": "dimensões medidas diferem do nome: conferir", "chave": "k1", "ids": ["g1"]},
                        {"peca": "F.T.1", "perfil": "U68X30", "o_que": "a peça sai 504 mm do plano: conferir", "chave": "k2"}]}
    sem = resumos.html_resumo_obra(R)
    assert "2 a conferir" in sem and "Resposta" not in sem.split("Pendências de conferência")[1]
    R["conferencias"] = {"k1": {"situacao": "resolvida", "resposta": "Medida da chapa confirmada no projeto: 215 x 110.", "quando": "2026-10-13T09:00:00"}}
    com = resumos.html_resumo_obra(R)
    bloco = com.split("Pendências de conferência")[1]
    assert "1 a conferir" in bloco and "1 resolvida(s)" in bloco and "Resposta" in bloco
    assert "215 x 110" in bloco and "resolvida · 2026-10-13 09:00" in bloco and 'class="resolvida" data-ids="g1"' in bloco


def test_linha_do_parafuso_na_compra_leva_os_ids_para_ver_no_3d():
    """a linha do parafuso na compra traz os ids dele (data-ids): na tela, o clique mostra onde estão no 3D — "onde vão
    esses 6 parafusos? pode colocar um link para ver no 3D" (14/10); porcas e arruelas soltas, sem"""
    lista = {"perfis": [], "chapas": []}
    pf = [{"nome": "Parafuso M12x35", "descricao": "Parafuso sextavado Ø1/2\" + porca e arruela", "qtd": 3, "parafuso": True, "d": 12,
           "locais": [{"local": "terça x banzo", "qtd": 2, "ids": ["a1", "a2"]}, {"local": "chapa", "qtd": 1, "ids": ["a3"]}]}]
    C = resumos._compra(lista, pf, {"itens": []}, {})
    assert C["parafusos"][0]["ids"] == ["a1", "a2", "a3"]
    h = resumos._html_compra({"compra": C})
    assert 'data-ids="a1,a2,a3"' in h
    assert h.count("data-ids=") == 1                          # a porca e a arruela não levam


def test_resumo_da_obra_com_as_fotos_sem_e_com_a_lona(tmp_path):
    """Kaefer (19/10): os pares de fotos sem/com lona entram lado a lado depois dos números; sem as fotos, nada"""
    fotos = {}
    for k in (1, 2):
        for q in ("sem", "com"):
            cam = tmp_path / ("lona-%d-%s.jpg" % (k, q))
            cam.write_bytes(b"\xff\xd8\xff\xd9")
            fotos["lona-%d-%s" % (k, q)] = str(cam)
    R = {"projeto": {"nome": "QUADRA"}, "dados": {}, "dimensoes": {}, "numeros": {"peso_aco": 1000.0, "parafusos": 0},
         "grupos_peso": [], "tesouras": [], "parafusos": [], "familias": [], "chaparia": [], "avisos": [],
         "dossie": {"fotos": fotos}}
    obra = resumos.html_resumo_obra(R)
    assert obra.count("Sem a lona") == 2 and obra.count("Com a lona") == 2 and 'class="com-lona"' in obra
    R["dossie"]["fotos"] = {}
    assert 'class="com-lona"' not in resumos.html_resumo_obra(R)


def test_resumo_da_obra_com_a_cobertura_retratil_aberta_e_retraida(tmp_path):
    """Kaefer (19/10): a implantação aberta e retraída lado a lado e as legendas das fotos pela situação"""
    fotos = {}
    for k in (1, 2):
        for q in ("sem", "com"):
            cam = tmp_path / ("lona-%d-%s.jpg" % (k, q))
            cam.write_bytes(b"\xff\xd8\xff\xd9")
            fotos["lona-%d-%s" % (k, q)] = str(cam)
    R = {"projeto": {"nome": "QUADRA"}, "dados": {}, "dimensoes": {}, "numeros": {"peso_aco": 1000.0, "parafusos": 0},
         "grupos_peso": [], "tesouras": [], "parafusos": [], "familias": [], "chaparia": [], "avisos": [],
         "dossie": {"fotos": fotos, "cobertura_movel": True, "legenda": [],
                    "svg": {"implantacao": "<svg id='a'></svg>", "implantacao_retraida": "<svg id='r'></svg>"}}}
    obra = resumos.html_resumo_obra(R)
    assert 'class="lado-movel"' in obra and "<svg id='r'>" in obra
    assert "Cobertura retraída · sem a lona" in obra and "Cobertura aberta · com a lona" in obra


def test_a_capa_mostra_a_foto_inteira():
    """Kaefer (19/10): a foto da capa (3:2) num quadro baixo com object-fit: cover cortava a estrutura"""
    import re
    css = re.search(r"\.capa img \{([^}]*)\}", resumos.html_resumo_obra({"projeto": {"nome": "X"}, "dados": {}, "dimensoes": {},
        "numeros": {"peso_aco": 1.0, "parafusos": 0}, "grupos_peso": [], "tesouras": [], "parafusos": [], "familias": [],
        "chaparia": [], "avisos": []}))
    assert css and "object-fit: contain" in css.group(1)


def test_tipo_de_8_linhas_vai_ao_lado_da_foto(tmp_path):
    """Kaefer (19/10): os contraventamentos (8 linhas) saíam com a foto grande em cima e o bloco não cabia no fim da
    folha — ia inteiro para a próxima e deixava meia folha em branco; até 12 linhas, a tabela vai ao lado da foto"""
    cam = tmp_path / "tipo-contrav.jpg"
    cam.write_bytes(b"\xff\xd8\xff\xd9")
    R = {"dossie": {"fotos": {"tipo-contrav": str(cam)}}}
    linhas = [{"comprimento": 7000.0 - 100 * k, "qtd": 4, "kg": 10.0, "marcas": ["CV.%d" % k], "perfis": ["Barra redonda ø 8 mm"],
               "onde": [], "ids": []} for k in range(8)]
    b = {"chave": "contrav", "titulo": "Contraventamentos", "cor": "#e03131", "ids": [], "qtd": 32, "m": 200.0, "kg": 80.0,
         "linhas": linhas}
    assert 'class="bloco-tipo lado"' in resumos._bloco_tipo(R, b, False)

