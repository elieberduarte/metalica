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

/** Interseções da reta (x + s·dx, y + s·dy) com um polígono fechado: os valores de s. */
export function cortesDaReta(x, y, dx, dy, pts) {
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length];
    const ex = bx - ax, ey = by - ay;
    const den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-12) continue;
    const s = ((ax - x) * ey - (ay - y) * ex) / den;
    const r = ((ax - x) * dy - (ay - y) * dx) / den;
    if (r >= -1e-9 && r < 1 - 1e-9) out.push(s);
  }
  return out;
}

/** Peça que o parafuso não aperta (o próprio fixador, a telha, o marcador de furo). */
export function foraDoPacote(e) {
  return /^BOLT|PORCA|ARRUELA|TELHA|^FURO/i.test(e.nome || '') || e.camada === 'Parafusos' || e.camada === 'Telhas'
    || e.camada === 'Furos';
}

/**
 * Índice das caixas envolventes das peças, para as ferramentas que olham o modelo inteiro a cada movimento do mouse
 * (Parafuso, Furo): montado uma vez, numa grade de 2 m; a peça que muda (outro objeto no documento) é refeita na
 * consulta. No PRATI CD (27 mil peças) cada movimento levava 160–180 ms varrendo tudo (revisão 14/10).
 */
export class IndiceDeCaixas {
  constructor(documento, { passo = 2000, folgaBarra = 0 } = {}) {
    this.documento = documento;
    this.passo = passo;
    this.folgaBarra = folgaBarra;
    this.caixas = new Map();        // id → {ent, caixa}
    this.grade = new Map();         // "i,j,k" → Set(id)
    this.grandes = new Set();       // as que ocupam células demais: sempre conferidas
    this.n = -1;
  }

  /** Caixa [lo, hi] da peça (a barra só tem as pontas: a seção entra como folga). */
  caixaDe(e) {
    const r = this.caixas.get(e.id);
    if (r && r.ent === e) return r.caixa;
    const pts = C.pontosDaEntidade(e);
    if (!pts.length) return null;
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (const q of pts) for (let i = 0; i < 3; i++) { if (q[i] < lo[i]) lo[i] = q[i]; if (q[i] > hi[i]) hi[i] = q[i]; }
    const folga = e.tipo === 'barra' ? this.folgaBarra : (e.tipo === 'chapa' ? (e.espessura || 10) : 0);
    const caixa = [lo.map(v => v - folga), hi.map(v => v + folga)];
    this.caixas.set(e.id, { ent: e, caixa });
    return caixa;
  }

  _celulas(caixa) {
    const p = this.passo;
    const a = caixa[0].map(v => Math.floor(v / p)), b = caixa[1].map(v => Math.floor(v / p));
    const n = (b[0] - a[0] + 1) * (b[1] - a[1] + 1) * (b[2] - a[2] + 1);
    return { a, b, n };
  }

  _montar() {
    this.grade.clear(); this.grandes.clear();
    for (const e of this.documento.entidades.values()) {
      if (e.visivel === false) continue;
      const c = this.caixaDe(e);
      if (!c) continue;
      const { a, b, n } = this._celulas(c);
      if (n > 64) { this.grandes.add(e.id); continue; }
      for (let i = a[0]; i <= b[0]; i++) for (let j = a[1]; j <= b[1]; j++) for (let k = a[2]; k <= b[2]; k++) {
        const ch = `${i},${j},${k}`;
        let s = this.grade.get(ch);
        if (!s) this.grade.set(ch, s = new Set());
        s.add(e.id);
      }
    }
    this.n = this.documento.entidades.size;
  }

  /** As peças cuja caixa encosta na caixa [lo, hi] (com `folga` mm), como um "documento" para as funções daqui. */
  perto(lo, hi, folga = 0) {
    if (this.n !== this.documento.entidades.size) this._montar();
    const q = [lo.map(v => v - folga), hi.map(v => v + folga)];
    const { a, b, n } = this._celulas(q);
    const ids = new Set(this.grandes);
    if (n > 4096) for (const id of this.documento.entidades.keys()) ids.add(id);
    else {
      for (let i = a[0]; i <= b[0]; i++) for (let j = a[1]; j <= b[1]; j++) for (let k = a[2]; k <= b[2]; k++) {
        const s = this.grade.get(`${i},${j},${k}`);
        if (s) for (const id of s) ids.add(id);
      }
    }
    const mapa = new Map();
    for (const id of ids) {
      const e = this.documento.get(id);
      if (!e || e.visivel === false) continue;
      // a peça mudou desde a montagem (outro objeto): refaz a caixa e confere de novo
      const c = this.caixaDe(e);
      if (!c || [0, 1, 2].some(i => c[1][i] < q[0][i] || c[0][i] > q[1][i])) continue;
      mapa.set(id, e);
    }
    return { entidades: mapa, get: (id) => this.documento.get(id), aparece: (e) => !this.documento.aparece || this.documento.aparece(e) };
  }

  /** Esquece a grade (o documento mudou de tamanho é conferido sozinho; isto é para a mudança no lugar). */
  invalidar() { this.n = -1; }
}

/**
 * As paredes que o eixo atravessa, como trechos [t0, t1] ao longo dele (t a partir de `ponto`, na direção `eixo`): no
 * sólido, a face de entrada e a de saída de cada parede (as faces de frente para o eixo, com o ponto dentro do contorno);
 * na chapa paramétrica, as duas faces dela; na barra do catálogo, a seção do perfil cortada pelo eixo.
 * `caixaDe(e)` (opcional) é a caixa envolvente guardada; `cena` dá a seção das barras.
 */
export function paredesNoEixo(documento, ponto, eixo, alcance, { cena = null, caixaDe = null, ignorar = new Set() } = {}) {
  const saida = [];
  if (!documento || !documento.entidades) return saida;
  const d = C.normalizar(eixo);
  const fim = C.add(ponto, C.mul(d, alcance));
  const lo = [0, 1, 2].map(i => Math.min(ponto[i], fim[i]) - 1);
  const hi = [0, 1, 2].map(i => Math.max(ponto[i], fim[i]) + 1);
  for (const e of documento.entidades.values()) {
    if (ignorar.has(e.id) || e.visivel === false || foraDoPacote(e)) continue;
    if (e.tipo !== 'solido' && e.tipo !== 'chapa' && e.tipo !== 'barra') continue;
    const cx = caixaDe ? caixaDe(e) : null;
    if (cx && e.tipo !== 'barra' && [0, 1, 2].some(i => cx[1][i] < lo[i] || cx[0][i] > hi[i])) continue;
    if (e.tipo === 'chapa') {
      const n = C.normalizar(C.cross(e.eixo_x, e.eixo_y));
      const den = C.dot(n, d);
      if (Math.abs(den) < 0.3 || !e.contorno || e.contorno.length < 3) continue;
      const esp = e.espessura || 0;
      const z0 = e.centrada === false ? 0 : -esp / 2;
      const ta = C.dot(C.sub(C.add(e.origem, C.mul(n, z0)), ponto), n) / den;
      const tb = C.dot(C.sub(C.add(e.origem, C.mul(n, z0 + esp)), ponto), n) / den;
      const t0 = Math.min(ta, tb), t1 = Math.max(ta, tb);
      if (t1 < -1 || t0 > alcance) continue;
      const rel = C.sub(C.add(ponto, C.mul(d, (t0 + t1) / 2)), e.origem);
      if (!dentroDoPoligono([C.dot(rel, e.eixo_x), C.dot(rel, e.eixo_y)], e.contorno)) continue;
      saida.push({ id: e.id, t0, t1 });
      continue;
    }
    if (e.tipo === 'barra') {
      if (!cena || typeof cena._secaoDoPerfil !== 'function' || !e.inicio || !e.fim) continue;
      // o perfil que ainda não chegou do servidor tem a seção provisória (um retângulo cheio): ela leria parede maciça
      if (typeof cena.perfil === 'function' && !cena.perfil(e.perfil)) continue;
      // longe do eixo do parafuso: nem calcula (a seção cabe em 400 mm)
      const blo = [0, 1, 2].map(i => Math.min(e.inicio[i], e.fim[i]) - 400), bhi = [0, 1, 2].map(i => Math.max(e.inicio[i], e.fim[i]) + 400);
      if ([0, 1, 2].some(i => hi[i] < blo[i] || lo[i] > bhi[i])) continue;
      let forma = null;
      try { forma = cena._secaoDoPerfil(e.perfil); } catch { forma = null; }
      if (!forma || typeof forma.getPoints !== 'function') continue;
      const { t, u, v } = baseDaBarraLocal(e);
      const rel = C.sub(ponto, e.inicio);
      const x = C.dot(rel, u), y = C.dot(rel, v), z = C.dot(rel, t);
      const dx = C.dot(d, u), dy = C.dot(d, v), dz = C.dot(d, t);
      if (Math.hypot(dx, dy) < 0.3) continue;
      const poligonos = [forma.getPoints().map(q => [q.x, q.y]), ...(forma.holes || []).map(h => h.getPoints().map(q => [q.x, q.y]))];
      const ss = poligonos.flatMap(pts => cortesDaReta(x, y, dx, dy, pts)).sort((a, b) => a - b);
      const comp = C.dist(e.inicio, e.fim);
      for (let i = 0; i + 1 < ss.length; i += 2) {
        const s0 = ss[i], s1 = ss[i + 1];
        if (s1 < -1 || s0 > alcance || s1 - s0 < 0.2) continue;
        const zq = z + dz * (s0 + s1) / 2;
        if (zq < (e.recorte_inicio || 0) - 1 || zq > comp - (e.recorte_fim || 0) + 1) continue;
        saida.push({ id: e.id, t0: s0, t1: s1 });
      }
      continue;
    }
    // sólido: os planos das faces de frente para o eixo, com o ponto dentro da face
    if (!cx) {
      const vs = e.vertices || [];
      if (!vs.length) continue;
      let fora = false;
      for (let i = 0; i < 3 && !fora; i++) {
        let mn = Infinity, mx = -Infinity;
        for (const q of vs) { if (q[i] < mn) mn = q[i]; if (q[i] > mx) mx = q[i]; }
        if (mx < lo[i] || mn > hi[i]) fora = true;
      }
      if (fora) continue;
    }
    const cortes = [];
    for (let k = 0; k < (e.faces || []).length; k++) {
      const f = e.faces[k];
      if (!f || f.length < 3) continue;
      const nf = C.normalizar(C.normalDaFace(e, k));
      const c = C.dot(nf, d);
      if (Math.abs(c) < 0.9) continue;
      const t = C.dot(C.sub(e.vertices[f[0]], ponto), nf) / c;
      if (t < -1 || t > alcance + 1) continue;
      const q = C.add(ponto, C.mul(d, t));
      if (faceDoPonto(e, q, nf, k) !== k) continue;
      cortes.push({ t, entra: c < 0 });
    }
    cortes.sort((a, b) => a.t - b.t);
    for (let i = 0; i < cortes.length; i++) {
      if (!cortes[i].entra) continue;
      let j = i + 1;
      while (j < cortes.length && cortes[j].entra) j++;
      if (j >= cortes.length) break;
      saida.push({ id: e.id, t0: cortes[i].t, t1: cortes[j].t });
      i = j;
    }
  }
  return saida.sort((a, b) => a.t0 - b.t0);
}

/**
 * O pacote que o parafuso aperta: as paredes em sequência a partir da cabeça (t = 0), cada uma encostada na anterior
 * (folga de até `folga` mm — a tolerância da montagem). Devolve {pega, paredes} ou null quando a cabeça não encosta em
 * nada. A pega é a espessura do pacote: onde ficam a arruela e a porca.
 */
export function pacoteDoEixo(documento, ponto, eixo, alcance, opcoes = {}) {
  const folga = opcoes.folga == null ? 3 : opcoes.folga;
  // parede mais grossa que isso não é chapa nem mesa: o eixo está correndo DENTRO de uma parede (no meio da mesa do I,
  // em cima da alma) — o parafuso não tem como passar (revisão 14/10: saía um M12x290 atravessando a viga inteira)
  const paredeMax = opcoes.paredeMax == null ? 60 : opcoes.paredeMax;
  const paredes = paredesNoEixo(documento, ponto, eixo, alcance, opcoes);
  let fim = 0;
  const usadas = [];
  let bloqueio = null;
  for (const p of paredes) {
    if (p.t1 <= fim + 0.05) continue;                    // dentro do que já está no pacote
    if (p.t0 > fim + folga) break;                       // depois de um vão: o pacote acabou (o miolo do perfil)
    if (p.t1 - Math.max(p.t0, fim) > paredeMax) { bloqueio = { id: p.id, t: Math.max(p.t0, fim) }; break; }
    fim = Math.max(fim, p.t1);
    usadas.push(p);
  }
  return usadas.length || bloqueio ? { pega: fim, paredes: usadas, bloqueio } : null;
}

//: o que se soma à pega para achar o comprimento (uma arruela, a porca e a ponta para fora), por diâmetro nominal, mm —
//: o "length addition" da tabela 7-15 do Manual do AISC (1/2" 11/16", 5/8" 7/8", 3/4" 1", 7/8" 1 1/8", 1" 1 1/4"),
//: levado ao métrico
const ACRESCIMO = { 8: 13, 10: 15, 12: 17.5, 14: 20, 16: 22, 18: 24.5, 20: 26.5, 22: 28.5, 24: 31, 27: 34, 30: 37.5 };

/**
 * Comprimento comercial do parafuso para a pega: pega + acréscimo (arruela + porca + ponta para fora), arredondado
 * para cima de 5 em 5 mm (de 10 em 10 acima de 100). M12 com pega de 16 → 33,5 → 35.
 */
export function comprimentoPelaPega(d, pega) {
  const ac = ACRESCIMO[Math.round(d)] || 1.3 * d + 2;
  const bruto = pega + ac;
  const m = bruto > 100 ? 10 : 5;
  return Math.max(20, Math.ceil(bruto / m - 1e-6) * m);
}

// a base da barra (a mesma de documento.baseDaBarra), sem importar o núcleo aqui
function baseDaBarraLocal(b) {
  const t = C.normalizar(C.sub(b.fim, b.inicio));
  const ref = Math.abs(t[2]) >= 0.9 ? [1, 0, 0] : [0, 0, 1];
  let u = C.normalizar(C.cross(ref, t));
  let v = C.normalizar(C.cross(t, u));
  const r = (b.rotacao || 0) * Math.PI / 180;
  if (r) {
    const c = Math.cos(r), s = Math.sin(r);
    const u2 = C.add(C.mul(u, c), C.mul(v, s)), v2 = C.add(C.mul(v, c), C.mul(u, -s));
    u = u2; v = v2;
  }
  return { t, u, v };
}
