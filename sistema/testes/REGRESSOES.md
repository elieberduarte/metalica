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

## Tesoura de aço: posição das peças (boca do U, lado da cantoneira)

Regra única em `nucleo3d/regras_trelica.py` (T1–T5); todo gerador chama `orientar` antes do encaixe e a
conferência do 3D chama `conferir`. Teste principal: `test_regras_trelica.py` — gera pela tesoura do desenho
(Docas, linha de centro com alma em U, planta em x e em y), pela treliça do editor (alma U e L), pelo galpão
treliçado, pela planta do Posto e pelos quadros; a lista de fora da regra tem de vir vazia.

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 16/10 | Mercado Hermes: "toda tesoura nova volta com a configuração antiga" — montante de canto com a boca para fora, cantoneiras da alma uma de cada lado, diagonal em U virada (826 peças); Posto: cantoneira da PM6 copa do outro lado; CD Bom Dia: alma Ue em pé "para o fim" | ccf52cf | test_regras_trelica (todos os caminhos de geração); test_conferencia: Verificar apoios acusa |
| 16/10 | Mercado Hermes (anexo e tesouras do galpão): o topo do painel de ponta, vindo como "diagonal", com a boca para cima — "o banzo superior das tesouras nunca pode ser com a boca para cima" (T6) | 8656eb6 | test_regras_trelica::test_banzo_de_cima_nunca_de_boca_para_cima |

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
| 16/10 | ME-Sooro: "desliguei a regra e o programa mexeu na furação mesmo assim, sem avisar" (Q02 — decisão: o padrão da máquina vence; a caixa com nome honesto, o que mudou no 3D e Desfazer) | 6496ada | test_regressoes_primeiro_uso_ifc TestOQueODetalharMudouNo3D; verif_primeiro_uso_ui Q02/Q03 |
| 16/10 | ME-Sooro: a atualização automática refazia o Detalhar com os padrões e as pranchas saíam sem o "Rotular" escolhido (Q03) | 6496ada | test_regressoes_primeiro_uso_ifc TestOpcoesDoDetalharValemNaAtualizacao; verif_primeiro_uso_ui Q02/Q03 |
| 16/10 | ME-Sooro: "CH2 08x" na prancha da T1 03x (são 24) e "CH2 56x" na das chapas, sem dizer que era cópia (Q04, N02) | 6496ada | test_regressoes_primeiro_uso_ifc TestCopiaDaChapaNaPranchaDaTesoura |
| 16/10 | Depósito Químico: as pranchas não montavam (KeyError 'categoria' na cópia de "DP.1.1 + DP.1.2") | 6496ada | test_regressoes_primeiro_uso_ifc TestPranchasDoDepositoQuimico |
| 16/10 | ME-Sooro: a altura dos furos da terça sem cota, os chanfros da CH2 e o furo da cantoneira até a aba sem cota, a A.T.1 de 29,4 m sem "prever emenda" (Q05, Q06, Q07) | 6496ada | test_regressoes_primeiro_uso_ifc TestCotasQueAFabricaPrecisa |
| 16/10 | ME-Sooro: "BOLT (A) 12x30" na lista, sem classe nem porca; 28 porcas Ø3/4" do chumbador faltando na compra (Q08, N07 — decisão: recebido segue o projetista, nosso 2 porcas + 1 arruela) | 6496ada | test_regressoes_primeiro_uso_ifc TestParafusosEPorcasNaLista |
| 16/10 | ME-Sooro: a busca não achava "T.O.6" (o nome do aviso) com o editor aberto antes do Detalhar (Q12) | 6496ada | verif_primeiro_uso_ui Q12 |
| 16/10 | ME-Sooro: a planta de chumbação sem a locação dos chumbadores (o CB2 a 262 mm do eixo D sem cota) (Q09) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestLocacaoDosChumbadores |
| 16/10 | ME-Sooro: "Detalhar as peças de um IFC…" não fazia nada (o navegador bloqueava a janela do arquivo) (Q11) | 9ad28b8 | verif_primeiro_uso_ui Q11 |
| 16/10 | ME-Sooro: o 3D com 16 × 13 eixos antes do Detalhar e as pranchas com 7 × 5 (Q13) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestEixosDo3DSaoOsDasPranchas |
| 16/10 | ME-Sooro: "L 1 1/2'' X 1/8' '" com as aspas soltas; "PLATE 270x120x6 #1/4\"" com duas espessuras (Q14, Q15) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestGrafiaDaCantoneira, TestChapaComUmaEspessura |
| 16/10 | ME-Sooro: "(folga 1 < 1,5)" em toda terça e chapa da prancha do projeto recebido (Q16) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestFolgaNaPranchaDoProjetoRecebido |
| 16/10 | ME-Sooro: os avisos do Detalhar de antes ficavam na tela; "Gerando o PDF de 1 prancha(s)" para 13 folhas (Q18) | 9ad28b8 | verif_primeiro_uso_ui Q18 |
| 16/10 | ME-Sooro: não havia DXF de corte das chapas (Q19) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestDxfDeCorteDasChapas; verif_primeiro_uso_ui Q19 |
| 16/10 | ME-Sooro: o diálogo Montar pranchas não lembrava o Projetista nem a revisão (Q20) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestCarimboLembrado; verif_primeiro_uso_ui Q20 |
| 16/10 | ME-Sooro: o 3D abria sem dizer o que o IFC trouxe (Q21) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestResumoDaImportacao; verif_primeiro_uso_ui Q21 |
| 16/10 | Primeiro uso: a Ajuda sem o roteiro IFC → pranchas (Q22) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestAjudaComORoteiroDoIfc; test_ajuda_menus |
| 16/10 | ME-Sooro: com nada selecionado, os padrões de desenho pareciam propriedades de uma peça (Q24) | 9ad28b8 | verif_primeiro_uso_ui Q24 |
| 16/10 | Sala dos Compressores: a cópia de CH3 na prancha da "T2" (M2 + M7) com 2x em vez de 12x — a composição da montada pelas peças de um exemplar (Q04, bateria) | 9ad28b8 | test_regressoes_primeiro_uso_ifc TestCopiaNaTesouraDeMetadesDiferentes |
| 16/10 | ME-Sooro: a cantoneira furada com prefixo CH ("CH = Chapa" na legenda) — decisão: CT.n (Q14) | 95a572a | test_regressoes_primeiro_uso_ifc TestNomesDecididosPeloUsuario |
| 16/10 | ME-Sooro: a "T4" da prancha (montada M8 + M9) não era a "T4" do romaneio (meia M6) — decisão: meias MT.n, montadas T (N01/R01) | 95a572a | test_regressoes_primeiro_uso_ifc TestNomesDecididosPeloUsuario |
| 16/10 | ME-Sooro: o modelo com M12 e a compra pedindo Ø1/2" — decisão: métrico ou polegada por projeto (N04) | 95a572a | test_regressoes_primeiro_uso_ifc TestParafusoDaCompraPorProjeto; verif_primeiro_uso_ui Q02/Q03 |
| 16/10 | ME-Sooro (2ª rodada): o Conferir acusava 21 terças fora do passo da máquina que o Detalhar acerta (R12) | 95a572a | test_regressoes_primeiro_uso_ifc TestConferirAntesDoPrimeiroDetalhar |
| 16/10 | ME-Sooro (2ª rodada): "Gerando o PDF de 1 folha(s)" para 14 folhas, com o desenho das pranchas acima de 4 MB (R20) | 95a572a | verif_primeiro_uso_ui Q18 |
| 16/10 | Portaria Hermes: o pilar lançado mostrava "Nome P1" e "Posição P11" (qual é a marca?), no grupo "Peça (IFC)" de um modelo que não veio de IFC | 226d225 | verif_primeiro_uso_ui P22 (lançado nos eixos pela tela) |
| 16/10 | Portaria Hermes: 1.874 kg no "Estrutura lançada" × 1.886,1 kg na lista × 1,9 t no 3D; "Ue 250… · 0 barras"; "a barra veio sem o furo no IFC" num modelo lançado | 45bd45d | test_regressoes_primeiro_uso TestPesoDoLancamentoIgualALista; verif_primeiro_uso_ui P23 |
| 16/10 | Portaria Hermes: zoom da roda do CAD fixo em 1,15× (16 roladas até ler os textos) e o x/y do rodapé parado no zoom | 882b03f | verif_primeiro_uso_ui P15 |
| 16/10 | Portaria Hermes: ferramentas na faixa de cima e na coluna ao mesmo tempo (não reproduziu em 16/10; guarda) | 2b2e061 | verif_primeiro_uso_ui P18 |
| 16/10 | Portaria Hermes: Ctrl+K "projeto recebido" não achava o desenho, e o Trocar de desenho só existia em Detalhamento | 127d282 | verif_primeiro_uso_ui P17 (desenho da Portaria) |
| 16/10 | Portaria Hermes: o painel de camadas punha CORTE…AUXILIAR vazias no topo e misturava as camadas do DXF com as do Metálica | a58af94 | verif_primeiro_uso_ui P16 (DXF da Portaria) |
| 16/10 | Portaria Hermes: logo depois do primeiro Detalhar, "Atualizando os desenhos (o detalhamento do programa mudou)" e tudo refeito | 643aa00 | test_regressoes_primeiro_uso TestDetalharNaoSeDaPorVelhoNoMeio |
| 16/10 | Portaria Hermes (rodada 2): com o 2D à mostra, Modelo › Eixos da obra… trocava para o 3D e não abria nada | dd6d58a | verif_primeiro_uso_ui P07 (rodada 2) |
| 16/10 | Mercado (de novo, no modo ver): os grupos do Pintar e as camadas ocultas no modo ver voltavam ao atualizar o projeto (6283ad4 só guardava as do editor) | d363d4a | verif_ver3d_ui (recarregar o quadro) + verif_vista3d_guardada |
