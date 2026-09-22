// A tela do CAD: canvas 2D, janela de visualização, desenho das entidades e acerto.
//
// Sistema do modelo em milímetro com Y para cima; a tela em pixels com Y para baixo.
// `vp` guarda a janela: `z` pixels por milímetro, (`x`, `y`) o ponto do modelo no canto
// inferior esquerdo da tela. O que é "de papel" (texto, seta de cota, espaçamento de
// hachura) vale `mm_papel × escala_do_desenho` em milímetros do modelo, então aparece
// na tela do tamanho que terá impresso, em qualquer zoom.
//
// Redesenho completo a cada quadro pedido: com dezenas de milhares de linhas o canvas
// 2D dá conta em poucos milissegundos, e a simplicidade vale mais que um cache.

import { pontosArco, valorCota, dentroDe, segmentosDe, caixaDe, pontosDe, distanciaEntidade } from './desenho2d.js';

const TRACOS = { CONTINUOUS: [], HIDDEN: [6, 4], CENTER: [16, 4, 4, 4], DASHED: [8, 6], DOT: [2, 3] };
const PX_GRADE_ALVO = 60;

export function formatarMm(v) {
  if (Math.abs(v - Math.round(v)) < 0.05) return String(Math.round(v));
  return v.toFixed(1).replace('.', ',');
}

export class Tela {
  constructor(canvas, documento) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.doc = documento;
    this.vp = { x: -100, y: -100, z: 0.5 };
    this.selecao = new Set();
    this.realce = null;                 // id sob o cursor
    this.previa = [];                   // entidades temporárias da ferramenta
    this.snap = null;                   // {ponto, tipo}
    this.cursor = null;                 // ponto do modelo sob o mouse
    this.retangulo = null;              // seleção por janela [[x,y],[x,y]] em tela
    this.escuro = false;
    this.grade = true;
    this._quadro = null;
    this.aoDesenhar = null;
  }

  // ------------------------------------------------------------ janela
  get largura() { return this.canvas.clientWidth; }
  get altura() { return this.canvas.clientHeight; }

  paraTela(p) { return [(p[0] - this.vp.x) * this.vp.z, this.altura - (p[1] - this.vp.y) * this.vp.z]; }
  paraMundo(px) { return [px[0] / this.vp.z + this.vp.x, (this.altura - px[1]) / this.vp.z + this.vp.y]; }
  /** mm do modelo por pixel. */
  get mmPorPixel() { return 1 / this.vp.z; }

  redimensionar() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    }
    this.pedirQuadro();
  }

  enquadrar(caixa = null, margem = 0.08) {
    const c = caixa || this.doc.caixa();
    if (!c) { this.vp = { x: -200, y: -200, z: 0.5 }; this.pedirQuadro(); return; }
    const [[x0, y0], [x1, y1]] = c;
    const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1);
    const z = Math.min(this.largura / (w * (1 + 2 * margem)), this.altura / (h * (1 + 2 * margem)));
    this.vp.z = z;
    this.vp.x = (x0 + x1) / 2 - this.largura / 2 / z;
    this.vp.y = (y0 + y1) / 2 - this.altura / 2 / z;
    this.pedirQuadro();
  }

  zoom(fator, pxFixo) {
    const antes = this.paraMundo(pxFixo);
    this.vp.z = Math.min(200, Math.max(0.0005, this.vp.z * fator));
    const depois = this.paraMundo(pxFixo);
    this.vp.x += antes[0] - depois[0];
    this.vp.y += antes[1] - depois[1];
    this.pedirQuadro();
  }

  arrastar(dpx) {
    this.vp.x -= dpx[0] / this.vp.z;
    this.vp.y += dpx[1] / this.vp.z;
    this.pedirQuadro();
  }

  pedirQuadro() {
    if (this._quadro) return;
    this._quadro = requestAnimationFrame(() => { this._quadro = null; this.desenhar(); });
  }

  // ------------------------------------------------------------ desenho
  cores() {
    return this.escuro
      ? { fundo: '#0e131a', grade: 'rgba(255,255,255,.06)', grade10: 'rgba(255,255,255,.13)', eixo: 'rgba(255,255,255,.22)',
          selecao: '#4b9bf0', realce: '#7aa7f0', previa: '#e6bb52', snap: '#5fd08d', cursor: 'rgba(255,255,255,.35)',
          textoInvertido: (c) => (c === '#16202e' || c === '#2b3646') ? '#e4eaf3' : c }
      : { fundo: '#f4f6fa', grade: 'rgba(16,32,60,.06)', grade10: 'rgba(16,32,60,.12)', eixo: 'rgba(16,32,60,.28)',
          selecao: '#1f7ae0', realce: '#3d8fe6', previa: '#c07a00', snap: '#1c7a43', cursor: 'rgba(16,32,60,.45)',
          textoInvertido: (c) => c };
  }

  desenhar() {
    const ctx = this.ctx, dpr = window.devicePixelRatio || 1;
    const W = this.largura, H = this.altura;
    const cores = this.cores();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = cores.fundo;
    ctx.fillRect(0, 0, W, H);
    if (this.grade) this._grade(ctx, cores);

    const k = this.doc.escala;                    // mm de papel → mm de modelo
    const ordem = [...this.doc.entidades.values()];
    // hachuras por baixo, textos e cotas por cima
    const peso = (e) => (e.tipo === 'hachura' ? 0 : (e.tipo === 'texto' || e.tipo === 'cota' || e.tipo === 'chamada') ? 2 : 1);
    ordem.sort((a, b) => peso(a) - peso(b));
    for (const e of ordem) {
      if (!this.doc.visivel(e)) continue;
      const cam = this.doc.camadas.get(e.camada);
      const cor = this.selecao.has(e.id) ? cores.selecao : this.realce === e.id ? cores.realce : cores.textoInvertido((cam && cam.cor) || '#4b5563');
      this._entidade(ctx, e, cor, cam, k, this.selecao.has(e.id));
    }
    for (const e of this.previa) this._entidade(ctx, e, cores.previa, null, k, false, true);

    if (this.retangulo) {
      const [a, b] = this.retangulo;
      ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.strokeStyle = cores.selecao;
      ctx.fillStyle = a[0] <= b[0] ? 'rgba(31,122,224,.08)' : 'rgba(31,160,80,.08)';
      ctx.fillRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
      ctx.strokeRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
      ctx.setLineDash([]);
    }
    if (this.snap) this._glifoSnap(ctx, this.snap, cores.snap);
    else if (this.cursor) {
      const [x, y] = this.paraTela(this.cursor);
      ctx.strokeStyle = cores.cursor; ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(x - 9, y); ctx.lineTo(x + 9, y); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 9); ctx.stroke();
    }
    if (this.aoDesenhar) this.aoDesenhar();
  }

  _grade(ctx, cores) {
    const mmpp = this.mmPorPixel;
    let passo = Math.pow(10, Math.ceil(Math.log10(mmpp * PX_GRADE_ALVO)));
    if (passo / mmpp > PX_GRADE_ALVO * 2.5) passo /= 2;
    const W = this.largura, H = this.altura;
    const m0 = this.paraMundo([0, H]), m1 = this.paraMundo([W, 0]);
    ctx.lineWidth = 1;
    for (const [p, cor] of [[passo, cores.grade], [passo * 10, cores.grade10]]) {
      if (p / mmpp < 6) continue;
      ctx.strokeStyle = cor; ctx.beginPath();
      for (let x = Math.floor(m0[0] / p) * p; x <= m1[0]; x += p) { const px = Math.round(this.paraTela([x, 0])[0]) + 0.5; ctx.moveTo(px, 0); ctx.lineTo(px, H); }
      for (let y = Math.floor(m0[1] / p) * p; y <= m1[1]; y += p) { const py = Math.round(this.paraTela([0, y])[1]) + 0.5; ctx.moveTo(0, py); ctx.lineTo(W, py); }
      ctx.stroke();
    }
    ctx.strokeStyle = cores.eixo; ctx.beginPath();
    const o = this.paraTela([0, 0]);
    ctx.moveTo(0, Math.round(o[1]) + 0.5); ctx.lineTo(W, Math.round(o[1]) + 0.5);
    ctx.moveTo(Math.round(o[0]) + 0.5, 0); ctx.lineTo(Math.round(o[0]) + 0.5, H);
    ctx.stroke();
    this.passoGrade = passo;
  }

  _estilo(ctx, cor, cam, selecionada, previa) {
    ctx.strokeStyle = cor; ctx.fillStyle = cor;
    const esp = (cam && cam.espessura) || 0.25;
    ctx.lineWidth = selecionada ? 2.2 : Math.max(1, Math.min(3, esp / 0.25));
    const tracos = TRACOS[(cam && cam.tipo_linha) || 'CONTINUOUS'] || [];
    ctx.setLineDash(previa ? [5, 4] : tracos);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  }

  _entidade(ctx, e, cor, cam, k, selecionada, previa = false) {
    const T = (p) => this.paraTela(p);
    this._estilo(ctx, cor, cam, selecionada, previa);
    switch (e.tipo) {
      case 'linha': { const a = T(e.a), b = T(e.b); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); break; }
      case 'polilinha': {
        if (e.vertices.length < 2) break;
        ctx.beginPath();
        e.vertices.forEach((p, i) => { const q = T(p); i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]); });
        if (e.fechada) ctx.closePath();
        ctx.stroke(); break;
      }
      case 'circulo': { const c = T(e.centro); ctx.beginPath(); ctx.arc(c[0], c[1], e.raio * this.vp.z, 0, Math.PI * 2); ctx.stroke(); break; }
      case 'arco': {
        const c = T(e.centro);
        // canvas mede ângulos no sentido horário (y para baixo): inverte
        ctx.beginPath(); ctx.arc(c[0], c[1], e.raio * this.vp.z, -e.fim * Math.PI / 180, -e.inicio * Math.PI / 180); ctx.stroke(); break;
      }
      case 'texto': this._texto(ctx, e.posicao, e.texto, e.altura * k, e.angulo || 0, e.alinhamento, e.vertical, cor); break;
      case 'cota': this._cota(ctx, e, k, cor); break;
      case 'hachura': this._hachura(ctx, e, k, cor); break;
      case 'chamada': this._chamada(ctx, e, k, cor); break;
    }
    ctx.setLineDash([]);
  }

  _texto(ctx, pos, texto, alturaMm, angulo, alinhamento = 'esquerda', vertical = 'base', cor) {
    const px = alturaMm * this.vp.z;
    if (px < 2.5) {                      // longe demais para ler: um traço do tamanho do texto
      const [x, y] = this.paraTela(pos);
      const w = (texto || '').length * px * 0.6;
      ctx.globalAlpha = 0.5; ctx.fillRect(alinhamento === 'centro' ? x - w / 2 : alinhamento === 'direita' ? x - w : x, y - px, w, px); ctx.globalAlpha = 1;
      return;
    }
    const [x, y] = this.paraTela(pos);
    ctx.save();
    ctx.translate(x, y); ctx.rotate(-(angulo || 0) * Math.PI / 180);
    ctx.font = `${px}px "Segoe UI", Roboto, Arial, sans-serif`;
    ctx.textAlign = alinhamento === 'centro' ? 'center' : alinhamento === 'direita' ? 'right' : 'left';
    ctx.textBaseline = vertical === 'meio' ? 'middle' : vertical === 'topo' ? 'top' : 'alphabetic';
    ctx.fillStyle = cor; ctx.setLineDash([]);
    ctx.fillText(texto || '', 0, 0);
    ctx.restore();
  }

  _seta(ctx, p, ang, tam) {
    const [x, y] = p;
    const a = -ang;                                   // tela com y invertido
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - tam * Math.cos(a - 0.35), y - tam * Math.sin(a - 0.35));
    ctx.lineTo(x - tam * Math.cos(a + 0.35), y - tam * Math.sin(a + 0.35));
    ctx.closePath(); ctx.fill();
  }

  /** Geometria da cota em coordenadas do modelo (compartilhada com o acerto). */
  static geometriaCota(c, k) {
    let [x1, y1] = c.p1, [x2, y2] = c.p2;
    if (c.modo === 'h') y2 = y1; else if (c.modo === 'v') x2 = x1;
    const dx = x2 - x1, dy = y2 - y1, comp = Math.hypot(dx, dy);
    if (comp < 1e-9) return null;
    const ux = dx / comp, uy = dy / comp, nx = -uy, ny = ux;
    const desl = c.deslocamento * k;
    const a1 = [x1 + nx * desl, y1 + ny * desl], a2 = [x2 + nx * desl, y2 + ny * desl];
    return { a1, a2, ux, uy, nx, ny, comp, desl, x1, y1, x2, y2 };
  }

  _cota(ctx, c, k, cor) {
    const g = Tela.geometriaCota(c, k);
    if (!g) return;
    const z = this.vp.z, T = (p) => this.paraTela(p);
    const sg = g.desl >= 0 ? 1 : -1, ext = 2 * k, fol = 1.5 * k, seta = Math.min(2.5 * k, Math.max(1 * k, g.comp / 4));
    ctx.setLineDash([]);
    ctx.beginPath();
    for (const [p, a] of [[c.p1, g.a1], [c.p2, g.a2]]) {
      const i = T([p[0] + g.nx * sg * fol, p[1] + g.ny * sg * fol]), f = T([a[0] + g.nx * sg * ext, a[1] + g.ny * sg * ext]);
      ctx.moveTo(i[0], i[1]); ctx.lineTo(f[0], f[1]);
    }
    const A1 = T(g.a1), A2 = T(g.a2);
    ctx.moveTo(A1[0], A1[1]); ctx.lineTo(A2[0], A2[1]); ctx.stroke();
    const ang = Math.atan2(g.uy, g.ux);
    const fora = g.comp < 3 * seta;
    this._seta(ctx, A1, fora ? ang : ang + Math.PI, seta * z);
    this._seta(ctx, A2, fora ? ang + Math.PI : ang, seta * z);
    const txt = c.texto != null && c.texto !== '' ? c.texto : formatarMm(valorCota(c));
    let mx = (g.a1[0] + g.a2[0]) / 2, my = (g.a1[1] + g.a2[1]) / 2;
    let angG = ang * 180 / Math.PI;
    const lado = (angG > -90 && angG <= 90) ? 1 : -1;
    if (lado < 0) angG += 180;
    const h = c.altura * k, off = h * 0.55 * lado;
    if (fora) { mx += g.ux * (2.4 * seta + 0.4 * h * txt.length); my += g.uy * (2.4 * seta + 0.4 * h * txt.length); }
    this._texto(ctx, [mx + g.nx * off, my + g.ny * off], txt, h, angG, 'centro', 'base', cor);
  }

  _hachura(ctx, e, k, cor) {
    const ext = e.contornos[0];
    if (!ext || ext.length < 3) return;
    const T = (p) => this.paraTela(p);
    ctx.save();
    ctx.beginPath();
    for (const c of e.contornos) { c.forEach((p, i) => { const q = T(p); i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]); }); ctx.closePath(); }
    ctx.clip('evenodd');
    const esp = (e.padrao === 'solido' ? 0.6 : e.espacamento) * k * this.vp.z;
    if (esp < 2.5) {                                    // longe: preenchimento leve no lugar das linhas
      ctx.globalAlpha = e.padrao === 'solido' ? 0.85 : 0.18; ctx.fillStyle = cor;
      const pts = ext.map(T); const cx = caixaDe(pts);
      ctx.fillRect(cx[0][0], cx[0][1], cx[1][0] - cx[0][0], cx[1][1] - cx[0][1]);
      ctx.restore(); return;
    }
    const pts = ext.map(T); const [[x0, y0], [x1, y1]] = caixaDe(pts);
    const a = -(e.angulo || 45) * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
    const diag = Math.hypot(x1 - x0, y1 - y0), cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    ctx.lineWidth = 1; ctx.strokeStyle = cor; ctx.setLineDash([]);
    ctx.beginPath();
    for (let t = -diag; t <= diag; t += esp) {
      const px = cx + t * (-sa), py = cy + t * ca;
      ctx.moveTo(px - ca * diag, py - sa * diag); ctx.lineTo(px + ca * diag, py + sa * diag);
    }
    ctx.stroke();
    ctx.restore();
  }

  _chamada(ctx, e, k, cor) {
    const T = (p) => this.paraTela(p);
    const a = T(e.alvo), p = T(e.posicao);
    ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(p[0], p[1]);
    const direita = e.posicao[0] >= e.alvo[0];
    const traco = (direita ? 8 : -8) * k;
    const f = T([e.posicao[0] + traco, e.posicao[1]]);
    ctx.lineTo(f[0], f[1]); ctx.stroke();
    this._seta(ctx, a, Math.atan2(e.alvo[1] - e.posicao[1], e.alvo[0] - e.posicao[0]), 2.5 * k * this.vp.z);
    this._texto(ctx, [e.posicao[0] + traco + (direita ? 1.5 : -1.5) * k, e.posicao[1] + 0.8 * k], e.texto, e.altura * k, 0,
                direita ? 'esquerda' : 'direita', 'base', cor);
  }

  _glifoSnap(ctx, snap, cor) {
    const [x, y] = this.paraTela(snap.ponto);
    ctx.strokeStyle = cor; ctx.fillStyle = cor; ctx.lineWidth = 1.5; ctx.setLineDash([]);
    ctx.beginPath();
    switch (snap.tipo) {
      case 'extremidade': ctx.rect(x - 5, y - 5, 10, 10); break;
      case 'meio': ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y + 5); ctx.lineTo(x - 6, y + 5); ctx.closePath(); break;
      case 'centro': ctx.arc(x, y, 5.5, 0, Math.PI * 2); break;
      case 'interseccao': ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x - 5, y + 5); ctx.lineTo(x + 5, y - 5); break;
      case 'perpendicular': ctx.moveTo(x - 5, y - 5); ctx.lineTo(x - 5, y + 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x - 5, y); ctx.lineTo(x, y); ctx.lineTo(x, y + 5); break;
      case 'sobre': ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); break;
      case 'grade': ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y); ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); break;
      default: ctx.arc(x, y, 3, 0, Math.PI * 2);
    }
    ctx.stroke();
    if (snap.rotulo) {
      ctx.font = '11px "Segoe UI", Arial, sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      ctx.fillText(snap.rotulo, x + 9, y - 6);
    }
  }

  // ------------------------------------------------------------ acerto
  /** Entidade mais próxima do ponto de tela, dentro de `tol` pixels. */
  sob(px, tol = 6) {
    const p = this.paraMundo(px), t = tol * this.mmPorPixel;
    let melhor = null, dm = Infinity;
    for (const e of this.doc.entidades.values()) {
      if (!this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      let d;
      if (e.tipo === 'cota') {
        const g = Tela.geometriaCota(e, this.doc.escala);
        d = g ? Math.min(distanciaEntidade(p, e), this._distSeg(p, g.a1, g.a2)) : Infinity;
      } else d = distanciaEntidade(p, e, this.doc.escala);
      if (d < t && d < dm) { dm = d; melhor = e; }
    }
    return melhor;
  }

  _distSeg(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    if (l2 < 1e-12) return Math.hypot(p[0] - a[0], p[1] - a[1]);
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  }

  /** Ids dentro de um retângulo de tela. Da esquerda para a direita: só as inteiramente
   *  dentro (janela); da direita para a esquerda: as que tocam (cruzamento). */
  naJanela(a, b) {
    const cruzamento = b[0] < a[0];
    const m1 = this.paraMundo([Math.min(a[0], b[0]), Math.max(a[1], b[1])]);
    const m2 = this.paraMundo([Math.max(a[0], b[0]), Math.min(a[1], b[1])]);
    const dentro = (p) => p[0] >= m1[0] && p[0] <= m2[0] && p[1] >= m1[1] && p[1] <= m2[1];
    const ids = [];
    for (const e of this.doc.entidades.values()) {
      if (!this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      const pts = pontosDe(e);
      if (!pts.length) continue;
      if (cruzamento) {
        const cx = caixaDe(pts);
        if (cx[1][0] >= m1[0] && cx[0][0] <= m2[0] && cx[1][1] >= m1[1] && cx[0][1] <= m2[1]) ids.push(e.id);
      } else if (pts.every(dentro)) ids.push(e.id);
    }
    return ids;
  }
}
