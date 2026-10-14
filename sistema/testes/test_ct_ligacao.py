# -*- coding: utf-8 -*-
"""Ct da área líquida efetiva de cantoneiras e U (achados N1 e N11, 14/10/2026).

Antes, `nbr8800.tracao` sem Ct/ec/lc tomava Ct = 1,0 ("todos os elementos ligados") e a
cantoneira de tesoura ligada por uma aba saía com a área líquida efetiva igual à bruta;
o U/Ue formado a frio nem verificava a ruptura da seção líquida (NBR 14762, item 9.6.2-c).

Regras do usuário (14/10/2026):
  * Ct pelos parafusos/solda do 3D quando houver;
  * sem a ligação no modelo: cantoneira e U laminados com Ct = Ac/Ag (piso da NBR 8800:2024,
    item 5.2.5-c); U/Ue formados a frio com Ct = 0,50 (o menor da NBR 14762 para U soldado);
  * cantoneira formada a frio ("L … (FF)") pela NBR 14762 — sem ligação, 0,40: para
    cantoneira a norma admite a soldada até 0,40 (0,50 seria contra a segurança);
  * ruptura da seção líquida só na barra com ponta ligada (ligacao["ponta_ligada"]).

Normas conferidas no texto:
  * NBR 8800:2024, item 5.2.5-c) (p. 41–42 da norma; págs. 63–64 do PDF escaneado):
    Ct = 1 − ec/ℓc e, fora tubos e chapas, Ct ≥ Ac/Ag (os limites 0,60/0,90 eram da 2008);
  * NBR 14762:2010, item 9.6.2-c) (p. 34–36): cantoneira e U parafusados, e cantoneira
    soldada, Ct = 1 − 1,2x/L (0,4 ≤ … ≤ 0,9); U soldado Ct = 1 − 0,36x/L (0,5 ≤ … ≤ 0,9);
    An = 0,9(A − nf·df·t) na parafusada; γ = 1,65; furo-padrão pela Tabela 15 (p. 58).

Os valores esperados estão calculados à mão nos comentários.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import nbr8800 as n, perfis_fabrica, verificar     # noqa: E402
from nucleo.base import ErroDeDados                           # noqa: E402
from nucleo.perfis import perfil                              # noqa: E402

A572 = "ASTM A572 Gr.50"      # fy = 34,5; fu = 45,0 kN/cm²
A36 = "ASTM A36"              # fy = 25,0; fu = 40,0 kN/cm²


def perto(obtido, esperado, tol=0.005, o=""):
    ref = abs(esperado) if esperado else 1.0
    assert abs(obtido - esperado) <= tol * ref, f"{o}: obtido {obtido:.6g}, esperado {esperado:.6g}"


def _l50x3():
    p = perfis_fabrica.perfil_de_fabrica("L 50x3")
    assert p.nome == "L 50×3 (FF)" and p.dados["formado_a_frio"]
    return p


def _l2():
    """L 2"×1/4" laminada de tabela: A = 6,05 cm², b = 5,08 cm, t = 0,635 cm."""
    return perfil('L 2"×1/4"')


def _v(r, inicio):
    return next(v for v in r.verificacoes if v.titulo.startswith(inicio))


def _tem(r, inicio):
    return any(v.titulo.startswith(inicio) for v in r.verificacoes)


# --------------------------------------------------------------- NBR 8800: cantoneira laminada

def test_cantoneira_laminada_sem_ligacao_ct_ac_ag():
    """(1) L 2"×1/4", A36, sem a ligação no modelo → Ct = Ac/Ag (piso da NBR 8800:2024).

      Ac = aba ligada = 5,08 × 0,635 = 3,2258 cm²;  Ct = 3,2258 / 6,05 = 0,5332
      ruptura:    Ae = 0,5332 × 6,05 = 3,2258 cm² → 3,2258 × 40 / 1,35 = 95,58 kN (governa)
      escoamento: 6,05 × 25 / 1,10 = 137,5 kN
    Antes da correção: Ct = 1,0 → ruptura 179,3 kN e Nt,Rd = 137,5 kN (+44 % sobre 95,58)."""
    L = _l2()
    r = n.tracao(L, A36, N_Sd=100.0, L=150.0)
    perto(r.dados["Ct"], 0.5332, o="Ct")
    perto(r.dados["N_Rd_escoamento"], 137.5, o="escoamento")
    perto(r.dados["N_Rd_ruptura"], 95.58, o="ruptura")
    perto(r.dados["N_Rd"], 95.58, o="Nt,Rd")
    assert r.dados["governa"] == "ruptura" and r.dados["Ct_adotado_sem_ligacao"]
    perto(n.ct_sem_ligacao(L), 0.5332, o="ct_sem_ligacao")
    # o mesmo pelo verificar_membro (o caminho das tesouras), com a chamada posicional antiga
    rm = verificar.verificar_membro(L, A36, 0.0, 100.0, 0.0, 150.0, 150.0, 1, "diagonal", [])
    perto(_v(rm, "Tração — ruptura").Rd, 95.58, o="ruptura pelo verificar_membro")
    assert not rm.ok                                     # 100 kN > 95,58 kN
    perto(rm.razao, 100.0 / 95.58, o="razão")


def test_cantoneira_laminada_soldada_com_lc_do_modelo():
    """(2) L 2"×1/4", A36, ligacao = {lc: 5 cm, soldada}.

      ec (abas retangulares) = (5,08·0,635·0,3175 + 4,445·0,635·(0,635 + 2,2225)) / (9,525·0,635)
         = (1,0242 + 8,0653) / 6,0484 = 1,5028 cm   (o manual, Exemplo 7.2, usa 1,50)
      Ct = 1 − 1,5028/5 = 0,6994 (≥ Ac/Ag = 0,5332)
      ruptura = 0,6994 × 6,05 × 40 / 1,35 = 125,4 kN (< escoamento 137,5 kN)."""
    L = _l2()
    ec, Ac, _ = n.excentricidade_ligacao(L)
    perto(ec, 1.5028, o="ec")
    perto(Ac, 3.2258, o="Ac")
    r = n.tracao(L, A36, N_Sd=50.0, L=150.0, ligacao={"lc": 5.0, "soldada": True, "fonte": "solda do 3D"})
    perto(r.dados["Ct"], 0.6994, o="Ct")
    perto(r.dados["N_Rd"], 125.4, o="Nt,Rd")
    assert not r.dados["Ct_adotado_sem_ligacao"]
    assert [h.fonte for h in r.hipoteses] == ["modelo"]
    assert "solda do 3D" in r.hipoteses[0].texto


def test_cantoneira_laminada_parafusada_desconta_o_furo():
    """(3) L 2"×1/4", A36, 3 parafusos de 5/8" a 6 cm → ℓc = 12 cm.

      furo: 1,5875 + 0,35 = 1,9375 cm (d + 1,5 mm do furo-padrão + 2 mm, item 5.2.4)
      An = 6,05 − 1 × 1,9375 × 0,635 = 4,820 cm²
      Ct = 1 − 1,5028/12 = 0,8748;  Ae = 0,8748 × 4,820 = 4,216 cm²
      ruptura = 4,216 × 40 / 1,35 = 124,9 kN;  escoamento = 137,5 kN."""
    L = _l2()
    lig = {"lc": 12.0, "n_parafusos": 3, "d_parafuso": 1.5875, "fonte": "parafusos do 3D"}
    r = n.tracao(L, A36, N_Sd=100.0, L=280.0, ligacao=lig)
    perto(r.dados["An"], 4.820, o="An")
    perto(r.dados["Ct"], 0.8748, o="Ct")
    perto(r.dados["Ae"], 4.216, o="Ae")
    perto(r.dados["N_Rd_ruptura"], 124.9, o="ruptura")
    perto(r.dados["N_Rd_escoamento"], 137.5, o="escoamento")
    assert r.dados["governa"] == "ruptura"
    # dois parafusos a 3 cm: 1 − 1,5028/3 = 0,499 < Ac/Ag = 0,5332 → vale o piso
    r2 = n.tracao(L, A36, N_Sd=100.0, L=280.0, ligacao={"lc": 3.0, "n_parafusos": 2, "d_parafuso": 1.5875})
    perto(r2.dados["Ct"], 0.5332, o="Ct no piso Ac/Ag")
    assert any("A<sub>c</sub>/A<sub>g</sub>" in p.formula for p in _v(r2, "Tração — ruptura").passos)
    # um parafuso só (ℓc = 0): Ct = Ac/Ag
    r1 = n.tracao(L, A36, N_Sd=10.0, L=280.0, ligacao={"n_parafusos": 1, "d_parafuso": 1.27})
    perto(r1.dados["Ct"], 0.5332, o="Ct com um parafuso")


def test_ct_explicito_tem_prioridade_sobre_a_ligacao():
    """Ct/ec/lc explícitos (exemplos do manual) continuam mandando."""
    r = n.tracao(_l2(), A36, L=280.0, n_furos=1, d_parafuso=1.27, t_furo=0.635, ec=1.50, lc=6.0,
                 ligacao={"lc": 50.0, "soldada": True})
    perto(r.dados["Ct"], 0.75, tol=1e-9, o="Ct do manual")
    assert not r.hipoteses


def test_u_laminado_sem_ligacao_e_com_lc():
    """U 3"×6,1 (A = 7,78 cm², d = 76,2, bf = 35,8, t = 4,3 mm) ligado pela alma, A572.

      Ac = alma = 7,62 × 0,43 = 3,2766 cm²; sem ligação Ct = 3,2766/7,78 = 0,4212
        → 0,4212 × 7,78 × 45 / 1,35 = 109,2 kN
      tf médio que fecha a área: (7,78 − 3,2766)/(2·(3,58 − 0,43)) = 0,7148 cm
      x̄ = (3,2766·0,215 + 2·3,15·0,7148·(0,43 + 1,575)) / 7,78 = 1,2511 cm
      ℓc = 10 cm: Ct = 1 − 0,12511 = 0,8749 → 226,9 kN; escoamento 7,78 × 34,5/1,1 = 244,0 kN."""
    u = perfil('U 3"×6,1')
    ec, Ac, _ = n.excentricidade_ligacao(u)
    perto(ec, 1.2511, o="x̄ do U")
    perto(Ac, 3.2766, o="Ac = alma")
    r = verificar.verificar_membro(u, A572, 0.0, 100.0, 0.0, 300.0, 300.0, 1, "banzo")
    perto(r.dados["Ct"], 0.4212, o="Ct sem ligação")
    perto(_v(r, "Tração — ruptura").Rd, 109.2, o="ruptura sem ligação")
    r2 = verificar.verificar_membro(u, A572, 0.0, 100.0, 0.0, 300.0, 300.0, 1, "banzo",
                                    ligacao={"lc": 10.0, "soldada": True})
    perto(r2.dados["Ct"], 0.8749, o="Ct com lc")
    perto(_v(r2, "Tração — ruptura").Rd, 226.9, o="ruptura com lc")


def test_perfil_i_e_tubo_continuam_com_ct_1():
    """(4) W e tubo: todos os elementos ligados, Ct = 1,0 como antes — e sem hipótese."""
    for nome in ("W 200×15,0", "TQ 50×50×2,0", "TC 33,7×2,65"):
        p = perfil(nome)
        assert n.ct_sem_ligacao(p) == 1.0
        for lig in (None, {"lc": 5.0, "soldada": True}):
            r = verificar.verificar_membro(p, A572, 0.0, 10.0, 0.0, 200.0, 200.0, 1, "barra", ligacao=lig)
            assert r.dados["Ct"] == 1.0, nome
            assert not r.hipoteses, nome
            assert not r.dados["Ct_adotado_sem_ligacao"]
            perto(_v(r, "Tração — ruptura").Rd, p.A * 45.0 / 1.35, tol=1e-9, o=nome)


def test_passo_e_hipotese_no_resultado():
    """(6) O Ct adotado aparece como passo da verificação e como hipótese do Resultado,
    e chega ao dicionário que a interface e o memorial leem."""
    r = verificar.verificar_membro(_l2(), A36, 0.0, 30.0, 0.0, 150.0, 150.0, 1, "diagonal")
    vr = _v(r, "Tração — ruptura")
    textos = [ps.texto for ps in vr.passos]
    assert any(t.startswith("C<sub>t</sub> = A<sub>c</sub>/A<sub>g</sub> adotado: ligação fora do modelo; "
                            "piso da NBR 8800:2024, 5.2.5-c") for t in textos), textos
    assert any("5.2.5" in ps.norma for ps in vr.passos)
    assert [(h.chave, h.fonte) for h in r.hipoteses] == [("ct_ligacao", "rotina")]
    s = verificar.serializar_resultado(r)
    assert s["hipoteses"][0]["chave"] == "ct_ligacao" and "0,533" in s["hipoteses"][0]["texto"]
    assert s["dados"]["Ct"] == pytest.approx(0.5332, abs=1e-4) and s["dados"]["Ct_adotado_sem_ligacao"] is True


def test_ligacao_invalida_falha_explicita():
    for p in (_l2(), _l50x3()):
        for lig in ({"lc": -1.0}, {"n_parafusos": 2}, {"n_parafusos": 2, "d_parafuso": 16.0},
                    {"soldada": True, "n_parafusos": 2, "d_parafuso": 1.27}, "lc=5"):
            with pytest.raises(ErroDeDados):
                n.tracao(p, A572, N_Sd=10.0, L=100.0, ligacao=lig)
    # pelo verificar_membro, o erro vira "não verificada" (não aprova)
    r = verificar.verificar_membro(_l2(), A572, 0.0, 10.0, 0.0, 100.0, 100.0, 1, "d", ligacao={"lc": -1})
    assert r.indeterminada and not r.ok


# --------------------------------------------------------------- NBR 14762: cantoneira (FF)

def test_cantoneira_formada_a_frio_pela_14762():
    """(1'/2'/3') L 50×3 (FF), A572 — tração pela NBR 14762, item 9.6.2.

    Linha média com o canto de raio interno t (r_m = 3 + 1,5 = 4,5 mm):
      L = 2 × (50 − 6) + π/2 × 4,5 = 95,07 mm → A = 9,507 × 0,3 = 2,852 cm²
      x̄ = (44·28 + 7,069·(6 − 4,5·2/π) + 44·1,5) / 95,07 = 13,886 mm → x = 1,389 cm
      escoamento (9.6.2-a): 2,852 × 34,5 / 1,10 = 89,45 kN
      sem ligação: Ct = 0,40 → 0,40 × 2,852 × 45 / 1,65 = 31,11 kN (governa)
      soldada, L = 5 cm: Ct = 1 − 1,2 × 1,3887/5 = 0,6667 → 0,6667 × 2,852 × 45/1,65 = 51,86 kN
      3 parafusos de 5/8" (d = 1,5875 ≥ 1,25 → df = 1,7375 cm), L = 12 cm:
        An = 0,9 × (2,852 − 1,7375 × 0,3) = 2,0977 cm²; Ct = 1 − 1,2 × 1,3887/12 = 0,8611
        → 0,8611 × 2,0977 × 45 / 1,65 = 49,27 kN
      soldada, L = 2 cm: Ct = 1 − 1,2 × 1,3887/2 = 0,167 < 0,4 → ligação não permitida.
    Antes da correção: pela NBR 8800 com Ct = 1,0, Nt,Rd = 89,45 kN (2,9 × 31,11)."""
    p = _l50x3()
    perto(p.A, 2.852, o="A")
    x, _, _ = n.excentricidade_ligacao(p)
    perto(x, 1.3887, o="x")
    assert n.ct_sem_ligacao(p) == 0.40
    r = verificar.verificar_membro(p, A572, 0.0, 30.0, 0.0, 150.0, 150.0, 1, "diagonal", [])
    ve, vr = _v(r, "Tração — escoamento"), _v(r, "Tração — ruptura")
    perto(ve.Rd, 89.45, o="escoamento")
    assert ve.norma == "NBR 14762:2010, item 9.6.2-a)"
    perto(vr.Rd, 31.11, o="ruptura sem ligação")
    assert vr.norma == "NBR 14762:2010, item 9.6.2-c)" and r.critica is vr
    perto(r.dados["Ct"], 0.40, tol=1e-9, o="Ct")
    assert [(h.chave, h.fonte) for h in r.hipoteses] == [("ct_ligacao", "rotina")]
    assert any(ps.texto.startswith("C<sub>t</sub> = 0,40 adotado") for ps in vr.passos)
    rs = n.tracao(p, A572, N_Sd=30.0, L=150.0, ligacao={"lc": 5.0, "soldada": True, "fonte": "solda do 3D"})
    perto(rs.dados["Ct"], 0.6667, o="Ct soldado")
    perto(rs.dados["N_Rd"], 51.86, o="ruptura soldada")
    rp = n.tracao(p, A572, N_Sd=30.0, L=150.0, ligacao={"lc": 12.0, "n_parafusos": 3, "d_parafuso": 1.5875})
    perto(rp.dados["An"], 2.0977, o="An parafusado")
    perto(rp.dados["Ct"], 0.8611, o="Ct parafusado")
    perto(rp.dados["N_Rd"], 49.27, o="ruptura parafusada")
    rc = n.tracao(p, A572, N_Sd=1.0, L=150.0, ligacao={"lc": 2.0, "soldada": True})
    assert rc.dados["N_Rd"] == 0.0 and not rc.ok and "não permite" in _v(rc, "Tração — ruptura").observacao


# --------------------------------------------------------------- NBR 14762: U e Ue

def test_ue_tracionado_tem_ruptura_que_governa():
    """(5) Ue 100×50×17×2,00 (A = 4,417 cm², x̄ = 1,783 cm pela linha média com os cantos;
    sem os cantos: (9,8·0,1 + 9,6·2,5 + 3,2·4,9)/22,6 = 1,799 cm), A572, Nt = 40 kN.

      escoamento (9.6.2-a): 4,417 × 34,5 / 1,10 = 138,5 kN
      ruptura sem ligação (9.6.2-c): Ct = 0,50 → 0,50 × 4,417 × 45 / 1,65 = 60,23 kN (governa)
      soldada, L = 5 cm: Ct = 1 − 0,36 × 1,783/5 = 0,8716 → 0,8716 × 4,417 × 45/1,65 = 105,0 kN
      3 parafusos de 1/2" (d = 1,27 ≥ 1,25 → df = 1,42 cm), L = 10 cm:
        An = 0,9 × (4,417 − 1,42 × 0,2) = 3,720 cm²; Ct = 1 − 1,2 × 1,783/10 = 0,7861
        → 0,7861 × 3,720 × 45 / 1,65 = 79,74 kN
      L = 3 cm: Ct = 1 − 1,2 × 1,783/3 = 0,287 < 0,4 → ligação não permitida (Rd = 0)."""
    ue = perfis_fabrica.perfil_de_fabrica("Ue 100x50x17x2")
    sec = perfis_fabrica.secao_frio(ue)
    perto(sec.A, 4.417, o="A")
    perto(sec.xc, 1.783, o="x̄")
    assert n.ct_sem_ligacao(ue) == 0.50
    r = verificar.verificar_membro(ue, A572, 0.0, 40.0, 0.0, 150.0, 150.0, 1, "banzo")
    perto(_v(r, "Tração — escoamento").Rd, 138.5, o="escoamento")
    vr = _v(r, "Tração — ruptura")
    perto(vr.Rd, 60.23, o="ruptura sem ligação")
    assert r.critica is vr and r.ok
    perto(r.razao, 40.0 / 60.23, o="razão")
    assert vr.norma == "NBR 14762:2010, item 9.6.2-c)"
    assert [(h.chave, h.fonte) for h in r.hipoteses] == [("ct_ligacao", "rotina")]
    assert any(p.texto.startswith("C<sub>t</sub> = 0,50 adotado") for p in vr.passos)
    # antes da correção a tração do Ue só tinha o escoamento: 40/138,5 = 0,29
    rs = verificar.verificar_membro(ue, A572, 0.0, 40.0, 0.0, 150.0, 150.0, 1, "banzo",
                                    ligacao={"lc": 5.0, "soldada": True, "fonte": "solda do 3D"})
    perto(rs.dados["Ct"], 0.8716, o="Ct soldado")
    perto(_v(rs, "Tração — ruptura").Rd, 105.0, o="ruptura soldada")
    assert [h.fonte for h in rs.hipoteses] == ["modelo"]
    rp = verificar.verificar_membro(ue, A572, 0.0, 40.0, 0.0, 150.0, 150.0, 1, "banzo",
                                    ligacao={"lc": 10.0, "n_parafusos": 3, "d_parafuso": 1.27})
    perto(rp.dados["An"], 3.720, o="An parafusado")
    perto(rp.dados["Ct"], 0.7861, o="Ct parafusado")
    perto(_v(rp, "Tração — ruptura").Rd, 79.74, o="ruptura parafusada")
    rc = verificar.verificar_membro(ue, A572, 0.0, 1.0, 0.0, 150.0, 150.0, 1, "banzo",
                                    ligacao={"lc": 3.0, "n_parafusos": 2, "d_parafuso": 1.27})
    vc = _v(rc, "Tração — ruptura")
    assert vc.Rd == 0.0 and not rc.ok and "não permite" in vc.observacao


def test_ue_interacao_de_tracao_usa_o_menor_nt_rd():
    """Tração com momento: Nt,Rd da interação é o menor entre escoamento e ruptura
    (NBR 14762, item 9.6.2) — aqui a ruptura de 60,23 kN; sem ponta ligada, o escoamento."""
    ue = perfis_fabrica.perfil_de_fabrica("Ue 100x50x17x2")
    r = verificar.verificar_membro(ue, A572, 0.0, 20.0, 50.0, 150.0, 150.0, 1, "banzo")
    vm = _v(r, "Flexão")
    perto(_v(r, "Interação").Sd, 20.0 / 60.23 + 50.0 / vm.Rd, o="interação")
    r2 = verificar.verificar_membro(ue, A572, 0.0, 20.0, 50.0, 150.0, 150.0, 1, "banzo",
                                    ligacao={"ponta_ligada": False})
    perto(_v(r2, "Interação").Sd, 20.0 / 138.5 + 50.0 / vm.Rd, o="interação sem ponta")


# --------------------------------------------------------------- ponta ligada

def test_trecho_corrido_sem_ponta_ligada_so_escoamento():
    """(4 da decisão) ligacao = {ponta_ligada: False}: trecho corrido de banzo contínuo — sem
    ruptura da seção líquida, fica o escoamento da seção bruta, com o passo escrito.

      L 2"×1/4" A36: 6,05 × 25 / 1,10 = 137,5 kN; L 50×3 (FF): 89,45 kN;
      Ue 100×50×17×2: 138,5 kN; U 3"×6,1 A572: 7,78 × 34,5 / 1,10 = 244,0 kN."""
    sem = {"ponta_ligada": False, "fonte": "banzo contínuo"}
    casos = ((_l2(), A36, 137.5), (_l50x3(), A572, 89.45),
             (perfis_fabrica.perfil_de_fabrica("Ue 100x50x17x2"), A572, 138.5),
             (perfil('U 3"×6,1'), A572, 244.0))
    for p, aco, esperado in casos:
        r = verificar.verificar_membro(p, aco, 0.0, 30.0, 0.0, 150.0, 150.0, 1, "banzo", ligacao=sem)
        assert not _tem(r, "Tração — ruptura"), p.nome
        ve = _v(r, "Tração — escoamento")
        perto(ve.Rd, esperado, o=p.nome)
        assert "trecho corrido de banzo contínuo: sem ligação de ponta, a seção líquida não se aplica" \
            in ve.observacao, p.nome
        assert any("seção líquida não se aplica" in ps.texto for ps in ve.passos), p.nome
        assert r.dados["ponta_ligada"] is False and not r.hipoteses, p.nome
    # pelo nbr8800.tracao: N_Rd = escoamento, sem Ct
    rt = n.tracao(_l2(), A36, N_Sd=10.0, L=150.0, ligacao=sem)
    assert rt.dados["Ct"] is None and rt.dados["N_Rd_ruptura"] is None
    perto(rt.dados["N_Rd"], 137.5, o="N_Rd sem ponta")
    assert rt.dados["governa"] == "escoamento"
    # ponta_ligada ausente ou True: o comportamento com ponta (Ct = Ac/Ag)
    for lig in (None, {"ponta_ligada": True}, {"ponta_ligada": None}):
        perto(n.tracao(_l2(), A36, N_Sd=10.0, L=150.0, ligacao=lig).dados["Ct"], 0.5332, o=str(lig))
    # furos no trecho corrido não são da ligação: seção líquida com Ct = 1,0
    rf = n.tracao(_l2(), A36, N_Sd=10.0, L=150.0, n_furos=1, d_parafuso=1.27, ligacao=sem)
    assert rf.dados["Ct"] == 1.0
    perto(rf.dados["An"], 6.05 - 1.62 * 0.635, o="An com furo fora da ligação")
