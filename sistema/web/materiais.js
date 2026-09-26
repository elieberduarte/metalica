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
      // coluna que mostra um elemento (as marcas das posições e dos conjuntos) ordena pelo
      // texto dele, não por "[object HTMLSpanElement]"
      td.dataset.v = c.num ? String(Number(v) || 0)
        : (v && v.nodeType ? (v.getAttribute && v.getAttribute('title')) || v.textContent || '' : String(v ?? ''));
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
  return el('section', {}, el('h3', {}, titulo, sub ? el('small', { texto: sub }) : null), conteudo);
}

function marcas(lista, max = 14) {
  const s = lista.slice(0, max).join(' ');
  return el('span', { class: 'mono', title: lista.join(' '), texto: s + (lista.length > max ? ' …' : '') });
}

const vazio = (texto) => el('div', { class: 'vazio', texto });

// o seletor da barra de compra vai para dentro do quadro Perfis, que é refeito a cada
// desenho: guardado aqui, ele sobrevive ao redesenho (antes, depois de gerar o PDF, a
// tela procurava #barra fora do documento e dava "Cannot read properties of null")
let SELETOR_BARRA = null, CONTROLE_BARRA = null;
const seletorBarra = () => (SELETOR_BARRA = SELETOR_BARRA || $('#barra'));
const controleBarra = () => (CONTROLE_BARRA = CONTROLE_BARRA || $('#controle-barra'));

const dataBR = (iso) => {
  const m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
  return m ? `${m[3]}/${m[2]}/${m[1]}${m[4] ? ` ${m[4]}:${m[5]}` : ''}` : '—';
};

/* ------------------------------------------------------------------- abas */
// cada aba: [chave, título, função que monta o conteúdo (ou null se não há nada)]
const ABAS = [
  ['geral', 'Visão geral'], ['perfis', 'Perfis'], ['corte', 'Plano de corte'], ['chapas', 'Chapas'], ['telhas', 'Telhas e rufos'],
  ['conjuntos', 'Conjuntos'], ['romaneio', 'Romaneio'], ['acessorios', 'Acessórios'],
  ['resumos', 'Resumos da obra'], ['arquivos', 'Arquivos'],
];
const COM_FILTRO = new Set(['perfis', 'corte', 'chapas', 'telhas', 'conjuntos', 'romaneio', 'acessorios']);
let ABA = 'geral';
try { ABA = (location.hash || '').slice(1) || localStorage.getItem('materiais.aba') || 'geral'; } catch (e) { /* sem armazenamento */ }
if (!ABAS.some(([k]) => k === ABA)) ABA = 'geral';

function montarAbas(contagem) {
  const nav = $('#abas');
  const busca = el('input', { type: 'search', id: 'filtro', placeholder: 'Filtrar posição, perfil, conjunto…', title: 'Filtra as linhas dos quadros desta aba' });
  busca.addEventListener('input', filtrar);
  const anterior = $('#filtro');
  if (anterior) busca.value = anterior.value;
  nav.replaceChildren(...ABAS.map(([k, t]) => el('button', { type: 'button', class: k === ABA ? 'ativa' : '', 'data-aba': k, onclick: () => irPara(k) },
    t, contagem[k] ? el('span', { class: 'qtd', texto: n(contagem[k]) }) : null)), el('span', { class: 'sep' }), busca);
  busca.hidden = !COM_FILTRO.has(ABA);
}

function irPara(k) {
  ABA = k;
  try { localStorage.setItem('materiais.aba', k); } catch (e) { /* sem armazenamento */ }
  history.replaceState(null, '', location.pathname + location.search + '#' + k);
  for (const b of document.querySelectorAll('#abas button[data-aba]')) b.classList.toggle('ativa', b.dataset.aba === k);
  for (const p of document.querySelectorAll('.painel-aba')) p.hidden = p.dataset.aba !== k;
  const busca = $('#filtro');
  if (busca) busca.hidden = !COM_FILTRO.has(k);
  if (k === 'resumos') abrirResumos();
  filtrar();
}

/* ------------------------------------------------------------------- tela */
function pesoCategoria(t, cat) {
  const c = (t.categorias || []).find(x => x.categoria === cat);
  return c ? c.peso : 0;
}

function desenhar(L) {
  LISTA = L;
  const t = L.totais || {};
  const p = L.projeto || {};
  $('#sub-projeto').textContent = p.nome || PROJETO;
  document.title = `Lista de materiais — ${p.nome || PROJETO}`;
  $('#quando').textContent = L.gerado ? `levantada em ${dataBR(L.gerado)}` : '—';
  $('#quando').title = 'Quando a lista foi levantada do modelo 3D. Depois de mudar o modelo, use "Atualizar pelo modelo 3D".';
  if (seletorBarra()) seletorBarra().value = String(L.barra || 0);
  $('#obra-nome').textContent = p.nome || PROJETO;
  $('#obra-sub').textContent = [p.cliente, p.local, L.gerado ? `lista levantada do modelo 3D em ${dataBR(L.gerado)}` : null].filter(Boolean).join(' · ') || '—';

  const telhas = pesoCategoria(t, 'TELHAS'), rufos = pesoCategoria(t, 'RUFOS');
  const aco = (t.peso || 0) - telhas - rufos;
  const mlTelhas = (L.telhas || []).reduce((s, g) => s + (g.comprimento_m || 0), 0);
  const barrasCompra = (L.perfis || []).reduce((s, g) => s + (g.barras?.quantidade || 0), 0);
  $('#cartoes').replaceChildren(
    cartao(n(aco, 1) + ' kg', 'aço (estrutura)', 'perfis, barras e chapas', true),
    cartao(n(telhas, 1) + ' kg', 'telhas', mlTelhas ? `${n(mlTelhas, 1)} m de telha` : (rufos ? `+ ${n(rufos, 1)} kg de rufos` : null)),
    cartao(n(t.pecas), 'peças', `${n(t.posicoes)} posições`),
    cartao(n(t.conjuntos), 'conjuntos', 'tesouras, vigas, dispositivos'),
    cartao(n(barrasCompra), 'barras de compra', 'pelo encaixe das peças'),
    cartao(n(t.acessorios), 'acessórios', 'parafusos, porcas, arruelas'));

  const c = $('#conteudo');
  c.replaceChildren();
  const painel = (k, ...filhos) => el('div', { class: 'painel-aba', 'data-aba': k, id: 'aba-' + k, hidden: k !== ABA }, ...filhos);
  const contagem = { corte: (L.perfis || []).reduce((s, g) => s + (g.barras?.quantidade || 0), 0), perfis: (L.perfis || []).length, chapas: (L.chapas || []).length, telhas: (L.telhas || []).length,
                     conjuntos: (L.conjuntos || []).length, romaneio: (L.posicoes || []).length, acessorios: (L.acessorios || []).length };

  // ---- visão geral
  const cats = (t.categorias || []).filter(x => x.peso > 0).sort((a, b) => b.peso - a.peso);
  const maxCat = Math.max(1, ...cats.map(x => x.peso));
  const barrasCat = el('div', { class: 'barras-peso' }, cats.map(x => [
    el('span', { class: 'nome', texto: x.titulo, title: `${n(x.posicoes)} posições · ${n(x.pecas)} peças` }),
    el('span', { class: 'trilho' }, el('i', { class: x.categoria === 'TELHAS' || x.categoria === 'RUFOS' ? 'telha' : '', style: `width:${(100 * x.peso / maxCat).toFixed(1)}%` })),
    el('span', { class: 'kg' }, el('b', { texto: n(x.peso, 1) + ' kg' }), ` · ${n(x.pct, 1)}%`),
  ]).flat());
  const perfisTop = (L.perfis || []).slice().sort((a, b) => b.peso - a.peso).slice(0, 8);
  const maxP = Math.max(1, ...perfisTop.map(g => g.peso));
  const barrasPerfil = el('div', { class: 'barras-peso' }, perfisTop.map(g => [
    el('span', { class: 'nome mono', texto: g.perfil, title: g.posicoes.join(' ') }),
    el('span', { class: 'trilho' }, el('i', { style: `width:${(100 * g.peso / maxP).toFixed(1)}%` })),
    el('span', { class: 'kg' }, el('b', { texto: n(g.peso, 1) + ' kg' }), ` · ${n(g.barras?.quantidade || 0)} barras`),
  ]).flat());
  const ressalvas = (L.ressalvas || []);
  c.append(painel('geral', el('div', { class: 'grade-geral' },
    el('div', { class: 'caixa' }, el('h3', {}, 'Peso por categoria', el('small', { texto: `total ${n(t.peso, 1)} kg · aço ${n(aco, 1)} kg` })),
      cats.length ? barrasCat : vazio('Sem peças levantadas.'),
      el('p', { class: 'nota', texto: 'As telhas (cinza) e os rufos entram no total geral, mas não no peso da estrutura metálica.' })),
    el('div', { class: 'caixa' }, el('h3', {}, 'Perfis que mais pesam', el('small', { texto: `${n((L.perfis || []).length)} perfis` })),
      perfisTop.length ? barrasPerfil : vazio('Sem perfis.'),
      el('div', { class: 'passos' },
        el('button', { type: 'button', class: 'botao-m', onclick: () => irPara('perfis'), texto: 'Ver todos os perfis' }),
        el('button', { type: 'button', class: 'botao-m', onclick: () => irPara('romaneio'), texto: 'Romaneio por posição' }),
        el('button', { type: 'button', class: 'botao-m principal', onclick: () => irPara('resumos'), texto: 'Gerar os resumos da obra' }))),
    ressalvas.length ? el('div', { class: 'caixa', style: 'grid-column: 1 / -1' },
      el('h3', {}, 'Observações do detalhamento', el('small', { texto: 'conferir antes de mandar cortar' })),
      el('ul', { class: 'lista-simples' }, ressalvas.slice(0, 40).map(r => el('li', {}, el('b', { texto: r.marca + ' ' }), r.perfil + ' — ' + r.observacoes.join('; '))))) : null)));

  // ---- perfis (e os dobrados)
  const pPerfis = painel('perfis');
  if ((L.perfis || []).length) {
    const totB = barrasCompra;
    controleBarra().hidden = false;
    pPerfis.append(secao('Perfis', `comprimento, peso e barras de compra por encaixe (do maior para o menor, 3 mm de corte); ${n(totB)} barras no total`,
      el('div', {}, controleBarra(), el('div', { class: 'rolagem' }, tabela([
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
      (g) => [g.perfil, g.material, g.posicoes.join(' ')].join(' '))))));
  } else pPerfis.append(vazio('Sem perfis nesta lista.'));
  const dob = L.dobrados || {};
  if ((dob.linhas || []).length) {
    const td = dob.totais || {};
    pPerfis.append(secao('Perfis dobrados: peso teórico × com desconto das dobras',
      'teórico = soma das medidas externas × espessura; com desconto = tira desenvolvida (' + (dob.regra || '') + '). O peso do modelo é o da malha 3D (cantos vivos, furos descontados).',
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Perfil', chave: 'perfil', classe: 'b' },
        { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
        { titulo: 'Compr. (m)', chave: 'comprimento_m', classe: 'r', num: true, casas: 2 },
        { titulo: 'Dobras', chave: 'dobras', classe: 'c', num: true },
        { titulo: 'Soma ext. (mm)', chave: 'soma_externa', classe: 'r', num: true, casas: 1, dica: 'Soma das medidas externas da seção' },
        { titulo: 'Desenv. (mm)', chave: 'desenvolvido', classe: 'r b', num: true, casas: 1, dica: 'Largura da tira cortada da bobina' },
        { titulo: 'kg/m teórico', chave: 'kg_m_teorico', classe: 'r', num: true, casas: 3 },
        { titulo: 'kg/m c/ desc.', chave: 'kg_m_desconto', classe: 'r', num: true, casas: 3 },
        { titulo: 'kg/m NBR', valor: (d) => d.kg_m_norma, classe: 'r', num: true, casas: 2, dica: 'Tabela da NBR 6355 (catálogo), quando o perfil está nela' },
        { titulo: 'Peso modelo (kg)', chave: 'peso_modelo', classe: 'r', num: true, casas: 1 },
        { titulo: 'Peso teórico (kg)', chave: 'peso_teorico', classe: 'r', num: true, casas: 1 },
        { titulo: 'Peso c/ desc. (kg)', chave: 'peso_desconto', classe: 'r b', num: true, casas: 1 },
        { titulo: 'Dif. (kg)', chave: 'diferenca', classe: 'r', num: true, casas: 1 },
        { titulo: 'Dif. (%)', chave: 'diferenca_pct', classe: 'c', num: true, casas: 1 },
      ], dob.linhas, ['TOTAL', '', '', '', '', '', '', '', '', n(td.peso_modelo, 1), n(td.peso_teorico, 1), n(td.peso_desconto, 1), n(td.diferenca, 1), n(td.diferenca_pct, 1)],
      (d) => d.perfil))));
  }
  c.append(pPerfis);

  // ---- plano de corte: o que sai de cada barra, as barras iguais juntas, desenhadas em escala
  const pCorte = painel('corte');
  const comPlano = (L.perfis || []).filter(g => (g.barras?.plano || []).length);
  if (comPlano.length) {
    pCorte.append(el('p', { class: 'nota', texto: 'Encaixe do maior para o menor, com 3 mm de perda por corte. Cada linha é um jeito de cortar a barra; o número à esquerda diz quantas barras são cortadas assim. A parte hachurada é a sobra.' }));
    for (const g of comPlano) {
      const b = g.barras;
      const linhas = b.plano.map(pl => ({ ...pl, _g: g }));
      pCorte.append(secao(g.perfil, `barras de ${n(b.comprimento / 1000)} m · ${n(b.quantidade)} barras · aproveitamento ${n(b.aproveitamento, 1)}% · sobra ${n(b.sobra_m, 2)} m${b.emendas ? ` · ${b.emendas} peça(s) com emenda` : ''}`,
        tabela([
          { titulo: 'Barras', chave: 'barras', classe: 'c b', num: true },
          { titulo: 'Cortes', valor: (pl) => barraDesenhada(pl, b.comprimento), classe: 'quebra corte-celula' },
          { titulo: 'Sobra (mm)', chave: 'sobra', classe: 'r', num: true },
        ], linhas, null, (pl) => [g.perfil, ...pl.cortes.map(c => c.nome)].join(' '))));
    }
  } else pCorte.append(vazio('Sem perfis para cortar nesta lista. Use "Atualizar pelo modelo 3D" para levantar o plano de corte.'));
  c.append(pCorte);

  // ---- chapas
  c.append(painel('chapas', (L.chapas || []).length
    ? secao('Chapas', 'por espessura e material; área = contorno (ou desenvolvimento, na dobrada) × quantidade',
      tabela([
        { titulo: 'Espessura (mm)', chave: 'espessura', classe: 'c b', num: true, casas: 1 }, { titulo: 'Material', chave: 'material' },
        { titulo: 'Posições', valor: (g) => marcas(g.posicoes, 30), classe: 'quebra' },
        { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
        { titulo: 'Área (m²)', chave: 'area_m2', classe: 'r', num: true, casas: 2 },
        { titulo: 'Peso (kg)', chave: 'peso', classe: 'r b', num: true, casas: 1 },
      ], L.chapas, ['TOTAL', '', '', n(L.chapas.reduce((s, g) => s + g.pecas, 0)), n(L.chapas.reduce((s, g) => s + g.area_m2, 0), 2),
                    n(L.chapas.reduce((s, g) => s + g.peso, 0), 1)],
      (g) => [g.espessura, g.material, g.posicoes.join(' ')].join(' ')))
    : vazio('Sem chapas nesta lista.')));

  // ---- telhas (e rufos, que estão no romaneio pela categoria)
  const pTelhas = painel('telhas');
  if ((L.telhas || []).length) {
    pTelhas.append(secao('Telhas', null, tabela([
      { titulo: 'Perfil', valor: (g) => g.perfil + (g.largura ? ` · larg. ${g.largura_total || g.largura} (útil ${g.largura})` : ''), classe: 'b' },
      { titulo: 'Chapas inteiras (qtd × compr. mm)', valor: (g) => g.chapas_texto || '', classe: 'quebra' },
      { titulo: 'Posições', valor: (g) => marcas(g.posicoes, 30), classe: 'quebra' },
      { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true }, { titulo: 'Compr. (m)', chave: 'comprimento_m', classe: 'r', num: true, casas: 2 },
      { titulo: 'Área (m²)', chave: 'area_m2', classe: 'r', num: true, casas: 2 }, { titulo: 'Peso (kg)', chave: 'peso', classe: 'r', num: true, casas: 1 },
    ], L.telhas, null, (g) => [g.perfil, g.posicoes.join(' ')].join(' '))));
  }
  const rufos_ = (L.posicoes || []).filter(x => x.categoria === 'RUFOS');
  if (rufos_.length) {
    pTelhas.append(secao('Rufos e calhas', 'funilaria de aluzinc: fora do peso da estrutura', tabela([
      { titulo: 'Nome', chave: 'nome', classe: 'b' }, { titulo: 'Perfil', chave: 'perfil' },
      { titulo: 'Qtd', chave: 'quantidade', classe: 'c b', num: true }, { titulo: 'Compr. (mm)', chave: 'comprimento', classe: 'r', num: true },
      { titulo: 'Peso tot. (kg)', chave: 'peso_total', classe: 'r b', num: true, casas: 1 },
    ], rufos_, null, (x) => [x.nome, x.perfil].join(' '))));
  }
  if (!pTelhas.children.length) pTelhas.append(vazio('Sem telhas nem rufos nesta lista.'));
  c.append(pTelhas);

  // ---- conjuntos
  c.append(painel('conjuntos', (L.conjuntos || []).length
    ? secao('Conjuntos', 'montagens (tesouras, vigas, pilares): instâncias pela composição e peso de cada uma',
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Nome', chave: 'nome', classe: 'b' }, { titulo: 'Conjunto', chave: 'marca' }, { titulo: 'Tipo', valor: (x) => rotuloCategoria(x.categoria) },
        { titulo: 'Instâncias', chave: 'instancias', classe: 'c b', num: true },
        { titulo: 'Peças/un.', chave: 'pecas_unidade', classe: 'c', num: true },
        { titulo: 'Composição', chave: 'composicao_texto', classe: 'quebra mono' },
        { titulo: 'Peso un. (kg)', chave: 'peso_unitario', classe: 'r', num: true, casas: 1 },
        { titulo: 'Peso total (kg)', chave: 'peso_total', classe: 'r b', num: true, casas: 1 },
      ], L.conjuntos, ['TOTAL', '', '', n(L.conjuntos.reduce((s, x) => s + x.instancias, 0)), '', '', '', n(L.conjuntos.reduce((s, x) => s + x.peso_total, 0), 1)],
      (x) => [x.nome, x.marca, x.composicao_texto].join(' '))))
    : vazio('Sem conjuntos nesta lista.')));

  // ---- romaneio
  c.append(painel('romaneio', secao('Romaneio por posição', `${n(t.posicoes)} posições · ${n(t.pecas)} peças`,
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
    (p_) => [p_.nome, p_.marca, p_.perfil, p_.material, p_.classe, (p_.conjuntos || []).join(' ')].join(' '))))));

  // ---- acessórios
  c.append(painel('acessorios', (L.acessorios || []).length
    ? secao('Acessórios', 'só na lista: parafusos, porcas, arruelas (não são desenhados)', tabela([
      { titulo: 'Item', chave: 'nome' }, { titulo: 'Quantidade', chave: 'quantidade', classe: 'c b', num: true },
    ], L.acessorios, ['TOTAL', n(L.acessorios.reduce((s, a) => s + a.quantidade, 0))], (a) => a.nome))
    : vazio('Sem acessórios nesta lista.')));

  // ---- resumos da obra (montado ao abrir a aba)
  c.append(painel('resumos', el('div', { id: 'resumos-corpo' }, vazio('Carregando os resumos…'))));
  RESUMOS_MONTADO = false;

  // ---- arquivos
  c.append(painel('arquivos', el('div', { id: 'arquivos-corpo' })));
  desenharArquivos();

  montarAbas(contagem);
  if (ABA === 'resumos') abrirResumos();
  filtrar();
}

/** A barra em escala: um segmento por peça (nome e comprimento), e a sobra hachurada. */
function barraDesenhada(pl, comprimento) {
  const barra = el('div', { class: 'barra-corte', title: pl.cortes.map(c => `${c.qtd}× ${c.nome || 'peça'} ${n(c.comprimento)} mm`).join(' + ') + ` · sobra ${n(pl.sobra)} mm` });
  for (const c of pl.cortes) {
    for (let i = 0; i < c.qtd; i++) {
      const pct = 100 * c.comprimento / comprimento;
      barra.append(el('span', { class: 'seg' + (/emenda/.test(c.nome) ? ' emenda' : ''), style: `width:${pct.toFixed(2)}%`, title: `${c.nome || 'peça'} · ${n(c.comprimento)} mm` },
        pct > 4 ? el('b', { texto: c.nome || 'peça' }) : null, pct > 12 ? el('small', { texto: n(c.comprimento) }) : null));
    }
  }
  if (pl.sobra > 0) barra.append(el('span', { class: 'sobra', style: `width:${(100 * pl.sobra / comprimento).toFixed(2)}%`, title: `sobra ${n(pl.sobra)} mm` }));
  // embaixo, o mesmo em texto: peça curta demais para o nome caber no desenho aparece aqui
  const legenda = el('div', { class: 'cortes-texto', texto: pl.cortes.map(c => `${c.qtd}× ${c.nome || 'peça'} ${n(c.comprimento)}`).join(' + ') });
  return el('div', {}, barra, legenda);
}

const CATEGORIAS = { TESOURAS: 'Tesoura/pórtico', CONJUNTOS: 'Conjunto', 'TERÇAS': 'Terça', BARRAS: 'Barra', CHAPAS: 'Chapa',
                     TIRANTES: 'Tirante', TELHAS: 'Telha', RUFOS: 'Rufo/calha', VISTAS: 'Vista', OUTROS: 'Outro' };
const rotuloCategoria = (k) => CATEGORIAS[k] || k || '—';

function cartao(valor, rotulo, sub = null, destaque = false) {
  return el('div', { class: 'cartao-n' + (destaque ? ' destaque' : '') }, el('b', { texto: valor }), el('span', { texto: rotulo }), sub ? el('small', { texto: sub }) : null);
}

function filtrar() {
  const campo = $('#filtro');
  const termo = ((campo && !campo.hidden && campo.value) || '').trim().toLowerCase();
  for (const tr of document.querySelectorAll('.materiais tbody tr[data-filtro]')) {
    tr.classList.toggle('oculta', !!termo && !tr.dataset.filtro.includes(termo));
  }
}

/* ------------------------------------------------------------------- arquivos */
const DESCRICOES = {
  romaneio: ['romaneio.csv', 'Romaneio por posição (Excel)'], perfis: ['resumo-perfis.csv', 'Perfis com barras de compra (Excel)'],
  dobras: ['peso-dobras.csv', 'Perfis dobrados: peso teórico × com desconto (Excel)'], chapas: ['resumo-chapas.csv', 'Chapas por espessura (Excel)'],
  conjuntos: ['conjuntos.csv', 'Conjuntos e composição (Excel)'], plano_corte: ['plano-de-corte.csv', 'Plano de corte: o que sai de cada barra (Excel)'], html: ['Lista (HTML)', 'Esta lista, para abrir no navegador'],
  pdf: ['Lista (PDF)', 'Esta lista em PDF, para imprimir'],
};

function desenharArquivos() {
  const alvo = $('#arquivos-corpo');
  if (!alvo) return;
  const linhas = [];
  const arq = (LISTA && LISTA.arquivos) || {};
  for (const [k, [rot, desc]] of Object.entries(DESCRICOES)) if (arq[k]) linhas.push({ rot, desc, a: arq[k] });
  const res = (RESUMOS && RESUMOS.arquivos) || {};
  for (const [k, rot] of [['obra', 'Resumo da obra'], ['materiais', 'Resumo de materiais']]) {
    for (const ext of ['pdf', 'html']) if (res[k] && res[k][ext]) linhas.push({ rot: `${rot} (${ext.toUpperCase()})`, desc: ext === 'pdf' ? 'Documento para a fábrica' : 'O mesmo, no navegador', a: res[k][ext] });
  }
  if (!linhas.length) { alvo.replaceChildren(vazio('Nenhum arquivo gerado ainda. "Atualizar pelo modelo 3D" grava a lista e os CSVs; os resumos saem na aba Resumos da obra.')); return; }
  alvo.replaceChildren(secao('Arquivos do projeto', 'tudo fica na pasta detalhamento/ do projeto',
    el('div', {}, tabela([
      { titulo: 'Arquivo', valor: (x) => el('a', { href: x.a.url, target: '_blank', rel: 'noopener', texto: x.rot }), classe: 'b' },
      { titulo: 'O que é', chave: 'desc', classe: 'quebra' },
      { titulo: 'Nome no disco', valor: (x) => x.a.nome, classe: 'mono' },
      { titulo: 'Tamanho (kB)', valor: (x) => x.a.tamanho_kb, classe: 'r', num: true, casas: 1 },
      { titulo: 'Gerado em', valor: (x) => dataBR(x.a.alterado) },
    ], linhas, null, (x) => x.rot),
    el('div', { class: 'passos' }, el('button', { type: 'button', class: 'botao-m', onclick: abrirPasta, texto: 'Abrir a pasta detalhamento/' })))));
}

/* ------------------------------------------------------------------- ações */
async function carregar(recalcular = false) {
  if (!PROJETO) { aviso('Abra a lista por um projeto (gerenciador → projeto → Lista de materiais).', true); return; }
  aviso(recalcular ? 'Levantando as peças do modelo…' : 'Carregando…');
  try {
    const L = recalcular
      ? await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais`, { barra: Number(seletorBarra() ? seletorBarra().value : 0) || 0 })
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
  aviso('Imprimindo o PDF da lista…');
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais/pdf`, {});
    if (LISTA) { LISTA.arquivos = Object.assign(LISTA.arquivos || {}, { pdf: r.pdf }); desenharArquivos(); }
    avisoComLinks(`Lista em PDF gravada em detalhamento/${r.pdf.nome}.`, [[r.pdf.url, 'Abrir o PDF']]);
  } catch (e) {
    aviso(`Não foi possível gerar o PDF: ${e.message}`, true);
  } finally { b.disabled = false; }
}

function abrirPasta() {
  pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/abrir-pasta`, { sub: 'detalhamento' }).catch(e => aviso(e.message, true));
}

function avisoComLinks(texto, links, tipo = 'ok') {
  const caixa = $('#aviso');
  caixa.hidden = false;
  caixa.className = 'aviso-topo ' + tipo;
  caixa.replaceChildren(texto, ' ', ...links.flatMap(([url, rot], i) => [i ? ' · ' : '', el('a', { href: url, target: '_blank', rel: 'noopener', texto: rot })]),
    ' · ', el('a', { href: '#', onclick: (ev) => { ev.preventDefault(); abrirPasta(); }, texto: 'Abrir a pasta' }));
}

/* ------------------------------------------------------------ resumos da obra */
const CAMPOS_RESUMO = [
  ['revisao', 'Revisão do projeto', 'ex.: R11', false],
  ['data', 'Data', 'dd/mm/aaaa', false],
  ['descricao', 'Descrição do projeto', 'ex.: Projeto de fabricação da cobertura metálica', false],
  ['telha', 'Telha (descrição comercial)', 'ex.: Telha TP40 #0,50 Aluzinc RAL 1015 (bege)', false],
  ['eixos', 'Eixos das tesouras', 'letras na ordem ao longo do galpão, separadas por vírgula (ex.: A, C, E, G); vazio = A, B, C…', false],
  ['notas_tesouras', 'Notas das tesouras', 'ex.: canto quinado; 2 meias-tesouras emendadas na cumeeira; T3 e T5 são as dos oitões', true],
];
let RESUMOS = null, RESUMOS_MONTADO = false, DOC_ATUAL = 'obra', ULTIMOS_NUMEROS = null;

async function abrirResumos(forcar = false) {
  if (RESUMOS_MONTADO && !forcar) return;
  RESUMOS_MONTADO = true;
  try { RESUMOS = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/resumos`); }
  catch (e) { $('#resumos-corpo').replaceChildren(vazio(`Não foi possível ler os dados dos resumos: ${e.message}`)); return; }
  desenharResumos();
  desenharArquivos();
}

function desenharResumos() {
  const corpo = $('#resumos-corpo');
  if (!corpo) return;
  const entradas = {};
  const form = el('form', { class: 'form-resumo' });
  for (const [id, rotulo, dica, longa] of CAMPOS_RESUMO) {
    entradas[id] = el(longa ? 'textarea' : 'input', { placeholder: dica, spellcheck: 'false', title: dica });
    entradas[id].value = (RESUMOS.dados || {})[id] || (RESUMOS.sugestoes || {})[id] || '';
    form.append(el('label', {}, rotulo, entradas[id]));
  }
  const botao = el('button', { type: 'submit', class: 'botao-m principal', texto: RESUMOS.arquivos && RESUMOS.arquivos.obra ? 'Gerar de novo' : 'Gerar os resumos' });
  const estado = el('div', { class: 'progresso', id: 'resumo-estado' });
  form.append(el('div', { class: 'passos' }, botao), estado);
  if (ULTIMOS_NUMEROS) form.append(numerosDoResumo(ULTIMOS_NUMEROS));
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const v = {};
    for (const [k, i] of Object.entries(entradas)) v[k] = i.value.trim();
    gerarResumos(v, botao, estado);
  });
  const esquerda = el('div', { class: 'caixa' }, el('h3', {}, 'Dados do resumo', el('small', { texto: 'o que o IFC não traz; fica gravado no projeto' })), form);
  corpo.replaceChildren(el('div', { class: 'grade-resumos' }, esquerda, el('div', { class: 'caixa doc-previa', id: 'doc-previa' })));
  desenharPrevia();
}

function numerosDoResumo(nums) {
  const cx = (v, r) => el('div', {}, el('b', { texto: v }), r);
  return el('div', { class: 'numeros-resumo' },
    cx(n(nums.tesouras), 'tesouras'), cx(n(nums.peso_aco, 1) + ' kg', 'estrutura metálica'),
    cx(n(nums.ml_telhas, 1) + ' m', 'telhas'), cx(n(nums.parafusos), 'parafusos'));
}

function desenharPrevia() {
  const alvo = $('#doc-previa');
  if (!alvo) return;
  const arq = (RESUMOS && RESUMOS.arquivos) || {};
  if (!arq.obra && !arq.materiais) {
    alvo.replaceChildren(el('h3', {}, 'Prévia'), vazio('Os resumos ainda não foram gerados. Preencha os dados ao lado e clique em "Gerar os resumos": os dois documentos aparecem aqui, e os PDFs ficam na pasta detalhamento/ do projeto.'));
    return;
  }
  if (!arq[DOC_ATUAL]) DOC_ATUAL = arq.obra ? 'obra' : 'materiais';
  const a = arq[DOC_ATUAL];
  const alternar = el('div', { class: 'alternar' },
    ...[['obra', 'Resumo da obra'], ['materiais', 'Resumo de materiais']].map(([k, t]) => el('button', { type: 'button', class: k === DOC_ATUAL ? 'ativa' : '', disabled: !arq[k], texto: t,
      onclick: () => { DOC_ATUAL = k; desenharPrevia(); } })));
  const quando = (a.pdf || a.html || {}).alterado;
  const frame = a.html ? el('iframe', { src: `${a.html.url}?t=${encodeURIComponent(quando || '')}`, title: 'Prévia do resumo' }) : vazio('Sem a versão HTML deste resumo.');
  alvo.replaceChildren(
    el('div', { class: 'doc-barra' }, alternar, el('span', { class: 'quando', texto: quando ? `gerado em ${dataBR(quando)}` : '' }), el('span', { class: 'sep' }),
      a.pdf ? el('a', { class: 'botao-m principal', href: a.pdf.url, target: '_blank', rel: 'noopener', texto: 'Abrir o PDF', title: `detalhamento/${a.pdf.nome}` }) : null,
      a.html ? el('button', { type: 'button', class: 'botao-m', texto: 'Imprimir', onclick: () => { try { frame.contentWindow.print(); } catch (e) { window.open(a.html.url, '_blank'); } } }) : null,
      el('button', { type: 'button', class: 'botao-m', texto: 'Abrir pasta', onclick: abrirPasta })),
    frame);
}

async function gerarResumos(valores, botao, estado) {
  botao.disabled = true;
  const rot = botao.textContent;
  botao.textContent = 'Gerando…';
  const mostrar = (txt) => estado.replaceChildren(el('span', { class: 'giro' }), txt);
  mostrar('levantando as peças do modelo…');
  // a etapa do servidor (levantamento, lista, resumos, PDFs) enquanto roda
  const vigia = setInterval(async () => {
    try { const p = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/progresso`); if (p.etapa) mostrar(p.etapa); } catch (e) { /* segue */ }
  }, 800);
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/resumos`, { dados: valores });
    clearInterval(vigia);
    ULTIMOS_NUMEROS = r.numeros || null;
    RESUMOS = Object.assign(RESUMOS || {}, { dados: r.dados || valores, arquivos: { obra: r.obra, materiais: r.materiais } });
    DOC_ATUAL = 'obra';
    const erros = ['obra', 'materiais'].map(k => r[k] && r[k].erro_pdf).filter(Boolean);
    desenharResumos();
    const est = $('#resumo-estado');
    if (est) est.replaceChildren(erros.length ? `Gerados, mas o PDF falhou: ${erros[0]}` : 'Pronto: os dois resumos estão na prévia ao lado e em PDF na pasta detalhamento/.');
    if ((r.avisos || []).length && est) est.append(el('div', { class: 'nota', texto: 'Avisos: ' + r.avisos.slice(0, 4).join(' · ') }));
    // a lista foi levantada de novo com os nomes atualizados: recarrega os quadros
    const L = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais`);
    RESUMOS_MONTADO = true;
    const guardado = RESUMOS;
    desenhar(L);
    RESUMOS = guardado; RESUMOS_MONTADO = true;
    desenharResumos();
    desenharArquivos();
  } catch (e) {
    clearInterval(vigia);
    estado.replaceChildren(`Não foi possível gerar os resumos: ${e.message}`);
    botao.disabled = false; botao.textContent = rot;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-resumos').addEventListener('click', () => irPara('resumos'));
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-3d').addEventListener('click', () => { location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-cad').addEventListener('click', () => { location.href = `/cad?projeto=${encodeURIComponent(PROJETO)}`; });
  $('#btn-recalcular').addEventListener('click', () => carregar(true));
  seletorBarra().addEventListener('change', () => carregar(true));
  controleBarra();
  $('#btn-voltar').addEventListener('click', () => {
    // volta para a tela de onde veio (CAD, 3D); aberta direto, vai ao modelo 3D
    if (document.referrer && new URL(document.referrer).origin === location.origin && history.length > 1) history.back();
    else location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
  });
  $('#btn-pdf').addEventListener('click', gerarPDF);
  $('#btn-imprimir').addEventListener('click', () => window.print());
  $('#btn-pasta').addEventListener('click', abrirPasta);
  carregar(false);
});
