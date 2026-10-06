# -*- coding: utf-8 -*-
"""O certificado HTTPS do acesso pelo celular (a cópia para a obra pede conexão segura).

Opção (a) da missão celular: um nome do domínio do usuário (ex.: metalica.dominio.com.br) aponta, no
DNS do Cloudflare, para o IP do computador **na rede interna**; nada fica exposto à internet. O
certificado é do Let's Encrypt, tirado por desafio de DNS (DNS-01, RFC 8555): o programa põe um
registro TXT `_acme-challenge.<nome>` pela API do Cloudflare, o Let's Encrypt confere e emite. A
renovação é igual, quando faltam menos de 30 dias.

Grava em `<pasta de trabalho>/tls/`: `certificado.pem` (com a cadeia), `chave.pem`, `nome.txt`, a
chave da conta ACME (`conta.pem`) e a configuração do Cloudflare (`cloudflare.json`, com o token —
fora do OneDrive e fora do git, como a lista de aparelhos).

Só a biblioteca `cryptography` além da padrão (chaves P-256, assinatura ES256 e o pedido CSR).
"""
import base64
import datetime
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

LETS_ENCRYPT = "https://acme-v02.api.letsencrypt.org/directory"
LETS_ENCRYPT_TESTE = "https://acme-staging-v02.api.letsencrypt.org/directory"
CLOUDFLARE = "https://api.cloudflare.com/client/v4"
RENOVAR_COM_DIAS = 30


class ErroCertificado(Exception):
    pass


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _json_b64(obj) -> str:
    return _b64(json.dumps(obj, separators=(",", ":"), sort_keys=False).encode("utf-8"))


# ------------------------------------------------------------------ chaves

def _chave_nova():
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.generate_private_key(ec.SECP256R1())


def _pem_da_chave(chave) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def _ler_chave(caminho: str):
    from cryptography.hazmat.primitives import serialization
    with open(caminho, "rb") as f:
        return serialization.load_pem_private_key(f.read(), None)


def _jwk(chave) -> dict:
    n = chave.public_key().public_numbers()
    return {"crv": "P-256", "kty": "EC", "x": _b64(n.x.to_bytes(32, "big")), "y": _b64(n.y.to_bytes(32, "big"))}


def _impressao(jwk: dict) -> str:
    """Impressão digital da chave da conta (RFC 7638): entra na resposta ao desafio."""
    canonico = json.dumps({k: jwk[k] for k in ("crv", "kty", "x", "y")}, separators=(",", ":"), sort_keys=True)
    return _b64(hashlib.sha256(canonico.encode()).digest())


def _assinar_es256(chave, dados: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    der = chave.sign(dados, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _csr(chave, nome: str) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    pedido = (x509.CertificateSigningRequestBuilder()
              .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nome)]))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName(nome)]), critical=False)
              .sign(chave, hashes.SHA256()))
    return pedido.public_bytes(serialization.Encoding.DER)


def validade(caminho_cert: str) -> Optional[datetime.datetime]:
    """Até quando vale o certificado gravado (UTC), ou None."""
    try:
        from cryptography import x509
        with open(caminho_cert, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        return cert.not_valid_after_utc
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ HTTP

def _pedir(url: str, metodo="GET", corpo: Optional[bytes] = None, cabecalhos: Optional[dict] = None,
           contexto: Optional[ssl.SSLContext] = None, prazo: float = 30.0):
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos or {}))
    req.add_header("User-Agent", "Metalica-celular/1")
    try:
        with urllib.request.urlopen(req, timeout=prazo, context=contexto) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


# ------------------------------------------------------------------ ACME

class ClienteAcme:
    """O mínimo do RFC 8555 para um nome com DNS-01."""

    def __init__(self, diretorio: str, chave_conta, contexto: Optional[ssl.SSLContext] = None, contato: str = ""):
        self.contexto = contexto
        st, _h, corpo = _pedir(diretorio, contexto=contexto)
        if st != 200:
            raise ErroCertificado("o Let's Encrypt não respondeu (%s)" % st)
        self.dir = json.loads(corpo)
        self.chave = chave_conta
        self.jwk = _jwk(chave_conta)
        self.kid = None
        self.nonce = None
        self.contato = contato

    def _novo_nonce(self):
        st, h, _ = _pedir(self.dir["newNonce"], "HEAD", contexto=self.contexto)
        self.nonce = h.get("Replay-Nonce") or h.get("replay-nonce")

    def _post(self, url: str, carga, tentativa=0):
        """POST assinado (JWS ES256). `carga` None é o POST-as-GET (corpo vazio)."""
        if not self.nonce:
            self._novo_nonce()
        protegido = {"alg": "ES256", "nonce": self.nonce, "url": url}
        if self.kid:
            protegido["kid"] = self.kid
        else:
            protegido["jwk"] = self.jwk
        p64 = _json_b64(protegido)
        c64 = "" if carga is None else _json_b64(carga)
        assinatura = _b64(_assinar_es256(self.chave, ("%s.%s" % (p64, c64)).encode("ascii")))
        corpo = json.dumps({"protected": p64, "payload": c64, "signature": assinatura}).encode()
        st, h, resp = _pedir(url, "POST", corpo, {"Content-Type": "application/jose+json"}, self.contexto)
        self.nonce = h.get("Replay-Nonce") or h.get("replay-nonce")
        if st == 400 and b"badNonce" in resp and tentativa < 3:
            return self._post(url, carga, tentativa + 1)
        if st >= 400:
            try:
                det = json.loads(resp).get("detail") or resp[:200]
            except ValueError:
                det = resp[:200]
            raise ErroCertificado("Let's Encrypt recusou (%s): %s" % (st, det))
        return st, h, resp

    def conta(self):
        carga = {"termsOfServiceAgreed": True}
        if self.contato:
            carga["contact"] = ["mailto:" + self.contato]
        _st, h, _ = self._post(self.dir["newAccount"], carga)
        self.kid = h.get("Location") or h.get("location")

    def emitir(self, nome: str, chave_cert, por_txt: Callable[[str, str], None], tirar_txt: Callable[[str], None],
               esperar_dns: Callable[[str, str], None], avisar: Callable[[str], None] = lambda t: None) -> bytes:
        """Pedido → desafio DNS-01 → certificado (PEM com a cadeia)."""
        if not self.kid:
            self.conta()
        avisar("pedindo o certificado")
        _st, h, corpo = self._post(self.dir["newOrder"], {"identifiers": [{"type": "dns", "value": nome}]})
        pedido_url = h.get("Location") or h.get("location")
        pedido = json.loads(corpo)
        registro = "_acme-challenge." + nome
        try:
            for autz_url in pedido["authorizations"]:
                _st, _h, a = self._post(autz_url, None)
                autz = json.loads(a)
                if autz.get("status") == "valid":
                    continue
                desafio = next((d for d in autz["challenges"] if d["type"] == "dns-01"), None)
                if not desafio:
                    raise ErroCertificado("o Let's Encrypt não ofereceu o desafio de DNS")
                chave_aut = desafio["token"] + "." + _impressao(self.jwk)
                valor = _b64(hashlib.sha256(chave_aut.encode()).digest())
                avisar("pondo o registro TXT no DNS")
                por_txt(registro, valor)
                avisar("esperando o DNS espalhar")
                esperar_dns(registro, valor)
                avisar("o Let's Encrypt está conferindo")
                self._post(desafio["url"], {})
                self._aguardar(autz_url, ("valid",), "a conferência do domínio")
            avisar("emitindo")
            self._post(pedido["finalize"], {"csr": _b64(_csr(chave_cert, nome))})
            final = self._aguardar(pedido_url, ("valid",), "a emissão")
            _st, _h, pem = self._post(final["certificate"], None)
            return pem
        finally:
            try:
                tirar_txt(registro)
            except Exception:                                       # noqa: BLE001 — limpeza; o TXT velho não atrapalha
                pass

    def _aguardar(self, url, estados, o_que, prazo=180.0):
        t0 = time.time()
        while time.time() - t0 < prazo:
            _st, h, corpo = self._post(url, None)
            obj = json.loads(corpo)
            if obj.get("status") in estados:
                return obj
            if obj.get("status") == "invalid":
                det = json.dumps(obj.get("error") or obj.get("challenges") or obj, ensure_ascii=False)[:300]
                raise ErroCertificado("%s falhou: %s" % (o_que, det))
            time.sleep(min(float(h.get("Retry-After") or 2), 10))
        raise ErroCertificado("%s demorou demais" % o_que)


# ------------------------------------------------------------------ Cloudflare (DNS)

class Cloudflare:
    """O DNS do domínio no Cloudflare, por um token de API restrito (Zona → DNS → Editar)."""

    def __init__(self, token: str, base: str = CLOUDFLARE):
        self.token = token
        self.base = base
        self._zonas = {}

    def _api(self, metodo, caminho, corpo=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        st, _h, resp = _pedir(self.base + caminho, metodo, dados,
                              {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            obj = json.loads(resp)
        except ValueError:
            obj = {}
        if st >= 400 or not obj.get("success", False):
            erros = "; ".join(e.get("message", "") for e in obj.get("errors") or []) or ("HTTP %s" % st)
            raise ErroCertificado("Cloudflare: " + erros)
        return obj.get("result")

    def zona(self, nome: str) -> str:
        """A zona (domínio) do nome: tenta do mais comprido ao mais curto (a.b.dominio.com.br → …)."""
        partes = nome.split(".")
        for i in range(len(partes) - 1):
            candidato = ".".join(partes[i:])
            if candidato in self._zonas:
                return self._zonas[candidato]
            r = self._api("GET", "/zones?name=" + candidato)
            if r:
                self._zonas[candidato] = r[0]["id"]
                return r[0]["id"]
        raise ErroCertificado("o domínio de %s não está nesta conta do Cloudflare (ou o token não dá acesso a ele)" % nome)

    def _registros(self, zona, tipo, nome):
        return self._api("GET", "/zones/%s/dns_records?type=%s&name=%s" % (zona, tipo, nome)) or []

    def por_txt(self, nome, valor):
        z = self.zona(nome)
        self._api("POST", "/zones/%s/dns_records" % z, {"type": "TXT", "name": nome, "content": valor, "ttl": 60})

    def tirar_txt(self, nome):
        z = self.zona(nome)
        for r in self._registros(z, "TXT", nome):
            self._api("DELETE", "/zones/%s/dns_records/%s" % (z, r["id"]))

    def apontar(self, nome, ip):
        """Registro A do nome para o IP interno do computador, sem o proxy do Cloudflare (o celular
        tem de falar direto com o PC na rede)."""
        z = self.zona(nome)
        corpo = {"type": "A", "name": nome, "content": ip, "ttl": 60, "proxied": False}
        atuais = self._registros(z, "A", nome)
        if atuais:
            if atuais[0].get("content") != ip or atuais[0].get("proxied"):
                self._api("PUT", "/zones/%s/dns_records/%s" % (z, atuais[0]["id"]), corpo)
        else:
            self._api("POST", "/zones/%s/dns_records" % z, corpo)


def esperar_dns_publico(nome: str, valor: str, prazo: float = 180.0):
    """Espera o TXT aparecer no DNS público (consulta pelo DNS sobre HTTPS do Cloudflare)."""
    t0 = time.time()
    while time.time() - t0 < prazo:
        try:
            st, _h, r = _pedir("https://cloudflare-dns.com/dns-query?name=%s&type=TXT" % nome,
                               cabecalhos={"Accept": "application/dns-json"}, prazo=10)
            if st == 200 and any(valor in (a.get("data") or "") for a in json.loads(r).get("Answer") or []):
                time.sleep(5)
                return
        except (OSError, ValueError):
            pass
        time.sleep(5)
    raise ErroCertificado("o registro TXT não apareceu no DNS em %d s" % prazo)


# ------------------------------------------------------------------ o processo inteiro

def precisa_renovar(pasta_tls: str) -> bool:
    v = validade(os.path.join(pasta_tls, "certificado.pem"))
    return v is None or v - datetime.datetime.now(datetime.timezone.utc) < datetime.timedelta(days=RENOVAR_COM_DIAS)


def obter(pasta_tls: str, nome: str, ip: str, dns, diretorio: str = LETS_ENCRYPT,
          contexto: Optional[ssl.SSLContext] = None, esperar_dns: Callable = esperar_dns_publico,
          avisar: Callable[[str], None] = lambda t: None, contato: str = "") -> dict:
    """Aponta o nome para o IP e tira (ou renova) o certificado. `dns` tem por_txt/tirar_txt/apontar."""
    nome = nome.strip().lower().rstrip(".")
    if not nome or "." not in nome or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in nome):
        raise ErroCertificado("nome inválido: %r (ex.: metalica.seudominio.com.br)" % nome)
    os.makedirs(pasta_tls, exist_ok=True)
    avisar("apontando %s para %s" % (nome, ip))
    dns.apontar(nome, ip)
    caminho_conta = os.path.join(pasta_tls, "conta.pem")
    if os.path.exists(caminho_conta):
        conta = _ler_chave(caminho_conta)
    else:
        conta = _chave_nova()
        with open(caminho_conta, "wb") as f:
            f.write(_pem_da_chave(conta))
    acme = ClienteAcme(diretorio, conta, contexto, contato)
    chave_cert = _chave_nova()
    pem = acme.emitir(nome, chave_cert, dns.por_txt, dns.tirar_txt, esperar_dns, avisar)
    for arq, dados in (("chave.pem.novo", _pem_da_chave(chave_cert)), ("certificado.pem.novo", pem)):
        with open(os.path.join(pasta_tls, arq), "wb") as f:
            f.write(dados)
    os.replace(os.path.join(pasta_tls, "chave.pem.novo"), os.path.join(pasta_tls, "chave.pem"))
    os.replace(os.path.join(pasta_tls, "certificado.pem.novo"), os.path.join(pasta_tls, "certificado.pem"))
    with open(os.path.join(pasta_tls, "nome.txt"), "w", encoding="utf-8") as f:
        f.write(nome)
    v = validade(os.path.join(pasta_tls, "certificado.pem"))
    avisar("certificado pronto")
    return {"nome": nome, "ip": ip, "valido_ate": v.isoformat() if v else None}
