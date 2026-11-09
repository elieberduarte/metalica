# -*- coding: utf-8 -*-
"""FAB-01, a conferência do suporte de terça no 3D (REGRAS.md; REGRAS · SISTEMA N.4, 09/11/2026). O suporte é furado
junto com a terça e vai ao corte das chapas, mas a trava R6 só olhava a terça. O Posto V2 chegou ao pacote de corte com
os suportes fora do passo da máquina três vezes em dois dias:
- 29/10, 96db66b: os 398 ST1/ST2 do gerador com o par a 40/60 mm;
- 29/10, bbb9a0e: o ST da ponta da linha com uma coluna a 50 e a outra a 40;
- 30/10: o ST1 sob a T.C.133, que sobe 22 %, com o par a 40.

Cada vez a correção foi no ajuste do gerador (`ajustar_suportes_as_tercas`), que acha a terça pela caixa do mundo, e
cada vez a terça que ele não viu passou calada. A conferência liga cada furo à terça em que o parafuso entra (o eixo do
furo dentro do sólido dela) e mede o par perpendicular a ela: 50 mm até 200 de altura, 100 acima. As pranchas (R6) e o
corte das chapas são recusados enquanto houver suporte fora. A 1ª versão (04/11, pela grade 2D dos furos, sem a terça)
acusava a placa de canto de duas longarinas que se cruzam e saiu da árvore."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Chapa, Documento                       # noqa: E402
from nucleo2d.detalhe.base import _proxy_da_barra                         # noqa: E402
from nucleo2d.detalhe.celulas import suportes_fora_da_maquina             # noqa: E402


def _terca(doc, marca="TC14", perfil="U 100×40×2,65", subida=0.0, y=0.0, z=1000.0, comprimento=3000.0, ao_longo="x"):
    """Terça de `comprimento` mm ao longo de x (ou de y), subindo `subida` (fração) ao longo dela."""
    if ao_longo == "x":
        ini, fim = (0.0, y, z), (comprimento, y, z + comprimento * subida)
    else:
        ini, fim = (y, 0.0, z), (y, comprimento, z + comprimento * subida)
    t = Barra(nome=marca, inicio=ini, fim=fim, perfil=perfil, papel="terça")
    t.camada = "Terças"
    t.atributos = {"marcas": {"posicao": marca, "perfil": perfil}}
    doc.add(t)
    return t


def _centro_da_secao(t, s):
    """O centro da seção da terça (sólido equivalente) a `s` mm do início, e (L, h): o eixo dela e a altura no plano xz."""
    pv = _proxy_da_barra(t).vertices
    L = tuple(b - a for a, b in zip(t.inicio, t.fim))
    n = math.sqrt(sum(c * c for c in L))
    L = tuple(c / n for c in L)
    sl = [sum(v[k] * L[k] for k in range(3)) for v in pv]
    c = [(max(v[k] for v in pv) + min(v[k] for v in pv)) / 2.0 for k in range(3)]
    cs = sum(c[k] * L[k] for k in range(3))
    p = tuple(c[k] + L[k] * (min(sl) + s - cs) for k in range(3))
    return p, L


def _suporte(doc, t, furos, s=1500.0, nome="Suporte de terça ST1", centro_y=45.0, alto=90.0):
    """Chapa vertical encostada na terça (no plano dela, normal em y), `furos` = [(ao longo, na altura)] a partir do
    centro da seção da terça a `s` mm do início, perpendicular a ela; a chapa de 150 × `alto` com o eixo da terça a
    `centro_y` do pé dela."""
    c, L = _centro_da_secao(t, s)
    h = (-L[2], 0.0, L[0])                                      # perpendicular à terça, no plano xz
    ch = Chapa(nome=nome, origem=tuple(c[k] - 75.0 * L[k] - centro_y * h[k] for k in range(3)), eixo_x=L, eixo_y=h,
               contorno=[(0.0, 0.0), (150.0, 0.0), (150.0, alto), (0.0, alto)], espessura=3.0, centrada=True,
               furos=[{"x": 75.0 + a, "y": centro_y + b, "largura": 25.0, "altura": 12.7} for a, b in furos])
    doc.add(ch)
    return ch


def _par(passo, entre=80.0):
    return [(a, b) for a in (-entre / 2, entre / 2) for b in (-passo / 2, passo / 2)]


@pytest.mark.parametrize("caso, furos, subida, fora", [
    ("o ST1 do projeto, par a 40 (96db66b)", _par(40), 0.0, True),
    ("o ST2 de 60 × 80: a diagonal dá 100 e não pode esconder", _par(60), 0.0, True),
    ("a ponta da linha: uma coluna a 50, a outra a 40 (bbb9a0e)",
     [(-40.0, -25.0), (-40.0, 25.0), (40.0, -20.0), (40.0, 20.0)], 0.0, True),
    ("sob a terça a 22 %, o par a 40 (30/10)", _par(40), 0.22, True),
    ("no passo: 50 × 80", _par(50), 0.0, False),
    ("no passo sob a terça a 22 %", _par(50), 0.22, False),
])
def test_suporte_de_terca_fora_do_passo_da_maquina(caso, furos, subida, fora):
    doc = Documento()
    t = _terca(doc, subida=subida)
    ch = _suporte(doc, t, furos)
    r = suportes_fora_da_maquina(doc, {"TC14"})
    assert bool(r) is fora, (caso, r)
    if fora:
        assert r[0]["ids"] == [ch.id] and "par de furos" in r[0]["texto"]


def test_terca_alta_e_no_passo_de_100():
    doc = Documento()
    t = _terca(doc, perfil="Ue 250×85×25×3,00")
    _suporte(doc, t, _par(100), centro_y=75.0, alto=150.0)
    assert suportes_fora_da_maquina(doc, {"TC14"}) == []
    doc2 = Documento()
    t2 = _terca(doc2, perfil="Ue 250×85×25×3,00")
    _suporte(doc2, t2, _par(50), centro_y=75.0, alto=150.0)
    r = suportes_fora_da_maquina(doc2, {"TC14"})
    assert r and r[0]["passos"] == [50] and r[0]["maquina"] == 100.0


@pytest.mark.parametrize("caso, centro_y, texto", [
    ("o ST1 de 90 com furo a 127, fora da chapa (Posto V2, 09/11)", 102.0, "furo fora da chapa"),
    ("o par no passo com o furo a 7 mm da borda de cima", 58.0, "furo a 7 mm da borda (mínimo "),
])
def test_furo_do_suporte_na_borda_ou_fora_da_chapa(caso, centro_y, texto):
    """Depois que o ajuste leva o par ao passo da máquina, a chapa tem de ter o furo dentro, com a borda mínima do
    parafuso (NBR 8800, Tabela 14; o 3/8" do ST com 1,5·d = 14,3): 11 suportes do Posto V2 iam ao corte com o furo na
    borda ou fora da chapa (OBRA · POSTO N.7, 09/11)."""
    doc = Documento()
    t = _terca(doc, subida=0.22)
    _suporte(doc, t, _par(50), centro_y=centro_y)
    r = suportes_fora_da_maquina(doc, {"TC14"})
    assert r and r[0]["passos"] == [] and texto in r[0]["texto"], (caso, r)


def test_furo_que_nao_entra_na_terca_nao_e_conferido():
    """Os furos de baixo do suporte vão no banzo da tesoura (a ligação), não na terça: o passo deles é da ligação."""
    doc = Documento()
    t = _terca(doc)
    _suporte(doc, t, _par(50) + [(-40.0, -95.0), (40.0, -95.0), (-40.0, -135.0), (40.0, -135.0)])
    assert suportes_fora_da_maquina(doc, {"TC14"}) == []


def test_linha_de_furos_ao_longo_da_terca_nao_e_par():
    """A "cadeirinha" da Ue 75 do Galpão Existente: 2 furos a 60 ao longo da terça, sem par na altura dela."""
    doc = Documento()
    t = _terca(doc)
    _suporte(doc, t, [(-30.0, 0.0), (30.0, 0.0)], nome="Suporte de terça (chapa)")
    assert suportes_fora_da_maquina(doc, {"TC14"}) == []


def test_placa_de_canto_de_duas_longarinas_que_se_cruzam():
    """A CH12 (M83) da Sala de Compressores: placa deitada sobre duas longarinas C127 deitadas que se cruzam no canto.
    Cada furo é da longarina em que o parafuso entra: os dois de cima da M92 são o par dela (perpendicular a ela); os
    dois da M61 estão em linha ao longo dela. A 1ª versão (grade 2D, 04/11) misturava as duas."""
    def montar(par_m92):
        doc = Documento()
        # as longarinas deitadas: alma na horizontal, 127 de largura, 50 de altura
        m92 = Solido_caixa("M92", (0.0, 127.0), (1000.0, 3000.0), (100.0, 150.0), "C127X50X17X#14")
        m61 = Solido_caixa("M61", (-2000.0, 127.0), (850.0, 1000.0), (100.0, 150.0), "U150X50X2.28")
        doc.add(m92)
        doc.add(m61)
        cx = 63.5
        furos = [(cx - par_m92 / 2, 1040.0), (cx + par_m92 / 2, 1040.0), (33.0, 960.0), (93.0, 960.0)]
        doc.add(Chapa(nome="PLATE 125x110x3", origem=(0.0, 0.0, 150.0), eixo_x=(1.0, 0.0, 0.0), eixo_y=(0.0, 1.0, 0.0),
                      contorno=[(0.0, 900.0), (127.0, 900.0), (127.0, 1100.0), (0.0, 1100.0)], espessura=3.0,
                      furos=[{"x": x, "y": y, "largura": 13.0, "altura": 25.0} for x, y in furos],
                      atributos={"marcas": {"posicao": "M83"}}))
        return doc
    assert suportes_fora_da_maquina(montar(50.0), {"M92", "M61"}, {"M83"}) == []
    r = suportes_fora_da_maquina(montar(60.0), {"M92", "M61"}, {"M83"})
    assert [f["passos"] for f in r] == [[60]]


def Solido_caixa(marca, xr, yr, zr, perfil):
    from nucleo3d.modelo import Solido
    vs = [(x, y, z) for x in xr for y in yr for z in zr]
    return Solido(nome=marca, vertices=vs, faces=[], atributos={"marcas": {"posicao": marca, "perfil": perfil}})


def test_so_o_suporte_de_terca():
    doc = Documento()
    t = _terca(doc)
    _suporte(doc, t, _par(40), nome="Placa de base CH2")
    assert suportes_fora_da_maquina(doc, {"TC14"}) == []
    # do IFC, com o nome da obra: o tipo de produção "suporte_terca" diz que é suporte
    ch = [e for e in doc.entidades.values() if isinstance(e, Chapa)][0]
    ch.atributos = {"marcas": {"posicao": "P77"}}
    assert suportes_fora_da_maquina(doc, {"TC14"}) == []
    assert len(suportes_fora_da_maquina(doc, {"TC14"}, {"P77"})) == 1


def _projeto_com_suporte_a_40(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    g = app._gerente()
    s = g.criar("Obra")["slug"]
    doc = Documento()
    t = _terca(doc)
    _suporte(doc, t, _par(40))
    g.salvar_modelo(s, doc.dict())
    monkeypatch.setattr(app, "_tipos_de_producao", lambda s_, d_: {"TC14": "terca_cobertura"})
    return app, s


def test_corte_das_chapas_recusado_com_o_suporte_fora_do_passo(tmp_path, monkeypatch):
    """O pacote de corte de 29/10 do Posto V2 saiu com os ST a 40/60, sem trava nenhuma."""
    app, s = _projeto_com_suporte_a_40(tmp_path, monkeypatch)
    with pytest.raises(app.ErroDeDados) as e:
        app.corte_das_chapas(s)
    assert "suporte(s) de terça" in str(e.value) and "40" in str(e.value)
    assert e.value.pecas and e.value.pecas[0]["ids"]
    assert not os.path.exists(os.path.join(app._gerente()._existente(s), "detalhamento", "corte-chapas.zip"))


def test_pranchas_recusadas_com_o_suporte_fora_do_passo(tmp_path, monkeypatch):
    """A R6: o carimbo do Detalhar com o suporte fora recusa a emissão, com o "Ver no 3D" da peça."""
    app, s = _projeto_com_suporte_a_40(tmp_path, monkeypatch)
    from nucleo2d.desenho import Desenho
    vivos = app._vivos()
    sup = [{"nome": "Suporte de terça ST1", "marca": "Suporte de terça ST1", "passos": [40], "maquina": 50.0,
            "ids": ["e1"], "texto": "Suporte de terça ST1: par de furos a 40 mm"}]
    vivos.gravar_carimbo(s, {}, extra={"suportes_fora_da_maquina": [sup[0]["texto"]], "suportes_fora_da_maquina_pecas": sup})
    monkeypatch.setattr(vivos, "por_que_velho", lambda s_: "")
    d = Desenho()
    d.metadados["prancha"] = True
    with pytest.raises(app.ErroDeDados) as e:
        app._conferir_para_emitir(s, [d])
    assert "suporte(s) de terça" in str(e.value)
    assert e.value.pecas == sup
    assert vivos.estado(s, conferir=False)["suportes_fora_da_maquina_pecas"] == sup


def test_detalhar_acusa_o_suporte_que_o_gerador_nao_acertou(tmp_path, monkeypatch):
    """O Detalhar grava no carimbo os suportes fora — o caminho até a R6 e o aviso do CAD."""
    app, s = _projeto_com_suporte_a_40(tmp_path, monkeypatch)
    monkeypatch.setattr(app, "_suportes_fora_da_maquina",
                        lambda doc, tipos: [{"nome": "X", "marca": "X", "passos": [40], "maquina": 50.0, "ids": ["e1"],
                                             "texto": "X: par de furos a 40 mm"}])
    app.detalhar_projeto(s, {"grupos": ["chapas"]}) if hasattr(app, "detalhar_projeto") else pytest.skip("sem a rota")
    assert app._vivos().estado(s, conferir=False)["suportes_fora_da_maquina"] == ["X: par de furos a 40 mm"]
