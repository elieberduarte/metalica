# -*- coding: utf-8 -*-
"""A tela Controle de produção (12/11/2026), com eventos de verdade. Até 12/11 era a aba Controle da lista de materiais;
o usuário não a achou e pediu no menu Produção do topo: agora é a tela /controle-producao.

Servidor de teste com --dev (o controle é extensão do desenvolvimento) e uma obra com a lista da obra de teste do
pytest (tesoura T38 ×2, T74, MT71 em duas marcas, terças T.C.1 ×46, contraventos CV.2 ×6, chapas):
  1. a lista de materiais não tem mais a aba; o clique em "Produção" no topo abre a lista das telas (Lista de materiais,
     Controle de produção) e "Controle de produção" leva à tela, com a Produção acesa;
  2. os cartões começam em 0 % e a lista tem T38-1, T38-2, T74, MT71-1..3 e T.C.1 (46);
  3. "Apontar" na T.C.1, etapa Pintura, 30 → a linha mostra "30 de 46" e o registro fica em producao/apontamentos.jsonl;
  4. 17 a mais é recusado no próprio diálogo ("só faltam 16"), sem gravar;
  5. T38-1 na Produção (quantidade 1) → ✓ e o cartão da Produção sai do 0 %;
  6. o filtro "Falta na produção" esconde a T38-1; a busca "T.C" deixa só a T.C.1;
  7. "Estornar" desfaz a pintura (a linha volta a "—") e o histórico mostra o original riscado;
  8. sem erro no console.
Se o Posto V2 estiver nesta máquina, a tela também abre com a lista dele (os itens que producao.controle.itens dá para a lista dele).
Porta livre, nunca a 8765/8766."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from test_producao_controle import _lista, NOMES, POSTO

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_controle_")


def _obra(slug, nome, lista, nomes):
    pasta = os.path.join(DADOS, slug)
    os.makedirs(os.path.join(pasta, "detalhamento"))
    json.dump({"formato": 1, "nome": nome, "tipo": "ifc", "alterado": "2026-11-12T08:00:00"},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
    json.dump(lista, open(os.path.join(pasta, "detalhamento", "lista-de-materiais.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(nomes, open(os.path.join(pasta, "detalhamento", "nomes.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return pasta


OBRA = _obra("obra-controle", "OBRA DO CONTROLE", _lista(), NOMES)
TEM_POSTO = os.path.exists(os.path.join(POSTO, "detalhamento", "lista-de-materiais.json"))
if TEM_POSTO:
    _lista_posto = json.load(open(os.path.join(POSTO, "detalhamento", "lista-de-materiais.json"), encoding="utf-8"))
    _nomes_posto = json.load(open(os.path.join(POSTO, "detalhamento", "nomes.json"), encoding="utf-8"))
    _obra("posto-copia", "POSTO (CÓPIA)", _lista_posto, _nomes_posto)
    # os itens que a tela tem de mostrar: a conta do controle sobre a mesma lista (702 em 09/11; 648 desde os nomes do
    # projetista de 12/11, com as meias unidades juntas — 5315b80, d9b0365)
    sys.path.insert(0, BASE)
    from producao import controle as _C
    N_POSTO = len(_C.itens(_lista_posto, _nomes_posto))

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--dev", "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://localhost:{PORTA}"
falhas = []
try: sys.stdout.reconfigure(errors="replace")
except Exception: pass


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


def clicar(aba, seletor):
    r = aba.avaliar(f"(() => {{ const e = document.querySelector({json.dumps(seletor)}); if (!e) return null; e.scrollIntoView({{block: 'center'}});"
                    f" const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; }})()")
    if not r: return False
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=r[0], y=r[1], button="left", clickCount=1)
    return True


def digitar(aba, seletor, texto):
    """foco no campo, seleciona tudo e digita (teclado de verdade)"""
    clicar(aba, seletor)
    aba.avaliar(f"document.querySelector({json.dumps(seletor)}).select()")
    aba.cmd("Input.insertText", text=texto)


def celula(item, coluna):
    """o texto da célula da coluna (pelo título) na linha do item"""
    return (f"(() => {{ const t = document.querySelector('#controle-corpo table'); if (!t) return null;"
            f" const i = [...t.tHead.rows[0].cells].findIndex(c => c.textContent.trim().startsWith({json.dumps(coluna)}));"
            f" const tr = [...t.tBodies[0].rows].find(r => r.dataset.item === {json.dumps(item)});"
            f" return tr ? tr.cells[i].textContent.trim() : null; }})()")


def apontar(aba, item, etapa=None, qtd=None):
    clicar(aba, f"#controle-corpo button[data-item={json.dumps(item)}]")
    if not esperar(aba, "!!document.querySelector('#ctl-dialogo[open]')", 10): return False
    if etapa:
        clicar(aba, f"#ctl-dialogo input[name=ctl-etapa][value={etapa}]")
    if qtd is not None:
        digitar(aba, "#ctl-qtd", str(qtd))
    clicar(aba, "#ctl-confirmar")
    return True


exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_controle_")
nav = subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)

    # 1. o menu Produção do topo
    aba.navegar(base + "/materiais?projeto=obra-controle#geral", limite=40)
    ok(esperar(aba, "!!document.querySelector('.be-aba[data-etapa=producao]') && !!document.querySelector('#abas button[data-aba]')", 40),
       "a lista de materiais abre com a barra de cima")
    ok(not aba.avaliar("!!document.querySelector('#abas button[data-aba=controle]')"), "a lista não tem mais a aba Controle")
    clicar(aba, ".be-aba[data-etapa=producao]")
    ok(esperar(aba, "!!document.querySelector('.be-lista')", 10), "o clique em Produção abre a lista das telas")
    telas = aba.avaliar("[...document.querySelectorAll('.be-lista .be-it')].map(b => b.firstChild.textContent.trim())") or []
    ok(telas == ["Lista de materiais", "Controle de produção"], f"Lista de materiais e Controle de produção ({telas})")
    ok(aba.avaliar("location.pathname") == "/materiais", "abrir a lista não sai da tela")
    clicar(aba, ".be-lista .be-it:nth-child(2)")
    ok(esperar(aba, "location.pathname === '/controle-producao' && !!document.querySelector('#ctl-cartoes')", 30),
       "Controle de produção leva à tela, com os cartões")
    ok(esperar(aba, "!!document.querySelector('.be-aba.ativa[data-etapa=producao]')", 10), "na tela do controle a Produção fica acesa no topo")
    ok(aba.avaliar("document.querySelector('#obra-nome').textContent") == "OBRA DO CONTROLE", "o nome do projeto no título, não o da lista (\"Obra de teste\") — 12/11 Posto renomeado")
    ok("/materiais?projeto=obra-controle" in (aba.avaliar("document.querySelector('#btn-lista').href") or ""), "o botão Lista de materiais leva à lista da obra")

    # 2. o começo
    cartoes = aba.avaliar("[...document.querySelectorAll('#ctl-cartoes .cartao-n[data-etapa] b')].map(b => b.textContent)") or []
    ok(cartoes == ["0,0 %", "0,0 %"], f"Produção e Pintura começam em 0 % ({cartoes})")
    ids = aba.avaliar("[...document.querySelectorAll('#controle-corpo table tbody tr[data-item]')].map(r => r.dataset.item)") or []
    ok({"T38-1", "T38-2", "T74", "MT71-1", "MT71-3", "T.C.1", "CV.2"} <= set(ids) and "T38" not in ids,
       f"itens numerados (T38-1, T38-2, T74, MT71-1..3) e peças pela posição ({len(ids)} linhas)")
    ok(aba.avaliar(celula("T.C.1", "Qtd")) == "46", "T.C.1 com 46 peças")

    # 3. apontar 30 terças na pintura
    ok(apontar(aba, "T.C.1", "pintura", 30), "o diálogo de apontar abre pela linha da T.C.1")
    ok(esperar(aba, "!document.querySelector('#ctl-dialogo')", 15), "o diálogo fecha depois de apontar")
    ok(esperar(aba, celula("T.C.1", "Pintura") + " === '30 de 46'", 15), f"a linha mostra 30 de 46 na pintura ({aba.avaliar(celula('T.C.1', 'Pintura'))})")
    arq = os.path.join(OBRA, "producao", "apontamentos.jsonl")
    evs = [json.loads(l) for l in open(arq, encoding="utf-8")] if os.path.exists(arq) else []
    ok(len(evs) == 1 and evs[0]["item"] == "T.C.1" and evs[0]["etapa"] == "pintura" and evs[0]["quantidade"] == 30 and evs[0]["quem"],
       "o apontamento ficou no projeto (producao/apontamentos.jsonl), com quem apontou")

    # 4. a mais é recusado no diálogo
    apontar(aba, "T.C.1", "pintura", 17)
    ok(esperar(aba, "(() => { const e = document.querySelector('#ctl-dialogo .erro'); return e && !e.hidden && /só faltam 16/.test(e.textContent); })()", 10),
       "17 a mais é recusado no diálogo (só faltam 16)")
    clicar(aba, "#ctl-dialogo .acoes button[type=button]")
    esperar(aba, "!document.querySelector('#ctl-dialogo')", 5)
    ok(len(open(arq, encoding="utf-8").read().strip().splitlines()) == 1, "nada gravado com o pedido recusado")

    # 5. uma tesoura na produção
    apontar(aba, "T38-1")
    ok(esperar(aba, celula("T38-1", "Produção") + " === '✓'", 15), "T38-1 produzida (✓)")
    prod = aba.avaliar("document.querySelector('#ctl-cartoes .cartao-n[data-etapa=producao] b').textContent")
    ok(prod not in (None, "0,0 %"), f"o cartão da Produção sai do 0 % ({prod})")

    # 6. filtros
    aba.avaliar("(() => { const s = document.querySelector('#ctl-filtro-etapa'); s.value = 'producao'; s.dispatchEvent(new Event('change')); })()")
    ok(esperar(aba, celula("T38-1", "Item") + " === null && " + celula("T38-2", "Item") + " === 'T38-2'", 10),
       "'Falta na produção' esconde a T38-1 e mostra a T38-2")
    aba.avaliar("(() => { const s = document.querySelector('#ctl-filtro-etapa'); s.value = ''; s.dispatchEvent(new Event('change')); })()")
    digitar(aba, "#filtro", "t.c")
    visiveis = aba.avaliar("[...document.querySelectorAll('#controle-corpo tbody tr[data-filtro]:not(.oculta)')].map(r => r.dataset.item)") or []
    ok(visiveis == ["T.C.1"], f"a busca 'T.C' deixa só a T.C.1 ({visiveis})")
    digitar(aba, "#filtro", "")
    aba.avaliar("document.querySelector('#filtro').dispatchEvent(new Event('input'))")

    # 7. estorno
    aba.avaliar("window.confirm = () => true")
    ev_id = evs[0]["id"] if evs else ""
    clicar(aba, f"#controle-corpo tr[data-evento='{ev_id}'] button")
    ok(esperar(aba, celula("T.C.1", "Pintura") + " === '—'", 15), "o estorno desfaz a pintura da T.C.1")
    ok(esperar(aba, f"(() => {{ const tr = document.querySelector(\"#controle-corpo tr[data-evento='{ev_id}']\"); return tr && tr.classList.contains('ctl-estornado'); }})()", 5),
       "o apontamento original continua no histórico, riscado")
    linhas = open(arq, encoding="utf-8").read().strip().splitlines()
    ok(len(linhas) == 3 and json.loads(linhas[-1]).get("estorno_de") == ev_id, "o estorno é mais uma linha; nada apagado")

    # 7b. apontar vários de uma vez (13/11): a busca "MT71" e a caixinha de todos escolhe as 3; Ctrl+clique na linha soma a CV.2
    digitar(aba, "#filtro", "mt71")
    aba.avaliar("document.querySelector('#filtro').dispatchEvent(new Event('input'))")
    clicar(aba, "#ctl-marcar-todos")
    ok(esperar(aba, "(() => { const f = document.querySelector('#ctl-varios'); return f && !f.hidden && /3 itens escolhidos/.test(f.textContent); })()", 10),
       "a caixinha de cima escolhe os 3 MT71 à vista e a faixa diz '3 itens escolhidos'")
    digitar(aba, "#filtro", "")
    aba.avaliar("document.querySelector('#filtro').dispatchEvent(new Event('input'))")
    ok(esperar(aba, "document.querySelector('#ctl-marcar-todos').indeterminate", 5), "sem a busca, a caixinha de cima fica pela metade")
    r = aba.avaliar("(() => { const tr = document.querySelector('#controle-corpo tr[data-item=\"CV.2\"] td:nth-child(3)'); tr.scrollIntoView({block: 'center'});"
                    " const b = tr.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()")
    for t in ("mousePressed", "mouseReleased"):
        aba.cmd("Input.dispatchMouseEvent", type=t, x=r[0], y=r[1], button="left", clickCount=1, modifiers=2)   # Ctrl
    ok(esperar(aba, "/4 itens escolhidos/.test(document.querySelector('#ctl-varios').textContent)"
                    " && document.querySelector('input.ctl-marcar[data-item=\"CV.2\"]').checked", 5),
       "Ctrl+clique na linha da CV.2 soma à escolha (4 itens)")
    clicar(aba, "#ctl-apontar-varios")
    ok(esperar(aba, "!!document.querySelector('#ctl-dialogo-varios[open]')", 10), "Apontar os escolhidos abre a janela de vários")
    clicar(aba, "#ctl-dialogo-varios input[name=ctl-etapa][value=producao]")
    res = aba.avaliar("document.querySelector('#ctl-varios-resumo').textContent") or ""
    ok("4 item(ns), 9 peça(s)/unidade(s)" in res, f"a janela diz o que vai: 4 itens, 3 MT71 + 6 CV.2 ({res[:90]})")
    digitar(aba, "#ctl-dialogo-varios #ctl-obs", "lote MT71")
    clicar(aba, "#ctl-dialogo-varios #ctl-confirmar")
    ok(esperar(aba, "!document.querySelector('#ctl-dialogo-varios')", 15), "a janela fecha depois de apontar")
    ok(esperar(aba, " && ".join(celula(i, "Produção") + " === '✓'" for i in ("MT71-1", "MT71-2", "MT71-3"))
               + " && " + celula("CV.2", "Produção") + " === '✓ 6'", 15),
       "MT71-1..3 e CV.2 (6) produzidos de uma vez")
    ok(esperar(aba, "document.querySelector('#ctl-varios').hidden && !document.querySelector('input.ctl-marcar:checked')", 5),
       "a escolha se limpa depois de apontar")
    novos = [json.loads(l) for l in open(arq, encoding="utf-8").read().strip().splitlines()][3:]
    ok(sorted((e["item"], e["quantidade"]) for e in novos) == [("CV.2", 6), ("MT71-1", 1), ("MT71-2", 1), ("MT71-3", 1)]
       and all(e["obs"] == "lote MT71" and e["etapa"] == "producao" for e in novos),
       f"um apontamento por item, com a observação em todos ({[(e['item'], e['quantidade']) for e in novos]})")

    # recarregar abre a mesma tela, com o histórico
    aba.navegar(base + "/controle-producao?projeto=obra-controle", limite=40)
    ok(esperar(aba, f"!!document.querySelector('#ctl-cartoes') && !!document.querySelector(\"#controle-corpo tr[data-evento='{ev_id}']\")", 30),
       "recarregar abre a tela do controle com o histórico")
    ok(esperar(aba, "document.querySelector('#painel3d').hidden && document.querySelector('#btn-3d').disabled && !document.querySelector('#p3-quadro')", 10),
       "obra sem modelo 3D: o painel do 3D não aparece, o botão fica desligado e o 3D nem é pedido")
    open(os.path.join(AQUI, "_controle_producao.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    # o detalhamento muda o nome (13/11: o número pela ordem dos eixos trocou 35 nomes no Posto): T38 passa a T39 na lista;
    # o apontamento da T38-1 segue a marca para a T39-1, a tela avisa e o histórico diz o nome de antes — nada apagado
    arq_lista = os.path.join(OBRA, "detalhamento", "lista-de-materiais.json")
    _l = json.load(open(arq_lista, encoding="utf-8"))
    for c in _l["conjuntos"]:
        if c.get("nome") == "T38":
            c["nome"] = "T39"
    json.dump(_l, open(arq_lista, "w", encoding="utf-8"), ensure_ascii=False)
    aba.navegar(base + "/controle-producao?projeto=obra-controle", limite=40)
    ok(esperar(aba, "!!document.querySelector('#ctl-seguiram')", 30), "o aviso de que o apontamento seguiu a peça aparece")
    aviso_seg = aba.avaliar("document.querySelector('#ctl-seguiram').textContent") or ""
    ok("T38-1 → T39-1" in aviso_seg, f"o aviso diz T38-1 → T39-1 ({aviso_seg[:90]})")
    ok(aba.avaliar(celula("T39-1", "Produção")) == "✓", "a T39-1 continua produzida")
    ok(not aba.avaliar("[...document.querySelectorAll('.aviso-topo')].some(a => a.textContent.includes('não estão mais na lista'))"),
       "nada fica 'fora da lista'")
    ok(aba.avaliar("[...document.querySelectorAll('#controle-corpo tr[data-evento] td')].some(t => t.textContent === 'T39-1 (era T38-1)')"),
       "o histórico mostra 'T39-1 (era T38-1)'")
    linhas_ap = open(arq, encoding="utf-8").read()
    ok('"item": "T38-1"' in linhas_ap and "T39-1" not in linhas_ap, "o arquivo de apontamentos não foi reescrito")

    if TEM_POSTO:
        aba.navegar(base + "/controle-producao?projeto=posto-copia", limite=60)
        ok(esperar(aba, "!!document.querySelector('#ctl-cartoes')", 60), "a cópia do Posto V2 abre no controle de produção")
        n = aba.avaliar("document.querySelectorAll('#controle-corpo .rolagem table tbody tr').length")
        ok(n == N_POSTO, f"Posto: {N_POSTO} itens ({n})")
        open(os.path.join(AQUI, "_controle_producao_posto.png"), "wb").write(base64.b64decode(aba.cmd("Page.captureScreenshot", format="png")["data"]))

    # o 400 do pedido de 17 a mais (passo 4) é o esperado
    erros = [c for c in aba.console if c[0] in ("error", "excecao") and not ("400" in c[1] and "/api/producao/apontar" in c[1])]
    ok(not erros, f"sem erro no console ({erros[:3]})")
finally:
    nav.terminate(); srv.terminate()
    try: nav.wait(10); srv.wait(10)
    except Exception: pass
    shutil.rmtree(DADOS, ignore_errors=True); shutil.rmtree(perfil, ignore_errors=True)

print("\n%d falha(s)" % len(falhas) if falhas else "\ntudo ok")
sys.exit(1 if falhas else 0)
