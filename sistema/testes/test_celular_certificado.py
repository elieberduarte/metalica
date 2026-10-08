# -*- coding: utf-8 -*-
"""O certificado HTTPS do celular (celular/certificado.py), de verdade, contra o Pebble — o servidor
ACME de teste do Let's Encrypt — e o DNS de teste dele (pebble-challtestsrv) no lugar do Cloudflare:
o desafio DNS-01 é conferido como no Let's Encrypt, o certificado sai para o nome, e o servidor do
celular passa a falar HTTPS com ele.

Precisa dos executáveis do Pebble (variável PEBBLE_DIR, ou %TEMP%\\mob\\pebble); sem eles, pula.
Tudo só no 127.0.0.1."""
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PEBBLE_DIR = os.environ.get("PEBBLE_DIR") or os.path.join(tempfile.gettempdir(), "mob", "pebble")


def _exe(nome):
    for raiz, _d, arqs in os.walk(PEBBLE_DIR):
        if nome in arqs:
            return os.path.join(raiz, nome)
    return None


PEBBLE, CHALL = _exe("pebble.exe"), _exe("pebble-challtestsrv.exe")
pytestmark = [pytest.mark.skipif(not (PEBBLE and CHALL and os.path.isfile(os.path.join(PEBBLE_DIR, "pebble.minica.pem"))),
                                 reason="Pebble não instalado"),
              pytest.mark.skipif(not __import__("importlib").util.find_spec("cryptography"), reason="cryptography não instalada")]


def _porta():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def pebble():
    pasta = tempfile.mkdtemp(prefix="pebble_")
    p_acme, p_gestao, p_dns, p_chall = _porta(), _porta(), _porta(), _porta()
    cfg = {"pebble": {"listenAddress": "127.0.0.1:%d" % p_acme, "managementListenAddress": "127.0.0.1:%d" % p_gestao,
                      "certificate": os.path.join(PEBBLE_DIR, "localhost-cert.pem"), "privateKey": os.path.join(PEBBLE_DIR, "localhost-key.pem"),
                      "httpPort": 5002, "tlsPort": 5001, "ocspResponderURL": "", "externalAccountBindingRequired": False,
                      "retryAfter": {"authz": 1, "order": 1}, "keyAlgorithm": "ecdsa"}}
    caminho_cfg = os.path.join(pasta, "pebble.json")
    json.dump(cfg, open(caminho_cfg, "w"))
    amb = dict(os.environ, PEBBLE_VA_NOSLEEP="1", PEBBLE_WFE_NONCEREJECT="10")      # 10 % dos nonces recusados: exercita a repetição
    chall = subprocess.Popen([CHALL, "-dnsserver", "127.0.0.1:%d" % p_dns, "-management", "127.0.0.1:%d" % p_chall, "-http01", "",
                              "-https01", "", "-tlsalpn01", "", "-doh", "", "-defaultIPv4", "127.0.0.1", "-defaultIPv6", ""],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    peb = subprocess.Popen([PEBBLE, "-config", caminho_cfg, "-dnsserver", "127.0.0.1:%d" % p_dns],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb, cwd=pasta)
    ctx = ssl.create_default_context(cafile=os.path.join(PEBBLE_DIR, "pebble.minica.pem"))
    for _ in range(60):
        try:
            urllib.request.urlopen("https://localhost:%d/dir" % p_acme, context=ctx, timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)
    yield {"diretorio": "https://localhost:%d/dir" % p_acme, "contexto": ctx, "chall": "http://127.0.0.1:%d" % p_chall,
           "gestao": "https://localhost:%d" % p_gestao}
    peb.kill()
    chall.kill()
    time.sleep(0.5)
    shutil.rmtree(pasta, ignore_errors=True)


class DnsDeTeste:
    """O pebble-challtestsrv no lugar do Cloudflare (a mesma interface: por_txt, tirar_txt, apontar)."""

    def __init__(self, base):
        self.base = base
        self.apontados = {}

    def _post(self, rota, corpo):
        req = urllib.request.Request(self.base + rota, data=json.dumps(corpo).encode(), method="POST")
        urllib.request.urlopen(req, timeout=5).read()

    def por_txt(self, nome, valor):
        self._post("/set-txt", {"host": nome + ".", "value": valor})

    def tirar_txt(self, nome):
        self._post("/clear-txt", {"host": nome + "."})

    def apontar(self, nome, ip):
        self.apontados[nome] = ip
        self._post("/add-a", {"host": nome + ".", "addresses": [ip]})


def test_emite_e_o_servidor_fala_https(pebble, tmp_path):
    from celular import certificado as C
    from celular import servidor as S
    tls = tmp_path / "trabalho" / "tls"
    dns = DnsDeTeste(pebble["chall"])
    avisos = []
    r = C.obter(str(tls), "metalica.exemplo.com.br", "192.168.18.148", dns, diretorio=pebble["diretorio"],
                contexto=pebble["contexto"], esperar_dns=lambda n, v: None, avisar=avisos.append)
    assert r["nome"] == "metalica.exemplo.com.br" and r["valido_ate"]
    assert dns.apontados == {"metalica.exemplo.com.br": "192.168.18.148"}
    assert "certificado pronto" in avisos and any("TXT" in a for a in avisos)
    from cryptography import x509
    cert = x509.load_pem_x509_certificate((tls / "certificado.pem").read_bytes())
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert sans == ["metalica.exemplo.com.br"]
    assert not C.precisa_renovar(str(tls))                       # o do Pebble vale 90 dias
    # o servidor do celular com esse certificado: HTTPS, e o QR leva ao nome
    raiz = urllib.request.urlopen(pebble["gestao"] + "/roots/0", context=pebble["contexto"], timeout=5).read()
    intermed = urllib.request.urlopen(pebble["gestao"] + "/intermediates/0", context=pebble["contexto"], timeout=5).read()
    ca = tmp_path / "ca.pem"
    ca.write_bytes(raiz + b"\n" + intermed)
    c = S.Celular(str(tmp_path), str(tmp_path / "trabalho"), porta=_porta(), host="127.0.0.1")
    assert c.https and c.novo_codigo()["url"].startswith("https://metalica.exemplo.com.br:")
    c.ligar()
    try:
        ctx = ssl.create_default_context(cafile=str(ca))
        sock = socket.create_connection(("127.0.0.1", c.porta), timeout=5)
        with ctx.wrap_socket(sock, server_hostname="metalica.exemplo.com.br") as s:      # o nome do certificado confere
            s.sendall(b"GET /celular/ HTTP/1.1\r\nHost: metalica.exemplo.com.br\r\nConnection: close\r\n\r\n")
            resposta = s.recv(200)
        assert resposta.startswith(b"HTTP/1.1 401")
    finally:
        c.desligar()
    # renovar: a conta é a mesma, o certificado é outro
    antes = (tls / "certificado.pem").read_bytes()
    C.obter(str(tls), "metalica.exemplo.com.br", "192.168.18.148", dns, diretorio=pebble["diretorio"],
            contexto=pebble["contexto"], esperar_dns=lambda n, v: None)
    assert (tls / "certificado.pem").read_bytes() != antes


def test_configurar_pela_tela_religa_em_https(pebble, tmp_path, monkeypatch):
    """O que a tela do PC faz: nome + token → certificado → o servidor ligado volta em HTTPS e o QR leva ao nome."""
    from celular import certificado as C
    from celular import servidor as S
    dns = DnsDeTeste(pebble["chall"])

    class CloudflareFalso:
        def __init__(self, token):
            assert token == "token-de-teste"
        por_txt, tirar_txt, apontar = dns.por_txt, dns.tirar_txt, dns.apontar
    monkeypatch.setattr(C, "Cloudflare", CloudflareFalso)
    monkeypatch.setenv("METALICA_ACME_DIR", pebble["diretorio"])
    obter_original = C.obter
    monkeypatch.setattr(C, "obter", lambda *a, **k: obter_original(*a, contexto=pebble["contexto"], esperar_dns=lambda n, v: None,
                                                                    **{x: y for x, y in k.items() if x not in ("contexto", "esperar_dns")}))
    c = S.Celular(str(tmp_path), str(tmp_path / "trabalho"), porta=_porta(), host="127.0.0.1")
    c.ligar()
    try:
        assert not c.https and c.estado()["url"].startswith("http://")
        with pytest.raises(ValueError):
            c.configurar_https("", "")
        s = c.configurar_https("metalica.exemplo.com.br", "token-de-teste", em_fundo=False)
        assert s["ativo"] and s["situacao"] == "pronto", s
        e = c.estado()
        assert e["ligado"] and e["url"].startswith("https://metalica.exemplo.com.br:") and e["conexao_segura"]["valido_ate"]
        assert "token" not in json.dumps(e)                      # o token não sai na tela
        # o servidor religado fala TLS na mesma porta
        sock = socket.create_connection(("127.0.0.1", c.porta), timeout=5)
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with ctx.wrap_socket(sock, server_hostname="metalica.exemplo.com.br") as t:
            t.sendall(b"GET /celular/ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            assert t.recv(100).startswith(b"HTTP/1.1 401")
        c.remover_https()
        assert not c.https and c.estado()["url"].startswith("http://") and c.ligado
    finally:
        c.desligar()


def test_nome_invalido_recusado(tmp_path):
    from celular import certificado as C
    for nome in ("", "localhost", "metalica dominio.com", "../x.com", "metálica.com.br"):
        with pytest.raises(C.ErroCertificado):
            C.obter(str(tmp_path), nome, "192.168.0.2", DnsDeTeste("http://127.0.0.1:1"), diretorio="https://127.0.0.1:1/dir")
