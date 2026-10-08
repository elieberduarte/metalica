# -*- coding: utf-8 -*-
"""O índice da pasta de catálogos (Normas/CATÁLOGOS): o PDF que ninguém cita aparece como novo, e o
Hardbolt transcrito bate com o boletim (08/10/2026)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dados import indice_catalogos as IC                               # noqa: E402


def test_pdf_novo_na_pasta_entra_na_fila(tmp_path):
    (tmp_path / "06-PARAFUSOS-E-CHUMBADORES").mkdir()
    (tmp_path / "06-PARAFUSOS-E-CHUMBADORES" / "Fabricante X - parafusos (2026).pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "solto.pdf").write_bytes(b"%PDF-1.4")
    I = IC.montar(str(tmp_path))
    assert len(I["novos"]) == 2 and any(p.endswith("Fabricante X - parafusos (2026).pdf") for p in I["novos"])
    assert any(k.startswith("Sem assunto") for k in I["grupos"])                  # o PDF solto na raiz pede pasta
    css, corpo = IC.html_indice(I)
    assert "Novos na pasta" in corpo and "Fabricante X" in corpo


def test_toda_fonte_com_pdf_aponta_para_a_pasta_de_catalogos():
    for arqs, x in IC.ler_fontes():
        if x.get("arquivo"):
            assert x["arquivo"].startswith("Normas/CATÁLOGOS/"), (arqs, x["arquivo"])


def test_hardbolt_transcrito():
    with open(os.path.join(IC.BASE, "fornecedores", "chumbadores.json"), encoding="utf-8") as f:
        hb = json.load(f)["hardbolt"]
    assert len(hb["itens"]) == 12 and hb["cargas"]["coeficiente_seguranca"] == 4.0
    m12 = next(c for c in hb["cargas"]["valores"] if c["diametro"] == "M12" and c["embutimento"] == 100)
    assert m12["permissivel_kgf"]["30"] == {"tracao": 1275, "corte": 1055}
    # cada diâmetro termina em 1,00 e o fator só cresce com a distância (o M8 da borda à tração chega a 1,00 em 55 mm,
    # antes do Ccr de 65: como impresso no boletim)
    for nome, tab in hb["fatores"].items():
        for d in (tab.get("Scr") or tab.get("Ccr")):
            serie = [l["fatores"][d] for l in tab["linhas"] if d in l["fatores"]]
            assert serie[-1] == 1.0 and serie == sorted(serie), (nome, d, serie)
