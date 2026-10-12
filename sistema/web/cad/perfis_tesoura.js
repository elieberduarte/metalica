// "Perfis da tesoura" (11/10/2026, pedido do usuário): o projetista configura sozinho os perfis de cada barra da
// tesoura — sem o Claude. Na elevação de um eixo, o botão "Perfis…" abre o painel: seleciona as barras (por função,
// por trecho entre eixos, ou clicando / passando uma janela na elevação) e dá a elas o perfil, o arranjo (simples,
// composto = dois U de costas, caixa = dois U de boca com boca), o vão entre os dois perfis e a boca (automática ou
// virada), com o croqui da seção como o da legenda do projeto. Vale para o tipo inteiro (todas as T1, em todos os
// eixos) ou só para esta tesoura, que vira outro tipo (T1A) — a mesma regra do "Tesoura…".
//
// As barras ficam no elemento "trelica" da implantação: desenho.barras[i] = [u0, v0, u1, v1, papel, perfil, arranjo,
// vão, virar] (nucleo3d/de_planta_estrutura._trelica lê os quatro últimos). Os métodos entram na Montagem.

import { Ferramenta } from './ferramentas.js';
import { ComandoAlterar } from './nucleo/comandos.js';
import { transformar } from './nucleo/desenho2d.js';

const ARRANJOS = [['', 'simples (um perfil)'], ['composto', 'composto — dois U de costas'], ['caixa', 'caixa — dois U de boca com boca']];
const FUNCOES = [['banzo_sup', 'banzo de cima'], ['banzo_inf', 'banzo de baixo'], ['montante', 'montantes'], ['diagonal', 'diagonais']];
const natural = (a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true, sensitivity: 'base' });

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

/** As medidas do perfil pelo nome ("Ue 100×50×17×2,25" → {fam: 'Ue', d: 100, bf: 50, c: 17, t: 2.25}); null se não é U. */
export function medidasDoPerfil(nome) {
  const l = /^\s*L\s*([\d.,]+)(?:\s*"[^×x]*)?\s*[x×]\s*([\d.,]+)/i.exec(String(nome || ''));
  if (l) { const b = parseFloat(l[1].replace(',', '.')), t = parseFloat(l[2].replace(',', '.')); return { fam: 'L', d: b, bf: b, c: 0, t }; }
  const m = /^\s*(Ue|U)\s*([\d.,]+)\s*[x×]\s*([\d.,]+)(?:\s*[x×]\s*([\d.,]+))?(?:\s*[x×]\s*([\d.,]+))?/i.exec(String(nome || ''));
  if (!m) return null;
  const n = (s) => (s == null ? null : parseFloat(String(s).replace(',', '.')));
  const fam = /e/i.test(m[1]) ? 'Ue' : 'U';
  const nums = [n(m[2]), n(m[3]), n(m[4]), n(m[5])].filter(x => x != null);
  return fam === 'Ue' ? { fam, d: nums[0], bf: nums[1], c: nums.length >= 4 ? nums[2] : 0, t: nums[nums.length - 1] }
    : { fam, d: nums[0], bf: nums[1], c: 0, t: nums[2] || 2 };
}

/**
 * O croqui da seção (SVG), como o da legenda do projeto: o banzo composto "] [" com o vão entre as costas; a caixa
 * com as bocas uma para a outra; o simples, o U com a boca para o miolo (banzo) ou atravessado ao plano (alma).
 * Horizontal = fora do plano da tesoura; vertical = no plano.
 */
export function croquiDaSecao(perfil, arranjo, vao, funcao) {
  const md = medidasDoPerfil(perfil);
  const W = 220, H = 150;
  const svg = (corpo) => `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" style="background:var(--campo-fundo);border:1px solid var(--borda);border-radius:4px">${corpo}</svg>`;
  if (!md) return svg(`<text x="110" y="78" text-anchor="middle" font-size="11" fill="currentColor">${perfil ? 'perfil sem croqui' : 'escolha o perfil'}</text>`);
  // U em coordenadas da seção: a alma em x = 0, as abas para +x (a boca), de altura d (em y)
  const U = (d, bf, c) => [[0, -d / 2], [bf, -d / 2], [bf, -d / 2 + c], [bf, -d / 2], [0, -d / 2], [0, d / 2], [bf, d / 2], [bf, d / 2 - c], [bf, d / 2]];
  // a cantoneira: as duas abas, uma no plano e outra atravessada (como fica soldada na lateral do U)
  const forma = md.fam === 'L' ? [[md.bf, md.d / 2], [0, md.d / 2], [0, -md.d / 2]] : U(md.d, md.bf, md.c || 0);
  const pecas = [];      // [pts, ângulo (graus), deslocamento x, deslocamento y]
  const v = Number(vao) > 0 ? Number(vao) : 127;
  if (arranjo === 'composto') {
    pecas.push([forma, 0, v / 2, 0], [forma, 180, -v / 2, 0]);                // de costas, a boca para fora
  } else if (arranjo === 'caixa') {
    pecas.push([forma, 90, 0, -md.bf], [forma, -90, 0, md.bf]);                // de boca, lado a lado no plano
  } else if (String(funcao || '').startsWith('banzo')) {
    pecas.push([forma, funcao === 'banzo_sup' ? 90 : -90, 0, 0]);              // a boca para o miolo
  } else {
    pecas.push([forma, -90, 0, 0]);                                           // a alma: a altura atravessa o plano
  }
  const todos = [];
  const pol = pecas.map(([pts, ang, dx, dy]) => {
    const r = ang * Math.PI / 180, co = Math.cos(r), se = Math.sin(r);
    const q = pts.map(([x, y]) => [x * co - y * se + dx, x * se + y * co + dy]);
    todos.push(...q);
    return q;
  });
  const xs = todos.map(p => p[0]), ys = todos.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const k = Math.min((W - 50) / Math.max(1, x1 - x0), (H - 50) / Math.max(1, y1 - y0));
  const T = ([x, y]) => [W / 2 + (x - (x0 + x1) / 2) * k, H / 2 + 6 - (y - (y0 + y1) / 2) * k];
  let corpo = `<line x1="${W / 2}" y1="10" x2="${W / 2}" y2="${H - 10}" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="4 3"/>`;
  for (const q of pol) corpo += `<polyline fill="none" stroke="#f59e0b" stroke-width="2" points="${q.map(T).map(p => p.join(',')).join(' ')}"/>`;
  if (arranjo === 'composto') {
    const a = T([-v / 2, y1]), b = T([v / 2, y1]);
    corpo += `<line x1="${a[0]}" y1="${a[1] - 10}" x2="${b[0]}" y2="${b[1] - 10}" stroke="currentColor" stroke-width="1"/>` +
      `<text x="${(a[0] + b[0]) / 2}" y="${a[1] - 14}" text-anchor="middle" font-size="11" fill="currentColor">${Math.round(v)}</text>`;
  }
  corpo += `<text x="6" y="${H - 6}" font-size="10" fill="currentColor" fill-opacity=".6">plano da tesoura ┆ fora do plano ↔</text>`;
  return svg(corpo);
}

const CORES = ['#f59e0b', '#22c55e', '#3b82f6', '#ec4899', '#a855f7', '#14b8a6', '#ef4444', '#84cc16', '#f97316', '#06b6d4', '#eab308', '#8b5cf6'];
const NOME_FN = { banzo_sup: 'banzo de cima', banzo_inf: 'banzo de baixo', montante: 'montante', diagonal: 'diagonal', extremidade: 'ponta' };

/** kg/m do perfil: o do catálogo pelo nome; senão pela seção (linha média × espessura × 7850 kg/m³) — aproximado. */
export function massaPorMetro(nome, dados = {}) {
  const c = dados[nome];
  if (c && +c.massa > 0) return { kg: +c.massa, aprox: false };
  const m = medidasDoPerfil(nome);
  if (!m || !(m.t > 0)) return null;
  const t = m.t;
  const A = m.fam === 'L' ? t * (2 * m.bf - t) : t * ((m.d - t) + 2 * (m.bf - t) + (m.c > 0 ? 2 * (m.c - t / 2) : 0));
  return { kg: A * 7.85e-3, aprox: true };
}

/** O perfil que a barra usa: o dela (o painel, a legenda) ou, sem perfil próprio, o do tipo pela função. */
export function perfilDaBarra(b, perfisDoTipo = {}) {
  if (b[5]) return { perfil: b[5], arranjo: b[6] || '', doTipo: false };
  const fn = b[4] === 'banzo_sup' ? 'banzo_sup' : (b[4] === 'banzo_inf' || b[4] === 'extremidade') ? 'banzo_inf' : 'diagonal';
  return { perfil: (perfisDoTipo || {})[fn] || '?', arranjo: '', doTipo: true };
}
const chavePerfil = (p) => `${p.perfil}|${p.arranjo}|${p.doTipo ? 1 : ''}`;

/** A tabela de uma tesoura: por função, perfil e arranjo — barras, comprimento (m, os dois perfis do duplo) e kg. */
export function tabelaDaTesoura(barras, perfisDoTipo = {}, dados = {}) {
  const linhas = new Map();
  for (const b of barras || []) {
    const { perfil, arranjo, doTipo } = perfilDaBarra(b, perfisDoTipo);
    const fn = b[4] === 'extremidade' ? 'banzo_inf' : b[4];
    const k = `${fn}|${perfil}|${arranjo}`;
    const L = Math.hypot(b[2] - b[0], b[3] - b[1]) / 1000 * (arranjo === 'composto' || arranjo === 'caixa' ? 2 : 1);
    const l = linhas.get(k) || { funcao: fn, perfil, arranjo, doTipo, n: 0, m: 0 };
    l.n++; l.m += L; linhas.set(k, l);
  }
  const ordem = ['banzo_sup', 'banzo_inf', 'montante', 'diagonal'];
  const out = [...linhas.values()].sort((x, y) => (ordem.indexOf(x.funcao) - ordem.indexOf(y.funcao)) || natural(x.perfil, y.perfil));
  for (const l of out) { const mm = massaPorMetro(l.perfil, dados); l.kg = mm ? mm.kg * l.m : null; l.aprox = !!(mm && mm.aprox); }
  return out;
}

/** Na elevação com o painel aberto: o clique pega a barra (Shift ou Ctrl soma); a janela pega as que estão dentro. */
class SelecionarBarras extends Ferramenta {
  static id = 'perfis-sel'; static nome = 'Selecionar barras da tesoura'; static grupo = 'montagem';
  static dica = 'Perfis: clique nas barras da tesoura (Shift soma) ou passe uma janela · Esc fecha o painel';
  reiniciar() { super.reiniciar(); this.a = null; this.editor.tela.regiao = null; }
  desativar() { super.desativar(); this.editor.tela.regiao = null; this.editor.tela.pedirQuadro(); }
  onMover(p) { if (this.a) { this.editor.tela.regiao = [this.a, p]; this.editor.tela.pedirQuadro(); } }
  onPonto(p, ev) {
    const m = window.montagem;
    const soma = !!(ev && (ev.shiftKey || ev.ctrlKey));
    const k = m._barraSob(p);
    if (k) { m._selecionarBarras([k], soma ? 'alternar' : 'trocar'); return; }
    if (!soma) m._selecionarBarras([], 'trocar');
  }
  onSoltar(p, ev) {
    const de = ev && ev.arrasto ? this.editor.tela.paraMundo(ev.arrasto.de) : null;
    if (!de) return;
    this.editor.tela.regiao = null;
    const caixa = [[Math.min(de[0], p[0]), Math.min(de[1], p[1])], [Math.max(de[0], p[0]), Math.max(de[1], p[1])]];
    window.montagem._selecionarBarras(window.montagem._barrasNaJanela(caixa), ev && (ev.shiftKey || ev.ctrlKey) ? 'somar' : 'trocar');
  }
  cancelar() { window.montagem.fecharPerfis(); }
}

export class MetodosPerfisTesoura {
  /** As tesouras (elementos "trelica" da implantação) no eixo da elevação `q`. */
  _tesourasDoEixo(q) {
    const qi = this._quadroImplantacao();
    return [...this.cad.doc.entidades.values()].filter(e => {
      const a = e.atributos || {};
      return a.elemento === 'trelica' && qi && a.quadro === qi.id && a.eixo === q.eixo && a.familia_eixo === q.familia;
    });
  }

  /** As linhas da elevação aberta que desenham as barras: [{id do elemento, i da barra, a, b}] */
  _linhasDasBarras() {
    const pf = this._pf;
    if (!pf) return [];
    // a pintura chama a cada quadro: as linhas ficam guardadas até o desenho mudar (não varrer o documento por quadro)
    const doc = this.cad.doc;
    if (this._docLinhasOuvido !== doc) {
      this._docLinhasOuvido = doc;
      doc.aoMudar(() => { this._cacheLinhas = null; });
    }
    const c = this._cacheLinhas;
    if (c && c.doc === doc && c.q === pf.q.id) return c.linhas;
    const out = [];
    this._cacheLinhas = { doc, q: pf.q.id, linhas: out };
    for (const e of doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo === 'linha' && a.quadro === pf.q.id && a.elemento_ref && Number.isInteger(a.barra)) out.push({ ref: a.elemento_ref, i: a.barra, a: e.a, b: e.b });
    }
    return out;
  }

  _barraSob(p) {
    const tol = 6 * this.cad.tela.mmPorPixel;
    let melhor = null, dm = Infinity;
    for (const l of this._linhasDasBarras()) {
      const dx = l.b[0] - l.a[0], dy = l.b[1] - l.a[1], L2 = dx * dx + dy * dy;
      const t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - l.a[0]) * dx + (p[1] - l.a[1]) * dy) / L2)) : 0;
      const d = Math.hypot(p[0] - l.a[0] - dx * t, p[1] - l.a[1] - dy * t);
      if (d <= tol && d < dm) { dm = d; melhor = `${l.ref}:${l.i}`; }
    }
    return melhor;
  }

  _barrasNaJanela(caixa) {
    const [[x0, y0], [x1, y1]] = caixa;
    const dentro = (p) => p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
    return this._linhasDasBarras().filter(l => dentro(l.a) && dentro(l.b)).map(l => `${l.ref}:${l.i}`);
  }

  _selecionarBarras(chaves, modo = 'trocar') {
    const pf = this._pf;
    if (!pf) return;
    if (modo === 'trocar') pf.sel = new Set(chaves);
    else for (const k of chaves) { if (modo === 'alternar' && pf.sel.has(k)) pf.sel.delete(k); else pf.sel.add(k); }
    this._encherPerfis();
    this.cad.tela.pedirQuadro();
  }

  /** As barras selecionadas: [{e (o elemento), i, b (a barra)}] */
  _barrasSelecionadas() {
    const pf = this._pf, out = [];
    if (!pf) return out;
    for (const k of pf.sel) {
      const [id, i] = k.split(':');
      const e = this.cad.doc.get(id);
      const b = e && ((e.atributos || {}).desenho || {}).barras && e.atributos.desenho.barras[+i];
      if (b) out.push({ e, i: +i, b });
    }
    return out;
  }

  /** Abre o painel "Perfis da tesoura" na elevação `q`. */
  async abrirPerfis(q) {
    const tes = this._tesourasDoEixo(q);
    if (!tes.length) { this.cad.aviso(`Nenhuma tesoura lançada no eixo ${q.eixo}: cole o desenho na elevação e use "Tesoura…" primeiro.`, 'atencao', 9000); return; }
    // a elevação desenhada antes do painel não tem o número da barra em cada linha: refaz
    const semNumero = [...this.cad.doc.entidades.values()].some(e => { const a = e.atributos || {}; return e.tipo === 'linha' && a.quadro === q.id && a.elemento_ref && !Number.isInteger(a.barra); });
    if (semNumero) await this.refazerQuadrosDaObra([q]);
    if (!this.cad.ferramentas.has('perfis-sel')) this.cad.ferramentas.set('perfis-sel', new SelecionarBarras(this.cad));
    this._pf = { q, sel: new Set() };
    if (!this.painelPerfis) {
      this.painelPerfis = el('aside', { class: 'painel-leitura painel-perfis', id: 'painel-perfis' });
      this.palco.append(this.painelPerfis);
    }
    this.painelPerfis.hidden = false;
    this.cad.ativarFerramenta('perfis-sel');
    // a elevação à esquerda do painel (360 px na direita): a caixa enquadrada se estende pela largura do painel
    const larg = this.cad.tela.canvas ? this.cad.tela.canvas.clientWidth : 1200;
    const extra = q.w * 380 / Math.max(300, larg - 380);
    this.cad.tela.enquadrar([[q.x, q.y - q.h], [q.x + q.w + extra, q.y]], 0.04);
    this._encherPerfis();
    this.cad.dica('Perfis da tesoura: selecione as barras (botões, clique ou janela) e dê o perfil, o arranjo e a boca. Esc fecha.');
  }

  fecharPerfis() {
    this._pf = null;
    if (this.painelPerfis) this.painelPerfis.hidden = true;
    if (this.cad.ferramenta && this.cad.ferramenta.constructor.id === 'perfis-sel') this.cad.ativarFerramenta('selecionar');
    this.cad.tela.pedirQuadro();
  }

  /** Seleciona pela função (banzo de cima…) ou pelo trecho entre dois eixos que cruzam a elevação. */
  _selecionarPor({ funcao = null, trecho = null } = {}) {
    const pf = this._pf;
    const linhas = this._linhasDasBarras();
    const chaves = [];
    for (const l of linhas) {
      const e = this.cad.doc.get(l.ref), b = e && e.atributos.desenho.barras[l.i];
      if (!b) continue;
      if (funcao && !(b[4] === funcao || (funcao === 'banzo_inf' && b[4] === 'extremidade'))) continue;
      if (trecho) {
        const m = this._paraReal(pf.q, [(l.a[0] + l.b[0]) / 2, (l.a[1] + l.b[1]) / 2])[0];
        if (m < trecho[0] - 1 || m > trecho[1] + 1) continue;
      }
      chaves.push(`${l.ref}:${l.i}`);
    }
    this._selecionarBarras(chaves, 'trocar');
  }

  async _encherPerfis() {
    const pf = this._pf, P = this.painelPerfis;
    if (!pf || !P) return;
    const tes = this._tesourasDoEixo(pf.q);
    const marcas = [...new Set(tes.map(t => t.atributos.marca))].sort(natural);
    const sel = this._barrasSelecionadas();
    const igual = (f) => { const vs = [...new Set(sel.map(f))]; return vs.length === 1 ? vs[0] : null; };
    const perfil0 = igual(s => s.b[5] || ''), arr0 = igual(s => s.b[6] || ''), vao0 = igual(s => (s.b[7] == null || s.b[7] === '' ? '' : String(s.b[7]))),
      virar0 = igual(s => (s.b[8] ? '1' : ''));
    const funcao0 = igual(s => s.b[4]);
    // a sugestão da legenda do projeto para as barras selecionadas (a mesma para todas e diferente do que já têm)
    const sug = pf.sugestao && sel.length ? igual(s => { const x = pf.sugestao.porBarra.get(`${s.e.id}:${s.i}`); return x ? `${x.perfil}|${x.arranjo}` : '-'; }) : null;
    const sugerido = sug && sug !== '-' && sel.some(s => `${s.b[5] || ''}|${s.b[6] || ''}` !== sug) ? sug.split('|') : null;
    const cat = this._catPerfis || (this._catPerfis = await this.cad.catalogoEstrutura().catch(() => ({ perfis: [], grupos: [] })));
    const nomes = (cat.grupos || []).flatMap(([, ns]) => ns).filter(n => /^(Ue|U|L|2L)\s/i.test(n));
    const lista = el('datalist', { id: 'perfis-catalogo' }, ...nomes.map(n => el('option', { value: n })));
    const perfil = el('input', { type: 'text', id: 'perfis-perfil', list: 'perfis-catalogo', value: perfil0 || '', spellcheck: 'false',
      placeholder: sel.length && perfil0 === null ? 'vários' : 'o do tipo', title: 'O perfil (do catálogo ou escrito: Ue 100×50×17×2,25)' });
    const arranjo = el('select', { id: 'perfis-arranjo' }, el('option', { value: '-', texto: '— não mudar —' }), ...ARRANJOS.map(([v, t]) => el('option', { value: v, texto: t })));
    arranjo.value = arr0 === null ? '-' : arr0;
    if (sugerido) { perfil.value = sugerido[0]; arranjo.value = sugerido[1]; }
    const vao = el('input', { type: 'text', id: 'perfis-vao', value: vao0 || '', size: 6, placeholder: 'altura da alma', title: 'O vão entre os dois perfis do composto (mm); vazio = a altura do perfil da alma' });
    const boca = el('select', { id: 'perfis-boca' }, el('option', { value: '-', texto: '— não mudar —' }), el('option', { value: '', texto: 'automática (para o miolo)' }), el('option', { value: '1', texto: 'virada' }));
    boca.value = virar0 === null ? '-' : virar0;
    for (const i of [perfil, vao]) i.addEventListener('keydown', ev => ev.stopPropagation());
    const croqui = el('div', { class: 'perfis-croqui' });
    const desenharCroqui = () => { croqui.innerHTML = croquiDaSecao(perfil.value || perfil0 || '', arranjo.value === '-' ? (arr0 || '') : arranjo.value, vao.value, funcao0 || ''); };
    for (const c of [perfil, arranjo, vao]) c.addEventListener('input', desenharCroqui), c.addEventListener('change', desenharCroqui);
    desenharCroqui();
    // os trechos entre os eixos que cruzam a elevação
    const cruz = this._cruzamDaElevacao(pf.q);
    const trechos = el('select', { id: 'perfis-trecho' }, el('option', { value: '', texto: 'trecho entre eixos…' }),
      ...cruz.slice(1).map((c, i) => el('option', { value: `${cruz[i].u}|${c.u}`, texto: `${cruz[i].nome}–${c.nome}` })));
    trechos.addEventListener('change', () => { if (trechos.value) { const [a, b] = trechos.value.split('|').map(Number); this._selecionarPor({ trecho: [Math.min(a, b), Math.max(a, b)] }); } });
    const resumo = new Map();
    for (const s of sel) { const k = `${NOME_FN[s.b[4]] || s.b[4]} · ${s.b[5] || 'o do tipo'}${s.b[6] ? ' ' + s.b[6] : ''}`; resumo.set(k, (resumo.get(k) || 0) + 1); }
    const marcaSel = [...new Set(sel.map(s => s.e.atributos.marca))];
    const usadas = new Set([...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica').map(e => e.atributos.marca));
    const nova = (m) => { let s = 'A'; while (usadas.has(m + s)) s = String.fromCharCode(s.charCodeAt(0) + 1); return m + s; };
    P.replaceChildren(
      el('div', { class: 'painel-leitura-topo' }, el('b', {}, `Perfis da tesoura · eixo ${pf.q.eixo}`),
        el('button', { type: 'button', class: 'quadro-tirar', title: 'Fechar (Esc)', onclick: () => this.fecharPerfis() }, '×')),
      el('div', { class: 'explica', texto: `Tipos neste eixo: ${marcas.join(', ')}. Selecione as barras: pelos botões, clicando na elevação (Shift soma) ou passando uma janela.` }),
      el('div', { class: 'perfis-botoes' }, ...FUNCOES.map(([f, t]) => el('button', { type: 'button', 'data-funcao': f, onclick: () => this._selecionarPor({ funcao: f }) }, t)),
        el('button', { type: 'button', onclick: () => this._selecionarPor({}) }, 'todas'), trechos),
      el('div', { class: 'perfis-sel', id: 'perfis-sel' }, sel.length ? `${sel.length} barra(s) selecionada(s): ` + [...resumo.entries()].map(([k, v]) => `${v}× ${k}`).join('; ') : 'Nenhuma barra selecionada.'),
      this._blocoSugestao(),
      sugerido ? el('div', { class: 'perfis-sugerido', id: 'perfis-sugerido', texto: `Preenchido pela legenda do projeto: ${sugerido[0]}${sugerido[1] ? ' · ' + sugerido[1] : ''}. Confira e aplique.` }) : null,
      el('label', {}, 'Perfil ', perfil), lista,
      el('label', {}, 'Arranjo ', arranjo),
      el('label', {}, 'Vão entre os perfis (mm) ', vao),
      el('label', {}, 'Boca ', boca),
      croqui,
      this._legendaPerfis(tes),
      this._tabelasDasTesouras(tes, cat.dados || {}),
      el('div', { class: 'painel-leitura-pe' },
        el('button', { type: 'button', class: 'primario', id: 'perfis-aplicar-todas', disabled: !sel.length,
          onclick: () => this._aplicarPerfis(true, { perfil, arranjo, vao, boca }) }, marcaSel.length ? `Aplicar a todas as ${marcaSel.join(', ')}` : 'Aplicar a todas'),
        el('button', { type: 'button', id: 'perfis-aplicar-so', disabled: !sel.length,
          onclick: () => this._aplicarPerfis(false, { perfil, arranjo, vao, boca }) }, marcaSel.length ? `Só neste eixo (vira ${marcaSel.map(nova).join(', ')})` : 'Só neste eixo')));
  }

  /** A barra `b` de um elemento corresponde a qual barra do outro elemento do mesmo tipo (a mesma, ou a espelhada). */
  _barraCorrespondente(b, vaoA, barrasB, vaoB) {
    const tol = 30;
    const perto = (x, y) => Math.abs(x - y) <= tol;
    for (const espelho of [false, true]) {
      const f = (u) => (espelho ? vaoA - u : u) * (vaoB / (vaoA || 1));
      for (let j = 0; j < barrasB.length; j++) {
        const c = barrasB[j];
        if (c[4] !== b[4]) continue;
        const a0 = [f(b[0]), b[1]], a1 = [f(b[2]), b[3]];
        if ((perto(a0[0], c[0]) && perto(a0[1], c[1]) && perto(a1[0], c[2]) && perto(a1[1], c[3])) ||
            (perto(a0[0], c[2]) && perto(a0[1], c[3]) && perto(a1[0], c[0]) && perto(a1[1], c[1]))) return j;
      }
    }
    return -1;
  }

  /** Aplica o perfil, o arranjo, o vão e a boca às barras selecionadas: em todas as tesouras do tipo (todas as T1, nos
   *  outros eixos também) ou só nas deste eixo, que viram um tipo novo (T1A). */
  async _aplicarPerfis(todas, campos, selecao = null) {
    const sel = selecao || this._barrasSelecionadas();
    if (!sel.length) return;
    const mud = {};
    const novo = (b, s) => {
      const n = [...b];
      while (n.length < 9) n.push(n.length === 7 ? null : '');
      if (typeof campos === 'function') { const v = campos(s); if (v) { n[5] = v.perfil; n[6] = v.arranjo; } return n; }
      if (campos.perfil.value.trim()) n[5] = campos.perfil.value.trim();
      if (campos.arranjo.value !== '-') n[6] = campos.arranjo.value;
      const v = parseFloat(String(campos.vao.value).replace(',', '.'));
      n[7] = campos.vao.value.trim() === '' ? (campos.arranjo.value === '-' ? n[7] : null) : (v > 0 ? v : n[7]);
      if (campos.boca.value !== '-') n[8] = campos.boca.value === '1' ? 1 : '';
      return n;
    };
    const barrasDe = (e) => (mud[e.id] ? mud[e.id].atributos.desenho.barras : e.atributos.desenho.barras);
    const mexer = (e, j, b, s) => {
      if (!mud[e.id]) mud[e.id] = { atributos: JSON.parse(JSON.stringify(e.atributos)) };
      mud[e.id].atributos.desenho.barras[j] = novo(b, s);
    };
    const doc = this.cad.doc;
    const trels = [...doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica');
    let n = 0;
    if (todas) {
      for (const s of sel) {
        const irmas = trels.filter(t => t.atributos.marca === s.e.atributos.marca);
        for (const t of irmas) {
          const j = t === s.e ? s.i : this._barraCorrespondente(s.b, s.e.atributos.desenho.vao, barrasDe(t), t.atributos.desenho.vao);
          if (j >= 0) { mexer(t, j, barrasDe(t)[j], s); n++; }
        }
      }
    } else {
      // só neste eixo: as tesouras com barra selecionada viram um tipo novo (a marca + A, B…)
      const usadas = new Set(trels.map(t => t.atributos.marca));
      const novaMarca = new Map();
      for (const s of sel) {
        const m = s.e.atributos.marca;
        if (!novaMarca.has(m)) { let x = 'A'; while (usadas.has(m + x)) x = String.fromCharCode(x.charCodeAt(0) + 1); novaMarca.set(m, m + x); usadas.add(m + x); }
        mexer(s.e, s.i, s.b, s); n++;
        mud[s.e.id].atributos.marca = novaMarca.get(m);
      }
      for (const [id, c] of Object.entries(mud)) {
        for (const r of doc.entidades.values()) if ((r.atributos || {}).rotulo_de === id && r.tipo === 'texto') mud[r.id] = { texto: c.atributos.marca };
      }
    }
    if (!Object.keys(mud).length) return;
    // o tipo guardado (m.tipos) acompanha: é dele que o "Tesoura…" tira o desenho das outras de mesma marca
    const tipos = { ...(this.m.tipos || {}) };
    for (const c of Object.values(mud)) {
      const at = c.atributos;
      if (!at || !at.marca) continue;
      const velho = tipos[at.marca] || Object.values(tipos).find(t => t && t.desenho && t.desenho.vao === at.desenho.vao) || {};
      tipos[at.marca] = { ...velho, desenho: at.desenho };
    }
    this.m.tipos = tipos;
    this.cad.executar(new ComandoAlterar(mud, typeof campos === 'function' ? 'Perfis pela legenda do projeto'
      : todas ? 'Perfis da tesoura (todas do tipo)' : 'Perfis da tesoura (só neste eixo)'));
    await this.cad.salvar({ avisar: false });
    const marcas = [...new Set(Object.values(mud).map(c => c.atributos && c.atributos.marca).filter(Boolean))];
    this.cad.aviso(`${n} barra(s) mudada(s)${todas ? ` em todas as ${marcas.join(', ')}` : ` — agora ${marcas.join(', ')}`}. O 3D acompanha. Ctrl+Z desfaz.`, 'info', 9000);
    if (this._pf && this._pf.sugestao && !this._pf.sugestao.vazia) await new Promise(r => setTimeout(r, 600)).then(() => this.lerLegendaColada());
    this._encherPerfis();
  }

  /**
   * A legenda de cores do projeto colada na elevação (a folha "PERFIS TC1": "PERFIL COMPOSTO UE100x50x17x2.25mm" na cor
   * das barras daquele perfil) como sugestão: o mesmo leitor do "Tesoura…" (_perfisPelaLegenda), agora sobre as barras
   * já lançadas — cada uma pega a cor do traço colado sobre ela. Não muda nada: o painel mostra e o operador aceita.
   */
  lerLegendaColada() {
    const pf = this._pf;
    if (!pf) return null;
    const q = pf.q, doc = this.cad.doc;
    const real = (e) => transformar(e, (p) => this._paraReal(q, p), (a) => a, q.escala);
    const RX = /PERFIL[^]*U[E]?\s*\d/i;
    const coladas = [...doc.entidades.values()].filter(e => { const a = e.atributos || {}; return a.quadro === q.id && a.colado && !a.gerado; });
    const comLegenda = new Map();
    for (const e of coladas) if (e.tipo === 'texto' && RX.test(e.texto || '') && (e.atributos || {}).cor) comLegenda.set(e.atributos.colado, (comLegenda.get(e.atributos.colado) || 0) + 1);
    const folhas = new Set([...comLegenda.entries()].filter(([, n]) => n >= 2).map(([c]) => c));
    if (!folhas.size) { pf.sugestao = { porBarra: new Map(), n: 0, vazia: true }; return pf.sugestao; }
    const textos = coladas.filter(e => e.tipo === 'texto' && folhas.has(e.atributos.colado)).map(real);
    const tracos = coladas.filter(e => ['linha', 'polilinha'].includes(e.tipo) && folhas.has(e.atributos.colado) && e.atributos.cor).map(real);
    // as barras lançadas, na medida real da elevação (pelas linhas geradas: as espelhadas já vêm no lugar)
    const linhas = this._linhasDasBarras();
    const des = { origem: [0, 0], barras: linhas.map(l => {
      const a = this._paraReal(q, l.a), b = this._paraReal(q, l.b), e = doc.get(l.ref);
      return [a[0], a[1], b[0], b[1], e.atributos.desenho.barras[l.i][4]];
    }) };
    const r = this._perfisPelaLegenda(des, tracos, textos) || { avisos: [] };
    const porBarra = new Map();
    linhas.forEach((l, k) => { const b = des.barras[k]; if (b[5]) porBarra.set(`${l.ref}:${l.i}`, { perfil: b[5], arranjo: b[6] || '' }); });
    let diferentes = 0;
    for (const [k, v] of porBarra) { const [id, i] = k.split(':'); const b = doc.get(id).atributos.desenho.barras[+i]; if ((b[5] || '') !== v.perfil || (b[6] || '') !== v.arranjo) diferentes++; }
    pf.sugestao = { porBarra, n: porBarra.size, total: linhas.length, diferentes, avisos: r.avisos || [] };
    return pf.sugestao;
  }

  _diferentesDaSugestao() {
    const pf = this._pf, out = [];
    if (!pf || !pf.sugestao) return out;
    for (const [k, v] of pf.sugestao.porBarra) {
      const [id, i] = k.split(':'); const e = this.cad.doc.get(id); const b = e && e.atributos.desenho.barras[+i];
      if (b && ((b[5] || '') !== v.perfil || (b[6] || '') !== v.arranjo)) out.push({ e, i: +i, b, sug: v });
    }
    return out;
  }

  /** O bloco "Legenda do projeto" do painel: ler, o que ela confirma e o que muda, selecionar ou aceitar as diferentes. */
  _blocoSugestao() {
    const pf = this._pf, sg = pf.sugestao;
    const ler = el('button', { type: 'button', id: 'perfis-ler-legenda', title: 'Lê a legenda de cores da folha de perfis colada nesta elevação e sugere o perfil de cada barra',
      onclick: () => { this.lerLegendaColada(); this._encherPerfis(); this.cad.tela.pedirQuadro(); } }, sg ? 'Ler de novo' : 'Ler a legenda colada');
    if (!sg) return el('div', { class: 'perfis-sugestao' }, el('span', {}, 'Legenda do projeto: '), ler);
    if (sg.vazia) return el('div', { class: 'perfis-sugestao' }, el('span', { texto: 'Nenhuma legenda de cores colada nesta elevação (a folha de perfis com "PERFIL … UE…" na cor das barras). Cole-a por cima, alinhada, e leia de novo. ' }), ler);
    const dif = this._diferentesDaSugestao();
    const marcas = [...new Set(dif.map(d => d.e.atributos.marca))].sort(natural);
    return el('div', { class: 'perfis-sugestao', id: 'perfis-sugestao' },
      el('div', {}, `Legenda do projeto: ${sg.n} de ${sg.total} barras com cor; ${sg.n - dif.length} conferem, `, el('b', {}, `${dif.length} diferente(s)`), sg.total - sg.n ? `, ${sg.total - sg.n} sem cor no desenho (ficam como estão).` : '.'),
      ...(sg.avisos || []).map(a => el('div', { class: 'explica', texto: a.replace('essas ficam com o perfil escolhido abaixo', 'essas ficam como estão') })),
      el('div', { class: 'perfis-botoes' },
        el('button', { type: 'button', id: 'perfis-sel-diferentes', disabled: !dif.length, onclick: () => this._selecionarBarras(dif.map(d => `${d.e.id}:${d.i}`), 'trocar') }, 'Selecionar as diferentes'),
        el('button', { type: 'button', id: 'perfis-aceitar-legenda', disabled: !dif.length,
          onclick: () => this._aplicarPerfis(true, (s) => (pf.sugestao.porBarra.get(`${s.e.id}:${s.i}`) || null), dif) }, marcas.length ? `Aceitar em todas as ${marcas.join(', ')}` : 'Aceitar'),
        ler));
  }

  /** A cor de cada perfil (perfil + arranjo) das tesouras do eixo, na ordem dos nomes: a mesma na elevação e na legenda. */
  _coresDosPerfis(tes) {
    const chaves = new Set();
    for (const t of tes) for (const b of t.atributos.desenho.barras) chaves.add(chavePerfil(perfilDaBarra(b, t.atributos.perfis)));
    return new Map([...chaves].sort(natural).map((k, i) => [k, CORES[i % CORES.length]]));
  }

  /** A legenda: cada perfil com a cor e quantas barras há no eixo; clicar seleciona as barras dele. */
  _legendaPerfis(tes) {
    const pf = this._pf;
    const cores = this._coresDosPerfis(tes);
    pf.cores = cores;
    const soma = new Map();
    for (const t of tes) for (const b of t.atributos.desenho.barras) {
      const p = perfilDaBarra(b, t.atributos.perfis), k = chavePerfil(p);
      const x = soma.get(k) || { ...p, n: 0 }; x.n++; soma.set(k, x);
    }
    const pintar = el('input', { type: 'checkbox', id: 'perfis-pintar', checked: pf.pintar !== false });
    pintar.addEventListener('change', () => { pf.pintar = pintar.checked; this.cad.tela.pedirQuadro(); });
    const linhas = [...cores.keys()].map(k => {
      const x = soma.get(k);
      return el('li', { 'data-chave': k, title: 'Clique para selecionar estas barras', onclick: () => this._selecionarPorPerfil(k) },
        el('span', { class: 'perfis-cor' + (x.doTipo ? ' tracejada' : ''), style: `--cor:${cores.get(k)}` }),
        el('span', {}, `${x.perfil}${x.arranjo ? ' · ' + x.arranjo : ''}${x.doTipo ? ' — do tipo (sem perfil próprio)' : ''}`),
        el('span', { class: 'perfis-n' }, `${x.n}`));
    });
    return el('div', { class: 'perfis-legenda' },
      el('label', { class: 'linha' }, pintar, ' Pintar a tesoura por perfil'),
      el('ol', { id: 'perfis-legenda' }, linhas));
  }

  _selecionarPorPerfil(chave) {
    const chaves = [];
    for (const l of this._linhasDasBarras()) {
      const e = this.cad.doc.get(l.ref), b = e && e.atributos.desenho.barras[l.i];
      if (b && chavePerfil(perfilDaBarra(b, e.atributos.perfis)) === chave) chaves.push(`${l.ref}:${l.i}`);
    }
    this._selecionarBarras(chaves, 'trocar');
  }

  /** A tabela de cada tipo do eixo: função, perfil, barras, metros e kg por tesoura, e o total da obra (× quantas há). */
  _tabelasDasTesouras(tes, dados) {
    const todas = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica');
    const porMarca = new Map();
    for (const t of tes) if (!porMarca.has(t.atributos.marca)) porMarca.set(t.atributos.marca, t);
    const fmt = (v, d = 1) => v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
    const blocos = [...porMarca.entries()].sort((a, b) => natural(a[0], b[0])).map(([marca, t]) => {
      const tab = tabelaDaTesoura(t.atributos.desenho.barras, t.atributos.perfis, dados);
      const qtd = todas.filter(x => x.atributos.marca === marca).length;
      const kg = tab.reduce((s, l) => s + (l.kg || 0), 0), aprox = tab.some(l => l.aprox), falta = tab.some(l => l.kg == null);
      return el('details', { class: 'perfis-tabela', 'data-marca': marca },
        el('summary', {}, `Tabela da ${marca}: ${fmt(kg)} kg por tesoura${aprox ? ' (≈)' : ''} · ${qtd}× na obra = ${fmt(kg * qtd / 1000, 2)} t${falta ? ' — há perfil sem peso' : ''}`),
        el('table', {},
          el('thead', {}, el('tr', {}, ['Função', 'Perfil', 'Barras', 'm', 'kg'].map(h => el('th', {}, h)))),
          el('tbody', {}, tab.map(l => el('tr', { class: l.doTipo ? 'do-tipo' : null },
            el('td', {}, NOME_FN[l.funcao] || l.funcao),
            el('td', {}, `${l.perfil}${l.arranjo ? ' · ' + l.arranjo : ''}`),
            el('td', {}, String(l.n)), el('td', {}, fmt(l.m, 2)),
            el('td', {}, l.kg == null ? '—' : fmt(l.kg) + (l.aprox ? ' ≈' : '')))))));
    });
    return el('div', { class: 'perfis-tabelas' }, blocos,
      el('div', { class: 'explica', texto: 'kg pelo catálogo; ≈ = pela seção do perfil (7850 kg/m³), sem chapas nem parafusos. O duplo (composto, caixa) conta os dois perfis. Em itálico: barras sem perfil próprio, com o do tipo.' }));
  }

  /** Pinta, na elevação, cada barra com a cor do perfil dela (tracejada = o do tipo) e destaca as selecionadas. */
  _desenharSelecaoPerfis() {
    const pf = this._pf;
    if (!pf) return;
    const tela = this.cad.tela, ctx = tela.ctx;
    if (pf.pintar !== false && pf.cores) {
      ctx.save(); ctx.lineWidth = 3; ctx.lineCap = 'round';
      for (const l of this._linhasDasBarras()) {
        const e = this.cad.doc.get(l.ref), b = e && e.atributos.desenho.barras[l.i];
        if (!b) continue;
        const p = perfilDaBarra(b, e.atributos.perfis);
        ctx.strokeStyle = pf.cores.get(chavePerfil(p)) || '#94a3b8';
        ctx.setLineDash(p.doTipo ? [6, 4] : []);
        const a = tela.paraTela(l.a), c = tela.paraTela(l.b);
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(c[0], c[1]); ctx.stroke();
      }
      ctx.restore();
    }
    if (!pf.sel.size) return;
    ctx.save();
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 8; ctx.globalAlpha = 0.4; ctx.setLineDash([]);
    ctx.beginPath();
    for (const l of this._linhasDasBarras()) {
      if (!pf.sel.has(`${l.ref}:${l.i}`)) continue;
      const a = tela.paraTela(l.a), b = tela.paraTela(l.b);
      ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
    }
    ctx.stroke();
    ctx.restore();
  }
}
