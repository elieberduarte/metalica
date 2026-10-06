// O modo "ver" do modelo 3D no computador.
//
// Abrir o modelo quase sempre é para ver: aqui ele chega já pronto para a placa de vídeo (o 3D leve,
// saida/modelo_leve.py) e abre em menos de um segundo, mesmo o Bella Casa de 6.896 peças, que no editor
// leva 7–8 s. Editar carrega o editor completo no mesmo lugar, com a mesma vista e a peça escolhida
// (o editor lê a vista em `metalica.vistaDoVisor`, editor.js `_vistaDoVisor`).
//
// Dentro da área de trabalho (/dividida), a barra única e a busca do Ctrl+K falam com esta página por
// `window.visorLeve` (procurar uma peça, passar para o editor antes de um comando de edição).

import { Visor3D } from './visor3d.js';

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

// ------------------------------------------------------------------ editar (o editor completo)

function irParaEditor() {
  if (visor && visor.cabecalho) {
    const cam = visor.lerCamera();
    const sel = visor.selecionada >= 0 && visor.fichas ? [visor.fichas[visor.selecionada].id] : [];
    try {
      sessionStorage.setItem('metalica.vistaDoVisor', JSON.stringify({ projeto: PROJETO, quando: Date.now(), ...cam, selecao: sel }));
    } catch (e) { /* sem armazenamento: abre no enquadramento do editor */ }
  }
  const url = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
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
    if (j.situacao === 'sem modelo') { $('#carregando').innerHTML = '<div><b>Este projeto ainda não tem modelo 3D.</b></div>'; return; }
  }
  if (!r.ok) { irParaEditor(); return; }                                // algo falhou: o editor abre como sempre
  const versao = r.headers.get('X-Versao-3D') || '';
  const buf = await r.arrayBuffer();
  const t0 = performance.now();
  visor = new Visor3D($('#tela'), { mouse: true, arestas: true, maxPixelRatio: 2, fundo: escuro() ? '#1a212c' : '#e4eaf2' });
  window.visor = visor;
  visor.leveAoGirar = false;                                           // no PC sobra placa: a imagem fica inteira ao girar
  await visor.carregar(buf);
  const fichas = await (await fetch(`${API}/pecas?v=${encodeURIComponent(versao)}`)).json();
  visor.definirFichas(fichas);
  const ms = Math.round(performance.now() - t0);
  $('#carregando').remove();
  $('#ferramentas').hidden = false;
  situacao(`Modo ver · ${nf(visor.nPecas)} peças · aberto em ${nf(ms / 1000, 1)} s · Editar carrega o editor completo`);
  window.ver3dPronto = { ms, pecas: visor.nPecas };
  ligar();
}

function situacao(t) { $('#situacao').textContent = t; }

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
  const linhas = [['Perfil', f.p], ['Camada', cam.nome], ['Material', f.m], ['Peso', f.kg ? nf(f.kg, f.kg < 10 ? 2 : 1) + ' kg' : null],
                  ['Posição', f.pos], ['Conjunto', f.cj], ['Marca', f.mc]].filter(x => x[1]);
  abrirPainel('ficha', f.n || 'Peça', `<dl>${linhas.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <p class="dica">Dois cliques giram em volta da peça. Para mudá-la, use <b>Editar</b>.</p>`);
}

function escolher(i, centrar) {
  visor.selecionar(i);
  if (i < 0) { if (painelAtual === 'ficha') fecharPainel(); return; }
  if (centrar) visor.centrarEm(i);
  ficha(i);
}

function painelCamadas() {
  const cams = visor.cabecalho.camadas;
  abrirPainel('camadas', 'Camadas', cams.map((c, i) => c.pecas ? `<label class="linha-lista">
      <input type="checkbox" data-c="${i}" ${visor.visivelCamada[i] !== false ? 'checked' : ''}>
      <i style="background:${esc(c.cor)}"></i><span>${esc(c.nome)}</span><em>${nf(c.pecas)}</em></label>` : '').join(''));
  $('#painel-corpo').querySelectorAll('input[data-c]').forEach(el => el.onchange = () => visor.mostrarCamada(+el.dataset.c, el.checked));
}

function painelLegenda(modo) {
  const titulo = modo === 'camada' ? 'Pintado por camada' : 'Pintado por perfil';
  abrirPainel('legenda', titulo, legenda.slice(0, 200).map((g, k) => `<div class="linha-lista" data-k="${k}">
      <i style="background:${g.cor}"></i><span title="${esc(g.nome)}">${esc(g.nome)}</span><em>${nf(g.n)}</em></div>`).join('')
    + (legenda.length > 200 ? `<p class="dica">e mais ${legenda.length - 200} grupos</p>` : '')
    + '<p class="dica">Clique num grupo para ir à primeira peça dele.</p>');
  $('#painel-corpo').querySelectorAll('[data-k]').forEach(el => el.onclick = () => {
    const g = legenda[+el.dataset.k];
    if (g && g.ids.length) { visor.selecionar(g.ids[0]); visor.centrarEm(g.ids[0]); }
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

function procurar(texto) {
  const t = (texto || '').trim().toLowerCase();
  if (t.length < 2 || !visor || !visor.fichas) return [];
  const out = [];
  visor.fichas.forEach((f, i) => {
    if ((f.n + ' ' + f.p + ' ' + (f.pos || '') + ' ' + (f.mc || '') + ' ' + (f.cj || '')).toLowerCase().includes(t)) out.push(i);
  });
  return out;
}

function painelBusca(texto) {
  const r = procurar(texto);
  if (!r.length) { abrirPainel('busca', 'Buscar', '<p class="dica">Nenhuma peça com esse texto.</p>'); return; }
  abrirPainel('busca', `${nf(r.length)} peça(s)`, r.slice(0, 80).map(i => `<div class="linha-lista" data-i="${i}">
      <span title="${esc(visor.fichas[i].n)}">${esc(visor.fichas[i].n)}</span><em>${esc(visor.fichas[i].p || '')}</em></div>`).join('')
    + (r.length > 80 ? `<p class="dica">e mais ${nf(r.length - 80)}</p>` : ''));
  $('#painel-corpo').querySelectorAll('[data-i]').forEach(el => el.onclick = () => { visor.selecionar(+el.dataset.i); visor.centrarEm(+el.dataset.i); });
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
  $('#painel-fechar').onclick = fecharPainel;
  document.querySelector('[data-painel="camadas"]').onclick = () => (painelAtual === 'camadas' ? fecharPainel() : painelCamadas());
  $('#btn-medir').onclick = () => (medindo ? (pararMedida(), fecharPainel()) : iniciarMedida());
  $('#btn-enquadrar').onclick = () => visor.enquadrar('iso');
  $('#btn-arestas').onclick = () => { const b = $('#btn-arestas'); b.classList.toggle('ligado'); visor.ligarArestas(b.classList.contains('ligado')); };
  document.querySelectorAll('[data-vista]').forEach(b => b.onclick = () => visor.enquadrar(b.dataset.vista));
  $('#pintar').onchange = () => {
    const modo = $('#pintar').value;
    legenda = visor.pintarPor(modo);
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

abrir().catch(e => {
  console.error(e);
  const c = $('#carregando');
  if (c) c.innerHTML = `<div><b>Não foi possível abrir o modo ver.</b><div style="margin:8px 0">${esc(e.message || e)}</div>
    <button class="botao" onclick="window.visorLeve.editar()">Abrir no editor</button></div>`;
});
