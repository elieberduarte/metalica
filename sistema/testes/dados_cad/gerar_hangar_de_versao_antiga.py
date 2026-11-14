# -*- coding: utf-8 -*-
"""Gera o 3D do Hangar (a Montagem identificada de hangar_montagem_identificada.json, a planta de hoje) pelo código de
uma versão PUBLICADA anterior — o modelo que o usuário tem gravado no projeto — para a volta do 3D de agora ser
conferida contra ele (revisão independente de 14/11, reforço A: o "modelo de antes" dos testes era o de hoje sem o
carimbo, e coincidia com a régua por construção).

    python testes/dados_cad/gerar_hangar_de_versao_antiga.py v0.9.2

Extrai o `sistema` inteiro da marca (git archive — só `nucleo*` não basta, falta o módulo `fabrica`) numa pasta
temporária e monta o Hangar num processo à parte, só com aquele código (python -I, a pasta da versão como a única do
sistema). Guarda em hangar_gerado_<versao>.json só as peças com `origem_2d` que não são de tesoura (a volta não toca a
tesoura, que é refeita pela planta) — o modelo inteiro tem 1,1 MB. Pesado: uma montagem do Hangar (segundos a
dezenas de segundos); rodar só com a vez da máquina."""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
RAIZ = os.path.dirname(SISTEMA)                                   # o repositório
HANGAR = os.path.join(AQUI, "hangar_montagem_identificada.json")

#: roda dentro da pasta da versão antiga: monta a planta e escreve o modelo filtrado na saída padrão
_MONTAR = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from nucleo2d.desenho import Desenho
from nucleo3d import de_planta_estrutura as DPE
with open(sys.argv[2], encoding="utf-8") as f:
    bruto = json.load(f)
des = Desenho.de_dict(bruto["desenho"])
tesouras = {e.id for e in des.entidades.values() if (e.atributos or {}).get("elemento") == "trelica"}
doc, avisos = DPE.modelo_da_planta(des, bruto["niveis"])
d = doc.dict()
d["entidades"] = [e for e in d["entidades"]
                  if (e.get("atributos") or {}).get("origem_2d") and (e.get("atributos") or {}).get("origem_2d") not in tesouras]
sys.stdout.buffer.write(json.dumps({"modelo": d, "avisos": len(avisos)}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))  # o -I ignora o PYTHONIOENCODING
"""


def gerar(versao: str) -> str:
    commit = subprocess.run(["git", "rev-list", "-n", "1", versao], cwd=RAIZ, capture_output=True, text=True,
                            check=True).stdout.strip()
    tar = subprocess.run(["git", "archive", "--format=tar", versao, "sistema"], cwd=RAIZ, capture_output=True,
                         check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            t.extractall(tmp, filter="data")
        pasta = os.path.join(tmp, "sistema")
        r = subprocess.run([sys.executable, "-I", "-c", _MONTAR, pasta, HANGAR], cwd=pasta, capture_output=True,
                           text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if r.returncode != 0:
            raise SystemExit("a montagem da %s falhou:\n%s" % (versao, r.stderr[-3000:]))
        sai = json.loads(r.stdout)
    destino = os.path.join(AQUI, "hangar_gerado_%s.json" % versao.replace(".", "_"))
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"versao": versao, "commit": commit, "planta": os.path.basename(HANGAR), "avisos": sai["avisos"],
                   "modelo": sai["modelo"]}, f, ensure_ascii=False, separators=(",", ":"))
    return destino


if __name__ == "__main__":
    for v in sys.argv[1:] or ["v0.9.2"]:
        caminho = gerar(v)
        print("%s: %s (%.0f kB)" % (v, caminho, os.path.getsize(caminho) / 1024))
