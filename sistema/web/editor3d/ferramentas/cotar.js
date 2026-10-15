// Cota permanente entre dois pontos.
//
// Escolha da representação: a cota vira um `Solido` com `atributos.tipo = 'cota'`,
// na camada "Referência". Os vértices e as `arestas_vivas` desenham as linhas de
// chamada, a linha de cota e os traços a 45° das extremidades, de modo que a cota
// aparece na cena mesmo que o núcleo só saiba desenhar sólidos — nenhum tipo novo
// de entidade precisa existir no documento nem no IFC. Os dados originais ficam em
// `atributos.cota = { a, b, deslocamento, texto, normal }`, e é por eles que a cota
// deve ser regerada se as pontas mudarem.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
import { refDoPonto, geometriaDaCota } from '../modulos/cotas.js';

export class FerramentaCotar extends Ferramenta {
  static id = 'cotar';
  static nome = 'Cotar';
  static atalho = 'D';
  static grupo = 'medicao';
  static dica = 'Clique na primeira extremidade da cota';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 15h16"/><path d="M4 11.5v7M20 11.5v7"/><path d="M6.4 12.6 4 15l2.4 2.4M17.6 12.6 20 15l-2.4 2.4"/><path d="M4 8.5h16" stroke-dasharray="2 2"/></svg>`;

  ativar() {
    this.a = null; this.b = null; this.atual = null;
    this.plano = null;
    this.desloc = 0;
    this.dica(FerramentaCotar.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  onMover(p) {
    if (!p) return;
    this.atual = C.copiar(p.ponto);
    if (this.a && this.b) this.desloc = this.deslocamentoDe(this.pontoNoPlanoDaCota(p));
    this.desenhar();
  }

  onPonto(p) {
    if (!p) return;
    if (!this.a) {
      this.a = C.copiar(p.ponto);
      // a ponta presa à peça que o snap pegou: a cota acompanha quando ela mudar (F20, modulos/cotas.js)
      this.refA = this._ref(p);
      C.ancorar(this.editor, this.a);
      this.planoBase = C.planoDoPonto(this.editor, p);
      this.dica('Clique na segunda extremidade');
      this.desenhar();
      return;
    }
    if (!this.b) {
      if (C.iguais(this.a, p.ponto, 1e-6)) return;
      this.b = C.copiar(p.ponto);
      this.refB = this._ref(p);
      this.montarPlano();
      this.dica('Afaste a linha de cota e clique, ou digite o afastamento');
      this.desenhar();
      return;
    }
    this.criar(this.deslocamentoDe(this.pontoNoPlanoDaCota(p)));
  }

  onValor(texto) {
    if (!this.a || !this.b) return false;
    const v = paraMilimetros(texto);
    if (!isFinite(v)) return false;
    this.criar(v || this.desloc || 0);
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.a && this.b) { this.criar(this.desloc); return true; }
    return false;
  }

  cancelar() {
    if (this.b) { this.b = null; this.dica('Clique na segunda extremidade'); this.desenhar(); return; }
    if (this.a) { this.reiniciar(); this.dica(FerramentaCotar.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  _ref(p) {
    const ent = p && p.entidade && this.documento && this.documento.get(p.entidade);
    return ent && p.tipoSnap !== 'plano_base' ? refDoPonto(ent, p.ponto) : null;
  }

  /** Direção de afastamento: perpendicular à cota, dentro do plano da face. */
  montarPlano() {
    const dir = C.normalizar(C.sub(this.b, this.a));
    let n = (this.planoBase && this.planoBase.normal) || [0, 0, 1];
    if (Math.abs(C.dot(n, dir)) > 0.99) n = C.perpendicular(dir);
    this.normal = C.normalizar(C.sub(n, C.mul(dir, C.dot(n, dir))));
    this.lado = C.normalizar(C.cross(this.normal, dir));
    this.dir = dir;
  }

  pontoNoPlanoDaCota(p) {
    return C.noPlano(this.editor, p, C.planoDe(this.a, this.normal));
  }

  deslocamentoDe(ponto) {
    return C.dot(C.sub(ponto, this.a), this.lado);
  }

  /** Vértices e arestas do desenho da cota. */
  geometria(desloc) {
    return geometriaDaCota(this.a, this.b, desloc, this.lado);
  }

  criar(desloc) {
    if (!this.a || !this.b) return;
    const g = this.geometria(desloc);
    const texto = formatar(C.dist(this.a, this.b));
    const ent = {
      tipo: 'solido', id: C.novoId('cota'), nome: texto, camada: 'Referência',
      material: '', visivel: true, bloqueada: false, grupo: '',
      vertices: g.vertices, faces: [], arestas_vivas: g.arestas,
      atributos: {
        tipo: 'cota',
        exportar: false,                // anotação: não é peça (fica fora do IFC e das listas)
        cota: { a: C.copiar(this.a), b: C.copiar(this.b), deslocamento: desloc,
                texto, normal: C.copiar(this.normal), lado: C.copiar(this.lado),
                refs: [this.refA || null, this.refB || null] },
      },
    };
    this.executar(C.cmdAdicionar(ent, 'Cotar'));
    this.reiniciar();
    this.dica(FerramentaCotar.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.a = null; this.b = null; this.atual = null; this.desloc = 0; this.refA = null; this.refB = null;
    this.limparPrevia();
    this.medida('');
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.a) g.add(C.gPonto(this.a, C.CORES.cota));
    if (this.a && !this.b) {
      if (this.atual) {
        g.add(C.gLinha([this.a, this.atual], C.CORES.cota, { tracejada: true }));
        this.medida(formatar(C.dist(this.a, this.atual)));
      }
    } else if (this.a && this.b) {
      g.add(C.gPonto(this.b, C.CORES.cota));
      const geo = this.geometria(this.desloc);
      for (const [i, j] of geo.arestas) g.add(C.gLinha([geo.vertices[i], geo.vertices[j]], C.CORES.cota));
      const texto = formatar(C.dist(this.a, this.b));
      this.medida(`${texto}  ·  afastamento ${formatar(Math.abs(this.desloc))}`);
      g.add(C.gRotulo(texto, C.meio(geo.vertices[2], geo.vertices[3]), '#b8860b'));
    } else if (this.atual) {
      g.add(C.gPonto(this.atual, C.CORES.cota));
    }
    this.previa(g);
  }
}

export default FerramentaCotar;
