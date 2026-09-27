// Métodos do editor 3D: o elemento treliçado como bloco.
//
// Toda peça que saiu de uma elevação (tesoura, transição, painel, treliça, COMP — as barras com a
// mesma peça de origem, "TESOURA 16#12") é um bloco: o clique pega o bloco inteiro e Alt+clique
// pega uma barra só (a mesma convenção do Desenho 2D). Com um bloco selecionado, o painel diz de
// onde até onde ele vai e no que cada ponta encosta — pilar, outra treliça, viga —, com essas peças
// em destaque e o resto apagado; clicar no nome de uma vizinha passa a seleção para ela.

import { el } from '../editor.js';
import { pecaDe, eixoDoSolido } from '../nucleo/esqueleto.js';

const PERTO = 350;           // mm: a ponta encosta na peça a até isso (meia altura dos perfis + folga)

function dist(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }

function distSeg(p, a, b) {
  const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const L2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
  let t = L2 > 1e-9 ? ((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1] + (p[2] - a[2]) * d[2]) / L2 : 0;
  t = Math.max(0, Math.min(1, t));
  return dist(p, [a[0] + d[0] * t, a[1] + d[1] * t, a[2] + d[2] * t]);
}

/** Os segmentos do eixo de uma peça: a barra, ou a polilinha do sólido. */
function segmentosDe(ent) {
  if (ent.tipo === 'barra' && ent.inicio && ent.fim) return [[ent.inicio, ent.fim]];
  if (ent.tipo === 'solido') {
    const pts = eixoDoSolido(ent);
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) out.push([pts[i], pts[i + 1]]);
    return out;
  }
  return [];
}

function nomeDaPeca(ent) {
  const p = pecaDe(ent);
  const o = (ent.atributos && ent.atributos.origem) || {};
  if (p) return o.planta || p.split('#')[0];          // o nome como está no projeto (com acento)
  if (ent.papel === 'pilar') return `pilar ${(o.locacao || ent.perfil || '').split('(')[0]}`;
  if (ent.papel === 'viga') return `viga ${o.planta || ent.perfil || ''}`.trim();
  return `${ent.papel || ent.tipo} ${ent.perfil || ent.nome || ''}`.trim();
}

const m = (mm) => (mm / 1000).toFixed(2).replace('.', ',');

export class MetodosBloco {
  /** As barras do mesmo bloco (mesma peça de origem); a peça solta vai sozinha. */
  blocoDe(id) {
    const ent = this.documento.get(id);
    const p = pecaDe(ent);
    if (!p) return [id];
    if (!this._indiceBlocos || this._indiceBlocosVersao !== this._versaoDoc) {
      this._indiceBlocos = new Map();
      for (const e of this.documento.entidades.values()) {
        const q = pecaDe(e);
        if (!q) continue;
        if (!this._indiceBlocos.has(q)) this._indiceBlocos.set(q, []);
        this._indiceBlocos.get(q).push(e.id);
      }
      this._indiceBlocosVersao = this._versaoDoc;
    }
    return this._indiceBlocos.get(p) || [id];
  }

  _ligarBlocos() {
    this._versaoDoc = 0;
    this.documento.aoMudar(() => { this._versaoDoc++; });
    this.selecao.grupoDe = (id) => this.blocoDe(id);
    this.selecao.aoMudar((ids) => this._aoMudarSelecaoBloco(ids));
  }

  _aoMudarSelecaoBloco(ids) {
    if (this._pintandoBloco) return;
    const pecas = new Set(ids.map(i => pecaDe(this.documento.get(i))));
    if (ids.length > 1 && pecas.size === 1 && !pecas.has(null) && !pecas.has(undefined)) {
      this._mostrarBloco([...pecas][0], ids);
    } else {
      this._fecharBloco(false);
    }
  }

  _fecharBloco(limparDestaque = true) {
    if (this._painelBloco) { this._painelBloco.remove(); this._painelBloco = null; }
    if (limparDestaque && this._destaqueBloco) { this.cena.destacar(null); this._destaqueBloco = false; }
  }

  /** A análise do bloco: comprimento, de onde até onde, e no que cada ponta encosta. */
  analisarBloco(ids) {
    const doc = this.documento;
    const meus = new Set(ids);
    const ents = ids.map(i => doc.get(i)).filter(Boolean);
    const banzo = ents.filter(e => e.papel === 'banzo' || e.tipo === 'solido');
    const pts = [];
    for (const e of (banzo.length ? banzo : ents)) for (const [a, b] of segmentosDe(e)) pts.push(a, b);
    if (pts.length < 2) return null;
    // as duas pontas: o par de pontos mais longe em planta
    let e1 = pts[0], e2 = pts[1], dmax = -1;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
        if (d > dmax) { dmax = d; e1 = pts[i]; e2 = pts[j]; }
      }
    }
    const zs = ents.flatMap(e => segmentosDe(e).flatMap(([a, b]) => [a[2], b[2]]));
    const outras = [...doc.entidades.values()].filter(e => !meus.has(e.id) && doc.aparece(e)
      && !['terça', 'terca', 'corrente', 'contraventamento'].includes(e.papel));
    const pontas = [e1, e2].map(ext => {
      // os pontos do bloco naquela ponta (os dois banzos, a alma da ponta)
      const aqui = pts.filter(q => Math.hypot(q[0] - ext[0], q[1] - ext[1]) < 300);
      const viz = new Map();
      for (const o of outras) {
        const segs = segmentosDe(o);
        if (!segs.length) continue;
        let dmin = Infinity;
        for (const q of aqui) for (const [a, b] of segs) dmin = Math.min(dmin, distSeg(q, a, b));
        if (dmin < PERTO) {
          const nome = nomeDaPeca(o);
          const chave = pecaDe(o) || nome;       // o perfil duplo (viga 2Ue) é uma peça só
          if (!viz.has(chave)) viz.set(chave, { nome, id: o.id, papel: o.papel, dist: dmin });
        }
      }
      return { ponto: ext, vizinhas: [...viz.values()].sort((a, b) => a.dist - b.dist) };
    });
    return {
      comprimento: dmax, altura: Math.max(...zs) - Math.min(...zs), barras: ents.length,
      zmin: Math.min(...zs), zmax: Math.max(...zs), pontas,
    };
  }

  /** O eixo mais perto de um ponto, em cada direção: "eixo 4 / B". */
  _eixosPerto(p) {
    const eixos = this._eixosRef || [];
    let melhorN = null, melhorL = null;
    for (const e of eixos) {
      const d = distSeg([p[0], p[1], 0], [e.a[0], e.a[1], 0], [e.b[0], e.b[1], 0]);
      const vertical = Math.abs(e.b[0] - e.a[0]) < Math.abs(e.b[1] - e.a[1]);
      if (vertical && (!melhorN || d < melhorN.d)) melhorN = { nome: e.nome, d };
      if (!vertical && (!melhorL || d < melhorL.d)) melhorL = { nome: e.nome, d };
    }
    const partes = [melhorN, melhorL].filter(x => x && x.d < 3000).map(x => x.nome);
    return partes.length ? `eixos ${partes.join(' / ')}` : '';
  }

  _mostrarBloco(peca, ids) {
    const r = this.analisarBloco(ids);
    this._fecharBloco(false);
    if (!r) return;
    const ent0 = this.documento.get(ids[0]);
    const nome = (ent0 && nomeDaPeca(ent0)) || peca.split('#')[0];
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    corpo.append(el('p', { texto: `${ids.length} barras · ${m(r.comprimento)} m de comprimento · altura ${m(r.altura)} m (de ${m(r.zmin)} a ${m(r.zmax)} m)` }));
    const destacar = new Set(ids);
    r.pontas.forEach((pt, k) => {
      const onde = `Ponta ${k + 1} — (${m(pt.ponto[0])}; ${m(pt.ponto[1])}; ${m(pt.ponto[2])}) m ${this._eixosPerto(pt.ponto)}`.trim();
      corpo.append(el('p', { class: 'bloco-ponta', texto: onde }));
      const ul = el('ul');
      if (!pt.vizinhas.length) ul.append(el('li', { class: 'solta', texto: 'nada encosta nessa ponta — sem apoio' }));
      for (const v of pt.vizinhas.slice(0, 8)) {
        destacar.add(v.id);
        for (const i of this.blocoDe(v.id)) destacar.add(i);
        ul.append(el('li', {
          texto: `${v.nome}${v.papel && !v.nome.startsWith(v.papel) ? ` (${v.papel})` : ''}`,
          title: 'Selecionar esta peça',
          onclick: () => { this.selecao.definir(this.blocoDe(v.id)); this.camera.zoomSelecao(this.blocoDe(v.id)); },
        }));
      }
      corpo.append(ul);
    });
    corpo.append(el('p', { class: 'explica', texto: 'Alt+clique pega uma barra só. Esc limpa a seleção.' }));
    this._painelBloco = el('div', { class: 'painel-apoios painel-bloco' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: `Bloco ${nome}` }),
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharBloco(true) })),
      corpo);
    (this.el.palco || document.body).append(this._painelBloco);
    // o bloco e o que ele toca em destaque; o resto apagado
    this._pintandoBloco = true;
    try { this.cena.destacar([...destacar]); } finally { this._pintandoBloco = false; }
    this._destaqueBloco = true;
    this._destaqueAtivo = true;
    this.dica(`${nome}: ${ids.length} barras. As peças em que ele encosta ficam em destaque.`);
  }
}
