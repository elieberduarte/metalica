# -*- coding: utf-8 -*-
"""Regras de montagem das tesouras (nucleo3d/regras_trelica.py) — recriadas e aprovadas pelo usuário em 16/10
(Projeto/ANALISES/Montagem/Regras-de-montagem-das-tesouras-revisao-geral-2026-10-16.docx): "o sistema continua gerando
peças com perfil errado, aleatório… toda vez que gera uma tesoura nova volta com a configuração antiga".

Cada gerador chama `regras_trelica.aplicar` antes do encaixe de fábrica; aqui cada caminho gera uma treliça e `conferir`
tem de voltar vazio. Os caminhos: a tesoura pelo desenho (de_planta_estrutura), a treliça entre banzos do editor 3D
(modelagem.trelica), o galpão treliçado (de_projeto), o projeto recebido pela planta (de_planta, o Posto) e o 3D pelos
quadros (de_quadros). Os testes unitários cobrem cada regra numerada (1.2, 1.4, 2.2–2.5) e as decisões do usuário."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

from nucleo3d import regras_trelica as R                                    # noqa: E402
from nucleo3d.geometria import base_local                                   # noqa: E402
from nucleo3d.modelo import Barra, Documento                                # noqa: E402

U_BZ = "U 150×50×3,00 (FF)"
U_AL = "U 100×40×2,65"
L_AL = 'L 1½"×1/8"'
N = (1.0, 0.0, 0.0)                                   # a normal do plano x = 0 (sinal fixo)


def _boca(b):
    return base_local(b.direcao, b.rotacao)[0]


def _deitada(b):
    return R._aba_deitada(b, N)


def _regras(bs):
    return {e["regra"] for e in R.conferir(bs)}


def _tesoura_a_mao(giro_banzo=0.0, giro_alma_u=0.0, l_alternada=True, ponta_alta=None):
    """uma tesoura plana em y-z (x = 0), 6 m × 1 m: banzos em U, montantes de ponta e do meio em U, diagonais em U e em L;
    os giros dados de propósito fora da regra (o giro 0 de quem não orienta, a cantoneira pelo sentido do desenho).
    `ponta_alta` = "y0" ou "y1" levanta o banzo de cima naquela ponta (a ponta alta da tesoura)"""
    at = {"origem": {"peca": "TT"}}
    z0, z1 = 1000, 1000
    if ponta_alta == "y0":
        z0 = 1300
    elif ponta_alta == "y1":
        z1 = 1300
    bs = [Barra(nome="BS", inicio=(0, 0, z0), fim=(0, 6000, z1), perfil=U_BZ, papel="banzo", rotacao=giro_banzo,
                atributos=dict(at, papel_trelica="banzo_sup")),
          Barra(nome="BI", inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=U_BZ, papel="banzo", rotacao=giro_banzo,
                atributos=dict(at, papel_trelica="banzo_inf"))]

    def ztopo(y):
        return z0 + (z1 - z0) * y / 6000.0
    for y in (0, 3000, 6000):                         # os montantes em U: as duas pontas (o canto) e o do meio
        bs.append(Barra(nome="M%d" % y, inicio=(0, y, 0), fim=(0, y, ztopo(y)), perfil=U_AL, papel="montante",
                        rotacao=giro_alma_u, atributos=dict(at)))
    for k, (y0, y1) in enumerate(((0, 1500), (1500, 3000))):
        bs.append(Barra(nome="DU%d" % k, inicio=(0, y0, ztopo(y0)), fim=(0, y1, 0), perfil=U_AL, papel="diagonal",
                        rotacao=giro_alma_u, atributos=dict(at)))
    for k, (y0, y1) in enumerate(((3000, 4500), (6000, 4500), (4500, 4500))):
        a, b = (0, y0, 0), (0, y1, ztopo(y1))
        if l_alternada and k % 2:
            a, b = b, a                               # desenhada ao contrário: sem a regra, a aba vai para o outro lado
        bs.append(Barra(nome="DL%d" % k, inicio=a, fim=b, perfil=L_AL, papel="montante" if k == 2 else "diagonal",
                        rotacao=0.0, atributos=dict(at)))
    return bs


def _por_nome(bs):
    return {b.nome: b for b in bs}


# ------------------------------------------------------------------ as regras, uma a uma
def test_conferir_acusa_cada_regra_e_aplicar_corrige():
    bs = _tesoura_a_mao(giro_banzo=0.0, giro_alma_u=0.0)
    regras = _regras(bs)
    # 1.4 (pontas sem o perfil do banzo), 2.2 (banzo de boca para fora do plano), 2.3 (alma), 2.4 (cantoneira de um lado e do outro)
    assert {"1.4", "2.2", "2.3", "2.4"} <= regras, regras
    n_class, n_giro, _n, _e = R.aplicar(bs)
    assert n_class == 2 and n_giro > 0
    assert R.conferir(bs) == []
    assert R.aplicar(bs) == (0, 0, 0, 0)              # idempotente: rodar de novo não mexe em nada


def test_1_4_ponta_recebe_o_perfil_do_banzo():
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    por = _por_nome(bs)
    assert por["M0"].perfil == U_BZ and por["M6000"].perfil == U_BZ
    assert por["M3000"].perfil == U_AL                # o montante do meio não é ponta
    assert por["DU0"].perfil == U_AL


def test_1_4_a_legenda_do_projeto_manda():
    """regime 0.1: a peça com o perfil da legenda (perfil_do_projeto) não muda, nem é acusada"""
    bs = _tesoura_a_mao()
    por = _por_nome(bs)
    por["M0"].atributos["perfil_do_projeto"] = True
    R.aplicar(bs)
    assert por["M0"].perfil == U_AL and por["M6000"].perfil == U_BZ
    assert not [e for e in R.conferir(bs) if e["nome"] == "M0"]


def test_2_1_e_2_2_banzos_abrem_para_dentro():
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    por = _por_nome(bs)
    assert _boca(por["BS"])[2] == pytest.approx(-1.0, abs=1e-6)      # o de cima para baixo
    assert _boca(por["BI"])[2] == pytest.approx(1.0, abs=1e-6)       # o de baixo para cima
    for nome in ("BS", "BI", "M0", "M3000", "DU0"):                  # 2.1: a altura do perfil atravessa o plano
        assert abs(base_local(por[nome].direcao, por[nome].rotacao)[1][0]) == pytest.approx(1.0, abs=1e-6), nome


def test_2_2_banzo_intermediario_abre_para_cima():
    """decisão 3: o banzo com alma chegando dos dois lados abre para cima"""
    bs = _tesoura_a_mao()
    at = {"origem": {"peca": "TT"}}
    # um segundo painel em cima do primeiro: o banzo de cima vira intermediário (montantes acima e abaixo dele)
    bs.append(Barra(nome="BT", inicio=(0, 0, 2000), fim=(0, 6000, 2000), perfil=U_BZ, papel="banzo", atributos=dict(at)))
    for y in (0, 3000, 6000):
        bs.append(Barra(nome="MT%d" % y, inicio=(0, y, 1000), fim=(0, y, 2000), perfil=U_AL, papel="montante", atributos=dict(at)))
    bs.append(Barra(nome="DT", inicio=(0, 0, 2000), fim=(0, 3000, 1000), perfil=U_AL, papel="diagonal", atributos=dict(at)))
    R.aplicar(bs)
    por = _por_nome(bs)
    assert _boca(por["BS"])[2] > 0.99                                # intermediário: para cima
    assert _boca(por["BT"])[2] < -0.99                               # o novo contorno de cima: para baixo
    assert R.conferir(bs) == []


def test_2_3_alma_abre_para_o_meio_e_diagonal_nunca_para_cima():
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    por = _por_nome(bs)
    assert _boca(por["M0"])[1] > 0.99                                # a ponta abre para dentro
    assert _boca(por["M6000"])[1] < -0.99
    for k in (0, 1):                                                 # decisão 1: a diagonal nunca para cima
        assert _boca(por["DU%d" % k])[2] < -0.3, (k, _boca(por["DU%d" % k]))
    # a diagonal "para cima" é acusada pela 2.3
    por["DU0"].rotacao = (por["DU0"].rotacao + 180.0) % 360.0
    assert any(e["regra"] == "2.3" and e["nome"] == "DU0" for e in R.conferir(bs))


@pytest.mark.parametrize("alta, sinal", [("y1", 1.0), ("y0", -1.0), (None, 1.0)])
def test_2_3_montante_no_meio_abre_para_a_ponta_alta(alta, sinal):
    """decisão 4: o montante no meio exato do vão abre para a ponta alta (tesoura reta: +eixo)"""
    bs = _tesoura_a_mao(ponta_alta=alta)
    R.aplicar(bs)
    assert _boca(_por_nome(bs)["M3000"])[1] * sinal > 0.99


def test_2_4_cantoneira_simples_e_um_u_cortado_ao_meio():
    """decisão 5: a aba de pé sempre para +n (o mesmo lado em toda a obra); a aba deitada para onde a boca do U iria"""
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    por = _por_nome(bs)
    for k in range(3):
        assert R.lado_da_aba(por["DL%d" % k], N) == 1, k
    assert _deitada(por["DL2"])[1] < -0.99                           # o montante em L (y 4500, à direita do meio): para o meio
    for k in (0, 1):                                                 # as diagonais em L: a aba deitada para baixo
        assert _deitada(por["DL%d" % k])[2] < -0.3, (k, _deitada(por["DL%d" % k]))
    # do outro lado do plano: acusada pela 2.4 com 180°
    por["DL0"].rotacao = (por["DL0"].rotacao + 180.0) % 360.0
    assert any(e["regra"] == "2.4" and e["nome"] == "DL0" and e["erro_graus"] == 180.0 for e in R.conferir(bs))


def test_2_5_cantoneira_em_par_e_um_u_partido():
    """o par: uma de cada lado do plano, as abas de pé para o centro e as deitadas as duas na direção da boca"""
    bs = _tesoura_a_mao()
    at = {"origem": {"peca": "TT"}}
    a = Barra(nome="PA", inicio=(-30, 1500, 0), fim=(-30, 3000, 1000), perfil=L_AL, papel="diagonal", rotacao=0.0, atributos=dict(at))
    b = Barra(nome="PB", inicio=(30, 3000, 1000), fim=(30, 1500, 0), perfil=L_AL, papel="diagonal", rotacao=0.0, atributos=dict(at))
    bs += [a, b]
    assert any(e["regra"] == "2.5" for e in R.conferir(bs))
    R.aplicar(bs)
    assert R.conferir(bs) == []
    assert R.lado_da_aba(a, N) == 1 and R.lado_da_aba(b, N) == -1  # para o centro: a de x<0 aponta +x, a de x>0 aponta −x
    da, db = _deitada(a), _deitada(b)
    assert da[2] < -0.3 and db[2] < -0.3                             # a diagonal: nunca para cima
    assert abs(da[1] - db[1]) < 1e-6 and abs(da[2] - db[2]) < 1e-6  # as duas na mesma direção


def test_1_2_topo_do_painel_de_ponta_vira_banzo():
    """a ponta da tesoura do anexo do Mercado Hermes (16/10): o painel de ponta com um X, e a peça de cima dele veio do
    desenho como "diagonal" (horizontal, no topo do painel). Decisão 2: vira banzo superior, com o perfil do banzo, e
    abre para baixo"""
    at = {"origem": {"peca": "TX"}}
    U1, U2 = "U 150×60×3,00 (FF)", "U 100×50×3,00 (FF)"
    pts = [((0, 0, 0), (0, 400, 0), U2, "montante"), ((0, 0, 0), (0, 0, 400), U1, "banzo"),
           ((0, 0, 0), (0, 400, 400), U2, "diagonal"), ((0, 0, 400), (0, 400, 0), U2, "diagonal"),
           ((0, 0, 400), (0, 400, 400), U2, "diagonal"),                       # o topo do painel, como veio
           ((0, 400, 0), (0, 400, 450), U2, "montante"), ((0, 400, 0), (0, 2000, 0), U1, "banzo"),
           ((0, 400, 450), (0, 2000, 550), U1, "banzo"), ((0, 2000, 0), (0, 2000, 550), U2, "montante"),
           ((0, 400, 450), (0, 2000, 0), U2, "diagonal")]
    bs = [Barra(nome="P%d" % k, inicio=a, fim=b, perfil=perfil, papel=papel, rotacao=0.0, atributos=dict(at))
          for k, (a, b, perfil, papel) in enumerate(pts)]
    topo = bs[4]
    topo.rotacao = R._giro_para(topo.direcao, (0.0, 0.0, 1.0))         # de boca para cima, como saiu
    assert any(e["regra"] == "1.2" and e["nome"] == topo.nome for e in R.conferir(bs))
    R.aplicar(bs)
    assert topo.papel == "banzo" and topo.atributos["papel_trelica"] == "banzo_sup" and topo.perfil == U1
    assert _boca(topo)[2] < -0.99
    assert bs[8].perfil == U1 and bs[0].perfil == U2                     # 1.4: a ponta em U do banzo; o montante do painel não
    assert R.conferir(bs) == []
    assert _boca(bs[6])[2] > 0.99                                        # o banzo de baixo continua para cima


def test_2_7_boca_virada_pelo_usuario_fica():
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    m = next(b for b in bs if b.nome == "M3000")
    m.rotacao = (m.rotacao + 180.0) % 360.0
    m.atributos["boca_virada"] = True                 # o "virar" do painel Perfis da tesoura
    assert R.conferir(bs) == []
    giro = m.rotacao
    R.aplicar(bs)
    assert m.rotacao == giro


def test_2_8_presilha_e_secundaria_ficam_fora():
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    at = {"origem": {"peca": "TT"}}
    bs.append(Barra(nome="PR", inicio=(-30, 2000, 400), fim=(30, 2000, 400), perfil=L_AL, papel="presilha", rotacao=0.0,
                    atributos=dict(at, papel_trelica="presilha")))
    bs.append(Barra(nome="SEC", inicio=(40, 1000, 200), fim=(40, 5000, 200), perfil=L_AL, papel="diagonal", rotacao=33.0,
                    atributos=dict(at, um_lado_so=True)))
    assert R.conferir(bs) == []


# ------------------------------------------------------------------ cada gerador
def _sem_erros(barras, por_grupo=True):
    erros = R.conferir(barras, por_grupo=por_grupo)
    assert erros == [], "\n".join("%s %s %s: %s %.0f°" % (e["regra"], e["nome"], e["perfil"], e["papel"], e["erro_graus"])
                                  for e in erros[:20])


# a T1 do Docas (test_premoldado_trelica): banzos e pontas em linha dupla, alma em linha simples
BARRAS_DOCAS = [
    [0, 350, 0, 0, "montante"], [50, 329, 50, 50, "montante"],
    [0, 0, 4750, 0, "banzo_inf"], [4700, 50, 50, 50, "diagonal"],
    [4750, 1400, 350, 700, "banzo_sup"], [4700, 1341, 374, 653, "diagonal"],
    [350, 700, 0, 350, "diagonal"], [374, 653, 50, 329, "diagonal"],
    [4750, 0, 4750, 1400, "montante"], [4700, 50, 4700, 1341, "montante"],
    [902, 0, 449, 716, "diagonal"], [449, 716, 449, 0, "montante"], [1810, 0, 1356, 860, "diagonal"],
]
# a tesoura em linha de centro com a alma em U (o CD Bom Dia, 11/10): montantes de ponta, um no meio e diagonais
BARRAS_LC = [
    [0, 0, 6000, 0, "banzo_inf"], [0, 1000, 6000, 1000, "banzo_sup"],
    [0, 0, 0, 1000, "extremidade"], [6000, 0, 6000, 1000, "extremidade"],
    [3000, 0, 3000, 1000, "montante"], [1500, 0, 1500, 1000, "montante"], [4500, 0, 4500, 1000, "montante"],
    [0, 1000, 1500, 0, "diagonal"], [1500, 0, 3000, 1000, "diagonal"],
    [3000, 1000, 4500, 0, "diagonal"], [4500, 0, 6000, 1000, "diagonal"],
]


@pytest.mark.parametrize("caso", ["docas", "docas_dupla", "alma_u", "alma_u_em_x"])
def test_tesoura_pelo_desenho(caso):
    from nucleo2d.desenho import Desenho, Linha
    from nucleo3d import de_planta_estrutura as P
    if caso.startswith("docas"):
        barras, perfis = BARRAS_DOCAS, {"banzo_sup": U_BZ, "banzo_inf": U_BZ, "diagonal": L_AL}
    else:
        barras = BARRAS_LC
        perfis = {"banzo_sup": U_BZ, "banzo_inf": U_BZ, "extremidade": U_BZ, "diagonal": U_AL, "montante": U_AL}
    # a linha da planta em y (plano x = 0) ou em x (plano y = 0): a regra não pode depender da direção
    a, b = ((0.0, 0.0), (6000.0, 0.0)) if caso.endswith("em_x") else ((0.0, 0.0), (0.0, 4750.0 if caso.startswith("docas") else 6000.0))
    des = Desenho(nome="planta")
    des.add(Linha(a=a, b=b, camada="ESTRUTURA",
                  atributos={"elemento": "trelica", "material": "aco", "marca": "T1", "perfis": perfis,
                             "cantoneira": "dupla" if caso == "docas_dupla" else "simples", "nivel_base": 5000,
                             "desenho": {"barras": barras, "vao": 4750 if caso.startswith("docas") else 6000,
                                         "altura": 1400}}))
    doc, avisos = P.modelo_da_planta(des, [])
    bs = [e for e in doc.entidades.values() if e.tipo == "barra"]
    assert len(bs) > 5
    _sem_erros(bs)


@pytest.mark.parametrize("perfil_alma", [U_AL, L_AL])
def test_trelica_entre_banzos_do_editor(perfil_alma):
    from nucleo3d import modelagem
    sup = Barra(nome="BS", inicio=(0, 0, 1000), fim=(6000, 0, 1000), perfil=U_AL, papel="banzo")
    inf = Barra(nome="BI", inicio=(0, 0, 0), fim=(6000, 0, 0), perfil=U_AL, papel="banzo")
    doc = Documento()
    doc.add(sup)
    doc.add(inf)
    r = modelagem.trelica(doc, [sup.id, inf.id], {"tipo": "pratt", "passo": 1000, "perfil_montante": perfil_alma})
    for bz in (sup, inf):
        bz.rotacao = r["alterar"].get(bz.id, {}).get("rotacao", bz.rotacao)
    novas = [Barra(**{k: v for k, v in e.items() if k != "tipo"}) for e in r["novas"]]
    _sem_erros([sup, inf] + novas, por_grupo=False)


def test_galpao_trelicado():
    from test_3d_projeto import _cap16
    from nucleo.galpao import dimensionar
    from nucleo3d import de_projeto as dp
    doc = dp.modelo_do_galpao(dimensionar(_cap16(tipo_portico="treliçado", base_rotulada=False)))
    ts = R.trelicas(doc.entidades.values())
    assert len(ts) >= 9                               # uma por pórtico
    _sem_erros(list(doc.entidades.values()))


def test_projeto_recebido_pela_planta():
    import test_de_planta as T
    from nucleo3d import de_planta
    ents = T.planta() + T.locacao() + T.plantas_das_tercas() + T.baloes(0, 0) + T.baloes(T.DX_LOC, 0) + T.baloes(0, T.DY_TER)
    ents += T.elevacao_tesoura(0.0, -120000.0) + T.elevacao_painel(20000.0, -120000.0)
    r = de_planta.montar(ents, {"nivel": 6000.0, "origem": False})
    doc = r["doc"] if isinstance(r, dict) else r[0]
    assert R.trelicas(doc.entidades.values())
    _sem_erros(list(doc.entidades.values()))


def test_3d_pelos_quadros():
    import test_leitura_quadros as T
    from nucleo3d import de_quadros
    r = de_quadros.gerar(T._montagem(ligacoes={"suporte_terca": "ST1", "base_pilar": "APOIO-CONCRETO"}))
    _sem_erros(list(r["doc"].entidades.values()))


def test_conferencia_do_3d_e_verificar_apoios_acusam():
    """o modelo que já existe (importado, de script, de antes da regra) mostra a peça fora da regra na conferência"""
    from nucleo3d import conferencia_3d
    doc = Documento()
    for b in _tesoura_a_mao():
        doc.add(b)
    conf = conferencia_3d.conferir(doc, telha=False, soltas=False)
    assert conf["contagens"]["fora_da_posicao"] > 0
    assert any(a["tipo"] == "posicao" and "regra 2." in a["texto"] for a in conf["apontamentos"])
    assert any(a["tipo"] == "posicao" and "regra 1.4" in a["texto"] for a in conf["apontamentos"])
    R.aplicar(doc.entidades.values())
    assert conferencia_3d.conferir(doc, telha=False, soltas=False)["contagens"]["fora_da_posicao"] == 0


# ------------------------------------------------------------------ 4.8: a tesoura para na face interna da platibanda
def _painel(x, y0, y1, z0=1000, z1=2500, nome="P"):
    """uma platibanda em pé no plano x = const (U 100: 50 mm para cada lado do plano), de y0 a y1"""
    at = {"origem": {"peca": nome}}
    U = "U 100×50×3,00 (FF)"
    bs = [Barra(nome=nome + " BI", inicio=(x, y0, z0), fim=(x, y1, z0), perfil=U, papel="banzo", atributos=dict(at)),
          Barra(nome=nome + " BS", inicio=(x, y0, z1), fim=(x, y1, z1), perfil=U, papel="banzo", atributos=dict(at))]
    for y in range(int(y0), int(y1) + 1, 1500):
        bs.append(Barra(nome=nome + " M%d" % y, inicio=(x, y, z0), fim=(x, y, z1), perfil=U, papel="montante", atributos=dict(at)))
    bs.append(Barra(nome=nome + " D", inicio=(x, y0, z0), fim=(x, y0 + 1500, z1), perfil=U, papel="diagonal", atributos=dict(at)))
    return bs


def _tesoura_em_x(x0, x1, y, nome="T", z0=1500, z1=2000):
    """uma tesoura em pé no plano y = const, de x0 a x1 (ponta em x0): banzos U 150, ponta e alma U 100"""
    at = {"origem": {"peca": nome}}
    bs = [Barra(nome=nome + " BI", inicio=(x0, y, z0), fim=(x1, y, z0), perfil=U_BZ, papel="banzo", atributos=dict(at, papel_trelica="banzo_inf")),
          Barra(nome=nome + " BS", inicio=(x0, y, z1), fim=(x1, y, z1 + 300), perfil=U_BZ, papel="banzo", atributos=dict(at, papel_trelica="banzo_sup")),
          Barra(nome=nome + " P0", inicio=(x0, y, z0), fim=(x0, y, z1), perfil=U_BZ, papel="montante", atributos=dict(at)),
          Barra(nome=nome + " P1", inicio=(x1, y, z0), fim=(x1, y, z1 + 300), perfil=U_BZ, papel="montante", atributos=dict(at)),
          Barra(nome=nome + " D0", inicio=(x0, y, z1), fim=(x0 + 1500, y, z0), perfil=U_AL, papel="diagonal", atributos=dict(at)),
          Barra(nome=nome + " M1", inicio=(x0 + 1500, y, z0), fim=(x0 + 1500, y, z1 + 100), perfil=U_AL, papel="montante", atributos=dict(at)),
          Barra(nome=nome + " D1", inicio=(x0 + 1500, y, z1 + 100), fim=(x0 + 3000, y, z0), perfil=U_AL, papel="diagonal", atributos=dict(at)),
          Barra(nome=nome + " M2", inicio=(x0 + 3000, y, z0), fim=(x0 + 3000, y, z1 + 200), perfil=U_AL, papel="montante", atributos=dict(at))]
    return bs


def test_4_8_tesoura_para_na_face_interna_da_platibanda():
    """usuário, 16/10 (Mercado Hermes, tesoura da ala entrando no painel oeste): "o final da tesoura nunca pode invadir a
    platibanda, deve sempre parar na face interna". O painel em x = 2900 (U 100: a face interna em 2950); a tesoura vinha
    até x = 2850 — 50 mm além do eixo do painel"""
    painel = _painel(2900.0, 0.0, 9000.0)
    tes = _tesoura_em_x(2850.0, 8850.0, 4500.0)
    bs = painel + tes
    R.classificar(bs)
    R.orientar(bs)
    inv = R.conferir(bs)
    assert {e["nome"] for e in inv if e["regra"] == "4.8"} >= {"T BI", "T BS", "T P0", "T D0"}, inv
    assert not [e for e in inv if e["regra"] == "4.8" and e["nome"].startswith("P ")]   # a platibanda não é acusada
    n = R.recuar(bs)
    assert n >= 4
    por = _por_nome(bs)
    face = 2950.0
    # o montante de ponta: a face externa (a alma do U, que está do lado do painel) na face interna do painel
    ext = R._extensao(por["T P0"], (-1.0, 0.0, 0.0))
    assert por["T P0"].inicio[0] == pytest.approx(face + ext, abs=0.01)
    assert por["T P0"].fim[0] == pytest.approx(face + ext, abs=0.01)
    # os banzos e a diagonal param no eixo do montante de ponta (o recuo é pela normal: só encurtam, o z não muda)
    for nome in ("T BI", "T BS", "T D0"):
        assert por[nome].inicio[0] == pytest.approx(face + ext, abs=0.01), nome
    assert por["T BS"].inicio[2] == 2000.0 and por["T BI"].fim[0] == 8850.0
    assert por["T P0"].fim == por["T BS"].inicio and por["T P0"].inicio == por["T BI"].inicio   # os nós continuam nós
    # nada da tesoura além da face; a platibanda intacta; rodar de novo não mexe; com o encaixe, conferir limpo
    assert not [e for e in R.conferir(bs) if e["regra"] == "4.8"]
    assert all(b.inicio[0] == 2900.0 and b.fim[0] == 2900.0 for b in painel)
    assert R.recuar(bs) == 0
    R.aplicar(bs)
    assert R.conferir(bs) == []


def test_4_8_so_recua_nunca_prolonga_e_ignora_quem_atravessa():
    # a tesoura que termina 300 mm antes do painel fica como está
    bs = _painel(2900.0, 0.0, 9000.0) + _tesoura_em_x(3250.0, 9250.0, 4500.0)
    R.classificar(bs)
    R.orientar(bs)
    assert not [e for e in R.conferir(bs) if e["regra"] == "4.8"]
    assert R.recuar(bs) == 0
    assert _por_nome(bs)["T P0"].inicio[0] == 3250.0
    # a treliça que atravessa a outra (a viga de transição no meio da tesoura contínua) não é "a que chega"
    bs = _painel(6000.0, 0.0, 9000.0, nome="VT") + _tesoura_em_x(0.0, 12000.0, 4500.0)
    R.classificar(bs)
    R.orientar(bs)
    assert not [e for e in R.conferir(bs) if e["regra"] == "4.8"]
    assert R.recuar(bs) == 0
    # dois painéis que se encontram no canto: nenhum passa pelo outro — é a meia-esquadria (3.1), não a 4.8
    bs = _painel(0.0, 0.0, 6000.0, nome="PA") + [Barra(nome="PB " + b.nome[2:], inicio=(b.inicio[1], 0.0, b.inicio[2]),
                                                      fim=(b.fim[1], 0.0, b.fim[2]), perfil=b.perfil, papel=b.papel,
                                                      atributos={"origem": {"peca": "PB"}}) for b in _painel(0.0, 0.0, 6000.0)]
    R.classificar(bs)
    R.orientar(bs)
    assert not [e for e in R.conferir(bs) if e["regra"] == "4.8"]


# ------------------------------------------------------------------ 3.1: nada atravessa o banzo
def test_3_1a_ponta_que_fura_o_banzo_e_acusada_e_aplicar_encaixa():
    """usuário, 16/10 (Mercado Hermes, montado por script): "algumas diagonais não passaram a regra dos recortes, ainda
    estão com a ponta furando o banzo" — as almas iam de eixo a eixo e o encaixe nunca rodou. Agora o encaixe é parte de
    `aplicar` e a conferência acusa a ponta sem corte"""
    from nucleo3d.geometria import malha_barra
    bs = _tesoura_a_mao()
    R.classificar(bs)
    R.orientar(bs)                                     # posição certa, mas sem o encaixe (como o script deixava)
    furos = [e for e in R.conferir(bs) if e["regra"] == "3.1"]
    # as diagonais: a quina da ponta inclinada desce além da face (o montante reto em U entra na boca e para no nó,
    # acima da alma do banzo: não fura); as pontas em U 150, da largura do banzo, também
    assert {e["nome"] for e in furos} >= {"DU0", "DU1", "M0", "M6000"}, furos
    assert "M3000" not in {e["nome"] for e in furos}
    assert all(e["mm"] > 0 for e in furos)
    *_resto, n_enc = R.aplicar(bs)
    assert n_enc > 0
    assert R.conferir(bs) == []
    # a malha da alma não passa da face de dentro da alma do banzo (a alma em U entra na boca dele e para nela): a de
    # baixo do banzo de baixo + a espessura, a de cima do banzo de cima − a espessura
    por = _por_nome(bs)
    esp = 3.0
    alma_bi = min(q[2] for q in malha_barra(por["BI"])[0]) + esp
    alma_bs = max(q[2] for q in malha_barra(por["BS"])[0]) - esp
    for nome in ("M3000", "DU0", "DU1"):
        vs, _ = malha_barra(por[nome])
        assert min(q[2] for q in vs) >= alma_bi - 0.5, (nome, min(q[2] for q in vs), alma_bi)
        assert max(q[2] for q in vs) <= alma_bs + 0.5, (nome, max(q[2] for q in vs), alma_bs)


def test_3_1b_trecho_de_montante_todo_dentro_do_banzo_e_absorvido():
    """Mercado Hermes (T.2, T.3, P.12): o montante partido em dois no nó de cima deixava um trecho de 50–74 mm todo dentro
    do banzo — o encaixe não corta mais que 35% da peça e o trecho ficava furando"""
    bs = _tesoura_a_mao()
    por = _por_nome(bs)
    m = por["M3000"]                                   # 0 → 1000: parte em 950 e 950 → 1000 (o trecho de 50 mm)
    m.fim = (0, 3000, 950)
    toco = Barra(nome="M3000b", inicio=(0, 3000, 950), fim=(0, 3000, 1000), perfil=U_AL, papel="montante",
                 rotacao=m.rotacao, atributos=dict(m.atributos))
    bs.append(toco)
    R.aplicar(bs)
    dentro = [e for e in R.conferir(bs) if e["regra"] == "3.1" and e["nome"] == "M3000b"]
    assert dentro and dentro[0]["mm"] < 0               # acusado como peça toda dentro do banzo
    absorvidos = R.juntar_trechos(bs)
    assert absorvidos == [toco]
    assert m.fim == (0, 3000, 1000)                     # o montante vai de banzo a banzo
    bs.remove(toco)
    R.aplicar(bs)
    assert R.conferir(bs) == []


def test_3_1b_emenda_com_outra_peca_chegando_e_no_nao_se_junta():
    """a emenda com outra peça chegando é um nó: o montante de baixo não se estende; o trecho todo dentro do banzo só sai"""
    bs = _tesoura_a_mao()
    por = _por_nome(bs)
    m = por["M3000"]
    m.fim = (0, 3000, 950)
    toco = Barra(nome="M3000b", inicio=(0, 3000, 950), fim=(0, 3000, 1000), perfil=U_AL, papel="montante",
                 rotacao=m.rotacao, atributos=dict(m.atributos))
    bs.append(toco)
    bs.append(Barra(nome="X", inicio=(0, 3000, 950), fim=(0, 4000, 0), perfil=U_AL, papel="diagonal",
                    atributos=dict(m.atributos)))
    assert R.juntar_trechos(bs) == [toco]
    assert m.fim == (0, 3000, 950)


def test_3_1b_degrau_entre_dois_banzos_sai():
    """o corte CC do Mercado Hermes (MT.1/MT.2): o topo do painel de ponta em z 0 e o banzo inclinado começando 50 mm
    acima, ligados por um "montante" de 50 mm que fica todo dentro dos dois U 150 — não é peça"""
    at = {"origem": {"peca": "DG"}}
    U1 = "U 150×60×4,75 (FF)"
    U2 = "U 100×50×3,00 (FF)"
    bs = [Barra(nome="BI", inicio=(0, 0, -850), fim=(0, 1500, -850), perfil=U1, papel="banzo", atributos=dict(at)),
          Barra(nome="TOPO", inicio=(0, 0, 0), fim=(0, 400, 0), perfil=U1, papel="banzo", atributos=dict(at)),
          Barra(nome="BS", inicio=(0, 400, 50), fim=(0, 1500, 150), perfil=U1, papel="banzo", atributos=dict(at)),
          Barra(nome="PONTA", inicio=(0, 0, -850), fim=(0, 0, 0), perfil=U1, papel="montante", atributos=dict(at)),
          Barra(nome="M", inicio=(0, 400, -850), fim=(0, 400, 0), perfil=U2, papel="montante", atributos=dict(at)),
          Barra(nome="DEGRAU", inicio=(0, 400, 0), fim=(0, 400, 50), perfil=U2, papel="montante", atributos=dict(at)),
          Barra(nome="D", inicio=(0, 400, 50), fim=(0, 1500, -850), perfil=U2, papel="diagonal", atributos=dict(at)),
          Barra(nome="P2", inicio=(0, 1500, -850), fim=(0, 1500, 150), perfil=U1, papel="montante", atributos=dict(at))]
    R.aplicar(bs)
    assert any(e["regra"] == "3.1" and e["nome"] == "DEGRAU" and e["mm"] < 0 for e in R.conferir(bs))
    absorvidos = R.juntar_trechos(bs)
    assert [b.nome for b in absorvidos] == ["DEGRAU"]
    assert _por_nome(bs)["M"].fim == (0, 400, 0)          # o montante de baixo não se estende (o nó tem banzo e diagonal)
    bs = [b for b in bs if b.nome != "DEGRAU"]
    R.aplicar(bs)
    assert R.conferir(bs) == []


# ------------------------------------------------------------------ 19/10: o que passava na regra (Mercado, faixa norte)
def _tesoura_com_degrau(degrau=40.0, montante_ate_o_no=True):
    """uma tesoura em y-z (x = 0) com o degrau no banzo de cima como a tesourinha da faixa norte do Mercado: o trecho
    inclinado termina em z 950 e o plano da ponta começa degrau mm abaixo. U 150×50: a seção tem 50 mm no plano, então
    um degrau menor que isso põe o material de um banzo dentro do outro"""
    at = {"origem": {"peca": "TD"}}
    zb = 950.0 - degrau
    topo_m = zb if montante_ate_o_no else zb - 50.0
    return [Barra(nome="BI", inicio=(0, 0, 0), fim=(0, 3000, 0), perfil=U_BZ, papel="banzo", atributos=dict(at, papel_trelica="banzo_inf")),
            Barra(nome="BS1", inicio=(0, 0, 1000), fim=(0, 2000, 950), perfil=U_BZ, papel="banzo", atributos=dict(at, papel_trelica="banzo_sup")),
            Barra(nome="BS2", inicio=(0, 2000, zb), fim=(0, 3000, zb), perfil=U_BZ, papel="banzo", atributos=dict(at, papel_trelica="banzo_sup")),
            Barra(nome="P0", inicio=(0, 0, 0), fim=(0, 0, 1000), perfil=U_BZ, papel="montante", atributos=dict(at)),
            Barra(nome="M1", inicio=(0, 1000, 0), fim=(0, 1000, 975), perfil=U_AL, papel="montante", atributos=dict(at)),
            Barra(nome="D0", inicio=(0, 0, 1000), fim=(0, 1000, 0), perfil=U_AL, papel="diagonal", atributos=dict(at)),
            Barra(nome="D1", inicio=(0, 1000, 975), fim=(0, 2000, 0), perfil=U_AL, papel="diagonal", atributos=dict(at)),
            Barra(nome="M2", inicio=(0, 2000, 0), fim=(0, 2000, topo_m), perfil=U_AL, papel="montante", atributos=dict(at)),
            Barra(nome="D2", inicio=(0, 2000, topo_m), fim=(0, 3000, 0), perfil=U_AL, papel="diagonal", atributos=dict(at)),
            Barra(nome="P1", inicio=(0, 3000, 0), fim=(0, 3000, zb), perfil=U_BZ, papel="montante", atributos=dict(at))]


def test_3_1c_degrau_no_banzo_de_cima_o_montante_sobe():
    """usuário, 19/10 (imagem 3, tesourinha da faixa norte): "esse ponto não passou na regra do recorte" — os dois trechos
    do banzo de cima se encontravam no degrau sem corte, um sobre o outro. Decisão dele: manter o degrau, o montante sobe
    até o banzo de cima e o de baixo nasce na face do montante"""
    bs = _tesoura_com_degrau()
    assert "3.1c" in _regras(bs)
    R.aplicar(bs)
    por = _por_nome(bs)
    assert por["M2"].fim == (0.0, 2000.0, 950.0)                # o montante vai até o nó do banzo de cima
    face = R._extensao(por["M2"], (0.0, 1.0, 0.0))               # o material do montante do lado do banzo de baixo
    assert face > 0 and por["BS2"].recorte_inicio == pytest.approx(face, abs=0.2)   # o de baixo nasce na face dele
    assert "3.1c" not in _regras(bs) and "3.1" not in _regras(bs)
    # um degrau que já separa as seções (60 mm num U de 50) não é acusado
    largo = _tesoura_com_degrau(degrau=60.0)
    R.orientar(largo)                                            # os banzos na posição da regra (50 mm no plano)
    assert not R.degraus(largo)


def test_3_2_no_da_alma_vai_para_o_eixo_do_banzo():
    """Mercado (meia-tesoura MT.1, 19/10): no painel da ponta a alma parava 50 mm abaixo do eixo do banzo plano — as peças
    não se tocavam e o montante do degrau não chegava no nó. NBR 8800, 6.5.2: a menos de 100 mm é um nó só"""
    bs = _tesoura_com_degrau(montante_ate_o_no=False)
    assert "3.2" in _regras(bs)
    R.aplicar(bs)
    por = _por_nome(bs)
    assert por["D2"].inicio[2] == pytest.approx(910.0)           # a diagonal foi para o eixo do banzo de baixo
    assert por["M2"].fim == (0.0, 2000.0, 950.0)                 # e o montante, depois, até o de cima (3.1c)
    assert not ({"3.2", "3.1c"} & _regras(bs))


def _terca_sobre(bs, giro, x0=-600.0, x1=600.0, y=1500.0):
    """uma terça Ue 150 ao longo de x, cruzando o banzo de cima da tesoura a mão (z 1000), sentada nele"""
    t = Barra(nome="TC", inicio=(x0, y, 1100.0), fim=(x1, y, 1100.0), perfil="Ue 150×60×20×2,00", papel="terça",
              rotacao=giro)
    bs.append(t)
    return t


def test_4_9_terca_torcida_volta_a_agua_sentada_no_apoio():
    """usuário, 19/10 (imagem 3, terça NC-3 da faixa norte): "essa terça ficou torcida demais" — 30,6° fora da água: o
    gerador mediu a inclinação do topo da tesourinha bem em cima do degrau. Nenhuma regra conferia o giro da terça"""
    from nucleo3d.geometria import malha_barra
    bs = _tesoura_a_mao()
    R.aplicar(bs)
    t = _terca_sobre(bs, 30.0)
    baixo0 = min(v[2] for v in malha_barra(t)[0])
    assert "4.9" in _regras(bs)
    assert R.girar_tercas(bs) == 1
    v = base_local(t.direcao, t.rotacao)[1]
    assert abs(v[2]) > 0.999                                     # a alma em pé (a água é plana aqui)
    assert min(v[2] for v in malha_barra(t)[0]) == pytest.approx(baixo0, abs=0.5)   # no mesmo apoio
    assert "4.9" not in _regras(bs)
    # a terça deitada de propósito (o beiral do Docas, 90°) não é acusada nem mexida
    bs2 = _tesoura_a_mao()
    R.aplicar(bs2)
    _terca_sobre(bs2, 90.0)
    assert "4.9" not in _regras(bs2) and R.girar_tercas(bs2) == 0


def test_4_8_trelica_so_empilhada_nao_e_a_que_chega():
    """Mercado, 19/10: a fachada (base em +5,01) passa logo acima da faixa norte (topo +4,99) — só se tocam na altura.
    Com 50 mm de folga na altura a 4.8 a via como "a que chega" e recuava o fechamento da faixa 100 mm"""
    painel = _painel(2900.0, 0.0, 9000.0, z0=1528.0, z1=2500.0)   # a fachada: começa 28 mm acima do topo da tesoura
    tes = _tesoura_em_x(2900.0, 8850.0, 4500.0, z0=500.0, z1=1500.0)
    for b in tes:                                                # a tesoura toda abaixo do painel
        b.inicio = (b.inicio[0], b.inicio[1], min(b.inicio[2], 1500.0))
        b.fim = (b.fim[0], b.fim[1], min(b.fim[2], 1500.0))
    bs = painel + tes
    assert R.invasoes(bs) == []
    assert R.recuar(bs) == 0
