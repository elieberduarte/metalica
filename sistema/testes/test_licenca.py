# -*- coding: utf-8 -*-
"""A licença do programa instalado (licenca.py, 11/10/2026): a verificação Ed25519 em Python puro pelos vetores do RFC 8032
e o estado da licença gravada (válida, adulterada, de outro computador, vencida)."""
import base64
import datetime
import json

import pytest

import licenca

# RFC 8032, 7.1 — testes 1 (mensagem vazia) e 2 (um byte)
VETORES = [
    ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


@pytest.mark.parametrize("pub, msg, sig", VETORES)
def test_vetores_do_rfc_8032(pub, msg, sig):
    pub, msg, sig = bytes.fromhex(pub), bytes.fromhex(msg), bytes.fromhex(sig)
    assert licenca.verificar_assinatura(pub, msg, sig)
    assert not licenca.verificar_assinatura(pub, msg + b"x", sig)                     # outra mensagem
    assert not licenca.verificar_assinatura(pub, msg, sig[:-1] + bytes([sig[-1] ^ 1]))  # assinatura mexida


@pytest.fixture
def chaves(monkeypatch, tmp_path):
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization
    priv = ed.Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(licenca, "CHAVE_PUBLICA", base64.b64encode(pub).decode())
    arq = tmp_path / "licenca.json"
    monkeypatch.setattr(licenca, "arquivo", lambda: str(arq))
    monkeypatch.setattr(licenca, "exigida", lambda: True)

    def emitir(maquina=None, dias=30, chave="MTL-AAAA-BBBB-CCCC"):
        agora = datetime.datetime.now(datetime.timezone.utc)
        p = json.dumps({"v": 1, "chave": chave, "maquina": maquina or licenca.impressao_da_maquina(), "pessoa": "Fulano",
                        "emitida": agora.isoformat(), "validade": (agora + datetime.timedelta(days=dias)).isoformat()}).encode()
        b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
        return b(p) + "." + b(priv.sign(p))

    def gravar(tok):
        arq.write_text(json.dumps({"licenca": tok}), encoding="utf-8")
        return licenca.estado(forcar=True)
    return emitir, gravar


def test_licenca_valida_libera(chaves):
    emitir, gravar = chaves
    e = gravar(emitir())
    assert e["ok"] and e["pessoa"] == "Fulano" and 28 <= e["dias_restantes"] <= 30 and licenca.liberado()


def test_sem_arquivo_adulterada_outra_maquina_e_vencida(chaves):
    emitir, gravar = chaves
    assert not licenca.estado(forcar=True)["ok"]                                       # sem arquivo
    tok = emitir()
    p, s = tok.split(".")
    assert "não é válida" in gravar(p[:-2] + ("A" if p[-2] != "A" else "B") + p[-1] + "." + s)["motivo"]
    assert "outro computador" in gravar(emitir(maquina="0" * 32))["motivo"]
    assert "venceu" in gravar(emitir(dias=-1))["motivo"]
    assert not licenca.liberado()


def test_fora_do_instalado_nao_exige(monkeypatch):
    monkeypatch.delenv("METALICA_EXIGIR_LICENCA", raising=False)
    assert not licenca.exigida() and licenca.liberado()


def test_impressao_da_maquina_e_estavel():
    a = licenca.impressao_da_maquina()
    assert a == licenca.impressao_da_maquina() and len(a) == 32
