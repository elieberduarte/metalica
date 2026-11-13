# -*- coding: utf-8 -*-
"""O vídeo da montagem por etapas (roteiro de refino, item 4; amostra-18 aprovada em 13/11: "B" — cada etapa cresce de uma
ponta à outra; as 5 etapas, ~2 s cada; a montagem ao longo do voo e, com uma cena só, a câmera dá a volta). Na tela das Cenas,
com o galpão de exemplo:
  A. as etapas pelo papel das peças: pilares, vigas/tesouras, terças/contraventos, fechamentos — nenhuma vazia no galpão;
  B. o momento 3,5: as etapas 1 e 2 inteiras, a 3 até a metade (as de uma ponta: as à vista antes das escondidas no eixo
     comprido), a 4 escondida; o momento 1: só o que já existe;
  C. Exportar › Vídeo MP4 › Montagem por etapas: com uma cena só o botão Gravar libera e o resumo diz a volta, ~9,5 s;
  D. o vídeo (pequeno, pela tela): 9,5 s, a estrutura aparecendo do começo ao fim (as escondidas só diminuem), a câmera
     girando 90° em volta do alvo, e no fim a estrutura inteira de volta;
  E. com duas cenas no rápido (2 s): o voo esticado até caber a montagem (~9,5 s);
  F. a prévia do voo com a montagem e uma cena só; sem erro no console.
Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time, math
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_montagem_video_")
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


# o vídeo pela tela (pequeno: 320 px), anotando a cada quadro quantas peças estão escondidas e a câmera
VIDEO = r"""((ids, porTrecho) => { window.fimVideo = null; window.amostrasVideo = [];
  cenaApi.videoDasCenas({ ids, lado: 320, fps: 30, porTrecho, parada: 0, ss: 1, fecho: 'nenhum', abertura: 'nenhuma', montagem: true,
    aoAndar: async (f, n) => { const c = visor.lerCamera(); window.amostrasVideo.push([f, visor.ocultas.size, c.posicao, c.alvo]); } })
  .then(r => window.fimVideo = { segundos: r.segundos, quadros: r.quadros, bytes: r.mp4.size }, e => window.fimVideo = { erro: e.message }); return 1; })"""

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_montagem_video_")
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
    aba = Aba(alvos[0]["webSocketDebuggerUrl"]); aba.ws.settimeout(600)
    for d in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    aba.avaliar("window.ids = null; cenaApi.gerarCenas(['aereas']).then(r => window.ids = r.ids); 1")
    esperar(aba, "!!window.ids", 60)
    ids = aba.avaliar("window.ids")
    # a tela de novo, já na Aérea sudeste (gerarCenas direto não recarrega a lista dos cartões; a janela recarrega)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro&cena={ids[1]}", limite=90)
    ok(esperar(aba, f"!!window.cenaPronta && cenaApi.estado().cena && cenaApi.estado().cena.id === '{ids[1]}'", 180), "a Aérea sudeste aberta")
    aba.drenar(1)

    print("A — as etapas")
    conta = aba.avaliar("cenaApi.etapasDaMontagem().conta")
    ok(conta and all(n > 0 for n in conta[1:5]), f"pilares, vigas/tesouras, terças/contraventos, fechamentos: nenhuma vazia ({conta})")

    print("B — os momentos")
    r = aba.avaliar("""(() => { const E = cenaApi.etapasDaMontagem(), F = visor.fichas; cenaApi.mostrarMontagem(3.5, new Set());
      const oc = visor.ocultas, vis = (e) => E.ordem[e].filter(i => !oc.has(i)).length;
      const eixo = (() => { const cx = visor.caixaVisivel(); return (cx.max.x - cx.min.x) >= (cx.max.y - cx.min.y) ? 0 : 1; })();
      const p = (i) => F[i].x[eixo], v3 = E.ordem[3].filter(i => !oc.has(i)).map(p), h3 = E.ordem[3].filter(i => oc.has(i)).map(p);
      const r = { e1: vis(1) === E.conta[1], e2: vis(2) === E.conta[2], e3: vis(3), n3: E.conta[3], e4: vis(4),
                  ponta: !v3.length || !h3.length || Math.max(...v3) <= Math.min(...h3) };
      cenaApi.mostrarMontagem(1, new Set()); r.inicio = visor.ocultas.size === E.conta[1] + E.conta[2] + E.conta[3] + E.conta[4];
      visor.ocultas = new Set(); visor._repintar(); return r; })()""")
    ok(r["e1"] and r["e2"] and abs(r["e3"] - r["n3"] / 2) <= 1 and r["e4"] == 0, f"3,5: etapas 1 e 2 inteiras, a 3 na metade, a 4 escondida ({r})")
    ok(r["ponta"], "a etapa cresce de uma ponta à outra (as à vista antes das escondidas no eixo comprido)")
    ok(r["inicio"], "o momento 1: só o que já existe")

    print("C — a caixinha no Exportar")
    clicar_no(aba, "#exportar"); esperar(aba, "!!document.getElementById('exportar-caixa')", 5)
    clicar_no(aba, "#exportar-caixa input[name=formato][value=mp4]")
    clicar_no(aba, "#exportar-caixa input[name=quais][value=esta]")
    clicar_no(aba, "#exportar-caixa input[name=fecho][value=nenhum]")
    clicar_no(aba, "#exportar-caixa input[name=abertura][value=nenhuma]")
    if aba.avaliar("document.getElementById('exportar-montagem').checked"): clicar_no(aba, "#exportar-montagem")
    ok(aba.avaliar("document.getElementById('exportar-ir').disabled"), "sem a montagem, uma cena só não grava")
    clicar_no(aba, "#exportar-montagem")
    info = aba.avaliar("document.getElementById('exportar-info').textContent")
    ok(not aba.avaliar("document.getElementById('exportar-ir').disabled") and "a câmera dando a volta" in info and "~10 s" in info,
       f"com a montagem, uma cena basta; o resumo diz a volta e ~9,5 s ({info})")
    ok(aba.avaliar("!document.getElementById('exportar-voo-linha').hidden"), "a prévia do voo também aparece")

    print("F — a prévia com a montagem")
    clicar_no(aba, "#exportar-voo-bt")
    ok(esperar(aba, "window.previaDoVoo && window.previaDoVoo.quadros > 5", 60), "a prévia anda com uma cena só")
    clicar_no(aba, "#exportar-voo-bt")
    esperar(aba, "!window.previaDoVoo.tocando", 10); aba.drenar(3)
    clicar_no(aba, "#exportar-cancelar"); esperar(aba, "!document.getElementById('exportar-caixa')", 5)
    ok(esperar(aba, "visor.ocultas.size === 0", 20), "parada a prévia, a estrutura inteira de volta")

    print("D — o vídeo com uma cena (a volta)")
    aba.avaliar(f"{VIDEO}({json.dumps([ids[1]])}, 3)")
    ok(esperar(aba, "!!window.fimVideo", 400), "o vídeo termina")
    fim = aba.avaliar("window.fimVideo") or {}
    ok(not fim.get("erro") and abs(fim.get("segundos", 0) - 9.5) < 0.1 and fim.get("bytes", 0) > 1000, f"9,5 s de MP4 ({fim})")
    am = aba.avaliar("window.amostrasVideo") or []
    ocult = [a[1] for a in am]
    ok(len(am) > 200 and ocult[0] > 0 and ocult[-1] == 0 and all(b <= a for a, b in zip(ocult, ocult[1:])),
       f"a estrutura aparecendo: {ocult[0]} escondidas no começo, {ocult[-1]} no fim, só diminuindo")
    if am:
        (p0, a0), (p1, a1) = (am[0][2], am[0][3]), (am[-1][2], am[-1][3])
        g0 = math.degrees(math.atan2(p0[1] - a0[1], p0[0] - a0[0])); g1 = math.degrees(math.atan2(p1[1] - a1[1], p1[0] - a1[0]))
        giro = (g1 - g0 + 540) % 360 - 180
        ok(abs(abs(giro) - 90) < 2 and abs(p0[2] - p1[2]) < 1, f"a câmera girou 90° em volta do alvo ({giro:.1f}°), na mesma altura")
    ok(esperar(aba, "visor.ocultas.size === 0", 20), "no fim, a estrutura inteira de volta")

    print("E — duas cenas no rápido: o voo esticado")
    aba.avaliar(f"{VIDEO}({json.dumps(ids[:2])}, 2)")
    ok(esperar(aba, "!!window.fimVideo", 400), "o vídeo termina")
    fim = aba.avaliar("window.fimVideo") or {}
    ok(not fim.get("erro") and abs(fim.get("segundos", 0) - 9.5) < 0.2, f"~9,5 s em vez de 2 s ({fim})")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
