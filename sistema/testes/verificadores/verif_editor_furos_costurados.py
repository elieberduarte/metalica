# -*- coding: utf-8 -*-
"""Os furos das faces costuradas do IFC abertos no EDITOR 3D, como no modo ver.

GESTÃO, 22/10 (ME Sooro — Depósito Químico, IFC do ST-DEVELOPER v12): o IFC grava a alma furada da terça como
uma face só, com cada furo ligado ao contorno por uma ponte (índices repetidos na face). O modo ver e o celular
foram corrigidos em 37623de (geometria.lacos_da_face + triangular_face_costurada); o editor
(editor3d/nucleo/cena.js, triangularFace → earcut direto sobre a face costurada) ainda tampava os mesmos furos:
na U 200 de T.L a ponte que não volta pelo mesmo caminho, na C 200 de T.C.1 o furo na diagonal que divide a alma.

As faces são as do arquivo do usuário (testes/dados_ifc/faces_costuradas_me_sooro.json), com as peças a 137 m da
origem, como o IFC do Sooro. No editor de verdade (Chrome sem janela):
  A. a malha que o editor monta para cada alma (cena._geometriaSolido, o que o lote desenha) não tem triângulo no
     plano da face por cima de nenhum furo, e a área desenhada é a da alma sem os furos (nada sobra, nada falta);
  B. na tela, olhando a alma de frente, o pixel no centro de cada furo é o fundo, não a cor da peça ao lado;
  C. sem erros no console.
Sem a correção (git stash de cena.js): A e B falham. Porta livre, nunca a 8765/8766."""
import base64, io, json, math, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.geometria import area_assinada
from saida.pacote_celular import _triangulos
from PIL import Image
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

DADOS_IFC = os.path.join(BASE, "testes", "dados_ifc", "faces_costuradas_me_sooro.json")
DESLOC = [137526.0, 72917.0, 6427.0]                 # o IFC do Sooro: a 137 m da origem
ESPESSURA = 2.25
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_furos_costurados_")
VISTA_DA_NORMAL = {2: "topo", 1: "frente", 0: "direita"}


def _cobre(P, tris, p):
    def cr(o, u, w):
        return (u[0] - o[0]) * (w[1] - o[1]) - (u[1] - o[1]) * (w[0] - o[0])
    for a, b, c in tris:
        d = (cr(P[a], P[b], p), cr(P[b], P[c], p), cr(P[c], P[a], p))
        if all(x > 1e-9 for x in d) or all(x < -1e-9 for x in d):
            return True
    return False


with open(DADOS_IFC, encoding="utf-8") as f:
    FACES = [(nome, d) for nome, d in json.load(f).items() if not nome.startswith("_")]

ents, casos = [], []
for n, (nome, d) in enumerate(FACES):
    V, F, (i, j) = d["vertices"], d["face"], d["eixos"]
    eixo = 3 - i - j
    base = [[v[0] + DESLOC[0], v[1] + DESLOC[1], v[2] + DESLOC[2]] for v in V]
    costas = [list(p) for p in base]
    for p in costas:
        p[eixo] -= ESPESSURA
    nv = len(base)
    ents.append({"id": "alma%d" % n, "tipo": "solido", "nome": nome.split(" ")[0], "camada": "Vigas", "material": "",
                 "vertices": base + costas, "faces": [F, [k + nv for k in reversed(F)]],
                 "atributos": {"marcas": {"perfil": nome.split(" ")[0], "posicao": "M%d" % (n + 1)}}})
    # um ponto de material perto de cada furo (pela triangulação certa, a do servidor), para comparar a cor
    P = [(v[i], v[j]) for v in V]
    certos = _triangulos(V, F)
    pares = []
    for h in d["furos"]:
        mat = None
        for r in (20, 30, 40, 55):
            for ang in range(0, 360, 30):
                q = (h[0] + r * math.cos(math.radians(ang)), h[1] + r * math.sin(math.radians(ang)))
                if _cobre(P, certos, q):
                    mat = q; break
            if mat: break
        pares.append((h, mat))
    area_face = sum(abs(area_assinada([P[a], P[b], P[c]])) for a, b, c in certos)
    casos.append({"id": "alma%d" % n, "nome": nome, "i": i, "j": j, "eixo": eixo, "plano": base[F[0]][eixo],
                  "pares": pares, "area": area_face})

os.makedirs(os.path.join(DADOS, "sooro"))
json.dump({"nome": "sooro", "tipo": "ifc", "alterado": "2026-11-06T09:00:00"},
          open(os.path.join(DADOS, "sooro", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "sooro", "unidade": "mm", "entidades": ents,
           "camadas": {"Vigas": {"nome": "Vigas", "cor": "#c0392b", "visivel": True}}, "materiais": {}},
          open(os.path.join(DADOS, "sooro", "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base_url = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_furos_cost_")
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

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and r.get("erro"): print("     erro JS:", str(r["erro"])[:400]); return None
        return r

    aba.navegar(base_url + "/editor?projeto=sooro", limite=120)
    t0 = time.time()
    while time.time() - t0 < 120:
        e = jsj("const ed = window.editor; return !!(ed && ed.documento && ed.documento.tamanho === %d && document.body.dataset.pronto === '1' && !ed.cena.montando);" % len(ents))
        if e: break
        aba.drenar(0.3)
    ok(bool(e), "o editor abriu com as %d almas" % len(ents))
    aba.drenar(1.0)

    for c in casos:
        print(c["nome"])
        # --- A. a malha que o editor monta
        pos = jsj("const ent = editor.documento.get('%s'); const r = editor.cena._geometriaSolido(ent);"
                  " return r.geom ? Array.from(r.geom.getAttribute('position').array) : null;" % c["id"])
        ok(pos is not None, "o editor montou a malha da alma")
        if pos is None: continue
        i, j, eixo = c["i"], c["j"], c["eixo"]
        pts = [(pos[k], pos[k + 1], pos[k + 2]) for k in range(0, len(pos), 3)]
        P = [(p[i] - DESLOC[i], p[j] - DESLOC[j]) for p in pts]
        # a face da frente: a 1ª metade da malha (a de trás é a mesma face, ao contrário, 2,25 mm atrás; a alma do arquivo
        # não é plana a 0,5 mm — a C 200 varia ~9 mm no y)
        tris = [(k, k + 1, k + 2) for k in range(0, len(pts) // 2, 3)]
        tampados = [h for h, _ in c["pares"] if _cobre(P, tris, h)]
        ok(not tampados, f"[malha] nenhum furo tampado ({len(c['pares']) - len(tampados)} de {len(c['pares'])} abertos; tampados {tampados})")
        area = sum(abs(area_assinada([P[a], P[b], P[cc]])) for a, b, cc in tris)
        ok(abs(area - c["area"]) <= 1e-3 * c["area"], f"[malha] a área desenhada é a da alma sem os furos ({area:.0f} × {c['area']:.0f} mm²)")
        # --- B. na tela: o centro do furo é o fundo, não a peça
        vista = VISTA_DA_NORMAL[eixo]
        abertos = 0
        for n, (h, mat) in enumerate(c["pares"]):
            if mat is None: continue
            centro = [0.0, 0.0, 0.0]
            centro[i], centro[j], centro[eixo] = h[0] + DESLOC[i], h[1] + DESLOC[j], c["plano"]
            caixa = {"min": [centro[0] - 60, centro[1] - 60, centro[2] - 60], "max": [centro[0] + 60, centro[1] + 60, centro[2] + 60]}
            jsj("const c = %s; editor.camera.vista('%s', [c.min, c.max]); editor.camera.concluirAnimacao(); return 1;"
                % (json.dumps(caixa), vista))
            aba.drenar(0.8)
            img = Image.open(io.BytesIO(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))).convert("RGB")
            pm = [0.0, 0.0, 0.0]
            pm[i], pm[j], pm[eixo] = mat[0] + DESLOC[i], mat[1] + DESLOC[j], c["plano"]
            r = jsj("const cv = editor.camera, el = editor.cena.renderer.domElement.getBoundingClientRect();"
                    " const a = cv.paraTela(%s), b = cv.paraTela(%s); return [a[0] + el.left, a[1] + el.top, b[0] + el.left, b[1] + el.top];"
                    % (json.dumps(centro), json.dumps(pm)))
            if not r: continue
            cf = img.getpixel((int(round(r[0])), int(round(r[1]))))
            cm = img.getpixel((int(round(r[2])), int(round(r[3]))))
            dif = max(abs(a - b) for a, b in zip(cf, cm))
            if dif > 40: abertos += 1
            else: print(f"     furo {n} em {h}: centro {cf} × peça {cm}")
            if n == 0: img.save(os.path.join(os.path.dirname(__file__), "editor_furos_costurados_%s.png" % c["id"]))
        n_ok = sum(1 for _, m in c["pares"] if m is not None)
        ok(abertos == n_ok, f"[tela] o fundo aparece pelo furo ({abertos} de {n_ok})")

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
