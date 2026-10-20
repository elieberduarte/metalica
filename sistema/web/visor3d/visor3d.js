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
/** No claro, as cores das camadas puxadas para o branco: o azul-marinho das vigas pesava no fundo claro (06/10). */
const CLAREAR_NO_CLARO = 0.45;
/** A marca das peças escolhidas (como o editor, web/editor3d/nucleo/cena.js): altura na tela, limites. */
const FRACAO_ANEL = 0.07, FRACAO_SETA = 0.06, MAIS_PECAS_COM_ANEL = 20000, MAIS_ANEIS = 40;
/** Peças a menos disto (mm) dividem o anel; a barra comprida e fina (tirante, contravento) ganha uma seta. */
const JUNTAR_ANEIS = 600, BARRA_FINA = 8;
let _texturaDoAnel = null, _texturaDaSeta = null;
/** Vermelho de linha fina com borda branca, para ler no fundo claro e no escuro (06/10: "um círculo com a linha
 *  fina"). Sem conversão: a saída é linear, a cor vai como está. */
function texturaDoAnel() {
  if (_texturaDoAnel) return _texturaDoAnel;
  const n = 128, tela = document.createElement('canvas');
  tela.width = tela.height = n;
  const g = tela.getContext('2d'), r = n / 2 - 6;
  g.lineWidth = 7; g.strokeStyle = 'rgba(255,255,255,0.9)';
  g.beginPath(); g.arc(n / 2, n / 2, r, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 3.5; g.strokeStyle = '#e5322d';
  g.beginPath(); g.arc(n / 2, n / 2, r, 0, Math.PI * 2); g.stroke();
  _texturaDoAnel = new THREE.CanvasTexture(tela);
  return _texturaDoAnel;
}
/** A seta para baixo, com a ponta no pé do desenho (o ponto marcado): na barra fina o anel no meio dela cercava o
 *  vazio (pedido do usuário, 06/10). */
function texturaDaSeta() {
  if (_texturaDaSeta) return _texturaDaSeta;
  const n = 128, tela = document.createElement('canvas');
  tela.width = tela.height = n;
  const g = tela.getContext('2d');
  const seta = () => {
    g.beginPath();
    g.moveTo(64, 6); g.lineTo(64, 96);                       // a haste
    g.moveTo(42, 74); g.lineTo(64, 122); g.lineTo(86, 74);   // a ponta
  };
  g.lineJoin = g.lineCap = 'round';
  seta(); g.lineWidth = 10; g.strokeStyle = 'rgba(255,255,255,0.9)'; g.stroke();
  seta(); g.lineWidth = 4.5; g.strokeStyle = '#e5322d'; g.stroke();
  _texturaDaSeta = new THREE.CanvasTexture(tela);
  return _texturaDaSeta;
}

// A sombra do sol (modo apresentação): a profundidade vista do sol, desenhada uma vez (a obra não se mexe) e refeita só
// quando o que está à vista muda; 3 × 3 amostras para a borda sair macia. O piso usa a mesma.
const SOMBRA_GLSL = /* glsl */`
uniform sampler2D tSombra;
uniform mat4 uMatSombra;
uniform float uTexel;
uniform float uDesloc;
uniform float uTemSombra;
float luzDoSol(vec3 p, vec3 n) {
  if (uTemSombra < 0.5) return 1.0;
  vec4 q = uMatSombra * vec4(p + n * uDesloc, 1.0);
  vec3 s = q.xyz / q.w * 0.5 + 0.5;
  if (s.x < 0.0 || s.x > 1.0 || s.y < 0.0 || s.y > 1.0 || s.z > 1.0) return 1.0;
  float soma = 0.0;
  for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++)
    soma += step(s.z - 0.0015, texture2D(tSombra, s.xy + vec2(float(i), float(j)) * uTexel).r);
  return soma / 9.0;
}`;
// de onde vem o sol: alto (57°), da esquerda e um pouco da frente da vista inicial (a perspectiva do enquadrar), para
// as faces que se veem saírem em tons diferentes e a sombra cair para trás do modelo, no chão à vista
const SOL = [-0.19, -0.71, 1.15];

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
varying vec3 vMundo;
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
  vMundo = mundo;
  vec4 vista = viewMatrix * vec4(mundo, 1.0);
  vVista = vista.xyz;
  gl_Position = projectionMatrix * vista;
  if (c.a < 0.5) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);     // peça escondida: fora da tela
}`;

const FRAG = /* glsl */`
varying vec3 vVista;
varying vec3 vCor;
varying vec3 vMundo;
#ifdef ESCOLHA
flat varying float vId;
#endif
uniform float uAresta;
uniform float uLonge;
uniform float uEscuro;
uniform float uApresenta;
uniform vec3 uSol;
${SOMBRA_GLSL}
void main() {
#if defined(SOMBRA)
  gl_FragColor = vec4(1.0);
#elif defined(PONTO)
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
    vec3 ca = uEscuro > 0.5 ? mix(vCor, vec3(0.94, 0.96, 1.0), 0.55) : vCor * 0.62;   // claro: a paleta mais clara (06/10)
    gl_FragColor = vec4(ca, uEscuro > 0.5 ? a + 0.15 : a); return;
  }
  // no escuro a peça sobe um pouco para o claro (o azul-marinho das vigas sumia no fundo)
  vec3 base = uEscuro > 0.5 ? mix(vCor, vec3(1.0), 0.18) : vCor;
  if (uApresenta > 0.5) {
    // apresentação (20/10): o sol parado no mundo, com sombra; o céu azulado por cima e o chão quente por baixo;
    // um brilho de aço nas faces viradas para o sol
    vec3 nm = normalize(cross(dFdx(vMundo), dFdy(vMundo)));
    vec3 olho = normalize(cameraPosition - vMundo);
    if (dot(nm, olho) < 0.0) nm = -nm;
    float sol = max(dot(nm, uSol), 0.0) * luzDoSol(vMundo, nm);
    vec3 amb = mix(vec3(0.58, 0.56, 0.54), vec3(0.76, 0.81, 0.90), 0.5 + 0.5 * nm.z);
    float brilho = pow(max(dot(nm, normalize(uSol + olho)), 0.0), 48.0) * 0.2 * sol;
    vec3 b = uEscuro > 0.5 ? base : base * 0.86;            // no claro a paleta vem clareada: tira um pouco
    gl_FragColor = vec4(min(b * (0.7 * amb + 0.66 * vec3(1.0, 0.97, 0.92) * sol) + brilho, 1.0), 1.0);
    return;
  }
  vec3 n = normalize(cross(dFdx(vVista), dFdy(vVista)));
  if (n.z < 0.0) n = -n;
  vec3 luz = normalize(vec3(0.35, 0.55, 0.75));
  float d = max(dot(n, luz), 0.0);
  float ceu = 0.5 + 0.5 * n.y;
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
    // o toque é tratado aqui (_toque…), não pelo OrbitControls: um dedo gira em volta da peça tocada, dois dedos
    // aproximam, giram e arrastam em volta do ponto entre eles (celular, 20/10)
    this.controles.touches = { ONE: null, TWO: null };
    this._dedos = new Map();
    this._gesto = null;
    tela.addEventListener('pointerdown', (ev) => this._toqueDesce(ev));
    tela.addEventListener('pointermove', (ev) => this._toqueMove(ev));
    tela.addEventListener('pointerup', (ev) => this._toqueSobe(ev));
    tela.addEventListener('pointercancel', (ev) => this._toqueSobe(ev));
    if (opcoes.mouse) {
      this.controles.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: THREE.MOUSE.PAN };
      this.controles.zoomToCursor = true;
      tela.addEventListener('pointerdown', (ev) => this._orbitarNoCursor(ev), { capture: true });
      tela.addEventListener('wheel', (ev) => this._zoomNaPeca(ev), { capture: true, passive: false });
      tela.addEventListener('pointerdown', (ev) => this._panNoCursor(ev), { capture: true });
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
    this.ocultasSistema = new Set();      // pelo Sistema (pré-moldado / metálica): à parte, vale em todo modo do Pintar
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
    this._luz = this._luz || {
      uApresenta: { value: 0 }, uSol: { value: new THREE.Vector3(...SOL).normalize() }, tSombra: { value: null },
      uMatSombra: { value: new THREE.Matrix4() }, uTexel: { value: 1 / 2048 }, uDesloc: { value: 0 }, uTemSombra: { value: 0 } };
    this._uLonge = { value: 10000 };
    this._uEscuro = { value: 0 };
    const un = () => ({ tPecas: { value: this.textura }, uIdBase: { value: 0 }, uAresta: { value: 0 }, uLonge: this._uLonge,
                        uEscuro: this._uEscuro, ...this._luz });
    this._mat = (defs, aresta) => {
      const sombra = 'SOMBRA' in defs;              // vista do sol: empurrada para trás (sem "acne" nas faces de frente para ele)
      const m = new THREE.ShaderMaterial({ ...comum, uniforms: un(), defines: defs,
        side: THREE.DoubleSide, polygonOffset: !aresta, polygonOffsetFactor: sombra ? 2 : 1, polygonOffsetUnits: sombra ? 4 : 1,
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
    const sombra = this._mat({ SOMBRA: '' }, false);
    malha.material.uniforms.uIdBase.value = b.id0;
    escolha.uniforms.uIdBase.value = b.id0;
    ponto.uniforms.uIdBase.value = b.id0;
    sombra.uniforms.uIdBase.value = b.id0;
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
    this.malhas.push({ malha, arestas, escolha, ponto, sombra, id0: b.id0, n: b.n });
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
    const sombra = this._mat({ INSTANCIA: '', SOMBRA: '' }, false);
    let arestas = null;
    if (f.arestas.n) {
      arestas = new THREE.LineSegments(geo(this._indice(buf, f.arestas)), this._mat({ INSTANCIA: '' }, true));
      arestas.frustumCulled = false;
      arestas.visible = this.arestasLigadas;
      this.raiz.add(arestas);
    }
    this.raiz.add(malha);
    this.malhas.push({ malha, arestas, escolha, ponto, sombra, ids });
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

  /** Esconde (ou mostra) as peças `ids` de um sistema (pré-moldado, metálica…) — não se perde ao trocar o Pintar. */
  ocultarSistema(ids, ocultar) {
    for (const i of ids) { if (ocultar) this.ocultasSistema.add(i); else this.ocultasSistema.delete(i); }
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
    this._marcarDestaque();
  }

  /** A peça clicada e as iguais a ela (a mesma posição), todas marcadas, sem esmaecer o resto (06/10: "mostrar
   *  também o círculo e as outras peças iguais"). */
  selecionarComIguais(i, iguais) {
    this.selecaoVarias = new Set(iguais && iguais.length ? iguais : [i]);
    this.selecionada = i;
    this.emDestaque = false;
    this._repintar();
    this._marcarDestaque();
  }

  /** Várias peças escolhidas (as que o 2D pediu); `destacar` esmaece o resto, como o editor. */
  selecionarVarias(lista, destacar = true) {
    this.selecaoVarias = new Set(lista);
    this.selecionada = lista.length === 1 ? lista[0] : -1;
    this.emDestaque = !!destacar && lista.length > 0;
    this._repintar();
    this._marcarDestaque();
  }

  /** Marca as peças escolhidas (as do 2D ou a clicada com as iguais), por cima do modelo e do mesmo tamanho na tela,
   *  como no editor — a chapa escolhida no 2D, com o prédio inteiro à vista, não se achava (06/10). Peça compacta: um
   *  anel; barra comprida e fina: uma seta no meio dela. Peças coladas (a menos de JUNTAR_ANEIS) dividem o anel, e ele
   *  fica numa delas — antes ia para a média do grupo, às vezes no vazio entre a chapa de cima e a da base, e parecia
   *  não seguir a peça. Escolha grande demais fica sem marca. */
  _marcarDestaque() {
    if (this._marcas) {
      this.cena.remove(this._marcas);
      this._marcas.traverse(o => { if (o.material) o.material.dispose(); });
      this._marcas = null;
    }
    const ids = [...this.selecaoVarias];
    if (!ids.length || ids.length > MAIS_PECAS_COM_ANEL || !this.fichas) { this.pedirQuadro(); return; }
    const aneis = [], setas = [];
    for (const i of ids) {
      const f = this.fichas[i], b = f.b;
      const p = b ? [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2] : [f.x[0], f.x[1], f.x[2]];
      const d = b ? [b[3] - b[0], b[4] - b[1], b[5] - b[2]].sort((x, y) => y - x) : [0, 0, 0];
      if (d[0] > 1500 && d[0] > BARRA_FINA * Math.max(d[1], 1)) setas.push(p);
      else aneis.push(p);
    }
    // junta as coladas, em cadeia; o anel fica na peça do grupo mais perto do meio dele. Peças demais (os 192 chumbadores
    // de uma pendência, 14/10: "não circula as peças, não consegui encontrar"): junta por distância cada vez maior até
    // caberem MAIS_ANEIS anéis — cada anel marca uma região; antes ficava sem marca nenhuma
    const juntar = (pontos, dist) => {
      // por célula de grade (do tamanho da distância): rápido com milhares de peças; vizinhas na mesma célula viram um grupo
      const celulas = new Map();
      for (const p of pontos) {
        const k = `${Math.floor(p[0] / dist)},${Math.floor(p[1] / dist)},${Math.floor(p[2] / dist)}`;
        if (!celulas.has(k)) celulas.set(k, []);
        celulas.get(k).push(p);
      }
      return [...celulas.values()];
    };
    let grupos = [];
    if (aneis.length <= 400) {
      for (const p of aneis) {
        const junto = grupos.filter(g => g.some(o => Math.hypot(o[0] - p[0], o[1] - p[1], o[2] - p[2]) <= JUNTAR_ANEIS));
        grupos = grupos.filter(g => !junto.includes(g));
        grupos.push([p, ...junto.flat()]);
      }
    } else {
      grupos = juntar(aneis, JUNTAR_ANEIS);
    }
    let dist = JUNTAR_ANEIS;
    while (grupos.length + Math.min(setas.length, MAIS_ANEIS / 2) > MAIS_ANEIS && dist < 1e7) {
      dist *= 2;
      grupos = juntar(aneis, dist);
    }
    if (setas.length > MAIS_ANEIS / 2) {
      // setas demais: viram anéis, juntadas com as outras
      grupos = juntar(aneis.concat(setas), dist);
      while (grupos.length > MAIS_ANEIS && dist < 1e7) { dist *= 2; grupos = juntar(aneis.concat(setas), dist); }
      setas.length = 0;
    }
    const naPeca = (g) => {
      const m = [0, 1, 2].map(k => g.reduce((t, o) => t + o[k], 0) / g.length);
      return g.reduce((a, o) => (Math.hypot(o[0] - m[0], o[1] - m[1], o[2] - m[2]) < Math.hypot(a[0] - m[0], a[1] - m[1], a[2] - m[2]) ? o : a));
    };
    this._marcas = new THREE.Group();
    const marca = (p, textura, fracao, ponta) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: textura, depthTest: false, depthWrite: false, transparent: true }));
      s.position.set(p[0], p[1], p[2]);
      if (ponta) s.center.set(0.5, 0.0);           // a ponta da seta (o pé do desenho) no ponto
      s.renderOrder = 999;
      s.raycast = () => {};
      // o mesmo tamanho na tela em qualquer zoom: a altura do que se vê na distância dela
      s.onBeforeRender = (_r, _c, cam) => {
        const alto = 2 * cam.position.distanceTo(s.position) * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
        s.scale.setScalar(Math.max(alto * fracao, 1e-6));
        s.updateMatrixWorld(true);
      };
      this._marcas.add(s);
    };
    for (const g of grupos) marca(naPeca(g), texturaDoAnel(), FRACAO_ANEL, false);
    for (const p of setas) marca(p, texturaDaSeta(), FRACAO_SETA, true);
    this.cena.add(this._marcas);
    this.pedirQuadro();
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
    const k0 = this.escuro ? 0 : CLAREAR_NO_CLARO, cb = this.corBase;
    for (let i = 0; i < this.nPecas; i++) {
      const k = i * 4;
      const vis = this.visivelCamada[this.camadaDe[i]] !== false && !this.ocultas.has(i) && !this.ocultasSistema.has(i);
      if (sel.has(i)) { d[k] = 31; d[k + 1] = 122; d[k + 2] = 224; }
      else if (fant) { d[k] = fant[0]; d[k + 1] = fant[1]; d[k + 2] = fant[2]; }
      else for (let j = 0; j < 3; j++) d[k + j] = cb[i * 3 + j] + (255 - cb[i * 3 + j]) * k0;
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
    this._sombraSuja = true;
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
    if (this._dadosReferencia) this.definirReferencia(this._dadosReferencia);
  }

  /** A planta no chão (arquitetônico, eixos com balões) e os níveis — web/visor3d/referencia.js, carregado só aqui
   *  (o celular serve este arquivo sozinho); nas cores do tema. */
  async definirReferencia(r) {
    this._dadosReferencia = r;
    const { montarReferencia } = await import('./referencia.js');
    if (this.referencia) {
      this.cena.remove(this.referencia);
      this.referencia.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
    }
    this.referencia = r ? montarReferencia(r, { escuro: this.escuro, caixa: this._caixaModelo, zChao: -2 }) : null;
    if (this.referencia) {
      // as peças estão em mm relativos à origem do arquivo (o centro do modelo); a planta vem em mm do projeto
      const o = (this.cabecalho && this.cabecalho.origem) || [0, 0, 0];
      this.referencia.position.set(-o[0], -o[1], -o[2]);
      this.referencia.visible = this._referenciaLigada !== false;
      for (const g of this.referencia.children) g.visible = !(this._partesOcultas && this._partesOcultas.has(g.name));
      this.cena.add(this.referencia);
    }
    this.pedirQuadro();
  }
  ligarReferencia(sim) {
    this._referenciaLigada = !!sim;
    if (this.referencia) this.referencia.visible = !!sim;
    this.pedirQuadro();
  }
  /** As partes da planta no chão que existem neste projeto ('arquitetonico', 'eixos', 'niveis' — referencia.js). */
  partesReferencia() { return this.referencia ? this.referencia.children.map(g => g.name) : []; }
  /** Uma parte da planta no chão como camada (16/10): fica oculta também quando o tema muda e a planta é refeita. */
  mostrarParteReferencia(nome, sim) {
    if (!this._partesOcultas) this._partesOcultas = new Set();
    if (sim) this._partesOcultas.delete(nome); else this._partesOcultas.add(nome);
    const g = this.referencia && this.referencia.getObjectByName(nome);
    if (g) g.visible = !!sim;
    this.pedirQuadro();
  }

  /** O piso: um plano grande até o horizonte, na cor do fundo (a borda não aparece), com as linhas de 10 m de 1 pixel
   *  só em volta do modelo (somem um pouco além dele); longe, quando se juntam, somem cedo em vez de virar moiré.
   *  Só a face de cima: olhando de baixo da linha do piso ele some e não cobre o modelo. */
  _criarPiso() {
    const material = new THREE.ShaderMaterial({
      uniforms: { uFundo: { value: new THREE.Color() }, uLinha: { value: new THREE.Color() }, uAlfa: { value: 0 },
                  uCentro: { value: new THREE.Vector2() }, uRaio: { value: 1e9 }, uEscuro: this._uEscuro || { value: 0 },
                  ...(this._luz || {}) },
      vertexShader: `varying vec2 vXY; varying vec3 vMundo;
        void main() { vec4 w = modelMatrix * vec4(position, 1.0); vXY = w.xy; vMundo = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: `uniform vec3 uFundo, uLinha; uniform float uAlfa, uRaio, uEscuro; uniform vec2 uCentro; varying vec2 vXY; varying vec3 vMundo;
        ${this._luz ? 'uniform float uApresenta; ' + SOMBRA_GLSL : 'float uApresenta = 0.0; float luzDoSol(vec3 p, vec3 n) { return 1.0; }'}
        float grade(float passo) {
          vec2 q = vXY / passo, w = fwidth(q);
          vec2 d = abs(fract(q - 0.5) - 0.5) / max(w, vec2(1e-6));
          return (1.0 - min(min(d.x, d.y), 1.0)) * (1.0 - smoothstep(0.04, 0.15, max(w.x, w.y)));
        }
        void main() {
          float a = grade(10000.0) * uAlfa * (1.0 - smoothstep(uRaio * 0.55, uRaio, distance(vXY, uCentro)));
          vec3 cor = mix(uFundo, uLinha, a);
          if (uApresenta > 0.5) cor *= 1.0 - (uEscuro > 0.5 ? 0.75 : 0.3) * (1.0 - luzDoSol(vMundo, vec3(0.0, 0.0, 1.0)));
          gl_FragColor = vec4(cor, 1.0);
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
    this._sombraSuja = true;
    this.pedirQuadro();
  }

  // ---------------------------------------------------------------- apresentação: sol e sombra

  /** Liga ou desliga o modo apresentação (20/10, para mostrar ao cliente no celular): o sol parado no mundo, a sombra
   *  das peças nelas mesmas e no chão, o céu e o brilho do aço. `resolucao` é o lado da imagem da sombra (o celular usa
   *  2048; mais que isso pesa na memória dele). */
  ligarApresentacao(sim, resolucao) {
    if (!this._luz) return;
    this.apresentacao = !!sim;
    this._luz.uApresenta.value = sim ? 1 : 0;
    if (sim && !this._alvoSombra) {
      const lado = Math.min(resolucao || 2048, this.renderer.capabilities.maxTextureSize);
      this._alvoSombra = new THREE.WebGLRenderTarget(lado, lado, { depthBuffer: true });
      this._alvoSombra.depthTexture = new THREE.DepthTexture(lado, lado);
      this._luz.uTexel.value = 1 / lado;
      this._camSombra = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 2);
      this._camSombra.up.set(0, 0, 1);
    }
    this._luz.tSombra.value = sim ? this._alvoSombra.depthTexture : null;
    this._luz.uTemSombra.value = 0;
    this._sombraSuja = true;
    this.pedirQuadro();
  }

  /** A profundidade vista do sol, numa câmera paralela. De longe pega a obra inteira (e a sombra que cai no chão); de
   *  perto, só a volta do que está na tela — a imagem da sombra cobrindo 200 m deixava cada pixel com 10 cm de obra e a
   *  sombra de uma terça na outra sumia. Refeita ao soltar o dedo (_movendo), não durante o gesto. */
  _recorteSombra() {
    const cx = this.caixaVisivel();
    const raioObra = Math.max(cx.getSize(new THREE.Vector3()).length() / 2, 1000) * 1.15;
    const perto = this.camera.position.distanceTo(this.controles.target) * 1.6;
    const c = perto < raioObra ? this.controles.target.clone() : cx.getCenter(new THREE.Vector3());
    return { c, raio: Math.min(perto, raioObra), raioObra };
  }

  /** O recorte da sombra mudou o bastante (zoom, arrastar, enquadrar, vistas) para refazê-la? */
  _vistaMudou() {
    const a = this._recorteDesenhado;
    if (!a) return true;
    const b = this._recorteSombra();
    return Math.abs(b.raio - a.raio) > 0.15 * a.raio || b.c.distanceTo(a.c) > 0.25 * a.raio;
  }

  _desenharSombra() {
    this._sombraSuja = false;
    const { c, raio, raioObra } = this._recorteDesenhado = this._recorteSombra();
    const cam = this._camSombra, sol = this._luz.uSol.value;
    cam.left = -raio; cam.right = raio; cam.top = raio; cam.bottom = -raio;
    // o sol fica fora da obra inteira, mesmo com o recorte pequeno: a coluna alta fora da tela ainda faz sombra nela
    cam.near = 1; cam.far = raioObra * 4 + raio;
    cam.position.copy(c).addScaledVector(sol, raioObra * 2);
    cam.lookAt(c);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    this._luz.uMatSombra.value.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    this._luz.uDesloc.value = 1.5 * (2 * raio) * this._luz.uTexel.value;     // 1,5 pixel da sombra, ao longo da normal
    const fundo = this.cena.background;
    this.cena.background = null;
    const trocas = [];
    for (const o of this.cena.children) if (o !== this.raiz && o.visible) { trocas.push([o, true, true]); o.visible = false; }
    for (const m of this.malhas) {
      trocas.push([m.malha, m.malha.material]);
      m.malha.material = m.sombra;
      if (m.arestas) { trocas.push([m.arestas, m.arestas.visible, true]); m.arestas.visible = false; }
    }
    this._luz.uTemSombra.value = 0;
    this._luz.tSombra.value = null;                   // a imagem que se desenha não fica ligada como textura ao mesmo tempo
    this.renderer.setRenderTarget(this._alvoSombra);
    this.renderer.clear();
    this.renderer.render(this.cena, cam);
    this.renderer.setRenderTarget(null);
    for (const t of trocas) { if (t[2]) t[0].visible = t[1]; else t[0].material = t[1]; }
    this.cena.background = fundo;
    this._luz.tSombra.value = this._alvoSombra.depthTexture;
    this._luz.uTemSombra.value = 1;
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
    // a vista guardada absurda (número inválido, alvo fora do modelo, câmera a quilômetros) não se repete a cada F5:
    // abre enquadrado (09/10)
    const pos = new THREE.Vector3(c.posicao[0] - o[0], c.posicao[1] - o[1], c.posicao[2] - o[2]);
    const alv = new THREE.Vector3(c.alvo[0] - o[0], c.alvo[1] - o[1], c.alvo[2] - o[2]);
    const esf = this._esferaModelo;
    if (![pos.x, pos.y, pos.z, alv.x, alv.y, alv.z].every(Number.isFinite) || pos.distanceTo(alv) < 1
        || alv.distanceTo(esf.center) > esf.radius * 3 || pos.distanceTo(esf.center) > esf.radius * 40) return;
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
  /** Arrastar sobre uma peça gira em volta do ponto dela sob o cursor, como no editor (camera.js, "como no
   *  SketchUp"): o ponto fica parado na tela e nada pula. O giro do OrbitControls era em volta do alvo, que o zoom no
   *  cursor leva para longe — com a peça selecionada no meio da tela, ela saía de vista (pedido do usuário, 06/10).
   *  Num vão, a peça mais perto em volta do cursor; no vazio, o chão do prédio ou, por último, o alvo da câmera. */
  _orbitarNoCursor(ev) {
    if (ev.pointerType === 'touch' || (ev.button !== 0 && ev.button !== 1) || !this.fichas) return;
    const r = this.tela.getBoundingClientRect();
    // o ponto conferido (dentro do modelo e no raio do cursor): o da placa pode vir errado e o giro em volta dele levava
    // o modelo embora (09/10). Num vão, a peça mais perto em volta; sem nenhuma, o chão do prédio sob o cursor (15/10)
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    const pivo = this._focoSeguro(x, y) || this._focoPerto(x, y) || this._focoNoVazio(x, y);
    if (!pivo) return;
    this.controles.enableRotate = false;
    let ultimo = { x: ev.clientX, y: ev.clientY }, mexeu = false;
    const mover = (e) => {
      const dx = e.clientX - ultimo.x, dy = e.clientY - ultimo.y;
      ultimo = { x: e.clientX, y: e.clientY };
      if (!dx && !dy) return;
      if (!mexeu) { mexeu = true; this._movendo(true); }
      this._girarEmVolta(pivo, dx, dy);
    };
    const soltar = () => {
      window.removeEventListener('pointermove', mover, true);
      window.removeEventListener('pointerup', soltar, true);
      window.removeEventListener('pointercancel', soltar, true);
      this.controles.enableRotate = true;
      if (mexeu) this._movendo(false);
    };
    window.addEventListener('pointermove', mover, true);
    window.addEventListener('pointerup', soltar, true);
    window.addEventListener('pointercancel', soltar, true);
  }

  /** A rodinha aproxima da peça que está sob o cursor, como no editor (camera.js, _zoomNaRoda): o passo é uma fração
   *  da distância até ela, e não até o alvo da câmera — com o alvo a 30 m e a viga a 1 m, o passo de 1,5 m do
   *  OrbitControls atravessava a viga e a câmera ia parar dentro da peça (o BRAMAIS "bugava inteiro" ao dar zoom,
   *  09/10). Chega a 30 mm da peça e não passa; o plano de corte de perto acompanha. Sem peça sob o cursor (o céu, o
   *  chão vazio), fica o zoom do OrbitControls. */
  _zoomNaPeca(ev) {
    if (!this.fichas || !ev.deltaY) return;
    const r = this.tela.getBoundingClientRect();
    const foco = this._focoSeguro(ev.clientX - r.left, ev.clientY - r.top) || this._focoNoVazio(ev.clientX - r.left, ev.clientY - r.top);
    ev.preventDefault();
    ev.stopImmediatePropagation();
    const cliques = Math.max(-5, Math.min(5, ev.deltaY / (ev.deltaMode === 1 ? 3 : ev.deltaMode === 2 ? 1 : 100)));
    const k = Math.pow(0.85, -cliques);                // < 1 aproxima, > 1 afasta
    const cam = this.camera, alvo = this.controles.target;
    const d = Math.max(cam.position.distanceTo(foco), 1e-6);
    const nova = Math.min(Math.max(d * k, 30), this.camera.far / 4);
    const fator = nova / d;
    if (Math.abs(fator - 1) < 1e-6) return;
    cam.position.sub(foco).multiplyScalar(fator).add(foco);
    alvo.sub(foco).multiplyScalar(fator).add(foco);
    // o plano de corte de perto menor que a distância até a peça, senão ela é cortada ao chegar perto
    const perto = Math.max(1, Math.min(cam.near, nova / 20));
    if (perto !== cam.near) { cam.near = perto; cam.updateProjectionMatrix(); }
    this.controles.update();
    this.pedirQuadro();
  }

  /** O ponto da peça sob (x, y) em que a rodinha mira, conferido: o da placa (`pontoEm`) só vale dentro da caixa do
   *  modelo e sobre o raio do cursor — a placa de vídeo integrada pode devolver lixo na imagem em ponto flutuante, e
   *  um ponto a quilômetros mandava a câmera para longe num clique (o BRAMAIS "sumia" ao primeiro giro, 09/10). Sem
   *  ele, a entrada do raio na caixa da peça (conta nossa, sem a placa); sem peça, null. */
  _focoSeguro(x, y) {
    const id = this.escolher(x, y);
    if (id < 0) return null;
    const ndc = new THREE.Vector2(x / Math.max(this.tela.clientWidth, 1) * 2 - 1, -(y / Math.max(this.tela.clientHeight, 1)) * 2 + 1);
    const raio = new THREE.Raycaster();
    this.camera.updateMatrixWorld();
    raio.setFromCamera(ndc, this.camera);
    const caixa = this._caixaModelo.clone().expandByScalar(this._esferaModelo.radius * 0.1 + 1000);
    let achado = null;
    try { achado = this.pontoEm(x, y); } catch (e) { achado = null; }
    if (achado) {
      const p = new THREE.Vector3(achado.local[0], achado.local[1], achado.local[2]);
      const d = this.camera.position.distanceTo(p);
      if (Number.isFinite(d) && caixa.containsPoint(p) && raio.ray.distanceToPoint(p) <= Math.max(0.02 * d, 50)) return p;
      if (!this._avisouPonto && window.__registrarLento) {
        // uma vez: o ponto da placa fora do lugar, com a placa de vídeo, para o registro do servidor
        this._avisouPonto = true;
        let placa = '?';
        try { const g = this.renderer.getContext(), x = g.getExtension('WEBGL_debug_renderer_info'); placa = x ? g.getParameter(x.UNMASKED_RENDERER_WEBGL) : '?'; } catch (e) { /* sem a extensão */ }
        try { window.__registrarLento({ tipo: 'erro', mensagem: 'ponto da placa fora do lugar no zoom (' + placa + '): ' + achado.local.map(Math.round).join(', '), onde: 'visor3d' }); } catch (e) { /* sem registro */ }
      }
    }
    const f = this.fichas[id], b = f && f.b;
    const caixaPeca = b ? new THREE.Box3(new THREE.Vector3(b[0], b[1], b[2]), new THREE.Vector3(b[3], b[4], b[5])).expandByScalar(5)
                        : new THREE.Box3().setFromCenterAndSize(new THREE.Vector3(f.x[0], f.x[1], f.x[2]), new THREE.Vector3(600, 600, 600));
    const p = raio.ray.intersectBox(caixaPeca, new THREE.Vector3());
    return p && caixa.containsPoint(p) ? p : null;
  }

  /** Num vão entre as peças (a treliça e os tirantes da Kaefer do engenheiro, 15/10: "gira em torno do ponto errado" —
   *  o cursor caía entre as barras e o giro ia para o alvo da câmera, no meio do prédio), o apoio como no editor
   *  (camera.js, _pecaPertoDoCursor): a peça mais perto da câmera no quadrado de 2·meio px em volta do cursor (um
   *  desenho só, em n × n pontos) dá a profundidade, e o ponto fica no raio do cursor (a tela não pula). null sem peça
   *  em volta (ou sem imagem em ponto flutuante na placa). */
  _focoPerto(x, y, meio = 200, n = 100) {
    if (!this.renderer.extensions.has('EXT_color_buffer_float')) return null;
    if (!this._alvoBloco) this._alvoBloco = new THREE.WebGLRenderTarget(n, n, { type: THREE.FloatType });
    const v = this._pixel(x, y, 'ponto', this._alvoBloco, new Float32Array(n * n * 4), meio, n);
    const cam = this.camera;
    cam.updateMatrixWorld();
    const dirVista = cam.getWorldDirection(new THREE.Vector3());
    const caixa = this._caixaModelo.clone().expandByScalar(this._esferaModelo.radius * 0.1 + 1000);
    const p = new THREE.Vector3();
    let melhor = Infinity;
    for (let i = 0; i < n * n; i++) {
      if (!(v[4 * i + 3] > 0.5)) continue;
      p.set(v[4 * i], v[4 * i + 1], v[4 * i + 2]);
      if (!caixa.containsPoint(p)) continue;               // o ponto da placa fora do lugar (09/10): não vale
      const d = p.sub(cam.position).dot(dirVista);
      if (d > 0 && d < melhor) melhor = d;
    }
    if (!Number.isFinite(melhor)) return null;
    const W = this.tela.clientWidth, H = this.tela.clientHeight;
    const raio = new THREE.Raycaster();
    raio.setFromCamera(new THREE.Vector2(x / Math.max(W, 1) * 2 - 1, -(y / Math.max(H, 1)) * 2 + 1), cam);
    const cos = Math.max(raio.ray.direction.dot(dirVista), 1e-3);
    return raio.ray.origin.clone().addScaledVector(raio.ray.direction, melhor / cos);
  }

  /** O pan do botão direito "agarra" o ponto sob o cursor (a peça ou o chão; no vazio, o plano do alvo): ele acompanha
   *  o mouse exatamente, perto ou longe. O do OrbitControls anda pela distância até o alvo — depois do zoom na peça o
   *  alvo vem junto e o pan quase parava (09/10). */
  _panNoCursor(ev) {
    if (ev.pointerType === 'touch' || ev.button !== 2 || !this.fichas) return;
    const r = this.tela.getBoundingClientRect();
    const x0 = ev.clientX - r.left, y0 = ev.clientY - r.top;
    const profundo = this._focoSeguro(x0, y0) || this._focoPerto(x0, y0) || this._focoNoVazio(x0, y0);
    if (!profundo) return;
    const cam = this.camera;
    const plano = new THREE.Plane().setFromNormalAndCoplanarPoint(cam.getWorldDirection(new THREE.Vector3()), profundo);
    const raio = new THREE.Raycaster();
    const noPlano = (cx, cy) => {
      const ndc = new THREE.Vector2(cx / Math.max(this.tela.clientWidth, 1) * 2 - 1, -(cy / Math.max(this.tela.clientHeight, 1)) * 2 + 1);
      cam.updateMatrixWorld();
      raio.setFromCamera(ndc, cam);
      return raio.ray.intersectPlane(plano, new THREE.Vector3());
    };
    // o ponto agarrado é o do cursor, na profundidade achada: no vazio o último recurso é o alvo da câmera, no meio da
    // tela, e agarrá-lo fazia o modelo pular para baixo do mouse no primeiro movimento (16/10, verif_camera_modelos F)
    const ancora = noPlano(x0, y0) || profundo;
    const antes = this.controles.enablePan;
    this.controles.enablePan = false;
    let mexeu = false;
    const mover = (e) => {
      const q = noPlano(e.clientX - r.left, e.clientY - r.top);
      if (!q) return;
      const d = ancora.clone().sub(q);
      if (d.lengthSq() < 1e-10) return;
      if (!mexeu) { mexeu = true; this._movendo(true); }
      cam.position.add(d);
      this.controles.target.add(d);
      this.controles.update();
      this.pedirQuadro();
    };
    const soltar = () => {
      window.removeEventListener('pointermove', mover, true);
      window.removeEventListener('pointerup', soltar, true);
      window.removeEventListener('pointercancel', soltar, true);
      this.controles.enablePan = antes;
      if (mexeu) this._movendo(false);
    };
    window.addEventListener('pointermove', mover, true);
    window.addEventListener('pointerup', soltar, true);
    window.addEventListener('pointercancel', soltar, true);
  }

  /** Sem peça sob o cursor, o foco do zoom como no editor (camera.js, _focoDoCursor): o chão do modelo (a cota mais
   *  baixa) sob o cursor, se está perto; senão o alvo da câmera. O zoom do OrbitControls no vazio levava a câmera para
   *  longe (09/10, "se o mouse está no vazio ele vai pra muito longe"). */
  _focoNoVazio(x, y) {
    const ndc = new THREE.Vector2(x / Math.max(this.tela.clientWidth, 1) * 2 - 1, -(y / Math.max(this.tela.clientHeight, 1)) * 2 + 1);
    const raio = new THREE.Raycaster();
    this.camera.updateMatrixWorld();
    raio.setFromCamera(ndc, this.camera);
    const alvo = this.controles.target;
    const limite = Math.max(this.camera.position.distanceTo(alvo), this._esferaModelo.radius) * 3;
    const chao = new THREE.Plane(new THREE.Vector3(0, 0, 1), -this._caixaModelo.min.z);
    const p = new THREE.Vector3();
    // o chão só dentro da planta do prédio (com folga): perto do horizonte o raio cai no chão a centenas de metros e o
    // zoom levava a câmera para lá
    const cx = this._caixaModelo, folga = this._esferaModelo.radius * 0.25;
    if (raio.ray.intersectPlane(chao, p) && p.distanceTo(this.camera.position) <= limite
        && p.x >= cx.min.x - folga && p.x <= cx.max.x + folga && p.y >= cx.min.y - folga && p.y <= cx.max.y + folga) return p;
    return alvo.clone();
  }

  /** Gira câmera e alvo juntos em volta de `pivo` (em volta do Z e do eixo horizontal da tela), na velocidade do
   *  OrbitControls; não passa do zênite. */
  _girarEmVolta(pivo, dx, dy) {
    const k = (2 * Math.PI / Math.max(this.tela.clientHeight || 1, 1)) * this.controles.rotateSpeed;
    const cam = this.camera, alvo = this.controles.target;
    const cima = new THREE.Vector3(0, 0, 1);
    const dir = alvo.clone().sub(cam.position).normalize();
    const direita = new THREE.Vector3().crossVectors(dir, cima);
    const q = new THREE.Quaternion().setFromAxisAngle(cima, -dx * k);
    if (direita.lengthSq() > 1e-10) {
      const qx = new THREE.Quaternion().setFromAxisAngle(direita.normalize(), -dy * k);
      const junto = q.clone().multiply(qx);
      const nova = dir.clone().applyQuaternion(junto);
      const polar = Math.acos(Math.max(-1, Math.min(1, nova.dot(cima))));
      if (polar > 0.02 && polar < Math.PI - 0.02) q.copy(junto);
    }
    for (const v of [cam.position, alvo]) v.sub(pivo).applyQuaternion(q).add(pivo);
    cam.lookAt(alvo);
    cam.updateMatrixWorld();
    this.controles.update();
    this.controles.dispatchEvent({ type: 'change' });
  }

  // ---------------------------------------------------------------- toque (celular)
  // Pedido do usuário (20/10, ME SOORO no celular): dois dedos giram "como se o eixo estivesse no meio dos dois
  // pontos"; de perto, o giro de um dedo andava demais e os eixos se misturavam. O OrbitControls girava sempre em volta
  // do alvo da câmera, na mesma velocidade perto ou longe, e a pinça mirava o alvo, não os dedos.

  /** Um dedo desce: o giro espera o dedo andar (um toque parado escolhe a peça, celular.js); com dois, o gesto de dois
   *  dedos começa de onde eles estão. */
  _toqueDesce(ev) {
    if (ev.pointerType !== 'touch' || !this.fichas) return;
    this._dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    this._recomecarGesto();
  }

  _toqueSobe(ev) {
    if (!this._dedos.delete(ev.pointerId)) return;
    if (this._dedos.size) { this._recomecarGesto(); return; }
    if (this._gesto && this._gesto.mexeu) this._movendo(false);
    this._gesto = null;
  }

  /** O gesto recomeça a cada dedo que desce ou sobe, dos lugares de agora (nada pula na troca de um para dois). */
  _recomecarGesto() {
    const mexeu = !!(this._gesto && this._gesto.mexeu);
    const [a, b] = [...this._dedos.values()];
    if (!b) { this._gesto = { dedos: 1, x0: a.x, y0: a.y, pivo: null, mexeu, media: { x: 0, y: 0 } }; return; }
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const r = this.tela.getBoundingClientRect();
    this._gesto = { dedos: 2, mexeu, pivo: this._pivoDoToque(mx - r.left, my - r.top),
                    dist: Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1), ang: Math.atan2(b.y - a.y, b.x - a.x),
                    torcao: 0, girando: false };
  }

  /** O ponto em volta do qual o gesto gira e aproxima: a peça sob o dedo (ou entre os dedos); num vão, a peça mais
   *  perto em volta; no vazio, o chão do prédio ou o alvo — como o mouse do modo ver. */
  _pivoDoToque(x, y) {
    return this._focoSeguro(x, y) || this._focoPerto(x, y) || this._focoNoVazio(x, y);
  }

  _toqueMove(ev) {
    const dedo = this._dedos.get(ev.pointerId), g = this._gesto;
    if (!dedo || !g) return;
    let ax = dedo.x, ay = dedo.y;
    dedo.x = ev.clientX; dedo.y = ev.clientY;
    if (g.dedos === 2) { this._doisDedos(g); return; }
    if (!g.pivo) {
      if (Math.hypot(dedo.x - g.x0, dedo.y - g.y0) <= 8) return;          // ainda pode ser um toque
      const r = this.tela.getBoundingClientRect();
      g.pivo = this._pivoDoToque(g.x0 - r.left, g.y0 - r.top);
      if (!g.pivo) return;
      ax = g.x0; ay = g.y0;
    }
    let dx = dedo.x - ax, dy = dedo.y - ay;
    if (!dx && !dy) return;
    if (!g.mexeu) { g.mexeu = true; this._movendo(true); }
    // os eixos não se misturam: arrastando de lado, o tremor do dedo para cima/baixo não inclina a vista (e vice-versa);
    // na diagonal, gira nos dois
    g.media.x = 0.7 * g.media.x + 0.3 * dx;
    g.media.y = 0.7 * g.media.y + 0.3 * dy;
    if (Math.abs(g.media.x) > 2.5 * Math.abs(g.media.y)) dy = 0;
    else if (Math.abs(g.media.y) > 2.5 * Math.abs(g.media.x)) dx = 0;
    const f = this._giroDePerto(g.pivo);
    this._girarEmVolta(g.pivo, dx * f, dy * f);
  }

  /** De perto, o giro anda mais devagar: com o modelo inteiro na tela, a velocidade de sempre; a uma fração do tamanho
   *  do modelo de distância (olhando uma ligação), até 30 % dela. */
  _giroDePerto(pivo) {
    const raio = Math.max(this._esferaModelo.radius, 1);
    return Math.min(1, Math.max(0.3, Math.sqrt(this.camera.position.distanceTo(pivo) / (1.5 * raio))));
  }

  /** Dois dedos: abrir/fechar aproxima do ponto entre eles, torcer gira em volta da vertical que passa por ele, arrastar
   *  leva o ponto junto — ele fica sempre no meio dos dedos. */
  _doisDedos(g) {
    if (!g.pivo) return;
    const [a, b] = [...this._dedos.values()];
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const dist = Math.max(Math.hypot(b.x - a.x, b.y - a.y), 1), ang = Math.atan2(b.y - a.y, b.x - a.x);
    let da = ang - g.ang;
    if (da > Math.PI) da -= 2 * Math.PI; else if (da < -Math.PI) da += 2 * Math.PI;
    const k = g.dist / dist;                                  // < 1 aproxima, > 1 afasta
    g.ang = ang; g.dist = dist;
    // a torção só conta depois de ~6°: na pinça os dedos sempre torcem um pouco
    if (!g.girando) {
      g.torcao += da;
      if (Math.abs(g.torcao) < 0.1) da = 0;
      else { g.girando = true; da = g.torcao - Math.sign(g.torcao) * 0.1; }
    }
    if (!g.mexeu) { g.mexeu = true; this._movendo(true); }
    const cam = this.camera, alvo = this.controles.target, P = g.pivo;
    // torcer no sentido do relógio (na tela) gira o modelo no mesmo sentido: a câmera vai no sentido contrário
    if (da) {
      const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), da);
      for (const v of [cam.position, alvo]) v.sub(P).applyQuaternion(q).add(P);
    }
    // a pinça: como a rodinha (_zoomNaPeca), chega a 30 mm do ponto e não passa
    const d = Math.max(cam.position.distanceTo(P), 1e-6);
    const fator = Math.min(Math.max(d * k, 30), cam.far / 4) / d;
    cam.position.sub(P).multiplyScalar(fator).add(P);
    alvo.sub(P).multiplyScalar(fator).add(P);
    const perto = Math.max(1, Math.min(cam.near, d * fator / 20));
    if (perto !== cam.near) { cam.near = perto; cam.updateProjectionMatrix(); }
    cam.lookAt(alvo);
    cam.updateMatrixWorld();
    // o ponto volta para o meio dos dedos
    const r = this.tela.getBoundingClientRect();
    const ndc = new THREE.Vector2((mx - r.left) / Math.max(this.tela.clientWidth, 1) * 2 - 1, -((my - r.top) / Math.max(this.tela.clientHeight, 1)) * 2 + 1);
    const raio = new THREE.Raycaster();
    raio.setFromCamera(ndc, cam);
    const plano = new THREE.Plane().setFromNormalAndCoplanarPoint(cam.getWorldDirection(new THREE.Vector3()), P);
    const Q = raio.ray.intersectPlane(plano, new THREE.Vector3());
    if (Q) { const desl = P.clone().sub(Q); cam.position.add(desl); alvo.add(desl); }
    this.controles.update();
    this.controles.dispatchEvent({ type: 'change' });
  }

  centrarEm(i) {
    const f = this.fichas && this.fichas[i];
    if (!f) return;
    // o meio da caixa da peça (o x da ficha é a origem dela: na barra comprida, uma ponta)
    const b = f.b;
    const alvo = b ? new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2) : new THREE.Vector3(f.x[0], f.x[1], f.x[2]);
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
    if (this._pedido || this._descartado) return;
    this._pedido = true;
    requestAnimationFrame(() => {
      this._pedido = false;
      if (this._descartado) return;
      // a sombra é refeita quando o que está à vista muda, ou quando a vista muda o bastante — nunca no meio do gesto
      if (this.apresentacao && this.cabecalho && (this._sombraSuja || (!this._emMovimento && this._vistaMudou()))) this._desenharSombra();
      this.renderer.render(this.cena, this.camera);
      this.quadros++;
    });
  }

  // ---------------------------------------------------------------- escolha pelo toque

  /** Desenha só o pixel (x, y) com a variante `qual` das malhas ('escolha' ou 'ponto') e o lê. Com `meio` (px CSS), o
   *  quadrado de lado 2·meio em volta de (x, y), desenhado no alvo inteiro (n × n) e lido todo. */
  _pixel(x, y, qual, alvo, saida, meio = 0, n = 1) {
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
    const lado = meio ? Math.round(2 * meio * dpr) : 1;
    this.camera.setViewOffset(w * dpr, h * dpr, Math.round((x - meio) * dpr), Math.round((y - meio) * dpr), lado, lado);
    this.renderer.setRenderTarget(alvo);
    this.renderer.clear();
    this.renderer.render(this.cena, this.camera);
    this.renderer.readRenderTargetPixels(alvo, 0, 0, n, n, saida);
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
  /** O meio da peça na tela (o meio da caixa dela; o x da ficha é a origem, na barra uma ponta). */
  paraTela(i) {
    const f = this.fichas[i], b = f.b;
    this.camera.updateMatrixWorld();                  // a câmera pode ter mudado depois do último quadro
    const p = (b ? new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
                 : new THREE.Vector3(f.x[0], f.x[1], f.x[2])).project(this.camera);
    return [(p.x + 1) / 2 * this.tela.clientWidth, (1 - p.y) / 2 * this.tela.clientHeight, p.z];
  }

  // ---------------------------------------------------------------- números

  numeros() {
    const info = this.renderer.info;
    return { chamadas: info.render.calls, triangulos: info.render.triangles, geometrias: info.memory.geometries,
             pecas: this.nPecas, objetos: this.malhas.length };
  }

  descartar() {
    // o quadro pedido e o fim do gesto ainda por vir não desenham mais (20/10, celular: sair do 3D e voltar — o visor
    // descartado redesenhava a sombra da apresentação com as malhas já fora da placa e os arrays soltos: TypeError em
    // createBuffer, e a ficha não abria ao tocar a peça no 3D novo)
    this._descartado = true;
    clearTimeout(this._fimMovimento);
    window.removeEventListener('resize', this._redimensionar);
    this.controles.dispose();
    for (const m of this.malhas) {
      m.malha.geometry.dispose(); m.malha.material.dispose(); m.escolha.dispose(); m.ponto.dispose();
      if (m.sombra) m.sombra.dispose();
      if (m.arestas) { m.arestas.geometry.dispose(); m.arestas.material.dispose(); }
    }
    if (this._alvoSombra) { this._alvoSombra.depthTexture.dispose(); this._alvoSombra.dispose(); }
    this.textura.dispose();
    if (this._alvo) this._alvo.dispose();
    if (this._alvoPonto) this._alvoPonto.dispose();
    if (this._alvoBloco) this._alvoBloco.dispose();
    this.renderer.dispose();
  }
}

/** Depois de enviada à placa, a cópia do trecho na memória do navegador não é mais usada. */
function _soltar() { this.array = null; }
