# -*- coding: utf-8 -*-
"""Edição geométrica, medição, snap e navegação do CAD 2D (15/10/2026), só com o mouse e o teclado de verdade (CDP).

O desenho de partida é gravado no .desenho.json antes de abrir: linhas que se cruzam, linhas que não chegam numa outra,
um arco, um círculo, polilinhas aberta e fechada, cada assunto numa região do papel (10 m uma da outra). O teste:

- atalhos: TR (Aparar, com o T sozinho sendo o Texto), N, K, F, U, Y, e com o Caps Lock ligado;
- Aparar: o trecho entre duas interseções, a ponta solta, o clique a poucos px do corte (o lado clicado é o que sai),
  numa polilinha, num círculo e num arco; Ctrl+Z desfaz num passo;
- Estender até a linha de fronteira, e sem fronteira (aviso, nada muda);
- Concordar com raio digitado (100) e com raio 0 (canto vivo); Ctrl+Z desfaz num passo;
- Offset com a distância digitada antes e depois do clique ("15cm": o "c" e o "m" não viram atalho), o lado pelo clique,
  em linha, arco, círculo, polilinha aberta e fechada;
- Medir dois pontos (o valor do aviso e o da caixa MEDIDAS);
- Corte: marcar a linha (sem vista do modelo não gera o 3D: só o aviso); Ctrl+Z tira a marca inteira;
- snap: extremidade, meio, interseção, centro, perpendicular e orto (Shift) com o mouse a poucos px, com o zoom bem
  longe e bem perto (a roda mantém o ponto sob o cursor);
- navegação: arrastar com o botão do meio e com o direito, Z enquadra, duplo clique do meio enquadra;
- Esc no meio cancela e solta (também com o campo MEDIDAS com texto).

O enquadramento de cada região é posto por JS (c.tela.enquadrar) — é só a vista; a entrada é sempre mouse e teclado.
As verificações que hoje falham ficam: são os defeitos, e servem de teste da correção.

Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_fluxo_geometria.py
"""
import json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cadgeo_")
PASTA = os.path.join(DADOS, "geo")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def L(i, a, b): return {"id": i, "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": a, "b": b}
def PL(i, vs, f=False): return {"id": i, "tipo": "polilinha", "camada": "VISTA", "atributos": {}, "vertices": vs, "fechada": f}
def CI(i, c, r): return {"id": i, "tipo": "circulo", "camada": "VISTA", "atributos": {}, "centro": c, "raio": r}
def AR(i, c, r, a0, a1): return {"id": i, "tipo": "arco", "camada": "VISTA", "atributos": {}, "centro": c, "raio": r, "inicio": a0, "fim": a1}


# cada região começa em x = 10000·k; tudo fica entre y −1000 e +1500, menos a linha sem fronteira (y −3000)
X = {k: 10000 * k for k in range(12)}
ents = [
    # R0 Aparar entre duas interseções; a ponta solta
    L("h1", [0, 0], [1000, 0]), L("v1", [300, -300], [300, 300]), L("v2", [700, -300], [700, 300]),
    L("h2", [0, 600], [1000, 600]), L("v3", [600, 400], [600, 800]),
    # R1 Aparar numa polilinha e num círculo
    PL("p1", [[X[1], 0], [X[1] + 1000, 0], [X[1] + 1000, 600]]), L("vp", [X[1] + 500, -300], [X[1] + 500, 300]),
    CI("ci", [X[1] + 2000, 300], 300), L("lc", [X[1] + 1500, 300], [X[1] + 2500, 300]),
    # R2 Aparar num arco
    AR("a1", [X[2] + 500, 0], 400, 0, 180), L("la", [X[2] + 500, -100], [X[2] + 500, 600]),
    # R3 Estender: até a fronteira; sem fronteira
    L("e1", [X[3], 0], [X[3] + 400, 0]), L("fr", [X[3] + 1000, -300], [X[3] + 1000, 300]),
    L("e2", [X[3], -3000], [X[3] + 400, -3000]),
    # R4 Concordar R 100; R5 Concordar R 0
    L("c1", [X[4], 0], [X[4] + 800, 0]), L("c2", [X[4] + 1000, 200], [X[4] + 1000, 1000]),
    L("c3", [X[5], 0], [X[5] + 800, 0]), L("c4", [X[5] + 1000, 200], [X[5] + 1000, 1000]),
    # R6 Offset: linha, arco, círculo
    L("o1", [X[6], 0], [X[6] + 1000, 0]), AR("o2", [X[6] + 2000, 0], 300, 0, 180), CI("o3", [X[6] + 3000, 300], 300),
    # R7 Offset: polilinha aberta e fechada
    PL("o4", [[X[7], 0], [X[7] + 1000, 0], [X[7] + 1000, 600]]),
    PL("o5", [[X[7] + 2000, 0], [X[7] + 3000, 0], [X[7] + 3000, 500], [X[7] + 2000, 500]], True),
    # R8 Medir
    L("m1", [X[8], 0], [X[8] + 1200, 500]),
    # R10 snap: s1 × s2 em (300, 0); o meio de s2 em (300, 100); o círculo
    L("s1", [X[10], 0], [X[10] + 1000, 0]), L("s2", [X[10] + 300, -400], [X[10] + 300, 600]), CI("s3", [X[10] + 2000, 0], 200),
    # R11 Estender um arco até uma linha; Concordar R 0 em duas linhas que se cruzam (fica o lado clicado de cada uma)
    AR("ea", [X[11] + 500, 0], 300, 0, 90), L("ex", [X[11] + 300, 0], [X[11] + 300, 600]),
    L("kx1", [X[11] + 1000, 0], [X[11] + 2000, 0]), L("kx2", [X[11] + 1500, -500], [X[11] + 1500, 500]),
]
REGIAO = {0: [[-100, -400], [1100, 900]], 1: [[X[1] - 100, -400], [X[1] + 2600, 700]], 2: [[X[2] - 100, -300], [X[2] + 1100, 700]],
          3: [[X[3] - 100, -3300], [X[3] + 1100, 400]], 4: [[X[4] - 100, -200], [X[4] + 1200, 1100]], 5: [[X[5] - 100, -200], [X[5] + 1200, 1100]],
          6: [[X[6] - 200, -500], [X[6] + 3500, 900]], 7: [[X[7] - 400, -400], [X[7] + 3400, 1000]], 8: [[X[8] - 200, -200], [X[8] + 1400, 700]],
          9: [[X[9] - 200, -200], [X[9] + 1200, 600]], 10: [[X[10] - 200, -500], [X[10] + 2400, 700]],
          11: [[X[11] - 100, -600], [X[11] + 2100, 700]]}

json.dump({"formato": 1, "nome": "Geo", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "geo", "unidade": "mm", "escala": 10, "camadas": {}, "entidades": ents, "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "geo.desenho.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadgeo_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
TECLAS = {"Enter": 13, "Escape": 27, "Control": 17, "Shift": 16, " ": 32, ",": 188, ".": 190, "-": 189}
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/cad?projeto=geo&desenho=geo", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar(f"document.body.dataset.pronto === '1' && !!window.cad && cad.doc.tamanho === {len(ents)}"):
        aba.drenar(0.5)
    aba.drenar(1.5)                     # a tela assenta (painéis, primeiro quadro)
    aba.console.clear()
    # aba.drenar espera no mínimo ~1 s quando não chega mensagem (o recv tem timeout de 1 s): entre teclas e cliques o
    # tempo de uma pessoa é o time.sleep; as mensagens do console são recolhidas pelos próprios comandos seguintes
    pausa = time.sleep

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    ok(js("return c.doc.tamanho;") == len(ents), f"desenho aberto com os {len(ents)} objetos")

    def ver(k):
        """Enquadra a região k (só a vista) e espera o quadro."""
        js(f"c.tela.enquadrar({json.dumps(REGIAO[k])}); return 1;"); pausa(0.3)

    def tela(p):
        return js(f"const t = c.tela.paraTela({json.dumps(p)}), r = c.el.canvas.getBoundingClientRect(); return [r.left + t[0], r.top + t[1]];")

    def mover(x, y, mods=0, botoes=0, botao="none"):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, modifiers=mods, buttons=botoes, button=botao); pausa(0.06)

    def clicar(x, y, mods=0):
        mover(x, y, mods)
        sobre = aba.avaliar(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e === cad.el.canvas ? '' : (e ? (e.id || e.className || e.tagName) : 'nada'); }})()")
        if sobre: print(f"     (o clique em {x:.0f},{y:.0f} caiu em cima de: {sobre})")
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1, modifiers=mods)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0, modifiers=mods)
        pausa(0.2)

    def clicar_mm(p, dx=0, dy=0, mods=0):
        x, y = tela(p); clicar(x + dx, y + dy, mods)

    def mover_mm(p, dx=0, dy=0, mods=0):
        x, y = tela(p); mover(x + dx, y + dy, mods)

    def tecla(k, mods=0, espera=0.12):
        code = TECLAS.get(k, ord(k.upper()) if len(k) == 1 else 0)
        texto = k if (len(k) == 1 and not (mods & 2)) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=("Key" + k.upper()) if k.isalpha() and len(k) == 1 else "",
                windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, windowsVirtualKeyCode=code, modifiers=mods)
        pausa(espera)

    def digitar(t, enter=True):
        """Tecla por tecla, como a pessoa: o primeiro número foca a caixa MEDIDAS e o resto entra nela."""
        for ch in t: tecla(ch, espera=0.03)
        valor = js("return c.el.medida.value;")
        if enter: tecla("Enter", espera=0.25)
        return valor

    def esc(): tecla("Escape", espera=0.2)
    def ferr(): return js("return c.ferramenta.constructor.id;")
    def ent(i): return js(f"const e = c.doc.get('{i}'); return e || null;")
    def na_regiao(k, tipo=None):
        (x0, y0), (x1, y1) = REGIAO[k]
        return js(f"""return [...c.doc.entidades.values()].filter(e => {('e.tipo === ' + json.dumps(tipo) + ' &&') if tipo else ''}
                   (() => {{ const b = c.doc.caixaDa(e); return b && b[0][0] >= {x0 - 1} && b[1][0] <= {x1 + 1} && b[0][1] >= {y0 - 1} && b[1][1] <= {y1 + 1}; }})());""")
    def seg(e): return sorted([tuple(round(v, 1) for v in e["a"]), tuple(round(v, 1) for v in e["b"])])
    def aviso_txt(): return js("return [...c.el.avisos.querySelectorAll('.aviso')].map(a => a.textContent).join(' | ');")
    def limpar_avisos(): js("c.el.avisos.innerHTML = ''; return 1;")
    def total(): return js("return c.doc.tamanho;")

    # ------------------------------------------------------------------ 0. atalhos
    ver(0)
    tecla("t")
    ok(ferr() == "texto", f"T sozinho abre o Texto ({ferr()})")
    tecla("r")
    ok(ferr() == "aparar", f"T e logo depois R abrem o Aparar (TR) ({ferr()})")
    esc()
    tecla("t"); pausa(1.2); tecla("r")
    ok(ferr() == "retangulo", f"T e R com mais de 1 s entre eles: o R é o Retângulo ({ferr()})")
    esc()
    for k, fid in (("n", "estender"), ("k", "concordar"), ("f", "offset"), ("u", "medir"), ("y", "corte")):
        tecla(k); ok(ferr() == fid, f"atalho {k.upper()} abre {fid} ({ferr()})"); esc()
    # Caps Lock ligado: a tecla chega maiúscula (sem Shift)
    tecla("K")
    ok(ferr() == "concordar", f"com o Caps Lock ligado, K também abre o Concordar ({ferr()})")
    esc()

    # ------------------------------------------------------------------ 1. Aparar
    ver(0)
    tecla("t"); tecla("r")
    n0 = total()
    clicar_mm([450, 0])
    hs = sorted(seg(e) for e in (na_regiao(0, "linha") or []) if abs(e["a"][1]) < 1e-6 and abs(e["b"][1]) < 1e-6)
    ok(hs == [[(0.0, 0.0), (300.0, 0.0)], [(700.0, 0.0), (1000.0, 0.0)]] and ent("h1") is None,
       f"Aparar: o trecho entre as duas interseções sai, ficam 0–300 e 700–1000 ({hs})")
    tecla("z", mods=2, espera=0.3)
    h1 = ent("h1")
    ok(h1 and seg(h1) == [(0.0, 0.0), (1000.0, 0.0)] and total() == n0, f"um Ctrl+Z volta a linha inteira (h1 {h1 and seg(h1)}, {total()} objetos, eram {n0})")
    ok(ferr() == "aparar", "depois do Ctrl+Z o Aparar continua ativo")
    # o clique 5 px à direita do corte em x = 300 (dentro do raio do snap): o trecho clicado (300–700) é o que sai
    x300, y0_ = tela([300, 0])
    clicar(x300 + 5, y0_)
    hs = sorted(seg(e) for e in (na_regiao(0, "linha") or []) if abs(e["a"][1]) < 1e-6 and abs(e["b"][1]) < 1e-6)
    ok(hs == [[(0.0, 0.0), (300.0, 0.0)], [(700.0, 0.0), (1000.0, 0.0)]],
       f"Aparar com o clique 5 px à direita da interseção: sai o trecho clicado (300–700), não o da esquerda ({hs})")
    tecla("z", mods=2, espera=0.3)
    # a ponta solta: h2 cruza v3 em x = 600; o clique em 850 tira 600–1000
    clicar_mm([850, 600])
    h2s = sorted(seg(e) for e in (na_regiao(0, "linha") or []) if abs(e["a"][1] - 600) < 1e-6 and abs(e["b"][1] - 600) < 1e-6)
    ok(h2s == [[(0.0, 600.0), (600.0, 600.0)]], f"Aparar a ponta solta: fica 0–600 ({h2s})")
    # polilinha: p1 cruza vp em x = X1 + 500; o clique no trecho da esquerda
    ver(1)
    clicar_mm([X[1] + 250, 0])
    pls = [e["vertices"] for e in (na_regiao(1, "polilinha") or [])]
    ok(pls == [[[X[1] + 500, 0], [X[1] + 1000, 0], [X[1] + 1000, 600]]],
       f"Aparar numa polilinha: o trecho até a interseção sai, o resto fica polilinha ({pls}; dica: {js('return c.el.dica.textContent;')})")
    # círculo: lc corta o círculo em (X1+1700, 300) e (X1+2300, 300); o clique no alto tira a metade de cima
    clicar_mm([X[1] + 2000 + 300 * math.cos(math.radians(60)), 300 + 300 * math.sin(math.radians(60))])
    arcs = [(round(e["inicio"]) % 360, round(e["fim"]) % 360, e["raio"]) for e in (na_regiao(1, "arco") or [])]
    ok(ent("ci") is None and arcs == [(180, 0, 300)],
       f"Aparar num círculo: sai a metade clicada, fica o arco de 180° a 360° ({arcs}, círculo {'sumiu' if ent('ci') is None else 'ficou'}; dica: {js('return c.el.dica.textContent;')})")
    # arco: la corta o arco no alto (90°); o clique a 45° tira 0–90
    ver(2)
    clicar_mm([X[2] + 500 + 400 * math.cos(math.radians(40)), 400 * math.sin(math.radians(40))])
    arcs = [(round(e["inicio"]) % 360, round(e["fim"]) % 360) for e in (na_regiao(2, "arco") or [])]
    ok(arcs == [(90, 180)], f"Aparar num arco: sai o trecho de 0° a 90°, fica 90°–180° ({arcs})")
    esc()

    # ------------------------------------------------------------------ 2. Estender
    ver(3)
    tecla("n")
    clicar_mm([X[3] + 370, 0])
    e1 = ent("e1")
    ok(e1 and seg(e1) == [(X[3], 0.0), (X[3] + 1000.0, 0.0)], f"Estender: a linha vai até a fronteira em x = 1000 ({e1 and seg(e1)})")
    n0 = total(); e2a = ent("e2")
    clicar_mm([X[3] + 370, -3000])
    dica = js("return c.el.dica.textContent;")
    ok(ent("e2") == e2a and total() == n0 and "Nada" in (dica or ""), f"Estender sem fronteira: avisa e nada muda (dica: {dica})")
    tecla("z", mods=2, espera=0.3)
    ok(seg(ent("e1")) == [(X[3], 0.0), (X[3] + 400.0, 0.0)], "Ctrl+Z volta a linha estendida")
    esc()

    # ------------------------------------------------------------------ 3. Concordar
    ver(4)
    tecla("k")
    v = digitar("100")
    ok(v == "100" and ferr() == "concordar", f"Concordar: o 100 digitado vai para MEDIDAS e não vira atalho (campo '{v}', ferramenta {ferr()})")
    ok("100" in (js("return c.el.dica.textContent;") or ""), f"a dica mostra o raio 100 ({js('return c.el.dica.textContent;')})")
    n0 = total()
    clicar_mm([X[4] + 400, 0]); clicar_mm([X[4] + 1000, 650])
    c1, c2 = ent("c1"), ent("c2")
    arcs = [(e["centro"], e["raio"], round(e["inicio"]) % 360, round(e["fim"]) % 360) for e in (na_regiao(4, "arco") or [])]
    ok(c1 and c2 and seg(c1) == [(X[4], 0.0), (X[4] + 900.0, 0.0)] and seg(c2) == [(X[4] + 1000.0, 100.0), (X[4] + 1000.0, 1000.0)]
       and len(arcs) == 1 and [round(v_) for v_ in arcs[0][0]] == [X[4] + 900, 100] and abs(arcs[0][1] - 100) < 1e-6 and arcs[0][2:] == (270, 0),
       f"Concordar R 100: as linhas param nas tangências (900; 100) e o arco de centro (900, 100) liga as duas ({c1 and seg(c1)}, {c2 and seg(c2)}, {arcs})")
    tecla("z", mods=2, espera=0.3)
    ok(seg(ent("c1")) == [(X[4], 0.0), (X[4] + 800.0, 0.0)] and seg(ent("c2")) == [(X[4] + 1000.0, 200.0), (X[4] + 1000.0, 1000.0)] and total() == n0,
       "um Ctrl+Z desfaz a concordância inteira (as duas linhas e o arco)")
    # Esc no meio: depois do primeiro clique
    clicar_mm([X[4] + 400, 0])
    esc()
    ok(ferr() == "selecionar" and js("return c.ferramentas.get('concordar').primeira;") is None, "Esc depois da primeira linha cancela e solta")
    # Esc com o campo MEDIDAS com texto: limpa, solta o foco, sai e não troca o raio
    tecla("k"); tecla("5")
    m_ = js("return [c.el.medida.value, document.activeElement === c.el.medida];")
    esc()
    ok(m_ == ["5", True] and js("return [c.el.medida.value, document.activeElement === c.el.medida, c.ferramenta.constructor.id, c.ferramentas.get('concordar').raio];") == ["", False, "selecionar", 100],
       f"Esc com '5' no campo MEDIDAS: limpa, solta o foco e sai (o raio fica 100) ({m_})")
    # raio 0
    ver(5)
    tecla("k"); digitar("0")
    clicar_mm([X[5] + 400, 0]); clicar_mm([X[5] + 1000, 650])
    c3, c4 = ent("c3"), ent("c4")
    ok(c3 and c4 and seg(c3) == [(X[5], 0.0), (X[5] + 1000.0, 0.0)] and seg(c4) == [(X[5] + 1000.0, 0.0), (X[5] + 1000.0, 1000.0)]
       and not na_regiao(5, "arco"), f"Concordar R 0: canto vivo, as duas linhas vão até o encontro e não há arco ({c3 and seg(c3)}, {c4 and seg(c4)})")
    esc()

    # o arco estendido pela curva até a linha (x = 300: a 131,8°); duas linhas em X com R 0: fica o lado clicado
    ver(11)
    tecla("n")
    clicar_mm([X[11] + 500 + 300 * math.cos(math.radians(80)), 300 * math.sin(math.radians(80))])
    ea = ent("ea")
    ok(ea and round(ea["inicio"], 1) == 0 and round(ea["fim"], 1) == 131.8, f"Estender um arco: a ponta segue a curva até a linha (fim 90° → 131,8°) ({ea and (ea['inicio'], ea['fim'])})")
    esc()
    tecla("k"); digitar("0")
    clicar_mm([X[11] + 1200, 0]); clicar_mm([X[11] + 1500, 300])
    k1, k2 = ent("kx1"), ent("kx2")
    ok(k1 and k2 and seg(k1) == [(X[11] + 1000.0, 0.0), (X[11] + 1500.0, 0.0)] and seg(k2) == [(X[11] + 1500.0, 0.0), (X[11] + 1500.0, 500.0)],
       f"Concordar R 0 em linhas que se cruzam: fica o lado clicado de cada uma ({k1 and seg(k1)}, {k2 and seg(k2)})")
    esc()

    # ------------------------------------------------------------------ 4. Offset
    ver(6)
    tecla("f")
    v = digitar("200")
    ok(v == "200" and ferr() == "offset", f"Offset: o 200 digitado antes vai para MEDIDAS ({v}, {ferr()})")
    clicar_mm([X[6] + 500, 0])
    mover_mm([X[6] + 500, 400])
    ok(len(js("return c.tela.previa;") or []) == 1, "Offset: a prévia da paralela acompanha o mouse")
    clicar_mm([X[6] + 500, 400])
    ls = sorted(seg(e) for e in (na_regiao(6, "linha") or []))
    ok([(X[6], 200.0), (X[6] + 1000.0, 200.0)] in ls, f"Offset 200 da linha, do lado do clique (y = 200) ({ls})")
    clicar_mm([X[6] + 2000, 300]); clicar_mm([X[6] + 2000, 700])
    rs = sorted(round(e["raio"], 1) for e in (na_regiao(6, "arco") or []))
    ok(rs == [300.0, 500.0], f"Offset 200 do arco para fora: R 500 ({rs})")
    clicar_mm([X[6] + 3300, 300]); clicar_mm([X[6] + 3080, 330])
    rs = sorted(round(e["raio"], 1) for e in (na_regiao(6, "circulo") or []))
    ok(rs == [100.0, 300.0], f"Offset 200 do círculo para dentro: R 100 ({rs})")
    tecla("z", mods=2, espera=0.3)
    ok(sorted(round(e["raio"], 1) for e in (na_regiao(6, "circulo") or [])) == [300.0], "um Ctrl+Z tira só o último offset")
    esc()
    # o lado pelo clique, sem distância: a paralela passa pelo ponto clicado
    tecla("f")
    clicar_mm([X[6] + 500, 0]); clicar_mm([X[6] + 500, -300])
    ls = sorted(seg(e) for e in (na_regiao(6, "linha") or []))
    ok([(X[6], -300.0), (X[6] + 1000.0, -300.0)] in ls, f"Offset sem distância: a paralela passa pelo clique (y = −300) ({ls})")
    # a distância digitada depois do clique na linha, com unidade ("15cm": o c e o m não abrem Círculo nem Mover)
    clicar_mm([X[6] + 500, 0])
    v = digitar("15cm")
    ok(v == "15cm" and ferr() == "offset", f"Offset: '15cm' digitado depois do clique fica no campo, sem virar atalho ({v}, {ferr()})")
    clicar_mm([X[6] + 500, 500])
    ls = sorted(seg(e) for e in (na_regiao(6, "linha") or []))
    ok([(X[6], 150.0), (X[6] + 1000.0, 150.0)] in ls, f"Offset 15 cm = 150 mm do lado do clique ({ls})")
    # Esc no meio: depois de escolher a linha
    n0 = total()
    clicar_mm([X[6] + 500, 0]); mover_mm([X[6] + 500, -600])
    esc()
    ok(ferr() == "selecionar" and not js("return c.tela.previa;") and total() == n0, "Esc depois de escolher a linha: sem prévia, nada criado, volta a Selecionar")
    # polilinhas
    ver(7)
    tecla("f"); digitar("200")
    clicar_mm([X[7] + 500, 0]); clicar_mm([X[7] + 500, -300])
    novas = [e["vertices"] for e in (na_regiao(7, "polilinha") or []) if e["id"] not in ("o4", "o5")]
    vs = [[round(a, 1) for a in q] for q in novas[0]] if novas else None
    ok(vs == [[X[7], -200.0], [X[7] + 1200.0, -200.0], [X[7] + 1200.0, 600.0]],
       f"Offset 200 da polilinha aberta para fora: [0,−200] [1200,−200] [1200,600] — as pontas ficam no prolongamento ({vs})")
    clicar_mm([X[7] + 2500, 0]); clicar_mm([X[7] + 2500, -300])
    novas = [e for e in (na_regiao(7, "polilinha") or []) if e["id"] not in ("o4", "o5") and e.get("fechada")]
    vs = [[round(a, 1) for a in q] for q in novas[0]["vertices"]] if novas else None
    ok(vs == [[X[7] + 1800.0, -200.0], [X[7] + 3200.0, -200.0], [X[7] + 3200.0, 700.0], [X[7] + 1800.0, 700.0]],
       f"Offset 200 da polilinha fechada para fora ({vs})")
    esc()

    # ------------------------------------------------------------------ 5. Medir
    ver(8); limpar_avisos()
    tecla("u")
    clicar_mm([X[8], 0], 3, -2)
    mover_mm([X[8] + 1200, 500], -2, 3)
    ph = js("return c.el.medida.placeholder;")
    ok(ph == "1300 mm", f"Medir: a caixa MEDIDAS mostra 1300 mm com o mouse na outra ponta ({ph})")
    clicar_mm([X[8] + 1200, 500], -2, 3)
    av = aviso_txt() or ""
    ok("Distância: 1300 mm" in av and "Δx 1200" in av and "Δy 500" in av and "22,6°" in av, f"Medir: o aviso dá 1300 mm, Δx 1200, Δy 500, 22,6° ({av})")
    clicar_mm([X[8] + 600, 250])
    esc()
    ok(ferr() == "selecionar" and not js("return c.tela.previa;"), "Medir: Esc depois do primeiro ponto tira a linha de medida")
    tecla("u")
    ok(js("return c.ferramenta.a;") is None, "Medir reaberto começa do primeiro ponto")
    esc()

    # ------------------------------------------------------------------ 6. Corte (só a marca no 2D)
    ver(9); limpar_avisos()
    n0 = total()
    tecla("y")
    clicar_mm([X[9], 0]); clicar_mm([X[9] + 1000, 0]); mover_mm([X[9] + 500, 300])
    ok(len(js("return c.tela.previa;") or []) > 3, "Corte: a prévia mostra a marca (linha, setas, bolinhas) antes do terceiro clique")
    clicar_mm([X[9] + 500, 300])
    pausa(0.3)
    marcas = js("return [...c.doc.entidades.values()].filter(e => (e.atributos || {}).marca_corte === '1').map(e => [e.tipo, e.camada]);") or []
    linha = js(f"return [...c.doc.entidades.values()].some(e => e.tipo === 'linha' && (e.atributos || {{}}).marca_corte === '1' && Math.hypot(e.a[0] - {X[9]}, e.a[1]) < 2 && Math.hypot(e.b[0] - {X[9] + 1000}, e.b[1]) < 2);")
    av = aviso_txt() or ""
    ok(linha and len(marcas) >= 9 and all(cam == "CORTES" for _, cam in marcas), f"Corte: a marca 1-1 (linha, setas, bolinhas, nomes) na camada CORTES ({linha}, {marcas})")
    ok("marcado" in av, f"Corte sem vista do modelo: avisa que só marcou (o 3D não é gerado aqui) ({av[:120]})")
    tecla("z", mods=2, espera=0.3)
    ok(total() == n0, f"um Ctrl+Z tira a marca do corte inteira ({total()} × {n0})")
    esc()

    # ------------------------------------------------------------------ 7. snap
    ver(10)
    tecla("l")

    def snap_em(p, dx, dy, mods=0):
        mover_mm(p, dx, dy, mods)
        return js("return c.tela.snap ? [c.tela.snap.tipo, c.tela.cursor.map(v => Math.round(v * 1000) / 1000)] : [null, c.tela.cursor];")

    def conferir_snaps(onde):
        for nome, p, d, tipo in (("extremidade", [X[10], 0], (3, -2), "extremidade"), ("meio", [X[10] + 500, 0], (2, 3), "meio"),
                                 ("interseção", [X[10] + 300, 0], (3, 2), "interseccao"), ("centro", [X[10] + 2000, 0], (3, 3), "centro")):
            r = snap_em(p, *d)
            ok(r and r[0] == tipo and r[1] == [float(p[0]), float(p[1])], f"snap {onde}: {nome} com o mouse a {d} px pega {p} ({r})")
    conferir_snaps("na vista normal")
    # perpendicular a partir do primeiro ponto da linha
    clicar_mm([X[10] + 800, 400])
    r = snap_em([X[10] + 800, 0], 2, 3)
    ok(r and r[0] == "perpendicular" and r[1] == [X[10] + 800.0, 0.0], f"snap perpendicular a s1 a partir do primeiro ponto ({r})")
    r = snap_em([X[10] + 1300, 450], 0, 0, mods=8)
    ok(r and r[0] == "orto" and r[1] == [X[10] + 1300.0, 400.0], f"Shift trava o orto na horizontal do primeiro ponto ({r})")
    esc()
    ok(not js("return c.tela.previa;") and not [e for e in (na_regiao(10, "linha") or []) if e["id"] not in ("s1", "s2")], "Esc na linha em curso: nada criado")
    tecla("l")
    # zoom bem longe pela roda, no ponto da interseção: o ponto sob o cursor fica
    xi, yi = [round(v) for v in tela([X[10] + 300, 0])]
    mover(xi, yi)
    sob_px = lambda: js(f"const r = c.el.canvas.getBoundingClientRect(); return c.tela.paraMundo([{xi} - r.left, {yi} - r.top]);")
    mm0 = sob_px()
    for _ in range(18):
        aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=xi, y=yi, deltaX=0, deltaY=100); pausa(0.02)
    pausa(0.3)
    z_longe = js("return c.tela.vp.z;")
    sob = sob_px()
    ok(z_longe < 0.06 and math.dist(sob, mm0) < 1e-6 / z_longe, f"roda para trás afasta (z {z_longe:.4f}) e o ponto sob o cursor fica ({mm0} → {sob})")
    conferir_snaps(f"com o zoom longe (1 m = {z_longe * 1000:.0f} px)")
    for _ in range(80):
        aba.cmd("Input.dispatchMouseEvent", type="mouseWheel", x=xi, y=yi, deltaX=0, deltaY=-100); pausa(0.01)
    pausa(0.3)
    z_perto = js("return c.tela.vp.z;")
    sob = sob_px()
    ok(z_perto > 20 and math.dist(sob, mm0) < 1e-6 * 1000, f"roda para a frente aproxima (z {z_perto:.1f}) e o ponto sob o cursor fica ({mm0} → {sob})")
    r = snap_em([X[10] + 300, 0], 3, 2)
    ok(r and r[0] == "interseccao" and r[1] == [X[10] + 300.0, 0.0], f"snap com o zoom bem perto (1 mm = {z_perto:.0f} px): interseção exata ({r})")
    r = snap_em([X[10] + 300, 0], 40, 0)
    ok(r and r[0] == "sobre" and abs(r[1][1]) < 1e-6, f"bem perto, 40 px ao lado da interseção: sobre a linha, sem pular para a interseção ({r})")
    esc()

    # ------------------------------------------------------------------ 8. navegação
    ver(10)
    vp0 = js("return { ...c.tela.vp };")
    mx, my = 800, 500
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=mx, y=my, button="middle", buttons=4, clickCount=1)
    for i in range(1, 6): mover(mx + 20 * i, my + 10 * i, botoes=4, botao="middle")
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=mx + 100, y=my + 50, button="middle", buttons=0, clickCount=1)
    pausa(0.2)
    vp1 = js("return { ...c.tela.vp };")
    ok(abs((vp0["x"] - vp1["x"]) * vp0["z"] - 100) < 0.5 and abs((vp1["y"] - vp0["y"]) * vp0["z"] - 50) < 0.5 and vp1["z"] == vp0["z"],
       f"arrastar com o botão do meio leva a vista junto (100, 50 px) ({vp0} → {vp1})")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=mx, y=my, button="right", buttons=2, clickCount=1)
    for i in range(1, 6): mover(mx - 20 * i, my, botoes=2, botao="right")
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=mx - 100, y=my, button="right", buttons=0, clickCount=1)
    pausa(0.2)
    vp2 = js("return { ...c.tela.vp };")
    menu = js("return !!document.querySelector('.menu-contexto, .menu-de-contexto, [data-menu-contexto]');")
    ok(abs((vp2["x"] - vp1["x"]) * vp1["z"] - 100) < 0.5 and not menu, f"arrastar com o direito também leva a vista, sem abrir o menu ({vp2}, menu {menu})")

    def enquadrado():
        return js("""const b = c.doc.caixa(), a = c.tela.paraTela(b[0]), d = c.tela.paraTela(b[1]);
                     return a[0] >= -1 && d[0] <= c.tela.largura + 1 && d[1] >= -1 && a[1] <= c.tela.altura + 1 && (d[0] - a[0] > 0.7 * c.tela.largura || a[1] - d[1] > 0.7 * c.tela.altura);""")
    ok(not enquadrado(), "(antes do Z o desenho não está todo na tela)")
    tecla("z")
    ok(enquadrado(), "Z enquadra o desenho inteiro")
    ver(10)
    js("window.__dbl = []; c.el.canvas.addEventListener('dblclick', ev => __dbl.push(['dblclick', ev.button])); c.el.canvas.addEventListener('auxclick', ev => __dbl.push(['auxclick', ev.button, ev.detail])); return 1;")
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=mx, y=my, button="middle", buttons=4, clickCount=1)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=mx, y=my, button="middle", buttons=0, clickCount=1)
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=mx, y=my, button="middle", buttons=4, clickCount=2)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=mx, y=my, button="middle", buttons=0, clickCount=2)
    pausa(0.3)
    ok(enquadrado(), f"duplo clique com o botão do meio enquadra (eventos no canvas: {js('return window.__dbl;')})")

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
    aba.ws.close()
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
