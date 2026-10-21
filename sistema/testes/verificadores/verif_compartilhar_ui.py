# -*- coding: utf-8 -*-
"""A obra para outro usuário pela tela inicial (inicio.js enviarObra/verificarRecebidos + compartilhar.py, 21/10 — o
usuário: "enviar o projeto para outro usuário por dentro do sistema sem precisar exportar o pacote"): o cartão › Enviar
para… lista as pessoas e envia; do outro lado, o aviso "… te enviou" no alto da lista, Abrir importa como projeto novo e o
aviso some; Recusar tira da nuvem. A nuvem é um dublê local com as regras do Worker (servicos/celular, /pc/envio…) e a
licença, um arquivo de teste (METALICA_LICENCA_ARQUIVO). Porta livre, nunca a 8765/8766."""
import base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

# ------------------------------------------------------------------ a nuvem de mentira (as regras do Worker)
NUVEM = {"eu": "A", "partes": {}, "envios": []}
PESSOAS = {"pa": ("A", "Elieber"), "pb": ("B", "Andrey")}


class Nuvem(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _resp(self, obj, status=200, bruto=None):
        corpo = bruto if bruto is not None else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if bruto is not None else "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota == "/pc/pessoas":
            return self._resp({"pessoas": [{"id": i, "pessoa": n, "eu": c == NUVEM["eu"]} for i, (c, n) in PESSOAS.items()]})
        if rota == "/pc/recebidos":
            return self._resp({"recebidos": [e for e in NUVEM["envios"] if e["para_chave"] == NUVEM["eu"] and e["estado"] == "pendente"]})
        m = re.match(r"^/pc/recebidos/(\d+)/parte/([0-9a-f]{40})$", rota)
        if m:
            return self._resp(None, bruto=NUVEM["partes"][m.group(2)])
        self._resp({"erro": "rota"}, 404)

    def do_PUT(self):
        m = re.match(r"^/pc/envio/parte/([0-9a-f]{40})$", self.path)
        b = self._corpo()
        if not m or hashlib.sha1(b).hexdigest() != m.group(1):
            return self._resp({"erro": "parte"}, 400)
        NUVEM["partes"][m.group(1)] = b
        self._resp({"ok": True})

    def do_POST(self):
        rota, c = self.path, json.loads(self._corpo() or b"{}")
        if rota == "/pc/envio/faltam":
            return self._resp({"faltam": [s for s in c["sha1s"] if s not in NUVEM["partes"]]})
        if rota == "/pc/envios":
            alvo = PESSOAS[c["para"]]
            NUVEM["envios"].append(dict(c, id=len(NUVEM["envios"]) + 1, de="Elieber", de_mim=False, para_chave=alvo[0],
                                        estado="pendente", criado="2026-10-21T10:00:00Z", bytes=sum(p["bytes"] for p in c["partes"])))
            return self._resp({"id": len(NUVEM["envios"]), "para": alvo[1], "eu": alvo[0] == NUVEM["eu"]})
        m = re.match(r"^/pc/recebidos/(\d+)/(recebido|recusar)$", rota)
        if m:
            NUVEM["envios"][int(m.group(1)) - 1]["estado"] = m.group(2)
            return self._resp({"ok": True})
        self._resp({"erro": "rota"}, 404)


porta_nuvem = _porta_livre()
servidor_nuvem = ThreadingHTTPServer(("127.0.0.1", porta_nuvem), Nuvem)
threading.Thread(target=servidor_nuvem.serve_forever, daemon=True).start()

# ------------------------------------------------------------------ o programa de teste
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_compartilhar_")
proj = os.path.join(DADOS, "prati-cd")
os.makedirs(proj)
json.dump({"nome": "PRATI CD", "tipo": "ifc", "alterado": "2026-10-21T09:00:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
# um projeto do TIPO "recebido" (o Hangar Almayer, 21/10): o aviso das obras recebidas não pode levar o ícone dele junto
os.makedirs(os.path.join(DADOS, "hangar"))
json.dump({"nome": "HANGAR ALMAYER", "tipo": "recebido", "alterado": "2026-10-20T09:00:00"},
          open(os.path.join(DADOS, "hangar", "projeto.json"), "w", encoding="utf-8"))
lic = os.path.join(DADOS, "..", "licenca-teste-%d.json" % PORTA)
json.dump({"licenca": "teste.teste", "chave": "MTL-TEST-TEST-TEST"}, open(lic, "w", encoding="utf-8"))
amb = dict(os.environ, METALICA_COMPARTILHAR="http://127.0.0.1:%d" % porta_nuvem, METALICA_LICENCA_ARQUIVO=os.path.abspath(lic))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.4)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_compartilhar_")
nav = subprocess.Popen([exe, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1300, height=860, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "document.querySelectorAll('[data-acao=enviar]').length === 2", 30), "o cartão tem Enviar para…")
    aba.avaliar("document.querySelector('.cartao[data-slug=prati-cd] [data-acao=enviar]').click(); 1")
    ok(esperar(aba, "document.getElementById('dlg').open && document.querySelectorAll('#dlg-campos input[type=radio]').length === 2", 15),
       "o diálogo lista as pessoas (2)")
    ok("você" in (aba.avaliar("document.getElementById('dlg-campos').textContent") or ""), "a própria licença aparece como os outros computadores")
    foto(aba, "compartilhar_1_enviar.png")
    aba.avaliar("document.querySelector('#dlg-campos input[value=pb]').click(); document.getElementById('dlg-ok').click(); 1")
    ok(esperar(aba, "document.getElementById('bandeja').textContent.includes('Obra enviada')", 30), "Obra enviada (o aviso)")
    ok(len(NUVEM["envios"]) == 1 and NUVEM["envios"][0]["para_chave"] == "B" and NUVEM["envios"][0]["nome"] == "PRATI CD",
       "o envio chegou à nuvem, para o Andrey")
    # do lado do Andrey: o aviso no alto da lista
    NUVEM["eu"] = "B"
    aba.navegar(base + "/", limite=60)
    ok(esperar(aba, "document.querySelectorAll('.obra-recebida').length === 1", 30), "o aviso da obra recebida aparece")
    ICONE = "!!document.querySelector('.cartao[data-slug=hangar] > .cartao-icone')"
    ok(aba.avaliar(ICONE), "o cartão do projeto tipo recebido continua com o ícone (o Hangar desalinhava)")
    ok("Elieber te enviou" in (aba.avaliar("document.querySelector('.obra-recebida').textContent") or ""), "diz quem enviou")
    foto(aba, "compartilhar_2_recebido.png")
    aba.avaliar("[...document.querySelectorAll('.obra-recebida button')].find(b => b.textContent === 'Abrir').click(); 1")
    ok(esperar(aba, "document.querySelectorAll('.obra-recebida').length === 0 && document.querySelectorAll('[data-acao=enviar]').length === 3", 40),
       "Abrir: a obra entra na lista como projeto novo e o aviso some")
    ok(NUVEM["envios"][0]["estado"] == "recebido", "e a nuvem marca recebido")
    pastas = [n for n in os.listdir(DADOS) if os.path.isfile(os.path.join(DADOS, n, "projeto.json"))]
    ok(len(pastas) == 3, f"a obra recebida é uma pasta nova, nunca por cima ({pastas})")
    ok(aba.avaliar(ICONE) and aba.avaliar("getComputedStyle(document.querySelector('.cartao[data-slug=hangar]')).gridTemplateColumns.split(' ').length === 3 && "
                                          "document.querySelector('.cartao[data-slug=hangar] .cartao-corpo').getBoundingClientRect().width > 300"),
       "depois de abrir, o cartão tipo recebido continua inteiro (ícone, corpo largo)")
    # recusar
    NUVEM["eu"] = "A"
    aba.navegar(base + "/", limite=60)
    esperar(aba, "document.querySelectorAll('[data-acao=enviar]').length >= 1", 20)
    aba.avaliar("document.querySelector('.cartao[data-slug=prati-cd] [data-acao=enviar]').click(); 1")
    esperar(aba, "document.getElementById('dlg').open", 10)
    aba.avaliar("document.querySelector('#dlg-campos input[value=pb]').click(); document.getElementById('dlg-ok').click(); 1")
    esperar(aba, "document.getElementById('bandeja').textContent.includes('Obra enviada')", 30)
    NUVEM["eu"] = "B"
    aba.navegar(base + "/", limite=60)
    esperar(aba, "document.querySelectorAll('.obra-recebida').length === 1", 30)
    aba.avaliar("window.confirm = () => true; [...document.querySelectorAll('.obra-recebida button')].find(b => b.textContent === 'Recusar').click(); 1")
    ok(esperar(aba, "document.querySelectorAll('.obra-recebida').length === 0", 20) and NUVEM["envios"][1]["estado"] == "recusar",
       "Recusar tira o aviso e a obra da nuvem")
    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    servidor_nuvem.shutdown()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
    try: os.remove(lic)
    except OSError: pass
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
