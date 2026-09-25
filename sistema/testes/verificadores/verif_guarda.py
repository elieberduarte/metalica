# -*- coding: utf-8 -*-
"""Guarda de modelo antigo: editor aberto antes do "Aplicar furos" não pode gravar por
cima; parafusos acompanham o furo; fantasma opaco no Ver no 3D."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
PORTA = 8789
DADOS = tempfile.mkdtemp(prefix="metalica_gd_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
def get(rota):
    return json.load(urllib.request.urlopen(base + rota, timeout=600))
def post(rota, corpo):
    return json.load(urllib.request.urlopen(urllib.request.Request(base + rota, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"}), timeout=600))
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)
def modelo():
    return get("/api/projetos/compressores/modelo")["documento"]
def p77(doc):
    ch = [e for e in doc["entidades"] if e.get("tipo") == "chapa" and ((e.get("atributos") or {}).get("marcas") or {}).get("posicao") == "P77"]
    return sorted((round(f.get("x", 0), 1), round(f.get("y", 0), 1)) for f in ch[0]["furos"]) if ch else None
def centro(e):
    v = e["vertices"]; return [round(sum(p[i] for p in v) / len(v), 2) for i in range(3)]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_gd_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    r = post("/api/projetos/compressores/detalhar-posicao", {"marca": "P77"})
    nome = r["nome"]
    doc0 = modelo()
    ch0 = next(e for e in doc0["entidades"] if e.get("tipo") == "chapa" and e["atributos"]["marcas"]["posicao"] == "P77")
    # parafusos perto do primeiro furo dessa chapa (no mundo)
    ex, ey, o = ch0["eixo_x"], ch0["eixo_y"], ch0["origem"]
    f0 = ch0["furos"][0]
    w0 = [o[i] + ex[i] * f0["x"] + ey[i] * f0["y"] for i in range(3)]
    fix = [e for e in doc0["entidades"] if e.get("tipo") == "solido" and (e.get("atributos") or {}).get("tipo_ifc") in ("IfcMechanicalFastener", "IfcBuildingElementProxy")]
    perto = [e["id"] for e in fix if sum((centro(e)[i] - w0[i]) ** 2 for i in range(3)) ** 0.5 < 60]
    print("       parafusos a menos de 60 mm do furo 0 da 1ª chapa P77:", len(perto))
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=950, deviceScaleFactor=1, mobile=False)
    # 1) editor "velho" aberto antes de aplicar
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.tamanho > 10 && window.editor._modeloAlterado"): aba.drenar(1.0)
    ok(aba.avaliar("typeof window.editor._modeloAlterado === 'number'"), "editor guardou a data do modelo carregado")
    # 2) aplica furos pela rota (como se fosse o CAD noutra janela): move o furo 0 em +10 x
    d = get("/api/projetos/compressores/desenhos/" + nome)["desenho"]
    for e in d["entidades"]:
        if e.get("camada") == "FURO" and (e.get("atributos") or {}).get("furo") == 0:
            if e["tipo"] == "circulo": e["centro"][0] += 10
            else: e["vertices"] = [[p[0] + 10, p[1]] for p in e["vertices"]]
    ra = post("/api/projetos/compressores/desenhos/%s/aplicar-furos" % nome, {"desenho": d})
    ok(ra["chapas"] == 18 and ra.get("parafusos", 0) >= 1, "aplicar moveu furo e %s parafuso(s) nas 18 chapas" % ra.get("parafusos"))
    doc1 = modelo()
    movidos = [e for e in doc1["entidades"] if e["id"] in perto]
    ok(all(abs(centro(e)[0] - centro(next(x for x in fix if x["id"] == e["id"]))[0]) > 1 or abs(centro(e)[1] - centro(next(x for x in fix if x["id"] == e["id"]))[1]) > 1 for e in movidos) if movidos else False,
       "os parafusos junto do furo 0 mudaram de lugar no modelo (%d)" % len(movidos))
    novo = p77(doc1)
    # 3) o editor velho tenta gravar: recusado, modelo intacto
    aba.avaliar("window.editor._autosavePendente = true; window.editor._autosalvar(); 1"); aba.drenar(1.0)
    t0 = time.time()
    while time.time() - t0 < 60 and aba.avaliar("window.editor._autosalvando"): aba.drenar(0.5)
    ok(p77(modelo()) == novo, "modelo continua com a furação nova depois do autosave do editor velho (%s)" % (novo[:2],))
    ok(aba.avaliar("!!document.querySelector('.aviso.erro, .avisos .erro, [class*=aviso]') && /Recarregue/i.test(document.body.textContent)"), "editor velho avisou para recarregar")
    # 4) editor recarregado grava normalmente
    aba.navegar(base + "/editor?projeto=compressores", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.documento && window.editor.documento.tamanho > 10 && window.editor._modeloAlterado"): aba.drenar(1.0)
    # espera a gravação terminar antes de sair da tela: sair com ela em curso dispara o aviso
    # de edição por gravar (beforeunload, 0.8.12), que é o comportamento certo do editor
    alterado0 = aba.avaliar("window.editor._modeloAlterado")
    aba.avaliar("window.editor._autosavePendente = true; window.editor._autosalvar(); 1"); aba.drenar(1.0)
    t0 = time.time()
    while time.time() - t0 < 120 and aba.avaliar("window.editor._autosalvando || window.editor._autosavePendente"): aba.drenar(0.5)
    ok(aba.avaliar("!window.editor._autosalvando && !window.editor._autosavePendente") and aba.avaliar("window.editor._modeloAlterado") != alterado0,
       "gravação do editor recarregado terminou e o servidor devolveu a data nova do modelo")
    ok(p77(modelo()) == novo and aba.avaliar("!/Recarregue/i.test((document.querySelector('.dica') || {}).textContent || '')"), "editor recarregado grava sem recusa e mantém a furação nova")
    # 5) fantasma opaco
    aba.navegar(base + "/editor?projeto=compressores&destacar=posicao:P77", limite=60)
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar("window.editor && window.editor.selecao && window.editor.selecao.ids.size > 0"): aba.drenar(1.0)
    aba.drenar(2.5)
    ok(aba.avaliar("(() => { const c = window.editor.cena; const m = c._materialFantasma(); return m.transparent === false && c.destaque && c.destaque.size === 18; })()"), "fantasma opaco ligado no Ver no 3D")
    # o 400 do /modelo é a recusa do servidor à gravação do editor velho, provocada no passo 3
    recusas = [m for m in aba.console if m[0] == "error" and "400" in m[1] and "/api/projetos/compressores/modelo" in m[1]]
    erros = [m for m in aba.console if m[0] in ("error", "excecao") and m not in recusas]
    ok(len(recusas) == 1, "uma única recusa (400) do /modelo, a do editor velho: %d" % len(recusas))
    ok(not erros, "sem outros erros no console: %s" % erros[:3])
finally:
    nav.kill(); srv.kill(); shutil.rmtree(perfil, ignore_errors=True)
print("\n%d falha(s)." % len(falhas))
sys.exit(1 if falhas else 0)
