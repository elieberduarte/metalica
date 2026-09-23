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
4. **Pórtico** analisado pelo método da rigidez, com mísulas e base rotulada ou engastada.
5. **Combinações** últimas e de serviço (NBR 8681), inclusive com a permanente favorável
   quando a sucção alivia, que é o caso que costuma governar em galpão leve.
6. **Viga e pilar** pela NBR 8800, num laço que refaz a análise a cada troca de perfil,
   porque a distribuição de momentos depende da rigidez relativa entre os dois.
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
da barra e afastam-se quando cairiam um sobre o outro; nas prateleiras (`_empilhar`) a
linha inteira desce quando uma célula é mais alta que a primeira, para o título não
invadir as cotas da linha de cima.

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

Limites: contraventamentos, agulhamentos e consoles não são verificados (sem cargas de oitão);
ligações e chapas de nó não entram; terças de beiral apoiadas nos consoles ficam sem apoio; sem
travamento lido no modelo o banzo inferior é verificado com o comprimento inteiro (informe
`trava_inferior`); as tabelas de vento são de galpão fechado de duas águas.

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

## Catálogo de peças

`nucleo/catalogo.py` é o ponto único para "que peças existem": perfis I laminados (W, HP), U laminados e
formados a frio, Ue, cantoneiras em polegada e em milímetro, tubos, barras redondas e chatas, chapas e
parafusos — 495 itens. Junta `dados/perfis.json` (tabelas de fabricante, extraídas pelo `extrai_perfis.py`)
com `dados/catalogo.json` (gerado por `dados/gerar_catalogo.py`: séries NBR 6355 e cantoneiras métricas
calculadas pelo método linear da NBR 14762, mais chapas, barras e parafusos das tabelas do anexo). Cada item
diz a `origem` — `tabela` ou `calculado` —, e quando o mesmo perfil está nos dois lugares vale o da tabela.

`itens()`, `item()` (tolerante à grafia: `ue150x60x20x2,65`), `buscar()` (nome ou dimensão), `perfil_de()`
(devolve o `Perfil` de cálculo, montando na hora os formados a frio e aceitando nome de fábrica fora do
catálogo) e `alternativas()` — o que pode entrar no lugar de uma peça, na mesma família (`TROCA_COMPATIVEL`:
U vira Ue e vice-versa; cantoneira não vira terça), com altura de seção entre metade e o dobro da atual
(`FAIXA_ALTURA`) e a diferença de massa por metro. O padrão é "vizinhos": metade mais leves, metade mais
pesados, os mais próximos.

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

- **Galpão de duas águas simétrico**, pórtico de alma cheia. Treliça, shed, arco,
  múltiplas naves e ponte rolante não estão implementados no dimensionador. O modelo
  **importado** de IFC é calculado à parte (tesouras como pórticos planos, terças como vigas;
  ver "Cálculo do modelo importado" e seus limites).
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
