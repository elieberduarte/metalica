"""O MEMORIAL DO QUANTITATIVO — o documento que embasa cada número do RESUMO de orçamento (o Word da Hermes), na cara do
Resumo da obra do sistema (FERRAMENTA · RESUMO DA OBRA, decisões do usuário de 05/11/2026):

- o Word da Hermes continua (é o formato que o chefe quer: só quantidade e preço UNITÁRIO, o total em branco); o memorial
  passa a ser no padrão do Resumo da obra do Kaefer — a faixa escura, a foto do 3D, os cartões, as seções numeradas, as
  tabelas abertas e, em cada linha de peso, a foto com as peças dela em destaque;
- o memorial é enxuto, focado nos custos: os desenhos (implantação, elevações, pavimentos) ficam só no Resumo da obra;
- é o mesmo documento com o preço ligado (orçamento: "Memorial do quantitativo") ou desligado (`preco=False`);
- o exemplo aprovado: Projeto/ESTUDOS/Resumo-unificado/exemplo-memorial-unificado-2026-11-05.pdf.

Não faz conta de obra: formata o dicionário `D` do quantitativo já preparado (o contrato do quantitativos_dados.py da Hora
Certa, depois do `preparar()` do resumo_hermes.py: setores com o r5, linhas com o texto do Word, ponte, compra, ligações,
contradições, perguntas, histórico). O preço vem pronto em cada linha (`preco_texto`, `preco_item`, `preco_estimativa`): a
tabela de preços fica fora do git e do sistema.

O texto guarda as âncoras que a conferência do auditor lê de volta no PDF (conferir_resumo_hermes.py): a seção
"<linha> — <texto do Word>" (C04), "3. Quadro DESCRIÇÃO" … "Compra = líquido" e, em cada linha de peso, as colunas na ordem
perfil · peças · m · kg/m · kg (C07), a nota da compra com emenda e a coluna "emendas" (C23).
"""
import base64
import html
import os
import re
from typing import Dict, List, Optional

from saida import identidade

#: as cores das linhas de uma seção (a mesma na foto e na pílula da tabela); da 4ª em diante, a última
CORES = ["#e03131", "#1c7ed6", "#2f9e44", "#f08c00"]
#: a cor de cada linha do Word no quadro DESCRIÇÃO (o quadradinho), pelo começo do nome
COR_LINHA = [("Perfil W", "#e03131"), ("Perfil U", "#868e96"), ("Perfil L", "#495057"), ("Perfil Ø", "#5c7cfa"),
             ("Tubo", "#1c7ed6"), ("Suporte", "#f08c00"), ("Chapa expandida", "#0b7285"), ("Chaparia", "#ae3ec9"),
             ("Telha", "#2f9e44"), ("Steel deck", "#15aabf")]
#: os cartões da capa que vêm de uma linha do Word: (começo do nome, rótulo do cartão)
CARTOES_DE_LINHA = [("Tinta", "Área de pintura"), ("Intumescente", "Intumescente"), ("Steel deck", "Steel deck"), ("Telha", "Telhas")]

EXTRA_CSS = """
.preco { display: inline-block; font: 600 6.8pt 'Segoe UI', Arial; letter-spacing: .04em; color: #0b3d91; background: #e3edff;
         border-radius: 99px; padding: .4mm 2.4mm; }
.preco.estimativa { color: #8a3d0c; background: #fbe9dc; }
.preco.vazio { color: var(--mudo); background: var(--fundo); }
.faixa-preco { display: flex; flex-wrap: wrap; gap: 1mm 3mm; align-items: center; background: #f2f6ff; border-left: 3px solid #1c7ed6;
               border-radius: 1.6mm; padding: 1.6mm 3mm; margin: 1mm 0 2.5mm; font-size: 7.4pt; color: #24364f; break-inside: avoid; }
.faixa-preco .rot { font: 600 6.4pt 'Segoe UI', Arial; letter-spacing: .12em; text-transform: uppercase; color: #0b3d91; }
.faixa-topo .chave { color: var(--dest); }
.linha-word { break-inside: auto; }
.foto-em-cima .foto-tipo { max-width: 110mm; margin: 0 auto 2mm; }
.linha-word h3.tipo small { white-space: nowrap; }
table.mq td.orig { white-space: normal; font-size: 7pt; color: var(--mudo); }
table.mq td { vertical-align: middle; }
.perguntas h3.sec { color: #7a4f00; margin-top: 6mm; }
.perguntas table.q { border-collapse: collapse; width: 100%; margin: 0 0 2mm; font-size: 8pt; }
.perguntas .q th, .perguntas .q td { border-bottom: 1px solid var(--linha); padding: 1.2mm 2mm; vertical-align: top; text-align: left; }
.perguntas .q th { width: 30mm; font: 600 6.8pt 'Segoe UI', Arial; letter-spacing: .06em; text-transform: uppercase; color: var(--mudo); }
.perguntas .q th.p, .perguntas .q td.p { background: #fff4d6; color: #7a4f00; font-weight: 600; }
.perguntas figure { margin: 2mm 0 3mm; break-inside: avoid; }
.perguntas img { max-width: 100%; max-height: 95mm; border: 1px solid var(--linha); border-radius: 1.5mm; display: block; }
.perguntas table.tab { border-collapse: collapse; width: 100%; font-size: 7.6pt; }
.perguntas .tab th, .perguntas .tab td { border-bottom: 1px solid var(--linha); padding: 1mm 1.5mm; text-align: left; }
"""


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""))


def br(v, d=2) -> str:
    return ("{:,.%df}" % d).format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _foto_uri(caminho: Optional[str]) -> str:
    if not caminho or not os.path.exists(caminho):
        return ""
    with open(caminho, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


def _cor_da_linha(nome: str) -> str:
    for k, c in COR_LINHA:
        if nome.startswith(k):
            return c
    return "#adb5bd"


def _texto_word(x: dict) -> str:
    """o texto da quantidade como no Word, numa linha só (o do chumbador tem uma linha por diâmetro)"""
    return " / ".join(t.strip() for t in str(x.get("texto") or "").split("\n") if t.strip())


def _tem_numero(x: dict) -> bool:
    return bool(x.get("peso") or x.get("tabela") or (x.get("texto") and x["texto"] != "—"))


def chave_da_foto(x: dict) -> str:
    return "linha-" + re.sub(r"[^a-z0-9]+", "-", x["nome"].lower()).strip("-")


# ------------------------------------------------------------------------------------------------ as peças de cada linha
def _perfil_canonico(p: str) -> str:
    """'U 200×75×3,00 (FF)' e 'U 200×75×3,0' são o mesmo perfil: sem o (FF), os números pelo valor"""
    p = re.sub(r"\(FF\)", "", str(p or ""), flags=re.I).strip().replace("x", "×").replace("X", "×")
    return re.sub(r"\d+(?:,\d+)?", lambda m: "%g" % float(m.group(0).replace(",", ".")), re.sub(r"\s+", "", p))


def pedidos_de_fotos(D: dict, entidades: List[dict]) -> List[dict]:
    """As fotos do memorial para o editor 3D (saida.imagens3d.fotografar): a capa e, em cada linha de peso, as peças dela em
    destaque, na cor da linha da tabela (o resto em fantasma claro). A peça da linha pelo perfil (a lista de materiais dá o
    mesmo nome do 3D); a linha da chaparia, todas as chapas."""
    por_perfil: Dict[str, List[str]] = {}
    chapas = []
    for e in entidades:
        if e.get("tipo") == "chapa":
            chapas.append(e["id"])
        elif e.get("tipo") == "barra" and e.get("perfil"):
            por_perfil.setdefault(_perfil_canonico(e["perfil"]), []).append(e["id"])
    pedidos = [{"nome": "capa", "angulo": "aerea_frente"}]
    for x in D.get("linhas") or []:
        if not x.get("peso"):
            continue
        if x["nome"].startswith("Chaparia"):
            if chapas:
                pedidos.append({"nome": chave_da_foto(x), "destaque": chapas, "cores": {"#ae3ec9": chapas}, "fantasma": "claro",
                                "angulo": "aerea_frente"})
            continue
        cores: Dict[str, List[str]] = {}
        for k, i in enumerate(x.get("itens") or []):
            ids = por_perfil.get(_perfil_canonico(i.get("perfil")), [])
            if ids:
                cores.setdefault(CORES[min(k, len(CORES) - 1)], []).extend(ids)
        todos = [i for v in cores.values() for i in v]
        if todos:
            pedidos.append({"nome": chave_da_foto(x), "destaque": todos, "cores": cores, "fantasma": "claro",
                            "angulo": "aerea_frente", "enquadrar": "destaque"})
    return pedidos


def fotografar(porta: int, slug: str, pasta: str, D: dict, entidades: List[dict], avisar=None) -> Dict[str, str]:
    """As fotos pelo editor 3D do servidor (só abre o modelo para ver; não grava nada no projeto)."""
    from saida import imagens3d
    pedidos = pedidos_de_fotos(D, entidades)
    erro = None
    for gpu in (True, False):                       # a placa de vídeo primeiro (o modelo grande não abre no swiftshader)
        try:
            return imagens3d.fotografar(porta, slug, pasta, pedidos, largura=1500, altura=1000, escala=1.0, capa=None,
                                        gpu=gpu, avisar=avisar)
        except Exception as exc:                    # noqa: BLE001
            erro = exc
    raise RuntimeError(str(erro))


# ------------------------------------------------------------------------------------------------ as partes do HTML
def _h2(n: int, titulo: str, tag: str = "") -> str:
    return "<h2><span class=\"n\">%02d</span>%s%s</h2>" % (n, _esc(titulo), ("<span class=\"tag\">%s</span>" % _esc(tag)) if tag else "")


def _tabela(cab, linhas, total=None, num=None, classe="mq", larguras=None) -> str:
    """cab: os títulos; num: as colunas à direita (índices); as células já em HTML"""
    num = set(num or [])
    th = "".join("<th%s>%s</th>" % (" class=\"r\"" if i in num else "", _esc(c)) for i, c in enumerate(cab))
    cols = ("<colgroup>%s</colgroup>" % "".join("<col style=\"width:%s\">" % w for w in larguras)) if larguras else ""

    def tr(ln, cl=""):
        return "<tr%s>%s</tr>" % (cl, "".join("<td%s>%s</td>" % (" class=\"r\"" if i in num else "", c) for i, c in enumerate(ln)))
    corpo = "".join(tr(ln) for ln in linhas) + (tr(total, " class=\"total\"") if total else "")
    return "<table class=\"%s\">%s<thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (classe, cols, th, corpo)


def _tabela_livre(t) -> str:
    cab, linhas, total = t
    num = set(range(1, len(cab)))
    return _tabela(cab, [[_esc(c) for c in ln] for ln in linhas], [_esc(c) for c in total] if total else None, num)


def _pilula(cor: str, texto: str) -> str:
    return "<span class=\"pilula\" style=\"background:%s33;border-color:%s\">%s</span>" % (cor, cor, _esc(texto))


def _preco_html(x: dict, preco: bool) -> str:
    if not preco:
        return ""
    t = x.get("preco_texto") or ""
    if not t:
        return "<span class=\"preco vazio\">a Hermes preenche</span>"
    return "<span class=\"preco%s\">%s</span>" % (" estimativa" if x.get("preco_estimativa") else "", _esc(t))


#: até quantas linhas a tabela de uma linha do Word vai ao lado da foto
LINHAS_AO_LADO = 6


def _prefixo_comum(textos: List[str]) -> str:
    """O começo comum de todas as origens, cortado no último "; " (só quando vale a pena: 2 linhas ou mais, 30 letras ou mais)."""
    if len(textos) < 2 or not all(textos):
        return ""
    pre = os.path.commonprefix(textos)
    corte = pre.rfind("; ")
    pre = pre[:corte + 2] if corte >= 0 else (pre if all(len(t) == len(pre) for t in textos) else "")
    return pre if len(pre) >= 30 else ""


def _faixa_preco(x: dict, preco: bool) -> str:
    if not preco or not x.get("preco_texto"):
        return ""
    return ("<div class=\"faixa-preco\"><span class=\"rot\">Preço unitário → Word%s</span><span><b>%s</b></span>%s</div>"
            % (" (estimativa)" if x.get("preco_estimativa") else "", _esc(x["preco_texto"]),
               ("<span class=\"cinza\">%s</span>" % _esc(x["preco_item"])) if x.get("preco_item") else ""))


def _secao_linha(D: dict, x: dict, numero: str, fotos: Dict[str, str], preco: bool) -> str:
    """Uma linha do Word: o título "<linha> — <texto do Word>" (a âncora C04), a lista que soma o número, a foto com as peças
    em destaque, a nota e o preço unitário."""
    cor = _cor_da_linha(x["nome"])
    txt = _texto_word(x)
    resumo = ""
    corpo = ""
    if x.get("peso"):
        itens = x.get("itens") or []
        soma = sum(i["kg"] for i in itens)
        n = sum(i.get("n") or 0 for i in itens)
        m = sum(i.get("m") or 0 for i in itens)
        resumo = "%s peças%s · %s kg" % (br(n, 0), (" · %s m" % br(m, 1)) if m else "", br(soma, 1))
        # o começo comum das origens (os 10 perfis W do ADM: "3D: o rótulo de cada vão…; pilares…; tabela resumo 900/901: X m")
        # vai para uma nota, e a coluna fica só com o que muda de linha para linha
        prefixo = _prefixo_comum([str(i.get("origem") or "") for i in itens])
        linhas = []
        for k, i in enumerate(itens):
            c = CORES[min(k, len(CORES) - 1)]
            # a ordem perfil · peças · m · kg/m · kg é a que a conferência C07 lê no PDF
            resto_o = str(i.get("origem") or "")[len(prefixo):].strip(" ;") or "—"
            linhas.append(["<b>%s</b>" % _esc(i["perfil"]), _pilula(c, br(i["n"], 0)), br(i["m"], 1) if i.get("m") else "—",
                           br(i["kgm"], 3) if i.get("kgm") else "—", br(i["kg"], 1), "<span class=\"orig\">%s</span>" % _esc(resto_o)])
        corpo = _tabela(["Perfil / chapa", "Peças", "m", "kg/m", "kg (lista)", "Origem"], linhas,
                        ["Soma", "", "", "", br(soma, 1), "no RESUMO: <b>%s</b> (de 5 em 5)" % _esc(txt)], num=[1, 2, 3, 4],
                        larguras=["19%", "9%", "10%", "9%", "12%", "41%"])
        if prefixo:
            corpo += "<p class=\"nota\">Origem de todas as linhas: %s.</p>" % _esc(prefixo.strip(" ;"))
        foto = _foto_uri(fotos.get(chave_da_foto(x)))
        if foto:
            curta = len(itens) <= LINHAS_AO_LADO and max((len(l[-1]) for l in linhas), default=0) <= 120
            # a chaparia: todas as chapas numa cor só (a foto não separa espessura)
            leg = ("As chapas em destaque" if x["nome"].startswith("Chaparia") else "As peças da linha em destaque, na cor da tabela")
            fig = "<figure class=\"foto-tipo\"><img src=\"%s\" alt=\"\"><figcaption>%s</figcaption></figure>" % (foto, leg)
            # a foto ao lado só da tabela curta; com a de 10 linhas de origem comprida (a chaparia do ADM) ela espremia a tabela
            corpo = ("<div class=\"lado-a-lado\">%s<div>%s</div></div>" % (fig, corpo)) if curta else                     "<div class=\"foto-em-cima\">%s</div>%s" % (fig, corpo)
    if x.get("tabela"):
        corpo += _tabela_livre(x["tabela"])
    if x.get("tabela_extra"):
        corpo += _tabela_livre(x["tabela_extra"])
    nota = ("<p class=\"nota\">%s</p>" % _esc(x["nota"])) if x.get("nota") else ""
    return ("<section class=\"linha-word\"><h3 class=\"tipo\"><i style=\"background:%s\"></i>%s · %s — %s%s</h3>%s%s%s</section>"
            % (cor, numero, _esc(x["nome"]), _esc(txt), ("<small>%s</small>" % _esc(resumo)) if resumo else "", corpo,
               _faixa_preco(x, preco), nota))


def _cartoes(D: dict) -> str:
    C = D["compra"]
    area = D.get("area_total") or 0.0
    q = [("Peso líquido", br(D["peso"], 0), "kg", "pelo desenho%s · sem os chumbadores" % ((" · %s kg/m²" % br(D["peso"] / area)) if area else "")),
         ("Compra", br(C["r5"], 0), "kg", "líquido + sobra das barras %s + perda da chaparia %s" % (br(C["sobra_kg"], 0), br(C["perda_chapa_kg"], 0))),
         ("Área · montagem", br(area), "m²", "%d setor%s do quadro OBRA" % (len(D["setores"]), "es" if len(D["setores"]) != 1 else ""))]
    for k, rot in CARTOES_DE_LINHA:
        x = next((x for x in D["linhas"] if x["nome"].startswith(k) and x.get("texto") not in (None, "", "—")), None)
        if x and len(q) < 6:
            t = _texto_word(x)
            m = re.match(r"^\s*([\d\.,]+)\s*(m2|m²|kg|ml|m)\b\s*(.*)$", t)
            if m:
                q.append((rot, m.group(1), m.group(2).replace("m2", "m²"), m.group(3).strip(" –-—")))
            else:
                q.append((rot, t, "", ""))
    n_perg = D.get("n_perguntas")
    if n_perg and len(q) < 6:
        q.append(("Perguntas ao projetista", str(n_perg), "", D.get("perguntas_resumo") or ""))
    cols = 3 if len(q) in (3, 6) else 4
    return "<div class=\"ficha\"%s>%s</div>" % ("" if cols == 4 else " style=\"grid-template-columns:repeat(3,1fr)\"", "".join(
        "<div><span>%s</span><b>%s%s</b>%s</div>" % (_esc(r), _esc(v), ("<small>%s</small>" % _esc(u)) if u else "",
                                                    ("<em>%s</em>" % _esc(d)) if d else "") for r, v, u, d in q))


def _cabecalho(D: dict, marca: dict, nome_docx: str, preco: bool) -> str:
    pe = ["base: <b>modelo 3D do projeto</b> (%s)" % _esc(D.get("projeto") or "")]
    if D.get("modelo_data"):
        pe.append("3D gravado em <b>%s</b>" % _esc(D["modelo_data"]))
    pe.append("documento interno")
    pe.append("preço: <b class=\"chave\">%s</b>" % ("ligado" if preco else "desligado"))
    chip = " · ".join(x for x in (D.get("data") or "", D.get("rev") or "") if x)
    return ("<header class=\"faixa-topo\"><div class=\"topo\">%s%s</div><div class=\"marca\"><i></i><i></i></div>"
            "<div class=\"rotulo\">%s</div><h1>%s</h1><div class=\"desc\">embasa cada número do <b>%s</b></div>"
            "<div class=\"pe\">%s</div></header>"
            % (identidade.logo_ou_nome(marca, claro=True) or "<span></span>", ("<span class=\"rev\">%s</span>" % _esc(chip)) if chip else "",
               "Memorial do quantitativo" if preco else "Memorial do quantitativo · sem preço",
               _esc(D.get("cabecalho") or D.get("titulo") or ""),
               _esc(nome_docx), "".join("<span>%s</span>" % x for x in pe)))


def corpo_memorial(D: dict, nome_docx: str, fotos: Optional[Dict[str, str]] = None, marca: Optional[dict] = None,
                   preco: bool = True) -> str:
    """O miolo do memorial em HTML (sem o envelope)."""
    fotos = fotos or {}
    marca = marca or {}
    C = D["compra"]
    assert abs(sum(v for _k, v in D["ponte"]) - D["total_kg"]) < 1.0, "a ponte projeto → lista não fecha"
    partes = [_cabecalho(D, marca, nome_docx, preco)]
    capa = _foto_uri(fotos.get("capa"))
    if capa:
        partes.append("<figure class=\"capa\"><img src=\"%s\" alt=\"\"></figure>" % capa)
    partes.append(_cartoes(D))

    # 01 quadro OBRA — o mesmo do Word, e de que é feito cada setor
    sec = 1
    area = D.get("area_total") or 0.0
    partes.append(_h2(sec, "Quadro OBRA", "%d setor%s · %s m²" % (len(D["setores"]), "es" if len(D["setores"]) != 1 else "", br(area))))
    partes.append(_tabela(["Setor", "Projeção (m)", "Altura (m)", "Área (m²)", "kg (lista)", "kg no RESUMO", "kg/m²"],
                          [["<b>%s</b>" % _esc(s["nome"]), "%s × %s" % (br(s["L"]), br(s["C"])), br(s["H"]),
                            br(s["area"]) if s["area"] else "—", br(s["kg"], 1), br(s["r5"]), br(s["r5"] / s["area"]) if s["area"] else "—"]
                           for s in D["setores"]],
                          ["TOTAL", "", "", br(area), br(sum(s["kg"] for s in D["setores"]), 1), br(D["peso"]), br(D["peso"] / area) if area else "—"],
                          num=[2, 3, 4, 5, 6]))
    partes.append("<p class=\"nota\">O mesmo quadro OBRA do Word. %s O kg no RESUMO vai de 5 em 5 e fecha com o quadro DESCRIÇÃO "
                  "(o resto, %s kg, no setor mais pesado).</p>" % (_esc(D.get("obra_nota") or ""), br(D.get("dif_setor") or 0.0)))
    for s in D["setores"]:
        assert abs(sum(s["tipos"].values()) - s["kg"]) < 0.5, "o setor %s não fecha com os tipos dele" % s["nome"]
        partes.append("<h3>%s — %s kg</h3><p class=\"explica\">Projeção: %s. Altura: %s. Área: %s. %s peças.</p>" % (
            _esc(s["nome"]), br(s["r5"]), _esc(s.get("de_projecao") or ""), _esc(s.get("de_H") or ""), _esc(s.get("de_area") or ""),
            br(s.get("n") or 0, 0)))
        partes.append(_tabela(["Tipo de peça", "kg (lista)"], [[_esc(k), br(v, 1)] for k, v in sorted(s["tipos"].items(), key=lambda kv: -kv[1])],
                              ["Soma", br(sum(s["tipos"].values()), 1)], num=[1], larguras=["80%", "20%"]))

    # 02 do projeto ao peso
    sec += 1
    partes.append(_h2(sec, "Do projeto ao peso", "%s → %s t" % (br(D["ponte"][0][1] / 1000.0), br(D["total_kg"] / 1000.0))))
    partes.append("<p class=\"explica\">A ponte das tabelas do projetista ao peso do RESUMO: o que o projeto não pesa e as diferenças de leitura.</p>")
    partes.append(_tabela(["Do projeto à lista", "t"],
                          [[_esc(k), ("%+.2f" % (v / 1000.0)).replace(".", ",").replace("-", "−") if i else br(v / 1000.0)]
                           for i, (k, v) in enumerate(D["ponte"])],
                          [_esc(D.get("ponte_total") or "Lista do sistema (3D)"), br(D["total_kg"] / 1000.0)], num=[1], larguras=["86%", "14%"]))
    if D.get("faixa"):
        partes.append(_tabela(["O que ainda pode mudar o peso", "t a menos", "t a mais"],
                              [[_esc(k), br(a / 1000.0) if a else "—", ("+" + br(b / 1000.0)) if b else "—"] for k, a, b in D["faixa"]],
                              ["Faixa do peso", br(D["baixo_kg"] / 1000.0), br(D["alto_kg"] / 1000.0)], num=[1, 2]))
    if D.get("confere"):
        partes.append("<p class=\"explica\">%s</p>" % _esc(D.get("confere_nota") or ""))
        partes.append(_tabela(D.get("confere_cab") or ["A lista do projetista diz outra coisa — vale o desenho", "t se valesse a lista"],
                              [[_esc(k), ("%+.2f" % (v / 1000.0)).replace(".", ",")] for k, v in D["confere"]], num=[1],
                              larguras=["86%", "14%"]))

    # 03 quadro DESCRIÇÃO: o resumo das linhas e uma seção por linha
    sec += 1
    com_num = [x for x in D["linhas"] if _tem_numero(x)]
    pesadas = [x for x in D["linhas"] if x.get("peso")]
    numero_de = {id(x): "3.%d" % k for k, x in enumerate(com_num, 1)}
    partes.append(_h2(sec, "Quadro DESCRIÇÃO", "%d linhas com número" % len(com_num)))
    # "3. Quadro DESCRIÇÃO" é a âncora em que a conferência C07 começa a seção 3 (até "Compra = líquido")
    partes.append("<p class=\"explica\">3. Quadro DESCRIÇÃO — uma linha do Word por linha da tabela, com a quantidade%s e a "
                  "seção deste memorial que embasa o número. Peso: a lista de materiais do sistema sobre o 3D, dobrados pela regra "
                  "da fábrica (soma externa − 2t por dobra). As %d linhas de peso somam %s kg = o PESO TOTAL do RESUMO.</p>"
                  % (" e o preço unitário que vão para ele" if preco else "", len(pesadas), br(D["peso"])))
    linhas_q = []
    for x in com_num:
        lin = ["<span class=\"chip\" style=\"background:%s\"></span><b>%s</b>" % (_cor_da_linha(x["nome"]) if x.get("peso") else "#c9d1d6", _esc(x["nome"])),
               _esc(_texto_word(x))]
        if preco:
            lin.append(_preco_html(x, preco))
        lin.append(numero_de[id(x)])
        linhas_q.append(lin)
    cab = ["Linha do Word", "Quantidade"] + (["Preço unitário"] if preco else []) + ["Seção"]
    partes.append(_tabela(cab, linhas_q, num=[1], larguras=(["38%", "24%", "30%", "8%"] if preco else ["56%", "34%", "10%"])))
    partes.append(_tabela(["Peso", "kg"], [["Peso líquido (as %d linhas de peso)" % len(pesadas), br(D["peso"])],
                                           ["Sobra das barras + perda da chaparia (seção 4)", br(C["r5"] - D["peso"])]],
                          ["COMPRA", br(C["r5"])], num=[1], larguras=["80%", "20%"]))
    partes.extend(_secao_linha(D, x, numero_de[id(x)], fotos, preco) for x in com_num)
    traco = [x["nome"] for x in D["linhas"] if x.get("texto") == "—"]
    if traco:
        partes.append("<h3>Linhas com \"—\"</h3><p class=\"explica\">%s: não há na obra ou o projeto não tem o item (seção 6). "
                      "As linhas em branco são da Hermes.</p>" % _esc(", ".join(traco)))

    # 04 compra
    sec += 1
    partes.append(_h2(sec, "Compra", "%s kg" % br(C["r5"])))
    partes.append("<h3>Compra = líquido + sobra do plano de corte + perda da chaparia — %s kg</h3><p class=\"explica\">Sobra de %s kg "
                  "nos perfis (%s %% do líquido) e perda de %s kg na chaparia (%d %% de %s kg). %s</p>"
                  % (br(C["r5"]), br(C["sobra_kg"], 1), br(100.0 * C["sobra_kg"] / D["peso"], 0), br(C["perda_chapa_kg"], 1),
                     round(100.0 * C["perda_chapa_kg"] / C["chapa_kg"]) if C.get("chapa_kg") else 0, br(C.get("chapa_kg") or 0.0, 1),
                     _esc(C.get("nota") or "")))
    T = C.get("tabela")
    if T:
        assert abs(sum(r["sobra_kg"] for r in T) - C["sobra_kg"]) < 1.0, "a tabela da compra não fecha com a sobra"
        n_em = sum(r.get("emendas") or 0 for r in T)
        if C.get("nota_emenda"):
            partes.append("<p class=\"explica\"><b>%s</b>: as peças das barras menos cheias vão para as sobras das outras, inteiras ou "
                          "em dois pedaços de pelo menos 1 m, no máximo uma emenda por peça, só no perfil W; cantoneira, tubo e barra "
                          "redonda em barra de 6 m sem emenda, o dobrado no comprimento real. %s emenda%s no total (coluna "
                          "\"emendas\").</p>" % (_esc(C["nota_emenda"][0].upper() + C["nota_emenda"][1:]), br(n_em, 0), "s" if n_em != 1 else ""))
        partes.append("<h3>Lista por perfil</h3>" + _tabela(
            ["Perfil", "Peças", "m (real)", "kg/m", "kg líquido", "Compra", "Emendas", "m comprados", "kg compra", "Sobra (kg)"],
            [[_esc(r["perfil"]), br(r["pecas"], 0), br(r["m"], 1), br(r["kgm"], 3), br(r["kg"], 1), _esc(r["compra"]),
              br(r["emendas"], 0) if r.get("emendas") else "—", br(r["m_compra"], 1), br(r["kg_compra"], 1),
              br(r["sobra_kg"], 1) if r["sobra_kg"] > 0.05 else "—"] for r in T],
            ["Perfis", br(sum(r["pecas"] for r in T), 0), br(sum(r["m"] for r in T), 1), "", br(sum(r["kg"] for r in T), 1), "",
             br(n_em, 0), br(sum(r["m_compra"] for r in T), 1), br(sum(r["kg_compra"] for r in T), 1), br(C["sobra_kg"], 1)],
            num=[1, 2, 3, 4, 6, 7, 8, 9], classe="mq compra-perfis"))
        partes.append("<p class=\"nota\">kg/m = o da lista de materiais do sistema (o de compra: catálogo para o laminado, a regra da "
                      "fábrica para o dobrado). A chaparia vai à parte, com a perda.</p>")
    elif C.get("barras"):
        partes.append(_tabela(["Perfil", "Barra (m)", "Barras", "Sobra (m)", "kg/m", "Sobra (kg)"],
                              [[_esc(p), br(b, 0), br(n, 0), br(so, 2), br(km, 3), br(kg, 1)] for p, b, n, so, km, kg in C["barras"] if kg > 0.05],
                              ["Sobra das barras", "", "", "", "", br(C["sobra_kg"], 1)], num=[1, 2, 3, 4, 5]))
    com_preco = [x for x in D["linhas"] if x.get("preco_texto")]
    if preco and com_preco:
        partes.append("<h3>Preço unitário</h3><p class=\"explica\">Só o unitário, na 1ª coluna VALOR do Word; os totais ficam em "
                      "branco, para o gestor somar. Fonte: %s. Em laranja, a estimativa até a cotação chegar.</p>" % _esc(D.get("preco_fonte") or "—")
                      + _tabela(["Linha do RESUMO", "Unitário", "Item da tabela / motivo"],
                                [[_esc(x["nome"]), _preco_html(x, True), "<span class=\"cinza\">%s</span>" % _esc(x.get("preco_item") or "")]
                                 for x in com_preco], larguras=["30%", "28%", "42%"]))

    # 05 ligações
    LG = D.get("ligacoes")
    if LG:
        sec += 1
        partes.append(_h2(sec, "Ligações"))
        partes.append("<p class=\"explica\">%s</p>" % _esc(LG.get("texto") or ""))
        partes.append(_tabela(["Ligação", "Quantas no 3D"], [[_esc(k), br(v, 0)] for k, v in LG.get("contadas") or []], num=[1],
                              larguras=["82%", "18%"]))
        partes.append(_tabela(["Peças das ligações", "Peças", "kg (lista)"], [[_esc(k), br(n, 0), br(kg, 1)] for k, n, kg in LG.get("pecas") or []],
                              ["Ligações", "", br(sum(kg for _k, _n, kg in LG.get("pecas") or []), 1)], num=[1, 2]))
    # 06 fora do aço
    if D.get("fora"):
        sec += 1
        partes.append(_h2(sec, "Fora do aço e adendos"))
        partes.append("<ul class=\"explica\">%s</ul>" % "".join("<li>%s</li>" % f for f in D["fora"]))
    # 07 contradições
    if D.get("contradicoes"):
        sec += 1
        partes.append(_h2(sec, "O projeto diz outra coisa", "decidido pela evidência"))
        partes.append(_tabela(["O projeto diz", "O quantitativo segue", "Pergunta"],
                              [[_esc(a), _esc(b), _esc(c)] for a, b, c in D["contradicoes"]], larguras=["44%", "44%", "12%"]))
    # 08 perguntas
    if D.get("perguntas_html") and os.path.exists(D["perguntas_html"]):
        sec += 1
        PQ = open(D["perguntas_html"], encoding="utf-8").read()
        s_perg = PQ[PQ.index("</p>", PQ.index("<p class=sub>")) + 4:PQ.rindex("</body>")] if "<p class=sub>" in PQ else ""
        s_perg = (s_perg.replace("<h1 class=sec>", "<h3 class=sec>").replace("</h1>", "</h3>").replace("<h2>", "<h3>").replace("</h2>", "</h3>"))
        partes.append(_h2(sec, D.get("perguntas_titulo") or "Perguntas ao projetista"))
        partes.append("<p class=\"explica\">As mesmas do <b>%s</b> (para mandar), sem o nosso peso. %s</p><div class=\"perguntas\">%s</div>"
                      % (_esc(D.get("perguntas_pdf") or ""), _esc(D.get("perguntas_nota") or ""), s_perg))
    # 09 revisões
    if D.get("historico"):
        sec += 1
        partes.append(_h2(sec, "Revisões", "%d" % len(D["historico"])))
        # a mais nova em cima (a regra das revisões das pranchas, 24/10)
        partes.append(_tabela(["Revisão", "Data", "O que mudou"], [[_esc(r), _esc(d), _esc(t)] for r, d, t in reversed(D["historico"])],
                              larguras=["9%", "12%", "79%"]))
    if D.get("modelo_data"):
        partes.append("<p class=\"nota\">Base: o modelo.json gravado em %s; a lista de materiais do sistema sobre ele dá %s kg. O gerador "
                      "trava se um arquivo tirado do 3D for mais velho que ele.</p>" % (_esc(D["modelo_data"]), br(D.get("lista_kg", D["total_kg"]), 1)))
    return "".join(partes)


def html_memorial(D: dict, nome_docx: str, fotos=None, marca=None, preco: bool = True, paginado: bool = False) -> str:
    """O documento inteiro: o mesmo envelope, cabeçalho e rodapé do Resumo da obra (saida.resumos)."""
    from saida import resumos
    marca = marca or {}
    R = {"projeto": {"nome": D.get("titulo") or ""}, "dados": {"revisao": D.get("rev") or ""}, "marca": marca}
    titulo = "MEMORIAL DO QUANTITATIVO"
    corpo = corpo_memorial(D, nome_docx, fotos, marca, preco)
    css = identidade.variaveis_css(marca) + resumos._CSS + EXTRA_CSS
    from saida.entrega import nome_de_entrega
    t_pag = nome_de_entrega(D.get("titulo") or "", "Memorial do quantitativo")
    if paginado:
        from saida import printpdf
        return printpdf.envelope(resumos._correntes(R, titulo) + corpo, css, _esc(t_pag))
    return ("<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>%s</title><style>%s</style></head><body>%s</body></html>"
            % (_esc(t_pag), css, corpo))


def gerar(D: dict, nome_docx: str, destino_pdf: str, fotos=None, marca=None, preco: bool = True) -> dict:
    """Grava o memorial em PDF (e o HTML ao lado, para a prévia); os anexos de `D["anexos"]` vão no fim do PDF."""
    from saida import printpdf
    base = destino_pdf[:-4] if destino_pdf.lower().endswith(".pdf") else destino_pdf
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(html_memorial(D, nome_docx, fotos, marca, preco))
    paginado = base + ".paginado.html"
    try:
        with open(paginado, "w", encoding="utf-8") as f:
            f.write(html_memorial(D, nome_docx, fotos, marca, preco, paginado=True))
        printpdf.imprimir(paginado, destino_pdf, verbose=False, timeout=600)
    finally:
        try:
            os.remove(paginado)
        except OSError:
            pass
    if D.get("anexos"):
        import pymupdf
        mem = pymupdf.open(destino_pdf)
        for a in D["anexos"]:
            mem.insert_pdf(pymupdf.open(a))
        mem.save(destino_pdf + ".tmp")
        mem.close()
        os.replace(destino_pdf + ".tmp", destino_pdf)
    return {"pdf": destino_pdf, "html": base + ".html"}
