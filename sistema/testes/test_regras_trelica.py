# -*- coding: utf-8 -*-
"""Regras de posição das peças da treliça (nucleo3d/regras_trelica.py) — o usuário, 16/10: "o sistema continua gerando
peças com perfil errado, aleatório… toda vez que gera uma tesoura nova volta com a configuração antiga, perfis de canto com
a boca virada para o lado errado; tornar regras do sistema".

Cada gerador de treliça chama `regras_trelica.orientar` antes do encaixe de fábrica; aqui cada caminho gera uma treliça e
`regras_trelica.conferir` tem de voltar vazio. Se um gerador novo (ou um antigo mexido) esquecer a regra, este teste cai.
Os caminhos: a tesoura pelo desenho (de_planta_estrutura), a treliça entre banzos do editor 3D (modelagem.trelica), o
galpão treliçado (de_projeto), o projeto recebido pela planta (de_planta, o Posto) e o 3D pelos quadros (de_quadros)."""
import math
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


def _boca(b):
    return base_local(b.direcao, b.rotacao)[0]


def _tesoura_a_mao(giro_banzo=0.0, giro_alma_u=0.0, l_alternada=True):
    """uma tesoura plana em y-z (x = 0), 6 m × 1 m: banzos em U, montantes de ponta e do meio em U, diagonais em U e em L;
    os giros dados de propósito fora da regra (o giro 0 de quem não orienta, a cantoneira pelo sentido do desenho)"""
    at = {"origem": {"peca": "TT"}}
    bs = [Barra(nome="BS", inicio=(0, 0, 1000), fim=(0, 6000, 1000), perfil=U_BZ, papel="banzo", rotacao=giro_banzo,
                atributos=dict(at)),
          Barra(nome="BI", inicio=(0, 0, 0), fim=(0, 6000, 0), perfil=U_BZ, papel="banzo", rotacao=giro_banzo,
                atributos=dict(at))]
    for y in (0, 3000, 6000):                         # os montantes em U: as duas pontas (o canto) e o do meio
        bs.append(Barra(nome="M%d" % y, inicio=(0, y, 0), fim=(0, y, 1000), perfil=U_AL, papel="montante",
                        rotacao=giro_alma_u, atributos=dict(at)))
    for k, (y0, y1) in enumerate(((0, 1500), (1500, 3000))):
        bs.append(Barra(nome="DU%d" % k, inicio=(0, y0, 1000), fim=(0, y1, 0), perfil=U_AL, papel="diagonal",
                        rotacao=giro_alma_u, atributos=dict(at)))
    for k, (y0, y1) in enumerate(((3000, 4500), (6000, 4500), (4500, 4500))):
        a, b = ((0, y0, 0), (0, y1, 1000)) if k != 1 else ((0, y0, 0), (0, y1, 1000))
        if l_alternada and k % 2:
            a, b = b, a                               # desenhada ao contrário: sem a regra, a aba vai para o outro lado
        bs.append(Barra(nome="DL%d" % k, inicio=a, fim=b, perfil=L_AL, papel="montante" if k == 2 else "diagonal",
                        rotacao=0.0, atributos=dict(at)))
    return bs


def test_conferir_acusa_cada_regra_e_orientar_corrige():
    bs = _tesoura_a_mao(giro_banzo=0.0, giro_alma_u=0.0)
    erros = R.conferir(bs)
    regras = {e["regra"] for e in erros}
    # T2 (banzo de boca para fora do plano), T3 (montantes), T4 (diagonais em U) e T5 (cantoneira de um lado e do outro)
    assert {"T2", "T3", "T4", "T5"} <= regras, erros
    assert R.orientar(bs) > 0
    assert R.conferir(bs) == []
    assert R.orientar(bs) == 0                        # idempotente: rodar de novo não mexe em nada


def test_a_regra_de_cada_peca():
    bs = _tesoura_a_mao()
    R.orientar(bs)
    por = {b.nome: b for b in bs}
    # T2: o banzo de cima abre para baixo, o de baixo para cima; a altura do perfil atravessa o plano (x)
    assert _boca(por["BS"])[2] == pytest.approx(-1.0, abs=1e-6)
    assert _boca(por["BI"])[2] == pytest.approx(1.0, abs=1e-6)
    assert abs(base_local(por["BS"].direcao, por["BS"].rotacao)[1][0]) == pytest.approx(1.0, abs=1e-6)
    # T3: os montantes de canto abrem para dentro (nunca para fora) e o do meio para o meio do vão
    assert _boca(por["M0"])[1] > 0.99
    assert _boca(por["M6000"])[1] < -0.99
    # T4: a diagonal em U abre para cima
    for k in (0, 1):
        assert _boca(por["DU%d" % k])[2] > 0.3
    # T5: as três cantoneiras com a aba que sai do plano do mesmo lado
    lados = {R.lado_da_aba(por["DL%d" % k], (1.0, 0.0, 0.0)) for k in range(3)}
    assert len(lados) == 1 and 0 not in lados


def test_boca_virada_pelo_usuario_fica():
    bs = _tesoura_a_mao()
    R.orientar(bs)
    m = next(b for b in bs if b.nome == "M0")
    m.rotacao = (m.rotacao + 180.0) % 360.0
    m.atributos["boca_virada"] = True                 # o "virar" do painel Perfis da tesoura
    assert R.conferir(bs) == []
    giro = m.rotacao
    R.orientar(bs)
    assert m.rotacao == giro


def test_pares_e_presilhas_ficam_fora():
    bs = _tesoura_a_mao()
    R.orientar(bs)
    # o par de cantoneiras (2L) espelhado: uma em cada aba, cada uma de um lado — não é a cantoneira simples da T5
    at = {"origem": {"peca": "TT"}}
    a = Barra(nome="PA", inicio=(-30, 1500, 0), fim=(-30, 3000, 1000), perfil=L_AL, papel="diagonal", rotacao=0.0,
              atributos=dict(at))
    b = Barra(nome="PB", inicio=(30, 1500, 0), fim=(30, 3000, 1000), perfil=L_AL, papel="diagonal", rotacao=90.0,
              atributos=dict(at))
    assert R.conferir(bs + [a, b]) == []


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
    """o modelo que já existe (importado, de script, de antes da regra) mostra a peça fora da posição na conferência"""
    from nucleo3d import conferencia_3d
    doc = Documento()
    for b in _tesoura_a_mao():
        doc.add(b)
    conf = conferencia_3d.conferir(doc, telha=False, soltas=False)
    assert conf["contagens"]["fora_da_posicao"] > 0
    assert any(a["tipo"] == "posicao" and "regra T" in a["texto"] for a in conf["apontamentos"])
    R.orientar(doc.entidades.values())
    assert conferencia_3d.conferir(doc, telha=False, soltas=False)["contagens"]["fora_da_posicao"] == 0
