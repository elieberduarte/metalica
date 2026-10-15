// A tela do CAD: canvas 2D, janela de visualização, desenho das entidades e acerto.
//
// Sistema do modelo em milímetro com Y para cima; a tela em pixels com Y para baixo.
// `vp` guarda a janela: `z` pixels por milímetro, (`x`, `y`) o ponto do modelo no canto
// inferior esquerdo da tela. O que é "de papel" (texto, seta de cota, espaçamento de
// hachura) vale `mm_papel × escala_do_desenho` em milímetros do modelo, então aparece
// na tela do tamanho que terá impresso, em qualquer zoom.
//
// O desenho em si (fundo, grade, entidades) vai para um canvas de cache que só é
// refeito quando a janela, o documento, a seleção ou o tema mudam; o que acompanha o
// mouse (cursor, snap, prévia da ferramenta, retângulo de seleção) é desenhado por cima
// a cada quadro. Um desenho do modelo inteiro passa de cem mil objetos e leva quase um
// segundo para ser refeito; sem o cache, cada movimento do mouse custaria isso.

import { pontosArco, valorCota, dentroDe, segmentosDe, caixaDe, pontosDe, distanciaEntidade, pontosCota, textoDaChamada, cantosDoTextoDaChamada } from './desenho2d.js';

const TRACOS = { CONTINUOUS: [], HIDDEN: [6, 4], CENTER: [16, 4, 4, 4], DASHED: [8, 6], DOT: [2, 3] };
const PX_GRADE_ALVO = 60;
/** Até quantos objetos selecionados são pintados por cima do cache, a cada quadro. */
const SELECAO_POR_CIMA = 3000;

/** Número de cota: inteiro quando é, senão uma casa; com `casas` (0 a 3), sempre esse número de
 *  casas depois da vírgula (pedido do usuário, 28/09). */
export function formatarMm(v, casas = null) {
  if (casas != null && casas !== '' && isFinite(casas) && +casas >= 0) return v.toFixed(+casas).replace('.', ',');
  if (Math.abs(v - Math.round(v)) < 0.05) return String(Math.round(v));
  return v.toFixed(1).replace('.', ',');
}

/** Cor quase preta (luminância abaixo de 6%) — no tema escuro some no fundo: a do traço do
 *  desenho (#16202e, #2b3646) e a da folha e do carimbo (#111827) viram claras. */
function escuraDemais(c) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(c || '').trim());
  if (!m) return false;
  const h = m[1].length === 3 ? m[1].split('').map(x => x + x).join('') : m[1];
  const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const [r, g, b] = [0, 2, 4].map(k => lin(parseInt(h.slice(k, k + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.06;
}

export class Tela {
  constructor(canvas, documento) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.doc = documento;
    this.vp = { x: -100, y: -100, z: 0.5 };
    this.selecao = new Set();
    this.realce = null;                 // id sob o cursor
    this.regiao = null;                 // [[x0, y0], [x1, y1]] marcada pela tela dividida (o que o 3D escolheu)
    this.previa = [];                   // entidades temporárias da ferramenta
    this.snap = null;                   // {ponto, tipo}
    this.cursor = null;                 // ponto do modelo sob o mouse
    this.retangulo = null;              // seleção por janela [[x,y],[x,y]] em tela
    this.alcaQuente = null;             // alça sendo arrastada ({id, parte, ponto})
    this.escuro = false;
    this.grade = true;
    this._quadro = null;
    this.aoDesenhar = null;
  }

  // ------------------------------------------------------------ janela
  get largura() { return this.canvas.clientWidth; }
  get altura() { return this.canvas.clientHeight; }

  // a altura lida do canvas é uma consulta ao navegador: no meio do desenho (milhares de chamadas) vale a do quadro
  paraTela(p) { return [(p[0] - this.vp.x) * this.vp.z, (this._alturaDoQuadro || this.altura) - (p[1] - this.vp.y) * this.vp.z]; }
  paraMundo(px) { return [px[0] / this.vp.z + this.vp.x, ((this._alturaDoQuadro || this.altura) - px[1]) / this.vp.z + this.vp.y]; }
  /** mm do modelo por pixel. */
  get mmPorPixel() { return 1 / this.vp.z; }

  /**
   * Alças da seleção: nas cotas, os dois pontos de referência (p1, p2), o meio da linha de
   * cota e o número; nas linhas, as duas pontas e o meio; nas polilinhas, cada vértice. É por elas
   * que se ajusta com o mouse, como nos CADs (a ponta da linha vai até outro ponto).
   */
  alcas() {
    if (!this.selecao.size || this.selecao.size > 300) return [];
    const k = this.doc.escala, fora = [], pontas = [];
    for (const id of this.selecao) {
      const e = this.doc.get(id);
      if (!e || !this.doc.visivel(e)) continue;
      if (e.tipo === 'linha') {
        // a do meio move a linha inteira (no eixo da malha, só atravessado, com a bolinha e as cotas — 06/10)
        pontas.push({ id, parte: 'a', ponto: e.a }, { id, parte: 'b', ponto: e.b },
                    { id, parte: 'meio', ponto: [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2] });
        continue;
      }
      if (e.tipo === 'polilinha') { e.vertices.forEach((v, i) => pontas.push({ id, parte: 'v' + i, ponto: v })); continue; }
      if (e.tipo === 'arco') {
        // as pontas (deslizam na mesma curva) e o meio da curva (muda a flecha, as pontas ficam) — 06/10
        let a1 = e.fim; if (a1 < e.inicio) a1 += 360;
        const pt = (g) => [e.centro[0] + e.raio * Math.cos(g * Math.PI / 180), e.centro[1] + e.raio * Math.sin(g * Math.PI / 180)];
        pontas.push({ id, parte: 'a0', ponto: pt(e.inicio) }, { id, parte: 'a1', ponto: pt(e.fim) }, { id, parte: 'curva', ponto: pt((e.inicio + a1) / 2) });
        continue;
      }
      if (e.tipo === 'chamada') {
        // a ponta da seta e o texto (arrastar o texto leva a linha junto, a seta fica — 28/09)
        const c = cantosDoTextoDaChamada(e, k);
        fora.push({ id, parte: 'alvo', ponto: e.alvo },
                  { id, parte: 'texto', ponto: [(c[0][0] + c[2][0]) / 2, (c[0][1] + c[2][1]) / 2] });
        continue;
      }
      if (e.tipo !== 'cota') continue;
      const pc = pontosCota(e, k);
      fora.push({ id, parte: 'p1', ponto: e.p1 }, { id, parte: 'p2', ponto: e.p2 });
      if (pc.length === 4) fora.push({ id, parte: 'linha', ponto: [(pc[2][0] + pc[3][0]) / 2, (pc[2][1] + pc[3][1]) / 2] });
      const t = Tela.textoCota(e, k);
      if (t) fora.push({ id, parte: 'texto', ponto: t.pos });
    }
    // muitas pontas (uma janela sobre o desenho todo) viram poluição: só as cotas
    return pontas.length <= 400 ? fora.concat(pontas) : fora;
  }

  /** A alça a até `raio` pixels de `px`, ou null. */
  alcaSob(px, raio = 7) {
    let melhor = null, dm = raio;
    for (const a of this.alcas()) {
      const q = this.paraTela(a.ponto), d = Math.hypot(q[0] - px[0], q[1] - px[1]);
      if (d <= dm) { dm = d; melhor = a; }
    }
    return melhor;
  }

  redimensionar() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    }
    this.pedirQuadro();
  }

  enquadrar(caixa = null, margem = 0.08) {
    const c = caixa || this.doc.caixa();
    if (!c) { this.vp = { x: -200, y: -200, z: 0.5 }; this.pedirQuadro(); return; }
    const [[x0, y0], [x1, y1]] = c;
    const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1);
    const z = Math.min(this.largura / (w * (1 + 2 * margem)), this.altura / (h * (1 + 2 * margem)));
    this.vp.z = z;
    this.vp.x = (x0 + x1) / 2 - this.largura / 2 / z;
    this.vp.y = (y0 + y1) / 2 - this.altura / 2 / z;
    this.pedirQuadro();
  }

  zoom(fator, pxFixo) {
    const antes = this.paraMundo(pxFixo);
    this.vp.z = Math.min(200, Math.max(0.0005, this.vp.z * fator));
    const depois = this.paraMundo(pxFixo);
    this.vp.x += antes[0] - depois[0];
    this.vp.y += antes[1] - depois[1];
    this.pedirQuadro();
  }

  arrastar(dpx) {
    this.vp.x -= dpx[0] / this.vp.z;
    this.vp.y += dpx[1] / this.vp.z;
    this.pedirQuadro();
  }

  pedirQuadro() {
    if (this._quadro) return;
    this._quadro = requestAnimationFrame(() => { this._quadro = null; this.desenhar(); });
  }

  // ------------------------------------------------------------ desenho
  cores() {
    return this.escuro
      ? { fundo: '#0e131a', grade: 'rgba(255,255,255,.06)', grade10: 'rgba(255,255,255,.13)', eixo: 'rgba(255,255,255,.22)',
          selecao: '#4b9bf0', realce: '#7aa7f0', previa: '#e6bb52', snap: '#5fd08d', cursor: 'rgba(255,255,255,.35)',
          textoInvertido: (c) => (escuraDemais(c) ? '#e4eaf3' : c) }
      : { fundo: '#f4f6fa', grade: 'rgba(16,32,60,.06)', grade10: 'rgba(16,32,60,.12)', eixo: 'rgba(16,32,60,.28)',
          selecao: '#1f7ae0', realce: '#3d8fe6', previa: '#c07a00', snap: '#1c7a43', cursor: 'rgba(16,32,60,.45)',
          textoInvertido: (c) => c };
  }

  /** As cores do tema atual, guardadas (cada cota pedia o objeto novo). */
  _coresDoTema() {
    if (!this._cores || this._cores.escuro !== this.escuro) this._cores = { escuro: this.escuro, cores: this.cores() };
    return this._cores.cores;
  }

  /** O que define o conteúdo do cache, fora a janela: documento, tema, grade, tamanho. */
  _assinaturaConteudo() {
    return [this.canvas.width, this.canvas.height, this.escuro, this.grade, this.doc.versao, this.doc.escala].join('|');
  }

  /** A seleção pequena é pintada por cima do cache a cada quadro (clicar num objeto não refaz o desenho inteiro); a
   *  grande (uma janela sobre o desenho todo) vai dentro do cache, como antes. */
  _selecaoNoCache() { return this.selecao.size > SELECAO_POR_CIMA; }

  _mesmaSelecao(f) {
    const noCache = this._selecaoNoCache();
    if (noCache !== !!f.selecao) return false;
    if (!noCache) return true;
    if (f.selecao.size !== this.selecao.size) return false;
    for (const id of this.selecao) if (!f.selecao.has(id)) return false;
    return true;
  }

  _cacheValido() {
    const f = this._cache, v = this.vp;
    return !!f && f.assinatura === this._assinaturaConteudo() && this._mesmaSelecao(f)
      && f.vp.x === v.x && f.vp.y === v.y && f.vp.z === v.z;
  }

  /** Só a janela mudou (pan/zoom): o conteúdo do cache serve, deslocado e escalado. */
  _cacheSoDeslocado() {
    const f = this._cache;
    return !!f && f.assinatura === this._assinaturaConteudo() && this._mesmaSelecao(f);
  }

  /** Fundo, grade e entidades, num canvas do tamanho da tela (em pixels físicos). */
  _renderizarCache(cores) {
    const t0 = performance.now();
    const dpr = window.devicePixelRatio || 1;
    const f = this._cache || (this._cache = { canvas: document.createElement('canvas') });
    if (f.canvas.width !== this.canvas.width || f.canvas.height !== this.canvas.height) {
      f.canvas.width = this.canvas.width; f.canvas.height = this.canvas.height;
    }
    const ctx = f.canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = this._pintar(ctx, cores, 0, 0, this.largura, this.altura);
    f.assinatura = this._assinaturaConteudo();
    f.selecao = this._selecaoNoCache() ? new Set(this.selecao) : null;
    f.vp = { ...this.vp };
    f.desenhadas = n.desenhadas;
    f.pontos = n.pontos;
    f.duracao = performance.now() - t0;
  }

  /**
   * Pinta fundo, grade e entidades no retângulo de tela (x0, y0)–(x1, y1), em pixels CSS: a tela inteira (o cache) ou
   * só a faixa que apareceu num arrasto. Rápido num desenho de centenas de milhares de objetos (CD Bom Dia, 278 mil,
   * 11/10: o quadro levava ~1 s e o pan/zoom ficava segundos sem os detalhes):
   *  - linhas, polilinhas, círculos e arcos vão num caminho só por estilo (cor, espessura, tracejado): um traço por
   *    estilo em vez de um por objeto;
   *  - o que cabe em menos de um pixel vira um ponto, um só por pixel e um preenchimento por cor;
   *  - a cor de cada objeto (a troca das quase pretas no tema escuro) é calculada uma vez por cor, não por objeto;
   *  - hachuras por baixo, textos e cotas por cima, separados numa passada (sem ordenar a lista).
   */
  _pintar(ctx, cores, x0, y0, x1, y1) {
    const W = this.largura, H = this.altura;
    this._alturaDoQuadro = H;
    const parcial = x0 > 0 || y0 > 0 || x1 < W || y1 < H;
    ctx.save();
    if (parcial) { ctx.beginPath(); ctx.rect(x0, y0, x1 - x0, y1 - y0); ctx.clip(); }
    ctx.__fonte = null;
    ctx.fillStyle = cores.fundo;
    ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    if (this.grade) this._grade(ctx, cores);

    const k = this.doc.escala;                    // mm de papel → mm de modelo
    // só o que toca o retângulo, com margem para textos e cotas que se estendem além dos pontos que os definem
    const m0 = this.paraMundo([x0, y1]), m1 = this.paraMundo([x1, y0]), mg = 30 * k;
    const caixas = [];
    const ordem = this.doc.naRegiao([[m0[0] - mg, m0[1] - mg], [m1[0] + mg, m1[1] + mg]], caixas);
    const camadas = this.doc.camadas;
    const sel = this._selecaoNoCache() ? this.selecao : null;
    const corDaBruta = new Map();
    const corDe = (e, cam) => {
      // a cor própria do objeto (o DXF importado com as cores do CAD de origem), senão a da camada
      const bruta = (e.atributos && e.atributos.cor) || (cam && cam.cor) || '#4b5563';
      let c = corDaBruta.get(bruta);
      if (c === undefined) { c = cores.textoInvertido(bruta); corDaBruta.set(bruta, c); }
      return c;
    };
    const { x: vx, y: vy, z } = this.vp;
    // nível de detalhe: o que cabe em menos de um pixel (parafusos e furos com a vista afastada) vira um ponto
    const minimo = 0.8 * this.mmPorPixel;
    // um ponto por pixel, com a cor do último objeto que caiu nele (como quando cada um era pintado por cima do outro)
    const Wi = Math.ceil(W) + 1, Hi = Math.ceil(H) + 1;
    if (!this._ocupado || this._ocupado.length !== Wi * Hi) this._ocupado = new Uint16Array(Wi * Hi); else this._ocupado.fill(0);
    const ocupado = this._ocupado, coresDosPontos = [], indiceDaCor = new Map();
    const tracos = new Map(), hachuras = [], porCima = [], selecionadas = [];
    let nPontos = 0, nDesenhadas = 0;
    for (let i = 0; i < ordem.length; i++) {
      const e = ordem[i], cam = camadas.get(e.camada);
      if (cam && cam.visivel === false) continue;
      if (sel && sel.has(e.id)) { selecionadas.push(e); continue; }
      const tipo = e.tipo;
      if (tipo !== 'texto') {
        const c = caixas[i];
        if (c[1][0] - c[0][0] < minimo && c[1][1] - c[0][1] < minimo) {
          const ix = Math.floor((c[0][0] - vx) * z), iy = Math.floor(H - (c[0][1] - vy) * z) - 1;
          if (ix < 0 || iy < 0 || ix >= Wi || iy >= Hi) continue;
          const cor = corDe(e, cam);
          let ic = indiceDaCor.get(cor);
          if (ic === undefined && coresDosPontos.length < 65535) { coresDosPontos.push(cor); indiceDaCor.set(cor, ic = coresDosPontos.length); }
          if (ic !== undefined) ocupado[iy * Wi + ix] = ic;
          nPontos++;
          continue;
        }
      }
      nDesenhadas++;
      if (tipo === 'hachura') { hachuras.push(e); continue; }
      if (tipo === 'texto' || tipo === 'cota' || tipo === 'chamada') { porCima.push(e); continue; }
      const cor = corDe(e, cam);
      const esp = (cam && cam.espessura) || 0.25, larg = Math.max(1, Math.min(3, esp / 0.25));
      const tl = (cam && cam.tipo_linha) || 'CONTINUOUS';
      const chave = cor + '|' + larg + '|' + tl;
      let lote = tracos.get(chave);
      if (!lote) tracos.set(chave, lote = { cor, larg, tracos: TRACOS[tl] || [], p: new Path2D() });
      lote.ultimo = nDesenhadas;
      this._caminho(lote.p, e, H);
    }
    for (const e of hachuras) { const cam = camadas.get(e.camada); this._entidade(ctx, e, corDe(e, cam), cam, k, false); }
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    // o lote cujo último objeto veio depois vai por cima: onde linhas de cores diferentes se sobrepõem (o contorno da
    // telha em cinza e em cor), fica a de cima como quando cada objeto era pintado na sua vez
    for (const l of [...tracos.values()].sort((a, b) => a.ultimo - b.ultimo)) {
      ctx.strokeStyle = l.cor; ctx.lineWidth = l.larg; ctx.setLineDash(l.tracos);
      ctx.stroke(l.p);
    }
    ctx.setLineDash([]);
    if (nPontos) {
      const pontos = coresDosPontos.map(() => new Path2D());
      for (let i = 0; i < ocupado.length; i++) { const ic = ocupado[i]; if (ic) pontos[ic - 1].rect(i % Wi, (i / Wi) | 0, 1, 1); }
      pontos.forEach((p, i) => { ctx.fillStyle = coresDosPontos[i]; ctx.fill(p); });
    }
    // textos longe demais para ler viram traços, juntos num preenchimento por cor (_texto)
    this._tracosDeTexto = new Map();
    for (const e of porCima) { const cam = camadas.get(e.camada); this._entidade(ctx, e, corDe(e, cam), cam, k, false); }
    ctx.globalAlpha = 0.5;
    for (const [cor, p] of this._tracosDeTexto) { ctx.fillStyle = cor; ctx.fill(p); }
    ctx.globalAlpha = 1;
    this._tracosDeTexto = null;
    for (const e of selecionadas) this._entidade(ctx, e, cores.selecao, camadas.get(e.camada), k, true);
    ctx.restore();
    ctx.__fonte = null;
    this._alturaDoQuadro = null;
    return { desenhadas: nDesenhadas + selecionadas.length, pontos: nPontos };
  }

  /** Acrescenta ao caminho `p` o traço de uma linha, polilinha, círculo ou arco, em pixels de tela. */
  _caminho(p, e, H) {
    const { x: vx, y: vy, z } = this.vp;
    switch (e.tipo) {
      case 'linha': p.moveTo((e.a[0] - vx) * z, H - (e.a[1] - vy) * z); p.lineTo((e.b[0] - vx) * z, H - (e.b[1] - vy) * z); break;
      case 'polilinha': {
        const v = e.vertices;
        if (v.length < 2) break;
        p.moveTo((v[0][0] - vx) * z, H - (v[0][1] - vy) * z);
        for (let i = 1; i < v.length; i++) p.lineTo((v[i][0] - vx) * z, H - (v[i][1] - vy) * z);
        // fechada: de volta ao primeiro vértice (o closePath num caminho com milhares de figuras custava caro)
        if (e.fechada) p.lineTo((v[0][0] - vx) * z, H - (v[0][1] - vy) * z);
        break;
      }
      case 'circulo': {
        const cx = (e.centro[0] - vx) * z, cy = H - (e.centro[1] - vy) * z, r = e.raio * z;
        p.moveTo(cx + r, cy); p.arc(cx, cy, r, 0, Math.PI * 2); break;
      }
      case 'arco': {
        // canvas mede ângulos no sentido horário (y para baixo): inverte
        const cx = (e.centro[0] - vx) * z, cy = H - (e.centro[1] - vy) * z, r = e.raio * z;
        const a0 = -e.fim * Math.PI / 180;
        p.moveTo(cx + r * Math.cos(a0), cy + r * Math.sin(a0));
        p.arc(cx, cy, r, a0, -e.inicio * Math.PI / 180); break;
      }
    }
  }

  /**
   * Pan puro (o zoom não mudou): o cache anda um número inteiro de pixels físicos e só a faixa que apareceu na borda é
   * pintada — o arrasto mostra na hora o que estava fora da tela, em vez do vazio até a mão parar (11/10). A janela é
   * acertada para o deslocamento inteiro (menos de meio pixel), e o que já estava pintado serve sem reamostrar. Quando
   * a mão para, o quadro é refeito inteiro: cada faixa decide sozinha qual cor fica por cima onde linhas se sobrepõem.
   * Falso quando não se aplica (zoom, ou um salto de mais de meia tela).
   */
  _deslocarPorFaixas(cores) {
    const f = this._cache, v = this.vp;
    if (f.vp.z !== v.z) return false;
    const dpr = window.devicePixelRatio || 1, W = this.largura, H = this.altura;
    const Dx = Math.round((f.vp.x - v.x) * v.z * dpr), Dy = Math.round((v.y - f.vp.y) * v.z * dpr);
    if (Math.abs(Dx) * 2 >= f.canvas.width || Math.abs(Dy) * 2 >= f.canvas.height) return false;
    v.x = f.vp.x - Dx / (dpr * v.z);
    v.y = f.vp.y + Dy / (dpr * v.z);
    if (Dx || Dy) {
      const g = f.troca || (f.troca = document.createElement('canvas'));
      if (g.width !== f.canvas.width || g.height !== f.canvas.height) { g.width = f.canvas.width; g.height = f.canvas.height; }
      const ctx = g.getContext('2d');
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(f.canvas, Dx, Dy);
      f.troca = f.canvas; f.canvas = g;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const dx = Dx / dpr, dy = Dy / dpr;
      if (dx > 0) this._pintar(ctx, cores, 0, 0, dx, H); else if (dx < 0) this._pintar(ctx, cores, W + dx, 0, W, H);
      if (dy > 0) this._pintar(ctx, cores, 0, 0, W, dy); else if (dy < 0) this._pintar(ctx, cores, 0, H + dy, W, H);
      this._agendarDefinitivo(true);
    }
    f.vp = { ...v };
    return true;
  }

  /** O quadro definitivo quando a janela fica parada 110 ms; `refazer`: também com o cache já na janela atual (o
   *  montado por faixas). */
  _agendarDefinitivo(refazer = false) {
    if (refazer) this._refazerAoParar = true;
    if (this._timerDefinitivo) clearTimeout(this._timerDefinitivo);
    this._timerDefinitivo = setTimeout(() => {
      this._timerDefinitivo = null; this._definitivo = true;
      if (this._refazerAoParar && this._cache) this._cache.vp = { x: NaN, y: NaN, z: NaN };
      this._refazerAoParar = false;
      this.pedirQuadro();
    }, 110);
  }

  /** Cache deslocado/escalado para a janela atual: resposta imediata ao pan e ao zoom
   *  num desenho pesado; o quadro definitivo vem quando a interação para. */
  _blitAproximado(ctx, cores) {
    const f = this._cache, W = this.largura, H = this.altura;
    const s = this.vp.z / f.vp.z;
    const dx = (f.vp.x - this.vp.x) * this.vp.z;
    const dy = H * (1 - s) - (f.vp.y - this.vp.y) * this.vp.z;
    ctx.fillStyle = cores.fundo;
    ctx.fillRect(0, 0, W, H);
    ctx.drawImage(f.canvas, dx, dy, W * s, H * s);
    this._agendarDefinitivo();
  }

  desenhar() {
    // escondido (a vista 3D da área de trabalho): o canvas tem tamanho zero e não há o que pintar;
    // ao aparecer, o redimensionamento pede o quadro de novo
    if (!this.canvas.width || !this.canvas.height || !this.largura || !this.altura) return;
    const ctx = this.ctx, dpr = window.devicePixelRatio || 1;
    const cores = this.cores();
    ctx.__fonte = null;                              // outros (o snap, a montagem) mudam a fonte deste canvas
    this._alturaDoQuadro = null;
    // pan puro: o cache anda e só a faixa nova é pintada
    if (!this._cacheValido() && this._cacheSoDeslocado()) this._deslocarPorFaixas(cores);
    // quadro pesado (> 40 ms) durante o zoom: aproxima com o cache e só refaz de
    // verdade quando a janela fica parada 110 ms
    const aproximar = !this._cacheValido() && this._cacheSoDeslocado() && this._cache.duracao > 40 && !this._definitivo;
    this._definitivo = false;
    if (aproximar) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._blitAproximado(ctx, cores);
    } else {
      if (!this._cacheValido()) this._renderizarCache(cores);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(this._cache.canvas, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const k = this.doc.escala;
    // a seleção pequena por cima do cache (a grande já está nele)
    if (this.selecao.size && !this._selecaoNoCache()) {
      for (const id of this.selecao) {
        const e = this.doc.get(id);
        if (e && this.doc.visivel(e)) this._entidade(ctx, e, cores.selecao, this.doc.camadas.get(e.camada), k, true);
      }
    }
    // realce do que está sob o mouse por cima do cache: passar o mouse não refaz o desenho
    if (this.realce && !this.selecao.has(this.realce)) {
      const e = this.doc.get(this.realce);
      if (e && this.doc.visivel(e)) this._entidade(ctx, e, cores.realce, this.doc.camadas.get(e.camada), k, false);
    }
    for (const e of this.previa) this._entidade(ctx, e, cores.previa, null, k, false, true);
    // a região que o 3D escolheu (tela dividida): retângulo laranja tracejado
    if (this.regiao) {
      const [a, b] = [this.paraTela(this.regiao[0]), this.paraTela(this.regiao[1])];
      ctx.setLineDash([8, 5]); ctx.lineWidth = 2; ctx.strokeStyle = '#f59e0b';
      ctx.strokeRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
      ctx.setLineDash([]);
    }
    // alças da seleção (quadradinhos; a que está sendo arrastada, cheia)
    for (const a of this.alcas()) {
      const [x, y] = this.paraTela(a.ponto);
      const quente = this.alcaQuente && this.alcaQuente.id === a.id && this.alcaQuente.parte === a.parte;
      ctx.setLineDash([]); ctx.lineWidth = 1; ctx.strokeStyle = cores.selecao;
      ctx.fillStyle = quente ? '#e0442f' : cores.selecao;
      if (a.parte === 'linha') { ctx.beginPath(); ctx.arc(x, y, 4.5, 0, Math.PI * 2); ctx.fill(); }
      else if (a.parte === 'texto') { ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 5, y); ctx.closePath(); ctx.fill(); }
      else ctx.fillRect(x - 4, y - 4, 8, 8);
    }

    if (this.retangulo) {
      const [a, b] = this.retangulo;
      ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.strokeStyle = cores.selecao;
      ctx.fillStyle = a[0] <= b[0] ? 'rgba(31,122,224,.08)' : 'rgba(31,160,80,.08)';
      ctx.fillRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
      ctx.strokeRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
      ctx.setLineDash([]);
    }
    if (this.snap) this._glifoSnap(ctx, this.snap, cores.snap);
    else if (this.cursor) {
      const [x, y] = this.paraTela(this.cursor);
      ctx.strokeStyle = cores.cursor; ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(x - 9, y); ctx.lineTo(x + 9, y); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 9); ctx.stroke();
    }
    if (this.aoDesenhar) this.aoDesenhar();
  }

  _grade(ctx, cores) {
    const mmpp = this.mmPorPixel;
    let passo = Math.pow(10, Math.ceil(Math.log10(mmpp * PX_GRADE_ALVO)));
    if (passo / mmpp > PX_GRADE_ALVO * 2.5) passo /= 2;
    const W = this.largura, H = this.altura;
    const m0 = this.paraMundo([0, H]), m1 = this.paraMundo([W, 0]);
    ctx.lineWidth = 1;
    for (const [p, cor] of [[passo, cores.grade], [passo * 10, cores.grade10]]) {
      if (p / mmpp < 6) continue;
      ctx.strokeStyle = cor; ctx.beginPath();
      for (let x = Math.floor(m0[0] / p) * p; x <= m1[0]; x += p) { const px = Math.round(this.paraTela([x, 0])[0]) + 0.5; ctx.moveTo(px, 0); ctx.lineTo(px, H); }
      for (let y = Math.floor(m0[1] / p) * p; y <= m1[1]; y += p) { const py = Math.round(this.paraTela([0, y])[1]) + 0.5; ctx.moveTo(0, py); ctx.lineTo(W, py); }
      ctx.stroke();
    }
    ctx.strokeStyle = cores.eixo; ctx.beginPath();
    const o = this.paraTela([0, 0]);
    ctx.moveTo(0, Math.round(o[1]) + 0.5); ctx.lineTo(W, Math.round(o[1]) + 0.5);
    ctx.moveTo(Math.round(o[0]) + 0.5, 0); ctx.lineTo(Math.round(o[0]) + 0.5, H);
    ctx.stroke();
    this.passoGrade = passo;
  }

  _estilo(ctx, cor, cam, selecionada, previa) {
    ctx.strokeStyle = cor; ctx.fillStyle = cor;
    const esp = (cam && cam.espessura) || 0.25;
    ctx.lineWidth = selecionada ? 2.2 : Math.max(1, Math.min(3, esp / 0.25));
    const tracos = TRACOS[(cam && cam.tipo_linha) || 'CONTINUOUS'] || [];
    ctx.setLineDash(previa ? [5, 4] : tracos);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  }

  _entidade(ctx, e, cor, cam, k, selecionada, previa = false) {
    const T = (p) => this.paraTela(p);
    this._estilo(ctx, cor, cam, selecionada, previa);
    switch (e.tipo) {
      case 'linha': { const a = T(e.a), b = T(e.b); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); break; }
      case 'polilinha': {
        if (e.vertices.length < 2) break;
        ctx.beginPath();
        e.vertices.forEach((p, i) => { const q = T(p); i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]); });
        if (e.fechada) ctx.closePath();
        ctx.stroke(); break;
      }
      case 'circulo': { const c = T(e.centro); ctx.beginPath(); ctx.arc(c[0], c[1], e.raio * this.vp.z, 0, Math.PI * 2); ctx.stroke(); break; }
      case 'arco': {
        const c = T(e.centro);
        // canvas mede ângulos no sentido horário (y para baixo): inverte
        ctx.beginPath(); ctx.arc(c[0], c[1], e.raio * this.vp.z, -e.fim * Math.PI / 180, -e.inicio * Math.PI / 180); ctx.stroke(); break;
      }
      case 'texto': this._texto(ctx, e.posicao, e.texto, e.altura * k, e.angulo || 0, e.alinhamento, e.vertical, cor); break;
      case 'cota': this._cota(ctx, e, k, cor); break;
      case 'hachura': this._hachura(ctx, e, k, cor); break;
      case 'chamada': this._chamada(ctx, e, k, cor); break;
    }
    ctx.setLineDash([]);
  }

  _texto(ctx, pos, texto, alturaMm, angulo, alinhamento = 'esquerda', vertical = 'base', cor) {
    const px = alturaMm * this.vp.z;
    const [x, y] = this.paraTela(pos);
    if (px < 2.5) {                      // longe demais para ler: um traço do tamanho do texto
      const w = (texto || '').length * px * 0.6, x0 = alinhamento === 'centro' ? x - w / 2 : alinhamento === 'direita' ? x - w : x;
      const lote = this._tracosDeTexto;  // pintando o cache: juntos, um preenchimento por cor no fim
      if (lote) { let p = lote.get(cor); if (!p) lote.set(cor, p = new Path2D()); p.rect(x0, y - px, w, px); return; }
      ctx.globalAlpha = 0.5; ctx.fillRect(x0, y - px, w, px); ctx.globalAlpha = 1;
      return;
    }
    // trocar a fonte custa (o navegador interpreta o texto dela): só quando muda
    const fonte = `${px}px "Segoe UI", Roboto, Arial, sans-serif`;
    if (ctx.__fonte !== fonte) { ctx.font = fonte; ctx.__fonte = fonte; }
    ctx.textAlign = alinhamento === 'centro' ? 'center' : alinhamento === 'direita' ? 'right' : 'left';
    ctx.textBaseline = vertical === 'meio' ? 'middle' : vertical === 'topo' ? 'top' : 'alphabetic';
    ctx.fillStyle = cor;
    if (!angulo) { ctx.fillText(texto || '', x, y); return; }
    // girado: a transformação montada direto (sem save/restore), e de volta à da tela
    const dpr = window.devicePixelRatio || 1, a = -angulo * Math.PI / 180, c = Math.cos(a) * dpr, s = Math.sin(a) * dpr;
    ctx.setTransform(c, s, -s, c, x * dpr, y * dpr);
    ctx.fillText(texto || '', 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  _seta(ctx, p, ang, tam) {
    const [x, y] = p;
    const a = -ang;                                   // tela com y invertido
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - tam * Math.cos(a - 0.35), y - tam * Math.sin(a - 0.35));
    ctx.lineTo(x - tam * Math.cos(a + 0.35), y - tam * Math.sin(a + 0.35));
    ctx.closePath(); ctx.fill();
  }

  /** A ponta da cota: seta cheia (padrão), bola ou traço oblíquo a 45°, como no AutoCAD. */
  _terminador(ctx, p, ang, tam, tipo) {
    if (tipo === 'bola') {
      ctx.beginPath(); ctx.arc(p[0], p[1], Math.max(1.2, 0.35 * tam), 0, 2 * Math.PI); ctx.fill();
    } else if (tipo === 'traco') {
      const a = -(ang + Math.PI / 4), c = 0.5 * tam * Math.cos(a), s = 0.5 * tam * Math.sin(a);
      ctx.beginPath(); ctx.moveTo(p[0] - c, p[1] - s); ctx.lineTo(p[0] + c, p[1] + s); ctx.stroke();
    } else {
      this._seta(ctx, p, ang, tam);
    }
  }

  /** Geometria da cota em coordenadas do modelo (compartilhada com o acerto). */
  static geometriaCota(c, k) {
    let [x1, y1] = c.p1, [x2, y2] = c.p2;
    if (c.modo === 'h') y2 = y1; else if (c.modo === 'v') x2 = x1;
    const dx = x2 - x1, dy = y2 - y1, comp = Math.hypot(dx, dy);
    if (comp < 1e-9) return null;
    const ux = dx / comp, uy = dy / comp, nx = -uy, ny = ux;
    const desl = c.deslocamento * k;
    const a1 = [x1 + nx * desl, y1 + ny * desl], a2 = [x2 + nx * desl, y2 + ny * desl];
    return { a1, a2, ux, uy, nx, ny, comp, desl, x1, y1, x2, y2 };
  }

  /**
   * Onde vai o número da cota (base do texto, centrado) e o ângulo dele. `texto_pos`
   * (arrastado pela alça do texto) manda; sem ela, o número fica no meio da linha — e,
   * quando não cabe entre as chamadas, sai para fora (um degrau mais longe da peça), para
   * não encavalar no da cota vizinha.
   */
  static textoCota(c, k) {
    const g = Tela.geometriaCota(c, k);
    if (!g) return null;
    // o fator de tamanho da cota (texto, ponta e afastamentos juntos): a cota feita sobre um desenho importado acompanha
    // o tamanho das cotas dele (07/10); vazio = 1
    const f = c.fator || 1;
    const sg = g.desl >= 0 ? 1 : -1, seta = Math.min(2.5 * k * f, Math.max(1 * k * f, g.comp / 4));
    // sem texto escrito, a medida × a escala da cota (a cota feita na célula em 1:25 da prancha mostra a da peça)
    const txt = c.texto != null && c.texto !== '' ? String(c.texto) : formatarMm(valorCota(c) * (c.escala || 1), c.casas);
    const ang = Math.atan2(g.uy, g.ux);
    let angG = ang * 180 / Math.PI;
    const lado = (angG > -90 && angG <= 90) ? 1 : -1;
    if (lado < 0) angG += 180;
    const h = c.altura * k * f, off = h * 0.55 * lado;
    const fora = g.comp < 3 * seta;
    if (c.texto_pos) return { pos: c.texto_pos, txt, h, angG, g, seta, fora, ang };
    let mx = (g.a1[0] + g.a2[0]) / 2, my = (g.a1[1] + g.a2[1]) / 2;
    if (fora) { mx += g.ux * (2.4 * seta + 0.4 * h * txt.length); my += g.uy * (2.4 * seta + 0.4 * h * txt.length); }
    else if (0.62 * h * txt.length + 2 * seta > g.comp) { mx += g.nx * sg * 1.9 * h; my += g.ny * sg * 1.9 * h; }
    return { pos: [mx + g.nx * off, my + g.ny * off], txt, h, angG, g, seta, fora, ang };
  }

  _cota(ctx, c, k, cor) {
    const g = Tela.geometriaCota(c, k);
    if (!g) return;
    const z = this.vp.z, T = (p) => this.paraTela(p);
    const f = c.fator || 1;
    const sg = g.desl >= 0 ? 1 : -1, ext = 2 * k * f, fol = 1.5 * k * f, seta = Math.min(2.5 * k * f, Math.max(1 * k * f, g.comp / 4));
    ctx.setLineDash([]);
    ctx.beginPath();
    for (const [p, a] of [[c.p1, g.a1], [c.p2, g.a2]]) {
      const i = T([p[0] + g.nx * sg * fol, p[1] + g.ny * sg * fol]), f = T([a[0] + g.nx * sg * ext, a[1] + g.ny * sg * ext]);
      ctx.moveTo(i[0], i[1]); ctx.lineTo(f[0], f[1]);
    }
    const A1 = T(g.a1), A2 = T(g.a2);
    ctx.moveTo(A1[0], A1[1]); ctx.lineTo(A2[0], A2[1]); ctx.stroke();
    const ang = Math.atan2(g.uy, g.ux);
    const fora = g.comp < 3 * seta;
    const term = c.terminador || ((this.doc.metadados || {}).estilo || {}).terminador || 'traco';   // padrão: o traço oblíquo da produção
    this._terminador(ctx, A1, fora ? ang : ang + Math.PI, seta * z, term);
    this._terminador(ctx, A2, fora ? ang + Math.PI : ang, seta * z, term);
    const t = Tela.textoCota(c, k);
    // o número na cor do texto (branco no tema escuro, preto no claro), como o texto da cota do AutoCAD
    // — na cor da linha (verde) ele sumia no fundo (pedido do usuário, 28/09); selecionada/realce, na cor dela
    const cs = this._coresDoTema();
    const destacada = cor === cs.selecao || cor === cs.realce || cor === cs.previa;
    const camTexto = this.doc.camadas.get('TEXTO');
    this._texto(ctx, t.pos, t.txt, t.h, t.angG, 'centro', 'base', destacada ? cor : cs.textoInvertido((camTexto && camTexto.cor) || '#111827'));
  }

  _hachura(ctx, e, k, cor) {
    const ext = e.contornos[0];
    if (!ext || ext.length < 3) return;
    const T = (p) => this.paraTela(p);
    ctx.save();
    ctx.beginPath();
    for (const c of e.contornos) { c.forEach((p, i) => { const q = T(p); i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]); }); ctx.closePath(); }
    ctx.clip('evenodd');
    const esp = (e.padrao === 'solido' ? 0.6 : e.espacamento) * k * this.vp.z;
    // a caixa de todos os contornos: a hachura do DXF pode ter várias ilhas (as letras de um logotipo, os triângulos
    // de um perfil) e, com a caixa só do primeiro, só ele saía pintado (Vicente, 08/10)
    const todos = e.contornos.length > 1 ? e.contornos.flat() : ext;
    if (esp < 2.5 || e.padrao === 'solido') {           // longe (ou sólida): preenchimento no lugar das linhas
      ctx.globalAlpha = e.padrao === 'solido' ? 0.9 : 0.18; ctx.fillStyle = cor;
      const pts = todos.map(T); const cx = caixaDe(pts);
      ctx.fillRect(cx[0][0], cx[0][1], cx[1][0] - cx[0][0], cx[1][1] - cx[0][1]);
      ctx.restore(); return;
    }
    const pts = todos.map(T); const [[x0, y0], [x1, y1]] = caixaDe(pts);
    const a = -(e.angulo || 45) * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
    const diag = Math.hypot(x1 - x0, y1 - y0), cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    ctx.lineWidth = 1; ctx.strokeStyle = cor; ctx.setLineDash([]);
    ctx.beginPath();
    for (let t = -diag; t <= diag; t += esp) {
      const px = cx + t * (-sa), py = cy + t * ca;
      ctx.moveTo(px - ca * diag, py - sa * diag); ctx.lineTo(px + ca * diag, py + sa * diag);
    }
    ctx.stroke();
    ctx.restore();
  }

  _chamada(ctx, e, k, cor) {
    const T = (p) => this.paraTela(p);
    const a = T(e.alvo), p = T(e.posicao);
    ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(p[0], p[1]);
    const t = textoDaChamada(e, k);
    const f = T([e.posicao[0] + t.traco, e.posicao[1]]);
    ctx.lineTo(f[0], f[1]); ctx.stroke();
    this._seta(ctx, a, Math.atan2(e.alvo[1] - e.posicao[1], e.alvo[0] - e.posicao[0]), 2.5 * k * this.vp.z);
    this._texto(ctx, t.posicao, e.texto, e.altura * k, 0, t.alinhamento, 'base', cor);
  }

  _glifoSnap(ctx, snap, cor) {
    const [x, y] = this.paraTela(snap.ponto);
    ctx.strokeStyle = cor; ctx.fillStyle = cor; ctx.lineWidth = 1.5; ctx.setLineDash([]);
    ctx.beginPath();
    switch (snap.tipo) {
      case 'extremidade': ctx.rect(x - 5, y - 5, 10, 10); break;
      case 'meio': ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y + 5); ctx.lineTo(x - 6, y + 5); ctx.closePath(); break;
      case 'centro': ctx.arc(x, y, 5.5, 0, Math.PI * 2); break;
      case 'interseccao': ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x - 5, y + 5); ctx.lineTo(x + 5, y - 5); break;
      case 'perpendicular': ctx.moveTo(x - 5, y - 5); ctx.lineTo(x - 5, y + 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x - 5, y); ctx.lineTo(x, y); ctx.lineTo(x, y + 5); break;
      case 'sobre': ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); break;
      case 'grade': ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y); ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); break;
      case 'alinhamento': ctx.moveTo(x - 7, y); ctx.lineTo(x + 7, y); ctx.moveTo(x - 3, y - 3); ctx.lineTo(x - 3, y + 3); ctx.moveTo(x + 3, y - 3); ctx.lineTo(x + 3, y + 3); break;
      default: ctx.arc(x, y, 3, 0, Math.PI * 2);
    }
    ctx.stroke();
    if (snap.rotulo) {
      ctx.font = '11px "Segoe UI", Arial, sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      ctx.fillText(snap.rotulo, x + 9, y - 6);
    }
  }

  // ------------------------------------------------------------ acerto
  /** Entidade mais próxima do ponto de tela, dentro de `tol` pixels. */
  sob(px, tol = 6) {
    const p = this.paraMundo(px), t = tol * this.mmPorPixel;
    let melhor = null, dm = Infinity;
    // textos e cotas ocupam mais que seus pontos de definição: margem no papel
    const m = t + 12 * this.doc.escala;
    for (const e of this.doc.naRegiao([[p[0] - m, p[1] - m], [p[0] + m, p[1] + m]])) {
      if (!this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      let d;
      if (e.tipo === 'cota') {
        const g = Tela.geometriaCota(e, this.doc.escala);
        if (!g) d = Infinity;
        else {
          // a cota é acertada pela linha de cota e pelo número; pelos pontos medidos (que ficam EM CIMA da peça) ela
          // ainda vale, mas perde para a linha que está ali — o clique na aresta da peça cotada pegava a cota (15/10)
          const dVista = Math.min(this._distSeg(p, g.a1, g.a2), this._distTextoCota(p, e));
          const dPontos = distanciaEntidade(p, e);
          d = dVista < t ? dVista : dPontos + t * 0.5;
        }
      } else d = distanciaEntidade(p, e, this.doc.escala);
      if (d < t && d < dm) { dm = d; melhor = e; }
    }
    return melhor;
  }

  /** Distância ao número da cota (a caixa do texto, girada com ele): clicar no número pega a cota
   *  (pedido do usuário, 28/09 — só a linha e os pontos contavam). */
  _distTextoCota(p, c) {
    const t = Tela.textoCota(c, this.doc.escala);
    if (!t) return Infinity;
    const a = -t.angG * Math.PI / 180, dx = p[0] - t.pos[0], dy = p[1] - t.pos[1];
    const lx = dx * Math.cos(a) - dy * Math.sin(a), ly = dx * Math.sin(a) + dy * Math.cos(a);
    const w = Math.max(t.h, String(t.txt).length * t.h * 0.65);
    return Math.hypot(Math.max(Math.abs(lx) - w / 2, 0), Math.max(-ly, 0, ly - t.h));
  }

  _distSeg(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    if (l2 < 1e-12) return Math.hypot(p[0] - a[0], p[1] - a[1]);
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  }

  /** O traço da entidade toca o retângulo (m1 canto de cima à esquerda, m2 de baixo à
   *  direita)? A caixa envolvente não serve: a moldura de um quadro (polilinha fechada)
   *  envolve tudo e entrava em qualquer seleção por cruzamento feita dentro dela. */
  _tocaJanela(e, m1, m2, dentro) {
    let trechos = null;
    if (e.tipo === 'linha') trechos = [[e.a, e.b]];
    else if (e.tipo === 'polilinha') {
      const v = e.vertices || [];
      trechos = v.slice(1).map((q, i) => [v[i], q]);
      if (e.fechada && v.length > 2) trechos.push([v[v.length - 1], v[0]]);
    } else if (e.tipo === 'hachura') {
      trechos = [];
      for (const c of e.contornos || []) c.forEach((q, i) => trechos.push([q, c[(i + 1) % c.length]]));
    } else if (e.tipo === 'arco') trechos = segmentosDe(e);
    else if (e.tipo !== 'circulo') return true;
    const x0 = Math.min(m1[0], m2[0]), x1 = Math.max(m1[0], m2[0]), y0 = Math.min(m1[1], m2[1]), y1 = Math.max(m1[1], m2[1]);
    if (e.tipo === 'circulo') {
      // a janela toca o TRAÇO do círculo: o ponto da janela mais perto do centro fica dentro e o canto mais longe fora
      // (a janela inteira dentro do círculo, sem tocar o traço, pegava o círculo — teste de fluxo, 15/10)
      const nx = Math.max(x0, Math.min(e.centro[0], x1)), ny = Math.max(y0, Math.min(e.centro[1], y1));
      const dmin = Math.hypot(e.centro[0] - nx, e.centro[1] - ny);
      const dmax = Math.max(...[[x0, y0], [x1, y0], [x0, y1], [x1, y1]].map(q => Math.hypot(q[0] - e.centro[0], q[1] - e.centro[1])));
      return dmin <= e.raio && dmax >= e.raio;
    }
    const cruza = (a, b) => {
      if (dentro(a) || dentro(b)) return true;
      // Liang–Barsky: o segmento atravessa o retângulo?
      let t0 = 0, t1 = 1;
      const dx = b[0] - a[0], dy = b[1] - a[1];
      for (const [pp, qq] of [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dy, a[1] - y0], [dy, y1 - a[1]]]) {
        if (pp === 0) { if (qq < 0) return false; continue; }
        const r = qq / pp;
        if (pp < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; }
      }
      return true;
    };
    return trechos.some(([a, b]) => cruza(a, b));
  }

  /** Ids dentro de um retângulo de tela. Da esquerda para a direita: só as inteiramente
   *  dentro (janela); da direita para a esquerda: as que tocam (cruzamento). */
  naJanela(a, b) {
    const cruzamento = b[0] < a[0];
    const m1 = this.paraMundo([Math.min(a[0], b[0]), Math.max(a[1], b[1])]);
    const m2 = this.paraMundo([Math.max(a[0], b[0]), Math.min(a[1], b[1])]);
    const dentro = (p) => p[0] >= m1[0] && p[0] <= m2[0] && p[1] >= m1[1] && p[1] <= m2[1];
    const ids = [];
    for (const e of this.doc.naRegiao([m1, m2])) {       // só as que tocam o retângulo
      if (!this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      if (cruzamento) { if (this._tocaJanela(e, m1, m2, dentro)) ids.push(e.id); }
      // a cota entra pela linha de cota (que é o que se vê e se quer apagar), não pelos
      // pontos medidos, que ficam na peça, fora da janela
      else if (e.tipo === 'cota' ? pontosCota(e, this.doc.escala).slice(2).every(dentro) : pontosDe(e).every(dentro)) ids.push(e.id);
    }
    return ids;
  }
}
