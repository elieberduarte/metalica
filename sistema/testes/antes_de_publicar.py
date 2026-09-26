# -*- coding: utf-8 -*-
"""O que roda antes de publicar uma versão, num comando só:

1. os testes automáticos (pytest);
2. os verificadores das telas (testes/rodar_verificadores.py);
3. a bateria das obras reais (testes/bateria_obras.py), que compara cada obra com a última
   rodada aceita e grava o relatório em Projeto/bateria/ultima-comparacao.txt.

A versão só sai com 1 e 2 verdes e a bateria sem erro. A diferença que a bateria mostra não
é erro: é para conferir — se é o que a versão queria mudar, aceita-se com
`python testes/bateria_obras.py --aceitar`.

Uso:  python testes/antes_de_publicar.py [--sem-telas] [--sem-bateria]
"""
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def etapa(titulo, cmd):
    print(f"\n==== {titulo}", flush=True)
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=RAIZ, env=env)
    print(f"==== {titulo}: {'ok' if r.returncode == 0 else 'FALHOU'} em {(time.time() - t0) / 60:.1f} min", flush=True)
    return r.returncode == 0


def main(argv):
    resultados = [("testes automáticos", etapa("testes automáticos", [sys.executable, "-m", "pytest", "testes/", "-q", "-p", "no:warnings"]))]
    if "--sem-telas" not in argv:
        resultados.append(("verificadores das telas", etapa("verificadores das telas", [sys.executable, "testes/rodar_verificadores.py"])))
    if "--sem-bateria" not in argv:
        resultados.append(("bateria das obras", etapa("bateria das obras", [sys.executable, "testes/bateria_obras.py"])))
    print("\nresumo:")
    for nome, ok in resultados:
        print(f"  {'ok    ' if ok else 'FALHOU'} {nome}")
    if "--sem-bateria" not in argv:
        print("  confira as diferenças das obras em ../Projeto/bateria/ultima-comparacao.txt")
    return 0 if all(ok for _, ok in resultados) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
