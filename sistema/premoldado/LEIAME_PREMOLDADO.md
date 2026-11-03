# Pré-moldado — módulo em desenvolvimento (só no modo dev, fora do git)

Começado na noite de 27 para 28/09/2026, a pedido do usuário ("módulo novo de pré-moldado, seguindo os
mesmos conceitos"; primeiro o galpão pré-moldado; só no modo dev; não subir para o git ainda).

## Como usar
- Rodar o programa em desenvolvimento (`python app.py --dev`, porta 8766). A tela de projetos ganha o botão
  **Novo galpão pré-moldado (dev)**; projetos desse tipo abrem em `/premoldado?projeto=…`.
- Na tela: geometria, cargas e vento, concreto e produção → **Dimensionar**; **Ver no 3D** grava o modelo no
  projeto e abre o editor; **Memorial em PDF** grava em `<projeto>/memorial/`.
- Tela inicial com duas áreas (troca na marca do canto de cima): **Metálica** e **Pré-moldado**; cada uma com a
  sua lista de obras, os seus botões de "Novo" e os seus menus. No Pré-moldado: **Catálogo de peças**
  (`/premoldado/catalogo`) e **Ligações pré-moldadas** (`/premoldado/ligacoes`).
- Os "Novo" do Pré-moldado: a partir de IFC (modelo de concreto → editor 3D), a partir do arquitetônico (planta
  DXF/PDF → malha de eixos → "Usar os eixos da planta" na tela do galpão traz o vão e os vãos entre pórticos),
  desenhando em 2D (o CAD; gerar peças de concreto do desenho ainda não existe) e o galpão pré-moldado. O projeto
  nasce com `area: "premoldado"` no projeto.json (a extensão intercepta o POST /api/projetos e acrescenta o campo
  `area` ao resumo da lista — sem mexer no projetos.py).
- Sem o `--dev` nada disso carrega (o `app.py` só tem o gancho genérico `_extensoes_dev`).

## Fora do git
`.git/info/exclude`: `sistema/premoldado/`, `sistema/web/premoldado/`, `sistema/testes/test_premoldado*.py`.
Arquivos versionados com ganchos SEM commit: `sistema/app.py` (`_extensoes_dev`, `EXTENSOES_DEV`, e as duas
chamadas em `do_GET` e `_do_post`). Nos commits da Metálica, listar os arquivos um a um e não levar esse trecho
do app.py enquanto o pré-moldado não for liberado.

## O que tem
- `concreto.py` — NBR 6118 seção 8: Concreto (fcd, fctm, Eci, Ecs, ηc, λ, αc, εc2, εcu), aços CA-50/60,
  bitolas, cobrimentos (Tabela 7.2, Δc = 5 mm para pré-fabricado).
- `nbr6118.py` — seção retangular por compatibilidade de deformações (parábola-retângulo, vetorizado),
  flexão simples (ductilidade, armadura mínima), cisalhamento modelo I, flexo-compressão resistente,
  diagrama M-N-1/r (pico 1,10·fcd), pilar com 2ª ordem (momento mínimo, dispensa λ1, curvatura aproximada
  até λ 90, pilar-padrão acoplado a M-N-1/r até λ 140, fluência 15.8.4 acima de 90), flexão oblíqua
  (α = 1,2), armadura mínima/máxima, a busca da armadura mais leve, estribos de pilar.
- `nbr9062.py` — γc/γs (8.1), cálice de interfaces lisas/rugosas (Tabela 15, Hsfd/Nbd com interpolação,
  compressão 0,4·fcd, armaduras do colarinho pelo modelo da Figura 27 — braços adotados, a conferir),
  içamento do pilar (βa = 1,3, γf = 1,30, σs ≤ 0,5·fyk), consolo (a/d, tirante, biela — largura 0,2d adotada,
  muito curto τwu, costura, estribos, suspensão, γn, Hd/Fd da 7.3.9), elastômero simples (7.2.1.6),
  ancoragem (NBR 6118 9.4.2).
- `galpao.py` — DadosGalpaoPM → dimensionar → ProjetoGalpaoPM: vento pela parte metálica
  (`nucleo.cargas.pressoes_galpao`), pórtico de pilares engastados com a cobertura como escora rotulada
  (`nucleo.analise`), direção longitudinal (oitão dividido pelos topos; canto com q·H²/8), combinações
  (γ 1,3 do pré-moldado), a seção mais leve que passa (λ ≤ 140), cálice nas duas direções, içamento,
  cintamento do topo (6.2.3), deslocamento do topo H/400 (Tabela 7), lista de peças.
- `vigas.py` (29/09) — vigas biapoiadas de concreto armado, seção de retângulos empilhados (retangular, T, I,
  T invertido, U da calha), altura variável ao longo do vão: flexão em 41 seções (retângulo de tensões na
  seção composta, ξlim, mínima), momento negativo da sucção, cisalhamento no apoio (ramos por alma), ELS-W
  (wk, 17.3.3.2, Tabela 13.4, frequente), flecha (Branson seção a seção por trabalhos virtuais, αf com t0
  ponderado: peso próprio no saque, o resto na montagem; limites da NBR 9062 Tabelas 8/9), estabilidade
  lateral (6.1.6), içamento (5.3.2: momento nas alças a 10 % das pontas) e alças ASTM A36 (βa = 3), apoio
  sem recorte (7.5) ou dente Gerber (7.4 = consolo + suspensão + estribos horizontais), elastômero (o menor
  que passa; H da temperatura 11.4.2.1 e da retração da Tabela 8.1 depois da montagem; rotação por
  trabalhos virtuais). Viga leve que não chega à tensão mínima do elastômero (7.2.1.6.22 a) fica travada por
  chumbador (pino) — corte só no aço (0,6·fyd), **modelo adotado pelo programa** (a 9062 não traz a conta);
  com sucção do vento que levanta a viga, o pino leva também a tração.
- No galpão: `vigas_longitudinais` = nenhuma | calha | travamento (nos consolos dos pilares, vão de cálculo
  = o maior vão; a mais leve das seções candidatas), `viga_cobertura` (seção I com o banzo de cima na água,
  uma por pórtico, sucção do vento), `extremidade_vigas` = sem recorte | dente Gerber. As vigas pesam no
  topo do pilar (PP; água da calha em SC) e o consolo dá momento constante na direção longitudinal
  ((b/2 + a)·diferença das reações — o pilar de canto leva uma viga só). Consolos (7.3) por tipo de pilar.
  Lista com as vigas por comprimento de peça (entre faces de pilar, 1 cm de folga), elastômeros e pinos.
  O padrão (`nenhuma`, sem viga de cobertura) deixa os projetos antigos com o mesmo resultado.
- 3D: vigas (calha em U, travamento, cobertura I em 4 sólidos) e consolos; **corrigido 29/09**: o pilar saía
  com b no Y (a extrusão vertical põe o 1º eixo do contorno no Y global) — agora b no X (comprimento).
  O peso das peças de concreto vai em `peso_peca_kg` (o painel do editor soma `peso_kg` como aço). Ao gravar
  o 3D, os eixos do galpão (1…n, A/B, `origem: "premoldado"`) vão para o projeto se não houver eixos da
  planta — sem isso a identificação automática (feita para treliça metálica) inventava eixos nas vigas.
- `fundacao.py` (29/09) — a fundação sob o cálice (`fundacao` = nenhuma | sapata | estacas no galpão): a base do
  pilar no topo da fundação (≥ 20 cm abaixo, 9062 7.7.5.1) e o colarinho só com o embutimento. Tensões no solo
  planas sem tração pelo método das áreas ativas (malha 40 × 40, máximo no canto do plano; confere com
  N/A(1 + 6e/a) e 2N/(3b(a/2 − e))). Sapata: a menor rígida (h ≥ (a − ap)/3, 22.6.1) com σmáx ≤ σadm e a área
  comprimida ≥ fração mínima (padrão 2/3) nas combinações características (γ = 1, com o acréscimo de 2ª ordem da
  ELU); flexão na face do colarinho com a tração uniforme na largura (22.6.2.2 a), compressão diagonal no
  contorno do colarinho (19.5.3.1 + momento de 19.5.2.2), pressão de contato da base do pilar (21.2.1). Bloco:
  2, 4 ou 6 estacas e espaçamento de 1× a 2× o mínimo, o de menor volume que passa (2 em linha não serve com
  momento longitudinal); reações ≤ carga/tração admissível; bielas de Blévot com tg θ ≥ 1, nós CCC (fcd1) e
  CCT (fcd3) de 22.3.2, tirante T = R·(x − ap/4)/d por faixa, distribuição 20 %. O que é da **NBR 6122** (σadm,
  cargas da estaca, fração comprimida, espaçamento, borda) é dado da obra e fica marcado "a conferir" — a
  norma não está em `Normas/`. ELU com os momentos de 2ª ordem do pilar (7.7.1.1) recalculados por situação.
- Ponte rolante no galpão (29/09): `ponte_rolante` + `pr_*` (rodas máx./mín., impacto, transversal e frenagem por
  lado: **dados do fabricante** — a NBR 8800:2024 da pasta traz só γ = 1,5 e os ψ; Tabela 2: pilares que suportam
  vigas de rolamento 0,7/0,6/0,4). O pilar ganha o nó C na altura do consolo (barras `pilar_esq`/`pilar_esq_sup`);
  a reação pela linha de influência das vigas de rolamento biapoiadas (`fator_rodas`: a cabeceira na pior
  posição), a excentricidade do trilho (momento no nó) e a transversal no topo do trilho (força + momento); 4
  casos `PONTE_CASOS` (carro de cada lado × transversal nos dois sentidos); a frenagem na direção longitudinal
  repartida pelos pilares do lado. Combinações últimas e características com a ponte principal e secundária.
  Consolo da ponte (7.3) com Hd = 1,5·Ht + 0,25·Fd e a **fadiga** obrigatória (7.3.1.3 → NBR 6118, 23.5):
  Δσ no tirante ≤ 85 MPa (barra com solda, Tabela 23.2; ψ1 = 1,0 e γf = 1,0) — aumenta o tirante se preciso — e
  a biela ≤ 0,45·fcd. ELS: deslocamento no nível da viga de rolamento ≤ Hr/400 (Tabela 7, nota a). Torção do
  consolo pela frenagem (7.3.1.8 b) fica como apontamento. A viga de rolamento entra como peso (kN/m): o
  dimensionamento dela em concreto (com fadiga) ainda não existe.
- `locacao.py` (29/09, pedido do usuário: "crie a planta de locação dos pilares") — a planta de locação em 1:100 como
  Desenho do CAD (`desenhos/locacao-pilares.desenho.json`, botão **Locação dos pilares (2D)**, rota
  `/api/premoldado/locacao`): os eixos 1…n e A/B com as bolinhas nas duas pontas, cada pilar em corte (hachurado)
  centrado no cruzamento — as mesmas posições do 3D (`posicoes_dos_pilares`, com os pilares de oitão), b no
  comprimento e h no vão —, a marca (P-C, P-I, P-O) e o eixo de cada um, o cálice e a sapata/bloco tracejados, a
  cadeia entre eixos com a total, o vão A–B e, nos oitões, a cadeia A → pilares de oitão → B; o quadro dos pilares
  (marca, seção, quantidade, comprimento da peça, cálice, fundação, eixos) e, por tipo, o detalhe de locação em 1:25
  com as distâncias das faces do pilar, do cálice e da fundação aos eixos (o que a obra marca no gabarito).
- `detalhe2d.py` (29/09) — o detalhamento dos pilares como Desenho do CAD (`nucleo2d.desenho`, só leitura da API;
  gravado em `desenhos/pilares-pre-moldados.desenho.json`, botão **Detalhar pilares (2D)** → `/cad?projeto=…`):
  por tipo de pilar, a fôrma no plano do pórtico (consolo da ponte) e no comprimento (consolos das vigas), níveis
  e cotas, a armação (N1 longitudinais, N2 estribos com ganchos a 135° de 9.4.6.1, N3 cintamento do topo, N4/N5
  suplementares pela regra dos 20φt de 18.2.4), o corte A-A e o quadro de ferros com o resumo por bitola (massa
  NBR 7480, sem perdas). Escala 1:25 para tudo (o corte na mesma escala). A armação dos consolos e do cálice fica
  na memória — o desenho deles ainda não sai.
- `protensao.py` (29/09) — pré-tração com cordoalhas retas aderentes (CP190/210 RB; áreas nominais e fpyk = 0,9·fptk da
  NBR 7483, **fora da pasta — conferir**): σpi ≤ 0,74·fptk (9.6.1.2.1 a, edição 2023); perdas iniciais (relaxação até a
  liberação, Tabela 8.3; acomodação na pista, dado do fabricante), imediatas (encurtamento na seção homogeneizada
  com Ecs a fcj) e progressivas pelo processo simplificado 9.6.3.4.2 (φ e εcs da Tabela 8.1 com t0 = 5 dias, χ da
  relaxação); transferência gradual em ℓbpt (9.4.5.2, fbpd de 9.3.2.2 a fcj); ato da protensão (17.2.4.3.2: γp 1,1,
  0,7·fckj, 1,2·fctm,j e As para a tração com 250 MPa); serviço nível 2 (CAA I-II) ou 3 (III-IV) da Tabela 13.4 —
  ELS-F com α·fctk,inf, ELS-D, compressões 0,45/0,6·fck, a borda de cima com a sucção; ELU com pré-alongamento
  (γp 0,9) e o diagrama bilinear, momento mínimo, ductilidade; cisalhamento com Vc da flexo-compressão (M0 com
  0,9·P∞); contraflecha e flecha (Ecs·Ic, permanente × (1 + φ)) na Tabela 8 da 9062; estabilidade lateral; apoio e
  elastômero das vigas. `dimensionar`: a seção mais leve e o menor número de cordoalhas. No galpão:
  `viga_cobertura_protendida` e `tercas_protendidas` (T a cada `tercas_espacamento` m, sobre as vigas de cobertura;
  o peso delas vai para a viga e para o CP do pórtico).
- `cobertura.py` (29/09) — a cobertura de outra obra (campo "Cobertura de outra obra", `cobertura_projeto`) no 3D do
  galpão, alinhada pelos eixos: o numerado "1" dela no eixo 1 do galpão, as linhas de apoio das tesouras (nós
  apoiados do `calculo.json` dela) nas filas A e B, o z dela (±0,00 = boca do cálice); sem os parafusos. A
  conferência vai para os apontamentos da tela (vão entre apoios, níveis dos apoios contra o topo dos pilares,
  apoio longe de pilar). O "Ver no 3D" grava os **níveis** no projeto (boca do cálice, base dos pilares, fundo
  da fundação, consolos, apoios da cobertura, topo) — o editor já desenha `niveis` do projeto.
- Apoios pela cobertura (30/09): `cobertura.alinhamento` prefere os **chumbadores** da obra da cobertura (tipos do
  `detalhamento/nomes.json`, como a identificação de eixos da Metálica), com o topo do concreto na face de baixo
  da chapa de base sobre cada um; `cobertura.geometria` tira daí o vão (as duas linhas extremas de apoios), os
  vãos entre pórticos, a altura e os **pilares de oitão** (apoios entre as filas nos pórticos das pontas) — botão
  "Usar os apoios da cobertura". Tipo de pilar `oitão` no galpão (`pilares_oitao` = [(eixo, distância à fila A)]):
  em balanço com o topo livre, vento do oitão na faixa de parede e a cobertura na faixa até o meio do 1º vão;
  cálice, sapata/bloco, lista (P-O), 3D e detalhe 2D. A cobertura trazida entra como um **grupo**.
- **Grupos no editor 3D (Metálica, versionado — 30/09):** `modulos/bloco.js` (agruparSelecao/desagruparSelecao,
  grupoTopoDe, folhasDoGrupo; blocoDe pega o grupo mais de fora), `editor.js` (ações + Ctrl+G / Ctrl+Shift+G) e
  `editor.html` (Editar → Agrupar/Desagrupar). Usa a entidade `grupo` do modelo (filhos) e o campo `grupo` das
  peças; grupo dentro de grupo vale; apagar o grupo apaga os filhos (documento.js), por isso Desagrupar esvazia
  a lista antes. Esses três arquivos ficam SEM commit até serem levados numa versão da Metálica.
- Planta de locação dos pilares (30/09): `detalhe2d.planta_locacao` (1:100; eixos com balões e cotas, pilares nas posições
  com marca/seção, cálices e fundações em linha oculta, oitões cotados, quadro), gravada como `locacao-dos-pilares` pelo
  botão Detalhar pilares. Análise do ciclo arquitetônico → locação → 3D em `Projeto/ANALISES/Desenho-e-pranchas/Analise-ciclo-2D-3D-2026-09-30.pdf`
  (5 rodadas propostas; R1 = objetos estruturais tipados no CAD).
- **Rodada 1 do ciclo (30/09, manhã) — lançar a estrutura na planta (Metálica, versionado, SEM commit):**
  `web/cad/estrutura.js` (menu Estrutura: Pilar, Viga, Fundação, Consolo com painel de medidas flutuante, catálogo de
  seções do pré-moldado e perfis da Metálica, níveis do projeto nos campos, R gira o pilar; `_propsEstrutura` no
  painel de propriedades; Níveis…; Gerar 3D da planta…), `cad.html` (o menu) e `cad.js` (import, mixin, registro,
  ações, uma linha no painel). Os elementos são entidades comuns na camada ESTRUTURA com `atributos.elemento`
  (pilar/viga/fundacao/consolo, material, secao, nivel_base/nivel_topo em mm ou nome de nível, marca, centro).
  `nucleo3d/de_planta_estrutura.py` gera o Documento 3D (concreto extrudado nas camadas do pré-moldado, aço como
  Barra com perfil; `origem_2d` em cada peça). Rotas no dev (premoldado/web.py): POST /api/premoldado/niveis e
  POST /api/premoldado/planta/3d (grava o modelo, traz a cobertura de outra obra se o projeto tiver, confere os
  pilares contra os chumbadores) — ao publicar, essas duas rotas passam para o app.py.
- **Rodada 3 do ciclo (30/09, manhã) — o cálculo do que foi lançado:** `galpao.py` aceita **filas com alturas
  diferentes** (`altura_pilar_b`; os pilares da fila B viram tipos à parte, "canto B"/"intermediário B", marcas
  P-CB/P-IB, CL-CB…, cada um com a própria altura no λ, no ℓe, no vento longitudinal, no cálice e na fundação;
  `tipos_de_pilar(d)`, `d.altura_tipo(tipo)`) e **cobertura de uma água** (`cobertura = "uma água"`: a inclinação
  vem das alturas, o pórtico tem os nós do topo em HA e HB, o vento na cobertura usa os coeficientes de duas
  águas com a normal do plano único, a viga de cobertura em concreto fica reta de A a B). O topo do pilar de
  oitão (`d.altura_oitao(y)`): na de uma água, na linha de A a B; nas duas águas com cobertura metálica, no topo
  das filas (a coluna de oitão metálica sobe até a água); com a viga de cobertura em concreto, na água. O 3D,
  a planta de locação, o detalhe 2D, os níveis ("Topo dos pilares — fila A/B", "Apoio das vigas — fila A/B") e
  o memorial seguem os tipos. `cobertura.conferir` aceita o topo de cada pilar (4º campo) e aponta o desnível
  pilar a pilar; `cobertura.geometria` devolve `altura_pilar_b`/`cobertura` quando as filas apoiam em alturas
  diferentes. **`da_planta.py`** — `dados_da_planta(des, niveis, base)`: os dados do galpão tirados da planta de
  lançamento do CAD (filas pelas duas linhas de pilares, pórticos, alturas pelos níveis do topo — filas
  diferentes viram uma água —, oitão, as seções lançadas como candidatas (o que não passa vira erro, não troca
  sozinho), vigas ao longo das filas → calha/travamento, de A a B → viga de cobertura, consolos, fundação);
  o resto (cargas, vento, materiais, solo) vem dos dados gravados. Rota POST /api/premoldado/planta/dados e
  botão **"Ler a planta de lançamento"** na tela (grava os dados e dimensiona). Limite herdado da Metálica:
  `cargas.pressoes_galpao` exige comprimento ≥ vão (vira erro do cálculo). Conferido no navegador: Sooro com a
  fila B lançada a +6,60 (teste) → P-C/P-I 30×40, P-CB/P-IB 35×40, 3D com as duas alturas e a cobertura trazida
  apontando o desnível pilar a pilar.
- **Rodada 4 do ciclo (30/09) — plantas de saída:** `plantas_saida.py` — planta de fôrmas da cobertura (1:100:
  pilares cortados, vigas em vista com a marca da lista, consolos ocultos, topo de cada fila, viga de cobertura e
  terças), planta de cálices e fundações (1:100, com o quadro: cálice ext./int., embutimento, fundação, fundo),
  corte transversal num pórtico (1:50, os níveis de cada fila, a viga longitudinal em seção, a viga de cobertura
  ou a linha da cobertura metálica) e corte longitudinal por fila (1:100; a fila B só com alturas diferentes).
  `conflitos(p)`: fundações que se sobrepõem em planta viram apontamento (o oitão perto da fila cai na sapata
  do canto) — o lugar dos pilares é do projeto, o programa não muda. O detalhe dos pilares ganhou uma célula
  por tipo (`metadados.celulas`) para caber na A1. Rota POST /api/premoldado/pranchas + botão **Pranchas**:
  grava locação, fôrmas, fundações, cortes e pilares como desenhos e monta o jogo de pranchas pela
  `app.montar_pranchas_projeto` (o mesmo da Metálica). Sooro: 8 pranchas A1.
- **Rodada 5 do ciclo (30/09) — ida e volta 2D ↔ 3D:** na tela dividida a seleção passa pelos dois lados pelo id
  do elemento da planta (`origem_2d`) e, na peça do galpão, pela marca e o eixo ("P-C@1/A"): `cad.js`
  (`_alvoNo3D` manda `origem2d:`/`pm:`; `_localizarPelaMarca` acha e seleciona), `editor.js` (`_destacar`
  aceita as duas chaves), `modulos/divisao.js` (manda `origem2d` e `pm`) — Metálica, SEM commit.
  `da_planta` guarda `origem_planta` (eixo → id/marca do elemento), que o 3D do galpão, a locação e as plantas
  de saída levam. A volta: `nucleo3d.de_planta_estrutura.planta_do_modelo` — a peça movida no 3D move o
  elemento (e o rótulo), o pilar com outra seção troca contorno e seção, os níveis seguem o 3D, as peças das
  ferramentas do 3D (P, V, SP, CS) entram na planta como elementos novos (e ganham o `origem_2d`), o que sumiu
  do 3D vira apontamento (não apaga). Rota POST /api/premoldado/planta/do3d e menu Estrutura → **Atualizar a
  planta pelo 3D**. Conferido no navegador (3D → 2D, 2D → 3D, P3 movido 600 mm no 3D voltou para a planta);
  `verif_dividida_ui.py` da Metálica: 0 falhas.
- **Barra da disciplina no CAD (30/09, pedido do usuário com print):** a barra da esquerda fica com a edição geral
  do desenho; uma segunda barra vertical à direita (entre o desenho e os painéis, `#barra-disciplina`, montada em
  `estrutura.js` → `_montarBarraDisciplina`) tem o seletor MET | PRÉ (padrão pela área do projeto; o PRÉ só aparece
  no dev, quando /api/premoldado/catalogo responde) e os elementos: Metálica — pilar e viga de perfil, **chapa**
  (dois cantos, espessura, nível da face de cima, aço), **furo** (camada FURO; fura a chapa em que cai) e
  **parafuso** (camada PARAFUSO; diâmetro, comprimento, nível da cabeça); pré-moldado — pilar, viga, consolo,
  fundação e **tesoura de concreto** (viga de cobertura em I de apoio a apoio: duas águas com h no meio, ou uma água
  com altura constante e os níveis das pontas). Embaixo, Níveis, Gerar 3D e Atualizar pelo 3D. O painel de medidas
  encosta na barra da direita. `de_planta_estrutura` gera tesoura (sólidos: mesas e alma), Chapa (com os furos) e
  o cilindro do parafuso; a volta do 3D move tesoura, chapa e parafuso; o `da_planta` lê a tesoura de A a B como a
  viga de cobertura do galpão. Arquivos da Metálica (sem commit): cad.html, cad.js, cad.css, estrutura.js,
  nucleo3d/de_planta_estrutura.py.
- **Telas (30/09, pedido com prints):** o projeto do pré-moldado abre direto na planta (a área de trabalho em
  2D: a planta de lançamento, senão a locação `locacao-pilares`, senão o primeiro desenho; sem desenho, o 3D; sem
  nada, a configuração) — `dev_inicio.js` (`urlDaPlanta`); a **configuração do galpão** (a tela dos dados e do
  cálculo, /premoldado) fica num lugar próprio: o botão "Configuração" no cartão do projeto, o ícone da
  engrenagem na barra da direita do 2D e Estrutura → "Configuração do galpão pré-moldado…" (`pm-configuracao`,
  só aparece em obra pré-moldada no dev). "Abrir a planta" da configuração vai para a mesma planta. A locação
  sai num nome só (`locacao-pilares`; a `locacao-dos-pilares` antiga não é mais gravada). A área de trabalho no
  dev (`/dividida`, servida por premoldado/web.py) ganha `dividida_pm.js`: os itens da barra da direita no menu
  Estrutura da barra única e, no Ver, Armaduras e Níveis.
- **Armaduras no 3D (30/09):** `modelo3d._armadura_do_pilar` — as barras N1 e os estribos N2 de cada pilar
  calculado (como o corte A-A do detalhe), na camada "Armaduras" (desligada ao abrir, material "Armadura").
  Ver → "Armaduras dos pilares (pré-moldado)" (`editor_pm.js`): liga a camada e deixa o concreto translúcido;
  no modo leve (modelo grande, peças em lote só com cor) o concreto (pilares, cálices, fundações) sai de cena
  enquanto elas aparecem. Também os **cálices** (`_armadura_do_calice`: laços horizontais principais na faixa de
  0,2·Lemb, secundários na altura, verticais nos quatro cantos, no eixo das paredes; a maior das direções x e y;
  cobrimento de 3 cm adotado para o desenho) e as **fundações** (`_armadura_da_fundacao`: a malha da sapata nas
  duas direções no fundo; os tirantes do bloco em faixas sobre as estacas, acima da cabeça delas — a armadura de
  distribuição do bloco não é desenhada). `fundacao.py` guarda as barras em números (`dados["barras"]`,
  `dados["cobrimento"]`). Modelo gerado antes (sem armaduras, ou só com as dos pilares): a opção do Ver oferece
  gerar o 3D do galpão de novo (o anterior vai para o histórico) e liga as armaduras depois de recarregar.
- **Níveis no 3D (30/09; `web/editor3d/modulos/lancamento.js`, Metálica, sem commit):** a cabeça do nível com a
  placa do fundo do tema (lia mal no tema claro) e o contorno mais forte; os níveis na mesma cota viram uma
  cabeça só ("Topo dos pilares · Apoio da cobertura"), os próximos (< 700 mm) alternam os cantos; duplo clique
  na cabeça (e Ver → Níveis do projeto…) abre o diálogo dos níveis com o clicado em destaque. Gravar usa
  POST /api/premoldado/niveis com `aplicar`: com a planta de lançamento, os elementos que usam o nível pelo
  nome seguem (o nome trocado vai junto) e o 3D se refaz da planta; sem ela, o topo dos pilares ("Topo dos
  pilares", "— fila A", "— fila B") muda a altura do galpão, que é recalculado e o 3D refeito. Fora do dev a
  rota não existe (aviso) — ao publicar, vai para o app.py com as outras.
- **Raio-X com as armaduras (30/09):** `editor_pm.raioXComArmaduras` — entrar no Raio-X liga a camada Armaduras
  (sair desliga, se foi ele que ligou); as armaduras ficam fora dos lotes do modo leve (embrulho de
  `Lote.aceita`) e opacas no Raio-X (embrulho de `cena._materialDe`), por fora do núcleo do 3D.
- **Placa de fechamento, laje e escada (30/09, barra PRÉ, menu Modelo → Lançar os elementos e menu Estrutura do
  CAD):** placa de fechamento = linha ao longo da parede (alveolar ou maciça, em pé na largura do módulo ou
  deitada, espessura, níveis; em planta, a espessura e as juntas); laje = dois cantos (maciça, alveolar ou
  pré-laje: as placas de `modulo` no sentido X ou Y e a capa; em planta, o X de canto a canto); escada = do pé ao
  topo (largura, espelho máximo, espessura da laje, níveis; os degraus iguais n = ⌈H/espelho⌉, em planta a
  largura e um traço por degrau; aviso quando 2e + p sai de 600–660 mm). `de_planta_estrutura` gera os painéis,
  as placas + capa e um sólido por degrau (convexo, da laje inclinada ao piso); a volta do 3D move a placa e a
  escada (a caixa das peças) e a laje pelo centro e pelo topo. Não entram no cálculo do galpão (são elementos da
  planta: o cálculo delas fica para depois).
- `web/premoldado/editor_pm.js` (29/09) — no editor 3D de um projeto do pré-moldado (o dev serve /editor3d com
  este script; o editor da Metálica não muda), a barra ESTR troca Barra/Chapa/Parafuso/Furo por **Pilar**
  (com o cálice, R gira), **Viga** (retangular/T/I/U, a face de cima nos dois cliques), **Consolo** (clique na
  face) e **Sapata**, com painel de medidas que começa pelo dimensionamento do galpão; desfazer normal. O painel
  de propriedades da direita ainda mostra perfil/aço (do metálico).
- `catalogo.py` — o catálogo: concretos C20–C90 (por agregado), aços com γs 1,15/1,10, bitolas com ℓb por
  concreto, cobrimentos (com o Δc do pré-fabricado), seções de pilar com a altura máxima por λ 90/140. A tela
  tem também a calculadora das seções de vigas e terças (retangular, T, T invertido, I). As fôrmas padrão da
  fábrica ainda não estão cadastradas.
- `ligacoes.py` — cálice, consolo e elastômero calculados avulsos (as mesmas rotinas do galpão), com desenho
  esquemático e memória na tela. Por fazer: chumbadores e ligações de vigas (dente Gerber, pino, chapa).
- `memorial.py` — memorial em PDF (mesmo formato do metálico: `saida/memorial.py`).
- `modelo3d.py` — pilares e cálices como sólidos no Documento do editor (camadas próprias, material Concreto).
- `web.py` + `web/premoldado/` — as rotas e as telas (`comum.js`/`pm.css` compartilhados; `dev_inicio.js` = as áreas da tela inicial).
- Testes: `testes/test_premoldado.py`.
- Normas: `Metálica/Normas/CONCRETO`; transcrições da NBR 9062 (imagem) no scratchpad da sessão.

## Caso de teste
Sala dos Compressores (ME SOORO), pilares em concreto de 9 m em Cascavel-PR (V0 ≈ 48 m/s lido no mapa da
NBR 6123:2023, entre 45 e 50): pilares 45 × 50 (canto 8 ø16, intermediário 10 ø16), cálices 95 × 100 com
embutimento de 110 cm (governado pela ancoragem), deslocamento 0,42 cm (limite 2,25).

## Próximos passos
- Ciclo 2D → 3D: vigas do lançado com seções diferentes por trecho (hoje uma seção por função); a volta do 3D
  para as vigas girar; ao publicar, as rotas /api/premoldado/niveis, /planta/3d e /planta/do3d vão para o app.py.
- Uma água com vento próprio (a NBR 6123 tem a Tabela 5 para uma água; hoje usa os coeficientes de duas águas
  com a normal do plano único); galpão com comprimento menor que o vão.
- Viga de rolamento de concreto (com fadiga) e torção do consolo da ponte (7.3.1.8).
- Detalhamento 2D dos consolos, do cálice, das vigas e da fundação; corte em escala maior.
- Protensão: isolamento de cordoalhas nas pontas (encamisamento) para seções baixas; cabos em camadas com
  excentricidade variável; perdas pelo Anexo A (idade fictícia com cura térmica).
