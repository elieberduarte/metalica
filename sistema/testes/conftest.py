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


# ------------------------------------------------------------------ cada teste devolve o ambiente (14/11)
# REINCIDÊNCIA: o test_projetos.py (13/11, c1b17d1) e o test_duas_abas_modelo.py (14/11) apagavam METALICA_DADOS e
# recarregavam o app — os testes seguintes do mesmo processo gravavam em sistema/projetos, e quem pegava era só o
# test_testes_nao_gravam_nos_dados, quando a ordem (ou o xdist) o punha depois. Em 13/11 também o gerente de mentira do
# test_desenhos_vivos ficou no desenhos_vivos. Agora o teste que sai com o ambiente trocado falha NA HORA, pelo nome.
import sys  # noqa: E402

import pytest  # noqa: E402


def _metalica():
    return {k: v for k, v in os.environ.items() if k.startswith("METALICA_")}


def _dentro(pasta: str, de: str) -> bool:
    return os.path.normcase(os.path.abspath(pasta)).startswith(os.path.normcase(os.path.abspath(de)))


def _de_teste(f) -> bool:
    mod = (getattr(f, "__module__", "") or "").rsplit(".", 1)[-1]
    return mod.startswith("test_") or mod == "conftest"


@pytest.fixture(autouse=True)
def _o_teste_devolve_o_ambiente(request):
    """no fim de cada teste (depois do monkeypatch desfazer o que fez): METALICA_DADOS é o temporário daqui, as outras
    METALICA_* estão como antes, o app (se importado) grava numa pasta temporária (o arquivo pode pôr uma sua no
    setUpModule: a volta ao temporário daqui é conferida no fim do arquivo, _o_arquivo_devolve_o_app), e o desenhos_vivos
    não ficou com uma função de um arquivo de teste"""
    antes = _metalica()
    dv0 = sys.modules.get("desenhos_vivos")
    funcoes_antes = dict(getattr(dv0, "_funcoes", None) or {}) if dv0 is not None else None
    yield
    erros = []
    if os.environ.get("METALICA_DADOS") != _DADOS:
        erros.append("METALICA_DADOS = %r (o conftest pôs %r)" % (os.environ.get("METALICA_DADOS"), _DADOS))
    depois = _metalica()
    for k in sorted(set(antes) | set(depois)):
        if k != "METALICA_DADOS" and antes.get(k) != depois.get(k):
            erros.append("%s: %r → %r" % (k, antes.get(k), depois.get(k)))
    app = sys.modules.get("app")
    projetos = getattr(app, "PROJETOS", None) if app is not None else None
    fora_do_temp = isinstance(projetos, str) and not _dentro(projetos, tempfile.gettempdir())
    if fora_do_temp:
        erros.append("app.PROJETOS = %r (fora da pasta temporária: o app foi recarregado sem METALICA_DADOS?)" % projetos)
    dv = sys.modules.get("desenhos_vivos")
    for k, f in sorted((getattr(dv, "_funcoes", None) or {}).items()):
        if _de_teste(f):
            erros.append("desenhos_vivos._funcoes[%r] ficou com %r, de %s" % (k, f, getattr(f, "__module__", "?")))
    if erros:
        # devolve o ambiente antes de acusar: só o culpado falha, não os testes seguintes do mesmo processo em cascata
        for k in set(depois) - set(antes):
            os.environ.pop(k, None)
        os.environ.update(antes)
        os.environ["METALICA_DADOS"] = _DADOS
        if fora_do_temp and app is not None:
            import importlib
            importlib.reload(app)
        if dv is not None and funcoes_antes is not None:
            dv._funcoes.clear()
            dv._funcoes.update(funcoes_antes)
        elif dv is not None:
            for k in [k for k, f in dv._funcoes.items() if _de_teste(f)]:
                del dv._funcoes[k]
        pytest.fail("%s saiu com o ambiente dos testes trocado — devolva o que mudou: %s"
                    % (request.node.nodeid, "; ".join(erros)), pytrace=False)


@pytest.fixture(scope="module", autouse=True)
def _o_arquivo_devolve_o_app(request):
    """no fim de cada arquivo de teste (depois do tearDownModule dele): o app volta a gravar no temporário daqui — o
    arquivo que põe uma pasta própria no começo (test_regressoes_primeiro_uso_ifc) tem de devolver"""
    yield
    app = sys.modules.get("app")
    projetos = getattr(app, "PROJETOS", None) if app is not None else None
    if isinstance(projetos, str) and not _dentro(projetos, _DADOS):
        app.PROJETOS = os.path.abspath(_DADOS) if os.environ.get("METALICA_DADOS") == _DADOS else projetos
        pytest.fail("%s terminou com app.PROJETOS = %r, fora do temporário do conftest — devolva no fim do arquivo"
                    % (request.node.nodeid, projetos), pytrace=False)
