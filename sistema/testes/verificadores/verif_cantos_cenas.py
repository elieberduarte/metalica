# -*- coding: utf-8 -*-
"""A sombra suave nos cantos do render das Cenas (roteiro de refino, item 2; amostra-15 aprovada em 12/11: "médio" como
padrão, ligada no Renderizar e no Exportar refinado, desligada no vídeo e no Salvar imagem; um seletor no Estilo). Na tela
das Cenas, com o galpão de exemplo e cliques de verdade:
  A. a cena nova: o seletor Sombra nos cantos em "média" e o resumo do Estilo dizendo "cantos médios";
  B. o render com os cantos × sem: mais escuro onde a parede encontra o chão (o pé do galpão), o céu igual;
  C. sem emenda: a imagem de 1600 px em blocos de 1024 (ss 2) — a diferença dos cantos na coluna da emenda segue as vizinhas;
  D. "sem" no seletor: o servidor guarda; o render com os cantos fica igual ao sem;
  E. "forte" mais escuro que "média"; a prévia do Exportar com Rápida = sem os cantos, com Refinada = com eles;
  F. sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_cantos_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, base64, io
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image, ImageChops, ImageStat
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cantos_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_cantos_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-12T00:00:00", "alterado": "2026-11-12T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
API = f"{base}/api/projetos/obra/terreno/cenas"
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
    r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(sel)}); const sec = b && b.closest('details'); if (sec && !sec.open && b.tagName !== 'SUMMARY') sec.open = true; if (!b || !b.offsetWidth) return null;"
                    f" b.scrollIntoView({{block: 'nearest'}}); const q = b.getBoundingClientRect(); return [q.x + q.width / 2, q.y + q.height / 2]; }})()")
    if not r: return False
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    for tipo in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button=botao, clickCount=1)
    aba.drenar(0.2)
    return True


def servidor():
    return {c["id"]: c for c in json.loads(urllib.request.urlopen(API, timeout=30).read())["cenas"]}


def render(aba, nome, cantos, w=1600, h=900, ss=2):
    aba.avaliar(f"window.img = null; cenaApi.imagemDaCena3d({w}, {h}, {ss}, null, false, null, {{ cantos: {str(cantos).lower()} }})"
                ".then(c => window.img = c.toDataURL('image/png'), e => window.img = 'erro ' + e.message); 1")
    esperar(aba, "!!window.img", 600)
    url = aba.avaliar("window.img")
    if not url or url.startswith("erro"):
        ok(False, f"o render {nome} ({url})"); return None
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
    im.save(os.path.join(SAIDA, nome + ".png"))
    return im


def escurece(sem, com, caixa=None):
    """Quanto o `com` é mais escuro que o `sem` (média de sem − com, em 0–255) na caixa."""
    a, b = (sem.crop(caixa), com.crop(caixa)) if caixa else (sem, com)
    return ImageStat.Stat(ImageChops.subtract(a.convert("L"), b.convert("L"))).mean[0]


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cantos_cenas_")
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"{base}/visor3d/cena.html?projeto=obra&tema=claro", limite=90)
    ok(esperar(aba, "!!window.cenaPronta", 180), "a tela das Cenas abriu")
    aba.avaliar("cenaApi.novaCena3d('Iso'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'iso'", 30), "a cena do 3D")
    aba.drenar(1.0)

    print("A — o seletor no Estilo")
    clicar_no(aba, "#sec-estilo > summary"); aba.drenar(0.3)
    ok(aba.avaliar("document.querySelector('#cantos3d button.ligado') && document.querySelector('#cantos3d button.ligado').dataset.v") == "medio",
       "Sombra nos cantos começa em \"média\" (o padrão aprovado)")
    ok("cantos médios" in aba.avaliar("document.getElementById('res-estilo').textContent"), "o resumo do Estilo diz \"cantos médios\"")

    print("B — com × sem")
    sem = render(aba, "sem", False)
    com = render(aba, "media", True)
    if sem and com:
        W, H = sem.size
        topo = escurece(sem, com, (0, 0, W, 12))
        ok(topo < 0.5, f"o céu igual ({topo:.2f})")
        geral = escurece(sem, com)
        ok(geral > 0.3, f"a imagem com os cantos é mais escura ({geral:.2f})")
        # onde mais escurece: a faixa mais escura de 80 px de altura deve estar no pé do galpão (metade de baixo)
        faixas = [(y, escurece(sem, com, (0, y, W, y + 80))) for y in range(0, H - 80, 40)]
        y_max, v_max = max(faixas, key=lambda t: t[1])
        ok(v_max > 1.0 and y_max > H * 0.3, f"o maior escurecimento perto do pé/chão (faixa y={y_max}, {v_max:.2f})")

        print("C — sem emenda entre os blocos (1600 px em blocos de 1024 com ss 2)")
        d = ImageChops.subtract(sem.convert("L"), com.convert("L"))
        col = lambda x: ImageStat.Stat(d.crop((x, 0, x + 1, H))).mean[0]
        salto = abs(col(1023) - col(1024))
        vizinhos = max(abs(col(x) - col(x + 1)) for x in (1010, 1015, 1030, 1035))
        ok(salto <= vizinhos * 2 + 0.6, f"a coluna da emenda segue as vizinhas (salto {salto:.2f}, vizinhas até {vizinhos:.2f})")

    print("D — \"sem\" no seletor")
    clicar_no(aba, "#cantos3d [data-v=sem]")
    t0 = time.time()
    while time.time() - t0 < 10 and servidor()["iso"].get("cantos") != "sem": aba.drenar(0.3)
    ok(servidor()["iso"].get("cantos") == "sem", "o servidor guarda \"sem\"")
    ok("sem sombra nos cantos" in aba.avaliar("document.getElementById('res-estilo').textContent"), "o resumo acompanha")
    desligada = render(aba, "desligada", True)
    if sem and desligada:
        ok(escurece(sem, desligada) < 0.05, f"com \"sem\" o render sai como sem os cantos ({escurece(sem, desligada):.3f})")

    print("E — forte e a prévia do Exportar")
    clicar_no(aba, "#cantos3d [data-v=forte]")
    aba.drenar(0.8)
    forte = render(aba, "forte", True)
    if sem and com and forte:
        ok(escurece(sem, forte) > escurece(sem, com) * 1.2, f"forte mais escuro que média ({escurece(sem, forte):.2f} × {escurece(sem, com):.2f})")
    # a prévia do Exportar: com os cantos só na Refinada (window.cantosUsados conta os blocos que saíram com eles)
    clicar_no(aba, "#exportar")
    ok(esperar(aba, "!!document.getElementById('exportar-caixa')", 5), "a janela Exportar abre")
    clicar_no(aba, "#exportar-caixa input[name=formato][value=jpg]")
    for q, espera in (("rapida", False), ("refinada", True)):
        clicar_no(aba, f"#exportar-caixa input[name=qualidade][value={q}]")
        aba.drenar(1.5)                                     # a prévia agendada pelo clique termina
        aba.avaliar("window.cantosUsados = 0; document.getElementById('exportar-previa').style.backgroundImage = '';"
                    " document.querySelector('#exportar-caixa input[name=formato][value=png]').click();"
                    " document.querySelector('#exportar-caixa input[name=formato][value=jpg]').click(); 1")
        refeita = esperar(aba, "!!document.getElementById('exportar-previa').style.backgroundImage", 60)
        n = aba.avaliar("window.cantosUsados")
        ok(refeita and (n > 0) == espera, f"a prévia na {q}: {'com' if espera else 'sem'} os cantos ({n} blocos com eles)")
    clicar_no(aba, "#exportar-cancelar")
    esperar(aba, "!document.getElementById('exportar-caixa')", 5)
    aba.avaliar("window.cantosUsados = 0; window.ultimaImagemCena = null; 1")
    clicar_no(aba, "#salvar-imagem")
    ok(esperar(aba, "!!window.ultimaImagemCena", 120) and aba.avaliar("window.cantosUsados") == 0,
       "o Salvar imagem (como na tela) sai sem os cantos")

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
