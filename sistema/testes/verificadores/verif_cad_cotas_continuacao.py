# -*- coding: utf-8 -*-
"""Rodada de melhorias do desenho 2D (usuário, 22/10, nas pranchas da ME Sooro - Sala de Compressores), com mouse e
teclado de verdade (Input.dispatchMouseEvent / dispatchKeyEvent) sobre um trecho da própria prancha
(testes/dados_cad/me_sooro_prancha_trecho.json — a cumeeira da tesoura e a cota 275, em mm de papel):
  A. "Estou tentando desenhar uma linha bem aproximada e ele não está fazendo a continuação do ângulo da linha existente":
     a Linha que sai da ponta do banzo (no meio de dezenas de linhas de chapa) gruda na continuação dele (11,31°);
  B. "Não consigo movimentar uma cota pegando pelo cantinho": a alça no canto da linha de cota leva a linha;
  C. "O MA não funciona se clico em cima do número da cota … só se clicar em cima da linha da cota": o número da cota
     275 (fator 1,96, que sobe um degrau por não caber) pega a cota no MA e no clique;
  D. "Gostaria de melhorar o magnetismo do número com a cota … e que isso fosse configurável igual ao autocad": o número a
     0,625 mm da linha (a DIMGAP do AutoCAD), pelo estilo do desenho e por cota (Propriedades);
  E. "Criar dimcontinue": a Cota contínua (D C), da última cota, da selecionada (a do detalhamento, com o número escrito,
     continua na escala dele) ou da clicada; mesma linha de cota; Ctrl+Z volta um passo da corrente.
"""
import json, math, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_cadcotas_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []
TRECHO = json.load(open(os.path.join(BASE, "testes", "dados_cad", "me_sooro_prancha_trecho.json"), encoding="utf-8"))
PONTA_BANZO = [2181.121, 438.477]          # a ponta do banzo bec7aab6cc (de 1859,284; 374,126), a 11,31°
COTA_275 = "x47p5qq0o8e"                   # h, p1 (1848,294; 360,729), p2 (1859,283; 374,127), deslocamento 125,17, fator 1,96, escala 25
COTA_376 = "1203290f86"                    # a do detalhamento: o número "376" escrito, sem escala


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        if aba.avaliar(expr):
            return True
        aba.drenar(0.3)
    return False


TECLAS = {"Enter": (13, "Enter"), "Escape": (27, "Escape")}
CTRL = 2
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_cadcotas_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos", {"nome": "Cotas", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/trecho", {"desenho": TRECHO})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + f"/cad?projeto={slug}&desenho=trecho", limite=30)
    n_ents = len(TRECHO["entidades"])
    ok(esperar(aba, f"document.body.dataset.pronto === '1' && !!window.cad && window.cad.doc.tamanho === {n_ents}"), f"desenho aberto ({n_ents} objetos da prancha)")
    js = lambda s: aba.avaliar("(() => { const c = window.cad; " + s + " })()")
    jsj = lambda s: json.loads(js("return JSON.stringify((() => { " + s + " })());"))

    def tela(p):
        return jsj("const cv = c.el.canvas; const r = cv.getBoundingClientRect(); const t = c.tela.paraTela(%s); return [r.left + t[0], r.top + t[1]];" % json.dumps(p))

    def evento(tipo, x, y, botao="none", botoes=0, n=1):
        aba.cmd("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=botao, buttons=botoes, clickCount=n)

    def mover(p):
        x, y = tela(p); evento("mouseMoved", x, y); aba.drenar(0.12)

    def clique(p):
        x, y = tela(p)
        evento("mouseMoved", x, y); evento("mousePressed", x, y, "left", 1); evento("mouseReleased", x, y, "left", 0)
        aba.drenar(0.2)

    def tecla(k, mods=0):
        code, nome = TECLAS.get(k, (ord(k.upper()) if len(k) == 1 else 0, ("Key" + k.upper()) if k.isalpha() else ""))
        texto = k if len(k) == 1 and not (mods & CTRL) else ""
        aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=nome, windowsVirtualKeyCode=code, text=texto, unmodifiedText=texto, modifiers=mods)
        aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=nome, windowsVirtualKeyCode=code, modifiers=mods)
        aba.drenar(0.12)

    def duas(k1, k2):
        """Um atalho de duas letras digitado rápido (o "MA", o "DC"): a segunda tecla desce antes de a primeira subir —
        cada comando ao Chrome sem janela leva uns 250 ms, e com a pausa de cada tecla o par passava do segundo que o
        programa espera entre as duas."""
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), text=k, unmodifiedText=k)
        for k in (k1, k2):
            aba.cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()))
        aba.drenar(0.15)

    def esc():
        tecla("Escape"); tecla("Escape")

    def preparar(caixa):
        esc()
        js("c.ativarFerramenta('selecionar'); c.selecionar([]); c.tela.enquadrar(%s, 0.02); return 1;" % json.dumps(caixa))
        aba.drenar(0.3)

    ferr = lambda: js("return c.ferramenta.constructor.id;")
    sel = lambda: sorted(js("return [...c.tela.selecao];") or [])
    dica = lambda: js("return c.el.dica.textContent;") or ""
    ent = lambda i: js(f"const e = c.doc.get({json.dumps(i)}); return e ? JSON.parse(JSON.stringify(e)) : null;")
    cotas = lambda: set(js("return [...c.doc.entidades.values()].filter(e => e.tipo === 'cota').map(e => e.id);"))
    pontas = lambda i: jsj(f"const e = c.doc.get({json.dumps(i)}); const g = c.tela.constructor.geometriaCota(e, c.doc.escala); return [g.a1, g.a2];")

    # ---------------------------------------------------------------- A. a continuação do banzo
    preparar([[2176, 433], [2192, 445]])
    z = js("return c.tela.vp.z;")
    tecla("l")
    ok(ferr() == "linha", "A. L abre a Linha")
    clique(PONTA_BANZO)
    ult = jsj("return c.snap.ultimo;")
    ok(ult and math.dist(ult, PONTA_BANZO) < 1e-3, f"A. o primeiro ponto na ponta do banzo ({ult})")
    ang = math.atan2(438.477 - 374.126, 2181.121 - 1859.284)      # o banzo: 11,3076°
    d = 3.0                                       # 3 mm adiante, 5 px fora da continuação (dentro do raio do snap)
    desvio = math.asin(5.0 / z / d)
    alvo = [PONTA_BANZO[0] + d * math.cos(ang - desvio), PONTA_BANZO[1] + d * math.sin(ang - desvio)]
    mover(alvo)
    s = jsj("const s = c.tela.snap; return s ? {tipo: s.tipo, rotulo: s.rotulo || '', ponto: s.ponto} : null;")
    noBanzo = lambda q: abs(-(q[0] - 1859.284) * math.sin(ang) + (q[1] - 374.126) * math.cos(ang))
    ok(s and s["tipo"] == "alinhamento" and noBanzo(s["ponto"]) < 0.01,
       f"A. o cursor gruda na continuação do banzo: {s and s['tipo']} {s and s['rotulo']}, fora da reta {s and round(noBanzo(s['ponto']), 4)} mm")
    antes = set(js("return [...c.doc.entidades.keys()];"))
    clique(alvo)
    novas = [ent(i) for i in set(js("return [...c.doc.entidades.keys()];")) - antes]
    linha = next((e for e in novas if e and e["tipo"] == "linha"), None)
    a_lin = math.degrees(math.atan2(linha["b"][1] - linha["a"][1], linha["b"][0] - linha["a"][0])) if linha else None
    ok(linha and abs(a_lin - math.degrees(ang)) < 0.01, f"A. a linha feita segue o ângulo do banzo: {a_lin and round(a_lin, 3)}° (banzo 11,31°)")
    esc()

    # ---------------------------------------------------------------- C. o número da cota 275 (antes do B, que a move)
    VISTA_C = [[1835, 355], [1880, 505]]
    preparar(VISTA_C)
    t = jsj(f"const e = c.doc.get('{COTA_275}'); const t = c.tela.constructor.textoCota(e, c.doc.escala, c.tela.estiloDoDesenho); return {{pos: t.pos, h: t.h}};")
    numero = [t["pos"][0], t["pos"][1] + t["h"] / 2]              # o meio do 275 (cota h: o número de pé)
    linha_cota = pontas(COTA_275)
    ok(numero[1] - linha_cota[0][1] > 10, f"C. o 275 fica {numero[1] - linha_cota[0][1]:.1f} mm acima da linha (sobe um degrau: não cabe)")
    clique(numero)
    ok(sel() == [COTA_275], f"C. o clique no número 275 seleciona a cota: {sel()}")
    preparar(VISTA_C)
    duas("m", "a")
    ok(ferr() == "copiar_propriedades", f"C. M A abre o Copiar propriedades: {ferr()}")
    clique(numero)
    ok("Origem: cota" in dica(), f"C. MA: o clique no número pega a cota de origem: '{dica()[:60]}'")
    destino = pontas(COTA_376)
    clique([(destino[0][0] + destino[1][0]) / 2, (destino[0][1] + destino[1][1]) / 2])
    e376 = ent(COTA_376)
    ok(e376["fator"] == 1.96 and e376["altura"] == 2.5, f"C. MA: a cota 376 recebe o tamanho da 275 (altura {e376['altura']}, fator {e376['fator']}; '{dica()[:50]}')")
    tecla("z", CTRL)
    esc()

    # ---------------------------------------------------------------- B. o canto da linha de cota
    preparar([[1835, 470], [1875, 500]])
    a1, a2 = pontas(COTA_275)
    clique([(a1[0] + a2[0]) / 2, a1[1]])
    ok(sel() == [COTA_275], f"B. a cota 275 selecionada pela linha: {sel()}")
    desl0 = ent(COTA_275)["deslocamento"]
    clique(a2)                                        # pega a alça do canto (direito)
    mover([a2[0] + 0.3, a2[1] + 4.0])
    clique([a2[0] + 0.3, a2[1] + 4.0])
    e = ent(COTA_275)
    ok(abs(e["deslocamento"] - (desl0 + 4.0)) < 0.05 and e["p1"] == [1848.294, 360.729] and e["p2"] == [1859.283, 374.127],
       f"B. o canto leva a linha de cota 4 mm para cima e os pontos medidos ficam ({desl0:.2f} → {e['deslocamento']:.2f})")
    clique(pontas(COTA_275)[0])                        # o canto esquerdo também
    mover([a1[0], a1[1] + 1.0]); clique([a1[0], a1[1] + 1.0])
    ok(abs(ent(COTA_275)["deslocamento"] - (desl0 + 1.0)) < 0.05, f"B. pelo canto esquerdo também ({ent(COTA_275)['deslocamento']:.2f})")
    tecla("z", CTRL); tecla("z", CTRL)
    ok(abs(ent(COTA_275)["deslocamento"] - desl0) < 1e-6, "B. Ctrl+Z volta a linha de cota")
    esc()

    # ---------------------------------------------------------------- D. a folga do número
    base_do_numero = lambda i: jsj(f"""const e = c.doc.get('{i}'); const T = c.tela.constructor; const g = T.geometriaCota(e, c.doc.escala);
        const m = [(g.a1[0] + g.a2[0]) / 2, (g.a1[1] + g.a2[1]) / 2]; const t = T.textoCota({{...e, texto_pos: null}}, c.doc.escala, c.tela.estiloDoDesenho);
        return Math.abs((t.pos[0] - m[0]) * g.nx + (t.pos[1] - m[1]) * g.ny);""")
    ok(abs(base_do_numero("a144547468") - 0.625) < 1e-6, f"D. o número a 0,625 mm da linha, como a DIMGAP do AutoCAD (era 1,375): {base_do_numero('a144547468'):.3f}")
    caixa = jsj(f"return c.doc.caixaDa(c.doc.get('{COTA_275}'));")
    ok(caixa[1][1] > numero[1] + 1, f"D. a caixa da cota no índice cobre o número (topo {caixa[1][1]:.1f} ≥ {numero[1]:.1f})")
    js("c.aplicarEstilos({folga: 1.5}); return 1;"); aba.drenar(0.2)
    ok(abs(base_do_numero("a144547468") - 1.5) < 1e-6 and js("return c.doc.metadados.estilo.folga_texto;") == 1.5,
       f"D. Estilos do desenho: a folga 1,5 vale para as cotas ({base_do_numero('a144547468'):.3f})")
    preparar([[1835, 355], [1880, 500]])
    ext = pontas("a144547468")
    clique([(ext[0][0] + ext[1][0]) / 2, (ext[0][1] + ext[1][1]) / 2])
    ok(sel() == ["a144547468"], f"D. a cota 433 selecionada: {sel()}")
    achou = js("""const i = [...document.querySelectorAll('input')].find(x => (x.title || '').startsWith('Distância da linha de cota'));
                  if (!i) return false; i.value = '0.3'; i.dispatchEvent(new Event('change')); return true;""")
    aba.drenar(0.2)
    ok(achou and ent("a144547468")["folga"] == 0.3 and abs(base_do_numero("a144547468") - 0.3) < 1e-6,
       f"D. Propriedades: a folga da cota (0,3) manda sobre a do desenho ({base_do_numero('a144547468'):.3f})")
    js("c.aplicarEstilos({folga: 0.625}); return 1;")
    ok(ent("a144547468")["folga"] is None, "D. Estilos em todo o desenho: as cotas voltam a seguir a folga dele")
    esc()

    # ---------------------------------------------------------------- E. a Cota contínua
    preparar([[1890, 585], [1990, 625]])
    tecla("d")
    ok(ferr() == "cota", "E. D abre a Cota")
    clique([1900, 600]); clique([1920, 600]); clique([1910, 610])
    primeira = list(cotas() - set(TRECHO_ID for TRECHO_ID in (x["id"] for x in TRECHO["entidades"])))
    ok(len(primeira) == 1, f"E. a cota feita com três cliques: {primeira}")
    primeira_p2 = lambda: ent(primeira[0])["p2"]
    duas("d", "c")
    ok(ferr() == "cota_continua", f"E. D C abre a Cota contínua: {ferr()}")
    antes = cotas()
    clique([1950, 600]); clique([1965, 600])
    feitas = [ent(i) for i in cotas() - antes]
    feitas.sort(key=lambda e: e["p2"][0])
    perto = lambda p, q: math.dist(p, q) < 1e-3
    linha_y = [round(pontas(e["id"])[k][1], 3) for e in feitas for k in (0, 1)]
    ok(len(feitas) == 2 and perto(feitas[0]["p1"], primeira_p2()) and perto(feitas[0]["p2"], [1950, 600]) and feitas[1]["p1"] == feitas[0]["p2"]
       and set(linha_y) == {610.0} and all(e["modo"] == "h" for e in feitas),
       f"E. duas cotas na corrente, cada uma do fim da anterior, na mesma linha de cota (y {sorted(set(linha_y))})")
    tecla("z", CTRL)
    ok(len(cotas() - antes) == 1 and ferr() == "cota_continua", "E. Ctrl+Z tira a última e a ferramenta continua")
    clique([1980, 600])
    ult = max((ent(i) for i in cotas() - antes), key=lambda e: e["p2"][0])
    ok(perto(ult["p1"], [1950, 600]) and perto(ult["p2"], [1980, 600]), f"E. a próxima sai do fim da que ficou: {ult['p1']} → {ult['p2']}")
    esc()
    ok(ferr() == "selecionar", "E. Esc termina")
    # da cota do detalhamento (o 376 escrito, sem escala): a corrente continua no número da peça
    preparar([[1835, 355], [1880, 500]])
    p376 = pontas(COTA_376)
    clique([(p376[0][0] + p376[1][0]) / 2, (p376[0][1] + p376[1][1]) / 2])
    ok(sel() == [COTA_376], f"E. a cota 376 do detalhamento selecionada: {sel()}")
    duas("d", "c")
    c376 = ent(COTA_376)
    antes = cotas()
    fim = [c376["p2"][0] + (c376["p2"][0] - c376["p1"][0]), c376["p2"][1] + (c376["p2"][1] - c376["p1"][1])]
    js("c.snap.ativos = {...c.snap.ativos, extremidade: false, meio: false, interseccao: false, perpendicular: false, sobre: false}; return 1;")
    clique(fim)
    js("c.snap.ativos = {...c.snap.ativos, extremidade: true, meio: true, interseccao: true, perpendicular: true, sobre: true}; return 1;")
    nova = [ent(i) for i in cotas() - antes]
    if nova:
        nv = nova[0]
        val = math.dist(nv["p1"], nv["p2"])
        txt = jsj(f"return c.tela.constructor.textoCota(c.doc.get('{nv['id']}'), c.doc.escala, c.tela.estiloDoDesenho).txt;")
        alinhada = abs((pontas(nv["id"])[0][0] - pontas(COTA_376)[1][0])) < 1e-6 and abs((pontas(nv["id"])[0][1] - pontas(COTA_376)[1][1])) < 1e-6
    ok(nova and nv["p1"] == c376["p2"] and nv["escala"] == 25 and txt == "376" and alinhada and nv["altura"] == c376["altura"],
       f"E. do 376 do detalhamento: a próxima em 1:25 (número {nova and txt}, escala {nova and nv['escala']}), na mesma linha ({nova and alinhada})")
    esc()

    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
