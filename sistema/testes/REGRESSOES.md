# Regressões: defeitos já corrigidos e o teste que vigia cada um

Defeito corrigido que volta é o pior defeito: o usuário já confiou na correção. Por isso:

1. **Toda correção de defeito ganha um teste** que falha sem a correção e passa com ela —
   pytest (`test_*.py`) quando é conta do servidor, verificador (`verificadores/verif_*.py`,
   Chrome sem janela) quando é tela. Conferir que o teste pega o defeito: desfazer a correção,
   ver o teste falhar, refazer.
2. **O teste roda na forma de modelo em que o defeito apareceu** — não só no modelo de exemplo.
   Os defeitos da câmera voltaram (16/10) porque os verificadores rodavam só no modelo dos
   compressores, perto do z = 0; um modelo importado com o piso a +637 m ou com 354 m de
   comprimento caía nos casos que ninguém conferia. Situação nova de obra → uma situação a mais
   no teste (ex.: `SITUACOES` em `verif_camera_modelos.py`).
3. **Uma linha aqui** com a data, o que o usuário viu, o commit da correção e o teste.

Os testes rodam no `antes_de_publicar.py` e na conferência da noite (os verificadores entram
sozinhos por estarem em `verificadores/`; a escolha seletiva por arquivo está em `selecao.py`).

## Câmera do 3D (editor, modo ver, análise estrutural)

Teste principal: `verificadores/verif_camera_modelos.py` — 6 formas de modelo × editor e modo
ver (origem, piso a +637 m, fundações a −7,35 m, 354 m de comprimento, 134 m de altura, peça
pequena). Os passos A–H dele estão no cabeçalho do arquivo.

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 22/09 | botão direito/meio trocados com o SketchUp | 0e47fb7 | verif_camera_modelos (C, D) |
| 25/09 | a órbita girava em volta de um ponto metros atrás da peça; a peça sumia | ade2f56, 48d337c | verif_orbita_cursor, verif_camera_modelos C |
| 25/09 | com o cursor no canto, a roda levava o alvo 35 m para fora e a órbita girava no vazio | camera.js `zoomToCursor = false` | verificar_zoom, verif_camera_modelos B/E |
| 06/10 | modo ver: o giro era em volta do alvo, a peça escolhida saía de vista | 477583d | verif_camera_modelos C (modo ver) |
| 09/10 | BRAMAIS "bugava inteiro" ao dar zoom: um passo atravessava a viga e a câmera ficava dentro dela | 587e5a0 | verif_camera_modelos B |
| 09/10 | o modelo "sumia" num clique da roda: a placa de vídeo devolvia um ponto a quilômetros | 631d6f7 | verif_camera_modelos E (a conta; o lixo da placa não se reproduz no Chrome sem janela) |
| 09/10 | "se o mouse está no vazio ele vai pra muito longe" | cda3ed2 (ver), 05f0810 (análise) | verif_camera_modelos E |
| 09/10 | depois do zoom na peça o pan quase parava | e93355d | verif_camera_modelos D |
| 09/10 | análise: girar segurando a rodinha mergulhava a câmera no modelo | 90453a9 | — (análise estrutural ainda fora do verif_camera_modelos) |
| 09/10 | vista guardada absurda voltava a cada F5 | 631d6f7 | verif_vista3d_guardada |
| 13/10 | PRATI: o plano de corte de perto comia a cantoneira de 1" ao aproximar | camera.js `_sincronizarZoom` | verif_camera_modelos B ("o plano de perto não a cortou") |
| 13/10 | PRATI: no pan, "parece que cliquei em outro lugar" (o alvo metros atrás do ponto clicado) | camera.js `_pivoDoPan` | verif_camera_modelos D |
| 13/10 | PRATI: entre as terças da fachada o giro/pan/zoom se apoiavam no fundo | camera.js `_pecaPertoDoCursor` | verif_camera_modelos (vãos entre as terças em todas as situações) |
| 15/10 | Kaefer: "gira em torno do ponto errado" entre as barras da treliça (modo ver) | 1289f8b | verif_camera_modelos C/G (modo ver) |
| 16/10 | modo ver: o pan começado no vazio fazia o modelo pular para baixo do cursor (agarrava o alvo, no meio da tela) | visor3d.js `_panNoCursor` | verif_camera_modelos F |
| 16/10 | editor, modelo com o piso a +637 m: o pan no vazio disparava 14× o mouse (apoiado no plano z = 0, 637 m abaixo) | camera.js `_chaoDoModelo` | verif_camera_modelos F (piso-alto) |
| 16/10 | editor, torre de 134 m: a roda no vazio mirava o chão a 2 raios do prédio e o modelo escapava | camera.js `_focoDoCursor` (chão do modelo dentro da planta) | verif_camera_modelos E (alto) |

## Barra de andamento

Testes: `test_barra_progresso.py` e `verificadores/verif_barra_progresso.py`.

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 16/10 | só o texto da etapa ("Pré-moldado: desenhando lajes… (19 s)"), e em muitas telas nem isso — sem saber quanto faltava | web/progresso.js (barra padrão + vigilância das chamadas), `_progresso` com fração | verif_barra_progresso, TestFracaoDaBarra |
| 16/10 | "Aplicar furos" deixava a etapa velha pendurada: a próxima tela mostrava "conferindo os eixos das chapas…" | `_tarefa_padrao` / `_fim_tarefa_padrao` no do_POST | TestTarefaPadrao |

## Desenho completo (2D)

Testes: `test_regressoes_completo.py` e `verificadores/verif_detalhar_premoldado.py` (o completo no CAD).

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 16/10 | "a prancha do 2D gerada pelo detalhamento do pré-fabricado precisaria abrir o projeto completo" | `premoldado_formas.desenho_completo` + rota + `dividida.js` (o 2D abre o completo da disciplina) | TestCompletoDoPreMoldado, TestRotaMontaOCompletoComTudo, verif_detalhar_premoldado |
| 16/10 | no completo, as marcas, os nomes dos eixos e as cotas das plantas (1:125) e cortes (1:75) viravam tracinhos — também na localização da metálica (1:150) | `detalhar._anexar_faixa` (`_papel_na_escala`) | TestPapelNaEscalaDoCompleto |
| 16/10 | o completo abria pedindo "Ajustar a escala para 1:50" (aviso de DXF importado num desenho gerado) | cad.js (sem sugestão em desenho com `gerado_por`/`detalhamento`) | verif_detalhar_premoldado |
| 16/10 | fôrmas: números das cotas empilhados no furo da estaca do bloco e nos alvéolos da contenção (as facetas do círculo) | `premoldado_formas._sem_facetas` | TestFormasRevisadas (facetas, bloco) |
| 16/10 | fôrmas: a cota total da vista lateral em cima da ponta da elevação (aba ABVL1) | folga 22 → 34 mm entre as vistas | TestFormasRevisadas (lateral) |
| 16/10 | fôrmas: a capa (concretada na obra) saía como peça de 54 × 53 m | `MOLDADO_NO_LOCAL` | TestFormasRevisadas (capa) |

## Modelo importado do Tekla (pré-moldado) e editor 3D — Mercado Conceito e Kaefer

Testes: `test_regressoes_mercado.py` (o prédio em L longe da origem, sem malha de eixos nem marca de conjunto, neoprene
"STEEL/SHORE A-60", um pavimento só — a forma do IFC do Mercado) e `verificadores/verif_selecao_por_peca.py` (barras de
um bloco a 3 km da origem, 19 perfis para a legenda rolar). Conferidos falhando no código de antes (1289f8b; o painel do
bloco no 2e3414c).

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 15/10 | Kaefer: "com Alt pressionado não seleciona mais de uma peça, apenas uma de cada vez" | 2e3414c | verif_selecao_por_peca 1 |
| 15/10 | Kaefer: "quando clico com Alt na segunda barra ele seleciona o grupo inteiro" (o painel do bloco pintava as vizinhas) | 2499ca6 | verif_selecao_por_peca 2 |
| 16/10 | Mercado: "quando desabilito a visualização de uma camada a lista rola automaticamente para o início" | 7f22cc7 | verif_selecao_por_peca 3 |
| 16/10 | Mercado: grupos ocultos voltavam ao atualizar; o modo ver não os ocultava; a cor do perfil diferente entre ver e editar | 6283ad4 | verif_vista3d_guardada |
| 16/10 | Mercado: "apaguei todos os eixos lançados errados, não tem um botão para salvar" (a lista vazia era recusada) | 45cbe33 | test_regressoes_mercado TestGravarEixosApagados |
| 16/10 | Mercado: "importando com os eixos todos desconfigurados" (51°, 1 numerado e 51 letras) | 254aacd | test_regressoes_mercado TestEixosPelosPilares |
| 16/10 | Mercado: "O 3D está fora do padrão de fábrica: Neoprene" (o neoprene sólido como aço) | fef554e | test_regressoes_mercado TestNeopreneNaoEhAco (sólido) |
| 16/10 | Mercado: a faixa do Neoprene voltava (o neoprene convertido em chapa paramétrica seguia como aço) | 067405b | TestNeopreneNaoEhAco (chapa paramétrica) |
| 16/10 | Mercado: a faixa do Neoprene voltava a cada abertura do editor (a migração dos eixos das chapas o reorientava) | a70b3b0 | TestNeopreneNaoEhAco (migração) |
| 16/10 | Mercado: "o projeto importado não está mostrando os níveis" (o Tekla manda um pavimento só) | 03563c7 | test_regressoes_mercado TestNiveisAutomaticos |
| 16/10 | dev: tela inicial em branco por minutos (a lista de 0,06 s a 24 s com o detalhamento automático rodando) | 73a5df4 | test_regressoes_mercado TestTelaInicialComDetalhamentoRodando |
| 16/10 | Mercado: "as elevações geradas pelo detalhamento do pré-moldado não ficaram legais" (a fachada pela peça mais de fora — só o muro da calçada —, contorno convexo, marcas amontoadas) | este pacote | test_regressoes_mercado TestElevacoesECortesDoPremoldado |

## Primeiro uso (agentes engenheiro-primeiro-uso e detalhista-primeiro-uso-ifc)

Achados dos testes de primeiro uso (`Projeto/BRIEFINGS/Briefing-primeiro-uso*.md`), feitos pelas telas com `testes/navegar.py`.

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 16/10 | Portaria Hermes: "Montar o 3D pela planta" → "falha no cálculo: 'posicao'" (hachura do DXF) | 8b7a830 | test_de_planta test_hachura_e_cota_no_desenho_nao_param_a_montagem |
| 16/10 | Portaria Hermes: a montagem pela planta terminava com 0 barras, sem aviso, e gravava o modelo vazio | 8b7a830 | test_de_planta test_planta_sem_pecas_nomeadas_avisa_e_nao_devolve_modelo_vazio |
| 16/10 | Portaria Hermes: "gravei A, B, 1, 2 em Eixos da obra", mas Pilares nos eixos e os balões do 3D seguiam os antigos (a malha da planta sempre vencia) | 159b5ed | test_regressoes_primeiro_uso TestEixosGravadosDepoisDaPlanta; verif_eixos_ui (eixo novo sem F5) |
| 16/10 | Portaria Hermes: "Não foi possível lançar: Vão: valor 4.0 fora da faixa" depois de clicar Lançar, com o vão já lido como 4,00 m | 182b2dd | verif_primeiro_uso_ui P06; test_regressoes_primeiro_uso TestVaoForaDaFaixaComVirgula |
| 16/10 | Portaria Hermes: Esc não fechava o menu aberto do CAD | bbe451f | verif_primeiro_uso_ui P11/P12 |
| 16/10 | Portaria Hermes: dois "Não foi possível montar…" vermelhos e fixos por cima do desenho por várias telas | bbe451f | verif_primeiro_uso_ui P11/P12 |
| 16/10 | Portaria Hermes: com o DXF do projetista, a única opção era "planta do cliente (arquitetônico)" — 75 ações no caminho errado | 32a47f3 | verif_primeiro_uso_ui P02/P13 |
| 16/10 | Portaria Hermes: Desenho → Projeto recebido abria o seletor do Windows sem explicar | 32a47f3 | verif_primeiro_uso_ui P02/P13 e P11/P12 |
| 16/10 | Portaria Hermes: o cartão dizia "Lançado sobre o arquitetônico" num projeto recebido | 32a47f3 | test_regressoes_primeiro_uso TestProjetoRecebidoMudaOTipo |
| 16/10 | Primeiro uso: nenhum botão Novo… dizia "DXF"; os da pasta vazia sem dica e com outros nomes | 4b8747e | verif_primeiro_uso_ui P20 (no bloco P02/P13) |
| 16/10 | Primeiro uso: a Ajuda citava "Novo a partir do arquitetônico…" e "Desenho → Montar o 3D pela planta", que não existem | 4c5c2c0 | test_ajuda_menus (Ajuda) |
| 16/10 | Primeiro uso: a árvore vazia do 3D mandava a "Arquivo → Gerar do galpão" (outro nome na tela do projeto) | 4c5c2c0 | test_ajuda_menus (textos das telas); verif_primeiro_uso_ui P27 |
| 16/10 | Portaria Hermes: Modelo › 5. Conferir as treliças lidas (3D no modo ver) dizia "Abra um projeto…" com o projeto aberto, e o Detalhar peças não abria | f8a2c2d | verif_primeiro_uso_ui P07 |
| 16/10 | Portaria Hermes: o passo 2 do projeto recebido (Ler folhas) abria a janela do Windows pedindo de novo o DXF do passo 1, sem explicar | 59fcd59 | test_regressoes_primeiro_uso TestFolhasDoDxfGuardado; verif_primeiro_uso_ui P08 |
| 16/10 | Portaria Hermes: o resultado do Projeto recebido era um paredão (8 "escala não encontrada" repetidos) e o aviso que importava — a planta sem eixos — vinha no fim | 72d64c4 | verif_primeiro_uso_ui P19 (DXF da Portaria) |
| 16/10 | Portaria Hermes: a aba Montagem mostrava os quadros vazios sem dizer como enchê-los (o "Enviar para quadro" só existe na Original) | c56c608 | verif_primeiro_uso_ui P14 |
| 16/10 | Portaria Hermes: o Montar o 3D pela planta mostrava banzo 6,00 m e ASTM A36 como lidos do desenho; eram o padrão | 3a32bc7 | test_regressoes_primeiro_uso TestOrigemDosPadroesDaPlanta; verif_primeiro_uso_ui P26 |
| 16/10 | Portaria Hermes: Novo modelo › Em branco → painel com 0 objetos e "Aço 4,3 t" (o peso do modelo anterior) | 632b886 | verif_primeiro_uso_ui P21 (modelo da Portaria) |
| 16/10 | ME-Sooro (IFC do TecnoMETAL): o PDF das pranchas recusado — 17 terças "fora do passo da máquina" no 1º Detalhar (só o 2º as acertava) | 2e73392 | test_regressoes_primeiro_uso_ifc TestPrimeiroDetalharNoPassoDaMaquina |
| 16/10 | ME-Sooro: o erro do PDF dizia "T.O.6: furos a 60 mm…" e nada levava à peça (a busca não achava T.O.6) | 2e73392 | test_regressoes_primeiro_uso_ifc TestPdfRecusadoLevaAPeca; verif_primeiro_uso_ui Q01 |
| 16/10 | ME-Sooro: o Conferir antes de detalhar não acusava o que trava o PDF nem a cantoneira de 29,4 m, e dava 9 "sem espaço para a chave" sem dizer qual parafuso | 2e73392 | test_regressoes_primeiro_uso_ifc TestConferirAcusaOQueTravaOPdf |
| 16/10 | Portaria Hermes: o pilar lançado mostrava "Nome P1" e "Posição P11" (qual é a marca?), no grupo "Peça (IFC)" de um modelo que não veio de IFC | 226d225 | verif_primeiro_uso_ui P22 (lançado nos eixos pela tela) |
| 16/10 | Portaria Hermes: 1.874 kg no "Estrutura lançada" × 1.886,1 kg na lista × 1,9 t no 3D; "Ue 250… · 0 barras"; "a barra veio sem o furo no IFC" num modelo lançado | 45bd45d | test_regressoes_primeiro_uso TestPesoDoLancamentoIgualALista; verif_primeiro_uso_ui P23 |
| 16/10 | Portaria Hermes: zoom da roda do CAD fixo em 1,15× (16 roladas até ler os textos) e o x/y do rodapé parado no zoom | 882b03f | verif_primeiro_uso_ui P15 |
| 16/10 | Portaria Hermes: ferramentas na faixa de cima e na coluna ao mesmo tempo (não reproduziu em 16/10; guarda) | 2b2e061 | verif_primeiro_uso_ui P18 |
| 16/10 | Portaria Hermes: Ctrl+K "projeto recebido" não achava o desenho, e o Trocar de desenho só existia em Detalhamento | 127d282 | verif_primeiro_uso_ui P17 (desenho da Portaria) |
