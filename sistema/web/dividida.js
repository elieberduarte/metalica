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
  if (!desl) {
    // o projeto do IFC: o 2D vai ao detalhe da peça pelas marcas dela (a célula da posição ou do conjunto; na
    // localização, a própria peça) — pedido do usuário, 29/09
    const mk = m.marcas || {};
    if ((mk.posicoes || []).length || (mk.conjuntos || []).length || (mk.ids || []).length) para2d({ metalica: 'localizar2d', ...mk });
    return;
  }
  if (!m.caixa) return;
  const c = [[m.caixa[0][0] - desl[0], m.caixa[0][1] - desl[1]], [m.caixa[1][0] - desl[0], m.caixa[1][1] - desl[1]]];
  // uma peça pequena não pode virar um zoom de milímetros: a região tem ao menos 3 m
  const cx = (c[0][0] + c[1][0]) / 2, cy = (c[0][1] + c[1][1]) / 2;
  const w = Math.max(c[1][0] - c[0][0], 3000), h = Math.max(c[1][1] - c[0][1], 3000);
  para2d({ metalica: 'enquadrar2d', caixa: [[cx - w / 2, cy - h / 2], [cx + w / 2, cy + h / 2]], margem: 0.35,
           dica: (m.nomes || []).length === 1 ? `${m.nomes[0]} na planta.` : `${m.n} peça(s) do 3D na planta.` });
}

function doDoisD(m) {
  if (!pref.seguir) return;
  // clicou fora no 2D (nada selecionado): o 3D larga a seleção também (06/10)
  if (!m.n) { para3d({ metalica: 'selecionar3d', limpar: true }); return; }
  if (!m.caixa) return;
  const meio = [(m.caixa[0][0] + m.caixa[1][0]) / 2, (m.caixa[0][1] + m.caixa[1][1]) / 2];
  const t = trelicas.find(x => x.caixa_desenho && dentro(x.caixa_desenho, meio));
  if (t) { para3d({ metalica: 'selecionar3d', nome: t.nome }); return; }
  // a peça do detalhamento pela marca (ou, na localização, a própria peça): vale no projeto do IFC, que
  // não tem a ligação pela planta (pedido do usuário, 29/09)
  if (m.alvo) { para3d({ metalica: 'selecionar3d', destacar: m.alvo }); return; }
  if (!desl) {
    // cota, texto ou traço sem peça: no projeto do IFC não há a ligação pela planta — avisa uma vez só
    if (!avisouSemLigacao) avisar('Essa seleção não é de uma peça do modelo (cota, texto ou desenho à mão): o 3D fica como está.', 5000);
    avisouSemLigacao = true;
    return;
  }
  para3d({ metalica: 'selecionar3d', caixa: [[m.caixa[0][0] + desl[0], m.caixa[0][1] + desl[1]], [m.caixa[1][0] + desl[0], m.caixa[1][1] + desl[1]]] });
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
    // o 2D mudou o modelo (a planta da Estrutura sincronizou o 3D): o modo ver recarrega já; o editor, sem edição
    // pendente, também (com, avisa) — 06/10
    if (ev.data.metalica === 'modelo-mudou' && ev.source === $('#f2d').contentWindow) { recarregar3d(); return; }
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
  desenhoDaPlanta = pm.desenho || '';
  // o detalhamento completo (tudo num desenho só) primeiro na lista, e é nele que o 2D abre quando o
  // endereço não pede outro desenho
  const eCompleto = (d) => /(^|-)completo$/.test(d.nome || '');
  desenhos.sort((a, b) => Number(eCompleto(b)) - Number(eCompleto(a)));
  const completo = desenhos.find(eCompleto);
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
