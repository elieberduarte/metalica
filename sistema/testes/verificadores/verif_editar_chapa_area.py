# -*- coding: utf-8 -*-
"""Editar chapa na área 2D + 3D (a tela dividida) sem recarregar os quadros (pedido do usuário, 15/10/2026: a volta
recarregava o 3D inteiro da PRATI):
  1. do 3D, abrir a edição da chapa: o 2D abre o desenho da edição;
  2. mexer num furo e Concluir: volta ao 3D SEM recarregar e as chapas da posição no 3D já têm o furo novo;
  3. abrir de novo: o CAD já aberto só troca de desenho (o quadro do 2D não recarrega);
  4. Cancelar: volta ao 3D sem recarregar;
  5. o 3D continua gravando sem conflito (a versão do modelo acompanhou);
  6. sem erros no console."""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_eca_")
os.makedirs(os.path.join(DADOS, "compressores", "desenhos-2d"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": [], "vistas": [], "metadados": {}},
          open(os.path.join(DADOS, "compressores", "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_eca_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
F3 = "document.getElementById('f3d').contentWindow"
F2 = "document.getElementById('f2d').contentWindow"
try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)

    def esperar(cond, limite=90.0):
        t = time.time()
        while time.time() - t < limite:
            try:
                if aba.avaliar(cond): return True
            except Exception:
                pass
            aba.drenar(0.4)
        return False

    aba.navegar(f"http://localhost:{PORTA}/dividida?projeto=compressores&vista=3d", limite=120)
    # o 3D da área abre leve (o modo ver): o editor sobe pelo Editar
    esperar(f"(() => {{ try {{ return !!{F3}.document.body; }} catch (e) {{ return false; }} }})()", 60)
    # a área montou os quadros (o 3D com o endereço inicial, carregado): só então o pedido do editor, como os menus fazem
    esperar("!!document.getElementById('f3d').dataset.src", 60)
    esperar(f"(() => {{ try {{ return {F3}.document.readyState === 'complete' && {F3}.location.pathname !== 'blank'; }} catch (e) {{ return false; }} }})()", 60)
    aba.drenar(2.0)
    for _tentativa in range(3):
        aba.avaliar("navegar('/editor?projeto=compressores'); 1")
        if esperar(f"(() => {{ try {{ return {F3}.location.pathname === '/editor'; }} catch (e) {{ return false; }} }})()", 20):
            break
    ok(esperar(f"(() => {{ try {{ const w = {F3}; return !!(w.editor && w.editor.documento && w.editor.documento.entidades.size > 100); }} catch (e) {{ return false; }} }})()", 240),
       "o editor 3D abriu na área")
    aba.drenar(2.0)
    aba.avaliar(f"{F3}.__sem_recarregar = 1; 1")
    P77 = f"""(() => {{ const w = {F3}; return [...w.editor.documento.entidades.values()].filter(e => ((e.atributos || {{}}).marcas || {{}}).posicao === 'P77'); }})()"""

    def furos_3d():
        return json.loads(aba.avaliar(f"""JSON.stringify({P77}.map(e => [e.tipo, (e.furos || []).map(f => [Math.round(f.x), Math.round(f.y)])]).sort())"""))

    def furos_servidor():
        salvo = json.load(open(os.path.join(DADOS, "compressores", "modelo.json"), encoding="utf-8"))
        return sorted([e.get("tipo"), [[round(f["x"]), round(f["y"])] for f in (e.get("furos") or [])]]
                      for e in salvo["entidades"] if ((e.get("atributos") or {}).get("marcas") or {}).get("posicao") == "P77")

    # o que a sincronização devolveu em cada volta
    aba.avaliar(f"""(() => {{ const w = {F3}; w.__sinc = []; const s0 = w.editor.sincronizarComServidor.bind(w.editor);
        w.editor.sincronizarComServidor = async () => {{ const p = !!w.editor._autosavePendente; const r = await s0(); w.__sinc.push([r, p, w.editor._modeloAlterado]); return r; }}; return 1; }})()""")
    # 1) abrir a edição pelo 3D (como os dois cliques)
    aba.avaliar(f"(() => {{ const w = {F3}; w.editor.abrirChapaNo2D({P77}[0], 'isolada'); return 1; }})()")
    ok(esperar(f"(() => {{ try {{ const w = {F2}; return !!(w.cad && w.document.querySelector('.faixa-edicao')); }} catch (e) {{ return false; }} }})()", 120),
       "o 2D abriu o desenho da edição")
    aba.drenar(1.5)
    aba.avaliar(f"{F2}.__sem_recarregar = 1; 1")
    antes = furos_servidor()
    # 2) mexer no furo 0 e Concluir
    aba.avaliar(f"""(() => {{ const w = {F2}; for (const e of w.cad.doc.entidades.values()) {{ const a = e.atributos || {{}};
        if (e.camada === 'FURO' && a.furo === 0) {{ if (e.tipo === 'circulo') e.centro = [e.centro[0] + 10, e.centro[1]];
          else e.vertices = e.vertices.map(p => [p[0] + 10, p[1]]); }} }} return 1; }})()""")
    t0 = time.time()
    aba.avaliar(f"(() => {{ {F2}.cad.concluirEdicaoChapa(); return 1; }})()")
    ok(esperar(f"(() => {{ try {{ return {F3}.__sinc.length >= 1; }} catch (e) {{ return false; }} }})()", 120), "Concluir pediu ao 3D a sincronização")
    dt = time.time() - t0
    print("        sincronização:", aba.avaliar(f"JSON.stringify({F3}.__sinc)"))
    depois_srv = furos_servidor()
    ok(depois_srv != antes, "o Concluir mudou os furos da P77 no servidor")
    ok(furos_3d() == depois_srv, f"o 3D ficou igual ao servidor: as 18 chapas P77 com o furo novo ({dt:.1f} s)")
    ok(aba.avaliar(f"{F3}.__sem_recarregar === 1"), "Concluir voltou ao 3D sem recarregá-lo")
    ok(aba.avaliar("document.body.classList.contains('v-3d')"), "a área mostra o 3D")
    # 3) abrir de novo: o CAD já aberto só troca de desenho
    aba.drenar(1.0)
    aba.avaliar(f"(() => {{ const w = {F3}; w.editor.abrirChapaNo2D({P77}[0], 'isolada'); return 1; }})()")
    ok(esperar(f"(() => {{ try {{ const w = {F2}; return !!w.document.querySelector('.faixa-edicao') && w.__sem_recarregar === 1; }} catch (e) {{ return false; }} }})()", 90),
       "abrir de novo: o 2D trocou de desenho sem recarregar")
    aba.drenar(1.0)
    # 4) Cancelar
    aba.avaliar(f"(() => {{ const w = {F2}; w.cad._editado = false; w.cad.cancelarEdicaoChapa(); return 1; }})()")
    ok(esperar(f"(() => {{ try {{ return {F3}.__sinc.length >= 2; }} catch (e) {{ return false; }} }})()", 90) and esperar(f"{F3}.__sem_recarregar === 1", 5),
       "Cancelar voltou ao 3D sem recarregá-lo")
    print("        sincronização:", aba.avaliar(f"JSON.stringify({F3}.__sinc)"))
    aba.drenar(1.0)
    # 5) o 3D continua gravando (sem o conflito "o modelo mudou")
    gravou = aba.avaliar(f"""(async () => {{ const w = {F3}; const e = {P77}[0];
        w.editor.alterarEntidades([e.id], {{ nome: 'P77 conferida' }}, 'renomear');
        try {{ await w.editor.gravarConfirmado(); return 'ok'; }} catch (err) {{ return String(err && err.message || err); }} }})()""")
    salvo = json.load(open(os.path.join(DADOS, "compressores", "modelo.json"), encoding="utf-8"))
    ok(gravou == "ok" and any(e.get("nome") == "P77 conferida" for e in salvo["entidades"]), f"o 3D grava depois da volta, sem conflito ({gravou})")
    # o 3D leve (o modo ver) que a área abre primeiro é trocado pelo editor no meio do carregamento: o download dele
    # interrompido não é erro desta edição
    erros = [m for m in aba.console if m[0] in ("error", "excecao") and "3d-leve" not in m[1]
             and not ("Failed to fetch" in m[1] and "visor3d" in m[1])]
    ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:3]]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
