# -*- coding: utf-8 -*-
"""Longarinas de fechamento: verificação pela NBR 14762 e reflexo nas saídas.

Até esta verificação existir, a lista de material copiava o perfil da terça para as
longarinas sem checar nada. Estes testes garantem que a peça é dimensionada com o vento
da parede e que a lista de material, os desenhos e o modelo 3D usam o perfil verificado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.galpao import dimensionar
from nucleo.modelo_galpao import DadosGalpao
from nucleo.perfis import banco


def _galpao(**ajustes):
    base = dict(nome="Longarinas", vao=20.0, comprimento=40.0, pe_direito=6.0,
                espacamento_porticos=5.0, inclinacao=10.0, v0=40.0,
                categoria_rugosidade="II", classe="B")
    base.update(ajustes)
    return dimensionar(DadosGalpao(**base))


def test_longarina_e_verificada_e_passa():
    p = _galpao()
    lg = p.elemento("Longarina")
    assert lg is not None, "o cálculo não publicou a longarina"
    assert lg.ok, lg.resultado.resumo()
    assert lg.perfil in banco().perfis, lg.perfil
    assert lg.resultado.verificacoes, "longarina sem verificações"


def test_longarina_usa_o_vento_da_parede():
    """Pressão e sucção vêm das paredes laterais, sem as zonas locais de canto."""
    p = _galpao()
    lg = p.elemento("Longarina")
    q = p.vento["q"]
    # Ce = +0,7 com Cpi = −0,3 dá 1,0·q de pressão; Ce = −0,8 com Cpi = +0,2, 1,0·q de sucção
    assert abs(lg.esforcos["pressao_kN_m2"] - 1.0 * q) < 0.02, lg.esforcos
    assert abs(lg.esforcos["succao_kN_m2"] + 1.0 * q) < 0.02, lg.esforcos


def test_titulos_falam_de_pressao_e_nao_de_gravidade():
    p = _galpao()
    titulos = " ".join(v.titulo for v in p.elemento("Longarina").resultado.verificacoes)
    assert "gravidade" not in titulos.lower(), titulos


def test_lista_de_material_usa_o_perfil_verificado():
    p = _galpao(pe_direito=10.0, comprimento=48.0, espacamento_porticos=6.0)
    lg = p.elemento("Longarina")
    l1 = [x for x in p.lista_material if x.marca == "L1"]
    assert l1, "lista de material sem longarinas"
    assert l1[0].perfil == lg.perfil
    n_vaos = p.dados.n_porticos - 1
    assert l1[0].quantidade == lg.geometria["fiadas_por_lado"] * 2 * n_vaos


def test_vento_mais_forte_pede_longarina_mais_pesada():
    leve = _galpao(v0=30.0).elemento("Longarina")
    forte = _galpao(v0=50.0, categoria_rugosidade="I").elemento("Longarina")
    massa = lambda e: banco()[e.perfil].massa
    assert massa(forte) >= massa(leve), (leve.perfil, forte.perfil)


def test_desenhos_e_modelo_3d_seguem_a_longarina():
    p = _galpao(pe_direito=10.0, comprimento=48.0, espacamento_porticos=6.0)
    lg = p.elemento("Longarina")
    from saida import desenhos
    assert desenhos._Geo(p).longarina.nome == lg.perfil
    from nucleo3d import de_projeto
    doc = de_projeto.modelo_do_galpao(p)
    perfis_3d = {e.perfil for e in doc.barras if e.papel == "longarina"}
    assert perfis_3d == {lg.perfil}, perfis_3d


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except Exception as e:
                falhas += 1
                print(f"  FALHA {nome}: {e}")
    print(f"\n{falhas} falha(s).")
    sys.exit(1 if falhas else 0)
