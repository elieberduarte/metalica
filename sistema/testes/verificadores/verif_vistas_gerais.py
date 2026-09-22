# -*- coding: utf-8 -*-
"""Vistas gerais do modelo inteiro num pedido só + gravações simultâneas no mesmo desenho."""
import json, os, shutil, sys, tempfile, threading, time, urllib.request
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE)
import app, projetos

DADOS = tempfile.mkdtemp(prefix="metalica_vg_")
os.makedirs(os.path.join(DADOS, "compressores"))
shutil.copy(os.path.join(BASE, "projetos", "modelos", "compressores-ar.modelo.json"), os.path.join(DADOS, "compressores", "modelo.json"))
json.dump({"formato": 1, "nome": "Compressores", "tipo": "ifc", "cliente": "", "local": "", "responsavel": "",
           "criado": "2026-09-21T00:00:00", "alterado": "2026-09-21T00:00:00", "dados": None, "origem_ifc": "x.ifc"},
          open(os.path.join(DADOS, "compressores", "projeto.json"), "w", encoding="utf-8"))
app.PROJETOS = DADOS
falhas = []
def ok(c, m):
    print(("  ok    " if c else "  FALHA ") + m)
    if not c: falhas.append(m)

# 1) três vistas do modelo inteiro num pedido só
t0 = time.time()
r = app.gerar_vista_2d("compressores", {"vistas": [{"padrao": k, "entidades": None, "rotular": False} for k in ("frente", "topo", "esquerda")], "desenho": "Vistas gerais"})
dt = time.time() - t0
arq = os.path.join(DADOS, "compressores", "desenhos-2d", "vistas-gerais.desenho.json")
ok(len(r["vistas"]) == 3 and r["nome"] == "vistas-gerais", "3 vistas geradas em %.1f s: %s" % (dt, [(v["tipo"], v["pecas_projetadas"]) for v in r["vistas"]]))
d = json.load(open(arq, encoding="utf-8"))
ok(len(d["vistas"]) == 3, "desenho gravado com as 3 vistas, %d entidades, %.1f MB" % (len(d["entidades"]), os.path.getsize(arq) / 1e6))
cantos = [v["canto"][0] for v in d["vistas"]]
ok(cantos == sorted(cantos) and len(set(cantos)) == 3, "vistas lado a lado: cantos x = %s" % [round(c) for c in cantos])
ok(not any(f.endswith(".parcial") for f in os.listdir(os.path.dirname(arq))), "nenhum .parcial sobrando")
# precisão: todas as coordenadas com no máximo 2 casas
amostra = [e for e in d["entidades"] if e["tipo"] == "polilinha"][:50]
ok(all(round(x, 2) == x for e in amostra for p in e["vertices"] for x in p), "coordenadas em centésimo de milímetro")

# 2) gravações simultâneas do mesmo desenho (autosave do CAD + vista nova) não emendam o arquivo
g = projetos.Projetos(DADOS)
grande = {"formato": 1, "nome": "x", "escala": 20, "camadas": [], "vistas": [], "metadados": {},
          "entidades": [{"tipo": "linha", "camada": "VISTA", "a": [i, 0], "b": [i, 1000]} for i in range(200000)]}
pequeno = dict(grande, entidades=grande["entidades"][:1000])
erros = []
def grava(dados):
    try:
        for _ in range(3):
            g.salvar_desenho("compressores", "concorrente", dados)
    except Exception as e:
        erros.append(repr(e))
ts = [threading.Thread(target=grava, args=(grande,)), threading.Thread(target=grava, args=(pequeno,)),
      threading.Thread(target=grava, args=(grande,))]
[t.start() for t in ts]; [t.join() for t in ts]
ok(not erros, "gravações simultâneas sem erro: %s" % erros[:2])
try:
    lido = g.abrir_desenho("compressores", "concorrente")
    ok(len(lido["entidades"]) in (1000, 200000), "arquivo final íntegro (%d entidades)" % len(lido["entidades"]))
except ValueError as e:
    ok(False, "arquivo final corrompido: %s" % e)

# 3) troca insistente: arquivo destino aberto por outro handle durante 1,5 s (como faz o OneDrive)
alvo = os.path.join(DADOS, "seguro.json")
projetos._gravar_json(alvo, {"v": 1})
import ctypes
h = ctypes.windll.kernel32.CreateFileW(alvo, 0x80000000, 1, None, 3, 0x80, None)  # GENERIC_READ, FILE_SHARE_READ (sem DELETE)
def solta():
    time.sleep(1.5); ctypes.windll.kernel32.CloseHandle(h)
threading.Thread(target=solta).start()
t0 = time.time()
try:
    projetos._gravar_json(alvo, {"v": 2})
    ok(json.load(open(alvo))["v"] == 2 and 1.0 < time.time() - t0 < 6, "troca esperou o outro processo soltar o arquivo (%.1f s)" % (time.time() - t0))
except PermissionError as e:
    ok(False, "troca falhou mesmo insistindo: %s" % e)

shutil.rmtree(DADOS, ignore_errors=True)
print("\nFALHAS:", len(falhas)); sys.exit(1 if falhas else 0)
