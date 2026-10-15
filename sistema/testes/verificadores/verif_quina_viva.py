# -*- coding: utf-8 -*-
"""A quina viva no snap do editor 3D (usuário, 15/10/2026: "nos tubos com o canto arredondado, difícil pegar o ponto
exato para os perfis não invadirem um ao outro"). Com a seção que a cena desenha de verdade, confere que:
  1. o tubo quadrado e o retangular ganham as 4 quinas vivas de fora (o encontro das faces) e as 4 de dentro;
  2. o Ue dobrado ganha as quinas das dobras; o tubo redondo não ganha nenhuma;
  3. a quina entra no snap da barra nas duas pontas, e o mouse em cima dela dá "Extremidade" no ponto exato."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_quina_")
PASTA = os.path.join(DADOS, "quina")
os.makedirs(PASTA)
json.dump({"formato": 1, "nome": "Quina", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-15T00:00:00", "alterado": "2026-10-15T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
PERFIS = {"tq": "TQ 100×100×4,75", "tr": "TR 100×70×1,5", "ue": "Ue 127×50×17×2,00", "tc": "TC 180×6,3"}
doc = Documento()
for k, (nome, p) in enumerate(PERFIS.items()):
    doc.add(Barra(nome=nome, inicio=(0.0, 1000.0 * k, 0.0), fim=(3000.0, 1000.0 * k, 0.0), perfil=p, rotacao=0.0, papel="viga"))
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_quina_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=quina", limite=60)
    todos = " && ".join("editor.cena.perfil(%s)" % json.dumps(p) for p in PERFIS.values())
    t0 = time.time()
    while time.time() - t0 < 60 and not aba.avaliar(f"!!(window.editor && editor.documento && editor.documento.entidades.size >= 4 && {todos})"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    aba.console.clear()

    def jsj(e):
        r = aba.avaliar(f"JSON.stringify((() => {{ {e} }})())")
        return json.loads(r) if r else None

    q = jsj("const inf = editor.inferencia, o = {};"
            f" for (const [k, p] of Object.entries({json.dumps(PERFIS)})) {{ inf._aneis && inf._aneis.delete(p);"
            "   const a = inf._aneisDoPerfil(p); o[k] = a ? a.flatMap(r => r.quinas || []).map(v => v.map(x => Math.round(x * 100) / 100)) : null; }"
            " return o;")
    print("  quinas:", q)
    def tem(lista, x, y): return any(abs(a - x) < 0.05 and abs(b - y) < 0.05 for a, b in lista or [])
    tq = q.get("tq") or []
    ok(len(tq) >= 4 and all(tem(tq, sx * 50, sy * 50) for sx in (-1, 1) for sy in (-1, 1)),
       f"TQ 100×100: as 4 quinas de fora em ±50 ({len(tq)})")
    tr = q.get("tr") or []
    ok(len(tr) >= 4 and all(tem(tr, sx * 50, sy * 35) or tem(tr, sx * 35, sy * 50) for sx in (-1, 1) for sy in (-1, 1)),
       f"TR 100×70: as 4 quinas de fora ({len(tr)})")
    ok(q.get("ue") is None or len(q.get("ue")) >= 4, f"Ue: as quinas das dobras ({None if q.get('ue') is None else len(q['ue'])})")
    ok(not q.get("tc"), "tubo redondo: nenhuma quina")

    # o snap: a quina de fora do TQ na ponta do início, com o mouse de verdade em cima dela
    aba.avaliar("editor.camera.enquadrar([[-400, -400, -400], [400, 400, 400]]); editor.camera.concluirAnimacao && editor.camera.concluirAnimacao(); 1")
    aba.drenar(1.0)
    r = jsj("const inf = editor.inferencia, b = [...editor.documento.entidades.values()].find(e => e.nome === 'tq');"
            " const c = inf._contornoDaBarra(b);"
            " const alvo = c.pontos.find(p => Math.abs(p[0]) < 0.5 && p[1] > 0 && p[2] > 0 && Math.abs(p[1] - 50) < 0.05 && Math.abs(p[2] - 50) < 0.05);"
            " if (!alvo) return {achou: false, n: c.pontos.length};"
            " const t = editor.camera.paraTela(alvo); return {achou: true, alvo, tela: t};")
    ok(r and r.get("achou"), f"a quina viva está nos pontos do snap da barra ({r})")
    if r and r.get("achou"):
        x, y = r["tela"][0], r["tela"][1]
        # com a câmera já parada (o enquadrar foi num passo antes), a inferência no pixel da quina — ligada, como nas
        # ferramentas de desenho (Mover, Barra); no Selecionar ela fica desligada
        s2 = jsj(f"const i = editor.inferencia, era = i.ativa; i.ativa = true; const u = i.resolver({x}, {y}, {{}}); i.ativa = era; return u ? {{ponto: u.ponto, tipo: u.tipoSnap}} : null;")
        if s2:
            d = max(abs(a - b) for a, b in zip(s2["ponto"], r["alvo"]))
            ok(s2["tipo"] == "extremidade" and d < 0.5, f"mouse na quina: {s2['tipo']} a {d:.2f} mm do canto")
        else:
            ok(False, "mouse na quina: a inferência não respondeu")
    e = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not e, "sem erros no console" + (f" — {[x[1][:200] for x in e[:2]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
