// O modo "ver" do modelo 3D no computador.
//
// Abrir o modelo quase sempre é para ver: aqui ele chega já pronto para a placa de vídeo (o 3D leve,
// saida/modelo_leve.py) e abre em menos de um segundo, mesmo o Bella Casa de 6.896 peças, que no editor
// leva 7–8 s. Editar carrega o editor completo no mesmo lugar, com a mesma vista e a peça escolhida
// (o editor lê a vista em `metalica.vistaDoVisor`, editor.js `_vistaDoVisor`).
//
// Dentro da área de trabalho (/dividida), a barra única e a busca do Ctrl+K falam com esta página por
// `window.visorLeve` (procurar uma peça, passar para o editor antes de um comando de edição), e o vínculo com
// o Desenho 2D ao lado é o mesmo do editor (editor3d/modulos/divisao.js): a peça escolhida aqui vai para o
// 2D ('sel3d'), e a escolhida no 2D chega como 'selecionar3d' e fica em destaque aqui.
// O tema acompanha o da tela de fora na hora (a barra troca o do editor pelo botão dele, que aqui não há).

import { Visor3D } from './visor3d.js';
import { gruposDeSistema as _gruposDeSistema } from './sistemas.js';
import { PARTES_PISO } from './referencia.js';
import { SOL_PADRAO, definirSol, controlesDoSol, ligarControlesDoSol } from './sol.js';
import { acompanhar } from '../progresso.js';

const $ = s => document.querySelector(s);
const q = new URLSearchParams(location.search);
const PROJETO = q.get('projeto') || '';
const API = `/api/projetos/${encodeURIComponent(PROJETO)}/3d-leve`;
const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const escuro = () => document.documentElement.getAttribute('data-tema') === 'escuro' ||
  (!document.documentElement.getAttribute('data-tema') && matchMedia('(prefers-color-scheme: dark)').matches);

let visor = null;
let painelAtual = null;
let medindo = false, medida = [];                // pontos da medida em curso: {local, ponto}
let objMedida = null;
let legenda = [];
// o que o editor deixou para este projeto (editor3d/modulos/paineis.js, _gravarVista3d): o Colorir por, as cores de cada
// grupo e as peças ocultas — o modo ver abre igual (usuário, 16/10)
let doEditor = null;
try { doEditor = JSON.parse(localStorage.getItem(`vista3d:${PROJETO}`) || 'null'); } catch (e) { doEditor = null; }
let ocultasDoEditor = [];
// o que se ocultou AQUI no modo ver, por projeto: os grupos do Pintar (pelo nome, em cada modo) e as camadas ligadas ou
// desligadas — antes ficava só na memória da página, e quando o 3D se atualizava ("o modelo mudou… troca sozinho") ou com
// F5 tudo voltava a aparecer (usuário, Mercado Conceito, 16/10: "as camadas que são ocultas voltam a aparecer quando o
// projeto é atualizado"). Pelo nome: a peça nova do mesmo perfil ou da mesma camada já nasce oculta.
const CHAVE_DO_VER = `ver3d:${PROJETO}`;
function lerDoVer() {
  try { const v = JSON.parse(localStorage.getItem(CHAVE_DO_VER) || 'null'); if (v && typeof v === 'object') return v; } catch (e) { /* sem armazenamento */ }
  return {};
}
let doVer = { pintar: null, grupos: {}, camadas: {}, ...lerDoVer() };
const PINTAR_DO_VER = doVer.pintar;            // lido antes: o "como no editor" da abertura grava por cima
function gravarDoVer() {
  try { localStorage.setItem(CHAVE_DO_VER, JSON.stringify(doVer)); } catch (e) { /* sem armazenamento */ }
}

// a paleta dos grupos, a mesma do editor (editor3d/editor.js, corDeGrupo): por perfil a mesma peça tem a mesma cor nos dois
const PALETA_GRUPOS = ['#d94a4a', '#2f9e5f', '#3d6fd6', '#e08a1e', '#8e44ad', '#17a2b8',
  '#c2185b', '#7cb342', '#f4c20d', '#6d4c41', '#00897b', '#5c6bc0', '#ef6c00', '#4db6ac',
  '#ad1457', '#9e9d24', '#1e88e5', '#e64a19', '#546e7a', '#8d6e63'];
function corDeGrupo(i) {
  if (i < PALETA_GRUPOS.length) return PALETA_GRUPOS[i];
  const k = i - PALETA_GRUPOS.length;
  return `hsl(${((k * 137.508) % 360).toFixed(1)}, ${[72, 58, 80][k % 3]}%, ${[48, 62, 36][k % 3]}%)`;
}
const NOMES_COR_POR = { conjunto: 'conjunto', posicao: 'posição', perfil: 'perfil', tipo: 'tipo IFC', nome: 'nome de produção',
  papel: 'papel', fase: 'fase', acabamento: 'acabamento', aco: 'aço', ligacao: 'ligação' };

/** Pinta os grupos [{nome, cor, ids}] (índices das peças) com a cor de cada um. */
function pintarGrupos(lista) {
  const c = document.createElement('canvas').getContext('2d');
  for (const g of lista) {
    c.fillStyle = '#000'; c.fillStyle = g.cor;                     // hsl() ou #hex → #rrggbb
    const h = String(c.fillStyle), rr = parseInt(h.slice(1, 3), 16), gg = parseInt(h.slice(3, 5), 16), bb = parseInt(h.slice(5, 7), 16);
    for (const i of g.ids) { visor.corBase[i * 3] = rr; visor.corBase[i * 3 + 1] = gg; visor.corBase[i * 3 + 2] = bb; }
  }
  visor._repintar();
}

/** O modo de pintar pedido, com as cores do editor: os grupos dele (modo "editor"), ou a paleta dele em ordem de nome. */
function pintar(modo) {
  if (modo === 'editor' && doEditor && doEditor.grupos) {
    visor.pintarPor('perfil');                                         // zera as ocultas e tira o material
    const pos = new Map(visor.fichas.map((f, i) => [f.id, i]));
    legenda = doEditor.grupos.map(([nome, cor, ids]) => {
      const idx = ids.map(id => pos.get(id)).filter(i => i !== undefined);
      return { nome, cor, n: idx.length, ids: idx };
    }).filter(g => g.n).sort((a, b) => b.n - a.n || a.nome.localeCompare(b.nome));
    pintarGrupos(legenda);
  } else if (modo === 'sistema') {
    visor.pintarPor('perfil');                                         // zera as ocultas e tira o material
    legenda = gruposDeSistema().map(g => ({ ...g }));
    pintarGrupos(legenda);
  } else {
    legenda = visor.pintarPor(modo);
    if (modo !== 'material') {
      [...legenda].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { numeric: true })).forEach((g, k) => { g.cor = corDeGrupo(k); });
      pintarGrupos(legenda);
    }
  }
  if (modo !== 'material') {
    let mudou = false;
    for (const g of legenda) { const c = corEscolhida(modo, g.chave || g.nome); if (c) { g.cor = c; mudou = true; } }
    if (mudou) pintarGrupos(legenda);
  }
  // a legenda em ordem alfabética (usuário, Mercado Conceito, 16/10: "organizar por ordem alfabética"); antes, da que
  // tinha mais peças para a que tinha menos. As cores não mudam: vêm do nome (a paleta do editor em ordem de nome)
  legenda.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { numeric: true, sensitivity: 'base' }));
  if (ocultasDoEditor.length) visor.ocultarPecas(ocultasDoEditor, true);
  const ocultosAqui = new Set((doVer.grupos || {})[modo] || []);
  for (const g of legenda) if (ocultosAqui.has(g.nome)) visor.ocultarPecas(g.ids, true);
  if (doVer.pintar !== modo) { doVer.pintar = modo; gravarDoVer(); }
}

/** A cor de cada grupo se troca clicando no quadradinho dela (usuário, Mercado Conceito, 16/10: "não consigo alterar a
 *  cor das camadas?"): nos grupos do Pintar, na seção Sistema e nas camadas. Guardada por projeto, por modo do Pintar e
 *  nome do grupo (ou a chave do sistema); trocar a cor de um grupo de outro modo passa o Pintar para esse modo. */
function corEscolhida(modo, chave) { return ((doVer.cores || {})[modo] || {})[chave]; }
/** A pintura da tela para o IFC do modelo (usuário, 19/10: "exportar com a estrutura de uma cor e a cobertura de outra,
 *  igual temos no modo ver"): os grupos do Pintar com a cor e as peças (ids do modelo) — a barra manda junto no pedido do
 *  IFC e cada peça sai com a cor e na camada do grupo. Sem pintura (o modo "material"), null: o IFC sai como o modelo. */
window.pinturaParaIfc = () => {
  if (!visor.fichas || !Array.isArray(legenda) || !legenda.length || !doVer.pintar || doVer.pintar === 'material') return null;
  return { modo: doVer.pintar, grupos: legenda.map(g => ({ nome: g.nome, cor: paraHex(g.cor),
    ids: g.ids.map(i => (visor.fichas[i] || {}).id).filter(Boolean) })) };
};
const quadradinho = (modo, chave, cor) =>
  `<i class="cor" data-cor-modo="${esc(modo)}" data-cor-chave="${esc(chave)}" title="Trocar a cor" style="background:${esc(cor)}"></i>`;
function paraHex(cor) {
  const c = document.createElement('canvas').getContext('2d');
  c.fillStyle = '#000'; c.fillStyle = cor;
  return String(c.fillStyle).startsWith('#') ? String(c.fillStyle) : '#888888';
}
let seletorCor = null;
function escolherCor(el) {
  const modo = el.dataset.corModo, chave = el.dataset.corChave;
  if (!seletorCor) {
    seletorCor = document.createElement('input');
    seletorCor.type = 'color';
    seletorCor.id = 'seletor-cor';
    Object.assign(seletorCor.style, { position: 'fixed', width: '1px', height: '1px', opacity: '0', border: '0', padding: '0' });
    document.body.appendChild(seletorCor);
  }
  const r = el.getBoundingClientRect();
  seletorCor.style.left = r.left + 'px'; seletorCor.style.top = r.bottom + 'px';
  seletorCor.value = paraHex(el.style.background || getComputedStyle(el).backgroundColor);
  seletorCor.oninput = seletorCor.onchange = () => { aplicarCor(modo, chave, seletorCor.value); el.style.background = seletorCor.value; };
  try { seletorCor.showPicker(); } catch (e) { seletorCor.click(); }
}
function aplicarCor(modo, chave, hex) {
  doVer.cores = { ...(doVer.cores || {}), [modo]: { ...((doVer.cores || {})[modo] || {}), [chave]: hex } };
  gravarDoVer();
  const sel = $('#pintar');
  if (sel.value === modo) {
    const g = legenda.find(x => (x.chave || x.nome) === chave);
    if (g) { g.cor = hex; pintarGrupos([g]); }
    return;
  }
  if (![...sel.options].some(o => o.value === modo)) return;
  sel.value = modo;
  pintar(modo);
  if (painelAtual === 'legenda') painelLegenda(modo);
}

/** A apresentação no PC (20/10, como no celular): sol e sombras, e a posição do sol — guardadas por projeto (doVer). */
function apresentacaoDoVer() { return { ligada: false, ...SOL_PADRAO, ...(doVer.apresentacao || {}) }; }
function aplicarApresentacao(a) {
  visor.ligarApresentacao(!!a.ligada, 4096);
  definirSol(visor, a);
  $('#btn-apresentacao').classList.toggle('ligado', !!a.ligada);
}
function painelApresentacao() {
  const a = apresentacaoDoVer();
  abrirPainel('apresentacao', 'Apresentação', `<label class="linha-lista"><input type="checkbox" id="apres-ligada" ${a.ligada ? 'checked' : ''}>
      <span>Sol e sombras</span></label><p class="titulo-secao">Sol</p>${controlesDoSol(a)}
    <p class="dica">A direção gira o sol em volta da obra; a altura vai do nascer (baixo, sombras compridas) ao meio-dia (alto).
      Mexer no sol liga a apresentação. Guardado neste projeto.</p>`);
  const guardar = (mud) => { doVer.apresentacao = { ...apresentacaoDoVer(), ...mud }; gravarDoVer(); aplicarApresentacao(doVer.apresentacao); };
  $('#apres-ligada').onchange = (ev) => guardar({ ligada: ev.target.checked });
  ligarControlesDoSol($('#painel-corpo'), a, s => { $('#apres-ligada').checked = true; guardar({ ...s, ligada: true }); });
}

/** Depois de abrir: o que se ocultou aqui no modo ver da outra vez (camadas e o Pintar com os grupos ocultos). */
function aplicarDoVer() {
  if (doVer.apresentacao && doVer.apresentacao.ligada) aplicarApresentacao(apresentacaoDoVer());
  for (const g of gruposDeSistema()) if ((doVer.sistemas || {})[g.chave] === false) visor.ocultarSistema(g.ids, true);
  const opcao = $('#pintar option[value=sistema]');
  if (opcao && gruposDeSistema().length < 2) opcao.remove();             // só aço (ou só concreto): não há o que separar
  const cams = visor.cabecalho.camadas || [];
  cams.forEach((c, i) => { const v = (doVer.camadas || {})[c.nome]; if (typeof v === 'boolean' && v !== (visor.visivelCamada[i] !== false)) visor.mostrarCamada(i, v); });
  const sel = $('#pintar');
  if (PINTAR_DO_VER && sel && sel.value !== PINTAR_DO_VER && [...sel.options].some(o => o.value === PINTAR_DO_VER)) {
    sel.value = PINTAR_DO_VER;
    pintar(PINTAR_DO_VER);
  }
}

/** Depois de abrir: as peças que o editor ocultou somem, e o Pintar começa como no editor. */
function aplicarDoEditor() {
  if (!doEditor) return;
  const pos = new Map(visor.fichas.map((f, i) => [f.id, i]));
  ocultasDoEditor = (doEditor.ids_ocultos || []).map(id => pos.get(id)).filter(i => i !== undefined);
  const sel = $('#pintar');
  if (doEditor.grupos && doEditor.grupos.length && sel) {
    const o = document.createElement('option');
    o.value = 'editor';
    o.textContent = `como no editor (${NOMES_COR_POR[doEditor.cor_por] || doEditor.cor_por})`;
    sel.prepend(o);
    sel.value = 'editor';
    pintar('editor');
  } else if (ocultasDoEditor.length) visor.ocultarPecas(ocultasDoEditor, true);
  if (ocultasDoEditor.length) situacao(`${situacaoBase} · ${nf(ocultasDoEditor.length)} peça(s) ocultas no editor`);
}
const NA_DIVIDIDA = window.parent !== window;
let daDivisao = false;

// ------------------------------------------------------------------ tema

function aplicarTema(t) {
  if (t === 'claro' || t === 'escuro') document.documentElement.setAttribute('data-tema', t);
  if (visor) visor.definirTema(escuro());
}
window.addEventListener('storage', e => { if (e.key === 'galpao.tema') aplicarTema(e.newValue); });
try {
  const raizDeFora = NA_DIVIDIDA && window.parent.document.documentElement;
  if (raizDeFora) new MutationObserver(() => aplicarTema(raizDeFora.getAttribute('data-tema')))
    .observe(raizDeFora, { attributes: true, attributeFilter: ['data-tema'] });
} catch (e) { /* outra origem */ }
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => aplicarTema(null));

// ------------------------------------------------------------------ o vínculo com o Desenho 2D (tela dividida)

/** A seleção daqui para o 2D: as marcas (posição, conjunto, id), a peça/planta da montagem pela planta, o
 *  elemento lançado na planta, a peça do pré-moldado e a caixa em planta (mm do projeto). */
function avisarDivisao() {
  if (!NA_DIVIDIDA || daDivisao || !visor || !visor.fichas) return;
  const lista = [...visor.selecaoVarias].slice(0, 5000);
  const o = visor.cabecalho.origem;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const nomes = new Set(), pecas = new Set(), posicoes = new Set(), conjuntos = new Set(), origem2d = new Set(), pm = new Set(), ids = [];
  for (const i of lista) {
    const f = visor.fichas[i];
    if (!f) continue;
    if (f.pos) posicoes.add(f.pos);
    if (f.cj) conjuntos.add(f.cj);
    if (f.o2) origem2d.add(f.o2);
    if (f.pm) pm.add(f.pm);
    if (ids.length < 200) ids.push(f.id);
    if (f.pc) { pecas.add(f.pc); nomes.add(f.pl || f.pc.split('#')[0]); }
    const b = f.b || [f.x[0], f.x[1], f.x[2], f.x[0], f.x[1], f.x[2]];
    x0 = Math.min(x0, b[0] + o[0]); y0 = Math.min(y0, b[1] + o[1]); x1 = Math.max(x1, b[3] + o[0]); y1 = Math.max(y1, b[4] + o[1]);
  }
  try {
    window.parent.postMessage({ metalica: 'sel3d', n: lista.length, caixa: isFinite(x0) ? [[x0, y0], [x1, y1]] : null,
      nomes: [...nomes], pecas: [...pecas], marcas: { posicoes: [...posicoes].slice(0, 50), conjuntos: [...conjuntos].slice(0, 50), ids,
      origem2d: [...origem2d].slice(0, 200), pm: [...pm].slice(0, 200) } }, location.origin);
  } catch (e) { /* sem a tela de fora */ }
}

/** O que se escolheu no 2D: {destacar: 'posicao:…'|'conjunto:…'|'peca:…'|'ids:…'|'origem2d:…'|'pm:…'},
 *  {nome} (as peças de uma elevação da planta) ou {caixa} (as que têm o meio nela, em planta). */
function selecionarDaDivisao(pedido) {
  if (!visor || !visor.fichas) return;
  const F = visor.fichas, o = visor.cabecalho.origem;
  // clicou fora no 2D (a seleção dele ficou vazia): a do 3D sai também (06/10)
  if (pedido.limpar) {
    if (visor.selecaoVarias.size) {
      visor.selecionarVarias([], false);
      if (painelAtual === 'ficha') fecharPainel();
      situacao(situacaoBase);
    }
    return;
  }
  let ids = [];
  if (pedido.destacar) {
    const m = /^(posicao|conjunto|peca|ids|origem2d|pm):(.+)$/.exec(String(pedido.destacar));
    if (m) {
      // marca com vírgula decimal ("CH9,5-A3-200", "TIRANTE-250x100x9,5-A3-200"): a vírgula seguida de algarismo não
      // separa marcas — cortada ali, a chapa do Vicente Residence não achava peça no 3D (09/10); os ids, como sempre
      const sep = ['posicao', 'conjunto'].includes(m[1]) ? /,(?!\d)/ : ',';
      const alvo = new Set(m[2].split(sep).map(s => s.trim()).filter(Boolean));
      const chave = { posicao: 'pos', conjunto: 'cj', ids: 'id', origem2d: 'o2', pm: 'pm' }[m[1]];
      F.forEach((f, i) => {
        // a posição da peça sem marca é o nome dela, como no detalhamento (posicao_base): a calha e o rufo do IFC do
        // Depósito Químico só têm o nome ("CALHA 1"), e a célula deles não achava nada (09/10)
        const pos_ = m[1] === 'posicao' && !f.pos ? f.n : f[chave];
        if (m[1] === 'peca' ? (f.pc && (alvo.has(f.pc) || alvo.has(f.pl))) : alvo.has(pos_)) ids.push(i);
      });
    }
  } else if (pedido.nome) {
    F.forEach((f, i) => { if (f.pc && f.pl === String(pedido.nome)) ids.push(i); });
  } else if (pedido.caixa) {
    const [[x0, y0], [x1, y1]] = pedido.caixa;
    const folga = pedido.folga ?? 300;
    F.forEach((f, i) => {
      const mx = f.x[0] + o[0], my = f.x[1] + o[1];
      if (mx >= x0 - folga && mx <= x1 + folga && my >= y0 - folga && my <= y1 + folga) ids.push(i);
    });
    // o que pega uma barra de treliça pega o bloco dela
    const blocos = new Set(ids.map(i => F[i].pc).filter(Boolean));
    if (blocos.size) F.forEach((f, i) => { if (f.pc && blocos.has(f.pc)) ids.push(i); });
    ids = [...new Set(ids)];
  }
  daDivisao = true;
  try {
    if (!ids.length) {
      visor.selecionarVarias([], false);
      if (painelAtual === 'ficha') fecharPainel();
      situacao(pedido.nome ? `Nenhuma peça de ${pedido.nome} no modelo.` : 'Essa seleção do 2D não tem peça no modelo.');
      return;
    }
    visor.selecionarVarias(ids, true);
    visor.enquadrarPecas(ids);
    if (ids.length === 1) ficha(ids[0]);
    else if (painelAtual === 'ficha') fecharPainel();
    situacao(`${nf(ids.length)} peça(s) do 2D em destaque no 3D · Esc limpa`);
  } finally {
    daDivisao = false;
  }
}
window.addEventListener('message', ev => {
  if (ev.origin !== location.origin || !ev.data) return;
  // o 2D ao lado mudou os níveis, a malha de eixos ou o arquitetônico: a planta no chão é refeita (06/10)
  if (ev.data.metalica === 'referencia-mudou') { if (visor && visor.cabecalho) carregarReferencia(); return; }
  if (ev.data.metalica !== 'selecionar3d') return;
  selecionarDaDivisao(ev.data);
});

// ------------------------------------------------------------------ editar (o editor completo)

function irParaEditor(extra) {
  const pedido = extra && !(extra instanceof Event) ? extra : {};
  if (visor && visor.cabecalho) {
    const cam = visor.lerCamera();
    const sel = visor.fichas ? [...visor.selecaoVarias].slice(0, 5000).map(i => visor.fichas[i].id) : [];
    try {
      sessionStorage.setItem('metalica.vistaDoVisor', JSON.stringify({ projeto: PROJETO, quando: Date.now(), ...cam, selecao: sel }));
    } catch (e) { /* sem armazenamento: abre no enquadramento do editor */ }
  }
  const url = `/editor?projeto=${encodeURIComponent(PROJETO)}` +
    Object.entries(pedido).map(([k, v]) => `&${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('');
  // dentro da área de trabalho, a dividida troca o quadro (e passa a lembrar que o 3D é o editor)
  if (window.parent !== window) {
    try { window.parent.postMessage({ metalica: 'navegar', url }, location.origin); return; } catch (e) { /* abre aqui */ }
  }
  location.href = url;
}

// a barra única e o Ctrl+K da área de trabalho
window.visorLeve = {
  editar: irParaEditor,
  pronto: () => !!window.ver3dPronto,
  procurar(texto) { const r = procurar(texto); if (r.length) escolher(r[0], true); return r.length; },
  focarBusca() { const b = $('#busca'); if (b) { b.focus(); b.select(); } },
};

// ------------------------------------------------------------------ abrir

async function abrir() {
  if (!PROJETO) { situacao('Nenhum projeto na URL.'); return; }
  let r;
  for (;;) {
    r = await fetch(API, { cache: 'no-cache' });
    if (r.status !== 202) break;
    const s = await r.json().catch(() => ({}));
    $('#carregando-titulo').textContent = 'Preparando o modelo para ver…';
    $('#carregando-texto').textContent = 'Na primeira vez (e depois de o modelo mudar) o programa monta a versão leve do 3D. Projetos grandes levam até meio minuto.';
    $('.barra-prog i').style.width = Math.round(Math.max(0.04, s.progresso || 0) * 100) + '%';
    await new Promise(res => setTimeout(res, 800));
  }
  if (r.status === 404) {
    const j = await r.json().catch(() => ({}));
    if (j.situacao === 'sem modelo') { $('#carregando').innerHTML = j.vazio ? '<div><b>O modelo 3D deste projeto está vazio.</b><br>Lance a estrutura (na planta ou no editor) e ela aparece aqui.</div>' : '<div><b>Este projeto ainda não tem modelo 3D.</b></div>'; return; }
  }
  if (!r.ok) { irParaEditor(); return; }                                // algo falhou: o editor abre como sempre
  const versao = r.headers.get('X-Versao-3D') || '';
  const buf = await r.arrayBuffer();
  const t0 = performance.now();
  visor = new Visor3D($('#tela'), { mouse: true, arestas: true, maxPixelRatio: 2, fundo: escuro() ? '#1a212c' : '#e4eaf2' });
  window.visor = visor;
  vigiarPlacaDeVideo($('#tela'));
  visor.leveAoGirar = false;                                           // no PC sobra placa: a imagem fica inteira ao girar
  await visor.carregar(buf);
  const rf = await fetch(`${API}/pecas?v=${encodeURIComponent(versao)}`);
  // o modelo mudou entre as duas leituras (a planta tirou a última peça, 06/10): abre de novo, já na versão nova
  if (!rf.ok) { setTimeout(() => location.reload(), 400); return; }
  visor.definirFichas(await rf.json());
  const ms = Math.round(performance.now() - t0);
  $('#carregando').remove();
  $('#ferramentas').hidden = false;
  situacaoBase = `Modo ver · ${nf(visor.nPecas)} peças · aberto em ${nf(ms / 1000, 1)} s · Editar carrega o editor completo`;
  situacao(situacaoBase);
  const vista = vistaGuardada();
  if (vista) {
    visor.definirCamera(vista);
    const pos = new Map(visor.fichas.map((f, i) => [f.id, i]));
    const sel = (vista.selecao || []).map(id => pos.get(id)).filter(i => i !== undefined);
    if (sel.length) visor.selecionarVarias(sel, false);
  }
  if (r.headers.get('X-Atualizando')) {
    situacao(`Modo ver · ${nf(visor.nPecas)} peças · o modelo mudou: atualizando o 3D, troca sozinho em instantes…`);
    // a barra de andamento padrão ao lado (usuário, 19/10: "uma barrinha de carregamento quando a estrutura está
    // atualizando o modelo"): o servidor conta a etapa e a fração no /estado
    const parar = acompanhar({ url: `${API}/estado`, tarefa: '3d-leve', rotulo: 'Atualizando o 3D', onde: $('#situacao') });
    esperarVersaoNova(versao, parar);
  }
  aplicarDoEditor();
  aplicarDoVer();
  if (vista && vista.painel === 'legenda' && $('#pintar').value !== 'material') painelLegenda($('#pintar').value);
  else if (vista && vista.painel === 'camadas') painelCamadas();
  window.ver3dPronto = { ms, pecas: visor.nPecas };
  aplicarTema(null);
  carregarReferencia();
  ligar();
  if (NA_DIVIDIDA) { try { window.parent.postMessage({ metalica: 'pronto3d' }, location.origin); } catch (e) { /* sem a tela de fora */ } }
}

/** A planta no chão e os níveis (os mesmos do editor): o arquitetônico da Planta de lançamento, os eixos e os níveis do
 *  projeto — antes só no editor (pedido do usuário, 06/10). O botão Planta liga e desliga (lembrado neste navegador). */
async function carregarReferencia() {
  let ligada = true;
  try { ligada = localStorage.getItem('ver3d.planta') !== '0'; } catch (e) { /* sem armazenamento */ }
  const b = $('#btn-planta');
  if (b) b.classList.toggle('ligado', ligada);
  visor.ligarReferencia(ligada);
  for (const nome of pisoOculto()) visor.mostrarParteReferencia(nome, false);
  try {
    const r = await (await fetch(`/api/projetos/${encodeURIComponent(PROJETO)}/lancamento/referencia`, { cache: 'no-store' })).json();
    const tem = r && !r.erro && ((r.segmentos || []).length || (r.eixos || []).length || (r.niveis || []).length);
    visor.definirReferencia(tem ? r : null);
    if (b) b.hidden = !tem;
  } catch (e) { if (b) b.hidden = true; }
}

/** O desenho do piso como camadas (usuário, 16/10: "transformar esse desenho do piso em uma camada que possa ser
 *  oculta"): o arquitetônico, os eixos e os níveis ligam e desligam um a um no alto dos painéis Camadas e Pintar —
 *  lembrado neste navegador; o botão Planta e níveis continua ligando e desligando os três juntos. */
function pisoOculto() {
  try { return JSON.parse(localStorage.getItem('ver3d.pisoOculto') || '[]'); } catch (e) { return []; }
}
function secaoPiso(comSistema = true) {
  const partes = visor.partesReferencia();
  const ocultas = new Set(pisoOculto());
  let html = partes.length ? '<p class="titulo-secao">No piso</p>' + partes.map(n => { const [nome, cor] = PARTES_PISO[n] || [n, '#999'];
    return `<label class="linha-lista"><input type="checkbox" data-piso="${esc(n)}" ${ocultas.has(n) ? '' : 'checked'}>
      <i style="background:${cor}"></i><span>${esc(nome)}</span></label>`; }).join('') : '';
  const sistemas = comSistema ? gruposDeSistema() : [];
  if (sistemas.length >= 2) html += '<p class="titulo-secao">Sistema</p>' + sistemas.map(g => `<label class="linha-lista">
      <input type="checkbox" data-sistema="${g.chave}" ${g.ids.some(i => visor.ocultasSistema.has(i)) ? '' : 'checked'}>
      ${quadradinho('sistema', g.chave, corEscolhida('sistema', g.chave) || g.cor)}<span>${esc(g.nome)}</span><em>${nf(g.n)}</em></label>`).join('');
  return html ? html + '<p class="titulo-secao">Modelo</p>' : '';
}

// o sistema de cada peça: as regras em sistemas.js (as mesmas do celular)
let _sistemas = null;
function gruposDeSistema() {
  return _sistemas || (_sistemas = _gruposDeSistema(visor));
}
function alternarSistema(chave, mostrar) {
  const g = gruposDeSistema().find(x => x.chave === chave);
  if (!g) return;
  visor.ocultarSistema(g.ids, !mostrar);
  doVer.sistemas = { ...(doVer.sistemas || {}), [chave]: !!mostrar };
  gravarDoVer();
}
function ligarSecaoPiso() {
  $('#painel-corpo').querySelectorAll('input[data-sistema]').forEach(cb => {
    cb.onclick = ev => ev.stopPropagation();
    cb.onchange = () => alternarSistema(cb.dataset.sistema, cb.checked);
  });
  $('#painel-corpo').querySelectorAll('input[data-piso]').forEach(cb => {
    cb.onclick = ev => ev.stopPropagation();
    cb.onchange = () => {
      const nome = cb.dataset.piso, ocultas = new Set(pisoOculto());
      if (cb.checked) ocultas.delete(nome); else ocultas.add(nome);
      try { localStorage.setItem('ver3d.pisoOculto', JSON.stringify([...ocultas])); } catch (e) { /* sem armazenamento */ }
      visor.mostrarParteReferencia(nome, cb.checked);
      // ligar uma parte com o botão desligado liga o botão (senão a caixinha marcada não mostraria nada)
      const b = $('#btn-planta');
      if (cb.checked && b && !b.classList.contains('ligado')) b.click();
    };
  });
}

let situacaoBase = '';
function situacao(t) { $('#situacao').textContent = t; }

const CHAVE_VISTA = 'metalica.vistaVer3d';
function guardarVista() {
  if (!visor || !visor.cabecalho) return;
  try {
    sessionStorage.setItem(CHAVE_VISTA, JSON.stringify({ projeto: PROJETO, quando: Date.now(), ...visor.lerCamera(),
      selecao: [...visor.selecaoVarias].map(i => visor.fichas[i].id), painel: painelAtual }));
  } catch (e) { /* sem armazenamento */ }
}
function vistaGuardada() {
  try {
    const v = JSON.parse(sessionStorage.getItem(CHAVE_VISTA) || 'null');
    sessionStorage.removeItem(CHAVE_VISTA);
    return v && v.projeto === PROJETO && Date.now() - v.quando < 30 * 60000 ? v : null;
  } catch (e) { return null; }
}
window.addEventListener('pagehide', guardarVista);

/** O modelo mudou: abriu o 3D de antes e o novo está sendo feito; pronto, troca (a vista fica). */
function esperarVersaoNova(versao, parar = () => {}) {
  const t = setInterval(async () => {
    try {
      const s = await (await fetch(`${API}/estado`, { cache: 'no-store' })).json();
      if ((s.situacao === 'pronto' && s.versao !== versao) || s.situacao === 'sem modelo') { clearInterval(t); parar(true); guardarVista(); location.reload(); }
      else if (s.situacao === 'erro') { clearInterval(t); parar(false); situacao('Não foi possível atualizar o 3D leve: ' + (s.erro || '')); }
    } catch (e) { /* tenta de novo */ }
  }, 2000);
}

// ------------------------------------------------------------------ painel lateral

function abrirPainel(nome, titulo, html) {
  painelAtual = nome;
  $('#painel-titulo').textContent = titulo;
  $('#painel-corpo').innerHTML = html;
  $('#painel').hidden = false;
}
function fecharPainel() {
  $('#painel').hidden = true;
  painelAtual = null;
  if (medindo) pararMedida();
}

function ficha(i) {
  const f = visor.fichas[i];
  const cam = visor.cabecalho.camadas[f.c] || {};
  const linhas = [['Perfil', f.p], ['Camada', cam.nome], ['Material', f.m], f.W ? ['Medidas', `${f.p.replace(/^CH\s*/, '').replace('.', ',')} × ${nf(f.W)} × ${nf(f.L)} mm`] : ['Comprimento', f.L ? nf(f.L) + ' mm' : null], ['Peso',f.kg ? nf(f.kg, f.kg < 10 ? 2 : 1) + ' kg' : null],
                  ['Posição', f.pos], ['Conjunto', f.cj], ['Marca', f.mc],
                  ['Iguais', visor.selecaoVarias.size > 1 ? `${nf(visor.selecaoVarias.size)} peças da posição (marcadas)` : null]].filter(x => x[1]);
  abrirPainel('ficha', f.n || 'Peça', `<dl>${linhas.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <p class="dica">Arrastar sobre uma peça gira em volta dela; dois cliques a trazem para o meio. Para mudá-la, use <b>Editar</b>.</p>`);
}

function escolher(i, centrar) {
  if (i < 0) visor.selecionar(-1);
  else {
    // a clicada e as iguais a ela (a mesma posição), marcadas — pedido do usuário, 06/10
    const pos = visor.fichas[i].pos;
    const iguais = pos ? visor.fichas.reduce((l, f, k) => { if (f.pos === pos) l.push(k); return l; }, []) : [i];
    visor.selecionarComIguais(i, iguais);
  }
  avisarDivisao();
  if (i < 0) { if (painelAtual === 'ficha') fecharPainel(); return; }
  if (centrar) visor.centrarEm(i);
  ficha(i);
}

function painelCamadas() {
  const cams = visor.cabecalho.camadas;
  const linha = (c, i, recuo) => c.pecas ? `<label class="linha-lista${recuo ? ' no-grupo' : ''}">
      <input type="checkbox" data-c="${i}" ${visor.visivelCamada[i] !== false ? 'checked' : ''}>
      ${quadradinho('camada', c.nome, corEscolhida('camada', c.nome) || c.cor)}<span>${esc(c.nome)}</span><em>${nf(c.pecas)}</em></label>` : '';
  // os grupos de camadas (19/10/2026, o usuário no Mercado: "agrupar layers onde seja possível desabilitar a layer de um
  // grupo todo de uma vez"): a caixinha do grupo liga e desliga todas as camadas dele; as camadas do grupo logo abaixo
  const membros = new Map();
  cams.forEach((c, i) => { if (c.grupo && c.pecas) { if (!membros.has(c.grupo)) membros.set(c.grupo, []); membros.get(c.grupo).push(i); } });
  const feitos = new Set();
  let html = '';
  cams.forEach((c, i) => {
    if (!c.grupo || !membros.has(c.grupo)) { html += linha(c, i, false); return; }
    if (feitos.has(c.grupo)) return;
    feitos.add(c.grupo);
    const is = membros.get(c.grupo), vis = is.filter(k => visor.visivelCamada[k] !== false).length;
    html += `<label class="linha-lista grupo-camadas"><input type="checkbox" data-g="${esc(c.grupo)}" ${vis ? 'checked' : ''}>
      <span>${esc(c.grupo)}</span><em>${nf(is.reduce((t, k) => t + cams[k].pecas, 0))}</em></label>`
      + is.map(k => linha(cams[k], k, true)).join('');
  });
  abrirPainel('camadas', 'Camadas', secaoPiso() + html);
  ligarSecaoPiso();
  const corpo = $('#painel-corpo');
  corpo.querySelectorAll('input[data-g]').forEach(el => {
    const is = membros.get(el.dataset.g);
    const vis = is.filter(k => visor.visivelCamada[k] !== false).length;
    el.indeterminate = vis > 0 && vis < is.length;                  // parte do grupo oculta
    el.onchange = () => {
      const novo = { ...(doVer.camadas || {}) };
      for (const k of is) { visor.mostrarCamada(k, el.checked); novo[cams[k].nome] = el.checked; }
      doVer.camadas = novo;
      gravarDoVer();
      painelCamadas();
    };
  });
  corpo.querySelectorAll('input[data-c]').forEach(el => el.onchange = () => {
    visor.mostrarCamada(+el.dataset.c, el.checked);
    doVer.camadas = { ...(doVer.camadas || {}), [cams[+el.dataset.c].nome]: el.checked };
    gravarDoVer();
    if (cams[+el.dataset.c].grupo) painelCamadas();               // a caixinha do grupo acompanha
  });
}

function painelLegenda(modo) {
  const titulo = modo === 'editor' ? $('#pintar').selectedOptions[0].textContent.replace(/^como/, 'Pintado como')
    : modo === 'camada' ? 'Pintado por camada' : modo === 'sistema' ? 'Pintado por sistema' : 'Pintado por perfil';
  // por sistema, a própria legenda é o Sistema (as caixinhas são as mesmas da seção Sistema)
  const oculto = modo === 'sistema' ? (g => g.ids.some(i => visor.ocultasSistema.has(i))) : (g => g.ids.some(i => visor.ocultas.has(i)));
  abrirPainel('legenda', titulo, secaoPiso(modo !== 'sistema') + legenda.slice(0, 200).map((g, k) => `<div class="linha-lista" data-k="${k}">
      <input type="checkbox" data-olho="${k}" title="Mostrar / ocultar este grupo" ${oculto(g) ? '' : 'checked'}>
      ${quadradinho(modo, g.chave || g.nome, g.cor)}<span title="${esc(g.nome)}">${esc(g.nome)}</span><em>${nf(g.n)}</em></div>`).join('')
    + (legenda.length > 200 ? `<p class="dica">e mais ${legenda.length - 200} grupos</p>` : '')
    + '<p class="dica">Clique num grupo para ir à primeira peça dele; a caixinha mostra ou oculta o grupo; o quadradinho troca a cor.</p>');
  $('#painel-corpo').querySelectorAll('[data-olho]').forEach(cb => {
    cb.onclick = ev => ev.stopPropagation();
    cb.onchange = () => {
      const g = legenda[+cb.dataset.olho];
      if (g.chave && $('#pintar').value === 'sistema') { alternarSistema(g.chave, cb.checked); return; }
      visor.ocultarPecas(g.ids, !cb.checked);
      const modo = $('#pintar').value, nomes = new Set((doVer.grupos || {})[modo] || []);
      if (cb.checked) nomes.delete(g.nome); else nomes.add(g.nome);
      doVer.grupos = { ...(doVer.grupos || {}), [modo]: [...nomes] };
      gravarDoVer();
    };
  });
  ligarSecaoPiso();
  $('#painel-corpo').querySelectorAll('[data-k]').forEach(el => el.onclick = (ev) => {
    if (ev.target.closest('input')) return;
    const g = legenda[+el.dataset.k];
    if (g && g.ids.length) { visor.selecionar(g.ids[0]); visor.centrarEm(g.ids[0]); avisarDivisao(); }
  });
}

// ------------------------------------------------------------------ medir

function iniciarMedida() {
  medindo = true;
  medida = [];
  limparDesenhoMedida();
  $('#btn-medir').classList.add('ligado');
  $('#palco').classList.add('medindo');
  abrirPainel('medida', 'Medir', '<p class="dica">Clique no primeiro ponto, numa peça. Esc sai.</p>');
}

function pararMedida() {
  medindo = false;
  medida = [];
  limparDesenhoMedida();
  $('#btn-medir').classList.remove('ligado');
  $('#palco').classList.remove('medindo');
  $('#rotulo-medida').hidden = true;
}

function limparDesenhoMedida() {
  if (objMedida && visor) { visor.cena.remove(objMedida); objMedida.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); }
  objMedida = null;
  if (visor) visor.pedirQuadro();
}

async function pontoDaMedida(x, y) {
  const p = visor.pontoEm(x, y);
  if (!p) return;
  if (medida.length === 2) medida = [];
  medida.push(p);
  await desenharMedida();
}

async function desenharMedida() {
  const THREE = await import('three');
  limparDesenhoMedida();
  const g = new THREE.Group();
  const pts = medida.map(m => new THREE.Vector3(...m.local));
  const marcas = new THREE.Points(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.PointsMaterial({ color: 0xd1392e, size: 9, sizeAttenuation: false, depthTest: false }));
  marcas.renderOrder = 20;
  g.add(marcas);
  if (pts.length === 2) {
    const linha = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0xd1392e, depthTest: false }));
    linha.renderOrder = 20;
    g.add(linha);
  }
  objMedida = g;
  visor.cena.add(g);
  visor.pedirQuadro();
  if (medida.length === 1) {
    abrirPainel('medida', 'Medir', `<p class="dica">Primeiro ponto em <b>${esc(visor.fichas[medida[0].id].n)}</b>. Clique no segundo.</p>`);
    $('#rotulo-medida').hidden = true;
    return;
  }
  const [a, b] = medida;
  const d = [b.ponto[0] - a.ponto[0], b.ponto[1] - a.ponto[1], b.ponto[2] - a.ponto[2]];
  const dist = Math.hypot(...d);
  abrirPainel('medida', 'Medir', `<div class="medida-grande">${nf(dist, 1)} mm</div>
    <dl><dt>Δ X</dt><dd>${nf(Math.abs(d[0]), 1)} mm</dd><dt>Δ Y</dt><dd>${nf(Math.abs(d[1]), 1)} mm</dd><dt>Δ Z</dt><dd>${nf(Math.abs(d[2]), 1)} mm</dd>
    <dt>De</dt><dd>${esc(visor.fichas[a.id].n)}</dd><dt>Até</dt><dd>${esc(visor.fichas[b.id].n)}</dd></dl>
    <p class="dica">O ponto é o da superfície da peça sob o cursor. Clique de novo para outra medida; Esc sai.</p>`);
  window.ultimaMedida = { mm: dist, d };
  posicionarRotulo();
}

async function posicionarRotulo() {
  const r = $('#rotulo-medida');
  if (medida.length !== 2 || !visor) { r.hidden = true; return; }
  const THREE = await import('three');
  const m = new THREE.Vector3(...medida[0].local).add(new THREE.Vector3(...medida[1].local)).multiplyScalar(0.5).project(visor.camera);
  if (m.z > 1) { r.hidden = true; return; }
  const dist = Math.hypot(...[0, 1, 2].map(k => medida[1].ponto[k] - medida[0].ponto[k]));
  r.textContent = nf(dist, 1) + ' mm';
  r.style.left = ((m.x + 1) / 2 * visor.tela.clientWidth) + 'px';
  r.style.top = ((1 - m.y) / 2 * visor.tela.clientHeight) + 'px';
  r.hidden = false;
}

// ------------------------------------------------------------------ busca

// a bitola em polegada dos parafusos e chumbadores, que têm o diâmetro em mm no nome ("HIT-V 15.875x250"): a busca por
// 5/8" não achava os chumbadores (Vicente, 14/10)
const POLEGADAS = [[6.35, '1/4"'], [7.94, '5/16"'], [9.525, '3/8"'], [12.7, '1/2"'], [15.875, '5/8"'], [19.05, '3/4"'],
  [22.225, '7/8"'], [25.4, '1"'], [28.575, '1.1/8" 1 1/8"'], [31.75, '1.1/4" 1 1/4"'], [38.1, '1.1/2" 1 1/2"'], [50.8, '2"']];
function polegadas(s) {
  const nums = String(s || '').match(/\d+(?:[.,]\d+)?/g) || [];
  return POLEGADAS.filter(([mm]) => nums.some(n => Math.abs(parseFloat(n.replace(',', '.')) - mm) < 0.02))
    .map(([, pol]) => pol + ' ø' + pol).join(' ');
}

function procurar(texto) {
  const t = (texto || '').trim().toLowerCase();
  if (t.length < 2 || !visor || !visor.fichas) return [];
  // a sigla ou a peça digitada inteira (TC3, TESOURA 16) vale só ela — "tc3" não traz TC30…TC39
  const exatas = [];
  visor.fichas.forEach((f, i) => { if ((f.sg || '').toLowerCase() === t || (f.pl || '').toLowerCase() === t) exatas.push(i); });
  if (exatas.length) return exatas;
  const out = [];
  visor.fichas.forEach((f, i) => {
    // também a sigla da terça (TC3) e a peça/planta de origem (TESOURA 16): os nomes do projeto (12/10)
    if ((f.n + ' ' + f.p + ' ' + (f.pos || '') + ' ' + (f.mc || '') + ' ' + (f.cj || '') + ' ' + (f.sg || '') + ' ' + (f.pl || '')
      + ' ' + polegadas(f.n)).toLowerCase().includes(t)) out.push(i);
  });
  return out;
}

function painelBusca(texto) {
  const r = procurar(texto);
  if (!r.length) { abrirPainel('busca', 'Buscar', '<p class="dica">Nenhuma peça com esse texto.</p>'); return; }
  abrirPainel('busca', `${nf(r.length)} peça(s)`, r.slice(0, 80).map(i => `<div class="linha-lista" data-i="${i}">
      <span title="${esc(visor.fichas[i].n)}">${esc(visor.fichas[i].sg || visor.fichas[i].pl || visor.fichas[i].n)}</span><em>${esc(visor.fichas[i].p || '')}</em></div>`).join('')
    + (r.length > 80 ? `<p class="dica">e mais ${nf(r.length - 80)}</p>` : ''));
  $('#painel-corpo').querySelectorAll('[data-i]').forEach(el => el.onclick = () => { visor.selecionar(+el.dataset.i); visor.centrarEm(+el.dataset.i); avisarDivisao(); });
}

// ------------------------------------------------------------------ eventos

function ligar() {
  const tela = $('#tela');
  let ini = null, ultimo = 0;
  tela.addEventListener('pointerdown', e => { ini = { x: e.clientX, y: e.clientY, t: performance.now(), b: e.button }; });
  tela.addEventListener('pointerup', e => {
    if (!ini || ini.b !== 0) { ini = null; return; }
    const mexeu = Math.hypot(e.clientX - ini.x, e.clientY - ini.y) > 4;
    ini = null;
    if (mexeu) return;
    const r = tela.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    if (medindo) { pontoDaMedida(x, y); return; }
    const id = visor.escolher(x, y);
    const agora = performance.now();
    escolher(id, id >= 0 && agora - ultimo < 350);
    ultimo = agora;
  });
  tela.addEventListener('contextmenu', e => e.preventDefault());
  visor.controles.addEventListener('change', () => { if (medida.length === 2) posicionarRotulo(); });

  $('#btn-editar').onclick = irParaEditor;
  $('#btn-reanalisar').onclick = () => irParaEditor({ reanalisar: '1' });       // o editor abre já com a prévia
  $('#painel-fechar').onclick = fecharPainel;
  $('#painel-corpo').addEventListener('click', ev => {
    const el = ev.target.closest && ev.target.closest('i.cor');
    if (!el) return;
    ev.preventDefault(); ev.stopPropagation();
    escolherCor(el);
  }, true);
  document.querySelector('[data-painel="camadas"]').onclick = () => (painelAtual === 'camadas' ? fecharPainel() : painelCamadas());
  $('#btn-medir').onclick = () => (medindo ? (pararMedida(), fecharPainel()) : iniciarMedida());
  $('#btn-enquadrar').onclick = () => visor.enquadrar('iso');
  $('#btn-planta').onclick = () => {
    const b = $('#btn-planta'); b.classList.toggle('ligado');
    const sim = b.classList.contains('ligado');
    visor.ligarReferencia(sim);
    try { localStorage.setItem('ver3d.planta', sim ? '1' : '0'); } catch (e) { /* sem armazenamento */ }
  };
  $('#btn-arestas').onclick = () => { const b = $('#btn-arestas'); b.classList.toggle('ligado'); visor.ligarArestas(b.classList.contains('ligado')); };
  $('#btn-apresentacao').onclick = () => { if (painelAtual === 'apresentacao') fecharPainel(); else painelApresentacao(); };
  document.querySelectorAll('[data-vista]').forEach(b => b.onclick = () => visor.enquadrar(b.dataset.vista));
  $('#pintar').onchange = () => {
    const modo = $('#pintar').value;
    pintar(modo);
    if (modo === 'material') { if (painelAtual === 'legenda') fecharPainel(); } else painelLegenda(modo);
  };
  let espera = null;
  $('#busca').oninput = () => { clearTimeout(espera); espera = setTimeout(() => painelBusca($('#busca').value), 180); };
  $('#busca').onkeydown = e => {
    if (e.key === 'Enter') { const r = procurar($('#busca').value); if (r.length) escolher(r[0], true); }
  };
  document.addEventListener('keydown', e => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT')) { if (e.key === 'Escape') e.target.blur(); return; }
    if (e.key === 'Escape') { if (medindo) { pararMedida(); fecharPainel(); } else escolher(-1); }
    else if (e.key === 'f' || e.key === 'F') visor.enquadrar('iso');
    else if (e.key === 'm' || e.key === 'M') (medindo ? (pararMedida(), fecharPainel()) : iniciarMedida());
  });
}

/** O navegador tira a placa de vídeo do 3D quando falta memória (o modelo grande aberto também no editor ou noutra
 *  tela): o quadro fica só com o fundo, sem erro nenhum — o 3D ao lado do relatório "não carregava" (09/10). Aqui a
 *  tela avisa, o registro do servidor guarda, e volta sozinha quando a placa é devolvida. */
function vigiarPlacaDeVideo(tela) {
  tela.addEventListener('webglcontextlost', (ev) => {
    ev.preventDefault();                                     // pede a placa de volta
    try { if (window.__registrarLento) window.__registrarLento({ tipo: 'erro', mensagem: 'o 3D perdeu a placa de vídeo (webglcontextlost)', onde: 'ver3d' }); } catch (e) { /* sem registro */ }
    let aviso = $('#placa-perdida');
    if (!aviso) {
      aviso = document.createElement('div');
      aviso.id = 'placa-perdida';
      aviso.innerHTML = '<div><b>O 3D ficou sem a placa de vídeo.</b><div style="margin:8px 0">Falta memória de vídeo: o modelo '
        + 'também está aberto no editor ou noutra tela. Feche o 3D que não está usando e recarregue.</div>'
        + '<button class="botao" type="button">Recarregar o 3D</button></div>';
      aviso.querySelector('button').onclick = () => location.reload();
      $('#palco').append(aviso);
    }
  });
  tela.addEventListener('webglcontextrestored', () => location.reload());
}

// ------------------------------------------------------------------ cobertura retrátil

/** Aberta / Retraída na barra — só no projeto com cobertura retrátil: a análise estrutural a declara, ou ela já foi
 *  vista numa das situações. Antes eram dois itens do menu Modelo, em todo projeto, e a cobertura é coisa de um
 *  projeto (Kaefer, 19/10). Como antes, a escolha grava o modelo nessa situação (POST cobertura-movel) e o 3D recarrega;
 *  a planta ao lado também, se as linhas das tesouras mudaram. */
async function coberturaRetratil() {
  let pj;
  try {
    const j = await (await fetch(`/api/projetos/${encodeURIComponent(PROJETO)}`, { cache: 'no-store' })).json();
    pj = j.projeto || j;
  } catch (e) { return; }
  if (!((pj.analise_parametros || {}).cobertura_movel || pj.cobertura_movel_vista)) return;
  const atual = pj.cobertura_movel_vista || null;
  const caixa = $('#cobertura');
  const botoes = caixa.querySelectorAll('button');
  caixa.hidden = false;
  document.querySelector('[data-cobertura]').hidden = false;
  botoes.forEach(b => {
    b.classList.toggle('ligado', b.dataset.situacao === atual);
    b.onclick = async () => {
      if (b.dataset.situacao === atual) return;
      botoes.forEach(x => { x.disabled = true; });
      try {
        const r = await fetch(`/api/projetos/${encodeURIComponent(PROJETO)}/cobertura-movel`, {
          method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
          body: JSON.stringify({ situacao: b.dataset.situacao }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || j.erro) throw new Error(j.erro || 'erro no servidor');
        if (j.planta_mudou && NA_DIVIDIDA) {
          try { window.parent.postMessage({ metalica: 'planta-mudou', desenho: j.planta_mudou }, location.origin); } catch (e) { /* sem a tela de fora */ }
        }
        location.reload();
      } catch (e) {
        window.alert('Cobertura retrátil: ' + e.message);
        botoes.forEach(x => { x.disabled = false; });
      }
    };
  });
}
if (PROJETO) coberturaRetratil();

abrir().catch(e => {
  console.error(e);
  const c = $('#carregando');
  if (c) c.innerHTML = `<div><b>Não foi possível abrir o modo ver.</b><div style="margin:8px 0">${esc(e.message || e)}</div>
    <button class="botao" onclick="window.visorLeve.editar()">Abrir no editor</button></div>`;
});
