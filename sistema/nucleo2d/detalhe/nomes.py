# -*- coding: utf-8 -*-
"""Parte "nomes" do detalhamento (nucleo2d/detalhar.py é a fachada)."""
import collections
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados
from nucleo3d.modelo import Documento, Solido, Chapa
from nucleo3d import geometria as _geo
from nucleo2d.desenho import Desenho, Linha, Polilinha, Circulo, Arco, Texto, Cota
from nucleo2d import vistas as _vistas
from saida.detalhamento import (Posicao, Furo, analisar, CLASSES, _vista, _desenhar_furos, RHO_ACO, _area_2d,
                                _arestas_dos_furos, _ordem_natural, _autovetores, _lacos_2d)
from saida.desenhos import Estilo, _mm

from nucleo2d.detalhe.base import (  # noqa: E402
    DIAMETRO_AGULHAMENTO_DIAGONAL,
    PREFIXO_NOME,
    _assinatura,
    _caixa,
    _camada_da_posicao,
    _eh_redonda_perfil,
    _eh_terca,
    _eixo_da_peca,
    _eixos_da_assinatura,
    _grupos_de_furos,
    _marcas,
    _parede_da_peca,
    _tipo_ifc,
    marcas_de)
from nucleo2d.detalhe.conjuntos import (  # noqa: E402
    MENOR_TIRANTE)

#: Terça cujo centro fica além disto (mm) da caixa dos pilares em planta é de marquise.
FOLGA_MARQUISE = 300.0


def _assinaturas_de_terca(posicoes: Sequence[Posicao], camadas: Dict[str, str]) -> set:
    fora = set()
    for p in posicoes:
        if _eh_terca(p, camadas.get(p.marca, "")):
            for g in _grupos_de_furos(p.furos):
                a = _assinatura(g)
                if a and len(g) >= 2:
                    fora.add(_eixos_da_assinatura(a))
    return fora


def _tem_furacao_de_terca(pos: Posicao, assinaturas: set) -> bool:
    for g in _grupos_de_furos(pos.furos):
        a = _assinatura(g)
        if a and len(g) >= 2 and _eixos_da_assinatura(a) in assinaturas:
            return True
    return False


#: Chapa a menos disto (mm) da ponta de uma terça é o suporte dela.
ALCANCE_SUPORTE_TERCA = 200.0


def _chapas_onde_a_terca_encosta(pecas: Sequence[Solido], marcas_terca: set) -> set:
    """Marcas das chapas que têm a ponta de alguma terça a menos de ALCANCE_SUPORTE_TERCA
    do seu centro: são os suportes de terça, seja qual for a furação."""
    pontas = collections.defaultdict(list)
    cel = 500.0
    for e in pecas:
        if str(_marcas(e).get("posicao") or e.nome or e.id) not in marcas_terca:
            continue
        eixo = _eixo_da_peca(e)
        if not eixo:
            continue
        for p in eixo:
            pontas[tuple(int(math.floor(p[i] / cel)) for i in range(3))].append(p)
    fora = set()
    for e in pecas:
        if not (_tipo_ifc(e).startswith("IfcPlate") or isinstance(getattr(e, "parametrica", None), Chapa)) or not e.vertices:
            continue
        c = tuple(sum(v[i] for v in e.vertices) / len(e.vertices) for i in range(3))
        k = tuple(int(math.floor(c[i] / cel)) for i in range(3))
        perto = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for p in pontas.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if math.dist(p, c) <= ALCANCE_SUPORTE_TERCA:
                            perto = True
                            break
                    if perto:
                        break
                if perto:
                    break
            if perto:
                break
        if perto:
            fora.add(str(_marcas(e).get("posicao") or e.nome or e.id))
    return fora


def _caixa_dos_pilares(pecas: Sequence[Solido]):
    """(x0, y0, x1, y1) em planta dos pilares (IfcColumn com mais de 1 m de altura)."""
    xs, ys = [], []
    for e in pecas:
        if _tipo_ifc(e) == "IfcColumn" and e.vertices:
            cx = _caixa(e)
            if cx[2][1] - cx[2][0] > 1000.0:
                xs.extend((cx[0][0], cx[0][1]))
                ys.extend((cx[1][0], cx[1][1]))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _nome_numero(nome: str, prefixo: str):
    """("T.C.2-A", "T.C.") → (2, "A"); None quando o nome não tem esse prefixo."""
    m = re.match(re.escape(prefixo) + r"(\d+)(?:-([A-Z]))?$", nome or "")
    return (int(m.group(1)), m.group(2) or "") if m else None


def nomear(posicoes: Sequence[Posicao], camadas: Dict[str, str], pecas: Sequence[Solido],
           conjuntos_info: Sequence[dict], anteriores: Optional[dict] = None) -> dict:
    """Nome de produção de cada posição e conjunto, no padrão da fábrica:

    * tesouras (conjuntos com 8+ barras) T1, T2…; terças de cobertura T.C.n (mesmo
      perfil e comprimento = mesma família; furação diferente = T.C.n-A, -B…) e de
      marquise T.M.n (centro fora da caixa dos pilares em planta); suportes de terça
      S.T.n (chapa/cantoneira com a furação de alguma terça, ou o conjunto que a
      contém); agulhamentos A.G.n (barra solta comprida que não é terça, ou o conjunto
      de uma barra com chapas); contraventamentos C.V.n (barras redondas e os conjuntos
      com elas); castanhas C.S.n (chapa pequena presa a contraventamento); as demais
      chapas CH.n, barras B.n, telhas TL.n e conjuntos CJ.n;
    * a peça que só existe dentro de um conjunto (que não seja tesoura) chama-se pelo
      conjunto: S.T.1.1, S.T.1.2…

    Numeração por quantidade decrescente. `anteriores` ({"posicoes": {marca: nome},
    "conjuntos": {...}}, o nomes.json do projeto) mantém os nomes já dados: uma peça
    nova não renumera as outras. Devolve {"posicoes", "conjuntos", "tipos",
    "tipos_conjuntos", "ifc" (marca do IFC → nome), "ifc_conjuntos"} e escreve
    `pos.nome` em cada posição."""
    anteriores = anteriores or {}
    ant_pos = anteriores.get("posicoes") or {}
    ant_conj = anteriores.get("conjuntos") or {}
    ass_terca = _assinaturas_de_terca(posicoes, camadas)
    caixa_pil = _caixa_dos_pilares(pecas)
    centros: Dict[str, List[Tuple[float, float]]] = collections.defaultdict(list)
    for e in pecas:
        m = str(_marcas(e).get("posicao") or e.nome or e.id)
        if e.vertices:
            centros[m].append((sum(v[0] for v in e.vertices) / len(e.vertices), sum(v[1] for v in e.vertices) / len(e.vertices)))
    fundidas = {m: p.marca for p in posicoes for m in marcas_de(p)}
    conj_de_marca: Dict[str, str] = {}
    for c in conjuntos_info:
        for m in c.get("marcas") or [c["marca"]]:
            conj_de_marca[m] = c["marca"]
    tesouras = {c["marca"] for c in conjuntos_info if c.get("categoria") == "TESOURAS"}
    # nível de apoio e eixo do galpão pelas tesouras: a terça e o agulhamento abaixo do
    # apoio são de parede (lateral, ao longo do galpão; de oitão, atravessado)
    marcas_tes = set()
    for c in conjuntos_info:
        if c.get("categoria") == "TESOURAS":
            marcas_tes.update(c.get("marcas") or [c["marca"]])
    pecas_tes = [e for e in pecas if str(_marcas(e).get("conjunto") or "") in marcas_tes and e.vertices]
    eixo_galpao = None
    if pecas_tes:
        centros_tes = [(sum(v[0] for v in e.vertices) / len(e.vertices), sum(v[1] for v in e.vertices) / len(e.vertices),
                        sum(v[2] for v in e.vertices) / len(e.vertices)) for e in pecas_tes]
        _c, pca = _autovetores(centros_tes) if len(centros_tes) >= 3 else (None, None)
        if pca:
            # várias tesouras: o maior espalhamento dos centros é o eixo do galpão; uma só:
            # o menor espalhamento dos vértices (a normal dela)
            xs = [c_[0] for c_ in centros_tes]
            ys = [c_[1] for c_ in centros_tes]
            eixo_galpao = pca[0] if max(max(xs) - min(xs), max(ys) - min(ys)) > 500.0 else _autovetores([v for e in pecas_tes for v in e.vertices])[1][2]

    limites_g = None
    if eixo_galpao is not None:
        gs = [v[0] * eixo_galpao[0] + v[1] * eixo_galpao[1] + v[2] * eixo_galpao[2] for e in pecas if e.vertices for v in e.vertices]
        if gs:
            limites_g = (min(gs), max(gs))

    def de_parede(p: Posicao) -> Optional[str]:
        """"lateral", "oitao" ou None (na cobertura) para uma terça ou agulhamento, pela
        maioria das peças da posição (`_parede_da_peca`): a mesma terça pode viajar na
        cobertura e na saia, e o nome vai pela maioria."""
        ms = marcas_de(p)
        votos = collections.Counter(
            _parede_da_peca(e, eixo_galpao, limites_g)
            for e in pecas if str(_marcas(e).get("posicao") or e.nome or e.id) in ms and e.vertices)
        parede = sorted(((n, k) for k, n in votos.items() if k), reverse=True)
        if not parede or parede[0][0] <= votos.get(None, 0):
            return None
        return parede[0][1]

    def conjuntos_de(p: Posicao) -> set:
        proprias = set(marcas_de(p))
        return {conj_de_marca.get(c, c) for c in p.conjuntos if c not in proprias}

    # ---- tipo de cada posição
    tipo: Dict[str, str] = {}
    marcas_terca = {m for p in posicoes for m in marcas_de(p) if p.classe == "barra" and _eh_terca(p, camadas.get(p.marca, ""))}
    suportes = _chapas_onde_a_terca_encosta(pecas, marcas_terca)
    # chumbador: barra redonda em pé que atravessa uma chapa de base deitada (no TecnoMETAL
    # vem como conjunto próprio e caía na regra do tirante: "C.V.")
    from nucleo2d.detalhe.montagens import grupos_montados, _eh_chapa
    marcas_chumbador = set()
    try:
        por_id = {e.id: e for e in pecas}
        for g in grupos_montados(pecas, (), lambda m: m):
            if g["tipo"] == "chumbamento":
                marcas_chumbador |= {m for m in g["marcas"]
                                     if any(not _eh_chapa(e) and str(_marcas(e).get("posicao") or e.nome) == m
                                            for e in (por_id[i] for i in g["pecas"] if i in por_id))}
    except Exception:                                 # noqa: BLE001 — sem isso, fica a regra antiga
        marcas_chumbador = set()
    for p in posicoes:
        cls = p.classe
        if cls in ("chapa", "chapa_dobrada"):
            # suporte de terça é a chapa em que a terça encosta (geometria), não a que
            # tem a furação parecida: a chapinha de ponta do agulhamento tem os mesmos furos
            t = "suporte_terca" if any(m in suportes for m in marcas_de(p)) else "chapa"
        elif cls == "telha":
            t = "telha"
        elif re.search(r"BARRA\s*ROSC", p.perfil or "", re.I):
            t = "barra_roscada"                      # o pedaço roscado do esticador, não o tirante
        elif (cls == "barra_redonda" or (cls == "barra_conformada" and _eh_redonda_perfil(p.perfil))) \
                and any(m in marcas_chumbador for m in marcas_de(p)):
            t = "chumbador"
        elif cls == "barra_redonda" or (cls == "barra_conformada" and _eh_redonda_perfil(p.perfil)):
            t = "contraventamento" if p.comprimento >= MENOR_TIRANTE else "gancho"
            if t == "contraventamento" and 0 < min(p.H or 0.0, p.T or 0.0) < DIAMETRO_AGULHAMENTO_DIAGONAL:
                t = "agulhamento_diagonal"           # Ø3/8" com gancho: agulha diagonal, não contravento
        elif cls == "barra" and _eh_terca(p, camadas.get(p.marca, "")):
            t = "terca_cobertura"
            parede = de_parede(p)
            if parede:
                t = "terca_lateral" if parede == "lateral" else "terca_oitao"
            pts = [q for m in marcas_de(p) for q in centros.get(m, [])]
            if caixa_pil and pts:
                cx = sum(q[0] for q in pts) / len(pts)
                cy = sum(q[1] for q in pts) / len(pts)
                if (cx < caixa_pil[0] - FOLGA_MARQUISE or cx > caixa_pil[2] + FOLGA_MARQUISE
                        or cy < caixa_pil[1] - FOLGA_MARQUISE or cy > caixa_pil[3] + FOLGA_MARQUISE):
                    t = "terca_marquise"
        elif cls in ("barra", "barra_conformada"):
            t = "agulhamento" if (p.comprimento >= 1500.0 and not conjuntos_de(p)) else "barra"
            if t == "agulhamento" and de_parede(p):
                t = "agulhamento_lateral"
            if t in ("agulhamento", "agulhamento_lateral"):
                # barra comprida solta que não é agulha: a cantoneira do forro (L comprida
                # sem chapas de ponta) e o perfil de fechamento dobrado (U/C com a ponta curva)
                if re.match(r"^\s*L\s*\d", p.perfil or "", re.I):
                    t = "cantoneira_forro"
                elif cls == "barra_conformada" and re.match(r"^\s*[CUZ]\s*\d", p.perfil or "", re.I):
                    t = "perfil_fechamento"
        else:
            t = "barra"
        tipo[p.marca] = t

    # ---- tipo de cada conjunto pela composição
    tipo_conj: Dict[str, str] = {}
    for c in conjuntos_info:
        if c.get("categoria") == "TESOURAS":
            tipo_conj[c["marca"]] = "tesoura"
            continue
        comp = c.get("composicao") or {}
        cont = collections.Counter()
        for m, q in comp.items():
            cont[tipo.get(fundidas.get(m, m), "")] += q
        n = sum(comp.values())
        barras_conj = [fundidas.get(m, m) for m, q in comp.items() if tipo.get(fundidas.get(m, m)) in ("barra", "agulhamento") for _ in range(q)]
        if cont.get("chumbador") and n == cont.get("chumbador"):
            tipo_conj[c["marca"]] = "chumbador"
        elif cont.get("contraventamento"):
            tipo_conj[c["marca"]] = "contraventamento"
        elif cont.get("agulhamento_diagonal"):
            tipo_conj[c["marca"]] = "agulhamento_diagonal"
        elif len(barras_conj) == 1 and n <= 6 and n == len(barras_conj) + cont.get("chapa", 0) + cont.get("suporte_terca", 0):
            # uma barra com chapinhas de ponta: agulhamento (a barra é a agulha); de parede
            # quando fica abaixo do apoio das tesouras
            pb = next((q for q in posicoes if q.marca == barras_conj[0]), None)
            lateral = pb is not None and de_parede(pb) is not None
            tipo_conj[c["marca"]] = "agulhamento_lateral" if lateral else "agulhamento"
            tipo[barras_conj[0]] = tipo_conj[c["marca"]]
        elif cont.get("suporte_terca") and n <= 6:
            tipo_conj[c["marca"]] = "suporte_terca"
        else:
            tipo_conj[c["marca"]] = "conjunto"
    for p in posicoes:
        cs = conjuntos_de(p)
        if not cs:
            continue
        if tipo[p.marca] == "chapa" and p.L <= 250.0 and any(tipo_conj.get(c) == "contraventamento" for c in cs):
            tipo[p.marca] = "castanha"
        elif tipo[p.marca] in ("chapa", "suporte_terca") and all(tipo_conj.get(c) in ("agulhamento", "agulhamento_lateral") for c in cs):
            tipo[p.marca] = "suporte_agulhamento"          # as chapinhas de ponta da agulha
        elif tipo[p.marca] in ("chapa", "barra") and all(tipo_conj.get(c) in ("contraventamento", "agulhamento_diagonal") for c in cs):
            tipo[p.marca] = "suporte_contraventamento"     # cantoneiras e chapas de ponta do tirante

    def anterior(mapa, chaves, prefixo):
        for k in chaves:
            n = mapa.get(k)
            if n and _nome_numero(n, prefixo):
                return n
        return ""

    # ---- conjuntos: por tipo, quantidade decrescente, mantendo os nomes anteriores
    nomes_conj: Dict[str, str] = {}
    usados_por_prefixo: Dict[str, set] = collections.defaultdict(set)   # conjuntos e posições não repetem nome
    por_tipo: Dict[str, list] = collections.defaultdict(list)
    for c in conjuntos_info:
        por_tipo[tipo_conj[c["marca"]]].append(c)
    for t, lista in por_tipo.items():
        prefixo = PREFIXO_NOME[t]
        usados, pendentes = usados_por_prefixo[prefixo], []
        for c in sorted(lista, key=lambda c: (-c.get("instancias", 0), _ordem_natural(c["marca"]))):
            n = anterior(ant_conj, [c["marca"]] + list(c.get("marcas") or []), prefixo)
            num = _nome_numero(n, prefixo)[0] if n else None
            if num is not None and num not in usados:
                nomes_conj[c["marca"]] = "%s%d" % (prefixo, num)
                usados.add(num)
            else:
                pendentes.append(c)
        k = 1
        for c in pendentes:
            while k in usados:
                k += 1
            nomes_conj[c["marca"]] = "%s%d" % (prefixo, k)
            usados.add(k)

    # ---- posições que só existem dentro de um conjunto (não tesoura): nome do conjunto + .k
    nomes_pos: Dict[str, str] = {}
    partes: Dict[str, List[Posicao]] = collections.defaultdict(list)
    for p in posicoes:
        cs = {c for c in conjuntos_de(p) if c in nomes_conj}
        if len(cs) == 1 and conjuntos_de(p) == cs:
            c = next(iter(cs))
            if tipo_conj.get(c) != "tesoura":
                partes[c].append(p)
    principais = {"contraventamento": "contraventamento", "agulhamento": "agulhamento"}
    for c, lista in partes.items():
        if tipo_conj.get(c) in principais:
            for p in lista:
                if tipo[p.marca] == principais[tipo_conj[c]]:
                    nomes_pos[p.marca] = nomes_conj[c]      # o tirante é o C.V.n; a agulha é o A.G.n
            continue
        for i, p in enumerate(sorted(lista, key=lambda q: _ordem_natural(q.marca)), 1):
            nomes_pos[p.marca] = "%s.%d" % (nomes_conj[c], i)
            tipo[p.marca] = "parte"

    # ---- as demais por tipo; terças em famílias (perfil + comprimento) com variantes
    por_tipo = collections.defaultdict(list)
    for p in posicoes:
        if p.marca not in nomes_pos:
            por_tipo[tipo[p.marca]].append(p)
    for t, lista in por_tipo.items():
        prefixo = PREFIXO_NOME.get(t) or "P."
        familias: Dict[object, List[Posicao]] = collections.OrderedDict()
        for p in lista:
            chave = (re.sub(r"\s+", "", p.perfil or "").upper(), round(p.comprimento)) if t in ("terca_cobertura", "terca_marquise") else p.marca
            familias.setdefault(chave, []).append(p)
        ordem = sorted(familias.values(), key=lambda l: (-sum(q.quantidade for q in l), _ordem_natural(l[0].marca)))
        for l in ordem:
            l.sort(key=lambda q: (-q.quantidade, _ordem_natural(q.marca)))

        def atribuir(l, num):
            letras = set()
            for q in l:
                n = anterior(ant_pos, [q.marca] + marcas_de(q), prefixo)
                if n and _nome_numero(n, prefixo)[0] == num and _nome_numero(n, prefixo)[1] not in letras:
                    nomes_pos[q.marca] = n
                    letras.add(_nome_numero(n, prefixo)[1])
            j = 0
            for q in l:
                if q.marca in nomes_pos:
                    continue
                while True:
                    letra = "" if j == 0 else chr(64 + j)
                    j += 1
                    if letra not in letras:
                        break
                letras.add(letra)
                nomes_pos[q.marca] = "%s%d%s" % (prefixo, num, "-" + letra if letra else "")
        usados, pendentes = usados_por_prefixo[prefixo], []
        for l in ordem:
            n = anterior(ant_pos, [l[0].marca] + marcas_de(l[0]), prefixo)
            num = _nome_numero(n, prefixo)[0] if n else None
            if num is not None and num not in usados:
                usados.add(num)
                atribuir(l, num)
            else:
                pendentes.append(l)
        k = 1
        for l in pendentes:
            while k in usados:
                k += 1
            usados.add(k)
            atribuir(l, k)
    for p in posicoes:
        p.nome = nomes_pos.get(p.marca, "")
        p.tipo_nome = tipo.get(p.marca, "")
    ifc: Dict[str, str] = {}
    ifc_conj: Dict[str, str] = {}
    for c in conjuntos_info:
        for m in c.get("marcas") or [c["marca"]]:
            ifc_conj[m] = nomes_conj.get(c["marca"], "")
    ifc.update(ifc_conj)
    for p in posicoes:
        for m in marcas_de(p):
            if p.nome:
                ifc[m] = p.nome
    return {"posicoes": nomes_pos, "conjuntos": nomes_conj, "tipos": tipo, "tipos_conjuntos": tipo_conj,
            "ifc": ifc, "ifc_conjuntos": ifc_conj}


def aplicar_nomes(posicoes: Sequence[Posicao], nomes: Optional[dict]):
    """Escreve `pos.nome` a partir do nomes.json do projeto (por marca fundida ou por
    qualquer das marcas originais); sem registro, o nome fica vazio."""
    mapa = (nomes or {}).get("posicoes") or {}
    cam = (nomes or {}).get("camadas_2d") or {}
    tipos = (nomes or {}).get("tipos") or {}
    for p in posicoes:
        p.nome = mapa.get(p.marca) or next((mapa[m] for m in marcas_de(p) if mapa.get(m)), "")
        p.tipo_nome = tipos.get(p.marca) or next((tipos[m] for m in marcas_de(p) if tipos.get(m)), "")
        p.camada_2d = cam.get(p.marca) or next((cam[m] for m in marcas_de(p) if cam.get(m)), "")
        if not p.camada_2d and nomes:
            p.camada_2d = _camada_da_posicao(p, (nomes.get("tipos") or {}).get(p.marca, ""))
