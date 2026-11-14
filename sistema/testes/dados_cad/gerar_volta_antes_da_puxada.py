# -*- coding: utf-8 -*-
"""Grava o que a volta do 3D fazia na planta ANTES da ponta puxada, nos contraexemplos das revisões de 14/11 — o oráculo
de test_volta_do_3d_montagem::test_fora_do_caso_puro_a_volta_e_a_de_antes_da_ponta_puxada.

    python testes/dados_cad/gerar_volta_antes_da_puxada.py [commit]

O commit padrão é o a10fa80 (o pai rebaseado do 8563caf, a 1ª versão da ponta puxada). Lê de lá só o
nucleo3d/de_planta_estrutura.py (git show) e o carrega como módulo à parte; a montagem dos casos é a de hoje (os casos
estão em CASOS_FORA_DO_PURO, no teste) — entre aquele commit e hoje o arquivo mudou só na volta. Grava
volta_antes_da_puxada.json: {commit, casos: {nome: {id da linha: {a, b, atributos}}}}. O main não serve de oráculo: nas
peças puxadas ele tem o defeito do c290e43 (o alongamento da montagem lido como mudança)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
RAIZ = os.path.dirname(SISTEMA)
sys.path.insert(0, SISTEMA)
sys.path.insert(0, os.path.dirname(AQUI))


def gerar(commit: str = "a10fa80") -> str:
    completo = subprocess.run(["git", "rev-parse", commit], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.strip()
    src = subprocess.run(["git", "show", "%s:sistema/nucleo3d/de_planta_estrutura.py" % completo], cwd=RAIZ,
                         capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "dpe_antes_da_puxada.py")
        with open(f, "wb") as g:
            g.write(src)
        spec = importlib.util.spec_from_file_location("dpe_antes_da_puxada", f)
        antes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(antes)
        import test_volta_do_3d_montagem as T
        casos = {nome: T._o_que_a_volta_fez(antes, nome) for nome in sorted(T.CASOS_FORA_DO_PURO)}
    destino = os.path.join(AQUI, "volta_antes_da_puxada.json")
    with open(destino, "w", encoding="utf-8", newline="\n") as g:
        json.dump({"commit": completo, "casos": casos}, g, ensure_ascii=False, indent=1, sort_keys=True)
    return destino


if __name__ == "__main__":
    print(gerar(*(sys.argv[1:2] or [])))
