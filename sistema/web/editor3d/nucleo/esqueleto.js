// Esqueleto: o modelo só em linhas, para conferir a estrutura antes dos perfis. Desenha o modelo
// analítico que o servidor monta (nucleo3d/analitico.py): nós e barras, o perfil duplo numa linha só,
// cada peça no eixo em que apoia, e as pontas que sobraram sem ligar em vermelho — cada ponto
// vermelho é um erro do modelo. Enquanto ele não chega, o eixo de cada peça como está no espaço.
//
// Cada peça vira o eixo dela — barra: do início ao fim; peça calandrada: a polilinha pelos
// centros dos anéis da varredura; outro sólido: a maior dimensão dele — numa cor por papel
// (treliça, terça, contravento, corrente, pilar, viga). Tudo num objeto só, leve mesmo no
// modelo grande. O modelo com perfis fica escondido enquanto o esqueleto está ligado, e o
// clique pega a treliça inteira (as barras de mesma peça de origem), como um bloco.

import * as THREE from 'three';
import { ESCALA } from './cena.js';

const CORES = {
  claro: {
    trelica: '#6b7686', terca: '#1f4fb8', contraventamento: '#1f9d55', corrente: '#d9822b',
    pilar: '#1c2330', viga: '#8e44ad', outro: '#9aa3ae', selecao: '#1f7ae0',
  },
  escuro: {
    trelica: '#7d8899', terca: '#6f9bff', contraventamento: '#3ecf8e', corrente: '#f0a050',
    pilar: '#f2f4f8', viga: '#c08ae0', outro: '#6b7686', selecao: '#4aa3ff',
  },
};

function grupoDoPapel(ent) {
  const p = ent.papel || '';
  if (p === 'banzo' || p === 'montante' || p === 'diagonal') return 'trelica';
  if (p === 'terça' || p === 'terca') return 'terca';
  if (p === 'contraventamento' || p === 'corrente' || p === 'pilar' || p === 'viga') return p;
  if (ent.tipo === 'solido' && ent.atributos && ent.atributos.calandrada) return 'trelica';
  return 'outro';
}

/** A peça de origem (a treliça inteira): "TESOURA 1#12". */
export function pecaDe(ent) {
  const o = ent && ent.atributos && ent.atributos.origem;
  return (o && o.peca) || null;
}

/** O eixo do sólido: os centros dos anéis quando é varredura (a tampa diz quantos pontos
 *  tem o anel); senão, a reta entre as pontas da maior dimensão. */
function eixoDoSolido(ent) {
  const v = ent.vertices || [];
  if (v.length < 2) return [];
  const k = ent.faces && ent.faces[0] ? ent.faces[0].length : 0;
  if (k >= 3 && v.length % k === 0 && v.length / k >= 2) {
    const pts = [];
    for (let i = 0; i < v.length; i += k) {
      let x = 0, y = 0, z = 0;
      for (let j = i; j < i + k; j++) { x += v[j][0]; y += v[j][1]; z += v[j][2]; }
      pts.push([x / k, y / k, z / k]);
    }
    return pts;
  }
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const p of v) for (let c = 0; c < 3; c++) { min[c] = Math.min(min[c], p[c]); max[c] = Math.max(max[c], p[c]); }
  const d = [0, 1, 2].map(c => max[c] - min[c]);
  const eixo = d.indexOf(Math.max(...d));
  const meio = [0, 1, 2].map(c => (min[c] + max[c]) / 2);
  const a = meio.slice(), b = meio.slice();
  a[eixo] = min[eixo]; b[eixo] = max[eixo];
  return [a, b];
}

export class Esqueleto {
  constructor(cena, documento, selecao) {
    this.cena = cena;
    this.documento = documento;
    this.selecao = selecao;
    this.ativo = false;
    this.objeto = null;
    this.pontos = null;
    this._segs = [];
    this._idDoSegmento = [];
    this._faixas = new Map();
    this._porPeca = new Map();         // peça de origem -> [ids]
    this._agendado = null;
    documento.aoMudar(() => { if (this.ativo) this._agendar(); });
    selecao.aoMudar(() => { if (this.ativo) this._pintar(); });
  }

  ligar(ativo) {
    this.ativo = !!ativo;
    if (this.ativo) this._montar();
    else this._descartar();
    this._esconderModelo(this.ativo);
    // o clique pega a treliça inteira só no esqueleto
    this.selecao.grupoDe = this.ativo ? (id) => this.grupoDe(id) : null;
    this.cena.alvosExtras = this.ativo && this.objeto ? [this.objeto] : null;
    this.cena.pedirQuadro();
  }

  /** As barras da mesma treliça (mesma peça de origem); a peça solta vai sozinha. */
  grupoDe(id) {
    const ent = this.documento.get(id);
    const p = pecaDe(ent);
    return p && this._porPeca.has(p) ? this._porPeca.get(p) : [id];
  }

  _agendar() {
    if (this._agendado) return;
    this._agendado = requestAnimationFrame(() => {
      this._agendado = null;
      if (!this.ativo) return;
      this._montar();
      this._esconderModelo(true);
      this.cena.pedirQuadro();
    });
  }

  _esconderModelo(esconder) {
    for (const c of this.cena.raiz.children) if (c !== this.cena.previa) c.visible = !esconder;
  }

  _descartar() {
    for (const o of [this.objeto, this.pontos]) {
      if (!o) continue;
      this.cena.cena.remove(o);
      o.geometry.dispose();
      o.material.dispose();
    }
    this.objeto = null;
    this.pontos = null;
  }

  /**
   * Primeiro o eixo de cada peça, na hora (o modelo físico); em seguida o servidor devolve o
   * modelo analítico — perfil duplo numa linha só, pontas juntadas no nó, cada peça no eixo em
   * que apoia — e ele toma o lugar, com as pontas que sobraram sem ligar em vermelho.
   */
  _montar() {
    this._porPeca = new Map();
    for (const ent of this.documento.entidades.values()) {
      const p = pecaDe(ent);
      if (!p) continue;
      if (!this._porPeca.has(p)) this._porPeca.set(p, []);
      this._porPeca.get(p).push(ent.id);
    }
    const pos = [];
    const segs = [];
    for (const ent of this.documento.entidades.values()) {
      if (!this.documento.aparece(ent)) continue;
      let pts = null;
      if (ent.tipo === 'barra' && ent.inicio && ent.fim) pts = [ent.inicio, ent.fim];
      else if (ent.tipo === 'solido') pts = eixoDoSolido(ent);
      if (!pts || pts.length < 2) continue;
      for (let i = 0; i < pts.length - 1; i++) {
        pos.push(...pts[i], ...pts[i + 1]);
        segs.push({ ids: [ent.id], cor: grupoDoPapel(ent) });
      }
    }
    this.analitico = null;
    this._desenhar(pos, segs, []);
    this._pedirAnalitico();
  }

  async _pedirAnalitico() {
    const api = this.cena.api;
    if (!api || typeof api.analitico !== 'function') return;
    const pedido = (this._pedido = (this._pedido || 0) + 1);
    let r;
    try {
      r = await api.analitico(this.documento.paraJSON());
    } catch (e) {
      if (this.aoAnalitico) this.aoAnalitico(null, e);
      return;
    }
    if (!this.ativo || pedido !== this._pedido || !r || !r.nos) return;
    const pos = [];
    const segs = [];
    for (const b of r.barras) {
      pos.push(...r.nos[b.a], ...r.nos[b.b]);
      segs.push({ ids: b.ids, cor: grupoDoPapel({ papel: b.papel, tipo: 'barra' }), duplo: b.duplo });
    }
    this.analitico = r;
    this._desenhar(pos, segs, r.soltas.map(s => r.nos[s.no]));
    this._esconderModelo(true);
    if (this.aoAnalitico) this.aoAnalitico(r.resumo);
  }

  _desenhar(pos, segs, soltas) {
    this._descartar();
    this._segs = segs;
    this._idDoSegmento = segs.map(s => s.ids[0]);
    this._faixas = new Map();          // id -> [primeiro vértice, 2] (o primeiro trecho dela)
    segs.forEach((s, k) => { for (const id of s.ids) if (!this._faixas.has(id)) this._faixas.set(id, [2 * k, 2]); });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(pos.length), 3));
    this.objeto = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true }));
    this.objeto.name = 'esqueleto';
    this.objeto.scale.setScalar(ESCALA);
    // o raycast de linha devolve o índice do vértice: o segmento diz de qual peça é
    this.objeto.userData.entidadeDe = (indice) => this._idDoSegmento[Math.floor(indice / 2)];
    this.cena.cena.add(this.objeto);
    if (soltas.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(soltas.flat(), 3));
      this.pontos = new THREE.Points(g, new THREE.PointsMaterial({
        color: 0xe5484d, size: 9, sizeAttenuation: false, depthTest: false }));
      this.pontos.name = 'esqueleto-soltas';
      this.pontos.renderOrder = 20;
      this.pontos.scale.setScalar(ESCALA);
      this.cena.cena.add(this.pontos);
    }
    this.cena.alvosExtras = this.ativo ? [this.objeto] : null;
    this._pintar();
  }

  _pintar() {
    if (!this.objeto) return;
    const cores = this.cena.escuro ? CORES.escuro : CORES.claro;
    const col = this.objeto.geometry.getAttribute('color');
    const c = new THREE.Color();
    const sel = this.selecao.ids;
    this._segs.forEach((s, k) => {
      c.set(s.ids.some(id => sel.has(id)) ? cores.selecao : cores[s.cor] || cores.outro);
      col.setXYZ(2 * k, c.r, c.g, c.b);
      col.setXYZ(2 * k + 1, c.r, c.g, c.b);
    });
    col.needsUpdate = true;
    this.cena.pedirQuadro();
  }

  /** Tema trocado: as cores do outro tema. */
  repintar() { if (this.ativo) this._pintar(); }
}
