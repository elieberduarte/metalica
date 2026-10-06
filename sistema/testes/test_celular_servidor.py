# -*- coding: utf-8 -*-
"""Segurança do servidor do celular (celular/servidor.py): sem a chave nada responde, com a chave
nenhuma rota grava, só sai o que o pacote lista, o código do QR vale uma vez e por 5 minutos, o
aparelho removido perde o acesso na hora, tentativas demais são freadas e, desligado, nada escuta.

O servidor sobe só no 127.0.0.1 de uma porta livre (o de verdade escuta na rede)."""
import http.client
import json
import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celular import servidor as S                     # noqa: E402
from test_pacote_celular import _modelo               # noqa: E402


def _porta():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def cel(tmp_path):
    proj = tmp_path / "dados" / "obra"
    (proj / "detalhamento").mkdir(parents=True)
    (proj / "comercial").mkdir()
    (proj / "comercial" / "comercial.json").write_text("{}", encoding="utf-8")
    (proj / "projeto.json").write_text(json.dumps({"nome": "Obra Teste", "alterado": "2026-10-05T10:00:00"}), encoding="utf-8")
    (proj / "modelo.json").write_text(json.dumps(_modelo()), encoding="utf-8")
    arq = tmp_path / "dados" / "velha"
    arq.mkdir()
    (arq / "projeto.json").write_text(json.dumps({"nome": "Arquivada", "arquivado": True}), encoding="utf-8")
    c = S.Celular(str(tmp_path / "dados"), str(tmp_path / "trabalho"), porta=_porta(), host="127.0.0.1")
    c.ligar()
    yield c
    c.desligar()


def _pedir(c, caminho, metodo="GET", cookie=None, corpo=None):
    con = http.client.HTTPConnection("127.0.0.1", c.porta, timeout=10)
    cab = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
    if cookie:
        cab["Cookie"] = "%s=%s" % (S.COOKIE, cookie)
    con.request(metodo, caminho, body=corpo, headers=cab)
    r = con.getresponse()
    dados = r.read()
    con.close()
    return r.status, dict(r.getheaders()), dados


def _parear(c):
    cod = c.novo_codigo()["codigo"]
    st, cab, _ = _pedir(c, "/celular/parear?c=" + cod)
    assert st == 302
    cookie = cab["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return cookie.split(";")[0].split("=", 1)[1]


ROTAS = ["/celular/", "/celular/index.html", "/celular/celular.js", "/celular/visor3d.js", "/lib/three.module.js",
         "/celular/dados/projetos.json", "/celular/dados/obra/manifesto.json", "/celular/api/estado", "/"]


def test_sem_chave_nada_responde(cel):
    for rota in ROTAS:
        st, _cab, corpo = _pedir(cel, rota)
        assert st == 401, rota
        assert b"Obra Teste" not in corpo and b"obra" not in corpo.lower().replace(b"obras", b""), rota
    for falsa in ("abc.def", "x", "", "%s.%s" % ("0" * 12, "a" * 40)):
        assert _pedir(cel, "/celular/dados/projetos.json", cookie=falsa)[0] == 401


def test_com_chave_le_mas_nao_grava(cel):
    k = _parear(cel)
    st, _c, corpo = _pedir(cel, "/celular/dados/projetos.json", cookie=k)
    assert st == 200
    lista = json.loads(corpo)["projetos"]
    assert [p["slug"] for p in lista] == ["obra"]            # a arquivada não aparece
    for metodo in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        for rota in ("/celular/dados/projetos.json", "/api/projetos", "/celular/", "/api/projetos/obra/modelo"):
            assert _pedir(cel, rota, metodo, cookie=k, corpo=b"{}")[0] == 405, (metodo, rota)
            assert _pedir(cel, rota, metodo, corpo=b"{}")[0] == 405, (metodo, rota)
    for rota in ("/api/projetos", "/api/versao", "/editor", "/lib/BufferGeometryUtils.js", "/web/estilo.css"):
        assert _pedir(cel, rota, cookie=k)[0] == 404, rota
    assert _pedir(cel, "/celular/", cookie=k)[0] == 200
    assert _pedir(cel, "/lib/three.module.js", cookie=k)[0] == 200


def test_caminhos_para_fora_recusados(cel):
    k = _parear(cel)
    for rota in ("/celular/../app.py", "/celular/%2e%2e/app.py", "/celular/..%2fapp.py", "/celular/lib/../../app.py",
                 "/celular/dados/obra/../projeto.json", "/celular/dados/obra/..%2Fprojeto.json", "/celular/dados/../obra/manifesto.json",
                 "/celular/dados/obra/fonte.txt", "/celular/dados/obra/modelo.json", "/celular/dados/obra/comercial/comercial.json",
                 "/celular/dados/velha/manifesto.json", "/celular/dados/.celular/aparelhos.json", "/lib/../app.py",
                 "/celular/%5c..%5capp.py", "/celular/C:/Windows/win.ini"):
        st = _pedir(cel, rota, cookie=k)[0]
        assert st in (404, 401), (rota, st)


def test_pacote_preparado_e_so_o_listado(cel):
    k = _parear(cel)
    st, _c, corpo = _pedir(cel, "/celular/dados/obra/manifesto.json", cookie=k)
    assert st in (202, 200)
    for _ in range(100):                                    # o operário gera em segundo plano
        st, _c, corpo = _pedir(cel, "/celular/dados/obra/manifesto.json", cookie=k)
        if st == 200:
            break
        time.sleep(0.2)
    assert st == 200
    m = json.loads(corpo)
    nomes = {a["nome"] for a in m["arquivos"]}
    assert "modelo3d.mcel" in nomes and not any("comercial" in n for n in nomes)
    st, cab, mcel = _pedir(cel, "/celular/dados/obra/modelo3d.mcel", cookie=k)
    assert st == 200 and mcel[:4] == b"MCEL" and cab["ETag"].strip('"') == next(a["sha1"] for a in m["arquivos"] if a["nome"] == "modelo3d.mcel")
    # sem mudança no projeto, não refaz; com o modelo gravado de novo, fica velho e refaz
    assert not cel.velho("obra")
    modelo = os.path.join(cel.pasta_projetos, "obra", "modelo.json")
    os.utime(modelo, (time.time() + 5, time.time() + 5))
    assert cel.velho("obra")


def test_codigo_uma_vez_e_com_prazo(cel, monkeypatch):
    cod = cel.novo_codigo()["codigo"]
    assert _pedir(cel, "/celular/parear?c=" + cod)[0] == 302
    assert _pedir(cel, "/celular/parear?c=" + cod)[0] == 403              # já usado
    assert _pedir(cel, "/celular/parear?c=inventado")[0] == 403
    cod2 = cel.novo_codigo()["codigo"]
    agora = time.time()
    monkeypatch.setattr(S.time, "time", lambda: agora + S.VALIDADE_CODIGO + 1)
    assert _pedir(cel, "/celular/parear?c=" + cod2)[0] == 403             # vencido


def test_aparelho_removido_perde_acesso(cel):
    k = _parear(cel)
    assert _pedir(cel, "/celular/dados/projetos.json", cookie=k)[0] == 200
    ap = cel.aparelhos()
    assert len(ap) == 1 and ap[0]["nome"] == "iPhone" and "hash" in ap[0]
    assert k.split(".", 1)[1] not in json.dumps(ap)                        # no PC fica só o resumo
    cel.remover(ap[0]["id"])
    assert _pedir(cel, "/celular/dados/projetos.json", cookie=k)[0] == 401


def test_tentativas_demais_freadas(cel):
    for _ in range(S.MAX_FALHAS + 1):
        _pedir(cel, "/celular/dados/projetos.json", cookie="x.y")
    assert _pedir(cel, "/celular/dados/projetos.json", cookie="x.y")[0] == 429
    cod = cel.novo_codigo()["codigo"]
    assert _pedir(cel, "/celular/parear?c=" + cod)[0] == 429               # nem pareando, até passar a janela


def test_desligado_nada_escuta(tmp_path):
    porta = _porta()
    c = S.Celular(str(tmp_path), str(tmp_path / "t"), porta=porta, host="127.0.0.1")
    assert c.configuracao().get("ligado") is False and not c.ligado       # desligado por padrão
    c.ligar()
    assert _pedir(c, "/celular/")[0] == 401
    c.desligar()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", porta), timeout=2).close()
    assert S.Celular(str(tmp_path), str(tmp_path / "t"), porta=porta).configuracao()["ligado"] is False


def test_desligar_fecha_as_conexoes_abertas(tmp_path):
    """O navegador reaproveita a conexão (keep-alive): desligado, nem por ela algo responde."""
    c = S.Celular(str(tmp_path), str(tmp_path / "t"), porta=_porta(), host="127.0.0.1")
    c.ligar()
    con = http.client.HTTPConnection("127.0.0.1", c.porta, timeout=5)
    con.request("GET", "/celular/")
    r = con.getresponse()
    r.read()
    assert r.status == 401
    c.desligar()
    try:
        con.request("GET", "/celular/")
        st = con.getresponse().status
    except (OSError, http.client.HTTPException):
        st = None                                       # a conexão foi fechada
    con.close()
    assert st in (None, 503), st


def test_https_com_o_certificado_na_pasta(tmp_path):
    """Com tls/certificado.pem + chave.pem + nome.txt na pasta de trabalho, o servidor fala HTTPS e o QR
    leva ao nome do certificado (não ao IP). Certificado de teste gerado na hora pelo openssl."""
    import shutil, ssl, subprocess
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl não instalado")
    tls = tmp_path / "t" / "tls"
    tls.mkdir(parents=True)
    r = subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-days", "2",
                        "-subj", "/CN=localhost", "-keyout", str(tls / "chave.pem"), "-out", str(tls / "certificado.pem")],
                       capture_output=True)
    if r.returncode:
        pytest.skip("openssl não gerou o certificado: %s" % r.stderr[:200])
    (tls / "nome.txt").write_text("metalica.exemplo.com.br", encoding="utf-8")
    c = S.Celular(str(tmp_path), str(tmp_path / "t"), porta=_porta(), host="127.0.0.1")
    assert c.https
    assert c.novo_codigo()["url"].startswith("https://metalica.exemplo.com.br:%d/celular/parear?c=" % c.porta)
    c.ligar()
    try:
        ctx = ssl.create_default_context(cafile=str(tls / "certificado.pem"))
        con = http.client.HTTPSConnection("localhost", c.porta, timeout=5, context=ctx)
        con.request("GET", "/celular/")
        resp = con.getresponse()
        assert resp.status == 401                         # HTTPS, e sem a chave nada responde
        con.close()
        cod = c.novo_codigo()["codigo"]
        con = http.client.HTTPSConnection("localhost", c.porta, timeout=5, context=ctx)
        con.request("GET", "/celular/parear?c=" + cod)
        resp = con.getresponse()
        assert resp.status == 302 and "; Secure" in resp.getheader("Set-Cookie")   # em HTTPS o cookie é só seguro
        con.close()
        with pytest.raises(Exception):                    # HTTP puro na porta HTTPS não passa
            _pedir(c, "/celular/")
    finally:
        c.desligar()


def test_extensao_so_no_desenvolvimento():
    """O programa instalado (sem --dev) não carrega o celular; o empacotador o deixa de fora."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = open(os.path.join(base, "app.py"), encoding="utf-8").read()
    construir = open(os.path.join(os.path.dirname(base), "empacotar", "construir.py"), encoding="utf-8").read()
    assert '"celular"' in construir and '"acesso-celular*"' in construir
    if "def _extensoes_dev()" not in app:
        pytest.skip("o app.py desta cópia ainda não tem as extensões do desenvolvimento (estão só na cópia de trabalho)")
    i = app.index("def _extensoes_dev()")
    trecho = app[i:app.index("\ndef ", i + 10)]
    assert "if not DEV:" in trecho and trecho.index("if not DEV:") < trecho.index("import celular.web")
