// Comandos e pilha de desfazer/refazer do CAD 2D.
//
// Mesmo contrato do editor 3D (aplicar/desfazer, rótulo legível), sobre o documento
// 2D. Toda alteração passa por aqui.

import { clonar } from './desenho2d.js';
import { acompanharMalha } from './malha.js';

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
      if (!this.antigas) {
        // o eixo da malha trocado leva a bolinha, o nome e as cotas da malha (nucleo/malha.js); entram no comando,
        // e o Ctrl+Z volta tudo junto
        this.novas.push(...acompanharMalha(doc, this.novas).map(clonar));
        this.antigas = this.novas.map(n => clonar(doc.get(n.id))).filter(Boolean);
      }
      for (const n of this.novas) { const { id, ...campos } = n; doc.alterar(id, campos); }
    });
  }
  desfazer(doc) { doc.lote(() => { for (const a of this.antigas || []) { const { id, ...campos } = a; doc.alterar(id, campos); } }); }
}

/**
 * Troca a escala do desenho (07/10). `modo`:
 *  * 'importado' — o que veio de arquivo importado (atributos.origem) fica do mesmo tamanho no modelo: os campos "de
 *    papel" dele (altura de texto, de cota e de chamada, afastamento da cota, espaçamento de hachura) são convertidos
 *    pela razão das escalas; o que foi feito no CAD acompanha a escala nova. É o que acerta um desenho importado de
 *    outra escala: a cota, o texto e o balão do eixo passam a ter o tamanho dos dele;
 *  * 'tudo' — tudo o que é de papel acompanha a escala (como antes);
 *  * 'nada' — tudo fica do tamanho que está; só o que se desenhar depois sai na escala nova.
 * Nos modos em que o feito no CAD acompanha a escala, o balão do eixo (o círculo da malha, em mm do modelo) muda o raio
 * e continua encostado na ponta do eixo, com o nome no centro.
 */
export class ComandoEscala extends Comando {
  constructor(nova, modo = 'importado', rotulo) {
    super(rotulo || `Escala 1:${nova}`);
    this.nova = nova; this.modo = modo === true ? 'importado' : modo === false ? 'tudo' : modo; this.velha = null; this.antes = null;
  }
  aplicar(doc) {
    doc.lote(() => {
      if (this.velha === null) this.velha = doc.escala;
      const r = this.velha / this.nova;
      const guardar = !this.antes;
      if (guardar) this.antes = {};
      const mudar = (e, m) => {
        if (!Object.keys(m).length) return;
        if (guardar) { const g = this.antes[e.id] || {}; for (const k of Object.keys(m)) if (!(k in g)) g[k] = clonar(e[k]); this.antes[e.id] = g; }
        doc.alterar(e.id, m);
      };
      const ents = [...doc.entidades.values()];
      if (Math.abs(r - 1) > 1e-9) {
        for (const e of ents) {
          const importado = !!(e.atributos && e.atributos.origem);
          const manter = this.modo === 'nada' || (this.modo === 'importado' && importado);
          if (!manter) continue;
          const m = {};
          if ((e.tipo === 'texto' || e.tipo === 'chamada') && e.altura) m.altura = e.altura * r;
          else if (e.tipo === 'cota') { m.altura = (e.altura || 2.5) * r; m.deslocamento = (e.deslocamento || 0) * r; }
          else if (e.tipo === 'hachura' && e.espacamento) m.espacamento = e.espacamento * r;
          mudar(e, m);
        }
        if (this.modo !== 'nada') {
          // o balão do eixo: o raio na escala nova, encostado na mesma ponta do eixo; o nome vai junto
          const eixos = ents.filter(e => e.tipo === 'linha' && e.atributos && e.atributos.malha && e.atributos.eixo != null);
          const f = 1 / r;
          for (const c of ents) {
            if (c.tipo !== 'circulo' || !c.atributos || !c.atributos.bolinha) continue;
            const ln = eixos.find(l => String(l.atributos.eixo) === String(c.atributos.eixo));
            let novo = c.centro;
            if (ln) {
              const pa = Math.hypot(c.centro[0] - ln.a[0], c.centro[1] - ln.a[1]), pb = Math.hypot(c.centro[0] - ln.b[0], c.centro[1] - ln.b[1]);
              const p = pa <= pb ? ln.a : ln.b;
              novo = [p[0] + (c.centro[0] - p[0]) * f, p[1] + (c.centro[1] - p[1]) * f];
            }
            for (const t of ents) {
              if (t.tipo === 'texto' && t.atributos && t.atributos.nome_eixo && String(t.atributos.eixo) === String(c.atributos.eixo)
                  && Math.hypot(t.posicao[0] - c.centro[0], t.posicao[1] - c.centro[1]) <= c.raio) mudar(t, { posicao: novo });
            }
            mudar(c, { raio: c.raio * f, centro: novo });
          }
        }
      }
      doc.mudarEscala(this.nova);
    });
  }
  desfazer(doc) {
    doc.lote(() => {
      for (const [id, g] of Object.entries(this.antes || {})) doc.alterar(id, g);
      doc.mudarEscala(this.velha);
    });
  }
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
