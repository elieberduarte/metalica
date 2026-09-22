// Ferramentas do CAD 2D.
//
// Cada ferramenta é uma máquina de estados que recebe pontos já resolvidos pelo snap
// (em milímetro), nunca coordenadas de tela. Toda alteração passa por `editor.executar`.
// Medida digitada (`onValor`): "1500", "1,5m", "150cm", "@30" (ângulo), e para
// retângulo "2000;1000". Esc cancela, Enter/espaço confirma ou repete.

import { criar, dist, transladar, transformar, clonar, pontosDe, segmentosDe, intersecaoSeg, maisProximoSeg, dentroDe } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoRemover, ComandoSubstituir, ComandoComposto } from './nucleo/comandos.js';

export function paraMilimetros(texto) {
  const t = String(texto || '').trim().toLowerCase().replace(',', '.');
  const m = t.match(/^(-?\d+(?:\.\d+)?)\s*(mm|cm|m)?$/);
  if (!m) return null;
  const v = parseFloat(m[1]);
  return m[2] === 'm' ? v * 1000 : m[2] === 'cm' ? v * 10 : v;
}

const ang = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
const polar = (a, angulo, d) => [a[0] + d * Math.cos(angulo), a[1] + d * Math.sin(angulo)];
const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1).replace('.', ','));

export class Ferramenta {
  static id = 'base'; static nome = 'Ferramenta'; static atalho = ''; static grupo = 'desenho'; static dica = '';
  constructor(editor) { this.editor = editor; }
  get doc() { return this.editor.doc; }
  get camada() { return this.editor.camadaAtiva; }
  ativar() { this.reiniciar(); }
  desativar() { this.editor.previa([]); this.editor.snap.ultimo = null; }
  reiniciar() { this.editor.previa([]); this.editor.snap.ultimo = null; this.dica(this.constructor.dica); this.editor.medida(''); }
  cancelar() { this.reiniciar(); }
  onPonto(p, ev) {}
  onMover(p, ev) {}
  onValor(texto) {}
  onTecla(ev) { return false; }
  onSoltar(p, ev) {}
  dica(t) { this.editor.dica(t); }
  novaEntidade(reg) { return criar({ ...reg, camada: reg.camada || this.camada }); }
}

// ------------------------------------------------------------ selecionar

export class Selecionar extends Ferramenta {
  static id = 'selecionar'; static nome = 'Selecionar'; static atalho = ' '; static grupo = 'navegacao';
  static dica = 'Clique para selecionar · Shift soma · Ctrl alterna · arraste uma janela · Del apaga';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 3l14 8-6 2-3 6z"/></svg>';
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (!e) { if (!ev.shiftKey && !ev.ctrlKey) this.editor.selecionar([]); return; }
    if (ev.ctrlKey) this.editor.alternarSelecao(e.id);
    else if (ev.shiftKey) this.editor.selecionar([...this.editor.tela.selecao, e.id]);
    else this.editor.selecionar([e.id]);
  }
  onSoltar(p, ev) {
    if (!ev.arrasto) return;
    const ids = this.editor.tela.naJanela(ev.arrasto.de, ev.arrasto.para);
    this.editor.selecionar(ev.shiftKey ? [...this.editor.tela.selecao, ...ids] : ids);
  }
  onTecla(ev) {
    if (ev.key === 'Delete' || ev.key === 'Backspace') { this.editor.apagarSelecao(); return true; }
    if (ev.key.toLowerCase() === 'a' && (ev.ctrlKey || ev.metaKey)) { this.editor.selecionar([...this.doc.entidades.keys()].filter(id => this.doc.visivel(this.doc.get(id)))); return true; }
    return false;
  }
}

// --------------------------------------------------------------- desenho

export class Linha extends Ferramenta {
  static id = 'linha'; static nome = 'Linha'; static atalho = 'l'; static dica = 'Clique no primeiro ponto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20 20 4"/><circle cx="4" cy="20" r="1.5"/><circle cx="20" cy="4" r="1.5"/></svg>';
  reiniciar() { super.reiniciar(); this.ultimo = null; }
  onPonto(p) {
    if (this.ultimo && dist(p, this.ultimo) < 1e-6) return;
    if (this.ultimo) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'linha', a: this.ultimo, b: p })], 'Linha'));
    this.ultimo = p; this.editor.snap.ultimo = p;
    this.dica('Próximo ponto, ou digite o comprimento · Enter/Esc termina');
  }
  onMover(p) {
    if (!this.ultimo) return;
    this.editor.previa([criar({ tipo: 'linha', camada: this.camada, a: this.ultimo, b: p })]);
    this.editor.medida(`${fmt(dist(this.ultimo, p))} mm  ∠ ${fmt(ang(this.ultimo, p) * 180 / Math.PI)}°`);
  }
  onValor(t) {
    if (!this.ultimo) return;
    const alvo = this.editor.tela.cursor || this.ultimo;
    const m = t.match(/^(.*?)(?:<|@)(-?\d+(?:[.,]\d+)?)$/);         // "1500<30" ou "1500@30"
    const comp = paraMilimetros(m ? m[1] : t);
    if (comp == null) return;
    const a = m ? parseFloat(m[2].replace(',', '.')) * Math.PI / 180 : ang(this.ultimo, alvo);
    this.onPonto(polar(this.ultimo, a, comp));
  }
  onTecla(ev) { if (ev.key === 'Enter' || ev.key === ' ') { this.reiniciar(); return true; } return false; }
}

export class Polilinha extends Linha {
  static id = 'polilinha'; static nome = 'Polilinha'; static atalho = 'p'; static dica = 'Clique nos vértices · Enter termina · C fecha';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 18l6-10 5 7 7-9"/></svg>';
  reiniciar() { super.reiniciar(); this.pontos = []; }
  onPonto(p) {
    if (this.pontos.length && dist(p, this.pontos[this.pontos.length - 1]) < 1e-6) return;
    this.pontos.push(p); this.ultimo = p; this.editor.snap.ultimo = p;
    this.editor.previa([criar({ tipo: 'polilinha', camada: this.camada, vertices: this.pontos })]);
    this.dica(`${this.pontos.length} vértice(s) · próximo ponto ou comprimento · Enter termina · C fecha`);
  }
  onMover(p) {
    if (!this.pontos.length) return;
    this.editor.previa([criar({ tipo: 'polilinha', camada: this.camada, vertices: [...this.pontos, p] })]);
    this.editor.medida(`${fmt(dist(this.ultimo, p))} mm`);
  }
  terminar(fechar) {
    if (this.pontos.length >= 2) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'polilinha', vertices: this.pontos, fechada: fechar && this.pontos.length > 2 })], 'Polilinha'));
    this.reiniciar();
  }
  onTecla(ev) {
    if (ev.key === 'Enter' || ev.key === ' ') { this.terminar(false); return true; }
    if (ev.key.toLowerCase() === 'c' && this.pontos.length > 2) { this.terminar(true); return true; }
    return false;
  }
}

export class Retangulo extends Ferramenta {
  static id = 'retangulo'; static nome = 'Retângulo'; static atalho = 'r'; static dica = 'Clique no primeiro canto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="6" width="16" height="12"/></svg>';
  reiniciar() { super.reiniciar(); this.a = null; }
  _ret(a, b) { return criar({ tipo: 'polilinha', camada: this.camada, vertices: [a, [b[0], a[1]], b, [a[0], b[1]]], fechada: true }); }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Canto oposto, ou digite largura;altura'); return; }
    this.editor.executar(new ComandoAdicionar([this._ret(this.a, p)], 'Retângulo'));
    this.reiniciar();
  }
  onMover(p) { if (this.a) { this.editor.previa([this._ret(this.a, p)]); this.editor.medida(`${fmt(Math.abs(p[0] - this.a[0]))} × ${fmt(Math.abs(p[1] - this.a[1]))} mm`); } }
  onValor(t) {
    if (!this.a) return;
    const [w, h] = t.split(/[;x]/).map(paraMilimetros);
    if (w == null || h == null) return;
    this.onPonto([this.a[0] + w, this.a[1] + h]);
  }
}

export class Circulo extends Ferramenta {
  static id = 'circulo'; static nome = 'Círculo'; static atalho = 'c'; static dica = 'Clique no centro';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1"/></svg>';
  reiniciar() { super.reiniciar(); this.c = null; }
  onPonto(p) {
    if (!this.c) { this.c = p; this.editor.snap.ultimo = p; this.dica('Ponto do raio, ou digite o raio (D+valor para diâmetro)'); return; }
    const r = dist(this.c, p);
    if (r > 1e-6) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'circulo', centro: this.c, raio: r })], 'Círculo'));
    this.reiniciar();
  }
  onMover(p) { if (this.c) { this.editor.previa([criar({ tipo: 'circulo', camada: this.camada, centro: this.c, raio: dist(this.c, p) })]); this.editor.medida(`R ${fmt(dist(this.c, p))}  Ø ${fmt(2 * dist(this.c, p))}`); } }
  onValor(t) {
    if (!this.c) return;
    const diam = /^d/i.test(t.trim());
    const v = paraMilimetros(t.replace(/^d/i, ''));
    if (v == null) return;
    this.onPonto([this.c[0] + (diam ? v / 2 : v), this.c[1]]);
  }
}

export class ArcoTresPontos extends Ferramenta {
  static id = 'arco'; static nome = 'Arco'; static atalho = 'a'; static dica = 'Arco por três pontos: início';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 18a10 10 0 0 1 16 0"/></svg>';
  reiniciar() { super.reiniciar(); this.pts = []; }
  _arco(a, b, c) {
    // círculo pelos três pontos
    const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
    if (Math.abs(d) < 1e-9) return null;
    const ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d;
    const uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d;
    const centro = [ux, uy], r = dist(centro, a);
    const g = (p) => ((Math.atan2(p[1] - uy, p[0] - ux) * 180 / Math.PI) + 360) % 360;
    let a0 = g(a), a1 = g(c), am = g(b);
    // o arco vai de a até c passando por b: escolhe o sentido que contém b
    const dentro = (x, i, f) => (f >= i ? x >= i && x <= f : x >= i || x <= f);
    if (!dentro(am, a0, a1)) [a0, a1] = [a1, a0];
    return criar({ tipo: 'arco', camada: this.camada, centro, raio: r, inicio: a0, fim: a1 });
  }
  onPonto(p) {
    this.pts.push(p); this.editor.snap.ultimo = p;
    if (this.pts.length === 1) this.dica('Ponto do arco (no meio)');
    else if (this.pts.length === 2) this.dica('Ponto final');
    else { const e = this._arco(...this.pts); if (e) this.editor.executar(new ComandoAdicionar([e], 'Arco')); this.reiniciar(); }
  }
  onMover(p) {
    if (this.pts.length === 1) this.editor.previa([criar({ tipo: 'linha', camada: this.camada, a: this.pts[0], b: p })]);
    else if (this.pts.length === 2) { const e = this._arco(this.pts[0], this.pts[1], p); if (e) this.editor.previa([e]); }
  }
}

export class Texto extends Ferramenta {
  static id = 'texto'; static nome = 'Texto'; static atalho = 't'; static dica = 'Clique onde o texto começa';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 6h14M12 6v13"/></svg>';
  async onPonto(p) {
    const texto = await this.editor.perguntar('Texto', 'Conteúdo', '');
    if (texto == null || !texto.trim()) return;
    this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'texto', camada: 'TEXTO', posicao: p, texto: texto.trim(), altura: this.editor.alturaTexto })], 'Texto'));
  }
}

export class Chamada extends Ferramenta {
  static id = 'chamada'; static nome = 'Chamada'; static atalho = 'h'; static dica = 'Clique no ponto apontado';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 18l8-8h8"/><circle cx="4" cy="18" r="1.3"/></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; }
  async onPonto(p) {
    if (!this.alvo) { this.alvo = p; this.editor.snap.ultimo = p; this.dica('Posição do texto'); return; }
    const texto = await this.editor.perguntar('Chamada', 'Texto da chamada', '');
    if (texto != null && texto.trim()) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'chamada', camada: 'TEXTO', alvo: this.alvo, posicao: p, texto: texto.trim(), altura: this.editor.alturaTexto })], 'Chamada'));
    this.reiniciar();
  }
  onMover(p) { if (this.alvo) this.editor.previa([criar({ tipo: 'chamada', camada: 'TEXTO', alvo: this.alvo, posicao: p, texto: '…', altura: this.editor.alturaTexto })]); }
}

export class Cota extends Ferramenta {
  static id = 'cota'; static nome = 'Cota'; static atalho = 'd'; static dica = 'Primeiro ponto da cota · H/V/A troca o modo (alinhada)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 16V8M20 16V8M4 12h16"/><path d="M7 10l-3 2 3 2M17 10l3 2-3 2"/></svg>';
  reiniciar() { super.reiniciar(); this.p1 = null; this.p2 = null; this.modo = this.modo || 'alinhada'; this.dica(`Primeiro ponto da cota · modo: ${this.modo} (H/V/A troca)`); }
  _cota(p1, p2, p3) {
    let desl = 10;
    if (p3) {
      let [x1, y1] = p1, [x2, y2] = p2;
      if (this.modo === 'h') y2 = y1; else if (this.modo === 'v') x2 = x1;
      const dx = x2 - x1, dy = y2 - y1, c = Math.hypot(dx, dy) || 1;
      desl = (-(dy / c) * (p3[0] - x1) + (dx / c) * (p3[1] - y1)) / this.doc.escala;
      if (Math.abs(desl) < 2) desl = desl < 0 ? -2 : 2;
    }
    return criar({ tipo: 'cota', camada: 'COTA', modo: this.modo, p1, p2, deslocamento: desl, altura: this.editor.alturaTexto });
  }
  onPonto(p) {
    if (!this.p1) { this.p1 = p; this.editor.snap.ultimo = p; this.dica('Segundo ponto'); return; }
    if (!this.p2) { if (dist(p, this.p1) < 1e-6) return; this.p2 = p; this.editor.snap.ultimo = null; this.dica('Posição da linha de cota'); return; }
    this.editor.executar(new ComandoAdicionar([this._cota(this.p1, this.p2, p)], 'Cota'));
    this.reiniciar();
  }
  onMover(p) {
    if (this.p1 && !this.p2) this.editor.previa([criar({ tipo: 'linha', camada: 'COTA', a: this.p1, b: p })]);
    else if (this.p2) this.editor.previa([this._cota(this.p1, this.p2, p)]);
  }
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (k === 'h' || k === 'v' || k === 'a') { this.modo = k === 'a' ? 'alinhada' : k; this.dica(`Modo: ${this.modo}`); if (this.p2) this.onMover(this.editor.tela.cursor || this.p2); return true; }
    return false;
  }
}

export class Hachura extends Ferramenta {
  static id = 'hachura'; static nome = 'Hachura'; static atalho = 'g'; static dica = 'Clique dentro de um contorno fechado';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="4" width="16" height="16"/><path d="M4 12l8-8M4 20L20 4M12 20l8-8"/></svg>';
  onPonto(p) {
    const cand = [...this.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && e.fechada && e.vertices.length >= 3 && this.doc.visivel(e) && dentroDe(p, e.vertices));
    if (!cand.length) { this.dica('Nenhum contorno fechado aqui: desenhe uma polilinha fechada (C) primeiro'); return; }
    cand.sort((a, b) => Math.abs(area(a.vertices)) - Math.abs(area(b.vertices)));
    this.editor.executar(new ComandoAdicionar([criar({ tipo: 'hachura', camada: 'HACHURA', contornos: [cand[0].vertices.map(v => [...v])], padrao: 'aco', atributos: { contorno: cand[0].id } })], 'Hachura'));
  }
}
const area = (pts) => pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + (p[0] * q[1] - q[0] * p[1]); }, 0) / 2;

// ---------------------------------------------------------------- edição

class Transformadora extends Ferramenta {
  /** Ferramentas que agem sobre a seleção: se não há, o primeiro clique seleciona. */
  static grupo = 'edicao';
  reiniciar() { super.reiniciar(); this.base = null; this.ids = [...this.editor.tela.selecao]; this.dica(this.ids.length ? this.constructor.dica : 'Selecione os objetos primeiro (clique ou janela) e depois use a ferramenta'); }
  selecionadas() { return this.ids.map(id => this.doc.get(id)).filter(Boolean); }
  onPonto(p, ev) {
    if (!this.ids.length) {
      const e = this.editor.tela.sob(ev.px);
      if (e) { this.editor.selecionar([e.id]); this.ids = [e.id]; this.dica(this.constructor.dica); }
      return;
    }
    this.passo(p, ev);
  }
}

export class Mover extends Transformadora {
  static id = 'mover'; static nome = 'Mover'; static atalho = 'm'; static dica = 'Ponto base do deslocamento';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/></svg>';
  copiar = false;
  passo(p) {
    if (!this.base) { this.base = p; this.editor.snap.ultimo = p; this.dica('Ponto de destino, ou digite a distância'); return; }
    const d = [p[0] - this.base[0], p[1] - this.base[1]];
    const novas = this.selecionadas().map(e => transladar(e, d));
    if (this.copiar) {
      const copias = novas.map(e => ({ ...e, id: undefined }));
      const cmd = new ComandoAdicionar(copias.map(c => criar(c)), 'Copiar');
      this.editor.executar(cmd);
      // o ponto base continua o mesmo: cada novo destino é medido da referência
      // original (como no AutoCAD), e a seleção copiada é sempre a original
      this.dica('Próximo destino, medido do mesmo ponto base (Esc termina)');
    } else {
      this.editor.executar(new ComandoSubstituir([...novas, ...this._cotasLigadas(d)], 'Mover'));
      this.reiniciar();
    }
  }
  /**
   * Cotas associativas: movendo furos (camada FURO), a cota horizontal cujo ponto está
   * na coluna do furo anda em x, e a vertical cuja linha é a do furo anda em y — desde
   * que todos os furos daquela coluna/linha estejam sendo movidos.
   */
  _cotasLigadas(d) {
    const sel = new Set(this.ids);
    const centro = (e) => e.tipo === 'circulo' ? e.centro
      : e.tipo === 'polilinha' ? (() => { const xs = e.vertices.map(q => q[0]), ys = e.vertices.map(q => q[1]); return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]; })()
      : null;
    if (!this.selecionadas().some(e => e.camada === 'FURO' && centro(e))) return [];
    const furos = [];
    for (const e of this.doc.entidades.values()) {
      if (e.camada !== 'FURO' || (e.tipo !== 'circulo' && e.tipo !== 'polilinha')) continue;
      const c = centro(e); if (c) furos.push({ id: e.id, c, pos: (e.atributos || {}).posicao || null });
    }
    const out = [];
    for (const e of this.doc.entidades.values()) {
      if (e.tipo !== 'cota' || sel.has(e.id) || (e.modo !== 'h' && e.modo !== 'v')) continue;
      const pe = (e.atributos || {}).posicao || null;
      const k = e.modo === 'h' ? 0 : 1;
      const p1 = e.p1.slice(), p2 = e.p2.slice();
      let mudou = false;
      for (const p of [p1, p2]) {
        const ali = furos.filter(f => (!pe || !f.pos || f.pos === pe) && Math.abs(f.c[k] - p[k]) < 0.05);
        if (!ali.length || !ali.every(f => sel.has(f.id))) continue;
        p[k] += d[k]; mudou = true;
      }
      if (mudou) out.push(criar({ ...e, p1, p2 }));
    }
    return out;
  }
  onMover(p) {
    if (!this.base) return;
    const d = [p[0] - this.base[0], p[1] - this.base[1]];
    this.editor.previa([...this.selecionadas().map(e => transladar(e, d)), ...(this.copiar ? [] : this._cotasLigadas(d))]);
    this.editor.medida(`${fmt(dist(this.base, p))} mm  ∠ ${fmt(ang(this.base, p) * 180 / Math.PI)}°`);
  }
  onValor(t) {
    if (!this.base) return;
    const alvo = this.editor.tela.cursor || this.base;
    const m = t.match(/^(.*?)(?:<|@)(-?\d+(?:[.,]\d+)?)$/);
    const comp = paraMilimetros(m ? m[1] : t);
    if (comp == null) return;
    this.passo(polar(this.base, m ? parseFloat(m[2].replace(',', '.')) * Math.PI / 180 : ang(this.base, alvo), comp));
  }
}

export class Copiar extends Mover {
  static id = 'copiar'; static nome = 'Copiar'; static atalho = 'o'; static dica = 'Ponto base da cópia';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="8" y="8" width="12" height="12"/><path d="M4 16V4h12"/></svg>';
  copiar = true;
}

export class Girar extends Transformadora {
  static id = 'girar'; static nome = 'Girar'; static atalho = 'q'; static dica = 'Centro de rotação';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4h-4"/></svg>';
  reiniciar() { super.reiniciar(); this.ref = null; }
  _girar(theta) {
    const c = this.base, co = Math.cos(theta), si = Math.sin(theta);
    const f = (p) => [c[0] + (p[0] - c[0]) * co - (p[1] - c[1]) * si, c[1] + (p[0] - c[0]) * si + (p[1] - c[1]) * co];
    return this.selecionadas().map(e => transformar(e, f, (a) => a + theta * 180 / Math.PI));
  }
  passo(p) {
    if (!this.base) { this.base = p; this.editor.snap.ultimo = p; this.dica('Ponto de referência do ângulo, ou digite o ângulo em graus'); return; }
    if (!this.ref) { this.ref = p; this.dica('Novo ângulo'); return; }
    this.editor.executar(new ComandoSubstituir(this._girar(ang(this.base, p) - ang(this.base, this.ref)), 'Girar'));
    this.reiniciar();
  }
  onMover(p) {
    if (this.base && this.ref) { const th = ang(this.base, p) - ang(this.base, this.ref); this.editor.previa(this._girar(th)); this.editor.medida(`${fmt(th * 180 / Math.PI)}°`); }
    else if (this.base) this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.base, b: p })]);
  }
  onValor(t) {
    if (!this.base) return;
    const g = parseFloat(t.replace(',', '.'));
    if (!isFinite(g)) return;
    this.editor.executar(new ComandoSubstituir(this._girar(g * Math.PI / 180), 'Girar'));
    this.reiniciar();
  }
}

export class Espelhar extends Transformadora {
  static id = 'espelhar'; static nome = 'Espelhar'; static atalho = 'i'; static dica = 'Primeiro ponto do eixo de espelho';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v18" stroke-dasharray="3 2"/><path d="M4 8l5 4-5 4zM20 8l-5 4 5 4z"/></svg>';
  _espelhar(a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1;
    const f = (p) => { const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2; const q = [a[0] + t * dx, a[1] + t * dy]; return [2 * q[0] - p[0], 2 * q[1] - p[1]]; };
    const angEixo = Math.atan2(dy, dx) * 180 / Math.PI;
    return this.selecionadas().map(e => transformar(e, f, (g) => 2 * angEixo - g, 1, true));
  }
  passo(p) {
    if (!this.base) { this.base = p; this.editor.snap.ultimo = p; this.dica('Segundo ponto do eixo'); return; }
    if (dist(p, this.base) < 1e-6) return;
    const novas = this._espelhar(this.base, p);
    this.editor.executar(new ComandoAdicionar(novas.map(e => criar({ ...e, id: undefined })), 'Espelhar'));
    this.reiniciar();
  }
  onMover(p) { if (this.base) this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.base, b: p }), ...this._espelhar(this.base, p)]); }
}

export class Apagar extends Ferramenta {
  static id = 'apagar'; static nome = 'Apagar'; static atalho = 'e'; static grupo = 'edicao'; static dica = 'Clique no objeto para apagar (ou selecione e Del)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>';
  ativar() { super.ativar(); if (this.editor.tela.selecao.size) this.editor.apagarSelecao(); }
  onPonto(p, ev) { const e = this.editor.tela.sob(ev.px); if (e) this.editor.executar(new ComandoRemover([e.id])); }
}

export class Aparar extends Ferramenta {
  static id = 'aparar'; static nome = 'Aparar'; static atalho = 'x'; static grupo = 'edicao'; static dica = 'Clique no trecho da linha a remover (corta nas interseções com outras linhas)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6h16M4 18h16M12 3v18" stroke-dasharray="4 2"/><path d="M9 9l6 6"/></svg>';
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (!e || e.tipo !== 'linha') { this.dica('Aparar funciona em linhas: clique no trecho a remover'); return; }
    const outros = [...this.doc.entidades.values()].filter(o => o.id !== e.id && this.doc.visivel(o));
    const cortes = [];
    for (const o of outros) for (const [s, t] of segmentosDe(o)) { const x = intersecaoSeg(e.a, e.b, s, t); if (x) cortes.push(x); }
    for (const o of outros) if (o.tipo === 'circulo') cortes.push(...intersecaoLinhaCirculo(e.a, e.b, o.centro, o.raio));
    if (!cortes.length) { this.dica('A linha não cruza nenhuma outra'); return; }
    const L = dist(e.a, e.b), ts = cortes.map(c => dist(e.a, c) / L).filter(t => t > 1e-6 && t < 1 - 1e-6).sort((a, b) => a - b);
    const tp = dist(e.a, maisProximoSeg(p, e.a, e.b)) / L;
    const limites = [0, ...ts, 1];
    let i = 0;
    while (i < limites.length - 1 && !(tp >= limites[i] && tp <= limites[i + 1])) i++;
    const at = (t) => [e.a[0] + t * (e.b[0] - e.a[0]), e.a[1] + t * (e.b[1] - e.a[1])];
    const restantes = [];
    if (limites[i] > 1e-6) restantes.push(criar({ ...e, id: undefined, a: e.a, b: at(limites[i]) }));
    if (limites[i + 1] < 1 - 1e-6) restantes.push(criar({ ...e, id: undefined, a: at(limites[i + 1]), b: e.b }));
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar(restantes)], 'Aparar'));
  }
}

function intersecaoLinhaCirculo(a, b, c, r) {
  const d = [b[0] - a[0], b[1] - a[1]], f = [a[0] - c[0], a[1] - c[1]];
  const A = d[0] * d[0] + d[1] * d[1], B = 2 * (f[0] * d[0] + f[1] * d[1]), C = f[0] * f[0] + f[1] * f[1] - r * r;
  let disc = B * B - 4 * A * C;
  if (disc < 0) return [];
  disc = Math.sqrt(disc);
  return [(-B - disc) / (2 * A), (-B + disc) / (2 * A)].filter(t => t >= 0 && t <= 1).map(t => [a[0] + t * d[0], a[1] + t * d[1]]);
}

export class Offset extends Ferramenta {
  static id = 'offset'; static nome = 'Offset (paralela)'; static atalho = 'f'; static grupo = 'edicao'; static dica = 'Offset: clique na linha, arco, círculo ou polilinha; depois do lado desejado (ou digite a distância e clique o lado)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 8h16M4 16h16" /></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; this.distancia = null; }
  onPonto(p, ev) {
    if (!this.alvo) { const e = this.editor.tela.sob(ev.px); if (e && (e.tipo === 'linha' || e.tipo === 'circulo' || e.tipo === 'polilinha' || e.tipo === 'arco')) { this.alvo = e; this.dica(this.distancia != null ? `Distância ${fmt(this.distancia)}: clique do lado desejado` : 'Lado (clique) ou distância (digite)'); } return; }
    const n = this._paralela(p, this.distancia);
    if (n) this.editor.executar(new ComandoAdicionar([n], 'Offset'));
    // a distância digitada vale para os próximos offsets, até Esc
    const d = this.distancia;
    this.reiniciar();
    this.distancia = d;
    if (d != null) this.dica(`Offset ${fmt(d)}: clique na próxima linha (Esc sai)`);
  }
  onValor(t) { const v = paraMilimetros(t); if (v != null) { this.distancia = v; this.dica(`Distância ${fmt(v)}: clique do lado desejado`); } }
  onMover(p) { if (this.alvo) { const n = this._paralela(p, this.distancia); if (n) this.editor.previa([n]); } }
  _paralela(p, dfix) {
    const e = this.alvo;
    if (e.tipo === 'circulo' || e.tipo === 'arco') { const d = dfix ?? Math.abs(dist(p, e.centro) - e.raio); const r = dist(p, e.centro) > e.raio ? e.raio + d : e.raio - d; return r > 0 ? criar({ ...e, id: undefined, raio: r }) : null; }
    if (e.tipo === 'linha') {
      const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L;
      const lado = Math.sign((p[0] - e.a[0]) * nx + (p[1] - e.a[1]) * ny) || 1;
      const d = (dfix ?? Math.abs((p[0] - e.a[0]) * nx + (p[1] - e.a[1]) * ny)) * lado;
      return criar({ ...e, id: undefined, a: [e.a[0] + nx * d, e.a[1] + ny * d], b: [e.b[0] + nx * d, e.b[1] + ny * d] });
    }
    // polilinha: desloca cada vértice pela bissetriz das normais (bom para contornos simples)
    const v = e.vertices, n = v.length, out = [];
    const sinal = area(v) >= 0 ? 1 : -1;
    const dentroP = dentroDe(p, v);
    const d = (dfix ?? Math.min(...segmentosDe(e).map(([s, t]) => distSegP(p, s, t)))) * (dentroP ? -1 : 1) * sinal;
    for (let i = 0; i < n; i++) {
      const prev = v[(i - 1 + n) % n], cur = v[i], next = v[(i + 1) % n];
      const n1 = normal(prev, cur), n2 = normal(cur, next);
      let bx = n1[0] + n2[0], by = n1[1] + n2[1];
      const l = Math.hypot(bx, by) || 1;
      const cosHalf = Math.max(0.2, (n1[0] * bx + n1[1] * by) / l);
      out.push([cur[0] + (bx / l) * d / cosHalf, cur[1] + (by / l) * d / cosHalf]);
    }
    return criar({ ...e, id: undefined, vertices: out });
  }
}
const normal = (a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1; return [-dy / L, dx / L]; };
const distSegP = (p, a, b) => dist(p, maisProximoSeg(p, a, b));

export class Medir extends Ferramenta {
  static id = 'medir'; static nome = 'Medir'; static atalho = 'u'; static grupo = 'medicao'; static dica = 'Primeiro ponto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 17L17 3l4 4L7 21z"/><path d="M8 12l2 2M11 9l2 2M14 6l2 2"/></svg>';
  reiniciar() { super.reiniciar(); this.a = null; }
  onPonto(p) { if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Segundo ponto'); return; } this.editor.aviso(`Distância: ${fmt(dist(this.a, p))} mm  ·  Δx ${fmt(p[0] - this.a[0])}  Δy ${fmt(p[1] - this.a[1])}  ·  ∠ ${fmt(ang(this.a, p) * 180 / Math.PI)}°`); this.reiniciar(); }
  onMover(p) { if (this.a) { this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.a, b: p })]); this.editor.medida(`${fmt(dist(this.a, p))} mm`); } }
}

export const FERRAMENTAS = [Selecionar, Linha, Polilinha, Retangulo, Circulo, ArcoTresPontos, Texto, Cota, Chamada, Hachura,
  Mover, Copiar, Girar, Espelhar, Offset, Aparar, Apagar, Medir];
export const GRUPOS = [['navegacao', 'Nav'], ['desenho', 'Des'], ['edicao', 'Edi'], ['medicao', 'Med']];
