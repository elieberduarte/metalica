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
    """Um item pelo nome, tolerante à grafia ("ue150x60x20x2,65")."""
    if isinstance(nome, Item):
        return nome
    _carregar()
    return _por_chave.get(_chave(nome))


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
