// A obra no terreno do cliente (20/10, o usuário: "vincular a obra a um mapa para ter o modelo apresentado dentro do
// terreno do cliente"): a imagem de satélite (ou a ortofoto do geoportal) no chão do modo ver, na escala e no giro da
// amarração gravada no projeto (saida/local_obra.py — as contas daqui são as mesmas de lá). O painel Terreno acha o
// lugar pelo endereço ou pela coordenada colada do Google Maps, baixa a imagem (fica no projeto: abre sem internet) e
// tem o Ajustar: arrastar a imagem por baixo da obra e girar o norte até as divisas e as ruas encaixarem.

import * as THREE from 'three';

const R = 6378137;
const rad = g => g * Math.PI / 180, grau = r => r * 180 / Math.PI;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const cotaTxt = mm => (mm > 0 ? '+' : mm < 0 ? '−' : '') + nf(Math.abs(mm) / 1000, 2);    // +4,00 / 0,00 / −3,50 (m)

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
    this.malha.onBeforeRender = () => { if (this._marcarObra()) this.visor.pedirQuadro(); };   // peças novas (outra situação)
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
    this.grupo = this.malha = this.vazada = null;
    this.visor.pedirQuadro();
  }

  /** Põe o plano pela amarração (e pelo arrasto em curso). */
  posicionar() {
    if (!this.malha) return;
    const p = planoDaImagem(this.t, this.imagem);
    const o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0];
    const d = this.arrasto ? this.arrasto.d : [0, 0];
    this.grupo.position.set(-o[0], -o[1], -o[2]);
    // na cota escolhida (o nível 0,00 da obra com subsolo: o subsolo fica embaixo do chão, a fundação não voa) ou no pé
    // da obra, logo acima do piso liso (min.z − 10)
    const cota = this.t && Number.isFinite(this.t.cota) ? this.t.cota : null;
    this.zChao = cota !== null ? cota - 3 : this.visor._caixaModelo.min.z + o[2] - 6;
    this.malha.position.set(p.meio[0] + d[0], p.meio[1] + d[1], this.zChao);
    this.malha.scale.set(p.largura, p.altura, 1);
    this.malha.rotation.set(0, 0, p.giro);
    this.malha.updateMatrixWorld();
    this.visor.pedirQuadro();
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
          <p class="dica">Obra com subsolo: a imagem no nível do terreno (o 0,00) deixa o subsolo embaixo do chão e a fundação
            no lugar.</p>
          <div class="sol-controles"><label>Transparência <output id="terreno-transp-saida">${Math.round((t.transparencia || 0) * 100)} %</output>
            <input type="range" id="terreno-transp" min="0" max="90" step="5" value="${Math.round((t.transparencia || 0) * 100)}"
              aria-label="Transparência da imagem"></label></div>`;
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
        <button type="button" id="terreno-esquecer">Tirar o local</button>`;
    } else {
      html += `<p class="dica">Ache o terreno pelo endereço, ou cole a coordenada: do Google Maps (botão direito no lote → a
        primeira linha) ou do geoportal da prefeitura (a latitude e a longitude do lote, em graus/minutos/segundos, ou a UTM
        SIRGAS 2000). A obra entra com o meio no ponto achado; depois o Ajustar acerta a posição e o giro.</p>`;
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
    const sq = $('#terreno-esquecer');
    if (sq) sq.onclick = async () => {
      if (!confirm('Tirar o local da obra deste projeto? A imagem baixada fica na pasta, mas some do 3D.')) return;
      this.ajustar(false);
      this.estado = await this._pedir('/esquecer', {});
      await this.montar(); this.ui.aoMudar(); this.painel();
    };
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
                endereco: r.nome, fonte: (this.t && this.t.fonte) || 'esri', caixa: cx };
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
    this.ui.palco.classList.toggle('ajustando-terreno', this.ajustando);
    if (this.ajustando && !this._ouvindo) {
      this._ouvindo = true;
      const palco = this.ui.palco;
      // na captura, no palco: o arrasto não chega à tela (nem à órbita nem à escolha de peça); a roda continua no zoom
      palco.addEventListener('pointerdown', ev => this._inicio(ev), true);
      window.addEventListener('pointermove', ev => this._move(ev));
      window.addEventListener('pointerup', ev => this._fim(ev));
    }
    if (this.ajustando && !this.ligado) this.mostrar(true);
  }

  _noChao(ev) {
    const tela = this.visor.renderer.domElement, r = tela.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.visor.camera);
    const o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0];
    const plano = new THREE.Plane(new THREE.Vector3(0, 0, 1), -(this.zChao - o[2]));
    const p = ray.ray.intersectPlane(plano, new THREE.Vector3());
    return p ? [p.x + o[0], p.y + o[1]] : null;
  }

  _inicio(ev) {
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
  _fim() {
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
