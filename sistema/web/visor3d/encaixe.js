// O encaixe da câmera numa foto (a cena, cena.js — usuário, 26/10: "encaixar certinho o 3D na imagem"). Com os pares de
// pontos — o ponto na foto (u, v de 0 a 1, v para baixo) e o mesmo ponto no modelo (x, y, z em mm, z para cima) — acha a
// câmera do three.js (posição, giro e o ângulo vertical da lente) que leva cada ponto do modelo ao ponto da foto.
//
// São 7 incógnitas (posição 3, giro 3, lente 1): 4 pares bastam (8 equações), 6 ou mais dão folga para o erro do clique.
// A conta é por mínimos quadrados (Levenberg–Marquardt) a partir de várias câmeras de saída em volta dos pontos, olhando
// para eles (de 12 direções, 3 alturas e 3 distâncias); fica a de menor erro. O erro sai em pixels da foto.

import * as THREE from 'three';

/** O ponto `X` (Vector3) na foto pela câmera `c` ({posicao: Vector3, giro: Quaternion, fov: graus}) e a proporção da foto
 *  (largura / altura): [u, v] de 0 a 1, ou null atrás da câmera. */
export function projetar(c, X, aspecto) {
  const p = X.clone().sub(c.posicao).applyQuaternion(c.giro.clone().invert());
  if (p.z >= -1e-9) return null;
  const t = Math.tan(c.fov * Math.PI / 360);
  const x = p.x / -p.z / (t * aspecto), y = p.y / -p.z / t;
  return [(x + 1) / 2, (1 - y) / 2];
}

const _eixo = new THREE.Vector3(), _q = new THREE.Quaternion();
/** Os 7 números → a câmera: centro + escala (a conta em unidades da nuvem de pontos), o giro de saída `q0` vezes o giro
 *  pequeno do vetor (p[3..5]), e a lente pela tangente (p[6] = log da tangente do meio ângulo, sempre positiva). */
function camera(p, centro, escala, q0) {
  const ang = Math.hypot(p[3], p[4], p[5]);
  _q.identity();
  if (ang > 1e-12) _q.setFromAxisAngle(_eixo.set(p[3] / ang, p[4] / ang, p[5] / ang), ang);
  return { posicao: new THREE.Vector3(p[0], p[1], p[2]).multiplyScalar(escala).add(centro), giro: q0.clone().multiply(_q),
           fov: 2 * Math.atan(Math.exp(p[6])) * 180 / Math.PI };
}

function residuos(p, pares, centro, escala, q0, W, H) {
  const c = camera(p, centro, escala, q0), r = [];
  for (const par of pares) {
    const uv = projetar(c, par.X, W / H);
    if (!uv) { r.push(5 * W, 5 * H); continue; }       // atrás da câmera: muito longe
    r.push((uv[0] - par.u) * W, (uv[1] - par.v) * H);
  }
  return r;
}

const soma2 = (r) => r.reduce((s, x) => s + x * x, 0);

/** Resolve A x = b (n × n) por eliminação com pivô. */
function resolver(A, b) {
  const n = b.length, M = A.map((l, i) => [...l, b[i]]);
  for (let k = 0; k < n; k++) {
    let m = k;
    for (let i = k + 1; i < n; i++) if (Math.abs(M[i][k]) > Math.abs(M[m][k])) m = i;
    [M[k], M[m]] = [M[m], M[k]];
    if (Math.abs(M[k][k]) < 1e-300) return null;
    for (let i = k + 1; i < n; i++) { const f = M[i][k] / M[k][k]; for (let j = k; j <= n; j++) M[i][j] -= f * M[k][j]; }
  }
  const x = new Array(n).fill(0);
  for (let i = n - 1; i >= 0; i--) { let s = M[i][n]; for (let j = i + 1; j < n; j++) s -= M[i][j] * x[j]; x[i] = s / M[i][i]; }
  return x;
}

function marquardt(p, f, voltas) {
  let r = f(p), e = soma2(r), lambda = 1e-3;
  for (let it = 0; it < voltas; it++) {
    const J = [];
    for (let k = 0; k < p.length; k++) {
      const h = 1e-6 * Math.max(1, Math.abs(p[k])), q = p.slice();
      q[k] += h;
      const rq = f(q);
      J.push(rq.map((v, i) => (v - r[i]) / h));
    }
    const n = p.length, JtJ = [], Jtr = [];
    for (let a = 0; a < n; a++) {
      JtJ.push([]);
      for (let b = 0; b < n; b++) { let s = 0; for (let i = 0; i < r.length; i++) s += J[a][i] * J[b][i]; JtJ[a].push(s); }
      let s = 0; for (let i = 0; i < r.length; i++) s += J[a][i] * r[i]; Jtr.push(-s);
    }
    let melhorou = false;
    for (let tentativa = 0; tentativa < 10 && !melhorou; tentativa++) {
      const A = JtJ.map((l, a) => l.map((v, b) => (a === b ? v * (1 + lambda) + 1e-12 : v)));
      const d = resolver(A, Jtr);
      if (!d) { lambda *= 10; continue; }
      const q = p.map((v, k) => v + d[k]), rq = f(q), eq = soma2(rq);
      if (eq < e) { p = q; r = rq; melhorou = eq < e * (1 - 1e-12); e = eq; lambda = Math.max(lambda / 10, 1e-12); }
      else lambda *= 10;
    }
    if (!melhorou) break;
  }
  return { p, e };
}

/** A câmera que encaixa os `pares` ([{u, v, X: [x, y, z]}]) numa foto `W` × `H` px: {posicao, giro, fov, erro_px (a média
 *  quadrática, em px da foto)}, ou null com menos de 4 pares. `saida` (opcional): uma câmera para começar também dela.
 *  `rapido`: só a partir da `saida` (o ajuste fino de um ponto, 26/10 — a câmera já está perto: milissegundos). */
export function encaixar(pares, W, H, saida = null, { rapido = false } = {}) {
  const ps = pares.filter(p => p && p.X).map(p => ({ u: p.u, v: p.v, X: new THREE.Vector3(...p.X) }));
  if (ps.length < 4) return null;
  const centro = ps.reduce((s, p) => s.add(p.X), new THREE.Vector3()).multiplyScalar(1 / ps.length);
  const escala = Math.max(...ps.map(p => p.X.distanceTo(centro)), 1);
  const nos = ps.map(p => ({ ...p, X: p.X.clone() }));
  const partidas = [];
  if (rapido && saida && saida.posicao && saida.giro) {
    const q0 = saida.giro.clone(), p0 = [...saida.posicao.clone().sub(centro).multiplyScalar(1 / escala).toArray(), 0, 0, 0,
                                       Math.log(Math.tan((saida.fov || 60) * Math.PI / 360))];
    const r = marquardt(p0, (p) => residuos(p, nos, centro, escala, q0, W, H), 200);
    return { ...camera(r.p, centro, escala, q0), erro_px: Math.sqrt(r.e / ps.length) };
  }
  const olhar = (olho) => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().lookAt(olho, centro, new THREE.Vector3(0, 0, 1)));
  for (const dist of [1.5, 3, 6]) for (const alt of [8, 25, 50]) for (let az = 0; az < 360; az += 30) {
    const a = az * Math.PI / 180, e = alt * Math.PI / 180;
    const olho = centro.clone().add(new THREE.Vector3(Math.cos(e) * Math.cos(a), Math.cos(e) * Math.sin(a), Math.sin(e)).multiplyScalar(dist * escala));
    partidas.push({ olho, q0: olhar(olho), t: Math.tan(30 * Math.PI / 180) });
  }
  if (saida && saida.posicao && saida.giro) {
    partidas.unshift({ olho: saida.posicao.clone(), q0: saida.giro.clone(), t: Math.tan((saida.fov || 60) * Math.PI / 360) });
  }
  let melhor = null;
  for (const s of partidas) {
    const p0 = [...s.olho.clone().sub(centro).multiplyScalar(1 / escala).toArray(), 0, 0, 0, Math.log(s.t)];
    const f = (p) => residuos(p, nos, centro, escala, s.q0, W, H);
    const r = marquardt(p0, f, 40);
    if (!melhor || r.e < melhor.e) melhor = { ...r, q0: s.q0 };
  }
  const fim = marquardt(melhor.p, (p) => residuos(p, nos, centro, escala, melhor.q0, W, H), 300);
  const c = camera(fim.p, centro, escala, melhor.q0);
  return { ...c, erro_px: Math.sqrt(fim.e / ps.length) };
}
