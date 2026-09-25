# -*- coding: utf-8 -*-
"""Desenhos da análise: diagramas do pórtico e quadro de verificações.

O que se garante aqui é que o papel conta a mesma história do cálculo: os valores
cotados nos diagramas e as razões do quadro têm de ser os do memorial, e o desenho
precisa se comportar mesmo quando não há análise nenhuma.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.galpao import dimensionar              # noqa: E402
from nucleo.modelo_galpao import DadosGalpao       # noqa: E402
from saida import desenhos, pranchas               # noqa: E402


def _texto(d) -> str:
    """Todo o texto do desenho, como aparece no DXF."""
    return "".join(d.entidades)


class BaseDesenhos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projeto = dimensionar(DadosGalpao())
        cls.diagramas = desenhos.diagramas_portico(cls.projeto)
        cls.quadro = desenhos.quadro_verificacoes(cls.projeto)


class TestDiagramas(BaseDesenhos):
    def test_cota_os_picos_do_calculo(self):
        texto = _texto(self.diagramas)
        # o desenho cota a análise; o momento de cálculo do joelho é esse × o fator de 2ª ordem
        so = self.projeto.esforcos["segunda_ordem"]
        joelho = self.projeto.esforcos["joelho_kNm_analise"]
        self.assertAlmostEqual(self.projeto.esforcos["joelho_kNm"], joelho * so["fator_pilar"], delta=0.15)
        self.assertIn("2a ordem", texto)
        self.assertIn(f"{joelho:.1f}".replace(".", ","), texto,
                      "o momento do joelho tem de aparecer cotado")
        for titulo in ("MOMENTO FLETOR", "ESFORCO CORTANTE", "FORCA NORMAL"):
            self.assertIn(titulo, texto)

    def test_nenhuma_cota_maior_que_o_esforco_real(self):
        """Rótulos sobrepostos já produziram "226,5" onde o esforço era 26,5."""
        from nucleo3d import mapa_esforcos as me
        mapa = me.mapa_de_esforcos(self.projeto)
        picos = {g: me and max(
            abs(v) for b in mapa["portico"]["barras"]
            for chave in (g + "_max", g + "_min")
            for v in b["diagramas"]["envoltoria"][chave]) for g in ("M", "V", "N")}
        maior = max(picos.values())
        for numero in _numeros_do_desenho(self.diagramas):
            self.assertLessEqual(numero, maior * 1.02,
                                 f"cota {numero} maior que o pico calculado {maior}")

    def test_empilhado_em_coluna(self):
        # lado a lado, três vãos de largura jogariam as coordenadas para longe demais
        self.assertGreater(self.diagramas.altura, self.diagramas.largura)
        self.assertLess(self.diagramas.largura, self.projeto.dados.vao * 1000 * 1.3)

    def test_sem_analise_explica_e_nao_quebra(self):
        d = desenhos.diagramas_portico(DadosGalpao())
        self.assertIn("Sem analise", _texto(d))
        self.assertGreater(len(d.entidades), 10)


class TestQuadro(BaseDesenhos):
    def test_uma_linha_por_elemento_ligacao_e_base(self):
        texto = _texto(self.quadro)
        for e in self.projeto.elementos:
            self.assertIn(e.perfil.split()[0], texto, e.nome)
        self.assertIn("Base do pilar", texto)
        for chave in self.projeto.ligacoes:
            self.assertIn(chave.split("-")[0][:8], texto.lower() + texto)

    def test_razoes_com_duas_casas(self):
        """A razão da tabela tem de ser a do cálculo, com duas casas.

        O mapa arredonda para três casas antes de o desenho arredondar para duas, então
        uma razão de 0,8253 pode sair como 0,83 ou 0,82 conforme o caminho — as duas
        grafias valem; o que não vale é a tabela mostrar outro número.
        """
        texto = _texto(self.quadro)
        for e in self.projeto.elementos:
            aceitas = {f"{e.razao:.2f}".replace(".", ","),
                       f"{round(e.razao, 3):.2f}".replace(".", ","),
                       desenhos._razao(round(e.razao, 3))}
            self.assertTrue(any(f"\n1\n{v}\n" in texto for v in aceitas),
                            f"{e.nome}: razão {e.razao:.4f} não aparece no quadro "
                            f"(esperava uma de {sorted(aceitas)})")

    def test_situacao_de_cada_peca(self):
        texto = _texto(self.quadro)
        self.assertIn("ATENDE", texto)
        self.assertEqual(self.projeto.ok, "NAO ATENDE" not in texto)

    def test_texto_cabe_na_coluna(self):
        largo = desenhos._cortar("Flexao Mx - combinacao de succao (mesa inferior "
                                 "comprimida)", 40.0, 2.8)
        self.assertLessEqual(len(largo) * 2.8 * 0.72, 40.0)
        self.assertTrue(largo.endswith("."))
        self.assertEqual(desenhos._cortar("W 410x38,8", 40.0, 2.8), "W 410x38,8")


class TestCatalogoEPrancha(unittest.TestCase):
    def test_desenhos_registrados(self):
        nomes = [n for n, *_ in desenhos.CATALOGO]
        self.assertIn("10-DIAGRAMAS-PORTICO", nomes)
        self.assertIn("11-QUADRO-DE-VERIFICACOES", nomes)

    def test_prancha_reune_os_dois(self):
        pr06 = [p for p in pranchas.COMPOSICAO if p[0] == 6]
        self.assertTrue(pr06, "falta a prancha dos diagramas")
        self.assertEqual(sorted(pr06[0][3]),
                         ["10-DIAGRAMAS-PORTICO", "11-QUADRO-DE-VERIFICACOES"])


def _numeros_do_desenho(d):
    """Valores numéricos dos textos do desenho (as cotas dos picos)."""
    import re
    saida = []
    for e in d.entidades:
        if "\nTEXT\n" not in e:
            continue
        for linha in e.splitlines():
            if re.fullmatch(r"\d{1,4},\d", linha.strip()):
                saida.append(float(linha.strip().replace(",", ".")))
    return saida


if __name__ == "__main__":
    unittest.main()
