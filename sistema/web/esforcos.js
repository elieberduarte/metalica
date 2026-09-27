/* Esforços da estrutura inteira (nucleo3d/esforcos.py; rota /api/projetos/<s>/esforcos): as
 * reações de cada pilar — o valor característico da gravidade, a maior compressão e o maior
 * arrancamento das combinações últimas — ao lado da carga que a locação do projeto escreve; a
 * planta com os pilares coloridos pela comparação; a memória do vento (NBR 6123:2023) com a
 * categoria do terreno e o grupo do S3 para recalcular; os casos, as combinações e as hipóteses. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const PARAMS = new URLSearchParams(location.search);
const PROJETO = PARAMS.get('projeto') || '';
const SVGNS = 'http://www.w3.org/2000/svg';
const TF = 9.80665;
let DADOS = null;
let MODO = 'razao';                  // razao | compressao | arrancamento
let SEL = null;                      // índice do pilar selecionado
let ORDEM = { chave: 'razao', desc: true };
let SO_DESTOAM = false;

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}
function sv(tag, attrs = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
const num = (v, c = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—'
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const tf = (kN) => kN / TF;

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  let j = {};
  try { j = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function alternarTema() {
  const raiz = document.documentElement;
  const escuro = matchMedia('(prefers-color-scheme: dark)').matches;
  const atual = raiz.getAttribute('data-tema') || (escuro ? 'escuro' : 'claro');
  const novo = atual === 'escuro' ? 'claro' : 'escuro';
  raiz.setAttribute('data-tema', novo);
  try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* privativa */ }
}

// ------------------------------------------------------------------ cada pilar
function linha(p, i) {
  const loc = p.locacao && p.locacao.Fz !== undefined ? p.locacao.Fz : null;
  const max = tf(p.envoltoria_kN.max), min = tf(p.envoltoria_kN.min);
  return { i, p, nome: (p.nome || '?').replace(/\(.*$/, ''), perfil: ((p.nome || '').match(/\((.*)\)/) || [])[1] || '',
           onde: p.onde || `(${num(p.x / 1000)}; ${num(p.y / 1000)}) m`, carac: tf(p.caracteristico_kN), max, min, loc,
           razao: loc ? max / loc : null };
}
const COR = { cinza: '#8a94a6', azul: '#3b82f6', verde: '#16a34a', laranja: '#d97706', verm: '#dc2626' };
function corDaRazao(r) {
  if (r === null) return COR.cinza;
  if (r < 0.5) return COR.azul;
  if (r <= 1.2) return COR.verde;
  if (r <= 2.0) return COR.laranja;
  return COR.verm;
}
const destoa = (l) => l.razao !== null && (l.razao < 0.5 || l.razao > 1.2);

// ------------------------------------------------------------------ planta
function planta(linhas) {
  const d = DADOS;
  const xs = [], ys = [];
  for (const s of d.planta) { xs.push(s[0], s[2]); ys.push(s[1], s[3]); }
  for (const l of linhas) { xs.push(l.p.x / 1000); ys.push(l.p.y / 1000); }
  const x0 = Math.min(...xs) - 2, x1 = Math.max(...xs) + 2, y0 = Math.min(...ys) - 2, y1 = Math.max(...ys) + 2;
  const svg = sv('svg', { class: 'planta', viewBox: `${x0} ${-y1} ${x1 - x0} ${y1 - y0}` });
  const g = sv('g');
  for (const s of d.planta) g.append(sv('line', { class: 'est', x1: s[0], y1: -s[1], x2: s[2], y2: -s[3] }));
  svg.append(g);
  const valor = (l) => MODO === 'arrancamento' ? Math.max(0, -l.min) : Math.max(0, l.max);
  const vmax = Math.max(1, ...linhas.map(valor));
  for (const l of linhas) {
    const v = valor(l);
    const r = 0.25 + 1.1 * Math.sqrt(v / vmax);
    let cor = corDaRazao(l.razao);
    if (MODO === 'compressao') cor = v > 0 ? COR.azul : COR.cinza;
    if (MODO === 'arrancamento') cor = v > 0 ? COR.verm : COR.cinza;
    const c = sv('circle', { class: 'pil' + (SEL === l.i ? ' sel' : ''), cx: l.p.x / 1000, cy: -l.p.y / 1000, r, fill: cor });
    const tit = sv('title');
    tit.textContent = `${l.nome} ${l.onde}\ncompressão ELU ${num(l.max)} tf · arrancamento ${num(l.min)} tf` +
      (l.loc !== null ? `\nlocação ${num(l.loc, 1)} tf · razão ${num(l.razao)}` : '\nsem carga na locação');
    c.append(tit);
    c.addEventListener('click', () => escolher(l.i, true));
    svg.append(c);
  }
  return svg;
}

// ------------------------------------------------------------------ montagem da tela
function numeros() {
  const d = DADOS, r = d.resumo;
  const soma = (f) => d.pilares.reduce((s, p) => s + f(p), 0);
  const loc = soma(p => (p.locacao && p.locacao.Fz) || 0);
  const box = (v, t) => el('div', {}, el('b', { texto: v }), el('span', { texto: t }));
  return el('div', { class: 'numeros' },
    box(`${num(tf(soma(p => p.caracteristico_kN)), 0)} tf`, 'soma característica (gravidade)'),
    box(`${num(tf(soma(p => p.envoltoria_kN.max)), 0)} tf`, 'soma da maior compressão ELU'),
    box(`${num(tf(soma(p => Math.min(0, p.envoltoria_kN.min))), 0)} tf`, 'soma do arrancamento ELU'),
    box(`${num(loc, 0)} tf`, 'soma da locação do projeto'),
    box(`${r.pilares}`, `pilares · ${r.engastados} engastados`),
    box(`${num(r.area_cobertura_m2, 0)} m²`, 'cobertura carregada'),
    box(`${num(r.peso_aco_kg / 1000, 1)} t`, 'aço no esqueleto'));
}

function caixaVento() {
  const v = DADOS.vento;
  const cx = el('div', { class: 'caixa' }, el('h3', { texto: 'Vento — NBR 6123:2023' }));
  if (!v) { cx.append(el('p', { class: 'vazio', texto: 'Sem V0: o projeto não tem as considerações de cálculo lidas das folhas.' })); return cx; }
  cx.append(el('p', { class: 'mem' }, 'V0 ', el('b', { texto: `${num(v.v0, 0)} m/s` }), ' · S1 ', el('b', { texto: num(v.s1) }),
    ' · S2 ', el('b', { texto: num(v.s2, 3) }), ` (categoria ${v.categoria}, classe ${v.classe}, h ${num(v.h, 1)} m)`,
    ' · S3 ', el('b', { texto: num(v.s3) }), ` (grupo ${v.grupo})`, ' → Vk ', el('b', { texto: `${num(v.vk, 1)} m/s` }),
    ' · q ', el('b', { texto: `${num(v.q, 3)} kN/m²` })));
  cx.append(el('p', { class: 'mem', texto: `Cobertura como edificação fechada (7.2.1: altura livre menor que metade da profundidade), telhado múltiplo pela Tabela 10 — tramo médio ${num(v.tramo, 1)} m, calhas em ${v.calhas_m.map(c => num(c, 1)).join(' / ')} m; cpi ${v.cpi.map(c => (c > 0 ? '+' : '') + num(c, 1)).join(' e ')}.` }));
  const cat = el('select', { id: 'categoria' }, ...['I', 'II', 'III', 'IV', 'V'].map(c => el('option', { value: c, texto: {
    I: 'I — mar, lagos, superfícies lisas', II: 'II — terreno aberto, poucos obstáculos', III: 'III — granjas, casas esparsas, subúrbios',
    IV: 'IV — cidade, subúrbio densamente construído', V: 'V — centro de grande cidade, muitos obstáculos altos' }[c] })));
  cat.value = v.categoria;
  const gr = el('select', { id: 'grupo' }, ...[1, 2, 3, 4, 5].map(g => el('option', { value: g, texto: {
    1: '1 — abriga inflamáveis, hospitais… (S3 1,11)', 2: '2 — aglomeração de pessoas (1,06)', 3: '3 — residência, comércio, indústria (1,00)',
    4: '4 — sem ocupação humana (0,95)', 5: '5 — temporária (0,83)' }[g] })));
  gr.value = String(v.grupo);
  cx.append(el('div', { class: 'campos' }, el('label', { texto: 'Categoria do terreno', for: 'categoria' }), cat,
    el('label', { texto: 'Grupo (S3)', for: 'grupo' }), gr));
  const bt = el('button', { type: 'button', class: 'botao-p', texto: 'Calcular de novo' });
  bt.addEventListener('click', () => calcular({ categoria: cat.value, grupo: Number(gr.value) }));
  cx.append(bt, el('span', { class: 'mem', texto: `  cálculo de ${DADOS.calculado_em} (${num(DADOS.segundos, 1)} s, v${DADOS.versao})` }));
  const casos = el('ul', { class: 'lista' }, v.casos.map(c => el('li', { texto: `${c.caso}: ${c.descricao} — ${num(c.para_cima_kN / TF, 0)} tf para cima` })));
  cx.append(el('details', {}, el('summary', { class: 'mem', texto: `os ${v.casos.length} casos de vento` }), casos));
  return cx;
}

function caixaDetalhe() {
  const cx = el('div', { class: 'caixa', id: 'detalhe' });
  if (SEL === null) {
    cx.append(el('h3', { texto: 'Pilar' }), el('p', { class: 'vazio', texto: 'Clique num pilar da planta ou da tabela para ver as reações por caso.' }));
    return cx;
  }
  const l = linha(DADOS.pilares[SEL], SEL);
  const p = l.p;
  cx.append(el('h3', {}, `${l.nome} — ${l.onde}`, el('span', { class: 'acoes' },
    el('button', { type: 'button', texto: 'Ver no 3D', onclick: () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}&destacar=${encodeURIComponent('ids:' + p.ids.join(','))}`; } }))));
  cx.append(el('p', { class: 'mem' }, `${l.perfil ? l.perfil + ' · ' : ''}${p.engastado ? 'base engastada' : 'base rotulada'} · `,
    'compressão ELU ', el('b', { texto: `${num(l.max)} tf` }), ` (${p.envoltoria_kN.max_comb}) · arrancamento `,
    el('b', { texto: `${num(l.min)} tf` }), ` (${p.envoltoria_kN.min_comb})`,
    l.loc !== null ? el('span', {}, ' · locação ', el('b', { texto: `${num(l.loc, 1)} tf` })) : ''));
  const tab = el('table', { class: 'tab' }, el('tr', {}, ['Caso', 'Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz'].map(t => el('th', { texto: t }))));
  const desc = {};
  for (const c of (DADOS.vento ? DADOS.vento.casos : [])) desc[c.caso] = c.descricao;
  Object.assign(desc, { PP: 'peso próprio', CP: 'telha, forro, painéis', SC: 'sobrecarga', AG: 'água das caixas' });
  for (const [c, v] of Object.entries(p.reacoes_kN)) {
    tab.append(el('tr', { title: desc[c] || '' }, el('td', { texto: c }), ...v.map((x, k) => el('td', { class: 'r', texto: num(k < 3 ? tf(x) : tf(x), 2) }))));
  }
  cx.append(tab, el('p', { class: 'mem', texto: 'Forças em tf e momentos em tf·m, no apoio (Fz positivo = o pilar comprime a base).' }));
  return cx;
}

function tabela(linhas) {
  const cols = [['nome', 'Pilar'], ['onde', 'Onde'], ['carac', 'Característico (tf)'], ['max', 'Compressão ELU (tf)'],
    ['min', 'Arrancamento ELU (tf)'], ['loc', 'Locação (tf)'], ['razao', 'ELU ÷ locação']];
  const tab = el('table', { class: 'tab' });
  tab.append(el('tr', {}, cols.map(([k, t]) => el('th', { class: ORDEM.chave === k ? 'ord' : '', texto: t,
    onclick: () => { ORDEM = { chave: k, desc: ORDEM.chave === k ? !ORDEM.desc : true }; montar(); } }))));
  const vis = linhas.filter(l => !SO_DESTOAM || destoa(l));
  vis.sort((a, b) => {
    const va = a[ORDEM.chave], vb = b[ORDEM.chave];
    if (va === null) return 1;
    if (vb === null) return -1;
    const r = typeof va === 'string' ? va.localeCompare(vb, 'pt-BR', { numeric: true }) : va - vb;
    return ORDEM.desc ? -r : r;
  });
  for (const l of vis) {
    tab.append(el('tr', { class: SEL === l.i ? 'sel' : '', onclick: () => escolher(l.i, false) },
      el('td', {}, el('span', { class: 'pt', style: `background:${corDaRazao(l.razao)}` }), l.nome, l.p.engastado ? ' (eng.)' : ''),
      el('td', { texto: l.onde }), el('td', { class: 'r', texto: num(l.carac) }),
      el('td', { class: 'r', texto: num(l.max) }), el('td', { class: 'r', texto: num(l.min) }),
      el('td', { class: 'r', texto: l.loc === null ? '—' : num(l.loc, 1) }),
      el('td', { class: 'r', texto: l.razao === null ? '—' : num(l.razao) })));
  }
  return tab;
}

function montar() {
  const d = DADOS;
  const linhas = d.pilares.map(linha);
  const raiz = $('#principal');
  raiz.replaceChildren();
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Resumo' }), numeros(),
    el('p', { class: 'mem', texto: 'A locação do projeto dá uma carga por pilar; aqui ela fica ao lado da maior compressão das combinações últimas. A comparação é a prova do modelo: onde destoa muito, o caminho da carga no esqueleto não é o do projeto (apoio, continuidade) ou falta carga (mezanino, passarela).' })));
  const modos = [['razao', 'ELU ÷ locação'], ['compressao', 'Compressão'], ['arrancamento', 'Arrancamento']];
  const cxPlanta = el('div', { class: 'caixa' }, el('h3', {}, 'Planta dos pilares', el('span', { class: 'acoes' },
    modos.map(([k, t]) => el('button', { type: 'button', class: MODO === k ? 'ativo' : '', texto: t, onclick: () => { MODO = k; montar(); } })))),
  planta(linhas),
  el('div', { class: 'legenda' }, MODO === 'razao'
    ? [el('span', {}, el('i', { style: `background:${COR.azul}` }), 'menos da metade da locação'), el('span', {}, el('i', { style: `background:${COR.verde}` }), '0,5 a 1,2'),
       el('span', {}, el('i', { style: `background:${COR.laranja}` }), '1,2 a 2'), el('span', {}, el('i', { style: `background:${COR.verm}` }), 'mais que o dobro'),
       el('span', {}, el('i', { style: `background:${COR.cinza}` }), 'sem carga na locação'), el('span', { texto: '· o tamanho é a compressão ELU' })]
    : el('span', { texto: MODO === 'compressao' ? 'O tamanho é a maior compressão das combinações últimas.' : 'O tamanho é o maior arrancamento (combinações de levantamento com o vento).' })));
  const lateral = el('div', {}, caixaDetalhe(), caixaVento());
  raiz.append(el('div', { class: 'linha2' }, cxPlanta, lateral));
  const filtro = el('label', { class: 'filtro' }, el('input', { type: 'checkbox', checked: SO_DESTOAM || undefined,
    onchange: (ev) => { SO_DESTOAM = ev.target.checked; montar(); } }), 'só os que destoam da locação (fora de 0,5 a 1,2)');
  raiz.append(el('div', { class: 'caixa' }, el('h3', {}, `Pilares (${linhas.length})`, el('span', { class: 'acoes' }, filtro)), tabela(linhas)));
  const casos = el('table', { class: 'tab' }, el('tr', {}, ['Caso', 'Carga (tf)', 'Reações (tf)', 'Erro de equilíbrio', 'Maior deslocamento'].map(t => el('th', { texto: t }))),
    Object.entries(d.casos).map(([c, x]) => el('tr', {}, el('td', { texto: c }), el('td', { class: 'r', texto: num(x.carga_kN / TF, 1) }),
      el('td', { class: 'r', texto: num(x.reacoes_kN / TF, 1) }), el('td', { class: 'r', texto: x.erro < 1e-4 ? 'fecha' : num(100 * x.erro, 2) + ' %' }),
      el('td', { class: 'r', texto: `${num(x.flecha_max_mm, 0)} mm` }))));
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Casos de carga' }), casos,
    el('details', {}, el('summary', { class: 'mem', texto: `as ${d.combinacoes.length} combinações últimas` }),
      el('ul', { class: 'lista' }, d.combinacoes.map(c => el('li', { texto: `${c.nome}: ${c.expressao}` }))))));
  raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Hipóteses do cálculo' }), el('ul', { class: 'lista' }, d.hipoteses.map(h => el('li', { texto: h })))));
  const av = (d.avisos || []).concat((d.cargas_sem_pilar || []).map(c => `carga da locação sem pilar perto: ${num(c.Fz, 1)} tf em (${num(c.x / 1000)}; ${num(c.y / 1000)}) m`));
  if (av.length) raiz.append(el('div', { class: 'caixa' }, el('h3', { texto: 'Avisos' }), el('ul', { class: 'lista' }, av.map(a => el('li', { texto: a })))));
}

function escolher(i, rolar) {
  SEL = i;
  montar();
  if (rolar) { const tr = document.querySelector('table.tab tr.sel'); if (tr) tr.scrollIntoView({ block: 'center' }); }
  else { const d = $('#detalhe'); if (d) d.scrollIntoView({ block: 'nearest' }); }
}

async function calcular(vento) {
  const raiz = $('#principal');
  raiz.classList.add('ocupado');
  document.body.style.cursor = 'progress';
  try {
    DADOS = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/esforcos`, vento ? { vento } : {});
    montar();
  } catch (e) {
    alert(`Não foi possível calcular: ${e.message}`);
  } finally {
    raiz.classList.remove('ocupado');
    document.body.style.cursor = '';
  }
}

async function iniciar() {
  $('#btn-voltar').addEventListener('click', () => { if (history.length > 1) history.back(); else location.href = '/'; });
  $('#btn-3d').addEventListener('click', () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-tema').addEventListener('click', alternarTema);
  if (!PROJETO) { $('#principal').replaceChildren(el('p', { class: 'vazio', texto: 'Abra esta tela a partir de um projeto (Modelo 3D → Ver → Esforços da estrutura).' })); return; }
  try {
    const p = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}`);
    $('#nome-projeto').textContent = (p.nome || (p.projeto && p.projeto.nome) || PROJETO);
    document.title = `Esforços — ${$('#nome-projeto').textContent} — Metálica`;
  } catch { /* o nome é só enfeite */ }
  try {
    DADOS = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/esforcos`);
  } catch (e) { $('#principal').replaceChildren(el('p', { class: 'vazio', texto: `Não foi possível ler: ${e.message}` })); return; }
  if (DADOS.vazio) {
    $('#principal').replaceChildren(el('div', { class: 'caixa' }, el('h3', { texto: 'Esforços' }),
      el('p', { class: 'vazio', texto: `${DADOS.vazio} O cálculo usa o modelo 3D do projeto (o esqueleto) e as cargas das folhas do projetista; leva alguns segundos.` }),
      el('button', { type: 'button', class: 'botao-p', texto: 'Calcular agora', onclick: () => calcular(null) })));
    return;
  }
  montar();
}

iniciar();
