/* Treliças lidas (nucleo3d/trelicas_lidas.py): cada elevação do projeto recebido ("TESOURA 16 - 3X")
 * ao lado do bloco que a montagem pela planta leu dela. À esquerda as elevações por família, com
 * o ponto laranja nas que têm algo a conferir; à direita o desenho do projetista e as barras
 * lidas no mesmo referencial (lado a lado ou uma sobre a outra), as quantidades e onde cada
 * cópia entrou — pelos eixos, com o encaixe no vão da planta e o atalho para vê-la no 3D. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const PARAMS = new URLSearchParams(location.search);
const PROJETO = PARAMS.get('projeto') || '';
let DADOS = null;
let ATUAL = PARAMS.get('peca') || '';
let sobreposto = false;
const SVGNS = 'http://www.w3.org/2000/svg';

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
const m = (mm) => (Number(mm) / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

async function pedir(rota) {
  const r = await fetch(rota, { cache: 'no-store' });
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

const url3d = (destacar) => `/editor?projeto=${encodeURIComponent(PROJETO)}` + (destacar ? `&destacar=${encodeURIComponent('peca:' + destacar)}` : '');

function montarIndice() {
  const lista = $('#lista');
  lista.replaceChildren();
  const filtro = $('#busca').value.trim().toLowerCase();
  const so = $('#so-conferir').checked;
  const grupos = new Map();
  for (const t of DADOS.trelicas) {
    if (filtro && !t.nome.toLowerCase().includes(filtro)) continue;
    if (so && t.situacao === 'ok') continue;
    if (!grupos.has(t.familia)) grupos.set(t.familia, []);
    grupos.get(t.familia).push(t);
  }
  for (const [fam, ts] of grupos) {
    lista.append(el('h3', { texto: `${fam} (${ts.length})` }));
    for (const t of ts) {
      lista.append(el('button', {
        type: 'button', class: t.nome === ATUAL ? 'ativo' : '', 'data-peca': t.nome,
        title: t.pendencias.length ? t.pendencias.join('; ') : 'nada a conferir',
        onclick: () => escolher(t.nome),
      }, el('span', { class: 'pt' + (t.situacao === 'ok' ? '' : ' conferir') }), t.nome,
      el('span', { class: 'n', texto: t.sem_elevacao ? 'sem elevação' : `${t.no_modelo}/${t.qtd_projeto}` })));
    }
  }
  if (!lista.children.length) lista.append(el('p', { class: 'vazio', texto: 'Nenhuma elevação com esse filtro.' }));
}

function escolher(nome) {
  ATUAL = nome;
  const u = new URL(location.href); u.searchParams.set('peca', nome); history.replaceState(null, '', u);
  for (const b of document.querySelectorAll('#lista button')) b.classList.toggle('ativo', b.dataset.peca === nome);
  mostrar(DADOS.trelicas.find(t => t.nome === nome));
}

/** a caixa (s, h) do que vai ser desenhado */
function caixaDe(t, comOriginal) {
  const xs = [], ys = [];
  for (const b of t.membros) { xs.push(b[1], b[3]); ys.push(b[2], b[4]); }
  if (comOriginal) {
    for (const d of t.desenho) {
      if (d.t === 'l') { xs.push(d.p[0], d.p[2]); ys.push(d.p[1], d.p[3]); }
      else if (d.t === 'p') for (const v of d.v) { xs.push(v[0]); ys.push(v[1]); }
      else if (d.t === 'c' || d.t === 'a') { xs.push(d.c[0] - d.r, d.c[0] + d.r); ys.push(d.c[1] - d.r, d.c[1] + d.r); }
      else if (d.t === 'x') { xs.push(d.p[0], d.p[0] + d.s.length * d.h * 0.7); ys.push(d.p[1], d.p[1] + d.h); }
    }
  }
  // arcos enormes (raio de calandra) não podem esticar a caixa: fica a da treliça com folga
  const L = Math.max(t.comprimento, 1000), H = Math.max(t.altura, 500);
  const cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const x0 = cl(Math.min(...xs), -0.4 * L, 0) - 200, x1 = cl(Math.max(...xs), L, 1.4 * L) + 200;
  const y0 = cl(Math.min(...ys), -2.5 * H, 0) - 200, y1 = cl(Math.max(...ys), H, 3 * H) + 200;
  return [x0, y0, x1, y1];
}

function svgBase(cx, classe) {
  const [x0, y0, x1, y1] = cx;
  // y do desenho para cima; no SVG, para baixo
  return sv('svg', { class: 'elev ' + classe, viewBox: `${x0} ${-y1} ${x1 - x0} ${y1 - y0}`, preserveAspectRatio: 'xMidYMid meet' });
}

function desenharOriginal(g, t) {
  for (const d of t.desenho) {
    if (d.t === 'l') g.append(sv('line', { class: 'orig', x1: d.p[0], y1: -d.p[1], x2: d.p[2], y2: -d.p[3] }));
    else if (d.t === 'p') g.append(sv(d.f ? 'polygon' : 'polyline', { class: 'orig', points: d.v.map(v => `${v[0]},${-v[1]}`).join(' ') }));
    else if (d.t === 'c') g.append(sv('circle', { class: 'orig', cx: d.c[0], cy: -d.c[1], r: d.r }));
    else if (d.t === 'a') {
      const rad = (a) => a * Math.PI / 180;
      const P = (a) => `${d.c[0] + d.r * Math.cos(rad(a))},${-(d.c[1] + d.r * Math.sin(rad(a)))}`;
      const varre = ((d.f - d.i) % 360 + 360) % 360;
      g.append(sv('path', { class: 'orig', d: `M${P(d.i)} A${d.r},${d.r} 0 ${varre > 180 ? 1 : 0} 0 ${P(d.f)}` }));
    } else if (d.t === 'x') {
      const tx = sv('text', { class: 'orig-tx', x: d.p[0], y: -d.p[1], 'font-size': Math.max(d.h, 40) });
      if (d.g) tx.setAttribute('transform', `rotate(${-d.g} ${d.p[0]} ${-d.p[1]})`);
      tx.textContent = d.s;
      g.append(tx);
    }
  }
}

function desenharLido(g, t) {
  g.append(sv('line', { class: 'base', x1: -100, y1: 0, x2: t.comprimento + 100, y2: 0 }));
  // banzos por último: ficam por cima da alma
  const ordem = { diagonal: 0, montante: 1, banzo: 2 };
  for (const b of [...t.membros].sort((a, c) => (ordem[a[0]] ?? 0) - (ordem[c[0]] ?? 0))) {
    g.append(sv('line', { class: b[0], x1: b[1], y1: -b[2], x2: b[3], y2: -b[4] }));
  }
}

function figuras(t) {
  const caixa = el('div', { class: 'caixa' });
  const bLado = el('button', { type: 'button', class: sobreposto ? '' : 'ativo', texto: 'Lado a lado', onclick: () => { sobreposto = false; mostrar(t); } });
  const bSob = el('button', { type: 'button', class: sobreposto ? 'ativo' : '', texto: 'Uma sobre a outra', onclick: () => { sobreposto = true; mostrar(t); } });
  caixa.append(el('h3', {}, 'O projeto × o que entrou no modelo', el('span', { class: 'acoes' }, bLado, bSob)));
  const cx = caixaDe(t, true);
  if (sobreposto) {
    const s = svgBase(cx, 'sobreposto');
    const g1 = sv('g'), g2 = sv('g');
    desenharOriginal(g1, t); desenharLido(g2, t);
    s.append(g1, g2);
    caixa.append(el('div', { class: 'figura' }, el('p', { class: 'rotulo', texto: 'O desenho do projetista (apagado) com as barras lidas por cima' }), s));
  } else {
    const s1 = svgBase(cx, 'projeto'), s2 = svgBase(cx, 'lido');
    const g1 = sv('g'), g2 = sv('g');
    desenharOriginal(g1, t); desenharLido(g2, t);
    s1.append(g1); s2.append(g2);
    caixa.append(el('div', { class: 'figura' }, el('p', { class: 'rotulo', texto: 'Como o projeto desenha (a elevação, com a nota dos perfis e o título)' }), s1));
    caixa.append(el('div', { class: 'figura' }, el('p', { class: 'rotulo', texto: 'Como entrou no modelo (o bloco, na mesma escala e posição)' }), s2));
  }
  const cm = t.contagem_membros || {};
  caixa.append(el('div', { class: 'legenda' },
    el('span', {}, el('i', { style: 'background: var(--azul)' }), `banzos (${cm.banzo || 0})`),
    el('span', {}, el('i', { style: 'background: #16a34a' }), `montantes (${cm.montante || 0})`),
    el('span', {}, el('i', { style: 'background: #d97706' }), `diagonais (${cm.diagonal || 0})`),
    el('span', {}, el('i', { style: 'background: var(--verm); height: 1px' }), 'eixo do banzo inferior (h = 0)')));
  return caixa;
}

function mostrar(t) {
  const det = $('#detalhe');
  det.replaceChildren();
  if (!t) { det.append(el('p', { class: 'vazio', texto: 'Escolha uma elevação à esquerda.' })); return; }
  if (t.sem_elevacao) {
    det.append(el('h2', {}, t.nome, el('span', { class: 'sub', texto: 'nome escrito na planta, sem elevação no desenho' })));
    det.append(el('div', { class: 'pendencias' }, el('strong', { texto: 'A conferir com o projeto:' }),
      el('ul', {}, t.pendencias.map(p => el('li', { texto: p })))));
    det.append(el('p', { class: 'vazio', texto: 'Sem a elevação, o programa não sabe a forma nem os perfis desta peça: ela não entra no modelo. Peça ao projetista o desenho dela, ou confirme se o nome se refere a outra elevação.' }));
    return;
  }
  det.append(el('h2', {}, t.nome, el('span', { class: 'sub', texto: `o título pede ${t.qtd_projeto}, o modelo tem ${t.no_modelo}` })));
  det.append(el('div', { class: 'etiquetas' },
    el('span', { texto: `comprimento ${m(t.comprimento)} m` }),
    el('span', { texto: `altura ${m(t.altura)} m` }),
    el('span', { texto: `banzo ${t.banzo || '— sem nota'}` }),
    el('span', { texto: `alma ${t.alma ? (t.alma_mult > 1 ? `${t.alma_mult}× ` : '') + t.alma : '— sem nota'}` }),
    t.marcas_terca.length ? el('span', { texto: `${t.marcas_terca.length} marcas de terça (ST)` }) : null));
  if (t.pendencias.length) {
    det.append(el('div', { class: 'pendencias' }, el('strong', { texto: 'A conferir com o projeto:' }),
      el('ul', {}, t.pendencias.map(p => el('li', { texto: p })))));
  } else {
    det.append(el('div', { class: 'tudo-ok', texto: 'Quantidade igual à do título e todas as cópias cabem no vão da planta (diferença até 20 cm).' }));
  }
  det.append(figuras(t));
  const cx = el('div', { class: 'caixa' });
  cx.append(el('h3', {}, `Onde entrou (${t.colocadas.length})`, t.colocadas.length ? el('span', { class: 'acoes' },
    el('button', { type: 'button', texto: 'Ver todas no 3D', onclick: () => { location.href = url3d(t.nome); } })) : null));
  if (!t.colocadas.length) {
    cx.append(el('p', { class: 'vazio', texto: t.no_modelo ? 'Montada sem medida de encaixe.' : 'Não entrou no modelo: o nome não aparece na planta estrutural.' }));
  } else {
    const tab = el('table', { class: 'tab' }, el('tr', {},
      el('th', { texto: 'Cópia' }), el('th', { texto: 'Onde (eixos do projeto)' }), el('th', { texto: 'Vão na planta' }),
      el('th', { texto: 'Elevação' }), el('th', { texto: 'Diferença' }), el('th', { texto: '' })));
    for (const c of t.colocadas) {
      const dif = c.dif;
      tab.append(el('tr', { class: c.a_conferir ? 'conferir' : '' },
        el('td', { texto: c.conjunto.split('#')[1] ? `#${c.conjunto.split('#')[1]}${c.deitada ? ' (deitada)' : ''}` : c.conjunto }),
        el('td', { texto: c.onde || `(${m(c.ponto[0])}; ${m(c.ponto[1])}) m` }),
        el('td', { class: 'r', texto: `${m(c.vao)} m` }),
        el('td', { class: 'r', texto: `${m(c.elevacao)} m` }),
        el('td', { class: 'r', texto: Math.abs(dif) <= 50 ? 'cabe' : `${dif > 0 ? '+' : '−'}${m(Math.abs(dif))} m` }),
        el('td', {}, el('a', { href: url3d(c.conjunto), texto: 'ver no 3D' }))));
    }
    cx.append(tab);
    cx.append(el('p', { class: 'vazio', texto: '“+” : o vão da planta é maior que a elevação; “−” : menor. As barras das pontas absorvem a diferença; mais de 20 cm é apontado.' }));
  }
  det.append(cx);
  if (t.avisos.length) {
    det.append(el('div', { class: 'caixa' }, el('h3', { texto: 'O que a leitura fez nesta elevação' }),
      el('ul', { class: 'avisos' }, t.avisos.map(a => el('li', { texto: a })))));
  }
}

async function iniciar() {
  $('#btn-voltar').addEventListener('click', () => { if (history.length > 1) history.back(); else location.href = '/'; });
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-3d').addEventListener('click', () => { location.href = url3d(''); });
  $('#btn-dividida').addEventListener('click', () => { location.href = `/dividida?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#busca').addEventListener('input', montarIndice);
  $('#so-conferir').addEventListener('change', montarIndice);
  if (!PROJETO) { $('#detalhe').replaceChildren(el('p', { class: 'vazio', texto: 'Abra esta tela pelo projeto (Desenho 2D ou modelo 3D).' })); return; }
  try {
    const p = await pedir('/api/projetos/' + encodeURIComponent(PROJETO));
    const nome = (p.projeto && p.projeto.nome) || PROJETO;
    $('#nome-projeto').textContent = nome;
    document.title = `Treliças lidas — ${nome}`;
  } catch (e) { /* o nome é só enfeite */ }
  try {
    DADOS = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/trelicas`);
  } catch (e) {
    $('#detalhe').replaceChildren(el('p', { class: 'vazio', texto: `Não foi possível ler as treliças: ${e.message}` }));
    return;
  }
  const ts = DADOS.trelicas || [];
  if (!ts.length) {
    $('#resumo').textContent = '';
    $('#detalhe').replaceChildren(el('p', { class: 'vazio', texto: DADOS.vazio || 'Nenhuma elevação lida neste projeto.' }));
    return;
  }
  const conf = ts.filter(t => t.situacao !== 'ok').length;
  $('#resumo').textContent = `${ts.length} elevações lidas · ${conf ? `${conf} com algo a conferir` : 'nada a conferir'}` +
    (DADOS.montado_em ? ` · montado em ${DADOS.montado_em}` : '');
  if (!ts.some(t => t.nome === ATUAL)) ATUAL = (ts.find(t => t.situacao !== 'ok') || ts[0]).nome;
  montarIndice();
  escolher(ATUAL);
  // só o índice rola até a escolhida (a página fica no topo)
  const b = document.querySelector('#lista button.ativo');
  const ind = $('#indice');
  if (b) ind.scrollTop = Math.max(0, b.offsetTop - ind.offsetTop - ind.clientHeight / 2);
  document.body.dataset.pronto = '1';
}

iniciar();
