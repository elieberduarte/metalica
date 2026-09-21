// Retângulo: dois cliques no plano.
//
// O plano é o da face sob o cursor no primeiro clique; não havendo face, o plano
// de trabalho do editor (por padrão o plano base XY na altura do ponto). A medida
// digitada aceita "2000;1000" — largura e altura no plano.

import { Ferramenta, listaDeMedidas, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaRetangulo extends Ferramenta {
  static id = 'retangulo';
  static nome = 'Retângulo';
  static atalho = 'R';
  static grupo = 'desenho';
  static dica = 'Clique para o primeiro canto';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<rect x="3.5" y="6" width="17" height="12" rx="0.8"/><circle cx="3.5" cy="18" r="1.6"/><circle cx="20.5" cy="6" r="1.6"/></svg>`;

  ativar() {
    this.plano = null;
    this.canto = null;
    this.atual = null;
    this.dica(FerramentaRetangulo.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  onMover(p) {
    if (!p) return;
    if (!this.canto) { this.atual = C.copiar(p.ponto); this.desenhar(); return; }
    this.atual = C.noPlano(this.editor, p, this.plano);
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.canto) {
      this.plano = C.planoDoPonto(this.editor, p);
      this.canto = C.copiar(p.ponto);
      this.plano.origem = this.canto;
      C.ancorar(this.editor, this.canto);
      this.atual = this.canto;
      this.dica('Clique para o canto oposto ou digite "largura;altura"');
      this.desenhar();
      return;
    }
    const q = C.noPlano(this.editor, p, this.plano);
    const [u, v] = C.para2d(this.plano, q);
    this.criar(u, v);
  }

  onValor(texto) {
    if (!this.canto) return false;
    const m = listaDeMedidas(texto);
    let u, v;
    if (m.length >= 2 && isFinite(m[0]) && isFinite(m[1])) {
      const atual = this.atual ? C.para2d(this.plano, this.atual) : [1, 1];
      u = Math.abs(m[0]) * (atual[0] < 0 ? -1 : 1);
      v = Math.abs(m[1]) * (atual[1] < 0 ? -1 : 1);
    } else if (m.length === 1 && isFinite(m[0])) {
      const lado = paraMilimetros(texto);
      u = lado; v = lado;                       // quadrado, quando vem só um valor
    } else return false;
    if (!u || !v) return false;
    this.criar(u, v);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.canto && this.atual) {
      const [u, v] = C.para2d(this.plano, this.atual);
      if (u && v) { this.criar(u, v); return true; }
    }
    return false;
  }

  cancelar() {
    if (this.canto) { this.reiniciar(); this.dica(FerramentaRetangulo.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  cantos(u, v) {
    const P = this.plano;
    return [C.para3d(P, 0, 0), C.para3d(P, u, 0), C.para3d(P, u, v), C.para3d(P, 0, v)];
  }

  criar(u, v) {
    if (Math.abs(u) < 1e-6 || Math.abs(v) < 1e-6) return;
    const pts = this.cantos(u, v);
    // contorno sempre anti-horário visto do lado da normal do plano
    const ordenado = (u * v >= 0) ? pts : pts.slice().reverse();
    const ent = C.solidoDeContorno(ordenado, {
      nome: 'Retângulo', camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura' });
    this.executar(C.cmdAdicionar(ent, 'Desenhar retângulo'));
    this.reiniciar();
    this.dica(FerramentaRetangulo.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.canto = null;
    this.atual = null;
    this.plano = null;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (!this.canto) {
      if (this.atual) g.add(C.gPonto(this.atual, C.CORES.desenho));
      this.previa(g);
      return;
    }
    const [u, v] = C.para2d(this.plano, this.atual || this.canto);
    const pts = this.cantos(u, v);
    g.add(C.gPoligono(pts));
    g.add(C.gLinha(pts, C.CORES.desenho, { fechada: true }));
    g.add(C.gPonto(this.canto, C.CORES.desenho));
    const texto = `${formatar(Math.abs(u))} ; ${formatar(Math.abs(v))}`;
    this.medida(texto);
    g.add(C.gRotulo(texto, C.meio(pts[0], pts[2])));
    this.previa(g);
  }
}

export default FerramentaRetangulo;
