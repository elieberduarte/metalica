# -*- coding: utf-8 -*-
"""O padrão dos nomes do catálogo de peças (usuário, 27/10: "não temos uma padronização de nomes definida").

    from nucleo.nomes_catalogo import padrao
    padrao("TC 12,7×0,5")                  # "TC 12,7×0,50"
    padrao('L 1½"×1/8"')                   # 'L 1.1/2"×1/8"'

Combinado com o usuário (27/10):

* polegada com parte inteira escrita `1.1/4"` (como a Gerdau e os fornecedores; nada de `1½"`);
* a espessura — a última medida em mm — sempre com 2 casas: `TC 12,7×0,50`, `CH 2,00 mm`, `L 50×5,00`,
  `Ue 200×75×25×2,25`; os laminados W e HP com a massa em 1 casa (`W 610×101,0`);
* `(FF)` só no U e na cantoneira, onde o laminado e o dobrado convivem; sai o `(métrica)`;
* telha = modelo do fabricante + espessura + o fabricante curto: `TP 40 0,43 mm (Isoeste)`;
* ficam como estão: o nominal dos tubos (`TC 60,3×3,00 (2")`), a mistura polegada × mm dos dobrados
  (`L 1/2"×2,50 mm`), barras redondas e parafusos.

O nome antigo continua valendo: os geradores do catálogo guardam em `apelidos` o nome de antes, e a chave
de comparação (`numeros_iguais`) já trata `0,5` = `0,50`, `101` = `101,0` e `1½` = `1.1/2`. Assim as obras
gravadas com o nome antigo acham o mesmo item, sem regravar nada.
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = ["padrao", "fracoes", "numeros_iguais", "chave_de_perfil", "FABRICANTES_CURTOS"]

_GLIFOS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
           "⅓": "1/3", "⅔": "2/3"}

#: O fabricante da telha como ele aparece no nome (o nome completo fica em `fabricantes`).
FABRICANTES_CURTOS = {
    "Regional Telhas": "Regional", "Isoeste Metálica": "Isoeste", "ArcelorMittal Perfilor": "Perfilor",
    "Ananda Metais": "Ananda", "Eternit (telhas metálicas)": "Eternit",
}


def fracoes(s: str) -> str:
    """`1½"` → `1.1/2"` e `½"` → `1/2"`."""
    for g, t in _GLIFOS.items():
        s = re.sub(r"(\d)" + g, r"\1." + t, s)
        s = s.replace(g, t)
    return s


def numeros_iguais(chave: str) -> str:
    """Numa chave já com ponto decimal, o mesmo número escrito igual: `0.50` → `0.5`, `101.0` → `101`.

    O ponto de `1.1/4` (polegada) não é decimal e fica."""
    def tira(m):
        dec = m.group(2).rstrip("0")
        return m.group(1) + ("." + dec if dec else "")
    return re.sub(r"(\d+)\.(\d+)(?![\d/])", tira, chave)


def chave_de_perfil(texto: str) -> str:
    """O perfil para dizer se duas peças são a mesma: sem espaços, maiúsculo, e o nome antigo igual ao novo
    ("TQ 50×50×2,0" = "TQ 50×50×2,00") — numa obra antiga, a barra lançada depois com o nome novo não vira outra marca."""
    s = re.sub(r"\s+", "", fracoes(str(texto or ""))).upper()
    return numeros_iguais(s.replace(",", "."))


def _duas(txt: str) -> str:
    return ("%.2f" % float(txt.replace(",", "."))).replace(".", ",")


def _ultima_com_2_casas(s: str) -> str:
    """A última medida métrica do nome (a espessura) com 2 casas; a polegada não se toca."""
    ms = list(re.finditer(r"(?<![\d/.,])(\d+(?:,\d+)?)(?![\d/,\"])", s))
    if not ms:
        return s
    m = ms[-1]
    return s[:m.start()] + _duas(m.group(1)) + s[m.end():]


def _familia(nome: str) -> str:
    n = nome.strip()
    for pre, fam in (("Barra redonda", "barra_redonda"), ("Barra chata", "barra_chata"), ("CH ", "chapa"),
                     ("W ", "I"), ("HP ", "I"), ("I ", "I"), ("Ue ", "Ue"), ("Ze ", "Ze"), ("Z45 ", "Z45"),
                     ("Cr ", "Cr"), ("U ", "U"), ("L ", "L"), ("TC ", "tubo"), ("TQ ", "tubo"), ("TR ", "tubo")):
        if n.startswith(pre):
            return fam
    return ""


def _telha(nome: str, dados: dict) -> str:
    modelo = str(dados.get("modelo") or "").strip()
    fabs = dados.get("fabricantes") or []
    fab = str(fabs[0] if fabs else "").strip()
    if not modelo or not fab:
        return nome
    modelo = re.sub(r"^([A-Z]+)-?(\d)", r"\1 \2", modelo)
    t = dados.get("t")
    esp = " %s mm" % _duas(str(t)) if t else ""
    return "%s%s (%s)" % (modelo, esp, FABRICANTES_CURTOS.get(fab, fab))


def padrao(nome: str, familia: Optional[str] = None, dados: Optional[dict] = None) -> str:
    """O nome no padrão do catálogo; o que não é de nenhuma família conhecida volta como veio."""
    n = fracoes(str(nome or "").strip())
    f = familia or _familia(n)
    if f == "telha":
        return _telha(n, dados or {})
    if f == "I":
        if n.startswith(("W ", "HP ")):
            n = re.sub(r"×(\d+)$", r"×\1,0", n)
        return n
    if f == "U":
        return _ultima_com_2_casas(n) if "(FF)" in n else n        # o laminado em polegada leva a massa
    if f in ("Ue", "Ze", "Z45", "Cr"):
        return _ultima_com_2_casas(n)
    if f == "L":
        n = n.replace(" (métrica)", "")
        if '"' in n and "mm" not in n:
            return n                                                # toda em polegada
        base, suf = re.match(r"(.*?)((?: mm)?(?: \(FF\))?)$", n).groups()
        return _ultima_com_2_casas(base) + suf
    if f == "tubo":
        base, suf = re.match(r"(.*?)((?: \([^)]*\))?)$", n).groups()
        return _ultima_com_2_casas(base) + suf
    if f == "chapa":
        return re.sub(r"CH (\d+(?:,\d+)?) mm", lambda m: "CH " + _duas(m.group(1)) + " mm", n)
    return n
