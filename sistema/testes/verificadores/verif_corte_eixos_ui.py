# -*- coding: utf-8 -*-
"""O corte do 3D nas elevações dos eixos (12/10/2026, web/cad/corte_eixos.js — pedido do usuário no Posto CB).
Num projeto com o 3D pronto (montado por outro caminho) e os eixos gravados: "Todas as elevações" no título da
Implantação abre uma elevação por eixo com o corte do 3D — as barras no plano do eixo em linha cheia com o nome da peça,
a tesoura que corre ao lado do eixo tracejada com o afastamento, a terça que atravessa como marca de corte com a sigla —
e a conferência: a tesoura e o pilar no mesmo alinhamento fora do eixo viram UMA linha; o pilar fora do cruzamento
aparece uma vez só (na elevação do eixo de que ele mais se afasta); a caixa "3D" no título tira e põe o corte; a lista
da "Conferência" abre; tudo continua depois de gravar e abrir de novo."""
import json, os, subprocess, sys, tempfile, time, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_corte_eixos_")
PASTA = os.path.join(DADOS, "obra")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
# os eixos 1, 2, 3 (a cada 6 m) e A, B (10 m); os níveis
json.dump({"formato": 1, "nome": "Obra", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-12T00:00:00", "alterado": "2026-10-12T00:00:00", "dados": None,
           "niveis": [{"nome": "BASE", "z": 0.0}, {"nome": "BANZO INFERIOR", "z": 6000.0}],
           "eixos": {"eixo_g": [1.0, 0.0], "perp_g": [0.0, 1.0], "numeros": [{"nome": "1", "pos": 0.0}, {"nome": "2", "pos": 6000.0}, {"nome": "3", "pos": 12000.0}],
                     "letras": [{"nome": "A", "pos": 0.0}, {"nome": "B", "pos": 10000.0}], "extras": [], "z_base": 0.0, "origem": "usuario"}},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"), ensure_ascii=False)
# o 3D: a TESOURA 1 no eixo 2; a TESOURA 2 a 0,30 m do eixo 3, com os pilares dela no mesmo alinhamento; um pilar a 0,25 m
# do cruzamento 2/B ao longo do eixo 2 (fora do eixo B); a terça TC1 atravessando os eixos 2 e 3
ents, n = [], 0


def barra(a, b, papel, peca="", planta="", sigla="", perfil="U 100×40×2,25 (FF)"):
    global n
    n += 1
    o = {"peca": peca, "planta": planta} if peca else {}
    if sigla: o["sigla"] = sigla
    ents.append({"id": "b%d" % n, "tipo": "barra", "nome": perfil, "camada": "Treliças", "perfil": perfil, "papel": papel, "rotacao": 0.0,
                 "inicio": list(a), "fim": list(b), "atributos": {"origem": o}})


for x, peca, planta in ((6000.0, "TESOURA 1#1", "TESOURA 1"), (12300.0, "TESOURA 2#2", "TESOURA 2")):
    barra((x, 0, 6000), (x, 10000, 6000), "banzo", peca, planta)
    barra((x, 0, 7000), (x, 10000, 7000), "banzo", peca, planta)
    for y in (0.0, 5000.0, 10000.0):
        barra((x, y, 6000), (x, y, 7000), "montante", peca, planta, perfil='L 1"×1/8"')
barra((3000.0, 0, 6000), (3000.0, 10000, 6000), "banzo", "TESOURA 3#3", "TESOURA 3")
barra((3000.0, 0, 7000), (3000.0, 10000, 7000), "banzo", "TESOURA 3#3", "TESOURA 3")
for p in ((0.0, 0.0), (6000.0, 0.0), (12300.0, 0.0), (12300.0, 10000.0), (6000.0, 10250.0)):
    barra((p[0], p[1], 0), (p[0], p[1], 6000), "pilar", perfil="Ue 200×70×20×2,65")
barra((0, 5000, 7100), (13000, 5000, 7100), "terça", sigla="TC1")
json.dump({"nome": "Modelo", "unidade": "mm", "entidades": ents, "camadas": [], "materiais": [], "metadados": {}},
          open(os.path.join(PASTA, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)
# o desenho do cliente (a Original), só para a Montagem ter de onde partir
json.dump({"nome": "Planta de lançamento", "unidade": "mm", "escala": 100,
           "camadas": {"ARQ": {"nome": "ARQ", "cor": "#888888", "visivel": True, "bloqueada": True}},
           "entidades": [{"id": "a1", "tipo": "linha", "camada": "ARQ", "a": [0, 0], "b": [12000, 0]},
                         {"id": "a2", "tipo": "linha", "camada": "ARQ", "a": [0, 10000], "b": [12000, 10000]}],
           "vistas": [], "metadados": {}},
          open(os.path.join(PASTA, "desenhos-2d", "planta-de-lançamento.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_corte_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


def abrir(aba):
    aba.navegar(base + "/cad?projeto=obra&desenho=planta-de-lançamento", limite=60)
    esperar(aba, "document.body.dataset.pronto === '1' && !!window.montagem", 40)
    aba.avaliar("(async () => { await window.montagem.ir('montagem'); return 1; })()")
    esperar(aba, "window.cad.nomeDesenho === 'montagem'", 20)


CONTAR = """((eixo, filtro) => { const m = window.montagem; const q = m._elevacoes().find(x => x.eixo === eixo);
  if (!q) return null; return [...window.cad.doc.entidades.values()].filter(e => { const a = e.atributos || {}; return a.quadro === q.id && a.do3d && filtro(e); }).length; })"""

try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for d in ("Page", "Runtime", "Log"): aba.cmd(f"{d}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1600, height=900, deviceScaleFactor=1, mobile=False)
    abrir(aba)
    ok(aba.avaliar("window.cad.nomeDesenho") == "montagem", "a Montagem abre")

    # 1. "Todas as elevações": os eixos vêm do projeto, uma elevação por eixo, com o 3D
    aba.avaliar("(async () => { await window.montagem.garantirImplantacao(); return 1; })()")
    btn = aba.avaliar("!![...document.querySelectorAll('.quadro-titulo[data-tipo=\"implantacao\"] button')].find(b => b.textContent === 'Todas as elevações')")
    ok(btn, "o botão \"Todas as elevações\" no título da Implantação")
    aba.avaliar("(async () => { await window.montagem.todasAsElevacoes(); return 1; })()")
    els = aba.avaliar("window.montagem._elevacoes().map(q => q.eixo + ':' + !!q.do3d).join(' ')")
    ok(els == "1:true 2:true 3:true A:true B:true", f"uma elevação por eixo, com o 3D ({els})")

    # 2. o corte: a TESOURA 1 no plano do eixo 2, com o nome; a marca da terça TC1 com a sigla
    linhas2 = aba.avaliar(CONTAR + "('2', e => e.tipo === 'linha' && e.camada === 'IMPL 3D')")
    ok(linhas2 is not None and linhas2 >= 5, f"elevação 2: as barras da TESOURA 1 em linha cheia ({linhas2})")
    nome2 = aba.avaliar(CONTAR + "('2', e => e.tipo === 'texto' && e.texto === 'TESOURA 1')")
    ok(nome2 == 1, "elevação 2: o nome da TESOURA 1 em cima dela")
    corte2 = aba.avaliar(CONTAR + "('2', e => e.tipo === 'polilinha' && e.camada === 'IMPL 3D CORTE')")
    sig2 = aba.avaliar(CONTAR + "('2', e => e.tipo === 'texto' && e.texto === 'TC1')")
    ok(corte2 >= 1 and sig2 == 1, f"elevação 2: a terça TC1 atravessando, com a marca e a sigla ({corte2}, {sig2})")
    # o pilar a 0,25 m do cruzamento 2/B (ao longo do eixo 2) não é "no plano" do eixo 2 duas vezes: entra, mas sem apontamento ali
    conf2 = aba.avaliar("(window.montagem._elevacoes().find(q => q.eixo === '2').conferencia_3d || []).map(c => c.texto)")
    ok(not any("pilar" in t for t in conf2), f"elevação 2: o pilar deslocado ao longo do eixo 2 não é apontado nela ({conf2})")

    # 3. a TESOURA 2 a 0,30 m do eixo 3: tracejada, com o afastamento; tesoura e pilares numa linha só da conferência
    lado3 = aba.avaliar(CONTAR + "('3', e => e.tipo === 'linha' && e.camada === 'IMPL 3D AO LADO')")
    ok(lado3 is not None and lado3 >= 7, f"elevação 3: a TESOURA 2 e os pilares dela tracejados ao lado ({lado3})")
    rot3 = aba.avaliar(CONTAR + "('3', e => e.tipo === 'texto' && /TESOURA 2 \\(0,30 m ao lado\\)/.test(e.texto))")
    ok(rot3 == 1, "elevação 3: o nome com o afastamento (\"TESOURA 2 (0,30 m ao lado)\")")
    conf3 = aba.avaliar("(window.montagem._elevacoes().find(q => q.eixo === '3').conferencia_3d || []).map(c => c.texto)")
    ok(len(conf3) == 1 and "TESOURA 2" in conf3[0] and "2 pilares" in conf3[0] and "0,30 m" in conf3[0],
       f"elevação 3: tesoura e pilares no mesmo alinhamento numa linha só ({conf3})")
    marcas3 = aba.avaliar(CONTAR + "('3', e => e.tipo === 'circulo' && e.camada === 'IMPL CONFERENCIA')")
    ok(marcas3 == 1, "elevação 3: a marca vermelha da conferência")

    # 4. o pilar a 0,25 m do cruzamento 2/B: apontado uma vez, na elevação B (o eixo de que ele se afasta)
    confB = aba.avaliar("(window.montagem._elevacoes().find(q => q.eixo === 'B').conferencia_3d || []).map(c => c.texto)")
    ok(any("pilar" in t and "B/2" in t and "0,25 m" in t for t in confB), f"elevação B: o pilar a 0,25 m do eixo B ({confB})")
    total = aba.avaliar("window.montagem._elevacoes().reduce((s, q) => s + (q.conferencia_3d || []).filter(c => /pilar/.test(c.texto) && /B\\/2/.test(c.texto)).length, 0)")
    ok(total == 1, f"o pilar de 2/B aparece uma vez só na conferência ({total})")

    # 5. a caixa "3D" no título tira e põe o corte
    aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(x => x.eixo === '2');
      const c = document.querySelector(`.quadro-titulo[data-quadro="${q.id}"] .quadro-3d input`); c.checked = false; c.dispatchEvent(new Event('change')); return 1; })()""")
    esperar(aba, CONTAR + "('2', e => true) === 0", 10)
    ok(aba.avaliar(CONTAR + "('2', e => true)") == 0, "desmarcar \"3D\" tira o corte da elevação 2")
    aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(x => x.eixo === '2');
      const c = document.querySelector(`.quadro-titulo[data-quadro="${q.id}"] .quadro-3d input`); c.checked = true; c.dispatchEvent(new Event('change')); return 1; })()""")
    esperar(aba, CONTAR + "('2', e => true) > 0", 10)
    ok(aba.avaliar(CONTAR + "('2', e => e.camada === 'IMPL 3D')") >= 5, "marcar de novo põe o corte de volta")

    # 6. a lista da Conferência
    aba.avaliar("window.montagem.conferenciaDosEixos(); 1")
    esperar(aba, "!!document.querySelector('.conferencia-eixos')", 8)
    itens = aba.avaliar("document.querySelectorAll('.conferencia-eixos li').length")
    ok(itens == 2, f"\"Conferência\": a lista com os 2 apontamentos ({itens})")
    aba.avaliar("(() => { const b = document.getElementById('dialogo-cancelar') || document.getElementById('dialogo-ok'); if (b) b.click(); return 1; })()")

    # 7. "Linhas das peças": a TESOURA 2 (0,30 m do eixo 3) e a TESOURA 3 (entre os eixos 1 e 2) ganham linha e elevação;
    # a do eixo 2 não (é o eixo); a linha tracejada na Implantação; o eixo 3 continua apontando a TESOURA 2
    aba.avaliar("(async () => { await window.montagem.linhasDasPecas(); return 1; })()")
    linhas = aba.avaliar("(window.montagem.m.linhas || []).map(l => l.nome + ':' + l.familia + ':' + l.pecas.join(',')).join(' | ')")
    ok(linhas == "1+3,00:numero:TESOURA 3 | 3+0,30:numero:TESOURA 2", f"as linhas das peças fora dos eixos ({linhas})")
    el_l = aba.avaliar("window.montagem._elevacoes().filter(q => q.linha).map(q => q.eixo).join(' ')")
    ok(el_l == "1+3,00 3+0,30", f"uma elevação por linha ({el_l})")
    no_l = aba.avaliar(CONTAR + "('3+0,30', e => e.tipo === 'linha' && e.camada === 'IMPL 3D')")
    ok(no_l is not None and no_l >= 5, f"na elevação da linha 3+0,30 a TESOURA 2 é cheia, no plano ({no_l})")
    conf_l = aba.avaliar("(window.montagem._elevacoes().find(q => q.eixo === '3+0,30').conferencia_3d || []).map(c => c.texto)")
    ok(not any("TESOURA 2" in t for t in conf_l), f"na linha dela a TESOURA 2 não é apontada ({conf_l})")
    impl = aba.avaliar("""(() => { const qi = window.montagem._quadroImplantacao(); return [...window.cad.doc.entidades.values()].filter(e => {
      const a = e.atributos || {}; return a.quadro === qi.id && a.linha && e.tipo === 'linha'; }).length; })()""")
    ok(impl == 2, f"as 2 linhas tracejadas na Implantação ({impl})")
    conf3b = aba.avaliar("(window.montagem._elevacoes().find(q => q.eixo === '3').conferencia_3d || []).map(c => c.texto)")
    ok(any("TESOURA 2" in t for t in conf3b), "o eixo 3 continua apontando a TESOURA 2 fora da linha dele")

    # 8. grava e abre de novo: as elevações e o corte continuam
    aba.avaliar("(async () => { await window.montagem._gravarJa(); await window.cad.salvar({ avisar: false }); return 1; })()")
    # a gravação adiada da Montagem (400 ms) termina antes de sair da página (senão o aviso de "não gravado" do navegador)
    esperar(aba, "!window.montagem._timer && !window.cad._editado", 15)
    abrir(aba)
    de_novo = aba.avaliar("window.montagem._elevacoes().filter(q => q.do3d).length")
    linhas = aba.avaliar(CONTAR + "('2', e => e.camada === 'IMPL 3D')")
    ok(aba.avaliar("(window.montagem.m.linhas || []).length") == 2, "as linhas continuam depois de abrir de novo")
    ok(de_novo == 7 and linhas and linhas >= 5, f"depois de abrir de novo: as 7 elevações com o 3D ({de_novo}, {linhas})")

    erros = [c for c in aba.console if c[0] in ("excecao", "error")]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.kill(); srv.kill()

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
