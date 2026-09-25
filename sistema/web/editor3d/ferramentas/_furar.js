// Furação na malha das peças: o que as ferramentas Furo e Parafuso usam.
//
// O furo é de verdade na malha: a face recebe o laço do furo costurado ao contorno (o
// mesmo formato dos furos do IFC do TecnoMETAL — o vértice da ponte repetido), a face de
// trás da parede também, e a parede ganha o tubo vazado. O detalhamento lê o laço redondo
// como furo e o laço em estádio como furo oblongo (saida/detalhamento._classificar_laco).
//
// `forma` = {d} para o redondo, ou {d, comp, dir} para o oblongo: `d` a largura (o
// diâmetro da broca), `comp` o comprimento total do rasgo e `dir` a direção dele no plano
// da face (a da peça ou a atravessada).

import * as C from './_comum.js';

//: lados do laço do furo redondo na malha (e de cada meia-volta do oblongo, com as pontas)
export const LADOS = 16;

export function dentroDoPoligono(pt, pts) {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

export function distPontoSegmento2d(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L2 = dx * dx + dy * dy;
  const t = L2 > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** É oblongo (o rasgo mais comprido que a largura)? */
export function ehOblongo(forma) {
  return !!(forma && forma.comp && forma.dir && forma.comp > forma.d + 0.5);
}

/** Rótulo do furo: "Ø13" ou "13 × 23" (largura × comprimento do oblongo). */
export function rotuloDaForma(forma) {
  const n = (x) => String(Math.round(x * 10) / 10).replace('.', ',');
  return ehOblongo(forma) ? `${n(forma.d)} × ${n(forma.comp)}` : `Ø${n(forma.d)}`;
}

/**
 * Pontos do laço no plano (u, v) da face: o círculo de LADOS lados, ou o estádio — meia-
 * volta em +a e meia-volta em -a ao longo de u, LADOS/2 + 1 pontos cada.
 */
export function lacoDaForma(forma) {
  const r = forma.d / 2;
  const pts = [];
  if (!ehOblongo(forma)) {
    for (let i = 0; i < LADOS; i++) {
      const t = (2 * Math.PI * i) / LADOS;
      pts.push([r * Math.cos(t), r * Math.sin(t)]);
    }
    return pts;
  }
  const a = (forma.comp - forma.d) / 2;
  const meio = LADOS / 2;
  for (let i = 0; i <= meio; i++) {
    const t = -Math.PI / 2 + (Math.PI * i) / meio;
    pts.push([a + r * Math.cos(t), r * Math.sin(t)]);
  }
  for (let i = 0; i <= meio; i++) {
    const t = Math.PI / 2 + (Math.PI * i) / meio;
    pts.push([-a + r * Math.cos(t), r * Math.sin(t)]);
  }
  return pts;
}

/** Base (u, v) do laço na face de normal `nf`: u na direção do oblongo (ou qualquer uma). */
function baseDoLaco(nf, forma) {
  let u = null;
  if (ehOblongo(forma)) {
    u = C.sub(forma.dir, C.mul(nf, C.dot(forma.dir, nf)));
    if (C.comp(u) < 1e-6) u = null;
  }
  u = C.normalizar(u || C.perpendicular(nf));
  const v = C.normalizar(C.cross(nf, u));
  return { u, v };
}

/**
 * A face da peça onde está o ponto: normal no sentido de `n`, plano passando pelo ponto e
 * o ponto dentro do contorno (fora dos furos que ela já tem). O índice que vem do clique é
 * o do triângulo da malha desenhada, não o da face da peça — só serve como palpite.
 */
export function faceDoPonto(ent, ponto, n, palpite = -1) {
  if (!ent || ent.tipo !== 'solido' || !ent.faces) return -1;
  const ordem = [];
  if (palpite >= 0 && ent.faces[palpite]) ordem.push(palpite);
  for (let k = 0; k < ent.faces.length; k++) if (k !== palpite) ordem.push(k);
  for (const k of ordem) {
    const f = ent.faces[k];
    if (!f || f.length < 3) continue;
    const nf = C.normalizar(C.normalDaFace(ent, k));
    if (!(C.comp(nf) > 0.5) || C.dot(nf, n) < 0.7) continue;
    if (Math.abs(C.dot(C.sub(ponto, ent.vertices[f[0]]), nf)) > 1.0) continue;
    const e1 = C.normalizar(C.perpendicular(nf)), e2 = C.normalizar(C.cross(nf, e1));
    const p2 = f.map(i => [C.dot(C.sub(ent.vertices[i], ponto), e1), C.dot(C.sub(ent.vertices[i], ponto), e2)]);
    if (dentroDoPoligono([0, 0], p2)) return k;
  }
  return -1;
}

/**
 * Abre o furo na malha: o laço costurado na face `iFace` e na face de trás da parede, e o
 * tubo entre elas. Devolve {vertices, faces, profundidade} (a malha nova, sem mexer em
 * `ent`) ou null — a face de trás não foi reconhecida, ou o furo não cabe na face (bate na
 * borda ou num furo que ela já tem).
 */
export function furarMalha(ent, iFace, ponto, n, forma) {
  if (!ent || ent.tipo !== 'solido' || !ent.faces || !ent.faces.length) return null;
  iFace = faceDoPonto(ent, ponto, n, iFace);
  if (!(iFace >= 0)) return null;
  const nf = C.normalizar(C.normalDaFace(ent, iFace));
  if (C.dot(nf, n) < 0.7) return null;
  const r = forma.d / 2;
  const { u, v } = baseDoLaco(nf, forma);
  const em2d = (q) => [C.dot(C.sub(q, ponto), u), C.dot(C.sub(q, ponto), v)];
  const poli = (f) => f.map(i => em2d(ent.vertices[i]));
  const frente = ent.faces[iFace];
  const p2 = poli(frente);
  // o eixo do furo (um ponto no redondo, o segmento central no oblongo) todo dentro da
  // face e a mais de r + 0,5 mm das bordas e dos furos que ela já tem
  const a = ehOblongo(forma) ? (forma.comp - forma.d) / 2 : 0;
  const amostras = a > 0 ? [-1, -0.5, 0, 0.5, 1].map(s => [s * a, 0]) : [[0, 0]];
  for (const q of amostras) {
    if (!dentroDoPoligono(q, p2)) return null;
    for (let i = 0; i < p2.length; i++) if (distPontoSegmento2d(q, p2[i], p2[(i + 1) % p2.length]) < r + 0.5) return null;
  }
  // a face de trás: paralela, olhando para o outro lado, logo atrás, com o eixo dentro dela
  let iTras = -1, prof = null;
  for (let k = 0; k < ent.faces.length; k++) {
    if (k === iFace || ent.faces[k].length < 3) continue;
    const nk = C.normalizar(C.normalDaFace(ent, k));
    if (C.dot(nk, nf) > -0.9) continue;
    const t = -C.dot(C.sub(ent.vertices[ent.faces[k][0]], ponto), nf);      // profundidade da face k
    if (!(t > 0.5) || t > 80) continue;
    const pk = poli(ent.faces[k]);
    if (!amostras.every(q => dentroDoPoligono(q, pk))) continue;
    if (prof === null || t < prof) { prof = t; iTras = k; }
  }
  if (iTras < 0) return null;
  const vertices = ent.vertices.map(q => q.slice());
  const faces = ent.faces.map(f => f.slice());
  const H = [], B = [];
  for (const [x, y] of lacoDaForma(forma)) {
    const h = C.add(ponto, C.add(C.mul(u, x), C.mul(v, y)));
    H.push(vertices.length); vertices.push(h);
    B.push(vertices.length); vertices.push(C.add(h, C.mul(nf, -prof)));
  }
  const costurar = (f, laco) => {
    // o laço gira ao contrário do contorno; a ponte sai do vértice do contorno mais perto
    const pts = poli(f);
    const horario = C.areaAssinada(pts) > 0;                      // contorno anti-horário → furo horário
    const ordem = horario ? laco.slice().reverse() : laco.slice();
    let k = 0, dm = Infinity;
    for (let i = 0; i < f.length; i++) { const dd = Math.hypot(pts[i][0], pts[i][1]); if (dd < dm) { dm = dd; k = i; } }
    const pk = vertices[f[k]];
    let j = 0; dm = Infinity;
    for (let i = 0; i < ordem.length; i++) { const dd = C.dist(vertices[ordem[i]], pk); if (dd < dm) { dm = dd; j = i; } }
    const giro = ordem.slice(j).concat(ordem.slice(0, j));
    return f.slice(0, k + 1).concat(giro, [giro[0], f[k]], f.slice(k + 1));
  };
  faces[iFace] = costurar(frente, H);
  faces[iTras] = costurar(ent.faces[iTras], B);
  const eixo = C.add(ponto, C.mul(nf, -prof / 2));
  const m = H.length;
  for (let i = 0; i < m; i++) {
    const j = (i + 1) % m;
    let q = [H[i], H[j], B[j], B[i]];
    const nq = C.normalDoContorno(q.map(k => vertices[k]));
    const cq = [0, 1, 2].map(ax => q.reduce((s, k) => s + vertices[k][ax], 0) / 4);
    // a normal olha para o vazio do furo (o eixo do oblongo é um segmento: o ponto dele
    // mais perto da parede)
    const e = a > 0 ? C.add(eixo, C.mul(u, Math.max(-a, Math.min(a, C.dot(C.sub(cq, eixo), u))))) : eixo;
    if (C.dot(nq, C.sub(e, cq)) < 0) q = [H[i], B[i], B[j], H[j]];
    faces.push(q);
  }
  return { vertices, faces, profundidade: prof };
}

/** O furo na chapa paramétrica (Chapa.furos: {x, y, diametro} ou {x, y, largura, altura}). */
export function furoNaChapa(chapa, ponto, forma) {
  const rel = C.sub(ponto, chapa.origem);
  const x = C.dot(rel, chapa.eixo_x), y = C.dot(rel, chapa.eixo_y);
  if (!ehOblongo(forma)) return { x, y, diametro: forma.d };
  const ax = Math.abs(C.dot(forma.dir, chapa.eixo_x)), ay = Math.abs(C.dot(forma.dir, chapa.eixo_y));
  if (ax >= ay) return { x, y, largura: forma.comp, altura: forma.d };
  return { x, y, largura: forma.d, altura: forma.comp };
}

/** Já há furo (da malha ou da chapa) a menos de `tol` mm do eixo, neste ponto da parede? */
function jaFurado(ent, ponto, eixo, tol) {
  if (ent.tipo === 'chapa') {
    const rel = C.sub(ponto, ent.origem);
    const x = C.dot(rel, ent.eixo_x), y = C.dot(rel, ent.eixo_y);
    return (ent.furos || []).some(f => Math.hypot(f.x - x, f.y - y) <= tol);
  }
  return false;
}

/**
 * Os furos que o corpo de um parafuso abre nas peças que ele atravessa: o eixo sai de
 * `ponto` (sob a cabeça) na direção `eixo` por `alcance` mm; em cada peça, cada parede
 * que o eixo cruza de frente (a face olhando para a cabeça) ganha o furo — a mesa do
 * banzo, a alma da terça e a chapa do suporte, na ordem. Onde a peça já tem furo no eixo
 * (o do IFC), nada muda. Devolve [{id, campos, rotulo, paredes}] para `cmdAlterar`.
 */
export function furosDoParafuso(documento, ponto, eixo, alcance, forma, ignorar = new Set(), parafuso = null) {
  const saida = [];
  if (!documento || !documento.entidades) return saida;
  const d = C.normalizar(eixo);
  const fim = C.add(ponto, C.mul(d, alcance));
  const lo = [0, 1, 2].map(i => Math.min(ponto[i], fim[i]) - 1);
  const hi = [0, 1, 2].map(i => Math.max(ponto[i], fim[i]) + 1);
  for (const e of documento.entidades.values()) {
    if (ignorar.has(e.id) || e.visivel === false) continue;
    if (e.tipo !== 'solido' && e.tipo !== 'chapa') continue;
    if (/^BOLT|PORCA|ARRUELA|TELHA|^FURO/i.test(e.nome || '') || e.camada === 'Parafusos' || e.camada === 'Telhas' || e.camada === 'Furos') continue;
    const pts = C.pontosDaEntidade(e);
    if (!pts.length) continue;
    const folga = e.tipo === 'chapa' ? (e.espessura || 10) : 0;
    const clo = [0, 1, 2].map(i => Math.min(...pts.map(q => q[i])) - folga);
    const chi = [0, 1, 2].map(i => Math.max(...pts.map(q => q[i])) + folga);
    if ([0, 1, 2].some(i => chi[i] < lo[i] || clo[i] > hi[i])) continue;
    if (e.tipo === 'chapa') {
      const nc = C.normalizar(C.cross(e.eixo_x, e.eixo_y));
      const den = C.dot(nc, d);
      if (Math.abs(den) < 0.7) continue;
      const t = C.dot(C.sub(e.origem, ponto), nc) / den;
      const esp = e.espessura || 10;
      if (t < -esp - 1 || t > alcance + esp) continue;
      const q = C.add(ponto, C.mul(d, t));
      const rel = C.sub(q, e.origem);
      const p2 = [C.dot(rel, e.eixo_x), C.dot(rel, e.eixo_y)];
      if (!e.contorno || e.contorno.length < 3 || !dentroDoPoligono(p2, e.contorno)) continue;
      if (jaFurado(e, q, d, Math.max(forma.d, 6) / 2)) continue;
      saida.push({ id: e.id, campos: { furos: [...(e.furos || []).map(f => ({ ...f })), furoNaChapa(e, q, forma)] }, paredes: 1 });
      continue;
    }
    // sólido: as faces que olham para a cabeça (normal contra o eixo) que o eixo cruza
    let atual = { tipo: 'solido', vertices: e.vertices, faces: e.faces };
    const entradas = [];
    for (let k = 0; k < e.faces.length; k++) {
      const f = e.faces[k];
      if (!f || f.length < 3) continue;
      const nf = C.normalizar(C.normalDaFace(e, k));
      if (C.dot(nf, d) > -0.9) continue;
      const t = C.dot(C.sub(e.vertices[f[0]], ponto), nf) / C.dot(d, nf);
      if (!(t > -2) || t > alcance) continue;
      entradas.push({ k, t });
    }
    entradas.sort((a, b) => a.t - b.t);
    let paredes = 0;
    const registros = [];
    for (const { k, t } of entradas) {
      const q = C.add(ponto, C.mul(d, t));
      const nIn = C.mul(d, -1);
      if (faceDoPonto(atual, q, nIn, k) !== k) continue;          // o eixo passa fora da face (ou num furo que ela já tem)
      const r = furarMalha(atual, k, q, nIn, forma);
      if (!r) continue;
      atual = { tipo: 'solido', vertices: r.vertices, faces: r.faces };
      paredes++;
      registros.push({ ...(parafuso ? { parafuso } : {}), d: forma.d, ...(ehOblongo(forma) ? { comp: forma.comp, dir: C.copiar(forma.dir) } : {}), ponto: C.copiar(q), eixo: C.copiar(d), profundidade: r.profundidade });
    }
    if (paredes) {
      const atributos = comMalhaBase(e, { ...(e.atributos || {}), furos_editor: [...((e.atributos && e.atributos.furos_editor) || []), ...registros] });
      saida.push({ id: e.id, campos: { vertices: atual.vertices, faces: atual.faces, atributos }, paredes });
    }
  }
  return saida;
}


/**
 * Atributos com a malha da peça **antes** do primeiro furo feito no editor
 * (`malha_sem_furos_editor`), guardada uma vez: com ela, os furos do editor podem ser
 * refeitos com outra medida (troca de parafuso) sem remendar a malha furada. Peça furada
 * por uma versão que não guardava fica sem (os furos dela não mudam de medida).
 */
export function comMalhaBase(ent, atributos) {
  const a = { ...atributos };
  const ja = ent.atributos && ent.atributos.furos_editor && ent.atributos.furos_editor.length;
  if (!a.malha_sem_furos_editor && !ja) {
    a.malha_sem_furos_editor = { vertices: ent.vertices.map(q => q.slice()), faces: ent.faces.map(f => f.slice()) };
  }
  return a;
}

/**
 * Refaz os furos do editor de uma peça a partir da malha guardada, com os registros
 * `registros` (os de sempre, com a medida trocada onde for o caso). Devolve {vertices,
 * faces, registros} ou null quando a peça não guardou a malha de antes.
 */
export function refazerFurosEditor(ent, registros) {
  const base = ent.atributos && ent.atributos.malha_sem_furos_editor;
  if (!base) return null;
  let atual = { tipo: 'solido', vertices: base.vertices, faces: base.faces };
  const feitos = [];
  for (const r of registros) {
    const nIn = C.mul(C.normalizar(r.eixo), -1);
    const forma = { d: r.d, ...(r.comp && r.dir ? { comp: r.comp, dir: r.dir } : {}) };
    const m = furarMalha(atual, -1, r.ponto, nIn, forma);
    if (!m) continue;                       // não cabe mais (furo maior que a parede): fica de fora
    atual = { tipo: 'solido', vertices: m.vertices, faces: m.faces };
    feitos.push({ ...r, profundidade: m.profundidade });
  }
  return { vertices: atual.vertices, faces: atual.faces, registros: feitos };
}

/**
 * Onde o eixo do parafuso/furo cruza as paredes das peças (as faces olhando para a
 * cabeça), de `ponto` na direção `eixo` até `alcance` mm: [{p, t, id}] — para a prévia
 * mostrar onde ele cai na peça de baixo.
 */
export function cruzamentosDoEixo(documento, ponto, eixo, alcance, ignorar = new Set(), caixaDe = null) {
  const saida = [];
  if (!documento || !documento.entidades) return saida;
  const d = C.normalizar(eixo);
  const fim = C.add(ponto, C.mul(d, alcance));
  const lo = [0, 1, 2].map(i => Math.min(ponto[i], fim[i]) - 1);
  const hi = [0, 1, 2].map(i => Math.max(ponto[i], fim[i]) + 1);
  for (const e of documento.entidades.values()) {
    if (ignorar.has(e.id) || e.visivel === false || e.tipo !== 'solido' || !e.faces) continue;
    if (/^BOLT|PORCA|ARRUELA|TELHA|^FURO/i.test(e.nome || '') || e.camada === 'Parafusos' || e.camada === 'Telhas' || e.camada === 'Furos') continue;
    const vs = e.vertices || [];
    if (!vs.length) continue;
    const cx = caixaDe ? caixaDe(e) : null;
    let fora = false;
    for (let i = 0; i < 3 && !fora; i++) {
      let mn = Infinity, mx = -Infinity;
      if (cx) { mn = cx[0][i]; mx = cx[1][i]; }
      else for (const q of vs) { if (q[i] < mn) mn = q[i]; if (q[i] > mx) mx = q[i]; }
      if (mx < lo[i] || mn > hi[i]) fora = true;
    }
    if (fora) continue;
    for (let k = 0; k < e.faces.length; k++) {
      const f = e.faces[k];
      if (!f || f.length < 3) continue;
      const nf = C.normalizar(C.normalDaFace(e, k));
      if (C.dot(nf, d) > -0.9) continue;
      const t = C.dot(C.sub(vs[f[0]], ponto), nf) / C.dot(d, nf);
      if (!(t > 0.5) || t > alcance) continue;
      const q = C.add(ponto, C.mul(d, t));
      if (faceDoPonto(e, q, C.mul(d, -1), k) === k) saida.push({ p: q, t, id: e.id });
    }
  }
  return saida.sort((a, b) => a.t - b.t);
}
