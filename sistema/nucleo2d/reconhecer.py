# -*- coding: utf-8 -*-
"""Reconhecimento das peças num projeto recebido em DXF ou PDF.

O projeto estrutural que chega à fábrica é um desenho: planta de cobertura, tesoura,
pórtico, fachadas — linhas e, perto de cada linha, o perfil escrito ("U100x50#11",
"W 200 x 19,3", "C150X50X17X2.25", "Ø1/2\"", "2U75x38#13"). Este módulo lê esse desenho
como um detalhista leria:

1. **Vistas.** As linhas próximas formam uma vista; o título dela (PLANTA DE COBERTURA,
   TESOURA T1, CORTE AA, FACHADA LATERAL) diz o que ela é.
2. **Escala.** Cada cota escrita perto de uma linha paralela dá uma razão
   valor / comprimento; a razão que mais se repete é a escala da vista (PDF: 1:50, 1:100…;
   DXF: mm, cm ou m). O "ESC. 1:50" do título confirma.
3. **Perfis.** Cada texto que é um perfil do catálogo (ou um dobrado que a fábrica faz)
   é ligado à linha que ele acompanha: paralela e perto, ou pela linha de chamada. A
   legenda ("BS – U 150x60x20#13") liga as siglas escritas nas barras.
4. **O resto da barra.** O rótulo costuma vir uma vez por banzo: a peça segue pelos
   trechos colineares ligados a ela, e numa camada em que tudo tem o mesmo perfil as
   linhas sem rótulo o herdam (estas ficam "a conferir").
5. **Linha dupla.** Barra desenhada com as duas faces (planta de vigas, pilar em
   elevação) vira uma barra só, no eixo, quando a distância entre as linhas bate com a
   altura ou a largura do perfil.
6. **Papel.** Pela palavra (BANZO, DIAGONAL, TERÇA, PILAR…), pela sigla, pelo perfil
   (barra redonda = contraventamento) e pela geometria da vista (numa treliça, o que
   está no contorno de cima e de baixo é banzo, o vertical é montante, o resto diagonal).
7. **Eixos.** Balões com número ou letra na ponta de uma linha longa são os eixos do
   projeto — é por eles que a montagem (`sugerir_montagem`) põe cada tesoura no lugar.

O resultado **não mexe** nas linhas do arquivo: as peças reconhecidas entram numa camada
própria ("PEÇAS RECONHECIDAS", e "PEÇAS A CONFERIR" para as herdadas), cada linha com a
peça (`atributos["peca"]`, o mesmo que o CAD grava à mão) e de onde ela veio
(`atributos["reconhecido"]`). É isso que o "Gerar modelo 3D" transforma em barras.
"""
from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from nucleo2d.desenho import Camada2D, Circulo, Desenho, Linha, Polilinha, Texto

__all__ = ["perfil_do_texto", "reconhecer", "aplicar", "sugerir_montagem", "CAMADA_OK", "CAMADA_CONFERIR"]

CAMADA_OK = "PEÇAS RECONHECIDAS"
CAMADA_CONFERIR = "PEÇAS A CONFERIR"

Ponto2 = Tuple[float, float]

#: camadas que são anotação (não têm barra): cota, texto, eixo, hachura, carimbo…
_ANOTACAO = re.compile(r"(?i)(COT|DIM|TEXT|TXT|TEXTO|EIXO|AXIS|CENTER|CENTRO|HACH|HATCH|CARIMBO|MOLDURA|FORMAT|"
                       r"FOLHA|LEGEND|SIMB|NOTA|DEFPOINTS|VIEWPORT|^VP|TITUL|SELO|PEÇAS RECONHECIDAS|PEÇAS A CONFERIR|"
                       r"ANOTA|CHAMADA|LEADER|NIVEL|NÍVEL)")

# ------------------------------------------------------------------------------------
# Perfil escrito → peça do catálogo
# ------------------------------------------------------------------------------------

#: palavra → papel da peça
PALAVRAS_PAPEL = [
    (r"BANZO|\bBS\b|\bBI\b|\bBSUP|\bBINF|CORDA", "banzo"),
    (r"DIAGONA|\bDG\d*\b|\bDIAG", "diagonal"),
    (r"MONTANTE|\bMT\d*\b|\bMONT", "montante"),
    (r"TER[ÇC]A|\bTC\d*\b|\bTER\b", "terça"),
    (r"LONGARINA|\bLG\d*\b|TRAVESSA", "longarina"),
    (r"CONTRAV|\bCT\d*\b|\bCV\d*\b|MÃO.FRANCESA|MAO.FRANCESA", "contraventamento"),
    (r"TIRANTE|CORRENTE|\bTIR\b", "tirante"),
    (r"PILAR|COLUNA|\bPL\d*\b|\bP\d+\b", "pilar"),
    (r"\bVIGA|\bV\d+\b", "viga"),
]

_BITOLAS_POL = {"1/8": 3.175, "5/32": 3.97, "3/16": 4.76, "1/4": 6.35, "5/16": 7.94, "3/8": 9.53, "7/16": 11.11,
                "1/2": 12.7, "5/8": 15.88, "3/4": 19.05, "7/8": 22.23, "1": 25.4}
#: mm → polegada da aba das cantoneiras laminadas (L 50x50#3/16" = L 2"x3/16")
_ABA_POL = [(12.7, '1/2"'), (15.9, '5/8"'), (19.05, '3/4"'), (22.2, '7/8"'), (25.4, '1"'), (31.75, '1.1/4"'),
            (38.1, '1.1/2"'), (44.45, '1.3/4"'), (50.8, '2"'), (63.5, '2.1/2"'), (76.2, '3"'), (88.9, '3.1/2"'),
            (101.6, '4"'), (127.0, '5"'), (152.4, '6"'), (203.2, '8"')]

_NUM = r"\d+(?:[.,]\d+)?"
_POL = r"\d+(?:[.\s-]\d+)?/\d+\"?|\d+\""
_RE_REDONDA = re.compile(
    r"(?:(?:FERRO|BARRA\s+REDONDA|REDONDO|BR|FR|TIRANTE|CORRENTE|CONTRAVENT\w*)\s*(?:REDONDO\s*)?(?:Ø|DIAM\.?)?|Ø|DIAM\.?)"
    r"\s*(" + _POL + r"|" + _NUM + r")\s*(?:MM)?")
_RE_PERFIL = re.compile(
    r"(?<![A-Z0-9])(?P<mult>[2-4]\s*)?(?P<fam>UE|ZE|Z45|CR|TQ|TR|TC|HP|CVS|CS|VS|PS|W|U|C|Z|L|I|TUBO)"
    r"\s*(?P<resto>\d[\d.,X/\"#\s]*(?:#\s*(?:" + _POL + r"|\d+))?)")
_RE_CHAPA = re.compile(r"(?<![A-Z])(?:CH|CHAPA|PL)\s*[.#]?\s*(?P<resto>[\d.,X/\"#\s]+)")
#: "3 PRESILHAS L 1"X1/8"" depois do perfil da peça (o projetista às vezes escreve PRELILHAS)
_RE_PRESILHA = re.compile(r"(?:\b\d+\s*)?\bPRE[SL]ILHAS?\b")
_NAO_PECA = re.compile(r"FURO|PARAF|PORCA|ARRUELA|CHUMB|PINO|SOLDA|A-?325|A-?307|A-?490|FILETE|\bESC\b|ESCALA|OBS")


def _limpo(texto: str) -> str:
    t = str(texto or "").upper()
    for a, b in (("×", "X"), ("*", "X"), ("%%C", "Ø"), ("Φ", "Ø"), ("∅", "Ø"), ("⌀", "Ø"), ("�", "Ø"),
                 ("''", '"'), ("”", '"'), ("“", '"'), ("MM", " MM"), (" ", " ")):
        t = t.replace(a, b)
    t = re.sub(r"(?<=\d)\s*X\s*(?=[\d#])", "X", t)
    return re.sub(r"\s+", " ", t).strip()


def _polegada(s: str) -> Optional[float]:
    """'1/2"' → 12,7; '1.1/4"' ou '1 1/4' → 31,75; '2"' → 50,8."""
    s = s.replace('"', "").strip()
    m = re.match(r"^(\d+)[.\s-](\d+)/(\d+)$", s)
    if m:
        return (int(m.group(1)) + int(m.group(2)) / int(m.group(3))) * 25.4
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2)) * 25.4
    try:
        return float(s) * 25.4
    except ValueError:
        return None


def _num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _fmt(v: float) -> str:
    return ("%.2f" % v).rstrip("0").replace(".", ",") if abs(v - round(v)) > 1e-6 else "%d" % round(v)


def _plausivel(p, fam: str) -> bool:
    """Medidas de perfil que existe (o banco monta qualquer nome de fábrica, até absurdo)."""
    d, bf, t = float(p.d or 0), float(p.bf or 0), float(p.tw or 0)
    if d > 1600 or bf > 1000 or (t and t > 80):
        return False
    if fam in ("U", "C", "UE", "Z", "ZE", "Z45", "CR", "L") and (d > 500 or bf > 300):
        return False
    return True


def _candidatos(fam: str, dims: List[float], t_opcoes: List[float], t_pol: Optional[str]) -> List[str]:
    """Nomes de catálogo a tentar, do mais provável ao menos."""
    c: List[str] = []
    ts = []
    for t in t_opcoes:
        for x in (_fmt(t), ("%.2f" % t).replace(".", ",")):
            if x not in ts:
                ts.append(x)
    if fam in ("U", "C") and len(dims) >= 2:
        h, b = dims[0], dims[1]
        if len(dims) >= 3:                            # U200x75x25#13, C150X50X17X2.25: com enrijecedor
            c += ["Ue %sx%sx%sx%s" % (_fmt(h), _fmt(b), _fmt(dims[2]), t) for t in ts]
        else:
            c += ["U %sx%sx%s (FF)" % (_fmt(h), _fmt(b), t) for t in ts]
            c += ["U %sx%sx%s" % (_fmt(h), _fmt(b), t) for t in ts]
            if fam == "U" and len(dims) == 2 and not t_opcoes:   # U 6"x12,2 / U 152x12,2 laminado
                c.append("U %sx%s" % (_fmt(h), _fmt(b)))
    elif fam == "UE" and len(dims) >= 3:
        c += ["Ue %sx%sx%sx%s" % (_fmt(dims[0]), _fmt(dims[1]), _fmt(dims[2]), t) for t in ts]
    elif fam in ("Z", "ZE") and len(dims) >= 3:
        c += ["Ze %sx%sx%sx%s" % (_fmt(dims[0]), _fmt(dims[1]), _fmt(dims[2]), t) for t in ts]
    elif fam == "Z45" and len(dims) >= 3:
        c += ["Z45 %sx%sx%sx%s" % (_fmt(dims[0]), _fmt(dims[1]), _fmt(dims[2]), t) for t in ts]
    elif fam == "CR" and len(dims) >= 3:
        c += ["Cr %sx%sx%sx%s" % (_fmt(dims[0]), _fmt(dims[1]), _fmt(dims[2]), t) for t in ts]
    elif fam == "L" and dims:
        b = dims[0]
        b2 = dims[1] if len(dims) >= 2 else b
        if t_pol:                                    # L50X50#3/16" → L 2"x3/16"
            aba = min(_ABA_POL, key=lambda x: abs(x[0] - b))
            if abs(aba[0] - b) <= 0.08 * b:
                c.append('L %sx%s"' % (aba[1], t_pol))
        if abs(b - b2) < 0.01:
            c += ["L %sx%s (FF)" % (_fmt(b), t) for t in ts]
        c += ["L %sx%sx%s" % (_fmt(b), _fmt(b2), t) for t in ts]
    elif fam in ("W", "HP", "I", "CS", "CVS", "VS", "PS") and len(dims) >= 2:
        c.append("%s %sx%s" % (fam, _fmt(dims[0]), _fmt(dims[1])))
    elif fam in ("TQ", "TR", "TUBO") and len(dims) >= 2:
        a, b = dims[0], dims[1]
        for t in ts or ([_fmt(dims[2])] if len(dims) >= 3 else []):
            c.append("%s %sx%sx%s" % ("TQ" if abs(a - b) < 0.1 else "TR", _fmt(a), _fmt(b), t))
    elif fam == "TC" and len(dims) >= 2:
        c.append("TC %sx%s" % (_fmt(dims[0]), _fmt(dims[1])))
    return c


def _perfil_valido(nome: str):
    from nucleo import catalogo
    try:
        p = catalogo.perfil_de(nome)
    except Exception:                                            # noqa: BLE001
        return None
    if p is None or not getattr(p, "massa", 0):
        return None
    return p


_CACHE_PERFIL: Dict[str, Optional[dict]] = {}


def perfil_do_texto(texto: str) -> Optional[dict]:
    """Perfil escrito num texto do desenho (veja `_perfil_do_texto`); o mesmo texto se
    repete centenas de vezes num desenho grande, então a resposta fica guardada."""
    chave = str(texto or "")
    if chave not in _CACHE_PERFIL:
        if len(_CACHE_PERFIL) > 20000:
            _CACHE_PERFIL.clear()
        _CACHE_PERFIL[chave] = _perfil_do_texto(chave)
    r = _CACHE_PERFIL[chave]
    return dict(r) if r else None


def _perfil_do_texto(texto: str) -> Optional[dict]:
    """Perfil escrito num texto do desenho → {perfil, mult, papel, trecho, chapa?}.

    Aceita a grafia da fábrica e a do projetista: U100x50#11, U200x75x25#13 (Ue),
    C150X50X17X2.25, L25x25#11, L50X50#3/16", 2U75x38#13, W 200 x 19,3, TQ 100x100x4,
    Tubo 30x30#1,5mm, Ø1/2", FERRO Ø3/8", CH 3/8", CH200x70x8.00. Texto de furo, parafuso,
    chumbador e solda não é peça. O nome devolvido é o do catálogo (ou o do perfil dobrado
    que a fábrica monta), para o 3D achar a seção."""
    t = _limpo(texto)
    if not t or len(t) > 160:
        return None
    # "2L 1"X1/8"  3 PRESILHAS L 1"X1/8"": a peça é a primeira; as presilhas são acessório
    m = re.search(_RE_PRESILHA, t)
    if m and m.start() > 0:
        t = t[:m.start()].strip()
    # sigla com o perfil entre parênteses: "PM3(200X70X20X2,65)" (Ue: altura, aba, dobra,
    # espessura) ou "VM1(150X60X3,00)" (U) — o projetista escreve só as medidas
    m = re.match(r"^([A-Z]{1,3})\d+[A-Z]?\s*\(\s*(\d[\d.,]*(?:\s*X\s*\d[\d.,]*){2,3})\s*\)", t)
    if m:
        n = len(re.findall(r"X", m.group(2)))
        t = ("UE " if n == 3 else "U ") + m.group(2).replace(" ", "")
        papel_sigla = {"PM": "pilar", "P": "pilar", "PL": "pilar", "VM": "viga", "V": "viga", "VG": "viga"}.get(m.group(1))
        r = _perfil_do_texto(t)
        if r:
            r["papel"] = r.get("papel") or papel_sigla
        return r
    papel = next((p for rx, p in PALAVRAS_PAPEL if re.search(rx, t)), None)
    if _NAO_PECA.search(t) and not re.search(r"CONTRAV|TIRANTE|CORRENTE|BANZO|TER[ÇC]A|DIAGONA|MONTANTE", t):
        return None
    # chapa: CH 3/8" / CH #8 / CH200x70x8.00 / CHAPA 9,5
    m = _RE_CHAPA.search(t)
    if m and not re.search(r"\bU|\bL\d|\bW\d", t[:m.start()]):
        resto = m.group("resto").strip()
        esp = None
        b = re.search(r"#\s*(\d+)(?!\s*/)", resto)
        if b:
            from nucleo.perfis_fabrica import BITOLAS
            esp = BITOLAS.get(int(b.group(1)))
        if esp is None:
            f = re.search(r"(" + _POL + r")", resto)
            if f and "/" in f.group(1) or (f and '"' in f.group(1)):
                esp = _polegada(f.group(1))
        if esp is None:
            nums = [x for x in (_num(s) for s in re.split(r"[X\s]+", resto.replace('"', ""))) if x]
            if nums:
                esp = nums[-1]
        if esp and 0.4 <= esp <= 76.2:
            return {"perfil": "CH %s mm" % _fmt(esp), "chapa": True, "espessura": round(esp, 2), "mult": 1,
                    "papel": "chapa", "trecho": m.group(0).strip()}
    # barra redonda
    m = _RE_REDONDA.search(t)
    if m:
        d = _polegada(m.group(1)) if ("/" in m.group(1) or '"' in m.group(1)) else _num(m.group(1))
        if d and 4.0 <= d <= 80.0:
            pol = m.group(1).replace('"', "")
            nomes = (["Barra redonda Ø %s\"" % pol] if ("/" in m.group(1) or '"' in m.group(1)) else []) + \
                    ["Barra redonda %s" % _fmt(d), "Barra redonda Ø %s mm" % _fmt(d)]
            for n in nomes:
                p = _perfil_valido(n)
                if p is not None and abs(float(p.d or d) - d) <= 0.6:
                    return {"perfil": p.nome, "mult": 1, "papel": papel or "contraventamento",
                            "trecho": m.group(0).strip(), "redonda": True}
    for m in _RE_PERFIL.finditer(t):
        fam = m.group("fam")
        fam = "TR" if fam == "TUBO" else fam
        resto = m.group("resto").strip().rstrip("X").strip()
        mult = int(m.group("mult").strip()) if m.group("mult") else 1
        t_opcoes: List[float] = []
        t_pol = None
        b = re.search(r"#\s*(" + _POL + r"|\d+(?:[.,]\d+)?)", resto)
        if b:
            v = b.group(1)
            if "/" in v or '"' in v:
                t_pol = v.replace('"', "")
                x = _polegada(v)
                if x:
                    t_opcoes.append(round(x, 2))
            elif re.match(r"^\d+$", v) and int(v) < 30 and not re.search(r"MM", resto[b.end():b.end() + 4]):
                # a bitola da ABNT primeiro (é a do catálogo), depois a da tabela MSG
                from saida.dobras import ESPESSURAS_BITOLA
                from nucleo.perfis_fabrica import BITOLAS
                if int(v) in BITOLAS:
                    t_opcoes.append(BITOLAS[int(v)])
                t_opcoes += [x for x in ESPESSURAS_BITOLA.get(int(v), ()) if x not in t_opcoes]
            else:
                x = _num(v)
                if x:
                    t_opcoes.append(x)
            resto = resto[:b.start()]
        partes = [s for s in re.split(r"X", resto) if s.strip()]
        dims: List[float] = []
        for s in partes:
            s = s.strip().replace(" MM", "")
            if "/" in s or '"' in s:
                x = _polegada(s)
            else:
                x = _num(s.split()[0]) if s.split() else None
            if x is None:
                break
            dims.append(x)
        if not dims:
            continue
        if t_opcoes and len(dims) >= 3 and any(abs(dims[-1] - x) <= 0.1 for x in t_opcoes):
            dims = dims[:-1]                     # U100x50x3.04#11: a espessura escrita duas vezes
        if not t_opcoes and fam in ("U", "C", "UE", "Z", "ZE", "Z45", "CR", "L", "TQ", "TR") and len(dims) >= 2:
            # U100X50X3.04 / C150X50X17X2.25 / L50X50X2.25 / TQ 100x100x4: a última é a espessura
            ultimo_eh_t = dims[-1] <= 25.0 and (len(dims) >= 3 or fam == "L")
            if ultimo_eh_t:
                t_opcoes = [dims[-1]]
                dims = dims[:-1]
        tent = _candidatos(fam, dims, t_opcoes, t_pol)
        # primeiro o que está no catálogo com esse nome; depois o que o banco monta
        # (perfil dobrado da fábrica), com as duas grafias da bitola (ABNT e MSG)
        from nucleo import catalogo
        for nome in tent:
            it = catalogo.item(nome)
            if it is not None and it.eh_barra:
                p = _perfil_valido(it.nome)
                if p is not None and _plausivel(p, fam):
                    return {"perfil": p.nome, "mult": mult, "papel": papel, "trecho": m.group(0).strip()}
        for nome in tent:
            p = _perfil_valido(nome)
            if p is not None and _plausivel(p, fam):
                return {"perfil": p.nome, "mult": mult, "papel": papel, "trecho": m.group(0).strip()}
    return None


# ------------------------------------------------------------------------------------
# Geometria
# ------------------------------------------------------------------------------------

@dataclass(eq=False)
class _Seg:
    i: int
    ent: str
    idx: int
    a: Ponto2
    b: Ponto2
    camada: str
    anotacao: bool
    L: float = 0.0
    ux: float = 1.0
    uy: float = 0.0
    vista: int = -1
    peca: Optional[dict] = None
    fonte: str = ""
    texto: str = ""
    consumido: bool = False

    def __post_init__(self):
        dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
        self.L = math.hypot(dx, dy)
        if self.L > 0:
            self.ux, self.uy = dx / self.L, dy / self.L

    @property
    def ang(self) -> float:
        return math.degrees(math.atan2(self.uy, self.ux)) % 180.0

    def dist_linha(self, p: Ponto2) -> float:
        return abs((p[0] - self.a[0]) * self.uy - (p[1] - self.a[1]) * self.ux)

    def param(self, p: Ponto2) -> float:
        return ((p[0] - self.a[0]) * self.ux + (p[1] - self.a[1]) * self.uy) / (self.L or 1.0)

    def dist(self, p: Ponto2) -> float:
        t = max(0.0, min(1.0, self.param(p)))
        q = (self.a[0] + (self.b[0] - self.a[0]) * t, self.a[1] + (self.b[1] - self.a[1]) * t)
        return math.hypot(p[0] - q[0], p[1] - q[1])


@dataclass(eq=False)
class _Txt:
    ent: str
    texto: str
    centro: Ponto2
    ang: float                  # graus, mod 180
    h: float                    # altura em unidades do desenho
    largura: float
    vista: int = -1
    perfil: Optional[dict] = None
    usado: bool = False


def _dif_ang(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


class _Grade:
    """Índice espacial simples (células quadradas) para segmentos e pontos."""

    def __init__(self, cel: float):
        self.cel = max(cel, 1e-6)
        self.d: Dict[Tuple[int, int], List[int]] = collections.defaultdict(list)

    def _c(self, v: float) -> int:
        return int(math.floor(v / self.cel))

    def por_seg(self, s: _Seg):
        n = max(1, int(s.L / self.cel) + 1)
        vistos = set()
        for k in range(n + 1):
            t = k / n
            x = s.a[0] + (s.b[0] - s.a[0]) * t
            y = s.a[1] + (s.b[1] - s.a[1]) * t
            c = (self._c(x), self._c(y))
            if c not in vistos:
                vistos.add(c)
                self.d[c].append(s.i)

    def perto(self, p: Ponto2, r: float) -> Iterable[int]:
        x0, x1 = self._c(p[0] - r), self._c(p[0] + r)
        y0, y1 = self._c(p[1] - r), self._c(p[1] + r)
        vistos = set()
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 4000:
            x0, x1 = self._c(p[0]) - 30, self._c(p[0]) + 30
            y0, y1 = self._c(p[1]) - 30, self._c(p[1]) + 30
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                for i in self.d.get((cx, cy), ()):
                    if i not in vistos:
                        vistos.add(i)
                        yield i


def _dist_segs(a: _Seg, b: _Seg) -> float:
    """Distância entre dois trechos (zero se se cruzam)."""
    d = min(a.dist(b.a), a.dist(b.b), b.dist(a.a), b.dist(a.b))
    if d <= 1e-9:
        return 0.0
    # cruzam-se?
    r = (a.b[0] - a.a[0], a.b[1] - a.a[1])
    q = (b.b[0] - b.a[0], b.b[1] - b.a[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) > 1e-12:
        t = ((b.a[0] - a.a[0]) * q[1] - (b.a[1] - a.a[1]) * q[0]) / den
        u = ((b.a[0] - a.a[0]) * r[1] - (b.a[1] - a.a[1]) * r[0]) / den
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return 0.0
    return d


def _segmentos(des: Desenho) -> List[_Seg]:
    segs: List[_Seg] = []
    for e in des.entidades.values():
        if (e.atributos or {}).get("reconhecido"):
            continue                          # peças de um reconhecimento anterior
        cam = e.camada or "0"
        anot = bool(_ANOTACAO.search(cam))
        if isinstance(e, Linha):
            pares = [(tuple(e.a), tuple(e.b))]
        elif isinstance(e, Polilinha):
            vs = [tuple(v) for v in e.vertices or []]
            pares = list(zip(vs, vs[1:])) + ([(vs[-1], vs[0])] if e.fechada and len(vs) > 2 else [])
        else:
            continue
        for k, (a, b) in enumerate(pares):
            s = _Seg(len(segs), e.id, k, a, b, cam, anot)
            if s.L > 1e-6:
                segs.append(s)
    return segs


def _centro_texto(e: Texto, esc: float) -> Tuple[Ponto2, float, float]:
    h = float(e.altura or 2.5) * esc
    w = 0.78 * h * max(1, len(e.texto.strip()))
    a = math.radians(e.angulo or 0.0)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    dx = {"esquerda": w / 2, "centro": 0.0, "direita": -w / 2}.get(e.alinhamento, w / 2)
    dy = {"base": h / 2, "meio": 0.0, "topo": -h / 2}.get(e.vertical, h / 2)
    x, y = e.posicao
    return (x + ux * dx + vx * dy, y + uy * dx + vy * dy), h, w


# ------------------------------------------------------------------------------------
# Números de cota e escala
# ------------------------------------------------------------------------------------

_RE_COTA = re.compile(r"^\s*[+±]?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,3}))?\s*(MM|CM|M)?\s*$")
_RE_ESCALA = re.compile(r"(?:ESC(?:ALA)?\.?\s*:?\s*)?1\s*[:/]\s*(\d{1,4})\b")
ESCALAS_PAPEL = [1, 2, 2.5, 5, 7.5, 10, 12.5, 15, 20, 25, 30, 40, 50, 60, 75, 80, 100, 125, 150, 175, 200, 250, 300,
                 400, 500, 750, 1000]
#: DXF: mm, cm, m, polegada, pé — e detalhe ampliado ou reduzido no próprio desenho
FATORES_ARQUIVO = [1.0, 10.0, 1000.0, 25.4, 304.8, 0.1, 0.2, 0.25, 0.5, 2.0, 2.5, 4.0, 5.0]


def _valores_de_cota(texto: str) -> List[float]:
    """"2500" → [2500]; "2.500" → [2500, 2,5 m]; "6,00" → [6000] (metro); "12,5" → [12,5]."""
    t = texto.strip().upper().replace(" ", "")
    m = _RE_COTA.match(t)
    if not m:
        return []
    inteiro, dec, un = m.group(1), m.group(2), m.group(3)
    if un == "M":
        return [float(inteiro.replace(".", "") + "." + (dec or "0")) * 1000.0]
    if un == "CM":
        return [float(inteiro.replace(".", "") + "." + (dec or "0")) * 10.0]
    if "." in inteiro:
        v = float(inteiro.replace(".", ""))
        out = [v]
        if inteiro.count(".") == 1 and not dec:
            out.append(float(inteiro) * 1000.0)       # 2.500 em metro com ponto
        return out
    if dec is not None:
        v = float(inteiro + "." + dec)
        if len(dec) == 2 or v < 30:
            return [v * 1000.0]                          # 6,00 / 12,50: metro
        return [v]
    v = float(inteiro)
    return [v] if v >= 5 else []


def _moda_log(razoes: List[float], tol=0.025) -> Optional[Tuple[float, int]]:
    if not razoes:
        return None
    lg = sorted(math.log(r) for r in razoes if r > 0)
    melhor = (0, 0.0)
    j = 0
    for i in range(len(lg)):
        while lg[i] - lg[j] > 2 * tol:
            j += 1
        n = i - j + 1
        if n > melhor[0]:
            melhor = (n, (lg[i] + lg[j]) / 2)
    n, c = melhor
    grupo = [x for x in lg if abs(x - c) <= tol]
    return math.exp(sorted(grupo)[len(grupo) // 2]), len(grupo)


def _encaixar(fator: float, lista: Sequence[float], tol=0.035) -> float:
    melhor = min(lista, key=lambda x: abs(math.log(fator / x)))
    return float(melhor) if abs(math.log(fator / melhor)) <= tol else fator


# ------------------------------------------------------------------------------------
# Reconhecimento
# ------------------------------------------------------------------------------------

_TITULOS = [
    (r"PLANTA|COBERTURA|LOCA[ÇC][ÃA]O\s+DE\s+TER|TERÇAS?\s+E\s+CONTRAV", "planta"),
    (r"FACHADA\s+LAT|LATERAL|LONGITUDINAL|ELEVA[ÇC][ÃA]O\s+LAT|FECHAMENTO\s+LAT", "lateral"),
    (r"TESOURA|TRELI[ÇC]A|\bTR\s*\d|\bT\s*\d+\b", "trelica"),
    (r"P[ÓO]RTICO|CORTE|ELEVA[ÇC][ÃA]O|VISTA|FACHADA|FRONTAL|OITÃO|OITAO", "elevacao"),
    (r"DETALHE|DET\.", "detalhe"),
]


def reconhecer(des: Desenho, *, papel_unidade: Optional[bool] = None, fator: Optional[float] = None,
               avisar=None) -> dict:
    """Lê o desenho e devolve o que achou (não altera o desenho — veja `aplicar`).

    `papel_unidade`: o desenho está em mm de papel (veio de PDF) — a escala de cada vista
    é descoberta pelas cotas; None = pelos metadados do desenho. `fator`: força mm do
    modelo por unidade do desenho em todas as vistas.

    Devolve {vistas: [...], barras: [...], chapas: [...], textos_sem_linha: [...],
    avisos: [...], resumo: {...}}. Cada barra: {a, b, perfil, papel, mult, vista, fonte,
    texto, conferir}; cada vista: {id, titulo, tipo, caixa, fator, escala_texto, eixos}."""
    avisar = avisar or (lambda *a: None)
    if papel_unidade is None:
        # PDF importado: as linhas vêm marcadas com a origem; a maioria decide
        origem = (des.metadados or {}).get("origem_arquivo")
        if origem in ("pdf", "dxf"):
            papel_unidade = origem == "pdf"
        else:
            n_pdf = sum(1 for e in des.entidades.values()
                        if isinstance(e, (Linha, Polilinha)) and (e.atributos or {}).get("origem") == "pdf")
            n_lin = sum(1 for e in des.entidades.values() if isinstance(e, (Linha, Polilinha)))
            papel_unidade = n_lin > 0 and n_pdf > n_lin / 2
    esc = float(des.escala or 1.0)
    avisar("lendo as linhas…")
    segs = _segmentos(des)
    circulos = [e for e in des.entidades.values() if isinstance(e, Circulo) and not (e.atributos or {}).get("reconhecido")]
    textos: List[_Txt] = []
    for e in des.entidades.values():
        if isinstance(e, Texto) and e.texto.strip() and not (e.atributos or {}).get("reconhecido"):
            c, h, w = _centro_texto(e, esc)
            textos.append(_Txt(e.id, e.texto.strip(), c, (e.angulo or 0.0) % 180.0, h, w))
    fechadas = [e for e in des.entidades.values() if isinstance(e, Polilinha) and e.fechada]
    avisos: List[str] = []
    # retângulo riscado em X de canto a canto é o "cancelado" do desenho: o que está
    # dentro dele (e o próprio risco) não é o projeto a montar
    riscados = _areas_riscadas(segs)
    if riscados:
        def dentro(pts) -> bool:
            return any(all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts) for x0, y0, x1, y1 in riscados)
        n_antes = len(segs)
        segs = [x for x in segs if not dentro((x.a, x.b))]
        for k, x in enumerate(segs):
            x.i = k
        circulos = [c for c in circulos if not dentro((c.centro,))]
        textos = [t for t in textos if not dentro((t.centro,))]
        fechadas = [e for e in fechadas if not dentro(e.vertices)]
        avisos.append("%d área(s) riscada(s) em X (cancelada) ficaram fora do reconhecimento, com %d linha(s) — "
                      "apague o X se aquele conjunto é para valer." % (len(riscados), n_antes - len(segs)))
    if not segs:
        return {"vistas": [], "barras": [], "chapas": [], "textos_sem_linha": [], "avisos": ["o desenho não tem linhas."],
                "resumo": {"barras": 0, "vistas": 0}}
    xs = [p[0] for s in segs for p in (s.a, s.b)]
    ys = [p[1] for s in segs for p in (s.a, s.b)]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    hs = sorted(t.h for t in textos) or [diag / 300.0]
    h_med = hs[len(hs) // 2]

    # ---- 1. vistas: segmentos próximos (grade de união)
    avisar("separando as vistas…")
    gap = max(3.0 * h_med, 0.004 * diag)
    grade = _Grade(gap)
    for s in segs:
        grade.por_seg(s)
    pai = list(range(len(segs)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    # só as linhas de peça ligam uma vista à outra: cota, eixo e texto de anotação passam
    # de uma vista para a vizinha no desenho de fábrica e juntariam tudo numa vista só.
    # Duas linhas se ligam quando estão de fato a menos de um gap (não só na mesma célula
    # ou na vizinha: a elevação e a planta logo abaixo, a um gap e meio, são duas vistas)
    for (cx, cy), lista in grade.d.items():
        viz = [i for i in lista if not segs[i].anotacao]
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            viz.extend(i for i in grade.d.get((cx + dx, cy + dy), ()) if not segs[i].anotacao)
        if len(viz) < 2:
            continue
        for k in range(1, len(viz)):
            a_ = segs[viz[k]]
            for j in range(k):
                b_ = segs[viz[j]]
                ra, rb = raiz(a_.i), raiz(b_.i)
                if ra == rb:
                    continue
                if _dist_segs(a_, b_) <= 1.5 * gap:
                    pai[ra] = rb
    grupos: Dict[int, List[_Seg]] = collections.defaultdict(list)
    for s in segs:
        if not s.anotacao:
            grupos[raiz(s.i)].append(s)
    # a tira fina (a fila de cotas desenhada como linhas, debaixo da vista) vai para a
    # vista mais perto: é anotação dela, e as cotas dão a escala da vista
    def caixa_de(g):
        xs = [p[0] for s in g for p in (s.a, s.b)]
        ys = [p[1] for s in g for p in (s.a, s.b)]
        return min(xs), min(ys), max(xs), max(ys)

    def dist_caixas(c1, c2):
        dx = max(c1[0] - c2[2], 0.0, c2[0] - c1[2])
        dy = max(c1[1] - c2[3], 0.0, c2[1] - c1[3])
        return math.hypot(dx, dy)

    caixas = {k: caixa_de(g) for k, g in grupos.items()}
    for k in list(grupos):
        c = caixas[k]
        w, h = c[2] - c[0], c[3] - c[1]
        if min(w, h) >= 0.05 * max(w, h, 1e-9):
            continue
        perto = [(dist_caixas(c, caixas[j]), j) for j in grupos if j != k and len(grupos[j]) > len(grupos[k])]
        if perto and min(perto)[0] <= 3.0 * gap:
            j = min(perto)[1]
            grupos[j].extend(grupos[k])
            for s in grupos[k]:
                pai[raiz(s.i)] = raiz(grupos[j][0].i)
            caixas[j] = caixa_de(grupos[j])
            del grupos[k]
    ordem = sorted(grupos.values(), key=lambda g: -len(g))
    vistas: List[dict] = []
    for k, g in enumerate(ordem):
        for s in g:
            s.vista = k
        gx = [p[0] for s in g for p in (s.a, s.b)]
        gy = [p[1] for s in g for p in (s.a, s.b)]
        vistas.append({"id": k, "caixa": [[min(gx), min(gy)], [max(gx), max(gy)]], "segs": g, "textos": [],
                       "titulo": "", "tipo": "", "fator": None, "escala_texto": None, "eixos": []})

    # só interessam os textos que dizem alguma coisa ao reconhecimento: perfil, cota,
    # título, escala, eixo, sigla — nota de montagem, carimbo e afins ficam de fora
    avisar("lendo os perfis escritos…")
    uteis = []
    for t in textos:
        u = _limpo(t.texto)
        t.perfil = perfil_do_texto(t.texto)
        titulo = any(re.search(rx, u) for rx, _tp in _TITULOS)
        sigla = re.match(r"^\s*[A-Z]{1,3}\d{0,2}\s*[-–=:)]", u)
        if t.perfil or _valores_de_cota(t.texto) or len(u) <= 4 or _RE_ESCALA.search(u) or titulo or sigla:
            uteis.append(t)
    textos = uteis
    # textos → vista da linha mais perto (busca em raio crescente)
    for t in textos:
        melhor, dmin = -1, float("inf")
        for r in (1.5 * t.h, 6 * t.h, max(6 * t.h, gap)):
            for i in grade.perto(t.centro, r):
                s = segs[i]
                if s.vista < 0 or abs(s.a[0] - t.centro[0]) > r + s.L or abs(s.a[1] - t.centro[1]) > r + s.L:
                    continue
                d = s.dist(t.centro)
                if d < dmin:
                    dmin, melhor = d, s.vista
            if melhor >= 0 and dmin <= r:
                break
        if melhor < 0:
            # título afastado: a vista cuja caixa está mais perto
            for v in vistas:
                (x0, y0), (x1, y1) = v["caixa"]
                dx = max(x0 - t.centro[0], 0, t.centro[0] - x1)
                dy = max(y0 - t.centro[1], 0, t.centro[1] - y1)
                d = math.hypot(dx, dy)
                if d < dmin and d < 0.25 * max(x1 - x0, y1 - y0) + 12 * t.h:
                    dmin, melhor = d, v["id"]
        t.vista = melhor
        if melhor >= 0:
            vistas[melhor]["textos"].append(t)

    # ---- 2. legenda de siglas
    legenda = _legenda(textos)

    # ---- 3. por vista: título, escala, eixos, rótulos, herança, linha dupla, papel
    barras: List[dict] = []
    chapas: List[dict] = []
    sem_linha: List[dict] = []
    from nucleo2d import reconhecer_geo as geo
    fech_por_id = {e.id: e for e in fechadas}
    analises: Dict[int, dict] = {}
    ativas: List[dict] = []
    for v in vistas:
        g = v["segs"]
        if len(g) < 2 and not any(t.perfil for t in v["textos"]):
            continue
        ativas.append(v)
        v["titulo"], v["tipo"], v["escala_texto"] = _titulo(v, textos)
        v["fator"], v["fator_origem"] = _fator_da_vista(v, segs, grade, papel_unidade, fator, esc)
        analises[v["id"]] = geo.analisar(v, fech_por_id)
    # sem título, a forma diz o que a vista é (pórtico, planta, fachada, repetição)
    ref = geo.classificar(ativas, analises)
    if not papel_unidade and not fator and geo.unidade_em_cm(ativas, analises):
        for v in ativas:
            v["fator"] = float(v["fator"] or 1.0) * 10.0
            v["fator_origem"] = "cm"
        avisos.append("o desenho parece estar em centímetros (o pórtico teria menos de 6 m de vão em mm): tomei "
                      "10 mm por unidade do desenho — se estiver errado, force a escala ao gerar o 3D.")
    avisar("lendo as barras…")
    for v in ativas:
        v["eixos"] = _eixos(v, circulos, textos, grade, segs)
        v["_fechadas"] = fechadas
        _rotular(v, segs, grade, legenda)
        _herdar(v)
        bs, chs = _barras_da_vista(v, segs, grade)
        if not bs:
            # nenhum perfil escrito nesta vista: as barras saem da forma, sem perfil
            bs, eixos_geo = geo.barras_da_vista(v, analises[v["id"]], ref)
            if eixos_geo and not v["eixos"]:
                v["eixos"] = eixos_geo
        barras.extend(bs)
        chapas.extend(chs)
        for t in v["textos"]:
            if t.perfil and not t.usado and not t.perfil.get("chapa"):
                sem_linha.append({"texto": t.texto, "perfil": t.perfil["perfil"], "vista": v["id"],
                                  "ponto": [round(t.centro[0], 2), round(t.centro[1], 2)]})
    geo.conferir_pilares(ativas, barras, analises)
    vistas_uteis = [v for v in vistas if any(b["vista"] == v["id"] for b in barras) or v.get("eixos")]
    if not barras:
        avisos.append("nenhum perfil escrito ficou ligado a uma linha: o desenho tem os perfis em texto? "
                      "(PDF digitalizado ou texto em fonte SHX não se lê)")
    sem_perfil = collections.Counter(b["papel"] for b in barras if not b["perfil"])
    if sem_perfil:
        avisos.append("%d barra(s) reconhecida(s) só pela forma, sem perfil escrito (%s): o perfil de cada papel é "
                      "escolhido ao gerar o modelo 3D." % (sum(sem_perfil.values()),
                                                           ", ".join("%d %s" % (n, p) for p, n in sem_perfil.most_common())))
    repetidas = [v for v in vistas if v.get("repetida") is not None]
    if repetidas:
        avisos.append("%d vista(s) repetida(s) (mesmo tamanho e as mesmas linhas de outra) ficaram de fora."
                      % len(repetidas))
    for v in vistas_uteis:
        if v.get("fator_origem") == "padrao":
            avisos.append("vista \"%s\": escala não encontrada pelas cotas; usei %s — confira."
                          % (v["titulo"] or "sem título", ("1:%g" % v["fator"]) if papel_unidade else "mm"))
    saida_vistas = []
    for v in vistas_uteis:
        saida_vistas.append({"id": v["id"], "titulo": v["titulo"], "tipo": v["tipo"], "caixa": v["caixa"],
                             "fator": v["fator"], "fator_origem": v.get("fator_origem"),
                             "escala_texto": v["escala_texto"], "eixos": v["eixos"],
                             "barras": sum(1 for b in barras if b["vista"] == v["id"])})
    resumo = {"vistas": len(saida_vistas), "barras": len(barras), "chapas": len(chapas),
              "a_conferir": sum(1 for b in barras if b["conferir"]),
              "perfis": dict(collections.Counter(b["perfil"] for b in barras if b["perfil"])),
              "papeis": dict(collections.Counter(b["papel"] for b in barras)),
              "sem_perfil": dict(sem_perfil), "repetidas": len(repetidas),
              "textos_de_perfil": sum(1 for t in textos if t.perfil), "sem_linha": len(sem_linha)}
    return {"vistas": saida_vistas, "barras": barras, "chapas": chapas, "textos_sem_linha": sem_linha,
            "avisos": avisos, "resumo": resumo, "papel_unidade": bool(papel_unidade)}


def _areas_riscadas(segs: List[_Seg]) -> List[Tuple[float, float, float, float]]:
    """Retângulos com as duas diagonais traçadas de canto a canto (o X do "cancelado"):
    devolve as caixas (x0, y0, x1, y1), com uma folga, para o que está dentro sair."""
    if not segs:
        return []
    xs = [p[0] for x in segs for p in (x.a, x.b)]
    ys = [p[1] for x in segs for p in (x.a, x.b)]
    diag_total = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    # só as linhas longas podem ser o risco (a diagonal do cancelado atravessa vistas)
    longas = [x for x in segs if x.L >= 0.1 * diag_total and 5.0 < x.ang < 175.0 and abs(x.ang - 90.0) > 5.0]
    if len(longas) < 2:
        return []
    horiz = [x for x in segs if x.L >= 0.1 * diag_total and (x.ang < 1.0 or x.ang > 179.0)]
    caixas = []
    for i, d1 in enumerate(longas):
        for d2 in longas[i + 1:]:
            c1 = [d1.a, d1.b]
            c2 = [d2.a, d2.b]
            xs4 = [p[0] for p in c1 + c2]
            ys4 = [p[1] for p in c1 + c2]
            x0, x1, y0, y1 = min(xs4), max(xs4), min(ys4), max(ys4)
            w, h = x1 - x0, y1 - y0
            if w <= 0 or h <= 0:
                continue
            tol = 0.01 * math.hypot(w, h)
            cantos = [(x0, y0), (x1, y1), (x0, y1), (x1, y0)]
            # cada diagonal liga dois cantos opostos, e as duas usam os quatro cantos
            usados = set()
            for p in c1 + c2:
                k = min(range(4), key=lambda j: math.dist(p, cantos[j]))
                if math.dist(p, cantos[k]) > tol:
                    break
                usados.add(k)
            else:
                if usados != {0, 1, 2, 3}:
                    continue
                # o retângulo tem de estar desenhado: as bordas de cima e de baixo
                bordas = sum(1 for x in horiz if abs(x.a[1] - x.b[1]) <= tol
                             and any(abs(x.a[1] - yy) <= tol for yy in (y0, y1))
                             and min(x.a[0], x.b[0]) <= x0 + tol and max(x.a[0], x.b[0]) >= x1 - tol)
                if bordas < 2:
                    continue
                # o cancelado cerca vistas inteiras e nada o atravessa; o painel de
                # contraventamento em X tem terças e tesouras passando pela borda
                X0, Y0, X1, Y1 = x0 - tol, y0 - tol, x1 + tol, y1 + tol
                ins = lambda p: X0 <= p[0] <= X1 and Y0 <= p[1] <= Y1                  # noqa: E731
                miolo = lambda p: x0 + tol < p[0] < x1 - tol and y0 + tol < p[1] < y1 - tol   # noqa: E731
                dentro = cruzam = 0
                for x in segs:
                    a_in, b_in = ins(x.a), ins(x.b)
                    if a_in and b_in:
                        dentro += 1
                    elif (a_in and miolo(x.a)) or (b_in and miolo(x.b)):
                        cruzam += 1
                if dentro >= 30 and cruzam <= max(2, 0.01 * dentro):
                    caixas.append((X0, Y0, X1, Y1))
    return caixas


def _legenda(textos: List[_Txt]) -> Dict[str, dict]:
    """Siglas definidas no desenho: "BS – BANZO SUPERIOR – U150x60x20#13", ou a sigla
    num texto e o perfil noutro, na mesma linha, à direita."""
    mapa: Dict[str, dict] = {}
    for t in textos:
        m = re.match(r"^\s*([A-Z]{1,3}\d{0,2})\s*[-–=:)]\s*(.+)$", _limpo(t.texto))
        if m and t.perfil:
            p = dict(t.perfil)
            p["papel"] = p.get("papel") or next((pp for rx, pp in PALAVRAS_PAPEL if re.search(rx, m.group(1))), None)
            mapa[m.group(1)] = p
            t.usado = True
    siglas = [t for t in textos if re.fullmatch(r"[A-Z]{1,3}\d{0,2}", _limpo(t.texto)) and not t.perfil]
    com_perfil = [t for t in textos if t.perfil]
    for s in siglas:
        chave = _limpo(s.texto)
        if chave in mapa:
            continue
        for t in com_perfil:
            if _dif_ang(s.ang, t.ang) > 2 or abs(s.h - t.h) > 0.5 * s.h:
                continue
            a = math.radians(s.ang)
            dx, dy = t.centro[0] - s.centro[0], t.centro[1] - s.centro[1]
            ao_longo = dx * math.cos(a) + dy * math.sin(a)
            fora = abs(-dx * math.sin(a) + dy * math.cos(a))
            if fora < 0.6 * s.h and 0 < ao_longo < 40 * s.h:
                p = dict(t.perfil)
                p["papel"] = p.get("papel") or next((pp for rx, pp in PALAVRAS_PAPEL if re.search(rx, chave)), None)
                mapa[chave] = p
                t.usado = True          # o texto da legenda não é rótulo de barra
                break
    return mapa


def _titulo(v: dict, textos: List[_Txt]) -> Tuple[str, str, Optional[float]]:
    (x0, y0), (x1, y1) = v["caixa"]
    cands = []
    esc_txt = None
    for t in v["textos"]:
        u = _limpo(t.texto)
        m = _RE_ESCALA.search(u)
        if m and ("ESC" in u or len(u) <= 12):
            esc_txt = float(m.group(1))
        for rx, tipo in _TITULOS:
            if re.search(rx, u) and not t.perfil:
                fora = t.centro[1] < y0 or t.centro[1] > y1
                cands.append((t.h * (1.5 if fora else 1.0), t.texto, tipo))
                break
    if not cands:
        return "", "", esc_txt
    cands.sort(key=lambda c: -c[0])
    return cands[0][1], cands[0][2], esc_txt


def _fator_da_vista(v: dict, segs: List[_Seg], grade: _Grade, papel: bool, forcado: Optional[float], esc: float):
    if forcado:
        return float(forcado), "informado"
    razoes: List[float] = []
    for t in v["textos"]:
        vals = _valores_de_cota(t.texto)
        if not vals:
            continue
        L = _linha_da_cota(t, v, segs, grade)
        if L:
            for val in vals:
                razoes.append(val / L)
    moda = _moda_log(razoes)
    if moda and moda[1] >= 2:
        lista = ESCALAS_PAPEL if papel else FATORES_ARQUIVO
        f = _encaixar(moda[0], lista, tol=0.06)
        if f in lista:
            return f, "cotas"
        # cotas que não fecham com escala nenhuma (cota de trecho, texto de outra coisa):
        # fica a escala do título ou a do arquivo
    if moda and not papel and moda[1] >= 2:
        return 1.0, "padrao"
    if papel and v.get("escala_texto"):
        return float(v["escala_texto"]), "titulo"
    return (float(v.get("escala_texto") or 50.0) if papel else 1.0), "padrao"


def _linha_da_cota(t: _Txt, v: dict, segs: List[_Seg], grade: _Grade) -> Optional[float]:
    """Comprimento da linha de cota do número `t`: paralela ao texto, logo abaixo dele,
    com o número no meio. A linha pode vir partida em volta do número (ou em duas
    metades com seta): os trechos colineares encostados são somados."""
    perto = []
    for i in grade.perto(t.centro, 3 * t.h + t.largura):
        s = segs[i]
        if (s.vista >= 0 and s.vista != v["id"]) or _dif_ang(s.ang, t.ang) > 3 or s.dist_linha(t.centro) > 2.2 * t.h:
            continue
        perto.append(s)
    if not perto:
        return None
    ref = min(perto, key=lambda s: s.dist_linha(t.centro))
    off = ref.dist_linha(t.centro)
    ux, uy = ref.ux, ref.uy
    iv = []
    for s in perto:
        if abs(s.dist_linha(t.centro) - off) > 0.15 * t.h:
            continue
        a = s.a[0] * ux + s.a[1] * uy
        b = s.b[0] * ux + s.b[1] * uy
        iv.append((min(a, b), max(a, b)))
    ja = {s.i for s in perto}
    for i in grade.perto(t.centro, t.largura + 8 * t.h):
        s = segs[i]
        if i in ja or (s.vista >= 0 and s.vista != v["id"]) or _dif_ang(s.ang, t.ang) > 3:
            continue
        if abs(s.dist_linha(t.centro) - off) > 0.15 * t.h or abs(ref.dist_linha(s.a)) > 0.15 * t.h:
            continue
        a = s.a[0] * ux + s.a[1] * uy
        b = s.b[0] * ux + s.b[1] * uy
        iv.append((min(a, b), max(a, b)))
    iv.sort()
    c = t.centro[0] * ux + t.centro[1] * uy
    folga = t.largura + 2 * t.h
    # o trecho que passa sob o número; ou os dois que param dos lados dele (linha partida
    # em volta do texto). Trechos que só se encostam são cotas vizinhas, não se somam.
    trecho = next(((a, b) for a, b in iv if a <= c <= b), None)
    if trecho is None:
        esq = max((x for x in iv if x[1] < c), key=lambda x: x[1], default=None)
        dir_ = min((x for x in iv if x[0] > c), key=lambda x: x[0], default=None)
        if esq and dir_ and dir_[0] - esq[1] <= folga:
            trecho = (esq[0], dir_[1])
    if trecho is None:
        return None
    a, b = trecho
    # a linha de cota costuma parar na seta: vai até a linha de chamada (perpendicular)
    # mais perto de cada ponta, se estiver a menos de 1,5 altura de texto
    nx, ny = -uy, ux
    d0 = t.centro[0] * nx + t.centro[1] * ny - off * (1 if (t.centro[0] - ref.a[0]) * nx + (t.centro[1] - ref.a[1]) * ny > 0 else -1)
    melhor_a, melhor_b = None, None
    for i in grade.perto(t.centro, (b - a) / 2 + 3 * t.h):
        s = segs[i]
        if (s.vista >= 0 and s.vista != v["id"]) or _dif_ang(s.ang, t.ang) < 80:
            continue
        # onde a linha de chamada corta a reta da cota
        pa, pb = s.a[0] * nx + s.a[1] * ny, s.b[0] * nx + s.b[1] * ny
        if (pa - d0) * (pb - d0) > 0 and min(abs(pa - d0), abs(pb - d0)) > 1.5 * t.h:
            continue
        x = s.a[0] * ux + s.a[1] * uy
        if a - 1.5 * t.h <= x <= a + 0.2 * t.h and (melhor_a is None or abs(x - a) < abs(melhor_a - a)):
            melhor_a = x
        if b - 0.2 * t.h <= x <= b + 1.5 * t.h and (melhor_b is None or abs(x - b) < abs(melhor_b - b)):
            melhor_b = x
    # ponta de seta: vértice em cima da reta da cota, logo além da ponta
    ponta_a = ponta_b = None
    for i in grade.perto(t.centro, (b - a) / 2 + 3 * t.h):
        s = segs[i]
        if s.vista >= 0 and s.vista != v["id"]:
            continue
        for q in (s.a, s.b):
            if abs(q[0] * nx + q[1] * ny - d0) > 0.15 * t.h:
                continue
            x = q[0] * ux + q[1] * uy
            if a - 1.5 * t.h <= x < a - 1e-6 and (ponta_a is None or x > ponta_a):
                ponta_a = x
            if b + 1e-6 < x <= b + 1.5 * t.h and (ponta_b is None or x < ponta_b):
                ponta_b = x
    a = min([a] + [x for x in (melhor_a, ponta_a) if x is not None])
    b = max([b] + [x for x in (melhor_b, ponta_b) if x is not None])
    L = b - a
    u = (c - a) / L if L else 0
    if L >= 2 * t.h and 0.2 <= u <= 0.8:
        return L
    return None


def _eixos(v: dict, circulos: List[Circulo], textos: List[_Txt], grade: _Grade, segs: List[_Seg]) -> List[dict]:
    """Eixos do projeto: balão (círculo com 1 a 3 caracteres dentro) e a linha longa que
    chega nele. Devolve [{rotulo, ponto, dir, pos}] — pos é a coordenada perpendicular."""
    (x0, y0), (x1, y1) = v["caixa"]
    folga = 0.1 * max(x1 - x0, y1 - y0)
    eixos = []
    vistos = set()
    for c in circulos:
        cx, cy = c.centro
        if not (x0 - folga <= cx <= x1 + folga and y0 - folga <= cy <= y1 + folga):
            continue
        r = float(c.raio)
        dentro = [t for t in v["textos"] + [t for t in textos if t.vista < 0]
                  if math.hypot(t.centro[0] - cx, t.centro[1] - cy) <= r * 0.9
                  and re.fullmatch(r"[A-Z0-9]{1,3}'?", t.texto.strip().upper())]
        if not dentro:
            continue
        rot = dentro[0].texto.strip().upper()
        melhor = None
        for i in grade.perto((cx, cy), 2 * r):
            s = segs[i]
            if s.L < 6 * r:
                continue
            da, db = math.hypot(s.a[0] - cx, s.a[1] - cy), math.hypot(s.b[0] - cx, s.b[1] - cy)
            if min(da, db) <= 1.6 * r or s.dist((cx, cy)) <= 0.3 * r:
                if melhor is None or s.L > melhor.L:
                    melhor = s
        if melhor is None:
            continue
        ang = melhor.ang
        # coordenada perpendicular do eixo (para eixo vertical: o x)
        nx, ny = -melhor.uy, melhor.ux
        if nx < -1e-9 or (abs(nx) <= 1e-9 and ny < 0):
            nx, ny = -nx, -ny
        pos = melhor.a[0] * nx + melhor.a[1] * ny
        chave = (rot, round(ang), round(pos / max(r, 1e-6)))
        if chave in vistos:
            continue
        vistos.add(chave)
        melhor.consumido = True
        eixos.append({"rotulo": rot, "ponto": [round(cx, 3), round(cy, 3)], "ang": round(ang, 2),
                      "dir": [round(melhor.ux, 6), round(melhor.uy, 6)], "pos": round(pos, 3),
                      "a": [round(melhor.a[0], 3), round(melhor.a[1], 3)], "b": [round(melhor.b[0], 3), round(melhor.b[1], 3)]})
    return eixos


def _rotular(v: dict, segs: List[_Seg], grade: _Grade, legenda: Dict[str, dict]):
    """Liga cada texto de perfil (ou sigla da legenda) à linha que ele acompanha."""
    candidatos = [s for s in v["segs"] if not s.anotacao and not s.consumido]
    ids = {s.i for s in candidatos}
    rotulos = []
    for t in v["textos"]:
        if t.usado:
            continue
        p = t.perfil
        if p is None:
            sig = _limpo(t.texto)
            if sig in legenda:
                p = dict(legenda[sig])
                p["trecho"] = sig
        if p is None:
            continue
        rotulos.append((t, p))
    # a barra que o texto acompanha (paralela, perto); senão a linha de chamada — um
    # traço curto (ou na camada de anotação) com uma ponta no texto e a outra na barra
    for t, p in rotulos:
        alvo = None
        if True:
            for i in grade.perto(t.centro, t.largura / 2 + 2 * t.h):
                s = segs[i]
                if (s.vista >= 0 and s.vista != v["id"]) or _dif_ang(s.ang, t.ang) < 15 or s.peca is not None:
                    continue
                if not (s.anotacao or s.L < 8 * t.h):
                    continue
                for pa, pb in ((s.a, s.b), (s.b, s.a)):
                    if _perto_do_texto(pa, t):
                        for j in grade.perto(pb, 0.6 * t.h):
                            if j != s.i and j in ids and segs[j].dist(pb) <= 0.4 * t.h and _dif_ang(segs[j].ang, s.ang) > 10:
                                alvo = segs[j]
                                break
                    if alvo:
                        break
                if alvo:
                    s.consumido = True
                    break
        if alvo is None:
            alvo = _paralela_mais_perto(t, grade, segs, ids, papel=p.get("papel"), planta=v.get("tipo") == "planta")
        if alvo is None:
            continue
        if alvo.peca is None or (alvo.fonte != "rótulo"):
            alvo.peca = p
            alvo.fonte = "rótulo"
            alvo.texto = t.texto
            t.usado = True
        elif alvo.peca.get("perfil") == p.get("perfil"):
            t.usado = True


def _perto_do_texto(p: Ponto2, t: _Txt) -> bool:
    a = math.radians(t.ang)
    dx, dy = p[0] - t.centro[0], p[1] - t.centro[1]
    ao_longo = abs(dx * math.cos(a) + dy * math.sin(a))
    fora = abs(-dx * math.sin(a) + dy * math.cos(a))
    return ao_longo <= t.largura / 2 + 1.2 * t.h and fora <= 1.4 * t.h


def _paralela_mais_perto(t: _Txt, grade: _Grade, segs: List[_Seg], ids: set, papel: Optional[str] = None,
                         planta: bool = False) -> Optional[_Seg]:
    melhor, nota = None, float("inf")
    for i in grade.perto(t.centro, 4 * t.h + t.largura / 2):
        if i not in ids:
            continue
        s = segs[i]
        if s.L < 1.5 * t.h:
            continue
        # a palavra do rótulo manda: PILAR é linha em pé; terça, longarina e banzo, deitada
        em_pe = abs(s.ang - 90.0) < 10.0
        if not planta and ((papel == "pilar" and not em_pe) or (papel in ("terça", "longarina", "banzo") and em_pe)):
            continue
        u = s.param(t.centro)
        if _dif_ang(s.ang, t.ang) <= 8:
            d = s.dist_linha(t.centro)
            if d > 3.5 * t.h or u < -0.15 or u > 1.15:
                continue
            n = d / t.h + (0.0 if 0 <= u <= 1 else 2.0) + (0.0 if s.L >= t.largura * 0.6 else 1.5)
        elif _dif_ang(s.ang, t.ang) >= 75:
            # texto horizontal ao lado de pilar em pé
            d = s.dist(t.centro) - t.largura / 2
            if d > 3.0 * t.h or not (0.0 <= u <= 1.0):
                continue
            n = 1.5 + max(d, 0) / t.h
        else:
            continue
        if n < nota:
            melhor, nota = s, n
    return melhor


def _nos(g: List[_Seg], tol: float) -> Dict[Tuple[int, int], List[_Seg]]:
    nos: Dict[Tuple[int, int], List[_Seg]] = collections.defaultdict(list)
    for s in g:
        for p in (s.a, s.b):
            nos[(int(round(p[0] / tol)), int(round(p[1] / tol)))].append(s)
    return nos


def _herdar(v: dict):
    """O perfil segue pelos trechos colineares ligados, pela mesma polilinha e, numa camada
    em que todos os rótulos dizem o mesmo perfil, pelas linhas sem rótulo."""
    g = [s for s in v["segs"] if not s.anotacao and not s.consumido]
    if not g:
        return
    hs = [t.h for t in v["textos"]] or [max(s.L for s in g) / 100]
    tol = max(sorted(hs)[len(hs) // 2] * 0.25, 1e-3)
    nos = _nos(g, tol)

    def chave(p):
        return (int(round(p[0] / tol)), int(round(p[1] / tol)))

    # a mesma polilinha aberta é a mesma barra (o banzo desenhado de uma vez); a fechada é
    # contorno (de chapa, de perfil em linha dupla) e não passa o perfil adiante
    fechadas = {e.id for e in v.get("_fechadas", ())}
    por_ent: Dict[str, List[_Seg]] = collections.defaultdict(list)
    for s in g:
        if s.ent not in fechadas:
            por_ent[s.ent].append(s)
    fila = [s for s in g if s.peca is not None]
    while fila:
        s = fila.pop()
        viz = list(por_ent.get(s.ent, ()))
        for p in (s.a, s.b):
            k = chave(p)
            no = []
            for dk in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                no.extend(nos.get((k[0] + dk[0], k[1] + dk[1]), ()))
            no = list({x.i: x for x in no}.values())
            for x in no:
                if x is s or _dif_ang(x.ang, s.ang) > 2.0 or x.camada != s.camada:
                    continue
                # nó com outras barras chegando e trecho seguinte muito mais curto: é
                # outra peça (o montante da ponta em cima do pilar), não a continuação
                if len(no) > 2 and x.L < 0.35 * s.L:
                    continue
                viz.append(x)
        for x in viz:
            if x.peca is None and x is not s:
                x.peca = s.peca
                x.fonte = "cadeia"
                x.texto = s.texto
                fila.append(x)
    # camada homogênea
    por_cam: Dict[str, List[_Seg]] = collections.defaultdict(list)
    for s in g:
        por_cam[s.camada].append(s)
    for cam, lista in por_cam.items():
        rot = [s for s in lista if s.fonte == "rótulo"]
        perfis = {s.peca["perfil"] for s in rot}
        if len(rot) < 3 or len(perfis) != 1:
            continue
        Ls = sorted(s.L for s in lista if s.peca is not None)
        Lmin = 0.3 * Ls[len(Ls) // 2]
        for s in lista:
            if s.peca is None and s.L >= Lmin:
                s.peca = rot[0].peca
                s.fonte = "camada"
                s.texto = rot[0].texto


def _barras_da_vista(v: dict, segs: List[_Seg], grade: _Grade) -> Tuple[List[dict], List[dict]]:
    """Segmentos com peça → barras (linha dupla fundida no eixo, colineares emendados)."""
    f = float(v.get("fator") or 1.0)
    g = [s for s in v["segs"] if s.peca is not None and not s.consumido]
    brutas: List[dict] = []
    chapas: List[dict] = []
    ja = set()
    for s in sorted(g, key=lambda s: (s.fonte != "rótulo", -s.L)):
        if s.i in ja:
            continue
        p = s.peca
        if p.get("chapa"):
            continue
        ja.add(s.i)
        eixo = _linha_dupla(s, v, segs, grade, f, ja)
        a, b = eixo if eixo else (s.a, s.b)
        brutas.append({"a": a, "b": b, "peca": p, "fonte": s.fonte, "texto": s.texto,
                       "dupla": bool(eixo), "camada": s.camada})
    fundidas = _emendar(brutas, v)
    saida = []
    for b in fundidas:
        papel = b["peca"].get("papel") or ""
        saida.append({"a": [round(b["a"][0], 3), round(b["a"][1], 3)], "b": [round(b["b"][0], 3), round(b["b"][1], 3)],
                      "perfil": b["peca"]["perfil"], "papel": papel, "mult": int(b["peca"].get("mult") or 1),
                      "vista": v["id"], "fonte": b["fonte"], "texto": b["texto"], "dupla": b["dupla"],
                      "conferir": b["fonte"] == "camada"})
    _papeis(saida, v)
    return saida, chapas


def _linha_dupla(s: _Seg, v: dict, segs: List[_Seg], grade: _Grade, f: float, ja: set):
    """Se a barra foi desenhada com as duas faces, devolve o eixo (a, b) e consome as
    outras linhas da faixa; senão None."""
    p = s.peca
    from nucleo import catalogo
    perf = catalogo.perfil_de(p["perfil"])
    if perf is None:
        return None
    alvos = [x / f for x in (float(perf.d or 0), float(perf.bf or 0)) if x > 0]
    if not alvos or max(alvos) < 1e-6:
        return None
    dmax = 1.3 * max(alvos)
    offs = [(0.0, s)]
    nx, ny = -s.uy, s.ux
    for i in grade.perto(((s.a[0] + s.b[0]) / 2, (s.a[1] + s.b[1]) / 2), s.L / 2 + dmax):
        x = segs[i]
        if x is s or x.vista != s.vista or x.anotacao or _dif_ang(x.ang, s.ang) > 1.0:
            continue
        if x.peca is not None and x.peca.get("perfil") != p["perfil"]:
            continue
        o = (x.a[0] - s.a[0]) * nx + (x.a[1] - s.a[1]) * ny
        if abs(o) > dmax or abs(o) < 1e-9:
            continue
        t0, t1 = sorted((s.param(x.a), s.param(x.b)))
        sobre = max(0.0, min(1.0, t1) - max(0.0, t0)) * s.L
        if sobre < 0.5 * min(s.L, x.L):
            continue
        offs.append((o, x))
    if len(offs) < 2:
        return None
    melhor = None
    valores = sorted({round(o, 6) for o, _ in offs})
    for i, o1 in enumerate(valores):
        for o2 in valores[i + 1:]:
            if not (o1 <= 1e-9 <= o2 + 1e-9):
                continue
            larg = o2 - o1
            for alvo in alvos:
                if abs(larg - alvo) <= 0.2 * alvo and (melhor is None or larg > melhor[1] - melhor[0]):
                    melhor = (o1, o2)
    if melhor is None:
        return None
    o1, o2 = melhor
    faixa = [x for o, x in offs if o1 - 1e-6 <= o <= o2 + 1e-6]
    ts = []
    for x in faixa:
        ts += [s.param(x.a), s.param(x.b)]
        if x is not s:
            x.consumido = True
            ja.add(x.i)
    t0, t1 = min(ts), max(ts)
    om = (o1 + o2) / 2
    a = (s.a[0] + s.ux * t0 * s.L + nx * om, s.a[1] + s.uy * t0 * s.L + ny * om)
    b = (s.a[0] + s.ux * t1 * s.L + nx * om, s.a[1] + s.uy * t1 * s.L + ny * om)
    return a, b


def _emendar(brutas: List[dict], v: dict) -> List[dict]:
    """Trechos colineares, encostados e com a mesma peça viram uma barra só."""
    hs = [t.h for t in v["textos"]] or [1.0]
    tol = max(sorted(hs)[len(hs) // 2] * 0.3, 1e-3)
    feitas = list(brutas)
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(feitas)):
            bi = feitas[i]
            if bi is None:
                continue
            for j in range(i + 1, len(feitas)):
                bj = feitas[j]
                if bj is None or bj["peca"]["perfil"] != bi["peca"]["perfil"]:
                    continue
                ai = math.degrees(math.atan2(bi["b"][1] - bi["a"][1], bi["b"][0] - bi["a"][0])) % 180
                aj = math.degrees(math.atan2(bj["b"][1] - bj["a"][1], bj["b"][0] - bj["a"][0])) % 180
                if _dif_ang(ai, aj) > 1.0:
                    continue
                pares = [(p, q) for p in (bi["a"], bi["b"]) for q in (bj["a"], bj["b"])]
                if min(math.dist(p, q) for p, q in pares) > tol:
                    continue
                pts = [bi["a"], bi["b"], bj["a"], bj["b"]]
                ux, uy = math.cos(math.radians(ai)), math.sin(math.radians(ai))
                pts.sort(key=lambda p: p[0] * ux + p[1] * uy)
                bi = dict(bi, a=pts[0], b=pts[-1], fonte=min(bi["fonte"], bj["fonte"], key=_peso_fonte),
                          texto=bi["texto"] or bj["texto"], dupla=bi["dupla"] or bj["dupla"])
                feitas[i] = bi
                feitas[j] = None
                mudou = True
    return [b for b in feitas if b is not None]


def _peso_fonte(f: str) -> int:
    return {"rótulo": 0, "cadeia": 1, "camada": 2}.get(f, 3)


def _papeis(barras: List[dict], v: dict):
    """Papel de cada barra: o que o texto disse; senão pela vista e pela geometria."""
    tipo = v.get("tipo") or ""
    if not barras:
        return
    inclinadas = sum(1 for b in barras if 8 < _ang(b) % 180 < 82 or 98 < _ang(b) % 180 < 172)
    trelica = tipo == "trelica" or (tipo in ("elevacao", "") and inclinadas >= 4)
    if trelica and not tipo:
        v["tipo"] = "trelica"
    hs = [t.h for t in v["textos"]] or [1.0]
    tol = max(sorted(hs)[len(hs) // 2] * 0.5, 1e-3)
    nao_pilar = []
    for b in barras:
        if b["papel"]:
            continue
        fam = b["perfil"].split()[0].upper()
        vert = abs(abs(_ang(b) % 180) - 90) < 5
        horiz = _ang(b) % 180 < 5 or _ang(b) % 180 > 175
        L = math.dist(b["a"], b["b"]) * float(v.get("fator") or 1.0)
        if b["perfil"].startswith("Barra redonda"):
            b["papel"] = "contraventamento"
        elif tipo == "planta":
            b["papel"] = "terça" if fam in ("UE", "U", "ZE", "Z45", "CR", "Z") and horiz or fam in ("UE", "ZE", "Z45", "CR") else \
                ("contraventamento" if fam == "L" else "viga")
        elif tipo == "lateral":
            b["papel"] = "pilar" if vert and L > 2000 else ("longarina" if horiz else "contraventamento")
        elif vert and L > 2000 and fam in ("W", "HP", "I", "CS", "CVS", "VS", "PS", "TQ", "TR", "TC") :
            b["papel"] = "pilar"
        else:
            nao_pilar.append(b)
    if trelica:
        for b in nao_pilar:
            vert = abs(abs(_ang(b) % 180) - 90) < 5
            if vert:
                b["papel"] = "montante"
            elif _no_contorno(b, barras, tol):
                b["papel"] = "banzo"
            else:
                b["papel"] = "diagonal"
    else:
        for b in nao_pilar:
            vert = abs(abs(_ang(b) % 180) - 90) < 5
            b["papel"] = "pilar" if vert else "viga"


def _ang(b: dict) -> float:
    return math.degrees(math.atan2(b["b"][1] - b["a"][1], b["b"][0] - b["a"][0]))


def _y_em(b: dict, x: float) -> Optional[float]:
    (x0, y0), (x1, y1) = b["a"], b["b"]
    if abs(x1 - x0) < 1e-9:
        return None
    t = (x - x0) / (x1 - x0)
    if t < -1e-6 or t > 1 + 1e-6:
        return None
    return y0 + (y1 - y0) * t


def _no_contorno(b: dict, barras: List[dict], tol: float) -> bool:
    """A barra está no contorno de cima ou de baixo da treliça (é banzo)?"""
    xm = (b["a"][0] + b["b"][0]) / 2
    ym = _y_em(b, xm)
    if ym is None:
        return False
    ys = [y for o in barras if o is not b and not (abs(abs(_ang(o) % 180) - 90) < 5)
          for y in [_y_em(o, xm)] if y is not None]
    if not ys:
        return True
    return ym >= max(ys) - tol or ym <= min(ys) + tol


# ------------------------------------------------------------------------------------
# Aplicar no desenho: camada das peças reconhecidas
# ------------------------------------------------------------------------------------

def aplicar(des: Desenho, resultado: dict, substituir: bool = True) -> List[Linha]:
    """Acrescenta ao desenho uma linha por barra reconhecida, na camada "PEÇAS
    RECONHECIDAS" (ou "PEÇAS A CONFERIR"), com a peça e a origem. Grava as vistas em
    `desenho.metadados["reconhecimento"]`. Devolve as linhas criadas."""
    if substituir:
        for k in [k for k, e in des.entidades.items() if (e.atributos or {}).get("reconhecido")]:
            des.remover(k)
    des.camadas.setdefault(CAMADA_OK, Camada2D(CAMADA_OK, "#e8590c", espessura=0.5))
    des.camadas.setdefault(CAMADA_CONFERIR, Camada2D(CAMADA_CONFERIR, "#d6336c", espessura=0.5))
    novas = []
    for b in resultado.get("barras") or []:
        peca = {"perfil": b["perfil"], "papel": b["papel"] or "barra", "aco": ""}
        if b.get("mult", 1) > 1:
            peca["mult"] = b["mult"]
        ln = Linha(camada=CAMADA_CONFERIR if b["conferir"] else CAMADA_OK, a=tuple(b["a"]), b=tuple(b["b"]),
                   atributos={"peca": peca, "reconhecido": {"vista": b["vista"], "fonte": b["fonte"],
                                                            "texto": b["texto"], "dupla": b["dupla"]}})
        des.add(ln)
        novas.append(ln)
    md = dict(des.metadados or {})
    from nucleo2d.reconhecer_geo import PERFIS_PADRAO
    sem_perfil = dict((resultado.get("resumo") or {}).get("sem_perfil") or {})
    md["reconhecimento"] = {"vistas": resultado.get("vistas") or [], "resumo": resultado.get("resumo") or {},
                            "papel_unidade": bool(resultado.get("papel_unidade")),
                            "sem_perfil": sem_perfil,
                            "perfis_padrao": {p: PERFIS_PADRAO.get(p, PERFIS_PADRAO["barra"]) for p in sem_perfil}}
    des.metadados = md
    return novas


# ------------------------------------------------------------------------------------
# Montagem sugerida: onde cada vista entra no espaço
# ------------------------------------------------------------------------------------

def _familias_de_eixos(eixos: List[dict]) -> List[List[dict]]:
    fams: List[List[dict]] = []
    for e in eixos:
        for f in fams:
            if _dif_ang(f[0]["ang"], e["ang"]) < 3:
                f.append(e)
                break
        else:
            fams.append([e])
    for f in fams:
        f.sort(key=lambda e: e["pos"])
    return [f for f in fams if len(f) >= 1]


def _eixos_unicos(f: List[dict], tol: float) -> List[dict]:
    out: List[dict] = []
    for e in f:
        if out and abs(e["pos"] - out[-1]["pos"]) < tol:
            continue
        out.append(e)
    return out


def _extensao(barras: List[dict], vid: int) -> Optional[Tuple[float, float, float, float]]:
    pts = [p for b in barras if b["vista"] == vid for p in (b["a"], b["b"])]
    if not pts:
        return None
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def sugerir_montagem(resultado: dict) -> dict:
    """Onde cada vista entra no espaço, pelo que se sabe de um galpão:

    * a **planta** fica deitada (X e Y da planta = X e Y do modelo), com a origem no
      primeiro eixo; as peças dela sobem até a cobertura (a altura sai do banzo superior
      da tesoura em cada ponto);
    * a **tesoura** (ou o pórtico) fica em pé em cada eixo da planta cuja família tem o
      comprimento do vão — uma cópia por eixo, apoio esquerdo no primeiro eixo da outra
      família; se a vista tem pilares, o pé deles fica em z = 0, senão a tesoura apoia na
      altura dos pilares de outra vista;
    * a **fachada lateral** fica em pé nos dois eixos das pontas, ao longo do galpão.

    Sem planta (ou sem eixos), cada vista entra sozinha, em pé, uma ao lado da outra, e a
    tela deixa acertar origem, direção e as posições das cópias.

    Devolve {montagens: [{vista, titulo, tipo, usar, u, v, base, origens, fator, cobertura,
    conjunto}], avisos: [...]} — u e v são os vetores do modelo em que caem o X e o Y do
    desenho, base é o ponto do desenho que vai para cada origem."""
    vistas = [v for v in resultado.get("vistas") or [] if v.get("barras")]
    barras = resultado.get("barras") or []
    avisos: List[str] = []
    mont: List[dict] = []
    plantas = [v for v in vistas if v["tipo"] == "planta"]
    planta = max(plantas, key=lambda v: (len(v["eixos"]), v["barras"]), default=None)
    em_pe = [v for v in vistas if v is not planta and v["tipo"] in ("trelica", "elevacao", "")]
    laterais = [v for v in vistas if v is not planta and v["tipo"] == "lateral"]

    def pilares(v):
        return [b for b in barras if b["vista"] == v["id"] and b["papel"] == "pilar"]

    # o pórtico com pilares e com menos deles (o interno) vai primeiro; o com mais (o oitão,
    # com o pilar do meio) só nos eixos das pontas; a tesoura sem pilar por último
    em_pe.sort(key=lambda v: (not pilares(v), len(pilares(v))))
    altura_pilar = 0.0
    for v in em_pe + laterais:
        ps = pilares(v)
        if ps:
            f = float(v["fator"] or 1.0)
            altura_pilar = max(abs(b["b"][1] - b["a"][1]) for b in ps) * f
            break

    def base_de(v):
        ext = _extensao(barras, v["id"])
        if ext is None:
            return [0.0, 0.0]
        x0, y0, x1, y1 = ext
        verticais = sorted(v["eixos"], key=lambda e: e["pos"])
        verticais = [e for e in verticais if abs(e["ang"] - 90) < 3]
        ps = pilares(v)
        if verticais:
            bx = verticais[0]["a"][0]
        elif ps:
            bx = min(min(b["a"][0], b["b"][0]) for b in ps)
        else:
            bx = x0
        return [bx, y0]

    if planta is not None and planta["eixos"]:
        fp = float(planta["fator"] or 1.0)
        fams = _familias_de_eixos(planta["eixos"])
        tol = 0.02 * max(planta["caixa"][1][0] - planta["caixa"][0][0], planta["caixa"][1][1] - planta["caixa"][0][1])
        fams = [_eixos_unicos(f, tol) for f in fams]
        principal = em_pe[0] if em_pe else None
        vao = None
        if principal is not None:
            ext = _extensao(barras, principal["id"])
            if ext:
                vao = (ext[2] - ext[0]) * float(principal["fator"] or 1.0)
        # família das tesouras: a outra família cobre o vão
        melhor = None
        if len(fams) >= 2:
            for i, f in enumerate(fams):
                outra = max((g for j, g in enumerate(fams) if j != i), key=len)
                ext_outra = (outra[-1]["pos"] - outra[0]["pos"]) * fp
                nota = abs(ext_outra - vao) / max(vao, 1.0) if vao else -len(f)
                if melhor is None or nota < melhor[0]:
                    melhor = (nota, f, outra)
        if melhor is not None:
            _, fam_t, fam_o = melhor
            # ponto base da planta: cruzamento do primeiro eixo de cada família
            e1, e2 = fam_t[0], fam_o[0]
            base_planta = _cruzamento(e1, e2) or [planta["caixa"][0][0], planta["caixa"][0][1]]
            # direção da tesoura na planta: ao longo do eixo da família das tesouras,
            # do primeiro para o último eixo da outra família
            d = fam_t[0]["dir"]
            o_ini = _cruzamento(fam_t[0], fam_o[0])
            o_fim = _cruzamento(fam_t[0], fam_o[-1])
            if o_ini and o_fim:
                dx, dy = o_fim[0] - o_ini[0], o_fim[1] - o_ini[1]
                n = math.hypot(dx, dy) or 1.0
                d = [dx / n, dy / n]
            origens_t = []
            for e in fam_t:
                c = _cruzamento(e, fam_o[0])
                if c is None:
                    continue
                origens_t.append([round((c[0] - base_planta[0]) * fp, 1), round((c[1] - base_planta[1]) * fp, 1), 0.0])
            mont.append({"vista": planta["id"], "titulo": planta["titulo"] or "Planta", "tipo": "planta", "usar": True,
                         "u": [1.0, 0.0, 0.0], "v": [0.0, 1.0, 0.0], "base": [round(x, 3) for x in base_planta],
                         "origens": [[0.0, 0.0, round(altura_pilar, 1)]], "fator": fp,
                         "cobertura": bool(em_pe), "conjunto": "", "cortar_nos_eixos": True,
                         "eixos_corte": [{"a": e["a"], "b": e["b"]} for e in fam_t]})
            n_pil_ref = len(pilares(em_pe[0])) if em_pe else 0

            def medidas(v):
                fv = float(v["fator"] or 1.0)
                ext = _extensao(barras, v["id"])
                return ((ext[2] - ext[0]) * fv if ext else 0.0), ((ext[3] - ext[1]) * fv if ext else 0.0)

            larg_ref, alt_ref = medidas(em_pe[0]) if em_pe else (0.0, 0.0)
            # o oitão: mesmo vão e altura do pórtico interno, com mais pilares (os de fechamento)
            eh_oitao = {}
            for v in em_pe[1:]:
                larg, alt = medidas(v)
                mesmo_vao = vao is None or abs(larg - (vao or larg)) <= 0.2 * max(larg, 1.0)
                mesma_altura = abs(alt - alt_ref) <= 0.25 * max(alt_ref, 1.0)
                eh_oitao[v["id"]] = bool(mesmo_vao and mesma_altura and pilares(v) and len(pilares(v)) > n_pil_ref
                                         and len(origens_t) >= 2)
            oitoes_v = [v for v in em_pe[1:] if eh_oitao.get(v["id"])]
            # dois desenhos de oitão: um em cada ponta (frontal e fundos); um só: nas duas.
            # Com oitão, o pórtico interno fica nos eixos de dentro.
            origens_oitao = {}
            if len(oitoes_v) >= 2:
                origens_oitao = {oitoes_v[0]["id"]: [origens_t[0]], oitoes_v[1]["id"]: [origens_t[-1]]}
            elif oitoes_v:
                origens_oitao = {oitoes_v[0]["id"]: [origens_t[0], origens_t[-1]]}
            usados_t = False
            oitoes = 0
            for v in em_pe:
                fv = float(v["fator"] or 1.0)
                tem_pilar = bool(pilares(v))
                z0 = 0.0 if tem_pilar else altura_pilar
                origens = origens_t
                if not usados_t:
                    usar = True
                    if origens_oitao and len(origens_t) > 2:
                        origens = origens_t[1:-1]
                elif v["id"] in origens_oitao:
                    usar = True
                    origens = origens_oitao[v["id"]]
                    oitoes += 1
                else:
                    usar = False
                # longarina do oitão partida nos pilares da própria vista: uma por vão
                cortes_v = [{"a": list(b_["a"]), "b": list(b_["b"])} for b_ in pilares(v)]
                mont.append({"vista": v["id"], "titulo": v["titulo"] or "Vista %d" % v["id"], "tipo": v["tipo"] or "elevacao",
                             "usar": usar, "u": [round(d[0], 6), round(d[1], 6), 0.0], "v": [0.0, 0.0, 1.0],
                             "base": base_de(v), "origens": [[o[0], o[1], round(z0, 1)] for o in origens], "fator": fv,
                             "cobertura": False, "conjunto": "T" if v["tipo"] == "trelica" else "PT",
                             "cortar_nos_eixos": bool(cortes_v), "eixos_corte": cortes_v})
                usados_t = True
            if len(em_pe) > 1:
                avisos.append("há %d vistas em pé: a primeira foi posta em todos os eixos das tesouras%s; as outras "
                              "ficaram desmarcadas — confira." % (len(em_pe), (", %d com mais pilares (oitão) só nos "
                                                                            "eixos das pontas" % oitoes) if oitoes else ""))
            for v in laterais:
                fv = float(v["fator"] or 1.0)
                dl = fam_o[0]["dir"]
                pontas = []
                for e in (fam_o[0], fam_o[-1]):
                    c = _cruzamento(fam_t[0], e)
                    if c is not None:
                        pontas.append([round((c[0] - base_planta[0]) * fp, 1), round((c[1] - base_planta[1]) * fp, 1), 0.0])
                # ao longo do galpão: do primeiro ao último eixo das tesouras
                c1, c2 = _cruzamento(fam_t[0], fam_o[0]), _cruzamento(fam_t[-1], fam_o[0])
                if c1 and c2:
                    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
                    n = math.hypot(dx, dy) or 1.0
                    dl = [dx / n, dy / n]
                # longarina partida nos eixos (ou nos pilares) da própria fachada: uma por vão
                cortes = [{"a": e["a"], "b": e["b"]} for e in v["eixos"] if abs(e["ang"] - 90) < 3]
                if not cortes:
                    cortes = [{"a": list(b["a"]), "b": list(b["b"])} for b in pilares(v)]
                mont.append({"vista": v["id"], "titulo": v["titulo"] or "Fachada lateral", "tipo": "lateral", "usar": True,
                             "u": [round(dl[0], 6), round(dl[1], 6), 0.0], "v": [0.0, 0.0, 1.0], "base": base_de(v),
                             "origens": pontas, "fator": fv, "cobertura": False, "conjunto": "FL",
                             "cortar_nos_eixos": True, "eixos_corte": cortes})
            return {"montagens": mont, "avisos": avisos}
        avisos.append("a planta tem eixos numa direção só: as vistas em pé entram sem posição — acerte as origens.")
    elif planta is not None:
        avisos.append("a planta não tem eixos com balão legíveis: a posição das tesouras não sai sozinha — acerte as "
                      "origens (a planta entra deitada, as outras vistas em pé).")
    # sem planta com eixos: cada vista sozinha
    x_livre = 0.0
    for v in vistas:
        f = float(v["fator"] or 1.0)
        ext = _extensao(barras, v["id"])
        larg = (ext[2] - ext[0]) * f if ext else 0.0
        if v["tipo"] == "planta":
            mont.append({"vista": v["id"], "titulo": v["titulo"] or "Planta", "tipo": "planta", "usar": True,
                         "u": [1.0, 0.0, 0.0], "v": [0.0, 1.0, 0.0], "base": [ext[0], ext[1]] if ext else [0, 0],
                         "origens": [[0.0, 0.0, round(altura_pilar, 1)]], "fator": f, "cobertura": False, "conjunto": ""})
            continue
        mont.append({"vista": v["id"], "titulo": v["titulo"] or "Vista %d" % v["id"], "tipo": v["tipo"] or "elevacao",
                     "usar": v["tipo"] != "detalhe", "u": [1.0, 0.0, 0.0], "v": [0.0, 0.0, 1.0], "base": base_de(v),
                     "origens": [[round(x_livre, 1), 0.0, 0.0]], "fator": f, "cobertura": False,
                     "conjunto": "T" if v["tipo"] == "trelica" else "M"})
        x_livre += larg + 3000.0
    return {"montagens": mont, "avisos": avisos}


def _cruzamento(e1: dict, e2: dict) -> Optional[List[float]]:
    (ax, ay), (bx, by) = e1["a"], e1["b"]
    (cx, cy), (dx, dy) = e2["a"], e2["b"]
    r = (bx - ax, by - ay)
    s = (dx - cx, dy - cy)
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((cx - ax) * s[1] - (cy - ay) * s[0]) / den
    return [ax + r[0] * t, ay + r[1] * t]
