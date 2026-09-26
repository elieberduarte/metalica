# -*- coding: utf-8 -*-
"""Roda todos os verificadores das telas (editor 3D, CAD, lista de materiais…) de uma vez,
um depois do outro, e diz quais passaram.

Cada verificador sobe o próprio servidor numa porta fixa e um Chrome sem janela, faz o
que o usuário faria e confere o resultado; ele falhou se sai com código diferente de zero
ou se imprime uma linha "FALHA". Os scripts de diagnóstico que pedem argumentos (porta de
um servidor já aberto, arquivo de saída) ficam de fora — eles não se verificam sozinhos.

Uso:
    python testes/rodar_verificadores.py              todos
    python testes/rodar_verificadores.py furo cantos  só os que têm esses pedaços no nome
    python testes/rodar_verificadores.py --lista      só lista quais rodariam

Sai com código 1 se algum falhou — é o que se roda antes de publicar uma versão
(testes/antes_de_publicar.py).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTAS = [os.path.join(RAIZ, "testes", "verificadores"), os.path.join(RAIZ, "testes")]
#: Tempo máximo de um verificador (s): o da lista de materiais gera os resumos em PDF.
LIMITE = 900
_PEDE_ARGUMENTOS = re.compile(r"len\(sys\.argv\)\s*<\s*[23]")


def descobrir(filtros=()):
    """(roda, fora): os verificadores que se verificam sozinhos e os de diagnóstico."""
    roda, fora = [], []
    for pasta in PASTAS:
        for nome in sorted(os.listdir(pasta)):
            if not (nome.startswith("verif_") or nome.startswith("verificar_")) or not nome.endswith(".py"):
                continue
            if nome == "verificar_editor.py" and pasta.endswith("testes"):
                pass                                    # o módulo base também tem o roteiro próprio
            caminho = os.path.join(pasta, nome)
            with open(caminho, encoding="utf-8", errors="replace") as f:
                texto = f.read()
            if filtros and not any(x in nome for x in filtros):
                continue
            (fora if _PEDE_ARGUMENTOS.search(texto) else roda).append(caminho)
    return roda, fora


def _pede_servidor(caminho) -> bool:
    """Os roteiros antigos (testes/verificar_*.py) esperam um servidor já aberto (--porta)."""
    with open(caminho, encoding="utf-8", errors="replace") as f:
        texto = f.read()
    return "--porta" in texto and "Servidor fora do ar" in texto


def _subir_servidor():
    """Um servidor numa porta livre (nunca a 8765 do programa instalado) com uma pasta de
    dados temporária, os modelos de exemplo copiados: (processo, porta, pasta) ou None."""
    pasta = tempfile.mkdtemp(prefix="verificadores_")
    origem = os.path.join(RAIZ, "projetos", "modelos")
    if os.path.isdir(origem):
        shutil.copytree(origem, os.path.join(pasta, "modelos"))
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        porta = so.getsockname()[1]
    if porta == 8765:
        porta = 8799
    proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "app.py"), "--sem-navegador", "--porta", str(porta), "--dados", pasta],
                            cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/versao", timeout=1) as r:
                dados = json.loads(r.read().decode("utf-8")).get("dados", "")
                if os.path.normcase(os.path.realpath(dados)) == os.path.normcase(os.path.realpath(pasta)):
                    return proc, porta, pasta
        except Exception:                                                  # noqa: BLE001
            pass
        time.sleep(0.5)
    proc.kill()
    shutil.rmtree(pasta, ignore_errors=True)
    return None


def rodar(caminho):
    """(ok, segundos, falhas, resumo): roda um verificador e lê o resultado."""
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cmd = [sys.executable, caminho]
    servidor = None
    if _pede_servidor(caminho):
        # servidor próprio, numa porta livre e com pasta de dados temporária: sem --porta
        # estes roteiros usam a 8765, que é a do Metálica instalado — e gravavam modelos e
        # um projeto de teste na pasta de dados do usuário
        servidor = _subir_servidor()
        if servidor is None:
            return False, time.time() - t0, ["não consegui subir o servidor próprio do verificador"], 0
        cmd += ["--porta", str(servidor[1])]
    try:
        r = subprocess.run(cmd, cwd=RAIZ, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=LIMITE)
        saida = (r.stdout or "") + (r.stderr or "")
        codigo = r.returncode
    except subprocess.TimeoutExpired as e:
        saida = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[tempo esgotado]"
        codigo = -1
    finally:
        if servidor:
            servidor[0].kill()
            shutil.rmtree(servidor[2], ignore_errors=True)
    dt = time.time() - t0
    falhas = [l.strip() for l in saida.splitlines() if re.match(r"\s*FALHA\b", l) and not re.match(r"\s*FALHAS\b", l)]
    total = re.search(r"FALHAS:\s*(\d+)", saida) or re.search(r"(\d+)\s+falha\(s\)", saida)
    n_falhas = int(total.group(1)) if total else len(falhas)
    oks = len(re.findall(r"^\s*ok\b", saida, re.M))
    ok = codigo == 0 and n_falhas == 0 and not falhas and "Traceback" not in saida
    if not ok and not falhas:
        linhas = [l for l in saida.strip().splitlines() if l.strip()]
        falhas = linhas[-6:]
    return ok, dt, falhas, oks


def main(argv):
    so_lista = "--lista" in argv
    filtros = [a for a in argv if not a.startswith("--")]
    roda, fora = descobrir(filtros)
    if so_lista:
        for c in roda:
            print("roda  ", os.path.relpath(c, RAIZ))
        for c in fora:
            print("fora  ", os.path.relpath(c, RAIZ), "(diagnóstico: pede argumentos)")
        return 0
    print(f"{len(roda)} verificadores (fora {len(fora)} de diagnóstico)\n", flush=True)
    resultados = []
    t0 = time.time()
    for c in roda:
        nome = os.path.splitext(os.path.basename(c))[0]
        ok, dt, falhas, oks = rodar(c)
        resultados.append((nome, ok, dt, falhas))
        print(f"{'ok   ' if ok else 'FALHA'}  {nome:28s} {dt:6.0f} s  {oks} verificações", flush=True)
        for f in falhas[:6]:
            print(f"         {f[:220]}", flush=True)
    ruins = [r for r in resultados if not r[1]]
    print(f"\n{len(resultados) - len(ruins)} de {len(resultados)} passaram em {(time.time() - t0) / 60:.1f} min")
    if ruins:
        print("falharam:", ", ".join(r[0] for r in ruins))
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
