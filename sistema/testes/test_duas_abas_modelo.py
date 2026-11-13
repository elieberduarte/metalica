# -*- coding: utf-8 -*-
"""Duas abas no 3D da mesma obra (D01 do usuario-desastrado, 13/11: "um Ctrl+S na aba B, até sem mudança nenhuma, faz a
aba A perder tudo dali em diante, com o botão mostrando '✓ Salvo'").

O servidor:
  1. o texto igual ao do disco (o Ctrl+S da aba B sem mexer em nada) não é gravação: o arquivo e a data ficam, e a aba A
     continua gravando;
  2. a gravação sobre uma versão velha é recusada com 409 e {"conflito": true, "alterado": <data do disco>} — a tela sabe
     que NADA foi gravado (antes era um 400 como outro erro qualquer, e a tela o tratava como gravado)."""
import http.client
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "testes"))


def _texto(nome, n=2):
    return json.dumps({"nome": nome, "entidades": [{"id": "e%d" % i, "tipo": "barra"} for i in range(n)]},
                      ensure_ascii=False).encode("utf-8")


def test_ctrl_s_sem_mudanca_na_aba_b_nao_derruba_a_aba_a():
    with tempfile.TemporaryDirectory() as raiz:
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            s = app.criar_projeto({"nome": "Duas abas", "tipo": "galpao", "dados": {"nome": "Duas abas", "vao": 18}})["slug"]
            aberto = app.salvar_modelo_cru(s, _texto("Obra"), None, 2)["alterado"]   # o que as duas abas carregaram
            caminho = app._gerente().caminho_modelo(s)
            time.sleep(1.1)                                                        # a data mudaria se gravasse
            b = app.salvar_modelo_cru(s, _texto("Obra"), aberto, 2)                # aba B: Ctrl+S sem mudança
            assert b.get("sem_mudanca") is True and b["alterado"] == aberto, b
            assert app._alterado_modelo(s) == aberto
            # a aba A apaga o P5 (uma peça a menos) e grava com a data que carregou: vai
            a = app.salvar_modelo_cru(s, _texto("Obra", 1), aberto, 1)
            assert not a.get("sem_mudanca")
            with open(caminho, "rb") as f:
                assert f.read() == _texto("Obra", 1)
        finally:
            del os.environ["METALICA_DADOS"]
            importlib.reload(app)


def test_gravacao_sobre_versao_velha_e_recusada_como_conflito():
    with tempfile.TemporaryDirectory() as raiz:
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            s = app.criar_projeto({"nome": "Conflito", "tipo": "galpao", "dados": {"nome": "Conflito", "vao": 18}})["slug"]
            aberto = app.salvar_modelo_cru(s, _texto("Obra"), None, 2)["alterado"]
            time.sleep(1.1)
            b = app.salvar_modelo_cru(s, _texto("Obra B", 3), aberto, 3)           # a aba B mudou e gravou
            try:
                app.salvar_modelo_cru(s, _texto("Obra A", 1), aberto, 1)           # a aba A, com a data velha
            except app.ModeloMaisNovo as e:
                assert e.alterado == b["alterado"] and "Nada foi gravado" in str(e)
            else:
                raise AssertionError("a gravação sobre a versão velha devia ser recusada")
            with open(app._gerente().caminho_modelo(s), "rb") as f:
                assert f.read() == _texto("Obra B", 3)                            # o da aba B ficou
        finally:
            del os.environ["METALICA_DADOS"]
            importlib.reload(app)


def test_a_rota_responde_409_com_conflito():
    """Pela rota de verdade (o editor manda X-Modelo-Cru e X-Base-Alterado): 409 e "conflito", não um 400 qualquer."""
    from verificar_editor import _porta_livre
    dados = tempfile.mkdtemp(prefix="metalica_duas_abas_")
    porta = _porta_livre()
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta),
                            "--dados", dados], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        def pedir(metodo, rota, corpo=None, cab=None):
            for _ in range(80):
                try:
                    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=30)
                    c.request(metodo, rota, body=corpo, headers=cab or {})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b"null")
                except (ConnectionError, OSError):
                    time.sleep(0.25)
            raise AssertionError("o servidor não respondeu")

        st, r = pedir("POST", "/api/projetos", json.dumps({"nome": "Rota", "tipo": "galpao", "dados": {"nome": "Rota", "vao": 18}}),
                      {"Content-Type": "application/json"})
        s = r["slug"]

        def gravar(texto, base=None):
            cab = {"Content-Type": "application/json; charset=utf-8", "X-Modelo-Cru": "1", "X-Entidades": "1"}
            if base is not None:
                cab["X-Base-Alterado"] = str(base)
            return pedir("POST", "/api/projetos/%s/modelo" % s, texto, cab)

        st, r = gravar(_texto("Obra"))
        assert st == 200, r
        aberto = r["alterado"]
        time.sleep(1.1)
        st, r = gravar(_texto("Obra"), aberto)                                    # sem mudança: 200, a data fica
        assert st == 200 and r.get("sem_mudanca") and r["alterado"] == aberto, r
        st, b = gravar(_texto("Obra B", 3), aberto)
        assert st == 200, b
        st, r = gravar(_texto("Obra A", 1), aberto)
        assert st == 409 and r.get("conflito") is True and r["alterado"] == b["alterado"], (st, r)
        # a escolha: "Abrir a versão gravada" (X-Para-Historico) não muda o disco; "Gravar as minhas por cima" (X-Por-Cima) grava
        cab = {"Content-Type": "application/json; charset=utf-8", "X-Modelo-Cru": "1", "X-Para-Historico": "1"}
        st, r = pedir("POST", "/api/projetos/%s/modelo" % s, _texto("Obra A", 1), cab)
        assert st == 200 and r["historico"] and r["alterado"] == b["alterado"], (st, r)
        cab = {"Content-Type": "application/json; charset=utf-8", "X-Modelo-Cru": "1", "X-Por-Cima": "1", "X-Base-Alterado": str(aberto)}
        st, r = pedir("POST", "/api/projetos/%s/modelo" % s, _texto("Obra A", 1), cab)
        assert st == 200 and r["historico"] and r["alterado"] != b["alterado"], (st, r)
        st, h = pedir("GET", "/api/projetos/%s/historico" % s)
        rot = [x["rotulo"] for x in h["historico"]]
        assert rot[0].startswith("antes de gravar por cima") and rot[1].startswith("edições não gravadas"), rot
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:                                                         # noqa: BLE001
            srv.kill()
        import shutil
        shutil.rmtree(dados, ignore_errors=True)


# ------------------------------------------------------------------ a escolha do usuário (13/11: "Escolher, com histórico")

def _historico(app, s):
    import gzip
    pasta = app._gerente()._pasta_historico(s)
    lista = app._gerente().listar_historico(s)
    return [(h["rotulo"], gzip.open(os.path.join(pasta, h["arquivo"])).read()) for h in lista]


def test_gravar_as_minhas_por_cima_guarda_a_outra_no_historico():
    """A aba desatualizada escolhe "Gravar as minhas por cima": grava mesmo com a base velha, e a versão que estava no
    disco (a da outra aba) vai antes para o histórico com o rótulo — dá para voltar pelo Restaurar."""
    with tempfile.TemporaryDirectory() as raiz:
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            s = app.criar_projeto({"nome": "Por cima", "tipo": "galpao", "dados": {"nome": "Por cima", "vao": 18}})["slug"]
            aberto = app.salvar_modelo_cru(s, _texto("Obra"), None, 2)["alterado"]
            time.sleep(1.1)
            app.salvar_modelo_cru(s, _texto("Obra B", 3), aberto, 3)                # a outra aba gravou
            r = app.salvar_modelo_cru(s, _texto("Obra A", 1), aberto, 1, por_cima=True)
            with open(app._gerente().caminho_modelo(s), "rb") as f:
                assert f.read() == _texto("Obra A", 1)                           # a desta aba no disco
            h = _historico(app, s)
            rot, conteudo = h[0]
            assert r["historico"] and rot.startswith("antes de gravar por cima") and conteudo == _texto("Obra B", 3), h[0]
            # o Restaurar volta à da outra aba
            app._gerente().restaurar_modelo(s, app._gerente().listar_historico(s)[0]["arquivo"])
            assert app.modelo_do_projeto(s)["documento"]["nome"] == "Obra B"
        finally:
            del os.environ["METALICA_DADOS"]
            importlib.reload(app)


def test_abrir_a_versao_gravada_guarda_as_minhas_no_historico():
    """"Abrir a versão gravada": as edições da aba desatualizada vão para o histórico com o rótulo; o modelo.json não muda."""
    with tempfile.TemporaryDirectory() as raiz:
        os.environ["METALICA_DADOS"] = raiz
        try:
            import app
            importlib.reload(app)
            s = app.criar_projeto({"nome": "Abrir", "tipo": "galpao", "dados": {"nome": "Abrir", "vao": 18}})["slug"]
            aberto = app.salvar_modelo_cru(s, _texto("Obra"), None, 2)["alterado"]
            time.sleep(1.1)
            b = app.salvar_modelo_cru(s, _texto("Obra B", 3), aberto, 3)
            r = app.guardar_edicoes_no_historico(s, _texto("Obra A", 1))
            assert r["alterado"] == b["alterado"]                                  # o modelo.json não mudou
            with open(app._gerente().caminho_modelo(s), "rb") as f:
                assert f.read() == _texto("Obra B", 3)
            rot, conteudo = _historico(app, s)[0]
            assert rot.startswith("edições não gravadas") and conteudo == _texto("Obra A", 1), rot
        finally:
            del os.environ["METALICA_DADOS"]
            importlib.reload(app)
