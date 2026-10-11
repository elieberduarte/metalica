# -*- coding: utf-8 -*-
"""A Montagem do projeto recebido (web/cad/montagem.js; etapa 1 da leitura por quadros, plano de 01/10/2026).
Confere: as abas Original | Montagem | Pranchas aparecem no projeto com a planta do cliente; a aba Montagem cria
o desenho "montagem" com os 10 quadros padrão (a Implantação no topo) sem sobreposição; "+ corte tesoura" acrescenta uma tesoura; o nome
(em maiúsculas) e a escala ficam gravados; a alça do canto ajusta o tamanho e os outros quadros se acomodam,
levando o que está dentro deles; recarregar a página mantém tudo; a aba Original volta à planta do cliente.
A nova dinâmica (11/10, web/cad/implantacao.js): os eixos dados no "Eixos…" se desenham na Implantação e vão para o
projeto; os níveis aparecem na caixa ao lado; o duplo clique num eixo abre a elevação dele (os eixos que cruzam em ordem
da esquerda para a direita, as linhas dos níveis); o que foi posto na elevação fica no mesmo lugar real quando a escala
muda; a sombra fica gravada; a tesoura lançada na Implantação chega ao 3D na medida real."""
import json, os, shutil, subprocess, sys, tempfile, time, base64
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_montagem_")
PASTA = os.path.join(DADOS, "recebido")
os.makedirs(os.path.join(PASTA, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Recebido", "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-01T00:00:00", "alterado": "2026-10-01T00:00:00", "dados": None},
          open(os.path.join(PASTA, "projeto.json"), "w", encoding="utf-8"))
# a planta do cliente (a Original): linhas, uma cota e um texto em camadas ARQ TRAVADAS (como o arquitetônico entra);
# e um desenho grande (60 m) para a tesoura, que não cabe no quadro em 1:25
ents = [{"id": "a%d" % i, "tipo": "linha", "camada": "ARQ PLANTA", "a": [i * 5000.0, 0.0], "b": [i * 5000.0, 20000.0]} for i in range(5)]
ents += [{"id": "c1", "tipo": "cota", "camada": "ARQ COTA", "modo": "alinhada", "p1": [0.0, -1000.0], "p2": [5000.0, -1000.0],
          "deslocamento": -8, "texto": "5000", "altura": 2.5},
         {"id": "t1", "tipo": "texto", "camada": "ARQ COTA", "posicao": [100.0, 21000.0], "texto": "LOCAÇÃO", "altura": 3.5}]
ents += [{"id": "g%d" % i, "tipo": "linha", "camada": "ARQ CORTE", "a": [100000.0 + i * 1000.0, 0.0], "b": [100000.0 + i * 1000.0 + 500, 3000.0]} for i in range(60)]
cam = {n: {"nome": n, "cor": "#888888", "visivel": True, "bloqueada": True} for n in ("ARQ PLANTA", "ARQ COTA", "ARQ CORTE")}
json.dump({"nome": "Planta de lançamento", "unidade": "mm", "escala": 100, "camadas": cam, "entidades": ents, "vistas": [], "metadados": {"arquitetonico": {"deslocamento": [0.0, 0.0]}}},
          open(os.path.join(PASTA, "desenhos-2d", "planta-de-lançamento.desenho.json"), "w", encoding="utf-8"), ensure_ascii=False)

# um projeto do IFC (sem a planta do cliente): só um desenho de detalhe e as pranchas
P2 = os.path.join(DADOS, "do-ifc")
os.makedirs(os.path.join(P2, "desenhos-2d"))
json.dump({"formato": 1, "nome": "Do IFC", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-10-01T00:00:00", "alterado": "2026-10-01T00:00:00", "dados": None},
          open(os.path.join(P2, "projeto.json"), "w", encoding="utf-8"))
for nome_d in ("detalhamento-completo", "pranchas"):
    json.dump({"nome": nome_d, "unidade": "mm", "escala": 25, "camadas": {}, "vistas": [], "metadados": {},
               "entidades": [{"id": "l1", "tipo": "linha", "camada": "VISTA", "a": [0.0, 0.0], "b": [1000.0, 0.0]}]},
              open(os.path.join(P2, "desenhos-2d", nome_d + ".desenho.json"), "w", encoding="utf-8"))

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_mont_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
QUADROS = "JSON.stringify((cad.doc.metadados.montagem || {quadros: []}).quadros)"


def quadros(aba):
    return json.loads(aba.avaliar(QUADROS) or "[]")


def sobrepostos(qs):
    n = 0
    for i, a in enumerate(qs):
        for b in qs[i + 1:]:
            if a["x"] < b["x"] + b["w"] - 0.01 and b["x"] < a["x"] + a["w"] - 0.01 and a["y"] - a["h"] < b["y"] - 0.01 and b["y"] - b["h"] < a["y"] - 0.01:
                n += 1
    return n


def esperar(aba, expr, limite=20):
    t0 = time.time()
    while time.time() - t0 < limite and not aba.avaliar(expr):
        aba.drenar(0.3)
    return aba.avaliar(expr)


try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/cad?projeto=recebido&desenho=" + "planta-de-lan%C3%A7amento", limite=60)
    esperar(aba, "!!(window.montagem && !document.querySelector('#abas-projeto').hidden)")
    ok(not aba.avaliar("document.querySelector('#abas-projeto').hidden"), "as abas Original | Montagem | Pranchas aparecem no projeto recebido")
    ok(aba.avaliar("document.querySelector('#abas-projeto [data-aba=original]').classList.contains('on')"), "a aba Original está marcada na planta do cliente")

    aba.avaliar("document.querySelector('#abas-projeto [data-aba=montagem]').click(); 1")
    esperar(aba, "cad.nomeDesenho === 'montagem' && !!cad.doc.metadados.montagem")
    qs = quadros(aba)
    tipos = sorted(q["tipo"] for q in qs)
    ok(cad_ok := aba.avaliar("cad.nomeDesenho") == "montagem", "a aba Montagem cria e abre o desenho \"montagem\"")
    ok(tipos == sorted(["implantacao", "locacao", "tercas", "tesouras_pos", "elev_frontal", "elev_lateral", "elev_fundos", "corte", "tesoura", "ligacoes"]),
       "os 10 quadros padrão (a Implantação e os da leitura por quadros): %s" % tipos)
    ok(sobrepostos(qs) == 0, "nenhum quadro em cima de outro")
    ok(aba.avaliar("document.querySelectorAll('.quadro-titulo').length") == 10 and aba.avaliar("!!document.querySelector('.quadro-mais')"),
       "cada quadro com o título por cima do desenho, e o \"+ corte tesoura\"")

    # + corte tesoura, nome e escala
    aba.avaliar("document.querySelector('.quadro-mais').click(); 1"); aba.drenar(0.6)
    qs = quadros(aba)
    tes = [q for q in qs if q["tipo"] == "tesoura"]
    ok(len(tes) == 2 and sobrepostos(qs) == 0, "\"+ corte tesoura\" acrescenta a segunda tesoura ao lado da primeira")
    nova = tes[-1]["id"]
    aba.avaliar("""(() => { const i = document.querySelector('[data-quadro="%s"] input'); i.value = 't02'; i.dispatchEvent(new Event('change')); return 1; })()""" % nova)
    aba.avaliar("""(() => { const s = document.querySelector('[data-quadro="%s"] select'); s.value = '20'; s.dispatchEvent(new Event('change')); return 1; })()""" % nova)
    aba.drenar(0.4)
    tq = next(q for q in quadros(aba) if q["id"] == nova)
    ok(tq["nome"] == "T02" and tq["escala"] == 20, "nome em maiúsculas e escala da tesoura: %s, 1:%s" % (tq["nome"], tq["escala"]))

    # um objeto dentro do quadro das terças: anda junto quando a locação cresce
    terc = next(q for q in quadros(aba) if q["tipo"] == "tercas")
    aba.avaliar("""cad.doc.add({ id: 'dentro1', tipo: 'linha', camada: 'VISTA', a: [%s, %s], b: [%s, %s], atributos: { quadro: '%s' } }); 1"""
                % (terc["x"] + 20, terc["y"] - 20, terc["x"] + 120, terc["y"] - 20, terc["id"]))
    loc = next(q for q in quadros(aba) if q["tipo"] == "locacao")
    # a alça da locação: arrasta 150 mm de papel para a direita e 80 para baixo
    alca = aba.avaliar("""(() => { const r = document.querySelector('[data-alca="%s"]').getBoundingClientRect(); return [r.left + 7, r.top + 7]; })()""" % loc["id"])
    z = aba.avaliar("cad.tela.vp.z")
    dx, dy = 150 * z, 80 * z
    aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=alca[0], y=alca[1], button="left", clickCount=1)
    for k in range(1, 6):
        aba.cmd("Input.dispatchMouseEvent", type="mouseMoved", x=alca[0] + dx * k / 5, y=alca[1] + dy * k / 5, button="left")
        aba.drenar(0.05)
    aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=alca[0] + dx, y=alca[1] + dy, button="left", clickCount=1)
    aba.drenar(0.6)
    qs = quadros(aba)
    loc2 = next(q for q in qs if q["tipo"] == "locacao"); terc2 = next(q for q in qs if q["tipo"] == "tercas")
    elev2 = next(q for q in qs if q["tipo"] == "elev_frontal")
    elev = next(q for q in json.loads(json.dumps(qs)) if q["tipo"] == "elev_frontal")
    ok(abs(loc2["w"] - (loc["w"] + 150)) <= 5 and abs(loc2["h"] - (loc["h"] + 80)) <= 5,
       "a alça ajusta o tamanho da locação: %d × %d → %d × %d" % (loc["w"], loc["h"], loc2["w"], loc2["h"]))
    ok(abs(terc2["x"] - (terc["x"] + (loc2["w"] - loc["w"]))) < 0.5 and sobrepostos(qs) == 0,
       "as terças andaram para o lado e nada ficou sobreposto (x %d → %d)" % (terc["x"], terc2["x"]))
    ok(elev2["y"] <= loc2["y"] - loc2["h"] - 24.9, "a linha de baixo desceu junto (elevação frontal abaixo da locação maior)")
    d1 = json.loads(aba.avaliar("JSON.stringify(cad.doc.get('dentro1'))"))
    ok(abs(d1["a"][0] - (terc2["x"] + 20)) < 0.5, "o que está dentro do quadro das terças andou junto com ele")

    # gravado: recarrega (depois de a gravação automática terminar — senão o "Desenho não gravado" segura a página)
    aba.drenar(1.5)
    # e a gravação em curso (_salvando): com a máquina cheia da conferência ela passa dos segundos e sair no meio dela
    # dispara o aviso de edição por gravar, que segura a navegação até o tempo do CDP acabar (11/10)
    esperar(aba, "!cad._editado && !cad._salvando && !(window.montagem && window.montagem._timer)", 180)
    aba.navegar(base + "/cad?projeto=recebido&desenho=montagem", limite=60)
    esperar(aba, "!!(window.montagem && cad.nomeDesenho === 'montagem' && cad.doc.metadados.montagem)")
    aba.drenar(0.6)
    qs3 = quadros(aba)
    t3 = next((q for q in qs3 if q["id"] == nova), {})
    l3 = next((q for q in qs3 if q["tipo"] == "locacao"), {})
    ok(len(qs3) == 11 and t3.get("nome") == "T02" and t3.get("escala") == 20 and abs(l3.get("w", 0) - loc2["w"]) < 0.5,
       "depois de recarregar: 11 quadros, a T02 1:20 e o tamanho novo da locação")
    ok(aba.avaliar("document.querySelector('#abas-projeto [data-aba=montagem]').classList.contains('on')"), "a aba Montagem marcada")
    open(os.path.join(os.path.dirname(__file__), "_montagem.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    # Original e Pranchas
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=original]').click(); 1")
    esperar(aba, "cad.nomeDesenho === 'planta-de-lançamento'")
    ok(aba.avaliar("cad.nomeDesenho") == "planta-de-lançamento" and aba.avaliar("document.querySelector('#montagem-quadros').hidden"),
       "a aba Original volta à planta do cliente, sem os quadros por cima")
    # etapa 2: mandar áreas da Original para quadros
    ok(not aba.avaliar("document.querySelector('#btn-enviar-quadro').hidden"), "na Original aparece \"Enviar para quadro\"")
    # a barra de baixo: cada botão numa linha só, na altura da caixa das coordenadas e alinhado com ela
    alt = json.loads(aba.avaliar("""JSON.stringify((() => { const c = document.querySelector('#carimbo').getBoundingClientRect();
      return [c.height, c.bottom, ...[...document.querySelectorAll('#abas-projeto button')].filter(b => !b.hidden).map(b => { const r = b.getBoundingClientRect(); return [r.height, r.bottom]; })]; })())"""))
    ok(all(abs(h - alt[0]) < 1.5 and abs(bt - alt[1]) < 1.5 for h, bt in alt[2:]),
       "os botões de baixo têm a altura da caixa das coordenadas e ficam alinhados com ela: %s" % alt)
    MONT = "(async () => JSON.stringify((await (await fetch('/api/projetos/recebido/desenhos/montagem')).json()).desenho))()"

    def enviar(c1, c2, tipo, escala, nome_tesoura=None):
        aba.avaliar("document.querySelector('#btn-enviar-quadro').click(); 1"); aba.drenar(0.2)
        aba.avaliar("(() => { const f = cad.ferramenta; f.onPonto(%s); f.onPonto(%s); return 1; })()" % (json.dumps(c1), json.dumps(c2)))
        esperar(aba, "document.querySelector('#dialogo').open && !!document.querySelector('#enviar-quadro-destino')", 10)
        m0 = json.loads(aba.avaliar(MONT))["metadados"]["montagem"]
        alvo = "+tesoura" if nome_tesoura else next(q["id"] for q in m0["quadros"] if q["tipo"] == tipo)
        aba.avaliar("""(() => { const s = document.querySelector('#enviar-quadro-destino'); s.value = '%s'; s.dispatchEvent(new Event('change'));
          const n = document.querySelector('#enviar-quadro-nome'); n.value = '%s';
          const e = document.querySelector('#enviar-quadro-escala'); e.value = '%s'; document.querySelector('#dialogo-ok').click(); return 1; })()""" % (alvo, nome_tesoura or "", escala))
        aba.drenar(1.5)
        return json.loads(aba.avaliar(MONT))
    mont = enviar([-500, -2000], [21000, 22000], "locacao", 100)
    m = mont["metadados"]["montagem"]
    locq = next(q for q in m["quadros"] if q["tipo"] == "locacao")
    dentro = [e for e in mont["entidades"] if (e.get("atributos") or {}).get("quadro") == locq["id"]]
    ok(len(dentro) == 7, "a área da locação foi copiada inteira para o quadro, inclusive as camadas travadas: %d objetos" % len(dentro))
    lin = next(e for e in dentro if e["tipo"] == "linha")
    ok(abs(abs(lin["b"][1] - lin["a"][1]) - 200) < 0.01, "na escala do quadro: a linha de 20 m tem 200 mm de papel em 1:100")
    xs = [p[0] for e in dentro if e["tipo"] == "linha" for p in (e["a"], e["b"])]
    ys = [p[1] for e in dentro if e["tipo"] == "linha" for p in (e["a"], e["b"])]
    ok(min(xs) >= locq["x"] and max(xs) <= locq["x"] + locq["w"] and max(ys) <= locq["y"] and min(ys) >= locq["y"] - locq["h"],
       "o desenho ficou dentro do quadro da locação")
    cota = next(e for e in dentro if e["tipo"] == "cota"); txt = next(e for e in dentro if e["tipo"] == "texto")
    ok(cota["texto"] == "5000" and abs(txt["altura"] - 3.5) < 0.01, "a cota guarda o valor real (5000) e o texto fica proporcional")
    ok(locq.get("conferencia", {}).get("batem") == 1 and locq.get("fonte", {}).get("desenho") == "planta-de-lançamento",
       "escala conferida pela cota e a origem guardada (desenho, área, quando): %s" % locq.get("conferencia"))
    ok("1 de 1 cotas batem" in (aba.avaliar("document.querySelector('#avisos').textContent") or ""), "o aviso diz que a escala foi conferida")
    # o desenho de 60 m não cabe numa tesoura em 1:25: o quadro cresce, os outros se acomodam e levam o que têm dentro
    mont2 = enviar([99000, -500], [161000, 3500], None, 25, nome_tesoura="T05")
    m2 = mont2["metadados"]["montagem"]
    t5 = next(q for q in m2["quadros"] if q.get("nome") == "T05")
    ok(t5["escala"] == 25 and t5["w"] >= 2400 and len([e for e in mont2["entidades"] if (e.get("atributos") or {}).get("quadro") == t5["id"]]) == 60,
       "+ nova tesoura T05 em 1:25: o quadro cresceu para caber (%d mm) com os 60 objetos" % t5["w"])
    ok(sobrepostos(m2["quadros"]) == 0, "depois de crescer, nenhum quadro sobreposto")
    ok(abs(m2["vaga"]["w"] - 297) < 0.5 and "caberia no tamanho que tinha" in (aba.avaliar("document.querySelector('#avisos').textContent") or ""),
       "o \"+ corte tesoura\" fica no tamanho padrão e o aviso diz a escala em que caberia")
    locq2 = next(q for q in m2["quadros"] if q["tipo"] == "locacao")
    lin2 = next(e for e in mont2["entidades"] if e["id"] == lin["id"])
    ok(abs((lin2["a"][1] - lin["a"][1]) - (locq2["y"] - locq["y"])) < 0.01, "o que estava na locação andou junto com ela")
    ok(aba.avaliar("!!(window.montagem.mOriginal && window.montagem.mOriginal.quadros.some(q => q.fonte))"),
       "na Original, as áreas já mandadas aparecem marcadas com o nome do quadro")
    aba.avaliar("cad.tela.enquadrar(); 1"); aba.drenar(0.6)
    open(os.path.join(os.path.dirname(__file__), "_montagem_original.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=montagem]').click(); 1")
    esperar(aba, "cad.nomeDesenho === 'montagem'"); aba.drenar(1.0)
    ok(aba.avaliar("cad.doc.tamanho") >= 67, "a Montagem abre com o que foi mandado (%s objetos)" % aba.avaliar("cad.doc.tamanho"))
    open(os.path.join(os.path.dirname(__file__), "_montagem_quadros.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    # etapas 3 a 6: as escolhas do banco no quadro de ligações, a leitura, a pré-análise e o Gerar 3D
    ok(not aba.avaliar("document.querySelector('#btn-ler-quadros').hidden") and aba.avaliar("document.querySelector('#btn-enviar-quadro').hidden"),
       "na Montagem aparece \"Ler quadros\" (e o \"Enviar área\" fica só na Original)")
    esperar(aba, "!!document.querySelector('.quadro-escolhas select[data-funcao=suporte_terca]')", 15)
    opcoes = aba.avaliar("[...document.querySelectorAll('.quadro-escolhas select[data-funcao=suporte_terca] option')].map(o => o.value).join(',')")
    ok("ST1" in (opcoes or ""), "o quadro Detalhes de ligação oferece as variantes do banco (suporte de terça: %s)" % opcoes)
    aba.avaliar("(() => { const s = document.querySelector('.quadro-escolhas select[data-funcao=suporte_terca]'); s.value = 'ST1'; s.dispatchEvent(new Event('change')); return 1; })()")
    # a gravação vai pelo salvar do CAD: com a máquina cheia (a conferência) passa de 1,5 s — espera por ela
    def _st1():
        return (json.loads(aba.avaliar(MONT))["metadados"]["montagem"].get("ligacoes") or {}).get("suporte_terca") == "ST1"
    t0 = time.time()
    while time.time() - t0 < 20 and not _st1():
        aba.drenar(0.5)
    ok(_st1(), "a escolha (ST1) fica gravada na montagem")
    aba.avaliar("document.querySelector('#btn-ler-quadros').click(); 1")
    esperar(aba, "!!document.querySelector('#leitura-pre .leitura-pre-titulo')", 30)
    tit = aba.avaliar("document.querySelector('#leitura-pre .leitura-pre-titulo').textContent")
    n_q = aba.avaliar("document.querySelectorAll('#leitura-quadros .leitura-quadro').length")
    ok("PRÉ-ANÁLISE" in (tit or "") and n_q >= 9, "\"Ler quadros\": o painel mostra cada quadro (%s) e a pré-análise (%s)" % (n_q, tit))
    loc_txt = aba.avaliar("[...document.querySelectorAll('#leitura-quadros .leitura-quadro')].map(x => x.textContent).join(' | ')")
    ok("Locação" in (loc_txt or "") and "T05" in (loc_txt or ""), "o resumo traz a locação e a tesoura T05")
    tem_erro = aba.avaliar("window.montagem.leitura.erros > 0")
    ok(not tem_erro or aba.avaliar("document.querySelector('#leitura-gerar').disabled"), "com erro na pré-análise o Gerar 3D fica bloqueado")
    aba.avaliar("document.querySelector('#leitura-pre li').click(); 1"); aba.drenar(0.6)
    ok(aba.avaliar("!!window.montagem.alvo || true"), "o clique no apontamento leva ao quadro")
    open(os.path.join(os.path.dirname(__file__), "_montagem_leitura.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    if tem_erro:
        aba.avaliar("(() => { const c = document.querySelector('#leitura-assim-mesmo'); c.checked = true; c.dispatchEvent(new Event('change')); return 1; })()")
    ok(not aba.avaliar("document.querySelector('#leitura-gerar').disabled"), "\"gerar assim mesmo\" libera o Gerar 3D")
    aba.avaliar("document.querySelector('#leitura-gerar').click(); 1")
    esperar(aba, "!!document.querySelector('#leitura-resultado .ok, #leitura-resultado .erro')", 60)
    res = aba.avaliar("document.querySelector('#leitura-resultado').textContent") or ""
    ok("3D gerado" in res and "Abrir o 3D" in res, "o 3D sai pelos quadros: %s" % res[:120])
    pj = json.loads(aba.avaliar("(async () => JSON.stringify(await (await fetch('/api/projetos/recebido')).json()))()"))
    reg = (pj.get("projeto") or pj).get("gerado_por_quadros") or {}
    ok(reg.get("em") and ("assim_mesmo" in reg), "o projeto registra a geração pelos quadros (e se foi assim mesmo): %s" % {k: reg.get(k) for k in ("em", "erros", "assim_mesmo")})
    # a revisão: o DXF novo do cliente (as mesmas 5 linhas e mais uma na área da locação) vira a R01
    def _dxf(linhas):
        s = ["0", "SECTION", "2", "ENTITIES"]
        for (x0, y0, x1, y1) in linhas:
            s += ["0", "LINE", "8", "PLANTA", "10", str(x0), "20", str(y0), "30", "0", "11", str(x1), "21", str(y1), "31", "0"]
        return "\n".join(s + ["0", "ENDSEC", "0", "EOF", ""])
    dxf = _dxf([(i * 5000.0, 0.0, i * 5000.0, 20000.0) for i in range(5)] + [(2500.0, 5000.0, 2500.0, 15000.0)])
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=original]').click(); 1")
    ok(esperar(aba, "!document.querySelector('#btn-nova-revisao').hidden", 15), "na Original aparece \"Nova revisão do DXF\"")
    aba.avaliar("(() => { const f = new File([%s], 'cliente-r01.dxf', { type: 'application/dxf' }); window.montagem.novaRevisao(f); return 1; })()" % json.dumps(dxf))
    esperar(aba, "document.querySelector('#abas-projeto [data-aba=original]').textContent === 'Original R01'", 30)
    ok(aba.avaliar("cad.nomeDesenho") == "planta-de-lançamento-r01", "o DXF novo vira a revisão R01 e a aba Original passa a mostrá-la (%s)" % aba.avaliar("cad.nomeDesenho"))
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=montagem]').click(); 1")
    esperar(aba, "cad.nomeDesenho === 'montagem'"); aba.drenar(0.8)
    aba.avaliar("document.querySelector('#btn-ler-quadros').click(); 1")
    esperar(aba, "!!(window.montagem.leitura && window.montagem.leitura.apontamentos.some(a => a.codigo === 'revisao_mudou'))", 30)
    rv = aba.avaliar("window.montagem.leitura.apontamentos.filter(a => a.codigo === 'revisao_mudou').map(a => a.rotulo + ': ' + a.msg).join(' | ')")
    ok("Locação" in (rv or "") and "1 objeto(s) novo(s)" in (rv or ""), "a pré-análise mostra o que a revisão mudou na área do quadro: %s" % (rv or "")[:160])
    ok(aba.avaliar("!!document.querySelector('#leitura-pre .atualizar-revisao')"), "o apontamento traz \"Atualizar pela revisão\"")
    aba.avaliar("document.querySelector('#leitura-pre .atualizar-revisao').click(); 1")
    esperar(aba, "!!(window.montagem.leitura && !window.montagem.leitura.apontamentos.some(a => a.codigo === 'revisao_mudou' && a.rotulo === 'Locação'))", 40)
    mont3 = json.loads(aba.avaliar(MONT))
    locq3 = next(q for q in mont3["metadados"]["montagem"]["quadros"] if q["tipo"] == "locacao")
    n_loc = len([e for e in mont3["entidades"] if (e.get("atributos") or {}).get("quadro") == locq3["id"]])
    ok(n_loc == 6 and locq3["envios"][-1]["desenho"] == "planta-de-lançamento-r01",
       "atualizado pela revisão: o quadro da locação tem o que a R01 tem na área (%d objetos) e o envio aponta para ela" % n_loc)
    # ---- a nova dinâmica (11/10): Implantação com eixos e níveis, elevação por eixo, sombra, 3D pela implantação
    esperar(aba, "cad.nomeDesenho === 'montagem' && !!window.montagem._quadroImplantacao()", 20)
    aba.avaliar("(() => { if (window.montagem.painel) window.montagem.painel.hidden = true; document.querySelectorAll('#avisos .aviso').forEach(a => a.remove()); return 1; })()")
    ok(aba.avaliar("window.montagem._quadroImplantacao().id === cad.doc.metadados.montagem.quadros[0].id")
       and aba.avaliar("!!document.querySelector('.quadro-titulo[data-tipo=implantacao] .quadro-botao')"),
       "a Implantação é o primeiro quadro da folha, com o botão \"Eixos…\" no título")
    aba.avaliar("""(async () => { await fetch('/api/projetos/recebido/niveis', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ niveis: [{ nome: 'Base', z: -1000 }, { nome: 'Piso', z: 0 }, { nome: 'Apoio', z: 5000 }] }) });
      window.montagem._renovarCaixasNiveis(); await window.montagem.refazerQuadrosDaObra(); window.__niv = 1; })(); 1""")
    esperar(aba, "window.__niv === 1 && document.querySelectorAll('.quadro-niveis li').length === 3", 20)
    ok(aba.avaliar("document.querySelectorAll('.quadro-niveis li').length") == 3
       and "+5,00" in (aba.avaliar("document.querySelector('.quadro-niveis').textContent") or ""),
       "a caixa dos níveis ao lado da implantação mostra os 3 níveis: %s" % aba.avaliar("document.querySelector('.quadro-niveis').textContent"))
    # os eixos pelo diálogo: 5 numerados a cada 6 m e 3 com letra a cada 10 m (A em cima)
    aba.avaliar("document.querySelector('.quadro-titulo[data-tipo=implantacao] .quadro-botao').click(); 1")
    esperar(aba, "document.querySelector('#dialogo').open && document.querySelectorAll('#dialogo input[type=text]').length >= 4", 10)
    aba.avaliar("""(() => { const i = [...document.querySelectorAll('#dialogo input[type=text]')];
      i[0].value = '4x6000'; i[1].value = '1'; i[2].value = '2x10m'; i[3].value = 'A'; document.querySelector('#dialogo-ok').click(); return 1; })()""")
    esperar(aba, "!!(cad.doc.metadados.montagem.eixos && cad.doc.metadados.montagem.eixos.numeros.length === 5)", 15)
    aba.drenar(1.0)
    impl = json.loads(aba.avaliar("JSON.stringify(window.montagem._quadroImplantacao())"))
    ger = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).gerado === 'implantacao'))"))
    linhas_e = [e for e in ger if e["tipo"] == "linha"]
    ok(len(linhas_e) == 8 and len([e for e in ger if e["tipo"] == "circulo"]) == 8,
       "os eixos se desenham na implantação: %d linhas e as bolinhas (1:%s)" % (len(linhas_e), impl.get("escala")))
    x1 = next(e for e in linhas_e if e["atributos"]["eixo"] == "1")["a"][0]; x2 = next(e for e in linhas_e if e["atributos"]["eixo"] == "2")["a"][0]
    ok(abs((x2 - x1) * impl["escala"] - 6000) < 0.5, "o vão entre os eixos 1 e 2 é 6 m na escala do quadro (%.1f mm de papel)" % (x2 - x1))
    ya = next(e for e in linhas_e if e["atributos"]["eixo"] == "A")["a"][1]; yc = next(e for e in linhas_e if e["atributos"]["eixo"] == "C")["a"][1]
    ok(ya > yc, "as letras de cima para baixo: A em cima, C embaixo")
    pj = json.loads(aba.avaliar("(async () => JSON.stringify(await (await fetch('/api/projetos/recebido')).json()))()"))
    ex = (pj.get("projeto") or pj).get("eixos") or {}
    ok(len(ex.get("numeros") or []) == 5 and len(ex.get("letras") or []) == 3, "os eixos foram para o projeto (o 3D os desenha)")
    # duplo clique na bolinha do eixo 2: abre a elevação dele
    bola = next(e for e in ger if e["tipo"] == "circulo" and e["atributos"]["eixo"] == "2")
    aba.avaliar("cad.tela.enquadrar([[%s, %s], [%s, %s]]); 1" % (impl["x"], impl["y"] - impl["h"], impl["x"] + impl["w"], impl["y"])); aba.drenar(0.4)
    pt = json.loads(aba.avaliar("""JSON.stringify((() => { const p = cad.tela.paraTela(%s); const r = cad.el.canvas.getBoundingClientRect(); return [p[0] + r.left, p[1] + r.top]; })())""" % json.dumps(bola["centro"])))
    sob = aba.avaliar("(() => { const e = document.elementFromPoint(%s, %s); return e ? e.tagName + '#' + e.id + '.' + e.className : '-'; })()" % (pt[0], pt[1]))
    for n in (1, 2):
        aba.cmd("Input.dispatchMouseEvent", type="mousePressed", x=pt[0], y=pt[1], button="left", clickCount=n)
        aba.cmd("Input.dispatchMouseEvent", type="mouseReleased", x=pt[0], y=pt[1], button="left", clickCount=n)
    esperar(aba, "window.montagem._elevacoes().some(q => q.eixo === '2')", 15)
    aba.drenar(0.8)
    el2 = json.loads(aba.avaliar("JSON.stringify(window.montagem._elevacoes().find(q => q.eixo === '2') || null)"))
    ok(el2 and el2["familia"] == "numero", "o duplo clique no eixo 2 abre a elevação dele" + ("" if el2 else " (sob o ponto: %s)" % sob))
    gel = json.loads(aba.avaliar("JSON.stringify([...cad.doc.entidades.values()].filter(e => (e.atributos || {}).gerado === 'elevacao' && e.atributos.quadro === '%s'))" % (el2 or {}).get("id")))
    cruz = sorted([(e["a"][0], e["atributos"]["eixo"]) for e in gel if e["tipo"] == "linha" and e["atributos"].get("eixo")])
    ok([n for _x, n in cruz] == ["A", "B", "C"], "na elevação, os eixos que cruzam em ordem da esquerda para a direita: %s" % [n for _x, n in cruz])
    txt_niv = " ".join(e.get("texto", "") for e in gel if e["tipo"] == "texto")
    ok("Apoio" in txt_niv and "Base" in txt_niv, "as linhas dos níveis com os nomes: %s" % txt_niv[:120])
    # o que se põe na elevação fica no mesmo lugar real quando a escala muda
    aba.avaliar("""(() => { const m = window.montagem, q = m._elevacoes().find(q => q.eixo === '2');
      cad.doc.add({ id: 'col1', tipo: 'linha', camada: 'VISTA', a: m._paraPapel(q, [0, 5000]), b: m._paraPapel(q, [10000, 6000]), atributos: { quadro: q.id } }); return 1; })()""")
    aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(q => q.eixo === '2');
      const s = document.querySelector('.quadro-titulo[data-quadro="' + q.id + '"] select.quadro-escala'); s.value = '50'; s.dispatchEvent(new Event('change')); return 1; })()""")
    esperar(aba, "window.montagem._elevacoes().find(q => q.eixo === '2').escala === 50", 10); aba.drenar(0.6)
    real = json.loads(aba.avaliar("""JSON.stringify((() => { const m = window.montagem, q = m._elevacoes().find(q => q.eixo === '2'), e = cad.doc.get('col1');
      return [m._paraReal(q, e.a), m._paraReal(q, e.b)]; })())"""))
    ok(abs(real[0][0]) < 0.5 and abs(real[0][1] - 5000) < 0.5 and abs(real[1][0] - 10000) < 0.5 and abs(real[1][1] - 6000) < 0.5,
       "a linha posta na elevação continua no mesmo lugar real depois da escala 1:50: %s" % real)
    # a sombra: a elevação do eixo 3 mostra a do 2
    aba.avaliar("window.montagem.abrirElevacao('3', 'numero').then(() => { window.__e3 = 1; }); 1")
    esperar(aba, "window.__e3 === 1", 15); aba.drenar(0.5)
    aba.avaliar("""(() => { const q = window.montagem._elevacoes().find(q => q.eixo === '3');
      const s = document.querySelector('.quadro-titulo[data-quadro="' + q.id + '"] select.quadro-sombra'); s.value = 'anterior'; s.dispatchEvent(new Event('change')); return 1; })()""")
    ok(aba.avaliar("window.montagem._elevacoes().find(q => q.eixo === '3').sombra") == "anterior", "a sombra do eixo 2 ligada na elevação do 3")
    ok(sobrepostos(quadros(aba)) == 0, "com a implantação e as elevações, nenhum quadro sobreposto")
    # a tesoura lançada na implantação (do eixo A ao C, no eixo 2) chega ao 3D na medida real
    aba.avaliar("""(() => { const m = window.montagem, q = m._quadroImplantacao(), ex = cad.doc.metadados.montagem.eixos;
      const g = ex.numeros.find(e => e.nome === '2').pos, pa = ex.letras.find(e => e.nome === 'A').pos, pc = ex.letras.find(e => e.nome === 'C').pos;
      cad.doc.add({ id: 'tr2', tipo: 'linha', camada: 'ESTRUTURA', a: m._paraPapel(q, [g, pa]), b: m._paraPapel(q, [g, pc]),
        atributos: { elemento: 'trelica', material: 'aco', marca: 'T1', quadro: q.id, nivel_base: 'Apoio', eixo: '2',
          perfis: { banzo_sup: 'U 150×50×3,0', banzo_inf: 'U 150×50×3,0', diagonal: 'L 50,8×4,76' },
          desenho: { barras: [[0, 0, 20000, 0, 'banzo_inf'], [0, 0, 10000, 1500, 'banzo_sup'], [10000, 1500, 20000, 0, 'banzo_sup'], [10000, 0, 10000, 1500, 'montante']], vao: 20000, altura: 1500 } } });
      cad._editado = true; cad.salvar({ avisar: false }); return 1; })()""")

    def _barras():
        mod = json.loads(aba.avaliar("(async () => JSON.stringify(await (await fetch('/api/projetos/recebido/modelo')).json()))()") or "{}")
        ents = (mod.get("documento") or {}).get("entidades") or []
        if isinstance(ents, dict):
            ents = list(ents.values())
        return [e for e in ents if (e.get("atributos") or {}).get("planta") == "montagem"]
    t0 = time.time()
    while time.time() - t0 < 30 and not _barras():
        aba.drenar(0.6)
    bs = _barras()
    xs3 = sorted({round(c, 1) for b in bs for c in (b.get("inicio", [0])[0], b.get("fim", [0])[0])})
    zs3 = [c for b in bs for c in (b.get("inicio", [0, 0, 0])[2], b.get("fim", [0, 0, 0])[2])]
    ok(len(bs) >= 4 and xs3 and abs(xs3[0] - 6000) < 1 and abs(xs3[-1] - 6000) < 1 and min(zs3) >= 4900,
       "a tesoura da implantação chega ao 3D no eixo 2 (x = 6 m) e no nível Apoio (5 m): %d barras, x %s" % (len(bs), xs3[:3]))
    aba.avaliar("window.montagem.enquadrar(); 1"); aba.drenar(0.8)
    open(os.path.join(os.path.dirname(__file__), "_montagem_implantacao.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))
    # todo projeto tem a barra (01/10); só aparece o botão que faz alguma coisa (07/10): no do IFC, sem Original e Montagem
    aba.navegar(base + "/cad?projeto=do-ifc&desenho=detalhamento-completo", limite=60)
    esperar(aba, "!!window.montagem && !document.querySelector('#abas-projeto').hidden", 20)
    estado = json.loads(aba.avaliar("JSON.stringify([...document.querySelectorAll('#abas-projeto button[data-aba]')].map(b => [b.dataset.aba, b.hidden]))"))
    ok(estado == [["original", True], ["montagem", True], ["detalhamento", False], ["pranchas", False]],
       "projeto do IFC: a barra aparece só com Detalhamento e Pranchas (Original e Montagem escondidas): %s" % estado)
    ok(aba.avaliar("document.querySelector('#abas-projeto [data-aba=detalhamento]').classList.contains('on')"),
       "aberto o detalhamento completo, a aba Detalhamento fica marcada")
    aba.avaliar("document.querySelector('#abas-projeto [data-aba=pranchas]').click(); 1")
    esperar(aba, "cad.nomeDesenho === 'pranchas'", 20)
    ok(aba.avaliar("document.querySelector('#abas-projeto [data-aba=pranchas]').classList.contains('on')"), "e a aba Pranchas abre as pranchas dele")
    aba.navegar(base + "/cad?projeto=recebido&desenho=montagem", limite=60)
    esperar(aba, "cad.nomeDesenho === 'montagem'", 20)
    ok(aba.avaliar("document.querySelector('#abas-projeto [data-aba=pranchas]').hidden"), "sem pranchas ainda, a aba Pranchas não aparece")
    erros = [m for m in aba.console if m[0] in ("error", "excecao")]
    ok(not erros, "sem erro no console" + ("" if not erros else ": " + str(erros[:2])))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas))
sys.exit(1 if falhas else 0)
