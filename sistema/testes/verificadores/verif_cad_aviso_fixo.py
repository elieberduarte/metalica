# -*- coding: utf-8 -*-
"""Aviso fixo que sumia (GESTÃO N.9, 14/11; conferência da 0.9.3, o verif_identificacao_ui caiu duas vezes na 4ª rodada):
o "Planta atualizada pelo 3D: …" é fixo (duração 0), mas o limite da pilha de avisos (no máximo 4, P11) tirava sempre o
mais velho — e os avisos da sincronia do 3D (10 s cada) que chegavam logo depois empurravam o fixo para fora em
milissegundos; o usuário não lia o que mudou. Agora o limite tira primeiro o aviso com prazo para sair; o fixo só sai
pelo limite quando o novo também é fixo.

  A. Estrutura › Atualizar a planta pelo 3D (clique de verdade no menu; a resposta do 3D é a da obra, com 1 + 32 mudanças
     e uma peça sem 3D), e logo depois os 3 avisos da sincronia do 3D (o _sincronizar3D de verdade, com a resposta do
     servidor trocada): "Planta atualizada pelo 3D" e "Sem peça no 3D" continuam na tela;
  B. 4 fixos e chega um aviso de 1,5 s: os 4 fixos ficam (a pilha tem 5 enquanto ele está) e ele sai sozinho;
  C. 4 fixos e chega outro fixo: o mais velho sai (o limite de 4 do P11 continua valendo entre fixos).

Rodar: PYTHONIOENCODING=utf-8 python testes/verificadores/verif_cad_aviso_fixo.py"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_aviso_fixo_")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


def post(rota, corpo):
    req = urllib.request.Request(base + urllib.parse.quote(rota), data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


ALTERACOES = ["a terça T1 movida 300 mm"] + [f"a terça T{i} com outro perfil" for i in range(2, 34)]
SINCRONIA = ["CL1: 2 furos fora da seção", "contraventos com 4 pontas no meio do banzo", "marcas repetidas: V1 (2×)"]
chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_aviso_fixo_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/", timeout=2); break
        except Exception:
            time.sleep(0.5)
    r = post("/api/projetos", {"nome": "Aviso fixo", "tipo": "desenho"})
    slug = r.get("slug") or (r.get("projeto") or {}).get("slug")
    post(f"/api/projetos/{slug}/desenhos/planta", {"desenho": {"nome": "Planta", "escala": 50, "entidades": [
        {"id": "l1", "tipo": "linha", "camada": "VISTA", "atributos": {}, "a": [0, 0], "b": [6000, 0]}]}})
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + f"/cad?projeto={slug}&desenho=planta", limite=60)

    def js(e):
        r = aba.avaliar(f"(() => {{ try {{ const c = window.cad; return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:300])
        return r

    def esperar(cond, limite=30.0):
        t0 = time.time()
        while time.time() - t0 < limite:
            if js(f"return !!({cond});"): return True
            aba.drenar(0.2)
        return False

    def clicar(seletor_js):
        r = js(f"const e = {seletor_js}; if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2];")
        if not r: return False
        x, y = r
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1, buttons=1)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1, buttons=0)
        aba.drenar(0.3)
        return True

    def avisos():
        return js("return [...document.querySelectorAll('#avisos .aviso')].map(a => a.dataset.texto || a.textContent);") or []

    def tem(trecho):
        return any(trecho in a for a in avisos())

    def limpar():
        js("document.querySelectorAll('#avisos .aviso').forEach(a => a.remove()); return 1;")

    ok(esperar("document.body.dataset.pronto === '1' && c && c.nomeDesenho === 'planta'", 60), "o CAD abriu a planta")

    # a resposta do servidor trocada só nas duas rotas do 3D (o resto — gravar a planta — vai ao servidor de verdade)
    js(f"""const orig = window.fetch.bind(window); window.__sinc = false;
      const resp = (o) => new Response(JSON.stringify(o), {{ status: 200, headers: {{ 'Content-Type': 'application/json' }} }});
      window.fetch = async (url, op) => {{
        const u = String(url && url.url || url);
        if (u.includes('/estrutura/do3d')) return resp({{ ok: true, alteracoes: {json.dumps(ALTERACOES)}, novos: [], sem_peca: ['P9'], desenho: null }});
        if (u.includes('/estrutura/3d')) {{
          if (!window.__sinc) return resp({{ ok: true, mudou: false }});
          await new Promise(r => setTimeout(r, 150));
          return resp({{ ok: true, mudou: true, entrou: 1, saiu: 0, avisos: {json.dumps(SINCRONIA)} }});
        }}
        return orig(url, op);
      }};
      return 1;""")
    limpar()

    # ------------------------------------------------------------------ A. a volta do 3D e, logo depois, a sincronia
    ok(clicar("document.querySelector('[data-menu=\"estrutura\"] .menu-botao')"), "A. abriu o menu Estrutura")
    ok(esperar("(() => { const b = document.querySelector('[data-acao=\"estr-do-3d\"]'); return b && b.getBoundingClientRect().height > 0; })()", 5)
       and clicar("document.querySelector('[data-acao=\"estr-do-3d\"]')"), "A. clicou em Atualizar a planta pelo 3D")
    ok(esperar("[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('Planta atualizada pelo 3D'))", 15),
       "A. o aviso \"Planta atualizada pelo 3D\" apareceu")
    js("window.__sinc = true; window.__sincronizou = false; c._sincronizar3D(true).then(() => window.__sincronizou = true); return 1;")
    ok(esperar("window.__sincronizou", 15), "A. a sincronia do 3D respondeu")
    ok(esperar("[...document.querySelectorAll('#avisos .aviso')].some(a => a.textContent.includes('marcas repetidas'))", 5),
       "A. os avisos da sincronia chegaram depois do fixo")
    aba.drenar(1.5)
    lista = avisos()
    ok(tem("Planta atualizada pelo 3D") and tem("movida 300 mm"),
       f"A. \"Planta atualizada pelo 3D … movida 300 mm\" continua na tela ({len(lista)} avisos: {[a[:40] for a in lista]})")
    ok(tem("Sem peça no 3D"), "A. \"Sem peça no 3D\" continua na tela")
    ok(len(lista) <= 4, f"A. a pilha continua com no máximo 4 ({len(lista)})")

    # ------------------------------------------------------------------ B. 4 fixos e um de 1,5 s
    limpar()
    js("for (let i = 1; i <= 4; i++) c.aviso(`fixo ${i}`, 'atencao', 0); c.aviso('passageiro', 'info', 1500); return 1;")
    lista = avisos()
    ok(all(f"fixo {i}" in lista for i in range(1, 5)) and "passageiro" in lista, f"B. os 4 fixos e o de 1,5 s, juntos ({lista})")
    ok(esperar("![...document.querySelectorAll('#avisos .aviso')].some(a => a.dataset.texto === 'passageiro')", 5),
       "B. o de 1,5 s saiu sozinho")
    ok(sorted(avisos()) == [f"fixo {i}" for i in range(1, 5)], f"B. ficaram os 4 fixos ({avisos()})")

    # ------------------------------------------------------------------ C. 4 fixos e mais um fixo
    js("c.aviso('fixo 5', 'atencao', 0); return 1;")
    ok(avisos() == ["fixo 2", "fixo 3", "fixo 4", "fixo 5"], f"C. entre fixos, o mais velho sai (limite 4): {avisos()}")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(0.5)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
