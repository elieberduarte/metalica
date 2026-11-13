# -*- coding: utf-8 -*-
"""A obra sem cobertura (o mezanino, o edifício): os grupos pelo papel da peça — Pilares, Vigas, Peças curtas —, não
"Vigas caixote", "Travamentos e agulhamentos", "Dispositivos" nem "Trechos da cobertura".

Usuário, Mezanino Drugovich 13/11 (pelo GESTÃO N.8; "é assim?" respondido): "não existe viga caixote no mezanino",
"não é cobertura", "Agulhamentos?", "Tesoura?" — "sugiro partirmos para nomes mais genéricos". Aprovado: Pilares · Vigas ·
Peças curtas; as marcas do projetista quando o IFC traz (Tekla 0055A), senão PL/VG/PC; "Vãos entre eixos" e "Nível do piso".
A obra com cobertura não muda, e a viga caixote de verdade (treliça em pé, o Vicente) continua viga caixote.
"""
import re

from nucleo3d.modelo import Barra, Documento
from nucleo2d.detalhar import detalhar
from nucleo2d.detalhe.base import _categoria
from saida import dossie, lista_producao, resumos

EIXOS = {"numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6000.0}],
         "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 4000.0}]}


def _ifc(conj, pos):
    """As marcas do Tekla (o conjunto 0055A, a peça W3) e a origem no IFC."""
    return {"marcas": {"posicao": pos, "conjunto": conj}, "origem_ifc": "guid-%s-%s" % (conj, pos)}


def _mezanino(doc, secundarias=8):
    """O Drugovich em miniatura: 4 pilares W150 em pé, 2 vigas W310 com 8 tocos W250 de 430 mm soldados (8+ barras: a
    regra antiga fazia "tesoura" / "viga caixote") e as secundárias W250 — sem telha nem terça."""
    k = 0
    for x in (0.0, 6000.0):
        for y in (0.0, 4000.0):
            k += 1
            doc.add(Barra(nome="P", inicio=(x, y, 0.0), fim=(x, y, 2530.0), perfil="W 150×18,0", papel="",
                          atributos=_ifc("00%02dA" % (40 + k), "W10")))
    for j, y in enumerate((0.0, 4000.0)):
        conj = "00%02dA" % (55 + j)
        doc.add(Barra(nome="V", inicio=(0.0, y, 2685.0), fim=(6000.0, y, 2685.0), perfil="W 310×38,7", papel="",
                      atributos=_ifc(conj, "W3")))
        for i in range(8):
            x = 600.0 + i * 650.0
            doc.add(Barra(nome="T", inicio=(x, y + 80.0, 2715.0), fim=(x, y + 510.0, 2715.0), perfil="W 250×17,9", papel="",
                          atributos=_ifc(conj, "W5")))
    for i, x in enumerate([600.0 + 4800.0 * k / max(1, secundarias - 1) for k in range(secundarias)]):
        doc.add(Barra(nome="S", inicio=(x, 510.0, 2715.0), fim=(x, 3490.0, 2715.0), perfil="W 250×17,9", papel="",
                      atributos=_ifc("00%02dA" % (68 + i), "W7")))


def _resumo(doc, eixos=None):
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    nomes = r.get("nomes") or {}
    cat = {p.marca: _categoria(p, r["camadas"].get(p.marca, "")) for p in r["objetos_posicoes"]}
    lista = lista_producao.montar(r["objetos_posicoes"], cat, r["acessorios"], pecas=r["objetos_pecas"], projeto={"nome": "m"})
    lev = {"posicoes": r["objetos_posicoes"], "pecas": r["objetos_pecas"], "acessorios": r["acessorios"], "avisos": r["avisos"]}
    R = resumos.levantar_resumos(doc, lev, lista, nomes, {})
    R["dossie"] = dossie.levantar(doc, lev, lista, nomes, R, eixos)
    R["_lista"] = lista
    return R, nomes


def _texto(R) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", resumos.html_resumo_obra(R)))


def test_mezanino_sem_cobertura_grupos_pelo_papel():
    doc = Documento(nome="mezanino")
    _mezanino(doc)
    R, nomes = _resumo(doc, EIXOS)
    assert R["cobertura"] is False
    assert R["tesouras"] == [] and R["numeros"]["trelicas_sem_cobertura"] == 0     # a viga com tocos não é treliça
    # a lista de materiais também: conjunto, não "Viga caixote"
    cl = {c["marca"]: c for c in R["_lista"]["conjuntos"]}
    assert cl["0055A"]["categoria"] == "CONJUNTOS" and not cl["0055A"].get("titulo_categoria")
    tc = resumos._por_marca(nomes["tipos_conjuntos"])
    assert tc["0055A"] == tc["0056A"] == "viga"
    tp = resumos._por_marca(nomes["tipos"])
    assert tp["W10"] == "pilar" and tp["W7"] == "viga"                 # a barra solta pelo papel (a W3 é parte do 0055A)
    # as marcas do projetista (o IFC do Tekla) nos conjuntos, não T1 / DP.1; a barra solta PL/VG, não A.L. / A.C.
    nomes_c = set(resumos._por_marca(nomes["conjuntos"]).values())
    assert nomes_c == {"0055A / 0056A"}                                  # as duas iguais, um desenho com os dois nomes
    nomes_p = resumos._por_marca(nomes["posicoes"])
    assert nomes_p["W10"].startswith("PL") and nomes_p["W7"].startswith("VG")
    X = R["dossie"]
    assert [b["chave"] for b in X["estrutura"]] == ["pilares", "vigas"]
    assert [b["titulo"] for b in X["estrutura"]] == ["Pilares", "Vigas"]
    assert {b["chave"]: b["qtd"] for b in X["estrutura"]} == {"pilares": 4, "vigas": 10}
    assert [g["grupo"] for g in R["grupos_peso"]] == ["Pilares", "Vigas"]
    t = _texto(R)
    for errado in ("caixote", "Trechos da cobertura", "gulhamento", "esoura", "Dispositivos", "Ala 1", "Transição"):
        assert errado not in t, errado
    assert "Nível do piso" in t and "+2,840 m" in t                  # o topo das vigas, não o apoio das tesouras
    assert "Vãos entre eixos" in t and "Vão 1–2" in t and "6,00 m" in t and "Vão A–B" in t and "4,00 m" in t
    # o peso não muda com o nome: o mesmo total das peças
    assert abs(sum(g["kg"] for g in R["grupos_peso"]) - R["numeros"]["peso_aco"]) < 0.5


def test_peca_curta_solta_e_o_local_dos_parafusos_pelo_papel():
    """o toco de 390 mm solto (como os A.C.2 de 0,39 m do Drugovich) é peça curta PC, não agulhamento"""
    doc = Documento(nome="mezanino")
    _mezanino(doc)
    for i in range(3):
        doc.add(Barra(nome="C", inicio=(6100.0, 500.0 + 1000.0 * i, 2715.0), fim=(6490.0, 500.0 + 1000.0 * i, 2715.0),
                      perfil="W 250×17,9", papel="", atributos=_ifc("0063A", "W12")))
    R, nomes = _resumo(doc, EIXOS)
    assert resumos._por_marca(nomes["tipos"])["W12"] == "peca_curta"
    assert resumos._por_marca(nomes["posicoes"])["W12"].startswith("PC")
    X = R["dossie"]
    pc = next(b for b in X["estrutura"] if b["chave"] == "suportes")
    assert pc["titulo"] == "Peças curtas" and pc["qtd"] == 3
    assert "Peças curtas" in [g["grupo"] for g in R["grupos_peso"]]


def test_viga_caixote_de_verdade_continua_sem_cobertura():
    """o Vicente (09/10, o usuário: "lá são as vigas caixotes"): a treliça em pé de tubos — dois banzos e montantes —
    continua viga caixote na obra sem cobertura"""
    doc = Documento(nome="residencia")
    at = lambda pos: {"marcas": {"posicao": pos, "conjunto": "V1"}}     # noqa: E731
    for z in (3000.0, 3600.0):
        doc.add(Barra(nome="B", inicio=(0.0, 0.0, z), fim=(8000.0, 0.0, z), perfil="TQ 50×50×3,0", papel="", atributos=at("BZ%d" % z)))
    for i in range(9):
        x = i * 1000.0
        doc.add(Barra(nome="M", inicio=(x, 0.0, 3000.0), fim=(x, 0.0, 3600.0), perfil="TQ 50×50×3,0", papel="", atributos=at("MT")))
    R, nomes = _resumo(doc)
    assert R["cobertura"] is False
    assert resumos._por_marca(nomes["tipos_conjuntos"])["V1"] == "tesoura"
    X = R["dossie"]
    assert [b["chave"] for b in X["estrutura"]] == ["caixote"] and X["estrutura"][0]["titulo"] == "Vigas caixote"


def test_posicao_fundida_vai_a_familia_do_tipo():
    """"0073A / 0075A" (duas marcas da mesma peça): `tipos` tem as chaves abertas e a fundida caía em "Vigas e barras" —
    as W250×32,7 do Drugovich (689,5 kg) fora das Vigas"""
    doc = Documento(nome="mezanino")
    _mezanino(doc)
    for conj, y in (("0073A", 1200.0), ("0075A", 2400.0)):
        doc.add(Barra(nome="F", inicio=(0.0, y, 2685.0), fim=(6000.0, y, 2685.0), perfil="W 250×32,7", papel="",
                      atributos=_ifc(conj, "W22")))
    R, _nomes = _resumo(doc, EIXOS)
    assert "Vigas e barras" not in [g["grupo"] for g in R["grupos_peso"]]


def test_topo_das_vigas_sem_piso():
    """o Kaefer (13/11): a quadra com 2 vigas a +8,000 e a cobertura do cliente — não é piso, é o topo das vigas"""
    doc = Documento(nome="mezanino")
    _mezanino(doc, secundarias=2)
    R, _nomes = _resumo(doc, EIXOS)
    t = _texto(R)
    assert "Nível do piso" not in t and "Topo das vigas" in t and "+2,840 m" in t


def test_obra_com_nomes_guarda_o_nome_neutro_e_troca_o_de_cobertura():
    """a obra que já tem pranchas (o Vicente: os 724 suportes B.1) guarda o nome neutro; o nome de cobertura (o A.C. das
    secundárias do Drugovich) troca pelo do papel"""
    doc = Documento(nome="mezanino")
    _mezanino(doc)
    for i in range(3):
        doc.add(Barra(nome="C", inicio=(6100.0, 500.0 + 1000.0 * i, 2715.0), fim=(6490.0, 500.0 + 1000.0 * i, 2715.0),
                      perfil="W 250×17,9", papel="", atributos=_ifc("0063A", "W12")))
    r = detalhar(doc, grupos=["localizacao"], converter=False,
                 nomes={"posicoes": {"W12": "B.1", "W7": "A.C.6", "W10": "A.L.1"}, "conjuntos": {}})
    np_ = resumos._por_marca((r.get("nomes") or {}).get("posicoes"))
    assert np_["W12"] == "B.1"
    assert np_["W7"].startswith("VG") and np_["W10"].startswith("PL")



def test_chapa_do_toco_que_era_agulhamento_guarda_o_nome():
    """VERSÃO 0.9.3 (13/11, test_predio): o conjunto barra + chapinha que antes da regra era agulhamento virou viga e a
    chapa ganhou o nome do conjunto (VG1.1) — a chumbação do Vicente dizia "4 em VG1.1" no lugar de "4 em CH1". A chapa
    fica com o nome dela; a barra leva o do conjunto. No mezanino: o toco W250 com a chapa de ponta (0063A do Drugovich)."""
    from nucleo3d.modelo import Solido
    doc = Documento(nome="mezanino")
    _mezanino(doc)
    for i in range(1):                                                 # um conjunto (a composição é por unidade)
        y = 600.0 + 1500.0 * i
        doc.add(Barra(nome="C", inicio=(6100.0, y, 2715.0), fim=(6490.0, y, 2715.0), perfil="W 250×17,9", papel="",
                      atributos=_ifc("0063A", "W30")))
        v = [(6490, y - 60, 2600), (6502, y - 60, 2600), (6502, y + 60, 2600), (6490, y + 60, 2600),
             (6490, y - 60, 2830), (6502, y - 60, 2830), (6502, y + 60, 2830), (6490, y + 60, 2830)]
        ch = Solido(nome="PL8", vertices=v, faces=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6],
                                                      [3, 0, 4, 7]], material="Aço")
        ch.atributos.update(_ifc("0063A", "PL8"))
        ch.atributos["tipo_ifc"] = "IfcPlate"
        ch.atributos["marcas"]["perfil"] = "PL 12"
        doc.add(ch)
    r = detalhar(doc, grupos=["localizacao"], converter=False)
    np_ = resumos._por_marca((r.get("nomes") or {}).get("posicoes"))
    assert np_["PL8"].startswith("CH"), np_["PL8"]
    assert resumos._por_marca((r.get("nomes") or {}).get("tipos_conjuntos"))["0063A"] == "peca_curta"

