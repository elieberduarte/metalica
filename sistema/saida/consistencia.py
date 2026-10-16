# -*- coding: utf-8 -*-
"""Consistência das saídas de uma obra: o mesmo número tem de ser o mesmo em todo lugar (16/10/2026).

A auditoria de números da ME-Sooro (agente auditor-de-numeros, Projeto/BRIEFINGS/Briefing-auditor-me-sooro.md)
achou totais certos e detalhes contraditórios: a cópia da chapa na prancha com a quantidade de UMA tesoura ("CH2
08x" eram 24), a marca "T4" da planta levando à prancha de outra tesoura. Isto confere, só lendo os arquivos que
o programa gravou na pasta da obra (nada é refeito nem gravado):

  quantidades  romaneio × lista de materiais × peças do 3D, por posição
  pesos        cada linha (qtd × kg/pç), romaneio × lista, categorias, resumo de perfis + chapas + telhas
  fabricacao   a célula de fabricação de cada posição nas pranchas: uma só, com a quantidade e o peso do romaneio;
               os conjuntos desenhados somam as instâncias do conjuntos.csv
  copias       a cópia local de uma peça na prancha = Σ (composição × quantidade) dos conjuntos desenhados nela
  nomes        o nome de um conjunto na prancha é o mesmo conjunto do conjuntos.csv; toda posição tem prancha

Ainda não confere (próximos, ver o briefing): peças espelhadas juntas numa posição (N03), compra × fábrica
(bitola do parafuso, espessura comercial, terça sob medida — N04–N06), porcas e arruelas (N07), eixos (N09).

Uso: `conferir(pasta_da_obra)` → lista de achados {conferencia, gravidade, texto}; gravidade "fabrica" (leva a
fabricar, comprar ou montar diferente) ou "apresentacao". Linha de comando: testes/consistencia_obra.py.
"""
import collections
import csv
import json
import os
import re
from typing import Dict, List, Optional

#: tolerâncias: arredondamento de kg/pç (3 casas) vezes a quantidade, e 0,5 % nos totais
TOL_TOTAL = 0.005


def _num(s) -> Optional[float]:
    s = str(s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return None


def _csv(pasta, nome) -> Optional[List[dict]]:
    arq = os.path.join(pasta, "detalhamento", nome)
    if not os.path.exists(arq):
        return None
    with open(arq, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _json(arq):
    if not os.path.exists(arq):
        return None
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def _perto(a, b, rel=TOL_TOTAL, absoluto=0.05) -> bool:
    return abs(a - b) <= max(absoluto, rel * max(abs(a), abs(b)))


def _composicao(texto) -> Dict[str, int]:
    """"1× P1, 2× P2, 2× P3 (b)" → {"P1": 1, "P2": 2, "P3 (b)": 2} — a variante "(b)" é outra posição (Água Gelada:
    CH9 = P3 e CH13 = P3 (b); lida como "P3", a conferência somava as duas e acusava cópia errada)"""
    return {k.strip(): int(v) for v, k in re.findall(r"(\d+)\s*[×x]\s*([^,]+?)\s*(?=,|$)", str(texto or ""))}


def _posicoes_do_3d(pasta) -> Optional[collections.Counter]:
    d = _json(os.path.join(pasta, "modelo.json"))
    if d is None:
        return None
    ents = d.get("entidades") or []
    ents = list(ents.values()) if isinstance(ents, dict) else ents
    cont = collections.Counter()
    for e in ents:
        a = e.get("atributos") or {}
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except ValueError:
                a = {}
        p = (a.get("marcas") or {}).get("posicao")
        if p:
            cont[str(p)] += 1
    return cont


def _celulas(pasta) -> Optional[List[dict]]:
    """As células de todas as pranchas (metadados do desenho "pranchas"), cada uma com o número da prancha."""
    des = os.path.join(pasta, "desenhos-2d")
    if not os.path.isdir(des):
        return None
    out = []
    for arq in sorted(os.listdir(des)):
        if not arq.endswith(".desenho.json"):
            continue
        d = _json(os.path.join(des, arq)) or {}
        for p in (d.get("metadados") or {}).get("pranchas") or []:
            for c in p.get("celulas") or []:
                out.append(dict(c, prancha=p.get("numero"), arquivo=arq))
    return out or None


def conferir(pasta: str) -> List[dict]:
    achados: List[dict] = []

    def achar(conf, grav, texto):
        achados.append({"conferencia": conf, "gravidade": grav, "texto": texto})

    rom = _csv(pasta, "romaneio.csv")
    if rom is None:
        return [{"conferencia": "obra", "gravidade": "fabrica", "texto": "sem detalhamento/romaneio.csv: a obra não foi detalhada"}]
    pecas = [r for r in rom if (r.get("Tipo") or "") != "Acessório"]
    R = {r["Nome"]: r for r in pecas}
    lista = _json(os.path.join(pasta, "detalhamento", "lista-de-materiais.json")) or {}

    # ---------------------------------------------------------------- quantidades
    LP = {str(p.get("nome")): p for p in lista.get("posicoes") or []}
    if LP:
        for n in sorted(set(R) | set(LP)):
            r, p = R.get(n), LP.get(n)
            if not r or not p:
                achar("quantidades", "fabrica", f"{n}: só {'no romaneio' if r else 'na lista de materiais'}")
                continue
            if int(r["Qtd"]) != int(p.get("quantidade") or 0):
                achar("quantidades", "fabrica", f"{n}: {r['Qtd']} no romaneio × {p.get('quantidade')} na lista de materiais")
    no_3d = _posicoes_do_3d(pasta)
    if no_3d:
        # a posição do 3D que o detalhamento separou em variantes ("P48" e "P48 (b)": peças que não eram iguais) continua
        # P48 no 3D — compara a soma das variantes (Água Gelada: CH22 260 + CH23 68 = 328 no 3D)
        base = lambda x: re.sub(r"\s*\([^)]*\)$", "", x.strip())          # noqa: E731
        grupos = collections.defaultdict(lambda: [0, [], set()])
        for r in pecas:
            poss = tuple(sorted({base(x) for x in str(r.get("Posicao") or "").split("/") if x.strip()}))
            g = grupos[poss]
            g[0] += int(r["Qtd"])
            g[1].append(r["Nome"])
        for poss, (q_rom, nomes, _x) in sorted(grupos.items()):
            q3 = sum(no_3d.get(x, 0) for x in poss)
            if q3 and q3 != q_rom:
                achar("quantidades", "fabrica", f"{' + '.join(nomes)} ({'/'.join(poss)}): {q_rom} no romaneio × {q3} peças no 3D")

    # ---------------------------------------------------------------- pesos
    soma_rom = 0.0
    for r in pecas:
        q, pu, pt = int(r["Qtd"]), _num(r.get("Peso unit (kg)")), _num(r.get("Peso total (kg)"))
        if pu is None or pt is None:
            continue
        soma_rom += pt
        if abs(q * pu - pt) > max(0.06, 0.0005 * q + 0.005 * pt):
            achar("pesos", "apresentacao", f"{r['Nome']}: {q} × {pu:.3f} kg = {q * pu:.2f} ≠ total impresso {pt:.2f} kg")
    tot = (lista.get("totais") or {})
    if tot.get("peso") is not None and not _perto(soma_rom, float(tot["peso"])):
        achar("pesos", "fabrica", f"romaneio soma {soma_rom:.1f} kg × lista de materiais {float(tot['peso']):.1f} kg")
    cats = tot.get("categorias") or []
    if cats and tot.get("peso") is not None and not _perto(sum(float(c.get("peso") or 0) for c in cats), float(tot["peso"])):
        achar("pesos", "apresentacao", f"as categorias somam {sum(float(c.get('peso') or 0) for c in cats):.1f} kg × total {float(tot['peso']):.1f} kg")
    rp, rc = _csv(pasta, "resumo-perfis.csv"), _csv(pasta, "resumo-chapas.csv")
    if rp is not None and rc is not None and tot.get("peso") is not None:
        telhas = sum(float(t.get("peso") or 0) for t in lista.get("telhas") or [])
        s_res = sum(_num(x.get("Peso (kg)")) or 0 for x in rp) + sum(_num(x.get("Peso (kg)")) or 0 for x in rc) + telhas
        if not _perto(s_res, float(tot["peso"])):
            achar("pesos", "fabrica", f"resumo de perfis + chapas + telhas = {s_res:.1f} kg × total {float(tot['peso']):.1f} kg")

    # ---------------------------------------------------------------- pranchas
    cel = _celulas(pasta)
    if not cel:
        return achados
    cj = _csv(pasta, "conjuntos.csv") or []
    comp_de = {r["Conjunto"]: _composicao(r.get("Composicao")) for r in cj}
    inst_de = {r["Conjunto"]: int(r.get("Instancias") or 0) for r in cj}
    conj_do_nome = collections.defaultdict(set)
    for r in cj:
        conj_do_nome[r["Nome"]].add(r["Conjunto"])

    def alternativas(c) -> List[List[str]]:
        """"M2 + M2" → [["M2", "M2"]] (uma tesoura montada de duas metades); "M18 / M19" → [["M18"], ["M19"]] (uma
        família desenhada uma vez, com a quantidade da família toda)"""
        return [[m.strip() for m in alt.split("+") if m.strip()] for alt in str(c.get("marca") or "").split("/") if alt.strip()]

    def metades(c) -> List[str]:
        return [m for alt in alternativas(c) for m in alt]

    def por_unidade(c, pos) -> Optional[int]:
        """quantas peças `pos` cada unidade desenhada leva; None quando a família não é igual nisso"""
        vals = {sum(comp_de.get(m, {}).get(pos, 0) for m in alt) for alt in alternativas(c)}
        return vals.pop() if len(vals) == 1 else None

    def eh_conjunto(c) -> bool:
        it = c.get("item") or {}
        return str(it.get("classe") or "") == "Conjunto" or (bool(metades(c)) and all(m in comp_de for m in metades(c)))

    def nomes_da_celula(c) -> List[str]:
        """"A.T.1, A.T.2" (a célula típica de várias posições iguais); sem item, pelo título ("CU1 – 32x")"""
        it = c.get("item") or {}
        bruto = str(it.get("nome") or "") or (re.match(r"^(.+?) – \d+x", str(c.get("titulo") or "")) or [None, ""])[1]
        return [n.strip() for n in bruto.split(",") if n.strip()]

    fab = collections.defaultdict(list)          # (nomes da célula) → células de fabricação (não cópia)
    citado = set()
    # conjuntos desenhados: os que aparecem juntos numa célula formam um grupo; o grupo tem de somar as instâncias
    grupo = {}

    def raiz(m):
        while grupo.setdefault(m, m) != m:
            m = grupo[m]
        return m
    desenhado_cel = []                           # (membros, metades desenhadas)
    for c in cel:
        it = c.get("item") or {}
        nome = str(it.get("nome") or "")
        citado.update(nomes_da_celula(c))
        if c.get("copia") or not it:
            continue
        if eh_conjunto(c):
            membros = set(metades(c))
            for m in membros:
                grupo[raiz(m)] = raiz(next(iter(membros)))
            n_metades = len(alternativas(c)[0]) if alternativas(c) else 1
            desenhado_cel.append((membros, int(it.get("quantidade") or 0) * n_metades))
            # nomes: o "T4" desenhado é o mesmo T4 do conjuntos.csv (Sooro: T4 da planta = M6, prancha T4 = M8 + M9)
            if nome in conj_do_nome and not conj_do_nome[nome] & set(metades(c)):
                achar("nomes", "fabrica", f"prancha {c['prancha']}: \"{nome}\" desenhado é {' + '.join(metades(c))}, "
                                          f"mas no romaneio/conjuntos \"{nome}\" é {', '.join(sorted(conj_do_nome[nome]))}")
        elif nome:
            fab[tuple(nomes_da_celula(c))].append(c)

    # fabricação: uma célula por posição, com a quantidade e o peso do romaneio
    celulas_do_nome = collections.defaultdict(list)
    for nomes, cs in fab.items():
        for n in nomes:
            celulas_do_nome[n] += cs
    for n, cs in sorted(celulas_do_nome.items()):
        if n in R and len(cs) > 1:
            achar("fabricacao", "fabrica", f"{n}: {len(cs)} células de fabricação (pranchas {', '.join(str(c['prancha']) for c in cs)}) — a fábrica conta duas vezes")
    for nomes, cs in sorted(fab.items()):
        if not all(n in R for n in nomes):
            continue
        rotulo = ", ".join(nomes)
        q_rom = sum(int(R[n]["Qtd"]) for n in nomes)
        for c in cs:
            it = c["item"]
            if int(it.get("quantidade") or 0) != q_rom:
                achar("fabricacao", "fabrica", f"{rotulo} na prancha {c['prancha']}: {it.get('quantidade')}x × {q_rom} no romaneio")
            pu = _num(R[nomes[0]].get("Peso unit (kg)")) if len(nomes) == 1 else None
            if it.get("peso") and pu and not _perto(float(it["peso"]), pu, rel=0.011, absoluto=0.011):
                achar("fabricacao", "apresentacao", f"{rotulo} na prancha {c['prancha']}: {it['peso']} kg/pç × {pu} no romaneio")
    soma_cel, membros_g = collections.Counter(), collections.defaultdict(set)
    for membros, n in desenhado_cel:
        r_ = raiz(next(iter(membros)))
        soma_cel[r_] += n
        membros_g[r_] |= membros
    for r_, ms in sorted(membros_g.items()):
        if all(m in inst_de for m in ms) and soma_cel[r_] != sum(inst_de[m] for m in ms):
            achar("fabricacao", "fabrica", f"conjunto(s) {', '.join(sorted(ms))}: {soma_cel[r_]} desenhado(s) nas pranchas × "
                                           f"{sum(inst_de[m] for m in ms)} no conjuntos.csv")
    desenhados = {m for ms in membros_g.values() for m in ms}

    # cópias locais: a quantidade é a dos conjuntos desenhados NA MESMA prancha
    por_prancha = collections.defaultdict(list)
    for c in cel:
        por_prancha[(c.get("arquivo"), c.get("prancha"))].append(c)
    for (_arq, num), cs in sorted(por_prancha.items(), key=lambda kv: (str(kv[0][0]), kv[0][1] or 0)):
        conjuntos = [c for c in cs if not c.get("copia") and c.get("item") and eh_conjunto(c)]
        copias = [c for c in cs if c.get("copia") and c.get("item") and c.get("marca") and not eh_conjunto(c)]
        # variantes: o detalhamento separa P3 em "P3" (CH9) e "P3 (b)" (CH13), mas a composição do conjunto pode
        # continuar dizendo só "P3" (Água Gelada) — aí a conta é a soma das cópias das variantes
        base_de = lambda t: re.sub(r"\s*\([^)]*\)$", "", t.strip())       # noqa: E731
        soma_variantes = collections.Counter()
        for c in copias:
            toks = [t.strip() for t in str(c["marca"]).split("/") if t.strip()]
            if len(toks) == 1:
                soma_variantes[base_de(toks[0])] += int(c["item"].get("quantidade") or 0)
        for c in cs:
            it = c.get("item") or {}
            pos = str(c.get("marca") or "")
            if not c.get("copia") or not it or not pos or eh_conjunto(c):
                continue
            # a marca da cópia pode juntar posições ("M110 / P94"): soma o que cada uma leva
            toks = [t.strip() for t in pos.split("/") if t.strip()]
            vals = [(int(k["item"].get("quantidade") or 0), [por_unidade(k, t) for t in toks]) for k in conjuntos]
            if any(v is None for _q, vs in vals for v in vs):
                continue                          # família com composições diferentes: não dá para saber a conta
            esperado = sum(q * sum(vs) for q, vs in vals)
            tem = int(it.get("quantidade") or 0)
            if len(toks) == 1:
                b = base_de(toks[0])
                sem_variante = toks[0] == b and not any(re.match(re.escape(b) + r"\s*\(", p_) for k in conjuntos
                                                         for m in metades(k) for p_ in comp_de.get(m, {}))
                if sem_variante and soma_variantes[b] != tem:
                    # há cópias das variantes junto: a conta é a soma delas
                    if esperado and soma_variantes[b] != esperado:
                        achar("copias", "fabrica", f"prancha {num}: cópias de {b} e das variantes somam {soma_variantes[b]}x, "
                                                   f"mas os conjuntos desta prancha levam {esperado}")
                    continue
            if esperado and tem != esperado:
                achar("copias", "fabrica", f"prancha {num}: cópia de {it.get('nome')} ({pos}) com {it.get('quantidade')}x, "
                                           f"mas os conjuntos desta prancha levam {esperado}")
            elif not conjuntos and str(it.get("nome") or "") in R and int(it.get("quantidade") or 0) != int(R[it["nome"]]["Qtd"]):
                # sem conjunto desenhado na prancha (suportes na das terças, chapas de base na dos chumbadores): a cópia
                # leva o total da obra (pedido do usuário, 28/09)
                achar("copias", "fabrica", f"prancha {num}: cópia de {it.get('nome')} ({pos}) com {it.get('quantidade')}x, "
                                           f"sem conjunto desenhado nela: devia ser o total da obra, {R[it['nome']]['Qtd']}")

    # nomes: toda posição do romaneio aparece em alguma prancha — na célula dela ou dentro de um conjunto desenhado
    # (a barra da tesoura é fabricada pela elevação do conjunto)
    dentro = {pos for m in desenhados for pos in comp_de.get(m, {})}
    sem = sorted(n for n in R if n not in citado and not str(R[n].get("Tipo") or "").startswith("Telha")
                 and not ({x.strip() for x in str(R[n].get("Posicao") or "").split("/")} & dentro))
    if sem:
        achar("nomes", "fabrica", f"{len(sem)} posição(ões) do romaneio sem prancha: {', '.join(sem[:20])}{' …' if len(sem) > 20 else ''}")
    return achados


def resumo(achados: List[dict]) -> str:
    if not achados:
        return "consistente: nenhuma divergência"
    por = collections.Counter((a["conferencia"], a["gravidade"]) for a in achados)
    return "; ".join(f"{c} {n} ({g})" for (c, g), n in sorted(por.items()))
