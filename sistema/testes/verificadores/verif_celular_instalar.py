# -*- coding: utf-8 -*-
"""O celular instala o Metálica com o nome e o logo (19/10).

O usuário pediu "instalar" no Android e o Chrome ofereceu só um atalho com um "1" cinza no lugar
do logo. O manifesto e os ícones existiam, mas o navegador busca o manifesto SEM o cookie do
aparelho (é o padrão dele) e o servidor do celular devolvia 401 — para o Chrome a página não tinha
manifesto nem ícone. O manifesto e o logo não dizem nada de projeto nenhum: saem sem a chave.

Aqui o servidor do celular sobe sozinho no 127.0.0.1 (que o Chrome trata como conexão segura,
como o HTTPS de verdade), o aparelho pareia, e o Chrome diz se acha o manifesto, o ícone e se o
app pode ser instalado. O que continua fechado sem a chave também é conferido."""
import http.client, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo
from celular import servidor as S

falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def sem_chave(rota):
    con = http.client.HTTPConnection("127.0.0.1", cel.porta, timeout=10)
    con.request("GET", rota)
    r = con.getresponse(); r.read(); con.close()
    return r.status, r.getheader("Content-Type") or ""


DADOS = tempfile.mkdtemp(prefix="metalica_celinst_")
proj = os.path.join(DADOS, "dados", "obra")
os.makedirs(os.path.join(proj, "detalhamento")); os.makedirs(os.path.join(proj, "comercial"))
open(os.path.join(proj, "comercial", "comercial.json"), "w", encoding="utf-8").write("{}")
json.dump({"nome": "Obra Instalada", "alterado": "2026-10-19T21:59:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
json.dump(_modelo(), open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"))
cel = S.Celular(os.path.join(DADOS, "dados"), os.path.join(DADOS, "trabalho"), porta=_porta_livre(), host="127.0.0.1")
cel.ligar()
base = f"http://127.0.0.1:{cel.porta}"

# ---------------------------------------------------------------- sem a chave
st, tipo = sem_chave("/celular/manifest.webmanifest")
ok(st == 200 and "manifest" in tipo, f"o manifesto sai sem a chave do aparelho ({st}, {tipo})")
for icone in ("icone-180.png", "icone-192.png", "icone-512.png"):
    st, tipo = sem_chave("/celular/lib/" + icone)
    ok(st == 200 and tipo == "image/png", f"o logo {icone} sai sem a chave ({st})")
for rota in ("/celular/", "/celular/celular.js", "/celular/dados/projetos.json", "/celular/lib/pdf.min.mjs", "/celular/lib/icone-9.png"):
    ok(sem_chave(rota)[0] == 401, f"sem a chave continua fechado: {rota}")

# ---------------------------------------------------------------- o Chrome
exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celinst_")
nav = subprocess.Popen([exe, "--headless=new", "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}",
                        f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    ap = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime"): ap.cmd(f"{dm}.enable")
    ap.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)
    ap.navegar(base + "/celular/parear?c=" + cel.novo_codigo()["codigo"], limite=30)
    ok(esperar(ap, "document.querySelectorAll('.projeto').length === 1"), "pareado: a lista de projetos abre")
    ok(esperar(ap, "navigator.serviceWorker && navigator.serviceWorker.controller !== null", 20),
       "o trabalhador de fundo da cópia para a obra assume a página")
    man = ap.cmd("Page.getAppManifest")
    dados = json.loads(man.get("data") or "{}") if man.get("data") else {}
    ok(not man.get("errors") and dados.get("short_name") == "Metálica",
       f"o Chrome lê o manifesto: {dados.get('short_name')!r} {man.get('errors') or ''}")
    erros = []
    for _ in range(20):                                # o Chrome confere os ícones em segundo plano
        erros = [e.get("errorId") for e in ap.cmd("Page.getInstallabilityErrors").get("installabilityErrors", [])]
        if not erros: break
        ap.drenar(0.5)
    ok(not erros, f"o Chrome considera o app instalável, com o logo: {erros or 'sem erros'}")

    # ------------------------------------------------------------ o cartão "Instalar o Metálica"
    # Instalável, o próprio Chrome pede a instalação — e o cartão aparece sozinho, com o logo.
    ok(esperar(ap, "!!document.querySelector('#instalar [data-instalar=sim]')", 15),
       "o próprio Chrome pede a instalação: o cartão Instalar aparece na lista")
    ok(esperar(ap, "document.querySelector('#instalar img').naturalWidth === 192", 5), "com o logo carregado")
    # O botão chama a instalação: um pedido de mentira no lugar do de verdade, que abriria a janela do Chrome.
    PEDIDO = """(() => { const e = new Event('beforeinstallprompt', { cancelable: true });
      e.prompt = () => { window.__instalou = (window.__instalou || 0) + 1; return Promise.resolve(); };
      e.userChoice = Promise.resolve({ outcome: 'accepted' }); window.dispatchEvent(e); })()"""
    ap.avaliar(PEDIDO)
    ap.avaliar("document.querySelector('#instalar [data-instalar=sim]').click()")
    ok(esperar(ap, "window.__instalou === 1 && document.getElementById('instalar').innerHTML === ''", 5),
       "o botão chama a instalação do Chrome e o cartão sai")
    ap.avaliar(PEDIDO)
    ok(esperar(ap, "!!document.querySelector('#instalar [data-instalar=nao]')", 5), "o pedido volta: o cartão volta")
    ap.avaliar("document.querySelector('#instalar [data-instalar=nao]').click()")
    ap.navegar(base + "/celular/", limite=30)
    esperar(ap, "document.querySelectorAll('.projeto').length === 1")
    ap.avaliar(PEDIDO)
    ap.drenar(1.0)
    ok(ap.avaliar("document.getElementById('instalar').innerHTML === ''"), "\"Agora não\" vale também depois de recarregar")
finally:
    try: nav.kill()
    except Exception: pass
    cel.desligar()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
