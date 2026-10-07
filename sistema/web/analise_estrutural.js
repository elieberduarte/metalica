// A tela da análise estrutural (/analise-estrutural?projeto=…): o unifilar do modelo com os apoios, as cargas de cada
// caso, os diagramas de esforços, o mapa de tensões, a deformada e as reações — o resultado de
// nucleo3d/analise_estrutural.py (GET/POST /api/projetos/<s>/analise-estrutural). Pedido do usuário, 06/10/2026: "um
// unifilar para ver como as cargas atuam na estrutura… os mapas de esforços, onde estão as maiores tensões".
//
// O servidor manda, por barra e por caso, as forças na ponta a (eixos locais) e a carga distribuída local: o diagrama
// de qualquer combinação sai aqui por superposição (o mesmo esforcos_em do Python).

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { guia } from '/analise_guia.js';
import { LineSegments2 } from 'three/addons/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/addons/LineMaterial.js';

const $ = (s, r = document) => r.querySelector(s);
const PROJETO = new URLSearchParams(location.search).get('projeto') || '';
const API = `/api/projetos/${encodeURIComponent(PROJETO)}/analise-estrutural`;
const nf = (v, c = 1) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const escuro = () => document.documentElement.getAttribute('data-tema') === 'escuro' ||
  (!document.documentElement.getAttribute('data-tema') && matchMedia('(prefers-color-scheme: dark)').matches);

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

// ------------------------------------------------------------------ estado
let D = null;                  // o resultado da situação à vista
let RAIZ = null;               // o resultado do servidor (com a cobertura retrátil, a aberta + outras_situacoes)
let estado = { modo: 'tensoes', caso: null, comb: 'env', esforco: 'Mz', escala: 1, escolhida: null, situacao: 'aberta', guia: true };
try { Object.assign(estado, JSON.parse(localStorage.getItem('ae.estado') || '{}'), { escolhida: null }); } catch (e) { /* */ }
const guardar = () => { try { localStorage.setItem('ae.estado', JSON.stringify({ ...estado, escolhida: null })); } catch (e) { /* */ } };

const PAPEL_COR = { pilar: '#6b7c93', viga: '#3b6fb6', banzo: '#c46a1b', montante: '#2f9e6a', diagonal: '#2f9e6a', terça: '#8e7cc3', contraventamento: '#b0476b' };
const ROTULO_PAPEL = { pilar: 'pilar', viga: 'viga', banzo_sup: 'banzo superior', banzo_inf: 'banzo inferior', montante: 'montante', diagonal: 'diagonal', terça: 'terça', contraventamento: 'contraventamento', banzo: 'banzo' };
const ESFORCOS = { N: ['N — normal (kN)', 0, 'ey'], Vy: ['Vy — cortante no plano forte (kN)', 1, 'ey'], Vz: ['Vz — cortante no plano fraco (kN)', 2, 'ez'],
                   T: ['T — torção (kN·m)', 3, 'ey'], Mz: ['Mz — momento no eixo forte (kN·m)', 5, 'ey'], My: ['My — momento no eixo fraco (kN·m)', 4, 'ez'] };

// ------------------------------------------------------------------ a cena
const tela = $('#tela');
const renderer = new THREE.WebGLRenderer({ canvas: tela, antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
const cena = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 50, 2e6);
camera.up.set(0, 0, 1);
const controles = new OrbitControls(camera, tela);
controles.enableDamping = false;
const grupo = new THREE.Group();
cena.add(grupo);
let centro = new THREE.Vector3(), raio = 10000;

function corFundo() { return escuro() ? 0x0e131a : 0xf4f6fa; }
function pedir() { requestAnimationFrame(desenharQuadro); }
let pedido = false;
function desenharQuadro() { pedido = false; renderer.render(cena, camera); }
function pedirQuadro() { if (!pedido) { pedido = true; requestAnimationFrame(desenharQuadro); } }
controles.addEventListener('change', pedirQuadro);
function redimensionar() {
  const r = tela.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / Math.max(1, r.height);
  camera.updateProjectionMatrix();
  for (const m of materiaisLinha) m.resolution.set(r.width, r.height);
  pedirQuadro();
}
const materiaisLinha = [];
window.addEventListener('resize', redimensionar);

function vista(v) {
  const dir = { iso: [1, -1.3, 0.8], frente: [0, -1, 0.05], lado: [1, 0, 0.05], topo: [0, -0.001, 1] }[v] || [1, -1, 1];
  const d = new THREE.Vector3(...dir).normalize();
  camera.position.copy(centro).addScaledVector(d, raio * 2.4);
  controles.target.copy(centro);
  camera.near = raio / 200; camera.far = raio * 50; camera.updateProjectionMatrix();
  controles.update();
  pedirQuadro();
}
document.querySelectorAll('[data-vista]').forEach(b => b.addEventListener('click', () => vista(b.dataset.vista)));

// ------------------------------------------------------------------ cálculo dos esforços ao longo da barra
function fatoresDe(comb) {
  const casos = Object.keys(D.casos);
  const f = new Array(casos.length).fill(0);
  if (comb && D.combinacoes[comb]) for (const [c, v] of Object.entries(D.combinacoes[comb].fatores)) { const k = casos.indexOf(c); if (k >= 0) f[k] = v; }
  return f;
}
function esforcosEm(i, fat, x) {
  const P = D.pontas[i], W = D.w_local[i];
  const f = [0, 0, 0, 0, 0, 0], w = [0, 0, 0];
  fat.forEach((a, c) => { if (!a) return; for (let k = 0; k < 6; k++) f[k] += a * P[c][k]; for (let k = 0; k < 3; k++) w[k] += a * W[c][k]; });
  const [Fx, Fy, Fz, Mx, My, Mz] = f, [wx, wy, wz] = w;
  return [-(Fx + wx * x), -(Fy + wy * x), -(Fz + wz * x), -Mx, -(My + x * Fz + wz * x * x / 2), -(Mz - x * Fy - wy * x * x / 2)];
}
const ESTACOES = 11;

// ------------------------------------------------------------------ cores
function rampa(t) {           // 0 → verde, 0,7 → amarelo, 1 → laranja, >1 → vermelho
  const pts = [[0, [46, 160, 90]], [0.5, [120, 190, 60]], [0.75, [235, 200, 40]], [1.0, [240, 120, 30]], [1.3, [200, 30, 40]]];
  t = Math.max(0, Math.min(1.3, t));
  for (let k = 0; k < pts.length - 1; k++) {
    const [a, ca] = pts[k], [b, cb] = pts[k + 1];
    if (t <= b) { const u = (t - a) / (b - a); return ca.map((v, j) => Math.round(v + (cb[j] - v) * u)); }
  }
  return pts[pts.length - 1][1];
}
function rampaSinal(t) {      // −1 azul (compressão) … 0 cinza … +1 vermelho (tração)
  t = Math.max(-1, Math.min(1, t));
  const z = escuro() ? [120, 130, 145] : [150, 158, 170];
  return t >= 0 ? z.map((v, j) => Math.round(v + ([210, 45, 45][j] - v) * t)) : z.map((v, j) => Math.round(v + ([35, 95, 210][j] - v) * -t));
}
const hex = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;

// ------------------------------------------------------------------ desenhar
const texto = (t, cor = '#1c2430') => {
  const c = document.createElement('canvas'), g = c.getContext('2d');
  g.font = 'bold 34px Segoe UI, Arial'; const w = Math.ceil(g.measureText(t).width) + 18;
  c.width = w; c.height = 48;
  const g2 = c.getContext('2d');
  g2.fillStyle = escuro() ? 'rgba(21,28,38,0.88)' : 'rgba(255,255,255,0.88)'; g2.fillRect(0, 0, w, 48);
  g2.font = 'bold 34px Segoe UI, Arial'; g2.fillStyle = cor; g2.textBaseline = 'middle'; g2.fillText(t, 9, 25);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, sizeAttenuation: false, transparent: true }));
  s.scale.set(0.017 * w / 48, 0.017, 1); s.renderOrder = 20; s.center.set(0, 0.5);
  return s;
};

function linhas(pos, cores, largura = 2, tracejado = false) {
  const g = new LineSegmentsGeometry();
  g.setPositions(pos); g.setColors(cores);
  const m = new LineMaterial({ linewidth: largura, vertexColors: true, dashed: tracejado, dashSize: 300, gapSize: 200 });
  const r = tela.parentElement.getBoundingClientRect(); m.resolution.set(r.width, r.height);
  materiaisLinha.push(m);
  const l = new LineSegments2(g, m);
  if (tracejado) l.computeLineDistances();
  return l;
}
function limpar() {
  for (const o of [...grupo.children]) { grupo.remove(o); o.traverse(x => { if (x.geometry) x.geometry.dispose(); if (x.material) { if (x.material.map) x.material.map.dispose(); x.material.dispose(); } }); }
  materiaisLinha.length = 0;
}

function valorDaBarra(i) {
  // o que pinta a barra no modo atual
  if (estado.modo === 'tensoes') {
    const fy = D.parametros.fy_mpa || 345;
    if (estado.comb === 'env') return D.envoltoria[i].sigma / fy;
    return (D.por_comb[estado.comb] ? D.por_comb[estado.comb].barras[i][4] : 0) / fy;
  }
  return null;
}

// o quadro "Como ler" (web/analise_guia.js): acompanha o modo, a combinação e o caso
function painelGuia() {
  const g = $('#guia');
  g.hidden = !estado.guia;
  $('#btn-guia').classList.toggle('on', !!estado.guia);
  if (estado.guia) g.innerHTML = guia(D, RAIZ, estado);
}
$('#btn-guia').addEventListener('click', () => { estado.guia = !estado.guia; guardar(); painelGuia(); });

function desenhar() {
  painelGuia();
  limpar();
  if (!D || D.vazio) { pedirQuadro(); return; }
  cena.background = new THREE.Color(corFundo());
  const nos = D.nos, B = D.barras;
  const modo = estado.modo;
  const pos = [], cor = [], posH = [], corH = [];
  const cinza = escuro() ? [95, 108, 125] : [175, 183, 195];
  const fat = (modo === 'esforcos' || modo === 'deformada' || modo === 'reacoes') ? fatoresDe(estado.comb === 'env' ? primeiraELU() : estado.comb) : null;
  // a cor de cada barra
  let maxN = 1e-9;
  if (modo === 'esforcos' && estado.esforco === 'N') B.forEach((b, i) => { const e0 = esforcosEm(i, fat, 0)[0]; maxN = Math.max(maxN, Math.abs(e0)); });
  B.forEach((b, i) => {
    const a = nos[b.a], c = nos[b.b];
    let rgb;
    const v = valorDaBarra(i);
    if (v !== null) rgb = rampa(v);
    else if (modo === 'esforcos' && estado.esforco === 'N') rgb = rampaSinal(esforcosEm(i, fat, 0)[0] / maxN);
    else if (modo === 'modelo') rgb = hexParaRgb(PAPEL_COR[b.papel] || '#888');
    else rgb = cinza;
    if (estado.escolhida === i) rgb = [255, 0, 200];
    const alvo = b.hipotese ? [posH, corH] : [pos, cor];
    alvo[0].push(...a, ...c);
    alvo[1].push(...rgb.map(x => x / 255), ...rgb.map(x => x / 255));
  });
  grupo.add(linhas(pos, cor, modo === 'modelo' || modo === 'tensoes' ? 3 : 2));
  if (posH.length) grupo.add(linhas(posH, corH.map(x => x * 0.85), 1.5, true));
  apoios();
  if (modo === 'cargas') setasCargas();
  if (modo === 'esforcos') diagramas(fat);
  if (modo === 'deformada') deformada();
  if (modo === 'reacoes') setasReacoes();
  legenda(maxN);
  pedirQuadro();
}
function hexParaRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function primeiraELU() { return Object.keys(D.combinacoes).find(c => D.combinacoes[c].tipo === 'ELU'); }

function apoios() {
  const t = raio * 0.012;
  for (const ap of D.apoios) {
    const p = D.nos[ap.no];
    let m;
    if (ap.tipo === 'engastada') {
      m = new THREE.Mesh(new THREE.BoxGeometry(t * 2.2, t * 2.2, t * 0.8), new THREE.MeshBasicMaterial({ color: 0x7a5230 }));
      m.position.set(p[0], p[1], p[2] - t * 0.4);
    } else {
      m = new THREE.Mesh(new THREE.ConeGeometry(t, t * 1.6, 16), new THREE.MeshBasicMaterial({ color: 0x7a5230 }));
      m.rotation.x = Math.PI / 2; m.position.set(p[0], p[1], p[2] - t * 0.8);
    }
    grupo.add(m);
  }
}

function seta(origem, vetor, comp, corHex, rotulo) {
  const dir = new THREE.Vector3(...vetor).normalize();
  const a = new THREE.ArrowHelper(dir, new THREE.Vector3(...origem).addScaledVector(dir, -comp), comp, corHex, comp * 0.25, comp * 0.12);
  a.line.material.depthTest = false; a.cone.material.depthTest = false; a.renderOrder = 15;
  grupo.add(a);
  if (rotulo) { const s = texto(rotulo, '#' + corHex.toString(16).padStart(6, '0')); s.position.set(...new THREE.Vector3(...origem).addScaledVector(dir, -comp * 1.1).toArray()); grupo.add(s); }
}

function setasCargas() {
  const caso = D.casos[estado.caso] || D.casos[Object.keys(D.casos)[0]];
  if (!caso) return;
  const porNo = new Map();
  for (const [i, F] of Object.entries(caso.nodal)) {
    const b = D.barras[+i];
    for (const n of [b.a, b.b]) { const v = porNo.get(n) || [0, 0, 0]; porNo.set(n, [v[0] + F[0], v[1] + F[1], v[2] + F[2]]); }
  }
  for (const [n, F] of Object.entries(caso.nos || {})) { const v = porNo.get(+n) || [0, 0, 0]; porNo.set(+n, [v[0] + F[0], v[1] + F[1], v[2] + F[2]]); }
  let max = 1e-9;
  for (const v of porNo.values()) max = Math.max(max, Math.hypot(...v));
  const L = raio * 0.08 * estado.escala;
  for (const [n, v] of porNo) {
    const m = Math.hypot(...v);
    if (m < max * 0.02) continue;
    seta(D.nos[n], v, L * (0.35 + 0.65 * m / max), 0xd0452f, null);
  }
  // o peso próprio é distribuído nas barras: setinhas no meio de cada barra
  if (Object.keys(caso.dist).length) {
    for (const [i, w] of Object.entries(caso.dist)) {
      const b = D.barras[+i]; if (b.hipotese) continue;
      const a = D.nos[b.a], c = D.nos[b.b];
      seta([(a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2], w, L * 0.25, 0x8a6d3b, null);
    }
  }
}

function diagramas(fat) {
  const idx = ESFORCOS[estado.esforco][1], eixo = ESFORCOS[estado.esforco][2];
  // a escala: o maior valor vira 6% do tamanho do modelo
  let max = 1e-9;
  const vals = D.barras.map((b, i) => {
    if (b.hipotese) return null;
    const v = []; for (let k = 0; k < ESTACOES; k++) v.push(esforcosEm(i, fat, b.L * k / (ESTACOES - 1))[idx]);
    for (const x of v) max = Math.max(max, Math.abs(x));
    return v;
  });
  const esc = raio * 0.06 * estado.escala / max;
  const pos = [], cor = [];
  D.barras.forEach((b, i) => {
    const v = vals[i]; if (!v) return;
    const a = new THREE.Vector3(...D.nos[b.a]), c = new THREE.Vector3(...D.nos[b.b]);
    const d = new THREE.Vector3(...(eixo === 'ey' ? b.ey : b.ez));
    let ant = null;
    for (let k = 0; k < ESTACOES; k++) {
      const p = a.clone().lerp(c, k / (ESTACOES - 1));
      const q = p.clone().addScaledVector(d, v[k] * esc);
      const rgb = v[k] >= 0 ? [210, 60, 50] : [40, 100, 210];
      pos.push(p.x, p.y, p.z, q.x, q.y, q.z); cor.push(...rgb.map(x => x / 255), ...rgb.map(x => x / 255));
      if (ant) { pos.push(ant.x, ant.y, ant.z, q.x, q.y, q.z); cor.push(...rgb.map(x => x / 255), ...rgb.map(x => x / 255)); }
      ant = q;
    }
  });
  grupo.add(linhas(pos, cor, 1.4));
  // rótulo nos picos mais altos
  const picos = vals.map((v, i) => v ? [Math.max(...v.map(Math.abs)), i] : [0, i]).sort((x, y) => y[0] - x[0]).slice(0, 6);
  const un = idx >= 3 ? ' kN·m' : ' kN';
  for (const [m, i] of picos) {
    if (m <= 0) continue;
    const b = D.barras[i], v = vals[i];
    const k = v.map(Math.abs).indexOf(m);
    const p = new THREE.Vector3(...D.nos[b.a]).lerp(new THREE.Vector3(...D.nos[b.b]), k / (ESTACOES - 1)).addScaledVector(new THREE.Vector3(...(eixo === 'ey' ? b.ey : b.ez)), v[k] * esc);
    const s = texto(nf(v[k], idx >= 3 ? 2 : 1) + un, v[k] >= 0 ? '#c0392b' : '#1f5fbf'); s.position.copy(p); grupo.add(s);
  }
}

function deformada() {
  const comb = estado.comb === 'env' ? Object.keys(D.combinacoes).find(c => D.combinacoes[c].tipo === 'ELS') || primeiraELU() : estado.comb;
  const U = D.por_comb[comb].desl_mm;
  let max = 1e-9; for (const u of U) max = Math.max(max, Math.hypot(...u));
  const esc = raio * 0.05 * estado.escala / max;
  const pos = [], cor = [];
  for (const b of D.barras) {
    const a = D.nos[b.a].map((v, k) => v + U[b.a][k] * esc), c = D.nos[b.b].map((v, k) => v + U[b.b][k] * esc);
    pos.push(...a, ...c); cor.push(0.85, 0.2, 0.55, 0.85, 0.2, 0.55);
  }
  grupo.add(linhas(pos, cor, 2));
  let k = 0, km = 0; U.forEach((u, i) => { const m = Math.hypot(...u); if (m > km) { km = m; k = i; } });
  const s = texto(`máx. ${nf(km, 1)} mm (${comb})`, '#b0336f'); s.position.set(...D.nos[k].map((v, j) => v + U[k][j] * esc)); grupo.add(s);
}

function setasReacoes() {
  const comb = estado.comb === 'env' ? primeiraELU() : estado.comb;
  const R = D.por_comb[comb].reacoes;
  let max = 1e-9; for (const r of Object.values(R)) max = Math.max(max, Math.hypot(r[0], r[1], r[2]));
  const L = raio * 0.1 * estado.escala;
  for (const ap of D.apoios) {
    const r = R[String(ap.no)]; if (!r) continue;
    const p = D.nos[ap.no];
    if (Math.abs(r[2]) > max * 0.01) seta([p[0], p[1], p[2]], [0, 0, Math.sign(r[2])], L * (0.3 + 0.7 * Math.abs(r[2]) / max), r[2] >= 0 ? 0x2a7d46 : 0xc0392b,
      `${nf(r[2], 1)} kN${Math.abs(r[3]) + Math.abs(r[4]) > 0.05 ? ` · M ${nf(Math.hypot(r[3], r[4]), 1)} kN·m` : ''}`);
    const h = Math.hypot(r[0], r[1]);
    if (h > max * 0.01) seta([p[0], p[1], p[2]], [r[0], r[1], 0], L * (0.3 + 0.7 * h / max), 0x8e44ad, null);
  }
}

function legenda(maxN) {
  const L = $('#legenda');
  const m = estado.modo;
  if (m === 'tensoes') {
    const fy = D.parametros.fy_mpa || 345;
    const grad = Array.from({ length: 14 }, (_, k) => hex(rampa(k / 10))).join(',');
    L.innerHTML = `<b>Tensão / fy</b> (fy = ${nf(fy, 0)} MPa)<div class="rampa" style="background:linear-gradient(90deg,${grad})"></div><div class="ext"><span>0</span><span>50%</span><span>100%</span><span>130%</span></div>
      <div class="sub">σ = |N|/A + |Mz|/Wz + |My|/Wy, ${estado.comb === 'env' ? 'envoltória ELU' : estado.comb}</div>`;
    L.hidden = false;
  } else if (m === 'esforcos' && estado.esforco === 'N') {
    L.innerHTML = `<b>Normal</b><div class="rampa" style="background:linear-gradient(90deg,rgb(35,95,210),rgb(150,158,170),rgb(210,45,45))"></div><div class="ext"><span>compressão</span><span>tração</span></div><div class="sub">até ${nf(maxN, 1)} kN</div>`;
    L.hidden = false;
  } else if (m === 'modelo') {
    L.innerHTML = '<b>Funções</b><br>' + Object.entries(PAPEL_COR).map(([p, c]) => `<span class="chip" style="background:${c};color:#fff">${p}</span>`).join(' ') + '<div class="sub">tracejado: barras de hipótese (só na análise)</div>';
    L.hidden = false;
  } else L.hidden = true;
}

// ------------------------------------------------------------------ escolher uma barra (clique)
tela.addEventListener('pointerdown', (ev) => { tela._xy = [ev.clientX, ev.clientY]; });
tela.addEventListener('pointerup', (ev) => {
  if (!D || !tela._xy || Math.hypot(ev.clientX - tela._xy[0], ev.clientY - tela._xy[1]) > 4) return;
  const r = tela.getBoundingClientRect();
  const px = [ev.clientX - r.left, ev.clientY - r.top];
  const proj = (p) => { const v = new THREE.Vector3(...p).project(camera); return [(v.x + 1) / 2 * r.width, (1 - v.y) / 2 * r.height, v.z]; };
  let melhor = null, dm = 8;
  D.barras.forEach((b, i) => {
    const a = proj(D.nos[b.a]), c = proj(D.nos[b.b]);
    if (a[2] > 1 || c[2] > 1) return;
    const dx = c[0] - a[0], dy = c[1] - a[1], L2 = dx * dx + dy * dy;
    const t = L2 ? Math.max(0, Math.min(1, ((px[0] - a[0]) * dx + (px[1] - a[1]) * dy) / L2)) : 0;
    const d = Math.hypot(px[0] - a[0] - dx * t, px[1] - a[1] - dy * t);
    if (d < dm) { dm = d; melhor = i; }
  });
  estado.escolhida = melhor;
  painelPeca();
  desenhar();
});

function painelPeca() {
  const det = $('#det-peca'), P = $('#peca');
  const i = estado.escolhida;
  if (i === null || i === undefined) { det.hidden = true; return; }
  det.hidden = false;
  const b = D.barras[i], e = D.envoltoria[i];
  const comb = estado.comb === 'env' ? (e.comb || primeiraELU()) : estado.comb;
  const fat = fatoresDe(comb);
  const xs = Array.from({ length: 21 }, (_, k) => b.L * k / 20);
  const val = xs.map(x => esforcosEm(i, fat, x));
  const fy = D.parametros.fy_mpa || 345;
  const svg = (k, nome, un) => {
    const v = val.map(r => r[k]); const m = Math.max(1e-9, ...v.map(Math.abs));
    const W = 300, H = 90, y0 = H / 2;
    const pts = v.map((y, j) => `${(j / 20) * (W - 20) + 10},${y0 - (y / m) * (H / 2 - 12)}`).join(' ');
    const ext = v.reduce((a, y, j) => Math.abs(y) > Math.abs(v[a]) ? j : a, 0);
    return `<svg class="diag" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="10" y1="${y0}" x2="${W - 10}" y2="${y0}" stroke="currentColor" stroke-opacity=".35"/>
      <polyline points="10,${y0} ${pts} ${W - 10},${y0}" fill="${v[ext] >= 0 ? 'rgba(210,60,50,.18)' : 'rgba(40,100,210,.18)'}" stroke="${v[ext] >= 0 ? '#c0392b' : '#1f5fbf'}" stroke-width="1.5"/>
      <text x="12" y="13" font-size="11" fill="currentColor">${nome}: ${nf(v[0], 2)} … ${nf(v[20], 2)} · pico ${nf(v[ext], 2)} ${un}</text></svg>`;
  };
  P.innerHTML = `<div class="peca"><b>${ROTULO_PAPEL[b.papel_trelica || b.papel] || b.papel}</b> ${b.marca ? `· ${b.marca}` : ''} · ${b.perfil}${b.hipotese ? ' · <i>barra de hipótese</i>' : ''}<br>
    L = ${nf(b.L, 3)} m · rótulas: ${b.rotulas.length ? b.rotulas.join(', ') : 'nenhuma'}<br>
    Envoltória ELU: σ = <b>${nf(e.sigma, 0)} MPa</b> (${nf(e.taxa * 100, 0)}% de fy ${nf(fy, 0)}) em ${e.comb || '—'} · N ${nf(e.N[0], 1)} / ${nf(e.N[1], 1)} kN · M ${nf(e.M, 2)} kN·m</div>
    <div class="sub" style="margin-top:4px">Diagramas na combinação <b>${comb}</b>:</div>
    ${svg(0, 'N', 'kN')}${svg(5, 'Mz', 'kN·m')}${svg(4, 'My', 'kN·m')}${svg(1, 'Vy', 'kN')}`;
}

// ------------------------------------------------------------------ painéis
const PREMISSAS = [
  ['base', 'Bases dos pilares', 'sel', [['engastada', 'engastadas'], ['articulada', 'articuladas']]],
  ['viga_pilar', 'Ligação viga–pilar', 'sel', [['rigida', 'rígida'], ['rotulada', 'rotulada']]],
  ['tesoura_rotulada_no_apoio', 'Tesoura no apoio', 'sel', [['true', 'rotulada'], ['false', 'contínua']]],
  ['rotula_alma', 'Almas das treliças', 'sel', [['no_plano', 'rotuladas no plano'], ['total', 'rotuladas nas duas direções']]],
  ['telha', 'Telha + terças (kN/m²)', 'num'],
  ['carga_extra', 'Permanente extra (kN/m²)', 'num'],
  ['sobrecarga', 'Sobrecarga (kN/m²)', 'num'],
  ['vento', 'Vento', 'sel', [['true', 'sim'], ['false', 'não']]],
  ['v0', 'V0 (m/s)', 'num'],
  ['categoria', 'Categoria do terreno', 'sel', [['I', 'I'], ['II', 'II'], ['III', 'III'], ['IV', 'IV'], ['V', 'V']]],
  ['s1', 'S1 (topográfico)', 'num'],
  ['s3', 'S3 (estatístico)', 'num'],
  ['travamento_hipotese', 'Terças e contravento de hipótese', 'sel', [['auto', 'só sem terças no modelo'], ['sim', 'sempre'], ['nao', 'não']]],
  ['cobertura_movel', 'Cobertura retrátil', 'sel', [['false', 'não'], ['true', 'sim (aberta e retraída)']]],
  ['movel_n', '  nº de tesouras', 'num'],
  ['movel_comprimento_aberta', '  comprimento aberta (m)', 'num'],
  ['movel_comprimento_retraida', '  comprimento retraída (m)', 'num'],
  ['movel_lado_retraida', '  pilha na ponta', 'sel', [['y_menor', 'de baixo na planta (Y menor)'], ['y_maior', 'de cima na planta (Y maior)']]],
  ['movel_peso_total_kg', '  peso total do fabricante (kg)', 'num'],
  ['perfil_sanfona', '  braço da sanfona (perfil)', 'txt'],
  ['fy_mpa', 'fy para o mapa (MPa)', 'num'],
];
function montarPremissas(par) {
  const box = $('#premissas'); box.replaceChildren();
  for (const [k, rot, tipo, ops] of PREMISSAS) {
    let inp;
    const v = par[k];
    if (tipo === 'sel') inp = el('select', { 'data-k': k }, ...ops.map(([val, t]) => el('option', { value: val, texto: t, selected: String(v) === val ? 'selected' : undefined })));
    else if (tipo === 'txt') inp = el('input', { 'data-k': k, 'data-txt': '1', type: 'text', value: v || '' });
    else inp = el('input', { 'data-k': k, type: 'text', value: v === null || v === undefined ? '' : String(v).replace('.', ',') });
    box.append(el('label', { class: 'linha' }, rot, inp));
  }
  box.append(el('div', { class: 'sub', style: 'margin-top:6px', texto: 'As premissas ficam gravadas no projeto. Calcular de novo aplica as mudanças.' }));
}
function lerPremissas() {
  const p = {};
  for (const inp of document.querySelectorAll('#premissas [data-k]')) {
    const k = inp.dataset.k, v = inp.value;
    if (v === 'true' || v === 'false') p[k] = v === 'true';
    else if (inp.tagName === 'INPUT' && inp.dataset.txt) p[k] = v.trim();
    else if (inp.tagName === 'INPUT') { const n = parseFloat(v.replace(',', '.')); if (isFinite(n)) p[k] = n; }
    else p[k] = v;
  }
  return p;
}

function montarControles() {
  const C = $('#controles'); C.replaceChildren();
  for (const b of document.querySelectorAll('#modos button')) b.classList.toggle('on', b.dataset.modo === estado.modo);
  if (!D || D.vazio) return;
  const combs = Object.keys(D.combinacoes);
  const selComb = (incluiEnv) => {
    const s = el('select', {}, ...(incluiEnv ? [el('option', { value: 'env', texto: 'Envoltória ELU', selected: estado.comb === 'env' ? 'selected' : undefined })] : []),
      ...combs.map(c => el('option', { value: c, texto: `${c} — ${D.combinacoes[c].descricao}`, selected: estado.comb === c ? 'selected' : undefined })));
    s.onchange = () => { estado.comb = s.value; guardar(); desenhar(); painelReacoes(); painelPeca(); };
    return s;
  };
  const linha = (rot, inp) => C.append(el('label', { class: 'linha', style: 'grid-template-columns:110px 1fr' }, rot, inp));
  const m = estado.modo;
  if (RAIZ && RAIZ.outras_situacoes) {
    const sits = ['aberta', ...Object.keys(RAIZ.outras_situacoes)];
    const ss = el('select', {}, ...sits.map(x => el('option', { value: x, texto: x === 'aberta' ? 'cobertura aberta' : x === 'retraida' ? 'cobertura retraída' : x, selected: estado.situacao === x ? 'selected' : undefined })));
    ss.onchange = () => { estado.situacao = ss.value; guardar(); trocarSituacao(); };
    linha('Situação', ss);
  }
  if (m === 'cargas') {
    const casos = Object.keys(D.casos);
    if (!casos.includes(estado.caso)) estado.caso = casos[0];
    const s = el('select', {}, ...casos.map(c => el('option', { value: c, texto: `${c} — ${D.casos[c].descricao}`, selected: estado.caso === c ? 'selected' : undefined })));
    s.onchange = () => { estado.caso = s.value; guardar(); desenhar(); };
    linha('Caso', s);
  }
  if (m === 'esforcos') {
    if (estado.comb === 'env') estado.comb = primeiraELU();
    linha('Combinação', selComb(false));
    const s = el('select', {}, ...Object.entries(ESFORCOS).map(([k, [t]]) => el('option', { value: k, texto: t, selected: estado.esforco === k ? 'selected' : undefined })));
    s.onchange = () => { estado.esforco = s.value; guardar(); desenhar(); };
    linha('Esforço', s);
  }
  if (m === 'tensoes') linha('Combinação', selComb(true));
  if (m === 'deformada' || m === 'reacoes') linha('Combinação', selComb(false));
  if (['cargas', 'esforcos', 'deformada', 'reacoes'].includes(m)) {
    const r = el('input', { type: 'range', min: '0.2', max: '4', step: '0.1', value: String(estado.escala) });
    r.oninput = () => { estado.escala = +r.value; guardar(); desenhar(); };
    linha('Escala', r);
  }
}
document.querySelectorAll('#modos button').forEach(b => b.addEventListener('click', () => { estado.modo = b.dataset.modo; guardar(); montarControles(); desenhar(); }));

function painelRanking() {
  const R = $('#ranking');
  const fy = D.parametros.fy_mpa || 345;
  const ord = D.envoltoria.map((e, i) => [e.sigma, i]).filter(([s, i]) => !D.barras[i].hipotese).sort((a, b) => b[0] - a[0]).slice(0, 15);
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'barra' }), el('th', { texto: 'perfil' }), el('th', { texto: 'σ MPa' }), el('th', { texto: '% fy' }), el('th', { texto: 'comb.' })));
  for (const [s, i] of ord) {
    const b = D.barras[i];
    const tr = el('tr', { class: 'clic', onclick: () => { estado.escolhida = i; painelPeca(); desenhar(); focar(i); } },
      el('td', { texto: ROTULO_PAPEL[b.papel_trelica || b.papel] || b.papel }), el('td', { texto: b.perfil }), el('td', { texto: nf(s, 0) }),
      el('td', { html: `<span style="color:${hex(rampa(s / fy))};font-weight:700">${nf(s / fy * 100, 0)}%</span>` }), el('td', { texto: D.envoltoria[i].comb || '' }));
    t.append(tr);
  }
  // o pior por grupo (função + perfil)
  const grupos = new Map();
  D.barras.forEach((b, i) => { if (b.hipotese) return; const k = `${ROTULO_PAPEL[b.papel_trelica || b.papel] || b.papel} · ${b.perfil}`; grupos.set(k, Math.max(grupos.get(k) || 0, D.envoltoria[i].sigma)); });
  const tg = el('table', { style: 'margin-top:8px' }, el('tr', {}, el('th', { texto: 'grupo' }), el('th', { texto: 'pior σ' }), el('th', { texto: '% fy' })));
  for (const [k, s] of [...grupos].sort((a, b) => b[1] - a[1])) tg.append(el('tr', {}, el('td', { texto: k }), el('td', { texto: nf(s, 0) }), el('td', { html: `<span style="color:${hex(rampa(s / fy))};font-weight:700">${nf(s / fy * 100, 0)}%</span>` })));
  R.replaceChildren(t, el('div', { class: 'sub', style: 'margin-top:6px', texto: 'Por grupo (função · perfil):' }), tg,
    el('div', { class: 'sub', style: 'margin-top:4px', texto: 'Tensão elástica combinada (mapa). A verificação da NBR 8800 — flambagem, flexo-compressão — vem na etapa do dimensionamento.' }));
}

function focar(i) {
  const b = D.barras[i];
  const p = new THREE.Vector3(...D.nos[b.a]).lerp(new THREE.Vector3(...D.nos[b.b]), 0.5);
  const d = camera.position.clone().sub(controles.target);
  controles.target.copy(p); camera.position.copy(p).add(d.multiplyScalar(0.35));
  controles.update(); pedirQuadro();
}

function painelReacoes() {
  const R = $('#reacoes');
  if (RAIZ && RAIZ.reacoes_envoltoria) {
    const t = el('table', {}, el('tr', {}, el('th', { texto: 'base (x, y m)' }), el('th', { texto: 'Fz máx' }), el('th', { texto: 'Fz mín' }), el('th', { texto: 'H máx' }), el('th', { texto: 'M máx' })));
    for (const e of RAIZ.reacoes_envoltoria) {
      const [x, y] = e.chave.split(',').map(v => (+v / 1000).toFixed(2));
      t.append(el('tr', { title: `Fz máx: ${e.Fz_max[1]}\nFz mín: ${e.Fz_min[1]}\nH máx: ${e.H_max[1]}\nM máx: ${e.M_max[1]}` },
        el('td', { texto: `${x}, ${y} ${e.tipo === 'engastada' ? '▪' : '▲'}` }), el('td', { texto: nf(e.Fz_max[0], 1) }),
        el('td', { html: e.Fz_min[0] < 0 ? `<b style="color:#c0392b">${nf(e.Fz_min[0], 1)}</b>` : nf(e.Fz_min[0], 1) }),
        el('td', { texto: nf(e.H_max[0], 1) }), el('td', { texto: nf(e.M_max[0], 1) })));
    }
    R.replaceChildren(el('div', { class: 'sub', texto: `Envoltória das combinações últimas${RAIZ.outras_situacoes ? ' nas duas situações (aberta e retraída)' : ''} — kN e kN·m. Fz positivo comprime a base; negativo (vermelho) arranca: é o que o chumbador recebe. Passe o mouse para ver a combinação de cada máximo.` }), t);
    return;
  }
  const comb = estado.comb === 'env' ? primeiraELU() : estado.comb;
  const elus = Object.keys(D.combinacoes).filter(c => D.combinacoes[c].tipo === 'ELU');
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'apoio (x,y m)' }), el('th', { texto: 'Fz máx' }), el('th', { texto: 'Fz mín' }), el('th', { texto: 'H máx' }), el('th', { texto: 'M máx' })));
  for (const ap of D.apoios) {
    const n = String(ap.no);
    const rs = elus.map(c => [c, D.por_comb[c].reacoes[n]]);
    const fzmax = rs.reduce((a, r) => (r[1][2] > a[1][2] ? r : a)), fzmin = rs.reduce((a, r) => (r[1][2] < a[1][2] ? r : a));
    const hmax = rs.reduce((a, r) => (Math.hypot(r[1][0], r[1][1]) > Math.hypot(a[1][0], a[1][1]) ? r : a));
    const mmax = rs.reduce((a, r) => (Math.hypot(r[1][3], r[1][4]) > Math.hypot(a[1][3], a[1][4]) ? r : a));
    const [x, y] = ap.chave.split(',').map(v => (+v / 1000).toFixed(2));
    t.append(el('tr', { title: `Fz máx em ${fzmax[0]} · Fz mín em ${fzmin[0]} · H em ${hmax[0]} · M em ${mmax[0]}` },
      el('td', { texto: `${x}, ${y} ${ap.tipo === 'engastada' ? '▪' : '▲'}` }), el('td', { texto: nf(fzmax[1][2], 1) }),
      el('td', { html: fzmin[1][2] < 0 ? `<b style="color:#c0392b">${nf(fzmin[1][2], 1)}</b>` : nf(fzmin[1][2], 1) }),
      el('td', { texto: nf(Math.hypot(hmax[1][0], hmax[1][1]), 1) }), el('td', { texto: nf(Math.hypot(mmax[1][3], mmax[1][4]), 1) })));
  }
  R.replaceChildren(el('div', { class: 'sub', texto: 'Envoltória das combinações últimas (kN, kN·m). Fz positivo comprime a base; negativo (em vermelho) arranca: é o que o chumbador recebe.' }), t);
}

function painelVento() {
  const V = $('#vento'), i = D.info || {};
  const v = i.vento, c = i.cobertura;
  const linhas = [];
  const mv = D.movel;
  if (mv) linhas.push(`<b>Cobertura retrátil — ${mv.configuracao === 'aberta' ? 'aberta' : 'retraída'}</b>: ${mv.n} tesouras a cada ${nf(mv.passo_m, 3)} m em ${nf(mv.comprimento_m, 2)} m; ${nf(mv.peso_tesoura_kg, 1)} kg cada (peso do fabricante ÷ ${mv.n}); sanfona com ${mv.sanfona_barras} braços; abas laterais de ${nf(mv.altura_aba_m, 2)} m (NBR 6123, 7.2.5.1: 1,3·q·A a barlavento, 0,6·q·A a sotavento).`);
  if (c) linhas.push(`Cobertura: ${nf(c.area_m2, 1)} m² em ${c.trelicas} tesouras; larguras de influência ${c.larguras_m.map(x => nf(x, 2)).join(' · ')} m.`);
  if (v) {
    linhas.push(`Vk = ${nf(v.Vk, 1)} m/s (S2 = ${nf(v.S2, 3)}, classe ${v.classe}, z = ${nf(v.z, 1)} m) · q = <b>${nf(v.q_kN_m2, 3)} kN/m²</b>`);
    linhas.push(`Cobertura isolada a duas águas (NBR 6123:2023, 7.2, Tabela 25): vão ${nf(v.vao, 1)} m, flecha ${nf(v.flecha, 2)} m → tg θ = ${nf(v.tg, 3)}; altura livre ${nf(v.h_livre, 2)} m.`);
    linhas.push(`Carregamento 1: cpb = ${nf(v.carregamento_1.cpb, 3)}, cps = ${nf(v.carregamento_1.cps, 3)} · Carregamento 2: cpb = ${nf(v.carregamento_2.cpb, 3)}, cps = ${nf(v.carregamento_2.cps, 3)} (positivo empurra para baixo).`);
    linhas.push(`Atrito ao longo da geratriz (7.2.2): ${nf(v.atrito_kN, 1)} kN.`);
  }
  linhas.push('Casos: ' + Object.entries(D.casos).map(([k, c]) => `<span class="chip">${k}</span>${c.descricao}`).join('<br>'));
  V.innerHTML = linhas.map(l => `<div style="margin:4px 0">${l}</div>`).join('');
}

function painelEquilibrio() {
  const E = $('#equilibrio');
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'caso' }), el('th', { texto: 'ΣFz cargas' }), el('th', { texto: 'ΣFz reações' }), el('th', { texto: 'ΣFx/ΣFy' })));
  for (const [c, e] of Object.entries(D.equilibrio)) t.append(el('tr', {}, el('td', { texto: c }), el('td', { texto: nf(e.cargas_kN[2], 2) }), el('td', { texto: nf(e.reacoes_kN[2], 2) }),
    el('td', { texto: `${nf(e.cargas_kN[0] + e.reacoes_kN[0], 2)} / ${nf(e.cargas_kN[1] + e.reacoes_kN[1], 2)}` })));
  E.replaceChildren(el('div', { class: 'sub', texto: 'A soma das reações deve fechar com a soma das cargas em cada caso (última coluna ≈ 0).' }), t);
}

function painelAvisos() {
  const A = $('#avisos');
  A.replaceChildren(...(D.avisos || []).map(a => el('div', { class: 'aviso', texto: a })));
  $('#instavel').replaceChildren(D.instavel ? el('div', { class: 'erro', texto: `Estrutura instável: ${D.instavel}. Veja os avisos.` }) : '');
}

function cabecalho() {
  $('#cab').textContent = D ? `${D.projeto || PROJETO}${D.local ? ' · ' + D.local : ''}` : PROJETO;
  $('#estado').textContent = D && !D.vazio ? `Calculado em ${D.calculado_em} (${nf(D.segundos, 1)} s) · ${D.barras.length} barras, ${D.nos.length} nós, ${D.apoios.length} apoios · ${Object.keys(D.casos).length} casos, ${Object.keys(D.combinacoes).length} combinações` : (D && D.vazio) || '';
  $('#btn-modelo3d').href = `/editor?projeto=${encodeURIComponent(PROJETO)}`;
}

// Voltar: a tela de onde veio (a área 2D + 3D, pelo menu Modelo); aberta direto, a área de trabalho do projeto
$('#btn-voltar').addEventListener('click', () => {
  let daqui = false;
  try { daqui = !!document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) { /* */ }
  if (daqui && history.length > 1) history.back();
  else location.href = `/dividida?projeto=${encodeURIComponent(PROJETO)}`;
});

function trocarSituacao() {
  D = (estado.situacao !== 'aberta' && RAIZ.outras_situacoes && RAIZ.outras_situacoes[estado.situacao]) || RAIZ;
  if (!D.combinacoes[estado.comb] && estado.comb !== 'env') estado.comb = 'env';
  estado.escolhida = null;
  montarControles(); painelRanking(); painelVento(); painelEquilibrio(); painelAvisos(); painelPeca();
  desenhar();
}

function aplicar(dados) {
  RAIZ = dados;
  if (!dados.outras_situacoes) estado.situacao = 'aberta';
  D = (estado.situacao !== 'aberta' && dados.outras_situacoes && dados.outras_situacoes[estado.situacao]) || dados;
  cabecalho();
  montarPremissas(RAIZ.parametros || {});
  if (D.vazio) {
    $('#vazio').hidden = false; $('#vazio').innerHTML = `<div><b>${D.vazio}</b><br>Confira as premissas e clique em <b>Calcular</b>.</div>`;
    $('#det-premissas').open = true;
    montarControles(); desenhar(); return;
  }
  $('#vazio').hidden = true;
  // o centro e o tamanho do modelo
  const bb = new THREE.Box3(); for (const p of D.nos) bb.expandByPoint(new THREE.Vector3(...p));
  bb.getCenter(centro); raio = Math.max(1000, bb.getSize(new THREE.Vector3()).length() / 2);
  montarControles(); painelRanking(); painelReacoes(); painelVento(); painelEquilibrio(); painelAvisos(); painelPeca();
  if (!aplicar._vista) { vista('iso'); aplicar._vista = true; }
  desenhar();
}

async function carregar() {
  const r = await fetch(API, { cache: 'no-store' });
  aplicar(await r.json());
}

$('#btn-calcular').addEventListener('click', async () => {
  $('#carregando').style.display = 'flex';
  try {
    const r = await fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ parametros: lerPremissas() }) });
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    aplicar(j);
  } catch (e) { alert('Não foi possível calcular: ' + e.message); }
  $('#carregando').style.display = 'none';
});

redimensionar();
carregar().catch(e => { $('#vazio').hidden = false; $('#vazio').textContent = 'Não foi possível abrir: ' + e.message; });
window.ae = { get D() { return D; }, estado, desenhar, camera };
