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

import * as THREE from 'three';
import { misturar } from './cena.js';

/** Acima de tantas entidades os sólidos são desenhados em lote. */
export const LIMITE_LOTE = 1500;

/** Vértices por bloco: ~12 blocos no IFC de 5 mil peças. Blocos menores fazem o raycast
 *  e a atualização de cor mais baratos; blocos maiores, menos chamadas de desenho. */
const VERTS_POR_BLOCO = 50000;

/** Contornos "através do modelo" da seleção: além disto, só a cor marca a peça. */
const MAX_CONTORNOS = 400;

const COR_SELECAO = '#1f7ae0';
const COR_SOBRE = '#5fa8f5';

const _cor = new THREE.Color();
// temporários do raycast (um por módulo: a escolha roda a cada movimento do mouse)
const _inv = new THREE.Matrix4();
const _raio = new THREE.Ray();
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3();
const _p = new THREE.Vector3();
const _tri = new THREE.Triangle();

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
    this.modo = cena.modo;
    this.materialMalha = new THREE.MeshStandardMaterial({
      vertexColors: true, metalness: 0.35, roughness: 0.6, side: THREE.DoubleSide,
    });
    this.materialArestas = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.55, depthWrite: false,
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
    for (const ent of ents) {
      if (this.itens.has(ent.id)) this.remover(ent.id);
      const g = this._geometria(ent);
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
    for (const p of pecas) { if (p.proprio) p.geom.dispose(); p.arestas.dispose(); }
    for (const p of pecas) this.pintar(p.id);
    this.aplicarModo(this.modo);
    this.definirSombras(this.cena.sombrasAtivas);
  }

  _geometria(ent) {
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
    const arestas = new THREE.EdgesGeometry(g, 24);
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
    const pos = new Float32Array(nv * 3), nor = new Float32Array(nv * 3), cor = new Float32Array(nv * 3);
    const apos = new Float32Array(na * 3), acor = new Float32Array(na * 3);
    const bloco = { itens: [], malha: null, arestas: null, nv, na, sujo: false };
    let v0 = 0, a0 = 0;
    const caixaBloco = new THREE.Box3();
    for (const p of pecas) {
      pos.set(p.geom.getAttribute('position').array, v0 * 3);
      nor.set(p.geom.getAttribute('normal').array, v0 * 3);
      apos.set(p.arestas.getAttribute('position').array, a0 * 3);
      // Caixa envolvente da peça: é o que faz a escolha pelo cursor ser barata (sem ela,
      // o raio testaria os ~16 mil triângulos de cada bloco a cada movimento do mouse).
      const caixa = new THREE.Box3().setFromArray(p.geom.getAttribute('position').array);
      caixaBloco.union(caixa);
      const item = { id: p.id, bloco, v0, nv: p.nv, a0, na: p.na, chave: p.chave,
                     corMalha: null, corAresta: null, caixa };
      bloco.itens.push(item);
      this.itens.set(p.id, item);
      v0 += p.nv;
      a0 += p.na;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    g.setAttribute('color', new THREE.BufferAttribute(cor, 3));
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
    ga.setAttribute('color', new THREE.BufferAttribute(acor, 3));
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

  remover(id) {
    const it = this.itens.get(id);
    if (!it) return;
    this.itens.delete(id);
    this.estado.delete(id);
    this._tirarContorno(id);
    const b = it.bloco;
    b.itens.splice(b.itens.indexOf(it), 1);
    // a geometria fica no bloco (vira zona morta); só sai do índice
    this.escondidos.add(id);
    b.sujo = true;
    this.concluir();
    this.escondidos.delete(id);
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
    if (!visivel) this._tirarContorno(id);
  }

  /** Aplica os índices dos blocos que mudaram (chame ao fim de um lote de mudanças). */
  concluir() {
    for (const b of this.blocos) {
      if (!b.sujo) continue;
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
    if (estado) {
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
    const b = it.bloco;
    const cor = b.malha.geometry.getAttribute('color');
    _cor.set(corMalha);
    const arr = cor.array;
    for (let i = it.v0 * 3, fim = (it.v0 + it.nv) * 3; i < fim; i += 3) { arr[i] = _cor.r; arr[i + 1] = _cor.g; arr[i + 2] = _cor.b; }
    this._marcar(cor, it.v0 * 3, it.nv * 3);
    const acor = b.arestas.geometry.getAttribute('color');
    _cor.set(corAresta);
    const a = acor.array;
    for (let i = it.a0 * 3, fim = (it.a0 + it.na) * 3; i < fim; i += 3) { a[i] = _cor.r; a[i + 1] = _cor.g; a[i + 2] = _cor.b; }
    this._marcar(acor, it.a0 * 3, it.na * 3);
  }

  /** Só o trecho mudado sobe para a placa; vários trechos no mesmo quadro viram o buffer inteiro. */
  _marcar(attr, offset, count) {
    if (attr.needsUpdate) {
      attr.updateRange.offset = 0;
      attr.updateRange.count = -1;
      return;
    }
    attr.updateRange.offset = offset;
    attr.updateRange.count = count;
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
    if (this.contornos.has(id) || this.contornos.size >= MAX_CONTORNOS) return;
    const it = this.itens.get(id);
    if (!it || !it.na) return;
    const fonte = it.bloco.arestas.geometry.getAttribute('position').array;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(fonte.slice(it.a0 * 3, (it.a0 + it.na) * 3), 3));
    const m = new THREE.LineBasicMaterial({ color: new THREE.Color(COR_SELECAO), transparent: true,
                                            opacity: 0.32, depthTest: false, depthWrite: false });
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
    for (const b of this.blocos) {
      b.malha.visible = modo !== 'arestas';
      b.arestas.visible = modo !== 'sombreado';
      b.malha.renderOrder = raiox ? 1 : 0;
    }
  }

  aplicarCorte(planos) {
    const p = planos && planos.length ? planos : null;
    this.materialMalha.clippingPlanes = p;
    this.materialArestas.clippingPlanes = p;
    this.materialMalha.needsUpdate = true;
    this.materialArestas.needsUpdate = true;
    for (const l of this.contornos.values()) { l.material.clippingPlanes = p; l.material.needsUpdate = true; }
  }

  definirSombras(ligadas) {
    for (const b of this.blocos) { b.malha.castShadow = !!ligadas; b.malha.receiveShadow = !!ligadas; }
  }

  /** Malhas dos blocos, para o raycast (as arestas não entram). */
  alvos() {
    return this.blocos.filter(b => b.malha.visible).map(b => b.malha);
  }

  descartar() {
    for (const b of this.blocos.slice()) this._descartarBloco(b);
    for (const id of [...this.contornos.keys()]) this._tirarContorno(id);
    this.itens.clear();
    this.estado.clear();
    this.escondidos.clear();
    this.cena.raiz.remove(this.grupo);
    this.materialMalha.dispose();
    this.materialArestas.dispose();
  }
}
