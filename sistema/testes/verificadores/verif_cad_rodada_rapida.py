# -*- coding: utf-8 -*-
"""A rodada rápida do CAD 2D (usuário, 23/10: "pode começar", depois do levantamento das ferramentas que faltam), com o
teclado e o mouse de verdade (CDP):
  A. Chanfro (C H): entre duas linhas, 20 × 30 — fica o lado clicado e entra a linha do chanfro; numa polilinha com P,
     todos os cantos;
  B. Quebrar (Q B): o trecho entre dois pontos sai da linha; o círculo vira arco; a polilinha fechada, com Enter, abre;
  C. Alongar (A L): "500" alonga a ponta clicada; "t300" deixa com 300 de comprimento total;
  D. Zoom janela (Z W) e zoom anterior (Z P);
  E. o cadeado da camada: travada não seleciona; "Destravar todas";
  F. a área, o perímetro e o peso da chapa selecionada, sem o furo dentro dela;
  G. Ctrl+C num desenho e Ctrl+V no outro (a área de transferência do programa): presa ao cursor pelo ponto de base, o
     texto no tamanho de origem (1:10 → 1:20); o Ctrl+C fora da Original não abre a cópia da tesoura da Montagem.
A área de transferência do Windows não é escrita: o servidor só lê o número dela (GetClipboardSequenceNumber)."""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Texto, Camada2D

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_rapida_")
PASTA = os.path.join(DADOS, "obra-rapida")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Obra rápida", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-23T00:00:00", "alterado": "2026-10-23T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
a = Desenho(nome="Desenho A", escala=10.0)
a.camadas["ARQ"] = Camada2D(nome="ARQ", cor="#888888")
a.add(Linha(id="h", a=(0, 0), b=(1000, 0))); a.add(Linha(id="v", a=(0, 0), b=(0, 600)))
a.add(Polilinha(id="ret", vertices=[(2000, 0), (2400, 0), (2400, 300), (2000, 300)], fechada=True))
a.add(Linha(id="q", a=(0, 1000), b=(1000, 1000)))
a.add(Circulo(id="ci", centro=(2200, 1000), raio=100))
a.add(Polilinha(id="pf", vertices=[(3000, 1000), (3400, 1000), (3400, 1300), (3000, 1300)], fechada=True))
a.add(Linha(id="al", a=(0, 2000), b=(1000, 2000)))
a.add(Linha(id="arq", a=(0, 2500), b=(1000, 2500), camada="ARQ"))
a.add(Polilinha(id="chapa", vertices=[(2000, 2000), (3000, 2000), (3000, 2500), (2000, 2500)], fechada=True))
a.add(Circulo(id="furo", centro=(2500, 2250), raio=50))
a.add(Texto(id="tx", posicao=(4000, 0), texto="CH1", altura=2.5))
a.add(Linha(id="lx", a=(4000, -100), b=(4500, -100)))
b = Desenho(nome="Desenho B", escala=20.0)
b.add(Linha(id="ref", a=(0, 0), b=(100, 0)))
for d, n in ((a, "desenho-a"), (b, "desenho-b")):
    json.dump(d.dict(), open(os.path.join(PASTA, "desenhos-2d", n + ".desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_rapida_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ const c = window.cad; {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.3)
        return False

    def tela(p):
        return js("const r = c.el.canvas.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def ev(tipo, x, y, botao="none", botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=1)

    def clique(p):
        x, y = tela(p)
        ev("mouseMoved", x, y); ev("mousePressed", x, y, "left", 1); ev("mouseReleased", x, y, "left", 0)
        aba.drenar(0.25)

    def clicar_el(seletor):
        r = js(f"const e = {seletor}; if (!e) return null; e.scrollIntoView({{block: 'nearest'}}); const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        ev("mouseMoved", *r); ev("mousePressed", *r, "left", 1); ev("mouseReleased", *r, "left", 0)
        aba.drenar(0.3)
        return True

    COD = {"Enter": (13, "Enter"), "Escape": (27, "Escape")}

    def tecla(k, mods=0):
        code, nome = COD.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() and len(k) == 1 else ("Digit" + k if k.isdigit() else k)))
        texto = k if len(k) == 1 and not (mods & 2) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.12)

    def duas(k1, k2):
        """o atalho de duas letras digitado rápido (a segunda desce antes de a primeira subir)"""
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        aba.drenar(0.2)

    def digitar(t):
        for ch in t: tecla(ch)
        tecla("Enter"); aba.drenar(0.2)

    def esc():
        tecla("Escape"); tecla("Escape")

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    ent = lambda i: js(f"const e = c.doc.get('{i}'); return e ? JSON.parse(JSON.stringify(e)) : null;")
    perto = lambda p, q, tol=0.5: p is not None and math.dist(p, q) < tol
    novas = lambda antes: [js(f"return c.doc.get('{i}');") for i in set(js("return [...c.doc.entidades.keys()];")) - antes]
    ids = lambda: set(js("return [...c.doc.entidades.keys()];"))

    def vista(caixa):
        esc(); js("c.ativarFerramenta('selecionar'); c.selecionar([]); c.tela.enquadrar(%s, 0.05); return 1;" % json.dumps(caixa)); aba.drenar(0.3)

    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-rapida&desenho=desenho-a", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 12", 40), "o CAD abriu o desenho A")
    aba.console.clear()

    # ------------------------------------------------------------------ A. chanfro
    vista([[-200, -200], [2600, 700]])
    duas("c", "h")
    ok(ferr() == "chanfro", f"A. C H abre o Chanfro ({ferr()})")
    digitar("20;30")
    antes = ids()
    clique([500, 0]); clique([0, 300])
    h, v, nv = ent("h"), ent("v"), [e for e in novas(antes) if e and e["tipo"] == "linha"]
    ok(perto(h["a"], [20, 0]) or perto(h["b"], [20, 0]), f"A. a primeira linha recua 20 do canto ({h['a']} → {h['b']})")
    ok(perto(v["a"], [0, 30]) or perto(v["b"], [0, 30]), f"A. a segunda recua 30 ({v['a']} → {v['b']})")
    ok(len(nv) == 1 and {tuple(map(round, nv[0]["a"])), tuple(map(round, nv[0]["b"]))} == {(20, 0), (0, 30)}, f"A. a linha do chanfro de (20, 0) a (0, 30): {nv and (nv[0]['a'], nv[0]['b'])}")
    tecla("p"); digitar("10")
    clique([2200, 0])
    r = ent("ret")
    ok(len(r["vertices"]) == 8 and all(not perto(p, q) for p in r["vertices"] for q in [[2000, 0], [2400, 0], [2400, 300], [2000, 300]]),
       f"A. P: os 4 cantos da polilinha chanfrados ({len(r['vertices'])} vértices)")
    tecla("p")
    esc()

    # ------------------------------------------------------------------ B. quebrar
    vista([[-200, 700], [3600, 1400]])
    duas("q", "b")
    ok(ferr() == "quebrar", f"B. Q B abre o Quebrar ({ferr()})")
    antes = ids()
    clique([300, 1000]); clique([600, 1000])
    partes = sorted((e for e in novas(antes) if e and e["tipo"] == "linha"), key=lambda e: e["a"][0])
    ok(ent("q") is None and len(partes) == 2 and perto(partes[0]["b"], [300, 1000], 3) and perto(partes[1]["a"], [600, 1000], 3),
       f"B. a linha sem o trecho de 300 a 600: {[(p['a'], p['b']) for p in partes]}")
    antes = ids()
    clique([2300, 1000]); clique([2200, 1100])
    arcos = [e for e in novas(antes) if e and e["tipo"] == "arco"]
    ok(ent("ci") is None and len(arcos) == 1 and abs(((arcos[0]["fim"] - arcos[0]["inicio"]) % 360) - 270) < 2,
       f"B. o círculo vira o arco de 270° (sai o quarto de 0° a 90°): {arcos and (round(arcos[0]['inicio']), round(arcos[0]['fim']))}")
    antes = ids()
    clique([3200, 1000]); tecla("Enter")
    abertas = [e for e in novas(antes) if e and e["tipo"] == "polilinha"]
    ok(ent("pf") is None and len(abertas) == 1 and not abertas[0]["fechada"] and len(abertas[0]["vertices"]) == 6,
       f"B. a polilinha fechada quebrada num ponto vira uma aberta que começa e termina ali ({abertas and len(abertas[0]['vertices'])} vértices)")
    esc()

    # ------------------------------------------------------------------ C. alongar
    vista([[-200, 1800], [1700, 2200]])
    duas("a", "l")
    ok(ferr() == "alongar", f"C. A L abre o Alongar ({ferr()})")
    digitar("500")
    clique([950, 2000])
    ok(perto(ent("al")["b"], [1500, 2000]), f"C. +500 na ponta clicada: {ent('al')['b']}")
    tecla("t"); digitar("300")                            # T: o comprimento total (o "t" não abre o Texto)
    clique([1450, 2000])
    al = ent("al")
    ok(abs(math.dist(al["a"], al["b"]) - 300) < 0.01 and perto(al["a"], [0, 2000]), f"C. total 300 a partir da outra ponta: {al['a']} → {al['b']}")
    esc()

    # ------------------------------------------------------------------ D. zoom janela e anterior
    vista([[-200, -200], [5000, 3000]])
    z0 = js("return c.tela.vp.z;")
    duas("z", "w")
    ok(ferr() == "zoom_janela", f"D. Z W abre o Zoom janela ({ferr()})")
    clique([2000, 2000]); clique([2600, 2500])
    z1 = js("return c.tela.vp.z;")
    vis = js("const a = c.tela.paraMundo([0, c.tela.altura]), b = c.tela.paraMundo([c.tela.largura, 0]); return [a, b];")
    ok(z1 > 4 * z0 and vis[0][0] <= 2000.5 and vis[1][0] >= 2599.5 and vis[0][1] <= 2000.5 and vis[1][1] >= 2499.5 and ferr() == "selecionar",
       f"D. a janela ocupa a tela (z {z0:.3f} → {z1:.3f})")
    duas("z", "p")
    z2 = js("return c.tela.vp.z;")
    ok(abs(z2 - z0) < 1e-9, f"D. Z P volta à vista de antes da janela — o enquadrar do Z é desfeito ({z2:.3f} = {z0:.3f})")
    duas("z", "w")
    clique([2000, 2000]); clique([2600, 2500])
    ok(abs(js("return c.tela.vp.z;") - z1) < 1e-6, "D. Z W de novo: a janela marcada na vista em que se estava, não no desenho inteiro")
    clicar_el("document.querySelector('.menu[data-menu=ver] .menu-botao')")
    ok(clicar_el("document.querySelector('button[data-acao=\"zoom-anterior\"]')"), "D. Ver › Zoom anterior")
    z3 = js("return c.tela.vp.z;")
    ok(abs(z3 - z0) < 1e-9, f"D. pelo menu também volta ({z3:.3f} = {z0:.3f})")

    # ------------------------------------------------------------------ E. cadeado
    vista([[-200, 1800], [3200, 2700]])
    ok(clicar_el("document.querySelector('.cadeado[data-camada=ARQ]')"), "E. o cadeado da camada ARQ")
    ok(js("return c.doc.camadas.get('ARQ').bloqueada;") is True, "E. a camada ARQ travada")
    clique([500, 2500])
    ok("arq" not in (js("return [...c.tela.selecao];") or []), "E. a linha da camada travada não seleciona")
    esc()                                                  # o clique "no vazio" abriu a janela de seleção
    ok(clicar_el("[...document.querySelectorAll('.acoes-painel button')].find(b => b.textContent.startsWith('Destravar todas'))"), "E. Destravar todas")
    clique([500, 2500])
    ok(js("return [...c.tela.selecao];") == ["arq"], f"E. destravada, seleciona ({js('return [...c.tela.selecao];')})")
    esc()

    # ------------------------------------------------------------------ F. área e peso
    vista([[1800, 1800], [3200, 2700]])
    js("c.selecionar(['chapa', 'furo']); return 1;"); aba.drenar(0.4)
    painel = js("return document.querySelector('#painel-props, .props') ? [...document.querySelectorAll('.props')].map(p => p.textContent).join(' ') : '';") or ""
    ok("0,4921 m²" in painel and "sem 1 furo" in painel, f"F. a área da chapa 1000 × 500 sem o furo Ø100: 0,4921 m² ({painel[painel.find('Área'):][:80] if 'Área' in painel else painel[:60]})")
    ok("3.000 mm" in painel, "F. o perímetro externo: 3.000 mm")
    ok("24,53 kg" in painel, f"F. o peso com #6,35: 24,53 kg ({painel[painel.find('Peso'):][:40] if 'Peso' in painel else ''})")
    esc()

    # ------------------------------------------------------------------ G. Ctrl+C num desenho e Ctrl+V no outro
    vista([[3800, -300], [4700, 200]])
    js("c.selecionar(['tx', 'lx']); return 1;")
    tecla("c", 2)
    ok(ferr() == "selecionar" and "copiado" in (js("return c.el.dica.textContent;") or ""), f"G. Ctrl+C copia (sem abrir a cópia da tesoura): {js('return c.el.dica.textContent;')}")
    ok(esperar("(JSON.parse(localStorage.getItem('cad.copia') || '{}').sequencia ?? null) !== null", 10), "G. a cópia guarda o número da área de transferência do Windows")
    js("c.salvar({ avisar: false }); return 1;"); aba.drenar(1.0)
    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=obra-rapida&desenho=desenho-b", limite=60)
    ok(esperar("document.body.dataset.pronto === '1' && window.cad && window.cad.doc.tamanho === 1", 40), "G. o desenho B aberto")
    js("c.tela.enquadrar([[-500, -500], [2000, 1000]], 0.05); return 1;"); aba.drenar(0.3)
    x, y = tela([500, 500]); ev("mouseMoved", x, y); aba.drenar(0.2)
    tecla("v", 2)
    ok(esperar("c.ferramenta.constructor.id === 'colar_autocad' && (c.tela.previa || []).length === 2", 20), "G. Ctrl+V no desenho B: os 2 objetos do A presos ao cursor")
    clique([500, 500])
    cs = js("return [...c.doc.entidades.values()].filter(e => e.id !== 'ref').map(e => JSON.parse(JSON.stringify(e)));") or []
    lx = next((e for e in cs if e["tipo"] == "linha"), None); tx = next((e for e in cs if e["tipo"] == "texto"), None)
    ok(lx and perto(lx["a"], [500, 500]) and perto(lx["b"], [1000, 500]), f"G. a linha colada com o canto de baixo à esquerda no clique: {lx and (lx['a'], lx['b'])}")
    ok(tx and abs(tx["altura"] - 1.25) < 1e-9, f"G. o texto do 1:10 no 1:20 com o mesmo tamanho (altura 2,5 → {tx and tx['altura']})")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
