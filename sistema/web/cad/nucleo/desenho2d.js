// Documento 2D no navegador: espelho de nucleo2d/desenho.py.
//
// Mesmos nomes de campo, mesma serialização, mesma regra: milímetro no modelo, e o que
// é "de papel" (altura de texto, deslocamento de cota, espaçamento de hachura) em mm de
// papel, multiplicado pela escala do desenho na hora de desenhar e de exportar.
//
// O documento é a única fonte de verdade da tela. Ferramentas nunca mexem nele
// diretamente: passam por um comando (comandos.js), que é o que dá desfazer.

export const TIPOS = ['linha', 'polilinha', 'circulo', 'arco', 'texto', 'cota', 'hachura', 'chamada'];

export const CAMADAS_PADRAO = [
  ['CORTE', '#16202e', 'CONTINUOUS', 0.5], ['VISTA', '#2b3646', 'CONTINUOUS', 0.35],
  ['VISTA-FINA', '#6b7280', 'CONTINUOUS', 0.18], ['OCULTA', '#8a94a6', 'HIDDEN', 0.18],
  ['HACHURA', '#8a94a6', 'CONTINUOUS', 0.13], ['EIXO', '#c0392b', 'CENTER', 0.18],
  ['COTA', '#1c7a43', 'CONTINUOUS', 0.18], ['TEXTO', '#16202e', 'CONTINUOUS', 0.25],
  ['FURO', '#1f5fbf', 'CONTINUOUS', 0.25], ['SOLDA', '#9a6b06', 'CONTINUOUS', 0.35],
  ['PARAFUSO', '#1f5fbf', 'CONTINUOUS', 0.25], ['AUXILIAR', '#7d8a9e', 'DASHED', 0.13],
];

let contador = 0;
export function novoId() {
  contador += 1;
  return Date.now().toString(36).slice(-5) + Math.random().toString(36).slice(2, 6) + contador.toString(36);
}

export const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));

/** Cria uma entidade com os padrões do tipo. */
export function criar(reg) {
  const base = { id: reg.id || novoId(), tipo: reg.tipo, camada: reg.camada, atributos: reg.atributos || {} };
  switch (reg.tipo) {
    case 'linha': return { ...base, camada: base.camada || 'VISTA', a: reg.a, b: reg.b };
    case 'polilinha': return { ...base, camada: base.camada || 'VISTA', vertices: reg.vertices || [], fechada: !!reg.fechada };
    case 'circulo': return { ...base, camada: base.camada || 'VISTA', centro: reg.centro, raio: reg.raio };
    case 'arco': return { ...base, camada: base.camada || 'VISTA', centro: reg.centro, raio: reg.raio, inicio: reg.inicio, fim: reg.fim };
    case 'texto': return { ...base, camada: base.camada || 'TEXTO', posicao: reg.posicao, texto: reg.texto || '',
      altura: reg.altura ?? 2.5, angulo: reg.angulo || 0, alinhamento: reg.alinhamento || 'esquerda', vertical: reg.vertical || 'base' };
    case 'cota': return { ...base, camada: base.camada || 'COTA', modo: reg.modo || 'alinhada', p1: reg.p1, p2: reg.p2,
      deslocamento: reg.deslocamento ?? 10, texto: reg.texto ?? null, altura: reg.altura ?? 2.5, texto_pos: reg.texto_pos ?? null };
    case 'hachura': return { ...base, camada: base.camada || 'HACHURA', contornos: reg.contornos || [], padrao: reg.padrao || 'aco',
      angulo: reg.angulo ?? 45, espacamento: reg.espacamento ?? 2.5 };
    case 'chamada': return { ...base, camada: base.camada || 'TEXTO', alvo: reg.alvo, posicao: reg.posicao, texto: reg.texto || '', altura: reg.altura ?? 2.5 };
    default: throw new Error('tipo de entidade desconhecido: ' + reg.tipo);
  }
}

// ------------------------------------------------------------- geometria

export const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
export const meio = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
const grausRad = (g) => (g * Math.PI) / 180;

/** Pontos do arco amostrados (para caixa, snap e desenho quando não há canvas arc). */
export function pontosArco(e, n = null) {
  let a0 = e.inicio, a1 = e.fim;
  if (a1 < a0) a1 += 360;
  const passos = n || Math.max(2, Math.ceil((a1 - a0) / 10));
  const pts = [];
  for (let i = 0; i <= passos; i++) {
    const a = grausRad(a0 + ((a1 - a0) * i) / passos);
    pts.push([e.centro[0] + e.raio * Math.cos(a), e.centro[1] + e.raio * Math.sin(a)]);
  }
  return pts;
}

/** Valor de uma cota, em mm. */
export function valorCota(c) {
  if (c.modo === 'h') return Math.abs(c.p2[0] - c.p1[0]);
  if (c.modo === 'v') return Math.abs(c.p2[1] - c.p1[1]);
  return dist(c.p1, c.p2);
}

/** Pontos característicos de uma entidade: os que a definem (para caixa e snap). */
/**
 * Pontos por onde a cota é desenhada (as pontas da linha de cota), além dos dois pontos
 * medidos. É o que a seleção por janela e o índice espacial precisam ver: a linha de
 * cota fica deslocada dos pontos medidos, às vezes muito.
 */
export function pontosCota(c, escala = 1) {
  let [x1, y1] = c.p1, [x2, y2] = c.p2;
  if (c.modo === 'h') y2 = y1; else if (c.modo === 'v') x2 = x1;
  const dx = x2 - x1, dy = y2 - y1, comp = Math.hypot(dx, dy);
  if (comp < 1e-9) return [c.p1, c.p2];
  const nx = -dy / comp, ny = dx / comp, desl = (c.deslocamento || 0) * escala;
  return [c.p1, c.p2, [x1 + nx * desl, y1 + ny * desl], [x2 + nx * desl, y2 + ny * desl]];
}

export function pontosDe(e) {
  switch (e.tipo) {
    case 'linha': return [e.a, e.b];
    case 'polilinha': return e.vertices;
    case 'circulo': return [[e.centro[0] - e.raio, e.centro[1] - e.raio], [e.centro[0] + e.raio, e.centro[1] + e.raio]];
    case 'arco': return pontosArco(e);
    case 'texto': return [e.posicao];
    case 'cota': return [e.p1, e.p2];
    case 'hachura': return e.contornos.flat();
    case 'chamada': return [e.alvo, e.posicao];
    default: return [];
  }
}

/** Segmentos retos de uma entidade (para snap de interseção e distância). */
export function segmentosDe(e) {
  switch (e.tipo) {
    case 'linha': return [[e.a, e.b]];
    case 'polilinha': {
      const s = [];
      for (let i = 0; i < e.vertices.length - 1; i++) s.push([e.vertices[i], e.vertices[i + 1]]);
      if (e.fechada && e.vertices.length > 2) s.push([e.vertices[e.vertices.length - 1], e.vertices[0]]);
      return s;
    }
    case 'arco': { const p = pontosArco(e); const s = []; for (let i = 0; i < p.length - 1; i++) s.push([p[i], p[i + 1]]); return s; }
    case 'cota': return [[e.p1, e.p2]];
    case 'chamada': return [[e.alvo, e.posicao]];
    case 'hachura': return e.contornos.flatMap(c => c.map((p, i) => [p, c[(i + 1) % c.length]]));
    default: return [];
  }
}

export function caixaDe(pontos) {
  if (!pontos.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pontos) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  return [[x0, y0], [x1, y1]];
}

/** Distância de um ponto a um segmento. */
export function distSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  if (l2 < 1e-12) return dist(p, a);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

/** Ponto mais próximo sobre um segmento. */
export function maisProximoSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  if (l2 < 1e-12) return a;
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  return [a[0] + t * dx, a[1] + t * dy];
}

/** Interseção de dois segmentos, ou null. */
export function intersecaoSeg(a, b, c, d) {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  const u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;
  return [a[0] + t * r[0], a[1] + t * r[1]];
}

/** Distância do ponto à entidade (para seleção por clique). `escala` é mm/px, para o
 *  texto ter uma caixa mínima clicável. */
export function distanciaEntidade(p, e, escalaTexto = 1) {
  switch (e.tipo) {
    case 'circulo': return Math.abs(dist(p, e.centro) - e.raio);
    case 'texto': {
      const h = (e.altura || 2.5) * escalaTexto, w = Math.max(h, (e.texto || '').length * h * 0.65);
      const x = e.alinhamento === 'centro' ? e.posicao[0] - w / 2 : e.alinhamento === 'direita' ? e.posicao[0] - w : e.posicao[0];
      const dx = Math.max(x - p[0], 0, p[0] - (x + w)), dy = Math.max(e.posicao[1] - p[1], 0, p[1] - (e.posicao[1] + h));
      return Math.hypot(dx, dy);
    }
    case 'hachura': {
      // dentro do contorno externo conta como acerto na borda
      const c = e.contornos[0] || [];
      if (c.length >= 3 && dentroDe(p, c)) return 0;
      return Math.min(...segmentosDe(e).map(([a, b]) => distSeg(p, a, b)), Infinity);
    }
    case 'cota': {
      // a linha de cota está deslocada: aproxima pela distância aos pontos e ao segmento
      return Math.min(distSeg(p, e.p1, e.p2), dist(p, e.p1), dist(p, e.p2));
    }
    default: {
      const segs = segmentosDe(e);
      if (!segs.length) return Infinity;
      return Math.min(...segs.map(([a, b]) => distSeg(p, a, b)));
    }
  }
}

export function dentroDe(p, poligono) {
  let dentro = false;
  for (let i = 0, j = poligono.length - 1; i < poligono.length; j = i++) {
    const [xi, yi] = poligono[i], [xj, yj] = poligono[j];
    if (((yi > p[1]) !== (yj > p[1])) && (p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi)) dentro = !dentro;
  }
  return dentro;
}

/** Translada uma entidade. */
export function transladar(e, d) {
  const mv = (p) => [p[0] + d[0], p[1] + d[1]];
  const n = clonar(e);
  switch (e.tipo) {
    case 'linha': n.a = mv(e.a); n.b = mv(e.b); break;
    case 'polilinha': n.vertices = e.vertices.map(mv); break;
    case 'circulo': case 'arco': n.centro = mv(e.centro); break;
    case 'texto': n.posicao = mv(e.posicao); break;
    case 'cota': n.p1 = mv(e.p1); n.p2 = mv(e.p2); if (e.texto_pos) n.texto_pos = mv(e.texto_pos); break;
    case 'hachura': n.contornos = e.contornos.map(c => c.map(mv)); break;
    case 'chamada': n.alvo = mv(e.alvo); n.posicao = mv(e.posicao); break;
  }
  return n;
}

/** Transformação afim genérica (girar, espelhar, escalar) de uma entidade. `f` mapeia
 *  pontos; `f_ang` corrige ângulos (graus); `k` escala comprimentos. */
export function transformar(e, f, fAng = (a) => a, k = 1, espelha = false) {
  const n = clonar(e);
  switch (e.tipo) {
    case 'linha': n.a = f(e.a); n.b = f(e.b); break;
    case 'polilinha': n.vertices = e.vertices.map(f); break;
    case 'circulo': n.centro = f(e.centro); n.raio = e.raio * k; break;
    case 'arco': {
      n.centro = f(e.centro); n.raio = e.raio * k;
      let a0 = fAng(e.inicio), a1 = fAng(e.fim);
      if (espelha) [a0, a1] = [a1, a0];
      n.inicio = ((a0 % 360) + 360) % 360; n.fim = ((a1 % 360) + 360) % 360;
      break;
    }
    case 'texto': n.posicao = f(e.posicao); n.angulo = espelha ? e.angulo : fAng(e.angulo); break;
    case 'cota': n.p1 = f(e.p1); n.p2 = f(e.p2); if (e.texto_pos) n.texto_pos = f(e.texto_pos); if (espelha) n.deslocamento = -e.deslocamento; break;
    case 'hachura': n.contornos = e.contornos.map(c => c.map(f)); break;
    case 'chamada': n.alvo = f(e.alvo); n.posicao = f(e.posicao); break;
  }
  return n;
}

// ------------------------------------------------------------- documento

export class Desenho2D {
  constructor(nome = 'Desenho') {
    this.nome = nome;
    this.unidade = 'mm';
    this.escala = 20;
    this.camadas = new Map();
    this.entidades = new Map();
    this.vistas = [];
    this.metadados = {};
    this._ouvintes = new Set();
    this._lote = null;
    for (const [n, cor, tipo, esp] of CAMADAS_PADRAO) {
      this.camadas.set(n, { nome: n, cor, visivel: true, bloqueada: false, tipo_linha: tipo, espessura: esp });
    }
  }

  get tamanho() { return this.entidades.size; }
  get(id) { return this.entidades.get(id); }

  add(reg) {
    const e = reg && reg.id && this.entidades.has(reg.id) ? reg : criar(reg);
    if (e.camada && !this.camadas.has(e.camada)) {
      this.camadas.set(e.camada, { nome: e.camada, cor: '#4b5563', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.25 });
    }
    this.entidades.set(e.id, e);
    this.notificar([e.id], 'add');
    return e;
  }

  remover(id) {
    if (this.entidades.delete(id)) this.notificar([id], 'remover');
  }

  alterar(id, campos) {
    const e = this.entidades.get(id);
    if (!e) return null;
    Object.assign(e, clonar(campos));
    this.notificar([id], 'alterar');
    return e;
  }

  alterarCamada(nome, campos) {
    const c = this.camadas.get(nome);
    if (!c) return;
    Object.assign(c, campos);
    this.notificar([], 'aparencia');
  }

  visivel(e) {
    const c = this.camadas.get(e.camada);
    return !c || c.visivel !== false;
  }

  bloqueada(e) {
    const c = this.camadas.get(e.camada);
    return !!(c && c.bloqueada);
  }

  caixa(ids = null) {
    const pts = [];
    for (const e of this.entidades.values()) {
      if (ids && !ids.has(e.id)) continue;
      if (!ids && !this.visivel(e)) continue;
      pts.push(...pontosDe(e));
    }
    return caixaDe(pts);
  }

  // ---- índice espacial ----
  // Grade uniforme de caixas: snap, seleção e redesenho perguntam "o que há nesta
  // região" em vez de varrer todas as entidades — um desenho do modelo inteiro passa de
  // cem mil objetos, e a varredura a cada movimento do mouse travava a tela.
  _indice() {
    if (this._grade) return this._grade;
    const caixas = new Map();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, n = 0;
    for (const e of this.entidades.values()) {
      const c = caixaDe(e.tipo === 'cota' ? pontosCota(e, this.escala) : pontosDe(e));
      if (!c) continue;
      caixas.set(e.id, c); n++;
      if (c[0][0] < x0) x0 = c[0][0]; if (c[0][1] < y0) y0 = c[0][1];
      if (c[1][0] > x1) x1 = c[1][0]; if (c[1][1] > y1) y1 = c[1][1];
    }
    // célula tal que a grade tenha ~ raiz(n)/2 células por lado: poucas entidades por
    // célula, e uma diagonal comprida (contraventamento) não cai em centenas delas
    const lado = Math.max(x1 - x0, y1 - y0, 1);
    const celula = Math.max(lado / Math.max(8, Math.min(160, Math.ceil(Math.sqrt(n) / 2))), 1);
    this._grade = { celula, caixas, celulas: new Map() };
    for (const [id, c] of caixas) this._indexar(id, c);
    return this._grade;
  }

  _chavesDe(c) {
    const g = this._grade, s = g.celula;
    return [Math.floor(c[0][0] / s), Math.floor(c[0][1] / s), Math.floor(c[1][0] / s), Math.floor(c[1][1] / s)];
  }

  // chave numérica da célula (i, j): mais rápida que texto como chave de Map
  static _chave(i, j) { return i * 4194304 + j; }

  _indexar(id, c) {
    const g = this._grade, [i0, j0, i1, j1] = this._chavesDe(c);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = Desenho2D._chave(i, j);
      let cel = g.celulas.get(k);
      if (!cel) { cel = { i, j, ids: new Set() }; g.celulas.set(k, cel); }
      cel.ids.add(id);
    }
  }

  _desindexar(id) {
    const g = this._grade, c = g.caixas.get(id);
    if (!c) return;
    const [i0, j0, i1, j1] = this._chavesDe(c);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = Desenho2D._chave(i, j), cel = g.celulas.get(k);
      if (cel) { cel.ids.delete(id); if (!cel.ids.size) g.celulas.delete(k); }
    }
    g.caixas.delete(id);
  }

  _atualizarIndice(ids, acao) {
    if (!this._grade) return;
    if (acao === 'tudo' || ids.length > this.entidades.size / 4) { this._grade = null; return; }
    for (const id of ids) {
      this._desindexar(id);
      const e = this.entidades.get(id);
      const c = e ? caixaDe(e.tipo === 'cota' ? pontosCota(e, this.escala) : pontosDe(e)) : null;
      if (c) { this._grade.caixas.set(id, c); this._indexar(id, c); }
    }
  }

  /** Caixa [[x0,y0],[x1,y1]] de uma entidade, do índice. */
  caixaDa(e) {
    return this._indice().caixas.get(e.id) || null;
  }

  /** Entidades cuja caixa toca a região [[x0,y0],[x1,y1]] (em mm do modelo). */
  naRegiao(regiao) {
    const g = this._indice(), [i0, j0, i1, j1] = this._chavesDe(regiao);
    const total = (i1 - i0 + 1) * (j1 - j0 + 1);
    const fora = [];
    const toca = (c) => c[1][0] >= regiao[0][0] && c[0][0] <= regiao[1][0] && c[1][1] >= regiao[0][1] && c[0][1] <= regiao[1][1];
    if (total > g.celulas.size) {
      // região maior que a grade ocupada: mais barato olhar as células que existem
      const vistos = new Set();
      for (const c of g.celulas.values()) {
        if (c.i < i0 || c.i > i1 || c.j < j0 || c.j > j1) continue;
        for (const id of c.ids) if (!vistos.has(id)) { vistos.add(id); if (toca(g.caixas.get(id))) fora.push(this.entidades.get(id)); }
      }
      return fora;
    }
    const vistos = new Set();
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const c = g.celulas.get(Desenho2D._chave(i, j));
      if (!c) continue;
      for (const id of c.ids) if (!vistos.has(id)) { vistos.add(id); if (toca(g.caixas.get(id))) fora.push(this.entidades.get(id)); }
    }
    return fora;
  }

  // ---- notificação ----
  aoMudar(fn) { this._ouvintes.add(fn); return () => this._ouvintes.delete(fn); }

  notificar(ids, acao) {
    this.versao = (this.versao || 0) + 1;         // a tela compara para saber se redesenha
    if (acao !== 'aparencia') this._atualizarIndice(ids, acao);
    if (this._lote) { for (const i of ids) this._lote.ids.add(i); if (acao === 'tudo') this._lote.acao = 'tudo'; return; }
    this._emitir(ids, acao);
  }

  _emitir(ids, acao) {
    for (const fn of this._ouvintes) { try { fn({ ids, acao, documento: this }); } catch (e) { console.error(e); } }
  }

  lote(fn) {
    const externo = !this._lote;
    if (externo) this._lote = { ids: new Set(), acao: 'alterar' };
    try { return fn(); } finally {
      if (externo) { const l = this._lote; this._lote = null; this._emitir([...l.ids], l.acao); }
    }
  }

  // ---- serialização ----
  paraJSON() {
    const camadas = {};
    for (const [k, v] of this.camadas) camadas[k] = { ...v };
    // sem clonar: quem chama serializa em seguida (JSON.stringify), e clonar cada uma
    // das centenas de milhares de entidades de um desenho grande dobrava o tempo e a memória
    return { nome: this.nome, unidade: this.unidade, escala: this.escala, camadas,
             entidades: [...this.entidades.values()], vistas: this.vistas, metadados: this.metadados };
  }

  static deJSON(d) {
    const doc = new Desenho2D((d && d.nome) || 'Desenho');
    if (!d) return doc;
    doc.unidade = d.unidade || 'mm';
    doc.escala = Number(d.escala) || 20;
    doc.vistas = d.vistas || [];
    doc.metadados = d.metadados || {};
    if (d.camadas && Object.keys(d.camadas).length) {
      doc.camadas = new Map();
      for (const [k, v] of Object.entries(d.camadas)) {
        doc.camadas.set(k, { nome: v.nome || k, cor: v.cor || '#4b5563', visivel: v.visivel !== false,
                             bloqueada: !!v.bloqueada, tipo_linha: v.tipo_linha || 'CONTINUOUS', espessura: v.espessura || 0.25 });
      }
    }
    for (const e of d.entidades || []) {
      if (!TIPOS.includes(e.tipo)) continue;
      try { doc.entidades.set(e.id || novoId(), criar({ ...e, id: e.id || novoId() })); } catch (err) { console.warn('entidade ignorada', e, err); }
    }
    return doc;
  }

  substituirPor(outro) {
    this.nome = outro.nome; this.unidade = outro.unidade; this.escala = outro.escala;
    this.camadas = outro.camadas; this.entidades = outro.entidades; this.vistas = outro.vistas; this.metadados = outro.metadados;
    this.notificar([], 'tudo');
  }
}
