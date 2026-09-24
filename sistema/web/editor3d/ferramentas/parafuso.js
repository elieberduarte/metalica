// Parafuso: coloca um parafuso numa ligação que o projeto não detalhou.
//
// Clique numa face (a mesa do banzo, a aba do perfil de fechamento): o parafuso fica
// perpendicular a ela, com a cabeça do lado de fora e o corpo atravessando a ligação, e a
// porca na ponta. Digite o tamanho a qualquer momento ("M16x40", "16x40", ou só o
// diâmetro, "16"). O parafuso sai como os do IFC — sólido na camada Parafusos com o nome
// "BOLT (A) 12x35" e tipo IfcMechanicalFastener —, então entra na contagem dos conjuntos,
// nos furos das chapas que ele atravessa e na lista de materiais.

import { Ferramenta } from './base.js';
import * as C from './_comum.js';

//: Medida entre faces da cabeça sextavada (ISO 4017/4032) por diâmetro nominal, mm.
const ENTRE_FACES = { 8: 13, 10: 16, 12: 18, 14: 21, 16: 24, 18: 27, 20: 30, 22: 34, 24: 36 };

/** Prisma de n lados em volta do eixo `a` (unitário), da base `c` até c + a·h. */
function prisma(c, a, raio, n, h, giro = 0) {
  const u = C.normalizar(C.perpendicular(a));
  const v = C.cross(a, u);
  const base = [], topo = [];
  for (let i = 0; i < n; i++) {
    const t = giro + (2 * Math.PI * i) / n;
    const d = C.add(C.mul(u, raio * Math.cos(t)), C.mul(v, raio * Math.sin(t)));
    base.push(C.add(c, d));
    topo.push(C.add(C.add(c, d), C.mul(a, h)));
  }
  const vertices = [...base, ...topo];
  const faces = [base.map((_, i) => n - 1 - i), topo.map((_, i) => n + i)];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    faces.push([i, j, n + j, n + i]);
  }
  return { vertices, faces };
}

/** Número sem unidade: 12, 12.5 (vai no nome "BOLT (A) 12x35"). */
const num = (x) => String(Math.round(x * 10) / 10);

function juntar(...partes) {
  const vertices = [], faces = [];
  for (const p of partes) {
    const k = vertices.length;
    vertices.push(...p.vertices);
    for (const f of p.faces) faces.push(f.map(i => i + k));
  }
  return { vertices, faces };
}

/** Lê "M16x40", "16x40", "16 x 40" ou "16" → {d, L}. */
function lerTamanho(texto, atual) {
  const t = String(texto || '').toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M?(\d+(?:\.\d+)?)[X×*](\d+(?:\.\d+)?)$/);
  if (m) return { d: +m[1], L: +m[2] };
  m = t.match(/^M?(\d+(?:\.\d+)?)$/);
  if (m) return { d: +m[1], L: atual.L };
  return null;
}

export class FerramentaParafuso extends Ferramenta {
  static id = 'parafuso';
  static nome = 'Parafuso';
  static atalho = 'U';
  static grupo = 'estrutura';
  static dica = 'Clique na face onde entra o parafuso · digite o tamanho (M12x35, 16x40…)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M8 3h8l2 3-2 3H8L6 6Z"/><path d="M10 9v11M14 9v11M10 12h4M10 15h4M10 18h4"/></svg>`;

  ativar() {
    this.tamanho = this.constructor.tamanho || { d: 12, L: 35 };
    this.dica(`${FerramentaParafuso.dica} · atual M${num(this.tamanho.d)}x${num(this.tamanho.L)}`);
    this.medida(`M${this.tamanho.d}x${this.tamanho.L}`);
  }

  desativar() { this.limparPrevia(); this.medida(''); }

  onValor(texto) {
    const t = lerTamanho(texto, this.tamanho);
    if (!t || !(t.d > 0) || !(t.L > 0)) { this.dica('Tamanho: M12x35, 16x40 ou só o diâmetro (16)'); return true; }
    this.tamanho = t;
    this.constructor.tamanho = t;
    this.dica(`Parafuso M${num(t.d)}x${num(t.L)}: clique na face onde ele entra`);
    this.medida(`M${num(t.d)}x${num(t.L)}`);
    return true;
  }

  /** Geometria do parafuso com a cabeça sobre `ponto`, corpo entrando contra `normal`. */
  geometria(ponto, normal) {
    const { d, L } = this.tamanho;
    const s = ENTRE_FACES[Math.round(d)] || 1.5 * d;
    const rHex = s / Math.sqrt(3);                   // raio do sextavado pelos cantos
    const k = 0.65 * d, m = 0.85 * d;
    const n = C.normalizar(normal);
    const dentro = C.mul(n, -1);
    const cabeca = prisma(ponto, n, rHex, 6, k);
    const corpo = prisma(ponto, dentro, d / 2, 12, L);
    const porca = prisma(C.add(ponto, C.mul(dentro, Math.max(L - m - 2, m))), dentro, rHex, 6, m);
    return juntar(cabeca, corpo, porca);
  }

  normalDoPonto(p) {
    const ent = p.entidade && this.documento && this.documento.get(p.entidade);
    if (ent && ent.tipo === 'chapa') {
      const n = C.normalizar(C.cross(ent.eixo_x, ent.eixo_y));
      return p.normal && C.dot(p.normal, n) < 0 ? C.mul(n, -1) : n;
    }
    return p.normal && C.comp(p.normal) > 0.5 ? C.normalizar(p.normal) : null;
  }

  onMover(p) {
    this.limparPrevia();
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const g = this.geometria(p.ponto, n);
    this.previa(C.grupo(C.gMalha(g.vertices, g.faces, '#d62728', 0.55),
                        C.gRotulo(`M${num(this.tamanho.d)}x${num(this.tamanho.L)}`, C.add(p.ponto, C.mul(n, 30)))));
  }

  onPonto(p) {
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const g = this.geometria(p.ponto, n);
    const { d, L } = this.tamanho;
    const alvo = this.documento.get(p.entidade);
    const marcas = (alvo && alvo.atributos && alvo.atributos.marcas) || {};
    const nome = `BOLT (A) ${num(d)}x${num(L)}`;
    const ent = {
      tipo: 'solido', id: C.novoId('paraf'), nome, camada: 'Parafusos', material: 'Cor #ff0000',
      visivel: true, bloqueada: false, grupo: '',
      vertices: g.vertices, faces: g.faces, arestas_vivas: [],
      atributos: {
        tipo_ifc: 'IfcMechanicalFastener',
        marcas: { perfil: nome, ...(marcas.conjunto ? { conjunto: marcas.conjunto } : {}) },
        criado_no_editor: true,
        parafuso: { d, L, ponto: C.copiar(p.ponto), eixo: C.mul(n, -1) },
      },
    };
    this.executar(C.cmdAdicionar(ent, 'Parafuso'));
    this.dica(`${nome} colocado · clique no próximo, ou digite outro tamanho (Esc sai)`);
  }

  cancelar() { this.limparPrevia(); C.voltarParaSelecao(this.editor); }
}

export default FerramentaParafuso;
