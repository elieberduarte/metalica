# -*- coding: utf-8 -*-
"""As ferramentas de transformação e de edição da seleção do CAD 2D (15/10/2026), só com o mouse e o teclado de verdade
(Chrome DevTools Protocol: Input.dispatchMouseEvent / Input.dispatchKeyEvent), como um usuário: Selecionar (clique,
Shift soma, Ctrl alterna, janela da esquerda para a direita × cruzando da direita para a esquerda, Ctrl+A, Del, alças
arrastadas, presas por um clique e com o comprimento digitado), Mover (M), Copiar (O), Girar (Q), Escala (pelo botão da
barra: não tem atalho), Espelhar (I), Copiar propriedades (M e logo depois A), Apagar (E), Explodir (B), Juntar (W) e
Esticar (S). Para cada uma: o caminho feliz com o mouse, a medida digitada (distância, "1,5m", "1000@90", "dx;dy",
ângulo, fator, referência), o snap no ponto base, com a seleção feita antes e sem seleção, Esc no meio (nada muda e a
ferramenta solta), Ctrl+Z num passo só e Ctrl+Y, a cópia com o toque no Ctrl, a camada travada que não muda, o número
digitado logo depois do clique que não vira atalho e Explodir → Juntar devolvendo o original.

O estado só é LIDO por JavaScript (o documento, a seleção, a ferramenta ativa, a dica); toda entrada é pelo mouse e pelo
teclado. As verificações que falham hoje são defeitos achados (ficam aqui para testar a correção).

Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_fluxo_edicao.py
"""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cadfluxo_")
PASTA = os.path.join(DADOS, "fluxo2d")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Fluxo 2D", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))


def L(id_, a, b, camada="VISTA"):
    return {"id": id_, "tipo": "linha", "camada": camada, "atributos": {}, "a": a, "b": b}


def PL(id_, vs, fechada=False, camada="VISTA"):
    return {"id": id_, "tipo": "polilinha", "camada": camada, "atributos": {}, "vertices": vs, "fechada": fechada}


ENTS = [
    L("l1", [0, 0], [1000, 0]),
    L("l2", [0, 600], [1000, 600]),
    L("lv", [2000, -500], [2000, 1500]),                                   # alvo dos snaps
    PL("rt", [[0, 2000], [1000, 2000], [1000, 2600], [0, 2600]], True),     # retângulo fechado
    PL("po", [[3000, 0], [3600, 0], [3600, 600]]),                          # polilinha aberta
    {"id": "ci", "tipo": "circulo", "camada": "VISTA", "atributos": {}, "centro": [3300, 2300], "raio": 250},
    {"id": "tx", "tipo": "texto", "camada": "TEXTO", "atributos": {}, "posicao": [0, 3200], "texto": "ORIGEM", "altura": 5, "angulo": 0},
    {"id": "t2", "tipo": "texto", "camada": "NOTAS", "atributos": {}, "posicao": [1800, 3200], "texto": "ALVO", "altura": 2, "angulo": 0},
    {"id": "ct", "tipo": "cota", "camada": "COTA", "atributos": {}, "modo": "h", "p1": [0, 600], "p2": [1000, 600],
     "deslocamento": 15, "texto": None, "altura": 2.5},
    L("lk", [0, 4200], [1000, 4200], camada="TRAVADA"),
    PL("pk", [[2000, 4200], [2600, 4200], [2600, 4600]], camada="TRAVADA"),
]
CAMADAS = {n: {"nome": n, "cor": "#4b5563", "visivel": True, "bloqueada": n == "TRAVADA"} for n in ("VISTA", "TEXTO", "NOTAS", "COTA", "TRAVADA")}
json.dump({"nome": "edicao", "unidade": "mm", "escala": 10, "camadas": CAMADAS, "entidades": ENTS, "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "edicao.desenho.json"), "w", encoding="utf-8"))

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas, oks = [], []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    (oks if c else falhas).append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadfluxo_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# tecla → (windowsVirtualKeyCode, code)
TECLAS = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), "Control": (17, "ControlLeft"), "Shift": (16, "ShiftLeft"),
          " ": (32, "Space"), "Delete": (46, "Delete"), ",": (188, "Comma"), ".": (190, "Period"), "-": (189, "Minus"),
          "@": (50, "Digit2"), ";": (186, "Semicolon")}
CTRL, SHIFT = 2, 8
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
    import websocket

    def _drenar(segundos):
        """O Aba.drenar espera até 1 s por mensagem a cada volta (settimeout 1.0): um drenar(0.1) durava ~1 s, e o M
        seguido do A passava do 1 s do atalho de duas letras. Aqui a espera é a pedida."""
        fim = time.time() + segundos
        aba.ws.settimeout(0.02)
        try:
            while time.time() < fim:
                try: aba._tratar(json.loads(aba.ws.recv()))
                except websocket.WebSocketTimeoutException: pass
        finally:
            aba.ws.settimeout(120)
    aba.drenar = _drenar
    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=fluxo2d&desenho=edicao", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho === %d" % len(ENTS)):
        aba.drenar(0.5)
    aba.drenar(1.5)
    aba.console.clear()

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def tela(p):
        return js(f"const t = c.tela.paraTela({json.dumps(p)}), r = c.el.canvas.getBoundingClientRect(); return [Math.round(r.left + t[0]), Math.round(r.top + t[1])];")

    cobertos = []

    def livre(x, y):
        s = aba.avaliar(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e === window.cad.el.canvas ? '' : (e ? (e.id || String(e.className) || e.tagName) : 'nada'); }})()")
        if s:
            cobertos.append((x, y, s)); print(f"     (o ponto {x},{y} da tela está coberto por: {s})")
        return not s

    def mover(x, y, mods=0, botoes=0):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=botoes, modifiers=mods,
                button="left" if botoes else "none"); aba.drenar(0.06)

    def clicar(x, y, mods=0):
        mover(x - 3, y - 2, mods); mover(x, y, mods)
        livre(x, y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1, modifiers=mods)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0, modifiers=mods)
        aba.drenar(0.2)

    def arrastar(de, para, mods=0, passos=6):
        livre(*de); livre(*para)
        mover(*de, mods)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=de[0], y=de[1], button="left", clickCount=1, buttons=1, modifiers=mods)
        for i in range(1, passos + 1):
            t = i / passos
            mover(round(de[0] + (para[0] - de[0]) * t), round(de[1] + (para[1] - de[1]) * t), mods, botoes=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=para[0], y=para[1], button="left", clickCount=1, buttons=0, modifiers=mods)
        aba.drenar(0.25)

    def tecla(k, mods=0):
        code, nome = TECLAS.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() else ("Digit" + k if k.isdigit() else "")))
        texto = k if len(k) == 1 and not (mods & CTRL) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.1)

    def digitar(t, enter=True):
        """Cada caractere como uma tecla de verdade (o primeiro número leva o foco para a caixa MEDIDAS; os demais
        chegam nela pelo teclado, e uma letra, como o "m" de "1,5m", não pode virar atalho)."""
        for ch in t: tecla(ch)
        if enter: tecla("Enter")
        aba.drenar(0.2)

    def toque_ctrl():
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key="Control", code="ControlLeft", windowsVirtualKeyCode=17, modifiers=CTRL)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key="Control", code="ControlLeft", windowsVirtualKeyCode=17, modifiers=0)
        aba.drenar(0.1)

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    sel = lambda: sorted(js("return [...c.tela.selecao];") or [])
    dica = lambda: js("return c.el.dica.textContent;") or ""
    ent = lambda i: js(f"const e = c.doc.get({json.dumps(i)}); return e ? JSON.parse(JSON.stringify(e)) : null;")
    feitos = lambda: js("return c.pilha.feitos.length;")
    cursor = lambda: js("return c.tela.cursor;")
    rnd = lambda v: [round(x, 3) for x in v]

    def estado():
        return js("""const o = {}; for (const e of c.doc.entidades.values()) { const x = JSON.parse(JSON.stringify(e)); o[e.id] = x; } return o;""")

    def esc():
        tecla("Escape"); aba.drenar(0.1)

    def desfazer_tudo():
        for _ in range(40):
            if not feitos(): break
            tecla("z", CTRL)

    def igual_ao_inicio(rot):
        d = estado()
        dif = sorted(set(d) ^ set(INICIO)) + sorted(k for k in d if k in INICIO and json.dumps(d[k], sort_keys=True) != json.dumps(INICIO[k], sort_keys=True))
        ok(not dif, f"{rot}: o desenho volta a ser o original" + (f" (diferem: {dif[:6]})" if dif else ""))

    def pt(e):
        """Um ponto clicável no traço da entidade (fora das pontas e do meio)."""
        return {"l1": [300, 0], "l2": [300, 600], "lv": [2000, 1200], "rt": [300, 2000], "po": [3200, 0], "ci": [3550, 2300],
                "tx": [40, 3215], "t2": [1810, 3205], "lk": [300, 4200], "pk": [2200, 4200]}[e]

    def clicar_em(p, mods=0, dx=0, dy=0):
        x, y = tela(p); clicar(x + dx, y + dy, mods)

    # ---------------------------------------------------------------- 0. abertura
    ok(js("return c.doc.tamanho;") == len(ENTS), f"desenho aberto com as {len(ENTS)} entidades")
    tecla("z")                                  # Z: enquadra tudo (tecla de verdade)
    aba.drenar(0.5)
    INICIO = estado()
    ok(ferr() == "selecionar", "abre na Selecionar")
    escala_px = js("return c.tela.vp.z;")
    print(f"     (zoom: {escala_px:.4f} px/mm — 1000 mm = {1000 * escala_px:.0f} px)")
    for nome in ("l1", "l2", "lv", "rt", "po", "ci", "tx", "t2", "lk", "pk"):
        livre(*tela(pt(nome)))
    ok(not cobertos, f"nenhum dos pontos de clique do desenho está coberto por painel ({cobertos[:3]})")
    cobertos.clear()

    # ---------------------------------------------------------------- 1. Selecionar
    print("\n  -- Selecionar")
    tecla("m"); tecla(" ")
    ok(ferr() == "selecionar", "Espaço volta para a Selecionar (vindo do Mover)")
    clicar_em(pt("l1"))
    ok(sel() == ["l1"], f"clique na linha seleciona ela: {sel()}")
    clicar_em(pt("l2"), SHIFT)
    ok(sel() == ["l1", "l2"], f"Shift+clique soma: {sel()}")
    clicar_em(pt("l1"), CTRL)
    ok(sel() == ["l2"], f"Ctrl+clique alterna (tira a l1): {sel()}")
    # o clique no vazio abre a janela, como no AutoCAD (usuário, 21/10); o Esc cancela a janela, o segundo limpa a seleção
    clicar_em([1500, 1200])
    ok(js("return !!c._janela;") and sel() == ["l2"], f"clique no vazio abre a janela e a seleção fica: {sel()}")
    tecla("Escape")
    ok(not js("return !!c._janela;") and sel() == ["l2"], f"Esc cancela a janela: {sel()}")
    tecla("Escape")
    ok(sel() == [], f"o segundo Esc limpa a seleção: {sel()}")
    # janela da esquerda para a direita: só o que está inteiro dentro
    arrastar(tela([-100, -100]), tela([1100, 300]))
    ok(sel() == ["l1"], f"janela da esquerda para a direita pega só o que está inteiro dentro (l1): {sel()}")
    arrastar(tela([1900, 1000]), tela([2100, -100]))
    ok(sel() == [], f"janela da esquerda para a direita sobre um pedaço da lv não pega nada: {sel()}")
    arrastar(tela([2100, 1000]), tela([1900, -100]))
    ok(sel() == ["lv"], f"o mesmo retângulo cruzando (da direita para a esquerda) pega a lv que ele toca: {sel()}")
    arrastar(tela([3380, 2380]), tela([3220, 2220]))
    ok(sel() == [], f"janela cruzando inteira DENTRO do círculo, sem tocar o traço, não pega o círculo: {sel()}")
    clicar_em(pt("lk"))
    ok(sel() == [], f"clique numa linha de camada travada não a seleciona: {sel()}")
    tecla("Escape")
    tecla("a", CTRL)
    todos = sel()
    ok(len(todos) >= 9, f"Ctrl+A seleciona tudo ({len(todos)})")
    tecla("Delete")
    sobrou = sorted(js("return [...c.doc.entidades.keys()];"))
    ok(sobrou == ["lk", "pk"], f"Del apaga a seleção e deixa o que está na camada travada: {sobrou}")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == len(ENTS), "Ctrl+Z devolve tudo num passo só")
    tecla("y", CTRL)
    ok(js("return c.doc.tamanho;") == 2, "Ctrl+Y apaga de novo")
    tecla("z", CTRL); esc()
    # alça arrastada até a outra linha (o snap da interseção com a continuação)
    clicar_em(pt("l1"))
    b = tela([1000, 0]); d = tela([2000, 0])
    arrastar(b, (d[0] + 3, d[1] + 2))
    ok(rnd(ent("l1")["b"]) == [2000, 0], f"arrastar a alça da ponta leva a ponta até a lv (snap): {ent('l1')['b']}")
    n = feitos(); tecla("z", CTRL)
    ok(rnd(ent("l1")["b"]) == [1000, 0] and feitos() == n - 1, "Ctrl+Z volta a ponta num passo")
    # alça presa por um clique e o comprimento digitado
    clicar_em(pt("l1")); clicar(*tela([1000, 0]))
    ok(js("return !!c.ferramenta.alca;"), "um clique na alça a prende ao cursor")
    mover(*tela([1300, 40]))
    digitar("1500")
    ok(rnd(ent("l1")["b"]) == [1500, 0] and not js("return !!c.ferramenta.alca;"), f"com a alça presa, 1500 e Enter dão o comprimento: {ent('l1')['b']}")
    tecla("z", CTRL)
    # Esc com a alça presa
    clicar_em(pt("l1")); clicar(*tela([1000, 0])); mover(*tela([1400, 300]))
    esc()
    ok(rnd(ent("l1")["b"]) == [1000, 0] and not js("return !!c.ferramenta.alca;") and ferr() == "selecionar" and not js("return c.tela.previa.length;"),
       "Esc com a alça presa solta a alça e não muda nada")
    # vértice da polilinha
    clicar_em(pt("rt"))
    arrastar(tela([1000, 2600]), tela([2000, 1500]))
    ok(rnd(ent("rt")["vertices"][2]) == [2000, 1500], f"alça do vértice da polilinha arrastada até a ponta da lv: {ent('rt')['vertices'][2]}")
    tecla("z", CTRL); esc()
    igual_ao_inicio("Selecionar")

    # ---------------------------------------------------------------- 2. Mover
    print("\n  -- Mover (M)")
    clicar_em(pt("l1")); tecla("m")
    ok(ferr() == "mover" and "base" in dica().lower(), f"M abre o Mover e pede o ponto base: {dica()!r}")
    clicar(*(lambda q: (q[0] + 4, q[1] - 3))(tela([0, 0])))
    ok(rnd(js("return c.ferramenta.base;") or [9, 9]) == [0, 0], f"o ponto base clicado 5 px ao lado da ponta pega a ponta (snap): {js('return c.ferramenta.base;')}")
    n = feitos()
    clicar(*(lambda q: (q[0] - 3, q[1] + 4))(tela([2000, -500])))
    ok(rnd(ent("l1")["a"]) == [2000, -500] and rnd(ent("l1")["b"]) == [3000, -500], f"o destino na ponta da lv: a l1 andou (2000, −500): {ent('l1')}")
    ok(feitos() == n + 1, "um comando só na pilha")
    tecla("z", CTRL)
    ok(rnd(ent("l1")["a"]) == [0, 0], "Ctrl+Z volta o Mover num passo")
    tecla("y", CTRL)
    ok(rnd(ent("l1")["a"]) == [2000, -500], "Ctrl+Y refaz")
    tecla("z", CTRL)
    ok(ferr() == "mover" and sel() == ["l1"], "continua no Mover com a seleção, pronto para outro")
    # distância digitada na direção do cursor
    clicar(*tela([0, 0])); mover(*tela([400, 0]))
    digitar("1500")
    ok(rnd(ent("l1")["a"]) == [1500, 0], f"1500 e Enter movem 1500 na direção do cursor: {ent('l1')['a']}")
    tecla("z", CTRL)
    # "1,5m": o "m" não pode virar o atalho do Mover (nem a vírgula sumir)
    clicar(*tela([0, 0])); mover(*tela([400, 0]))
    digitar("1,5m", enter=False)
    caixa = js("return c.el.medida.value;")
    tecla("Enter"); aba.drenar(0.2)
    ok(caixa == "1,5m" and rnd(ent("l1")["a"]) == [1500, 0], f"1,5m digitado logo depois do clique fica na caixa ({caixa!r}) e move 1500: {ent('l1')['a']}")
    tecla("z", CTRL)
    # ângulo junto: 1000@90
    clicar(*tela([0, 0])); mover(*tela([400, 0]))
    digitar("1000@90")
    ok(rnd(ent("l1")["a"]) == [0, 1000], f"1000@90 move 1000 para cima: {ent('l1')['a']}")
    if rnd(ent("l1")["a"]) != [0, 0]: tecla("z", CTRL)
    # o cursor quase na vertical (sem Shift): o Mover devia grudar na guia de 90° a partir da base, como a Linha faz
    if ferr() != "mover": esc(); clicar_em(pt("l1")); tecla("m")
    clicar(*tela([0, 0])); mover(*tela([30, 400])); digitar("1000")
    q = ent("l1")["a"]
    ok(abs(q[0]) < 0.01 and abs(q[1] - 1000) < 0.01, f"cursor quase na vertical e 1000: anda 1000 exatos para cima (guia de 0°/90° a partir da base): {q}")
    if rnd(q) != [0, 0]: tecla("z", CTRL)
    # dx;dy (como o "2000;1000" do retângulo)
    if ferr() != "mover": esc(); clicar_em(pt("l1")); tecla("m")
    clicar(*tela([0, 0])); mover(*tela([400, 0]))
    n = feitos()
    digitar("500;300")
    ok(rnd(ent("l1")["a"]) == [500, 300], f"500;300 move 500 em x e 300 em y: {ent('l1')['a']}")
    ok(feitos() != n or dica() and "não" in dica().lower(), f"ou, se não aceita dx;dy, avisa que não entendeu (dica: {dica()!r})")
    if feitos() != n: tecla("z", CTRL)
    # Esc no meio
    esc(); clicar_em(pt("l1")); tecla("m")
    n = feitos()
    clicar(*tela([0, 0])); mover(*tela([700, 900]))
    ok(js("return c.tela.previa.length;") > 0, "com o ponto base, a prévia acompanha o cursor")
    esc()
    ok(feitos() == n and rnd(ent("l1")["a"]) == [0, 0] and ferr() == "selecionar" and not js("return c.tela.previa.length;"),
       "Esc no meio do Mover: nada muda, a prévia some e volta para a Selecionar")
    # Esc com a medida já digitada na caixa (sem Enter)
    clicar_em(pt("l1")); tecla("m"); n = feitos()
    clicar(*tela([0, 0])); mover(*tela([400, 0])); digitar("15", enter=False)
    esc()
    ok(feitos() == n and rnd(ent("l1")["a"]) == [0, 0] and ferr() == "selecionar" and not js("return c.el.medida.value;")
       and js("return document.activeElement !== c.el.medida;"), "Esc com \"15\" na caixa MEDIDAS: nada muda, a caixa limpa e solta o foco")
    # sem seleção
    tecla("m")
    ok("selecione" in dica().lower(), f"M sem seleção pede para selecionar: {dica()!r}")
    arrastar(tela([-100, -100]), tela([1100, 700]))
    ok(sel() == ["l1", "l2"], f"no Mover sem seleção, a janela (a dica diz \"clique ou janela\") seleciona as duas linhas: {sel()}")
    esc(); tecla("m")
    clicar_em(pt("l2"))
    ok(sel() == ["l2"] and js("return c.ferramenta.base;") is None, "o primeiro clique seleciona a l2 (não é o ponto base)")
    clicar(*tela([0, 600])); clicar(*tela([2000, 1500]))
    ok(rnd(ent("l2")["a"]) == [2000, 1500], f"e depois base e destino movem a l2: {ent('l2')['a']}")
    tecla("z", CTRL); esc()
    # cópia com um toque no Ctrl
    clicar_em(pt("l1")); tecla("m"); clicar(*tela([0, 0]))
    toque_ctrl()
    ok(js("return c.ferramenta.modoCopia;") is True and "cópia" in dica(), f"um toque no Ctrl liga a cópia: {dica()!r}")
    n = feitos(); antes = js("return c.doc.tamanho;")
    clicar(*tela([2000, -500]))
    ok(js("return c.doc.tamanho;") == antes + 1 and rnd(ent("l1")["a"]) == [0, 0] and feitos() == n + 1,
       "o destino cria a cópia e o original fica (um comando)")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == antes, "Ctrl+Z tira a cópia num passo")
    esc()
    # camada travada (Ctrl+A pega também o travado)
    tecla("a", CTRL); tecla("m"); clicar(*tela([0, 0])); clicar(*tela([0, 600]))
    ok(rnd(ent("lk")["a"]) == [0, 4200] and rnd(ent("pk")["vertices"][0]) == [2000, 4200] and rnd(ent("l1")["a"]) == [0, 600],
       "Ctrl+A e Mover: tudo anda, menos o que está na camada travada")
    tecla("z", CTRL); esc()
    igual_ao_inicio("Mover")

    # ---------------------------------------------------------------- 3. Copiar
    print("\n  -- Copiar (O)")
    clicar_em(pt("l1")); tecla("o")
    ok(ferr() == "copiar", "O abre o Copiar")
    antes = js("return c.doc.tamanho;"); n = feitos()
    clicar(*tela([0, 0])); clicar(*tela([2000, -500]))
    mover(*tela([30, 400]), SHIFT)                     # Shift: orto (o cursor solto não dá 90° exatos)
    digitar("1000")
    novas = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'linha' && !['l1','l2','lv','lk'].includes(e.id)).map(e => [e.a, e.b]);")
    novas = [[rnd(q) for q in par] for par in (novas or [])]
    ok(js("return c.doc.tamanho;") == antes + 2 and sorted(novas) == [[[0, 1000], [1000, 1000]], [[2000, -500], [3000, -500]]] and rnd(ent("l1")["a"]) == [0, 0],
       f"cópia múltipla: um destino clicado e outro digitado (1000 para cima), do mesmo ponto base: {novas}")
    ok(ferr() == "copiar", "o Copiar continua esperando o próximo destino")
    esc()
    ok(ferr() == "selecionar", "Esc termina o Copiar")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == antes + 1, "Ctrl+Z tira a última cópia")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == antes and feitos() == n, "outro Ctrl+Z tira a primeira")
    tecla("a", CTRL); tecla("o"); clicar(*tela([0, 0])); clicar(*tela([0, 600]))
    copias_trav = js("return [...c.doc.entidades.values()].filter(e => e.camada === 'TRAVADA').length;")
    ok(copias_trav == 2, f"Ctrl+A e Copiar: não cria cópia do que está na camada travada (objetos na TRAVADA: {copias_trav}, eram 2)")
    esc(); desfazer_tudo()
    igual_ao_inicio("Copiar")

    # ---------------------------------------------------------------- 4. Girar
    print("\n  -- Girar (Q)")
    clicar_em(pt("l1")); tecla("q")
    ok(ferr() == "girar" and "centro" in dica().lower(), f"Q abre o Girar e pede o centro: {dica()!r}")
    clicar(*(lambda q: (q[0] + 4, q[1] + 3))(tela([0, 0])))
    ok(rnd(js("return c.ferramenta.base;") or [9, 9]) == [0, 0], "o centro pega a ponta da linha (snap)")
    n = feitos()
    digitar("90")
    e1 = ent("l1")
    ok(rnd(e1["a"]) == [0, 0] and [round(v) for v in e1["b"]] == [0, 1000] and feitos() == n + 1, f"90 e Enter giram 90° em volta do centro: {e1['b']}")
    tecla("z", CTRL)
    ok(rnd(ent("l1")["b"]) == [1000, 0], "Ctrl+Z volta num passo")
    clicar(*tela([0, 0])); digitar("-90")
    ok([round(v) for v in ent("l1")["b"]] == [0, -1000], f"−90 gira para baixo: {ent('l1')['b']}")
    tecla("z", CTRL)
    # pelo mouse: centro, referência e o novo ângulo na ponta da l2
    clicar(*tela([0, 0])); clicar(*tela([1000, 0])); mover(*tela([200, 500])); clicar(*tela([0, 600]))
    ok([round(v) for v in ent("l1")["b"]] == [0, 1000], f"pelo mouse (centro, referência na ponta, ângulo na ponta da l2): {ent('l1')['b']}")
    tecla("z", CTRL)
    # cópia
    antes = js("return c.doc.tamanho;")
    clicar(*tela([0, 0])); toque_ctrl(); digitar("45")
    ok(js("return c.doc.tamanho;") == antes + 1 and rnd(ent("l1")["b"]) == [1000, 0], "toque no Ctrl e 45: gira uma cópia, o original fica")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == antes, "Ctrl+Z tira a cópia girada")
    # Esc no meio
    esc(); clicar_em(pt("l1")); tecla("q"); n = feitos()
    clicar(*tela([0, 0])); clicar(*tela([1000, 0])); mover(*tela([600, 700]))
    esc()
    ok(feitos() == n and rnd(ent("l1")["b"]) == [1000, 0] and ferr() == "selecionar", "Esc no meio do Girar: nada muda e volta para a Selecionar")
    tecla("q")
    ok("selecione" in dica().lower(), f"Q sem seleção pede para selecionar: {dica()!r}")
    esc()
    igual_ao_inicio("Girar")

    # ---------------------------------------------------------------- 5. Escala
    print("\n  -- Escala (botão da barra)")
    botao = js("const b = document.querySelector('[data-ferramenta=escalar]'); if (!b) return null; b.scrollIntoView({ block: 'nearest' }); const r = b.getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2), b.offsetParent !== null];")
    ok(botao and botao[2], f"o botão da Escala está na barra: {botao}")
    sem_atalho = js("return !c.ferramentas.get('escalar').constructor.atalho;")

    def abrir_escala():
        x, y = botao[0], botao[1]
        mover(x, y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.2)
    print(f"     (a Escala não tem atalho de teclado: {sem_atalho})")
    clicar_em(pt("rt")); abrir_escala()
    ok(ferr() == "escalar", "o botão abre a Escala")
    clicar(*(lambda q: (q[0] + 3, q[1] - 4))(tela([0, 2000])))
    n = feitos()
    digitar("2")
    ok([rnd(v) for v in ent("rt")["vertices"]] == [[0, 2000], [2000, 2000], [2000, 3200], [0, 3200]] and feitos() == n + 1,
       f"base na ponta (snap) e 2 e Enter dobram em volta dela: {ent('rt')['vertices']}")
    tecla("z", CTRL)
    ok([rnd(v) for v in ent("rt")["vertices"]] == INICIO["rt"]["vertices"], "Ctrl+Z volta num passo")
    # o fator sem o ponto base: em volta do centro
    esc(); clicar_em(pt("rt")); abrir_escala()
    digitar("0,5")
    ok([rnd(v) for v in ent("rt")["vertices"]] == [[250, 2150], [750, 2150], [750, 2450], [250, 2450]], f"0,5 sem ponto base: em volta do centro: {ent('rt')['vertices']}")
    tecla("z", CTRL)
    # por referência: base, R, dois pontos (1000) e a medida nova
    esc(); clicar_em(pt("rt")); abrir_escala()
    clicar(*tela([0, 2000])); tecla("r")
    ok(ferr() == "escalar" and "refer" in dica().lower(), f"R liga a referência (não abre o Retângulo): {ferr()} {dica()!r}")
    clicar(*tela([0, 2000])); clicar(*tela([1000, 2000]))
    digitar("2500")
    ok([rnd(v) for v in ent("rt")["vertices"]][1] == [2500, 2000], f"referência 1000 → 2500: fator 2,5: {ent('rt')['vertices']}")
    tecla("z", CTRL)
    # Esc no meio
    esc(); clicar_em(pt("rt")); abrir_escala(); n = feitos()
    clicar(*tela([0, 2000])); mover(*tela([800, 2900]))
    esc()
    ok(feitos() == n and ferr() == "selecionar", "Esc no meio da Escala: nada muda")
    abrir_escala()
    ok("selecione" in dica().lower(), f"Escala sem seleção pede para selecionar: {dica()!r}")
    esc()
    igual_ao_inicio("Escala")

    # ---------------------------------------------------------------- 6. Espelhar
    print("\n  -- Espelhar (I)")
    clicar_em(pt("po")); tecla("i")
    ok(ferr() == "espelhar", "I abre o Espelhar")
    n = feitos(); antes = js("return c.doc.tamanho;")
    clicar(*(lambda q: (q[0] + 4, q[1] + 3))(tela([2000, -500]))); clicar(*(lambda q: (q[0] - 3, q[1] - 4))(tela([2000, 1500])))
    esp = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && !['rt','po','pk'].includes(e.id)).map(e => e.vertices);")
    ok(esp and [rnd(v) for v in esp[0]] == [[1000, 0], [400, 0], [400, 600]] and js("return c.doc.tamanho;") == antes + 1 and feitos() == n + 1,
       f"eixo pelas pontas da lv (snap): a cópia espelhada, o original fica: {esp}")
    tecla("z", CTRL)
    ok(js("return c.doc.tamanho;") == antes, "Ctrl+Z tira o espelhado num passo")
    esc(); clicar_em(pt("po")); tecla("i"); clicar(*tela([2000, -500])); mover(*tela([2400, 1200]))
    esc()
    ok(js("return c.doc.tamanho;") == antes and ferr() == "selecionar", "Esc depois do primeiro ponto do eixo: nada muda")
    tecla("a", CTRL); tecla("i"); clicar(*tela([2000, -500])); clicar(*tela([2000, 1500]))
    trav = js("return [...c.doc.entidades.values()].filter(e => e.camada === 'TRAVADA').length;")
    ok(trav == 2, f"Ctrl+A e Espelhar: o que está na camada travada não é espelhado (objetos na TRAVADA: {trav}, eram 2)")
    esc(); desfazer_tudo()
    igual_ao_inicio("Espelhar")

    # ---------------------------------------------------------------- 7. Copiar propriedades
    print("\n  -- Copiar propriedades (M, A)")
    clicar_em(pt("tx")); ok(sel() == ["tx"], f"selecionado o texto de origem: {sel()}")
    tecla("m"); tecla("a")
    ok(ferr() == "copiar_propriedades" and dica().startswith("Origem: texto na camada TEXTO"), f"M e logo depois A abrem o Copiar propriedades com a origem: {dica()!r}")
    n = feitos()
    clicar_em(pt("t2"))
    e2 = ent("t2")
    ok(e2["altura"] == 5 and e2["camada"] == "TEXTO" and e2["texto"] == "ALVO" and feitos() == n + 1, f"clique no outro texto: altura e camada copiadas: {e2['altura']} {e2['camada']}")
    clicar_em(pt("lk"))
    ok(ent("lk")["camada"] == "TRAVADA", "clicar na linha travada não a muda")
    tecla("z", CTRL)
    ok(ent("t2")["altura"] == 2 and ent("t2")["camada"] == "NOTAS", "Ctrl+Z volta num passo")
    esc()
    ok(ferr() == "selecionar", "Esc termina")
    tecla("m"); tecla("a")
    ok(ferr() == "copiar_propriedades" and "origem" in dica().lower(), f"sem seleção pede a origem: {dica()!r}")
    clicar_em(pt("tx")); clicar_em(pt("t2"))
    ok(ent("t2")["altura"] == 5, "origem e destino clicados")
    tecla("z", CTRL); esc()
    igual_ao_inicio("Copiar propriedades")

    # ---------------------------------------------------------------- 8. Apagar
    print("\n  -- Apagar (E)")
    clicar_em(pt("l1")); tecla("e")
    ok(ent("l1") is None, "selecionada e E: apaga")
    tecla("z", CTRL)
    ok(ent("l1") is not None, "Ctrl+Z volta")
    esc(); tecla("e")
    ok(ferr() == "apagar", "E sem seleção abre o Apagar")
    clicar_em(pt("l2"))
    ok(ent("l2") is None and ferr() == "apagar", "clique apaga a l2 e continua no Apagar")
    clicar_em(pt("lk"))
    ok(ent("lk") is not None, "clique na travada não apaga")
    tecla("z", CTRL); esc()
    ok(ferr() == "selecionar", "Esc solta o Apagar")
    tecla("a", CTRL); tecla("e")
    sobrou = sorted(js("return [...c.doc.entidades.keys()];"))
    ok(sobrou == ["lk", "pk"], f"Ctrl+A e E: fica só a camada travada: {sobrou}")
    tecla("z", CTRL); esc()
    igual_ao_inicio("Apagar")

    # ---------------------------------------------------------------- 9. Explodir e Juntar
    print("\n  -- Explodir (B) e Juntar (W)")
    clicar_em(pt("rt")); n = feitos(); tecla("b")
    linhas = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'linha' && !['l1','l2','lv','lk'].includes(e.id)).length;")
    ok(ent("rt") is None and linhas == 4 and feitos() == n + 1, f"selecionado o retângulo e B: 4 linhas soltas, num comando: {linhas}")
    ok("solta" in dica().lower(), f"e a dica diz o que aconteceu (\"4 linha(s) soltas · Juntar (W) volta\"): {dica()!r}")
    ok(len(sel()) == 4, f"as 4 linhas ficam selecionadas: {len(sel())}")
    tecla("w")
    pls = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && !['po','pk'].includes(e.id)).map(e => ({ v: e.vertices, f: e.fechada, c: e.camada }));")
    ok(pls and len(pls) == 1 and [rnd(v) for v in pls[0]["v"]] == INICIO["rt"]["vertices"] and pls[0]["f"] is True and pls[0]["c"] == "VISTA",
       f"W junta de volta: a mesma polilinha fechada, mesmos vértices na mesma ordem: {pls}")
    ok(ferr() == "selecionar", "e volta para a Selecionar")
    tecla("z", CTRL)
    ok(js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'linha').length;") == 8, "Ctrl+Z desfaz o Juntar num passo (as 4 linhas)")
    tecla("z", CTRL)
    ok(ent("rt") is not None, "outro Ctrl+Z desfaz o Explodir (o retângulo)")
    esc()
    # sem seleção: B e clique; W, cliques e Enter
    tecla("b"); ok(ferr() == "explodir", "B sem seleção abre o Explodir")
    clicar_em(pt("po"))
    ok(ent("po") is None, "clique na polilinha aberta explode")
    esc()
    soltas = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'linha' && !['l1','l2','lv','lk'].includes(e.id)).map(e => [e.a, e.b]);")
    tecla("w"); ok(ferr() == "juntar", "W sem seleção abre o Juntar")
    for s in soltas:
        clicar_em([(s[0][0] + s[1][0]) / 2 + (s[1][0] - s[0][0]) * 0.2, (s[0][1] + s[1][1]) / 2 + (s[1][1] - s[0][1]) * 0.2])
    ok(len(sel()) == 2, f"os cliques no Juntar somam à seleção: {len(sel())}")
    tecla("Enter")
    pls = js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && !['rt','pk'].includes(e.id)).map(e => ({ v: e.vertices, f: e.fechada }));")
    ok(pls and len(pls) == 1 and [rnd(v) for v in pls[0]["v"]] == INICIO["po"]["vertices"] and not pls[0]["f"], f"Enter junta: a polilinha aberta de volta: {pls}")
    esc(); desfazer_tudo()
    # o que não explode avisa
    clicar_em(pt("ci")); tecla("b")
    ok("nada" in dica().lower(), f"círculo selecionado e B: avisa que não há o que explodir: {dica()!r}")
    esc()
    # duas linhas que não se tocam: o Juntar avisa
    # longe da cota "ct", que passa por cima do ponto de sempre da l2
    clicar_em([800, 0]); clicar_em([800, 600], SHIFT)
    ok(sorted(sel()) == ["l1", "l2"], f"as duas linhas soltas selecionadas: {sel()}")
    tecla("w")
    ok("nenhuma" in dica().lower() or "nada" in dica().lower(), f"duas linhas que não se tocam e W: avisa: {dica()!r}")
    esc()
    # Ctrl+A e B: o travado fica como está e não ganha linhas
    tecla("a", CTRL); tecla("b")
    trav = js("return [...c.doc.entidades.values()].filter(e => e.camada === 'TRAVADA').map(e => e.id + ':' + e.tipo).sort();")
    ok(trav == ["lk:linha", "pk:polilinha"], f"Ctrl+A e B: a polilinha travada não explode nem ganha cópia em linhas: {trav}")
    esc(); desfazer_tudo()
    igual_ao_inicio("Explodir/Juntar")

    # ---------------------------------------------------------------- 10. Esticar
    print("\n  -- Esticar (S)")
    tecla("s"); ok(ferr() == "esticar", "S abre o Esticar")
    clicar_em([1000, 2300]); n = feitos()
    ok(js("return !!c.ferramenta.dentro && !!c.ferramenta.base;"), "clique na aresta da direita do retângulo: pega a aresta")
    mover(*tela([1300, 2300]))
    digitar("500")
    v = [rnd(q) for q in ent("rt")["vertices"]]
    ok(v == [[0, 2000], [1500, 2000], [1500, 2600], [0, 2600]] and feitos() == n + 1, f"500 e Enter: a aresta anda 500 para o lado do cursor: {v}")
    tecla("z", CTRL)
    ok([rnd(q) for q in ent("rt")["vertices"]] == INICIO["rt"]["vertices"], "Ctrl+Z volta num passo")
    ok(ferr() == "esticar", "continua no Esticar")
    # "50cm": o "c" e o "m" não abrem Círculo/Mover
    clicar_em([1000, 2300]); mover(*tela([1300, 2300]))
    digitar("50cm")
    v = [rnd(q) for q in ent("rt")["vertices"]]
    ok(v[1] == [1500, 2000] and ferr() == "esticar", f"50cm logo depois do clique: estica 500 e não troca de ferramenta: {v[1]} {ferr()}")
    tecla("z", CTRL)
    # pelo mouse: até a ponta da lv (a aresta anda só na perpendicular dela)
    clicar_em([1000, 2300]); clicar(*tela([2000, 1500]))
    v = [rnd(q) for q in ent("rt")["vertices"]]
    ok(v == [[0, 2000], [2000, 2000], [2000, 2600], [0, 2600]], f"destino clicado na ponta da lv: a aresta anda só em x, até 2000: {v}")
    tecla("z", CTRL)
    # janela cruzando sobre a metade da direita, ponto base e a distância digitada (Shift: orto)
    arrastar(tela([1200, 2700]), tela([700, 1900]))
    ok(js("return !!c.ferramenta.dentro && !c.ferramenta.base;") and "base" in dica().lower(), f"janela no Esticar: pede o ponto base: {dica()!r}")
    clicar(*tela([1000, 2000]))
    mover(*tela([1400, 2010]), SHIFT)
    digitar("300")
    v = [rnd(q) for q in ent("rt")["vertices"]]
    ok(v == [[0, 2000], [1300, 2000], [1300, 2600], [0, 2600]], f"janela + base + 300: os vértices dentro da janela andam 300: {v}")
    tecla("z", CTRL)
    # Esc no meio
    n = feitos()
    clicar_em([1000, 2300]); mover(*tela([1600, 2300]))
    esc()
    ok(feitos() == n and [rnd(q) for q in ent("rt")["vertices"]] == INICIO["rt"]["vertices"] and ferr() == "selecionar" and not js("return c.tela.previa.length;"),
       "Esc no meio do Esticar: nada muda e volta para a Selecionar")
    # a janela sobre a ponta da linha travada não a estica
    tecla("s"); arrastar(tela([1100, 4300]), tela([900, 4100])); clicar(*tela([1000, 4200])); mover(*tela([1400, 4205]), SHIFT); digitar("400")
    ok(rnd(ent("lk")["b"]) == [1000, 4200], f"a ponta da linha travada dentro da janela não estica: {ent('lk')['b']}")
    esc(); desfazer_tudo()
    igual_ao_inicio("Esticar")

    # ---------------------------------------------------------------- 11. atalhos
    print("\n  -- Atalhos")
    esc()
    for k, fid in (("m", "mover"), ("o", "copiar"), ("q", "girar"), ("i", "espelhar"), ("e", "apagar"), ("b", "explodir"), ("w", "juntar"), ("s", "esticar")):
        esc(); tecla(k)
        ok(ferr() == fid, f"{k.upper()} abre {fid} ({ferr()})")
    esc()
    igual_ao_inicio("atalhos")

    erros = [x for x in aba.console if x[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
    aba.ws.close()
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print(f"\nOK: {len(oks)}")
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
