# -*- coding: utf-8 -*-
"""Conferência seletiva: o que rodar antes de publicar, pelo que mudou desde a última versão
publicada (a última etiqueta vX.Y.Z do Git).

A conferência completa (os ~45 verificadores das telas e a bateria das obras) leva uns 20 min;
a maior parte das versões mexe em uma ou duas telas. Aqui:

* o pytest roda sempre (1–2 min);
* cada verificador de tela roda quando mudou uma tela que ele abre (o 2D, o 3D, a área de
  trabalho, os materiais…) ou um módulo Python que ele usa; os arquivos comuns a todas as telas
  (estilo, versão, sinal de vida) valem para todos; o servidor (app.py) chama a "fumaça" — a
  tela inicial, o 2D, o 3D e a área de trabalho;
* a bateria das obras de detalhamento (IFC) roda quando mudou o núcleo (cálculo, detalhamento,
  saídas, IFC); a do Posto CB, quando mudou a montagem 3D (nucleo3d/);
* a completa volta sozinha quando mexeu no núcleo, quando não há registro de uma completa, e a
  cada MAX_SEM_COMPLETA versões desde a última completa (para pegar o que a seletiva deixa passar).

Uso (o antes_de_publicar.py chama): python testes/selecao.py [--desde v0.8.44]   → mostra a escolha e o porquê
"""
import json
import os
import re
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(RAIZ)
REGISTRO = os.path.abspath(os.path.join(RAIZ, "..", "Projeto", "bateria", "ultima-completa.json"))
MAX_SEM_COMPLETA = 4

#: Mexer aqui é mexer no núcleo: cálculo, saídas, IFC, geometria das peças.
NUCLEO = ("nucleo/", "saida/", "ifc/", "nucleo3d/geometria.py", "nucleo3d/modelo.py",
          "nucleo3d/eixos.py", "empacotar/", "dados/")
#: O detalhamento e o CAD 2D (28/09): só o 2D depende dele — as telas do CAD, os verificadores do
#: detalhamento sem tela e a bateria das obras (que compara os desenhos). O 3D fica de fora.
DETALHAMENTO = ("nucleo2d/",)
DO_DETALHAMENTO = ["verif_detalhar", "verif_pranchas", "verif_vistas_gerais"]
#: A montagem 3D (a bateria do Posto CB).
MONTAGEM = ("nucleo3d/",)
#: Arquivos das telas: o caminho (começo) → as telas que usam.
TELAS = [("web/cad/", {"cad"}), ("web/editor3d/", {"editor"}), ("web/dividida", {"dividida"}), ("web/barra_unica", {"dividida"}),
         ("web/area.js", {"cad", "editor", "dividida"}), ("web/trelicas", {"trelicas"}),
         ("web/materiais", {"materiais"}), ("web/analise", {"analise"}), ("web/memorial", {"memorial"}),
         ("web/ligacoes", {"ligacoes"}), ("web/catalogo", {"catalogo"}), ("web/inicio", {"inicio"}),
         ("web/index.html", {"inicio"}), ("web/app.js", {"dimensionar"}), ("web/dimensionar", {"dimensionar"})]
#: Comuns a todas as telas.
COMUNS = ("web/estilo.css", "web/versao.js", "web/vivo.js", "web/atualizacao.js", "web/tema-janela.js",
          "web/lentidao.js", "web/lib/")
#: A montagem 3D mudou: as telas que mostram o que ela monta (além da bateria do Posto CB).
DA_MONTAGEM = ["verif_apoios_ui", "verif_esqueleto_ui", "verif_trelicas_ui", "verif_dividida_ui"]
#: O servidor mudou: o mínimo que abre as telas principais.
FUMACA = ["verif_gerenciador", "verif_cad", "verificar_editor", "verif_dividida_ui"]
_TELA_NA_URL = re.compile(r"/(cad|editor|dividida|materiais|analise|memorial|ligacoes|trelicas|dimensionar|catalogo)[?\"'/]")
#: a primeira tela que o verificador abre (além da inicial): a que ele testa
_PRINCIPAL = re.compile(r"navegar\(\s*(?:base|BASE|url)?\s*\+?\s*f?[\"']/(cad|editor|dividida|materiais|analise|memorial|ligacoes|trelicas|dimensionar|catalogo)")


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8").stdout
    except OSError:
        return ""


def ultima_etiqueta() -> str:
    return _git("describe", "--tags", "--abbrev=0").strip()


def mudados(base: str) -> list:
    """os arquivos de sistema/ mudados desde `base` (commitados ou não), relativos a sistema/"""
    nomes = set(_git("diff", "--name-only", base, "--", "sistema").split())
    for linha in _git("status", "--porcelain", "--", "sistema").splitlines():
        caminho = linha[3:].strip().strip('"')
        if caminho:
            nomes.add(caminho)
    return sorted(n[len("sistema/"):] for n in nomes if n.startswith("sistema/"))


def _verificadores():
    """{nome: (telas que ele testa, texto, telas por onde passa)} dos verificadores que se verificam sozinhos.
    A tela que ele testa é a primeira que abre; sem ela no código, todas as que cita."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("rv", os.path.join(RAIZ, "testes", "rodar_verificadores.py"))
    rv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rv)
    roda, _fora = rv.descobrir()
    out = {}
    for c in roda:
        with open(c, encoding="utf-8", errors="replace") as f:
            texto = f.read()
        passa = set(_TELA_NA_URL.findall(texto))
        if "cartao" in texto or "#lista" in texto:
            passa.add("inicio")
        m = _PRINCIPAL.search(texto)
        telas = {m.group(1)} if m else set(passa)
        if "cartao" in texto or "#lista" in texto:
            telas.add("inicio")
        out[os.path.splitext(os.path.basename(c))[0]] = (telas, texto, passa)
    return out


def versoes_desde_completa() -> int:
    """quantas versões publicadas desde a última conferência completa (sem registro: muitas)"""
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            ultima = json.load(f).get("etiqueta")
    except (OSError, ValueError):
        return 99
    etiquetas = _git("tag", "--sort=-creatordate").split()
    return etiquetas.index(ultima) if ultima in etiquetas else 99


def registrar_completa(etiqueta: str) -> None:
    import time
    os.makedirs(os.path.dirname(REGISTRO), exist_ok=True)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump({"etiqueta": etiqueta, "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, ensure_ascii=False)


def escolher(forcar_completa: bool = False, base: str = None) -> dict:
    base = base or ultima_etiqueta()
    arqs = mudados(base) if base else []
    verifs = _verificadores()
    todos = sorted(verifs)
    nucleo = [a for a in arqs if a.startswith(NUCLEO)]
    faltam = versoes_desde_completa()
    if forcar_completa or not base or nucleo or faltam >= MAX_SEM_COMPLETA:
        motivo = ("pedida" if forcar_completa else "sem a última versão no Git" if not base
                  else f"mexeu no núcleo ({', '.join(nucleo[:4])}{'…' if len(nucleo) > 4 else ''})" if nucleo
                  else f"{faltam} versões desde a última completa")
        return {"completa": True, "motivo": motivo, "base": base, "mudados": arqs, "verificadores": todos,
                "bateria_ifc": True, "bateria_planta": True}
    escolhidos, porque = set(), {}

    def pega(nome, razao):
        if nome in verifs and nome not in escolhidos:
            escolhidos.add(nome)
            porque[nome] = razao
    for a in arqs:
        if a.startswith(COMUNS):
            for n in todos:
                pega(n, a)
            continue
        telas = set()
        for prefixo, ts in TELAS:
            if a.startswith(prefixo):
                telas |= ts
        if telas:
            # a navegação entre as telas (web/area.js) vale para quem passa por elas; o resto, para quem as testa
            por_onde = a == "web/area.js"
            for n, (tv, _t, passa) in verifs.items():
                if (passa if por_onde else tv) & telas:
                    pega(n, a)
            continue
        base_nome = os.path.splitext(os.path.basename(a))[0]
        if a.startswith("testes/verificadores/") or a.startswith("testes/verif"):
            pega(base_nome, a)                                  # o próprio verificador mudou
            continue
        if a == "app.py":
            for n in FUMACA:
                pega(n, a)
            continue
        if a.startswith(DETALHAMENTO):
            for n, (tv, _t, _p) in verifs.items():
                if "cad" in tv:
                    pega(n, a)
            for n in DO_DETALHAMENTO:
                pega(n, a)
            continue
        if a.startswith(MONTAGEM):
            for n in DA_MONTAGEM:
                pega(n, a)
        if a.endswith(".py") and not a.startswith("testes/"):
            # o módulo que mudou: os verificadores que falam dele (apoios, trelicas_lidas, projetos, dev…)
            chave = base_nome.replace("_", "")
            for n, (_tv, texto, _p) in verifs.items():
                if base_nome in texto or chave in n.replace("_", ""):
                    pega(n, a)
    return {"completa": False, "motivo": f"seletiva: {len(arqs)} arquivo(s) mudados desde {base}", "base": base,
            "mudados": arqs, "verificadores": sorted(escolhidos), "porque": porque,
            "bateria_ifc": any(a.startswith(DETALHAMENTO) for a in arqs),
            "bateria_planta": any(a.startswith(MONTAGEM) for a in arqs)}


if __name__ == "__main__":
    import sys
    desde = sys.argv[sys.argv.index("--desde") + 1] if "--desde" in sys.argv else None     # simular a partir de outra versão
    e = escolher("--completa" in sys.argv, desde)
    print(("COMPLETA — " if e["completa"] else "") + e["motivo"])
    print(f"  {len(e['mudados'])} arquivo(s): " + ", ".join(e["mudados"][:12]) + (" …" if len(e["mudados"]) > 12 else ""))
    print(f"  verificadores ({len(e['verificadores'])}): " + ", ".join(e["verificadores"]))
    for n, r in sorted((e.get("porque") or {}).items()):
        print(f"     {n:28s} ← {r}")
    print(f"  bateria das obras de detalhamento: {'sim' if e['bateria_ifc'] else 'não'} · do Posto CB: {'sim' if e['bateria_planta'] else 'não'}")
