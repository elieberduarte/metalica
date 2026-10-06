// A cena Three.js: luzes, grade, eixos e a representação de cada entidade.
//
// A cena é derivada do documento, nunca o contrário. Quando o documento avisa que algo
// mudou, só os ids afetados são reconstruídos.
//
// Unidades: o documento está em milímetros; a cena trabalha em metros (ESCALA). Um
// galpão de 40 m tem 40 000 mm, e manter isso no buffer de profundidade custaria
// precisão. Tudo o que representa o modelo mora dentro de `raiz`, que já carrega a
// escala — as ferramentas continuam falando em milímetros.
//
// Malhas de barra e chapa: o Python é quem sabe gerar a seção correta de cada perfil,
// então elas são pedidas ao servidor e guardadas em cache por perfil e comprimento.
// Enquanto a resposta não chega — ou quando `nucleo3d/geometria.py` ainda não existe —
// a seção é montada aqui mesmo a partir das dimensões do catálogo, para que o modelo
// apareça na hora.

import * as THREE from 'three';
import { Lote, LIMITE_LOTE } from './lote.js';
import { Documento, baseDaBarra, normalizar, produtoVetorial,
         comprimentoDaBarra, normalDaChapa, arestasSoltasDe } from './documento.js';

/** Subtipo de um sólido anotado pelas ferramentas: 'cota', 'construcao', ''. */
const tipoDe = (ent) => (ent && ent.atributos && ent.atributos.tipo) || '';

/** Metros de cena por milímetro de documento. */
export const ESCALA = 0.001;

/** Cor cheia da peça em destaque (a escolhida no 2D, a achada na busca): o azul da seleção misturado à cor
 *  dela sumia no cinza do resto, no tema claro (30/09). */
export const COR_DESTAQUE = '#ff5a1f';
export const COR_DESTAQUE_ARESTA = '#8a2400';
/** Anéis em volta das peças em destaque: até tantas peças e tantos grupos; o diâmetro, em fração da altura
 *  da tela. */
const MAIS_PECAS_COM_ANEL = 400;
const MAIS_ANEIS = 40;
const FRACAO_ANEL = 0.075;

let _texturaDoAnel = null;
/** O anel: vermelho com borda branca por dentro e por fora, para ler no fundo claro e no escuro. */
function texturaDoAnel() {
  if (_texturaDoAnel) return _texturaDoAnel;
  const n = 128;
  const tela = document.createElement('canvas');
  tela.width = tela.height = n;
  const g = tela.getContext('2d');
  const r = n / 2 - 6;
  // linha fina (06/10: "pode ser um círculo com a linha fina")
  g.lineWidth = 7; g.strokeStyle = 'rgba(255,255,255,0.9)';
  g.beginPath(); g.arc(n / 2, n / 2, r, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 3.5; g.strokeStyle = '#e5322d';
  g.beginPath(); g.arc(n / 2, n / 2, r, 0, Math.PI * 2); g.stroke();
  _texturaDoAnel = new THREE.CanvasTexture(tela);
  _texturaDoAnel.colorSpace = THREE.SRGBColorSpace;
  return _texturaDoAnel;
}

/**
 * Operações pesadas medidas (as últimas 40), para Ver → Diagnóstico de desempenho dizer
 * o que travou a tela. Uma travada de segundos não aparece na média de quadros: aparece
 * aqui, com nome e duração.
 */
export const PESADOS = [];
// também em window, para os verificadores de tela lerem sem mexer no editor
try { window.__pesados = PESADOS; } catch (e) { /* fora do navegador */ }

// Qualquer travada acima de 250 ms entra aqui, mesmo sem nome: assim o diagnóstico
// mostra que houve travada mesmo quando ela veio de um ponto ainda não medido.
try {
  if (typeof PerformanceObserver !== 'undefined') {
    new PerformanceObserver((lista) => {
      for (const e of lista.getEntries()) {
        if (e.duration < 250) continue;
        PESADOS.push({ nome: 'travada não identificada', ms: Math.round(e.duration), quando: Date.now() });
        if (PESADOS.length > 40) PESADOS.shift();
      }
    }).observe({ entryTypes: ['longtask'] });
  }
} catch (e) { /* navegador sem PerformanceObserver de tarefas longas */ }

export function medir(nome, fn) {
  const t0 = performance.now();
  try {
    return fn();
  } finally {
    const ms = performance.now() - t0;
    if (ms >= 60) {
      PESADOS.push({ nome, ms: Math.round(ms), quando: Date.now() });
      if (PESADOS.length > 40) PESADOS.shift();
    }
  }
}

/** Acima de tantos objetos a sombra sai sozinha: o mapa de sombra desenha o modelo
 *  inteiro uma segunda vez a cada quadro (medido: 152 ms → 49 ms por quadro num IFC de
 *  5 mil peças). */
export const LIMITE_SOMBRAS = 1500;

export const MODOS = [
  ['sombreado', 'Sombreado'],
  ['sombreado_arestas', 'Sombreado com arestas'],
  ['arestas', 'Só arestas'],
  ['raiox', 'Raio-X'],
];

const CORES_EIXO = { x: 0xc0392b, y: 0x2e8b57, z: 0x2a63c8 };

// Peça sem valor no mapa de esforços: cinza neutro e apagado, para não competir com as
// coloridas. Uma por tema, porque o mesmo cinza que some no claro berra no escuro.
const CINZA_SEM_VALOR = { claro: '#aeb6c2', escuro: '#4e5766' };
/** Quanto da peça sem valor continua visível quando o mapa de esforços está ligado. */
const OPACIDADE_SEM_VALOR = 0.3;

// Densidade da grade em pixels de tela. O passo desce de década quando as linhas
// finas fecham além de PX_GRADE_MIN e sobe quando passam de PX_GRADE_MAX — a folga
// entre os dois é o que impede a grade de trocar de escala a cada clique da roda.
// Entre MIN e CHEIA as linhas finas vão aparecendo aos poucos, para a troca não pular.
// O piso (03/10/2026: "essa malha do piso dos modelos 3D confunde um pouco a visualização"): no lugar de linhas
// de ponta a ponta, um plano só, desenhado pela placa de vídeo — tom neutro e discreto que some em degradê em volta
// do ponto para onde se olha (sem borda nem "rede" no horizonte), e a grade com as linhas suavizadas pelo próprio
// pixel (fwidth): de longe ou de lado elas se apagam sozinhas, sem o efeito de malha. Ver › Estilo › Piso escolhe
// grade suave, piso liso ou nenhum (guardado no navegador).
const PISO_VERTEX = `
varying vec2 vMundo;
void main() {
  vec4 m = modelMatrix * vec4(position, 1.0);
  vMundo = m.xy;
  gl_Position = projectionMatrix * viewMatrix * m;
}`;
const PISO_FRAGMENT = `
uniform float uPasso; uniform float uOpFina; uniform vec2 uCentro; uniform float uRaio;
uniform vec3 uCorPiso; uniform float uAlfaPiso; uniform vec3 uCorLinha; uniform float uAlfaLinhas;
varying vec2 vMundo;
float linha(vec2 p, float passo, float largura) {
  vec2 c = p / passo;
  vec2 w = fwidth(c);
  vec2 g = abs(fract(c - 0.5) - 0.5) / max(w, 1e-5);
  float l = 1.0 - min(min(g.x, g.y) / largura, 1.0);
  // densa demais na tela (longe ou de lado): some, em vez de virar moiré
  return l * (1.0 - smoothstep(0.18, 0.45, max(w.x, w.y)));
}
void main() {
  float d = length(vMundo - uCentro);
  float fade = 1.0 - smoothstep(uRaio * 0.2, uRaio, d);
  float fina = linha(vMundo, uPasso, 1.0) * uOpFina * 0.55;
  float forte = linha(vMundo, uPasso * 10.0, 1.3);
  float l = max(fina, forte) * uAlfaLinhas;
  vec3 cor = mix(uCorPiso, uCorLinha, clamp(l * 1.6, 0.0, 1.0));
  float a = fade * clamp(uAlfaPiso + l * 0.7, 0.0, 1.0);
  if (a < 0.003) discard;
  gl_FragColor = vec4(cor, a);
}`;
const MODOS_PISO = ['grade', 'liso', 'nenhum'];
/** O fundo do Desenho 2D (web/cad/nucleo/tela.js): o 3D usa o mesmo, liso. */
const FUNDO_2D = { escuro: '#0e131a', claro: '#f4f6fa' };

const PX_GRADE_MIN = 8;
const PX_GRADE_ALVO = 14;
const PX_GRADE_CHEIA = 26;
const PX_GRADE_MAX = 110;

export class Cena {
  /**
   * @param canvas  o <canvas> do editor
   * @param doc     o Documento (fonte de verdade)
   * @param opcoes  { api, escuro }
   */
  constructor(canvas, doc, opcoes = {}) {
    this.canvas = canvas;
    this.documento = doc || new Documento();
    this.api = opcoes.api || null;
    this.escuro = !!opcoes.escuro;
    this.catalogo = { perfis: new Map() };
    this.modo = 'sombreado_arestas';
    this.sombras = 'auto';                 // 'auto' | true | false (Ver → Sombras)
    this._sombrasAtivas = true;
    this.usarServidor = true;         // desligado sozinho se o servidor não puder ajudar
    this.avisoServidor = '';

    // Cor vinda de fora (mapa de esforços). Enquanto as duas forem nulas, a cena pinta
    // exatamente como sempre pintou — quem constrói o mapa não muda nada só por existir.
    this.corPorValor = null;          // (entidade) => '#rrggbb' | null
    this.mapaCores = null;            // Map<id, '#rrggbb'>, alternativa à função

    this.objetos = new Map();         // id da entidade -> THREE.Group
    this.lote = null;                 // sólidos em lote (modelo grande): ver lote.js
    this.semLote = !!opcoes.semLote;  // força um objeto por peça (teste e comparação)
    this.cacheGeometria = new Map();  // chave (perfil|comprimento) -> BufferGeometry
    this.origemGeometria = new Map(); // mesma chave -> 'servidor' | 'local'
    this.cacheMaterial = new Map();
    this._pendentes = new Set();      // ids esperando refino do servidor
    // Texto das cotas: {ponto (mm), texto} por id. O editor desenha em HTML por cima
    // do canvas, para ficar legível em qualquer zoom e nas duas projeções.
    this.rotulos = new Map();
    this._pedidoAgendado = null;

    this._montarRenderizador();
    this._montarCena();

    this.planoCorte = null;           // {origem, normal} em mm, ou null
    this.planosCorte = [];            // o mesmo, já como THREE.Plane em metros

    this.desinscrever = this.documento.aoMudar(({ ids, acao }) => {
      if (acao === 'aparencia') this.repintarTudo();
      else if (acao === 'tudo' || !ids || !ids.length) this.reconstruirTudo();
      else this.atualizar(ids);
    });
  }

  get renderer() { return this.renderizador; }

  /**
   * Plano de corte (ferramenta Seção). Fica visível o lado para onde a normal
   * aponta — é o que a seta desenhada pela ferramenta indica. Só o modelo é cortado;
   * grade, eixos e prévias continuam inteiros.
   */
  definirPlanoCorte(dado) {
    this.planoCorte = dado ? { origem: dado.origem.slice(), normal: dado.normal.slice() } : null;
    if (dado) {
      const n = new THREE.Vector3(...dado.normal).normalize();
      const o = new THREE.Vector3(...dado.origem).multiplyScalar(ESCALA);
      this.planosCorte = [new THREE.Plane(n, -n.dot(o))];
    } else {
      this.planosCorte = [];
    }
    this.cacheMaterial.clear();
    if (this.lote) this.lote.aplicarCorte(this.planosCorte);
    for (const id of this.objetos.keys()) this._pintar(id);
    if (this.aoRepintar) this.aoRepintar();
    this.pedirQuadro();
  }

  // ------------------------------------------------------------ montagem

  _montarRenderizador() {
    this.renderizador = new THREE.WebGLRenderer({
      canvas: this.canvas, antialias: true, alpha: false,
      preserveDrawingBuffer: true,       // permite captura de tela do canvas
    });
    this.renderizador.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderizador.shadowMap.enabled = true;
    this.renderizador.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderizador.outputColorSpace = THREE.SRGBColorSpace;
    this.renderizador.localClippingEnabled = true;     // plano de corte por material
  }

  _montarCena() {
    this.cena = new THREE.Scene();
    this.cena.background = this._fundoGradiente();

    // Luz do céu mais uma direcional: leitura de volume sem contraste teatral.
    this.luzAmbiente = new THREE.HemisphereLight(
      this.escuro ? 0x2c3a52 : 0xdfe8f5,
      this.escuro ? 0x0d1219 : 0x5a6172,
      this.escuro ? 1.5 : 2.1);
    this.cena.add(this.luzAmbiente);

    this.luzSol = new THREE.DirectionalLight(0xffffff, 2.2);
    this.luzSol.position.set(28, -34, 46);
    this.luzSol.castShadow = true;
    this.luzSol.shadow.mapSize.set(2048, 2048);
    this.luzSol.shadow.radius = 3;
    this.luzSol.shadow.bias = -0.0012;
    const c = this.luzSol.shadow.camera;
    c.near = 1; c.far = 400; c.left = -80; c.right = 80; c.top = 80; c.bottom = -80;
    this.cena.add(this.luzSol);
    this.cena.add(this.luzSol.target);

    // Segunda direcional fraca, sem sombra, para o lado escuro não virar mancha.
    this.luzPreenchimento = new THREE.DirectionalLight(0xc9d7ee, 0.55);
    this.luzPreenchimento.position.set(-30, 22, 14);
    this.cena.add(this.luzPreenchimento);

    this.grade = new THREE.Group();
    this.grade.name = 'grade';
    this.cena.add(this.grade);
    let modo = 'grade';
    try { modo = localStorage.getItem('metalica.piso3d') || 'grade'; } catch { /* sem armazenamento */ }
    this.modoPiso = MODOS_PISO.includes(modo) ? modo : 'grade';
    this.piso = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShaderMaterial({
      vertexShader: PISO_VERTEX, fragmentShader: PISO_FRAGMENT, transparent: true, depthWrite: false,
      uniforms: {
        uPasso: { value: 1 }, uOpFina: { value: 0.75 }, uCentro: { value: new THREE.Vector2(0, 0) }, uRaio: { value: 30 },
        uCorPiso: { value: new THREE.Color() }, uAlfaPiso: { value: 0.5 }, uCorLinha: { value: new THREE.Color() }, uAlfaLinhas: { value: 1 },
      },
    }));
    this.piso.name = 'piso';
    this.piso.renderOrder = -10;
    this.piso.position.z = -0.001;
    this.grade.add(this.piso);
    this._dirCamera = new THREE.Vector3();

    this.eixos = new THREE.Group();
    this.eixos.name = 'eixos';
    this.cena.add(this.eixos);

    this.chao = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.ShadowMaterial({ opacity: this.escuro ? 0.28 : 0.16 }));
    this.chao.receiveShadow = true;
    this.chao.position.z = -0.002;
    this.cena.add(this.chao);

    // Tudo o que vem do documento mora aqui, já na escala do milímetro.
    this.raiz = new THREE.Group();
    this.raiz.name = 'modelo';
    this.raiz.scale.setScalar(ESCALA);
    this.cena.add(this.raiz);

    // Desenhos temporários das ferramentas, também em milímetros.
    this.previa = new THREE.Group();
    this.previa.name = 'previa';
    this.raiz.add(this.previa);

    this._construirEixos(20);
    this._construirGrade(30, 1);
  }

  /** O fundo liso na cor do Desenho 2D (web/cad/nucleo/tela.js), como no modo ver: sem degradê (06/10). */
  _fundoGradiente() {
    return new THREE.Color(this.escuro ? FUNDO_2D.escuro : FUNDO_2D.claro);
  }

  /** Um fundo desenhado num <canvas> (o degradê de estúdio das imagens da proposta, ?render=1). */
  fundoDeCanvas(c) {
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }

  /** Troca a paleta quando o tema muda. */
  aplicarTema(escuro) {
    if (this.escuro === !!escuro) return;
    this.escuro = !!escuro;
    if (this.cena.background && this.cena.background.dispose) this.cena.background.dispose();
    this.cena.background = this._fundoGradiente();
    this.chao.material.opacity = this.escuro ? 0.28 : 0.16;
    this.luzAmbiente.color.set(this.escuro ? 0x2c3a52 : 0xdfe8f5);
    this.luzAmbiente.groundColor.set(this.escuro ? 0x0d1219 : 0x5a6172);
    this.luzAmbiente.intensity = this.escuro ? 1.5 : 2.1;
    this._construirGrade(this._gradeExtensao || 30, this._gradePasso || 1);
    this.cacheMaterial.clear();
    for (const id of this.objetos.keys()) this._pintar(id);
    if (this.aoRepintar) this.aoRepintar();
    this.pedirQuadro();
  }

  // --------------------------------------------------------- grade e eixos

  /** Grade do plano de trabalho: o passo acompanha o zoom, como no CAD.
   *
   * O passo vem da densidade na tela, e não da distância crua: uma linha fina a cada
   * `passo`, uma grossa a cada dez. A troca de década tem folga (as finas fecham até
   * PX_GRADE_MIN e abrem até PX_GRADE_MAX) e elas somem por transparência conforme
   * fecham, de modo que a troca não apareça. Antes disso, um clique da roda perto do
   * limiar trocava a grade de 10 m para 1 m e de volta, refazendo grade, eixos e
   * câmera de sombra: a cena piscava enquanto o usuário aproximava.
   *
   * @param distancia   distância da câmera ao alvo, em metros de cena
   * @param mmPorPixel  milímetros do modelo por pixel de tela (`Camera.mmPorPixel`)
   */
  ajustarGradeAoZoom(distancia, mmPorPixel = null) {
    const mpp = mmPorPixel ? mmPorPixel / 1000
      : Math.max(distancia, 1) * 0.77 / Math.max(this.canvas.clientHeight || 900, 1);
    let passo = this._gradePasso || Math.pow(10, Math.ceil(Math.log10(mpp * PX_GRADE_ALVO)));
    while (passo / mpp < PX_GRADE_MIN && passo < 1e4) passo *= 10;
    while (passo / mpp > PX_GRADE_MAX && passo > 1e-3) passo /= 10;
    const opacidade = 0.75 * Math.max(0, Math.min(
      1, (passo / mpp - PX_GRADE_MIN) / (PX_GRADE_CHEIA - PX_GRADE_MIN)));

    const alvo = Math.max(20, Math.ceil(distancia * 2.2 / (passo * 10)) * passo * 10);
    let extensao = this._gradeExtensao || alvo;
    // a extensão cresce quando falta grade e só encolhe quando sobra muito; a folga
    // evita refazer a grade inteira a cada clique da roda
    if (passo !== this._gradePasso || alvo > extensao * 1.25 || alvo < extensao * 0.45) {
      extensao = alvo;
    }
    if (passo === this._gradePasso && extensao === this._gradeExtensao) {
      this._opacidadeGradeFina(opacidade);
      return;
    }
    this._construirGrade(extensao, passo, opacidade);
    // os eixos: referência da origem, curtos e apagados (não uma régua até o horizonte)
    this._construirEixos(Math.min(Math.max(3, extensao * 0.12), 30));
  }

  /** Só a transparência das linhas finas, sem refazer a grade. */
  _opacidadeGradeFina(opacidade) {
    this._gradeOpacidadeFina = opacidade;
    const u = this.piso.material.uniforms.uOpFina;
    if (Math.abs(u.value - opacidade) < 0.005) return;
    u.value = opacidade;
    this.pedirQuadro();
  }

  /** Ver › Estilo › Piso: 'grade' (suave), 'liso' (só o tom do piso) ou 'nenhum'. */
  definirPiso(modo) {
    if (!MODOS_PISO.includes(modo)) return this.modoPiso;
    this.modoPiso = modo;
    try { localStorage.setItem('metalica.piso3d', modo); } catch { /* sem armazenamento */ }
    this._aplicarModoPiso();
    this.pedirQuadro();
    return modo;
  }

  _aplicarModoPiso() {
    if (!this.piso) return;
    this.piso.visible = this.modoPiso !== 'nenhum';
    this.piso.material.uniforms.uAlfaLinhas.value = this.modoPiso === 'grade' ? 1 : 0;
  }

  _construirGrade(extensao, passo, opacidadeFina = null) {
    this._gradeExtensao = extensao;
    this._gradePasso = passo;
    if (opacidadeFina === null) opacidadeFina = this._gradeOpacidadeFina;
    if (opacidadeFina === null || opacidadeFina === undefined) opacidadeFina = 0.75;
    this._gradeOpacidadeFina = opacidadeFina;
    this._matGradeFina = null;
    const u = this.piso.material.uniforms;
    u.uPasso.value = passo;
    u.uOpFina.value = opacidadeFina;
    u.uRaio.value = Math.max(12, extensao * 0.62);
    // o piso na cor do fundo (some no horizonte sem borda nem esfumado) e as linhas na da grade do 2D: a principal é a
    // grade10 dele (branco a 13% no escuro, azul-marinho a 12% no claro) já misturada ao fundo (06/10). O shader do
    // piso escreve a cor crua (sem a conversão de saída): as cores vão como estão na tela, senão o piso sai mais
    // escuro que o fundo
    u.uCorPiso.value.setStyle(this.escuro ? FUNDO_2D.escuro : FUNDO_2D.claro, THREE.LinearSRGBColorSpace);
    u.uCorLinha.value.setStyle(this.escuro ? '#2d3238' : '#d9dce3', THREE.LinearSRGBColorSpace);
    u.uAlfaPiso.value = this.escuro ? 0.62 : 0.65;
    this._aplicarModoPiso();
    this.piso.scale.set(extensao * 2, extensao * 2, 1);
    this.chao.scale.set(extensao * 2.4, extensao * 2.4, 1);
    const sombra = Math.max(40, extensao * 0.9);
    const sc = this.luzSol.shadow.camera;
    sc.left = -sombra; sc.right = sombra; sc.top = sombra; sc.bottom = -sombra;
    sc.far = sombra * 6;
    sc.updateProjectionMatrix();
    this.luzSol.position.set(sombra * 0.7, -sombra * 0.85, sombra * 1.15);
  }

  _construirEixos(tamanho) {
    for (const f of this.eixos.children.slice()) {
      this.eixos.remove(f);
      f.geometry.dispose(); f.material.dispose();
    }
    const eixo = (a, b, cor, tracejado) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute([...a, ...b], 3));
      const m = tracejado
        ? new THREE.LineDashedMaterial({ color: cor, dashSize: tamanho / 40,
                                         gapSize: tamanho / 40, transparent: true,
                                         opacity: 0.15, depthWrite: false })
        // só de referência: apagado, para não disputar com a estrutura
        : new THREE.LineBasicMaterial({ color: cor, transparent: true, opacity: 0.35,
                                        depthWrite: false });
      const l = new THREE.Line(g, m);
      if (tracejado) l.computeLineDistances();
      l.renderOrder = -5;
      this.eixos.add(l);
    };
    const t = tamanho;
    eixo([0, 0, 0], [t, 0, 0], CORES_EIXO.x, false);
    eixo([0, 0, 0], [-t, 0, 0], CORES_EIXO.x, true);
    eixo([0, 0, 0], [0, t, 0], CORES_EIXO.y, false);
    eixo([0, 0, 0], [0, -t, 0], CORES_EIXO.y, true);
    eixo([0, 0, 0], [0, 0, t * 0.7], CORES_EIXO.z, false);
    eixo([0, 0, 0], [0, 0, -t * 0.2], CORES_EIXO.z, true);
  }

  // ------------------------------------------------------------- sombras

  /** Sombras ligadas agora? */
  get sombrasAtivas() { return this._sombrasAtivas; }

  /** Desligadas por serem muitas peças (e não por escolha do usuário)? */
  get sombrasDesligadasPeloTamanho() { return this.sombras === 'auto' && !this._sombrasAtivas; }

  /** `true`, `false` ou 'auto' (desliga acima de LIMITE_SOMBRAS objetos). */
  definirSombras(valor) {
    this.sombras = valor === 'auto' ? 'auto' : !!valor;
    this._ajustarSombras(true);
    return this._sombrasAtivas;
  }

  _ajustarSombras(forcar = false) {
    const querido = this.sombras === 'auto' ? this.objetos.size <= LIMITE_SOMBRAS : this.sombras;
    if (!forcar && querido === this._sombrasAtivas) return;
    this._sombrasAtivas = querido;
    this.renderizador.shadowMap.enabled = querido;
    if (this.luzSol) this.luzSol.castShadow = querido;
    this.raiz.traverse(o => { if (o.isMesh) { o.castShadow = querido; o.receiveShadow = querido; } });
    if (this.chao) this.chao.receiveShadow = querido;
    if (this.lote) this.lote.definirSombras(querido);
    // o programa de sombreamento muda: os materiais precisam recompilar
    for (const m of this.cacheMaterial.values()) m.needsUpdate = true;
    this.cena.traverse(o => {
      if (!o.material) return;
      (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.needsUpdate = true; });
    });
    this.pedirQuadro();
  }

  // ------------------------------------------------------ modo de exibição

  definirModo(modo) {
    if (!MODOS.some(m => m[0] === modo)) return;
    this.modo = modo;
    if (this.lote) this.lote.aplicarModo(modo);
    this.cacheMaterial.clear();
    for (const id of this.objetos.keys()) this._pintar(id);
    if (this.aoRepintar) this.aoRepintar();
    this.pedirQuadro();
  }

  // ------------------------------------------------------- cor vinda de fora

  /**
   * Pinta cada peça por um valor calculado fora da cena (o mapa de esforços).
   *
   * `fn(entidade)` devolve '#rrggbb' ou null; quem não tem valor fica no cinza neutro
   * e apagado, para não competir com as coloridas. Não é um modo de exibição novo: a
   * cor entra pelo `_corDe`, que é por onde malha, arestas, linhas soltas e o realce da
   * seleção já passam — então o que está selecionado continua com a cor de seleção.
   *
   * `definirCorPorValor(null)` devolve as cores de material e camada.
   */
  definirCorPorValor(fn) {
    this.corPorValor = typeof fn === 'function' ? fn : null;
    this._repintarPorValor();
  }

  /** Mesma coisa, com um `Map<id, '#rrggbb'>` pronto no lugar da função. */
  definirMapaCores(mapa) {
    this.mapaCores = mapa instanceof Map && mapa.size ? mapa : null;
    this._repintarPorValor();
  }

  /** Está pintando por valor? (a cena continua normal enquanto ninguém pediu) */
  get pintandoPorValor() { return !!(this.mapaCores || this.corPorValor); }

  /** Cor de valor de uma entidade, ou null quando ela não tem valor. */
  _corDeValor(ent) {
    if (!ent) return null;
    if (this.mapaCores) {
      const c = this.mapaCores.get(ent.id);
      if (c) return c;
    }
    if (this.corPorValor) {
      // Um erro dentro do mapa não pode deixar a cena sem pintar.
      try {
        const c = this.corPorValor(ent);
        if (typeof c === 'string' && c) return c;
      } catch (e) {
        console.warn('cor por valor falhou para', ent.id, e);
      }
    }
    return null;
  }

  _repintarPorValor() {
    // A chave do cacheMaterial já inclui a cor, mas ela mudou para os mesmos ids:
    // limpar é o jeito de não servir o material antigo.
    this.cacheMaterial.clear();
    for (const id of this.objetos.keys()) this._pintar(id);
    if (this.aoRepintar) this.aoRepintar();     // reaplica a seleção por cima
    this.pedirQuadro();
  }

  // ------------------------------------------------ construção das entidades

  reconstruirTudo() {
    return medir('montar o modelo na tela', () => this._reconstruirTudo());
  }

  _reconstruirTudo() {
    for (const [id, obj] of this.objetos) this._descartarObjeto(obj);
    this.objetos.clear();
    this.rotulos.clear();
    if (this.lote) { this.lote.descartar(); this.lote = null; }
    this.raiz.children = this.raiz.children.filter(c => c === this.previa);
    // Modelo grande: sólidos em lote (poucas chamadas de desenho). O pequeno continua
    // com um objeto por peça, que é o caminho que todas as ferramentas conhecem.
    if (!this.semLote && this.documento.tamanho > LIMITE_LOTE) this.lote = new Lote(this);
    this.atualizar([...this.documento.entidades.keys()]);
  }

  /** Os sólidos estão em lote? (o editor mostra na barra de estado) */
  get emLote() { return !!this.lote; }

  /** Reconstrói apenas as entidades pedidas (sem lista: só redesenha). */
  atualizar(ids = []) {
    if (ids.length > 200) return medir(`refazer ${ids.length} peças na tela`, () => this._atualizar(ids));
    return this._atualizar(ids);
  }

  _atualizar(ids = []) {
    const paraLote = [];
    for (const id of ids) {
      const ent = this.documento.get(id);
      const antigo = this.objetos.get(id);
      if (antigo) { this.raiz.remove(antigo); this._descartarObjeto(antigo); this.objetos.delete(id); }
      this.rotulos.delete(id);
      if (!ent) continue;
      if (!this.documento.aparece(ent)) continue;
      if (this.lote && Lote.aceita(ent)) { paraLote.push(ent); continue; }
      const obj = this._construirEntidade(ent);
      if (obj) { this.objetos.set(id, obj); this.raiz.add(obj); }
    }
    if (paraLote.length) {
      // Um grupo vazio por peça mantém a contabilidade (`objetos`) e faz o código de um
      // objeto por peça não achar malha nenhuma — e portanto não mexer.
      this.lote.definirVarios(paraLote);
      for (const ent of paraLote) {
        const proxy = new THREE.Group();
        proxy.name = ent.id;
        proxy.userData.entidade = ent.id;
        proxy.userData.lote = true;
        // a chave da geometria (barra, chapa) continua aqui: é por ela que o refino do
        // servidor sabe o que ainda está com a seção local
        const it = this.lote.itens.get(ent.id);
        proxy.userData.chave = it ? it.chave : null;
        this.objetos.set(ent.id, proxy);
      }
    }
    if (this.lote) this.lote.concluir();
    // Objeto recém-construído nasce sem destaque. Quando a reconstrução vem de dentro
    // da cena (malhas do servidor chegando), o documento não avisa ninguém — então a
    // seleção precisa ser reaplicada daqui, senão o que estava selecionado apaga.
    if (ids.length && this.aoRepintar) this.aoRepintar();
    this._ajustarSombras();
    this._agendarRefino();
    this.pedirQuadro();
  }

  /** Refaz só a visibilidade e a cor, sem tocar na geometria (camadas, materiais). */
  repintarTudo() {
    for (const [id, obj] of this.objetos) {
      const ent = this.documento.get(id);
      obj.visible = !!ent && this.documento.aparece(ent);
      if (obj.userData.lote && this.lote) this.lote.mostrar(id, obj.visible);
      this._pintar(id);
    }
    if (this.lote) this.lote.concluir();
    // Entidades que estavam escondidas e voltaram ainda não têm objeto.
    const faltando = [];
    for (const [id, ent] of this.documento.entidades) {
      if (!this.objetos.has(id) && this.documento.aparece(ent)) faltando.push(id);
    }
    if (faltando.length) this.atualizar(faltando);
    if (this.aoRepintar) this.aoRepintar();
    this.pedirQuadro();
  }

  _construirEntidade(ent) {
    let geom = null, matriz = null, chave = null, linhas = null;
    try {
      if (ent.tipo === 'barra') ({ geom, matriz, chave } = this._geometriaBarra(ent));
      else if (ent.tipo === 'chapa') ({ geom, matriz, chave } = this._geometriaChapa(ent));
      else if (ent.tipo === 'solido') {
        ({ geom, matriz } = this._geometriaSolido(ent));
        linhas = this._linhasSoltas(ent);
      }
      else return null;
    } catch (e) {
      console.warn('geometria falhou para', ent.id, e);
      return null;
    }
    // Um sólido sem faces (linha, arco, cota) é só as suas linhas — e precisa aparecer.
    if (!geom && !linhas) return null;

    const grupo = new THREE.Group();
    grupo.name = ent.id;
    grupo.userData.entidade = ent.id;
    grupo.userData.chave = chave || null;
    if (matriz) { grupo.matrixAutoUpdate = false; grupo.matrix.copy(matriz); grupo.matrixWorldNeedsUpdate = true; }

    if (geom) {
      const malha = new THREE.Mesh(geom, this._materialDe(ent));
      malha.castShadow = true;
      malha.receiveShadow = true;
      malha.userData.entidade = ent.id;
      malha.name = 'malha';
      grupo.add(malha);

      const arestas = new THREE.LineSegments(
        obterArestas(geom, !!chave), this._materialArestas(ent));
      arestas.name = 'arestas';
      arestas.userData.entidade = ent.id;
      arestas.raycast = () => {};           // bordas de face não entram no raycast
      grupo.add(arestas);
    }
    if (linhas) grupo.add(linhas);          // linhas soltas entram: são o objeto

    if (tipoDe(ent) === 'cota') {
      const vs = ent.vertices || [];
      const c = (ent.atributos && ent.atributos.cota) || {};
      // Vértices 2 e 3 são as pontas da linha de cota (ferramentas/cotar.js).
      const ponto = vs.length >= 4
        ? [(vs[2][0] + vs[3][0]) / 2, (vs[2][1] + vs[3][1]) / 2, (vs[2][2] + vs[3][2]) / 2]
        : centroDe(vs);
      if (ponto) this.rotulos.set(ent.id, { ponto, texto: c.texto || ent.nome || '' });
    }

    this._aplicarModo(grupo);
    return grupo;
  }

  _descartarObjeto(obj) {
    if (!obj) return;
    if (obj.userData.lote) { if (this.lote) this.lote.remover(obj.userData.entidade); return; }
    obj.traverse(f => {
      // As geometrias de barra e chapa são compartilhadas pelo cache: não descarte.
      if (f.geometry && f.geometry.userData && f.geometry.userData.emCache !== true) {
        f.geometry.dispose();
      }
    });
  }

  // ---- geometria de cada tipo ----

  _geometriaBarra(b) {
    if (temCorteNoAngulo(b)) {
      const cortada = this._geometriaBarraCortada(b);
      if (cortada) return cortada;
    }
    const L = comprimentoDaBarra(b);
    const util = Math.max(1, L - (b.recorte_inicio || 0) - (b.recorte_fim || 0));
    const chave = `barra|${b.perfil}|${util.toFixed(2)}`;
    let geom = this.cacheGeometria.get(chave);
    if (!geom) {
      geom = extrudar(this._secaoDoPerfil(b.perfil), util);
      geom.userData.emCache = true;
      this.cacheGeometria.set(chave, geom);
      this.origemGeometria.set(chave, 'local');
    }
    const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao);
    const o = [b.inicio[0] + t[0] * (b.recorte_inicio || 0),
               b.inicio[1] + t[1] * (b.recorte_inicio || 0),
               b.inicio[2] + t[2] * (b.recorte_inicio || 0)];
    const m = new THREE.Matrix4().makeBasis(vet(u), vet(v), vet(t));
    m.setPosition(o[0], o[1], o[2]);
    return { geom, matriz: m, chave };
  }

  /** A barra com corte no ângulo (`cortes_inicio`/`cortes_fim`, o encaixe de fábrica): a mesma
   *  receita de `geometria._prisma_cortado` no Python, no triedro da barra com a origem no
   *  início. A chave leva as alturas das pontas: peças com o mesmo corte dividem a malha. */
  _geometriaBarraCortada(b) {
    const base = baseDaBarra(b.inicio, b.fim, b.rotacao);
    const [f0, f1] = alturasDeCorte(b, base);
    const chave = `barra|${b.perfil}|corte|` + [f0, f1].map(fs => fs.map(f =>
      `${f[0].toFixed(5)},${f[1].toFixed(5)},${f[2].toFixed(2)}`).join(';')).join('|');
    let geom = this.cacheGeometria.get(chave);
    if (!geom) {
      geom = prismaCortado(this._secaoDoPerfil(b.perfil), f0, f1);
      if (!geom) return null;               // o corte comeria a peça (barra mexida depois): ponta reta
      geom.userData.emCache = true;
      this.cacheGeometria.set(chave, geom);
      this.origemGeometria.set(chave, 'local');
    }
    const m = new THREE.Matrix4().makeBasis(vet(base.u), vet(base.v), vet(base.t));
    m.setPosition(b.inicio[0], b.inicio[1], b.inicio[2]);
    return { geom, matriz: m, chave };
  }

  _geometriaChapa(ch) {
    const contorno = ch.contorno || [];
    if (contorno.length < 3) return { geom: null, matriz: null };
    const chave = `chapa|${ch.espessura}|${contorno.map(p => p.join()).join(';')}|` +
                  (ch.furos || []).map(f => `${f.x},${f.y},${f.diametro || ''},${f.largura || ''},${f.altura || ''},${f.angulo || ''}`).join(';');
    let geom = this.cacheGeometria.get(chave);
    if (!geom) {
      const forma = new THREE.Shape(contorno.map(p => new THREE.Vector2(p[0], p[1])));
      for (const f of (ch.furos || [])) {
        const r = (f.diametro || 0) / 2;
        const furo = new THREE.Path();
        if (r > 0) {
          furo.absarc(f.x || 0, f.y || 0, r, 0, Math.PI * 2, true);
        } else if ((f.largura || 0) > 0 && (f.altura || 0) > 0) {
          // oblongo: dois semicírculos ligados por retas (o Path liga os arcos sozinho)
          let larg = f.largura, alt = f.altura, ang = (f.angulo || 0) * Math.PI / 180;
          if (alt > larg) { [larg, alt] = [alt, larg]; ang += Math.PI / 2; }
          const rr = alt / 2, m = (larg - alt) / 2, ca = Math.cos(ang), sa = Math.sin(ang), x0 = f.x || 0, y0 = f.y || 0;
          furo.absarc(x0 + m * ca, y0 + m * sa, rr, ang + Math.PI / 2, ang - Math.PI / 2, true);
          furo.absarc(x0 - m * ca, y0 - m * sa, rr, ang - Math.PI / 2, ang - 3 * Math.PI / 2, true);
        } else continue;
        forma.holes.push(furo);
      }
      geom = extrudar(forma, ch.espessura || 1);
      geom.userData.emCache = true;
      this.cacheGeometria.set(chave, geom);
      this.origemGeometria.set(chave, 'local');
    }
    const n = normalDaChapa(ch);
    const m = new THREE.Matrix4().makeBasis(vet(ch.eixo_x), vet(ch.eixo_y), vet(n));
    const d = ch.centrada === false ? 0 : -(ch.espessura || 0) / 2;
    m.setPosition(ch.origem[0] + n[0] * d, ch.origem[1] + n[1] * d, ch.origem[2] + n[2] * d);
    return { geom, matriz: m, chave };
  }

  _geometriaSolido(s) {
    // Sólidos são editados a cada movimento do mouse: tesselados aqui, sem cache.
    const vs = s.vertices || [], fs = s.faces || [];
    if (!vs.length || !fs.length) return { geom: null, matriz: null };
    const pos = [];
    for (const f of fs) {
      if (f.length < 3 || f.some(i => !vs[i])) continue;
      // Face desenhada à mão pode ser côncava (um L): o leque sairia para fora dela.
      const tris = f.length <= 4 ? leque(f.length) : triangularFace(f.map(i => vs[i]));
      for (const t of tris) for (const k of t) { const p = vs[f[k]]; pos.push(p[0], p[1], p[2]); }
    }
    if (!pos.length) return { geom: null, matriz: null };
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    return { geom: g, matriz: new THREE.Matrix4() };
  }

  /**
   * Linhas que não são borda de face — polilinha, arco, cota, linha de construção —
   * como LineSegments em milímetros. Entram no raycast (a seleção usa um limiar em
   * pixels). A linha de construção sai tracejada, com o traço proporcional ao
   * comprimento, para ser lida como guia em qualquer zoom.
   */
  _linhasSoltas(ent) {
    const pares = arestasSoltasDe(ent);
    if (!pares.length) return null;
    const vs = ent.vertices;
    const pos = new Float32Array(pares.length * 6);
    let total = 0;
    pares.forEach(([a, b], i) => {
      pos.set(vs[a], i * 6);
      pos.set(vs[b], i * 6 + 3);
      total += Math.hypot(vs[b][0] - vs[a][0], vs[b][1] - vs[a][1], vs[b][2] - vs[a][2]);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const obj = new THREE.LineSegments(g, this._materialLinhas(ent));
    if (tipoDe(ent) === 'construcao') {
      obj.computeLineDistances();
      const d = g.getAttribute('lineDistance');
      const k = 30 / Math.max(total, 1);          // ~30 traços na linha inteira
      for (let i = 0; i < d.count; i++) d.setX(i, d.getX(i) * k);
      d.needsUpdate = true;
    }
    obj.name = 'linhas';
    obj.userData.entidade = ent.id;
    obj.renderOrder = 2;
    return obj;
  }

  _materialLinhas(ent) {
    if (this.destaque && !this.destaque.has(ent.id)) return this._materialFantasmaLinha();
    const tipo = tipoDe(ent);
    const base = this._corDe(ent);
    const cor = tipo === 'construcao' ? (this.escuro ? '#9aa4b2' : '#5d6a7e')
              : tipo === 'cota' ? base
              : misturar(base, this.escuro ? '#f0f5ff' : '#101822', 0.35);
    const chave = `linhas|${cor}|${tipo}|${this.planosCorte.length}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      const comum = { color: new THREE.Color(cor), transparent: true, opacity: 0.95,
                      clippingPlanes: this.planosCorte.length ? this.planosCorte : null };
      m = tipo === 'construcao'
        ? new THREE.LineDashedMaterial({ ...comum, dashSize: 0.6, gapSize: 0.4 })
        : new THREE.LineBasicMaterial(comum);
      this.cacheMaterial.set(chave, m);
    }
    return m;
  }

  // ---- seções de perfil (usadas enquanto o servidor não responde) ----

  /** Dimensões do perfil no catálogo, em milímetros. */
  perfil(nome) {
    const p = this.catalogo.perfis instanceof Map
      ? this.catalogo.perfis.get(nome) : null;
    return p || null;
  }

  definirCatalogo(cat) {
    const perfis = new Map();
    for (const p of ((cat && cat.perfis) || [])) perfis.set(p.nome, p);
    this.catalogo = { ...cat, perfis };
  }

  /** Perfis que chegaram depois (fora do banco básico: dobrados de fábrica, barras
   *  redondas): entram no catálogo e as barras deles são refeitas com a seção certa. */
  acrescentarPerfis(lista) {
    if (!this.catalogo || !(this.catalogo.perfis instanceof Map)) this.catalogo = { ...(this.catalogo || {}), perfis: new Map() };
    const nomes = new Set();
    for (const p of lista || []) { this.catalogo.perfis.set(p.nome, p); nomes.add(p.nome); }
    if (!nomes.size) return 0;
    for (const chave of [...this.cacheGeometria.keys()]) {
      if (chave.startsWith('barra|') && nomes.has(chave.split('|')[1])) {
        this.cacheGeometria.delete(chave);
        this.origemGeometria.delete(chave);
      }
    }
    const ids = this.documento.barras.filter(b => nomes.has(b.perfil)).map(b => b.id);
    if (ids.length) this.atualizar(ids);
    return ids.length;
  }

  _secaoDoPerfil(nome) {
    const p = this.perfil(nome);
    if (!p) return secaoRetangulo(100, 200);
    // O catálogo já traz a seção feita pelo Python (`geometria.secao`): é a mesma
    // que o servidor extruda, com chanfros e dobras. O tubo sem furo declarado fica
    // com a versão daqui, que é oca.
    const doServidor = formaDaSecao(p.secao);
    if (doServidor && !(p.tipo === 'tubo' && !doServidor.holes.length)) return doServidor;
    // tubo quadrado ou retangular (TQ, TR) com só o contorno de fora: o furo pela espessura da parede — o redondo
    // daqui o desenharia redondo no modo leve, que não pede a malha ao servidor (portaria, 30/09)
    const oco = doServidor && p.tipo === 'tubo' ? tuboRetangularOco(p.secao, p.tw) : null;
    if (oco) return oco;
    switch (p.tipo) {
      case 'I': return secaoI(p.bf, p.d, p.tw, p.tf);
      case 'U': return secaoU(p.bf, p.d, p.tw, p.tf);
      case 'Ue': return secaoUe(p.bf, p.d, p.tw);
      case 'L': return secaoL(p.bf || 50, p.tw);
      case 'tubo': return secaoTubo(p.d, p.tw);
      default: return secaoRetangulo(p.bf || 100, p.d || 200);
    }
  }

  // ---- refino pelo servidor ----

  _agendarRefino() {
    if (!this.usarServidor || !this.api || this._refinando) return;
    // Modelo grande (desenho em lote): a seção local já é fiel o bastante, e trocar a
    // geometria de centenas de chapas obrigaria a refazer os blocos — uma travada de
    // segundos em troca de quase nada na tela.
    if (this.lote) { this.avisoServidor = 'modelo grande: seção local, sem refino'; return; }
    // Junta os pedidos de um mesmo quadro numa chamada só.
    if (this._pedidoAgendado) return;
    this._pedidoAgendado = setTimeout(() => {
      this._pedidoAgendado = null;
      this._refinar().catch(e => console.warn('refino de malhas:', e));
    }, 30);
  }

  async _refinar() {
    if (!this.usarServidor || !this.api) return;
    // Uma entidade por chave de geometria ainda não resolvida pelo servidor.
    const porChave = new Map();
    for (const [id, obj] of this.objetos) {
      const ent = this.documento.get(id);
      if (!ent || (ent.tipo !== 'barra' && ent.tipo !== 'chapa')) continue;
      const chave = obj.userData.chave;
      // Só o que ainda está com a seção local; 'servidor' e 'recusada' já foram tratadas.
      if (!chave || this.origemGeometria.get(chave) !== 'local') continue;
      if (!porChave.has(chave)) porChave.set(chave, ent);
    }
    if (!porChave.size) return;

    // Uma rodada só: antes eram 80 chaves por vez, e cada rodada refazia o modelo
    // inteiro na tela — num IFC com centenas de chapas isso eram várias travadas de
    // segundos em sequência, que é o que o usuário sentia como "calculando o tempo todo".
    // A peça como foi pedida (e a chave dela): se ela mudar enquanto o servidor responde — o segundo plano do
    // Encaixar ponta, o bico —, a malha que volta é a de antes e fica na chave de antes, não na de agora.
    const pedidas = [...porChave].map(([chave, e]) => [chave, JSON.parse(JSON.stringify(e))]);
    const amostras = pedidas.map(([, e]) => e);
    const docJSON = {
      nome: this.documento.nome, unidade: 'mm',
      entidades: amostras,
      camadas: {}, materiais: {},
    };
    let resposta;
    try {
      resposta = await this.api.malhas(docJSON, amostras.map(e => e.id));
    } catch (e) {
      // O Python de geometria ainda não existe, ou quebrou: seguimos com a seção local.
      this.usarServidor = false;
      this.avisoServidor = e && e.message ? String(e.message) : 'malhas indisponíveis';
      console.info('malhas do servidor indisponíveis, usando a seção local:', this.avisoServidor);
      return;
    }
    const malhas = (resposta && resposta.malhas) || {};
    const chavesTrocadas = new Set();
    let trocadas = 0;
    for (const [chave, ent] of pedidas) {
      const reg = malhas[ent.id];
      // Uma malha recusada fica com a seção local e não é pedida de novo — senão cada
      // reconstrução repetiria o mesmo pedido fadado a falhar.
      if (!reg || reg.erro || !reg.vertices || !reg.faces) {
        this.origemGeometria.set(chave, 'recusada');
        continue;
      }
      const geom = this._doMundoParaLocal(reg, ent);
      if (!geom) { this.origemGeometria.set(chave, 'recusada'); continue; }
      const velha = this.cacheGeometria.get(chave);
      if (velha && velha !== geom) velha.dispose();
      geom.userData.emCache = true;
      this.cacheGeometria.set(chave, geom);
      this.origemGeometria.set(chave, 'servidor');
      chavesTrocadas.add(chave);
      trocadas++;
    }
    if (trocadas) {
      // Só quem usa as geometrias que acabaram de mudar — e não o modelo inteiro.
      const ids = [];
      for (const [id, obj] of this.objetos) {
        if (chavesTrocadas.has(obj.userData.chave)) ids.push(id);
      }
      this._refinando = true;         // a reconstrução não pede refino de novo (laço)
      try { this.atualizar(ids); } finally { this._refinando = false; }
    }
  }

  _chaveDe(ent) {
    if (ent.tipo === 'barra' && temCorteNoAngulo(ent)) {
      const r = this._geometriaBarraCortada(ent);
      if (r) return r.chave;
    }
    if (ent.tipo === 'barra') {
      const L = comprimentoDaBarra(ent);
      const util = Math.max(1, L - (ent.recorte_inicio || 0) - (ent.recorte_fim || 0));
      return `barra|${ent.perfil}|${util.toFixed(2)}`;
    }
    const c = ent.contorno || [];
    return `chapa|${ent.espessura}|${c.map(p => p.join()).join(';')}|` +
           (ent.furos || []).map(f => `${f.x},${f.y},${f.diametro}`).join(';');
  }

  /** O servidor devolve a malha em coordenadas do mundo; o cache guarda a local. */
  _doMundoParaLocal(reg, ent) {
    const m = ent.tipo === 'barra'
      ? this._geometriaBarra(ent).matriz
      : this._geometriaChapa(ent).matriz;
    if (!m) return null;
    const inv = new THREE.Matrix4().copy(m).invert();
    const v = reg.vertices;
    const pos = [];
    const p = new THREE.Vector3();
    const ponto = (idx) => [v[idx * 3], v[idx * 3 + 1], v[idx * 3 + 2]];
    for (const f of reg.faces) {
      // Faces de até 4 lados são convexas; acima disso (tampa de um perfil I, por
      // exemplo) o leque sairia para fora da seção, então triangulamos de verdade.
      const tris = f.length <= 4 ? leque(f.length) : triangularFace(f.map(ponto));
      for (const [a, b, c] of tris) {
        for (const idx of [f[a], f[b], f[c]]) {
          p.set(v[idx * 3], v[idx * 3 + 1], v[idx * 3 + 2]).applyMatrix4(inv);
          pos.push(p.x, p.y, p.z);
        }
      }
    }
    if (!pos.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    return g;
  }

  // -------------------------------------------------------------- materiais

  _corDe(ent) {
    // Ponto único de decisão de cor: o mapa de esforços entra aqui, e com isso vale
    // para malha, arestas, linhas soltas e para a mistura que a seleção faz.
    if (this.pintandoPorValor) {
      return this._corDeValor(ent) ||
             (this.escuro ? CINZA_SEM_VALOR.escuro : CINZA_SEM_VALOR.claro);
    }
    const mat = ent.material && this.documento.materiais.get(ent.material);
    if (mat && mat.cor) return mat.cor;
    const cam = this.documento.camadas.get(ent.camada);
    return (cam && cam.cor) || '#8a94a6';
  }

  _materialDe(ent) {
    if (this.destaque && !this.destaque.has(ent.id)) return this._materialFantasma();
    const mat = ent.material && this.documento.materiais.get(ent.material);
    const cor = this._corDe(ent);
    // Pintando por valor, a peça sem valor fica translúcida e o brilho metálico sai de
    // cena: a cor do mapa tem de ser lida como cor, não como reflexo.
    const porValor = this.pintandoPorValor;
    const semValor = porValor && !this._corDeValor(ent);
    // Sem valor no mapa: o mesmo cinza opaco do fantasma. Translúcido ficava bonito no
    // galpão de 300 peças, mas num IFC de 5 mil (telhas, parafusos, chapas sem
    // verificação) milhares de materiais transparentes obrigam a ordenar e sobrepor tudo
    // a cada quadro, e a cena trava.
    if (semValor && this.modo !== 'raiox' && this.modo !== 'arestas') return this._materialFantasma();
    const opac = this.modo === 'raiox' ? 0.18
               : this.modo === 'arestas' ? 0
               : semValor ? OPACIDADE_SEM_VALOR
               : porValor ? 1
               : (mat ? (mat.opacidade ?? 1) : 1);
    const metal = porValor ? 0.12 : mat ? (mat.metalico ?? 0.55) : 0.55;
    const rug = porValor ? 0.78 : mat ? (mat.rugosidade ?? 0.5) : 0.5;
    const chave = `${cor}|${opac}|${metal}|${rug}|${this.modo}|${this.planosCorte.length}` +
                  `|${porValor ? (semValor ? 'sem' : 'valor') : ''}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      m = new THREE.MeshStandardMaterial({
        color: new THREE.Color(cor), metalness: metal, roughness: rug,
        transparent: opac < 1, opacity: opac,
        depthWrite: opac >= 0.95,
        side: THREE.DoubleSide,
        flatShading: false,
        clippingPlanes: this.planosCorte.length ? this.planosCorte : null,
      });
      // No escuro a peça ganha um empurrãozinho de brilho — menos quando a cor vem do
      // mapa de esforços, que precisa bater exatamente com a cor da legenda.
      if (this.escuro && !porValor) m.color.multiplyScalar(1.06);
      this.cacheMaterial.set(chave, m);
    }
    return m;
  }

  _materialArestas(ent) {
    if (this.destaque && !this.destaque.has(ent.id)) return this._materialFantasmaLinha();
    const forte = this.modo === 'arestas' || this.modo === 'raiox';
    const cor = forte ? (this.escuro ? '#c8d4e6' : '#1c2836')
                      : misturar(this._corDe(ent), this.escuro ? '#f0f5ff' : '#101822', 0.55);
    const chave = `aresta|${cor}|${this.modo}|${this.escuro}|${this.planosCorte.length}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      m = new THREE.LineBasicMaterial({
        color: new THREE.Color(cor), transparent: true,
        opacity: forte ? 0.92 : 0.55, depthWrite: false,
        clippingPlanes: this.planosCorte.length ? this.planosCorte : null,
      });
      this.cacheMaterial.set(chave, m);
    }
    return m;
  }

  _pintar(id) {
    const obj = this.objetos.get(id);
    const ent = this.documento.get(id);
    if (!obj || !ent) return;
    if (obj.userData.lote) { if (this.lote) this.lote.pintar(id); return; }
    const malha = obj.getObjectByName('malha');
    const arestas = obj.getObjectByName('arestas');
    const linhas = obj.getObjectByName('linhas');
    if (malha && !obj.userData.realce) malha.material = this._materialDe(ent);
    if (arestas && !obj.userData.realce) arestas.material = this._materialArestas(ent);
    if (linhas && !obj.userData.realce) linhas.material = this._materialLinhas(ent);
    if (this.destaque && !this.destaque.has(id) && !obj.userData.realce) {
      // fora do destaque: fantasma cinza claro opaco, para as peças em foco saltarem
      if (malha) malha.material = this._materialFantasma();
      if (arestas) arestas.material = this._materialFantasmaLinha();
      if (linhas) linhas.material = this._materialFantasmaLinha();
    }
    this._aplicarModo(obj);
    // fantasma sem arestas: metade dos objetos desenhados a menos
    if (this.destaque && !this.destaque.has(id) && arestas) arestas.visible = false;
    // idem para a peça sem valor no mapa de esforços
    if (arestas && this.pintandoPorValor && !this._corDeValor(ent) && !obj.userData.realce &&
        this.modo !== 'arestas' && this.modo !== 'raiox') arestas.visible = false;
  }

  /** Destaque: só `ids` ficam com a cor normal, o resto do modelo vira fantasma. null desliga. */
  destacar(ids) {
    this.destaque = ids && ids.length ? new Set(ids) : null;
    for (const id of this.objetos.keys()) this._pintar(id);
    // a seleção por cima de novo: a peça em destaque ganha a cor dele (a seleção foi feita antes do destaque)
    if (this.aoRepintar) this.aoRepintar();
    this._marcarDestaque(ids);
    this.pedirQuadro();
  }

  /**
   * Um anel vermelho de tamanho fixo na tela em volta de cada grupo de peças em destaque, por cima do
   * modelo: a chapa escolhida no 2D, com o prédio inteiro enquadrado, era um ponto que não se achava,
   * sobretudo no tema claro (pedido do usuário, 30/09). Peças perto umas das outras (as de um conjunto)
   * ganham um anel só; destaque grande demais (a busca com centenas de peças) fica sem anel.
   */
  _marcarDestaque(ids) {
    if (this._marcas) {
      this.cena.remove(this._marcas);
      this._marcas.traverse(o => { if (o.material) o.material.dispose(); });
      this._marcas = null;
    }
    if (!ids || !ids.length || ids.length > MAIS_PECAS_COM_ANEL) return;
    const centros = [];
    for (const id of ids) {
      const c = this.documento.caixa([id]);
      if (c[0].every((v, i) => v === 0 && c[1][i] === 0)) continue;
      centros.push({ p: [0, 1, 2].map(i => (c[0][i] + c[1][i]) / 2), n: 1 });
    }
    if (!centros.length) return;
    // junta as vizinhas (a distância pelo tamanho do modelo), em cadeia
    const cx = this.documento.caixa();
    const perto = Math.max(1500, 0.08 * Math.hypot(cx[1][0] - cx[0][0], cx[1][1] - cx[0][1], cx[1][2] - cx[0][2]));
    const grupos = [];
    for (const c of centros) {
      const junto = grupos.filter(g => g.some(o => Math.hypot(o.p[0] - c.p[0], o.p[1] - c.p[1], o.p[2] - c.p[2]) <= perto));
      const novo = [c];
      for (const g of junto) { novo.push(...g); grupos.splice(grupos.indexOf(g), 1); }
      grupos.push(novo);
    }
    if (grupos.length > MAIS_ANEIS) return;
    this._marcas = new THREE.Group();
    this._marcas.name = 'marcas-destaque';
    const textura = texturaDoAnel();
    for (const g of grupos) {
      const m = [0, 1, 2].map(i => g.reduce((s, o) => s + o.p[i], 0) / g.length * ESCALA);
      const anel = new THREE.Sprite(new THREE.SpriteMaterial({ map: textura, depthTest: false, depthWrite: false,
                                                                transparent: true }));
      anel.position.set(m[0], m[1], m[2]);
      anel.renderOrder = 999;
      anel.raycast = () => {};                        // não pega o clique das peças
      // o mesmo tamanho na tela em qualquer zoom e nas duas projeções: a altura do que se vê na distância dele
      anel.onBeforeRender = (_r, _c, cam) => {
        let alto;
        if (cam.isOrthographicCamera) alto = (cam.top - cam.bottom) / (cam.zoom || 1);
        else alto = 2 * cam.position.distanceTo(anel.position) * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
        anel.scale.setScalar(Math.max(alto * FRACAO_ANEL, 1e-6));
        anel.updateMatrixWorld(true);
      };
      this._marcas.add(anel);
    }
    this.cena.add(this._marcas);
  }

  _materialFantasma() {
    const chave = `fantasma|${this.escuro ? 1 : 0}|${this.planosCorte.length}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      // opaco de propósito: material transparente em milhares de peças obriga a ordenar
      // e sobrepor tudo a cada quadro, e a cena trava; um cinza claro opaco faz o mesmo
      // papel de "sumir" sem custo
      m = new THREE.MeshStandardMaterial({
        color: new THREE.Color(this.escuro ? '#2e3642' : '#d7dce6'), metalness: 0.0, roughness: 1.0,
        side: THREE.DoubleSide,
        clippingPlanes: this.planosCorte.length ? this.planosCorte : null,
      });
      this.cacheMaterial.set(chave, m);
    }
    return m;
  }

  _materialFantasmaLinha() {
    const chave = `fantasma-linha|${this.escuro ? 1 : 0}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      m = new THREE.LineBasicMaterial({ color: new THREE.Color(this.escuro ? '#3a4352' : '#c3c9d4') });
      this.cacheMaterial.set(chave, m);
    }
    return m;
  }

  _aplicarModo(obj) {
    const malha = obj.getObjectByName('malha');
    const arestas = obj.getObjectByName('arestas');
    if (!malha) return;
    if (this.modo === 'sombreado') {
      malha.visible = true; if (arestas) arestas.visible = false;
    } else if (this.modo === 'sombreado_arestas') {
      malha.visible = true; if (arestas) arestas.visible = true;
    } else if (this.modo === 'arestas') {
      malha.visible = false; if (arestas) arestas.visible = true;
    } else {                                 // raio-x
      malha.visible = true; if (arestas) arestas.visible = true;
      malha.renderOrder = 1;
    }
  }

  // ------------------------------------------------------------- prévia

  /** Desenho temporário das ferramentas, em milímetros. */
  addPrevia(obj) { if (obj) { this.previa.add(obj); this.pedirQuadro(); } return obj; }

  limparPrevia() {
    for (const f of this.previa.children.slice()) {
      this.previa.remove(f);
      f.traverse && f.traverse(x => {
        if (x.geometry) x.geometry.dispose();
        if (x.material) (Array.isArray(x.material) ? x.material : [x.material])
          .forEach(m => m.dispose && m.dispose());
      });
    }
    this.pedirQuadro();
  }

  // -------------------------------------------------------------- desenho

  /** Objetos que entram no raycast. */
  get alvos() {
    // esqueleto ligado: só as linhas dele (o modelo com perfis está escondido)
    if (this.alvosExtras) return this.alvosExtras.slice();
    const out = this.lote ? this.lote.alvos() : [];
    for (const obj of this.objetos.values()) {
      if (!obj.visible) continue;
      const m = obj.getObjectByName('malha');
      if (m) out.push(m);
      const l = obj.getObjectByName('linhas');
      if (l) out.push(l);
    }
    return out;
  }

  redimensionar(largura, altura) {
    this.renderizador.setSize(largura, altura, false);
    this.pedirQuadro();
  }

  /** Pede um quadro; vários pedidos no mesmo tique viram um só. */
  pedirQuadro() {
    if (this._quadro) return;
    this._quadro = requestAnimationFrame(() => {
      this._quadro = null;
      if (this.aoDesenhar) this.aoDesenhar();
    });
  }

  desenhar(camera) {
    if (!camera) return;
    if (this.piso && this.piso.visible) {
      // o centro do degradê do piso: onde o olhar da câmera encontra o chão (ou embaixo dela, olhando para o horizonte)
      const d = camera.getWorldDirection(this._dirCamera);
      const c = camera.position;
      const t = d.z < -0.08 ? Math.min(-c.z / d.z, this._gradeExtensao || 1e4) : 0;
      this.piso.material.uniforms.uCentro.value.set(c.x + d.x * t, c.y + d.y * t);
    }
    this.renderizador.render(this.cena, camera);
  }

  descartar() {
    if (this.desinscrever) this.desinscrever();
    if (this.lote) { this.lote.descartar(); this.lote = null; }
    for (const g of this.cacheGeometria.values()) g.dispose();
    this.cacheGeometria.clear();
    for (const m of this.cacheMaterial.values()) m.dispose();
    this.cacheMaterial.clear();
    this.renderizador.dispose();
  }
}

// ------------------------------------------------------------- geometria

const vet = (a) => new THREE.Vector3(a[0], a[1], a[2]);

function extrudar(forma, profundidade) {
  const g = new THREE.ExtrudeGeometry(forma, {
    depth: profundidade, bevelEnabled: false, steps: 1, curveSegments: 16,
  });
  g.computeVertexNormals();
  return g;
}

// ---- o corte no ângulo (a mesma receita de nucleo3d/geometria.py) ----

const _pz = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const _alt = (f, x, y) => f[0] * x + f[1] * y + f[2];

export function temCorteNoAngulo(b) {
  return !!((b.cortes_inicio && b.cortes_inicio.length) || (b.cortes_fim && b.cortes_fim.length));
}

/** As pontas como alturas z(x, y) = a·x + b·y + c no triedro local (origem no início): [início, fim]. */
export function alturasDeCorte(b, base) {
  const { t, u, v } = base;
  const L = comprimentoDaBarra(b);
  const r0 = Math.max(0, b.recorte_inicio || 0), r1 = Math.max(0, b.recorte_fim || 0);
  const c0 = b.cortes_inicio || [], c1 = b.cortes_fim || [];
  const f0 = (r0 > 0 || !c0.length) ? [[0, 0, r0]] : [];
  const f1 = (r1 > 0 || !c1.length) ? [[0, 0, L - r1]] : [];
  for (const [lista, destino, ext] of [[c0, f0, 0], [c1, f1, L]]) {
    for (const c of lista) {
      const n = c && c.normal, p = (c && c.ponto) || [0, 0, 0];
      if (!n) continue;
      const nn = Math.hypot(n[0], n[1], n[2]);
      if (!(nn > 1e-9)) continue;
      const nx = _pz(n, u) / nn, ny = _pz(n, v) / nn, nz = _pz(n, t) / nn;
      if (Math.abs(nz) < 0.1) continue;                 // quase paralelo ao eixo: não corta a ponta
      const px = _pz(p, u), py = _pz(p, v), pzz = _pz(p, t) + ext;
      destino.push([-nx / nz, -ny / nz, (nx * px + ny * py + nz * pzz) / nz]);
    }
  }
  const distintas = (fs) => fs.filter((f, i) => !fs.slice(0, i).some(g =>
    Math.abs(f[0] - g[0]) < 1e-9 && Math.abs(f[1] - g[1]) < 1e-9 && Math.abs(f[2] - g[2]) < 1e-6));
  return [distintas(f0.length ? f0 : [[0, 0, r0]]), distintas(f1.length ? f1 : [[0, 0, L - r1]])];
}

function _recortarConvexo(poli, a, b, c) {
  const out = [];
  for (let i = 0; i < poli.length; i++) {
    const P = poli[i], Q = poli[(i + 1) % poli.length];
    const fp = a * P[0] + b * P[1] + c, fq = a * Q[0] + b * Q[1] + c;
    if (fp >= 0) out.push(P);
    if ((fp >= 0) !== (fq >= 0)) {
      const k = fp / (fp - fq);
      out.push([P[0] + k * (Q[0] - P[0]), P[1] + k * (Q[1] - P[1])]);
    }
  }
  return out;
}

const _area2 = (p) => {
  let s = 0;
  for (let i = 0; i < p.length; i++) { const a = p[i], b = p[(i + 1) % p.length]; s += a[0] * b[1] - b[0] * a[1]; }
  return s / 2;
};

function _pedacos(tri, fs, maior) {
  if (fs.length === 1) return [[tri, fs[0]]];
  const s = maior ? 1 : -1, res = [];
  fs.forEach((fk, k) => {
    let poli = tri;
    for (let j = 0; j < fs.length && poli.length >= 3; j++) {
      if (j === k) continue;
      const fj = fs[j];
      poli = _recortarConvexo(poli, s * (fk[0] - fj[0]), s * (fk[1] - fj[1]), s * (fk[2] - fj[2]));
    }
    if (poli.length >= 3 && Math.abs(_area2(poli)) > 1e-9) res.push([poli, fk]);
  });
  return res;
}

/** Malha da barra cortada no triedro local; null quando o corte come a peça (< 1 mm entre as pontas). */
export function prismaCortado(forma, f0, f1) {
  const ext = forma.extractPoints(16);
  const limpar = (pts) => {
    const q = pts.map(p => [p.x, p.y]);
    if (q.length > 1) {
      const a = q[0], z = q[q.length - 1];
      if (Math.abs(a[0] - z[0]) < 1e-9 && Math.abs(a[1] - z[1]) < 1e-9) q.pop();
    }
    return q;
  };
  const externo = limpar(ext.shape);
  if (_area2(externo) < 0) externo.reverse();
  const internos = ext.holes.map(h => { const q = limpar(h); if (_area2(q) > 0) q.reverse(); return q; });
  const F0 = (x, y) => Math.max(...f0.map(f => _alt(f, x, y)));
  const F1 = (x, y) => Math.min(...f1.map(f => _alt(f, x, y)));
  const pos = [];
  const tri3 = (a, b, c) => pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
  const quebras = (fs, P, Q) => {
    const ss = [0, 1];
    for (let k = 0; k < fs.length; k++) for (let j = k + 1; j < fs.length; j++) {
      const g0 = _alt(fs[k], P[0], P[1]) - _alt(fs[j], P[0], P[1]);
      const g1 = _alt(fs[k], Q[0], Q[1]) - _alt(fs[j], Q[0], Q[1]);
      if (g0 * g1 < 0) ss.push(g0 / (g0 - g1));
    }
    return ss.sort((a, b) => a - b).map(s => [P[0] + s * (Q[0] - P[0]), P[1] + s * (Q[1] - P[1])]);
  };
  for (const anel of [externo, ...internos]) {           // laterais: um polígono plano e convexo por aresta
    for (let i = 0; i < anel.length; i++) {
      const P = anel[i], Q = anel[(i + 1) % anel.length];
      const baixo = quebras(f0, P, Q), cima = quebras(f1, P, Q);
      for (const [x, y] of baixo.concat(cima)) if (F1(x, y) - F0(x, y) < 1) return null;
      const poli = baixo.map(([x, y]) => [x, y, F0(x, y)])
        .concat(cima.reverse().map(([x, y]) => [x, y, F1(x, y)]));
      for (let k = 1; k < poli.length - 1; k++) tri3(poli[0], poli[k], poli[k + 1]);
    }
  }
  const plano = externo.concat(...internos);
  const tris = THREE.ShapeUtils.triangulateShape(externo.map(p => new THREE.Vector2(p[0], p[1])),
                                                 internos.map(h => h.map(p => new THREE.Vector2(p[0], p[1]))));
  for (const [a, b, c] of tris) {
    const tri = [plano[a], plano[b], plano[c]];
    if (_area2(tri) < 0) tri.reverse();
    for (const [poli, f] of _pedacos(tri, f1, false)) {          // tampa do fim: +z
      const q = poli.map(([x, y]) => [x, y, _alt(f, x, y)]);
      for (let k = 1; k < q.length - 1; k++) tri3(q[0], q[k], q[k + 1]);
    }
    for (const [poli, f] of _pedacos(tri, f0, true)) {           // tampa do início: −z
      const q = poli.map(([x, y]) => [x, y, _alt(f, x, y)]);
      for (let k = 1; k < q.length - 1; k++) tri3(q[k + 1], q[k], q[0]);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

const _cacheArestas = new WeakMap();
/** As arestas acompanham o destino da geometria: compartilhadas quando ela é. */
function obterArestas(geom, compartilhada) {
  if (!compartilhada) {
    const e = new THREE.EdgesGeometry(geom, 24);
    e.userData.emCache = false;
    return e;
  }
  let e = _cacheArestas.get(geom);
  if (!e) {
    e = new THREE.EdgesGeometry(geom, 24);
    e.userData.emCache = true;
    _cacheArestas.set(geom, e);
  }
  return e;
}

/** Perfil I: dois banzos e uma alma. Coordenadas locais: x = bf, y = d. */
export function secaoI(bf, d, tw, tf) {
  const bx = bf / 2, dy = d / 2, wx = tw / 2;
  return caminho([
    [-bx, -dy], [bx, -dy], [bx, -dy + tf], [wx, -dy + tf],
    [wx, dy - tf], [bx, dy - tf], [bx, dy], [-bx, dy],
    [-bx, dy - tf], [-wx, dy - tf], [-wx, -dy + tf], [-bx, -dy + tf],
  ]);
}

/** Perfil U laminado: alma de um lado, mesas para o outro. */
export function secaoU(bf, d, tw, tf) {
  const x0 = -bf / 2, dy = d / 2;
  return caminho([
    [x0, -dy], [x0 + bf, -dy], [x0 + bf, -dy + tf], [x0 + tw, -dy + tf],
    [x0 + tw, dy - tf], [x0 + bf, dy - tf], [x0 + bf, dy], [x0, dy],
  ]);
}

/** Perfil U enrijecido (formado a frio): parede fina com lábios nas pontas. */
export function secaoUe(bf, d, t) {
  const x0 = -bf / 2, dy = d / 2;
  const lab = Math.max(8, Math.min(25, bf / 3));
  return caminho([
    [x0, -dy], [x0 + bf, -dy], [x0 + bf, -dy + lab], [x0 + bf - t, -dy + lab],
    [x0 + bf - t, -dy + t], [x0 + t, -dy + t], [x0 + t, dy - t], [x0 + bf - t, dy - t],
    [x0 + bf - t, dy - lab], [x0 + bf, dy - lab], [x0 + bf, dy], [x0, dy],
  ]);
}

/** Cantoneira de abas iguais. */
export function secaoL(aba, t) {
  const a = aba / 2;
  return caminho([
    [-a, -a], [a, -a], [a, -a + t], [-a + t, -a + t], [-a + t, a], [-a, a],
  ]);
}

/** Tubo circular: disco externo com furo interno. */
export function secaoTubo(diametro, parede) {
  const re = Math.max(1, diametro / 2);
  const ri = Math.max(0.5, re - (parede || 1));
  const forma = new THREE.Shape();
  forma.absarc(0, 0, re, 0, Math.PI * 2, false);
  const furo = new THREE.Path();
  furo.absarc(0, 0, ri, 0, Math.PI * 2, true);
  forma.holes.push(furo);
  return forma;
}

export function secaoRetangulo(b, h) {
  return caminho([[-b / 2, -h / 2], [b / 2, -h / 2], [b / 2, h / 2], [-b / 2, h / 2]]);
}

/** O tubo retangular oco a partir do contorno de fora (lista de [x,y]); null quando o contorno é redondo. */
export function tuboRetangularOco(secao, parede) {
  const pts = Array.isArray(secao) ? secao : (secao && (secao.contorno || secao.externo));
  if (!Array.isArray(pts) || pts.length < 4) return null;
  const xs = pts.map(q => (Array.isArray(q) ? q[0] : q.x)), ys = pts.map(q => (Array.isArray(q) ? q[1] : q.y));
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const b = x1 - x0, h = y1 - y0, t = parede || Math.max(1, Math.min(b, h) * 0.05);
  // redondo: o contorno não encosta nos cantos da caixa (a área fica em ~78 % dela)
  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], q = pts[(i + 1) % pts.length];
    area += (Array.isArray(p) ? p[0] : p.x) * (Array.isArray(q) ? q[1] : q.y) - (Array.isArray(q) ? q[0] : q.x) * (Array.isArray(p) ? p[1] : p.y);
  }
  if (Math.abs(area) / 2 < 0.85 * b * h || b <= 2 * t || h <= 2 * t) return null;
  const forma = formaDaSecao(pts.map(q => (Array.isArray(q) ? q : [q.x, q.y])));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, bi = b / 2 - t, hi = h / 2 - t;
  const furo = new THREE.Path();
  furo.moveTo(cx - bi, cy - hi); furo.lineTo(cx - bi, cy + hi); furo.lineTo(cx + bi, cy + hi); furo.lineTo(cx + bi, cy - hi);
  furo.closePath();
  forma.holes.push(furo);
  return forma;
}

/** Seção vinda do catálogo: lista de [x,y], ou {contorno, furos}. */
function formaDaSecao(secao) {
  if (!secao) return null;
  const par = (q) => (Array.isArray(q) ? [q[0], q[1]] : [q.x, q.y]);
  const externo = Array.isArray(secao) ? secao
                : Array.isArray(secao.contorno) ? secao.contorno
                : Array.isArray(secao.externo) ? secao.externo : null;
  if (!externo || externo.length < 3) return null;
  const forma = caminho(externo.map(par));
  for (const furo of (secao.furos || secao.internos || [])) {
    if (!Array.isArray(furo) || furo.length < 3) continue;
    const pts = furo.map(par);
    const f = new THREE.Path();
    f.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) f.lineTo(pts[i][0], pts[i][1]);
    f.closePath();
    forma.holes.push(f);
  }
  return forma;
}

function centroDe(vs) {
  if (!vs || !vs.length) return null;
  const c = [0, 0, 0];
  for (const p of vs) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  return [c[0] / vs.length, c[1] / vs.length, c[2] / vs.length];
}

const leque = (n) => {
  const t = [];
  for (let i = 1; i < n - 1; i++) t.push([0, i, i + 1]);
  return t;
};

/** Triangula uma face plana qualquer, projetando-a no próprio plano. */
function triangularFace(pts) {
  let nx = 0, ny = 0, nz = 0;                 // normal de Newell
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const ax = Math.abs(nx), ay = Math.abs(ny), az = Math.abs(nz);
  // Descarta a coordenada dominante da normal: sobra uma projeção sem degenerar.
  const plano = az >= ax && az >= ay ? (p) => new THREE.Vector2(p[0], p[1])
              : ax >= ay ? (p) => new THREE.Vector2(p[1], p[2])
              : (p) => new THREE.Vector2(p[2], p[0]);
  const tris = THREE.ShapeUtils.triangulateShape(pts.map(plano), []);
  return tris.length ? tris : leque(pts.length);
}

function caminho(pts) {
  const s = new THREE.Shape();
  s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  s.closePath();
  return s;
}

// --------------------------------------------------------------- cores

export function misturar(a, b, k) {
  const ca = new THREE.Color(a), cb = new THREE.Color(b);
  return '#' + ca.lerp(cb, k).getHexString();
}
