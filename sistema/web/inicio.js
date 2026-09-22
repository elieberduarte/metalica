/* Gerenciador de projetos: a primeira tela do programa.
 *
 * Lista os projetos da pasta de dados (GET /api/projetos), cria, abre, renomeia,
 * duplica e manda para a lixeira. Um projeto é uma pasta com projeto.json, modelo.json
 * e as entregas — ver sistema/projetos.py. Esta tela não guarda estado próprio: tudo o
 * que mostra vem do servidor, e depois de cada ação a lista é pedida de novo.
 *
 * Abrir um projeto leva para a tela que faz sentido para o tipo dele:
 *   galpão dimensionado  →  /dimensionar?projeto=<slug>
 *   modelo de IFC        →  /editor?projeto=<slug>
 */
'use strict';

const $ = (s, raiz = document) => raiz.querySelector(s);

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

async function api(url, opcoes = {}) {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json; charset=utf-8' }, ...opcoes });
  let corpo = null;
  try { corpo = await r.json(); } catch (e) { corpo = null; }
  if (!r.ok || (corpo && corpo.erro)) {
    throw new Error((corpo && corpo.erro) || `${r.status} ${r.statusText}`);
  }
  return corpo;
}

const postar = (url, dados) => api(url, { method: 'POST', body: JSON.stringify(dados || {}) });

/* ------------------------------------------------------------------ avisos */

function recado(titulo, texto = '', tipo = 'ok') {
  const caixa = el('div', { class: 'recado ' + tipo }, el('div', { class: 'tit', texto: titulo }),
    texto ? el('div', { texto }) : null);
  $('#bandeja').append(caixa);
  setTimeout(() => caixa.remove(), tipo === 'erro' ? 9000 : 4500);
}

function carregando(ligado, texto = 'Trabalhando…') {
  $('#carregando-texto').textContent = texto;
  $('#carregando').hidden = !ligado;
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

/* ------------------------------------------------------------------ lista */

let projetos = [];
let janelaPropria = false;

const ICONES = {
  galpao: '<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><path d="M4 27V13.5L16 6l12 7.5V27" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M4 13.5h24M10 27v-8h12v8" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/></svg>',
  ifc: '<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 21V11l10-5 10 5v10l-10 5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M6 11l10 5 10-5M16 16v10" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/></svg>',
};

function quando(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  const dias = Math.floor((Date.now() - d.getTime()) / 86400000);
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (dias <= 0 && d.getDate() === new Date().getDate()) return 'hoje, ' + hora;
  if (dias <= 1) return 'ontem, ' + hora;
  if (dias < 7) return `há ${dias} dias`;
  return d.toLocaleDateString('pt-BR');
}

function urlDoProjeto(p, destino) {
  const s = encodeURIComponent(p.slug);
  if (destino === 'editor') return `/editor?projeto=${s}`;
  if (destino === 'dimensionar') return `/dimensionar?projeto=${s}`;
  return p.tipo === 'ifc' ? `/editor?projeto=${s}` : `/dimensionar?projeto=${s}`;
}

function cartao(p) {
  const onde = [p.cliente, p.local].filter(Boolean).join(' · ');
  const medidas = (p.vao && p.comprimento)
    ? `${String(p.vao).replace('.', ',')} × ${String(p.comprimento).replace('.', ',')} m` : '';
  const conteudo = [];
  if (p.tipo === 'galpao') conteudo.push(p.tem_dados ? ['Dimensionamento', ''] : ['Sem dados ainda', 'fraco']);
  if (p.tem_modelo) conteudo.push([`Modelo 3D${p.modelo_mb >= 1 ? ' · ' + String(p.modelo_mb).replace('.', ',') + ' MB' : ''}`, '']);
  for (const e of p.entregas || []) {
    if (e.pasta === 'desenhos-2d' && (p.desenhos || []).length) continue;   // listados um a um abaixo
    conteudo.push([e.rotulo, 'entrega', e.pasta]);
  }
  if (p.tem_materiais) {
    conteudo.push(['≡ Lista de materiais', 'desenho', null, `/materiais?projeto=${encodeURIComponent(p.slug)}`,
                   'Romaneio por posição, perfis com barras comerciais, chapas, conjuntos e acessórios; CSV e PDF']);
  }
  // desenhos 2D gravados: cada um abre direto no CAD, sem gerar nada de novo
  for (const d of (p.desenhos || []).slice(0, 6)) {
    conteudo.push([`✎ ${d.titulo}`, 'desenho', null, `/cad?projeto=${encodeURIComponent(p.slug)}&desenho=${encodeURIComponent(d.nome)}`,
                   `Abrir no CAD 2D · ${d.vistas.length} vista(s)${d.vistas.length ? ': ' + d.vistas.slice(0, 6).join(', ') : ''}`]);
  }

  const menu = el('div', { class: 'cartao-menu' },
    el('button', { type: 'button', class: 'discreto', title: 'Abrir a pasta do projeto no Explorador de Arquivos',
                   onclick: (ev) => { ev.stopPropagation(); abrirPasta(p); } }, 'Pasta'),
    el('button', { type: 'button', class: 'discreto', onclick: (ev) => { ev.stopPropagation(); renomear(p); } }, 'Renomear'),
    el('button', { type: 'button', class: 'discreto', onclick: (ev) => { ev.stopPropagation(); duplicar(p); } }, 'Duplicar'),
    el('button', { type: 'button', class: 'discreto perigo', onclick: (ev) => { ev.stopPropagation(); excluir(p); } }, 'Excluir'));

  const icone = el('div', { class: 'cartao-icone ' + p.tipo });
  icone.innerHTML = ICONES[p.tipo] || ICONES.galpao;

  const c = el('article', { class: 'cartao', tabindex: '0', role: 'button',
                            'aria-label': `Abrir o projeto ${p.nome}`,
                            onclick: () => { location.href = urlDoProjeto(p); },
                            onkeydown: (ev) => { if (ev.key === 'Enter') location.href = urlDoProjeto(p); } },
    icone,
    el('div', { class: 'cartao-corpo' },
      el('div', { class: 'cartao-linha1' },
        el('h3', { texto: p.nome }),
        el('span', { class: 'etiqueta ' + p.tipo, texto: p.tipo_rotulo })),
      el('div', { class: 'cartao-sub' },
        [onde, medidas, p.origem_ifc].filter(Boolean).join('  ·  ') || 'sem cliente nem local informados'),
      el('div', { class: 'cartao-conteudo' }, conteudo.map(([rot, cls, pasta, url, dica]) =>
        el(pasta || url ? 'button' : 'span', {
          class: 'pilula ' + cls, type: pasta || url ? 'button' : undefined,
          title: dica || (pasta ? `Abrir a pasta ${pasta}` : undefined),
          onclick: url ? (ev) => { ev.stopPropagation(); location.href = url; }
            : pasta ? (ev) => { ev.stopPropagation(); abrirPasta(p, pasta); } : undefined,
        }, rot)))),
    el('div', { class: 'cartao-lado' },
      el('div', { class: 'cartao-quando', title: p.alterado || '' }, 'alterado ' + quando(p.alterado)),
      el('div', { class: 'cartao-botoes' },
        p.tipo === 'galpao'
          ? el('button', { type: 'button', onclick: (ev) => { ev.stopPropagation(); location.href = urlDoProjeto(p, 'editor'); },
                           title: 'Abrir o modelo 3D deste projeto' }, 'Editor 3D')
          : null,
        el('button', { type: 'button', class: 'principal',
                       onclick: (ev) => { ev.stopPropagation(); location.href = urlDoProjeto(p); } }, 'Abrir')),
      menu));
  return c;
}

function desenhar() {
  const termo = ($('#busca').value || '').trim().toLowerCase();
  const visiveis = termo
    ? projetos.filter(p => [p.nome, p.cliente, p.local, p.responsavel, p.origem_ifc]
        .filter(Boolean).join(' ').toLowerCase().includes(termo))
    : projetos;
  const lista = $('#lista');
  lista.replaceChildren(...visiveis.map(cartao));
  $('#vazio').hidden = projetos.length > 0;
  $('.gerenciador-cabeca').hidden = projetos.length === 0;
  $('#contagem').textContent = !projetos.length ? ''
    : termo ? `${visiveis.length} de ${projetos.length} projeto(s)`
    : `${projetos.length} projeto(s), do mais recente ao mais antigo`;
  if (termo && !visiveis.length) lista.append(el('p', { class: 'nota', texto: 'Nenhum projeto com esse termo.' }));
}

async function carregar() {
  try {
    projetos = await api('/api/projetos');
  } catch (e) {
    projetos = [];
    recado('Não foi possível listar os projetos', e.message, 'erro');
  }
  desenhar();
}

/* ---------------------------------------------------------------- diálogo */

/** Diálogo de campos de texto. Devolve os valores, ou null se cancelado. */
function perguntar({ titulo, texto = '', campos, ok = 'OK' }) {
  return new Promise((resolver) => {
    const dlg = $('#dlg');
    $('#dlg-titulo').textContent = titulo;
    $('#dlg-texto').textContent = texto;
    $('#dlg-texto').hidden = !texto;
    $('#dlg-ok').textContent = ok;
    $('#dlg-erro').hidden = true;
    const entradas = {};
    $('#dlg-campos').replaceChildren(...campos.map(c => {
      entradas[c.id] = el('input', { type: 'text', id: 'dlg-' + c.id, value: c.valor || '',
                                     placeholder: c.dica || '', spellcheck: 'false', autocomplete: 'off',
                                     required: c.obrigatorio || undefined });
      return el('div', { class: 'campo' }, el('label', { for: 'dlg-' + c.id, texto: c.rotulo }), entradas[c.id]);
    }));
    const fechar = (valor) => {
      $('#dlg-form').onsubmit = null;
      $('#dlg-cancelar').onclick = null;
      dlg.oncancel = null;
      dlg.close();
      resolver(valor);
    };
    $('#dlg-form').onsubmit = (ev) => {
      ev.preventDefault();
      const v = {};
      for (const [k, i] of Object.entries(entradas)) v[k] = i.value.trim();
      const falta = campos.find(c => c.obrigatorio && !v[c.id]);
      if (falta) {
        $('#dlg-erro').textContent = `Preencha: ${falta.rotulo}.`;
        $('#dlg-erro').hidden = false;
        entradas[falta.id].focus();
        return;
      }
      fechar(v);
    };
    $('#dlg-cancelar').onclick = () => fechar(null);
    dlg.oncancel = (ev) => { ev.preventDefault(); fechar(null); };
    dlg.showModal();
    const primeiro = entradas[campos[0].id];
    primeiro.focus();
    primeiro.select();
  });
}

const CAMPOS_PROJETO = [
  { id: 'nome', rotulo: 'Nome do projeto', dica: 'ex.: Galpão da fazenda São João', obrigatorio: true },
  { id: 'cliente', rotulo: 'Cliente' },
  { id: 'local', rotulo: 'Local', dica: 'cidade / UF da obra' },
  { id: 'responsavel', rotulo: 'Responsável técnico' },
];

/* ------------------------------------------------------------------ ações */

async function novoProjeto() {
  const v = await perguntar({
    titulo: 'Novo projeto de galpão',
    texto: 'Cria a pasta do projeto e abre o dimensionamento. Os dados podem ser mudados depois.',
    campos: CAMPOS_PROJETO, ok: 'Criar e abrir' });
  if (!v) return;
  try {
    const p = await postar('/api/projetos', { ...v, tipo: 'galpao' });
    location.href = urlDoProjeto(p);
  } catch (e) { recado('Não foi possível criar o projeto', e.message, 'erro'); }
}

function lerComoBase64(arquivo) {
  return new Promise((ok, falhou) => {
    const leitor = new FileReader();
    leitor.onerror = () => falhou(new Error('não foi possível ler o arquivo.'));
    leitor.onload = () => { const s = String(leitor.result || ''); ok(s.slice(s.indexOf(',') + 1)); };
    leitor.readAsDataURL(arquivo);
  });
}

function novoDeIFC() {
  const entrada = $('#arquivo-ifc');
  entrada.value = '';
  entrada.onchange = async () => {
    const arquivo = entrada.files && entrada.files[0];
    if (!arquivo) return;
    const sugestao = arquivo.name.replace(/\.ifc$/i, '').replace(/[._-]+/g, ' ').trim();
    const v = await perguntar({
      titulo: 'Novo projeto a partir de IFC',
      texto: `${arquivo.name} · ${(arquivo.size / 1048576).toFixed(1).replace('.', ',')} MB. ` +
             'O arquivo é copiado para a pasta do projeto e aberto no editor 3D.',
      campos: CAMPOS_PROJETO.map(c => c.id === 'nome' ? { ...c, valor: sugestao } : c),
      ok: 'Criar e importar' });
    if (!v) return;
    let criado = null;
    try {
      carregando(true, 'Criando o projeto…');
      criado = await postar('/api/projetos', { ...v, tipo: 'ifc' });
      carregando(true, `Lendo ${arquivo.name}… arquivo grande leva um minuto ou dois.`);
      const conteudo_b64 = await lerComoBase64(arquivo);
      carregando(true, `Importando ${arquivo.name}… arquivo grande leva um minuto ou dois.`);
      await postar(`/api/projetos/${encodeURIComponent(criado.slug)}/importar-ifc`,
                   { nome: arquivo.name, conteudo_b64 });
      location.href = urlDoProjeto(criado, 'editor');
    } catch (e) {
      carregando(false);
      recado('Não foi possível importar o IFC', e.message, 'erro');
      if (criado) carregar();          // o projeto existe, vazio: aparece na lista para tentar de novo
    }
  };
  entrada.click();
}

async function renomear(p) {
  const v = await perguntar({ titulo: 'Renomear projeto', ok: 'Renomear',
    campos: [{ id: 'nome', rotulo: 'Nome do projeto', valor: p.nome, obrigatorio: true }] });
  if (!v || v.nome === p.nome) return;
  try {
    await postar(`/api/projetos/${encodeURIComponent(p.slug)}/renomear`, v);
    recado('Projeto renomeado', v.nome);
  } catch (e) { recado('Não foi possível renomear', e.message, 'erro'); }
  carregar();
}

async function duplicar(p) {
  const v = await perguntar({ titulo: 'Duplicar projeto', ok: 'Duplicar',
    texto: 'Copia a pasta inteira: dados, modelo 3D e entregas.',
    campos: [{ id: 'nome', rotulo: 'Nome da cópia', valor: p.nome + ' (cópia)', obrigatorio: true }] });
  if (!v) return;
  try {
    carregando(true, 'Copiando…');
    await postar(`/api/projetos/${encodeURIComponent(p.slug)}/duplicar`, v);
    recado('Projeto duplicado', v.nome);
  } catch (e) { recado('Não foi possível duplicar', e.message, 'erro'); }
  carregando(false);
  carregar();
}

async function excluir(p) {
  const v = await perguntar({ titulo: `Excluir "${p.nome}"?`, ok: 'Mover para a lixeira',
    texto: 'O projeto sai da lista e a pasta vai para a subpasta .lixeira, dentro da pasta dos ' +
           'projetos. Nada é apagado do disco: para recuperar, mova a pasta de volta.',
    campos: [{ id: 'confirma', rotulo: 'Digite EXCLUIR para confirmar', obrigatorio: true }] });
  if (!v) return;
  if (v.confirma.toUpperCase() !== 'EXCLUIR') { recado('Nada foi excluído', 'A confirmação não conferiu.', 'aviso'); return; }
  try {
    await postar(`/api/projetos/${encodeURIComponent(p.slug)}/excluir`, {});
    recado('Projeto movido para a lixeira', p.nome);
  } catch (e) { recado('Não foi possível excluir', e.message, 'erro'); }
  carregar();
}

async function abrirPasta(p, sub = '') {
  try {
    if (p) await postar(`/api/projetos/${encodeURIComponent(p.slug)}/abrir-pasta`, { sub });
    else await postar('/api/pasta-de-dados', {});
  } catch (e) { recado('Não foi possível abrir a pasta', e.message, 'erro'); }
}

/* ----------------------------------------------------------------- início */

async function iniciar() {
  $('#btn-tema').addEventListener('click', alternarTema);
  $('#btn-novo').addEventListener('click', novoProjeto);
  $('#btn-novo-ifc').addEventListener('click', novoDeIFC);
  $('#btn-pasta').addEventListener('click', () => abrirPasta(null));
  $('#busca').addEventListener('input', desenhar);
  for (const b of document.querySelectorAll('[data-acao="novo"]')) b.addEventListener('click', novoProjeto);
  for (const b of document.querySelectorAll('[data-acao="novo-ifc"]')) b.addEventListener('click', novoDeIFC);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'n' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); novoProjeto(); }
    if (ev.key === '/' && document.activeElement === document.body) { ev.preventDefault(); $('#busca').focus(); }
  });
  // voltar de outra tela (botão Voltar do navegador) traz a página do cache: recarrega a lista
  window.addEventListener('pageshow', (ev) => { if (ev.persisted) { carregando(false); carregar(); } });

  try {
    const v = await api('/api/versao');
    janelaPropria = !!v.janela;
    $('#pasta-dados').textContent = v.dados || '—';
    $('#pe').textContent = `${v.programa} ${v.versao} · núcleo ${String(v.nucleo || '').slice(0, 12)} · ` +
      'cada projeto é uma pasta com arquivos comuns (JSON, PDF, DXF, CSV, IFC): copie a pasta para fazer backup.';
  } catch (e) { /* sem versão: a tela funciona igual */ }
  await carregar();
  verificarAtualizacao();
}

/** Avisa quando há versão mais nova publicada; sem internet, nada aparece. */
async function verificarAtualizacao() {
  try {
    const a = await api('/api/atualizacao');
    if (!a || !a.nova) return;
    const aviso = el('div', { class: 'atualizacao', role: 'status' },
      el('span', { texto: `Versão ${a.ultima} disponível (esta é a ${a.atual}). ` }),
      a.arquivo
        ? el('a', { href: a.arquivo, texto: `Baixar o instalador${a.tamanho_mb ? ` (${String(a.tamanho_mb).replace('.', ',')} MB)` : ''}`, target: '_blank', rel: 'noopener' })
        : el('a', { href: a.url, texto: 'Ver no GitHub', target: '_blank', rel: 'noopener' }),
      el('span', { texto: ' — os projetos ficam onde estão.' }),
      janelaPropria && a.arquivo
        ? el('button', { type: 'button', class: 'principal', texto: 'Atualizar agora', title: 'Baixa o instalador e o executa; o programa fecha e reabre na versão nova',
                         onclick: async (ev) => {
                           const b = ev.currentTarget; b.disabled = true; b.textContent = 'Baixando…';
                           try {
                             const r = await postar('/api/atualizacao/instalar');
                             aviso.replaceChildren(el('span', { texto: `${r.mensagem} (${String(r.tamanho_mb).replace('.', ',')} MB baixados) — se a janela não voltar em um minuto, abra o Metálica pelo atalho.` }));
                           } catch (e) { b.disabled = false; b.textContent = 'Atualizar agora'; recado('Não foi possível atualizar', e.message, 'erro'); }
                         } })
        : null,
      el('button', { type: 'button', class: 'discreto', texto: '×', title: 'fechar', onclick: () => aviso.remove() }));
    $('#pe').before(aviso);
  } catch (e) { /* sem rede */ }
}

document.addEventListener('DOMContentLoaded', iniciar);
