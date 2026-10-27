/* A área de trabalho do projeto (/dividida?projeto=…&vista=2d|3d|ambos): o Desenho 2D e o modelo 3D
 * como vistas da mesma tela. Cada um é a própria tela, no seu quadro; trocar de vista só mostra ou
 * esconde o quadro — o 3D é montado uma vez (antes, cada troca abria a outra tela do zero e o modelo
 * de milhares de peças levava segundos para aparecer). Cada quadro carrega na primeira vez que é
 * mostrado. As telas pedem para ir ao outro lado por postMessage ("navegar", web/area.js): o
 * "Abrir o modelo 3D" depois de montar pela planta recarrega o 3D (o modelo mudou) e troca a vista.
 *
 * Na vista 2D + 3D, a seleção passa de um lado para o outro (com a Montagem aberta no 2D, pelo trecho na Implantação e
 * pelo corte do 3D nas elevações — web/cad/corte_eixos.js, doTresD):
 *   3D → 2D  a caixa em planta do que se escolheu vira a região no desenho (o modelo é o desenho
 *            + o deslocamento que a montagem pela planta gravou), ou, no modo "a elevação", a
 *            moldura da elevação da treliça escolhida (da tela Treliças lidas);
 *   2D → 3D  o que se escolhe dentro da moldura de uma elevação seleciona o bloco dela (todas as
 *            cópias); a peça do detalhamento, pela marca dela (a posição ou o conjunto — na
 *            localização e na chumbação, a própria peça); na planta, as peças na caixa da seleção.
 */
'use strict';

const $ = (s) => document.querySelector(s);
const PARAMS = new URLSearchParams(location.search);
const PROJETO = PARAMS.get('projeto') || '';
const CHAVE = 'metalica.dividida';
let pref = { largura: 0.5, trocado: false, modo: 'planta', seguir: true };
let vista = ['2d', '3d', 'ambos'].includes(PARAMS.get('vista')) ? PARAMS.get('vista') : 'ambos';
const fontes = { f2d: '', f3d: '' };      // o endereço de cada quadro (carregado na primeira vez que aparece)
try { pref = { ...pref, ...JSON.parse(localStorage.getItem(CHAVE) || '{}') }; } catch (e) { /* sem armazenamento */ }
const guardar = () => { try { localStorage.setItem(CHAVE, JSON.stringify(pref)); } catch (e) { /* idem */ } };

let desl = null;             // [dx, dy]: modelo = desenho + desl
// a planta de cada peça (22/10, a terça do Posto V2 caía na planta de 6,00): o deslocamento de cada planta lida, além do
// geral (modelo = desenho + desl + fontes[planta]), e a camada das peças de cada outra planta (mezanino, caixa d'água)
let fontesPlanta = {};
let camadasPlanta = {};
// a caixa de cada planta no desenho ({planta: [[x0, y0], [x1, y1]]}): a escolha no 2D vai às peças daquela planta, com o
// deslocamento dela (26/10, Edifício Administrativo da Hora Certa: 4 pavimentos, cada um numa planta do Original)
let regioesPlanta = {};
let elevacoesPlanta = [];    // os cortes do desenho, cada um na linha do modelo dele (26/10, os pórticos do Galpão Novo)
let desenhoDaPlanta = '';    // o desenho de onde a montagem leu a planta
let trelicas = [];           // [{nome, caixa_desenho}] da tela Treliças lidas
let avisoTimer = null;
let avisouSemLigacao = false;

function avisar(txt, ms = 6000) {
  const a = $('#aviso');
  a.textContent = txt;
  a.hidden = !txt;
  clearTimeout(avisoTimer);
  if (txt && ms) avisoTimer = setTimeout(() => { a.hidden = true; }, ms);
}

/** Com os dois completos — o "Detalhamento – completo" da metálica e o "pré-moldado – completo" (16/10) —, o da
 *  disciplina escolhida no CAD para este projeto (a chave MET/PRÉ, web/cad/estrutura.js); sem escolha, o do projeto
 *  pré-moldado; senão o gerado por último (a lista vem do mais novo): depois de "Detalhar pré-moldado", o dele. */
function completoDaDisciplina(completos, projeto) {
  if (completos.length < 2) return completos[0];
  const ePM = (d) => /^pr[eé]-moldado-/.test(d.nome || '');
  let disc = '';
  try { disc = localStorage.getItem(`cad.estrutura.disciplina.${PROJETO}`) || ''; } catch (e) { disc = ''; }
  if (!disc && (projeto || {}).area === 'premoldado') disc = 'premoldado';
  if (disc) return completos.find(d => ePM(d) === (disc === 'premoldado')) || completos[0];
  return completos[0];
}

async function pedir(rota) {
  const r = await fetch(rota, { cache: 'no-store' });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function carregarQuadros() {
  for (const [id, lado] of [['f2d', '2d'], ['f3d', '3d']]) {
    const f = $('#' + id);
    const visivel = vista === 'ambos' || vista === lado;
    if (visivel && fontes[id] && f.dataset.src !== fontes[id]) { f.dataset.src = fontes[id]; f.src = fontes[id]; }
  }
}

/** o estado da área para as barras das duas telas (o seletor e a ligação moram nelas) */
function avisarEstado() {
  const msg = { metalica: 'estado', vista, seguir: !!pref.seguir, modo: pref.modo };
  para2d(msg); para3d(msg);
}

function mostrarVista(v, gravar = true) {
  if (window.barraUnica) window.barraUnica.vista(v);
  if (window.faixaFerramentas) window.faixaFerramentas.vista(v);
  vista = v;
  document.body.classList.remove('v-2d', 'v-3d', 'v-ambos');
  document.body.classList.add('v-' + v);
  for (const b of document.querySelectorAll('.vistas button')) b.classList.toggle('ativo', b.dataset.vista === v);
  carregarQuadros();
  if (v !== 'ambos') para2d({ metalica: 'enquadrar2d', caixa: null });
  const u = new URL(location.href); u.searchParams.set('vista', v); history.replaceState(null, '', u);
  if (gravar) guardar();
  avisarEstado();
}

/** um pedido de ir ao 2D ou ao 3D, vindo de dentro de um quadro */
function navegar(url) {
  const u = new URL(url, location.origin);
  if (u.pathname === '/dividida' || u.pathname === '/2d-3d') {
    const v = u.searchParams.get('vista');
    if (v) mostrarVista(v);
    return;
  }
  const tres = ['/editor', '/editor3d', '/3d', '/visor3d/ver3d.html'].includes(u.pathname);
  const id = tres ? 'f3d' : 'f2d';
  if (!u.searchParams.get('projeto')) u.searchParams.set('projeto', PROJETO);
  if (!tres && desenhoNoLugar(u)) return;
  fontes[id] = u.pathname + u.search;
  $('#' + id).dataset.src = '';                // recarrega: o pedido traz o que mudou (modelo novo, destaque…)
  if (!tres && u.searchParams.get('desenho')) $('#desenho').value = u.searchParams.get('desenho');
  mostrarVista(vista === 'ambos' ? 'ambos' : (tres ? '3d' : '2d'));
  carregarQuadros();
}

function aplicarLayout() {
  $('#quadro').classList.toggle('trocado', !!pref.trocado);
  const f = Math.min(0.85, Math.max(0.15, pref.largura || 0.5));
  $('#lado-2d').style.flex = `0 0 calc(${(f * 100).toFixed(2)}% - 3.5px)`;
  $('#lado-3d').style.flex = '1 1 0';
  for (const b of document.querySelectorAll('.grupo-modo button')) b.classList.toggle('ativo', b.dataset.modo === pref.modo);
  $('#seguir').checked = !!pref.seguir;
}

function ligarDivisor() {
  const d = $('#divisor'), q = $('#quadro');
  d.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    d.setPointerCapture(ev.pointerId);
    d.classList.add('arrastando'); q.classList.add('arrastando');
    const mover = (e) => {
      const r = q.getBoundingClientRect();
      let f = (e.clientX - r.left) / r.width;
      if (pref.trocado) f = 1 - f;
      pref.largura = Math.min(0.85, Math.max(0.15, f));
      aplicarLayout();
    };
    const soltar = () => {
      d.classList.remove('arrastando'); q.classList.remove('arrastando');
      d.removeEventListener('pointermove', mover); d.removeEventListener('pointerup', soltar);
      guardar();
    };
    d.addEventListener('pointermove', mover);
    d.addEventListener('pointerup', soltar);
  });
  d.addEventListener('dblclick', () => { pref.largura = 0.5; aplicarLayout(); guardar(); });
}

const para2d = (msg) => { try { $('#f2d').contentWindow.postMessage(msg, location.origin); } catch (e) { /* quadro recarregando */ } };
const para3d = (msg) => { try { $('#f3d').contentWindow.postMessage(msg, location.origin); } catch (e) { /* idem */ } };

function dentro(c, p) { return p[0] >= c[0][0] && p[0] <= c[1][0] && p[1] >= c[0][1] && p[1] <= c[1][1]; }

function doTresD(m) {
  if (!pref.seguir) return;
  // a Montagem, se estiver aberta no 2D, acha o trecho na implantação e o corte nas elevações pelos ids das peças (21/10)
  para2d({ metalica: 'do3d', n: m.n || 0, ids: (m.marcas || {}).ids || [], caixa: m.caixa || null, nomes: m.nomes || [] });
  if (!m.n) { para2d({ metalica: 'enquadrar2d', caixa: null }); return; }
  if (pref.modo === 'elevacao') {
    const t = m.nomes && m.nomes.length === 1 ? trelicas.find(x => x.nome === m.nomes[0]) : null;
    if (t && t.caixa_desenho) {
      para2d({ metalica: 'enquadrar2d', caixa: t.caixa_desenho, margem: 0.06, dica: `Elevação ${t.nome}, como o projeto desenha.` });
      return;
    }
    // o corte do pórtico onde a peça está (pela linha dele no modelo): o 2D vai ao trecho dela no corte
    const el = m.caixa ? elevacaoDaCaixa(m.caixa) : null;
    if (el) {
      const us = cantos(m.caixa).map(p => uDaElevacao(el, p));
      const u0 = Math.min(...us), u1 = Math.max(...us), um = (u0 + u1) / 2, w = Math.max(u1 - u0, 3000);
      const [[, v0], [, v1]] = el.caixa_desenho;
      para2d({ metalica: 'enquadrar2d', caixa: [[um - w / 2, v0], [um + w / 2, v1]], margem: 0.1,
               dica: (m.nomes || []).length === 1 ? `${m.nomes[0]} no ${el.nome}.` : `${m.n} peça(s) do 3D no ${el.nome}.` });
      return;
    }
    if (m.nomes && m.nomes.length > 1) avisar('Várias treliças escolhidas: o 2D mostra a elevação quando o 3D tem uma só.');
    else if (!(m.nomes || []).length) avisar('Essa peça não veio de uma elevação: o 2D mostra o lugar dela na planta.', 4000);
  }
  if (!desl) {
    // o projeto do IFC: o 2D vai ao detalhe da peça pelas marcas dela (a célula da posição ou do conjunto; na
    // localização, a própria peça) — pedido do usuário, 29/09
    const mk = m.marcas || {};
    if ((mk.posicoes || []).length || (mk.conjuntos || []).length || (mk.ids || []).length) para2d({ metalica: 'localizar2d', ...mk });
    return;
  }
  if (!m.caixa) return;
  const c = caixaDe(m.caixa, p => aoDesenho(p, chaveDaFonte(m.fontes)));
  // uma peça pequena não pode virar um zoom de milímetros: a região tem ao menos 3 m
  const cx = (c[0][0] + c[1][0]) / 2, cy = (c[0][1] + c[1][1]) / 2;
  const w = Math.max(c[1][0] - c[0][0], 3000), h = Math.max(c[1][1] - c[0][1], 3000);
  // o eixo de cada barra escolhida, neste desenho: o 2D acende as linhas que caem sobre ele (a terça, não a região)
  const linhas = (m.eixos || []).map(([a, b, k]) => {
    const fk = chaveDaFonte([k]);
    return [aoDesenho(a, fk), aoDesenho(b, fk)];
  });
  para2d({ metalica: 'enquadrar2d', caixa: [[cx - w / 2, cy - h / 2], [cx + w / 2, cy + h / 2]], margem: 0.35, linhas,
           dica: (m.nomes || []).length === 1 ? `${m.nomes[0]} na planta.` : `${m.n} peça(s) do 3D na planta.` });
}

/** o deslocamento da planta de onde vieram as peças escolhidas (a mais frequente): a marcada na peça (fonte_2d) ou, no
 *  modelo de antes, pelo papel e pela camada — a terça, a corrente e o contravento na planta das terças, o pilar na
 *  locação, a peça da camada do mezanino na planta dele; o resto na planta estrutural */
function fonteDaChave(k) {
  if (!k) return 'planta';
  if (!k.startsWith('?')) return k;
  const [papel, camada] = k.slice(1).split('|');
  if (camada && camadasPlanta[camada]) return camadasPlanta[camada];
  if (['terça', 'terca', 'corrente', 'contraventamento', 'apoio_terca'].includes(papel)) return 'tercas';
  if (papel === 'pilar') return 'locacao';
  return 'planta';
}
/** a planta (chave de fontesPlanta) das peças escolhidas: a primeira que tem ligação gravada; senão nenhuma (a geral) */
function chaveDaFonte(chaves) {
  for (const k of chaves || []) {
    const f = fonteDaChave(k);
    if (transfDaFonte(f)) return f;
  }
  return '';
}
/** a ligação de uma planta: [dx, dy], ou {deslocamento: [dx, dy], giro: graus} quando a planta está girada no desenho
 *  (26/10, Galpão Novo da Hora Certa: as coberturas G1–G4 desenham os eixos A–Q no sentido de x) */
function transfDaFonte(f) {
  const d = fontesPlanta[f];
  if (Array.isArray(d) && d.length === 2) return { d: d.map(Number), g: 0 };
  if (d && Array.isArray(d.deslocamento) && d.deslocamento.length === 2) {
    return { d: d.deslocamento.map(Number), g: (Number(d.giro) || 0) * Math.PI / 180 };
  }
  return null;
}
/** modelo = gira(desenho, giro da planta) + desl + deslocamento da planta, e a volta */
function aoModelo(p, f) {
  const t = transfDaFonte(f) || { d: [0, 0], g: 0 };
  const c = Math.cos(t.g), s = Math.sin(t.g);
  return [p[0] * c - p[1] * s + desl[0] + t.d[0], p[0] * s + p[1] * c + desl[1] + t.d[1]];
}
function aoDesenho(p, f) {
  const t = transfDaFonte(f) || { d: [0, 0], g: 0 };
  const x = p[0] - desl[0] - t.d[0], y = p[1] - desl[1] - t.d[1];
  const c = Math.cos(t.g), s = Math.sin(t.g);
  return [x * c + y * s, -x * s + y * c];
}
function cantos(cx) { return [[cx[0][0], cx[0][1]], [cx[1][0], cx[0][1]], [cx[0][0], cx[1][1]], [cx[1][0], cx[1][1]]]; }
/** a caixa [[x0, y0], [x1, y1]] levada por fn: a caixa dos 4 cantos (a planta girada troca largura e altura) */
function caixaDe(cx, fn) {
  const ps = cantos(cx).map(fn);
  const xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}

/** Os cortes (26/10, Galpão Novo da Hora Certa: um corte por pórtico, AA…QQ): planta_modelo.elevacoes =
 *  [{nome, caixa_desenho, u0, origem: [x, y], direcao: [dx, dy], faixa}] — o corte é a linha do modelo que passa por
 *  `origem` na `direcao`; no desenho ela começa em x = u0 e cresce para a direita, em tamanho real. A peça está no corte
 *  quando o meio dela fica a até `faixa` mm da linha. */
function direcaoDe(el) {
  const n = Math.hypot(el.direcao[0], el.direcao[1]) || 1;
  return [el.direcao[0] / n, el.direcao[1] / n];
}
function uDaElevacao(el, p) {
  const d = direcaoDe(el);
  return Number(el.u0) + (p[0] - el.origem[0]) * d[0] + (p[1] - el.origem[1]) * d[1];
}
function elevacaoDaCaixa(cx) {
  const c = [(cx[0][0] + cx[1][0]) / 2, (cx[0][1] + cx[1][1]) / 2];
  let melhor = null, d0 = Infinity;
  for (const el of elevacoesPlanta) {
    const d = direcaoDe(el);
    const dist = Math.abs(-(c[0] - el.origem[0]) * d[1] + (c[1] - el.origem[1]) * d[0]);
    if (dist <= (Number(el.faixa) || 1000) && dist < d0) { melhor = el; d0 = dist; }
  }
  return melhor;
}
/** o ponto da linha do corte em u, no modelo */
function pontoDaElevacao(el, u) {
  const d = direcaoDe(el);
  return [el.origem[0] + (u - el.u0) * d[0], el.origem[1] + (u - el.u0) * d[1]];
}
/** o trecho [u0, u1] do corte, no modelo: a faixa em volta da linha */
function caixaDaElevacao(el, ua, ub) {
  const d = direcaoDe(el), n = [-d[1], d[0]], f = Number(el.faixa) || 1000;
  const ps = [pontoDaElevacao(el, ua), pontoDaElevacao(el, ub)].flatMap(p => [[p[0] + n[0] * f, p[1] + n[1] * f], [p[0] - n[0] * f, p[1] - n[1] * f]]);
  const xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}
/** o mesmo trecho como faixa: as pontas da linha e a largura. O 3D escolhe pela distância à linha — a caixa alinhada aos
 *  eixos, com os 0,30 de folga dela, pegava o prédio por dentro na fachada oblíqua e a tesoura da linha Q, a 0,29 do
 *  fechamento (27/10, Galpão Novo da Hora Certa) */
function faixaDaElevacao(el, ua, ub) {
  return { a: pontoDaElevacao(el, ua), b: pontoDaElevacao(el, ub), largura: Number(el.faixa) || 1000 };
}

function doDoisD(m) {
  if (!pref.seguir) return;
  // clicou fora no 2D (nada selecionado): o 3D larga a seleção também (06/10)
  if (!m.n) { para3d({ metalica: 'selecionar3d', limpar: true }); return; }
  // a Montagem (21/10): a peça do corte pelo id dela; a escolha na Implantação pela caixa em planta, já em mm do modelo
  if (m.montagem) {
    if (m.alvo) para3d({ metalica: 'selecionar3d', destacar: m.alvo });
    else if (m.caixa_modelo) para3d({ metalica: 'selecionar3d', caixa: m.caixa_modelo });
    return;
  }
  if (!m.caixa) return;
  const meio = [(m.caixa[0][0] + m.caixa[1][0]) / 2, (m.caixa[0][1] + m.caixa[1][1]) / 2];
  const t = trelicas.find(x => x.caixa_desenho && dentro(x.caixa_desenho, meio));
  if (t) { para3d({ metalica: 'selecionar3d', nome: t.nome }); return; }
  // a peça do detalhamento pela marca (ou, na localização, a própria peça): vale no projeto do IFC, que
  // não tem a ligação pela planta (pedido do usuário, 29/09)
  if (m.alvo) { para3d({ metalica: 'selecionar3d', destacar: m.alvo }); return; }
  // dentro do quadro de um corte: as peças do trecho escolhido, na linha do pórtico (26/10)
  const el = elevacoesPlanta.find(x => dentro(x.caixa_desenho, meio));
  if (el) {
    para3d({ metalica: 'selecionar3d', caixa: caixaDaElevacao(el, m.caixa[0][0], m.caixa[1][0]),
             faixa: faixaDaElevacao(el, m.caixa[0][0], m.caixa[1][0]) });
    return;
  }
  if (!desl) {
    // cota, texto ou traço sem peça: no projeto do IFC não há a ligação pela planta — avisa uma vez só
    if (!avisouSemLigacao) avisar('Essa seleção não é de uma peça do modelo (cota, texto ou desenho à mão): o 3D fica como está.', 5000);
    avisouSemLigacao = true;
    return;
  }
  const fonte = Object.keys(regioesPlanta).find(k => Array.isArray(regioesPlanta[k]) && dentro(regioesPlanta[k], meio));
  para3d({ metalica: 'selecionar3d', caixa: caixaDe(m.caixa, p => aoModelo(p, fonte || '')),
           ...(fonte ? { fonte } : {}) });
}

function referencia3d() {
  let w = null;
  try { w = $('#f3d').contentWindow; } catch (e) { w = null; }
  if (!w) return;
  try {
    if (w.editor && typeof w.editor._carregarReferencia === 'function') { w.editor._carregarReferencia(); return; }
    w.postMessage({ metalica: 'referencia-mudou' }, location.origin);
  } catch (e) { /* outra tela */ }
}

/** O CAD já aberto neste projeto só troca de desenho, sem recarregar o quadro (15/10: o Editar chapa recarregava o CAD
 *  inteiro). Só quando o pedido traz o desenho (e o "voltar" da edição) e nada mais; senão, false. */
function desenhoNoLugar(u) {
  const d = u.searchParams.get('desenho');
  if (!d || !['/cad', '/desenho'].includes(u.pathname)) return false;
  if ([...u.searchParams.keys()].some(k => !['projeto', 'desenho', 'voltar'].includes(k))) return false;
  const f = $('#f2d');
  let w = null;
  try { w = f.contentWindow; } catch (e) { return false; }
  try {
    if (!f.dataset.src || !w || !w.cad || typeof w.cad.abrirDesenho !== 'function') return false;
    if (new URL(w.location.href).searchParams.get('projeto') !== u.searchParams.get('projeto')) return false;
    w.cad._voltarEdicao = u.searchParams.get('voltar') || undefined;
    w.cad.abrirDesenho(d);
  } catch (e) { return false; }
  $('#desenho').value = d;
  mostrarVista(vista === 'ambos' ? 'ambos' : '2d');
  return true;
}

/** O 2D mudou o modelo pela edição da chapa (Concluir): o 3D aberto troca só as peças que mudaram; sem ele (o modo
 *  ver, o editor com edição por gravar), recarrega como antes. */
async function sincronizar3d() {
  mostrarVista(vista === 'ambos' ? 'ambos' : '3d');
  let w = null;
  try { w = $('#f3d').contentWindow; } catch (e) { w = null; }
  try {
    if (w && w.editor && typeof w.editor.sincronizarComServidor === 'function' && await w.editor.sincronizarComServidor()) return;
  } catch (e) { /* recarrega */ }
  recarregar3d();
}

function recarregar3d() {
  const f = $('#f3d');
  let w = null;
  try { w = f.contentWindow; } catch (e) { w = null; }
  if (!w) return;
  try {
    if (w.visorLeve || /\/visor3d\//.test(w.location.pathname)) { w.location.reload(); return; }
    const ed = w.editor;
    const pendente = !!(ed && (ed._autosavePendente || ed._salvando));            // edição do 3D ainda não gravada
    if (!pendente) { w.location.reload(); return; }
  } catch (e) { /* outra tela */ }
  avisar('A planta mudou o modelo 3D: grave o que está aberto no 3D e recarregue (F5) para ver.', 6000);
}

async function iniciar() {
  // ouvido antes de carregar os quadros: o primeiro pedido de estado chega logo
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin || !ev.data || !ev.data.metalica) return;
    const deUmLado = ev.source === $('#f2d').contentWindow || ev.source === $('#f3d').contentWindow;
    if (ev.data.metalica === 'navegar' && deUmLado) { navegar(ev.data.url); return; }
    if (ev.data.metalica === 'modelo-editado' && ev.source === $('#f2d').contentWindow) { sincronizar3d(); return; }
    // o 2D mudou o modelo (a planta da Estrutura sincronizou o 3D): o modo ver recarrega já; o editor, sem edição
    // pendente, também (com, avisa) — 06/10
    if (ev.data.metalica === 'modelo-mudou' && ev.source === $('#f2d').contentWindow) { recarregar3d(); return; }
    // os níveis, a malha de eixos ou o arquitetônico mudaram no 2D: o 3D ao lado refaz a planta no chão
    if (ev.data.metalica === 'referencia-mudou' && ev.source === $('#f2d').contentWindow) { referencia3d(); return; }
    // o 3D mudou a planta (a cobertura retrátil aberta/retraída): o 2D ao lado recarrega o desenho
    if (ev.data.metalica === 'planta-mudou' && ev.source === $('#f3d').contentWindow) { para2d({ metalica: 'recarregar2d', desenho: ev.data.desenho }); return; }
    // o seletor e os controles da ligação estão na barra de cada tela
    if (ev.data.metalica === 'vista' && deUmLado) { mostrarVista(ev.data.vista); return; }
    if (ev.data.metalica === 'pedir-estado' && deUmLado) { avisarEstado(); return; }
    if (ev.data.metalica === 'controle' && deUmLado) {
      if (ev.data.seguir !== undefined) { pref.seguir = !!ev.data.seguir; if (!pref.seguir) para2d({ metalica: 'enquadrar2d', caixa: null }); }
      if (ev.data.modo) pref.modo = ev.data.modo;
      if (ev.data.trocar) pref.trocado = !pref.trocado;
      aplicarLayout(); guardar(); avisarEstado();
      return;
    }
    if (ev.data.metalica === 'desenho2d' && ev.source === $('#f2d').contentWindow && ev.data.desenho) {
      // o CAD abriu outro desenho (pela lista dele, ou a prancha depois de montar): o endereço guarda, para
      // o F5 voltar a ele (pedido do usuário, 28/09), e a lista de cima mostra o mesmo
      const u = new URL(location.href);
      u.searchParams.set('desenho', ev.data.desenho);
      history.replaceState(history.state, '', u);
      const sel = $('#desenho');
      if (sel && ![...sel.options].some(o => o.value === ev.data.desenho)) {
        const o = document.createElement('option');
        o.value = ev.data.desenho; o.textContent = ev.data.titulo || ev.data.desenho;
        sel.append(o);
      }
      if (sel) sel.value = ev.data.desenho;
      return;
    }
    if (vista !== 'ambos') return;
    if (ev.data.metalica === 'sel3d' && ev.source === $('#f3d').contentWindow) doTresD(ev.data);
    else if (ev.data.metalica === 'sel2d' && ev.source === $('#f2d').contentWindow) doDoisD(ev.data);
  });
  for (const b of document.querySelectorAll('.vistas button')) b.addEventListener('click', () => mostrarVista(b.dataset.vista));
  // os painéis da direita dos dois lados de uma vez: segue o estado do lado que está à vista
  $('#btn-paineis').addEventListener('click', () => {
    let visiveis = true;
    for (const id of ['f3d', 'f2d']) {
      try { const d = $('#' + id).contentDocument; if (d && d.querySelector('#paineis') && $('#' + id).offsetParent) { visiveis = !d.documentElement.classList.contains('sem-paineis'); break; } }
      catch (e) { /* quadro ainda carregando */ }
    }
    para2d({ metalica: 'paineis', mostrar: !visiveis });
    para3d({ metalica: 'paineis', mostrar: !visiveis });
  });
  $('#btn-trocar').addEventListener('click', () => { pref.trocado = !pref.trocado; aplicarLayout(); guardar(); });
  $('#seguir').addEventListener('change', () => { pref.seguir = $('#seguir').checked; guardar(); if (!pref.seguir) para2d({ metalica: 'enquadrar2d', caixa: null }); });
  for (const b of document.querySelectorAll('.grupo-modo button')) {
    b.addEventListener('click', () => { pref.modo = b.dataset.modo; aplicarLayout(); guardar(); });
  }
  aplicarLayout();
  ligarDivisor();
  if (!PROJETO) { avisar('Abra esta tela pelo projeto (Ver → Dividir com o 2D, no modelo 3D).', 0); return; }
  let projeto = {}, desenhos = [];
  try {
    const p = await pedir('/api/projetos/' + encodeURIComponent(PROJETO));
    projeto = p.projeto || {};
    desenhos = (p.resumo && p.resumo.desenhos) || [];
    $('#nome-projeto').textContent = projeto.nome || PROJETO;
    document.querySelector('.area-topo .marca').title = projeto.nome || PROJETO;
    document.title = `${projeto.nome || PROJETO} — Metálica`;
  } catch (e) { avisar(`Projeto não encontrado: ${e.message}`, 0); return; }
  const pm = projeto.planta_modelo || {};
  if (Array.isArray(pm.deslocamento) && pm.deslocamento.length === 2) desl = pm.deslocamento.map(Number);
  fontesPlanta = (pm.fontes && typeof pm.fontes === 'object') ? pm.fontes : {};
  camadasPlanta = (pm.camadas && typeof pm.camadas === 'object') ? pm.camadas : {};
  regioesPlanta = (pm.regioes && typeof pm.regioes === 'object') ? pm.regioes : {};
  elevacoesPlanta = (Array.isArray(pm.elevacoes) ? pm.elevacoes : [])
    .filter(e => e && Array.isArray(e.caixa_desenho) && Array.isArray(e.origem) && Array.isArray(e.direcao) && isFinite(Number(e.u0)));
  desenhoDaPlanta = pm.desenho || '';
  // o detalhamento completo (tudo num desenho só) primeiro na lista, e é nele que o 2D abre quando o
  // endereço não pede outro desenho
  const eCompleto = (d) => /(^|-)completo$/.test(d.nome || '');
  desenhos.sort((a, b) => Number(eCompleto(b)) - Number(eCompleto(a)));
  const completo = completoDaDisciplina(desenhos.filter(eCompleto), projeto);
  const inicial = PARAMS.get('desenho') || (completo && completo.nome) || desenhoDaPlanta || (desenhos[0] && desenhos[0].nome) || '';
  const sel = $('#desenho');
  for (const d of desenhos) {
    const o = document.createElement('option');
    o.value = d.nome; o.textContent = d.titulo || d.nome;
    if (d.nome === inicial) o.selected = true;
    sel.append(o);
  }
  if (!desenhos.length) { const o = document.createElement('option'); o.textContent = '— sem desenho —'; sel.append(o); sel.disabled = true; }
  const carregar2d = (nome) => { fontes.f2d = `/cad?projeto=${encodeURIComponent(PROJETO)}` + (nome ? `&desenho=${encodeURIComponent(nome)}` : ''); carregarQuadros(); };
  sel.addEventListener('change', () => carregar2d(sel.value));
  // o 3D leva junto o que veio na URL para ele (destacar=…, lancar=1)
  const extra3d = ['destacar', 'lancar'].filter(k => PARAMS.get(k)).map(k => `&${k}=${encodeURIComponent(PARAMS.get(k))}`).join('');
  // abrir o projeto é quase sempre para ver: sem pedido especial, o 3D abre no modo "ver" (web/visor3d),
  // que chega pronto para a placa de vídeo e abre em menos de um segundo; Editar — ou um comando de edição
  // da barra — carrega o editor no mesmo quadro, com a mesma vista. &editar=1 abre direto no editor.
  const editar = !!extra3d || PARAMS.get('editar') === '1';
  fontes.f3d = editar ? `/editor?projeto=${encodeURIComponent(PROJETO)}` + extra3d
                      : `/visor3d/ver3d.html?projeto=${encodeURIComponent(PROJETO)}`;
  carregar2d(inicial);
  mostrarVista(vista, false);
  try { trelicas = ((await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/trelicas`)).trelicas || []).filter(t => t.caixa_desenho); }
  catch (e) { trelicas = []; }
  document.body.dataset.pronto = '1';
}

window.mostrarVista = mostrarVista;
window.vistaAtual = () => vista;
iniciar();
