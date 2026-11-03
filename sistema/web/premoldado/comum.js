/* Pré-moldado (em desenvolvimento): o que as telas do pré-moldado usam em comum — montar elementos,
 * números em pt-BR, pedir ao servidor, a tabela das verificações com a memória e o botão do tema. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);

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
const num = (v, c = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—'
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  let j = {};
  try { j = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function verificacoes(r) {
  const tab = el('table', { class: 'tab' }, el('tr', {}, ['Verificação', 'Solicitante', 'Resistente', 'Razão', ''].map(t => el('th', { texto: t }))));
  for (const v of r.verificacoes) {
    const linha = el('tr', {}, el('td', {}, el('div', { html: v.titulo }), el('div', { class: 'mem', texto: v.norma })),
      el('td', { class: 'r', texto: `${num(v.Sd)} ${v.unidade}` }), el('td', { class: 'r', texto: `${num(v.Rd)} ${v.unidade}` }),
      el('td', { class: 'r', texto: num(v.razao) }), el('td', { class: v.ok ? 'ok' : 'nao', texto: v.ok ? 'ok' : 'não passa' }));
    tab.append(linha);
    if (v.passos && v.passos.length) {
      tab.append(el('tr', {}, el('td', { colspan: 5 }, el('details', {}, el('summary', { texto: 'memória de cálculo' }),
        v.passos.map(p => el('div', { class: 'passo', html: `${p.texto}: ${p.formula || ''} ${p.conta ? '= ' + p.conta : ''} → <b>${p.valor || ''}</b> <i>${p.norma || ''}</i>` }))))));
    }
    if (v.observacao) tab.append(el('tr', {}, el('td', { colspan: 5, class: 'mem', html: '⚠ ' + v.observacao })));
  }
  return tab;
}

function ligarTema() {
  const b = $('#btn-tema');
  if (!b) return;
  b.addEventListener('click', () => {
    const r = document.documentElement, novo = (r.getAttribute('data-tema') || 'claro') === 'escuro' ? 'claro' : 'escuro';
    r.setAttribute('data-tema', novo); try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* */ }
  });
}
