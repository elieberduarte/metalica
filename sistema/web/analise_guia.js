// O quadro "Como ler" da análise estrutural (pedido de 06/10/2026): para cada modo da tela e para a combinação
// escolhida, o que aquilo representa, com o que o engenheiro deve se preocupar, o que não importa no nosso modelo,
// dicas práticas e as conferências com os números do projeto aberto. Texto aqui, separado da tela, para crescer.

const nf = (v, d = 1) => (v === null || v === undefined || !isFinite(v)) ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });

// ------------------------------------------------------------------ as combinações, pelo nome
export function explicarCombinacao(nome, cb) {
  if (!nome || nome === 'env') {
    return 'Envoltória: para cada barra, a pior das combinações últimas (ELU, com a 2ª ordem). Serve para achar onde a estrutura trabalha mais; para entender o porquê, escolha a combinação que aparece na coluna "comb." do ranking.';
  }
  const sentido = nome.includes('→') ? 'vento num sentido (→)' : nome.includes('←') ? 'vento no sentido oposto (←)' : nome.includes('↑') || nome.includes('↓') ? 'vento ao longo do comprimento' : '';
  if (nome.startsWith('ELS')) {
    return `Serviço (ELS, combinação rara, sem coeficientes): ${cb ? cb.descricao : ''}. Use só para deslocamentos (flechas, balanço do topo dos pilares) — nunca para a resistência das peças.`;
  }
  if (nome.includes('SC+')) return 'Sobrecarga como ação principal (×1,5) com o vento reduzido (ψ₀). Gravidade máxima com um pouco de vento.';
  if (nome.includes('SC')) return 'Gravidade máxima: permanentes majorados + sobrecarga como ação principal (×1,5). Costuma governar o banzo superior comprimido, a compressão nos pilares e a fundação à compressão.';
  if (nome.includes('Vat')) return `Vento ao longo da geratriz (atrito na cobertura, NBR 6123 7.2.2, e arrasto nos pilares e vigas, 8.1) — ${sentido}. Governa o contraventamento longitudinal, as vigas-trilho e os pilares na direção do comprimento.`;
  if (nome.includes('suc') || nome.includes('V2')) {
    return `Sucção (${sentido}): permanentes favoráveis (×1,0, o peso ajuda) + vento ×1,4 levantando a cobertura. É a combinação do ARRANCAMENTO nos chumbadores e da INVERSÃO de esforços: o banzo inferior, tracionado na gravidade, passa a ser comprimido — e só resiste se estiver travado lateralmente.`;
  }
  if (nome.includes('V1')) return `Vento como ação principal (×1,4), carregamento 1 da Tabela 25 da NBR 6123 (cobertura isolada), ${sentido}, com os permanentes majorados e a sobrecarga reduzida. Pressão de um lado e sucção do outro: governa os momentos nos pilares e nas bases.`;
  return cb ? cb.descricao : nome;
}

// ------------------------------------------------------------------ números do projeto
function topoDosPilares(D) {
  const tops = new Map();           // nó do topo → altura (mm)
  for (const b of D.barras) {
    if (b.papel !== 'pilar') continue;
    const za = D.nos[b.a][2], zb = D.nos[b.b][2];
    const topo = za >= zb ? b.a : b.b, base = za >= zb ? b.b : b.a;
    const H = Math.abs(za - zb);
    if (!tops.has(topo) || tops.get(topo).H < H) tops.set(topo, { H, base });
  }
  // o pilar partido em trechos: a altura até o pé (o apoio mais baixo)
  const zmin = Math.min(...D.apoios.map(a => D.nos[a.no][2]));
  for (const [n, v] of tops) v.H = D.nos[n][2] - zmin;
  return tops;
}

function conferirDeslocamentos(D) {
  const els = Object.keys(D.combinacoes).filter(c => D.combinacoes[c].tipo === 'ELS');
  if (!els.length) return null;
  const tops = topoDosPilares(D);
  let hMax = 0, hComb = '', hLim = 0, hNo = null;
  for (const c of els) {
    const U = D.por_comb[c].desl_mm;
    for (const [n, v] of tops) {
      const d = Math.hypot(U[n][0], U[n][1]);
      if (d > hMax) { hMax = d; hComb = c; hLim = v.H / 300; hNo = n; }
    }
  }
  // flecha das tesouras: o maior deslocamento vertical de um nó de treliça menos o do apoio (o topo do pilar)
  const trel = new Set();
  for (const b of D.barras) if (b.elemento === 'trelica') { trel.add(b.a); trel.add(b.b); }
  let vMax = 0, vComb = '';
  const zApoio = (U) => { let s = 0, k = 0; for (const n of tops.keys()) { s += U[n][2]; k++; } return k ? s / k : 0; };
  for (const c of els) {
    const U = D.por_comb[c].desl_mm, z0 = zApoio(U);
    for (const n of trel) { const d = Math.abs(U[n][2] - z0); if (d > vMax) { vMax = d; vComb = c; } }
  }
  const vao = D.info && D.info.vento ? D.info.vento.vao * 1000 : null;
  return { hMax, hComb, hLim, vMax, vComb, vLim: vao ? vao / 250 : null, vao };
}

const NOME = { banzo_sup: 'banzo superior', banzo_inf: 'banzo inferior', contraventamento: 'contraventamento' };
const nome = (p) => NOME[p] || p;

function chip(ok) { return ok ? '<span class="g-ok">ok</span>' : '<span class="g-ruim">passa do limite</span>'; }

// ------------------------------------------------------------------ o texto de cada modo
const MODOS = {
  modelo: {
    titulo: 'Modelo — o unifilar',
    oque: 'Cada barra é o eixo de uma peça, ligada às outras por nós. É o que o programa realmente calcula: o 3D renderizado não entra, só a linha, o perfil (área, inércias) e o giro da seção. Cores por função; tracejado = barra de hipótese (só existe na análise, para a estrutura não virar mecanismo).',
    preocupe: [
      'As ligações e os apoios são a maior fonte de diferença entre dois cálculos. Base engastada × rotulada muda o momento no pé do pilar de zero a centenas de kN·m. Confira com o engenheiro o que ele adotou.',
      'A tesoura apoiada na viga está rotulada (não transmite momento). Numa cobertura retrátil o apoio é um carrinho sobre o trilho: confirme com o fabricante se ele segura a força horizontal ou só a vertical.',
      'Barra faltando, nó que não encosta ou peça "voando" — o aviso de instabilidade aparece no topo do painel.',
    ],
    ignore: [
      'Pequenas excentricidades do desenho (o eixo do banzo e o do montante não se encontram no mesmo ponto): o esqueleto junta os nós próximos; o efeito é local e entra no detalhamento da ligação.',
      'Chapas, parafusos e acabamento: não entram na análise global.',
    ],
    dicas: [
      'Antes de olhar qualquer número, gire o modelo e confira se ele é a estrutura que vai ser montada.',
      'A seção amarela na base de cada pilar é a orientação que o cálculo usa: a alma aponta a direção da inércia forte. No galpão, a alma fica no plano do pórtico (o vão da tesoura). Clique no pilar para testar o giro de 90° (só na análise); o definitivo é girar na planta.',
      'Barras de hipótese (tracejadas) são um aviso: o projeto ainda não tem aquele travamento modelado. O cálculo final deve tê-lo de verdade.',
    ],
  },
  cargas: {
    titulo: 'Cargas — os casos',
    oque: 'Cada caso é uma ação isolada, sem coeficientes: PP (peso próprio pelos perfis), CP (permanentes da cobertura), SC (sobrecarga de cobertura, NBR 8800 B.5.1), V1/V2 (vento perpendicular à cumeeira, carregamentos 1 e 2 da Tabela 25 da NBR 6123 para cobertura isolada), Vat (atrito ao longo do comprimento). As setas são as forças nos nós (área de influência de cada nó do banzo superior). Nos casos de vento entra também o arrasto direto nos pilares, nas vigas e no X entre pilares (NBR 6123, 8.1: C·q·K·c por metro, c = a largura que o vento enxerga) — a Tabela 25 só cobre a cobertura.',
    preocupe: [
      'O vento é a maior incerteza: V0 (mapa de isopletas), categoria de rugosidade, S2 (altura e dimensões) e os coeficientes da tabela. Uma diferença de 10% no V0 dá 21% na pressão.',
      'A interpretação da Tabela 25 (sinal dos coeficientes no carregamento 2) e o vento nas abas de lona (7.2.5.1) — confirme com o engenheiro.',
      'O arrasto nos pilares e vigas (8.1) usa C = 2,0 nos perfis de faces planas (Tabela 26, conservador para I/H e tubo quadrado) e o Ca do cilindro pelo número de Reynolds nos tubos circulares (Tabela 27); sem anteparo de uma fila de pilares sobre a outra.',
      'Numa lona, a sobrecarga de 0,25 kN/m² pode não ser realista (a lona não acumula gente nem equipamento) — é premissa a combinar.',
    ],
    ignore: [
      'A distribuição exata entre nós vizinhos: o que importa para as peças é a carga total por tesoura e onde ela entra.',
    ],
    dicas: [
      'Abra "Equilíbrio dos casos": a soma das cargas tem de bater com a soma das reações em cada caso. É a primeira coisa a comparar com o cálculo do engenheiro — se a carga total de um caso não bate, nada depois vai bater.',
      'Conta de mão para conferir o vento: força ≈ pressão q × coeficiente × área em planta. Se a ordem de grandeza não bate, algo está errado nas premissas.',
    ],
  },
  esforcos: {
    titulo: 'Esforços — os diagramas',
    oque: 'Os esforços internos de cada barra na combinação escolhida: N (normal, + tração / − compressão), Vy e Vz (cortantes), T (torção), Mz (momento no eixo forte) e My (no eixo fraco). O desenho fica perpendicular à barra; os rótulos marcam os maiores valores. Nas combinações últimas (ELU) os esforços já são os de 2ª ordem (P-Δ com as imperfeições da NBR 8800:2024, 4.10.7; as combinações só gravitacionais aparecem duas vezes, ·X e ·Y — a imperfeição em cada direção); nas de serviço (ELS), de 1ª ordem.',
    preocupe: [
      'Banzos das tesouras: o N. Compressão é o que manda (flambagem); na sucção o sinal inverte.',
      'Pilares: N junto com M — a flexo-compressão. O pé do pilar engastado concentra o momento.',
      'Vigas-trilho: M e V, principalmente na cobertura retraída, com o peso todo concentrado em poucos metros.',
      'Diagonais e montantes comprimidos: a força é pequena, mas a barra é longa e fina — flambagem.',
    ],
    ignore: [
      'Momentos pequenos em diagonais e montantes (rotulados no plano da treliça): resíduo do modelo, a barra trabalha a N.',
      'Torção (T) residual em barras de treliça.',
    ],
    dicas: [
      'Compare sempre a mesma combinação com o engenheiro (ele pode ter nomeado diferente: veja os coeficientes de cada uma).',
      'Clique numa barra para ver os diagramas dela ao longo do comprimento e os valores de ponta.',
      'Para comparar com um programa que faz só 1ª ordem, desligue a 2ª ordem nas premissas e calcule de novo: a diferença é o efeito P-Δ (veja o quadro "2ª ordem").',
    ],
  },
  tensoes: {
    titulo: 'Tensões — o mapa de onde a estrutura trabalha',
    oque: 'σ = |N|/A + |Mz|/Wz + |My|/Wy na fibra mais solicitada, em relação ao fy. É um mapa de triagem: mostra onde olhar primeiro.',
    preocupe: [
      'Vermelho = olhar primeiro. Mas o mapa NÃO é a verificação da norma: não considera flambagem (global, local, lateral com torção). Uma barra comprimida e esbelta pode falhar com σ baixa — e uma peça compacta pode passar com σ um pouco acima do fy.',
      'Grupos inteiros acima de 100% (pilares, vigas) indicam problema de sistema — rigidez, travamento ou premissa — e não de uma peça.',
    ],
    ignore: [
      'Barras de hipótese (tracejadas): o perfil delas é provisório.',
      'Diferenças de 5–10% de tensão entre programas: o refinamento do modelo (onde ficam os nós, como entram as cargas) muda um pouco os picos.',
    ],
    dicas: [
      'A verificação pela norma (compressão com χ e Q, flexão FLA/FLM/FLT, flexo-compressão, esbeltez) está no modo Verificação: é ela que diz se a peça passa. Este mapa é a triagem.',
    ],
  },
  verificacao: {
    titulo: 'Verificação — cada peça pela norma',
    oque: 'O uso de cada peça = a solicitação dividida pela resistência de cálculo da norma (100% = o limite). A peça é o membro inteiro (o banzo todo, não cada trecho entre nós). Os esforços são os das combinações últimas com a 2ª ordem; a resistência sai da NBR 8800 (laminados e tubos) ou da NBR 14762 (U e Ue formados a frio): compressão com χ (a flambagem global) e Q (a flambagem local das chapas), tração na seção bruta, flexão nos dois eixos com FLA, FLM e FLT (a flambagem lateral com torção), cortante e a interação N + M (5.5.1.2).',
    preocupe: [
      '<b>Os comprimentos de flambagem</b> (no detalhe da peça): Lx no eixo forte e Ly no eixo fraco, medidos entre os pontos travados — um nó trava a peça numa direção quando chega nele uma barra de outra peça com componente nessa direção. Peça comprida sem nada chegando de lado (o banzo inferior de uma tesoura, a viga-trilho entre pilares) flamba no comprimento todo: a solução é travar, não engrossar.',
      '<b>FLT</b> em vigas e pilares de perfil I: com Lb grande, o momento resistente cai muito abaixo de W·fy. É o que derruba o pilar W de cobertura alta sem travamento lateral.',
      '<b>A inversão na sucção</b>: a peça tracionada na gravidade pode comprimir no vento — a verificação pega a pior combinação de cada peça, veja qual em "governa".',
      '<b>Instável (N ≥ Ne)</b>: a compressão passou da carga de flambagem elástica da peça — o B1 do P-δ vai ao infinito. Não é questão de perfil um pouco maior: falta travamento.',
      '<b>Esbeltez</b>: KL/r ≤ 200 na peça que comprime, ≤ 300 na só tracionada (barra redonda não entra).',
    ],
    ignore: [
      'Diferenças de poucos por cento com outro programa: o comprimento de flambagem adotado (K, pontos travados) e o Cb da FLT mudam o resultado — compare essas premissas, não só o número final.',
      'Barras de hipótese (tracejadas): verificadas, mas o perfil delas é provisório.',
    ],
    dicas: [
      'Clique numa peça: aparece a conta inteira — Lx, Ly, λ, as resistências (com χ, Q e o estado-limite da flexão), os esforços no ponto que governa, o B1 e a interação com os números.',
      'A tabela por grupo é a da troca de perfil: a estimativa usa as mesmas resistências desta verificação; depois de trocar, o recalcular confirma (os esforços se redistribuem).',
      'Premissas adotadas a favor da segurança: K = 1 entre pontos travados (permitido com a 2ª ordem global), Cb = 1 na FLT, Lt = o maior comprimento de flambagem, tração sem furos (a seção líquida fica para as ligações), perfil duplo como 2 × um perfil. O aço de cada peça vem do modelo (o dos tubos pode ser trocado nas premissas).',
    ],
  },
  deformada: {
    titulo: 'Deformada — os deslocamentos',
    oque: 'A estrutura deformada, exagerada para ver a forma (a escala não é real). O número é o maior deslocamento da combinação.',
    preocupe: [
      'Os limites de serviço (NBR 8800, Anexo C, Tabela C.1) se conferem nas combinações ELS (sem coeficientes): topo dos pilares em galpões H/300; vigas e treliças de cobertura L/250.',
      'Balanço grande nas combinações de vento = estrutura flexível: os efeitos de 2ª ordem (P-Δ) aumentam os momentos dos pilares. O programa já faz a 2ª ordem nas ELU — o quadro "2ª ordem" mostra Δ2/Δ1 (NBR 8800:2024, 4.10.4: até 1,10 pequena, até 1,40 média, acima grande). Grande deslocabilidade pede mais rigidez lateral.',
      'A forma: se a cobertura "anda" toda para um lado, falta contraventamento naquela direção.',
    ],
    ignore: [
      'O deslocamento nas combinações ELU: tem os coeficientes (×1,25…1,5), a rigidez reduzida (0,8) e a 2ª ordem — não se compara com limite nenhum; serve para ver a forma e o P-Δ.',
    ],
    dicas: [
      'Troque a combinação para uma ELS de vento e olhe o topo dos pilares. É a conferência mais simples e mais reveladora de um galpão.',
    ],
  },
  reacoes: {
    titulo: 'Reações — o que chega nas bases',
    oque: 'As forças que a estrutura entrega à fundação em cada base: Fz (vertical), H (horizontal) e M (momento, só nas engastadas). Verde comprime, vermelho arranca.',
    preocupe: [
      'Arrancamento (Fz negativo, combinações de sucção): é o que os chumbadores puxam e o que a fundação precisa segurar pelo peso.',
      'H: o cisalhamento nos chumbadores (ou uma barra de cisalhamento sob a placa).',
      'M na base engastada: placa grossa, chumbadores maiores e fundação que resista a momento. Se a base do projeto for rotulada, esses momentos não existem — e os pilares precisam de outro travamento.',
    ],
    ignore: [
      'Reações das combinações ELS para dimensionar chumbador ou placa: use as ELU.',
    ],
    dicas: [
      'Para a fundação, o projetista costuma pedir as reações por caso (sem coeficientes) para fazer as combinações dele — estão no resultado (reacoes_casos).',
      'Na tabela "Reações nas bases", passe o mouse: aparece a combinação de cada máximo. Dimensione a base com os valores concomitantes (Fz, H e M da mesma combinação), não com o máximo de cada um.',
      'O painel "Bases dos pilares" já faz isso: cada base pela NBR 8800:2024, 6.7, em todas as combinações, cada uma com o N, o M e o V dela — a placa e os chumbadores saem da Tabela 18 (com a Errata 1:2025), o arrancamento fica coberto pelas disposições da tabela (embutimento e armadura do bloco) e o cortante vai por atrito, arruelas soldadas ou placa de cisalhamento. Clique numa base para ver a conta e o bloco mínimo para o projetista de fundações.',
      'A 6.7 só cobre pilar I/H com momento no eixo forte. Pilar tubular é da NBR 16239; momento grande no eixo fraco pede outro método (base com enrijecedores) — os dois aparecem como apontamento.',
      'O painel "Apoio das tesouras" mostra o que cada tesoura entrega onde apoia: numa cobertura retrátil é o que o carrinho precisa segurar — inclusive o arrancamento e a força ao longo do trilho.',
    ],
  },
};

// ------------------------------------------------------------------ o que importa neste projeto (sempre no fim)
function noProjeto(D, RAIZ, estado) {
  const itens = [];
  const p = RAIZ.parametros || {};
  if (p.base === 'engastada') itens.push('Bases <b>engastadas</b> no modelo. É a premissa que mais muda o resultado — confirme com o engenheiro antes de comparar qualquer número.');
  if (RAIZ.outras_situacoes) itens.push('Cobertura <b>retrátil</b>: confira as duas situações. Aberta, a área de vento é máxima; retraída, o peso das 38 tesouras fica em poucos metros e carrega as vigas-trilho e os pilares daquela ponta. O esforço dinâmico do movimento (partida e frenagem do sistema) não está no modelo — pergunte ao fabricante.');
  const cmb = conferirDeslocamentos(D);
  if (cmb && cmb.hMax > 0) {
    itens.push(`Topo dos pilares (ELS): ${nf(cmb.hMax, 0)} mm em ${cmb.hComb}; limite H/300 ≈ ${nf(cmb.hLim, 0)} mm — ${chip(cmb.hMax <= cmb.hLim)}.`
      + (cmb.hMax > cmb.hLim ? ' Falta rigidez lateral: contraventamento entre pilares (o X de cabo das fotos do fabricante não está no modelo) ou pórticos mais rígidos.' : ''));
  }
  if (cmb && cmb.vLim) itens.push(`Flecha das tesouras (ELS): ${nf(cmb.vMax, 0)} mm em ${cmb.vComb}; limite L/250 = ${nf(cmb.vLim, 0)} mm (vão ${nf(cmb.vao / 1000, 2)} m) — ${chip(cmb.vMax <= cmb.vLim)}.`);
  const env = RAIZ.reacoes_envoltoria || [];
  if (env.length) {
    const up = env.reduce((m, e) => e.Fz_min[0] < m.Fz_min[0] ? e : m, env[0]);
    const mm = env.reduce((m, e) => e.M_max[0] > m.M_max[0] ? e : m, env[0]);
    if (up.Fz_min[0] < 0) itens.push(`Maior arrancamento: <b>${nf(-up.Fz_min[0], 1)} kN</b> (${up.Fz_min[1]}) — os chumbadores à tração e o peso da fundação.`);
    if (mm.M_max[0] > 0.5) itens.push(`Maior momento na base: <b>${nf(mm.M_max[0], 1)} kN·m</b> (${mm.M_max[1]}).`);
  }
  const so = D.segunda_ordem && D.segunda_ordem.resumo;
  if (so && so.razao_max) {
    itens.push(`2ª ordem: Δ2/Δ1 até <b>${nf(so.razao_max, 2)}</b> (${so.comb_razao_max}) — deslocabilidade <b>${so.classe}</b>.`
      + (so.classe === 'grande' ? ' <span class="g-ruim">Acima de 1,4 a NBR 8800 pede análise rigorosa e a estrutura precisa de mais rigidez lateral.</span>' : '')
      + ((so.instaveis || []).length ? ` <span class="g-ruim">Instável em ${so.instaveis.join(', ')}.</span>` : ''));
  }
  const V = D.verificacao;
  if (V) {
    const pc = V.pecas.filter(p => !p.hipotese && p.uso !== null && p.uso !== undefined);
    const nao = pc.filter(p => p.uso > 1);
    const pior = pc.reduce((m, p) => (!m || p.uso > m.uso ? p : m), null);
    itens.push(`Verificação: <b>${nao.length}</b> de ${pc.length} peças acima de 100%${pior ? ` — a pior: ${nome(pior.papel)} ${pior.perfil}, ${pior.uso >= 9.99 ? 'instável' : nf(pior.uso * 100, 0) + '%'} (${pior.verif})` : ''}.`);
    const semTrava = pc.filter(p => (p.obs || []).some(o => o.startsWith('nenhuma barra trava')));
    if (semTrava.length) {
      const fs = [...new Set(semTrava.map(p => nome(p.papel)))].join(', ');
      itens.push(`Peças comprimidas sem travamento lateral no comprimento todo: <b>${fs}</b> (${semTrava.length} peças). Trocar o perfil não resolve bem — trave (mão-francesa, linha de corrente, contraventamento) ou confirme com o engenheiro a restrição que ele considerou.`);
    }
  }
  const BS = RAIZ.bases;
  if (BS && BS.length) {
    const ok = BS.filter(b => b.ok === true).length, nao = BS.filter(b => b.ok === false).length, sem = BS.filter(b => b.ok === null || b.ok === undefined).length;
    const tps = BS.filter(b => b.base && b.base.tp).map(b => b.base.tp);
    itens.push(`Bases (NBR 8800:2024, 6.7): <b>${ok}</b> fecham${nao ? `, <span class="g-ruim">${nao} não fecham</span>` : ''}${sem ? `, ${sem} fora do método (pilar tubular — NBR 16239)` : ''}${tps.length ? `; placas de ${nf(Math.min(...tps), 1)} a ${nf(Math.max(...tps), 1)} mm` : ''}. Placa acima de ~38 mm sem enrijecedor é sinal de momento grande na base — de novo, rigidez lateral.`);
  }
  const AT = D.apoios_tesouras;
  if (AT && AT.pior && AT.pior.Fv_min.valor < 0) {
    itens.push(`Apoio das tesouras: arrancamento até <b>${nf(-AT.pior.Fv_min.valor, 1)} kN</b> e ${nf(Math.abs(AT.pior.Hl_max.valor), 1)} kN ao longo do trilho num só apoio — pergunte ao fabricante se o carrinho segura${D.movel ? ' (e se a sanfona é rígida como no modelo: ela concentra a carga nos apoios sobre os pilares)' : ''}.`);
  }
  if ((D.avisos || []).some(a => a.includes('hipótese de travamento'))) itens.push('Há barras de <b>hipótese</b> (tracejadas): o travamento real da cobertura ainda não está no modelo.');
  itens.push('Ao comparar com o engenheiro, siga a ordem: (1) premissas e cargas totais por caso; (2) reações; (3) esforços nos pilares e vigas; (4) peças. Diferença na etapa 1 explica todas as outras.');
  return itens;
}

// ------------------------------------------------------------------ o quadro
export function guia(D, RAIZ, estado) {
  if (!D || D.vazio) return '<p>Calcule a estrutura para ver o guia de leitura.</p>';
  const m = MODOS[estado.modo] || MODOS.modelo;
  const lista = (xs) => '<ul>' + xs.map(x => `<li>${x}</li>`).join('') + '</ul>';
  let comb = '';
  if (['esforcos', 'tensoes', 'verificacao', 'deformada', 'reacoes'].includes(estado.modo)) {
    const c = estado.comb === 'env' && !['tensoes', 'verificacao'].includes(estado.modo) ? null : estado.comb;
    comb = `<div class="g-comb"><b>${c && c !== 'env' ? c : 'Envoltória'}</b> — ${explicarCombinacao(c || 'env', c && D.combinacoes[c])}</div>`;
  }
  if (estado.modo === 'cargas' && estado.caso && D.casos[estado.caso]) {
    const eq = (D.equilibrio || {})[estado.caso];
    comb = `<div class="g-comb"><b>${estado.caso}</b> — ${D.casos[estado.caso].descricao}${eq ? `<br>Carga total: ${eq.cargas_kN.map(v => nf(v, 1)).join(' · ')} kN (x · y · z); reações: ${eq.reacoes_kN.map(v => nf(v, 1)).join(' · ')} kN.` : ''}</div>`;
  }
  return `<h3>${m.titulo}</h3>${comb}<p>${m.oque}</p>
    <h4>Preocupe-se com</h4>${lista(m.preocupe)}
    <h4>Não é o que importa aqui</h4>${lista(m.ignore)}
    <h4>Dicas práticas</h4>${lista(m.dicas)}
    <h4>Neste projeto</h4>${lista(noProjeto(D, RAIZ, estado))}`;
}
