# Catálogo das regras do sistema (o ponto de não retorno)

Erro corrigido não volta, nem no mesmo caso nem com outra forma. O teste de regressão (REGRESSOES.md) guarda o desenho
daquele dia; a **regra** guarda a ideia, e a **conferência** dela olha o modelo inteiro de qualquer obra. Usuário, 21/10:
"o sistema fica andando em círculos" — 22 correções de telha em 5 dias; "a telha vai até a parede" corrigida 4 vezes.

Cuidado por: chat REGRAS · SISTEMA (`Projeto/BRIEFINGS/CHATS/REGRAS-sistema.md`). Caixa de entrada dos outros chats:
`Projeto/BRIEFINGS/CHATS/REGRAS-entrada.md`.

## Como usar

- **Antes de corrigir qualquer defeito:** procure aqui a regra (Ctrl+F pelo assunto: telha, calha, rufo, boca, cantoneira,
  presilha, platibanda, furo…). Se existe, é **reincidência**: diga ao usuário, e a correção começa reforçando a
  conferência da regra até ela pegar o caso (falha antes, passa depois). Corrija no gerador, não no script da obra.
- **Depois de corrigir:** teste + linha no REGRESSOES.md + linha no REGRAS-entrada.md. O REGRAS · SISTEMA acrescenta a
  linha no histórico da regra e +1 no placar.
- **Regra nova** só entra com o "aprovada" do usuário. Até lá fica em "Propostas" (no fim).
- **Histórico depois de 22/10:** as reincidências triadas pelo N.4 (22/10 a 04/11) estão juntas em "Triagem de 22/10 a
  04/11", logo depois do placar, regra por regra. As regras aprovadas nesse período já estão nas seções delas.

- **Regra nova ou mudança de regra** se combina com exemplos antes do código (CLAUDE.md, 21/10): 2–3 casos com imagem e
  medidas para o usuário aprovar. Os casos aprovados viram o teste e o **exemplo** da regra aqui.

Cada regra tem: **código**, enunciado (com as palavras do usuário), **aprovada** (data e onde), **aplica-se a**, onde está
no **código**, a **conferência** que a verifica no modelo inteiro, os **testes** e o **histórico** de reincidências.
Situação da conferência: **sim** (pega no modelo inteiro), **parcial** (pega parte das formas), **não** (só o teste do caso).

**Teste por propriedade** (Hypothesis, só no desenvolvimento): o teste sorteia a forma do caso (ângulo da parede, curva,
terça emendada, inclinação, vão) num modelo mínimo e confere a regra em todas, para achar a "próxima forma" do erro antes
do usuário. Sorteio fixo no antes_de_publicar; `METALICA_HIPOTESE=aleatorio` sorteia casos novos. Arquivo:
`testes/test_propriedades_cobertura.py`.

| Regra | Teste por propriedade | Situação |
|---|---|---|
| COB-03 | parede reta de 3° a 12° para os dois lados, face de 150 a 1600 mm, 2–5 terças, inclinação 2–30 %, vão 0,9–1,8 m, última terça emendada ou não | verde (40 fixos em 3,6 s; 400 aleatórios em 21/10). Na 1ª rodada achou a fresta na emenda (corrigida em c8f1e1f) |
| COB-01 | — | a fazer (sortear telhados mínimos e conferir com `cobertura_continua`) |

## Placar de reincidências

Reincidência = defeito corrigido de novo, numa regra que já existia (inclusive com outra forma). Meta: zero.
Triagem inicial de 21/10 (REGRESSOES.md + git log desde 12/10); atualizado em 04/11 pelo N.4 com a caixa de 22/10 a 04/11
(+62). Ordem: mais reincidências primeiro.

| Regra | Reincidências | Conferência | Última |
|---|---|---|---|
| GER-01 cada barra uma vez só | 7 | parcial | 03/11 SESI (paredes ARQ e capas um dentro do outro; só no script da obra). Barras pela seção desde 29/10 (372490b); sólidos ainda não |
| COB-04 cada água é um plano | 6 | sim, mas não barra | 04/11 SESI (telha levantada no transpasse entre panos; só no script da obra) |
| COB-03 telha até a parede | 5 | parcial | 30/10 SESI (terça sem telha até a borda; conferência reforçada) |
| GER-03 nenhuma ponta solta | 5 | sim | 02/11 Galpão Novo 60878fe (`pecas_sem_encosto`, pelas faces) |
| TES-7 mesma peça, mesmo nome | 5 | parcial | 30/10 Galpão Existente bd1c514 (o consistencia.py acusa, não trava) |
| COB-02 nada atravessa telha, calha e rufo | 4 | parcial | 03/11 SESI (calha e capa atravessados por pilaretes; só no script da obra). A telha desde 29/10; calha e rufo não |
| GER-02 nada atravessa outra peça | 4 | parcial | 03/11 SESI (airbrises dentro das paredes ARQ; só no script da obra). Viga × viga pela seção desde 29/10 (a2e78bc) |
| FAB-03 peso dos dobrados | 4 | sim | 30/10 7a6b475 (o catálogo inteiro conferido) |
| GER-06 a peça é como o projetista desenha | 4 | não | 03/11 Galpão Novo (simples no lugar da transição; só no script da obra) |
| GER-08 tudo o que o desenho mostra vira peça | 4 | não | 30/10 Galpão Novo (25,8 t de chapas laterais das notas; só no script da obra) |
| TEL-02 cada peça no sistema que diz o que ela é | 4 | sim | 29/10 Galpão Existente 6cc14e3 |
| COB-01 sem fresta nem buraco | 3 | sim | 21/10 c8f1e1f (Posto V2, 53 buracos e 43 frestas) |
| COB-12 o rufo segue a telha | 3 | **não** | 03/11 SESI (11 rufos ajustados à mão; só no script da obra) |
| FAB-01 furação das terças | 3 | parcial | 30/10 Posto V2 (ST1 a 40 mm; a R6 olha só a terça) |
| TEL-01 barra de andamento | 3 | parcial | 03/11 conferência da 0.9.2 (duas barras no rodapé) |
| GER-04 3D vinculado ao 2D | 3 | parcial | 29/10 Galpão Novo 510fb67 (planta por planta; peça por peça não) |
| TES-3.1 nada atravessa o banzo | 2 | sim | 19/10 22c229a |
| TES-2.2 banzos abrem para dentro | 2 | sim | 21/10 8421ab5 |
| TES-2.1 U com a alma atravessando o plano | 2 | parcial | 27/10 SESI (peças lidas sem encostar não formam treliça; só no script da obra) |
| TES-2.9 banzo 2U composto | 2 | sim | 28/10 Galpão Novo (o par como uma barra "2×"; só no script da obra) |
| COB-05 toda borda é fechada | 2 | parcial | 03/11 SESI (telha interna abaixo do ACM; só no script da obra) |
| COB-06 calha onde a água chega | 2 | parcial | 03/11 Galpão Novo ed3bbb3 (`calhas_duplas`) |
| COB-13 peças inteiriças | 2 | **não** | 30/10 SESI (capa interrompido; só no script da obra) |
| FAB-05 porcas do chumbador | 2 | parcial | 30/10 Galpão Existente (só no script da obra) |
| TES-2.5 cantoneira em par | 1 | sim | 27/10 Posto V2 a703f6c (o par nas duas faces do caixão) |
| FAB-07 3D → detalhe → prancha | 1 | **não** | 23/10 ligações (furo do 3D sem furo na prancha) |
| FAB-08 chumbador mecânico | 1 | **não** | 24/10 SESI (Parabolt como químico; a 1ª foi o Hardbolt, 14/10) |
| GER-07 o Original traz as pranchas do projetista | 1 | sim | 03/11 WE Coqueiral 9265545 (`tem_o_original`) |
---

## Triagem de 22/10 a 04/11 (REGRAS · SISTEMA N.4, 04/11)

150 linhas da caixa REGRAS-entrada, de 22/10 a 04/11:
- **62 reincidências**, em 58 linhas. **34 linhas foram corrigidas só no script da obra**: SESI, Galpão Novo, Edifício
  Administrativo e Galpão Existente, obras montadas por script sem gerador comum.
- 6 casos em que a conferência pegou antes do usuário (não contam).
- 19 linhas com regra nova aprovada pelo usuário; 17 viraram propostas.
- 49 defeitos pontuais sem regra, como o CAD 2D, o editor 3D, as Cenas e o desempenho. O teste de regressão basta.

**O que mudou nas conferências** (reforços feitos pelos chats donos no código comum):
- GER-01 `repetidas` pela seção (372490b);
- GER-02 viga × viga pela altura da seção (a2e78bc);
- GER-03 `pecas_sem_encosto` (60878fe);
- GER-04 planta por planta (510fb67);
- GER-07 `tem_o_original` (9265545);
- COB-02 `_barras_na_telha`;
- COB-03 `terca_sem_telha`;
- COB-06 `calhas_duplas` (ed3bbb3);
- FAB-03 o catálogo inteiro (941fa4e, 7a6b475);
- TEL-01 uma barra por vez;
- TEL-02 a expressão do telhado (6cc14e3);
- TES-7 nome do 3D × romaneio no consistencia.py (840c3da).

**Histórico das reincidências** (data, obra, commit; "script" = corrigido só no script da obra):
- **COB-02:** 29/10 SESI, terças acima da telha (conferência reforçada; modelo no script); 03/11 SESI, calha CM4 atravessada
  por pilaretes (script); 03/11 SESI, capa do muro atravessando os pilares (script).
- **COB-03:** 30/10 SESI, terças à mostra até a borda (conferência reforçada; modelo no script).
- **COB-04:** 23/10 Posto V2, a TESOURA 14 virada e as telhas levantadas (7601597; a correção 47b588a, do efeito, foi
  desfeita); 26/10 Posto V2, terça fora do alinhamento e 0,10 m abaixo do outro lado da calha (fc00ae9); 27/10 Posto V2, terça
  picada sobre a TRANSIÇÃO 9 (4ba1089); 03/11 SESI, TM1 erguida até o banzo da VF (script); 04/11 SESI, telha levantada
  no transpasse (script). Em todas, a conferência acusava (telha_degrau) e a montagem seguiu. **Reforço:** barrar.
- **COB-05:** 30/10 SESI, capa fora do lugar (conferência reforçada); 03/11 SESI, telha interna 95 mm abaixo do ACM (script).
- **COB-06:** 26/10 Posto V2, calha do vale parando 2 m antes (fc00ae9); 03/11 Galpão Novo, duas calhas lado a lado no vale (ed3bbb3).
- **COB-12:** 30/10 SESI, rufo em degrau (script); 03/11 SESI, 11 rufos ajustados à mão pelo usuário (script; conferir_ajustes_usuario.py).
- **COB-13:** 30/10 SESI, capa do muro interrompido (script).
- **GER-01:** 26/10 SESI, 5 suportes para 66 terças: "um suporte por apoio" vale também para o apoio sem suporte (script);
  29/10 ADM, duas W530 no mesmo lugar (372490b, reforço); 03/11 SESI, capa dentro de outro (script); 03/11 SESI, 50 pares de
  paredes ARQ uma dentro da outra (script). **Reforço:** sólido dentro de sólido da mesma camada.
- **GER-02:** 22/10 Hangar, a castanha entrando na CB1 (5cd788b; a `choques` não olha barra × chapa); 29/10 ADM, 45 vigas
  atravessando outras (a2e78bc, reforço); 03/11 SESI, airbrises dentro das paredes ARQ (script). Resto da 6b22115: 22/10
  SESI, correntes 7 mm fora da alma (d25a5e2), sem +1.
- **GER-03:** 27/10 SESI, ~1.800 pontas a 10–300 mm (script, `fechar_nos.py`); 28/10 Galpão Novo, terças da platibanda a 16 cm
  (script); 02/11 Galpão Novo, quadros de suporte voando (60878fe, reforço). Lição de 28/10 (SESI, BM14): a conferência não
  isenta uma peça pelo nome do apoio sem ver o apoio no 3D.
- **GER-04:** 27/10 Galpão Novo, pente fino com o 3D fora do desenho (script); 27/10 SESI, vínculo à vista errada, 3.002 de
  6.036 peças (script); 29/10 Galpão Novo, vigas do forro sem traço (510fb67, reforço). **Reforço que falta:** a peça e a
  vista (prova por vetores, pente_fino_vinculo.py), e a remontagem rodar o `vinculo_2d.conferir` no fim (27/10, Posto).
- **GER-06:** 26/10 SESI, pilaretes 100 mm curtos (script); 27/10 Galpão Novo, terça de 89,5 m atravessando o prédio (script);
  29/10 Posto V2, CH6 400 × 390 contra o detalhe 400 × 400 (bases_locacao); 03/11 Galpão Novo, simples no lugar da transição (script).
- **GER-07:** 03/11 WE Coqueiral, o PDF recebido sem o Original (9265545, reforço).
- **GER-08:** 26/10 ADM, vigas W530 faltando (script; leitura a duas linhas); 27/10 ADM, o P12 fora da camada (script); 28/10
  SESI, os 22 SP5 do romaneio sem peça (script); 30/10 Galpão Novo, as chapas laterais 9,52 das notas, o gancho dos
  chumbadores e as diagonais do lanternim, 25,8 t (script).
- **TEL-01:** 27/10, rodapé do CAD com textos sobrepostos (37da918); 03/11, duas barras no rodapé (0.9.2); 03/11, o "~28 %"
  e o rodapé sobreposto na tela dividida.
- **TEL-02:** 29/10 Galpão Existente, o telhado do arquitetônico fora da Cobertura (6cc14e3).
- **TES-2.1/2.3:** 27/10 SESI, a diagonal em U solta do painel de ponta (81d299f); 27/10 SESI, TS6 com peças lidas sem encostar (script).
- **TES-2.5:** 27/10 Posto V2, o par nas duas faces do caixão, pelo ajuste à mão do usuário (a703f6c, VERSAO_REGRAS 6).
- **TES-2.9:** 28/10 Galpão Novo, o par ]-[ como uma barra "2×", 32 t a menos na lista (script).
- **TES-7:** 24/10, a peça girada 180° com outra marca (_assinatura_posicao); 30/10 Galpão Existente, duas T2/T3 diferentes
  (941fa4e); 30/10 Sooro, a chamada do S.T. com os nomes das chapas (d3047c4); 30/10 Galpão Existente, CH35 como "PL13.3" no 3D
  e "PL14.1 12x · total 04x" (840c3da, bd1c514). **Reforço:** a trava na emissão.
- **FAB-01:** 29/10 Posto V2, 77 terças e 398 ST fora do passo (96db66b); 29/10 Posto V2, ST na ponta (bbb9a0e); 30/10 Posto V2,
  ST1 sob terça a 22 % (celulas.py). **Reforço:** conferir o par do próprio suporte e recusar o DXF de corte como a R6 recusa a prancha.
- **FAB-03:** 28/10 SESI, Ue sem o enrijecedor e "L 50×2 (FF)" (o auditor); 30/10 Galpão Existente, Ue 200 a 7,824 (941fa4e);
  30/10 SESI, L (FF) e laminadas pela regra das dobras (7a6b475).
- **FAB-05:** 30/10 Galpão Existente, 218 chumbadores sem porca (941fa4e); 30/10 Galpão Existente, CB5 sem porca (script).
- **FAB-07:** 23/10, a cantoneira da SC1 e a castanha "sem furo" na prancha (ligações).
- **FAB-08:** 24/10 SESI, o Parabolt como químico (resumos.py).

**Origens e refinamentos sem +1:**
- TES-2.3: os montantes da junta com as costas na junta (22/10 Hangar, 5cd788b, VERSAO_REGRAS 5).
- GER-04: a peça sabe de que planta veio (22/10 Posto, 847bbfa); o prédio em pavimentos (26/10 ADM); a elevação oblíqua
  (27/10 Galpão Novo, 54254f3); o encaixe das plantas pelos balões (23/10 Posto, ee44272).
- GER-07: os leitores do Original ignoram as folhas (27/10 Posto, c8b1a4a); código comum `nucleo2d/folhas_papel.py` (8cd53e9).

## COB — Cobertura: telhas, calhas e rufos

Fontes: as 11 regras aprovadas em 19/10 (`Projeto/ANALISES/Montagem/Regras-da-cobertura-telhas-calhas-rufos-2026-10-19.pdf`,
memória regras-telhas-calhas-rufos), o adendo do Guia de 12/10 (G1) e as 22 linhas de telha do REGRESSOES.md.
Gerador: `nucleo3d/telhas_cobertura.py`. Conferência: `conferencia_3d.cobertura` e `conferencia_3d.telha_ao_lado`, no fim
da montagem e no Estrutura › Verificar apoios. Testes: `test_telhas_cobertura.py` (43), `test_conferencia_cobertura.py` (4),
`test_conferencia_3d.py`. **As telhas ainda são lançadas por scripts de cada obra** (sem botão na tela) — por isso
a pergunta de toda correção de telha é: foi no `telhas_cobertura.py` ou só no script da obra?

### COB-01 — A cobertura não tem fresta nem buraco
- **Enunciado:** dentro de um telhado, a telha cobre tudo: nenhuma fresta entre chapas vizinhas e nenhum buraco no meio
  da água, nem nos encontros de faixas, nas emendas das terças ou nas bordas curvas.
- **Aprovada:** **PROPOSTA** — nomeada no plano aprovado em 21/10; o enunciado espera o "aprovada" do usuário.
- **Aplica-se a:** toda obra com telha lançada.
- **Código:** `telhas_cobertura._analise` (faixas, panos, `PONTE_TERCA`, `JUNTA_ESTACAO`).
- **Conferência:** **sim** (21/10 noite) — `conferencia_3d.cobertura_continua`, no `conferir`, no fim da montagem e no
  Verificar apoios ("Cobertura: buraco" e "Cobertura: fresta"). É a conta do chat do Posto, levada ao sistema.
  - Primeiro a união em planta das faces de cima dos sólidos das camadas Telhas/Calhas/Cumeeiras/Rufos. O fechamento
    em pé entra como uma faixa de 30 mm.
  - **Fresta:** o que fechar a união por 2 × 60 mm tapa (≥ 0,003 m²).
  - **Buraco:** o anel de dentro (≥ 0,005 m²) que a fresta não fecha.
  - **Vão de projeto, não acusado:** ≥ 1 m² com 95 % do contorno a até 300 mm de parede ou platibanda.
  - Leva ~2,5 s no Posto V2 (3.573 sólidos).
  - Posto V2 de antes: 23 buracos e 43 frestas (a conta original dava 53 buracos: 30 eram as mesmas frestas e 1 era a
    oval). Depois do c8f1e1f: 7 buracos e 17 frestas, que a obra ainda vai classificar.
  - **Achado no telhado de exemplo do gerador:** no canto da calha com o encosto lateral sobra um vão de 197 × 104 mm sem
    nada (o encosto começa em x 293, a calha acaba em x 96). Pedido ao FERRAMENTA · LEITURA DXF/IFC → 3D.
- **Testes:** test_sem_fresta_onde_as_pontas_das_tercas_quase_coincidem, test_telha_passa_por_cima_da_terca_cortada_pela_trelica_de_baixo,
  test_telha_ate_a_telha_vizinha_de_outra_direcao; test_conferencia_cobertura::test_cob01_* (chapa que falta, fresta
  entre chapas, abertura cercada × aberta, o Posto V2 de antes e de depois congelado em
  `Projeto/bateria/entradas/posto-v2-cobertura/`, o canto calha × encosto em xfail estrito).
- **Histórico:**
  - 21/10 Posto V2 — frestas na água inteira (o trecho curto entre as pontas das terças emendadas era pulado; o pedaço < 30 mm saía) — 8bedaa1.
  - 21/10 Posto V2 — o triângulo sem telha no norte da oval e a fila de buracos de 1 m (a faixa juntada apagava outros panos) — 8e9ac8c. **Reincidência.**
  - 21/10 Posto V2 (noite) — 53 buracos e 43 frestas no modelo gravado — c8f1e1f (gerador). **Reincidência.**

### COB-02 — Nada atravessa a telha, a calha ou o rufo
- **Enunciado:** nenhuma peça passa por dentro da telha, da calha ou do rufo, e nenhuma chapa da cobertura passa por
  dentro de uma barra. A treliça que sai acima da telha é revestida (COB-16); a calha e o rufo param na face da treliça
  que atravessam (COB-15).
- **Aprovada:** 19/10 (regras 9 e 11 da cobertura); "nada atravessa a telha" como regra do modelo inteiro — **PROPOSTA**
  do plano de 21/10.
- **Aplica-se a:** toda obra com telha, calha ou rufo lançado.
- **Código:** `telhas_cobertura` (pontas de calha e rufo na face, meia-esquadria).
- **Conferência:** **parcial** — `conferencia_3d._cobertura_choques` ("rufo_choque") pega a chapa de calha/rufo dentro de
  uma barra (3 mm de folga). Não pega: a calha cortada onde cruza uma treliça (o furo na calha do Posto V2), a barra
  atravessando o pano de telha.
- **Testes:** test_capas_em_meia_esquadria_no_canto, test_conferencia_cobertura::test_rufo_atravessando_peca,
  test_trelica_acima_da_telha_no_meio_do_telhado_e_revestida.
- **Histórico:**
  - 17/10 Posto CB — a TRANSIÇÃO 1 e as tesouras de cima atravessando a telha sem revestimento nem rufo — a2d716a.
  - 19/10 Mercado — capas atravessando a outra treliça nas quinas; pontas de calha entrando nas treliças — 984fbd8.
  - 21/10 Posto V2 — calhas cortadas onde cruzam uma treliça — c8f1e1f (gerador). **Reincidência.** A conta do Posto
    para a conferência que falta está em `Projeto/OBRAS/Posto-CB/leitura-3d/furam_telha.py` (barras que atravessam a telha).

### COB-03 — A telha vai até a parede
- **Enunciado:** a telha chega até a face da parede, platibanda ou treliça que fecha o telhado, seja qual for a forma da
  borda: paralela, diagonal, quase paralela, curva ou o telhado vizinho de outra direção. A ponta é cortada na forma da
  borda e é a mesma chapa (COB-14). O afastamento é só o da calha de parede (COB-06).
- **Aprovada:** **PROPOSTA** — nomeada no plano aprovado em 21/10 (o exemplo do usuário do "andando em círculos").
- **Aplica-se a:** cobertura com parede, platibanda ou treliça de borda (`_e_barreira`, banzos, `_paredes_curvas`).
- **Código:** `telhas_cobertura` (`PAREDE_PARALELA` = 3°, `PASSO_CURVA`, `_paredes_curvas`).
- **Conferência:** **parcial** — "borda_aberta" (COB-05) só acusa a borda sem nada até 0,35 m para fora: a telha que para
  a 0,3 m da parede passa. Falta a conta "distância da ponta da telha à face da parede ≤ afastamento previsto".
- **Testes:** test_borda_escalonada_pela_linha_emendada, test_telha_ate_a_face_da_parede_diagonal,
  test_telha_ate_a_platibanda_quase_paralela_com_terca_junto, test_telha_ate_a_platibanda_curva,
  test_telha_ate_a_telha_vizinha_de_outra_direcao, test_recorte_na_ponta_da_chapa_e_a_mesma_telha.
- **Histórico:**
  - 17/10 Posto CB — degraus de até 1,35 m da borda diagonal da TRANSIÇÃO 16 — a2d716a.
  - 21/10 Posto V2 — não chegava na platibanda da oval (a PAINEL 12, 9,6° fora das terças, contada como paralela) — 8bedaa1. **Reincidência.**
  - 21/10 Posto V2 — falhas nas bordas curvas (a platibanda calandrada não contava como parede) — 8e9ac8c. **Reincidência.**
  - 21/10 Posto V2 — a telha que chega na parede diagonal saía em duas peças (chapa + recorte) — 3391273. **Reincidência.**
  - 21/10 Posto V2 (noite) — borda até a beira do pano, linha de terça inteira — c8f1e1f. **Reincidência.**
- **Achados do teste por propriedade (21/10 noite):**
  - **Terça emendada:** antes do c8f1e1f, 38 de 55 casos falhavam, todos na estação da emenda da última terça ou no
    pedaço curto. O recorte até a parede saía em duas peças com **fresta de 2 mm** (y 1999 → 2001) e uma tira de 39 mm.
    O código de antes já fazia isso. Corrigido pelo Posto no c8f1e1f (`_linhas_inteiras`), com
    test_recorte_ate_a_parede_inteiro_na_emenda_da_ultima_terca. **Achado antes do usuário.**
  - **Parede paralela (< 3°, `PAREDE_PARALELA`):** a telha para na última terça, qualquer que seja a distância (com a
    face a 1,4 m ficam 1,3 m abertos; a "borda_aberta" só acusa a partir de 0,35 m). O gerador chama isso de "borda
    comum". **Decisão do usuário**, que vai com os exemplos da COB-03.

### COB-04 — Cada água é um plano
- **Enunciado (G1, 12/10):** "a telha passa reta de uma terça à outra (sem dobra) e de uma chapa à vizinha (sem degrau),
  até 20 mm". "O que comanda no final é a telha, toda a estrutura é feita para acomodá-las." Terça da calha sobe com
  suporte; terça torta fica nivelada no apoio; a altura da terça vem de onde ela apoia de verdade (C7).
- **Aprovada:** 12/10 (Guia básico, adendo, G1 e C7).
- **Aplica-se a:** toda cobertura com terças.
- **Código:** `telhas_cobertura._analise` (terça fora do plano, `tol_plano`), `de_planta` (C7: altura da terça).
- **Conferência:** **sim** — `conferencia_3d.telha_ao_lado` (telha de teste só na conta: "degrau" e "dobra" ≥ 20 mm;
  cumeeira e vale não contam) e, desde 04/11, `conferencia_3d.telha_fora_da_agua` (a telha lançada que sobe mais que a
  caída de 0,3 na medida dela em planta + 300 mm: "fora_da_agua", no topo dos apontamentos) e `telha_baixa` (a telha da
  cobertura com o topo a menos de 1,5 m do pé dos pilares).
- **Testes:** test_agua_reta_de_5_por_cento, test_terca_erguida_no_meio_da_agua, test_terca_da_calha_sobe_ao_plano_com_suporte,
  test_terca_torta_fica_nivelada_no_apoio, test_telha_ao_lado_aponta_o_degrau_e_a_dobra, test_linha_da_calha_emendada_sobe_inteira,
  test_linha_emendada_nao_sobe_para_dentro_de_outra_peca, test_chapa_reta_por_cima_da_terca_fora_da_reta,
  test_conferencia_3d::test_telha_ao_lado_e_os_avisos, test_terca_de_parede_nao_da_telha_de_borda (o canto noroeste do
  Hora Certa · Galpão Novo congelado), test_conferencia_3d::test_telha_fora_da_agua, test_terca_de_parede_empilhada_nao_da_telha,
  test_conferencia_3d::test_telha_baixa.
- **Histórico:**
  - 17/10 Posto CB — degrau de 133 mm na calha x 34,06 (a ponta da linha subia sozinha ao plano) — a2d716a.
  - 21/10 Posto V2 — "trecho caído/levantado": a terça fora da reta partia a chapa — 8bedaa1. **Reincidência** (a
    conferência acusava a dobra; o gerador seguia a terça em vez de passar reto).
  - 04/11 Hora Certa · Galpão Novo — 105 telhas da borda subindo até 64 m (print do usuário: "esses elementos bugaram"): a
    inclinação da borda contra a parede (`inclinacao`) vinha da vizinha mais perto, a terça de fechamento a prumo (caída
    30–38); agora só vizinha que forma água (caída ≤ 0,3), e terça de parede não dá telha de borda. **Reincidência** (a
    telha_ao_lado não olhava a telha sozinha): conferência reforçada, `telha_fora_da_agua` (109 no modelo de antes, 0 depois).
  - 04/11 Hora Certa · Galpão Novo (auditor N12, na rev4) — 185 telhas de 0,30 m deitadas na terça de fechamento mais baixa
    das fachadas (0,7 m do piso) e tiras sobre as duas terças da platibanda: a terça de PAREDE dava pano. Agora a terça em
    pilha a prumo (3 ou mais na mesma linha, `_tercas_de_parede`) não dá pano (segue como terça de outra direção).
    **Reincidência** (a correção de 15:07 só olhava a inclinação): conferência `telha_baixa` (185 antes, 0 depois).

### COB-05 — Toda borda de telhado é fechada
- **Enunciado (regra 11, 19/10):** toda borda de telhado termina em calha, rufo, fechamento, parede ou no telhado de
  cima. Telha encostada em parede leva rufo de encosto.
- **Aprovada:** 19/10 (regras da cobertura, 11).
- **Aplica-se a:** toda obra com telha lançada.
- **Código:** `telhas_cobertura` (calhas, rufos, fechamentos).
- **Conferência:** **sim** — `conferencia_3d.cobertura`: "borda_aberta" (trecho ≥ COBERTURA_MIN sem nada até 0,35 m) e
  "sem_rufo" (borda encostada em sólido que não é da cobertura).
- **Testes:** test_conferencia_cobertura (os 4).
- **Histórico:** (nenhuma reincidência registrada)

### COB-06 — Calha onde a água chega
- **Enunciado:** em todo encontro de águas baixas (o vale) vai calha: as telhas afastadas 150 mm e a calha centrada por
  baixo, com 100 mm de telha por cima de cada lado (350); usuário, 17/10: "as telhas devem ter um afastamento entre si e
  a calha ficará centralizada deixando os cobrimentos necessários para a água não infiltrar". Na borda baixa contra a
  parede (regra 5, 19/10): calha de 200 com a telha a 100 da face. Fundo 150, calha **aberta** (U), uma peça por linha.
- **Aprovada:** 17/10 (Posto) e 19/10 (regra 5).
- **Aplica-se a:** cobertura com vale ou com água descendo para parede/platibanda.
- **Código:** `telhas_cobertura` (`AFASTAMENTO_CALHA`, `COBRIMENTO_CALHA`, `AFASTAMENTO_PAREDE`, `FUNDO_CALHA`).
- **Conferência:** **parcial** — "borda_aberta" acusa a borda baixa sem calha; ninguém confere a medida (afastamento,
  cobrimento, calha por baixo da telha) nem a calha fechada.
- **Testes:** test_calha_no_vale_em_v, test_vale_com_a_terca_do_fundo_baixa_ao_lado_ganha_calha,
  test_calha_da_parede_por_baixo_da_ponta_da_telha, test_terca_baixa_no_meio_da_agua_nao_vira_calha,
  test_calha_da_parede_na_borda_baixa_contra_a_platibanda, test_calha_aberta_em_cima, test_calha_terca_baixa_e_transicao_no_meio.
- **Histórico:**
  - 17/10 Posto CB — encontros de águas baixas sem calha; calha 50 mm por cima da telha — 8cf8d70.
  - 19/10 Mercado — sem calha na borda baixa contra a platibanda — 0f37140.
  - 19/10 Mercado — calha fechada como tubo — 51d5532.

### COB-07 — O fechamento encosta na face da treliça
- **Enunciado (regra 1, 19/10):** o fechamento lateral encosta na face das barras da treliça (não a 110 mm do eixo).
- **Aprovada:** 19/10. **Aplica-se a:** treliça de fechamento (P/VT/VL/PAINEL/TRANSIÇÃO).
- **Código:** `telhas_cobertura` (fechamento). **Conferência:** **não**.
- **Testes:** test_fechamento_encosta_na_face_da_trelica, test_fechamento_duplo_no_painel.
- **Histórico:** 19/10 Mercado — fechamentos a 110 mm do eixo — b627225.

### COB-08 — Quem leva fechamento
- **Enunciado (regra 2, 19/10):** fecham as treliças P/VT/VL/PAINEL/TRANSIÇÃO do perímetro, nas duas faces (7035 fora,
  TP25 dentro); o degrau entre dois telhados (o de baixo é o "fora"); a P.n sem telhado de lado nenhum também fecha
  (fora = longe do centro).
- **Aprovada:** 19/10. **Aplica-se a:** obra com platibanda, degrau entre telhados ou treliça de perímetro.
- **Código:** `telhas_cobertura` (nomes da regra TES-7: `^(P|VT|VL)\.\d`). **Conferência:** parcial ("borda_aberta").
- **Testes:** test_fechamento_na_platibanda_com_os_nomes_da_regra, test_fechamento_no_degrau_entre_dois_telhados,
  test_platibanda_sem_telhado_de_lado_nenhum.
- **Histórico:** 19/10 Mercado — platibandas com os nomes P.n/VT.n sem fechamento — 6c3e423; 19/10 Mercado — degrau e
  terraço sem fechamento — a48a8d3.

### COB-09 — A telha passa por cima do fechamento na linha dela
- **Enunciado (regra 3, 19/10):** treliça de fechamento com o topo na linha da telha → a telha passa POR CIMA (beiral até
  a onda de fora + 50); o fechamento para embaixo do beiral.
- **Aprovada:** 19/10. **Aplica-se a:** fechamento com o topo na linha da telha (degrau ala × galpão).
- **Código:** `telhas_cobertura` (`ALTURA_ONDA_FECHAMENTO`). **Conferência:** parcial ("borda_aberta" vê o beiral).
- **Testes:** test_telha_passa_por_cima_do_fechamento_na_linha_dela, test_telha_segue_sob_o_telhado_de_cima.
- **Histórico:** 19/10 Mercado — a telha da ala parava na última terça — b627225; 19/10 a P.15 até a face do pilar — f331063.

### COB-10 — No degrau, o fechamento de fora desce até o telhado de baixo
- **Enunciado (regra 4, 19/10):** o fechamento de fora desce até 50 mm da telha/calha de baixo; nada de chapa alta de rufo.
- **Aprovada:** 19/10. **Aplica-se a:** degrau entre telhados. **Código:** `telhas_cobertura`. **Conferência:** **não**.
- **Testes:** test_rufos_do_fechamento, test_fechamento_no_degrau_entre_dois_telhados.
- **Histórico:** 19/10 Mercado — chapa alta no pé do fechamento sobre o anexo e a calha — 51d5532.

### COB-11 — Os rufos e as medidas
- **Enunciado (regra 6, 19/10):** rufos #26: capa (abas 100), encosto (150 + 150), contra-rufo até 150 acima da crista da telha.
  **Usuário, 03/11 (padrão da empresa):** calha em chapa 0,65 mm, rufo 0,50 mm. A espessura da calha **ainda não está no
  código** (pedido ao dono do `telhas_cobertura`).
- **Aprovada:** 19/10. **Aplica-se a:** obra com fechamento ou parede encostando na telha.
- **Código:** `telhas_cobertura`. **Conferência:** **não**.
- **Testes:** test_rufos_do_fechamento, test_capa_desce_ate_a_telha_perto_do_topo, test_contra_rufo_sobe_acima_da_telha_e_calha_inteira.
- **Histórico:** 19/10 Mercado — sem rufos nos fechamentos — 0f37140; 19/10 contra-rufo embaixo da telha — b886cb9.

### COB-12 — O rufo segue a telha
- **Enunciado (regra 7, 19/10):** o rufo acompanha a inclinação da telha (lido a cada 250 mm), sem degrau nem pedaço reto.
- **Aprovada:** 19/10. **Aplica-se a:** rufo ao longo de borda inclinada. **Código:** `telhas_cobertura`.
- **Conferência:** **não** (a FAZER: o desvio entre o rufo e a telha ao longo da borda).
- **Testes:** test_rufo_acompanha_a_telha_e_e_uma_peca_so, test_rufo_segue_a_telha_com_a_platibanda_passando_do_telhado.
- **Histórico:** 19/10 Mercado — rufos picotados e em degraus — 51d5532; 19/10 Mercado — reto na doca, em degraus sobre o
  anexo, quebrado na P.2 — b886cb9. **Reincidência.**

### COB-13 — Peças inteiriças
- **Enunciado (regra 8, 19/10):** rufo e calha saem numa peça por linha; capa e encosto separados, um de cada por lado.
- **Aprovada:** 19/10. **Aplica-se a:** toda calha e rufo. **Código:** `telhas_cobertura`.
- **Conferência:** **não** (a FAZER: duas peças da mesma linha encostadas pela ponta).
- **Testes:** test_capa_e_encosto_inteiros_perto_do_topo, test_contra_rufo_sobe_acima_da_telha_e_calha_inteira, test_rufo_acompanha_a_telha_e_e_uma_peca_so.
- **Histórico:** 19/10 Mercado — rufos picotados — 51d5532; 19/10 Mercado — rufos e calhas em pedaços — b886cb9. **Reincidência.**

### COB-14 — A telha é uma chapa por faixa, com o recorte junto
- **Enunciado:** da calha à cumeeira, a faixa é uma chapa só (até o comprimento máximo da telha), mesmo com as terças
  emendadas em tesouras diferentes; o beiral sobre a calha e o recorte até a parede diagonal são a mesma telha.
- **Aprovada:** **PROPOSTA** — a correção de 21/10 ("pode seguir", conferida pela paginação da folha 12 do Posto V2).
- **Aplica-se a:** toda cobertura. **Código:** `telhas_cobertura`. **Conferência:** **não** (contar chapas por faixa).
- **Testes:** test_uma_chapa_por_faixa_com_as_tercas_emendadas_em_estacoes_diferentes, test_recorte_na_ponta_da_chapa_e_a_mesma_telha,
  test_borda_escalonada_vira_chapa_recortada, test_ondas_da_chapa_no_sentido_da_caida.
- **Histórico:** 21/10 Posto V2 — 1.100 chapas no lugar de ~650 — 3391273.

### COB-15 — Cantos em meia-esquadria; ponta de topo na face
- **Enunciado (regra 9, 19/10):** nos cantos, capa e rufo em meia-esquadria; a ponta de topo para na face da treliça atravessada.
- **Aprovada:** 19/10. **Aplica-se a:** canto de platibanda/fechamento. **Código:** `telhas_cobertura`.
- **Conferência:** **sim** pela COB-02 ("rufo_choque").
- **Testes:** test_capas_em_meia_esquadria_no_canto.
- **Histórico:** 19/10 Mercado — capas atravessando a outra treliça nas quinas — 984fbd8.

### COB-16 — Treliça acima da telha no meio do telhado é revestida
- **Enunciado:** a treliça que sai acima da telha no meio do telhado recebe o revestimento e o rufo (o corte BB do Posto).
- **Aprovada:** 17/10 (cobertura do Posto revista pelo 3D) — **confirmar** como regra.
- **Aplica-se a:** treliça que sobe acima do telhado (transição, tesoura alta). **Código:** `telhas_cobertura`.
- **Conferência:** **não**. **Testes:** test_trelica_acima_da_telha_no_meio_do_telhado_e_revestida.
- **Histórico:** 17/10 Posto CB — TRANSIÇÃO 1 sem revestimento — a2d716a.

### COB-17 — Parede de concreto
- **Enunciado (regra 10, 19/10):** encosto e calha também na parede de concreto.
- **Aprovada:** 19/10. **Aplica-se a:** obra com parede de concreto junto da telha.
- **Código:** **só no script da obra** — o gerador só vê barras; a obra lança uma parede provisória. **Pendência de gerador**
  (pedido ao chat dono do `telhas_cobertura`). **Conferência:** "sem_rufo" (COB-05) vê a parede depois de lançada.
- **Histórico:** (nenhum)

### COB-19 — O lanternim
- **Enunciado (usuário, 03/11, pela figura "duas águas, como o desenho"):** a abertura debaixo do lanternim fica sem telha; a
  telha do topo dele vai pela travessa, em duas águas, com cumeeira no ponto alto.
- **Aprovada:** 03/11 (Hora Certa · Galpão Novo). **Aplica-se a:** cobertura com lanternim.
- **Código:** `telhas_cobertura` (`_lanternins`, `_sem_abertura_do_lanternim`). **Conferência:** **não**.
- **Testes:** test_telhas_cobertura (os 7 de ed3bbb3).
- **Histórico:** 03/11 Galpão Novo — a abertura fechada com telha e o topo sem telha — ed3bbb3 (a 1ª).

---

## TES — Tesoura de aço (montagem das treliças)

Fonte: `Projeto/ANALISES/Montagem/Regras-de-montagem-das-tesouras-revisao-geral-2026-10-16.(docx|pdf)` (aprovadas em
16/10 22h) e os acréscimos até 21/10 (memória regras-modelagem-tesoura). Código: `nucleo3d/regras_trelica.py` (a docstring
é a regra; `aplicar` = classificar + orientar + recuar + encaixar, em todo gerador e script de obra). Conferência:
`regras_trelica.conferir`, chamada por `conferencia_3d.posicao_na_trelica` ("posicao_trelica" no Verificar apoios) e pelo
Modelo › Reanalisar estrutura (`reanalise.py`, VERSAO_REGRAS = 4). Teste: `test_regras_trelica.py` (43: uma função por
regra e os 5 caminhos de geração — tesoura pelo desenho, treliça do editor, galpão treliçado, projeto recebido pela
planta, 3D pelos quadros).

**Aplica-se a** de toda a família: treliça plana de aço (tesoura, meia-tesoura, platibanda, VT, VL, transição). Fora:
tubo, barra redonda, I/W, banzo em caixa (2.8).

| Código | Regra | Aprovada | Conferência (`conferir`) | Testes principais |
|---|---|---|---|---|
| TES-0.1 | Projeto recebido: seguir o projeto (legenda, croqui, cotas); `perfil_do_projeto` não muda | 16/10 | — (princípio; ver PRI-01) | test_1_4_a_legenda_do_projeto_manda |
| TES-0.2 | Estudo nosso sem perfil: padrão Hermes (seção 5), não dimensionar até fechar | 16/10 | — | — |
| TES-1.1 | Linha dupla = um perfil só | 16/10 | não | (leitura: test_de_planta) |
| TES-1.2 | Banzo superior = o contorno de cima (também o topo do painel de ponta vindo como "diagonal") | 16/10 | **sim** ("1.2") | test_1_2_topo_do_painel_de_ponta_vira_banzo |
| TES-1.3 | Banzo inferior = contorno de baixo; linha dupla entre banzos = alma | 16/10 | não | — |
| TES-1.4 | Ponta (peça em pé no apoio) SEMPRE com o perfil do banzo | 16/10 | **sim** ("1.4") | test_1_4_ponta_recebe_o_perfil_do_banzo |
| TES-1.5–1.8 | Montante/diagonal = alma; secundária "um lado só"; presilha não é peça da treliça; tesouras encostadas não se separam | 16/10 | não | test_2_8_presilha_e_secundaria_ficam_fora |
| TES-2.0 | Um plano por tesoura, normal com sinal fixo | 16/10 | (base das outras) | — |
| TES-2.1 | Todo U/Ue com a alma atravessando o plano (exceto o composto, 2.9) | 16/10 | **sim** | test_2_1_e_2_2_banzos_abrem_para_dentro |
| TES-2.2 | Banzos abrem para dentro; o intermediário para cima; nenhum banzo de cima de boca para cima | 16/10 | **sim** | test_2_1_e_2_2_…, test_2_2_banzo_intermediario_abre_para_cima, test_u_simples_com_alma_2l_e_2_2_e_2_5, test_alma_no_plano_de_modelo_antigo_e_acusado_pela_2_2 |
| TES-2.3 | Alma abre para o meio do vão; "a diagonal nunca para cima"; montante do meio para a ponta alta; na junta com dois montantes, as costas na junta (22/10, Hangar) | 16/10 | **sim** | test_2_3_alma_abre_para_o_meio_e_diagonal_nunca_para_cima, test_2_3_montante_no_meio_abre_para_a_ponta_alta |
| TES-2.4 | Cantoneira simples = "um U cortado ao meio" (aba de pé sempre +n) | 16/10 | **sim** | test_2_4_cantoneira_simples_e_um_u_cortado_ao_meio |
| TES-2.5 | Cantoneira em par = um U partido (abas de pé para o centro), par coincidente ≤ 40 mm; vale também nas duas faces do caixão sem ligação entre elas (27/10, ajuste do usuário no Posto V2, a703f6c) | 16/10 (≤ 40 mm: 21/10) | **sim** | test_2_5_cantoneira_em_par_e_um_u_partido |
| TES-2.6 | U deitado fora da tesoura nunca para cima | 16/10 | não (fica com o gerador) | — |
| TES-2.7 | "Virar" do painel = o contrário da regra (`boca_virada`) | 16/10 | **sim** | test_2_7_boca_virada_pelo_usuario_fica |
| TES-2.8 | Fora da regra: tubo, redonda, I/W, secundária, presilha, caixa | 16/10 | — | test_2_8_presilha_e_secundaria_ficam_fora |
| TES-2.9 | **Só o 2U composto**: os dois U de costas, alma no plano, encostados no U que passa entre as almas; 2L por dentro dos perfis | 21/10 (Hangar) | **sim** ("2.9") | test_2_9_* (4) |
| TES-2.9a | Ponta do composto = um U só entre as almas, no final da tesoura; U simples: ponta em quadro, sentado na chapa | 21/10 (Hangar, montada à mão) | **sim** ("2.9a") | test_2_9a_* (5) |
| TES-3.1 | Nada atravessa o banzo: alma cortada na face (3.1a encaixe em `aplicar`; 3.1b trecho dentro do banzo sai; 3.1c degrau no banzo de cima) | 16/10 (3.1a/b 16/10 23h; 3.1c 19/10) | **sim** ("3.1", "3.1c") | test_3_1a_*, test_3_1b_* (3), test_3_1c_* |
| TES-3.2 | Nós no eixo do banzo (< 100 mm = um nó, NBR 8800 6.5.2) | 16/10 (conferência 19/10) | **sim** ("3.2") | test_3_2_no_da_alma_vai_para_o_eixo_do_banzo |
| TES-3.3 | Presilhas max(nota, norma), mín. 2; **a presilha segue o par** (não fura a cantoneira) | 16/10 (posição: 21/10) | **sim** ("3.3") | test_3_3_* (3) |
| TES-3.4 | λ ≤ 200 na alma (5.3.4) | 16/10 | não (fica com a análise) | — |
| TES-3.5 | Furo: a cota do projetista; sem cota d + 1,5 | 15/10 | não — ver FAB-02 | — |
| TES-3.6 | Barra não se dobra | 06/10 | não — ver FAB-04 | — |
| TES-3.7 | Pensar na execução | 14/10 | não — ver PRI-02 | — |
| TES-4.1 | NÃO vai tesoura colada em platibanda: terças até a face de dentro, em L 2"×1/8" soldada na face (exceção: anexo do Mercado, 19/10) | 16/10 | não | — |
| TES-4.2–4.7 | Viga lateral no lado sem fechamento; mesmo topo; fechamento baixo sem banzo do meio; montantes de fachada ≤ 2,5 m fora das linhas das terças; escora do oitão no banzo inferior, U boca para baixo; furação das terças (FAB-01) | 16/10 | não | — |
| TES-4.8 | A que chega para na face da que passa: "o final da tesoura nunca pode invadir a platibanda, deve sempre parar na face interna"; recua pelos nós, nunca prolonga (inclui B7 e B9 do Guia) | 16/10 23h (B7/B9: 12/10) | **sim** ("4.8") | test_4_8_* (3) |
| TES-4.9 | Terça perpendicular à água (10°–70° fora = torcida; ~90° = deitada de propósito) | 19/10 | **sim** ("4.9") | test_4_9_* (2) |
| TES-5 | Perfis do estudo (U 100×50×3,00; > 3,14 m U 150×60; platibanda U 100×50…) — só no 0.2 | 16/10 | não | — |
| TES-7 | Nomes: T.n, MT.n, CT.n, T.C.n, S.T.n, C.V.n, P.n, VT.n, VL.n (mesma assinatura = mesmo n) | 16/10 22h40 | não | (test_regressoes_primeiro_uso_ifc TestNomesDecididosPeloUsuario) |

**Histórico das tesouras** (as correções desde a aprovação de 16/10 22h):
- 16/10 23h Mercado — "algumas diagonais não passaram a regra dos recortes": **o script da obra nunca chamava o encaixe**
  (1.390 almas eixo a eixo) — 6dffa53 → TES-3.1a (o encaixe entrou em `aplicar`). **Reincidência (só na obra).**
- 16/10 23h Mercado — a ponta da tesoura entrando na platibanda — 6dffa53 → TES-4.8 nova.
- 19/10 Mercado — "veja porque passaram na regra": degrau sem corte no banzo de cima e alma 50 mm abaixo do banzo —
  22c229a → TES-3.1c, 3.2. **Reincidência da 3.1.**
- 19/10 Mercado — a fachada empilhada tomada como "a que chega" — 22c229a → TES-4.8 (falso positivo da conferência).
- 19/10 Mercado — terça NC-3 torcida 30,6° — 22c229a → TES-4.9 nova.
- 21/10 Hangar — a reanálise passava "nada a corrigir" com os banzos virados (a peça com `secao_dupla` era pulada) —
  c5d4073 → TES-2.9 nova.
- 21/10 Hangar — a T3 do oitão com a boca para dentro do prédio; 28 cantoneiras fora da regra — 1188b4c. **Reincidência da 2.9.**
- 21/10 Hangar — o U simples com alma 2L lido como "alma no plano" (exceção criada contra a 2.2); a 2.5 casando
  diagonais vizinhas — 8421ab5. **Reincidência da 2.2.** Lição: na dúvida entre o croqui e uma regra aprovada, perguntar.
- 21/10 Hangar — banzos do composto afastados 13,5 mm do montante — 77c9c0f → TES-2.9 (vão = altura do montante).
- 21/10 Hangar/Posto — presilhas tortas e furando a cantoneira ("percebi esse mesmo erro no projeto do posto") —
  f332494 → TES-3.3 (posição). Posto: 692–731 de 7.006, corrigido pelo Reanalisar (VERSAO_REGRAS 4).

---

## GER — Conferências gerais do modelo (montagem pela planta)

Fonte: Guia básico, adendo de 12/10 (B4, B10, C6, C8) e memória conferencia-do-3d. Código: `nucleo3d/conferencia_3d.py`
(`repetidas`, `pontas_soltas`, `choques`), no fim de `de_planta.montar` e no Verificar apoios; `reanalise.py` corrige.
Testes: `test_conferencia_3d.py`, `test_reanalise.py`.

### GER-01 — Cada barra entra uma vez só
- **Enunciado (B10 e C8, 12/10):** a linha repetida na elevação não dobra o montante nem a presilha; um suporte de terça por apoio.
- **Aprovada:** 12/10. **Aplica-se a:** todo modelo.
- **Conferência:** **parcial** — `repetidas` (as mesmas pontas a 15 mm). **Reforçada em 29/10 (372490b):** a barra paralela dentro da outra, pela seção
  (eixos a < ¼ da menor medida, trecho comum > 300 mm). Achou casos nas obras do dev (CD Bom Dia 60, Galpão Novo 9…).
  **Falta:** sólido dentro de sólido (paredes ARQ, capas de rufo), que o SESI corrigiu só no script.
- **Testes:** test_repetida_pega_as_mesmas_pontas_em_qualquer_sentido, test_3_3_presilha_dobrada_aparece_e_sai.
- **Histórico:**
  - 19/10 CD Bom Dia — montantes repetidos (modelo antigo) — 934dbd0 (Reanalisar).
  - 21/10 Posto CB — duas presilhas na mesma altura (uma 6,4 mm fora) — 0af6b75. **Reincidência.**
  - 21/10 Posto V2 — o montante da tesoura que chega, visto de lado, entrava como montante da transição a 11 cm do
    montante 2L (21 peças duplicadas) — ad76db2. **Reincidência** (a conferência não pegou: 11 cm > 15 mm).
  - 22/10 SESI Chapecó — montantes repetidos a 30–120 mm nos cantos (VF9/41/43/47), achados pelo agente de verificação
    (`Projeto/OBRAS/Sesi-Chapecó/verificacao-22-10/metalica.md`). **Reincidência, aberta:** espera o usuário; a
    conferência não pegou.

### GER-02 — Nada atravessa outra peça
- **Enunciado (B4, B9, C6, 12/10):** uma treliça não passa por dentro da outra (barra a barra); a terça não corre dentro
  de painel ou transição; a treliça deitada termina na face da outra.
- **Aprovada:** 12/10. **Aplica-se a:** todo modelo.
- **Conferência:** **parcial** (rebaixada em 22/10) — `choques` olha o eixo (40 mm) e pula as barras paralelas (fora os
  cruzamentos normais: X do contraventamento, corrente, nó no pilar). Por isso não pegou os 2 Ue da VM caixa um dentro
  do outro, nem degraus, steel deck e postes sobrepostos no SESI. **Reforçada em 29/10 (a2e78bc):** viga × viga pela altura da seção,
  longe das pontas. **Falta:** barra × chapa (a castanha na CB1, Hangar), aço × ARQ (airbrises do SESI) e o resto pela seção real
  do catálogo, girada como a barra. O SESI já tem a conta (`Projeto/OBRAS/Sesi-Chapecó/leitura-3d/conferir_met.py`, 12 s
  para 577 mil pares) e ela vai para `conferencia_3d`.
- **Código:** `nucleo3d/encaixe_pela_secao.py` (eixo_pelo_contorno, correntes_ate_a_alma), `de_planta._assentar_tercas`.
- **Testes:** test_choque_entre_pecas_mas_nao_o_cruzamento_normal, test_encaixe_pela_secao.
- **Histórico:**
  - 22/10 SESI Chapecó — a leitura dava o eixo no meio do contorno e o 3D punha o centroide no eixo: a VM caixa com os 2 Ue
    22–30 mm um dentro do outro (93 pares), terças no ar, correntes antes da terça — 6b22115 (código comum). **Reincidência**
    (a regra B4/C6 é de 12/10; a conferência não pegou). Degraus, steel deck e postes sobrepostos: **abertos**, esperam o usuário.

### GER-03 — Nenhuma ponta solta
- **Enunciado (12/10):** nenhuma ponta de barra longe de qualquer peça (a terça em balanço, a treliça que não chega, a alma pendurada).
- **Aprovada:** 12/10. **Aplica-se a:** todo modelo.
- **Conferência:** **parcial** — `pontas_soltas` (250 mm; 150 mm de sólido), barra por barra, e desde 22/10
  `pecas_voando` (9f2c42c, pelo Hangar): o grupo de barras ligadas só entre si, longe de tudo (fora o maior e o que chega
  no chão), com grade 3D e sólido simples pela caixa (Hangar 0,8 s, Posto V2 7,8 s, SESI 4,2 s). Roda também no Montar pela
  Montagem (gerar_no_projeto). Desde 02/11 (60878fe) também `pecas_sem_encosto`, pelas faces (raio das seções + 15 mm), que pega a peça a centímetros.
- **Testes:** test_ponta_solta_mas_nao_a_que_encosta_no_banzo_curvo, test_reanalise,
  test_conferencia_3d::test_peca_voando_pega_o_grupo_que_so_encosta_nele_mesmo, test_hangar_v12::test_chapa_da_vc_e_castanha_no_3d.
- **Histórico:**
  - 19/10 CD Bom Dia — tocos soltos e diagonais penduradas — 934dbd0.
  - 21/10 Posto V2 — "peças voando": a diagonal do painel vizinho entrando como alma; a meia diagonal solta a ~9 cm da
    diagonal que trava — ad76db2. **Reincidência.**
  - 22/10 Hangar Almayer V12 — 64 castanhas CA1 a z 9.985, 5 m acima do banzo (a altura da seção somada duas vezes); a
    castanha e a aba encostavam uma na outra e as `pontas_soltas` não viam — 9f2c42c (gerador + conferência reforçada).
    **Reincidência.**

### GER-04 — O 3D modelado do DXF fica vinculado ao 2D
- **Enunciado (usuário, 26/10):** "todas as vezes que montarmos um projeto modelando ele em 3D a partir de projetos dxf,
  os projetos dxf utilizados devem ser importados para 2D e o modelo em 3D deve ser vinculado ao 2D para facilitar a
  verificação do 2D com 3D". Inclui a regra de 23/10 (memória dxf-junto-do-ifc-no-original): a obra com DXF e IFC também
  leva o DXF para o Original.
- **Aprovada:** 26/10 (o usuário, direto no REGRAS · SISTEMA).
- **Aplica-se a:** projeto que veio de DXF (o DXF recebido, o arquitetônico em DXF ou a peça montada pela planta). O
  projeto só do IFC não entra.
- **Código:** o vínculo é o `planta_modelo` do projeto (o desenho 2D com o DXF, o deslocamento do 3D e o de cada planta
  lida), que a tela dividida lê (web/dividida.js). Quem grava: a montagem pela planta (app.py) e por quadros, sozinhas; o
  script de obra, por `nucleo3d/vinculo_2d.gravar`. **O outro jeito de ligar:** cada peça com a chave do traço do desenho
  (`atributos.origem_2d`, como a Montagem e a planta de lançamento fazem; o cad.js e o ver3d.js fazem a ida e volta por ela).
  Vale com 80 % das barras ligadas.
- **Conferência:** **sim** — `nucleo3d/vinculo_2d.conferir(pasta do projeto)`. Aponta:
  - o DXF não está no 2D ou o 3D não está ligado a ele: sem `planta_modelo` e sem a chave do traço em 80 % das barras, ou o
    desenho do vínculo sem nada do DXF;
  - falta o deslocamento;
  - peça de uma planta que o vínculo não conhece;
  - **o 3D não cai em cima do desenho**: mais de 12 % das barras, levadas ao 2D, longe de qualquer traço (meio e duas
    pontas, grade de 250 mm). Com o vínculo certo ficam até ~8 % (Posto V2 2,7 %); com o 3D 1 m fora, 16–28 %; com 5 m, mais de 50 %.
- **Reforçada em 29/10 (510fb67):** também planta por planta (> 25 % das barras de uma planta, com ≥ 30, longe do traço); a
  borda da hachura conta como traço. **Falta:** a peça e a vista certas (a prova por vetores do SESI e o
  pente_fino_vinculo.py do Galpão Novo) e a remontagem rodar a conferência no fim.
- **Testes:** test_vinculo_2d (8 casos e a trava: as obras do desenvolvimento não pioram em relação a
  `Projeto/bateria/vinculo-2d.json`, aceita em 26/10).
- **Situação em 26/10 (33 obras do dev):**
  - 8 ligadas: Posto V2, Hora Certa Edifício Administrativo, Portaria e o Posto teste, pelo `planta_modelo`; Hangar (93 %),
    Ortobio, CD Bom Dia e Docas (92 %), pela chave.
  - **5 vieram do DXF sem vínculo nenhum:** Hora Certa galpão novo e existente, Moinho Globo, PRATI metálica e sem
    lateral. Em todas, o DXF já está no 2D. A correção é de cada chat de obra.
  - A 1ª versão da conferência (a6cc391) só conhecia o `planta_modelo` e acusava também as 4 ligadas pela chave.
  - 26/10, depois: resolvidos o Hora Certa galpão existente (o script da obra grava os dois jeitos), o Moinho Globo e
    o Hora Certa galpão novo. No galpão novo (9685e2d), a planta girada no desenho: `fontes[planta]` aceita
    `{deslocamento, giro}`, no dividida.js e no vinculo_2d.py, com teste de giro certo, trocado e sem giro. Seguem sem
    vínculo: PRATI metálica e sem lateral.

### GER-06 — A peça é como o projetista a desenha
- **Enunciado (usuário, 22/10, memória seguir-o-projeto):** "a concepção do projetista primeiro (os encontros como a planta),
  a execução depois". A peça chega onde a planta a desenha, com a altura, a medida e o tipo que o desenho cota. Exceção da
  TES-4.8: no encontro quase tangente (< 30°) a peça segue a planta e não para na face.
- **Aprovada:** 22/10 (decisão do usuário; princípio PRI-01). **Aplica-se a:** todo modelo montado de desenho.
- **Código:** `de_planta.aparar_nas_faces` (TANGENTE_ATE 30°), `ancorar_pelas_chegadas`, `bases_locacao` (a medida do detalhe).
- **Conferência:** **não**. Propostas: ponta do 3D × ponta da planta > 50 mm; chegadas × montantes da elevação > 30 mm; a chapa
  do 3D × o DET. do CHn; o tipo da peça × o rótulo ou a hachura; o apoio fora da linha das vizinhas (rampa).
- **Testes:** test_de_planta::test_encontro_quase_tangente_segue_a_planta e os 12 de 22/10 (79788b6, 0d06d01, 86132d9).
- **Histórico:** 22/10 Posto V2 — a curva do PAINEL 9 parando na face do PAINEL 12, vão de 0,42 m — 8848154 (a 1ª); 22/10
  Posto V2 — as referências dos elementos errados — 79788b6, 0d06d01, 86132d9. Depois: ver "Triagem de 22/10 a 04/11".

### GER-07 — O Original traz as pranchas do projetista como foram emitidas
- **Enunciado (usuário, 27/10):** "no original precisam aparecer todas as pranchas originais do projetista, para que eu
  consiga conferir com o que ele projetou… isso é regra para todas as importações desse tipo" — com o carimbo, as tabelas e
  as notas. Os leitores do Original ignoram as folhas (não viram peça de novo).
- **Aprovada:** 27/10 (Hora Certa · Galpão Novo). **Aplica-se a:** projeto recebido, em DXF ou PDF.
- **Código:** `nucleo2d/folhas_papel.py` (o espaço do papel do DXF como sai na impressão, 8cd53e9); `de_planta.montar` ignora
  a origem "dxf-papel" (c8b1a4a).
- **Conferência:** **sim** — `vinculo_2d.tem_o_original` (9265545): projeto recebido sem traço do projeto na planta de lançamento aponta.
- **Testes:** test_folhas_papel, test_vinculo_2d::test_projeto_recebido_do_pdf_sem_o_original_aponta,
  test_de_planta::test_folhas_do_projetista_no_original_nao_sao_lidas_como_projeto.
- **Histórico:** 27/10 Galpão Novo (a 1ª, no script da obra); 03/11 WE Coqueiral — **reincidência**.

### GER-08 — Tudo o que o desenho mostra vira peça ou apontamento
- **Enunciado:** a conferência do PRI-01 ("o que não encaixa vira apontamento"). Toda peça desenhada, todo texto "PILAR nn",
  todo rótulo de perfil ("CV. L…", "2U…"), toda borda de viga, toda nota e toda linha dos quadros RESUMO/TABELA do projetista
  vira peça no 3D ou premissa/apontamento declarado.
- **Aprovada:** 26/09 (PRI-01). **Aplica-se a:** todo projeto recebido.
- **Código:** cada leitor (de_planta, leituras por script). **Conferência:** **não**. Proposta (auditor, 30/10): ler as notas e
  os quadros RESUMO das folhas e exigir uma peça ou uma premissa para cada perfil/nota ("PLATIMBA", "GANCHO", "DIAGONAL"…); o
  chumbador com gancho no detalhe pesa pelo desenvolvido.
- **Histórico:** ver "Triagem de 22/10 a 04/11" (4 reincidências, todas no script da obra).

---

## FAB — Fábrica, detalhamento e compra

Regras aprovadas; a conferência de cada uma ainda está por levantar (etapa seguinte do catálogo).

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| FAB-01 | Furação das terças e de tudo da ligação delas: 50 × 60 até 200 mm, 100 × 60 acima; oblongo 25 × 13; **o padrão da máquina vence o projeto** (também no IFC recebido) | 22/09 (30/09, 02/10, 16/10) | `_padronizar_3d` (app.py), `regra_furacao_terca` | R6 recusa o PDF "fora_da_maquina"; test_regressoes_primeiro_uso_ifc |
| FAB-02 | Furo cotado pelo projetista vale; sem cota, d + 1,5 mm no mínimo | 15/10 | saida/detalhamento.py `FOLGA_MINIMA_FURO` | aviso "< 1,5" no detalhe; TestFolgaNaPranchaDoProjetoRecebido |
| FAB-03 | Peso do dobrado: (soma externa − 2t por dobra) × t × 8 kg/m² por mm | 14/10 | saida/dobras.py, nucleo/catalogo.py | **sim** desde 30/10: test_dobras.py + test_massa_formados_catalogo.py (o catálogo inteiro; o nome que o leitor não entende falha) |
| FAB-04 | Barra não se dobra: curva = calandrada ou trechos retos | 06/10 | catalogo, resumos | — |
| FAB-05 | Porcas: projeto recebido segue o projetista; nosso: parafuso 1 porca + 2 arruelas, chumbador 1 arruela + 2 porcas | 16/10 | lista de materiais | TestParafusosEPorcasNaLista, TestSegundaRodadaDaCamila::test_r05 |
| FAB-06 | Nomes CT.n (cantoneira furada), MT.n (meia-tesoura); parafuso métrico × polegada por projeto | 16/10 | nucleo2d/detalhe/base.py, nomes.py | TestNomesDecididosPeloUsuario |
| FAB-07 | 3D → detalhe → prancha (R1–R6): o 3D é a peça; regra de fábrica vai para o 3D; peça travada na prancha; PDF recusado com desenho velho | 02/10 | app.py `_padronizar_3d`, `_conferir_para_emitir`, web/cad/trava_pecas.js | R6 |
| FAB-08 | Chumbador mecânico (Hardbolt, Parabolt) não leva químico nem porca solta | 14/10 (Hardbolt, PRATI) | saida/resumos.py (`_eh_parabolt`, Hardbolt) | não; test_hardbolt_sai_como_hardbolt_e_nao_como_quimico, test_parabolt. Histórico: 24/10 Parabolt — **reincidência** |
| FAB-10 | Nomes do catálogo: polegada `1.1/4"`, espessura com 2 casas, W com a massa em 1 casa, telha = modelo + espessura + fabricante curto; o nome antigo gravado continua valendo | 27/10 (usuário, entre exemplos) | nucleo/nomes_catalogo.py | **sim**: test_nomes_catalogo (o catálogo inteiro) |
| FAB-11 | Barra redonda maior que a barra comercial vem sob medida, sem emenda no plano de corte | 30/10 (usuário, Galpão Existente) | saida/lista_producao._regra_sob_medida | não; test_redondo_sob_medida |

## PRI — Princípios (valem em toda regra)

| Código | Princípio | Aprovado |
|---|---|---|
| PRI-01 | Seguir o projeto: montar como o projetista desenhou; o que não encaixa vira apontamento | 26/09 |
| PRI-02 | Pensar na execução: "Como será executado? É possível executar dessa forma?" antes de lançar peça ou fixação | 14/10 |
| PRI-03 | A telha manda: conferir de cima para baixo (telha → terças → treliças); o que a estrutura não deixa acertar vai ao projetista (G2) | 12/10 |
| PRI-04 | Corrigir a regra, não a obra: todo gerador e todo script de obra passa pela regra (`regras_trelica.aplicar`, `telhas_cobertura`) | 12/10, 16/10, 21/10 |

## TEL — Telas (o comportamento da interface)

Regras de tela aprovadas. A conferência é o verificador (Chrome sem janela, eventos de verdade). Uma correção no código
comum (progresso.js, cad.js, editor.js, sistemas.js) vale para todas as telas que o usam.

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| TEL-01 | Toda tarefa demorada mostra a barra de andamento, com a etapa e a estimativa, **numa linha só e sem repetir o texto do aviso** | 16/10 (CLAUDE.md); a linha só, 21/10 | web/progresso.js (instalado pelo vivo.js), `_progresso` no servidor | **parcial**: verif_ver3d_atualizando (só o modo ver). Histórico: 21/10 Sesi Chapecó, a barra do "Atualizando o 3D" e o aviso em duas linhas, com o texto repetido — 4d633bc (1ª correção) |
| TEL-02 | Toda peça cai num sistema do modo ver e do celular cujo nome diz o que ela é: primeiro o nome da peça, depois a camada e o grupo, por último o material. **Outros só com motivo conhecido**, com o motivo no nome ("Outros — PVC"; PVC, neoprene, borracha, madeira, argamassa, tela, vidro). O material que ninguém reconhece vai para **"Sem material — a definir"**. Material só com a cor ("Cor #…") ou automático ("<auto>") é como sem material: Metálica. Armadura (e o aço CA-50/60 que não é chapa) é Pré-moldado | 22/10 (usuário, pelo GESTÃO, depois de 4 correções no mesmo dia; os 3 exemplos em `Projeto/ANALISES/Interface/TEL-02-sistemas-do-modo-ver-proposta-2026-10-22.pdf`) | web/visor3d/sistemas.js (`gruposDeSistema`, `conferirSistemas`), o mesmo no modo ver e no celular | **sim**: `conferirSistemas` (sem material, cobertura fora da Cobertura, ARQ fora do Arquitetônico, perfil de aço em Outros); test_sistemas_modo_ver (os 3 exemplos e a trava: as obras do desenvolvimento não pioram em relação a `Projeto/bateria/sistemas-modo-ver.json`); verif_ver3d_sistema. Histórico: 22/10 SESI e156c93 (1ª), c39a8b1, e014461, 8aa0515 (**3 reincidências**); 22/10 a regra virou conferência (este commit): 1.010–1.292 parafusos do Sooro, os furos do Hangar e do PRATI e 15 peças do Capitão para a Metálica, 1.876 armaduras e 534 pinos CA-50 do Ortobio para o Pré-moldado, as 3.146 peças da Vicente e 127 do Bellacasa em "Sem material — a definir" |
| TEL-05 | O chão do terreno é feito de planos (contorno + cota): Plano / Inclinado / Plano, o degrau em pé em cor neutra, longe da obra volta ao plano; sem planos, o plano de sempre. Todo lote tem chão em todo ponto | 03/11 (usuário, caso (b); simplificado no mesmo dia, c22fc2f) | web/visor3d/chao.js, terreno.js; saida/local_obra.niveis_do_chao | test_chao_em_niveis, verif_ver3d_terreno_niveis |

---

## LIG — Ligações

Padrões de ligação aprovados com exemplos. O tipo se troca por nó (tela /ligacoes). Prefixo aberto em 04/11 (GESTÃO avisado).

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| LIG-01 | Contravento × viga, uma ligação por nó, três variantes que se trocam: A castanha (CA1 do Hangar), B duas chapas (Sooro), C cantoneira cortada (SC1) | 23/10 (usuário: "1. Sim 2. Pode ser 3. Sim", Projeto/ESTUDOS/Ligações/exemplos/contravento_{A,B,C}_*.png) | nucleo3d/ligacoes3d.py (FAMILIAS) | colisão nos 3 tipos: test_ligacoes_contravento, verif_ligacoes_trocar_tipo |
| LIG-02 | Ligação "chapa simples" (viga na viga do heliponto: chapa 8 × 90 na alma do apoio, 5 M16 a 45 da face, borda 29, viga 10 mm antes, cope com 10 de folga) — padrão que se escolhe por obra | 23/10 (3 casos, Projeto/OBRAS/Heliponto/ligacoes-v2/1-casos-viga-na-viga.png) | nucleo3d/ligacoes3d.py (`chapa_simples`) | test_ligacoes3d::test_chapa_simples_* |
| LIG-03 | Contravento horizontal em cantoneira ("CV. L…" na planta de nível) embaixo do banzo de baixo, de nó a nó, aba deitada no fundo dele; no X uma passa inteira e a outra logo abaixo (calço nas pontas); a ponta que chega numa VM para na face dela | 26/10 (usuário, caso A, Posto-CB/lista-do-projetista/exemplos-cv) | de_planta.contraventos_em_cantoneira | não (pela GER-08 e GER-02); test_de_planta::test_contravento_em_cantoneira_embaixo_do_banzo_e_cruzando_no_x |

## DET — Desenho e pranchas

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| DET-02 | Revisões: a tabela inteira em cima do carimbo (2 mm acima, a mais nova em cima, começa em "00 — EMISSÃO INICIAL", o REV. do carimbo = a última); nuvem com o △ do número; o diálogo "Revisões das pranchas…" marca as pranchas | 24/10 (usuário, opção A) | nucleo2d/revisoes.py, web/cad/revisoes.js | não (proposta: nenhuma prancha emitida com a tabela sobre um detalhe); test_revisoes, verif_cad_revisoes |
| DET-03 | Cota em mm inteiro (decimal só escolhido à mão; ângulo com uma casa); na dúvida entre dois, o MAIOR ("é mais fácil ele cortar um pedacinho do que faltar"); metades espelhadas com o mesmo número | 26/10 (T1 da Sala, Sooro); o maior e as metades, 30/10 | desenho.py formatar_cota, desenho2d.js, conjuntos.metades_espelhadas_iguais | não; test_cota_mm_inteiro, test_cotas_pranchas. Pendência: as metades só na tesoura montada (faltam pórticos e vigas) |
| DET-04 | Pranchas da tesoura (o ajuste do usuário na T1 da Sala): texto de cotas e chamadas 5 mm (furos 2,0); o vão dividido ao meio por um nó leva uma cota só; chamada das chapas em toda ocorrência até 4; a cadeia de baixo até o centro geométrico, a da cumeeira pelas faces das chapas de união; cada perfil do banzo com a sua cor | 26/10 ("sim"; muda o pedido de 28/09 das faces das metades); a cor, 30/10 | nucleo2d/detalhe/base.py, celulas.py, conjuntos.py | não; test_cotas_pranchas |
| DET-06 | A frente fora da malha ganha eixos locais nossos (a conferir com o projetista), uma planta de chumbação por malha; toda base desenhada tem linha de locação a um eixo | 30/10 (usuário, Galpão Existente) | nucleo3d/eixos (malhas), detalhe/conjuntos (_locacao_dos_chumbadores) | não (proposta: nenhuma locação a mais de 15 m de um eixo); test_malhas_locais |

## COM — Proposta e orçamento

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| COM-01 | A proposta não entrega o estudo: cargas de norma, geometria, só o TIPO do perfil (W, U), peso estimado; nada de bitola ou lista copiável | 27/10 (usuário; memória proposta-nao-entrega-o-estudo) | saida/comercial.py (`PERFIL_ESPECIFICO`, `avisos_proposta`) | **sim**: a medida de perfil vira aviso; test_proposta_empresas |
| COM-02 | Orçamento: o projeto (desenho) vale sobre a lista; na dúvida, a MAIOR medida; chumbador por unidade (fora do kg); guarda-corpo fora (adendo com a quantidade); calha só a metragem | 03/11 (usuário; memória regras-de-orcamento) | **só no relatório da obra** (relatorio_quantitativos.py) — pendência de gerador (FERRAMENTA · ORÇAMENTO) | não |
| COM-03 | Orçamento: chapa = a comercial MAIS PRÓXIMA em mm e polegada, mesmo menor, kg pela comercial (CH 15 → "CH 16 - 5/8"", CH 20 → "CH 19,1 - 3/4"", empate → a maior); chumbador de barra redonda com o comprimento total ("Ø12 - 1/2" x 230 x 60 pç = 13,8 m"); disco em branco (o gestor); tinta só a área de pintura (m²), a especial à parte | 05/11 (usuário, pelo gestor) | saida/orcamento.py (`CHAPAS_GROSSAS`, `chapa_do_orcamento`, `_RE_CHUMB_BARRA`, linha tinta) — aba Orçamento | não; test_orcamento_regras_0511 |

## ARQ — Arquitetura (módulo só no dev)

Família pedida pelo FERRAMENTA · ARQUITETURA; regras aprovadas pelo usuário em 30/10 ("pode seguir com as recomendações"), exemplos
em `Projeto/ANALISES/Arquitetura/Prova-fase-1-arquitetura-2026-10-30.pdf`. Código: `sistema/arquitetura/paredes.py`; teste:
test_arquitetura_paredes (14). ARQ-05 a 07 vêm na fase 2.

| Código | Regra |
|---|---|
| ARQ-01 | A parede é desenhada pelo eixo e tem um tipo com camadas: externa 20 (reboco 3 + bloco 14 + reboco 3), interna 15 (3 + 9 + 3) |
| ARQ-02 | Nas uniões L/T/X o bloco se amarra (núcleo contínuo) e o reboco contorna; na T e na X passa a parede mais grossa (empate: a desenhada primeiro) |
| ARQ-03 | A base fica no nível e o topo no fundo da laje de cima |
| ARQ-04 | A esquadria abre o vão sozinha; janela pelo vão acabado, osso +3 cm por lado e em cima; porta pela folha, osso folha +10 × folha +5 |
| ARQ-05 | Planta cortada a 1,20 m (NBR 6492), penas 0,50/0,25/0,15/0,13; alvenaria cortada hachurada; abaixo em vista, acima tracejado |
| ARQ-06 | Etiqueta do ambiente: nome, área pelas faces internas e piso; cotas em metro com 2 casas e traço a 45° |
| ARQ-07 | Pranchas para a prefeitura de Cascavel (art. 6º e 7º: espaço de 17,5 × 6 cm), com o carimbo da DEZN |

---

## Propostas — esperando o "aprovada" do usuário

| Código | Enunciado proposto | De onde veio |
|---|---|---|
| COB-01 | A cobertura não tem fresta nem buraco | plano de 21/10; Posto V2 (8bedaa1, 8e9ac8c, 52 buracos / 43 frestas) |
| COB-02 (ampliação) | Nada atravessa a telha, a calha ou o rufo (também a treliça × calha e a barra × pano de telha) | plano de 21/10; Posto V2 (calhas cortadas) |
| COB-03 | A telha vai até a parede, seja qual for a forma da borda | plano de 21/10; 4 correções (a2d716a, 8bedaa1, 8e9ac8c, 3391273) |
| COB-14 | A telha é uma chapa por faixa, com o recorte junto | 3391273 (paginação da folha 12 do Posto V2) |
| COB-16 | Treliça acima da telha no meio do telhado é revestida e rufada | a2d716a (corte BB do Posto) |
| TEL-03 | A janela de seleção do CAD 2D e do 3D funciona como no AutoCAD: o pan funciona durante o arrasto, a tela anda com o cursor na borda e o Alt+Tab no meio solta a janela | 00fd082 (Vicente Residence, 22/10); verif_cad_janela, verif_selecao_janela_3d |
| TEL-04 | O modo ver e o celular mostram a peça como ela é: o furo aberto (o editor também) e o vidro transparente, como no editor | e369076 (Sesi, 22/10: o vidro opaco do arquitetônico escondia os brises); 37623de (ME Sooro, 22/10: 10 furos das terças do IFC tampados no modo ver e no celular; o editor, cena.js, tampa os mesmos e ficou com o EDITOR 3D). Proposta de conferência do modelo inteiro: nenhum furo de face costurada coberto por triângulo no .mcel (a conta de test_face_costurada._cobre); verif_ver3d_vidro, test_face_costurada |
| COB-01 (ampliação) | …nem chapa sobre chapa: duas telhas de direções diferentes não se cobrem além do cobrimento na terça | 7cf6e1d (Posto V2, 22/10: no canto da oval com a parede reta, chapas de duas direções uma sobre a outra — efeito das correções de encontro de 21/10). Conferência proposta: `Projeto/OBRAS/Posto-CB/leitura-3d/sobreposicao.py` (pares de direções diferentes que se cobrem > 0,005 m² em planta; Posto V2 0,77 → 0,31 m², 24 pares que sobram, quase todos o cobrimento de 50–100 mm) |
| TES-2.9b | A terça de fim de curso (sem outra terça do outro lado) sobre banzo de perfil duplo vai até a face de fora do último perfil, apoiada nos dois. Na emenda, cada terça vai até o meio (fica). No banzo de perfil único, para no eixo (a confirmar) | usuário, 26/10, print do Ortobio. Exemplos: `Projeto/ANALISES/Montagem/Terca-fim-de-curso-banzo-duplo-exemplos-2026-10-26.pdf`. Hoje, nas obras do dev: Ortobio 58 terças curtas (+114, +125 e +250 mm), Mercado 4, Posto teste 1. Precedente: Hangar 22/10 ("a terça vai até a face de fora da tesoura", de_planta_estrutura), que só valia com o suporte lançado e ficou só no REGRESSOES — **a mesma ideia voltando** |
| DET-01 | Planta de localização e chumbação por pavimento (o modo prédio) só em prédio de aço: chumbador em 3 pavimentos ou mais. Senão, a planta do galpão | 1725e84 (bateria da 0.9.1, 22/10: o modo prédio da Vicente entrou no Capitão pré-moldado, 17 plantas "IFCBEAM"); test_predio |
| GER-05 | O perfil composto desenhado (2U/2Ue/2L) sai composto; o rótulo da peça vale mais que a camada. Conferência: texto 2U/2Ue/2L do desenho × peça simples; barra com "2×"/composicao no atributo e um perfil só | f22b561 (Posto, 22/10: o pilar 2U em 1 U); 28/10 Galpão Novo (32 t a menos na lista, TES-2.9) |
| GER-09 | A peça é inteira como no desenho: o banzo não sai picado por painel. Conferência: trechos colineares seguidos da mesma peça | 27/10 Galpão Novo (só no script da obra) |
| GER-10 | A peça e a chapa se posicionam pelo contorno da seção, não pelo centro de gravidade (U, Ue, L) | 6b22115 (SESI, 22/10: a VM caixa) e 51545e6 (SESI, 28/10: 41 bases a 12,9 mm) — **2 vezes** |
| GER-11 | Peça fixada no concreto encosta na face dele: nem dentro nem no ar, e o concreto está no 3D | 03/11 SESI (airbrises dentro das paredes e depois voando: a viga de borda faltava) |
| TES-2.8b | A caixa de 2 U/Ue é boca com boca (hoje a 2.8 deixa a caixa fora da regra) | 27/10 SESI (os postes da TS6 com os dois Ue para o mesmo lado) — com exemplos |
| TES-3.2a | **Decisão do usuário:** a alma entre banzos em par tem comprimento de corte até a face de fora (o nó continua no eixo) | 28/10 Galpão Novo: a alma 3,6 t curta (22,0 → 25,6 t, +17 %) |
| DET-05 | Treliça plana em linha não sai como tesoura montada; só a de duas águas sai montada | d2fd713 (29/10) e 941fa4e (30/10), Galpão Existente — **2 vezes** |
| FAB-09 | O que se compra por m² (telha, chapa expandida) pesa pela massa por m² do fabricante e não vai para o plano de corte | 24/10 Posto (a chapa expandida pesando 4,3 t) |
| TEL-01 (ampliação) | O fim da tarefa diz onde ela parou e sai sozinho ou tem ×; a tarefa segue quando o usuário sai da tela e a tela de volta mostra o andamento; nada se sobrepõe ao rodapé, também na tela dividida | 8bbdef0 (22/10), db64dab (27/10), 37da918 (27/10), 03/11 (a marca d'água) |
| TEL-06 | Abrir um modelo de qualquer tamanho não trava a tela: acima de 6.000 peças a montagem é em partes com andamento, e o resultado é o mesmo | f3eaed8 (SESI, 03/11); verif_editor_modelo_grande |
| TEL-07 | O que o servidor refaz sozinho depois de gravar (3D leve, desenhos, pranchas) roda em segundo plano, depois de meio minuto de sossego; o usuário passa na frente | b8aeebc (SESI, 03/11) |
| COB-18 | O capa fica centrado no topo da parede que é o apoio dele (alvenaria ou concreto, nunca revestimento); na platibanda cobre a telha interna e o ACM; parede corrida = capa reto; pilar acima = o capa termina nele | 30/10, 03/11 (duas vezes) SESI — só no script da obra |
| ARQ-08 | A escada confortável: 63 ≤ 2e + p ≤ 64 cm (Blondel) e o patamar com pelo menos a largura do lance | e4e98f3 (casa alto padrão, 02/11); hoje só avisa |

## Pendências de gerador (correção que mora só no script da obra)

- COB-17: a parede de concreto entra como parede provisória no script de cada obra — o `telhas_cobertura` só vê barras.
- As telhas de toda obra são lançadas por script (`Projeto/OBRAS/<obra>/…`), sem botão na tela.
- GER-04: a camada "3D — Peças em planta" no Original, com a chave `origem_2d` em cada peça (o jeito da chave, para a obra
  lida de PDF ou montada por script), mora em cópias por obra: `Projeto/OBRAS/Sesi-Chapecó/leitura-3d/vinculo_2d.py` e
  `Projeto/OBRAS/Hora-Certa/Galpão Existente/leitura-3d/vinculo_planta.py` e `Projeto/OBRAS/Moinho-Globo/ligar_2d.py` (a chave do traço da vista de cada barra, porque o DXF do Moinho só tem elevações e cortes). Deve ir para o código comum (pedido ao
  FERRAMENTA · LEITURA DXF/IFC → 3D).
- **Leituras por script sem gerador comum** (de onde vieram 34 das 150 linhas de 22/10 a 04/11):
  - SESI: a leitura por subagente (pilaretes, suportes de terça, quadros da frontal, `fechar_nos.py`, rufos e capas em
    `telhas_sesi.py`, airbrises);
  - Edifício Administrativo e Galpão Existente: a planta a duas linhas (`vigas_por_pares.py`) e o pilar fora da camada;
  - Galpão Novo: a elevação no trecho dela, o par ]-[ e as notas dos quadros RESUMO.

  O `fechar_nos.py` e os critérios de rufo do SESI são os candidatos mais fortes ao código comum (GER-03, COB-12/13/18).
- `regras_trelica.aplicar` deixa barra de comprimento zero (o montante de ponta mais curto que o banzo; Residencial Madrid,
  04/11). Foi contornado no script da obra. Pedido ao dono das tesouras: não deixar peça nula, com teste.
- "A viga de menor hierarquia é partida no cruzamento": só em `nos_das_vigas.py` do ADM (29/10).
- COB-11: a calha em 0,65 mm (usuário, 03/11) ainda não está no `telhas_cobertura`.
- COM-02: as regras de orçamento estão só no relatório da obra.
- GER-07: resolvida no código comum (`folhas_papel.py`, 8cd53e9); a leitura das folhas em PDF segue por script nas obras.
