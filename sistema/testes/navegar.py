# -*- coding: utf-8 -*-
"""Mouse, teclado e olhos para um agente usar o Metálica como um usuário (16/10/2026).

Cada chamada é um comando; o estado (servidor de teste, Chrome, aba atual, últimos elementos
listados) fica em %TEMP%\\metalica_navegar\\estado.json, de modo que um agente vai dando um comando
por vez, olhando a captura e decidindo o próximo — como uma pessoa na frente da tela.

    python testes/navegar.py iniciar                  servidor de teste com pasta de projetos VAZIA + Chrome
    python testes/navegar.py ver [nome]               captura + elementos clicáveis numerados + texto visível
    python testes/navegar.py clicar 12|"Texto" [--duplo|--direito]
    python testes/navegar.py xy 800 500 [--duplo|--direito]   clique num ponto (canvas do CAD/3D)
    python testes/navegar.py arrastar x1 y1 x2 y2 [--botao meio|direito]
    python testes/navegar.py rolar x y dy             roda do mouse (dy < 0 aproxima)
    python testes/navegar.py passar x y               mouse em cima (dica/tooltip)
    python testes/navegar.py digitar "texto"          tecla por tecla, no foco atual
    python testes/navegar.py tecla Enter|Escape|ctrl+z|shift+L|F1
    python testes/navegar.py arquivo 3 C:\\caminho.dxf  escolhe o arquivo num campo de arquivo (o nº vem do `ver`)
    python testes/navegar.py texto                    todo o texto visível da página
    python testes/navegar.py abas | aba 2             janelas/abas abertas e trocar de aba
    python testes/navegar.py ir /caminho              navegar (só o que o usuário digitaria na barra)
    python testes/navegar.py erros                    erros de JavaScript desde o início
    python testes/navegar.py js "expressão"           só para diagnóstico, não para "usar" o sistema
    python testes/navegar.py parar

Nunca usa a 8765 (instalado) nem a 8766 (dev): os projetos do usuário ficam intocados.
Dois agentes ao mesmo tempo: cada um põe `--sessao=nome` logo depois de navegar.py em TODOS os comandos
(pasta %TEMP%\\metalica_navegar_<nome>).
"""
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket  # websocket-client

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# vários agentes ao mesmo tempo: `--sessao=nome` como 1º argumento (ou NAVEGAR_SESSAO) separa servidor,
# Chrome, estado e capturas; sem ela, a pasta de sempre
_SESSAO = os.environ.get("NAVEGAR_SESSAO", "")
if len(sys.argv) > 1 and sys.argv[1].startswith("--sessao="):
    _SESSAO = sys.argv.pop(1).split("=", 1)[1]
PASTA = os.path.join(tempfile.gettempdir(), "metalica_navegar" + ("_" + _SESSAO if _SESSAO else ""))
ESTADO = os.path.join(PASTA, "estado.json")
CAPTURAS = os.path.join(PASTA, "capturas")
LARGURA, ALTURA = 1600, 1000
CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
           r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _porta_livre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _json(url, tentativas=60):
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("sem resposta de " + url)


def _ler():
    if not os.path.exists(ESTADO):
        sys.exit("Nada iniciado: rode `python testes/navegar.py iniciar`.")
    return json.load(open(ESTADO, encoding="utf-8"))


def _gravar(e):
    json.dump(e, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


class Aba:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=180, suppress_origin=True)
        self.n = 0

    def cmd(self, metodo, **params):
        self.n += 1; meu = self.n
        self.ws.send(json.dumps({"id": meu, "method": metodo, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == meu:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            return {"__erro__": (d.get("exception") or {}).get("description") or d.get("text")}
        return r.get("result", {}).get("value")


# guarda os erros da página em window.__navErros (sobrevive entre comandos, não entre recargas;
# o Page.addScriptToEvaluateOnNewDocument cobre as recargas enquanto o Chrome viver)
GANCHO = r"""
(() => { if (window.__navErros) return; window.__navErros = [];
  const p = (t, m) => { try { window.__navErros.push(t + ': ' + String(m).slice(0, 400)); } catch (e) {} };
  window.addEventListener('error', ev => p('erro', ev.message + (ev.filename ? ' @' + ev.filename.split('/').pop() + ':' + ev.lineno : '')));
  window.addEventListener('unhandledrejection', ev => p('promessa', ev.reason && (ev.reason.stack || ev.reason.message) || ev.reason));
  const ce = console.error.bind(console); console.error = (...a) => { p('console', a.map(String).join(' ')); ce(...a); };
})()
"""

LISTAR = r"""
(() => {
  const SEM = 'button,a[href],input,select,textarea,summary,[role=button],[role=menuitem],[role=tab],[role=option],[role=checkbox],[onclick],[contenteditable=true],[tabindex]:not([tabindex="-1"])';
  const W = innerWidth, H = innerHeight, out = [], vistos = new Set();
  const visivel = el => { const r = el.getBoundingClientRect();
    if (r.width < 3 || r.height < 3 || r.bottom < 0 || r.right < 0 || r.top > H || r.left > W) return null;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return null;
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), W - 1), cy = Math.min(Math.max(r.top + r.height / 2, 1), H - 1);
    const topo = document.elementFromPoint(cx, cy); if (!topo || !(el === topo || el.contains(topo) || topo.contains(el))) return null;
    return {x: Math.round(cx), y: Math.round(cy), w: Math.round(r.width), h: Math.round(r.height)}; };
  const texto = el => { let t = '';
    if (el.tagName === 'INPUT') { const ty = (el.type || 'text');
      t = '[' + ty + (ty === 'checkbox' || ty === 'radio' ? (el.checked ? ' ✔' : ' ☐') : '') + '] ' + (el.labels && el.labels[0] ? el.labels[0].innerText + ' ' : '') + (el.placeholder ? '«' + el.placeholder + '» ' : '') + (ty !== 'checkbox' && ty !== 'radio' && el.value ? '= ' + el.value : ''); }
    else if (el.tagName === 'SELECT') t = '[lista] ' + (el.selectedOptions[0] ? el.selectedOptions[0].text : '') + ' (' + [...el.options].map(o => o.text).slice(0, 12).join(' | ') + ')';
    else if (el.tagName === 'TEXTAREA') t = '[caixa de texto] ' + (el.value || el.placeholder || '').slice(0, 60);
    else t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    const dica = el.getAttribute('title') || el.getAttribute('aria-label') || el.getAttribute('data-dica') || '';
    if (!t.trim() && !dica) { const img = el.querySelector('svg title, img[alt]'); if (img) t = img.textContent || img.alt || ''; }
    t = t.slice(0, 90); if (dica && !t.includes(dica)) t += (t ? '  ' : '') + '(dica: ' + dica.slice(0, 80) + ')';
    return t || '(sem texto: ' + el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') + ')'; };
  const todos = [...document.querySelectorAll('*')];
  for (const el of todos) {
    const sem = el.matches(SEM);
    let ptr = false;
    if (!sem) { const cs = getComputedStyle(el); ptr = cs.cursor === 'pointer' && (!el.parentElement || getComputedStyle(el.parentElement).cursor !== 'pointer'); }
    if (!sem && !ptr) continue;
    if (el.tagName === 'INPUT' && el.type === 'file') continue;
    const v = visivel(el); if (!v) continue;
    const t = texto(el); const k = t + '@' + Math.round(v.x / 6) + ',' + Math.round(v.y / 6); if (vistos.has(k)) continue; vistos.add(k);
    out.push({t, ...v, tag: el.tagName.toLowerCase(), des: el.disabled ? 1 : 0});
  }
  const arquivos = [...document.querySelectorAll('input[type=file]')].map((el, i) => ({i, accept: el.accept || '', multiple: el.multiple, perto: (el.closest('label,form,div') || {}).innerText ? el.closest('label,form,div').innerText.replace(/\s+/g, ' ').trim().slice(0, 80) : ''}));
  const dialogs = [...document.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],.modal,.dialogo,.janela,.aviso,.toast,.notificacao')]
    .filter(d => visivel(d)).map(d => d.innerText.replace(/\s+/g, ' ').trim().slice(0, 600)).filter(Boolean);
  const corpo = (document.body ? document.body.innerText : '').replace(/[ \t]+/g, ' ').replace(/\n{2,}/g, '\n').trim();
  return {titulo: document.title, url: location.pathname + location.search + location.hash, els: out, arquivos, dialogs, corpo,
          erros: window.__navErros || [], foco: document.activeElement ? document.activeElement.tagName + (document.activeElement.id ? '#' + document.activeElement.id : '') : ''};
})()
"""


def _conectar(e, alvo_id=None):
    porta = e["cdp"]
    alvos = [t for t in _json(f"http://127.0.0.1:{porta}/json/list") if t.get("type") == "page"]
    if not alvos:
        sys.exit("Nenhuma aba aberta.")
    alvo = None
    ids = [t["id"] for t in alvos]
    # aba nova que o sistema abriu (window.open) vira a atual sozinha, como o usuário veria
    novas = [t for t in alvos if t["id"] not in e.get("conhecidas", [])]
    if alvo_id:
        alvo = next((t for t in alvos if t["id"] == alvo_id), None)
    elif novas:
        alvo = novas[0]
        print(f"** O sistema abriu uma janela/aba nova: «{alvo.get('title', '')}» {alvo.get('url', '')} — agora é a atual.")
    else:
        alvo = next((t for t in alvos if t["id"] == e.get("aba")), alvos[0])
    e["conhecidas"] = ids
    e["aba"] = alvo["id"]
    _gravar(e)
    a = Aba(alvo["webSocketDebuggerUrl"])
    a.cmd("Page.enable")
    a.cmd("Page.bringToFront")
    a.cmd("Emulation.setDeviceMetricsOverride", width=LARGURA, height=ALTURA, deviceScaleFactor=1, mobile=False)
    a.cmd("Page.addScriptToEvaluateOnNewDocument", source=GANCHO)
    a.js(GANCHO)
    # diálogos nativos (alert/confirm/prompt) travariam a página: aceita e conta o que dizia
    return a


def _dialogo_nativo(a):
    try:
        a.ws.settimeout(0.3)
        while True:
            msg = json.loads(a.ws.recv())
            if msg.get("method") == "Page.javascriptDialogOpening":
                p = msg["params"]
                print(f"** Caixa do navegador ({p.get('type')}): «{p.get('message')}» — respondida com OK.")
                a.cmd("Page.handleJavaScriptDialog", accept=True, promptText=p.get("defaultPrompt", ""))
    except Exception:
        pass
    finally:
        a.ws.settimeout(180)


def _esperar(a, s):
    fim = time.time() + s
    while time.time() < fim:
        _dialogo_nativo(a)
        time.sleep(0.2)


def _foto(a, e, nome=""):
    os.makedirs(CAPTURAS, exist_ok=True)
    e["n_foto"] = e.get("n_foto", 0) + 1
    nome = "".join(c if c.isalnum() or c in "-_" else "-" for c in (nome or "tela"))[:40]
    arq = os.path.join(CAPTURAS, f"{e['n_foto']:03d}-{nome}.png")
    r = a.cmd("Page.captureScreenshot", format="png")
    open(arq, "wb").write(base64.b64decode(r["data"]))
    _gravar(e)
    return arq


def _ver(a, e, nome="", texto_max=1800):
    _esperar(a, 0.3)
    info = a.js(LISTAR) or {}
    if "__erro__" in info:
        print("não consegui ler a página:", info["__erro__"]); return
    arq = _foto(a, e, nome)
    e["els"] = [{"t": x["t"], "x": x["x"], "y": x["y"]} for x in info["els"]]
    _gravar(e)
    print(f"CAPTURA: {arq}")
    print(f"PÁGINA: {info['titulo']}  —  {info['url']}   (foco: {info['foco']})")
    if info["dialogs"]:
        print("JANELAS/AVISOS NA FRENTE:")
        for d in info["dialogs"][:4]:
            print("  »", d)
    print(f"CLICÁVEIS ({len(info['els'])}):")
    for i, x in enumerate(info["els"]):
        print(f"  [{i}] {x['t']}  @{x['x']},{x['y']}{'  (desabilitado)' if x['des'] else ''}")
    for f in info["arquivos"]:
        print(f"  [arquivo {f['i']}] aceita «{f['accept']}»{' vários' if f['multiple'] else ''} — perto de: {f['perto']}")
    corpo = info["corpo"]
    print(f"TEXTO VISÍVEL ({len(corpo)} car.):")
    print(corpo[:texto_max] + (" …(use `texto` para o resto)" if len(corpo) > texto_max else ""))
    novos = info["erros"][e.get("n_erros", 0):]
    if novos:
        print("ERROS DE JAVASCRIPT NOVOS:")
        for x in novos[:10]:
            print("  !", x)
    e["n_erros"] = len(info["erros"]); _gravar(e)


def _mouse(a, x, y, botao="left", cliques=1):
    a.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    for c in range(1, cliques + 1):
        a.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=botao, clickCount=c, buttons=1 if botao == "left" else (2 if botao == "right" else 4))
        a.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=botao, clickCount=c)


TECLAS = {"enter": (13, "Enter", "\r"), "escape": (27, "Escape", ""), "esc": (27, "Escape", ""), "tab": (9, "Tab", ""),
          "delete": (46, "Delete", ""), "del": (46, "Delete", ""), "backspace": (8, "Backspace", ""), "espaco": (32, "Space", " "),
          "space": (32, "Space", " "), "arrowleft": (37, "ArrowLeft", ""), "arrowup": (38, "ArrowUp", ""),
          "arrowright": (39, "ArrowRight", ""), "arrowdown": (40, "ArrowDown", ""), "home": (36, "Home", ""), "end": (35, "End", ""),
          "pageup": (33, "PageUp", ""), "pagedown": (34, "PageDown", "")}
NOMES = {"Space": " ", "Escape": "Escape", "Enter": "Enter"}


def _tecla(a, combo):
    partes = combo.split("+")
    base = partes[-1]
    mods = 0
    for m in partes[:-1]:
        m = m.lower()
        mods |= {"alt": 1, "ctrl": 2, "control": 2, "meta": 4, "shift": 8}.get(m, 0)
    b = base.lower()
    if b in TECLAS:
        vk, code, txt = TECLAS[b]; key = NOMES.get(code, code)
    elif b.startswith("f") and b[1:].isdigit():
        vk, code, txt = 111 + int(b[1:]), base.upper(), ""; key = code
    elif len(base) == 1:
        ch = base
        if mods & 8 and ch.isalpha(): ch = ch.upper()
        vk = ord(ch.upper()) if ch.isalnum() else 0
        code = ("Key" + ch.upper()) if ch.isalpha() else (("Digit" + ch) if ch.isdigit() else "")
        key, txt = ch, ch
    else:
        sys.exit(f"tecla desconhecida: {combo}")
    texto = txt if not (mods & 3) else ""
    p = dict(modifiers=mods, windowsVirtualKeyCode=vk, key=key, code=code)
    a.cmd("Input.dispatchKeyEvent", type="keyDown" if texto else "rawKeyDown", text=texto, **p)
    a.cmd("Input.dispatchKeyEvent", type="keyUp", **p)


def iniciar(args):
    if os.path.exists(ESTADO):
        try:
            parar([], silencioso=True)
        except SystemExit:
            pass
    shutil.rmtree(PASTA, ignore_errors=True)
    os.makedirs(CAPTURAS, exist_ok=True)
    dados = os.path.join(PASTA, "projetos")   # vazia: o primeiro uso de verdade
    os.makedirs(dados, exist_ok=True)
    porta = _porta_livre()
    extra = ["--dev"] if "--dev" in args else []
    log = open(os.path.join(PASTA, "servidor.log"), "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", dados] + extra,
                           stdout=log, stderr=subprocess.STDOUT, cwd=BASE,
                           creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://localhost:{porta}/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit("o servidor de teste não subiu; veja " + os.path.join(PASTA, "servidor.log"))
    chrome = next((c for c in CHROMES if os.path.exists(c)), None)
    if not chrome:
        sys.exit("Chrome/Edge não encontrado")
    cdp = _porta_livre()
    perfil = os.path.join(PASTA, "perfil")
    nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader",
                            "--no-first-run", "--remote-allow-origins=*", f"--window-size={LARGURA},{ALTURA}",
                            f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    e = {"porta": porta, "cdp": cdp, "srv": srv.pid, "nav": nav.pid, "dados": dados, "aba": None, "conhecidas": []}
    _json(f"http://127.0.0.1:{cdp}/json/version")
    _gravar(e)
    a = _conectar(e)
    a.cmd("Page.navigate", url=f"http://localhost:{porta}/")
    _esperar(a, 3)
    print(f"Servidor de teste em http://localhost:{porta}  (projetos em {dados}, vazio)")
    print(f"Capturas em {CAPTURAS}")
    _ver(a, e, "inicio")


def parar(args, silencioso=False):
    e = _ler()
    for pid in (e.get("nav"), e.get("srv")):
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not silencioso:
        print("Servidor e Chrome encerrados. Capturas continuam em", CAPTURAS)
    os.remove(ESTADO)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    c, args = sys.argv[1], sys.argv[2:]
    if c == "iniciar":
        return iniciar(args)
    if c == "parar":
        return parar(args)
    e = _ler()
    opc = [x for x in args if x.startswith("--")]
    pos = [x for x in args if not x.startswith("--")]
    espera = 1.5
    for o in opc:
        if o.startswith("--espera="):
            espera = float(o.split("=", 1)[1])
    if c == "abas":
        for i, t in enumerate(x for x in _json(f"http://127.0.0.1:{e['cdp']}/json/list") if x.get("type") == "page"):
            print(f"[{i}] {'* ' if t['id'] == e.get('aba') else '  '}{t.get('title')} — {t.get('url')}")
        return
    if c == "aba":
        alvos = [x for x in _json(f"http://127.0.0.1:{e['cdp']}/json/list") if x.get("type") == "page"]
        a = _conectar(e, alvos[int(pos[0])]["id"]); return _ver(a, e, "aba")
    a = _conectar(e)
    if c == "ver":
        return _ver(a, e, pos[0] if pos else "tela")
    if c == "texto":
        print((a.js("document.body ? document.body.innerText : ''") or "")); return
    if c == "erros":
        for x in a.js("window.__navErros || []") or []:
            print(" !", x)
        print(open(os.path.join(PASTA, "servidor.log"), encoding="utf-8", errors="replace").read()[-3000:])
        return
    if c == "js":
        print(json.dumps(a.js(pos[0]), ensure_ascii=False, indent=1)[:6000]); return
    if c == "ir":
        url = pos[0] if pos[0].startswith("http") else f"http://localhost:{e['porta']}{pos[0] if pos[0].startswith('/') else '/' + pos[0]}"
        a.cmd("Page.navigate", url=url); _esperar(a, max(espera, 3)); return _ver(a, e, "ir")
    botao = "right" if "--direito" in opc else ("middle" if "--meio" in opc else "left")
    cliques = 2 if "--duplo" in opc else 1
    if c == "clicar":
        alvo = pos[0]
        els = e.get("els") or []
        if alvo.isdigit():
            if int(alvo) >= len(els):
                sys.exit("número fora da lista; rode `ver` de novo")
            el = els[int(alvo)]
        else:
            # pelo texto, na tela de agora (o usuário lê o botão e clica)
            info = a.js(LISTAR) or {}
            els = info.get("els", [])
            al = alvo.lower()
            el = next((x for x in els if x["t"].lower() == al), None) or next((x for x in els if x["t"].lower().startswith(al)), None) \
                or next((x for x in els if al in x["t"].lower()), None)
            if not el:
                sys.exit(f"não achei «{alvo}» na tela")
        print(f"clicando em «{el['t']}» @{el['x']},{el['y']}")
        _mouse(a, el["x"], el["y"], botao, cliques)
    elif c == "xy":
        _mouse(a, float(pos[0]), float(pos[1]), botao, cliques)
    elif c == "passar":
        a.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=float(pos[0]), y=float(pos[1]))
    elif c == "arrastar":
        x1, y1, x2, y2 = map(float, pos[:4])
        b = "middle" if "--botao=meio" in opc or "--meio" in opc else ("right" if "--direito" in opc else "left")
        bits = {"left": 1, "right": 2, "middle": 4}[b]
        a.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x1, y=y1)
        a.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x1, y=y1, button=b, buttons=bits, clickCount=1)
        for k in range(1, 13):
            a.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x1 + (x2 - x1) * k / 12, y=y1 + (y2 - y1) * k / 12, button=b, buttons=bits)
            time.sleep(0.02)
        a.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x2, y=y2, button=b, buttons=0, clickCount=1)
    elif c == "rolar":
        a.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=float(pos[0]), y=float(pos[1]), deltaX=0, deltaY=float(pos[2]))
    elif c == "digitar":
        for ch in pos[0]:
            if ch == "\n":
                _tecla(a, "Enter")
            else:
                a.cmd("Input.dispatchKeyEvent", type="keyDown", text=ch, key=ch)
                a.cmd("Input.dispatchKeyEvent", type="keyUp", key=ch)
    elif c == "tecla":
        for t in pos:
            _tecla(a, t)
    elif c == "arquivo":
        caminho = os.path.abspath(pos[1])
        doc = a.cmd("DOM.getDocument", depth=-1, pierce=True)
        ids = a.cmd("DOM.querySelectorAll", nodeId=doc["root"]["nodeId"], selector="input[type=file]")["nodeIds"]
        i = int(pos[0])
        if i >= len(ids):
            sys.exit(f"só há {len(ids)} campo(s) de arquivo")
        a.cmd("DOM.setFileInputFiles", files=[caminho], nodeId=ids[i])
        print(f"arquivo escolhido: {caminho}")
    else:
        sys.exit("comando desconhecido: " + c)
    _esperar(a, espera)
    _ver(a, e, c + ("-" + pos[0] if pos and len(pos[0]) < 25 else ""))


if __name__ == "__main__":
    main()
