// Snap: para a posição do mouse, o ponto do desenho mais provável.
//
// Ordem de preferência, como nos CADs: extremidade, meio, centro, interseção,
// perpendicular (em relação ao último ponto da ferramenta), sobre a entidade, grade.
// Tudo dentro de um raio em pixels; o resultado traz o tipo, que a tela desenha como
// glifo. Orto (Shift) trava a direção a 0°/90° a partir do último ponto.

import { pontosDe, segmentosDe, intersecaoSeg, maisProximoSeg, dist } from './desenho2d.js';

export class Snap {
  constructor(tela) {
    this.tela = tela;
    this.ativos = { extremidade: true, meio: true, centro: true, interseccao: true, perpendicular: true, sobre: true, grade: false };
    this.raioPx = 9;
    this.ultimo = null;                  // último ponto fixado pela ferramenta (para orto/perpendicular)
    this.orto = false;
  }

  /** Candidatos das entidades perto do cursor (em mm), pelo índice espacial do documento. */
  _candidatas(p, raioMm) {
    const doc = this.tela.doc, r = raioMm * 3;
    return doc.naRegiao([[p[0] - r, p[1] - r], [p[0] + r, p[1] + r]])
      .filter(e => doc.visivel(e) && e.tipo !== 'hachura' && e.tipo !== 'texto');
  }

  resolver(px, opcoes = {}) {
    const tela = this.tela, p = tela.paraMundo(px);
    const raio = this.raioPx * tela.mmPorPixel;
    let melhor = null;
    const considerar = (ponto, tipo, prioridade, rotulo = '') => {
      const d = dist(ponto, p);
      if (d > raio) return;
      const chave = prioridade * 1e6 + d;
      if (!melhor || chave < melhor.chave) melhor = { ponto, tipo, chave, rotulo };
    };
    const ents = this._candidatas(p, raio);
    const a = this.ativos;
    for (const e of ents) {
      if (a.extremidade) {
        if (e.tipo === 'linha') { considerar(e.a, 'extremidade', 0); considerar(e.b, 'extremidade', 0); }
        else if (e.tipo === 'polilinha') for (const v of e.vertices) considerar(v, 'extremidade', 0);
        else if (e.tipo === 'arco') { const pa = pontosDe(e); considerar(pa[0], 'extremidade', 0); considerar(pa[pa.length - 1], 'extremidade', 0); }
        else if (e.tipo === 'cota') { considerar(e.p1, 'extremidade', 0); considerar(e.p2, 'extremidade', 0); }
        else if (e.tipo === 'chamada') { considerar(e.alvo, 'extremidade', 0); }
      }
      if (a.meio) {
        for (const [s, t] of (e.tipo === 'linha' || e.tipo === 'polilinha' ? segmentosDe(e) : [])) considerar([(s[0] + t[0]) / 2, (s[1] + t[1]) / 2], 'meio', 1);
      }
      if (a.centro && (e.tipo === 'circulo' || e.tipo === 'arco')) considerar(e.centro, 'centro', 1);
      // polilinha fechada pequena (furo oblongo, recorte): o centro da caixa é o centro do furo
      if (a.centro && e.tipo === 'polilinha' && e.fechada && e.vertices.length >= 3 && e.vertices.length <= 64) {
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const q of e.vertices) { if (q[0] < x0) x0 = q[0]; if (q[0] > x1) x1 = q[0]; if (q[1] < y0) y0 = q[1]; if (q[1] > y1) y1 = q[1]; }
        considerar([(x0 + x1) / 2, (y0 + y1) / 2], 'centro', 1);
      }
      if (a.centro && e.tipo === 'circulo') {
        for (const q of [[e.centro[0] + e.raio, e.centro[1]], [e.centro[0] - e.raio, e.centro[1]], [e.centro[0], e.centro[1] + e.raio], [e.centro[0], e.centro[1] - e.raio]]) considerar(q, 'extremidade', 1, 'quadrante');
      }
    }
    if (a.interseccao && ents.length > 1) {
      // só segmentos que passam a menos de um raio do cursor: a interseção que vale
      // está dentro do raio, logo os dois segmentos passam por ali. Com a vista muito
      // afastada num desenho denso ainda podem ser milhares; os pares ficam limitados
      // aos mais próximos, senão cada movimento do mouse custa segundos.
      const perto = [];
      for (const e of ents) for (const s of segmentosDe(e)) {
        const d = distSegmento(p, s[0], s[1]);
        if (d < raio) perto.push([e.id, s, d]);
      }
      if (perto.length > 200) { perto.sort((x, y) => x[2] - y[2]); perto.length = 200; }
      for (let i = 0; i < perto.length; i++) for (let j = i + 1; j < perto.length; j++) {
        if (perto[i][0] === perto[j][0]) continue;
        const x = intersecaoSeg(perto[i][1][0], perto[i][1][1], perto[j][1][0], perto[j][1][1]);
        if (x) considerar(x, 'interseccao', 0);
      }
    }
    if (a.perpendicular && this.ultimo) {
      for (const e of ents) for (const [s, t] of segmentosDe(e)) {
        const q = maisProximoSeg(this.ultimo, s, t);
        if (dist(q, s) > 1e-6 && dist(q, t) > 1e-6) considerar(q, 'perpendicular', 2);
      }
    }
    if (a.sobre && !melhor) {
      for (const e of ents) {
        if (e.tipo === 'circulo') {
          const ang = Math.atan2(p[1] - e.centro[1], p[0] - e.centro[0]);
          considerar([e.centro[0] + e.raio * Math.cos(ang), e.centro[1] + e.raio * Math.sin(ang)], 'sobre', 3);
        } else for (const [s, t] of segmentosDe(e)) considerar(maisProximoSeg(p, s, t), 'sobre', 3);
      }
    }
    let ponto = melhor ? melhor.ponto : p;
    let tipo = melhor ? melhor.tipo : null;
    if (!melhor && a.grade && tela.passoGrade) {
      const g = tela.passoGrade;
      const q = [Math.round(p[0] / g) * g, Math.round(p[1] / g) * g];
      if (dist(q, p) < raio) { ponto = q; tipo = 'grade'; }
    }
    // orto: trava a 0/90° a partir do último ponto, mantendo a componente dominante
    if ((this.orto || opcoes.orto) && this.ultimo && !melhor) {
      const dx = ponto[0] - this.ultimo[0], dy = ponto[1] - this.ultimo[1];
      ponto = Math.abs(dx) >= Math.abs(dy) ? [ponto[0], this.ultimo[1]] : [this.ultimo[0], ponto[1]];
      tipo = tipo || 'orto';
    }
    return { ponto, tipo, rotulo: melhor ? melhor.rotulo : '' };
  }
}

function distSegmento(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
  if (l2 < 1e-12) return dist(p, a);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
