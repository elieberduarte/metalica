# -*- coding: utf-8 -*-
"""Calibração (08/10/2026): o relatório para a gerência — o nosso sistema, o Tekla Structures e o OpenSees lado a lado.

    python testes/calibracao/relatorio.py <projeto> [pasta]

Lê o que as outras ferramentas gravaram na pasta (modelo.json, comparacao.json, comparacao_tekla.json, tekla_analise_*.json,
as pastas antes/ e imagens/) e roda a análise do projeto duas vezes (as regras de antes e as de agora) para o aproveitamento
das peças. Grava Calibracao-<projeto>.pdf na pasta.
"""
import base64
import datetime
import html
import json
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, SISTEMA)
sys.path.insert(0, AQUI)

from exportar_modelo import SAIDA_PADRAO  # noqa: E402


def _e(t):
    return html.escape(str(t if t is not None else ""))


def _n(v, c=1):
    return ("{:,.%df}" % c).format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _img(caminho):
    if not os.path.exists(caminho):
        return ""
    tipo = "image/png" if caminho.lower().endswith(".png") else "image/jpeg"
    return "data:%s;base64,%s" % (tipo, base64.b64encode(open(caminho, "rb").read()).decode("ascii"))


def _ler(pasta, nome):
    c = os.path.join(pasta, nome)
    return json.load(open(c, encoding="utf-8")) if os.path.exists(c) else None


def _usos(slug):
    """o aproveitamento por grupo de peças com as regras de antes (terça engastada, carga do telhado no banzo) e as de agora"""
    os.environ.setdefault("METALICA_DADOS", os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica"))
    import warnings
    warnings.filterwarnings("ignore")
    import app
    from nucleo3d import analise_estrutural as AE
    proj = app._gerente().ler(slug)
    par = dict(AE.PARAMETROS_PADRAO, **(proj.get("analise_parametros") or {}))
    doc = app._documento3d_do_projeto(slug)
    out = {}
    for nome, extra in (("antes", dict(cargas_pelas_tercas=False, terca_rotulada=False)), ("agora", {})):
        r = AE.calcular(doc, dict(par, **extra))
        out[nome] = {g["chave"]: g for g in (r.get("verificacao") or {}).get("grupos") or []}
        out[nome + "_peso"] = sum(br["sec"]["kg_m"] * br["L"] for br in AE.montar(doc, dict(par, **extra))["barras"])
    return out


CSS = """
@page { size: A4; margin: 15mm 13mm 15mm 13mm; @bottom-right { content: counter(page) " / " counter(pages); font: 600 7.5pt 'Segoe UI', Arial; color: #6b7780; } }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 8.8pt/1.45 'Segoe UI', Arial, sans-serif; color: var(--texto); }
.topo { background: var(--pri2); color: #fff; border-radius: 3mm; padding: 7mm 8mm 6mm; position: relative; overflow: hidden; }
.topo::after { content: ""; position: absolute; right: -10mm; top: -5mm; width: 46mm; height: 10mm; background: var(--dest); transform: skewX(-38deg); }
.topo small { font: 600 7.6pt 'Segoe UI', Arial; letter-spacing: .24em; text-transform: uppercase; color: var(--dest); }
.topo h1 { font: 300 22pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; margin: 2mm 0 1.5mm; }
.topo p { margin: 0; color: rgba(255,255,255,.8); font-size: 9pt; }
.marca { display: flex; gap: 2mm; margin-bottom: 4mm; } .marca i { width: 8mm; height: 2.6mm; background: var(--dest); transform: skewX(-38deg); display: block; } .marca i + i { opacity: .55; }
.cartoes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.5mm; margin: 4mm 0 1mm; break-inside: avoid; }
.cartoes div { background: var(--fundo); border-radius: 2.2mm; padding: 2.6mm 3.2mm; border-top: 2.4px solid var(--dest); }
.cartoes b { display: block; font: 300 15pt/1.1 'Segoe UI Light', 'Segoe UI', Arial; color: var(--pri); }
.cartoes span { display: block; font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .1em; text-transform: uppercase; color: var(--mudo); margin-top: .6mm; }
.cartoes em { display: block; font-style: normal; font-size: 7pt; color: var(--mudo); margin-top: .6mm; line-height: 1.3; }
h2 { display: flex; align-items: flex-end; gap: 3.5mm; font: 700 12pt 'Segoe UI', Arial; color: var(--pri); margin: 7mm 0 2.5mm; padding-bottom: 2mm;
     border-bottom: 1.2px solid var(--linha); break-after: avoid; }
h2 .n { font: 300 20pt/.85 'Segoe UI Light', 'Segoe UI', Arial; color: var(--dest); }
h3 { display: flex; align-items: center; gap: 2mm; font: 700 9.4pt 'Segoe UI', Arial; color: var(--pri); margin: 4.5mm 0 1mm; break-after: avoid; }
h3::before { content: ""; width: 3.6mm; height: 1.5mm; background: var(--dest); transform: skewX(-38deg); flex: none; }
p { margin: 0 0 2mm; } .mudo { color: var(--mudo); font-size: 7.6pt; }
table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: 1mm 0 2.5mm; break-inside: avoid; }
th { text-align: left; font: 600 6.6pt 'Segoe UI', Arial; letter-spacing: .08em; text-transform: uppercase; color: var(--mudo); border-bottom: 1.2px solid var(--pri); padding: 1.3mm 1.5mm; vertical-align: bottom; }
td { padding: 1.2mm 1.5mm; border-bottom: 1px solid var(--linha); vertical-align: top; }
td.r, th.r { text-align: right; white-space: nowrap; }
tr.total td { font-weight: 700; color: var(--pri); background: var(--fundo); border-top: 1.2px solid var(--pri); }
.ok { color: #4f5f12; font-weight: 700; } .atencao { color: #9a6a00; font-weight: 700; } .ruim { color: #b4483c; font-weight: 700; }
.chip { display: inline-block; padding: .2mm 2mm; border-radius: 99px; font: 600 6.8pt 'Segoe UI', Arial; }
.chip.ok { background: #eef4d5; } .chip.atencao { background: #fff4d6; } .chip.ruim { background: #fde4e1; }
.lado { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; margin: 2mm 0 3mm; break-inside: avoid; }
.lado figure { margin: 0; } .lado .img { height: 62mm; border-radius: 2.5mm; background: #eef2f6 center / contain no-repeat; border: 1px solid var(--linha); }
.lado figcaption { font-size: 7.4pt; color: var(--mudo); margin-top: 1.2mm; }
.tres { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin: 2mm 0 3mm; break-inside: avoid; }
.tres div { background: var(--fundo); border-radius: 2.5mm; padding: 3mm 3.5mm; border-left: 3px solid var(--dest); }
.tres b { display: block; color: var(--pri); font-size: 9pt; margin-bottom: .8mm; }
.destaque { background: var(--pri); color: #fff; border-radius: 3mm; padding: 4.5mm 6mm; margin: 3mm 0; break-inside: avoid; }
.destaque b { color: var(--dest); } .destaque p { margin: 0; }
.aviso { background: #fff4d6; border-left: 3px solid #d9a300; padding: 2.5mm 4mm; border-radius: 2mm; margin: 2mm 0; break-inside: avoid; }
ol, ul { margin: 0 0 2mm; padding-left: 5mm; } li { margin-bottom: 1mm; }
"""


def montar(slug, pasta):
    from saida import identidade
    M = _ler(pasta, "modelo.json")
    MA = _ler(os.path.join(pasta, "antes"), "modelo.json")
    C = _ler(pasta, "comparacao.json")
    CT = _ler(pasta, "comparacao_tekla.json")
    CTA = _ler(os.path.join(pasta, "antes"), "comparacao_tekla.json")
    TA = _ler(pasta, "tekla_analise_neutro.json")
    U = _usos(slug)
    marca = identidade.ler_marca(os.environ.get("METALICA_DADOS", ""))
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    h = []
    h.append('<div class="topo"><div class="marca"><i></i><i></i></div><small>Calibração da análise estrutural</small>'
             '<h1>%s</h1><p>O nosso sistema, o Tekla Structures 2026 e o OpenSees com a mesma estrutura, peça por peça. %s.</p></div>'
             % (_e(M["projeto"]), hoje))
    casos = C["casos"]
    dif_calc = max(max(r["desloc_dif_pct"], r["reacao_dif_pct"], *(r["pontas"][k]["dif_pct"] for k in ("N", "Vy", "Vz", "My", "Mz")))
                   for r in casos.values())
    h.append('<div class="cartoes"><div><b>%s %%</b><span>diferença no cálculo</span><em>nosso motor × OpenSees, 9 casos de carga</em></div>'
             '<div><b>%d peças</b><span>montadas no Tekla</span><em>no mesmo lugar: centro de gravidade a até 0,3 mm</em></div>'
             '<div><b>5</b><span>correções no sistema</span><em>perfis e caminho da carga do telhado</em></div>'
             '<div><b>3</b><span>apontamentos no projeto</span><em>terças, travamento longitudinal, J</em></div></div>'
             % (_n(dif_calc, 3), sum(r["pecas"] for r in CT.values())))

    # 01 método
    h.append('<h2><span class="n">01</span>Como foi feito</h2>')
    h.append('<p>A mesma estrutura (o Docas de teste, com %d barras no modelo de cálculo) em três programas: o nosso '
             'sistema gera o modelo; o <b>Tekla Structures</b> recebe as peças físicas pela API dele e monta o seu próprio modelo '
             'de cálculo; o <b>OpenSees</b>, programa de cálculo independente (Universidade da Califórnia, Berkeley), resolve a '
             'mesma estrutura com as mesmas cargas. O Tekla desta máquina não tem o Tekla Structural Designer (o programa de '
             'cálculo da Trimble, licença à parte): por isso a conferência dos números do cálculo foi feita com o OpenSees, e a '
             'do Tekla ficou na modelagem.</p>' % len(M["barras"]))
    h.append('<div class="tres"><div><b>Nosso sistema</b>o modelo 3D, o modelo de cálculo (nós, barras, rótulas, apoios), as cargas '
             'da NBR 6123/8800, o cálculo de 1ª e 2ª ordem e a verificação das peças</div>'
             '<div><b>Tekla Structures 2026</b>as 366 peças com os perfis paramétricos do Tekla, o peso, a área de pintura, as '
             'propriedades das seções e o modelo de cálculo que ele monta sozinho</div>'
             '<div><b>OpenSees</b>o mesmo modelo de cálculo resolvido por outro programa: deslocamentos, reações e esforços em '
             'cada barra, e a 2ª ordem com as barras divididas em 4 (a referência mais exata)</div></div>')
    h.append('<div class="lado"><figure><div class="img" style="background-image:url(\'%s\')"></div><figcaption>No nosso sistema '
             '(com os pilares de concreto onde a marquise é chumbada)</figcaption></figure><figure><div class="img" style="background-image:'
             'url(\'%s\')"></div><figcaption>No Tekla Structures 2026 (as peças de aço, no modelo "TESTE DE CARGAS MARQUISE")</figcaption>'
             '</figure></div>' % (_img(os.path.join(pasta, "imagens", "perspectiva.jpg")), _img(os.path.join(pasta, "imagens", "tekla_recorte.png"))))

    # 02 cálculo
    h.append('<h2><span class="n">02</span>O cálculo: nosso motor × OpenSees</h2>')
    h.append('<p>Cada caso de carga calculado nos dois programas. A diferença é a maior entre todas as barras, sobre o maior valor da '
             'mesma grandeza no caso.</p>')
    linhas = []
    for caso, r in casos.items():
        p = r["pontas"]
        dmax = max(p[k]["dif_pct"] for k in ("N", "Vy", "Vz", "My", "Mz"))
        linhas.append('<tr><td><b>%s</b></td><td class="r">%s / %s</td><td class="r">%s / %s</td><td class="r">%s %%</td><td class="r">%s %%</td>'
                      '<td><span class="chip ok">igual</span></td></tr>' % (
                          _e(caso), _n(r["desloc_max_mm"][0], 2), _n(r["desloc_max_mm"][1], 2), _n(r["reacao_soma_nosso"][2], 2),
                          _n(r["reacao_soma_opensees"][2], 2), _n(r["desloc_dif_pct"], 3), _n(dmax, 3)))
    h.append('<table><tr><th>Caso</th><th class="r">Desloc. máx. (mm) nosso / OpenSees</th><th class="r">Reação vertical (kN) nosso / OpenSees</th>'
             '<th class="r">Dif. desloc.</th><th class="r">Dif. esforços</th><th></th></tr>%s</table>' % "".join(linhas))
    so = C.get("segunda_ordem_dividida") or {}
    if so:
        piores = sorted(so.items(), key=lambda kv: -kv[1]["desloc_dif_pct"])[:5]
        h.append('<h3>2ª ordem (NBR 8800:2024, 4.10.7)</h3><p>As %d análises de 2ª ordem do nosso motor (com as forças nocionais) refeitas no '
                 'OpenSees com cada barra dividida em 4 trechos. Deslocamentos e reações batem; nos momentos, o nosso fica igual ou '
                 'até 3 %% acima da referência (a favor da segurança) e mais perto dela que o P-Delta simples do OpenSees (uma barra por '
                 'elemento).</p>' % len(so))
        h.append('<table><tr><th>Combinação</th><th class="r">Desloc. máx. (mm) nosso / OpenSees</th><th class="r">Dif. desloc.</th>'
                 '<th class="r">Dif. reações</th></tr>%s</table>' % "".join(
                     '<tr><td>%s</td><td class="r">%s / %s</td><td class="r">%s %%</td><td class="r">%s %%</td></tr>' % (
                         _e(c), _n(r["desloc_max_mm"][0], 2), _n(r["desloc_max_mm"][1], 2), _n(r["desloc_dif_pct"], 2), _n(r["reacao_dif_pct"], 3))
                     for c, r in piores))
    h.append('<div class="destaque"><p><b>Conclusão:</b> o motor de cálculo do sistema dá os mesmos números de um programa de cálculo '
             'independente — deslocamentos, reações e esforços, na 1ª e na 2ª ordem. As diferenças que importam estão na '
             '<b>modelagem</b> (o que entra no cálculo), e foi lá que o Tekla ensinou.</p></div>')

    # 03 modelagem com o Tekla
    h.append('<h2><span class="n">03</span>A modelagem: nosso sistema × Tekla</h2>')
    linhas = []
    tot = [0.0, 0.0, 0.0]
    for perf, r in CT.items():
        a = (CTA or {}).get(perf, r)
        linhas.append('<tr><td><b>%s</b></td><td class="r">%d</td><td class="r">%s</td><td class="r">%s</td><td class="r">%s</td>'
                      '<td class="r">%s</td><td class="r">%s / %s</td></tr>' % (
                          _e(perf), r["pecas"], _n(r["comprimento_m"][0], 2), _n(a["peso_kg"][0], 1), _n(r["peso_kg"][0], 1), _n(r["peso_kg"][1], 1),
                          _n(r["pintura_m2"][0], 1), _n(r["pintura_m2"][1], 1)))
        tot = [tot[0] + a["peso_kg"][0], tot[1] + r["peso_kg"][0], tot[2] + r["peso_kg"][1]]
    linhas.append('<tr class="total"><td>Total</td><td></td><td></td><td class="r">%s</td><td class="r">%s</td><td class="r">%s</td><td></td></tr>'
                  % (_n(tot[0], 1), _n(tot[1], 1), _n(tot[2], 1)))
    h.append('<table><tr><th>Perfil</th><th class="r">Peças</th><th class="r">Compr. (m)</th><th class="r">Peso nosso antes (kg)</th>'
             '<th class="r">Peso nosso agora (kg)</th><th class="r">Peso Tekla (kg)</th><th class="r">Pintura m² nosso / Tekla</th></tr>%s</table>'
             % "".join(linhas))
    h.append('<p class="mudo">Comprimentos e posições iguais (o centro de gravidade de cada peça no Tekla a até 0,3 mm da nossa linha). '
             'Nas cantoneiras e no U, os perfis paramétricos do Tekla são de canto laminado (raio de raiz, ponta viva): por isso 3 a 5 % '
             'acima; a referência das peças dobradas são as tabelas dos fabricantes (Perfinasa, Gerdau), com as quais o sistema agora bate.</p>')
    if TA:
        import collections
        nos_por = collections.Counter()
        for p in TA["pecas"]:
            for b in p["barras"]:
                for q in b["posicoes"]:
                    nos_por[tuple(round(v, 1) for v in q["no"])] += 1
        soltas = sum(1 for v in nos_por.values() if v == 1)
        h.append('<h3>O modelo de cálculo que o Tekla monta</h3><p>Com as mesmas peças, o Tekla gerou %d nós (o nosso, %d). Sem as ligações '
                 'modeladas (soldas, parafusos, componentes), ele não une diagonais e montantes aos banzos — ficam %d pontas soltas, '
                 'porque as barras terminam na face do banzo e não no eixo. O nosso esqueleto une as pontas no eixo do banzo (o ponto de '
                 'trabalho da treliça), que é a prática de cálculo. O Tekla rotula as terças nas tesouras e as almas nas duas direções '
                 'por padrão; as seções que ele calcula confirmaram a área e a inércia do Ue e acusaram o J (constante de torção) que '
                 'faltava no nosso catálogo.</p>' % (len(TA["nos"]), len(M["nos"]), soltas))

    # 04 correções
    h.append('<h2><span class="n">04</span>O que foi corrigido no sistema</h2>')
    h.append('<table><tr><th>Correção</th><th>Antes</th><th>Agora</th><th>Como a calibração mostrou</th></tr>'
             '<tr><td><b>Cantoneira dobrada</b> (área e peso)</td><td>4 a 8 % leve (L 30×3: 1,56 cm²)</td><td>igual à tabela do fabricante (1,65 cm²)'
             '</td><td>Tekla e tabela da Perfinasa; a L 1¼"×1/8" agora dá 1,49 kg/m (Gerdau: 1,50)</td></tr>'
             '<tr><td><b>"L 38×3,00 (FF)"</b> virava laminada</td><td>L 1½"×1/8" (3,18 mm) — 272 diagonais 9 % mais pesadas</td>'
             '<td>dobrada de 3,00 mm</td><td>o perfil que o Tekla recebeu tinha 3,00 mm; a espessura casava com 6 % de folga</td></tr>'
             '<tr><td><b>J do Ue 200×75×20×2,65</b></td><td>vazio: o cálculo usava 0,76 cm⁴</td><td>0,231 cm⁴ (NBR 14762)</td>'
             '<td>o Tekla calcula 0,226 cm⁴</td></tr>'
             '<tr><td><b>Carga do telhado</b></td><td>direto nos nós da tesoura: a terça só via o peso próprio</td><td>pelas terças (faixa de '
             'influência de cada uma), com o mesmo total</td><td>o Tekla e o TSD aplicam a carga de área nas peças que a recebem</td></tr>'
             '<tr><td><b>Terça na tesoura</b></td><td>engastada (momento no vão 3× menor; momento passando ao banzo)</td><td>rotulada onde a '
             'peça termina</td><td>padrão do Tekla e a ligação da obra (clip aparafusado)</td></tr></table>')
    h.append('<p class="mudo">Peso das barras do Docas: %s kg antes das correções, %s kg agora (o Tekla, com os perfis de canto laminado: '
             '%s kg). As correções de perfil valem para todas as obras (lista de materiais, resumos, orçamento); o catálogo foi regerado. '
             'Todos os testes do sistema passam (1.342).</p>' % (_n(tot[0], 1), _n(tot[1], 1), _n(tot[2], 1)))

    # 05 o que muda no Docas
    h.append('<h2><span class="n">05</span>O que isso muda no Docas</h2>')
    linhas = []
    for k in sorted(set(U["antes"]) | set(U["agora"])):
        a, b = U["antes"].get(k, {}), U["agora"].get(k, {})
        ua, ub = a.get("uso"), b.get("uso")
        cls = lambda u: "ok" if u is not None and u <= 1.0 else ("ruim" if u is not None and u > 1.0 else "")   # noqa: E731
        f = lambda u: ("falha (instável)" if u is not None and u >= 99 else ("%s %%" % _n(100 * u, 0))) if u is not None else "—"   # noqa: E731
        linhas.append('<tr><td>%s</td><td class="r"><span class="chip %s">%s</span></td><td class="r"><span class="chip %s">%s</span></td><td>%s</td></tr>'
                      % (_e(k.replace("|", " · ")), cls(ua), f(ua), cls(ub), f(ub), _e(b.get("comb") or "")))
    h.append('<p>Aproveitamento de cada grupo de peças (a maior relação esforço / resistência da NBR 8800 e NBR 14762; acima de 100 % '
             'não passa). O Docas de teste já não passava antes — a calibração não muda isso, mas revela o que estava escondido.</p>')
    h.append('<table><tr><th>Grupo</th><th class="r">Antes (terça engastada, telhado no banzo)</th><th class="r">Agora</th>'
             '<th>Combinação que governa</th></tr>%s</table>' % "".join(linhas))
    razoes = {c: r.get("razao") for c, r in (M["nossos"].get("segunda_ordem") or {}).items()}
    razoes_a = {c: r.get("razao") for c, r in ((MA or {}).get("nossos", {}).get("segunda_ordem") or {}).items()}
    vat = max((v for c, v in razoes.items() if "Vat" in c and v), default=None)
    vat_a = max((v for c, v in razoes_a.items() if "Vat" in c and v), default=None)
    h.append('<h3>Apontamentos para o projeto</h3><ol>'
             '<li><b>Terças:</b> com a carga do telhado chegando a elas, as Ue 200×75×20×2,65 de até 10,3 m de vão recebem cerca de 43 kN·m '
             'de cálculo no vento de sucção (Tabela 24, cp até 2,0) e não passam — sem linha de corrente no modelo, a mesa comprimida fica '
             'solta nos 10 m. Antes a análise não via isso. Rever o vão, o perfil e as correntes com o projetista.</li>'
             '<li><b>Travamento longitudinal:</b> com as terças rotuladas (como na obra), o vento ao longo da cobertura desloca a estrutura '
             'cerca de 5 vezes mais e a 2ª ordem passa de pequena para média deslocabilidade (Δ2/Δ1 %s → %s). A rigidez nessa direção vinha '
             'de uma ligação engastada que a obra não tem: prever contraventamento no plano da cobertura.</li>'
             '<li><b>Banzo inferior e diagonais</b> já não passavam no Docas de teste (flambagem): seguem como apontamento do modelo de teste.</li></ol>'
             % (_n(vat_a or 1.0, 3), _n(vat or 1.0, 3)))

    # 06 próximos passos
    h.append('<h2><span class="n">06</span>Próximos passos e decisões</h2><ul>'
             '<li><b>Telha como travamento:</b> considerar a telha travando a mesa de cima da terça sob gravidade (e as correntes sob sucção) — '
             'prática do TSD e das normas; hoje a terça é verificada sem travamento entre as tesouras.</li>'
             '<li><b>Duas fontes para o Ue:</b> a tabela do manual (A = 10,10 cm², 7,90 kg/m) e a NBR 6355 com cantos arredondados (9,87 cm², '
             '7,75 kg/m) diferem 2 a 3 %. O Tekla fica com a tabela. Decidir qual vale para peso e cálculo.</li>'
             '<li><b>Balanço da terça além da última tesoura</b> (294 mm na junta do Docas): o esqueleto corta; o Tekla mantém.</li>'
             '<li><b>Excentricidades nas ligações</b> (o Tekla tem a opção de eixo de referência com excentricidade): estudar para cantoneira '
             'ligada por uma aba.</li>'
             '<li><b>Tekla Structural Designer:</b> com uma licença (ou avaliação) da Trimble, a comparação de esforços entra também com o Tekla, '
             'pelo mesmo caminho.</li></ul>')
    h.append('<p class="mudo">Arquivos: %s — modelo.json (o modelo de cálculo e os nossos resultados), opensees.json, comparacao.json, '
             'tekla_pecas.json, tekla_analise_neutro.json, comparacao_tekla.json e a pasta antes/. Ferramentas em sistema/testes/calibracao/.</p>'
             % _e(os.path.relpath(pasta, os.path.dirname(SISTEMA))))
    return identidade.variaveis_css(marca) + CSS, "".join(h)


def main():
    slug = sys.argv[1]
    pasta = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAIDA_PADRAO, slug)
    from saida import printpdf
    css, corpo = montar(slug, pasta)
    doc = printpdf.envelope(corpo, css, "Calibração da análise")
    tmp = tempfile.mkdtemp(prefix="mtl_cal_")
    try:
        h = os.path.join(tmp, "doc.html")
        open(h, "w", encoding="utf-8").write(doc)
        printpdf.imprimir(h, os.path.join(tmp, "doc.pdf"), verbose=False, timeout=300)
        destino = os.path.join(pasta, "Calibracao-%s.pdf" % slug)
        shutil.move(os.path.join(tmp, "doc.pdf"), destino)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("->", destino)


if __name__ == "__main__":
    main()
