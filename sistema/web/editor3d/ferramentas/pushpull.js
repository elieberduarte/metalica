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

  iniciar(p, ev) {
    const achado = this.faceApontada(p);
    const ent = achado && achado.ent;
    const iFace = achado ? achado.iFace : -1;
    if (!ent) {
      this.dica('Aponte uma face de geometria livre (sólido). Barras e chapas são paramétricas.');
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
