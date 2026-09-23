// Tela do catálogo de peças: famílias à esquerda, itens no meio, peça escolhida e suas
// alternativas à direita.
//
// Tudo vem de `GET /api/catalogo/pecas` (nucleo/catalogo.py). A tela não calcula nada:
// as propriedades e as diferenças de massa chegam prontas do servidor, que é quem sabe
// de onde veio cada número (tabela de fabricante ou cálculo pelo método linear).

const $ = (s) => document.querySelector(s);
const numero = (v, casas = 0) => v === null || v === undefined || v === ''
  ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: casas, minimumFractionDigits: 0 });

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) {
    e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return e;
}

async function api(rota) {
  const r = await fetch(rota, { cache: 'no-store' });
  const t = await r.text();
  let d = null;
  try { d = t ? JSON.parse(t) : null; } catch { d = null; }
  if (!r.ok || (d && d.erro)) throw new Error((d && d.erro) || `${r.status} ${r.statusText}`);
  return d;
}

/** Colunas por tipo de peça: barra tem massa por metro e propriedades; chapa, massa por m². */
const COLUNAS = {
  barra: [
    ['nome', 'Peça', ''], ['dim', 'Dimensões', ''], ['altura', 'h (mm)', 'r'],
    ['espessura', 't (mm)', 'r'], ['massa', 'kg/m', 'r'], ['A', 'A (cm²)', 'r'],
    ['Ix', 'Ix (cm⁴)', 'r'], ['Wx', 'Wx (cm³)', 'r'], ['rx', 'rx (cm)', 'r'],
    ['ry', 'ry (cm)', 'r'], ['fabricantes', 'Fabricantes', ''], ['origem', 'Origem', ''],
  ],
  telha: [
    ['nome', 'Telha', ''], ['espessura', 't (mm)', 'r'], ['massa_m2', 'kg/m²', 'r'],
    ['largura_total', 'Larg. total (mm)', 'r'], ['largura_util', 'Larg. útil (mm)', 'r'],
    ['fabricantes', 'Fabricante', ''], ['origem', 'Origem', ''],
  ],
  chapa: [
    ['nome', 'Peça', ''], ['espessura', 'Espessura (mm)', 'r'], ['massa_m2', 'kg/m²', 'r'],
    ['uso', 'Uso', ''], ['origem', 'Origem', ''],
  ],
  conector: [
    ['nome', 'Peça', ''], ['altura', 'ø (mm)', 'r'], ['origem', 'Origem', ''], ['uso', 'Uso', ''],
  ],
};

const estado = { familias: [], familia: null, itens: [], escolhida: null, ordem: null, invertida: false };

function pecaDaFamilia(familia) {
  const f = estado.familias.find(x => x.familia === familia);
  return (f && f.peca) || 'barra';
}

function casasDe(chave) {
  return { massa: 2, massa_m2: 1, A: 2, Ix: 1, Wx: 2, rx: 2, ry: 2, altura: 0, espessura: 2 }[chave] ?? 0;
}

function desenharFamilias() {
  const caixa = $('#familias');
  caixa.replaceChildren();
  for (const f of estado.familias) {
    caixa.append(el('button', {
      type: 'button', 'aria-pressed': String(f.familia === estado.familia),
      title: f.descricao, onclick: () => escolherFamilia(f.familia),
    }, el('span', { texto: f.nome }), el('span', { class: 'n', texto: numero(f.itens) })));
  }
  const f = estado.familias.find(x => x.familia === estado.familia);
  $('#descricao').textContent = f ? `${f.descricao}. Serve como: ${f.papeis.join(', ')}.` : '';
}

function desenharTabela() {
  const peca = pecaDaFamilia(estado.familia);
  const colunas = COLUNAS[peca] || COLUNAS.barra;
  const tabela = $('#tabela');
  const thead = tabela.querySelector('thead');
  const tbody = tabela.querySelector('tbody');
  thead.replaceChildren(el('tr', {}, colunas.map(([chave, rotulo, classe]) =>
    el('th', { class: classe, onclick: () => ordenarPor(chave), texto: rotulo }))));
  const linhas = [...estado.itens];
  if (estado.ordem) {
    const k = estado.ordem;
    linhas.sort((a, b) => {
      const x = a[k], y = b[k];
      const n = typeof x === 'number' && typeof y === 'number';
      const cmp = n ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'pt-BR');
      return estado.invertida ? -cmp : cmp;
    });
  }
  tbody.replaceChildren();
  for (const it of linhas) {
    const tr = el('tr', {
      'aria-selected': String(estado.escolhida && estado.escolhida.nome === it.nome),
      onclick: () => escolherPeca(it.nome),
    });
    for (const [chave, , classe] of colunas) {
      const v = it[chave];
      if (chave === 'origem') {
        tr.append(el('td', {}, el('span', { class: `etiqueta ${String(v).split(' ')[0]}`, texto: v })));
      } else if (Array.isArray(v)) {
        tr.append(el('td', { class: 'fabricantes', title: v.join('\n'), texto: v.length ? v.join(', ') : '—' }));
      } else if (typeof v === 'number') {
        tr.append(el('td', { class: classe, texto: numero(v, casasDe(chave)) }));
      } else {
        tr.append(el('td', { class: classe, texto: v || '—' }));
      }
    }
    tbody.append(tr);
  }
  $('#contagem').textContent = `${numero(linhas.length)} peça(s)`;
}

function ordenarPor(chave) {
  estado.invertida = estado.ordem === chave ? !estado.invertida : false;
  estado.ordem = chave;
  desenharTabela();
}

async function escolherFamilia(familia) {
  estado.familia = familia;
  estado.ordem = null;
  desenharFamilias();
  const q = $('#busca').value.trim();
  const rota = `/api/catalogo/pecas?familia=${encodeURIComponent(familia)}` + (q ? `&q=${encodeURIComponent(q)}` : '');
  estado.itens = (await api(rota)).itens || [];
  desenharTabela();
}

async function buscar() {
  const q = $('#busca').value.trim();
  if (!q) return escolherFamilia(estado.familia);
  const r = await api(`/api/catalogo/pecas?q=${encodeURIComponent(q)}&limite=400`);
  estado.itens = r.itens || [];
  // a busca livre atravessa as famílias: a tabela segue o tipo da primeira peça achada
  if (estado.itens.length) {
    const fam = estado.itens[0].familia;
    if (pecaDaFamilia(fam) !== pecaDaFamilia(estado.familia)) {
      estado.familia = fam;
      desenharFamilias();
    }
  }
  desenharTabela();
}

async function escolherPeca(nome) {
  const r = await api(`/api/catalogo/pecas?alternativas=${encodeURIComponent(nome)}&limite=12`);
  estado.escolhida = r.peca;
  desenharTabela();
  desenharDetalhe(r.peca, r.alternativas || []);
}

function desenharDetalhe(peca, alternativas) {
  const caixa = $('#detalhe');
  caixa.replaceChildren(el('h2', { texto: peca ? peca.nome : 'Peça' }));
  if (!peca) { caixa.append(el('div', { class: 'vazio', texto: 'Peça não encontrada.' })); return; }
  const campos = el('div', { class: 'campos' });
  const linha = (rot, val) => {
    if (val === null || val === undefined || val === '' || val === 0) return;
    campos.append(el('label', { texto: rot }), el('span', { class: 'valor', texto: val }));
  };
  linha('Família', peca.familia_nome);
  linha('Dimensões', peca.dim);
  linha('Altura', peca.altura ? `${numero(peca.altura, 2)} mm` : '');
  linha('Espessura', peca.espessura ? `${numero(peca.espessura, 2)} mm` : '');
  linha('Massa', peca.massa ? `${numero(peca.massa, 3)} kg/m` : (peca.massa_m2 ? `${numero(peca.massa_m2, 1)} kg/m²` : ''));
  linha('Área', peca.A ? `${numero(peca.A, 2)} cm²` : '');
  linha('Ix', peca.Ix ? `${numero(peca.Ix, 1)} cm⁴` : '');
  linha('Wx', peca.Wx ? `${numero(peca.Wx, 2)} cm³` : '');
  linha('rx / ry', peca.rx ? `${numero(peca.rx, 2)} / ${numero(peca.ry, 2)} cm` : '');
  linha('Serve como', (peca.papeis || []).join(', '));
  linha('Uso', peca.uso);
  linha('Largura total / útil', peca.largura_total ? `${numero(peca.largura_total)} / ${numero(peca.largura_util)} mm` : '');
  linha('Origem', { tabela: 'tabela de fabricante', calculado: 'calculado (método linear)' }[peca.origem] || peca.origem);
  linha('Norma', peca.norma);
  linha('Fabricantes', (peca.fabricantes || []).join(', '));
  linha('Disponibilidade', peca.sob_consulta ? 'sob consulta ao fabricante' : '');
  linha('Propriedades', peca.so_massa ? 'o catálogo do fabricante só dá a massa' : '');
  linha('Observação', peca.obs);
  caixa.append(campos);
  // a tabela de cada fabricante ao lado do valor calculado, para conferir
  const tabs = peca.tabela_fabricante || {};
  for (const [fab, valores] of Object.entries(tabs)) {
    const partes = Object.entries(valores).map(([k, v]) => `${k} ${numero(v, 2)}`);
    if (!partes.length) continue;
    caixa.append(el('p', { class: 'nota', texto: `Tabela ${fab}: ${partes.join(' · ')}` }));
  }

  caixa.append(el('h2', { texto: 'No lugar dela', style: 'margin-top:14px' }));
  if (!alternativas.length) {
    caixa.append(el('div', { class: 'vazio', texto: 'Sem alternativas nesta família.' }));
    return;
  }
  const lista = el('div', { class: 'alt' });
  for (const a of alternativas) {
    const m = a.massa || a.massa_m2;
    const unidade = a.massa ? 'kg/m' : 'kg/m²';
    lista.append(el('div', {
      class: 'linha', title: `${a.uso || ''} · ${a.origem}`, onclick: () => escolherPeca(a.nome),
    },
      el('span', { texto: a.nome }),
      el('span', { class: 'massa', texto: `${numero(m, 2)} ${unidade}` }),
      el('span', { class: `delta ${a.mais_leve ? 'leve' : 'pesado'}`,
                   texto: `${a.delta_pct > 0 ? '+' : ''}${numero(a.delta_pct, 0)} %` })));
  }
  caixa.append(lista);
  caixa.append(el('p', { class: 'nota', texto:
    'A diferença é de massa por metro (ou por m²), na mesma família e com altura de seção entre a metade ' +
    'e o dobro da atual. Se a peça passa ou não nos esforços, quem diz é a análise do projeto.' }));
}

async function iniciar() {
  const btnTema = $('#btn-tema');
  if (btnTema) {
    btnTema.addEventListener('click', () => {
      const atual = document.documentElement.getAttribute('data-tema');
      const novo = atual === 'claro' ? 'escuro' : 'claro';
      document.documentElement.setAttribute('data-tema', novo);
      try { localStorage.setItem('galpao.tema', novo); } catch { /* sem armazenamento */ }
    });
  }
  let r;
  try { r = await api('/api/catalogo/pecas'); }
  catch (e) { $('#detalhe').replaceChildren(el('div', { class: 'vazio', texto: `Catálogo indisponível: ${e.message}` })); return; }
  estado.familias = r.familias || [];
  $('#sub-resumo').textContent = `${numero(r.resumo.itens)} peças`;
  estado.familia = estado.familias.length ? estado.familias[0].familia : null;
  desenharFamilias();
  if (estado.familia) await escolherFamilia(estado.familia);
  let t = null;
  $('#busca').addEventListener('input', () => { clearTimeout(t); t = setTimeout(buscar, 180); });
  document.body.dataset.pronto = '1';
}

iniciar();
