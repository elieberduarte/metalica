// Seção: plano de corte da cena.
//
// O plano sai de uma face apontada ou de um eixo (teclas X, Y, Z ou as setas).
// Depois de definido, a medida digitada desloca o plano ao longo da própria
// normal, Tab inverte o lado cortado e Delete remove o corte. Fica visível o lado
// para onde a normal aponta — é o que a seta da prévia mostra, nos dois caminhos.
//
// O corte é estado de visualização, não do documento: nada entra na pilha de
// desfazer. A ferramenta chama `editor.cena.definirPlanoCorte(plano)` quando o
// núcleo oferece esse método; se não oferecer, cai para `editor.cena.planoCorte`
// e, em último caso, liga o clipping global do renderizador do Three.js.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

// A cena desenha em metros (a `raiz` carrega a escala); o plano do renderizador vive
// no mundo, então a constante do plano precisa da mesma escala.
const escalaDaCena = (cena) => (cena && cena.raiz && cena.raiz.scale) ? cena.raiz.scale.x : 1;

export class FerramentaSecao extends Ferramenta {
  static id = 'secao';
  static nome = 'Seção';
  static atalho = 'X';
  static grupo = 'medicao';
  static dica = 'Clique numa face, ou tecle X, Y ou Z para o plano de corte';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 8.5 12 4.5l8 4-8 4Z"/><path d="M4 8.5v6l8 4 8-4v-6"/><path d="M2.5 15.5h19" stroke-dasharray="3 2"/></svg>`;

  ativar() {
    this.plano = this.constructor.ultimo || null;
    this.invertido = false;
    this.dica(FerramentaSecao.dica);
    this.medida('');
    if (this.plano) this.desenhar();
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  // ------------------------------------------------------------- eventos

  onMover(p, ev) {
    if (!p) return;
    if (this.plano) {
      // arrasto com o botão apertado: o plano desliza ao longo da própria normal até o
      // ponto do mouse projetado nela (o plano fixo num eixo também se move assim)
      if (ev && ev.arrasto && this._arrastoBase) {
        const alvo = this._pontoNaNormal(p);
        if (alvo) this.definir(C.planoDe(alvo, this.plano.normal), true);
      }
      return;
    }
    if (p.entidade && p.normal) {
      this.candidato = C.planoDe(p.ponto, p.normal);
      this.desenhar(true);
    }
  }

  onPonto(p, ev) {
    if (!p) return;
    if (this.plano) {
      // clique parado com o plano definido: não muda nada (o arrasto é que desloca)
      return;
    }
    const n = (p.normal && C.comp(p.normal) > 1e-6) ? p.normal : [0, 0, 1];
    this.definir(C.planoDe(p.ponto, n));
  }

  onSoltar(p, ev) {
    if (!this.plano) { this.onPonto(p, ev); return; }
    if (this._arrastoBase) {
      const alvo = this._pontoNaNormal(p);
      if (alvo) this.definir(C.planoDe(alvo, this.plano.normal));
    }
    this._arrastoBase = null;
  }

  /** Ponto do plano mais perto do raio do mouse, medido ao longo da normal. */
  _pontoNaNormal(p) {
    if (!this.plano) return null;
    const base = this._arrastoBase ? this._arrastoBase.origem : this.plano.origem;
    const t = C.distanciaNaReta(this.editor, p, base, this.plano.normal);
    if (!isFinite(t)) return null;
    return C.add(base, C.mul(this.plano.normal, t));
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    const k = String(ev.key || '').toLowerCase();
    let eixo = null;
    // com o plano já definido, as setas deslocam (100 mm; Shift: 10 mm); sem plano, escolhem o eixo
    if (this.plano && (ev.key === 'ArrowUp' || ev.key === 'ArrowRight')) { this.deslocar(ev.shiftKey ? 10 : 100); return true; }
    if (this.plano && (ev.key === 'ArrowDown' || ev.key === 'ArrowLeft')) { this.deslocar(ev.shiftKey ? -10 : -100); return true; }
    if (k === 'x' || ev.key === 'ArrowRight') eixo = 'x';
    else if (k === 'y' || ev.key === 'ArrowLeft') eixo = 'y';
    else if (k === 'z' || ev.key === 'ArrowUp') eixo = 'z';
    if (eixo) {
      const c = this.centroDoModelo();
      this.definir(C.planoDe(c, C.EIXOS[eixo].vetor));
      return true;
    }
    if ((k === 'g' || ev.key === 'Enter') && this.plano && this.editor && typeof this.editor.gerarDesenhoDoCorte === 'function') {
      this.editor.gerarDesenhoDoCorte(this.plano);
      return true;
    }
    if (ev.key === 'Tab' && this.plano) {
      this.definir(C.planoDe(this.plano.origem, C.mul(this.plano.normal, -1)));
      return true;
    }
    if ((ev.key === 'Delete' || ev.key === 'Backspace')) { this.limpar(); return true; }
    return false;
  }

  onValor(texto) {
    if (!this.plano) return false;
    const d = paraMilimetros(texto);
    if (!isFinite(d)) return false;
    this.definir(C.planoDe(C.add(this.plano.origem, C.mul(this.plano.normal, d)),
                           this.plano.normal));
    return true;
  }

  cancelar() {
    if (this.plano) { this.limpar(); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  centroDoModelo() {
    const doc = this.documento;
    if (doc && typeof doc.caixa === 'function') {
      const cx = doc.caixa();
      if (Array.isArray(cx) && cx.length === 2) return C.meio(cx[0], cx[1]);
      if (cx && cx.min && cx.max) return C.meio(cx.min, cx.max);
    }
    return [0, 0, 0];
  }

  tamanhoDoModelo() {
    const doc = this.documento;
    let min = [0, 0, 0], max = [0, 0, 0];
    if (doc && typeof doc.caixa === 'function') {
      const cx = doc.caixa();
      if (Array.isArray(cx) && cx.length === 2) { min = cx[0]; max = cx[1]; }
      else if (cx && cx.min) { min = cx.min; max = cx.max; }
    }
    const d = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
    return Math.max(d, 4000);
  }

  definir(plano, arrastando = false) {
    if (!arrastando) this._arrastoBase = { origem: C.copiar(plano.origem) };
    this.plano = plano;
    this.constructor.ultimo = plano;
    this.aplicarNaCena(plano);
    this.medida('corte em ' + this.descrever(plano));
    this.dica('Arraste o plano ou digite um afastamento para deslocar · setas ±100 mm (Shift ±10) · Tab inverte · Delete remove · G gera o desenho 2D');
    this.desenhar();
  }

  /** Desloca o plano `d` mm ao longo da normal. */
  deslocar(d) {
    if (!this.plano) return;
    this.definir(C.planoDe(C.add(this.plano.origem, C.mul(this.plano.normal, d)), this.plano.normal));
  }

  limpar() {
    this.plano = null;
    this.constructor.ultimo = null;
    this.aplicarNaCena(null);
    this.limparPrevia();
    this.medida('');
    this.dica(FerramentaSecao.dica);
  }

  descrever(p) {
    const e = C.eixoInferido(p.normal);
    const o = p.origem;
    if (e === 'x') return `X = ${formatar(o[0])}`;
    if (e === 'y') return `Y = ${formatar(o[1])}`;
    if (e === 'z') return `Z = ${formatar(o[2])}`;
    return `plano livre em (${formatar(o[0])}, ${formatar(o[1])}, ${formatar(o[2])})`;
  }

  /** Entrega o plano ao núcleo, pelo caminho que estiver disponível. */
  aplicarNaCena(plano) {
    const cena = this.editor && this.editor.cena;
    const dado = plano ? { origem: C.copiar(plano.origem), normal: C.copiar(plano.normal),
                           constante: -C.dot(plano.normal, plano.origem) } : null;
    if (cena && typeof cena.definirPlanoCorte === 'function') {
      cena.definirPlanoCorte(dado);
      this.meioUsado = 'cena.definirPlanoCorte';
      return;
    }
    if (cena && 'planoCorte' in cena) {
      cena.planoCorte = dado;
      this.meioUsado = 'cena.planoCorte';
      if (typeof cena.atualizar === 'function') cena.atualizar();
      return;
    }
    // último recurso: clipping global do renderizador
    const r = (this.editor && (this.editor.renderizador || this.editor.renderer)) ||
              (cena && (cena.renderizador || cena.renderer));
    if (r) {
      r.localClippingEnabled = true;
      r.clippingPlanes = plano
        // Mesma convenção do núcleo e da seta da prévia: fica visível o lado para
        // onde a normal aponta. O Three.js corta onde n·p + c < 0.
        ? [new C.THREE.Plane(C.tresJS(plano.normal).normalize(),
                             -C.dot(plano.normal, plano.origem) * escalaDaCena(cena))]
        : [];
      if (cena && typeof cena.pedirQuadro === 'function') cena.pedirQuadro();
      this.meioUsado = 'renderizador.clippingPlanes';
      return;
    }
    this.meioUsado = 'nenhum';
    console.info('Seção: o núcleo ainda não expõe definirPlanoCorte; o plano foi só ' +
                 'desenhado como prévia.');
  }

  desenhar(candidato = false) {
    this.limparPrevia();
    const p = candidato ? this.candidato : this.plano;
    if (!p) return;
    const r = this.tamanhoDoModelo() * 0.6;
    const cantos = [C.para3d(p, -r, -r), C.para3d(p, r, -r),
                    C.para3d(p, r, r), C.para3d(p, -r, r)];
    const cor = candidato ? C.CORES.guia : C.CORES.aviso;
    const g = C.grupo(C.gPoligono(cantos, cor, 0.10),
                      C.gLinha(cantos, cor, { fechada: true }));
    // seta da normal, mostrando o lado que fica visível
    const c = C.meio(cantos[0], cantos[2]);
    g.add(C.gLinha([c, C.add(c, C.mul(p.normal, r * 0.25))], cor));
    if (!candidato) g.add(C.gRotulo(this.descrever(p), c, '#c0392b'));
    this.previa(g);
  }
}

FerramentaSecao.ultimo = null;

export default FerramentaSecao;
