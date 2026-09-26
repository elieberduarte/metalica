# -*- coding: utf-8 -*-
"""Camada didática do memorial: o que cada verificação protege, o fenômeno, o que pesa no
resultado e o erro típico — em linguagem comum, para quem está aprendendo a calcular.

Os textos são procurados pelo título da verificação (o começo dele) e pela chave da hipótese
(`Hipotese.chave`). Nada aqui calcula: são explicações fixas, escritas uma vez e conferidas
com o usuário na trilha de aprendizado (terça → tesoura → pilar → vento → ligações). Cada
entrada traz:

    protege   o que a verificação impede de acontecer
    fenomeno  como a peça falha, em palavras
    pesa      qual número manda no resultado e por quê
    erro      o engano mais comum de quem calcula
    desenho   um SVG pequeno do fenômeno (opcional)

`explicar_verificacao(titulo)` e `explicar_hipotese(chave)` devolvem o dicionário ou None —
o memorial escreve "explicação ainda não escrita" quando não há, para a lacuna ficar visível.
"""
from typing import Dict, Optional

# ---------------------------------------------------------------- desenhos (SVG pequenos)
_ESTILO = ('<style>svg.fenomeno .l{stroke:#1f5fbf;stroke-width:1.6;fill:none}svg.fenomeno .f{fill:#dbe6f7;stroke:#1f5fbf;stroke-width:1.2}'
           'svg.fenomeno .q{stroke:#a5231a;stroke-width:1.2;fill:none}svg.fenomeno .t{font:10px Arial,sans-serif;fill:#333}'
           'svg.fenomeno .d{stroke:#888;stroke-width:1;stroke-dasharray:3 2;fill:none}</style>')


def _svg(corpo: str, w: int = 300, h: int = 110) -> str:
    return (f'<svg class="fenomeno" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'xmlns="http://www.w3.org/2000/svg">{_ESTILO}{corpo}</svg>')


def _viga_biapoiada() -> str:
    setas = "".join(f'<path class="q" d="M{x} 18 v14 m-3 -4 l3 4 l3 -4"/>' for x in range(40, 261, 20))
    return _svg(
        f'{setas}<text class="t" x="140" y="12" text-anchor="middle">q (kN/m)</text>'
        '<rect class="f" x="30" y="34" width="240" height="8"/>'
        '<path class="l" d="M30 42 l-8 12 h16 z M270 42 l-8 12 h16 z"/>'
        '<path class="d" d="M30 70 Q150 118 270 70"/>'
        '<path class="l" d="M30 70 h240"/>'
        '<text class="t" x="150" y="104" text-anchor="middle">M = q·L²/8</text>'
        '<text class="t" x="18" y="66">V = q·L/2</text>')


def _flt_mesa_inferior() -> str:
    return _svg(
        '<text class="t" x="150" y="12" text-anchor="middle">sucção: o vento puxa a telha para cima</text>'
        '<path class="q" d="M60 40 v-14 m-3 4 l3 -4 l3 4 M120 40 v-14 m-3 4 l3 -4 l3 4 M180 40 v-14 m-3 4 l3 -4 l3 4 M240 40 v-14 m-3 4 l3 -4 l3 4"/>'
        '<rect class="f" x="30" y="40" width="240" height="6"/>'
        '<text class="t" x="276" y="46">telha + mesa sup.</text>'
        '<path class="l" d="M30 46 v30 h240 v-30"/>'
        '<path class="d" d="M30 76 C 90 96, 210 56, 270 76"/>'
        '<text class="t" x="150" y="100" text-anchor="middle">mesa inferior comprimida foge de lado entre as correntes (L_b)</text>')


def _flambagem_local() -> str:
    return _svg(
        '<path class="l" d="M60 20 h180"/>'
        '<path class="l" d="M60 20 c 15 -8, 15 8, 30 0 s 15 8, 30 0 s 15 8, 30 0 s 15 8, 30 0 s 15 8, 30 0 s 15 8, 30 0"/>'
        '<path class="l" d="M60 20 v70 M240 20 v70"/>'
        '<text class="t" x="150" y="50" text-anchor="middle">a chapa fina da mesa comprimida ondula</text>'
        '<text class="t" x="150" y="64" text-anchor="middle">antes de o aço escoar: b/t alto → M_ℓ baixo</text>'
        '<text class="t" x="150" y="100" text-anchor="middle">λ_ℓ = √(M_Re/M_ℓ)</text>')


def _flecha() -> str:
    return _svg(
        '<rect class="f" x="30" y="30" width="240" height="6"/>'
        '<path class="l" d="M30 36 l-8 12 h16 z M270 36 l-8 12 h16 z"/>'
        '<path class="d" d="M30 60 Q150 100 270 60"/>'
        '<path class="q" d="M150 60 v20 m-3 -4 l3 4 l3 -4"/>'
        '<text class="t" x="160" y="74">δ</text>'
        '<text class="t" x="150" y="104" text-anchor="middle">δ = 5·q·L⁴/(384·E·I) ≤ L/180</text>')


def _esmagamento() -> str:
    return _svg(
        '<path class="l" d="M120 20 v50 M180 20 v50"/>'
        '<path class="l" d="M110 20 h80"/>'
        '<path class="l" d="M118 70 c -6 8, -6 14, 2 16 h60 c 8 -2, 8 -8, 2 -16"/>'
        '<rect class="f" x="100" y="86" width="100" height="8"/>'
        '<path class="q" d="M150 20 v-12 m-3 4 l3 -4 l3 4"/>'
        '<text class="t" x="150" y="108" text-anchor="middle">a alma fina amassa sobre a chapa de apoio (N curto)</text>')


def _cortante() -> str:
    return _svg(
        '<rect class="f" x="60" y="30" width="180" height="50"/>'
        '<path class="q" d="M60 30 l180 50 M60 80 l180 -50"/>'
        '<path class="l" d="M50 30 v50 m-3 -4 l3 4 l3 -4 M250 80 v-50 m-3 4 l3 -4 l3 4"/>'
        '<text class="t" x="150" y="100" text-anchor="middle">a alma resiste ao cortante; se for esbelta, flamba em diagonal</text>')


def _tributaria() -> str:
    return _svg(
        '<path class="l" d="M20 90 L150 20 L280 90"/>'
        '<circle class="f" cx="85" cy="55" r="4"/><circle class="f" cx="150" cy="20" r="4"/><circle class="f" cx="215" cy="55" r="4"/>'
        '<path class="q" d="M117 38 L183 38"/>'
        '<path class="d" d="M117 38 v-20 M183 38 v-20"/>'
        '<text class="t" x="150" y="12" text-anchor="middle">largura tributária da terça da cumeeira</text>'
        '<text class="t" x="150" y="104" text-anchor="middle">metade do caminho até cada vizinha: é o que cai nesta terça</text>')


# ---------------------------------------------------------------- explicações
#: Por começo do título da verificação (o mais específico primeiro).
VERIFICACOES: Dict[str, dict] = {
    "Flexão Mx — combinação gravitacional": {
        "protege": "Que a terça dobre demais para baixo com o peso da telha e da sobrecarga e escoe ou "
                   "flambe a mesa de cima.",
        "fenomeno": "A carga de cima para baixo comprime a mesa superior. Como a telha está parafusada nela, "
                    "a mesa não consegue fugir de lado: a única forma de a peça falhar é a chapa fina "
                    "ondular (flambagem local) ou o aço escoar. Por isso este caso raramente governa numa "
                    "terça de galpão leve.",
        "pesa": "W<sub>x</sub> (o quanto a seção resiste a dobrar) e a esbeltez da mesa b/t, que decide se a "
                "flambagem local corta a resistência antes do escoamento.",
        "erro": "Verificar só este caso e esquecer a sucção, que na maioria dos galpões leves é o que "
                "governa a terça.",
        "desenho": _viga_biapoiada(),
    },
    "Flexão Mx — combinação de sucção": {
        "protege": "Que o vento, ao puxar a telha para cima, faça a mesa inferior da terça (agora "
                   "comprimida e sem nada que a segure) fugir de lado e a peça tombar.",
        "fenomeno": "Na sucção a terça dobra para cima: a mesa de baixo passa a ser a comprimida. A telha "
                    "está na mesa de cima e não ajuda. Só as correntes seguram a mesa de baixo, e só nos "
                    "pontos onde encostam; entre duas correntes a mesa pode flambar lateralmente com torção "
                    "(FLT). Quanto maior o trecho livre L<sub>b</sub>, menor o momento que a peça aguenta.",
        "pesa": "L<sub>b</sub> = vão/(correntes + 1): dobrar o número de linhas de correntes reduz L<sub>b</sub> e "
                "sobe a resistência mais do que trocar por um perfil mais pesado. Depois vem a esbeltez da "
                "mesa (flambagem local) e a própria sucção do vento, que depende de V<sub>0</sub> e da "
                "pressão interna.",
        "erro": "Contar as correntes como se travassem também o giro da seção (elas só seguram o "
                "deslocamento lateral), ou usar o peso próprio majorado contra o vento — o peso ajuda, "
                "então entra com 1,0.",
        "desenho": _flt_mesa_inferior(),
    },
    "Flexão My": {
        "protege": "Que a parcela da carga que corre paralela ao telhado dobre a terça no eixo fraco.",
        "fenomeno": "Num telhado inclinado a carga vertical se divide: uma parte empurra a terça "
                    "perpendicular ao telhado (é o M<sub>x</sub>) e outra a empurra ao longo da água, para "
                    "baixo, no eixo fraco do U. As correntes é que seguram essa parcela, por isso o vão dessa "
                    "flexão é o espaçamento entre correntes.",
        "pesa": "A inclinação (sen θ) e o espaçamento das correntes ao quadrado.",
        "erro": "Esquecer essa parcela em telhados de 15° ou mais, ou usar o vão inteiro em vez do "
                "espaçamento das correntes.",
        "desenho": None,
    },
    "Flexão oblíqua": {
        "protege": "Que as duas flexões juntas (M<sub>x</sub> e M<sub>y</sub>) esgotem a seção mesmo que cada "
                   "uma sozinha passe.",
        "fenomeno": "Cada verificação usa uma parte da capacidade da seção; a equação de interação soma as "
                    "duas frações. Se a soma passa de 1, a fibra mais solicitada escoa.",
        "pesa": "A parcela maior — quase sempre M<sub>x</sub>/M<sub>x,Rd</sub>.",
        "erro": "Verificar as duas flexões separadas e dar como aprovada uma peça com 0,7 + 0,4.",
        "desenho": None,
    },
    "Força cortante": {
        "protege": "Que a alma da terça rasgue ou flambe em diagonal perto dos apoios, onde o cortante é máximo.",
        "fenomeno": "O cortante é resistido pela alma. Numa chapa de 2 mm a alma pode flambar em diagonal "
                    "(campo de tração) antes de o aço escoar; a norma dá três fórmulas e vale a menor.",
        "pesa": "A esbeltez da alma h/t e a espessura ao quadrado ou ao cubo nas parcelas de flambagem.",
        "erro": "Nenhum grave em terça: o cortante costuma ficar abaixo de 10 %. Vira problema em vigas "
                "curtas e carregadas.",
        "desenho": _cortante(),
    },
    "Esmagamento da alma": {
        "protege": "Que a alma fina amasse (enrugue) sobre a chapa de apoio, onde toda a reação entra numa "
                   "faixa curta.",
        "fenomeno": "A reação do apoio entra pela mesa e desce pela alma numa largura pequena; a chapa de "
                    "2 mm dobra ali como uma lata pisada. Nenhuma verificação de flexão avisa isso.",
        "pesa": "O comprimento de apoio N (quanto maior a chapa, melhor) e t². Aqui o programa adota "
                "N = 10 cm porque o IFC não diz: se a chapa de terça da fábrica for mais curta, esta "
                "verificação muda.",
        "erro": "Apoiar a terça numa cantoneira ou tira estreita sem conferir; e ignorar que o furo do "
                "parafuso perto do apoio reduz ainda mais a alma.",
        "desenho": _esmagamento(),
    },
    "Interação momento–cortante": {
        "protege": "Que momento e cortante, atuando no mesmo ponto da alma, somem seus efeitos.",
        "fenomeno": "No apoio há só cortante; no meio do vão só momento. A um quarto do vão há os dois: a "
                    "norma exige a verificação combinada ali.",
        "pesa": "M<sub>Sd</sub>/M<sub>Rd</sub>, porque o cortante é pequeno na terça.",
        "erro": "Verificar no apoio (M = 0) e achar que passou.",
        "desenho": None,
    },
    "Flecha — gravidade": {
        "protege": "Que a terça, mesmo sem quebrar, vergue tanto que a telha empoce água, os parafusos "
                   "folguem ou o telhado fique visivelmente ondulado.",
        "fenomeno": "É um estado-limite de serviço: usa a carga sem majorar e o limite é uma fração do vão "
                    "(L/180 para terça). Depende da rigidez E·I, não da resistência.",
        "pesa": "O vão à quarta potência e I<sub>x</sub>: aumentar a altura do perfil rende mais do que "
                "engrossar a chapa.",
        "erro": "Usar a carga de cálculo (majorada) na flecha, ou esquecer o limite do fabricante da "
                "telha, que pode ser mais rigoroso que o da norma.",
        "desenho": _flecha(),
    },
    "Flecha — sucção": {
        "protege": "Que a terça levante demais com o vento e arranque a fixação da telha.",
        "fenomeno": "Mesmo raciocínio da flecha de gravidade, para cima, com a carga de vento de serviço "
                    "e o limite mais folgado L/120.",
        "pesa": "A sucção de serviço e I<sub>x</sub>.",
        "erro": "Nenhum grave: costuma passar quando a flexão de sucção passa.",
        "desenho": None,
    },
}

#: Por chave da hipótese.
HIPOTESES: Dict[str, dict] = {
    "vao": {
        "protege": "É o dado que mais pesa: o momento cresce com o quadrado do vão e a flecha com a "
                   "quarta potência.",
        "fenomeno": "O vão é a distância entre dois apoios consecutivos da terça, ou seja, entre duas "
                    "tesouras. O programa mede no modelo 3D onde o eixo da terça cruza o plano de cada "
                    "tesoura.",
        "pesa": "Se a posição tem vãos diferentes, o maior governa.",
        "erro": "Usar o comprimento da peça (que passa das tesouras no beiral) como vão.",
        "desenho": None,
    },
    "largura": {
        "protege": "Define quanta carga por m² vira carga por metro na terça.",
        "fenomeno": "Cada terça carrega a faixa de telhado até a metade do caminho da vizinha, de cada "
                    "lado. A do beiral carrega só metade de um lado mais o balanço da telha.",
        "pesa": "Multiplica todas as cargas de área (telha, sobrecarga e vento).",
        "erro": "Usar o espaçamento das terças em projeção horizontal para o vento (que age no "
                "telhado inclinado) ou vice-versa.",
        "desenho": _tributaria(),
    },
    "inclinacao": {
        "protege": "Divide a carga vertical em parcela normal e paralela ao telhado e define os "
                   "coeficientes de vento.",
        "fenomeno": "Quanto mais inclinado o telhado, menor a parcela que dobra a terça no eixo forte e "
                    "maior a que escorrega ao longo da água.",
        "pesa": "Pouco abaixo de 10°; muito acima de 20°.",
        "erro": "Uma inclinação média poluída por uma tesoura fora do padrão (oitão, meia-tesoura) — "
                "confira se o valor é o do telhado.",
        "desenho": None,
    },
    "cargas_area": {
        "protege": "São as ações permanentes e de uso: o que a estrutura carrega todos os dias.",
        "fenomeno": "Telha, forro, instalações e o próprio perfil são o peso próprio; a sobrecarga de "
                    "0,25 kN/m² representa gente na cobertura na montagem e manutenção, e água ou poeira "
                    "acumulada.",
        "pesa": "Em galpão leve o peso próprio é pequeno (isso é bom contra a gravidade e ruim contra o "
                "vento, que não tem o que segurar).",
        "erro": "Esquecer o forro ou os dutos pendurados na terça; ou contar a sobrecarga em área "
                "inclinada em vez de projeção horizontal.",
        "desenho": None,
    },
    "vento": {
        "protege": "É a ação que governa terça, tesoura e contraventamento de galpão leve.",
        "fenomeno": "O vento passa por cima do telhado e o suga (como a asa de um avião); a pressão "
                    "interna (aberturas) pode somar. A NBR 6123 dá a velocidade básica V<sub>0</sub> do "
                    "mapa, corrige por terreno, altura e uso (S<sub>1</sub>, S<sub>2</sub>, S<sub>3</sub>) e "
                    "aplica coeficientes de pressão por face do telhado.",
        "pesa": "V<sub>0</sub> ao quadrado (40 → 45 m/s é +27 % de pressão); a categoria de rugosidade "
                "(S<sub>2</sub>) e o coeficiente de pressão interna.",
        "erro": "Usar a sucção média em vez da mais severa entre os casos; esquecer a pressão interna "
                "com portão aberto; ou tratar o vento como carga vertical (ele é perpendicular ao telhado).",
        "desenho": None,
    },
    "combinacoes": {
        "protege": "Os coeficientes de majoração cobrem a incerteza das cargas; combinar é decidir o que "
                   "age junto.",
        "fenomeno": "Ninguém carrega a cobertura com gente no dia da ventania: por isso a ação secundária "
                    "entra reduzida (ψ<sub>0</sub>). Na sucção o peso próprio é favorável e entra com 1,0 — "
                    "majorá-lo seria fingir que a terça pesa mais do que pesa.",
        "pesa": "Em galpão leve, a combinação de sucção (1,4·V − 1,0·PP).",
        "erro": "Majorar o peso próprio na sucção (dá uma terça contra a segurança) ou somar sobrecarga "
                "com sucção (não age junto).",
        "desenho": None,
    },
    "correntes": {
        "protege": "As correntes decidem o comprimento destravado L<sub>b</sub> na sucção e o vão da flexão "
                   "no eixo fraco.",
        "fenomeno": "São as barras que ligam uma terça à outra no meio do vão. O programa as conta no "
                    "modelo: barras curtas encostadas no eixo da terça entre duas tesouras.",
        "pesa": "Cada linha a mais reduz L<sub>b</sub> e a resistência à sucção sobe; é a correção mais "
                "barata para uma terça que reprova.",
        "erro": "Contar corrente que não chega até a tesoura ou até a cumeeira (uma corrente solta não "
                "trava nada: a linha precisa fechar num ponto fixo).",
        "desenho": None,
    },
    "flecha_limite": {
        "protege": "Limites de serviço da NBR 14762 (Anexo C).",
        "fenomeno": "L/180 na gravidade e L/120 na sucção são os mínimos; o fabricante da telha pode "
                    "exigir menos flecha.",
        "pesa": "Pouco em terça curta; governa em vãos de 7 m ou mais.",
        "erro": "Confundir com o limite da tesoura (L/250).",
        "desenho": None,
    },
    "modelo_estatico": {
        "protege": "Define como a carga vira esforço.",
        "fenomeno": "Viga biapoiada é o modelo mais simples e o mais seguro para o momento no vão: a terça "
                    "apoia nas duas tesouras e nada a segura no meio (as correntes seguram de lado, não "
                    "para cima). Se a terça for contínua sobre a tesoura, o momento no vão cai, mas "
                    "aparece momento negativo sobre o apoio.",
        "pesa": "q·L²/8: o vão ao quadrado.",
        "erro": "Aproveitar a continuidade sem verificar o momento negativo e o apoio.",
        "desenho": _viga_biapoiada(),
    },
    "secao": {
        "protege": "As propriedades geométricas da seção são a metade da conta.",
        "fenomeno": "I<sub>x</sub> e W<sub>x</sub> dizem o quanto a seção resiste a dobrar; b/t e h/t dizem "
                    "se a chapa fina flamba antes de escoar. O programa calcula tudo pela linha média da "
                    "chapa, com o raio de dobra.",
        "pesa": "A altura h ao quadrado no W<sub>x</sub> e ao cubo no I<sub>x</sub>.",
        "erro": "Pegar propriedades de tabela de outro raio de dobra ou de perfil laminado.",
        "desenho": None,
    },
    "aco": {
        "protege": "f<sub>y</sub> é o teto da resistência; E é a rigidez.",
        "fenomeno": "Escoamento (f<sub>y</sub>) governa quando a chapa é grossa; flambagem (E) governa quando "
                    "é fina. Em terça de 2 mm, quase sempre a flambagem.",
        "pesa": "f<sub>y</sub> pouco (a flambagem manda), E nada (é o mesmo para todo aço).",
        "erro": "Achar que um aço mais resistente resolve uma terça que flamba.",
        "desenho": None,
    },
    "gravidade_travamento": {
        "protege": "Justifica L<sub>b</sub> = 0 na gravidade.",
        "fenomeno": "A telha parafusada na mesa superior a segura de lado continuamente; sem isso a terça "
                    "teria FLT também na gravidade.",
        "pesa": "Só vale com telha fixada por parafuso na terça; telha simplesmente apoiada ou fixação "
                "oculta pode não travar.",
        "erro": "Assumir o travamento com fixação que desliza.",
        "desenho": None,
    },
    "succao_travamento": {
        "protege": "É a hipótese que mais muda o resultado da terça.",
        "fenomeno": "Na sucção a mesa comprimida é a de baixo, sem telha; só as correntes a seguram. "
                    "Entre correntes ela pode fugir de lado e torcer.",
        "pesa": "L<sub>b</sub> ao quadrado no M<sub>e</sub>; e L<sub>t</sub> (torção) igual ao vão inteiro "
                "porque as correntes não impedem o giro.",
        "erro": "Contar L<sub>t</sub> = L<sub>b</sub> sem mão-francesa ou travamento de mesa a mesa.",
        "desenho": _flt_mesa_inferior(),
    },
    "cb": {
        "protege": "C<sub>b</sub> corrige o momento crítico pela forma do diagrama.",
        "fenomeno": "Momento uniforme no trecho é o pior caso (C<sub>b</sub> = 1); momento variando ao "
                    "longo do trecho é menos severo (C<sub>b</sub> > 1).",
        "pesa": "Pouco na terça com poucas correntes (o trecho central tem momento quase uniforme).",
        "erro": "Usar C<sub>b</sub> > 1 no trecho central sem calcular.",
        "desenho": None,
    },
    "flexao_y": {
        "protege": "A parcela paralela ao telhado.",
        "fenomeno": "Ver a verificação Flexão M<sub>y</sub>.",
        "pesa": "sen θ e o espaçamento das correntes.",
        "erro": "Esquecer em telhados inclinados.",
        "desenho": None,
    },
    "apoio": {
        "protege": "O comprimento de apoio N entra no esmagamento da alma.",
        "fenomeno": "Quanto mais curta a chapa em que a terça apoia, mais concentrada a reação e mais fácil "
                    "a alma amassar.",
        "pesa": "√N: dobrar N rende cerca de 20 % a mais.",
        "erro": "Adotar 10 cm com chapa de terça de 4 cm.",
        "desenho": _esmagamento(),
    },
    "interacao_mv": {
        "protege": "Onde M e V coexistem.",
        "fenomeno": "Ver a verificação de interação.",
        "pesa": "M<sub>Sd</sub>/M<sub>Rd</sub>.",
        "erro": "Verificar no apoio.",
        "desenho": None,
    },
    "servico": {
        "protege": "Cargas sem majoração para as flechas.",
        "fenomeno": "Flecha é aparência e funcionamento, não ruína: usa-se a carga que de fato atua.",
        "pesa": "A carga de serviço e I<sub>x</sub>.",
        "erro": "Usar carga majorada.",
        "desenho": None,
    },
}


def explicar_verificacao(titulo: str) -> Optional[dict]:
    """A explicação da verificação com esse título (busca pelo começo, o mais longo primeiro)."""
    t = (titulo or "").strip()
    for chave in sorted(VERIFICACOES, key=len, reverse=True):
        if t.startswith(chave):
            return VERIFICACOES[chave]
    return None


def explicar_hipotese(chave: str) -> Optional[dict]:
    return HIPOTESES.get(chave)


def explicar_passo(texto: str) -> Optional[str]:
    """Uma linha sobre um passo da conta (pelo começo do texto do passo)."""
    t = (texto or "").strip()
    for chave in sorted(PASSOS, key=len, reverse=True):
        if t.startswith(chave):
            return PASSOS[chave]
    return None


#: Uma frase por passo da conta, para o iniciante saber o que está lendo.
PASSOS: Dict[str, str] = {
    "Início de escoamento da seção bruta": "O momento em que a fibra mais afastada chega a f<sub>y</sub>: é o "
                                           "teto; nenhum modo de flambagem passa dele.",
    "Flambagem lateral com torção": "A mesa comprimida foge de lado e a seção gira: M<sub>e</sub> é o momento "
                                    "crítico elástico; λ<sub>0</sub> compara o teto com ele. λ<sub>0</sub> ≤ 0,6 "
                                    "não perde nada; acima disso a resistência cai pela curva do item 9.8.2.2.",
    "Flambagem local": "A chapa fina ondula antes de escoar: M<sub>ℓ</sub> é o momento em que isso começa; "
                       "λ<sub>ℓ</sub> ≤ 0,776 não perde nada.",
    "Flambagem distorcional": "A mesa com enrijecedor gira em torno da alma. Só existe em Ue; no U simples "
                              "M<sub>dist</sub> = ∞ e o modo não corta nada.",
    "Momento resistente de cálculo": "O menor dos três modos dividido por γ = 1,10 — a margem da norma.",
    "Escoamento da fibra extrema": "No eixo fraco não há FLT; a resistência é W<sub>y</sub>·f<sub>y</sub>/γ.",
    "Equação de interação": "Soma das frações da capacidade usadas por cada esforço; tem de dar ≤ 1.",
    "Esbeltez da alma": "h/t: quanto maior, mais fácil a alma flambar ao cortante.",
    "Parcelas de resistência": "Escoamento, flambagem inelástica e elástica da alma — vale a menor.",
    "Resistência de cálculo": "Valor nominal dividido por γ.",
    "Coeficientes da Tabela 22": "Coeficientes empíricos do esmagamento da alma, conforme a posição do "
                                 "apoio e se a mesa está fixada.",
    "Resistência nominal": "A fórmula empírica do item 9.9, ajustada em ensaios.",
    "Flecha no meio do vão": "Fórmula clássica da viga biapoiada com carga uniforme.",
    "Limite": "Fração do vão que a norma (ou o fabricante da telha) aceita.",
    "Carga permanente por metro": "Peso por m² vezes a faixa que a terça carrega, mais o peso dela.",
    "Sobrecarga por metro": "A sobrecarga é dada em projeção horizontal; cos θ leva para o telhado inclinado.",
    "Vento por metro": "Pressão (ou sucção) do telhado vezes a largura tributária; o vento já age "
                       "perpendicular ao telhado.",
    "Carga de cálculo, gravidade": "Combinação última com os coeficientes da NBR 8681; a maior das duas.",
    "Carga de cálculo, sucção": "O vento majorado menos o peso próprio sem majorar (ele ajuda).",
    "Cargas de serviço": "Sem majoração: são as que atuam de verdade, para as flechas.",
    "Momento máximo, gravidade": "q·L²/8 da viga biapoiada, com a parcela da carga normal ao telhado.",
    "Momento no plano do telhado": "A parcela paralela dobra o eixo fraco entre correntes.",
    "Momento máximo, sucção": "q·L²/8 com a carga de sucção; dobra a terça para cima.",
    "Reação no apoio": "q·L/2: metade da carga do vão vai para cada tesoura.",
    "Comprimentos destravados": "L<sub>b</sub> entre correntes; L<sub>t</sub> o vão inteiro (as correntes "
                                "não travam o giro).",
}
