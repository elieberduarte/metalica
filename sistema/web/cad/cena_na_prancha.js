// A cena da obra na prancha (usuário, 11/11: "pode fazer" — a etapa 4 da tela das Cenas, FERRAMENTA · CENAS; amostra-2
// aprovada: a imagem renderizada de uma cena como um objeto do CAD 2D, mover, redimensionar sem distorcer, título e "sem
// escala" embaixo, sai no PDF e na impressão como as outras vistas). A entidade é `imagem` (nucleo/desenho2d.js; no
// servidor nucleo2d/desenho.Imagem): VIVA = o render atual da cena (renderizar de novo na tela das Cenas atualiza a
// prancha); FIXA = a cópia congelada daquele render (…/cenas/<id>/fixar). Desenhos › Pranchas › Inserir cena da obra….

import { criar } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoAlterar } from './nucleo/comandos.js';

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

async function chamar(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
  return j;
}

const quando = (s) => s ? `${s.slice(8, 10)}/${s.slice(5, 7)} ${s.slice(11, 16)}` : '';

/** O tamanho (px) da imagem no endereço. */
function tamanhoDaImagem(url) {
  return new Promise((ok, falha) => {
    const im = new Image();
    im.onload = () => ok([im.naturalWidth, im.naturalHeight]);
    im.onerror = () => falha(new Error('a imagem da cena não abriu'));
    im.src = url;
  });
}

export class MetodosCenaNaPranchaCAD {
  _apiCenas() { return `/api/projetos/${encodeURIComponent(this.projeto)}/terreno/cenas`; }

  /** O endereço da imagem da entidade (a tela do CAD a desenha por ele). */
  _urlDaImagem(e) {
    if (!this.projeto || !e) return null;
    if (e.viva === false) return e.arquivo ? `${this._apiCenas()}/prancha/${encodeURIComponent(e.arquivo)}` : null;
    return e.cena ? `${this._apiCenas()}/${encodeURIComponent(e.cena)}/render.jpg?v=${this._versaoDasImagens || 0}` : null;
  }

  /** Recarrega as imagens (o render da cena foi refeito na tela das Cenas). */
  recarregarImagens() {
    this._versaoDasImagens = (this._versaoDasImagens || 0) + 1;
    if (this.tela._imagensCarregadas) this.tela._imagensCarregadas.clear();
    this.tela._cache = null;
    this.tela.pedirQuadro();
  }

  async inserirCena() {
    if (!this.projeto) { this.aviso('Inserir cena precisa de um projeto aberto.', 'atencao'); return; }
    let cenas = [];
    try { cenas = (await chamar(this._apiCenas())).cenas || []; } catch (e) { this.aviso(`As cenas não vieram: ${e.message}`, 'erro', 0); return; }
    const comRender = cenas.filter(c => c.render_em);
    if (!comRender.length) {
      this.aviso(cenas.length ? 'Nenhuma cena tem render ainda: renderize uma na tela das Cenas (menu Cenas › Cenas da obra…).'
                              : 'A obra não tem cenas: crie uma na tela das Cenas (menu Cenas › Cenas da obra…) e renderize.', 'atencao', 12000);
      return;
    }
    const lista = el('div', { class: 'lista-cenas-prancha', style: 'display:flex;flex-direction:column;gap:6px;max-height:300px;overflow:auto' },
      ...comRender.map((c, i) => el('label', { style: 'display:flex;gap:8px;align-items:center;cursor:pointer' },
        el('input', { type: 'radio', name: 'cena-prancha', value: c.id, checked: i === 0 ? 'checked' : undefined }),
        el('span', { style: `width:96px;height:54px;flex:none;border:1px solid var(--borda,#ccc);border-radius:4px;background:#f3f5f8 center/cover no-repeat url('${this._apiCenas()}/${encodeURIComponent(c.id)}/render.jpg?v=${encodeURIComponent(c.render_em)}')` }),
        el('span', {}, el('b', { texto: c.nome }), el('br'),
          el('small', { texto: `render ${quando(c.render_em)}${c.render_em < (c.alterada || '') ? ' — a cena mudou depois (render velho)' : ''}` })))));
    const viva = el('select', {}, el('option', { value: 'viva', texto: 'Viva — acompanha o render da cena (renderizar de novo atualiza a prancha)' }),
      el('option', { value: 'fixa', texto: 'Fixa — o render de agora, congelado' }));
    const largura = el('input', { type: 'number', min: '20', max: '1100', step: '10', value: '250', title: 'Largura da imagem no papel (mm)' });
    const titulo = el('input', { type: 'checkbox', checked: 'checked' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'A imagem renderizada de uma cena da obra entra no meio da tela; mova-a para dentro da folha (Mover) e mude o tamanho pela largura no papel, no painel — ela não distorce. Sai no PDF e na impressão.' }),
      lista, el('label', {}, 'A imagem', viva), el('label', {}, 'Largura no papel (mm)', largura),
      el('label', {}, titulo, ' Título e "sem escala" embaixo'));
    if (await this.dialogo({ titulo: 'Inserir cena da obra', corpo, ok: 'Inserir' }) !== 'ok') return;
    const id = (corpo.querySelector('input[name=cena-prancha]:checked') || {}).value;
    const c = comRender.find(x => x.id === id);
    if (!c) return;
    try {
      let arquivo = '';
      if (viva.value === 'fixa') arquivo = (await chamar(`${this._apiCenas()}/${encodeURIComponent(c.id)}/fixar`, {})).arquivo;
      const prov = { tipo: 'imagem', cena: c.id, viva: viva.value !== 'fixa', arquivo };
      const [pw, ph] = await tamanhoDaImagem(this._urlDaImagem(prov) + (prov.viva ? '' : '?v=1'));
      const k = this.doc.escala || 1;
      const w = Math.max(20, Math.min(1100, parseFloat(String(largura.value).replace(',', '.')) || 250)) * k, h = w * ph / pw;
      const centro = this.tela.paraMundo([this.tela.largura / 2, this.tela.altura / 2]);
      const p0 = [centro[0] - w / 2, centro[1] - h / 2];
      const novas = [criar({ ...prov, camada: 'VISTA', posicao: p0, largura: w, altura: h, nome: c.nome })];
      if (titulo.checked) {
        if (!this.doc.camadas.has('TEXTO')) this.doc.camadas.set('TEXTO', { nome: 'TEXTO', cor: '#000000', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.25 });
        novas.push(criar({ tipo: 'texto', camada: 'TEXTO', posicao: [p0[0], p0[1] - 8 * k], texto: `PERSPECTIVA — ${String(c.nome).toUpperCase()}`, altura: 5 }),
                   criar({ tipo: 'texto', camada: 'TEXTO', posicao: [p0[0], p0[1] - 14 * k], texto: `sem escala · cena "${c.nome}" do 3D`, altura: 2.5 }));
      }
      this.executar(new ComandoAdicionar(novas, `Cena "${c.nome}" na prancha`));
      this.selecionar(novas.map(e => e.id));
      this.aviso(`Cena "${c.nome}" inserida (${prov.viva ? 'viva' : 'fixa'}). Mova-a para dentro da folha; o tamanho, no painel.`, 'info', 10000);
    } catch (e) { this.aviso(`A cena não entrou: ${e.message}`, 'erro', 0); }
  }

  /** O painel da imagem selecionada: a cena, viva ou fixa, a largura no papel, recarregar, abrir a cena. */
  _propsImagem(g, e) {
    const k = this.doc.escala || 1;
    g.append(el('label', { texto: 'Cena' }), el('div', {}, el('b', { texto: e.nome || e.cena }), ' ',
      el('button', { type: 'button', title: 'A cena na tela das Cenas (numa aba nova)', onclick: () => window.open(`/visor3d/cena.html?projeto=${encodeURIComponent(this.projeto)}&cena=${encodeURIComponent(e.cena)}`, '_blank') }, 'Abrir a cena')));
    const viva = el('select', {}, el('option', { value: 'viva', texto: 'Viva (o render atual)', selected: e.viva !== false ? 'selected' : undefined }),
      el('option', { value: 'fixa', texto: 'Fixa (congelada)', selected: e.viva === false ? 'selected' : undefined }));
    viva.addEventListener('change', async () => {
      try {
        if (viva.value === 'fixa') {
          const r = await chamar(`${this._apiCenas()}/${encodeURIComponent(e.cena)}/fixar`, {});
          this.executar(new ComandoAlterar({ [e.id]: { viva: false, arquivo: r.arquivo } }, 'Imagem da cena: fixa'));
        } else this.executar(new ComandoAlterar({ [e.id]: { viva: true } }, 'Imagem da cena: viva'));
      } catch (err) { this.aviso(`Não deu: ${err.message}`, 'erro', 0); viva.value = e.viva === false ? 'fixa' : 'viva'; }
    });
    g.append(el('label', { texto: 'A imagem' }), viva);
    const largura = el('input', { type: 'number', step: '10', value: Math.round(e.largura / k) });
    largura.addEventListener('change', () => {
      const v = parseFloat(String(largura.value).replace(',', '.'));
      if (!isFinite(v) || v <= 0) return;
      const w = v * k;
      this.executar(new ComandoAlterar({ [e.id]: { largura: w, altura: w * e.altura / e.largura } }, 'Largura da imagem'));
    });
    g.append(el('label', { texto: 'Largura no papel (mm)' }), largura);
    g.append(el('label', { texto: '' }), el('button', { type: 'button', title: 'Depois de renderizar a cena de novo', onclick: () => this.recarregarImagens() }, 'Recarregar a imagem'));
  }
}
