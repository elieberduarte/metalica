/* Memorial de cálculo de uma peça do modelo importado: a tela lê
 * GET /api/projetos/<slug>/memorial?marca=&didatico= (saida/memorial_peca.py monta o HTML
 * a partir do calculo.json) e mostra as quatro camadas. "PDF" imprime pelo servidor
 * (POST /memorial/pdf) na pasta memorial/ do projeto. Abre-se pelo painel do cálculo no 3D
 * ("Memorial desta peça") ou por /memorial?projeto=<slug>&marca=<posição>. */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);
const PARAMS = new URLSearchParams(location.search);
const PROJETO = PARAMS.get('projeto') || '';
let MARCA = PARAMS.get('marca') || '';
let DOC = null;

async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  let j = {};
  try { j = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function aviso(texto, erro = false, html = false) {
  const a = $('#aviso');
  a.hidden = !texto;
  if (html) a.innerHTML = texto || ''; else a.textContent = texto || '';
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

function progresso(texto) {
  $('#progresso').hidden = !texto;
  $('#progresso-texto').textContent = texto || '';
}

function didatico() { return $('#didatico').checked; }

/** Preenche a caixa de peças (uma vez) e marca a atual. */
function listarMarcas(marcas) {
  const sel = $('#marca');
  if (!sel.options.length) {
    const grupos = new Map();
    for (const m of marcas) {
      const g = m.tipo || 'outras';
      if (!grupos.has(g)) grupos.set(g, []);
      grupos.get(g).push(m);
    }
    const ordem = ['terca', 'longarina', 'banzo', 'diagonal', 'montante', 'pilar', 'contraventamento', 'corrente', 'travamento'];
    const chaves = [...grupos.keys()].sort((a, b) => (ordem.indexOf(a) + 1 || 99) - (ordem.indexOf(b) + 1 || 99));
    for (const g of chaves) {
      const og = document.createElement('optgroup');
      og.label = g === 'terca' ? 'Terças' : g.charAt(0).toUpperCase() + g.slice(1) + (g.endsWith('s') ? '' : 's');
      for (const m of grupos.get(g).sort((a, b) => (b.aproveitamento || 0) - (a.aproveitamento || 0))) {
        const o = document.createElement('option');
        o.value = m.marca;
        const ap = typeof m.aproveitamento === 'number' ? `${Math.round(m.aproveitamento * 100)} %` : '—';
        o.textContent = `${m.marca}${m.nome ? ' ' + m.nome : ''} · ${m.perfil} · ${ap}${m.ok === false ? ' · NÃO ATENDE' : ''}`;
        og.append(o);
      }
      sel.append(og);
    }
  }
  sel.value = MARCA;
}

async function carregar() {
  if (!PROJETO) { aviso('Abra o memorial por um projeto (Modelo 3D → painel do cálculo → Memorial desta peça).', true); return; }
  const doc = $('#doc');
  doc.innerHTML = '<p class="pequeno">Carregando…</p>';
  try {
    const q = new URLSearchParams({ didatico: didatico() ? '1' : '0' });
    if (MARCA) q.set('marca', MARCA);
    DOC = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/memorial?${q}`);
  } catch (e) {
    doc.innerHTML = '';
    aviso(`Não foi possível montar o memorial: ${e.message}`, true);
    return;
  }
  aviso('');
  MARCA = DOC.marca;
  document.title = `${DOC.titulo} — ${DOC.obra || PROJETO}`;
  $('#sub-projeto').textContent = DOC.obra || PROJETO;
  $('#obra-nome').textContent = DOC.titulo;
  $('#quando').textContent = DOC.quando ? `cálculo de ${DOC.quando}` : '—';
  $('#link-c4').hidden = !DOC.didatico;
  doc.innerHTML = DOC.html;
  doc.classList.toggle('profissional', !DOC.didatico);
  listarMarcas(DOC.marcas || []);
  const url = new URL(location.href);
  url.searchParams.set('marca', MARCA);
  history.replaceState(null, '', url);
  // os links "?marca=" da tabela do resumo trocam a peça sem recarregar
  for (const a of doc.querySelectorAll('a.marca')) {
    a.addEventListener('click', (ev) => { ev.preventDefault(); MARCA = new URL(a.href).searchParams.get('marca'); carregar(); });
  }
  abrirTudo($('#abrir-tudo').checked);
}

function abrirTudo(sim) {
  for (const d of document.querySelectorAll('#doc details.explica')) d.open = sim;
}

async function pdf(did) {
  progresso(did ? 'imprimindo o memorial didático…' : 'imprimindo o memorial…');
  try {
    const r = await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/memorial/pdf`, { marca: MARCA, didatico: did });
    aviso(`PDF gravado em <b>memorial/${r.pdf.nome}</b> (${r.pdf.tamanho_kb} kB) — <a href="${r.pdf.url}" target="_blank" rel="noopener">abrir</a>.`, false, true);
  } catch (e) { aviso(`Não foi possível gerar o PDF: ${e.message}`, true); }
  finally { progresso(''); }
}

document.addEventListener('DOMContentLoaded', () => {
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-3d').addEventListener('click', () => {
    location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}${MARCA ? '&destacar=posicao:' + encodeURIComponent(MARCA) : ''}`;
  });
  $('#btn-voltar').addEventListener('click', () => {
    if (history.length > 1) history.back(); else location.href = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
  });
  $('#marca').addEventListener('change', (ev) => { MARCA = ev.target.value; carregar(); });
  $('#didatico').addEventListener('change', carregar);
  $('#abrir-tudo').addEventListener('change', (ev) => abrirTudo(ev.target.checked));
  $('#btn-pdf-pro').addEventListener('click', () => pdf(false));
  $('#btn-pdf-did').addEventListener('click', () => pdf(true));
  $('#btn-imprimir').addEventListener('click', () => { abrirTudo(true); window.print(); });
  carregar();
});
