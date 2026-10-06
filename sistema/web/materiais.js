/* Lista de materiais do projeto: a tela lê GET /api/projetos/<slug>/materiais (a lista
 * gravada pelo último detalhamento, ou levantada na hora do modelo) e mostra os quadros —
 * totais por categoria, perfis com barras comerciais, chapas por espessura, telhas,
 * conjuntos, romaneio por posição, acessórios e ressalvas. "Recalcular" refaz do modelo
 * (POST, com a barra comercial escolhida); "PDF" imprime pelo servidor (POST /materiais/pdf).
 * Os arquivos ficam em <projeto>/detalhamento/ — ver saida/lista_producao.py. */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);
const PROJETO = new URLSearchParams(location.search).get('projeto') || '';
// o orçamento mora na tela Comercial (03/10/2026): lá ele é este quadro, aberto com ?so=orcamento dentro da aba
// Orçamento; quem chega aqui por um link antigo (#orcamento) vai para lá
const SO_ORCAMENTO = new URLSearchParams(location.search).get('so') === 'orcamento';
if (SO_ORCAMENTO) document.documentElement.classList.add('so-orcamento');
else if (location.hash === '#orcamento') location.replace(`/comercial?projeto=${encodeURIComponent(PROJETO)}#orcamento`);

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
  ['orcamento', 'Orçamento'], ['resumos', 'Resumos da obra'], ['arquivos', 'Arquivos'],
];
const COM_FILTRO = new Set(['perfis', 'corte', 'chapas', 'telhas', 'conjuntos', 'romaneio', 'acessorios']);
let ABA = 'geral';
try { ABA = (location.hash || '').slice(1) || localStorage.getItem('materiais.aba') || 'geral'; } catch (e) { /* sem armazenamento */ }
if (SO_ORCAMENTO) ABA = 'orcamento';
else if (ABA === 'orcamento') ABA = 'geral';
if (!ABAS.some(([k]) => k === ABA)) ABA = 'geral';

function montarAbas(contagem) {
  const nav = $('#abas');
  const busca = el('input', { type: 'search', id: 'filtro', placeholder: 'Filtrar posição, perfil, conjunto…', title: 'Filtra as linhas dos quadros desta aba' });
  busca.addEventListener('input', filtrar);
  const anterior = $('#filtro');
  if (anterior) busca.value = anterior.value;
  nav.replaceChildren(...ABAS.filter(([k]) => k !== 'orcamento').map(([k, t]) => el('button', { type: 'button', class: k === ABA ? 'ativa' : '', 'data-aba': k, onclick: () => irPara(k) },
    t, contagem[k] ? el('span', { class: 'qtd', texto: n(contagem[k]) }) : null)), el('span', { class: 'sep' }), busca);
  busca.hidden = !COM_FILTRO.has(ABA);
}

// os atalhos da busca (Plano de corte, Romaneio…) trocam só o # desta tela
window.addEventListener('hashchange', () => {
  const k = location.hash.slice(1);
  if (k === 'orcamento' && !SO_ORCAMENTO) { location.replace(`/comercial?projeto=${encodeURIComponent(PROJETO)}#orcamento`); return; }
  if (k !== ABA && ABAS.some(([a]) => a === k)) irPara(k);
});

function irPara(k) {
  ABA = k;
  if (!SO_ORCAMENTO) try { localStorage.setItem('materiais.aba', k); } catch (e) { /* sem armazenamento */ }
  history.replaceState(null, '', location.pathname + location.search + '#' + k);
  for (const b of document.querySelectorAll('#abas button[data-aba]')) b.classList.toggle('ativa', b.dataset.aba === k);
  for (const p of document.querySelectorAll('.painel-aba')) p.hidden = p.dataset.aba !== k;
  const busca = $('#filtro');
  if (busca) busca.hidden = !COM_FILTRO.has(k);
  if (k === 'resumos') abrirResumos();
  if (k === 'orcamento') abrirOrcamento();
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
    el('span', { class: 'nome mono', texto: g.perfil_nome || g.perfil, title: g.posicoes.join(' ') }),
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
      el('ul', { class: 'lista-simples' }, ressalvas.slice(0, 40).map(r => el('li', {}, el('b', { texto: r.marca + ' ' }), (r.perfil_nome || r.perfil) + ' — ' + r.observacoes.join('; '))))) : null)));

  // ---- perfis (e os dobrados)
  const pPerfis = painel('perfis');
  if ((L.perfis || []).length) {
    const totB = barrasCompra;
    controleBarra().hidden = false;
    pPerfis.append(secao('Perfis', `comprimento, peso e barras de compra por encaixe (do maior para o menor, 3 mm de corte); ${n(totB)} barras no total`,
      el('div', {}, controleBarra(), el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Perfil', valor: (g) => g.perfil_nome || g.perfil, classe: 'b' },
        { titulo: 'No catálogo', valor: (g) => g.catalogo ? (g.fonte_kg_m === 'similar' ? 'similar: ' + g.catalogo : g.catalogo)
            : (g.fonte_kg_m === 'calculado' ? 'fora, sem similar (kg/m pelas medidas)' : '—'),
          dica: 'O item do catálogo que corresponde ao perfil do modelo; o tubo fora dele vai para o similar (mesma forma, lados até 12 % diferentes, área e inércias pelo menos as do projeto, o mais leve)' },
        { titulo: 'Material', chave: 'material' },
        { titulo: 'Categoria', valor: (g) => rotuloCategoria(g.categoria) },
        { titulo: 'Posições', valor: (g) => marcas(g.nomes_posicoes || g.posicoes), classe: 'quebra' },
        { titulo: 'Peças', chave: 'pecas', classe: 'c', num: true },
        { titulo: 'Compr. (m)', chave: 'comprimento_m', classe: 'r', num: true, casas: 2 },
        { titulo: 'kg/m', chave: 'kg_m', classe: 'r', num: true, casas: 2 },
        { titulo: 'Peso (kg)', chave: 'peso', classe: 'r b', num: true, casas: 1 },
        { titulo: 'Barra', valor: (g) => `${n(g.barras.comprimento / 1000)} m`, classe: 'c' },
        { titulo: 'Barras', valor: (g) => g.barras.quantidade, classe: 'c b', num: true },
        { titulo: 'Aprov. (%)', valor: (g) => g.barras.aproveitamento, classe: 'c', num: true, casas: 1 },
        { titulo: 'Sobra (m)', valor: (g) => g.barras.sobra_m, classe: 'r', num: true, casas: 2 },
        { titulo: 'Emendas', valor: (g) => g.barras.emendas, classe: 'c', num: true, dica: 'Peças mais compridas que a barra comercial' },
      ], L.perfis, ['TOTAL', '', '', '', '', n(L.perfis.reduce((s, g) => s + g.pecas, 0)), n(L.perfis.reduce((s, g) => s + g.comprimento_m, 0), 2), '',
                    n(L.perfis.reduce((s, g) => s + g.peso, 0), 1), '', n(totB), '', '', ''],
      (g) => [g.perfil, g.perfil_nome, g.catalogo || '', g.material, g.posicoes.join(' '), (g.nomes_posicoes || []).join(' ')].join(' '))))));
  } else pPerfis.append(vazio('Sem perfis nesta lista.'));
  const dob = L.dobrados || {};
  if ((dob.linhas || []).length) {
    const td = dob.totais || {};
    pPerfis.append(secao('Perfis dobrados: peso teórico × com desconto das dobras',
      'teórico = soma das medidas externas × espessura; com desconto = tira desenvolvida (' + (dob.regra || '') + '). O peso do modelo é o da malha 3D (cantos vivos, furos descontados).',
      el('div', { class: 'rolagem' }, tabela([
        { titulo: 'Perfil', valor: (d) => d.perfil_nome || d.perfil, classe: 'b' },
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
      (d) => [d.perfil, d.perfil_nome].join(' ')))));
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
      pCorte.append(secao(g.perfil_nome || g.perfil, `barras de ${n(b.comprimento / 1000)} m · ${n(b.quantidade)} barras · aproveitamento ${n(b.aproveitamento, 1)}% · sobra ${n(b.sobra_m, 2)} m${b.emendas ? ` · ${b.emendas} peça(s) com emenda` : ''}`,
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
      { titulo: 'Tipo', chave: 'classe' }, { titulo: 'Perfil / chapa', valor: (p_) => p_.perfil_nome || p_.perfil }, { titulo: 'Material', chave: 'material' },
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
    (p_) => [p_.nome, p_.marca, p_.perfil, p_.perfil_nome, p_.material, p_.classe, (p_.conjuntos || []).join(' ')].join(' '))))));

  // ---- acessórios
  c.append(painel('acessorios', (L.acessorios || []).length
    ? secao('Acessórios', 'só na lista: parafusos, porcas, arruelas (não são desenhados)', tabela([
      { titulo: 'Item', chave: 'nome' }, { titulo: 'Quantidade', chave: 'quantidade', classe: 'c b', num: true },
    ], L.acessorios, ['TOTAL', n(L.acessorios.reduce((s, a) => s + a.quantidade, 0))], (a) => a.nome))
    : vazio('Sem acessórios nesta lista.')));

  // ---- orçamento (montado ao abrir a aba; refeito a cada lista nova)
  c.append(painel('orcamento', el('div', { id: 'orcamento-corpo' }, vazio('Carregando o orçamento…'))));
  ORC_MONTADO = false;

  // ---- resumos da obra (montado ao abrir a aba)
  c.append(painel('resumos', el('div', { id: 'resumos-corpo' }, vazio('Carregando os resumos…'))));
  RESUMOS_MONTADO = false;

  // ---- arquivos
  c.append(painel('arquivos', el('div', { id: 'arquivos-corpo' })));
  desenharArquivos();

  montarAbas(contagem);
  if (ABA === 'resumos') abrirResumos();
  if (ABA === 'orcamento') abrirOrcamento();
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
    // a lista só se refaz pelo botão (06/10): o modelo 3D gravado depois dela fica avisado aqui
    if (L.desatualizada) aviso(`Lista de ${L.gerado || '—'}: ${L.desatualizada}. Para refazer, clique em "Atualizar pelo modelo 3D".`);
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
  ['perda_chapas', 'Perda no corte das chapas (%)', 'para contar as chapas de 1,20 x 3,00 na compra; vazio = 15', false],
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
  if (a.html && DOC_ATUAL === 'materiais') frame.addEventListener('load', () => ligarTrocas(frame));
  alvo.replaceChildren(
    el('div', { class: 'doc-barra' }, alternar, el('span', { class: 'quando', texto: quando ? `gerado em ${dataBR(quando)}` : '' }), el('span', { class: 'sep' }),
      a.pdf ? el('a', { class: 'botao-m principal', href: a.pdf.url, target: '_blank', rel: 'noopener', texto: 'Abrir o PDF', title: `detalhamento/${a.pdf.nome}` }) : null,
      a.html ? el('button', { type: 'button', class: 'botao-m', texto: 'Imprimir', onclick: () => { try { frame.contentWindow.print(); } catch (e) { window.open(a.html.url, '_blank'); } } }) : null,
      el('button', { type: 'button', class: 'botao-m', texto: 'Abrir pasta', onclick: abrirPasta })),
    frame);
}

/* ------------------------------------------------------------------- troca do perfil de compra (06/10)
 * No resumo de materiais, o nome de cada perfil abre os parecidos do catálogo: a mesma forma, os lados até 25 %
 * diferentes, se atendem (área e inércias pelo menos as do projeto), o kg/m. A escolha fica gravada no projeto,
 * a lista se atualiza na hora e os resumos se refazem. */
function ligarTrocas(frame) {
  let doc;
  try { doc = frame.contentDocument; } catch (e) { return; }
  if (!doc || !doc.head) return;
  const st = doc.createElement('style');
  st.textContent = '.trocar-perfil[data-perfil]{cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px}'
    + '.trocar-perfil[data-perfil]:hover{color:#0b3d91}.trocar-perfil[data-perfil]::after{content:" ⇄";font-weight:400;color:#0b3d91}'
    + '@media print{.trocar-perfil[data-perfil]::after{content:none}.trocar-perfil[data-perfil]{text-decoration:none}}';
  doc.head.append(st);
  doc.querySelectorAll('.trocar-perfil[data-perfil]').forEach((b) => {
    b.title = 'Ver os parecidos do catálogo e trocar o perfil de compra';
    b.addEventListener('click', () => abrirTroca(b.dataset.perfil));
  });
}

async function abrirTroca(perfil) {
  let r;
  try { r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais/parecidos?perfil=${encodeURIComponent(perfil)}`); }
  catch (e) { aviso(e.message, true); return; }
  const atual = r.escolhido || r.automatico;
  const dlg = el('dialog', { class: 'troca' });
  const fechar = () => { dlg.close(); dlg.remove(); };
  const usar = async (nome) => {
    fechar();
    aviso(nome ? `${r.ifc} → ${nome}: lista atualizada; refazendo os resumos…` : `${r.ifc}: de volta ao automático; refazendo os resumos…`);
    try {
      await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/materiais/perfil-compra`, { perfil: r.ifc, catalogo: nome });
      const form = document.querySelector('.form-resumo');
      if (form) form.requestSubmit(); else carregar(false);
    } catch (e) { aviso(e.message, true); }
  };
  const pj = r.projeto;
  const linhas = r.itens.map((x) => el('tr', { class: (x.nome === atual ? 'atual ' : '') + (x.atende ? '' : 'nao') },
    el('td', { texto: x.nome + (x.nome === atual ? (r.escolhido ? '  (escolhido)' : '  (automático)') : '') }),
    el('td', { texto: n(x.kg_m, 2) }), el('td', { texto: x.A == null ? '—' : n(x.A, 2) }),
    el('td', { texto: x.Ix == null ? '—' : n(x.Ix, 0) }), el('td', { texto: x.Iy == null ? '—' : n(x.Iy, 0) }),
    el('td', { class: 'esq', texto: x.atende ? 'atende' : 'menor que o projeto' }),
    el('td', { class: 'esq', texto: x.fabricante || '' }),
    el('td', {}, x.nome === atual ? '' : el('button', { type: 'button', class: 'botao-m', texto: 'Usar', onclick: () => usar(x.nome) }))));
  dlg.append(
    el('h3', { texto: `Trocar ${r.ifc} por um parecido do catálogo` }),
    el('p', { class: 'sub', texto: (pj ? `No projeto (IFC): A ${n(pj.A, 2)} cm² · Ix ${n(pj.Ix, 0)} cm⁴ · Iy ${n(pj.Iy, 0)} cm⁴. ` : '')
      + `Hoje na compra: ${atual || 'o próprio perfil do IFC (fora do catálogo)'}${r.escolhido ? ' (escolhido)' : ''}. `
      + 'Os que atendem (área e inércias pelo menos as do projeto) vêm primeiro, do mais leve ao mais pesado. A troca muda o nome e o kg/m da compra; a geometria e o comprimento continuam os do modelo.' }),
    el('div', { class: 'rol' }, el('table', {},
      el('thead', {}, el('tr', {}, ...['Item do catálogo', 'kg/m', 'A (cm²)', 'Ix (cm⁴)', 'Iy (cm⁴)', 'Projeto', 'Fabricante', ''].map((t) => el('th', { texto: t })))),
      el('tbody', {}, ...(linhas.length ? linhas : [el('tr', {}, el('td', { colspan: '8', texto: 'Nada parecido no catálogo.' }))])))),
    el('div', { class: 'rodape' },
      r.escolhido ? el('button', { type: 'button', class: 'botao-m', texto: `Voltar ao automático${r.automatico ? ' (' + r.automatico + ')' : ''}`, onclick: () => usar('') }) : null,
      el('button', { type: 'button', class: 'botao-m principal', texto: 'Fechar', onclick: fechar })));
  dlg.addEventListener('cancel', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
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

/* ------------------------------------------------------------ orçamento */
// O resumo de orçamento (saida/orcamento.py): as quantidades da lista com os preços da tabela da
// fábrica (<dados>/fabrica/precos/), e as colunas de fechamento que o dono preenche. Tudo o que é
// digitado aqui fica em <projeto>/orcamento/orcamento.json; "Gerar o resumo" grava o PDF e o CSV.
const CAMPOS_ORC = [
  ['data', 'Data', 'dd/mm/aaaa', false], ['obra', 'Obra', 'ex.: Barracão BYD', false],
  ['local', 'Cidade', 'ex.: São Paulo – SP', false], ['distancia_km', 'Distância (km)', 'ex.: 925', false],
  ['opcao', 'Opção', 'ex.: OPÇÃO 01 – (Pilares e tesouras treliçados)', false], ['area_m2', 'Área total (m²)', 'ex.: 1101,78', false],
  ['descricao', 'Descrição (uma linha por barracão)', 'ex.: Barracão 01 – Oficina 20,00x40,00m – 800,00m² (17.500,00kg)', true],
];
let ORC = null, ORC_MONTADO = false, ORC_SUJO = false, ORC_LINHAS = [], ORC_CAB = {}, ORC_NOTAS = null;

const numBR = (s) => {
  let t = String(s ?? '').trim().replace(/\s/g, '').replace(/^R\$/i, '');
  if (!t) return null;
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
};
const paraCampo = (v, casas = 4) => (v === null || v === undefined || v === '') ? ''
  : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: casas, useGrouping: false });
const reais = (v) => (v === null || v === undefined || v === '') ? '' : 'R$ ' + n(v, 2);

async function abrirOrcamento(forcar = false) {
  if (ORC_MONTADO && !forcar) return;
  ORC_MONTADO = true;
  const corpo = $('#orcamento-corpo');
  if (!corpo) return;
  try { ORC = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/orcamento`); }
  catch (e) { corpo.replaceChildren(vazio(`Não foi possível montar o orçamento: ${e.message}`)); ORC_MONTADO = false; return; }
  desenharOrcamento();
}

function marcarSujo() {
  ORC_SUJO = true;
  const e = $('#orc-estado');
  if (e) e.textContent = 'alterações não gravadas';
  recalcularOrcamento();
}

function campoNum(valor, auto, dica) {
  const i = el('input', { type: 'text', inputmode: 'decimal', class: 'orc-num', placeholder: paraCampo(auto), title: dica || '' });
  i.value = (valor !== null && valor !== undefined && valor !== auto) ? paraCampo(valor) : '';
  // o digitado em destaque; o vazio mostra o automático (da lista ou da tabela) em cinza
  const marca = () => i.classList.toggle('editado', !!i.value.trim());
  marca();
  i.addEventListener('input', () => { marca(); marcarSujo(); });
  return i;
}

function desenharOrcamento() {
  const corpo = $('#orcamento-corpo');
  if (!corpo || !ORC) return;
  ORC_SUJO = false;
  const tab = ORC.tabela || {};
  const arq = ORC.arquivos || {};
  const entradaArq = el('input', { type: 'file', accept: '.xlsx', hidden: true, onchange: (ev) => carregarTabela(ev.target.files[0]) });
  const barra = el('div', { class: 'doc-barra' },
    el('span', { class: 'orc-tabela', title: tab.titulo || 'A planilha de preços da empresa (Documentos\\Metálica\\fabrica\\precos)' },
      'Tabela de preços: ', el('b', { texto: tab.arquivo || 'nenhuma carregada' })),
    el('button', { type: 'button', class: 'botao-m', texto: tab.arquivo ? 'Trocar a tabela…' : 'Carregar a tabela…', onclick: () => entradaArq.click(),
      title: 'Escolha a planilha .xlsx de preços (a coluna CHAVE e as especificações são lidas dela); vale para todos os projetos' }), entradaArq,
    el('span', { class: 'sep' }), el('span', { class: 'quando', id: 'orc-estado' }),
    el('button', { type: 'button', class: 'botao-m', texto: 'Tabela → fechamento', onclick: copiarTabelaParaFechamento,
      title: 'Copia o valor da tabela para a coluna de fechamento nas linhas em que ela está vazia (depois é só trocar o que mudar)' }),
    el('button', { type: 'button', class: 'botao-m', texto: 'Gravar', onclick: () => gravarOrcamento('') }),
    el('button', { type: 'button', class: 'botao-m principal', texto: 'Gerar o resumo (PDF)', onclick: () => gravarOrcamento('pdf') }),
    arq.pdf ? el('a', { class: 'botao-m', href: arq.pdf.url, target: '_blank', rel: 'noopener', texto: 'Abrir o PDF' }) : null,
    arq.csv ? el('a', { class: 'botao-m', href: arq.csv.url, texto: 'CSV (Excel)' }) : null,
    el('a', { class: 'botao-m', href: `/comercial?projeto=${encodeURIComponent(PROJETO)}#proposta`, texto: 'Proposta comercial →', target: '_top',
      title: 'Abre a proposta: ela usa o total de fechamento deste orçamento',
      // dentro da tela Comercial (aba Orçamento): só troca de aba lá
      onclick: (ev) => { if (SO_ORCAMENTO && window.parent && typeof window.parent.irPara === 'function') { ev.preventDefault(); window.parent.irPara('proposta'); } } }));

  // ---- cabeçalho
  ORC_CAB = {};
  const form = el('div', { class: 'form-resumo orc-cab' });
  for (const [id, rot, dica, longa] of CAMPOS_ORC) {
    const i = el(longa ? 'textarea' : 'input', { placeholder: dica, title: dica, spellcheck: 'false' });
    const v = (ORC.cabecalho || {})[id];
    i.value = v === null || v === undefined ? '' : (id === 'area_m2' ? paraCampo(v, 2) : String(v));
    i.addEventListener('input', marcarSujo);
    ORC_CAB[id] = i;
    form.append(el('label', { class: longa ? 'largo' : '' }, rot, i));
  }

  // ---- avisos
  const av = (ORC.avisos || []).length ? el('div', { class: 'caixa orc-avisos' },
    el('h3', {}, 'A conferir antes de fechar', el('small', { texto: `${ORC.avisos.length} ponto(s)` })),
    el('ul', {}, ORC.avisos.map(a => el('li', { class: a.nivel, texto: a.texto })))) : null;

  // ---- linhas
  ORC_LINHAS = [];
  const tbody = el('tbody');
  const grupos = ORC.grupos || [];
  for (const [gk, gt] of grupos) {
    const linhas = ORC.linhas.filter(li => li.grupo === gk);
    if (!linhas.length && gk !== 'extras') continue;
    tbody.append(el('tr', { class: 'grupo' }, el('td', { colspan: 8, texto: gt })));
    for (const li of linhas) tbody.append(linhaOrcamento(li));
    if (gk === 'extras' || (gk === 'dono' && !grupos.some(([k]) => k === 'extras'))) { /* o botão vai no fim */ }
  }
  const tabelaOrc = el('table', { class: 'orc-tabela-linhas' },
    el('thead', {}, el('tr', {}, ['Descrição', 'Quantidade', 'Un', 'Valor (tabela)', 'Valor total', 'Valor (fechamento)', 'Valor total (fechamento)', '']
      .map((t, i) => el('th', { class: i >= 1 && i !== 2 && i < 7 ? 'r' : '', texto: t })))),
    tbody, el('tfoot', {}, el('tr', {}, el('td', { colspan: 4, texto: 'TOTAL' }), el('td', { class: 'r', id: 'orc-tot-tab' }),
      el('td', {}), el('td', { class: 'r', id: 'orc-tot-fech' }), el('td', {}))));
  const novo = el('button', { type: 'button', class: 'botao-m', texto: '+ Acrescentar linha', onclick: () => {
    const li = { id: 'novo:' + Date.now(), grupo: 'extras', descricao: '', qtd: null, un: '', preco: null, extra: true, origem: 'manual' };
    let marco = [...tbody.querySelectorAll('tr.grupo')].find(tr => tr.textContent === 'Itens acrescentados');
    if (!marco) { marco = el('tr', { class: 'grupo' }, el('td', { colspan: 8, texto: 'Itens acrescentados' })); tbody.append(marco); }
    tbody.append(linhaOrcamento(li));
    marcarSujo();
  } });
  ORC_NOTAS = el('textarea', { placeholder: 'Observações da proposta, uma por linha (ex.: Estrutura 100% parafusada; Estrutura auxiliar do ACM por conta do cliente)', spellcheck: 'false' });
  ORC_NOTAS.value = ORC.notas || '';
  ORC_NOTAS.addEventListener('input', marcarSujo);

  corpo.replaceChildren(barra, el('div', { class: 'cartoes', id: 'orc-cartoes' }),
    el('div', { class: 'grade-orc' }, el('div', { class: 'caixa' }, el('h3', {}, 'Cabeçalho do resumo', el('small', { texto: 'fica gravado no projeto' })), form), av),
    secao('Itens do orçamento', 'quantidades da lista de materiais · preços da tabela · fechamento à direita',
      el('div', { class: 'rolagem orc-rolagem' }, tabelaOrc)),
    el('div', { class: 'passos' }, novo),
    secao('Observações', 'saem no pé do resumo', el('div', { class: 'form-resumo' }, ORC_NOTAS)),
    el('ul', { class: 'nota orc-regras' }, (ORC.regras || []).map(r => el('li', { texto: r }))));
  recalcularOrcamento();
  const e = $('#orc-estado');
  if (e) e.textContent = ORC.lista_gerada ? `lista de ${dataBR(ORC.lista_gerada)}` : '';
}

function linhaOrcamento(li) {
  const reg = { li };
  const tr = el('tr', { class: li.oculta ? 'orc-oculta' : '' });
  const extra = !!li.extra;
  let celDesc;
  if (extra) {
    reg.desc = el('input', { type: 'text', class: 'orc-desc', placeholder: 'Descrição do item', value: li.descricao || '' });
    reg.desc.addEventListener('input', marcarSujo);
    reg.forn = el('input', { type: 'text', class: 'orc-forn', placeholder: 'fornecedor', value: li.fornecedor || '' });
    reg.forn.addEventListener('input', marcarSujo);
    celDesc = el('td', { class: 'quebra' }, reg.desc, reg.forn);
  } else {
    const dica = [li.item_tabela && `Tabela: ${li.item_tabela}${li.linha_tabela ? ` (linha ${li.linha_tabela})` : ''}`,
      li.data && `cotação de ${li.data}`, li.situacao && `situação: ${li.situacao}`, li.confira].filter(Boolean).join(' · ');
    celDesc = el('td', { class: 'quebra', title: dica },
      el('span', { class: li.origem === 'dono' || li.origem === 'equipe' ? 'orc-dono' : '', texto: li.descricao }),
      li.detalhe ? el('div', { class: 'orc-det', texto: li.detalhe }) : null,
      li.fornecedor ? el('div', { class: 'orc-det', texto: li.fornecedor + (li.data ? ` · ${li.data}` : '') }) : null,
      li.confira || String(li.situacao || '').toUpperCase().startsWith('VER') ? el('div', { class: 'orc-confira', texto: li.confira || 'preço a confirmar com o fornecedor' }) : null);
  }
  reg.qtd = campoNum(li.qtd, extra ? null : li.qtd_auto, 'Quantidade; vazio = a da lista');
  reg.un = extra ? el('input', { type: 'text', class: 'orc-un', value: li.un || '' }) : null;
  if (reg.un) reg.un.addEventListener('input', marcarSujo);
  reg.preco = campoNum(li.preco, extra ? null : li.preco_auto, 'Valor unitário; vazio = o da tabela');
  reg.total = el('td', { class: 'r' });
  reg.pf = campoNum(li.preco_fech, null, 'Valor unitário de fechamento');
  reg.tf = campoNum(li.total_fech_ed, null, 'Valor total de fechamento (digite direto, ou deixe vazio para quantidade × valor)');
  reg.ocultar = el('button', { type: 'button', class: 'orc-x', title: extra ? 'Remover a linha' : (li.oculta ? 'Mostrar a linha no resumo' : 'Tirar a linha do resumo'),
    texto: extra ? '×' : (li.oculta ? '↺' : '×'), onclick: () => {
      if (extra) { tr.remove(); ORC_LINHAS = ORC_LINHAS.filter(r => r !== reg); }
      else { li.oculta = !li.oculta; tr.classList.toggle('orc-oculta', li.oculta); reg.ocultar.textContent = li.oculta ? '↺' : '×'; }
      marcarSujo();
    } });
  tr.append(celDesc, el('td', { class: 'r' }, reg.qtd), el('td', { class: 'c' }, reg.un || (li.un || '')), el('td', { class: 'r' }, reg.preco),
    reg.total, el('td', { class: 'r' }, reg.pf), el('td', { class: 'r' }, reg.tf), el('td', { class: 'c' }, reg.ocultar));
  ORC_LINHAS.push(reg);
  return tr;
}

function valoresDaLinha(reg) {
  const li = reg.li;
  const extra = !!li.extra;
  const qtd = numBR(reg.qtd.value) ?? (extra ? null : li.qtd_auto);
  const preco = numBR(reg.preco.value) ?? (extra ? null : li.preco_auto);
  const pf = numBR(reg.pf.value);
  let tf = numBR(reg.tf.value);
  const total = qtd !== null && preco !== null && qtd !== undefined && preco !== undefined ? qtd * preco : null;
  const tfAuto = pf !== null && qtd !== null && qtd !== undefined ? qtd * pf : null;
  return { qtd, preco, pf, tf, total, tfFinal: tf ?? tfAuto, tfAuto };
}

function recalcularOrcamento() {
  let tot = 0, totF = 0;
  for (const reg of ORC_LINHAS) {
    const v = valoresDaLinha(reg);
    reg.total.textContent = reais(v.total);
    reg.tf.placeholder = v.tfAuto !== null ? paraCampo(v.tfAuto, 2) : '';
    if (reg.li.oculta) continue;
    tot += v.total || 0;
    totF += v.tfFinal || 0;
  }
  const a = $('#orc-tot-tab'), b = $('#orc-tot-fech');
  if (a) a.textContent = reais(tot);
  if (b) b.textContent = totF ? reais(totF) : '';
  const t = (ORC && ORC.totais) || {};
  const area = numBR(ORC_CAB.area_m2 ? ORC_CAB.area_m2.value : '') || t.area_m2;
  const c = $('#orc-cartoes');
  if (c) c.replaceChildren(
    cartao(reais(tot), 'total pela tabela', t.aco_kg ? `${n(tot / t.aco_kg, 2)} R$/kg de aço` : null, !totF),
    cartao(totF ? reais(totF) : '—', 'fechamento', totF && t.aco_kg ? `${n(totF / t.aco_kg, 2)} R$/kg${area ? ` · ${n(totF / area, 2)} R$/m²` : ''}` : 'preencha as colunas da direita', !!totF),
    cartao(n(t.aco_kg, 1) + ' kg', 'aço (estrutura)', 'peso teórico da lista'),
    cartao(n(t.telhas_ml, 1) + ' m', 'telhas', t.funilaria_kg ? `+ ${n(t.funilaria_kg, 1)} kg de rufos e calhas` : null));
}

function copiarTabelaParaFechamento() {
  let n_ = 0;
  for (const reg of ORC_LINHAS) {
    if (reg.li.oculta || reg.pf.value.trim() || reg.tf.value.trim()) continue;
    const v = valoresDaLinha(reg);
    if (v.preco === null || v.preco === undefined) continue;
    reg.pf.value = paraCampo(v.preco);
    reg.pf.classList.add('editado');
    n_++;
  }
  if (n_) marcarSujo();
  const e = $('#orc-estado');
  if (e) e.textContent = n_ ? `${n_} linha(s) copiadas — não gravado` : 'nada a copiar';
}

function edicoesDoOrcamento() {
  const cab = {};
  for (const [id, i] of Object.entries(ORC_CAB)) cab[id] = i.value.trim();
  const linhas = {}, extras = [];
  for (const reg of ORC_LINHAS) {
    const li = reg.li;
    const v = valoresDaLinha(reg);
    if (li.extra) {
      if (!reg.desc.value.trim()) continue;
      extras.push({ descricao: reg.desc.value.trim(), fornecedor: reg.forn.value.trim(), un: reg.un.value.trim(), qtd: v.qtd, preco: v.preco,
                    preco_fech: v.pf, total_fech: v.tf });
      continue;
    }
    const e = {};
    if (numBR(reg.qtd.value) !== null && numBR(reg.qtd.value) !== li.qtd_auto) e.qtd = numBR(reg.qtd.value);
    if (numBR(reg.preco.value) !== null && numBR(reg.preco.value) !== li.preco_auto) e.preco = numBR(reg.preco.value);
    if (v.pf !== null) e.preco_fech = v.pf;
    if (v.tf !== null) e.total_fech = v.tf;
    if (li.oculta) e.oculta = true;
    if (Object.keys(e).length) linhas[li.id] = e;
  }
  return { cabecalho: cab, linhas, extras, notas: ORC_NOTAS ? ORC_NOTAS.value : '' };
}

async function gravarOrcamento(acao) {
  const e = $('#orc-estado');
  if (e) e.replaceChildren(el('span', { class: 'giro' }), acao === 'pdf' ? ' gerando o resumo…' : ' gravando…');
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/orcamento${acao ? '/' + acao : ''}`, edicoesDoOrcamento());
    ORC = r;
    desenharOrcamento();
    if (acao === 'pdf') {
      if (r.erro_pdf) aviso(`Resumo gravado em HTML e CSV, mas o PDF falhou: ${r.erro_pdf}`, true);
      else if (r.arquivos && r.arquivos.pdf) avisoComLinks(`Resumo de orçamento gravado em orcamento/${r.arquivos.pdf.nome}.`,
        [[r.arquivos.pdf.url, 'Abrir o PDF']].concat(r.arquivos.csv ? [[r.arquivos.csv.url, 'CSV (Excel)']] : []));
    } else {
      const est = $('#orc-estado');
      if (est) est.textContent = 'gravado';
    }
  } catch (err) {
    if (e) e.textContent = '';
    aviso(`Não foi possível gravar o orçamento: ${err.message}`, true);
  }
}

async function carregarTabela(arquivo) {
  if (!arquivo) return;
  if (ORC_SUJO && !confirm('Há alterações não gravadas no orçamento. Gravar antes de trocar a tabela?')) return;
  try {
    if (ORC_SUJO) await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/orcamento`, edicoesDoOrcamento());
    const b64 = await new Promise((ok, falha) => {
      const fr = new FileReader();
      fr.onload = () => ok(String(fr.result).split(',', 2)[1] || '');
      fr.onerror = () => falha(fr.error);
      fr.readAsDataURL(arquivo);
    });
    ORC = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/orcamento/tabela`, { nome: arquivo.name, base64: b64 });
    desenharOrcamento();
    aviso(`Tabela de preços ${arquivo.name} carregada: vale para todos os projetos.`);
  } catch (err) {
    aviso(`Não foi possível carregar a tabela: ${err.message}`, true);
  }
}

window.addEventListener('beforeunload', (ev) => { if (ORC_SUJO) { ev.preventDefault(); ev.returnValue = ''; } });

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
