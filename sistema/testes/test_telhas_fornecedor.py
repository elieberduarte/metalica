# -*- coding: utf-8 -*-
"""As telhas para o fornecedor no padrão do Fábio (usuário, 13/11; Projeto/BRIEFINGS/Briefing-padrao-telhas-fabio-
2026-11-13.md): a prova é pelo formato dele — as linhas do .doc e as medidas dos quadros da multidobra como entrada fixa —,
e o DXF em tamanho real com cotas de verdade, sem os textos que ele riscou."""
import math
import re

import ezdxf
import pytest

from nucleo2d.desenho import Cota, CotaEspecial, Desenho, Texto
from nucleo2d.cota_especial import medida
from nucleo2d.detalhe import telhas_fornecedor as F
from saida import telhas_fornecedor as S

#: o texto do .doc do Fábio ("RELAÇÃO DE TELHAS - BOM DIA_10-09-2026_Fabio.doc"), as linhas com texto, na ordem
FABIO = """RELAÇÃO DE TELHAS BOM DIA – Maringá - PR
10/09/2026
COBERTURA:
TELHA TP40-0,65mm GALVALUME NATURAL (Tamanho útil 0,98m)
48 pçs c/. 9,70m (S/. Lanternin)
160 pçs c/. 9,50m (C/. Lanternin)
412 pçs c/. 9,75m
206 pçs c/. 6,45m
Total: 7.331,30ml
CUMEEIRA TP40-0,65mm GALVALUME NATURAL
23 pçs com 1,00m (Aba 0,50m x 0,50m)
TELHA Ondulada L17-0,50mm GALVALUME NATURAL
12 pçs c/. 9,05m
18 pçs c/. 7,75m
06 pçs c/. 1,00m
Total: 254,10ml
TELHA MULTIDOBRA TP40-0,50mm pré-pintada CINZA RAL 7035
206 pçs c/. 2,662m
72 pçs c/. 1,995m (Marquise)
Total: 692,01ml
Lateral
TELHA TP40-0,50mm pré-pintada CINZA RAL 7035 (Tamanho útil 0,98m)
38 pçs c/. 8,35m
170 pçs c/. 8,45m
Total: 1.753,80ml
Oitoes
TELHA TP40-0,50mm pré-pintada CINZA RAL 7035 (Tamanho útil 0,98m)
72 pçs c/. 7,30m (Oitão Fundos)
72 pçs c/. 5,55m (Oitão Frente)
72 pçs c/. 1,83m (Fechamento marquise)
""" + "".join("04 pçs c/. %s\n" % v for v in (
    "5,70m", "5,60m", "5,55m", "5,50m", "5,40m", "5,30m", "5,25m", "5,20m", "5,10m", "5,05m", "4,95m", "4,90m", "4,80m",
    "4,75m", "4,65m", "4,60m", "4,50m", "4,45m", "4,40m", "4,30m", "4,25m", "4,15m", "4,05m", "4,00m", "3,95m", "3,85m",
    "3,80m", "3,70m", "3,65m", "3,55m", "3,50m", "3,40m", "3,35m", "3,25m", "3,20m", "3,10m")) + """Total: 1.691,76ml
Marquise
TELHA TP40-0,50mm pré-pintada CINZA RAL 7035 (Tamanho útil 0,98m)
72 pçs c/. 4,75m
02 pçs c/. 1,90m
02 pçs c/. 1,80m
02 pçs c/. 1,65m
02 pçs c/. 1,50m
02 pçs c/. 1,40m
02 pçs c/. 1,25m
Total: 361,00ml"""


def _linhas_do_fabio():
    """os blocos (lugar, tipo, quantidade, comprimento, obs) lidos do texto dele — a entrada do escritor"""
    blocos, tipo = [], None
    for t in FABIO.splitlines()[2:]:
        m = re.match(r"^(\d+) pçs (c/\.|com) (\d+),(\d+)m(?: \((.*)\))?$", t)
        if m:
            casas = len(m.group(4))
            tipo["linhas"].append({"qtd": int(m.group(1)), "com": m.group(2), "casas": casas, "obs": m.group(5) or "",
                                   "comp": float(m.group(3) + "." + m.group(4)) * 1000.0})
        elif t.startswith("Total:"):
            tipo["total"] = sum(l_["qtd"] * l_["comp"] for l_ in tipo["linhas"]) / 1000.0
        elif t.startswith(("TELHA", "CUMEEIRA")):
            tipo = {"titulo": t, "linhas": [], "total": None}
            if not blocos:
                blocos.append({"lugar": "", "tipos": []})
            blocos[-1]["tipos"].append(tipo)
        else:
            blocos.append({"lugar": t, "tipos": []})
    return blocos


def test_a_relacao_sai_igual_ao_word_do_fabio_linha_a_linha():
    blocos = _linhas_do_fabio()
    saida = [t for t, _e in F.texto_da_relacao(blocos, "BOM DIA", "Maringá - PR", "10/09/2026") if t]
    assert saida == FABIO.splitlines()


def test_os_totais_sao_as_somas_das_linhas():
    # os totais do Fábio são as somas exatas: o milhar com ponto, duas casas
    assert F._num(7331.3) == "7.331,30" and F._num(692.012) == "692,01" and F._num(1691.76) == "1.691,76"


def test_o_word_tem_o_formato_do_fabio(tmp_path):
    import docx
    blocos = _linhas_do_fabio()
    cam = S.gravar_docx(F.texto_da_relacao(blocos, "BOM DIA", "Maringá - PR", "10/09/2026"), str(tmp_path / "r.docx"))
    d = docx.Document(cam)
    ps = [p for p in d.paragraphs if p.text]
    assert [p.text for p in ps] == FABIO.splitlines()
    assert d.styles["Normal"].font.name == "Times New Roman" and d.styles["Normal"].font.size.pt == 12
    tit = ps[0]
    assert tit.alignment == 1 and tit.runs[0].bold and tit.runs[0].underline
    assert ps[2].runs[0].bold and ps[2].runs[0].underline                      # COBERTURA:
    tot = next(p for p in ps if p.text.startswith("Total:"))
    assert tot.runs[0].bold and not tot.runs[0].underline
    linha = next(p for p in ps if " pçs " in p.text)
    assert not linha.runs[0].bold


@pytest.mark.parametrize("retas, raio_int, ang, quadros", [
    # (internas, externas): retas, raio, ângulo, arco, corda, total — os quadros do Fábio
    ((468, 608), 600, 82.25, [((468, 608), 600, 82, 861, 1602, "1,937m"), ((468, 608), 640, 82, 919, 1655, "1,995m")]),
    ((425, 1580), 400, 85.53, [((425, 1580), 400, 86, 597, 2162, "2,602m"), ((425, 1580), 440, 86, 657, 2213, "2,662m")]),
])
def test_a_multidobra_refaz_os_quadros_do_fabio(retas, raio_int, ang, quadros):
    d = Desenho(nome="md", escala=F.ESCALA_TEXTO)
    F.desenho_da_multidobra(F.md_das_medidas(retas[0], retas[1], raio_int, ang), d, 0, 0, "Marquise", 72)
    cotas = [round(e.medida()) for e in d.entidades.values() if isinstance(e, Cota)]
    esp = [medida(e) for e in d.entidades.values() if isinstance(e, CotaEspecial)]
    arcos = [e.atributos["arco"] for e in d.entidades.values() if isinstance(e, Texto) and "arco" in (e.atributos or {})]
    totais = [e.texto for e in d.entidades.values() if isinstance(e, Texto) and "total" in (e.atributos or {})]
    assert len(cotas) == 6 and len(esp) == 4 and len(arcos) == 2           # seis cotas por quadro
    for k, (r, raio, a, arco, corda, total) in enumerate(quadros):
        assert cotas[3 * k: 3 * k + 2] == list(r)
        assert abs(cotas[3 * k + 2] - corda) <= 2                         # a corda VOLTA (decisão 3)
        assert esp[2 * k] == "R%d" % raio and esp[2 * k + 1] == "%d°" % a
        assert abs(arcos[k] - arco) <= 1.0
        assert totais[k] == total
    # o perfil com as duas faces, afastadas a altura da onda (R ext − R int = 40)
    assert esp[2] == "R%d" % (raio_int + 40)
    assert any(isinstance(e, Texto) and e.texto == "Multidobra Marquise - 72x" for e in d.entidades.values())


def _face_de_teste():
    """um oitão: 6 chapas de pé de base reta, comprimentos de 5 em 5 cm (as três do meio iguais)"""
    chapas = []
    for i, L in enumerate((1500.0, 1700.0, 1900.0, 1900.0, 1900.0, 1700.0)):
        x = 977.0 * i
        corte = [(x - 490, 0.0), (x + 490, 0.0), (x + 490, L - 30.0), (x - 490, L - 60.0)]
        chapas.append({"x": x, "y0": 0.0, "y1": L - 30.0, "comprimento": L, "contorno": corte, "corte": corte, "nome": "TL%d" % L,
                       "alinhada": True})
    return {"numero": 4, "tipo": "fachada", "chapas": chapas, "normal": (1.0, 0.0, 0.0), "u": (0.0, 0.0, 1.0), "v": (0.0, 1.0, 0.0)}


def test_a_fachada_e_a_area_util_so_com_o_comprimento():
    d = Desenho(nome="f", escala=F.ESCALA_TEXTO)
    F.desenho_da_fachada(_face_de_teste(), d, 0, 0, titulo="OITÃO 4")
    from nucleo2d.desenho import Polilinha
    rets = [e for e in d.entidades.values() if isinstance(e, Polilinha) and e.fechada]
    assert len(rets) == 6
    for r in rets:
        xs = [q[0] for q in r.vertices]
        ys = [q[1] for q in r.vertices]
        assert abs(max(xs) - min(xs) - 980.0) < 0.01                         # o retângulo inteiro da largura útil
        assert round(max(ys) - min(ys)) % 50 == 0                            # de 5 em 5 cm
    cotas = sorted(round(e.medida()) for e in d.entidades.values() if isinstance(e, Cota))
    assert cotas == [1500, 1700, 1700, 1900]       # as três iguais e vizinhas: uma cota só (como a prancha, de 3 em diante)
    assert all(e.texto is None for e in d.entidades.values() if isinstance(e, Cota))
    textos = [e.texto for e in d.entidades.values() if isinstance(e, Texto)]
    assert textos == ["OITÃO 4"]                                             # nem nome TL, nem útil/total, nem resumo


def test_o_dxf_e_tamanho_real_com_cotas_de_verdade(tmp_path):
    d = Desenho(nome="forn", escala=F.ESCALA_TEXTO)
    F.desenho_da_multidobra(F.md_das_medidas(468, 608, 600, 82.25), d, 0, 0, "Marquise", 72)
    F.desenho_da_fachada(_face_de_teste(), d, 0, -6000.0, titulo="OITÃO 4")
    cam = S.gravar_dxf(d, str(tmp_path / "t.dxf"))
    doc = ezdxf.readfile(cam)
    assert doc.dxfversion == "AC1032"                                        # R2018
    msp = doc.modelspace()
    textos = [e.dxf.text for e in msp if e.dxftype() in ("TEXT", "MTEXT")]
    proibido = re.compile(r"(?i)\bESC\b|ESC\.|útil|\btotal\b|\bTL\d|RELA|\bkg\b|ampliad")
    assert not [t for t in textos if proibido.search(t)], textos
    dims = [e for e in msp if e.dxftype() == "DIMENSION"]
    assert len(dims) == 6 + 4 + 4                                            # 6 lineares + 2 raios + 2 ângulos; 4 na fachada
    for dm in dims:
        assert dm.dxf.text in ("", "<>")                                     # nenhum número escrito por cima
    lineares = [dm for dm in dims if dm.dimtype in (0, 1)]
    medidas = sorted(round(dm.get_measurement()) for dm in lineares)
    for v in (468, 608, 1500, 1700, 1900):
        assert v in medidas
    estilo = doc.dimstyles.get(S.NOME_ESTILO)
    assert estilo.dxf.dimlfac == 1.0                                         # a cota mede o desenho: tamanho real


def test_o_raio_externo_e_o_comercial_e_nao_a_onda_do_modelo():
    # a Sala: o modelo traz 41 de onda e o desenho dava R491; o raio comercial é R450 int. / R490 ext. (GESTÃO, 13/11)
    md = F.md_das_medidas(560, 990, 450, 79.0, altura_onda=41.0)
    md.update(raio_ext=490.0, arco_ext=490.0 * math.radians(79.0))
    d = Desenho(nome="md", escala=F.ESCALA_TEXTO)
    F.desenho_da_multidobra(md, d, 0, 0, "cobertura", 64)
    raios = [medida(e) for e in d.entidades.values() if isinstance(e, CotaEspecial) and e.modo == "raio"]
    assert raios == ["R450", "R490"]


def _face_lateral(numero, lado, x0, comps, plano):
    chapas = []
    for i, L in enumerate(comps):
        x = x0 + 977.0 * i
        corte = [(x - 490, 0.0), (x + 490, 0.0), (x + 490, L - 20.0), (x - 490, L - 20.0)]
        chapas.append({"x": x, "y0": 0.0, "y1": L - 20.0, "comprimento": L, "contorno": corte, "corte": corte,
                       "nome": "TL%d" % L, "alinhada": True, "perfil": "TELHA TP40 0.50MM"})
    return {"numero": numero, "lado": lado, "tipo": "fachada", "chapas": chapas, "normal": (0.0, 1.0, 0.0),
            "u": (0.0, 0.0, 1.0), "v": (1.0, 0.0, 0.0), "plano": plano}


def test_a_mesma_medida_em_duas_linhas_leva_o_lugar_de_cada_uma():
    # o Depósito: "16 pçs c/. 1,55m" seguida de "54 pçs c/. 1,55m (externa)" não se distinguia (GESTÃO, 13/11)
    agua = {"numero": 1, "tipo": "cobertura", "inclinacao": 10.0, "u": (0.0, 0.99, 0.17), "normal": (0.0, -0.17, 0.99),
            "chapas": [], "plano": 0.0}
    faces = [agua, _face_lateral(3, "externa", 0.0, [1550.0] * 3, 21000.0), _face_lateral(4, "interna", 0.0, [900.0] * 3, 21000.0),
             _face_lateral(7, None, 5000.0, [1550.0] * 2, 21200.0), _face_lateral(5, "externa", 0.0, [1550.0], 0.0)]
    bl = F.relacao_das_telhas(faces, {"telhas": [], "cumeeiras": []})
    linhas = [F.linha_da_relacao(l_) for b in bl for t in b["tipos"] for l_ in t["linhas"]]
    assert linhas == ["02 pçs c/. 1,55m (Lateral direita)", "03 pçs c/. 1,55m (Lateral direita externa)",
                      "01 pçs c/. 1,55m (Lateral esquerda externa)", "03 pçs c/. 0,90m (interna)"]
    # e cada linha guarda a medida do modelo (a tabela "medida do modelo → relação")
    assert [l_["modelo"] for b in bl for t in b["tipos"] for l_ in t["linhas"]][-1] == [880.0, 880.0]


def test_o_titulo_da_vista_e_o_eixo_do_projeto():
    agua = {"numero": 1, "tipo": "cobertura", "inclinacao": 10.0, "u": (0.0, 0.99, 0.17), "normal": (0.0, -0.17, 0.99),
            "chapas": [], "plano": 0.0}
    lat = _face_lateral(3, "externa", 0.0, [1550.0], 21000.0)
    eixos = {"eixo_g": (1.0, 0.0), "perp_g": (0.0, 1.0), "numeros": [{"nome": "1", "pos": 0.0}],
             "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 20800.0}]}
    assert F.titulo_da_face(lat, [agua, lat], eixos) == "LATERAL EIXO B – EXTERNA"
    assert F.titulo_da_face(lat, [agua, lat], None) == "LATERAL 3 – EXTERNA"           # sem eixo e sem outra lateral


def test_a_estrutura_vai_numa_camada_propria():
    d = Desenho(nome="f", escala=F.ESCALA_TEXTO)
    F.desenho_da_fachada(_face_de_teste(), d, 0, 0, estrutura=[((-500.0, 800.0), (5000.0, 1200.0))], titulo="OITÃO 4")
    from nucleo2d.desenho import Linha
    est = [e for e in d.entidades.values() if isinstance(e, Linha)]
    assert est and all(e.camada == F.CAMADA_ESTRUTURA for e in est)
    assert F.CAMADA_ESTRUTURA in d.camadas


def test_a_fachada_enviesada_do_canto_leva_o_lugar_pela_posicao():
    # o Depósito: "Oitão 9" não é lugar para o fornecedor (GESTÃO, 13/11) — a chapa enviesada do canto leva o canto
    agua = {"numero": 1, "tipo": "cobertura", "inclinacao": 10.0, "u": (0.0, 0.99, 0.17), "normal": (0.0, -0.17, 0.99),
            "chapas": [], "plano": 0.0}
    # o prédio de x 0 a 30000 (ao longo da cumeeira) e y 0 a 20000; a cumeeira corre em x
    esq = _face_lateral(3, None, 10000.0, [1550.0] * 3, 0.0)
    dir_ = _face_lateral(4, None, 10000.0, [1550.0] * 3, 20000.0)
    oitoes = []
    for k, x in ((5, 0.0), (6, 30000.0)):
        o = _face_lateral(k, None, 9000.0, [1550.0] * 3, x)
        o.update(normal=(1.0, 0.0, 0.0), v=(0.0, 1.0, 0.0))
        oitoes.append(o)
    # a enviesada a 45°, com o meio em (29000, 19000)
    s2 = math.sqrt(0.5)
    env = _face_lateral(9, None, 0.0, [1550.0], 0.0)
    a_, c_ = (19000.0 - 29000.0) / (2 * s2), (29000.0 + 19000.0) / (2 * s2)
    env.update(normal=(s2, s2, 0.0), v=(-s2, s2, 0.0), plano=c_)
    env["chapas"][0]["contorno"] = [(a_ - 490.0, 0.0), (a_ + 490.0, 0.0), (a_ + 490.0, 1530.0), (a_ - 490.0, 1530.0)]
    faces = [agua, esq, dir_] + oitoes + [env]
    # frente = o começo ao longo de (-1, 0) (a cumeeira desta água): x grande; direita = y grande
    assert F.titulo_da_face(env, faces) == "CANTO FRENTE DIREITA"
    assert F.titulo_da_face(dir_, faces) == "LATERAL DIREITA"
    assert F.titulo_da_face(oitoes[1], faces) == "OITÃO FRENTE"
