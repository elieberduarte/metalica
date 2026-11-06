# -*- coding: utf-8 -*-
"""A abertura retangular da chapa no EDITOR 3D, e as nervuras da placa de base sem caixa a mais.

OBRA · POSTO N.6, 29/10 (90be457): o furo da Chapa ganhou `forma: "retangular"` — a abertura 250 × 250 do meio da placa
CH5. O servidor (geometria.contorno_do_furo, Chapa.area) já era quadrado; o editor (cena._geometriaChapa) desenhava todo
furo com largura e altura como oblongo — a 250 × 250 virava um círculo de Ø250 — e a área da chapa no editor
(documento.areaDaChapa, o peso da ficha) descontava o círculo (49.087 mm² no lugar de 62.500). Só nas fotos ?render=1 a
abertura saía quadrada, porque a malha do servidor chegava depois e tomava o lugar.

E (OBRA · POSTO N.3, 23/10): as 48 nervuras das CH5 saíam no editor com uma caixa grande embaixo de cada uma. Em 06/11, na
versão do main e no modelo do V2 de hoje, não reproduz mais (a foto da PM6 no modelo inteiro está certa); a trava fica
aqui: cada nervura desenhada pelo lote ocupa só a caixa dela, 6,35 × 70 × 150.

Os dados são os do modelo do Posto V2 (testes/dados_editor/posto_v2_base_pm6.json), nas coordenadas da obra.
  A. a malha que o editor monta para a placa (sem a do servidor): o centro e o canto da abertura (fora do círculo de
     Ø250, dentro do quadrado) abertos; fora do quadrado, chapa;
  B. a área da chapa no editor = a do servidor (550² − 250² − os furos dos chumbadores);
  C. cada nervura desenhada (no lote ou na cena): caixa 6,35 × 70 × 150 (fora de ordem);
  D. sem erros no console.
Sem a correção (git stash de cena.js e documento.js): A e B falham. Porta livre, nunca a 8765/8766."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

DADOS_OBRA = os.path.join(BASE, "testes", "dados_editor", "posto_v2_base_pm6.json")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_abertura_ret_")
m = json.load(open(DADOS_OBRA, encoding="utf-8"))
ents = m["entidades"]
placa = next(e for e in ents if e.get("nome") == "Placa de base CH5")
nervuras = [e["id"] for e in ents if str(e.get("nome", "")).startswith("Nervura")]
ab = next(f for f in placa["furos"] if f.get("forma") == "retangular")
from nucleo3d.modelo import Documento                                   # noqa: E402
AREA = Documento.de_dict({"entidades": [placa]}).entidades[placa["id"]].area   # a do servidor: 550² − 250² − os 8 furos dos chumbadores
assert abs(AREA - 550 * 550 + 250 * 250 + sum(3.141592653589793 * f["diametro"] ** 2 / 4 for f in placa["furos"] if f.get("diametro"))) < 1, AREA

os.makedirs(os.path.join(DADOS, "posto"))
json.dump({"nome": "posto", "tipo": "dxf", "alterado": "2026-11-06T09:00:00"},
          open(os.path.join(DADOS, "posto", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "posto", "unidade": "mm", "entidades": ents, "camadas": m.get("camadas", {}), "materiais": m.get("materiais", {})},
          open(os.path.join(DADOS, "posto", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
# a mesma base 70 vezes, 2 m uma da outra (1.750 peças): o editor desenha pelo lote e as nervuras iguais viram cópias — a
# forma de modelo em que a caixa a mais apareceu (o Posto V2 inteiro, 23/10)
COPIAS = 70
obra = []
for k in range(COPIAS):
    for e in ents:
        e2 = json.loads(json.dumps(e)); e2["id"] = "%s_%02d" % (e["id"], k)
        for campo in ("origem", "inicio", "fim"):
            if campo in e2: e2[campo] = [e2[campo][0] + 2000 * k] + e2[campo][1:]
        obra.append(e2)
nerv_obra = [e["id"] for e in obra if str(e.get("nome", "")).startswith("Nervura")]
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"nome": "obra", "tipo": "dxf", "alterado": "2026-11-06T09:00:00"},
          open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "obra", "unidade": "mm", "entidades": obra, "camadas": m.get("camadas", {}), "materiais": m.get("materiais", {})},
          open(os.path.join(DADOS, "obra", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base_url = f"http://localhost:{PORTA}"
falhas = []


def ok(c, msg):
    print(("  ok    " if c else "  FALHA ") + msg, flush=True)
    if not c: falhas.append(msg)


def cobre(tris, p):
    def cr(o, u, w):
        return (u[0] - o[0]) * (w[1] - o[1]) - (u[1] - o[1]) * (w[0] - o[0])
    for a, b, c in tris:
        d = (cr(a, b, p), cr(b, c, p), cr(c, a, p))
        if all(x > 1e-9 for x in d) or all(x < -1e-9 for x in d):
            return True
    return False


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_abertura_ret_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try: _json(base_url + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)

    def jsj(e, assinc=False):
        corpo = (f"(async () => {{ try {{ return JSON.stringify(await (async () => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()"
                 if assinc else
                 f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = aba.avaliar(corpo)
        r = json.loads(r) if r else None
        if isinstance(r, dict) and r.get("erro"): print("     erro JS:", str(r["erro"])[:400]); return None
        return r

    aba.navegar(base_url + "/editor?projeto=posto", limite=120)
    t0, e = time.time(), None
    while time.time() - t0 < 120:
        e = jsj("const ed = window.editor; return !!(ed && ed.documento && ed.documento.tamanho === %d && document.body.dataset.pronto === '1' && !ed.cena.montando);" % len(ents))
        if e: break
        aba.drenar(0.3)
    ok(bool(e), "o editor abriu com as %d peças da base PM6" % len(ents))
    aba.drenar(1.0)

    # --- A. a malha local da placa (a do editor, sem a do servidor): a face de cima, no plano da chapa
    r = jsj("""const ent = editor.documento.get('%s'), c = editor.cena;
      const f = ent.furos.map(f => `${f.x},${f.y},${f.diametro || ''},${f.largura || ''},${f.altura || ''},${f.angulo || ''},${f.forma || ''}`).join(';');
      const f0 = ent.furos.map(f => `${f.x},${f.y},${f.diametro || ''},${f.largura || ''},${f.altura || ''},${f.angulo || ''}`).join(';');
      for (const k of [...c.cacheGeometria.keys()]) if (k.startsWith('chapa|')) c.cacheGeometria.delete(k);
      const { geom } = c._geometriaChapa(ent);
      const g = geom.index ? geom.toNonIndexed() : geom, p = g.getAttribute('position').array;
      let zmax = -1e9; for (let i = 2; i < p.length; i += 3) zmax = Math.max(zmax, p[i]);
      const tris = [];
      for (let i = 0; i < p.length; i += 9) {
        if ([p[i + 2], p[i + 5], p[i + 8]].every(z => Math.abs(z - zmax) < 1e-3)) tris.push([[p[i], p[i + 1]], [p[i + 3], p[i + 4]], [p[i + 6], p[i + 7]]]);
      }
      return { tris, zmax, origem: c.origemGeometria.get([...c.cacheGeometria.keys()].find(k => k.startsWith('chapa|'))) };""" % placa["id"])
    ok(r is not None and r["tris"], "o editor montou a malha da placa CH5 (%s)" % (r and r.get("origem")))
    if r:
        tris = r["tris"]
        cx, cy, a = ab["x"], ab["y"], ab["largura"] / 2
        dentro = [(cx, cy), (cx + a - 8, cy + a - 8), (cx - a + 8, cy + a - 8), (cx + a - 8, cy - a + 8), (cx - a + 8, cy - a + 8)]
        fora = [(cx + a + 10, cy), (cx, cy - a - 10), (cx + a + 10, cy + a + 10)]
        tampados = [p for p in dentro if cobre(tris, p)]
        ok(not tampados, f"[malha] a abertura é o quadrado 250 × 250: o centro e os 4 cantos abertos (tampados {tampados})")
        sem = [p for p in fora if not cobre(tris, p)]
        ok(not sem, f"[malha] fora do quadrado é chapa ({sem})")
        area = sum(abs((b[0] - aa[0]) * (c[1] - aa[1]) - (b[1] - aa[1]) * (c[0] - aa[0])) / 2 for aa, b, c in tris)
        ok(abs(area - AREA) < 0.01 * AREA, f"[malha] a face de cima tem a área da chapa do servidor ({area:.0f} × {AREA:.0f} mm²)")

    # --- B. a área da chapa no editor (o peso da ficha)
    b = jsj("""const url = performance.getEntriesByType('resource').map(e => e.name).find(n => /nucleo\\/documento\\.js/.test(n));
      const mod = await import(url); return mod.areaDaChapa(editor.documento.get('%s'));""" % placa["id"], assinc=True)
    ok(b is not None and abs(b - AREA) < 1, f"[área] a área da placa no editor = a do servidor, 550² − 250² − os furos ({b} × {AREA:.0f})")

    # --- C. as nervuras no lote: cada uma só a caixa dela (o defeito de 23/10, a caixa grande embaixo)
    def nervuras_certas(ids, rotulo):
        cx = jsj("""const l = editor.cena.lote, ids = %s, out = {};
          for (const id of ids) {
            // no lote (modelo grande) a malha que ele desenha; senão o objeto da cena (em metros)
            let pos = null, esc = 1;
            if (l && editor.cena.emLote) { const g = l._geometria(editor.documento.get(id)); pos = g && g.pos; }
            else {
              const o = editor.cena.objetos.get(id), mesh = o && (o.isMesh ? o : o.children.find(c => c.isMesh));
              if (mesh) { mesh.updateWorldMatrix(true, false); const q = mesh.geometry.getAttribute('position'), v = mesh.position.clone(); pos = [];
                for (let i = 0; i < q.count; i++) { v.fromBufferAttribute(q, i).applyMatrix4(mesh.matrixWorld); pos.push(v.x, v.y, v.z); } esc = 1000; }
            }
            if (!pos) { out[id] = null; continue; }
            const mn = [1e12, 1e12, 1e12], mx = [-1e12, -1e12, -1e12];
            for (let i = 0; i < pos.length; i += 3) for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], pos[i + k]); mx[k] = Math.max(mx[k], pos[i + k]); }
            out[id] = [(mx[0] - mn[0]) * esc, (mx[1] - mn[1]) * esc, (mx[2] - mn[2]) * esc];
          }
          return out;""" % json.dumps(ids))
        erradas = {k: v for k, v in (cx or {}).items() if not v or any(abs(x - y) > 0.2 for x, y in zip(sorted(v), (6.35, 70, 150)))}
        ok(cx is not None and len(cx) == len(ids) and not erradas,
           f"[nervuras, {rotulo}] as {len(ids)} nervuras no lote têm a caixa 6,35 × 70 × 150 (erradas: {list(erradas.items())[:3]})")

    nervuras_certas(nervuras, "base sozinha")

    # --- a mesma trava no modelo grande, desenhado pelo lote
    print("obra: %d peças" % len(obra))
    aba.navegar(base_url + "/editor?projeto=obra", limite=120)
    t0, e = time.time(), None
    while time.time() - t0 < 240:
        e = jsj("const ed = window.editor; return !!(ed && ed.documento && ed.documento.tamanho === %d && document.body.dataset.pronto === '1' && !ed.cena.montando && ed.cena.emLote);" % len(obra))
        if e: break
        aba.drenar(0.5)
    ok(bool(e), "o editor abriu as %d peças pelo lote" % len(obra))
    nervuras_certas(nerv_obra, "%d bases, no lote" % COPIAS)

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
