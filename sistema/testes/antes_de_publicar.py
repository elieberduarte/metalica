# -*- coding: utf-8 -*-
"""O que roda antes de publicar uma versão, num comando só:

1. os testes automáticos (pytest) — sempre;
2. os verificadores das telas (testes/rodar_verificadores.py);
3. a bateria das obras (testes/bateria_obras.py): as de detalhamento (IFC, já em produção) e a
   montagem pela planta do Posto CB — cada uma comparada com a última rodada aceita, relatório em
   Projeto/bateria/ultima-comparacao.txt.

Seletiva (o normal): 2 e 3 só no que a versão mexeu desde a última publicada (testes/selecao.py —
os verificadores das telas que mudaram, a bateria do detalhamento quando mudou o núcleo, a do
Posto quando mudou a montagem 3D). A completa volta sozinha quando mexeu no núcleo, a cada 4
versões e quando pedida (`--completa`), e fica registrada em Projeto/bateria/ultima-completa.json.

A versão só sai com 1 e 2 verdes e a bateria sem erro. A diferença que a bateria mostra não
é erro: é para conferir — se é o que a versão queria mudar, aceita-se com
`python testes/bateria_obras.py --aceitar`.

Uso:  python testes/antes_de_publicar.py [--completa] [--sem-telas] [--sem-bateria]
"""
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "testes"))
sys.path.insert(0, RAIZ)


def etapa(titulo, cmd):
    print(f"\n==== {titulo}", flush=True)
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=RAIZ, env=env)
    print(f"==== {titulo}: {'ok' if r.returncode == 0 else 'FALHOU'} em {(time.time() - t0) / 60:.1f} min", flush=True)
    return r.returncode == 0


def _paralelo_pytest() -> list:
    """`-n N` quando o pytest-xdist está instalado: a suíte inteira em metade dos núcleos
    (medido: 200 s → 93 s com 6). Sem ele, roda como sempre."""
    import importlib.util
    if importlib.util.find_spec("xdist") is None:
        return []
    return ["-n", str(max(1, min(6, (os.cpu_count() or 2) // 2)))]


def main(argv):
    import selecao
    t_inicio = time.time()
    esc = selecao.escolher("--completa" in argv)
    print(("CONFERÊNCIA COMPLETA — " if esc["completa"] else "CONFERÊNCIA SELETIVA — ") + esc["motivo"], flush=True)
    if not esc["completa"]:
        print(f"  verificadores ({len(esc['verificadores'])}): " + (", ".join(esc["verificadores"]) or "nenhum"))
        print(f"  bateria: detalhamento {'sim' if esc['bateria_ifc'] else 'não'} · Posto CB {'sim' if esc['bateria_planta'] else 'não'}")
    resultados = [("testes automáticos", etapa("testes automáticos",
                                                [sys.executable, "-m", "pytest", "testes/", "-q", "-p", "no:warnings"] + _paralelo_pytest()))]
    if "--sem-telas" not in argv and esc["verificadores"]:
        filtros = [] if esc["completa"] else [n + ".py" for n in esc["verificadores"]]
        resultados.append(("verificadores das telas", etapa("verificadores das telas",
                                                             [sys.executable, "testes/rodar_verificadores.py"] + filtros)))
    bateria = []
    if esc["bateria_ifc"] and not esc["bateria_planta"]:
        bateria = ["--sem-planta"]
    elif esc["bateria_planta"] and not esc["bateria_ifc"]:
        bateria = ["--so-planta"]
    if "--sem-bateria" not in argv and (esc["bateria_ifc"] or esc["bateria_planta"]):
        resultados.append(("bateria das obras", etapa("bateria das obras", [sys.executable, "testes/bateria_obras.py"] + bateria)))
    print("\nresumo:")
    for nome, ok in resultados:
        print(f"  {'ok    ' if ok else 'FALHOU'} {nome}")
    if any(n == "bateria das obras" for n, _ in resultados):
        print("  confira as diferenças das obras em ../Projeto/bateria/ultima-comparacao.txt")
    tudo_ok = all(ok for _, ok in resultados)
    if tudo_ok and esc["completa"] and "--sem-telas" not in argv and "--sem-bateria" not in argv:
        import versao
        selecao.registrar_completa("v" + versao.VERSAO)
        print(f"  conferência completa registrada para v{versao.VERSAO}")
    print(f"  tudo em {(time.time() - t_inicio) / 60:.1f} min")
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
