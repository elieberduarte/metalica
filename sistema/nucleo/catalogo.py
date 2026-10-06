# -*- coding: utf-8 -*-
"""Catálogo de peças: tudo que a fábrica pode comprar ou dobrar, num lugar só.

    from nucleo import catalogo
    catalogo.familias()                     # o que existe, para montar a tela
    catalogo.itens("Ue")                    # os U enrijecidos
    catalogo.buscar("150x60")               # busca livre, tolerante à grafia
    catalogo.item("Ue 150×60×20×2,65")      # um item
    catalogo.alternativas("Ue 150×60×20×2,65")   # o que dá para pôr no lugar

Junta duas fontes, sem repetir nada:

* `dados/perfis.json` — laminados W e HP, U em polegada, cantoneiras em polegada e tubos,
  com as propriedades das tabelas de fabricante (`dados/extrai_perfis.py`);
* `dados/catalogo.json` — séries formadas a frio (U e Ue), cantoneiras em milímetro,
  chapas, barras redondas e chatas e parafusos (`dados/gerar_catalogo.py`), mais os
  catálogos dos fornecedores (`dados/fornecedores/`: Gerdau, ArcelorMittal, Vallourec,
  Marcegaglia, Perfinasa, Perfilor, Isoeste, Tetraferro e as telhas). Os itens que vêm só
  dos fornecedores têm `fornecedor: True`: aparecem na consulta, na busca e na troca, mas o
  dimensionamento automático continua escolhendo nas séries padrão.

Quando o mesmo perfil aparece nas duas, vale o da tabela de fabricante.

**Unidades**: dimensões em mm; propriedades de seção em cm (A cm², I cm⁴, W cm³, r cm,
J cm⁴, Cw cm⁶); massa em kg/m, e em kg/m² nas chapas.

**Papéis** (`PAPEIS`) dizem para que serve cada família na estrutura — é o que permite
oferecer alternativas de troca sem misturar coisas que não se substituem (uma terça não
vira chumbador). A troca de perfil da análise usa `alternativas()` para levantar os
candidatos e depois verifica cada um com a norma; aqui não se decide nada de resistência,
só de geometria e disponibilidade.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .base import ErroDeDados
from .perfis import Perfil, banco

__all__ = ["Item", "itens", "item", "familias", "buscar", "alternativas", "perfil_de",
           "PAPEIS", "FAMILIAS", "resumo"]

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(BASE, "dados", "catalogo.json")

#: Rótulo e descrição de cada família, na ordem em que a tela mostra.
FAMILIAS: Dict[str, dict] = {
    "I": {"nome": "Perfis I laminados (W, HP, I)", "grupo": "laminado", "peca": "barra",
          "descricao": "vigas e pilares de alma cheia; a série W é a usual em galpões"},
    "U": {"nome": "Perfis U", "grupo": "laminado e formado a frio", "peca": "barra",
          "descricao": "terças, travessas, montantes e diagonais; em polegada (laminado) "
                       "ou dobrado da chapa (formado a frio)"},
    "Ue": {"nome": "Perfis U enrijecidos (Ue)", "grupo": "formado a frio", "peca": "barra",
           "descricao": "o perfil de terça e longarina; a aba dobrada segura a mesa"},
    "Ze": {"nome": "Perfis Z enrijecidos a 90°", "grupo": "formado a frio", "peca": "barra",
           "descricao": "terças e longarinas contínuas; um Z encaixa no outro no transpasse"},
    "Z45": {"nome": "Perfis Z enrijecidos a 45°", "grupo": "formado a frio", "peca": "barra",
            "descricao": "terças e longarinas contínuas, com transpasse"},
    "Cr": {"nome": "Perfis cartola", "grupo": "formado a frio", "peca": "barra",
           "descricao": "terças leves, travessas de fechamento, apoio de forro e de telha"},
    "L": {"nome": "Cantoneiras", "grupo": "laminado e formado a frio", "peca": "barra",
          "descricao": "diagonais, montantes, travamentos e agulhamento"},
    "tubo": {"nome": "Tubos estruturais", "grupo": "tubo", "peca": "barra",
             "descricao": "redondos, quadrados e retangulares; pilares e treliças aparentes"},
    "barra_redonda": {"nome": "Barras redondas", "grupo": "barra", "peca": "barra",
                      "descricao": "tirantes, contraventamentos e chumbadores"},
    "barra_chata": {"nome": "Barras chatas", "grupo": "barra", "peca": "barra",
                    "descricao": "travessas, enrijecedores e grades"},
    "chapa": {"nome": "Chapas", "grupo": "chapa", "peca": "chapa",
              "descricao": "chapas de topo, de base, gussets e chapinhas; massa por m²"},
    "parafuso": {"nome": "Parafusos", "grupo": "conector", "peca": "conector",
                 "descricao": "parafusos estruturais e comuns, com o furo padrão"},
    "telha": {"nome": "Telhas metálicas", "grupo": "telha", "peca": "telha",
              "descricao": "trapezoidais e onduladas; larguras total e útil e massa por m²"},
}

#: Famílias que se substituem de verdade na obra. Um Ue vira U (e o contrário), porque
#: são o mesmo perfil dobrado com ou sem aba; uma terça não vira cantoneira nem tirante,
#: mesmo compartilhando o papel "diagonal" em outra posição.
TROCA_COMPATIVEL: Dict[str, List[str]] = {
    "I": ["I"], "U": ["U", "Ue"], "Ue": ["Ue", "U"], "L": ["L"], "tubo": ["tubo"],
    "Ze": ["Ze", "Z45"], "Z45": ["Z45", "Ze"], "Cr": ["Cr"], "telha": ["telha"],
    "barra_redonda": ["barra_redonda"], "barra_chata": ["barra_chata"],
    "chapa": ["chapa"], "parafuso": ["parafuso"],
}

#: Faixa de altura de seção oferecida na troca, em relação à atual: de metade ao dobro.
#: Fora disso deixa de ser troca e vira outro projeto.
FAIXA_ALTURA = (0.5, 2.0)

#: Para que serve cada família na estrutura. A troca só oferece candidatos que dividem
#: papel com o perfil atual.
PAPEIS: Dict[str, List[str]] = {
    "I": ["viga", "pilar", "banzo"],
    "U": ["terça", "longarina", "banzo", "diagonal", "montante", "travessa"],
    "Ue": ["terça", "longarina", "banzo", "diagonal", "montante"],
    "Ze": ["terça", "longarina"],
    "Z45": ["terça", "longarina"],
    "Cr": ["terça", "travessa"],
    "telha": ["cobertura", "fechamento"],
    "L": ["diagonal", "montante", "travamento", "agulhamento"],
    "tubo": ["pilar", "banzo", "diagonal", "montante"],
    "barra_redonda": ["tirante", "contraventamento", "chumbador"],
    "barra_chata": ["travessa", "enrijecedor"],
    "chapa": ["chapa"],
    "parafuso": ["conector"],
}


@dataclass
class Item:
    """Uma peça do catálogo. `dados` guarda o registro cru da fonte."""
    nome: str
    familia: str
    grupo: str = ""
    origem: str = "tabela"          # "tabela" (fabricante) ou "calculado"
    massa: float = 0.0              # kg/m (barras) — 0 nas chapas
    massa_m2: float = 0.0           # kg/m² (chapas)
    uso: str = ""
    norma: str = ""
    dados: dict = field(default_factory=dict)

    # --- atalhos das propriedades mais pedidas (cm) ---
    @property
    def A(self) -> float:
        return float(self.dados.get("A") or 0.0)

    @property
    def Ix(self) -> float:
        return float(self.dados.get("Ix") or 0.0)

    @property
    def Wx(self) -> float:
        return float(self.dados.get("Wx") or 0.0)

    @property
    def rx(self) -> float:
        return float(self.dados.get("rx") or 0.0)

    @property
    def ry(self) -> float:
        return float(self.dados.get("ry") or 0.0)

    @property
    def altura(self) -> float:
        """Altura da seção em mm (diâmetro no tubo redondo e na barra redonda)."""
        d = self.dados
        return float(d.get("d") or d.get("D") or d.get("h") or d.get("b") or d.get("t") or 0.0)

    @property
    def espessura(self) -> float:
        d = self.dados
        return float(d.get("t") or d.get("tw") or 0.0)

    @property
    def papeis(self) -> List[str]:
        return PAPEIS.get(self.familia, [])

    @property
    def eh_barra(self) -> bool:
        return FAMILIAS.get(self.familia, {}).get("peca") == "barra"

    def dict(self) -> dict:
        """Registro para a interface (já com os rótulos prontos)."""
        return {
            "nome": self.nome, "familia": self.familia,
            "familia_nome": FAMILIAS.get(self.familia, {}).get("nome", self.familia),
            "grupo": self.grupo, "origem": self.origem,
            "massa": round(self.massa, 3) if self.massa else None,
            "massa_m2": round(self.massa_m2, 2) if self.massa_m2 else None,
            "altura": self.altura or None, "espessura": self.espessura or None,
            "A": self.A or None, "Ix": self.Ix or None, "Wx": self.Wx or None,
            "rx": self.rx or None, "ry": self.ry or None,
            "uso": self.uso, "norma": self.norma, "papeis": self.papeis,
            "dim": self.dados.get("dim") or "",
            "fabricantes": self.dados.get("fabricantes") or [],
            "fornecedor": bool(self.dados.get("fornecedor")),
            "tabela_fabricante": self.dados.get("tabela_fabricante") or None,
            "obs": self.dados.get("obs") or "",
            "sob_consulta": bool(self.dados.get("sob_consulta")),
            "so_massa": bool(self.dados.get("so_massa")),
            "largura_util": self.dados.get("largura_util"),
            "largura_total": self.dados.get("largura_total"),
        }


# =====================================================================================
# Carga
# =====================================================================================

_itens: Optional[List[Item]] = None
_por_chave: Dict[str, Item] = {}


#: Frações que aparecem nos nomes em polegada e não sobrevivem ao corte de acentos.
_FRACOES = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8",
            "⅞": "7/8", "⅓": "1/3", "⅔": "2/3"}


def _chave(nome: str) -> str:
    """Grafia única para comparar nomes.

    A ordem importa: `×` e as frações (½, ¾) têm de virar texto **antes** de tirar os
    acentos, senão somem — e aí "2½\"×1/4\"" e "2\"×1/4\"" viravam a mesma chave.
    """
    s = str(nome or "")
    for f, txt in _FRACOES.items():
        s = s.replace(f, txt)
    s = s.replace("×", "X").replace("Ø", "D").replace("ø", "D").replace(",", ".").replace('"', "")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_]+", "", s.upper())


def _familia_do_perfil(p: Perfil) -> str:
    if p.tipo == "I":
        return "I"
    if p.tipo in ("U", "Ue"):
        # o perfis.json guarda U formado a frio dentro do tipo "Ue"
        return "Ue" if p.nome.strip().upper().startswith("UE") else "U"
    return p.tipo


def _do_banco() -> List[Item]:
    """Os perfis tabelados de `dados/perfis.json`."""
    saida = []
    for tipo, lista in banco().por_tipo.items():
        for p in lista:
            fam = _familia_do_perfil(p)
            frio = "(FF)" in p.nome or p.nome.strip().upper().startswith("UE")
            saida.append(Item(
                nome=p.nome, familia=fam,
                grupo="formado a frio" if frio else FAMILIAS.get(fam, {}).get("grupo", tipo),
                origem="tabela", massa=float(p.massa or 0.0),
                uso=str(p.dados.get("uso") or ""),
                norma=str(p.dados.get("norma") or "tabela de fabricante (anexo do manual)"),
                dados=dict(p.dados)))
    return saida


_fabricantes_perfis: Dict[str, List[str]] = {}
_bitolas: List[dict] = []


def _do_arquivo() -> List[Item]:
    global _fabricantes_perfis, _bitolas
    if not os.path.exists(ARQUIVO):
        return []
    with open(ARQUIVO, encoding="utf-8") as f:
        dados = json.load(f)
    # quem fabrica os perfis do perfis.json (o gerador acha pelos catálogos)
    _fabricantes_perfis = {_chave(k): v for k, v in (dados.get("fabricantes_perfis") or {}).items()}
    _bitolas = list(dados.get("bitolas") or [])
    saida = []
    for reg in dados.get("itens", []):
        saida.append(Item(
            nome=reg["nome"], familia=reg.get("familia", ""), grupo=reg.get("grupo", ""),
            origem=reg.get("origem", "calculado"), massa=float(reg.get("massa") or 0.0),
            massa_m2=float(reg.get("massa_m2") or 0.0), uso=reg.get("uso", ""),
            norma=reg.get("norma", ""), dados=reg))
    return saida


def _carregar() -> List[Item]:
    global _itens, _por_chave
    if _itens is not None:
        return _itens
    todos = _do_banco()
    vistos = {_chave(i.nome) for i in todos}
    do_arquivo = _do_arquivo()
    for i in todos:
        fabs = _fabricantes_perfis.get(_chave(i.nome))
        if fabs:
            i.dados["fabricantes"] = list(fabs)
    for i in do_arquivo:
        if _chave(i.nome) in vistos:
            continue                      # o valor de tabela vence o calculado
        vistos.add(_chave(i.nome))
        todos.append(i)
    # ordem de exibição: família, depois altura e massa
    ordem = list(FAMILIAS)
    # sem massa (modelo de telha sem tabela publicada) vai para o fim da família
    todos.sort(key=lambda i: (ordem.index(i.familia) if i.familia in ordem else 99,
                              0 if (i.massa or i.massa_m2) else 1, i.altura, i.massa or i.massa_m2))
    _itens = todos
    _por_chave = {_chave(i.nome): i for i in todos}
    return _itens


def recarregar():
    """Esquece o catálogo em memória (usado pelos testes e depois de gerar de novo)."""
    global _itens, _por_chave
    _itens = None
    _por_chave = {}
    _DO_IFC.clear()


# =====================================================================================
# Consulta
# =====================================================================================

def itens(familia: Optional[str] = None, grupo: Optional[str] = None) -> List[Item]:
    """Itens do catálogo, todos ou de uma família ("Ue", "chapa"…)."""
    todos = _carregar()
    if familia:
        todos = [i for i in todos if i.familia == familia]
    if grupo:
        todos = [i for i in todos if grupo.lower() in (i.grupo or "").lower()]
    return todos


def item(nome) -> Optional[Item]:
    """Um item pelo nome, tolerante à grafia ("ue150x60x20x2,65").

    O perfil de cálculo de alguns itens leva a medida em mm no nome ("Barra redonda
    ø 1/2\" (12,7 mm)"), e é esse nome que o modelo 3D grava: sem achar o item de novo, a
    barra ficava fora do cálculo. O parêntese do fim só sai quando o nome inteiro não
    existe — "(FF)" faz parte do nome dos formados a frio."""
    if isinstance(nome, Item):
        return nome
    _carregar()
    it = _por_chave.get(_chave(nome))
    if it is None and isinstance(nome, str) and re.search(r"\([^()]*\)\s*$", nome):
        it = _por_chave.get(_chave(re.sub(r"\s*\([^()]*\)\s*$", "", nome)))
    return it


def familias() -> List[dict]:
    """Famílias com a contagem de itens — é o que a tela lista à esquerda."""
    saida = []
    for chave, meta in FAMILIAS.items():
        lista = itens(chave)
        if not lista:
            continue
        saida.append({
            "familia": chave, "nome": meta["nome"], "grupo": meta["grupo"],
            "peca": meta["peca"], "descricao": meta["descricao"],
            "itens": len(lista), "papeis": PAPEIS.get(chave, []),
            "alturas": sorted({round(i.altura) for i in lista if i.altura}),
        })
    return saida


def bitolas() -> List[dict]:
    """Bitolas de chapa dos fornecedores (#14 etc.) com a espessura em mm. A mesma bitola
    tem mais de uma espessura: laminada a quente, a frio ou zincada."""
    _carregar()
    return list(_bitolas)


def espessuras_da_bitola(bitola: str) -> List[float]:
    """Espessuras (mm) que a bitola "#14" pode ser, da tabela dos fornecedores."""
    num = re.sub(r"[^0-9]", "", str(bitola))
    return sorted({float(b["t_mm"]) for b in bitolas()
                   if re.sub(r"[^0-9]", "", str(b.get("bitola", ""))) == num
                   and str(b.get("bitola", "")).startswith("#")})


#: Apelidos da fábrica na busca: "BR 3/8" é a barra redonda, "BC" a chata.
_APELIDOS = [(r"^BR(?=[0-9])", "BARRAREDONDAD"), (r"^BC(?=[0-9])", "BARRACHATA")]


def buscar(texto: str, familia: Optional[str] = None, limite: int = 60) -> List[Item]:
    """Busca livre pelo nome e pelas dimensões ("150x60", "W 310", "3/8").

    Entende a bitola no lugar da espessura ("127x50x17x#14" acha as de 1,90, 1,95 e 2,00
    mm) e os apelidos BR/BC das barras."""
    alvo = _chave(texto)
    if not alvo:
        return itens(familia)[:limite]
    alvos = [alvo]
    for padrao, troca in _APELIDOS:
        if re.search(padrao, alvo):
            alvos.append(re.sub(padrao, troca, alvo))
    m = re.search(r"X?#(\d+)", alvo)
    if m:
        alvos = [a.replace(m.group(0), "X%.2f" % t) for a in alvos
                 for t in espessuras_da_bitola(m.group(1))] or alvos
    saida = [i for i in itens(familia)
             if any(a in _chave(i.nome) or a in _chave(i.dados.get("dim", "")) for a in alvos)]
    return saida[:limite]


def perfil_de(nome) -> Optional[Perfil]:
    """`Perfil` de cálculo do item (para as verificações da NBR 8800 e da NBR 14762).

    Os tabelados saem do catálogo de perfis; os calculados são montados na hora pelo
    mesmo caminho do nome de fábrica (`nucleo/perfis_fabrica.py`)."""
    it = item(nome)
    if it is None:
        # nome de fábrica fora do catálogo (U92X40X2.25, L1.1/4"X1/8"): monta na hora
        from . import perfis_fabrica
        try:
            return perfis_fabrica.perfil_de_fabrica(str(nome))
        except Exception:
            return None
    if not it.eh_barra:
        return None
    p = banco().get(it.nome)
    if p is not None:
        return p
    from . import perfis_fabrica
    d = it.dados
    try:
        if it.familia in ("U", "Ue") and d.get("d") and d.get("bf"):
            if d.get("enrijecedor"):
                return perfis_fabrica.perfil_ue_frio(d["d"], d["bf"], d["enrijecedor"], d["t"])
            return perfis_fabrica.perfil_u_frio(d["d"], d["bf"], d["t"])
        if it.familia == "L" and d.get("b"):
            return perfis_fabrica.perfil_cantoneira(d["b"], d.get("b2") or d["b"], d["t"])
        if it.familia == "barra_redonda" and d.get("d"):
            from nucleo3d import geometria
            return geometria.barra_redonda(d["d"], it.nome)
        if it.familia == "barra_chata" and d.get("b"):
            from nucleo3d import geometria
            return geometria.barra_chata(d["b"], d["t"], it.nome)
        # laminados e tubos dos fornecedores: a tabela já traz as propriedades
        if it.familia in ("I", "U", "tubo") and d.get("A") and d.get("Ix") and d.get("Iy"):
            return Perfil(nome=it.nome, tipo=it.familia, dados=dict(d))
    except Exception:
        return None
    return None


# =====================================================================================
# Nome que vem do IFC
# =====================================================================================

def nome_do_ifc(nome) -> str:
    """O tipo do perfil no nome que o IFC traz, sem a família e sem o ID da peça.

    O Revit grava "Família:Tipo:ID" em cada peça ("CRV - Cortes retangulares vazados (sem
    emenda):RHS 127x76.2x6.35:6474177"): o ID é da peça, então cada barra saía como um
    perfil diferente no resumo (Bella Casa, 06/10). Nome sem ":" fica como está."""
    s = re.sub(r"\s+", " ", str(nome or "")).strip()
    if ":" not in s:
        return s
    s = re.sub(r":\s*\d+\s*$", "", s)
    return s.rsplit(":", 1)[-1].strip() or s


_NUM = r"(\d+(?:[.,]\d+)?)"
_X = r"\s*[X×]\s*"


def _medidas(nome: str):
    """(forma, medidas) pelo nome: ("I", (W|HP, d, kg/m)), ("redondo", (D, t)),
    ("retangular", (h, b, t)) com h ≥ b, ("L", (b1, b2, t)). None se não for um desses."""
    s = re.sub(r"\s+", " ", str(nome or "")).strip().upper().replace("Ø", "").replace(",", ".")
    f = float
    m = re.match(r"^(W|HP) ?" + _NUM + _X + _NUM + r"$", s)
    if m:
        return "I", (m.group(1), f(m.group(2)), f(m.group(3)))
    m = re.match(r"^(?:CHS|TC|TUBO REDONDO) ?" + _NUM + _X + _NUM + r"$", s)
    if m:
        return "redondo", (f(m.group(1)), f(m.group(2)))
    # a forma também vem no fim: "250x250x10SHS", "406.4x12.5CHS" (a Passarela Mirante do Revit, 06/10)
    m = re.match(r"^" + _NUM + _X + _NUM + r" ?(?:CHS|TC)$", s)
    if m:
        return "redondo", (f(m.group(1)), f(m.group(2)))
    m = (re.match(r"^(?:SHS|RHS|TQ|TR) ?" + _NUM + _X + _NUM + _X + _NUM + r"$", s)
         or re.match(r"^" + _NUM + _X + _NUM + _X + _NUM + r" ?(?:SHS|RHS|TQ|TR)$", s))
    if m:
        h, b = sorted((f(m.group(1)), f(m.group(2))), reverse=True)
        return "retangular", (h, b, f(m.group(3)))
    m = re.match(r"^L ?" + _NUM + _X + _NUM + r"(?:" + _X + _NUM + r")?$", s)
    if m:
        if m.group(3):
            b1, b2 = sorted((f(m.group(1)), f(m.group(2))), reverse=True)
            return "L", (b1, b2, f(m.group(3)))
        return "L", (f(m.group(1)), f(m.group(1)), f(m.group(2)))
    return None


def _medidas_do_item(it: Item):
    d = it.dados
    try:
        if it.familia == "I":
            return _medidas(it.nome)
        if it.familia == "tubo" and d.get("tipo") == "redondo":
            return "redondo", (float(d["D"]), float(d["t"]))
        if it.familia == "tubo" and d.get("b") and d.get("h"):
            h, b = sorted((float(d["h"]), float(d["b"])), reverse=True)
            return "retangular", (h, b, float(d["t"]))
        if it.familia == "L" and d.get("b") and d.get("t"):
            b1, b2 = sorted((float(d["b"]), float(d.get("b2") or d["b"])), reverse=True)
            return "L", (b1, b2, float(d["t"]))
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _area_pelas_medidas(forma: str, med) -> float:
    """Área da seção (mm²) pelas medidas nominais: tubo retangular com os cantos da
    EN 10219 (raio externo 2t, interno t), cantoneira de cantos vivos."""
    if forma == "redondo":
        D, t = med
        return math.pi * t * (D - t)
    if forma == "retangular":
        h, b, t = med
        return 2 * t * (h + b - 2 * t) - (4 - math.pi) * 3 * t * t
    if forma == "L":
        b1, b2, t = med
        return t * (b1 + b2 - t)
    return 0.0


def _mesma_medida(forma: str, a, b) -> bool:
    if forma == "I":
        return a[0] == b[0] and abs(a[1] - b[1]) <= 0.5 and abs(a[2] - b[2]) <= 0.11
    *lados_a, ta = a
    *lados_b, tb = b
    # 76,2 (3") do IFC é o 76 do catálogo; 6,35 (1/4") é o 6,3
    return abs(ta - tb) <= 0.1 and all(abs(x - y) <= max(1.0, 0.01 * x) for x, y in zip(lados_a, lados_b))


_DO_IFC: Dict[str, Optional[dict]] = {}


def do_ifc(nome) -> Optional[dict]:
    """O perfil do IFC cruzado com o catálogo (06/10, Bella Casa).

    {"ifc": o tipo no IFC ("RHS 127x76.2x6.35"), "item": o Item do catálogo ou None,
    "catalogo": o nome no catálogo ("TR 127×76×6,3") ou "", "kg_m", "area_mm2",
    "fonte": "catálogo" | "calculado"}. Fora do catálogo, o kg/m sai da área pelas
    medidas do nome (tubos e cantoneiras); None quando não há como."""
    chave = str(nome or "")
    if chave in _DO_IFC:
        return _DO_IFC[chave]
    tipo = nome_do_ifc(nome)
    it = item(tipo)
    med = _medidas(tipo)
    if it is None and med is not None:
        fam = {"I": "I", "redondo": "tubo", "retangular": "tubo", "L": "L"}[med[0]]
        candidatos = []
        for c in itens(fam):
            mc = _medidas_do_item(c)
            if mc is not None and mc[0] == med[0] and _mesma_medida(med[0], med[1], mc[1]) and c.massa:
                dif = 0.0 if med[0] == "I" else sum(abs(x - y) for x, y in zip(med[1], mc[1]))
                candidatos.append((dif, 0 if c.origem == "tabela" else 1, c.nome, c))
        if candidatos:
            it = min(candidatos, key=lambda x: x[:3])[3]
    r = None
    if it is not None and it.massa and it.eh_barra:
        area = it.A * 100.0 if it.A else (_area_pelas_medidas(*med) if med else it.massa / 7.85e-3)
        r = {"ifc": tipo, "item": it, "catalogo": it.nome, "kg_m": float(it.massa), "area_mm2": area, "fonte": "catálogo"}
    elif med is not None and med[0] != "I":
        area = _area_pelas_medidas(*med)
        if area > 0:
            r = {"ifc": tipo, "item": None, "catalogo": "", "kg_m": area * 7.85e-3, "area_mm2": area, "fonte": "calculado"}
            # o tubo fora do catálogo vai para o similar dele (06/10): a geometria e o comprimento continuam os do
            # projeto (`area_mm2`, `secao`); o nome de compra e o kg/m passam a ser os do similar
            sim = similar(med)
            if sim is not None:
                r.update(item=sim, catalogo=sim.nome, kg_m=float(sim.massa), fonte="similar")
    if r is not None:
        r["secao"] = _contorno_nominal(it, med)
    _DO_IFC[chave] = r
    return r


def _propriedades_tubo(forma: str, med) -> Optional[tuple]:
    """(A cm², Ix cm⁴, Iy cm⁴) do tubo pelas medidas; o retangular com os cantos da EN 10219 (raio externo 2t,
    interno t), pelo contorno arredondado — confere com a tabela da Marcegaglia e a 1 % da Vallourec."""
    if forma == "redondo":
        D, t = med
        A = math.pi * t * (D - t) / 100.0
        I = math.pi / 64.0 * (D ** 4 - (D - 2 * t) ** 4) / 1e4
        return A, I, I
    if forma != "retangular":
        return None
    h, b, t = med

    def contorno(hh, bb, r, n=12):
        pts = []
        for cx, cy, a0 in ((bb / 2 - r, hh / 2 - r, 0), (-bb / 2 + r, hh / 2 - r, 90), (-bb / 2 + r, -hh / 2 + r, 180),
                           (bb / 2 - r, -hh / 2 + r, 270)):
            for k in range(n + 1):
                a = math.radians(a0 + 90.0 * k / n)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    def props(pts):
        A = Ix = Iy = 0.0
        for i in range(len(pts)):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
            c = x1 * y2 - x2 * y1
            A += c / 2
            Ix += (y1 * y1 + y1 * y2 + y2 * y2) * c / 12
            Iy += (x1 * x1 + x1 * x2 + x2 * x2) * c / 12
        return A, Ix, Iy
    if h <= 2 * t or b <= 2 * t:
        return None
    fora, dentro = props(contorno(h, b, 2 * t)), props(contorno(h - 2 * t, b - 2 * t, t))
    return (fora[0] - dentro[0]) / 100.0, (fora[1] - dentro[1]) / 1e4, (fora[2] - dentro[2]) / 1e4


#: Quanto cada lado do similar pode diferir do tubo do projeto: primeiro até 5 %; sem nenhum, até 12 %.
FAIXAS_SIMILAR = (0.05, 0.12)


def similar(med) -> Optional[Item]:
    """O tubo do catálogo que faz as vezes do tubo do projeto fora dele (06/10, Bella Casa: SHS 225x225x6.4 →
    TQ 220×220×7,1; SHS 110x110x3.2 → TQ 110×110×3,35; RHS 127x63.5x3.2 → TR 130×70×3,0): a mesma forma, os lados
    até 5 % diferentes (senão até 12 %), área e inércias pelo menos as do projeto (1 % de folga: as tabelas
    arredondam) e, desses, o mais leve. None quando nada serve (o CHS 406,4: o maior redondo é o Ø355,6)."""
    if not med or med[0] not in ("redondo", "retangular"):
        return None
    forma, m = med
    alvo = _propriedades_tubo(forma, m)
    if alvo is None:
        return None
    lados = m[:-1]
    for faixa in FAIXAS_SIMILAR:
        bons = []
        for c in itens("tubo"):
            mc = _medidas_do_item(c)
            if mc is None or mc[0] != forma or not c.massa:
                continue
            if any(abs(x - y) > faixa * y for x, y in zip(mc[1][:-1], lados)):
                continue
            p = _propriedades_tubo(forma, mc[1])
            if p and all(a >= 0.99 * b for a, b in zip(p, alvo)):
                bons.append((float(c.massa), sum(abs(x - y) for x, y in zip(mc[1], m)), c.nome, c))
        if bons:
            return min(bons, key=lambda x: x[:3])[3]
    return None


def _propriedades(forma: str, med, it: Optional[Item] = None) -> Optional[tuple]:
    """(A cm², Ix cm⁴, Iy cm⁴): do tubo pelas medidas; do laminado pela tabela do item."""
    if forma in ("redondo", "retangular"):
        return _propriedades_tubo(forma, med)
    if it is not None and it.A and it.Ix:
        return it.A, it.Ix, float(it.dados.get("Iy") or 0.0)
    return None


def parecidos(nome, limite: int = 40) -> Optional[dict]:
    """Os itens do catálogo parecidos com o perfil do projeto, para a troca na compra (06/10): a mesma forma, os lados
    até 25 % diferentes, cada um com o kg/m, a área, as inércias e se atende (área e inércias pelo menos as do perfil
    do projeto, 1 % de folga); os que atendem primeiro, do mais leve ao mais pesado. None se o perfil não tem forma
    reconhecida (o nome não diz as medidas)."""
    tipo = nome_do_ifc(nome)
    med = _medidas(tipo)
    base = item(tipo)
    if med is None and base is not None:
        med = _medidas_do_item(base)
    if med is None:
        return None
    forma, m = med
    cat = do_ifc(nome) or {}
    if base is None and forma == "I":
        base = cat.get("item")
    alvo = _propriedades(forma, m, base)
    if forma == "I":
        if base is None:
            return None
        d = base.dados
        lados = (float(d.get("d") or 0.0), float(d.get("bf") or 0.0))
    else:
        lados = tuple(m[:-1])
    fam = {"I": "I", "redondo": "tubo", "retangular": "tubo", "L": "L"}[forma]
    itens_ = []
    for c in itens(fam):
        mc = _medidas_do_item(c)
        if mc is None or mc[0] != forma or not c.massa:
            continue
        if forma == "I":
            lc = (float(c.dados.get("d") or 0.0), float(c.dados.get("bf") or 0.0))
            if not all(lc):
                continue
        else:
            lc = tuple(mc[1][:-1])
        if any(abs(x - y) > 0.25 * y for x, y in zip(lc, lados)):
            continue
        p = _propriedades(forma, mc[1], c)
        atende = bool(p and alvo and all(a >= 0.99 * b for a, b in zip(p, alvo) if b))
        itens_.append({"nome": c.nome, "kg_m": round(float(c.massa), 3),
                       "A": round(p[0], 2) if p else None, "Ix": round(p[1], 1) if p else None, "Iy": round(p[2], 1) if p else None,
                       "atende": atende, "fabricante": ", ".join((c.dados.get("fabricantes") or [])[:2]),
                       "_ordem": (not atende, float(c.massa), sum(abs(x - y) for x, y in zip(lc, lados)))})
    itens_.sort(key=lambda x: x["_ordem"])
    for x in itens_:
        x.pop("_ordem")
    return {"ifc": tipo, "automatico": cat.get("catalogo") or "", "fonte": cat.get("fonte") or "",
            "projeto": {"A": round(alvo[0], 2), "Ix": round(alvo[1], 1), "Iy": round(alvo[2], 1)} if alvo else None,
            "itens": itens_[:limite]}


def _contorno_nominal(it: Optional[Item], med) -> Optional[tuple]:
    """(maior, menor) lado da caixa da seção em mm: altura × largura das mesas do W, os
    lados do tubo e da cantoneira, o diâmetro do tubo redondo duas vezes."""
    if med is not None and med[0] == "redondo":
        return (med[1][0], med[1][0])
    if med is not None and med[0] in ("retangular", "L"):
        return (med[1][0], med[1][1])
    d = (it.dados if it is not None else {}) or {}
    try:
        if d.get("d") and d.get("bf"):
            return tuple(sorted((float(d["d"]), float(d["bf"])), reverse=True))
    except (TypeError, ValueError):
        return None
    return None


# =====================================================================================
# Alternativas de troca
# =====================================================================================

def alternativas(nome, *, familias_extras: Sequence[str] = (), altura_min: float = 0.0,
                 altura_max: float = 0.0, massa_max: float = 0.0,
                 mesma_altura: bool = False, modo: str = "vizinhos",
                 limite: int = 40) -> List[dict]:
    """Candidatos para pôr no lugar de `nome`, do mais leve ao mais pesado.

    Só entra quem divide papel com o perfil atual (uma terça Ue pode virar U ou Ue; um
    tirante redondo só vira outro redondo). Cada candidato vem com a diferença de massa
    por metro — o impacto no peso da estrutura quem calcula é quem sabe o comprimento
    total da posição.

    `mesma_altura` limita aos de mesma altura de seção (troca sem mexer no desenho);
    `altura_min`/`altura_max` e `massa_max` são filtros diretos. `modo="vizinhos"` (o
    padrão) devolve os mais próximos em massa, metade abaixo e metade acima; `"todos"`
    devolve do mais leve ao mais pesado.
    """
    atual = item(nome)
    if atual is None:
        raise ErroDeDados("peça fora do catálogo: %s" % nome)
    familias_ok = set(TROCA_COMPATIVEL.get(atual.familia, [atual.familia])) | set(familias_extras)
    # sem faixa pedida, a altura da seção fica entre metade e o dobro da atual
    if not (altura_min or altura_max) and atual.altura:
        altura_min = altura_min or atual.altura * FAIXA_ALTURA[0]
        altura_max = altura_max or atual.altura * FAIXA_ALTURA[1]
    saida = []
    for c in _carregar():
        if c.familia not in familias_ok or c.nome == atual.nome:
            continue
        if FAMILIAS.get(c.familia, {}).get("peca") != FAMILIAS.get(atual.familia, {}).get("peca"):
            continue
        if mesma_altura and atual.altura and abs(c.altura - atual.altura) > 1.0:
            continue
        if altura_min and c.altura < altura_min - 0.5:
            continue
        if altura_max and c.altura > altura_max + 0.5:
            continue
        if massa_max and c.massa > massa_max:
            continue
        saida.append(c)
    saida.sort(key=lambda c: (c.massa or c.massa_m2, c.altura))
    base = atual.massa or atual.massa_m2 or 0.0
    if modo == "vizinhos" and base:
        # Metade mais leves e metade mais pesados, os mais próximos do atual: é assim que
        # a pergunta costuma vir ("tem algo um pouco mais leve que isto?"). A lista do
        # mais leve para o mais pesado, começando pelo mínimo do catálogo, não ajuda.
        leves = [c for c in saida if (c.massa or c.massa_m2) < base]
        pesados = [c for c in saida if (c.massa or c.massa_m2) >= base]
        n = max(limite // 2, 1)
        saida = leves[-n:] + pesados[:limite - min(len(leves), n)]
    fora = []
    for c in saida[:limite]:
        m = c.massa or c.massa_m2
        reg = c.dict()
        reg["massa_atual"] = round(base, 3) if base else None
        reg["delta_massa"] = round(m - base, 3) if base else None
        reg["delta_pct"] = round((m - base) / base * 100.0, 1) if base else None
        reg["mais_leve"] = bool(base and m < base)
        fora.append(reg)
    return fora


def resumo() -> dict:
    """Quantos itens, por família e por origem — para a tela e para os testes."""
    todos = _carregar()
    por_familia = {}
    por_origem = {}
    for i in todos:
        por_familia[i.familia] = por_familia.get(i.familia, 0) + 1
        por_origem[i.origem] = por_origem.get(i.origem, 0) + 1
    return {"itens": len(todos), "familias": por_familia, "origens": por_origem}
