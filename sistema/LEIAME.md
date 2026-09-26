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
a normalizada seguinte, com nota. A prancha é um
desenho em milímetro de papel (escala 1), editável como qualquer outro, e o DXF sai em
papel 1:1: a cota guarda o valor original como texto. Cada prancha traz, no rodapé à
esquerda do carimbo, a **tabela das posições** que contém (marca, quantidade, perfil,
comprimento, peso). Para escolher à mão o que vai numa prancha, selecione as células no
desenho de detalhamento antes de abrir o diálogo e marque "só as peças selecionadas".
**Desenho → Importar DXF neste desenho…** traz um DXF em texto (R12 a R2018: linhas,
polilinhas com arcos, círculos, textos e MTEXT, blocos aninhados, cotas como o CAD de
origem as desenhou; hachura e imagem ficam de fora) para a escala do desenho aberto,
com a unidade do arquivo (`$INSUNITS` ou escolhida) e ponto de inserção; entra como um
comando, então Ctrl+Z desfaz. DWG não é lido: salve como DXF no CAD de origem.
**Desenho → Exportar PDF** gera o PDF vetorial do desenho aberto (prancha no tamanho da
folha; desenho comum no tamanho dele na escala) e **PDF de todas as pranchas…** junta as
pranchas do projeto num arquivo em `pranchas/`, uma por página, pronto para plotar.

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

O editor 3D roda no navegador, então não entra no `pytest`. Ele tem três verificadores
que abrem o Chrome sem janela e trabalham no editor de verdade. Com o servidor no ar:

```bash
python testes/verificar_editor.py --porta 8765           # abre o galpão no editor
python testes/verificar_editor_arquivos.py --porta 8765  # salvar, abrir, exportar e importar IFC
python testes/verificar_zoom.py --porta 8765             # zoom da roda e grade do plano
```

Cada um grava um galpão no navegador como a interface faz, executa a sua sequência,
salva uma captura de tela em `projetos/` e lista os erros de JavaScript. Saem com
código 1 quando alguma conferência falha.

### Verificadores headless e CI

`testes/verificadores/verif_*.py` sobem o servidor numa pasta temporária e exercitam a interface pelo Chrome
sem janela (CDP); a maioria usa o modelo de exemplo do cliente, que não está no repositório — ver o LEIAME
da pasta. `.github/workflows/testes.yml` roda o `pytest` no GitHub a cada push (Windows, Python 3.12).

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
