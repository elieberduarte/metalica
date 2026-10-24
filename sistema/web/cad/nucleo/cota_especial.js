// As cotas angular, de raio, de diâmetro e ordenada (pedido do usuário, 23/10, na lista das ferramentas que faltam: "a
// inclinação da diagonal e da mão-francesa, o recorte em raio, o Ø do furo"; a ordenada, a furação medida de uma borda).
// Espelho de nucleo2d/cota_especial.py: a mesma conta dá o que se desenha (linhas, arcos, pontas e o número), na tela, no
// PDF e no DXF — test_cota_especial.py roda as duas e compara.
//
// A entidade `cota_especial`: modo (angular | raio | diametro | ordenada), centro (o vértice do ângulo, o centro do
// círculo, a origem da ordenada), p1 (o ponto no primeiro lado / no círculo / o ponto medido), p2 (o ponto no segundo
// lado do ângulo), posicao (por onde passa o arco do ângulo / onde fica o número), eixo (x | y, da ordenada), texto
// (vazio = a medida), altura, casas, escala (o número por mm desenhado), fator, terminador, folga.

import { folgaDaCota, formatarMm } from './desenho2d.js';

const RAD = Math.PI / 180;
const n360 = (g) => ((g % 360) + 360) % 360;
const angDe = (a, b) => n360(Math.atan2(b[1] - a[1], b[0] - a[0]) / RAD);
const pol = (c, g, r) => [c[0] + r * Math.cos(g * RAD), c[1] + r * Math.sin(g * RAD)];
const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** O ângulo da cota angular: o setor de p1 a p2 (anti-horário) que contém a posição, ou o outro. */
function setorAngular(c) {
  const a1 = angDe(c.centro, c.p1), a2 = angDe(c.centro, c.p2), ap = angDe(c.centro, c.posicao);
  const s12 = n360(a2 - a1);
  return n360(ap - a1) <= s12 ? { ini: a1, varre: s12 } : { ini: a2, varre: 360 - s12 };
}

/** O número escrito (sem o texto posto à mão). */
export function medidaDaCotaEspecial(c) {
  const e = c.escala || 1;
  if (c.modo === 'angular') {
    const v = setorAngular(c).varre;
    return (c.casas != null && c.casas !== '' ? v.toFixed(+c.casas) : Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1)).replace('.', ',') + '°';
  }
  if (c.modo === 'raio') return 'R' + formatarMm(dist(c.centro, c.p1) * e, c.casas);
  if (c.modo === 'diametro') return 'Ø' + formatarMm(2 * dist(c.centro, c.p1) * e, c.casas);
  const i = c.eixo === 'y' ? 1 : 0;
  return formatarMm(Math.abs(c.p1[i] - c.centro[i]) * e, c.casas);
}

/** O ângulo do texto lido de baixo para cima ou da esquerda para a direita: (graus, virou). */
function legivel(g) { g = n360(g); return g > 90 && g <= 270 ? [g - 180, true] : [g > 270 ? g - 360 : g, false]; }

/**
 * O que a cota desenha, em mm do desenho: {linhas: [[a, b]], arcos: [{centro, raio, inicio, fim}], pontas: [{p, ang
 * (graus, para onde a ponta aponta), tam, tipo}], textos: [{pos, txt, h, ang (graus), alinhamento}]}. `k` é a escala do
 * desenho (mm de papel → mm), `estilo` o metadados.estilo (a folga e o terminador padrão).
 */
export function primitivasDaCotaEspecial(c, k = 1, estilo = null) {
  const f = c.fator || 1, h = (c.altura || 2.5) * k * f, seta = 2.5 * k * f, ext = 2 * k * f, fol = folgaDaCota(c, estilo) * k * f;
  const termo = c.terminador || (estilo && estilo.terminador) || 'traco';
  const txt = c.texto != null && c.texto !== '' ? String(c.texto) : medidaDaCotaEspecial(c);
  const larg = Math.max(h, txt.length * h * 0.62);
  const out = { linhas: [], arcos: [], pontas: [], textos: [] };
  const C = c.centro;
  if (c.modo === 'angular') {
    const { ini, varre } = setorAngular(c), fim = ini + varre;
    const r = Math.max(dist(C, c.posicao), 3 * seta);
    for (const [p, g] of [[c.p1, angDe(C, c.p1)], [c.p2, angDe(C, c.p2)]]) {
      // a chamada até o arco, quando o ponto do lado fica aquém dele
      const d = dist(C, p);
      if (d < r - 1e-9) out.linhas.push([pol(C, g, d + fol), pol(C, g, r + ext)]);
    }
    out.arcos.push({ centro: C, raio: r, inicio: n360(ini), fim: n360(fim) });
    out.pontas.push({ p: pol(C, ini, r), ang: ini - 90, tam: seta, tipo: termo }, { p: pol(C, fim, r), ang: fim + 90, tam: seta, tipo: termo });
    const meio = ini + varre / 2;
    const [g, virou] = legivel(meio - 90);
    out.textos.push({ pos: pol(C, meio, r + fol + (virou ? h : 0)), txt, h, ang: g, alinhamento: 'centro' });
    return out;
  }
  if (c.modo === 'raio' || c.modo === 'diametro') {
    const R = dist(C, c.p1), u = angDe(C, c.posicao), dP = dist(C, c.posicao);
    const P1 = pol(C, u, R), P2 = pol(C, u + 180, R);
    const ponta = termo === 'traco' ? 'seta' : termo;          // o traço oblíquo não se lê no raio: a seta
    const ini = c.modo === 'raio' ? C : P2;
    if (dP > R + 1e-9) {
      // o número por fora: a linha até a posição e o patamar dele
      const dir = c.posicao[0] >= C[0] ? 1 : -1;
      out.linhas.push([c.modo === 'raio' ? P1 : P2, c.posicao], [c.posicao, [c.posicao[0] + dir * (larg + 2 * fol), c.posicao[1]]]);
      out.pontas.push({ p: P1, ang: u + 180, tam: seta, tipo: ponta });
      if (c.modo === 'diametro') out.pontas.push({ p: P2, ang: u, tam: seta, tipo: ponta });
      out.textos.push({ pos: [c.posicao[0] + dir * (fol + larg / 2), c.posicao[1] + fol], txt, h, ang: 0, alinhamento: 'centro' });
    } else {
      out.linhas.push([ini, P1]);
      out.pontas.push({ p: P1, ang: u, tam: seta, tipo: ponta });
      if (c.modo === 'diametro') out.pontas.push({ p: P2, ang: u + 180, tam: seta, tipo: ponta });
      const m = [(ini[0] + P1[0]) / 2, (ini[1] + P1[1]) / 2];
      const [g, virou] = legivel(u);
      const nrm = (virou ? g + 90 : g + 90);
      out.textos.push({ pos: pol(m, nrm, fol), txt, h, ang: g, alinhamento: 'centro' });
    }
    return out;
  }
  // ordenada: a chamada do ponto medido, atravessada ao eixo medido, com o degrau quando o número fica de lado
  const F = c.p1, P = c.posicao, vert = c.eixo !== 'y';                 // eixo x: a chamada é vertical
  const a = vert ? 1 : 0, b = vert ? 0 : 1;
  const s = (P[a] - F[a]) >= 0 ? 1 : -1, J = 2 * seta;
  const q = (va, vb) => (vert ? [vb, va] : [va, vb]);                     // (ao longo da chamada, de lado)
  const inicio = q(F[a] + s * fol, F[b]);
  if (Math.abs(P[b] - F[b]) < 1e-6 || Math.abs(P[a] - F[a]) < 3 * J) out.linhas.push([inicio, q(P[a], F[b])]);
  else out.linhas.push([inicio, q(P[a] - s * 2 * J, F[b])], [q(P[a] - s * 2 * J, F[b]), q(P[a] - s * J, P[b])], [q(P[a] - s * J, P[b]), q(P[a], P[b])]);
  const lado = Math.abs(P[b] - F[b]) < 1e-6 ? F[b] : P[b];
  // o número continua a chamada: vertical (girado 90°) na ordenada em x, centrado nela
  out.textos.push(vert
    ? { pos: [lado + h / 2, P[a] + s * fol], txt, h, ang: 90, alinhamento: s > 0 ? 'esquerda' : 'direita' }
    : { pos: [P[a] + s * fol, lado - h / 2], txt, h, ang: 0, alinhamento: s > 0 ? 'esquerda' : 'direita' });
  return out;
}

/** Os pontos que dão a caixa da cota (o índice espacial, a seleção por janela): as linhas, os arcos e os textos. */
export function pontosDaCotaEspecial(c, k = 1, estilo = null) {
  const pr = primitivasDaCotaEspecial(c, k, estilo), pts = [];
  for (const [a, b] of pr.linhas) pts.push(a, b);
  for (const ar of pr.arcos) { const v = n360(ar.fim - ar.inicio) || 360; for (let i = 0; i <= 12; i++) pts.push(pol(ar.centro, ar.inicio + v * i / 12, ar.raio)); }
  for (const p of pr.pontas) pts.push(p.p);
  for (const t of pr.textos) pts.push(...cantosDoTextoEspecial(t));
  return pts;
}

/** Os cantos da caixa de um texto das primitivas. */
export function cantosDoTextoEspecial(t) {
  const w = Math.max(t.h, String(t.txt).length * t.h * 0.65), x = t.alinhamento === 'centro' ? -w / 2 : t.alinhamento === 'direita' ? -w : 0;
  const a = t.ang * RAD, ca = Math.cos(a), sa = Math.sin(a);
  return [[x, 0], [x + w, 0], [x + w, t.h], [x, t.h]].map(([u, v]) => [t.pos[0] + u * ca - v * sa, t.pos[1] + u * sa + v * ca]);
}

/** A distância do ponto à cota (o clique): às linhas, aos arcos e às caixas dos números. */
export function distanciaCotaEspecial(p, c, k = 1, estilo = null) {
  const pr = primitivasDaCotaEspecial(c, k, estilo);
  let d = Infinity;
  const seg = (a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-12; const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)); return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy); };
  for (const [a, b] of pr.linhas) d = Math.min(d, seg(a, b));
  for (const ar of pr.arcos) {
    const g = angDe(ar.centro, p), v = n360(ar.fim - ar.inicio) || 360;
    if (n360(g - ar.inicio) <= v) d = Math.min(d, Math.abs(dist(ar.centro, p) - ar.raio));
  }
  for (const t of pr.textos) {
    const q = cantosDoTextoEspecial(t);
    let dentro = false;
    for (let i = 0, j = 3; i < 4; j = i++) if (((q[i][1] > p[1]) !== (q[j][1] > p[1])) && (p[0] < (q[j][0] - q[i][0]) * (p[1] - q[i][1]) / (q[j][1] - q[i][1]) + q[i][0])) dentro = !dentro;
    d = Math.min(d, dentro ? 0 : Math.min(...q.map((a, i) => seg(a, q[(i + 1) % 4]))));
  }
  return d;
}
