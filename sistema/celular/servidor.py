# -*- coding: utf-8 -*-
"""O servidor do celular: as telas de consulta e os pacotes dos projetos, pela rede local.

O servidor do programa (app.py) só atende o próprio computador, e isso não muda. Este é um
**segundo servidor, separado**, que só existe com a chave "Acesso pelo celular" ligada:

* **Somente leitura por construção.** Só GET e HEAD; qualquer outro método é 405. Só as rotas
  `/celular/…` (as telas, os pacotes) e os dois arquivos do Three.js que o 3D usa. Ele lê a pasta
  dos pacotes e o `projeto.json` para a lista; não chama nada que grave num projeto.
* **Pareamento.** O computador mostra um QR com um código de uso único (5 minutos). O celular
  troca o código por uma chave própria do aparelho, guardada num cookie que o JavaScript não lê.
  No computador fica só o resumo SHA-256 da chave, na lista de aparelhos, que pode remover um.
* **Sem a chave, nada responde**: 401, sem nomes de projeto. Muitas tentativas erradas do mesmo
  endereço são freadas (429).
* **Pacotes** (saida/pacote_celular.py) numa pasta de trabalho fora do OneDrive, refeitos em
  segundo plano quando o projeto muda (o celular que pede um pacote velho recebe o atual).

A parte comercial não entra: o pacote é uma lista fechada de arquivos.
"""
import hashlib
import hmac
import http.server
import json
import mimetypes
import os
import queue
import re
import secrets
import socket
import threading
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(AQUI), "web")
TELAS = os.path.join(WEB, "celular")

PORTA_PADRAO = 8767
VALIDADE_CODIGO = 300.0             # s
COOKIE = "mcel"
#: Tentativas sem chave válida, por endereço, antes de frear (na janela abaixo).
MAX_FALHAS = 60
JANELA_FALHAS = 600.0
#: Arquivos do Three.js que as telas do celular importam (mais nada de web/lib).
LIB_LIBERADA = {"three.module.js", "OrbitControls.js"}
TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png",
         ".pdf": "application/pdf", ".mcel": "application/octet-stream", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8",
         ".webmanifest": "application/manifest+json; charset=utf-8"}


def pasta_de_trabalho(pasta_projetos: str, teste: bool = False) -> str:
    """Onde ficam os pacotes e a lista de aparelhos. Fora do OneDrive (são refeitos do projeto
    quando preciso); num teste (`--dados` de pasta temporária), dentro dela."""
    if os.environ.get("METALICA_CELULAR_DIR"):
        return os.environ["METALICA_CELULAR_DIR"]
    if teste:
        return os.path.join(pasta_projetos, ".celular")
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Metálica", "celular")


def enderecos_da_rede() -> List[str]:
    """IPv4 deste computador na rede local (o principal primeiro)."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))           # não envia nada: só escolhe a interface de saída
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    ips = [ip for ip in out if not ip.startswith(("127.", "169.254."))]

    # a rede de casa/escritório primeiro: com VPN ligada (o NordVPN dá 10.5.0.x) a interface de saída é
    # a da VPN, que o celular não enxerga; o Hyper-V/WSL costuma usar 172.x
    def ordem(ip):
        a, b = (int(x) for x in ip.split(".")[:2])
        return 0 if (a, b) == (192, 168) else 1 if a == 172 and 16 <= b <= 31 else 2 if a == 10 else 3
    return sorted(ips, key=ordem) or ["127.0.0.1"]


def _nome_do_aparelho(agente: str) -> str:
    a = agente or ""
    if "iPad" in a:
        return "iPad"
    if "iPhone" in a:
        return "iPhone"
    m = re.search(r"Android [\d.]+; ([^;)]+)", a)
    if m:
        modelo = m.group(1).strip()
        return ("Android " + modelo) if modelo and modelo != "K" else "Android"
    if "Macintosh" in a:
        return "Mac / iPad"
    if "Windows" in a:
        return "Computador Windows"
    return "Aparelho"


class Celular:
    """O acesso pelo celular de um programa: estado, aparelhos, códigos, pacotes e o servidor."""

    def __init__(self, pasta_projetos: str, pasta_trabalho: str, porta: int = PORTA_PADRAO,
                 host: Optional[str] = None, https: Optional[bool] = None):
        self.pasta_projetos = pasta_projetos
        self.trabalho = pasta_trabalho
        self.pacotes = os.path.join(pasta_trabalho, "pacotes")
        self.host = host or os.environ.get("METALICA_CELULAR_HOST") or "0.0.0.0"
        self.porta = int(os.environ.get("METALICA_CELULAR_PORTA") or porta)
        # HTTPS (a cópia para a obra pede conexão segura): o certificado do nome da rede interna em
        # tls/certificado.pem + tls/chave.pem, e o nome em tls/nome.txt (ex.: metalica.dominio.com.br)
        self.tls = os.path.join(pasta_trabalho, "tls")
        self.https = self._tem_certificado() if https is None else https
        self._trava = threading.RLock()
        self._codigos: Dict[str, float] = {}
        self._falhas: Dict[str, List[float]] = {}
        self._servidor = None
        self._fio = None
        self._fila: "queue.Queue[str]" = queue.Queue()
        self._situacao: Dict[str, dict] = {}         # slug -> {"situacao", "progresso", "erro"}
        self._operario = None
        self._vigia = None
        self._parar = threading.Event()
        self._geracao = 0
        self._https_situacao: dict = {}
        os.makedirs(self.pacotes, exist_ok=True)

    # ------------------------------------------------------------------ configuração e aparelhos

    def _ler(self, nome, padrao):
        try:
            with open(os.path.join(self.trabalho, nome), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return padrao

    def _gravar(self, nome, dados):
        os.makedirs(self.trabalho, exist_ok=True)
        c = os.path.join(self.trabalho, nome)
        with open(c + ".tmp", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        os.replace(c + ".tmp", c)

    def _tem_certificado(self) -> bool:
        return all(os.path.isfile(os.path.join(self.tls, n)) for n in ("certificado.pem", "chave.pem"))

    def nome_na_rede(self) -> Optional[str]:
        """O nome do certificado (o QR leva a ele, e não ao IP: o certificado é do nome)."""
        try:
            with open(os.path.join(self.tls, "nome.txt"), encoding="utf-8") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def _endereco_base(self, ip: str) -> str:
        if self.https and self.nome_na_rede():
            return "https://%s:%d" % (self.nome_na_rede(), self.porta)
        return "%s://%s:%d" % ("https" if self.https else "http", ip, self.porta)

    def aparelhos(self) -> List[dict]:
        return self._ler("aparelhos.json", [])

    def configuracao(self) -> dict:
        return self._ler("config.json", {"ligado": False})

    @property
    def ligado(self) -> bool:
        return self._servidor is not None

    def estado(self) -> dict:
        ips = enderecos_da_rede()
        return {"ligado": self.ligado, "porta": self.porta, "enderecos": ips, "https": self.https,
                "nome": self.nome_na_rede(), "url": self._endereco_base(ips[0]) + "/celular/",
                "aparelhos": [{k: a.get(k) for k in ("id", "nome", "criado", "visto", "ip")} for a in self.aparelhos()],
                "pacotes": {s: dict(v) for s, v in self._situacao.items()}, "conexao_segura": self.estado_https()}

    def novo_codigo(self) -> dict:
        """Código de uso único para o QR (5 minutos). Gerar outro não invalida o anterior antes do prazo."""
        codigo = secrets.token_urlsafe(9)
        agora = time.time()
        with self._trava:
            self._codigos = {c: t for c, t in self._codigos.items() if t > agora}
            self._codigos[codigo] = agora + VALIDADE_CODIGO
        ips = enderecos_da_rede()
        urls = [self._endereco_base(ip) + "/celular/parear?c=" + codigo for ip in ips]
        return {"codigo": codigo, "validade_s": int(VALIDADE_CODIGO), "url": urls[0], "urls": list(dict.fromkeys(urls))}

    def parear(self, codigo: str, agente: str, ip: str) -> Optional[str]:
        """Troca o código pela chave do aparelho (o valor do cookie) — ou None se o código não vale."""
        agora = time.time()
        with self._trava:
            validade = self._codigos.pop(codigo or "", None)
            if not validade or validade < agora:
                return None
            ident = secrets.token_hex(6)
            segredo = secrets.token_urlsafe(32)
            lista = self.aparelhos()
            lista.append({"id": ident, "nome": _nome_do_aparelho(agente), "hash": hashlib.sha256(segredo.encode()).hexdigest(),
                          "criado": time.strftime("%Y-%m-%dT%H:%M:%S"), "visto": time.strftime("%Y-%m-%dT%H:%M:%S"), "ip": ip})
            self._gravar("aparelhos.json", lista)
        return "%s.%s" % (ident, segredo)

    def remover(self, ident: str) -> dict:
        with self._trava:
            lista = [a for a in self.aparelhos() if a.get("id") != ident]
            self._gravar("aparelhos.json", lista)
        return self.estado()

    def renomear(self, ident: str, nome: str) -> dict:
        with self._trava:
            lista = self.aparelhos()
            for a in lista:
                if a.get("id") == ident:
                    a["nome"] = str(nome or "")[:60] or a["nome"]
            self._gravar("aparelhos.json", lista)
        return self.estado()

    def autenticar(self, valor: str, ip: str) -> Optional[dict]:
        """O aparelho dono do cookie, ou None. Compara o resumo em tempo constante."""
        ident, _, segredo = (valor or "").partition(".")
        if not ident or not segredo:
            return None
        resumo = hashlib.sha256(segredo.encode()).hexdigest()
        for a in self.aparelhos():
            if a.get("id") == ident and hmac.compare_digest(a.get("hash", ""), resumo):
                agora = time.strftime("%Y-%m-%dT%H:%M:%S")
                if (a.get("visto") or "")[:15] != agora[:15] or a.get("ip") != ip:      # grava no máximo a cada ~10 min
                    with self._trava:
                        lista = self.aparelhos()
                        for b in lista:
                            if b.get("id") == ident:
                                b["visto"], b["ip"] = agora, ip
                        self._gravar("aparelhos.json", lista)
                return a
        return None

    def falhou(self, ip: str) -> bool:
        """Conta uma tentativa sem chave; True quando o endereço passou do limite."""
        agora = time.time()
        with self._trava:
            l = [t for t in self._falhas.get(ip, []) if t > agora - JANELA_FALHAS]
            l.append(agora)
            self._falhas[ip] = l
            return len(l) > MAX_FALHAS

    def freado(self, ip: str) -> bool:
        agora = time.time()
        return len([t for t in self._falhas.get(ip, []) if t > agora - JANELA_FALHAS]) > MAX_FALHAS

    # ------------------------------------------------------------------ projetos e pacotes

    def projetos(self) -> List[dict]:
        """Os projetos da pasta de dados (sem os arquivados e sem os do pré-moldado), com o que já
        se sabe do pacote de cada um."""
        out = []
        try:
            nomes = os.listdir(self.pasta_projetos)
        except OSError:
            return []
        for slug in nomes:
            pasta = os.path.join(self.pasta_projetos, slug)
            if slug.startswith((".", "_")) or slug in ("modelos",) or not os.path.isdir(pasta):
                continue
            try:
                with open(os.path.join(pasta, "projeto.json"), encoding="utf-8") as f:
                    p = json.load(f)
            except (OSError, ValueError):
                continue
            if self._fora_da_lista(p):
                continue
            item = {"slug": slug, "nome": p.get("nome") or slug, "cliente": p.get("cliente") or "",
                    "alterado": p.get("alterado"), "revisao": (p.get("dados_resumo") or {}).get("revisao") or "",
                    "tem_modelo": os.path.exists(os.path.join(pasta, "modelo.json"))}
            m = self._manifesto(slug)
            if m:
                item.update({"gerado": m.get("gerado"), "bytes": m.get("bytes"), "numeros": m.get("numeros") or {},
                             "atual": not self.velho(slug)})
            item.update(self._situacao.get(slug) or {})
            out.append(item)
        out.sort(key=lambda i: str(i.get("alterado") or ""), reverse=True)
        return out

    def _pasta_projeto(self, slug: str) -> Optional[str]:
        s = os.path.basename(str(slug or "").replace("\\", "/"))
        if not s or s.startswith((".", "_")):
            return None
        p = os.path.join(self.pasta_projetos, s)
        try:
            with open(os.path.join(p, "projeto.json"), encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            return None
        if self._fora_da_lista(dados):                  # o que a lista não mostra também não se abre pelo nome
            return None
        return p

    @staticmethod
    def _fora_da_lista(p: dict) -> bool:
        return bool(p.get("arquivado")) or p.get("tipo") == "premoldado" or p.get("area") == "premoldado"

    def _manifesto(self, slug: str) -> Optional[dict]:
        try:
            with open(os.path.join(self.pacotes, slug, "manifesto.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _assinatura(self, slug: str) -> str:
        """Datas e tamanhos de tudo de que o pacote sai: mudou um, o pacote está velho."""
        pasta = self._pasta_projeto(slug)
        if not pasta:
            return ""
        from saida.pacote_celular import RESUMOS
        fontes = ["projeto.json", "modelo.json", "detalhamento/lista-de-materiais.json", "detalhamento/resumo-numeros.json",
                  "desenhos-2d/pranchas.desenho.json"] + ["detalhamento/" + a for a, _t in RESUMOS]
        partes = []
        for rel in fontes:
            c = os.path.join(pasta, rel)
            try:
                st = os.stat(c)
                partes.append("%s:%d:%d" % (rel, int(st.st_mtime), st.st_size))
            except OSError:
                partes.append(rel + ":-")
        return hashlib.sha1("|".join(partes).encode()).hexdigest()

    def velho(self, slug: str) -> bool:
        try:
            with open(os.path.join(self.pacotes, slug, "fonte.txt"), encoding="utf-8") as f:
                return f.read().strip() != self._assinatura(slug)
        except OSError:
            return True

    def pedir_pacote(self, slug: str) -> dict:
        """Situação do pacote; se falta ou está velho, entra na fila de geração."""
        if not self._pasta_projeto(slug):
            return {"situacao": "inexistente"}
        sit = self._situacao.get(slug)
        if sit and sit.get("situacao") in ("na fila", "preparando"):
            return dict(sit)
        if self.velho(slug):
            with self._trava:
                self._situacao[slug] = {"situacao": "na fila", "progresso": 0.0}
            self._fila.put(slug)
            self._garantir_operario()
            return dict(self._situacao[slug])
        return {"situacao": "pronto"}

    def gerar_agora(self, slug: str) -> dict:
        """Gera (ou refaz) o pacote neste fio — para os testes e para o operário."""
        from saida.pacote_celular import gerar_pacote
        pasta = self._pasta_projeto(slug)
        assinatura = self._assinatura(slug)
        destino = os.path.join(self.pacotes, slug)

        def progresso(k, n):
            with self._trava:
                self._situacao[slug] = {"situacao": "preparando", "progresso": round(0.1 + 0.8 * k / max(n, 1), 2)}
        with self._trava:
            self._situacao[slug] = {"situacao": "preparando", "progresso": 0.05}
        m = gerar_pacote(pasta, destino, slug, progresso)
        with open(os.path.join(destino, "fonte.txt"), "w", encoding="utf-8") as f:
            f.write(assinatura)
        with self._trava:
            self._situacao.pop(slug, None)
        return m

    def _garantir_operario(self):
        with self._trava:
            if self._operario and self._operario.is_alive():
                return
            self._operario = threading.Thread(target=self._trabalhar, name="celular-pacotes", daemon=True)
            self._operario.start()

    def _trabalhar(self):
        while not self._parar.is_set():
            try:
                slug = self._fila.get(timeout=2.0)
            except queue.Empty:
                continue
            try:
                if self.velho(slug):
                    self.gerar_agora(slug)
                else:
                    with self._trava:
                        self._situacao.pop(slug, None)
            except Exception as e:                      # noqa: BLE001 — o erro vai para a tela do celular
                with self._trava:
                    self._situacao[slug] = {"situacao": "erro", "erro": str(e)[:300]}

    def _vigiar(self):
        """Com o acesso ligado, refaz em segundo plano os pacotes que algum celular já abriu e
        ficaram velhos (o projeto foi gravado no PC): quando o celular pedir, já está pronto."""
        geracao, voltas = self._geracao, 0
        self._manter_https()
        while self._geracao == geracao and not self._parar.wait(60.0):
            voltas += 1
            if voltas % 360 == 0:                       # a cada 6 h: IP do PC e validade do certificado
                self._manter_https()
            try:
                for slug in os.listdir(self.pacotes):
                    if self._pasta_projeto(slug) and self.velho(slug) and slug not in self._situacao:
                        self.pedir_pacote(slug)
            except OSError:
                pass

    # ------------------------------------------------------------------ HTTPS (a cópia para a obra)
    # O nome do domínio do usuário aponta (no Cloudflare) para o IP do PC na rede, e o certificado é do
    # Let's Encrypt por desafio de DNS (celular/certificado.py). Configurado uma vez na tela do PC; depois
    # o programa renova sozinho e reaponta o nome quando o IP do PC muda.

    def _config_https(self) -> dict:
        try:
            with open(os.path.join(self.tls, "cloudflare.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def estado_https(self) -> dict:
        from celular import certificado as C
        v = C.validade(os.path.join(self.tls, "certificado.pem")) if self._tem_certificado() else None
        cfg = self._config_https()
        return {"configurado": bool(cfg.get("token")), "nome": cfg.get("nome") or self.nome_na_rede(), "ativo": self.https,
                "valido_ate": v.isoformat() if v else None, "ip": cfg.get("ip"), **self._https_situacao}

    def configurar_https(self, nome: str, token: str, em_fundo: bool = True) -> dict:
        """Guarda o nome e o token do Cloudflare e tira o certificado (em segundo plano)."""
        nome = (nome or "").strip().lower().rstrip(".")
        token = (token or "").strip() or self._config_https().get("token", "")
        if not nome or not token:
            raise ValueError("informe o nome (ex.: metalica.seudominio.com.br) e o token do Cloudflare")
        os.makedirs(self.tls, exist_ok=True)
        with open(os.path.join(self.tls, "cloudflare.json"), "w", encoding="utf-8") as f:
            json.dump({"nome": nome, "token": token}, f)
        if em_fundo:
            threading.Thread(target=self._obter_certificado, name="celular-certificado", daemon=True).start()
        else:
            self._obter_certificado()
        return self.estado_https()

    def _obter_certificado(self):
        from celular import certificado as C
        cfg = self._config_https()
        if self._https_situacao.get("situacao") == "trabalhando":
            return
        self._https_situacao = {"situacao": "trabalhando", "mensagem": "começando"}

        def avisar(t):
            self._https_situacao = {"situacao": "trabalhando", "mensagem": t}
        try:
            ip = enderecos_da_rede()[0]
            dns = C.Cloudflare(cfg["token"])
            r = C.obter(self.tls, cfg["nome"], ip, dns, diretorio=os.environ.get("METALICA_ACME_DIR") or C.LETS_ENCRYPT,
                        avisar=avisar)
            cfg["ip"] = ip
            with open(os.path.join(self.tls, "cloudflare.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            self._https_situacao = {"situacao": "pronto", "mensagem": "certificado válido até %s" % (r.get("valido_ate") or "")[:10]}
            self._trocar_protocolo(True)
        except Exception as e:                          # noqa: BLE001 — a mensagem vai para a tela do PC
            self._https_situacao = {"situacao": "erro", "mensagem": str(e)[:300]}

    def _manter_https(self):
        """Reaponta o nome se o IP do PC mudou e renova o certificado perto do vencimento."""
        cfg = self._config_https()
        if not cfg.get("token") or self._https_situacao.get("situacao") == "trabalhando":
            return
        try:
            from celular import certificado as C
            ip = enderecos_da_rede()[0]
            if C.precisa_renovar(self.tls):
                threading.Thread(target=self._obter_certificado, name="celular-certificado", daemon=True).start()
            elif ip != cfg.get("ip"):
                C.Cloudflare(cfg["token"]).apontar(cfg["nome"], ip)
                cfg["ip"] = ip
                with open(os.path.join(self.tls, "cloudflare.json"), "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
        except Exception as e:                          # noqa: BLE001 — sem internet agora: tenta na próxima volta
            self._https_situacao = {"situacao": "aviso", "mensagem": "não foi possível conferir o DNS: %s" % str(e)[:200]}

    def remover_https(self) -> dict:
        for n in ("certificado.pem", "chave.pem", "nome.txt", "cloudflare.json"):
            try:
                os.remove(os.path.join(self.tls, n))
            except OSError:
                pass
        self._https_situacao = {}
        self._trocar_protocolo(False)
        return self.estado()

    def _trocar_protocolo(self, https: bool):
        """Religa o servidor (se ligado) no protocolo novo; os aparelhos pareados continuam (a chave é a mesma,
        mas o endereço muda: o cookie de http não vale no nome do HTTPS, então pareia-se de novo uma vez)."""
        with self._trava:
            self.https = https and self._tem_certificado()
            if self.ligado:
                self.desligar(lembrar=False)
                self.ligar()

    # ------------------------------------------------------------------ servidor

    def ligar(self) -> dict:
        with self._trava:
            if self._servidor is None:
                srv = _Servidor((self.host, self.porta), _Handler)
                if self.https:
                    import ssl
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                    ctx.load_cert_chain(os.path.join(self.tls, "certificado.pem"), os.path.join(self.tls, "chave.pem"))
                    # o aperto de mão fica no fio de cada conexão (não no que aceita): um aparelho lento não trava os outros
                    srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
                srv.celular = self
                self._servidor = srv
                self._parar.clear()
                self._geracao += 1
                self._fio = threading.Thread(target=srv.serve_forever, name="celular-servidor", daemon=True)
                self._fio.start()
                self._vigia = threading.Thread(target=self._vigiar, name="celular-vigia", daemon=True)
                self._vigia.start()
            cfg = self.configuracao()
            cfg["ligado"] = True
            self._gravar("config.json", cfg)
        return self.estado()

    def desligar(self, lembrar: bool = True) -> dict:
        with self._trava:
            srv, self._servidor = self._servidor, None
            self._parar.set()
            if srv is not None:
                srv.shutdown()
                srv.fechar_conexoes()          # as já abertas (keep-alive) também: desligado, nada responde
                srv.server_close()
            if lembrar:
                cfg = self.configuracao()
                cfg["ligado"] = False
                self._gravar("config.json", cfg)
        return self.estado()


class _Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    celular: Celular = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._conexoes = set()
        self._trava_conexoes = threading.Lock()

    def process_request(self, request, client_address):
        with self._trava_conexoes:
            self._conexoes.add(request)
        super().process_request(request, client_address)

    def shutdown_request(self, request):
        with self._trava_conexoes:
            self._conexoes.discard(request)
        super().shutdown_request(request)

    def fechar_conexoes(self):
        """O navegador mantém a conexão aberta entre um pedido e outro: ao desligar, ela fecha também."""
        with self._trava_conexoes:
            abertas, self._conexoes = list(self._conexoes), set()
        for s in abertas:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    def handle_error(self, request, client_address):
        # o celular que troca de tela no meio de um download fecha a conexão: não é erro
        import sys
        e = sys.exc_info()[1]
        if isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


_PAGINA_SEM_PAR = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Metálica</title>
<style>body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#eef1f6;color:#16202e}
header{background:#0b3d91;color:#fff;padding:16px 18px;font-weight:650;font-size:18px}
main{padding:20px 18px;max-width:520px}b{display:block;font-size:18px;margin-bottom:8px}
.c{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 8px rgba(16,32,60,.08)}</style></head>
<body><header>Metálica</header><main><div class="c"><b>%s</b>%s</div></main></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    """Só leitura: GET e HEAD das rotas do celular; o resto é 405."""
    server_version = "Metalica-celular"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    @property
    def celular(self) -> Celular:
        return self.server.celular

    # ---- métodos que não existem aqui
    def _recusar(self):
        # o corpo do pedido recusado é descartado e a conexão fecha: sobrando na conexão, ele viraria o
        # começo do próximo pedido ("{}GET …")
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 1 << 20)
            if n:
                self.rfile.read(n)
        except (ValueError, OSError):
            pass
        self.close_connection = True
        self._enviar(405, b"", "text/plain", {"Allow": "GET, HEAD", "Connection": "close"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _recusar

    def do_HEAD(self):
        self._atender(cabeca=True)

    def do_GET(self):
        self._atender(cabeca=False)

    # ---- resposta
    def _enviar(self, status: int, corpo: bytes, tipo: str, extras: Optional[dict] = None, cabeca: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not cabeca and corpo:
            self.wfile.write(corpo)

    def _json(self, obj, status=200, cabeca=False):
        self._enviar(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), TIPOS[".json"],
                     {"Cache-Control": "no-store"}, cabeca)

    def _pagina(self, status, titulo, texto, cabeca=False):
        self._enviar(status, (_PAGINA_SEM_PAR % (titulo, texto)).encode("utf-8"), TIPOS[".html"],
                     {"Cache-Control": "no-store"}, cabeca)

    def _arquivo(self, caminho: str, cabeca: bool, etag: Optional[str] = None):
        try:
            st = os.stat(caminho)
        except OSError:
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        etag = etag or '"%x-%x"' % (int(st.st_mtime), st.st_size)
        if self.headers.get("If-None-Match") == etag:
            return self._enviar(304, b"", "text/plain", {"ETag": etag, "Cache-Control": "no-cache"}, cabeca=True)
        with open(caminho, "rb") as f:
            dados = f.read()
        tipo = TIPOS.get(os.path.splitext(caminho)[1].lower()) or mimetypes.guess_type(caminho)[0] or "application/octet-stream"
        self._enviar(200, dados, tipo, {"ETag": etag, "Cache-Control": "no-cache"}, cabeca)

    def _cookie(self) -> str:
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == COOKIE:
                return v
        return ""

    # ---- rotas
    def _atender(self, cabeca: bool):
        ip = self.client_address[0]
        url = urlparse(self.path)
        rota = unquote(url.path)
        cel = self.celular
        if cel._servidor is not self.server:            # desligado no meio de uma conexão aberta
            self.close_connection = True
            return self._enviar(503, b"", "text/plain", {"Connection": "close"}, cabeca)
        if cel.freado(ip):
            return self._enviar(429, b"", "text/plain", {"Retry-After": "600"}, cabeca)
        if rota == "/celular/parear":
            codigo = (parse_qs(url.query).get("c") or [""])[0]
            valor = cel.parear(codigo, self.headers.get("User-Agent") or "", ip)
            if not valor:
                cel.falhou(ip)
                return self._pagina(403, "Código vencido ou já usado",
                                    "No computador, abra <i>Acesso pelo celular</i> e gere um QR code novo. "
                                    "Cada código vale uma vez, por 5 minutos.", cabeca)
            cookie = "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=34560000%s" % (
                COOKIE, valor, "; Secure" if cel.https else "")
            return self._enviar(302, b"", "text/plain", {"Location": "/celular/", "Set-Cookie": cookie,
                                                          "Cache-Control": "no-store"}, cabeca)
        aparelho = cel.autenticar(self._cookie(), ip)
        if not aparelho:
            cel.falhou(ip)
            if rota in ("/", "/celular", "/celular/", "/celular/index.html"):
                return self._pagina(401, "Este aparelho ainda não está ligado ao computador",
                                    "No computador, abra <i>Acesso pelo celular</i> e leia o QR code com a câmera.", cabeca)
            return self._enviar(401, b"", "text/plain", {"Cache-Control": "no-store"}, cabeca)
        if rota in ("/", "/celular"):
            return self._enviar(302, b"", "text/plain", {"Location": "/celular/"}, cabeca)
        if rota == "/visor3d/visor3d.js":                # o visor do 3D leve (o mesmo do modo "ver" do PC)
            return self._arquivo(os.path.join(WEB, "visor3d", "visor3d.js"), cabeca)
        if rota.startswith("/lib/"):
            nome = rota[len("/lib/"):]
            if nome in LIB_LIBERADA:
                return self._arquivo(os.path.join(WEB, "lib", nome), cabeca)
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        if rota == "/celular/api/estado":
            from versao import VERSAO
            return self._json({"aparelho": aparelho.get("nome"), "computador": socket.gethostname(),
                               "programa": VERSAO, "agora": time.strftime("%Y-%m-%dT%H:%M:%S")}, cabeca=cabeca)
        if rota.startswith("/celular/dados/"):
            return self._dados(rota[len("/celular/dados/"):], cabeca)
        if rota.startswith("/celular/"):
            rel = rota[len("/celular/"):] or "index.html"
            return self._estatico(rel, cabeca)
        return self._enviar(404, b"", "text/plain", cabeca=cabeca)

    def _estatico(self, rel: str, cabeca: bool):
        """Arquivos de web/celular (e a subpasta lib), sem sair dela."""
        if "\\" in rel or rel.startswith("/") or any(p in ("", ".", "..") for p in rel.split("/")) or rel.count("/") > 1:
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        caminho = os.path.abspath(os.path.join(TELAS, rel))
        if not caminho.startswith(os.path.abspath(TELAS) + os.sep) or not os.path.isfile(caminho):
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        return self._arquivo(caminho, cabeca)

    def _dados(self, rel: str, cabeca: bool):
        cel = self.celular
        if rel == "projetos.json":
            return self._json({"formato": 1, "projetos": cel.projetos()}, cabeca=cabeca)
        slug, _, arq = rel.partition("/")
        if not cel._pasta_projeto(slug):
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        if arq == "manifesto.json":
            sit = cel.pedir_pacote(slug)
            m = cel._manifesto(slug)
            if sit.get("situacao") == "erro":
                return self._json({"preparando": False, "erro": sit.get("erro")}, 500, cabeca)
            if not m:                                   # primeira vez: ainda não há o que mostrar
                return self._json({"preparando": True, **sit}, 202, cabeca)
            if sit.get("situacao") in ("na fila", "preparando"):
                m = dict(m, atualizando=True, progresso=sit.get("progresso"))
            return self._json(m, cabeca=cabeca)
        m = cel._manifesto(slug)
        item = next((a for a in (m or {}).get("arquivos") or [] if a.get("nome") == arq), None)
        if not item:                                    # só o que o manifesto lista
            return self._enviar(404, b"", "text/plain", cabeca=cabeca)
        return self._arquivo(os.path.join(cel.pacotes, slug, *arq.split("/")), cabeca, etag='"%s"' % item["sha1"])
