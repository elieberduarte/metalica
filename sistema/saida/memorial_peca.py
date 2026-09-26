# -*- coding: utf-8 -*-
"""Memorial de cálculo de uma peça do modelo importado, em quatro camadas.

    from saida import memorial_peca
    doc = memorial_peca.documento(calculo, "M15", didatico=True, obra="Sala dos Compressores")
    doc["html"]                      # corpo da página (a tela /memorial monta o resto)
    memorial_peca.gerar_pdf(calculo, "M15", pasta, didatico=False)

O documento lê só o que o cálculo gravou em `calculo.json` (`nucleo3d.calculo_ifc.calcular`):
não calcula nada, como o memorial do galpão. As quatro camadas:

    1. Resumo      uma linha por peça do mesmo tipo: perfil, aproveitamento, o que governa
    2. Hipóteses   por extenso, com a fonte de cada uma (medida no modelo, informada, adotada)
    3. Conta       da carga por m² ao esforço, e cada verificação passo a passo com a norma
    4. Explicação  (didático) o que a verificação protege, o fenômeno, o que pesa, o erro
                   típico — recolhida em cada item e reunida no fim, para quem aprende

`didatico=False` é a versão profissional: sem a camada 4 e sem as dicas dos passos.
"""
import html as _html_mod
import os
import sys
from typing import Dict, List, Optional

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from nucleo.base import FONTES_DE_HIPOTESE, fmt           # noqa: E402
from saida import didatica                                 # noqa: E402
from saida.memorial import _Doc, _barra_aproveitamento, _identificacao_do_programa, _tabela   # noqa: E402

_AQUI = os.path.dirname(os.path.abspath(__file__))

#: Nome do tipo de peça, no singular e no plural, para os títulos.
TIPOS = {
    "terca": ("terça", "terças"), "longarina": ("longarina", "longarinas"), "banzo": ("banzo", "banzos"),
    "diagonal": ("diagonal", "diagonais"), "montante": ("montante", "montantes"), "pilar": ("pilar", "pilares"),
    "contraventamento": ("contraventamento", "contraventamentos"), "corrente": ("corrente", "correntes"),
    "travamento": ("travamento", "travamentos"),
}


def _esc(t) -> str:
    return _html_mod.escape("" if t is None else str(t), quote=False)


def _pct(x) -> str:
    return fmt(float(x or 0.0) * 100.0, 0) + " %"


# ---------------------------------------------------------------- leitura do cálculo

def _verificacao_da_marca(calculo: dict, marca: str) -> Optional[dict]:
    for v in calculo.get("verificacoes") or []:
        if v.get("marca") == marca:
            return v
    return None


def marcas_com_memorial(calculo: dict) -> List[dict]:
    """As peças que têm verificação gravada, na ordem do cálculo: [{marca, nome, tipo, perfil,
    aproveitamento, ok}]. É a lista da caixa de escolha da tela."""
    els = calculo.get("elementos") or {}
    saida = []
    for v in calculo.get("verificacoes") or []:
        m = v.get("marca")
        e = els.get(m) or {}
        saida.append({"marca": m, "nome": v.get("nome") or e.get("nome") or "", "tipo": v.get("tipo") or e.get("tipo") or "",
                      "perfil": v.get("perfil") or e.get("perfil") or "", "aproveitamento": e.get("aproveitamento", v.get("razao")),
                      "ok": e.get("ok", v.get("ok")), "governa": e.get("governa", "")})
    return saida


def marca_sugerida(calculo: dict, tipo: str = "terca") -> Optional[str]:
    """A peça mais solicitada do tipo (a primeira que se quer conferir)."""
    cands = [m for m in marcas_com_memorial(calculo) if m["tipo"] == tipo] or marcas_com_memorial(calculo)
    if not cands:
        return None
    return max(cands, key=lambda m: float(m.get("aproveitamento") or 0.0))["marca"]


# ---------------------------------------------------------------- pedaços de HTML

def _explicacao_html(ex: Optional[dict], titulo: str = "Entender", aberto: bool = False) -> str:
    """Bloco recolhido da camada 4 (protege, fenômeno, o que pesa, erro típico, desenho)."""
    if not ex:
        corpo = '<p class="pequeno lacuna">Explicação ainda não escrita para este item.</p>'
    else:
        partes = []
        if ex.get("protege"):
            partes.append(f'<p><b>O que protege.</b> {ex["protege"]}</p>')
        if ex.get("fenomeno"):
            partes.append(f'<p><b>O fenômeno.</b> {ex["fenomeno"]}</p>')
        if ex.get("desenho"):
            partes.append(f'<div class="desenho">{ex["desenho"]}</div>')
        if ex.get("pesa"):
            partes.append(f'<p><b>O que pesa no resultado.</b> {ex["pesa"]}</p>')
        if ex.get("erro"):
            partes.append(f'<p><b>Erro típico.</b> {ex["erro"]}</p>')
        corpo = "".join(partes)
    return (f'<details class="explica"{" open" if aberto else ""}><summary>{_esc(titulo)}</summary>'
            f'<div class="corpo">{corpo}</div></details>')


def _passos_html(passos: List[dict], didatico: bool) -> str:
    if not passos:
        return '<p class="pequeno">Sem memória de cálculo registrada para esta verificação.</p>'
    linhas = []
    for p in passos:
        texto = _esc(p.get("texto"))
        if didatico:
            dica = didatica.explicar_passo(p.get("texto", ""))
            if dica:
                texto += f'<div class="dica">{dica}</div>'
        linhas.append([(texto, "txt"), (p.get("formula") or "", "frm"), (p.get("conta") or "", "cta"),
                       (p.get("valor") or "", "val"), (_esc(p.get("norma")), "nrm")])
    return _tabela(["Passo", "Fórmula", "Com os números", "Resultado", "Norma"], linhas, "", "passos")


def _verificacao_html(v: dict, didatico: bool) -> str:
    ok = bool(v.get("ok"))
    if v.get("indeterminada"):
        cls, selo = "verif reprova", '<span class="selo nao">NÃO VERIFICADA</span>'
    elif ok:
        cls, selo = "verif", '<span class="selo ok">atende</span>'
    else:
        cls, selo = "verif reprova", '<span class="selo nao">NÃO ATENDE</span>'
    razao = float(v.get("razao") or 0.0)
    cab = (f'<div class="cab"><span class="t">{_esc(v.get("titulo"))}</span>'
           f'<span class="n">{_esc(v.get("norma"))}</span>{selo}</div>')
    cartoes = (
        '<div class="resultado">'
        f'<div class="c"><div class="k">Solicitante S<sub>d</sub></div><div class="v">{fmt(v.get("Sd"), 2)}</div>'
        f'<div class="u">{_esc(v.get("unidade"))}</div></div>'
        f'<div class="c"><div class="k">Resistente R<sub>d</sub></div><div class="v">{fmt(v.get("Rd"), 2)}</div>'
        f'<div class="u">{_esc(v.get("unidade"))}</div></div>'
        f'<div class="c"><div class="k">S<sub>d</sub>/R<sub>d</sub></div><div class="v">{fmt(razao, 3)}</div><div class="u">—</div></div>'
        f'<div class="c"><div class="k">Folga</div><div class="v">{fmt((1.0 - razao) * 100.0, 1)}</div><div class="u">%</div></div>'
        "</div>" + _barra_aproveitamento(razao, ok))
    obs = f'<p class="obs">{_esc(v.get("observacao"))}</p>' if v.get("observacao") else ""
    ex = _explicacao_html(didatica.explicar_verificacao(v.get("titulo", "")), "Entender esta verificação") if didatico else ""
    return f'<div class="{cls}">{cab}<div class="corpo">{_passos_html(v.get("passos") or [], didatico)}{cartoes}{obs}{ex}</div></div>'


def _hipoteses_html(hips: List[dict], didatico: bool) -> str:
    if not hips:
        return ('<p class="pequeno lacuna">O cálculo ainda não registra as hipóteses deste tipo de peça: '
                'o que vale está nas observações de cada verificação, abaixo.</p>')
    itens = []
    for h in hips:
        fonte = h.get("fonte") or "rotina"
        rot = FONTES_DE_HIPOTESE.get(fonte, fonte)
        ex = _explicacao_html(didatica.explicar_hipotese(h.get("chave", "")), "Entender") if didatico else ""
        itens.append(f'<li class="hip" data-chave="{_esc(h.get("chave"))}"><span class="fonte {fonte}" title="{_esc(rot)}">'
                     f'{_esc(rot)}</span><div class="texto">{h.get("texto", "")}</div>{ex}</li>')
    return f'<ol class="hipoteses">{"".join(itens)}</ol>'


def _resumo_html(calculo: dict, marca: str, tipo: str) -> str:
    els = calculo.get("elementos") or {}
    linhas = []
    for m in marcas_com_memorial(calculo):
        if m["tipo"] != tipo:
            continue
        e = els.get(m["marca"]) or {}
        dim = e.get("dimensionamento") or {}
        ap = float(m.get("aproveitamento") or 0.0)
        estado, cls = ("atende", "c ok") if m.get("ok") else ("NÃO ATENDE", "c nao")
        sel = " sel" if m["marca"] == marca else ""
        rot = f'<a href="?marca={_esc(m["marca"])}" class="marca">{_esc(m["marca"])}</a>'
        linhas.append([(rot, "l b" + sel), (_esc(m["nome"]), "l" + sel), (_esc(m["perfil"]), "l" + sel),
                       (fmt(dim.get("vao_m"), 2) if dim.get("vao_m") else "—", "r" + sel),
                       (fmt(dim.get("largura_m"), 2) if dim.get("largura_m") else "—", "r" + sel),
                       (str(dim.get("correntes")) if dim.get("correntes") is not None else "—", "c" + sel),
                       (fmt(ap * 100, 0) + " %", "r b" + sel), (_esc(m.get("governa")), "l" + sel), (estado, cls + sel)])
    if not linhas:
        return '<p class="pequeno">Nenhuma peça deste tipo verificada.</p>'
    return _tabela(["Posição", "Nome", "Perfil", "Vão (m)", "Largura (m)", "Corr.", "S/R", "Governa", "Estado"],
                   linhas, "", "tab small resumo", ["8%", "8%", "17%", "7%", "8%", "5%", "7%", "30%", "10%"])


def _conclusao(v: dict, e: dict, singular: str) -> str:
    ap = float(e.get("aproveitamento", v.get("razao")) or 0.0)
    crit = e.get("governa") or ""
    if v.get("indeterminada"):
        return (f'<div class="box atencao"><div class="t">Não verificada</div><p>Faltou dado para verificar esta '
                f'{singular}: {_esc(next((x.get("observacao") for x in v.get("verificacoes") or [] if x.get("indeterminada")), ""))}</p></div>')
    if e.get("ok", v.get("ok")):
        return (f'<div class="box ok"><div class="t">Atende</div><p>A {singular} usa {_pct(ap)} da capacidade. '
                f'O que chega mais perto do limite é <b>{_esc(crit)}</b> ({_esc(e.get("norma"))}).</p></div>')
    return (f'<div class="box atencao"><div class="t">Não atende</div><p>A {singular} está em {_pct(ap)} da capacidade: '
            f'<b>{_esc(crit)}</b> ({_esc(e.get("norma"))}) passa do limite em {fmt((ap - 1.0) * 100.0, 0)} %. '
            f'Confira primeiro as hipóteses da camada 2 — vão, largura, correntes e vento são o que mais pesa — e '
            f'depois as alternativas (mais correntes ou outro perfil).</p></div>')


def _caminhos_terca(v: dict, e: dict) -> str:
    """Para a terça: o que mudaria o resultado (só aritmética dos dados gravados, sem verificar)."""
    d = v.get("dados") or {}
    vao = float(d.get("vao_m") or 0.0)
    n = int(d.get("n_correntes") or 0)
    if vao <= 0:
        return ""
    L = vao * 100.0
    lb0, lb1 = L / (n + 1), L / (n + 2)
    return (f'<p>Os caminhos usuais quando uma terça reprova na sucção: <b>mais uma linha de correntes</b> '
            f'(L<sub>b</sub> cai de {fmt(lb0, 0)} para {fmt(lb1, 0)} cm, e a resistência à flambagem lateral sobe sem trocar o '
            f'perfil); <b>perfil mais alto</b> (W<sub>x</sub> e I<sub>x</sub> crescem com a altura); ou <b>Ue com enrijecedor</b> '
            f'(a mesa deixa de ter borda livre e a flambagem local recua). Trocar o aço não resolve: a flambagem não depende '
            f'de f<sub>y</sub>. No 3D, o bloco "No lugar dela" verifica cada alternativa com os mesmos esforços.</p>')


# ---------------------------------------------------------------- o documento

def documento(calculo: dict, marca: str, didatico: bool = True, obra: str = "", quando: str = "") -> dict:
    """Corpo HTML do memorial da peça `marca` e o que a tela precisa em volta dele."""
    v = _verificacao_da_marca(calculo, marca)
    if v is None:
        raise KeyError(f"a posição {marca} não tem verificação gravada no cálculo")
    els = calculo.get("elementos") or {}
    e = els.get(marca) or {}
    tipo = v.get("tipo") or e.get("tipo") or ""
    singular, plural = TIPOS.get(tipo, (tipo or "peça", (tipo or "peça") + "s"))
    nome = v.get("nome") or e.get("nome") or ""
    titulo = f"Memorial de cálculo — {singular} {marca}" + (f" ({nome})" if nome else "")
    par = calculo.get("parametros") or {}
    doc = _Doc()

    # cabeçalho
    cab = (f'<header class="cabecalho"><h1>{_esc(titulo)}</h1>'
           f'<p class="sub">{_esc(obra)}{" · " if obra else ""}{_esc(v.get("elemento"))}</p>'
           f'<p class="pequeno">Perfil {_esc(v.get("perfil"))} · aço {_esc(v.get("material"))}'
           + (f' · cálculo de {_esc(quando)}' if quando else "")
           + f' · {_esc(_identificacao_do_programa())}'
           + (" · versão didática" if didatico else " · versão profissional") + "</p></header>")

    # 1. resumo
    doc.cap(f"Resumo das {plural}")
    doc.p(f"Uma linha por posição de {singular} do cálculo: perfil, o que governa e o aproveitamento "
          f"(S<sub>d</sub>/R<sub>d</sub> da pior verificação). A linha destacada é a peça deste memorial.")
    doc.add(_resumo_html(calculo, marca, tipo))
    doc.add(_conclusao(v, e, singular))
    doc.fim_cap()

    # 2. hipóteses
    doc.cap("Hipóteses")
    doc.p("O que foi decidido antes da conta, e de onde cada decisão veio. É o que o profissional confere "
          "primeiro: uma hipótese errada não aparece na conta, que sai certa para a hipótese errada.")
    doc.add(_hipoteses_html(v.get("hipoteses") or [], didatico))
    if par:
        pares = [("V0 (m/s)", par.get("v0")), ("Categoria / classe", f"{par.get('categoria', '—')} / {par.get('classe', '—')}"),
                 ("Aberturas", par.get("aberturas")), ("Altura do beiral (m)", par.get("altura_beiral")),
                 ("Telha (kN/m²)", par.get("telha")), ("Sobrecarga (kN/m²)", par.get("sobrecarga")),
                 ("Carga extra (kN/m²)", par.get("carga_extra")), ("Correntes por vão", par.get("correntes")),
                 ("Aço formado a frio", par.get("aco_frio")), ("Flecha da terça", f"L/{par.get('flecha_terca')}")]
        linhas = [[(_esc(k), "l"), (_esc("—" if x in (None, "") else ("lido no modelo" if x is None else x)), "r")] for k, x in pares]
        doc.sec("Parâmetros do diálogo de cálculo")
        doc.add(_tabela(["Parâmetro", "Valor"], linhas, "", "tab small", ["55%", "45%"]))
    doc.fim_cap()

    # 3. conta
    doc.cap("Conta")
    if v.get("cargas"):
        doc.sec("Da carga por m² ao esforço na peça")
        doc.add(_passos_html(v["cargas"], didatico))
    doc.sec("Verificações")
    doc.p("Cada verificação traz a fórmula, a mesma fórmula com os números e o item da norma. "
          "Solicitante S<sub>d</sub> é o esforço de cálculo; resistente R<sub>d</sub> é o que a peça aguenta.")
    for x in v.get("verificacoes") or []:
        doc.add(_verificacao_html(x, didatico))
    doc.fim_cap()

    # 4. explicação (didático)
    if didatico:
        doc.cap("Para quem está aprendendo")
        crit = e.get("governa") or (v.get("verificacoes") or [{}])[0].get("titulo", "")
        ex = didatica.explicar_verificacao(crit)
        doc.sec(f"O que decide esta {singular}: {crit}")
        if ex:
            doc.add(_explicacao_html(ex, "A verificação que governa, explicada", aberto=True))
        else:
            doc.p('<span class="lacuna">Explicação ainda não escrita para esta verificação.</span>')
        if tipo == "terca":
            doc.sec("O que mudaria o resultado")
            doc.add(_caminhos_terca(v, e))
        doc.sec("Como conferir à mão")
        doc.p("Refaça na ordem da camada 3: (1) carga por metro = carga por m² × largura tributária; "
              "(2) combinação com os coeficientes da NBR 8681; (3) M = q·L²/8 e V = q·L/2; (4) resistência da "
              "seção pelo item da norma indicado em cada passo; (5) compare S<sub>d</sub>/R<sub>d</sub>. Se um número "
              "não bater, o erro está na hipótese daquele passo, não na fórmula.")
        doc.p("Obra que vai ser fabricada precisa de engenheiro calculista responsável (ART): este memorial é o "
              "material de conferência, não substitui a assinatura.")
        doc.fim_cap()

    return {"html": cab + doc.corpo(), "titulo": titulo, "marca": marca, "tipo": tipo, "nome": nome,
            "marcas": marcas_com_memorial(calculo), "didatico": didatico}


#: Estilo próprio do memorial da peça (soma-se ao memorial.css no PDF e ao estilo da tela).
CSS_EXTRA = """
.cabecalho h1 { font-size: 17pt; margin: 0 0 1mm 0; color: var(--azul) }
.cabecalho .sub { font-size: 10pt; color: #33363c; margin: 0 0 1mm 0 }
ol.hipoteses { list-style: none; padding: 0; margin: 0 0 3mm 0; counter-reset: hip }
ol.hipoteses li.hip { position: relative; border: 1px solid var(--linha); border-left: 4px solid var(--azul2);
  padding: 1.6mm 2.5mm 1.6mm 3mm; margin: 0 0 1.6mm 0; break-inside: avoid; counter-increment: hip }
ol.hipoteses li.hip::before { content: counter(hip) "."; position: absolute; left: -7mm; top: 1.6mm; width: 6mm;
  text-align: right; color: var(--azul2); font-weight: bold; font-size: 8.5pt }
ol.hipoteses .fonte { float: right; margin: 0 0 1mm 3mm; font-size: 7.2pt; text-transform: uppercase; letter-spacing: .04em;
  padding: .4mm 1.6mm; border-radius: 2px; border: 1px solid var(--linha); color: var(--cinza); background: #f5f7fb }
ol.hipoteses .fonte.modelo { border-color: #7fb0e6; color: #0b3d91; background: #e6f0fc }
ol.hipoteses .fonte.parametro { border-color: #d3b45a; color: #6d4f00; background: #fff5d6 }
ol.hipoteses .fonte.rotina { border-color: #b8a9d8; color: #4a2d8a; background: #f1ecfa }
ol.hipoteses .fonte.norma { border-color: #9dc9a8; color: #1f5f34; background: #e9f7ec }
ol.hipoteses .fonte.catalogo { border-color: #c9c9c9; color: #444; background: #f3f3f3 }
ol.hipoteses li.hip .texto { font-size: 9pt }
details.explica { margin: 1.6mm 0 0 0; border: 1px dashed #b9c5da; border-radius: 2px; background: #fbfcfe; font-size: 8.8pt }
details.explica summary { cursor: pointer; padding: 1.2mm 2.5mm; color: var(--azul2); font-weight: bold; font-size: 8.4pt }
details.explica .corpo { padding: 0 2.5mm 1.6mm 2.5mm }
details.explica .corpo p { text-align: left; margin: 0 0 1.2mm 0 }
details.explica .desenho { text-align: center; margin: 1mm 0 }
details.explica .desenho svg { max-width: 100%; height: auto }
table.passos td.txt .dica { font-size: 7.6pt; color: #4a5468; font-style: italic; margin-top: .6mm }
table.resumo td.sel { background: #fff5d6 }
table.resumo a.marca { color: var(--azul); font-weight: bold }
.lacuna { color: #a5231a }
"""


def montar_html_impressao(calculo: dict, marca: str, didatico: bool = False, obra: str = "", quando: str = "") -> str:
    """Documento HTML completo para o PDF (Paged.js, folha de estilo do memorial)."""
    from . import printpdf
    d = documento(calculo, marca, didatico=didatico, obra=obra, quando=quando)
    css = open(os.path.join(_AQUI, "memorial.css"), encoding="utf-8").read() + CSS_EXTRA
    corpo = d["html"]
    if didatico:
        corpo = corpo.replace("<details class=\"explica\">", "<details class=\"explica\" open>")
    return printpdf.envelope(corpo, css, d["titulo"])


def gerar_pdf(calculo: dict, marca: str, pasta: str, didatico: bool = False, obra: str = "", quando: str = "") -> str:
    """Gera o PDF do memorial da peça em `pasta` e devolve o caminho."""
    from . import printpdf
    os.makedirs(os.path.abspath(pasta), exist_ok=True)
    base = "Memorial_%s%s" % (marca, "_didatico" if didatico else "")
    html_path = os.path.join(pasta, base + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(montar_html_impressao(calculo, marca, didatico=didatico, obra=obra, quando=quando))
    pdf_path = os.path.join(pasta, base + ".pdf")
    printpdf.imprimir(html_path, pdf_path, verbose=False)
    return os.path.abspath(pdf_path)
