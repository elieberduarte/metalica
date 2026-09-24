// Push/Pull: arrasta uma face na direção da normal e cria volume.
//
// Comportamento do SketchUp:
//   · face solta (sem volume atrás) → extruda, virando um prisma;
//   · face de um sólido fechado    → move a face, esticando o sólido;
//   · com Ctrl                     → sempre inicia uma face nova, mesmo no sólido;
//   · duplo clique                 → repete a última distância na face apontada.
// A distância pode ser digitada a qualquer momento.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaPushPull extends Ferramenta {
  static id = 'pushpull';
  static nome = 'Empurrar/Puxar';
  static atalho = 'P';
  static grupo = 'edicao';
  static dica = 'Clique numa face para empurrar ou puxar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3.5 12.5 8 9.9l7 4.05L10.5 16.6Z"/><path d="M3.5 12.5v3.2l7 4.05v-3.15"/><path d="M10.5 16.6 15 13.95v3.2"/><path d="M12 7.6V2.6"/><path d="M9.9 4.6 12 2.5l2.1 2.1"/></svg>`;

  ativar() {
    this.alvo = null;          // { id, iFace, base, normal, original }
    this.distancia = 0;
    this.novaFace = false;
    this.dica(FerramentaPushPull.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  // ------------------------------------------------------------- eventos

  onMover(p, ev) {
    if (!p) return;
    if (!this.alvo) { this.destacar(p); return; }
    if (ev) this.novaFace = !!ev.ctrlKey || this.novaFace;
    this.distancia = C.distanciaNaReta(this.editor, p, this.alvo.base, this.alvo.normal);
    this.desenhar();
  }

  onPonto(p, ev) {
    if (!p) return;
    if (!this.alvo) {
      if (!this.iniciar(p, ev)) return;
      this.dica('Mova para dar o volume, clique para terminar ou digite a distância');
      this.desenhar();
      return;
    }
    this.distancia = C.distanciaNaReta(this.editor, p, this.alvo.base, this.alvo.normal);
    this.aplicar(this.distancia);
  }

  onDuploClique(p, ev) {
    const d = this.constructor.ultimaDistancia;
    if (!isFinite(d) || !d) return;
    if (!this.alvo && !this.iniciar(p, ev)) return;
    this.aplicar(d);
  }

  onValor(texto) {
    if (!this.alvo) return false;
    const d = paraMilimetros(texto);
    if (!isFinite(d) || d === 0) return false;
    // sem sinal, vale o sentido em que o usuário já estava puxando; parado sobre a
    // própria face (distância ~0, só ruído numérico), vale o lado da normal
    const sinal = this.distancia < -0.5 ? -1 : 1;
    this.aplicar(d < 0 ? d : Math.abs(d) * sinal);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Control' && !ev.repeat) { this.novaFace = !this.novaFace; this.desenhar(); return true; }
    if (ev.key === 'Enter' && this.alvo && this.distancia) { this.aplicar(this.distancia); return true; }
    return false;
  }

  cancelar() {
    if (this.alvo) { this.reiniciar(); this.dica(FerramentaPushPull.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  /** Sólido e índice da face apontada (o núcleo entrega o índice do triângulo). */
  faceApontada(p) {
    if (!p || !p.entidade) return null;
    const ent = this.documento && this.documento.get(p.entidade);
    if (!ent || ent.tipo !== 'solido' || !ent.faces || !ent.faces.length) return null;
    const iFace = C.faceDoTriangulo(ent, p.face, p.ponto, p.normal);
    return iFace >= 0 ? { ent, iFace } : null;
  }

  /**
   * Chapa paramétrica: a face lateral apontada é um lado do contorno — ele anda na
   * perpendicular dele, no plano da chapa (os furos ficam onde estão); a face de cima ou de
   * baixo muda a espessura, com a face oposta parada.
   */
  iniciarChapa(p, ch) {
    const cont = ch.contorno || [];
    if (cont.length < 3) return false;
    const ex = C.normalizar(ch.eixo_x), ey = C.normalizar(ch.eixo_y);
    const n = C.normalizar(C.cross(ex, ey));
    const rel = C.sub(p.ponto, ch.origem);
    const x = C.dot(rel, ex), y = C.dot(rel, ey), z = C.dot(rel, n);
    const t = ch.espessura || 0;
    const z0 = ch.centrada ? -t / 2 : 0, z1 = z0 + t;
    // lado do contorno mais perto do ponto (no plano da chapa)
    let melhor = null;
    for (let i = 0; i < cont.length; i++) {
      const a = cont[i], b = cont[(i + 1) % cont.length];
      const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1;
      const k = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / L2));
      const d = Math.hypot(x - a[0] - k * dx, y - a[1] - k * dy);
      if (!melhor || d < melhor.d) melhor = { d, i };
    }
    const naFace = Math.min(Math.abs(z - z0), Math.abs(z - z1)) < 0.6;
    const original = { contorno: cont.map(q => [q[0], q[1]]), espessura: t, origem: C.copiar(ch.origem) };
    if (naFace && melhor.d > 0.6) {
      // face de cima (+n) ou de baixo (−n): espessura
      const cima = Math.abs(z - z1) < Math.abs(z - z0);
      this.alvo = { id: ch.id, chapa: 'espessura', cima, base: C.copiar(p.ponto), normal: cima ? n : C.mul(n, -1), n, original };
    } else {
      const a = cont[melhor.i], b = cont[(melhor.i + 1) % cont.length];
      const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      let nx = (b[1] - a[1]) / L, ny = -(b[0] - a[0]) / L;
      // para fora do contorno: o lado oposto ao centro
      const cx = cont.reduce((s_, q) => s_ + q[0], 0) / cont.length, cy = cont.reduce((s_, q) => s_ + q[1], 0) / cont.length;
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      if ((mx - cx) * nx + (my - cy) * ny < 0) { nx = -nx; ny = -ny; }
      const normal = C.normalizar(C.add(C.mul(ex, nx), C.mul(ey, ny)));
      this.alvo = { id: ch.id, chapa: 'lado', lado: melhor.i, n2: [nx, ny], base: C.copiar(p.ponto), normal, n, original };
    }
    this.novaFace = false;
    this.distancia = 0;
    C.ancorar(this.editor, p.ponto);
    return true;
  }

  /** Campos novos da chapa para a distância d (positiva = para fora). */
  resultadoChapa(d) {
    const A = this.alvo, o = A.original;
    if (A.chapa === 'lado') {
      const cont = o.contorno.map(q => [q[0], q[1]]);
      const i = A.lado, j = (i + 1) % cont.length;
      for (const k of [i, j]) cont[k] = [Math.round((cont[k][0] + A.n2[0] * d) * 100) / 100, Math.round((cont[k][1] + A.n2[1] * d) * 100) / 100];
      return { contorno: cont };
    }
    const t = Math.max(0.5, o.espessura + d);
    const dt = t - o.espessura;
    // a face oposta fica parada: centrada anda meio acréscimo; "cresce para a normal" com
    // a face de baixo puxada anda o acréscimo inteiro para trás
    let origem = C.copiar(o.origem);
    const alvo = this.documento && this.documento.get(A.id);
    if (alvo && alvo.centrada) origem = C.add(origem, C.mul(A.n, (A.cima ? 1 : -1) * dt / 2));
    else if (!A.cima) origem = C.add(origem, C.mul(A.n, -dt));
    return { espessura: Math.round(t * 100) / 100, origem };
  }

  iniciar(p, ev) {
    const entAlvo = p && p.entidade && this.documento && this.documento.get(p.entidade);
    if (entAlvo && entAlvo.tipo === 'chapa') return this.iniciarChapa(p, entAlvo);
    const achado = this.faceApontada(p);
    const ent = achado && achado.ent;
    const iFace = achado ? achado.iFace : -1;
    if (!ent) {
      this.dica('Aponte uma face de sólido ou de chapa (as barras mudam de comprimento pelo painel).');
      return false;
    }
    this.alvo = {
      id: ent.id, iFace,
      base: C.copiar(p.ponto),
      normal: C.normalDaFace(ent, iFace),
      original: { vertices: ent.vertices.map(C.copiar), faces: ent.faces.map(f => f.slice()) },
      fechado: C.faceTemVizinhas(ent, iFace),
    };
    this.novaFace = !!(ev && ev.ctrlKey);
    this.distancia = 0;
    C.ancorar(this.editor, p.ponto);
    return true;
  }

  /** Geometria resultante para uma distância, sem tocar no documento. */
  resultado(d) {
    const s = this.alvo.original;
    const usarExtrusao = this.novaFace || !this.alvo.fechado;
    return usarExtrusao ? C.extrudarFace(s, this.alvo.iFace, d)
                        : C.moverFace(s, this.alvo.iFace, d);
  }

  aplicar(d) {
    if (!this.alvo || !isFinite(d) || Math.abs(d) < 1e-6) { this.reiniciar(); return; }
    if (this.alvo.chapa) {
      this.executar(C.cmdAlterar(this.alvo.id, this.resultadoChapa(d),
        this.alvo.chapa === 'lado' ? 'Esticar chapa' : 'Espessura da chapa'));
      this.constructor.ultimaDistancia = d;
      this.reiniciar();
      this.dica(`Última distância: ${formatar(Math.abs(d))} (duplo clique repete)`);
      return;
    }
    const geo = this.resultado(d);
    this.executar(C.cmdAlterar(this.alvo.id,
      { vertices: geo.vertices, faces: geo.faces },
      this.novaFace || !this.alvo.fechado ? 'Puxar face' : 'Mover face'));
    this.constructor.ultimaDistancia = d;
    this.reiniciar();
    this.dica(`Última distância: ${formatar(Math.abs(d))} (duplo clique repete)`);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.alvo = null;
    this.distancia = 0;
    this.novaFace = false;
    this.limparPrevia();
    this.medida('');
  }

  destacar(p) {
    this.limparPrevia();
    const ch = p && p.entidade && this.documento && this.documento.get(p.entidade);
    if (ch && ch.tipo === 'chapa') { this.medida('chapa: lado ou espessura'); return; }
    const achado = this.faceApontada(p);
    if (!achado) { this.medida(''); return; }
    const { ent, iFace } = achado;
    const face = ent.faces[iFace].map(i => ent.vertices[i]);
    const g = C.grupo(C.gPoligono(face, C.CORES.face, 0.30),
                      C.gLinha(face, C.CORES.face, { fechada: true }));
    this.previa(g);
  }

  desenhar() {
    this.limparPrevia();
    if (this.alvo && this.alvo.chapa) {
      // prévia: o contorno novo nas duas faces da chapa
      const ch = this.documento.get(this.alvo.id);
      const campos = this.resultadoChapa(this.distancia || 0);
      const cont = campos.contorno || this.alvo.original.contorno;
      const t = campos.espessura != null ? campos.espessura : this.alvo.original.espessura;
      const org = campos.origem || this.alvo.original.origem;
      const ex = C.normalizar(ch.eixo_x), ey = C.normalizar(ch.eixo_y);
      const z0 = ch.centrada ? -t / 2 : 0;
      const face = (z) => cont.map(q => C.add(org, C.add(C.add(C.mul(ex, q[0]), C.mul(ey, q[1])), C.mul(this.alvo.n, z))));
      const g = C.grupo(C.gLinha(face(z0), C.CORES.face, { fechada: true }), C.gLinha(face(z0 + t), C.CORES.face, { fechada: true }),
                        C.gPoligono(face(z0 + t), C.CORES.face, 0.25));
      const ponta = C.add(this.alvo.base, C.mul(this.alvo.normal, this.distancia));
      g.add(C.gLinha([this.alvo.base, ponta], C.CORES.desenho));
      const texto = formatar(Math.abs(this.distancia)) + (this.alvo.chapa === 'espessura' ? `  ·  espessura ${formatar(t)}` : '');
      this.medida(texto);
      g.add(C.gRotulo(texto, ponta));
      this.previa(g);
      return;
    }
    const geo = this.resultado(this.distancia || 0.001);
    const g = C.gMalha(geo.vertices, geo.faces, C.CORES.face, 0.25);
    const face = this.alvo.original.faces[this.alvo.iFace].map(i => this.alvo.original.vertices[i]);
    const centro = face.reduce((a, b) => C.add(a, b), [0, 0, 0]);
    const c = C.mul(centro, 1 / face.length);
    const ponta = C.add(c, C.mul(this.alvo.normal, this.distancia));
    g.add(C.gLinha([c, ponta], C.CORES.desenho));
    const texto = formatar(Math.abs(this.distancia)) +
                  (this.novaFace ? '  ·  nova face (Ctrl)' : '');
    this.medida(texto);
    g.add(C.gRotulo(texto, ponta));
    this.previa(g);
  }
}

FerramentaPushPull.ultimaDistancia = 0;

export default FerramentaPushPull;
