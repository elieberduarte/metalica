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
Triagem inicial de 21/10 (REGRESSOES.md + git log desde 12/10).

| Regra | Reincidências | Conferência | Última |
|---|---|---|---|
| COB-03 telha até a parede | 4 (+ a 1ª correção) | parcial | 21/10 c8f1e1f |
| COB-01 sem fresta nem buraco | 3 | sim | 21/10 c8f1e1f (Posto V2, 53 buracos e 43 frestas) |
| TES-3.1 nada atravessa o banzo | 2 | sim | 19/10 22c229a |
| GER-01 cada barra uma vez só | 2 | parcial | 21/10 ad76db2 |
| TES-2.2 banzos abrem para dentro | 2 | sim | 21/10 8421ab5 |
| TES-2.9 banzo 2U composto | 1 | sim | 21/10 1188b4c |
| COB-02 nada atravessa telha, calha e rufo | 1 | parcial | 21/10 c8f1e1f (calhas cortadas na treliça) |
| COB-04 cada água é um plano | 1 | sim | 21/10 8bedaa1 |
| COB-12 o rufo segue a telha | 1 | **não** | 19/10 b886cb9 |
| COB-13 peças inteiriças | 1 | **não** | 19/10 b886cb9 |
| GER-03 nenhuma ponta solta | 1 | parcial | 21/10 ad76db2 |

---

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
  cumeeira e vale não contam).
- **Testes:** test_agua_reta_de_5_por_cento, test_terca_erguida_no_meio_da_agua, test_terca_da_calha_sobe_ao_plano_com_suporte,
  test_terca_torta_fica_nivelada_no_apoio, test_telha_ao_lado_aponta_o_degrau_e_a_dobra, test_linha_da_calha_emendada_sobe_inteira,
  test_linha_emendada_nao_sobe_para_dentro_de_outra_peca, test_chapa_reta_por_cima_da_terca_fora_da_reta,
  test_conferencia_3d::test_telha_ao_lado_e_os_avisos.
- **Histórico:**
  - 17/10 Posto CB — degrau de 133 mm na calha x 34,06 (a ponta da linha subia sozinha ao plano) — a2d716a.
  - 21/10 Posto V2 — "trecho caído/levantado": a terça fora da reta partia a chapa — 8bedaa1. **Reincidência** (a
    conferência acusava a dobra; o gerador seguia a terça em vez de passar reto).

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
| TES-2.3 | Alma abre para o meio do vão; "a diagonal nunca para cima"; montante do meio para a ponta alta | 16/10 | **sim** | test_2_3_alma_abre_para_o_meio_e_diagonal_nunca_para_cima, test_2_3_montante_no_meio_abre_para_a_ponta_alta |
| TES-2.4 | Cantoneira simples = "um U cortado ao meio" (aba de pé sempre +n) | 16/10 | **sim** | test_2_4_cantoneira_simples_e_um_u_cortado_ao_meio |
| TES-2.5 | Cantoneira em par = um U partido (abas de pé para o centro), par coincidente ≤ 40 mm | 16/10 (≤ 40 mm: 21/10) | **sim** | test_2_5_cantoneira_em_par_e_um_u_partido |
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
- **Conferência:** **parcial** — `repetidas` (as mesmas pontas a 15 mm). Não pega a peça dobrada deslocada (o montante
  visto de lado a 11 cm do verdadeiro, no Posto V2).
- **Testes:** test_repetida_pega_as_mesmas_pontas_em_qualquer_sentido, test_3_3_presilha_dobrada_aparece_e_sai.
- **Histórico:**
  - 19/10 CD Bom Dia — montantes repetidos (modelo antigo) — 934dbd0 (Reanalisar).
  - 21/10 Posto CB — duas presilhas na mesma altura (uma 6,4 mm fora) — 0af6b75. **Reincidência.**
  - 21/10 Posto V2 — o montante da tesoura que chega, visto de lado, entrava como montante da transição a 11 cm do
    montante 2L (21 peças duplicadas) — ad76db2. **Reincidência** (a conferência não pegou: 11 cm > 15 mm).

### GER-02 — Nada atravessa outra peça
- **Enunciado (B4, B9, C6, 12/10):** uma treliça não passa por dentro da outra (barra a barra); a terça não corre dentro
  de painel ou transição; a treliça deitada termina na face da outra.
- **Aprovada:** 12/10. **Aplica-se a:** todo modelo.
- **Conferência:** **sim** — `choques` (fora os cruzamentos normais: X do contraventamento, corrente, nó no pilar).
- **Testes:** test_choque_entre_pecas_mas_nao_o_cruzamento_normal.
- **Histórico:** (nenhuma reincidência registrada)

### GER-03 — Nenhuma ponta solta
- **Enunciado (12/10):** nenhuma ponta de barra longe de qualquer peça (a terça em balanço, a treliça que não chega, a alma pendurada).
- **Aprovada:** 12/10. **Aplica-se a:** todo modelo.
- **Conferência:** **parcial** — `pontas_soltas` (250 mm; 150 mm de sólido). Não pega a ponta a 9 cm da peça em que
  devia estar presa.
- **Testes:** test_ponta_solta_mas_nao_a_que_encosta_no_banzo_curvo, test_reanalise.
- **Histórico:**
  - 19/10 CD Bom Dia — tocos soltos e diagonais penduradas — 934dbd0.
  - 21/10 Posto V2 — "peças voando": a diagonal do painel vizinho entrando como alma; a meia diagonal solta a ~9 cm da
    diagonal que trava — ad76db2. **Reincidência.**

---

## FAB — Fábrica, detalhamento e compra

Regras aprovadas; a conferência de cada uma ainda está por levantar (etapa seguinte do catálogo).

| Código | Regra | Aprovada | Onde | Conferência / teste |
|---|---|---|---|---|
| FAB-01 | Furação das terças e de tudo da ligação delas: 50 × 60 até 200 mm, 100 × 60 acima; oblongo 25 × 13; **o padrão da máquina vence o projeto** (também no IFC recebido) | 22/09 (30/09, 02/10, 16/10) | `_padronizar_3d` (app.py), `regra_furacao_terca` | R6 recusa o PDF "fora_da_maquina"; test_regressoes_primeiro_uso_ifc |
| FAB-02 | Furo cotado pelo projetista vale; sem cota, d + 1,5 mm no mínimo | 15/10 | saida/detalhamento.py `FOLGA_MINIMA_FURO` | aviso "< 1,5" no detalhe; TestFolgaNaPranchaDoProjetoRecebido |
| FAB-03 | Peso do dobrado: (soma externa − 2t por dobra) × t × 8 kg/m² por mm | 14/10 | saida/dobras.py, nucleo/catalogo.py | test_dobras.py |
| FAB-04 | Barra não se dobra: curva = calandrada ou trechos retos | 06/10 | catalogo, resumos | — |
| FAB-05 | Porcas: projeto recebido segue o projetista; nosso: parafuso 1 porca + 2 arruelas, chumbador 1 arruela + 2 porcas | 16/10 | lista de materiais | TestParafusosEPorcasNaLista, TestSegundaRodadaDaCamila::test_r05 |
| FAB-06 | Nomes CT.n (cantoneira furada), MT.n (meia-tesoura); parafuso métrico × polegada por projeto | 16/10 | nucleo2d/detalhe/base.py, nomes.py | TestNomesDecididosPeloUsuario |
| FAB-07 | 3D → detalhe → prancha (R1–R6): o 3D é a peça; regra de fábrica vai para o 3D; peça travada na prancha; PDF recusado com desenho velho | 02/10 | app.py `_padronizar_3d`, `_conferir_para_emitir`, web/cad/trava_pecas.js | R6 |

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

---

## Propostas — esperando o "aprovada" do usuário

| Código | Enunciado proposto | De onde veio |
|---|---|---|
| COB-01 | A cobertura não tem fresta nem buraco | plano de 21/10; Posto V2 (8bedaa1, 8e9ac8c, 52 buracos / 43 frestas) |
| COB-02 (ampliação) | Nada atravessa a telha, a calha ou o rufo (também a treliça × calha e a barra × pano de telha) | plano de 21/10; Posto V2 (calhas cortadas) |
| COB-03 | A telha vai até a parede, seja qual for a forma da borda | plano de 21/10; 4 correções (a2d716a, 8bedaa1, 8e9ac8c, 3391273) |
| COB-14 | A telha é uma chapa por faixa, com o recorte junto | 3391273 (paginação da folha 12 do Posto V2) |
| COB-16 | Treliça acima da telha no meio do telhado é revestida e rufada | a2d716a (corte BB do Posto) |
| TEL-02 | No modo ver (e no celular), cada peça cai no sistema pelo que ela é (telha, tesoura, concreto…), não pelo nome do grupo: desligar um sistema esconde tudo dele e nada de outro | e156c93 (Sesi Chapecó, 22/10: as telhas do arquitetônico não sumiam com a Cobertura; a Cobertura escondia as tesouras dos grupos "Cobertura…"); c39a8b1 (22/10, 2ª correção em poucas horas: a platibanda em ACM do arquitetônico não saía com a Cobertura); verif_ver3d_sistema |
| TEL-03 | A janela de seleção do CAD 2D e do 3D funciona como no AutoCAD: o pan funciona durante o arrasto, a tela anda com o cursor na borda e o Alt+Tab no meio solta a janela | 00fd082 (Vicente Residence, 22/10); verif_cad_janela, verif_selecao_janela_3d |
| DET-01 | Planta de localização e chumbação por pavimento (o modo prédio) só em prédio de aço: chumbador em 3 pavimentos ou mais. Senão, a planta do galpão | 1725e84 (bateria da 0.9.1, 22/10: o modo prédio da Vicente entrou no Capitão pré-moldado, 17 plantas "IFCBEAM"); test_predio |

## Pendências de gerador (correção que mora só no script da obra)

- COB-17: a parede de concreto entra como parede provisória no script de cada obra — o `telhas_cobertura` só vê barras.
- As telhas de toda obra são lançadas por script (`Projeto/OBRAS/<obra>/…`), sem botão na tela.
