# -*- coding: utf-8 -*-
"""A faixa de ferramentas da área de trabalho (/dividida, web/faixa_ferramentas.js; UI1, 30/09/2026): uma linha
só no lugar das colunas do 2D e do 3D, que somem dentro da área (e continuam no /cad e no editor sozinhos).
Confere: nenhuma ferramenta das colunas fica fora da faixa; o lado ativo muda com o mouse; o que não é do lado
ativo fica apagado e o clique passa o lado; a ferramenta ligada por atalho aparece marcada; a vista de um lado
só esconde as do outro; a peça selecionada abre o grupo verde; em 1366 e 1100 px a faixa cabe (recolhe)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Barra, Documento

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_faixaui_")
PASTA = os.path.join(DADOS, "faixa")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Faixa", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-30T00:00:00", "alterado": "2026-09-30T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
ents = [{"id": "l1", "tipo": "linha", "camada": "0", "a": [0.0, 0.0], "b": [8000.0, 0.0]},
        {"id": "l2", "tipo": "linha", "camada": "0", "a": [0.0, 0.0], "b": [0.0, 4000.0]}]
json.dump({"nome": "desenho", "unidade": "mm", "escala": 20, "camadas": {}, "entidades": ents, "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "desenho.desenho.json"), "w", encoding="utf-8"))
doc = Documento()
b = Barra(nome="W 200×26,6", inicio=(0.0, 0.0, 0.0), fim=(0.0, 0.0, 4000.0), perfil="W 200×26,6", papel="pilar")
doc.add(b)
ID_BARRA = b.id
json.dump(doc.dict(), open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_faixaui_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
F2 = "document.querySelector('#f2d').contentWindow"
F3 = "document.querySelector('#f3d').contentWindow"
FX = "document.querySelector('#faixa-ferramentas')"


def mouse_em(aba, sel, dx=0.5, dy=0.5):
    r = aba.avaliar(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.left + r.width*{dx}, r.top + r.height*{dy}]; }})()")
    aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=r[0], y=r[1])
    aba.drenar(0.4)


def estado(aba, chave):
    return aba.avaliar(f"(() => {{ const b = {FX}.querySelector('.fx-bt[data-chave=\"{chave}\"]'); return b ? b.className : null; }})()")


try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/"); aba.console.clear()
    aba.navegar(base + "/dividida?projeto=faixa&vista=ambos&editar=1", limite=60)      # o editor, não o modo ver
    t0 = time.time()
    while time.time() - t0 < 90 and not aba.avaliar(f"!!({F2}.cad && {F3}.editor && {F3}.editor.ferramentas.size > 5 && {FX}.querySelectorAll('.fx-bt').length > 15)"):
        aba.drenar(0.5)
    aba.drenar(1.0)
    n = aba.avaliar(f"{FX}.querySelectorAll('.fx-bt').length") or 0
    col = aba.avaliar(f"[getComputedStyle({F2}.document.getElementById('barra-ferramentas')).display, getComputedStyle({F3}.document.getElementById('barra-ferramentas')).display]")
    # a barra da disciplina do 2D (no dev, a do pré-moldado): aqui, uma de mentira com uma ferramenta e uma ação —
    # a faixa acompanha a barra pelo MutationObserver e mostra as duas
    aba.avaliar(f"""(() => {{ const d = {F2}.document; let n = d.getElementById('barra-disciplina');
        if (!n) {{ n = d.createElement('nav'); n.id = 'barra-disciplina'; n.className = 'ferramentas barra-disciplina'; d.querySelector('.area').appendChild(n); }}
        n.innerHTML = '<button type="button" class="ferramenta" data-ferramenta="linha" data-material="aco" title="Elemento de teste">E</button>' +
                      '<button type="button" class="ferramenta acao" title="Ação de teste">A</button>';
        window.__acao = 0; n.querySelector('.acao').addEventListener('click', () => {{ window.parent.__acao = (window.parent.__acao || 0) + 1; }});
        return 1; }})()""")
    aba.drenar(1.0)
    acao = aba.avaliar(f"(() => {{ const b = [...{FX}.querySelectorAll('.fx-bt')].find(x => x.getAttribute('aria-label') === 'Ação de teste'); if (b) b.click(); return window.__acao || 0; }})()")
    ok(acao == 1 and aba.avaliar(f"{FX}.querySelectorAll('[data-grupo=\"Planta\"] .fx-bt').length") == 1,
       f"a barra da disciplina entra na faixa: a ação da planta aparece e aciona o botão original ({acao})")
    ok(n > 15 and col == ["none", "none"], f"a faixa no lugar das colunas ({n} botões; colunas do 2D e do 3D: {col})")
    # nenhuma ferramenta das colunas fora da faixa (na faixa ou no ▾ de algum grupo)
    faltam = aba.avaliar(f"""(() => {{
        const na = new Set();
        for (const b of {FX}.querySelectorAll('.fx-bt')) {{ if (b.dataset.id2) na.add('2d:' + b.dataset.id2); if (b.dataset.id3) na.add('3d:' + b.dataset.id3); }}
        for (const m of {FX}.querySelectorAll('.fx-mais')) {{ m.click();
            for (const li of document.querySelectorAll('.faixa-lista .fx-li')) {{ if (li.dataset.id2) na.add('2d:' + li.dataset.id2); if (li.dataset.id3) na.add('3d:' + li.dataset.id3); }} }}
        document.body.click();
        const out = [];
        for (const b of {F2}.document.querySelectorAll('#barra-ferramentas .ferramenta')) {{
            const id = b.dataset.ferramenta; if (!na.has('2d:' + id)) out.push('2d:' + id); }}
        for (const b of {F3}.document.querySelectorAll('#barra-ferramentas .ferramenta')) {{
            const id = b.dataset.id; if (!na.has('3d:' + id)) out.push('3d:' + id); }}
        return out; }})()""")
    ok(faltam == [], f"nenhuma ferramenta das colunas ficou fora da faixa ({faltam})")
    # o lado ativo pelo mouse; o que não é dele fica apagado
    mouse_em(aba, "#f2d")
    l2 = aba.avaliar(f"{FX}.dataset.lado"); p2 = estado(aba, "poligono"); h2 = estado(aba, "hachura")
    mouse_em(aba, "#f3d")
    l3 = aba.avaliar(f"{FX}.dataset.lado"); p3 = estado(aba, "poligono"); h3 = estado(aba, "hachura")
    ok(l2 == "2d" and l3 == "3d" and "fora" in (p2 or "") and "fora" not in (p3 or "x") and "fora" in (h3 or "") and "fora" not in (h2 or "x"),
       f"o lado ativo segue o mouse ({l2} → {l3}); polígono (3D) e hachura (2D) apagados no outro lado ({p2} | {p3} | {h2} | {h3})")
    contorno = aba.avaliar("document.getElementById('lado-3d').classList.contains('faixa-ativo')")
    ok(contorno, "o lado ativo ganha o contorno")
    # clique numa ferramenta comum: age no lado ativo e fica marcada
    mouse_em(aba, "#f2d")
    aba.avaliar(f"{FX}.querySelector('.fx-bt[data-chave=\"linha\"]').click(); 1"); aba.drenar(0.6)
    f2 = aba.avaliar(f"{F2}.cad.ferramenta.constructor.id")
    ok(f2 == "linha" and "on" in (estado(aba, "linha") or ""), f"Linha pela faixa com o 2D ativo liga a linha do 2D ({f2}, {estado(aba, 'linha')})")
    # a apagada (só do 3D) passa o lado e começa lá
    aba.avaliar(f"{FX}.querySelector('.fx-bt[data-chave=\"poligono\"]').click(); 1"); aba.drenar(0.8)
    ok(aba.avaliar(f"{F3}.editor.idAtiva") == "poligono" and aba.avaliar(f"{FX}.dataset.lado") == "3d",
       f"Polígono (só do 3D) com o 2D ativo: o 3D fica ativo e a ferramenta começa lá ({aba.avaliar(F3 + '.editor.idAtiva')})")
    # ferramenta ligada por fora da faixa (atalho): a faixa acompanha
    aba.avaliar(f"{F3}.editor.ativarFerramenta('mover'); 1"); aba.drenar(0.6)
    ok("on" in (estado(aba, "mover") or ""), f"a ferramenta ligada no 3D por atalho aparece marcada na faixa ({estado(aba, 'mover')})")
    aba.avaliar(f"{F3}.editor.ativarFerramenta('selecionar'); 1"); aba.drenar(0.3)
    # a peça selecionada: o grupo verde
    aba.avaliar(f"{F3}.editor.selecao.definir(['{ID_BARRA}']); 1"); aba.drenar(1.2)
    ctx = aba.avaliar(f"(() => {{ const c = {FX}.querySelector('.fx-ctx'); return c ? c.textContent : ''; }})()") or ""
    ok("W 200" in ctx and "Apagar" in ctx, f"com uma peça selecionada no 3D, o grupo verde com o nome dela ({ctx})")
    aba.avaliar(f"{F3}.editor.selecao.limpar(); 1"); aba.drenar(1.0)
    ok(not aba.avaliar(f"!!{FX}.querySelector('.fx-ctx')"), "sem seleção, o grupo verde sai")
    # vista de um lado só: as ferramentas do outro somem
    aba.avaliar("window.mostrarVista('3d'); 1"); aba.drenar(1.0)
    ok(estado(aba, "hachura") is None and estado(aba, "poligono") is not None and "fora" not in (estado(aba, "poligono") or ""),
       "só o 3D: as ferramentas só do 2D somem da faixa")
    aba.avaliar("window.mostrarVista('ambos'); 1"); aba.drenar(1.0)
    # larguras menores: cabe, recolhendo grupos
    for larg in (1366, 1100):
        aba.cmd("Emulation.setDeviceMetricsOverride", width=larg, height=800, deviceScaleFactor=1, mobile=False); aba.drenar(1.0)
        r = aba.avaliar(f"[{FX}.scrollWidth, {FX}.clientWidth, {FX}.querySelectorAll('.fx-grupo.recolhido').length, document.documentElement.scrollWidth <= window.innerWidth]")
        ok(r and r[0] <= r[1] + 1 and r[3], f"em {larg} px a faixa cabe sem rolagem ({r[0]} de {r[1]} px, {r[2]} grupo(s) recolhido(s))")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    # fora da área, as telas continuam com as colunas
    aba.navegar(base + "/cad?projeto=faixa&desenho=desenho", limite=60)
    t0 = time.time()
    while time.time() - t0 < 30 and not aba.avaliar("!!window.cad"): aba.drenar(0.3)
    ok(aba.avaliar("getComputedStyle(document.getElementById('barra-ferramentas')).display") != "none",
       "o /cad sozinho continua com a coluna de ferramentas")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, f"sem erros no console: {erros[:3]}")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
print()
print("FALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
