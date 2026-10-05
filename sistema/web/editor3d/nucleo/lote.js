// Desenho em lote dos sólidos de um modelo grande.
//
// Um IFC de fábrica traz milhares de sólidos. Um objeto Three.js por peça — malha mais
// arestas — são duas chamadas de desenho por peça, e é o número de chamadas, não o de
// triângulos, que trava a placa de vídeo: no IFC de 5 mil peças eram 7 mil chamadas por
// quadro. Aqui os sólidos entram em poucos **blocos**: uma malha e um conjunto de
// arestas por bloco, com a cor de cada peça num atributo de vértice e a visibilidade no
// índice (peça escondida sai do índice; a geometria fica). O raycast continua dando a
// peça: o índice de face leva ao vértice, e o vértice à peça, por busca binária.
//
// A cena continua dona das decisões (cor, modo, corte, sombra, destaque): este módulo
// só as aplica aos blocos. Quem não é sólido com faces (barra, chapa, cota, linha) segue
// no caminho de um objeto por peça, e o modelo pequeno nem passa por aqui.
//
// Unidades: as posições entram em milímetros (as do documento) e a escala mm → m fica
// na raiz da cena, como nos demais objetos.
//
// Cópias: sólidos que são a mesma malha só movida ou girada (os parafusos de um IFC, um
// quarto dos triângulos do Bella Casa) vão para um InstancedMesh por forma — a malha sobe
// uma vez para a placa e cada cópia é uma matriz e uma cor. As arestas delas continuam no
// bloco, como as das outras peças; a escolha pelo cursor, a cor, esconder e o corte valem
// igual. Espelhada ou que não bate vértice a vértice, a peça fica no bloco.

import * as THREE from 'three';
import { misturar, COR_DESTAQUE, COR_DESTAQUE_ARESTA } from './cena.js';
import { arestasDoSolido } from './arestas.js';

/** Acima de tantas entidades os sólidos são desenhados em lote. */
export const LIMITE_LOTE = 1500;

/** Vértices por bloco: ~12 blocos no IFC de 5 mil peças. Blocos menores fazem o raycast
 *  e a atualização de cor mais baratos; blocos maiores, menos chamadas de desenho. */
const VERTS_POR_BLOCO = 50000;

/** Contornos "através do modelo" da seleção: além disto, só a cor marca a peça. */
const MAX_CONTORNOS = 400;

/** Forma repetida só vira cópias acima de tantos triângulos economizados: grupo pequeno
 *  fica no bloco, para não trocar memória por chamadas de desenho. */
const MIN_TRI_COPIAS = 2000;
/** Distância máxima (mm) entre um vértice da cópia e o da referência levada até ela. */
const TOL_COPIA = 0.05;

const COR_SELECAO = '#1f7ae0';
const COR_SOBRE = '#5fa8f5';

const _cor = new THREE.Color();
// temporários do raycast (um por módulo: a escolha roda a cada movimento do mouse)
const _inv = new THREE.Matrix4();
const _raio = new THREE.Ray();
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3();
const _p = new THREE.Vector3();
const _tri = new THREE.Triangle();
const _raioLote = new THREE.Ray();
const _zero = new THREE.Matrix4().makeScale(0, 0, 0);

// ---- cópias: três vértices fixos (pelo índice: as cópias de uma forma do IFC saem com os
// vértices na mesma ordem) dão o sistema de eixos de cada peça

function _ancoras(vs) {
  const p0 = vs[0];
  let i1 = -1, d1 = 0;
  for (let i = 1; i < vs.length; i++) {
    const v = vs[i], d = (v[0] - p0[0]) ** 2 + (v[1] - p0[1]) ** 2 + (v[2] - p0[2]) ** 2;
    if (d > d1) { d1 = d; i1 = i; }
  }
  if (i1 < 0 || d1 < 1e-6) return null;
  const ux = vs[i1][0] - p0[0], uy = vs[i1][1] - p0[1], uz = vs[i1][2] - p0[2];
  let i2 = -1, c2 = 0;
  for (let i = 1; i < vs.length; i++) {
    const wx = vs[i][0] - p0[0], wy = vs[i][1] - p0[1], wz = vs[i][2] - p0[2];
    const c = (uy * wz - uz * wy) ** 2 + (uz * wx - ux * wz) ** 2 + (ux * wy - uy * wx) ** 2;
    if (c > c2) { c2 = c; i2 = i; }
  }
  if (i2 < 0 || c2 < 1e-6 * d1) return null;
  return [i1, i2];
}

function _quadro(vs, ancoras) {
  const p0 = vs[0], a = vs[ancoras[0]], b = vs[ancoras[1]];
  const x = new THREE.Vector3(a[0] - p0[0], a[1] - p0[1], a[2] - p0[2]);
  const w = new THREE.Vector3(b[0] - p0[0], b[1] - p0[1], b[2] - p0[2]);
  if (x.lengthSq() < 1e-12) return null;
  x.normalize();
  const z = new THREE.Vector3().crossVectors(x, w);
  if (z.lengthSq() < 1e-12) return null;
  z.normalize();
  const y = new THREE.Vector3().crossVectors(z, x);
  return new THREE.Matrix4().makeBasis(x, y, z).setPosition(p0[0], p0[1], p0[2]);
}

/** Todos os vértices da referência, levados por `m`, caem nos da peça? */
function _bate(vsRef, vs, m) {
  const e = m.elements, tol = TOL_COPIA * TOL_COPIA;
  for (let i = 0; i < vs.length; i++) {
    const p = vsRef[i], q = vs[i];
    const x = e[0] * p[0] + e[4] * p[1] + e[8] * p[2] + e[12] - q[0];
    const y = e[1] * p[0] + e[5] * p[1] + e[9] * p[2] + e[13] - q[1];
    const z = e[2] * p[0] + e[6] * p[1] + e[10] * p[2] + e[14] - q[2];
    if (x * x + y * y + z * z > tol) return false;
  }
  return true;
}

export class Lote {
  constructor(cena) {
    this.cena = cena;
    this.grupo = new THREE.Group();
    this.grupo.name = 'lote';
    cena.raiz.add(this.grupo);
    this.blocos = [];
    this.itens = new Map();          // id -> {id, bloco, v0, nv, a0, na}
    this.estado = new Map();         // id -> 'selecionado' | 'sobre'
    this.escondidos = new Set();     // ids fora do índice
    this.contornos = new Map();      // id -> LineSegments da seleção
    this.copias = [];                // formas repetidas: {ref, itens:[{ent, quadro}], malha, vivos, inversas}
    this.modo = cena.modo;
    this.materialMalha = new THREE.MeshStandardMaterial({
      vertexColors: true, metalness: 0.35, roughness: 0.6, side: THREE.DoubleSide,
    });
    this.materialArestas = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.55, depthWrite: false,
    });
    // a cor das cópias vem de cada cópia (instanceColor), não dos vértices
    this.materialCopias = new THREE.MeshStandardMaterial({
      metalness: 0.35, roughness: 0.6, side: THREE.DoubleSide,
    });
    this.aplicarCorte(cena.planosCorte || []);
  }

  /** Sólido com faces (e sem linhas soltas), chapa e barra vão para o lote. */
  static aceita(ent) {
    if (!ent) return false;
    if (ent.tipo === 'chapa') return !!(ent.contorno && ent.contorno.length >= 3);
    if (ent.tipo === 'barra') return true;
    if (ent.tipo !== 'solido') return false;
    if (ent.atributos && ent.atributos.tipo) return false;      // cota, linha de construção…
    return !!(ent.vertices && ent.vertices.length && ent.faces && ent.faces.length);
  }

  get tamanho() { return this.itens.size; }

  // ---------------------------------------------------------------- construção

  /**
   * Põe várias entidades de uma vez (é como o modelo carrega). Quem já estava sai
   * antes. As peças são ordenadas no espaço para cada bloco ser compacto: o raycast
   * descarta blocos pela esfera envolvente antes de olhar triângulo por triângulo.
   */
  definirVarios(ents) {
    const pecas = [];
    // tira de uma vez quem já estava (cada remoção avulsa refazia os índices do bloco)
    const velhas = ents.filter(e => this.itens.has(e.id));
    for (const e of velhas) this.remover(e.id, true);
    if (velhas.length) this.concluir();
    const copias = this._agruparCopias(ents);
    for (const ent of ents) {
      const g = this._geometria(ent, copias.get(ent.id));
      if (!g) continue;
      pecas.push(g);
    }
    if (!pecas.length) return;
    pecas.sort((a, b) => (a.centro[0] - b.centro[0]) || (a.centro[1] - b.centro[1]));
    let atual = [], soma = 0;
    const lotes = [];
    for (const p of pecas) {
      if (soma && soma + p.nv > VERTS_POR_BLOCO) { lotes.push(atual); atual = []; soma = 0; }
      atual.push(p);
      soma += p.nv;
    }
    if (atual.length) lotes.push(atual);
    for (const l of lotes) this._montarBloco(l);
    for (const p of pecas) { if (p.proprio && p.geom) p.geom.dispose(); p.arestas.dispose(); }
    for (const p of pecas) this.pintar(p.id);
    this.aplicarModo(this.modo);
    this.definirSombras(this.cena.sombrasAtivas);
  }

  /**
   * Sólidos que são a mesma malha só movida ou girada: id -> {grupo, i}. Candidatas pela
   * contagem de vértices e pelas faces (os mesmos índices); cópia é a que bate com a referência
   * vértice a vértice. Cada grupo aceito já sai com o InstancedMesh montado.
   */
  _agruparCopias(ents) {
    const mapa = new Map();
    const porChave = new Map();
    for (const ent of ents) {
      if (ent.tipo !== 'solido' || !ent.vertices || ent.vertices.length < 3 || !ent.faces) continue;
      let h = 2166136261 ^ ent.vertices.length;
      for (const f of ent.faces) { h = Math.imul(h ^ f.length, 16777619); for (const i of f) h = Math.imul(h ^ i, 16777619); }
      const chave = ent.vertices.length + '|' + ent.faces.length + '|' + (h >>> 0);
      let l = porChave.get(chave);
      if (!l) porChave.set(chave, (l = []));
      l.push(ent);
    }
    for (const lista of porChave.values()) {
      if (lista.length < 2) continue;
      const tri = lista[0].faces.reduce((s, f) => s + Math.max(f.length - 2, 0), 0);
      let resto = lista;
      while (resto.length >= 2 && tri * (resto.length - 1) >= MIN_TRI_COPIAS) {
        const ref = resto[0];
        const ancoras = _ancoras(ref.vertices);
        const qRef = ancoras && _quadro(ref.vertices, ancoras);
        if (!qRef) break;
        const inv = qRef.clone().invert();
        const iguais = [{ ent: ref, quadro: qRef }], outros = [];
        for (const e of resto.slice(1)) {
          const q = _quadro(e.vertices, ancoras);
          if (q && _bate(ref.vertices, e.vertices, q.clone().multiply(inv))) iguais.push({ ent: e, quadro: q });
          else outros.push(e);
        }
        if (iguais.length >= 2 && tri * (iguais.length - 1) >= MIN_TRI_COPIAS) {
          const grupo = { ref, inv, itens: iguais, malha: null, vivos: iguais.length, inversas: [] };
          if (this._montarCopias(grupo)) iguais.forEach((x, i) => mapa.set(x.ent.id, { grupo, i }));
        }
        resto = outros;
      }
    }
    return mapa;
  }

  /** A malha da forma, uma vez, perto da origem (a Float32 da placa guarda a forma sem perder
   *  precisão longe dela), e uma matriz por cópia. */
  _montarCopias(grupo) {
    let geom = null;
    try { ({ geom } = this.cena._geometriaSolido(grupo.ref)); } catch (e) { geom = null; }
    if (!geom) return false;
    const g = geom.index ? geom.toNonIndexed() : geom;
    g.applyMatrix4(grupo.inv);
    if (!g.getAttribute('normal')) g.computeVertexNormals();
    const malha = new THREE.InstancedMesh(g, this.materialCopias, grupo.itens.length);
    grupo.itens.forEach((x, i) => {
      malha.setMatrixAt(i, this.escondidos.has(x.ent.id) ? _zero : x.quadro);
      malha.setColorAt(i, _cor.set('#7d8a9e'));
    });
    malha.instanceMatrix.needsUpdate = true;
    malha.frustumCulled = false;
    malha.name = 'lote-copias';
    malha.userData.lote = true;
    malha.raycast = (raycaster, intersects) => this._raycastCopias(grupo, raycaster, intersects);
    grupo.malha = malha;
    this.copias.push(grupo);
    this.grupo.add(malha);
    return true;
  }

  _descartarCopias(grupo) {
    const i = this.copias.indexOf(grupo);
    if (i >= 0) this.copias.splice(i, 1);
    this.grupo.remove(grupo.malha);
    grupo.malha.geometry.dispose();
    grupo.malha.dispose();
  }

  _geometria(ent, copia = null) {
    if (copia) {
      // a malha está no grupo de cópias; aqui só as arestas, no mundo, e a caixa
      const arestas = new THREE.BufferGeometry();
      arestas.setAttribute('position', new THREE.BufferAttribute(arestasDoSolido(ent.vertices, ent.faces), 3));
      const caixa = new THREE.Box3();
      for (const v of ent.vertices) caixa.expandByPoint(_p.set(v[0], v[1], v[2]));
      return { id: ent.id, geom: null, arestas, nv: 0, na: arestas.getAttribute('position').count,
               centro: caixa.getCenter(new THREE.Vector3()).toArray(), chave: null, proprio: false, caixa, copia };
    }
    let geom = null, matriz = null, chave = null;
    try {
      if (ent.tipo === 'barra') ({ geom, matriz, chave } = this.cena._geometriaBarra(ent));
      else if (ent.tipo === 'chapa') ({ geom, matriz, chave } = this.cena._geometriaChapa(ent));
      else ({ geom } = this.cena._geometriaSolido(ent));
    } catch (e) { geom = null; }
    if (!geom) return null;
    // Barra e chapa vêm do cache, em coordenadas locais: a cópia entra no bloco já no
    // mundo (a do cache fica intacta para as outras peças iguais).
    let g = geom.index ? geom.toNonIndexed() : (chave ? geom.clone() : geom);
    if (matriz) {
      if (g === geom) g = geom.clone();
      g.applyMatrix4(matriz);
    }
    if (!g.getAttribute('normal')) g.computeVertexNormals();
    const pos = g.getAttribute('position');
    let arestas = null;
    if (ent.tipo === 'solido') {
      arestas = new THREE.BufferGeometry();
      arestas.setAttribute('position', new THREE.BufferAttribute(arestasDoSolido(ent.vertices, ent.faces), 3));
    } else arestas = new THREE.EdgesGeometry(g, 24);
    const centro = [0, 0, 0];
    const arr = pos.array;
    for (let i = 0; i < arr.length; i += 3) { centro[0] += arr[i]; centro[1] += arr[i + 1]; centro[2] += arr[i + 2]; }
    for (let i = 0; i < 3; i++) centro[i] /= Math.max(pos.count, 1);
    return { id: ent.id, geom: g, arestas, nv: pos.count, na: arestas.getAttribute('position').count, centro,
             chave: chave || null, proprio: g !== geom };
  }

  _montarBloco(pecas) {
    let nv = 0, na = 0;
    for (const p of pecas) { nv += p.nv; na += p.na; }
    // normal em 16 bits e cor em 8 (normalizados): 18 bytes por vértice a menos que em Float32 —
    // ~270 dos 745 MB dos blocos do Bella Casa (05/10), na memória e na placa de vídeo. A cor é
    // lisa por peça e a normal erra 1/32767: a imagem é a mesma
    const pos = new Float32Array(nv * 3), nor = new Int16Array(nv * 3), cor = new Uint8Array(nv * 3);
    const apos = new Float32Array(na * 3), acor = new Uint8Array(na * 3);
    const bloco = { itens: [], malha: null, arestas: null, nv, na, sujo: false };
    let v0 = 0, a0 = 0;
    const caixaBloco = new THREE.Box3();
    for (const p of pecas) {
      if (p.geom) {
        pos.set(p.geom.getAttribute('position').array, v0 * 3);
        const n = p.geom.getAttribute('normal').array;
        for (let i = 0, k = v0 * 3; i < n.length; i++, k++) nor[k] = Math.round(Math.max(-1, Math.min(1, n[i])) * 32767);
      }
      apos.set(p.arestas.getAttribute('position').array, a0 * 3);
      // Caixa envolvente da peça: é o que faz a escolha pelo cursor ser barata (sem ela,
      // o raio testaria os ~16 mil triângulos de cada bloco a cada movimento do mouse).
      const caixa = p.caixa || new THREE.Box3().setFromArray(p.geom.getAttribute('position').array);
      caixaBloco.union(caixa);
      const item = { id: p.id, bloco, v0, nv: p.nv, a0, na: p.na, chave: p.chave,
                     corMalha: null, corAresta: null, caixa, copia: p.copia || null };
      bloco.itens.push(item);
      this.itens.set(p.id, item);
      v0 += p.nv;
      a0 += p.na;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3, true));
    g.setAttribute('color', new THREE.BufferAttribute(cor, 3, true));
    g.setIndex(new THREE.BufferAttribute(this._indice(bloco, false), 1));
    bloco.caixa = caixaBloco;
    const malha = new THREE.Mesh(g, this.materialMalha);
    malha.name = 'lote-malha';
    malha.userData.lote = true;
    malha.userData.entidadeDe = (faceIndex) => this._entidadeDaFace(bloco, faceIndex);
    // Escolha pelo cursor: caixa do bloco → caixa de cada peça → triângulos só das
    // candidatas. Substitui o raycast padrão, que varre o bloco inteiro.
    malha.raycast = (raycaster, intersects) => this._raycast(bloco, raycaster, intersects);
    const ga = new THREE.BufferGeometry();
    ga.setAttribute('position', new THREE.BufferAttribute(apos, 3));
    ga.setAttribute('color', new THREE.BufferAttribute(acor, 3, true));
    ga.setIndex(new THREE.BufferAttribute(this._indice(bloco, true), 1));
    const arestas = new THREE.LineSegments(ga, this.materialArestas);
    arestas.name = 'lote-arestas';
    arestas.raycast = () => {};
    bloco.malha = malha;
    bloco.arestas = arestas;
    this.blocos.push(bloco);
    this.grupo.add(malha, arestas);
  }

  /** Índice do bloco sem as peças escondidas. */
  _indice(bloco, deArestas) {
    let n = 0;
    for (const it of bloco.itens) if (!this.escondidos.has(it.id)) n += deArestas ? it.na : it.nv;
    const idx = new Uint32Array(n);
    let k = 0;
    for (const it of bloco.itens) {
      if (this.escondidos.has(it.id)) continue;
      const ini = deArestas ? it.a0 : it.v0, fim = ini + (deArestas ? it.na : it.nv);
      for (let i = ini; i < fim; i++) idx[k++] = i;
    }
    return idx;
  }

  /** Raycast do bloco: devolve no máximo um encontro, o da peça mais próxima. */
  _raycast(bloco, raycaster, intersects) {
    const malha = bloco.malha;
    if (!malha.visible || !bloco.caixa) return;
    _inv.copy(malha.matrixWorld).invert();
    _raio.copy(raycaster.ray).applyMatrix4(_inv);
    if (!_raio.intersectsBox(bloco.caixa)) return;
    const pos = malha.geometry.getAttribute('position');
    let melhor = Infinity, item = null, tri = -1;
    for (const it of bloco.itens) {
      if (this.escondidos.has(it.id)) continue;
      if (!_raio.intersectsBox(it.caixa)) continue;
      const fim = it.v0 + it.nv;
      for (let i = it.v0; i < fim; i += 3) {
        _a.fromBufferAttribute(pos, i);
        _b.fromBufferAttribute(pos, i + 1);
        _c.fromBufferAttribute(pos, i + 2);
        if (!_raio.intersectTriangle(_a, _b, _c, false, _p)) continue;   // material é DoubleSide
        const d = _p.distanceToSquared(_raio.origin);
        if (d < melhor) { melhor = d; item = it; tri = i; }
      }
    }
    if (!item) return;
    _a.fromBufferAttribute(pos, tri);
    _b.fromBufferAttribute(pos, tri + 1);
    _c.fromBufferAttribute(pos, tri + 2);
    _raio.intersectTriangle(_a, _b, _c, false, _p);
    const ponto = _p.clone().applyMatrix4(malha.matrixWorld);
    const distancia = raycaster.ray.origin.distanceTo(ponto);
    if (distancia < raycaster.near || distancia > raycaster.far) return;
    _tri.set(_a, _b, _c);
    const normal = new THREE.Vector3();
    _tri.getNormal(normal);
    intersects.push({
      distance: distancia, point: ponto, object: malha, entidadeId: item.id,
      face: { a: tri, b: tri + 1, c: tri + 2, normal, materialIndex: 0 },
      faceIndex: tri / 3, uv: null,
    });
  }

  /** Raycast de um grupo de cópias: caixa de cada cópia no lote, depois os triângulos da forma
   *  no espaço dela (a matriz é rígida, então as distâncias se comparam direto). */
  _raycastCopias(grupo, raycaster, intersects) {
    const malha = grupo.malha;
    if (!malha.visible) return;
    _inv.copy(malha.matrixWorld).invert();
    _raioLote.copy(raycaster.ray).applyMatrix4(_inv);
    const pos = malha.geometry.getAttribute('position');
    let melhor = Infinity, achado = -1, tri = -1;
    for (let i = 0; i < grupo.itens.length; i++) {
      const id = grupo.itens[i].ent.id;
      const it = this.itens.get(id);
      if (!it || !it.copia || it.copia.grupo !== grupo || this.escondidos.has(id)) continue;
      if (!_raioLote.intersectsBox(it.caixa)) continue;
      const inv = grupo.inversas[i] || (grupo.inversas[i] = grupo.itens[i].quadro.clone().invert());
      _raio.copy(_raioLote).applyMatrix4(inv);
      for (let k = 0; k < pos.count; k += 3) {
        _a.fromBufferAttribute(pos, k);
        _b.fromBufferAttribute(pos, k + 1);
        _c.fromBufferAttribute(pos, k + 2);
        if (!_raio.intersectTriangle(_a, _b, _c, false, _p)) continue;
        const d = _p.distanceToSquared(_raio.origin);
        if (d < melhor) { melhor = d; achado = i; tri = k; }
      }
    }
    if (achado < 0) return;
    const quadro = grupo.itens[achado].quadro;
    _raio.copy(_raioLote).applyMatrix4(grupo.inversas[achado]);
    _a.fromBufferAttribute(pos, tri);
    _b.fromBufferAttribute(pos, tri + 1);
    _c.fromBufferAttribute(pos, tri + 2);
    _raio.intersectTriangle(_a, _b, _c, false, _p);
    const ponto = _p.clone().applyMatrix4(quadro).applyMatrix4(malha.matrixWorld);
    const distancia = raycaster.ray.origin.distanceTo(ponto);
    if (distancia < raycaster.near || distancia > raycaster.far) return;
    _tri.set(_a, _b, _c);
    const normal = new THREE.Vector3();
    _tri.getNormal(normal);
    normal.applyMatrix3(new THREE.Matrix3().setFromMatrix4(quadro)).normalize();   // para o espaço do lote
    intersects.push({
      distance: distancia, point: ponto, object: malha, entidadeId: grupo.itens[achado].ent.id,
      face: { a: tri, b: tri + 1, c: tri + 2, normal, materialIndex: 0 },
      faceIndex: tri / 3, uv: null, instanceId: achado,
    });
  }

  _entidadeDaFace(bloco, faceIndex) {
    const idx = bloco.malha.geometry.index;
    if (!idx || faceIndex == null) return null;
    const v = idx.array[faceIndex * 3];
    // busca binária pelo item que contém o vértice
    const itens = bloco.itens;
    let lo = 0, hi = itens.length - 1;
    while (lo <= hi) {
      const m = (lo + hi) >> 1, it = itens[m];
      if (v < it.v0) hi = m - 1;
      else if (v >= it.v0 + it.nv) lo = m + 1;
      else return it.id;
    }
    return null;
  }

  /** Tira a peça do lote. `adiar` deixa os índices para um `concluir()` depois. */
  remover(id, adiar = false) {
    const it = this.itens.get(id);
    if (!it) return;
    this.itens.delete(id);
    this.estado.delete(id);
    this._tirarContorno(id);
    if (it.copia) {
      const g = it.copia.grupo;
      g.malha.setMatrixAt(it.copia.i, _zero);
      g.malha.instanceMatrix.needsUpdate = true;
      if (--g.vivos <= 0) this._descartarCopias(g);
    }
    const b = it.bloco;
    b.itens.splice(b.itens.indexOf(it), 1);
    b.sujo = true;                    // a geometria fica no bloco; só sai do índice
    if (adiar) return;
    this.concluir();
    if (!b.itens.length) this._descartarBloco(b);
  }

  _descartarBloco(b) {
    this.blocos.splice(this.blocos.indexOf(b), 1);
    this.grupo.remove(b.malha, b.arestas);
    b.malha.geometry.dispose();
    b.arestas.geometry.dispose();
  }

  // ----------------------------------------------------------------- estado

  /** Esconde ou mostra a peça (camada apagada): entra ou sai do índice do bloco. */
  mostrar(id, visivel) {
    const it = this.itens.get(id);
    if (!it) return;
    const escondida = this.escondidos.has(id);
    if (visivel === !escondida) return;
    if (visivel) this.escondidos.delete(id); else this.escondidos.add(id);
    it.bloco.sujo = true;
    if (it.copia) {
      const { grupo, i } = it.copia;
      grupo.malha.setMatrixAt(i, visivel ? grupo.itens[i].quadro : _zero);
      grupo.malha.instanceMatrix.needsUpdate = true;
    }
    if (!visivel) this._tirarContorno(id);
  }

  /** Aplica os índices dos blocos que mudaram (chame ao fim de um lote de mudanças). */
  concluir() {
    for (const b of this.blocos.slice()) {
      if (!b.sujo) continue;
      if (!b.itens.length) { this._descartarBloco(b); continue; }
      b.sujo = false;
      b.malha.geometry.setIndex(new THREE.BufferAttribute(this._indice(b, false), 1));
      b.arestas.geometry.setIndex(new THREE.BufferAttribute(this._indice(b, true), 1));
      b.malha.geometry.computeBoundingSphere();
    }
  }

  /** Cor da peça pela decisão da cena (material, camada, mapa, destaque) e pelo realce. */
  pintar(id) {
    const it = this.itens.get(id);
    const ent = this.cena.documento.get(id);
    if (!it || !ent) return;
    const cena = this.cena;
    let base = cena._corDe(ent);
    const fantasma = (cena.destaque && !cena.destaque.has(id)) ||
                     (cena.pintandoPorValor && !cena._corDeValor(ent));
    if (fantasma) base = cena.escuro ? '#2e3642' : '#d7dce6';
    const estado = this.estado.get(id);
    let corMalha = base;
    let corAresta = misturar(base, cena.escuro ? '#f0f5ff' : '#101822', 0.55);
    if (cena.destaque && cena.destaque.has(id) && estado !== 'sobre') {
      // a peça em destaque na cor cheia: misturada ao azul ela sumia no cinza do resto (30/09)
      corMalha = COR_DESTAQUE;
      corAresta = COR_DESTAQUE_ARESTA;
    } else if (estado) {
      const cor = estado === 'selecionado' ? COR_SELECAO : COR_SOBRE;
      corMalha = misturar(base, cor, estado === 'selecionado' ? 0.55 : 0.3);
      corAresta = cor;
    }
    // Repintar tudo (camada, tema, mapa) passa por cada peça: só quem mudou sobe para a placa.
    if (it.corMalha === corMalha && it.corAresta === corAresta) return;
    it.corMalha = corMalha;
    it.corAresta = corAresta;
    this._escrever(it, corMalha, corAresta);
  }

  _escrever(it, corMalha, corAresta) {
    if (it.copia) {
      const m = it.copia.grupo.malha;
      m.setColorAt(it.copia.i, _cor.set(corMalha));
      m.instanceColor.needsUpdate = true;
    }
    const b = it.bloco;
    const cor = b.malha.geometry.getAttribute('color');
    _cor.set(corMalha);
    let r = Math.round(_cor.r * 255), g = Math.round(_cor.g * 255), bb = Math.round(_cor.b * 255);      // cor em 8 bits
    const arr = cor.array;
    for (let i = it.v0 * 3, fim = (it.v0 + it.nv) * 3; i < fim; i += 3) { arr[i] = r; arr[i + 1] = g; arr[i + 2] = bb; }
    this._marcar(cor, it.v0 * 3, it.nv * 3);
    const acor = b.arestas.geometry.getAttribute('color');
    _cor.set(corAresta);
    r = Math.round(_cor.r * 255); g = Math.round(_cor.g * 255); bb = Math.round(_cor.b * 255);
    const a = acor.array;
    for (let i = it.a0 * 3, fim = (it.a0 + it.na) * 3; i < fim; i += 3) { a[i] = r; a[i + 1] = g; a[i + 2] = bb; }
    this._marcar(acor, it.a0 * 3, it.na * 3);
  }

  /**
   * Só os trechos mudados sobem para a placa. As faixas se acumulam até o próximo quadro
   * (o renderer as limpa depois de enviar); muitas de uma vez viram o buffer inteiro.
   * Antes isto lia `attr.needsUpdate` para saber se já havia envio pendente — mas no
   * three.js ele só tem setter, a leitura dá undefined, e cada peça sobrescrevia a faixa
   * da anterior: repintar o modelo (colorir por perfil) só mudava a última peça.
   * O pedido de envio (`needsUpdate`) vai sempre: faixas marcadas antes do primeiro envio
   * do bloco não são limpas pelo three.js (o primeiro envio manda tudo e deixa a lista),
   * então "já há faixa pendente" não quer dizer que um envio vai acontecer.
   */
  _marcar(attr, offset, count) {
    const faixas = attr.updateRanges;
    const n = attr.array.length;
    const inteiro = faixas.length === 1 && faixas[0].start === 0 && faixas[0].count === n;
    if (!inteiro) {
      if (faixas.length >= 64) { attr.clearUpdateRanges(); attr.addUpdateRange(0, n); }
      else attr.addUpdateRange(offset, count);
    }
    attr.needsUpdate = true;
  }

  /** Realce da seleção ou do cursor. `estado` null tira. */
  realcar(id, estado) {
    if (!this.itens.has(id)) return;
    if (estado) this.estado.set(id, estado); else this.estado.delete(id);
    this.pintar(id);
    if (estado === 'selecionado') this._porContorno(id); else this._tirarContorno(id);
  }

  _porContorno(id) {
    // a peça em destaque (a escolhida no 2D) com o contorno na cor dele e forte: o azul fraco por cima dela
    // era o que se via, e ela parecia só mais uma selecionada (30/09)
    const destacada = !!(this.cena.destaque && this.cena.destaque.has(id));
    const cor = destacada ? COR_DESTAQUE : COR_SELECAO;
    const opacidade = destacada ? 0.9 : 0.32;
    const velho = this.contornos.get(id);
    if (velho) { velho.material.color.set(cor); velho.material.opacity = opacidade; return; }
    if (this.contornos.size >= MAX_CONTORNOS) return;
    const it = this.itens.get(id);
    if (!it || !it.na) return;
    const fonte = it.bloco.arestas.geometry.getAttribute('position').array;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(fonte.slice(it.a0 * 3, (it.a0 + it.na) * 3), 3));
    const m = new THREE.LineBasicMaterial({ color: new THREE.Color(cor), transparent: true,
                                            opacity: opacidade, depthTest: false, depthWrite: false });
    const l = new THREE.LineSegments(g, m);
    l.renderOrder = 12;
    l.raycast = () => {};
    this.contornos.set(id, l);
    this.grupo.add(l);
  }

  _tirarContorno(id) {
    const l = this.contornos.get(id);
    if (!l) return;
    this.contornos.delete(id);
    this.grupo.remove(l);
    l.geometry.dispose();
    l.material.dispose();
  }

  aplicarModo(modo) {
    this.modo = modo;
    const raiox = modo === 'raiox';
    this.materialMalha.transparent = raiox;
    this.materialMalha.opacity = raiox ? 0.18 : 1;
    this.materialMalha.depthWrite = !raiox;
    this.materialMalha.needsUpdate = true;
    this.materialCopias.transparent = raiox;
    this.materialCopias.opacity = raiox ? 0.18 : 1;
    this.materialCopias.depthWrite = !raiox;
    this.materialCopias.needsUpdate = true;
    for (const b of this.blocos) {
      b.malha.visible = modo !== 'arestas';
      b.arestas.visible = modo !== 'sombreado';
      b.malha.renderOrder = raiox ? 1 : 0;
    }
    for (const g of this.copias) {
      g.malha.visible = modo !== 'arestas';
      g.malha.renderOrder = raiox ? 1 : 0;
    }
  }

  aplicarCorte(planos) {
    const p = planos && planos.length ? planos : null;
    this.materialMalha.clippingPlanes = p;
    this.materialArestas.clippingPlanes = p;
    this.materialCopias.clippingPlanes = p;
    this.materialCopias.needsUpdate = true;
    this.materialMalha.needsUpdate = true;
    this.materialArestas.needsUpdate = true;
    for (const l of this.contornos.values()) { l.material.clippingPlanes = p; l.material.needsUpdate = true; }
  }

  definirSombras(ligadas) {
    for (const b of this.blocos) { b.malha.castShadow = !!ligadas; b.malha.receiveShadow = !!ligadas; }
    for (const g of this.copias) { g.malha.castShadow = !!ligadas; g.malha.receiveShadow = !!ligadas; }
  }

  /** Malhas dos blocos e das cópias, para o raycast (as arestas não entram). */
  alvos() {
    return [...this.blocos.filter(b => b.malha.visible).map(b => b.malha),
            ...this.copias.filter(g => g.malha.visible).map(g => g.malha)];
  }

  descartar() {
    for (const b of this.blocos.slice()) this._descartarBloco(b);
    for (const g of this.copias.slice()) this._descartarCopias(g);
    for (const id of [...this.contornos.keys()]) this._tirarContorno(id);
    this.itens.clear();
    this.estado.clear();
    this.escondidos.clear();
    this.cena.raiz.remove(this.grupo);
    this.materialMalha.dispose();
    this.materialArestas.dispose();
    this.materialCopias.dispose();
  }
}
