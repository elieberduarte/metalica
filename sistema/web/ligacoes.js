/* Biblioteca de ligações e acessórios (nucleo/acessorios.py): à esquerda os tipos por
 * categoria (com quantos exemplos há nas obras detalhadas); à direita o tipo escolhido —
 * desenho com cotas, parâmetros, peças com peso, verificação pela NBR 8800 com os esforços
 * informados e as peças reais das obras que correspondem a ele. Tudo muda na hora: cada
 * mudança de parâmetro remonta pelo servidor (POST /api/ligacoes/montar). */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const PARAMS = new URLSearchParams(location.search);
let CATALOGO = null;
let ATUAL = PARAMS.get('tipo') || '';
let valores = {};
let esforcos = {};
let pedido = 0;

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}
const n = (x, c = 0) => (x === null || x === undefined || x === '') ? '—'
  : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
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

function montarIndice() {
  const lista = $('#lista');
  lista.replaceChildren();
  const filtro = $('#busca').value.trim().toLowerCase();
  for (const c of CATALOGO.categorias) {
    const tipos = CATALOGO.tipos.filter(t => t.categoria === c.id &&
      (!filtro || (t.nome + ' ' + t.descricao + ' ' + t.origem).toLowerCase().includes(filtro)));
    if (!tipos.length) continue;
    lista.append(el('h3', { texto: c.nome }));
    for (const t of tipos) {
      lista.append(el('button', { type: 'button', class: t.id === ATUAL ? 'ativo' : '', title: t.descricao, 'data-tipo': t.id,
        onclick: () => escolher(t.id) }, el('span', { texto: t.nome }), t.exemplos ? el('span', { class: 'n', texto: String(t.exemplos), title: 'peças desse tipo nas obras detalhadas' }) : null));
    }
  }
}

function escolher(id) {
  ATUAL = id;
  valores = {};
  esforcos = {};
  const url = new URL(location.href); url.searchParams.set('tipo', id); history.replaceState(null, '', url);
  montarIndice();
  desenharDetalhe();
}

function campo(p, alvo, aoMudar) {
  const atual = alvo[p.chave] ?? p.padrao;
  let e;
  if (p.opcoes && p.opcoes.length) {
    e = el('select', {}, ...p.opcoes.map(o => el('option', { value: String(o), texto: String(o) === '' ? '(nenhum)' : String(o) })));
    e.value = String(atual ?? '');
  } else {
    e = el('input', { type: 'text', value: atual === null || atual === undefined ? '' : String(atual).replace('.', ',') });
  }
  e.title = p.dica || '';
  e.addEventListener('change', () => { alvo[p.chave] = e.value.replace(',', '.'); aoMudar(); });
  return [el('label', { html: p.rotulo + (p.unidade ? ` <span class="un">(${p.unidade})</span>` : ''), title: p.dica || '' }), e];
}

async function desenharDetalhe() {
  const t = CATALOGO.tipos.find(x => x.id === ATUAL) || CATALOGO.tipos[0];
  ATUAL = t.id;
  const d = $('#detalhe');
  d.replaceChildren(
    el('h2', { texto: t.nome }),
    el('p', { class: 'desc', texto: t.descricao }),
    el('div', { class: 'etiquetas' },
      t.origem ? el('span', { class: /sooro/i.test(t.origem) ? 'sooro' : '', texto: 'Origem: ' + t.origem }) : null,
      t.uso ? el('span', { texto: 'Uso: ' + t.uso }) : null,
      el('span', { texto: t.verifica ? 'Verificação pela NBR 8800' : 'Sem verificação (referência)' })),
    el('div', { class: 'grade' },
      el('div', { class: 'caixa' }, el('h3', { texto: 'Desenho' }), el('div', { class: 'figura', id: 'figura' }, el('span', { class: 'vazio', texto: 'montando…' }))),
      el('div', { class: 'caixa' }, el('h3', { texto: 'Parâmetros' }), el('div', { class: 'params', id: 'params' }))),
    el('div', { class: 'caixa', style: 'margin-top:14px' }, el('h3', { texto: 'Peças' }), el('div', { id: 'pecas' }), el('ul', { class: 'notas', id: 'notas' })),
    t.verifica ? el('div', { class: 'caixa', style: 'margin-top:14px' }, el('h3', { texto: 'Verificação' }),
      el('div', { class: 'esforcos', id: 'esforcos' }), el('div', { id: 'verif' })) : null,
    el('div', { class: 'caixa', style: 'margin-top:14px' }, el('h3', { texto: 'Nas obras' }), el('div', { id: 'obras' }, el('span', { class: 'vazio', texto: 'procurando nas obras detalhadas…' }))));
  const ps = $('#params');
  for (const p of t.parametros) ps.append(...campo(p, valores, montar));
  if (!t.parametros.length) ps.append(el('span', { class: 'vazio', texto: 'Sem parâmetros.' }));
  const es = $('#esforcos');
  if (es) {
    for (const p of t.esforcos) {
      const [lab, inp] = campo(p, esforcos, montar);
      es.append(el('label', {}, lab.firstChild ? lab.textContent : p.rotulo, inp));
    }
  }
  await montar();
  carregarObras(t.id);
}

async function montar() {
  const meu = ++pedido;
  let r;
  try {
    r = await pedir('/api/ligacoes/montar', { tipo: ATUAL, parametros: valores, esforcos });
  } catch (e) {
    if (meu !== pedido) return;
    $('#figura').replaceChildren(el('div', { class: 'aviso-topo', texto: 'Não foi possível montar: ' + e.message }));
    return;
  }
  if (meu !== pedido) return;
  $('#figura').innerHTML = r.svg;
  const tb = el('table', { class: 'tab' },
    el('thead', {}, el('tr', {}, ...['Peça', 'Medida (mm)', 'Furos', 'Qtd', 'Material', 'kg/un', 'kg'].map(h => el('th', { texto: h })))),
    el('tbody', {}, ...r.pecas.map(p => el('tr', {},
      el('td', { texto: p.descricao + (p.nota ? ' — ' + p.nota : '') }), el('td', { texto: p.medida }), el('td', { texto: p.furos }),
      el('td', { class: 'r', texto: n(p.qtd) }), el('td', { texto: p.material }),
      el('td', { class: 'r', texto: p.peso_unit ? n(p.peso_unit, 2) : '' }), el('td', { class: 'r', texto: p.peso ? n(p.peso, 2) : '' })))),
    el('tfoot', {}, el('tr', {}, el('td', { colspan: '6', texto: 'Aço (sem fixadores e solda)' }), el('td', { class: 'r', texto: n(r.peso_kg, 2) }))));
  $('#pecas').replaceChildren(r.pecas.length ? tb : el('span', { class: 'vazio', texto: 'Tabela de consulta: nada a fabricar.' }));
  $('#notas').replaceChildren(...(r.notas || []).map(t => el('li', { texto: t })));
  const v = r.verificacao;
  const alvo = $('#verif');
  if (alvo && v) {
    const ap = v.razao || 0;
    const governa = (v.verificacoes || []).reduce((a, b) => (b.razao > (a ? a.razao : -1) ? b : a), null);
    alvo.replaceChildren(
      el('div', { class: 'resumo-verif' },
        el('span', { class: 'selo ' + (v.ok ? 'ok' : 'nao'), texto: v.indeterminada ? 'não verificada' : v.ok ? 'atende' : 'não atende' }),
        el('span', { texto: `aproveitamento ${n(ap * 100, 0)} %` + (governa ? ` · governa: ${governa.titulo}` : '') }),
        el('div', { class: 'barra-ap' + (v.ok ? '' : ' reprova') }, el('i', { style: `width:${Math.min(ap, 1.35) / 1.35 * 100}%` }), el('span', { class: 'lim', style: `left:${100 / 1.35}%` }))),
      el('div', { class: 'contas', html: r.verificacao_html || '' }));
  }
}

async function carregarObras(id) {
  const alvo = $('#obras');
  let ex = [];
  try { ex = (await pedir('/api/ligacoes/exemplos?tipo=' + encodeURIComponent(id))).exemplos || []; } catch (e) { /* segue vazio */ }
  if (id !== ATUAL) return;
  if (!ex.length) {
    alvo.replaceChildren(el('span', { class: 'vazio', texto: 'Nenhuma peça deste tipo nas obras detalhadas desta pasta de dados. As obras entram aqui depois de Detalhar peças e conjuntos.' }));
    return;
  }
  alvo.replaceChildren(el('table', { class: 'tab' },
    el('thead', {}, el('tr', {}, ...['Obra', 'Nome', 'Perfil', 'Medida', 'Furos', 'Parafusos', 'Qtd', 'kg/un'].map(h => el('th', { texto: h })))),
    el('tbody', {}, ...ex.map(x => el('tr', {},
      el('td', {}, el('a', { href: `/materiais?projeto=${encodeURIComponent(x.projeto)}`, texto: x.obra, title: 'Abrir a lista de materiais da obra' })),
      el('td', { texto: x.nome }), el('td', { texto: x.perfil }), el('td', { texto: x.medida }), el('td', { texto: x.furos }),
      el('td', { texto: x.parafusos }), el('td', { class: 'r', texto: n(x.qtd) }), el('td', { class: 'r', texto: n(x.peso, 2) }))))));
}

document.addEventListener('DOMContentLoaded', async () => {
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-voltar').addEventListener('click', () => { if (history.length > 1) history.back(); else location.href = '/'; });
  $('#busca').addEventListener('input', montarIndice);
  try { CATALOGO = await pedir('/api/ligacoes'); } catch (e) {
    $('#detalhe').replaceChildren(el('div', { class: 'aviso-topo', texto: 'Não foi possível ler a biblioteca: ' + e.message }));
    return;
  }
  if (!CATALOGO.tipos.some(t => t.id === ATUAL)) ATUAL = CATALOGO.tipos[0].id;
  montarIndice();
  desenharDetalhe();
  document.body.dataset.pronto = '1';
});
