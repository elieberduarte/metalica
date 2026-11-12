# -*- coding: utf-8 -*-
"""Os ambientes da cena do 3D (usuário, 11/11: "criar antes algumas opções de fundos diferentes, criar umas cenas noturnas";
amostra-6 aprovada — os 6 ambientes, as luzes de noite automáticas + ajuste). Na tela das Cenas, com cliques de verdade:
  A. Noite: a luz do 3D muda (o sol fraco, as luzes acesas), o painel Luzes da noite aparece, o céu escuro atrás do 3D; o
     render: o céu escuro em cima e a luz quente no prédio; o servidor guarda o fundo;
  B. as luzes: desligar refletores e luz interna apaga todas; Ctrl+Z (↶) volta; a força e a cor gravadas na cena;
  C. Entardecer: o sol desce para 9° (sombra comprida) e fica quente;
  D. Dia: a luz de sempre de volta (a conta de antes), sem o painel das luzes; o sol sobe de novo;
  E. Estúdio: o render com o fundo cinza claro nos cantos;
  F. a cena da foto depois de uma noite: a luz de sempre, sem o céu do ambiente;
  G. sem erro no console.
Porta livre, nunca a 8765/8766. Capturas na pasta temporária metalica_saida_ambientes_cenas."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request, base64, io
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from PIL import Image, ImageStat
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_ambientes_cenas_")
SAIDA = os.path.join(tempfile.gettempdir(), "metalica_saida_ambientes_cenas")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "Obra Teste", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-11-11T00:00:00", "alterado": "2026-11-11T00:00:00", "dados": None},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "galpão.modelo.json"), os.path.join(DADOS, "obra", "modelo.json"))
FOTO_DIR = os.path.join(DADOS, "obra", "cenas", "dados", "quadra")
os.makedirs(FOTO_DIR)
Image.new("RGB", (120, 90), (120, 110, 95)).save(os.path.join(FOTO_DIR, "foto.jpg"), "JPEG")
json.dump({"id": "quadra", "nome": "Quadra", "foto": "foto.jpg", "px": [120, 90], "pares": [], "camera": None, "opacidade": 1.0,
           "criada": "2026-11-01T08:00:00", "alterada": "2026-11-01T08:00:00"},
          open(os.path.join(FOTO_DIR, "cena.json"), "w", encoding="utf-8"))
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


def luz(aba):
    return aba.avaliar("(() => { const L = visor._luz; return { n: L.uNLuz.value, solK: L.uSolK.value, ambK: L.uAmbK.value,"
                       " solCor: [L.uSolCor.value.x, L.uSolCor.value.y, L.uSolCor.value.z], aresta: L.uArestaK.value }; })()")


def render(aba, nome):
    url = aba.avaliar("cenaApi.imagemDaCena3d(960, 540, 1, null, false).then(c => c.toDataURL('image/png'))")
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
    im.save(os.path.join(SAIDA, nome))
    return im


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_ambientes_cenas_")
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
    aba.avaliar("cenaApi.novaCena3d('Fachada'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada'", 30), "a cena do 3D")
    clicar_no(aba, "#barra-palco [data-vista=frente]")
    clicar_no(aba, "#atualizar-vista")
    aba.drenar(1.0)
    l0 = luz(aba)
    ok(l0 == {"n": 0, "solK": 0.66, "ambK": 0.7, "solCor": [1.0, 0.97, 0.92], "aresta": 1}, f"o Dia: a luz de sempre ({l0})")
    ok(aba.avaliar("!!document.querySelector('#ambiente3d [data-v=ceu].ligado') && !document.getElementById('ceu').hidden"), "Dia marcado, o céu atrás do 3D")

    print("P — o painel em seções (12/11, amostra-7: \"1 · Seções que abrem\")")
    ok(aba.avaliar("document.querySelectorAll('#corpo3d details.secao').length === 4 && !!document.querySelector('details#marca-bloco')"),
       "as seções Quadro, O que aparece, Ambiente e luz, Estilo e Marca d'água")
    clicar_no(aba, "#sec-quadro > summary"); aba.drenar(0.3)
    clicar_no(aba, "#sec-estilo > summary"); aba.drenar(0.3)
    abertas = aba.avaliar("[...document.querySelectorAll('details.secao[open]')].map(d => d.id)")
    ok(abertas == ["sec-estilo"], f"uma aberta por vez ({abertas})")
    res = aba.avaliar("({q: document.getElementById('res-quadro').textContent, a: document.getElementById('res-ambiente').textContent, e: document.getElementById('res-estilo').textContent})")
    ok(res["q"].startswith("16:9 · lente") and res["a"].startswith("Dia · sol") and "arestas finas" in res["e"], f"o resumo na barra de cada uma ({res})")
    ok(clicar_no(aba, "#mais-cena") and aba.avaliar("!document.getElementById('menu-mais').hidden && !!document.getElementById('copiar-3d') && !!document.getElementById('apagar-3d')"),
       "⋯ ao lado do nome: Copiar ajustes e Apagar")
    clicar_no(aba, "#mais-cena")

    print("A — a Noite")
    clicar_no(aba, "#ambiente3d [data-v=noite]")
    aba.drenar(1.0)
    l = luz(aba)
    ok(l["n"] > 4 and l["solK"] < 0.1 and l["aresta"] < 0.5, f"a luz da noite: o sol fraco e as luzes acesas ({l})")
    ok(aba.avaliar("!document.getElementById('luzes3d').hidden"), "o painel Luzes da noite aparece")
    ok(aba.avaliar("document.getElementById('res-ambiente').textContent") == "Noite · luzes acesas", "o resumo: Noite · luzes acesas")
    topo = aba.avaliar("Array.from(document.getElementById('ceu').getContext('2d').getImageData(200, 3, 1, 1).data)")
    ok(topo and max(topo[:3]) < 30, f"o céu escuro atrás do 3D na tela ({topo})")
    aba.drenar(0.8)
    ok(servidor()["fachada"].get("fundo") == "noite", "o servidor guarda o ambiente")
    im = render(aba, "noite.png")
    rgb = im.convert("RGB"); W, H = rgb.size
    ok(max(rgb.getpixel((W // 2, 3))) < 30, f"o render: o céu escuro em cima ({rgb.getpixel((W // 2, 3))})")
    quentes = sum(1 for x in range(0, W, 6) for y in range(H // 3, H, 6)
                  if (lambda p: p[0] > 120 and p[0] > p[2] + 35)(rgb.getpixel((x, y))))
    ok(quentes > 30, f"o render: a luz quente no prédio ({quentes} pontos)")

    print("B — as luzes")
    clicar_no(aba, "#luz-ref"); clicar_no(aba, "#luz-int")
    aba.drenar(0.8)
    ok(luz(aba)["n"] == 0, "sem refletores e sem a luz interna: tudo apagado")
    clicar_no(aba, "#btn-desfazer")
    aba.drenar(0.8)
    ok(luz(aba)["n"] > 0 and aba.avaliar("document.getElementById('luz-int').checked"), "↶ volta a luz interna")
    clicar_no(aba, "#btn-desfazer")
    aba.drenar(0.8)
    ok(aba.avaliar("document.getElementById('luz-ref').checked && document.getElementById('luz-int').checked"), "e os refletores")
    n_tudo = luz(aba)["n"]
    clicar_no(aba, "#luz-cor [data-v=branca]")
    ok(aba.avaliar("(() => { const r = document.getElementById('luz-ref-forca'); r.value = '2.5'; r.dispatchEvent(new Event('input')); return r.value; })()") == "2.5", "a força dos refletores no controle")
    t0 = time.time()
    while time.time() - t0 < 10 and (servidor()["fachada"].get("luzes") or {}).get("forca_ref") != 2.5: aba.drenar(0.3)
    lz = servidor()["fachada"].get("luzes") or {}
    ok(lz.get("cor") == "branca" and lz.get("forca_ref") == 2.5 and lz.get("refletores") and lz.get("interna"), f"a força e a cor gravadas ({lz})")
    ok(luz(aba)["n"] == n_tudo, "o mesmo número de luzes")

    print("C — o Entardecer")
    clicar_no(aba, "#ambiente3d [data-v=entardecer]")
    aba.drenar(1.0)
    l = luz(aba)
    ok(l["n"] == 0 and abs(l["solCor"][1] - 0.68) < 0.01, f"o sol quente, sem luzes ({l})")
    ok((servidor()["fachada"].get("sol") or {}).get("altura") == 9, f"o sol desce para 9° ({servidor()['fachada'].get('sol')})")
    ok(aba.avaliar("document.getElementById('luzes3d').hidden"), "sem o painel das luzes")
    render(aba, "entardecer.png")

    print("D — o Dia de volta")
    clicar_no(aba, "#ambiente3d [data-v=ceu]")
    aba.drenar(1.0)
    ok(luz(aba) == l0, f"a luz de sempre ({luz(aba)})")
    ok((servidor()["fachada"].get("sol") or {}).get("altura", 0) > 30, "o sol sobe de novo")

    print("E — o Estúdio")
    clicar_no(aba, "#ambiente3d [data-v=estudio]")
    aba.drenar(1.0)
    im = render(aba, "estudio.png").convert("RGB")
    c = im.getpixel((3, 3))
    ok(min(c) > 200 and max(c) - min(c) < 20, f"o fundo cinza claro nos cantos ({c})")
    clicar_no(aba, "#fundo3d [data-v=branco]")
    aba.drenar(0.8)
    ok(aba.avaliar("document.getElementById('ceu').hidden") and luz(aba) == l0, "o fundo liso branco: sem o céu, a luz de sempre")

    print("F — a cena da foto depois da noite")
    clicar_no(aba, "#ambiente3d [data-v=noite]")
    aba.drenar(0.8)
    clicar_no(aba, ".cartao-cena[data-cena=quadra]")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'quadra'", 30),
       f"a cena da foto abre ({aba.avaliar('document.getElementById(\"aviso\").textContent')}; {[c for c in aba.console if c[0] in ('excecao', 'error')][:3]})")
    ok(luz(aba) == l0 and aba.avaliar("document.getElementById('ceu').hidden"), f"a luz de sempre e sem o céu da noite ({luz(aba)})")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'fachada'", 30) and luz(aba)["n"] > 0, "e a do 3D volta de noite")
    d = aba.cmd("Page.captureScreenshot", format="png")["data"]
    open(os.path.join(SAIDA, "tela-noite.png"), "wb").write(base64.b64decode(d))

    print("H — copiar os ajustes para outras cenas (11/11: \"ter a opção de copiar de uma cena para (sol, terreno...)\")")
    aba.avaliar("cenaApi.novaCena3d('Lateral'); 1")
    ok(esperar(aba, "cenaApi.estado().cena && cenaApi.estado().cena.id === 'lateral'", 30), "outra cena do 3D (Lateral, de dia)")
    clicar_no(aba, "#ambiente3d [data-v=ceu]")
    aba.drenar(1.0)
    ok(luz(aba)["n"] == 0, "a Lateral de dia")
    sol_fachada = servidor()["fachada"].get("sol")
    clicar_no(aba, ".cartao-cena[data-cena=fachada]", "right")
    ok(clicar_no(aba, "#menu-cartao [data-acao='Copiar ajustes para outras cenas…']") and esperar(aba, "!!document.getElementById('caixa-copiar')", 5),
       "no cartão da Fachada: Copiar ajustes… abre a janela")
    marcados = aba.avaliar("[...document.querySelectorAll('#copiar-grupos input:checked')].map(i => i.value)")
    ok(marcados == ["sol", "ambiente"], f"vêm marcados o sol e o ambiente ({marcados})")
    clicar_no(aba, "#copiar-cenas input[value=quadra]")
    ok(aba.avaliar("!document.querySelector('#caixa-copiar input[value=\"*todas\"]').checked"), "desmarcar uma cena tira o Todas")
    clicar_no(aba, "#caixa-copiar [data-r=ok]")
    ok(esperar(aba, "JSON.stringify(window.ultimaCopiaCenas) === '[\"lateral\"]'", 10), "copiado só para a Lateral")
    sv = servidor()
    ok(sv["lateral"].get("fundo") == "noite" and (sv["lateral"].get("luzes") or {}).get("cor") == "branca"
       and sv["lateral"].get("sol") == sol_fachada, f"a Lateral com a noite, as luzes e o sol da Fachada ({sv['lateral'].get('fundo')}, {sv['lateral'].get('luzes')})")
    ok(sv["quadra"].get("sol") != sol_fachada or sol_fachada is None, "a Quadra (desmarcada) não mudou")
    ok(aba.avaliar("/copiados para 1 cena/.test(document.getElementById('aviso').textContent)"), "o aviso diz para quantas")
    # a Lateral estava aberta na tela (a cópia saiu do cartão da Fachada): a tela passa a mostrá-la de noite na hora
    ok(esperar(aba, "cenaApi.estado().cena.id === 'lateral' && visor._luz.uNLuz.value > 0 && !!document.querySelector('#ambiente3d [data-v=noite].ligado')", 10),
       "a Lateral, aberta na tela, já aparece de noite")
    t0 = time.time()
    while time.time() - t0 < 20 and (servidor()["lateral"].get("miniatura") or "") < (servidor()["lateral"].get("alterada") or ""): aba.drenar(0.5)
    ok((servidor()["lateral"].get("miniatura") or "") >= (servidor()["lateral"].get("alterada") or "x"), "a miniatura dela refeita (a de dia era velha)")

    print("G — o console")
    erros = [c for c in aba.console if c[0] in ("excecao", "error") and "Failed to load resource" not in c[1]]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print(f"\ncapturas em {SAIDA}")
print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
