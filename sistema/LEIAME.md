# Sistema de dimensionamento e detalhamento de galpões metálicos

Dimensiona um galpão industrial de duas águas do início ao fim, conforme as normas
brasileiras, e entrega memorial de cálculo, desenhos de CAD, pranchas de impressão e
lista de material. Traz também um editor 3D no navegador, com as ferramentas principais
de um modelador como o SketchUp, e troca de modelos em IFC nos dois sentidos.

## Como usar

```bash
cd sistema
python app.py
```

O navegador abre em `http://localhost:8765` no **gerenciador de projetos**. Ali você cria um
projeto de galpão (que abre o dimensionamento) ou um projeto a partir de um IFC (que abre o
editor 3D), e volta a qualquer projeto pela lista. Cada projeto é uma pasta em
`Documentos\Metálica` (no programa instalado) ou em `sistema/projetos` (no desenvolvimento):

```
<pasta de dados>/galpao-do-joao/
├── projeto.json     identificação, tipo, datas e os dados do dimensionamento
├── modelo.json      documento do editor 3D
├── origem/          o IFC importado, como veio
├── memorial/  desenhos/  pranchas/  lista/   entregas do dimensionamento
├── detalhamento/    DXF de produção, romaneio e relatório
└── ifc/             IFC exportado pelo editor
```

Tudo é arquivo comum (JSON, PDF, DXF, CSV, IFC): copiar a pasta é o backup. O formulário
do dimensionamento e o modelo 3D são gravados sozinhos a cada mudança. `projeto.json`
guarda a entrada do cálculo, não o resultado: o cálculo é refeito ao abrir, e o memorial
diz de qual versão do programa saiu. Excluir move a pasta para `.lixeira`.

Telas: `/` gerenciador, `/dimensionar?projeto=<pasta>` dimensionamento,
`/editor?projeto=<pasta>` editor 3D. Sem `?projeto=`, o dimensionamento funciona como
rascunho guardado no navegador, e o botão Salvar cria o projeto.

**Modo de desenvolvimento** (`python dev.py`, ou o atalho "Metálica (desenvolvimento)" na área de trabalho):
o programa roda do código, na porta 8766, com os mesmos projetos do instalado (Documentos\Metálica), uma faixa
laranja no alto das telas e "[DEV]" no título, sem oferecer atualização. Mudou um `.py`, o vigia reinicia o servidor
sozinho e a janela aberta volta a responder em segundos; mudou js/html/css, o rótulo da versão pede F5. É onde as
rodadas de correção acontecem; a versão oficial (conferência completa, instalador, GitHub) sai no fim de cada leva.
Não abra o mesmo projeto no instalado e no desenvolvimento ao mesmo tempo: um grava por cima do outro.

Opções: `--porta 9000` muda a porta, `--sem-navegador` não abre o navegador sozinho,
`--dados pasta` muda a pasta de dados.

## O que o sistema faz

Percorre o mesmo caminho de um projetista:

1. **Cargas permanentes** da cobertura, parcela a parcela (NBR 6120).
2. **Vento** pela NBR 6123: V₀, S₁, S₂, S₃, pressão dinâmica, coeficientes de pressão
   externa por face e os dois coeficientes internos.
3. **Terças e longarinas** pela NBR 14762. A terça sob gravidade e sob sucção do
   telhado; a longarina sob pressão e sucção da parede. Em cada caso o sistema escolhe
   o perfil Ue mais leve que atende e ajusta as linhas de correntes.
4. **Pórtico** analisado pelo método da rigidez, com mísulas e base rotulada ou
   engastada — de **alma cheia** (viga e pilar de perfil I) ou **treliçado** (tesoura
   sobre pilares; ver "Tesouras treliçadas").
5. **Combinações** últimas e de serviço (NBR 8681), inclusive com a permanente favorável
   quando a sucção alivia, que é o caso que costuma governar em galpão leve.
6. **Viga e pilar** pela NBR 8800, num laço que refaz a análise a cada troca de perfil,
   porque a distribuição de momentos depende da rigidez relativa entre os dois. No
   pórtico treliçado o laço dimensiona as quatro famílias da tesoura e os pilares juntos.
7. **Contraventamentos** por tirante redondo com esticador. O X de cobertura de cada vão
   extremo é tratado como treliça horizontal que vence o vão do galpão, com cortante de
   apoio igual a metade da força do vento no oitão. Quando o tirante não cabe, o sistema
   aumenta o número de painéis ao longo do vão, o que encurta a diagonal.
8. **Ligações** de joelho e cumeeira por chapa de topo, e **base** do pilar com placa,
   chumbadores e chave de cisalhamento.
9. **Lista de material**, pesos, área de pintura e estimativa de custo.

Cada verificação guarda a memória de cálculo passo a passo, com a fórmula, a mesma
fórmula com os números substituídos e o item da norma. É dessa memória que o memorial
é montado, de modo que o documento nunca diverge do que foi calculado.

Os desenhos, a lista de material e o modelo 3D leem do cálculo os perfis, a altura da
mísula, os vãos contraventados e o número de painéis. Assim, o que se desenha é o que se
calculou e o que se compra.

## Tesouras treliçadas

`nucleo/tesouras.py` monta a malha, o modelo de análise e a escolha do perfil; o
`nucleo/galpao.py` carrega, combina e imprime, no mesmo caminho do pórtico de alma cheia.

**Formatos**: `trapezoidal` (banzo inferior horizontal, altura crescendo do apoio à
cumeeira — o usual), `banzos paralelos` (os dois banzos acompanham a inclinação, altura
constante, todas as diagonais iguais) e `triangular` (altura nula no apoio; só fecha com
telhado inclinado, e o programa recusa quando a inclinação não dá altura ao vão).

**Diagonais**: `Howe` (montantes verticais, diagonais caindo para o apoio), `Pratt` (o
contrário: diagonais tracionadas sob gravidade, que é o arranjo mais leve) e `Warren`
(sem montantes, nós do banzo inferior no meio do painel).

**Ligação no pilar**: `apoiada` — a tesoura se apoia no topo do pilar e não transmite
momento, e então a base tem de ser engastada, senão o pórtico é um mecanismo no plano
transversal (o programa recusa); `rígida` — o pilar sobe até o banzo superior e recebe os
dois banzos, formando o joelho do pórtico treliçado, e aí a base pode ser rotulada.

O que o modelo de análise faz, e por quê:

* **banzos contínuos** (elementos de pórtico): a terça carrega o banzo superior *entre*
  os nós, e ignorar essa flexão local subestima justamente a barra mais solicitada;
* **diagonais e montantes rotulados** nas duas pontas, como a chapa de nó de fato liga;
* no joelho rígido os **banzos chegam rotulados ao pilar**: o momento do joelho é o
  binário entre os dois banzos, não flexão de banzo;
* a **altura do perfil do banzo** é limitada a um oitavo do painel. Banzo mais alto
  deixa de trabalhar por força normal e puxa para si o momento da continuidade — o nó
  rotulado que a treliça pressupõe deixa de existir e o dimensionamento entra em
  círculo, cada perfil mais pesado atraindo mais momento.

**Travamento do banzo inferior**: sob gravidade ele traciona, mas **sob sucção ele
comprime** — é o caso que governa o galpão leve. Fora do plano quem o segura são os
tirantes que ligam o banzo de uma tesoura à vizinha, e o passo desse travamento é parte
do dimensionamento: fecha-se a malha (sempre num múltiplo inteiro de painel, porque o
travamento tem de cair num nó) até o banzo passar, antes de engrossar o perfil. Os
tirantes saem na lista com a marca `TV`, dimensionados a 2 % da compressão do banzo
(NBR 8800, item 4.11).

**Pé-direito e beiral**: na tesoura o pé-direito é o nível do **banzo inferior** — a
altura livre sob a tesoura. A parede ainda sobe a altura da tesoura até o beiral, e é
essa altura que o vento vê e que as longarinas acompanham.

Sai tudo o que sai do pórtico de alma cheia: elevação do pórtico com a tesoura barra por
barra (`saida/desenhos.portico_trelicado`), modelo 3D com uma peça por barra e as marcas
do romaneio (BS, BI, D1…Dn, M1…Mn), memorial, lista de material e mapa de esforços por
família. Ligações verificadas: **chapa de nó** (gusset da diagonal mais solicitada, pela
seção de Whitmore, bloco de cisalhamento e parafusos) e **tesoura–pilar** (cortante do
pórtico e a tração de arrancamento sob sucção). Testes: `testes/test_tesouras.py`.

## Perfil por elemento

Na etapa **Materiais → Perfis por elemento** o projetista escolhe o perfil de cada
elemento (terça, longarina, viga, pilar, banzos, diagonais e montantes) entre os do catálogo
— vazio continua sendo "o mais leve que passa". O perfil forçado é verificado exatamente
como qualquer outro (`DadosGalpao.perfil_forcado`, `tesouras.menor_perfil(forcado=…)`,
`nbr14762.dimensionar_terca(perfis=[…])`): reprovado, ele fica no resultado com a razão e
um aviso, em vez de ser trocado às escondidas. Família errada (um Ue na viga) é recusada
na validação. **Banzos com perfil duplo** e **diagonais e montantes com perfil duplo**
(`banzos_duplos`, `diagonais_duplas`) entram na análise com o dobro da área e da inércia,
na verificação com `n = 2` (os esforços se dividem pelas duas peças) e na lista de
material com o dobro das peças.

Cada elemento dos resultados traz **os perfis do catálogo verificados nos esforços dele**
(`ElementoDimensionado.alternativas`, com razão, kg/m e situação): os que passam
primeiro, do mais leve ao mais pesado, depois os que não passam, do que chegou mais perto
(`tesouras.candidatos_verificados`, `galpao._alternativas_W`, `_alternativas_de_opcoes`).
Na tela, **Usar** grava o perfil no formulário e redimensiona o galpão inteiro — é como se
troca a altura da terça ou do banzo sem sair do que a norma aceita.

## Telhas: multi-dobra e paginação

**Multi-dobra** (`nucleo2d/detalhe/telhas.py`): o TecnoMETAL modela a telha que dobra do
telhado para a parede como uma fileira de peças do mesmo conjunto — a reta da cobertura,
facetas curtas (110 mm) girando alguns graus cada uma e a reta da parede. `multidobras`
reconhece essas fileiras por instância do conjunto (largura comum às peças, cadeia
contínua, ≥ 3 facetas, retas bem mais longas que as facetas), mede no plano do perfil as
duas retas entre os pontos de tangência, o raio (arco das facetas / ângulo), o ângulo e o
desenvolvido **externo** e **interno** (raio ± meia altura da onda), e as posições que a
multi-dobra consome deixam de sair como telhas recortadas. A célula (`desenho_da_multidobra`)
traz o perfil duas vezes, medidas externas e internas, como a fábrica pede; a lista de
materiais conta a multi-dobra pelo desenvolvido externo.

**Paginação** (`faces_de_telhas`, `desenho_da_paginacao`): no padrão do "comprimentos
reais" da fábrica, cada face (água da cobertura, fachada) sai com as chapas lado a lado na
posição de montagem, a marca embaixo e a cota do comprimento real dentro da chapa. A
direção da onda vem das normais das faces da malha (a direção que nenhuma face aponta), não
do maior eixo — numa telha curta o maior eixo é a largura.

**Cobrimento da multi-dobra** (regra da fábrica, `COBRIMENTO_TERCA`): a reta da cobertura
termina 150 mm depois da primeira terça (achada entre as barras paralelas à largura da telha,
logo abaixo da reta); a telha seguinte começa 150 mm antes da terça — transpasse de 300 mm +
a largura do perfil. O que sobra da reta do modelo vira a telha **complementar** (`-C`), na
célula, na paginação e na lista de materiais. Largura da telha: **1050 total** (com os
transpasses) e **980 útil**.

**Saia** (`telhas.SAIA_TELHA`, regra da fábrica): a telha de fachada e a reta da parede da
multi-dobra descem 150 mm abaixo da última longarina (`saias_de_fachada`, `aplicar_saias`: a
posição ganha `saia`, que entra na compra, na célula, na lista e na paginação). Na paginação
cada telha sai **inteira** (retângulo até o ponto mais alto) e o corte do modelo — a empena
inclinada, a curva do canto — fica tracejado: é feito na obra, medido depois de instalada.

**0.8.58.** (versão da noite, 07/10/2026) IFC: a barra usa a posição própria do perfil (vigas do Revit deitadas no Bella Casa, 05/10); Perfil do Revit também em "Tipo:Id" e sem o comprimento no fim (deck do Bella Casa, 05/10); IFC: o deck de madeira vai para a camada Deck (Bella Casa, 05/10); Celular, rodada 1: 3D leve (.mcel), pacote do projeto e protótipo das telas (só no desenvolvimento); Celular, rodada 2: servidor do celular com pareamento por QR, leitor de PDF e diagnóstico (só no desenvolvimento); Celular, Fase 2 adiantada: cópia para a obra (service worker), app instalável e HTTPS pronto no servidor; Celular: certificado HTTPS pelo Let's Encrypt com DNS do Cloudflare (opção a), configurado na tela do PC; Celular: girando, o 3D desenha em resolução menor e sem arestas (volta inteiro ao soltar); Modelo 3D abre no modo "ver" (leve); Modo ver: vínculo com o 2D, tema na hora, chão sob o modelo, abre na hora quando o modelo mudou; Editor: botão Ver volta ao modo ver (grava o pendente antes) com a mesma vista e a seleção; Modo ver: faixa sai quando vazia, menus integrados ao topo, lista do Pintar no escuro, piso com contraste e só de cima; Camadas: excluir camada vazia, ocultar grupo do "Colorir por" (editor e modo ver), laje do deck na camada Deck; CI: tarefa testes só à mão (falhava em todo push e gerava e-mail; Modo ver: piso do tema escuro mais claro (a cor ia escurecida até o preto pela saída linear do renderizador); Modo ver, tema escuro: fundo liso na cor do 2D e piso com a grade fina dele (1 m e 10 m), sem degradê nem esfumado; Modo ver, tema escuro: só as linhas de 10 m, e só em volta do modelo; Modo ver, tema claro: o mesmo do escuro (fundo liso e linhas de 10 m do 2D, só em volta do modelo); Editor 3D: fundo liso na cor do 2D e o piso da mesma cor com as linhas da grade do 2D (sem degradê; Modo ver: clicar fora no 2D limpa a seleção do 3D (visor e editor), anel vermelho nas peças em destaque, paleta mais clara no tema claro; Detalhamento: como nas pranchas, quadro com faixa de título, cada peça na sua caixinha (as da linha com a mesma altura) e, no completo, um quadro por família com um quadro por tipo de peça dentro; Modo ver: giro em volta do ponto da peça sob o cursor, clique marca a peça e as iguais, anel fino na peça (não no meio do grupo) e seta nas barras finas; Perfis do IFC do Revit cruzados com o catálogo e barras curvas sem "dobra" (Bella Casa, 06/10); Detalhamento: a linha da faixa do título fica só com 'faixa' (o 'quadro' é da moldura; Resumo de materiais: nome do catálogo em cima e o do IFC embaixo; Tubo fora do catálogo vai para o similar; Resumo de materiais: trocar o perfil de compra pelo parecido do catálogo, chapas pela espessura comercial, peças embaixo de cada perfil no Por grupo; Chapas: a espessura do modelo mostra a polegada equivalente (5,60mm ≈ 7/32", 11,20mm ≈ 7/16"); Resumo de materiais: cor na linha da compra diferente do projeto (similar âmbar, fora do catálogo vermelho, trocado à mão azul; Pendências do resumo da obra levam ao 3D: clique na linha abre o modelo com as peças em destaque; IFC do Revit (Passarela Mirante): arco da diretriz em 3D (vergalhão e corrimão; Catálogo: perfil do Revit com a forma depois das medidas ("250x250x10SHS", "406.4x12.5CHS") também cruza com o banco (o pilar da Passarela Mirante saía sem peso teórico); Lista de materiais: o texto da barra automática diz a regra inteira (W e HP em 12 m; Barra curva do Revit é calandrada: o importador lê o eixo (Axis) da viga — desenvolvido, raio e ângulo — e o detalhamento usa ("calandrar: R=…, comprimento desenvolvido …", sem pendência); Fora do aço: a observação do peso pela malha diz o que conferir (chapa perfurada sem os furos, barra maciça no lugar de tubo) — o gradil da Passarela é modelado barra a barra, não cheio; Eixos do desenho: traços do tracejado (PDF/DXF explodido) viram a linha, camadas Eixos/AXIS/GRID, só os eixos da planta (os das vistas não cruzam a outra direção), aviso de calibrar quando o desenho está na medida do pap…; CAD: ferramenta Escala (o SCALE do AutoCAD) — ponto base e fator, ou R: dois pontos de uma medida conhecida e a medida nova (5050, 5,05m, 505cm); Barra da área de trabalho: Modelo › Lançar na planta (Estrutura) — pilar, viga, fundação… e Gerar 3D da planta; CAD: a cópia de um elemento da estrutura ganha marca nova (P2, P3…) e o rótulo acompanha; Tela dividida: quando o 2D muda o modelo (a planta da Estrutura sincroniza o 3D), o 3D ao lado recarrega — o modo ver na hora, o editor se não houver edição pendente; Escala: o botão à vista no Modificar da faixa; Modelo vazio: o 3D leve fica 'sem modelo' (vazio) e o modo ver diz que está vazio, em vez de seguir mostrando a versão anterior; CAD: a alça do meio da linha a move inteira; Resumo de materiais: gradis, pisos de chapa perfurada e outras peças de aço que o IFC traz fora das peças entram na compra (peças, ml e m², sem o peso da malha); CAD: a malha de eixos acompanha o eixo em qualquer troca (alça da ponta ou do meio, Mover, Girar, Escala): a bolinha e o nome vão além da ponta nova, as cotas da malha com ponta no eixo vão para o cruzamento novo e o últ…; CAD: copiar um eixo da malha cria o eixo seguinte (7, 8… ou C, D…) com bolinha e nome; Modo ver: a planta no chão (arquitetônico do lançamento), os eixos com os balões e os níveis, como no editor; Modo ver: a planta no chão desconta a origem do arquivo do 3D leve (as peças são relativas ao centro do modelo) — a planta saía deslocada dos pilares; CAD: o eixo copiado entre dois eixos toma o nome da sequência (entre o 4 e o 5 é o 5) e os seguintes andam um, na linha, na bolinha e no nome; Modo ver: os eixos são os da malha desenhada na planta (os mesmos nomes e posições do 2D; Tela dividida: os níveis, a malha de eixos ou o arquitetônico mudados no 2D refazem a planta no chão do 3D ao lado (referencia-mudou), sem recarregar o modelo; CAD: o snap aceita segmentos que só existem na tela (Snap.virtuais) — a faixa da viga da Estrutura dá os cantos, o meio das bordas, interseção, perpendicular e sobre; CAD: o Esticar pergunta ao editor se o clique pegou a ponta de um elemento que se estica pela ponta (_pontaParaEsticar: a viga da Estrutura) — a ponta anda no eixo dele, em vez de a linha inteira andar de lado; Barra da área de trabalho: Modelo › Lançar na planta ganha Arrumar os nomes dos elementos e Renumerar os elementos em ordem (aparecem onde o CAD tem os comandos: o dev); CAD: o Esc no campo das medidas também encerra o comando (a cópia em série não soltava com o foco ali); CAD: o campo das medidas solta o foco depois do Enter e do Esc (o canvas não recebe foco: o teclado ficava preso no campo e o Ctrl+Z, o Del e os atalhos não chegavam ao desenho); CAD: o snap pega arcos e círculos pela curva (perpendicular, sobre e interseção exatos — as cordas de 10° ficavam 20 cm abaixo do banzo curvo) e o cruzamento da linha-guia com linhas e arcos; CAD: Aparar e Estender cortam no arco pela curva (não pelas cordas de 10°); CAD: o arco se ajusta depois de lançado — alças nas pontas (andam na mesma curva) e no meio (a flecha muda, as pontas ficam); Montagem: Enviar para quadro manda a seleção (sem seleção, pede a área com aviso na tela); Barra da área de trabalho: Modelo › Lançar na planta › Tesoura de aço pelo desenho (aparece onde o CAD tem o comando: o dev); Análise estrutural do modelo (etapas 1–3 do plano de 06/10): motor de pórtico espacial sobre o esqueleto com o giro das peças, rótulas por condensação (almas no plano da treliça, tesoura no apoio, viga–pilar), bases arti…; Análise estrutural: cobertura retrátil (lona) — a tesoura lançada vira molde copiado em N posições (aberta pelo comprimento total, retraída empilhada na ponta), peso ajustado ao total do fabricante, sanfona em X rotulado…; Análise estrutural: o 3D não girava — a camada "sem resultado" (#vazio, display:flex) ficava por cima do palco mesmo escondida e engolia arraste, roda e os botões de vista; Cobertura retrátil no 3D: as mesmas tesouras e a mesma sanfona da análise, aberta ou retraída — nucleo3d/cobertura_movel.py troca as tesouras lançadas pelas n da análise (a tesoura da planta é o molde; Cobertura retrátil: as tesouras das pontas no eixo dos últimos pilares — n tesouras em n − 1 vãos de pilar a pilar (pelos pilares do 3D: o esqueleto leva o topo do pilar à ponta da viga, 73 mm além), a pilha retraída ren…; Análise estrutural: quadro "Como ler" (web/analise_guia.js) — para cada modo (modelo, cargas, esforços, tensões, deformada, reações) e para a combinação ou o caso escolhido: o que representa, com o que se preocupar, o qu…; Análise estrutural: o analise_estrutural.js volta ao fim de linha de antes (o commit anterior trocou o arquivo inteiro sem mudar o conteúdo); Cobertura retrátil na planta: aberta ou retraída, a planta de lançamento acompanha o 3D — uma linha por tesoura na posição da situação (camada COBERTURA RETRÁTIL) e o texto com o resumo; Cobertura retrátil: cobertura_movel.py e dividida.js voltam ao fim de linha de antes (o commit anterior trocou as linhas sem mudar o conteúdo); Análise estrutural: botão Voltar (a tela anterior; Análise estrutural: troca de perfil só na análise ("e se") — na tabela por grupo (função + perfil original), "trocar" abre a lista do catálogo (mesma família, do mais leve ao mais pesado, ou o nome digitado) e recalcula; Análise estrutural: a lista da troca de perfil visível (a datalist do navegador filtrava pelo texto e não mostrava nada) e com a estimativa de cada alternativa — os esforços da combinação que governa cada barra do grupo …; Análise estrutural: a seção de cada pilar desenhada na base, na orientação do cálculo (a alma = a inércia forte; Análise estrutural: a deformada mais forte no tema claro (magenta escuro e linha mais grossa; Análise estrutural: a estrutura em cinza mais escuro no tema claro (cargas, esforços, deformada e reações): sumia no fundo claro; Análise estrutural, etapa 4: 2ª ordem da NBR 8800 e verificação de cada peça pela norma; Análise estrutural, etapa 5: bases pela NBR 8800:2024 (6.7) com as reações concomitantes, apoio das tesouras, esforços nas ligações e a 2ª ordem alinhada à 4.10.7; Resumo de materiais: peso de compra dos perfis (kg por barra comercial pelo kg/m do catálogo e o total das barras, com a sobra), ao lado do kg das peças; Análise estrutural: bases de pilar tubular pela NBR 16239:2013 (seção 8) e o comprimento de flambagem das treliças de tubos (4.8), com o apontamento das paredes abaixo de 2,5 mm; Plano de corte: quadro de todos os perfis para a consulta rápida e os planos recolhidos por perfil (abre pelo quadro ou pelo título; Plano de corte com e sem emenda: os dois encaixes por perfil para a comparação, e a escolha do que vai para a compra; Análise estrutural: a ligação da viga apoiada no topo do pilar (chapas parafusadas), o chumbador em J pela NBR 6118 e a base com abas de reforço; Tela inicial: "Novo a partir do arquitetônico" e "Novo desenhando em 2D" viram um botão só, "Novo pelo CAD 2D…", com a escolha "Como começar" (tenho a planta do cliente / desenhar a estrutura eu mesmo) no diálogo; Análise estrutural: a base com duas abas por lado (nas pontas das mesas) e a especificação do chumbador em J que fecha; CAD, Malha de eixos: a caixa do diálogo alarga para os campos caberem (cortava os rótulos e rolava de lado), "Pegar no desenho" numa linha só, primeiro número e primeira letra lado a lado; Área de trabalho: as ferramentas nas colunas ao lado, como nas telas sozinhas (o padrão de todas as telas); CAD: ferramenta Eixo, um por vez — clique num eixo e o seguinte (paralelo) vai com o cursor, ou digite o vão (6000, 3x6000, 6000 6000 7500); CAD, Calibrar escala do arquitetônico: escala junto o que foi desenhado por cima (eixos, cotas da malha, elementos), com pilar, fundação, consolo e bolinhas mudando só de lugar (a bolinha e o nome na ponta do eixo, o rót…; CAD: a escala do desenho acompanha o DXF importado e as cotas acompanham o desenho em volta; CAD: menu do botão direito — clique curto abre o menu no cursor (arrastar continua sendo o pan); CAD, Planta de lançamento: ao abrir, a planta do cliente com tamanho que não é de obra (menos de 15 m ou mais de 2 km) pergunta no aviso — "Escalar ×10" (planta, eixos e cotas juntos; CAD: o quadrinho da escala no canto de baixo à direita do desenho (visível também na área de trabalho, onde a barra de cima some) — a escala atual com o seletor ligado ao de cima, a régua gráfica que acompanha o zoom e o…; CAD, barra de baixo: só aparece o botão que faz alguma coisa no projeto — Detalhamento só depois de detalhar, Pranchas só com pranchas (antes só avisava), Original e Montagem só com a planta do cliente, Enviar para quadr…; CAD: Ajustar cotas e eixos à escala — as cotas (texto de 2,5 mm, sem fator), os balões dos eixos (5 mm, na mesma ponta) e os nomes (4 mm, no centro do balão) feitos no CAD no tamanho da escala atual, com seleção só nela; CAD, Planta de lançamento: a planta do cliente fora do tamanho de obra pergunta antes da escala pelos textos — na planta em centímetro os textos são 10× menores e a sugestão "Ajustar a escala para 1:12,5" acertava os tex…; Tela de projetos: com o servidor reiniciando (no desenvolvimento, a cada .py alterado), a lista espera ele voltar ("Esperando o programa responder…", até 1 min, depois "Tentar de novo") em vez de mostrar "Nenhum projeto …; CAD: Medidas em mm, cm ou m — a unidade das medidas, separada da escala de impressão (o usuário punha 1:12,5 para "trabalhar em cm" e o pilar e o vão lançados saíam em mm): o número digitado sem unidade vale a unidade (4…; CAD, Escalar a planta do cliente (×10 e Calibrar): os textos, as cotas e as hachuras do arquivo crescem junto com a planta — o transformar só move o texto (a altura é de papel) e no Docas ×10 os textos do arquivo ficaram…; Análise estrutural: vento direto nos pilares, vigas e X entre pilares (NBR 6123:2023, 8.1) — antes o vento só entrava pela cobertura (Tabela 25) e pelas abas, e o pilar recebia só o que a cobertura passava a ele (o engen…; Varredura geral antes da 0.8.58: falhas, código morto, desempenho, instalador e testes.

**0.8.57.** (05/10/2026) Modelos grandes (o IFC de 321 MB do Bella Casa, Revit): abrir no editor 3D cai de ~45–55 s para ~7–8 s (o servidor manda o modelo como está no disco e as arestas saem direto das faces, sem as diagonais que riscavam as peças redondas); a importação vai de ~139 s para ~100 s com o resultado idêntico peça por peça; o modelo gravado fica 35% menor (199 → 130 MB) e a gravação automática não reescreve mais o arquivo inteiro no servidor; a memória da aba cai de ~1 GB para ~490 MB (peças repetidas, como os parafusos, desenhadas uma vez só; cor e normal compactas). Importar um IFC grande pela tela inicial ou pelo editor manda o arquivo como ele é (antes passava do limite e dava "Failed to fetch"). IFC do Revit: o perfil é o tipo (W200X22.5), sem o número da peça — "colorir por perfil" não pinta mais cada peça de uma cor. Perfis com a bitola e a espessura juntas (C127X50X17X#13/2.25mm) em todo lugar que se lê; telhas multi-dobra MD e cumeeira CU, o padrão da fábrica; resumos da obra e de materiais refeitos sozinhos, com pendências e a parte de compra; exportar o pacote do projeto (.metalica.zip); cabeçalho do projeto numa linha só, com busca Ctrl+K que acha as peças do 3D e o botão de tema; piso do 3D em tom neutro. A parte comercial (orçamento, proposta, contrato, obra e pagamentos) segue só na versão de desenvolvimento: não está neste programa.

**0.8.56.** (03/10/2026) Leitura por quadros: quadro Viga treliçada (viga painel, de transição, pergolado); pranchas: as três regras aprovadas em 01/10, chapas de corte em 1:10 e DXF de corte em tamanho real, cantoneiras L separadas das chapas (e fora do DXF de corte), "DXF de todas as pranchas", chamadas com o nome das chapas nas tesouras; regras 3D → detalhe → prancha (R1–R6): o 3D é a peça, a furação da máquina vai para o modelo, "Aplicar no 3D" quando o editor está aberto, peça gerada travada no desenho e pranchas conferidas antes de exportar; editar chapa isolada ou no local, a partir do 2D ou do 3D, espelhada do outro lado do prédio, furo copiado com o parafuso e Cancelar/Concluir voltando ao desenho de antes; furação padrão das terças (50 mm na altura, limite da máquina) também nos suportes e chapinhas, oblongo pelo parafuso até a terça, chapas da mesma posição com furação diferente viram posições diferentes; CAD: duplo clique edita texto, A−/A+ em bloco, cota em mm da peça e cota girada/espelhada inteira, DXF com as cotas como na tela e o número em branco; editor 3D: Esc solta a ferramenta sempre, parafuso fura também as barras do catálogo, "Furar pelos parafusos já colocados", peso total da estrutura na barra de baixo; típicos de barra com o suporte montado em cada ponta; telhas: canto em meia-esquadria do anel e planta dos tipos sem cores e sem eixos; barra Original | Montagem | Pranchas em todo projeto e aba Detalhamento; importar .skp direto (pela biblioteca do SketchUp instalado), com viga dupla separada em duas; correções da conferência: a peça cortada duas vezes seguidas no Encaixar ponta (o bico) não volta mais com um plano só, o primeiro detalhamento parcial não se refaz sozinho ao abrir o CAD, e a variante de furação de uma chapa conta como a mesma peça no conjunto (o resumo da obra voltou a contar as tesouras certas).

**0.8.55.** (versão da noite, 01/10/2026) Montagem do projeto recebido, etapa 1 da leitura por quadros (plano de 01/10): abas Original | Montagem | Pranchas embaixo do CAD no projeto com a planta do cliente; Montagem, etapa 2 da leitura por quadros: da Original para o quadro; Montagem: fim de linha LF nos arquivos novos (montagem.js, montagem.css, verif_montagem_ui.py), como o resto da pasta; Leitura por quadros, etapas 3 a 6 (plano de 01/10): ler cada quadro, pré-análise, banco de detalhes e o 3D pelos quadros; Cumeeira com as pernas da fábrica: PERNAS_CUMEEIRA = (300, 500) em nucleo2d/detalhe/telhas.py — cada perna vai no menor padrão que cobre a modelada (o TecnoMETAL traz 260, sai 300; Leitura por quadros: revisões da Original (o DXF novo do cliente vira R01, R02… no mesmo referencial; Leitura por quadros: a conferência projeto × modelo depois do 3D (o título e a lista do projeto, as marcas da planta e o que entrou no modelo, por tesoura e por sigla de terça; Pranchas: as alterações feitas à mão na Sala de Compressores (30/09 e 01/10) viram regra do gerador.

**0.7.19.** Eixo da barra sem enviesar: barra de perfil pelo comprimento da aresta reta mais longa da face
principal, redonda pelas geratrizes (arestas longas do cilindro) — o eixo dos vértices inclinava com
furos, ponta cortada ou gancho, e o refino pelos centros das seções (`_alinhar_eixo`) só roda quando o eixo
ainda é o dos vértices. Vista: vértice repetido na mesma posição vira um só (a "ponte" dos furos recortados
aparecia como linha no meio da terça depois de um furo retirado). Terças uma por linha, do menor comprimento
para o maior (`UMA_POR_LINHA`). Gancho com a rosca de 100 mm na ponta reta (`ROSCA_GANCHO`). Tipos novos:
cantoneira de forro (CF., L comprida solta) e perfil de fechamento (PF., U/C dobrado solto). Tesouras: só as
iguais dividem célula (as de outra composição saem em detalhe próprio) e os furos das barras aparecem na
elevação (cruz na camada FURO). Oblongo em pé na terça (copiado de chapa) gira para o sentido da barra, e a
chapa junto.

**0.7.20.** Legendas enxutas em todas as células (`_cabecalho`, conjuntos, montagens, telhas): nome e
quantidade com o comprimento no título, perfil, parafusos e peso; o tipo fica só no título do quadro e a
marca do TecnoMETAL, o material, a contagem de furos e as observações ficam nos metadados e na lista de
produção. Cotas da terça como a máquina fura (`_cotas_da_terca`): a cadeia dos furos duplos (duas furações
na mesma abscissa, a ligação ao suporte) de ponta a ponta na primeira linha, e cada furo simples (tirante,
esticador) cotado a partir do furo duplo mais próximo na segunda — o segundo simples do mesmo duplo desce
uma linha; a total fica por fora. Suporte soldado montado (chapa furada + nervura): as vistas seguem a
peça, não o prédio — "acima" é o eixo comum às duas chapas, a frente mostra a chapa com os furos e a lateral
a nervura de face, as duas retas (no modelo o suporte está inclinado com o banzo e saía torto); chapa deitada
com nervura em pé sai em elevação pela nervura e PLANTA. Paginação: as pernas da cumeeira entram na face
delas com o nome da cumeeira (CM.n) e o comprimento da perna; o título conta "N chapas + M pernas de
cumeeira". Contraventamentos: as cotas empilhadas dos tirantes ficam na própria linha (deslocamento zero),
sem as linhas de chamada até a barra.

**0.7.21.** Tesouras: cada barra furada ganha um detalhe ampliado (1:5, `_detalhes_de_furos`) abaixo da
elevação — a face furada de frente, da ponta mais perto dos furos até depois do último, trechos longos
interrompidos, cadeia da ponta aos furos e as linhas de furação; na elevação, uma chamada com a letra. Os
furos da alma virada para baixo (escondidos na elevação) aparecem aí. Canto chanfrado do banzo: a diagonal
é a tangente ao arco no meio dele (`_avanco_tangente`), não a corda — a corda cortava por dentro e a
diagonal da treliça atravessava o banzo. Suporte soldado montado sempre pela peça (frente = chapa com os
furos em pé, lateral = nervura), também o que está deitado no modelo, com as cadeias dos furos. Terça: os
furos simples dos dois lados de um furo duplo numa cadeia só, na mesma linha. Paginação: a cumeeira
hachurada sobre as telhas, com a linha e o rótulo.

**0.7.22.** Desenhos de detalhamento por família de produção (`GRUPOS`): tesouras, conjuntos (vigas, pilares
e outros), terças, contraventamentos, agulhamentos e extras em 1:25 — cada um com os conjuntos da família e
as peças que eles levam (`_familia_da_posicao`; as células são as mesmas do completo, agora com o tipo para
os quadros internos) —, telhas (1:50), chaparias (todas as chapas e as peças montadas, 1:10, para o corte),
localização e completo. Os grupos por classe de antes (`GRUPOS_BASE`: chapas, barras, tirantes, conjuntos em
1:50) continuam montados por dentro e saem só se pedidos pelo nome; ao detalhar com "substituir", os
desenhos antigos (`TITULOS_ANTIGOS`) são apagados.

**0.8.54.** **Pranchas — ajustes pedidos em 30/09.** **Elevações da localização em corte:** a elevação transversal e a longitudinal projetavam o contorno de todas as peças do prédio umas sobre as outras (todas as tesouras, as agulhas, os contraventos) e nada se lia; agora são uma fatia — só o que está no plano do corte, cada peça recortada nele, sem as de trás. A transversal corta no pórtico típico (o plano das tesouras que mais se repete; no depósito, a T1 e a T2 no eixo 3); a longitudinal, quando não há treliça comprida nesse sentido, corta na primeira linha de eixo, a dos apoios, com a ponta de cada tesoura e o chumbamento dela (no depósito, o eixo A). O título diz onde ("ELEVAÇÃO TRANSVERSAL – CORTE NO EIXO 3").**Índice das pranchas:** a relação quebrava cada linha em 125 letras e media a coluna pela mais comprida — letra 2,0 e metade da faixa vazia; agora usa a maior letra (e o número de colunas) em que tudo cabe na faixa inteira, cada entrada quebrada pela largura real da coluna, com as continuações alinhadas no texto. **Chapas para corte no chumbamento:** o chumbamento montado (CB4 + CH19 + CH24 + CH25, CB1.1 + CH9 + CH14 + CH17 + CH22, CB1.1 + CH23) continua com a frente e a lateral, e embaixo leva CHAPAS PARA CORTE — cada chapa dele desenhada como na prancha de corte (contorno, furos, cotas, nome e quantidade da obra), em fileira; a cópia solta da chapa de base na mesma prancha saiu (repetia), e a cópia do chumbamento na faixa da tesoura vai sem elas. **Cota dos suportes de terça na tesoura:** o suporte só era achado a até 150 mm da reta do banzo e com até 40 mm de largura na horizontal; na tesoura de alma cheia (W250) ele fica sobre a mesa de cima, a 230–270 mm, e inclinado com o banzo — a T1 do depósito saía só com 10612 na água direita. Agora a largura é medida ao longo do banzo e vale também o suporte assentado na face de cima dele: a cadeia sai com todos (559 | 900 | 872 | 253 | 499 | 1624 … | 133 na T1). **Quadro das terças vazio / peças antigas por cima das pranchas:** o aprendizado dos ajustes tomava a repetição de uma peça gerada no mesmo lugar (as tesouras projetadas umas sobre as outras na elevação) por cópia feita à mão e a guardava — no depósito, 9366 entidades antigas voltavam em toda geração por cima do desenho novo; agora a repetição em cima da original é do gerador e só a cópia fora do lugar é desenho à mão. As que já estão guardadas saem ao montar as pranchas do zero (`esquecer_ajustes`). **Peça do 2D achada no 3D** (pedido do usuário, 30/09: no tema claro não se via onde a peça estava): a peça em destaque — a escolhida no 2D ao lado, o Ver no 3D, a achada na busca — fica na cor cheia do destaque (laranja, com o contorno forte por cima do modelo), não mais o azul da seleção misturado ao cinza, e cada grupo de peças em destaque ganha um anel vermelho de borda branca, do mesmo tamanho na tela em qualquer zoom, por cima do modelo (as chapas de um conjunto, perto umas das outras, num anel só); Esc tira os anéis com o destaque.

**Menus da área de trabalho na ordem da obra** (pedido do usuário, 30/09 — "estão muito confusos, tem a mesma função para 2 telas"; aprovado no protótipo Projeto/Prototipo-faixa-e-menus-v3.html): a barra única passa a ter **Arquivo · Modelo · Cálculo · Desenho · Produção · Ver · ?**, sem as etiquetas 2D/3D (cada item sabe o lado dele e a vista troca sozinha). **Salvar** é um só (grava o modelo e o desenho aberto) e o **Zoom** age no lado em que o mouse está. As listas longas foram para submenus (Novo modelo, Importar, Exportar, Inserir vista do modelo, Pranchas, Olhar de, Estilo, Tela) e os dois caminhos em que a ordem importa viraram roteiros numerados: Modelo › Lançar pelo arquitetônico (1 a 6) e Modelo › Montar pelo projeto recebido (1 a 5). O que depende de uma peça selecionada fica apagado com o motivo ("selecione uma peça antes"). O antigo Desenhos se dividiu em **Desenho** (trocar de desenho, vistas do modelo, cortes, estilos) e **Produção** (detalhar, pranchas, lista de materiais, a peça do detalhamento selecionada); no 3D, "Explodir peça em trechos" virou **Dividir a peça em trechos** e "Juntar peças" virou **Unir peças** (os nomes batiam com o Explodir e o Juntar do 2D). **? › Onde foi parar cada item do menu antigo…** lista o antes e o agora de cada item. Na barra, o **⌂** da tela inicial foi para o começo (no lugar do logotipo) e o tema virou um ícone ☀/☾ logo depois de 2D | 3D | 2D + 3D; "Painéis" ficou em Ver › Painéis da direita (F4). Teste: nenhum dos 95 comandos dos menus antigos some do mapa novo.

**Faixa de ferramentas única na área de trabalho** (a outra metade do mesmo pedido, aprovada no protótipo v3): as três colunas (a do 2D, a barra da disciplina e a do 3D) dão lugar a uma linha só de ícones embaixo da barra de menus, igual nas vistas 2D, 2D + 3D e 3D — sem títulos de grupo e sem etiqueta 2D/3D. Ela age no **lado em que o mouse está** (o lado ganha um contorno azul); a ferramenta que só existe no outro lado fica apagada e o clique passa o lado e começa lá (Polígono e Seção só no 3D; Hachura, Texto, Aparar… só no 2D); na vista de um lado só, as do outro somem. O que é o mesmo nos dois lados é um botão só (selecionar, linha, retângulo, círculo, arco, mover, copiar, girar, offset, empurrar/puxar, medir, cota; o pilar e a viga de aço do 2D com a Barra do 3D). Os menos usados ficam no ▾ do grupo, e em janela estreita os grupos recolhem num botão com a última ferramenta usada. Com uma peça selecionada, entra no fim da faixa um grupo verde com o nome dela, Propriedades, Ver no 3D (no 2D) e Apagar. A faixa aciona os botões das colunas, que continuam nas telas (o /cad e o editor 3D abertos sozinhos ficam como eram): ferramenta nova aparece sozinha, e a que a tabela não conhece vai para o ▾ de Modificar. Verificador verif_faixa_ui e teste de que todo id da tabela existe nas ferramentas.

**Tubos TQ/TR quadrados no 3D e cantoneira de abas desiguais** (portaria, 30/09): o perfil que só o catálogo completo conhece (tubos TQ e TR dos fornecedores) não tinha malha no servidor, e o editor o desenhava como tubo redondo; agora a geometria busca no catálogo completo e o TQ sai quadrado e o TR retangular. A cantoneira de abas desiguais (L 100×50) saía com as duas abas iguais à maior; agora cada aba com a sua medida. A bateria das obras sai idêntica com e sem a mudança. Teste test_geometria_catalogo. No modelo grande (modo leve, acima de 1.500 peças) o editor não pede a malha ao servidor e montava o tubo sem furo declarado como redondo; agora o TQ/TR com só o contorno de fora ganha o furo pela parede e sai quadrado/retangular (verif_encaixar_ui).

**Corte no ângulo e encaixe de fábrica da alma** (portaria, 30/09, pedido do usuário: "os recortes precisariam seguir como vai ser feito na indústria... um entra dentro do outro"): a barra ganhou `cortes_inicio`/`cortes_fim`, planos de corte (normal e ponto relativo ao nó da ponta, nos eixos do mundo, então a barra movida ou girada leva o corte junto). Um plano é a meia-esquadria; dois numa ponta fazem o bico. O 3D do editor e o do servidor desenham a mesma malha (conferido: volume igual), o IFC grava IfcBooleanClippingResult com IfcHalfSpaceSolid (como o Tekla e o TecnoMETAL), o peso usa o comprimento médio (volume ÷ seção) e o detalhamento lê a ponta da malha. A regra `alma_na_face.encaixar` põe os planos: a alma deita na face do banzo que passa na faixa dela (a alma estreita, como a L dupla soldada nas paredes, desce na boca do U até a alma dele; a larga para na ponta das abas), a diagonal ganha o bico encostado no montante do mesmo nó e duas diagonais sem montante se cortam na bissetriz. A montagem pela planta segue com o corte reto (`aparar`): ligar o encaixe nela fica para a revisão do Posto (usuário, 30/09; medido: a alma pesaria +1,4 t, +2,7 %, porque 9.469 pontas deixariam de parar 10 mm antes com a quina livre e passariam a encostar na face, e 504 desceriam na boca do U até a alma do banzo). Teste test_encaixe_fabrica.

**Encaixar ponta** (ferramenta do 3D, grupo Estrutura; pedido de 30/09: "para esses que passam pelo filtro eu poder ajustar manualmente"): o Fit do Tekla. Clique na barra e depois na face em que ela deve encostar: a ponta mais perto é cortada no plano da face, ou esticada até ela quando a barra é curta. Com Shift a face soma um plano (o bico) e a ferramenta continua na mesma barra. Del tira os cortes, Ctrl+Z volta, e a face que corre ao longo da barra é recusada com o motivo. Verificador verif_encaixar_ui.

**Virar perfil** (ferramenta do 3D, atalho V, grupo Estrutura e faixa; pedido de 30/09: "algo como a ferramenta virar do SketchUp"): gira a seção da barra no próprio eixo, com os nós no lugar. Passando o mouse aparecem a seção de agora (cinza) e como ela fica (laranja). Clique gira 90°, Shift gira ao contrário, Ctrl vira 180° (a boca do U, a aba da cantoneira), e o ângulo digitado com Enter vira o passo. Com barras já selecionadas, o clique vira todas, cada uma no seu eixo; Ctrl+Z desfaz de uma vez. É o campo Rotação das propriedades a um clique. Verificador verif_encaixar_ui.

**Montagem do projeto recebido — etapa 1 da leitura por quadros** (plano de 01/10, Projeto/Leitura-por-quadros-plano-2026-10-01.pdf): no projeto com a planta do cliente, o CAD ganha embaixo as abas **Original | Montagem | Pranchas**. A Original é a planta de lançamento (o DXF do cliente); a Montagem é o desenho "montagem" do projeto, em mm de papel, com os quadros onde o operador vai pôr cada parte do projeto: Locação, Posição das terças, Posição das tesouras, Elevação frontal, lateral e fundos, Corte transversal, uma Tesoura por quadro (com nome, e "+ corte tesoura" para mais uma) e Detalhes de ligação. Cada quadro tem a sua escala (planta 1:100, elevações e corte 1:50, tesoura 1:25, ligações 1:10). A alça do canto ajusta o tamanho, e os outros quadros se movem e se acomodam, levando o que está dentro deles. Os quadros ficam gravados no próprio desenho. Módulo web/cad/montagem.js. Verificador verif_montagem_ui.

**Etapa 2: da Original para o quadro.** Na Original, o botão **Enviar para quadro** marca um retângulo (dois cliques ou arrastando) e pega tudo o que está inteiro dentro dele, inclusive as camadas travadas do cliente. A janela pede o quadro (ou "+ nova tesoura" com o nome), a escala e se substitui o que já está lá. O desenho vai **copiado** para o canto do quadro, reduzido à escala dele: textos, cotas e hachuras ficam proporcionais, e a cota guarda o valor real escrito. Se não couber, o quadro cresce (os outros se acomodam) e o aviso diz em que escala caberia no tamanho que tinha. A cópia guarda de onde veio (o desenho, a área e quando), que é o que a revisão vai comparar quando chegar um DXF novo. A escala é conferida pelas cotas copiadas: o número escrito contra a medida no desenho do cliente; se a maioria não bate, o aviso diz o fator (o DXF em cm ou em m). Na Original, cada área já mandada fica contornada com o nome do quadro.

**Etapas 3 a 6: ler os quadros, pré-análise, banco de detalhes e o 3D pelos quadros.** Cada envio de área guarda a sua volta para o real (a escala, a caixa na Original e o canto no quadro), e mandar outra área sem substituir põe o desenho ao lado do que já está (a lista das terças ao lado da planta). Na Montagem, **Ler quadros** abre o painel da leitura: o servidor lê cada quadro em milímetros reais, nas coordenadas da Original (nucleo3d/leitura_quadros.py, rota POST /api/projetos/&lt;s&gt;/montagem/ler) — a tesoura vira um elemento único (banzos, montantes, diagonais, os perfis da legenda, também na grafia do Advance "U100x40#2mm", os suportes e as terças que a elevação desenha), a locação dá pilares (seção, contorno, concreto 30/30 ou Ø40) e eixos (pela linha de cada balão, a ala girada inclusive), as terças dão as linhas com sigla e a lista, a posição das tesouras as marcas em cima de cada linha, o corte e as elevações os níveis; a locação desenhada noutro canto é trazida pelos nomes dos pilares em comum. A **pré-análise** lista erros (impedem o 3D: perfil que o catálogo não reconhece, tesoura sem legenda, banzo interrompido, marca sem quadro de tesoura, sigla sem quantidade, função sem variante, sem topo dos pilares) e avisos (quantidade do título × marcas, sigla da lista × planta, contravento da planta × lista, pilar fora dos eixos, barra solta, tesoura sem diagonal, escala que as cotas não confirmam); o clique leva ao ponto no quadro. No quadro **Detalhes de ligação** o operador escolhe, por função, a variante do **banco de detalhes** da empresa (nucleo/banco_detalhes.py, GET/POST /api/banco-detalhes; ST1, SC1, Castanha 16, apoio em concreto, emenda por transpasse; "Cadastrar variante…" grava em banco-detalhes.json da pasta de dados). **Gerar 3D** (POST …/montagem/gerar-3d, nucleo3d/de_quadros.py) monta pelos quadros: cada tesoura um bloco colocado pelas marcas (peças em linha contínua encostadas; a ponta mais funda para dentro), banzo em U deitado, L dupla nas paredes do U, encaixe de fábrica da alma; terças cortadas nas siglas, na altura da terça desenhada na elevação, com a alma virada para o suporte; ST1 atravessado no banzo, paralelo à terça, só onde a elevação desenha o suporte (e nas pontas); tirante entre dois SC1 girados no ângulo da barra; pilares de concreto só de apoio. Com erro, só com "gerar assim mesmo", gravado no projeto (gerado_por_quadros). Conferido na portaria do Projeto Hermes: as 5 tesouras lidas pelos quadros são as mesmas barras do modelo montado; tesouras, terças (92) e ST1 (120) caem a menos de 1 mm; os tirantes seguem a planta (a portaria usou o comprimento da lista — fica como aviso); fora do gerador: a V.T01 (sem marca na planta), forro e molduras, parafusos e furos. **Viga treliçada** (01/10, "não tem a viga painel para importar"): quadro próprio para a viga painel, de transição ou de pergolado — "+ nova viga treliçada…" no Enviar para quadro, com nome (VP1); lida como a tesoura (elemento único), a quantidade do título também no meio ("VP1 - 01X - cuidar lado da cantoneira"), colocada pelas marcas da planta e na conferência projeto × modelo. A barra de baixo (Original, Montagem, Pranchas e os botões) fica numa linha só, na altura da caixa das coordenadas e alinhada com ela. A conferência (empacotar/publicar_noite.py) roda em prioridade baixa: de dia o computador continua usável.

**Revisões da Original:** na Original, **Nova revisão do DXF** lê o DXF novo do cliente como a revisão seguinte (R01, R02…; desenho "planta-de-lançamento-r01"), no mesmo referencial da primeira (o deslocamento para perto da origem é o dela), e a aba passa a dizer "Original R01". Os quadros não mudam sozinhos: a pré-análise compara a área de cada envio na revisão em que foi copiada com a revisão atual (objetos novos e que saíram) e o apontamento traz **Atualizar pela revisão**, que copia de novo aquela área no mesmo lugar e escala do quadro (rota POST …/montagem/revisao). testes/test_leitura_quadros.py (10 testes) e verif_montagem_ui (18 pontos novos).

**Empurrar/Puxar na barra** (30/09, "a função puxar não está funcionando... clicar na face do perfil para estender"): a ferramenta aceitava só sólido e chapa. Agora, na barra, a ponta apontada anda no eixo dela (estica ou encurta, a outra ponta parada; clique na lateral vale a ponta mais perto), com a medida digitada e o Ctrl+Z; os cortes no ângulo daquela ponta vão junto. Verificador verif_encaixar_ui.

**0.8.53.** **Segurança do cálculo — leva 1 da auditoria de 30/09** (relatório em Projeto/Auditoria-geral-2026-09-30.pdf; tabelas conferidas célula a célula nas imagens da norma). **C1 — vento em toda situação de abertura:** os casos de vento do pórtico eram fixos em C<sub>pi</sub> = +0,2 e −0,3 (duas faces opostas); com estanque, quatro faces ou portão aberto a pressão não era achada e entrava 0,0 — o pórtico saía sem vento. Agora sai um caso por C<sub>pi</sub> da situação escolhida, e a pressão que faltar é erro, nunca zero. O portão aberto a barlavento, sem a razão de áreas na tela, entra com o caso mais severo (+0,8) e aviso; a sotavento e em face paralela, com o C<sub>e</sub> da face e também com o vento entrando pela abertura (+0,8), porque o vento sopra de qualquer direção. **C2/C6 — Tabelas 6 e 7 da NBR 6123:2023:** a faixa 1/2 < h/b ≤ 3/2 do telhado tinha valores que não são os da norma (EF −0,9/−1,2 a 0°/5°, a norma dá −0,8/−0,9; EG −0,8 a 0°, a norma −1,0; GH −0,4 em todos os ângulos, a norma −0,6 até 15° e −0,5 depois; FH −0,5, a norma −0,6 até 20° e −0,8 depois), e a observação "a favor da segurança" saiu; a faixa 3/2 < h/b ≤ 6, com os ângulos dela (40° e 50°), passou a existir (antes era erro); nas paredes, com h/b ≤ 1/2 e 1 ≤ a/b ≤ 3/2 o C2/D2 do vento na parede maior é −0,4 (era −0,5), e com 1/2 < h/b ≤ 3/2 e 2 ≤ a/b ≤ 4, no vento pelo oitão, D é −0,3 e A2/B2 −0,4 (eram −0,5); o telhado no vento longitudinal ganhou a terceira zona I/J (NOTA 3: −0,2 para a/b ≥ 2) e as larguras das zonas de parede da figura (2h ou b/2; b/3 ou a/4 até 2h); os coeficientes locais vêm do c<sub>pe</sub> médio das tabelas. **C3 — S<sub>3</sub> da Tabela 4 de 2023:** os grupos eram os de 1988 (1,10/1,00/0,95/0,88/0,83, com "vedações" como grupo) e o S<sub>3</sub> escolhido na tela era lido e descartado — o vento saía sempre com 1,00. Agora 1,11 / 1,06 / 1,00 / 0,95 / 0,83 (grupo 3 = residências, hotéis, comércio e indústrias, o padrão) entram em V<sub>k</sub>; o cálculo do IFC traduz o grupo guardado pela tabela antiga uma vez (o 2 de "indústria" vira 3, não 1,06) e o módulo 3D usa a mesma tabela. **C10 — S<sub>2</sub> constante até 10 m na categoria V** (Tabela 3 e item 5.3.3), não só até 5 m. **C4 — sobrecarga da NBR 6120:2019, item 6.4:** q = 0,50·α entre 0,25 e 0,50 kN/m² pela inclinação (em telhado de até 2 % o mínimo é 0,50; a 0,25 da tela sobe, com aviso), no galpão e no cálculo do IFC; e a carga concentrada de 1 kN na posição mais desfavorável, só com a permanente: na terça no meio do vão (governa nos vãos curtos; também nas terças de cobertura do cálculo do IFC e na triagem de perfis dele) e no banzo superior da tesoura no meio de cada painel (combinação C6). **N1 — base com arrancamento:** a base recebia só a maior compressão; agora recebe também a menor (a da sucção, negativa quando o pilar é arrancado): a tração vai inteira aos chumbadores, somada à do binário, e o atrito placa–grout nessa combinação é zero. **N2 — viga do pórtico à flexão composta** com a força normal do mesmo caso que dá o momento, e também no caso de maior compressão com o momento dele; vale o pior (antes a normal era descartada). **N3 — K e C<sub>b</sub>:** o pilar com K = 1,0 no plano, já que os esforços chegam amplificados por B1/B2 (o K = 2,0 somava a 2ª ordem duas vezes), e C<sub>b</sub> pelo diagrama do caso que governa, no trecho destravado do pico (eram 1,14 e 1,67 fixos). **N4 — cortante de tubo circular** pelo item 5.4.3.6 da NBR 8800:2024 (0,5·τ<sub>cr</sub>·A<sub>g</sub>/γ<sub>a1</sub>, com L<sub>v</sub>); a fórmula da alma plana não vale para ele, e sem L<sub>v</sub> é erro. Testes célula a célula das Tabelas 3, 4, 6 e 7 e um por opção da tela (aberturas, grupo, inclinação).

**0.8.52.** **Pranchas que guardam os seus ajustes** (pedido do usuário, 29/09): o que você muda na prancha gerada — mover ou escalar uma célula, arrastar um texto, uma chamada ou o número de uma cota, apagar o que foi gerado, desenhar ou escrever à mão — volta na próxima vez que as pranchas se refazem. Cada peça gerada leva a identidade da célula (a posição, o conjunto, a montagem) e a impressão do lugar em que foi gerada; ao refazer, a prancha gravada é comparada com as impressões e os ajustes vão para detalhamento/ajustes-pranchas.json (com um diário), aplicados na prancha nova pela mesma célula e peça. Peça que mudou demais (o ajuste não acha mais a peça) fica de fora e é contada. **Janela de seleção** do CAD com zoom ou pan no meio do arrasto: o primeiro canto fica no ponto do desenho clicado. **Faixa de ACESSÓRIOS** que invadia a legenda: quando a legenda final sai mais larga que a estimada, o detalhe que passaria da borda sai da faixa. Sigla **S.T.** (suporte de terça) na legenda. **Prancha de corte em retângulos iguais:** cada chapa no seu retângulo, do tamanho da maior, em fileiras alinhadas, com a moldura. **Chapas na posição montada, com a base reta:** toda chapa é desenhada como fica na obra — em pé com o alto para cima, deitada com o norte para cima —, e os furos editados no 2D voltam ao sistema da chapa mesmo assim. **Chumbador de parede:** a elevação do conjunto (CB2, CB3) olha ao longo da chapa em pé — a chapa em pé, as barras deitadas para a esquerda, as nervuras para a direita. **Suporte de terça:** a altura da terça pelo nome do perfil (a C200 inclinada caía no passo de 100), o furo só na terça que corre ao longo da chapa (a de parede que atravessa o suporte da ponta do oitão levava furos para fora da chapa), o eixo da terça pelas arestas compridas. **Detalhe típico** com a barra na direção das arestas dela (a cantoneira A.C. no caimento saía torta). **3D → 2D no projeto do IFC:** a peça escolhida no 3D leva o 2D ao detalhe dela. **Prancha quase vazia** (uma categoria só, pequena) vai para o espaço livre de outra. **O retângulo da prancha de corte** tem um padrão: o cabeçalho (nome, perfil, furos, peso) no canto de cima à esquerda com margem, a escala no canto de baixo à esquerda, o desenho centrado no que sobra. **Conjuntos espelhados iguais:** o tirante ou a agulha espelhada (o par de diagonais do X) é a mesma peça e ganha um nome só — no depósito os 24 contraventos eram 12 pares CV.1/CV.2 de mesmo comprimento. **Montar pranchas do zero:** o pedido com `esquecer_ajustes` gera as pranchas sem os ajustes aprendidos. **Uma caixa em cada detalhe:** nas pranchas, cada célula (o contravento típico, o DP, a terça…) sai na sua caixa, só com o elemento detalhado dentro, com o mesmo padrão do retângulo da prancha de corte — o cabeçalho no canto de cima à esquerda com margem, a escala no canto de baixo à esquerda, o desenho centrado no que sobra; na prancha de corte é a grade de retângulos iguais. A tesoura que enche o quadro continua centrada nele, sem caixa. **Tesoura de alma cheia arrumada:** a barra W da tesoura é detalhada inteira só na célula dela na prancha das barras (com as cotas dos furos, a linha de cima com a cadeia em cima), e não mais repetida embaixo da tesoura em 1:50, onde saía ilegível; o bloco do título escreve cada perfil uma vez (a W200X22.50 aparecia três vezes, uma por função); a tesoura reduzida para caber na folha reespaça as linhas do bloco, que se atropelavam. **Exportar e importar o projeto inteiro** (pedido do usuário, 29/09): na tela Projetos, **Exportar** baixa um arquivo `.metalica.zip` com tudo o que foi feito no projeto — modelo 3D, IFC de origem, cálculo, desenhos 2D, pranchas, detalhamento e os ajustes das pranchas (o histórico do modelo fica de fora) — e **Importar pacote…** abre esse arquivo como um projeto novo na pasta de dados de quem recebeu, sem mexer em nada que já exista; o projeto guarda de onde veio. Rotas `GET /api/projetos/<slug>/exportar` e `POST /api/projetos/importar-pacote`. **Cancelar a conferência:** a barrinha da conferência do modo desenvolvimento ganhou o botão **Cancelar**, que derruba os testes, os verificadores e a bateria na hora (`POST /api/conferencia/cancelar`, pelo processo que a conferência grava); nada é publicado, a rodada da noite desfaz a cópia limpa e recomeça do zero quando for pedida de novo. **Cotas que pegavam no vazio** (revisão pedida pelo usuário, 29/09, conferida cota a cota em todas as pranchas do depósito e da Sala): o ajuste aprendido de uma célula que só tinha sido montada de outro jeito entre duas gerações (o S.TI.2 com escala × 1,088 e 21 entidades "movidas", cotas fora da chapa) não é mais aprendido — quando metade ou mais das entidades de uma célula aparecem movidas dentro dela, nada se aprende dela; na barra redonda com gancho, a cota total mede o que está desenhado (a desenvolvida fica no título) e a altura vai do lado da dobra; na planta de chumbação, as totais medem os chumbadores e as chapas, não a ponta das linhas de eixo; no DP, a cadeia de cima nasce na peça em cada ponto (a linha de chamada do ponto mais baixo desce até ele). **Padrão de organização das caixas nas pranchas** (pedido do usuário, 29/09: "para não parecerem que só foram jogados ali dentro"): cada fileira de caixas vai de borda a borda do quadro, com a sobra de largura repartida igualmente entre as caixas e todas na altura da mais alta, o topo alinhado; o desenho continua centrado em cada caixa, com o cabeçalho no canto. A fileira com poucas caixas (a última) fica à esquerda, só com a altura igualada, como a última linha de um texto justificado. As colunas das terças e a grade da prancha de corte ficam com todas as colunas da mesma largura, de borda a borda, a última fileira nas mesmas colunas. Ficam como estavam as tesouras, a faixa de acessórios e as caixas sem cabeçalho (telhas, vistas); o alargamento para antes de outra caixa ou de um quadro encaixado. **Correções da análise das pranchas** (29/09, relatório em Projeto/Analise-das-pranchas-2026-09-29.pdf): a planta de chumbação sem a total das peças quando há eixos e com o título no cabeçalho da caixa; o suporte de terça só com a terça aparafusada nele (com parafusos no modelo), e a legenda, o CONTEÚDO e o índice pelo nome da caixa; a chapa não retangular com a cota de cada aresta inclinada, e a chapa sem aresta de baixo reta girada pela aresta mais comprida; a barra cortada em ângulo com a face curta cotada; a barra dobrada em planta com a cadeia trecho reto | resto na vista de cima (F.T.1: 495 | 8100); o toco de perfil mais curto que a altura dele (o B.14, W250 de 156 mm) com o eixo no comprimento, não na altura da seção (saía "L desenv. 715"); a barra de malha aberta no arquivo (a DP.17.1) reta pelas fatias e com o peso pela seção × comprimento (saía dobrada, 1798 mm e 4 % mais pesada); o chumbador sem o poste vizinho desenhado (o CB1 saía com uma cantoneira alta sem cota); a prancha quase vazia não recebe o bloco de outra quase vazia (sobrava uma prancha misturada e rala); e a peça maior que a barra comercial de 12 m (a do plano de corte) sai com "prever emenda" no cabeçalho da caixa e na lista de avisos do detalhamento (A.C.5, A.C.15, rufos e calhas do depósito; A.T.1 e A.T.2 da Sala) — a emenda é do projetista. Nas telhas: a mesma telha com um comprimento só em toda a paginação, o da posição (a TL2 do depósito saía 10,32 m numa água e 10,27 na outra — a direção da onda enviesada no caimento somava um pedaço da largura); a face que vale por outras diz "34 chapas por face (68 no total)" e o singular "1 chapa"; o detalhe ampliado da multi-dobra com a escala real ("ESC. 1:33 (1:100 ampliada 3x)"); na face, a nota de que a cota da multi-dobra é o desenvolvido (na água só aparece a reta); a caixa centrada no quadro não passa da borda dele (a FACE 5 da Sala saía 12 mm para fora); e as pranchas de telhas com LEGENDA (as telhas, a multi-dobra e a cumeeira com a quantidade da obra, e as siglas). Na leitura das pranchas: a cadeia horizontal de cima do DP pelo topo do desenho também no trecho reto e no comprimento da água (o 906 caía sobre o 839 do DP.3 da Sala); a chamada da chapa do chumbamento na tesoura procura a direção em que o texto não cai sobre um número de cota (o "CB1 + CH9" em cima do 463 da ponta); as cadeias fundem pontos a até 3 mm (furos de duas colunas 1 ou 2 mm desalinhados no modelo davam a parcial de 2 mm da CH11, com o número encavalado); e a legenda abrevia também a lista com vírgulas ("T.L.5 … T.L.22" — as quantidades saíam da caixa da legenda). Nomes e textos: o conjunto de uma barra com chapinhas de ponta é agulhamento também quando outro conjunto já fez a barra agulhamento lateral (dependia da ordem: o "CH2" do depósito e o "DP.1" no típico dos contraventos da Sala viraram A.L.4 e A.L.3); a telha sai das plantas de localização (TL2 ao lado de T.L.2); o cabeçalho do DP sem os parafusos da terça presa nele, e a altura do DP estreito cotada de um lado só (423 | 423 dos DP.37 a DP.41); os detalhes de furos das barras da tesoura na legenda ("B.28  det. A"); a faixa de baixo com o título da categoria quando só recebeu as últimas peças dela ("BARRAS (CONTINUAÇÃO)", não ACESSÓRIOS); a chapa que acompanha o chumbamento no padrão da caixa (título no canto e ESC.); o CONTEÚDO do carimbo quebrado pela largura real; o furo medido na malha no meio milímetro mais perto (Ø12,9 → Ø13); "Peças de ponta", "02x" e a polegada com as aspas juntas ("1/4''"); uma casa a mais no peso das peças leves (0,126 kg/pç; o conjunto com duas); e o aviso da chapa com a medida do modelo diferente do nome do TecnoMETAL (a CH11 da Sala: 148 x 240, nome 148 x 148). Ficam como estão, de propósito: as cantoneiras de ponta dos contraventos com CH (a sigla é "chapa, suportes e castanhas") e a barra comum a vários típicos com nome próprio (A.C.8 serve a A.C.1 … A.C.7). Por fim ("pode corrigir"): as faces de telha não se reduzem além de 1:125 para caber numa prancha (o depósito saía em 1:200, ilegível; o que não couber segue para a prancha seguinte, salvo a face mais larga que o quadro, que vai até a escala em que cabe); nas elevações da localização só as tesouras, os dispositivos e os chumbamentos (as terças, os contraventos e as agulhas, uma marca por peça em todo vão, amontoavam tudo — estão na planta); e a prancha não fecha quando a categoria acabou na fileira parcial e ainda sobra espaço para a próxima.

**0.8.51.** **Prancha de corte mais cheia** (pedido do usuário, 29/09): quando a próxima fileira não cabe, as peças menores da mesma categoria que ainda cabem na altura que sobra vão antes de fechar a prancha; menos folga entre um quadro e o seguinte; a vista de cima das barras mais perto das cotas da de frente. Na Sala, as barras (A.T., F.T., DP.x.1, B.x) cabem na prancha das chapas — 9 pranchas. **A localização é a prancha 01** (a planta e as elevações com os nomes das peças), centrada, com o **índice das pranchas** na faixa de baixo: número, título e o conteúdo de cada uma, as linhas longas quebradas. Na legenda de cores das telhas, a amostra de cor acompanha o texto dela quando a célula é reduzida. **Desenhos que se empilhavam:** ao refazer o detalhamento, as vistas geradas da localização e da chumbação eram tomadas por desenho à mão e copiadas junto — a cada atualização automática uma cópia a mais (a Sala chegou a 75 mil entidades na prancha 01 e a tela das pranchas ficou lenta); agora o que é gerado é refeito. **Eixos automáticos** (o depósito químico, 29/09: o IFC veio sem a categoria TESOURAS e os eixos saíam inclinados, 2 numerados e 10 letras): a direção sai das barras das treliças (em planta caem todas no vão), as treliças são reconhecidas pela geometria quando o nome não diz (conjunto num plano vertical, comprido e com altura — a terça no caimento não conta), as letras só das chapas de apoio do nível mais baixo (não as deitadas dos nós) e cada apoio cai num cruzamento — o eixo vai ao centro do apoio e o pilar do oitão ganha a sua letra; na planta, a linha do eixo passa da borda das peças, e a bolinha não cai mais em cima do beiral. **Chumbadores do depósito químico:** o perfil "BR3/4''" (BR + bitola) é barra redonda — antes nenhum chumbador era achado e a chumbação e os eixos tomavam as chapas deitadas por chumbador; o conjunto de chumbadores com a cantoneira de ancoragem no pé é conjunto chumbador (CB1, as barras CB1.1 seguem chumbador); o **chumbador de parede** (barra curta deitada que atravessa uma chapa em pé só, quase toda do lado de dentro — a tesoura do eixo 1 presa na parede) também é chumbador, desenhado na chumbação sem criar eixo; na planta de chumbação, só a chapa que o chumbador atravessa (a CH28 do suporte da agulha, logo acima, saía junto). As varetas BR3/8'' com gancho entre as terças, que saíam como conjuntos DP.x, são agulhas diagonais (A.D.x), como na Sala. **Nomes que se mantêm:** os nomes novos só são dados depois que todos os tipos guardaram os que já tinham — a peça que mudava de tipo tomava o número de uma chapa de outro tipo (CH27 → CH33). **Tesouras de alma cheia sem a categoria no IFC** (o depósito químico): quando nenhum conjunto vem como TESOURAS, o conjunto comum num plano vertical, com vão de 4 m ou mais e altura fora do caimento, é tesoura — as meias-tesouras de W200/W250 (antes DP.6, DP.7, DP.28…DP.34) saem como T1…T8, montadas aos pares como as tesouras; a mão-francesa da marquise (2 m em balanço) e os montantes do oitão continuam conjunto. **Barra de perfil laminado na tesoura** (W, I, H): desenhada inteira como a terça — a vista com os furos da furação original (sem oblongo), a cadeia de cotas de ponta a ponta, a total, a seção —, uma embaixo da outra, no lugar dos trechos ampliados a 1:5 com quebras e da chamada em círculo (que na barra de 10 m cobria a tesoura inteira). **2D + 3D no projeto do IFC:** a seleção no desenho de detalhamento destaca a peça no 3D ao lado pela marca — a célula da posição ou do conjunto (a tesoura montada, "M16 + M17", as duas metades), e na localização e na chumbação a própria peça (a origem dela); antes só o projeto montado pela planta tinha a ligação, e o do IFC dava "Sem a ligação entre o desenho e o modelo" a cada clique (fica um aviso só, para cota e texto). O Ver no 3D usa a mesma regra. **Tesoura de alma cheia** (o depósito): as duas águas são banzo de cima — cada uma com a cadeia na própria inclinação e o comprimento dela; embaixo, ponta, apoios, cumeeira e a total —; montante W/I/H com o perfil cheio; na barra inteira, a linha de furos de cima com a cadeia em cima da peça; o montante lateral da ponta (A.L.) e as chapas dele vistos na elevação. **Suporte de terça:** a chapa segue a furação padrão da terça — 50 mm (100 acima de 200 de altura) centrados no eixo de cada terça parafusada, o furo sem parafuso sai, os parafusos e as terças acompanham —; desenhado em pé, na posição montada; o suporte chama-se **S.T.n** com a quantidade (as chapinhas seguem CH). **Terças sem furo** num detalhe típico por perfil, com as cotas empilhadas ("T.L.21 COMP=4579mm – 01X"). **Prancha mais limpa:** sem a seção nas terças e nas barras redondas, sem a vista de cima do gancho; o detalhe típico com a barra alinhada (o montante lateral saía 3° torto). **Suporte de tirante S.TI:** a chapa inteira em cima da mesa do banzo onde a ponta do contraventamento aparafusa (marcada no modelo) tem nome próprio, S.TI.n.

**0.8.50.** **Porcas e arruelas no padrão da fábrica** (pedido do usuário, 28/09: "é 1 porca e 2 arruelas por
padrão … para tudo"): cada ponta roscada de barra redonda — tirante, agulha, gancho, barra roscada, chumbador —
conta 1 porca sextavada + 2 arruelas lisas na bitola da barra, e não as porcas e arruelas soltas que o projetista
modelou (`base.pontas_roscadas`: cada solta vai para a barra cuja malha passa rente a ela; as de uma barra a até
45 mm são uma ponta). Vale na lista de materiais (o Quadro 7 deixa de mostrar "BOLT () 0x0": porcas e arruelas por
bitola), no resumo de materiais (no local da barra) e na legenda dos conjuntos. Na Sala: 168 pontas (agulhas,
barras roscadas dos contraventos, as duas pernas de cada chumbador em U). **Desenhos e pranchas que se atualizam
sozinhos** (`desenhos_vivos.py`, pedido do usuário, 28/09): o detalhamento grava um carimbo do que usou (o modelo
3D, o código do detalhamento, a furação ajustada, os eixos); quando algo muda — o 3D foi gravado, saiu versão nova —,
os desenhos são refeitos em segundo plano pelo mesmo caminho do botão Detalhar (a montagem das folhas fica), sem
regravar o modelo (que o editor pode estar editando), e o CAD aberto recarrega o desenho na mesma vista; com edição
por gravar, avisa, e a gravação por cima do desenho refeito é recusada (a tela recarrega). O desenho "Pranchas"
se refaz junto e quando um desenho de trabalho com folhas é gravado. Desenhos → Atualizar desenhos e pranchas agora
força a atualização. Verificador: `verif_desenhos_vivos`. **A faixa ao lado do carimbo em todas as pranchas** (pedido do usuário, 28/09): o último quadro de cima desce até
ela, e ela tem DETALHES — as chapas dos conjuntos desenhados na prancha (a composição deles: as da tesoura, com as da
cumeeira separadas da célula dela), ou, sem conjunto, mais peças das mesmas categorias — e LEGENDA junto do carimbo —
as peças da prancha (a composição da tesoura por unidade: nome, quantidade, perfil, comprimento e a prancha em que
cada peça está detalhada), as siglas usadas nela e, na primeira, a relação das pranchas (sem folha de índice). A
mesma posição desenhada em dois desenhos (a chapa na tesoura e nas chaparias) sai uma vez só. **Tesouras na prancha como o
usuário ajustou a Sala (28/09)**: cada tesoura montada com o nome dela em sequência — T1 (03x), T2 (02x)… —, não
"T1 + T1" (as metades ficam no perfil do item e no resumo); as cotas de baixo em três linhas coladas na base (a
cadeia sem os pontos de dentro do joelho, as metades, a total, 7 mm uma da outra); o bloco do título embaixo, à
esquerda, pela borda da tesoura; duas tesouras por prancha quando cabem, a de baixo encaixada pelo perfil no canto
vazio da de cima; chamadas das chapas e dos chumbamentos ("CB1 + CH9", um em cada apoio), com a prancha do detalhe;
o chumbamento primeiro nos DETALHES. No CAD, o número da cota na cor do texto (branco no escuro, preto no papel), o
texto da chamada arrastado pela alça com a linha acompanhando, e o F5 na área de trabalho volta ao desenho aberto.
**Uma cor por chapa** (pedido do usuário, 28/09): no conjunto com mais de um perfil numa função — os banzos da T1
são U100X50 #11, #9 e #8 —, cada perfil vai para uma camada dele ("BANZOS U100X50X#9") com uma cor, a mesma em
banzo, diagonal ou montante e em todas as tesouras do desenho (verde e ouro ficam de fora: são as cotas e as
chapas); a legenda lista cada perfil uma vez, na cor dele, e o PDF das pranchas sai com essas cores. O DXF para o
AutoCAD passa a declarar as camadas do desenho (banzos, diagonais, os perfis) com a cor ACI mais perto e nome que o
R12 aceita ("BANZOS_U100X50X_9") — antes abriam todas brancas. **A cor pela seleção** (pedido do usuário, 28/09):
nas Propriedades, a linha "Cor" muda a camada do que está selecionado — o texto da legenda e as linhas do perfil
juntos; numa camada de perfil, o perfil em todas as funções. A cor escolhida (ali ou no painel Camadas) fica no
projeto (`detalhamento/cores-camadas.json`): vale nos desenhos refeitos pela atualização automática, nas pranchas e
nos desenhos já gravados. **A telha sai da tesoura**: a linha dela e o parafuso na terça ficam só na prancha das
telhas (pedido do usuário, 28/09). No tema escuro, os botões do painel de Propriedades (Peça…, A−, A+) e as barras
de rolagem saíam brancos: o tema diz ao navegador que é escuro (`color-scheme`). **Prancha da tesoura com as
peças dela** (pedidos do usuário, 28/09):
- A faixa de baixo passa a se chamar ACESSÓRIOS/DISPOSITIVOS. Ela recebe todas as chapas e os chumbamentos das
  tesouras da prancha, com quantas estão desenhadas ali (CH4 – 08x: 4 na T1 + 4 na T2). O total da obra fica na
  prancha das chapas, e a chamada na tesoura aponta o detalhe da própria prancha.
- O que não cabe na faixa vai para o canto livre do quadro, embaixo da última tesoura. Com uma tesoura só, a faixa
  sobe para uma segunda fileira.
- A legenda ficou só com o que está NESTA PRANCHA (nome e quantidade) e as SIGLAS, uma embaixo da outra. Saíram
  a relação das pranchas e as tabelas por unidade.
- Os detalhes de furos das barras vão logo abaixo da cota de baixo da tesoura deles, com uma linha de chamada até
  a marca dos furos. Eles ganharam a cota do último furo até a outra ponta, e furos a até 3 mm um do outro são uma
  linha de furação só (24 e 26 mm davam "2" e "246" encavalados).
- Nas cotas curtas das chapas, o número posto fora da linha voltava sem a conversão para a folha e sumia; agora
  aparece.
- A chapa do chumbamento vai junto das vistas dele, embaixo ou ao lado, só com o título e a linha "PLATE…"; o
  resto está na prancha das chapas. As chapas de uma montagem de chapas (CH1 + CH2) não saem soltas na prancha da
  tesoura, porque a montagem já as cota, e a chamada delas fica sem "– PR.xx".
- Os detalhes de furos ficam perto da marca deles, com espaço entre um e outro, e sem a linha "ESC." (a escala
  está no título). A legenda tem letra maior quando cabe.
- A prancha dos conjuntos menores tem dois quadros lado a lado: "Contraventos e agulhamentos" (CV., A.C., A.L.,
  A.D.) e "Conjuntos menores" (DP.). Diagonais e montantes de cada DP saem com o perfil cheio (as duas bordas), não só a linha de eixo; o DP não leva as terças em corte nem as chamadas dos parafusos que prendem as terças nele (a ligação com a tesoura fica). Na legenda, um
  nome com muitas partes aparece resumido ("A.D.1 … A.D.10").
- Os agulhamentos de cantoneira (A.C., A.L. e o conjunto que usa a barra deles, como o DP.1 da Sala) saem num
  detalhe típico só, como as A.D.: a cantoneira mais comprida deitada, as cotas empilhadas "A.L.2 COMP=792mm –
  04X" e as peças de ponta por conjunto quando mudam. As barras deles saem da prancha de barras.
- Terças em colunas alinhadas; na faixa de baixo da prancha delas, os suportes de terça (não mais terças). A
  vista de cima da terça (o recorte da aba) ganhou o nome ("VISTA DE CIMA – T.C.4") e ficou colada na de frente. As fileiras de células ficam mais juntas (6 mm) e a última vai até o fundo do quadro: na Sala, as terças cabem em duas pranchas (13 no total, eram 14). A prancha dos chumbadores é a primeira: a planta de locação reduzida à esquerda e, à direita, os chumbamentos (CB + CH), os chumbadores e as chapas de base. As barras das agulhas e dos contraventos (A.D.1.1…) ficam só no detalhe típico deles, e a barra roscada (BR) e o gancho (G.) vão para o quadro de contraventos e agulhamentos: a prancha de tirantes deixa de existir. As telhas numa prancha só: sem as peças uma a uma (TL…), a face de cobertura repetida junta com a igual ("FACES 2 E 3"), a paginação por tipo numa coluna à esquerda (até 2x mais reduzida) e as faces na maior escala que cabe (1:100 na Sala; o detalhe da multidobra no máximo 1:100), a cumeeira na faixa de baixo (a tabela de tipos saiu). Uma célula reduzida reespaça as linhas de texto empilhadas e afasta os títulos que encostariam — a Sala vai de 13 para 9 pranchas. A prancha das chapas é a de corte: todas as chapas do projeto numa prancha só, na ordem do nome (as pranchas das tesouras, das terças e dos chumbadores levam cópias com a quantidade delas), e as barras no quadro de baixo; as peças com nome de chapa (CH15, CH16: cantoneiras) vão com as chapas. Com ela completa, a Sala fica com 10 pranchas.

**0.8.49.** Pedidos do usuário de 28/09, no detalhamento e no CAD. **Tesoura montada**: a cadeia horizontal
sem a largura dos perfis, o vão livre do joelho por dentro e a largura dele por fora, medidos pelas faces da
descida do banzo (B.14); a altura da descida (o 463 do projeto); na cumeeira, a cadeia do banzo de baixo termina
na face do montante e cada metade leva a horizontal por cima; FLECHA TOTAL e ALTURA TOTAL na ponta da direita,
como no projeto. No corte, o forro (a telha toda abaixo das barras) não entra — saía em riscos soltos debaixo do
banzo — e o texto do raio da multidobra sai (fica a linha da telha). **Terças**: o corte com o contorno fechado
e como bloco (o clique pega a seção inteira); as cotas com o furo simples primeiro (medido da referência mais
perto), a cadeia dos duplos e a total, a 7 mm uma da outra, também nas terças laterais e de oitão. **Desenho
completo** com a planta de chumbação. **Telhas**: a planta da cobertura no padrão do modelo de paginação (cada
chapa no lugar, na cor do tipo, com tipo e comprimento, eixos e legenda) e o quadro das telhas. **CAD**: cota
linear automática (a posição do mouse escolhe horizontal, vertical ou alinhada; H/V/A fixam, L volta); casas
decimais da cota; a cota se seleciona pelo número; snap nas pernas das cotas; carimbo da folha editável; MA
(copiar propriedades), também com caixa de seleção; tamanho do texto (A−/A+ e todos da camada); o texto comprido
se seleciona em qualquer ponto dele (o índice espacial guarda a caixa inteira). **Pranchas lado a lado num
desenho só** ("Pranchas", papel 1:1): Montar pranchas e Gerar pranchas das folhas gravam as folhas uma ao lado
da outra; o PDF sai uma página por folha (a da Sala em 32 s, eram 5 min). Revisão da montagem automática: a
caixa da célula conta a linha de cota (as cotas da terça invadiam a linha de baixo), "(continuação)" só quando o
quadro já começou antes, células alinhadas pelo topo. **Barras cortadas no gabarito**: as barras em U das
tesouras e dos complementos delas (o conjunto treliçado com três ou mais barras em U, os DP) não ganham desenho
próprio — a obra corta medindo no gabarito da tesoura; ficam cotadas no conjunto e na lista (W150, avulsas, peças
dobradas e chapas continuam). **Detalhe típico de contraventos e agulhas** no estilo do projeto do Posto: as agulhas
também num detalhe por grupo; as cotas empilhadas debaixo da peça, do tamanho da barra desenhada, com
"NOME COMP=Lmm – NNX" no meio; a rosca desenhada e cotada na peça em que a porca solta está (o gancho da agulha, a
barra roscada do esticador); o padrão da fábrica na ponta roscada, 1 porca sextavada + 2 arruelas lisas.

**0.8.48.** **Barrinha da conferência no modo desenvolvimento** (pedido do usuário: "uma
barrinha que mostre o progresso da conferência"): `testes/antes_de_publicar.py` grava o andamento em
`testes/_conferencia.json` (`testes/progresso.py`: as etapas, os verificadores e as obras da bateria contados um a um,
a duração da rodada anterior como estimativa) e o servidor em `--dev` o devolve junto de `/api/versao`
(`estado_da_conferencia`); a caixinha fica embaixo à direita, na janela de cima, com a barra, a etapa e quanto
falta — laranja rodando, verde ou vermelha no fim (10 min), cinza se parou (20 min sem notícia).
**Vento, caixas d'água, mezanino e combinações nos esforços** (`nucleo3d/esforcos.py`): NBR 6123:2023 — a cobertura
isolada com altura livre menor que metade da profundidade vai como edificação fechada (7.2.1), telhado múltiplo pela
Tabela 10 (os tramos pelas calhas e cumeeiras achadas na altura das terças), S2 da Tabela 3, S3 da Tabela 4 (grupo 1:
abriga inflamáveis), cpi +0,8/−0,3, quatro sentidos; a água das caixas desenhadas nas outras plantas ("CX.5.000 l", o
centro pelo círculo da caixa) a 10 kN/m³ (NBR 6120:2019, Tabela A.1); o piso do mezanino nos barrotes achados na camada
Mezanino, com o peso e a sobrecarga informados na tela; combinações últimas (γ e ψ da NBR 8800) com a envoltória da
vertical por pilar. **Tela de esforços** (`/esforcos`; 3D → Ver → Esforços da estrutura…): a planta dos pilares
coloridos pela comparação com a locação (ou pela compressão, ou pelo arrancamento), a tabela ordenável, as reações por
caso do pilar escolhido com "ver no 3D" (`destacar=ids:`), a memória do vento com a categoria e o grupo para
recalcular, o mezanino, os casos, as combinações e as hipóteses; o resultado fica em `esforcos.json` no projeto.
**O esqueleto, pelo que o cálculo mostrou**: a alma corta o banzo contínuo da própria treliça (ficava presa só nas
pontas); o nó novo no meio de uma linha é o que já existe ali; a treliça deitada presa pela lateral no banzo da outra
(a passarela); o perfil de apoio das terças fixado em cada montante; a terça que chega na lateral da transição encosta
na alma dela. No Posto CB, pontas soltas 15 → 3 e a comparação com a locação passou a ter sentido (PM7: 24,9 × 24 tf). **Escadas** (`nucleo3d/escadas.py`, ligado em `de_planta.montar`; pedido do usuário: "tem uma escada no projeto"): a
planta baixa de cada escada ("PLANTA BAIXA DA ESCADA 1") — as longarinas pela linha dupla do perfil, os lances em pares, o
patamar onde dois lances se cruzam, os degraus numerados para o sentido de subida — no lugar pelos balões em comum com a
planta estrutural, a locação e as outras plantas (a letra dá y, o número dá x) e, o que faltar, pelos pés da escada na
locação (a placa com a seção da longarina dentro); do chão ao piso de cima, com o patamar pelas cotas dos cortes (as duas
da mesma corrente que somam a altura; a de baixo). Camada "Escadas"; o pé no chão é apoio no cálculo, e o peso dos
degraus e a sobrecarga de uso entram pela tela de esforços. Pesos e sobrecargas de uso do mezanino e da passarela também.
No Posto CB: ESCADA 1 (E/F/G + pés CH8) e ESCADA 2 (1A/1B, A6–A8), patamar a 1,70 m, topo a 3,17 m; o pé da escada 1
dá 0,63 tf × 0,6 tf da locação. As peças da planta da escada que não são longarina nem degrau também entram (pedido do usuário:
"faltou um elemento de ligação dela com o mezanino"): a viga de chegada e a ligação dela até o pilar do mezanino (1,08 m
na escada 1), as vigas do meio do patamar e o piso de chapa xadrez (espessura pela nota dos cortes). **Base da caixa
d'água** (print do usuário, a VM P30 embaixo da treliça): na planta de piso acima da cobertura ("NIVEL 8,20") as
treliças ficam embaixo do nível, como os cortes mostram — a que recebe as VMs por cima com o topo no fundo delas
(7,40–8,00), as outras com o topo no nível (7,40–8,20); no esqueleto a viga que passa sobre um banzo ganha nó nele, e a
água da caixa desce pelas VMs embaixo do fundo dela (proporcional ao trecho dentro do círculo), não mais nos nós perto. **Pisantes**
(pedido do usuário): a chapa xadrez dobrada de cada degrau (# 2,65 dos cortes), entre as faces de dentro das longarinas,
com abas de 40 mm para baixo na frente e atrás; os pisantes de cada lance pelo comprimento dele e o passo, e um espelho a
mais que pisantes por lance — o **patamar de cada escada** pela cota do corte que confirma os espelhos iguais (a ESCADA 2
tem 8 + 10 pisantes, 20 espelhos: patamar a 1,421 m, a cota do corte FF; antes pegava o 1,70 da escada 1). **PERFIL 1**
(print do usuário, a cobertura da caixa d'água): a família "PERFIL" — peça de um perfil só, a elevação em linha dupla na
altura dele e a nota "PERFIL 1 2U100X40X2,65" dentro do desenho — vira viga 2U100 inclinada a 5% nas faces E e H, com o
topo de 10,64 a 11,00 junto do banzo de cima da TESOURA 38 e o dente da calha a 10,49. No editor, o **esqueleto** virou o
5º quadradinho dos modos de exibição (pedido do usuário). **Terças da planta de piso**: a cobertura da caixa desenha as
terças dela na própria planta 11,00 (camada "Terça Eixo", TC69/TC70) — cada eixo senta no topo das peças daquela planta
que cruza (PERFIL 1 nas faces, TESOURA 38 no meio), a emenda entre dois nomes no apoio do meio; as correntes, agulhas e
esticadores dela na altura das terças. **Agulhas** (camada "1-Agulha", AG1–AG6: barra redonda Ø 10 rosqueada, pelo
"DETALHE TÍPICO DAS AGULHAS"): a montagem só lia "corrente" e "esticador" — as 199 da cobertura principal ficavam de
fora; agora entram, com linha própria na conferência (204 no modelo × 239 na lista do projeto).

**Verificação dos perfis** (`nucleo3d/verificacao_perfis.py`, na tela de esforços; pedido do usuário "bora" para o passo
2 da frente): cada barra do esqueleto verificada em todas as combinações últimas pelas rotinas de `nucleo/verificar.py`
(U/Ue a frio pela NBR 14762 — MRD, interação linear —; laminados e cantoneiras pela NBR 8800; redonda só à tração),
com as resistências calculadas uma vez por perfil e comprimentos de flambagem. O momento é o das pontas mais o da barra
biapoiada com a carga dela (o cálculo guarda o momento de vão simples por caso: as cargas entram nos nós). Banzo em U
deitado: no plano da treliça flamba e flete no eixo fraco (conferência elástica W·fy/γ), fora dele no forte, com a
distância entre os nós travados (onde chega peça fora do plano); o cálculo também passou a dar a inércia fraca ao
banzo em U no plano vertical. Terça: gravidade com a mesa de cima travada pela telha. Alma em 2L: a compressão do par
(NBR 8800). O limite KL/r ≤ 200 à parte da resistência. Três cenários — só gravidade, vento de cpi −0,3, todas (cpi
+0,8) — com a pior razão de cada peça e o "3D" que a destaca. No esqueleto: a viga horizontal que cruza outra no mesmo
nível ganha nó ali (o barrote sobre a viga principal); alma rotulada disponível como opção (`alma_rotulada`). Na
montagem: a linha de terça sem nome TC não vira terça com perfil inventado — com o nome VM escrito ao longo dela, é
barrote (no mezanino do Posto, já lido pelas VMs; o repetido é pulado); sem nome, fica de fora com aviso. No Posto
(primeira passada): só gravidade 809 de 9.715 barras sem resistência, vento leve 975, todas 2.397 — com pontos do
esqueleto ainda a acertar (a copa do PM6, pontas das tesouras sobre os pilares, banzos de COMP 21 e TESOURA 18 com
150–290 kN de compressão, banzos com carga de terça fora do nó).


**Leva de 28/09 (pedidos do usuário).** **Vigas VM e curvas de canto pela planta**: o nome marca o pedaço pelo começo
do texto (cada vão com o seu nome vira uma viga, apoiada no pilar); os redondos do mezanino (tubo de 2U) entram
calandrados, com o nome escrito como chamada levado à peça onde a chamada termina. **Área de trabalho (2D, 3D, 2D + 3D)
com um menu só**, fixo em qualquer vista e projeto (`web/barra_unica.js`): Arquivo (com o IFC), Desenhos (Desenho +
Detalhamentos + Vistas), Estrutura (o antigo Lançamento, o projeto recebido, eixos, apoios, Explodir/Juntar), Cálculo e
Ver; setas de desfazer no lado mexido por último; Voltar; a barra se compacta quando a janela é estreita; o seletor da
vista em destaque; o completo é o primeiro desenho e é nele que o 2D abre; detalhar também abre no completo.
**Elevação da treliça no padrão do corte das tesouras do projetista** (`nucleo2d/detalhe/conjuntos.py`): cada barra
só com as bordas de fora; a alma pela linha de trabalho (montante no eixo, diagonal de nó a nó; a barra deitada ou em
pé fica no eixo dela, só até o cruzamento); as peças com o perfil do banzo ligadas a ele com contorno (a descida do
banzo no joelho, a horizontal e o montante da cumeeira), o banzo parando na face do montante; cotas para a produção
(água inteira nos dois banzos, nós do banzo de cima, cadeia horizontal de face a face sem a chapa de apoio que fecha
com a total, alturas das pontas e do montante da cumeeira, chanfro); ponta de cota em traço oblíquo por padrão. Em
volta da tesoura, o corte: as terças encostadas no contorno (de cima, da cumeeira e de parede) e a telha pelo perfil
inteiro (onda e crista), assentada nas terças, com o canto no raio comercial da multi-dobra (R450 int. / R490 ext.) e
os parafusos nos encostos. **Terça que veio do IFC sem o furo da ligação** ganha os furos da chapa de apoio encostada
nela (água gelada: o suporte CH1 com os oblongos, a terça sem nenhum); a regra de fábrica põe no padrão.
**Pranchas montadas à mão**: Desenhos → Inserir folha (prancha)… põe folhas com o carimbo no desenho de trabalho (várias
de uma vez), para mover ou copiar os detalhes para dentro; Gerar pranchas das folhas faz de cada uma uma prancha 1:1; e
**detalhar de novo mantém a montagem** — as folhas, o desenhado à mão e cada pedaço posto numa folha voltam no mesmo
lugar, já com o desenho novo (achado pelas linhas e textos que não mudaram). No tema escuro, a folha e o carimbo claros.
**3D**: Explodir peça em trechos (a dobrada do joelho, a quebrada em retas, o tirante com gancho: uma peça por trecho,
marca .1, .2…) e Juntar peças (os trechos voltam à peça; barras na mesma reta viram uma); balões dos eixos e cabeças
dos níveis com tamanho fixo na tela. **CAD**: o clique numa linha de desenho importado (DXF/PDF) não trava mais.
**0.8.47.** **A alma da treliça para na face interna do banzo** (`nucleo3d/alma_na_face.py`;
print do usuário: "as treliças e montantes não furarem os banzos"): o nó continua no eixo do banzo (o esqueleto e
as regras de apoio não mudam), e a peça termina antes — `recorte_inicio`/`recorte_fim` da barra, que o 3D, o IFC e o
Detalhar já descontam: a quina da ponta reta da cantoneira (ou do U) fica 10 mm fora da face do banzo, pela seção
girada de cada um (o caixão com os dois U; o banzo calandrado pelo eixo que o sólido varrido agora guarda em
`atributos.banzo`). Vale para os banzos do mesmo bloco e da outra parte da treliça montada em duas peças (a tesoura
de cima apoia no banzo da viga de transição); o banzo só conta se a ponta recortada ainda estiver sobre ele (o toco
do apoio). No Posto CB: 5.311 de 5.414 peças de alma recortadas (mediana ~10 cm; até ~40 cm nas diagonais quase
deitadas, a ~22° do banzo); as 103 restantes terminam em outra peça da alma ou no pilar. Peso 55,2 → 53,1 t (a alma
pelo comprimento de corte, não de eixo a eixo). **O pilar inclinado em quadro** (`pilares_corte`: `_pernas_na_frontal`,
`outra_placa`; print do usuário: "estruturalmente não faz sentido essa viga da frente estar nesse ponto"): o PM8 do
Posto CB é um quadro de duas pernas 2Ue 250×125 a 1,35 m de eixo a eixo, com três travessas (a vista frontal e o
"LOCAÇÃO DO CHUMBADOR PM8": duas placas CH7); a leitura tomava por vista frontal a seta "VISTA FRONTAL" dentro da
vista lateral (agora vale o rótulo de texto maior) e montava só a perna da placa com o rótulo — 1,5 m ao lado da
TRANSIÇÃO 16, solta. Agora a outra perna nasce na outra placa (no plano da TRANSIÇÃO 16, chega no nó com a
TRANSIÇÃO 1, como a "VISTA NO PILAR INCLINADO PM8" desenha) e as travessas ligam as duas (0,71; 6,82; 8,41 m);
pilar sem carga 2 → 0. A origem das peças do corte levava a quantidade do último corte lido ("PM8 - 3X"): agora a do
próprio corte. As duas Ue de cada perna (e das travessas) ficam de boca uma para a outra, formando o tubo, como o
banzo em caixão (print do usuário: "as bocas precisam estar viradas uma pra outra"); a travessa com a seção no plano
das pernas, de face a face delas. **A treliça que passa desenhada em corte na emenda** (`_limpar_emenda`; print do
usuário: "a transição 3 está estranha"): no vão da emenda TRANSIÇÃO 2 | 3 (e 5 | 6) a elevação desenha a TRANSIÇÃO 1
em corte — os lados dela entravam como montantes 2L soltos nas duas partes; agora saem, os U de ponta das tesouras de
cima (sobre a TRANSIÇÃO 1) ficam como U 200×100, e a ponta da viga da TRANSIÇÃO 3/6, que perdeu uma das linhas do U
para o lado da treliça em corte, ganha o U de ponta de volta.

**Esforços na estrutura inteira** (`nucleo3d/esforcos.py`, primeiro passo da frente de esforços): cada barra do
esqueleto é uma barra de pórtico espacial (12 graus de liberdade, nós rígidos, matriz esparsa pelo scipy — o Posto
CB tem ~29 mil graus e resolve em ~2 s), com os casos PP (kg/m do perfil), CP (telha, forro e painéis) e SC
(sobrecarga) chegando pelas terças, cada uma com a faixa até a meia distância das vizinhas. O pé do pilar é rotulado,
e engastado onde a locação dá momento; a parte sem caminho até um pilar fica de fora, com aviso. As reações saem
por pilar, ao lado das cargas que a locação escreve: a montagem pela planta agora lê embaixo do nome de cada pilar o
"7,0tf" ou o bloco "Fz/Fx/Fy/MX/My" (o bloco sem nome — a outra placa do PM8 — vai para a placa livre mais perto) e
grava em `metadados.de_planta.cargas_locacao` (82 blocos, 515,9 tf no Posto CB). O cálculo mostrou dois defeitos do
esqueleto, corrigidos: a ponta da treliça (fim do banzo, só com o montante da própria peça) não descia ao pilar a
8 cm dela — agora desce, levando as barras dela; e a terça com a corrente presa na ponta não descia mais ao banzo (a
ponta só conta como apoiada se chega nela uma peça em que ela apoia). **As folhas do projeto recebido**
(`nucleo2d/folhas_recebidas.py`; Desenho 2D → "Ler folhas e considerações de cálculo do DXF…"; rota
`projeto-recebido`): o espaço do papel do DXF (os layouts), que a importação não lia — número, título e formato de
cada folha, carimbo (cliente, obra, local, responsável, revisão), as considerações de cálculo (cargas em kgf/m² e o
vento), as normas e os materiais —, gravado no projeto em `projeto_recebido`; o cliente, o local e o responsável vêm
do carimbo quando estão vazios, e o cálculo de esforços parte dessas cargas (`esforcos.cargas_do_projeto`). No
Posto CB: 15 folhas, Maringá-PR, telha 5 / forro 15 / sobrecarga 25 / painéis 17 kgf/m², V0 45 m/s → 179 tf
característicos na cobertura (a locação soma 514 tf: faltam vento, mezanino e caixa d'água). **Pesquisa de peças**
pelo nome do projeto (TRANSIÇÃO 8, TESOURA 3B, PM6…), sem olhar acento, no 3D e na tela Treliças lidas; a caixa
MEDIDAS do Desenho 2D no tema escuro. **Terças no nível do telhado** (prints do usuário: "essas terças estão
erradas"): a tesoura de cima das elevações em duas peças (TRANSIÇÕES 2/3 e 5/6) é o frontão acima do telhado — o
corte BB do projeto desenha a telha reta embaixo dele e a nota "REVESTIR TRANSIÇÃO 2/3 COM TELHA OU RUFO" —, então a
terça senta no topo da viga de transição (`Elevacao.topo_telhado`); a transição na ponta da terça não dá altura a ela,
e onde uma tesoura comum também passa, a altura é a da tesoura. Trechos de terça inclinados ao longo do comprimento
27 → 5 (as linhas da cumeeira e das calhas subiam até 8,3 m na TRANSIÇÃO 1). **Sentido da treliça**: a decidida pelas
marcas ST que fica com o banzo de cima desencontrado da vizinha da mesma linha (> 150 mm) e, virada, se encontra com
ela (< 50 mm), vira, com aviso — a TESOURA 20 do Posto CB (3,5 m, marcas quase simétricas) começava baixa na
cumeeira. O modo desenvolvimento só se encerra sozinho depois de meia hora sem janela (`SILENCIO_DEV`; a página
pesada do projeto e a janela minimizada atrasavam o sinal de vida e ele saía em 30 s).

**0.8.46.** **Conferência seletiva antes de publicar** (`testes/selecao.py`, pedido do
usuário: a completa levava ~20 min a cada versão; "as demais obras já estão fechadas, em produção"): o pytest roda
sempre; os verificadores das telas, só os da tela que cada um testa (a primeira que abre) quando os arquivos dela
mudaram desde a última versão publicada (a navegação entre telas, `web/area.js`, chama quem passa por elas; os
arquivos comuns, todos; o servidor, a "fumaça": tela inicial, 2D, 3D, área de trabalho; a montagem 3D, as telas que
a mostram); a bateria das obras de detalhamento (IFC, em produção) só quando mudou o núcleo — e aí a conferência é
completa; a completa volta também a cada 4 versões e com `--completa`, e fica registrada em
`Projeto/bateria/ultima-completa.json`. Exemplos pelo histórico: o montante em U (de_planta) → 4 verificadores +
Posto; o seletor do desenho → 1 verificador; mudança só nas ferramentas de teste → só o pytest (1,4 min). **O Posto
CB na bateria** (`OBRAS_PLANTA`, `--so-planta`/`--sem-planta`): o desenho recebido congelado em
`Projeto/bateria/entradas/projeto-posto-cb/`, montado pela planta pelo caminho do programa (13 s) e fotografado —
quantidades, peso, cada treliça lida (quantidade, comprimento, barras, situação), encaixe, apoios por regra, esqueleto
e avisos. **Sentido da treliça pelo cruzamento na emenda** (print do usuário: "na TRANSIÇÃO 2 a viga
de transição 1 para no centro da tesoura e no 3D ela está passando na aba lateral"): onde outra treliça atravessa a linha
de uma na planta (a planta a interrompe ali), a elevação tem a junta dos banzos (a emenda) — só um sentido põe a junta
sobre o cruzamento, e ele vale antes do "encontro dos banzos" (`orientar`: `_juntas_dos_banzos`, `_cruzamentos`,
`pelo_cruzamento`). No Posto CB, as TRANSIÇÕES 2 e 5 estavam invertidas pelo encontro dos banzos: a cumeeira e a
emenda de 250 mm ficavam em y ≈ 16,6 m, e a TRANSIÇÃO 1 (y = 19,45 m, contínua na planta) atravessava a lateral da
tesoura; agora a emenda cai em 19,32–19,57 m, o espaço que a planta deixa na linha delas, e a TRANSIÇÃO 1 passa no
centro da tesoura. Terças fora do nó 125 → 121. As curvas de 90° nos cantos da planta (6, sem nome) ficam de fora: o
usuário confirmou que são um detalhe descontinuado. **Pilar no lugar que a planta estrutural desenha**
(`_pilares_pela_planta`; print do usuário: "deslocar um pouco para o lado"): quando a planta desenha a seção do pilar
(o retângulo com as medidas do perfil, ou os dois U costas com costas) a menos de 1,2 m do lugar da locação, vale a da
planta — é nela que as treliças apoiam —, com aviso e `origem.a_conferir`. No Posto CB, os três PM6 (a copa em cruz vai
junto) andaram 0,72 m para o cruzamento das treliças; encaixes justos 123 → 125, pilares fora do eixo 14 → 13.
**Elevação que desenha duas peças separada na emenda** (`_separar_nas_emendas`, `_dividir`): o nome da planta sem
elevação, na mesma linha de uma elevação com emenda, cujo pedaço na planta tem o comprimento de uma das partes, fica
com essa parte (quantidade = os rótulos da planta); a peça separada sabe qual ponta é a emenda, e essa ponta vai para
onde a outra treliça passa (`orientar`: "emenda na treliça que passa"). No Posto CB, a elevação "TRANSIÇÃO 2" (16,63 m)
vira TRANSIÇÃO 2 (9,61 m) + TRANSIÇÃO 3 (6,76 m, 2×), e a "TRANSIÇÃO 5", TRANSIÇÃO 5 + TRANSIÇÃO 6 — a segunda
TRANSIÇÃO 3 (x = 33,96) aparece. **Perfil de apoio das terças dos dois lados da treliça** (`_apoio_das_tercas`,
pedido do usuário: "na viga de transição 1 tem um perfil em ambos os lados para receber as terças"): a linha dupla
inclinada, no caimento do telhado, com a nota "U100X40X2,25 NO EIXO DA TRELIÇA" ao lado, era tirada como a tesoura
vista ao fundo; agora volta como `apoio_terca`, um U de cada lado com a alma na face do banzo e as abas para fora (12
barras na TRANSIÇÃO 1); o esqueleto os prende à treliça e as terças a eles (`analitico.APOIA_EM`). Terças em balanço
29 → 18, pontas soltas no esqueleto 45 → 17. **Camada de cada outra planta** (`camada_da_outra`, pedido do usuário:
"uma camada para as vigas do mezanino"): as vigas e treliças de uma outra planta vão para a camada dela — "Mezanino"
(abaixo do nível da planta estrutural, ou com MEZANINO no título), "Caixa d'água 8,20"/"11,00" (CX ou CAIXA no
título), senão "Nível x,xx"; `outras[i].camada` escolhe outro nome. No Posto CB: Mezanino 138 vigas, caixa d'água
20 + 12, nível 6,00 fica com 50 na camada "Vigas". A copa em cruz e as mãos-francesas MF1 do PM6 vão com o
pilar, na camada "Pilares" (pedido do usuário: "colocar esses elementos no mesmo grupo dos pilares"), com o papel
de treliça (banzo/montante/diagonal) para o esqueleto e as regras de apoio.

**0.8.45.** **Área de trabalho do projeto** (`/dividida?projeto=…&vista=2d|3d|ambos`, pedido do
usuário: "a transição entre 2D, 3D e 2D+3D muda o menu superior… e ao sair do 2D para o 3D ele renderiza o modelo todas
as vezes, carrega um modelo antigo e depois o correto"): o 2D e o 3D são vistas da mesma tela, com o seletor
[2D | 3D | 2D + 3D] numa barra só; trocar de vista mostra ou esconde o quadro — o 3D de milhares de peças é montado uma
vez (antes, cada troca abria a outra tela do zero: 5–7 s de tela travada, com o modelo pela metade à vista). Cada
quadro carrega na primeira vez que aparece. A tela inicial abre os projetos na área (na vista de antes: o desenho no
2D, o IFC e o lançado no 3D); a tela sozinha (/cad, /editor) ganha o mesmo seletor no começo da barra, no lugar de
"Modelo 3D", "2D + 3D" e "← Desenho 2D". `web/area.js`: dentro da área, as idas de uma tela à outra ("Abrir o modelo
3D" depois de montar pela planta, "Lançar estrutura", "Abrir no 3D" do detalhe) viram troca de vista e recarregam só o
lado que mudou; o que não é 2D nem 3D (materiais, análise, memorial) sai da área. Barras sem quebra de linha e mais
enxutas na metade da tela (o nome da tela só no ícone, busca que encolhe, Tema/Escala/Fechar escondidos). O 2D
escondido não pinta (canvas de tamanho zero). **Montante de ponta em U** gira pela largura desenhada (a aba: alma
atravessada, abas para o meio da treliça — a ponta do caixão da TRANSIÇÃO 1) e pela direção da treliça. **Seletor do
desenho** da tela dividida no padrão escuro. **Painéis da direita recolhíveis** (Propriedades, Camadas, Snap… no 2D;
Propriedades, Camadas, Materiais… no 3D): a aba na borda do painel, Ver → Esconder os painéis laterais e F4, em cada
tela; na área de trabalho, o botão "Painéis" da barra de fora esconde ou mostra os dois lados. A escolha fica guardada
por tela (e à parte dentro da área, onde o espaço é metade); sem escolha, a janela estreita (< 900 px) começa sem eles. **Uma linha só** (pedido do usuário: "pode unir isso tudo em uma linha apenas"): a
barra de fora da área de trabalho saiu; o seletor [2D | 3D | 2D + 3D] mora na barra de cada tela, também dentro da
área (ele pede a troca por postMessage), e na vista 2D + 3D a barra do 2D ganha a ligação (🔗 seguir a seleção,
planta / elevação, ⇄ trocar os lados). Na metade da área, a barra do 3D encolhe para caber (a busca vira lupa, o
Salvar fica no sinal, "Projetos" vira ⌂, a perspectiva fica na vista 3D cheia) e o 2D tira o Exportar DXF (continua no
menu Desenho). O atributo do seletor é `data-vista-area`: `data-vista` é dos itens de "Vistas do modelo" do 2D, e o
clique no seletor chegava a pedir uma vista "3d" ao servidor.

**0.8.44.** **Tela dividida 2D + 3D** (`/dividida?projeto=…`, `web/dividida.html`/`.js`,
`web/editor3d/modulos/divisao.js`; pedido do usuário: "dividir a visualização entre 2D e 3D no mesmo quadro, vai
facilitar muito a conferência"): o Desenho 2D e o modelo 3D do projeto lado a lado, cada um a própria tela num quadro,
com a divisória arrastável, trocar os lados e "seguir a seleção". 3D → 2D: a caixa em planta do que se escolheu vira
a região marcada (retângulo laranja) na planta do desenho — o modelo é o desenho + o deslocamento que a montagem pela
planta agora grava em `projeto.json` (`planta_modelo`) —, ou, no modo "a elevação", a moldura da elevação da treliça
escolhida (`caixa_desenho` da tela Treliças lidas). 2D → 3D: o que se escolhe dentro da moldura de uma elevação
seleciona o bloco dela (todas as cópias); na planta, as peças da região (e o bloco de cada uma). As telas conversam
por postMessage (mesma origem); dentro da divisão a navegação de cada lado some (`html.embutida`). Abre por Ver →
Dividir com o 2D (3D), pelo "2D + 3D" do Desenho 2D e da tela Treliças lidas. Verificador `verif_dividida_ui`.
**Leitura das elevações** (prints do usuário no Posto CB): *alma desenhada duas vezes* — a 2L com linha dupla de nó a
nó e mais uma linha ao lado virava duas barras (e a linha dupla ganhava o perfil do banzo: um Ue 250 no meio de cada
2L da TRANSIÇÃO 1); agora a linha dupla da alma só é do perfil do banzo quando a largura dela é a do banzo (o montante
de ponta em U), e barras paralelas a menos de 30 mm (ou a linha simples a menos de 70 mm da dupla) entram uma vez —
os pares de verdade (os montantes da cumeeira, a 150 mm) ficam; *banzo em caixão* — "BANZO 2Ue 250X70X25X4,75" com
três linhas compridas por caixão vira um banzo só, no eixo da junta, montado com os dois Ue boca com boca (±51 mm,
abas para baixo em cima e para cima embaixo); *elevação em duas partes* — o desenho sem título logo à direita, com a
mesma altura e um espaço de até 60 cm, é a mesma peça (a TRANSIÇÃO 16: 12,12 + 0,27 + 19,73 = 32,12 m, a linha
inclinada inteira da planta; a TRELIÇA 1 deitada: 3,12 + 0,25 + 20,80 = 24,17 m, a passarela inteira), com os banzos
ligados na emenda e aviso; e a faixa deitada da planta em dois pedaços com um espaço pequeno é uma treliça só. No
Posto: pontas de treliça sem apoio 4 → 0, a TRANSIÇÃO 14 deixa de ser "pode ser deitada" (a faixa é a TRELIÇA 1).
O Verificar apoios não cobra ponta de treliça deitada (ela se liga ao longo). Os nomes da planta sem elevação no
desenho (TRANSIÇÃO 3 e 6) aparecem na tela Treliças lidas, com onde estão escritos. **Arquivar projeto** (tela
inicial): tira da lista principal sem apagar nem mover nada (marca `arquivado` no projeto.json, a data de alteração
fica); os arquivados ficam numa seção recolhida no fim da lista, com Desarquivar. **Botão Salvar no 3D**: ao lado do
nome do modelo, com o estado da gravação automática ("✓ Salvo 10:42", "● Salvar" com mudança por gravar,
"Salvando…", "⚠ Salvar" quando falhou); clicar ou Ctrl+S grava na hora. **Janelas repetidas**: a janela minimizada
tem o sinal de vida freado pelo navegador (um por minuto), e a espera de 10 s abria outra a cada atualização e a cada
reinício do vigia do desenvolvimento; agora a atualização espera 70 s e o reinício do vigia não abre janela.

**0.8.43.** **Modo de desenvolvimento** (`dev.py`, `app.py --dev`, atalho "Metálica
(desenvolvimento)"): porta 8766, os mesmos projetos do instalado, faixa laranja e "[DEV]" no título, sem oferta de
atualização, reinício automático ao mudar um `.py` (o vigia passa `--reaberto`, e o servidor espera a janela que já
está aberta em vez de abrir outra), rótulo "código novo — recarregar (F5)" quando js/html/css mudam no disco
(`/api/versao` traz `dev` e o carimbo `codigo`); verificador `verif_dev_ui`. **Conferência em paralelo**:
`rodar_verificadores.py` roda N verificadores de cada vez (`--paralelo N`, `--serie`), os mais demorados primeiro
(`_duracoes.json`), trava por porta fixa (8781/8783/8784/8787 aparecem duas vezes) e repete em série o que falhou;
`antes_de_publicar.py` roda o pytest com `-n` quando há pytest-xdist (200 s → 93 s). A placa de vídeo no Chrome sem
janela não ajudou (medido nos verificadores pesados): fica o desenho por software. **Pilares com corte próprio**
(`nucleo3d/pilares_corte.py`): o título "PMn - kX" com as vistas rotuladas acima dá a forma do pilar — o aglomerado
de linhas estruturais acima de cada rótulo (varredura em grade), o pilar pelas linhas compridas paralelas
(inclinação, comprimento, largura), a copa pelos banzos que passam sobre o eixo logo acima do topo (uma altura só,
ou treliça), os braços pela vista superior, a mão-francesa pelos segmentos desenhados entre o pilar e a ponta do
braço (linha dupla da cantoneira numa só), os perfis pelas notas BANZO/DIAG-MONT. No Posto CB: PM6 (3×) vira pilar
com viga em cruz de ±2,06 m em 5,93–5,97 m e 4 MF1 treliçadas; PM8 vira o perfil duplo inclinado a 50,9° (10,96 m)
no sentido do lado comprido da placa de base, para o lado da estrutura mais perto — chega ao nível 6,00 na borda da
passarela e segue até 8,51 m sem nada em cima (o Verificar apoios aponta; é do projeto). Tudo o que precisou de
escolha fica em `origem.a_conferir`, e os cortes usados entram no quadro do projeto. (Os ângulos do arco no desenho
são `inicio`/`fim`, em graus — com `ini` o arco virava um círculo de cordas fantasmas.) No modelo analítico, a alma
liga também em pilar e viga (a mão-francesa termina na face do pilar), e a alma da mesma peça aceita a tolerância
normal. **Registro de lentidão** (`web/lentidao.js`, `POST /api/lento`): a janela conta ao servidor cada tarefa que
a segurou por mais de meio segundo (PerformanceObserver de longtask) e cada erro de JavaScript, com a tela, a
ferramenta ativa e o número de objetos; vai por sendBeacon e fica no metalica.log como "[lento] …" — para achar o
travamento da cota no desenho de 77 mil objetos, que ninguém reproduziu. **Verificar apoios — ponta de treliça
ligada em diagonal** (regra B3 do Guia básico): a ponta que só toca a alma (montante, diagonal) de outra treliça, a
mais de 20 cm de um nó dela, é apontada ("ponta_em_diagonal"); e a vizinhança da ponta passou a ser medida na
própria ponta, não no elemento inteiro — o banzo comprido tocava um pilar lá longe e a ponta contava como apoiada
(no Posto CB, 4 pontas sem apoio de verdade apareceram: PAINEL 14, TESOURA 20, TRANSIÇÃO 16 e a TRELIÇA 1
deitada). A copa do pilar em árvore fica fora das regras de ponta (é apoio, não apoiada). O nome da peça nos
achados vem da treliça de origem antes do perfil. **Decisões gravadas** (0.8.42) valem ao montar de novo.

**Verificar apoios — as regras que faltavam do Guia básico.** D3: o pilar fica na linha de alguma peça que ele
carrega ("pilar_fora_da_linha", > 15 cm) e, com os eixos do projeto, em cima do eixo de que está perto
("pilar_fora_do_eixo", de 10 a 60 cm — no Posto CB, 14, entre eles PM3/PM4 a 35 cm do eixo 4; é locação a conferir
com o projetista). B4: uma treliça não passa por dentro da outra — o banzo dela entre os banzos da outra, com 15 cm
de folga dos dois lados, longe das pontas ("trelica_dentro"; empilhada banzo com banzo não conta). A3: as treliças
ligadas pelas terças formam um plano de telhado, que precisa de ao menos um contravento ("plano_sem_contravento";
o resumo diz planos e planos travados). O editor manda os eixos da referência junto, e cada achado diz onde fica na
malha ("eixo 7 / entre J e K"; `nucleo3d.eixos.onde`). **Avisos da montagem pelos eixos**: o "(x; y)" em mm do
desenho vira "(eixo 13 / entre A e B — 50,17; 53,19 m)", na coordenada do modelo, e os metros e graus saem com
vírgula. **Encaixe dos blocos**: cada treliça entra como a elevação desenha (sem esticar); a montagem mede a
elevação contra o vão na planta (`encaixe` no resultado, `origem.encaixe` em cada barra) e o que passa de 20 cm
vira aviso — no Posto CB, 122 de 162 com até 5 cm, 5 a conferir (COMP 25 com 0,44 m a menos no vão, TRANSIÇÃO 14,
PAINEL 12, PAINEL 1, PAINEL 8). O diálogo da montagem diz o encaixe e mostra todos os avisos; o painel do bloco no
3D diz "a elevação mede … e o vão …". **Balões encostados**: um texto por balão, do par mais perto para o mais
longe — os eixos 9 e 10 do Posto CB (balões a 51 cm) caíam os dois na mesma linha. **Tela Treliças lidas**
(`/trelicas?projeto=…`, `web/trelicas.html`/`.js`, `nucleo3d/trelicas_lidas.py`, `GET /api/projetos/<s>/trelicas`): cada
elevação do projeto recebido ao lado do bloco que a montagem leu dela — o desenho do projetista (tudo o que está na
moldura: linhas, arcos, textos, cotas; sem o título da elevação vizinha) e as barras lidas no mesmo referencial (s ao
longo do banzo inferior, h acima dele), lado a lado ou uma sobre a outra; o título × o modelo; e cada cópia colocada,
pelos eixos, com o encaixe no vão e o atalho "ver no 3D" (`/editor?destacar=peca:TESOURA 16#12`, ou pelo nome para
todas as cópias). O índice marca em laranja o que tem algo a conferir (quantidade diferente do título, cópia com mais de
20 cm de diferença, elevação que não entrou, sem nota do banzo). A montagem pela planta grava `trelicas-lidas.json` no
projeto; a tela abre pelo diálogo da montagem, por Ver → Treliças lidas… no 3D e pelo painel do bloco ("Ver a
elevação … do projeto"). No Posto CB: 122 elevações, 7 a conferir — além dos 5 encaixes, PAINEL 4 (o título pede 2, a
planta tem 1) e TESOURA 1A (o nome não aparece na planta). Verificador `verif_trelicas_ui`.

**0.8.42.** **O elemento treliçado é um bloco** (pedido do usuário: "selecionar uma tesoura e toda ela se
selecionar, para ver como estão se ligando, de onde até onde"; vale para tesoura, transição, painel, treliça,
COMP): no editor 3D o clique pega o bloco inteiro — as barras de mesma peça de origem — e Alt+clique pega uma
barra só (a convenção do Desenho 2D), em qualquer modo (`modulos/bloco.js`, `selecao.grupoDe`). Com um bloco
selecionado, o painel do bloco diz as barras, o comprimento, a altura e, para cada ponta, onde ela está (com os
eixos mais perto) e no que encosta — pilar, outra treliça, viga; "nada encosta" em vermelho —, com essas peças em
destaque; clicar numa vizinha passa a seleção para ela. **Decisões do projeto gravadas**: `deitadas` e
`duas_pecas` ficam em `decisoes_planta` do projeto; montar de novo pela planta, do zero, as mantém. **Elevação em
duas peças** (`duas_pecas`, confirmado pelo usuário nas TRANSIÇÕES 2 e 5 do Posto CB): a viga de transição embaixo
e a tesoura em cima dela, dois blocos na mesma linha; a barra que atravessa é cortada no banzo do meio. Os avisos
de cada elevação usada (vista de fundo tirada, duas peças) passam para os avisos da montagem.

**0.8.41.** **Esqueleto analítico** (pedido do usuário: "olhando só as linhas quase todas estão desconectadas;
as duplas podem virar uma linha só"): `nucleo3d/analitico.py` e `POST /api/modelo/analitico` montam o modelo de nós
e barras — o perfil duplo (cantoneira dupla, viga 2Ue) numa barra só, as pontas a menos de 6 cm no mesmo nó, a
ponta solta levada ao eixo em que apoia (terça no banzo, viga no pilar, corrente na terça, alma no meio de outra
alma do painel subdividido…, até 45 cm — a excentricidade física volta no detalhamento), a terça com um nó em cada
banzo que cruza; o que sobra sem ligar é ponta solta. Ver → Esqueleto desenha esse modelo, com as pontas soltas em
vermelho (peça importada do IFC entra pelo eixo, sem alarme). No Posto CB: 7.018 barras em 5.127 nós, 2.486 duplos,
30 pontas soltas (todas erros reais). **Montagem pela planta, pelos casos do Posto CB**: corrente e esticador na
altura da terça que ligam (antes, da treliça mais alta ali — a transição levava a corrente a 1 m da terça); a
emenda entre duas terças fica num apoio ENTRE os dois nomes, e sem apoio ali fica onde o projetista separou (o
meio) e vira aviso — não mais levada além do nome da outra terça; o perfil da terça vem do nome da própria linha
(o da linha vizinha dava TC19 num pedaço da TC2A); a elevação que desenha a tesoura de trás e as chapinhas dos nós
(TRANSIÇÃO 1) fica só com os dois banzos e a alma (`_tirar_vista_de_fundo`, só quando há várias inclinadas por
dentro e muitas chapinhas; as outras 121 elevações ficam iguais); a transição/painel que barra a terça não dá a
altura da ponta dela; `deitadas` aceita a lista das treliças deitadas confirmadas. **Verificar apoios**: a altura
do banzo no cruzamento é medida no ponto (não só nas pontas das barras) — com o banzo comprido a terça que encosta
de lado contava como sentada (no Posto, 159 → 125 terças fora do nó).

**0.8.40.** **Ver → Esqueleto (só linhas)** no editor 3D (pedido do usuário: ver a estrutura antes dos perfis; é o
modelo do cálculo de esforços, e o detalhamento só vem depois que ele estiver estruturalmente certo). Cada peça
vira o eixo dela, numa cor por tipo (treliça, terça, contravento, corrente, pilar, viga); a calandrada é a polilinha
pelos centros dos anéis da varredura (a tampa diz quantos pontos tem o anel) e outro sólido, a maior dimensão dele.
Tudo num objeto só (`nucleo/esqueleto.js`), leve no modelo grande; o modelo com perfis fica escondido enquanto o
esqueleto está ligado. O clique pega o bloco — a treliça inteira, pelas barras de mesma peça de origem
(`selecao.grupoDe`) — e a dica diz o nome dela; o raio acha a linha pelo índice do vértice (`entidadeDe` recebe o
índice da face ou, na linha, o do vértice). Verificador `verif_esqueleto_ui`.

**0.8.39.** Terceira leva de prints do Posto CB. **Eixos e níveis no tema escuro**: o balão do eixo tinha
fundo branco e ofuscava; agora cada tema tem as suas cores (no escuro, o fundo da cena e o traço mais claro;
níveis em azul claro), redesenhados ao trocar o tema. **Viga repetida**: a viga lida de novo (o nome em duas
linhas da mesma peça) não entra duas vezes (`_viga_repetida`: mesmo perfil e nível, na mesma linha, cobrindo
90 %). **Verificar apoios — canto de vigas no ar**: duas vigas que só se tocam pelas pontas, em ângulo, longe
de pilar (mais de 90 cm), não se apoiam uma na outra; a viga que apoia no meio da outra, e a que chega numa
linha partida no cruzamento (a viga contínua), continuam apoiadas. **Treliça deitada, a conferir**: a faixa em
que a planta desenha a treliça vista de cima (os dois banzos e a alma entre eles) é achada
(`_trelicas_deitadas`, medindo tudo no mesmo referencial — o desenho fica a 400 m do zero e 0,1° ali vira 70
cm) e o nome da elevação de mesma altura e comprimento é apontado nos avisos; só vira treliça deitada com o
parâmetro `deitadas` (no Posto CB a faixa ao lado da TRANSIÇÃO 14 ficou a conferir com o usuário).

**0.8.38.** Montar o 3D pela planta, pelos prints do Posto CB: **banzo com as abas para dentro da treliça** — o U
do banzo de cima fica com a alma em cima (onde a terça apoia) e as abas para baixo, o de baixo com as abas para
cima (antes os dois saíam com as abas para cima, rotação 90; agora 270 no de cima). Cima ou baixo pelo meio da
altura da treliça, a mesma regra do banzo calandrado. **Viga até o pilar**: a ponta da viga que para antes de um
pilar na linha dela (até 50 cm antes, pilar a até 25 cm da linha) vai até a face do pilar (`_viga_ate_o_pilar`);
a que já encosta fica como está, e o pilar mais de lado que isso é do desenho, para conferir.

**0.8.37.** 3D: os eixos da obra (tracejado vermelho), o contorno dos níveis (tracejado azul) e as direções
X/Y/Z ficam apagados, só de referência — no Posto CB eles disputavam com a estrutura (pedido do usuário). Os
balões e as cabeças de nível continuam legíveis. Verificar apoios: peça sem nome não deixa mais espaço duplo no
texto do achado.

**0.8.36.** Montar o 3D pela planta: **as regras de apoio** (pedido do usuário com os prints do 3D do Posto CB: "não
pode ter elemento voando; tesoura apoiada em pilar; terça apoiada nos nós"). Leitura: a linha dupla interrompida onde
outra peça cruza volta a ser uma linha só **antes** de emendar os arcos (o arco da borda levava junto o pedaço reto de
outra peça); o trecho de cada nome é escolhido **entre dois nós** (cruzamentos, pontas encostadas, emendas de arco com
reta, pilares) com o comprimento da elevação e o nome dentro (`_escolher_trechos`), em vez de centrado no nome — o nome
fica muitas vezes perto de uma ponta, e o tamanho do texto no arquivo depende da escala de impressão (o meio do nome
não passa de 35 % da peça); o arco que o projetista esticou além da tangência emenda na reta; viga VM segue pelos
pedaços da mesma linha sem nome (interrompida no pilar) e o nome escrito duas vezes dá uma viga só. Terças: começam e
terminam num apoio (aparadas até 1,5 m, esticadas até 1 m; na face do painel e da transição, no eixo das outras
treliças — `_pontas_da_terca`), a emenda é sempre em cima de um apoio, painel e transição no meio da linha são
barreira, a terça deitada ao longo da transição tem apoio contínuo, a altura segue os apoios vizinhos e a transição
alta perto da ponta não tira mais as tesouras certas. Treliças: a elevação entra sem esticar, e anda até os nós
caírem nas linhas das terças (`ajustar_aos_nos`, mediana dos desencontros quando concordam, até 300 mm). No posto:
comprimento diferente da elevação 36 → 4, pontas de treliça sem apoio 35 → 2 (a passarela, que não entrou), terças
em balanço 120 → 20, TRANSIÇÃO 1 duplicada saiu, 54,9 t. **Ver → Verificar apoios…** no editor 3D
(`nucleo3d/apoios.py`, rota `POST /api/modelo/apoios`): peça voando (o que não chega à base seguindo o que encosta),
ponta de treliça sem apoio (pela marca `origem.peca` que a montagem agora grava), terça em balanço e fora do nó (só a
que senta em cima; o par da cumeeira fica a ~150 mm e passa), pilar sem carga, viga sem apoio; clicar no achado
seleciona e enquadra as peças. Sólido importado entra como cápsula (eixo + meia seção). Verificador:
`testes/verificadores/verif_apoios_ui.py`; testes em `test_apoios.py` e `test_de_planta.py`.

**0.8.35.** Montar o 3D pela planta: **o resto da estrutura**. O diálogo lista as outras plantas com nível no título
("PLANTA NO NÍVEL 3,17m", "PLANTA DA BASE DA CX DÁGUA NIVEL 8,20", "COBERTURA DA CX DÁGUA NIVEL 11,00"), com o nível ao
lado; cada uma é alinhada à planta estrutural pelos balões dos eixos de mesmo nome e entra no nível dela — vigas VM com o
topo no nível, treliças nomeadas com o banzo inferior nele (`parametros.outras`). O **pilar sobe até a peça mais alta
que passa em cima dele** (no posto: 64 até 6,00, 12 até 11,00 na torre da caixa d'água, 2 até 8,20, 1 até 3,17). A
moldura de cada planta ficou mais esperta: o título pode ficar até 5 m ao lado do desenho, as partes a até 12 m se
juntam, o grupo que tem outro título logo embaixo (a vista empilhada ao lado) não entra, e a moldura da folha (retângulo
de poucas linhas em volta de várias vistas) é ignorada — era ela que levava a caixa d'água a engolir os cortes. No
posto: mezanino com 89 peças, base da caixa com 23, cobertura com as treliças 7 a 15 (as quantidades batem com os
títulos), 55,0 t; ficam de fora a passarela e os painéis solares (desenhados de outro jeito). Também: o arco grande
cujo centro cai fora da planta (a curva em S da borda) agora entra (o filtro olhava o centro, não o arco), e a treliça
cuja linha dupla foi interrompida onde outra peça cruza segue pelos trechos na mesma linha até o comprimento da
elevação (`_estender_na_linha`). No posto: 59,0 t; conferência dos títulos com 3 diferenças.

**0.8.34.** (1) **Seção certa no 3D para qualquer perfil do catálogo**: em modelo grande (modo lote) o editor monta as
seções no navegador com o banco básico, e perfil fora dele (dobrado de fábrica "(FF)", barra redonda, perfis dos
fornecedores) saía com a seção padrão de 100 × 200 mm — no posto, 18 dos 23 perfis, e os contraventos de Ø12,5
pareciam perfis grandes. O editor agora pede ao servidor a seção e a massa dos que faltam (`POST /api/modelo/perfis`,
`Cena.acrescentarPerfis`) e refaz essas barras. (2) **Quadro do projeto considerado**: a montagem pela planta desenha,
no próprio desenho e abaixo de tudo, o quadro "PROJETO CONSIDERADO NO MODELO 3D" com só o que virou peça — a planta
estrutural, a das terças e a locação (com os eixos) e cada elevação usada, cada uma na sua moldura, em camadas
QUADRO … (que a montagem seguinte ignora e refaz); o CAD recarrega o desenho e o botão "Ver o quadro no desenho"
enquadra. Cada peça guarda de que entidades do desenho saiu (`Caminho.fontes`, `Elevacao.fontes`). (3) **Eixos e
níveis no 3D, como no Revit**: a montagem grava no projeto os eixos lidos dos balões da planta (numerados e com letra;
os inclinados em `extras`) e os níveis (base, banzo inferior e os escritos nos títulos: "NÍVEL 3,17", "NIVEL 8,20"…);
o 3D mostra os eixos com o balão nas duas pontas e cada nível como um contorno tracejado com a cabeça (triângulo,
nome e cota); Ver → Arquitetônico, eixos e níveis liga e desliga.

**0.8.33.** Montar o 3D pela planta: o modelo vem para perto da origem. A planta do Posto CB está a 400 m do zero do
DXF e o modelo abria pequeno no fim de uma malha enorme (a malha do chão vai do zero até o modelo); agora o canto da
planta vai para o zero, em metros redondos, e o deslocamento fica em `metadados.de_planta.deslocamento` (e no resumo)
para voltar às coordenadas do desenho.

**0.8.32.** **Montar o 3D pela planta** (projeto recebido sem 3D; pedido do usuário com o projeto do Posto CB, um DXF
de 30 MB sem limpeza, com a cobertura de forma livre de um posto, mezaninos, caixa d'água e passarela). No CAD,
**Desenho → Montar o 3D pela planta (projeto recebido)…** (`nucleo3d/de_planta.py`, rota
`POST /api/projetos/<s>/desenhos/<nome>/montar-pela-planta`). O diálogo pergunta só quais são as plantas, pelos títulos
do desenho (planta estrutural, locação, planta das terças), e o nível do banzo inferior. O que ele faz: (1) lê cada
**elevação** pelo título "FAMÍLIA n - kX" (TESOURA, PAINEL, TRANSIÇÃO, TRELIÇA, COMP; "COMP.10 2X" também): banzo em
linha dupla, montantes e diagonais em linha simples, a nota dos perfis entre o desenho e o título ("BANZO U100X40X2,25",
"DIAGONAIS E MONTANTES 2L 1"X1/8" 3 PRESILHAS…" → cantoneira dupla) e as marcas "ST" de apoio de terça, seguindo a
linha de chamada até o apoio; (2) na **planta estrutural**, acha a linha de centro de cada peça desenhada pela largura
(duas linhas paralelas, dois arcos, ou a borda curva feita de arcos e retas emendados na mesma tangente) e liga o
nome escrito a ela; a linha comprida com vários nomes é cortada no comprimento de cada elevação, encostando as pontas
nos nós, e o nome repetido na mesma peça (a transição de 36 m) conta uma vez quando a planta tem mais nomes do que o
título pede; (3) põe cada treliça em pé na sua linha, com o banzo inferior no nível; o **sentido** (qual ponta da
elevação vai em qual ponta da planta) sai das marcas ST — no sentido certo elas caem onde as linhas de terça cruzam a
treliça, com a mesma distância do texto ao apoio em todo o desenho —, senão do encontro dos banzos superiores, senão do
costume do desenho; (4) o banzo na borda curva sai **calandrado**, um sólido varrido com um anel a cada ~3° (como o IFC
do TecnoMETAL); (5) **pilares** da locação: o nome "PM3(200X70X20X2,65)" casado com a placa de base pelo deslocamento
típico nome–placa, alinhados à planta pelos **balões dos eixos** de mesmo nome (28 balões concordam no posto); pilar sem
peça da cobertura em cima (mezanino) é avisado; (6) **terças** da planta das terças (camada da linha de eixo da terça),
uma por nome TC, cortadas no apoio entre dois nomes, com o perfil da lista "TC13-U100X40X2,65 - 56X", sentadas no banzo
superior das treliças da cobertura (a testeira, PAINEL, e o apoio que foge mais de 400 mm da reta dos
vizinhos — a transição que sobe acima do telhado — não são apoio); correntes, esticadores e contraventos na altura da cobertura; vigas VM em perfil duplo. O resultado confere as
quantidades com o que o próprio projeto pede. No Posto CB: 150 treliças (4 tipos diferentes do título, por nome que
falta ou sobra na planta), 79 de 79 pilares, 430 terças (427 nomes na planta; a lista pede 450), 90 de 90
contraventos, 26 peças calandradas, 44,7 t, em 15 s; o Detalhar roda sobre o modelo (6.249 peças). Também: o
reconhecedor lê a cantoneira dupla antes das presilhas e o perfil entre parênteses da sigla ("PM3(200X70X20X2,65)" →
Ue, pilar); o "Aço estimado" do painel do 3D soma o peso gravado nas peças de perfil que o editor não traz (dobrados de
fábrica). Testes em `testes/test_de_planta.py` (projeto sintético com o mesmo desenho).

**0.8.31.** Ensaio geral de um projeto do zero até a entrega (pedido do usuário para começar o dia seguinte com um
projeto novo): 19 etapas pelo caminho do servidor — criar, arquitetônico, malha, eixos, lançar, memorial do lançamento,
Calcular estrutura, memorial por peça, Dimensionar, Detalhar, lista, PDF da lista, plano de corte, resumos da obra,
pranchas A1 com carimbo, PDF das pranchas, IFC e DXF —, tesoura treliçada (42 s de processamento) e alma cheia (25 s). O
que o ensaio corrigiu: (1) **texto sobreposto**, medido pela caixa do miolo das letras em cada PDF: o título "SEÇÃO" da
barra fina (13 a 25 mm) caía no número da cota vertical, que não cabe ao lado e sobe (`celulas.py`); o título da planta de
localização ficava a distância fixa das peças e a bolinha do primeiro eixo (1,5 m além delas) caía nele — agora vai abaixo
do ponto mais baixo desenhado (`conjuntos.py`); na prancha, a célula vizinha era posta em cima das chamadas de parafuso,
porque a caixa da chamada não contava a largura do texto (`pranchas._caixa_de`); na figura da tesoura do memorial do
galpão, os rótulos do banzo e dos montantes se encontravam junto dos nós — agora cada rótulo procura um lugar livre (outro
lado, mais para uma ponta); na paginação das telhas, o nome da chapa emendada no comprimento caía na
cota da chapa de baixo (agora fica dentro da própria chapa, do outro lado da linha de cota), a telha em camada (duas
chapas no mesmo lugar do modelo) tem a cota e o nome deslocados para o lado, e as cotas da largura útil e total descem
abaixo do nome mais longo da face; na chapa curta demais para o número da cota, o título da face sobe acima dele
(`telhas.py`; nas três obras da Sooro, a paginação das telhas foi de 430 textos cruzados para 2). (2) **Dimensionar em projeto lançado pede confirmação**: o Dimensionar do modelo 3D analisa a
tesoura isolada, apoiada no topo dos pilares, e no ensaio aliviava os banzos pela metade (banzo inferior de Ue
150×75×20×4,75 para U 100×50×2,25, −730 kg) contra o pórtico inteiro do lançamento, que o deixa a 95 %; até os dois
cálculos serem conciliados com casos de referência, a troca de perfil em projeto lançado avisa e pede confirmação. (3)
Pórtico de alma cheia lançado: o Calcular estrutura e o Dimensionar do modelo 3D dizem que o cálculo que vale é o do
lançamento (antes mandavam "gerar o detalhamento"). (4) **Excluir desenho insistente**: a conferência completa
pegou, uma vez em algumas rodadas, erro 500 ao excluir um desenho logo depois de o 3D pedir a lista (o Windows ainda
segurava o arquivo); a ida para a lixeira agora tenta de novo por alguns segundos, como a gravação já fazia
(`projetos.excluir_desenho`). Análise para o dia seguinte em `Projeto/Analise-geral-2026-09-26.pdf`.

**0.8.30.** **Ligações e acessórios** (pedido do usuário: "a tela de todas as ligações, começando pelas peças da
Sooro"). (1) **Biblioteca** (`nucleo/acessorios.py`): 23 tipos em 7 categorias — terças (cadeirinha, chapa simples,
cantoneira, emenda por transpasse), correntes (agulhamento rígido, agulhamento diagonal com gancho, corrente roscada),
contraventamento (tirante com castanha e barra roscada, tirante com esticador, gusset), apoios e bases (apoio da
tesoura em pilar de concreto, placa de base rotulada e engastada, tesoura no topo do pilar metálico, console),
tesoura e pórtico (nó soldado, emenda de banzo, chapa de topo do joelho, ligação flexível), fechamento (fixação da
telha) e fixadores (chumbador em J, com placa de ancoragem, tabela de resistências dos parafusos). Cada tipo tem os
parâmetros (padrões tirados das obras da Sooro, onde há: cadeirinha 150×145×4,75 com 4 oblongos e base 153×44×3,
castanha 200×76×6,35 com chapas-arruela 80×80×8, apoio 400×120×12,7 com chumbador 3/4" de 996 mm), as peças com
furos, quantidade e peso, o desenho em SVG com cotas, furos, oblongos e solda (classes de estilo: acompanha o tema) e a
verificação pela NBR 8800 com as rotinas que o núcleo já tinha (grupo de parafusos, esmagamento, solda de filete,
tração de barra roscada, chumbadores com aderência e cone, placa de base, chapa de topo, gusset, dupla cantoneira,
compressão da agulha). `exemplos_das_obras` lê a lista de materiais e os nomes de cada obra detalhada e diz a que tipo
cada acessório corresponde. (2) **Tela `/ligacoes`** (tela inicial, menu Lançamento do 3D e do CAD): tipos por categoria
com quantos exemplos há nas obras; desenho, parâmetros (a peça remonta a cada mudança), peças com peso, esforços e as
contas no formato do memorial, e a tabela "Nas obras" com as peças reais (obra, nome, perfil, furos, parafusos,
quantidade) e o link para a lista de materiais da obra. Rotas `GET /api/ligacoes`, `GET /api/ligacoes/exemplos?tipo=`,
`POST /api/ligacoes/montar`. O que a biblioteca revelou das obras: o agulhamento L 1¼"×⅛" de 1,54 m da Sooro tem
esbeltez 240, acima do limite de 200 da barra comprimida (NBR 8800, 5.3.4); a tela acusa e explica. (3) **O lançamento
gera as ligações no modelo** (opção "Ligações" no diálogo, ligada por padrão): cadeirinha em cada cruzamento terça ×
tesoura (base no banzo, chapa em pé com os oblongos da regra da fábrica, 4 parafusos M12), tesoura apoiada no topo do
pilar (chapa de topo no pilar, chapa de apoio na tesoura, 4 M16 A325; o pilar termina na chapa) e chumbadores nos furos
das placas de base; os parafusos entram como no editor ("BOLT (A307) 12x25"), então o detalhamento conta quantos
atravessam cada chapa e a lista de materiais traz os acessórios. As chapas vão para o conjunto soldado certo (suportes e
apoio na tesoura, chapa de topo no pilar). (4) Correções: o detalhamento tomava toda **barra paramétrica** (modelo
desenhado em 2D ou lançado) por chapa na busca de peças montadas, e nunca achava o chumbador (`montagens._eh_chapa`);
os desenhos didáticos do memorial traziam um `<style>` com classes curtas (`.t`, `.l`) que valiam para a página
inteira; a regra global `.corpo` (o layout de duas colunas) dava a cada verificação do memorial e da biblioteca a altura
de uma tela. Testes em `testes/test_acessorios.py`.

**0.8.29.** O meio do caminho que faltava: **lançar a estrutura sobre o arquitetônico do cliente** (análise
"caminho do início ao fim", rodadas 1 e 2). (1) **Arquitetônico como referência** (`nucleo3d/lancamento.py`,
`ler_arquitetonico`; rota `POST /api/projetos/<s>/arquitetonico`): DXF (unidade pelo $INSUNITS ou informada) ou PDF
vetorial (escala 1:N pelas cotas escritas, pelo leitor do projeto recebido, ou informada) vira a **Planta de lançamento**
do CAD, em milímetro real, trazida para perto da origem (DWG de topografia chega em coordenadas UTM), com as camadas
"ARQ ..." em cinza e travadas (aparecem e dão snap, não se selecionam). Importar de novo mantém os eixos. **Calibrar
escala** (dois cliques numa medida conhecida e a medida real) corrige arquivo com unidade errada. O DXF de 39 MB do
cliente (118 mil objetos) entra em 24 s e o CAD o abre em 4 s. (2) **Eixos**: **Malha de eixos...** desenha as linhas na
camada EIXO com as bolinhas e as cotas entre eixos e totais por fora (vãos como 5x6000 ou 6000 6000 7500, ângulo,
origem pegada no desenho); **Gravar eixos no projeto** lê as linhas da camada EIXO (duas famílias perpendiculares, nomes
nas bolinhas; a família de números são os pórticos; sem nomes, a que tem mais linhas) e grava em projeto.json ->
`eixos`, o formato de `nucleo3d/eixos.py` que as plantas de localização e chumbação já usam. (3) **Lançar estrutura**
(Modelo 3D, menu Lançamento; rota `POST .../lancamento/estrutura`): o motor do galpão é o gerador. Ele dimensiona o
pórtico (tesoura treliçada ou alma cheia) com o maior espaçamento entre eixos, e o construtor do 3D monta pilares,
tesouras ou vigas com mísulas, terças, correntes, longarinas, contraventos e placas de base nas posições reais dos eixos
(girados e deslocados como a planta), com **marcas de posição e conjunto** (tesouras iguais, um conjunto; pilar + placa;
viga + mísulas + chapas de topo). Na tesoura, as terças sentam **nos nós do banzo superior** (o galpão as desenhava a
200 mm do beiral, fora dos nós, e calculava com a carga no nó) e a cumeeira não sai em dobro. Padrão da tesoura:
**apoiada** no pilar com **base engastada**, o arranjo que o cálculo do modelo 3D representa igual ao do galpão; a
ligação rígida continua possível, com aviso. O modelo anterior vai para o histórico; **Memorial do dimensionamento
(PDF)** refaz o memorial completo do galpão com os dados gravados do lançamento (`memorial/lancamento`). No chão do 3D,
o arquitetônico em cinza e os eixos com as bolinhas (Ver -> Arquitetônico e eixos; rota `GET .../lancamento/referencia`,
com cache). Tela inicial: **Novo a partir do arquitetônico...** (tipo de projeto `lancamento`) abre a planta e pede o
arquivo. (4) O que o modelo lançado ensinou ao resto do sistema, comparando os dois motores na mesma estrutura: o
cálculo do modelo 3D não reconhecia as barras redondas do galpão ("Barra ø 16 mm", "Barra redonda ø 13 mm": terça sem
correntes, banzo sem travamento), e `perfis_fabrica` agora lê; a corrente feita em trechos era contada duas vezes por
terça (`_correntes` junta toques a menos de 150 mm; nas obras reais nada muda, as correntes atravessam a terça); o
travamento do banzo inferior ganha o papel `travamento` (o cálculo exclui contravento de propósito). O
**detalhamento** aprendeu pilar e viga de pórtico pelo papel da barra (conjuntos **PL** e **VG**, peças PL1.1,
PL1.2...; famílias Pilares e Vigas de pórtico nos resumos), correntes e travamentos como agulhamento (A.C.), e a
**planta de chumbação** aceita placa de base de até 3" (a do pilar engastado sai com 2"), desenha os **furos das
placas** (onde passam os chumbadores), põe o nome a partir da borda da peça e, sem chumbador no modelo, conta chapas de
base em vez de chumbadores (no Depósito Químico as placas iam para a camada dos tirantes; a bateria aceitou essas
mudanças nas três obras que têm placa de base). Testes em `testes/test_lancamento.py` (inclui o PDF a 1:100 lido de
volta pelas cotas); verificador das telas `testes/verificadores/verif_lancamento.py`.

**0.8.28.** Memorial de cálculo por peça, em quatro camadas — o piloto é a terça do modelo importado. (1) **Hipóteses
por extenso** (`nucleo/base.py`: `Hipotese(chave, texto, fonte)` e `Resultado.hipoteses`; `Resultado.cargas` são os passos
da carga por m² ao esforço): a rotina da terça (`nbr14762.terca`) registra modelo estático, seção, aço, travamento da mesa
na gravidade e na sucção (L_b, L_t), C_b, flexão no eixo fraco, apoio (N = 10 cm adotado, não lido), interação M–V e
serviço; o cálculo do IFC (`calculo_ifc._hipoteses_da_terca`) põe antes o que mediu no modelo (vão, largura tributária,
inclinação, correntes contadas) e o que veio do diálogo (cargas por m², vento com os coeficientes e o pior caso, limites de
flecha) e da norma (combinações). Cada hipótese leva a **fonte** (medido no modelo, informado no diálogo, adotado pela
rotina, exigido pela norma, do catálogo), que é a ordem em que o profissional confere. Tudo vai ao `calculo.json`
(`serializar_resultado`). (2) **`saida/memorial_peca.py`** monta o documento a partir do cálculo gravado, sem calcular:
1 resumo (uma linha por peça do mesmo tipo, a escolhida destacada), 2 hipóteses, 3 conta (passos das cargas e cada
verificação com fórmula, números, item da norma, S_d/R_d e barra), 4 explicação — recolhida em cada item ("Entender") e
reunida no fim: o que a verificação protege, o fenômeno com um desenho, o que pesa no resultado e o erro típico. Os textos
da camada 4 ficam em `saida/didatica.py`, por título da verificação, chave da hipótese e texto do passo; o que não tem
explicação aparece em vermelho como lacuna. (3) **Tela `/memorial?projeto=&marca=`** (`web/memorial.html/.js`), aberta pelo
painel do cálculo no 3D ("Memorial desta peça" na peça selecionada; "Memorial de cálculo" nas ações abre a terça mais
solicitada): caixa com todas as posições verificadas, interruptor da camada didática, "abrir todas", "Ver no 3D" volta
com a peça em destaque; rotas `GET /api/projetos/<s>/memorial?marca=&didatico=` e `POST .../memorial/pdf {marca, didatico}`
(PDF profissional sem a camada 4, ou didático com as explicações abertas, em `<projeto>/memorial/`). (4) Duas correções que
o memorial fez aparecer na Sala dos Compressores: a **inclinação do telhado** era a média simples dos ângulos dos banzos
superiores e o joelho do canto quebrado (peça curta a 78°) levava a média para 44° em vez de 11° — vento, sobrecarga e a
flexão no eixo fraco de todas as terças iam junto; agora vale o ângulo do banzo comprido, ponderado pelo comprimento
(`_Tesoura._classificar_banzos`). E os **valores por combinação** da terça eram todos a envoltória (o painel do 3D mostrava
o mesmo M em C1 e C2): cada combinação leva o momento da carga dela (`_valores_da_terca`). Testes em
`testes/test_memorial_peca.py`, com a T.C.5 resolvida à mão como caso de referência.

**0.8.27.** Rodada de consolidação e produção (panorama de 25/09, caminhos A e B). (1) **Antes de publicar, um comando
só**: `testes/antes_de_publicar.py` roda o pytest, os verificadores das telas (`testes/rodar_verificadores.py`, todos os
que se verificam sozinhos, um depois do outro) e a **bateria das obras reais** (`testes/bateria_obras.py`: Sala dos
Compressores, ÁGUA GELADA, Depósito Químico e Capitão refeitas pelo caminho do servidor numa pasta temporária, a partir
de entradas congeladas em `Projeto/bateria/entradas/`, e comparadas com a última rodada aceita — posições, pesos,
totais, resumo, entidades por camada e vistas de cada desenho; relatório em `Projeto/bateria/ultima-comparacao.txt`).
O verif_cantos passou a consultar a chamada longa ao servidor em vez de esperar (estourava tempo com a máquina
carregada). (2) **Editor 3D dividido**: `editor.js` tinha 4.858 linhas; os métodos de cantos/eixos, painéis, troca de
peças, análise/cálculo e diagnóstico saíram para `web/editor3d/modulos/` (classes só com os métodos, copiados para
`Editor.prototype` por `aplicarMetodos`, que acusa nome repetido), sem mudar o corpo; ficou com 2.400. (3) **Plano de
corte por barra**: o encaixe da lista (`lista_producao.encaixar`) guarda o que sai de cada barra, as barras de corte
igual juntas (`plano`), no JSON, no `plano-de-corte.csv`, no quadro 2A do PDF e numa aba da tela com cada barra
desenhada em escala (peças, emendas e sobra hachurada); a contagem de barras não mudou. (4) **Chamadas nos desenhos**:
cada grupo de furos da peça ganha a chamada ("3x OBL 25x13") logo acima dela, em até duas linhas, sem texto por cima de
texto e, perto da ponta, para o outro lado (longe da cota vertical) — `celulas.chamadas_de_furos`; nas elevações dos
conjuntos menores (dispositivos, vigas, pilares), uma chamada por ligação com os parafusos dela ("4x M12 x 30") —
`conjuntos.chamadas_de_parafusos`; a tesoura fica sem (os parafusos dela são os dos suportes de terça). A bateria
confirmou: nas quatro obras só os textos dos desenhos mudaram; posições, pesos e totais iguais.

**0.8.26.** Furo que ia para o canto da peça (print do usuário: clicou na mesa da terça perto da ponta e o furo foi
para o vértice): o ponto que chega às ferramentas Furo e Parafuso vinha grudado pela inferência do editor (snap de
extremidade/aresta); agora elas usam o raio contra a peça sob o cursor (`_naFace`). O ajuste pelo eixo da peça de baixo e
pelos furos de baixo só vale se o ponto continua dentro da face com a folga do furo (`_dentroDaFace`) — a terça que
termina antes do eixo do banzo levava o furo para fora dela —, e o furo que não cabe na face não cria nada (antes virava
um marcador no canto).

**0.8.25.** Rodada de ajustes do editor 3D e da lista de materiais. (1) **O parafuso fura o que atravessa**: ao
colocar, cada parede que o corpo cruza de frente (a face clicada, a mesa de baixo, a chapa do suporte) ganha o furo
d + 1 mm na malha, e a chapa paramétrica em `furos`; onde já há furo no eixo (o do IFC), nada muda. Parafuso e furos são
um passo só no Ctrl+Z (`cmdComposto`). O corte da malha saiu da ferramenta Furo para `ferramentas/_furar.js`
(`furarMalha`, `faceDoPonto`, `furosDoParafuso`), e a peça guarda a malha de antes do primeiro furo do editor
(`malha_sem_furos_editor`) para os furos poderem ser refeitos com outra medida (`refazerFurosEditor`). (2) **Trocar
parafuso…** no painel de propriedades (um, vários, ou todos iguais no modelo): diâmetro, comprimento e classe; a peça é
refeita no mesmo lugar — apoio da cabeça, eixo e pega vêm de `atributos.parafuso` ou, no parafuso do IFC, da malha
(`quadroDoParafuso`: maior eixo principal, cabeça na ponta de raio grande, pega até o próximo nível largo) — e os furos
do editor desses parafusos são refeitos com o diâmetro novo; os do IFC ficam. (3) **Furo oblongo** na ferramenta Furo:
forma, comprimento total e direção (ao longo da peça ou atravessado), ou digitar "13x23"; o laço em estádio é o que o
detalhamento lê como oblongo (`_classificar_laco`), e na chapa paramétrica entra como largura × altura. (4) **Linha do
eixo** na prévia do Furo e do Parafuso: atravessa a peça e marca (e cota) onde cai na peça de baixo. (5) **Órbita**:
qualquer peça sob o cursor vale como pivô, a qualquer distância (o limite do apoio do zoom descartava o ponto depois de
aproximar com a roda, e a órbita caía no centro da seleção); a seleção não puxa mais o pivô, nem no clique no vazio.
(6) **Lista de materiais** refeita em abas (visão geral com barras de peso, perfis, chapas, telhas e rufos, conjuntos,
romaneio, acessórios, resumos da obra, arquivos), cartão do aço separado das telhas; os **Resumos da obra** saem numa
aba com o formulário ao lado da prévia do documento na própria página (antes a tela abria os PDFs com `window.open`
e o usuário não sabia para onde iam), com a etapa do servidor enquanto gera, "Abrir o PDF" e "Abrir pasta"; a aba
Arquivos lista tudo de `detalhamento/` com a data. O GET dos resumos devolve os já gerados.

**0.8.24.** Rufos e calhas (pedido do usuário no DEPÓSITO QUÍMICO: "não foi reconhecida a camada dos rufos"). O
TecnoMETAL grava a funilaria de aluzinc como IfcBeam com o nome do perfil ("RUFO CHAPEU 1", "CALHA 1", "CUMEEIRA
I7.5"), e ela caía em Vigas; no detalhamento, a barra comprida solta virava **agulhamento** (A.C.) e somava no peso
dos agulhamentos. Agora `ifc.importar.funilaria` reconhece rufo (RUFO, contrarrufo, pingadeira, arremate, testeira,
cumeeira de funilaria) e calha pelo nome — a cumeeira de telha (TELHA/TP40) continua telha —, e a peça vai para as
camadas **Rufos** e **Calhas** do modelo 3D. Modelo importado antes muda de camada ao abrir
(`migrar_camadas_de_funilaria`, uma vez por modelo, só das camadas automáticas Vigas/Barras/Pilares; marca
`metadados.camadas_funilaria`). No detalhamento: tipos `rufo` e `calha`, nomes **RF1, RF2… e CL1…** (prefixo a
confirmar com a fábrica), camadas 2D RUFOS e CALHAS, quadros RUFOS e CALHAS no desenho de extras, categoria "Rufos e
calhas" na lista de materiais, sem o aviso de peso teórico (chapa fina: pelo volume da malha). No resumo de
materiais, bloco "Rufos RF e calhas CL" **fora do peso da estrutura metálica** (como a telha; entra no total geral).
Na mesma versão: **o joelho que descolava** (ÁGUA GELADA: nas tesouras de oitão o banzo passa 235 mm ao lado da ponta,
e no M100 o joelho desce sobre uma viga; sem barra alinhada para esticar, a 0.8.21 encurtava o joelho até o nó e abria
o vão) — agora `quebrar_instancia` refaz a peça com `quebrar_peca(manter=[lado])`: segue reta do nó até a ponta antiga
(`pontas_mantidas`). **Pré-visualização** no diálogo Cantos redondos (`cantos.previa`, rota
`GET /api/projetos/<s>/cantos/previa?marca=&n=`, modelo em cache pelo mtime): o canto da primeira instância no plano do
arco, antes (cinza tracejado) e depois (laranja) da opção escolhida, com os nós, o banzo esticado e as diagonais novas,
rodando a mesma quebra numa cópia das peças em volta; muda ao trocar a opção ou clicar na linha. **Órbita no ponto sob
o cursor** (editor 3D, botão do meio ou Shift + direito sobre uma peça): câmera e alvo giram juntos em volta do ponto
(`Camera.girarEmVolta`), que fica parado na tela; antes, com peça selecionada, o pivô ia para o centro da seleção e a
vista deslizava até ele (a terça de 8 m: a câmera ia para o meio da barra). No vazio, a órbita de antes.

**0.8.23.** O programa instalado se encerrava sozinho com a janela na tela ("não é possível acessar esse site"
ao clicar em voltar): a página que sai manda `fechou` na hora e a que entra, pesada (o CAD com o completo de 8 MB),
levava mais que os 6 s que o vigia dava para a troca de página. O vigia (`vigiar`, em `main`) agora espera 30 s
(`SILENCIO_TROCA_DE_PAGINA`) e conta **qualquer pedido HTTP atendido** como sinal de vida (`_ULTIMO_PEDIDO`,
`_pedido_recente`): uma página carregando pede arquivos antes de conseguir mandar o sinal, e isso já prova que há
janela. Encontrado no log do usuário: "nenhuma janela aberta: encerrando" às 15:01:54, antes da 0.8.22 existir.

**0.8.22.** As linhas das tesouras com o canto quebrado no 3D (prints do usuário: a aba do banzo ia parar no contorno
de baixo e cruzava o perfil até a cumeeira; a perna e o banzo "entortavam" antes da ligação): `_emendas_do_chanfro`
levava o banzo até o nó também nas peças já quebradas no 3D — feito para o arco chanfrado só no desenho —, e mexia nos
vértices errados. A peça com `quebras` agora só ganha a linha de emenda (a geometria já vem do modelo como a fábrica
monta), e é banzo na classificação das camadas. **Voltar ao canto redondo** (diálogo Cantos redondos, tabela das já
quebradas): a quebra guarda a malha original em `quebras.original`, os vértices de antes do banzo esticado em
`antes_de_estender` e a diagonal antiga em `quebras.diagonais_antes`; `cantos.desfazer_modelo` devolve tudo, e a peça
quebrada pela 0.8.20 (sem a malha guardada) vem da gravação mais nova do histórico em que ainda era arco
(`_buscar_no_historico`). **Copiar com ponto de referência** no 3D, como no AutoCAD: o primeiro clique é a base (canto,
furo, extremidade da peça), cada clique seguinte cola uma cópia com a base ali, todas medidas da mesma referência
(Enter aceita o canto da caixa; "dx;dy;dz" cola pelo vetor). **Furo que virava marcador** na peça do IFC: o índice de
face do clique é o do triângulo da malha desenhada, não o da face da peça — a ferramenta acha a face pelo ponto e
pela normal (`_faceDoPonto`) e abre o furo de verdade.

**0.8.21.** O canto quebrado como a fábrica monta (pedido do usuário vendo a 0.8.20): quando o arco vai até a ponta
da peça (o joelho que encosta no banzo), a peça passa a terminar **no nó**, em meia-esquadria — o nó cai R·tan(θ/4N)
antes da ponta antiga, e antes a peça sobrava esses 200 mm por cima do banzo —, e o **banzo é esticado até o nó**
(`_estender_vizinha`: os vértices da ponta encostada andam pelo eixo até o plano da meia-esquadria). A **diagonal do
canto**, que apontava para o meio do arco, é refeita **do nó de baixo até cada nó da quebra** (`_diagonais_do_canto`:
mesma seção pela transformação afim que gira e estica só no eixo; posições `P13-Q1`, `P13-Q2`…; o banzo e a perna,
tangentes ao arco, ficam de fora pela componente radial). Quem já quebrou o canto na 0.8.20 restaura o modelo anterior
(Arquivo → Restaurar modelo anterior…) e quebra de novo. **Estilos do desenho** no CAD (Desenho → Estilos do
desenho…, como os estilos do AutoCAD): altura de texto e cota, terminador das cotas (seta, bola ou traço oblíquo —
`Cota.terminador`, ou o padrão do desenho em `metadados.estilo`, no papel e no DXF) e padrão, espaçamento e ângulo das
hachuras, na seleção ou no desenho inteiro (`aplicarEstilos`). E os nomes dos eixos nas plantas saem maiores (3,5 mm),
com a bolinha de 4,5 mm.

**0.8.20.** Quatro frentes pedidas no dia. (1) **Eixos da obra** (`nucleo3d/eixos.py`; editor 3D, Detalhamentos →
Eixos da obra…): os numerados são as tesouras (agrupamento dos centroides das peças de tesoura ao longo do galpão — PCA
em planta: várias tesouras, o maior espalhamento; uma só, o menor) e os com letra são os apoios (chumbadores pelo
nomes.json; sem eles, as chapas horizontais junto do nível mais baixo; sem nada, as pontas das tesouras). O diálogo
mostra os dois grupos, deixa renomear, mover, acrescentar e apagar, identifica de novo e grava em `projeto.json` →
`eixos` (rotas `GET/POST /api/projetos/<s>/eixos`); a planta de localização e a de chumbação desenham os eixos gravados
(ou identificam na hora): linha em EIXO com a bolinha e o nome nas duas pontas e a cadeia de cotas entre eixos com a
total (`_desenhar_eixos`). (2) **Planta de chumbação** (grupo `chumbacao` do Detalhar): chumbadores e chapas de base
vistos de cima, com a marca de cada chumbador, os eixos e as cotas. (3) **Corte no CAD** (ferramenta Corte, `Y`, três
cliques: começo, fim e o lado para onde se olha): marca a linha de corte na camada CORTES — setas para o lado que se
olha e bolinhas com o nome nas pontas (1-1, 2-2…) — e gera a vista do corte no modelo pela planta em que a linha
está: as vistas passaram a gravar `ref2d` (a origem do papel nas direções u e v), e com ela um ponto do papel volta ao 3D
(`dot(q − origem, u) = X − canto_x + ref2d[0]`); o corte é vertical, olhando para o lado clicado, com a profundidade
perguntada. (4) **Furo de verdade na malha** (ferramenta Furo): a face clicada e a face de trás da parede recebem o
laço do furo costurado ao contorno — o mesmo formato dos furos do IFC do TecnoMETAL, com o vértice da ponte repetido —
e a parede ganha o cilindro vazado (`_furarMalha`); o detalhamento lê o laço como lê os do IFC; o marcador de antes só
fica quando a parede de trás não é reconhecida ou na barra paramétrica. E os **furos da peça de baixo** aparecem
projetados na face (circulinhos) e prendem o furo novo no mesmo alinhamento (`furosDaMalha`: o laço entre um vértice
repetido e a sua repetição), como o eixo da peça de baixo já fazia. **Cantos redondos** (editor 3D, Detalhamentos → Cantos redondos…): a barra calandrada do modelo — o
joelho da tesoura, que o TecnoMETAL exporta como um arco facetado de anéis (27 seções a cada 3°) — é reconhecida
pelos anéis da malha (`nucleo3d/cantos.py`: eixo pelos centroides, arco por ajuste de círculo: raio, ângulo,
comprimento, trechos retos), e o diálogo mostra, por posição, em quantas retas quebrar com o desvio de cada opção
(R·(1/cos(θ/2N) − 1); com N = 1 são as pontas, R·(1/cos(θ/4) − 1)). A quebra troca o arco por N retas **tangentes**
(o canto quinado que `_chanfrar_cantos` já desenhava no 2D com N = 1: os trechos retos se prolongam até a primeira e a
última tangente), reconstrói a malha com a seção do próprio anel nos nós em meia-esquadria, em todas as instâncias, e
grava `atributos.quebras`; a peça continua "barra dobrada/curva" e a elevação ganha a linha de emenda em cada quina
(`_nos_das_quebras`). Barra redonda (gancho, tirante) fica de fora. Testes em `test_cantos.py` e
`verificadores/verif_cantos.py`. Motivo: as correções do canto feitas à mão na elevação não valiam para o completo — com
o canto certo no 3D, tudo sai dele.

**0.8.19.** Ferramenta **Furo** no editor 3D (`F`), no molde da Parafuso: diâmetro no painel (usuais, os que o
modelo já usa — furos das chapas e parafusos + 1 mm — ou digitado: 14, 17,5, M12 = 13), eixos da face para prender e
medir, clique na face fura só aquela parede (a profundidade é a camada de vértices logo atrás da face). Na chapa
paramétrica o furo entra em `furos`; na peça do IFC e na barra fica um marcador — cilindro na camada Furos, tipo
IfcOpeningElement, `atributos.furo = {d, ponto, eixo, profundidade}`, `exportar: false` — que viaja com os fixadores no
detalhamento (`_fixadores`) e dá o furo na barra (alma ou mesa) e na chapa com o diâmetro marcado
(`inferir_furos_de_barra/parafusos`), anda com o furo da chapa movido no CAD (`_mover_fixadores`), e fica de fora de tudo
que conta parafuso (`_so_parafusos`: posição, conjunto, montagens, resumos, passantes). Testes em
`test_furo_editor.py` e `verificadores/verif_furo.py`. **Levar para o 3D** agora gera de novo os outros desenhos de
detalhamento a partir do 3D corrigido (o completo, os conjuntos…), e o desenho editado fica como o usuário o deixou —
antes o completo continuava com o desenho anterior até o próximo Detalhar; desenho de outra versão desde a 0.8.17 é
aceito com aviso (só o de antes, sem versão gravada, é recusado).

**0.8.18.** Resumo da obra e resumo de materiais direto do sistema — os dois documentos que a fábrica emite por
obra —, na tela Lista de materiais, botão "Resumos da obra…" (revisão, descrição, telha, letras dos eixos e notas
ficam no projeto e são pedidos na primeira vez). (1) Nomenclatura de produção no padrão da fábrica: T.C./T.L./T.O./T.M.
(terças), A.C./A.L./A.D. (agulhamentos), CV. (contraventos), DP. (dispositivos), F.T., A.T., CH (chapas), CB (chumbadores),
TL/MD/CU (telhas); as obras já detalhadas renumeram uma vez ao detalhar de novo. (2) Peso teórico como padrão em todos os
levantamentos: formados a frio pela NBR 6355 com o desconto das dobras (≈1,64·t por dobra — a planilha da fábrica dá o
mesmo número), laminados, tubos e barras pelo catálogo, chapas pelo retângulo envolvente; o peso da malha 3D fica guardado
para conferir. (3) Terça de parede (T.L./T.O.) pela orientação da seção — alma deitada —, não pela altura: a mesma
posição pode viajar na cobertura e na saia, o nome vai pela maioria e as linhas nas saias contam peça a peça. (4)
Meias-tesouras emendadas na cumeeira viram uma tesoura no resumo: vão entre as chapas de apoio, comprimento entre os
beirais, altura e nível de apoio pela chapa, inclinação pelo banzo mais comprido, flecha pela subida do banzo no
meio-vão; o corpo principal é o trecho com mais tesouras e o degrau entre coberturas sai como linha. (5) Porcas e arruelas
soltas do IFC ("BOLT () 0x0") reconhecidas pela geometria (disco fino = arruela; bitola pelo diâmetro externo ou entre
cantos) e o local de uso de cada parafuso pelas peças que ele atravessa. (6) A impressão dos resumos leva o Paged.js (sem o
sinal de fim de paginação o PDF não saía). Na obra ÁGUA GELADA R00 os números batem com o documento R11 da fábrica onde
os modelos coincidem: 12,30/16,95 m de vão, 14,70/19,15 m, flecha 1,23/1,69 m, altura 2,13/2,57 m, +6,6 m, 20 %,
10 + 4 linhas de terça, 126/126/64/52/32/56 porcas e arruelas. (7) Atualização com uma janela só (vale a partir da
próxima atualização, porque o .cmd é gerado pelo programa que está rodando): o lote roda sem console — com
DETACHED_PROCESS cada filho (timeout, tasklist, find) abria o próprio console, a janela preta "find /i Metalica.exe"
que ficava na tela —, a janela de antes recarrega sozinha no mesmo lugar quando o servidor novo responde (todas as
janelas abertas, pelo canal entre elas) e o programa reaberto, vendo o sinal de vida dela, não abre outra.

**0.8.17.** O que ficou da revisão geral. (1) Atualização com acento no caminho: o .cmd sai de
`gravar_lote_de_atualizacao` e `test_atualizacao_lote.py` o roda de verdade numa pasta "José Ação" com um executável
marcador compilado pelo csc — o instalador é chamado com os argumentos do modo silencioso, apagado e o programa reaberto;
sem o `chcp 65001` nada roda (era o caso até a 0.8.11). (2) Catálogo: as massas da Marcegaglia conferidas no PDF do
fornecedor — a tabela dá a massa do tubo redondo de partida, igual para retângulos de perímetros diferentes (o "70×100"
sai do Ø114,3, perímetro de um 100×80); a nota do item corrigido diz isso. (3) Obra Capitão: a parte de malha aberta
(sem tampas) e a barra contínua ganham a área da seção pelo corte (`area_pelo_corte`: três estações, laço dentro de laço
é furo, vetorizado); o corte que ramifica ou acha dois perfis é "aglomerado de barras"; sem kg/m sobraram 10 partes de
3.507 (eram 517), 56 t medidas (eram 20 t), as terças contínuas de 84 m saem Ue 200×75 com 5,9 kg/m. (4) Desempenho: o
custo de forma da conversão de chapas em numpy e `Entidade.dict` sem o `asdict` número por número (a mesma saída,
conferida contra a anterior); a meta de 20 s da rota do Detalhar não foi alcançada. (5) CAD: linha e polilinha
selecionadas ganham **alças** nas pontas e nos vértices (`Tela.alcas`, `Selecionar._editada`): a ponta vai até outro
ponto, com o snap seguindo a continuação da linha (`snap.ultimo`/`direcoes`) e comprimento digitado; **Esticar** anda no
eixo da própria peça (`_eixoDasVizinhas` só com as linhas da mesma `origem` e, entre direções, a de mais comprimento —
a barra de outra peça no mesmo nó entortava a terça); `pecaDe` pega a peça pela **ligação** das linhas (ponta sobre
outra), não pela proximidade: a cópia espelhada no mesmo nó era selecionada junto; **Explodir** (B) e **Juntar** (W)
(`SobreSelecao`; a linha solta guarda `origem_explodida` e o Juntar devolve a `origem`). (6) Chanfro do canto só no
**joelho**: a transição curta do banzo para o arco (8 segmentos, ~200 mm de corda) virava um segundo chanfro e o banzo
avançava até ele, fechando as duas linhas num trecho inteiro (a terça 3 da Sala dos Compressores) — `FRACAO_JOELHO`,
arco pequeno vira a reta entre as pontas. (7) **Aplicar peças das elevações ao modelo 3D**
(`nucleo2d/detalhe/aplicar_pecas.py`, rota `POST …/desenhos/<nome>/aplicar-pecas`, Vistas do modelo no CAD): o
desenho é comparado com um detalhamento gerado na hora (os artifícios de geração se cancelam), peça a peça pelo
segmento do eixo — apagada, movida/espelhada (rotação + translação no plano da vista), esticada (a ponta anda no eixo)
e cópia (`grupo_copia`, na célula em que caiu, na profundidade daquela instância) —, e a mudança vai para todas as
instâncias de mesma composição (`_instancias_iguais`); exige desenho gerado pela versão atual (`metadados.versao`).
Ensaio na Sala dos Compressores: as diagonais corrigidas dos cantos de M2 + M2 e M2 + M7 subiram para o 3D (uma das
tesouras M2 + M7 não é reconhecida como instância — aviso já existente do modelo). Testes `test_aplicar_pecas.py`;
verificador `verif_cad_edicao.py`.

**0.8.16.** Tela do resultado da análise (`/analise?projeto=…`, `web/analise.html` e `analise.js`): lê o cálculo gravado
(`GET /api/projetos/<s>/calculo`) e mostra o resumo em cartões (posições verificadas, não passam, pior aproveitamento,
peso verificado, ligações, flecha, peças fora do cálculo), a situação por tipo de peça, todas as peças da mais carregada
para a menos (a linha abre as verificações com os passos da conta, "Perfis que servem no lugar…" pela rota de
alternativas e "Ver no 3D" com a posição em destaque; o banzo inferior sem travamento lateral vem marcado), as ligações,
o que ficou fora do cálculo, os avisos, os dados de entrada (cargas e vento NBR 6123 com os casos) e as combinações;
filtro por texto e "só as reprovadas", impressão, tema claro/escuro e tela estreita. No 3D: Ver → Resultado da análise…
e o botão "Resultado em tela…" no painel do cálculo. Verificador `verif_analise.py`.

**0.8.15.** Revisão geral de 24/09, blocos 4 e 5. Telas: o Detalhar do 3D ganhou a opção "Chapas planas viram
chapas paramétricas" (ia sempre ligada); na tela inicial, o erro de "Novo projeto desenhando" aparece (`aviso` não
existia ali — `recado`) e Enter num botão do cartão (Excluir) não abre mais o projeto; no CAD, com um diálogo aberto,
Del/Ctrl+Z/atalhos não agem no desenho por trás; na lista de materiais, ordenar por Posições/Conjuntos ordena pelo texto
das marcas; `paraMilimetros` lê "1.500" e "12.000 mm" como milhar ("1.5m" continua 1,5 m). Desempenho, com a saída
idêntica (desenhos, modelo regravado e lista conferidos contra a versão anterior): direção da onda da telha vetorizada,
covariância dos autovetores em numpy (o Jacobi fica, para os eixos saírem iguais), `_caixa` por zip, célula de conjunto
reaproveitada no desenho completo (`_desenhar_celula`, cache por thread), o desenho por classe dos conjuntos (1:50, que
não saía) deixou de ser desenhado, `_gravar_json` por `json.dumps` (codificador em C), centro dos fixadores guardado na
peça e `analisar` com memória pela geometria — Detalhar do ÁGUA GELADA 50 → 24 s; rota /detalhar dos compressores
85 → 50 s (a meta de 20 s não foi alcançada). Obra Capitão (`nucleo2d/detalhe/fora_do_aco.py`): concreto, neoprene,
madeira… saem do aço pelo material para a lista de pré-moldados (quadro 8 e pre-moldados.csv: peças, volume da malha,
peso pela massa específica), o terreno ("SOLO") fica de fora de tudo, e a malha solta de aço grande
(IfcBuildingElementProxy > 1,5 m, que era contada como parafuso) é separada pelas partes conectadas e medida (seção,
kg/m só em malha fechada, comprimento) no quadro 9 "Estrutura de aço a conferir" e estrutura-a-conferir.csv. PI1/PI2 não
são chapas, como a análise sugeriu: são alças de barra redonda dobrada (Ø12,5 e Ø16), e a classificação "barra
dobrada" que já tinham está certa. Verificadores de diagnóstico sem argumento dão o uso em vez de quebrar. Testes
`test_fora_do_aco.py`.

**0.8.14.** Cálculo pela revisão geral de 24/09 (bloco 3) — **muda a impressão digital do núcleo**; memoriais
emitidos com perfis formados a frio comprimidos, cantoneiras simples de tesoura ou pórtico de alma cheia devem ser
conferidos. (1) `nbr14762.GAMA_COMPRESSAO = 1,20` (Tabela 4, compressão centrada) em `compressao_mrd`, e
`nbr8800.compressao` usa 1,20 no perfil `formado_a_frio` (U, Ue, cantoneira dobrada): Ue 127×50×17×2,00, CIVIL 300,
1,50 m → 66,7 kN (era 72,7). Tubos ficam na NBR 8800 (1,10). (2) `esbeltez_equivalente_cantoneira(..., trelica="plana")`
por padrão — E.1.4.2, 72 + 0,75·L/r até 80 e 32 + 1,25·L/r acima; "espacial" (E.1.4.3) com o limite corrigido para 75:
L 2"×3/16", A36, 1,0/1,5/2,0 m → 48,7/31,4/19,7 kN (eram 54,2/36,5/24,3). (3) `verificar_frio`: KL/r ≤ 200 na barra
comprimida (item 9.7.4). (4) `Verificacao.indeterminada` e `base.nao_verificada()`: a peça sem dado não aprova (`ok`
falso, `Resultado.indeterminada`), sai marcada na serialização e nos elementos do cálculo do IFC e do mapa, e o mapa de
aproveitamento a pinta de violeta (`COR_INDETERMINADA`); o Dimensionar não a aceita mais como "o mais leve que passa".
(5) `galpao.combinacoes_com_vento`: C3 1,25·PP + 1,5·SC + 0,84·V (SC principal), C4 1,25·PP + 1,4·V + 1,2·SC (vento
principal), C5 1,25·PP + 1,4·V, no galpão e nas tesouras do IFC (antes só 1,25·PP + 0,9·SC + 0,84·V, sem ação
principal); a terça do IFC pega a maior entre SC e vento principal; o memorial documenta as mesmas. (6) 2ª ordem no
pórtico: `_forcas_nocionais` (0,3 % da carga gravitacional de cada combinação última, no topo dos pilares) e
`segunda_ordem` — B2 pela flexibilidade lateral com 0,8·EI e R_s = 0,85, B1 com C_m = 1; pilar e viga dimensionados com
M × máx(B1, B2) e N do pilar × B2 (no treliçado, só o pilar); aviso para grande deslocabilidade; seção "Efeitos de
segunda ordem" no memorial, nota nos diagramas (que continuam de 1ª ordem) e `joelho_kNm_analise`. Pórtico padrão:
B2 = 1,14 (média deslocabilidade). (7) Catálogo: `conferir_massas` troca a massa do fornecedor que não bate com a área
(35 itens, com `massa_fornecedor` e `obs_massa`: L 5"×7/16" 23,52 → 21,16; TC 42,4×1,35; TQ 30×30×1,8; série TR 100×70
e 150×80/130×100 da Marcegaglia, que batem com outra medida — a conferir no catálogo deles); tubo retangular calculado
com cantos arredondados (raio 2t/t); chapas CH 2,0 (#14) e CH 3,35 (#10) como a fábrica usa, a CH 1,9 e a CH 3,4
marcadas MSG. Galpão treliçado de 20 m trapezoidal Howe: o banzo inferior deixa de passar com Ue simples (1,03) e o
aviso aponta os banzos duplos. Testes `test_calculo_revisao.py`.

**0.8.13.** Números da produção iguais (revisão geral de 24/09, bloco 2). (1) Romaneio CSV:
`gravar_romaneio_da_lista` sai das linhas da lista impressa (TMD, complemento e cumeeira como na lista, telhas no
comprimento de compra, acessórios no fim), não das posições cruas; o JSON da lista por `_gravar_json`. (2) PDF dos
desenhos com o texto original: `DXF(texto_unicode=True)` grava em UTF-8 sem passar pelo ASCII do R12 (`para_dxf(...,
texto_unicode=True)` em `pdf_dos_desenhos`; "12,5°", "TERÇAS" e "…" saíam "12,5 ", "TERCAS" e "?"); `ler_dxf` tenta
UTF-8 e cai para cp1252; o DXF para o AutoCAD continua ASCII. (3) Nada some calado: `_pecas(doc, puladas)` junta a
barra/chapa paramétrica que não se monta, a regra da saia das telhas que falha vira aviso, e os avisos das vistas (peça
sem geometria) chegam ao resultado do Detalhar. (4) `fundir_posicoes_iguais` separa por volume (1 %) dentro do mesmo
comprimento — nos projetos reais P104 (ponta a 45°) estava fundida com P112/P113 (corte reto) no ÁGUA GELADA e P78 com
P87 na Sala dos Compressores; telha e tirante ficam fora da regra (telha se compra inteira). (5) Seção vazada sem
hachura por dentro (o contorno interno passa para a hachura comum também). (6) Células: a caixa de cada uma é o que as
entidades ocupam (`_extremos_de` mudou do detalhar para a base; `_extremos_reais`) e a célula que desenha à esquerda da
origem é empurrada — na Sala dos Compressores eram 5 pares sobrepostos (até 32 mm no papel), agora nenhum. Testes
`test_producao_saidas.py`.

**0.8.12.** Proteção dos dados (revisão geral de 24/09, bloco 1). Servidor: `projetos.ler` não recria o projeto.json
que existe e não se lê (cópia `projeto.json.ilegivel-<data>`, projeto marcado `ilegivel`, `_atualizar` recusa, `tocar`
não quebra a entrega); `_atualizar` sob `_trava_do_projeto` (RLock por projeto: gravações simultâneas não trazem estado
antigo); nomes.json, ajustes-furos.json e relatorio.json por `_gravar_json` (temporário + troca) e lidos por `_ler_ajuste`
(ilegível vira ErroDeDados com cópia, não "vazio" calado); `_documento3d_do_projeto` anota `_mtime_lido` e
`_regravar_modelo` (14 regravações) recusa gravar por cima do que o editor gravou no meio (`ModeloMudouNoMeio`; no
Detalhar vira aviso); o encerramento automático espera pedidos e progresso em curso (`_em_curso`, `_trabalho_em_curso`);
`_de_fora` recusa Host e Origin que não são do servidor local (GET e POST); `_arquivo` compara pasta por
`commonpath`; nome do PDF limpo; o .cmd da atualização em UTF-8 com `chcp 65001` (usuário com acento — não testado numa
atualização real); histórico do modelo com 20 cópias; `esvaziar_lixeira_antiga` apaga desenhos da lixeira com mais de 30
dias na abertura (projetos excluídos ficam). Telas: `gravarConfirmado` no CAD e no 3D (espera a gravação em curso, não
engole a falha) usado pelo Atualizar, pela troca de desenho, pelo Voltar e pelas saídas ("Modelo 3D", Materiais, Ver no
3D); desenho que não abriu fica bloqueado para gravar (`_naoAbriu`); modelo que não abriu no 3D (`_modeloNaoAbriu`) não
gera do galpão nem grava por cima; Novo desenho com nome existente pergunta; aviso ao fechar com edição pendente; a
gravação automática do 3D que falha continua pendente; Ctrl+S espera a gravação automática (sem o falso "gravado por
outra tela"). `atualizacao.js`: todas as janelas gravam antes (BroadcastChannel `metalica-gravar`), e a atualização é
cancelada se alguma falhar. Testes `test_protecao_dados.py`; verificador `verif_protecao_telas.py`.

**0.8.11.** Projeto recebido "limpo" pelo usuário (as vistas remanejadas): (1) `classificar` — o vão de referência é o
da vista com mais treliça (não a mediana das larguras), e a vista em pé tipada pela forma com pilares na altura do
pórtico, largura que não é o vão e mais larga que alta é fachada lateral (o pilar treliçado dela tem diagonal curta e a
fazia passar por pórtico, que então virava o "pórtico principal" e tirava o oitão da montagem); (2) `_lateral` — inclinada
curta (< 6 % da largura) é diagonal de pilar treliçado, não contraventamento; (3) `_portico` — a faixa da treliça sai dos
grupos de diagonais ligadas pelas pontas que atravessam 40 % do vão, sem as diagonais das tiras dos pilares
(±1,5 % da largura); sem grupo largo, os grupos com pelo menos um quarto do maior (o V de contraventamento de 2 barras
fica de fora — ele descia a faixa e a longarina virava banzo). No desenho limpo do IVAN: 857 barras, dimensionado com 4
pendências (banzo inferior sem travamento); o original segue com 838.

**0.8.10.** Projeto recebido com área cancelada: o retângulo riscado em X de canto a canto (`_areas_riscadas`: as duas
diagonais usam os quatro cantos, as bordas de cima e de baixo desenhadas, pelo menos 30 linhas dentro e nada
atravessando a borda — o painel de contraventamento em X tem terças e tesouras passando por ela) sai do reconhecimento
com tudo o que está dentro, e o aviso diz quantas linhas. No IVAN.dxf a versão antiga riscada virava uma vista só de
30 m, tomava o lugar do pórtico e desligava a detecção de centímetros ("3D todo desmontado"). Teste
`test_area_riscada_em_x_fica_de_fora` (`projeto_2d_sem_texto.dxf(riscado=True)`). Editor 3D: "← Desenho 2D" (`#link-desenho`,
`_ligarVoltaAoDesenho`) volta ao desenho de onde se veio — o CAD manda `desenho=` na URL do editor (`cad.urlDoEditor`,
atualizado ao abrir outro desenho); sem ele, vale o desenho do CAD que abriu a página, e sem nada, o CAD do projeto.
Verificador `verif_voltar_desenho.py`.

**0.8.9.** Cálculo e dimensionamento do modelo gerado do projeto recebido (e mais do IFC). (1) `calculo_ifc`: o
perfil de cálculo cai no catálogo por último (`_perfil_do_catalogo`) e `catalogo.item` acha o nome com a medida em mm
entre parênteses ("Barra redonda ø 1/2\" (12,7 mm)", que o 2D → 3D grava) — o contraventamento ficava fora; o papel da
barra desenhada vale como tipo (`TIPO_DO_PAPEL`); a tesoura desenhada é montada pelo papel (`PAPEIS_DA_TRELICA`) e só com
banzo, montante e diagonal (`_fora_da_trelica`); pilar, longarina, contraventamento, corrente, tirante, suporte e barra
roscada não são terça nem travamento (`TIPOS_NAO_TERCA` — no IFC eles roubavam faixa da terça ou somavam carga falsa:
no ÁGUA GELADA a carga por tesoura mudou de −18 % a +14 %). (2) Apoios no topo dos pilares do modelo
(`_apoios_nos_pilares`, `_definir_apoios`; ponto a mais de `TOL_APOIO` de um nó ganha nó no banzo, `_no_no_banzo`); com
mais de dois apoios, um fixo e os outros só na vertical (sem efeito de arco). (3) `_verificar_complementares`: pilar
(reação da tesoura + peso; fachada lateral engastada com a tesoura de escora, X = 3H(w₁−w₂)/16, K = 2; oitão biapoiado
sob o vento no oitão; interno só normal; fora do plano o trecho entre longarinas — `_verificar_pilar` com K no plano e a
tração com o comprimento real), longarina (rotina da terça com a pressão do vento, faixa entre as vizinhas,
`correntes_longarina`, 1 se não informar), contraventamento em X só à tração (cobertura: F = 1,4·q·área do oitão até
meia altura do frontão, cortante F/2 decrescendo até o meio do vão, N = V·L/profundidade; parede lateral: o cortante à
base; oitão: o vento transversal da faixa do pórtico da ponta), corrente (componente do peso ao longo da água, mínimo
2 kN), travamento do banzo inferior (2 % da compressão). `_vento` guarda as pressões das paredes. (4) `dimensionar`: a
cada rodada o candidato mais leve de `alternativas` (agora com `limite_catalogo` e `so_padrao`) que passa, aceito pelas
regras de fábrica do galpão (`_aceito_no_automatico`: parede ≥ `tesouras.MIN_ESPESSURA` e esbeltez 200/300 na tesoura,
K·L/r ≤ 200 no pilar), com o perfil atual na disputa; banzo por linha (`_grupo_do_elemento`); sem esforço fica; banzo
inferior sem travamento vai para `pendentes`; repete até a escolha se repetir (ciclo: o mais pesado); `sem_solucao` são
as reprovadas que nada das séries padrão resolve. `aplicar_perfis` troca nas barras (perfil original, histórico da
troca, peso); sólido fica como perfil de cálculo. `nomes_das_barras`: o modelo desenhado calcula sem detalhamento. Rota
`POST /api/projetos/<s>/dimensionar {parametros, aplicar}` (modelo anterior no histórico, cálculo gravado). Editor 3D:
"Dimensionar: o perfil mais leve que passa…" (menu e painel do cálculo), campo das correntes da longarina, resultado com
as trocas. (5) `analise.resolver`: cargas agrupadas por barra e K/fatoração guardadas no modelo (`_montagem`,
`_fatorar`, `_resolver_fatorado`; a mesma eliminação de Gauss) — no IVAN o cálculo foi de 83 s a 20 s. (6) Projeto
recebido: vistas em pé com oitão — o pórtico interno só nos eixos de dentro e um oitão em cada ponta (dois desenhos) ou
nas duas (um); longarina do oitão partida nos pilares da vista; no pórtico, o pé vem dos pilares que chegam à treliça,
linha comprida da faixa sem diagonal da alma chegando não é banzo (a longarina de topo do oitão), traço curto abaixo da
treliça (pilar treliçado) sai; `de_vistas`: só banzo, montante e diagonal levam o conjunto da vista. Testes
`test_dimensionar_modelo.py`; verificador `verif_dimensionar.py`.

**0.8.8.** Projeto recebido **sem perfil escrito** (o DXF exportado de um modelo 3D: só linhas, sem título de vista,
sem eixo, em centímetros sem unidade declarada — o "IVAN.dxf" do usuário): `nucleo2d/reconhecer_geo.py`. `analisar`
(retângulo fino fechado alinhado → barra no eixo, com o que está entre as faces — a hachura, o reticulado do pilar
treliçado, até 2,5 larguras para cada lado — consumido; retângulo pequeno → marca de seção; reticulado = inclinadas
curtas; assinatura ângulo × comprimento). `classificar`: pórtico = reticulado espalhado por ≥ 50 % da largura e mais
largo que alto, com pilares (em pé ≥ 0,35 H) é elevação, senão treliça; W = mediana das larguras, H = mediana dos
pilares; elevação cujos pilares têm menos de H/2 vira treliça (a axonometria); planta = uma medida é o vão (±6 %) e há
≥ 3 linhas atravessando; fachada = ≥ 2 pilares, altura entre 0,5 e 1,8 H, mais larga que alta e a largura não é o vão;
o resto é detalhe (sem peças); vista parecida (mesmo tipo, tamanho, ±10 % de linhas e ≥ 90 % da assinatura) e a treliça
solta com o vão do pórtico ficam como `repetida`. `unidade_em_cm`: pórtico com menos de 6 m (ou, sem pórtico, tudo
com menos de 8 m) → fator ×10, `fator_origem` "cm", aviso. `barras_da_vista` → `_portico` (faixa da treliça pelo
reticulado ligado — a diagonal encostada em outras duas, o traço da seta de cota não —; pilar = em pé, ≥ 0,2 H, do pé
do pórtico até a faixa, faces paralelas fundidas (`_fundir_paralelas`, sobreposição com a extensão da própria linha) e
o que fica entre elas consumido; banzo = contorno de cima e de baixo entre os membros da faixa, montante em pé na faixa,
o resto diagonal; linha ≥ 0,15 W sem dois nós interiores — chegada ou cruzamento — é cota desenhada como linha e sai;
a linha do chão (≥ 0,5 W a 5 % de H do pé) e o que está acima da faixa saem; abaixo, inclinada é contraventamento e
deitada longarina), `_planta` (eixos das tesouras pelas marcas de seção com ≥ 2 marcas na fila, na posição exata da
linha que atravessa o vão; filas A, B, C… pelas marcas presentes em ≥ metade das tesouras; terça, contraventamento,
corrente = linha que atravessa o vão fora de eixo, partida nas terças e marcada `fixa` para o `_emendar` não juntar),
`_lateral`; `conferir_pilares` tira das elevações o pilar que não está numa fila de pilares da planta (a linha de cota em
pé). `reconhecer`: título e escala de todas as vistas primeiro, depois a classificação e a unidade, depois as barras;
união das vistas pela distância real entre linhas (≤ 1,5 gap; a tira fina — a fila de cotas — vai para a vista mais
perto a ≤ 3 gap; antes a célula da grade juntava a elevação com a planta de baixo); a forma só entra na vista sem barra
por texto; `resumo.sem_perfil`, `repetidas`; `aplicar` grava `sem_perfil` e `perfis_padrao`. `sugerir_montagem`: vistas
em pé ordenadas (com pilar e menos pilares primeiro — o pórtico interno, cuja altura de pilar é a `altura_pilar`), o
oitão (mais pilares, mesmo vão e ±25 % da altura) só nos eixos das pontas, o resto desmarcado.
`de_vistas.modelo_das_vistas(perfis=)`: linha com papel e sem perfil ganha o perfil do papel (`PERFIS_PADRAO` sem
escolha; nome fora do catálogo é `ErroDeDados`), `de_desenho.perfis_por_papel`. Rotas `gerar-3d` e `projeto-2d` aceitam
`perfis`; `projeto-2d` devolve `sem_perfil`/`perfis_padrao`. CAD: bloco "Perfil das peças reconhecidas só pela forma"
no diálogo das montagens (um campo por papel com datalist do catálogo; guardado em `reconhecimento.perfis`), aviso no
resultado do Projeto recebido e no Reconhecer, "desenho em cm" na escala. `PAPEIS` ganha "corrente". Testes
`test_projeto_2d_geo.py` sobre `projeto_2d_sem_texto.py` (galpão 35 × 25 m só de linhas, em cm); verificador
`verif_projeto_2d_geo.py`.

**0.8.7.** (1) Cópia no CAD é outra peça: `copiaDe` (ferramentas.js) dá às linhas copiadas por Mover+Ctrl, Copiar, Girar
em modo cópia e Espelhar um `atributos.grupo_copia` por operação, e `cad.pecaDe` separa por ele — original e cópia, com a
mesma `origem` do 3D e encostados, eram selecionados juntos. (2) Canto da tesoura com a silhueta partida (M8 + M9: as
arestas das abas da P15 vieram como polilinhas só de arco, 24 pontos, separadas das retas): `_trechos_curvos` reconhece a
polilinha que é só arco (segmentos iguais virando para o mesmo lado, sem segmento comprido que torne os do arco "curtos") e
devolve o trecho inteiro (0, n−1). Os nós do arco puro (`_nos_do_arco_puro`) vêm das direções das retas do contorno da
mesma peça (colhidas no primeiro laço de `_chanfrar_cantos`, `direcoes`) e da bissetriz delas tangente ao círculo de três
pontos — o arco puro acaba um ou dois facetados antes da tangência, e a tangente ali (ou o índice médio) errava 3–8°.
(3) Cotas empilhadas do contraventamento: texto alinhado à esquerda pelo `texto_pos` (margem de 5 mm de papel + meia
largura do texto) e um traço vertical em cada ponta da cota.

**0.8.6.** (1) Emenda do banzo com a peça do canto em **meia-esquadria** (`conjuntos._quinas_da_emenda`): a quina é o
cruzamento do contorno do banzo com o lado da peça do canto; a tampa e a linha da aba terminam na emenda entre as duas
quinas; nós a menos de 12 mm são o mesmo (`nos_quina`). (2) Furos pelos **parafusos colocados no 3D**: a peça que representa
a posição passa a ser uma que tem esses parafusos (antes era a primeira do modelo — as terças da empena ficavam sem o furo),
com a nota "em N de Q peças" quando só parte tem; na peça curva (`barra_conformada`, o perfil de fechamento do beiral) a
alma é a dos vértices na altura do parafuso, não o plano médio da peça inteira; a contagem dos parafusos de mesa usa o `w`
centrado de `pos.local` (o `wt` a partir do mínimo errava meia largura). (3) **Multi-dobra no raio comercial e no formato
da fábrica**: `telhas.RAIO_INTERNO_COMERCIAL` = 450 (R45 cm interno / R49 cm externo na TP40, decisão do usuário; o R800 das
facetas do TecnoMETAL fica em `raio_modelo` e na legenda); pontas livres e vértice ficam os do modelo, tangências
recalculadas. `desenho_da_multidobra`: dois quadros lado a lado (Medidas internas / externas) com o desenvolvido em metros,
retas e corda por fora, ângulo em arco de cota com chamadas radiais, comprimento do arco com o símbolo, raio sobre a linha,
detalhe **ampliado** por fator inteiro até ~120 mm de papel (textos com a medida real; `_cotas_dos_apoios` recebe `amp`),
título "TMD.1 – 64x  MULTIDOBRA TP40 #0,65" (`_rotulo_telha`). (4) **Fechamentos frontal e de fundos**: o topo das chapas
no canto é cortado pelo perfil interno da multi-dobra levado à face (`_perfis_nos_cantos`, um perfil por beiral, o segundo
espelhado pela posição das instâncias; `_recortar_pelo_canto`), o comprimento de compra vai até o topo do canto e a face
avisa "canto cortado pelo arco…".

**0.8.5.** "Já usados no modelo" do Parafuso inclui os fixadores sem tamanho no nome ("BOLT () 0x0", porca de chumbador
ou de barra roscada): `tamanhoDoFixador` mede a entre faces nos eixos principais da peça (Jacobi 3×3; a caixa do mundo
engana com a porca girada) e usa a tabela `_PORCAS` do detalhamento; arruela (espessura < 1/4 da maior medida) fica fora.

**0.8.4.** Célula de peça com a linha dos furos ("furo Ø17", "furos: 2x Ø21") — a legenda enxuta da 0.7.20 tinha tirado,
e a fábrica precisa do diâmetro. Barra que atravessa furo de chapa (`base.barras_passantes`: barra roscada, ferro redondo,
tirante, pelo eixo inteiro furando o plano médio da chapa) entra pelo nome: "fixação: barra roscada Ø5/8", 2x porca 5/8""
em vez de "2 fixador(es) sem tamanho no IFC". Parafuso no 3D: a peça atravessada abaixo da face (`_atravessadas`, caixa
com 80 mm de folga lateral) mostra o eixo dela no plano da face (`_eixoDaPeca`, seção local a ±400 mm), com a distância; o
ponto prende nele e, com o eixo da face preso, no cruzamento.

**0.8.3.** Ponta do banzo no chanfro: na 0.8.1 toda ponta de linha deslizava na própria direção até o nó; a tampa da ponta
(linha curta, atravessada) deslizava ao longo dela mesma e ficava no lugar antigo — a ponta do banzo desmanchava. Agora só
desliza quem anda na própria direção (≤ 15°); o resto vai ao nó como antes.

**0.8.2.** Parafuso no 3D: a ferramenta põe as opções no painel de propriedades (gancho genérico `ferramenta.painel(raiz, el)`
no `_painelPropriedades`; o editor repinta o painel ao trocar de ferramenta): diâmetro, comprimento, classe e os tamanhos
usados no modelo; abrir com um parafuso selecionado copia o tamanho. Eixos da face (`eixosDaFace`: vértices da peça no plano
da face, direção pela aresta mais comprida das faces nesse plano) com snap nas linhas de centro e rótulo das distâncias às
bordas e pontas. Nome "BOLT (A325) 16x50": `_nome_do_parafuso` põe a classe na lista ("M16 x 50 A325"); "(A)" do IFC não
é classe. Atualização: `verificar_atualizacao` não guarda em cache a versão nova ainda sem o .exe anexado (a tela inicial
ficava com "Ver no GitHub" e sem o botão), e a publicação cria a release como rascunho e só publica depois do anexo.

**0.8.1.** Ajustes do detalhamento dos compressores: (1) clique no CAD seleciona a peça inteira (`cad.pecaDe`: mesma
origem, célula e detalhe, encostadas; Alt = só a linha) e o cruzamento testa o traço (`Tela._tocaJanela`, a moldura do
quadro não entra); (2) banzo que avança até o nó do chanfro desliza na direção da própria linha (`_emendas_do_chanfro.destino`
com a ponta de longe) — a linha da aba girava 0,35° e o banzo "torcia"; (3) chapa soldada no chumbador e a montagem
CB + CH vão para o quadro CHUMBADORES (`chapas_de_chumbador`, `grupos_montados` levantado uma vez); (4) chapa de topo
da cumeeira (em pé: extensão ao longo do vão ≤ espessura + 5, a 350 mm do meio) detalhada debaixo da tesoura montada
(`com_chapas_da_cumeeira`, atributo `detalhe_cumeeira`); (5) terças em colunas (`base._em_colunas`, 560 mm de papel) em vez
de uma por linha (quadro de 8,5 × 40 m); (6) lista de materiais: o seletor da barra, movido para o quadro Perfis, era
apagado no redesenho (PDF pela tela dava "Cannot read properties of null") — referência guardada; botão Voltar;
(7) Mover e Girar copiam com Ctrl (toque liga/desliga, como no SketchUp; segurar no clique também).
Verificador `verif_peca_inteira.py`; `verif_materiais.py` gera o PDF pela tela.

**0.8.0.** Projeto recebido em DXF ou PDF → modelo 3D → IFC. `nucleo2d/pdf_ler.py` lê o PDF vetorial (PyMuPDF: traços,
Béziers, círculos dos balões, textos com rotação; camada = OCG ou cor; mm de papel; avisa PDF digitalizado e texto SHX).
`nucleo2d/reconhecer.py`: vistas por proximidade só das linhas de peça (cota e eixo não juntam vistas), título e tipo
(planta, treliça, elevação, lateral, detalhe), escala de cada vista pela moda de valor/comprimento das cotas (linha de cota
partida em volta do número e até a ponta da seta; PDF encaixa em 1:N, DXF em mm/cm/m/pol e ampliações), eixos (balão +
linha longa), perfil escrito → catálogo (`perfil_do_texto`: #bitola ABNT e MSG, polegadas, 2U/2L, Ø, CH, legenda de
siglas), rótulo → linha (chamada curta ou de camada de anotação; senão paralela; texto ao lado de pilar), herança pelo
colinear da mesma camada e pela camada homogênea (≥ 3 rótulos, "a conferir"), linha dupla fundida no eixo, emenda de
colineares, papel (palavra, sigla, contorno da treliça). `aplicar` põe as barras nas camadas PEÇAS RECONHECIDAS / A
CONFERIR (não mexe no desenho). `sugerir_montagem`: planta deitada subindo até o banzo superior (`_Cobertura`) e terças
partidas nos eixos; vista em pé em cada eixo da família que tem o vão; lateral nos eixos das pontas.
`nucleo3d/de_vistas.modelo_das_vistas` gera as barras (posição por perfil/papel/comprimento; conjunto igual para
instâncias iguais). Rotas `importar-pdf`, `desenhos/<n>/reconhecer`, `projeto-2d` (tudo de uma vez + IFC em `ifc/`),
`gerar-3d` com `montagens`. DXF: `texto_de_bytes` (ANSI dos DXF antigos), `codigos_de_texto` (%%U some), objetos de bloco
na camada 0 herdam a camada de quem insere, altura de texto sem o piso de 0,5. Exemplo: `testes/projeto_2d_exemplo.py`
(galpão em DXF e PDF); testes `test_projeto_2d.py`; verificador `verif_projeto_2d.py`.

**0.7.31.** Regras da fábrica (`fabrica.py`, `<dados>/fabrica/regras.json`): bobinas, largura máxima da tira, limites
da dobradeira e raio interno; o Trocar perfil do 3D valida pelo servidor (`POST /api/fabrica/validar`) e recusa o perfil
dobrado que a fábrica não faz (laminado só do catálogo; MSG e ABNT da mesma bitola valem). Perfis fora do catálogo usados
ficam em `<dados>/fabrica/perfis.json` com data, projetos, usuário e máquina, e entram nas sugestões. Tela: Catálogo →
Regras da fábrica. Verificador `testes/verificadores/verif_fabrica.py`.

**0.7.30.** Bitolas #7 (4,50), #9 (3,75) e #15 (1,70) em `nucleo/perfis_fabrica.BITOLAS` e no Trocar perfil do 3D
(U100X50X#9 não era reconhecido). Histórico da troca de perfil: a peça guarda `marcas.perfil_original` e
`atributos.trocas_de_perfil` ([{de, para, data}]), mostrados nas propriedades; a posição leva "perfil original X,
trocado em dd/mm/aaaa" nas observações (romaneio).

**0.7.29.** O furo da barra segue o parafuso (`alinhar_furos_das_barras_aos_parafusos`, até 250 mm; o parafuso tem de
cruzar a peça no sistema dela): a ligação mexida à mão no 3D (chapa P79 esticada 90 mm) não passava do limite de 40 mm
do alinhamento com as chapas. **Atualizar peça** (`POST /atualizar-pecas`): furos e células só das peças pedidas,
redesenhadas no mesmo lugar em cada desenho de detalhamento (`nucleo2d.desenho.transladar`). 3D: Shift sobre uma aresta
trava o movimento paralelo a ela (`EIXOS.aresta`); a chapa paramétrica tem as arestas das duas faces (`facesDaChapa`)
para o snap. Editor não abria modelo com malha de 200 mil vértices (`push(...lista)` em `Documento.caixa`, OBRA
CAPITÃO do SketchUp).

**0.7.28.** Ferramenta **Parafuso** (U) no 3D (`web/editor3d/ferramentas/parafuso.js`): cabeça, corpo e porca
perpendiculares à face clicada, tamanho digitado (M12x35, 16x40); sólido na camada Parafusos com o nome e o tipo dos
parafusos do IFC ("BOLT (A) 12x35", IfcMechanicalFastener, `criado_no_editor`). No levantamento, a barra que um
parafuso do editor atravessa ganha o furo na alma ou na mesa (`inferir_furos_de_barra`; os parafusos do IFC não criam
furo em barra). Verificador `testes/verificadores/verif_parafuso.py` (parafuso e Empurrar/Puxar em chapa).

**0.7.27.** Tesouras **montadas**: as meias-tesouras no mesmo plano (`tesouras_montadas`, 150 mm) saem juntas,
como a fábrica gabarita, e as montadas com as mesmas meias viram uma célula ("T1 + T1 – 03x"); a meia só sai sozinha
se tiver instância sem par. Cadeias de cota por água (`trechos` do banzo; banzo de cima pela comparação na mesma
abscissa, não pela altura média). Canto chanfrado em peças retas (`_emendas_do_chanfro`): o banzo vai até o nó (o
trecho reto curto da calandrada sai) e cada nó ganha a linha de emenda. Legendas com a espessura pela bitola
(`saida.dobras.com_bitola`: MSG 4,176 = #8 → U100X50X#8) e continuação alinhada à margem. Furação padrão de fábrica
também no 3D: ao detalhar, as chapas paramétricas das posições corrigidas pela regra das terças recebem os passos
novos (`padronizar_furos_das_chapas`, com os parafusos) e as terças acompanham. CAD: Estender numa polilinha (chapa)
passa ao Esticar com o lado pego. 3D: Empurrar/Puxar em chapa paramétrica (lado do contorno ou espessura); cotas 3D
com chamada e traço proporcionais à medida.

**0.7.26.** Esticar (S) na ponta de barra inclinada com corte oblíquo (a diagonal da tesoura): a aresta andava
na perpendicular dela mesma e entortava a barra, e as linhas internas do perfil, que chegam no meio da aresta,
ficavam paradas. Agora anda tudo o que termina sobre a aresta, na direção das linhas que chegam nela quando são
paralelas (`_eixoDasVizinhas`, ±2°); sem vizinhas paralelas, na perpendicular, como antes.

**0.7.25.** Lista de materiais: o seletor "Barra comercial" (6/12 m) ficava no topo, ao lado de "Recalcular do
modelo", e parecia escolher outro projeto; agora está dentro do quadro Perfis ("Comprimento da barra de aço para
compra"), que é o único que ele muda, o topo diz "Projeto: <nome>" e o botão virou "Atualizar pelo modelo 3D".

**0.7.24.** Lista de materiais: totais e categorias somados das linhas da lista (antes, das posições cruas)
— as telhas multi-dobra, o complemento e a cumeeira entram, e as telhas pelo peso de compra; na sala dos
compressores o cabeçalho dizia 6.957 kg / 1.866 peças e a coluna somava 11.215 kg / 2.026. Conjuntos com
uma peça a mais ou a menos numa das instâncias contam as instâncias pela maioria das posições, como o
detalhamento (`_unidade_pela_maioria`): M2 = 8 tesouras, não 1; o peso total é o das peças que existem e a
composição anota o que difere. CAD: "Abrir desenho do projeto" fechava o diálogo sem abrir (o `close()`
direto não resolvia a promessa). Saídas dos verificadores headless no `.gitignore`.

**0.7.23.** Pranchas no modelo da fábrica (`Projeto/Modelos de Pranchas - Hermes.dwg`, medidas em
`nucleo2d/modelo_hermes.py`): quadro com 25 mm à esquerda e 7 mm nos outros lados, marcas de dobra, aviso de
propriedade em pé na margem e carimbo 178 × 99,8 mm (0,6 disso na A3/A4) com caixas R2 — logo (hachuras do
bloco do DWG, `nucleo2d/_logo_hermes.py`), CONTEÚDO (gerado: "- TESOURAS: T1 (08X), T2 (02X)", com o número
da prancha), ESCALA ("INDICADA" com mais de uma), DATA (mês / ano), OBRA (obra - cliente) e PROJETISTA. A
tabela de posições no rodapé saiu (o conteúdo está no carimbo e no índice). A prancha herda as camadas dos
desenhos de origem, e o PDF sai com as cores das camadas das peças; a moldura/título dos quadros do desenho de
origem não entra mais na célula. Legenda dos conjuntos sem a lista de nomes das peças: uma linha por tipo
(banzos, diagonais, montantes, chapas pela espessura) na cor da camada, parafusos e peso. Contraventamentos:
o tirante que já está no detalhe do grupo não ganha célula própria. Lista de materiais: a página não
carregava `web/vivo.js` e o programa instalado se encerrava 6 s depois de abri-la ("Failed to fetch" no
PDF) — `testes/test_paginas.py` cobre todas as páginas; novo quadro **perfis dobrados: peso teórico × com
desconto das dobras** (`saida/dobras.py`: desconto = 2(ri + t) − π/2 (ri + k·t), ri = t, k = 0,5 — bate com
a massa da NBR 6355), com a tira desenvolvida e `peso-dobras.csv`.

**0.7.18.** Furos das terças "viradas": a detecção (`saida.detalhamento._lacos_2d`) aceitava só os laços
no nível médio da alma (±0,6 mm), mas os eixos da barra vêm da nuvem de vértices e saem inclinados uma
fração de grau — numa terça de 5 m a alma "sobe" ~7 mm de ponta a ponta, e só o furo do meio passava.
Agora o nível de cada laço é comparado com o plano ajustado à alma (`_plano_do_laco`); uma seção inteira de
terças (T.C.4 e outras) voltou a ter furos alinhados, retirados e oblongados. `aplicar_furos_nas_barras`
repete a passada até assentar (o eixo gira um pouco quando os furos andam). Medidas e direção da onda das
telhas guardadas por peça (o detalhamento completo caiu de ~60 s para ~33 s).

**0.7.16.** Furo fechado sai da malha de verdade (`_limpar_faces`: tira os pontos repetidos e as pontas
que o furo fechado deixava no polígono da alma e as faces da parede; conserta também os furos fechados
pela 0.7.13–0.7.15). "Tem uso" passou a ser a distância real do centro do furo à superfície do parafuso
ou da barra (a caixa de um tirante em diagonal cobria metros de terça). `oblongar_furos_das_tercas`:
todo furo de ligação da terça (≤ 18 mm) vira oblongo 25×13 no sentido da barra também na malha, e o
furo redondo da chapa parafusada nele (suporte de agulhamento, de terça) vira oblongo igual.
**Cumeeira** (`telhas.cumeeiras`): o TecnoMETAL modela como duas telhas curtas, uma em cada água,
que se encontram na cumeeira; agora é uma peça só (CM.n), com as pernas (arredondadas para cima), a
dobra e o desenvolvido, na lista de materiais e fora da paginação. No CAD, o painel mostra o
comprimento da polilinha, do arco e do círculo (a soma, com vários).

**0.7.13 — peças montadas e furos sem uso.** `nucleo2d/detalhe/montagens.py`: `grupos_montados` acha
pela geometria as chapas miúdas (≤ 600 mm) do mesmo conjunto que se encostam (suporte de terça = chapa +
nervura soldada) e a chapa de base deitada atravessada por barra redonda em pé (o chumbador, que no
TecnoMETAL vem como conjunto próprio), com as porcas; pares de chapas iguais não contam. Cada combinação
vira uma célula (quadro "PEÇAS MONTADAS", no desenho de chapas e na família dela no completo) com frente,
lateral (cotas gerais, nomes com chamada; a isométrica saiu na 0.7.17). O chumbador ganhou tipo próprio (`chumbador`,
"CB."; antes caía como contraventamento). `retirar_furos_sem_uso`: furo de terça sem parafuso nem barra
passando (caixa do fixador/barra cobrindo o centro, 2 mm) é fechado na malha — os vértices vão para o
eixo do furo — e some do detalhamento; roda ao gerar o detalhamento, depois do alinhamento às chapas.
O alinhamento passou a parear furo × furo da chapa pelo par mais próximo no todo (furo a furo, um furo
sem uso perto da ligação roubava o furo da chapa).

**0.7.12 — retorno da fábrica.** Telha: comprimento de compra arredondado **para cima** de 5 em 5 mm
(`base.arredondar_telha`, `PASSO_TELHA`: 1449 → 1450, 1891 → 1895) na compra, na célula, na lista, na
paginação e nas retas da multi-dobra (a sobra fica nas pontas livres). A saia é **fora a fora**: uma
altura por face, a da longarina mais baixa da face (`saias_de_fachada` agrupa as telhas pelo plano; a
telha do canto, onde a longarina já terminou, desce junto). Na paginação da fachada, a linha da última
longarina (EIXO) atravessa a face com a cota da saia; o tracejado do corte fica na posição real (sem a
escala para 1050), e a linha da empena segue contínua. Multi-dobra: o raio sai do modelo como arco das
facetas ÷ ângulo (no TecnoMETAL do usuário, 110 mm por faceta girando 7,87° = R800 na linha média) —
o desenho explica a conta; as terças e longarinas debaixo dela aparecem (camada TERCAS, seção pela face
da ponta, `_apoios_no_perfil`) com a cadeia de espaçamento em cada reta, da ponta livre.
Nós da tesoura: onde chega um montante, o nó é o eixo dele (a diagonal cruza o banzo com excentricidade e puxava a média uns 23 mm). Cadeia dos suportes de terça: a referência é o suporte (pé da perpendicular no banzo), a chamada nasce
nele. Contraventamento: a cota empilhada é o tamanho da **barra** (sem as peças de ponta), a dobra da
ponta ganha cota, e as peças de ponta (gancho, chapas, barra roscada) são detalhe padrão — só o nome.
Bitola #14 = **2,00** (a da fábrica); a troca de perfil mede a espessura na malha, então refazer a troca
para o mesmo nome corrige peça trocada antes com 1,90. Furos das terças seguem a chapa de suporte
(`alinhar_furos_das_barras_as_chapas`: pela geometria — furo de chapa paramétrica encostado a menos de
40 mm —, com o formato: oblongo da chapa vira oblongo na malha da terça); roda ao gerar o detalhamento e
ao aplicar furos. No 3D, **Isolar** (painel da seleção, menu Ver): só a peça aparece (também para seleção
e snap, `Documento.foraDoIsolamento`); "Voltar ao modelo" oferece levar a chapa editada às iguais.

**Quadros por família no desenho completo** (`detalhar.FAMILIAS`): o conjunto e as peças dele
juntos — a tesoura com as barras e as chapas de base, o agulhamento com o suporte e a barra, o
contraventamento com o tirante, a castanha e a barra roscada. A família de uma peça avulsa vem
do tipo de produção dela ou do tipo do conjunto em que ela mais aparece.

**Canto da tesoura**: sem nada apoiado, a diagonal é a corda do arco; com um suporte de terça
encostado no trecho reto depois do arco, esse trecho avança até passar do suporte
(`FOLGA_CHANFRO_SUPORTE` = 100 mm) e a diagonal vai até ali.

**Cotas**: número que não cabe entre as chamadas sai pela ponta (primeira e última cota da
cadeia) ou um degrau para fora (as do meio), gravado em `Cota.texto_pos`; no CAD, a cota
selecionada tem uma quarta alça (losango) que leva só o número.

**Esticar (S)** no CAD: clique numa aresta e ela anda na perpendicular levando o que encosta
nas pontas dela (arestas vizinhas esticam, cotas presas mudam de valor) — o empurrar/puxar do
SketchUp; ou arraste uma janela e os pontos dentro dela andam (o STRETCH do AutoCAD).

## Exportar DXF

`nucleo2d/dxf_cad.py` (ezdxf, DXF R2010): cotas como DIMENSION funcionais (estilo METALICA,
DIMSCALE = escala do desenho, decimal com vírgula), camadas com a cor do CAD (RGB e ACI mais
próxima; as quase pretas em ACI 7), tipo de linha e espessura, textos no estilo METALICA com
a fonte da tela (Segoe UI) e um GROUP por peça ou conjunto com o nome de produção. Sem a
ezdxf, a rota cai no R12 antigo (`Desenho.para_dxf`). As posições também saem em **quadros
por tipo** (`detalhar.QUADROS_POSICOES`: terças, suportes de terça, chapas…), no desenho do
grupo e no completo.

## Trocar o perfil de uma peça importada

A peça do IFC é uma malha, não uma barra paramétrica. **Trocar perfil…** (painel
Propriedades, grupo "Peça (IFC)", ou com várias peças do mesmo perfil selecionadas) passa
a malha para a seção nova (`web/editor3d/nucleo/trocar_perfil.js`): a seção é remapeada
por faixas — espessura da mesa, enrijecedor e alma na altura; espessura da alma e do
enrijecedor na largura — com o comprimento intacto, então espessuras, abas e enrijecedores
saem exatos; o esticamento do miolo vai para o maior trecho sem vértices, e os furos só se
deslocam, sem mudar de tamanho. A face da alma fica no lugar; a altura cresce igual para
os dois lados. Alcance: as peças escolhidas, a posição inteira ou todas com o mesmo perfil;
Ctrl+Z desfaz. A marca `perfil` passa a ser a nova (`perfil_anterior` guarda a de origem),
e detalhamento, lista de materiais e cálculo saem com ela. Por ora U e Ue (C) formados a
frio. A espessura pode vir pela **bitola** (`perfis_fabrica.BITOLAS`: #16 = 1,50, #14 =
1,90, #13 = 2,25, #12 = 2,65, #11 = 3,00 mm): "C127X50X17X#14" é um Ue 127×50×17×1,90.

## Editor 3D

O editor roda no navegador e funciona sem internet: a biblioteca 3D, Three.js r160 sobre
WebGL 2, fica em `web/lib/`.

**Dois tipos de objeto.** Barras e chapas são paramétricas: a barra sabe o perfil do
catálogo, o aço e o papel (pilar, viga, terça, longarina, contraventamento), e trocar o
perfil refaz a geometria e o peso. Além delas há sólidos livres, como no SketchUp, para
terreno, equipamentos e geometria recebida de terceiros.

**Ferramentas**, com o atalho de teclado entre parênteses:

| Grupo | Ferramentas |
|---|---|
| Navegação | selecionar (espaço), vistas padrão (1 a 7), zoom na extensão (Z) |
| Desenho | linha (L), retângulo (R), círculo (C), polígono, arco |
| Edição | push/pull (P), offset (O), mover (M), girar (Q), escalar (E), copiar |
| Medição | trena (T), cota (D), plano de seção (X) |
| Estrutura | barra com perfil do catálogo (B), chapa com furos (H) |

Durante uma operação dá para digitar a medida e confirmar com Enter, como no SketchUp:
`3000`, `3,5m`, `350cm`, ou `2000;1000` para um retângulo. Toda alteração pode ser
desfeita com Ctrl+Z.

**Mapa de esforços.** O botão **Calcular estrutura** (ou F9) calcula o galpão e pinta o
modelo pelo que você escolher: aproveitamento S/R, momento, cortante ou força normal.
Ele não fica ligado sozinho — só aparece quando você manda calcular, e o mesmo botão
esconde tudo depois. Com o mapa ligado, o painel "Análise" mostra:

- a **escala de cores** com a faixa de valores, e a marca de 100 % no aproveitamento;
- as **dez peças mais solicitadas**, com marca, elemento e razão; clicar seleciona a
  peça no modelo, clicar duas vezes enquadra;
- a **peça selecionada** com perfil, verificação que governa, S<sub>d</sub>/R<sub>d</sub>
  e os esforços que a dimensionaram;
- a **combinação** em exibição — envoltória (o pior caso de cada seção) ou uma
  combinação específica, últimas e de serviço separadas;
- o **deslocamento do topo** contra o limite da norma, em barra de proporção.

Três desenhos podem ser ligados sobre o modelo: os **diagramas** de M, V e N ao longo do
pórtico, com os picos cotados; a **deformada**, com fator de exagero ajustável; e as
**cargas** da combinação, em setas com o valor em kN/m. Eles vivem só na tela: não entram
na árvore do modelo, na lista de material nem no IFC.

Como os pórticos são todos iguais e recebem a mesma carga, a fita é desenhada num só —
um seletor escolhe entre um, três (pontas e meio) ou todos, e o painel diz qual está em
exibição. Terça e longarina não entram no modelo de pórtico: são verificadas como viga
biapoiada, e o diagrama delas aparece sobre uma **peça típica** de cada elemento.

**IFC.** O menu IFC exporta o modelo em IFC4 e importa arquivos IFC de outros programas.

- Na exportação, barras saem como `IfcColumn`, `IfcBeam` ou `IfcMember`, com o perfil
  paramétrico quando o tipo permite (`IfcIShapeProfileDef` e similares). Chapas saem
  como `IfcPlate`, com os furos como vazios de verdade. Cada peça leva material,
  propriedades de cálculo e quantidades.
- Na importação, pilares, vigas e barras cujo perfil casa com o catálogo voltam como
  barras editáveis, e chapas voltam como chapas. O resto vira sólido livre. O editor
  mostra um relatório do que foi reconhecido e do que ficou de fora.
- Arquivo sem camadas (TecnoMETAL, Tekla sem configuração) recebe camadas pelo que a
  peça é: Telhas, Chapas, Parafusos, Tirantes, Pilares, Vigas e Barras, para dar para
  ocultar as telhas e ver a estrutura. Cada peça guarda as marcas de conjunto, posição
  e perfil do exportador.
- Modelo em coordenadas de obra (o canto a mais de 50 m da origem) é trazido para a
  origem na importação, para cair sobre a grade; a cota fica como está. O deslocamento
  vai para `metadados["deslocamento_mm"]` e o exportador o devolve na colocação do
  `IfcSite`, de modo que o arquivo exportado volta ao lugar de obra.
- O editor grava o documento no servidor alguns segundos depois de cada mudança, em
  `projetos/modelos/<nome>.modelo.json`, e reabre o último modelo ao carregar a página
  sem parâmetros. Atualizar a página não descarta o trabalho.
- **Colorir por**, no painel Camadas, pinta o modelo por conjunto de montagem, posição,
  perfil ou tipo IFC, com legenda: clique num grupo seleciona as peças dele, duplo
  clique enquadra. Peças sem a marca ficam em cinza.

## CAD 2D: cortes e vistas do modelo para as pranchas

O caminho de produção a partir de um modelo importado: no editor 3D, posicione o plano
com a ferramenta **Seção (X)** e tecle **G** (ou menu Desenho 2D → Gerar desenho do corte
atual). O servidor corta o modelo pelo plano e abre o **CAD 2D** (`/cad`) no desenho
gerado, dentro do projeto (`<projeto>/desenhos-2d/`).

- **Motor de vistas** (`nucleo2d/vistas.py`): o que o plano atravessa vira a seção da
  peça, hachurada e rotulada com a marca de posição; o que está além, até a
  *profundidade de vista*, sai projetado (silhueta e arestas vivas). Vistas padrão de
  frente, topo e laterais, do modelo inteiro ou só da seleção. Cada linha sabe de que
  peça 3D veio, e o CAD seleciona "tudo da mesma peça". Linhas ocultas não são removidas.
- **Documento 2D** (`nucleo2d/desenho.py`): camadas com tipo de linha e espessura;
  linha, polilinha, círculo, arco, texto, cota, hachura e chamada. Milímetro no modelo;
  texto, cota e hachura em mm de papel, multiplicados pela **escala do desenho** ao
  desenhar e ao exportar, então mudar a escala redimensiona a anotação toda.
- **CAD** (`web/cad/`): canvas 2D com zoom na roda e pan no botão direito; snap de
  extremidade, meio, centro, interseção, perpendicular e sobre a linha; orto com Shift;
  ferramentas de linha (L), polilinha (P), retângulo (R), círculo (C), arco (A), texto
  (T), cota (D, com H/V/A para o modo), chamada (H), hachura (G), mover (M), copiar (O),
  girar (Q), espelhar (I), paralela (F), aparar (X), apagar (E) e medir (U); medida
  digitada (`1500`, `1,5m`, `1500<30`, `2000;1000`); desfazer/refazer; painéis de
  propriedades, camadas, snap e vistas. O desenho é gravado sozinho no projeto.
- **Exportar DXF** gera o arquivo em `desenhos-2d/` com as camadas da produção (ACO,
  ACO-FINO, HACHURA, COTA, TEXTO…), na escala do desenho.

Ferramentas do CAD 2D (`web/cad/ferramentas.js`): linha (L), polilinha (P), retângulo (R),
círculo (C), arco (A), texto (T), cota (D), chamada (H), hachura (G); mover (M), copiar (O),
girar (Q), espelhar (I), offset (F), **aparar/trim (X)**, **estender/extend (N)** — a linha vai
até a primeira linha, arco ou círculo na direção dela —, **concordar/fillet (K)** — duas linhas
viram canto vivo (raio 0) ou arco tangente do raio digitado, com as pontas aparadas ou
estendidas —, **mover linha de cota (J)** — clique na cota, ou selecione várias, e depois onde a linha deve ficar; os pontos medidos não mudam, e várias cotas paralelas vão para a mesma linha —, apagar (E), medir (U). O snap enxerga a **linha de cota** das cotas existentes (pontas e "sobre", rótulo `linha de cota`): é como se alinha a próxima cota pela anterior. Ao desenhar linha ou polilinha, o cursor **gruda na
continuação da linha anterior** e na perpendicular dela (snap `alinhamento`, marcado com
`⊢─⊣`), e no primeiro ponto segue a linha existente de onde a nova parte — é o *tracking*
dos CADs, sem travar como o orto. **Esc** volta para selecionar e **espaço** chama de novo a
ferramenta que estava em uso. A seleção por janela pega a cota pela **linha de cota**
(`pontosCota`), não pelos pontos medidos, que ficam na peça: antes uma cota deslocada da peça
não entrava na janela nem no índice espacial, e não havia como apagá-la.
**Alças da cota** (`Tela.alcas`, `Selecionar.onPressionar`): com a cota selecionada aparecem
três alças — os dois pontos medidos (quadrados) e o meio da linha de cota (círculo). Arrastar
(ou clicar e clicar de novo) a do meio leva a linha de cota; as das pontas mudam o ponto de
referência com snap, e a linha de cota fica onde estava. O texto numérico da cota acompanha a
medida nova; o snap não enxerga a própria cota enquanto ela é arrastada (`Snap.ignorar`).

## Detalhamento de peças a partir de um IFC

Para produção a partir de um modelo de detalhamento de terceiros (TecnoMETAL, Tekla,
Advance Steel), o sistema lê o IFC e entrega, em `projetos/<nome>/detalhamento/`:

- **`detalhamento.dxf`**, um arquivo único em milímetro e 1:1 com o desenho de cada
  posição numa célula, agrupadas por tipo: contorno e furos nas camadas `ACO` e `FURO`
  (o que a máquina de corte lê), cotas, marca, material e quantidade nas camadas `COTA`
  e `TEXTO` (que o operador desliga), moldura das células em `AUXILIAR`;
- **`romaneio.csv`** com posição, conjuntos, tipo, perfil, material, quantidade,
  dimensões, furos e peso, mais os parafusos, que só entram na lista;
- **`relatorio.json`** com o que foi reconhecido e as posições com ressalva.

```bash
python -m saida.detalhamento caminho/do/modelo.ifc            # grava em projetos/<nome>/detalhamento/
python -m saida.detalhamento caminho/do/modelo.ifc pasta --png  # também uma imagem de conferência
```

No editor 3D, **IFC → Detalhar peças de um IFC…** faz o mesmo e mostra os links e as
ressalvas. As peças são agrupadas pela marca de posição (`Part Mark`) e o desenho é
reconstruído da malha, porque esses exportadores escrevem toda a geometria como Brep
facetado, sem perfil paramétrico: contorno e furos (redondos e oblongos) vêm das arestas
de borda da face, a seção vem do corte da malha ao longo do eixo, o comprimento é a
extensão no eixo e as pontas cortadas fora do esquadro saem com o ângulo. Barra redonda
dobrada (gancho, chumbador) recebe o comprimento desenvolvido pelo volume. O que o
módulo não resolve fica dito na célula e no relatório: recorte que não é furo redondo
nem oblongo desenhado como polilinha. **Chapa dobrada** sai com o desenvolvimento pela
linha média (largura × comprimento planificado, desenhado ao lado da vista lateral) e
**barra curva ou dobrada** com o comprimento de corte pelo volume ÷ área da seção, ambos
anotados na célula com o método; quando a conta não fecha, a célula diz que não calculou.

### Detalhamento no CAD do projeto (peças e conjuntos)

No editor 3D de um projeto, **Desenho 2D → Detalhar peças e conjuntos…** gera, a partir
do modelo já importado, desenhos editáveis no CAD (`nucleo2d/detalhar.py` é a fachada — reexporta tudo,
inclusive os nomes privados usados nos testes — e a orquestração `levantar`/`detalhar`/`desenho_completo`;
as partes ficam em `nucleo2d/detalhe/`: `base.py` (papel, posições, furos e parafusos, regra das terças,
categorias), `conjuntos.py` (instâncias, elevação, contraventamentos, localização), `nomes.py` (nomes de
produção) e `celulas.py` (célula da posição, chapa paramétrica, furos editáveis); rota
`POST /api/projetos/<slug>/detalhar`), no formato das pranchas de fábrica:

- um desenho por grupo — chapas (1:10), barras e terças (1:25), tirantes, telhas e
  conjuntos (1:50) — com uma célula por **posição**: título "T.C.1 – 28x  (M13)" — o
  **nome de produção** no padrão da fábrica e, entre parênteses, a marca do TecnoMETAL;
  as iguais são contadas, não repetidas —, perfil ou chapa com espessura (`#3/8"`), material, furos,
  peso, contorno com furos e cotas em cadeia (só quando cabem), seção da barra ao lado e
  vista de topo quando há furo na mesa;
- a **elevação de cada conjunto** (marca de montagem: tesoura, viga de painel, pilar),
  na orientação em que está montado (a tesoura inclinada, o pilar em pé; só o conjunto
  deitado no plano horizontal é girado para o comprido ficar na horizontal), com a
  cadeia de cotas dos nós embaixo e em cima, altura, rótulo de posição em
  cada barra, título "M2 – 08x" e a lista de perfis e posições. O número de instâncias é
  o máximo divisor comum das quantidades por posição dentro da marca (8 pórticos M2 =
  80 P10, 64 P11, 64 P12 → 8); a instância desenhada é um agrupamento espacial com a
  composição unitária. Marcas diferentes com a mesma geometria (o TecnoMETAL numera
  por pórtico) saem numa célula só, "M17 / M46 – 04x";
- a **planta de localização** (grupo `localizacao`): planta e duas elevações esquemáticas
  do modelo inteiro (cada peça é o contorno convexo da projeção, em linha fina; telhas
  ficam fora) com a marca de cada conjunto e de cada peça solta escrita no lugar de
  montagem — é a planta que diz onde vai cada item detalhado. Instâncias de conjunto por
  conectividade das caixas (`_instancias`); um grupo com k unidades encostadas (as duas
  águas de um pórtico na cumeeira) é dividido ao longo do eixo comprido (`_dividir`);
- `detalhamento/relatorio.json` e a lista de materiais (abaixo).

Desenhos gerados podem ser excluídos em lote (**Excluir desenhos…** no menu Desenho 2D do
editor 3D e no menu Desenho do CAD; × ao lado de cada desenho salvo no editor): vão para a
`.lixeira` da pasta de dados (`POST …/desenhos/<nome>/excluir`).

Medidas ao milímetro (`saida.detalhamento._arredondar`: comprimento, chapa e furos; espessura
e diâmetros ficam) e posições iguais fundidas (`nucleo2d.detalhar.fundir_posicoes_iguais`:
mesma classe, perfil, material, comprimento, altura, espessura e furos → "P64 / P65 / P66",
`marcas_de(pos)` guarda as originais; `/aplicar-furos` e `regenerar_celula` aceitam o rótulo).

Chapa sem furo na malha (caixa de 8 vértices): `inferir_furos_de_parafusos` cruza o eixo
de cada fixador (`TIPOS_ACESSORIO`; parafuso comprido → eixo maior, porca achatada → eixo
menor) com o plano médio da chapa e abre Ø d + 1 (d do nome "12x35" ou da porca por entre
faces). Vínculo chapa → terças: `vincular_furos_de_ligacao` (mesma lógica de assinatura da
regra de fábrica) grava `detalhamento/ajustes-furos.json`, aplicado por
`aplicar_ajustes_de_furos` em `levantar(..., ajustes=)`. No CAD, `Mover._cotasLigadas` leva as
cotas presas à coluna/linha dos furos movidos.

Ao aplicar furos, `_mover_fixadores` leva junto os fixadores cujo eixo passa pelo furo movido
(até 120 mm de cada lado da chapa). `POST …/modelo` aceita `base_alterado` (mtime do modelo
carregado) e recusa gravar por cima de um modelo mais novo; o editor 3D pára o autosave e pede F5.

Orientação dos conjuntos (`_eixos_do_conjunto`): a normal da vista é o eixo mais fino do
conjunto e a vertical do desenho é a vertical da obra projetada — a tesoura sai inclinada
como montada. Conjunto **linear** (segunda extensão < 12 % da primeira: tirante com as
chapinhas, viga de uma barra, pilar) sai deitado na horizontal, com o comprimento total
legível; deitado no plano horizontal é visto de cima. O triedro segue a convenção do
gerador de vistas (`Vista.eixos`: observador em −w, direita = w × v) — é o que garante que
os rótulos de posição caem sobre as barras desenhadas. Os rótulos ficam na perpendicular
da barra e afastam-se quando cairiam um sobre o outro; **saem desligados por padrão**
("Rotular posições nos conjuntos"): a fábrica gabarita a tesoura e mede peça a peça, e o
nome ao lado de cada barra mais atrapalhava. Nas prateleiras (`_empilhar`) a linha inteira
desce quando uma célula é mais alta que a primeira, para o título não invadir as cotas da
linha de cima.

**Quadros por tipo** (`detalhar._quadros_por_tipo`): o desenho de conjuntos agrupa as
células por tipo — TESOURAS, VIGAS, PILARES, CONJUNTOS, AGULHAMENTOS, CONTRAVENTAMENTOS —,
cada grupo empilhado à parte e dentro de uma moldura com título (camada AUXILIAR), um
quadro abaixo do outro. Antes saíam numa fila só, na ordem do IFC. O **desenho completo**
usa os mesmos quadros: um por grupo de posições (CHAPAS, BARRAS E TERÇAS…), os de conjuntos
por tipo e a planta de localização. A moldura cerca a extensão real (`detalhar._extremos_de`:
linha de cota deslocada com o número e largura estimada do texto), não só os pontos que
definem as entidades — antes as cotas das tesouras saíam para fora do quadro.

**Telhas pela chapa de compra** (`detalhe.base.compra_da_telha`, `celulas._desenho_da_telha`):
a telha é comprada inteira e cortada na obra. A célula mostra a chapa inteira (comprimento
da peça × **largura comercial**, `LARGURA_COMPRA_TELHA` = 980 mm — o TecnoMETAL modela a
TP40 com 1031) com as ondas de ponta a ponta, tiradas dos vértices da peça inteira (a
seção de uma ponta cortada em diagonal pega só parte da largura), e o corte que a peça tem
no modelo (ângulo do beiral, curva do canto) em **pontilhado**, camada OCULTA. O peso é o
da chapa inteira (o da peça × retângulo / área do casco). A lista de materiais segue a
mesma regra e diz quantas chapas de cada comprimento comprar.

**Unidade do conjunto pela maioria** (`detalhar._unidade_pela_maioria`): as instâncias de
um conjunto saem do mdc das quantidades por posição; uma peça a mais ou a menos numa delas
(29 P13 em 8 tesouras de 4) derrubava o mdc para 1 e o conjunto inteiro saía desenhado como
se fosse uma instância. Quando ≥ 80 % das posições têm quantidade múltipla de um mesmo n, a
unidade é quantidade/n; a instância desenhada é uma das que batem com ela, e o aviso diz o
que difere no total. Conjunto espalhado em vários grupos nunca é desenhado inteiro.

**Canto da tesoura em meia-esquadria** (`conjuntos._chanfrar_cantos`): o banzo calandrado
do joelho chega do IFC como um arco, mas a fábrica não calandra — corta os dois banzos
retos em diagonal e solda. Na elevação do conjunto cada arco da silhueta da peça
`barra_conformada` vira o canto vivo (interseção das tangentes nas duas pontas do arco) e
a emenda sai como linha do canto de fora ao de dentro. O modelo 3D e a célula da peça
continuam com o arco. Na célula da **terça** a cadeia vertical dos furos não sai (a
altura dos furos é o padrão da máquina de corte: 50 ou 100 mm); ficam a altura da peça e
as cotas horizontais.

**Regra da furação das terças** (padrão da máquina da fábrica, opção ligada por padrão):
terça com menos de 200 mm de altura fura a 50 mm na vertical e 60 mm na horizontal; com
200 mm ou mais, 100 × 60. Terça é a barra U/C/Z de 50 a 400 mm que viaja solta (marca de
posição igual à de conjunto). A regra vale para o que compõe a ligação da terça: toda
posição com um grupo de furos de furação original igual à da terça, em qualquer
orientação (a chapinha do suporte), recebe a mesma substituição; o centro do grupo é
mantido e a célula diz "furação no padrão de fábrica". Padrão quadrado ou terças de
alturas diferentes com a mesma furação original saem com "conferir".

**Atualizar de dentro do trabalho**: `web/atualizacao.js` põe o botão "Atualizar → x.y.z" ao lado de
Tema no editor 3D, no CAD e na lista de materiais quando há release nova (janela própria, programa
instalado); ao clicar, a tela grava o pendente (`window.__antesDeAtualizar`), `POST /api/atualizacao/instalar
{reabrir}` guarda o caminho em `<dados>/reabrir.json` e o programa reabre nessa tela
(`_url_para_reabrir`, válido por 15 min).

**Nomes de produção** (`nucleo2d.detalhar.nomear`, guardados em `detalhamento/nomes.json` para
não mudarem entre gerações): tesouras (conjuntos com 8+ barras) `T1, T2…`; terças de cobertura
`T.C.n` (mesmo perfil e comprimento = mesma família; só a furação diferente = `T.C.n-A`, `-B`…)
e de marquise `T.M.n` (centro fora da caixa dos pilares em planta); suportes de terça `S.T.n`
(a chapa em que a ponta de uma terça encosta, a menos de 200 mm — `_chapas_onde_a_terca_encosta`);
agulhamentos `A.G.n` (conjunto de uma barra com chapinhas de ponta: a barra leva o nome do
conjunto e as chapinhas são `S.A.G.n`); contraventamentos `C.V.n` (o tirante leva o nome do
conjunto; cantoneiras e chapas de ponta `S.C.V.n`, castanhas `C.S.n`, barra roscada `B.R.n`,
gancho `G.n`); demais chapas `CH.n`, barras `B.n`, telhas `TL.n`, conjuntos `CJ.n`. A peça que só
existe dentro de outro conjunto (que não seja tesoura) chama-se pelo conjunto: `CJ.1.1`. O painel
Propriedades do editor 3D mostra o nome e o nome do conjunto (`marcas.nome`). Numeração por quantidade decrescente; nomes únicos entre posições e conjuntos.
O nome vai para o título das células, os rótulos da elevação, a planta de localização, a
lista de materiais (coluna "Nome", CSV, HTML e PDF), a tabela das pranchas e para
`marcas.nome` / `marcas.nome_conjunto` das peças do modelo 3D (a pesquisa do editor acha
"S.T.1").

**Conjuntos iguais a menos de décimos** (`_assinatura_conjunto` + `_conjuntos_iguais`): mesma
composição por posição fundida, extensões a 3 mm, cada peça a 8 mm da correspondente e o
mesmo **lado** (`_lado_do_conjunto`: para onde a tesoura sobe no desenho — a água esquerda e
a direita ficam em células separadas, uma de cada lado) viram uma célula ("M17 / M46 – 04x").
Conjunto **semelhante** (`_conjuntos_semelhantes`: mesmo lado, dimensões a 20 mm e 75 % das
peças em comum — a tesoura de ponta com outra chapa de base ou uma diagonal a menos) entra na
mesma célula, desenhado o líder e cada variante anotada ("M7 – 02x: +P26 x1; -P1 x1";
`conjuntos_info[..]["variantes"]`) — decisão do usuário: um detalhe por lado.
Todas as cotas dos detalhes saem em **milímetro inteiro** (`_Papel.cota_h/cota_v/cadeia_*`).
Na elevação do conjunto, a cadeia de nós de um banzo inclinado (mais de 2°) é **alinhada ao banzo**
(`_Papel.cadeia_alinhada`): distâncias medidas na própria barra, como se marca na produção. Acima
dela sai a **cadeia dos suportes de terça** (chapas em pé encostadas no banzo de cima, fundidas a
60 mm), quando não coincide com a dos nós. O título de cada célula começa pelo **tipo** em caixa
alta ("TESOURA", "TERÇA DE COBERTURA", "CONTRAVENTAMENTO"). Tesouras semelhantes toleram 3 % nas
dimensões (a chapa de base maior). **Contraventamentos** com as mesmas peças de ponta saem num
detalhe só (`desenho_de_contraventamentos`): elevação do mais comprido, cotas empilhadas
"C.V.3 (02x) – 5150" por contraventamento, cotas das peças de ponta com o nome ("230  B.R.1") e,
no título, o tirante de cada um com o comprimento de corte. Barra roscada é `B.R.n`; redondo curto
(< 600 mm) é gancho `G.n`. A regra das terças também torna **oblongos** todos os furos redondos da terça na vista de
frente (Ø13 → 25x13, rasgo no sentido da barra; `oblongar_tercas`, depois da regra e dos ajustes)
— a chapinha do suporte fica redonda; `_arestas_dos_furos` esconde o cilindro inteiro do furo da
malha atrás do símbolo. As **cotas dos furos** das células saem sempre: trecho curto demais para o
número (35 mm da ponta em 1:25) vai para uma segunda linha alternada (`cadeia_h` devolve "dupla" e
a total sobe uma linha).

**Prancha de índice** (`pranchas._prancha_indice`, `montar_pranchas(..., indice=True)`, padrão na rota
`/pranchas`): a prancha 01 relaciona as pranchas (número, conteúdo, nº de vistas) e traz a tabela de
todas as posições e conjuntos — nome, marca, quantidade, perfil, comprimento e a prancha em que cada
um está —, em ordem de nome, em colunas. As pranchas de conteúdo passam a 02…N; `metadados.prancha.celulas`
guarda `marca` e `item` resumido de cada vista. Desenho de uma célula só (detalhe de uma peça) recebe a
chave da posição (`celulas_de`). O desenho completo não entra nas pranchas por padrão (repete as células).

**Furos das barras editáveis** (`aplicar_furos_de_barra`): a célula de uma barra (detalhe pelo duplo
clique ou desenho geral) traz os furos da alma como entidades FURO; "Aplicar furos" guarda a furação
nova em `ajustes-furos.json` (é o que o detalhamento seguinte usa) e move os furos na malha 3D com
`aplicar_furos_nas_barras` (até 300 mm por furo; furo novo ou apagado vale só no desenho). Os furos da
mesa (vista de topo) continuam os da malha. `_origem_da_celula` dá o canto da célula sem contorno fechado.

**Parafusos nos detalhes** (`parafusos_da_posicao`): os fixadores do IFC cujo eixo atravessa um furo da
peça (uma instância) são contados por rosca × comprimento — "parafusos: 4x M12 x 35" no título da
célula, coluna "Parafusos" na lista de materiais, no romaneio e no HTML/PDF; fixador sem tamanho no
nome (porca, chumbador) é contado à parte. Chapa sem furo e sem parafuso ganha a nota "chapa soldada".
A elevação do conjunto lista os parafusos dentro da instância (`parafusos_no_conjunto`). O IFC do
TecnoMETAL não traz soldas: o símbolo de solda continua fora.

**Desenho completo** (`desenho_completo`, grupo `completo`, padrão ligado): todos os grupos num desenho só,
em faixas com título (CHAPAS, BARRAS E TERÇAS, TIRANTES, TELHAS, CONJUNTOS, PLANTA DE LOCALIZAÇÃO), na
escala 1:25 — as células são desenhadas de novo nessa escala (`_anexar_faixa` translada cada faixa
para baixo da anterior e funde células e metadados; as chapas continuam editáveis ali); a planta entra
como está. Os desenhos por grupo continuam saindo nas escalas próprias, para as pranchas.

**Camadas por tipo de peça** (`CAMADAS_PECAS`, paleta das camadas do 3D): TERCAS, BANZOS,
DIAGONAIS, MONTANTES, CHAPAS, TIRANTES, PILARES, VIGAS, TELHAS. O traço forte de cada peça vai
na camada do seu tipo (`_Papel.camada_peca` nas células de posição; `_classificar_pecas_do_conjunto`
remapeia VISTA/CORTE na elevação do conjunto e vota a camada das posições — banzo, montante ou
diagonal pela posição da barra na elevação, porque o TecnoMETAL exporta montantes como
IfcColumn; `desenho_de_localizacao(camadas_pecas=…)`). As arestas finas continuam em
VISTA-FINA. A camada de cada posição fica em `nomes.json` (`camadas_2d`). O contorno da chapa
editável pode estar em VISTA ou CHAPAS (`CAMADAS_DE_CONTORNO`; CAD `_contornoDe`).

### Detalhe de uma peça ligado ao 3D (chapa paramétrica)

Duplo clique numa peça do editor 3D → `POST /api/projetos/<slug>/detalhar-posicao {marca, referencia}`:
sólidos de chapa plana da posição viram entidades `Chapa` (`nucleo2d.detalhar.converter_chapas`:
contorno, espessura e furos medidos pela análise, mesmo id e atributos). **Todas as instâncias
da posição saem no mesmo sistema**: a peça clicada (`referencia`) é medida na vista natural
(`_orientar_para_vista`: chapa deitada vista de cima, em pé vista de frente, comprimento
para +x) e cada outra recebe o triedro que põe a forma dela sobre a forma da referência
(`_eixos_pela_forma`: entre ±e1, ±e2, o de menor custo de forma; furo fora do centro decide
o sentido e, em forma simétrica, vale a vista natural) — a chapa montada virada ou espelhada
fica com o furo mexido no mesmo lado físico que as demais (`atributos.eixos_conferidos`).
Chapas convertidas por versões anteriores são refeitas uma vez a partir do IFC de origem do
projeto (`reorientar_chapas`, chamada por `app._conferir_eixos_das_chapas`), mantendo a
furação atual da referência em todas e levando os parafusos junto.
O desenho "Detalhe – P77" sai com os furos como entidades marcadas da camada
FURO (`desenho_da_posicao(..., editavel=True)`, `metadados.detalhe_posicao`). No CAD,
**Aplicar furos ao modelo 3D** (`POST …/desenhos/<nome>/aplicar-furos`) lê círculos e
polilinhas fechadas da camada FURO, escreve nas chapas da posição (`aplicar_furos`; só a
chapa medida sozinha, sem `eixos_conferidos`, ainda decide o espelhamento pelos furos
originais — `_simetria`), regrava o modelo e regenera o detalhe. As terças vinculadas
(`ajustes-furos.json`) têm os furos movidos também **nas malhas do 3D**
(`aplicar_furos_nas_barras`: os vértices de cada furo da malha — parede e as duas faces —
transladam no plano da alma ou da mesa até a posição do ajuste; só quando a malha tem os
mesmos furos, cada um a menos de 40 mm do alvo; repetir não mexe). Chapas paramétricas entram no detalhamento geral
como sólidos equivalentes (`_proxy_da_chapa`); a malha 3D (`geometria.malha_chapa`) e a
cena do editor abrem furos redondos e **oblongos** (`{x, y, largura, altura}`).
O detalhamento geral (`detalhar(..., converter=True)`) converte todas as chapas planas
(`converter_chapas_planas`) e as células de chapa saem editáveis
(`metadados.detalhamento.editaveis` e `furos_originais`); `/aplicar-furos` com `marca` lê
furos e contorno da célula (`contorno_do_desenho`, `furos_do_desenho`), aplica (contorno
mudado = tamanho ajustado) e regenera a célula no lugar (`regenerar_celula`).
**Ver no 3D** (CAD) abre o editor com `destacar=posicao:P77` — peças selecionadas,
enquadradas e o resto do modelo em fantasma (`cena.destacar`). Chapa com nome nominal e malha até 1 mm menor sai com a dimensão nominal
(`saida.detalhamento._ajustar_ao_nominal`).

### Lista de materiais

`saida/lista_producao.py`, tela `/materiais?projeto=<slug>` (menu **Desenho 2D → Lista de
materiais…** no editor 3D, **Vistas do modelo → Lista de materiais…** no CAD, pílula no
gerenciador). Sai do mesmo levantamento do detalhamento (`nucleo2d.detalhar.levantar`):

- **romaneio por posição** (marca, conjuntos, tipo, perfil/chapa, material, quantidade,
  dimensões, furos, pesos, observações);
- **perfis**: peças, comprimento total, kg/m, peso e **barras comerciais** por encaixe
  "primeiro que cabe, do maior para o menor" em barras de 6 m (12 m quando alguma peça
  passa de 6, ou fixado pelo usuário), com 3 mm de perda por corte, aproveitamento, sobra
  e peças com emenda;
- **chapas** por espessura e material (área pelo contorno ou desenvolvimento, peso);
- **conjuntos**: instâncias pelo mdc, composição e peso da montagem;
- **acessórios** contados e **totais por categoria**.

Rotas: `GET /api/projetos/<slug>/materiais` (a gravada, ou levanta do modelo na hora),
`POST …/materiais` (recalcula; `barra`: 0, 6000 ou 12000), `POST …/materiais/pdf`. Arquivos em
`detalhamento/`: `lista-de-materiais.json`, `romaneio.csv`, `resumo-perfis.csv`,
`resumo-chapas.csv`, `conjuntos.csv`, `lista-de-materiais.html` e `Lista-de-materiais.pdf`
(Chrome, A4 paisagem, padrão visual do memorial). A rota `/detalhar` regrava a lista.

### Pranchas com carimbo

No CAD, **Desenho → Montar pranchas…** (rota `POST /api/projetos/<slug>/pranchas`,
`nucleo2d/pranchas.py`) monta folhas A0–A4 em paisagem com moldura, quadro e carimbo
(obra, cliente, título, responsável, escala, data, número "01/07", revisão). Cada posição
ou conjunto dos desenhos de detalhamento vira uma vista na escala do desenho de origem;
cortes e vistas entram inteiros, agrupados em **quadros por categoria** com título —
tesouras e pórticos, conjuntos menores, terças, barras, chapas, tirantes, telhas, vistas —
que continuam na prancha seguinte quando não cabem. O que não cabe na escala desce para
a normalizada seguinte, com nota. **Todas as pranchas ficam lado a lado num desenho só**
("Pranchas", 28/09), em milímetro de papel (escala 1), editável como qualquer outro; cada
folha está em `metadados.pranchas` com a origem dela, a moldura e o carimbo levam `folha`
(o clique na borda pega a folha inteira; o carimbo edita pelo painel) e o DXF sai em
papel 1:1: a cota guarda o valor original como texto. As células de uma prateleira alinham
pelo topo (os títulos numa linha), a caixa de cada célula conta a linha de cota e o número
(a cadeia de cotas sob a terça não invade a linha de baixo), e "(continuação)" só aparece
quando o quadro já começou na folha anterior. **Gerar pranchas das folhas** (o caminho à mão,
com folhas postas no desenho de trabalho) grava no mesmo desenho "Pranchas": as folhas
geradas antes de outros desenhos ficam, na ordem, e as do desenho atual são refeitas, com a
numeração correndo por todas. Cada prancha traz, no rodapé à
esquerda do carimbo, a **tabela das posições** que contém (marca, quantidade, perfil,
comprimento, peso). Para escolher à mão o que vai numa prancha, selecione as células no
desenho de detalhamento antes de abrir o diálogo e marque "só as peças selecionadas".
**Desenho → Importar DXF neste desenho…** traz um DXF em texto (R12 a R2018: linhas,
polilinhas com arcos, círculos, textos e MTEXT, blocos aninhados, cotas como o CAD de
origem as desenhou; hachura e imagem ficam de fora) para a escala do desenho aberto,
com a unidade do arquivo (`$INSUNITS` ou escolhida) e ponto de inserção; entra como um
comando, então Ctrl+Z desfaz. DWG não é lido: salve como DXF no CAD de origem.
**Desenho → Exportar PDF** gera o PDF vetorial do desenho aberto (o desenho das pranchas sai
uma página por folha, cada uma renderizando só o que é dela; a prancha solta no tamanho da
folha; desenho comum no tamanho dele na escala) e **PDF de todas as pranchas…** junta as
pranchas do projeto num arquivo em `pranchas/`, pronto para plotar.

## O que sai

| Entrega | Formato | Onde |
|---|---|---|
| Detalhamento de peças de um IFC | DXF único, CSV e JSON | `projetos/<nome>/detalhamento/` |
| Lista de materiais de produção | tela, CSVs para Excel, HTML e PDF | `projetos/<nome>/detalhamento/` |
| Memorial de cálculo | PDF, cerca de 50 páginas | `projetos/<nome>/memorial/` |
| Desenhos | 11 arquivos DXF (R12, abrem em qualquer CAD), do pórtico ao nó de contraventamento, mais os diagramas de M, V e N e o quadro de verificações | `projetos/<nome>/desenhos/` |
| Pranchas | PDF A1, A2 ou A3 com carimbo; a folha sai da escala em que cada desenho foi cotado | `projetos/<nome>/pranchas/` |
| Lista de material | CSV para Excel e PDF | `projetos/<nome>/lista/` |
| Modelo BIM | IFC4, exportado pelo editor 3D | `projetos/<nome>/ifc/` |
| Modelo 3D editável | JSON do editor | `projetos/modelos/` |

## Estrutura

```
sistema/
├── app.py                servidor web local (só biblioteca padrão)
├── nucleo/               cálculo
│   ├── base.py           Verificacao, Resultado, Passo, constantes
│   ├── materiais.py      aços, parafusos, eletrodos, concreto
│   ├── perfis.py         catálogo (W, HP, U, Ue, L, tubos)
│   ├── cargas.py         NBR 6120, NBR 6123, NBR 8681
│   ├── analise.py        pórtico plano pelo método da rigidez
│   ├── nbr8800.py        barras de aço laminado e soldado
│   ├── nbr14762.py       perfis formados a frio (terças e longarinas)
│   ├── ligacoes.py       parafusos, soldas e ligações típicas
│   ├── bases.py          placa de base, chumbadores, chave
│   ├── galpao.py         orquestrador de todas as etapas
│   └── modelo_galpao.py  contrato de entrada e saída
├── nucleo3d/
│   ├── modelo.py         documento 3D: barras, chapas, sólidos, camadas, materiais
│   ├── geometria.py      seções de perfil, extrusão, malhas, operações de edição
│   └── de_projeto.py     gera o modelo 3D do galpão dimensionado
├── ifc/
│   ├── step.py           leitor do formato STEP (ISO 10303-21)
│   ├── exportar.py       documento 3D para IFC4
│   └── importar.py       IFC para documento 3D
├── saida/                memorial, desenhos DXF, pranchas, lista
│   ├── detalhamento.py   peças de um IFC para produção (DXF único e romaneio)
│   └── lista_producao.py lista de materiais do detalhamento (perfis, barras, chapas, conjuntos)
├── web/                  interface de dimensionamento (HTML, CSS e JS puros)
│   ├── editor3d/         editor 3D: núcleo e ferramentas
│   └── lib/              Three.js r160, servido localmente
├── dados/perfis.json     catálogo de perfis
├── testes/               cerca de 500 testes
└── projetos/             projetos salvos e arquivos gerados
```

No catálogo, tubos redondos têm o prefixo `TC` e tubos retangulares e quadrados, `TR`
e `TQ`.

## Progresso das operações longas

Importar IFC, detalhar e a conferência dos eixos das chapas publicam a etapa corrente em
`app.PROGRESSO[slug]` (`_progresso`/`_fim_progresso`; `detalhar()` chama `avisar` a cada etapa) e
`GET /api/projetos/<s>/progresso` a devolve; o editor 3D e o CAD (`_acompanharProgresso`) mostram-na na
linha de dica a cada 0,7 s enquanto esperam a resposta.

## Histórico do modelo e projeto aberto

`Projetos.salvar_modelo(..., marco=True)` guarda antes o modelo anterior comprimido em
`<projeto>/historico/modelo-AAAAMMDD-HHMMSS[-marco].json.gz` (operações que mudam peças: aplicar furos,
detalhamento, migração, restauro); sem marco, uma cópia a cada 10 min no máximo; ficam as 8 últimas.
`GET /api/projetos/<s>/historico` lista; `POST .../restaurar-modelo {arquivo}` volta a uma delas (a atual vai
para o histórico antes). No editor 3D: Arquivo → Restaurar modelo anterior…

Ao abrir o modelo (`GET .../modelo`) e a cada sinal de vida da página (`/api/vivo?p=<slug>`, web/vivo.js) o
servidor grava `<projeto>/aberto.json` {máquina, usuário, hora} (no máximo a cada 60 s; apagado ao fechar).
A tela Projetos e o editor avisam quando outra máquina tem o projeto aberto há menos de 3 min — é o caso
de duas máquinas na mesma pasta do OneDrive; a guarda `base_alterado` continua a impedir gravar por cima.

## Cálculo do modelo importado (IFC de fábrica)

`nucleo3d/calculo_ifc.py` monta o modelo de cálculo a partir dos sólidos do TecnoMETAL, sem barra
paramétrica: cada instância de conjunto classificado como **tesoura** (nomes.json do detalhamento)
vira um pórtico plano no seu plano — banzos contínuos divididos nos nós, diagonais e montantes
rotulados, nós nos pontos de trabalho, peças geminadas (dois U) somadas; peças de ponta livre
(consoles de apoio à coluna, que não está no modelo) ficam fora com aviso; apoios nos nós mais
baixos de cada extremidade, ou nos pontos informados (`apoios`). Toda barra fora das tesouras cujo
eixo cruza o plano da tesoura junto ao banzo superior é **terça** (reação do trecho tributário como
carga concentrada) e junto ao inferior é **travamento**. Cargas: peso próprio medido (perfil e
chapas), telha pela espessura do nome ou informada, sobrecarga (0,25 kN/m²), vento NBR 6123 com a
geometria lida (vão, comprimento, inclinação, cota do apoio) — cobertura de uma água usa a sucção
mais severa das duas águas. Combinações como no galpão. Verificação por posição (marca), com os
piores esforços entre as instâncias: U/Ue formados a frio pela NBR 14762 (MRD; U simples sem
enrijecedor em `propriedades_u`, mesa AL, sem modo distorcional), cantoneiras/W/tubos pela NBR 8800
(cantoneira fria com fator Q), terças pela rotina de terça (correntes contadas no modelo), redondas
à tração. Perfis pelo nome de fábrica em `nucleo/perfis_fabrica.py` (U92X40X2.25,
C150X75X20X2.25, L1.1/4''X1/8'', W150X13.00, FE RED 3/8''…); aço CIVIL 300/350 no catálogo.

Rotas: `GET /api/projetos/<s>/calculo/geometria` (o que o diálogo precisa), `POST .../calcular
{parametros, trocas, comparar}` (grava `<projeto>/calculo.json`; `trocas` = {marca: perfil de
cálculo}, `comparar` devolve `antes`), `GET .../calculo`. No editor 3D, **Calcular estrutura**
num projeto importado abre o diálogo (vento, cargas, travamentos, apoios, aços) e pinta o mapa;
o cálculo gravado volta ao abrir o projeto. Em "Peça selecionada", **Perfil de cálculo** troca o
perfil da posição (catálogo, perfis do projeto ou nome de fábrica), recalcula e mostra o que mudou;
o sólido do modelo continua o de fábrica.

**Alternativas de perfil verificadas** (`calculo_ifc.alternativas(calculo, marca)`, rota
`GET /api/projetos/<s>/calculo/alternativas?marca=`): pega os candidatos do catálogo (mesma família, altura
entre metade e o dobro) e **verifica cada um com os esforços já gravados** do cálculo — responde em
décimos de segundo porque não refaz a análise. Cada candidato volta com aproveitamento, verificação que
governa e o impacto no peso (diferença de massa por metro × comprimento total daquela posição no modelo,
que o cálculo passou a guardar em `comprimento_total_m`/`peso_kg`; o total fica em
`resumo.peso_verificado_kg`). Ordem: quem passa primeiro, do mais leve ao mais pesado; quando nada passa,
os que chegam mais perto. No editor é o bloco "No lugar dela" da peça selecionada, e clicar aplica a troca
— aí sim o cálculo inteiro é refeito, porque trocar o perfil redistribui os esforços na treliça.

**Ligações**: cada diagonal e montante é verificado também na ligação com o banzo, e o
resultado sai em `ligacoes` (uma linha por chapa-ou-banzo × barra, com o pior esforço entre
todos os nós, como a fábrica detalha). Há três casos, decididos pela geometria lida do modelo:
chapa de nó **parafusada** (furos da chapa na faixa da barra: diâmetro pelo furo, passo e borda
medidos — Whitmore, cisalhamento e esmagamento dos parafusos, bloco de cisalhamento), chapa de
nó **soldada** (sobreposição da barra sobre a chapa medida ao longo do eixo — Whitmore e dois
cordões de filete) e, sem chapa sobre a barra, a **solda da diagonal direto no banzo**, que é
como a treliça leve de Ue é fabricada: contato = altura do banzo / sen θ, dois cordões, perna
mínima da Tabela 10 limitada pela chapa mais fina (item 6.2.6.2.2). Chapinha de terça e chapa
de apoio perto do nó não recebem a barra e ficam de fora sozinhas. Cada barra guarda a pior
ligação dela (`elementos[marca]["ligacao"]`), e **"No lugar dela" reverifica a ligação com
cada candidato**: a diagonal mais fina passa na barra e reprova na solda, e a lista mostra os
dois aproveitamentos. No editor, o bloco *Ligações* do painel do cálculo lista tudo; clicar
seleciona a chapa e as barras da ligação. Parâmetros novos: `parafuso` (classe, o IFC não
diz) e `eletrodo`.

Limites: contraventamentos, agulhamentos e consoles não são verificados (sem cargas de oitão);
a ligação da tesoura ao pilar (chapa de apoio) e a solda dos suportes de terça não entram; o
IFC não traz a solda, então perna e cordões são os adotados acima e ficam declarados na
observação de cada verificação; a chapa de nó comprimida é verificada como escoamento de
Whitmore, sem flambagem; terças de beiral apoiadas nos consoles ficam sem apoio; sem
travamento lido no modelo o banzo inferior é verificado com o comprimento inteiro (informe
`trava_inferior`); as tabelas de vento são de galpão fechado de duas águas.

### Memorial de cálculo por peça (quatro camadas)

`saida/memorial_peca.py` escreve, para cada posição verificada do cálculo do IFC, um memorial que o profissional confere
e o iniciante entende: **1 resumo** (uma linha por peça do mesmo tipo), **2 hipóteses** (as decisões anteriores à conta,
por extenso, cada uma com a fonte — medida no modelo, informada no diálogo, adotada pela rotina, exigida pela norma, do
catálogo), **3 conta** (da carga por m² ao esforço, e cada verificação passo a passo com o item da norma) e **4 explicação**
(recolhida em cada item: o que protege, o fenômeno, o que pesa, o erro típico; textos em `saida/didatica.py`). As hipóteses
e os passos das cargas nascem no cálculo (`Resultado.hipoteses`, `Resultado.cargas`) e vão ao `calculo.json`; o memorial não
calcula. Tela `/memorial?projeto=<s>&marca=<posição>` (pelo painel do cálculo no 3D), PDF profissional (sem a camada 4) e
didático em `<projeto>/memorial/`. Hoje só a terça registra hipóteses e cargas; as outras peças saem com as camadas 1 e 3 e
a lacuna marcada. A trilha combinada estende isso na ordem terça → tesoura → pilar → vento → ligações.

## Lançar a estrutura sobre o arquitetônico

O caminho de um projeto que começa na planta do cliente (`nucleo3d/lancamento.py`):

1. **Arquitetônico do cliente** (CAD -> Lançamento, ou "Novo a partir do arquitetônico..." na tela inicial): DXF ou PDF
   vetorial vira a Planta de lançamento, em milímetro real, com as camadas "ARQ ..." cinza e travadas. Confira uma medida
   com Medir (U); se a unidade do arquivo estiver errada, **Calibrar escala** (dois cliques e a medida real).
2. **Malha de eixos...** (ou linhas desenhadas à mão na camada EIXO, com os nomes nas bolinhas) e **Gravar eixos no
   projeto**. Números são os pórticos; letras, as filas de pilares. As duas direções têm de ser perpendiculares.
3. **Lançar estrutura no 3D**: sistema (tesoura apoiada com base engastada, tesoura rígida ou alma cheia), pé-direito,
   inclinação, terças, correntes, telha, cargas, vento. O galpão é dimensionado com o maior espaçamento entre eixos e
   montado nos eixos reais, com marcas de posição e conjunto; o modelo anterior vai para o histórico.
4. Dali o caminho é o de sempre: Detalhar peças e conjuntos, Lista de materiais, Calcular estrutura (confere o modelo
   depois de editado), Memorial do dimensionamento (PDF) e Exportar IFC.

Limites: galpão retangular de vão livre (eixos com letra intermediários ficam sem pilar), sem ponte rolante nem mezanino.

## Ligações e acessórios

`nucleo/acessorios.py` é a biblioteca das ligações e dos acessórios de uma estrutura metálica: cada tipo gera as peças
(chapas com furos e oblongos, barras, parafusos, porcas, com peso), o desenho em SVG com cotas e, com os esforços de
cálculo, a verificação pela NBR 8800 com as rotinas de `nucleo/ligacoes.py` e `nucleo/bases.py`. Os padrões vêm das
obras da Sooro. A tela `/ligacoes` mostra tudo isso e, em "Nas obras", as peças reais das obras detalhadas que
correspondem ao tipo (`exemplos_das_obras`, lendo `detalhamento/lista-de-materiais.json` e `nomes.json`). O lançamento
usa a biblioteca para gerar no modelo os suportes de terça, o apoio da tesoura no pilar e os chumbadores
(`nucleo3d/lancamento._gerar_ligacoes`). Um tipo novo é um `Tipo` registrado com `_registrar`: parâmetros, esforços,
`gerar(p) -> (peças, svg, notas)` e `verificar(p, e) -> Resultado`.

## Versão que cada janela está rodando

`web/versao.js` (em todas as páginas) escreve `v<versão>` no rodapé: é a versão do **código que aquela
janela carregou**. De minuto em minuto pergunta ao servidor; se ele passou a responder outra versão (o
programa foi atualizado com a janela aberta), o rótulo fica amarelo com "recarregar para vX" e um clique
recarrega. Janelas abertas antes de uma atualização continuam com o código antigo até serem recarregadas.

## Testes

```bash
python -m pytest testes/ -q
```

Os exemplos resolvidos do manual (capítulos 5, 7, 8, 9, 10 e 16) são reproduzidos como
teste, com tolerância de 1 %. É a validação independente do código de cálculo. Quatro
testes do IFC ficam pulados quando o `ifcopenshell` não está instalado; os demais
conferem a sintaxe STEP, a integridade das referências e a ida e volta pelo importador.

O editor 3D roda no navegador, então não entra no `pytest`. Os verificadores das telas abrem o
Chrome sem janela e trabalham nas telas de verdade; o jeito de rodar é pelo executor, que sobe um
servidor de teste numa porta livre com uma pasta de dados temporária:

```bash
python testes/rodar_verificadores.py            # todos, 3 em paralelo, os mais demorados primeiro
python testes/antes_de_publicar.py [--completa] # pytest + verificadores + bateria das obras
```

Os três roteiros antigos (`testes/verificar_editor.py`, `verificar_editor_arquivos.py`, `verificar_zoom.py`)
pedem `--porta` de um servidor de teste (`app.py --sem-navegador --porta N --dados <pasta temporária>`) e
recusam a 8765 (o programa instalado) e a 8766 (o desenvolvimento): gravam modelos na pasta de dados.

### Verificadores headless e CI

`testes/verificadores/verif_*.py` sobem o servidor numa pasta temporária e exercitam a interface pelo Chrome
sem janela (CDP); a maioria usa o modelo de exemplo do cliente (`projetos/modelos/`), que não está no
repositório. `.github/workflows/testes.yml` roda o `pytest` no GitHub só à mão (desde 06/10: falhava em todo
push por causa do ambiente); a garantia é a conferência antes de publicar.

## Montar o 3D pela planta (projeto recebido sem 3D)

`nucleo3d/de_planta.py`. Para o projeto de escritório que chega completo em DXF (plantas, elevações de cada treliça,
listas) mas sem modelo. As plantas ficam em lugares diferentes do arquivo; a moldura de cada uma é o desenho logo acima
do título (os grupos a menos de 8 m se juntam), e o alinhamento entre elas é a mediana dos balões de eixo de mesmo nome.
Elevações: `ler_elevacoes` (título "FAMÍLIA n - kX", o desenho logo acima dele, nota dos perfis entre os dois, marcas
ST pela ponta da chamada). Planta: `pecas_da_planta` (linhas de centro retas, arcos e compostos; nome → peça;
corte pelo comprimento da elevação). Sentido: `orientar`. Montagem, pilares, terças e acessórios: `montar`, que devolve
o documento, o resumo (com as quantidades do projeto) e a conferência por nome de treliça. As barras levam em
`atributos.origem` o nome da planta e como o sentido foi decidido ("marcas ST", "encontro dos banzos", "costume do
desenho") e a peça de que fazem parte (`origem.peca`, "TESOURA 1#12"); pilar sem cobertura em cima leva `a_conferir`.
As regras de apoio (0.8.36) estão na montagem — treliça termina num nó ou pilar, terça termina num apoio e emenda em
cima de um, a elevação anda até os nós caírem nas terças — e são conferidas depois por `nucleo3d/apoios.py`
(Ver → Verificar apoios…). Limites: agulhas (AG) e suportes de terça (ST, SC) não entram
(são acessórios: chapas); a planta sem nome escrito na peça fica de fora (o resumo diz quantas); vigas VM entram no
nível do banzo inferior (a conferir no projeto); estruturas em outros níveis (mezanino, caixa d'água, passarela) ainda
não são montadas.

## Do desenho 2D para o modelo 3D

`nucleo3d/de_desenho.py` faz o caminho inverso do importador: um desenho do CAD vira modelo 3D com a
informação de cada peça. Cada linha (ou lado de polilinha) marcada com uma **peça do catálogo** vira uma
`Barra` com perfil, aço, papel, camada e — o que liga tudo o que vem depois — as **marcas por peça** em
`atributos["marcas"]`: `posicao` (P1, P2… por perfil e comprimento) e `conjunto` (M1, M2…, um por cópia),
no mesmo formato que o IFC de fábrica traz. Assim o modelo desenhado serve ao detalhamento, à lista de
materiais, ao cálculo e ao IFC sem caminho paralelo.

**Chapa de nó**: polilinha **fechada** com peça de chapa vira uma `Chapa` no plano do desenho, e os
círculos com centro dentro do contorno viram os furos dela. A espessura vem do item de chapa do catálogo
(`CH 9,53 mm (3/8")`) ou do campo `espessura` da peça. As chapas entram na mesma numeração de posições das
barras, agrupadas por espessura, área e número de furos.

A peça fica em `atributos["peca"]` da entidade 2D (`{perfil, papel, aco, rotacao}`) ou, valendo para tudo
o que está nela, em `desenho.metadados["pecas_por_camada"]` — é assim que se desenha uma tesoura: uma
camada por tipo de peça. Linha sem peça é anotação e fica de fora, contada no relatório.

`plano` põe o desenho no espaço (`frente`, `lado`, `topo`) e `repeticoes`/`espacamento` copiam ao longo da
normal: as oito tesouras do galpão saem de um desenho só. Rota
`POST /api/projetos/<s>/desenhos/<nome>/gerar-3d` (com `conferir: true` só levanta o que o desenho tem).
No CAD: **Peça do catálogo…** (seleção ou camada ativa) e **Gerar modelo 3D do desenho…**. Na tela de
projetos, **Novo desenhando em 2D…** cria um projeto do tipo `desenho`, que abre direto no CAD.

**Detalhamento de modelo desenhado**: `nucleo2d/detalhe/base._pecas` aceita `Barra` e `Chapa`
paramétricas, convertendo-as no sólido equivalente (`_proxy_da_barra`, `_proxy_da_chapa`) com a malha
montada dos próprios parâmetros. Com isso o detalhamento, o romaneio e as pranchas funcionam igual para
modelo importado, desenhado ou gerado do galpão.

O exportador de IFC passou a gravar as marcas (`Part Mark`, `Assembly Mark`, `Nome`) no
`Pset_MetalicaCalculo`, e o importador aceita o nome de perfil declarado quando o catálogo o conhece —
com isso um IFC gerado aqui volta como barra, com posição e conjunto. O cálculo (`calculo_ifc`) lê barras
paramétricas direto (`_CorpoDaBarra` dá a elas os vértices que o reconhecimento de tesouras espera), então
um modelo desenhado é calculado como um importado. Testes: `testes/test_de_desenho.py`.

## Catálogo de peças

`nucleo/catalogo.py` é o ponto único para "que peças existem": perfis I laminados (W, HP, I americano), U
laminados e formados a frio, Ue, Z enrijecido a 90° e a 45°, cartola, cantoneiras em polegada e em milímetro,
tubos, barras redondas e chatas, chapas, parafusos e telhas — cerca de 5.200 itens. Junta `dados/perfis.json` (tabelas de fabricante, extraídas pelo `extrai_perfis.py`)
com `dados/catalogo.json` (gerado por `dados/gerar_catalogo.py`: séries NBR 6355 e cantoneiras métricas
calculadas pelo método linear da NBR 14762, mais chapas, barras e parafusos das tabelas do anexo). Cada item
diz a `origem` — `tabela` ou `calculado` —, e quando o mesmo perfil está nos dois lugares vale o da tabela.

`itens()`, `item()` (tolerante à grafia: `ue150x60x20x2,65`), `buscar()` (nome ou dimensão), `perfil_de()`
(devolve o `Perfil` de cálculo, montando na hora os formados a frio e aceitando nome de fábrica fora do
catálogo) e `alternativas()` — o que pode entrar no lugar de uma peça, na mesma família (`TROCA_COMPATIVEL`:
U vira Ue e vice-versa; cantoneira não vira terça), com altura de seção entre metade e o dobro da atual
(`FAIXA_ALTURA`) e a diferença de massa por metro. O padrão é "vizinhos": metade mais leves, metade mais
pesados, os mais próximos.

**Fornecedores** (`dados/fornecedores/*.json`, transcrições dos catálogos públicos): Gerdau (W/HP, U, I,
cantoneiras, barras), ArcelorMittal, Vallourec (tubos sem costura, com a tabela completa), Marcegaglia (tubos
com costura, só massa — as propriedades são calculadas pela seção cheia menos o furo), Perfinasa, Perfilor,
Isoeste e Tetraferro (formados a frio) e as telhas (Isoeste, Kingspan Isoeste, Perfilor, Ananda, Regional,
Eternit, Sandre). Da NBR 6355 entram só as designações; as propriedades dos formados a frio são sempre
calculadas (U e Ue por `nbr14762`, Ze/Z45/cartola por `nucleo/secoes_frio.py`, que dá também Ixy, os eixos
principais I1/I2 e o ângulo α do Z), e a tabela do fabricante fica ao lado (`tabela_fabricante`) para
conferir. Conferido contra a transcrição da norma: A, Ix e Iy a menos de 0,3 % (U até 3 %); Cw 1 % a 10 %
abaixo. O gerador junta sem repetir (mesmo nome ou mesma geometria só acrescenta o fabricante em
`fabricantes`); o que só o fornecedor tem ganha `fornecedor: True` — aparece na tela, na busca e na troca,
mas `tesouras.candidatos` não o usa, e o dimensionamento automático segue nas séries padrão. `perfil_de()`
monta o `Perfil` dos laminados e tubos de fornecedor direto da tabela.

A busca entende a bitola no lugar da espessura (`127x50x17x#14` acha as de 1,90, 1,95 e 2,00 mm —
`espessuras_da_bitola()`, da tabela `bitolas` dos fornecedores: #14 é 1,90 a frio, 2,00 a quente e 1,95
zincada) e os apelidos BR/BC das barras. No 3D, o diálogo **Trocar perfil** sugere os perfis da mesma família
do catálogo, já no jeito da fábrica (`C127X50X17X2.00`), com massa e fabricante.

Correção da 0.7.11 em `nbr14762._trechos_u`: a linha média da mesa do U simples ia até `bf − t/2` em vez de
`bf`; a área e o Iy do U formado a frio ficavam um pouco baixos.

Rota `GET /api/catalogo/pecas` (sem parâmetros: famílias e resumo; `familia`, `q`, `alternativas`) e tela
`/catalogo`, ligada na barra da tela de projetos. Testes em `testes/test_catalogo.py`, inclusive um que
confere se `dados/catalogo.json` ainda é o que o gerador produz.

## Desempenho no Modelo 3D com IFC grande

**Escolha de peça pelo cursor**: o raycast do lote é próprio (`Lote._raycast`) — caixa do bloco, caixa de
cada peça e só então os triângulos das candidatas; o encontro leva `entidadeId`. Sem isso cada movimento do
mouse varria os ~16 mil triângulos de cada bloco (10 a 50 ms por movimento, a origem real da sensação de
travamento). Medido no IFC de 5 mil peças: 0,3 ms.

**Refino de malhas desligado no lote**: o refino pelo servidor (`Cena._refinar`) trocava a geometria de
80 chaves por rodada e, a cada rodada, **refazia o modelo inteiro na tela** — num IFC com centenas de chapas
eram várias travadas de 4 s em sequência (a "sensação de que está calculando o tempo todo"). Com o lote
ativo o refino não roda (a seção local basta) e a barra de estado diz "malhas: locais · lote"; fora do lote
ele vai numa rodada só e refaz apenas as peças cujas geometrias mudaram.

**Travadas medidas**: `cena.js` exporta `PESADOS` e `medir(nome, fn)` (operações acima de 60 ms) e observa
`longtask` acima de 250 ms; Ver → Diagnóstico de desempenho lista as cinco maiores. Verificador:
scratchpad `verif_travadas.py` (abre o modelo grande e reporta as travadas em 90 s).

**Modo leve**: acima de `LIMITE_LOTE` o modelo abre em "Sombreado" (sem as arestas de cada peça: eram 362 mil
linhas) e sem sombra; os botões de modo e Ver → Sombras devolvem o normal.

**Ver → Diagnóstico de desempenho** (`Editor3D.dialogoDesempenho`): mede na máquina do usuário os quadros por
segundo reais, as chamadas de desenho, o custo de escolher uma peça e qual placa de vídeo o navegador está
usando — e avisa quando caiu para SwiftShader (desenho por software). A janela do programa é aberta com
`--ignore-gpu-blocklist` e `--enable-gpu-rasterization` para não cair nesse modo por driver antigo.

**Desenho em lote** (`web/editor3d/nucleo/lote.js`): acima de `LIMITE_LOTE` (1.500) entidades, sólidos com
faces, chapas e barras entram em blocos de ~50 mil vértices (uma malha e um `LineSegments` de arestas
por bloco), ordenados no espaço; a cor de cada peça é um atributo de vértice e a visibilidade está no
índice (peça escondida sai do índice). O raycast dá a peça pelo índice da face (`userData.entidadeDe`).
A cena mantém um `Group` vazio por peça em `objetos` (com `userData.lote`), então o código de um objeto
por peça não acha malha e não mexe; cor, realce, modo, corte e sombras passam pelo `Lote`. IFC de 5 mil
peças: 7.122 → 82 chamadas de desenho por quadro. `?lote=0` força um objeto por peça (comparação).
Medição: scratchpad `verif_lote.py` (chamadas, quadro, clique, camada, mapa).


Acima de 1.500 objetos (`LIMITE_SOMBRAS` em `web/editor3d/nucleo/cena.js`) a cena abre sem a sombra
do sol: o mapa de sombra desenha o modelo inteiro uma segunda vez por quadro (IFC de 5 mil peças:
152 ms → 49 ms por quadro). Ver → Sombras liga de novo; o modo "Sombreado" (sem arestas) corta as
chamadas de desenho pela metade (28 ms). Com o mapa de esforços ligado, a peça sem valor fica em
cinza opaco sem arestas (material translúcido em milhares de peças obrigava a ordenar tudo a cada
quadro). Medição: scratchpad `medir_quadro.py` (renderer.info e tempo de `cena.desenhar`).

## Limites do sistema

Estes pontos são declarados no memorial e precisam de atenção do engenheiro:

- **Galpão de duas águas simétrico**, pórtico de alma cheia ou tesoura treliçada. Shed,
  arco, múltiplas naves e ponte rolante não estão implementados no dimensionador. O modelo
  **importado** de IFC é calculado à parte (tesouras como pórticos planos, terças como vigas;
  ver "Cálculo do modelo importado" e seus limites).
- Na tesoura, a **chapa de nó não é modelada em 3D** nem desenhada em detalhe: o cálculo
  verifica a chapa da diagonal mais solicitada e a prancha a indica por chamada.
- A **placa de base** é uma chapa lisa, sem enrijecedores. Base engastada de pórtico de
  vão grande pode pedir placa enrijecida, que o programa não dimensiona — nesse caso ele
  reprova a base com aviso, em vez de entregar uma chapa que não existe.
- **Análise plana e elástica**, com efeitos de segunda ordem por amplificação B₁/B₂.
  Não há análise não linear geométrica nem plastificação.
- **Fundação fora do escopo**: o sistema entrega as reações e a tração nos chumbadores;
  bloco, sapata e armadura de suspensão são do projeto de fundações.
- A **constante de torção** dos perfis é calculada pela soma de retângulos e fica cerca
  de 10 % abaixo do catálogo, porque despreza os raios de concordância. Isso reduz o
  momento resistente à flambagem lateral, ou seja, é conservador.
- As cargas críticas **local e distorcional** dos perfis formados a frio vêm de
  expressões analíticas aproximadas, não de análise de faixas finitas. Valores de
  catálogo do fabricante prevalecem.
- As **escoras** dos nós do contraventamento aparecem nos desenhos, mas não são
  verificadas nem entram na lista de material.
- Os **custos** usam percentuais indicativos sobre o preço por quilo informado.

Limites do editor 3D e do IFC:

- A **importação de IFC** não subtrai aberturas (`IfcOpeningElement`), então vãos de
  porta e janela de um modelo de arquitetura chegam fechados. Superfícies curvas exatas
  (NURBS, `IfcAdvancedBrep`) entram como caixa envolvente, com aviso. Não lê `.ifczip`
  nem `ifcXML`.
- A **união de sólidos** junta as malhas e remove as faces de contato; não é uma
  operação booleana completa, e sólidos que se interpenetram dão volume errado.

Nenhum resultado substitui o projeto conferido e assinado por engenheiro habilitado,
com ART registrada.

## Requisitos

Python 3 com `matplotlib` e `pymupdf` (desenhos e PDF) e `websocket-client` (impressão
do memorial e verificação do editor). O Google Chrome precisa estar instalado no caminho
padrão do Windows; se estiver em outro lugar, ajuste a variável `CHROME` em
`saida/printpdf.py`. O editor 3D precisa de um navegador com WebGL 2, o que vale para
qualquer Chrome, Edge ou Firefox atual.
