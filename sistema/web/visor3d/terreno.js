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

/** O ponto do modelo (mm do projeto) em [lat, lon] pela amarração `t` ({lat, lon, ponto, norte}). */
export function modeloParaGeo(t, x, y) {
  const a = rad(t.norte || 0), dx = (x - t.ponto[0]) / 1000, dy = (y - t.ponto[1]) / 1000;
  const leste = dx * Math.cos(a) + dy * Math.sin(a), norte = -dx * Math.sin(a) + dy * Math.cos(a);
  return [t.lat + grau(norte / R), t.lon + grau(leste / (R * Math.cos(rad(t.lat))))];
}

export function geoParaModelo(t, lat, lon) {
  const a = rad(t.norte || 0);
  const norte = rad(lat - t.lat) * R, leste = rad(lon - t.lon) * R * Math.cos(rad(t.lat));
  return [t.ponto[0] + (leste * Math.cos(a) - norte * Math.sin(a)) * 1000, t.ponto[1] + (leste * Math.sin(a) + norte * Math.cos(a)) * 1000];
}

const deMercator = (mx, my) => [grau(2 * Math.atan(Math.exp(my / R)) - Math.PI / 2), grau(mx / R)];

/** O plano da imagem no modelo: o meio (mm do projeto), o lado no chão (mm) e o giro em Z (o norte da imagem para cima). */
export function planoDaImagem(t, im) {
  const [lat, lon] = deMercator((im.x0 + im.x1) / 2, (im.y0 + im.y1) / 2);
  const k = Math.cos(rad(lat));                           // o Mercator estica o chão por 1/cos(lat)
  return { meio: geoParaModelo(t, lat, lon), largura: (im.x1 - im.x0) * k * 1000, altura: (im.y1 - im.y0) * k * 1000,
           giro: rad(t.norte || 0) };
}

/** A imagem com as bordas esmaecendo no fundo (sem o recorte quadrado no meio do chão). */
function comBordaSuave(img) {
  const c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0);
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
    try { this.ligado = localStorage.getItem('ver3d.terreno') !== '0'; } catch (e) { /* sem armazenamento */ }
  }

  /** false: o servidor não tem o terreno (o programa instalado, por enquanto só no dev). */
  async carregar() {
    const r = await fetch(this.api, { cache: 'no-store' });
    if (!r.ok) return false;
    this.estado = await r.json();
    await this.montar();
    return true;
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
    img.src = `${this.api}/imagem.jpg?v=${im.versao || 0}`;
    try { await img.decode(); } catch (e) { this.ui.situacao('A imagem do terreno não abriu: baixe de novo no painel Terreno.'); return; }
    const tex = new THREE.CanvasTexture(comBordaSuave(img));
    // a saída do visor é linear (sem a volta para sRGB): a foto vai como está, senão sai escura
    tex.colorSpace = THREE.NoColorSpace;
    tex.anisotropy = this.visor.renderer.capabilities.getMaxAnisotropy();
    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false });
    this.malha = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
    this.malha.name = 'terreno';
    this.malha.renderOrder = -0.5;                        // depois do piso liso, antes das peças
    this.malha.raycast = () => {};                        // não se escolhe nem mede no chão de foto
    this.grupo = new THREE.Group();
    this.grupo.add(this.malha);
    this.visor.cena.add(this.grupo);
    this.posicionar();
    this.mostrar(this.ligado);
  }

  _tirar() {
    if (!this.grupo) return;
    this.visor.cena.remove(this.grupo);
    this.malha.geometry.dispose(); this.malha.material.map.dispose(); this.malha.material.dispose();
    this.grupo = this.malha = null;
    this.visor.pedirQuadro();
  }

  /** Põe o plano pela amarração (e pelo arrasto em curso). */
  posicionar() {
    if (!this.malha) return;
    const p = planoDaImagem(this.t, this.imagem);
    const o = (this.visor.cabecalho && this.visor.cabecalho.origem) || [0, 0, 0];
    const d = this.arrasto ? this.arrasto.d : [0, 0];
    this.grupo.position.set(-o[0], -o[1], -o[2]);
    this.zChao = this.visor._caixaModelo.min.z + o[2] - 6;          // logo acima do piso liso (min.z − 10)
    this.malha.position.set(p.meio[0] + d[0], p.meio[1] + d[1], this.zChao);
    this.malha.scale.set(p.largura, p.altura, 1);
    this.malha.rotation.set(0, 0, p.giro);
    this.malha.updateMatrixWorld();
    this.visor.pedirQuadro();
  }

  mostrar(sim) {
    this.ligado = !!sim;
    try { localStorage.setItem('ver3d.terreno', sim ? '1' : '0'); } catch (e) { /* sem armazenamento */ }
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
        placeholder="Endereço ou coordenada (cole do Google Maps)"><button type="submit">Buscar</button></form>
      <div id="terreno-resultados"></div>`;
    if (t) {
      html += `<dl class="terreno-dl"><dt>Lugar</dt><dd>${esc(t.endereco || 'coordenada')}</dd>
        <dt>Coordenada</dt><dd id="terreno-coord">${nf(t.lat, 6)}, ${nf(t.lon, 6)}</dd>
        <dt>Norte</dt><dd id="terreno-norte-dd">${nf(t.norte, 1)}° do eixo Y</dd>
        ${im ? `<dt>Imagem</dt><dd>${esc(im.fonte)} · ${nf(im.lado_m)} m de lado · ${esc(im.baixada_em)}</dd>` : ''}</dl>`;
      if (im) html += `<label class="linha-lista"><input type="checkbox" id="terreno-ligado" ${this.ligado ? 'checked' : ''}><span>Mostrar a imagem no chão</span></label>
        <p class="titulo-secao">Ajustar a posição</p>
        <button type="button" id="terreno-ajustar" class="${this.ajustando ? 'ligado' : ''}">${this.ajustando ? '✓ Terminar o ajuste' : '✥ Ajustar (arrastar a imagem)'}</button>
        <div class="sol-controles"><label>Norte <output id="terreno-norte-saida">${nf(t.norte, 1)}°</output>
          <input type="range" id="terreno-norte" min="-180" max="180" step="0.5" value="${t.norte}" aria-label="Giro do norte"></label></div>
        <p class="dica">No Ajustar, arraste a imagem por baixo da obra (de cima, na vista Topo, fica mais fácil) e gire o norte até
          as divisas e as ruas encaixarem. Grava sozinho.</p>`;
      html += `<p class="titulo-secao">Imagem</p>
        <label class="terreno-fonte-sel">Fonte <select id="terreno-fonte-sel">${fontes.map(f => `<option value="${esc(f.chave)}" ${f.chave === fonteAtual ? 'selected' : ''}>${esc(f.nome)}</option>`).join('')}
          <option value="wms" ${fonteAtual === 'wms' ? 'selected' : ''}>Geoportal (WMS)…</option></select></label>
        <div id="terreno-wms" ${fonteAtual === 'wms' ? '' : 'hidden'}>
          <input id="terreno-wms-url" placeholder="Endereço do WMS (https://…/wms)" value="${esc(wms.url)}">
          <input id="terreno-wms-camada" placeholder="Camada (ex.: ortofoto)" value="${esc(wms.camada)}"></div>
        <button type="button" id="terreno-baixar" class="forte">${im ? 'Baixar a imagem de novo' : 'Baixar a imagem do terreno'}</button>
        <button type="button" id="terreno-esquecer">Tirar o local</button>`;
    } else {
      html += `<p class="dica">Ache o terreno pelo endereço, ou cole a coordenada do Google Maps (botão direito no lote → a
        primeira linha). A obra entra com o meio no ponto achado; depois o Ajustar acerta a posição e o giro.</p>`;
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
    const nor = $('#terreno-norte');
    if (nor) nor.oninput = () => {
      this.t.norte = +nor.value;
      $('#terreno-norte-saida').textContent = nf(this.t.norte, 1) + '°';
      $('#terreno-norte-dd').textContent = nf(this.t.norte, 1) + '° do eixo Y';
      this.posicionar();
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
