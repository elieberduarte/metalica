# -*- coding: utf-8 -*-
"""O fluxo das ferramentas de DESENHO e ANOTAÇÃO do CAD 2D (15/10/2026), só com o mouse e o teclado de verdade (CDP):
Linha (L), Polilinha (P), Retângulo (R), Círculo (C), Arco (A), Texto (T), Chamada (H), Hachura (G), Cota (D),
Ajustar cotas ao desenho (botão da barra) e Mover linha de cota (J).

Para cada uma: o atalho abre a ferramenta; o caminho feliz pelos cliques; a medida digitada (comprimento, "1500<30",
"largura;altura", raio, "d" + diâmetro); o snap nos pontos de outra entidade (extremidade, meio, centro, interseção,
a ponta da linha de outra cota); Esc no meio cancela sem deixar lixo e volta ao Selecionar; Enter (e o duplo clique)
termina a polilinha; Ctrl+Z desfaz num passo; o número digitado logo depois do clique vai para a caixa MEDIDAS e não vira
atalho; as letras de opção (C da polilinha, H/V/A/L/P da cota) ficam com a ferramenta e não abrem outra.

O desenho de partida (escala 1:20) tem, em cada zona (uma por ferramenta, 20 m uma da outra), a linha horizontal
[0,0]–[2000,0], a vertical [1500,-1000]–[1500,1000] (cruzam em [1500,0]), o círculo de centro [4000,0] e R 500 e o
quadrado fechado [0,-2500]–[1000,-1500]. Só se lê o estado por JS para conferir (e para enquadrar a zona na tela);
toda entrada é Input.dispatchMouseEvent / Input.dispatchKeyEvent.

As verificações que FALHAM hoje são defeitos achados (15/10), deixados aqui para servir de teste da correção.
Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_fluxo_desenho.py"""
import json, math, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_fluxo2d_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas, acertos = [], []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    (acertos if c else falhas).append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


ESCALA = 20
ZONAS = ["linha", "polilinha", "retangulo", "circulo", "arco", "texto", "chamada", "hachura", "cota", "cota_fator", "ajustar", "mover"]
OX = {z: i * 20000 for i, z in enumerate(ZONAS)}
ents = []
for z, x in OX.items():
    ents += [
        {"id": f"h_{z}", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [x, 0], "b": [x + 2000, 0]},
        {"id": f"v_{z}", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [x + 1500, -1000], "b": [x + 1500, 1000]},
        {"id": f"c_{z}", "tipo": "circulo", "camada": "VISTA", "atributos": {}, "centro": [x + 4000, 0], "raio": 500},
        {"id": f"q_{z}", "tipo": "polilinha", "camada": "VISTA", "atributos": {}, "fechada": True,
         "vertices": [[x, -2500], [x + 1000, -2500], [x + 1000, -1500], [x, -1500]]},
    ]
# textos de 5 mm no papel em volta das cotas das zonas "cota_fator" e "ajustar" (o dobro do padrão 2,5: fator 2)
for z in ("cota_fator", "ajustar"):
    x = OX[z]
    ents += [{"id": f"t{i}_{z}", "tipo": "texto", "camada": "TEXTO", "atributos": {}, "posicao": [x + 1000 * i, 2500], "texto": "PERFIL",
              "altura": 5, "angulo": 0} for i in range(3)]
x = OX["ajustar"]
ents += [{"id": "cz", "tipo": "cota", "camada": "COTA", "atributos": {}, "modo": "h", "p1": [x, 1500], "p2": [x + 2000, 1500],
          "deslocamento": 10, "texto": None, "altura": 2.5},
         {"id": "cz2", "tipo": "cota", "camada": "COTA", "atributos": {}, "modo": "h", "p1": [x + 2500, 1500], "p2": [x + 4500, 1500],
          "deslocamento": 10, "texto": None, "altura": 2.5}]
x = OX["mover"]
ents += [{"id": "ma", "tipo": "cota", "camada": "COTA", "atributos": {}, "modo": "h", "p1": [x, 0], "p2": [x + 2000, 0],
          "deslocamento": 10, "texto": None, "altura": 2.5},
         {"id": "mb", "tipo": "cota", "camada": "COTA", "atributos": {}, "modo": "h", "p1": [x + 2600, 0], "p2": [x + 4600, 0],
          "deslocamento": 20, "texto": None, "altura": 2.5}]
N0 = len(ents)

chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_fluxo2d_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
TECLAS = {"Enter": 13, "Escape": 27, "Control": 17, " ": 32, "Delete": 46, "Shift": 16}
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Fluxo desenho", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/fluxo", {"desenho": {"nome": "Fluxo", "escala": ESCALA, "entidades": ents}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + f"/cad?projeto={slug}&desenho=fluxo", limite=60)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    t0 = time.time()
    while time.time() - t0 < 60 and not js(f"return document.body.dataset.pronto === '1' && !!c && c.doc.tamanho === {N0};"):
        aba.drenar(0.4)
    aba.drenar(1.5)                    # a tela assenta (painéis, primeiro quadro)
    ok(js(f"return c.doc.tamanho;") == N0, f"desenho aberto com as {N0} entidades de partida")
    aba.console.clear()

    # ------------------------------------------------------------------ entrada de verdade
    def tela(p):
        return js(f"const t = c.tela.paraTela({json.dumps(p)}), r = c.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")

    def mover(x, y, botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=botoes); aba.drenar(0.06)

    def sobre_canvas(x, y):
        s = aba.avaliar(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e === window.cad.el.canvas ? '' : (e ? (e.id || String(e.className) || e.tagName) : 'nada'); }})()")
        if s: print(f"     (o clique em {x},{y} caiu em cima de: {s})")
        return not s

    def clicar(x, y, mods=0, n=1):
        mover(x, y)
        sobre_canvas(x, y)
        for k in range(1, n + 1):
            aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=k, buttons=1, modifiers=mods)
            aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=k, buttons=0, modifiers=mods)
        aba.drenar(0.2)

    def clicar_mm(p, desvio=(0, 0), mods=0, n=1):
        x, y = tela(p)
        clicar(x + desvio[0], y + desvio[1], mods, n)

    def mover_mm(p, desvio=(0, 0)):
        x, y = tela(p)
        mover(x + desvio[0], y + desvio[1])

    def tecla(k, mods=0):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = k if len(k) == 1 and not mods else ("\r" if k == "Enter" else "")   # o Enter de verdade traz o "\r" (é ele que envia o formulário da caixa)
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if len(k) == 1 and k.isalpha() else "",
                windowsVirtualKeyCode=code, text=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.12)

    def digitar(t, enter=True):
        # o primeiro caractere vai do desenho para a caixa MEDIDAS (o CAD a foca); o resto entra nela; Enter manda
        tecla(t[0])
        if len(t) > 1: aba.cmd("Input.insertText", text=t[1:])
        aba.drenar(0.05)
        if enter: tecla("Enter")
        aba.drenar(0.2)

    def desfazer():
        tecla("z", 2)

    def zona(z, caixa=((-1200, -3000), (5600, 2000))):
        x = OX[z]
        js(f"c.tela.enquadrar([[{x + caixa[0][0]}, {caixa[0][1]}], [{x + caixa[1][0]}, {caixa[1][1]}]]); return 1;")
        aba.drenar(0.3)
        mover(5, 500)   # o mouse sai do desenho entre uma zona e outra

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    novas = lambda tipo=None: js("return [...c.doc.entidades.values()].filter(e => !e.id.includes('_') && !['cz','cz2','ma','mb'].includes(e.id)"
                                 + (f" && e.tipo === '{tipo}'" if tipo else "") + ");")
    n_ents = lambda: js("return c.doc.tamanho;")
    sem_lixo = lambda: js("return c.tela.previa.length === 0 && !c.snap.ultimo && document.activeElement !== c.el.medida && !c.el.medida.value;")
    perto = lambda a, b, tol=1e-6: a is not None and b is not None and all(abs(u - v) <= tol for u, v in zip(a, b))
    mmpx = lambda: js("return c.tela.mmPorPixel;")

    def ultima(tipo):
        l = novas(tipo)
        return l[-1] if l else None

    # ================================================================== LINHA (L)
    print("\n-- Linha")
    zona("linha"); X = OX["linha"]
    tecla("l")
    ok(ferr() == "linha", "L abre a Linha")
    n = n_ents()
    clicar_mm([X - 800, -1200]); clicar_mm([X + 200, -1200])
    l1 = ultima("linha"); tol = 1.5 * mmpx()
    ok(n_ents() == n + 1 and l1 and perto(l1["a"], [X - 800, -1200], tol) and perto(l1["b"], [X + 200, -1200], tol),
       f"dois cliques: uma linha entre eles ({l1 and [l1['a'], l1['b']]})")
    tecla("Enter")
    ok(ferr() == "linha" and js("return c.ferramenta.ultimo === null && c.tela.previa.length === 0;"), "Enter termina a sequência e a Linha continua ativa")
    # snap: meio da horizontal → centro do círculo; interseção → ponta da vertical; extremidade
    clicar_mm([X + 1000, 0], (4, -3)); clicar_mm([X + 4000, 0], (-3, 4)); tecla("Enter")
    l2 = ultima("linha")
    ok(l2 and perto(l2["a"], [X + 1000, 0]) and perto(l2["b"], [X + 4000, 0]), f"snap no meio da linha e no centro do círculo ({l2 and [l2['a'], l2['b']]})")
    clicar_mm([X + 1500, 0], (3, 4)); clicar_mm([X + 1500, 1000], (-4, -3)); tecla("Enter")
    l3 = ultima("linha")
    ok(l3 and perto(l3["a"], [X + 1500, 0]) and perto(l3["b"], [X + 1500, 1000]), f"snap na interseção e na extremidade ({l3 and [l3['a'], l3['b']]})")
    # medida digitada: comprimento na direção do cursor, e "comprimento<ângulo"
    clicar_mm([X, 0], (3, 3)); mover_mm([X, -900])
    digitar("750")
    l4 = ultima("linha")
    ok(l4 and perto(l4["a"], [X, 0]) and perto(l4["b"], [X, -750], 1e-3), f"clique na ponta, cursor para baixo e 750 + Enter: a linha de 750 para baixo ({l4 and [l4['a'], l4['b']]})")
    ok(ferr() == "linha" and js("return document.activeElement !== c.el.medida && !c.el.medida.value;"),
       "o número digitado foi para a caixa MEDIDAS (a Linha continua, a caixa volta vazia e sem foco)")
    digitar("1,5m<30")
    l5 = ultima("linha")
    ok(l5 and perto(l5["a"], [X, -750], 1e-3) and perto(l5["b"], [X + 1500 * math.cos(math.pi / 6), -750 + 750], 1e-3),
       f"logo depois, \"1,5m<30\": 1500 mm a 30° a partir da ponta anterior ({l5 and l5['b']})")
    tecla("Enter")
    # Esc no meio
    n = n_ents()
    clicar_mm([X - 900, -1700]); mover_mm([X - 100, -1700])
    ok(js("return c.tela.previa.length;") == 1, "com o primeiro ponto dado, a prévia acompanha o cursor")
    tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")
    # Ctrl+Z
    tecla("l"); n = n_ents()
    clicar_mm([X - 900, 1200]); clicar_mm([X + 100, 1200]); clicar_mm([X + 100, 1700]); tecla("Enter")
    ok(n_ents() == n + 2, "três cliques e Enter: dois trechos")
    desfazer()
    ok(n_ents() == n + 1, "Ctrl+Z tira o último trecho (um passo)")
    desfazer()
    ok(n_ents() == n, "outro Ctrl+Z tira o primeiro")
    # Ctrl+Z no meio da sequência: o trecho seguinte deveria sair da ponta que sobrou, não do ponto do trecho apagado
    pa, pb, pc_, pd = [X - 900, 1200], [X + 100, 1200], [X + 100, 1700], [X + 900, 1700]
    clicar_mm(pa); clicar_mm(pb); clicar_mm(pc_)
    pb_real = js("const l = [...c.doc.entidades.values()].filter(e => e.tipo === 'linha').pop(); return l.a;")
    desfazer()
    clicar_mm(pd); tecla("Enter")
    l6 = ultima("linha")
    ok(l6 and perto(l6["a"], pb_real, 1e-6),
       f"Ctrl+Z no meio da Linha: o trecho seguinte sai da ponta que sobrou (esperado {pb_real}; saiu de {l6 and l6['a']}, a ponta do trecho desfeito)")
    tecla("Escape")

    # ================================================================== POLILINHA (P)
    print("\n-- Polilinha")
    zona("polilinha"); X = OX["polilinha"]
    tecla("p")
    ok(ferr() == "polilinha", "P abre a Polilinha")
    n = n_ents()
    clicar_mm([X - 900, 1200]); clicar_mm([X, 1700]); clicar_mm([X + 900, 1200])
    ok(n_ents() == n and js("return c.tela.previa.length;") == 1, "três cliques: só a prévia, nada gravado ainda")
    tecla("Enter")
    p1 = ultima("polilinha")
    ok(n_ents() == n + 1 and p1 and len(p1["vertices"]) == 3 and not p1.get("fechada") and ferr() == "polilinha",
       f"Enter grava a polilinha aberta de 3 vértices e a ferramenta continua ({p1 and len(p1['vertices'])} vértices)")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira a polilinha inteira num passo")
    # snap e medida digitada (o cursor na mesma linha de pixels: a direção é exata)
    clicar_mm([X, 0], (3, -3)); mover_mm([X + 600, 0])
    digitar("1000")
    mover_mm([X + 1000, 800])
    digitar("500")
    tecla("Enter")
    p2 = ultima("polilinha")
    ok(p2 and len(p2["vertices"]) == 3 and perto(p2["vertices"][0], [X, 0]) and perto(p2["vertices"][1], [X + 1000, 0], 1e-3)
       and perto(p2["vertices"][2], [X + 1000, 500], 1e-3), f"snap na ponta, \"1000\" para a direita e \"500\" para cima ({p2 and p2['vertices']})")
    ok(ferr() == "polilinha", "os números digitados não trocaram a ferramenta")
    # C fecha (com 3 ou mais vértices)
    n = n_ents()
    clicar_mm([X - 900, -500]); clicar_mm([X - 300, -500]); clicar_mm([X - 300, -1000])
    tecla("c")
    p3 = ultima("polilinha")
    ok(n_ents() == n + 1 and p3 and p3.get("fechada") and len(p3["vertices"]) == 3 and ferr() == "polilinha",
       f"C com 3 vértices fecha a polilinha e não abre o Círculo (ferramenta: {ferr()})")
    # C com 2 vértices: a letra de opção não pode abrir o Círculo e jogar fora os pontos
    clicar_mm([X - 900, -1200]); clicar_mm([X - 300, -1200])
    tecla("c")
    f_ = ferr()
    ok(f_ == "polilinha" and js("return (c.ferramenta.pontos || []).length;") == 2,
       f"C com só 2 vértices não abre o Círculo nem perde os pontos (ferramenta: {f_})")
    tecla("Escape"); tecla("p")
    # duplo clique termina
    n = n_ents()
    clicar_mm([X + 2500, 1200]); clicar_mm([X + 3200, 1700]); clicar_mm([X + 3900, 1200], n=2)
    aba.drenar(0.3)
    p4 = ultima("polilinha")
    ok(n_ents() == n + 1 and p4 and len(p4["vertices"]) == 3,
       f"duplo clique no último ponto termina a polilinha ({n_ents() - n} gravada(s); {js('return (c.ferramenta.pontos || []).length;')} vértice(s) ainda em curso)")
    tecla("Escape"); tecla("p")
    # Esc no meio
    n = n_ents()
    clicar_mm([X + 2500, -500]); clicar_mm([X + 3200, -500]); mover_mm([X + 3200, -1000])
    tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")
    # Ctrl+Z no meio: não pode desfazer outro objeto do desenho (o último comando é a polilinha fechada acima)
    tecla("p")
    antes = js("return [...c.doc.entidades.keys()].sort();")
    clicar_mm([X + 2500, -1200]); clicar_mm([X + 3200, -1200]); clicar_mm([X + 3200, -1700])
    desfazer()
    depois = js("return [...c.doc.entidades.keys()].sort();")
    ok(depois == antes, f"Ctrl+Z no meio da polilinha não apaga outro objeto do desenho ({len(antes) - len(depois)} apagado(s))")
    ok(js("return (c.ferramenta.pontos || []).length;") == 2, f"… e tira o último vértice em curso ({js('return (c.ferramenta.pontos || []).length;')} vértices)")
    tecla("Escape")
    # (se o Ctrl+Z apagou a polilinha fechada, o Ctrl+Shift+Z a devolve, para não atrapalhar o resto)
    if depois != antes: tecla("z", 2 | 8)

    # ================================================================== RETÂNGULO (R)
    print("\n-- Retângulo")
    zona("retangulo"); X = OX["retangulo"]
    tecla("r")
    ok(ferr() == "retangulo", "R abre o Retângulo")
    n = n_ents()
    clicar_mm([X - 900, 1200]); clicar_mm([X + 700, 1800])
    r1 = ultima("polilinha"); tol = 1.5 * mmpx()
    ok(n_ents() == n + 1 and r1 and r1.get("fechada") and len(r1["vertices"]) == 4 and perto(r1["vertices"][0], [X - 900, 1200], tol)
       and perto(r1["vertices"][2], [X + 700, 1800], tol), "dois cliques: o retângulo fechado entre os cantos")
    ok(ferr() == "retangulo", "a ferramenta continua depois do retângulo")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira o retângulo num passo")
    # snap: canto na ponta da horizontal e o oposto na ponta de cima da vertical
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, 3))
    r2 = ultima("polilinha")
    ok(r2 and perto(r2["vertices"][0], [X, 0]) and perto(r2["vertices"][2], [X + 1500, 1000]), f"snap nos dois cantos ({r2 and r2['vertices']})")
    # medida "largura;altura" e "largura x altura"
    clicar_mm([X + 2000, 0], (3, 3)); mover_mm([X + 2600, 600])
    digitar("2000;1000")
    r3 = ultima("polilinha")
    ok(r3 and perto(r3["vertices"][0], [X + 2000, 0]) and perto(r3["vertices"][2], [X + 4000, 1000], 1e-6), f"\"2000;1000\": o retângulo de 2000 × 1000 ({r3 and r3['vertices'][2]})")
    ok(ferr() == "retangulo", "o número digitado não virou atalho")
    clicar_mm([X - 1000, -1000]); digitar("50cmx30cm")
    r4 = ultima("polilinha")
    ok(r4 and perto([r4["vertices"][2][0] - r4["vertices"][0][0], r4["vertices"][2][1] - r4["vertices"][0][1]], [500, 300], 1e-6),
       "\"50cmx30cm\": o x entra na caixa sem abrir outra ferramenta e vira 500 × 300")
    # com o cursor à esquerda e abaixo, as medidas vão para o lado do cursor (como a Linha faz com o comprimento)
    clicar_mm([X + 1500, -1000], (3, 3)); mover_mm([X + 900, -1700])
    digitar("400;300")
    r5 = ultima("polilinha")
    ok(r5 and perto(r5["vertices"][2], [X + 1100, -1300], 1e-6),
       f"\"400;300\" com o cursor à esquerda e abaixo: o canto oposto vai para o lado do cursor ([{X + 1100}, -1300]; saiu {r5 and r5['vertices'][2]})")
    clicar_mm([X + 1500, -1000], (3, 3)); digitar("-400;-300")
    r6 = ultima("polilinha")
    ok(r6 and perto(r6["vertices"][2], [X + 1100, -1300], 1e-6), "\"-400;-300\" (com sinal) vai para a esquerda e para baixo")
    # Esc no meio
    n = n_ents()
    clicar_mm([X - 900, -2800]); mover_mm([X - 200, -2600])
    tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")
    # Ctrl+Z com o primeiro canto dado: desiste do canto, não apaga o retângulo de antes
    tecla("r")
    antes = js("return [...c.doc.entidades.keys()].sort();")
    clicar_mm([X - 900, -2800]); desfazer()
    depois = js("return [...c.doc.entidades.keys()].sort();")
    ok(depois == antes and js("return c.ferramenta.a === null;"),
       f"Ctrl+Z com o primeiro canto dado desiste do canto e não apaga outro objeto ({len(antes) - len(depois)} apagado(s))")
    tecla("Escape")
    if depois != antes: tecla("z", 2 | 8)

    # ================================================================== CÍRCULO (C)
    print("\n-- Círculo")
    zona("circulo"); X = OX["circulo"]
    tecla("c")
    ok(ferr() == "circulo", "C abre o Círculo")
    n = n_ents()
    clicar_mm([X - 600, 1300]); clicar_mm([X - 300, 1300])
    c1 = ultima("circulo"); tol = 1.5 * mmpx()
    ok(n_ents() == n + 1 and c1 and abs(c1["raio"] - 300) < tol, f"centro e ponto do raio: o círculo ({c1 and round(c1['raio'], 1)})")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira o círculo num passo")
    # snap: centro na ponta da horizontal, raio até a interseção (R 500)
    clicar_mm([X + 2000, 0], (3, 3)); clicar_mm([X + 1500, 0], (-3, 4))
    c2 = ultima("circulo")
    ok(c2 and perto(c2["centro"], [X + 2000, 0]) and abs(c2["raio"] - 500) < 1e-6, f"snap: centro na extremidade e o raio até a interseção ({c2 and (c2['centro'], c2['raio'])})")
    # concêntrico: centro no centro do círculo existente, raio no quadrante
    clicar_mm([X + 4000, 0], (4, 3)); mover_mm([X + 4300, 0])
    digitar("300")
    c3 = ultima("circulo")
    ok(c3 and perto(c3["centro"], [X + 4000, 0]) and abs(c3["raio"] - 300) < 1e-9, f"snap no centro do círculo e raio digitado 300 ({c3 and (c3['centro'], c3['raio'])})")
    ok(ferr() == "circulo", "o número digitado não virou atalho")
    # "d" + valor: o diâmetro (a dica promete); a letra d não pode abrir a Cota
    n = n_ents()
    clicar_mm([X - 600, -1000])
    digitar("d500")
    f_ = ferr(); c4 = ultima("circulo")
    ok(f_ == "circulo" and n_ents() == n + 1 and c4 and abs(c4["raio"] - 250) < 1e-9,
       f"depois do centro, \"d500\" faz o círculo de diâmetro 500 (ferramenta: {f_}, {n_ents() - n} círculo(s) novo(s))")
    tecla("Escape"); tecla("c")
    # Esc no meio
    n = n_ents()
    clicar_mm([X - 900, -2800]); mover_mm([X - 600, -2800])
    tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")

    # ================================================================== ARCO (A)
    print("\n-- Arco")
    zona("arco"); X = OX["arco"]
    tecla("a")
    ok(ferr() == "arco", "A abre o Arco")
    n = n_ents()
    # pelos três pontos de snap: início na ponta esquerda da horizontal, meio na ponta de cima da vertical, fim na direita
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); clicar_mm([X + 2000, 0], (3, 3))
    a1 = ultima("arco")
    passa = False
    if a1:
        cx, cy = a1["centro"]; r_ = a1["raio"]
        passa = all(abs(math.hypot(px - cx, py - cy) - r_) < 1e-6 for px, py in ([X, 0], [X + 1500, 1000], [X + 2000, 0]))
        g = lambda px, py: (math.degrees(math.atan2(py - cy, px - cx)) + 360) % 360
        i0, f0, m0 = a1["inicio"] % 360, a1["fim"] % 360, g(X + 1500, 1000)
        dentro = (i0 <= m0 <= f0) if f0 >= i0 else (m0 >= i0 or m0 <= f0)
        passa = passa and dentro and {round(i0, 3), round(f0, 3)} == {round(g(X, 0), 3), round(g(X + 2000, 0), 3)}
    ok(n_ents() == n + 1 and passa, f"três cliques no snap: o arco passa pelos três pontos e vai de um ao outro pelo do meio ({a1 and (a1['centro'], a1['raio'], a1['inicio'], a1['fim'])})")
    ok(ferr() == "arco", "a ferramenta continua depois do arco")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira o arco num passo")
    clicar_mm([X - 900, 1200]); clicar_mm([X - 400, 1600])
    ok(js("return c.tela.previa.length === 1 && c.tela.previa[0].tipo;") is not None, "depois de dois pontos, a prévia do arco segue o cursor")
    tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")

    # ================================================================== TEXTO (T)
    print("\n-- Texto")
    zona("texto"); X = OX["texto"]
    tecla("t")
    ok(ferr() == "texto", "T abre o Texto")
    n = n_ents()
    clicar_mm([X + 2000, 0], (3, 3))
    ok(js("return !!document.querySelector('dialog[open]');"), "o clique abre a caixa do conteúdo")
    for k in "LPRC": tecla(k)            # letras que são atalhos: dentro da caixa são texto
    aba.cmd("Input.insertText", text=" 02x"); tecla("Enter"); aba.drenar(0.3)
    t1 = ultima("texto")
    ok(n_ents() == n + 1 and t1 and t1["texto"] == "LPRC 02x" and perto(t1["posicao"], [X + 2000, 0]),
       f"conteúdo digitado (com L, P, R, C) e Enter: o texto no ponto do snap ({t1 and (t1['texto'], t1['posicao'])})")
    ok(ferr() == "texto" and not js("return !!document.querySelector('dialog[open]');"), "as letras ficaram na caixa: a ferramenta continua Texto")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira o texto num passo")
    clicar_mm([X - 600, 1200]); tecla("Escape"); aba.drenar(0.3)
    ok(n_ents() == n and not js("return !!document.querySelector('dialog[open]');"), "Esc na caixa: nenhum texto")
    tecla("Escape")
    ok(ferr() == "selecionar" and sem_lixo(), "o Esc seguinte volta ao Selecionar")

    # ================================================================== CHAMADA (H)
    print("\n-- Chamada")
    zona("chamada"); X = OX["chamada"]
    tecla("h")
    ok(ferr() == "chamada", "H abre a Chamada")
    n = n_ents()
    clicar_mm([X + 1500, 0], (3, -3)); mover_mm([X + 2500, 900])
    ok(js("return c.tela.previa.length === 1 && c.tela.previa[0].tipo === 'chamada';"), "depois do ponto apontado, a prévia da chamada segue o cursor")
    clicar_mm([X + 2500, 900])
    ok(js("return !!document.querySelector('dialog[open]');"), "o segundo clique abre a caixa do texto")
    aba.cmd("Input.insertText", text="CH9 #6,3"); tecla("Enter"); aba.drenar(0.3)
    h1 = ultima("chamada")
    ok(n_ents() == n + 1 and h1 and h1["texto"] == "CH9 #6,3" and perto(h1["alvo"], [X + 1500, 0]),
       f"a chamada aponta a interseção (snap) com o texto digitado ({h1 and (h1['texto'], h1['alvo'])})")
    desfazer()
    ok(n_ents() == n, "Ctrl+Z tira a chamada num passo")
    clicar_mm([X - 600, 1200]); clicar_mm([X - 100, 1600]); tecla("Escape"); aba.drenar(0.3)
    ok(n_ents() == n and js("return c.ferramenta.constructor.id === 'chamada' && c.ferramenta.alvo === null;"),
       "Esc na caixa do texto: nenhuma chamada e a ferramenta volta ao ponto apontado")
    clicar_mm([X - 600, -1000]); tecla("Escape")
    ok(n_ents() == n and sem_lixo() and ferr() == "selecionar", "Esc depois do ponto apontado: nada gravado, volta ao Selecionar")

    # ================================================================== HACHURA (G)
    print("\n-- Hachura")
    zona("hachura"); X = OX["hachura"]
    tecla("g")
    ok(ferr() == "hachura", "G abre a Hachura")
    n = n_ents()
    clicar_mm([X + 300, -2200])
    g1 = ultima("hachura")
    ok(n_ents() == n + 1 and g1 and (g1.get("atributos") or {}).get("contorno") == "q_hachura", "clique dentro do quadrado fechado: a hachura dele")
    clicar_mm([X + 700, -1800])
    ok(n_ents() == n + 1, f"o segundo clique no mesmo contorno não empilha outra hachura igual ({n_ents() - n} hachura(s))")
    while n_ents() > n: desfazer()
    ok(n_ents() == n, "Ctrl+Z tira a hachura num passo")
    clicar_mm([X + 2800, 1300])
    ok(n_ents() == n and "contorno fechado" in (js("return c.el.dica.textContent;") or ""), "clique fora de um contorno: nada, e a dica explica")
    # o retângulo feito pelo R vira contorno
    tecla("r"); clicar_mm([X + 2200, -2800]); clicar_mm([X + 3200, -1800]); tecla("g")
    clicar_mm([X + 2500, -2500])
    g2 = ultima("hachura"); rr = ultima("polilinha")
    ok(g2 and rr and (g2.get("atributos") or {}).get("contorno") == rr["id"], "a Hachura pega o retângulo recém-desenhado com o R")
    tecla("Escape")
    ok(ferr() == "selecionar" and sem_lixo(), "Esc volta ao Selecionar")

    # ================================================================== COTA (D)
    print("\n-- Cota")
    zona("cota"); X = OX["cota"]
    tecla("d")
    ok(ferr() == "cota", "D abre a Cota")
    n = n_ents()
    medida_cota = lambda k: (abs(k["p2"][0] - k["p1"][0]) if k["modo"] == "h" else abs(k["p2"][1] - k["p1"][1]) if k["modo"] == "v" else math.hypot(k["p2"][0] - k["p1"][0], k["p2"][1] - k["p1"][1]))
    # os pontos fora de prumo e de nível: a ponta esquerda da horizontal e a de cima da vertical
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); clicar_mm([X + 700, 1600])
    k1 = ultima("cota")
    ok(n_ents() == n + 1 and k1 and k1["modo"] == "h" and perto(k1["p1"], [X, 0]) and perto(k1["p2"], [X + 1500, 1000]) and abs(medida_cota(k1) - 1500) < 1e-9,
       f"mouse acima dos pontos: a horizontal de 1500 nos pontos do snap ({k1 and (k1['modo'], k1['p1'], k1['p2'])})")
    ok(ferr() == "cota", "a ferramenta continua depois da cota")
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); clicar_mm([X + 2600, 500])
    k2 = ultima("cota")
    ok(k2 and k2["modo"] == "v" and abs(medida_cota(k2) - 1000) < 1e-9, f"mouse ao lado: a vertical de 1000 ({k2 and k2['modo']})")
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); clicar_mm([X + 600, 600])
    k3 = ultima("cota")
    ok(k3 and k3["modo"] == "alinhada", f"mouse entre os pontos: a alinhada ({k3 and k3['modo']})")
    # as letras de opção: ficam com a Cota (L não abre a Linha, P não abre a Polilinha, A não abre o Arco…)
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); mover_mm([X + 700, 1600])
    abriu = []
    for k, modo in (("v", "v"), ("a", "alinhada"), ("h", "h"), ("l", "linear")):
        tecla(k)
        abriu.append((k, ferr(), js("return c.ferramenta.modo;")))
    ok(all(f == "cota" and m == modo for (k, f, m), (_, modo) in zip(abriu, (("v", "v"), ("a", "alinhada"), ("h", "h"), ("l", "linear")))),
       f"V, A, H e L trocam o modo e a ferramenta continua Cota ({abriu})")
    tecla("v"); clicar_mm([X + 700, 1600])
    k4 = ultima("cota")
    ok(k4 and k4["modo"] == "v", f"com V fixado, o mouse acima dos pontos ainda faz a vertical ({k4 and k4['modo']})")
    tecla("l")
    tecla("p")
    ok(ferr() == "cota" and js("return c.ferramenta.padrao;") is True, "P fixa o tamanho padrão e não abre a Polilinha")
    tecla("p")
    ok(ferr() == "cota" and not js("return c.ferramenta.padrao;"), "P outra vez volta ao tamanho pelo desenho")
    n = n_ents()
    desfazer()
    ok(n_ents() == n - 1, "Ctrl+Z tira a cota num passo")
    # Esc no meio (depois do segundo ponto)
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 1500, 1000], (3, -3)); mover_mm([X + 700, 1600])
    tecla("Escape")
    ok(n_ents() == n - 1 and sem_lixo() and ferr() == "selecionar", "Esc no meio: nada gravado, prévia limpa, volta ao Selecionar")
    # o tamanho pelo desenho em volta: perto de textos de 5 mm, a cota nasce com fator 2; com P, sem fator
    zona("cota_fator"); X = OX["cota_fator"]
    tecla("d")
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 2000, 0], (3, 3)); clicar_mm([X + 1000, 600])
    k5 = ultima("cota")
    ok(k5 and k5.get("fator") == 2, f"perto de textos de 5 mm a cota nasce no tamanho deles (fator {k5 and k5.get('fator')})")
    tecla("p")
    clicar_mm([X, 0], (-3, 3)); clicar_mm([X + 2000, 0], (3, 3)); clicar_mm([X + 1000, -600])
    k6 = ultima("cota")
    ok(k6 and not k6.get("fator"), f"com P, o tamanho padrão (fator {k6 and k6.get('fator')})")
    tecla("p"); tecla("Escape")

    # ================================================================== AJUSTAR COTAS (botão)
    print("\n-- Ajustar cotas ao desenho")
    zona("ajustar"); X = OX["ajustar"]
    bt = js("const b = document.querySelector('[data-ferramenta=\"ajustar_cota\"]'); if (!b) return null; b.scrollIntoView({ block: 'nearest' }); const r = b.getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2), document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) === b || b.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2))];")
    ok(bt and bt[2], f"o botão Ajustar cotas está na barra e visível ({bt})")
    if bt:
        mover(bt[0], bt[1]); aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=bt[0], y=bt[1], button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=bt[0], y=bt[1], button="left", clickCount=1, buttons=0); aba.drenar(0.3)
    ok(ferr() == "ajustar_cota", "o clique no botão abre a ferramenta")
    linha_cz = 1500 + 10 * ESCALA
    clicar_mm([X + 400, linha_cz])
    ok(js("return c.doc.get('cz').fator;") == 2, f"clique na cota: ela toma o tamanho dos textos em volta (fator {js('return c.doc.get(\"cz\").fator;')})")
    ok(js("return c.doc.get('cz2').fator;") in (None, 1), "a outra cota não mudou")
    desfazer()
    ok(not js("return c.doc.get('cz').fator;"), "Ctrl+Z volta o tamanho num passo")
    clicar_mm([X + 1000, -2900])
    ok("Clique numa cota" in (js("return c.el.dica.textContent;") or ""), "clique fora de cota: a dica pede uma cota")
    tecla("Escape")
    ok(ferr() == "selecionar", "Esc volta ao Selecionar")
    # com as duas selecionadas antes (Selecionar, clique e Shift+clique), o botão ajusta as duas de uma vez
    clicar_mm([X + 400, linha_cz]); clicar_mm([X + 2900, linha_cz], mods=8)
    ok(sorted(js("return [...c.tela.selecao];") or []) == ["cz", "cz2"], f"clique e Shift+clique selecionam as duas cotas ({js('return [...c.tela.selecao];')})")
    if bt:
        mover(bt[0], bt[1]); aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=bt[0], y=bt[1], button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=bt[0], y=bt[1], button="left", clickCount=1, buttons=0); aba.drenar(0.3)
    ok(js("return [c.doc.get('cz').fator, c.doc.get('cz2').fator];") == [2, 2], "com a seleção, o botão ajusta as duas")
    desfazer()
    ok(js("return [c.doc.get('cz').fator || null, c.doc.get('cz2').fator || null];") == [None, None], "um Ctrl+Z volta as duas")
    mover(5, 500); tecla("Escape")

    # ================================================================== MOVER LINHA DE COTA (J)
    print("\n-- Mover linha de cota")
    zona("mover", ((-1200, -1500), (5600, 1500))); X = OX["mover"]
    tecla("j")
    ok(ferr() == "mover_cota", "J abre o Mover linha de cota")
    clicar_mm([X + 3000, 20 * ESCALA])                               # na linha da cota mb
    ok(js("return [...c.tela.selecao];") == ["mb"], "o primeiro clique pega a cota")
    mover_mm([X + 1200, 1000])
    ok(js("return c.tela.previa.length;") == 1, "a prévia da linha de cota segue o cursor")
    clicar_mm([X + 2000, 10 * ESCALA], (4, -3))                      # a ponta da linha de cota da ma (snap)
    mb = js("return c.doc.get('mb');")
    ok(mb and abs(mb["deslocamento"] - 10) < 1e-9 and mb["p1"] == [X + 2600, 0] and mb["p2"] == [X + 4600, 0],
       f"o segundo clique, no snap da ponta da linha de outra cota: a linha alinha com ela e os pontos medidos ficam (desloc. {mb and mb['deslocamento']})")
    desfazer()
    ok(js("return c.doc.get('mb').deslocamento;") == 20, "Ctrl+Z volta a linha num passo")
    clicar_mm([X + 3000, 20 * ESCALA]); mover_mm([X + 3000, 900]); tecla("Escape")
    ok(js("return c.doc.get('mb').deslocamento;") == 20 and sem_lixo() and ferr() == "selecionar" and not js("return c.tela.selecao.size;"),
       "Esc depois de pegar a cota: nada muda, a seleção limpa, volta ao Selecionar")
    # as duas selecionadas antes, J e um clique: as duas na mesma linha
    clicar_mm([X + 600, 10 * ESCALA]); clicar_mm([X + 3000, 20 * ESCALA], mods=8)
    tecla("j")
    clicar_mm([X + 2300, 30 * ESCALA])
    dd = js("return [c.doc.get('ma').deslocamento, c.doc.get('mb').deslocamento];")
    ok(dd and abs(dd[0] - dd[1]) < 1e-9 and abs(dd[0] - 30) < 1.5 * mmpx() / ESCALA, f"duas cotas selecionadas, J e um clique: as duas na mesma linha ({dd})")
    desfazer()
    ok(js("return [c.doc.get('ma').deslocamento, c.doc.get('mb').deslocamento];") == [10, 20], "um Ctrl+Z volta as duas")
    tecla("j"); clicar_mm([X + 2300, -1000])
    ok(ferr() == "mover_cota" and "Clique numa cota" in (js("return c.el.dica.textContent;") or ""), "clique fora de cota: a dica pede uma cota")
    tecla("Escape")

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
    aba.ws.close()
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print(f"\nOK: {len(acertos)}")
print("FALHAS:", len(falhas))
for f in falhas: print("  -", f[:160])
sys.exit(1 if falhas else 0)
