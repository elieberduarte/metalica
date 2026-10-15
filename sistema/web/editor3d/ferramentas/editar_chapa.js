// Editar chapa no 3D (F10 do levantamento de 14/10): as alças da chapa paramétrica, sem ir ao 2D.
//
// Escolha a chapa (selecionada antes ou com um clique): aparecem as alças — os vértices (quadrado), o meio dos lados (+)
// e os furos (círculo).
//   · clique no vértice e de novo onde ele vai (ou digite "dx;dy" no plano da chapa): muda o contorno;
//   · clique no meio do lado: um vértice novo ali, já pego;
//   · clique no furo e de novo onde ele vai: o furo muda de lugar (de 5 em 5 mm);
//   · Delete apaga o vértice ou o furo escolhido (o último clicado ou o que está sob o mouse);
//   · com um vértice escolhido, "ch20" chanfra o canto (20 × 20) e "r30" arredonda (raio 30).
// Cada mudança é uma entrada do Ctrl+Z; a chapa com marca fica com a marca a conferir.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

/** O canto `i` do contorno chanfrado em `d` mm (os dois lados encurtados de `d`). */
export function chanfrarCanto(pts, i, d) {
  const n = pts.length, P = pts[(i - 1 + n) % n], V = pts[i], N = pts[(i + 1) % n];
  const lP = Math.hypot(P[0] - V[0], P[1] - V[1]), lN = Math.hypot(N[0] - V[0], N[1] - V[1]);
  if (!(d > 0) || d >= lP - 0.5 || d >= lN - 0.5) return null;
  const A = [V[0] + (P[0] - V[0]) * d / lP, V[1] + (P[1] - V[1]) * d / lP];
  const B = [V[0] + (N[0] - V[0]) * d / lN, V[1] + (N[1] - V[1]) * d / lN];
  return [...pts.slice(0, i), A, B, ...pts.slice(i + 1)];
}

/** O canto `i` arredondado com raio `r` (o arco tangente aos dois lados, em `lados` segmentos). */
export function arredondarCanto(pts, i, r, lados = 8) {
  const n = pts.length, P = pts[(i - 1 + n) % n], V = pts[i], N = pts[(i + 1) % n];
  const a = [P[0] - V[0], P[1] - V[1]], b = [N[0] - V[0], N[1] - V[1]];
  const la = Math.hypot(...a), lb = Math.hypot(...b);
  if (!(r > 0) || la < 1e-9 || lb < 1e-9) return null;
  const ua = [a[0] / la, a[1] / la], ub = [b[0] / lb, b[1] / lb];
  const th = Math.acos(Math.max(-1, Math.min(1, ua[0] * ub[0] + ua[1] * ub[1])));       // o ângulo do canto
  if (th < 1e-3 || th > Math.PI - 1e-3) return null;
  const t = r / Math.tan(th / 2);                                                         // até o ponto de tangência
  if (t >= la - 0.5 || t >= lb - 0.5) return null;
  const bis = [ua[0] + ub[0], ua[1] + ub[1]], lbis = Math.hypot(...bis);
  const c = [V[0] + bis[0] / lbis * r / Math.sin(th / 2), V[1] + bis[1] / lbis * r / Math.sin(th / 2)];
  const A = [V[0] + ua[0] * t, V[1] + ua[1] * t], B = [V[0] + ub[0] * t, V[1] + ub[1] * t];
  let a0 = Math.atan2(A[1] - c[1], A[0] - c[0]), a1 = Math.atan2(B[1] - c[1], B[0] - c[0]);
  let da = a1 - a0;
  while (da > Math.PI) da -= 2 * Math.PI;
  while (da < -Math.PI) da += 2 * Math.PI;
  const arco = [];
  for (let k = 0; k <= lados; k++) {
    const ang = a0 + da * k / lados;
    arco.push([c[0] + r * Math.cos(ang), c[1] + r * Math.sin(ang)]);
  }
  return [...pts.slice(0, i), ...arco, ...pts.slice(i + 1)];
}

export class FerramentaEditarChapa extends Ferramenta {
  static id = 'editar_chapa';
  static nome = 'Editar chapa';
  static atalho = 'Shift+C';
  static grupo = 'estrutura';
  static dica = 'Clique na chapa (ou selecione-a antes): arraste vértice, meio do lado ou furo · Delete apaga · "ch20" / "r30" no canto';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 6h12l4 4v8H4Z"/><rect x="14.5" y="4.5" width="3" height="3" fill="currentColor"/><circle cx="9" cy="12" r="2"/></svg>`;

  ativar() {
    this.chapa = null; this.pego = null; this.escolhido = null; this.sob = null; this.atual = null;
    const sel = C.idsSelecionados(this.editor).map(id => this.documento.get(id)).find(e => e && e.tipo === 'chapa');
    if (sel) this._escolher(sel);
    else this.dica(FerramentaEditarChapa.dica);
    this.medida('');
  }

  desativar() { this.limparPrevia(); }

  cancelar() {
    if (this.pego) { this.pego = null; this.desenhar(); this.dica('Solto. Escolha outra alça (Esc sai da chapa)'); return; }
    if (this.chapa) { this.chapa = null; this.limparPrevia(); this.selecao.limpar(); this.dica(FerramentaEditarChapa.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  teclaDeValor(k) { return !!this.chapa && /^[0-9cCrR\-]$/.test(k); }

  get ent() { return this.chapa && this.documento.get(this.chapa); }

  _plano(ch) {
    return { origem: ch.origem, ex: C.normalizar(ch.eixo_x), ey: C.normalizar(ch.eixo_y),
             normal: C.normalizar(C.cross(ch.eixo_x, ch.eixo_y)) };
  }

  _escolher(ch) {
    if (!C.editavel(this.editor, ch)) { this.dica(C.DICA_BLOQUEADA); return; }
    this.chapa = ch.id; this.pego = null; this.escolhido = null;
    this.selecao.definir([ch.id]);
    this.dica(`${ch.nome || 'Chapa'}: clique num vértice, no meio de um lado ou num furo · Delete apaga o escolhido · "ch20" chanfra, "r30" arredonda o canto escolhido`);
    this.desenhar();
  }

  /** As alças no mundo: [{tipo: 'vertice'|'meio'|'furo', i, p}], na face de cima da chapa. */
  _alcas(ch) {
    const pl = this._plano(ch);
    const z = ch.centrada === false ? (ch.espessura || 0) + 0.5 : (ch.espessura || 0) / 2 + 0.5;
    const em = (u, v) => C.add(C.add(ch.origem, C.add(C.mul(pl.ex, u), C.mul(pl.ey, v))), C.mul(pl.normal, z));
    const c = ch.contorno || [];
    const out = [];
    c.forEach(([u, v], i) => out.push({ tipo: 'vertice', i, p: em(u, v) }));
    c.forEach(([u, v], i) => { const [u2, v2] = c[(i + 1) % c.length]; out.push({ tipo: 'meio', i, p: em((u + u2) / 2, (v + v2) / 2) }); });
    (ch.furos || []).forEach((f, i) => out.push({ tipo: 'furo', i, p: em(f.x || 0, f.y || 0) }));
    return { out, em, z };
  }

  /** A alça sob o cursor (a até 14 px). */
  _alcaSob(ch, tela) {
    if (!tela) return null;
    let melhor = null;
    for (const a of this._alcas(ch).out) {
      const t = this.editor.camera.paraTela(a.p);
      if (t[2] > 1) continue;
      const d = Math.hypot(t[0] - tela[0], t[1] - tela[1]);
      // o furo e o vértice ganham do meio do lado quando estão juntos
      const peso = a.tipo === 'meio' ? 3 : 0;
      if (d <= 14 && (!melhor || d + peso < melhor.d)) melhor = { ...a, d: d + peso };
    }
    return melhor;
  }

  /** O ponto do mouse no plano da chapa, em (u, v), de 5 em 5 mm (Shift: livre). */
  _uv(ch, p, ev) {
    const pl = this._plano(ch);
    const q = C.noPlano(this.editor, p, { origem: ch.origem, normal: pl.normal, ex: pl.ex, ey: pl.ey });
    let uv = C.para2d({ origem: ch.origem, ex: pl.ex, ey: pl.ey, normal: pl.normal }, q);
    if (!(ev && ev.shiftKey)) uv = uv.map(x => Math.round(x / 5) * 5);
    return uv;
  }

  _gravar(campos, rotulo) {
    const ch = this.ent;
    this.executar(C.cmdAlterar(ch.id, C.marcarParaConferir(ch, campos), rotulo));
  }

  onMover(p, ev) {
    const ch = this.ent;
    if (!ch) return;
    if (this.pego) { this.atual = this._uv(ch, p, ev); this.desenhar(); return; }
    this.sob = this._alcaSob(ch, p && p.tela);
    this.desenhar();
  }

  onPonto(p, ev) {
    const ch = this.ent;
    if (!ch) {
      const t = p && p.tela, s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
      if (s && s.entidade && s.entidade.tipo === 'chapa') this._escolher(s.entidade);
      else this.dica('Clique numa chapa (a desenhada no editor ou a do projeto, paramétrica)');
      return;
    }
    if (this.pego) { this._soltar(this._uv(ch, p, ev)); return; }
    const a = this._alcaSob(ch, p && p.tela);
    if (!a) {
      const t = p && p.tela, s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
      if (s && s.entidade && s.entidade.tipo === 'chapa' && s.entidade.id !== ch.id) this._escolher(s.entidade);
      return;
    }
    if (a.tipo === 'meio') {
      // um vértice novo no meio do lado, já pego
      const c = ch.contorno.map(q => q.slice());
      const [u, v] = c[a.i], [u2, v2] = c[(a.i + 1) % c.length];
      c.splice(a.i + 1, 0, [(u + u2) / 2, (v + v2) / 2]);
      this._gravar({ contorno: c }, 'Vértice novo na chapa');
      this.pego = { tipo: 'vertice', i: a.i + 1 };
    } else {
      this.pego = { tipo: a.tipo, i: a.i };
    }
    this.escolhido = { ...this.pego };
    this.atual = null;
    this.dica(this.pego.tipo === 'furo' ? 'Clique onde o furo vai (de 5 em 5 mm; Shift livre) · ou digite "dx;dy" · Delete apaga · Esc solta'
                                        : 'Clique onde o vértice vai · ou digite "dx;dy" · Delete apaga · "ch20"/"r30" no canto · Esc solta');
  }

  _soltar(uv) {
    const ch = this.ent;
    const { tipo, i } = this.pego;
    if (tipo === 'furo') {
      const furos = (ch.furos || []).map(f => ({ ...f }));
      const f = furos[i];
      const c2 = ch.contorno;
      const r = (f.diametro || Math.max(f.largura || 0, f.altura || 0)) / 2;
      if (!C.dentroDoContorno(c2, uv)) { this.dica('O furo precisa ficar dentro da chapa'); return; }
      furos[i] = { ...f, x: uv[0], y: uv[1] };
      this._gravar({ furos }, 'Mover furo');
      this.dica(`Furo em ${formatar(uv[0])}; ${formatar(uv[1])} (Ø${formatar(r * 2, 1)}) · escolha outra alça`);
    } else {
      const c = ch.contorno.map(q => q.slice());
      c[i] = uv;
      if (Math.abs(C.areaAssinada(c)) < 1) { this.dica('Assim a chapa some: escolha outro ponto'); return; }
      this._gravar({ contorno: C.areaAssinada(c) >= 0 ? c : c.reverse() }, 'Mover vértice da chapa');
      this.dica('Vértice movido · escolha outra alça (Ctrl+Z desfaz)');
    }
    this.pego = null; this.atual = null;
    this.desenhar();
  }

  onValor(texto) {
    const ch = this.ent;
    if (!ch) return false;
    const t = String(texto).trim().toLowerCase();
    const m = t.match(/^(ch|r)\s*(.+)$/);
    if (m) {
      const alvo = this.escolhido || (this.sob && this.sob.tipo === 'vertice' ? this.sob : null);
      if (!alvo || alvo.tipo !== 'vertice') { this.dica('Clique antes no vértice (o canto) a chanfrar ou arredondar'); return true; }
      const d = paraMilimetros(m[2]);
      const novo = m[1] === 'ch' ? chanfrarCanto(ch.contorno, alvo.i, d) : arredondarCanto(ch.contorno, alvo.i, d);
      if (!novo) { this.dica(`${m[1] === 'ch' ? 'Chanfro' : 'Raio'} de ${formatar(d)} não cabe nesse canto`); return true; }
      this._gravar({ contorno: novo }, m[1] === 'ch' ? 'Chanfro de canto' : 'Raio de canto');
      this.pego = null; this.escolhido = null;
      this.dica(`${m[1] === 'ch' ? 'Chanfro' : 'Raio'} de ${formatar(d)} no canto (Ctrl+Z desfaz)`);
      this.desenhar();
      return true;
    }
    if (this.pego) {
      const xy = t.split(';').map(paraMilimetros);
      if (xy.length !== 2 || !xy.every(isFinite)) return false;
      const base = this.pego.tipo === 'furo' ? [ch.furos[this.pego.i].x || 0, ch.furos[this.pego.i].y || 0] : ch.contorno[this.pego.i];
      this._soltar([base[0] + xy[0], base[1] + xy[1]]);
      return true;
    }
    return false;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    const ch = this.ent;
    if (!ch || (ev.key !== 'Delete' && ev.key !== 'Backspace')) return false;
    const alvo = this.pego || this.escolhido || this.sob;
    if (!alvo) { this.dica('Escolha (clique) o vértice ou o furo a apagar'); return true; }
    if (alvo.tipo === 'furo') {
      this._gravar({ furos: (ch.furos || []).filter((_, i) => i !== alvo.i) }, 'Apagar furo da chapa');
      this.dica('Furo apagado (Ctrl+Z desfaz)');
    } else if (alvo.tipo === 'vertice') {
      if (ch.contorno.length <= 3) { this.dica('A chapa precisa de pelo menos três vértices'); return true; }
      this._gravar({ contorno: ch.contorno.filter((_, i) => i !== alvo.i) }, 'Apagar vértice da chapa');
      this.dica('Vértice apagado (Ctrl+Z desfaz)');
    }
    this.pego = null; this.escolhido = null; this.sob = null;
    this.desenhar();
    return true;
  }

  desenhar() {
    this.limparPrevia();
    const ch = this.ent;
    if (!ch) return;
    const { out, em } = this._alcas(ch);
    const g = C.grupo();
    const c = ch.contorno || [];
    let contorno = c;
    if (this.pego && this.atual && this.pego.tipo === 'vertice') {
      contorno = c.map((q, i) => (i === this.pego.i ? this.atual : q));
    }
    g.add(C.gLinha(contorno.map(([u, v]) => em(u, v)), '#0b3d91', { fechada: true }));
    for (const a of out) {
      const sob = this.sob && this.sob.tipo === a.tipo && this.sob.i === a.i;
      const pego = this.pego && this.pego.tipo === a.tipo && this.pego.i === a.i;
      const cor = pego ? '#c2410c' : sob ? '#0a8f3c' : (a.tipo === 'meio' ? '#8a94a6' : '#0b3d91');
      g.add(C.gPonto(a.p, cor));
    }
    if (this.pego && this.atual) {
      if (this.pego.tipo === 'furo') {
        const f = ch.furos[this.pego.i];
        const r = (f.diametro || Math.max(f.largura || 0, f.altura || 0)) / 2;
        const pts = [];
        for (let k = 0; k < 20; k++) { const a = 2 * Math.PI * k / 20; pts.push(em(this.atual[0] + r * Math.cos(a), this.atual[1] + r * Math.sin(a))); }
        g.add(C.gLinha(pts, '#c2410c', { fechada: true }));
      }
      g.add(C.gRotulo(`${formatar(this.atual[0])}; ${formatar(this.atual[1])}`, em(this.atual[0], this.atual[1]), '#c2410c'));
      this.medida(`${formatar(this.atual[0])}; ${formatar(this.atual[1])}`);
    }
    this.previa(g);
  }
}

export default FerramentaEditarChapa;
