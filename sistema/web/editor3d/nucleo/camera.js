// Câmeras e navegação.
//
// Duas câmeras sobre o mesmo alvo: perspectiva para entender o volume, ortográfica para
// desenhar e conferir medidas. A troca preserva o enquadramento — o que estava na tela
// continua na tela, só muda a projeção.
//
// Mouse: o botão esquerdo é da ferramenta ativa, nunca da navegação. O botão direito
// desloca (pan, a "mão"); o do meio orbita; Shift inverte (Shift + direito orbita,
// Shift + meio desloca); a roda dá zoom no cursor.

import * as THREE from 'three';
import { OrbitControls } from '../../lib/OrbitControls.js';
import { ESCALA } from './cena.js';

/** Vistas padrão: direção de onde a câmera olha para o alvo (Z para cima). */
export const VISTAS = {
  topo:      { rotulo: 'Topo',      dir: [0, 0, 1],       cima: [0, 1, 0], tecla: '1' },
  frente:    { rotulo: 'Frente',    dir: [0, -1, 0],      cima: [0, 0, 1], tecla: '2' },
  tras:      { rotulo: 'Trás',      dir: [0, 1, 0],       cima: [0, 0, 1], tecla: '3' },
  esquerda:  { rotulo: 'Esquerda',  dir: [-1, 0, 0],      cima: [0, 0, 1], tecla: '4' },
  direita:   { rotulo: 'Direita',   dir: [1, 0, 0],       cima: [0, 0, 1], tecla: '5' },
  inferior:  { rotulo: 'Inferior',  dir: [0, 0, -1],      cima: [0, 1, 0], tecla: '6' },
  isometrica:{ rotulo: 'Isométrica',dir: [0.82, -1, 0.72],cima: [0, 0, 1], tecla: '7' },
};

/** Quanto a cena cresce ou encolhe a cada clique da roda (~10 %, como no SketchUp). */
const FATOR_ZOOM = 1.1;
/** Teto de cliques somados num só evento, para um empurrão do trackpad não teleportar. */
const CLIQUES_MAX = 4;
/** Apoio do zoom mais longe que isto, em relação à distância atual, não serve.
 *
 * Com o cursor na parte de cima da tela, o raio ainda encontra o chão lá longe, perto
 * do horizonte. Apoiar o zoom nesse ponto arrastava a cena para o canto. */
const LONGE_DEMAIS = 1.5;

export class Camera {
  /**
   * @param elemento  o canvas (recebe os eventos de navegação)
   * @param cena      a Cena, para grade adaptativa e escala
   */
  constructor(elemento, cena) {
    this.elemento = elemento;
    this.cena = cena;
    this.largura = elemento.clientWidth || 1;
    this.altura = elemento.clientHeight || 1;
    const razao = this.largura / this.altura;

    this.perspectiva = new THREE.PerspectiveCamera(42, razao, 0.05, 8000);
    this.perspectiva.up.set(0, 0, 1);
    this.perspectiva.position.set(24, -30, 18);

    const h = 30;
    this.ortografica = new THREE.OrthographicCamera(
      -h * razao / 2, h * razao / 2, h / 2, -h / 2, -4000, 8000);
    this.ortografica.up.set(0, 0, 1);
    this.ortografica.position.copy(this.perspectiva.position);

    this.ativa = this.perspectiva;
    this.projecao = 'perspectiva';

    this.controles = new OrbitControls(this.ativa, elemento);
    this.controles.enableDamping = true;
    this.controles.dampingFactor = 0.12;
    this.controles.screenSpacePanning = true;
    // A roda é tratada aqui, em `_zoomNaRoda`, e não pelo OrbitControls: o
    // `zoomToCursor` dele recoloca o alvo à frente da câmera a cada clique, e o pivô
    // ia embora do modelo — com o cursor num canto, seis cliques levavam o alvo 35 m
    // para fora, e depois a órbita girava em torno do vazio.
    this.controles.zoomToCursor = false;
    this.controles.zoomSpeed = 1.2;          // só a pinça de dois dedos usa isto
    this.controles.rotateSpeed = 0.85;
    this.controles.minDistance = 0.05;
    this.controles.maxDistance = 6000;
    // O esquerdo fica livre para as ferramentas.
    this.controles.mouseButtons = {
      LEFT: null, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: THREE.MOUSE.PAN,
    };
    this.controles.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };

    // Direito desloca e meio orbita; Shift inverte. O OrbitControls relê
    // `mouseButtons` a cada pointerdown, então basta ajustar antes dele — daí o `capture`.
    this._antesDoDown = (ev) => {
      if (ev.button === 1) {
        this.controles.mouseButtons.MIDDLE =
          ev.shiftKey ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
      } else if (ev.button === 2) {
        this.controles.mouseButtons.RIGHT =
          ev.shiftKey ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
      }
      const orbita = (ev.button === 1 && !ev.shiftKey) || (ev.button === 2 && ev.shiftKey);
      if (orbita && this.controles.enabled) {
        // sobre uma peça: gira em volta do ponto sob o cursor, e o OrbitControls fica de
        // fora deste arrasto (botão sem ação); no vazio, o pivô de sempre
        if (this._orbitarNoCursor(ev)) {
          if (ev.button === 1) this.controles.mouseButtons.MIDDLE = null;
          else this.controles.mouseButtons.RIGHT = null;
        } else {
          this._pivoDaOrbita(ev);
        }
      }
    };
    elemento.addEventListener('pointerdown', this._antesDoDown, { capture: true });
    elemento.addEventListener('contextmenu', e => e.preventDefault());

    // O OrbitControls escuta a mesma roda. Desligar o zoom dele por um tique é o jeito
    // seguro de não somar dois zooms sem depender da ordem dos ouvintes; a pinça de
    // dois dedos continua sendo dele.
    this._naRoda = (ev) => {
      if (!this.controles.enabled) return;
      ev.preventDefault();
      ev.stopPropagation();
      this.controles.enableZoom = false;
      setTimeout(() => { this.controles.enableZoom = true; }, 0);
      this._zoomNaRoda(ev);
    };
    elemento.addEventListener('wheel', this._naRoda, { capture: true, passive: false });

    this.controles.addEventListener('change', () => {
      // O OrbitControls só gira o quaternion; a matriz inversa que `paraTela` e o
      // raycast usam só seria refeita no próximo render. Sem isto, a inferência logo
      // após mexer a câmera trabalharia com a vista do quadro anterior.
      this.ativa.updateMatrixWorld();
      this._sincronizarZoom();
      if (this.cena) {
        this.cena.ajustarGradeAoZoom(this.distancia, this.mmPorPixel());
        this.cena.pedirQuadro();
      }
      if (this.aoMover) this.aoMover();
    });

    this._animacao = null;
    this.enquadrar([[-2000, -2000, 0], [22000, 22000, 9000]]);
  }

  get alvo() { return this.controles.target; }
  get distancia() { return this.ativa.position.distanceTo(this.controles.target); }

  // ------------------------------------------------------ troca de projeção

  /** Altura da janela de visão no plano do alvo — é o que precisa ser preservado. */
  _alturaVisivel() {
    if (this.projecao === 'perspectiva') {
      const f = THREE.MathUtils.degToRad(this.perspectiva.fov);
      return 2 * this.distancia * Math.tan(f / 2);
    }
    return (this.ortografica.top - this.ortografica.bottom) / this.ortografica.zoom;
  }

  definirProjecao(qual) {
    if (qual === this.projecao) return;
    const altura = this._alturaVisivel();
    const pos = this.ativa.position.clone();
    const alvo = this.controles.target.clone();

    if (qual === 'ortografica') {
      this.ortografica.position.copy(pos);
      this.ortografica.up.copy(this.perspectiva.up);
      const base = this.ortografica.top - this.ortografica.bottom;
      this.ortografica.zoom = base / Math.max(altura, 1e-6);
      this.ortografica.updateProjectionMatrix();
      this.ativa = this.ortografica;
    } else {
      // Recoloca a perspectiva à distância que reproduz a mesma altura visível.
      const f = THREE.MathUtils.degToRad(this.perspectiva.fov);
      const d = altura / (2 * Math.tan(f / 2));
      const dir = pos.clone().sub(alvo).normalize();
      this.perspectiva.position.copy(alvo).addScaledVector(dir, Math.max(d, 0.1));
      this.perspectiva.up.copy(this.ortografica.up);
      this.perspectiva.updateProjectionMatrix();
      this.ativa = this.perspectiva;
    }
    this.projecao = qual;
    this.controles.object = this.ativa;
    this.controles.target.copy(alvo);
    this.controles.update();
    if (this.aoMover) this.aoMover();
    if (this.cena) this.cena.pedirQuadro();
  }

  alternarProjecao() {
    this.definirProjecao(this.projecao === 'perspectiva' ? 'ortografica' : 'perspectiva');
  }

  _sincronizarZoom() {
    // Na ortográfica o "zoom" do OrbitControls mexe em camera.zoom; nada a fazer.
  }

  // ---------------------------------------------------------- zoom da roda

  /** Coordenadas normalizadas (−1..1) do cursor dentro do canvas. */
  _ndcDoEvento(ev) {
    const r = this.elemento.getBoundingClientRect();
    return new THREE.Vector2(
      ((ev.clientX - r.left) / Math.max(r.width, 1)) * 2 - 1,
      -((ev.clientY - r.top) / Math.max(r.height, 1)) * 2 + 1);
  }

  /**
   * Ponto em que o zoom se apoia, e que fica parado na tela: a peça sob o cursor ou,
   * sem peça, o plano de trabalho (z = 0).
   *
   * Quando não há nada sob o cursor — o céu — ou o que há está longe demais, o apoio
   * passa a ser o próprio alvo: o zoom vira um avanço na direção da vista, sem
   * escorregar para o lado. Apoiar num ponto imaginário do céu arrastava a cena para
   * fora enquanto o usuário só queria afastar.
   */
  _focoDoCursor(ndc) {
    const raio = this._raio || (this._raio = new THREE.Raycaster());
    raio.setFromCamera(ndc, this.ativa);
    raio.params.Line.threshold = 6 * this.mmPorPixel() * ESCALA;
    const alvos = (this.cena && this.cena.alvos) || [];
    const encontros = alvos.length ? raio.intersectObjects(alvos, false) : [];
    const limite = Math.max(this.distancia, 1) * LONGE_DEMAIS;
    if (encontros.length && encontros[0].distance <= limite) {
      this.apoioDoZoom = 'peça';
      return encontros[0].point.clone();
    }
    const plano = this._planoTrabalho
      || (this._planoTrabalho = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0));
    const p = new THREE.Vector3();
    if (raio.ray.intersectPlane(plano, p)
        && p.distanceTo(this.ativa.position) <= limite) {
      this.apoioDoZoom = 'plano';
      return p;
    }
    this.apoioDoZoom = 'alvo';
    return this.controles.target.clone();
  }

  /** Ponto do mundo sob o cursor no plano médio da câmera (só para a ortográfica). */
  _mundoNoCursor(ndc) {
    return new THREE.Vector3(ndc.x, ndc.y, 0).unproject(this.ativa);
  }

  /**
   * Zoom da roda, ancorado no ponto sob o cursor.
   *
   * Na perspectiva, câmera e alvo são escalados em torno do foco: a direção da vista
   * não muda, o ponto sob o cursor fica parado e o pivô continua junto do modelo, em
   * vez de escapar para a frente da câmera. Na ortográfica muda o `zoom` e a câmera é
   * deslocada para o mesmo ponto continuar sob o cursor.
   */
  _zoomNaRoda(ev) {
    const ndc = this._ndcDoEvento(ev);
    const bruto = ev.deltaY / (ev.deltaMode === 1 ? 3 : ev.deltaMode === 2 ? 1 : 100);
    const cliques = Math.max(-CLIQUES_MAX, Math.min(CLIQUES_MAX, bruto || Math.sign(ev.deltaY)));
    if (!cliques) return;
    const k = Math.pow(FATOR_ZOOM, cliques);       // k > 1 afasta, k < 1 aproxima
    this.concluirAnimacao();

    if (this.projecao === 'perspectiva') {
      const foco = this._focoDoCursor(ndc);
      this.focoDoZoom = foco.clone();          // conferido pela verificação do zoom
      const pos = this.perspectiva.position;
      const d = Math.max(pos.distanceTo(foco), 1e-6);
      const limitada = Math.min(Math.max(d * k, this.controles.minDistance),
                                this.controles.maxDistance);
      const fator = limitada / d;
      if (Math.abs(fator - 1) < 1e-6) return;
      pos.sub(foco).multiplyScalar(fator).add(foco);
      this.controles.target.sub(foco).multiplyScalar(fator).add(foco);
    } else {
      const antes = this._mundoNoCursor(ndc);
      this.focoDoZoom = antes.clone();
      this.apoioDoZoom = 'plano da tela';
      this.ortografica.zoom = Math.min(Math.max(this.ortografica.zoom / k, 1e-4), 1e5);
      this.ortografica.updateProjectionMatrix();
      const desloc = antes.sub(this._mundoNoCursor(ndc));
      this.ortografica.position.add(desloc);
      this.controles.target.add(desloc);
    }

    this.ativa.updateMatrixWorld();
    this.controles.update();
    if (this.cena) {
      this.cena.ajustarGradeAoZoom(this.distancia, this.mmPorPixel());
      this.cena.pedirQuadro();
    }
    if (this.aoMover) this.aoMover();
  }

  // -------------------------------------------------------------- vistas

  /** Vai para uma vista padrão, com transição suave. */
  vista(nome, caixaMM = null) {
    const v = VISTAS[nome];
    if (!v) return;
    const caixa = caixaMM || (this.cena && this.cena.documento.caixa());
    const { centro, raio } = esferaDe(caixa);
    const dist = Math.max(raio * 2.4, 2);
    const dir = new THREE.Vector3(...v.dir).normalize();
    const destino = centro.clone().addScaledVector(dir, dist);
    // O "cima" muda na vista de topo, senão a câmera fica indefinida.
    this.perspectiva.up.set(...v.cima);
    this.ortografica.up.set(...v.cima);
    this.irPara(destino, centro);
  }

  /** Zoom que mostra o modelo inteiro. */
  zoomExtensao(caixaMM = null) {
    const caixa = caixaMM || (this.cena && this.cena.documento.caixa());
    this._enquadrarSuave(caixa);
  }

  /**
   * Antes de orbitar, põe o pivô onde o usuário está olhando. Com peça selecionada, o
   * pivô é o centro dela (a vista desliza para centrá-la): a órbita gira em volta da
   * peça, como nos CADs. Sem seleção, o pivô vai para a profundidade da peça sob o
   * cursor, no eixo da vista — a tela não pula. Antes o pivô ficava onde o último
   * enquadramento o deixou; de perto de uma chapa, a câmera girava em torno de um ponto
   * metros atrás e a peça sumia da tela.
   */
  _pivoDaOrbita(ev) {
    const alvo = this.controles.target;
    const ids = this.idsSelecionados ? this.idsSelecionados() : [];
    if (ids && ids.length && this.cena) {
      const caixa = this.cena.documento.caixa(ids);
      if (caixa) {
        const { centro } = esferaDe(caixa);
        const d = centro.clone().sub(alvo);
        if (d.lengthSq() > 1e-12) {
          this._animacao = null;
          this.ativa.position.add(d);
          alvo.copy(centro);
          this.controles.update();
        }
        return;
      }
    }
    const p = this._focoDoCursor(this._ndcDoEvento(ev));
    if (this.apoioDoZoom !== 'peça') return;
    const dir = new THREE.Vector3();
    this.ativa.getWorldDirection(dir);
    const prof = p.clone().sub(this.ativa.position).dot(dir);
    if (prof > 1e-4) {
      alvo.copy(this.ativa.position).addScaledVector(dir, prof);
      this.controles.update();
    }
  }

  /**
   * Órbita em volta do ponto da peça sob o cursor, como no SketchUp: a câmera e o alvo
   * giram juntos em torno desse ponto (em volta do Z e do eixo horizontal da tela), então
   * ele fica parado na tela e nada pula. Antes, com peça selecionada, o pivô ia para o
   * centro da seleção e a vista deslizava até ele — com uma terça de 8 m selecionada, o
   * usuário que queria girar na ponta dela via a câmera ir para o meio da barra.
   * Devolve false quando não há peça sob o cursor (fica o pivô de `_pivoDaOrbita`).
   */
  _orbitarNoCursor(ev) {
    const p = this._focoDoCursor(this._ndcDoEvento(ev));
    if (this.apoioDoZoom !== 'peça') return false;
    this._animacao = null;
    this.pivoDaOrbita = p.clone();                 // conferido pela verificação
    let ultimo = { x: ev.clientX, y: ev.clientY };
    const mover = (e) => {
      const dx = e.clientX - ultimo.x, dy = e.clientY - ultimo.y;
      ultimo = { x: e.clientX, y: e.clientY };
      if (dx || dy) this.girarEmVolta(p, dx, dy);
    };
    const soltar = () => {
      window.removeEventListener('pointermove', mover, true);
      window.removeEventListener('pointerup', soltar, true);
      window.removeEventListener('pointercancel', soltar, true);
    };
    window.addEventListener('pointermove', mover, true);
    window.addEventListener('pointerup', soltar, true);
    window.addEventListener('pointercancel', soltar, true);
    return true;
  }

  /** Gira câmera e alvo em volta de `pivo` pelo arrasto (dx, dy) em pixels, no mesmo
   *  sentido e na mesma velocidade da órbita do OrbitControls. */
  girarEmVolta(pivo, dx, dy) {
    const k = (2 * Math.PI / Math.max(this.elemento.clientHeight || 1, 1)) * this.controles.rotateSpeed;
    const cam = this.ativa, alvo = this.controles.target;
    const cima = new THREE.Vector3(0, 0, 1);
    const dir = alvo.clone().sub(cam.position).normalize();
    const direita = new THREE.Vector3().crossVectors(dir, cima);
    const q = new THREE.Quaternion().setFromAxisAngle(cima, -dx * k);
    if (direita.lengthSq() > 1e-10) {
      const qx = new THREE.Quaternion().setFromAxisAngle(direita.normalize(), -dy * k);
      const junto = q.clone().multiply(qx);
      const nova = dir.clone().applyQuaternion(junto);
      const polar = Math.acos(Math.max(-1, Math.min(1, nova.dot(cima))));
      if (polar > 0.02 && polar < Math.PI - 0.02) q.copy(junto);   // não passa do zênite
    }
    for (const v of [cam.position, alvo]) v.sub(pivo).applyQuaternion(q).add(pivo);
    cam.lookAt(alvo);
    cam.updateMatrixWorld();
    this.controles.update();
    this.controles.dispatchEvent({ type: 'change' });
  }

  /** Zoom no que está selecionado. */
  zoomSelecao(ids) {
    if (!this.cena || !ids || !ids.length) return this.zoomExtensao();
    this._enquadrarSuave(this.cena.documento.caixa(ids));
  }

  /** Enquadramento imediato, sem animação (usado na abertura). */
  enquadrar(caixaMM) {
    const { centro, raio } = esferaDe(caixaMM);
    const dist = this._distanciaPara(raio);
    const dir = this.ativa.position.clone().sub(this.controles.target);
    if (dir.lengthSq() < 1e-9) dir.set(0.82, -1, 0.72);
    dir.normalize();
    this.controles.target.copy(centro);
    this.ativa.position.copy(centro).addScaledVector(dir, dist);
    if (this.projecao === 'ortografica') {
      const base = this.ortografica.top - this.ortografica.bottom;
      this.ortografica.zoom = base / Math.max(raio * 2.4, 1e-6);
      this.ortografica.updateProjectionMatrix();
    }
    this.controles.update();
    if (this.cena) { this.cena.ajustarGradeAoZoom(this.distancia, this.mmPorPixel()); this.cena.pedirQuadro(); }
  }

  _enquadrarSuave(caixaMM) {
    const { centro, raio } = esferaDe(caixaMM);
    const dist = this._distanciaPara(raio);
    const dir = this.ativa.position.clone().sub(this.controles.target);
    if (dir.lengthSq() < 1e-9) dir.set(0.82, -1, 0.72);
    dir.normalize();
    this.irPara(centro.clone().addScaledVector(dir, dist), centro, raio);
  }

  _distanciaPara(raio) {
    const f = THREE.MathUtils.degToRad(this.perspectiva.fov);
    const vertical = raio / Math.sin(f / 2);
    const horizontal = raio / Math.sin(Math.atan(Math.tan(f / 2) * this.ativa.aspect || f / 2));
    return Math.max(vertical, horizontal || 0, 1.2) * 1.08;
  }

  /** Transição suave de posição e alvo. */
  irPara(posicao, alvo, raio = null, duracao = 420) {
    const p0 = this.ativa.position.clone();
    const a0 = this.controles.target.clone();
    const z0 = this.ortografica.zoom;
    const z1 = raio
      ? (this.ortografica.top - this.ortografica.bottom) / Math.max(raio * 2.35, 1e-6)
      : z0;
    const inicio = performance.now();
    if (this._animacao) cancelAnimationFrame(this._animacao);
    this._destino = { posicao: posicao.clone(), alvo: alvo.clone(), z1, raio };
    const passo = () => {
      const k = Math.min(1, (performance.now() - inicio) / duracao);
      const s = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;   // ease in-out
      this.ativa.position.lerpVectors(p0, posicao, s);
      this.controles.target.lerpVectors(a0, alvo, s);
      if (this.projecao === 'ortografica' && raio) {
        this.ortografica.zoom = z0 + (z1 - z0) * s;
        this.ortografica.updateProjectionMatrix();
      }
      this.controles.update();
      if (this.cena) { this.cena.ajustarGradeAoZoom(this.distancia, this.mmPorPixel()); this.cena.pedirQuadro(); }
      if (this.aoMover) this.aoMover();
      this._animacao = k < 1 ? requestAnimationFrame(passo) : null;
    };
    passo();
  }

  /** Termina na hora uma transição em curso: a próxima ação parte do destino. */
  concluirAnimacao() {
    if (!this._animacao || !this._destino) return;
    cancelAnimationFrame(this._animacao);
    this._animacao = null;
    const d = this._destino;
    this.ativa.position.copy(d.posicao);
    this.controles.target.copy(d.alvo);
    if (this.projecao === 'ortografica' && d.raio) {
      this.ortografica.zoom = d.z1;
      this.ortografica.updateProjectionMatrix();
    }
    this.controles.update();
    this.ativa.updateMatrixWorld();
    if (this.cena) { this.cena.ajustarGradeAoZoom(this.distancia, this.mmPorPixel()); this.cena.pedirQuadro(); }
    if (this.aoMover) this.aoMover();
  }

  // -------------------------------------------------------------- serviço

  redimensionar(largura, altura) {
    this.largura = Math.max(1, largura);
    this.altura = Math.max(1, altura);
    const razao = this.largura / this.altura;
    this.perspectiva.aspect = razao;
    this.perspectiva.updateProjectionMatrix();
    const h = (this.ortografica.top - this.ortografica.bottom) || 30;
    this.ortografica.left = -h * razao / 2;
    this.ortografica.right = h * razao / 2;
    this.ortografica.updateProjectionMatrix();
  }

  atualizar() { return this.controles.update(); }

  /** Habilita ou desabilita a órbita — usado durante um arrasto de ferramenta. */
  permitirNavegacao(sim) { this.controles.enabled = !!sim; }

  /** Ponto do documento (mm) projetado para pixels do canvas. */
  paraTela(pontoMM, saida = null) {
    const v = new THREE.Vector3(pontoMM[0] * ESCALA, pontoMM[1] * ESCALA, pontoMM[2] * ESCALA);
    v.project(this.ativa);
    const x = (v.x * 0.5 + 0.5) * this.largura;
    const y = (-v.y * 0.5 + 0.5) * this.altura;
    if (saida) { saida[0] = x; saida[1] = y; return saida; }
    return [x, y, v.z];
  }

  /** Quantos milímetros do documento cabem num pixel, à distância do alvo. */
  mmPorPixel(pontoMM = null) {
    let d;
    if (this.projecao === 'ortografica') {
      d = (this.ortografica.top - this.ortografica.bottom) / this.ortografica.zoom / this.altura;
    } else {
      const alvo = pontoMM
        ? new THREE.Vector3(pontoMM[0] * ESCALA, pontoMM[1] * ESCALA, pontoMM[2] * ESCALA)
        : this.controles.target;
      const dist = this.ativa.position.distanceTo(alvo);
      const f = THREE.MathUtils.degToRad(this.perspectiva.fov);
      d = 2 * dist * Math.tan(f / 2) / this.altura;
    }
    return d / ESCALA;
  }

  descartar() {
    this.elemento.removeEventListener('pointerdown', this._antesDoDown, { capture: true });
    this.elemento.removeEventListener('wheel', this._naRoda, { capture: true });
    this.controles.dispose();
  }
}

/** Esfera que envolve a caixa do documento, já em unidades de cena. */
function esferaDe(caixaMM) {
  const c = caixaMM || [[0, 0, 0], [0, 0, 0]];
  const min = c[0], max = c[1];
  const centro = new THREE.Vector3(
    (min[0] + max[0]) / 2 * ESCALA,
    (min[1] + max[1]) / 2 * ESCALA,
    (min[2] + max[2]) / 2 * ESCALA);
  const raio = Math.max(
    Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2 * ESCALA, 1.5);
  return { centro, raio };
}
