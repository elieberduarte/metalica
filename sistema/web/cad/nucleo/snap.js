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

  /** Candidatos das entidades perto do cursor (em mm). */
  _candidatas(p, raioMm) {
    const doc = this.tela.doc, fora = [];
    const caixaOk = (pts) => pts.some(q => Math.abs(q[0] - p[0]) < raioMm * 40 && Math.abs(q[1] - p[1]) < raioMm * 40) || pts.length > 40;
    for (const e of doc.entidades.values()) {
      if (!doc.visivel(e) || e.tipo === 'hachura' || e.tipo === 'texto') continue;
      const pts = pontosDe(e);
      if (!pts.length || !caixaOk(pts)) continue;
      fora.push(e);
    }
    return fora;
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
      if (a.centro && e.tipo === 'circulo') {
        for (const q of [[e.centro[0] + e.raio, e.centro[1]], [e.centro[0] - e.raio, e.centro[1]], [e.centro[0], e.centro[1] + e.raio], [e.centro[0], e.centro[1] - e.raio]]) considerar(q, 'extremidade', 1, 'quadrante');
      }
    }
    if (a.interseccao && ents.length > 1) {
      const segs = ents.flatMap(e => segmentosDe(e).map(s => [e.id, s]));
      // só segmentos perto do cursor
      const perto = segs.filter(([, [s, t]]) => Math.min(dist(s, p), dist(t, p), distSegmento(p, s, t)) < raio * 3);
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
