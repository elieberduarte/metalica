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
  · Fase 3: "Colar nos eixos 3, 4, 5…" da T2 pergunta o nível do apoio (o Hangar não escreve), cola a tesoura da folha 17
    na Elevação 3 em tamanho real (20 m, centrada entre A e B: 0,30 m para fora de cada lado, avisado) e abre o Tesoura…
    com a marca T2 e os eixos 3, 4, 5 marcados; Lançar põe a T2 nos três eixos da implantação;
  · Fase 4: "Lançar as terças nos eixos" lê a planta de terças (folha 13): 56 peças com as marcas da tabela (T.C.1 ×14,
    T.C.2 ×12, T.C.2-A ×8, T.C.2-B ×8, T.C.3 ×14), o pé de +6,45 a +7,30 pelo corte na vista da tesoura; no 3D, 56 barras
    com papel terça (U127, o eixo meio perfil acima do pé);
  · etapa 4: "Lançar contraventos e vigas" — 32 contraventos (CV1–CV8; os 16 do banzo de cima inclinados com o telhado),
    as correntes (as "A DEFINIR" com aviso), 6 VC (treliçadas, pela folha delas) e 6 VT, também no 3D;
  · Fase 5: com 5 barras antigas no modelo (o 3D desmontado do caminho antigo), "Montar o modelo 3D" avisa delas, deixa o
    modelo só com o identificado (as 141 barras das T2 e as 56 terças), guarda o anterior no histórico e abre o 3D;
  · Fase 6: uma terça andou 300 mm no 3D; "Trazer do 3D o que mudou" leva o movimento à Implantação (no papel do quadro)
    sem mexer na cota do pé;
  · "Ver" leva ao Original com o painel junto; recarregar a página guarda as etapas confirmadas;
  · o Original não é mexido (as mesmas entidades antes e depois)."""
import base64, collections, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
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
    # o 3D desmontado do caminho antigo (o Hangar tinha 417 barras enfileiradas): 5 barras soltas, sem vir da planta
    from nucleo3d.modelo import Barra as _Barra, Documento as _Doc
    _velho = _Doc(nome="antigo")
    for i in range(5):
        _velho.add(_Barra(nome="solta %d" % i, inicio=(i * 4000.0, 0.0, 0.0), fim=(i * 4000.0 + 2000.0, 0.0, 0.0), perfil="W 250×32,7", papel="viga"))
    json.dump(_velho.dict(), open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
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
    ok(aba.avaliar(f"!!({botao('Colar nos eixos 3, 4, 5')})"), "a T2 tem o botão Colar nos eixos 3, 4, 5")

    # ---- Fase 3: a T2 colada na elevação do eixo 3 e lançada nos eixos 3, 4 e 5 pelo Tesoura…
    clicar_em(botao("Colar nos eixos 3, 4, 5"))
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Nível do apoio das tesouras'", 20),
       "sem nível de apoio no projeto, o painel pergunta a cota do apoio")
    aba.avaliar("document.querySelector('#dialogo-corpo input').value = '6000'; 1")
    clicar("#dialogo-ok")
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Tesoura da Elevação 3'", 60), "a T2 foi colada na Elevação 3 e o Tesoura… abriu")
    marca = aba.avaliar("[...document.querySelectorAll('#dialogo-corpo input[type=text]')].map(i => i.value)[0]")
    marcados = aba.avaliar("[...document.querySelectorAll('#dialogo-corpo input[type=checkbox]:checked')].map(i => i.value).filter(v => /^[0-9]+$/.test(v))") or []
    info = aba.avaliar("(document.querySelector('#dialogo-corpo .explica') || {}).textContent || ''") or ""
    ok(marca == "T2" and marcados == ["3", "4", "5"], f"o Tesoura… vem com a marca T2 e os eixos 3, 4, 5 marcados: {marca} {marcados}")
    ok("20,000 m de comprimento" in info and "+6,00" in info, f"a leitura: 20 m de tesoura, apoio em +6,00: «{info[:220]}»")
    import re as _re
    nb = int((_re.search(r"(\d+) barras", info) or [0, 0])[1])
    ok(nb >= 40, f"a alma atravessando o banzo desenhado em contorno é cortada nas faces: {nb} barras lidas (eram 13)")
    avisos = aba.avaliar("[...document.querySelectorAll('#avisos .aviso')].map(a => a.textContent).join(' | ')") or ""
    ok("0,30 m para fora de cada lado" in avisos, f"o aviso diz que a tesoura passa 0,30 m de cada lado do vão A–B: «{avisos[:300]}»")
    clicar("#dialogo-ok")
    ok(esperar("(document.querySelector('[data-tipo=T2]') || {}).classList && document.querySelector('[data-tipo=T2]').classList.contains('lancada')", 30), "a T2 aparece como lançada no painel")
    trels = aba.avaliar("[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e => e.atributos.marca + '@' + e.atributos.eixo).sort()") or []
    ok(trels == ["T2@3", "T2@4", "T2@5"], f"a implantação tem a T2 nos eixos 3, 4 e 5: {trels}")

    # ---- Fase 4: as terças da planta de terças (folha 13), nos eixos, na cota do corte na vista da tesoura
    clicar_em(botao("Confirmar as tesouras"))
    ok(esperar("!document.querySelector('[data-etapa=tercas]').classList.contains('bloqueada')", 10), "confirmadas as tesouras, as terças se liberam")
    clicar_em(botao("Lançar as terças nos eixos"))
    ok(esperar("[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca').length === 56", 60), "56 terças lançadas na Implantação")
    marcas = aba.avaliar("(() => { const c = {}; for (const e of window.cad.doc.entidades.values()) { const a = e.atributos || {}; if (a.identificacao === 'terca') c[a.marca] = (c[a.marca] || 0) + 1; } return c; })()") or {}
    ok(marcas == {"T.C.1": 14, "T.C.2": 12, "T.C.2-A": 8, "T.C.2-B": 8, "T.C.3": 14}, f"as marcas batem com a tabela das folhas 1 e 2: {marcas}")
    zs = aba.avaliar("[...new Set([...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca').map(e => e.atributos.nivel_topo))].sort((a, b) => a - b)") or []
    ok(zs and abs(zs[0] - 6454.5) < 1 and abs(zs[-1] - 7303.1) < 1, f"o pé das terças sobe de +6,45 (borda) a +7,30 (cumeeira): {zs[:3]}…{zs[-2:]}")
    t = painel()
    ok("56 terça(s) lançada(s)" in t and "T.L.1" in t, "o painel mostra as terças lançadas e o aviso das laterais (fechamento)")
    # o 3D acompanha a planta (a gravação sincroniza): as terças e as tesouras no modelo do projeto
    def modelo3d():
        try:
            m = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return []
        ents = m.get("entidades") or []
        return list(ents.values()) if isinstance(ents, dict) else ents
    t0 = time.time()
    while time.time() - t0 < 60 and sum(1 for e in modelo3d() if e.get("papel") == "terça") < 56:
        aba.drenar(1.0)
    m3 = modelo3d()
    tercas3d = [e for e in m3 if e.get("papel") == "terça"]
    ok(len(tercas3d) == 56 and all(e.get("camada") == "Terças" for e in tercas3d), f"no 3D: 56 barras com papel terça na camada Terças ({len(tercas3d)})")
    borda = min(tercas3d, key=lambda e: e["inicio"][2]) if tercas3d else None
    ok(borda and abs(borda["inicio"][2] - (6454.5 + 63.5)) < 2 and borda["perfil"].startswith("U 127"), f"a terça da borda: U127 com o eixo em +6,52 ({borda and borda['inicio'][2]}, {borda and borda['perfil']})")

    # ---- Etapa 4: contraventos (folhas 14 e 15), correntes e as vigas VC (treliçada) e VT (simples) onde a locação marca
    clicar_em(botao("Confirmar as terças"))
    ok(esperar("!document.querySelector('[data-etapa=contraventos]').classList.contains('bloqueada')", 10), "confirmadas as terças, os contraventos se liberam")
    clicar_em(botao("Lançar contraventos e vigas"))
    ok(esperar("[...window.cad.doc.entidades.values()].some(e => (e.atributos || {}).identificacao === 'outra')", 60), "contraventos e vigas lançados na Implantação")
    conta = aba.avaliar("""(() => { const c = {}; for (const e of window.cad.doc.entidades.values()) { const a = e.atributos || {}; if (a.identificacao !== 'outra') continue;
      const k = a.elemento === 'trelica' ? 'VC' : a.marca === 'VT' ? 'VT' : a.papel; c[k] = (c[k] || 0) + 1; } return c; })()""") or {}
    ok(conta.get("contraventamento") == 32 and conta.get("VC") == 6 and conta.get("VT") == 6 and conta.get("corrente", 0) >= 80,
       f"32 contraventos (CV1–CV8), 6 VC, 6 VT e as correntes: {conta}")
    t = painel()
    ok("A DEFINIR" in t and "alma não tem perfil escrito" in t, "os avisos: as correntes A DEFINIR e a alma da VC sem perfil")
    t0 = time.time()
    while time.time() - t0 < 60 and sum(1 for e in modelo3d() if e.get("papel") == "contraventamento") < 32:
        aba.drenar(1.0)
    m3 = modelo3d()
    cvs = [e for e in m3 if e.get("papel") == "contraventamento"]
    inclinados = sum(1 for e in cvs if abs(e["inicio"][2] - e["fim"][2]) > 100)
    ok(len(cvs) == 32 and all(e.get("camada") == "Contraventamento" for e in cvs), f"no 3D: 32 contraventos na camada Contraventamento ({len(cvs)})")
    ok(inclinados == 16, f"os 16 do banzo de cima sobem com o telhado; os 16 do de baixo ficam no plano dele ({inclinados} inclinados)")
    vc = [e for e in m3 if str((e.get("atributos") or {}).get("marca", "")).startswith("VC")]
    ok(len(vc) >= 6 * 10, f"as VC viraram treliças no 3D ({len(vc)} barras)")

    # ---- Etapa 5: os apoios (21/10) — as chapas PB/CB e os chumbadores pela locação dos chumbadores (folha 35) e o
    # detalhe (folha 36). Os pilares pré-moldados entram antes na Implantação, como no Hangar (16, 30 × 40)
    PIL = {"PM1": (82895, -4900), "PM2": (82895, -24300), "PM3": (87695, -4900), "PM4": (87695, -24300),
           "PM5": (92495, -4900), "PM6": (92495, -24300), "PM7": (97295, -4900), "PM8": (97295, -24300),
           "PM9": (102095, -4900), "PM10": (102095, -24300), "PM11": (102095, -9750), "PM12": (102095, -14600),
           "PM13": (102095, -19450), "PM14": (102120, -6250), "PM15": (82895, -1300), "PM16": (82895, -27650)}
    aba.avaliar("""(() => { const M = window.montagem, qi = M._quadroImplantacao(), P = (x, y) => M._paraPapel(qi, [x, y]);
      const pil = %s; const novas = [];
      for (const [m, [x, y]] of Object.entries(pil)) novas.push({ tipo: 'polilinha', camada: 'ESTRUTURA', fechada: true,
        vertices: [P(x - 150, y - 200), P(x + 150, y - 200), P(x + 150, y + 200), P(x - 150, y + 200)],
        atributos: { elemento: 'pilar', material: 'concreto', marca: m, quadro: qi.id, nivel_base: -1000, nivel_topo: 6000,
                     secao: { tipo: 'retangular', b: 30, h: 40 } } });
      window.verifPilares = novas; })()""" % json.dumps(PIL))
    aba.avaliar("""import('/cad/nucleo/desenho2d.js').then(d => import('/cad/nucleo/comandos.js').then(c => {
      window.cad.executar(new c.ComandoAdicionar(window.verifPilares.map(e => d.criar(e)), 'Pilares')); window.verifPilaresOk = 1; }))""")
    ok(esperar("window.verifPilaresOk === 1", 20), "os 16 pilares entraram na Implantação")
    clicar_em(botao("Confirmar ✓"))
    ok(esperar("!document.querySelector('[data-etapa=apoios]').classList.contains('bloqueada')", 10), "confirmados os contraventos, os apoios se liberam")
    clicar_em(botao("Lançar os apoios"))
    ok(esperar("[...window.cad.doc.entidades.values()].some(e => (e.atributos || {}).identificacao === 'apoio')", 60), "os apoios entraram na Implantação")
    ap = aba.avaliar("""(() => { const c = {}; for (const e of window.cad.doc.entidades.values()) { const a = e.atributos || {};
      if (a.identificacao !== 'apoio') continue; const k = a.elemento + ':' + (a.marca || ''); c[k] = (c[k] || 0) + 1; } return c; })()""") or {}
    ok(ap.get("chapa:PB1") == 15 and ap.get("chapa:CB1") == 6, f"15 PB1 (o P07 sem) e a CB1 só nos 6 pilares sob a T2 lançada: {ap}")
    ok(sum(v for k, v in ap.items() if k.startswith("furo")) == 60 and sum(v for k, v in ap.items() if k.startswith("parafuso")) == 60,
       f"60 furos Ø18 e 60 chumbadores: {ap}")
    topos = aba.avaliar("""[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'pilar')
      .map(e => [e.atributos.marca, e.atributos.nivel_topo])""") or []
    baixos = sorted(m for m, z in topos if z == 5992)
    ok(baixos == sorted(["PM3", "PM4", "PM5", "PM6", "PM7", "PM8"]), f"os pilares sob a T2 com o topo na face de baixo da CB (+5,992): {baixos}")
    t = painel()
    ok("PM14" in t and "A DEFINIR" in t, "os avisos: o P07 sem apoio e a CB1 A DEFINIR da folha 36")
    t0 = time.time()
    while time.time() - t0 < 60 and sum(1 for e in modelo3d() if e.get("papel") == "chumbador") < 60:
        aba.drenar(1.0)
    m3 = modelo3d()
    chb = [e for e in m3 if e.get("papel") == "chumbador"]
    chs = [e for e in m3 if e.get("tipo") == "chapa" and str((e.get("atributos") or {}).get("marca", "")) in ("PB1", "CB1")]
    ok(len(chb) == 60 and all(abs(abs(e["inicio"][2] - e["fim"][2]) - 550) < 1 for e in chb), f"no 3D: 60 chumbadores de 550 mm ({len(chb)})")
    ok(len(chs) == 21 and all(len(e.get("furos") or []) == 4 for e in chs if e["atributos"]["marca"] == "PB1"),
       f"no 3D: 21 chapas, a PB1 com os 4 furos ({len(chs)})")

    # ---- Etapa 6: o suporte das terças (21/10) — o ST1 das folhas 4 e 33 em cada terça; o 3D põe um por cruzamento
    clicar_em(botao("Confirmar ✓", "[data-etapa=apoios]"))
    ok(esperar("!document.querySelector('[data-etapa=suportes]').classList.contains('bloqueada')", 10), "confirmados os apoios, os suportes se liberam")
    clicar_em(botao("Pôr os suportes nas terças"))
    ok(esperar("[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca' && (e.atributos || {}).suporte).length === 56", 30),
       "o ST1 nas 56 terças da Implantação")
    ok("ST1 em 56 terça(s)" in painel() and "SL1" in painel(), "o painel: ST1 nas terças e o SL1 que fica para as laterais")

    # ---- Etapa 7: as chapas da emenda e das ligações (21/10) — CE1/CL1 da T2 pelas folhas 30 e 32; o 3D faz a emenda
    # na cumeeira (as duas CE e os 8 parafusos) e a CL1 nos montantes onde as VC e as VT chegam
    clicar_em(botao("Confirmar ✓", "[data-etapa=suportes]"))
    ok(esperar("!document.querySelector('[data-etapa=chapas]').classList.contains('bloqueada')", 10), "confirmados os suportes, as chapas se liberam")
    clicar_em(botao("Pôr as chapas nas tesouras"))
    ok(esperar("[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && (e.atributos || {}).chapas).length === 3", 30),
       "as chapas nas 3 T2 da Implantação")
    t = painel()
    ok("CE1 (T2" in t and "CL1 (T2" in t and "8 parafusos" in t, f"o painel: CE1 e CL1 da T2 e os parafusos da emenda: «{t[-400:]}»")
    t0 = time.time()
    while time.time() - t0 < 60 and sum(1 for e in modelo3d() if (e.get("atributos") or {}).get("marca") == "CE1") < 6:
        aba.drenar(1.0)
    m3 = modelo3d()
    pl = collections.Counter((e.get("atributos") or {}).get("marca") for e in m3 if e.get("tipo") == "chapa" and (e.get("atributos") or {}).get("papel_chapa"))
    pz = [e for e in m3 if ((e.get("atributos") or {}).get("parafuso") or {}) and str((e.get("atributos") or {}).get("marca", "")) == "PAR CE1"]
    ok(pl.get("CE1") == 6 and pl.get("CL1") == 6 and len(pz) == 24, f"no 3D: 6 CE1, 6 CL1 e 24 parafusos da emenda ({dict(pl)}, {len(pz)})")

    # ---- Etapa 8: as aletas dos contraventos (21/10) — a AC1 da folha 34 em cada ponta de contravento que chega numa T2
    clicar_em(botao("Confirmar ✓", "[data-etapa=chapas]"))
    ok(esperar("!document.querySelector('[data-etapa=aletas]').classList.contains('bloqueada')", 10), "confirmadas as chapas, as aletas se liberam")
    clicar_em(botao("Pôr as aletas nas tesouras"))
    ok(esperar("[...window.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && (e.atributos || {}).aletas).length === 3", 30),
       "as aletas nas 3 T2 da Implantação")
    ok("AC1 (T2" in painel(), "o painel: a AC1 da T2")
    t0 = time.time()
    while time.time() - t0 < 60 and sum(1 for e in modelo3d() if (e.get("atributos") or {}).get("papel_chapa") == "aleta") < 32:
        aba.drenar(1.0)
    m3 = modelo3d()
    acs = [e for e in m3 if (e.get("atributos") or {}).get("papel_chapa") == "aleta"]
    ok(len(acs) == 32 and all(e["atributos"]["marca"] == "AC1" for e in acs), f"no 3D: 32 AC1, uma em cada ponta de contravento nos eixos 3 e 5 ({len(acs)})")

    clicar_em("[...document.querySelectorAll('.ident-tesoura')].find(d => d.textContent.includes('T3')).querySelector('.ident-ver')")
    ok(esperar("window.cad.nomeDesenho === 'planta-de-lançamento' && !document.querySelector('#painel-ident').hidden", 30), "Ver leva ao Original com o painel junto")
    aba.drenar(1.0)
    ok(not aba.avaliar("[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('Ajustar a escala'))"),
       "o Original do projeto recebido não sugere mudar a escala dele")
    clicar("[data-aba=montagem]")
    ok(esperar("window.cad.nomeDesenho === 'montagem' && !document.querySelector('#painel-ident').hidden", 30), "a aba Montagem volta, com o painel")

    aba.drenar(1.5)                                       # a gravação da montagem (400 ms depois da mudança)
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && window.montagem && document.body.dataset.pronto === '1'")
    clicar('.menu[data-menu="desenho"] > button')
    clicar('[data-acao="identificacao"]')
    ok(esperar("document.querySelector('[data-etapa=locacao]') && document.querySelector('[data-etapa=locacao]').classList.contains('confirmada')", 60),
       "recarregada a página, a locação continua confirmada (sem varrer de novo)")

    # ---- Fase 5: Montar o modelo 3D — o que não veio da identificação vai para o histórico, o 3D abre
    def modelo3d_():
        m = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
        e = m.get("entidades") or []
        return list(e.values()) if isinstance(e, dict) else e
    soltas_antes = sum(1 for e in modelo3d_() if str(e.get("nome", "")).startswith("solta"))
    ok(soltas_antes == 5, f"antes de montar, o modelo tem as 5 barras antigas junto do identificado ({soltas_antes})")
    hist_antes = len(os.listdir(os.path.join(pasta, "historico"))) if os.path.isdir(os.path.join(pasta, "historico")) else 0
    clicar_em(botao("Montar o modelo 3D"))
    ok(esperar("document.querySelector('#dialogo').open && document.querySelector('#dialogo-titulo').textContent === 'Montar o modelo 3D'", 30)
       and "5 peça(s) que não vieram da identificação" in (aba.avaliar("document.querySelector('#dialogo-corpo').textContent") or ""),
       "Montar avisa das 5 peças que não vieram da identificação")
    clicar("#dialogo-ok")
    ok(esperar("location.pathname.indexOf('/editor') >= 0 || location.pathname.indexOf('/dividida') >= 0", 60), f"depois de montar, o 3D abre ({aba.avaliar('location.pathname')})")
    m3 = modelo3d_()
    soltas = sum(1 for e in m3 if str(e.get("nome", "")).startswith("solta"))
    papeis = {}
    for e in m3:
        papeis[e.get("papel")] = papeis.get(e.get("papel"), 0) + 1
    ok(soltas == 0 and papeis.get("terça") == 56 and papeis.get("contraventamento") == 32 and len(m3) >= 56 + 141 + 32,
       f"o modelo ficou só com o identificado: {len(m3)} peças, {papeis.get('terça')} terças, {papeis.get('contraventamento')} contraventos, {soltas} antigas")
    hist = len(os.listdir(os.path.join(pasta, "historico"))) if os.path.isdir(os.path.join(pasta, "historico")) else 0
    ok(hist > hist_antes, f"o modelo de antes foi para o histórico ({hist_antes} → {hist})")

    # ---- Fase 6: a volta do 3D — uma terça andou 300 mm ao longo dela no 3D; "Trazer do 3D o que mudou" leva à Implantação
    mod = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
    lista = mod["entidades"] if isinstance(mod["entidades"], list) else list(mod["entidades"].values())
    tb = next(e for e in lista if e.get("papel") == "terça")
    import math as _m
    L_ = _m.dist(tb["inicio"], tb["fim"])
    d_ = [(tb["fim"][i] - tb["inicio"][i]) / L_ for i in range(3)]
    tb["inicio"] = [tb["inicio"][i] + 300 * d_[i] for i in range(3)]
    tb["fim"] = [tb["fim"][i] + 300 * d_[i] for i in range(3)]
    origem = tb["atributos"]["origem_2d"]
    json.dump(mod, open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    aba.navegar(f"{base}/cad?projeto={s}", limite=60)
    esperar("window.cad && window.montagem && document.body.dataset.pronto === '1'")
    clicar('.menu[data-menu="desenho"] > button')
    clicar('[data-acao="identificacao"]')
    ok(esperar(f"!!({botao('Trazer do 3D o que mudou')})", 60), "montado, o painel tem Trazer do 3D o que mudou")
    antes_a = aba.avaliar(f"window.cad.doc.get('{origem}').a")
    clicar_em(botao("Trazer do 3D o que mudou"))
    ok(esperar("[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('Planta atualizada pelo 3D') && a.textContent.includes('movida 300 mm'))", 30),
       "a volta diz o que mudou: a terça movida 300 mm")
    depois_a = aba.avaliar(f"window.cad.doc.get('{origem}').a")
    esc = aba.avaliar("window.montagem.m.quadros.find(q => q.tipo === 'implantacao').escala")
    anda = _m.dist(antes_a, depois_a) * esc if antes_a and depois_a else 0
    ok(abs(anda - 300) < 2, f"a terça andou 300 mm na Implantação (no papel, 300 ÷ {esc}): {round(anda, 1)} mm")
    zt = aba.avaliar(f"window.cad.doc.get('{origem}').atributos.nivel_topo")
    ok(zt is not None and abs(zt - 6454.5) < 1, f"a cota do pé não mudou na volta (apoiada pela base): {zt}")

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
