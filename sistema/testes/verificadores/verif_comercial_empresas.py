# -*- coding: utf-8 -*-
"""Várias empresas na tela Comercial (27/10/2026: "poder escolher no momento de gerar a proposta para qual empresa
vai ser"; a DEZN Construtora com o desenho compacto aprovado no piloto C). Com eventos de verdade:

  1. a aba Proposta mostra o seletor "Empresa" (a principal e a DEZN); trocar para a DEZN grava, dá o número da
     sequência dela (DZ-AAAA-NNN) e mostra os campos do compacto (título, destaques);
  2. "Gerar a proposta (PDF)" ganha a barra de andamento com o rótulo e sai o PDF da DEZN, em 2 páginas, sem
     nada da principal;
  3. a aba Empresa mostra a empresa da proposta (a DEZN), com o desenho do PDF e o prefixo.
Porta livre, nunca a 8765/8766; dados numa pasta temporária."""
import json, os, subprocess, sys, tempfile, time
from datetime import date
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, "testes"))
from verificar_editor import Aba, CHROMES, _json, _porta_livre

PORTA = _porta_livre()
DADOS = tempfile.mkdtemp(prefix="metalica_empresas_")
os.makedirs(os.path.join(DADOS, "obra"))
json.dump({"formato": 1, "nome": "WE Coqueiral", "cliente": "Coqueiral Residence", "local": "Cascavel - PR", "tipo": "desenho",
           "alterado": "2026-10-27T00:00:00"}, open(os.path.join(DADOS, "obra", "projeto.json"), "w", encoding="utf-8"))
os.makedirs(os.path.join(DADOS, "fabrica", "empresas", "dezn", "marca"))
json.dump({"razao_social": "Metalúrgica Principal Ltda.", "cnpj": "00.000.000/0001-00"},
          open(os.path.join(DADOS, "fabrica", "empresa.json"), "w", encoding="utf-8"))
json.dump({"nome_comercial": "DEZN Construtora", "layout": "compacto", "prefixo_numero": "DZ",
           "cores": {"primaria": "#22346E", "destaque": "#800080", "apoio": "#7F9FFF"}},
          open(os.path.join(DADOS, "fabrica", "empresas", "dezn", "empresa.json"), "w", encoding="utf-8"))
open(os.path.join(DADOS, "fabrica", "empresas", "dezn", "marca", "logo_claro.svg"), "w", encoding="utf-8").write(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 4"><text x="0" y="3" font-size="3" fill="#fff">DEZN</text></svg>')
env = dict(os.environ, METALICA_COMERCIAL="1")
srv = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py"), "--sem-navegador", "--porta", str(PORTA), "--dados", DADOS],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
base = f"http://localhost:{PORTA}"
falhas = []


def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m, flush=True)
    if not c:
        falhas.append(m)


def esperar(aba, expr, limite=40):
    t0 = time.time()
    while time.time() - t0 < limite:
        try:
            if aba.avaliar(expr): return True
        except Exception: pass
        aba.drenar(0.2)
    return False


ESTADO = "fetch('/api/projetos/obra/comercial').then(r => r.json()).then(j => { window.__S = j; return 1; })"
ABA = "(n => { const b = [...document.querySelectorAll('#abas button')].find(x => x.textContent.trim() === n); if (b) b.click(); return !!b; })(%r)"
SELETOR = """(() => { const l = [...document.querySelectorAll('label')].find(x => x.firstChild && x.firstChild.textContent === 'Empresa');
  const s = l && l.querySelector('select'); return s ? [...s.options].map(o => o.value).join(',') : ''; })()"""
TROCAR = """(() => { const l = [...document.querySelectorAll('label')].find(x => x.firstChild && x.firstChild.textContent === 'Empresa');
  const s = l.querySelector('select'); s.value = 'dezn'; s.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()"""
ROTULOS = "[...document.querySelectorAll('label')].map(l => l.firstChild && l.firstChild.textContent).filter(Boolean).join('|')"

exe = next(c for c in CHROMES if os.path.exists(c)); cdp = _porta_livre(); perfil = tempfile.mkdtemp(prefix="verif_empresas_")
nav = subprocess.Popen([exe, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                        f"--user-data-dir={perfil}", f"--remote-debugging-port={cdp}", "about:blank"],
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
    aba.cmd("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    aba.navegar(base + "/comercial?projeto=obra#proposta", limite=60)
    ok(esperar(aba, "!!document.querySelector('#abas button') && !!window.__metalicaVigiaChamadas"), "a tela Comercial abriu (com a vigilância das chamadas)")
    aba.avaliar(ABA % "Proposta"); aba.drenar(0.5)

    # 1. o seletor e a troca
    ok(aba.avaliar(SELETOR) == "principal,dezn", f"o seletor Empresa tem a principal e a DEZN ({aba.avaliar(SELETOR)!r})")
    ok("Título (compacto)" not in aba.avaliar(ROTULOS), "com a principal (clássico), sem os campos do compacto")
    aba.avaliar(TROCAR)
    ano = date.today().year
    ok(esperar(aba, "(%s, window.__S && window.__S.proposta.numero === 'DZ-%d-001')" % (ESTADO, ano), 20),
       "trocar para a DEZN grava a proposta com o número da sequência dela (DZ-%d-001)" % ano)
    ok(esperar(aba, "document.querySelector('#obra-sub').textContent.includes('DZ-%d-001')" % ano, 10), "o número novo aparece na tela")
    ok("Título (compacto)" in aba.avaliar(ROTULOS), "com a DEZN aparecem o título e os destaques do compacto")

    # 2. gerar o PDF: a barra de andamento e o arquivo
    aba.avaliar("localStorage.clear(); window.__barra = ''; window.__obs = setInterval(() => { const b = document.querySelector('.barra-andamento');"
                " if (b && !window.__barra) window.__barra = b.title || b.textContent; }, 50); 1")
    aba.avaliar("[...document.querySelectorAll('button')].find(b => b.textContent.startsWith('Gerar a proposta')).click(); 1")
    ok(esperar(aba, "!!document.querySelector('.aviso a, #aviso a') || [...document.querySelectorAll('a')].some(a => a.textContent === 'Abrir PDF')", 90),
       "o PDF ficou pronto (link Abrir PDF)")
    barra = aba.avaliar("window.__barra")
    ok("Gerando a proposta" in (barra or ""), f"a geração ganhou a barra de andamento com o rótulo ({barra!r})")
    pasta = os.path.join(DADOS, "obra", "comercial")
    pdfs = [n for n in os.listdir(pasta) if n.endswith(".pdf")] if os.path.isdir(pasta) else []
    ok(len(pdfs) == 1 and pdfs[0].startswith("Proposta_DZ-%d-001_R00" % ano), f"o PDF da DEZN foi gravado ({pdfs})")
    if pdfs:
        import pymupdf
        doc = pymupdf.open(os.path.join(pasta, pdfs[0]))
        txt = "".join(p.get_text() for p in doc)
        # (o rodapé "DEZN CONSTRUTORA" é margem de página do Chrome: sai no PDF, mas não como texto extraível)
        ok("DEZN Construtora" in txt and "Metalúrgica Principal" not in txt, "o PDF é da DEZN (assinatura) e não traz a principal")
        ok(len(doc) <= 2, f"a proposta compacta sem conteúdo extra fica em até 2 páginas ({len(doc)})")

    # 3. a aba Empresa é a da proposta
    aba.avaliar(ABA % "Empresa"); aba.drenar(0.5)
    rot = aba.avaliar(ROTULOS)
    ok("Desenho do PDF" in rot and "Prefixo do número" in rot, "a aba Empresa mostra o desenho do PDF e o prefixo da DEZN")
    ok(esperar(aba, "[...document.querySelectorAll('button')].some(b => b.textContent.includes('DEZN Construtora'))", 5),
       "o botão de gravar é o da DEZN")
    e = [m for m in aba.console if m[0] in ("error", "excecao") and "favicon" not in m[1]]
    ok(not e, "sem erros no console" + (f" — {[x[1][:160] for x in e[:3]]}" if e else ""))
finally:
    try: nav.kill()
    except Exception: pass
    srv.kill()
print("FALHAS: %d" % len(falhas) if falhas else "TUDO CERTO")
sys.exit(1 if falhas else 0)
