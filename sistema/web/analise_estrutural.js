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
// nas combinações últimas com a 2ª ordem (D.pontas2[comb]) as forças da ponta vêm prontas — o P-Δ não se superpõe;
// a carga distribuída continua a soma dos casos
function esforcosEm(i, fat, x, comb) {
  const P2 = comb && D.pontas2 && D.pontas2[comb] ? D.pontas2[comb][i] : null;
  const P = D.pontas[i], W = D.w_local[i];
  const f = P2 ? P2.slice(0, 6) : [0, 0, 0, 0, 0, 0], w = [0, 0, 0];
  fat.forEach((a, c) => { if (!a) return; if (!P2) for (let k = 0; k < 6; k++) f[k] += a * P[c][k]; for (let k = 0; k < 3; k++) w[k] += a * W[c][k]; });
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
    const pc = D.por_comb[estado.comb];
    return (pc ? (pc.sigma ? pc.sigma[i] : pc.barras[i][4]) : 0) / fy;
  }
  if (estado.modo === 'verificacao') {
    const V = D.verificacao;
    if (!V) return 0;
    if (estado.comb === 'env' || !V.uso_barras[estado.comb]) return V.uso_env[i];
    return V.uso_barras[estado.comb][i];
  }
  return null;
}
// a combinação dos desenhos: a escolhida, ou na envoltória a primeira ELU
function combDoDesenho() { return estado.comb === 'env' ? primeiraELU() : estado.comb; }

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
  const cinza = escuro() ? [95, 108, 125] : [48, 55, 66];      // no claro, mais escuro: a estrutura sumia no fundo (07/10)
  const cd = combDoDesenho();
  const fat = (modo === 'esforcos' || modo === 'deformada' || modo === 'reacoes') ? fatoresDe(cd) : null;
  // a cor de cada barra
  let maxN = 1e-9;
  if (modo === 'esforcos' && estado.esforco === 'N') B.forEach((b, i) => { const e0 = esforcosEm(i, fat, 0, cd)[0]; maxN = Math.max(maxN, Math.abs(e0)); });
  B.forEach((b, i) => {
    const a = nos[b.a], c = nos[b.b];
    let rgb;
    const v = valorDaBarra(i);
    if (v !== null) rgb = rampa(v);
    else if (modo === 'esforcos' && estado.esforco === 'N') rgb = rampaSinal(esforcosEm(i, fat, 0, cd)[0] / maxN);
    else if (modo === 'modelo') rgb = hexParaRgb(PAPEL_COR[b.papel] || '#888');
    else rgb = cinza;
    if (estado.escolhida === i) rgb = [255, 0, 200];
    const alvo = b.hipotese ? [posH, corH] : [pos, cor];
    alvo[0].push(...a, ...c);
    alvo[1].push(...rgb.map(x => x / 255), ...rgb.map(x => x / 255));
  });
  grupo.add(linhas(pos, cor, modo === 'modelo' || modo === 'tensoes' || modo === 'verificacao' ? 3 : 2));
  if (posH.length) grupo.add(linhas(posH, corH.map(x => x * 0.85), 1.5, true));
  apoios();
  secoesDosPilares();
  if (modo === 'cargas') setasCargas();
  if (modo === 'esforcos') diagramas(fat, cd);
  if (modo === 'deformada') deformada();
  if (modo === 'reacoes') setasReacoes();
  legenda(maxN);
  pedirQuadro();
}
// a seção de cada pilar desenhada na base, na orientação que o cálculo usa (o giro da peça no 3D): mostra para que lado
// está a alma — a inércia forte resiste às forças na direção da alma. Amarelo; laranja = girado só na análise
function secoesDosPilares() {
  const baixo = new Map();
  D.barras.forEach(b => {
    if (b.papel !== 'pilar' || !b.secao || !b.pilar) return;
    const n = D.nos[b.a][2] <= D.nos[b.b][2] ? b.a : b.b;
    const at = baixo.get(b.pilar);
    if (!at || D.nos[n][2] < D.nos[at.n][2]) baixo.set(b.pilar, { b, n });
  });
  const pos = [], cor = [];
  for (const { b, n } of baixo.values()) {
    const o = D.nos[n], u = b.ez.map(v => -v), v = b.ey;
    const P = b.secao.map(([x, y]) => [o[0] + x * u[0] + y * v[0], o[1] + x * u[1] + y * v[1], o[2] + x * u[2] + y * v[2] + 30]);
    const c = b.giro ? [240, 140, 20] : [245, 197, 24];
    for (let k = 0; k < P.length; k++) {
      const p = P[k], q = P[(k + 1) % P.length];
      pos.push(...p, ...q); cor.push(...c.map(x => x / 255), ...c.map(x => x / 255));
    }
  }
  if (pos.length) { const l = linhas(pos, cor, 2.5); l.renderOrder = 18; l.material.depthTest = false; grupo.add(l); }
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

function diagramas(fat, comb) {
  const idx = ESFORCOS[estado.esforco][1], eixo = ESFORCOS[estado.esforco][2];
  // a escala: o maior valor vira 6% do tamanho do modelo
  let max = 1e-9;
  const vals = D.barras.map((b, i) => {
    if (b.hipotese) return null;
    const v = []; for (let k = 0; k < ESTACOES; k++) v.push(esforcosEm(i, fat, b.L * k / (ESTACOES - 1), comb)[idx]);
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
  const cd = escuro() ? [0.96, 0.45, 0.71] : [0.62, 0.04, 0.38];   // no claro, magenta escuro (o rosa sumia no fundo, 07/10)
  for (const b of D.barras) {
    const a = D.nos[b.a].map((v, k) => v + U[b.a][k] * esc), c = D.nos[b.b].map((v, k) => v + U[b.b][k] * esc);
    pos.push(...a, ...c); cor.push(...cd, ...cd);
  }
  grupo.add(linhas(pos, cor, escuro() ? 2.2 : 2.8));
  let k = 0, km = 0; U.forEach((u, i) => { const m = Math.hypot(...u); if (m > km) { km = m; k = i; } });
  const s = texto(`máx. ${nf(km, 1)} mm (${comb})`, escuro() ? '#f472b6' : '#9d1260'); s.position.set(...D.nos[k].map((v, j) => v + U[k][j] * esc)); grupo.add(s);
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
  } else if (m === 'verificacao') {
    const grad = Array.from({ length: 14 }, (_, k) => hex(rampa(k / 10))).join(',');
    const V = D.verificacao;
    L.innerHTML = `<b>Uso da resistência de cálculo</b><div class="rampa" style="background:linear-gradient(90deg,${grad})"></div><div class="ext"><span>0</span><span>50%</span><span>100%</span><span>130%</span></div>
      <div class="sub">${V ? `NBR 8800 / NBR 14762, ${estado.comb === 'env' ? 'envoltória ELU' : estado.comb}${V.primeira_ordem ? ' — esforços de 1ª ordem' : ' — esforços de 2ª ordem'}` : 'calcule de novo para verificar as peças'}</div>`;
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
  const V = D.verificacao, pc = V ? V.pecas[V.peca_da_barra[i]] : null;
  const combEnv = estado.modo === 'verificacao' && pc && pc.comb ? pc.comb : e.comb;
  const comb = estado.comb === 'env' ? (combEnv || primeiraELU()) : estado.comb;
  const fat = fatoresDe(comb);
  const xs = Array.from({ length: 21 }, (_, k) => b.L * k / 20);
  const val = xs.map(x => esforcosEm(i, fat, x, comb));
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
    <div class="sub" style="margin-top:4px">Diagramas na combinação <b>${comb}</b>${D.pontas2 && D.pontas2[comb] ? ' (2ª ordem)' : ''}:</div>
    ${svg(0, 'N', 'kN')}${svg(5, 'Mz', 'kN·m')}${svg(4, 'My', 'kN·m')}${svg(1, 'Vy', 'kN')}`;
  if (pc) P.prepend(blocoDaVerificacao(pc, V));
  if (b.papel === 'pilar' && b.pilar) P.prepend(blocoDoPilar(b));
}

// a verificação da peça pela norma (nucleo3d/verificacao_pecas.py): o uso, o que governa, os comprimentos de flambagem,
// as resistências de cálculo, os esforços no ponto que governa com o B1 e a conta da interação
const VERIF_CURTO = { 'flambagem (N ≥ Ne)': 'flambagem', 'tração (barra redonda)': 'tração', 'não verificada': '—' };
const pctUso = (u) => (u === null || u === undefined) ? '—' : u >= 9.99 ? 'instável' : `${nf(u * 100, 0)}%`;
const corUso = (u) => (u === null || u === undefined) ? 'inherit' : hex(rampa(Math.min(u, 1.3)));
function blocoDaVerificacao(pc, V) {
  const R = V.resistencias[pc.res] || {};
  const box = el('div', { class: 'verif' });
  const titulo = `${ROTULO_PAPEL[pc.papel] || pc.papel}${pc.marca ? ' · ' + pc.marca : ''} · ${pc.perfil} · ${pc.aco}${R.fy ? ` (fy ${nf(R.fy, 0)} MPa)` : ''}`;
  if (pc.uso === null || pc.uso === undefined) {
    box.innerHTML = `<b>Verificação da peça</b> — ${titulo}<div class="erro">${(pc.obs || []).join(' · ') || 'não verificada'}</div>`;
    return box;
  }
  const u = pc.uso, ok = u <= 1;
  const linhas = [];
  linhas.push(`<div class="vcab"><div class="uso-grande${u >= 9.99 ? ' menor' : ''}" style="color:${corUso(u)}">${pctUso(u)}</div><div><b>Verificação da peça</b> (${R.norma || 'NBR 8800'})<br>${titulo}<br>
    <span class="sub">governa: <b>${pc.verif}</b>${pc.comb ? ` em ${pc.comb}` : ''}${pc.x !== undefined ? `, a ${nf(pc.x * 100, 0)}% da barra` : ''}${V.primeira_ordem ? ' · esforços de 1ª ordem' : ' · esforços de 2ª ordem'}</span></div></div>`);
  const tab = [];
  tab.push(`<tr><td>Peça</td><td>L = ${nf(pc.L, 2)} m (${pc.nb} trecho${pc.nb > 1 ? 's' : ''})</td></tr>`);
  tab.push(`<tr><td>Flambagem</td><td>${pc.K ? 'K·' : ''}Lx = <b>${nf(pc.Lx, 2)} m</b> (eixo forte) · ${pc.K ? 'K·' : ''}Ly = <b>${nf(pc.Ly, 2)} m</b> (eixo fraco; Lb da FLT) · K = ${pc.K ? nf(pc.K, 2) + ' (NBR 16239, 4.8)' : '1'}</td></tr>`);
  tab.push(`<tr><td>Travamentos</td><td>${pc.travamentos[0]} na altura · ${pc.travamentos[1]} na largura, ao longo da peça</td></tr>`);
  if (pc.lam_lim) tab.push(`<tr><td>Esbeltez</td><td>λ = ${nf(pc.lam, 0)} (limite ${nf(pc.lam_lim, 0)}${pc.lam_lim === 200 ? ', comprimida' : ', só tracionada'}) ${pc.lam > pc.lam_lim ? ' — <span class="g-ruim">acima do limite</span>' : ' — ok'}</td></tr>`);
  const rd = [];
  if (R.Nc) rd.push(`N<sub>c,Rd</sub> = <b>${nf(R.Nc, 1)} kN</b>${R.chi !== undefined && R.chi !== null ? ` (χ ${nf(R.chi, 3)}, Q ${nf(R.Q, 3)}, λ₀ ${nf(R.lambda0, 2)})` : ''}`);
  if (R.Nt) rd.push(`N<sub>t,Rd</sub> = <b>${nf(R.Nt, 1)} kN</b>`);
  if (R.Mz) rd.push(`M<sub>z,Rd</sub> = <b>${nf(R.Mz, 2)} kN·m</b>${R.gov_Mz ? ` (${R.gov_Mz.replace('Flexão — ', '')})` : ''}`);
  if (R.My) rd.push(`M<sub>y,Rd</sub> = <b>${nf(R.My, 2)} kN·m</b>${R.gov_My ? ` (${R.gov_My.replace('Flexão — ', '')})` : ''}`);
  if (R.Vy) rd.push(`V<sub>y,Rd</sub> = ${nf(R.Vy, 1)} · V<sub>z,Rd</sub> = ${nf(R.Vz, 1)} kN`);
  tab.push(`<tr><td>Resistências</td><td>${rd.join('<br>')}</td></tr>`);
  if (pc.esf) {
    const s = pc.esf;
    tab.push(`<tr><td>Solicitantes</td><td>N = ${nf(s.N, 1)} kN · M<sub>z</sub> = ${nf(s.Mz, 2)} · M<sub>y</sub> = ${nf(s.My, 2)} kN·m · V = ${nf(Math.hypot(s.Vy, s.Vz), 1)} kN</td></tr>`);
    const b1 = (v) => v >= 99 ? '∞ (N ≥ Ne)' : nf(v, 3);
    if (pc.B1) tab.push(`<tr><td>P-δ (B1)</td><td>B1 = ${b1(pc.B1[0])} (z) · ${b1(pc.B1[1])} (y); C<sub>m</sub> ${nf(pc.Cm[0], 2)} · ${nf(pc.Cm[1], 2)}; N<sub>e</sub> ${nf(pc.Ne[0], 0)} · ${nf(pc.Ne[1], 0)} kN</td></tr>`);
    const p = pc.partes || {};
    let conta = '';
    if (R.redonda) conta = `N/N<sub>t,Rd</sub> = ${nf(p.N, 3)}`;
    else if (R.linear) conta = `N/N<sub>Rd</sub> + B1·M<sub>z</sub>/M<sub>z,Rd</sub> + B1·M<sub>y</sub>/M<sub>y,Rd</sub> = ${nf(p.N, 3)} + ${nf(p.Mz, 3)} + ${nf(p.My, 3)} (NBR 14762, 9.8.2.4)`;
    else if (p.N >= 0.2) conta = `N/N<sub>Rd</sub> + 8/9·(B1·M<sub>z</sub>/M<sub>z,Rd</sub> + B1·M<sub>y</sub>/M<sub>y,Rd</sub>) = ${nf(p.N, 3)} + 8/9·(${nf(p.Mz, 3)} + ${nf(p.My, 3)}) (5.5.1.2, eq. a)`;
    else conta = `N/(2·N<sub>Rd</sub>) + B1·M<sub>z</sub>/M<sub>z,Rd</sub> + B1·M<sub>y</sub>/M<sub>y,Rd</sub> = ${nf(p.N, 3)}/2 + ${nf(p.Mz, 3)} + ${nf(p.My, 3)} (5.5.1.2, eq. b)`;
    tab.push(`<tr><td>Interação</td><td>${conta}${p.V ? `<br>cortante: ${nf(p.V, 3)}` : ''}</td></tr>`);
  }
  linhas.push(`<table class="vt">${tab.join('')}</table>`);
  if ((pc.obs || []).length) linhas.push(`<div class="${ok ? 'sub' : 'aviso'}" style="margin-top:4px">${pc.obs.join('<br>')}</div>`);
  if ((R.obs || []).length) linhas.push(`<div class="sub" style="margin-top:3px">${R.obs.join(' · ')}</div>`);
  box.innerHTML = linhas.join('');
  return box;
}

// o pilar escolhido: para que lado está a inércia forte e o giro de teste (só na análise)
function blocoDoPilar(b) {
  const dir = Math.abs(b.ey[0]) >= Math.abs(b.ey[1]) ? 'X' : 'Y';
  const outra = dir === 'X' ? 'Y' : 'X';
  const giros = () => ({ ...((RAIZ && RAIZ.parametros && RAIZ.parametros.giro_pilares) || {}) });
  const atual = Number(giros()[b.pilar] || 0);
  const novo = (atual + 90) % 180;
  const girar = (chaves) => { const g = giros(); for (const k of chaves) { if (novo) g[k] = novo; else delete g[k]; } calcular({ giro_pilares: g }); };
  const mesmos = [...new Set(D.barras.filter(x => x.papel === 'pilar' && x.pilar && (x.perfil_original || x.perfil) === (b.perfil_original || b.perfil)).map(x => x.pilar))];
  return el('div', { class: 'aviso', style: 'margin-bottom:6px' },
    el('div', { html: `<b>Inércia forte (a alma) na direção ${dir}</b>: o pilar resiste melhor às forças em ${dir} (o pórtico nessa direção); em ${outra} trabalha pelo eixo fraco. A seção está desenhada em amarelo na base.${atual ? ` <b>Girado ${atual}° só na análise.</b>` : ''}` }),
    el('div', { style: 'display:flex;gap:6px;margin-top:5px;flex-wrap:wrap' },
      el('button', { type: 'button', class: 'sec mini', texto: atual ? 'Voltar ao giro do modelo' : 'Girar 90° (só na análise)', onclick: () => girar([b.pilar]) }),
      mesmos.length > 1 ? el('button', { type: 'button', class: 'sec mini', texto: `${atual ? 'Voltar' : 'Girar'} os ${mesmos.length} pilares ${b.perfil_original || b.perfil}`, onclick: () => girar(mesmos) }) : ''),
    el('div', { class: 'sub', style: 'margin-top:4px', texto: 'O giro aqui é um teste: o definitivo é girar o pilar na planta (o 3D e a análise acompanham).' }));
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
  ['segunda_ordem', '2ª ordem nas ELU', 'sel', [['true', 'sim (P-Δ, NBR 8800:2024 4.10.7)'], ['false', 'não (só 1ª ordem)']]],
  ['aco_tubos', 'Aço dos tubos (verificação)', 'sel', [['', 'o de cada peça no modelo'], ['ASTM A572 Gr.50', 'ASTM A572 Gr.50 (fy 345)'],
    ['ASTM A500 Gr.B', 'ASTM A500 Gr.B (fy 315)'], ['ASTM A500 Gr.C', 'ASTM A500 Gr.C (fy 345)'], ['VMB 250', 'VMB 250 (fy 250)'],
    ['VMB 300', 'VMB 300 (fy 300)'], ['VMB 350', 'VMB 350 (fy 350)'], ['ASTM A36', 'ASTM A36 (fy 250)']]],
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
  const todas = Object.keys(D.combinacoes);
  const selComb = (incluiEnv, soELU = false) => {
    const combs = soELU ? todas.filter(c => D.combinacoes[c].tipo === 'ELU') : todas;
    if (soELU && estado.comb !== 'env' && !combs.includes(estado.comb)) estado.comb = 'env';
    const s2 = (c) => (D.segunda_ordem && D.segunda_ordem.combinacoes[c]) || null;
    const marca = (c) => { const r = s2(c); return r ? (r.instavel ? ' ⚠ instável na 2ª ordem' : r.razao ? ` · Δ2/Δ1 ${nf(r.razao, 2)}` : '') : ''; };
    const s = el('select', {}, ...(incluiEnv ? [el('option', { value: 'env', texto: 'Envoltória ELU', selected: estado.comb === 'env' ? 'selected' : undefined })] : []),
      ...combs.map(c => el('option', { value: c, texto: `${c} — ${D.combinacoes[c].descricao}${marca(c)}`, selected: estado.comb === c ? 'selected' : undefined })));
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
  if (m === 'verificacao') linha('Combinação', selComb(true, true));
  if (m === 'deformada' || m === 'reacoes') linha('Combinação', selComb(false));
  if (['cargas', 'esforcos', 'deformada', 'reacoes'].includes(m)) {
    const r = el('input', { type: 'range', min: '0.2', max: '4', step: '0.1', value: String(estado.escala) });
    r.oninput = () => { estado.escala = +r.value; guardar(); desenhar(); };
    linha('Escala', r);
  }
}
document.querySelectorAll('#modos button').forEach(b => b.addEventListener('click', () => { estado.modo = b.dataset.modo; guardar(); montarControles(); desenhar(); }));

// ------------------------------------------------------------------ troca de perfil (só na análise)
function chaveDoGrupo(b) { return `${b.papel_trelica || b.papel}|${b.perfil_original || b.perfil}`; }
function trocasAtuais() { return { ...((RAIZ && RAIZ.parametros && RAIZ.parametros.trocas_perfil) || {}) }; }
function editarTroca(chave, linha, g) {
  const ja = linha.nextSibling && linha.nextSibling.classList && linha.nextSibling.classList.contains('troca');
  document.querySelectorAll('#ranking tr.troca').forEach(x => x.remove());
  if (ja) return;
  const info = ((RAIZ && RAIZ.grupos_perfis) || []).find(x => x.chave === chave) || {};
  const alts = info.alternativas || [];
  const leve = info.mais_leve_que_passa;
  const inp = el('input', { type: 'text', value: leve || g.atual, placeholder: 'ou digite outro perfil do catálogo', style: 'width:100%;box-sizing:border-box;margin-top:4px' });
  const pct = (u) => (u === null || u === undefined) ? '—' : u >= 9.99 ? 'instável' : `${nf(u * 100, 0)}%`;
  const cor = (u, s) => (u !== null && u !== undefined) ? (u <= 1 ? '#1e8e4e' : '#c0392b') : (s <= (D.parametros.fy_mpa || 345) ? '#9a6b06' : '#c0392b');
  const tab = el('table', { class: 'alts' }, el('tr', {}, el('th', { texto: 'perfil' }), el('th', { texto: 'kg/m' }), el('th', { texto: 'σ est.' }), el('th', { texto: 'uso est.' }), el('th', { texto: '' })));
  const linhas = [];
  for (const [nome, kg, sg, uso] of alts) {
    const passa = uso !== null && uso !== undefined && uso <= 1;
    const tr = el('tr', { class: 'clic' + (nome === leve ? ' leve' : ''), title: nome === leve ? 'o mais leve que passa na estimativa' : '' },
      el('td', { html: nome === leve ? `<b>${nome}</b> <span class="g-ok">← mais leve que passa</span>` : nome }), el('td', { texto: nf(kg, 1) }),
      el('td', { texto: nf(sg, 0) }), el('td', { html: `<span style="color:${cor(uso, sg)};font-weight:700">${pct(uso)}</span>` }),
      el('td', { html: passa ? '<span class="g-ok">✓</span>' : '<span class="g-ruim">✗</span>' }));
    tr.onclick = () => { inp.value = nome; linhas.forEach(x => x.classList.remove('sel')); tr.classList.add('sel'); };
    if (nome === (leve || g.atual)) tr.classList.add('sel');
    linhas.push(tr); tab.append(tr);
  }
  const ir = () => {
    const v = inp.value.trim(); if (!v) return;
    const t2 = trocasAtuais();
    if (v === g.original) delete t2[chave]; else t2[chave] = v;
    calcular({ trocas_perfil: t2 });
  };
  const voltar = () => { const t2 = trocasAtuais(); delete t2[chave]; calcular({ trocas_perfil: t2 }); };
  const ea = info.estimativa_atual;
  const explica = `Novo perfil para ${ROTULO_PAPEL[g.funcao] || g.funcao} · ${g.original} (${info.barras || ''} barras)${ea ? ` — hoje: σ ${nf(ea[0], 0)} MPa, uso estimado ${pct(ea[1])}` : ''}.`;
  const nota = 'Estimativa com os esforços atuais do grupo (nas duas situações) e as MESMAS resistências da verificação: os comprimentos de flambagem de cada peça pelos travamentos, compressão com χ e Q, flexão com FLA, FLM e FLT, formados a frio pela NBR 14762. Ao trocar, os esforços se redistribuem e o B1 muda — o recalcular confirma. Só tubos com parede ≥ 1,5 mm na lista (digitar aceita qualquer um).';
  const gv = D.verificacao ? gruposDaVerificacao().find(x => x.chave === chave) : null;
  const travar = gv && gv.pc ? (gv.pc.obs || []).filter(o => o.startsWith('nenhuma barra trava')) : [];
  const linhaT = el('tr', { class: 'troca' }, el('td', { colspan: '4' },
    el('div', { class: 'sub', texto: explica }),
    travar.length ? el('div', { class: 'aviso', texto: travar[0] + ' — trocar o perfil não resolve bem: o mais leve que passa precisa vencer esse comprimento sozinho.' }) : '',
    alts.length ? el('div', { class: 'lista-alts' }, tab) : el('div', { class: 'sub', texto: 'Sem alternativas calculadas: clique em Calcular uma vez e abra de novo (ou digite o perfil).' }),
    inp,
    el('div', { style: 'display:flex;gap:6px;margin-top:4px;flex-wrap:wrap' },
      el('button', { type: 'button', class: 'prim', texto: 'Trocar e recalcular', onclick: ir }),
      g.atual !== g.original ? el('button', { type: 'button', class: 'sec', texto: `Voltar ao ${g.original}`, onclick: voltar }) : '',
      el('button', { type: 'button', class: 'sec', texto: 'Cancelar', onclick: () => linhaT.remove() })),
    el('div', { class: 'sub', style: 'margin-top:4px', texto: nota })));
  inp.addEventListener('keydown', ev => { if (ev.key === 'Enter') ir(); if (ev.key === 'Escape') linhaT.remove(); });
  linha.after(linhaT);
  const sel = linhaT.querySelector('tr.sel'); if (sel) sel.scrollIntoView({ block: 'nearest' });
}

// o grupo (função + perfil original) na pior das situações (a cobertura retrátil calcula aberta e retraída)
function gruposDaVerificacao() {
  const sits = [['aberta', RAIZ], ...Object.entries((RAIZ && RAIZ.outras_situacoes) || {})];
  const m = new Map();
  for (const [sit, R] of sits) {
    const V = R && R.verificacao; if (!V) continue;
    for (const g of V.grupos || []) {
      const at = m.get(g.chave);
      const pc = g.peca !== null && g.peca !== undefined ? V.pecas[g.peca] : null;
      if (!at || g.uso > at.uso) m.set(g.chave, { ...g, sit, pc, nao: Math.max(g.nao_passam, at ? at.nao : 0), total: g.pecas });
      else at.nao = Math.max(at.nao, g.nao_passam);
    }
  }
  return [...m.values()].sort((a, b) => b.uso - a.uso);
}

function painelRanking() {
  const R = $('#ranking');
  if (D.verificacao) return painelRankingVerificacao(R);
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
  // o pior por grupo (função + perfil original): a troca de perfil é por grupo
  const grupos = new Map();
  D.barras.forEach((b, i) => {
    if (b.hipotese) return;
    const k = chaveDoGrupo(b);
    const g = grupos.get(k) || { s: 0, atual: b.perfil, original: b.perfil_original || b.perfil, funcao: b.papel_trelica || b.papel };
    g.s = Math.max(g.s, D.envoltoria[i].sigma); grupos.set(k, g);
  });
  const tg = el('table', { style: 'margin-top:8px' }, el('tr', {}, el('th', { texto: 'grupo' }), el('th', { texto: 'pior σ' }), el('th', { texto: '% fy' }), el('th', { texto: '' })));
  for (const [k, g] of [...grupos].sort((a, b) => b[1].s - a[1].s)) {
    const nome = ROTULO_PAPEL[g.funcao] || g.funcao;
    const perfil = g.atual !== g.original ? `<s style="opacity:.6">${g.original}</s> → <b>${g.atual}</b>` : g.original;
    const tr = el('tr', {}, el('td', { html: `${nome} · ${perfil}` }), el('td', { texto: nf(g.s, 0) }),
      el('td', { html: `<span style="color:${hex(rampa(g.s / fy))};font-weight:700">${nf(g.s / fy * 100, 0)}%</span>` }),
      el('td', {}, el('button', { type: 'button', class: 'sec mini', title: 'Trocar o perfil deste grupo e recalcular (só na análise: o 3D não muda)', texto: 'trocar', onclick: () => editarTroca(k, tr, g) })));
    tg.append(tr);
  }
  R.replaceChildren(t, el('div', { class: 'sub', style: 'margin-top:6px', texto: 'Por grupo (função · perfil) — "trocar" muda o perfil do grupo e recalcula:' }), tg, caixaDasTrocas(),
    el('div', { class: 'sub', style: 'margin-top:4px', texto: 'Tensão elástica combinada (mapa). Calcule de novo para ter a verificação de cada peça pela norma.' }));
}

function caixaDasTrocas() {
  const trocas = Object.entries(trocasAtuais());
  return trocas.length ? el('div', { class: 'aviso', style: 'margin-top:6px' },
    el('b', { texto: 'Perfis trocados só na análise' }), el('span', { texto: ' (o modelo 3D não muda):' }),
    ...trocas.map(([k, novo]) => {
      const [f, p0] = k.split('|');
      return el('div', {}, `${ROTULO_PAPEL[f] || f}: ${p0} → ${novo} `,
        el('button', { type: 'button', class: 'sec mini', texto: 'desfazer', onclick: () => { const t2 = trocasAtuais(); delete t2[k]; calcular({ trocas_perfil: t2 }); } }));
    })) : '';
}

// o ranking pela verificação da norma: as peças de maior uso e o pior de cada grupo (a troca de perfil é por grupo)
function painelRankingVerificacao(R) {
  const V = D.verificacao;
  const escolher = (pc) => { const i = pc.barra !== undefined ? pc.barra : pc.b0; estado.escolhida = i; painelPeca(); desenhar(); focar(i); };
  const porGrupo = new Map();
  const ord = V.pecas.filter(p => !p.hipotese && p.uso !== null && p.uso !== undefined).sort((a, b) => b.uso - a.uso).filter(p => {
    const k = chaveDoGrupo(D.barras[p.b0]); const n = (porGrupo.get(k) || 0) + 1; porGrupo.set(k, n); return n <= 3;
  }).slice(0, 15);
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'peça' }), el('th', { texto: 'perfil' }), el('th', { texto: 'uso' }), el('th', { texto: 'governa' })));
  for (const pc of ord) {
    t.append(el('tr', { class: 'clic', title: `${pc.verif} em ${pc.comb || '—'}${(pc.obs || []).length ? '\n' + pc.obs.join('\n') : ''}`, onclick: () => escolher(pc) },
      el('td', { texto: `${ROTULO_PAPEL[pc.papel] || pc.papel}${pc.marca ? ' ' + pc.marca : ''}` }), el('td', { texto: pc.perfil }),
      el('td', { html: `<span style="color:${corUso(pc.uso)};font-weight:700">${pctUso(pc.uso)}</span>` }),
      el('td', { texto: VERIF_CURTO[pc.verif] || pc.verif })));
  }
  const nv = V.pecas.filter(p => p.uso === null || p.uso === undefined).length;
  const sits = RAIZ.outras_situacoes ? ' (a pior das duas situações)' : '';
  const tg = el('table', { style: 'margin-top:8px' }, el('tr', {}, el('th', { texto: 'grupo' }), el('th', { texto: 'pior uso' }), el('th', { texto: 'acima de 100%' }), el('th', { texto: '' })));
  for (const g of gruposDaVerificacao()) {
    const [funcao, original] = g.chave.split('|');
    const atual = (g.pc && g.pc.perfil) || original;
    const perfil = atual !== original ? `<s style="opacity:.6">${original}</s> → <b>${atual}</b>` : original;
    const gg = { atual, original, funcao };
    const tr = el('tr', { title: g.pc ? `pior peça: ${g.pc.verif} em ${g.pc.comb || '—'}${g.sit !== 'aberta' ? ' (retraída)' : ''}\n${(g.pc.obs || []).join('\n')}` : '' },
      el('td', { html: `${ROTULO_PAPEL[funcao] || funcao} · ${perfil}` }),
      el('td', { html: `<span style="color:${corUso(g.uso)};font-weight:700">${pctUso(g.uso)}</span>${RAIZ.outras_situacoes && g.sit !== 'aberta' ? ' <span class="sub">ret.</span>' : ''}` }),
      el('td', { html: g.nao ? `<span class="g-ruim">${g.nao}</span> de ${g.total}` : `0 de ${g.total}` }),
      el('td', {}, el('button', { type: 'button', class: 'sec mini', title: 'Trocar o perfil deste grupo e recalcular (só na análise: o 3D não muda)', texto: 'trocar', onclick: () => editarTroca(g.chave, tr, gg) })));
    tg.append(tr);
  }
  R.replaceChildren(
    el('div', { class: 'sub', texto: `As peças de maior uso da resistência de cálculo (100% = o limite da norma)${V.primeira_ordem ? ' — esforços de 1ª ordem' : ', com os esforços de 2ª ordem'}; até 3 por grupo — passe o mouse para ver a combinação:` }), t,
    el('div', { class: 'sub', style: 'margin-top:6px', texto: `Por grupo (função · perfil)${sits} — "trocar" muda o perfil do grupo e recalcula:` }), tg, caixaDasTrocas(),
    V.instaveis && V.instaveis.length ? el('div', { class: 'erro', texto: `Fora da verificação (instáveis na 2ª ordem): ${V.instaveis.join(', ')}` }) : '',
    nv ? el('div', { class: 'aviso', texto: `${nv} peça(s) não verificada(s): perfil fora do que a norma cobre aqui (veja o detalhe da peça).` }) : '',
    el('div', { class: 'sub', style: 'margin-top:4px', texto: 'Uso = a pior verificação de cada peça: a interação N + M (NBR 8800 5.5.1.2; linear nos formados a frio, NBR 14762), o cortante e a esbeltez. Compressão com χ e Q; flexão com FLA, FLM e FLT; comprimentos de flambagem pelos travamentos que chegam na peça (K = 1, com a 2ª ordem global); B1 para o P-δ. Clique numa peça para ver a conta.' }));
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

// as bases dos pilares pela NBR 8800:2024, 6.7 (nucleo/base_pilar.py), com as reações concomitantes de cada combinação
function painelBases() {
  const B = $('#bases'), L = (RAIZ && RAIZ.bases) || null;
  if (!L) { B.replaceChildren(el('div', { class: 'sub', texto: 'Calcule de novo para dimensionar as bases.' })); return; }
  const mm = (v) => nf(v, 0);
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'base (x, y m)' }), el('th', { texto: 'pilar' }), el('th', { texto: 'chumbadores · placa (mm)' }), el('th', { texto: '' })));
  const det = el('div', {});
  // as bases iguais (mesmo pilar e mesma solução) numa linha só
  const grupos = new Map();
  for (const b of L) {
    const bb = b.base;
    const k = bb ? `${b.perfil}|${bb.tipo}|${bb.nb}|${bb.diametro}|${bb.tp}|${bb.lx}|${bb.ly}|${b.ok}` : `${b.perfil}|${b.chave}`;
    const g = grupos.get(k) || { b, chaves: [] }; g.chaves.push(b.chave); grupos.set(k, g);
  }
  for (const { b, chaves } of grupos.values()) {
    const bb = b.base;
    const xy = chaves.map(c => c.split(',').map(v => (+v / 1000).toFixed(1)).join('; ')).join(' · ');
    const st = b.ok === null || b.ok === undefined ? '<span class="sub">—</span>' : b.ok ? '<span class="g-ok">ok</span>' : '<span class="g-ruim">não fecha</span>';
    const tr = el('tr', { class: 'clic', title: (b.avisos || []).join('\n') },
      el('td', { texto: chaves.length > 1 ? `${chaves.length} bases` : xy, title: xy }), el('td', { texto: b.perfil }),
      el('td', { texto: bb && bb.tp ? `${bb.nb}×ø${bb.diametro} · ${mm(bb.lx)}×${mm(bb.ly)}×${nf(bb.tp, 1)}` : bb ? `${bb.nb}×ø${bb.diametro}` : '—' }),
      el('td', { html: st + ((b.avisos || []).length ? ' ⚠' : '') }));
    tr.onclick = () => { det.replaceChildren(detalheDaBase(b, xy)); };
    t.append(tr);
  }
  B.replaceChildren(el('div', { class: 'sub', texto: `Cada base verificada em todas as combinações últimas${RAIZ.outras_situacoes ? ' das duas situações' : ''}, cada uma com o N, o M e o V dela (concomitantes, de 2ª ordem). Método da NBR 8800:2024, 6.7 (com a Errata 1:2025): placa e chumbadores pela Tabela 18, chumbadores ASTM A36, bloco f_ck ${nf(L[0] ? L[0].fck : 25, 0)} MPa, placa ${L[0] ? L[0].aco_placa : ''}. Clique numa linha para ver a conta.` }), t, det);
}

function detalheDaBase(b, xy) {
  const bb = b.base, env = b.envoltoria || {};
  const box = el('div', { class: 'verif', style: 'margin-top:6px' });
  const linhas = [`<b>Base ${xy}</b> — pilar ${b.perfil}, apoio ${b.apoio}`];
  const cr = (c) => c ? `${nf(c.N, 1)} kN · M ${nf(c.M, 1)} · V ${nf(c.V, 1)} (${c.sit ? c.sit + ' · ' : ''}${c.comb})` : '—';
  linhas.push(`<table class="vt"><tr><td>N máx</td><td>${cr(env.N_max)}</td></tr><tr><td>N mín</td><td>${cr(env.N_min)}</td></tr><tr><td>M máx</td><td>${cr(env.M_max)}</td></tr><tr><td>V máx</td><td>${cr(env.V_max)}</td></tr></table>`);
  if (bb) {
    const T = bb.tabela || {}, K = bb.bloco || {};
    const tab = [];
    tab.push(`<tr><td>Método</td><td>${bb.norma || 'NBR 8800:2024, 6.7'}</td></tr>`);
    tab.push(`<tr><td>Solução</td><td>base tipo ${bb.tipo} (${bb.tipo === 1 ? (bb.ld ? 'placa circular' : 'chumbadores externos') : bb.tipo === 3 ? 'placa circular' : 'internos'}) · <b>${bb.nb} chumbadores ø ${bb.diametro}</b> ASTM A36 · placa <b>${nf(bb.lx, 0)} × ${nf(bb.ly, 0)} × ${nf(bb.tp, 1)} mm</b> (t<sub>p,mín</sub> ${nf(bb.tp_min, 1)} mm)${bb.peso_kg ? ` · ~${nf(bb.peso_kg, 0)} kg` : ''}</td></tr>`);
    tab.push(`<tr><td>Casos</td><td>${(bb.casos || []).join(', ')} (Figuras 22 e 23); a espessura governa em ${bb.governa_tp ? `${bb.governa_tp.sit ? bb.governa_tp.sit + ' · ' : ''}${bb.governa_tp.comb} (${bb.governa_tp.caso})` : '—'}</td></tr>`);
    if (bb.governa_ft) tab.push(`<tr><td>Chumbador</td><td>F<sub>t,Sd</sub> = ${nf(bb.governa_ft.Ft, 1)} kN por chumbador → d<sub>b,mín</sub> ${nf(bb.governa_ft.db_min, 1)} mm (ø ${nf(bb.db, 0)} mm) em ${bb.governa_ft.comb} (${bb.governa_ft.caso})</td></tr>`);
    const pc = bb.placa_cisalhamento;
    tab.push(`<tr><td>Cortante</td><td>${bb.dispositivo === 'atrito' ? 'atrito placa–argamassa (μ = 0,45)' : bb.dispositivo === 'arruelas soldadas' ? 'arruelas especiais soldadas à placa (6.7.2.5)' : `placa de cisalhamento ${nf(pc.bh, 0)} × ${nf(pc.bv, 0)} × ${nf(pc.tpv, 1)} mm (6.7.2.4)`}</td></tr>`);
    tab.push(`<tr><td>Tabela 18</td><td>a₁ ${T.a1} · a₂ ${T.a2} · embutimento h₁ ${T.h1} · h₂ ${T.h2} · r₁ ${T.r1} · r₂ ${T.r2} · furo ${T.df} · arruela ${T.arruela}×${T.arruela}×${nf(T.ta, 1)} · argamassa e<sub>n</sub> ${T.en} mm</td></tr>`);
    tab.push(`<tr><td>Bloco</td><td>mínimo ${nf(K.Nb, 0)} × ${nf(K.Bb, 0)} mm, altura ${nf(K.Ab, 0)} mm; f<sub>ck</sub> ≥ ${T.fck_min} MPa; armadura mínima ø${nf(K.phi, 1)} c/ ${K.S} mm (NBR 6118); argamassa com o dobro do f<sub>ck</sub> do bloco</td></tr>`);
    linhas.push(`<table class="vt">${tab.join('')}</table>`);
    if ((bb.criticas || []).length) {
      linhas.push('<div class="sub" style="margin-top:4px">Combinações que governam:</div><table class="vt">' + bb.criticas.map(r =>
        `<tr><td>${r.caso || '—'}</td><td>${r.sit ? r.sit + ' · ' : ''}${r.comb}: N ${nf(r.N, 1)} · M ${nf(r.M, 1)} · V ${nf(r.V, 1)} → t<sub>p,mín</sub> ${nf(r.tp_min, 1)} mm${r.Ft ? ` · F<sub>t</sub> ${nf(r.Ft, 1)} kN` : ''}${r.erro ? ` · <span class="g-ruim">${r.erro}</span>` : ''}</td></tr>`).join('') + '</table>');
    }
    if ((bb.falhas || []).length) linhas.push(`<div class="erro">${bb.falhas.join('<br>')}</div>`);
    const J = b.chumbador_j;
    if (J) linhas.push(`<div class="sub" style="margin-top:6px"><b>Chumbador em J</b> (barra roscada A36 dobrada, concretada com a armadura do bloco — NBR 6118:2023, 9.4.2):</div>
      <table class="vt"><tr><td>Ancoragem</td><td>F<sub>t</sub> ${nf(J.Ft_kN, 1)} kN por chumbador · f<sub>bd</sub> = ${nf(J.fbd, 2)} MPa (barra lisa, η₁ = 1,0) · ℓ<sub>b</sub> = ${nf(J.lb, 0)} mm · <b>ℓ<sub>b,nec</sub> = ${nf(J.lb_nec, 0)} mm</b> (com gancho, α = 0,7) contra o embutimento da Tabela (${nf(J.h_disponivel, 0)} mm) — ${J.ok ? '<span class="g-ok">ok</span>' : '<span class="g-ruim">precisa de embutimento maior</span>'}</td></tr>
      <tr><td>Gancho</td><td>semicircular (obrigatório na barra lisa, 9.4.2.3) · ponta reta ≥ ${nf(J.ponta_reta_min, 0)} mm · pino de dobramento ≥ ${nf(J.pino_dobramento_min, 0)} mm · cobrimento ≥ 3φ no plano do gancho</td></tr></table>
      <div class="sub">A dispensa do arrancamento da 6.7.1.5 vale só para o chumbador reto com porca e arruela da Tabela 18; o J é ancorado por aderência e passa a força para a armadura do bloco (suspensão e a transversal de 9.4.2.6 — projeto de fundações).</div>`);
    const AB = b.com_abas;
    if (AB) linhas.push(`<div class="sub" style="margin-top:6px"><b>Com abas de reforço</b> (uma de cada lado, no plano da alma — ${AB.metodo}):</div>
      <table class="vt"><tr><td>Placa</td><td><b>${AB.tp ? nf(AB.tp, 1) : '—'} mm</b> (sem abas ${nf(bb.tp, 1)} mm) · t<sub>mín</sub> ${nf(AB.tp_min, 1)} mm · ~${nf(AB.peso_kg, 0)} kg (sem abas ~${nf(bb.peso_kg, 0)} kg)</td></tr>
      <tr><td>Aba</td><td>${nf(AB.hg, 0)} × ${nf(AB.Lg, 0)} × ${nf(AB.tg, 1)} mm · força ${nf(AB.F_aba_kN, 0)} kN · usos: flexão ${nf(AB.u_flexao * 100, 0)}%, cortante ${nf(AB.u_cortante * 100, 0)}%, borda livre ${nf(AB.u_borda * 100, 0)}% · filete ${AB.perna_solda ? nf(AB.perna_solda, 0) + ' mm' : '<span class="g-ruim">acima de 12 mm</span>'}</td></tr></table>
      ${(AB.falhas || []).length ? `<div class="aviso">${AB.falhas.join('<br>')}</div>` : ''}`);
  }
  if ((b.avisos || []).length) linhas.push(`<div class="aviso">${b.avisos.join('<br>')}</div>`);
  box.innerHTML = linhas.join('');
  return box;
}

// o que cada tesoura entrega onde apoia (o carrinho da cobertura retrátil): o pior de cada direção
function painelCarrinho() {
  const C = $('#carrinho'), A = D.apoios_tesouras;
  if (!A) { C.replaceChildren(el('div', { class: 'sub', texto: 'Sem tesouras apoiadas em viga ou pilar neste resultado (ou calcule de novo).' })); return; }
  const p = A.pior, xy = (v) => v.xy.map(x => nf(x, 2)).join('; ');
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'o pior' }), el('th', { texto: 'kN' }), el('th', { texto: 'onde' })));
  const lin = (rot, v, cor) => t.append(el('tr', { title: v.comb }, el('td', { texto: rot }), el('td', { html: cor ? `<b style="color:${cor}">${nf(v.valor, 1)}</b>` : nf(v.valor, 1) }), el('td', { texto: `${v.grupo} (${xy(v)}) · ${v.comb}` })));
  lin('compressão no apoio', p.Fv_max);
  lin('arrancamento', p.Fv_min, p.Fv_min.valor < 0 ? '#c0392b' : null);
  lin('horizontal no vão', p.Ht_max);
  lin('ao longo do trilho', p.Hl_max);
  const media = A.apoios.length ? A.apoios.reduce((s, a) => s + Math.max(0, a.Fv_max[0]), 0) / A.apoios.length : 0;
  C.replaceChildren(el('div', { class: 'sub', texto: `${A.n} apoios — a soma das forças que a tesoura e o que vai com ela (a sanfona) entregam no apoio, nas combinações últimas (2ª ordem). Compressão positiva; negativa = arrancamento.` }), t,
    el('div', { class: 'aviso', texto: D.movel
      ? `Para o fabricante do carrinho: ele precisa segurar o arrancamento e as duas forças horizontais acima. A média por apoio é ${nf(media, 1)} kN: os picos ficam nos apoios sobre os pilares porque a sanfona, modelada como X rígido, trabalha como treliça ao longo do trilho e leva a carga para os pontos mais rígidos — se a sanfona real for articulada (pantógrafo), essa redistribuição não existe. Confirmar com o fabricante.`
      : `É o que a ligação da tesoura no apoio precisa transmitir (média por apoio ${nf(media, 1)} kN).` }));
}

// os esforços nas ligações viga–pilar (as pontas das vigas que chegam em pilares), concomitantes, de 2ª ordem
function painelLigacoes() {
  const P = $('#ligacoes'), L = D.ligacoes;
  if (!L || !L.length) { P.replaceChildren(el('div', { class: 'sub', texto: 'Nenhuma viga chegando em pilar neste modelo (ou calcule de novo).' })); return; }
  const topo = ligacoesNoTopo();
  // as ligações parecidas (mesmos perfis, mesmos esforços arredondados) numa linha
  const g = new Map();
  for (const l of L) {
    const m = l.max;
    const k = `${l.perfil_viga}|${l.perfil_pilar}|${Math.round(m.Mz[0])}|${Math.round(m.V[0])}`;
    const it = g.get(k) || { l, n: 0 }; it.n++; g.set(k, it);
  }
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'viga → pilar' }), el('th', { texto: 'M (kN·m)' }), el('th', { texto: 'V' }), el('th', { texto: 'N±' })));
  for (const { l, n } of [...g.values()].slice(0, 14)) {
    const m = l.max, c = m.Mz[1];
    t.append(el('tr', { title: `${n} ligação(ões); a de (${l.xyz.map(v => nf(v, 2)).join('; ')})
M máx em ${c.comb}: N ${nf(c.N, 1)} kN, V ${nf(c.V, 1)} kN, M fraco ${nf(c.My, 2)} kN·m
V máx em ${m.V[1].comb}; tração máx em ${m.Nt[1].comb}; compressão máx em ${m.Nc[1].comb}` },
      el('td', { texto: `${l.perfil_viga} → ${l.perfil_pilar}${n > 1 ? ` (${n})` : ''}` }),
      el('td', { html: `<b>${nf(m.Mz[0], 1)}</b> <span class="sub">${c.comb}</span>` }),
      el('td', { texto: nf(m.V[0], 1) }), el('td', { texto: `+${nf(m.Nt[0], 1)} / −${nf(m.Nc[0], 1)}` })));
  }
  P.replaceChildren(...topo, el('div', { class: 'sub', style: 'margin-top:8px', texto: 'Os esforços nas pontas das vigas que chegam em pilares (2ª ordem): o maior momento no eixo forte e, passando o mouse, a normal, o cortante e o momento fraco da MESMA combinação.' }), t);
}

// a viga apoiada no topo do pilar por duas chapas parafusadas (nucleo/ligacao_topo_pilar.py — a solução de partida)
function ligacoesNoTopo() {
  const L = (RAIZ && RAIZ.ligacoes_topo) || null;
  if (!L || !L.length) return [];
  const det = el('div', {});
  const g = new Map();
  for (const l of L) {
    const x = l.ligacao || {};
    const k = `${l.pilar}|${l.viga}|${x.n}|${x.diametro}|${x.t_pilar}|${x.t_viga}|${l.ok}|${(l.pontas_viga || []).map(p => p.ligacao && p.ligacao.Lp).join(',')}`;
    const it = g.get(k) || { l, chaves: [] }; it.chaves.push(l.chave); g.set(k, it);
  }
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'pilar · viga' }), el('th', { texto: 'parafusos · chapas (mm)' }), el('th', { texto: '' })));
  for (const { l, chaves } of g.values()) {
    const x = l.ligacao || {};
    const tr = el('tr', { class: 'clic', title: l.aviso || '' },
      el('td', { texto: `${l.pilar} · ${l.viga}${chaves.length > 1 ? ` (${chaves.length})` : ''}` }),
      el('td', { texto: x.n ? `${x.n}×ø${x.diametro} A325 · ${nf(x.Bx, 0)}×${nf(x.By, 0)} · ${nf(x.t_pilar, 1)}/${nf(x.t_viga, 1)}` : '—' }),
      el('td', { html: (l.ok ? '<span class="g-ok">ok</span>' : '<span class="g-ruim">não fecha</span>') + (l.aviso ? ' ⚠' : '') }));
    tr.onclick = () => det.replaceChildren(detalheDaLigacao(l, chaves));
    t.append(tr);
  }
  return [el('div', { class: 'sub', texto: 'Viga apoiada no topo do pilar: chapa soldada no topo do pilar + chapa soldada sob a mesa da viga, parafusos verticais (a solução de partida, a avaliar). NBR 8800:2024 — parafusos 6.3.3, alavanca 6.3.5, solda 6.2.5, alma da viga 5.7.3/5.7.4. Clique para ver a conta.' }), t, det];
}

function detalheDaLigacao(l, chaves) {
  const x = l.ligacao || {}, env = l.envoltoria || {};
  const pc = (v) => `${nf((v || 0) * 100, 0)}%`;
  const box = el('div', { class: 'verif', style: 'margin-top:6px' });
  const cr = (c) => c ? `N ${nf(c.N, 1)} kN · M ${nf(Math.hypot(c.Mz, c.My), 1)} kN·m · V ${nf(c.V, 1)} kN (${c.sit ? c.sit + ' · ' : ''}${c.comb})` : '—';
  const L = [`<b>Topo do pilar ${l.pilar} — viga ${l.viga}</b> ${l.viga_continua ? '(viga contínua sobre o pilar)' : '(a viga termina no pilar)'}<br><span class="sub">${chaves.map(c => c.split(',').map(v => (+v / 1000).toFixed(1)).join('; ')).join(' · ')}</span>`];
  L.push(`<table class="vt"><tr><td>N máx</td><td>${cr(env.N_max)}</td></tr><tr><td>N mín</td><td>${cr(env.N_min)}</td></tr><tr><td>M máx</td><td>${cr(env.M_max)}</td></tr><tr><td>V máx</td><td>${cr(env.V_max)}</td></tr></table>`);
  if (x.n) {
    const pr = x.pior || {};
    L.push(`<table class="vt"><tr><td>Solução</td><td><b>${x.n} parafusos ø ${x.diametro} ASTM A325</b> (F<sub>t,Rd</sub> ${nf(x.Ft_Rd, 1)} · F<sub>v,Rd</sub> ${nf(x.Fv_Rd, 1)} kN) a ${nf(x.gx, 0)} × ${nf(x.gy, 0)} mm · chapas ${nf(x.Bx, 0)} × ${nf(x.By, 0)} mm: <b>${nf(x.t_pilar, 1)} mm no pilar</b> e <b>${nf(x.t_viga, 1)} mm na viga</b> · filete pilar–chapa ${x.perna_solda ? nf(x.perna_solda, 0) + ' mm' : '—'} (E70XX)</td></tr>
      <tr><td>Usos</td><td>tração no parafuso ${pc(pr.ft)} · cisalhamento ${pc(pr.fv)} · tração + cisalhamento ${pc(pr.int)} · contato no furo ${pc(pr.contato)} · alma da viga ${pc(pr.alma)}</td></tr>
      <tr><td>Chapas</td><td>t<sub>mín</sub> pela alavanca (placa flexível, 6.3.5.4): pilar ${nf(pr.tp, 1)} mm · viga ${nf(pr.tv, 1)} mm${x.parafusos_fora_da_mesa ? ' (parafusos fora da mesa da viga: a chapa da viga em balanço da borda da mesa)' : ''}</td></tr>
      ${x.alma ? `<tr><td>Alma da viga</td><td>C = ${nf(x.alma.C, 1)} kN contra ${nf(Math.min(x.alma.F_esc, x.alma.F_enr), 1)} kN (${x.alma.governa})${x.enrijecedor_na_viga ? ' — <span class="g-ruim">enrijecedores na alma</span>' : ''}</td></tr>` : ''}</table>`);
    if ((x.falhas || []).length) L.push(`<div class="erro">${x.falhas.join('<br>')}</div>`);
  }
  for (const p of l.pontas_viga || []) {
    const y = p.ligacao || {}, pr = y.pior || {};
    L.push(`<div class="sub" style="margin-top:4px"><b>Ponta da viga ${p.viga}</b> — M até ${nf(p.M_max, 1)} kN·m: ${y.n ? `${y.n}×ø${y.diametro} · chapa ${nf(y.Lp, 0)} mm ao longo × ${nf(y.t_chapa, 1)} mm · usos tração ${pc(pr.ft)}, interação ${pc(pr.int)}, alma ${pc(pr.alma)}` : '—'} ${p.ok ? '<span class="g-ok">ok</span>' : '<span class="g-ruim">não fecha</span>'}</div>`);
  }
  if (l.chapa_topo_ao_longo_mm) L.push(`<div class="sub">A chapa do topo do pilar precisa ter ${nf(l.chapa_topo_ao_longo_mm, 0)} mm ao longo da viga para receber as duas pontas.</div>`);
  if (l.aviso) L.push(`<div class="aviso">${l.aviso}</div>`);
  L.push(`<div class="sub">A análise considera a ligação viga–pilar rígida; chapas parafusadas no topo são semirrígidas (a rigidez cresce com a espessura das chapas e a protensão dos parafusos) — se a ligação girar, parte do momento migra para a base do pilar.</div>`);
  box.innerHTML = L.join('');
  return box;
}

// a 2ª ordem de cada combinação última (nucleo3d/segunda_ordem.py): Δ1 e Δ2 no topo dos pilares, a razão e a classe
function painelSegunda() {
  const S = $('#segunda'), so = D.segunda_ordem;
  if (!so) {
    S.replaceChildren(el('div', { class: 'sub', texto: D.parametros && D.parametros.segunda_ordem === false ? 'Desligada nas premissas: os esforços são de 1ª ordem.' : 'Sem 2ª ordem neste resultado (calcule de novo).' }));
    return;
  }
  const r = so.resumo || {};
  const cls = { pequena: 'pequena (≤ 1,1)', 'média': 'média (1,1 a 1,4)', grande: 'GRANDE (> 1,4)' };
  const t = el('table', {}, el('tr', {}, el('th', { texto: 'combinação' }), el('th', { texto: 'Δ1 mm' }), el('th', { texto: 'Δ2 mm' }), el('th', { texto: 'Δ2/Δ1' }), el('th', { texto: 'it.' })));
  for (const [c, x] of Object.entries(so.combinacoes)) {
    t.append(el('tr', { title: x.instavel || `forças nocionais: ${nf(x.nocional.H_kN, 2)} kN na direção (${x.nocional.dir.map(v => nf(v, 2)).join('; ')})` },
      el('td', { texto: c }), el('td', { texto: nf(x.delta1_mm, 1) }), el('td', { texto: x.delta2_mm !== undefined ? nf(x.delta2_mm, 1) : '—' }),
      el('td', { html: x.instavel ? '<b class="g-ruim">instável</b>' : `<span class="${x.razao > 1.4 ? 'g-ruim' : ''}">${nf(x.razao, 3)}</span>` }),
      el('td', { texto: String(x.iteracoes) })));
  }
  S.replaceChildren(
    el('div', { html: `Deslocabilidade <b>${cls[r.classe] || '—'}</b> — Δ2/Δ1 até <b>${nf(r.razao_max, 3)}</b>${r.comb_razao_max ? ` (${r.comb_razao_max})` : ''}.${(r.instaveis || []).length ? ` <b class="g-ruim">Instável em ${r.instaveis.length} combinação(ões).</b>` : ''}` }),
    el('div', { class: 'sub', style: 'margin:4px 0', texto: `Cada combinação última com P-Δ (rigidez geométrica, iterando a normal), EA e EI × ${nf(r.fator_rigidez || 0.8, 1)} e forças nocionais de ${nf((r.nocional || 0.003) * 100, 1)}% da carga gravitacional de cálculo de cada nó nas combinações só gravitacionais, nas duas direções em planta (cada uma vira ·X e ·Y; NBR 8800:2024, 4.10.7.1.1) — nas de vento a norma as dispensa (carregamento lateral mínimo), salvo na grande deslocabilidade (4.10.7.2). Δ = o maior deslocamento horizontal no topo dos pilares; Δ1 = 1ª ordem com as mesmas cargas e rigidez. Os esforços, as reações e a verificação das ELU já são os de 2ª ordem.` }),
    t);
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
  const r2 = D && D.segunda_ordem && D.segunda_ordem.resumo;
  const nv = D && D.verificacao ? D.verificacao.pecas.filter(p => !p.hipotese && p.uso > 1).length : null;
  $('#estado').textContent = D && !D.vazio ? `Calculado em ${(RAIZ || D).calculado_em} (${nf((RAIZ || D).segundos, 1)} s) · ${D.barras.length} barras, ${D.nos.length} nós, ${D.apoios.length} apoios · ${Object.keys(D.casos).length} casos, ${Object.keys(D.combinacoes).length} combinações`
    + (r2 ? ` · 2ª ordem: Δ2/Δ1 até ${nf(r2.razao_max, 2)} (${r2.classe})` : '') + (nv !== null ? ` · ${nv} peça(s) acima de 100%` : '') : (D && D.vazio) || '';
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
  cabecalho();
  montarControles(); painelRanking(); painelSegunda(); painelCarrinho(); painelLigacoes(); painelVento(); painelEquilibrio(); painelAvisos(); painelPeca();
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
  montarControles(); painelRanking(); painelSegunda(); painelReacoes(); painelBases(); painelCarrinho(); painelLigacoes(); painelVento(); painelEquilibrio(); painelAvisos(); painelPeca();
  if (!aplicar._vista) { vista('iso'); aplicar._vista = true; }
  desenhar();
}

async function carregar() {
  const r = await fetch(API, { cache: 'no-store' });
  aplicar(await r.json());
}

async function calcular(extra = {}) {
  $('#carregando').style.display = 'flex';
  try {
    const r = await fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ parametros: { ...lerPremissas(), ...extra } }) });
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    aplicar(j);
  } catch (e) { alert('Não foi possível calcular: ' + e.message); }
  $('#carregando').style.display = 'none';
}
$('#btn-calcular').addEventListener('click', () => calcular());

redimensionar();
carregar().catch(e => { $('#vazio').hidden = false; $('#vazio').textContent = 'Não foi possível abrir: ' + e.message; });
window.ae = { get D() { return D; }, estado, desenhar, camera, painelPeca };
