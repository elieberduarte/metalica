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
/** O arquivo como ele é, sem base64 nem JSON: o IFC de 321 MB, em base64, passava do limite do servidor e o navegador
 *  só dizia "Failed to fetch" (05/10). */
const enviarArquivo = (url, arquivo) => api(url, { method: 'POST', body: arquivo,
  headers: { 'Content-Type': 'application/octet-stream', 'X-Nome-Arquivo': encodeURIComponent(arquivo.name) } });

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
let listaChegou = false;          // o "Nenhum projeto ainda" só depois da lista chegar do servidor
let janelaPropria = false;
let maquinaLocal = '';

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
  // o 2D e o 3D abrem na área de trabalho do projeto: as duas vistas na mesma tela, trocar de uma
  // para a outra não recarrega nada
  const area = (vista, desenho) => `/dividida?projeto=${s}&vista=${vista}` + (desenho ? `&desenho=${encodeURIComponent(desenho)}` : '');
  if (destino === 'editor') return area('3d');
  if (destino === 'dimensionar') return `/dimensionar?projeto=${s}`;
  if (destino === 'cad') return area('2d');
  if (p.tipo === 'desenho') return area('2d');    // começa desenhando
  if (p.tipo === 'lancamento') return p.tem_modelo ? area('3d') : area('2d', 'planta-de-lançamento');
  if (p.tipo === 'recebido') return area(p.tem_modelo ? '3d' : '2d');
  return p.tipo === 'ifc' ? area('3d') : `/dimensionar?projeto=${s}`;
}

const expandidos = new Set();   // projetos com todos os desenhos à mostra

/** As seis etapas da obra (as da barra do projeto, web/etapas.js) em bolinhas: clicar vai para a etapa; "Continuar"
 * abre a primeira em andamento (ou a primeira que falta). */
function etapasDoCartao(p) {
  const et = p.etapas || [];
  // o galpão do configurador com dados já tem as etapas (vai direto ao orçamento, 20/10)
  if (!et.length || p.tipo === 'galpao' && !p.tem_modelo && !p.tem_dados) return null;
  const alvo = et.find(e => e.situacao === 'andamento') || et.find(e => !e.situacao) || et[et.length - 1];
  return el('div', { class: 'cartao-etapas', onclick: (ev) => ev.stopPropagation() },
    et.map((e, i) => el('button', { type: 'button', class: 'ce-etapa ' + (e.situacao || ''), title: `${e.nome}${e.situacao === 'feita' ? ' — feita' : e.situacao === 'andamento' ? ' — em andamento' : ''}`,
      onclick: () => { irPara(p, e.url); } }, el('i', { texto: e.situacao === 'feita' ? '✓' : String(i + 1) }), e.nome)),
    el('button', { type: 'button', class: 'ce-continuar', title: `Abre ${alvo.nome}`, onclick: () => { irPara(p, alvo.url); } }, `Continuar: ${alvo.nome} →`));
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
  if (p.aberto_por && p.aberto_por.maquina && p.aberto_por.maquina !== maquinaLocal) {
    const a = p.aberto_por;
    const ha = a.ha_s >= 60 ? `${Math.round(a.ha_s / 60)} min` : `${a.ha_s} s`;
    conteudo.push([`⚠ Aberto em ${a.maquina}${a.usuario ? ' (' + a.usuario + ')' : ''} há ${ha}`, 'fraco', null, null,
                   'Outra máquina está com este projeto aberto; se as duas gravarem, a segunda recebe "recarregue"']);
  }
  if (p.tem_materiais) {
    conteudo.push(['≡ Lista de materiais', 'desenho', null, `/materiais?projeto=${encodeURIComponent(p.slug)}`,
                   'Romaneio por posição, perfis com barras comerciais, chapas, conjuntos e acessórios; CSV e PDF']);
  }
  // desenhos 2D gravados: cada um abre direto no CAD, sem gerar nada de novo; além de 6,
  // uma pílula "+N" mostra o resto
  const desenhos = p.desenhos || [];
  const todos = expandidos.has(p.slug);
  for (const d of (todos ? desenhos : desenhos.slice(0, 6))) {
    conteudo.push([`✎ ${d.titulo}`, 'desenho', null, `/cad?projeto=${encodeURIComponent(p.slug)}&desenho=${encodeURIComponent(d.nome)}`,
                   `Abrir no CAD 2D · ${d.vistas.length} vista(s)${d.vistas.length ? ': ' + d.vistas.slice(0, 6).join(', ') : ''}`]);
  }
  if (!todos && desenhos.length > 6) {
    conteudo.push([`+${desenhos.length - 6} desenhos…`, 'desenho', null, 'expandir', 'Mostrar todos os desenhos do projeto']);
  }

  const menu = el('div', { class: 'cartao-menu' },
    el('button', { type: 'button', class: 'discreto', title: 'Abrir a pasta do projeto no Explorador de Arquivos',
                   onclick: (ev) => { ev.stopPropagation(); abrirPasta(p); } }, 'Pasta'),
    el('button', { type: 'button', class: 'discreto', onclick: (ev) => { ev.stopPropagation(); renomear(p); } }, 'Renomear'),
    el('button', { type: 'button', class: 'discreto', onclick: (ev) => { ev.stopPropagation(); duplicar(p); } }, 'Duplicar'),
    el('button', { type: 'button', class: 'discreto', title: 'Baixa o projeto inteiro num arquivo (.metalica.zip) para outro usuário abrir com "Importar pacote…"',
                   onclick: (ev) => { ev.stopPropagation(); exportar(p); } }, 'Exportar'),
    el('button', { type: 'button', class: 'discreto', 'data-acao': 'enviar',
                   title: 'Manda a obra para o Metálica de outra pessoa (pela nuvem): ela recebe um aviso na tela inicial e abre como um projeto novo',
                   onclick: (ev) => { ev.stopPropagation(); enviarObra(p); } }, 'Enviar para…'),
    el('button', { type: 'button', class: 'discreto', 'data-acao': 'arquivar',
                   title: p.arquivado ? 'Volta para a lista principal' : 'Tira da lista principal sem apagar nada (fica em "Arquivados", no fim da lista)',
                   onclick: (ev) => { ev.stopPropagation(); arquivar(p, !p.arquivado); } }, p.arquivado ? 'Desarquivar' : 'Arquivar'),
    el('button', { type: 'button', class: 'discreto perigo', onclick: (ev) => { ev.stopPropagation(); excluir(p); } }, 'Excluir'));

  const icone = el('div', { class: 'cartao-icone ' + p.tipo });
  icone.innerHTML = ICONES[p.tipo] || ICONES.galpao;

  const c = el('article', { class: 'cartao' + (p.atualizando ? ' atualizando' : ''), tabindex: '0', role: 'button', 'data-slug': p.slug,
                            'aria-label': `Abrir o projeto ${p.nome}`,
                            onclick: () => { irPara(p, urlDoProjeto(p)); },
                            // só o próprio cartão: Enter num botão dele (Excluir, Renomear…) é do botão
                            onkeydown: (ev) => { if (ev.key === 'Enter' && ev.target === ev.currentTarget) irPara(p, urlDoProjeto(p)); } },
    icone,
    el('div', { class: 'cartao-corpo' },
      el('div', { class: 'cartao-linha1' },
        el('h3', { texto: p.nome }),
        el('span', { class: 'etiqueta ' + p.tipo, texto: p.tipo_rotulo })),
      el('div', { class: 'cartao-sub' },
        [onde, medidas, p.origem_ifc].filter(Boolean).join('  ·  ') || 'sem cliente nem local informados'),
      p.atualizando ? blocoAtualizando(p) : null,
      etapasDoCartao(p),
      el('div', { class: 'cartao-conteudo' }, conteudo.map(([rot, cls, pasta, url, dica]) =>
        el(pasta || url ? 'button' : 'span', {
          class: 'pilula ' + cls, type: pasta || url ? 'button' : undefined,
          title: dica || (pasta ? `Abrir a pasta ${pasta}` : undefined),
          onclick: url === 'expandir' ? (ev) => { ev.stopPropagation(); expandidos.add(p.slug); desenhar(); }
            : url ? (ev) => { ev.stopPropagation(); irPara(p, url); }
            : pasta ? (ev) => { ev.stopPropagation(); abrirPasta(p, pasta); } : undefined,
        }, rot)))),
    el('div', { class: 'cartao-lado' },
      el('div', { class: 'cartao-quando', title: p.alterado || '' }, 'alterado ' + quando(p.alterado)),
      el('div', { class: 'cartao-botoes' },
        p.tipo === 'galpao'
          ? el('button', { type: 'button', disabled: !!p.atualizando, onclick: (ev) => { ev.stopPropagation(); irPara(p, urlDoProjeto(p, 'editor')); },
                           title: 'Abrir o modelo 3D deste projeto' }, 'Editor 3D')
          : null,
        el('button', { type: 'button', class: 'principal', disabled: !!p.atualizando,
                       title: p.atualizando ? 'O projeto está sendo atualizado; espere terminar' : undefined,
                       onclick: (ev) => { ev.stopPropagation(); irPara(p, urlDoProjeto(p)); } }, p.atualizando ? 'Atualizando…' : 'Abrir')),
      menu));
  return c;
}

/* ------------------------------------------------ projeto sendo atualizado (21/10/2026) */
// atualizando.json na pasta do projeto (app._progresso grava nas tarefas demoradas; um script ou outra janela do programa
// gravam o mesmo): o cartão mostra "Atualizando…" com a etapa e a barra, não abre (clique, Enter, Abrir, etapas, desenhos)
// e volta ao normal sozinho quando a tarefa acaba — abrir no meio interrompia a atualização e deixava o projeto pela metade.
const VIGIAS = new Map();

function irPara(p, url) {
  if (p && p.atualizando) {
    recado('Projeto sendo atualizado', (p.atualizando.etapa || 'trabalhando…') + ' — espere terminar para abrir.', 'erro');
    return;
  }
  location.href = url;
}

function estiloAtualizando() {
  if (document.getElementById('estilo-atualizando')) return;
  const st = el('style', { id: 'estilo-atualizando' });
  st.textContent = `
.cartao.atualizando { cursor: not-allowed; outline: 2px dashed var(--acento, #1f6feb); outline-offset: -2px; }
.cartao-atualizando { margin-top: 6px; font-size: 12.5px; color: var(--texto2); display: flex; flex-direction: column; gap: 4px; max-width: 520px; }
.cartao-atualizando b { color: var(--acento, #1f6feb); }
.cartao-atualizando .trilho { position: relative; height: 6px; border-radius: 3px; background: color-mix(in srgb, var(--acento, #1f6feb) 18%, transparent); overflow: hidden; }
.cartao-atualizando .cheio { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: var(--acento, #1f6feb); border-radius: 3px; transition: width .4s; }
.cartao-atualizando .cheio.corre { width: 30%; animation: cartao-corre 1.4s linear infinite; }
@keyframes cartao-corre { from { left: -30%; } to { left: 100%; } }`;
  document.head.append(st);
}

function tempoCurto(s) { s = Math.round(s || 0); return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`; }

function blocoAtualizando(p) {
  estiloAtualizando();
  const a = p.atualizando || {};
  const cheio = el('span', { class: 'cheio' + (typeof a.fracao === 'number' ? '' : ' corre') });
  if (typeof a.fracao === 'number') cheio.style.width = Math.round(a.fracao * 100) + '%';
  return el('div', { class: 'cartao-atualizando', 'data-slug': p.slug, role: 'progressbar', 'aria-label': 'Atualizando o projeto' },
    el('span', {}, el('b', { texto: 'Atualizando…' }), ' ', el('span', { class: 'etapa', texto: a.etapa || '' }),
      el('span', { class: 'tempo', texto: a.desde_s >= 5 ? ` · ${tempoCurto(a.desde_s)}` : '' })),
    el('span', { class: 'trilho' }, cheio));
}

/** Cada projeto em atualização: a etapa e a barra seguem o servidor a cada 1,5 s; quando acaba, a lista volta e o cartão abre. */
function vigiarAtualizando() {
  for (const parar of VIGIAS.values()) parar();
  VIGIAS.clear();
  for (const p of projetos) {
    if (!p.atualizando) continue;
    let vivo = true;
    VIGIAS.set(p.slug, () => { vivo = false; });
    (async () => {
      while (vivo) {
        await new Promise(r => setTimeout(r, 1500));
        if (!vivo) return;
        let prog = null;
        try {
          const r = await fetch(`/api/projetos/${encodeURIComponent(p.slug)}/progresso`, { cache: 'no-store' });
          if (r.ok) prog = await r.json();
        } catch (e) { continue; }
        if (!vivo || !prog) continue;
        if (prog.etapa) {
          p.atualizando = { ...p.atualizando, etapa: prog.etapa, fracao: prog.fracao, desde_s: prog.desde_s };
          const bloco = document.querySelector(`.cartao-atualizando[data-slug="${CSS.escape(p.slug)}"]`);
          if (!bloco) continue;
          bloco.querySelector('.etapa').textContent = prog.etapa;
          bloco.querySelector('.tempo').textContent = prog.desde_s >= 5 ? ` · ${tempoCurto(prog.desde_s)}` : '';
          const cheio = bloco.querySelector('.cheio');
          if (typeof prog.fracao === 'number') { cheio.classList.remove('corre'); cheio.style.width = Math.round(prog.fracao * 100) + '%'; }
        } else {
          vivo = false; VIGIAS.delete(p.slug);
          try { projetos = await api('/api/projetos'); desenhar(); } catch (e) { /* a próxima lista acerta */ }
          recado('Projeto atualizado', `${p.nome}: a atualização terminou; pode abrir.`, 'ok');
        }
      }
    })();
  }
}

function desenhar() {
  const termo = ($('#busca').value || '').trim().toLowerCase();
  const visiveis = termo
    ? projetos.filter(p => [p.nome, p.cliente, p.local, p.responsavel, p.origem_ifc]
        .filter(Boolean).join(' ').toLowerCase().includes(termo))
    : projetos;
  const lista = $('#lista');
  // os arquivados ficam numa seção recolhida no fim (a busca procura neles também)
  const ativos = visiveis.filter(p => !p.arquivado);
  const guardados = visiveis.filter(p => p.arquivado);
  lista.replaceChildren(...ativos.map(cartao));
  if (guardados.length) {
    const det = el('details', { class: 'arquivados', id: 'arquivados' },
      el('summary', { texto: `Arquivados (${guardados.length}) — fora da lista, nada apagado; "Desarquivar" traz de volta` }));
    if (termo || abertosArquivados) det.open = true;
    det.addEventListener('toggle', () => { abertosArquivados = det.open; });
    det.append(el('div', { class: 'lista-projetos' }, ...guardados.map(cartao)));
    lista.append(det);
  }
  $('#vazio').hidden = !listaChegou || projetos.length > 0;
  $('.gerenciador-cabeca').hidden = projetos.length === 0;
  const nAtivos = projetos.filter(p => !p.arquivado).length;
  const nArq = projetos.length - nAtivos;
  $('#contagem').textContent = !projetos.length ? ''
    : termo ? `${visiveis.length} de ${projetos.length} projeto(s)`
    : `${nAtivos} projeto(s), do mais recente ao mais antigo` + (nArq ? ` · ${nArq} arquivado(s) no fim` : '');
  if (termo && !visiveis.length) lista.append(el('p', { class: 'nota', texto: 'Nenhum projeto com esse termo.' }));
  vigiarAtualizando();
}

async function carregar() {
  // o servidor pode estar reiniciando (no desenvolvimento, a cada .py alterado): espera ele voltar em vez de mostrar
  // "Nenhum projeto ainda" — a lista vazia parecia que os projetos tinham sumido (07/10)
  for (let i = 0; ; i++) {
    // a lista que demora (o programa ocupado com um detalhamento automático em segundo plano): diz que está carregando,
    // em vez da tela em branco (16/10)
    const t0 = Date.now();
    const espera = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000);
      if (s >= 2) $('#lista').replaceChildren(el('p', { class: 'nota', texto: `Carregando os projetos… ${s} s — o programa está ocupado (provavelmente atualizando os desenhos de um projeto em segundo plano).` }));
    }, 1000);
    try { projetos = await api('/api/projetos'); listaChegou = true; clearInterval(espera); break; } catch (e) {
      clearInterval(espera);
      $('#vazio').hidden = true;
      if (i >= 40) {
        $('#lista').replaceChildren(el('p', { class: 'nota' }, `Não foi possível listar os projetos (${e.message}). Os projetos continuam na pasta. `,
          el('button', { type: 'button', onclick: () => carregar() }, 'Tentar de novo')));
        return;
      }
      $('#lista').replaceChildren(el('p', { class: 'nota', texto: 'Esperando o programa responder (ele pode estar reiniciando)…' }));
      await new Promise(r => setTimeout(r, 1500));
    }
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
      if (c.opcoes) {
        // escolha entre opções (botões de rádio): o valor é o da marcada
        const grupo = el('div', { class: 'campo escolha', role: 'radiogroup', 'aria-label': c.rotulo }, el('span', { class: 'rotulo-escolha', texto: c.rotulo }));
        const radios = c.opcoes.map(o => {
          const r = el('input', { type: 'radio', name: 'dlg-' + c.id, value: o.valor, checked: o.valor === c.valor || undefined });
          grupo.append(el('label', { class: 'opcao' }, r, el('span', {}, el('b', { texto: o.titulo }), o.texto ? el('small', { texto: o.texto }) : null)));
          return r;
        });
        entradas[c.id] = { get value() { const m = radios.find(x => x.checked); return m ? m.value : ''; } };
        return grupo;
      }
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
        if (entradas[falta.id].focus) entradas[falta.id].focus();
        return;
      }
      fechar(v);
    };
    $('#dlg-cancelar').onclick = () => fechar(null);
    dlg.oncancel = (ev) => { ev.preventDefault(); fechar(null); };
    dlg.showModal();
    const primeiro = entradas[campos[0].id];
    if (primeiro.focus) { primeiro.focus(); primeiro.select(); }
  });
}

/**
 * Projeto que nasce no CAD 2D (07/10: os dois começos num botão só): com a planta do cliente, o CAD abre na Planta
 * de lançamento e pede o DXF/PDF — dali a malha de eixos e o lançamento no 3D; sem ela, o CAD vazio para desenhar a
 * estrutura linha por linha, dizer o perfil de cada linha e gerar o modelo 3D do desenho.
 */
async function novoProjetoPeloCad() {
  const v = await perguntar({
    titulo: 'Novo projeto pelo CAD 2D',
    texto: 'O projeto abre no CAD 2D. Depois de criado, as ferramentas são as mesmas nos dois começos.',
    campos: [...CAMPOS_PROJETO, {
      id: 'comeco', rotulo: 'Como começar', valor: 'recebido', opcoes: [
        { valor: 'recebido', titulo: 'Recebi o projeto estrutural (DXF ou PDF)',
          texto: 'Do escritório de cálculo, com perfis, tesouras e eixos: o sistema lê as vistas e monta o 3D; você confere e corrige.' },
        { valor: 'arquitetonico', titulo: 'Tenho a planta do cliente — arquitetônico (DXF ou PDF)',
          texto: 'Lança a malha de eixos por cima dela; o Modelo 3D monta e dimensiona o galpão nos eixos (pilares, tesouras ou vigas, terças, contraventos, bases).' },
        { valor: 'desenho', titulo: 'Desenhar a estrutura eu mesmo',
          texto: 'CAD vazio: desenhe linha por linha (uma tesoura, um pórtico, uma peça), diga o perfil de cada linha e gere o modelo 3D do desenho.' },
      ] }],
    ok: 'Criar e abrir o CAD' });
  if (!v) return;
  const { comeco, ...dados } = v;
  // o projeto estrutural recebido (P02, primeiro uso 16/10): antes só havia "planta do cliente" ou "desenhar", e o
  // engenheiro com o DXF do projetista importava como arquitetônico
  const tipo = { recebido: 'recebido', arquitetonico: 'lancamento' }[comeco] || 'desenho';
  try {
    carregando(true, 'Criando o projeto…');
    const criado = await postar('/api/projetos', { ...dados, tipo });
    location.href = `/cad?projeto=${encodeURIComponent(criado.slug)}` + ({ recebido: '&recebido=1', lancamento: '&arquitetonico=1' }[tipo] || '');
  } catch (e) {
    carregando(false);
    recado('Não foi possível criar o projeto', e.message, 'erro');
  }
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
      const mb = arquivo.size / 1048576;
      carregando(true, `Importando ${arquivo.name} (${mb.toFixed(0)} MB)… ` +
                       (mb > 150 ? 'arquivo muito grande: pode levar 10 minutos ou mais.' : 'arquivo grande leva um minuto ou dois.'));
      await enviarArquivo(`/api/projetos/${encodeURIComponent(criado.slug)}/importar-ifc`, arquivo);
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

/**
 * O projeto inteiro num arquivo só (.metalica.zip): modelo 3D, IFC de origem, cálculo, desenhos 2D,
 * pranchas, detalhamento e ajustes. Outro usuário abre com "Importar pacote…". O histórico do modelo
 * (cópias antigas) fica de fora.
 */
async function exportar(p) {
  const v = await perguntar({ titulo: `Exportar "${p.nome}"`, ok: 'Baixar o pacote',
    texto: 'Baixa um arquivo .metalica.zip com tudo o que foi feito no projeto: modelo 3D, IFC de origem, ' +
           'cálculo, desenhos 2D, pranchas, detalhamento e os ajustes das pranchas. Quem receber abre em ' +
           '"Importar pacote…". O histórico do modelo (cópias antigas) fica de fora. ' +
           (p.modelo_mb ? `Modelo de ${String(p.modelo_mb).replace('.', ',')} MB: o pacote leva alguns segundos.` : ''),
    campos: [{ id: 'nome', rotulo: 'Nome do projeto no pacote', valor: p.nome, obrigatorio: true }] });
  if (!v) return;
  const a = el('a', { href: `/api/projetos/${encodeURIComponent(p.slug)}/exportar?nome=${encodeURIComponent(v.nome)}`,
                      download: true, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  recado('Preparando o pacote…', 'O download começa quando o arquivo estiver pronto.');
}

/* ------------------------------------------------------------------ a obra para outro usuário (21/10)
 * O usuário: "ter uma opção de enviar o projeto para outro usuário por dentro do sistema sem precisar exportar o pacote
 * da obra e enviar para ele abrir". O cartão › Enviar para… escolhe a pessoa (as licenças ativas) e sobe a obra pela nuvem
 * (sistema/compartilhar.py); quem recebe vê o aviso no alto da lista e abre como um projeto novo. */
const mbDe = (b) => (Math.round((b || 0) / 104857.6) / 10).toLocaleString('pt-BR');

async function enviarObra(p) {
  let lista;
  try { lista = (await api('/api/compartilhar/pessoas')).pessoas || []; }
  catch (e) { recado('Não foi possível listar as pessoas', e.message, 'erro'); return; }
  if (!lista.length) { recado('Ninguém para receber', 'Não há outras licenças ativas do Metálica.', 'erro'); return; }
  const v = await perguntar({ titulo: `Enviar "${p.nome}"`, ok: 'Enviar',
    texto: 'A obra vai inteira (modelo 3D, desenhos, pranchas, detalhamento) para o Metálica da pessoa, pela internet: ela ' +
           'recebe um aviso na tela inicial e abre como um projeto novo. É uma cópia — cada um segue com a sua.' +
           (p.modelo_mb ? ` Modelo de ${String(p.modelo_mb).replace('.', ',')} MB: o envio leva de alguns segundos a poucos minutos.` : ''),
    campos: [{ id: 'para', rotulo: 'Para quem', obrigatorio: true, valor: '',
               opcoes: lista.map(x => ({ valor: x.id, titulo: x.eu ? `${x.pessoa} (você — os seus outros computadores)` : x.pessoa })) }] });
  if (!v || !v.para) return;
  recado('Enviando a obra…', `"${p.nome}" está subindo para a nuvem; a barra no rodapé mostra o andamento.`);
  try {
    const r = await postar(`/api/projetos/${encodeURIComponent(p.slug)}/enviar`, { para: v.para });
    recado('Obra enviada', `"${p.nome}" foi para ${r.eu ? 'os seus outros computadores' : r.para} (${String(r.mb).replace('.', ',')} MB). ` +
           'Aparece na tela inicial do Metálica dela.');
  } catch (e) { recado('A obra não foi enviada', e.message, 'erro'); }
}

/** As obras que outras pessoas enviaram para esta licença: um aviso por obra, no alto da lista, com Abrir e Recusar. A
 *  classe não pode ser "recebido": é o tipo dos projetos recebidos de outro projetista (o ícone e a etiqueta do cartão) —
 *  o remove() dos avisos levava o ícone junto e o cartão desalinhava (Hangar Almayer, 21/10). */
async function verificarRecebidos() {
  let lista;
  try { lista = (await api('/api/compartilhar/recebidos')).recebidos || []; } catch (e) { return; }   // sem internet: nada
  document.querySelectorAll('.obra-recebida').forEach(x => x.remove());
  for (const e of lista) {
    const quando = e.criado ? new Date(e.criado).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
    const aviso = el('div', { class: 'obra-recebida', role: 'status', 'data-envio': e.id },
      el('span', { class: 'obra-recebida-icone', 'aria-hidden': 'true', texto: '📥' }),
      el('span', { class: 'obra-recebida-texto' }, el('b', { texto: e.de_mim ? 'Do seu outro computador' + (e.de_pc ? ` (${e.de_pc})` : '') : `${e.de} te enviou` }),
        ` "${e.nome}" · ${mbDe(e.bytes)} MB${quando ? ' · ' + quando : ''}`),
      el('button', { type: 'button', class: 'primario', onclick: () => abrirRecebido(e) }, 'Abrir'),
      el('button', { type: 'button', class: 'discreto', onclick: () => recusarRecebido(e) }, 'Recusar'));
    $('#lista').before(aviso);
  }
}

async function abrirRecebido(e) {
  carregando(true, `Baixando "${e.nome}"…`);
  try {
    const r = await postar(`/api/compartilhar/recebidos/${e.id}/abrir`, {});
    recado('Obra recebida', `"${r.nome}" de ${e.de} já está na sua lista de projetos.`);
    await carregar();
  } catch (err) { recado('Não foi possível abrir a obra', err.message, 'erro'); }
  finally { carregando(false); verificarRecebidos(); }
}

async function recusarRecebido(e) {
  if (!confirm(`Recusar "${e.nome}" de ${e.de}? A obra sai da nuvem e não aparece mais.`)) return;
  try { await postar(`/api/compartilhar/recebidos/${e.id}/recusar`, {}); } catch (err) { recado('Não foi possível recusar', err.message, 'erro'); }
  verificarRecebidos();
}

/** O pacote de outro usuário vira um projeto novo desta pasta de dados. */
function importarPacote() {
  const entrada = $('#arquivo-pacote');
  entrada.value = '';
  entrada.onchange = async () => {
    const arquivo = entrada.files && entrada.files[0];
    if (!arquivo) return;
    const sugestao = arquivo.name.replace(/\.metalica\.zip$/i, '').replace(/\.zip$/i, '').trim();
    const v = await perguntar({
      titulo: 'Importar pacote de projeto',
      texto: `${arquivo.name} · ${(arquivo.size / 1048576).toFixed(1).replace('.', ',')} MB. ` +
             'Vira um projeto novo nesta pasta de dados, com tudo o que veio no pacote; nada existente é alterado.',
      campos: [{ id: 'nome_projeto', rotulo: 'Nome do projeto', valor: sugestao, obrigatorio: true }],
      ok: 'Importar' });
    if (!v) return;
    try {
      carregando(true, `Lendo ${arquivo.name}…`);
      const conteudo_b64 = await lerComoBase64(arquivo);
      carregando(true, `Importando ${arquivo.name}… pacote grande leva um minuto.`);
      const r = await postar('/api/projetos/importar-pacote', { nome: arquivo.name, conteudo_b64, nome_projeto: v.nome_projeto });
      carregando(false);
      recado('Projeto importado', r.nome);
    } catch (e) {
      carregando(false);
      recado('Não foi possível importar o pacote', e.message, 'erro');
    }
    carregar();
  };
  entrada.click();
}

let abertosArquivados = false;

async function arquivar(p, sim) {
  try {
    await postar(`/api/projetos/${encodeURIComponent(p.slug)}/arquivar`, { arquivar: sim });
    await carregar();
    recado(sim ? `"${p.nome}" arquivado` : `"${p.nome}" de volta na lista`,
           sim ? 'Está em "Arquivados", no fim da lista. Nada foi apagado.' : '', 'ok');
  } catch (e) { recado('Não foi possível arquivar', e.message, 'erro'); }
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
  $('#btn-importar-pacote').addEventListener('click', importarPacote);
  $('#btn-novo-cad').addEventListener('click', novoProjetoPeloCad);
  $('#btn-pasta').addEventListener('click', () => abrirPasta(null));
  $('#busca').addEventListener('input', desenhar);
  for (const b of document.querySelectorAll('[data-acao="novo"]')) b.addEventListener('click', novoProjeto);
  for (const b of document.querySelectorAll('[data-acao="novo-ifc"]')) b.addEventListener('click', novoDeIFC);
  for (const b of document.querySelectorAll('[data-acao="novo-cad"]')) b.addEventListener('click', novoProjetoPeloCad);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'n' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); novoProjeto(); }
    if (ev.key === '/' && document.activeElement === document.body) { ev.preventDefault(); $('#busca').focus(); }
  });
  // voltar de outra tela (botão Voltar do navegador) traz a página do cache: recarrega a lista
  window.addEventListener('pageshow', (ev) => { if (ev.persisted) { carregando(false); carregar(); } });

  await carregar();                  // primeiro a lista: ela espera o servidor, se ele estiver reiniciando
  try {
    const v = await api('/api/versao');
    janelaPropria = !!v.janela;
    if (v.licencas_dev && $('#btn-licencas')) $('#btn-licencas').hidden = false;   // a tela das licenças: só no desenvolvimento
    if (v.dev && v.ritmo && $('#btn-ritmo')) {        // o ritmo da conferência (11/10): calmo com o PC em uso, cheio com ele parado
      const b = $('#btn-ritmo');
      const pintar = (m) => { b.dataset.modo = m; b.textContent = 'Conferência: ' + m; };
      pintar(v.ritmo);
      b.hidden = false;
      b.onclick = async () => {
        const novo = b.dataset.modo === 'calmo' ? 'cheio' : 'calmo';
        try { pintar((await api('/api/conferencia/ritmo', { method: 'POST', body: JSON.stringify({ modo: novo }) })).modo); }
        catch (err) { alert('Não consegui trocar o ritmo: ' + err.message); }
      };
    }
    maquinaLocal = v.maquina || '';
    if (maquinaLocal) desenhar();    // os cartões "aberto em outra máquina" dependem dela
    $('#pasta-dados').textContent = v.dados || '—';
    $('#pe').textContent = `${v.programa} ${v.versao} · núcleo ${String(v.nucleo || '').slice(0, 12)} · ` +
      'cada projeto é uma pasta com arquivos comuns (JSON, PDF, DXF, CSV, IFC): copie a pasta para fazer backup.';
  } catch (e) { /* sem versão: a tela funciona igual */ }
  verificarAtualizacao();
  verificarRecebidos();                                    // as obras que outras pessoas enviaram (21/10)
  setInterval(() => { if (!document.hidden) verificarRecebidos(); }, 5 * 60 * 1000);
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
