# -*- coding: utf-8 -*-
"""As revisões das pranchas (usuário, 24/10: a opção A — a tabela inteira em cima do carimbo, a mais nova em cima,
REV. | DATA | DESCRIÇÃO DA REVISÃO | POR; lançadas pelo diálogo "Revisões das pranchas…", que marca as pranchas que
mudaram; imagens em Projeto/ANALISES/Desenho-e-pranchas/Revisoes-opcao-A-*.png).

Ficam no projeto, em `carimbo_pranchas.revisoes`: {"3": [{rev, data, descricao, por}, …]} — a numeração é de cada
prancha (a prancha 03 vai para a REV. 02 enquanto a 05 está na 01). A tabela é desenhada pelo carimbo
(modelo_hermes.desenhar_revisoes) quando as pranchas são montadas, e posta direto no desenho das pranchas já montado
quando uma revisão é lançada (`aplicar_no_desenho`), sem remontar."""
import datetime
import re
from typing import Dict, List, Optional, Sequence

from nucleo2d.desenho import Desenho, Texto, transladar
from nucleo2d.modelo_hermes import desenhar_revisoes
from nucleo2d.pranchas import FOLHAS

__all__ = ["hoje", "linhas_validas", "nova_revisao", "ultima_revisao", "aplicar_no_desenho", "pranchas_do_projeto",
           "gravar"]

CAMPO = "revisoes"


def hoje() -> str:
    return datetime.date.today().strftime("%d/%m/%Y")


def linhas_validas(linhas) -> List[dict]:
    """As linhas de uma prancha, limpas: {rev, data, descricao, por} em texto, sem as vazias."""
    out = []
    for ln in linhas or []:
        if not isinstance(ln, dict):
            continue
        d = {k: str(ln.get(k) or "").strip() for k in ("rev", "data", "descricao", "por")}
        if d["rev"] or d["descricao"]:
            out.append(d)
    return out


def ultima_revisao(linhas) -> str:
    linhas = linhas_validas(linhas)
    return linhas[-1]["rev"] if linhas else ""


def _seguinte(rev: str) -> str:
    m = re.match(r"^(\d+)$", str(rev or "").strip())
    return "%02d" % (int(m.group(1)) + 1) if m else "01"


def nova_revisao(revisoes: dict, numeros: Sequence[int], descricao: str, por: str = "", data: str = "",
                 data_emissao: str = "") -> dict:
    """A revisão nova nas pranchas `numeros`: cada uma vai para o número seguinte ao dela; a que ainda não tinha
    revisão começa pela "00 — EMISSÃO INICIAL" (na `data_emissao`). Devolve as revisões novas (não mexe na entrada)."""
    descricao = str(descricao or "").strip()
    if not descricao:
        raise ValueError("escreva a descrição da revisão.")
    out = {str(k): linhas_validas(v) for k, v in (revisoes or {}).items()}
    data = str(data or "").strip() or hoje()
    for n in sorted({int(n) for n in numeros}):
        linhas = out.get(str(n)) or []
        if not linhas:
            linhas = [{"rev": "00", "data": str(data_emissao or "").strip(), "descricao": "EMISSÃO INICIAL", "por": por}]
        linhas.append({"rev": _seguinte(linhas[-1]["rev"]), "data": data, "descricao": descricao.upper(), "por": por})
        out[str(n)] = linhas
    return out


def _texto_da_prancha(texto: str, rev: str) -> str:
    """"PRANCHA 03/12   REV. 01" com a revisão nova (ou acrescentada)."""
    base = re.sub(r"\s*REV\.\s*\S+\s*$", "", str(texto or ""))
    return "%s   REV. %s" % (base, rev) if rev else base


def _folhas(d: Desenho) -> List[dict]:
    """As folhas do desenho das pranchas: {numero, formato, origem}; a prancha solta, uma na origem."""
    lista = d.metadados.get("pranchas")
    if lista:
        return [{"numero": int(p.get("numero") or i + 1), "formato": p.get("formato") if p.get("formato") in FOLHAS else "A1",
                 "origem": tuple(p.get("origem") or (0.0, 0.0)), "folha": p.get("folha")} for i, p in enumerate(lista)]
    p = d.metadados.get("prancha")
    if p:
        return [{"numero": int(p.get("numero") or 1), "formato": p.get("formato") if p.get("formato") in FOLHAS else "A1",
                 "origem": (0.0, 0.0), "folha": None, "solta": True}]
    return []


def aplicar_no_desenho(d: Desenho, revisoes: dict) -> dict:
    """Põe a tabela de cada prancha (de `revisoes`) no desenho das pranchas já montado: tira a tabela de antes, desenha
    a nova no lugar dela (acima do carimbo) e acerta o "REV." do número da prancha. A prancha não é rearrumada: a
    tabela que cai em cima de um detalhe é avisada (`encostam`), para arrastar o detalhe. Devolve {folhas, encostam}."""
    mudou, encostam = 0, []
    for f in _folhas(d):
        n = f["numero"]
        linhas = linhas_validas((revisoes or {}).get(str(n)))
        da_folha = (lambda a: True) if f.get("solta") else (lambda a, n=n: a.get("prancha_numero") == n)
        velhas = [e.id for e in d.entidades.values() if (e.atributos or {}).get("campo") == CAMPO and da_folha(e.atributos or {})]
        if not linhas and not velhas:
            continue
        for i in velhas:
            d.remover(i)
        if linhas:
            larg, alt = FOLHAS[f["formato"]]
            papel = Desenho(nome="revisoes", escala=1.0)
            atr = {"prancha": "moldura"}
            if not f.get("solta"):
                atr.update(prancha_numero=n, folha=f["folha"], formato=f["formato"], escala=1.0)
            bx0, by0, bx1, by1 = desenhar_revisoes(papel, f["formato"], larg, alt, linhas, atr)
            ox, oy = f["origem"]
            for e in papel.entidades.values():
                d.add(transladar(e, ox, oy))
            caixa = (bx0 + ox, by0 + oy, bx1 + ox, by1 + oy)
            if any(_dentro(p, caixa) for e in d.entidades.values() if _do_desenho(e.atributos or {}, da_folha)
                   for p in e.pontos()):
                encostam.append(n)
        rev = ultima_revisao(linhas)
        for e in d.entidades.values():
            a = e.atributos or {}
            if isinstance(e, Texto) and a.get("campo") == "prancha" and da_folha(a) and rev:
                e.texto = _texto_da_prancha(e.texto, rev)
        mudou += 1
    return {"folhas": mudou, "encostam": encostam}


def _do_desenho(a: dict, da_folha) -> bool:
    """o conteúdo da folha (não a moldura nem o carimbo)"""
    return da_folha(a) and a.get("prancha") != "moldura" and a.get("campo") != CAMPO


def _dentro(p, caixa) -> bool:
    return caixa[0] < p[0] < caixa[2] and caixa[1] < p[1] < caixa[3]


def pranchas_do_projeto(g, s: str) -> List[dict]:
    """Os desenhos de pranchas do projeto e as folhas de cada um: [{desenho, numero, titulo}], pelo número."""
    out = []
    for item in g.listar_desenhos(s, contar=False):
        if not item.get("pranchas"):
            continue
        meta = (g.abrir_desenho(s, item["nome"]) or {}).get("metadados") or {}
        folhas = meta.get("pranchas") or ([meta["prancha"]] if meta.get("prancha") else [])
        for i, p in enumerate(folhas):
            out.append({"desenho": item["nome"], "numero": int(p.get("numero") or i + 1), "titulo": str(p.get("titulo") or "")})
    out.sort(key=lambda p: (p["numero"], p["desenho"]))
    return out


def gravar(g, s: str, revisoes: dict) -> dict:
    """Grava as revisões no projeto e põe as tabelas nos desenhos das pranchas. Devolve {revisoes, desenhos, encostam}."""
    p = g.ler(s)
    cp = dict(p.get("carimbo_pranchas") or {})
    cp["revisoes"] = {str(k): linhas_validas(v) for k, v in (revisoes or {}).items() if linhas_validas(v)}
    g.tocar(s, carimbo_pranchas=cp)
    feitos, encostam = [], []
    for nome in sorted({pr["desenho"] for pr in pranchas_do_projeto(g, s)}):
        d = Desenho.de_dict(g.abrir_desenho(s, nome))
        r = aplicar_no_desenho(d, cp["revisoes"])
        if r["folhas"]:
            g.salvar_desenho(s, nome, d.dict())
            feitos.append(nome)
            encostam += r["encostam"]
    return {"revisoes": cp["revisoes"], "desenhos": feitos, "encostam": sorted(set(encostam))}
