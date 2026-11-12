# -*- coding: utf-8 -*-
"""Os vídeos da obra assistidos dentro do sistema (usuário, 12/11: "quero assistir dentro do sistema" — antes só tocava o vídeo
recém-gravado, na janela do Exportar; os de antes ficavam na pasta cenas/ e abriam pelo 📁). Na tela das Cenas, com cliques
de verdade:
  A. sem vídeo na pasta: 🎬 Vídeos abre a janela dizendo como fazer um;
  B. dois MP4 gravados pela própria tela (o GravadorMp4 do vídeo das cenas, mandados pela rota …/cenas/video): a lista com o
     mais novo primeiro, a duração e o tamanho; o mais novo começa tocando (o tempo anda);
  C. escolher o outro na lista: o player troca de vídeo (a duração dele) e PULA NO TEMPO (o servidor não responde por
     partes: o vídeo toca da memória — sem isso o <video> não sai do lugar);
  D. 📁 Mostrar na pasta seleciona o vídeo tocando (o pedido interceptado: nenhum Explorador abre na máquina);
  E. Esc fecha: sem player, sem vídeo tocando;
  F. sem erro no console.
Porta livre, nunca a 8765/8766. Captura na pasta temporária metalica_saida_videos_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_videos_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_videos_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
PASTA_CENAS = os.path.join(DADOS, "obra", "cenas")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30.0):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def clicar_no(aba, sel, botao="left"):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button=botao, clickCount=1)
    aba.drenar(0.2)
    return True


# um MP4 de verdade, feito pela tela com o gravador do vídeo das cenas: `seg` segundos, uma cor por segundo, mandado à pasta
GRAVAR = """(async (nome, seg) => {
  const { GravadorMp4 } = await import('/visor3d/video_cenas.js');
  const g = await GravadorMp4.abrir(320, 180, 30), cv = document.createElement('canvas'); cv.width = 320; cv.height = 180;
  const c = cv.getContext('2d');
  for (let i = 0; i < seg; i++) { c.fillStyle = `hsl(${i * 70}, 70%, 50%)`; c.fillRect(0, 0, 320, 180); c.fillStyle = '#fff';
    c.font = '60px sans-serif'; c.fillText(String(i), 140, 110); await g.quadro(cv, 30); }
  const blob = await g.fim();
  const r = await fetch('/api/projetos/obra/terreno/cenas/video', { method: 'POST', body: blob,
    headers: { 'Content-Type': 'application/octet-stream', 'X-Nome-Arquivo': encodeURIComponent(nome) } });
  return (await r.json()).nome;
})"""

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_videos_cenas_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--autoplay-policy=no-user-gesture-required",
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
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")

    print("A — sem vídeo ainda")
    ok(clicar_no(aba, "#videos-cenas") and esperar(aba, "!!document.getElementById('videos-caixa')", 5), "🎬 Vídeos abre a janela")
    ok(esperar(aba, "document.getElementById('videos-lista').textContent.includes('Nenhum vídeo')", 10)
       and "Exportar" in aba.avaliar("document.getElementById('videos-palco').textContent"), "nenhum vídeo: diz como fazer um")
    clicar_no(aba, "#videos-fechar")
    ok(esperar(aba, "!document.getElementById('videos-caixa')", 5), "Fechar fecha")

    print("B — dois vídeos gravados")
    aba.avaliar(f"window.gravado = null; {GRAVAR}('Vídeo - Antigo.mp4', 4).then(n => window.gravado = n, e => window.gravado = 'erro: ' + e.message); 1")
    ok(esperar(aba, "window.gravado !== null", 60) and aba.avaliar("window.gravado") == "Vídeo - Antigo.mp4", f"o 1º vídeo gravado ({aba.avaliar('window.gravado')})")
    aba.avaliar(f"window.gravado = null; {GRAVAR}('Vídeo - Obra Teste (cenas).mp4', 2).then(n => window.gravado = n, e => window.gravado = 'erro: ' + e.message); 1")
    ok(esperar(aba, "window.gravado !== null", 60) and aba.avaliar("window.gravado") == "Vídeo - Obra Teste (cenas).mp4", "o 2º vídeo gravado")
    agora = time.time()
    os.utime(os.path.join(PASTA_CENAS, "Vídeo - Antigo.mp4"), (agora - 3600, agora - 3600))
    clicar_no(aba, "#videos-cenas")
    ok(esperar(aba, "document.querySelectorAll('#videos-lista button').length === 2", 10), "a lista com os dois")
    itens = aba.avaliar("[...document.querySelectorAll('#videos-lista button')].map(b => [b.dataset.nome, b.querySelector('small').textContent])")
    ok(itens and itens[0][0] == "Vídeo - Obra Teste (cenas).mp4" and itens[1][0] == "Vídeo - Antigo.mp4", f"o mais novo primeiro ({itens})")
    ok(itens and "2 s" in itens[0][1] and "4 s" in itens[1][1] and " KB" in itens[0][1] and "0,0" not in itens[0][1],
       "a duração e o tamanho de cada um (o pequeno em KB, não \"0,0 MB\")")
    ok(aba.avaliar("document.getElementById('videos-palco').offsetHeight >= document.querySelector('#videos-caixa .videos-corpo').offsetHeight - 2"),
       "o palco preto ocupa a altura toda da janela")
    ok(esperar(aba, "(() => { const v = document.getElementById('videos-player'); return v && v.readyState >= 2 && v.currentTime > 0.3; })()", 30),
       f"o mais novo começa tocando ({aba.avaliar('window.videosCenas')})")
    ok(aba.avaliar("document.querySelector('#videos-lista button.sel').dataset.nome") == "Vídeo - Obra Teste (cenas).mp4", "e fica marcado na lista")
    dur = aba.avaliar("document.getElementById('videos-player').duration")
    ok(dur and abs(dur - 2) < 0.2, f"a duração no player ({dur})")

    print("C — o outro vídeo, pulando no tempo")
    clicar_no(aba, "#videos-lista button[data-nome='Vídeo - Antigo.mp4']")
    ok(esperar(aba, "(() => { const v = document.getElementById('videos-player'); return v && v.readyState >= 1 && Math.abs(v.duration - 4) < 0.2; })()", 30),
       "o player troca para o outro (4 s)")
    aba.avaliar("(() => { const v = document.getElementById('videos-player'); v.pause(); window.pulou = false;"
                " v.addEventListener('seeked', () => { window.pulou = v.currentTime; }, { once: true }); v.currentTime = 3.0; return 1; })()")
    ok(esperar(aba, "window.pulou !== false", 10) and abs((aba.avaliar("window.pulou") or 0) - 3.0) < 0.2,
       f"pula para 3 s ({aba.avaliar('window.pulou')})")
    d = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(os.path.join(SAIDA, "janela-videos.png"), "wb").write(base64.b64decode(d))

    print("D — mostrar na pasta")
    aba.avaliar("""window.pedidosMostrar = []; const f0 = window.fetch;
      window.fetch = (u, o) => { if (String(u).endsWith('/cenas/mostrar')) { window.pedidosMostrar.push(JSON.parse(o.body).nome);
        return Promise.resolve(new Response('{"pasta": "x"}', { headers: { 'Content-Type': 'application/json' } })); } return f0(u, o); }; 1""")
    ok(clicar_no(aba, "#videos-mostrar") and esperar(aba, "window.pedidosMostrar.length === 1", 5)
       and aba.avaliar("window.pedidosMostrar[0]") == "Vídeo - Antigo.mp4", "📁 Mostrar na pasta seleciona o vídeo tocando")

    print("E — Esc fecha")
    clicar_no(aba, "#videos-lista button.sel")              # o foco dentro da janela
    aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    ok(esperar(aba, "!document.getElementById('videos-caixa')", 5), "a janela fecha")
    ok(aba.avaliar("!document.querySelector('video') && window.videosCenas.tocando === null"), "sem player, nada tocando")

    print("F — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print(f"\ncapturas em {SAIDA}")
print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
