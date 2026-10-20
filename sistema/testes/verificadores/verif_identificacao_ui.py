# -*- coding: utf-8 -*-
"""Identificação para modelagem — a locação (Fase 2, 20/10/2026), com o mouse de verdade (CDP), no DXF do Hangar Almayer
(o projeto de fabricação em 36 folhas que, pelo caminho antigo, virou 30 desenhos enfileirados no 3D):
  · Desenho → Identificação para modelagem abre a Montagem com o painel de etapas e varre o Original;
  · a locação é a FOLHA 12 (PLANTA DE LOCAÇÃO), com os eixos A e B (balão) e as 6 linhas das tesouras sem balão,
    numeradas 1–6 pelo programa (com o aviso "confira"); sem níveis escritos, o aviso pede a altura de apoio;
  · "Confirmar a locação" só depois dos eixos gravados; "Conferir e gravar os eixos…" abre o diálogo da Implantação
    com os vãos lidos e grava 6 + 2 eixos no projeto;
  · confirmada a locação, as tesouras se liberam: T1 no eixo 6, T2 nos 3, 4 e 5, T2-A no 2, T3 no 1, cada uma com a
    vista geral (folhas 20, 17, 17, 23);
  · "Ver" leva ao Original com o painel junto; recarregar a página guarda as etapas confirmadas;
  · o Original não é mexido (as mesmas entidades antes e depois)."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

HANGAR = os.path.join(BASE, "..", "Projeto", "OBRAS", "Hangar-Almayer", "Hangar-Allmayer_Projeto de fabricacao_V5.dxf")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_identificacao_")
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))


if not os.path.exists(HANGAR):
    print("  (sem o DXF do Hangar em Projeto/OBRAS/Hangar-Almayer: nada a conferir)")
    sys.exit(0)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_identificacao_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    slug = post("/api/projetos", {"nome": "Hangar identificação", "tipo": "desenho"})["slug"]
    s = urllib.parse.quote(slug)
    post(f"/api/projetos/{s}/arquitetonico", {"arquivo": os.path.basename(HANGAR), "tipo": "dxf", "recebido": True,
                                              "conteudo_b64": base64.b64encode(open(HANGAR, "rb").read()).decode()})
    pasta = os.path.join(DADOS, slug)
    arq_original = [os.path.join(pasta, "desenhos-2d", f) for f in os.listdir(os.path.join(pasta, "desenhos-2d")) if "lan" in f][0]
    ents_antes = json.load(open(arq_original, encoding="utf-8"))["entidades"]

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log", "DOM"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=60.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if aba.avaliar(expr): return True
            aba.drenar(0.3)
        return False

    def clicar_em(expr_elemento):
        r = aba.avaliar(f"(() => {{ const b = {expr_elemento}; if (!b) return null; b.scrollIntoView({{ block: 'center' }}); const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
        if not r: raise RuntimeError("não achei " + expr_elemento)
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1, buttons=1 if tipo == "mousePressed" else 0)
        aba.drenar(0.4)

    def clicar(seletor):
        clicar_em(f"document.querySelector({json.dumps(seletor)})")

    def botao(texto, dentro="#painel-ident"):
        return f"[...document.querySelectorAll('{dentro} button')].find(b => b.textContent.trim().startsWith({json.dumps(texto)}))"

    def painel():
        return aba.avaliar("(document.querySelector('#painel-ident') || {}).textContent || ''") or ""

    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && window.montagem && document.body.dataset.pronto === '1'")
    aba.console.clear()
    clicar('.menu[data-menu="desenho"] > button')
    clicar('[data-acao="identificacao"]')
    ok(esperar("window.cad.nomeDesenho === 'montagem' && !document.querySelector('#painel-ident').hidden", 60), "Identificação para modelagem abre a Montagem com o painel")
    ok(esperar("(document.querySelector('#painel-ident') || {}).textContent.includes('PLANTA DE LOCAÇÃO')", 90), "a varredura achou a planta de locação")
    t = painel()
    ok("Folha 12 — PLANTA DE LOCAÇÃO" in t, f"a locação é a folha 12: «{t[:160]}»")
    ok("1, 2, 3, 4, 5, 6" in t and "A, B" in t and "19,40" in t, "eixos sugeridos: 1–6 e A, B (vão A–B de 19,40 m)")
    ok("não têm balão" in t and "confira" in t, "o aviso diz que os numerados foram nomeados pelo programa")
    ok("informe a altura de apoio" in t, "sem níveis escritos, o aviso pede a altura de apoio")
    ok(aba.avaliar(f"!!({botao('Confirmar a locação')}).disabled"), "Confirmar a locação fica desligado antes de gravar os eixos")
    ok(aba.avaliar("document.querySelector('[data-etapa=tesouras]').classList.contains('bloqueada')"), "as tesouras esperam a locação")

    clicar_em(botao("Conferir e gravar os eixos"))
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Eixos da obra'", 20), "abre o diálogo Eixos da obra")
    vaos = aba.avaliar("[...document.querySelectorAll('#dialogo-corpo input[type=text]')].map(i => i.value)") or []
    ok(vaos and "619" in vaos[0] and "4850" in vaos[0] and "19400" in vaos[2], f"os vãos lidos vêm preenchidos: {vaos}")
    clicar("#dialogo-ok")
    ok(esperar("(document.querySelector('#painel-ident') || {}).textContent.includes('Gravados na Implantação')", 30), "o painel mostra os eixos gravados")
    pj = json.load(open(os.path.join(pasta, "projeto.json"), encoding="utf-8"))
    ex = pj.get("eixos") or {}
    ok(len(ex.get("numeros") or []) == 6 and len(ex.get("letras") or []) == 2, f"o projeto ficou com 6 + 2 eixos: {[e['nome'] for e in ex.get('numeros') or []]} {[e['nome'] for e in ex.get('letras') or []]}")

    clicar_em(botao("Confirmar a locação"))
    ok(esperar("document.querySelector('[data-etapa=locacao]').classList.contains('confirmada') && !document.querySelector('[data-etapa=tesouras]').classList.contains('bloqueada')", 10),
       "confirmada a locação, as tesouras se liberam")
    tes = aba.avaliar("[...document.querySelectorAll('.ident-tesoura')].map(d => d.textContent.replace(/\\s+/g, ' ').trim())") or []
    junto = " | ".join(tes)
    ok("T1 nos eixos 6" in junto and "T2 nos eixos 3, 4, 5" in junto and "T2-A nos eixos 2" in junto and "T3 nos eixos 1" in junto,
       f"as tesouras nos eixos da locação: {junto[:300]}")
    ok("folha 20" in junto and "folha 17" in junto and "folha 23" in junto, "cada uma com a vista geral (folhas 20, 17, 23)")
    ok(aba.avaliar(f"!!({botao('Elevação 3')})"), "a T2 tem o botão da elevação do eixo 3")

    clicar_em("[...document.querySelectorAll('.ident-tesoura')].find(d => d.textContent.includes('T3')).querySelector('.ident-ver')")
    ok(esperar("window.cad.nomeDesenho === 'planta-de-lançamento' && !document.querySelector('#painel-ident').hidden", 30), "Ver leva ao Original com o painel junto")
    clicar("[data-aba=montagem]")
    ok(esperar("window.cad.nomeDesenho === 'montagem' && !document.querySelector('#painel-ident').hidden", 30), "a aba Montagem volta, com o painel")

    aba.drenar(1.5)                                       # a gravação da montagem (400 ms depois da mudança)
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && window.montagem && document.body.dataset.pronto === '1'")
    clicar('.menu[data-menu="desenho"] > button')
    clicar('[data-acao="identificacao"]')
    ok(esperar("document.querySelector('[data-etapa=locacao]') && document.querySelector('[data-etapa=locacao]').classList.contains('confirmada')", 60),
       "recarregada a página, a locação continua confirmada (sem varrer de novo)")

    ents_depois = json.load(open(arq_original, encoding="utf-8"))["entidades"]
    ok(ents_depois == ents_antes, f"o Original não foi mexido ({len(ents_antes)} entidades)")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
