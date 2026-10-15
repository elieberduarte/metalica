// O perfil que veio do IFC como malha (o sólido extrudado do TecnoMETAL, do Revit, do Tekla): o eixo e a seção lidos
// dos vértices, para o Virar e o Encaixar trabalharem nele como na barra do catálogo (revisão 14/10: as duas
// ferramentas recusavam a malha e mandavam usar o Girar ou o Empurrar).
//
// O eixo é o maior dos eixos principais; o centro é o meio da caixa da seção (não a média dos vértices — no U ela cai
// na alma): virado 180°, o U troca a boca de lado no mesmo lugar.

import * as C from './_comum.js';
import { eixosPrincipais } from './parafuso.js';

/** Normal de uma face pelos vértices (Newell), unitária, ou null na face degenerada. */
function normalDaFace(vs, f) {
  const n = [0, 0, 0];
  for (let i = 0; i < f.length; i++) {
    const a = vs[f[i]], b = vs[f[(i + 1) % f.length]];
    n[0] += (a[1] - b[1]) * (a[2] + b[2]);
    n[1] += (a[2] - b[2]) * (a[0] + b[0]);
    n[2] += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const k = C.comp(n);
  return k > 1e-9 ? C.mul(n, 1 / k) : null;
}

/**
 * O quadro da malha comprida: {eixo, u, v, centro, t0, t1, largura, altura} — `centro` no eixo, na altura de t = 0;
 * t0/t1 são as pontas ao longo do eixo. null quando a peça não é comprida (a chapa, o nó, a porca).
 */
export function quadroDaMalha(ent) {
  const vs = ent && ent.tipo === 'solido' && Array.isArray(ent.vertices) ? ent.vertices : null;
  if (!vs || vs.length < 6 || !Array.isArray(ent.faces) || !ent.faces.length) return null;
  if (ent.atributos && (ent.atributos.cota || ent.atributos.furo || ent.atributos.parafuso)) return null;
  const eixos = eixosPrincipais(vs);
  const faixa = eixos.map(ax => {
    let lo = Infinity, hi = -Infinity;
    for (const q of vs) { const t = C.dot(q, ax); if (t < lo) lo = t; if (t > hi) hi = t; }
    return { ax, lo, hi, ext: hi - lo };
  }).sort((a, b) => b.ext - a.ext);
  const [L, A, B] = faixa;
  if (!(L.ext > 2.5 * Math.max(A.ext, B.ext, 1))) return null;
  const eixo = C.normalizar(L.ax);
  // u e v: os outros dois eixos, de mão direita com o eixo
  const u = C.normalizar(A.ax);
  const v = C.normalizar(C.cross(eixo, u));
  let vlo = Infinity, vhi = -Infinity;
  for (const q of vs) { const t = C.dot(q, v); if (t < vlo) vlo = t; if (t > vhi) vhi = t; }
  const centro = C.add(C.mul(u, (A.lo + A.hi) / 2), C.mul(v, (vlo + vhi) / 2));   // t = 0 no eixo
  return { eixo, u, v, centro, t0: L.lo, t1: L.hi, largura: A.ext, altura: vhi - vlo };
}

/** Gira a malha `ang` graus no próprio eixo: {fp, fv} para C.camposTransformados. */
export function giroNoEixo(q, ang) {
  const a = ang * Math.PI / 180, c = Math.cos(a), s = Math.sin(a), k = q.eixo;
  const R = (w) => C.add(C.add(C.mul(w, c), C.mul(C.cross(k, w), s)), C.mul(k, C.dot(k, w) * (1 - c)));
  const O = q.centro;
  return { fp: (p) => C.add(O, R(C.sub(p, O))), fv: R };
}

/** O contorno da caixa da seção girada de `ang`, na altura do eixo mais perto de `ponto` (a prévia do Virar). */
export function caixaDaSecao(q, ponto, ang = 0) {
  const t = Math.max(q.t0, Math.min(q.t1, C.dot(ponto, q.eixo)));
  const O = C.add(q.centro, C.mul(q.eixo, t));
  const { fv } = giroNoEixo(q, ang);
  const u = fv(q.u), v = fv(q.v), a = q.largura / 2, b = q.altura / 2;
  return [[-a, -b], [a, -b], [a, b], [-a, b]].map(([x, y]) => C.add(O, C.add(C.mul(u, x), C.mul(v, y))));
}

/**
 * Os vértices da malha com a ponta mais perto do plano (P, n) levada até ele: os vértices da tampa da ponta (as faces
 * de frente para o eixo, na metade daquela ponta) andam ao longo do eixo até o plano — corta em ângulo ou estica, e as
 * faces dos lados acompanham. {vertices, ponta} ou {erro}: o plano corre ao longo da peça, a ponta não é um corte só
 * (tem recorte, é um bico), ou a ponta nova passaria por um furo ou comeria a peça.
 */
export function encaixeDaMalha(vs, faces, q, P, n) {
  n = C.normalizar(n);
  const d = q.eixo;
  const den = C.dot(d, n);
  if (Math.abs(den) < 0.1) return { erro: 'Essa face corre ao longo da peça: não corta a ponta. Escolha a face em que ela chega' };
  const tP = (t) => C.add(q.centro, C.mul(d, t));
  const ponta = Math.abs(C.dot(C.sub(tP(q.t0), P), n)) <= Math.abs(C.dot(C.sub(tP(q.t1), P), n)) ? 'inicio' : 'fim';
  const s = ponta === 'fim' ? 1 : -1;
  const meio = (q.t0 + q.t1) / 2;
  const naPonta = (i) => (C.dot(vs[i], d) - meio) * s > 0;
  const tampa = new Set();
  for (const f of faces) {
    if (!f || f.length < 3 || !f.every(naPonta)) continue;
    const nf = normalDaFace(vs, f);
    if (nf && Math.abs(C.dot(nf, d)) > 0.1) for (const i of f) tampa.add(i);
  }
  if (!tampa.size) return { erro: 'Não achei a tampa da ponta dessa malha' };
  // a malha com os vértices repetidos por face (comum no IFC): as cópias da tampa nas faces dos lados andam junto
  const chave = (p) => p.map(x => Math.round(x * 100)).join(',');
  const naTampa = new Set([...tampa].map(i => chave(vs[i])));
  for (let i = 0; i < vs.length; i++) if (!tampa.has(i) && naTampa.has(chave(vs[i]))) tampa.add(i);
  // a tampa tem de ser um plano só (o corte reto ou em ângulo): o recorte de encaixe e o bico ficam como estão
  const lista = [...tampa];
  let nt = null;
  for (const f of faces) {
    if (f && f.length >= 3 && f.every(i => tampa.has(i))) { nt = normalDaFace(vs, f); if (nt) break; }
  }
  const p0 = vs[lista[0]];
  if (!nt || lista.some(i => Math.abs(C.dot(C.sub(vs[i], p0), nt)) > 0.5)) {
    return { erro: 'A ponta dessa malha não é um corte só (tem recorte ou bico): o Encaixar ajusta na malha só a ponta reta ou em ângulo' };
  }
  const novos = vs.map(p => p.slice());
  for (const i of lista) novos[i] = C.add(vs[i], C.mul(d, C.dot(C.sub(P, vs[i]), n) / den));
  // a ponta nova não pode passar da outra ponta nem deixar para fora um furo ou recorte do miolo
  const fora = (p) => C.dot(C.sub(p, P), n) * (C.dot(d, n) * s) > 0.5;          // além do plano, do lado de fora
  const outra = vs.reduce((m, p, i) => (tampa.has(i) ? m : Math.max(m, C.dot(p, d) * s)), -Infinity);
  for (const i of lista) if (C.dot(novos[i], d) * s < outra + 1) return { erro: 'Esse corte comeria a peça inteira: escolha outra face' };
  for (let i = 0; i < vs.length; i++) {
    if (!tampa.has(i) && fora(vs[i])) return { erro: 'A ponta nova passaria por um furo ou recorte da peça: ajuste a malha à mão (Empurrar/Puxar)' };
  }
  return { vertices: novos, ponta };
}
