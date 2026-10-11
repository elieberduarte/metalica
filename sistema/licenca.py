# -*- coding: utf-8 -*-
"""A licença do Metálica (11/10/2026): o programa instalado só abre com uma licença válida neste computador.

A licença vem do serviço de licenças (servicos/licencas, um Worker da Cloudflare): a pessoa digita a chave
(MTL-XXXX-XXXX-XXXX) na primeira abertura, o serviço confere se a chave está ativa e se ainda há vaga de computador (2 por
chave) e devolve a licença assinada (Ed25519). O programa confere a assinatura com a chave pública abaixo, sem internet:
vale 30 dias e se renova sozinha a cada abertura com rede. Chave bloqueada ou computador liberado na tela das licenças →
a renovação é recusada e o programa volta à tela de ativação.

Só o programa instalado (`versao.CONGELADO`) exige a licença; rodando do código (desenvolvimento, testes, verificadores)
não. A verificação Ed25519 é a do RFC 8032 em Python puro: o programa instalado não leva a biblioteca `cryptography`.
"""
import base64
import datetime
import getpass
import hashlib
import json
import os
import platform
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

import versao

#: o serviço de licenças (o Worker metalica-licencas)
SERVICO = "https://metalica-licencas.elieber-lucas.workers.dev"
#: a chave pública Ed25519 (32 bytes em base64); a privada fica só no Worker
CHAVE_PUBLICA = "2aOrHl8gPxh6lYZMGrXTT1Y+XAoX7en9+lAIYDDZoNg="
#: de quanto em quanto tempo o programa aberto renova a licença
RENOVAR_A_CADA = 6 * 3600

if not versao.CONGELADO:
    # só fora do instalado (testes): o serviço e a chave de teste; no .exe não se troca nada por variável de ambiente
    SERVICO = os.environ.get("METALICA_LICENCAS") or SERVICO
    CHAVE_PUBLICA = os.environ.get("METALICA_LICENCA_PUBLICA") or CHAVE_PUBLICA


def exigida() -> bool:
    """o instalado sempre; rodando do código, só com METALICA_EXIGIR_LICENCA=1 (o teste da trava — só endurece)"""
    return versao.CONGELADO or os.environ.get("METALICA_EXIGIR_LICENCA") == "1"


# ------------------------------------------------------------------ Ed25519 (RFC 8032, 6: só a verificação)
_P = 2 ** 255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_RAIZ_M1 = pow(2, (_P - 1) // 4, _P)


def _somar(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _multiplicar(s, ponto):
    r = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            r = _somar(r, ponto)
        ponto = _somar(ponto, ponto)
        s >>= 1
    return r


def _iguais(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x(y, sinal):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


def _ponto(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _x(y, sinal)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def verificar_assinatura(publica: bytes, mensagem: bytes, assinatura: bytes) -> bool:
    if len(publica) != 32 or len(assinatura) != 64:
        return False
    A, R = _ponto(publica), _ponto(assinatura[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(assinatura[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(assinatura[:32] + publica + mensagem).digest(), "little") % _Q
    return _iguais(_multiplicar(s, _G), _somar(R, _multiplicar(h, A)))


# ------------------------------------------------------------------ o computador e o arquivo
def _b64url(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def impressao_da_maquina() -> str:
    """o identificador deste computador: o MachineGuid do Windows (o mesmo enquanto o Windows não é reinstalado),
    passado por um hash — o serviço nunca vê o valor original"""
    base = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
            base = str(winreg.QueryValueEx(k, "MachineGuid")[0])
    except (OSError, ImportError):
        import uuid
        base = "%012x" % uuid.getnode()
    return hashlib.sha256(("metalica:" + base).encode("utf-8")).hexdigest()[:32]


def _pasta() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, versao.NOME)


def arquivo() -> str:
    return os.environ.get("METALICA_LICENCA_ARQUIVO") if not versao.CONGELADO and os.environ.get("METALICA_LICENCA_ARQUIVO") \
        else os.path.join(_pasta(), "licenca.json")


def _ler() -> dict:
    try:
        with open(arquivo(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _gravar(dados: dict):
    os.makedirs(os.path.dirname(arquivo()), exist_ok=True)
    tmp = arquivo() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, arquivo())


# ------------------------------------------------------------------ o estado da licença
_CACHE = {"quando": 0.0, "estado": None}
_TRAVA = threading.Lock()


def ler_licenca(token: str) -> Optional[dict]:
    """o conteúdo da licença se a assinatura confere, senão None"""
    try:
        p, s = str(token or "").split(".")
        dados = _b64url(p)
        if not verificar_assinatura(base64.b64decode(CHAVE_PUBLICA), dados, _b64url(s)):
            return None
        return json.loads(dados.decode("utf-8"))
    except (ValueError, TypeError):
        return None


def _data(iso: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None


def estado(forcar: bool = False) -> dict:
    """{ok, pessoa, validade, dias_restantes, motivo, chave}: a licença deste computador agora (guardada por 1 min)"""
    with _TRAVA:
        if not forcar and _CACHE["estado"] is not None and time.time() - _CACHE["quando"] < 60:
            return dict(_CACHE["estado"])
        g = _ler()
        e = {"ok": False, "exigida": exigida(), "motivo": "", "pessoa": "", "validade": "", "dias_restantes": 0,
             "chave": g.get("chave", ""), "servico": SERVICO}
        if not g.get("licenca"):
            e["motivo"] = g.get("motivo_bloqueio") or "este computador ainda não tem licença do Metálica"
        else:
            p = ler_licenca(g["licenca"])
            fim = _data(p.get("validade")) if p else None
            if not p:
                e["motivo"] = "a licença gravada neste computador não é válida"
            elif p.get("maquina") != impressao_da_maquina():
                e["motivo"] = "a licença gravada é de outro computador"
            elif not fim or fim <= datetime.datetime.now(datetime.timezone.utc):
                e["motivo"] = "a licença venceu: o Metálica ficou mais de 30 dias sem conferir pela internet"
            else:
                e.update(ok=True, pessoa=p.get("pessoa", ""), validade=p.get("validade", ""), chave=p.get("chave", ""),
                         dias_restantes=max(0, (fim - datetime.datetime.now(datetime.timezone.utc)).days))
        _CACHE.update(quando=time.time(), estado=e)
        return dict(e)


def liberado() -> bool:
    """o programa pode abrir as telas: a licença não é exigida (desenvolvimento) ou está válida"""
    return not exigida() or estado()["ok"]


def _postar(rota: str, corpo: dict, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(SERVICO + rota, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Metalica/" + versao.VERSAO})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8"))
        except (ValueError, OSError):
            d = {}
        d.setdefault("erro", "o serviço de licenças recusou (%s)" % e.code)
        d["status"] = e.code
        return d


def _quem() -> dict:
    try:
        usuario = getpass.getuser()
    except Exception:                              # noqa: BLE001
        usuario = ""
    return {"maquina": impressao_da_maquina(), "nome_pc": platform.node(), "usuario": usuario, "versao": versao.VERSAO}


def ativar(chave: str) -> dict:
    """ativa este computador com a chave digitada; devolve o estado (com `erro` se o serviço recusou)"""
    try:
        r = _postar("/api/ativar", dict(_quem(), chave=str(chave or "").strip()))
    except OSError as e:
        return dict(estado(), erro="sem conexão com o serviço de licenças (%s) — confira a internet" % str(e)[:80])
    if r.get("erro") or not r.get("licenca"):
        return dict(estado(), erro=r.get("erro") or "o serviço de licenças não devolveu a licença")
    p = ler_licenca(r["licenca"])
    if not p:
        return dict(estado(), erro="a licença recebida não confere com a assinatura do Metálica")
    _gravar({"licenca": r["licenca"], "chave": p.get("chave", ""), "ativada": time.strftime("%Y-%m-%d %H:%M")})
    return estado(forcar=True)


def renovar() -> dict:
    """renova a licença (com rede); recusada (chave bloqueada, computador liberado) → apaga e o programa volta à ativação.
    Sem rede, nada muda: a licença gravada vale até a data dela"""
    g = _ler()
    if not g.get("licenca"):
        return estado()
    try:
        r = _postar("/api/renovar", dict(_quem(), licenca=g["licenca"]))
    except OSError:
        return estado()
    if r.get("licenca") and ler_licenca(r["licenca"]):
        g["licenca"] = r["licenca"]
        g["renovada"] = time.strftime("%Y-%m-%d %H:%M")
        _gravar(g)
    elif r.get("bloqueada"):
        _gravar({"chave": g.get("chave", ""), "motivo_bloqueio": r.get("erro") or "a licença foi bloqueada"})
    return estado(forcar=True)


def renovar_sempre():
    """a linha que renova a licença ao abrir e a cada RENOVAR_A_CADA, enquanto o programa está aberto"""
    def laco():
        time.sleep(5)
        while True:
            try:
                renovar()
            except Exception:                        # noqa: BLE001 — sem rede ou o serviço fora: tenta depois
                pass
            time.sleep(RENOVAR_A_CADA)
    threading.Thread(target=laco, daemon=True, name="licenca").start()


def cabecalho() -> dict:
    """o cabeçalho que o serviço pede na consulta da atualização"""
    return {"Authorization": "Licenca " + (_ler().get("licenca") or "")}


def token() -> str:
    return _ler().get("licenca") or ""
