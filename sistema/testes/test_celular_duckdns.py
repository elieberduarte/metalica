# -*- coding: utf-8 -*-
"""O subdomínio grátis do DuckDNS para a conexão segura do celular (celular/certificado.py, 19/10).

Para quem não tem domínio próprio: <nome>.duckdns.org aponta para o IP interno do PC e o desafio
DNS-01 do Let's Encrypt entra e sai pelo TXT do DuckDNS. Sem rede: um DuckDNS de mentira no lugar
da internet confere o que o programa manda. (O caminho inteiro até o certificado, contra o Pebble,
está em test_celular_certificado.py — este arquivo não depende dele.)"""
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _porta():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p



def _duck_falso(monkeypatch, resposta=b"OK"):
    """O DuckDNS de mentira: guarda os pedidos e responde OK (ou KO)."""
    from urllib.parse import parse_qs, urlparse
    from celular import certificado as C
    pedidos = []

    def pedir(url, *a, **k):
        u = urlparse(url)
        pedidos.append((u.netloc + u.path, {k: v[0] for k, v in parse_qs(u.query).items()}))
        return 200, {}, resposta
    monkeypatch.setattr(C, "_pedir", pedir)
    return C, pedidos


def test_duckdns_aponta_e_poe_e_tira_o_txt(monkeypatch):
    C, pedidos = _duck_falso(monkeypatch)
    d = C.DuckDNS("tok-123")
    d.apontar("metalica-vizin.duckdns.org", "192.168.18.213")
    d.por_txt("_acme-challenge.metalica-vizin.duckdns.org", "valor-do-desafio")
    d.tirar_txt("_acme-challenge.metalica-vizin.duckdns.org")
    assert [p[0] for p in pedidos] == ["www.duckdns.org/update"] * 3
    assert pedidos[0][1] == {"domains": "metalica-vizin", "token": "tok-123", "ip": "192.168.18.213"}   # IP interno, sem proxy
    assert pedidos[1][1] == {"domains": "metalica-vizin", "token": "tok-123", "txt": "valor-do-desafio"}
    assert pedidos[2][1]["clear"] == "true" and pedidos[2][1]["domains"] == "metalica-vizin"


def test_duckdns_recusa_vira_erro_que_diz_o_que_conferir(monkeypatch):
    C, _p = _duck_falso(monkeypatch, resposta=b"KO")
    with pytest.raises(C.ErroCertificado, match="subdomínio"):
        C.DuckDNS("errado").apontar("metalica-vizin.duckdns.org", "192.168.18.213")
    with pytest.raises(C.ErroCertificado, match="DuckDNS"):
        C.DuckDNS("tok").apontar("metalica.exemplo.com.br", "192.168.18.213")


def test_o_nome_escolhe_o_provedor():
    from celular import certificado as C
    assert isinstance(C.provedor_dns("metalica-vizin.duckdns.org", "t"), C.DuckDNS)
    assert isinstance(C.provedor_dns("Metalica-Vizin.DuckDNS.org.", "t"), C.DuckDNS)
    assert isinstance(C.provedor_dns("metalica.exemplo.com.br", "t"), C.Cloudflare)


def test_configurar_com_duckdns_usa_o_duckdns(tmp_path, monkeypatch):
    """O que a tela do PC faz com um nome .duckdns.org: aponta e tira o certificado pelo DuckDNS."""
    from celular import certificado as C
    from celular import servidor as S
    usados = []

    def obter(pasta, nome, ip, dns, **k):
        usados.append(type(dns).__name__)
        raise C.ErroCertificado("parado aqui de propósito")
    monkeypatch.setattr(C, "obter", obter)
    c = S.Celular(str(tmp_path), str(tmp_path / "trabalho"), porta=_porta(), host="127.0.0.1")
    s = c.configurar_https("metalica-vizin.duckdns.org", "tok-123", em_fundo=False)
    assert usados == ["DuckDNS"] and s["situacao"] == "erro" and "de propósito" in s["mensagem"]
