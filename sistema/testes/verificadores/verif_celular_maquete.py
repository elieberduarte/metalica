# -*- coding: utf-8 -*-
"""A maquete na mesa pelo celular (realidade aumentada, Fase 1 — usuário, 20/10: "mostrar com a câmera do celular a
peça no mundo real... tipo uma maquete"). No celular emulado (390 × 844, toque), com o 3D aberto:
  1. Vistas → "Maquete na mesa": a maquete do que está à vista (a camada desligada não vai; parafusos e porcas, as
     peças menores que 80 mm, ficam de fora na obra inteira), em metros, Y para cima, centrada, no chão, 0,6 m de lado;
  2. o .usdz do iPhone: um zip sem compressão com os arquivos alinhados em 64 bytes, o model.usda primeiro, Y para
     cima, uma malha por cor, os pontos todos lá;
  3. a ficha → "Na mesa": o conjunto da peça (a peça da montagem pela planta; o conjunto que se toca, não as cópias
     dele espalhadas pela obra);
  4. os três caminhos da tela: sem realidade aumentada (o aviso), iPhone (o link rel="ar" com o .usdz) e Android
     (o botão que abre a câmera; a câmera recusada não deixa nada por cima da tela).
A câmera de verdade não roda no Chrome sem janela: o teste no aparelho fica com a pessoa.

Obra real (opcional): METALICA_MAQUETE_OBRA=<pasta do projeto> copia o projeto para o teste e mede a maquete inteira.
Porta livre, nunca a 8765/8766."""
import base64, io, json, os, shutil, subprocess, sys, tempfile, time, zipfile
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_pacote_celular import _modelo
from test_cobertura_movel import PAR, _modelo as _modelo_cobertura
from nucleo3d import cobertura_movel as CM

if "import celular.web" not in open(os.path.join(BASE, "app.py"), encoding="utf-8").read():
    print("  pulado: o app.py desta cópia não carrega o acesso pelo celular (extensões do desenvolvimento)")
    print()
    print("FALHAS: 0")
    sys.exit(0)

PORTA, PORTA_CEL = _porta_livre(), _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_celmaq_")
proj = os.path.join(DADOS, "obra-maquete")
os.makedirs(proj)
json.dump({"nome": "Obra da maquete", "alterado": "2026-10-20T10:00:00"}, open(os.path.join(proj, "projeto.json"), "w", encoding="utf-8"))
MODELO = _modelo()
# uma diagonal de tesoura inclinada a 45°, com cor própria: simplificada, tem de virar uma barra na direção dela (a caixa
# só girada na planta fazia dela uma placa da altura da diagonal — usuário, 20/10, no S25)
MODELO["entidades"].append({"id": "d1", "tipo": "barra", "nome": "diagonal", "camada": "Vigas", "material": "Aço diagonal",
                            "inicio": [0, 4000, 0], "fim": [3000, 4000, 3000], "perfil": "W 200×22,5", "rotacao": 0.0})
MODELO["materiais"]["Aço diagonal"] = {"nome": "Aço diagonal", "cor": "#ff00ff"}
json.dump(MODELO, open(os.path.join(proj, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
# a cobertura retrátil (usuário, 20/10: "ter a visualização do modelo aberto e fechado na maquete"): a pequena do
# test_cobertura_movel, gravada aberta
cob = os.path.join(DADOS, "cobertura")
os.makedirs(cob)
json.dump({"nome": "Cobertura retrátil", "alterado": "2026-10-20T10:00:00", "analise_parametros": PAR}, open(os.path.join(cob, "projeto.json"), "w", encoding="utf-8"))
_doc = _modelo_cobertura()
CM.aplicar(_doc, PAR, "aberta")
json.dump(_doc.dict(), open(os.path.join(cob, "modelo.json"), "w", encoding="utf-8"))
REAL = os.environ.get("METALICA_MAQUETE_OBRA")
if REAL:
    destino = os.path.join(DADOS, "obra-real")
    os.makedirs(destino)
    for nome in ("projeto.json", "modelo.json"):
        shutil.copy2(os.path.join(REAL, nome), os.path.join(destino, nome))

amb = dict(os.environ, METALICA_CELULAR_PORTA=str(PORTA_CEL), METALICA_CELULAR_HOST="127.0.0.1", PYTHONIOENCODING="utf-8")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=amb)
base, cel = f"http://localhost:{PORTA}", f"http://127.0.0.1:{PORTA_CEL}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def foto(aba, nome):
    aba.drenar(0.4)
    open(os.path.join(SCR, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


def esperar(aba, expr, limite=60):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.3)
    return False


def chrome(largura, altura, dpr, celular):
    exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_celmaq_")
    p = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                          "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
            if alvos: break
        except Exception: pass
        time.sleep(0.5)
    a = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): a.cmd(f"{dm}.enable")
    a.cmd("Emulation.setDeviceMetricsOverride", width=largura, height=altura, deviceScaleFactor=dpr, mobile=celular)
    if celular:
        a.cmd("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        a.cmd("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (Linux; Android 15; SM-S938B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36")
    return p, perfil, a


def tocar(aba, seletor):
    r = aba.avaliar("(() => { const b = document.querySelector(%s).getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()" % json.dumps(seletor))
    aba.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": r[0], "y": r[1]}])
    aba.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])


ABERTO = "window.visor && window.visor.fichas && !document.querySelector('.carregando')"
# o que a maquete da obra deve levar, contado à parte: à vista e com o lado maior de 80 mm ou mais
ESPERADO = """(() => { const v = window.visor; let n = 0, peq = 0; const mn = [1e12, 1e12, 1e12], mx = [-1e12, -1e12, -1e12];
  v.fichas.forEach((f, i) => { if (i >= v.nPecas || v.visivelCamada[v.camadaDe[i]] === false) return;
    const b = f.b, t = b ? Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) : 1e9;
    if (t < 80) { peq++; return; } n++; for (let r = 0; r < 3; r++) { mn[r] = Math.min(mn[r], b[r]); mx[r] = Math.max(mx[r], b[r + 3]); } });
  return JSON.stringify({ n, peq, medidas: [0, 1, 2].map(r => (mx[r] - mn[r]) / 1000) }); })()"""
# a maquete montada de novo pelo módulo, para medir a caixa dela no espaço da realidade aumentada
CAIXA = """(async () => { const M = await import('./maquete.js'), T = await import('three'); const v = window.visor;
  const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), {});
  const c = new T.Box3().setFromObject(r.grupo); const s = c.getSize(new T.Vector3()), m = c.getCenter(new T.Vector3());
  let pontos = 0; r.grupo.traverse(o => { if (o.isMesh) pontos += o.geometry.attributes.position.count; });
  window._maq = r;
  return JSON.stringify({ lado: Math.max(s.x, s.y, s.z), chao: c.min.y, cx: m.x, cz: m.z, malhas: r.grupo.children.length, pontos,
    altura: s.y, normais: r.grupo.children.every(o => o.geometry.attributes.normal && o.geometry.attributes.normal.count === o.geometry.attributes.position.count) }); })()"""
# a maquete desenhada como a câmera vai mostrar (luz do dia, de cima e de lado), por cima da tela, para a foto
DESENHAR = """(async () => { const T = await import('three'), M = await import('./maquete.js');
  const c = document.createElement('canvas'); c.id = 'foto-maquete'; c.style.cssText = 'position:fixed;inset:0;z-index:999;width:100vw;height:100vh';
  document.body.appendChild(c); const r = new T.WebGLRenderer({ canvas: c, antialias: true }); r.setSize(innerWidth, innerHeight, false);
  r.setClearColor(0xd9d4cb);
  const cotas = M.cotasDaMaquete(window._maq);
  const { cena, chao, refazerSombra } = await M.cenaDaMesa(r, { situacoes: [{ grupo: window._maq.grupo }], cotas,
    sol: window.visor._luz ? window.visor._luz.uSol.value.toArray() : null });
  refazerSombra(1);
  const cam = new T.PerspectiveCamera(40, innerWidth / innerHeight, 0.01, 20); cam.position.set(0.55, 0.5, 0.75); cam.lookAt(0, 0.04, 0);
  const g = r.getContext(), w = g.drawingBufferWidth, h = g.drawingBufferHeight, px = new Uint8Array(w * h * 4);
  const soma = () => { g.readPixels(0, 0, w, h, g.RGBA, g.UNSIGNED_BYTE, px); let t = 0; for (let k = 0; k < px.length; k += 4) t += px[k] + px[k + 1] + px[k + 2]; return t / (w * h * 3); };
  chao.visible = false; r.shadowMap.needsUpdate = true; r.render(cena, cam); const sem = soma();
  chao.visible = true; r.shadowMap.needsUpdate = true; r.render(cena, cam); const com = soma();
  return JSON.stringify({ sombra: sem - com, cotas: cotas ? cotas.userData.textos : [] }); })()"""
USDZ = """(async () => { const M = await import('./maquete.js'); const b = await M.usdz(window._maq.grupo);
  const u = new Uint8Array(await b.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768));
  return btoa(s); })()"""

navs = []
try:
    for _ in range(40):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    p1, perf1, pc = chrome(1400, 860, 1, False); navs.append((p1, perf1))
    pc.navegar(base + "/acesso-celular", limite=60)
    esperar(pc, "!!document.getElementById('interruptor')", 20)
    pc.avaliar("document.getElementById('interruptor').click()")
    ok(esperar(pc, "!!document.querySelector('#qr svg')", 20), "o acesso pelo celular ligado no PC")
    url = pc.avaliar("document.getElementById('endereco').textContent") or ""
    codigo = url.split("?c=")[1].split("http")[0].strip() if "?c=" in url else ""
    p2, perf2, ap = chrome(390, 844, 3, True); navs.append((p2, perf2))
    ap.navegar(cel + "/celular/parear?c=" + codigo, limite=30)
    ap.navegar(cel + "/celular/#/p/obra-maquete/modelo", limite=30)
    t0 = time.time()
    # com a obra real na pasta, o PC prepara o pacote dela também, e a fila demora
    ok(esperar(ap, ABERTO, 600 if REAL else 120), "o 3D da obra abre no celular (%.0f s)" % (time.time() - t0))

    # o atalho logo abaixo do olho (Vistas) — usuário, 20/10: "um botão abaixo do olho para facilitar o acesso"
    ok(ap.avaliar("(() => { const b = [...document.querySelectorAll('.ferramentas button')].map(x => x.dataset.f); return b.indexOf('maquete') === b.indexOf('vistas') + 1; })()"),
       "o botão da maquete fica logo abaixo do olho")
    ap.avaliar("window.ultimaMaquete = null")
    tocar(ap, "[data-f=maquete]")
    ok(esperar(ap, "!!window.ultimaMaquete && !!document.getElementById('ra-acoes')", 30), "tocar nele monta a maquete da obra")
    # 1. Vistas → Maquete na mesa (o Chrome sem janela não tem realidade aumentada: o aviso)
    ap.avaliar("document.querySelector('[data-f=vistas]').click()")
    ok(esperar(ap, "!!document.getElementById('ra-obra')", 5), "Vistas tem a Maquete na mesa")
    tocar(ap, "#ra-obra")
    ok(esperar(ap, "!!window.ultimaMaquete && !!document.getElementById('ra-acoes')", 30), "a maquete é montada no aparelho")
    esp = json.loads(ap.avaliar(ESPERADO))
    um = ap.avaliar("JSON.stringify(window.ultimaMaquete)")
    um = json.loads(um) if um else {}
    ok(um.get("pecas") == esp["n"] and esp["n"] >= 3, f"leva as peças à vista ({um.get('pecas')} de {esp['n']}), sem a camada desligada (os parafusos)")
    ok(um.get("deFora") == esp["peq"], f"as peças menores que 80 mm ficam de fora ({um.get('deFora')} de {esp['peq']})")
    ok(all(abs(a - b) < 0.002 for a, b in zip(um.get("medidas", [0, 0, 0]), esp["medidas"])), f"as medidas na obra ({um.get('medidas')} × {esp['medidas']})")
    ok(um.get("como") is None and "não abre realidade aumentada" in (ap.avaliar("document.getElementById('folha').innerText") or ""),
       "sem realidade aumentada no aparelho: o aviso diz o que usar")
    foto(ap, "celular_maquete_aviso.png")
    cx = json.loads(ap.avaliar(CAIXA))
    ok(abs(cx["lado"] - 0.6) < 1e-3, f"o lado maior da maquete é 0,6 m ({cx['lado']:.4f})")
    ok(abs(cx["chao"]) < 1e-4 and abs(cx["cx"]) < 1e-3 and abs(cx["cz"]) < 1e-3, f"no chão e no centro (chão {cx['chao']:.5f}, centro {cx['cx']:.4f}, {cx['cz']:.4f})")
    escala = 0.6 / max(esp["medidas"])
    ok(abs(cx["altura"] - esp["medidas"][2] * escala) < 1e-3, f"a altura da obra (z) vira o Y da maquete ({cx['altura']:.4f})")
    ok(cx["normais"], "toda malha tem a normal de cada vértice (as quinas vivas)")
    # passando do limite, as peças pesadas vão com a forma de fora (a caixa justa): nenhuma sai, a caixa da obra não muda
    # no limite de 12 triângulos por peça, todas viram caixa; a da diagonal (a malha da cor dela) tem os lados de uma barra
    SIMPL = """(async () => { const M = await import('./maquete.js'), T = await import('three'); const v = window.visor;
      const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), { limite: %d });
      const s = new T.Box3().setFromObject(r.grupo).getSize(new T.Vector3());
      const diag = r.grupo.children.find(o => /Cor_ff(72|00)ff/.test(o.name)), p = diag ? diag.geometry.attributes.position : null;
      let lados = [];
      if (p) { const q0 = new T.Vector3().fromBufferAttribute(p, 0), d = [];
        for (let k = 1; k < p.count; k++) { const x = new T.Vector3().fromBufferAttribute(p, k).distanceTo(q0); if (x > 1e-6 && !d.some(y => Math.abs(y - x) < 1e-6)) d.push(x); }
        d.sort((a, b) => a - b); lados = [d[0], d[1], Math.sqrt(Math.max(0, d[d.length - 1] ** 2 - d[0] ** 2 - d[1] ** 2))]; }
      return JSON.stringify({ pecas: r.pecas, simplificadas: r.simplificadas, triangulos: r.triangulos, deFora: r.deFora, x: s.x, y: s.y, z: s.z,
        lados, mm: 1000 * r.escala }); })()""" % (12 * esp["n"])
    sp = json.loads(ap.avaliar(SIMPL) or "{}")
    cheia = json.loads(ap.avaliar("""(async () => { const T = await import('three'); const s = new T.Box3().setFromObject(window._maq.grupo).getSize(new T.Vector3());
      return JSON.stringify([s.x, s.y, s.z, window._maq.triangulos]); })()""") or "[0,0,0,0]")
    ok(sp.get("simplificadas", 0) > 0 and sp.get("pecas") == esp["n"] and sp.get("deFora") == 0 and sp.get("triangulos", 1e9) <= 12 * esp["n"],
       f"no limite de {12 * esp['n']} triângulos (a maquete cheia tem {cheia[3]}): {sp.get('simplificadas')} peças simplificadas, nenhuma de fora ({sp.get('triangulos')} triângulos)")
    lados = [round(x * sp.get("mm", 0)) for x in sp.get("lados", [])]
    ok(len(lados) == 3 and lados[2] > 4000 and lados[1] < 260, f"a diagonal simplificada é uma barra na direção dela, não uma placa (lados {lados} mm)")
    # a caixa girada de uma peça pode passar uns décimos da caixa dela alinhada à obra
    ok(all(abs(sp.get(k, 0) - cheia[j]) < 0.003 for j, k in enumerate("xyz")), f"e a caixa da obra é a mesma ({sp.get('x')}, {sp.get('y')}, {sp.get('z')} × {cheia[:3]})")

    dz = json.loads(ap.avaliar(DESENHAR) or "{}"); foto(ap, "celular_maquete_desenho.png"); ap.avaliar("document.getElementById('foto-maquete').remove()")
    ok(dz.get("sombra", 0) > 0.3, f"a maquete faz sombra na mesa (a imagem escurece {dz.get('sombra', 0):.2f} com o chão de sombra)")
    # as arestas do 3D da tela (o caminho do Android)
    # e todas as camadas, cada uma na sua malha, ligadas como na tela (os parafusos desligados): ligar e desligar na câmera
    AR = """(async () => { const M = await import('./maquete.js'); const v = window.visor;
      const ch = v.cabecalho.camadas.findIndex(c => c.nome === 'Chapas'); v.mostrarCamada(ch, false);
      const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), { limite: M.LIMITES.webxr, arestas: true, todas: true });
      v.mostrarCamada(ch, true);
      const linhas = r.grupo.children.filter(o => o.isLineSegments).reduce((n, o) => n + o.geometry.attributes.position.count / 2, 0);
      const vis = (nome) => r.grupo.children.filter(o => o.userData.camada === nome).map(o => o.visible);
      M.aplicarVisiveis(r.grupo, new Set(['camada:Vigas', 'camada:Parafusos']));
      const desl = { vigas: vis('Vigas'), chapas: vis('Chapas'), parafusos: vis('Parafusos') };
      M.aplicarVisiveis(r.grupo, new Set());
      return JSON.stringify({ arestas: r.arestas, linhas, pecas: r.pecas, camadas: r.camadas, desl, ligadas: vis('Vigas') }); })()"""
    ar = json.loads(ap.avaliar(AR) or "{}")
    ok(ar.get("arestas", 0) > 50 and ar.get("linhas") == ar.get("arestas"), f"no Android a maquete leva as arestas do 3D ({ar.get('arestas')})")
    cams = {c["nome"]: c["ligada"] for c in ar.get("camadas", [])}
    ok(cams.get("Chapas") is False and cams.get("Vigas") is True and "Parafusos" not in cams,
       f"todas as camadas vão, ligadas como na tela — Chapas desligada na tela vai desligada; os parafusos, pequenos, ficam de fora ({cams})")
    d = ar.get("desl", {})
    ok(d.get("vigas") and not any(d["vigas"]) and d.get("chapas") and all(d["chapas"]) and all(ar.get("ligadas", [False])),
       f"desligar Vigas esconde só as malhas dela, e ligar traz de volta ({d})")
    COTAS = """(async () => { const M = await import('./maquete.js'); const v = window.visor;
      const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), { limite: M.LIMITES.webxr, todas: true });
      const mn = [1e12, 1e12, 1e12], mx = [-1e12, -1e12, -1e12];
      v.fichas.forEach((f, i) => { const b = f.b; if (i >= v.nPecas || !b || Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) < 80) return;
        for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], b[k]); mx[k] = Math.max(mx[k], b[k + 3]); } });
      const c = M.cotasDaMaquete(r);
      // cada valor em cima da linha da sua cota: o de x no meio da linha da frente, deitado; o da altura em pé
      const T = await import('three'); c.updateMatrixWorld(true);
      const normal = (nome) => new T.Vector3(0, 0, 1).applyQuaternion(c.getObjectByName(nome).getWorldQuaternion(new T.Quaternion())).toArray().map(x => Math.round(x * 1000) / 1000);
      const cx = c.getObjectByName('Cota_x').position, q = r.quadro;
      const meioX = [((mn[0] + mx[0]) / 2 - q.cx) * q.s, 0, null];
      const dir = (nome) => new T.Vector3(1, 0, 0).applyQuaternion(c.getObjectByName(nome).quaternion).toArray().map(x => Math.round(x * 1000) / 1000);
      const sobre = { nx: normal('Cota_x'), ny: normal('Cota_y'), nz: normal('Cota_z'), dx: dir('Cota_x'), dy: dir('Cota_y'), dz: dir('Cota_z'),
                      xNoMeio: Math.abs(cx.x - meioX[0]) < 0.002 && Math.abs(cx.y - 0.001) < 1e-4 };
      M.aplicarVisiveis(c, new Set(['piso:cotas']));
      return JSON.stringify({ textos: c.userData.textos, min: r.cotas.min, max: r.cotas.max, mn, mx, some: c.visible, sobre }); })()"""
    ct = json.loads(ap.avaliar(COTAS) or "{}")
    perto = all(abs(a - b) <= 2 for a, b in zip(ct.get("min", []) + ct.get("max", []), ct.get("mn", []) + ct.get("mx", [])))
    m = lambda k: f"{(ct['mx'][k] - ct['mn'][k]) / 1000:.2f}".replace(".", ",") + " m"
    # o lado maior é o comprimento (na Kaefer, o y: 38,65 m), e ele vem primeiro
    if ct.get("mx"):
        lx, ly = ct["mx"][0] - ct["mn"][0], ct["mx"][1] - ct["mn"][1]
        esperado = ([f"Comprimento {m(0)}", f"Largura {m(1)}"] if lx >= ly else [f"Comprimento {m(1)}", f"Largura {m(0)}"]) + [f"Altura {m(2)}"]
    else:
        esperado = []
    ok(perto and ct.get("textos") == esperado, f"as cotas principais: {ct.get('textos')} (a caixa das peças: {esperado})")
    so = ct.get("sobre", {})
    ok(so.get("nx") in ([0, 1, 0], [-0.0, 1, 0]) and so.get("ny") in ([0, 1, 0], [-0.0, 1, 0]) and so.get("dx") == [1, 0, 0] and so.get("dy") == [0, 0, -1]
       and abs(so.get("nz", [0, 0, 0])[1]) < 1e-3 and so.get("dz") == [0, 1, 0] and so.get("xNoMeio"),
       f"cada valor em cima da linha da cota, na direção dela: deitados no chão ao longo do comprimento e da largura, a altura em pé ({so})")
    ok(ct.get("some") is False, "desligar as cotas esconde as cotas")
    GIRO = """(async () => { const M = await import('./maquete.js'); const g = M.giroPelaGravidade;
      return JSON.stringify([g(9.8, 0.4, 0), g(-9.8, 0.3, 0), g(0.4, 9.8, 90), g(5, 5, 90), g(1, 2, -90), g(0.5, 9.7, 0)]); })()"""
    ok(json.loads(ap.avaliar(GIRO) or "[]") == [90, -90, 0, 90, -90, 0],
       f"os menus giram com o celular deitado, para um lado ou para o outro, com folga no meio do caminho ({ap.avaliar(GIRO)})")
    # o desenho do piso na maquete: eixos e níveis no quadro dela, ligáveis
    PISO = """(async () => { const M = await import('./maquete.js'), T = await import('three');
      const dados = { segmentos: [[0, 0, 10000, 0]], eixos: [{ nome: 'A', a: [0, 0, 0], b: [0, 8000, 0] }, { nome: '1', a: [0, 0, 0], b: [10000, 0, 0] }],
                      niveis: [{ nome: '+3,00', z: 3000 }] };
      const piso = await M.pisoDaMaquete(dados, { cx: 5000, cy: 4000, z0: 0, s: 0.001 }, [0, 0, 0]);
      piso.updateMatrixWorld(true);
      const caixa = (nome) => { const b = new T.Box3(); piso.userData.ref.getObjectByName(nome).traverse(o => { if (o.isLineSegments) b.expandByObject(o); }); return [b.min.toArray(), b.max.toArray()]; };
      const niv = caixa('niveis'), eix = caixa('eixos');
      M.aplicarVisiveis(piso, new Set(['piso:eixos']));
      return JSON.stringify({ partes: piso.userData.partes, niv, eix, eixosVisiveis: piso.userData.ref.getObjectByName('eixos').visible,
        niveisVisiveis: piso.userData.ref.getObjectByName('niveis').visible }); })()"""
    pz = json.loads(ap.avaliar(PISO) or "{}")
    ok(pz.get("partes") == ["arquitetonico", "eixos", "niveis"], f"o piso leva o arquitetônico, os eixos e os níveis ({pz.get('partes')})")
    niv = pz.get("niv", [[0, 0, 0], [0, 0, 0]])
    ok(abs(niv[1][1] - 3.0) < 0.05 and abs(niv[0][0] + 5.0) < 0.3, f"o nível +3,00 a 3 m de altura na maquete de 1:1000, no quadro dela ({niv})")
    ok(pz.get("eixosVisiveis") is False and pz.get("niveisVisiveis") is True, "desligar os eixos esconde só eles")
    # 2. o .usdz do iPhone
    dados = base64.b64decode(ap.avaliar(USDZ) or "")
    z = zipfile.ZipFile(io.BytesIO(dados))
    nomes = z.namelist()
    ok(nomes and nomes[0] == "model.usda", f"o model.usda é o primeiro arquivo ({nomes[:2]})")
    ok(all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()), "o zip sem compressão (o que o Quick Look exige)")
    alinhados = []
    for i in z.infolist():
        n_nome, n_extra = int.from_bytes(dados[i.header_offset + 26:i.header_offset + 28], "little"), int.from_bytes(dados[i.header_offset + 28:i.header_offset + 30], "little")
        alinhados.append((i.header_offset + 30 + n_nome + n_extra) % 64 == 0)
    ok(all(alinhados), f"cada arquivo começa em múltiplo de 64 bytes ({alinhados})")
    modelo = z.read("model.usda").decode("utf-8")
    ok('upAxis = "Y"' in modelo and "metersPerUnit = 1" in modelo, "Y para cima, em metros")
    geos = [n for n in nomes if n.startswith("geometries/")]
    ok(len(geos) == cx["malhas"], f"uma malha por cor ({len(geos)} arquivos, {cx['malhas']} malhas)")
    pontos = sum(z.read(n).decode("utf-8").split("point3f[] points = [", 1)[1].split("]", 1)[0].count("(") for n in geos)
    ok(pontos == cx["pontos"], f"os pontos todos no arquivo ({pontos} de {cx['pontos']})")
    print(f"        .usdz da obra de teste: {len(dados) / 1024:.0f} kB")

    # a camada dos parafusos ligada: os 60 parafusos ficam de fora (pequenos), a contagem acompanha
    ap.avaliar("(() => { const v = window.visor, i = v.cabecalho.camadas.findIndex(c => c.nome === 'Parafusos'); v.mostrarCamada(i, true); return 1; })()")
    ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
    esperar(ap, "!!document.getElementById('ra-obra')", 5)
    tocar(ap, "#ra-obra")
    esperar(ap, "!!window.ultimaMaquete && !!document.getElementById('ra-acoes')", 30)
    esp2 = json.loads(ap.avaliar(ESPERADO))
    um2 = json.loads(ap.avaliar("JSON.stringify(window.ultimaMaquete)") or "{}")
    ok(esp2["peq"] >= esp["peq"] + 60 and um2.get("deFora") == esp2["peq"] and um2.get("pecas") == esp["n"],
       f"ligados os parafusos: eles ficam de fora e o resto não muda ({um2.get('deFora')} de fora, {um2.get('pecas')} peças)")

    # 3. a ficha → Na mesa: só o conjunto da peça
    alvo = ap.avaliar("visor.fichas.findIndex(f => f.pc)")
    ap.avaliar("document.getElementById('folha').hidden = true")
    conj = json.loads(ap.avaliar(f"(async () => {{ const M = await import('./maquete.js'); return JSON.stringify(M.conjuntoDa(window.visor, {alvo})); }})()") or "{}")
    pcs = json.loads(ap.avaliar(f"JSON.stringify(visor.fichas.map((f, i) => i).filter(i => visor.fichas[i].pc === visor.fichas[{alvo}].pc))"))
    ok(alvo >= 0 and sorted(conj.get("ids", [])) == pcs and conj.get("nome") == "TESOURA 1",
       f"o conjunto da peça da montagem pela planta: {conj.get('nome')} ({len(conj.get('ids', []))} peças)")
    # o conjunto do IFC (a mesma marca repetida pela obra): só a cópia que se toca a partir da peça
    teste = """(async () => { const M = await import('./maquete.js');
      const caixa = (x, y) => [x, y, 0, x + 1000, y + 100, 100];
      const fichas = [{ cj: 'T1', b: caixa(0, 0) }, { cj: 'T1', b: caixa(1010, 0) }, { cj: 'T1', b: caixa(2020, 0) },
                      { cj: 'T1', b: caixa(0, 9000) }, { cj: 'T1', b: caixa(1010, 9000) }, { cj: 'T2', b: caixa(0, 110) }];
      return JSON.stringify(M.conjuntoDa({ fichas, nPecas: fichas.length }, 1).ids.sort()); })()"""
    cj = ap.avaliar(teste)
    ok(json.loads(cj or "[]") == [0, 1, 2], f"o conjunto que se repete: só a cópia em volta da peça ({cj})")
    # pela tela: a ficha da peça tem o Na mesa
    ap.avaliar(f"(() => {{ const v = window.visor; const r = v.tela.getBoundingClientRect(); const [x, y] = v.paraTela({alvo}); window._toque = [x + r.left, y + r.top]; return 1; }})()")
    xy = ap.avaliar("window._toque")
    ap.cmd("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": xy[0], "y": xy[1]}])
    ap.cmd("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    if esperar(ap, "!!document.getElementById('na-mesa')", 10):
        ok(True, "a ficha da peça tem o Na mesa")
        ap.avaliar("window.ultimaMaquete = null")
        tocar(ap, "#na-mesa")
        ok(esperar(ap, "!!window.ultimaMaquete && !!document.getElementById('ra-acoes')", 30), "Na mesa monta a maquete do conjunto")
        um3 = json.loads(ap.avaliar("JSON.stringify(window.ultimaMaquete)") or "{}")
        tocada = ap.avaliar("visor.selecionada")
        conj3 = json.loads(ap.avaliar(f"(async () => {{ const M = await import('./maquete.js'); return JSON.stringify(M.conjuntoDa(window.visor, {tocada if isinstance(tocada, int) else -1}).ids); }})()") or "[]")
        ok(um3.get("pecas") == len(conj3) and um3.get("pecas", 0) >= 1, f"só as peças do conjunto da peça tocada ({um3.get('pecas')} de {len(conj3)})")
    else:
        ok(False, "a ficha da peça tem o Na mesa")

    # 4. iPhone: o link rel="ar" com o .usdz (o Safari abre o Quick Look ao tocar)
    ap.avaliar("""(() => { const o = DOMTokenList.prototype.supports; window._sup = o;
      DOMTokenList.prototype.supports = function (t) { return t === 'ar' ? true : o.call(this, t); }; return 1; })()""")
    ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
    esperar(ap, "!!document.getElementById('ra-obra')", 5)
    tocar(ap, "#ra-obra")
    ok(esperar(ap, "!!document.querySelector('#ra-acoes a[rel=ar]')", 30), "iPhone: aparece o Abrir na câmera")
    ok(ap.avaliar("(() => { const a = document.querySelector('#ra-acoes a[rel=ar]'); return a.href.startsWith('blob:') && a.firstElementChild && a.firstElementChild.tagName === 'IMG'; })()"),
       "é o link rel=\"ar\" com o .usdz e a imagem dentro (o que o Safari pede)")
    ok((ap.avaliar("window.ultimaMaquete.como") == "quicklook") and (ap.avaliar("window.ultimaMaquete.bytes") or 0) > 1000, "o .usdz feito no aparelho")
    foto(ap, "celular_maquete_iphone.png")
    ap.avaliar("DOMTokenList.prototype.supports = window._sup")

    # Android: o botão que abre a câmera; a câmera recusada não deixa nada por cima da tela
    ap.avaliar("""(() => { Object.defineProperty(navigator, 'xr', { configurable: true, value: { isSessionSupported: async m => m === 'immersive-ar',
      requestSession: async () => { throw new Error('sem câmera no teste'); } } }); return 1; })()""")
    ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
    esperar(ap, "!!document.getElementById('ra-obra')", 5)
    tocar(ap, "#ra-obra")
    ok(esperar(ap, "!!document.querySelector('#ra-acoes button.forte') && window.ultimaMaquete && window.ultimaMaquete.como === 'webxr'", 30),
       "Android: aparece o Abrir na câmera")
    tocar(ap, "#ra-acoes button.forte")
    ok(esperar(ap, "(document.getElementById('folha').innerText || '').includes('sem câmera no teste')", 10)
       and not ap.avaliar("!!document.getElementById('ra-sobre')"), "a câmera recusada: o aviso, e nada fica por cima da tela")

    # a câmera aberta (uma sessão que não termina): os botões e o painel de camadas, e o celular deitado (o sensor) gira tudo
    ap.avaliar("""(() => { Object.defineProperty(navigator, 'xr', { configurable: true, value: { isSessionSupported: async m => m === 'immersive-ar',
      requestSession: () => new Promise(() => {}) } }); return 1; })()""")
    ap.avaliar("window.ultimaMaquete = null")
    tocar(ap, "[data-f=maquete]")
    # a folha da maquete nova (a de antes ainda pode estar na tela enquanto esta monta)
    esperar(ap, "!!window.ultimaMaquete && window.ultimaMaquete.como === 'webxr' && !!document.querySelector('#ra-acoes button.forte')", 60)
    tocar(ap, "#ra-acoes button.forte")
    ok(esperar(ap, "!!document.querySelector('#ra-sobre [data-ra=camadas]')", 10), "na câmera: os botões por cima da imagem")
    ap.avaliar("document.querySelector('#ra-sobre [data-ra=camadas]').click()")
    ok(esperar(ap, "!document.querySelector('#ra-sobre .ra-painel').hidden && [...document.querySelectorAll('#ra-sobre .ra-linha')].some(l => l.textContent.includes('Cotas principais'))", 5),
       "o painel Camadas tem as cotas principais")
    DENTRO = """(() => { const fora = []; for (const b of document.querySelectorAll('#ra-sobre button, #ra-sobre .ra-painel, #ra-sobre .ra-dica')) {
      const r = b.getBoundingClientRect(); if (r.left < -1 || r.top < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1) fora.push(b.dataset.ra || b.className); }
      return JSON.stringify(fora); })()"""
    ok(json.loads(ap.avaliar(DENTRO) or '["?"]') == [], "em pé, tudo dentro da tela")
    foto(ap, "celular_maquete_camera_em_pe.png")
    for x, giro in ((9.8, "90"), (-9.8, "-90")):
        ap.avaliar(f"window.dispatchEvent(new DeviceMotionEvent('devicemotion', {{ accelerationIncludingGravity: {{ x: {x}, y: 0.3, z: 0.5 }} }})); 1")
        ok(esperar(ap, f"document.querySelector('#ra-sobre .ra-giro').dataset.giro === '{giro}'", 3), f"deitado para o lado {giro}°: os botões giram")
        ap.drenar(0.5)
        fora = json.loads(ap.avaliar(DENTRO) or '["?"]')
        ok(fora == [], f"deitado ({giro}°), tudo dentro da tela ({fora})")
        foto(ap, f"celular_maquete_camera_deitado_{giro.replace('-', 'menos')}.png")
    ap.avaliar("window.dispatchEvent(new DeviceMotionEvent('devicemotion', { accelerationIncludingGravity: { x: 0.2, y: 9.8, z: 0.5 } })); 1")
    ok(esperar(ap, "document.querySelector('#ra-sobre .ra-giro').dataset.giro === '0'", 3), "em pé de novo: os botões voltam")
    ap.avaliar("document.getElementById('ra-sobre').remove(); 1")

    # a cobertura retrátil: as duas situações no mesmo quadro — a parte fixa no mesmo lugar, a parte móvel não
    ap.navegar(cel + "/celular/#/p/cobertura/modelo", limite=30)
    ok(esperar(ap, "document.getElementById('titulo') && document.getElementById('titulo').textContent === 'Cobertura retrátil' && " + ABERTO, 120),
       "a cobertura retrátil abre no celular")
    SIT = """(async () => { const M = await import('./maquete.js'), T = await import('three'); const v = window.visor;
      const op = { limite: M.LIMITES.webxr, todas: true };
      const r1 = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), op);
      const s = v.outrasSituacoesRA[0], fichas = (await s.pecas()).pecas, buf2 = await (await fetch(s.modelo)).arrayBuffer();
      const w = M.visorDaOutra(v, fichas, M.lerCabecalho(buf2).camadas);
      const r2 = await M.montarMaquete(w, buf2, { ...op, quadro: r1.quadro });
      const caixas = (r) => { const m = {}; for (const o of r.grupo.children) { const k = o.userData.camada; m[k] = (m[k] || new T.Box3()).expandByObject(o); }
        return Object.fromEntries(Object.entries(m).map(([k, b]) => [k, [...b.min.toArray(), ...b.max.toArray()].map(x => Math.round(x * 1e4))])); };
      const c1 = caixas(r1), c2 = caixas(r2), iguais = [], mudaram = [];
      for (const k of Object.keys(c1)) (JSON.stringify(c1[k]) === JSON.stringify(c2[k]) ? iguais : mudaram).push(k);
      const pos = new Map(v.fichas.map((f, i) => [f.id, i]));
      const cores = fichas.every((f, j) => { const i = pos.get(f.id); return i === undefined || [0, 1, 2].every(k => w.corBase[j * 3 + k] === v.corBase[i * 3 + k]); });
      return JSON.stringify({ rotulos: [v.situacaoRA.rotulo, s.rotulo], iguais, mudaram, escalas: [r1.escala, r2.escala], pecas: [r1.pecas, r2.pecas], cores }); })()"""
    st = json.loads(ap.avaliar(SIT) or "{}")
    ok(st.get("rotulos") == ["Aberta", "Retraída"], f"as situações: {st.get('rotulos')}")
    ok(st.get("iguais") and st.get("mudaram") and st.get("escalas", [0, 1])[0] == st.get("escalas", [0, 1])[1] and st.get("pecas", [0, 1])[0] == st.get("pecas", [0, 1])[1],
       f"no mesmo quadro: a parte fixa no mesmo lugar ({st.get('iguais')}), a móvel não ({st.get('mudaram')})")
    ok(st.get("cores") is True, "a outra situação com as cores da tela (pela peça)")
    # Android: as duas situações vão para a câmera
    ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
    esperar(ap, "!!document.getElementById('ra-obra')", 5)
    tocar(ap, "#ra-obra")
    ok(esperar(ap, "!!window.ultimaMaquete && !!document.querySelector('#ra-acoes button.forte')", 60)
       and ap.avaliar("JSON.stringify(window.ultimaMaquete.situacoes)") == '["Aberta","Retraída"]'
       and "troque na câmera" in (ap.avaliar("document.getElementById('folha').innerText") or ""), "Android: aberta e retraída, para trocar na câmera")
    # iPhone: um link por situação
    ap.avaliar("""(() => { const o = DOMTokenList.prototype.supports; window._sup = o;
      DOMTokenList.prototype.supports = function (t) { return t === 'ar' ? true : o.call(this, t); }; return 1; })()""")
    ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
    esperar(ap, "!!document.getElementById('ra-obra')", 5)
    tocar(ap, "#ra-obra")
    dois = esperar(ap, "document.querySelectorAll('#ra-acoes a[rel=ar]').length === 2", 60)
    textos = ap.avaliar("[...document.querySelectorAll('#ra-acoes a[rel=ar]')].map(a => a.textContent.trim()).join('|')")
    ok(dois and textos == "Abrir aberta|Abrir retraída", f"iPhone: Abrir aberta e Abrir retraída ({textos})")
    foto(ap, "celular_maquete_cobertura_iphone.png")
    ap.avaliar("DOMTokenList.prototype.supports = window._sup")

    # obra real (opcional): o tamanho e o tempo da maquete inteira — pelo caminho do iPhone na tela (sem a simulação do
    # Android dos passos de cima) e, depois, pelo do Android
    ap.avaliar("Object.defineProperty(navigator, 'xr', { configurable: true, value: undefined }); 1")
    if REAL:
        ap.navegar(cel + "/celular/#/p/obra-real/modelo", limite=30)
        t0 = time.time()
        nome_real = json.load(open(os.path.join(REAL, "projeto.json"), encoding="utf-8")).get("nome", "")
        ok(esperar(ap, "document.getElementById('titulo') && document.getElementById('titulo').textContent === %s && %s" % (json.dumps(nome_real), ABERTO), 600),
           "a obra real abre no celular (%.0f s)" % (time.time() - t0))
        ap.avaliar("window.ultimaMaquete = null; document.querySelector('[data-f=vistas]').click()")
        esperar(ap, "!!document.getElementById('ra-obra')", 5)
        t0 = time.time()
        tocar(ap, "#ra-obra")
        ok(esperar(ap, "!!window.ultimaMaquete && !!document.getElementById('ra-acoes')", 180), "a maquete da obra real (%.1f s)" % (time.time() - t0))
        um = json.loads(ap.avaliar("JSON.stringify(window.ultimaMaquete)") or "{}")
        esp = json.loads(ap.avaliar(ESPERADO))
        ok(um.get("pecas") == esp["n"] and um.get("deFora") == esp["peq"],
           f"obra real: vão todas as peças à vista ({um.get('pecas')} de {esp['n']}); de fora só as pequenas ({um.get('deFora')} de {esp['peq']})")
        cx = json.loads(ap.avaliar(CAIXA))
        ap.cmd("Emulation.setDeviceMetricsOverride", width=900, height=700, deviceScaleFactor=1, mobile=True)
        ap.avaliar(DESENHAR); foto(ap, "celular_maquete_obra_real.png"); ap.avaliar("document.getElementById('foto-maquete').remove()")
        t0 = time.time()
        dados = base64.b64decode(ap.avaliar(USDZ) or "")
        print(f"        obra real: {um.get('pecas')} peças, {um.get('deFora')} de fora, {um.get('simplificadas')} simplificadas, {um.get('triangulos')} triângulos, 1:{um.get('escala')}, "
              f".usdz {len(dados) / 1048576:.1f} MB em {time.time() - t0:.1f} s")
        ok(um.get("triangulos", 0) <= 300000 and len(dados) > 0, "a obra real cabe no limite de triângulos")
        # o caminho do Android: quase inteira, com as arestas — a foto com a luz da maquete
        t0 = time.time()
        andr = json.loads(ap.avaliar("""(async () => { const M = await import('./maquete.js'); const v = window.visor;
          const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), { limite: M.LIMITES.webxr, arestas: true, todas: true });
          window._maq = r; return JSON.stringify({ pecas: r.pecas, triangulos: r.triangulos, arestas: r.arestas, simplificadas: r.simplificadas, deFora: r.deFora }); })()""") or "{}")
        print(f"        Android: {andr.get('pecas')} peças, {andr.get('simplificadas')} simplificadas, {andr.get('triangulos')} triângulos, "
              f"{andr.get('arestas')} arestas, em {time.time() - t0:.1f} s")
        ok(andr.get("triangulos", 0) <= 1000000 and andr.get("arestas", 0) > 0, "Android: no limite, com as arestas")
        dz = json.loads(ap.avaliar(DESENHAR) or "{}"); foto(ap, "celular_maquete_obra_real_android.png"); ap.avaliar("document.getElementById('foto-maquete').remove()")
        print(f"        cotas da obra real: {dz.get('cotas')}")

    for nome, a in (("computador", pc), ("celular", ap)):
        erros = [m for m in a.console if m[0] in ("error", "excecao") and "401" not in str(m) and "405" not in str(m)]
        ok(not erros, f"sem erros no console do {nome}: {erros[:3]}")
finally:
    for p, perf in navs:
        try: p.kill()
        except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    for _p, perf in navs: shutil.rmtree(perf, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
