# -*- coding: utf-8 -*-
"""O celular de qualquer lugar (20/10/2026): o PC envia para a nuvem as telas do celular e os pacotes das obras
ligadas na chave "Celular" da tela de projetos; o celular liberado lê de lá (servicos/celular, Worker
metalica-celular + R2), de qualquer rede e com este PC desligado.

* Quem envia é este PC, provando quem é com a licença dele (licenca.py). Só a licença marcada "envia obras"
  na tela de licenças pode gravar; qualquer licença pode mostrar o QR code que põe um celular nela.
* Só sobe o que mudou: cada arquivo vai uma vez, pelo SHA-1 do manifesto do pacote (o Worker confere o SHA-1).
* Com o envio ligado, um fio olha a cada minuto se alguma obra mudou (a mesma assinatura do pacote que o servidor
  da rede local usa: datas e tamanhos das fontes), se uma obra foi ligada ou desligada, ou se as telas mudaram.
  Obra desligada (ou arquivada) sai da nuvem no envio seguinte.
* A parte comercial não sobe: o pacote é uma lista fechada de arquivos (saida/pacote_celular.py).
"""
import hashlib
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Tuple

from celular.servidor import WEB, TELAS, LIB_LIBERADA

SERVICO = "https://metalica-celular.elieber-lucas.workers.dev"
INTERVALO = 60.0                         # s entre as conferências do fio
ESPERA_DEPOIS_DE_ERRO = 300.0            # s: falhou (sem internet…), tenta de novo depois disto
FORA_DA_NUVEM = {"fonte.txt"}            # do pacote, mas só serve ao PC


class ErroNuvem(Exception):
    pass


def _sha1(caminho: str) -> str:
    h = hashlib.sha1()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def telas() -> List[Tuple[str, str]]:
    """(rota no celular, arquivo no PC): o que o servidor da rede local também entrega."""
    out = []
    for nome in sorted(os.listdir(TELAS)):
        c = os.path.join(TELAS, nome)
        if os.path.isfile(c):
            out.append(("/celular/" + nome, c))
    lib = os.path.join(TELAS, "lib")
    for nome in sorted(os.listdir(lib)):
        if os.path.isfile(os.path.join(lib, nome)) and not nome.startswith("LICENSE"):
            out.append(("/celular/lib/" + nome, os.path.join(lib, nome)))
    out.append(("/visor3d/visor3d.js", os.path.join(WEB, "visor3d", "visor3d.js")))
    for nome in sorted(LIB_LIBERADA):
        out.append(("/lib/" + nome, os.path.join(WEB, "lib", nome)))
    return out


class Nuvem:
    def __init__(self, cel, servico: Optional[str] = None, token: Optional[Callable[[], str]] = None):
        self.cel = cel
        self.servico = (servico or os.environ.get("METALICA_NUVEM") or SERVICO).rstrip("/")
        if token is None:
            import licenca
            token = licenca.token
        self._token = token
        self._trava = threading.Lock()           # um envio por vez
        self._fio = None
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self.andamento = {"etapa": "", "fracao": None}
        self.erro = ""
        self._falhou_em = 0.0

    # ------------------------------------------------------------------ configuração

    def configuracao(self) -> dict:
        c = self.cel._ler("nuvem.json", {})
        return c if isinstance(c, dict) else {}

    def _gravar(self, **mudancas):
        c = self.configuracao()
        c.update(mudancas)
        self.cel._gravar("nuvem.json", c)

    @property
    def ligada(self) -> bool:
        return bool(self.configuracao().get("ligada"))

    def ligar(self, ligada: bool) -> dict:
        self._gravar(ligada=bool(ligada))
        if ligada:
            self.iniciar()
            self._acordar.set()                  # envia já, sem esperar o minuto
        return self.estado()

    def estado(self) -> dict:
        c = self.configuracao()
        return {"ligada": bool(c.get("ligada")), "servico": self.servico, "enviado": c.get("enviado") or "",
                "obras": len(c.get("obras") or {}), "bytes": c.get("bytes") or 0, "erro": self.erro,
                "enviando": self._trava.locked(), "etapa": self.andamento.get("etapa") or "",
                "fracao": self.andamento.get("fracao")}

    # ------------------------------------------------------------------ o serviço

    def _pedir(self, metodo: str, rota: str, corpo=None, tipo: str = "application/json", timeout: float = 60.0):
        tok = self._token() or ""
        if not tok:
            raise ErroNuvem("este computador não tem licença ativa — a licença é que dá o direito de enviar as obras")
        from versao import VERSAO
        dados = None
        if corpo is not None:
            dados = corpo if isinstance(corpo, (bytes, bytearray)) else json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        cab = {"Authorization": "Licenca " + tok, "User-Agent": "Metalica/" + VERSAO}   # o Cloudflare barra o agente do Python
        if dados is not None:
            cab["Content-Type"] = tipo
        req = urllib.request.Request(self.servico + rota, data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("erro")
            except (ValueError, OSError, AttributeError):
                msg = None
            raise ErroNuvem(msg or "a nuvem recusou (%s)" % e.code)
        except (urllib.error.URLError, OSError) as e:
            raise ErroNuvem("sem conexão com a nuvem (%s)" % getattr(e, "reason", e))

    def novo_codigo(self) -> dict:
        """O QR code que põe um celular na licença deste PC (5 minutos, uso único)."""
        return self._pedir("POST", "/pc/codigo", {})

    def na_nuvem(self) -> dict:
        return self._pedir("GET", "/pc/estado")

    def _subir(self, arquivos: List[Tuple[str, str]], etapa: str) -> int:
        """Envia os (sha1, caminho) que a nuvem ainda não tem; devolve os bytes enviados."""
        por_sha = {s: c for s, c in arquivos}
        faltam = []
        lista = list(por_sha)
        for i in range(0, len(lista), 500):
            faltam += self._pedir("POST", "/pc/faltam", {"sha1s": lista[i:i + 500]}).get("faltam") or []
        total = 0
        for k, s in enumerate(faltam):
            self.andamento = {"etapa": "%s — enviando %d de %d arquivo(s)" % (etapa, k + 1, len(faltam)), "fracao": None}
            with open(por_sha[s], "rb") as f:
                dados = f.read()
            if hashlib.sha1(dados).hexdigest() != s:
                raise ErroNuvem("o arquivo %s mudou durante o envio — tente de novo" % os.path.basename(por_sha[s]))
            self._pedir("PUT", "/pc/arquivo/" + s, dados, "application/octet-stream", timeout=600.0)
            total += len(dados)
        return total

    # ------------------------------------------------------------------ o envio

    def assinatura(self) -> str:
        """Muda quando uma obra muda, é ligada ou desligada, ou quando as telas do celular mudam."""
        partes = []
        for p in self.cel.projetos():
            partes.append(p["slug"] + "=" + self.cel._assinatura(p["slug"]))
        for rota, c in telas():
            try:
                st = os.stat(c)
                partes.append("%s:%d:%d" % (rota, int(st.st_mtime), st.st_size))
            except OSError:
                partes.append(rota + ":-")
        return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()

    def enviar(self, forcar: bool = False) -> dict:
        """Envia o que mudou: os pacotes das obras ligadas, a lista, as telas; tira da nuvem as obras desligadas."""
        with self._trava:
            try:
                r = self._enviar(forcar)
                self.erro = ""
                self._falhou_em = 0.0
                return r
            except Exception as e:                        # noqa: BLE001 — vai para a tela do PC
                self.erro = str(e)[:300]
                self._falhou_em = time.time()
                raise
            finally:
                self.andamento = {"etapa": "", "fracao": None}

    def _enviar(self, forcar: bool) -> dict:
        assinatura = self.assinatura()
        cfg = self.configuracao()
        ja = {} if forcar else dict(cfg.get("obras") or {})
        obras = self.cel.projetos()
        nuvem = set(self.na_nuvem().get("obras") or [])
        enviados, total_bytes, lista = 0, 0, []
        for i, p in enumerate(obras):
            slug = p["slug"]
            etapa = "%s (%d de %d)" % (p.get("nome") or slug, i + 1, len(obras))
            self.andamento = {"etapa": "Preparando " + etapa, "fracao": i / max(len(obras), 1)}
            self.cel.gerar_se_velho(slug)
            m = self.cel._manifesto(slug)
            if not m:
                continue
            m = dict(m, arquivos=[a for a in m.get("arquivos") or [] if a.get("nome") not in FORA_DA_NUVEM])
            versao = hashlib.sha1(json.dumps(m, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            total_bytes += sum(int(a.get("bytes") or 0) for a in m["arquivos"])
            if ja.get(slug) != versao or slug not in nuvem:
                pasta = os.path.join(self.cel.pacotes, slug)
                enviados += self._subir([(a["sha1"], os.path.join(pasta, *a["nome"].split("/"))) for a in m["arquivos"]],
                                        "Enviando " + etapa)
                self._pedir("PUT", "/pc/obra/" + urllib.parse.quote(slug, safe=""), m)
                ja[slug] = versao
            item = {k: v for k, v in p.items() if k not in ("situacao", "progresso", "erro")}
            item.update({"gerado": m.get("gerado"), "bytes": m.get("bytes"), "numeros": m.get("numeros") or {}, "atual": True})
            lista.append(item)
        locais = {p["slug"] for p in obras}
        tirar = sorted((nuvem | set(ja)) - locais)
        for slug in tirar:
            self.andamento = {"etapa": "Tirando da nuvem: " + slug, "fracao": None}
            self._pedir("DELETE", "/pc/obra/" + urllib.parse.quote(slug, safe=""))
            ja.pop(slug, None)
        self.andamento = {"etapa": "Enviando as telas do celular", "fracao": None}
        mapa = {rota: _sha1(c) for rota, c in telas()}
        enviados += self._subir([(mapa[rota], c) for rota, c in telas()], "Telas do celular")
        self._pedir("PUT", "/pc/telas", mapa)
        from versao import VERSAO
        self._pedir("PUT", "/pc/indice", {"formato": 1, "projetos": lista, "computador": socket.gethostname(), "programa": VERSAO})
        if tirar or enviados:
            try:
                self._pedir("POST", "/pc/limpar", {}, timeout=120.0)
            except ErroNuvem:
                pass                                       # limpar fica para o próximo envio
        enviado = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._gravar(obras=ja, enviado=enviado, assinatura=assinatura, bytes=total_bytes)
        return {"obras": len(lista), "enviados_bytes": enviados, "tiradas": tirar, "enviado": enviado}

    # ------------------------------------------------------------------ em segundo plano

    def iniciar(self):
        if self._fio and self._fio.is_alive():
            return
        self._parar.clear()
        self._fio = threading.Thread(target=self._vigiar, name="celular-nuvem", daemon=True)
        self._fio.start()

    def enviar_ja(self) -> dict:
        """O botão "Enviar agora": o fio envia já (em segundo plano), sem esperar o minuto."""
        self.iniciar()
        self._acordar.set()
        return self.estado()

    def parar(self):
        self._parar.set()
        self._acordar.set()

    def _vigiar(self):
        while not self._parar.is_set():
            try:
                if not self.ligada:
                    self._acordar.clear()
                else:
                    cfg = self.configuracao()
                    pode = not self._falhou_em or time.time() - self._falhou_em > ESPERA_DEPOIS_DE_ERRO or self._acordar.is_set()
                    if pode and (self._acordar.is_set() or cfg.get("assinatura") != self.assinatura() or self.erro):
                        self._acordar.clear()
                        self.enviar()
            except Exception:                              # noqa: BLE001 — o erro fica em self.erro, para a tela
                pass
            self._acordar.wait(INTERVALO)
