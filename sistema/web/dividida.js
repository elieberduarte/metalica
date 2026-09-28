/* A área de trabalho do projeto (/dividida?projeto=…&vista=2d|3d|ambos): o Desenho 2D e o modelo 3D
 * como vistas da mesma tela. Cada um é a própria tela, no seu quadro; trocar de vista só mostra ou
 * esconde o quadro — o 3D é montado uma vez (antes, cada troca abria a outra tela do zero e o modelo
 * de milhares de peças levava segundos para aparecer). Cada quadro carrega na primeira vez que é
 * mostrado. As telas pedem para ir ao outro lado por postMessage ("navegar", web/area.js): o
 * "Abrir o modelo 3D" depois de montar pela planta recarrega o 3D (o modelo mudou) e troca a vista.
 *
 * Na vista 2D + 3D, a seleção passa de um lado para o outro:
 *   3D → 2D  a caixa em planta do que se escolheu vira a região no desenho (o modelo é o desenho
 *            + o deslocamento que a montagem pela planta gravou), ou, no modo "a elevação", a
 *            moldura da elevação da treliça escolhida (da tela Treliças lidas);
 *   2D → 3D  o que se escolhe dentro da moldura de uma elevação seleciona o bloco dela (todas as
 *            cópias); na planta, as peças que caem na caixa da seleção.
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
let desenhoDaPlanta = '';    // o desenho de onde a montagem leu a planta
let trelicas = [];           // [{nome, caixa_desenho}] da tela Treliças lidas
let avisoTimer = null;

function avisar(txt, ms = 6000) {
  const a = $('#aviso');
  a.textContent = txt;
  a.hidden = !txt;
  clearTimeout(avisoTimer);
  if (txt && ms) avisoTimer = setTimeout(() => { a.hidden = true; }, ms);
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
  const tres = ['/editor', '/editor3d', '/3d'].includes(u.pathname);
  const id = tres ? 'f3d' : 'f2d';
  if (!u.searchParams.get('projeto')) u.searchParams.set('projeto', PROJETO);
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
  if (!m.n) { para2d({ metalica: 'enquadrar2d', caixa: null }); return; }
  if (pref.modo === 'elevacao') {
    const t = m.nomes && m.nomes.length === 1 ? trelicas.find(x => x.nome === m.nomes[0]) : null;
    if (t && t.caixa_desenho) {
      para2d({ metalica: 'enquadrar2d', caixa: t.caixa_desenho, margem: 0.06, dica: `Elevação ${t.nome}, como o projeto desenha.` });
      return;
    }
    if (m.nomes && m.nomes.length > 1) avisar('Várias treliças escolhidas: o 2D mostra a elevação quando o 3D tem uma só.');
    else if (!(m.nomes || []).length) avisar('Essa peça não veio de uma elevação: o 2D mostra o lugar dela na planta.', 4000);
  }
  if (!desl) { avisar('Este projeto não tem a ligação entre o desenho e o modelo: monte o 3D pela planta de novo (Desenho 2D → Montar o 3D pela planta).', 8000); return; }
  if (!m.caixa) return;
  const c = [[m.caixa[0][0] - desl[0], m.caixa[0][1] - desl[1]], [m.caixa[1][0] - desl[0], m.caixa[1][1] - desl[1]]];
  // uma peça pequena não pode virar um zoom de milímetros: a região tem ao menos 3 m
  const cx = (c[0][0] + c[1][0]) / 2, cy = (c[0][1] + c[1][1]) / 2;
  const w = Math.max(c[1][0] - c[0][0], 3000), h = Math.max(c[1][1] - c[0][1], 3000);
  para2d({ metalica: 'enquadrar2d', caixa: [[cx - w / 2, cy - h / 2], [cx + w / 2, cy + h / 2]], margem: 0.35,
           dica: (m.nomes || []).length === 1 ? `${m.nomes[0]} na planta.` : `${m.n} peça(s) do 3D na planta.` });
}

function doDoisD(m) {
  if (!pref.seguir || !m.n || !m.caixa) return;
  const meio = [(m.caixa[0][0] + m.caixa[1][0]) / 2, (m.caixa[0][1] + m.caixa[1][1]) / 2];
  const t = trelicas.find(x => x.caixa_desenho && dentro(x.caixa_desenho, meio));
  if (t) { para3d({ metalica: 'selecionar3d', nome: t.nome }); return; }
  if (!desl) { avisar('Sem a ligação entre o desenho e o modelo: monte o 3D pela planta de novo.', 8000); return; }
  para3d({ metalica: 'selecionar3d', caixa: [[m.caixa[0][0] + desl[0], m.caixa[0][1] + desl[1]], [m.caixa[1][0] + desl[0], m.caixa[1][1] + desl[1]]] });
}

async function iniciar() {
  // ouvido antes de carregar os quadros: o primeiro pedido de estado chega logo
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin || !ev.data || !ev.data.metalica) return;
    const deUmLado = ev.source === $('#f2d').contentWindow || ev.source === $('#f3d').contentWindow;
    if (ev.data.metalica === 'navegar' && deUmLado) { navegar(ev.data.url); return; }
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
    document.title = `${projeto.nome || PROJETO} — Metálica`;
  } catch (e) { avisar(`Projeto não encontrado: ${e.message}`, 0); return; }
  const pm = projeto.planta_modelo || {};
  if (Array.isArray(pm.deslocamento) && pm.deslocamento.length === 2) desl = pm.deslocamento.map(Number);
  desenhoDaPlanta = pm.desenho || '';
  const inicial = PARAMS.get('desenho') || desenhoDaPlanta || (desenhos[0] && desenhos[0].nome) || '';
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
  fontes.f3d = `/editor?projeto=${encodeURIComponent(PROJETO)}` + extra3d;
  carregar2d(inicial);
  mostrarVista(vista, false);
  try { trelicas = ((await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/trelicas`)).trelicas || []).filter(t => t.caixa_desenho); }
  catch (e) { trelicas = []; }
  document.body.dataset.pronto = '1';
}

window.mostrarVista = mostrarVista;
window.vistaAtual = () => vista;
iniciar();
