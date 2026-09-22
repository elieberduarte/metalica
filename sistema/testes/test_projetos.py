# -*- coding: utf-8 -*-
"""Testes do gerenciador de projetos (projetos.py) e das rotas em app.py."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados                    # noqa: E402
from projetos import Projetos, slug, LIXEIRA, ARQUIVO   # noqa: E402


def test_slug():
    assert slug("Galpão da Fazenda São João") == "galpão-da-fazenda-são-joão"   # acento fica
    assert slug("  ") == "projeto"
    assert slug("A/B\\C:D") == "abcd"
    assert "/" not in slug("../x") and ".." not in slug("../x")


def test_criar_listar_abrir():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        assert g.listar() == []
        r = g.criar("Galpão do João", cliente="João", local="Cascavel/PR")
        assert r["slug"] and os.path.isdir(os.path.join(raiz, r["slug"]))
        assert r["tipo"] == "galpao" and r["nome"] == "Galpão do João" and not r["tem_dados"]
        p = g.ler(r["slug"])
        assert p["cliente"] == "João" and p["criado"] == p["alterado"]
        lista = g.listar()
        assert len(lista) == 1 and lista[0]["slug"] == r["slug"]
        # mesmo nome de novo: outra pasta, sem sobrescrever
        r2 = g.criar("Galpão do João")
        assert r2["slug"] != r["slug"] and len(g.listar()) == 2


def test_nome_obrigatorio_e_pasta_invalida():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        for nome in ("", "   ", None):
            try:
                g.criar(nome)
            except ErroDeDados:
                pass
            else:
                raise AssertionError("nome vazio devia ser recusado")
        for ruim in ("", "..", "modelos", ".lixeira", "../fora"):
            try:
                g.ler(ruim)
            except ErroDeDados:
                pass
            else:
                raise AssertionError("pasta %r devia ser recusada" % ruim)


def test_dados_do_dimensionamento_acompanham_identificacao():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        s = g.criar("Teste")["slug"]
        r = g.salvar_dados(s, {"nome": "Teste renomeado", "cliente": "ACME", "vao": 20, "comprimento": 40})
        assert r["tem_dados"] and r["vao"] == 20 and r["nome"] == "Teste renomeado" and r["cliente"] == "ACME"
        p = g.ler(s)
        assert p["dados"]["comprimento"] == 40 and p["alterado"] >= p["criado"]
        # rascunho incompleto também é aceito: quem valida é o cálculo
        g.salvar_dados(s, {"nome": "", "vao": ""})
        assert g.ler(s)["nome"] == "Teste renomeado"      # nome vazio não apaga o nome


def test_renomear_duplicar_excluir():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        s = g.criar("Um")["slug"]
        g.salvar_dados(s, {"nome": "Um", "vao": 12})
        os.makedirs(os.path.join(raiz, s, "memorial"))
        open(os.path.join(raiz, s, "memorial", "m.pdf"), "wb").write(b"%PDF")
        r = g.renomear(s, "Dois")
        assert r["nome"] == "Dois" and r["slug"] == "dois" and not os.path.exists(os.path.join(raiz, s))
        assert g.ler("dois")["dados"]["nome"] == "Dois"
        c = g.duplicar("dois")
        assert c["slug"] != "dois" and c["nome"] == "Dois (cópia)"
        assert os.path.exists(os.path.join(raiz, c["slug"], "memorial", "m.pdf"))
        assert any(e["pasta"] == "memorial" for e in c["entregas"])
        e = g.excluir("dois")
        assert not os.path.exists(os.path.join(raiz, "dois"))
        assert os.path.isdir(e["lixeira"]) and e["lixeira"].startswith(os.path.join(raiz, LIXEIRA))
        assert [p["slug"] for p in g.listar()] == [c["slug"]]


def test_modelo_3d_do_projeto():
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        s = g.criar("Com modelo")["slug"]
        assert g.abrir_modelo(s) is None and not g.resumo(s)["tem_modelo"]
        doc = {"nome": "Com modelo", "entidades": [{"tipo": "barra"}, {"tipo": "chapa"}], "camadas": {}}
        r = g.salvar_modelo(s, doc)
        assert r["entidades"] == 2
        assert g.abrir_modelo(s)["entidades"][1]["tipo"] == "chapa"
        assert g.resumo(s)["tem_modelo"]
        assert not os.path.exists(os.path.join(raiz, s, "modelo.json.parcial"))


def test_pasta_antiga_e_adotada():
    """Entregas geradas antes do gerenciador (pasta com memorial/, sem projeto.json)
    aparecem na lista e ganham o projeto.json ao serem lidas."""
    with tempfile.TemporaryDirectory() as raiz:
        os.makedirs(os.path.join(raiz, "galpao-antigo", "memorial"))
        os.makedirs(os.path.join(raiz, "qualquer-coisa"))          # pasta do usuário: fora
        os.makedirs(os.path.join(raiz, "modelos"))                 # reservada: fora
        g = Projetos(raiz)
        lista = g.listar()
        assert [p["slug"] for p in lista] == ["galpao-antigo"]
        assert os.path.exists(os.path.join(raiz, "galpao-antigo", ARQUIVO))
        assert g.ler("galpao-antigo")["tipo"] == "galpao"


def test_rotas_do_servidor():
    """As rotas de app.py com uma pasta de dados temporária."""
    import importlib
    with tempfile.TemporaryDirectory() as raiz:
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            r = app.criar_projeto({"nome": "Pela rota", "tipo": "galpao",
                                   "dados": {"nome": "Pela rota", "vao": 18, "comprimento": 30}})
            s = r["slug"]
            assert app.projeto_completo(s)["projeto"]["dados"]["vao"] == 18
            assert app.acao_de_projeto(s, "dados", {"dados": {"nome": "Pela rota", "vao": 22}})["vao"] == 22
            assert app.acao_de_projeto(s, "modelo", {"documento": {"entidades": []}})["entidades"] == 0
            assert app.modelo_do_projeto(s)["existe"]
            assert app.acao_de_projeto(s, "renomear", {"nome": "Outra"})["nome"] == "Outra"
            try:
                app.acao_de_projeto("outra", "explodir", {})
            except ErroDeDados:
                pass
            else:
                raise AssertionError("ação desconhecida devia ser recusada")
            # entrega dentro do projeto
            resp = app.gerar_saidas({"dados": {"nome": "Outra", "vao": 20, "comprimento": 40},
                                     "saidas": ["lista"], "projeto": "outra"})
            assert resp["pasta"] == os.path.join(raiz, "outra")
            assert any(e["pasta"] == "lista" for e in app._gerente().resumo("outra")["entregas"])
        finally:
            del os.environ["METALICA_DADOS"]
            importlib.reload(app)


def test_gravacao_simultanea_nao_emenda_arquivo():
    """Autosave do CAD e vista nova gravando o mesmo desenho ao mesmo tempo: o arquivo
    final é um dos dois, inteiro — nunca metade de um e o fim do outro."""
    import threading
    with tempfile.TemporaryDirectory() as raiz:
        g = Projetos(raiz)
        s = g.criar("Simultâneo")["slug"]
        grande = {"nome": "x", "entidades": [{"tipo": "linha", "a": [i, 0], "b": [i, 1]} for i in range(60000)]}
        pequeno = {"nome": "x", "entidades": grande["entidades"][:100]}
        erros = []

        def grava(d):
            try:
                for _ in range(3):
                    g.salvar_desenho(s, "corte", d)
            except Exception as e:                   # noqa: BLE001
                erros.append(e)
        fios = [threading.Thread(target=grava, args=(d,)) for d in (grande, pequeno, grande)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()
        assert not erros
        assert len(g.abrir_desenho(s, "corte")["entidades"]) in (100, 60000)
        assert not [a for a in os.listdir(os.path.join(raiz, s, "desenhos-2d")) if a.endswith(".parcial")]


def test_troca_espera_arquivo_em_uso():
    """Outro processo (OneDrive, antivírus) segurando o destino: a troca insiste em vez
    de falhar com WinError 32."""
    import threading
    import time
    from projetos import _gravar_json
    with tempfile.TemporaryDirectory() as raiz:
        alvo = os.path.join(raiz, "a.json")
        _gravar_json(alvo, {"v": 1})
        if os.name != "nt":
            return
        import ctypes
        # GENERIC_READ, FILE_SHARE_READ (sem FILE_SHARE_DELETE): a troca por cima falha
        h = ctypes.windll.kernel32.CreateFileW(alvo, 0x80000000, 1, None, 3, 0x80, None)
        assert h not in (0, -1)
        threading.Timer(0.6, lambda: ctypes.windll.kernel32.CloseHandle(h)).start()
        t0 = time.monotonic()
        _gravar_json(alvo, {"v": 2})
        assert 0.4 < time.monotonic() - t0 < 6
        with open(alvo, encoding="utf-8") as f:
            assert json.load(f)["v"] == 2


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
