// Inferência de pontos — o snap.
//
// Para a posição do mouse, devolve o ponto 3D mais provável e diz por quê. É o que faz
// um modelador parecer preciso: o desenhista mira "mais ou menos" e o programa entende
// que ele quis a extremidade, o meio, a interseção ou o eixo.
//
// Prioridade (a mesma do contrato): extremidade vence meio, que vence sobre aresta, que
// vence sobre face, que vence o plano de base. Interseção e centro entram junto dos
// pontos notáveis; a inferência de eixo entra depois das arestas e antes das faces.
// Um eixo travado à mão vence tudo.

import { subtrair, somar, escalar, normalizar, norma, baseDaBarra,
         pontosDe, arestasDe, contornoNoMundo, caixaDePontos } from './documento.js';

/** Cor e glifo de cada tipo, como no SketchUp. */
export const TIPOS = {
  extremidade:  { rotulo: 'Extremidade', cor: '#1f9d55', glifo: 'quadrado', prio: 1 },
  interseccao:  { rotulo: 'Interseção',  cor: '#b3261e', glifo: 'xis',      prio: 2 },
  meio:         { rotulo: 'Meio',        cor: '#00b0bd', glifo: 'losango',  prio: 3 },
  centro:       { rotulo: 'Centro',      cor: '#7aa7f0', glifo: 'circulo',  prio: 4 },
  sobre_aresta: { rotulo: 'Sobre aresta',cor: '#d1392e', glifo: 'quadrado', prio: 5 },
  eixo_x:       { rotulo: 'No eixo X',   cor: '#c0392b', glifo: 'eixo',     prio: 6 },
  eixo_y:       { rotulo: 'No eixo Y',   cor: '#2e8b57', glifo: 'eixo',     prio: 6 },
  eixo_z:       { rotulo: 'No eixo Z',   cor: '#2a63c8', glifo: 'eixo',     prio: 6 },
  paralelo:     { rotulo: 'Paralelo',    cor: '#b07cc6', glifo: 'eixo',     prio: 6 },
  perpendicular:{ rotulo: 'Perpendicular', cor: '#b07cc6', glifo: 'eixo',   prio: 4.5 },   // vence o "sobre aresta" no pé
  // os eixos e os níveis da obra (F11, 14/10): o cruzamento de dois eixos num nível, o ponto sobre um eixo, a altura de
  // um nível na vertical da âncora; e as direções do plano de trabalho inclinado (a água da cobertura)
  eixo_obra:    { rotulo: 'Eixo da obra', cor: '#b45309', glifo: 'xis',      prio: 2.5 },
  nivel:        { rotulo: 'Nível',       cor: '#b45309', glifo: 'quadrado', prio: 2.6 },
  sobre_eixo_obra: { rotulo: 'Sobre o eixo', cor: '#b45309', glifo: 'losango', prio: 5.5 },
  eixo_plano:   { rotulo: 'No plano de trabalho', cor: '#7c3aed', glifo: 'eixo', prio: 6 },
  // alinhado com um ponto lembrado (o mouse parou nele): o "a partir do ponto" do SketchUp — na reta do eixo a partir da
  // âncora, onde a coordenada coincide com a do ponto (vence o eixo puro); sem âncora, sobre as retas X/Y/Z do ponto
  alinhado:     { rotulo: 'Alinhado',    cor: '#b07cc6', glifo: 'eixo',     prio: 5.7 },
  alinhado_livre: { rotulo: 'Alinhado',  cor: '#b07cc6', glifo: 'eixo',     prio: 6.5 },
  // o X de um ponto lembrado e o Y de outro, na altura da âncora (o canto definido por duas referências)
  alinhado2:    { rotulo: 'Alinhado com dois pontos', cor: '#b07cc6', glifo: 'xis', prio: 5.6 },
  sobre_face:   { rotulo: 'Sobre face',  cor: '#2a63c8', glifo: 'losango',  prio: 7 },
  plano_base:   { rotulo: 'No plano',    cor: '#8a94a6', glifo: 'ponto',    prio: 8 },
};

// "aresta": a direção da aresta travada com Shift (paralelo), preenchida na hora
const EIXOS = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
const COR_EIXO = { x: '#c0392b', y: '#2e8b57', z: '#2a63c8' };
//: os pontos que ficam lembrados quando o mouse para neles
const LEMBRAVEIS = new Set(['extremidade', 'meio', 'centro', 'interseccao', 'eixo_obra']);
const NS = 'http://www.w3.org/2000/svg';

export class Inferencia {
  /**
   * @param svg  overlay <svg> sobre o canvas, onde os glifos são desenhados
   */
  constructor(documento, cena, camera, selecao, svg) {
    this.documento = documento;
    this.cena = cena;
    this.camera = camera;
    this.selecao = selecao;
    this.svg = svg || null;
    this.tolerancia = 12;           // pixels
    this.ativa = true;
    this.ancora = null;             // último ponto confirmado, base da inferência de eixo
    this.travado = null;            // 'x' | 'y' | 'z' | null
    this.travadoPorShift = false;
    this.ultimo = null;             // último ponto resolvido
    this._contornos = new Map();    // id → {chave, pontos, arestas, raioMM}: o contorno da seção da barra no mundo
    // o plano de trabalho (ferramenta Plano de trabalho): {origem, normal, ex, ey, nome} ou null = o chão (z da âncora)
    this.planoTrabalho = null;
    // os eixos e os níveis da obra (modulos/lancamento._carregarReferencia): {eixos: [{nome, a, b}], niveis: [{nome, z}]}
    this.referencias = null;
    // os pontos notáveis em que o mouse parou (até 3, o mais recente primeiro) e o que está sob o mouse agora
    this._lembrados = [];
    this._pairando = null;
    this._esferas = new Map();      // id → {c, r}: a esfera envolvente da peça, para o descarte pelo raio do cursor
    if (documento && typeof documento.aoMudar === 'function') {
      documento.aoMudar(({ ids, acao }) => {
        if (acao === 'aparencia') return;
        if (acao === 'tudo' || !ids || !ids.length) {
          this._esferas.clear();
          // o modelo novo: aquece o snap um pouco depois (dá tempo do catálogo de perfis chegar)
          if (acao === 'tudo' && typeof setTimeout === 'function') { clearTimeout(this._timerAquecer); this._timerAquecer = setTimeout(() => this.aquecer(), 1500); }
          return;
        }
        for (const i of ids) this._esferas.delete(i);
      });
    }
  }

  /** Esfera envolvente da peça (guardada; a peça que muda é esquecida pelo aviso do documento). Na barra, a seção entra
   *  pelo raio do contorno, ou 400 mm enquanto ele não foi calculado. */
  _esferaDe(id, ent) {
    let s = this._esferas.get(id);
    if (s) return s;
    const pts = pontosDe(ent);
    if (!pts.length) return null;
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (const q of pts) for (let i = 0; i < 3; i++) { if (q[i] < lo[i]) lo[i] = q[i]; if (q[i] > hi[i]) hi[i] = q[i]; }
    const c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
    let r = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
    if (ent.tipo === 'barra') { const cc = this._contornos.get(id); r += cc ? cc.raioMM : 400; }
    else if (ent.tipo === 'chapa') r += (ent.espessura || 0);
    s = { c, r };
    this._esferas.set(id, s);
    return s;
  }

  /** O contorno da seção da barra no mundo, nas duas pontas (com o recorte), e as arestas do perfil: as de cada ponta e as que
   *  correm ao longo dela. A seção é a mesma que a cena desenha (`_secaoDoPerfil`); a ponta com corte no ângulo entra como
   *  reta. `raioPx`: o tamanho da seção na tela, para a folga do descarte rápido. */
  _contornoDaBarra(b) {
    if (!this.cena || typeof this.cena._secaoDoPerfil !== 'function') return null;
    // a seção provisória (o perfil ainda não chegou do servidor) não fica guardada: a chave muda quando ele chega
    const pronto = typeof this.cena.perfil !== 'function' || !!this.cena.perfil(b.perfil);
    const chave = [b.perfil, b.rotacao || 0, b.recorte_inicio || 0, b.recorte_fim || 0, ...b.inicio, ...b.fim, pronto ? 1 : 0].join('|');
    let c = this._contornos.get(b.id);
    if (!c || c.chave !== chave) {
      const aneis = this._aneisDoPerfil(b.perfil, pronto);
      if (!aneis) return null;
      const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao);
      const o0 = somar(b.inicio, escalar(t, b.recorte_inicio || 0));
      const o1 = somar(b.fim, escalar(t, -(b.recorte_fim || 0)));
      const no = (o, [x, y]) => somar(o, somar(escalar(u, x), escalar(v, y)));
      const pontos = [], arestas = [];
      let raioMM = 0;
      for (const anel of aneis) {
        const p0 = anel.map(q => no(o0, q)), p1 = anel.map(q => no(o1, q));
        for (let i = 0; i < anel.length; i++) {
          const j = (i + 1) % anel.length;
          arestas.push([p0[i], p0[j]], [p1[i], p1[j]], [p0[i], p1[i]]);
          raioMM = Math.max(raioMM, Math.hypot(anel[i][0], anel[i][1]));
        }
        pontos.push(...p0, ...p1);
      }
      c = { chave, pontos, arestas, raioMM };
      this._contornos.set(b.id, c);
    }
    // o raio da seção em pixels pela escala da câmera (com folga de 2× para a perspectiva: o que está mais perto do que o
    // alvo da órbita aparece maior) — sem projetar nada, a conta roda para cada barra a cada movimento do mouse
    const mmpx = typeof this.camera.mmPorPixel === 'function' ? this.camera.mmPorPixel() : 0;
    const raioPx = mmpx > 1e-9 ? 2 * c.raioMM / mmpx + 2 : 40;
    return { pontos: c.pontos, arestas: c.arestas, raioPx };
  }

  /** Os anéis da seção do perfil (o contorno e os furos, no plano dela), guardados por perfil — antes cada barra refazia
   *  os pontos da forma. null quando não há seção ou ela tem pontos demais para o snap (> 80). */
  _aneisDoPerfil(perfil, pronto = true) {
    if (!this._aneis) this._aneis = new Map();
    if (pronto && this._aneis.has(perfil)) return this._aneis.get(perfil);
    let forma = null;
    try { forma = this.cena._secaoDoPerfil(perfil); } catch { forma = null; }
    let aneis = null;
    if (forma && typeof forma.extractPoints === 'function') {
      const ext = forma.extractPoints(8);
      aneis = [ext.shape, ...(ext.holes || [])].filter(a => a && a.length >= 3).map(a => {
        const r = a.map(p => [p.x, p.y]);
        const ult = r[r.length - 1];
        if (Math.hypot(ult[0] - r[0][0], ult[1] - r[0][1]) < 1e-6) r.pop();     // o anel fechado repete o primeiro
        return r;
      });
      if (!aneis.length || aneis.reduce((n, a) => n + a.length, 0) > 80) aneis = null;
    }
    if (pronto) this._aneis.set(perfil, aneis);
    return aneis;
  }

  /**
   * Aquece o snap depois de abrir o modelo: o contorno de cada barra e a esfera de cada peça, aos poucos (8 ms por vez,
   * quando o navegador está à toa) — antes o primeiro movimento do mouse fazia isso tudo de uma vez (~120 ms no PRATI CD,
   * 27 mil peças). A barra de perfil que ainda não chegou fica para quando o mouse passar nela.
   */
  aquecer() {
    const doc = this.documento;
    if (!doc || !doc.entidades) return;
    const vez = (this._vezAquecimento || 0) + 1;
    this._vezAquecimento = vez;
    const ids = [...doc.entidades.keys()];
    let i = 0;
    const agenda = (f) => (typeof requestIdleCallback === 'function' ? requestIdleCallback(f, { timeout: 400 }) : setTimeout(f, 16));
    const passo = () => {
      if (this._vezAquecimento !== vez) return;                // outro modelo abriu: este aquecimento parou
      const ate = performance.now() + 8;
      while (i < ids.length && performance.now() < ate) {
        const e = doc.get(ids[i++]);
        if (!e) continue;
        if (e.tipo === 'barra' && (typeof this.cena.perfil !== 'function' || this.cena.perfil(e.perfil))) this._contornoDaBarra(e);
        this._esferaDe(e.id, e);
      }
      if (i < ids.length) agenda(passo);
      else this.aquecido = true;
    };
    this.aquecido = false;
    agenda(passo);
  }

  // --------------------------------------------------------- estado externo

  definirAncora(p) { this.ancora = p ? p.slice(0, 3) : null; }
  limparAncora() { this.ancora = null; this.destravar(); this._lembrados = []; this._pairando = null; }

  /** Os pontos lembrados para o alinhamento: [{ponto, rotulo}] (o mais recente primeiro). */
  get lembrados() { return this._lembrados.slice(); }

  _lembrar(ponto, rotulo) {
    const l = this._lembrados.filter(q => norma(subtrair(q.ponto, ponto)) > 0.5);
    l.unshift({ ponto: ponto.slice(0, 3), rotulo });
    this._lembrados = l.slice(0, 3);
  }

  travarEixo(eixo) {
    this.travado = (eixo === this.travado) ? null : eixo;
    this.travadoPorShift = false;
    return this.travado;
  }
  destravar() { this.travado = null; this.travadoPorShift = false; }

  /** Setas travam eixo; Shift trava o que está inferido no momento. */
  onTecla(ev) {
    if (ev.type === 'keydown') {
      // Mesmo padrão do SketchUp e das ferramentas: → X (vermelho), ← Y (verde), ↑ Z.
      if (ev.key === 'ArrowUp') { this.travarEixo('z'); return true; }
      if (ev.key === 'ArrowRight') { this.travarEixo('x'); return true; }
      if (ev.key === 'ArrowLeft') { this.travarEixo('y'); return true; }
      if (ev.key === 'ArrowDown') { this.destravar(); return true; }
      if (ev.key === 'Shift' && !this.travadoPorShift) {
        const t = this.ultimo && this.ultimo.tipoSnap;
        const eixo = t === 'eixo_x' ? 'x' : t === 'eixo_y' ? 'y' : t === 'eixo_z' ? 'z'
          : (t === 'alinhado' && this.ultimo.eixoAlinhado) || null;
        if (eixo) { this.travado = eixo; this.travadoPorShift = true; return true; }
        // sobre uma aresta (a do banzo inclinado): Shift trava paralelo a ela
        const ar = (this.ultimo && this.ultimo.aresta) || this.ultimaAresta;
        if (ar && this.ancora) {
          const d = normalizar(subtrair(ar[1], ar[0]));
          if (norma(d) > 0.5) {
            // a direção fica só no objeto: gravada em EIXOS (a tabela do módulo), a "aresta" entrava no laço dos eixos
            // inferidos como 'eixo_aresta', que não tem prioridade em TIPOS — e todo movimento do mouse, em todas as
            // ferramentas, dava erro até recarregar a página (2.300 erros no registro de 13/10; revisão de 14/10)
            this.direcaoTravada = d;
            this.travado = 'aresta'; this.travadoPorShift = true;
            return true;
          }
        }
      }
    } else if (ev.type === 'keyup' && ev.key === 'Shift' && this.travadoPorShift) {
      this.destravar();
      return true;
    }
    return false;
  }

  /** Descrição do que está travado, para a barra inferior. */
  get descricaoTrava() {
    const pl = this.planoTrabalho ? `plano de trabalho: ${this.planoTrabalho.nome || 'inclinado'}` : '';
    let t = '';
    if (this.travado === 'aresta') t = 'paralelo à aresta (solte o Shift para destravar)';
    else if (this.travado) t = `eixo ${this.travado.toUpperCase()} travado`;
    return [t, pl].filter(Boolean).join(' · ');
  }

  // ------------------------------------------------------------- resolver

  /**
   * O ponto mais provável para o cursor.
   * @returns {ponto, tela, entidade, face, aresta, tipoSnap, normal, rotulo, cor}
   */
  resolver(x, y, ev = {}) {
    const tela = [x, y];
    const raio = this.selecao.raioEm(x, y);
    const alvo = this.selecao.sob(x, y);
    // a peça de verdade sob o cursor, para as ferramentas que precisam da face e não do snap (Parafuso, Furo): sem
    // repetir o raio, que custa ~10 ms num modelo grande
    this.ultimoAlvo = { x, y, alvo };
    const base = {
      ponto: [0, 0, 0], tela, entidade: null, face: -1, aresta: null,
      tipoSnap: 'plano_base', normal: [0, 0, 1], rotulo: '', cor: TIPOS.plano_base.cor,
    };

    // 1. Eixo travado: o ponto é a projeção do raio sobre a reta do eixo.
    if (this.travado && this.ancora) {
      const dir = this.travado === 'aresta' ? this.direcaoTravada : (EIXOS[this.travado] || this.direcaoTravada);
      const p = pontoNoEixo(this.ancora, dir, raio);
      const r = { ...base, ponto: p, tipoSnap: this.travado === 'aresta' ? 'paralelo' : 'eixo_' + this.travado };
      return this._concluir(r, tela);
    }

    if (!this.ativa) {
      const p = alvo ? alvo.ponto : cruzarPlano(raio, this.ancora ? this.ancora[2] : 0);
      return this._concluir({ ...base, ponto: p,
        entidade: alvo ? alvo.id : null, face: alvo ? alvo.face : -1,
        normal: alvo ? alvo.normal : [0, 0, 1],
        tipoSnap: alvo ? 'sobre_face' : 'plano_base' }, tela);
    }

    const cand = [];
    const tol = this.tolerancia;
    // o canto (extremidade) pega de um pouco mais longe que a aresta: na ponta de uma aba fina (a cantoneira de 1" do
    // agulhamento, 3 mm = 30 px de perto) a aresta vertical da ponta ganhava do canto que o usuário mirava (13/10/2026)
    const tolPonto = Math.round(tol * 1.5);
    const perto = (p) => {
      const t = this.camera.paraTela(p);
      if (t[2] > 1) return null;                       // atrás da câmera
      const d = Math.hypot(t[0] - x, t[1] - y);
      return d <= tol ? d : null;
    };

    // 2. Pontos notáveis das entidades próximas do cursor.
    const arestasPerto = [];
    let examinadas = 0;
    // primeiro a peça sob o cursor e as selecionadas: o laço para em 4000 peças, e num modelo grande (o PRATI CD, 7.800) as do
    // fim da lista — o agulhamento — nunca eram examinadas e o canto delas não pegava (13/10/2026)
    const doc = this.documento;
    const primeiras = [];
    if (alvo && alvo.id) primeiras.push(alvo.id);
    for (const i of (this.selecao && this.selecao.ids) || []) primeiras.push(i);
    const ordem = function* () {
      const vistas = new Set();
      for (const i of primeiras) {
        const e = doc.get(i);
        if (e && !vistas.has(i)) { vistas.add(i); yield [i, e]; }
      }
      for (const [i, e] of doc.entidades) if (!vistas.has(i)) yield [i, e];
    };
    // descarte pelo raio do cursor: a esfera envolvente de cada peça contra a reta do raio, com a folga da tolerância em
    // milímetros na profundidade dela. Sem ele, cada movimento do mouse projetava na tela os pontos de todas as peças —
    // ~110 ms por movimento no PRATI CD (27 mil peças), em todas as ferramentas de desenho (revisão 14/10)
    const ro = raio.origem, rd = normalizar(raio.direcao);
    const orto = this.camera.projecao === 'ortografica';
    const mmpxFixo = orto && typeof this.camera.mmPorPixel === 'function' ? this.camera.mmPorPixel() : 0;
    let kPersp = 0;
    if (!orto && typeof this.camera.mmPorPixel === 'function') kPersp = this.camera.mmPorPixel(somar(ro, escalar(rd, 1000))) / 1000;
    const folgaPx = tolPonto + 4;
    const longeDoRaio = (id, ent) => {
      if (!(mmpxFixo > 0 || kPersp > 0)) return false;
      const s = this._esferaDe(id, ent);
      if (!s) return false;
      const v = subtrair(s.c, ro);
      const t = v[0] * rd[0] + v[1] * rd[1] + v[2] * rd[2];
      if (t < -s.r) return true;                                   // atrás da câmera
      const perp = Math.sqrt(Math.max(0, v[0] * v[0] + v[1] * v[1] + v[2] * v[2] - t * t));
      const mmpx = orto ? mmpxFixo : Math.max(t, 1) * kPersp;
      return perp - s.r > folgaPx * mmpx;
    };
    for (const [id, ent] of ordem()) {
      if (!this.documento.aparece(ent)) continue;
      if (longeDoRaio(id, ent)) continue;
      const pts = pontosDe(ent);
      if (!pts.length) continue;

      // Descarte rápido: se a entidade inteira está longe do cursor na tela, pule —
      // é o que mantém a inferência barata num modelo com centenas de barras.
      let sx0 = Infinity, sy0 = Infinity, sx1 = -Infinity, sy1 = -Infinity, visivel = false;
      const projetados = [];
      for (const p of pts) {
        const t = this.camera.paraTela(p);
        projetados.push(t);
        if (t[2] > 1) continue;
        visivel = true;
        if (t[0] < sx0) sx0 = t[0];
        if (t[0] > sx1) sx1 = t[0];
        if (t[1] < sy0) sy0 = t[1];
        if (t[1] > sy1) sy1 = t[1];
      }
      if (!visivel) continue;
      // a barra: o eixo sozinho não diz onde está a peça — a folga cresce com o tamanho da seção na tela, e os cantos e
      // as arestas do perfil (nas duas pontas e ao longo dela) entram no snap: o canto do L, a aba do U (13/10/2026,
      // "não consigo selecionar a aresta do perfil para movimentar")
      const contorno = ent.tipo === 'barra' ? this._contornoDaBarra(ent) : null;
      const folga = tolPonto + 2 + (contorno ? contorno.raioPx : 0);
      if (x < sx0 - folga || x > sx1 + folga || y < sy0 - folga || y > sy1 + folga) continue;
      // o limite conta só as peças perto do cursor (antes contava todas, e as do fim da lista de um modelo grande nunca
      // eram examinadas)
      if (++examinadas > 400) break;
      if (contorno) {
        for (const p of contorno.pontos) { pts.push(p); projetados.push(this.camera.paraTela(p)); }
      }

      let algumPerto = false;
      for (let i = 0; i < pts.length; i++) {
        const t = projetados[i];
        if (t[2] > 1) continue;
        const d = Math.hypot(t[0] - x, t[1] - y);
        if (d <= tolPonto) {
          algumPerto = true;
          cand.push({ tipo: 'extremidade', ponto: pts[i], d, id });
        }
      }
      const ars = contorno ? arestasDe(ent).concat(contorno.arestas) : arestasDe(ent);
      for (const [a, b] of ars) {
        const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
        const dm = perto(m);
        if (dm !== null) { cand.push({ tipo: 'meio', ponto: m, d: dm, id }); algumPerto = true; }
        const q = maisPertoDoSegmento(a, b, raio);
        if (q) {
          const dq = perto(q);
          if (dq !== null) {
            cand.push({ tipo: 'sobre_aresta', ponto: q, d: dq, id, aresta: [a, b] });
            arestasPerto.push([a, b]);
            algumPerto = true;
          }
        }
      }
      if (algumPerto) {
        // Centro: da entidade inteira (barra: meio do eixo; chapa: centro do contorno).
        const c = centroDe(ent);
        if (c) {
          const dc = perto(c);
          if (dc !== null) cand.push({ tipo: 'centro', ponto: c, d: dc, id });
        }
      }
    }

    // 3. Interseções entre arestas próximas, avaliadas na tela.
    for (let i = 0; i < arestasPerto.length && i < 8; i++) {
      for (let j = i + 1; j < arestasPerto.length && j < 8; j++) {
        const p = interseccaoDeArestas(arestasPerto[i], arestasPerto[j]);
        if (!p) continue;
        const d = perto(p);
        if (d !== null) cand.push({ tipo: 'interseccao', ponto: p, d });
      }
    }

    // 3b. Perpendicular: o pé da perpendicular da âncora numa aresta perto do cursor (a linha que sai da ponta da barra e
    // chega em esquadro no banzo). Estava declarada em TIPOS, mas nunca era gerada (revisão 14/10, D8).
    if (this.ancora) {
      for (let i = 0; i < arestasPerto.length && i < 8; i++) {
        const [a, b] = arestasPerto[i];
        const ab = subtrair(b, a), L2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2];
        if (L2 < 1e-6) continue;
        const ap = subtrair(this.ancora, a);
        const s = (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / L2;
        if (s < -1e-6 || s > 1 + 1e-6) continue;
        const pe = somar(a, escalar(ab, s));
        if (norma(subtrair(pe, this.ancora)) < 1) continue;
        const d = perto(pe);
        if (d !== null) cand.push({ tipo: 'perpendicular', ponto: pe, d, aresta: [a, b] });
      }
    }

    // 4. Inferência de eixo a partir da âncora.
    if (this.ancora) {
      for (const [nome, dir] of Object.entries(EIXOS)) {
        const p = pontoNoEixo(this.ancora, dir, raio);
        if (!p) continue;
        // Só vale se o cursor estiver mesmo em cima da reta do eixo, na tela.
        const t = this.camera.paraTela(p);
        const d = Math.hypot(t[0] - x, t[1] - y);
        const avanco = norma(subtrair(p, this.ancora));
        if (d <= tol * 1.4 && avanco > 1e-6 && t[2] < 1) {
          cand.push({ tipo: 'eixo_' + nome, ponto: p, d });
        }
      }
    }

    // 4b. As direções do plano de trabalho inclinado, a partir da âncora (desenhar ao longo da água)
    const pl = this.planoTrabalho;
    if (this.ancora && pl && pl.ex && pl.ey) {
      for (const [nome, dir] of [['u', pl.ex], ['v', pl.ey]]) {
        const p = pontoNoEixo(this.ancora, dir, raio);
        if (!p) continue;
        const t = this.camera.paraTela(p);
        const d = Math.hypot(t[0] - x, t[1] - y);
        if (d <= tol * 1.4 && norma(subtrair(p, this.ancora)) > 1e-6 && t[2] < 1) {
          cand.push({ tipo: 'eixo_plano', ponto: p, d, rotulo: `No plano (${nome === 'u' ? 'ao longo' : 'atravessado'})`, direcao: dir });
        }
      }
    }

    // 4c. Os eixos e os níveis da obra: o cruzamento de dois eixos em cada nível (e no chão), o ponto sobre um eixo, e a
    // altura do nível na vertical da âncora
    const ref = this.referencias;
    if (ref && ((ref.eixos && ref.eixos.length) || (ref.niveis && ref.niveis.length))) {
      const zs = [...new Set([0, ...((ref.niveis || []).map(n => +n.z || 0))])];
      const nomeNivel = (z) => { const n = (ref.niveis || []).find(k => Math.abs((+k.z || 0) - z) < 0.5); return n ? n.nome : (z ? `+${(z / 1000).toFixed(2).replace('.', ',')}` : '±0,00'); };
      const eixos = ref.eixos || [];
      // os cruzamentos dos eixos (na planta) uma vez por conjunto de eixos: o mouse só projeta
      if (this._refDosNos !== ref) {
        this._refDosNos = ref;
        this._nosDaObra = [];
        for (let i = 0; i < eixos.length; i++) {
          for (let j = i + 1; j < eixos.length; j++) {
            const A = eixos[i], B = eixos[j];
            const p2 = cruzamento2d(A.a, A.b, B.a, B.b);
            if (p2) this._nosDaObra.push({ p2, nome: `${A.nome}-${B.nome}` });
          }
        }
      }
      for (const { p2, nome } of this._nosDaObra) {
        for (const z of zs) {
          const q = [p2[0], p2[1], z];
          const d = perto(q);
          if (d !== null) cand.push({ tipo: 'eixo_obra', ponto: q, d, rotulo: `${nome} · ${nomeNivel(z)}` });
        }
      }
      for (const E of eixos) {
        for (const z of zs) {
          const q = maisPertoDoSegmento([E.a[0], E.a[1], z], [E.b[0], E.b[1], z], raio);
          if (!q) continue;
          const d = perto(q);
          if (d !== null) cand.push({ tipo: 'sobre_eixo_obra', ponto: q, d: d + 1, rotulo: `Eixo ${E.nome} · ${nomeNivel(z)}` });
        }
      }
      if (this.ancora) {
        for (const z of zs) {
          if (Math.abs(z - this.ancora[2]) < 0.5) continue;
          const q = [this.ancora[0], this.ancora[1], z];
          const d = perto(q);
          if (d !== null) cand.push({ tipo: 'nivel', ponto: q, d, rotulo: `Nível ${nomeNivel(z)}` });
        }
      }
    }

    // 4d. Alinhado com um ponto lembrado: com âncora, na reta de cada eixo a partir dela, no ponto em que a coordenada
    // daquele eixo é a do ponto lembrado; sem ela (ou além disso), sobre as retas X/Y/Z que passam pelo ponto lembrado
    for (const L of this._lembrados) {
      const P = L.ponto;
      for (const [nome, dir] of Object.entries(EIXOS)) {
        if (this.ancora) {
          const s = (P[0] - this.ancora[0]) * dir[0] + (P[1] - this.ancora[1]) * dir[1] + (P[2] - this.ancora[2]) * dir[2];
          const Q = somar(this.ancora, escalar(dir, s));
          if (Math.abs(s) > 1 && norma(subtrair(Q, P)) > 1) {
            const d = perto(Q);
            if (d !== null) cand.push({ tipo: 'alinhado', ponto: Q, d, de: P, eixoAlinhado: nome,
                                        rotulo: `Alinhado com ${L.rotulo.toLowerCase()} (${nome.toUpperCase()})` });
          }
        }
        const q = pontoNoEixo(P, dir, raio);
        if (!q || norma(subtrair(q, P)) < 1) continue;
        const t = this.camera.paraTela(q);
        const d = Math.hypot(t[0] - x, t[1] - y);
        if (d <= tol && t[2] < 1) cand.push({ tipo: 'alinhado_livre', ponto: q, d, de: P, eixoAlinhado: nome,
                                              rotulo: `Na direção ${nome.toUpperCase()} de ${L.rotulo.toLowerCase()}` });
      }
    }

    // 4e. Alinhado com dois pontos lembrados: o X de um e o Y do outro, na altura da âncora (ou do chão), no plano —
    // o canto que as duas referências definem
    if (this._lembrados.length >= 2 && !(pl && pl.normal)) {
      const z = this.ancora ? this.ancora[2] : 0;
      for (const L1 of this._lembrados) {
        for (const L2 of this._lembrados) {
          if (L1 === L2) continue;
          const Q = [L1.ponto[0], L2.ponto[1], z];
          if (Math.hypot(Q[0] - L1.ponto[0], Q[1] - L1.ponto[1]) < 1 || Math.hypot(Q[0] - L2.ponto[0], Q[1] - L2.ponto[1]) < 1) continue;
          const d = perto(Q);
          if (d !== null) cand.push({ tipo: 'alinhado2', ponto: Q, d, de: [L1.ponto, L2.ponto], cores: [COR_EIXO.y, COR_EIXO.x],
                                      rotulo: `X de ${L1.rotulo.toLowerCase()} · Y de ${L2.rotulo.toLowerCase()}` });
        }
      }
    }

    // 5. Sobre a face, quando o raio atinge alguma coisa.
    if (alvo) {
      cand.push({ tipo: 'sobre_face', ponto: alvo.ponto, d: tol + 1,
                  id: alvo.id, face: alvo.face, normal: alvo.normal });
    }

    // 6. Último recurso: o plano de trabalho — o chão na altura da âncora ou, com o plano de trabalho definido, o plano
    // dele (pela âncora, paralelo a ele): o ponto solto cai na água da cobertura, não no chão
    if (pl && pl.normal) {
      const o = this.ancora || pl.origem;
      cand.push({ tipo: 'plano_base', ponto: cruzarPlanoQualquer(raio, o, pl.normal), d: tol + 2, normal: pl.normal });
    } else {
      const zPlano = this.ancora ? this.ancora[2] : 0;
      cand.push({ tipo: 'plano_base', ponto: cruzarPlano(raio, zPlano), d: tol + 2 });
    }

    // oclusão (15/10/2026, "pega um ponto de origem nada a ver atrás da placa, no pé da placa de trás"): com uma face sob o
    // cursor, o ponto notável que fica ATRÁS dela — o canto da peça escondida, o cruzamento dos eixos no chão lá atrás — não
    // vale; antes só a distância na tela contava e a extremidade escondida ganhava da face (prioridade maior). A folga
    // cresce com a distância do ponto ao cursor na tela: o canto e a aresta da própria face mirada, vista de lado, ficam
    // um pouco mais fundos que o acerto e continuam valendo.
    if (alvo && alvo.ponto) {
      const ESCONDE = new Set(['extremidade', 'meio', 'sobre_aresta', 'centro', 'interseccao', 'perpendicular',
                               'eixo_obra', 'sobre_eixo_obra', 'nivel']);
      const vh = subtrair(alvo.ponto, ro);
      const tHit = vh[0] * rd[0] + vh[1] * rd[1] + vh[2] * rd[2];
      for (let i = cand.length - 1; i >= 0; i--) {
        const c = cand[i];
        if (!ESCONDE.has(c.tipo)) continue;
        const vc = subtrair(c.ponto, ro);
        const tc = vc[0] * rd[0] + vc[1] * rd[1] + vc[2] * rd[2];
        const mmpx = orto ? mmpxFixo : Math.max(tc, 1) * kPersp;
        const folgaMM = 3 + 3 * (c.d + 2) * (mmpx > 0 ? mmpx : 1);
        if (tc > tHit + folgaMM) cand.splice(i, 1);
      }
    }

    // empate na tela (o mesmo tipo, a menos de 3 px): ganha o ponto da peça sob o cursor e, depois, o mais perto da câmera —
    // num modelo grande, a ponta de uma peça lá atrás caía no mesmo pixel do canto que o usuário mirava (13/10/2026)
    const alvoId = alvo ? alvo.id : null;
    const prof = (c) => (c._z === undefined ? (c._z = this.camera.paraTela(c.ponto)[2]) : c._z);
    cand.sort((a, b) => {
      const pa = (TIPOS[a.tipo] || TIPOS.plano_base).prio, pb = (TIPOS[b.tipo] || TIPOS.plano_base).prio;
      if (pa !== pb) return pa - pb;
      if (Math.abs(a.d - b.d) >= 3) return a.d - b.d;
      const aa = a.id && a.id === alvoId ? 0 : 1, ab = b.id && b.id === alvoId ? 0 : 1;
      if (aa !== ab) return aa - ab;
      return prof(a) - prof(b) || a.d - b.d;
    });
    const melhor = cand[0];
    // o ponto notável em que o mouse parou (250 ms ou mais) fica lembrado quando ele sai de cima — base do alinhamento
    const agora = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const notavel = LEMBRAVEIS.has(melhor.tipo);
    const h = this._pairando;
    if (h && !(notavel && norma(subtrair(h.ponto, melhor.ponto)) < 0.5)) {
      if (agora - h.desde >= 250) this._lembrar(h.ponto, h.rotulo);
      this._pairando = null;
    }
    if (notavel && !this._pairando) this._pairando = { ponto: melhor.ponto.slice(0, 3), desde: agora, rotulo: (TIPOS[melhor.tipo] || {}).rotulo || 'Ponto' };
    if (melhor.aresta) this.ultimaAresta = melhor.aresta;     // para o Shift travar paralelo
    if (melhor.direcao) this.ultimaAresta = [melhor.ponto, somar(melhor.ponto, melhor.direcao)];   // Shift trava a direção do plano
    return this._concluir({
      ...base,
      ponto: melhor.ponto,
      entidade: melhor.id || (alvo ? alvo.id : null),
      face: melhor.face != null ? melhor.face : (alvo ? alvo.face : -1),
      aresta: melhor.aresta || null,
      normal: melhor.normal || (alvo ? alvo.normal : [0, 0, 1]),
      tipoSnap: melhor.tipo,
      rotuloSnap: melhor.rotulo || '',
      ...(melhor.de ? { alinhadoCom: melhor.de, eixoAlinhado: melhor.eixoAlinhado, corSnap: COR_EIXO[melhor.eixoAlinhado],
                        coresAlinhamento: melhor.cores || null } : {}),
    }, tela);
  }

  _concluir(r, tela) {
    const t = TIPOS[r.tipoSnap] || TIPOS.plano_base;
    r.rotulo = r.rotuloSnap || t.rotulo;
    r.cor = r.corSnap || t.cor;
    r.tela = tela;
    this.ultimo = r;
    return r;
  }

  // ------------------------------------------------------------- desenho

  /** Desenha o glifo do snap e, quando houver, a linha-guia do eixo. */
  desenhar(p) {
    if (!this.svg) return;
    this.limpar();
    if (!p) return;
    const t = TIPOS[p.tipoSnap] || TIPOS.plano_base;
    // O glifo vai onde o ponto inferido está, não onde o cursor está: é o salto do
    // marcador para a extremidade que diz ao usuário que o snap pegou.
    const proj = this.camera.paraTela(p.ponto);
    const [x, y] = proj[2] <= 1 && isFinite(proj[0]) ? proj : p.tela;

    // Linha-guia do eixo, da âncora até o ponto, atravessando a tela.
    if (this.ancora && (p.tipoSnap.startsWith('eixo_') || p.tipoSnap === 'paralelo')) {
      const a = this.camera.paraTela(this.ancora);
      const l = doc(this.svg, 'line');
      l.setAttribute('x1', a[0]); l.setAttribute('y1', a[1]);
      l.setAttribute('x2', x); l.setAttribute('y2', y);
      l.setAttribute('stroke', t.cor);
      l.setAttribute('stroke-width', this.travado ? 2.4 : 1.2);
      l.setAttribute('stroke-dasharray', this.travado ? '' : '5 4');
      l.setAttribute('opacity', '.9');
      this.svg.appendChild(l);
    }

    // o alinhamento: a linha pontilhada do ponto lembrado até o ponto, na cor do eixo
    const cor = p.cor || t.cor;
    if (p.alinhadoCom) {
      // um ponto (o alinhamento num eixo) ou dois (o X de um e o Y do outro): uma linha pontilhada de cada
      const de = Array.isArray(p.alinhadoCom[0]) ? p.alinhadoCom : [p.alinhadoCom];
      de.forEach((P, k) => {
        const a = this.camera.paraTela(P);
        if (a[2] > 1) return;
        const l = doc(this.svg, 'line');
        l.setAttribute('x1', a[0]); l.setAttribute('y1', a[1]); l.setAttribute('x2', x); l.setAttribute('y2', y);
        l.setAttribute('stroke', (p.coresAlinhamento && p.coresAlinhamento[k]) || cor); l.setAttribute('stroke-width', 1.2); l.setAttribute('stroke-dasharray', '2 4');
        this.svg.appendChild(l);
      });
    }
    // os pontos lembrados: uma marquinha em cada (o usuário vê o que o snap guardou)
    for (const L of this._lembrados) {
      const a = this.camera.paraTela(L.ponto);
      if (a[2] > 1 || !isFinite(a[0])) continue;
      const c = doc(this.svg, 'circle');
      c.setAttribute('cx', a[0]); c.setAttribute('cy', a[1]); c.setAttribute('r', 3);
      c.setAttribute('fill', 'none'); c.setAttribute('stroke', '#b07cc6'); c.setAttribute('stroke-width', 1.4);
      c.setAttribute('class', 'ponto-lembrado');
      this.svg.appendChild(c);
    }

    desenharGlifo(this.svg, x, y, t.glifo, cor);

    const texto = doc(this.svg, 'text');
    texto.setAttribute('x', x + 15);
    texto.setAttribute('y', y - 11);
    texto.setAttribute('class', 'rotulo-snap');
    texto.setAttribute('fill', cor);
    const rot = p.rotulo || t.rotulo;
    texto.textContent = this.travado ? `${rot} (travado)` : rot;
    this.svg.appendChild(texto);
  }

  limpar() {
    if (!this.svg) return;
    while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
  }
}

// ------------------------------------------------------------ glifos

export function desenharGlifo(svg, x, y, glifo, cor) {
  const r = 5;
  let el;
  if (glifo === 'quadrado') {
    el = doc(svg, 'rect');
    el.setAttribute('x', x - r); el.setAttribute('y', y - r);
    el.setAttribute('width', r * 2); el.setAttribute('height', r * 2);
  } else if (glifo === 'losango') {
    el = doc(svg, 'polygon');
    el.setAttribute('points',
      `${x},${y - r - 1} ${x + r + 1},${y} ${x},${y + r + 1} ${x - r - 1},${y}`);
  } else if (glifo === 'circulo') {
    el = doc(svg, 'circle');
    el.setAttribute('cx', x); el.setAttribute('cy', y); el.setAttribute('r', r + 0.5);
  } else if (glifo === 'xis') {
    const g = doc(svg, 'g');
    for (const [dx, dy] of [[1, 1], [1, -1]]) {
      const l = doc(svg, 'line');
      l.setAttribute('x1', x - r * dx); l.setAttribute('y1', y - r * dy);
      l.setAttribute('x2', x + r * dx); l.setAttribute('y2', y + r * dy);
      l.setAttribute('stroke', cor); l.setAttribute('stroke-width', 2.4);
      g.appendChild(l);
    }
    svg.appendChild(g);
    return g;
  } else if (glifo === 'eixo') {
    el = doc(svg, 'rect');
    el.setAttribute('x', x - r + 1); el.setAttribute('y', y - r + 1);
    el.setAttribute('width', r * 2 - 2); el.setAttribute('height', r * 2 - 2);
  } else {
    el = doc(svg, 'circle');
    el.setAttribute('cx', x); el.setAttribute('cy', y); el.setAttribute('r', 2.6);
  }
  el.setAttribute('fill', glifo === 'ponto' ? cor : 'none');
  el.setAttribute('stroke', cor);
  el.setAttribute('stroke-width', 2.2);
  svg.appendChild(el);
  return el;
}

const doc = (svg, tag) => svg.ownerDocument.createElementNS(NS, tag);

// --------------------------------------------------------- geometria 3D

/** Onde o raio cruza o plano horizontal z = altura. */
/** O raio contra o plano (ponto `o`, normal `n`); longe na direção do raio quando não cruza para a frente. */
export function cruzarPlanoQualquer(raio, o, n) {
  const { origem: r0, direcao: d } = raio;
  const den = d[0] * n[0] + d[1] * n[1] + d[2] * n[2];
  if (Math.abs(den) < 1e-9) return [r0[0] + d[0] * 1e4, r0[1] + d[1] * 1e4, r0[2] + d[2] * 1e4];
  const t = ((o[0] - r0[0]) * n[0] + (o[1] - r0[1]) * n[1] + (o[2] - r0[2]) * n[2]) / den;
  const k = t < 0 ? 1e4 : t;
  return [r0[0] + d[0] * k, r0[1] + d[1] * k, r0[2] + d[2] * k];
}

/** O cruzamento das retas AB e CD na planta (x, y), ou null quando são paralelas. */
export function cruzamento2d(A, B, Cc, D) {
  const r = [B[0] - A[0], B[1] - A[1]], s = [D[0] - Cc[0], D[1] - Cc[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((Cc[0] - A[0]) * s[1] - (Cc[1] - A[1]) * s[0]) / den;
  return [A[0] + t * r[0], A[1] + t * r[1]];
}

export function cruzarPlano(raio, altura = 0) {
  const { origem: o, direcao: d } = raio;
  if (Math.abs(d[2]) < 1e-9) return [o[0] + d[0] * 1e4, o[1] + d[1] * 1e4, altura];
  const t = (altura - o[2]) / d[2];
  if (t < 0) return [o[0] + d[0] * 1e4, o[1] + d[1] * 1e4, altura];
  return [o[0] + d[0] * t, o[1] + d[1] * t, altura];
}

/** Ponto da reta (origem, direcao) mais próximo do raio do cursor. */
export function pontoNoEixo(origem, direcao, raio) {
  const u = normalizar(direcao);
  const v = raio.direcao;
  const w = subtrair(origem, raio.origem);
  const a = 1, b = u[0] * v[0] + u[1] * v[1] + u[2] * v[2], c = 1;
  const d = u[0] * w[0] + u[1] * w[1] + u[2] * w[2];
  const e = v[0] * w[0] + v[1] * w[1] + v[2] * w[2];
  const den = a * c - b * b;
  if (Math.abs(den) < 1e-9) return origem.slice();
  const s = (b * e - c * d) / den;
  return somar(origem, escalar(u, s));
}

/** Ponto do segmento [a,b] mais próximo do raio do cursor, ou null se fora dele. */
export function maisPertoDoSegmento(a, b, raio) {
  const dir = subtrair(b, a);
  const L = norma(dir);
  if (L < 1e-9) return null;
  const p = pontoNoEixo(a, dir, raio);
  const t = ((p[0] - a[0]) * dir[0] + (p[1] - a[1]) * dir[1] + (p[2] - a[2]) * dir[2]) / (L * L);
  if (t < -0.02 || t > 1.02) return null;
  const k = Math.min(1, Math.max(0, t));
  return somar(a, escalar(dir, k));
}

/** Ponto onde duas arestas do modelo se cruzam (ou quase). */
export function interseccaoDeArestas([a1, a2], [b1, b2]) {
  const u = subtrair(a2, a1), v = subtrair(b2, b1), w = subtrair(a1, b1);
  const a = u[0] * u[0] + u[1] * u[1] + u[2] * u[2];
  const b = u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
  const c = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
  const d = u[0] * w[0] + u[1] * w[1] + u[2] * w[2];
  const e = v[0] * w[0] + v[1] * w[1] + v[2] * w[2];
  const den = a * c - b * b;
  if (Math.abs(den) < 1e-9) return null;
  const s = (b * e - c * d) / den;
  const t = (a * e - b * d) / den;
  if (s < -0.02 || s > 1.02 || t < -0.02 || t > 1.02) return null;
  const p = somar(a1, escalar(u, s));
  const q = somar(b1, escalar(v, t));
  // Só conta como interseção se as duas realmente se encontram.
  return norma(subtrair(p, q)) < Math.max(2, norma(u) * 0.002) ? p : null;
}

/** Centro característico de uma entidade. */
export function centroDe(ent) {
  if (!ent) return null;
  if (ent.tipo === 'barra') {
    return [(ent.inicio[0] + ent.fim[0]) / 2, (ent.inicio[1] + ent.fim[1]) / 2,
            (ent.inicio[2] + ent.fim[2]) / 2];
  }
  const pts = ent.tipo === 'chapa' ? contornoNoMundo(ent) : (ent.vertices || []);
  const c = caixaDePontos(pts);
  return c ? [(c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2, (c[0][2] + c[1][2]) / 2] : null;
}
