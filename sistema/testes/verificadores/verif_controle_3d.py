# -*- coding: utf-8 -*-
"""O modelo 3D ao lado do Controle de produção (12/11/2026), com eventos de verdade.

Pedido do usuário: o 3D ao lado da lista; clicar no item destaca a peça; as peças mudam de cor conforme a fábrica aponta
(não feita cinza, produzida azul, pintada verde) e uma ferramenta para escolher os tons.

Servidor de teste com --dev e uma CÓPIA do Posto (modelo.json + lista + nomes) numa pasta temporária — nunca o Posto de
verdade:
  1. a tela abre com o 3D ao lado; tudo o que está no controle começa cinza (não feita);
  2. as 7 TESOURA 1 (uma marca, 7 unidades) se separam no 3D: cada unidade com as suas peças, nenhuma repetida;
  3. clicar na linha TESOURA 14-1 destaca as peças dela no 3D (na cor de destaque) e enquadra;
  4. clicar numa peça do 3D (mouse de verdade) marca a linha do item na lista;
  5. Apontar TESOURA 1-3 na Produção → as peças dela azuis; na Pintura → verdes; as outras TESOURA 1 seguem cinza;
  6. peças avulsas iguais pintam na proporção (T.C.1: metade apontada → metade azul);
  7. "Só o que falta produzir" esconde as produzidas;
  8. Cores…: trocar a produzida para #ff0000 muda o 3D na hora; Gravar guarda em _producao-cores.json e vale ao
     recarregar; a sugestão Padrão + Gravar apaga o arquivo;
  9. o botão 3D esconde e mostra o painel; sem erro no console.
Porta livre, nunca a 8765/8766. Sem o Posto nesta máquina, o verificador avisa e sai sem falha."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_producao_controle import POSTO

AQUI = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

if not os.path.exists(os.path.join(POSTO, "modelo.json")):
    print("sem o Posto nesta máquina (%s): nada a verificar" % POSTO)
    sys.exit(0)

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_controle3d_")
OBRA = os.path.join(DADOS, "posto-3d")
os.makedirs(os.path.join(OBRA, "detalhamento"))
for rel in ("modelo.json", "projeto.json", os.path.join("detalhamento", "lista-de-materiais.json"),
            os.path.join("detalhamento", "nomes.json")):
    shutil.copy2(os.path.join(POSTO, rel), os.path.join(OBRA, rel))

# o lugar das unidades pela ordem dos eixos (13/11, detalhe/unidades.py): o nomes.json da cópia ganha as "unidades" como o
# Detalhar grava (o Posto real só as terá no próximo Detalhar da obra) — o 3D acende as peças gravadas de cada unidade
_nomes = json.load(open(os.path.join(OBRA, "detalhamento", "nomes.json"), encoding="utf-8"))
if not _nomes.get("unidades"):
    from nucleo3d.modelo import Documento
    from nucleo2d import detalhar as _det
    from nucleo2d.detalhe import unidades as _U
    print("  (o lugar das unidades da cópia: levantando as peças do Posto, ~1 min)", flush=True)
    _lista = json.load(open(os.path.join(OBRA, "detalhamento", "lista-de-materiais.json"), encoding="utf-8"))
    _doc = Documento.de_dict(json.load(open(os.path.join(OBRA, "modelo.json"), encoding="utf-8")))
    _nomes["unidades"] = _U.numerar([(c["marca"], c["nome"], c["instancias"]) for c in _lista["conjuntos"]],
                                    _det.levantar(_doc, regra_tercas=False)["pecas"],
                                    json.load(open(os.path.join(OBRA, "projeto.json"), encoding="utf-8")).get("eixos"))[1]
    json.dump(_nomes, open(os.path.join(OBRA, "detalhamento", "nomes.json"), "w", encoding="utf-8"), ensure_ascii=False)
LUGAR = _nomes["unidades"]

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c: falhas.append(m)


def esperar(aba, expr, limite=30):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.25)
    return False


def clicar_em(aba, x, y):
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)


def clicar(aba, seletor):
    r = aba.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor)}); if (!e) return null; e.scrollIntoView({{block: 'center'}});"
                    f" const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }})()")
    if not r: return False
    clicar_em(aba, r[0], r[1])
    return True


def digitar(aba, seletor, texto):
    clicar(aba, seletor)
    aba.avaliar(f"document.querySelector({json.dumps(seletor)}).select()")
    aba.cmd("Input.insertText", text=texto)


def apontar(aba, item, etapa, qtd=None):
    clicar(aba, f"#controle-corpo button[data-item={json.dumps(item)}]")
    if not esperar(aba, "!!document.querySelector('#ctl-dialogo[open]')", 10): return False
    clicar(aba, f"#ctl-dialogo input[name=ctl-etapa][value={etapa}]")
    if qtd is not None:
        digitar(aba, "#ctl-qtd", str(qtd))
    clicar(aba, "#ctl-confirmar")
    return esperar(aba, "!document.querySelector('#ctl-dialogo[open]')", 15)


S = "window.controle3d"
V = "window.controle3d.visor"
K = lambda item: f"{S}.dados.itens.findIndex(x => x.id === {json.dumps(item)})"


def cores_de(item):
    """as cores (#rrggbb) das peças do item no 3D, sem repetição"""
    return aba.avaliar(f"(() => {{ const k = {K(item)}; const ps = {S}.mapa.pecas[k] || []; const cb = {V}.corBase;"
                       f" const h = (i) => '#' + [0, 1, 2].map(j => cb[i * 3 + j].toString(16).padStart(2, '0')).join('');"
                       f" return [...new Set(ps.map(h))].sort(); }})()") or []


def foto(nome):
    open(os.path.join(AQUI, nome), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_controle3d_")
nav = subprocess.Popen([exe, "--headless=new", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars", "--no-first-run",
                        "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try: _json(base + "/api/versao"); break
        except Exception: time.sleep(0.5)
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1700, height=1000, deviceScaleFactor=1, mobile=False)

    # 1. abre com o 3D ao lado, tudo cinza
    aba.navegar(base + "/controle-producao?projeto=posto-3d", limite=60)
    ok(esperar(aba, "!!document.querySelector('#ctl-cartoes') && !!document.querySelector('#p3-quadro')", 60),
       "a tela abre com a lista e o quadro do 3D ao lado")
    ok(esperar(aba, f"!!({S} && {S}.visor && {S}.mapa && {S}.estado)", 240), "o 3D abre e as peças ganham a cor da situação")
    padrao = aba.avaliar(f"{S}.padrao") or {}
    contas = aba.avaliar(f"(() => {{ const e = {S}.estado; const c = [0, 0, 0, 0]; for (const v of e) c[v]++; return c; }})()") or [0, 0, 0, 0]
    ok(contas[1] > 1000 and contas[2] == 0 and contas[3] == 0, f"sem apontamento: só não feitas no 3D ({contas})")
    sem = aba.avaliar(f"{S}.mapa.semPeca")
    ok(sem == 0, f"todo item tem peça no 3D (sem peça: {sem})")
    ok(cores_de("TESOURA 14-1") == [padrao.get("falta")], f"TESOURA 14-1 cinza ({cores_de('TESOURA 14-1')})")
    foto("_controle_3d.png")

    # 2. as unidades no lugar gravado: a TESOURA 1-1 é a do eixo A (o y maior no Posto) e acende as peças gravadas dela
    t11 = next((u for uns in LUGAR.values() for u in uns if u["nome"] == "TESOURA 1-1"), None)
    if t11:
        pecas_t11 = aba.avaliar(f"(() => {{ const k = {K('TESOURA 1-1')}; const F = {V}.fichas; return {S}.mapa.pecas[k].map(i => String(F[i].id)).sort(); }})()") or []
        ok(pecas_t11 == sorted(t11["ids"]), f"TESOURA 1-1 acende as {len(t11['ids'])} peças gravadas dela ({len(pecas_t11)})")
        ys = [u["meio"][1] for uns in LUGAR.values() for u in uns if u["nome"].startswith("TESOURA 1-")]
        ok(t11["meio"][1] == max(ys), "a TESOURA 1-1 é a do eixo A (o primeiro pela letra)")
    else:
        ok(False, "a TESOURA 1-1 tem lugar gravado")
    # as 7 TESOURA 1 separadas
    sep = aba.avaliar(f"""(() => {{ const M = {S}.mapa, I = {S}.dados.itens; const ks = I.map((x, k) => k).filter(k => /^TESOURA 1-\\d+$/.test(I[k].id));
      const todas = ks.flatMap(k => M.pecas[k]); return {{ n: ks.length, juntas: ks.some(k => M.juntasDe.has(k)),
      vazias: ks.filter(k => !M.pecas[k].length).length, repetidas: todas.length - new Set(todas).size }}; }})()""") or {}
    ok(sep.get("n") == 7 and not sep.get("juntas") and not sep.get("vazias") and not sep.get("repetidas"),
       f"as 7 TESOURA 1 se separam no 3D, cada uma com as suas peças ({sep})")

    # 3. a linha destaca no 3D
    clicar(aba, "#controle-corpo tr[data-item='TESOURA 14-1'] td:nth-child(3)")
    ok(esperar(aba, f"{V}.selecaoVarias.size > 0 && {V}.selecaoVarias.size === {S}.mapa.pecas[{K('TESOURA 14-1')}].length", 10),
       "clicar na linha TESOURA 14-1 destaca as peças dela no 3D")
    ok(aba.avaliar("document.querySelector(\"#controle-corpo tr[data-item='TESOURA 14-1']\").classList.contains('escolhida')"),
       "a linha fica marcada")
    ok("TESOURA 14-1" in (aba.avaliar("document.querySelector('#p3-situacao').textContent") or ""), "a situação do 3D diz o item")
    foto("_controle_3d_escolhida.png")
    livre = aba.avaliar("(() => { const b = document.querySelector('#p3-cores').getBoundingClientRect(); const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);"
                        " return e && e.id === 'p3-cores'; })()")
    ok(livre, "com a lista rolada, o topo do painel 3D (Cores…) fica à vista, abaixo da barra de cima")

    # 4. a peça do 3D marca a linha (mouse de verdade no quadro)
    alvo = aba.avaliar(f"""(() => {{ const q = document.querySelector('#p3-quadro').getBoundingClientRect();
      const ps = {S}.mapa.pecas[{K('TESOURA 14-1')}];
      for (const i of ps) {{ const p = {V}.paraTela(i); if (!p) continue;
        if ({V}.escolher(p[0], p[1]) === i) return [q.left + p[0], q.top + p[1]]; }}
      return null; }})()""")
    if alvo:
        aba.avaliar("document.querySelectorAll('#controle-corpo tr.escolhida').forEach(t => t.classList.remove('escolhida'))")
        clicar_em(aba, alvo[0], alvo[1])
        ok(esperar(aba, "!!document.querySelector(\"#controle-corpo tr[data-item='TESOURA 14-1'].escolhida\")", 10),
           "clicar numa peça da TESOURA 14-1 no 3D marca a linha dela na lista")
    else:
        ok(False, "achar na tela uma peça da TESOURA 14-1 para clicar")

    # 5. apontar muda a cor
    ok(apontar(aba, "TESOURA 1-3", "producao"), "apontar TESOURA 1-3 na produção")
    ok(esperar(aba, f"(() => {{ const k = {K('TESOURA 1-3')}; return k >= 0 && ({S}.dados.itens[k].feito.producao === 1); }})()", 15), "o apontamento chega no 3D")
    esperar(aba, "false", 0.6)
    ok(cores_de("TESOURA 1-3") == [padrao.get("producao")], f"TESOURA 1-3 azul ({cores_de('TESOURA 1-3')})")
    ok(cores_de("TESOURA 1-2") == [padrao.get("falta")] and cores_de("TESOURA 1-4") == [padrao.get("falta")],
       "as TESOURA 1-2 e 1-4 seguem cinza")
    ok(apontar(aba, "TESOURA 1-3", "pintura"), "apontar TESOURA 1-3 na pintura")
    ok(esperar(aba, f"{S}.dados.itens[{K('TESOURA 1-3')}].feito.pintura === 1", 15), "a pintura chega no 3D")
    esperar(aba, "false", 0.6)
    ok(cores_de("TESOURA 1-3") == [padrao.get("pintura")], f"TESOURA 1-3 verde ({cores_de('TESOURA 1-3')})")

    # 6. avulsas iguais na proporção
    av = aba.avaliar(f"""(() => {{ const I = {S}.dados.itens, M = {S}.mapa;
      const k = I.findIndex((x, t) => x.origem === 'pecas' && x.quantidade >= 4 && x.quantidade % 2 === 0 && M.pecas[t].length === x.quantidade);
      return k >= 0 ? {{ id: I[k].id, q: I[k].quantidade }} : null; }})()""")
    if av:
        ok(apontar(aba, av["id"], "producao", av["q"] // 2), f"apontar metade de {av['id']} ({av['q'] // 2} de {av['q']})")
        ok(esperar(aba, f"{S}.dados.itens[{K(av['id'])}].feito.producao === {av['q'] // 2}", 15), "o apontamento chega no 3D")
        esperar(aba, "false", 0.6)
        meio = aba.avaliar(f"""(() => {{ const ps = {S}.mapa.pecas[{K(av['id'])}]; const e = {S}.estado;
          return [ps.filter(i => e[i] === 2).length, ps.filter(i => e[i] === 1).length]; }})()""")
        ok(meio == [av["q"] // 2, av["q"] - av["q"] // 2], f"metade azul, metade cinza ({meio})")
    else:
        ok(False, "achar um item de peças avulsas iguais com todas as peças no 3D")

    # 7. só o que falta produzir
    aba.avaliar("const s = document.querySelector('#p3-mostrar'); s.value = 'falta-producao'; s.dispatchEvent(new Event('change'))")
    esperar(aba, "false", 0.4)
    esc = aba.avaliar(f"(() => {{ const ps = {S}.mapa.pecas[{K('TESOURA 1-3')}]; return ps.every(i => {V}.ocultas.has(i)) && !{S}.mapa.pecas[{K('TESOURA 1-2')}].some(i => {V}.ocultas.has(i)); }})()")
    ok(esc, "'Só o que falta produzir' esconde a TESOURA 1-3 e deixa a 1-2")
    aba.avaliar("const s = document.querySelector('#p3-mostrar'); s.value = 'tudo'; s.dispatchEvent(new Event('change'))")

    # 8. a ferramenta das cores
    clicar(aba, "#p3-cores")
    ok(esperar(aba, "!!document.querySelector('#p3-dlg-cores[open]')", 10), "Cores… abre a ferramenta")
    n_sug = aba.avaliar("document.querySelectorAll('#p3-dlg-cores [data-sugestao]').length")
    ok(n_sug == 4, f"com as sugestões de tons ({n_sug})")
    digitar(aba, "#p3-dlg-cores [data-cor=pintura] .p3-hex", "#ff0000")
    esperar(aba, "false", 0.4)
    ok(cores_de("TESOURA 1-3") == ["#ff0000"], f"a cor nova aparece no 3D na hora ({cores_de('TESOURA 1-3')})")
    clicar(aba, "#p3-gravar")
    ok(esperar(aba, "!document.querySelector('#p3-dlg-cores')", 10), "Gravar fecha a ferramenta")
    arq = os.path.join(DADOS, "_producao-cores.json")
    gravado = json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else {}
    ok(gravado.get("pintura") == "#ff0000", f"a cor fica gravada para todas as obras ({gravado})")
    projetos = _json(base + "/api/projetos")
    lista_proj = projetos.get("projetos", projetos) if isinstance(projetos, dict) else projetos
    ok(not any("producao-cores" in json.dumps(p, ensure_ascii=False) for p in lista_proj), "o arquivo das cores não vira projeto")
    aba.navegar(base + "/controle-producao?projeto=posto-3d", limite=60)
    ok(esperar(aba, f"!!({S} && {S}.estado)", 240), "recarregar abre o 3D de novo")
    ok(cores_de("TESOURA 1-3") == ["#ff0000"], "ao recarregar a cor gravada continua")
    clicar(aba, "#p3-cores")
    esperar(aba, "!!document.querySelector('#p3-dlg-cores[open]')", 10)
    clicar(aba, "#p3-dlg-cores [data-sugestao='0']")
    clicar(aba, "#p3-gravar")
    esperar(aba, "!document.querySelector('#p3-dlg-cores')", 10)
    ok(not os.path.exists(arq) and cores_de("TESOURA 1-3") == [padrao.get("pintura")], "Padrão + Gravar volta ao verde e apaga o arquivo")

    # 9. o botão 3D
    clicar(aba, "#btn-3d")
    escondeu = esperar(aba, "document.querySelector('#painel3d').hidden && !document.body.classList.contains('com-3d')", 5)
    onde = aba.avaliar("(() => { const b = document.querySelector('#btn-3d').getBoundingClientRect(); const e = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);"
                       " return [Math.round(b.left), Math.round(b.top), e ? (e.id || e.className || e.tagName) : null]; })()")
    ok(escondeu, f"o botão 3D esconde o painel (o botão em {onde})")
    clicar(aba, "#btn-3d")
    ok(esperar(aba, "!document.querySelector('#painel3d').hidden", 5), "e mostra de novo")

    erros = [c for c in aba.console if c[0] in ("error", "excecao")]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.terminate(); srv.terminate()
    try: nav.wait(10); srv.wait(10)
    except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
