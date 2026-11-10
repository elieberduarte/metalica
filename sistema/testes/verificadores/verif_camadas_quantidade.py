# -*- coding: utf-8 -*-
"""O painel Camadas do modo ver e do editor 3D com a quantidade de cada camada — a do RESUMO DA OBRA.

Usuário, 06/11 (pelo GESTÃO, captura do Hora Certa · Galpão Novo): "criar na ferramenta de camadas uma informação a mais
ao lado, por ex. dos isopainéis, telhas (m²) — perfil, chapa (kg)". Aprovado na imagem do "é assim?" (forma A, duas
colunas: peças e quantidade); o peso é o do resumo da obra ("não posso mostrar para o fornecedor um peso na apresentação e
na proposta outro"); o grupo soma cada unidade separada; a camada escondida continua com a quantidade dela.

Um projeto com a amostra do modelo do Galpão Novo (testes/dados_editor/hora_certa_gn_amostra.json) e o resumo da obra
gerado pela conta de verdade (test_camadas_quantidade._resumo + resumos.gerar_resumos):
  A. modo ver, botão Camadas (clique de verdade): cada camada com a quantidade da rota — Pilares em kg, Telhas em m²,
     Calhas e Cumeeiras em m, as paredes do ARQ em m² —, o grupo "Cobertura" com a soma de cada unidade, e a nota "as mesmas
     da proposta"; a camada escondida continua com a quantidade;
  B. editor 3D, painel Camadas: as mesmas quantidades, e o mesmo total do grupo;
  C. o modelo gravado depois do resumo: a nota avisa e os números ficam (apagados);
  E. o resumo de antes das camadas (o do GN em 06/11: "porque tem várias camadas sem informação?"): o aço com "—" e a
     dica, a nota com o caminho para os Resumos da obra e presa no alto do painel rolado, no modo ver e no editor;
  F. o rodapé do modo ver (usuário, 10/11: "Área obra - Altura - Qtd peças - Peso estrutura"): a área e o peso do resumo
     (os da proposta), a altura do piso ±0,00 dos níveis ao topo do modelo, as peças do modelo; com o modelo mudado depois
     do resumo, o peso diz de quando é;
  D. sem erros no console.
Porta livre, nunca a 8765/8766."""
import base64, io, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_camadas_quantidade import _resumo
from saida import resumos
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_camadas_qtd_")
GRUPO_COB = "Cobertura — telhas, calhas e rufos"

m, R = _resumo()
camadas = json.loads(json.dumps(m["camadas"]))
for c in ("Telhas", "Calhas", "Cumeeiras"):
    camadas[c]["grupo"] = GRUPO_COB
for c in camadas:
    if c.startswith("ARQ"):
        camadas[c]["grupo"] = "ARQUITETÔNICO"
camadas["Calhas"]["visivel"] = False             # a camada escondida continua com a quantidade
pasta = os.path.join(DADOS, "gn")
os.makedirs(os.path.join(pasta, "detalhamento"))
NIVEIS = [{"nome": "Topo da base 906,18", "z": -220.0}, {"nome": "Piso 906,40 (±0,00)", "z": 0.0}, {"nome": "Topo dos pilares 917,05", "z": 10650.0}]
json.dump({"nome": "gn", "tipo": "ifc", "alterado": "2026-11-06T10:00:00", "niveis": NIVEIS}, open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "gn", "unidade": "mm", "entidades": m["entidades"], "camadas": camadas, "materiais": m.get("materiais", {})},
          open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
time.sleep(0.1)
R.update({"projeto": {"nome": "gn"}, "dados": {}})
R["dimensoes"]["area_m2"] = 10653.79                # a amostra não tem eixos: a área da projeção do GN, como o resumo grava
resumos.gerar_resumos(os.path.join(pasta, "detalhamento"), R, imprimir_pdf=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base_url = f"http://localhost:{PORTA}"
falhas = []


def ok(c, msg):
    print(("  ok    " if c else "  FALHA ") + msg, flush=True)
    if not c: falhas.append(msg)


def br(v):
    return f"{round(v):,}".replace(",", ".")


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_camadas_qtd_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base_url + "/api/versao"); break
        except Exception: time.sleep(0.5)
    Q = _json(base_url + "/api/projetos/gn/camadas-quantidade")
    C, A = Q["camadas"], Q["arq"]
    ok(Q["resumo"]["atual"] and Q["resumo"]["tem_camadas"], f"a rota lê o resumo da obra gerado ({Q['resumo']})")
    esperado = {"Pilares": f"{br(C['Pilares']['kg'])} kg", "Placas de base": f"{br(C['Placas de base']['kg'])} kg",
                "Telhas": f"{br(C['Telhas']['m2'])} m²", "Calhas": f"{br(C['Calhas']['m'])} m", "Cumeeiras": f"{br(C['Cumeeiras']['m'])} m",
                "ARQ — Paredes de fachada": f"{br(A['ARQ — Paredes de fachada']['m2'])} m²"}
    grupo_cob = f"{br(C['Telhas']['m2'])} m² · {br(C['Calhas']['m'] + C['Cumeeiras']['m'])} m"
    print("     esperado:", esperado, "| grupo:", grupo_cob)

    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)

    def esperar(expr, limite=90):
        t0 = time.time()
        while time.time() - t0 < limite:
            try:
                v = aba.avaliar(expr)
                if v: return v
            except Exception: pass
            aba.drenar(0.3)
        return None

    def clicar(seletor):
        r = aba.avaliar(f"(() => {{ const b = document.querySelector({json.dumps(seletor)}); if (!b) return null; b.scrollIntoView({{block: 'center'}}); const q = b.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; }})()")
        if not r: return False
        for tipo in ("mousePressed", "mouseReleased"):
            aba.cmd("Input.dispatchMouseEvent", type=tipo, x=r[0], y=r[1], button="left", clickCount=1)
        return True

    def foto(nome):
        img = base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"])
        open(os.path.join(os.path.dirname(__file__), nome), "wb").write(img)

    # --- A. modo ver
    LER_VER = """JSON.stringify((() => { const o = {}; document.querySelectorAll('#painel-corpo .linha-lista').forEach(l => {
        const n = l.querySelector('span'), q = l.querySelector('b.qtd'); if (n && q) o[n.textContent.trim()] = q.textContent.trim(); });
        const nota = document.querySelector('#painel-corpo .nota-qtd');
        const lista = document.querySelector('#painel-corpo .lista-camadas');
        return { linhas: o, nota: nota ? [nota.dataset.situacao, nota.textContent] : null, situacao: lista ? lista.dataset.situacao : null }; })())"""
    aba.navegar(base_url + "/visor3d/ver3d.html?projeto=gn", limite=60)
    ok(bool(esperar("!!(window.ver3dPronto && window.visor && visor.fichas)", 180)), "o modo ver abriu")
    ok(clicar('[data-painel="camadas"]'), "clique no botão Camadas")
    v = json.loads(esperar(f"(() => {{ const r = {LER_VER}; return JSON.parse(r).nota ? r : null; }})()", 30) or "{}")
    print("     modo ver:", v.get("linhas"), v.get("nota"))
    L = v.get("linhas") or {}
    for cam, txt in esperado.items():
        ok(L.get(cam) == txt, f"[modo ver] {cam}: {txt!r} ({L.get(cam)!r})")
    ok(L.get(GRUPO_COB) == grupo_cob, f"[modo ver] o grupo Cobertura soma cada unidade: {grupo_cob!r} ({L.get(GRUPO_COB)!r})")
    ok(v.get("nota") and v["nota"][0] == "atual" and "proposta" in v["nota"][1], f"[modo ver] a nota diz que é o resumo, o mesmo da proposta ({v.get('nota')})")
    ok(aba.avaliar("document.querySelector('#painel').getBoundingClientRect().width") >= 420, "[modo ver] o painel Camadas mais largo, com a coluna")
    foto("camadas_quantidade_ver.png")

    # --- F. o rodapé com as informações rápidas da obra
    z_topo = max([p[2] for e in m["entidades"] if e["tipo"] == "barra" for p in (e["inicio"], e["fim"])]
                 + [v[2] for e in m["entidades"] if e["tipo"] == "solido" for v in e["vertices"]])
    rod = aba.avaliar("document.querySelector('#situacao').textContent") or ""
    print("     rodapé:", rod)
    ok(f"Área {br(R['dimensoes']['area_m2'])} m²" in rod, f"[rodapé] a área do resumo, {br(R['dimensoes']['area_m2'])} m² ({rod!r})")
    ok(f"Estrutura {br(R['numeros']['peso_aco'])} kg" in rod and "antes da última" not in rod,
       f"[rodapé] o peso do resumo, {br(R['numeros']['peso_aco'])} kg — o mesmo do painel e da proposta")
    ok(f"{len(m['entidades'])} peças" in rod, f"[rodapé] as peças do modelo ({len(m['entidades'])})")
    import re as _re
    alt = _re.search(r"Altura ([\d.,]+) m", rod)
    alt_v = float(alt.group(1).replace(".", "").replace(",", ".")) if alt else None
    ok(alt_v is not None and abs(alt_v - z_topo / 1000) <= 0.1,
       f"[rodapé] a altura do piso ±0,00 ao topo do modelo, ~{z_topo / 1000:.2f} m ({alt_v}) — não do pé do chumbador")

    # --- B. editor
    LER_ED = """JSON.stringify((() => { const o = {}; document.querySelectorAll('#painel-camadas .linha').forEach(l => {
        const n = l.querySelector('.nome'), q = l.querySelector('.qtd'); if (n && q) o[n.textContent.trim()] = q.textContent.trim(); });
        const nota = document.querySelector('#painel-camadas .nota-qtd');
        return { linhas: o, nota: nota ? [nota.dataset.situacao, nota.textContent] : null }; })())"""
    aba.navegar(base_url + "/editor?projeto=gn", limite=120)
    ok(bool(esperar("!!(window.editor && editor.documento && editor.documento.tamanho && document.body.dataset.pronto === '1')", 120)), "o editor abriu")
    if not aba.avaliar("(() => { const c = document.querySelector('#painel-camadas'); return !!(c && c.offsetHeight > 0); })()"):
        clicar('section.painel[data-painel="camadas"] .cabecalho')
    e = json.loads(esperar(f"(() => {{ const r = {LER_ED}; return JSON.parse(r).nota ? r : null; }})()", 30) or "{}")
    print("     editor:", e.get("linhas"), e.get("nota"))
    L = e.get("linhas") or {}
    for cam, txt in esperado.items():
        ok(L.get(cam) == txt, f"[editor] {cam}: {txt!r} ({L.get(cam)!r})")
    ok(L.get(GRUPO_COB) == grupo_cob, f"[editor] o grupo Cobertura: {grupo_cob!r} ({L.get(GRUPO_COB)!r})")
    ok(e.get("nota") and e["nota"][0] == "atual", f"[editor] a nota do resumo ({e.get('nota')})")
    foto("camadas_quantidade_editor.png")

    # --- C. o modelo gravado depois do resumo
    futuro = time.time() + 5
    os.utime(os.path.join(pasta, "modelo.json"), (futuro, futuro))
    aba.navegar(base_url + "/visor3d/ver3d.html?projeto=gn", limite=60)
    esperar("!!(window.ver3dPronto && window.visor && visor.fichas)", 180)
    clicar('[data-painel="camadas"]')
    v = json.loads(esperar(f"(() => {{ const r = {LER_VER}; return JSON.parse(r).nota ? r : null; }})()", 30) or "{}")
    ok(v.get("nota") and v["nota"][0] == "velho" and "mudou" in v["nota"][1], f"[modelo mudou] a nota avisa ({v.get('nota')})")
    ok(v.get("situacao") == "velho" and (v.get("linhas") or {}).get("Pilares") == esperado["Pilares"],
       f"[modelo mudou] os números ficam, apagados ({v.get('situacao')}, {(v.get('linhas') or {}).get('Pilares')})")
    rod = aba.avaliar("document.querySelector('#situacao').textContent") or ""
    ok(f"Estrutura {br(R['numeros']['peso_aco'])} kg (resumo de" in rod and "antes da última mudança" in rod,
       f"[modelo mudou] o rodapé diz de quando é o peso ({rod!r})")

    # --- E. o resumo de antes das camadas (o do GN, 05/11 — usuário, 06/11: "porque tem várias camadas sem informação?"): a
    # camada de aço com "—" e a dica, o arquitetônico com o número dele, e a nota com o caminho para os Resumos, presa no alto
    # do painel rolado
    arq_num = os.path.join(pasta, "detalhamento", resumos.ARQ_NUMEROS)
    d = json.load(open(arq_num, encoding="utf-8")); d.pop("camadas", None)
    json.dump(d, open(arq_num, "w", encoding="utf-8"))
    futuro2 = time.time() + 20
    os.utime(arq_num, (futuro2, futuro2))
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=520, deviceScaleFactor=1, mobile=False)
    aba.navegar(base_url + "/visor3d/ver3d.html?projeto=gn", limite=60)
    esperar("!!(window.ver3dPronto && window.visor && visor.fichas)", 180)
    clicar('[data-painel="camadas"]')
    LER_SEM = LER_VER.replace("o[n.textContent.trim()] = q.textContent.trim();", "o[n.textContent.trim()] = [q.textContent.trim(), q.title || ''];")
    v = json.loads(esperar(f"(() => {{ const r = {LER_SEM}; return JSON.parse(r).nota ? r : null; }})()", 30) or "{}")
    L = v.get("linhas") or {}
    print("     sem camadas no resumo:", L, v.get("nota"))
    ok(v.get("nota") and v["nota"][0] == "sem", f"[resumo sem camadas] a nota pede o resumo ({v.get('nota')})")
    ok(all((L.get(c) or ["", ""])[0] == "—" and "Resumo da obra" in (L.get(c) or ["", ""])[1] for c in ("Pilares", "Placas de base")),
       f"[resumo sem camadas] o aço com '—' e a dica do porquê ({L.get('Pilares')}, {L.get('Placas de base')})")
    ok((L.get("ARQ — Paredes de fachada") or [""])[0] == esperado["ARQ — Paredes de fachada"],
       f"[resumo sem camadas] o arquitetônico continua com o número dele ({L.get('ARQ — Paredes de fachada')})")
    href = aba.avaliar("(() => { const a = document.querySelector('#painel-corpo .nota-qtd a'); return a ? a.getAttribute('href') : null; })()")
    ok(href == "/materiais?projeto=gn#resumos", f"[resumo sem camadas] a nota leva aos Resumos da obra ({href})")
    rolou = aba.avaliar("""(() => { const p = document.querySelector('#painel'); p.scrollTop = p.scrollHeight; return p.scrollTop; })()""")
    aba.drenar(0.5)
    pos = aba.avaliar("""(() => { const p = document.querySelector('#painel').getBoundingClientRect(), t = document.querySelector('.painel-topo').getBoundingClientRect(),
        n = document.querySelector('#painel-corpo .nota-qtd').getBoundingClientRect(); return [p.top, t.bottom, n.top, n.bottom, p.bottom]; })()""")
    ok(rolou > 50 and pos and pos[1] - 1 <= pos[2] <= pos[1] + 8 and pos[3] < pos[4],
       f"[resumo sem camadas] com o painel rolado ({rolou} px), a nota fica à vista logo abaixo do título ({pos})")
    foto("camadas_quantidade_sem_resumo.png")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
    aba.navegar(base_url + "/editor?projeto=gn", limite=120)
    esperar("!!(window.editor && editor.documento && editor.documento.tamanho && document.body.dataset.pronto === '1')", 120)
    if not aba.avaliar("(() => { const c = document.querySelector('#painel-camadas'); return !!(c && c.offsetHeight > 0); })()"):
        clicar('section.painel[data-painel="camadas"] .cabecalho')
    e = json.loads(esperar(f"(() => {{ const r = {LER_ED}; return JSON.parse(r).nota ? r : null; }})()", 30) or "{}")
    L = e.get("linhas") or {}
    href = aba.avaliar("(() => { const a = document.querySelector('#painel-camadas .nota-qtd a'); return a ? a.getAttribute('href') : null; })()")
    ok(e.get("nota") and e["nota"][0] == "sem" and L.get("Pilares") == "—" and href == "/materiais?projeto=gn#resumos",
       f"[editor, resumo sem camadas] '—' no aço e o caminho para os Resumos ({L.get('Pilares')!r}, {href})")

    erros = [x for x in aba.console if x[0] in ("error", "excecao") and "favicon" not in str(x)]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.terminate()
    except Exception: pass
    srv.terminate()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS: %d" % len(falhas))
sys.exit(1 if falhas else 0)
