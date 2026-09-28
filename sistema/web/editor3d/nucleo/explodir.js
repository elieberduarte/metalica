// Explodir e juntar peças do 3D — a geometria, sem tela (testável no node).
//
// Explodir: a peça varrida (o perfil levado ao longo de um caminho — a peça dobrada do joelho, a
// barra quebrada em retas pelos Cantos redondos) vira uma peça por trecho reto, para separar um
// trecho e apagar um pedaço (pedido do usuário, 28/09: "a função de explodir do 2D para o 3D").
// A malha varrida é uma pilha de anéis iguais (a seção em cada ponta de trecho) ligados por
// quadriláteros, com uma tampa em cada ponta; o trecho reto é a sequência de anéis na mesma direção.
//
// Juntar: o contrário — as peças selecionadas numa só; as tampas que encostam (a emenda de dois
// trechos vizinhos) somem, e a peça que foi explodida volta inteira, com o nome de antes.

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cruz = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norma = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const n = norma(a) || 1; return [a[0] / n, a[1] / n, a[2] / n]; };
const media = (pts) => {
  const c = [0, 0, 0];
  for (const p of pts) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  return [c[0] / pts.length, c[1] / pts.length, c[2] / pts.length];
};

/** Normal (não normalizada) de um polígono pela soma de Newell — serve para o côncavo (o U). */
function normalDaFace(vs, f) {
  const n = [0, 0, 0];
  for (let i = 0; i < f.length; i++) {
    const a = vs[f[i]], b = vs[f[(i + 1) % f.length]];
    n[0] += (a[1] - b[1]) * (a[2] + b[2]);
    n[1] += (a[2] - b[2]) * (a[0] + b[0]);
    n[2] += (a[0] - b[0]) * (a[1] + b[1]);
  }
  return n;
}

/**
 * Os anéis da malha varrida, da tampa de uma ponta à da outra: cada anel na ordem da primeira
 * tampa (o vértice j de um anel liga no vértice j do seguinte). null quando a malha não é uma
 * varredura (furos feitos no editor, faces trianguladas, peça que não é de perfil).
 */
export function aneisDoSolido(vertices, faces) {
  const n = (vertices || []).length;
  if (n < 6 || !faces || !faces.length) return null;
  const viz = Array.from({ length: n }, () => new Set());
  for (const f of faces) {
    for (let i = 0; i < f.length; i++) {
      const a = f[i], b = f[(i + 1) % f.length];
      if (a !== b && a < n && b < n) { viz[a].add(b); viz[b].add(a); }
    }
  }
  // a tampa é a maior face (a seção); no prisma em U a face do lado também tem os vértices de grau 3 e
  // a caminhada por ela andava pelo contorno da seção
  for (const tampa of faces.slice().sort((x, y) => y.length - x.length)) {
    const k = tampa.length;
    if (k < 3 || n % k || !tampa.every(v => viz[v].size === 3)) continue;
    const aneis = [tampa.slice()];
    const usados = new Set(tampa);
    let ok = true;
    while (usados.size < n) {
      const prox = [];
      for (const v of aneis[aneis.length - 1]) {
        const novos = [...viz[v]].filter(w => !usados.has(w));
        if (novos.length !== 1) { ok = false; break; }
        prox.push(novos[0]);
      }
      if (!ok || new Set(prox).size !== k) { ok = false; break; }
      for (const w of prox) usados.add(w);
      aneis.push(prox);
    }
    if (ok && aneis.length >= 2 && aneis[aneis.length - 1].every(v => viz[v].size === 3)) return aneis;
  }
  return null;
}

/** A malha de um trecho: os anéis dados (já com as coordenadas), tampa nas duas pontas. */
function malhaDoTrecho(aneis) {
  const k = aneis[0].length, m = aneis.length;
  const vertices = aneis.flat().map(p => [p[0], p[1], p[2]]);
  // a direção na primeira ponta (no trecho curvo, a do primeiro pedaço)
  const d = unit(sub(media(aneis[1]), media(aneis[0])));
  let tampa0 = [...Array(k).keys()];
  if (dot(normalDaFace(vertices, tampa0), d) > 0) tampa0 = tampa0.reverse();      // para fora: para trás
  const tampa1 = tampa0.map(j => (m - 1) * k + j).reverse();
  // os lados, com a orientação tirada da face mais afastada do eixo (a de fora do perfil)
  const lados = [];
  for (let r = 0; r < m - 1; r++) {
    for (let j = 0; j < k; j++) {
      const j2 = (j + 1) % k;
      lados.push([r * k + j, r * k + j2, (r + 1) * k + j2, (r + 1) * k + j]);
    }
  }
  const c0 = media(aneis[0]);
  let longe = null, dist = -1;
  for (const f of lados.slice(0, k)) {
    const c = media(f.map(i => vertices[i]));
    const rad = sub(sub(c, c0), d.map(x => x * dot(sub(c, c0), d)));
    if (norma(rad) > dist) { dist = norma(rad); longe = { f, rad }; }
  }
  const virar = longe && dot(normalDaFace(vertices, longe.f), longe.rad) < 0;
  return { vertices, faces: [tampa0, tampa1, ...lados.map(f => (virar ? f.slice().reverse() : f))] };
}

/**
 * Os trechos retos da peça varrida: [{vertices, faces}], um por trecho (a mudança de direção
 * entre anéis vizinhos passa de `tolGraus`). null quando a malha não é varrida.
 */
export function trechosDoSolido(ent, tolGraus = 2.0) {
  const vs = ent && ent.vertices;
  const aneis = aneisDoSolido(vs, ent && ent.faces);
  if (!aneis) return null;
  const cs = aneis.map(a => media(a.map(i => vs[i])));
  const grupos = [[0]];
  let dAnt = null;
  for (let i = 0; i < cs.length - 1; i++) {
    const L = norma(sub(cs[i + 1], cs[i]));
    const d = L > 1e-6 ? unit(sub(cs[i + 1], cs[i])) : dAnt;
    if (dAnt && d && Math.acos(Math.max(-1, Math.min(1, dot(d, dAnt)))) * 180 / Math.PI > tolGraus) grupos.push([i]);
    grupos[grupos.length - 1].push(i + 1);
    if (d) dAnt = d;
  }
  // a curva facetada (o gancho do tirante, a barra calandrada) fica inteira: os pedaços curtos
  // (até 60 mm) vizinhos viram um trecho só
  const comp = g => norma(sub(cs[g[g.length - 1]], cs[g[0]]));
  const juntos = [];
  for (const g of grupos) {
    const ant = juntos[juntos.length - 1];
    if (ant && comp(g) < 60.0 && comp(ant) < 60.0) ant.push(...g.slice(1));
    else if (ant && comp(g) < 60.0 && ant.curva) ant.push(...g.slice(1));
    else juntos.push(g.slice());
    const ult = juntos[juntos.length - 1];
    if (ult.length > 2 && comp(g) < 60.0) ult.curva = true;
  }
  return juntos.map(g => malhaDoTrecho(g.map(r => aneis[r].map(i => vs[i]))));
}

/**
 * As malhas numa só: as tampas que encostam uma na outra (os mesmos pontos, até `tol` mm — a
 * emenda de dois trechos) saem, e os vértices delas viram um só.
 */
export function juntarMalhas(malhas, tol = 0.5) {
  const vertices = [], faces = [];
  for (const m of malhas) {
    const base = vertices.length;
    for (const p of m.vertices) vertices.push([p[0], p[1], p[2]]);
    for (const f of m.faces) faces.push(f.map(i => i + base));
  }
  const perto = (a, b) => Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol && Math.abs(a[2] - b[2]) <= tol;
  const dono = [];                                 // de que malha é cada face
  malhas.forEach((m, k) => { for (let i = 0; i < m.faces.length; i++) dono.push(k); });
  const tira = new Set();
  const refaz = new Map();                         // vértice → o vértice que fica
  for (let a = 0; a < faces.length; a++) {
    if (tira.has(a) || faces[a].length < 3) continue;
    for (let b = a + 1; b < faces.length; b++) {
      if (tira.has(b) || dono[a] === dono[b] || faces[b].length !== faces[a].length) continue;
      const par = faces[a].map(i => faces[b].find(j => perto(vertices[i], vertices[j])));
      if (par.some(j => j === undefined)) continue;
      tira.add(a); tira.add(b);
      faces[a].forEach((i, t) => refaz.set(par[t], i));
      break;
    }
  }
  const final = (i) => { let x = i; while (refaz.has(x)) x = refaz.get(x); return x; };
  const usadas = faces.filter((f, i) => !tira.has(i)).map(f => f.map(final));
  // compacta os vértices
  const novo = new Map(), vs = [];
  const fs = usadas.map(f => f.map(i => {
    if (!novo.has(i)) { novo.set(i, vs.length); vs.push(vertices[i]); }
    return novo.get(i);
  }));
  return { vertices: vs, faces: fs, emendas: tira.size / 2 };
}

/** As barras retas numa só: mesmo perfil e rotação, na mesma reta (até 1 mm). null se não dá. */
export function juntarBarras(barras, tol = 1.0) {
  if (!barras.length) return null;
  const b0 = barras.reduce((a, b) => (norma(sub(b.fim, b.inicio)) > norma(sub(a.fim, a.inicio)) ? b : a));
  const d = unit(sub(b0.fim, b0.inicio));
  const ts = [];
  for (const b of barras) {
    if (b.perfil !== b0.perfil || Math.abs((b.rotacao || 0) - (b0.rotacao || 0)) > 0.01) return null;
    for (const p of [b.inicio, b.fim]) {
      const v = sub(p, b0.inicio);
      const t = dot(v, d);
      if (norma(sub(v, d.map(x => x * t))) > tol) return null;
      ts.push(t);
    }
  }
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  return { inicio: b0.inicio.map((x, i) => x + d[i] * t0), fim: b0.inicio.map((x, i) => x + d[i] * t1), base: b0 };
}
