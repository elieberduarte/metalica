// Visualizador do 3D leve (.mcel) — o modelo 3D do celular. Só consulta.
//
// O arquivo vem pronto do PC (saida/pacote_celular.py): blocos de peças com os vértices em
// 16 bits e as formas repetidas com uma matriz por cópia. Aqui nada é refeito: os trechos do
// arquivo viram buffers da placa de vídeo e, depois de enviados, a cópia na memória do
// navegador é solta. É isso que deixa o Bella Casa inteiro caber no celular (no editor do
// PC ele ocupa ~490 MB, porque lá o modelo é editável).
//
// * A cor e a visibilidade de cada peça ficam numa textura (uma célula por peça): ligar ou
//   desligar camada, destacar a peça tocada ou pintar de outro jeito é reescrever a textura,
//   sem tocar nos vértices.
// * A normal não vem no arquivo: o sombreado plano sai das derivadas da posição na tela.
// * A escolha da peça pelo toque é pela placa (cada peça desenhada com o próprio número numa
//   imagem de 1 pixel), sem guardar triângulos na memória para o raio.
//
// Unidades: milímetros, relativos à origem do arquivo (o centro do modelo).

import * as THREE from 'three';
import { OrbitControls } from '../lib/OrbitControls.js';

const LARG_TEX = 1024;

const VERT = /* glsl */`
uniform sampler2D tPecas;
uniform float uIdBase;
attribute float pid;
#ifdef INSTANCIA
attribute vec4 i0;
attribute vec4 i1;
attribute vec4 i2;
attribute float iid;
#endif
varying vec3 vVista;
varying vec3 vCor;
#ifdef ESCOLHA
flat varying float vId;
#endif
void main() {
#ifdef INSTANCIA
  vec4 p = vec4(position, 1.0);
  vec3 mundo = vec3(dot(i0, p), dot(i1, p), dot(i2, p));
  float id = iid;
#else
  vec3 mundo = (modelMatrix * vec4(position, 1.0)).xyz;
  float id = uIdBase + pid;
#endif
  ivec2 t = ivec2(int(mod(id, ${LARG_TEX}.0)), int(floor(id / ${LARG_TEX}.0)));
  vec4 c = texelFetch(tPecas, t, 0);
  vCor = c.rgb;
#ifdef ESCOLHA
  vId = id + 1.0;
#endif
  vec4 vista = viewMatrix * vec4(mundo, 1.0);
  vVista = vista.xyz;
  gl_Position = projectionMatrix * vista;
  if (c.a < 0.5) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);     // peça escondida: fora da tela
}`;

const FRAG = /* glsl */`
varying vec3 vVista;
varying vec3 vCor;
#ifdef ESCOLHA
flat varying float vId;
#endif
uniform float uAresta;
uniform float uLonge;
void main() {
#ifdef ESCOLHA
  float r = mod(vId, 256.0), g = mod(floor(vId / 256.0), 256.0), b = floor(vId / 65536.0);
  gl_FragColor = vec4(r / 255.0, g / 255.0, b / 255.0, 1.0);
#else
  // aresta: a cor da peça escurecida e meio transparente (como no editor), para o deck de mil
  // tábuas não virar uma mancha escura de longe
  // e somem aos poucos com a distância: de perto marcam cada peça, de longe só o contorno geral
  if (uAresta > 0.5) {
    float a = mix(0.5, 0.1, clamp((-vVista.z - 0.6 * uLonge) / uLonge, 0.0, 1.0));
    gl_FragColor = vec4(vCor * 0.45, a); return;
  }
  vec3 n = normalize(cross(dFdx(vVista), dFdy(vVista)));
  if (n.z < 0.0) n = -n;
  vec3 luz = normalize(vec3(0.35, 0.55, 0.75));
  float d = max(dot(n, luz), 0.0);
  float ceu = 0.5 + 0.5 * n.y;
  gl_FragColor = vec4(min(vCor * (0.5 + 0.18 * ceu + 0.5 * d), 1.0), 1.0);
#endif
}`;

function _corHex(h, padrao) {
  const c = new THREE.Color();
  try { c.set(h || padrao); } catch (e) { c.set(padrao); }
  return c;
}

export class Visor3D {
  constructor(tela, opcoes = {}) {
    this.tela = tela;
    this.renderer = new THREE.WebGLRenderer({ canvas: tela, antialias: opcoes.antialias !== false,
                                              powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, opcoes.maxPixelRatio || 2));
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    this.renderer.sortObjects = false;          // tudo opaco: a ordem não muda a imagem
    this.cena = new THREE.Scene();
    this.cena.background = new THREE.Color(opcoes.fundo || '#e9edf2');
    this.camera = new THREE.PerspectiveCamera(45, 1, 10, 1e6);
    this.camera.up.set(0, 0, 1);
    this.controles = new OrbitControls(this.camera, tela);
    this.controles.enableDamping = false;
    this.controles.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
    this.controles.addEventListener('change', () => this.pedirQuadro());
    this.raiz = new THREE.Group();
    this.cena.add(this.raiz);
    this.malhas = [];        // {malha, arestas, escolha, forma?, ids?}
    this.fichas = null;
    this.cabecalho = null;
    this.selecionada = -1;
    this.arestasLigadas = opcoes.arestas !== false;
    this._pedido = false;
    this.quadros = 0;
    this._redimensionar = () => this.redimensionar();
    window.addEventListener('resize', this._redimensionar);
    this.redimensionar();
  }

  // ---------------------------------------------------------------- carregar

  /** Abre o .mcel (URL ou ArrayBuffer). `aoProgresso(fração, texto)` durante a descida. */
  async carregar(fonte, aoProgresso) {
    const t0 = performance.now();
    let buf = fonte;
    if (typeof fonte === 'string') buf = await this._baixar(fonte, aoProgresso);
    const t1 = performance.now();
    const dv = new DataView(buf);
    const magica = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    if (magica !== 'MCEL') throw new Error('arquivo do 3D leve inválido');
    const versao = dv.getUint32(4, true);
    if (versao !== 1) throw new Error(`versão ${versao} do 3D leve: atualize o programa no computador`);
    const n = dv.getUint32(8, true);
    const cab = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 12, n)));
    this.cabecalho = cab;
    this.nPecas = cab.numeros.pecas;
    this._caixaModelo = new THREE.Box3(new THREE.Vector3(...cab.caixa[0]), new THREE.Vector3(...cab.caixa[1]));
    this._esferaModelo = this._caixaModelo.getBoundingSphere(new THREE.Sphere());
    this._montarTextura();
    this._materiais();
    for (const b of cab.blocos) this._bloco(buf, b);
    for (const f of cab.formas) this._forma(buf, f);
    buf = null;                               // os trechos sobem para a placa e a cópia sai
    this.enquadrar();
    this.pedirQuadro();
    this.renderer.render(this.cena, this.camera);      // envia tudo agora (o primeiro quadro)
    this.tempos = { baixar: Math.round(t1 - t0), montar: Math.round(performance.now() - t1) };
    return this.tempos;
  }

  async _baixar(url, aoProgresso) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`não abriu o 3D (${r.status})`);
    const total = +r.headers.get('Content-Length') || 0;
    if (!r.body || !total) return await r.arrayBuffer();
    const saida = new Uint8Array(total);
    const leitor = r.body.getReader();
    let k = 0;
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      saida.set(value, k);
      k += value.length;
      if (aoProgresso) aoProgresso(k / total, `${(k / 1048576).toFixed(1)} de ${(total / 1048576).toFixed(1)} MB`);
    }
    return saida.buffer;
  }

  _montarTextura() {
    const altura = Math.max(1, Math.ceil(this.nPecas / LARG_TEX));
    this.dadosTex = new Uint8Array(LARG_TEX * altura * 4);
    this.textura = new THREE.DataTexture(this.dadosTex, LARG_TEX, altura, THREE.RGBAFormat);
    this.textura.magFilter = THREE.NearestFilter;
    this.textura.minFilter = THREE.NearestFilter;
    this.textura.generateMipmaps = false;
    this.camadaDe = new Uint16Array(this.nPecas);
    this.visivelCamada = this.cabecalho.camadas.map(c => c.visivel);
    this.corBase = new Uint8Array(this.nPecas * 3);
    const cinza = new THREE.Color('#8a94a6');
    for (let i = 0; i < this.nPecas; i++) { this.corBase[i * 3] = cinza.r * 255; this.corBase[i * 3 + 1] = cinza.g * 255; this.corBase[i * 3 + 2] = cinza.b * 255; }
    this._repintar();
  }

  _materiais() {
    const comum = { vertexShader: VERT, fragmentShader: FRAG };
    this._uLonge = { value: 10000 };
    const un = () => ({ tPecas: { value: this.textura }, uIdBase: { value: 0 }, uAresta: { value: 0 }, uLonge: this._uLonge });
    this._mat = (defs, aresta) => {
      const m = new THREE.ShaderMaterial({ ...comum, uniforms: un(), defines: defs,
        side: THREE.DoubleSide, polygonOffset: !aresta, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
        transparent: !!aresta, depthWrite: !aresta });
      m.uniforms.uAresta.value = aresta ? 1 : 0;
      return m;
    };
  }

  _atributos(buf, desc) {
    const v = new Uint16Array(buf, desc.ofs, desc.n * 4);
    const ib = new THREE.InterleavedBuffer(v, 4);
    ib.onUpload(_soltar);
    return { position: new THREE.InterleavedBufferAttribute(ib, 3, 0), pid: new THREE.InterleavedBufferAttribute(ib, 1, 3) };
  }

  _indice(buf, desc) {
    const T = desc.tipo === 'u32' ? Uint32Array : Uint16Array;
    const a = new THREE.BufferAttribute(new T(buf, desc.ofs, desc.n), 1);
    a.onUpload(_soltar);
    return a;
  }

  _bloco(buf, b) {
    const at = this._atributos(buf, b.vertices);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', at.position);
    g.setAttribute('pid', at.pid);
    g.setIndex(this._indice(buf, b.indices));
    const caixa = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(65535, 65535, 65535));
    g.boundingBox = caixa;
    g.boundingSphere = caixa.getBoundingSphere(new THREE.Sphere());
    const matriz = new THREE.Matrix4().makeScale(b.esc[0], b.esc[1], b.esc[2]).setPosition(b.min[0], b.min[1], b.min[2]);
    const malha = new THREE.Mesh(g, this._mat({}, false));
    const escolha = this._mat({ ESCOLHA: '' }, false);
    malha.material.uniforms.uIdBase.value = b.id0;
    escolha.uniforms.uIdBase.value = b.id0;
    malha.matrixAutoUpdate = false;
    malha.matrix.copy(matriz);
    let arestas = null;
    if (b.arestas.n) {
      const ga = new THREE.BufferGeometry();
      ga.setAttribute('position', at.position);
      ga.setAttribute('pid', at.pid);
      ga.setIndex(this._indice(buf, b.arestas));
      ga.boundingBox = caixa; ga.boundingSphere = g.boundingSphere;
      arestas = new THREE.LineSegments(ga, this._mat({}, true));
      arestas.material.uniforms.uIdBase.value = b.id0;
      arestas.matrixAutoUpdate = false;
      arestas.matrix.copy(matriz);
      arestas.visible = this.arestasLigadas;
      this.raiz.add(arestas);
    }
    this.raiz.add(malha);
    this.malhas.push({ malha, arestas, escolha, id0: b.id0, n: b.n });
  }

  _forma(buf, f) {
    const at = this._atributos(buf, f.vertices);
    const inst = new Float32Array(buf, f.copias.ofs, f.copias.n * 13);
    const ib = new THREE.InstancedInterleavedBuffer(inst, 13, 1);
    ib.onUpload(_soltar);
    const ids = [];
    for (let i = 0; i < f.copias.n; i++) ids.push(inst[i * 13 + 12]);
    const geo = (idx) => {
      const g = new THREE.InstancedBufferGeometry();
      g.setAttribute('position', at.position);
      g.setAttribute('pid', at.pid);
      g.setAttribute('i0', new THREE.InterleavedBufferAttribute(ib, 4, 0));
      g.setAttribute('i1', new THREE.InterleavedBufferAttribute(ib, 4, 4));
      g.setAttribute('i2', new THREE.InterleavedBufferAttribute(ib, 4, 8));
      g.setAttribute('iid', new THREE.InterleavedBufferAttribute(ib, 1, 12));
      g.setIndex(idx);
      g.instanceCount = f.copias.n;
      g.boundingBox = this._caixaModelo;          // as cópias se espalham pelo modelo: a caixa é a dele
      g.boundingSphere = this._esferaModelo;
      return g;
    };
    const malha = new THREE.Mesh(geo(this._indice(buf, f.indices)), this._mat({ INSTANCIA: '' }, false));
    malha.frustumCulled = false;
    const escolha = this._mat({ INSTANCIA: '', ESCOLHA: '' }, false);
    let arestas = null;
    if (f.arestas.n) {
      arestas = new THREE.LineSegments(geo(this._indice(buf, f.arestas)), this._mat({ INSTANCIA: '' }, true));
      arestas.frustumCulled = false;
      arestas.visible = this.arestasLigadas;
      this.raiz.add(arestas);
    }
    this.raiz.add(malha);
    this.malhas.push({ malha, arestas, escolha, ids });
  }

  // ---------------------------------------------------------------- fichas, camadas, cor

  definirFichas(dados) {
    this.fichas = dados.pecas;
    const mats = (this.cabecalho && this.cabecalho.materiais) || {};
    const cams = this.cabecalho.camadas;
    const cores = cams.map(c => _corHex(c.cor, '#8a94a6'));
    const porMat = new Map();
    for (let i = 0; i < this.fichas.length && i < this.nPecas; i++) {
      const f = this.fichas[i];
      this.camadaDe[i] = f.c || 0;
      let c = cores[f.c || 0] || cores[0];
      if (f.m && mats[f.m]) {
        if (!porMat.has(f.m)) porMat.set(f.m, _corHex(mats[f.m], '#8a94a6'));
        c = porMat.get(f.m);
      }
      this.corBase[i * 3] = Math.round(c.r * 255);
      this.corBase[i * 3 + 1] = Math.round(c.g * 255);
      this.corBase[i * 3 + 2] = Math.round(c.b * 255);
    }
    this._repintar();
  }

  /** Liga ou desliga a camada `i` (índice das camadas do cabeçalho). */
  mostrarCamada(i, visivel) {
    this.visivelCamada[i] = !!visivel;
    this._repintar();
  }

  ligarArestas(sim) {
    this.arestasLigadas = !!sim;
    for (const m of this.malhas) if (m.arestas) m.arestas.visible = this.arestasLigadas && m.malha.visible;
    this.pedirQuadro();
  }

  selecionar(i) {
    this.selecionada = i;
    this._repintar();
  }

  _repintar() {
    const d = this.dadosTex, sel = this.selecionada;
    for (let i = 0; i < this.nPecas; i++) {
      const k = i * 4;
      const vis = this.visivelCamada[this.camadaDe[i]] !== false;
      if (i === sel) { d[k] = 31; d[k + 1] = 122; d[k + 2] = 224; }
      else { d[k] = this.corBase[i * 3]; d[k + 1] = this.corBase[i * 3 + 1]; d[k + 2] = this.corBase[i * 3 + 2]; }
      d[k + 3] = vis ? 255 : 0;
    }
    this.textura.needsUpdate = true;
    // bloco ou forma sem nenhuma peça à vista nem é desenhado
    for (const m of this.malhas) {
      let algum = false;
      if (m.ids) { for (const id of m.ids) if (d[id * 4 + 3]) { algum = true; break; } }
      else { for (let i = m.id0; i < m.id0 + m.n; i++) if (d[i * 4 + 3]) { algum = true; break; } }
      m.malha.visible = algum;
      if (m.arestas) m.arestas.visible = algum && this.arestasLigadas;
    }
    this.pedirQuadro();
  }

  // ---------------------------------------------------------------- câmera

  /** Caixa das camadas ligadas (as fundações escondidas não contam no enquadramento). */
  caixaVisivel() {
    const cx = new THREE.Box3();
    this.cabecalho.camadas.forEach((c, i) => {
      if (this.visivelCamada[i] !== false && c.caixa) cx.union(new THREE.Box3(new THREE.Vector3(...c.caixa[0]), new THREE.Vector3(...c.caixa[1])));
    });
    return cx.isEmpty() ? this._caixaModelo.clone() : cx;
  }

  enquadrar(vista = 'iso') {
    const cx = this.caixaVisivel();
    const c = cx.getCenter(new THREE.Vector3());
    const dir = { iso: [1, -1.2, 0.9], topo: [0, -0.001, 1], frente: [0, -1, 0.05], lado: [1, 0, 0.05] }[vista] || [1, -1, 1];
    const v = new THREE.Vector3(...dir).normalize();
    // distância em que os 8 cantos da caixa cabem na tela, nas duas aberturas (na tela em pé
    // o que limita é a horizontal)
    const tv = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)), th = tv * this.camera.aspect;
    const dir_ = v.clone().negate();
    const dir_r = new THREE.Vector3().crossVectors(dir_, this.camera.up).normalize();
    const dir_u = new THREE.Vector3().crossVectors(dir_r, dir_).normalize();
    let dist = 0;
    for (let k = 0; k < 8; k++) {
      const p = new THREE.Vector3(k & 1 ? cx.max.x : cx.min.x, k & 2 ? cx.max.y : cx.min.y, k & 4 ? cx.max.z : cx.min.z).sub(c);
      const z = p.dot(v);
      dist = Math.max(dist, z + Math.abs(p.dot(dir_r)) / th, z + Math.abs(p.dot(dir_u)) / tv);
    }
    dist = (dist || 1000) * 1.06;
    this._uLonge.value = cx.getSize(new THREE.Vector3()).length() / 2;    // o "longe" das arestas: o raio do que se vê
    this.camera.position.copy(c).addScaledVector(v, dist);
    this.camera.near = Math.max(dist / 2000, 1);
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controles.target.copy(c);
    this.controles.update();
    this.pedirQuadro();
  }

  /** Gira em volta da peça (o centro dela da ficha). */
  centrarEm(i) {
    const f = this.fichas && this.fichas[i];
    if (!f) return;
    const alvo = new THREE.Vector3(f.x[0], f.x[1], f.x[2]);       // o centro já vem relativo à origem
    const delta = alvo.clone().sub(this.controles.target);
    this.controles.target.add(delta);
    this.camera.position.add(delta);
    this.controles.update();
    this.pedirQuadro();
  }

  redimensionar() {
    const w = this.tela.clientWidth || 1, h = this.tela.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.pedirQuadro();
  }

  pedirQuadro() {
    if (this._pedido) return;
    this._pedido = true;
    requestAnimationFrame(() => {
      this._pedido = false;
      this.renderer.render(this.cena, this.camera);
      this.quadros++;
    });
  }

  // ---------------------------------------------------------------- escolha pelo toque

  /** Número da peça no ponto (x, y) da tela, em pixels CSS; -1 se nenhuma. */
  escolher(x, y) {
    const w = this.tela.clientWidth, h = this.tela.clientHeight;
    if (!this._alvo) this._alvo = new THREE.WebGLRenderTarget(1, 1);
    const px = new Uint8Array(4);
    const fundo = this.cena.background;
    this.cena.background = new THREE.Color(0, 0, 0);
    const trocas = [];
    for (const m of this.malhas) {
      trocas.push([m.malha, m.malha.material]);
      m.malha.material = m.escolha;
      if (m.arestas) { trocas.push([m.arestas, m.arestas.visible, true]); m.arestas.visible = false; }
    }
    const dpr = this.renderer.getPixelRatio();
    this.camera.setViewOffset(w * dpr, h * dpr, Math.round(x * dpr), Math.round(y * dpr), 1, 1);
    this.renderer.setRenderTarget(this._alvo);
    this.renderer.render(this.cena, this.camera);
    this.renderer.readRenderTargetPixels(this._alvo, 0, 0, 1, 1, px);
    this.renderer.setRenderTarget(null);
    this.camera.clearViewOffset();
    for (const t of trocas) { if (t[2]) t[0].visible = t[1]; else t[0].material = t[1]; }
    this.cena.background = fundo;
    this.pedirQuadro();
    const id = px[0] + px[1] * 256 + px[2] * 65536 - 1;
    return id >= 0 && id < this.nPecas ? id : -1;
  }

  /** Centro da peça na tela (pixels CSS), para os testes do toque. */
  paraTela(i) {
    const f = this.fichas[i];
    const p = new THREE.Vector3(f.x[0], f.x[1], f.x[2]).project(this.camera);
    return [(p.x + 1) / 2 * this.tela.clientWidth, (1 - p.y) / 2 * this.tela.clientHeight, p.z];
  }

  // ---------------------------------------------------------------- números

  numeros() {
    const info = this.renderer.info;
    return { chamadas: info.render.calls, triangulos: info.render.triangles, geometrias: info.memory.geometries,
             pecas: this.nPecas, objetos: this.malhas.length };
  }

  descartar() {
    window.removeEventListener('resize', this._redimensionar);
    this.controles.dispose();
    for (const m of this.malhas) {
      m.malha.geometry.dispose(); m.malha.material.dispose(); m.escolha.dispose();
      if (m.arestas) { m.arestas.geometry.dispose(); m.arestas.material.dispose(); }
    }
    this.textura.dispose();
    if (this._alvo) this._alvo.dispose();
    this.renderer.dispose();
  }
}

/** Depois de enviada à placa, a cópia do trecho na memória do navegador não é mais usada. */
function _soltar() { this.array = null; }
