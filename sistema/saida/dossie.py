# -*- coding: utf-8 -*-
"""O dossiê da obra: a parte visual do resumo da obra (09/10, pedido do usuário: "o resumo da obra vai ser o
DOSSIÊ da obra" — o analista bate o olho e vê a obra, não lê uma tabela de eixos).

* **Estrutura por tipo** — cada conjunto (ou peça solta) pelo papel dele na obra, não pela categoria da prancha:
  pilares, pilaretes, tesouras (só a treliça da cobertura: com terças ou telhas na obra), vigas caixote (a treliça
  que não é cobertura: a "tesoura" do Vicente é viga de transição), vigas pela seção (tubo, I, U), terças (só as da
  cobertura; as do fechamento são longarinas), contraventamentos, travamentos e dispositivos. As linhas saem por
  comprimento — "Pilares 22 un 6,85 m" — sem separar perfil nem espessura.
* **Pavimentos** — a obra de vários pavimentos pelas camadas do modelo ("Metálica – Duplex"); o pavimento que se
  repete (o Tipo, 12 andares) pelas faixas de cota das peças dele.
* **Desenhos em SVG** — a implantação (planta com eixos, cotas e as tesouras marcadas), o corte esquemático com os
  níveis e a planta de cada pavimento, feitos direto das peças do 3D.

Tudo sai de `levantar(...)` num dicionário só de números e SVG (vai no `R["dossie"]` do resumo); as fotos do 3D
(um tipo em destaque, o resto apagado) são pedidas depois por `pedidos_de_fotos` e tiradas pelo editor 3D.
"""
import collections
import html
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo2d.detalhe.base import _marcas, marcas_de, _eixo_da_peca, obra_tem_cobertura

#: Os papéis na ordem do dossiê: (chave, título, cor no desenho).
PAPEIS = collections.OrderedDict([
    ("pilares", ("Pilares", "#364fc7")),
    ("pilaretes", ("Pilaretes", "#15aabf")),
    ("tesouras", ("Tesouras", "#d9480f")),
    # a treliça em pé (de fechamento, a TV da PRATI, 19/10): não é tesoura
    ("trelicas_v", ("Treliças verticais", "#0b7285")),
    ("caixote", ("Vigas caixote", "#c77700")),
    ("vigas_tubo", ("Vigas tubo", "#0f8a7e")),
    ("vigas_i", ("Vigas I", "#2f9e44")),
    ("vigas_u", ("Vigas U", "#5c940d")),
    ("vigas", ("Vigas", "#2b8a3e")),
    ("tercas", ("Terças", "#7048e8")),
    ("longarinas", ("Longarinas de fechamento", "#ae3ec9")),
    ("diagonais", ("Diagonais e escoras", "#e8590c")),
    ("contrav", ("Contraventamentos", "#e03131")),
    ("travamentos", ("Travamentos e agulhamentos", "#495057")),
    ("fechamento", ("Perfis de fechamento e acabamento", "#e67700")),
    ("dispositivos", ("Dispositivos", "#c2255c")),
    ("suportes", ("Suportes e peças curtas", "#adb5bd")),
    ("outros", ("Outras barras", "#6c757d")),
    # a parte do cliente (a cobertura retrátil industrializada, 19/10): só desenhada, fora das contas
    ("cliente", ("Fora do escopo (do cliente)", "#c3c9d1")),
])
#: Tipo de peça (nucleo2d.detalhe.nomes) → papel, para o que não se decide pela geometria.
_PAPEL_DO_TIPO = {
    "terca_cobertura": "tercas", "terca_marquise": "tercas", "terca_lateral": "longarinas", "terca_oitao": "longarinas",
    "agulhamento": "travamentos", "agulhamento_lateral": "travamentos", "agulhamento_diagonal": "travamentos",
    "gancho": "travamentos", "barra_roscada": "travamentos", "contraventamento": "contrav",
    "perfil_fechamento": "fechamento", "cantoneira_forro": "fechamento", "conjunto": "dispositivos",
}
#: Tipos que não entram como barra da estrutura (vão para a chaparia, a compra ou a funilaria).
_FORA = {"chapa", "castanha", "suporte_terca", "suporte_agulhamento", "suporte_contraventamento", "telha", "rufo", "calha",
         "chumbador"}
#: Abaixo disto (mm) a barra solta não é pilar nem viga: é suporte, chapinha dobrada, toco (as 724 fixações U75x40 de
#: 160 mm do Vicente caíam em pilaretes).
CURTA = 600.0
#: Camadas do modelo que dizem o que a peça é (o IFC importado, o lançamento): não são pavimentos.
_CAMADA_SEMANTICA = re.compile(
    r"^(vigas?|pilar(es|etes)?|telhas?|chapas?|tirantes?|ter[çc]as?|tesouras?|contrav\w*|parafusos?|chumbadores?|rufos?|"
    r"calhas?|cumeeiras?|refer\w*|barras?|agulhamentos?|longarinas?|perfis?|acess[óo]rios?|fixadores?|"
    r"diagonais|montantes?|banzos?|treli[çc]as?|elementos?|outros|geral|0|padr[ãa]o|default|metálica|metalica)$", re.I)
#: Cores dos pavimentos no corte esquemático (na ordem de cota).
#: As cores das linhas de cada tipo na foto dele e na tabela (Kaefer, 19/10: "uma diferenciação por cores de cada
#: elemento"): fortes, distintas entre si e do cinza do resto
CORES_LINHAS = ["#e03131", "#1c7ed6", "#2f9e44", "#f08c00", "#ae3ec9", "#0ca678", "#d6336c", "#5c7cfa", "#fab005",
                "#74b816", "#1098ad", "#862e9c"]
CORES_PAV = ["#1f6feb", "#2f9e44", "#d9480f", "#7048e8", "#c2255c", "#0f8a7e", "#c77700", "#495057", "#3f7cc4", "#ae3ec9"]


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""), quote=True)


def _n(x, casas=2) -> str:
    s = ("%." + str(casas) + "f") % float(x)
    inteiro, _, dec = s.partition(".")
    neg = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return ("-" if neg else "") + ".".join(grupos) + ("," + dec if dec else "")


def _m(mm: float) -> str:
    """mm → "6,85 m" (o 5 arredonda para cima: 2.195 → 2,20)."""
    return _n(math.floor(float(mm) / 10.0 + 0.5) / 100.0, 2) + " m"


def _por_marca(d: Optional[dict]) -> dict:
    fora = {}
    for k, v in (d or {}).items():
        for m in str(k).split(" / "):
            fora[m.strip()] = v
    return fora


def _ordem_natural(texto: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(texto))]


def _base(marca: str) -> str:
    """A variante de furação ("P3 (b)") é a mesma posição."""
    return re.sub(r" \([b-z]\)$", "", str(marca or ""))


def _secao(perfil: str) -> str:
    """A família da seção pelo nome do perfil: tubo, I ou U (o resto é "vigas")."""
    p = str(perfil or "").upper().replace(" ", "")
    if re.match(r"^(TQ|TR|TC|TB|TUBO|RHS|SHS|CHS|PIPE|Ø|TUB)", p) or re.match(r"^\d+(\.\d+)?X\d+(\.\d+)?X\d", p) and "TUBO" in p:
        return "vigas_tubo"
    if re.match(r"^(W|HP|I|VS|CVS|CS|VE|IPE|HEA|HEB|PS)\d", p):
        return "vigas_i"
    if re.match(r"^(U|UE|C)\d", p):
        return "vigas_u"
    return "vigas"


# ============================================================ pavimentos

def _faixas(intervalos: List[Tuple[float, float]], folga: float = 300.0) -> List[Tuple[float, float]]:
    """As faixas de cota que as peças ocupam: intervalos [z0, z1] que se tocam (com `folga`) viram uma faixa só —
    cada andar do Tipo é uma faixa; o duplex, com o pilar de 7 m, é uma faixa só."""
    faixas: List[List[float]] = []
    for a, b in sorted(intervalos):
        if faixas and a <= faixas[-1][1] + folga:
            faixas[-1][1] = max(faixas[-1][1], b)
        else:
            faixas.append([a, b])
    return [(a, b) for a, b in faixas]


def pavimentos_do_modelo(pecas) -> Tuple[bool, List[dict], Dict[str, str]]:
    """(vários pavimentos?, pavimentos, {id da peça: pavimento}). Os pavimentos vêm das camadas das peças de aço
    quando elas não são camadas de tipo de peça (Vigas, Telhas…) e são duas ou mais; o que se repete (Tipo ×12) pelas
    faixas de cota. Uma camada só, ou camadas de tipo, é obra de um pavimento."""
    por_camada: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        por_camada[str(getattr(e, "camada", "") or "")].append(e)
    nomes = [c for c in por_camada if c and not _CAMADA_SEMANTICA.match(_nome_pav(c))]
    cobertas = sum(len(por_camada[c]) for c in nomes)
    if len(nomes) < 2 or cobertas < 0.9 * max(1, len(pecas)):
        return False, [], {}
    pavs = []
    pav_de: Dict[str, str] = {}
    for c in nomes:
        es = por_camada[c]
        ints = []
        for e in es:
            zs = [v[2] for v in e.vertices] if e.vertices else []
            if zs:
                ints.append((min(zs), max(zs)))
        faixas = _faixas(ints)
        nome = _nome_pav(c)
        pavs.append({"nome": nome, "camada": c, "faixas": faixas, "repete": len(faixas),
                     "z0": min(a for a, _ in faixas) if faixas else 0.0, "z1": max(b for _, b in faixas) if faixas else 0.0,
                     "n_pecas": len(es), "ids": [e.id for e in es]})
        for e in es:
            pav_de[e.id] = nome
    pavs.sort(key=lambda p: (p["z0"], p["z1"]))
    for i, p in enumerate(pavs):
        p["cor"] = CORES_PAV[i % len(CORES_PAV)]
    return True, pavs, pav_de


def _nome_pav(camada: str) -> str:
    """ "Metálica – Duplex" → "Duplex" (o prefixo do material sai)."""
    c = str(camada or "").strip()
    m = re.match(r"^(met[áa]lica|a[çc]o|estrutura met[áa]lica)\s*[–\-:]\s*(.+)$", c, re.I)
    return m.group(2).strip() if m else c


# ============================================================ estrutura por tipo

def levantar(doc, lev: dict, lista: dict, nomes: dict, R: dict, eixos: Optional[dict] = None,
             movel: Optional[dict] = None) -> dict:
    """O dossiê: pavimentos, estrutura por tipo (papel × comprimento) e os desenhos em SVG. `movel`: os parâmetros da
    cobertura retrátil (o modelo já vem com ela aberta): a planta dela retraída vai ao lado e as fotos mostram as duas."""
    posicoes = list(lev["posicoes"])
    pecas = [e for e in lev["pecas"] if e.vertices]
    tipos = _por_marca(nomes.get("tipos"))
    tipos_conj = _por_marca(nomes.get("tipos_conjuntos"))
    marca_para_pos = {}
    for p in posicoes:
        for m in marcas_de(p):
            marca_para_pos[m] = p
    varios, pavs, pav_de = pavimentos_do_modelo(pecas)
    # obra com cobertura: telha ou terça de cobertura no modelo — só então a treliça é tesoura e a terça é terça
    tem_cobertura = nomes.get("cobertura") if nomes.get("cobertura") is not None else obra_tem_cobertura(posicoes, tipos)

    pecas_conj: Dict[str, list] = collections.defaultdict(list)
    pecas_soltas: Dict[str, list] = collections.defaultdict(list)
    for e in pecas:
        mk = _marcas(e)
        cj = str(mk.get("conjunto") or "")
        pos = _base(str(mk.get("posicao") or e.nome or ""))
        if cj and cj != pos:
            pecas_conj[cj].append(e)
        else:
            pecas_soltas[pos].append(e)

    eixo_cache: Dict[str, Optional[tuple]] = {}

    def eixo(e):
        if e.id not in eixo_cache:
            try:
                eixo_cache[e.id] = _eixo_da_peca(e)
            except Exception:                                   # noqa: BLE001
                eixo_cache[e.id] = None
        return eixo_cache[e.id]

    def direcao(e) -> str:
        ex = eixo(e)
        if not ex:
            return "?"
        a, b = ex
        L = math.dist(a, b) or 1.0
        dz = abs(b[2] - a[2])
        return "v" if dz >= 0.85 * L else ("h" if dz <= 0.2 * L else "i")

    # ---- as unidades: cada conjunto pela barra principal (a mais comprida), cada posição solta pela peça
    unidades: List[dict] = []
    for c in lista.get("conjuntos") or []:
        marca = c.get("marca")
        comp = {_base(m): q for m, q in (c.get("composicao") or {}).items()}
        barras = [(marca_para_pos.get(m), q) for m, q in comp.items()]
        barras = [(p, q) for p, q in barras if p is not None and p.classe not in ("chapa", "chapa_dobrada", "telha")
                  and tipos.get(p.marca) not in _FORA]
        es = pecas_conj.get(marca) or []
        if not barras or not es:
            continue
        principal, q_p = max(barras, key=lambda pq: float(pq[0].comprimento or 0.0))
        principais = [e for e in es if _base(str(_marcas(e).get("posicao") or "")) == principal.marca] or es[:1]
        tc = tipos_conj.get(marca) or ""
        trelica = tc == "tesoura" or c.get("categoria") == "TESOURAS"
        unidades.append({"marca": marca, "nome": c.get("nome") or marca, "conjunto": True, "tipo": tc, "trelica": trelica,
                         "principal": principal, "q_principal": max(1, int(q_p)), "pecas": es, "principais": principais,
                         "kg_un": float(c.get("peso_unitario") or 0.0), "instancias": int(c.get("instancias") or 0)})
    for marca, es in pecas_soltas.items():
        p = marca_para_pos.get(marca)
        if p is None or p.classe in ("chapa", "chapa_dobrada", "telha", "indefinida") or tipos.get(p.marca) in _FORA:
            continue
        if any(c not in set(marcas_de(p)) for c in (p.conjuntos or [])) and not es:
            continue
        unidades.append({"marca": marca, "nome": getattr(p, "nome", "") or marca, "conjunto": False, "tipo": tipos.get(marca) or "",
                         "trelica": False, "principal": p, "q_principal": 1, "pecas": es, "principais": es,
                         "kg_un": float(p.peso or 0.0), "instancias": len(es)})

    # ---- o papel de cada unidade
    vert_max: Dict[str, float] = collections.defaultdict(float)
    for u in unidades:
        e0 = u["principais"][0]
        u["dir"] = direcao(e0)
        u["comprimento"] = float(u["principal"].comprimento or 0.0)
        if u["dir"] == "v" and not u["trelica"] and _PAPEL_DO_TIPO.get(u["tipo"]) is None and u["comprimento"] >= CURTA:
            for e in u["principais"]:
                vert_max[pav_de.get(e.id, "")] = max(vert_max[pav_de.get(e.id, "")], u["comprimento"])
    for u in unidades:
        if u["trelica"] and u["dir"] == "v":           # o banzo em pé: a treliça de fechamento (TV), não tesoura
            u["papel"] = "trelicas_v"
        elif u["trelica"]:
            u["papel"] = "tesouras" if tem_cobertura else "caixote"
        elif _PAPEL_DO_TIPO.get(u["tipo"]):
            u["papel"] = _PAPEL_DO_TIPO[u["tipo"]]
            if u["papel"] == "tercas" and not tem_cobertura:
                u["papel"] = _secao(u["principal"].perfil)
        elif not u["conjunto"] and _PAPEL_DO_TIPO.get(tipos.get(u["marca"]) or ""):
            u["papel"] = _PAPEL_DO_TIPO[tipos.get(u["marca"])]
        elif u["comprimento"] < CURTA:
            u["papel"] = "suportes"
        elif u["dir"] == "v":
            ref = max((vert_max.get(pav_de.get(e.id, ""), 0.0) for e in u["principais"]), default=0.0)
            u["papel"] = "pilares" if u["comprimento"] >= 0.75 * ref else "pilaretes"
        elif u["dir"] == "h":
            u["papel"] = _secao(u["principal"].perfil)
        elif u["dir"] == "i":
            u["papel"] = "diagonais"
        else:
            u["papel"] = "outros"

    # ---- as linhas por papel e comprimento, com onde estão (pavimento) e os ids para o 3D
    nomes_pav = [p["nome"] for p in pavs]
    papeis: Dict[str, dict] = collections.OrderedDict()
    for u in unidades:
        chave = u["papel"]
        titulo, cor = PAPEIS.get(chave, PAPEIS["outros"])
        bloco = papeis.setdefault(chave, {"chave": chave, "titulo": titulo, "cor": cor, "linhas": {}, "ids": [],
                                          "qtd": 0, "m": 0.0, "kg": 0.0})
        onde: Dict[str, float] = collections.Counter()
        for e in u["principais"]:
            onde[pav_de.get(e.id, "")] += 1.0 / u["q_principal"]
        qtd = int(round(sum(onde.values())))
        if qtd <= 0:
            continue
        L = int(round(u["comprimento"]))
        perfil = str(u["principal"].perfil or "")
        # comprimentos a menos de 5 mm são o mesmo (a mesma peça com o arredondamento do IFC); perfis diferentes, linhas
        # diferentes (Kaefer, 19/10: os pilares W310×32,7, W460×52,0 e TC 180×6,3 de 7,67 m saíam numa linha só)
        # o conjunto montado (treliça, dispositivo) é uma peça própria: uma linha por marca (as treliças T1, T2, T6… de 10,15 m
        # da PRATI saíam numa linha só)
        dono = u["nome"] if u["conjunto"] else ""
        alvo = next((k for k in bloco["linhas"] if k[1] == perfil and k[2] == dono and abs(k[0] - L) <= 5), (L, perfil, dono))
        li = bloco["linhas"].setdefault(alvo, {"comprimento": alvo[0], "qtd": 0, "kg": 0.0, "marcas": [], "perfis": [],
                                               "onde": collections.Counter(), "ids": []})
        li["qtd"] += qtd
        li["kg"] += qtd * u["kg_un"]
        if u["nome"] not in li["marcas"]:
            li["marcas"].append(u["nome"])
        if perfil and perfil not in li["perfis"]:
            li["perfis"].append(perfil)
        for k, v in onde.items():
            li["onde"][k] += v
        li["ids"].extend(e.id for e in u["pecas"])
        bloco["ids"].extend(e.id for e in u["pecas"])
        bloco["qtd"] += qtd
        bloco["m"] += qtd * u["comprimento"] / 1000.0
        bloco["kg"] += qtd * u["kg_un"]
    estrutura = []
    for chave in PAPEIS:
        b = papeis.get(chave)
        if not b or not b["linhas"]:
            continue
        linhas = []
        for li in sorted(b["linhas"].values(), key=lambda x: (-x["comprimento"], x["perfis"])):
            li["marcas"].sort(key=_ordem_natural)
            li["onde"] = [(p, int(round(li["onde"][p]))) for p in nomes_pav if round(li["onde"].get(p, 0))] if varios else []
            linhas.append(li)
        b["linhas"] = linhas
        estrutura.append(b)
    # as tesouras da cobertura pelo tipo montado do resumo (as duas meias são uma tesoura; T1, T2… como nas pranchas)
    # e o eixo do projeto em que cada uma está
    tes = [t for t in (R or {}).get("tesouras") or [] if t.get("qtd")]
    b = next((x for x in estrutura if x["chave"] == "tesouras"), None)
    if b is not None and tes:
        eixo_de = _eixos_das_tesouras(R, eixos)
        linhas = []
        for t in tes:
            ids = [e.id for m in t.get("marcas") or [] for e in pecas_conj.get(m, [])]
            linhas.append({"comprimento": t["comprimento"], "qtd": t["qtd"], "kg": t["kg_total"], "marcas": [t["tipo"]],
                           "perfis": [x for x in (t.get("banzos"), t.get("trelicamento")) if x], "onde": [], "ids": ids,
                           "vao": t["vao"], "altura": t["altura"], "flecha": t["flecha"],
                           "eixos": eixo_de.get(t["tipo"]) or t.get("eixos", "")})
        b.update({"linhas": linhas, "qtd": sum(t["qtd"] for t in tes), "kg": sum(t["kg_total"] for t in tes),
                  "m": sum(t["qtd"] * t["comprimento"] for t in tes) / 1000.0})

    # a cor de cada linha (a mesma na foto do tipo e na tabela)
    for b in estrutura:
        for k, li in enumerate(b["linhas"]):
            li["cor"] = CORES_LINHAS[k % len(CORES_LINHAS)]

    # ---- os pavimentos: peças, kg e o que cada um tem por papel (por andar e no total)
    if varios:
        for p in pavs:
            p["papeis"] = []
            for b in estrutura:
                q = sum(dict(li["onde"]).get(p["nome"], 0) for li in b["linhas"])
                if q:
                    linhas = [{"comprimento": li["comprimento"], "qtd": dict(li["onde"]).get(p["nome"], 0), "marcas": li["marcas"]}
                              for li in b["linhas"] if dict(li["onde"]).get(p["nome"], 0)]
                    p["papeis"].append({"chave": b["chave"], "titulo": b["titulo"], "cor": b["cor"], "qtd": q, "linhas": linhas})
        kg_pav = _kg_por_pavimento(unidades, pav_de)
        for p in pavs:
            p["kg"] = kg_pav.get(p["nome"], 0.0)

    # ---- desenhos
    papel_da_peca = {}
    # a marca (a das pranchas) na barra principal de cada unidade, para escrever na planta do pavimento
    marca_da_peca = {}
    for u in unidades:
        if u["papel"] not in ("suportes", "travamentos", "fechamento"):
            for e in u["principais"]:
                marca_da_peca[e.id] = u["nome"]
    for u in unidades:
        for e in u["pecas"]:
            papel_da_peca[e.id] = u["papel"]
    geo = _geometria(pecas, papel_da_peca, eixo)
    # o que é do cliente (fora do escopo, fora das peças do levantamento) entra só no desenho, em cinza
    geo.update(_geometria_do_cliente(doc))
    for i, m in marca_da_peca.items():
        if i in geo:
            geo[i]["marca"] = m
    svgs = {}
    eixos_ok = eixos if (eixos and (eixos.get("numeros") or eixos.get("letras"))) else None
    if varios:
        # eixos automáticos numa obra de vários pavimentos não são os do projeto (são os das caixas): só os do usuário
        eixos_pav = eixos_ok if (eixos_ok and eixos_ok.get("origem") == "usuario") else None
        svgs["corte"] = corte_svg(geo, pavs, pav_de, _concreto(doc, pecas))
        for p in pavs:
            z0, z1 = p["faixas"][0] if p["faixas"] else (p["z0"], p["z1"])
            ids = {i for i in p["ids"] if _dentro(geo.get(i), z0, z1)}
            p["svg"] = planta_svg({i: geo[i] for i in ids if i in geo}, eixos_pav, R=R, concreto=_concreto(doc, pecas, z0, z1),
                                  largura=186.0, altura_max=70.0, marcas=True)
            p["ids_andar"] = sorted(ids)
            p["contexto"] = contexto_de_concreto(doc, pecas, z0, z1)
    else:
        # a cobertura retrátil (Kaefer, 19/10): aberta e retraída lado a lado
        if movel is not None:
            try:
                svgs["implantacao_retraida"] = planta_svg(_geo_retraida(doc, geo, movel), eixos_ok, R=R, largura=92.0,
                                                          altura_max=150.0)
            except Exception:                                   # noqa: BLE001 — sem ela, a aberta sozinha
                svgs.pop("implantacao_retraida", None)
        lado = "implantacao_retraida" in svgs
        svgs["implantacao"] = planta_svg(geo, eixos_ok, R=R, largura=92.0 if lado else 186.0, altura_max=150.0,
                                         rotulos_tesouras=True)
        # as elevações (19/10): a lateral olhando o lado comprido, a frontal o curto
        for chave, frontal in (("elevacao_lateral", False), ("elevacao_frontal", True)):
            try:
                svgs[chave] = elevacao_svg(geo, eixos_ok, frontal=frontal)
            except Exception:                                   # noqa: BLE001 — sem ela, o resumo segue
                svgs.pop(chave, None)
    legenda = [(b["titulo"], b["cor"]) for b in estrutura]
    if any(g["papel"] == "cliente" for g in geo.values()):
        legenda.append(PAPEIS["cliente"])
    return {"varios": varios, "pavimentos": pavs, "estrutura": estrutura, "svg": svgs, "legenda": legenda,
            "tem_cobertura": tem_cobertura, "eixos": eixos_ok, "tem_lona": tem_lona(doc), "lona_paredes": lona_das_paredes(doc),
            "cobertura_movel": movel is not None}


def _geometria_do_cliente(doc) -> Dict[str, dict]:
    """As barras fora do nosso escopo (a cobertura retrátil industrializada) para o desenho: o papel "cliente", em cinza."""
    from nucleo2d.detalhe.base import _proxy_da_barra, fora_do_escopo
    geo = {}
    for e in getattr(doc, "entidades", {}).values() if doc is not None else ():
        if not fora_do_escopo(e) or not hasattr(e, "inicio"):
            continue
        try:
            px = _proxy_da_barra(e)
            seg = _eixo_da_peca(px)
        except Exception:                                       # noqa: BLE001
            continue
        zs = [v[2] for v in px.vertices]
        geo[e.id] = {"papel": "cliente", "seg": seg, "z0": min(zs), "z1": max(zs), "verts": px.vertices}
    return geo


def _geo_retraida(doc, geo: Dict[str, dict], movel: dict) -> Dict[str, dict]:
    """A geometria da planta com a cobertura retrátil retraída: as peças geradas (tesouras, sanfona) têm o mesmo id nas
    duas situações (cobertura_movel._id_estavel); só a posição delas muda, o papel e a cor ficam os da aberta."""
    import copy
    from nucleo3d import cobertura_movel as CM
    from nucleo2d.detalhe.base import _proxy_da_barra
    d2 = copy.deepcopy(doc)
    CM.aplicar(d2, movel, "retraida")
    saida = {}
    for i, g in geo.items():
        e = d2.entidades.get(i)
        if e is None:
            continue
        if CM.gerada(e) and hasattr(e, "inicio"):
            px = _proxy_da_barra(e)
            zs = [v[2] for v in px.vertices]
            try:
                seg = _eixo_da_peca(px)
            except Exception:                                   # noqa: BLE001
                seg = None
            g = dict(g, seg=seg, z0=min(zs), z1=max(zs), verts=px.vertices)
        saida[i] = g
    return saida


def _eixos_das_tesouras(R: dict, eixos: Optional[dict]) -> Dict[str, str]:
    """{tipo da tesoura: "2, 3, 4"}: o eixo numerado do projeto mais perto de cada tesoura (a sequência A, B, C… do
    resumo antigo não era a dos eixos do projeto)."""
    nums = (eixos or {}).get("numeros") or []
    g = (eixos or {}).get("eixo_g")
    if not nums or not g:
        return {}
    por_tipo: Dict[str, list] = collections.defaultdict(list)
    for t in R.get("tesouras_lugar") or []:
        u = t["xy"][0] * g[0] + t["xy"][1] * g[1]
        perto = min(nums, key=lambda x: abs(x["pos"] - u))
        if abs(perto["pos"] - u) <= 1500.0 and perto["nome"] not in por_tipo[t["tipo"]]:
            por_tipo[t["tipo"]].append(perto["nome"])
    return {k: ", ".join(sorted(v, key=_ordem_natural)) for k, v in por_tipo.items()}


def _kg_por_pavimento(unidades, pav_de) -> Dict[str, float]:
    kg: Dict[str, float] = collections.Counter()
    for u in unidades:
        for e in u["principais"]:
            kg[pav_de.get(e.id, "")] += u["kg_un"] / u["q_principal"]
    return kg


def _dentro(g, z0, z1) -> bool:
    return bool(g) and g["z0"] >= z0 - 300.0 and g["z1"] <= z1 + 300.0


# ============================================================ geometria para os desenhos

def _geometria(pecas, papel_da_peca: Dict[str, str], eixo) -> Dict[str, dict]:
    """{id: {papel, seg (a, b) ou None, pts (x, y) da sombra em planta, z0, z1, xyz}} das peças com papel."""
    geo = {}
    for e in pecas:
        papel = papel_da_peca.get(e.id)
        if not papel:
            continue
        zs = [v[2] for v in e.vertices]
        ex = eixo(e)
        geo[e.id] = {"papel": papel, "seg": ex, "z0": min(zs), "z1": max(zs), "verts": e.vertices}
    return geo


def _concreto(doc, pecas, z0: Optional[float] = None, z1: Optional[float] = None) -> List[dict]:
    """Os pilares de concreto do modelo (o TQS junto com o aço, no Vicente) para dar o lugar da estrutura no desenho:
    a sombra de cada um; com z0/z1, só os que passam por essa faixa."""
    if doc is None:
        return []
    chave = (id(doc), None if z0 is None else round(z0), None if z1 is None else round(z1))
    if chave in _CACHE_CONCRETO:
        return _CACHE_CONCRETO[chave]
    aco = {e.id for e in pecas}
    saida = []
    try:
        ents = list(doc.entidades.values()) if isinstance(getattr(doc, "entidades", None), dict) else list(getattr(doc, "entidades", []) or [])
    except Exception:                                           # noqa: BLE001
        ents = []
    for e in ents:
        if getattr(e, "id", None) in aco:
            continue
        at = getattr(e, "atributos", None) or {}
        if str(at.get("tipo_ifc") or "") != "IfcColumn":
            continue
        vs = getattr(e, "vertices", None)
        if not vs:
            continue
        zs = [v[2] for v in vs]
        if z0 is not None and (max(zs) < z0 or min(zs) > z1):
            continue
        saida.append({"verts": vs, "z0": min(zs), "z1": max(zs)})
    _CACHE_CONCRETO[chave] = saida
    return saida


_CACHE_CONCRETO: Dict[tuple, list] = {}


def contexto_de_concreto(doc, pecas, z0: float, z1: float) -> List[str]:
    """Os ids do concreto que aparece em cinza na foto de um pavimento: os pilares que passam pela faixa e a laje e as
    vigas do piso dele (o topo perto da base da faixa) — a laje de cima tamparia a vista aérea."""
    if doc is None:
        return []
    aco = {e.id for e in pecas}
    try:
        ents = list(doc.entidades.values()) if isinstance(getattr(doc, "entidades", None), dict) else list(getattr(doc, "entidades", []) or [])
    except Exception:                                           # noqa: BLE001
        return []
    ids = []
    for e in ents:
        if getattr(e, "id", None) in aco:
            continue
        t = str((getattr(e, "atributos", None) or {}).get("tipo_ifc") or "")
        vs = getattr(e, "vertices", None)
        if t not in ("IfcColumn", "IfcSlab", "IfcBeam") or not vs:
            continue
        zs = [v[2] for v in vs]
        if t == "IfcColumn":
            if max(zs) >= z0 and min(zs) <= z1 - 500.0:
                ids.append(e.id)
        elif z0 - 900.0 <= max(zs) <= z0 + 400.0:
            ids.append(e.id)
    return ids


def _casco(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Casco convexo (cadeia monótona)."""
    pts = sorted(set((round(x, 1), round(y, 1)) for x, y in pts))
    if len(pts) <= 2:
        return pts

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo, cima = [], []
    for p in pts:
        while len(baixo) >= 2 and cruz(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pts):
        while len(cima) >= 2 and cruz(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


class _Folha:
    """Um SVG em milímetros de papel: o modelo (mm) entra pela escala; texto e traço já em mm de papel."""

    def __init__(self, x0, y0, x1, y1, largura, altura_max, margem=(14.0, 10.0, 22.0, 24.0)):
        # margem: (direita, baixo, cima, esquerda) em mm de papel — os eixos e as cotas moram nela
        md, mb, mc, me = margem
        w = max(x1 - x0, 1.0)
        h = max(y1 - y0, 1.0)
        self.k = min((largura - me - md) / w, (altura_max - mc - mb) / h)
        self.x0, self.y1 = x0, y1
        self.me, self.mc = me, mc
        self.W = largura
        self.H = h * self.k + mc + mb
        self.partes: List[str] = []

    def p(self, x, y) -> Tuple[float, float]:
        return (self.me + (x - self.x0) * self.k, self.mc + (self.y1 - y) * self.k)

    def add(self, s: str):
        self.partes.append(s)

    def linha(self, a, b, cor, larg, extra=""):
        (x1, y1), (x2, y2) = self.p(*a), self.p(*b)
        self.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="%.2f"%s/>' % (x1, y1, x2, y2, cor, larg, extra))

    def poligono(self, pts, cor, fundo, larg=0.15, extra=""):
        s = " ".join("%.2f,%.2f" % self.p(x, y) for x, y in pts)
        self.add('<polygon points="%s" stroke="%s" fill="%s" stroke-width="%.2f"%s/>' % (s, cor, fundo, larg, extra))

    def texto(self, x, y, t, tam=2.2, cor="#1d232b", ancora="middle", peso=600, papel=False, extra=""):
        if not papel:
            x, y = self.p(x, y)
        self.add('<text x="%.2f" y="%.2f" font-size="%.2f" fill="%s" text-anchor="%s" font-weight="%d"%s>%s</text>'
                 % (x, y, tam, cor, ancora, peso, extra, _esc(t)))

    def svg(self, classe="desenho") -> str:
        return ('<svg class="%s" xmlns="http://www.w3.org/2000/svg" width="%.1fmm" height="%.1fmm" viewBox="0 0 %.2f %.2f" '
                'font-family="Segoe UI, Arial, sans-serif">%s</svg>' % (classe, self.W, self.H, self.W, self.H, "".join(self.partes)))


_LARG_PAPEL = {"pilares": 0.0, "pilaretes": 0.0, "tesouras": 0.7, "trelicas_v": 0.6, "caixote": 0.55, "vigas_tubo": 0.6, "vigas_i": 0.6,
               "vigas_u": 0.5, "vigas": 0.5, "tercas": 0.3, "longarinas": 0.3, "diagonais": 0.3, "contrav": 0.25,
               "travamentos": 0.18, "fechamento": 0.18, "dispositivos": 0.35, "outros": 0.25}
#: A ordem de pintura: o fino por baixo, o principal por cima.
_ORDEM_PINTURA = ["travamentos", "fechamento", "contrav", "diagonais", "longarinas", "tercas", "outros", "dispositivos", "vigas",
                  "vigas_u", "vigas_i", "vigas_tubo", "caixote", "tesouras", "trelicas_v", "pilaretes", "pilares"]


def _cota(f: _Folha, a: float, b: float, fixo: float, horizontal: bool, texto: str, cor="#2b8a3e"):
    """Cota em papel: de `a` a `b` (mm de papel) na linha `fixo`; o traço oblíquo nas pontas."""
    if horizontal:
        f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.15"/>' % (a, fixo, b, fixo, cor))
        for x in (a, b):
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.25"/>' % (x - 0.8, fixo + 0.8, x + 0.8, fixo - 0.8, cor))
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.1"/>' % (x, fixo - 1.2, x, fixo + 1.2, cor))
        if b - a >= 4.0:
            f.texto((a + b) / 2, fixo - 0.8, texto, tam=1.9, cor="#1d232b", papel=True, peso=500)
    else:
        f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.15"/>' % (fixo, a, fixo, b, cor))
        for y in (a, b):
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.25"/>' % (fixo - 0.8, y + 0.8, fixo + 0.8, y - 0.8, cor))
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.1"/>' % (fixo - 1.2, y, fixo + 1.2, y, cor))
        if b - a >= 4.0:
            cx, cy = fixo - 0.8, (a + b) / 2
            f.add('<text x="%.2f" y="%.2f" font-size="1.9" fill="#1d232b" text-anchor="middle" font-weight="500" '
                  'transform="rotate(-90 %.2f %.2f)">%s</text>' % (cx, cy, cx, cy, _esc(texto)))


def planta_svg(geo: Dict[str, dict], eixos: Optional[dict], R: Optional[dict] = None, concreto: Sequence[dict] = (),
               largura=186.0, altura_max=150.0, rotulos_tesouras=False, marcas=False) -> str:
    """A planta (de implantação, ou de um pavimento): as barras pela cor do papel, os pilares como quadrados, os
    pilares de concreto em cinza claro, os eixos com as bolhas e as cotas entre eixos e totais."""
    if not geo:
        return ""
    if eixos and eixos.get("eixo_g"):
        g = tuple(eixos["eixo_g"])[:2]
        q = tuple(eixos.get("perp_g") or (-g[1], g[0]))[:2]
    else:
        # sem eixos, a planta deitada: o lado mais comprido na horizontal (a faixa de aço da fachada ficava em pé, miúda)
        xs = [v[0] for d in geo.values() for v in d["verts"][::8]]
        ys = [v[1] for d in geo.values() for v in d["verts"][::8]]
        g, q = ((1.0, 0.0), (0.0, 1.0)) if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else ((0.0, 1.0), (-1.0, 0.0))

    def uv(v):
        return (v[0] * g[0] + v[1] * g[1], v[0] * q[0] + v[1] * q[1])
    us, vs = [], []
    for d in geo.values():
        for v in d["verts"][:: max(1, len(d["verts"]) // 16)]:
            a, b = uv(v)
            us.append(a)
            vs.append(b)
    nums = sorted((eixos or {}).get("numeros") or [], key=lambda x: x["pos"])
    lets = sorted((eixos or {}).get("letras") or [], key=lambda x: x["pos"])
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    # o concreto só em volta do aço (o prédio inteiro deixava a estrutura do pavimento num canto, miúda)
    perto = 4000.0
    cascos = []
    for c in concreto:
        pts = _casco([uv(v) for v in c["verts"]])
        if len(pts) >= 3 and all(u0 - perto <= a <= u1 + perto and v0 - perto <= b <= v1 + perto for a, b in pts):
            cascos.append(pts)
    for pts in cascos:
        u0, u1 = min(u0, min(a for a, _ in pts)), max(u1, max(a for a, _ in pts))
        v0, v1 = min(v0, min(b for _, b in pts)), max(v1, max(b for _, b in pts))
    for x in nums:
        u0, u1 = min(u0, x["pos"]), max(u1, x["pos"])
    for x in lets:
        v0, v1 = min(v0, x["pos"]), max(v1, x["pos"])
    f = _Folha(u0, v0, u1, v1, largura, altura_max, margem=(8.0, 6.0, 24.0 if nums else 12.0, 24.0 if lets else 12.0))
    # concreto de fundo
    for pts in cascos:
        f.poligono(pts, "#c6ccd4", "#e9ecef", 0.12)
    # eixos (traço-ponto, por baixo da estrutura)
    for x in nums:
        f.linha((x["pos"], v0 - 600), (x["pos"], v1 + 600), "#c0392b", 0.12, ' stroke-dasharray="3 0.8 0.6 0.8"')
    for x in lets:
        f.linha((u0 - 600, x["pos"]), (u1 + 600, x["pos"]), "#c0392b", 0.12, ' stroke-dasharray="3 0.8 0.6 0.8"')
    # a estrutura, do fino ao grosso
    ordem = {k: i for i, k in enumerate(_ORDEM_PINTURA)}
    pontos = []
    for d in sorted(geo.values(), key=lambda d: ordem.get(d["papel"], 0)):
        cor = PAPEIS.get(d["papel"], PAPEIS["outros"])[1]
        seg = d["seg"]
        if seg:
            a, b = uv(seg[0]), uv(seg[1])
            if math.dist(a, b) * f.k >= 0.6:
                f.linha(a, b, cor, _LARG_PAPEL.get(d["papel"], 0.25), ' stroke-linecap="round"')
                continue
        pts = [uv(v) for v in d["verts"]]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if d["papel"] in ("pilares", "pilaretes"):
            pontos.append((cx, cy, cor, d["papel"]))
    vistos = set()
    for cx, cy, cor, papel in pontos:
        x, y = f.p(cx, cy)
        chave = (round(x, 1), round(y, 1))
        if chave in vistos:
            continue
        vistos.add(chave)
        t = 1.6 if papel == "pilares" else 1.1
        f.add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="#fff" stroke-width="0.15"/>' % (x - t / 2, y - t / 2, t, t, cor))
    # bolhas e cotas
    xa, ya = f.p(u0, v1)
    xb, yb = f.p(u1, v0)
    if nums:
        for x in nums:
            px, _ = f.p(x["pos"], v1)
            f.add('<circle cx="%.2f" cy="%.2f" r="2.6" fill="#fff" stroke="#c0392b" stroke-width="0.25"/>' % (px, 4.0))
            f.texto(px, 4.0 + 0.85, x["nome"], tam=2.4, cor="#c0392b", papel=True, peso=700)
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#c0392b" stroke-width="0.12"/>' % (px, 6.6, px, ya - 1.0))
        ps = [f.p(x["pos"], v1)[0] for x in nums]
        for a, b, xa_, xb_ in zip(ps, ps[1:], nums, nums[1:]):
            _cota(f, a, b, 12.0, True, _n((xb_["pos"] - xa_["pos"]) / 1000.0, 2))
        if len(ps) > 2:
            _cota(f, ps[0], ps[-1], 17.5, True, _n((nums[-1]["pos"] - nums[0]["pos"]) / 1000.0, 2))
    else:
        _cota(f, xa, xb, f.mc - 4.0, True, _n((u1 - u0) / 1000.0, 2))
    if lets:
        for x in lets:
            _, py = f.p(u0, x["pos"])
            f.add('<circle cx="%.2f" cy="%.2f" r="2.6" fill="#fff" stroke="#c0392b" stroke-width="0.25"/>' % (4.0, py))
            f.texto(4.0, py + 0.85, x["nome"], tam=2.4, cor="#c0392b", papel=True, peso=700)
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#c0392b" stroke-width="0.12"/>' % (6.6, py, xa - 1.0, py))
        ps = [f.p(u0, x["pos"])[1] for x in lets]
        pares = sorted(zip(ps, lets), key=lambda t: t[0])
        for (a, la), (b, lb) in zip(pares, pares[1:]):
            _cota(f, a, b, 12.0, False, _n(abs(lb["pos"] - la["pos"]) / 1000.0, 2))
        if len(ps) > 2:
            _cota(f, pares[0][0], pares[-1][0], 17.5, False, _n(abs(lets[-1]["pos"] - lets[0]["pos"]) / 1000.0, 2))
    else:
        _cota(f, ya, yb, f.me - 4.0, False, _n((v1 - v0) / 1000.0, 2))
    # a marca das pranchas em cada peça principal (PL2, VG1, T7…), na cor do tipo; a que cairia em cima de outra fica de
    # fora (as duas cordas da mesma caixa, a peça repetida no mesmo ponto)
    if marcas:
        postos: List[Tuple[float, float, float]] = []
        for d in sorted(geo.values(), key=lambda d: -ordem.get(d["papel"], 0)):
            m = d.get("marca")
            if not m:
                continue
            ancora = "start"
            if d["seg"] and math.dist(uv(d["seg"][0]), uv(d["seg"][1])) * f.k >= 0.6:
                (x1, y1), (x2, y2) = f.p(*uv(d["seg"][0])), f.p(*uv(d["seg"][1]))
                x, y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                # a linha deitada no papel com o nome embaixo; a em pé, à esquerda dela
                if abs(x2 - x1) >= abs(y2 - y1):
                    x, y, ancora = x, y + 2.6, "middle"
                else:
                    x, y, ancora = x - 1.3, y + 0.7, "end"
            else:
                pts = [uv(v) for v in d["verts"]]
                x, y = f.p(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                x, y = x + 1.4, y - 1.1                    # o pilar com o nome no canto de cima do quadrado
            larg = 1.1 * len(m)
            x0 = x - (larg / 2 if ancora == "middle" else (larg if ancora == "end" else 0.0))
            if any(x0 < qx1 and x0 + larg > qx0 and abs(y - qy) < 2.2 for qx0, qx1, qy in postos):
                continue
            postos.append((x0, x0 + larg, y))
            cor = PAPEIS.get(d["papel"], PAPEIS["outros"])[1]
            f.add('<text x="%.2f" y="%.2f" font-size="1.9" fill="%s" text-anchor="%s" font-weight="700" stroke="#fff" '
                  'stroke-width="0.5" paint-order="stroke">%s</text>' % (x, y, cor, ancora, _esc(m)))
    # o tipo de cada tesoura no lugar dela (T1, T2…), na ponta de cima
    if rotulos_tesouras and R:
        for t in R.get("tesouras_lugar") or []:
            a, b = uv(t["xy"]), None
            px, py = f.p(*a)
            f.add('<rect x="%.2f" y="%.2f" width="6.4" height="3.2" rx="0.6" fill="#fff" stroke="#d9480f" stroke-width="0.2"/>' % (px - 3.2, py - 1.6))
            f.texto(px, py + 0.75, t["tipo"], tam=2.0, cor="#d9480f", papel=True, peso=700)
    return f.svg()


def corte_svg(geo: Dict[str, dict], pavs: List[dict], pav_de: Dict[str, str], concreto: Sequence[dict] = (),
              largura=186.0, altura_max=210.0) -> str:
    """O corte esquemático da obra de vários pavimentos: a estrutura de aço projetada num plano vertical (na direção
    mais comprida do prédio), pintada pelo pavimento, os pilares de concreto em cinza e, à direita, cada pavimento com
    a faixa de cotas e quantas vezes se repete."""
    if not geo:
        return ""
    xs = [v[0] for d in geo.values() for v in d["verts"][::8]]
    ys = [v[1] for d in geo.values() for v in d["verts"][::8]]
    h = (1.0, 0.0) if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else (0.0, 1.0)

    def hz(v):
        return (v[0] * h[0] + v[1] * h[1], v[2])
    hs = [hz(v)[0] for d in geo.values() for v in d["verts"][::8]]
    zs = [d["z0"] for d in geo.values()] + [d["z1"] for d in geo.values()]
    for c in concreto:
        for v in c["verts"][::4]:
            hs.append(hz(v)[0])
        zs += [c["z0"], c["z1"]]
    x0, x1, z0, z1 = min(hs), max(hs), min(zs), max(zs)
    f = _Folha(x0, z0, x1, z1, largura, altura_max, margem=(62.0, 6.0, 6.0, 16.0))
    for c in concreto:
        pts = _casco([hz(v) for v in c["verts"]])
        if len(pts) >= 3:
            f.poligono(pts, "#ced4da", "#e9ecef", 0.1)
    cor_pav = {p["nome"]: p["cor"] for p in pavs}
    for i, d in sorted(geo.items(), key=lambda kv: _ORDEM_PINTURA.index(kv[1]["papel"]) if kv[1]["papel"] in _ORDEM_PINTURA else 0):
        cor = cor_pav.get(pav_de.get(i, ""), "#495057")
        if d["seg"]:
            a, b = hz(d["seg"][0]), hz(d["seg"][1])
            if math.dist(a, b) * f.k >= 0.3:
                f.linha(a, b, cor, 0.35 if d["papel"] in ("pilares", "pilaretes", "caixote", "tesouras") else 0.22, ' stroke-linecap="round"')
                continue
        a = hz(d["verts"][0])
        x, y = f.p(*a)
        f.add('<circle cx="%.2f" cy="%.2f" r="0.25" fill="%s"/>' % (x, y, cor))
    # níveis à esquerda: cada faixa de cada pavimento
    xr = f.W - 60.0
    for p in pavs:
        for a, b in p["faixas"]:
            _, ya = f.p(x0, a)
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.1" stroke-dasharray="0.8 0.6"/>'
                  % (f.me - 2.0, ya, xr - 2.0, ya, p["cor"]))
    # à direita: o pavimento, a faixa de cotas e a repetição — rótulos afastados para não se encostarem
    # as faixas seguidas do mesmo pavimento (sem outro no meio) viram um trecho: o Tipo entre os duplex são 2 trechos
    todas = sorted((a, b, p["nome"]) for p in pavs for a, b in p["faixas"])
    trechos: Dict[str, list] = collections.defaultdict(list)
    ultimo = None
    for a, b, nome in todas:
        if ultimo == nome and trechos[nome]:
            trechos[nome][-1][1] = max(trechos[nome][-1][1], b)
        else:
            trechos[nome].append([a, b])
        ultimo = nome
    rotulos = []
    for p in pavs:
        ys = []
        for a, b in trechos.get(p["nome"]) or [[p["z0"], p["z1"]]]:
            ya, yb = f.p(x0, b)[1], f.p(x0, a)[1]
            ys.append((ya, yb))
        rotulos.append([sum((ya + yb) / 2.0 for ya, yb in ys) / len(ys), ys, p])
    rotulos.sort(key=lambda r: r[0])
    for i in range(1, len(rotulos)):
        if rotulos[i][0] - rotulos[i - 1][0] < 8.5:
            rotulos[i][0] = rotulos[i - 1][0] + 8.5
    for ym, ys, p in rotulos:
        for ya, yb in ys:
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.7"/>' % (xr, ya, xr, yb, p["cor"]))
            f.add('<polyline points="%.2f,%.2f %.2f,%.2f %.2f,%.2f" fill="none" stroke="%s" stroke-width="0.15"/>'
                  % (xr + 0.4, (ya + yb) / 2, xr + 3.5, ym, xr + 4.5, ym, p["cor"]))
        f.texto(xr + 5.0, ym - 0.4, p["nome"] + (" ×%d" % p["repete"] if p["repete"] > 1 else ""), tam=2.6, cor=p["cor"],
                ancora="start", papel=True, peso=700)
        f.texto(xr + 5.0, ym + 2.6, "%s a %s" % (_nivel(p["z0"]), _nivel(p["z1"])), tam=1.9, cor="#5b6573", ancora="start",
                papel=True, peso=500)
    # cotas de nível na esquerda: a base e o topo da obra
    for z in (z0, z1):
        _, y = f.p(x0, z)
        f.texto(f.me - 2.5, y + 0.7, _nivel(z), tam=1.9, cor="#5b6573", ancora="end", papel=True, peso=500)
    return f.svg("desenho corte")


_LARG_ELEVACAO = dict(_LARG_PAPEL, pilares=0.55, pilaretes=0.4, cliente=0.18)


def elevacao_svg(geo: Dict[str, dict], eixos: Optional[dict], frontal: bool = False, largura: float = 186.0,
                 altura_max: float = 95.0) -> str:
    """A elevação da obra de um pavimento: a estrutura projetada num plano vertical — `frontal` olhando o lado curto,
    senão o comprido (lateral) —, as barras pela cor do papel (a parte do cliente em cinza), os eixos daquela direção
    com as bolhas embaixo, os níveis (o piso e o topo do aço) à esquerda e as cotas: entre eixos embaixo, a altura à
    direita."""
    if not geo:
        return ""
    if eixos and eixos.get("eixo_g"):
        g = tuple(eixos["eixo_g"])[:2]
        q = tuple(eixos.get("perp_g") or (-g[1], g[0]))[:2]
    else:
        g, q = (1.0, 0.0), (0.0, 1.0)
    pts = [v for d in geo.values() for v in d["verts"][:: max(1, len(d["verts"]) // 16)]]
    ext_g = max(v[0] * g[0] + v[1] * g[1] for v in pts) - min(v[0] * g[0] + v[1] * g[1] for v in pts)
    ext_q = max(v[0] * q[0] + v[1] * q[1] for v in pts) - min(v[0] * q[0] + v[1] * q[1] for v in pts)
    longo_g = ext_g >= ext_q
    # a direção horizontal do desenho e os eixos que a cortam
    usa_g = longo_g != frontal
    h = g if usa_g else q
    marcos = sorted((eixos or {}).get("numeros" if usa_g else "letras") or [], key=lambda x: x["pos"])

    def hz(v):
        return (v[0] * h[0] + v[1] * h[1], v[2])
    hs = [hz(v)[0] for v in pts] + [x["pos"] for x in marcos]
    zs = [d["z0"] for d in geo.values()] + [d["z1"] for d in geo.values()]
    x0, x1, z0, z1 = min(hs), max(hs), min(min(zs), 0.0), max(zs)
    f = _Folha(x0, z0, x1, z1, largura, altura_max, margem=(16.0, 20.0 if marcos else 12.0, 6.0, 26.0))
    # o piso
    f.linha((x0 - 800.0, 0.0), (x1 + 800.0, 0.0), "#868e96", 0.25)
    # eixos (traço-ponto, por baixo)
    for x in marcos:
        f.linha((x["pos"], 0.0), (x["pos"], z1 + 300.0), "#c0392b", 0.12, ' stroke-dasharray="3 0.8 0.6 0.8"')
    ordem = {k: i for i, k in enumerate(["cliente"] + _ORDEM_PINTURA)}
    for d in sorted(geo.values(), key=lambda d: ordem.get(d["papel"], 0)):
        cor = PAPEIS.get(d["papel"], PAPEIS["outros"])[1]
        larg = _LARG_ELEVACAO.get(d["papel"], 0.25)
        if d["seg"]:
            a, b = hz(d["seg"][0]), hz(d["seg"][1])
            if math.dist(a, b) * f.k >= 0.3:
                f.linha(a, b, cor, larg, ' stroke-linecap="round"')
                continue
        # peça vista de topo (a barra na direção do olhar): um ponto
        a = hz(d["verts"][0])
        x, y = f.p(*a)
        f.add('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s"/>' % (x, y, max(larg, 0.25), cor))
    # níveis à esquerda: o piso, o topo do aço (o nosso) e, com a parte do cliente, o topo dela
    nosso = [d["z1"] for d in geo.values() if d["papel"] != "cliente"]
    niveis = [0.0] + ([max(nosso)] if nosso else []) + ([z1] if nosso and z1 > max(nosso) + 50.0 else [])
    for z in niveis:
        _, y = f.p(x0, z)
        f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#1f6feb" stroke-width="0.12" stroke-dasharray="0.8 0.6"/>'
              % (f.me - 18.0, y, f.me - 1.0, y))
        f.add('<path d="M%.2f %.2f l1.2 -1.6 h-2.4 z" fill="#1f6feb"/>' % (f.me - 15.0, y))
        f.texto(f.me - 13.0, y - 0.6, _nivel(z), tam=2.0, cor="#1f6feb", ancora="start", papel=True)
    # bolhas e cotas embaixo
    _, ypiso = f.p(x0, 0.0)
    if marcos:
        yb = f.H - 4.0
        for x in marcos:
            px, _ = f.p(x["pos"], 0.0)
            f.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#c0392b" stroke-width="0.12"/>' % (px, ypiso + 0.5, px, yb - 2.6))
            f.add('<circle cx="%.2f" cy="%.2f" r="2.6" fill="#fff" stroke="#c0392b" stroke-width="0.25"/>' % (px, yb))
            f.texto(px, yb + 0.85, x["nome"], tam=2.4, cor="#c0392b", papel=True, peso=700)
        ps = [f.p(x["pos"], 0.0)[0] for x in marcos]
        for a, b, xa_, xb_ in zip(ps, ps[1:], marcos, marcos[1:]):
            _cota(f, a, b, ypiso + 5.5, True, _n((xb_["pos"] - xa_["pos"]) / 1000.0, 2))
        if len(ps) > 2:
            _cota(f, ps[0], ps[-1], ypiso + 10.5, True, _n((marcos[-1]["pos"] - marcos[0]["pos"]) / 1000.0, 2))
    else:
        xa, _ = f.p(x0, 0.0)
        xb, _ = f.p(x1, 0.0)
        _cota(f, xa, xb, ypiso + 5.5, True, _n((x1 - x0) / 1000.0, 2))
    # a altura à direita (do piso ao topo)
    xr, _ = f.p(x1, 0.0)
    _, ytopo = f.p(x1, z1)
    _cota(f, ytopo, ypiso, xr + 6.0, False, _n((z1 - 0.0) / 1000.0, 2))
    return f.svg("desenho elevacao")


def _nivel(z: float) -> str:
    return ("+" if z >= 0 else "") + _n(z / 1000.0, 2)


# ============================================================ fotos do 3D

#: Ângulo das fotos do dossiê (diagnostico.js, ANGULOS).
ANGULO = "aerea_frente"
#: A direção da câmera "aérea de frente" (diagnostico.js): observador em +x, −y, acima.
DIR_AEREA = (0.95, -1.25, 0.8)


def direcao_pelo_aco(doc, pecas) -> List[float]:
    """A direção da câmera aérea do lado em que o aço está: o centro das peças de aço contra o centro do modelo inteiro
    (o pré-moldado junto) decide o sinal de x e de y — no PRATI a "aérea de frente" (+x, −y) mostrava o pré-moldado e o aço
    ficava atrás (usuário, 14/10: "inverter a visão dessa foto para dar mais destaque à estrutura metálica"). Sem diferença
    clara (menos de 5 % da extensão), fica o lado de sempre."""
    def centro(vs):
        # o centro da caixa, não a média dos vértices: os milhares de parafusos e furos do aço puxariam a média para ele
        return [(min(v[i] for v in vs) + max(v[i] for v in vs)) / 2.0 for i in range(2)]
    vs_aco = [v for e in pecas for v in (getattr(e, "vertices", None) or [])]
    vs_tudo = []
    for e in doc.entidades.values():
        if getattr(e, "vertices", None):
            vs_tudo.extend(e.vertices)
        elif hasattr(e, "inicio") and hasattr(e, "fim"):
            vs_tudo.extend([tuple(e.inicio), tuple(e.fim)])
    if len(vs_aco) < 4 or len(vs_tudo) < 4:
        return list(DIR_AEREA)
    ca, ct = centro(vs_aco), centro(vs_tudo)
    ext = [max(v[i] for v in vs_tudo) - min(v[i] for v in vs_tudo) for i in range(2)]
    sx = DIR_AEREA[0] if abs(ca[0] - ct[0]) < 0.05 * max(ext[0], 1.0) else abs(DIR_AEREA[0]) * (1.0 if ca[0] > ct[0] else -1.0)
    sy = DIR_AEREA[1] if abs(ca[1] - ct[1]) < 0.05 * max(ext[1], 1.0) else abs(DIR_AEREA[1]) * (1.0 if ca[1] > ct[1] else -1.0)
    return [round(sx, 3), round(sy, 3), DIR_AEREA[2]]


#: A camada da lona de ilustração (Kaefer, 19/10): escondida no modelo, aparece só nas fotos "com lona" do resumo — o
#: editor a mostra no modo "+telhas" das fotos (diagnostico.js), como as telhas.
CAMADA_LONA = re.compile(r"^lonas?$", re.I)


def lona_das_paredes(doc) -> List[str]:
    """Os ids da lona de ilustração que não é a da cobertura retrátil (a das paredes): fora da foto da cobertura retraída
    com a lona (o usuário, 19/10: "pode deixar essa foto sem as lonas laterais")."""
    return [e.id for e in doc.entidades.values() if CAMADA_LONA.match(str(getattr(e, "camada", "") or ""))
            and ((getattr(e, "atributos", None) or {}).get("elemento") != "lona_cobertura")]


def tem_lona(doc) -> bool:
    """O modelo tem a lona de ilustração (o fechamento que não é peça de aço)."""
    return any(CAMADA_LONA.match(str(getattr(e, "camada", "") or "")) and getattr(e, "visivel", True) is not False
               for e in doc.entidades.values())


def _angulo(X: dict) -> dict:
    """O pedido de ângulo das fotos: a direção escolhida pelo usuário ou calculada pelo lado do aço (`X["dir_foto"]`), senão
    o ângulo de sempre."""
    d = X.get("dir_foto")
    if isinstance(d, (list, tuple)) and len(d) == 3:
        return {"dir": [float(c) for c in d]}
    return {"angulo": ANGULO}


def _cores_das_linhas(b: dict, so: Optional[set] = None) -> Dict[str, list]:
    """{cor: [ids]} das linhas do tipo (a cor de cada linha da tabela); sem cor nas linhas, a do tipo"""
    cores: Dict[str, list] = collections.defaultdict(list)
    for li in b.get("linhas") or []:
        for i in li.get("ids") or []:
            if so is None or i in so:
                cores[li.get("cor") or b["cor"]].append(i)
    return dict(cores)


#: Até quantas linhas a foto do tipo leva a etiqueta com a marca; acima disso, o número da linha numa bolinha (as 30+
#: linhas de agulhamentos da PRATI viravam um emaranhado de etiquetas, 19/10)
ROTULOS_COM_MARCA = 6


def numerar(b: dict) -> bool:
    """O tipo com muitas linhas vai por números (a tabela é a legenda da foto)"""
    return len(b.get("linhas") or []) > ROTULOS_COM_MARCA


def _rotulos_das_linhas(b: dict, so: Optional[set] = None) -> List[dict]:
    """A etiqueta de cada linha na foto do tipo (19/10): a marca na cor da linha, presa à peça mais à frente dela; com
    muitas linhas, só o número da linha numa bolinha em cima da peça (diagnostico.js, __render) — no PDF, sem o 3D
    ligado, é ela que diz qual peça é qual"""
    saida = []
    por_numero = numerar(b)
    for k, li in enumerate(b.get("linhas") or [], 1):
        ids = [i for i in li.get("ids") or [] if so is None or i in so]
        marcas = list(li.get("marcas") or [])
        if not ids or not marcas:
            continue
        texto = str(k) if por_numero else ", ".join(marcas[:2]) + (" …" if len(marcas) > 2 else "")
        saida.append({"texto": texto, "cor": li.get("cor") or b["cor"], "ids": ids, "numero": por_numero})
    return saida


def pedidos_de_fotos(X: dict, tem_telhas: bool = False) -> List[dict]:
    """As fotos que o dossiê pede ao editor 3D (window.__render): a capa; cada tipo de estrutura em destaque na cor
    dele, com o resto apagado — na obra de vários pavimentos, no pavimento onde ele mais aparece, com o resto do aço
    daquele pavimento em cinza (o prédio inteiro deixava o tipo do tamanho de um risco); e cada pavimento sozinho,
    com o concreto em volta e cada peça na cor do tipo."""
    # a capa mostra a estrutura (com as telhas, o galpão virava uma laje cinza)
    pedidos = [dict({"nome": "capa"}, **_angulo(X))]
    # a obra com e sem a lona (Kaefer, 19/10: "quero ela com lona e sem lona"): os mesmos dois ângulos — a aérea da capa e
    # a perspectiva baixa do mesmo lado —, um par por ângulo
    # com a cobertura retrátil, o segundo par é ela retraída no mesmo ângulo (fotografar: outra carga do modelo)
    if X.get("tem_lona"):
        d = X.get("dir_foto") if isinstance(X.get("dir_foto"), (list, tuple)) and len(X["dir_foto"]) == 3 else DIR_AEREA
        d = [float(c) for c in d]
        segundo = d if X.get("cobertura_movel") else [math.copysign(1.35, d[0]), math.copysign(0.7, d[1]), 0.3]
        for k, dr in enumerate((d, segundo), 1):
            pedidos.append({"nome": "lona-%d-sem" % k, "dir": dr})
            com = {"nome": "lona-%d-com" % k, "angulo": ANGULO + "+telhas", "dir": dr}
            if k == 2 and X.get("cobertura_movel") and X.get("lona_paredes"):
                com["ocultar"] = list(X["lona_paredes"])            # retraída: só a lona da cobertura
            pedidos.append(com)
    pavs = X.get("pavimentos") or []
    papel_do_id = {}
    for b in X.get("estrutura") or []:
        for i in b["ids"]:
            papel_do_id[i] = b
    kg_total = sum(b["kg"] for b in X.get("estrutura") or []) or 1.0
    for b in X.get("estrutura") or []:
        # a peça miúda e o tipo de peso irrisório (os 6 ganchos do Vicente) ficam sem foto
        if b["chave"] == "suportes" or b["kg"] < 0.005 * kg_total:
            continue
        if X.get("varios") and pavs:
            linha = collections.Counter()
            for li in b["linhas"]:
                for p, q in li.get("onde") or []:
                    linha[p] += q
            nome_pav = linha.most_common(1)[0][0] if linha else pavs[0]["nome"]
            p = next(x for x in pavs if x["nome"] == nome_pav)
            andar = set(p.get("ids_andar") or [])
            ids = [i for i in b["ids"] if i in andar]
            if not ids:
                continue
            pedidos.append(dict({"nome": "tipo-" + b["chave"], "destaque": ids, "cor": b["cor"],
                                 "cores": _cores_das_linhas(b, set(ids)), "fantasma": "claro", "rotulos": _rotulos_das_linhas(b, set(ids)),
                                 "contexto": sorted(andar) + list(p.get("contexto") or []), "enquadrar": sorted(andar),
                                 "_onde": p["nome"]}, **_angulo(X)))
        else:
            pedidos.append(dict({"nome": "tipo-" + b["chave"], "destaque": list(b["ids"]), "cor": b["cor"],
                                 "cores": _cores_das_linhas(b), "fantasma": "claro", "rotulos": _rotulos_das_linhas(b)},
                                **_angulo(X)))
    for k, p in enumerate(pavs):
        ids = list(p.get("ids_andar") or [])
        if not ids:
            continue
        cores: Dict[str, list] = collections.defaultdict(list)
        for i in ids:
            b = papel_do_id.get(i)
            cores[b["cor"] if b else "#6c757d"].append(i)
        pedidos.append(dict({"nome": "pav-%d" % k, "destaque": ids, "cores": dict(cores),
                             "contexto": list(p.get("contexto") or []), "enquadrar": "destaque"}, **_angulo(X)))
    return pedidos


def fotografar(porta: int, slug: str, pasta: str, X: dict, tem_telhas: bool = False, avisar=None) -> Dict[str, str]:
    """Tira as fotos do dossiê pelo editor 3D do servidor (`porta`) e devolve {nome: caminho .jpg}. A placa de vídeo
    primeiro (o modelo grande não abre no swiftshader); sem ela, o swiftshader."""
    import os
    import shutil
    from saida import imagens3d
    if os.path.isdir(pasta):
        shutil.rmtree(pasta, ignore_errors=True)
    pedidos = pedidos_de_fotos(X, tem_telhas)
    onde = {p["nome"]: p.get("_onde") for p in pedidos}
    pedidos = [{k: v for k, v in p.items() if not k.startswith("_")} for p in pedidos]
    # a cobertura retrátil: tudo com ela aberta e o segundo par de fotos da lona com ela retraída (outra carga do modelo)
    if X.get("cobertura_movel"):
        lotes = [("aberta", [p for p in pedidos if not p["nome"].startswith("lona-2-")]),
                 ("retraida", [p for p in pedidos if p["nome"].startswith("lona-2-")])]
    else:
        lotes = [(None, pedidos)]
    erro = None
    for gpu in (True, False):
        try:
            fotos = {}
            for cobertura, lote in lotes:
                if lote:
                    fotos.update(imagens3d.fotografar(porta, slug, pasta, lote, largura=1500, altura=1000, escala=1.0, capa=None,
                                                      avisar=avisar, gpu=gpu, cobertura=cobertura))
            X["fotos_onde"] = {k: v for k, v in onde.items() if v}
            return fotos
        except Exception as exc:                                # noqa: BLE001
            erro = exc
    raise RuntimeError(str(erro))
