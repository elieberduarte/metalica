# -*- coding: utf-8 -*-
"""FAB-03 no catálogo inteiro: todo perfil formado a frio pesa pela regra da fábrica, como a lista o pesa.

REINCIDÊNCIA (30/10, Hora Certa · Galpão Existente, auditor; o mesmo do SESI, N02 de 28/10): os itens de tabela do
perfis.json sem a chave do enrijecedor eram pesados como U sem a dobra da aba — Ue 200×75×25×3,00 a 7,824 kg/m em vez
de 9,024, Ue 150×60×20×2,65 a 5,275 em vez de 6,123 (a compra do SESI 1.115 kg abaixo). A conferência agora passa por
todos os itens, não por exemplos: o kg/m do catálogo = o da regra pelo nome (saida/dobras.pesos), onde a regra se aplica.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest  # noqa: E402

from nucleo import catalogo  # noqa: E402
from saida import dobras  # noqa: E402


def test_os_casos_do_galpao_existente_e_do_sesi():
    assert catalogo.item("Ue 200×75×25×3,00").massa == pytest.approx(9.024, abs=0.005)
    assert catalogo.item("Ue 150×60×20×2,65").massa == pytest.approx(6.123, abs=0.005)


def _fora_da_regra(familias=None, sem=()):
    fora = []
    for it in catalogo.itens():
        if it.grupo != "formado a frio" or not it.massa:
            continue
        if (familias and it.familia not in familias) or it.familia in sem:
            continue
        r = dobras.pesos(it.nome)
        if not r or not r.get("kg_m_desconto"):
            # o nome que o leitor não entende saía da conferência calado: assim passaram as 47 cantoneiras de uma medida
            # só, "L 50×2,00 (FF)" a 1,518 kg/m na lista do SESI (N10, 30/10)
            fora.append("%s: o leitor do nome (dobras.geometria) não reconhece" % it.nome)
            continue
        if abs(float(it.massa) - float(r["kg_m_desconto"])) > 0.01:
            fora.append("%s: catálogo %.3f × regra %.3f" % (it.nome, it.massa, r["kg_m_desconto"]))
    return fora


def test_todo_formado_a_frio_do_catalogo_pela_regra():
    """o Z45 também entrou aqui: o leitor do nome (dobras.geometria) lia o "45" na altura — 723 kg/m na lista"""
    fora = _fora_da_regra(sem=("Cr",))
    assert not fora, "%d perfil(is) fora da FAB-03: %s" % (len(fora), "; ".join(fora[:20]))


def test_cartola_pela_regra():
    """o leitor do nome lia "Cr h×b×D" como alma × abas × mesas; o catálogo (e a área da NBR 6355) é laterais × topo × abas"""
    fora = _fora_da_regra(familias=("Cr",))
    assert not fora, "%d cartola(s): %s" % (len(fora), "; ".join(fora[:5]))


def test_nenhum_laminado_pela_regra_das_dobras():
    """a laminada de duas medidas ("L 75×50×6,00") era lida como dobrada: 5,424 kg/m em vez dos 5,544 da tabela (30/10)"""
    lam = [it.nome for it in catalogo.itens() if it.grupo != "formado a frio" and dobras.pesos(it.nome)]
    assert not lam, lam[:20]


@pytest.mark.parametrize("nome, kg_m", [("L 50×2 (FF)", 1.536),             # o nome gravado no SESI (N10)
                                        ("L 50×2,25 (FF)", 1.719),
                                        ("L50X2", 1.536),                   # o do exportador, sem o (FF)
                                        ("L 75×50×6,00", 5.544),            # laminada: a tabela
                                        ("L 50×5,00", 3.77)])
def test_cantoneira_na_lista(nome, kg_m):
    """o peso da peça como a lista e o romaneio o tiram (nucleo2d/detalhe/base.peso_teorico), 1 m de barra"""
    from nucleo2d.detalhe.base import peso_teorico
    from saida.detalhamento import Posicao
    p = Posicao(marca="C1", tipo_ifc="IfcMember", perfil=nome, classe="cantoneira", L=1000.0, H=50.0, T=50.0,
                comprimento=1000.0)
    assert peso_teorico(p) == pytest.approx(kg_m, abs=0.005)


@pytest.mark.parametrize("nome, kg_m", [("Cr 20×30×12×0,95", 0.657),      # topo maior que as laterais
                                        ("Cr 100×50×20×3,35", 7.054)])    # laterais maiores que o topo (Ix > Iy)
def test_cartola_na_lista(nome, kg_m):
    assert dobras.pesos(nome)["kg_m_desconto"] == pytest.approx(kg_m, abs=0.01)
