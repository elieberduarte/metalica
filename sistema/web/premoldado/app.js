/* Galpão pré-moldado (em desenvolvimento): o formulário da obra, o dimensionamento pela rota
 * /api/premoldado/dimensionar (premoldado/galpao.py — NBR 6118 e NBR 9062), os resultados por
 * peça com a memória de cada verificação, o 3D gravado no projeto e o memorial em PDF. */
'use strict';

const PARAMS = new URLSearchParams(location.search);
let PROJETO = PARAMS.get('projeto') || '';
let DADOS = null;

// ------------------------------------------------------------------ o formulário
const CAMPOS = {
  'f-geometria': [
    ['nome', 'Nome da obra', 'texto'], ['local', 'Local', 'texto'],
    ['vao', 'Vão transversal (m)'], ['vaos_longitudinais', 'Vãos entre pórticos (m, separados por espaço)', 'lista'],
    ['altura_pilar', 'Altura dos pilares da fila A (m, acima da boca do cálice)'], ['altura_pilar_b', 'Altura dos pilares da fila B (m; 0 = igual à A)'],
    ['cobertura', 'Cobertura', 'sel', ['duas águas', 'uma água']], ['inclinacao_graus', 'Inclinação da cobertura (°, nas duas águas)'],
    ['cobertura_projeto', 'Cobertura de outra obra (para conferir no 3D)', 'sel', ['']],
    ['pilares_oitao', 'Pilares de oitão (eixo@distância à fila A, m)', 'oitao'],
  ],
  'f-cargas': [
    ['cobertura_permanente', 'Cobertura — telha e estrutura (kN/m²)'], ['sobrecarga', 'Sobrecarga da cobertura (kN/m²)'],
    ['fechamento_lateral', 'Fechamento lateral nos pilares (kN/m²)'], ['v0', 'V0 do vento (m/s)'],
    ['categoria', 'Categoria do terreno', 'sel', ['I', 'II', 'III', 'IV', 'V']], ['classe', 'Classe da edificação', 'sel', ['A', 'B', 'C']],
    ['s1', 'S1 (topografia)'], ['aberturas', 'Aberturas', 'sel', ['duas faces opostas', 'quatro faces', 'face dominante']],
  ],
  'f-vigas': [
    ['vigas_longitudinais', 'Vigas longitudinais', 'sel', ['nenhuma', 'calha', 'travamento']],
    ['extremidade_vigas', 'Apoio das longitudinais', 'sel', ['sem recorte', 'dente Gerber']],
    ['consolo_altura', 'Altura do consolo (cm)'], ['consolo_a', 'Distância da face ao apoio (cm)'],
    ['viga_cobertura', 'Viga de cobertura em concreto', 'bool'], ['umidade', 'Umidade média do ar (%)'],
    ['viga_cobertura_protendida', 'Viga de cobertura protendida', 'bool'], ['tercas_protendidas', 'Terças protendidas (T)', 'bool'],
    ['tercas_espacamento', 'Espaçamento das terças (m)'],
    ['cordoalha', 'Cordoalha', 'sel', ['CP190 RB 9,5', 'CP190 RB 12,7', 'CP190 RB 15,2', 'CP210 RB 12,7']],
    ['sigma_pi', 'σpi/fptk (≤ 0,74)'], ['fcj_liberacao', 'fcj na liberação (MPa)'],
    ['acomodacao_pista', 'Acomodação na pista (mm)'], ['pista', 'Comprimento da pista (m)'],
  ],
  'f-ponte': [
    ['ponte_rolante', 'Tem ponte rolante', 'bool'], ['pr_altura', 'Topo do consolo acima da boca do cálice (m)'],
    ['pr_excentricidade', 'Eixo do trilho a partir do eixo do pilar (cm)'], ['pr_roda_max', 'Carga máxima por roda (kN)'],
    ['pr_roda_min', 'Carga mínima por roda (kN)'], ['pr_rodas', 'Rodas por cabeceira'], ['pr_entre_eixos', 'Distância entre rodas (m)'],
    ['pr_impacto', 'Impacto vertical (fração)'], ['pr_transversal', 'Força transversal por lado (kN)'],
    ['pr_longitudinal', 'Frenagem por lado (kN)'], ['pr_viga_peso', 'Viga de rolamento + trilho (kN/m)'],
    ['pr_altura_trilho', 'Topo do trilho acima do consolo (m)'], ['consolo_pr_altura', 'Altura do consolo da ponte (cm)'],
  ],
  'f-fundacao': [
    ['fundacao', 'Fundação', 'sel', ['nenhuma', 'sapata', 'estacas']], ['sigma_adm', 'Tensão admissível do solo (kPa)'],
    ['fracao_comprimida', 'Área comprimida mínima (fração)'], ['peso_solo', 'Peso do solo (kN/m³)'],
    ['estaca_diametro', 'Diâmetro da estaca (cm)'], ['estaca_carga', 'Carga admissível da estaca (kN)'],
    ['estaca_tracao', 'Tração admissível da estaca (kN)'], ['estaca_espacamento', 'Espaçamento mínimo (× diâmetro)'],
  ],
  'f-concreto': [
    ['fck', 'fck (MPa)'], ['agregado', 'Agregado', 'sel', ['basalto', 'granito', 'gnaisse', 'calcário', 'arenito']],
    ['caa', 'Classe de agressividade', 'sel', ['I', 'II', 'III', 'IV']], ['pre_fabricado', 'Pré-fabricado (γc 1,3 / γs 1,10)', 'bool'],
    ['phi_fluencia', 'Coeficiente de fluência φ'], ['interface_calice', 'Interface do cálice', 'sel', ['rugosa', 'lisa']],
    ['parede_calice', 'Parede do colarinho (cm)'],
  ],
};

function montarFormulario(d) {
  for (const [id, campos] of Object.entries(CAMPOS)) {
    const box = $('#' + id);
    box.replaceChildren();
    for (const [k, rot, tipo, ops] of campos) {
      const v = d[k];
      let inp;
      if (tipo === 'sel') {
        inp = el('select', { id: 'c-' + k }, ops.map(o => el('option', { value: o, texto: o, selected: String(v) === o || undefined })));
      } else if (tipo === 'bool') {
        inp = el('input', { id: 'c-' + k, type: 'checkbox', checked: v ? true : undefined });
      } else {
        const val = tipo === 'oitao' ? (v || []).map(([e, y]) => `${e}@${String(y).replace('.', ',')}`).join(' ')
          : tipo === 'lista' ? (v || []).map(x => String(x).replace('.', ',')).join(' ')
          : (typeof v === 'number' ? String(v).replace('.', ',') : (v ?? ''));
        inp = el('input', { id: 'c-' + k, value: val });
      }
      const largo = tipo === 'texto' || tipo === 'lista' || tipo === 'oitao';
      box.append(el('label', { for: 'c-' + k, class: largo ? 'largo' : '', texto: rot }), largo ? el('div', { class: 'largo' }, inp) : inp);
    }
  }
}

function lerFormulario() {
  const d = Object.assign({}, DADOS || {});
  for (const campos of Object.values(CAMPOS)) {
    for (const [k, , tipo] of campos) {
      const e = $('#c-' + k);
      if (!e) continue;
      if (tipo === 'bool') d[k] = e.checked;
      else if (tipo === 'lista' || tipo === 'oitao') d[k] = e.value.trim();
      else d[k] = e.value;
    }
  }
  return d;
}

// ------------------------------------------------------------------ os resultados
function svgSecao(p) {
  const b = p.b, h = p.h, br = p.barras;
  const esc = 3.2, pad = 22, W = h * esc, H = b * esc, c = 4.5;
  const pts = [];
  for (const x of [c, h - c]) for (let i = 0; i < br.n_h; i++) pts.push([x, c + i * (b - 2 * c) / Math.max(br.n_h - 1, 1)]);
  for (const y of [c, b - c]) for (let i = 1; i <= br.n_b; i++) pts.push([c + i * (h - 2 * c) / (br.n_b + 1), y]);
  const circ = pts.map(([x, y]) => `<circle cx="${pad + x * esc}" cy="${pad + y * esc}" r="${Math.max(br.bitola / 10 * esc / 2, 2.4)}" fill="currentColor"/>`).join('');
  return `<svg width="${W + 2 * pad}" height="${H + 2 * pad}" viewBox="0 0 ${W + 2 * pad} ${H + 2 * pad}" style="color:var(--texto)">
    <rect x="${pad}" y="${pad}" width="${W}" height="${H}" fill="var(--painel2)" stroke="currentColor"/>
    <rect x="${pad + 2.5 * esc}" y="${pad + 2.5 * esc}" width="${W - 5 * esc}" height="${H - 5 * esc}" fill="none" stroke="var(--azul)" rx="3"/>
    ${circ}<text x="${pad + W / 2}" y="${pad - 7}" font-size="11" text-anchor="middle" fill="currentColor">h = ${h} cm</text>
    <text x="${pad - 7}" y="${pad + H / 2}" font-size="11" text-anchor="middle" fill="currentColor" transform="rotate(-90 ${pad - 7} ${pad + H / 2})">b = ${b} cm</text></svg>`;
}

/** a seção da viga (contorno em cm, y para cima) com as barras de baixo e de cima */
function svgViga(v) {
  const pts = v.contorno, a = v.armadura || {};
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const W = Math.max(...xs) - Math.min(...xs), H = Math.max(...ys);
  const esc = Math.min(3.2, 170 / Math.max(W, H)), pad = 22;
  const X = x => pad + (x - Math.min(...xs)) * esc, Y = y => pad + (H - y) * esc;
  const poli = pts.map(p => `${X(p[0])},${Y(p[1])}`).join(' ');
  const c = 4.0, circ = [];
  const base = pts.filter(p => p[1] < 1e-6).map(p => p[0]);
  const larg = Math.max(...base) - Math.min(...base);
  const linha = (n, fi, y, largura) => {
    for (let i = 0; i < n; i++) {
      const x = -largura / 2 + c + (n > 1 ? i * (largura - 2 * c) / (n - 1) : (largura - 2 * c) / 2);
      circ.push(`<circle cx="${X(x)}" cy="${Y(y)}" r="${Math.max(fi / 10 * esc / 2, 2.2)}" fill="currentColor"/>`);
    }
  };
  if (a.camadas_cord) {
    const fi = parseFloat(String(a.cordoalha || '12,7').split(' ').pop().replace(',', '.')) || 12.7;
    for (const [n, y] of a.camadas_cord) linha(n, fi, y, larg);
  }
  if (a.n_inf) {
    const porCam = Math.ceil(a.n_inf / (a.camadas || 1));
    for (let k = 0, resto = a.n_inf; k < (a.camadas || 1); k++, resto -= porCam) linha(Math.min(porCam, resto), a.fi_inf, c + k * (a.fi_inf / 10 + 2), larg);
  }
  if (a.n_sup) {
    const topo = v.contorno.filter(p => p[1] >= H - 1e-6).map(p => p[0]);
    if (v.tipo === 'U') {
      const t = v.parametros.t, r = Math.max(a.fi_sup / 10 * esc / 2, 2.2);
      for (const x of [-W / 2 + t / 2, W / 2 - t / 2]) circ.push(`<circle cx="${X(x)}" cy="${Y(H - c)}" r="${r}" fill="currentColor"/>`);
    } else linha(a.n_sup, a.fi_sup, H - c, Math.max(...topo) - Math.min(...topo));
  }
  return `<svg width="${W * esc + 2 * pad}" height="${H * esc + 2 * pad}" viewBox="0 0 ${W * esc + 2 * pad} ${H * esc + 2 * pad}" style="color:var(--texto)">
    <polygon points="${poli}" fill="var(--painel2)" stroke="currentColor"/>${circ.join('')}
    <text x="${pad + W * esc / 2}" y="${pad - 7}" font-size="11" text-anchor="middle" fill="currentColor">${num(W, 0)} cm</text>
    <text x="${pad - 7}" y="${pad + H * esc / 2}" font-size="11" text-anchor="middle" fill="currentColor" transform="rotate(-90 ${pad - 7} ${pad + H * esc / 2})">h = ${num(H, 0)} cm</text></svg>`;
}

function cargas(r) {
  if (!r || !r.cargas || !r.cargas.length) return null;
  return el('details', { class: 'mem' }, el('summary', { texto: 'cargas e combinação' }),
    r.cargas.map(p => el('div', { class: 'passo', html: `${p.texto}: ${p.formula || ''} ${p.conta ? '= ' + p.conta : ''} → <b>${p.valor || ''}</b> <i>${p.norma || ''}</i>` })));
}

function mostrar(j) {
  const raiz = $('#resultado');
  raiz.replaceChildren();
  if (j.avisos && j.avisos.length) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Apontamentos' }), el('ul', { class: 'mem' }, j.avisos.map(e => el('li', { texto: e })))));
  if (j.erros && j.erros.length) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Erros' }), el('ul', {}, j.erros.map(e => el('li', { texto: e })))));
  const tot_v = j.lista.reduce((s, l) => s + l.volume_m3 * l.quantidade, 0);
  const tot_a = j.lista.reduce((s, l) => s + (l.aco_kg || 0) * l.quantidade, 0);
  const box = (v, t) => el('div', {}, el('b', { texto: v }), el('span', { texto: t }));
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Resumo' }),
    el('div', { class: 'numeros' },
      box(j.ok ? 'tudo atende' : 'há reprovações', 'situação'),
      ...j.pilares.map(p => box(`${p.b} × ${p.h} cm`, `pilar ${p.tipo} — ${p.armadura}`)),
      ...(j.vigas || []).map(v => box(v.secao, `${v.funcao} ${v.marca} (${v.quantidade} un.)`)),
      box(`${num(tot_v, 1)} m³`, 'concreto das peças e cálices'), box(`${num(tot_a, 0)} kg`, 'aço das peças'),
      j.vento ? box(`${num(j.vento.q, 3)} kN/m²`, `vento: V0 ${num(j.vento.V0, 0)} m/s, Vk ${num(j.vento.Vk, 1)} m/s`) : null)));
  for (const p of j.pilares) {
    raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: `Pilar ${p.tipo} — ${p.b} × ${p.h} cm (${p.quantidade} un.)` }),
      el('div', { class: 'secao' }, el('div', { html: svgSecao(p) }),
        el('div', { class: 'mem' }, `${p.armadura} + estribos ø${num(p.estribos[0], 1)} c/ ${num(p.estribos[1], 1)} cm`, el('br'),
          `comprimento total ${num(p.comprimento_total, 2)} m (com o embutimento no cálice)`, el('br'), `razão ${num(p.razao)}`)),
      verificacoes(p.resultado)));
  }
  for (const v of j.vigas || []) {
    const alt = (v.alternativas || []).map(a => `${a.secao}: ${a.ok ? 'passa' : 'não passa'}${a.razao != null ? ' (' + num(a.razao) + ')' : ''}`).join(' · ');
    raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: `${v.funcao} ${v.marca} — ${v.secao} (${v.quantidade} un.)` }),
      el('div', { class: 'secao' }, el('div', { html: svgViga(v) }),
        el('div', { class: 'mem' }, v.texto_armadura, el('br'),
          `vão de cálculo ${num(v.vao)} m${Math.abs(v.h - v.h_apoio) > 0.5 ? `, altura ${num(v.h_apoio, 0)} cm no apoio e ${num(v.h, 0)} cm no meio` : ''}`, el('br'),
          `peso ${num(v.peso_kN, 1)} kN; reação característica ${num(v.reacoes.pp + v.reacoes.g, 1)} kN (permanente) + ${num(v.reacoes.q, 1)} kN (variável)`, el('br'),
          `razão da viga ${num(v.razao)}`, alt ? el('div', { texto: 'seções tentadas: ' + alt }) : null)),
      cargas(v.resultado), verificacoes(v.resultado),
      el('h3', { texto: v.apoio.elemento, style: 'margin-top:10px' }), el('p', { class: 'mem', texto: v.apoio.perfil }), verificacoes(v.apoio),
      el('h3', { texto: v.elastomero.elemento, style: 'margin-top:10px' }), cargas(v.elastomero), verificacoes(v.elastomero)));
  }
  for (const r of j.ligacoes || []) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: r.elemento }), el('p', { class: 'mem', texto: r.perfil }), verificacoes(r)));
  for (const r of j.fundacoes || []) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: r.elemento }),
    el('p', { class: 'mem', texto: r.perfil }), r.dados && r.dados.armadura ? el('p', { class: 'mem', texto: r.dados.armadura }) : null, verificacoes(r),
    r.hipoteses && r.hipoteses.length ? el('ul', { class: 'mem' }, r.hipoteses.map(h => el('li', { html: h.texto }))) : null));
  for (const r of j.calices) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: r.elemento }), el('p', { class: 'mem', texto: r.perfil }), verificacoes(r)));
  for (const r of j.transitorias) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: r.elemento }), verificacoes(r)));
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Lista de peças' }),
    el('table', { class: 'tab' }, el('tr', {}, ['Marca', 'Peça', 'Qtd.', 'Comp. (m)', 'Concreto (m³/un.)', 'Peso (kN/un.)', 'Aço (kg/un.)', 'Armadura'].map(t => el('th', { texto: t }))),
      j.lista.map(l => el('tr', {}, el('td', { texto: l.marca }), el('td', { texto: l.descricao }), el('td', { class: 'r', texto: l.quantidade }),
        el('td', { class: 'r', texto: num(l.comprimento_m) }), el('td', { class: 'r', texto: num(l.volume_m3, 3) }),
        el('td', { class: 'r', texto: l.peso_kN == null ? '—' : num(l.peso_kN, 1) }), el('td', { class: 'r', texto: l.aco_kg == null ? '—' : num(l.aco_kg, 1) }),
        el('td', { texto: l.armadura }))))));
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Hipóteses' }), el('ul', { class: 'mem' }, j.hipoteses.map(h => el('li', { texto: h })))));
}

/** o campo "cobertura de outra obra": as obras metálicas com modelo (refeito depois de montar o formulário) */
async function preencherCoberturas() {
  try {
    const lp = await pedir('/api/projetos');
    const lista = (Array.isArray(lp) ? lp : (lp.projetos || [])).filter(x => (x.area || 'metalica') !== 'premoldado' && x.tem_modelo);
    const sel = $('#c-cobertura_projeto');
    sel.replaceChildren(el('option', { value: '', texto: '— nenhuma —' }),
      ...lista.map(x => el('option', { value: x.slug, texto: x.nome, selected: (DADOS || {}).cobertura_projeto === x.slug || undefined })));
  } catch (e) { /* sem a lista: o campo fica vazio */ }
}

async function comEspera(botao, fn) {
  const b = $(botao);
  const t = b.textContent;
  b.disabled = true; b.textContent = 'Calculando…';
  try { await fn(); } catch (e) { $('#situacao').textContent = 'Erro: ' + e.message; } finally { b.disabled = false; b.textContent = t; }
}

async function garantirProjeto() {
  if (PROJETO) return PROJETO;
  const d = lerFormulario();
  const p = await pedir('/api/premoldado/projeto', { nome: d.nome || 'Galpão pré-moldado', local: d.local || '', dados: d });
  PROJETO = p.slug;
  history.replaceState(null, '', '/premoldado?projeto=' + encodeURIComponent(PROJETO));
  return PROJETO;
}

/** os eixos gravados na planta (Desenho 2D → Malha de eixos): o vão e os vãos entre pórticos */
async function eixosDaPlanta(p) {
  if (!PROJETO) return;
  const caixa = $('#caixa-eixos');
  $('#btn-planta').onclick = async () => {
    // a planta de lançamento, senão a locação dos pilares, senão o primeiro desenho do projeto
    let ds = [];
    try { const r = await pedir('/api/projetos/' + encodeURIComponent(PROJETO)); ds = ((r.resumo || {}).desenhos || []).map(d => d.nome); } catch (e) { ds = []; }
    const alvo = ['planta-de-lançamento', 'locacao-pilares', 'locacao-dos-pilares'].find(n => ds.includes(n)) || ds[0] || 'planta-de-lançamento';
    location.href = `/dividida?projeto=${encodeURIComponent(PROJETO)}&vista=2d&desenho=${encodeURIComponent(alvo)}`;
  };
  if (!p.eixos) {
    if (p.lancamento || p.arquitetonico) {
      caixa.hidden = false;
      $('#eixos-texto').textContent = 'A planta do arquitetônico está no projeto, mas os eixos ainda não foram gravados: abra a planta, lance a malha de eixos (Malha de eixos…) e grave.';
      $('#btn-usar-eixos').hidden = true;
    }
    return;
  }
  let e;
  try { e = await pedir('/api/premoldado/eixos', { projeto: PROJETO }); } catch (err) {
    caixa.hidden = false; $('#btn-usar-eixos').hidden = true; $('#eixos-texto').textContent = err.message; return;
  }
  caixa.hidden = false;
  $('#btn-usar-eixos').hidden = false;
  $('#eixos-texto').replaceChildren(
    `Eixos ${e.letras.join(', ')} (vão de ${num(e.vao)} m) e ${e.numeros.join(', ')} (${e.vaos_longitudinais.length} vãos: ${e.vaos_longitudinais.map(v => num(v, 3)).join(' + ')} m).`,
    ...e.avisos.map(a => el('div', { class: 'nao', style: 'font-weight:400; margin-top:4px', texto: '⚠ ' + a })));
  $('#btn-usar-eixos').onclick = () => {
    $('#c-vao').value = String(e.vao).replace('.', ',');
    $('#c-vaos_longitudinais').value = e.vaos_longitudinais.map(v => String(v).replace('.', ',')).join(' ');
    $('#situacao').textContent = 'Vãos trazidos da planta — clique em Dimensionar.';
    $('#btn-dimensionar').click();
  };
}

async function iniciar() {
  ligarTema();
  if (PROJETO) {
    const resp = await pedir('/api/projetos/' + encodeURIComponent(PROJETO));
    const p = resp.projeto || resp;
    DADOS = (p.dados) || {};
    $('#nome-projeto').textContent = ' — ' + (p.nome || PROJETO);
    eixosDaPlanta(p).catch(() => { /* os eixos são opcionais */ });
  }
  if (!DADOS || !Object.keys(DADOS).length) {
    const j = await pedir('/api/premoldado/dimensionar', { dados: {} });
    DADOS = j.dados;
    mostrar(j);
  }
  montarFormulario(DADOS);
  // as obras da Metálica que podem dar a cobertura (a lista do programa)
  await preencherCoberturas();
  $('#btn-dimensionar').addEventListener('click', () => comEspera('#btn-dimensionar', async () => {
    const j = await pedir('/api/premoldado/dimensionar', { dados: lerFormulario(), projeto: PROJETO || undefined });
    DADOS = j.dados; mostrar(j); $('#situacao').textContent = j.ok ? 'Dimensionado: tudo atende.' : 'Dimensionado com reprovações.';
  }));
  $('#btn-3d').addEventListener('click', () => comEspera('#btn-3d', async () => {
    const s = await garantirProjeto();
    const j = await pedir('/api/premoldado/modelo', { projeto: s, dados: lerFormulario() });
    location.href = j.url;
  }));
  $('#btn-memorial').addEventListener('click', () => comEspera('#btn-memorial', async () => {
    const s = await garantirProjeto();
    const j = await pedir('/api/premoldado/memorial', { projeto: s, dados: lerFormulario() });
    $('#situacao').innerHTML = `Memorial gravado no projeto: <a href="${j.url}" target="_blank">abrir o PDF</a>`;
  }));
  $('#btn-detalhar').addEventListener('click', () => comEspera('#btn-detalhar', async () => {
    const s = await garantirProjeto();
    const j = await pedir('/api/premoldado/detalhamento', { projeto: s, dados: lerFormulario() });
    location.href = j.url;
  }));
  $('#btn-ler-planta').addEventListener('click', () => comEspera('#btn-ler-planta', async () => {
    const s = new URLSearchParams(location.search).get('projeto');
    if (!s) throw new Error('abra um projeto para ler a planta de lançamento');
    const j = await pedir('/api/premoldado/planta/dados', { projeto: s });
    DADOS = j.dados;
    montarFormulario(DADOS);
    await preencherCoberturas();
    $('#situacao').textContent = 'Planta de lançamento lida: ' + j.avisos.join('; ');
    $('#btn-dimensionar').click();
  }));
  $('#btn-pranchas').addEventListener('click', () => comEspera('#btn-pranchas', async () => {
    const s = await garantirProjeto();
    const j = await pedir('/api/premoldado/pranchas', { projeto: s, dados: lerFormulario() });
    location.href = j.url;
  }));
  $('#btn-apoios-cobertura').addEventListener('click', () => comEspera('#btn-apoios-cobertura', async () => {
    const slug = $('#c-cobertura_projeto').value;
    const g = await pedir('/api/premoldado/cobertura_geometria', { cobertura_projeto: slug });
    $('#c-vao').value = String(g.vao).replace('.', ',');
    $('#c-vaos_longitudinais').value = g.vaos_longitudinais.map(v => String(v).replace('.', ',')).join(' ');
    $('#c-altura_pilar').value = String(g.altura_pilar).replace('.', ',');
    $('#c-altura_pilar_b').value = String(g.altura_pilar_b || 0).replace('.', ',');
    $('#c-cobertura').value = g.cobertura || 'duas águas';
    $('#c-pilares_oitao').value = g.pilares_oitao.map(([e, y]) => `${e}@${String(y).replace('.', ',')}`).join(' ');
    $('#situacao').textContent = `Pilares nos apoios da cobertura (${g.fonte}).` + (g.avisos.length ? ' ' + g.avisos.join('; ') : '');
    $('#btn-dimensionar').click();
  }));
  $('#btn-locacao').addEventListener('click', () => comEspera('#btn-locacao', async () => {
    const s = await garantirProjeto();
    const j = await pedir('/api/premoldado/locacao', { projeto: s, dados: lerFormulario() });
    location.href = j.url;
  }));
  if (PROJETO) $('#btn-dimensionar').click();
}
iniciar().catch(e => { $('#situacao').textContent = 'Erro: ' + e.message; });
