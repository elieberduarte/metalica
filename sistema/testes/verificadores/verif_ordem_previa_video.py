# -*- coding: utf-8 -*-
"""A ordem das cenas e a prévia do voo na janela Exportar › Vídeo MP4 (usuário, 13/11: "gostaria de poder mexer na ordem das
cenas, por exemplo colocar vista de cima por primeiro para ele iniciar por ela, e se tivesse como ao lado ter um preview sem
renderizar só para ver como o vídeo está ficando"). Na tela das Cenas, com o galpão de exemplo e 3 cenas, cliques de verdade:
  A. ↑ ↓ na lista Várias: a ordem muda no resumo do vídeo (C → A → B); a ordem dos cartões não muda;
  B. reabrir a janela: a ordem guardada;
  C. ▶ Prévia do voo: um canvas no lugar da imagem, desenhado; os trechos na ordem escolhida; no tempo do vídeo (pula
     quadros quando atrasa, não vira câmera lenta); termina sozinha;
  D. ■ Parar e mudar uma opção param a prévia (a imagem parada volta);
  E. sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ordem_previa_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-13T00:00:00", "alterado": "2026-11-13T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
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


def abrir_janela(aba):
    clicar_no(aba, "#exportar")
    esperar(aba, "!!document.getElementById('exportar-caixa')", 5)
    clicar_no(aba, "#exportar-caixa input[name=formato][value=mp4]")
    clicar_no(aba, "#exportar-caixa input[name=quais][value=varias]")
    aba.drenar(0.5)


ordem_da_lista = "[...document.querySelectorAll('#exportar-varias .linha-cena')].map(l => l.dataset.cena)"
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ordem_previa_")
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
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    # 3 cenas de vistas diferentes (A, B, C), sem abertura e sem fechamento no vídeo (a prévia fica curta)
    for nome, vista in (("A", "frente"), ("B", "lado"), ("C", "topo")):
        clicar_no(aba, f"#barra-palco [data-vista={vista}]")
        aba.avaliar(f"cenaApi.novaCena3d('{nome}'); 1")
        esperar(aba, f"cenaApi.estado().cena && cenaApi.estado().cena.id === '{nome.lower()}'", 30)
        aba.drenar(0.5)
    ok(aba.avaliar("cenaApi.estado().cenas.join(',')") == "a,b,c", "as 3 cenas A, B, C")

    print("A — ↑ ↓ na lista")
    abrir_janela(aba)
    for c in ("a", "b", "c"):
        aba.avaliar(f"(() => {{ const i = document.querySelector('#exportar-varias input[value={c}]'); if (!i.checked) i.click(); return 1; }})()")
    clicar_no(aba, "#exportar-caixa input[name=fecho][value=nenhum]")
    clicar_no(aba, "#exportar-caixa input[name=abertura][value=nenhuma]")
    clicar_no(aba, "#exportar-caixa input[name=velocidade][value=rapido]")
    ok(aba.avaliar(ordem_da_lista) == ["a", "b", "c"], "a lista começa na ordem dos cartões")
    clicar_no(aba, "#exportar-varias .linha-cena[data-cena=c] button[data-mover='-1']")
    clicar_no(aba, "#exportar-varias .linha-cena[data-cena=c] button[data-mover='-1']")
    ok(aba.avaliar(ordem_da_lista) == ["c", "a", "b"], f"C subiu para o começo ({aba.avaliar(ordem_da_lista)})")
    info = aba.avaliar("document.getElementById('exportar-info').textContent")
    ok("C → A → B" in info, f"o resumo do vídeo na ordem nova ({info})")
    clicar_no(aba, "#exportar-varias .linha-cena[data-cena=b] button[data-mover='1']")      # o último não desce mais
    ok(aba.avaliar(ordem_da_lista) == ["c", "a", "b"], "o último não desce além do fim")
    ok(aba.avaliar("[...document.querySelectorAll('.cartao-cena')].map(b => b.dataset.cena).join(',')") == "a,b,c", "a ordem dos cartões não muda")

    print("B — a ordem guardada")
    clicar_no(aba, "#exportar-cancelar"); esperar(aba, "!document.getElementById('exportar-caixa')", 5)
    abrir_janela(aba)
    ok(aba.avaliar(ordem_da_lista) == ["c", "a", "b"], f"ao reabrir, C → A → B ({aba.avaliar(ordem_da_lista)})")

    print("C — a prévia do voo")
    ok(aba.avaliar("!document.getElementById('exportar-voo-linha').hidden"), "o botão ▶ Prévia do voo aparece no vídeo")
    t0 = time.time()
    clicar_no(aba, "#exportar-voo-bt")
    ok(esperar(aba, "!!document.getElementById('exportar-voo') && document.getElementById('exportar-previa').hidden", 10), "um canvas no lugar da imagem")
    ok(esperar(aba, "window.previaDoVoo && window.previaDoVoo.quadros > 3", 60), "a prévia anda")
    desenhado = aba.avaliar("(() => { const c = document.getElementById('exportar-voo'); if (!c) return 0; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                            " let n = 0; for (let i = 0; i < d.length; i += 400) if (d[i + 3] > 0) n++; return n; })()")
    ok(desenhado > 50, f"o canvas desenhado ({desenhado} amostras com cor)")
    ok(esperar(aba, "window.previaDoVoo && window.previaDoVoo.terminou", 90), "termina sozinha")
    dur = time.time() - t0
    trechos = aba.avaliar("window.previaDoVoo.trechos")
    ok(trechos and trechos[0] == "C → A" and "A → B" in trechos, f"os trechos na ordem escolhida ({trechos})")
    # 3 cenas, rápido (2 s por trecho): o voo tem ~4 s; câmera lenta passaria muito disso
    ok(dur < 4 * 2.5 + 6, f"no tempo do vídeo, sem câmera lenta ({dur:.1f} s para ~4 s de voo)")
    ok(aba.avaliar("document.getElementById('exportar-voo-bt').textContent") == "▶ Prévia do voo", "o botão volta a ▶")

    print("D — parar")
    clicar_no(aba, "#exportar-voo-bt")
    esperar(aba, "window.previaDoVoo && window.previaDoVoo.tocando && window.previaDoVoo.quadros > 1", 30)
    clicar_no(aba, "#exportar-voo-bt")
    ok(esperar(aba, "!document.getElementById('exportar-voo') && !document.getElementById('exportar-previa').hidden && !window.previaDoVoo.tocando", 10),
       "■ Parar: o canvas sai, a imagem parada volta")
    aba.drenar(2.0)
    clicar_no(aba, "#exportar-voo-bt")
    esperar(aba, "window.previaDoVoo && window.previaDoVoo.tocando && window.previaDoVoo.quadros > 1", 30)
    clicar_no(aba, "#exportar-caixa input[name=velocidade][value=lento]")
    ok(esperar(aba, "!document.getElementById('exportar-voo') && !window.previaDoVoo.tocando", 10), "mudar uma opção para a prévia")
    aba.drenar(2.0)
    clicar_no(aba, "#exportar-cancelar")
    ok(esperar(aba, "!document.getElementById('exportar-caixa')", 5), "a janela fecha")

    print("E — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
