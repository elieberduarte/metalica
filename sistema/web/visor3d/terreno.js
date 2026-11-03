// A obra no terreno do cliente (20/10, o usuário: "vincular a obra a um mapa para ter o modelo apresentado dentro do
// terreno do cliente"): a imagem de satélite (ou a ortofoto do geoportal) no chão do modo ver, na escala e no giro da
// amarração gravada no projeto (saida/local_obra.py — as contas daqui são as mesmas de lá). O painel Terreno acha o
// lugar pelo endereço ou pela coordenada colada do Google Maps, baixa a imagem (fica no projeto: abre sem internet) e
// tem o Ajustar: arrastar a imagem por baixo da obra e girar o norte até as divisas e as ruas encaixarem.

import * as THREE from 'three';
import { superficie, contornoDosEixos, cotasDaMalha, paredesDaMalha } from './chao.js';

const R = 6378137;
const rad = g => g * Math.PI / 180, grau = r => r * 180 / Math.PI;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const cotaTxt = mm => (mm > 0 ? '+' : mm < 0 ? '−' : '') + nf(Math.abs(mm) / 1000, 2);    // +4,00 / 0,00 / −3,50 (m)
const cmTxt = mm => nf(mm / 10, Math.round(mm) % 10 ? 1 : 0);                            // o ajuste fino: 5 / −20 / 2,5 (cm)

/** O ponto do modelo (mm do projeto) em [lat, lon] pela amarração `t` ({lat, lon, ponto, norte}). */
/** Os raios do elipsoide (do meridiano e da primeira vertical) na latitude — a Terra esfera errava 0,5 % no norte–sul
 *  (21/10); as mesmas contas de saida/local_obra.py. */
function raios(lat) {
  const e2 = (1 / 298.257222101) * (2 - 1 / 298.257222101), s2 = Math.sin(rad(lat)) ** 2;
  return [R * (1 - e2) / (1 - e2 * s2) ** 1.5, R / Math.sqrt(1 - e2 * s2)];
}

export function modeloParaGeo(t, x, y) {
  const a = rad(t.norte || 0), dx = (x - t.ponto[0]) / 1000, dy = (y - t.ponto[1]) / 1000;
  const leste = dx * Math.cos(a) + dy * Math.sin(a), norte = -dx * Math.sin(a) + dy * Math.cos(a);
  const [m, n] = raios(t.lat);
  return [t.lat + grau(norte / m), t.lon + grau(leste / (n * Math.cos(rad(t.lat))))];
}

export function geoParaModelo(t, lat, lon) {
  const a = rad(t.norte || 0), [m, n] = raios(t.lat);
  const norte = rad(lat - t.lat) * m, leste = rad(lon - t.lon) * n * Math.cos(rad(t.lat));
  return [t.ponto[0] + (leste * Math.cos(a) - norte * Math.sin(a)) * 1000, t.ponto[1] + (leste * Math.sin(a) + norte * Math.cos(a)) * 1000];
}

const deMercator = (mx, my) => [grau(2 * Math.atan(Math.exp(my / R)) - Math.PI / 2), grau(mx / R)];

/** O plano da imagem no modelo: o meio (mm do projeto), o lado no chão (mm) e o giro em Z (o norte da imagem para cima). */
export function planoDaImagem(t, im) {
  // pelos cantos (os mesmos do IFC, local_obra.para_ifc): o lado leste–oeste e o norte–sul no chão, cada um com o raio
  // do elipsoide dele
  const c = (mx, my) => geoParaModelo(t, ...deMercator(mx, my));
  const a = c(im.x0, im.y0), b = c(im.x1, im.y0), d = c(im.x0, im.y1), e = c(im.x1, im.y1);
  return { meio: [(a[0] + b[0] + d[0] + e[0]) / 4, (a[1] + b[1] + d[1] + e[1]) / 4],
           largura: Math.hypot(b[0] - a[0], b[1] - a[1]), altura: Math.hypot(d[0] - a[0], d[1] - a[1]),
           giro: rad(t.norte || 0) };
}

/** A imagem com as bordas esmaecendo no fundo (sem o recorte quadrado no meio do chão). */
function comBordaSuave(img, maxLado = 8192) {
  const c = document.createElement('canvas');
  // no celular o lado tem teto (o Safari recusa canvas acima de ~16 milhões de pixels e a memória é curta)
  const k = Math.min(1, maxLado / Math.max(img.naturalWidth, img.naturalHeight));
  c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0, c.width, c.height);
  const n = 64, m = document.createElement('canvas');
  m.width = m.height = n;
  const gm = m.getContext('2d'), dados = gm.createImageData(n, n);
  const borda = 0.12;
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const u = (i + 0.5) / n, v = (j + 0.5) / n;
    const d = Math.min(u, v, 1 - u, 1 - v) / borda;
    const a = Math.max(0, Math.min(1, d));
    dados.data[(j * n + i) * 4 + 3] = Math.round(255 * a * a * (3 - 2 * a));
  }
  gm.putImageData(dados, 0, 0);
  g.globalCompositeOperation = 'destination-in';
  g.imageSmoothingEnabled = true;
  g.drawImage(m, 0, 0, c.width, c.height);
  return c;
}

/** A parede do chão em níveis (o muro do subsolo, o degrau entre os níveis): uma cor neutra no lugar da foto esticada. */
function comParede(mat) {
  if (mat.userData.comParede) return;
  mat.userData.comParede = true;
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = 'attribute float parede;\nvarying float vParede;\n'
      + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  vParede = parede;');
    sh.fragmentShader = 'varying float vParede;\n' + sh.fragmentShader.replace('#include <map_fragment>',
      '#include <map_fragment>\n  diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.54, 0.50, 0.45), 0.85 * vParede);');
  };
  mat.customProgramCacheKey = () => 'terreno-parede';
  mat.needsUpdate = true;
}

export class Terreno {
  /** `ui` = {abrirPainel(nome, titulo, html), corpo() (o elemento do painel), situacao(texto), palco} do ver3d.js. */
  constructor(visor, projeto, ui) {
    this.visor = visor;
    this.projeto = projeto;
    this.ui = ui;
    this.api = `/api/projetos/${encodeURIComponent(projeto)}/terreno`;
    this.estado = null;           // {terreno, imagem, fontes}
    this.malha = null;
    this.ajustando = false;
    this.arrasto = null;
    this.ligado = true;
    // o liga/desliga lembrado neste navegador (o modo ver do PC); o celular guarda o dele por obra (ui.chaveLigado = null)
    this.chaveLigado = ui.chaveLigado === undefined ? 'ver3d.terreno' : ui.chaveLigado;
    this.escala = ui.escala || 1;                         // mm do projeto → unidade da cena (o editor: 0,001)
    if (this.chaveLigado) { try { this.ligado = localStorage.getItem(this.chaveLigado) !== '0'; } catch (e) { /* sem armazenamento */ } }
  }

  /** false: o servidor não tem o terreno (o programa instalado, por enquanto só no dev). */
  async carregar() {
    const r = await fetch(this.api, { cache: 'no-store' });
    if (!r.ok) return false;
    this.estado = await r.json();
    await this.montar();
    return true;
  }

  /** O celular (20/10, "levar essa visualização do terreno para o mobile"): a amarração e a imagem do pacote da obra
   *  (terreno.json + terreno.jpg, saida/pacote_celular.py), sem o servidor do PC; só ver, sem o painel. */
  async usar(estado, urlImagem) {
    this.estado = estado;
    this._urlImagem = urlImagem;
    await this.montar();
    return !!this.malha;
  }

  get t() { return this.estado && this.estado.terreno; }
  get imagem() { return this.estado && this.estado.imagem; }

  /** A caixa do modelo em planta (mm do projeto) e o meio dela: o ponto de amarração de saída. */
  caixaDoModelo() {
    const cx = this.visor._caixaModelo, o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0];
    return [cx.min.x + o[0], cx.min.y + o[1], cx.max.x + o[0], cx.max.y + o[1]];
  }

  async montar() {
    this._tirar();
    const t = this.t, im = this.imagem;
    if (!t || !im) { this._atribuicao(); return; }
    const img = new Image();
    img.src = this._urlImagem || `${this.api}/imagem.jpg?v=${im.versao || 0}`;
    try { await img.decode(); } catch (e) { (this.ui.situacao || (() => {}))('A imagem do terreno não abriu: baixe de novo no painel Terreno.'); return; }
    const tex = new THREE.CanvasTexture(comBordaSuave(img, this.ui.maxLado));
    // a saída do visor é linear (sem a volta para sRGB): a foto vai como está, senão sai escura
    tex.colorSpace = THREE.NoColorSpace;
    tex.anisotropy = this.visor.renderer.capabilities.getMaxAnisotropy();
    // a transparência só onde há obra por trás do chão (usuário, 20/10: no tema claro "a imagem com transparência ficou
    // muito lavada" — misturava a foto inteira com o fundo claro): as peças marcam 1 no estêncil onde aparecem; a foto sai
    // inteira fora delas (opaca) e transparente sobre elas (vazada) — o subsolo à vista, o resto da foto com a cor dela
    const opaca = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false });
    const vazada = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false,
      opacity: 1 - ((this.t && this.t.transparencia) || 0) });
    for (const [m, f] of [[opaca, THREE.NotEqualStencilFunc], [vazada, THREE.EqualStencilFunc]]) {
      m.stencilWrite = true;                              // liga o teste (as operações só mantêm)
      m.stencilRef = 1; m.stencilFunc = f;
      m.stencilFail = m.stencilZFail = m.stencilZPass = THREE.KeepStencilOp;
    }
    const geo = new THREE.PlaneGeometry(1, 1);
    this.malha = new THREE.Mesh(geo, opaca);
    this.vazada = new THREE.Mesh(geo, vazada);
    this.malha.add(this.vazada);
    this.malha.name = 'terreno';
    for (const m of [this.malha, this.vazada]) {
      m.renderOrder = -0.5;                               // depois do piso liso, antes das peças transparentes
      m.raycast = () => {};                               // não se escolhe nem mede no chão de foto
    }
    this.malha.onBeforeRender = () => {
      if (this._marcarObra()) this.visor.pedirQuadro();                                    // peças novas (outra situação)
      // os eixos chegaram depois do terreno (a referência vem em paralelo): a face do prédio entra no chão em níveis
      if (this._pontosDeNivel().length && this.visor._dadosReferencia !== this._referenciaUsada) setTimeout(() => this.posicionar(), 0);
      if (this.pinos) this.pinos.visible = this._pinosAVista();
    };
    this._marcarObra();
    this.grupo = new THREE.Group();
    this.grupo.add(this.malha);
    this.visor.cena.add(this.grupo);
    this.posicionar();
    this.mostrar(this.ligado);
  }

  /** As peças da obra marcam 1 no estêncil onde aparecem (a imagem fica transparente só ali). true = marcou alguma nova. */
  _marcarObra() {
    let novas = false;
    for (const m of this.visor.malhas || []) {
      const mat = m.malha && m.malha.material;
      if (!mat || mat.userData.marcaTerreno) continue;
      mat.stencilWrite = true; mat.stencilRef = 1;
      mat.stencilFunc = THREE.AlwaysStencilFunc; mat.stencilZPass = THREE.ReplaceStencilOp;
      mat.userData.marcaTerreno = true;
      novas = true;
    }
    return novas;
  }

  _tirar() {
    if (!this.grupo) return;
    this.visor.cena.remove(this.grupo);
    this.malha.geometry.dispose(); this.malha.material.map.dispose(); this.malha.material.dispose(); this.vazada.material.dispose();
    if (this._plano && this._plano !== this.malha.geometry) this._plano.dispose();
    this._tirarPinos();
    this.grupo = this.malha = this.vazada = this._plano = this._geoChao = this._sup = null;
    this.visor.pedirQuadro();
  }

  /** Põe o plano pela amarração (e pelo arrasto em curso). */
  posicionar() {
    if (!this.malha) return;
    const p = planoDaImagem(this.t, this.imagem);
    const o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0];
    const d = this.arrasto ? this.arrasto.d : [0, 0];
    // o editor 3D desenha em metros (ESCALA 0,001, o modelo no grupo escalado); o modo ver e o celular, em mm
    const k = this.escala;
    this.grupo.scale.setScalar(k);
    this.grupo.position.set(-o[0] * k, -o[1] * k, -o[2] * k);
    // na cota escolhida (o nível 0,00 da obra com subsolo: o subsolo fica embaixo do chão, a fundação não voa) ou no pé
    // da obra, logo acima do piso liso (min.z − 10)
    // + o ajuste fino (usuário, 21/10: "de 5 em 5 cm com base em um nível de referência, tipo nível doca (−20 cm)")
    const cota = this.t && Number.isFinite(this.t.cota) ? this.t.cota : null;
    const ajuste = this.t && Number.isFinite(this.t.ajuste) ? this.t.ajuste : 0;
    this.zChao = (cota !== null ? cota - 3 : this.visor._caixaModelo.min.z + o[2] - 6) + ajuste;
    this.malha.position.set(p.meio[0] + d[0], p.meio[1] + d[1], this.zChao);
    this.malha.scale.set(p.largura, p.altura, 1);
    this.malha.rotation.set(0, 0, p.giro);
    this.malha.updateMatrixWorld();
    this._moldarChao({ meio: [p.meio[0] + d[0], p.meio[1] + d[1]], largura: p.largura, altura: p.altura, giro: p.giro });
    this.visor.pedirQuadro();
  }

  // ---------------------------------------------------------------- o chão em mais de um nível (03/11, chao.js)
  // (o usuário pelo SESI Chapecó, 02/11: "uma limitação legal da nossa representação do terreno, quando temos níveis
  // diferentes"; escolhida a malha pelos pontos de nível, 03/11): com pontos no projeto (terreno.niveis, mm do projeto), a
  // imagem vira uma malha que passa por eles; sem pontos, o plano de sempre

  /** Os pontos de nível do chão gravados no projeto: [{x, y, z}] (mm do projeto). */
  _pontosDeNivel() { return (this.t && Array.isArray(this.t.niveis)) ? this.t.niveis : []; }

  /** A cota do chão (mm do projeto) onde a imagem passa em (x, y): a dos pontos de nível, ou a do plano. */
  cotaEm(x, y) {
    if (!this._sup) return this.zChao;
    const aj = this.t && Number.isFinite(this.t.ajuste) ? this.t.ajuste : 0;
    return this._sup.cota(x, y) + aj - 3;
  }

  _moldarChao(g) {
    const niv = this._pontosDeNivel(), m = this.malha;
    if (!niv.length) {
      this._sup = null;
      if (this._plano && m.geometry !== this._plano) { m.geometry = this.vazada.geometry = this._plano; }
      this._tirarPinos();
      return;
    }
    if (!this._plano) this._plano = m.geometry;
    // arrastando a imagem (Ajustar) ou girando o norte: a malha refeita no fim do movimento, não a cada quadro (~0,2 s)
    clearTimeout(this._esperaChao);
    if (this.arrasto || performance.now() - (this._ultimoChao || 0) < 150) {
      this._esperaChao = setTimeout(() => this._moldarChao(g), 160);
      return;
    }
    const aj = this.t && Number.isFinite(this.t.ajuste) ? this.t.ajuste : 0;
    const base = this.zChao - aj + 3;                     // o plano de antes: o chão de longe volta a ele
    const ref = this.visor._dadosReferencia;
    this._referenciaUsada = ref;
    const contorno = contornoDosEixos(((ref && ref.eixos) || []).map(e => ({ a: e.a, b: e.b })));
    const chave = JSON.stringify([niv, contorno, base]);
    if (!this._sup || this._chaveSup !== chave) {
      this._sup = superficie(niv, { base, contorno, raio: Math.hypot(g.largura, g.altura) * 0.75 });
      this._chaveSup = chave;
    }
    // ~0,8 m por quadrinho (a imagem de 446 m: 512); no celular a metade
    const n = Math.round(Math.max(64, Math.min(this.ui.maxLado ? 256 : 512, Math.max(g.largura, g.altura) / 800)));
    const z = cotasDaMalha(this._sup, { ...g, n });
    let geo = this._geoChao;
    if (!geo || geo.parameters.widthSegments !== n) {
      if (geo) geo.dispose();
      geo = this._geoChao = new THREE.PlaneGeometry(1, 1, n, n);
      geo.setAttribute('parede', new THREE.BufferAttribute(new Float32Array((n + 1) * (n + 1)), 1));
    }
    const pos = geo.attributes.position, par = geo.attributes.parede;
    for (let v = 0; v < pos.count; v++) pos.setZ(v, z[v] + aj - 3 - this.zChao);
    par.array.set(paredesDaMalha(z, n, [g.largura / n, g.altura / n]));
    pos.needsUpdate = par.needsUpdate = true;
    geo.computeBoundingSphere(); geo.computeBoundingBox();
    m.geometry = this.vazada.geometry = geo;
    for (const mat of [m.material, this.vazada.material]) comParede(mat);
    this._montarPinos();
    this._ultimoChao = performance.now();
    this.visor.pedirQuadro();
  }

  _pinosAVista() { return !!(this.verPontos && this.ui.painelAtual && this.ui.painelAtual() === 'terreno'); }

  _tirarPinos() {
    if (!this.pinos) return;
    this.pinos.parent && this.pinos.parent.remove(this.pinos);
    this.pinos.traverse(o => { if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } if (o.geometry) o.geometry.dispose(); });
    this.pinos = null;
  }

  /** Os pontos de nível no 3D (com o painel Terreno aberto e "Mostrar os pontos"): uma haste e a cota escrita. */
  _montarPinos() {
    this._tirarPinos();
    const niv = this._pontosDeNivel();
    if (!niv.length || !this.grupo) return;
    const cx = this.visor._caixaModelo, k = Math.max(400, Math.min(4000, cx.min.distanceTo(cx.max) / 80));
    this.pinos = new THREE.Group();
    this.pinos.name = 'terreno-niveis';
    const aj = this.t && Number.isFinite(this.t.ajuste) ? this.t.ajuste : 0;
    const haste = new THREE.CylinderGeometry(k * 0.04, k * 0.04, k, 6).rotateX(Math.PI / 2).translate(0, 0, k / 2);
    const matHaste = new THREE.MeshBasicMaterial({ color: 0xe8590c, depthTest: false });
    niv.forEach((p, i) => {
      const h = new THREE.Mesh(haste, matHaste);
      h.position.set(p.x, p.y, p.z + aj);
      h.renderOrder = 10;
      const c = document.createElement('canvas'); c.width = 256; c.height = 64;
      const g = c.getContext('2d');
      g.fillStyle = 'rgba(232,89,12,.92)'; g.beginPath(); g.roundRect(4, 6, 248, 52, 12); g.fill();
      g.fillStyle = '#fff'; g.font = 'bold 36px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(cotaTxt(p.z), 128, 33);
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.NoColorSpace;
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
      s.scale.set(k * 1.6, k * 0.4, 1);
      s.position.set(p.x, p.y, p.z + aj + k * 1.25);
      s.renderOrder = 11;
      s.userData.indice = i;
      this.pinos.add(h, s);
    });
    this.pinos.visible = this._pinosAVista();
    this.grupo.add(this.pinos);
  }

  mostrar(sim) {
    this.ligado = !!sim;
    if (this.chaveLigado) { try { localStorage.setItem(this.chaveLigado, sim ? '1' : '0'); } catch (e) { /* sem armazenamento */ } }
    if (this.grupo) this.grupo.visible = this.ligado;
    this._atribuicao();
    this.visor.pedirQuadro();
  }

  /** A fonte da imagem no canto (a Esri pede; o geoportal também). */
  _atribuicao() {
    let el = document.getElementById('terreno-fonte');
    const texto = this.grupo && this.ligado && this.imagem ? this.imagem.atribuicao || this.imagem.fonte : '';
    if (!texto) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement('div'); el.id = 'terreno-fonte'; this.ui.palco.appendChild(el); }
    el.textContent = texto;
  }

  // ---------------------------------------------------------------- o painel

  painel() {
    const t = this.t, im = this.imagem, fontes = (this.estado && this.estado.fontes) || [];
    const fonteAtual = t && t.fonte ? (typeof t.fonte === 'object' ? 'wms' : t.fonte) : 'esri';
    const wms = t && typeof t.fonte === 'object' ? t.fonte : { url: '', camada: '' };
    let html = `<p class="titulo-secao">Local da obra</p>
      <form id="terreno-busca" class="terreno-busca"><input id="terreno-q" type="search" autocomplete="off"
        placeholder="Endereço ou coordenada (Google Maps ou geoportal)"><button type="submit">Buscar</button></form>
      <div id="terreno-resultados"></div>`;
    if (t) {
      html += `<dl class="terreno-dl"><dt>Lugar</dt><dd>${esc(t.endereco || 'coordenada')}</dd>
        <dt>Coordenada</dt><dd id="terreno-coord">${nf(t.lat, 6)}, ${nf(t.lon, 6)}</dd>
        <dt>Norte</dt><dd id="terreno-norte-dd">${nf(t.norte, 2)}° do eixo Y</dd>
        ${im ? `<dt>Imagem</dt><dd>${esc(im.fonte)} · ${nf(im.lado_m)} m de lado · ${esc(im.baixada_em)}</dd>` : ''}</dl>`;
      if (im) html += `<label class="linha-lista"><input type="checkbox" id="terreno-ligado" ${this.ligado ? 'checked' : ''}><span>Mostrar a imagem no chão</span></label>
        <p class="titulo-secao">Ajustar a posição</p>
        <button type="button" id="terreno-ajustar" class="${this.ajustando ? 'ligado' : ''}">${this.ajustando ? '✓ Terminar o ajuste' : '✥ Ajustar (arrastar a imagem)'}</button>
        <div class="terreno-norte"><span>Norte</span>
          <button type="button" data-passo="-1" title="Girar 1° no sentido horário">−1°</button><button type="button" data-passo="-0.1">−0,1°</button>
          <input id="terreno-norte-num" type="text" inputmode="decimal" value="${nf(t.norte, 2)}" aria-label="Norte (graus)"><span>°</span>
          <button type="button" data-passo="0.1">+0,1°</button><button type="button" data-passo="1" title="Girar 1° no sentido anti-horário">+1°</button></div>
        <input type="range" id="terreno-norte" class="terreno-norte-barra" min="-180" max="180" step="0.01" value="${t.norte}" aria-label="Giro do norte">
        <p class="dica">No Ajustar, arraste a imagem por baixo da obra (de cima, na vista Topo, fica mais fácil) e gire o norte até
          as divisas e as ruas encaixarem. Grava sozinho.</p>`;
      if (im) {
        const niv = this._niveis(), temCota = Number.isFinite(t.cota);
        const naLista = temCota && niv.some(n => n.z === Math.round(t.cota));
        html += `<p class="titulo-secao">Altura da imagem</p>
          <div class="terreno-cota"><select id="terreno-cota-sel" aria-label="Altura da imagem">
            <option value="auto" ${temCota ? '' : 'selected'}>No pé da obra (automático)</option>
            ${niv.map(n => `<option value="${n.z}" ${naLista && Math.round(t.cota) === n.z ? 'selected' : ''}>${esc(n.nome)} (${cotaTxt(n.z)})</option>`).join('')}
            <option value="outra" ${temCota && !naLista ? 'selected' : ''}>Outra cota…</option></select>
            <span id="terreno-cota-outra" ${temCota && !naLista ? '' : 'hidden'}><input id="terreno-cota" type="text" inputmode="decimal"
              value="${temCota ? nf(t.cota / 1000, 2) : '0,00'}" aria-label="Cota da imagem (m)"> m</span></div>
          <div class="terreno-norte terreno-ajuste"><span>Ajuste</span>
            <button type="button" data-ajuste="-50" title="Descer a imagem 5 cm">−5 cm</button>
            <input id="terreno-ajuste" type="text" inputmode="decimal" value="${cmTxt(t.ajuste || 0)}"
              aria-label="Ajuste fino da altura da imagem (cm)"><span>cm</span>
            <button type="button" data-ajuste="50" title="Subir a imagem 5 cm">+5 cm</button></div>
          <p class="dica" id="terreno-cota-final">${esc(this._cotaFinal())}</p>
          <p class="dica">Obra com subsolo: a imagem no nível do terreno (o 0,00) deixa o subsolo embaixo do chão e a fundação
            no lugar.</p>
          <div class="sol-controles"><label>Transparência <output id="terreno-transp-saida">${Math.round((t.transparencia || 0) * 100)} %</output>
            <input type="range" id="terreno-transp" min="0" max="90" step="5" value="${Math.round((t.transparencia || 0) * 100)}"
              aria-label="Transparência da imagem"></label></div>`;
        html += this._painelNiveis();
      }
      html += `<p class="titulo-secao">Imagem</p>
        <label class="terreno-fonte-sel">Fonte <select id="terreno-fonte-sel">${fontes.map(f => `<option value="${esc(f.chave)}" ${f.chave === fonteAtual ? 'selected' : ''}>${esc(f.nome)}</option>`).join('')}
          <option value="wms" ${fonteAtual === 'wms' ? 'selected' : ''}>Outro geoportal (link)…</option></select></label>
        <div id="terreno-wms" ${fonteAtual === 'wms' ? '' : 'hidden'}>
          <input id="terreno-wms-url" placeholder="Link do geoportal ou do serviço (https://…)" value="${esc(wms.url)}">
          <input id="terreno-wms-camada" placeholder="Camada (se não vier no link)" value="${esc(wms.camada)}">
          <p class="dica">Cole o link do serviço de imagem (WMS) ou o endereço de um pedido GetMap: no geoportal, F12 → aba
            Rede, escreva GetMap no filtro, mexa no mapa e copie o endereço de uma linha. A camada vem junto.</p></div>
        <button type="button" id="terreno-baixar" class="forte">${im ? 'Baixar a imagem de novo' : 'Baixar a imagem do terreno'}</button>
        <button type="button" id="terreno-esquecer">Tirar o local</button>
        ${this._painelPropria()}`;
    } else {
      html += `<p class="dica">Ache o terreno pelo endereço, ou cole a coordenada: do Google Maps (botão direito no lote → a
        primeira linha) ou do geoportal da prefeitura (a latitude e a longitude do lote, em graus/minutos/segundos, ou a UTM
        SIRGAS 2000). A obra entra com o meio no ponto achado; depois o Ajustar acerta a posição e o giro.</p>
        ${this._painelPropria()}`;
    }
    this.ui.abrirPainel('terreno', 'Terreno', `<div class="painel-terreno">${html}</div>`);
    this._ligarPainel();
  }

  _ligarPainel() {
    const raiz = this.ui.corpo(), $ = s => raiz.querySelector(s);
    $('#terreno-busca').onsubmit = (ev) => { ev.preventDefault(); this._buscar($('#terreno-q').value); };
    const cb = $('#terreno-ligado');
    if (cb) cb.onchange = () => { this.mostrar(cb.checked); this.ui.aoMudar(); };
    const aj = $('#terreno-ajustar');
    if (aj) aj.onclick = () => { this.ajustar(!this.ajustando); this.painel(); };
    // o norte fino (usuário, 20/10: "só vai de 0,5 em 0,5, poderia ser mais fino"): a barra de 0,01°, o número digitado
    // (vírgula ou ponto) e os botões de 0,1° e 1°
    const nor = $('#terreno-norte'), num = $('#terreno-norte-num');
    const definirNorte = (v, deOnde) => {
      if (!Number.isFinite(v)) return;
      v = Math.round((((v + 180) % 360 + 360) % 360 - 180) * 100) / 100;
      this.t.norte = v;
      if (deOnde !== 'barra') nor.value = v;
      if (deOnde !== 'numero') num.value = nf(v, 2);
      $('#terreno-norte-dd').textContent = nf(v, 2) + '° do eixo Y';
      this.posicionar();
      this._gravarLogo();
    };
    if (nor) {
      nor.oninput = () => definirNorte(+nor.value, 'barra');
      num.oninput = () => definirNorte(parseFloat(String(num.value).replace(',', '.')), 'numero');
      num.onblur = () => { num.value = nf(this.t.norte, 2); };
      num.onkeydown = (ev) => {
        if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
        ev.preventDefault();
        definirNorte(this.t.norte + (ev.key === 'ArrowUp' ? 1 : -1) * (ev.shiftKey ? 1 : 0.1));
      };
      raiz.querySelectorAll('[data-passo]').forEach(b => { b.onclick = () => definirNorte(this.t.norte + +b.dataset.passo); });
    }
    const cs = $('#terreno-cota-sel'), ci = $('#terreno-cota');
    if (cs) {
      const aplicar = (mm) => {
        if (mm === null) delete this.t.cota; else this.t.cota = mm;
        this.posicionar();
        this._gravarLogo();
      };
      const digitada = () => { const v = parseFloat(String(ci.value).replace(',', '.')); return Number.isFinite(v) ? Math.round(v * 1000) : null; };
      cs.onchange = () => {
        const outra = cs.value === 'outra';
        $('#terreno-cota-outra').hidden = !outra;
        if (cs.value === 'auto') aplicar(null);
        else if (outra) { ci.focus(); aplicar(digitada() ?? 0); }
        else aplicar(+cs.value);
      };
      ci.oninput = () => { const mm = digitada(); if (mm !== null) aplicar(mm); };
      // o ajuste fino em cima do nível escolhido: os botões de 5 cm, as setas do teclado (5 cm) e o número digitado (cm)
      const ca = $('#terreno-ajuste');
      const ajustar = (mm, deOnde) => {
        if (!Number.isFinite(mm)) return;
        mm = Math.max(-100000, Math.min(100000, Math.round(mm)));
        if (mm) this.t.ajuste = mm; else delete this.t.ajuste;
        if (deOnde !== 'numero') ca.value = cmTxt(mm);
        $('#terreno-cota-final').textContent = this._cotaFinal();
        this.posicionar();
        this._gravarLogo();
      };
      ca.oninput = () => ajustar(parseFloat(String(ca.value).replace(',', '.')) * 10, 'numero');
      ca.onblur = () => { ca.value = cmTxt(this.t.ajuste || 0); };
      ca.onkeydown = (ev) => {
        if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
        ev.preventDefault();
        ajustar((this.t.ajuste || 0) + (ev.key === 'ArrowUp' ? 50 : -50));
      };
      raiz.querySelectorAll('[data-ajuste]').forEach(b => { b.onclick = () => ajustar((this.t.ajuste || 0) + +b.dataset.ajuste); });
      const cotaFinal = () => { $('#terreno-cota-final').textContent = this._cotaFinal(); };
      cs.addEventListener('change', cotaFinal);
      ci.addEventListener('input', cotaFinal);
    }
    // a transparência (o subsolo à vista através do chão)
    const tr = $('#terreno-transp');
    if (tr) tr.oninput = () => {
      const v = Math.min(Math.max(+tr.value, 0), 90) / 100;
      if (v > 0) this.t.transparencia = v; else delete this.t.transparencia;
      $('#terreno-transp-saida').textContent = Math.round(v * 100) + ' %';
      if (this.vazada) { this.vazada.material.opacity = 1 - v; this.visor.pedirQuadro(); }
      this._gravarLogo();
    };
    const sel = $('#terreno-fonte-sel');
    if (sel) sel.onchange = () => { $('#terreno-wms').hidden = sel.value !== 'wms'; };
    const bx = $('#terreno-baixar');
    if (bx) bx.onclick = () => this._baixar();
    this._ligarPropria(raiz);
    this._ligarNiveis(raiz);
    const sq = $('#terreno-esquecer');
    if (sq) sq.onclick = async () => {
      if (!confirm('Tirar o local da obra deste projeto? A imagem baixada fica na pasta, mas some do 3D.')) return;
      this.ajustar(false);
      this.estado = await this._pedir('/esquecer', {});
      await this.montar(); this.ui.aoMudar(); this.painel();
    };
  }

  // ---------------------------------------------------------------- os níveis do chão (o painel)

  _painelNiveis() {
    const niv = this._pontosDeNivel();
    let html = `<p class="titulo-secao">Níveis do chão</p>
      <p class="dica">Pontos com a cota do chão (a calçada −0,50, o pátio do subsolo −3,98, a rampa…): a imagem passa por eles e
        encosta no prédio pelo lado de fora. Sem pontos, a imagem fica plana na altura acima.</p>
      <button type="button" id="terreno-nivel-marcar" class="${this.marcandoNivel ? 'ligado' : ''}">${this.marcandoNivel
        ? '✓ Terminar de marcar' : '+ Ponto de nível (clique no chão)'}</button>`;
    if (niv.length) {
      html += `<label class="linha-lista"><input type="checkbox" id="terreno-niveis-ver" ${this.verPontos ? 'checked' : ''}><span>Mostrar os
          ${niv.length} pontos no 3D</span></label>
        <div class="terreno-niveis">${niv.map((p, i) => `<div class="terreno-nivel" data-i="${i}">
          <input type="text" inputmode="decimal" data-cota="${i}" value="${esc(cotaTxt(p.z))}" aria-label="Cota do ponto ${i + 1} (m)"><span>m</span>
          <span class="onde" title="${esc(p.nome || '')}">x ${nf(p.x / 1000, 1)} · y ${nf(p.y / 1000, 1)}${p.nome ? ' · ' + esc(p.nome) : ''}</span>
          <button type="button" data-tirar="${i}" title="Tirar este ponto">✕</button></div>`).join('')}</div>
        <button type="button" id="terreno-niveis-tirar">Tirar todos os pontos</button>`;
    }
    return html;
  }

  _ligarNiveis(raiz) {
    const $ = s => raiz.querySelector(s);
    const bm = $('#terreno-nivel-marcar');
    if (bm) bm.onclick = () => { this.marcarNivel(!this.marcandoNivel); this.painel(); };
    const vp = $('#terreno-niveis-ver');
    if (vp) vp.onchange = () => { this.verPontos = vp.checked; if (this.pinos) this.pinos.visible = this._pinosAVista(); this.visor.pedirQuadro(); };
    raiz.querySelectorAll('[data-cota]').forEach(inp => {
      const i = +inp.dataset.cota;
      inp.onchange = () => {
        const v = parseFloat(String(inp.value).replace('−', '-').replace('+', '').replace(',', '.'));
        if (!Number.isFinite(v) || !this._pontosDeNivel()[i]) { if (this._pontosDeNivel()[i]) inp.value = cotaTxt(this._pontosDeNivel()[i].z); return; }
        this.t.niveis[i] = { ...this.t.niveis[i], z: Math.round(v * 1000) };
        inp.value = cotaTxt(this.t.niveis[i].z);
        this.posicionar(); this._gravarLogo();
      };
      inp.onkeydown = (ev) => { if (ev.key === 'Enter') inp.blur(); };
    });
    raiz.querySelectorAll('[data-tirar]').forEach(b => {
      b.onclick = () => { this.t.niveis.splice(+b.dataset.tirar, 1); this._depoisDosNiveis(); };
    });
    const tt = $('#terreno-niveis-tirar');
    if (tt) tt.onclick = () => {
      if (!confirm(`Tirar os ${this._pontosDeNivel().length} pontos de nível? A imagem volta a ficar plana.`)) return;
      this.t.niveis = []; this._depoisDosNiveis();
    };
  }

  _depoisDosNiveis(focar = null) {
    if (!this._pontosDeNivel().length) delete this.t.niveis;
    this.posicionar();
    this._gravarLogo();
    if (this.ui.painelAtual && this.ui.painelAtual() === 'terreno') {
      this.painel();
      if (focar !== null) {
        const inp = this.ui.corpo().querySelector(`[data-cota="${focar}"]`);
        if (inp) { inp.scrollIntoView({ block: 'nearest' }); inp.focus(); inp.select(); }
      }
    }
  }

  /** Marcar pontos de nível: cada clique no chão põe um ponto com a cota que o chão tem ali; a cota se digita na lista. */
  marcarNivel(sim) {
    this.marcandoNivel = !!sim && !!this.malha;
    if (this.marcandoNivel) { this.ajustar(false); this.verPontos = true; if (!this.ligado) this.mostrar(true); }
    this.ui.palco.classList.toggle('marcando-nivel', this.marcandoNivel);
    this._ouvirPalco();
    if (this.pinos) this.pinos.visible = this._pinosAVista();
    this.visor.pedirQuadro();
  }

  /** O ponto do chão sob o mouse (mm do projeto), já na cota do chão em níveis (o raio vai e volta até a malha). */
  _noChaoEmNiveis(ev) {
    let z = this.zChao, p = null;
    for (let k = 0; k < 8; k++) {
      p = this._noChao(ev, z);
      if (!p) return null;
      const z2 = this.cotaEm(p[0], p[1]);
      if (Math.abs(z2 - z) < 1) break;
      z = z2;
    }
    return p;
  }

  _marcarNoChao(ev) {
    const p = this._noChaoEmNiveis(ev);
    if (!p) return;
    const aj = this.t && Number.isFinite(this.t.ajuste) ? this.t.ajuste : 0;
    const z = Math.round(this.cotaEm(p[0], p[1]) - aj + 3);
    this.t.niveis = [...this._pontosDeNivel(), { x: Math.round(p[0]), y: Math.round(p[1]), z }];
    this._depoisDosNiveis(this.t.niveis.length - 1);
  }

  // ---------------------------------------------------------------- a imagem própria (o drone do cliente)
  // (21/10, o usuário: "criar uma opção para importar uma imagem do terreno… talvez o usuário tenha uma imagem própria de
  // drone do local que não esteja nos portais"): o ortomosaico com coordenadas vai sozinho para o lugar, por cima da
  // imagem do portal; a sem coordenadas entra no meio da obra, com a largura em metros

  _painelPropria() {
    const p = this.estado && this.estado.propria;
    let html = `<p class="titulo-secao">Imagem própria (drone)</p>`;
    if (p && p.colocada) {
      html += `<dl class="terreno-dl"><dt>Arquivo</dt><dd>${esc(p.nome)}</dd>
        <dt>Lugar</dt><dd>${p.modo === 'coordenadas' ? `pelas coordenadas da imagem (${esc(p.crs)})` : 'sem coordenadas: no meio da obra'}</dd>
        ${this.imagem && this.imagem.pixel_cm ? `<dt>Resolução</dt><dd>${nf(this.imagem.pixel_cm, 1)} cm por pixel</dd>` : ''}</dl>`;
      if (p.modo === 'sem coordenadas') html += `<div class="terreno-norte terreno-largura"><span>Largura</span>
          <button type="button" data-largura="-10">−10 m</button><button type="button" data-largura="-1">−1 m</button>
          <input id="terreno-largura" type="text" inputmode="decimal" value="${nf(p.largura_m, 1)}" aria-label="Largura da imagem (m)"><span>m</span>
          <button type="button" data-largura="1">+1 m</button><button type="button" data-largura="10">+10 m</button></div>
        <p class="dica">Sem coordenadas, a imagem entra com o norte para cima: acerte a largura até as medidas da obra baterem e use o
          Ajustar e o Norte (acima) para encaixar.</p>`;
      html += `<button type="button" id="terreno-tirar-propria">Tirar a imagem própria</button>`;
    } else {
      html += `<p class="dica">O ortomosaico do drone do local (GeoTIFF do Pix4D, DroneDeploy, Metashape ou WebODM, ou JPG/PNG com o
        .jgw e o .prj): vai sozinho para o lugar, por cima da imagem do portal. Uma imagem sem coordenadas entra no meio da
        obra e você acerta a largura.</p>`;
    }
    html += `<button type="button" id="terreno-importar">${p && p.colocada ? 'Importar outra imagem…' : 'Importar imagem própria…'}</button>
      <input type="file" id="terreno-arquivo" hidden multiple accept=".tif,.tiff,.jpg,.jpeg,.png,.jgw,.pgw,.tfw,.wld,.prj">`;
    return html;
  }

  _ligarPropria(raiz) {
    const $ = s => raiz.querySelector(s);
    const bt = $('#terreno-importar'), arq = $('#terreno-arquivo');
    if (bt) bt.onclick = () => arq.click();
    if (arq) arq.onchange = () => { const l = [...arq.files]; arq.value = ''; if (l.length) this.importarPropria(l); };
    const tp = $('#terreno-tirar-propria');
    if (tp) tp.onclick = async () => {
      if (!confirm('Tirar a imagem própria? Volta a imagem do portal (se houver).')) return;
      try { this.estado = await this._pedir('/tirar-imagem-propria', {}); await this.montar(); this.ui.aoMudar(); }
      catch (e) { this.ui.situacao('Terreno: ' + e.message); }
      this.painel();
    };
    const li = $('#terreno-largura');
    if (li) {
      const p = this.estado.propria;
      const definir = (m) => {
        if (!Number.isFinite(m)) return;
        m = Math.round(Math.max(5, Math.min(20000, m)) * 10) / 10;
        li.value = nf(m, 1);
        p.largura_m = m;
        clearTimeout(this._esperaLargura);
        this._esperaLargura = setTimeout(() => this._posicionarPropria({ largura_m: m }).catch(e => this.ui.situacao('Terreno: ' + e.message)), 400);
      };
      li.onchange = () => definir(parseFloat(String(li.value).replace(',', '.')));
      raiz.querySelectorAll('[data-largura]').forEach(b => { b.onclick = () => definir(p.largura_m + +b.dataset.largura); });
    }
  }

  /** Os arquivos escolhidos: a imagem (GeoTIFF, JPG ou PNG) e, se vierem, o arquivo de mundo (.jgw…) e o .prj. */
  async importarPropria(arquivos) {
    const img = arquivos.find(f => /\.(tiff?|jpe?g|png)$/i.test(f.name));
    if (!img) { alert('Escolha a imagem (GeoTIFF, JPG ou PNG) — o .jgw e o .prj vão junto, se tiver.'); return; }
    const mundoArq = arquivos.find(f => /\.(jgw|pgw|tfw|wld)$/i.test(f.name));
    const prjArq = arquivos.find(f => /\.prj$/i.test(f.name));
    this.ui.situacao(`Terreno: enviando ${img.name} (${nf(img.size / 1048576, 1)} MB)…`);
    try {
      const r = await fetch(this.api + '/importar-imagem', { method: 'POST', body: img,
        headers: { 'Content-Type': 'application/octet-stream', 'X-Nome-Arquivo': encodeURIComponent(img.name) } });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
      this.estado = j;
      const extra = {};
      if (mundoArq) extra.mundo = await mundoArq.text();
      if (prjArq) extra.prj = await prjArq.text();
      if (!j.georreferenciada && !mundoArq && !this.t) {
        throw new Error('a imagem não tem coordenadas: busque o endereço da obra antes (ou importe junto o .jgw e o .prj).');
      }
      await this._posicionarPropria(extra);
    } catch (e) {
      this.ui.situacao('Terreno: ' + e.message);
      alert('A imagem não entrou: ' + e.message);
      if (this.ui.painelAtual() === 'terreno') this.painel();
    }
  }

  async _posicionarPropria(extra) {
    this.estado = await this._pedir('/posicionar-imagem', { caixa: this.caixaDoModelo(), ...extra });
    await this.montar();
    this.mostrar(true);
    this.ui.aoMudar();
    const p = this.estado.propria || {};
    this.ui.situacao(p.modo === 'coordenadas'
      ? `Terreno: ${p.nome} no lugar pelas coordenadas (${p.crs}), ${nf((this.imagem && this.imagem.pixel_cm) || 0, 1)} cm por pixel.`
      : `Terreno: ${p.nome} no meio da obra, ${nf(p.largura_m, 1)} m de largura — acerte a largura e use o Ajustar.`);
    if (this.ui.painelAtual() === 'terreno') this.painel();
  }

  /** "Imagem em −1,40 (Doca −1,20 − 20 cm)": a altura em que a imagem ficou, pelo nível de referência e o ajuste. */
  _cotaFinal() {
    const t = this.t || {}, aj = Number.isFinite(t.ajuste) ? t.ajuste : 0;
    const ajTxt = aj ? ` ${aj > 0 ? '+' : '−'} ${cmTxt(Math.abs(aj))} cm` : '';
    if (!Number.isFinite(t.cota)) return aj ? `Imagem no pé da obra${ajTxt}.` : 'Imagem no pé da obra.';
    const n = this._niveis().find(v => v.z === Math.round(t.cota));
    const ref = n ? `${n.nome}${/[0-9]/.test(n.nome) ? '' : ' ' + cotaTxt(n.z)}` : `cota ${cotaTxt(t.cota)}`;
    return aj ? `Imagem em ${cotaTxt(t.cota + aj)} (${ref}${ajTxt}).` : `Imagem em ${cotaTxt(t.cota)} (${ref}).`;
  }

  /** Os níveis do projeto (os da planta no chão, Planta e níveis), um por cota, com o 0,00 sempre. */
  _niveis() {
    const r = this.visor._dadosReferencia, lista = [], vistos = new Set();
    for (const n of ((r && r.niveis) || [])) {
      const z = Math.round(+n.z);
      if (!Number.isFinite(z) || vistos.has(z)) continue;
      vistos.add(z);
      lista.push({ nome: n.nome || 'nível', z });
    }
    if (!vistos.has(0)) lista.push({ nome: 'Nível 0,00', z: 0 });
    return lista.sort((a, b) => a.z - b.z);
  }

  _fonteDoPainel() {
    const raiz = this.ui.corpo(), sel = raiz.querySelector('#terreno-fonte-sel');
    if (!sel) return (this.t && this.t.fonte) || 'esri';
    if (sel.value !== 'wms') return sel.value;
    return { tipo: 'wms', url: raiz.querySelector('#terreno-wms-url').value.trim(), camada: raiz.querySelector('#terreno-wms-camada').value.trim() };
  }

  async _pedir(sufixo, corpo) {
    const r = await fetch(this.api + sufixo, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
    return j;
  }

  async _buscar(texto) {
    const lugar = this.ui.corpo().querySelector('#terreno-resultados');
    lugar.innerHTML = '<p class="dica">Procurando…</p>';
    try {
      const r = await fetch(`${this.api}/buscar-endereco?q=${encodeURIComponent(texto)}`);
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
      const lista = j.resultados || [];
      lugar.innerHTML = lista.length ? lista.map((x, i) => `<label class="linha-lista" data-i="${i}"><span title="${esc(x.nome)}">${esc(x.nome)}</span></label>`).join('')
        : '<p class="dica">Nada achado. Tente com a cidade (ex.: "Rua Paraná 1000, Cascavel") ou cole a coordenada.</p>';
      lugar.querySelectorAll('[data-i]').forEach(el => el.onclick = () => this._escolher(lista[+el.dataset.i]));
    } catch (e) {
      lugar.innerHTML = `<p class="dica">${esc(e.message)}</p>`;
    }
  }

  /** O lugar achado: o meio da obra vai para ele (o norte fica o que estava) e a imagem vem em seguida. */
  async _escolher(r) {
    const cx = this.caixaDoModelo();
    const t = { lat: r.lat, lon: r.lon, ponto: [(cx[0] + cx[2]) / 2, (cx[1] + cx[3]) / 2], norte: (this.t && this.t.norte) || 0,
                endereco: r.nome, fonte: (this.t && this.t.fonte) || 'esri', caixa: cx,
                // os pontos de nível são do projeto (mm da obra), não do lugar: ficam quando o lugar muda
                ...(this._pontosDeNivel().length ? { niveis: this._pontosDeNivel() } : {}) };
    try {
      this.estado = await this._pedir('', t);
      await this._baixar();
    } catch (e) { this.ui.situacao('Terreno: ' + e.message); }
  }

  async _baixar() {
    const bx = this.ui.corpo().querySelector('#terreno-baixar');
    if (bx) { bx.disabled = true; bx.textContent = 'Baixando…'; }
    try {
      const fonte = this._fonteDoPainel();
      if (JSON.stringify(fonte) !== JSON.stringify(this.t.fonte)) this.estado = await this._pedir('', { ...this.t, fonte });
      this.estado = await this._pedir('/baixar-imagem', { caixa: this.caixaDoModelo() });
      await this.montar();
      this.mostrar(true);
      this.ui.aoMudar();
      this.ui.situacao(`Terreno: imagem de ${nf(this.imagem.lado_m)} m de lado (${esc(this.imagem.fonte)}), guardada no projeto.`);
    } catch (e) {
      this.ui.situacao('Terreno: ' + e.message);
      alert('A imagem do terreno não veio: ' + e.message);
    }
    if (this.ui.painelAtual() === 'terreno') this.painel();
  }

  _gravarLogo() {
    clearTimeout(this._espera);
    this._espera = setTimeout(async () => {
      try { this.estado = { ...this.estado, ...(await this._pedir('', this.t)) }; }
      catch (e) { this.ui.situacao('Terreno: não gravou (' + e.message + ')'); }
    }, 500);
  }

  // ---------------------------------------------------------------- o Ajustar (arrastar a imagem)

  ajustar(sim) {
    this.ajustando = !!sim && !!this.malha;
    if (this.ajustando && this.marcandoNivel) this.marcarNivel(false);
    this.ui.palco.classList.toggle('ajustando-terreno', this.ajustando);
    this._ouvirPalco();
    if (this.ajustando && !this.ligado) this.mostrar(true);
  }

  _ouvirPalco() {
    if (this._ouvindo || !(this.ajustando || this.marcandoNivel)) return;
    this._ouvindo = true;
    const palco = this.ui.palco;
    // na captura, no palco: o arrasto não chega à tela (nem à órbita nem à escolha de peça); a roda continua no zoom
    palco.addEventListener('pointerdown', ev => this._inicio(ev), true);
    window.addEventListener('pointermove', ev => this._move(ev));
    window.addEventListener('pointerup', ev => this._fim(ev));
    window.addEventListener('keydown', ev => {
      if (ev.key !== 'Escape' || !this.marcandoNivel) return;
      this.marcarNivel(false);
      if (this.ui.painelAtual() === 'terreno') this.painel();
    });
  }

  _noChao(ev, zChao = this.zChao) {
    const tela = this.visor.renderer.domElement, r = tela.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.visor.camera);
    const o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0], k = this.escala;
    const plano = new THREE.Plane(new THREE.Vector3(0, 0, 1), -(zChao - o[2]) * k);
    const p = ray.ray.intersectPlane(plano, new THREE.Vector3());
    return p ? [p.x / k + o[0], p.y / k + o[1]] : null;
  }

  _inicio(ev) {
    if (this.marcandoNivel && ev.button === 0 && ev.target === this.visor.renderer.domElement) {
      // o clique parado marca o ponto; o arrasto continua girando a vista
      this._cliqueNivel = { x: ev.clientX, y: ev.clientY };
      return;
    }
    if (!this.ajustando || ev.button !== 0 || ev.target !== this.visor.renderer.domElement) return;
    const p = this._noChao(ev);
    if (!p) return;
    ev.stopPropagation(); ev.preventDefault();
    this.arrasto = { p0: p, d: [0, 0] };
  }

  _move(ev) {
    if (!this.arrasto) return;
    const p = this._noChao(ev);
    if (!p) return;
    this.arrasto.d = [p[0] - this.arrasto.p0[0], p[1] - this.arrasto.p0[1]];
    this.posicionar();
  }

  /** Soltou: a imagem andou `d` por baixo da obra — o ponto de amarração do modelo passa a cair no lugar do mundo que
   *  estava em `ponto − d`. */
  _fim(ev) {
    if (this._cliqueNivel) {
      const c = this._cliqueNivel;
      this._cliqueNivel = null;
      if (this.marcandoNivel && ev && Math.hypot(ev.clientX - c.x, ev.clientY - c.y) < 5) this._marcarNoChao(ev);
      return;
    }
    if (!this.arrasto) return;
    const d = this.arrasto.d;
    this.arrasto = null;
    if (Math.hypot(d[0], d[1]) < 1) { this.posicionar(); return; }
    const t = this.t;
    const [lat, lon] = modeloParaGeo(t, t.ponto[0] - d[0], t.ponto[1] - d[1]);
    t.lat = lat; t.lon = lon;
    this.posicionar();
    this._gravarLogo();
    if (this.ui.painelAtual() === 'terreno') {
      const dd = this.ui.corpo().querySelector('#terreno-coord');
      if (dd) dd.textContent = `${nf(t.lat, 6)}, ${nf(t.lon, 6)}`;
    }
  }
}
