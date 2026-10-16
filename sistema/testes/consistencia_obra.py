# -*- coding: utf-8 -*-
"""Confere as saídas de uma obra já detalhada (saida/consistencia.py): o mesmo número em romaneio, lista de
materiais, 3D e pranchas. Só lê a pasta; não refaz nem grava nada.

    python testes/consistencia_obra.py <pasta da obra>
    python testes/consistencia_obra.py <slug>            uma obra de Documentos\\Metálica (só leitura)

Sai com código 1 quando há achado que leva a fabricar, comprar ou montar diferente ("fabrica").
A bateria das obras (testes/bateria_obras.py) roda a mesma conferência em cada obra, com as pranchas montadas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from saida import consistencia  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    pasta = argv[0]
    if not os.path.isdir(pasta):
        pasta = os.path.join(os.path.expanduser("~"), "Documents", "Metálica", argv[0])
    if not os.path.isdir(pasta):
        print("pasta não encontrada:", argv[0])
        return 2
    achados = consistencia.conferir(pasta)
    print(consistencia.resumo(achados))
    for a in achados:
        print(f"  [{a['gravidade']}] {a['conferencia']}: {a['texto']}")
    return 1 if any(a["gravidade"] == "fabrica" for a in achados) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
