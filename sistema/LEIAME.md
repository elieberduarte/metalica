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
do modelo já importado, desenhos editáveis no CAD (`nucleo2d/detalhar.py`, rota
`POST /api/projetos/<slug>/detalhar`), no formato das pranchas de fábrica:

- um desenho por grupo — chapas (1:10), barras e terças (1:25), tirantes, telhas e
  conjuntos (1:50) — com uma célula por **posição**: título "P12 – 112x" (as iguais são
  contadas, não repetidas), perfil ou chapa com espessura (`#3/8"`), material, furos,
  peso, contorno com furos e cotas em cadeia (só quando cabem), seção da barra ao lado e
  vista de topo quando há furo na mesa;
- a **elevação de cada conjunto** (marca de montagem: tesoura, viga de painel, pilar),
  deitada, com a cadeia de cotas dos nós embaixo e em cima, altura, rótulo de posição em
  cada barra, título "M2 – 08x" e a lista de perfis e posições. O número de instâncias é
  o máximo divisor comum das quantidades por posição dentro da marca (8 pórticos M2 =
  80 P10, 64 P11, 64 P12 → 8); a instância desenhada é um agrupamento espacial com a
  composição unitária;
- `detalhamento/romaneio.csv` e `relatorio.json`.

**Regra da furação das terças** (padrão da máquina da fábrica, opção ligada por padrão):
terça com menos de 200 mm de altura fura a 50 mm na vertical e 60 mm na horizontal; com
200 mm ou mais, 100 × 60. Terça é a barra U/C/Z de 50 a 400 mm que viaja solta (marca de
posição igual à de conjunto). A regra vale para o que compõe a ligação da terça: toda
posição com um grupo de furos de furação original igual à da terça, em qualquer
orientação (a chapinha do suporte), recebe a mesma substituição; o centro do grupo é
mantido e a célula diz "furação no padrão de fábrica". Padrão quadrado ou terças de
alturas diferentes com a mesma furação original saem com "conferir".

### Pranchas com carimbo

No CAD, **Desenho → Montar pranchas…** (rota `POST /api/projetos/<slug>/pranchas`,
`nucleo2d/pranchas.py`) monta folhas A0–A4 em paisagem com moldura, quadro e carimbo
(obra, cliente, título, responsável, escala, data, número "01/07", revisão). Cada posição
ou conjunto dos desenhos de detalhamento vira uma vista na escala do desenho de origem;
cortes e vistas entram inteiros. O que não cabe na escala desce para a normalizada
seguinte, com nota; o que não cabe na folha vai para a prancha seguinte. A prancha é um
desenho em milímetro de papel (escala 1), editável como qualquer outro, e o DXF sai em
papel 1:1: a cota guarda o valor original como texto. Cada prancha traz, no rodapé à
esquerda do carimbo, a **tabela das posições** que contém (marca, quantidade, perfil,
comprimento, peso). Para escolher à mão o que vai numa prancha, selecione as células no
desenho de detalhamento antes de abrir o diálogo e marque "só as peças selecionadas".
**Desenho → Exportar PDF** gera o PDF vetorial do desenho aberto (prancha no tamanho da
folha; desenho comum no tamanho dele na escala) e **PDF de todas as pranchas…** junta as
pranchas do projeto num arquivo em `pranchas/`, uma por página, pronto para plotar.

## O que sai

| Entrega | Formato | Onde |
|---|---|---|
| Detalhamento de peças de um IFC | DXF único, CSV e JSON | `projetos/<nome>/detalhamento/` |
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
│   └── detalhamento.py   peças de um IFC para produção (DXF único e romaneio)
├── web/                  interface de dimensionamento (HTML, CSS e JS puros)
│   ├── editor3d/         editor 3D: núcleo e ferramentas
│   └── lib/              Three.js r160, servido localmente
├── dados/perfis.json     catálogo de perfis
├── testes/               cerca de 500 testes
└── projetos/             projetos salvos e arquivos gerados
```

No catálogo, tubos redondos têm o prefixo `TC` e tubos retangulares e quadrados, `TR`
e `TQ`.

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

## Limites do sistema

Estes pontos são declarados no memorial e precisam de atenção do engenheiro:

- **Galpão de duas águas simétrico**, pórtico de alma cheia. Treliça, shed, arco,
  múltiplas naves e ponte rolante não estão implementados.
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
