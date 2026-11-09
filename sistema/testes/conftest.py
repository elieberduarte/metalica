# -*- coding: utf-8 -*-
"""Os testes nunca gravam na pasta de dados de verdade (GESTÃO N.6, 09/11).

Desde 04/11 a pasta de dados é C:\\Metálica\\dados (METALICA_DADOS), e o app a lê ao ser importado: um teste que chamava
uma rota sem pasta própria (o test_ifc_pintura) criava a obra "Teste pintura" na tela de Projetos a cada bateria. Aqui,
antes de qualquer teste importar o app, METALICA_DADOS passa a ser uma pasta temporária desta rodada (uma por processo
do pytest-xdist), apagada no fim. A bateria inteira passa com ela vazia (conferido em 09/11: nenhum teste depende dos
projetos de verdade)."""
import atexit
import os
import shutil
import tempfile

_DADOS = tempfile.mkdtemp(prefix="metalica-dados-teste-")
os.environ["METALICA_DADOS"] = _DADOS
atexit.register(shutil.rmtree, _DADOS, True)
