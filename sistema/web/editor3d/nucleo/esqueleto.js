// Esqueleto: o modelo só em linhas, para conferir a estrutura antes dos perfis.
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
    this._idDoSegmento = [];
    this._faixas = new Map();          // id -> [primeiro vértice, quantos vértices]
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
      this.cena.alvosExtras = this.objeto ? [this.objeto] : null;
      this.cena.pedirQuadro();
    });
  }

  _esconderModelo(esconder) {
    for (const c of this.cena.raiz.children) if (c !== this.cena.previa) c.visible = !esconder;
  }

  _descartar() {
    if (!this.objeto) return;
    this.cena.cena.remove(this.objeto);
    this.objeto.geometry.dispose();
    this.objeto.material.dispose();
    this.objeto = null;
  }

  _montar() {
    this._descartar();
    const pos = [];
    this._idDoSegmento = [];
    this._faixas = new Map();
    this._porPeca = new Map();
    this._grupoCor = new Map();
    for (const ent of this.documento.entidades.values()) {
      if (!this.documento.aparece(ent)) continue;
      let pts = null;
      if (ent.tipo === 'barra' && ent.inicio && ent.fim) pts = [ent.inicio, ent.fim];
      else if (ent.tipo === 'solido') pts = eixoDoSolido(ent);
      if (!pts || pts.length < 2) continue;
      const v0 = pos.length / 3;
      for (let i = 0; i < pts.length - 1; i++) {
        pos.push(...pts[i], ...pts[i + 1]);
        this._idDoSegmento.push(ent.id);
      }
      this._faixas.set(ent.id, [v0, pos.length / 3 - v0]);
      this._grupoCor.set(ent.id, grupoDoPapel(ent));
      const p = pecaDe(ent);
      if (p) {
        if (!this._porPeca.has(p)) this._porPeca.set(p, []);
        this._porPeca.get(p).push(ent.id);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(pos.length), 3));
    this.objeto = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true }));
    this.objeto.name = 'esqueleto';
    this.objeto.scale.setScalar(ESCALA);
    // o raycast de linha devolve o índice do vértice: o segmento diz de qual peça é
    this.objeto.userData.entidadeDe = (indice) => this._idDoSegmento[Math.floor(indice / 2)];
    this.cena.cena.add(this.objeto);
    this._pintar();
  }

  _pintar() {
    if (!this.objeto) return;
    const cores = this.cena.escuro ? CORES.escuro : CORES.claro;
    const col = this.objeto.geometry.getAttribute('color');
    const c = new THREE.Color();
    const sel = this.selecao.ids;
    for (const [id, [v0, n]] of this._faixas) {
      c.set(sel.has(id) ? cores.selecao : cores[this._grupoCor.get(id)] || cores.outro);
      for (let i = v0; i < v0 + n; i++) col.setXYZ(i, c.r, c.g, c.b);
    }
    col.needsUpdate = true;
    this.cena.pedirQuadro();
  }

  /** Tema trocado: as cores do outro tema. */
  repintar() { if (this.ativo) this._pintar(); }
}
