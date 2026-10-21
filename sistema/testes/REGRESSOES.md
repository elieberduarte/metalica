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
| 16/10 | Regras recriadas e aprovadas pelo usuário ("as regras são bem inconsistentes"; Word com as respostas em Projeto/ANALISES/Montagem): numeração 1.2/1.4/2.2–2.5, diagonal NUNCA para cima (também a cantoneira, "um U cortado ao meio"), ponta e topo do painel de ponta com o perfil do banzo, par de cantoneiras como U partido, banzo intermediário para cima, montante do meio para a ponta alta, lado fixo da cantoneira, "virar" = o contrário da regra | d38a742 | test_regras_trelica (uma função por regra + os 5 geradores); test_implantacao/test_premoldado_trelica acompanham |
| 16/10 | Mercado Hermes: a ponta da tesoura da ala entrando no painel da fachada oeste — "quando existe uma platibanda o final da tesoura nunca pode invadir a platibanda, deve sempre parar na face interna" (regra 4.8: a peça que chega para na face interna da que passa; recua pelos nós, nunca prolonga) | 6dffa53 | test_regras_trelica::test_4_8_* |
| 16/10 | Mercado Hermes: "algumas diagonais não passaram a regra dos recortes, ainda estão com a ponta furando o banzo" — o script da obra nunca chamava o encaixe (1.390 almas de eixo a eixo) e o encaixe não corta o trecho curto (montante partido no nó; o degrau de 50 mm entre o topo do painel de ponta e o banzo inclinado). 3.1a: o encaixe entra em `aplicar` e a conferência acusa a ponta que fura (pelas quinas da seção); 3.1b: o trecho todo dentro do banzo não é peça (junta com o vizinho ou sai) | 6dffa53 | test_regras_trelica::test_3_1a_*, test_3_1b_* (o degrau do corte CC) |

## Acesso pelo celular

Teste principal: `verificadores/verif_celular_ui.py` (de ponta a ponta, com o app.py). O pareamento
pelo caminho da câmera — link vindo de fora do site — fica em `verif_celular_qr_outro_app.py`.

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 19/10 | leu o QR com a câmera do Android: o computador listou o aparelho como pareado, e o celular abriu "Este aparelho ainda não está ligado ao computador" — o cookie em SameSite=Strict não ia no redirecionamento depois de uma navegação vinda de outro app | b1211db | verif_celular_qr_outro_app, test_celular_servidor `_parear` |
| 19/10 | no Android, "Instalar" dizia que não era possível e o atalho saía com um "1" cinza no lugar do logo — o manifesto e os ícones davam 401, porque o navegador os busca sem o cookie do aparelho | 8ae8e40 | verif_celular_instalar |
| 19/10 | Android no tema escuro: a lista e as abas escuras, mas o Modelo 3D abria claro (fundo, botões flutuantes, contagem de peças) | 0faa2c6 | verif_celular_tema_escuro |
| 20/10 | ME SOORO no 3D do celular: dois dedos não giravam "com o eixo no meio dos dois pontos"; de perto, o giro de um dedo "se movimenta muito" (mesma velocidade perto e longe, em volta do alvo da câmera) e "os eixos se confundem" | visor3d.js `_toque…`, `_doisDedos`, `_giroDePerto` (7a3ee70) | verif_celular_gestos (as 6 formas do verif_camera_modelos, toques de verdade) |

## Cobertura retrátil (Kaefer)

| Data | O que o usuário via | Correção | Teste |
|---|---|---|---|
| 19/10 | "Cobertura retrátil: ver aberta / ver retraída" no menu Modelo de todos os projetos — a cobertura é de um projeto só | aef5650 | verif_cobertura_barra |
| 19/10 | celular: aberta/retraída não aparecia na Kaefer — o pacote era de antes e, sem o projeto mudar, não era refeito | 0dd4c87 | test_pacote_cobertura_movel `test_pacote_de_antes_e_refeito_quando_o_formato_muda`, verif_celular_cobertura |
| 19/10 | celular: a lona desligada voltava ao trocar retraída/aberta — e em todo projeto as camadas desligadas voltavam ao sair e voltar | f7b4201 | verif_celular_cobertura (camadas) |

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
| 17/10 | ME-Sooro (2ª rodada): a prancha das elevações com outra malha de eixos (1–16 × A–M) e as plantas com 1–7 × A–E (R02) | 9531a1c | test_regressoes_primeiro_uso_ifc TestSegundaRodadaDaCamila::test_r02 |
| 17/10 | ME-Sooro (2ª rodada): a agulha A.D.9.1 (barra curva, 2× FE 3/8" 1.131 mm) não aparecia em prancha nenhuma de corte (R04) | 9531a1c | TestSegundaRodadaDaCamila::test_r04 |
| 17/10 | ME-Sooro (2ª rodada): porcas do chumbador com três quantidades — "6x porca/chumbador" (eram 4 porcas + 2 arruelas), 1 porca + 2 arruelas por perna na tesoura e o do modelo na lista (R05) | 9531a1c | TestSegundaRodadaDaCamila::test_r05 |
| 17/10 | ME-Sooro (2ª rodada): "CH2 – 56x, parafusos: 1x M16 x 40" e a lista com 48 — 8 CH2 sem parafuso no modelo, sem aviso (R06) | 9531a1c | TestSegundaRodadaDaCamila::test_r06 |
| 17/10 | ME-Sooro (2ª rodada): os furos fora do par da terça (a 35 e a 75 da base na T.C.4) sem cota nem nota (R07) | 9531a1c | TestSegundaRodadaDaCamila::test_r07 |
| 17/10 | ME-Sooro (2ª rodada): a F.T.1 e a B.10 curvas saíam sem raio — "sem raio a calandra não trabalha" (R08) | 9531a1c | TestSegundaRodadaDaCamila::test_r08 |
| 17/10 | ME-Sooro (2ª rodada): o chumbador sem a rosca e sem quanto a ponta passa da chapa (R09) | 9531a1c | TestSegundaRodadaDaCamila::test_r09 |
| 17/10 | ME-Sooro (2ª rodada): a locação dos chumbadores com cotas de 21 e 29 mm (0,2 mm no papel), sem dizer de que eixo nem para que lado, e sem o nível (R11) | 9531a1c | TestSegundaRodadaDaCamila::test_r11 |
| 17/10 | HEAD: o pytest falhava em test_detalhar2d e test_pranchas2d (esperavam T1/CH depois da decisão MT/CT de 16/10, 95a572a) | c0ab2d6 | os próprios testes |
| 17/10 | HEAD: arrastar no vazio do modo ver dava ReferenceError (`ancora` usada sem definição desde 53ce645; a definição estava só no disco) | 0c14393 | verif_camera_modelos (F) |
| 16/10 | Portaria Hermes: o pilar lançado mostrava "Nome P1" e "Posição P11" (qual é a marca?), no grupo "Peça (IFC)" de um modelo que não veio de IFC | 226d225 | verif_primeiro_uso_ui P22 (lançado nos eixos pela tela) |
| 16/10 | Portaria Hermes: 1.874 kg no "Estrutura lançada" × 1.886,1 kg na lista × 1,9 t no 3D; "Ue 250… · 0 barras"; "a barra veio sem o furo no IFC" num modelo lançado | 45bd45d | test_regressoes_primeiro_uso TestPesoDoLancamentoIgualALista; verif_primeiro_uso_ui P23 |
| 16/10 | Portaria Hermes: zoom da roda do CAD fixo em 1,15× (16 roladas até ler os textos) e o x/y do rodapé parado no zoom | 882b03f | verif_primeiro_uso_ui P15 |
| 16/10 | Portaria Hermes: ferramentas na faixa de cima e na coluna ao mesmo tempo (não reproduziu em 16/10; guarda) | 2b2e061 | verif_primeiro_uso_ui P18 |
| 16/10 | Portaria Hermes: Ctrl+K "projeto recebido" não achava o desenho, e o Trocar de desenho só existia em Detalhamento | 127d282 | verif_primeiro_uso_ui P17 (desenho da Portaria) |
| 16/10 | Portaria Hermes: o painel de camadas punha CORTE…AUXILIAR vazias no topo e misturava as camadas do DXF com as do Metálica | a58af94 | verif_primeiro_uso_ui P16 (DXF da Portaria) |
| 16/10 | Portaria Hermes: logo depois do primeiro Detalhar, "Atualizando os desenhos (o detalhamento do programa mudou)" e tudo refeito | 643aa00 | test_regressoes_primeiro_uso TestDetalharNaoSeDaPorVelhoNoMeio |
| 16/10 | Portaria Hermes (rodada 2): com o 2D à mostra, Modelo › Eixos da obra… trocava para o 3D e não abria nada | dd6d58a | verif_primeiro_uso_ui P07 (rodada 2) |
| 16/10 | Mercado (de novo, no modo ver): os grupos do Pintar e as camadas ocultas no modo ver voltavam ao atualizar o projeto (6283ad4 só guardava as do editor) | d363d4a | verif_ver3d_ui (recarregar o quadro) + verif_vista3d_guardada |
| 16/10 | PRATI CD - Metálica: o Verificar apoios caía (atributos.origem gravado como texto pelo script da obra em 1.086 peças) | 4e1c532 | test_origem_em_texto |
| 17/10 | Posto CB: a telha parava em degraus de até 1,35 m da borda diagonal da TRANSIÇÃO 16 (terça emendada no apoio; última terça antes da parede diagonal) | a2d716a | test_borda_escalonada_pela_linha_emendada + test_telha_ate_a_face_da_parede_diagonal |
| 17/10 | Posto CB: degrau de 133 mm na telha na calha x 34,06 (a ponta da linha subia sozinha ao plano e o resto ficava embaixo) | a2d716a | test_linha_da_calha_emendada_sobe_inteira + test_linha_emendada_nao_sobe_para_dentro_de_outra_peca |
| 17/10 | Posto CB: a TRANSIÇÃO 1 e as tesouras de cima atravessando a telha sem o revestimento e o rufo do corte BB | a2d716a | test_trelica_acima_da_telha_no_meio_do_telhado_e_revestida |
| 17/10 | Posto CB: a remontagem lia a caixa d'água com 2.324 peças e punha a obra 14 m fora do lugar (desenho trocado de 1:20 para 1:50 no CAD, textos ÷ 2,5) | 8cf8d70 | test_de_planta::test_desenho_noutra_escala_le_igual |
| 17/10 | Posto CB: encontros de águas baixas sem calha (a linha x 10,06 inteira) e a calha do V e da parede 50 mm por cima da telha, sem afastamento nem cobrimento | 8cf8d70 | test_vale_com_a_terca_do_fundo_baixa_ao_lado_ganha_calha + test_calha_da_parede_por_baixo_da_ponta_da_telha + test_calha_no_vale_em_v + test_terca_baixa_no_meio_da_agua_nao_vira_calha |
| 19/10 | Mercado (faixa norte): a terça NC-3 saía torcida 30,6° e nenhuma regra conferia o giro da terça (4.9) | 22c229a | test_regras_trelica test_4_9_terca_torcida_volta_a_agua_sentada_no_apoio |
| 19/10 | Mercado (faixa norte e meia-tesoura): os dois trechos do banzo de cima se encontravam no degrau sem corte e a alma parava 50 mm abaixo do banzo (3.1c, 3.2) | 22c229a | test_regras_trelica test_3_1c_degrau_no_banzo_de_cima_o_montante_sobe, test_3_2_no_da_alma_vai_para_o_eixo_do_banzo |
| 19/10 | Mercado: a fachada que só encosta por cima da faixa norte era tomada pela 4.8 como a tesoura que chega e o fechamento da faixa era recuado 100 mm | 22c229a | test_regras_trelica test_4_8_trelica_so_empilhada_nao_e_a_que_chega |
| 19/10 | CD Bom Dia (modelo antigo): tocos soltos abaixo e acima dos oitões TF1, diagonais penduradas nos nós, a diagonal da TC1 passando do banzo de baixo e montantes repetidos — nenhuma conferência corrigia sem remontar (e remontar perde as edições do 3D) | 934dbd0 | test_reanalise (na origem, longe dela e com banzo em cantoneira dupla) + verif_reanalisar |
| 19/10 | Kaefer: no resumo da obra a foto "sem a lona" saía com a lona quando a camada Lona estava ligada no modelo (a cena das fotos era montada antes da regra que a esconde) | 6c60fb5 | verif_fotos_lona (camada ligada; aberta e ?cobertura=retraida) |
| 19/10 | Mercado (modo ver, tema claro): a barra de andamento flutuante saía escura, com o texto escuro do tema por cima (contraste 1,1) — a cor dela era uma variável que não existe em tela nenhuma | daec17f | verif_barra_progresso (tema claro e escuro, contraste ≥ 4,5) |
| 19/10 | CD Bom Dia: Reanalisar estrutura deu "Failed to fetch" — o servidor do modo dev reiniciou no meio da conta (outro chat salvou um .py) | c88ada3 | test_dev_espera + verif_reanalisar (a conexão caindo no meio) |
| 19/10 | Mercado (anexo): o clique selecionava todas as tesouras iguais (a peça de origem sem a instância, "T.7") | 801b740 | verif_bloco_instancia |
| 19/10 | Mercado (anexo): com a tesoura selecionada, as vigas pré-moldadas onde ela apoia saíam laranja como a seleção (o destaque das vizinhas no lote) | 51b004e | verif_bloco_vizinhas |
| 19/10 | Kaefer, resumo da obra: os chumbadores Ø20 da base saíam em "Contraventamentos", os X Ø8 em "Travamentos e agulhamentos" e as travessas da lona (2U 127, papel longarina) em "Terças" — o papel declarado no modelo era ignorado | 561d2d3 | test_nomes_papel_declarado (com e sem a placa de base) |
| 19/10 | Kaefer: o reforço Ue 180×70×20 em pé do pilar redondo caía na categoria Terças da lista | 561d2d3 | test_nomes_papel_declarado (peça em pé não é terça) |
| 19/10 | Kaefer: a foto da capa do resumo da obra cortava a estrutura (a imagem 3:2 num quadro de 78 mm com object-fit: cover) | b296542 | test_resumos test_a_capa_mostra_a_foto_inteira |
| 19/10 | Mercado: o lançamento das telhas não punha fechamento nas platibandas com os nomes da regra (P.n, VT.n) | 6c3e423 | test_telhas_cobertura test_fechamento_na_platibanda_com_os_nomes_da_regra |
| 19/10 | Kaefer, resumo da obra: os pilares W 310×32,7, W 460×52,0 e TC 180×6,3 de 7,67 m saíam numa linha só (agrupados só pelo comprimento) e pareciam do perfil errado | a0bb5f6 | test_dossie test_linhas_do_tipo_separadas_por_perfil |
| 19/10 | Mercado: faltava o fechamento em telha na platibanda sobre o telhado mais baixo (P.5 sobre o anexo, P.6 sobre a faixa norte — telhado dos dois lados em planta) e na faixa do terraço sem telhado (P.13/P.14) | a48a8d3 | test_telhas_cobertura test_fechamento_no_degrau_entre_dois_telhados, test_platibanda_sem_telhado_de_lado_nenhum |
| 19/10 | Mercado: os fechamentos laterais ficavam afastados da treliça (110 mm do eixo, 60 mm de folga na U 100×50) e no degrau ala × galpão a telha da ala parava na última terça, com a faixa aberta até o fechamento | b627225 | test_telhas_cobertura test_fechamento_encosta_na_face_da_trelica, test_telha_passa_por_cima_do_fechamento_na_linha_dela |
| 19/10 | Mercado: o lançamento das telhas não punha calha onde a água desce para a platibanda P.n no fim do telhado, nem rufos nos fechamentos | 0f37140 | test_telhas_cobertura test_calha_da_parede_na_borda_baixa_contra_a_platibanda, test_rufos_do_fechamento |
| 19/10 | Mercado: rufos picotados e em degraus (não acompanhavam a telha), aba dupla capa + encosto perto do topo, chapa alta no pé do fechamento sobre o anexo e a calha, calha fechada como tubo | 51d5532 | test_telhas_cobertura test_rufo_acompanha_a_telha_e_e_uma_peca_so, test_capa_desce_ate_a_telha_perto_do_topo, test_rufos_do_fechamento, test_calha_aberta_em_cima |
| 19/10 | Mercado, modo ver: a barra de "atualizando o 3D" aparecia no canto de cima, escondida atrás do botão Reanalisar estrutura | 7a8bfb5 | verif_ver3d_atualizando (a posição da barra) |
| 19/10 | PRATI CD, resumo da obra: as treliças de fechamento em pé (TV) saíam na tabela de tesouras com vão de 0,20 m e altura igual ao comprimento (10,21 m) | 3d5a098 | test_dossie test_trelica_em_pe_nao_e_tesoura |
| 19/10 | Mercado: o rufo não seguia a inclinação da telha (reto na doca, em degraus sobre o anexo, quebrado na P.2, beirada acima na cumeeira), rufos e calhas em pedaços, contra-rufo da caixa d'água embaixo da telha | b886cb9 | test_telhas_cobertura test_rufo_segue_a_telha_com_a_platibanda_passando_do_telhado, test_capa_e_encosto_inteiros_perto_do_topo, test_contra_rufo_sobe_acima_da_telha_e_calha_inteira |
| 19/10 | PRATI, memorial de rufos e calhas: a mesma chapa de 0,50 mm saía com kg/m² diferentes (3,914 a 4,263) — área e peso da lista arredondados peça a peça | bb93396 | test_resumos test_rufos_com_o_mesmo_coeficiente_na_mesma_chapa |
| 19/10 | Mercado (conferência do modelo): nas quinas as capas atravessavam a outra treliça; a capa da P.9 e as pontas das calhas entravam nas treliças atravessadas | 984fbd8 | test_telhas_cobertura test_capas_em_meia_esquadria_no_canto |
| 19/10 | Kaefer e PRATI, resumo da obra: muito espaço em branco nas folhas — as 4 fotos da lona sozinhas em meia folha, o bloco de tipo e a tabela de até 8 linhas pulando inteiros para a folha seguinte, o cabeçalho sozinho no pé da folha e a foto de 120 mm em cima das tabelas compridas | 43bda55 | test_resumos test_tabela_comprida_parte_sem_deixar_o_cabecalho_sozinho, test_tipo_comprido_comeca_ao_lado_da_foto, test_fotos_da_lona_numa_fileira_so |
| 19/10 | Kaefer, resumo da obra: sem tesouras nossas, o kg/m² de projeção usava a caixa de todas as peças com as placas de base no chão (18,45 × 38,65 = 713 m²) | 242868e | test_dossie test_projecao_entre_eixos_sem_tesouras |
| 20/10 | Mercado, editor 3D: as telhas (sólidos em seções, sem tampa nas pontas; o fechamento em pedaços de 0,8 m) não esticavam nem recuavam — o Empurrar/Puxar e o Estender não pegavam nelas | 013f9d0 | verif_estender_telha (fiada de 3 com Shift+clique, +300, corrige 500, Ctrl+Z, até a ponta do pilar, recuo de 2000 passando a terça) |
| 19/10 | Mercado, modo ver: no Pintar por sistema não havia o grupo da cobertura — as telhas caíam em Outros e as calhas/rufos em Metálica | 1e665ea | verif_grupo_camadas (Pintar por sistema) |
| 20/10 | Mercado, modo ver: o muro e os contornos das vagas do estacionamento ficavam no Pré-moldado, fora do grupo Terreno, rua e calçada; e não havia como mandar uma peça à mão para o terreno | 60d3138 | verif_ver3d_sistema (muro, vaga e peça na camada Terreno) |
| 20/10 | Celular, folha Camadas: o quadradinho de cor da camada não era a cor das peças no 3D (a cor da camada no arquivo, cinza; o 3D pinta pelo material) | 45fcec6 | verif_celular_ui (o quadradinho de cada camada × a cor na tela; trocar a cor, reabrir, voltar às cores do modelo) |
| 20/10 | Hangar Almayer (projeto de fabricação, 36 folhas): o "1. Importar o projeto" lia e já montava o 3D — sem malha de eixos, 30 desenhos de fabricação enfileirados no 3D e as vistas com cota 10× menores (cotas em cm lidas como mm); agora a importação só lê (o Original) e a Identificação para modelagem acha a locação, os eixos e as tesouras | 58c5eb4, 02ae8ae | verif_projeto_recebido_original, verif_identificacao_ui (DXF do Hangar em Projeto/OBRAS/Hangar-Almayer) |
| 20/10 | Celular, 3D: sair da obra e voltar — o visor antigo redesenhava a sombra da apresentação com as malhas já descartadas (TypeError em createBuffer) e a ficha às vezes não abria ao tocar a peça | dd33ee9 | verif_celular_ui (reabrir a obra e tocar a peça, sem erro no console) |
| 20/10 | Tela inicial: a pasta da empresa (Documentos\Metálica\fabrica — empresa.json, logo, tabela de preços Hermes, numeração das propostas) aparecia como o projeto de galpão "Fabrica"; Excluir mandaria os dados da empresa para a lixeira e Renomear tiraria a pasta do comercial | 185785d | test_projetos::test_pasta_da_fabrica_nao_vira_projeto |
| 20/10 | Cópia limpa do git (conferência da noite): todo POST dava 500 ("EXTENSOES_DEV is not defined") — criar projeto, gravar desenho, a Montagem | 339ad43 (+ f15c8f4) | test_app_copia_limpa |
| 20/10 | Galpão gerado (configurador): com 42 m e pórticos a 5 m, o último vão saía com 7 m, verificado como 5 m | f4918e3 | test_galpao::test_comprimento_que_nao_divide_vira_vaos_iguais |
| 20/10 | Galpão gerado: o deslocamento lia só o joelho esquerdo de um C_pi (o direito passava do limite) e acima do limite era só aviso (pé-direito 12 m, 7,2 cm × 4,0 cm, aprovado); combinação pela NBR 8800:2024 B.2.4 | f4918e3 | test_galpao::test_deslocamento_nos_dois_pilares_e_em_todos_os_cpi, ::test_deslocamento_reprova_e_alvenaria_usa_a_rara |
| 20/10 | Galpão gerado: a flecha da terça da tela não chegava à conta (sempre L/180); a telha cerâmica era calculada como metálica (0,05 kN/m²); comprimento < vão, inclinação 100 % e critério 0 quebravam no meio da conta | f4918e3 | test_galpao::test_flecha_da_terca_da_tela_chega_a_verificacao, ::test_telha_da_lista_da_tela_entra_com_o_peso_dela, ::test_validar_recusa_antes_de_calcular |
| 20/10 | Galpão gerado (Fabrica 20×40): a análise 3D acusava mecanismo (corrente com papel "barra") ou calculava sem carga nenhuma (sem banzo de cima marcado) — 22 % de uso, verde falso | f4918e3 | test_tesouras::test_analise_3d_carrega_o_galpao_gerado |
| 20/10 | Identificação para modelagem (Hangar): a volta do 3D lia o eixo da viga de aço como a face em que ela apoia (alinhamento base/topo) — a terça subia 63,5 mm a cada ida e volta; e a Montagem não tinha volta do 3D | 52cf304 | test_identificacao test_terca_apoiada_pela_base_nao_sobe_na_volta, test_montagem_volta_ao_papel; verif_identificacao_ui |
| 20/10 | Galpão gerado: a longarina era calculada com correntes que não existiam no 3D nem na lista (195 % na análise 3D) | 6ab0e16 | test_galpao::test_correntes_das_longarinas_no_3d_e_na_lista |
| 20/10 | Galpão gerado (Fabrica 20×40, V0 45): a terça na linha do X da cobertura é escora do contraventamento e nunca era verificada à compressão (160 % na análise 3D) | 6ab0e16 | test_tesouras::test_terca_escora_do_contraventamento_e_x_nas_linhas_de_terca |
| 20/10 | Galpão gerado, tesoura apoiada: o vento da faixa de parede acima do pilar não entrava no pórtico (momento na base ~20 % menor que no 3D); a terça e a telha ficavam ~75 mm acima do banzo | 6ab0e16 | test_tesouras::test_vento_na_faixa_de_parede_acima_do_pilar, ::test_terca_assentada_no_banzo_de_cima |
| 20/10 | Galpão gerado de alma cheia: a análise 3D não aplicava carga nenhuma, e conferia o W sozinho no trecho da mísula (164 % no joelho) | 6ab0e16 | test_galpao::test_analise_3d_carrega_o_portico_de_alma_cheia |
| 20/10 | Celular, maquete na mesa (S25, Mercado Hermes): as tesouras viravam placas maciças — a simplificação fazia caixa só girada na planta e a diagonal inclinada saía da altura dela | e2b0f9f | verif_celular_maquete (diagonal a 45° simplificada = barra de 205 × 105 mm na direção dela) |
| 20/10 | Galpão gerado (Fabrica 20×40, tesoura apoiada): o X das paredes acabava no topo do pilar, abaixo do X da cobertura — deslocabilidade grande na análise 3D (Δ2/Δ1 = 1,44) | 70fec1e | test_tesouras::test_x_vertical_sobe_ate_o_beiral_na_tesoura_apoiada |
| 20/10 | Celular, maquete na mesa: o valor da cota flutuava de frente para a câmera, longe da linha, e o comprimento era o lado do eixo x (na Kaefer, 18,45 m em vez de 38,65 m) | 535b6de | verif_celular_maquete (as cotas: direção e lugar de cada valor; o lado maior é o comprimento) |
| 20/10 | Galpão gerado: o oitão não tinha estrutura (a análise 3D jogava o vento dele no pilar de canto); agora pilaretes e longarinas de oitão, com o topo solto (padrão) ou apoiado (viga de oitão) | 3f7c424 | test_tesouras::test_oitao_solto_e_o_padrao_do_alma_cheia, ::test_oitao_apoiado_vira_viga_de_oitao, ::test_topo_do_pilar_de_oitao_a_escolha |
| 20/10 | Galpão gerado de alma cheia: a viga sob sucção era verificada com mãos-francesas que não existiam no 3D nem na lista | 3f7c424 | test_tesouras::test_maos_francesas_da_viga_de_alma_cheia |
| 20/10 | Hangar Almayer montado pela Identificação: o 3D desenhava no chão o Original do projeto recebido (36 folhas, 226 m) num sistema que não é o da obra, espalhado longe do hangar | e952cd0 | test_identificacao test_original_do_projeto_recebido_nao_vai_ao_chao_do_3d |
| 20/10 | Kaefer, modo ver no PC: Aberta/Retraída da cobertura retrátil demorava e pedia dois cliques (gravava o modelo inteiro e refazia o 3D leve; a página voltava ainda na situação anterior) — agora só para ver, como no celular | 10fb564 | test_modelo_leve::test_cobertura_retratil_a_outra_situacao_so_para_ver, ::test_cobertura_retratil_pedida_antes_de_pronta_e_obra_comum; verif_cobertura_barra (um clique, < 8 s, modelo intocado) |

## A obra no terreno (modo ver, imagem de satélite)

| Data | O que se viu | Commit | Teste |
|---|---|---|---|
| 20/10 | Obra em Cascavel (centro): a imagem da Esri vinha cinza, "Map data not yet available" — a fonte não tem o nível 19 ali; agora o bloco vazio é reconhecido e o nível desce até ter imagem (o 18) | a508301 | test_local_obra::test_fonte_sem_o_nivel_desce_ate_ter_imagem |
| 20/10 | O link do geoportal de Cascavel colado como fonte da imagem: "a fonte WMS precisa do endereço (http…) e do nome da camada"; agora o link escolhe a ortofoto 2021 da prefeitura, o GetMap traz a camada e o GetCapabilities acha a ortofoto | db6f89d | test_local_obra::test_fonte_pelo_que_se_cola, ::test_camada_achada_no_getcapabilities, ::test_imagem_pelo_wms_em_blocos |
| 20/10 | Mercado Conceito no tema claro: a imagem do terreno com transparência ficou toda lavada (misturada com o fundo claro); agora só fica transparente onde há obra por baixo do chão | 4b0b3b9 | verif_ver3d_terreno ("fora da obra a foto não lava com a transparência") |
| 21/10 | IFC georreferenciado da PRATI CD: a escala do mapa saía 0,9956 (devia ~1,0005) — a Terra esfera errava 0,5 % no norte–sul; e no modelo importado (sítio a milhares de km) a conversão caía no fuso errado | 3b93331 | test_local_obra::test_conversao_do_mapa_do_ifc, ::test_ida_e_volta |
| 21/10 | IFC da PRATI CD no Trimble Connect sem o terreno: exportado pelo editor, que não pedia o terreno; e o Trimble não mostra textura de IFC — agora o editor manda o terreno e a placa é um mosaico de cores da imagem | f1632e9 | verif_ver3d_terreno ("o IFC do editor sai com o terreno"), test_local_obra::test_mosaico_de_cores_do_terreno |
| 21/10 | IFC da PRATI CD com o terreno vermelho no Trimble Connect (não abria): o Trimble recusa a textura de IFC — agora a textura sai desligada e o terreno vai só no mosaico de cores (fino na obra) | 4928683 | test_local_obra::test_ifc_com_o_terreno_e_valido (o padrão sem textura), ::test_mosaico_fino_na_obra_e_grosso_em_volta |
| 21/10 | Imagem da ortofoto de Toledo (PRATI CD) com um quadrado cinza: um bloco que o servidor da prefeitura não entregou na hora — agora pedido de novo até três vezes | 8fc0ea4 | test_local_obra::test_bloco_que_falha_e_pedido_de_novo |
| 20/10 | Galpão gerado: longarinas que no 3D viram escora (a lateral do vão da ponta, 113 %) ou tirante (a de oitão, 227 %), e sem o peso do fechamento no eixo fraco | 4f1bf57 | test_tesouras::test_longarina_da_ponta_leva_a_reacao_do_pilar_de_canto, ::test_longarinas_com_o_peso_do_fechamento, ::test_longarina_de_oitao_com_folga_e_correntes_aos_montantes |
| 20/10 | Galpão gerado alto (pé-direito 10–12 m): o tirante do X vertical não cabia e o galpão saía reprovado; e sem escora de beiral a direção longitudinal ficava flexível na análise 3D (Δ2/Δ1 1,42) | 3346de4 | test_tesouras::test_x_vertical_em_paineis_no_galpao_alto, ::test_escora_de_beiral |
| 20/10 | Galpão gerado de tesoura com a ponta em viga de oitão (topo apoiado): a última tesoura ficava com o banzo de baixo travado só para um lado (Δ2/Δ1 2,13 na análise 3D) | f0869dc | test_tesouras::test_oitao_apoiado_vira_viga_de_oitao |
| 20/10 | IFC: cantoneira e U voltavam fora do lugar na importação (L 2": 14,7 mm; U 6": 9,7 mm) e a mão-francesa voltava "barra"; no lançamento os pilaretes de oitão ganhavam chapa de apoio de tesoura (conferência da 0.9.0) | cffb032 | test_ifc_importar::TestPerfilAssimetricoVoltaNoLugar, test_acessorios::test_ligacoes_geradas_no_lancamento |
| 20/10 | Faixa de ferramentas: o Estender telha (Shift+T) caía nas sobras do ▾ Modificar em vez de ficar com a estrutura do 3D (conferência da 0.9.0) | b1a5d46 | test_faixa_ferramentas::test_a_tabela_cobre_as_ferramentas_da_coluna |
| 21/10 | Conferência da noite: a 3ª rodada da 0.9.0 parou em "a cópia limpa já existe" — o verificador que esgotou o tempo deixou vivos os servidores que subiu, presos à pasta | f116d71 | test_rodar_verificadores::test_tempo_esgotado_leva_a_arvore_junto |
| 21/10 | Empurrar/Puxar com duas barras selecionadas (os dois U do banzo) puxava só a clicada; agora as selecionadas esticam juntas, cada uma na própria ponta do mesmo lado, num desfazer só | ef0fb19 | verif_pushpull_juntas, test_ferramentas3d.js ("barras selecionadas esticam juntas") |
| 21/10 | Hangar Almayer: a reanálise passava "nada a corrigir" com os banzos em U virados — a peça com `secao_dupla` (o U simples de alma no plano da T1/T3 e o 2U composto) era pulada pela regra; agora a 2.9 (alma do U no plano, 2L abraçando a alma, boca para fora do prédio) é conferida e corrigida, e o gerador faz o par de L pelo "2L" do projeto | c5d4073 | test_regras_trelica::test_2_9_u_simples_abre_para_fora_do_predio, ::test_2_9_composto_cada_u_abre_para_o_seu_lado, ::test_2_9_par_de_cantoneiras_abraca_a_alma_do_u, ::test_2_9_tesoura_pelo_desenho_u_centrado_e_par_abracando, test_identificacao::test_hangar_t1_banzo_de_alma_no_plano_com_a_alma_em_2l |
| 21/10 | Hangar: a ponta do banzo composto (2U) saía em par, um U de cada lado, e a 2.9 acusaria (e a reanálise giraria) a ponta certa montada à mão — um U só no plano entre as almas, boca no plano; agora a 2.9a acusa o par, a ponta certa passa e o gerador a faz assim (apoio, meia-esquadria, vão = altura do banzo) | 5ae2177 | test_regras_trelica::test_2_9a_ponta_do_composto_e_um_u_so_entre_as_almas, ::test_2_9a_ponta_em_par_e_acusada |
- 21/10/2026 — Posto CB V2: a planta da caixa d'água não entrava no 3D (o título do desenho é "CX DÁGUA", o parâmetro veio "CX D'ÁGUA"; só um aviso "planta não achada" e 16 treliças a menos). Correção: `de_planta._chave_de_titulo` ignora apóstrofo, acento e espaço no casamento do título. Teste: `test_de_planta.py::test_titulo_da_planta_com_apostrofo`.
| 21/10 | Hangar remontado pelas regras 2.9/2.9a: a T3 do oitão saía com a boca para dentro do prédio, os U (b) da T2/T2-A com a boca para baixo (o par de L dentro das bocas partia a treliça em duas e o U do outro lado virava "ponta") e 28 cantoneiras que só encostavam nos U ficavam fora da regra, com a aba para o lado da alma | 1188b4c | test_regras_trelica::test_2_9_sem_predio_de_um_lado_qualquer_lado_fora_do_plano, ::test_2_9a_par_dentro_das_bocas_nao_vira_o_banzo, ::test_2_9_par_que_so_encosta_no_u_entra_na_regra, ::test_2_9_gerador_poe_a_boca_da_tesoura_de_oitao_para_fora_do_predio |
| 21/10 | Hangar: o U simples com alma 2L (T1/T3) saía com a boca para fora do vão (leitura errada do corte T1 como "alma no plano"), a ponta do composto 51 mm para dentro do final da tesoura, e — ao remontar — a T1 partida em pedaços (nós da alma na face da faixa de 127) e a 2.5 casando diagonais vizinhas como par | 8421ab5 | test_regras_trelica::test_u_simples_com_alma_2l_e_2_2_e_2_5, ::test_alma_no_plano_de_modelo_antigo_e_acusado_pela_2_2, ::test_2_9a_ponta_alinhada_com_o_final_da_tesoura, test_identificacao::test_hangar_t1_banzo_simples_com_a_alma_em_2l |

## Tela inicial: obras enviadas entre usuários

| Data | O que se viu | Commit | Teste |
|---|---|---|---|
| 21/10 | A tela inicial desconfigurada: os cartões dos projetos do tipo recebido (Hangar Almayer…) sem o ícone e com o corpo espremido — o aviso das obras recebidas usava a classe "recebido" e o remove() levava o ícone junto | c5fd601 | verif_compartilhar_ui ("o cartão do projeto tipo recebido continua com o ícone") |
| 21/10 | Posto V2 (print do usuário, "peças voando"): na ponta da TESOURA 12 (e 13, 3B, 5) a diagonal do painel vizinho que a elevação desenha junto, acima do banzo, entrava como alma da tesoura e ficava solta no ar | ad76db2 | test_de_planta::test_alma_desenhada_fora_dos_banzos_sai |
| 21/10 | Posto V2 (print): a meia diagonal que trava a diagonal longa no meio do painel (TESOURAS 21, 22, 24–28, 32, 6) ficava solta a ~9 cm dela — o nó unido ao do montante e o recuo da ponta moviam a diagonal longa e a meia diagonal não acompanhava | ad76db2 | test_de_planta::test_meia_diagonal_fica_presa_na_diagonal_que_trava |
| 21/10 | Posto V2 (prints: "pilar com chapinhas" no meio da transição): o montante U de ponta da tesoura que chega, desenhado de lado na elevação da TRANSIÇÃO 9 (e 2, 4–7, TRELIÇAS 12/13/15), entrava como montante da transição, a 11 cm do montante 2L — 21 peças duplicadas | ad76db2 | test_de_planta::test_ponta_da_trelica_que_chega_vista_de_lado_sai |
| 21/10 | O Andrey sem nenhum projeto: a tela inicial vazia não tinha o Importar pacote (só na barra de cima, escondida com a lista vazia) | f110e07 | verif_compartilhar_ui ("a tela vazia tem o Importar pacote…") |
| 21/10 | Vicente Residence ("essas duas não ficaram muito legais, não são informações úteis para obra"): a localização punha todos os andares do prédio uns sobre os outros numa planta só, com eixos inventados das caixas, e a chumbação não tinha os 924 chumbadores químicos das lajes | e801211 | test_predio (localização por pavimento, chumbação com os químicos) |
| 21/10 | Posto V2 na tela 2D + 3D: com a Montagem aberta no 2D, escolher uma peça no 3D enquadrava um quadro em branco (a caixa vinha nas coordenadas da planta do cliente) e a Montagem travava com zoom (56–75 ms por quadro de tela para reposicionar os títulos dos 74 quadros) | 7aafc5f | verif_montagem_3d_ui |
| 21/10 | Hangar: as pontas que o usuário montou à mão (T1 em quadro de U com meia-esquadria e no final; T2 com o 45° até o topo e a diagonal da ponta entre as almas) não existiam no gerador; a T1/T3 de U deitado ficava 51 mm acima do apoio e 51 mm abaixo das terças; e a terça junto da ponta do composto passava a ser acusada de torcida (o 45° tomado como água) | cb8b335 | test_regras_trelica::test_2_9a_u_simples_quadro_da_ponta_sentado_na_chapa, ::test_2_9a_composto_45_sobe_ate_o_topo_do_banzo_superior, ::test_2_9a_par_dentro_das_bocas_nao_vira_o_banzo, ::test_4_9_terca_junto_da_ponta_do_composto_nao_toma_o_45_como_agua |
