# -*- coding: utf-8 -*-
"""Abrir o editor 3D com um modelo grande (SESI Chapecó, 03/11: 42,7 mil peças, "Página sem resposta — Aguarde / Sair da
página" ao clicar Editar no modo ver; ~200 s de CPU no navegador, todo em montar o lote: as arestas refeitas peça por peça
em coordenadas de mundo, os perfis fora do catálogo buscados DEPOIS da montagem e as barras refeitas, e cada peça tirada do
lote refazendo o índice e a esfera do bloco).

Dois modelos, como a regra manda (na forma em que o defeito apareceu e na de sempre):
  grande — acima de LIMITE_AOS_POUCOS (6.000): barras com um perfil fora do catálogo básico, chapas com furos e sólidos
           repetidos (cópias), longe da origem como o SESI; é montado em partes.
  medio  — acima de LIMITE_LOTE (1.500) e abaixo de 6.000: em lote, de uma vez (o Posto, o PRATI dos verificadores).
Para cada um:
  A. a página RESPONDE enquanto o modelo grande monta (nenhuma chamada de avaliação espera mais de 2 s), o andamento aparece
     (body[data-montando] e a barra "Montando o modelo na tela") e, no fim, o lote tem todas as peças;
  B. RESULTADO IDÊNTICO: o mesmo modelo montado pelo caminho de antes (arestas refeitas no mundo, de uma vez) dá os mesmos
     blocos, byte a byte (posições, normais, arestas, itens) — sem a correção, o caminho novo nem existe;
  C. os perfis fora do catálogo chegam ANTES da montagem: nenhuma "refazer N peças na tela" depois do "montar o modelo", e
     a barra com esse perfil sai com a seção do servidor (não o retângulo genérico de 100 × 200);
  D. tirar peças do lote (editar) refaz o índice dos blocos UMA vez (`concluir`), não uma por peça;
  E. a seleção feita no meio da montagem fica (cor e contorno) quando o bloco dela entra;
  F. ?render=1 (as fotos dos resumos) só fica pronto com o lote inteiro; sem erros no console.
Sem a correção (git stash dos 4 arquivos): A falha (travada de vários segundos, sem andamento), C falha (refazer 3000),
D falha (3001 conclusões)."""
import json, os, shutil, subprocess, sys, tempfile, time
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre
from nucleo3d.modelo import Documento
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                   # noqa: BLE001
    pass

#: (nome, barras, chapas, sólidos): o grande passa de LIMITE_AOS_POUCOS; o médio fica entre LIMITE_LOTE e ele
SITUACOES = [("grande", 3000, 3000, 3000), ("medio", 700, 700, 500)]
PERFIL_FORA = "U150X50X2.28"          # dobrado de fábrica: não está no banco básico do editor; o servidor dá a seção
X0, Y0, Z0 = 60000, 20000, 6000       # longe da origem, como o SESI


def modelo(nb, nc, ns):
    doc = Documento().dict()
    ents = []
    for i in range(nb):
        x = X0 + (i % 60) * 1500; y = Y0 + (i // 60) * 1500
        perfil = PERFIL_FORA if i % 3 == 0 else "W 150×13,0"
        ents.append({"id": "b%04d" % i, "tipo": "barra", "nome": "terça", "perfil": perfil, "camada": "Estrutura",
                     "inicio": [x, y, Z0], "fim": [x + (300 if i % 2 else 0), y + 1000, Z0 + (i % 5) * 100],
                     "rotacao": (i % 4) * 15, "papel": "viga", "atributos": {}})
    for i in range(nc):
        x = X0 + (i % 60) * 1500 + 700; y = Y0 + (i // 60) * 1500 + 200
        furos = [{"x": 40, "y": 30, "diametro": 14}] if i % 2 else []
        ents.append({"id": "c%04d" % i, "tipo": "chapa", "nome": "Gusset", "camada": "Chapas", "origem": [x, y, Z0 + 100],
                     "eixo_x": [1, 0, 0], "eixo_y": [0, 0, 1], "contorno": [[0, 0], [200 + (i % 7) * 10, 0], [200 + (i % 7) * 10, 120], [0, 120]],
                     "espessura": 6.35 if i % 3 else 9.5, "centrada": True, "furos": furos, "aco": "ASTM A36", "atributos": {}})
    for i in range(ns):
        x = X0 + (i % 60) * 1500 + 300; y = Y0 + (i // 60) * 1500 + 600; z = Z0 - 500
        a = 200 if i % 4 else 350                              # duas formas: a repetida vira cópias (InstancedMesh)
        vs = [[x, y, z], [x + a, y, z], [x + a, y + a, z], [x, y + a, z], [x, y, z + a], [x + a, y, z + a], [x + a, y + a, z + a], [x, y + a, z + a]]
        ents.append({"id": "s%04d" % i, "tipo": "solido", "nome": "bloco", "camada": "Concreto", "vertices": vs,
                     "faces": [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], "atributos": {}})
    doc["entidades"] = ents
    return doc


PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_modelo_grande_")
for nome, nb, nc, ns in SITUACOES:
    pasta = os.path.join(DADOS, nome)
    os.makedirs(pasta)
    json.dump({"formato": 1, "nome": "Modelo " + nome, "tipo": "desenho", "cliente": "", "local": "", "responsavel": "",
               "criado": "2026-11-03T00:00:00", "alterado": "2026-11-03T00:00:00", "dados": None},
              open(os.path.join(pasta, "projeto.json"), "w", encoding="utf-8"))
    json.dump(modelo(nb, nc, ns), open(os.path.join(pasta, "modelo.json"), "w", encoding="utf-8"), ensure_ascii=False)

srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)


chrome = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_grande_")
nav = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--no-first-run", "--remote-allow-origins=*", f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# os blocos do lote, byte a byte: {itens: [[id, nv, na]...] por bloco, soma: hash das posições/normais/arestas}
BLOCOS = """(lote) => {
  let h = 2166136261;
  const mistura = (arr) => { const u = new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength); for (let i = 0; i < u.length; i++) h = Math.imul(h ^ u[i], 16777619); };
  const itens = [];
  for (const b of lote.blocos) {
    itens.push(b.itens.map(it => [it.id, it.nv, it.na, it.chave]));
    mistura(b.malha.geometry.getAttribute('position').array); mistura(b.malha.geometry.getAttribute('normal').array);
    mistura(b.arestas.geometry.getAttribute('position').array);
    mistura(b.malha.geometry.index.array); mistura(b.arestas.geometry.index.array);
  }
  const copias = lote.copias.map(g => [g.itens.map(x => x.ent.id), g.malha.count]);
  return { blocos: lote.blocos.length, itens, copias, hash: h >>> 0, n: lote.tamanho };
}"""

try:
    for _ in range(60):
        alvos = [t for t in _json(f"http://127.0.0.1:{cdp}/json/list") if t.get("type") == "page"]
        if alvos: break
        time.sleep(0.5)
    aba = Aba(alvos[0]["webSocketDebuggerUrl"])
    for dm in ("Page", "Runtime", "Log"): aba.cmd(f"{dm}.enable")
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)

    def jsj(e):
        r = aba.avaliar(f"(() => {{ try {{ return JSON.stringify((() => {{ {e} }})()); }} catch (x) {{ return JSON.stringify({{ erro: String(x && x.stack || x) }}); }} }})()")
        r = json.loads(r) if r else None
        if isinstance(r, dict) and "erro" in r: print("     erro JS:", r["erro"][:400]); return None
        return r

    for nome, nb, nc, ns in SITUACOES:
        total = nb + nc + ns
        print(f"{nome} ({total} peças)")
        aba.console.clear()
        t0 = time.time()
        aba.navegar(f"http://localhost:{PORTA}/editor?projeto={nome}", limite=120)
        # --- A. enquanto monta: a página responde; o andamento aparece
        maior = 0.0; viu_montando = False; viu_barra = False; selecionou = False; viu_pronto = False
        while time.time() - t0 < 240:
            ta = time.time()
            e = jsj("""const ed = window.editor; if (!ed || !ed.documento) return { n: 0 };
              const c = ed.cena, m = c.montando;
              return { n: ed.documento.tamanho, montando: !!m, feitas: m ? m.feitas : 0, lote: c.lote ? c.lote.tamanho : 0,
                       pronto: document.body.dataset.pronto === '1', data: document.body.dataset.montando === '1',
                       barra: !!document.querySelector('.barra-andamento[data-tarefa="editor.montar-na-tela"]'),
                       dica: ed.el.dica.textContent };""")
            resp = time.time() - ta
            if e and e.get("n"): maior = max(maior, resp)
            if e and e.get("montando"):
                viu_montando = True
                if e.get("data") and e.get("barra"): viu_barra = True
                if not selecionou:
                    jsj("editor.selecao.definir(['b0001', 'c0001']); return 1;"); selecionou = True
            if e and e.get("pronto"): viu_pronto = True
            if e and e.get("pronto") and not e.get("montando") and e.get("lote", 0) >= total and resp < 0.5:
                break
            aba.drenar(0.3)
        aba.drenar(1.0)
        e = jsj("""const c = editor.cena; return { lote: c.lote ? c.lote.tamanho : 0, montando: !!c.montando, emLote: c.emLote,
                   objetos: c.objetos.size, data: document.body.dataset.montando === '1', dica: editor.el.dica.textContent };""")
        print(f"     aberto em {time.time() - t0:.1f} s; maior espera de uma avaliação {maior:.2f} s; {e}")
        ok(e and e["emLote"] and e["lote"] == total and e["objetos"] == total, f"o lote tem as {total} peças ({e})")
        if nome == "grande":
            ok(viu_montando and viu_barra, f"o modelo grande é montado em partes, com body[data-montando] e a barra de andamento (montando {viu_montando}, barra {viu_barra})")
            ok(maior < 2.0, f"a página responde enquanto monta: a maior espera foi {maior:.2f} s (< 2 s)")
            ok(e and not e["data"] and "montado" in (e["dica"] or "").lower(), f"no fim, sem data-montando e a dica diz que montou ({e and e['dica']!r})")
        else:
            ok(not viu_montando, "o modelo médio é montado de uma vez (não em partes)")
        # --- E. a seleção feita no meio da montagem ficou
        if selecionou:
            s = jsj("""const l = editor.cena.lote; return { estado: [l.estado.get('b0001'), l.estado.get('c0001')], contornos: [l.contornos.has('b0001'), l.contornos.has('c0001')],
                       sel: [...editor.selecao.ids] };""")
            ok(s and s["estado"] == ["selecionado", "selecionado"] and all(s["contornos"]), f"a seleção feita no meio da montagem fica, com cor e contorno ({s})")
            jsj("editor.selecao.limpar(); return 1;")
        # --- C. os perfis fora do catálogo chegaram antes da montagem
        p = jsj("""const pes = (window.__pesados || []).map(x => x.nome);
          const iMontar = pes.lastIndexOf('montar o modelo na tela');
          const refeitas = pes.slice(iMontar + 1).filter(n => /^refazer /.test(n));
          const it = editor.cena.lote.itens.get('b0000');
          return { pes, refeitas, perfil: !!editor.cena.perfil(%s), nv: it ? it.nv : 0, chave: it ? it.chave : null };""" % json.dumps(PERFIL_FORA))
        ok(p and not p["refeitas"], f"nenhuma peça refeita depois de montar (os perfis vieram antes): {p and p['refeitas']}")
        ok(p and p["perfil"] and p["nv"] > 36 and PERFIL_FORA in (p["chave"] or ""), f"a barra com o perfil fora do catálogo tem a seção do servidor ({p and (p['nv'], p['chave'])})")
        # --- B. resultado idêntico ao caminho de antes (arestas refeitas no mundo, de uma vez)
        r = jsj("""const c = editor.cena; const Lote = c.lote.constructor;
          const novo = (%s)(c.lote);
          Lote.arestasDoCache = false;
          const l2 = new Lote(c);
          try {
            const ents = [...c.documento.entidades.values()].filter(e => Lote.aceita(e));
            l2.definirVarios(ents);
            const antigo = (%s)(l2);
            return { novo, antigo, iguais: JSON.stringify(novo) === JSON.stringify(antigo) };
          } finally { l2.descartar(); Lote.arestasDoCache = true; }""" % (BLOCOS, BLOCOS))
        ok(r and r["iguais"], f"os blocos são iguais, byte a byte, aos do caminho de antes ({r and (r['novo']['blocos'], r['novo']['hash'], r['antigo']['hash'])})")
        if r and not r["iguais"]:
            dif = [(a, b) for a, b in zip(r["novo"]["itens"], r["antigo"]["itens"]) if a != b][:2]
            print("     diferenças:", r["novo"]["blocos"], r["antigo"]["blocos"], r["novo"]["copias"] == r["antigo"]["copias"], dif)
        # --- D. tirar peças do lote refaz o índice uma vez só
        d = jsj("""const c = editor.cena, l = c.lote; let n = 0; const orig = l.concluir.bind(l); l.concluir = () => { n++; return orig(); };
          const ids = [...l.itens.keys()].slice(0, 1000);
          const antes = l.tamanho;
          try { c.atualizar(ids); } finally { l.concluir = orig; }
          let coerente = true;
          for (const b of l.blocos) { let nv = 0; for (const it of b.itens) if (!l.escondidos.has(it.id)) nv += it.nv; if (b.malha.geometry.index.count !== nv) coerente = false; }
          return { n, antes, depois: l.tamanho, coerente };""")
        ok(d and d["n"] == 1 and d["antes"] == d["depois"] == total and d["coerente"], f"refazer 1000 peças concluiu os blocos 1 vez (foi {d and d['n']}), o lote segue com {d and d['depois']} e os índices batem")
        erros = [m for m in aba.console if m[0] in ("error", "excecao") and "Failed to load resource" not in m[1]]
        ok(not erros, f"sem erros no console: {[x[1][:200] for x in erros[:2]]}")
        aba.avaliar("(async () => { try { await editor.gravarConfirmado(); } catch (e) {} return 1; })()")

    # --- F. as fotos (?render=1) esperam o lote inteiro
    print("fotos (?render=1) do grande")
    t0 = time.time()
    aba.navegar(f"http://localhost:{PORTA}/editor?projeto=grande&render=1", limite=120)
    while time.time() - t0 < 240 and not aba.avaliar("window.__renderPronto === true"): aba.drenar(0.5)
    f = jsj("return { pronto: window.__renderPronto === true, montando: !!editor.cena.montando, lote: editor.cena.lote.tamanho };")
    ok(f and f["pronto"] and not f["montando"] and f["lote"] == sum(SITUACOES[0][1:]), f"o render fica pronto só com o lote inteiro ({f}, {time.time() - t0:.0f} s)")
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
    time.sleep(1)
    shutil.rmtree(DADOS, ignore_errors=True)
    shutil.rmtree(perfil, ignore_errors=True)
print("\nFALHAS:", len(falhas))
sys.exit(1 if falhas else 0)
