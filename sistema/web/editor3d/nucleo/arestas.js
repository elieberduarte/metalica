// Arestas de um sólido, direto das faces dele. Sem Three.js: roda no node (testes/test_arestas_3d.py).

/**
 * Arestas de um sólido direto das faces dele (polígonos de índices), com o critério do
 * `THREE.EdgesGeometry(geom, 24)`: borda de uma face só, ou dobra entre duas faces maior que
 * o limiar. O EdgesGeometry olha triângulo por triângulo, com chaves de texto em cada canto,
 * e levava 9 dos 40 s de abrir o Bella Casa (05/10); aqui a vizinhança vem pelos índices.
 * Vértices repetidos (mesma posição, a 1 µm) contam como um só. Devolve os pares de pontos.
 */
export function arestasDoSolido(vs, fs, limiarGraus = 24) {
  const cosLim = Math.cos(limiarGraus * Math.PI / 180);
  const nv = vs.length;
  const canon = new Int32Array(nv);
  const porPos = new Map();
  for (let i = 0; i < nv; i++) {
    const p = vs[i];
    if (!p) { canon[i] = i; continue; }
    const k = Math.round(p[0] * 1e3) + ',' + Math.round(p[1] * 1e3) + ',' + Math.round(p[2] * 1e3);
    const j = porPos.get(k);
    if (j === undefined) { porPos.set(k, i); canon[i] = i; } else canon[i] = j;
  }
  const normais = [];
  const pares = new Map();             // a*nv+b (a<b) -> [a, b, face, outra face ou -1, vezes]
  for (let fi = 0; fi < fs.length; fi++) {
    const f = fs[fi];
    if (!f || f.length < 3 || f.some(i => !vs[i])) continue;
    // normal de Newell (vale para polígono de qualquer forma)
    let nx = 0, ny = 0, nz = 0;
    for (let k = 0; k < f.length; k++) {
      const a = vs[f[k]], b = vs[f[(k + 1) % f.length]];
      nx += (a[1] - b[1]) * (a[2] + b[2]);
      ny += (a[2] - b[2]) * (a[0] + b[0]);
      nz += (a[0] - b[0]) * (a[1] + b[1]);
    }
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-12) continue;                        // face degenerada: o EdgesGeometry também a pula
    normais[fi] = [nx / len, ny / len, nz / len];
    for (let k = 0; k < f.length; k++) {
      let a = canon[f[k]], b = canon[f[(k + 1) % f.length]];
      if (a === b) continue;
      if (a > b) { const t = a; a = b; b = t; }
      const chave = a * nv + b;
      const r = pares.get(chave);
      if (!r) pares.set(chave, [a, b, fi, -1, 1]);
      else { if (r[3] < 0) r[3] = fi; r[4]++; }
    }
  }
  const saida = [];
  for (const [a, b, f1, f2, vezes] of pares.values()) {
    if (vezes === 2) {
      const n1 = normais[f1], n2 = normais[f2];
      if (n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2] > cosLim) continue;     // dobra suave: não é aresta
    }
    const p = vs[a], q = vs[b];
    saida.push(p[0], p[1], p[2], q[0], q[1], q[2]);
  }
  return new Float32Array(saida);
}
