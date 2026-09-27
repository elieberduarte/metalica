/* Tela dividida (/dividida?projeto=…): o Desenho 2D e o modelo 3D do mesmo projeto lado a lado.
 *
 * Cada lado é a própria tela (o CAD e o editor 3D, cada um no seu quadro); esta página só os
 * põe juntos e passa a seleção de um para o outro (postMessage, mesma origem):
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
  if (!desl) { avisar('Este projeto não tem a ligação entre o desenho e o modelo: monte o 3D pela planta de novo (Desenho 2D → Montar o 3D pela planta).', 0); return; }
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
  if (!desl) { avisar('Sem a ligação entre o desenho e o modelo: monte o 3D pela planta de novo.', 0); return; }
  para3d({ metalica: 'selecionar3d', caixa: [[m.caixa[0][0] + desl[0], m.caixa[0][1] + desl[1]], [m.caixa[1][0] + desl[0], m.caixa[1][1] + desl[1]]] });
}

async function iniciar() {
  $('#btn-voltar').addEventListener('click', () => { if (history.length > 1) history.back(); else location.href = '/'; });
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
    document.title = `2D + 3D — ${projeto.nome || PROJETO}`;
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
  const carregar2d = (nome) => { $('#f2d').src = `/cad?projeto=${encodeURIComponent(PROJETO)}` + (nome ? `&desenho=${encodeURIComponent(nome)}` : ''); };
  sel.addEventListener('change', () => carregar2d(sel.value));
  carregar2d(inicial);
  $('#f3d').src = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
  try { trelicas = ((await pedir(`/api/projetos/${encodeURIComponent(PROJETO)}/trelicas`)).trelicas || []).filter(t => t.caixa_desenho); }
  catch (e) { trelicas = []; }
  if (!desl) avisar('Para ligar os dois lados, monte o 3D pela planta de novo (a montagem grava onde o desenho fica no modelo).', 12000);
  window.addEventListener('message', (ev) => {
    if (ev.origin !== location.origin || !ev.data || !ev.data.metalica) return;
    if (ev.data.metalica === 'sel3d' && ev.source === $('#f3d').contentWindow) doTresD(ev.data);
    else if (ev.data.metalica === 'sel2d' && ev.source === $('#f2d').contentWindow) doDoisD(ev.data);
  });
  document.body.dataset.pronto = '1';
}

iniciar();
