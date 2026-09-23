// Seleção: raycast, clique, janela, consultas e destaque visual.
//
// Janela de seleção como no CAD: arrastando da esquerda para a direita só entra o que
// está inteiramente dentro; da direita para a esquerda entra também o que apenas toca a
// janela. A diferença é sutil e é exatamente a que o desenhista espera.

import * as THREE from 'three';
import { ESCALA, misturar } from './cena.js';
import { pontosDe, arestasDe } from './documento.js';

export const COR_SELECAO = '#1f7ae0';
export const COR_SOBRE = '#5fa8f5';

export class Selecao {
  constructor(documento, cena, camera) {
    this.documento = documento;
    this.cena = cena;
    this.camera = camera;
    this.ids = new Set();
    this.sobre = null;                 // id sob o cursor
    this._ouvintes = new Set();
    this._guardados = new Map();       // id -> materiais originais
    this.raio = new THREE.Raycaster();
    this.raio.params.Line.threshold = 0.05;
    this._v2 = new THREE.Vector2();

    // Entidades reconstruídas perdem o destaque: reaplica.
    this.documento.aoMudar(({ ids }) => {
      for (const id of (ids || [])) if (this.ids.has(id)) this._realcar(id, 'selecionado');
    });
  }

  aoMudar(fn) { this._ouvintes.add(fn); return () => this._ouvintes.delete(fn); }
  _avisar() {
    for (const fn of this._ouvintes) {
      try { fn([...this.ids], this); } catch (e) { console.error('ouvinte da seleção:', e); }
    }
  }

  get vazia() { return this.ids.size === 0; }
  get tamanho() { return this.ids.size; }
  get entidades() {
    return [...this.ids].map(i => this.documento.get(i)).filter(Boolean);
  }
  tem(id) { return this.ids.has(id); }

  // ------------------------------------------------------------- raycast

  /** Coordenadas normalizadas (-1..1) a partir de pixels do canvas. */
  _ndc(x, y) {
    this._v2.set((x / this.camera.largura) * 2 - 1, -(y / this.camera.altura) * 2 + 1);
    return this._v2;
  }

  /**
   * O que está sob o cursor.
   * @returns {{id, ponto:[x,y,z], normal:[x,y,z], face:number, distancia:number}|null}
   */
  sob(x, y) {
    this.raio.setFromCamera(this._ndc(x, y), this.camera.ativa);
    const alvos = this.cena.alvos;
    if (!alvos.length) return null;
    // Limiar das linhas em pixels de tela, convertido para milímetros: o Three.js
    // compara a distância ao segmento no espaço local do objeto, que é o do documento.
    this.raio.params.Line.threshold = 6 * this.camera.mmPorPixel();
    // Malha em lote: a peça vem do índice da face (lote.js); as demais trazem o id no objeto.
    const idDe = (h) => h.entidadeId
      || (h.object.userData.entidadeDe ? h.object.userData.entidadeDe(h.faceIndex)
                                       : h.object.userData.entidade);
    const hits = this.raio.intersectObjects(alvos, false).filter(h => {
      const e = this.documento.get(idDe(h));
      return e && this.documento.aparece(e);
    });
    // Linha desenhada sobre uma face ganha da face: é ela que o usuário está mirando.
    const naMalha = hits.find(h => h.object.isMesh);
    const naLinha = hits.find(h => h.object.isLineSegments);
    const escolhido = naLinha && (!naMalha || naLinha.distance <= naMalha.distance * 1.01 + 0.02)
      ? naLinha : naMalha;
    for (const h of escolhido ? [escolhido] : []) {
      const id = idDe(h);
      const ent = this.documento.get(id);
      const n = h.face
        ? new THREE.Vector3().copy(h.face.normal)
            .applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(h.object.matrixWorld))
            .normalize()
        : new THREE.Vector3(0, 0, 1);
      return {
        id, entidade: ent,
        ponto: [h.point.x / ESCALA, h.point.y / ESCALA, h.point.z / ESCALA],
        normal: [n.x, n.y, n.z],
        face: h.faceIndex == null ? -1 : h.faceIndex,
        distancia: h.distance,
      };
    }
    return null;
  }

  /** Raio do cursor, em milímetros: origem e direção. */
  raioEm(x, y) {
    this.raio.setFromCamera(this._ndc(x, y), this.camera.ativa);
    const o = this.raio.ray.origin, d = this.raio.ray.direction;
    return { origem: [o.x / ESCALA, o.y / ESCALA, o.z / ESCALA], direcao: [d.x, d.y, d.z] };
  }

  // ----------------------------------------------------------- operações

  /** Clique: substitui, soma (Shift) ou alterna (Ctrl). */
  clicar(id, ev = {}) {
    if (!id) {
      if (!ev.shiftKey && !ev.ctrlKey && !ev.metaKey) this.limpar();
      return;
    }
    if (ev.ctrlKey || ev.metaKey) this.alternar(id);
    else if (ev.shiftKey) this.somar([id]);
    else this.definir([id]);
  }

  definir(ids) {
    const novo = new Set((ids || []).filter(i => this.documento.get(i)));
    for (const id of this.ids) if (!novo.has(id)) this._realcar(id, null);
    for (const id of novo) if (!this.ids.has(id)) this._realcar(id, 'selecionado');
    this.ids = novo;
    this._avisar();
    this.cena.pedirQuadro();
  }

  somar(ids) {
    let mudou = false;
    for (const id of (ids || [])) {
      if (!this.documento.get(id) || this.ids.has(id)) continue;
      this.ids.add(id); this._realcar(id, 'selecionado'); mudou = true;
    }
    if (mudou) { this._avisar(); this.cena.pedirQuadro(); }
  }

  tirar(ids) {
    let mudou = false;
    for (const id of (ids || [])) {
      if (!this.ids.delete(id)) continue;
      this._realcar(id, null); mudou = true;
    }
    if (mudou) { this._avisar(); this.cena.pedirQuadro(); }
  }

  alternar(id) { this.ids.has(id) ? this.tirar([id]) : this.somar([id]); }

  /** Reaplica o destaque depois que a cena trocou materiais (tema, modo, corte). */
  reaplicar() {
    for (const id of this.ids) this._realcar(id, 'selecionado');
    if (this.sobre && !this.ids.has(this.sobre)) this._realcar(this.sobre, 'sobre');
  }

  /** Tira da seleção o que deixou de existir no documento. */
  podar() {
    const mortos = [...this.ids].filter(id => !this.documento.get(id));
    if (mortos.length) { for (const id of mortos) this.ids.delete(id); this._avisar(); }
    if (this.sobre && !this.documento.get(this.sobre)) this.sobre = null;
  }

  limpar() {
    if (!this.ids.size) return;
    for (const id of this.ids) this._realcar(id, null);
    this.ids.clear();
    this._avisar();
    this.cena.pedirQuadro();
  }

  tudo() {
    this.definir([...this.documento.entidades.keys()]
      .filter(i => this.documento.aparece(this.documento.get(i))));
  }

  inverter() {
    const novo = [];
    for (const [id, ent] of this.documento.entidades) {
      if (!this.ids.has(id) && this.documento.aparece(ent)) novo.push(id);
    }
    this.definir(novo);
  }

  // ------------------------------------------------- seleção por critério

  porTipo(tipo, somar = false) { this._porFiltro(e => e.tipo === tipo, somar); }
  porCamada(camada, somar = false) { this._porFiltro(e => e.camada === camada, somar); }
  porPerfil(perfil, somar = false) { this._porFiltro(e => e.perfil === perfil, somar); }
  porPapel(papel, somar = false) { this._porFiltro(e => e.papel === papel, somar); }
  porMaterial(mat, somar = false) { this._porFiltro(e => e.material === mat, somar); }

  /** Tudo que se parece com a entidade dada (mesmo tipo e mesmo perfil/espessura). */
  semelhantes(id, somar = false) {
    const ref = this.documento.get(id);
    if (!ref) return;
    this._porFiltro(e => e.tipo === ref.tipo &&
      (ref.tipo !== 'barra' || e.perfil === ref.perfil) &&
      (ref.tipo !== 'chapa' || e.espessura === ref.espessura), somar);
  }

  _porFiltro(fn, somar) {
    const achados = [];
    for (const [id, ent] of this.documento.entidades) {
      if (this.documento.aparece(ent) && fn(ent)) achados.push(id);
    }
    somar ? this.somar(achados) : this.definir(achados);
  }

  // --------------------------------------------------- seleção por janela

  /**
   * Seleciona pelo retângulo de tela.
   * @param a,b   cantos em pixels
   * @param modo  'dentro' (esquerda→direita) ou 'toca' (direita→esquerda)
   */
  porJanela(a, b, modo, ev = {}) {
    const r = {
      x0: Math.min(a[0], b[0]), x1: Math.max(a[0], b[0]),
      y0: Math.min(a[1], b[1]), y1: Math.max(a[1], b[1]),
    };
    const achados = [];
    const p = [0, 0];
    for (const [id, ent] of this.documento.entidades) {
      if (!this.documento.aparece(ent)) continue;
      const pts = pontosDe(ent);
      if (!pts.length) continue;
      const tela = pts.map(q => this.camera.paraTela(q));
      const dentro = tela.map(t => t[0] >= r.x0 && t[0] <= r.x1 && t[1] >= r.y0 && t[1] <= r.y1);
      if (modo === 'dentro') {
        // Atrás da câmera (z > 1) não conta como dentro.
        if (dentro.every(Boolean) && tela.every(t => t[2] < 1)) achados.push(id);
      } else {
        if (dentro.some(Boolean)) { achados.push(id); continue; }
        // Nenhum vértice dentro: talvez uma aresta atravesse a janela.
        const arestas = arestasDe(ent);
        const cruza = arestas.some(([q1, q2]) => {
          const t1 = this.camera.paraTela(q1), t2 = this.camera.paraTela(q2);
          return segmentoCruzaRetangulo(t1, t2, r);
        });
        if (cruza) achados.push(id);
      }
    }
    if (ev.ctrlKey || ev.metaKey) this.tirar(achados);
    else if (ev.shiftKey) this.somar(achados);
    else this.definir(achados);
    return achados;
  }

  // ------------------------------------------------------------- destaque

  /** Marca visualmente o que está sob o cursor. */
  realcarSobre(id) {
    if (this.sobre === id) return;
    const antigo = this.sobre;
    this.sobre = id;
    if (antigo && !this.ids.has(antigo)) this._realcar(antigo, null);
    if (antigo && this.ids.has(antigo)) this._realcar(antigo, 'selecionado');
    if (id && !this.ids.has(id)) this._realcar(id, 'sobre');
    this.cena.pedirQuadro();
  }

  _realcar(id, estado) {
    const obj = this.cena.objetos.get(id);
    const ent = this.documento.get(id);
    if (!obj || !ent) return;
    if (obj.userData.lote) { if (this.cena.lote) this.cena.lote.realcar(id, estado); return; }
    const malha = obj.getObjectByName('malha');
    const arestas = obj.getObjectByName('arestas');
    const contornoAntigo = obj.getObjectByName('contorno');
    if (contornoAntigo) {
      obj.remove(contornoAntigo);
      if (contornoAntigo.material) contornoAntigo.material.dispose();
    }

    const linhas = obj.getObjectByName('linhas');
    if (!estado) {
      obj.userData.realce = null;
      if (malha) malha.material = this.cena._materialDe(ent);
      if (arestas) arestas.material = this.cena._materialArestas(ent);
      if (linhas) linhas.material = this.cena._materialLinhas(ent);
      return;
    }

    obj.userData.realce = estado;
    const cor = estado === 'selecionado' ? COR_SELECAO : COR_SOBRE;
    if (linhas) linhas.material = materialLinha(this.cena, cor, 1, true);
    if (malha) {
      malha.material = materialRealce(this.cena, ent, cor, estado);
    }
    if (arestas) {
      arestas.material = materialLinha(this.cena, cor, 0.95, true);
      arestas.visible = true;
    }
    // Contorno que atravessa o modelo, para a seleção ser vista mesmo por trás.
    if (estado === 'selecionado' && arestas && arestas.geometry) {
      const contorno = new THREE.LineSegments(
        arestas.geometry, materialLinha(this.cena, cor, 0.32, false));
      contorno.name = 'contorno';
      contorno.renderOrder = 12;
      contorno.raycast = () => {};
      obj.add(contorno);
    }
  }
}

// -------------------------------------------------------------- apoio

function materialRealce(cena, ent, cor, estado) {
  const corte = cena.planosCorte && cena.planosCorte.length ? cena.planosCorte : null;
  const chave = `realce|${cor}|${estado}|${cena._corDe(ent)}|${cena.modo}|${corte ? 1 : 0}`;
  let m = cena.cacheMaterial.get(chave);
  if (!m) {
    const base = new THREE.Color(cena._corDe(ent));
    m = new THREE.MeshStandardMaterial({
      color: base.lerp(new THREE.Color(cor), estado === 'selecionado' ? 0.55 : 0.3),
      emissive: new THREE.Color(cor).multiplyScalar(estado === 'selecionado' ? 0.22 : 0.12),
      metalness: 0.5, roughness: 0.42, side: THREE.DoubleSide,
      transparent: cena.modo === 'raiox', opacity: cena.modo === 'raiox' ? 0.35 : 1,
      clippingPlanes: corte,
    });
    cena.cacheMaterial.set(chave, m);
  }
  return m;
}

function materialLinha(cena, cor, opacidade, comTeste) {
  const corte = cena.planosCorte && cena.planosCorte.length ? cena.planosCorte : null;
  const chave = `linha|${cor}|${opacidade}|${comTeste}|${corte ? 1 : 0}`;
  let m = cena.cacheMaterial.get(chave);
  if (!m) {
    m = new THREE.LineBasicMaterial({
      color: new THREE.Color(cor), transparent: true, opacity: opacidade,
      depthTest: comTeste, depthWrite: false, clippingPlanes: corte,
    });
    cena.cacheMaterial.set(chave, m);
  }
  return m;
}

/** O segmento de tela cruza o retângulo? (janela do tipo "toca") */
function segmentoCruzaRetangulo(a, b, r) {
  const cantos = [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]];
  for (let i = 0; i < 4; i++) {
    if (segmentosCruzam(a, b, cantos[i], cantos[(i + 1) % 4])) return true;
  }
  return false;
}

function segmentosCruzam(p1, p2, p3, p4) {
  const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
  if (Math.abs(d) < 1e-9) return false;
  const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
  const u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}

export { misturar };
