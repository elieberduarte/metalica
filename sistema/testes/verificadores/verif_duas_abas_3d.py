# -*- coding: utf-8 -*-
r"""Duas abas no 3D da mesma obra (D01 do usuario-desastrado, 13/11: "um Ctrl+S na aba B, até sem mudança nenhuma, faz
a aba A perder tudo dali em diante, com o botão mostrando '✓ Salvo'").

Duas abas de verdade no mesmo projeto (dois alvos do Chrome), teclas e cliques de verdade:
  A. aba B: Ctrl+S sem mexer em nada → "Nada mudou", o modelo.json fica como estava (a data não muda);
  B. aba A: Delete numa peça → a gravação automática grava (o modelo perde a peça) — antes o Ctrl+S da B a derrubava;
  C. aba B (que carregou antes da gravação da A): Delete noutra peça → o servidor recusa (409) e a B mostra
     "⚠ Não gravado" (data-estado="conflito"), não "✓ Salvo"; o modelo.json continua o da A;
  D. a B pergunta antes de sair (o beforeunload cancelado);
  F. a escolha (usuário, 13/11: "Escolher, com histórico"), pelo clique no "⚠ Não gravado": F1 "Gravar as minhas por
     cima" com a confirmação que diz de quando é a versão substituída, e ela no histórico; F2 a outra aba cai no
     "⚠ Não gravado" e "Abrir a versão gravada" recarrega, com as mudanças dela no histórico (capturas
     duas_abas_escolha.png e duas_abas_confirmar_por_cima.png);
  E. sem erros no console (fora o 409 esperado).
Falha sem a correção (o botão da B volta a "salvo" e o beforeunload não pergunta). Porta livre, nunca a 8765/8766."""
import json, os, re, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_duas_abas_")
pasta = os.path.join(DADOS, "duas-abas")
os.makedirs(pasta)


def _caixa(i):
    x = i * 2000.0
    v = [[x, 0, 0], [x + 500, 0, 0], [x + 500, 500, 0], [x, 500, 0], [x, 0, 3000], [x + 500, 0, 3000], [x + 500, 500, 3000], [x, 500, 3000]]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return {"id": "P%d" % i, "tipo": "solido", "nome": "P%d" % i, "camada": "Layer0", "material": "", "vertices": v, "faces": f,
            "arestas_vivas": [], "atributos": {}}


json.dump({"nome": "duas-abas", "unidade": "mm", "camadas": {"Layer0": {"nome": "Layer0", "cor": "#8a94a6", "visivel": True, "bloqueada": False}},
           "materiais": {}, "entidades": [_caixa(i) for i in range(1, 7)]},
          open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"formato": 1, "nome": "duas-abas", "tipo": "ifc", "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00"},
          open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
MODELO = os.path.join(pasta, "modelo.json")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def ids_no_disco():
    return sorted(e["id"] for e in json.load(open(MODELO, encoding="utf-8"))["entidades"])


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_duas_abas_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)

    def abrir_aba(ws):
        a = Aba(ws)
        for dm in ("Page", "Runtime", "Log"): a.cmd(f"{dm}.enable")
        a.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
        return a

    A = abrir_aba(alvos[0]["webSocketDebuggerUrl"])
    import urllib.request
    novo = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{cdp}/json/new?about:blank", method="PUT")).read())
    B = abrir_aba(novo["webSocketDebuggerUrl"])

    def esperar(aba, expr, limite=60):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                v = aba.avaliar(expr)
                if v: return v
            except Exception: pass
            aba.drenar(0.3)
        return None

    PRONTO = "!!(window.editor && editor.documento && editor.documento.entidades.size === 6 && document.body.dataset.pronto === '1')"
    A.navegar(base + "/editor?projeto=duas-abas", limite=90)
    ok(bool(esperar(A, PRONTO, 120)), "aba A abriu (6 peças)")
    B.navegar(base + "/editor?projeto=duas-abas", limite=90)
    ok(bool(esperar(B, PRONTO, 120)), "aba B abriu a mesma obra (6 peças)")

    def tecla(aba, key, code, vk, mod=0):
        for tipo in ("rawKeyDown", "keyUp"):
            aba.cmd("Input.dispatchKeyEvent", type=tipo, key=key, code=code, windowsVirtualKeyCode=vk, modifiers=mod)
        aba.drenar(0.3)

    def apagar(aba, pid):
        aba.avaliar(f"editor.selecao.definir([{json.dumps(pid)}]); 1")
        aba.avaliar("document.querySelector('canvas').focus && document.querySelector('canvas').focus(); 1")
        tecla(aba, "Delete", "Delete", 46)

    ESTADO = "(() => { const b = document.querySelector('.btn-salvar'); return b ? b.dataset.estado + '|' + b.textContent : ''; })()"

    # --- A. aba B: Ctrl+S sem mudança
    t_antes = os.path.getmtime(MODELO)
    time.sleep(1.2)
    tecla(B, "s", "KeyS", 83, mod=2)
    aviso = esperar(B, "(() => { const t = document.body.innerText; return /Nada mudou desde a última gravação/.test(t) ? 'sim' : null; })()", 10)
    ok(aviso == "sim", "[A] Ctrl+S sem mudança na B: \"Nada mudou\"")
    ok(abs(os.path.getmtime(MODELO) - t_antes) < 0.01, "[A] o modelo.json não foi regravado (a data ficou)")

    # --- B. aba A apaga o P5: grava
    apagar(A, "P5")
    ok(esperar(A, "editor.documento.entidades.size === 5", 10) is True, "[B] a A apagou o P5")
    t0 = time.time()
    while time.time() - t0 < 20 and "P5" in ids_no_disco():
        A.drenar(0.5)
    ok("P5" not in ids_no_disco(), f"[B] a gravação automática da A gravou (no disco: {ids_no_disco()})")
    ok((esperar(A, f"{ESTADO}.startsWith('salvo') ? {ESTADO} : null", 20) or "").startswith("salvo"), "[B] a A diz \"✓ Salvo\"")

    # --- C. aba B (versão velha) apaga o P2: o servidor recusa e a B diz "⚠ Não gravado"
    apagar(B, "P2")
    ok(esperar(B, "editor.documento.entidades.size === 5", 10) is True, "[C] a B apagou o P2 (na tela dela)")
    est = esperar(B, f"{ESTADO}.startsWith('conflito') ? {ESTADO} : null", 25) or B.avaliar(ESTADO)
    ok(str(est).startswith("conflito") and "Não gravado" in str(est), f"[C] o botão da B: \"⚠ Não gravado\" ({est!r})")
    B.drenar(6)
    est2 = B.avaliar(ESTADO)
    ok(str(est2).startswith("conflito"), f"[C] e continua assim (não volta a \"✓ Salvo\": {est2!r})")
    ok(ids_no_disco() == ["P1", "P2", "P3", "P4", "P6"], f"[C] o disco continua o da A ({ids_no_disco()})")
    ok(bool(esperar(B, "/NÃO foram gravadas/.test(document.body.innerText)", 5)), "[C] o aviso diz que as edições da B não foram gravadas")

    # --- D. sair da B pergunta
    pergunta = B.avaliar("(() => { const ev = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(ev); return ev.defaultPrevented; })()")
    ok(pergunta is True, "[D] sair da B pergunta antes (beforeunload)")

    # --- F. a escolha (usuário, 13/11: "Escolher, com histórico"), pelo botão "⚠ Não gravado" de verdade
    import base64

    def clicar(aba, seletor):
        c = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; const q = b.getBoundingClientRect(); return q.width ? [q.left + q.width / 2, q.top + q.height / 2] : null; }})()")
        if not c: return False
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=c[0], y=c[1], button="left", clickCount=1)
        aba.drenar(0.4)
        return True

    def foto(aba, nome):
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), nome), "wb").write(
            base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    ok(clicar(B, ".btn-salvar"), "[F] clique no \"⚠ Não gravado\" da B")
    txt = esperar(B, "(() => { const d = document.querySelector('#dialogo'); return d && d.open ? d.textContent : null; })()", 10) or ""
    ok("Gravar as minhas por cima" in txt and "Abrir a versão gravada" in txt, f"[F] a escolha abre com as duas saídas ({' '.join(txt.split())[:120]!r})")
    foto(B, "duas_abas_escolha.png")
    # F1. gravar por cima: confirmação com a data da versão substituída, depois grava; a da A vai para o histórico
    clicar(B, "#dialogo-ok")
    txt = esperar(B, "(() => { const d = document.querySelector('#dialogo'); return d && d.open && /Gravar as minhas por cima\\?/.test(d.textContent) ? d.textContent : null; })()", 10) or ""
    ok(bool(re.search(r"gravada em \d\d/\d\d \d\d:\d\d será substituída", txt)), f"[F1] a confirmação diz de quando é a versão substituída ({' '.join(txt.split())[:140]!r})")
    foto(B, "duas_abas_confirmar_por_cima.png")
    clicar(B, "#dialogo-ok")
    t0 = time.time()
    while time.time() - t0 < 20 and ids_no_disco() != ["P1", "P3", "P4", "P5", "P6"]:
        B.drenar(0.5)
    ok(ids_no_disco() == ["P1", "P3", "P4", "P5", "P6"], f"[F1] gravou a da B por cima ({ids_no_disco()})")
    ok((esperar(B, f"{ESTADO}.startsWith('salvo') ? {ESTADO} : null", 15) or "").startswith("salvo"), "[F1] a B diz \"✓ Salvo\" de verdade")
    hist = _json(f"{base}/api/projetos/duas-abas/historico")["historico"]
    ok(hist and hist[0]["rotulo"].startswith("antes de gravar por cima"), f"[F1] a versão da A está no histórico ({hist[:1]})")
    # F2. agora a A está desatualizada: apaga o P1 → "⚠ Não gravado" → "Abrir a versão gravada"
    # quem clica na escolha está olhando a aba A: ela vem para a frente (no Chrome sem janela a aba de trás, escondida,
    # não chegava a montar o texto do modelo depois do clique — 14/11, 1ª rodada; ninguém clica numa aba que não vê)
    A.cmd("Page.bringToFront")
    apagar(A, "P1")
    est = esperar(A, f"{ESTADO}.startsWith('conflito') ? {ESTADO} : null", 25)
    ok(bool(est), f"[F2] a A cai no \"⚠ Não gravado\" na gravação seguinte ({est!r})")
    clicar(A, ".btn-salvar")
    esperar(A, "document.querySelector('#dialogo').open", 10)
    A.avaliar("[...document.querySelectorAll('#dialogo-corpo button')].find(b => /Abrir a versão gravada/.test(b.textContent)).setAttribute('data-verif', 'abrir'); 1")
    clicar(A, '[data-verif="abrir"]')
    ok(bool(esperar(A, "window.editor && editor.documento && editor.documento.entidades.size === 5 && document.body.dataset.pronto === '1' && !editor._conflito", 60)),
       "[F2] a A recarregou com a versão gravada (a da B, 5 peças)")
    ok(bool(esperar(A, "/Aberta a versão gravada/.test(document.body.innerText)", 10)), "[F2] o aviso diz onde ficaram as mudanças da A")
    ok(ids_no_disco() == ["P1", "P3", "P4", "P5", "P6"], f"[F2] o disco não mudou ({ids_no_disco()})")
    hist = _json(f"{base}/api/projetos/duas-abas/historico")["historico"]
    ok(hist and hist[0]["rotulo"].startswith("edições não gravadas"), f"[F2] as mudanças da A estão no histórico ({hist[:1]})")

    # --- E. console
    for nome, aba in (("A", A), ("B", B)):
        erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x) and "409" not in str(x)]
        ok(not erros, f"[E] aba {nome} sem erros no console: {erros[:3]}")
finally:
    print("\nFALHAS: %d" % len(falhas))
    for f in falhas: print("  -", f)
    srv.terminate(); nav.terminate()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)
sys.exit(1 if falhas else 0)
