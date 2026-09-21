// Girar (transferidor): plano, centro, referência e ângulo.
//
// O primeiro clique fixa o centro — e, com ele, o plano: a face sob o cursor, ou
// o plano forçado pelas setas do teclado (→ X, ← Y, ↑ Z). O segundo clique dá a
// direção de referência (o zero grau). Depois, mover define o ângulo, que também
// pode ser digitado. Com Ctrl a seleção é copiada, e "*n" faz o array radial.

import { Ferramenta, formatar } from './base.js';
import * as C from './_comum.js';

const GRAU = Math.PI / 180;

export class FerramentaGirar extends Ferramenta {
  static id = 'girar';
  static nome = 'Girar';
  static atalho = 'Q';
  static grupo = 'edicao';
  static dica = 'Selecione e clique no centro de giro';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M20 12a8 8 0 1 1-3.1-6.3"/><path d="M20.4 4.6v4.2h-4.2"/><circle cx="12" cy="12" r="1.3"/></svg>`;

  ativar() {
    this.centro = null;
    this.plano = null;
    this.ref = null;         // direção de referência, unitária
    this.raio = 1000;
    this.angulo = 0;
    this.copia = false;
    this.eixoForcado = null;
    this.ultimoArray = null;
    this.ids = C.idsSelecionados(this.editor);
    this.dica(this.ids.length ? FerramentaGirar.dica
                              : 'Nada selecionado: selecione o que girar');
    this.medida('');
  }

  desativar() { this.reiniciar(); this.ultimoArray = null; }

  // ------------------------------------------------------------- eventos

  onMover(p, ev) {
    if (!p) return;
    if (!this.centro) { this.pre = C.copiar(p.ponto); this.desenhar(); return; }
    if (ev && ev.ctrlKey) this.copia = true;
    const q = C.noPlano(this.editor, p, this.plano);
    const v = C.sub(q, this.centro);
    if (C.comp(v) < 1e-6) return;
    if (!this.ref) { this.raio = C.comp(v); this.dirAtual = C.normalizar(v); }
    else this.angulo = this.anguloDe(v);
    this.desenhar();
  }

  onPonto(p, ev) {
    if (!p) return;
    if (!this.centro) {
      this.ids = C.idsSelecionados(this.editor);
      if (!this.ids.length) { this.dica('Selecione o que girar antes.'); return; }
      this.plano = this.eixoForcado
        ? C.planoDe(p.ponto, C.EIXOS[this.eixoForcado].vetor)
        : C.planoDoPonto(this.editor, p);
      this.centro = C.copiar(p.ponto);
      this.plano.origem = this.centro;
      C.ancorar(this.editor, this.centro);
      this.ultimoArray = null;
      this.copia = !!(ev && ev.ctrlKey);
      this.dica('Clique para a direção de referência (0°)');
      this.desenhar();
      return;
    }
    const v = C.sub(C.noPlano(this.editor, p, this.plano), this.centro);
    if (C.comp(v) < 1e-6) return;
    if (!this.ref) {
      this.ref = C.normalizar(v);
      this.raio = C.comp(v);
      this.angulo = 0;
      this.dica('Mova para girar, clique ou digite o ângulo em graus');
      this.desenhar();
      return;
    }
    this.aplicar(this.anguloDe(v));
  }

  onValor(texto) {
    const t = String(texto).trim();
    if (this.ultimoArray) {
      const arr = t.match(/^([*/xX])\s*(\d+)$/);
      if (arr) { this.arranjar(arr[1].toLowerCase() === '/' ? 'dividir' : 'multiplicar',
                                parseInt(arr[2], 10)); return true; }
    }
    if (!this.centro || !this.ref) return false;
    const g = parseFloat(t.replace(',', '.').replace(/[°º]/g, ''));
    if (!isFinite(g) || g === 0) return false;
    this.aplicar(g);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (this.ultimoArray && (ev.key === '*' || ev.key === '/') &&
        C.abrirCaixaDeMedidas(this.editor, ev.key)) return true;
    const e = C.lerEixoTecla(ev);
    if (e !== undefined && !this.centro) {
      this.eixoForcado = e;
      this.dica(e ? `Plano perpendicular ao eixo ${C.EIXOS[e].nome}: clique no centro`
                  : FerramentaGirar.dica);
      return true;
    }
    if (ev.key === 'Control' && !ev.repeat) { this.copia = !this.copia; this.desenhar(); return true; }
    if (ev.key === 'Enter' && this.ref && this.angulo) { this.aplicar(this.angulo); return true; }
    return false;
  }

  cancelar() {
    if (this.ref) { this.ref = null; this.angulo = 0; this.dica('Clique para a direção de referência (0°)'); this.desenhar(); return; }
    if (this.centro) { this.reiniciar(); this.dica(FerramentaGirar.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  anguloDe(v) {
    const u = C.normalizar(v);
    const cos = Math.max(-1, Math.min(1, C.dot(u, this.ref)));
    const sen = C.dot(C.cross(this.ref, u), this.plano.normal);
    return Math.atan2(sen, cos) / GRAU;
  }

  girador(graus) {
    const n = this.plano.normal, c = this.centro;
    const a = graus * GRAU, co = Math.cos(a), si = Math.sin(a);
    const rv = (v) => C.add(C.add(C.mul(v, co), C.mul(C.cross(n, v), si)),
                            C.mul(n, C.dot(n, v) * (1 - co)));
    return { fp: (q) => C.add(c, rv(C.sub(q, c))), fv: rv };
  }

  entidades() {
    return this.ids.map(id => this.documento && this.documento.get(id)).filter(Boolean);
  }

  comandosPara(graus, copias, rotulo) {
    const cmds = [], novos = [];
    if (copias <= 0) {
      const { fp, fv } = this.girador(graus);
      for (const ent of this.entidades()) {
        cmds.push(C.cmdAlterar(ent.id, C.camposTransformados(ent, fp, fv), rotulo));
      }
      return { cmds, novos };
    }
    for (let k = 1; k <= copias; k++) {
      const { fp, fv } = this.girador(graus * k);
      const lote = this.entidades().map(ent => {
        const c = C.clonarEntidade(ent);
        Object.assign(c, C.camposTransformados(ent, fp, fv));
        novos.push(c.id);
        return c;
      });
      if (lote.length) cmds.push(C.cmdAdicionar(lote, rotulo));
    }
    return { cmds, novos };
  }

  aplicar(graus) {
    if (!this.ids.length || !isFinite(graus) || Math.abs(graus) < 1e-6) { this.reiniciar(); return; }
    if (this.copia) {
      const { cmds, novos } = this.comandosPara(graus, 1, 'Copiar girando');
      this.executar(C.cmdComposto(cmds, 'Copiar girando'));
      this.ultimoArray = { graus, ids: this.ids.slice(), centro: this.centro,
                           plano: this.plano, ref: this.ref, criadas: novos };
      this.reiniciar();
      this.medida(`cópia a ${C.num(graus)}°`);
      this.dica('Cópia girada — digite "*6" para o array radial');
      return;
    }
    const { cmds } = this.comandosPara(graus, 0, 'Girar');
    this.executar(C.cmdComposto(cmds, 'Girar'));
    this.ultimoArray = null;
    this.reiniciar();
    this.dica(FerramentaGirar.dica);
  }

  arranjar(modo, n) {
    if (!this.ultimoArray || n < 1) return;
    const a = this.ultimoArray;
    if (this.editor && typeof this.editor.desfazer === 'function') this.editor.desfazer();
    this.ids = a.ids.slice();
    this.centro = a.centro; this.plano = a.plano; this.ref = a.ref;
    const passo = modo === 'dividir' ? a.graus / n : a.graus;
    const { cmds, novos } = this.comandosPara(passo, n, `Array radial ${n}`);
    this.executar(C.cmdComposto(cmds, 'Array radial'));
    this.ultimoArray = { ...a, graus: a.graus, criadas: novos };
    this.centro = null; this.plano = null; this.ref = null;   // pronto para um giro novo
    this.dica(`${n} cópias a cada ${C.num(passo)}°`);
    this.medida(`${n} × ${C.num(passo)}°`);
    this.limparPrevia();
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.centro = null; this.plano = null; this.ref = null;
    this.angulo = 0; this.copia = false;
    this.limparPrevia();
    this.medida('');
  }

  /** Círculo do transferidor com marcas a cada 15°. */
  transferidor() {
    const g = C.grupo();
    const r = this.raio || 1000;
    const pts = [];
    for (let i = 0; i <= 72; i++) {
      const a = (i / 72) * Math.PI * 2;
      pts.push(C.para3d(this.plano, r * Math.cos(a), r * Math.sin(a)));
    }
    g.add(C.gLinha(pts, C.CORES.guia));
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2;
      const k = i % 6 === 0 ? 0.88 : 0.95;
      g.add(C.gLinha([C.para3d(this.plano, r * k * Math.cos(a), r * k * Math.sin(a)),
                      C.para3d(this.plano, r * Math.cos(a), r * Math.sin(a))], C.CORES.guia));
    }
    return g;
  }

  desenhar() {
    this.limparPrevia();
    if (!this.centro) {
      if (this.pre) this.previa(C.grupo(C.gPonto(this.pre, C.CORES.desenho)));
      return;
    }
    const g = C.grupo(this.transferidor(), C.gPonto(this.centro, C.CORES.desenho));
    const base = this.ref || this.dirAtual || this.plano.ex;
    g.add(C.gLinha([this.centro, C.add(this.centro, C.mul(base, this.raio))], C.CORES.guia));
    if (this.ref) {
      const { fp, fv } = this.girador(this.angulo);
      g.add(C.gLinha([this.centro, fp(C.add(this.centro, C.mul(this.ref, this.raio)))],
                     C.CORES.desenho));
      for (const ent of this.entidades()) {
        const pts = C.pontosDaEntidade(ent).map(fp);
        if (pts.length >= 2) g.add(C.gLinha(pts, C.CORES.ok, { fechada: pts.length > 2 }));
      }
      const texto = `${C.num(this.angulo)}°` + (this.copia ? '  ·  cópia' : '');
      this.medida(texto);
      g.add(C.gRotulo(texto, C.add(this.centro, C.mul(fv(this.ref), this.raio * 0.6))));
    } else {
      this.medida('raio ' + formatar(this.raio));
    }
    this.previa(g);
  }
}

export default FerramentaGirar;
