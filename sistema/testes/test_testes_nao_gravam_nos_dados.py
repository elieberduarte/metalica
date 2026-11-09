# -*- coding: utf-8 -*-
"""Os testes não gravam na pasta de dados de verdade (GESTÃO N.6, 09/11).

Desde 04/11 a pasta de dados é C:\\Metálica\\dados (METALICA_DADOS) e o app a usa também quando o pytest o importa.
O test_ifc_pintura chamava a rota do IFC sem pasta de teste: criava `teste-pintura/ifc/teste-pintura.ifc` lá, a tela de
Projetos mostrava a obra "Teste pintura" e ela voltava a cada bateria. Agora o conftest.py troca METALICA_DADOS por uma
pasta temporária antes de qualquer teste importar o app, e o test_ifc_pintura usa a pasta dele."""
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def test_o_app_dos_testes_usa_pasta_temporaria():
    import app
    pasta = os.path.normcase(os.path.abspath(app.PROJETOS))
    assert pasta.startswith(os.path.normcase(os.path.abspath(tempfile.gettempdir()))), app.PROJETOS
    assert "metalica-dados-teste-" in pasta, app.PROJETOS


def test_bateria_nao_cria_obra_na_pasta_de_dados(tmp_path):
    # o caso de 09/11: a pasta de dados de fora (aqui uma vazia) continua vazia depois do test_ifc_pintura
    dados = tmp_path / "dados"
    dados.mkdir()
    env = dict(os.environ, METALICA_DADOS=str(dados), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings",
                        os.path.join(AQUI, "test_ifc_pintura.py")],
                       cwd=BASE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    sobras = sorted(os.path.relpath(os.path.join(dp, n), dados) for dp, ds, fs in os.walk(dados) for n in ds + fs)
    assert not sobras, f"o teste gravou na pasta de dados: {sobras[:10]}"
