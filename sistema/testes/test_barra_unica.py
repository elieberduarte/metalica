# -*- coding: utf-8 -*-
"""A barra única da área de trabalho (web/barra_unica.js) aciona os comandos das telas pelo data-acao /
data-vista do menu delas: cada comando do mapa tem de existir na tela do lado dele (senão o item some
do menu em silêncio)."""
import os
import re

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _ler(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


def test_cada_comando_do_mapa_existe_na_tela_do_lado():
    js = _ler("barra_unica.js")
    telas = {"2d": _ler("cad", "cad.html"), "3d": _ler("editor3d", "editor.html")}
    topo = {k: v[v.index('<header class="topo"'):v.index("</header>")] for k, v in telas.items()}
    faltam = []
    for texto, lado, acao in re.findall(r"I\('([^']+)', '(2d|3d)', '([^']+)'", js):
        if acao in ("desfazer", "refazer"):
            continue
        if 'data-acao="%s"' % acao not in topo[lado]:
            faltam.append((texto, lado, acao))
    for texto, lado, vista in re.findall(r"V\('([^']+)', '(2d|3d)', '([^']+)'", js):
        if 'data-vista="%s"' % vista not in topo[lado]:
            faltam.append((texto, lado, "vista " + vista))
    assert not faltam, faltam
    # as setas de desfazer / refazer usam o Editar das duas telas
    for lado in ("2d", "3d"):
        assert 'data-acao="desfazer"' in topo[lado] and 'data-acao="refazer"' in topo[lado]


# Os comandos dos menus até a 0.8.53. Na UI1 (30/09/2026) os menus foram reorganizados na ordem da obra —
# Arquivo, Modelo, Cálculo, Desenho, Produção, Ver, ? — e nenhum comando pode sumir: cada um tem de continuar
# acionável por um item do mapa novo (o Salvar e o Zoom viraram um item só para os dois lados).
ANTIGOS = [
    ('', 'fn:modo-elevacao'), ('', 'fn:modo-planta'), ('', 'fn:seguir'), ('', 'fn:tema'), ('', 'fn:trocar'),
    ('', 'link:/ajuda'), ('', 'link:/ligacoes'), ('2d', 'acao:abrir'), ('2d', 'acao:abrir-pasta'),
    ('2d', 'acao:ajustar-tamanho'), ('2d', 'acao:aplicar-furos'), ('2d', 'acao:aplicar-pecas'),
    ('2d', 'acao:arquitetonico'), ('2d', 'acao:atualizar-desenhos'), ('2d', 'acao:calibrar'), ('2d', 'acao:corte'),
    ('2d', 'acao:estilos'), ('2d', 'acao:excluir-desenhos'), ('2d', 'acao:exportar-dxf'), ('2d', 'acao:exportar-pdf'),
    ('2d', 'acao:folhas-recebidas'), ('2d', 'acao:gerar-3d'), ('2d', 'acao:grade'), ('2d', 'acao:gravar-eixos'),
    ('2d', 'acao:importar-dxf'), ('2d', 'acao:inserir-folha'), ('2d', 'acao:malha'), ('2d', 'acao:montar-planta'),
    ('2d', 'acao:novo'), ('2d', 'acao:orto'), ('2d', 'acao:pdf-pranchas'), ('2d', 'acao:peca-catalogo'),
    ('2d', 'acao:planta-lancamento'), ('2d', 'acao:pranchas'), ('2d', 'acao:pranchas-das-folhas'),
    ('2d', 'acao:projeto-2d'), ('2d', 'acao:reconhecer'), ('2d', 'acao:salvar'), ('2d', 'acao:selecionar-peca'),
    ('2d', 'acao:ver-3d'), ('2d', 'acao:zoom-extensao'), ('2d', 'acao:zoom-selecao'), ('2d', 'vista:direita'),
    ('2d', 'vista:esquerda'), ('2d', 'vista:frente'), ('2d', 'vista:inferior'), ('2d', 'vista:topo'),
    ('2d', 'vista:tras'), ('3d', 'acao:abrir'), ('3d', 'acao:alternar-projecao'), ('3d', 'acao:cantos-redondos'),
    ('3d', 'acao:desempenho'), ('3d', 'acao:desenho-corte'), ('3d', 'acao:desenho-selecao'),
    ('3d', 'acao:detalhar-ifc'), ('3d', 'acao:detalhar-pecas'), ('3d', 'acao:dimensionar'), ('3d', 'acao:do-galpao'),
    ('3d', 'acao:eixos-obra'), ('3d', 'acao:esforcos'), ('3d', 'acao:exemplo'), ('3d', 'acao:explodir'),
    ('3d', 'acao:exportar-ifc'), ('3d', 'acao:importar-ifc'), ('3d', 'acao:inspecionar-ifc'),
    ('3d', 'acao:inverter-selecao'), ('3d', 'acao:isolar'), ('3d', 'acao:juntar'), ('3d', 'acao:lancar-estrutura'),
    ('3d', 'acao:mapa-esforcos'), ('3d', 'acao:materiais'), ('3d', 'acao:memorial-lancamento'), ('3d', 'acao:novo'),
    ('3d', 'acao:referencia'), ('3d', 'acao:restaurar-modelo'), ('3d', 'acao:resultado-analise'),
    ('3d', 'acao:salvar'), ('3d', 'acao:salvar-como'), ('3d', 'acao:sombras'), ('3d', 'acao:trelicas-lidas'),
    ('3d', 'acao:verificar-apoios'), ('3d', 'acao:zoom-extensao'), ('3d', 'acao:zoom-selecao'),
    ('3d', 'sel:#modos-exibicao [data-esqueleto]'), ('3d', 'sel:#modos-exibicao [data-modo="arestas"]'),
    ('3d', 'sel:#modos-exibicao [data-modo="raiox"]'), ('3d', 'sel:#modos-exibicao [data-modo="sombreado"]'),
    ('3d', 'sel:#modos-exibicao [data-modo="sombreado_arestas"]'), ('3d', 'vista:direita'), ('3d', 'vista:esquerda'),
    ('3d', 'vista:frente'), ('3d', 'vista:inferior'), ('3d', 'vista:isometrica'), ('3d', 'vista:topo'),
    ('3d', 'vista:tras'),
]


def _comandos_do_mapa(js):
    tem = {(l, "acao:" + a) for l, a in re.findall(r"I\('[^']+', '(2d|3d)', '([^']+)'", js)}
    tem |= {(l, "vista:" + v) for l, v in re.findall(r"V\('[^']+', '(2d|3d)', '([^']+)'", js)}
    tem |= {(l, "acao:" + a) for l, a in re.findall(r"\['(2d|3d)', '([^']+)'\]", js)}          # varios (Salvar)
    for a in re.findall(r"noAtivo: '([^']+)'", js):                                              # no lado ativo (Zoom)
        tem |= {("2d", "acao:" + a), ("3d", "acao:" + a)}
    tem |= {("", "fn:" + f) for f in re.findall(r"F\('[^']+', '([^']+)'", js)}
    tem |= {("", "link:" + u) for u in re.findall(r"link: '([^']+)'", js)}
    tem |= {(l, "sel:" + s) for l, s in re.findall(r"lado: '(2d|3d)', sel: '([^']+)'", js)}
    return tem


def test_nenhum_comando_do_menu_antigo_sumiu():
    tem = _comandos_do_mapa(_ler("barra_unica.js"))
    faltam = [c for c in ANTIGOS if c not in tem]
    assert not faltam, faltam


def test_menus_na_ordem_da_obra():
    js = _ler("barra_unica.js")
    nomes = re.findall(r"^    \{ nome: '([^']+)', itens: \[", js, re.M)
    # enxutos em 03/10/2026: o Cálculo foi para o Modelo; Desenho + detalhar/pranchas = Detalhamento; Produção e
    # Comercial viraram etapas da barra do projeto (web/etapas.js)
    assert nomes == ["Arquivo", "Modelo", "Detalhamento", "Ver", "?"], nomes
    # no 3D, os nomes que batiam com o Explodir e o Juntar do 2D
    assert "I('Dividir a peça em trechos', '3d', 'explodir'" in js and "I('Unir peças', '3d', 'juntar'" in js
    # cada item movido diz de onde veio (? › Onde foi parar)
    assert js.count("antes: ") >= 80
