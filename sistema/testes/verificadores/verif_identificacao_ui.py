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
  · Fase 5: com 5 barras antigas no modelo (o 3D desmontado do caminho antigo), "Montar o modelo 3D" avisa delas, deixa o
    modelo só com o identificado (as 141 barras das T2 e as 56 terças), guarda o anterior no histórico e abre o 3D;
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
    ok(soltas == 0 and papeis.get("terça") == 56 and len(m3) == 56 + 141, f"o modelo ficou só com o identificado: {len(m3)} peças, {papeis.get('terça')} terças, {soltas} antigas")
    hist = len(os.listdir(os.path.join(pasta, "historico"))) if os.path.isdir(os.path.join(pasta, "historico")) else 0
    ok(hist > hist_antes, f"o modelo de antes foi para o histórico ({hist_antes} → {hist})")

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
