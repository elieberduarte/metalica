/* Resultado da análise do projeto numa tela só: lê o último cálculo gravado
 * (GET /api/projetos/<slug>/calculo, o mesmo que o 3D mostra no mapa de aproveitamento) e
 * mostra o resumo, a situação por tipo de peça, a tabela de todas as peças verificadas —
 * com as verificações e os passos da conta ao clicar numa linha —, as ligações, o que não
 * foi verificado, os avisos, os dados de entrada (cargas e vento) e as combinações.
 * Recalcular, trocar perfil e dimensionar continuam no 3D ("Modelo 3D"). */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);
const PROJETO = new URLSearchParams(location.search).get('projeto') || '';

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
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    e.append(f.nodeType ? f : document.createTextNode(String(f)));
  }
  return e;
}

const n = (x, casas = 0) => (x === null || x === undefined || x === '' || Number.isNaN(Number(x))) ? '—'
  : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const pct = (x) => (x === null || x === undefined) ? '—' : `${n(Number(x) * 100, 0)} %`;
const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
/* as fórmulas do núcleo vêm com <sub>/<sup>: só essas marcas passam, o resto é texto */
const formula = (t) => esc(t).replace(/&lt;(\/?)(sub|sup)&gt;/g, '<$1$2>');

async function pedir(rota) {
  const r = await fetch(rota);
  let j = {};
  try { j = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function aviso(texto, erro = false) {
  const a = $('#aviso');
  a.hidden = !texto;
  a.textContent = texto || '';
  a.classList.toggle('erro', !!erro);
}

function alternarTema() {
  const raiz = document.documentElement;
  const escuroDoSistema = matchMedia('(prefers-color-scheme: dark)').matches;
  const atual = raiz.getAttribute('data-tema') || (escuroDoSistema ? 'escuro' : 'claro');
  const novo = atual === 'escuro' ? 'claro' : 'escuro';
  raiz.setAttribute('data-tema', novo);
  try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* janela privativa */ }
}

/* ------------------------------------------------------------------- rótulos */
const TIPOS = {
  banzo: 'Banzo', diagonal: 'Diagonal', montante: 'Montante', terca: 'Terça', pilar: 'Pilar',
  longarina: 'Longarina', contraventamento: 'Contraventamento', corrente: 'Corrente',
  travamento: 'Travamento', tirante: 'Tirante', viga: 'Viga',
};
const ORDEM_TIPOS = Object.keys(TIPOS);
const rotuloTipo = (t) => TIPOS[t] || (t ? t[0].toUpperCase() + t.slice(1) : '—');

function situacao(e) {
  if (e.indeterminada) return el('span', { class: 'situacao ind', texto: 'não verificada', title: 'Faltou dado para verificar: conta como não aprovada' });
  return e.ok ? el('span', { class: 'situacao ok', texto: 'passa' }) : el('span', { class: 'situacao nao', texto: 'não passa' });
}

function barraAprov(a, indeterminada = false) {
  const v = Number(a) || 0;
  const faixa = indeterminada ? 'indeterminado' : v > 1.0001 ? 'reprovado' : v >= 0.9 ? 'alto' : 'bom';
  const larg = Math.max(0, Math.min(1, v)) * 100;
  return el('span', { class: 'aprov', 'data-faixa': faixa, title: indeterminada ? 'não verificada' : `aproveitamento ${n(v, 3)}` },
    el('span', { class: 'trilho' }, el('span', { class: 'cheio', style: `width:${larg}%` })),
    el('b', { texto: indeterminada ? '—' : pct(v) }));
}

/* ------------------------------------------------------------------- tabela ordenável */
function tabela(colunas, linhas, { filtro, linhaExtra } = {}) {
  const thead = el('thead', {}, el('tr', {}, colunas.map((c, i) => el('th', {
    class: c.classe || '', texto: c.titulo, title: c.dica || 'Clique para ordenar',
    onclick: (ev) => ordenar(ev.currentTarget.closest('table'), i, c),
  }))));
  const tbody = el('tbody');
  for (const li of linhas) {
    const tr = el('tr', { 'data-filtro': (filtro ? filtro(li) : JSON.stringify(li)).toLowerCase(),
                          'data-situacao': li.indeterminada ? 'nao' : (li.ok === false ? 'nao' : 'ok') });
    for (const c of colunas) {
      const v = c.valor ? c.valor(li) : li[c.chave];
      const td = el('td', { class: c.classe || '' });
      if (v && v.nodeType) td.append(v); else td.textContent = c.num ? n(v, c.casas || 0) : (v ?? '—');
      const o = c.ordem ? c.ordem(li) : (c.num ? Number(v) : v);
      td.dataset.v = typeof o === 'number' ? String(Number.isFinite(o) ? o : 0) : String(o && o.nodeType ? o.textContent : (o ?? ''));
      td.dataset.num = c.num || c.ordem ? '1' : '';
      tr.append(td);
    }
    if (linhaExtra) { tr.classList.add('linha-peca'); tr.addEventListener('click', () => linhaExtra(tr, li, colunas.length)); }
    tbody.append(tr);
  }
  return el('table', {}, thead, tbody);
}

function ordenar(table, i, c) {
  const th = table.tHead.rows[0].cells[i];
  const asc = !th.classList.contains('ordem-asc');
  for (const x of table.tHead.rows[0].cells) x.classList.remove('ordem-asc', 'ordem-desc');
  th.classList.add(asc ? 'ordem-asc' : 'ordem-desc');
  // os detalhes abertos saem junto (voltam ao clicar de novo)
  for (const d of [...table.tBodies[0].querySelectorAll('tr.detalhe')]) d.remove();
  for (const a of table.tBodies[0].querySelectorAll('tr.aberta')) a.classList.remove('aberta');
  const linhas = [...table.tBodies[0].rows];
  const num = !!(c.num || c.ordem);
  linhas.sort((a, b) => {
    const va = a.cells[i].dataset.v, vb = b.cells[i].dataset.v;
    const r = num ? (Number(va) - Number(vb)) : va.localeCompare(vb, 'pt-BR', { numeric: true });
    return asc ? r : -r;
  });
  table.tBodies[0].append(...linhas);
}

function secao(titulo, sub, conteudo) {
  // tabela solta ganha rolagem própria: na tela estreita a página não rola de lado
  if (conteudo && conteudo.tagName === 'TABLE') conteudo = el('div', { class: 'larga' }, conteudo);
  return el('section', {}, el('h2', {}, titulo, sub ? el('small', { texto: sub }) : null), conteudo);
}

function cartao(valor, rotulo, nota, classe) {
  return el('div', { class: 'cartao-n' + (classe ? ' ' + classe : '') }, el('b', { texto: valor }), el('span', { texto: rotulo }),
    nota ? el('small', { texto: nota }) : null);
}

/* ------------------------------------------------------------------- detalhe de uma peça */
let CALCULO = null;
let VERIF_POR_TITULO = new Map();

function detalhePeca(tr, e, ncol) {
  const prox = tr.nextElementSibling;
  if (prox && prox.classList.contains('detalhe')) { prox.remove(); tr.classList.remove('aberta'); return; }
  tr.classList.add('aberta');
  const caixa = el('div', { class: 'detalhe-peca' });
  const ver3d = `/editor?projeto=${encodeURIComponent(PROJETO)}&destacar=${encodeURIComponent('posicao:' + e.marca)}`;
  const alt = el('div', { class: 'alternativas' });
  caixa.append(el('div', { class: 'acoes' },
    el('button', { type: 'button', texto: 'Ver no 3D', title: 'Abre o modelo com esta posição em destaque (lá se troca o perfil e recalcula)',
                   onclick: (ev) => { ev.stopPropagation(); location.href = ver3d; } }),
    el('button', { type: 'button', texto: 'Perfis que servem no lugar…', title: 'Perfis do catálogo verificados com os esforços deste cálculo',
                   onclick: (ev) => { ev.stopPropagation(); alternativas(e, alt); } })));
  const d = e.dimensionamento || {};
  const dados = [
    ['Caso que governa', d.caso], ['N (kN)', n(d.N, 2)], ['V (kN)', n(d.V, 2)], ['M (kN·m)', n(d.M, 2)],
    ['Lx (cm)', n(d.Lx_cm, 1)], ['Ly (cm)', n(d.Ly_cm, 1)], ['K', d.K], ['Vão (m)', n(d.vao_m, 2)],
    ['Correntes', d.correntes], ['Comprimento total no modelo (m)', n(e.comprimento_total_m, 2)], ['Peso no modelo (kg)', n(e.peso_kg, 1)],
  ].filter(([, v]) => v !== undefined && v !== null && v !== '—' && v !== '');
  caixa.append(el('p', { class: 'nota', texto: dados.map(([k, v]) => `${k}: ${v}`).join(' · ') }));
  if (e.ligacao) {
    caixa.append(el('p', { class: 'nota', texto: `Ligação ${e.ligacao.chave} (${e.ligacao.tipo}): ${pct(e.ligacao.aproveitamento)} — ${e.ligacao.governa || ''}` }));
  }
  const r = VERIF_POR_TITULO.get(e.titulo);
  if (!r) caixa.append(el('div', { class: 'vazio', texto: 'As verificações desta peça não estão no cálculo gravado.' }));
  for (const v of (r ? r.verificacoes : [])) {
    const blocos = el('div', { class: 'verif' },
      el('header', {}, el('b', { texto: v.titulo }), el('span', { class: 'norma', texto: v.norma || '' }),
        el('span', { class: 'conta', texto: `${n(v.Sd, 2)} / ${n(v.Rd, 2)}${v.unidade && v.unidade !== '—' ? ' ' + v.unidade : ''} = ${pct(v.razao)}` }),
        situacao({ ok: v.ok, indeterminada: v.indeterminada })));
    if ((v.passos || []).length) {
      const corpo = el('tbody');
      for (const p of v.passos) {
        corpo.append(el('tr', {}, el('td', { html: formula(p.texto || '') }), el('td', { html: formula(p.formula || '') }),
          el('td', { html: formula(p.conta || '') }), el('td', { class: 'b', html: formula(p.valor || '') }), el('td', { class: 'nota', texto: p.norma || '' })));
      }
      blocos.append(el('table', {}, corpo));
    }
    if (v.observacao) blocos.append(el('div', { class: 'obs', texto: v.observacao }));
    caixa.append(blocos);
  }
  caixa.append(alt);
  const det = el('tr', { class: 'detalhe' }, el('td', { colspan: String(ncol) }, caixa));
  tr.after(det);
}

async function alternativas(e, caixa) {
  caixa.replaceChildren(el('p', { class: 'nota', texto: 'Verificando os perfis do catálogo…' }));
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/calculo/alternativas?marca=${encodeURIComponent(e.marca)}`);
    const lista = r.alternativas || [];
    if (!lista.length) { caixa.replaceChildren(el('div', { class: 'vazio', texto: 'Nada no catálogo serve para esta posição.' })); return; }
    const passam = lista.filter(a => a.ok).length;
    caixa.replaceChildren(el('p', { class: 'nota', texto: (passam ? `${passam} de ${lista.length} passam nos esforços atuais.` : 'Nenhum passa; os primeiros são os que chegam mais perto.') +
      ' Para trocar, use "Ver no 3D" (a troca refaz o cálculo, porque muda a rigidez da tesoura).' }),
      tabela([
        { titulo: 'Perfil', chave: 'nome', classe: 'b' },
        { titulo: 'kg/m', chave: 'massa', classe: 'r', num: true, casas: 2 },
        { titulo: 'Δ peso (kg)', valor: (a) => a.delta_peso_kg, classe: 'r', num: true, casas: 0 },
        { titulo: 'Aproveitamento', valor: (a) => barraAprov(a.aproveitamento), ordem: (a) => a.aproveitamento },
        { titulo: 'Ligação', valor: (a) => a.ligacao ? pct(a.ligacao.aproveitamento) : '—', classe: 'r' },
        { titulo: 'Governa', chave: 'governa', classe: 'quebra' },
        { titulo: 'Situação', valor: (a) => situacao(a) },
      ], lista));
  } catch (err) {
    caixa.replaceChildren(el('div', { class: 'vazio', texto: `Não foi possível levantar as alternativas: ${err.message}` }));
  }
}

/* ------------------------------------------------------------------- a tela */
function desenhar(C, quando, parametros, nomeProjeto) {
  CALCULO = C;
  VERIF_POR_TITULO = new Map((C.verificacoes || []).map(v => [v.elemento, v]));
  const res = C.resumo || {};
  const elementos = Object.entries(C.elementos || {}).map(([marca, e]) => ({ marca, ...e }));
  const reprovadas = elementos.filter(e => !e.ok);
  const indet = elementos.filter(e => e.indeterminada);
  const pior = elementos.reduce((p, e) => (!p || (e.aproveitamento || 0) > (p.aproveitamento || 0) ? e : p), null);
  const ligs = C.ligacoes || [];
  const ligRep = ligs.filter(l => !l.ok);
  const nv = res.nao_verificadas || [];
  const desl = (C.servico || {}).deslocamento;

  document.title = `Resultado da análise — ${nomeProjeto || PROJETO}`;
  $('#sub-projeto').textContent = nomeProjeto || PROJETO;
  $('#obra-atual').replaceChildren('Projeto: ', el('b', { texto: nomeProjeto || PROJETO }));
  $('#quando').textContent = quando ? `calculado em ${quando.replace(/^(\d{4})-(\d{2})-(\d{2})/, '$3/$2/$1')}` : '—';
  $('#quando').title = 'Quando o cálculo foi feito. Depois de mudar o modelo, recalcule no 3D ("Calcular estrutura").';

  $('#cartoes').replaceChildren(
    cartao(n(elementos.length), 'posições verificadas', `${n(res.barras_no_modelo)} barras no modelo`),
    cartao(n(reprovadas.length), 'não passam', indet.length ? `${indet.length} sem dado para verificar` : (reprovadas.length ? 'ver a tabela' : 'todas passam'),
      reprovadas.length ? 'ruim' : 'bom'),
    cartao(pior ? pct(pior.aproveitamento) : '—', 'pior aproveitamento', pior ? `${pior.marca}${pior.nome ? ' ' + pior.nome : ''} · ${rotuloTipo(pior.tipo)} · ${pior.governa || ''}` : '',
      pior && pior.aproveitamento > 1.0001 ? 'ruim' : pior && pior.aproveitamento >= 0.9 ? 'atencao' : 'bom'),
    cartao(n(res.peso_verificado_kg, 0) + ' kg', 'peso verificado'),
    ligs.length ? cartao(n(ligs.length), 'ligações', ligRep.length ? `${ligRep.length} não passam` : `todas passam · pior ${pct(res.pior_ligacao)}`, ligRep.length ? 'ruim' : 'bom') : null,
    desl ? cartao(`${n(desl.u_cm, 2)} cm`, 'flecha', `${desl.rotulo || ''} · limite ${n(desl.limite_cm, 2)} cm (${desl.criterio || ''})`, desl.razao > 1 ? 'ruim' : 'bom') : null,
    nv.length ? cartao(n(nv.reduce((s, x) => s + (x.pecas || 0), 0)), 'peças fora do cálculo', nv.map(x => x.marca).join(', '), 'atencao') : null);

  const c = $('#conteudo');
  c.replaceChildren();

  if (reprovadas.length) {
    const semTrava = reprovadas.filter(e => e.sem_trava).map(e => e.marca);
    aviso(`${reprovadas.length} posição(ões) não passam: ${reprovadas.map(e => e.marca).sort((a, b) => a.localeCompare(b, 'pt-BR', { numeric: true })).join(', ')}. ` +
          (semTrava.length ? `${semTrava.join(', ')}: banzo inferior sem travamento lateral no modelo (Ly = comprimento inteiro) — informe o espaçamento dos travamentos no cálculo do 3D e recalcule. ` : '') +
          'Clique numa linha para ver a conta; troque o perfil ou dimensione no Modelo 3D.', true);
  } else aviso('');

  // situação por tipo
  const porTipo = new Map();
  for (const e of elementos) {
    const t = porTipo.get(e.tipo) || { tipo: e.tipo, posicoes: 0, passam: 0, reprovam: 0, pior: 0, pior_marca: '', peso: 0 };
    t.posicoes += 1; t.peso += e.peso_kg || 0;
    if (e.ok) t.passam += 1; else t.reprovam += 1;
    if ((e.aproveitamento || 0) > t.pior) { t.pior = e.aproveitamento || 0; t.pior_marca = e.marca; }
    porTipo.set(e.tipo, t);
  }
  const tipos = [...porTipo.values()].sort((a, b) => (ORDEM_TIPOS.indexOf(a.tipo) + 99 * (ORDEM_TIPOS.indexOf(a.tipo) < 0)) - (ORDEM_TIPOS.indexOf(b.tipo) + 99 * (ORDEM_TIPOS.indexOf(b.tipo) < 0)));
  c.append(secao('Situação por tipo de peça', null, tabela([
    { titulo: 'Tipo', valor: (t) => rotuloTipo(t.tipo), classe: 'b' },
    { titulo: 'Posições', chave: 'posicoes', classe: 'c', num: true },
    { titulo: 'Passam', chave: 'passam', classe: 'c', num: true },
    { titulo: 'Não passam', chave: 'reprovam', classe: 'c', num: true },
    { titulo: 'Pior aproveitamento', valor: (t) => barraAprov(t.pior), ordem: (t) => t.pior },
    { titulo: 'Onde', chave: 'pior_marca' },
    { titulo: 'Peso (kg)', chave: 'peso', classe: 'r', num: true, casas: 0 },
  ], tipos)));

  // todas as peças
  elementos.sort((a, b) => (b.aproveitamento || 0) - (a.aproveitamento || 0));
  c.append(secao('Peças verificadas', 'da mais carregada para a menos; clique numa linha para ver as verificações e a conta',
    el('div', { class: 'rolagem' }, tabela([
      { titulo: 'Posição', chave: 'marca', classe: 'b' },
      { titulo: 'Nome', chave: 'nome' },
      { titulo: 'Tipo', valor: (e) => e.sem_trava
          ? el('span', {}, rotuloTipo(e.tipo) + (e.posicao ? ` ${e.posicao}` : ''), el('br'),
               el('small', { class: 'sem-trava', texto: 'sem travamento lateral',
                             title: 'No modelo o banzo inferior não tem travamento fora do plano: Ly é o comprimento inteiro. Informe o espaçamento dos travamentos no cálculo (3D) e recalcule.' }))
          : rotuloTipo(e.tipo) + (e.posicao ? ` ${e.posicao}` : ''), ordem: (e) => rotuloTipo(e.tipo) + (e.posicao || '') },
      { titulo: 'Perfil', chave: 'perfil' },
      { titulo: 'Aço', chave: 'material' },
      { titulo: 'Aproveitamento', valor: (e) => barraAprov(e.aproveitamento, e.indeterminada), ordem: (e) => e.aproveitamento || 0 },
      { titulo: 'Governa', chave: 'governa', classe: 'quebra' },
      { titulo: 'Sd', chave: 'Sd', classe: 'r', num: true, casas: 2 },
      { titulo: 'Rd', chave: 'Rd', classe: 'r', num: true, casas: 2 },
      { titulo: 'Un.', chave: 'unidade' },
      { titulo: 'Caso', valor: (e) => (e.dimensionamento || {}).caso || '—' },
      { titulo: 'N (kN)', valor: (e) => (e.dimensionamento || {}).N, classe: 'r', num: true, casas: 1 },
      { titulo: 'M (kN·m)', valor: (e) => (e.dimensionamento || {}).M, classe: 'r', num: true, casas: 2 },
      { titulo: 'Peso (kg)', chave: 'peso_kg', classe: 'r', num: true, casas: 0 },
      { titulo: 'Situação', valor: (e) => situacao(e), ordem: (e) => (e.indeterminada ? 2 : e.ok ? 0 : 1) },
    ], elementos, { filtro: (e) => [e.marca, e.nome, e.tipo, rotuloTipo(e.tipo), e.perfil, e.governa, (e.conjuntos || []).join(' ')].join(' '),
                    linhaExtra: detalhePeca }))));

  if (ligs.length) {
    const ls = [...ligs].sort((a, b) => (b.aproveitamento || 0) - (a.aproveitamento || 0));
    c.append(secao('Ligações', 'chapa de nó ou solda da barra no banzo, com a força da barra no pior caso',
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Ligação', chave: 'chave', classe: 'b' },
        { titulo: 'Tipo', chave: 'tipo' },
        { titulo: 'Barra', valor: (l) => `${l.barra}${l.tipo_barra ? ' (' + l.tipo_barra + ')' : ''}` },
        { titulo: 'Perfil', chave: 'perfil' },
        { titulo: 'Chapa (mm)', chave: 'espessura_mm', classe: 'r', num: true, casas: 1 },
        { titulo: 'N (kN)', chave: 'N_kN', classe: 'r', num: true, casas: 1 },
        { titulo: 'Aproveitamento', valor: (l) => barraAprov(l.aproveitamento, l.indeterminada), ordem: (l) => l.aproveitamento || 0 },
        { titulo: 'Governa', chave: 'governa', classe: 'quebra' },
        { titulo: 'Caso', chave: 'caso', classe: 'quebra' },
        { titulo: 'Situação', valor: (l) => situacao(l), ordem: (l) => (l.ok ? 0 : 1) },
      ], ls, { filtro: (l) => [l.chave, l.tipo, l.barra, l.chapa, l.perfil, l.governa].join(' ') }))));
  }

  if (nv.length) {
    c.append(secao('Fora do cálculo', 'posições que o cálculo não verificou (conferir à mão)', tabela([
      { titulo: 'Posição', chave: 'marca', classe: 'b' }, { titulo: 'Nome', chave: 'nome' },
      { titulo: 'Tipo', valor: (x) => rotuloTipo(x.tipo) }, { titulo: 'Perfil', chave: 'perfil' },
      { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
    ], nv)));
  }

  if ((C.avisos || []).length) {
    c.append(secao('Avisos do cálculo', null, el('ul', { class: 'lista' }, C.avisos.map(a => el('li', { texto: a })))));
  }

  // dados de entrada
  const par = parametros || res.parametros || {};
  const v = res.vento || {};
  const linhasDados = [
    ['Tesouras', `${n(res.tesouras)} (${n(res.tipos_de_tesoura)} tipo(s))`], ['Vão', `${n(res.vao_m, 2)} m`],
    ['Inclinação', `${n(res.inclinacao_graus, 2)}°`], ['Telha', `${n(res.telha_kN_m2, 3)} kN/m²`],
    ['Sobrecarga', `${n(res.sobrecarga_kN_m2, 2)} kN/m²`], ['Carga extra', `${n(res.carga_extra_kN_m2, 2)} kN/m²`],
    ['Apoio da tesoura', par.apoio], ['Aço formado a frio', par.aco_frio], ['Aço laminado', par.aco_laminado],
    ['Parafuso / eletrodo', [par.parafuso, par.eletrodo].filter(Boolean).join(' / ')],
    ['Flecha da tesoura', par.flecha_tesoura ? `L/${par.flecha_tesoura}` : null], ['Flecha da terça', par.flecha_terca ? `L/${par.flecha_terca}` : null],
  ].filter(([, x]) => x !== undefined && x !== null && x !== '');
  const linhasVento = [
    ['V₀', `${n(v.V0, 1)} m/s`], ['S₁ · S₂ · S₃', `${n(v.S1, 3)} · ${n(v.S2, 3)} · ${n(v.S3, 3)}`],
    ['Categoria / classe', `${v.categoria || '—'} / ${v.classe || '—'}`], ['Vk', `${n(v.Vk, 2)} m/s`], ['q', `${n(v.q, 4)} kN/m²`],
    ['Dimensões (a × b × h)', `${n(v.a, 2)} × ${n(v.b, 2)} × ${n(v.h, 2)} m`],
  ];
  const tabelaSimples = (linhas) => el('table', {}, el('tbody', {}, linhas.map(([k, x]) => el('tr', {}, el('td', { texto: k }), el('td', { class: 'b', texto: x })))));
  const casos = Object.entries(v.casos || {});
  c.append(secao('Dados do cálculo', 'cargas e vento (NBR 6123) usados nesta análise', el('div', { class: 'grade-dados' },
    el('div', {}, tabelaSimples(linhasDados)),
    el('div', {}, tabelaSimples(linhasVento),
      casos.length ? el('table', { style: 'margin-top:8px' },
        el('thead', {}, el('tr', {}, el('th', { texto: 'Caso de vento (coef. no telhado)' }), el('th', { class: 'r', texto: 'Água esq.' }), el('th', { class: 'r', texto: 'Água dir.' }))),
        el('tbody', {}, casos.map(([, cv]) => el('tr', {}, el('td', { class: 'quebra', texto: cv.descricao }),
          el('td', { class: 'r', texto: n(cv.esq, 3) }), el('td', { class: 'r', texto: n(cv.dir, 3) }))))) : null))));
  if ((v.observacoes || []).length) c.append(el('ul', { class: 'lista' }, v.observacoes.map(o => el('li', { class: 'nota', texto: o }))));

  const combs = (C.combinacoes || []).filter(x => x.tipo !== 'envoltoria');
  if (combs.length) {
    c.append(secao('Combinações', 'as últimas entram na envoltória; as de serviço, na flecha', tabela([
      { titulo: 'Combinação', chave: 'nome', classe: 'b' },
      { titulo: 'Expressão', chave: 'descricao', classe: 'quebra' },
      { titulo: 'Tipo', valor: (x) => x.tipo === 'ultima' ? 'última' : 'serviço' },
    ], combs)));
  }
  filtrar();
}

function filtrar() {
  const q = ($('#filtro').value || '').trim().toLowerCase();
  const s = $('#situacao').value;
  for (const tr of document.querySelectorAll('#conteudo tbody tr[data-filtro]')) {
    if (tr.closest('.detalhe-peca')) continue;           // as tabelas dentro do detalhe aberto
    const ok = (!q || tr.dataset.filtro.includes(q)) && (!s || tr.dataset.situacao === s || !tr.closest('.rolagem'));
    tr.classList.toggle('oculta', !ok);
    const d = tr.nextElementSibling;
    if (d && d.classList.contains('detalhe')) d.classList.toggle('oculta', !ok);
  }
}

async function carregar() {
  if (!PROJETO) { aviso('Abra esta tela pelo projeto (Modelo 3D → Calcular → Resultado da análise).', true); return; }
  aviso('Lendo o cálculo gravado…');
  let nome = '';
  try { nome = ((await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}`)).projeto || {}).nome || ''; } catch { /* sem nome */ }
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/calculo`);
    if (!r.calculo) {
      $('#sub-projeto').textContent = nome || PROJETO;
      $('#obra-atual').replaceChildren('Projeto: ', el('b', { texto: nome || PROJETO }));
      aviso('Este projeto ainda não tem cálculo. Abra o Modelo 3D e use "Calcular estrutura" (F9); o resultado aparece aqui.');
      return;
    }
    desenhar(r.calculo, r.quando, r.parametros, nome);
  } catch (e) {
    aviso(`Não foi possível ler o cálculo: ${e.message}`, true);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-3d').addEventListener('click', () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-materiais').addEventListener('click', () => { location.href = `/materiais?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-voltar').addEventListener('click', () => {
    if (document.referrer && new URL(document.referrer).origin === location.origin && history.length > 1) history.back();
    else location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
  });
  $('#btn-imprimir').addEventListener('click', () => {
    // imprime com as peças todas e sem os detalhes abertos fora de lugar
    window.print();
  });
  $('#filtro').addEventListener('input', filtrar);
  $('#situacao').addEventListener('change', filtrar);
  carregar();
});
