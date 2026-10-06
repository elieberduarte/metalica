// Visualizador do 3D leve (.mcel) — o modelo 3D do celular e o modo "ver" do computador. Só consulta.
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
/** O fundo e a linha principal da grade do Desenho 2D (web/cad/nucleo/tela.js, `grade10`): o 3D usa os mesmos. */
const TEMA_ESCURO = { fundo: '#0e131a', linha: '#ffffff', alfa: 0.13 };
const TEMA_CLARO = { fundo: '#f4f6fa', linha: '#10203c', alfa: 0.12 };

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
#ifdef PONTO
varying vec3 vMundo;
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
#ifdef PONTO
  vMundo = mundo;
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
#ifdef PONTO
varying vec3 vMundo;
#endif
uniform float uAresta;
uniform float uLonge;
uniform float uEscuro;
void main() {
#if defined(PONTO)
  gl_FragColor = vec4(vMundo, 1.0);
#elif defined(ESCOLHA)
  float r = mod(vId, 256.0), g = mod(floor(vId / 256.0), 256.0), b = floor(vId / 65536.0);
  gl_FragColor = vec4(r / 255.0, g / 255.0, b / 255.0, 1.0);
#else
  // aresta: a cor da peça escurecida e meio transparente (como no editor), para o deck de mil
  // tábuas não virar uma mancha escura de longe
  // e somem aos poucos com a distância: de perto marcam cada peça, de longe só o contorno geral
  if (uAresta > 0.5) {
    float a = mix(0.5, 0.1, clamp((-vVista.z - 0.6 * uLonge) / uLonge, 0.0, 1.0));
    // como o editor: no escuro a aresta é a cor da peça puxada para o claro; no claro, para o escuro
    vec3 ca = uEscuro > 0.5 ? mix(vCor, vec3(0.94, 0.96, 1.0), 0.55) : vCor * 0.45;
    gl_FragColor = vec4(ca, uEscuro > 0.5 ? a + 0.15 : a); return;
  }
  vec3 n = normalize(cross(dFdx(vVista), dFdy(vVista)));
  if (n.z < 0.0) n = -n;
  vec3 luz = normalize(vec3(0.35, 0.55, 0.75));
  float d = max(dot(n, luz), 0.0);
  float ceu = 0.5 + 0.5 * n.y;
  // no escuro a peça sobe um pouco para o claro (o azul-marinho das vigas sumia no fundo)
  vec3 base = uEscuro > 0.5 ? mix(vCor, vec3(1.0), 0.18) : vCor;
  gl_FragColor = vec4(min(base * (0.5 + 0.18 * ceu + 0.5 * d), 1.0), 1.0);
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
    this.dprParado = Math.min(window.devicePixelRatio || 1, opcoes.maxPixelRatio || 2);
    // girando, a imagem sai em resolução menor e sem arestas (o que pesa no celular é encher a tela de
    // alta densidade); ao soltar, volta inteira
    this.dprMovendo = Math.min(this.dprParado, opcoes.dprMovendo || 1);
    this.renderer.setPixelRatio(this.dprParado);
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    this.renderer.sortObjects = false;          // tudo opaco: a ordem não muda a imagem
    this.cena = new THREE.Scene();
    this.cena.background = new THREE.Color(opcoes.fundo || '#e9edf2');
    this.camera = new THREE.PerspectiveCamera(45, 1, 10, 1e6);
    this.camera.up.set(0, 0, 1);
    this.controles = new OrbitControls(this.camera, tela);
    this.controles.enableDamping = false;
    this.controles.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
    if (opcoes.mouse) {
      this.controles.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: THREE.MOUSE.PAN };
      this.controles.zoomToCursor = true;
    }
    this.controles.addEventListener('change', () => this.pedirQuadro());
    this.controles.addEventListener('start', () => this._movendo(true));
    this.controles.addEventListener('end', () => this._movendo(false));
    this.raiz = new THREE.Group();
    this.cena.add(this.raiz);
    this.malhas = [];        // {malha, arestas, escolha, forma?, ids?}
    this.fichas = null;
    this.cabecalho = null;
    this.selecionada = -1;
    this.selecaoVarias = new Set();       // as peças escolhidas (uma do clique, várias do 2D ao lado)
    this.ocultas = new Set();             // peças escondidas pela legenda do Pintar (grupo de perfil ou camada)
    this.emDestaque = false;              // com várias vindas do 2D, o resto do modelo fica esmaecido
    this.corFantasma = [215, 220, 230];
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
    this._uEscuro = { value: 0 };
    const un = () => ({ tPecas: { value: this.textura }, uIdBase: { value: 0 }, uAresta: { value: 0 }, uLonge: this._uLonge,
                        uEscuro: this._uEscuro });
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
    const ponto = this._mat({ PONTO: '' }, false);
    malha.material.uniforms.uIdBase.value = b.id0;
    escolha.uniforms.uIdBase.value = b.id0;
    ponto.uniforms.uIdBase.value = b.id0;
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
    this.malhas.push({ malha, arestas, escolha, ponto, id0: b.id0, n: b.n });
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
    const ponto = this._mat({ INSTANCIA: '', PONTO: '' }, false);
    let arestas = null;
    if (f.arestas.n) {
      arestas = new THREE.LineSegments(geo(this._indice(buf, f.arestas)), this._mat({ INSTANCIA: '' }, true));
      arestas.frustumCulled = false;
      arestas.visible = this.arestasLigadas;
      this.raiz.add(arestas);
    }
    this.raiz.add(malha);
    this.malhas.push({ malha, arestas, escolha, ponto, ids });
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
    this.corMaterial = this.corBase.slice();
    this.modoPintura = 'material';
    this._repintar();
  }

  /**
   * Pinta as peças por 'camada' ou 'perfil' (uma cor por grupo, as mais distintas possível — as
   * camadas de um IFC costumam ter todas o mesmo cinza) ou volta ao 'material'. Devolve a legenda
   * [{nome, cor, n, ids}], do grupo com mais peças para o com menos.
   */
  pintarPor(modo) {
    this.modoPintura = modo;
    this.ocultas = new Set();
    if (modo === 'material' || !this.fichas) {
      this.corBase.set(this.corMaterial);
      this._repintar();
      return [];
    }
    const grupos = new Map();
    for (let i = 0; i < this.fichas.length && i < this.nPecas; i++) {
      const f = this.fichas[i];
      const nome = modo === 'camada' ? ((this.cabecalho.camadas[f.c] || {}).nome || '—') : (f.p || '(sem perfil)');
      let g = grupos.get(nome);
      if (!g) grupos.set(nome, (g = { nome, n: 0, ids: [] }));
      g.n++;
      g.ids.push(i);
    }
    const lista = [...grupos.values()].sort((a, b) => b.n - a.n || a.nome.localeCompare(b.nome));
    const c = new THREE.Color();
    lista.forEach((g, k) => {
      c.setHSL((k * 0.618034) % 1, k % 2 ? 0.5 : 0.62, k % 3 === 2 ? 0.42 : 0.52);
      g.cor = '#' + c.getHexString();
      const r = Math.round(c.r * 255), gg = Math.round(c.g * 255), b = Math.round(c.b * 255);
      for (const i of g.ids) { this.corBase[i * 3] = r; this.corBase[i * 3 + 1] = gg; this.corBase[i * 3 + 2] = b; }
    });
    this._repintar();
    return lista;
  }

  /** Esconde (ou mostra) as peças `ids` (um grupo da legenda do Pintar). */
  ocultarPecas(ids, ocultar) {
    for (const i of ids) { if (ocultar) this.ocultas.add(i); else this.ocultas.delete(i); }
    this._repintar();
  }

  /** Liga ou desliga a camada `i` (índice das camadas do cabeçalho). */
  mostrarCamada(i, visivel) {
    this.visivelCamada[i] = !!visivel;
    this._repintar();
    this.posicionarPiso();
  }

  _movendo(sim) {
    if (this.leveAoGirar === false) return;
    clearTimeout(this._fimMovimento);
    if (sim) {
      if (this._emMovimento) return;
      this._emMovimento = true;
      if (this.dprMovendo !== this.dprParado) { this.renderer.setPixelRatio(this.dprMovendo); this._ajustarTamanho(); }
      for (const m of this.malhas) if (m.arestas) m.arestas.visible = false;
    } else {
      // um instante depois de soltar (o dedo pode voltar logo)
      this._fimMovimento = setTimeout(() => {
        this._emMovimento = false;
        if (this.dprMovendo !== this.dprParado) { this.renderer.setPixelRatio(this.dprParado); this._ajustarTamanho(); }
        for (const m of this.malhas) if (m.arestas) m.arestas.visible = this.arestasLigadas && m.malha.visible;
        this.pedirQuadro();
      }, 120);
    }
  }

  _ajustarTamanho() {
    this.renderer.setSize(this.tela.clientWidth || 1, this.tela.clientHeight || 1, false);
  }

  ligarArestas(sim) {
    this.arestasLigadas = !!sim;
    for (const m of this.malhas) if (m.arestas) m.arestas.visible = this.arestasLigadas && m.malha.visible;
    this.pedirQuadro();
  }

  selecionar(i) {
    this.selecionada = i;
    this.selecaoVarias = new Set(i >= 0 ? [i] : []);
    this.emDestaque = false;
    this._repintar();
  }

  /** Várias peças escolhidas (as que o 2D pediu); `destacar` esmaece o resto, como o editor. */
  selecionarVarias(lista, destacar = true) {
    this.selecaoVarias = new Set(lista);
    this.selecionada = lista.length === 1 ? lista[0] : -1;
    this.emDestaque = !!destacar && lista.length > 0;
    this._repintar();
  }

  /** Aproxima a câmera das peças, mantendo a direção de onde se olha. */
  enquadrarPecas(lista) {
    if (!lista.length || !this.fichas) return;
    const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
    for (const i of lista) {
      const f = this.fichas[i];
      const b = f.b || [f.x[0] - 300, f.x[1] - 300, f.x[2] - 300, f.x[0] + 300, f.x[1] + 300, f.x[2] + 300];
      for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], b[k]); mx[k] = Math.max(mx[k], b[k + 3]); }
    }
    const c = new THREE.Vector3((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2);
    const raio = Math.max(Math.hypot(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]) / 2, 400);
    const dir = this.camera.position.clone().sub(this.controles.target).normalize();
    const vfov = THREE.MathUtils.degToRad(this.camera.fov / 2), hfov = Math.atan(Math.tan(vfov) * this.camera.aspect);
    const dist = raio / Math.sin(Math.min(vfov, hfov)) * 1.15;
    this.controles.target.copy(c);
    this.camera.position.copy(c).addScaledVector(dir, dist);
    this.camera.near = Math.max(dist / 2000, 1);
    this.camera.far = Math.max(this.camera.far, dist * 20);
    this.camera.updateProjectionMatrix();
    this.controles.update();
    this.pedirQuadro();
  }

  _repintar() {
    const d = this.dadosTex, sel = this.selecaoVarias, fant = this.emDestaque ? this.corFantasma : null;
    for (let i = 0; i < this.nPecas; i++) {
      const k = i * 4;
      const vis = this.visivelCamada[this.camadaDe[i]] !== false && !this.ocultas.has(i);
      if (sel.has(i)) { d[k] = 31; d[k + 1] = 122; d[k + 2] = 224; }
      else if (fant) { d[k] = fant[0]; d[k + 1] = fant[1]; d[k + 2] = fant[2]; }
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

  // ---------------------------------------------------------------- ambiente (fundo e piso)

  /** O fundo e um piso sob o modelo (ele não fica solto no vazio), como o Desenho 2D nos dois temas: fundo liso na
   *  cor dele e o piso na mesma cor com só as linhas principais da grade, em volta do modelo (pedido do usuário,
   *  06/10: sem degradê, sem esfumado nas bordas, sem "monte de linha"). Chamado de novo quando o tema muda. */
  definirTema(escuro) {
    this.escuro = !!escuro;
    if (this._uEscuro) this._uEscuro.value = escuro ? 1 : 0;
    if (!this.piso) this._criarPiso();
    const t = escuro ? TEMA_ESCURO : TEMA_CLARO;
    // a saída do renderizador é linear: as cores vão como estão na tela (o .set() comum as escurece)
    this.cena.background = new THREE.Color().setStyle(t.fundo, THREE.LinearSRGBColorSpace);
    const u = this.piso.material.uniforms;
    u.uFundo.value.setStyle(t.fundo, THREE.LinearSRGBColorSpace);
    u.uLinha.value.setStyle(t.linha, THREE.LinearSRGBColorSpace);
    u.uAlfa.value = t.alfa;
    this.corFantasma = escuro ? [46, 54, 66] : [215, 220, 230];
    this.posicionarPiso();
    this._repintar();
  }

  /** O piso: um plano grande até o horizonte, na cor do fundo (a borda não aparece), com as linhas de 10 m de 1 pixel
   *  só em volta do modelo (somem um pouco além dele); longe, quando se juntam, somem cedo em vez de virar moiré.
   *  Só a face de cima: olhando de baixo da linha do piso ele some e não cobre o modelo. */
  _criarPiso() {
    const material = new THREE.ShaderMaterial({
      uniforms: { uFundo: { value: new THREE.Color() }, uLinha: { value: new THREE.Color() }, uAlfa: { value: 0 },
                  uCentro: { value: new THREE.Vector2() }, uRaio: { value: 1e9 } },
      vertexShader: `varying vec2 vXY;
        void main() { vec4 w = modelMatrix * vec4(position, 1.0); vXY = w.xy; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: `uniform vec3 uFundo, uLinha; uniform float uAlfa, uRaio; uniform vec2 uCentro; varying vec2 vXY;
        float grade(float passo) {
          vec2 q = vXY / passo, w = fwidth(q);
          vec2 d = abs(fract(q - 0.5) - 0.5) / max(w, vec2(1e-6));
          return (1.0 - min(min(d.x, d.y), 1.0)) * (1.0 - smoothstep(0.04, 0.15, max(w.x, w.y)));
        }
        void main() {
          float a = grade(10000.0) * uAlfa * (1.0 - smoothstep(uRaio * 0.55, uRaio, distance(vXY, uCentro)));
          gl_FragColor = vec4(mix(uFundo, uLinha, a), 1.0);
        }`,
      depthWrite: false, side: THREE.FrontSide });
    this.piso = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
    this.piso.renderOrder = -1;
    this.piso.raycast = () => {};
    this.cena.add(this.piso);
  }

  /** O piso logo abaixo das peças à vista, maior que elas. */
  posicionarPiso() {
    if (!this.piso || !this.cabecalho) return;
    const cx = this.caixaVisivel();
    const s = cx.getSize(new THREE.Vector3()), c = cx.getCenter(new THREE.Vector3());
    const lado = Math.max(s.x, s.y, 10000) * 40;          // até o horizonte (na cor do fundo, a borda não aparece)
    this.piso.scale.set(lado, lado, 1);
    this.piso.position.set(c.x, c.y, cx.min.z - 10);
    this.piso.material.uniforms.uCentro.value.set(c.x, c.y);
    this.piso.material.uniforms.uRaio.value = Math.max(s.x, s.y) * 0.85 + 15000;
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
    this.camera.far = dist * 60;                            // alcança o chão até o horizonte
    this.camera.updateProjectionMatrix();
    this.controles.target.copy(c);
    this.controles.update();
    this.pedirQuadro();
  }

  /** A câmera em mm do projeto (para o editor abrir com a mesma vista). */
  lerCamera() {
    const o = this.cabecalho.origem;
    const p = this.camera.position, t = this.controles.target;
    return { posicao: [p.x + o[0], p.y + o[1], p.z + o[2]], alvo: [t.x + o[0], t.y + o[1], t.z + o[2]], fov: this.camera.fov };
  }

  definirCamera(c) {
    if (!c || !c.posicao || !c.alvo) return;
    const o = this.cabecalho.origem;
    this.camera.position.set(c.posicao[0] - o[0], c.posicao[1] - o[1], c.posicao[2] - o[2]);
    this.controles.target.set(c.alvo[0] - o[0], c.alvo[1] - o[1], c.alvo[2] - o[2]);
    const dist = this.camera.position.distanceTo(this.controles.target);
    this.camera.near = Math.max(dist / 2000, 1);
    this.camera.far = Math.max(dist * 20, this.camera.far);
    this.camera.updateProjectionMatrix();
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

  /** Desenha só o pixel (x, y) com a variante `qual` das malhas ('escolha' ou 'ponto') e o lê. */
  _pixel(x, y, qual, alvo, saida) {
    const w = this.tela.clientWidth, h = this.tela.clientHeight;
    const fundo = this.cena.background;
    this.cena.background = null;
    const corLimpa = this.renderer.getClearColor(new THREE.Color()), alfaLimpo = this.renderer.getClearAlpha();
    this.renderer.setClearColor(0x000000, 0);
    const trocas = [];
    for (const o of this.cena.children) if (o !== this.raiz && o.visible) { trocas.push([o, true, true]); o.visible = false; }
    for (const m of this.malhas) {
      trocas.push([m.malha, m.malha.material]);
      m.malha.material = m[qual];
      if (m.arestas) { trocas.push([m.arestas, m.arestas.visible, true]); m.arestas.visible = false; }
    }
    const dpr = this.renderer.getPixelRatio();
    this.camera.setViewOffset(w * dpr, h * dpr, Math.round(x * dpr), Math.round(y * dpr), 1, 1);
    this.renderer.setRenderTarget(alvo);
    this.renderer.clear();
    this.renderer.render(this.cena, this.camera);
    this.renderer.readRenderTargetPixels(alvo, 0, 0, 1, 1, saida);
    this.renderer.setRenderTarget(null);
    this.camera.clearViewOffset();
    for (const t of trocas) { if (t[2]) t[0].visible = t[1]; else t[0].material = t[1]; }
    this.renderer.setClearColor(corLimpa, alfaLimpo);
    this.cena.background = fundo;
    this.pedirQuadro();
    return saida;
  }

  /** Número da peça no ponto (x, y) da tela, em pixels CSS; -1 se nenhuma. */
  escolher(x, y) {
    if (!this._alvo) this._alvo = new THREE.WebGLRenderTarget(1, 1);
    const px = this._pixel(x, y, 'escolha', this._alvo, new Uint8Array(4));
    const id = px[0] + px[1] * 256 + px[2] * 65536 - 1;
    return id >= 0 && id < this.nPecas ? id : -1;
  }

  /** O ponto da superfície sob (x, y), em mm do projeto, e a peça; null se não há peça ali. A posição
   *  vem da placa (uma imagem de 1 pixel em ponto flutuante): exata na face, sem guardar triângulos. */
  pontoEm(x, y) {
    const id = this.escolher(x, y);
    if (id < 0) return null;
    if (!this._alvoPonto) {
      if (!this.renderer.extensions.has('EXT_color_buffer_float')) return null;
      this._alvoPonto = new THREE.WebGLRenderTarget(1, 1, { type: THREE.FloatType });
    }
    const v = this._pixel(x, y, 'ponto', this._alvoPonto, new Float32Array(4));
    if (!(v[3] > 0.5)) return null;
    const o = this.cabecalho.origem;
    return { id, ponto: [v[0] + o[0], v[1] + o[1], v[2] + o[2]], local: [v[0], v[1], v[2]] };
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
      m.malha.geometry.dispose(); m.malha.material.dispose(); m.escolha.dispose(); m.ponto.dispose();
      if (m.arestas) { m.arestas.geometry.dispose(); m.arestas.material.dispose(); }
    }
    this.textura.dispose();
    if (this._alvo) this._alvo.dispose();
    if (this._alvoPonto) this._alvoPonto.dispose();
    this.renderer.dispose();
  }
}

/** Depois de enviada à placa, a cópia do trecho na memória do navegador não é mais usada. */
function _soltar() { this.array = null; }
