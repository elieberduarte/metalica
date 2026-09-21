// Documento 3D no navegador — espelho de `nucleo3d/modelo.py`.
//
// Mesmos nomes de campo, mesmas unidades: milímetro e grau, Z para cima. O documento é
// a única fonte de verdade; a cena Three.js é derivada dele. Quem altera o documento
// avisa os interessados pelo `aoMudar`, sempre com a lista de ids afetados, para que a
// cena reconstrua só o que mudou em vez de refazer o modelo inteiro.

// --------------------------------------------------------------- utilidades

export function novoId(prefixo = 'e') {
  // Mesmo formato do Python: prefixo + 12 hexadecimais.
  let s = '';
  for (let i = 0; i < 12; i++) s += Math.floor(Math.random() * 16).toString(16);
  return prefixo + s;
}

export const somar = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const subtrair = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const escalar = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
export const escalarProduto = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const norma = (a) => Math.hypot(a[0], a[1], a[2]);
export const distancia = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
export const meio = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];

export function normalizar(a) {
  const n = norma(a);
  return n > 1e-12 ? [a[0] / n, a[1] / n, a[2] / n] : [0, 0, 1];
}

export function produtoVetorial(a, b) {
  return [a[1] * b[2] - a[2] * b[1],
          a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]];
}

/** Base ortonormal de uma barra: t ao longo do eixo, u e v na seção.
 *  `rotacao` gira a seção em torno do próprio eixo, em graus, como no modelo Python. */
export function baseDaBarra(inicio, fim, rotacao = 0) {
  const t = normalizar(subtrair(fim, inicio));
  // Referência estável: o vertical, salvo quando a barra é quase vertical. O limiar
  // é o mesmo de `geometria.base_local` no Python — a malha do servidor e a daqui
  // precisam cair no mesmo triedro, senão o cache giraria a seção.
  const ref = Math.abs(t[2]) >= 0.9 ? [1, 0, 0] : [0, 0, 1];
  let u = normalizar(produtoVetorial(ref, t));       // largura (bf)
  let v = normalizar(produtoVetorial(t, u));         // altura (d)
  const r = (rotacao || 0) * Math.PI / 180;
  if (r) {
    const c = Math.cos(r), s = Math.sin(r);
    const u2 = somar(escalar(u, c), escalar(v, s));
    const v2 = somar(escalar(v, c), escalar(u, -s));
    u = u2; v = v2;
  }
  return { t, u, v };
}

// --------------------------------------------------------------- entidades

/** Campos comuns a toda entidade, com os mesmos padrões do Python. */
export const CAMPOS_COMUNS = {
  tipo: 'entidade', nome: '', camada: 'Estrutura', material: '',
  visivel: true, bloqueada: false, grupo: '', atributos: null,
};

/** Padrões por tipo, idênticos aos dataclasses de `nucleo3d/modelo.py`. */
export const PADRAO = {
  barra: {
    tipo: 'barra', inicio: [0, 0, 0], fim: [0, 0, 1000], perfil: 'W 310×38,7',
    rotacao: 0, papel: 'viga', aco: 'ASTM A572 Gr.50',
    recorte_inicio: 0, recorte_fim: 0,
  },
  chapa: {
    tipo: 'chapa', origem: [0, 0, 0], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
    contorno: null, espessura: 12.7, centrada: true, furos: null, aco: 'ASTM A36',
  },
  solido: {
    tipo: 'solido', vertices: null, faces: null, arestas_vivas: null, origem_ifc: '',
  },
  grupo: {
    tipo: 'grupo', filhos: null, origem: [0, 0, 0], definicao: '',
  },
};

/** Campos que descrevem a posição de cada tipo — os que uma transformação mexe. */
export const CAMPOS_GEOMETRICOS = {
  barra: ['inicio', 'fim'],
  chapa: ['origem', 'eixo_x', 'eixo_y'],
  solido: ['vertices'],
  grupo: ['origem'],
};

const PAPEIS = ['pilar', 'viga', 'terça', 'contraventamento', 'longarina', 'barra'];
export { PAPEIS };

/** Cria uma entidade completa a partir de um registro parcial. */
export function criar(reg) {
  const tipo = reg && reg.tipo ? reg.tipo : 'solido';
  const base = PADRAO[tipo] || {};
  const ent = { id: reg.id || novoId(), ...CAMPOS_COMUNS, ...base, tipo };
  // Os padrões mutáveis (listas e dicionários) precisam ser recriados por entidade.
  ent.atributos = {};
  if (tipo === 'chapa') { ent.contorno = []; ent.furos = []; }
  if (tipo === 'solido') { ent.vertices = []; ent.faces = []; ent.arestas_vivas = []; }
  if (tipo === 'grupo') { ent.filhos = []; }
  for (const [k, v] of Object.entries(reg)) if (v !== undefined) ent[k] = v;
  return ent;
}

/** Cópia profunda barata: entidades são só números, textos e listas. */
export const clonar = (o) => (o === undefined || o === null
  ? o : JSON.parse(JSON.stringify(o)));

// ------------------------------------------------- consultas de geometria

/** Pontos característicos de uma entidade, em coordenadas do mundo. */
export function pontosDe(ent) {
  if (!ent) return [];
  if (ent.tipo === 'barra') return [ent.inicio, ent.fim];
  if (ent.tipo === 'chapa') return contornoNoMundo(ent);
  if (ent.tipo === 'solido') return ent.vertices || [];
  if (ent.tipo === 'grupo') return [ent.origem];
  return [];
}

/** Contorno da chapa levado para o mundo. */
export function contornoNoMundo(ch) {
  const pts = [];
  for (const [x, y] of (ch.contorno || [])) {
    pts.push(somar(ch.origem, somar(escalar(ch.eixo_x, x), escalar(ch.eixo_y, y))));
  }
  return pts;
}

export const normalDaChapa = (ch) =>
  normalizar(produtoVetorial(ch.eixo_x, ch.eixo_y));

export const comprimentoDaBarra = (b) => distancia(b.inicio, b.fim);
export const meioDaBarra = (b) => meio(b.inicio, b.fim);
export const direcaoDaBarra = (b) => normalizar(subtrair(b.fim, b.inicio));

/** Arestas de uma entidade como pares de pontos do mundo — usadas por snap e desenho. */
export function arestasDe(ent) {
  if (!ent) return [];
  if (ent.tipo === 'barra') return [[ent.inicio, ent.fim]];
  if (ent.tipo === 'chapa') {
    const p = contornoNoMundo(ent);
    return p.map((a, i) => [a, p[(i + 1) % p.length]]);
  }
  if (ent.tipo === 'solido') {
    const out = [];
    const vs = ent.vertices || [];
    const vistas = new Set();
    const somar = (a, b) => {
      const chave = a < b ? a + ':' + b : b + ':' + a;
      if (vistas.has(chave) || !vs[a] || !vs[b]) return;
      vistas.add(chave);
      out.push([vs[a], vs[b]]);
    };
    for (const f of (ent.faces || [])) {
      for (let i = 0; i < f.length; i++) somar(f[i], f[(i + 1) % f.length]);
    }
    // Linhas soltas também são arestas: é nelas que o snap da ferramenta Linha encaixa.
    for (const [a, b] of arestasSoltasDe(ent)) somar(a, b);
    return out;
  }
  return [];
}

const chaveAresta = (a, b) => (a < b ? a + ':' + b : b + ':' + a);

/**
 * Arestas de um sólido que não são borda de nenhuma face, como pares de índices:
 * linha aberta, arco, cota, linha de construção. Um sólido sem faces e sem arestas
 * declaradas é lido como uma polilinha pelos vértices, na ordem.
 */
export function arestasSoltasDe(ent) {
  if (!ent || ent.tipo !== 'solido') return [];
  const vs = ent.vertices || [], fs = ent.faces || [];
  const vivas = ent.arestas_vivas || [];
  const deFace = new Set();
  for (const f of fs) {
    for (let i = 0; i < f.length; i++) deFace.add(chaveAresta(f[i], f[(i + 1) % f.length]));
  }
  const out = [];
  for (const par of vivas) {
    const [a, b] = par || [];
    if (a === b || !vs[a] || !vs[b] || deFace.has(chaveAresta(a, b))) continue;
    out.push([a, b]);
  }
  if (!fs.length && !vivas.length) {
    for (let i = 0; i < vs.length - 1; i++) out.push([i, i + 1]);
  }
  return out;
}

/** Área do contorno da chapa, em mm² (mesmo cálculo do Python, descontando furos). */
export function areaDaChapa(ch) {
  const p = ch.contorno || [];
  if (p.length < 3) return 0;
  let s = 0;
  for (let i = 0; i < p.length; i++) {
    const q = p[(i + 1) % p.length];
    s += p[i][0] * q[1] - q[0] * p[i][1];
  }
  let a = Math.abs(s) / 2;
  for (const f of (ch.furos || [])) a -= Math.PI * Math.pow((f.diametro || 0) / 2, 2);
  return a;
}

// --------------------------------------------------------------- documento

export const CAMADAS_PADRAO = [
  ['Estrutura', '#4b5563'], ['Terças', '#0b3d91'], ['Contraventamento', '#2e8b57'],
  ['Chapas', '#b8860b'], ['Fechamento', '#9aa4b2'], ['Referência', '#c0392b'],
  ['Importado', '#6a3fb5'],
];

export const MATERIAIS_PADRAO = [
  { nome: 'Aço', cor: '#8a94a6', opacidade: 1, metalico: 0.85, rugosidade: 0.45, aco: 'ASTM A572 Gr.50' },
  { nome: 'Aço galvanizado', cor: '#b6bec9', opacidade: 1, metalico: 0.85, rugosidade: 0.45, aco: 'ZAR-345' },
  { nome: 'Concreto', cor: '#b9b2a6', opacidade: 1, metalico: 0, rugosidade: 0.9, aco: '' },
  { nome: 'Telha', cor: '#cfd6e0', opacidade: 1, metalico: 0.6, rugosidade: 0.45, aco: '' },
  { nome: 'Vidro', cor: '#9fc6e8', opacidade: 0.35, metalico: 0.1, rugosidade: 0.05, aco: '' },
];

export class Documento {
  constructor(nome = 'Modelo') {
    this.nome = nome;
    this.unidade = 'mm';
    this.entidades = new Map();
    this.camadas = new Map();
    this.materiais = new Map();
    this.projeto = {};
    this.metadados = {};
    this._ouvintes = new Set();
    this._lote = null;          // acumula ids enquanto uma operação composta roda
    for (const [n, cor] of CAMADAS_PADRAO) {
      this.camadas.set(n, { nome: n, cor, visivel: true, bloqueada: false });
    }
    for (const m of MATERIAIS_PADRAO) this.materiais.set(m.nome, { ...m });
  }

  // ---- notificação ----

  /** Registra um ouvinte. Devolve a função que o remove. */
  aoMudar(fn) {
    this._ouvintes.add(fn);
    return () => this._ouvintes.delete(fn);
  }

  /** Avisa quem depende do documento. `acao` é 'add', 'remover', 'alterar' ou 'tudo'. */
  notificar(ids, acao = 'alterar') {
    const lista = Array.isArray(ids) ? ids : (ids ? [ids] : []);
    if (this._lote) {
      for (const i of lista) this._lote.ids.add(i);
      if (acao === 'tudo') this._lote.acao = 'tudo';
      return;
    }
    for (const fn of this._ouvintes) {
      try { fn({ ids: lista, acao, documento: this }); }
      catch (e) { console.error('ouvinte do documento falhou:', e); }
    }
  }

  /** Agrupa várias alterações numa notificação só. */
  lote(fn) {
    const externo = !this._lote;
    if (externo) this._lote = { ids: new Set(), acao: 'alterar' };
    try { return fn(); }
    finally {
      if (externo) {
        const l = this._lote;
        this._lote = null;
        this.notificar([...l.ids], l.acao);
      }
    }
  }

  /** Alias usado por comandos que alteram a entidade no lugar. */
  marcarMudanca(id) { this.notificar(id ? [id] : [], 'alterar'); }

  /** Camadas ou materiais mudaram: a cena só precisa repintar, não refazer malhas. */
  notificarAparencia() { this.notificar([], 'aparencia'); }

  // ---- manipulação ----

  add(reg) {
    const ent = reg && reg.id && this.entidades.has(reg.id) ? reg : criar(reg);
    if (ent.camada && !this.camadas.has(ent.camada)) {
      this.camadas.set(ent.camada, { nome: ent.camada, cor: '#8a94a6', visivel: true, bloqueada: false });
    }
    this.entidades.set(ent.id, ent);
    this.notificar([ent.id], 'add');
    return ent;
  }

  get(id) { return this.entidades.get(id) || null; }

  remover(id) {
    const ent = this.entidades.get(id);
    if (!ent) return null;
    this.entidades.delete(id);
    if (ent.tipo === 'grupo') for (const f of (ent.filhos || [])) this.remover(f);
    this.notificar([id], 'remover');
    return ent;
  }

  /** Altera campos de uma entidade. Não faz undo por si — use `ComandoAlterar`. */
  alterar(id, campos) {
    const ent = this.entidades.get(id);
    if (!ent) return null;
    Object.assign(ent, clonar(campos));
    if (ent.camada && !this.camadas.has(ent.camada)) {
      this.camadas.set(ent.camada, { nome: ent.camada, cor: '#8a94a6', visivel: true, bloqueada: false });
    }
    this.notificar([id], 'alterar');
    return ent;
  }

  porTipo(tipo) { return [...this.entidades.values()].filter(e => e.tipo === tipo); }
  porCamada(camada) { return [...this.entidades.values()].filter(e => e.camada === camada); }
  porPerfil(perfil) { return [...this.entidades.values()].filter(e => e.perfil === perfil); }

  get barras() { return this.porTipo('barra'); }
  get chapas() { return this.porTipo('chapa'); }
  get solidos() { return this.porTipo('solido'); }
  get lista() { return [...this.entidades.values()]; }
  get tamanho() { return this.entidades.size; }

  camadaDe(ent) {
    return this.camadas.get(ent && ent.camada) ||
           { nome: ent && ent.camada || '', cor: '#8a94a6', visivel: true, bloqueada: false };
  }

  /** A entidade aparece na cena? Considera a camada além dela mesma. */
  aparece(ent) {
    if (!ent || ent.visivel === false) return false;
    const c = this.camadas.get(ent.camada);
    return !c || c.visivel !== false;
  }

  /** A entidade pode ser editada? Camada bloqueada bloqueia o que está nela. */
  editavel(ent) {
    if (!ent || ent.bloqueada) return false;
    const c = this.camadas.get(ent.camada);
    return !c || !c.bloqueada;
  }

  // ---- caixas envolventes ----

  /** Caixa de uma entidade: [[xmin,ymin,zmin],[xmax,ymax,zmax]] ou null. */
  caixaDe(ent) { return caixaDePontos(pontosDe(ent)); }

  /** Caixa do modelo inteiro, ou só dos ids pedidos. */
  caixa(ids = null) {
    const pts = [];
    const alvo = ids ? ids.map(i => this.entidades.get(i)) : this.entidades.values();
    for (const e of alvo) if (e) pts.push(...pontosDe(e));
    return caixaDePontos(pts) || [[0, 0, 0], [0, 0, 0]];
  }

  estatisticas() {
    return {
      entidades: this.entidades.size, barras: this.barras.length,
      chapas: this.chapas.length, solidos: this.solidos.length,
      camadas: this.camadas.size,
    };
  }

  /** Quantas entidades por camada — o painel da árvore do modelo usa isto. */
  contagemPorCamada() {
    const c = new Map();
    for (const n of this.camadas.keys()) c.set(n, 0);
    for (const e of this.entidades.values()) c.set(e.camada, (c.get(e.camada) || 0) + 1);
    return c;
  }

  // ---- serialização (mesmo formato de Documento.dict() no Python) ----

  paraJSON() {
    const camadas = {}, materiais = {};
    for (const [k, v] of this.camadas) camadas[k] = { ...v };
    for (const [k, v] of this.materiais) materiais[k] = { ...v };
    return {
      nome: this.nome, unidade: this.unidade,
      entidades: [...this.entidades.values()].map(e => clonar(e)),
      camadas, materiais, projeto: this.projeto, metadados: this.metadados,
    };
  }

  static deJSON(d) {
    const doc = new Documento((d && d.nome) || 'Modelo');
    if (!d) return doc;
    doc.unidade = d.unidade || 'mm';
    doc.projeto = d.projeto || {};
    doc.metadados = d.metadados || {};
    if (d.camadas && Object.keys(d.camadas).length) {
      doc.camadas = new Map();
      for (const [k, v] of Object.entries(d.camadas)) {
        doc.camadas.set(k, { nome: v.nome || k, cor: v.cor || '#8a94a6',
                             visivel: v.visivel !== false, bloqueada: !!v.bloqueada });
      }
    }
    if (d.materiais && Object.keys(d.materiais).length) {
      doc.materiais = new Map();
      for (const [k, v] of Object.entries(d.materiais)) {
        doc.materiais.set(k, { nome: v.nome || k, cor: v.cor || '#9aa4b2',
                               opacidade: v.opacidade ?? 1, metalico: v.metalico ?? 0.85,
                               rugosidade: v.rugosidade ?? 0.45, aco: v.aco || '' });
      }
    }
    for (const reg of (d.entidades || [])) {
      const ent = criar(reg);
      if (ent.camada && !doc.camadas.has(ent.camada)) {
        doc.camadas.set(ent.camada, { nome: ent.camada, cor: '#8a94a6', visivel: true, bloqueada: false });
      }
      doc.entidades.set(ent.id, ent);
    }
    return doc;
  }

  /** Substitui o conteúdo por outro documento, preservando os ouvintes. */
  substituirPor(outro) {
    this.nome = outro.nome;
    this.unidade = outro.unidade;
    this.entidades = outro.entidades;
    this.camadas = outro.camadas;
    this.materiais = outro.materiais;
    this.projeto = outro.projeto;
    this.metadados = outro.metadados;
    this.notificar([], 'tudo');
    return this;
  }
}

export function caixaDePontos(pts) {
  if (!pts || !pts.length) return null;
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const p of pts) {
    if (!p) continue;
    for (let i = 0; i < 3; i++) {
      if (p[i] < min[i]) min[i] = p[i];
      if (p[i] > max[i]) max[i] = p[i];
    }
  }
  return isFinite(min[0]) ? [min, max] : null;
}
