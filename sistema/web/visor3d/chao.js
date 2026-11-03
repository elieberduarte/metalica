// O chão em mais de um nível (03/11, o usuário pelo SESI Chapecó: "encontramos uma limitação legal da nossa representação do
// terreno, quando temos níveis diferentes"; escolhida a malha pelos pontos, amostras em Projeto/ESTUDOS/Terreno-niveis): a
// imagem do terreno deixa de ser um plano numa cota só e passa pelos pontos de nível do projeto (a calçada −0,50, o pátio do
// subsolo −3,98, a rua que desce em rampa). Só as contas, sem o three (o node roda os testes): a triangulação dos pontos, a
// face do prédio pelos eixos (o chão encosta nela na cota do lado de fora, não numa rampa por baixo do prédio), o anel de
// longe na altura de sempre (fora da obra o chão volta ao plano de antes) e a cota de cada vértice da malha da imagem.

const PASSO_FACE = 5000;          // mm entre os pontos da face do prédio
const FORA_FACE = 1500;           // mm para fora da face (o pilar e a fachada ficam por cima)
const ALCANCE_FACE = 60000;       // mm: os pontos de nível que dão a cota da face (os 4 mais perto, do mesmo lado)

/** A triangulação de Delaunay (Bowyer–Watson) de [[x, y]…] → [[i, j, k]…]. Pontos repetidos ficam de fora. */
export function triangular(p) {
  const n = p.length;
  if (n < 3) return [];
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of p) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, d = Math.max(x1 - x0, y1 - y0, 1) * 20;
  // perto da origem (a conta do círculo em mm de obra grande perde casas)
  const q = p.map(([x, y]) => [x - cx, y - cy]);
  q.push([-2 * d, -d], [2 * d, -d], [0, 2 * d]);
  const circulo = (a, b, c) => {
    const [ax, ay] = q[a], [bx, by] = q[b], [qx, qy] = q[c];
    const D = 2 * (ax * (by - qy) + bx * (qy - ay) + qx * (ay - by));
    if (Math.abs(D) < 1e-12) return null;
    const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = qx * qx + qy * qy;
    const ux = (a2 * (by - qy) + b2 * (qy - ay) + c2 * (ay - by)) / D, uy = (a2 * (qx - bx) + b2 * (ax - qx) + c2 * (bx - ax)) / D;
    return [ux, uy, (ax - ux) ** 2 + (ay - uy) ** 2];
  };
  let tris = [{ v: [n, n + 1, n + 2], c: circulo(n, n + 1, n + 2) }];
  const vistos = new Set();
  for (let i = 0; i < n; i++) {
    const chave = `${Math.round(q[i][0])},${Math.round(q[i][1])}`;
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    const [px, py] = q[i], ruins = [], bons = [];
    for (const t of tris) {
      if (t.c && (px - t.c[0]) ** 2 + (py - t.c[1]) ** 2 < t.c[2] * (1 + 1e-12)) ruins.push(t); else bons.push(t);
    }
    const arestas = new Map();
    for (const t of ruins) for (let k = 0; k < 3; k++) {
      const a = t.v[k], b = t.v[(k + 1) % 3], ch = a < b ? `${a},${b}` : `${b},${a}`;
      arestas.set(ch, arestas.has(ch) ? null : [a, b]);
    }
    tris = bons;
    for (const ab of arestas.values()) if (ab) tris.push({ v: [ab[0], ab[1], i], c: circulo(ab[0], ab[1], i) });
  }
  return tris.filter(t => t.v.every(k => k < n)).map(t => t.v);
}

/** O casco convexo de [[x, y]…] (cadeia monótona), no sentido anti-horário. */
export function casco(p) {
  const s = [...p].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (s.length < 3) return s;
  const cruz = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const baixo = [], cima = [];
  for (const v of s) { while (baixo.length >= 2 && cruz(baixo[baixo.length - 2], baixo[baixo.length - 1], v) <= 0) baixo.pop(); baixo.push(v); }
  for (const v of s.reverse()) { while (cima.length >= 2 && cruz(cima[cima.length - 2], cima[cima.length - 1], v) <= 0) cima.pop(); cima.push(v); }
  return baixo.slice(0, -1).concat(cima.slice(0, -1));
}

/** O contorno do prédio pelos eixos ([{a: [x, y], b: [x, y]}…], mm do projeto): o casco dos cruzamentos dos eixos (as
 *  linhas passam um pouco das pontas — o cruzamento é o eixo de verdade). null sem duas direções. */
export function contornoDosEixos(eixos) {
  const segs = (eixos || []).filter(e => e && e.a && e.b && Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1]) > 1);
  const cruzes = [];
  for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) {
    const [a, b] = [segs[i].a, segs[i].b], [c, d] = [segs[j].a, segs[j].b];
    const ux = b[0] - a[0], uy = b[1] - a[1], vx = d[0] - c[0], vy = d[1] - c[1];
    const den = ux * vy - uy * vx;
    if (Math.abs(den) < 0.34 * Math.hypot(ux, uy) * Math.hypot(vx, vy)) continue;     // menos de 20°: a mesma direção
    const t = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / den, s = ((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) / den;
    if (t < -0.01 || t > 1.01 || s < -0.01 || s > 1.01) continue;
    cruzes.push([a[0] + t * ux, a[1] + t * uy]);
  }
  const h = casco(cruzes);
  let area = 0;
  for (let i = 0; i < h.length; i++) { const p = h[i], q = h[(i + 1) % h.length]; area += p[0] * q[1] - q[0] * p[1]; }
  return h.length >= 3 && area / 2 > 1e6 ? h : null;                                    // mais de 1 m²
}

/** true: o segmento p–q passa por dentro do polígono convexo (anti-horário), mais que 1 mm. */
function cortaPoligono(p, q, poli) {
  let t0 = 0, t1 = 1;
  const dx = q[0] - p[0], dy = q[1] - p[1];
  for (let i = 0; i < poli.length; i++) {
    const a = poli[i], b = poli[(i + 1) % poli.length];
    const nx = b[1] - a[1], ny = a[0] - b[0];                                           // a normal para fora
    const num = nx * (a[0] - p[0]) + ny * (a[1] - p[1]), den = nx * dx + ny * dy;
    if (Math.abs(den) < 1e-12) { if (num < 0) return false; continue; }
    const t = num / den;
    if (den < 0) t0 = Math.max(t0, t); else t1 = Math.min(t1, t);
    if (t0 >= t1) return false;
  }
  return (t1 - t0) * Math.hypot(dx, dy) > 1;
}

/** Os pontos da face do prédio, por fora do contorno, com a cota dos pontos de nível da frente dessa face: só os que caem
 *  diante dela (não os da outra face, depois da quina), e o que está ao longo da face pesa mais que o que está para fora
 *  (o chão encostado na fachada segue o nível dela — no SESI o pátio −3,98 junto da face norte, não a rua −2,86 a 4,8 m). */
export function pontosDaFace(pontos, contorno) {
  if (!contorno || !pontos.length) return [];
  const fora = pontos.filter(p => !dentro(contorno, p.x, p.y));
  const saida = [];
  const m = contorno.length;
  for (let i = 0; i < m; i++) {
    const a = contorno[i], b = contorno[(i + 1) % m], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 1) continue;
    const ex = (b[0] - a[0]) / L, ey = (b[1] - a[1]) / L, nx = ey, ny = -ex, k = Math.max(1, Math.ceil(L / PASSO_FACE));
    const daFace = fora.filter(p => {
      const t = ((p.x - a[0]) * ex + (p.y - a[1]) * ey) / L, d = (p.x - a[0]) * nx + (p.y - a[1]) * ny;
      return t > -0.05 && t < 1.05 && d > 0;
    });
    for (let j = 0; j <= k; j++) {
      const q = [a[0] + (b[0] - a[0]) * j / k + nx * FORA_FACE, a[1] + (b[1] - a[1]) * j / k + ny * FORA_FACE];
      const dist = p => Math.hypot(((p.x - q[0]) * ex + (p.y - q[1]) * ey) / 8, (p.x - q[0]) * nx + (p.y - q[1]) * ny);
      const vis = daFace.map(p => [dist(p), p])
        .filter(([d, p]) => d < ALCANCE_FACE && !cortaPoligono(q, [p.x, p.y], contorno)).sort((u, v) => u[0] - v[0]).slice(0, 4);
      if (!vis.length) continue;
      let sw = 0, sz = 0;
      for (const [d, p] of vis) { const w = 1 / Math.max(d, 100) ** 2; sw += w; sz += w * p.z; }
      saida.push({ x: q[0], y: q[1], z: sz / sw, face: true });
    }
  }
  return saida;
}

/** true: (x, y) dentro do polígono convexo anti-horário. */
function dentro(poli, x, y) {
  for (let i = 0; i < poli.length; i++) {
    const a = poli[i], b = poli[(i + 1) % poli.length];
    if ((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]) < 0) return false;
  }
  return true;
}

/** A superfície do chão: os pontos de nível ({x, y, z} mm), a face do prédio (o `contorno` dos eixos) e o anel de longe
 *  na cota `base` (o plano de antes) a `raio` mm do `centro`. `cota(x, y)` é a do chão ali (a base fora de tudo). */
export function superficie(pontos, { base = 0, contorno = null, centro = null, raio = 400000 } = {}) {
  const reais = (pontos || []).filter(p => p && [p.x, p.y, p.z].every(Number.isFinite));
  const face = pontosDaFace(reais, contorno);
  const c = centro || (reais.length ? [reais.reduce((s, p) => s + p.x, 0) / reais.length, reais.reduce((s, p) => s + p.y, 0) / reais.length] : [0, 0]);
  const longe = Math.max(raio, ...reais.map(p => Math.hypot(p.x - c[0], p.y - c[1]) + 100000));
  const anel = [];
  for (let k = 0; k < 24; k++) anel.push({ x: c[0] + longe * Math.cos(k * Math.PI / 12), y: c[1] + longe * Math.sin(k * Math.PI / 12), z: base, anel: true });
  const todos = reais.concat(face, anel);
  const tri = triangular(todos.map(p => [p.x, p.y]));
  const cota = (x, y) => {
    for (const [i, j, k] of tri) {
      const z = baricentrica(todos[i], todos[j], todos[k], x, y);
      if (z !== null) return z;
    }
    return base;
  };
  return { pontos: todos, tri, face, base, cota };
}

function baricentrica(a, b, c, x, y, folga = 1e-9) {
  const den = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
  if (Math.abs(den) < 1e-9) return null;
  const l1 = ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y)) / den;
  const l2 = ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y)) / den, l3 = 1 - l1 - l2;
  if (l1 < -folga || l2 < -folga || l3 < -folga) return null;
  return l1 * a.z + l2 * b.z + l3 * c.z;
}

/** A cota de cada vértice da malha da imagem (PlaneGeometry(1, 1, n, n) de lados `largura` × `altura` mm, o meio em `meio`,
 *  girada `giro` rad em Z): Float32Array de (n + 1)², na ordem dos vértices do three (a linha de cima primeiro). Cada
 *  triângulo pinta os vértices que cobre (a malha inteira em ~1 passada, sem procurar o triângulo de cada vértice). */
export function cotasDaMalha(sup, { meio, largura, altura, giro, n }) {
  const N = n + 1, z = new Float32Array(N * N).fill(sup.base), feito = new Uint8Array(N * N);
  const c = Math.cos(giro), s = Math.sin(giro);
  // o ponto da obra → (coluna, linha) reais da malha
  const naGrade = p => {
    const dx = p.x - meio[0], dy = p.y - meio[1];
    const u = (c * dx + s * dy) / largura + 0.5, w = (-s * dx + c * dy) / altura;
    return { x: u * n, y: (0.5 - w) * n, z: p.z };
  };
  const g = sup.pontos.map(naGrade);
  for (const [i, j, k] of sup.tri) {
    const a = g[i], b = g[j], d = g[k];
    const c0 = Math.max(0, Math.ceil(Math.min(a.x, b.x, d.x) - 1e-6)), c1 = Math.min(n, Math.floor(Math.max(a.x, b.x, d.x) + 1e-6));
    const l0 = Math.max(0, Math.ceil(Math.min(a.y, b.y, d.y) - 1e-6)), l1 = Math.min(n, Math.floor(Math.max(a.y, b.y, d.y) + 1e-6));
    if (c0 > c1 || l0 > l1) continue;
    for (let l = l0; l <= l1; l++) for (let col = c0; col <= c1; col++) {
      const v = l * N + col;
      if (feito[v]) continue;
      const zz = baricentrica(a, b, d, col, l, 1e-7);
      if (zz !== null) { z[v] = zz; feito[v] = 1; }
    }
  }
  return z;
}

/** Quanto cada vértice é parede (0 a 1): o chão mais em pé que ~45° (o muro do subsolo, o degrau entre os níveis) sai numa
 *  cor neutra em vez da foto esticada. `passo` = [mm entre colunas, mm entre linhas]. */
export function paredesDaMalha(z, n, passo) {
  const N = n + 1, p = new Float32Array(N * N);
  for (let l = 0; l < N; l++) for (let col = 0; col < N; col++) {
    const v = l * N + col;
    const gx = (z[l * N + Math.min(col + 1, n)] - z[l * N + Math.max(col - 1, 0)]) / (passo[0] * (Math.min(col + 1, n) - Math.max(col - 1, 0)));
    const gy = (z[Math.min(l + 1, n) * N + col] - z[Math.max(l - 1, 0) * N + col]) / (passo[1] * (Math.min(l + 1, n) - Math.max(l - 1, 0)));
    const inc = Math.hypot(gx, gy);
    p[v] = Math.max(0, Math.min(1, (inc - 0.8) / 0.6));
  }
  return p;
}
