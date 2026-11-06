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
    assert obra.count("Sem a lona") == 2 and obra.count("Com a lona") == 2 and 'class="com-lona quatro"' in obra
    R["dossie"]["fotos"] = {}
    assert 'class="com-lona' not in resumos.html_resumo_obra(R)


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



def test_quantidade_da_linha_na_cor_dela():
    """Kaefer (19/10): a quantidade de cada linha do tipo na cor da peça na foto"""
    assert 'class="pilula"' in resumos._pilula({"cor": "#e03131"}, "4 un") and "#e03131" in resumos._pilula({"cor": "#e03131"}, "4 un")
    assert resumos._pilula({}, "4 un") == "4 un"


def test_coeficiente_de_peso_nas_tabelas():
    """PRATI (19/10): o resumo dava os kg e os m² dos rufos sem o coeficiente usado; agora kg/m e kg/m² escritos (a chapa
    de 0,50 mm: 3,925 kg/m²) — o mesmo nas telhas, na chaparia e nos perfis"""
    R = {"funilaria": [{"nome": "RF2", "tipo": "Rufo", "perfil": "Rufo chapa galvanizada 0,50 mm", "desenvolvimento": 969.0,
                        "comprimento": 6000.0, "qtd": 16, "ml": 96.0, "m2": 93.024, "kg": 365.1}]}
    t = resumos._tabela_funilaria(R)
    assert "kg/m²" in t and "3,925" in t and "3,803" in t                    # 365,1 ÷ 93,024 e 365,1 ÷ 96
    assert resumos._coef(10.0, 0.0) == "—"


def test_rufos_com_o_mesmo_coeficiente_na_mesma_chapa():
    """PRATI (19/10): "porque foi considerado coeficiente diferente apesar de ser a mesma chapa" — a área e o peso da
    lista vêm arredondados peça a peça (o RF7 de 0,0235 m² saía 0,01 m² e 4,167 kg/m²); agora a área exata e o peso
    teórico (área × espessura × 7,85): 3,925 kg/m² em todas as linhas da chapa de 0,50 mm"""
    lista = {"posicoes": [
        {"nome": "RF1", "categoria": "RUFOS", "perfil": "Rufo chapa galvanizada 0,50 mm", "quantidade": 16, "comprimento": 969,
         "largura": 6000, "espessura": 0.5, "area_m2": 93.024, "peso_total": 365.1},
        {"nome": "RF7", "categoria": "RUFOS", "perfil": "Rufo chapa galvanizada 0,50 mm", "quantidade": 2, "comprimento": 51,
         "largura": 230, "espessura": 0.5, "area_m2": 0.01, "peso_total": 0.1}]}
    F = resumos.funilaria_da_lista(lista)
    assert {round(x["kg"] / x["m2"], 3) for x in F} == {3.925}
    assert abs(F[1]["m2"] - 2 * 0.051 * 0.230) < 1e-9


def test_tabela_comprida_parte_sem_deixar_o_cabecalho_sozinho():
    """Kaefer e PRATI (19/10): a tabela de até 8 linhas pulava inteira para a folha seguinte (52 mm em branco antes dos
    Pesos da Kaefer, 78 mm antes dos Rufos da PRATI) e, na maior, o cabeçalho ficava sozinho no pé da folha. Agora parte
    a partir de 6 linhas, com o cabeçalho e as 3 primeiras num tbody que não se parte e as 2 últimas com o total noutro"""
    import re
    linhas = [["L%d" % i, ("%d" % i, "r")] for i in range(11)]
    t = resumos._tabela(["Grupo", ("kg", "r")], linhas, rodape=[("TOTAL", "b"), ("55", "r")])
    cab = re.search(r'<tbody class="com-cab">(.*?)</tbody>', t).group(1)
    assert "<th>Grupo</th>" in cab and cab.count("<td>L") == 3 and "L2<" in cab and "L3<" not in cab
    fim = re.search(r'<tbody class="com-total">(.*?)</tbody>', t).group(1)
    assert "L9<" in fim and "L10<" in fim and "TOTAL" in fim and "L8<" not in fim
    assert t.count("<table") == 1 and "inteira" not in t                       # a mesma tabela, as mesmas colunas
    seis = resumos._tabela(["Grupo"], [["x"]] * 6)
    assert "inteira" not in seis and 'class="com-cab"' in seis                # 6 linhas já partem
    assert 'class="inteira"' in resumos._tabela(["Grupo"], [["x"]] * 5)        # 5, não
    css = resumos._CSS
    assert re.search(r"tbody\.com-cab, tbody\.com-total \{ break-inside: avoid; \}", css)


def test_tipo_comprido_comeca_ao_lado_da_foto(tmp_path):
    """PRATI (19/10): o tipo com mais de 12 linhas (Longarinas, 28) punha a foto de 120 mm em cima, centralizada, com as
    faixas dos lados vazias; e, como a foto não se parte, ficavam 87 mm em branco no pé da folha anterior. Agora as 8
    primeiras linhas vão ao lado da foto e o resto segue embaixo, na largura da folha"""
    import re
    cam = tmp_path / "tipo-longarinas.jpg"
    cam.write_bytes(b"\xff\xd8\xff\xd9")
    R = {"dossie": {"fotos": {"tipo-longarinas": str(cam)}}}
    linhas = [{"comprimento": 12000.0 - 100 * k, "qtd": 2, "kg": 10.0, "marcas": ["T.L%d" % k], "perfis": ["Ue 200×75×25×2,25"],
               "onde": [], "ids": ["p%d" % k]} for k in range(28)]
    b = {"chave": "longarinas", "titulo": "Longarinas", "cor": "#ae3ec9", "ids": [], "qtd": 56, "m": 600.0, "kg": 280.0,
         "linhas": linhas}
    h = resumos._bloco_tipo(R, b, False)
    assert 'class="bloco-tipo longa"' in h
    lado, resto = h.split('<div class="lado-a-lado">', 1)[1].split("</div></div>", 1)
    assert "<figure" in lado and lado.count('data-ids="p') == resumos.LINHAS_AO_LADO_DA_FOTO == 8
    assert resto.count('data-ids="p') == 20 and 'class="tipo continua"' in resto and "TOTAL" in resto
    assert re.search(r"\.bloco-tipo\.longa \.lado-a-lado \{ break-inside: avoid; \}", resumos._CSS)


def test_fotos_da_lona_numa_fileira_so():
    """Kaefer (19/10): as 4 fotos sem/com a lona em 2 × 2 com 52 mm ocupavam meia folha sozinhas e a implantação pulava
    (144 mm em branco); numa fileira, inteiras (3:2), cabem no pé da capa"""
    import re
    css = re.search(r"\.com-lona\.quatro \{([^}]*)\}", resumos._CSS).group(1)
    assert "repeat(4, 1fr)" in css
    assert "aspect-ratio: 3 / 2" in re.search(r"\.com-lona\.quatro img \{([^}]*)\}", resumos._CSS).group(1)


def test_pecas_fora_do_escopo_nao_sao_pendencia():
    """Kaefer (19/10): o aviso das 2.200 peças da cobertura industrializada (do cliente) saía nas pendências "a conferir";
    é uma decisão tomada — fica fora delas. Os outros avisos que mudam o peso continuam"""
    avisos = ["2200 peça(s) fora do nosso escopo (cobertura retrátil industrializada, fornecimento do cliente): ficaram fora "
              "do detalhamento, da lista de materiais e do peso — estão no 3D e no cálculo",
              "2 posição(ões) sem peso teórico"]
    assert resumos._avisos_que_contam(avisos) == ["2 posição(ões) sem peso teórico"]


def test_resumo_da_obra_no_peso_de_compra_quando_os_dados_pedem():
    """Kaefer, 26/10 ("ainda está com o peso antigo"): a proposta foi fechada pelo peso de compra (10.505 kg) e o resumo da
    obra dava o das peças (9.957,8). Com `peso_resumo` = "compra" nos Dados do resumo, a capa e os Pesos mostram os perfis
    em barras comerciais com aproveitamento + as chapas na espessura comercial, e o das peças fica ao lado; vazio, nada muda."""
    R = {"projeto": {"nome": "QUADRA"}, "dados": {}, "numeros": {"tesouras": 0, "peso_aco": 9957.8, "ml_telhas": 0.0, "peso_telhas": 0.0,
                                                                 "total": 9957.8, "parafusos": 0, "inclinacao": 0.0, "kg_m2": 14.56},
         "dimensoes": {"eixos": "", "comprimento_total": 0.0, "n_tesouras": 0, "nivel_apoio": 0.0, "apoio_por_chapa": False, "trechos": [],
                       "projecao": (18000.0, 38000.0), "area_m2": 684.0},
         "tesouras": [], "tercas": {"contagem": {k: {"pecas": 0, "tipos": 0} for k in ("cob", "lat", "oit", "marq")}, "linhas": [],
                                    "perfil_principal": "", "furos": ""},
         "grupos_peso": [{"grupo": "Pilares", "kg": 9957.8, "pct": 100.0}],
         "telhas": {"descricao": "", "itens": [], "trechos": {}, "ml_total": 0.0, "kg_total": 0.0, "ml_por_trecho": {}, "largura_util": 980.0},
         "parafusos": [], "familias": [], "chaparia": [], "chaparia_total": {"kg": 938.6, "pecas": 84}, "perfis_kg": 9019.2, "avisos": [],
         "compra": {"perfis": [{"perfil": "W 360×32,9", "kg": 4636.3, "kg_compra": 4737.6}, {"perfil": "W 200×26,6", "kg": 2021.6, "kg_compra": 2234.4},
                               {"perfil": "W 200×19,3", "kg": 600.6, "kg_compra": 694.8}, {"perfil": "U 127×50×2,00 (FF)", "kg": 1027.7, "kg_compra": 1027.7},
                               {"perfil": "Barra redonda ø 1\"", "kg": 473.1, "kg_compra": 525.1},
                               {"perfil": "Barra redonda ø 1/2\"", "kg": 259.8, "kg_compra": 262.4}],
                    "chapas": [{"kg": 215.7}, {"kg": 69.8}, {"kg": 776.1}]}}
    assert resumos.peso_de_compra(R) is None
    pecas = resumos.html_resumo_obra(R)
    assert "9.957,8" in pecas and "TOTAL DE COMPRA" not in pecas and "peso de compra" not in pecas
    R["dados"] = {"peso_resumo": "compra"}
    c = resumos.peso_de_compra(R)
    assert abs(c["kg"] - 10543.6) < 0.05 and abs(c["kg_m2"] - 10543.6 / 684.0) < 1e-6 and abs(c["sobra"] - 585.8) < 0.05
    obra = resumos.html_resumo_obra(R)
    capa = obra.split("Peças principais")[0]
    assert "10.543,6" in capa and "peso de compra" in capa and "15,41 kg/m² de projeção" in capa and "peças 9.957,8 kg" in capa
    assert "TOTAL DE COMPRA" in obra and "10.543,6 kg de aço na compra" in obra


# ---- a quantidade por tipo de peça (05/11, usuário: "um resumo igual ao que foi feito no Vicente mostrando a quantidade
# por tipo de peças" — Projeto/OBRAS/Vicente-Residence/Resumo-por-tipo-de-estrutura-2026-10-13.pdf)

def _bloco(chave, titulo, cor, linhas):
    """Um tipo da Estrutura por tipo do dossiê: linhas (qtd, comprimento mm, kg, marcas, perfil, onde)."""
    ls = [{"qtd": q, "comprimento": L, "kg": kg, "marcas": list(ms), "perfis": [perfil], "onde": list(onde), "ids": ["e%s%d" % (chave, k)]}
          for k, (q, L, kg, ms, perfil, onde) in enumerate(linhas)]
    return {"chave": chave, "titulo": titulo, "cor": cor, "ids": [i for li in ls for i in li["ids"]], "linhas": ls,
            "qtd": sum(li["qtd"] for li in ls), "m": sum(li["qtd"] * li["comprimento"] for li in ls) / 1000.0,
            "kg": sum(li["kg"] for li in ls)}


def _R_kaefer():
    """Os números do resumo da obra da Quadra Kaefer de 26/10 (um nível)."""
    est = [_bloco("pilares", "Pilares", "#364fc7", [(4, 8000, 1052.8, ["PL5"], "W 360×32,9", []), (4, 7780, 600.6, ["PL3"], "W 200×19,3", []),
                                                    (14, 7780, 3583.5, ["PL1"], "W 360×32,9", [])]),
           _bloco("vigas_i", "Vigas I", "#2f9e44", [(2, 38000, 2021.6, ["VG1"], "W 200×26,6", [])]),
           _bloco("longarinas", "Longarinas de fechamento", "#ae3ec9", [(16, 5925, 332.3, ["T.L.2"], "U 127×50×2,00 (FF)", []),
                                                                       (8, 5825, 163.4, ["T.L.3"], "U 127×50×2,00 (FF)", []),
                                                                       (32, 4744, 531.9, ["T.L.1"], "U 127×50×2,00 (FF)", [])]),
           _bloco("contrav", "Contraventamentos", "#e03131", [(12, 7155, 85.4, ["CV.3"], "Barra redonda ø 1/2\"", []),
                                                              (4, 7035, 28.0, ["CV.4"], "Barra redonda ø 1/2\"", []),
                                                              (12, 6210, 74.1, ["CV.1"], "Barra redonda ø 1/2\"", []),
                                                              (12, 6075, 72.4, ["CV.2"], "Barra redonda ø 1/2\"", [])])]
    return {"projeto": {"nome": "QUADRA"}, "dados": {}, "dimensoes": {}, "numeros": {"peso_aco": 9957.8, "parafusos": 0},
            "grupos_peso": [], "tesouras": [], "parafusos": [], "familias": [], "chaparia": [], "avisos": [],
            "dossie": {"estrutura": est, "varios": False}}


def _celulas(html_, rotulo):
    """O texto das células da linha da tabela que começa com `rotulo`."""
    import re
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_, re.S):
        tds = [re.sub(r"<[^>]+>", " ", t) for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        tds = [" ".join(t.split()) for t in tds]
        if tds and tds[0].startswith(rotulo):
            return tds
    raise AssertionError("sem a linha %r" % rotulo)


def test_quantidade_por_tipo_na_obra_de_um_nivel():
    """Kaefer: um tipo por linha com qtd, metros, peso, % e as marcas; as peças principais fecham com o cartão da capa
    (120 un) e a última linha com o peso da estrutura (o resto é chapa solta e chumbador)."""
    R = _R_kaefer()
    q = resumos.quadro_por_tipo(R, 1)
    assert "Quantidade por tipo de peça" in q and "120 peças principais" in q
    assert _celulas(q, "Pilares") == ["Pilares W 360×32,9, W 200×19,3", "22 un", "172,0 m", "5.236,9 kg", "52,6%", "PL1 · PL3 · PL5"]
    assert _celulas(q, "Contraventamentos")[1:] == ["40 un", "261,4 m", "259,9 kg", "2,6%", "CV.1 · CV.2 · CV.3 · CV.4"]
    assert _celulas(q, "PEÇAS PRINCIPAIS")[1:5] == ["120 un", "802,7 m", "8.546,0 kg", "85,8%"]
    assert _celulas(q, "Chapas soltas, chumbadores e o mais")[3:5] == ["1.411,8 kg", "14,2%"]
    assert _celulas(q, "ESTRUTURA METÁLICA")[3:5] == ["9.957,8 kg", "100,0%"]
    assert 'data-ids="epilares0,epilares1,epilares2"' in q          # na tela, a linha abre o 3D com as peças do tipo
    # o título vai junto com a tabela (Vicente, ensaio de 05/11: o título ficava no pé da capa e a tabela na folha seguinte)
    assert q.startswith('<section class="qtipo-bloco">') and q.endswith("</section>")
    assert ".qtipo-bloco { break-inside: avoid; }" in resumos.html_resumo_obra(R)
    # na abertura do resumo da obra: logo depois dos cartões, antes dos desenhos (a seção 01; a Implantação vira a 02)
    obra = resumos.html_resumo_obra(R)
    assert obra.index('class="ficha"') < obra.index("Quantidade por tipo de peça") < obra.index("Implantação")
    assert '<span class="n">01</span>Quantidade por tipo de peça' in obra and '<span class="n">02</span>Implantação' in obra


def test_quantidade_por_tipo_marcas_demais_resumidas():
    assert resumos._marcas_resumidas(["T10", "T2", "T1", "T3", "T5", "T2"]) == "T1 … T10 (5 marcas)"
    assert resumos._marcas_resumidas(["PL3", "PL1", ""]) == "PL1 · PL3"


def _R_vicente(pavs=None):
    """Os números do resumo da obra do Vicente Residence de 13/10 (6 pavimentos com repetição)."""
    P, La, D, T, Pe, C = "Piscina", "Lazer", "Duplex", "Tipo", "Penthouse", "Cobertura"
    est = [_bloco("pilares", "Pilares", "#364fc7", [(22, 6850, 7869.0, ["PL2"], "TQ 250x6,3", [(La, 6), (D, 12), (C, 4)]),
                                                    (1, 6320, 356.1, ["PL6"], "TQ 250x6,3", [(P, 1)])]),
           _bloco("pilaretes", "Pilaretes", "#15aabf", [(47, 3666, 9991.5, ["PL1", "PL3", "PL4", "PL5", "PL7"], "TR 250x100x9,5",
                                                         [(P, 6), (La, 8), (D, 24), (C, 9)])]),
           _bloco("caixote", "Vigas caixote", "#c77700", [(123, 3784, 10972.6, ["T%d" % k for k in range(1, 20)], "TQ 50x50x3,0",
                                                           [(La, 12), (D, 33), (T, 48), (Pe, 18), (C, 12)])]),
           _bloco("vigas_tubo", "Vigas tubo", "#0f8a7e", [(22, 6491, 6907.9, ["VG1", "VG2"], "TR 250x100x9,5", [(P, 2), (La, 4), (D, 12), (C, 4)])]),
           _bloco("travamentos", "Travamentos e agulhamentos", "#495057", [(6, 517, 4.8, ["G.1"], "FE RED 5/8\"", [(D, 6)])]),
           _bloco("suportes", "Suportes e peças curtas", "#adb5bd", [(724, 160, 395.9, ["S1"], "U 75x40", [(T, 336), (Pe, 168), (D, 220)])])]
    pavs = pavs or [{"nome": P, "repete": 1}, {"nome": La, "repete": 1}, {"nome": D, "repete": 3}, {"nome": T, "repete": 12},
                    {"nome": Pe, "repete": 6}, {"nome": C, "repete": 1}]
    return {"projeto": {"nome": "VICENTE"}, "dados": {}, "dimensoes": {}, "numeros": {"peso_aco": 39667.0, "parafusos": 0},
            "dossie": {"estrutura": est, "varios": True, "pavimentos": pavs}}


def test_quantidade_por_tipo_com_uma_coluna_por_pavimento():
    """Vicente: na obra de vários pavimentos, quantas peças do tipo vão em cada um, já com as repetições (o Tipo ×12
    conta os 12 andares); travamentos e suportes ficam fora das peças principais, como no cartão da capa (215)."""
    q = resumos.quadro_por_tipo(_R_vicente(), 1)
    assert "215 peças principais · 6 pavimentos" in q
    for cab in ("Piscina", "Lazer", "Duplex ×3", "Tipo ×12", "Penthouse ×6", "Cobertura"):
        assert '<th class="pav">%s</th>' % cab in q
    assert _celulas(q, "Vigas caixote")[1:] == ["123 un", "·", "12", "33", "48", "18", "12", "465,4 m", "10.972,6 kg"]
    assert _celulas(q, "Pilares")[1:8] == ["23 un", "1", "6", "12", "·", "·", "4"]
    assert _celulas(q, "PEÇAS PRINCIPAIS")[1:] == ["215 un", "9", "30", "81", "48", "18", "29", "937,6 m", "36.097,1 kg"]
    assert _celulas(q, "Travamentos e agulhamentos")[1:5] == ["6 un", "·", "·", "6"]
    assert _celulas(q, "Chapas soltas, chumbadores e o mais")[-1] == "3.169,2 kg"
    assert _celulas(q, "ESTRUTURA METÁLICA")[-1] == "39.667,0 kg"
    assert "%" not in "".join(_celulas(q, "PEÇAS PRINCIPAIS"))          # o % e as marcas só na obra de um nível


def test_quantidade_por_tipo_com_pavimentos_demais_diz_onde_em_texto():
    pavs = [{"nome": "P%d" % k, "repete": 1} for k in range(1, 9)]
    R = _R_vicente(pavs)
    for b in R["dossie"]["estrutura"]:
        for li in b["linhas"]:
            li["onde"] = [("P1", li["qtd"])]
    q = resumos.quadro_por_tipo(R, 1)
    assert '<th class="pav">' not in q and "<th>Onde</th>" in q and _celulas(q, "Vigas caixote")[2] == "P1 123"


def test_sem_a_estrutura_do_dossie_nao_ha_quadro_por_tipo():
    """o resumo montado à mão (sem o dossiê): só as tesouras, que não são a obra inteira — o quadro não sai"""
    assert resumos.quadro_por_tipo({"numeros": {"peso_aco": 1000.0}, "tesouras": [{"qtd": 2}]}, 1) == ""


def test_quantidade_por_tipo_no_peso_de_compra_leva_a_ponte_ate_a_compra():
    """com o resumo no peso de compra (o cartão da capa dá 10.543,6 kg), o quadro fecha no peso das peças e diz a compra
    embaixo — sem isso, o 9.957,8 do quadro parecia contradizer o cartão"""
    R = _R_kaefer()
    R["dados"] = {"peso_resumo": "compra"}
    R["dimensoes"] = {"area_m2": 684.0}
    R["compra"] = {"perfis": [{"kg_compra": 9482.0}], "chapas": [{"kg": 1061.6}]}
    q = resumos.quadro_por_tipo(R, 1)
    assert _celulas(q, "ESTRUTURA METÁLICA (peças)")[3:5] == ["9.957,8 kg", "100,0%"]
    assert _celulas(q, "Na compra (barras e chapas comerciais)")[3:5] == ["10.543,6 kg", ""]
    R["dados"] = {}
    assert "Na compra" not in resumos.quadro_por_tipo(R, 1)


def test_revisao_nova_manda_os_documentos_da_anterior_para_o_obsoleto(tmp_path):
    """Usuário, 06/11 (LEIA-ME, "Revisões de documentos"): o documento da revisão nova substitui o anterior e o ANTIGO vai
    para Obsoleto/, na mesma pasta e no mesmo passo, com a revisão no nome; a mesma revisão gerada de novo substitui no lugar."""
    import json
    pasta = str(tmp_path)
    R = {"projeto": {"nome": "QUADRA"}, "dados": {"revisao": "R01", "data": "05/11/2026"},
         "numeros": {"tesouras": 0, "peso_aco": 100.0, "ml_telhas": 0.0, "peso_telhas": 0.0, "total": 100.0, "parafusos": 0,
                     "inclinacao": 0.0, "kg_m2": 1.0},
         "dimensoes": {"eixos": "", "comprimento_total": 0.0, "n_tesouras": 0, "nivel_apoio": 0.0, "apoio_por_chapa": False,
                       "trechos": [], "projecao": (10000.0, 10000.0), "area_m2": 100.0},
         "tesouras": [], "tercas": {"contagem": {k: {"pecas": 0, "tipos": 0} for k in ("cob", "lat", "oit", "marq")}, "linhas": [],
                                    "perfil_principal": "", "furos": ""},
         "grupos_peso": [], "telhas": {"descricao": "", "itens": [], "trechos": {}, "ml_total": 0.0, "kg_total": 0.0,
                                       "ml_por_trecho": {}, "largura_util": 980.0},
         "parafusos": [], "familias": [], "chaparia": [], "chaparia_total": {"kg": 0.0, "pecas": 0}, "perfis_kg": 100.0, "avisos": []}
    resumos.gerar_resumos(pasta, dict(R), imprimir_pdf=False)
    assert json.load(open(os.path.join(pasta, resumos.ARQ_NUMEROS), encoding="utf-8"))["revisao"] == "R01"
    for n in resumos.DOCUMENTOS_DA_REVISAO:                     # os PDFs e a planilha da R01 (a impressão fica fora do teste)
        open(os.path.join(pasta, n), "w").write("R01")
    resumos.gerar_resumos(pasta, dict(R), imprimir_pdf=False)  # a mesma revisão: nada vai para o Obsoleto
    assert not os.path.exists(os.path.join(pasta, "Obsoleto"))
    R2 = dict(R, dados={"revisao": "R02", "data": "06/11/2026"}, avisos=[])
    resumos.gerar_resumos(pasta, R2, imprimir_pdf=False)
    obs = sorted(os.listdir(os.path.join(pasta, "Obsoleto")))
    assert obs == ["resumo-da-obra (R01).pdf", "resumo-de-materiais (R01).pdf", "resumo-de-materiais (R01).xlsx"], obs
    assert open(os.path.join(pasta, "Obsoleto", "resumo-da-obra (R01).pdf")).read() == "R01"
    assert len(R2["obsoletos"]) == 3 and not any("abertos" in a for a in R2["avisos"])
    # o arquivo aberto (o Word/Excel prende) não se move: fica, com o aviso
    for n in resumos.DOCUMENTOS_DA_REVISAO:
        open(os.path.join(pasta, n), "w").write("R02")
    from saida import entrega
    real = os.replace

    def preso(a, b):
        if a.endswith(".xlsx"):
            raise PermissionError(a)
        return real(a, b)
    entrega.os.replace = preso
    try:
        R3 = dict(R, dados={"revisao": "R03"}, avisos=[])
        resumos.gerar_resumos(pasta, R3, imprimir_pdf=False)
    finally:
        entrega.os.replace = real
    assert any("abertos" in a and "resumo-de-materiais.xlsx" in a for a in R3["avisos"]), R3["avisos"]
    assert "resumo-da-obra (R02).pdf" in os.listdir(os.path.join(pasta, "Obsoleto"))
