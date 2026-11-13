# -*- coding: utf-8 -*-
"""O vídeo e o lote de imagens das Cenas seguem com a janela minimizada (usuário, 13/11: "Se eu minimizo a tela quando o vídeo
está sendo gerado ele para até eu retornar para tela, não tem como deixar esse processo rodando em segundo plano?").

A causa: entre um quadro e outro a gravação esperava com setTimeout(0) — numa janela minimizada o navegador segura cada um por
1 s ou mais (depois de 5 min, até 1 min) — e o lote de imagens esperava um requestAnimationFrame, que nem dispara escondida.
A correção (video_cenas.js → ceder(), a mensagem do MessageChannel, sem freio; a fila do codificador pelo evento dequeue).

Na tela das Cenas, com cliques de verdade e a janela do Chrome minimizada de verdade (Browser.setWindowBounds):
  A. Exportar › Vídeo MP4 de 2 cenas: a janela aberta, quantos quadros por segundo; minimizada (document.hidden), o vídeo
     continua no mesmo passo (≥ metade) e termina minimizada, gravado na pasta cenas da obra;
  B. Exportar › Várias em PNG com a janela minimizada: as duas imagens saem sem voltar à janela;
  C. sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, re, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_video_minimizado_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
PASTA = os.path.join(DADOS, "obra", "cenas")
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


def clicar_no(aba, sel):
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
    aba.drenar(0.2)
    return True


def quadro(aba):
    """O quadro da barra ("Vídeo · quadro 1.234 de 2.000 — …"), ou None."""
    t = aba.avaliar("document.getElementById('exportar-situacao').textContent") or ""
    m = re.search(r"quadro ([\d.]+) de ([\d.]+)", t)
    return (int(m.group(1).replace(".", "")), int(m.group(2).replace(".", ""))) if m else None


def janela(aba, estado):
    aba.cmd("Browser.setWindowBounds", windowId=JANELA, bounds={"windowState": estado})
    aba.drenar(1.0)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_video_minimizado_")
nav = subprocess.Popen([chrome, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}",
                        "--window-size=1500,900", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
erros = []
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
    JANELA = aba.cmd("Browser.getWindowForTarget")["windowId"]
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    aba.avaliar("window.__erros = []; addEventListener('error', e => __erros.push(String(e.message))); "
                "addEventListener('unhandledrejection', e => __erros.push(String(e.reason && e.reason.message || e.reason))); 1")

    # duas cenas do 3D: frente e topo
    for nome, vista in (("Frente", "frente"), ("Topo", "iso")):
        aba.avaliar(f"cenaApi.novaCena3d('{nome}'); 1")
        esperar(aba, f"cenaApi.estado().cena && cenaApi.estado().cena.nome === '{nome}'", 30)
        clicar_no(aba, f"#barra-palco [data-vista={vista}]"); clicar_no(aba, "#atualizar-vista"); aba.drenar(0.8)
    ok(aba.avaliar("cenaApi.estado().cenas") == ["frente", "topo"], "as duas cenas")

    print("A — o vídeo com a janela minimizada")
    aba.avaliar("try { localStorage.removeItem('metalica.exportarCenas'); } catch (e) {} 1")
    clicar_no(aba, "#exportar")
    ok(esperar(aba, "!!document.getElementById('exportar-caixa')", 10), "a janela Exportar abriu")
    clicar_no(aba, "input[name=formato][value=mp4]")
    clicar_no(aba, "input[name=quais][value=varias]")
    for c in ("frente", "topo"):
        if not aba.avaliar(f"document.querySelector('#exportar-varias input[value={c}]').checked"): clicar_no(aba, f"#exportar-varias input[value={c}]")
    clicar_no(aba, "input[name=lado][value=\"1920\"]"); clicar_no(aba, "input[name=qualidade][value=rapida]")
    clicar_no(aba, "#exportar-abrir") if aba.avaliar("document.getElementById('exportar-abrir').checked") else None
    esperar(aba, "window.cartoesDoVideo >= 4", 120)
    clicar_no(aba, "label.cartao-op:has(input[name=fecho][value=nenhum]) .mini"); aba.drenar(0.3)
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    # o vídeo pequeno (320 × 180, para o teste não levar 5 min: o Chrome do teste desenha por software, 0,3 quadro/s em Full HD):
    # o Full HD vale 320 só no instante do clique em Gravar (a janela lê as opções ali) e volta logo
    aba.avaliar("""(() => { const i = document.querySelector('input[name=lado][value="1920"]'); i.value = '320';
        document.getElementById('exportar-ir').click(); i.value = '1920'; return 1; })()""")
    ok(esperar(aba, "/Vídeo · quadro/.test(document.getElementById('exportar-situacao').textContent)", 60), "a gravação começou")
    # as esperas curtas (setTimeout de 0–5 ms) medidas na página: numa janela minimizada o navegador segura cada uma por 1 s
    # ou mais — a gravação que dá a vez ao navegador por elas quase para (o Chrome do teste desenha por software, devagar,
    # e a diferença não aparece só na velocidade; no computador do usuário cada quadro leva centésimos e a espera manda)
    aba.avaliar("""(() => { window.__esperas = []; const st = window.setTimeout;
        window.setTimeout = function (f, ms, ...a) { if (!(+ms > 5) && typeof f === 'function') { const t0 = performance.now(), oculta = document.hidden;
          return st.call(window, (...b) => { if (oculta) __esperas.push(performance.now() - t0); f(...b); }, ms, ...a); }
          return st.call(window, f, ms, ...a); }; return 1; })()""")
    q0, t0 = quadro(aba), time.time(); aba.drenar(4); q1 = quadro(aba)
    total = q1[1]
    print(f"        janela aberta: {(q1[0] - q0[0]) / (time.time() - t0):.1f} quadros/s ({q0[0]} → {q1[0]} de {total})")
    janela(aba, "minimized")
    ok(aba.avaliar("document.hidden") is True, "a janela minimizada (document.hidden)")
    q2, t2 = quadro(aba), time.time(); aba.drenar(10); q3 = quadro(aba)
    print(f"        minimizada: {((q3 or (total,))[0] - q2[0]) / (time.time() - t2):.1f} quadros/s ({q2[0]} → {q3[0] if q3 else 'o fim'})")
    esp = aba.avaliar("JSON.stringify((e => ({ n: e.length, soma: e.reduce((a, b) => a + b, 0), max: Math.max(0, ...e) }))(__esperas))")
    esp = json.loads(esp)
    ok(esp["soma"] < 500, f"minimizada nada segura a gravação: {esp['n']} esperas curtas, {esp['soma'] / 1000:.1f} s no total (a maior {esp['max']:.0f} ms)")
    ok(q3 is None or q3[0] > q2[0], "minimizada a barra continua andando")
    terminou = esperar(aba, "!!window.ultimoLoteCenas", 60 + 4 * (total - (q3[0] if q3 else total)))
    ok(terminou, "o vídeo terminou com a janela ainda minimizada"
       + ("" if terminou else f" (parou em: {aba.avaliar('document.getElementById(`exportar-situacao`).textContent')})"))
    ok(aba.avaliar("document.hidden") is True, "(ainda minimizada)")
    lote = json.loads(aba.avaliar("JSON.stringify(window.ultimoLoteCenas)") or "{}")
    ok(not lote.get("erro") and lote.get("gravados") == ["Vídeo - Obra Teste (cenas).mp4"], f"gravado na pasta cenas ({lote.get('gravados')}, {lote.get('erro')})")
    arq = os.path.join(PASTA, "Vídeo - Obra Teste (cenas).mp4")
    ok(os.path.isfile(arq) and open(arq, "rb").read(8)[4:8] == b"ftyp" and (lote.get("video") or {}).get("quadros") == total,
       f"o MP4 com todos os quadros ({(lote.get('video') or {}).get('quadros')} de {total})")
    janela(aba, "normal")

    print("B — o lote de imagens com a janela minimizada")
    antes = set(os.listdir(PASTA))
    clicar_no(aba, "input[name=formato][value=png]")
    clicar_no(aba, "input[name=qualidade][value=rapida]")                # o lado continua o de 320 px
    clicar_no(aba, "#exportar-baixar") if aba.avaliar("(b => !!b && b.checked)(document.getElementById('exportar-baixar'))") else None
    aba.avaliar("window.ultimoLoteCenas = null; 1")
    clicar_no(aba, "#exportar-ir")
    janela(aba, "minimized")
    ok(esperar(aba, "!!window.ultimoLoteCenas", 240), "o lote terminou com a janela minimizada")
    lote = json.loads(aba.avaliar("JSON.stringify(window.ultimoLoteCenas)") or "{}")
    novos = sorted(n for n in set(os.listdir(PASTA)) - antes if n.lower().endswith(".png"))
    ok(not lote.get("erro") and len(lote.get("gravados") or []) == 2 and len(novos) == 2, f"as duas imagens na pasta cenas ({novos}, {lote.get('erro')})")
    janela(aba, "normal")

    print("C — o console")
    erros = aba.avaliar("window.__erros") or []
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    for p in (nav, srv):
        try: p.kill()
        except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True)

print("FALHAS:", len(falhas))
for f in falhas: print("  -", f)
sys.exit(1 if falhas else 0)
