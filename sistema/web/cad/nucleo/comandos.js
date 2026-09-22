// Comandos e pilha de desfazer/refazer do CAD 2D.
//
// Mesmo contrato do editor 3D (aplicar/desfazer, rótulo legível), sobre o documento
// 2D. Toda alteração passa por aqui.

import { clonar } from './desenho2d.js';

export class Comando {
  constructor(rotulo = 'Alteração') { this.rotulo = rotulo; }
  aplicar(doc) {}
  desfazer(doc) {}
}

export class ComandoAdicionar extends Comando {
  constructor(entidades, rotulo) {
    super(rotulo || (entidades.length > 1 ? `Adicionar ${entidades.length} objetos` : 'Adicionar'));
    this.entidades = entidades.map(clonar);
  }
  aplicar(doc) { doc.lote(() => { for (const e of this.entidades) doc.add(clonar(e)); }); }
  desfazer(doc) { doc.lote(() => { for (const e of this.entidades) doc.remover(e.id); }); }
}

export class ComandoRemover extends Comando {
  constructor(ids, rotulo) {
    super(rotulo || (ids.length > 1 ? `Apagar ${ids.length} objetos` : 'Apagar'));
    this.ids = [...ids];
    this.guardadas = [];
  }
  aplicar(doc) {
    doc.lote(() => {
      this.guardadas = [];
      for (const id of this.ids) { const e = doc.get(id); if (e) { this.guardadas.push(clonar(e)); doc.remover(id); } }
    });
  }
  desfazer(doc) { doc.lote(() => { for (const e of this.guardadas) doc.add(clonar(e)); }); }
}

/** Substitui campos de várias entidades: {id: {campo: valor}}. Guarda o antes. */
export class ComandoAlterar extends Comando {
  constructor(mudancas, rotulo = 'Alterar') {
    super(rotulo);
    this.mudancas = clonar(mudancas);
    this.antes = null;
  }
  aplicar(doc) {
    doc.lote(() => {
      if (!this.antes) {
        this.antes = {};
        for (const [id, depois] of Object.entries(this.mudancas)) {
          const e = doc.get(id);
          if (!e) continue;
          const g = {};
          for (const k of Object.keys(depois)) g[k] = clonar(e[k]);
          this.antes[id] = g;
        }
      }
      for (const [id, depois] of Object.entries(this.mudancas)) doc.alterar(id, depois);
    });
  }
  desfazer(doc) { doc.lote(() => { for (const [id, antes] of Object.entries(this.antes || {})) doc.alterar(id, antes); }); }
}

/** Troca entidades inteiras (mover, girar, espelhar): recebe as versões novas. */
export class ComandoSubstituir extends Comando {
  constructor(novas, rotulo = 'Transformar') {
    super(rotulo);
    this.novas = novas.map(clonar);
    this.antigas = null;
  }
  aplicar(doc) {
    doc.lote(() => {
      if (!this.antigas) this.antigas = this.novas.map(n => clonar(doc.get(n.id))).filter(Boolean);
      for (const n of this.novas) { const { id, ...campos } = n; doc.alterar(id, campos); }
    });
  }
  desfazer(doc) { doc.lote(() => { for (const a of this.antigas || []) { const { id, ...campos } = a; doc.alterar(id, campos); } }); }
}

export class ComandoAparencia extends Comando {
  constructor(camada, depois, rotulo) {
    super(rotulo || `Camada ${camada}`);
    this.camada = camada; this.depois = { ...depois }; this.antes = null;
  }
  aplicar(doc) {
    const c = doc.camadas.get(this.camada);
    if (!c) return;
    if (!this.antes) { this.antes = {}; for (const k of Object.keys(this.depois)) this.antes[k] = c[k]; }
    doc.alterarCamada(this.camada, this.depois);
  }
  desfazer(doc) { if (this.antes) doc.alterarCamada(this.camada, this.antes); }
}

export class ComandoComposto extends Comando {
  constructor(comandos, rotulo = 'Alteração') { super(rotulo); this.comandos = comandos; }
  aplicar(doc) { doc.lote(() => { for (const c of this.comandos) c.aplicar(doc); }); }
  desfazer(doc) { doc.lote(() => { for (let i = this.comandos.length - 1; i >= 0; i--) this.comandos[i].desfazer(doc); }); }
}

export class Pilha {
  constructor(documento, limite = 300) {
    this.doc = documento; this.limite = limite;
    this.feitos = []; this.desfeitos = [];
    this._ouvintes = new Set();
  }
  aoMudar(fn) { this._ouvintes.add(fn); return () => this._ouvintes.delete(fn); }
  _avisar() { for (const fn of this._ouvintes) fn(this); }
  executar(cmd) {
    cmd.aplicar(this.doc);
    this.feitos.push(cmd);
    if (this.feitos.length > this.limite) this.feitos.shift();
    this.desfeitos = [];
    this._avisar();
    return cmd;
  }
  desfazer() { const c = this.feitos.pop(); if (!c) return null; c.desfazer(this.doc); this.desfeitos.push(c); this._avisar(); return c; }
  refazer() { const c = this.desfeitos.pop(); if (!c) return null; c.aplicar(this.doc); this.feitos.push(c); this._avisar(); return c; }
  limpar() { this.feitos = []; this.desfeitos = []; this._avisar(); }
  get podeDesfazer() { return this.feitos.length > 0; }
  get podeRefazer() { return this.desfeitos.length > 0; }
}
