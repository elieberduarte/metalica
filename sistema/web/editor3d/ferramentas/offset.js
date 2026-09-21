// Offset: contorno paralelo de uma face ou de um contorno fechado.
//
// Aponte a face, mova para dentro ou para fora e clique (ou digite a distância).
// O resultado é uma face nova com o contorno paralelo, na mesma camada e no mesmo
// plano da original — a original permanece, que é o que se espera ao fazer o
// contorno de uma chapa a partir de outra.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaOffset extends Ferramenta {
  static id = 'offset';
  static nome = 'Deslocamento';
  static atalho = 'O';
  static grupo = 'edicao';
  static dica = 'Aponte uma face ou contorno para deslocar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 5.5h18v13H3Z"/><path d="M6.5 9h11v6h-11Z" stroke-dasharray="2.5 2"/></svg>`;

  ativar() {
    this.alvo = null;      // { id, iFace, plano, contorno2d }
    this.d = 0;
    this.dica(FerramentaOffset.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  onMover(p) {
    if (!p) return;
    if (!this.alvo) { this.destacar(p); return; }
    this.d = this.distanciaDe(C.noPlano(this.editor, p, this.alvo.plano));
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.alvo) {
      if (!this.iniciar(p)) return;
      this.dica('Mova para dentro ou para fora, clique ou digite a distância');
      this.desenhar();
      return;
    }
    this.aplicar(this.distanciaDe(C.noPlano(this.editor, p, this.alvo.plano)));
  }

  onValor(texto) {
    if (!this.alvo) return false;
    const v = paraMilimetros(texto);
    if (!isFinite(v) || v === 0) return false;
    const sinal = this.d < -0.5 ? -1 : 1;     // ~0 é ruído: sem sinal, para fora
    this.aplicar(v < 0 ? v : Math.abs(v) * sinal);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.alvo && this.d) { this.aplicar(this.d); return true; }
    return false;
  }

  cancelar() {
    if (this.alvo) { this.reiniciar(); this.dica(FerramentaOffset.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  /** Contorno fechado da entidade apontada: face do sólido ou laço de arestas. */
  contornoApontado(p) {
    if (!p || !p.entidade) return null;
    const ent = this.documento && this.documento.get(p.entidade);
    if (!ent) return null;
    if (ent.tipo === 'solido' && ent.faces && ent.faces.length) {
      const k = C.faceDoTriangulo(ent, p.face, p.ponto, p.normal);
      if (k >= 0) return { ent, iFace: k, pts: ent.faces[k].map(i => ent.vertices[i]) };
    }
    if (ent.tipo === 'solido' && (!ent.faces || !ent.faces.length) &&
        ent.vertices && ent.vertices.length >= 3) {
      return { ent, iFace: -1, pts: ent.vertices.map(C.copiar) };
    }
    if (ent.tipo === 'chapa') {
      return { ent, iFace: -1, pts: C.pontosDaEntidade(ent) };
    }
    return null;
  }

  iniciar(p) {
    const achado = this.contornoApontado(p);
    if (!achado || achado.pts.length < 3) {
      this.dica('Nada para deslocar aqui: aponte uma face ou um contorno fechado.');
      return false;
    }
    const n = C.normalDoContorno(achado.pts);
    const plano = C.planoDe(achado.pts[0], n);
    this.alvo = {
      id: achado.ent.id, tipo: achado.ent.tipo, camada: achado.ent.camada,
      iFace: achado.iFace, plano,
      pts3: achado.pts,
      pts2: achado.pts.map(q => C.para2d(plano, q)),
    };
    this.d = 0;
    return true;
  }

  /** Distância assinada do ponto ao contorno: fora positivo, dentro negativo. */
  distanciaDe(ponto) {
    const q = C.para2d(this.alvo.plano, C.projetarNoPlano(this.alvo.plano, ponto));
    const pts = this.alvo.pts2;
    let melhor = Infinity;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      const vx = b[0] - a[0], vy = b[1] - a[1];
      const ll = vx * vx + vy * vy || 1;
      let t = ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / ll;
      t = Math.max(0, Math.min(1, t));
      melhor = Math.min(melhor, Math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t));
    }
    return C.dentroDoContorno(pts, q) ? -melhor : melhor;
  }

  contornoDeslocado(d) {
    return C.offsetContorno(this.alvo.pts2, d)
            .map(([u, v]) => C.para3d(this.alvo.plano, u, v));
  }

  aplicar(d) {
    if (!this.alvo || !isFinite(d) || Math.abs(d) < 1e-6) { this.reiniciar(); return; }
    const pts = this.contornoDeslocado(d);
    const ent = C.solidoDeContorno(pts, {
      nome: 'Deslocamento', camada: this.alvo.camada || 'Estrutura',
      atributos: { origem_offset: this.alvo.id, distancia: d },
    });
    this.executar(C.cmdAdicionar(ent, 'Deslocar contorno'));
    this.reiniciar();
    this.dica(`Deslocamento de ${formatar(Math.abs(d))} criado.`);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.alvo = null; this.d = 0;
    this.limparPrevia();
    this.medida('');
  }

  destacar(p) {
    this.limparPrevia();
    const achado = this.contornoApontado(p);
    if (!achado) { this.medida(''); return; }
    this.previa(C.grupo(C.gLinha(achado.pts, C.CORES.face, { fechada: true })));
  }

  desenhar() {
    this.limparPrevia();
    const pts = this.contornoDeslocado(this.d || 0.001);
    const g = C.grupo(
      C.gLinha(this.alvo.pts3, C.CORES.guia, { fechada: true, tracejada: true }),
      C.gPoligono(pts, C.CORES.face, 0.2),
      C.gLinha(pts, C.CORES.desenho, { fechada: true }));
    const texto = formatar(Math.abs(this.d)) + (this.d < 0 ? '  para dentro' : '  para fora');
    this.medida(texto);
    g.add(C.gRotulo(texto, pts[0]));
    this.previa(g);
  }
}

export default FerramentaOffset;
