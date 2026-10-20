# -*- coding: utf-8 -*-
"""O celular de qualquer lugar (20/10), de ponta a ponta, com o Worker metalica-celular rodando NESTA máquina
(wrangler dev --local: o mesmo código, com D1 e R2 locais numa pasta temporária — nada vai para a Cloudflare):

* o PC (celular/nuvem.py) envia a obra ligada e as telas; o segundo envio sem mudança não manda nada;
* licença sem "envia obras" não grava; licença bloqueada não faz nada;
* o celular sem chave só vê a tela de entrada; chave errada é recusada; chave certa entra (cookie) e lê a lista,
  o manifesto e os arquivos (só os que o manifesto lista, conferidos pelo SHA-1); QR do PC entra uma vez só;
* limite de celulares por chave; bloquear a chave corta o celular; liberar a vaga também;
* obra desligada na chave "Celular" sai da nuvem no envio seguinte;
* no Chrome emulando o celular: digita a chave, a lista abre e o 3D da obra abre — tudo vindo da nuvem.

Precisa do wrangler em %LOCALAPPDATA%\\Metalica-ferramentas\\cloudflare (servicos/licencas/LEIAME.md); sem ele, pula."""
import base64, hashlib, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAIZ = os.path.dirname(BASE)
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo

FERR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Metalica-ferramentas", "cloudflare")
WRANGLER = os.path.join(FERR, "node_modules", ".bin", "wrangler.cmd")
SERV = os.path.join(RAIZ, "servicos", "celular")
if not os.path.isfile(WRANGLER) or not os.path.isdir(SERV):
    print("  pulado: sem o wrangler (ou sem servicos/celular) nesta máquina")
    print()
    print("FALHAS: 0")
    sys.exit(0)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from celular import servidor as S
from celular.nuvem import Nuvem, ErroNuvem

falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


PRIV = Ed25519PrivateKey.generate()
PUB = base64.b64encode(PRIV.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def licenca(chave, maquina):
    p = json.dumps({"v": 1, "chave": chave, "maquina": maquina, "pessoa": "Teste", "emitida": "2026-10-20T00:00:00Z",
                    "validade": "2026-11-20T00:00:00Z"}).encode()
    return b64url(p) + "." + b64url(PRIV.sign(p))


CH_PC, CH_SEM, CH_OUTRA = "MTL-AAAA-BBBB-CCCC", "MTL-DDDD-EEEE-FFFF", "MTL-GGGG-HHHH-JJJJ"
TMP = tempfile.mkdtemp(prefix="metalica_nuvem_")
PERSIST = os.path.join(TMP, "wrangler")
amb = dict(os.environ, WRANGLER_SEND_METRICS="false", CI="1", NO_COLOR="1")


def sql(comando=None, arquivo=None):
    args = [WRANGLER, "d1", "execute", "metalica-licencas", "--local", "--persist-to", PERSIST, "-c", "wrangler.toml"]
    args += ["--file", arquivo] if arquivo else ["--command", comando]
    r = subprocess.run(args, cwd=SERV, capture_output=True, text=True, encoding="utf-8", errors="replace", env=amb, timeout=180)
    if r.returncode:
        raise RuntimeError("d1: " + (r.stderr or r.stdout)[-800:])


def pedir(caminho, metodo="GET", cookie=None, corpo=None, cab=None, seguir=False):
    h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
    h.update(cab or {})
    if cookie: h["Cookie"] = "mcel=" + cookie
    if corpo is not None:
        corpo = json.dumps(corpo).encode(); h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + caminho, data=corpo, method=metodo, headers=h)

    class SemSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    abrir = urllib.request.build_opener() if seguir else urllib.request.build_opener(SemSeguir)
    try:
        with abrir.open(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def cookie_de(cab):
    c = cab.get("Set-Cookie") or ""
    return c.split(";")[0].split("=", 1)[1] if c.startswith("mcel=") else ""


srv = None
navs = []
try:
    # ------------------------------------------------------------------ o banco local e o Worker
    sql(arquivo=os.path.join(RAIZ, "servicos", "licencas", "schema.sql"))
    sql(arquivo="schema.sql")
    sql(arquivo="migracao-celular.sql")
    sql("INSERT INTO licencas (chave, pessoa, maquinas_max, ativa, criada, celulares_max, envia_obras) VALUES "
        f"('{CH_PC}', 'Escritório', 2, 1, '2026-10-20', 3, 1), ('{CH_SEM}', 'Sem envio', 2, 1, '2026-10-20', 3, 0), "
        f"('{CH_OUTRA}', 'Outra', 2, 1, '2026-10-20', 1, 0);"
        "INSERT INTO maquinas (chave, maquina, ativada, ultima_vez) VALUES "
        f"('{CH_PC}', 'pc1', '2026-10-20', '2026-10-20'), ('{CH_SEM}', 'pc2', '2026-10-20', '2026-10-20')")
    PORTA = _porta_livre()
    URL = f"http://127.0.0.1:{PORTA}"
    srv = subprocess.Popen([WRANGLER, "dev", "--local", "--persist-to", PERSIST, "-c", "wrangler.toml", "--ip", "127.0.0.1",
                            "--port", str(PORTA), "--var", "LICENCA_CHAVE_PUBLICA:" + PUB, "--show-interactive-dev-session=false"],
                           cwd=SERV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
    for _ in range(120):
        try:
            urllib.request.urlopen(URL + "/celular/", timeout=2)
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.5)
    ok(pedir("/celular/")[0] == 401, "o Worker sobe (wrangler dev local) e, sem chave, responde 401")

    # ------------------------------------------------------------------ o PC envia
    dados = os.path.join(TMP, "dados")
    proj = os.path.join(dados, "obra-nuvem")
    os.makedirs(os.path.join(proj, "detalhamento"))
    json.dump({"nome": "Obra da nuvem", "alterado": "2026-10-20T10:00:00", "cliente": "Hermes"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
    json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
    os.makedirs(os.path.join(dados, "comercial-nao", "comercial"))
    cel = S.Celular(dados, os.path.join(TMP, "trabalho"), porta=_porta_livre(), host="127.0.0.1")
    nuv = Nuvem(cel, servico=URL, token=lambda: licenca(CH_PC, "pc1"))
    r = nuv.enviar()
    ok(r["obras"] == 1 and r["enviados_bytes"] > 0, f"o PC envia a obra e as telas: {r}")
    r2 = nuv.enviar()
    ok(r2["enviados_bytes"] == 0, f"o segundo envio, sem mudança, não manda nada: {r2['enviados_bytes']} bytes")
    ok(nuv.configuracao().get("assinatura") == nuv.assinatura(), "o PC guarda a assinatura do que enviou (o fio só reenvia se mudar)")
    try:
        Nuvem(cel, servico=URL, token=lambda: licenca(CH_SEM, "pc2")).enviar(); ok(False, "licença sem 'envia obras' não grava")
    except ErroNuvem as e:
        ok("envia obras" in str(e).lower(), f"licença sem 'envia obras' não grava: {e}")
    try:
        Nuvem(cel, servico=URL, token=lambda: licenca(CH_PC, "pc-que-nao-existe")).enviar(); ok(False, "computador fora da licença não grava")
    except ErroNuvem as e:
        ok(True, f"computador fora da licença não grava: {e}")
    falsa = licenca(CH_PC, "pc1")[:-6] + "AAAAAA"
    ok(pedir("/pc/estado", cab={"Authorization": "Licenca " + falsa})[0] == 403, "licença com assinatura falsa: 403")

    # ------------------------------------------------------------------ o celular entra
    st, cab, corpo = pedir("/celular/")
    ok(st == 401 and b"Chave da licen" in corpo and b"Obra da nuvem" not in corpo, "sem chave: só a tela de entrada, sem nome de obra")
    for rota in ("/celular/dados/projetos.json", "/celular/dados/obra-nuvem/manifesto.json", "/celular/celular.js", "/lib/three.module.js", "/celular/api/estado"):
        ok(pedir(rota)[0] == 401, f"sem chave: {rota} → 401")
    ok(pedir("/celular/manifest.webmanifest")[0] == 200, "o manifesto do app sai sem chave (o instalar do Chrome)")
    ok(pedir("/favicon.ico")[0] == 200, "o ícone da aba sai sem chave")
    st, _c, corpo = pedir("/celular/api/entrar", "POST", corpo={"chave": "MTL-ZZZZ-ZZZZ-ZZZZ"})
    ok(st == 403, f"chave errada recusada: {st} {corpo[:80]!r}")
    st, cab, _ = pedir("/celular/api/entrar", "POST", corpo={"chave": CH_PC.lower().replace("-", " ")})
    k1 = cookie_de(cab)
    ok(st == 200 and k1 and "HttpOnly" in cab.get("Set-Cookie", ""), "chave certa (digitada de qualquer jeito) entra e ganha o cookie")
    st, _c, corpo = pedir("/celular/dados/projetos.json", cookie=k1)
    lista = json.loads(corpo)["projetos"] if st == 200 else []
    ok([p["slug"] for p in lista] == ["obra-nuvem"], f"a lista vem da nuvem: {[p['slug'] for p in lista]}")
    st, _c, corpo = pedir("/celular/dados/obra-nuvem/manifesto.json", cookie=k1)
    man = json.loads(corpo) if st == 200 else {}
    nomes = {a["nome"] for a in man.get("arquivos", [])}
    ok("modelo3d.mcel" in nomes and "fonte.txt" not in nomes, f"o manifesto da obra (sem o fonte.txt do PC): {sorted(nomes)[:6]}")
    a = next(a for a in man["arquivos"] if a["nome"] == "modelo3d.mcel")
    st, cab, mcel = pedir("/celular/dados/obra-nuvem/modelo3d.mcel?v=" + a["sha1"][:12], cookie=k1)
    ok(st == 200 and mcel[:4] == b"MCEL" and hashlib.sha1(mcel).hexdigest() == a["sha1"], "o 3D leve chega inteiro (SHA-1 confere)")
    ok(pedir("/celular/dados/obra-nuvem/modelo3d.mcel", cookie=k1, cab={"If-None-Match": cab.get("ETag", "")})[0] == 304, "revalidar sem mudança: 304")
    for rota in ("/celular/dados/obra-nuvem/fonte.txt", "/celular/dados/obra-nuvem/modelo.json", "/celular/dados/comercial-nao/manifesto.json",
                 "/celular/dados/obra-nuvem/../indice.json", "/celular/dados/%2e%2e/telas.json", "/celular/app.py", "/pc/estado"):
        ok(pedir(rota, cookie=k1)[0] in (401, 403, 404), f"fora da lista: {rota}")
    st, _c, corpo = pedir("/celular/api/estado", cookie=k1)
    est = json.loads(corpo) if st == 200 else {}
    ok(est.get("nuvem") is True and est.get("enviado"), f"o estado diz que é a nuvem e quando o PC enviou: {est.get('enviado')}")
    ok(pedir("/celular/", cookie=k1)[0] == 200 and pedir("/visor3d/visor3d.js", cookie=k1)[0] == 200, "com a chave: as telas e o visor")

    # QR do PC
    cod = nuv.novo_codigo()
    ok(cod["url"].startswith(URL + "/celular/parear?c="), f"o PC gera o QR da nuvem: {cod['url'][-30:]}")
    st, cab, _ = pedir(cod["url"][len(URL):])
    k2 = cookie_de(cab)
    ok(st == 302 and k2, "o QR põe o celular na licença do PC")
    ok(pedir(cod["url"][len(URL):])[0] == 403, "o mesmo QR não vale de novo")
    st, _c, corpo = pedir("/pc/estado", cab={"Authorization": "Licenca " + licenca(CH_PC, "pc1")})
    aps = json.loads(corpo).get("aparelhos", [])
    ok(sorted(a["via"] for a in aps) == ["chave", "qr"] and any(a["nome"] == "iPhone" for a in aps), f"o PC vê os celulares da chave: {aps}")

    # limite, bloqueio, liberar
    ok(pedir("/celular/api/entrar", "POST", corpo={"chave": CH_OUTRA})[0] == 200, "outra chave (limite 1): o 1º celular entra")
    st, _c, corpo = pedir("/celular/api/entrar", "POST", corpo={"chave": CH_OUTRA})
    ok(st == 409 and "limite" in corpo.decode(), "o 2º celular passa do limite da chave: 409")
    sql(f"UPDATE licencas SET ativa = 0 WHERE chave = '{CH_PC}'")
    time.sleep(61)                                         # o Worker lembra o aparelho por 1 min
    ok(pedir("/celular/dados/projetos.json", cookie=k1)[0] == 401, "chave bloqueada: o celular perde o acesso")
    sql(f"UPDATE licencas SET ativa = 1 WHERE chave = '{CH_PC}'")
    ok(pedir("/celular/dados/projetos.json", cookie=k1)[0] == 200, "desbloqueada: volta")
    sql("UPDATE aparelhos SET liberado = 1 WHERE via = 'qr'")
    time.sleep(61)
    ok(pedir("/celular/dados/projetos.json", cookie=k2)[0] == 401, "vaga liberada na tela: aquele celular perde o acesso")

    # obra desligada sai da nuvem
    cel.mostrar("obra-nuvem", False)
    r = nuv.enviar()
    ok(r["tiradas"] == ["obra-nuvem"], f"obra desligada sai da nuvem no envio seguinte: {r['tiradas']}")
    ok(json.loads(pedir("/celular/dados/projetos.json", cookie=k1)[2])["projetos"] == [] and
       pedir("/celular/dados/obra-nuvem/manifesto.json", cookie=k1)[0] == 404, "o celular não vê mais a obra")
    cel.mostrar("obra-nuvem", True)
    nuv.enviar()

    # ------------------------------------------------------------------ no Chrome, como um celular
    exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_nuvem_")
    p = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                          "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    navs.append((p, perfil))
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    ap = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): ap.cmd(f"{dm}.enable")
    ap.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)
    ap.cmd("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    ap.cmd("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36")

    def esperar(expr, limite=60):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                if ap.avaliar(expr): return True
            except Exception: pass
            ap.drenar(0.3)
        return False

    ap.navegar(URL + "/celular/", limite=30)
    ok(esperar("!!document.getElementById('chave')", 15), "Chrome: a tela de entrada pede a chave")
    ap.avaliar("document.getElementById('chave').focus()")
    ap.cmd("Input.insertText", text=CH_PC)
    caixa = ap.avaliar("(() => { const b = document.getElementById('b').getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()")
    ap.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": caixa[0], "y": caixa[1]}])
    ap.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    ok(esperar("document.querySelectorAll('.projeto').length === 1", 30), "Chrome: tocar Entrar abre a lista com a obra")
    ok(esperar("(document.getElementById('conexao') || {}).textContent && document.getElementById('conexao').textContent.indexOf('Nuvem') === 0", 10),
       "Chrome: o selo diz que vem da nuvem: %r" % ap.avaliar("(document.getElementById('conexao') || {}).textContent"))
    ap.avaliar("document.querySelector('.projeto').click()")
    ok(esperar("window.visor && window.visor.fichas && !document.querySelector('.carregando') && window.visor.nPecas > 0", 90),
       "Chrome: o 3D da obra abre, vindo da nuvem")
    open(os.path.join(SCR, "celular_nuvem.png"), "wb").write(base64.b64decode(ap.cmd("Page.captureScreenshot", format="png")["data"]))
    erros = [m for m in ap.console if m[0] in ("error", "excecao") and "401" not in str(m)]
    ok(not erros, f"Chrome: sem erros no console: {erros[:3]}")
finally:
    for p, perf in navs:
        try: p.kill()
        except Exception: pass
    if srv:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(srv.pid)], capture_output=True)
    time.sleep(1)
    shutil.rmtree(TMP, ignore_errors=True)
    for _p, perf in navs: shutil.rmtree(perf, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
