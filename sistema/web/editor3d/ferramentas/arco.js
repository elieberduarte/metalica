// Arco por três pontos: início, fim e bojo.
//
// Os dois primeiros cliques dão a corda; o terceiro (ou a medida digitada) dá a
// flecha, isto é, o afastamento do meio da corda até o arco. O arco sai como
// polilinha de N segmentos (padrão 12), no plano do primeiro clique.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaArco extends Ferramenta {
  static id = 'arco';
  static nome = 'Arco';
  static atalho = 'A';
  static grupo = 'desenho';
  static dica = 'Clique para o início do arco';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 17.5a9.5 9.5 0 0 1 16 0"/><path d="M4 17.5h16" stroke-dasharray="2.5 2.5"/><circle cx="4" cy="17.5" r="1.5"/><circle cx="20" cy="17.5" r="1.5"/></svg>`;

  ativar() {
    this.plano = null;
    this.a = null; this.b = null; this.c = null;
    this.atual = null;
    this.dica(FerramentaArco.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  get segmentos() { return this.constructor.segmentos || 12; }

  onMover(p) {
    if (!p) return;
    this.atual = this.plano ? this.pontoNoPlano(p) : C.copiar(p.ponto);
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.a) {
      this.plano = C.planoDoPonto(this.editor, p);
      this.a = C.copiar(p.ponto);
      this.plano.origem = this.a;
      C.ancorar(this.editor, this.a);
      this.dica('Clique para o fim do arco ou digite o comprimento da corda');
      this.desenhar();
      return;
    }
    const q = this.pontoNoPlano(p);
    if (!this.b) {
      if (C.iguais(this.a, q, 0.5)) return;
      this.b = q;
      this.dica('Clique para o bojo ou digite a flecha');
      this.desenhar();
      return;
    }
    this.c = q;
    this.criar();
  }

  onValor(texto) {
    const t = String(texto).trim().toLowerCase();
    const ms = t.match(/^(\d+)\s*(s|seg|segmentos?)$/);
    if (ms) {
      this.constructor.segmentos = Math.max(1, Math.min(180, parseInt(ms[1], 10)));
      this.desenhar();
      return true;
    }
    const v = paraMilimetros(t);
    if (!isFinite(v)) return false;
    if (this.a && !this.b) {
      // comprimento da corda na direção corrente do mouse
      if (!this.atual || C.iguais(this.atual, this.a, 1e-6)) return false;
      this.b = C.add(this.a, C.mul(C.normalizar(C.sub(this.atual, this.a)), Math.abs(v)));
      this.dica('Clique para o bojo ou digite a flecha');
      this.desenhar();
      return true;
    }
    if (this.a && this.b) {
      const lado = this.ladoCorrente();
      this.c = C.add(C.meio(this.a, this.b), C.mul(lado, v));
      this.criar();
      return true;
    }
    return false;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.a && this.b && this.atual) { this.c = this.atual; this.criar(); return true; }
    return false;
  }

  cancelar() {
    if (this.b) { this.b = null; this.c = null; this.dica('Clique para o fim do arco'); this.desenhar(); return; }
    if (this.a) { this.reiniciar(); this.dica(FerramentaArco.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  /**
   * Ponto do cursor no plano do arco. No passo do bojo, a inferência de eixo (a
   * partir do fim da corda) só atrapalha — puxaria o bojo para a própria reta da
   * corda —, então ali vale o raio do cursor contra o plano.
   */
  pontoNoPlano(p) {
    if (this.b && /^eixo_/.test(p.tipoSnap || '')) {
      const q = C.raioContraPlano(this.editor, p, this.plano);
      if (q) return q;
    }
    return C.noPlano(this.editor, p, this.plano);
  }

  /** Perpendicular unitária à corda, no plano, apontando para o lado do mouse. */
  ladoCorrente() {
    const dir = C.normalizar(C.sub(this.b, this.a));
    let perp = C.normalizar(C.cross(this.plano.normal, dir));
    if (this.atual) {
      const d = C.sub(this.atual, C.meio(this.a, this.b));
      if (C.dot(d, perp) < 0) perp = C.mul(perp, -1);
    }
    return perp;
  }

  /** Pontos do arco por três pontos, no plano corrente. */
  pontosDoArco(c) {
    const P = this.plano;
    const A = C.para2d(P, this.a), B = C.para2d(P, this.b), M = C.para2d(P, c);
    const d = 2 * (A[0] * (B[1] - M[1]) + B[0] * (M[1] - A[1]) + M[0] * (A[1] - B[1]));
    if (Math.abs(d) < 1e-9) { this.ultimoRaio = Infinity; return [this.a, c, this.b]; }   // colinear: reta
    const sa = A[0] * A[0] + A[1] * A[1], sb = B[0] * B[0] + B[1] * B[1];
    const sm = M[0] * M[0] + M[1] * M[1];
    const ux = (sa * (B[1] - M[1]) + sb * (M[1] - A[1]) + sm * (A[1] - B[1])) / d;
    const uy = (sa * (M[0] - B[0]) + sb * (A[0] - M[0]) + sm * (B[0] - A[0])) / d;
    const r = Math.hypot(A[0] - ux, A[1] - uy);
    const ang = (p) => Math.atan2(p[1] - uy, p[0] - ux);
    const a0 = ang(A), a1 = ang(M), a2 = ang(B);
    const dois = Math.PI * 2;
    const rel = (x) => ((x - a0) % dois + dois) % dois;
    const antiHorario = rel(a1) < rel(a2);
    let varre = antiHorario ? rel(a2) : rel(a2) - dois;
    const n = Math.max(2, this.segmentos);
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const t = a0 + varre * (i / n);
      pts.push(C.para3d(P, ux + r * Math.cos(t), uy + r * Math.sin(t)));
    }
    this.ultimoRaio = r;
    return pts;
  }

  criar() {
    const pts = this.pontosDoArco(this.c);
    if (pts.length < 2) return;
    const ent = C.solidoDeArestas(pts, {
      nome: 'Arco',
      camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura',
      atributos: { forma: 'arco', raio: isFinite(this.ultimoRaio) ? this.ultimoRaio : 0, segmentos: this.segmentos },
    });
    this.executar(C.cmdAdicionar(ent, 'Desenhar arco'));
    this.reiniciar();
    this.dica(FerramentaArco.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.a = null; this.b = null; this.c = null; this.atual = null; this.plano = null;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.a) g.add(C.gPonto(this.a, C.CORES.desenho));
    if (this.a && !this.b) {
      if (this.atual) {
        g.add(C.gLinha([this.a, this.atual], C.CORES.desenho));
        this.medida('corda ' + formatar(C.dist(this.a, this.atual)));
      }
    } else if (this.a && this.b) {
      g.add(C.gPonto(this.b, C.CORES.desenho));
      g.add(C.gLinha([this.a, this.b], C.CORES.guia, { tracejada: true }));
      const bojo = this.c || this.atual || C.meio(this.a, this.b);
      const pts = this.pontosDoArco(bojo);
      g.add(C.gLinha(pts, C.CORES.desenho));
      const flecha = C.dist(C.meio(this.a, this.b), C.projetarNoPlano(this.plano, bojo));
      const texto = `flecha ${formatar(flecha)} · raio ${formatar(this.ultimoRaio || 0)}`;
      this.medida(texto);
      g.add(C.gRotulo(texto, pts[Math.floor(pts.length / 2)]));
    } else if (this.atual) {
      g.add(C.gPonto(this.atual, C.CORES.desenho));
    }
    this.previa(g);
  }
}

FerramentaArco.segmentos = 12;

export default FerramentaArco;
