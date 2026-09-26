# -*- coding: utf-8 -*-
"""Bateria das obras reais: refaz cada obra como o programa faz (detalhar todos os
desenhos, lista de materiais, resumos da obra) e compara com a última rodada aceita.

Por que existe: cada obra nova ensinou algo que quebrou em outra (os cantos quebrados na
Sala dos Compressores, as tesouras de oitão no ÁGUA GELADA, os rufos no Depósito Químico).
Refazendo todas a cada versão, a diferença aparece antes de chegar ao usuário.

As entradas ficam congeladas em `Projeto/bateria/entradas/<obra>/` (modelo, projeto, nomes
de produção, ajustes de furação) — a edição que o usuário faz na obra dele não se mistura
com a mudança do código. As fotografias aceitas ficam em `Projeto/bateria/<obra>.json`.
`Projeto/` fica fora do Git: são dados do cliente.

Uso:
    python testes/bateria_obras.py                 compara com a última rodada aceita
    python testes/bateria_obras.py --aceitar       grava a rodada atual como a aceita
    python testes/bateria_obras.py --aceitar-ultima  aceita a última rodada feita, sem refazer as obras
    python testes/bateria_obras.py --congelar      copia de novo as entradas das obras
    python testes/bateria_obras.py agua capitao    só as obras com esses pedaços no nome

Sai com código 1 quando uma obra deu erro (a diferença não é erro: é para conferir).
"""
import collections
import glob
import json
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.abspath(os.path.join(RAIZ, "..", "Projeto", "bateria"))
ENTRADAS = os.path.join(PASTA, "entradas")
#: As obras da bateria (a pasta delas em Documentos\Metálica).
OBRAS = ["me-sooro-sala-compressores", "me-sooro-cags-01-r00-modelo-água-gelada",
         "me-sooro-depósito-químico", "obra-capitão-2026"]
#: Arquivos da obra que o detalhamento lê.
ARQUIVOS = ["modelo.json", "projeto.json", os.path.join("detalhamento", "nomes.json"),
            os.path.join("detalhamento", "ajustes-furos.json")]
#: Diferença de peso (kg) e de comprimento (mm) abaixo da qual uma posição é igual.
TOL_KG, TOL_MM = 0.05, 0.6


def _documentos_metalica() -> str:
    sys.path.insert(0, RAIZ)
    from app import _documentos                       # a mesma pasta que o programa instalado usa
    return os.path.join(_documentos(), "Metálica")


def congelar(obras):
    origem = _documentos_metalica()
    for s in obras:
        de = os.path.join(origem, s)
        para = os.path.join(ENTRADAS, s)
        if not os.path.isdir(de):
            print(f"  {s}: não achei em {origem}")
            continue
        if os.path.isdir(para):
            shutil.rmtree(para)
        for rel in ARQUIVOS:
            if os.path.exists(os.path.join(de, rel)):
                os.makedirs(os.path.dirname(os.path.join(para, rel)), exist_ok=True)
                shutil.copy2(os.path.join(de, rel), os.path.join(para, rel))
        print(f"  {s}: entradas congeladas")


# ------------------------------------------------------------------ uma obra
def refazer(s: str) -> dict:
    """Refaz a obra numa pasta temporária pelo caminho do programa e devolve a fotografia."""
    tmp = tempfile.mkdtemp(prefix="bateria_")
    try:
        shutil.copytree(os.path.join(ENTRADAS, s), os.path.join(tmp, s))
        os.environ["METALICA_DADOS"] = tmp
        sys.path.insert(0, RAIZ)
        import app
        app.PROJETOS = tmp                                # o gerenciador de projetos é refeito a cada chamada
        from saida import resumos as _res
        original = _res.gerar_resumos
        _res.gerar_resumos = lambda pasta, R, imprimir_pdf=True: original(pasta, R, imprimir_pdf=False)
        t0 = time.time()
        try:
            det = app.detalhar_projeto(s, {})
            t_det = time.time() - t0
            lista = app.lista_de_materiais(s)
            res = app.gerar_resumos_projeto(s, {})
        finally:
            _res.gerar_resumos = original
        return fotografar(tmp, s, det, lista, res, t_det, time.time() - t0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fotografar(tmp, s, det, lista, res, t_det, t_total) -> dict:
    t = lista.get("totais") or {}
    posicoes = {}
    for p in lista.get("posicoes") or []:
        chave = str(p.get("nome") or p.get("marca"))
        posicoes[chave] = {"marca": p.get("marca"), "perfil": p.get("perfil"), "categoria": p.get("categoria"),
                           "qtd": p.get("quantidade"), "comprimento": round(float(p.get("comprimento") or 0), 1),
                           "peso": round(float(p.get("peso_total") or 0), 2)}
    desenhos = {}
    for arq in sorted(glob.glob(os.path.join(tmp, s, "desenhos-2d", "*.desenho.json"))):
        with open(arq, encoding="utf-8") as f:
            d = json.load(f)
        ents = d.get("entidades") or []
        ents = list(ents.values()) if isinstance(ents, dict) else ents
        por_camada = collections.Counter(e.get("camada") or "" for e in ents)
        desenhos[os.path.basename(arq).replace(".desenho.json", "")] = {
            "entidades": len(ents), "camadas": dict(sorted(por_camada.items())),
            "vistas": sorted(v.get("nome") or "" for v in (d.get("vistas") or [])),
        }
    return {
        "obra": s, "quando": time.strftime("%Y-%m-%dT%H:%M:%S"), "segundos": {"detalhar": round(t_det, 1), "total": round(t_total, 1)},
        "totais": {k: t.get(k) for k in ("pecas", "posicoes", "peso", "conjuntos", "acessorios")},
        "categorias": {c.get("categoria"): round(float(c.get("peso") or 0), 1) for c in (t.get("categorias") or [])},
        "resumo": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in (res.get("numeros") or {}).items()},
        "posicoes": posicoes, "desenhos": desenhos,
        "avisos": sorted(set(det.get("avisos") or [])),
    }


# ------------------------------------------------------------------ comparação
def comparar(antes: dict, agora: dict) -> list:
    """As diferenças que importam, em linhas de texto."""
    d = []
    for k, v in (agora.get("totais") or {}).items():
        a = (antes.get("totais") or {}).get(k)
        if a != v and not (isinstance(a, (int, float)) and isinstance(v, (int, float)) and abs(a - v) < TOL_KG):
            d.append(f"total {k}: {a} → {v}")
    for k in sorted(set(antes.get("resumo") or {}) | set(agora.get("resumo") or {})):
        a, v = (antes.get("resumo") or {}).get(k), (agora.get("resumo") or {}).get(k)
        if a != v and not (isinstance(a, (int, float)) and isinstance(v, (int, float)) and abs(a - v) < TOL_KG):
            d.append(f"resumo {k}: {a} → {v}")
    pa, pn = antes.get("posicoes") or {}, agora.get("posicoes") or {}
    saiu = sorted(set(pa) - set(pn))
    entrou = sorted(set(pn) - set(pa))
    if saiu:
        d.append(f"posições que saíram ({len(saiu)}): " + ", ".join(f"{n} ({pa[n]['perfil']})" for n in saiu[:15]) + (" …" if len(saiu) > 15 else ""))
    if entrou:
        d.append(f"posições novas ({len(entrou)}): " + ", ".join(f"{n} ({pn[n]['perfil']})" for n in entrou[:15]) + (" …" if len(entrou) > 15 else ""))
    mudou = []
    for n in sorted(set(pa) & set(pn)):
        a, v = pa[n], pn[n]
        partes = []
        if a["perfil"] != v["perfil"]:
            partes.append(f"perfil {a['perfil']} → {v['perfil']}")
        if a["qtd"] != v["qtd"]:
            partes.append(f"qtd {a['qtd']} → {v['qtd']}")
        if abs((a["comprimento"] or 0) - (v["comprimento"] or 0)) > TOL_MM:
            partes.append(f"compr. {a['comprimento']} → {v['comprimento']}")
        if abs((a["peso"] or 0) - (v["peso"] or 0)) > TOL_KG:
            partes.append(f"peso {a['peso']} → {v['peso']}")
        if a.get("categoria") != v.get("categoria"):
            partes.append(f"categoria {a.get('categoria')} → {v.get('categoria')}")
        if partes:
            mudou.append(f"{n}: " + "; ".join(partes))
    if mudou:
        d.append(f"posições alteradas ({len(mudou)}):")
        d.extend("   " + m for m in mudou[:25])
        if len(mudou) > 25:
            d.append(f"   … e mais {len(mudou) - 25}")
    da, dn = antes.get("desenhos") or {}, agora.get("desenhos") or {}
    for nome in sorted(set(da) | set(dn)):
        if nome not in dn:
            d.append(f"desenho {nome}: não saiu mais")
            continue
        if nome not in da:
            d.append(f"desenho {nome}: novo ({dn[nome]['entidades']} entidades)")
            continue
        a, v = da[nome], dn[nome]
        if a["entidades"] != v["entidades"]:
            camadas = [f"{c} {a['camadas'].get(c, 0)}→{v['camadas'].get(c, 0)}" for c in sorted(set(a["camadas"]) | set(v["camadas"]))
                       if a["camadas"].get(c, 0) != v["camadas"].get(c, 0)]
            d.append(f"desenho {nome}: {a['entidades']} → {v['entidades']} entidades ({', '.join(camadas[:8])})")
        if a["vistas"] != v["vistas"]:
            fora = sorted(set(a["vistas"]) - set(v["vistas"]))
            novas = sorted(set(v["vistas"]) - set(a["vistas"]))
            d.append(f"desenho {nome}: vistas " + (f"sem {fora[:6]}" if fora else "") + (f" com {novas[:6]}" if novas else ""))
    novos_av = sorted(set(agora.get("avisos") or []) - set(antes.get("avisos") or []))
    if novos_av:
        d.append(f"avisos novos ({len(novos_av)}): " + " | ".join(a[:140] for a in novos_av[:5]))
    return d


def main(argv):
    filtros = [a for a in argv if not a.startswith("--")]
    obras = [s for s in OBRAS if not filtros or any(f.lower() in s.lower() for f in filtros)]
    os.makedirs(PASTA, exist_ok=True)
    if "--aceitar-ultima" in argv:
        for s in obras:
            ult = os.path.join(PASTA, s + ".ultima.json")
            if os.path.exists(ult):
                shutil.copy2(ult, os.path.join(PASTA, s + ".json"))
                print(f"  {s}: a última rodada virou a aceita")
            else:
                print(f"  {s}: sem rodada feita para aceitar")
        return 0
    if "--congelar" in argv or not all(os.path.isdir(os.path.join(ENTRADAS, s)) for s in obras):
        print("congelando as entradas…")
        congelar([s for s in obras if "--congelar" in argv or not os.path.isdir(os.path.join(ENTRADAS, s))])
    aceitar = "--aceitar" in argv
    erros, relatorio = 0, []
    for s in obras:
        if not os.path.isdir(os.path.join(ENTRADAS, s)):
            continue
        print(f"\n== {s}", flush=True)
        try:
            foto = refazer(s)
        except Exception as e:                                        # noqa: BLE001
            import traceback
            erros += 1
            print("  ERRO:", e)
            traceback.print_exc()
            relatorio.append(f"== {s}\n  ERRO: {e}")
            continue
        t = foto["totais"]
        print(f"  {t['posicoes']} posições, {t['pecas']} peças, {t['peso']:.1f} kg, {len(foto['desenhos'])} desenhos "
              f"· detalhar {foto['segundos']['detalhar']:.0f} s, tudo {foto['segundos']['total']:.0f} s")
        caminho = os.path.join(PASTA, s + ".json")
        with open(os.path.join(PASTA, s + ".ultima.json"), "w", encoding="utf-8") as f:
            json.dump(foto, f, ensure_ascii=False, indent=1)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                antes = json.load(f)
            dif = comparar(antes, foto)
            print(f"  comparado com a rodada aceita em {antes.get('quando', '?')}: " + ("igual" if not dif else f"{len(dif)} diferença(s)"))
            for linha in dif:
                print("   ", linha)
            relatorio.append(f"== {s}\n" + ("  igual à rodada aceita" if not dif else "\n".join("  " + x for x in dif)))
        else:
            print("  primeira rodada: nada para comparar")
            relatorio.append(f"== {s}\n  primeira rodada")
        if aceitar or not os.path.exists(caminho):
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(foto, f, ensure_ascii=False, indent=1)
            print("  gravada como a rodada aceita")
    with open(os.path.join(PASTA, "ultima-comparacao.txt"), "w", encoding="utf-8") as f:
        f.write(time.strftime("%d/%m/%Y %H:%M") + "\n\n" + "\n\n".join(relatorio) + "\n")
    print(f"\nrelatório: {os.path.join(PASTA, 'ultima-comparacao.txt')}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
