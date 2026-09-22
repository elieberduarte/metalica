/* Lista de materiais do projeto: a tela lê GET /api/projetos/<slug>/materiais (a lista
 * gravada pelo último detalhamento, ou levantada na hora do modelo) e mostra os quadros —
 * totais por categoria, perfis com barras comerciais, chapas por espessura, telhas,
 * conjuntos, romaneio por posição, acessórios e ressalvas. "Recalcular" refaz do modelo
 * (POST, com a barra comercial escolhida); "PDF" imprime pelo servidor (POST /materiais/pdf).
 * Os arquivos ficam em <projeto>/detalhamento/ — ver saida/lista_producao.py. */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);
const PROJETO = new URLSearchParams(location.search).get('projeto') || '';

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    e.append(f.nodeType ? f : document.createTextNode(String(f)));
  }
  return e;
}

const n = (x, casas = 0) => (x === null || x === undefined || x === '') ? '—'
  : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
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

/* ------------------------------------------------------------------- tema */
function alternarTema() {
  const raiz = document.documentElement;
  const escuroDoSistema = matchMedia('(prefers-color-scheme: dark)').matches;
  const atual = raiz.getAttribute('data-tema') || (escuroDoSistema ? 'escuro' : 'claro');
  const novo = atual === 'escuro' ? 'claro' : 'escuro';
  raiz.setAttribute('data-tema', novo);
  try { localStorage.setItem('galpao.tema', novo); } catch (e) { /* janela privativa */ }
}

/* ------------------------------------------------------------------- quadros */
let LISTA = null;

/** Tabela ordenável: colunas = [{titulo, chave|valor(l), classe, num}], linhas = objetos. */
function tabela(colunas, linhas, rodape, chaveFiltro) {
  const thead = el('thead', {}, el('tr', {}, colunas.map((c, i) => el('th', {
    class: c.classe || '', texto: c.titulo, title: c.dica || 'Clique para ordenar',
    onclick: (ev) => ordenar(ev.currentTarget.closest('table'), i, c),
  }))));
  const tbody = el('tbody');
  for (const li of linhas) {
    const tr = el('tr', { 'data-filtro': (chaveFiltro ? chaveFiltro(li) : JSON.stringify(li)).toLowerCase() });
    for (const c of colunas) {
      const v = c.valor ? c.valor(li) : li[c.chave];
      const td = el('td', { class: c.classe || '' });
      if (v && v.nodeType) td.append(v); else td.textContent = c.num ? n(v, c.casas || 0) : (v === 0 && c.zero ? '—' : (v ?? '—'));
      td.dataset.v = c.num ? String(Number(v) || 0) : String(v ?? '');
      tr.append(td);
    }
    tbody.append(tr);
  }
  const t = el('table', {}, thead, tbody);
  if (rodape) t.append(el('tfoot', {}, el('tr', {}, rodape.map((v, i) => el('td', { class: colunas[i].classe || '', texto: v ?? '' })))));
  return t;
}

function ordenar(table, i, c) {
  const th = table.tHead.rows[0].cells[i];
  const asc = !th.classList.contains('ordem-asc');
  for (const x of table.tHead.rows[0].cells) x.classList.remove('ordem-asc', 'ordem-desc');
  th.classList.add(asc ? 'ordem-asc' : 'ordem-desc');
  const linhas = [...table.tBodies[0].rows];
  const num = !!c.num;
  linhas.sort((a, b) => {
    const va = a.cells[i].dataset.v, vb = b.cells[i].dataset.v;
    const r = num ? (Number(va) - Number(vb)) : va.localeCompare(vb, 'pt-BR', { numeric: true });
    return asc ? r : -r;
  });
  table.tBodies[0].append(...linhas);
}

function secao(titulo, sub, conteudo) {
  return el('section', {}, el('h2', {}, titulo, sub ? el('small', { texto: sub }) : null), conteudo);
}

function marcas(lista, max = 14) {
  const s = lista.slice(0, max).join(' ');
  return el('span', { class: 'mono', title: lista.join(' '), texto: s + (lista.length > max ? ' …' : '') });
}

function desenhar(L) {
  LISTA = L;
  const t = L.totais || {};
  const p = L.projeto || {};
  $('#sub-projeto').textContent = p.nome || PROJETO;
  document.title = `Lista de materiais — ${p.nome || PROJETO}`;
  $('#quando').textContent = L.gerado ? `levantada em ${L.gerado.replace(/^(\d{4})-(\d{2})-(\d{2})/, '$3/$2/$1')}` : '—';
  $('#quando').title = 'Quando a lista foi levantada do modelo. Depois de mudar o modelo, use "Recalcular".';
  $('#barra').value = String(L.barra || 0);

  // arquivos gravados
  const arq = L.arquivos || {};
  const rot = { romaneio: 'romaneio.csv', perfis: 'resumo-perfis.csv', chapas: 'resumo-chapas.csv', conjuntos: 'conjuntos.csv', html: 'lista (HTML)', pdf: 'lista (PDF)' };
  $('#arquivos').replaceChildren(el('span', { class: 'nota', texto: 'Arquivos (abrem no Excel / navegador): ' }),
    ...Object.entries(rot).filter(([k]) => arq[k]).map(([k, r]) => el('a', { href: arq[k].url, target: '_blank', rel: 'noopener',
      title: `${arq[k].nome} · ${n(arq[k].tamanho_kb, 1)} kB`, texto: r })));

  $('#cartoes').replaceChildren(
    cartao(n(t.pecas), 'peças'), cartao(n(t.posicoes), 'posições'), cartao(n(t.peso, 1) + ' kg', 'peso total'),
    cartao(n(t.conjuntos), 'conjuntos'), cartao(n((L.perfis || []).reduce((s, g) => s + (g.barras?.quantidade || 0), 0)), 'barras comerciais'),
    cartao(n(t.acessorios), 'acessórios'));

  const c = $('#conteudo');
  c.replaceChildren();

  c.append(secao('Totais por categoria', null, tabela([
    { titulo: 'Categoria', chave: 'titulo' }, { titulo: 'Posições', chave: 'posicoes', classe: 'c', num: true },
    { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true }, { titulo: 'Peso (kg)', chave: 'peso', classe: 'r', num: true, casas: 1 },
    { titulo: '% do peso', chave: 'pct', classe: 'c', num: true, casas: 1 },
  ], t.categorias || [], ['TOTAL', n(t.posicoes), n(t.pecas), n(t.peso, 1), '100,0'], (li) => li.titulo)));

  if ((L.perfis || []).length) {
    const totB = L.perfis.reduce((s, g) => s + g.barras.quantidade, 0);
    c.append(secao('Perfis', `comprimento, peso e barras comerciais por encaixe (do maior para o menor, 3 mm de corte); ${n(totB)} barras no total`,
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Perfil', chave: 'perfil', classe: 'b' }, { titulo: 'Material', chave: 'material' },
        { titulo: 'Categoria', valor: (g) => rotuloCategoria(g.categoria) },
        { titulo: 'Posições', valor: (g) => marcas(g.posicoes), classe: 'quebra' },
        { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
        { titulo: 'Compr. (m)', chave: 'comprimento_m', classe: 'r', num: true, casas: 2 },
        { titulo: 'kg/m', chave: 'kg_m', classe: 'r', num: true, casas: 2 },
        { titulo: 'Peso (kg)', chave: 'peso', classe: 'r b', num: true, casas: 1 },
        { titulo: 'Barra', valor: (g) => `${n(g.barras.comprimento / 1000)} m`, classe: 'c' },
        { titulo: 'Barras', valor: (g) => g.barras.quantidade, classe: 'c b', num: true },
        { titulo: 'Aprov. (%)', valor: (g) => g.barras.aproveitamento, classe: 'c', num: true, casas: 1 },
        { titulo: 'Sobra (m)', valor: (g) => g.barras.sobra_m, classe: 'r', num: true, casas: 2 },
        { titulo: 'Emendas', valor: (g) => g.barras.emendas, classe: 'c', num: true, dica: 'Peças mais compridas que a barra comercial' },
      ], L.perfis, ['TOTAL', '', '', '', n(L.perfis.reduce((s, g) => s + g.pecas, 0)), n(L.perfis.reduce((s, g) => s + g.comprimento_m, 0), 2), '',
                    n(L.perfis.reduce((s, g) => s + g.peso, 0), 1), '', n(totB), '', '', ''],
      (g) => [g.perfil, g.material, g.posicoes.join(' ')].join(' ')))));
  }

  if ((L.chapas || []).length) {
    c.append(secao('Chapas', 'por espessura e material; área = contorno (ou desenvolvimento, na dobrada) × quantidade',
      tabela([
        { titulo: 'Espessura (mm)', chave: 'espessura', classe: 'c b', num: true, casas: 1 }, { titulo: 'Material', chave: 'material' },
        { titulo: 'Posições', valor: (g) => marcas(g.posicoes, 30), classe: 'quebra' },
        { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
        { titulo: 'Área (m²)', chave: 'area_m2', classe: 'r', num: true, casas: 2 },
        { titulo: 'Peso (kg)', chave: 'peso', classe: 'r b', num: true, casas: 1 },
      ], L.chapas, ['TOTAL', '', '', n(L.chapas.reduce((s, g) => s + g.pecas, 0)), n(L.chapas.reduce((s, g) => s + g.area_m2, 0), 2),
                    n(L.chapas.reduce((s, g) => s + g.peso, 0), 1)],
      (g) => [g.espessura, g.material, g.posicoes.join(' ')].join(' '))));
  }

  if ((L.telhas || []).length) {
    c.append(secao('Telhas', null, tabela([
      { titulo: 'Perfil', chave: 'perfil', classe: 'b' }, { titulo: 'Posições', valor: (g) => marcas(g.posicoes, 30), classe: 'quebra' },
      { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true }, { titulo: 'Compr. (m)', chave: 'comprimento_m', classe: 'r', num: true, casas: 2 },
      { titulo: 'Área (m²)', chave: 'area_m2', classe: 'r', num: true, casas: 2 }, { titulo: 'Peso (kg)', chave: 'peso', classe: 'r', num: true, casas: 1 },
    ], L.telhas, null, (g) => [g.perfil, g.posicoes.join(' ')].join(' '))));
  }

  if ((L.conjuntos || []).length) {
    c.append(secao('Conjuntos', 'montagens (tesouras, vigas, pilares): instâncias pela composição e peso de cada uma',
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Nome', chave: 'nome', classe: 'b' }, { titulo: 'Conjunto', chave: 'marca' }, { titulo: 'Tipo', valor: (x) => rotuloCategoria(x.categoria) },
        { titulo: 'Instâncias', chave: 'instancias', classe: 'c b', num: true },
        { titulo: 'Peças/un.', chave: 'pecas_unidade', classe: 'c', num: true },
        { titulo: 'Composição', chave: 'composicao_texto', classe: 'quebra mono' },
        { titulo: 'Peso un. (kg)', chave: 'peso_unitario', classe: 'r', num: true, casas: 1 },
        { titulo: 'Peso total (kg)', chave: 'peso_total', classe: 'r b', num: true, casas: 1 },
      ], L.conjuntos, ['TOTAL', '', '', n(L.conjuntos.reduce((s, x) => s + x.instancias, 0)), '', '', '', n(L.conjuntos.reduce((s, x) => s + x.peso_total, 0), 1)],
      (x) => [x.nome, x.marca, x.composicao_texto].join(' ')))));
  }

  c.append(secao('Romaneio por posição', `${n(t.posicoes)} posições · ${n(t.pecas)} peças`,
    el('div', { class: 'rolagem' }, tabela([
      { titulo: 'Nome', chave: 'nome', classe: 'b' }, { titulo: 'Posição', chave: 'marca' }, { titulo: 'Categoria', valor: (p_) => rotuloCategoria(p_.categoria) },
      { titulo: 'Tipo', chave: 'classe' }, { titulo: 'Perfil / chapa', chave: 'perfil' }, { titulo: 'Material', chave: 'material' },
      { titulo: 'Qtd', chave: 'quantidade', classe: 'c b', num: true },
      { titulo: 'Compr. (mm)', chave: 'comprimento', classe: 'r', num: true },
      { titulo: 'Larg. (mm)', valor: (p_) => p_.largura || null, classe: 'r', num: true },
      { titulo: 'Esp. (mm)', valor: (p_) => p_.espessura || null, classe: 'r', num: true, casas: 1 },
      { titulo: 'Furos', valor: (p_) => p_.furos || '—' },
      { titulo: 'Parafusos', valor: (p_) => p_.parafusos || '—', classe: 'quebra' },
      { titulo: 'Peso un. (kg)', chave: 'peso', classe: 'r', num: true, casas: 2 },
      { titulo: 'Peso tot. (kg)', chave: 'peso_total', classe: 'r b', num: true, casas: 1 },
      { titulo: 'Conjuntos', valor: (p_) => marcas(p_.conjuntos, 10), classe: 'quebra' },
      { titulo: 'Obs.', valor: (p_) => (p_.observacoes || []).join('; ') || '', classe: 'quebra' },
    ], L.posicoes || [], ['TOTAL', '', '', '', '', '', n(t.pecas), '', '', '', '', '', '', n(t.peso, 1), '', ''],
    (p_) => [p_.nome, p_.marca, p_.perfil, p_.material, p_.classe, (p_.conjuntos || []).join(' ')].join(' ')))));

  if ((L.acessorios || []).length) {
    c.append(secao('Acessórios', 'só na lista: parafusos, porcas, arruelas (não são desenhados)', tabela([
      { titulo: 'Item', chave: 'nome' }, { titulo: 'Quantidade', chave: 'quantidade', classe: 'c b', num: true },
    ], L.acessorios, null, (a) => a.nome)));
  }

  if ((L.ressalvas || []).length) {
    c.append(secao('Observações do detalhamento', 'conferir antes de mandar cortar',
      el('ul', { class: 'ressalvas' }, L.ressalvas.map(r => el('li', {}, el('b', { texto: r.marca + ' ' }), r.perfil + ' — ' + r.observacoes.join('; '))))));
  }
  filtrar();
}

const CATEGORIAS = { TESOURAS: 'Tesoura/pórtico', CONJUNTOS: 'Conjunto', 'TERÇAS': 'Terça', BARRAS: 'Barra', CHAPAS: 'Chapa',
                     TIRANTES: 'Tirante', TELHAS: 'Telha', VISTAS: 'Vista', OUTROS: 'Outro' };
const rotuloCategoria = (k) => CATEGORIAS[k] || k || '—';

function cartao(valor, rotulo) {
  return el('div', { class: 'cartao-n' }, el('b', { texto: valor }), el('span', { texto: rotulo }));
}

function filtrar() {
  const termo = ($('#filtro').value || '').trim().toLowerCase();
  for (const tr of document.querySelectorAll('.materiais tbody tr[data-filtro]')) {
    tr.classList.toggle('oculta', !!termo && !tr.dataset.filtro.includes(termo));
  }
}

/* ------------------------------------------------------------------- ações */
async function carregar(recalcular = false) {
  if (!PROJETO) { aviso('Abra a lista por um projeto (gerenciador → projeto → Lista de materiais).', true); return; }
  aviso(recalcular ? 'Levantando as peças do modelo…' : 'Carregando…');
  try {
    const L = recalcular
      ? await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais`, { barra: Number($('#barra').value) || 0 })
      : await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais`);
    aviso('');
    desenhar(L);
  } catch (e) {
    aviso(`Não foi possível montar a lista: ${e.message}`, true);
  }
}

async function gerarPDF() {
  const b = $('#btn-pdf');
  b.disabled = true;
  aviso('Imprimindo o PDF…');
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais/pdf`, {});
    aviso('');
    window.open(r.pdf.url, '_blank');
    if (LISTA) { LISTA.arquivos = Object.assign(LISTA.arquivos || {}, { pdf: r.pdf }); desenhar(LISTA); }
  } catch (e) {
    aviso(`Não foi possível gerar o PDF: ${e.message}`, true);
  } finally { b.disabled = false; }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-3d').addEventListener('click', () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-cad').addEventListener('click', () => { location.href = `/cad?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-recalcular').addEventListener('click', () => carregar(true));
  $('#barra').addEventListener('change', () => carregar(true));
  $('#btn-pdf').addEventListener('click', gerarPDF);
  $('#btn-imprimir').addEventListener('click', () => window.print());
  $('#btn-pasta').addEventListener('click', () => pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/abrir-pasta`, { sub: 'detalhamento' }).catch(e => aviso(e.message, true)));
  $('#filtro').addEventListener('input', filtrar);
  carregar(false);
});
