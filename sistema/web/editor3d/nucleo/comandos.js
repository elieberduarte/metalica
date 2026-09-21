// Comandos e pilha de desfazer/refazer.
//
// Toda alteração do documento passa por um comando com `aplicar` e `desfazer`. É o que
// dá um desfazer confiável: nenhuma ferramenta mexe no documento diretamente. Cada
// comando tem um rótulo legível, que é o que aparece no menu de desfazer.

import { clonar, CAMPOS_GEOMETRICOS, criar } from './documento.js';

export class Comando {
  constructor(rotulo = 'Alteração') { this.rotulo = rotulo; }
  aplicar(doc) {}                 // executa
  desfazer(doc) {}                // desfaz exatamente
  /** Ids afetados — a cena reconstrói só estes. */
  ids() { return []; }
  /** Ids que devem ficar selecionados depois de aplicar. */
  selecao() { return this.ids(); }
}

// ----------------------------------------------------------------- básicos

export class ComandoAdicionar extends Comando {
  /** @param entidades registro ou lista de registros de entidade. */
  constructor(entidades, rotulo) {
    const lista = Array.isArray(entidades) ? entidades : [entidades];
    // Materializa já aqui para que o id exista antes de aplicar — quem chamou pode
    // querer referenciar a entidade nova (por exemplo, para selecioná-la).
    const prontas = lista.map(e => (e && e.id && e.tipo ? e : criar(e)));
    super(rotulo || (prontas.length === 1
      ? `Adicionar ${rotuloDe(prontas[0])}`
      : `Adicionar ${prontas.length} objetos`));
    this.entidades = prontas;
  }
  aplicar(doc) {
    doc.lote(() => { for (const e of this.entidades) doc.add(clonar(e)); });
  }
  desfazer(doc) {
    doc.lote(() => { for (const e of this.entidades) doc.remover(e.id); });
  }
  ids() { return this.entidades.map(e => e.id); }
}

export class ComandoRemover extends Comando {
  /** @param ids id ou lista de ids a remover. */
  constructor(ids, rotulo) {
    const lista = Array.isArray(ids) ? ids.slice() : [ids];
    super(rotulo || (lista.length === 1 ? 'Apagar objeto' : `Apagar ${lista.length} objetos`));
    this.alvos = lista;
    this.guardadas = [];          // preenchido no aplicar, para poder devolver igual
  }
  aplicar(doc) {
    doc.lote(() => {
      this.guardadas = [];
      for (const id of this.alvos) {
        const e = doc.get(id);
        if (e) { this.guardadas.push(clonar(e)); doc.remover(id); }
      }
    });
  }
  desfazer(doc) {
    doc.lote(() => { for (const e of this.guardadas) doc.add(clonar(e)); });
  }
  ids() { return this.alvos.slice(); }
  selecao() { return []; }
}

export class ComandoAlterar extends Comando {
  /**
   * Guarda antes e depois dos campos alterados.
   * @param mudancas  {id: {campo: valor}}  ou  [{id, depois:{...}}]
   */
  constructor(mudancas, rotulo, terceiro) {
    // Também aceita (id, campos, rotulo), que é como as ferramentas o chamam.
    if (typeof mudancas === 'string') {
      const id = mudancas;
      mudancas = { [id]: rotulo || {} };
      rotulo = terceiro;
    }
    super(rotulo || 'Alterar propriedades');
    this.mudancas = normalizarMudancas(mudancas);
    this.antes = null;
  }
  aplicar(doc) {
    doc.lote(() => {
      if (!this.antes) {
        this.antes = {};
        for (const [id, depois] of Object.entries(this.mudancas)) {
          const e = doc.get(id);
          if (!e) continue;
          const guarda = {};
          for (const k of Object.keys(depois)) guarda[k] = clonar(e[k]);
          this.antes[id] = guarda;
        }
      }
      for (const [id, depois] of Object.entries(this.mudancas)) doc.alterar(id, depois);
    });
  }
  desfazer(doc) {
    doc.lote(() => {
      for (const [id, antes] of Object.entries(this.antes || {})) doc.alterar(id, antes);
    });
  }
  ids() { return Object.keys(this.mudancas); }
}

export class ComandoTransformar extends Comando {
  /**
   * Move, gira ou escala entidades aplicando uma função a cada ponto.
   * @param ids     entidades afetadas
   * @param funcao  ([x,y,z]) => [x,y,z] para posições
   * @param opcoes  { rotulo, direcional } — `direcional` é a função aplicada a vetores
   *                de direção (eixos da chapa), sem a translação. Quando ausente, os
   *                eixos da chapa ficam como estão (caso de uma translação pura).
   */
  constructor(ids, funcao, opcoes = {}) {
    super(opcoes.rotulo || 'Transformar');
    this.alvos = Array.isArray(ids) ? ids.slice() : [ids];
    this.funcao = funcao;
    this.direcional = opcoes.direcional || null;
    this.antes = null;
  }

  aplicar(doc) {
    doc.lote(() => {
      if (!this.antes) {
        this.antes = {};
        for (const id of this.alvos) {
          const e = doc.get(id);
          if (!e) continue;
          const guarda = {};
          for (const k of (CAMPOS_GEOMETRICOS[e.tipo] || [])) guarda[k] = clonar(e[k]);
          this.antes[id] = guarda;
        }
      }
      for (const id of this.alvos) {
        const e = doc.get(id);
        if (!e) continue;
        const novo = {};
        for (const k of (CAMPOS_GEOMETRICOS[e.tipo] || [])) {
          const eixo = (k === 'eixo_x' || k === 'eixo_y');
          const f = eixo ? (this.direcional || null) : this.funcao;
          if (!f) continue;
          novo[k] = (k === 'vertices')
            ? (e[k] || []).map(p => f(p))
            : f(e[k]);
        }
        doc.alterar(id, novo);
      }
    });
  }

  desfazer(doc) {
    doc.lote(() => {
      for (const [id, antes] of Object.entries(this.antes || {})) doc.alterar(id, antes);
    });
  }
  ids() { return this.alvos.slice(); }
}

export class ComandoComposto extends Comando {
  /** Agrupa vários comandos numa entrada só de desfazer. */
  constructor(comandos, rotulo) {
    const lista = (comandos || []).filter(Boolean);
    super(rotulo || (lista.length ? lista[0].rotulo : 'Operação'));
    this.comandos = lista;
  }
  add(cmd) { if (cmd) this.comandos.push(cmd); return this; }
  get vazio() { return this.comandos.length === 0; }
  aplicar(doc) {
    doc.lote(() => { for (const c of this.comandos) c.aplicar(doc); });
  }
  desfazer(doc) {
    doc.lote(() => {
      for (let i = this.comandos.length - 1; i >= 0; i--) this.comandos[i].desfazer(doc);
    });
  }
  ids() {
    const s = new Set();
    for (const c of this.comandos) for (const i of c.ids()) s.add(i);
    return [...s];
  }
  selecao() {
    const s = new Set();
    for (const c of this.comandos) for (const i of c.selecao()) s.add(i);
    return [...s];
  }
}

// -------------------------------------------------------------------- pilha

export class Pilha {
  /** @param limite quantas operações ficam disponíveis para desfazer. */
  constructor(documento, limite = 200) {
    this.documento = documento;
    this.limite = limite;
    this.feitos = [];
    this.desfeitos = [];
    this._ouvintes = new Set();
  }

  aoMudar(fn) { this._ouvintes.add(fn); return () => this._ouvintes.delete(fn); }

  _avisar(cmd, acao) {
    for (const fn of this._ouvintes) {
      try { fn({ comando: cmd, acao, pilha: this }); }
      catch (e) { console.error('ouvinte da pilha falhou:', e); }
    }
  }

  executar(cmd) {
    if (!cmd) return null;
    cmd.aplicar(this.documento);
    this.feitos.push(cmd);
    if (this.feitos.length > this.limite) this.feitos.shift();
    this.desfeitos.length = 0;
    this._avisar(cmd, 'executar');
    return cmd;
  }

  desfazer() {
    const cmd = this.feitos.pop();
    if (!cmd) return null;
    cmd.desfazer(this.documento);
    this.desfeitos.push(cmd);
    this._avisar(cmd, 'desfazer');
    return cmd;
  }

  refazer() {
    const cmd = this.desfeitos.pop();
    if (!cmd) return null;
    cmd.aplicar(this.documento);
    this.feitos.push(cmd);
    this._avisar(cmd, 'refazer');
    return cmd;
  }

  limpar() { this.feitos.length = 0; this.desfeitos.length = 0; this._avisar(null, 'limpar'); }

  get podeDesfazer() { return this.feitos.length > 0; }
  get podeRefazer() { return this.desfeitos.length > 0; }
  get rotuloDesfazer() {
    const c = this.feitos[this.feitos.length - 1];
    return c ? c.rotulo : '';
  }
  get rotuloRefazer() {
    const c = this.desfeitos[this.desfeitos.length - 1];
    return c ? c.rotulo : '';
  }
  /** Histórico do mais recente para o mais antigo, para o menu de desfazer. */
  historico(n = 12) {
    return this.feitos.slice(-n).reverse().map((c, i) => ({ rotulo: c.rotulo, passos: i + 1 }));
  }
  /** Desfaz n passos de uma vez (escolha direta no menu de desfazer). */
  desfazerAte(passos) {
    for (let i = 0; i < passos; i++) if (!this.desfazer()) break;
  }
}

// ------------------------------------------------------------------ apoio

function normalizarMudancas(m) {
  if (Array.isArray(m)) {
    const d = {};
    for (const it of m) d[it.id] = clonar(it.depois || it.campos || {});
    return d;
  }
  const d = {};
  for (const [id, campos] of Object.entries(m || {})) d[id] = clonar(campos);
  return d;
}

export function rotuloDe(ent) {
  if (!ent) return 'objeto';
  const nomes = { barra: 'barra', chapa: 'chapa', solido: 'sólido', grupo: 'grupo' };
  const base = nomes[ent.tipo] || 'objeto';
  return ent.nome ? `${base} ${ent.nome}` : base;
}
