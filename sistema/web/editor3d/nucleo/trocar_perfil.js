// Troca do perfil de uma peça importada do IFC (sólido facetado), no próprio modelo.
//
// A peça do TecnoMETAL não é paramétrica: é uma malha. Para ela passar a ser, por exemplo,
// um C127X50X17X#14 em vez de C125X50X17X2.00, a malha é deformada na seção por faixas —
// espessura da mesa, enrijecedor, alma, na altura; espessura da alma e do enrijecedor, na
// largura —, com o comprimento intacto. Cada faixa vai para a sua medida nova, então as
// espessuras, as abas e os enrijecedores saem exatos; o que fica no meio da alma (furos)
// acompanha com a escala da faixa, que é de 1 ou 2 %. A face da alma fica no lugar (é ela
// que encosta no suporte) e a altura cresce igual para os dois lados.
//
// Por enquanto: U e Ue (C) formados a frio — os perfis de terça, longarina e banzo da
// treliça. Espessura por bitola: "#14" = 2,00 mm (a da fábrica: chapa a quente).

/** Bitolas de chapa (número → mm), como o comércio de aço usa no Brasil. */
export const BITOLAS = { 8: 4.25, 10: 3.35, 11: 3.0, 12: 2.65, 13: 2.25, 14: 2.0, 16: 1.5, 18: 1.2, 20: 0.9 };

/**
 * Nome de perfil → {familia: 'Ue'|'U', H, B, D, t, prefixo} ou null. Aceita a grafia do
 * TecnoMETAL (C125X50X17X2.00, U92X40X2.25), "Ue 127x50x17x1,90" e a bitola no lugar da
 * espessura (127X50X17X#14). Sem prefixo, 4 medidas = Ue e 3 = U.
 */
export function lerPerfil(nome) {
  const s = String(nome || '').toUpperCase().replace(/×/g, 'X').replace(/,/g, '.').replace(/\s+/g, '')
    .replace(/(\d)#/g, '$1X#');     // "17#14" = "17X#14" (a bitola colada na medida anterior)
  const m = s.match(/^([A-Z]*)(.*)$/);
  const prefixo = m[1];
  const partes = m[2].split('X').filter(p => p !== '');
  const nums = partes.map(p => {
    const g = p.match(/^#(\d+)$/);
    if (g) return BITOLAS[Number(g[1])] ?? NaN;
    return /^\d+(\.\d+)?$/.test(p) ? parseFloat(p) : NaN;
  });
  if (!nums.length || nums.some(v => !Number.isFinite(v) || v <= 0)) return null;
  if (['C', 'UE', ''].includes(prefixo) && nums.length === 4) {
    const [H, B, D, t] = nums;
    if (D <= t || 2 * D >= H) return null;
    return { familia: 'Ue', H, B, D, t, prefixo: prefixo || 'C' };
  }
  if (['U', ''].includes(prefixo) && nums.length === 3) {
    const [H, B, t] = nums;
    return { familia: 'U', H, B, D: 0, t, prefixo: 'U' };
  }
  return null;
}

/** Nome a gravar: o que foi digitado, em maiúsculas, com o prefixo da família do antigo. */
export function nomeDoPerfil(digitado, antigo) {
  const s = String(digitado || '').toUpperCase().replace(/×/g, 'X').replace(/\s+/g, '');
  if (/^[A-Z]/.test(s)) return s;
  const p = lerPerfil(antigo);
  return (p ? p.prefixo : '') + s;
}

// ------------------------------------------------------------------ álgebra

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const n = Math.hypot(a[0], a[1], a[2]); return n > 1e-12 ? [a[0] / n, a[1] / n, a[2] / n] : [0, 0, 0]; };

/** Centro e eixos principais (covariância, Jacobi), do maior para o menor. */
function eixosPrincipais(P) {
  const n = P.length, c = [0, 0, 0];
  for (const p of P) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  c[0] /= n; c[1] /= n; c[2] /= n;
  const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of P) {
    const d = sub(p, c);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) A[i][j] += d[i] * d[j];
  }
  const V = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let it = 0; it < 60; it++) {
    let p = 0, q = 1, m = Math.abs(A[0][1]);
    if (Math.abs(A[0][2]) > m) { p = 0; q = 2; m = Math.abs(A[0][2]); }
    if (Math.abs(A[1][2]) > m) { p = 1; q = 2; m = Math.abs(A[1][2]); }
    if (m < 1e-9) break;
    const th = 0.5 * Math.atan2(2 * A[p][q], A[q][q] - A[p][p]);
    const co = Math.cos(th), si = Math.sin(th);
    for (let k = 0; k < 3; k++) { const akp = A[k][p], akq = A[k][q]; A[k][p] = co * akp - si * akq; A[k][q] = si * akp + co * akq; }
    for (let k = 0; k < 3; k++) { const apk = A[p][k], aqk = A[q][k]; A[p][k] = co * apk - si * aqk; A[q][k] = si * apk + co * aqk; }
    for (let k = 0; k < 3; k++) { const vkp = V[k][p], vkq = V[k][q]; V[k][p] = co * vkp - si * vkq; V[k][q] = si * vkp + co * vkq; }
  }
  const ordem = [0, 1, 2].sort((i, j) => A[j][j] - A[i][i]);
  return { c, eixos: ordem.map(i => [V[0][i], V[1][i], V[2][i]]) };
}

/** Normal e área de cada face (polígono plano, leque). */
function facesComArea(P, faces) {
  return faces.map(f => {
    let s = [0, 0, 0];
    for (let i = 1; i + 1 < f.length; i++) {
      const cr = cross(sub(P[f[i]], P[f[0]]), sub(P[f[i + 1]], P[f[0]]));
      s = [s[0] + cr[0], s[1] + cr[1], s[2] + cr[2]];
    }
    const area = Math.hypot(s[0], s[1], s[2]) / 2;
    return { f, area, normal: norm(s) };
  });
}

/** Mapa linear por trechos: pontos `de` (crescentes) → `para`; fora, a translação da ponta. */
function porTrechos(de, para) {
  return (x) => {
    if (x <= de[0]) return para[0] + (x - de[0]);
    for (let i = 0; i + 1 < de.length; i++) {
      if (x <= de[i + 1]) {
        const k = de[i + 1] - de[i];
        return k > 1e-9 ? para[i] + (x - de[i]) * (para[i + 1] - para[i]) / k : para[i];
      }
    }
    return para[para.length - 1] + (x - de[de.length - 1]);
  };
}

/**
 * No trecho do meio de `de` → `para` (entre as duas metades da lista), troca a escala
 * uniforme por duas translações e uma rampa no maior intervalo sem vértices: o que está
 * de cada lado (furos) anda sem se deformar. Sem intervalo largo o bastante, fica a escala.
 */
function folgaNoMiolo(de, para, valores) {
  const i = de.length / 2 - 1;                 // o trecho do meio vai de de[i] a de[i + 1]
  const lo = de[i], hi = de[i + 1];
  const dentro = valores.filter(v => v > lo + 0.3 && v < hi - 0.3).sort((x, y) => x - y);
  const pontos = [lo, ...dentro, hi];
  let g0 = lo, g1 = lo;
  for (let k = 0; k + 1 < pontos.length; k++) if (pontos[k + 1] - pontos[k] > g1 - g0) { g0 = pontos[k]; g1 = pontos[k + 1]; }
  const desloc0 = para[i] - lo, desloc1 = para[i + 1] - hi;
  const n0 = g0 + desloc0 + 0.25, n1 = g1 + desloc1 - 0.25;     // a rampa, recuada dos vértices vizinhos
  if (!(n1 - n0 > 0.5) || g1 - g0 < 1.0) return;
  de.splice(i + 1, 0, g0 + 0.25, g1 - 0.25);
  para.splice(i + 1, 0, n0, n1);
}

/**
 * Vértices da peça `ent` (sólido com vertices/faces) com a seção do perfil `antigo` passada
 * para `novo` (resultados de lerPerfil, mesma família). Devolve {vertices} ou {erro}.
 */
export function trocarSecao(ent, antigo, novo) {
  const P = ent.vertices || [], F = ent.faces || [];
  if (P.length < 8 || !F.length) return { erro: 'a peça não tem malha para deformar' };
  if (!antigo || !novo) return { erro: 'perfil não reconhecido (use U ou Ue/C: 127X50X17X#14, U92X40X2.25)' };
  if (antigo.familia !== novo.familia) return { erro: `troca de família (${antigo.familia} → ${novo.familia}) não é feita na malha` };
  const { c, eixos } = eixosPrincipais(P);
  const e1 = norm(eixos[0]);
  // alma: a direção (perpendicular ao comprimento) com mais área de face — as duas faces
  // da alma; os enrijecedores são paralelos a ela, mas muito menores
  const fs = facesComArea(P, F);
  const cand = [];
  for (const x of fs) {
    if (x.area < 1e-6 || Math.abs(dot(x.normal, e1)) > 0.2) continue;
    const n = norm(sub(x.normal, e1.map(v => v * dot(x.normal, e1))));
    const g = cand.find(k => Math.abs(dot(k.n, n)) > 0.97);
    if (g) g.area += x.area; else cand.push({ n, area: x.area });
  }
  if (!cand.length) return { erro: 'não achei a alma da peça' };
  cand.sort((x, y) => y.area - x.area);
  const eb = cand[0].n;                     // normal da alma (direção da largura da mesa)
  const ea = norm(cross(e1, eb));           // direção da altura
  const loc = P.map(p => { const d = sub(p, c); return [dot(d, e1), dot(d, ea), dot(d, eb)]; });
  let aMin = Infinity, aMax = -Infinity, bMin = Infinity, bMax = -Infinity;
  for (const q of loc) { aMin = Math.min(aMin, q[1]); aMax = Math.max(aMax, q[1]); bMin = Math.min(bMin, q[2]); bMax = Math.max(bMax, q[2]); }
  const altura = aMax - aMin, largura = bMax - bMin;
  const tol = Math.max(4, 0.06 * antigo.H);
  if (Math.abs(altura - antigo.H) > tol || Math.abs(largura - antigo.B) > Math.max(4, 0.08 * antigo.B)) {
    return { erro: `a seção da peça (${altura.toFixed(1)} × ${largura.toFixed(1)} mm) não bate com ${antigo.familia} ${antigo.H}×${antigo.B}` };
  }
  // de que lado está a alma: média (por área) da largura das faces paralelas à alma
  let sa = 0, sb = 0;
  for (const x of fs) {
    if (Math.abs(dot(x.normal, eb)) < 0.97) continue;
    const cf = x.f.reduce((s, i) => s + loc[i][2], 0) / x.f.length;
    sa += x.area; sb += x.area * cf;
  }
  const almaEmBaixo = sa > 0 ? (sb / sa) < (bMin + bMax) / 2 : true;
  // espessura de verdade da malha (a face interna da mesa): o nome pode dizer outra coisa —
  // peça trocada quando #14 era 1,90; refazer a troca para o mesmo nome corrige a espessura
  const acima = loc.map(q => q[1] - aMin).filter(v => v > 0.3 && v > 0.5 * antigo.t && v < 1.6 * antigo.t);
  if (acima.length) antigo = { ...antigo, t: Math.min(...acima) };
  // altura: centro fixo; faixas da mesa (t) e do enrijecedor (D) em cada lado
  const novaAltura = altura + (novo.H - antigo.H);
  const aC = (aMin + aMax) / 2, a0 = aC - novaAltura / 2, a1 = aC + novaAltura / 2;
  const deA = [aMin, aMin + antigo.t], paraA = [a0, a0 + novo.t];
  if (antigo.familia === 'Ue') { deA.push(aMin + antigo.D, aMax - antigo.D); paraA.push(a0 + novo.D, a1 - novo.D); }
  deA.push(aMax - antigo.t, aMax); paraA.push(a1 - novo.t, a1);
  // largura: a face da alma fica; faixas da alma e do enrijecedor (espessura t)
  const novaLargura = largura + (novo.B - antigo.B);
  const b0 = almaEmBaixo ? bMin : bMax - novaLargura, b1 = b0 + novaLargura;
  const deB = [bMin, bMin + antigo.t, bMax - antigo.t, bMax], paraB = [b0, b0 + novo.t, b1 - novo.t, b1];
  // o esticamento do miolo (alma na altura, mesa na largura) vai para o maior trecho
  // vazio de vértices: os furos só se deslocam, sem mudar de tamanho
  folgaNoMiolo(deA, paraA, loc.map(q => q[1]));
  folgaNoMiolo(deB, paraB, loc.map(q => q[2]));
  const fa = porTrechos(deA, paraA), fb = porTrechos(deB, paraB);
  const vertices = loc.map(([u, a, b]) => {
    const a2 = fa(a), b2 = fb(b);
    return [c[0] + e1[0] * u + ea[0] * a2 + eb[0] * b2,
            c[1] + e1[1] * u + ea[1] * a2 + eb[1] * b2,
            c[2] + e1[2] * u + ea[2] * a2 + eb[2] * b2];
  });
  return { vertices };
}
