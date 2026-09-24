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

import { subtrair, somar, escalar, normalizar, norma,
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
  perpendicular:{ rotulo: 'Perpendicular', cor: '#b07cc6', glifo: 'eixo',   prio: 6 },
  sobre_face:   { rotulo: 'Sobre face',  cor: '#2a63c8', glifo: 'losango',  prio: 7 },
  plano_base:   { rotulo: 'No plano',    cor: '#8a94a6', glifo: 'ponto',    prio: 8 },
};

// "aresta": a direção da aresta travada com Shift (paralelo), preenchida na hora
const EIXOS = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
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
  }

  // --------------------------------------------------------- estado externo

  definirAncora(p) { this.ancora = p ? p.slice(0, 3) : null; }
  limparAncora() { this.ancora = null; this.destravar(); }

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
        const eixo = t === 'eixo_x' ? 'x' : t === 'eixo_y' ? 'y' : t === 'eixo_z' ? 'z' : null;
        if (eixo) { this.travado = eixo; this.travadoPorShift = true; return true; }
        // sobre uma aresta (a do banzo inclinado): Shift trava paralelo a ela
        const ar = (this.ultimo && this.ultimo.aresta) || this.ultimaAresta;
        if (ar && this.ancora) {
          const d = normalizar(subtrair(ar[1], ar[0]));
          if (norma(d) > 0.5) {
            EIXOS.aresta = d;
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
    if (this.travado === 'aresta') return 'paralelo à aresta (solte o Shift para destravar)';
    return this.travado ? `eixo ${this.travado.toUpperCase()} travado` : '';
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
    const base = {
      ponto: [0, 0, 0], tela, entidade: null, face: -1, aresta: null,
      tipoSnap: 'plano_base', normal: [0, 0, 1], rotulo: '', cor: TIPOS.plano_base.cor,
    };

    // 1. Eixo travado: o ponto é a projeção do raio sobre a reta do eixo.
    if (this.travado && this.ancora) {
      const p = pontoNoEixo(this.ancora, EIXOS[this.travado], raio);
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
    const perto = (p) => {
      const t = this.camera.paraTela(p);
      if (t[2] > 1) return null;                       // atrás da câmera
      const d = Math.hypot(t[0] - x, t[1] - y);
      return d <= tol ? d : null;
    };

    // 2. Pontos notáveis das entidades próximas do cursor.
    const arestasPerto = [];
    let examinadas = 0;
    for (const [id, ent] of this.documento.entidades) {
      if (!this.documento.aparece(ent)) continue;
      if (++examinadas > 4000) break;
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
      const folga = tol + 2;
      if (x < sx0 - folga || x > sx1 + folga || y < sy0 - folga || y > sy1 + folga) continue;

      let algumPerto = false;
      for (let i = 0; i < pts.length; i++) {
        const t = projetados[i];
        if (t[2] > 1) continue;
        const d = Math.hypot(t[0] - x, t[1] - y);
        if (d <= tol) {
          algumPerto = true;
          cand.push({ tipo: 'extremidade', ponto: pts[i], d, id });
        }
      }
      const ars = arestasDe(ent);
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

    // 5. Sobre a face, quando o raio atinge alguma coisa.
    if (alvo) {
      cand.push({ tipo: 'sobre_face', ponto: alvo.ponto, d: tol + 1,
                  id: alvo.id, face: alvo.face, normal: alvo.normal });
    }

    // 6. Último recurso: o plano de trabalho.
    const zPlano = this.ancora ? this.ancora[2] : 0;
    cand.push({ tipo: 'plano_base', ponto: cruzarPlano(raio, zPlano), d: tol + 2 });

    cand.sort((a, b) => {
      const pa = TIPOS[a.tipo].prio, pb = TIPOS[b.tipo].prio;
      return pa !== pb ? pa - pb : a.d - b.d;
    });
    const melhor = cand[0];
    if (melhor.aresta) this.ultimaAresta = melhor.aresta;     // para o Shift travar paralelo
    return this._concluir({
      ...base,
      ponto: melhor.ponto,
      entidade: melhor.id || (alvo ? alvo.id : null),
      face: melhor.face != null ? melhor.face : (alvo ? alvo.face : -1),
      aresta: melhor.aresta || null,
      normal: melhor.normal || (alvo ? alvo.normal : [0, 0, 1]),
      tipoSnap: melhor.tipo,
    }, tela);
  }

  _concluir(r, tela) {
    const t = TIPOS[r.tipoSnap] || TIPOS.plano_base;
    r.rotulo = t.rotulo;
    r.cor = t.cor;
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

    desenharGlifo(this.svg, x, y, t.glifo, t.cor);

    const texto = doc(this.svg, 'text');
    texto.setAttribute('x', x + 15);
    texto.setAttribute('y', y - 11);
    texto.setAttribute('class', 'rotulo-snap');
    texto.setAttribute('fill', t.cor);
    texto.textContent = this.travado ? `${t.rotulo} (travado)` : t.rotulo;
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
