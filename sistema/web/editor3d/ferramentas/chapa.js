// Chapa: contorno no plano da face, espessura e furos de parafuso.
//
// Na ordem em que se detalha uma ligação:
//   1. contorno — o primeiro clique numa face escolhe o plano (os eixos dele seguem a peça: o X ao longo da barra ou
//      do lado comprido da face). Retângulo (o padrão): o segundo clique é o canto oposto, ou digite "200;300"
//      (largura ao longo da peça; altura atravessada). Polígono: um clique por vértice — Enter, duplo clique ou
//      clique no primeiro ponto fecham; um número digitado é o comprimento do lado.
//   2. a chapa é criada com a espessura do painel. Desenhada numa face, ela fica EM CIMA da face (cresce para fora
//      da peça); solta no espaço, centrada no plano.
//   3. furos — cada clique dentro da chapa põe um furo do parafuso ativo (furo-padrão da norma, d + 1,5); o ponto anda
//      de 5 em 5 mm a partir do canto e mostra as distâncias às bordas. Digite "40;60" para o furo a 40 × 60 do canto,
//      "M16" para trocar o parafuso ou só um número ("8") para trocar a espessura da chapa recém-criada. Enter ou Esc
//      encerram.
// A chapa é a entidade paramétrica `Chapa`: contorno em coordenadas do plano, espessura e furos — o que o IFC, o
// detalhamento e a lista de materiais leem.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
import { furoDoParafuso } from './parafuso.js';

//: espessuras comerciais de chapa (mm), para a lista do painel
const ESPESSURAS = [3, 4.75, 6.3, 8, 9.5, 12.5, 16, 19, 22.4, 25, 31.5, 37.5];
const ACOS = ['ASTM A36', 'ASTM A572 Gr.50', 'SAE 1020', 'USI CIVIL 300'];
const num = (x) => String(Math.round(x * 10) / 10).replace('.', ',');

/** "M16", "16", "3/4"", "5/8" → diâmetro nominal do parafuso em mm (ou null). */
export function lerParafuso(texto) {
  const t = String(texto || '').trim().toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M(\d+(?:\.\d+)?)$/);
  if (m) return { nome: `M${m[1]}`, d: +m[1] };
  m = t.match(/^(\d+)\/(\d+)(?:"|POL)?$/);
  if (m && +m[2] > 0) return { nome: `${m[1]}/${m[2]}"`, d: Math.round(25.4 * (+m[1]) / (+m[2]) * 100) / 100 };
  m = t.match(/^(\d+(?:\.\d+)?)("|POL)$/);
  if (m) return { nome: `${m[1]}"`, d: Math.round(25.4 * (+m[1]) * 100) / 100 };
  return null;
}

export class FerramentaChapa extends Ferramenta {
  static id = 'chapa';
  static nome = 'Chapa';
  static atalho = 'H';
  static grupo = 'estrutura';
  static dica = 'Clique na face onde vai a chapa (o primeiro canto)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 7.5 10 4l11 4.5-7 3.5Z"/><path d="M3 7.5v3l11 4.5v-3"/><path d="M14 12v3l7-3.5v-3"/><circle cx="8.6" cy="7.2" r="1"/><circle cx="15.4" cy="9.2" r="1"/></svg>`;
  //: 'retangulo' (dois cantos ou "200;300") ou 'poligono' (vértice a vértice)
  static modo = 'retangulo';
  static espessura = 9.5;
  static aco = 'ASTM A36';
  //: o parafuso dos furos: {nome, d}; vazio = o tamanho da ferramenta Parafuso
  static parafuso = null;
  static passo = 5;

  ativar() {
    this.passo = 'contorno';
    this.plano = null;
    this.pontos = [];
    this.atual = null;
    this.eixo = null;
    this.chapaId = null;
    this.furos = [];
    this.naFace = false;
    this._dicaInicial();
  }

  desativar() { this.reiniciar(); }

  _dicaInicial() {
    const F = this.constructor;
    this.dica(`Chapa ${num(F.espessura)} mm (${F.modo === 'retangulo' ? 'retângulo' : 'polígono'}): clique na face onde ela vai — o primeiro canto · espessura e forma no painel`);
    this.medida('');
  }

  get espessura() { return this.constructor.espessura || 9.5; }
  set espessura(v) { this.constructor.espessura = v; }

  /** O parafuso dos furos: o escolhido aqui, senão o da ferramenta Parafuso (M12 de início). */
  get parafuso() {
    const F = this.constructor;
    if (F.parafuso && F.parafuso.d > 0) return F.parafuso;
    const P = this.editor && this.editor.ferramentas && this.editor.ferramentas.get('parafuso');
    const d = (P && P.tamanho && P.tamanho.d) || 12;
    return { nome: `M${num(d)}`, d };
  }

  get diametroFuro() { return furoDoParafuso(this.parafuso.d); }

  /** Números, ";" e o "M" do parafuso vão para a caixa de medidas. */
  teclaDeValor(k) { return /^[0-9]$/.test(k) || (this.passo === 'furos' && /^[Mm]$/.test(k)); }

  // ------------------------------------------------------------- painel

  painel(raiz, el) {
    const F = this.constructor;
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Chapa a desenhar' }),
                   el('span', { texto: `${num(F.espessura)} mm · ${F.aco} · furos ${this.parafuso.nome} (Ø${num(this.diametroFuro)})` })));
    const g = el('div', { class: 'campos' });
    const selM = el('select', { title: 'Retângulo: dois cantos (ou digite "200;300"). Polígono: um clique por vértice' });
    selM.append(el('option', { value: 'retangulo', texto: 'retângulo' }), el('option', { value: 'poligono', texto: 'polígono' }));
    selM.value = F.modo;
    selM.addEventListener('change', () => { F.modo = selM.value; if (this.passo === 'contorno') { this.reiniciar(); this._dicaInicial(); } });
    const inE = el('input', { type: 'number', min: '1', step: '0.05', value: String(F.espessura), list: 'chapa-espessuras', title: 'Espessura da chapa, mm' });
    const dl = el('datalist', { id: 'chapa-espessuras' });
    for (const e of ESPESSURAS) dl.append(el('option', { value: String(e) }));
    inE.addEventListener('change', () => { const e = +inE.value; if (e > 0) this._trocarEspessura(e); });
    const selA = el('select', { title: 'Aço da chapa (vai para a lista de materiais)' });
    for (const a of ACOS) selA.append(el('option', { value: a, texto: a }));
    if (!ACOS.includes(F.aco)) selA.append(el('option', { value: F.aco, texto: F.aco }));
    selA.value = F.aco;
    selA.addEventListener('change', () => { F.aco = selA.value; });
    const inP = el('input', { type: 'text', value: F.parafuso ? F.parafuso.nome : '', placeholder: this.parafuso.nome,
                              title: 'Parafuso dos furos: M12, M16, 3/4"… (vazio = o da ferramenta Parafuso). O furo é o padrão da norma, d + 1,5', style: 'width:6em' });
    inP.addEventListener('change', () => {
      const v = inP.value.trim();
      if (!v) { F.parafuso = null; return; }
      const r = lerParafuso(v);
      if (r) F.parafuso = r; else inP.value = F.parafuso ? F.parafuso.nome : '';
    });
    const selP = el('select', { title: 'O ponto anda de tantos em tantos mm (o canto e o furo)' });
    for (const [v, t] of [[0, 'livre'], [1, '1 mm'], [5, '5 mm'], [10, '10 mm']]) selP.append(el('option', { value: String(v), texto: t }));
    selP.value = String(F.passo || 0);
    selP.addEventListener('change', () => { F.passo = +selP.value; });
    g.append(el('label', { texto: 'Forma' }), selM,
             el('label', { texto: 'Espessura (mm)' }), el('span', {}, inE, dl),
             el('label', { texto: 'Aço' }), selA,
             el('label', { texto: 'Parafuso' }), inP,
             el('label', { texto: 'Passo' }), selP);
    raiz.append(g);
    raiz.append(el('p', { class: 'nota', texto: 'Na face de uma peça, a chapa fica em cima da face (cresce para fora). Depois de criada, cada clique dentro dela fura; "40;60" fura a 40 × 60 do canto; um número sozinho troca a espessura.' }));
  }

  _trocarEspessura(e) {
    this.espessura = e;
    if (this.chapaId && this.documento.get(this.chapaId)) {
      const ch = this.documento.get(this.chapaId);
      const campos = { espessura: e };
      if (/^CH /.test(ch.nome || '')) campos.nome = this._nomeDaChapa(ch.contorno || [], e);
      this.executar(C.cmdAlterar(this.chapaId, campos, 'Espessura da chapa'));
      this.dica(`Chapa de ${num(e)} mm — clique para furar com ${this.parafuso.nome}, "40;60" fura pelo canto; Enter ou Esc encerram`);
    }
    this.desenhar();
  }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (this.passo === 'contorno') {
      this.atual = this.pontos.length ? this.resolver(C.noPlano(this.editor, p, this.plano)) : null;
    } else if (this.passo === 'furos') {
      this.atual = this._noPasso(C.noPlano(this.editor, p, this.plano));
    }
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (this.passo === 'contorno') return this.pontoDoContorno(p);
    if (this.passo === 'furos') return this.furarEm(this._noPasso(C.noPlano(this.editor, p, this.plano)));
  }

  onDuploClique() {
    if (this.passo === 'contorno' && this.constructor.modo === 'poligono') this.fecharContorno();
  }

  onValor(texto) {
    const t = String(texto).trim();
    if (this.passo === 'contorno') {
      if (!this.pontos.length) return false;
      const partes = t.split(/[;x×*]/).map(paraMilimetros);
      if (this.constructor.modo === 'retangulo') {
        // "200;300": largura ao longo do X do plano, altura no Y; o sentido é o do mouse
        const [a, b] = partes.length >= 2 ? partes : [partes[0], partes[0]];
        if (!(a > 0) || !(b > 0)) return false;
        const o = this.pontos[0];
        const uv = this.atual ? C.para2d(this.plano, this.atual) : [1, 1];
        const o2 = C.para2d(this.plano, o);
        const sx = uv[0] - o2[0] < 0 ? -1 : 1, sy = uv[1] - o2[1] < 0 ? -1 : 1;
        this._retangulo(o, C.para3d(this.plano, o2[0] + sx * a, o2[1] + sy * b));
        return true;
      }
      const d = partes[0];
      if (!isFinite(d) || d <= 0 || !this.atual) return false;
      const base = this.pontos[this.pontos.length - 1];
      const dir = C.sub(this.atual, base);
      if (C.comp(dir) < 1e-6) return false;
      this.acrescentar(C.add(base, C.mul(C.normalizar(dir), d)));
      return true;
    }
    if (this.passo === 'furos') {
      const par = lerParafuso(t);
      if (par) {
        this.constructor.parafuso = par;
        this.dica(`Furos de ${par.nome} (Ø${num(this.diametroFuro)}) — clique para furar, "40;60" fura pelo canto`);
        if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
        return true;
      }
      const xy = t.split(';').map(paraMilimetros);
      if (xy.length === 2 && xy.every(v => isFinite(v))) {
        // a partir do canto de menor X e Y do contorno
        const c2 = this.contorno2d();
        const x0 = Math.min(...c2.map(q => q[0])), y0 = Math.min(...c2.map(q => q[1]));
        this.furarEm(C.para3d(this.plano, x0 + xy[0], y0 + xy[1]));
        return true;
      }
      const e = paraMilimetros(t);
      if (isFinite(e) && e > 0 && e < 200) { this._trocarEspessura(e); return true; }
      return false;
    }
    return false;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (this.passo === 'contorno') {
      if (C.teclaDeEixo(this, ev)) { this.desenhar(); return true; }
      if (ev.key === 'Enter' && this.constructor.modo === 'poligono') { this.fecharContorno(); return true; }
      return false;
    }
    if (ev.key === 'Enter' && this.passo === 'furos') { this.concluir(); return true; }
    return false;
  }

  cancelar() {
    if (this.passo === 'furos') { this.concluir(); return; }
    if (this.pontos.length) { this.reiniciar(); this._dicaInicial(); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- contorno

  resolver(ponto) {
    if (!this.pontos.length) return C.copiar(ponto);
    const q = this.plano ? C.projetarNoPlano(this.plano, ponto) : C.copiar(ponto);
    if (this.eixo) return C.projetarNoEixo(this.pontos[this.pontos.length - 1], q, this.eixo);
    return this._noPasso(q, this.pontos[0]);
  }

  /** O ponto do plano levado ao passo (5 mm) a partir de `ref` (o primeiro canto, ou o canto mínimo da chapa). */
  _noPasso(q, ref = null) {
    const passo = this.constructor.passo || 0;
    if (!passo || !this.plano) return q;
    let r2;
    if (ref) r2 = C.para2d(this.plano, ref);
    else {
      const c2 = this.contorno2d();
      r2 = [Math.min(...c2.map(v => v[0])), Math.min(...c2.map(v => v[1]))];
    }
    const q2 = C.para2d(this.plano, q);
    return C.para3d(this.plano, r2[0] + Math.round((q2[0] - r2[0]) / passo) * passo, r2[1] + Math.round((q2[1] - r2[1]) / passo) * passo);
  }

  /**
   * O plano do primeiro clique: a face sob o cursor (o raio, não o snap — o canto de uma peça lá atrás não serve), com o
   * X ao longo da peça (a barra, o lado comprido da face, o X da chapa) para "200;300" sair alinhado com ela.
   */
  _planoDoClique(p) {
    const t = p && p.tela;
    const sob = t && this.editor.selecao && this.editor.selecao.sob ? this.editor.selecao.sob(t[0], t[1]) : null;
    if (!sob || !sob.entidade) {
      const pl = C.planoDoPonto(this.editor, p);
      pl.origem = C.copiar(p.ponto);
      return { plano: pl, naFace: false };
    }
    const n = C.normalizar(sob.normal);
    const ent = sob.entidade;
    // origem: o ponto do snap, se estiver na face; senão o do raio
    const noPlano = Math.abs(C.dot(C.sub(p.ponto, sob.ponto), n)) <= 1.0;
    const origem = C.copiar(noPlano ? p.ponto : sob.ponto);
    let dir = null;
    if (ent.tipo === 'barra') dir = C.sub(ent.fim, ent.inicio);
    else if (ent.tipo === 'chapa') dir = ent.eixo_x;
    else if (ent.vertices && ent.faces) {
      // a aresta mais comprida das faces que estão no plano clicado
      let dm = 0;
      const vs = ent.vertices;
      const naFace = (q) => Math.abs(C.dot(C.sub(q, sob.ponto), n)) < 0.8;
      for (const f of ent.faces) {
        if (!f.every(i => vs[i] && naFace(vs[i]))) continue;
        for (let k = 0; k < f.length; k++) {
          const a = vs[f[k]], b = vs[f[(k + 1) % f.length]];
          const d = C.dist(a, b);
          if (d > dm) { dm = d; dir = C.sub(b, a); }
        }
      }
    }
    let ex = dir ? C.sub(dir, C.mul(n, C.dot(dir, n))) : null;
    if (!ex || C.comp(ex) < 1e-6) return { plano: C.planoDe(origem, n), naFace: true };
    ex = C.normalizar(ex);
    // o X para o lado positivo do mundo (as medidas digitadas não saem invertidas à toa)
    const s = ex[0] + ex[1] * 0.5 + ex[2] * 0.25;
    if (s < 0) ex = C.mul(ex, -1);
    const ey = C.normalizar(C.cross(n, ex));
    return { plano: { origem, normal: n, ex, ey }, naFace: true };
  }

  pontoDoContorno(p) {
    if (!this.pontos.length) {
      const { plano, naFace } = this._planoDoClique(p);
      this.plano = plano;
      this.naFace = naFace;
      const q0 = plano.origem;
      this.pontos.push(C.copiar(q0));
      C.ancorar(this.editor, q0);
      this.dica(this.constructor.modo === 'retangulo'
        ? 'Clique no canto oposto — ou digite largura;altura ("200;300", a largura ao longo da peça)'
        : 'Clique nos demais pontos — Enter ou duplo clique fecham o contorno; um número é o comprimento do lado');
      this.desenhar();
      return;
    }
    const q = this.resolver(C.noPlano(this.editor, p, this.plano));
    if (this.constructor.modo === 'retangulo') { this._retangulo(this.pontos[0], q); return; }
    if (this.pontos.length >= 3 && C.iguais(this.pontos[0], q, 1.0)) { this.fecharContorno(); return; }
    if (C.iguais(this.pontos[this.pontos.length - 1], q, 0.5)) return;
    this.acrescentar(q);
  }

  /** Os quatro cantos do retângulo de `a` a `b` nos eixos do plano. */
  _cantos(a, b) {
    const a2 = C.para2d(this.plano, a), b2 = C.para2d(this.plano, b);
    return [[a2[0], a2[1]], [b2[0], a2[1]], [b2[0], b2[1]], [a2[0], b2[1]]].map(([u, v]) => C.para3d(this.plano, u, v));
  }

  _retangulo(a, b) {
    const a2 = C.para2d(this.plano, a), b2 = C.para2d(this.plano, b);
    if (Math.abs(b2[0] - a2[0]) < 1 || Math.abs(b2[1] - a2[1]) < 1) { this.dica('O retângulo precisa de largura e altura: clique no canto oposto, na diagonal'); return; }
    this.pontos = this._cantos(a, b);
    this.criar();
  }

  acrescentar(q) {
    this.pontos.push(q);
    C.ancorar(this.editor, q);
    this.desenhar();
  }

  fecharContorno() {
    if (this.pontos.length < 3) { this.dica('A chapa precisa de pelo menos três pontos.'); return; }
    this.criar();
  }

  // ------------------------------------------------------------- entidade

  contorno2d() {
    const pts = this.pontos.map(p => C.para2d(this.plano, p));
    return C.areaAssinada(pts) >= 0 ? pts : pts.reverse();
  }

  /** O nome de produção da chapa feita à mão, pelas medidas ("CH 200×100×8"): sem marca, o detalhamento mostrava o
   *  código interno (e3f…) — revisão 14/10, D7. A marca de posição vem do Numerar. */
  _nomeDaChapa(c2, e) {
    const w = Math.max(...c2.map(q => q[0])) - Math.min(...c2.map(q => q[0]));
    const h = Math.max(...c2.map(q => q[1])) - Math.min(...c2.map(q => q[1]));
    const [a, b] = [w, h].sort((x, y) => y - x);
    return `CH ${num(a)}×${num(b)}×${num(e)}` + (c2.length !== 4 ? ' (recortada)' : '');
  }

  criar() {
    const e = this.espessura;
    const F = this.constructor;
    const ent = {
      tipo: 'chapa', id: C.novoId('ch'),
      nome: this._nomeDaChapa(this.contorno2d(), e), camada: (this.editor && this.editor.camadaAtiva) || 'Chapas',
      material: '', visivel: true, bloqueada: false, grupo: '',
      origem: C.copiar(this.plano.origem),
      eixo_x: C.copiar(this.plano.ex), eixo_y: C.copiar(this.plano.ey),
      // na face de uma peça, a chapa fica em cima dela (cresce para a normal, que olha para fora da peça); antes saía
      // centrada no plano — metade enterrada na mesa (revisão 14/10)
      contorno: this.contorno2d(), espessura: e, centrada: !this.naFace, furos: [],
      aco: F.aco || 'ASTM A36',
      atributos: { criado_no_editor: true },
    };
    this.chapaId = ent.id;
    this.furos = [];
    this.executar(C.cmdAdicionar(ent, 'Criar chapa'));
    this.passo = 'furos';
    this.atual = null;
    C.desancorar(this.editor);
    const c2 = ent.contorno;
    const w = Math.max(...c2.map(q => q[0])) - Math.min(...c2.map(q => q[0]));
    const h = Math.max(...c2.map(q => q[1])) - Math.min(...c2.map(q => q[1]));
    this.dica(`Chapa ${num(w)} × ${num(h)} × ${num(e)} mm criada — clique para furar com ${this.parafuso.nome} (Ø${num(this.diametroFuro)}), `
              + '"40;60" fura pelo canto, um número troca a espessura; Enter ou Esc encerram');
    this.medida(`${num(e)} mm`);
    this.desenhar();
  }

  furarEm(ponto) {
    if (!this.chapaId) return;
    const uv = C.para2d(this.plano, ponto);
    const c2 = this.contorno2d();
    const r = this.diametroFuro / 2;
    if (!C.dentroDoContorno(c2, uv) || this._distBorda(uv, c2) < r + 1) {
      this.dica(`O furo Ø${num(this.diametroFuro)} precisa caber dentro da chapa (a mais de ${num(r + 1)} mm da borda).`);
      return;
    }
    this.furos.push({ x: uv[0], y: uv[1], diametro: this.diametroFuro, parafuso: this.parafuso.nome });
    this.executar(C.cmdAlterar(this.chapaId, { furos: this.furos.map(f => ({ ...f })) }, 'Furar chapa'));
    this.dica(`${this.furos.length} furo(s) de ${this.parafuso.nome} (Ø${num(this.diametroFuro)}) — clique no próximo, "40;60" pelo canto; Enter ou Esc encerram`);
    this.desenhar();
  }

  _distBorda(uv, c2) {
    let m = Infinity;
    for (let i = 0; i < c2.length; i++) {
      const a = c2[i], b = c2[(i + 1) % c2.length];
      const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
      const t = L2 > 0 ? Math.max(0, Math.min(1, ((uv[0] - a[0]) * dx + (uv[1] - a[1]) * dy) / L2)) : 0;
      m = Math.min(m, Math.hypot(uv[0] - a[0] - t * dx, uv[1] - a[1] - t * dy));
    }
    return m;
  }

  concluir() {
    this.reiniciar();
    this._dicaInicial();
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.passo = 'contorno';
    this.pontos = [];
    this.atual = null;
    this.plano = null;
    this.eixo = null;
    this.chapaId = null;
    this.furos = [];
    this.naFace = false;
    this.limparPrevia();
    this.medida('');
  }

  // ------------------------------------------------------------- prévia

  circulo(centro2d, raio, n = 16, z = 0) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const q = C.para3d(this.plano, centro2d[0] + raio * Math.cos(a), centro2d[1] + raio * Math.sin(a));
      pts.push(z ? C.add(q, C.mul(this.plano.normal, z)) : q);
    }
    return pts;
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.passo === 'contorno') {
      for (const p of this.pontos) g.add(C.gPonto(p, C.CORES.cota));
      let lista = this.pontos;
      if (this.atual && this.pontos.length) {
        lista = this.constructor.modo === 'retangulo' ? this._cantos(this.pontos[0], this.atual) : this.pontos.concat([this.atual]);
      }
      if (lista.length >= 2) g.add(C.gLinha(lista, C.CORES.cota, { fechada: this.constructor.modo === 'retangulo' }));
      if (lista.length >= 3) {
        g.add(C.gPoligono(lista, C.CORES.cota, 0.18));
        if (this.constructor.modo !== 'retangulo') g.add(C.gLinha([lista[lista.length - 1], lista[0]], C.CORES.guia, { tracejada: true }));
      }
      if (this.pontos.length && this.atual) {
        if (this.constructor.modo === 'retangulo') {
          const a2 = C.para2d(this.plano, this.pontos[0]), b2 = C.para2d(this.plano, this.atual);
          const txt = `${num(Math.abs(b2[0] - a2[0]))} × ${num(Math.abs(b2[1] - a2[1]))} × ${num(this.espessura)} mm`;
          this.medida(txt);
          g.add(C.gRotulo(txt, C.meio(this.pontos[0], this.atual), '#4b5563'));
        } else {
          const d = C.dist(this.pontos[this.pontos.length - 1], this.atual);
          this.medida(formatar(d) + (this.eixo ? '  eixo ' + C.EIXOS[this.eixo].nome : ''));
        }
      }
    } else if (this.plano && this.pontos.length >= 3) {
      // a chapa criada, com os furos e o furo do cursor com as distâncias às bordas
      const z = this.naFace ? this.espessura + 0.5 : this.espessura / 2 + 0.5;
      const topo = this.pontos.map(p => C.add(p, C.mul(this.plano.normal, z)));
      g.add(C.gLinha(topo, C.CORES.cota, { fechada: true }));
      for (const f of (this.furos || [])) {
        g.add(C.gLinha(this.circulo([f.x, f.y], f.diametro / 2, 16, z), C.CORES.aviso, { fechada: true }));
      }
      if (this.passo === 'furos' && this.atual) {
        const uv = C.para2d(this.plano, this.atual);
        const c2 = this.contorno2d();
        const x0 = Math.min(...c2.map(q => q[0])), x1 = Math.max(...c2.map(q => q[0]));
        const y0 = Math.min(...c2.map(q => q[1])), y1 = Math.max(...c2.map(q => q[1]));
        const ok = C.dentroDoContorno(c2, uv) && this._distBorda(uv, c2) >= this.diametroFuro / 2 + 1;
        g.add(C.gLinha(this.circulo(uv, this.diametroFuro / 2, 16, z), ok ? C.CORES.desenho : '#b91c1c', { fechada: true }));
        const em = (u, v) => C.add(C.para3d(this.plano, u, v), C.mul(this.plano.normal, z));
        const c = em(uv[0], uv[1]);
        g.add(C.gLinha([c, em(x0, uv[1])], '#c2410c'));
        g.add(C.gLinha([c, em(uv[0], y0)], '#c2410c'));
        g.add(C.gRotulo(num(uv[0] - x0), em((uv[0] + x0) / 2, uv[1]), '#c2410c'));
        g.add(C.gRotulo(num(uv[1] - y0), em(uv[0], (uv[1] + y0) / 2), '#c2410c'));
        g.add(C.gRotulo(num(x1 - uv[0]), em((uv[0] + x1) / 2, uv[1]), '#475569'));
        g.add(C.gRotulo(num(y1 - uv[1]), em(uv[0], (uv[1] + y1) / 2), '#475569'));
        this.medida(`furo Ø${num(this.diametroFuro)} · ${this.parafuso.nome} · ${num(uv[0] - x0)};${num(uv[1] - y0)} do canto`);
      }
    }
    this.previa(g);
  }
}

export default FerramentaChapa;
