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
import { Documento, baseDaBarra, normalizar, produtoVetorial,
         comprimentoDaBarra, normalDaChapa, arestasSoltasDe } from './documento.js';

/** Subtipo de um sólido anotado pelas ferramentas: 'cota', 'construcao', ''. */
const tipoDe = (ent) => (ent && ent.atributos && ent.atributos.tipo) || '';

/** Metros de cena por milímetro de documento. */
export const ESCALA = 0.001;

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
    this.usarServidor = true;         // desligado sozinho se o servidor não puder ajudar
    this.avisoServidor = '';

    // Cor vinda de fora (mapa de esforços). Enquanto as duas forem nulas, a cena pinta
    // exatamente como sempre pintou — quem constrói o mapa não muda nada só por existir.
    this.corPorValor = null;          // (entidade) => '#rrggbb' | null
    this.mapaCores = null;            // Map<id, '#rrggbb'>, alternativa à função

    this.objetos = new Map();         // id da entidade -> THREE.Group
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

  _fundoGradiente() {
    const c = document.createElement('canvas');
    c.width = 4; c.height = 256;
    const g = c.getContext('2d');
    const grad = g.createLinearGradient(0, 0, 0, 256);
    if (this.escuro) {
      grad.addColorStop(0, '#111a27');
      grad.addColorStop(0.55, '#0e131a');
      grad.addColorStop(1, '#161d27');
    } else {
      grad.addColorStop(0, '#cfdcf0');
      grad.addColorStop(0.52, '#eaf0f8');
      grad.addColorStop(1, '#dde4ee');
    }
    g.fillStyle = grad;
    g.fillRect(0, 0, 4, 256);
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
    this._construirEixos(Math.max(6, extensao * 0.45));
  }

  /** Só a transparência das linhas finas, sem refazer a grade. */
  _opacidadeGradeFina(opacidade) {
    this._gradeOpacidadeFina = opacidade;
    const m = this._matGradeFina;
    if (!m || Math.abs(m.opacity - opacidade) < 0.005) return;
    m.opacity = opacidade;
    m.visible = opacidade > 0.02;
    this.pedirQuadro();
  }

  _construirGrade(extensao, passo, opacidadeFina = null) {
    this._gradeExtensao = extensao;
    this._gradePasso = passo;
    if (opacidadeFina === null) opacidadeFina = this._gradeOpacidadeFina;
    if (opacidadeFina === null || opacidadeFina === undefined) opacidadeFina = 0.75;
    this._gradeOpacidadeFina = opacidadeFina;
    this._matGradeFina = null;
    for (const f of this.grade.children.slice()) {
      this.grade.remove(f);
      f.geometry.dispose(); f.material.dispose();
    }
    const finas = [], grossas = [];
    const n = Math.round(extensao / passo);
    for (let i = -n; i <= n; i++) {
      const v = i * passo;
      const forte = Math.abs(i % 10) < 1e-9;
      const alvo = forte ? grossas : finas;
      alvo.push(-extensao, v, 0, extensao, v, 0);
      alvo.push(v, -extensao, 0, v, extensao, 0);
    }
    const corFina = this.escuro ? 0x232e3d : 0xd3dbe7;
    const corForte = this.escuro ? 0x35455c : 0xb6c2d4;
    for (const [pts, cor, op] of [[finas, corFina, opacidadeFina], [grossas, corForte, 1]]) {
      if (!pts.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      const m = new THREE.LineBasicMaterial({ color: cor, transparent: true, opacity: op,
                                              depthWrite: false });
      if (pts === finas) { this._matGradeFina = m; m.visible = op > 0.02; }
      const linhas = new THREE.LineSegments(g, m);
      linhas.renderOrder = -10;
      this.grade.add(linhas);
    }
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
                                         opacity: 0.5, depthWrite: false })
        : new THREE.LineBasicMaterial({ color: cor, transparent: true, opacity: 0.95,
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

  // ------------------------------------------------------ modo de exibição

  definirModo(modo) {
    if (!MODOS.some(m => m[0] === modo)) return;
    this.modo = modo;
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
    for (const [id, obj] of this.objetos) this._descartarObjeto(obj);
    this.objetos.clear();
    this.rotulos.clear();
    this.raiz.children = this.raiz.children.filter(c => c === this.previa);
    this.atualizar([...this.documento.entidades.keys()]);
  }

  /** Reconstrói apenas as entidades pedidas (sem lista: só redesenha). */
  atualizar(ids = []) {
    for (const id of ids) {
      const ent = this.documento.get(id);
      const antigo = this.objetos.get(id);
      if (antigo) { this.raiz.remove(antigo); this._descartarObjeto(antigo); this.objetos.delete(id); }
      this.rotulos.delete(id);
      if (!ent) continue;
      if (!this.documento.aparece(ent)) continue;
      const obj = this._construirEntidade(ent);
      if (obj) { this.objetos.set(id, obj); this.raiz.add(obj); }
    }
    // Objeto recém-construído nasce sem destaque. Quando a reconstrução vem de dentro
    // da cena (malhas do servidor chegando), o documento não avisa ninguém — então a
    // seleção precisa ser reaplicada daqui, senão o que estava selecionado apaga.
    if (ids.length && this.aoRepintar) this.aoRepintar();
    this._agendarRefino();
    this.pedirQuadro();
  }

  /** Refaz só a visibilidade e a cor, sem tocar na geometria (camadas, materiais). */
  repintarTudo() {
    for (const [id, obj] of this.objetos) {
      const ent = this.documento.get(id);
      obj.visible = !!ent && this.documento.aparece(ent);
      this._pintar(id);
    }
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
    obj.traverse(f => {
      // As geometrias de barra e chapa são compartilhadas pelo cache: não descarte.
      if (f.geometry && f.geometry.userData && f.geometry.userData.emCache !== true) {
        f.geometry.dispose();
      }
    });
  }

  // ---- geometria de cada tipo ----

  _geometriaBarra(b) {
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

  _secaoDoPerfil(nome) {
    const p = this.perfil(nome);
    if (!p) return secaoRetangulo(100, 200);
    // O catálogo já traz a seção feita pelo Python (`geometria.secao`): é a mesma
    // que o servidor extruda, com chanfros e dobras. O tubo sem furo declarado fica
    // com a versão daqui, que é oca.
    const doServidor = formaDaSecao(p.secao);
    if (doServidor && !(p.tipo === 'tubo' && !doServidor.holes.length)) return doServidor;
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
    if (!this.usarServidor || !this.api) return;
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

    const amostras = [...porChave.values()].slice(0, 80);
    const docJSON = {
      nome: this.documento.nome, unidade: 'mm',
      entidades: amostras.map(e => JSON.parse(JSON.stringify(e))),
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
    let trocadas = 0;
    for (const ent of amostras) {
      const reg = malhas[ent.id];
      const chave = this._chaveDe(ent);
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
      trocadas++;
    }
    if (trocadas) {
      // Reconstrói quem usa as chaves que acabaram de mudar.
      this.atualizar([...this.objetos.keys()]);
    }
  }

  _chaveDe(ent) {
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
    const malha = obj.getObjectByName('malha');
    const arestas = obj.getObjectByName('arestas');
    const linhas = obj.getObjectByName('linhas');
    if (malha && !obj.userData.realce) malha.material = this._materialDe(ent);
    if (arestas && !obj.userData.realce) arestas.material = this._materialArestas(ent);
    if (linhas && !obj.userData.realce) linhas.material = this._materialLinhas(ent);
    if (this.destaque && !this.destaque.has(id) && !obj.userData.realce) {
      // fora do destaque: fantasma cinza quase transparente, para as peças em foco saltarem
      if (malha) malha.material = this._materialFantasma();
      if (arestas) arestas.material = this._materialFantasmaLinha();
      if (linhas) linhas.material = this._materialFantasmaLinha();
    }
    this._aplicarModo(obj);
  }

  /** Destaque: só `ids` ficam com a cor normal, o resto do modelo vira fantasma. null desliga. */
  destacar(ids) {
    this.destaque = ids && ids.length ? new Set(ids) : null;
    for (const id of this.objetos.keys()) this._pintar(id);
    this.pedirQuadro();
  }

  _materialFantasma() {
    const chave = `fantasma|${this.escuro ? 1 : 0}|${this.planosCorte.length}`;
    let m = this.cacheMaterial.get(chave);
    if (!m) {
      m = new THREE.MeshStandardMaterial({
        color: new THREE.Color(this.escuro ? '#6b7280' : '#9aa3b2'), metalness: 0.1, roughness: 0.9,
        transparent: true, opacity: 0.08, depthWrite: false, side: THREE.DoubleSide,
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
      m = new THREE.LineBasicMaterial({ color: new THREE.Color(this.escuro ? '#6b7280' : '#9aa3b2'), transparent: true, opacity: 0.12, depthWrite: false });
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
    const out = [];
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
    this.renderizador.render(this.cena, camera);
  }

  descartar() {
    if (this.desinscrever) this.desinscrever();
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
