# -*- coding: utf-8 -*-
"""Resumo de orçamento da obra: as quantidades da lista de materiais com os preços da tabela da
fábrica, no formato do resumo que a equipe monta à mão (o "R00_RESUMO" do Barracão BYD).

O fluxo da fábrica (03/10/2026): a equipe levanta os quantitativos (aço, acessórios, telhas…), põe
numa planilha com o valor de mercado da tabela de preços, e o dono preenche à mão os valores de
fechamento da proposta comercial. Aqui as duas primeiras etapas saem sozinhas:

* **tabela de preços** — a planilha da empresa (``Tabela de precos <EMPRESA> V<n> <data>.xlsx``) em
  ``<dados>/fabrica/precos/``; vale a mais nova. Lida direto do .xlsx (sem openpyxl). As linhas com
  CHAVE são as que o gerador usa por nome; parafusos, porcas, arruelas e chapas são achados pela
  especificação (diâmetro × comprimento × classe; faixa de espessura).
* **linhas do resumo** — da lista de materiais (``saida/lista_producao.py``): cada posição de aço vai
  para a linha de preço dela (chapa, Ø e L, U padrão MVAL fino/grosso, U fora do comprimento padrão,
  W, U fora padrão, L dobrada, cartola, tubo), telhas por metro linear, cumeeira por peça, rufos e
  calhas por kg, parafusos por classe e diâmetro, porcas e arruelas soltas.
* **o que é do dono** (fabricação, montagem, frete, impostos, comissão…) — linhas em branco, que a tela
  deixa preencher, e as colunas de fechamento (valor e total) ao lado das da tabela.

As edições (quantidade ou preço trocado, linha acrescentada, fechamento, cabeçalho, notas) ficam em
``<projeto>/orcamento/orcamento.json`` e o documento em ``resumo-de-orcamento.html/.pdf`` e ``.csv``.

Regras de classificação adotadas (A CONFERIR com o usuário; ficam escritas no documento):

* U/Ue dobrado com espessura 2,00/2,25/2,65/3,00/4,75 mm é **U padrão MVAL**; outra espessura é **U
  fora padrão** (Perfyaço) — como o U200×50#3,75 do BYD.
* A MVAL entrega o padrão em barras de 4,80 a 6,40 m. Terça com comprimento fora dessa faixa, e
  qualquer peça acima de 6,40 m, vai pelo preço "menor 4,80 m / maior 6,40 m" (as linhas "Terça" do
  BYD); as demais peças saem de barras e ficam no preço normal.
* Peso teórico da lista (o padrão da fábrica), sem perda de corte — o acréscimo, se houver, é do dono.
"""
import csv
import html
import json
import os
import re
import zipfile
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

PASTA_TABELAS = os.path.join("fabrica", "precos")
PASTA_ORCAMENTO = "orcamento"
ARQ_EDICOES = "orcamento.json"
ARQ_HTML = "resumo-de-orcamento.html"
ARQ_PDF = "resumo-de-orcamento.pdf"
ARQ_CSV = "resumo-de-orcamento.csv"

#: Cotação mais velha que isto (dias) aparece como aviso.
DIAS_COTACAO = 60
#: Espessuras (mm) da série padrão MVAL ("2,00 e 2,25" e "2,65/3,00 e 4,75" na tabela).
MVAL_FINO = (2.00, 2.25)
MVAL_GROSSO = (2.65, 3.00, 4.75)
#: Faixa de comprimento (mm) das barras padrão da MVAL.
BARRA_MIN, BARRA_MAX = 4800.0, 6400.0

_X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


# ============================================================ números

def _f(x) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(str(x).replace(",", ".")) if not isinstance(x, (int, float)) else float(x)
    except ValueError:
        return None


def br(x, casas: int = 2) -> str:
    """12.345,67 — vazio para None."""
    if x is None or x == "":
        return ""
    s = "{:,.{c}f}".format(float(x), c=casas)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""))


# ============================================================ tabela de preços

def _ler_xlsx(caminho: str) -> List[Tuple[int, Dict[str, str]]]:
    """Linhas da primeira aba: [(nº da linha, {coluna: texto})]. Lê o XML do .xlsx direto."""
    try:
        z = zipfile.ZipFile(caminho)
    except zipfile.BadZipFile:
        raise ValueError("o arquivo não é uma planilha .xlsx (salve no Excel como \"Pasta de Trabalho do Excel\")")
    nomes = set(z.namelist())
    ss: List[str] = []
    if "xl/sharedStrings.xml" in nomes:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("{%s}si" % _X):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % _X)))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    folha = wb.find("{%s}sheets" % _X)[0]
    alvo = rels[folha.get("{%s}id" % _R)].lstrip("/")
    if not alvo.startswith("xl/"):
        alvo = "xl/" + alvo
    linhas = []
    for row in ET.fromstring(z.read(alvo)).iter("{%s}row" % _X):
        d = {}
        for c in row.findall("{%s}c" % _X):
            v = c.find("{%s}v" % _X)
            t = c.get("t")
            col = "".join(ch for ch in c.get("r", "") if ch.isalpha())
            if t == "s" and v is not None:
                d[col] = ss[int(v.text)]
            elif t == "inlineStr":
                d[col] = "".join(x.text or "" for x in c.iter("{%s}t" % _X))
            elif v is not None and v.text is not None:
                d[col] = v.text
        if d:
            linhas.append((int(row.get("r") or 0), d))
    return linhas


def _data_excel(v) -> str:
    """'08/09/2026' (texto) ou número de série do Excel → 'dd/mm/aaaa'."""
    if v is None:
        return ""
    s = str(v).strip()
    if re.match(r"^\d{4,5}(\.0+)?$", s):
        try:
            return date.fromordinal(date(1899, 12, 30).toordinal() + int(float(s))).strftime("%d/%m/%Y")
        except ValueError:
            return s
    return s


def ler_tabela(caminho: str) -> dict:
    """A tabela de preços da empresa: {"arquivo", "titulo", "itens": [{chave, categoria, item,
    fornecedor, un, preco, data, situacao, fonte, linha}]}. O cabeçalho é a linha com "CHAVE"."""
    linhas = _ler_xlsx(caminho)
    cab_i = None
    cols: Dict[str, str] = {}
    titulo = []
    for i, (r, d) in enumerate(linhas):
        if any(str(v).strip().upper().startswith("CHAVE") for v in d.values()):
            cab_i = i
            for col, v in d.items():
                k = re.sub(r"\s+", " ", str(v)).strip().upper()
                for nome, prefixo in (("chave", "CHAVE"), ("categoria", "CATEGORIA"), ("item", "ITEM"), ("fornecedor", "FORNECEDOR"),
                                      ("un", "UN"), ("preco", "PREÇO"), ("data", "DATA"), ("validade", "VALIDADE"),
                                      ("situacao", "SITUAÇÃO"), ("fonte", "FONTE")):
                    if k.startswith(prefixo) and nome not in cols.values():
                        cols[col] = nome
                        break
            break
        titulo.append(" ".join(str(v) for v in d.values()))
    if cab_i is None:
        raise ValueError("a planilha não tem a linha de cabeçalho com a coluna CHAVE")
    itens = []
    for r, d in linhas[cab_i + 1:]:
        it = {nome: str(d.get(col, "") or "").strip() for col, nome in cols.items()}
        preco = _f(it.get("preco"))
        if preco is None or not it.get("item"):
            continue                                   # título de grupo ("PERFIS") ou linha vazia
        it["preco"] = round(preco, 4)
        it["data"] = _data_excel(it.get("data"))
        it["linha"] = r
        itens.append(it)
    return {"arquivo": os.path.basename(caminho), "caminho": caminho, "titulo": " · ".join(t for t in titulo[:2] if t).strip(),
            "itens": itens}


def tabela_vigente(dados: str) -> Optional[str]:
    """A planilha de preços mais nova em <dados>/fabrica/precos/ (pela data de alteração)."""
    pasta = os.path.join(dados, PASTA_TABELAS)
    try:
        cands = [os.path.join(pasta, n) for n in os.listdir(pasta) if n.lower().endswith(".xlsx") and not n.startswith("~$")]
    except OSError:
        return None
    return max(cands, key=os.path.getmtime) if cands else None


def guardar_tabela(dados: str, nome: str, conteudo: bytes) -> str:
    """Grava uma planilha nova em <dados>/fabrica/precos/ (confere que ela se lê antes)."""
    pasta = os.path.join(dados, PASTA_TABELAS)
    os.makedirs(pasta, exist_ok=True)
    nome = os.path.basename(nome or "Tabela de precos.xlsx")
    if not nome.lower().endswith(".xlsx"):
        raise ValueError("a tabela de preços tem de ser uma planilha .xlsx")
    destino = os.path.join(pasta, nome)
    tmp = destino + ".parcial"
    with open(tmp, "wb") as f:
        f.write(conteudo)
    try:
        ler_tabela(tmp)
    except Exception:
        os.remove(tmp)
        raise
    os.replace(tmp, destino)
    os.utime(destino, None)                    # passa a ser a vigente
    return destino


class Precos:
    """Busca na tabela: por chave, por texto, parafuso, porca, arruela e chapa por espessura."""

    def __init__(self, tabela: Optional[dict]):
        self.tabela = tabela or {"itens": []}
        self.itens = list(self.tabela.get("itens") or [])
        self.por_chave = {it["chave"]: it for it in self.itens if it.get("chave")}

    def chave(self, k: str) -> Optional[dict]:
        return self.por_chave.get(k)

    def texto(self, *padroes: str, categoria: str = "") -> Optional[dict]:
        """A primeira linha cujo item casa com todos os padrões (regex, sem diferenciar maiúsculas)."""
        for it in self.itens:
            if categoria and not it.get("categoria", "").upper().startswith(categoria.upper()):
                continue
            if all(re.search(p, it["item"], re.I) for p in padroes):
                return it
        return None

    def chapa(self, t: float) -> Optional[dict]:
        """Chapa de aço pela faixa de espessura ("CHAPA MVAL - 3,75 à 12,50mm"); a linha com chave primeiro."""
        cands = []
        for it in self.itens:
            if not it.get("categoria", "").upper().startswith("CHAPA"):
                continue
            m = re.search(r"(\d+[.,]\d+)\s*[àa]\s*(\d+[.,]\d+)\s*mm", it["item"], re.I)
            if not m or re.search(r"GALVAL|PR[ÉE]-?PINT", it["item"], re.I):
                continue
            a, b = _f(m.group(1)), _f(m.group(2))
            # a faixa é nominal: a chapa de 1/2" (12,7 mm, 13 no modelo) é a "até 12,50" do comércio
            if a - 0.06 <= t <= b + 0.6:
                cands.append((0 if it.get("chave") else 1, 0 if "MVAL" in it["item"].upper() else 1, it))
        return min(cands, key=lambda c: c[:2])[2] if cands else None

    def _parafusos(self):
        for it in self.itens:
            m = re.match(r"\s*PARAFUSO\s+(\d+(?:/\d+)?)\"?\s*x\s*([\d./]+)\"?", it["item"], re.I)
            if m:
                yield it, _pol(m.group(1)), _pol(m.group(2))

    def parafuso(self, d_pol: float, L_mm: float, classe: str, galv_fogo: bool = False) -> Optional[dict]:
        """O parafuso completo do diâmetro (pol.) e classe, no menor comprimento que não fica curto."""
        cands = []
        for it, d, L in self._parafusos():
            if abs(d - d_pol) > 1e-6 or classe.upper() not in it["item"].upper().replace(" ", ""):
                continue
            fogo = bool(re.search(r"G\.?\s*F", it["item"], re.I))
            if fogo != galv_fogo:
                continue
            cands.append((L * 25.4, it))
        if not cands:
            return None
        servem = [c for c in cands if c[0] >= L_mm - 2.0]
        return (min(servem, key=lambda c: c[0]) if servem else max(cands, key=lambda c: c[0]))[1]

    def porca(self, d_pol: float) -> Optional[dict]:
        return self._miudo("PORCA", d_pol)

    def arruela(self, d_pol: float) -> Optional[dict]:
        return self._miudo("ARRUE", d_pol)

    def _miudo(self, nome: str, d_pol: float) -> Optional[dict]:
        cands = []
        for it in self.itens:
            m = re.match(r"\s*%s\w*\s+(\d+(?:/\d+)?)" % nome, it["item"], re.I)
            if m and abs(_pol(m.group(1)) - d_pol) < 1e-6:
                cands.append((0 if "ZB" in it["item"].upper() else 1, it))
        return min(cands, key=lambda c: c[0])[1] if cands else None


def _pol(txt: str) -> float:
    """'1/2' → 0,5; '1.1/2' → 1,5; '2' → 2."""
    s = str(txt).strip().strip('"')
    tot = 0.0
    for parte in s.replace("-", ".").split("."):
        if "/" in parte:
            a, b = parte.split("/", 1)
            tot += float(a) / float(b)
        elif parte:
            tot += float(parte)
    return tot


#: Diâmetro do parafuso em mm (como vem do IFC) → polegada da tabela.
_MM_PARA_POL = [(9.5, 3 / 8), (12.7, 1 / 2), (15.9, 5 / 8), (19.05, 3 / 4), (22.2, 7 / 8), (25.4, 1.0)]


def mm_para_pol(d_mm: float) -> float:
    return min(_MM_PARA_POL, key=lambda p: abs(p[0] - d_mm))[1]


def rotulo_pol(p: float) -> str:
    return {3 / 8: '3/8"', 1 / 2: '1/2"', 5 / 8: '5/8"', 3 / 4: '3/4"', 7 / 8: '7/8"', 1.0: '1"'}.get(p, '%g"' % p)


# ============================================================ classificação das peças

def _norm(perfil: str) -> str:
    return str(perfil or "").upper().replace("×", "X").replace(",", ".").replace(" ", "")


def _espessura_do_nome(p: str) -> Optional[float]:
    """Última medida do nome: 'U150X50X2.25' → 2,25; 'U200X50#3.75' → 3,75; bitola 'U92X30X#13' → 2,25
    (das espessuras que a bitola pode ser, a da série MVAL quando há)."""
    m = re.search(r"#(\d+)$", p)
    if m and "." not in m.group(1):
        try:
            from nucleo.catalogo import espessuras_da_bitola
            esp = espessuras_da_bitola("#" + m.group(1))
        except Exception:                                # noqa: BLE001
            esp = []
        if esp:
            return next((e for e in esp if _perto(e, MVAL_FINO + MVAL_GROSSO)), esp[0])
    nums = re.findall(r"(\d+(?:\.\d+)?)", p.replace("#", "X"))
    return float(nums[-1]) if nums else None


def _perto(t: Optional[float], serie: Sequence[float], tol: float = 0.06) -> bool:
    return t is not None and any(abs(t - s) <= tol for s in serie)


def classificar(li: dict) -> str:
    """Grupo de preço de uma linha da lista de materiais (posição)."""
    classe = str(li.get("classe") or "")
    cat = str(li.get("categoria") or "")
    p = _norm(li.get("perfil"))
    if classe.startswith("Chapa"):
        return "chapa"
    if classe.startswith("Cumeeira"):
        return "cumeeira"
    if "multi-dobra" in classe and "complemento" not in classe:
        return "multidobra"                              # o complemento é telha comum (vai por ml de telha)
    if classe.startswith("Telha"):
        return "telha"
    if cat == "RUFOS" or re.match(r"^(RUFO|CALHA|PINGADEIRA|ARREMATE)", p):
        return "calha" if p.startswith("CALHA") else "rufo"
    if re.match(r"^(W|HP|VS|CVS|CS|PS)\d", p):
        return "w"
    if re.match(r"^(TQ|TR|TC|TUBO|TB)\d|^TUBO", p):
        return "tubo"
    if "CARTOLA" in p or re.match(r"^CR\d", p):
        return "cartola"
    if classe == "Barra redonda" or "REDOND" in p or re.match(r"^(Ø|RB|BR|BARRA|FE?RED|FERRO)", p) or "CHATA" in p:
        return "redondo_L"
    polegada = '"' in p or "''" in p
    if p.startswith("L"):
        if polegada:
            return "redondo_L"
        t = _espessura_do_nome(p)
        if "(FF)" in p or (t is not None and t <= 4.76):
            return "l_dobrado"
        return "redondo_L"
    if re.match(r"^(UE|U|Z|C|CE)\d", p):
        if polegada:
            return "w"                                   # U laminado (U 6"…): preço de laminado
        t = _espessura_do_nome(p)
        if _perto(t, MVAL_FINO + MVAL_GROSSO) or (t is not None and abs(t - 4.76) < 0.02):
            fino = _perto(t, MVAL_FINO)
            L = float(li.get("comprimento") or 0.0)
            fora = L > BARRA_MAX + 1 or (cat == "TERÇAS" and L < BARRA_MIN - 1)
            return ("u_fino" if fino else "u_grosso") + ("_fora" if fora else "")
        return "u_fora"
    return "outro"


#: Grupos de preço do aço, na ordem do resumo: (grupo, descrição, como achar o preço).
GRUPOS_ACO = [
    ("chapa", "Estrutura # (chapas)", None),
    ("redondo_L", "Estrutura Ø e L", ("chave", "redondo_L")),
    ("u_fino", "Estrutura U padrão 2,00 e 2,25 mm", ("chave", "u_225")),
    ("u_grosso", "Estrutura U padrão 2,65, 3,00 e 4,75 mm", ("chave", "u_esp")),
    ("u_grosso_fora", "Estrutura U padrão 2,65, 3,00 e 4,75 mm — terça (menor 4,80 / maior 6,40 m)",
     ("texto", (r"MVAL", r"2,65", r"Menor"))),
    ("u_fino_fora", "Estrutura U padrão 2,00 e 2,25 mm — terça (menor 4,80 / maior 6,40 m)", ("chave", "u_terca")),
    ("w", "Estrutura W (laminado)", ("chave", "w")),
    ("u_fora", "Estrutura U fora padrão", ("chave", "u_fora")),
    ("l_dobrado", "Estrutura L (dobrado)", ("chave", "l_dobrado")),
    ("cartola", "Estrutura cartola", ("chave", "cartola")),
    ("tubo", "Estrutura tubo", ("chave", "tubo")),
    ("outro", "Estrutura — outros perfis (sem preço na tabela)", None),
]

#: Linhas que o dono preenche (o fim do resumo do BYD), na ordem; (id, descrição, unidade, qtd automática).
LINHAS_DO_DONO = [
    ("fabricacao", "Fabricação", "kg", "aco"), ("montagem", "Montagem", "kg", "aco"),
    ("eletrodo", "Eletrodo", "", None), ("disco", "Disco", "", None), ("tinta", "Tinta", "", None),
    ("arts", "ART's", "", None), ("luz", "Luz", "", None), ("frete", "Frete", "carga", None),
    ("pedagio", "Pedágio", "carga", None), ("alojamento", "Alojamento", "", None), ("impostos", "Impostos", "", None),
    ("comissao", "Comissão", "", None), ("engenheiro", "Engenheiro", "", None), ("extras", "Extras", "", None),
    ("diesel", "Diesel", "", None), ("desp_externas", "Despesas externas", "", None),
    ("desp_internas", "Despesas internas", "", None), ("seguro", "Seguro de obras", "", None),
]

#: Acessórios de telha: quantidade da equipe (o modelo não traz), preço da tabela.
LINHAS_ACESSORIOS_TELHA = [
    ("fix_4", "Fixação de telha 4\"", "pç", ("texto", (r"FIXA", r"4\"", r"BRANCO"))),
    ("fix_oa", "Fixação onda alta 2.3/8\"", "pç", ("chave", "oa")),
    ("costura", "Costura", "pç", ("chave", "cost")),
    ("fix_ob", "Fixação onda baixa", "pç", ("chave", "ob")),
    ("fita", "Fita de vedação Tacky-tape", "ml", ("chave", "fita")),
]


def _achar(precos: Precos, como) -> Optional[dict]:
    if not como:
        return None
    if como[0] == "chave":
        return precos.chave(como[1])
    return precos.texto(*como[1])


def _linha(id_, grupo, descricao, qtd, un, item, detalhe="", origem="lista") -> dict:
    preco = item["preco"] if item else None
    return {"id": id_, "grupo": grupo, "descricao": descricao, "qtd": qtd, "un": un, "preco": preco,
            "fornecedor": (item or {}).get("fornecedor", ""), "item_tabela": (item or {}).get("item", ""),
            "linha_tabela": (item or {}).get("linha"), "data": (item or {}).get("data", ""),
            "situacao": (item or {}).get("situacao", ""), "detalhe": detalhe, "origem": origem}


def _faixa(perfis: Sequence[str], max_n: int = 6) -> str:
    ps = sorted(set(p for p in perfis if p))
    return ", ".join(ps[:max_n]) + (" …" if len(ps) > max_n else "")


def linhas_da_lista(lista: dict, precos: Precos) -> Tuple[List[dict], dict]:
    """As linhas automáticas do resumo e os números (aço, telhas, funilaria, chapas)."""
    acc: Dict[str, dict] = {}
    chapas: Dict[str, dict] = {}
    telhas: Dict[str, dict] = {}
    funil: Dict[str, dict] = {}
    num = {"aco_kg": 0.0, "chapas_kg": 0.0, "telhas_kg": 0.0, "funilaria_kg": 0.0, "telhas_ml": 0.0}
    for li in lista.get("posicoes") or []:
        g = classificar(li)
        kg = float(li.get("peso_total") or 0.0)
        if g in ("telha", "multidobra", "cumeeira"):
            num["telhas_kg"] += kg
            perfil = str(li.get("perfil") or "telha")
            k = (g, perfil if g == "telha" else "")
            t = telhas.setdefault(k, {"grupo": g, "perfil": perfil, "ml": 0.0, "pecas": 0, "kg": 0.0})
            t["ml"] += float(li.get("comprimento") or 0.0) * int(li.get("quantidade") or 0) / 1000.0
            t["pecas"] += int(li.get("quantidade") or 0)
            t["kg"] += kg
            if g != "cumeeira":
                num["telhas_ml"] += float(li.get("comprimento") or 0.0) * int(li.get("quantidade") or 0) / 1000.0
            continue
        if g in ("rufo", "calha"):
            num["funilaria_kg"] += kg
            f = funil.setdefault(g, {"kg": 0.0, "perfis": []})
            f["kg"] += kg
            f["perfis"].append(str(li.get("perfil") or ""))
            continue
        num["aco_kg"] += kg
        if g == "chapa":
            num["chapas_kg"] += kg
            t = float(li.get("espessura") or 0.0)
            item = precos.chapa(t)
            chave = item["item"] if item else "sem preço (%s mm)" % br(t, 2)
            c = chapas.setdefault(chave, {"kg": 0.0, "esp": set(), "item": item})
            c["kg"] += kg
            c["esp"].add(round(t, 2))
            continue
        a = acc.setdefault(g, {"kg": 0.0, "perfis": []})
        a["kg"] += kg
        a["perfis"].append(str(li.get("perfil") or ""))

    linhas: List[dict] = []
    for chave, c in sorted(chapas.items(), key=lambda kv: min(kv[1]["esp"])):
        esp = sorted(c["esp"])
        linhas.append(_linha("chapa:" + chave, "aco", "Estrutura # (chapas %s mm)" % " / ".join(br(e, 2) for e in esp),
                             round(c["kg"], 1), "kg", c["item"], detalhe=chave if not c["item"] else ""))
    for g, desc, como in GRUPOS_ACO:
        if g == "chapa" or g not in acc:
            continue
        a = acc[g]
        linhas.append(_linha(g, "aco", desc, round(a["kg"], 1), "kg", _achar(precos, como), detalhe=_faixa(a["perfis"])))
    if num["chapas_kg"]:
        linhas.append(_linha("corte_chaparia", "aco", "Corte chaparia", round(num["chapas_kg"], 1), "kg", None, origem="dono"))

    for (g, perfil), t in sorted(telhas.items(), key=lambda kv: ("telha", "multidobra", "cumeeira").index(kv[0][0])):
        if g == "telha":
            item = _preco_telha(precos, perfil)
            nome_t = re.sub(r"(?i)^\s*telha\s+", "", perfil)
            lin = _linha("telha:" + perfil, "telhas", "Telha %s" % nome_t, round(t["ml"], 2), "ml", item, detalhe="%d peças" % t["pecas"])
            if item is not None and not item.get("chave"):
                lin["confira"] = "preço de outra telha da tabela (%s): confira cor e acabamento" % item["item"]
            linhas.append(lin)
        elif g == "multidobra":
            linhas.append(_linha("multidobra", "telhas", "Multidobra", round(t["ml"], 2), "ml", precos.chave("multidobra"),
                                 detalhe="%d peças" % t["pecas"]))
        else:
            linhas.append(_linha("cumeeira", "telhas", "Cumeeira", t["pecas"], "pç", precos.chave("cumeeira")))
    for g in ("rufo", "calha"):
        if g in funil:
            item = precos.chave("rufo050") if g == "rufo" else precos.chave("calha")
            lin = _linha(g, "telhas", "Rufos" if g == "rufo" else "Calhas", round(funil[g]["kg"], 1), "kg", item,
                         detalhe=_faixa(funil[g]["perfis"]))
            if item is not None:
                lin["confira"] = "preço de %s: confira material e espessura desta obra" % item["item"]
            linhas.append(lin)
            linhas.append(_linha("mo_" + g, "telhas", "Mão de obra de %s" % ("rufo" if g == "rufo" else "calha"), None, "", None,
                                 origem="dono"))
    if telhas:
        for id_, desc, un, como in LINHAS_ACESSORIOS_TELHA:
            linhas.append(_linha(id_, "acessorios", desc, None, un, _achar(precos, como), origem="equipe"))
    linhas.extend(_linhas_fixadores(lista.get("acessorios") or [], precos))
    num["aco_kg"] = round(num["aco_kg"], 1)
    return linhas, num


def _preco_telha(precos: Precos, perfil: str) -> Optional[dict]:
    """TP40 0,50 → chave "telha"; senão a linha de telha da mesma espessura."""
    p = _norm(perfil)
    m = re.search(r"0[.,]?(43|50|65)", p)
    esp = m.group(1) if m else ""
    if "TP40" in p and esp in ("", "50"):
        return precos.chave("telha")
    if esp:
        return precos.texto(r"TELHA", r"0,%s" % esp) or precos.chave("telha")
    return precos.chave("telha")


_RE_PARAF = re.compile(r"(?:BOLT|PARAFUSO)\s*(?:\(([^)]*)\))?\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)", re.I)
_RE_MIUDO = re.compile(r"(PORCA|ARRUELA)\D*?(\d+(?:/\d+)?)\"", re.I)


def _linhas_fixadores(acessorios: Sequence[dict], precos: Precos) -> List[dict]:
    """Parafusos por classe e diâmetro (preço médio pelos comprimentos), porcas e arruelas soltas,
    chumbadores (previsão, sem preço) e o que não se reconheceu."""
    paraf: Dict[Tuple[str, float], dict] = {}
    miudos: Dict[Tuple[str, float], int] = {}
    outros: List[Tuple[str, int]] = []
    chumb: List[Tuple[str, int]] = []
    for a in acessorios:
        nome, q = str(a.get("nome") or ""), int(a.get("quantidade") or 0)
        if not q:
            continue
        if re.search(r"CHUMBADOR|PARABOLT|HARDBOLT", nome, re.I):
            chumb.append((nome, q))
            continue
        m = _RE_PARAF.search(nome)
        if m:
            classe = "A325" if "325" in (m.group(1) or "") or "A325" in nome.upper() else "A307"
            d = mm_para_pol(float(m.group(2).replace(",", ".")))
            L = float(m.group(3).replace(",", "."))
            p = paraf.setdefault((classe, d), {"qtd": 0, "valor": 0.0, "sem": 0, "comprs": {}, "itens": set()})
            item = precos.parafuso(d, L, classe)
            if item is None:
                outra = "A325" if classe == "A307" else "A307"
                item = precos.parafuso(d, L, outra)
                if item is not None:
                    p.setdefault("trocas", set()).add(outra)
            p["qtd"] += q
            p["comprs"][int(round(L))] = p["comprs"].get(int(round(L)), 0) + q
            if item:
                p["valor"] += item["preco"] * q
                p["itens"].add(item["item"])
            else:
                p["sem"] += q
            continue
        m = _RE_MIUDO.search(nome)
        if m:
            k = ("porca" if m.group(1).upper() == "PORCA" else "arruela", _pol(m.group(2)))
            miudos[k] = miudos.get(k, 0) + q
            continue
        outros.append((nome, q))
    linhas = []
    for (classe, d), p in sorted(paraf.items()):
        com_preco = p["qtd"] - p["sem"]
        preco = round(p["valor"] / com_preco, 4) if com_preco else None
        itens = sorted(p["itens"])
        lin = _linha("paraf:%s:%s" % (classe, rotulo_pol(d)), "parafusos", "Parafuso %s Ø%s completo" % (classe, rotulo_pol(d)),
                     p["qtd"], "pç", None,
                     detalhe="comprimentos (mm): " + ", ".join("%d× %d" % (q, L) for L, q in sorted(p["comprs"].items()))
                             + ("; %d sem preço na tabela" % p["sem"] if p["sem"] else "")
                             + ("; sem %s Ø%s na tabela: preço do %s" % (classe, rotulo_pol(d), "/".join(sorted(p["trocas"])))
                                if p.get("trocas") else ""))
        lin["preco"] = preco
        if p.get("trocas"):
            lin["confira"] = "a tabela não tem %s Ø%s: usado o preço do %s" % (classe, rotulo_pol(d), "/".join(sorted(p["trocas"])))
        lin["item_tabela"] = itens[0] if len(itens) == 1 else ("média de %d linhas da tabela" % len(itens) if itens else "")
        linhas.append(lin)
    for (tipo, d), q in sorted(miudos.items()):
        item = precos.porca(d) if tipo == "porca" else precos.arruela(d)
        linhas.append(_linha("%s:%s" % (tipo, rotulo_pol(d)), "parafusos", "%s Ø%s (barras roscadas)" % (tipo.capitalize(), rotulo_pol(d)),
                             q, "pç", item))
    for nome, q in chumb:
        linhas.append(_linha("chumb:" + nome, "parafusos", "Chumbador %s (previsão)" % re.sub(r"(?i)chumbador\s*", "", nome).strip(),
                             q, "pç", None))
    for nome, q in outros:
        linhas.append(_linha("acess:" + nome, "parafusos", nome, q, "pç", None, detalhe="não reconhecido na tabela"))
    return linhas


# ============================================================ montagem com as edições

def _aplicar_edicoes(linhas: List[dict], edicoes: dict) -> List[dict]:
    ed = (edicoes or {}).get("linhas") or {}
    saida = []
    for li in linhas:
        e = ed.get(li["id"]) or {}
        li = dict(li)
        li["qtd_auto"], li["preco_auto"] = li.get("qtd"), li.get("preco")
        for k in ("qtd", "preco", "descricao", "un"):
            if k in e and e[k] not in (None, ""):
                li[k] = _f(e[k]) if k in ("qtd", "preco") else str(e[k])
                li["editado"] = True
        for k in ("preco_fech", "total_fech"):
            li[k] = _f(e.get(k))
        li["total_fech_ed"] = li["total_fech"]           # o digitado (a tela distingue do calculado)
        if e.get("oculta"):
            li["oculta"] = True
        saida.append(li)
    for i, x in enumerate((edicoes or {}).get("extras") or []):
        saida.append({"id": "extra:%d" % i, "grupo": x.get("grupo") or "extras", "descricao": str(x.get("descricao") or ""),
                      "qtd": _f(x.get("qtd")), "un": str(x.get("un") or ""), "preco": _f(x.get("preco")),
                      "preco_fech": _f(x.get("preco_fech")), "total_fech": _f(x.get("total_fech")), "total_fech_ed": _f(x.get("total_fech")),
                      "fornecedor": str(x.get("fornecedor") or ""), "origem": "manual", "detalhe": "", "extra": True})
    for li in saida:
        li["total"] = round(li["qtd"] * li["preco"], 2) if li.get("qtd") not in (None, "") and li.get("preco") not in (None, "") else None
        if li.get("total_fech") is None and li.get("preco_fech") is not None and li.get("qtd") not in (None, ""):
            li["total_fech"] = round(li["qtd"] * li["preco_fech"], 2)
    return saida


GRUPOS = [("aco", "Estrutura metálica"), ("telhas", "Telhas e funilaria"), ("parafusos", "Parafusos e chumbadores"),
          ("acessorios", "Acessórios de telha"), ("dono", "Fabricação, montagem e despesas"), ("extras", "Itens acrescentados")]


def montar(lista: dict, tabela: Optional[dict], edicoes: Optional[dict] = None, projeto: Optional[dict] = None,
           numeros_resumo: Optional[dict] = None, hoje: Optional[date] = None) -> dict:
    """O resumo de orçamento inteiro: cabeçalho, linhas (automáticas + do dono + acrescentadas, com as
    edições), totais e avisos."""
    hoje = hoje or date.today()
    precos = Precos(tabela)
    linhas, num = linhas_da_lista(lista, precos)
    for id_, desc, un, auto in LINHAS_DO_DONO:
        linhas.append(_linha(id_, "dono", desc, num["aco_kg"] if auto == "aco" else None, un, None, origem="dono"))
    linhas = _aplicar_edicoes(linhas, edicoes or {})
    vis = [li for li in linhas if not li.get("oculta")]
    tot_tab = round(sum(li["total"] or 0.0 for li in vis), 2)
    tot_fech = round(sum(li.get("total_fech") or 0.0 for li in vis), 2)
    proj = dict(projeto or {})
    nr = numeros_resumo or {}
    area = _f(((edicoes or {}).get("cabecalho") or {}).get("area_m2")) or _f((nr.get("dimensoes") or {}).get("area_m2"))
    cab = {"data": hoje.strftime("%d/%m/%Y"), "obra": proj.get("nome", ""), "cliente": proj.get("cliente", ""),
           "local": proj.get("local", ""), "distancia_km": "", "opcao": "", "area_m2": round(area, 2) if area else None,
           "descricao": ""}
    cab.update({k: v for k, v in ((edicoes or {}).get("cabecalho") or {}).items() if v not in (None, "")})
    if area:
        cab["area_m2"] = round(area, 2)
    totais = {"tabela": tot_tab, "fechamento": tot_fech, "aco_kg": num["aco_kg"], "telhas_ml": round(num["telhas_ml"], 2),
              "telhas_kg": round(num["telhas_kg"], 1), "funilaria_kg": round(num["funilaria_kg"], 1),
              "rs_kg_tabela": round(tot_tab / num["aco_kg"], 2) if num["aco_kg"] else None,
              "rs_kg_fechamento": round(tot_fech / num["aco_kg"], 2) if num["aco_kg"] and tot_fech else None,
              "rs_m2_fechamento": round(tot_fech / area, 2) if area and tot_fech else None}
    return {"cabecalho": cab, "linhas": linhas, "grupos": GRUPOS, "totais": totais,
            "notas": str((edicoes or {}).get("notas") or ""),
            "tabela": {k: (tabela or {}).get(k, "") for k in ("arquivo", "titulo")},
            "avisos": avisos(lista, linhas, tabela, hoje),
            "regras": REGRAS_TEXTO}


REGRAS_TEXTO = [
    "U dobrado de 2,00/2,25/2,65/3,00/4,75 mm = U padrão MVAL; outra espessura = U fora padrão (Perfyaço).",
    "Terça fora de 4,80–6,40 m e qualquer peça acima de 6,40 m: preço MVAL 'menor 4,80 / maior 6,40 m'.",
    "Peso teórico da lista de materiais, sem perda de corte. Telhas em metro linear de chapa comprada.",
    "Parafusos: o completo (porca e arruela) zincado da tabela, no menor comprimento que não fica curto; "
    "o preço da linha é a média pelos comprimentos da obra.",
]


def avisos(lista: dict, linhas: Sequence[dict], tabela: Optional[dict], hoje: date) -> List[dict]:
    """As travas: o que precisa ser conferido antes de mandar a proposta."""
    av: List[dict] = []

    def add(nivel, texto):
        av.append({"nivel": nivel, "texto": texto})

    velhas: Dict[tuple, List[str]] = {}
    longos: List[dict] = []
    if not tabela or not tabela.get("itens"):
        add("alto", "Nenhuma tabela de preços carregada: as linhas saem sem valor. Carregue a planilha da empresa.")
    for li in linhas:
        if li.get("oculta"):
            continue
        if li.get("origem") in ("dono", "equipe", "manual"):
            # o que a equipe ou o dono preenchem não é "sem preço"; o preço "VER ?" usado, sim
            if li.get("qtd") and str(li.get("situacao") or "").upper().startswith("VER") and li.get("preco") is not None:
                add("medio", "Preço a confirmar com o fornecedor (VER ?): %s — %s" % (li["descricao"], li.get("item_tabela", "")))
            continue
        if li.get("qtd") and li.get("preco") in (None, ""):
            add("medio", "Sem preço na tabela: %s (%s %s)%s" % (li["descricao"], br(li["qtd"], 1), li.get("un", ""),
                                                                 (" — " + li["detalhe"]) if li.get("detalhe") else ""))
        if str(li.get("situacao") or "").upper().startswith("VER"):
            add("medio", "Preço a confirmar com o fornecedor (VER ?): %s — %s" % (li["descricao"], li.get("item_tabela", "")))
        if li.get("confira"):
            add("medio", "%s: %s" % (li["descricao"], li["confira"]))
        d = _dias(li.get("data"), hoje)
        if d is not None and d > DIAS_COTACAO and li.get("preco") is not None:
            velhas.setdefault((li["data"], d), []).append(li["descricao"])
    for li in lista.get("posicoes") or []:
        if str(li.get("classe") or "").startswith("Chapa") and float(li.get("espessura") or 0) > 50:
            add("alto", "Chapa de %s mm na posição %s (%s kg): espessura fora do comum — confira o modelo"
                % (br(li.get("espessura"), 1), li.get("marca"), br(li.get("peso_total"), 0)))
        if classificar(li).startswith(("u_", "l_dobrado", "cartola")) and float(li.get("comprimento") or 0) > 12000:
            longos.append(li)
    if longos:
        longos.sort(key=lambda li: -float(li["comprimento"]))
        add("medio", "%d posição(ões) de perfil dobrado acima de 12 m, o máximo da dobradeira — prever emenda (chapas, "
                     "parafusos e mão de obra não estão no orçamento): %s"
            % (len(longos), ", ".join("%s %s m" % (li.get("marca"), br(float(li["comprimento"]) / 1000.0, 2)) for li in longos[:5])
               + (" …" if len(longos) > 5 else "")))
    for (data_, d), descs in sorted(velhas.items(), key=lambda kv: -kv[0][1]):
        add("baixo", "Cotação de %s (%d dias) em %d linha(s): %s" % (data_, d, len(descs), _faixa(descs, 4)))
    chapas_sem = [li for li in lista.get("posicoes") or [] if str(li.get("classe") or "").startswith("Chapa") and not li.get("material")]
    if chapas_sem:
        add("baixo", "%d posição(ões) de chapa sem material no modelo" % len(chapas_sem))
    aco = sum(float(li.get("peso_total") or 0) for li in lista.get("posicoes") or [] if classificar(li) not in ("telha", "multidobra", "cumeeira", "rufo", "calha"))
    if aco > 1000 and not lista.get("acessorios"):
        add("alto", "Obra com %s kg de aço e nenhum parafuso na lista: as ligações não foram modeladas — some os parafusos à mão" % br(aco, 0))
    # linhas repetidas de cotação: ordena por gravidade
    ordem = {"alto": 0, "medio": 1, "baixo": 2}
    vistos, unicos = set(), []
    for a in sorted(av, key=lambda a: ordem.get(a["nivel"], 3)):
        if a["texto"] not in vistos:
            vistos.add(a["texto"])
            unicos.append(a)
    return unicos


def _dias(data_txt, hoje: date) -> Optional[int]:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(data_txt or ""))
    if not m:
        return None
    try:
        return (hoje - date(int(m.group(3)), int(m.group(2)), int(m.group(1)))).days
    except ValueError:
        return None


# ============================================================ edições gravadas

def ler_edicoes(pasta_projeto: str) -> dict:
    try:
        with open(os.path.join(pasta_projeto, PASTA_ORCAMENTO, ARQ_EDICOES), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gravar_edicoes(pasta_projeto: str, edicoes: dict) -> dict:
    pasta = os.path.join(pasta_projeto, PASTA_ORCAMENTO)
    os.makedirs(pasta, exist_ok=True)
    limpo = {"cabecalho": dict(edicoes.get("cabecalho") or {}), "linhas": {}, "extras": [], "notas": str(edicoes.get("notas") or ""),
             "gravado": datetime.now().strftime("%Y-%m-%d %H:%M")}
    for id_, e in (edicoes.get("linhas") or {}).items():
        e = {k: v for k, v in (e or {}).items() if k in ("qtd", "preco", "descricao", "un", "preco_fech", "total_fech", "oculta") and v not in (None, "")}
        if e:
            limpo["linhas"][str(id_)] = e
    for x in edicoes.get("extras") or []:
        if str((x or {}).get("descricao") or "").strip():
            limpo["extras"].append({k: x.get(k) for k in ("grupo", "descricao", "qtd", "un", "preco", "preco_fech", "total_fech", "fornecedor")})
    caminho = os.path.join(pasta, ARQ_EDICOES)
    with open(caminho + ".parcial", "w", encoding="utf-8") as f:
        json.dump(limpo, f, ensure_ascii=False, indent=1)
    os.replace(caminho + ".parcial", caminho)
    return limpo


# ============================================================ documento

def _qtd_txt(li) -> str:
    if li.get("qtd") in (None, ""):
        return ""
    casas = 0 if li.get("un") in ("pç", "carga") else (2 if li.get("un") == "ml" else 2)
    return "%s %s" % (br(li["qtd"], casas), li.get("un") or "")


def _preco_txt(li) -> str:
    if li.get("preco") in (None, ""):
        return ""
    un = li.get("un") or ""
    return "R$ %s%s" % (br(li["preco"], 2), ("/" + un) if un else "")


def html_resumo(R: dict) -> str:
    """O resumo no formato do R00 da equipe: descrição, quantidade, valor (tabela, com o fornecedor),
    valor total, e as duas colunas de fechamento do dono."""
    c = R["cabecalho"]
    t = R["totais"]
    linhas_html = []
    for gk, gt in R["grupos"]:
        do_grupo = [li for li in R["linhas"] if li["grupo"] == gk and not li.get("oculta")]
        if not do_grupo:
            continue
        linhas_html.append('<tr class="grupo"><td colspan="6">%s</td></tr>' % _esc(gt))
        for li in do_grupo:
            det = ('<div class="det">%s</div>' % _esc(li["detalhe"])) if li.get("detalhe") else ""
            forn = ('<div class="forn">%s</div>' % _esc(li["fornecedor"])) if li.get("fornecedor") else ""
            linhas_html.append(
                "<tr><td>%s%s</td><td class=\"c\">%s</td><td class=\"c\"><b>%s</b>%s</td><td class=\"r\">%s</td>"
                "<td class=\"r\">%s</td><td class=\"r\">%s</td></tr>" % (
                    _esc(li["descricao"]), det, _esc(_qtd_txt(li)), _esc(_preco_txt(li)), forn,
                    _esc(("R$ " + br(li["total"])) if li.get("total") is not None else ""),
                    _esc(("R$ " + br(li["preco_fech"])) if li.get("preco_fech") is not None else ""),
                    _esc(("R$ " + br(li["total_fech"])) if li.get("total_fech") is not None else "")))
    linhas_html.append('<tr class="total"><td colspan="3">TOTAL</td><td class="r">R$ %s</td><td></td><td class="r">%s</td></tr>'
                       % (br(t["tabela"]), ("R$ " + br(t["fechamento"])) if t["fechamento"] else ""))
    sub = []
    if c.get("local") or c.get("distancia_km"):
        sub.append("%s%s" % (_esc(c.get("local") or ""), (" (+/- %s km)" % _esc(c["distancia_km"])) if c.get("distancia_km") else ""))
    area = c.get("area_m2")
    peso = t["aco_kg"]
    notas = [n_.strip(" •-") for n_ in str(R.get("notas") or "").splitlines() if n_.strip()]
    avisos_ = "".join("<li class=\"%s\">%s</li>" % (a["nivel"], _esc(a["texto"])) for a in R.get("avisos") or [])
    return """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Resumo de orçamento — %(obra)s</title>
<style>
@page { size: A4; margin: 14mm 12mm; }
body { font: 9.5pt/1.3 Calibri, 'Segoe UI', Arial, sans-serif; color: #000; margin: 0; }
.data { text-align: right; margin: 0 0 3mm; }
.cab { text-align: center; font-weight: 700; text-decoration: underline; margin: .8mm 0; }
.cab.n { font-weight: 400; }
table { border-collapse: collapse; width: 100%%; margin-top: 3mm; }
th, td { border: 1px solid #000; padding: 1mm 1.5mm; vertical-align: top; }
th { font-weight: 700; text-align: center; }
td.c { text-align: center; } td.r { text-align: right; white-space: nowrap; }
tr { break-inside: avoid; }
tr.grupo td { font-weight: 700; background: #eee; }
tr.total td { font-weight: 700; }
.det { font-size: 7.5pt; color: #444; } .forn { font-size: 8pt; font-weight: 400; }
ul.notas { font-weight: 700; margin: 3mm 0 0 18mm; }
.rod { font-size: 7.5pt; color: #444; margin-top: 4mm; }
ul.av { font-size: 7.5pt; margin: 1mm 0 0 4mm; padding-left: 3mm; } ul.av li.alto { color: #b00; } ul.av li.medio { color: #a60; }
</style>
<script>/* sem Paged.js: o sinal de "pronto" que saida/printpdf.imprimir espera */
document.addEventListener("DOMContentLoaded", function () { document.documentElement.setAttribute("data-paged", "done"); });</script>
</head><body>
<p class="data">%(data)s</p>
<p class="cab">%(titulo)s</p>
%(opcao)s%(descricao)s
<p class="cab">(ÁREA total: %(area)s) (Peso total: %(peso)s kg)</p>
<table>
<colgroup><col style="width:30%%"><col style="width:15%%"><col style="width:15%%"><col style="width:14%%"><col style="width:12%%"><col style="width:14%%"></colgroup>
<thead><tr><th>DESCRIÇÃO</th><th>QUANTIDADE</th><th>VALOR</th><th>VALOR TOTAL</th><th>VALOR</th><th>VALOR TOTAL</th></tr></thead>
<tbody>%(linhas)s</tbody></table>
%(notas)s
<div class="rod">Quantidades da lista de materiais do modelo 3D (peso teórico); preços da %(tabela)s.
Colunas da direita: valores de fechamento. %(rskg)s
%(avisos)s</div>
</body></html>""" % {
        "obra": _esc(c.get("obra")), "data": _esc(c.get("data")),
        "titulo": _esc(" – ".join(x for x in (c.get("obra"), " ".join(sub)) if x)),
        "opcao": ('<p class="cab">%s</p>' % _esc(c["opcao"])) if c.get("opcao") else "",
        "descricao": "".join('<p class="cab n">%s</p>' % _esc(l_) for l_ in str(c.get("descricao") or "").splitlines() if l_.strip()),
        "area": (br(area, 2) + "m²") if area else "—", "peso": br(peso, 2),
        "linhas": "".join(linhas_html),
        "notas": ('<ul class="notas">%s</ul>' % "".join("<li>%s</li>" % _esc(n_) for n_ in notas)) if notas else "",
        "tabela": _esc((R.get("tabela") or {}).get("arquivo") or "tabela de preços (nenhuma carregada)"),
        "rskg": _esc("Tabela: R$ %s/kg de aço." % br(t["rs_kg_tabela"]) if t.get("rs_kg_tabela") else ""),
        "avisos": ('<b>A conferir:</b><ul class="av">%s</ul>' % avisos_) if avisos_ else "",
    }


def gravar_documentos(pasta_projeto: str, R: dict, imprimir_pdf: bool = True) -> dict:
    """resumo-de-orcamento.html/.pdf e .csv em <projeto>/orcamento/."""
    pasta = os.path.join(pasta_projeto, PASTA_ORCAMENTO)
    os.makedirs(pasta, exist_ok=True)
    saida = {}
    h = os.path.join(pasta, ARQ_HTML)
    with open(h, "w", encoding="utf-8") as f:
        f.write(html_resumo(R))
    saida["html"] = h
    cam = os.path.join(pasta, ARQ_CSV)
    with open(cam, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        w.writerow(["Grupo", "Descrição", "Quantidade", "Un", "Valor (tabela)", "Fornecedor", "Valor total", "Valor (fechamento)",
                    "Valor total (fechamento)", "Item da tabela", "Data da cotação", "Detalhe"])
        nomes = dict(R["grupos"])
        num = lambda x: "" if x in (None, "") else ("%.4f" % float(x)).rstrip("0").rstrip(".").replace(".", ",")   # noqa: E731
        for li in R["linhas"]:
            if li.get("oculta"):
                continue
            w.writerow([nomes.get(li["grupo"], li["grupo"]), li["descricao"], num(li.get("qtd")), li.get("un", ""), num(li.get("preco")),
                        li.get("fornecedor", ""), num(li.get("total")), num(li.get("preco_fech")), num(li.get("total_fech")),
                        li.get("item_tabela", ""), li.get("data", ""), li.get("detalhe", "")])
        w.writerow(["", "TOTAL", "", "", "", "", num(R["totais"]["tabela"]), "", num(R["totais"]["fechamento"] or None), "", "", ""])
    saida["csv"] = cam
    if imprimir_pdf:
        from saida import printpdf
        pdf = os.path.join(pasta, ARQ_PDF)
        try:
            printpdf.imprimir(h, pdf, verbose=False, timeout=300)
            saida["pdf"] = pdf
        except Exception as exc:                       # noqa: BLE001 — sem navegador, fica o HTML e o CSV
            saida["erro_pdf"] = str(exc)
    return saida
