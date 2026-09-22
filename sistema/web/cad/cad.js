// CAD 2D: ponto de entrada. Monta tela, ferramentas, painéis, snap e a conversa com o
// projeto (desenhos em <projeto>/desenhos-2d/, gravados sozinhos a cada mudança).
//
// Mouse: botão esquerdo é da ferramenta; do meio ou direito arrasta a vista; roda dá
// zoom no cursor. Shift trava orto. Esc cancela; Enter e espaço confirmam/repetem.

import { Desenho2D, clonar, valorCota, pontosDe } from './nucleo/desenho2d.js';
import { Pilha, ComandoRemover, ComandoAlterar, ComandoAparencia } from './nucleo/comandos.js';
import { Tela, formatarMm } from './nucleo/tela.js';
import { Snap } from './nucleo/snap.js';
import { FERRAMENTAS, GRUPOS, Ferramenta } from './ferramentas.js';

const CHAVE_TEMA = 'galpao.tema';
const ATRASO_AUTOSAVE = 3000;
const ARRASTO_MIN = 4;
const $ = (s, r = document) => r.querySelector(s);

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

async function pedir(rota, opcoes = {}) {
  let r;
  try { r = await fetch(rota, opcoes); } catch (e) { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}
const postar = (rota, corpo) => pedir(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo || {}) });
const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

class CAD {
  constructor() {
    this.parametros = new URLSearchParams(location.search);
    this.projeto = this.parametros.get('projeto') || null;
    this.nomeDesenho = this.parametros.get('desenho') || null;
    this.doc = new Desenho2D();
    this.pilha = new Pilha(this.doc);
    this.tela = new Tela($('#canvas2d'), this.doc);
    this.snap = new Snap(this.tela);
    this.camadaAtiva = 'VISTA';
    this.alturaTexto = 2.5;
    this.ferramentas = new Map();
    this.ferramenta = null;
    this._autosavePendente = false;
    this._autosaveTimer = null;
    this._salvando = false;
    this._paineisPendentes = new Set();
    this.el = {
      palco: $('#palco'), canvas: $('#canvas2d'), dica: $('#dica'), medida: $('#medida'), avisos: $('#avisos'),
      barra: $('#barra-ferramentas'), props: $('#painel-propriedades'), camadas: $('#painel-camadas'),
      snap: $('#painel-snap'), vistas: $('#painel-vistas'), nome: $('#nome-desenho'), escala: $('#escala'),
      contagem: $('#carimbo-contagem'), coord: $('#carimbo-coord'), estadoSalvo: $('#estado-salvo'),
    };
  }

  // ------------------------------------------------------------- início
  async iniciar() {
    this._aplicarTema(this.parametros.get('tema') || lerTema());
    this.tela.escuro = document.documentElement.getAttribute('data-tema') === 'escuro' ||
      (!document.documentElement.getAttribute('data-tema') && matchMedia('(prefers-color-scheme: dark)').matches);
    this._montarFerramentas();
    this._ligarMouse();
    this._ligarTeclado();
    this._ligarMenus();
    this._ligarPaineis();
    this.doc.aoMudar((ev) => this._aposMudanca(ev));
    this.pilha.aoMudar(() => this._atualizarMenuEditar());
    new ResizeObserver(() => this.tela.redimensionar()).observe(this.el.palco);
    this.tela.redimensionar();
    this.ativarFerramenta('selecionar');

    if (this.projeto) {
      $('#link-editor').href = '/editor?projeto=' + encodeURIComponent(this.projeto);
      try {
        const p = (await pedir('/api/projetos/' + encodeURIComponent(this.projeto))).projeto;
        this.tituloProjeto = p.nome || this.projeto;
      } catch (e) { this.aviso(`Projeto "${this.projeto}" não encontrado: ${e.message}`, 'erro', 0); this.projeto = null; }
    } else {
      $('#link-editor').hidden = true;
      this.aviso('Sem projeto: o desenho fica só nesta janela. Abra pelo gerenciador para gravar no projeto.', 'atencao', 0);
    }
    if (this.projeto && this.nomeDesenho) await this.abrirDesenho(this.nomeDesenho);
    else if (this.projeto) {
      const lista = await this._listaDesenhos();
      if (lista.length) await this.abrirDesenho(lista[0].nome);
      else this.dica('Desenho novo. Use "Vistas do modelo" para trazer uma vista do 3D, ou desenhe à mão.');
    }
    this._agendarPaineis('props', 'camadas', 'snap', 'vistas');
    this._atualizarCarimbo();
    document.body.dataset.pronto = '1';
    window.cad = this;
  }

  // ---------------------------------------------------------- documento
  carregar(json, { enquadrar = true } = {}) {
    const novo = Desenho2D.deJSON(json);
    this.selecionar([]);
    this.doc.substituirPor(novo);
    this.pilha.limpar();
    this.el.nome.value = this.doc.nome || 'Desenho';
    this._refletirEscala();
    if (enquadrar) this.tela.enquadrar();
    this._autosavePendente = false;
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    this._agendarPaineis('props', 'camadas', 'vistas');
    document.title = `${this.doc.nome} — Desenho 2D`;
  }

  async abrirDesenho(nome) {
    try {
      const r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(nome)}`);
      this.nomeDesenho = nome;
      this.carregar(r.desenho);
      const url = new URL(location.href); url.searchParams.set('desenho', nome); history.replaceState(null, '', url);
      this.dica(`Desenho "${this.doc.nome}" aberto: ${numero(this.doc.tamanho)} objetos, escala 1:${this.doc.escala}.`);
    } catch (e) { this.aviso(`Não foi possível abrir "${nome}": ${e.message}`, 'erro', 0); }
  }

  async _listaDesenhos() {
    try { return await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`); } catch { return []; }
  }

  async salvar({ avisar = true } = {}) {
    if (!this.projeto) { if (avisar) this.aviso('Sem projeto aberto: nada para gravar.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || this.doc.nome || 'desenho');
    this.doc.nome = this.el.nome.value.trim() || this.doc.nome;
    if (this._salvando) { this._autosavePendente = true; return; }
    this._salvando = true;
    this.el.estadoSalvo.textContent = 'gravando…';
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}`, { desenho: this.doc.paraJSON() });
      this.el.estadoSalvo.textContent = 'gravado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      if (avisar) this.aviso(`Desenho salvo no projeto (${numero(r.entidades)} objetos).`, 'info');
    } catch (e) {
      this.el.estadoSalvo.textContent = 'não foi possível gravar';
      if (avisar) this.aviso(`Não foi possível salvar: ${e.message}`, 'erro', 0);
    } finally {
      this._salvando = false;
      if (this._autosavePendente) { this._autosavePendente = false; this._agendarAutosave(); }
    }
  }

  _agendarAutosave() {
    if (!this.projeto) return;
    if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
    // desenho enorme (modelo inteiro): serializar 100 MB trava a tela por um instante,
    // então espera mais, para uma sequência de edições gravar uma vez só
    const atraso = this.doc.tamanho > 100000 ? ATRASO_AUTOSAVE * 5 : ATRASO_AUTOSAVE;
    this._autosaveTimer = setTimeout(() => { this._autosaveTimer = null; this.salvar({ avisar: false }); }, atraso);
  }

  async exportarDXF() {
    if (!this.doc.tamanho) { this.dica('O desenho está vazio.'); return; }
    if (!this.projeto) { this.aviso('Exportar DXF precisa de um projeto aberto.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || 'desenho');
    this.dica('Gerando o DXF…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/dxf`, { desenho: this.doc.paraJSON(), escala: this.doc.escala });
      const a = r.arquivo || {};
      this.aviso(el('span', {}, `DXF gerado (${numero(r.entidades)} objetos, 1:${this.doc.escala}): `,
        el('a', { href: a.url, download: a.nome || true, texto: a.nome || 'baixar' }), a.tamanho_kb ? ` · ${numero(a.tamanho_kb, 1)} kB` : ''), 'info', 0);
      this.dica('DXF exportado.');
    } catch (e) { this.aviso(`Não foi possível exportar: ${e.message}`, 'erro', 0); }
  }

  async inserirVista(definicao, titulo) {
    if (!this.projeto) { this.aviso('Inserir vista precisa de um projeto com modelo 3D.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || titulo || 'desenho');
    this.dica(`Gerando a vista "${titulo}" do modelo… (um modelo grande leva alguns segundos)`);
    try {
      // grava o estado atual primeiro, para a vista entrar em cima do que já existe
      if (this.doc.tamanho) await this.salvar({ avisar: false });
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/vista2d`, { vista: definicao, desenho: this.nomeDesenho, titulo: this.el.nome.value || titulo });
      await this.abrirDesenho(this.nomeDesenho);
      const v = r.vista || {};
      this.aviso(`Vista "${titulo}" inserida: ${v.pecas_cortadas || 0} peça(s) cortada(s), ${v.pecas_projetadas || 0} projetada(s), ${numero(v.largura)} × ${numero(v.altura)} mm.` +
                 (v.avisos && v.avisos.length ? ` ${v.avisos.length} aviso(s).` : ''), 'info', 9000);
    } catch (e) { this.aviso(`Não foi possível gerar a vista: ${e.message}`, 'erro', 0); this.dica('Vista não gerada.'); }
  }

  _aposMudanca({ acao }) {
    this.tela.pedirQuadro();
    this._podarSelecao();
    this._agendarPaineis('props', acao === 'aparencia' || acao === 'tudo' ? 'camadas' : null, acao === 'tudo' ? 'vistas' : null);
    this._atualizarCarimbo();
    this._agendarAutosave();
  }

  executar(cmd) { this.pilha.executar(cmd); }
  desfazer() { const c = this.pilha.desfazer(); if (c) this.dica(`Desfeito: ${c.rotulo}`); }
  refazer() { const c = this.pilha.refazer(); if (c) this.dica(`Refeito: ${c.rotulo}`); }

  // ------------------------------------------------------------ seleção
  selecionar(ids) {
    this.tela.selecao = new Set(ids.filter(id => this.doc.get(id)));
    this.tela.pedirQuadro();
    this._agendarPaineis('props');
    this._atualizarCarimbo();
  }
  alternarSelecao(id) { const s = new Set(this.tela.selecao); s.has(id) ? s.delete(id) : s.add(id); this.selecionar([...s]); }
  _podarSelecao() { const antes = this.tela.selecao.size; this.tela.selecao = new Set([...this.tela.selecao].filter(id => this.doc.get(id))); if (this.tela.selecao.size !== antes) this._agendarPaineis('props'); }
  apagarSelecao() { if (this.tela.selecao.size) this.executar(new ComandoRemover([...this.tela.selecao])); }
  selecionarMesmaPeca() {
    const origens = new Set([...this.tela.selecao].map(id => (this.doc.get(id).atributos || {}).origem).filter(Boolean));
    if (!origens.size) { this.dica('Selecione um objeto que veio do modelo 3D.'); return; }
    this.selecionar([...this.doc.entidades.values()].filter(e => origens.has((e.atributos || {}).origem)).map(e => e.id));
  }

  // ------------------------------------------------------- ferramentas
  _montarFerramentas() {
    const barra = this.el.barra;
    for (const [grupo, rotulo] of GRUPOS) {
      barra.append(el('div', { class: 'grupo-rotulo', texto: rotulo }));
      for (const F of FERRAMENTAS.filter(f => f.grupo === grupo)) {
        this.ferramentas.set(F.id, new F(this));
        const b = el('button', { type: 'button', class: 'ferramenta', 'data-ferramenta': F.id, 'aria-pressed': 'false',
          title: `${F.nome}${F.atalho ? ` (${F.atalho === ' ' ? 'espaço' : F.atalho.toUpperCase()})` : ''}`, html: F.icone || '' });
        b.addEventListener('click', () => this.ativarFerramenta(F.id));
        barra.append(b);
      }
    }
  }

  ativarFerramenta(id) {
    const f = this.ferramentas.get(id);
    if (!f) return;
    if (this.ferramenta) this.ferramenta.desativar();
    this.ferramenta = f;
    this.previa([]);
    for (const b of this.el.barra.querySelectorAll('.ferramenta')) b.setAttribute('aria-pressed', String(b.dataset.ferramenta === id));
    f.ativar();
  }

  previa(entidades) { this.tela.previa = entidades || []; this.tela.pedirQuadro(); }
  dica(t) { this.el.dica.textContent = t || ''; }
  medida(t) { if (document.activeElement !== this.el.medida) this.el.medida.placeholder = t || 'digite e Enter'; }

  // ------------------------------------------------------------- mouse
  _ligarMouse() {
    const c = this.el.canvas;
    let arrastoVista = null, pressao = null;
    const px = (ev) => { const r = c.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    c.addEventListener('contextmenu', (ev) => ev.preventDefault());
    c.addEventListener('pointerdown', (ev) => {
      c.setPointerCapture(ev.pointerId);
      if (ev.button === 1 || ev.button === 2) { arrastoVista = px(ev); this.el.palco.dataset.arrastando = '1'; return; }
      if (ev.button === 0) pressao = { px: px(ev), movido: false };
    });
    c.addEventListener('pointermove', (ev) => {
      const p = px(ev);
      if (arrastoVista) { this.tela.arrastar([p[0] - arrastoVista[0], p[1] - arrastoVista[1]]); arrastoVista = p; return; }
      const s = this.snap.resolver(p, { orto: ev.shiftKey });
      this.tela.cursor = s.ponto; this.tela.snap = s.tipo ? s : null;
      this.el.coord.textContent = `x ${formatarMm(s.ponto[0])}  y ${formatarMm(s.ponto[1])}`;
      if (pressao && !pressao.movido && Math.hypot(p[0] - pressao.px[0], p[1] - pressao.px[1]) > ARRASTO_MIN) pressao.movido = true;
      if (pressao && pressao.movido && this.ferramenta && this.ferramenta.onSoltar !== Ferramenta.prototype.onSoltar) {
        this.tela.retangulo = [pressao.px, p];
      }
      if (!pressao || !pressao.movido) {
        this.tela.realce = this.ferramenta && this.ferramenta.constructor.id === 'selecionar' ? (this.tela.sob(p) || {}).id || null : null;
        if (this.ferramenta) this.ferramenta.onMover(s.ponto, { ...evInfo(ev), px: p });
      }
      this.tela.pedirQuadro();
    });
    c.addEventListener('pointerup', (ev) => {
      const p = px(ev);
      if (arrastoVista) { arrastoVista = null; delete this.el.palco.dataset.arrastando; return; }
      if (!pressao) return;
      const s = this.snap.resolver(p, { orto: ev.shiftKey });
      if (pressao.movido && this.tela.retangulo) {
        this.tela.retangulo = null;
        if (this.ferramenta) this.ferramenta.onSoltar(s.ponto, { ...evInfo(ev), px: p, arrasto: { de: pressao.px, para: p } });
      } else if (this.ferramenta) {
        this.ferramenta.onPonto(s.ponto, { ...evInfo(ev), px: p });
      }
      pressao = null;
      this.tela.pedirQuadro();
    });
    c.addEventListener('wheel', (ev) => { ev.preventDefault(); this.tela.zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, px(ev)); }, { passive: false });
    c.addEventListener('dblclick', (ev) => { if (ev.button === 1) this.tela.enquadrar(); });
    c.addEventListener('pointerleave', () => { this.tela.cursor = null; this.tela.snap = null; this.tela.pedirQuadro(); });
  }

  // ----------------------------------------------------------- teclado
  _ligarTeclado() {
    document.addEventListener('keydown', (ev) => {
      const alvo = ev.target;
      const emCampo = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'SELECT' || alvo.tagName === 'TEXTAREA');
      if (emCampo && alvo !== this.el.medida) return;
      if (alvo === this.el.medida) {
        if (ev.key === 'Enter') { ev.preventDefault(); const v = this.el.medida.value.trim(); this.el.medida.value = ''; if (v && this.ferramenta) this.ferramenta.onValor(v); this.el.canvas.focus(); }
        if (ev.key === 'Escape') { this.el.medida.value = ''; this.el.canvas.focus(); }
        return;
      }
      if (ev.key === 'Shift') { this.snap.orto = true; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); ev.shiftKey ? this.refazer() : this.desfazer(); return; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y') { ev.preventDefault(); this.refazer(); return; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') { ev.preventDefault(); this.salvar(); return; }
      if (ev.key === 'Escape') { if (this.ferramenta) { this.ferramenta.cancelar(); } this.selecionar([]); if (this.ferramenta.constructor.id !== 'selecionar') this.ativarFerramenta('selecionar'); return; }
      if (ev.key === 'F8') { ev.preventDefault(); this.snap.orto = !this.snap.orto; this.dica(`Orto ${this.snap.orto ? 'ligado' : 'desligado'}`); return; }
      if (this.ferramenta && this.ferramenta.onTecla(ev)) { ev.preventDefault(); return; }
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
      if (ev.key.toLowerCase() === 'z') { this.tela.enquadrar(); return; }
      // número ou sinal digitado no canvas vai para a caixa de medidas
      if (/^[-0-9.,@<]$/.test(ev.key)) { this.el.medida.focus(); return; }
      for (const F of FERRAMENTAS) if (F.atalho && ev.key === F.atalho) { ev.preventDefault(); this.ativarFerramenta(F.id); return; }
    });
    document.addEventListener('keyup', (ev) => { if (ev.key === 'Shift') this.snap.orto = false; });
  }

  // ------------------------------------------------------------- menus
  _ligarMenus() {
    const acoes = {
      abrir: () => this.dialogoAbrir(),
      novo: () => this.dialogoNovo(),
      salvar: () => this.salvar(),
      'exportar-dxf': () => this.exportarDXF(),
      'abrir-pasta': () => this.projeto && postar(`/api/projetos/${encodeURIComponent(this.projeto)}/abrir-pasta`, { sub: 'desenhos-2d' }).catch(e => this.aviso(e.message, 'erro')),
      corte: () => this.dialogoCorte(),
      detalhar: () => this.dialogoDetalhar(),
      desfazer: () => this.desfazer(), refazer: () => this.refazer(),
      'selecionar-tudo': () => this.selecionar([...this.doc.entidades.keys()].filter(id => this.doc.visivel(this.doc.get(id)))),
      apagar: () => this.apagarSelecao(),
      'selecionar-peca': () => this.selecionarMesmaPeca(),
      'zoom-extensao': () => this.tela.enquadrar(),
      'zoom-selecao': () => { const c = this.doc.caixa(this.tela.selecao); if (c) this.tela.enquadrar(c, 0.2); },
      grade: () => { this.tela.grade = !this.tela.grade; this.tela.pedirQuadro(); },
      orto: () => { this.snap.orto = !this.snap.orto; this.dica(`Orto ${this.snap.orto ? 'ligado' : 'desligado'}`); },
    };
    document.addEventListener('click', (ev) => {
      const botaoMenu = ev.target.closest('.menu-botao');
      if (botaoMenu) { const m = botaoMenu.parentElement; const aberto = m.classList.contains('aberto'); this._fecharMenus(); if (!aberto) m.classList.add('aberto'); return; }
      const item = ev.target.closest('[data-acao], [data-vista]');
      if (item) {
        this._fecharMenus();
        if (item.dataset.vista) this.inserirVista({ padrao: item.dataset.vista }, item.textContent.trim());
        else if (acoes[item.dataset.acao]) acoes[item.dataset.acao]();
        return;
      }
      if (!ev.target.closest('.menu')) this._fecharMenus();
    });
    $('#btn-salvar').addEventListener('click', () => this.salvar());
    $('#btn-dxf').addEventListener('click', () => this.exportarDXF());
    $('#btn-tema').addEventListener('click', () => this._alternarTema());
    this.el.nome.addEventListener('change', () => { this.doc.nome = this.el.nome.value.trim() || 'Desenho'; document.title = `${this.doc.nome} — Desenho 2D`; this._agendarAutosave(); });
    this.el.escala.addEventListener('change', () => { this.doc.escala = parseFloat(this.el.escala.value) || 20; this.doc.notificar([], 'aparencia'); this.dica(`Escala 1:${this.doc.escala}: textos, cotas e hachuras redimensionados.`); });
  }
  _fecharMenus() { for (const m of document.querySelectorAll('.menu.aberto')) m.classList.remove('aberto'); }
  _atualizarMenuEditar() {
    const m = $('#menu-editar');
    m.querySelector('[data-acao="desfazer"]').disabled = !this.pilha.podeDesfazer;
    m.querySelector('[data-acao="refazer"]').disabled = !this.pilha.podeRefazer;
  }
  _refletirEscala() {
    const s = this.el.escala;
    if (![...s.options].some(o => parseFloat(o.value) === this.doc.escala)) s.append(el('option', { value: String(this.doc.escala), texto: String(this.doc.escala) }));
    s.value = String(this.doc.escala);
  }

  // ----------------------------------------------------------- painéis
  _ligarPaineis() {
    for (const cab of document.querySelectorAll('.painel .cabecalho')) cab.addEventListener('click', () => cab.closest('.painel').classList.toggle('fechado'));
  }
  _agendarPaineis(...quais) {
    for (const q of quais) if (q) this._paineisPendentes.add(q);
    if (this._rafPaineis) return;
    this._rafPaineis = requestAnimationFrame(() => {
      this._rafPaineis = null;
      const p = this._paineisPendentes; this._paineisPendentes = new Set();
      if (p.has('props')) this._painelProps();
      if (p.has('camadas')) this._painelCamadas();
      if (p.has('snap')) this._painelSnap();
      if (p.has('vistas')) this._painelVistas();
    });
  }

  _painelProps() {
    const raiz = this.el.props; raiz.replaceChildren();
    const ids = [...this.tela.selecao];
    if (!ids.length) {
      const g = el('div', { class: 'props' });
      g.append(el('label', { texto: 'Camada ativa' }), this._seletorCamada(this.camadaAtiva, (v) => { this.camadaAtiva = v; }));
      const alt = el('input', { type: 'number', step: '0.5', min: '1', value: this.alturaTexto, title: 'Altura de texto e cota, em mm no papel' });
      alt.addEventListener('change', () => { this.alturaTexto = parseFloat(alt.value) || 2.5; });
      g.append(el('label', { texto: 'Texto (mm)' }), alt);
      g.append(el('div', { class: 'origem', texto: `${numero(this.doc.tamanho)} objetos no desenho · nada selecionado` }));
      raiz.append(g); return;
    }
    const ents = ids.map(id => this.doc.get(id));
    const g = el('div', { class: 'props' });
    const tipos = new Set(ents.map(e => e.tipo));
    g.append(el('label', { texto: 'Seleção' }), el('div', { texto: ids.length === 1 ? ents[0].tipo : `${ids.length} objetos (${[...tipos].join(', ')})` }));
    const camadas = new Set(ents.map(e => e.camada));
    g.append(el('label', { texto: 'Camada' }), this._seletorCamada(camadas.size === 1 ? ents[0].camada : '', (v) => {
      const m = {}; for (const id of ids) m[id] = { camada: v }; this.executar(new ComandoAlterar(m, 'Trocar camada'));
    }, camadas.size !== 1));
    if (ids.length === 1) {
      const e = ents[0];
      const campo = (rotulo, chave, tipo = 'text', extra = {}) => {
        const i = el('input', { type: tipo, value: e[chave] ?? '', ...extra });
        i.addEventListener('change', () => { const v = tipo === 'number' ? parseFloat(i.value.replace(',', '.')) : i.value; if (tipo === 'number' && !isFinite(v)) return; this.executar(new ComandoAlterar({ [e.id]: { [chave]: v } }, `Alterar ${rotulo}`)); });
        g.append(el('label', { texto: rotulo }), i);
      };
      if (e.tipo === 'texto' || e.tipo === 'chamada') { campo('Texto', 'texto'); campo('Altura (mm)', 'altura', 'number', { step: '0.5' }); }
      if (e.tipo === 'texto') campo('Ângulo', 'angulo', 'number', { step: '15' });
      if (e.tipo === 'cota') {
        g.append(el('label', { texto: 'Valor' }), el('div', { texto: formatarMm(valorCota(e)) + ' mm' }));
        campo('Texto (vazio = medida)', 'texto'); campo('Deslocamento', 'deslocamento', 'number', { step: '1' });
        const modo = el('select', {}, ...['alinhada', 'h', 'v'].map(m => el('option', { value: m, texto: m, selected: e.modo === m ? 'selected' : undefined })));
        modo.addEventListener('change', () => this.executar(new ComandoAlterar({ [e.id]: { modo: modo.value } }, 'Modo da cota')));
        g.append(el('label', { texto: 'Modo' }), modo);
      }
      if (e.tipo === 'circulo' || e.tipo === 'arco') campo('Raio', 'raio', 'number', { step: '1' });
      if (e.tipo === 'linha') g.append(el('label', { texto: 'Comprimento' }), el('div', { texto: formatarMm(Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])) + ' mm' }));
      if (e.tipo === 'hachura') {
        const pad = el('select', {}, ...['aco', 'concreto', 'solido'].map(m => el('option', { value: m, texto: m, selected: e.padrao === m ? 'selected' : undefined })));
        pad.addEventListener('change', () => this.executar(new ComandoAlterar({ [e.id]: { padrao: pad.value } }, 'Padrão da hachura')));
        g.append(el('label', { texto: 'Padrão' }), pad); campo('Espaçamento', 'espacamento', 'number', { step: '0.5' }); campo('Ângulo', 'angulo', 'number', { step: '15' });
      }
      const a = e.atributos || {};
      if (a.origem) {
        g.append(el('div', { class: 'origem' }, el('b', { texto: 'Do modelo 3D: ' }), [a.posicao && `posição ${a.posicao}`, a.conjunto && `conjunto ${a.conjunto}`, a.perfil, a.nome].filter(Boolean).join(' · ')));
      }
    } else {
      const a = ents.map(e => (e.atributos || {}).posicao).filter(Boolean);
      if (a.length) g.append(el('div', { class: 'origem' }, el('b', { texto: 'Peças: ' }), [...new Set(a)].slice(0, 12).join(', ')));
    }
    const botoes = el('div', { class: 'botoes' },
      el('button', { type: 'button', texto: 'Zoom', onclick: () => { const c = this.doc.caixa(this.tela.selecao); if (c) this.tela.enquadrar(c, 0.25); } }),
      el('button', { type: 'button', texto: 'Mesma peça', onclick: () => this.selecionarMesmaPeca() }),
      el('button', { type: 'button', texto: 'Apagar', onclick: () => this.apagarSelecao() }));
    g.append(botoes);
    raiz.append(g);
  }

  _seletorCamada(atual, aoMudar, varios = false) {
    const s = el('select', {}, varios ? el('option', { value: '', texto: '— várias —' }) : null,
      ...[...this.doc.camadas.keys()].map(n => el('option', { value: n, texto: n, selected: n === atual ? 'selected' : undefined })));
    s.addEventListener('change', () => { if (s.value) aoMudar(s.value); });
    return s;
  }

  _painelCamadas() {
    const raiz = this.el.camadas; raiz.replaceChildren();
    const cont = new Map();
    for (const e of this.doc.entidades.values()) cont.set(e.camada, (cont.get(e.camada) || 0) + 1);
    const lista = el('div', { class: 'lista-linhas' });
    const olho = (v) => v ? '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3" opacity=".45"/><path d="M3 13L13 3" stroke="currentColor" stroke-width="1.3"/></svg>';
    for (const [nome, c] of this.doc.camadas) {
      const linha = el('div', { class: 'linha', title: 'Clique: camada ativa · duplo clique: selecionar o que está nela' });
      if (c.visivel === false) linha.dataset.oculta = '';
      if (nome === this.camadaAtiva) linha.dataset.ativa = '';
      const vis = el('button', { type: 'button', class: 'alternador', html: olho(c.visivel !== false), title: c.visivel === false ? 'Mostrar' : 'Ocultar',
        onclick: () => this.executar(new ComandoAparencia(nome, { visivel: c.visivel === false })) });
      const cor = el('input', { type: 'color', value: c.cor, title: 'Cor da camada' });
      cor.addEventListener('change', () => this.executar(new ComandoAparencia(nome, { cor: cor.value })));
      linha.addEventListener('click', (ev) => { if (ev.target.closest('button, input')) return; this.camadaAtiva = nome; this._agendarPaineis('camadas', 'props'); this.dica(`Camada ativa: ${nome}`); });
      linha.addEventListener('dblclick', (ev) => { if (ev.target.closest('button, input')) return; this.selecionar([...this.doc.entidades.values()].filter(e => e.camada === nome).map(e => e.id)); });
      linha.append(vis, cor, el('span', { class: 'nome', texto: nome }), el('span', { class: 'contagem', texto: numero(cont.get(nome) || 0) }));
      lista.append(linha);
    }
    raiz.append(lista);
    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: '+ Nova camada', onclick: async () => {
      const n = await this.perguntar('Nova camada', 'Nome', ''); if (!n) return;
      const nome = n.trim().toUpperCase(); if (this.doc.camadas.has(nome)) { this.camadaAtiva = nome; return; }
      this.doc.camadas.set(nome, { nome, cor: '#5b7db1', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.25 });
      this.camadaAtiva = nome; this.doc.notificar([], 'aparencia');
    } }));
    acoes.append(el('button', { type: 'button', texto: 'Mostrar todas', onclick: () => { for (const [n, c] of this.doc.camadas) if (c.visivel === false) this.executar(new ComandoAparencia(n, { visivel: true })); } }));
    raiz.append(acoes);
  }

  _painelSnap() {
    const raiz = this.el.snap; raiz.replaceChildren();
    const g = el('div', { class: 'snaps' });
    const rot = { extremidade: 'Extremidade', meio: 'Meio', centro: 'Centro', interseccao: 'Interseção', perpendicular: 'Perpendicular', sobre: 'Sobre a linha', grade: 'Grade' };
    for (const [k, r] of Object.entries(rot)) {
      const c = el('input', { type: 'checkbox', checked: this.snap.ativos[k] ? 'checked' : undefined });
      c.addEventListener('change', () => { this.snap.ativos[k] = c.checked; });
      g.append(el('label', {}, c, r));
    }
    raiz.append(g);
  }

  _painelVistas() {
    const raiz = this.el.vistas; raiz.replaceChildren();
    if (!this.doc.vistas.length) { raiz.append(el('div', { class: 'nada', texto: 'Nenhuma vista do modelo neste desenho. Use o menu "Vistas do modelo".' })); return; }
    for (const v of this.doc.vistas) {
      const item = el('div', { class: 'vista-item', title: 'Clique para enquadrar' },
        el('div', { class: 't', texto: v.nome || v.tipo }),
        el('div', { class: 's', texto: `${v.tipo || 'corte'} · ${v.pecas_cortadas || 0} cortadas, ${v.pecas_projetadas || 0} projetadas · ${numero(v.largura)} × ${numero(v.altura)} mm` + (v.profundidade ? ` · prof. ${numero(v.profundidade)} mm` : '') }));
      item.addEventListener('click', () => { const c = v.canto || [0, 0]; this.tela.enquadrar([[c[0], c[1]], [c[0] + (v.largura || 1), c[1] + (v.altura || 1)]], 0.1); });
      raiz.append(item);
    }
  }

  _atualizarCarimbo() {
    this.el.contagem.textContent = `${numero(this.doc.tamanho)} objetos` + (this.tela.selecao.size ? ` · ${numero(this.tela.selecao.size)} selecionados` : '');
  }

  // ------------------------------------------------------------ diálogos
  dialogo({ titulo, corpo, ok = 'OK' }) {
    return new Promise((resolver) => {
      const d = $('#dialogo');
      $('#dialogo-titulo').textContent = titulo;
      $('#dialogo-corpo').replaceChildren(corpo);
      $('#dialogo-ok').textContent = ok; $('#dialogo-ok').hidden = ok === null;
      const fechar = (v) => { d.querySelector('form').onsubmit = null; $('#dialogo-cancelar').onclick = null; d.oncancel = null; d.close(); resolver(v); };
      d.querySelector('form').onsubmit = (ev) => { ev.preventDefault(); fechar('ok'); };
      $('#dialogo-cancelar').onclick = () => fechar(null);
      d.oncancel = (ev) => { ev.preventDefault(); fechar(null); };
      d.showModal();
      const primeiro = corpo.querySelector && corpo.querySelector('input, select, button');
      if (primeiro) primeiro.focus();
    });
  }

  async perguntar(titulo, rotulo, valor = '') {
    const i = el('input', { type: 'text', value: valor, spellcheck: 'false' });
    const corpo = el('div', {}, el('label', {}, rotulo, i));
    const r = await this.dialogo({ titulo, corpo });
    return r === 'ok' ? i.value : null;
  }

  async dialogoAbrir() {
    if (!this.projeto) return;
    const lista = await this._listaDesenhos();
    const caixa = el('div', { class: 'lista-abrir' });
    if (!lista.length) caixa.append(el('div', { class: 'explica', texto: 'Este projeto ainda não tem desenhos 2D.' }));
    let escolhido = null;
    for (const d of lista) {
      const b = el('button', { type: 'button' }, d.titulo || d.nome, el('small', { texto: `${numero(d.entidades)} objetos · 1:${d.escala} · ${(d.vistas || []).join(', ') || 'sem vistas'} · ${d.alterado.replace('T', ' ')}` }));
      b.addEventListener('click', () => { escolhido = d.nome; $('#dialogo').close(); });
      caixa.append(b);
    }
    await this.dialogo({ titulo: 'Abrir desenho do projeto', corpo: caixa, ok: null });
    if (escolhido) await this.abrirDesenho(escolhido);
  }

  async dialogoNovo() {
    const nome = await this.perguntar('Novo desenho', 'Nome', 'Desenho ' + ((await this._listaDesenhos()).length + 1));
    if (!nome) return;
    this.nomeDesenho = slug(nome);
    this.carregar({ nome, escala: 20 });
    const url = new URL(location.href); url.searchParams.set('desenho', this.nomeDesenho); history.replaceState(null, '', url);
    this._agendarAutosave();
  }

  async dialogoCorte() {
    const campos = {
      eixo: el('select', {}, ...[['y', 'Corte transversal (plano perpendicular a Y, olhando para +Y)'], ['-y', 'Corte transversal olhando para −Y'], ['x', 'Corte longitudinal (perpendicular a X, olhando para +X)'], ['-x', 'Corte longitudinal olhando para −X'], ['z', 'Corte horizontal (planta, olhando para baixo)']].map(([v, t]) => el('option', { value: v, texto: t }))),
      posicao: el('input', { type: 'number', step: 'any', value: '0', placeholder: 'mm' }),
      profundidade: el('input', { type: 'number', step: 'any', value: '1500', placeholder: 'mm' }),
      nome: el('input', { type: 'text', value: 'Corte A' }),
    };
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Posição é a coordenada do plano ao longo do eixo (mm). A profundidade limita o que aparece além do corte. Para posicionar o plano vendo o modelo, use a ferramenta Seção no Modelo 3D.' }),
      el('label', {}, 'Direção', campos.eixo), el('label', {}, 'Posição do plano (mm)', campos.posicao),
      el('label', {}, 'Profundidade de vista (mm)', campos.profundidade), el('label', {}, 'Nome da vista', campos.nome));
    if (await this.dialogo({ titulo: 'Corte por plano', corpo, ok: 'Gerar' }) !== 'ok') return;
    const eixo = campos.eixo.value, pos = parseFloat(campos.posicao.value) || 0;
    const normal = { y: [0, 1, 0], '-y': [0, -1, 0], x: [1, 0, 0], '-x': [-1, 0, 0], z: [0, 0, -1] }[eixo];
    const origem = eixo.endsWith('y') ? [0, pos, 0] : eixo.endsWith('x') ? [pos, 0, 0] : [0, 0, pos];
    const prof = parseFloat(campos.profundidade.value);
    await this.inserirVista({ origem, normal, acima: eixo === 'z' ? [0, 1, 0] : null, profundidade: isFinite(prof) && prof > 0 ? prof : null, cortar: true, nome: campos.nome.value, tipo: 'corte' }, campos.nome.value);
  }

  /** Detalhamento de peças e conjuntos do projeto (mesma rota do editor 3D); abre o primeiro desenho aqui. */
  async dialogoDetalhar() {
    if (!this.projeto) { this.aviso('Detalhar precisa de um projeto aberto.', 'atencao'); return; }
    const grupos = [['chapas', 'Chapas'], ['barras', 'Barras e terças'], ['tirantes', 'Tirantes e barras redondas'], ['telhas', 'Telhas'], ['conjuntos', 'Conjuntos (tesouras, vigas, pilares)']];
    const caixas = {};
    const lista = el('div', { class: 'lista-opcoes' });
    for (const [k, r] of grupos) { caixas[k] = el('input', { type: 'checkbox', checked: 'checked' }); lista.append(el('label', { class: 'linha' }, caixas[k], ' ' + r)); }
    const regra = el('input', { type: 'checkbox', checked: 'checked' });
    const substituir = el('input', { type: 'checkbox', checked: 'checked' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Uma célula por posição (as peças iguais são contadas, não repetidas) e a elevação de cada conjunto, com cotas de fabricação e lista de perfis. Gera um desenho por grupo e o romaneio em detalhamento/romaneio.csv.' }),
      lista,
      el('label', { class: 'linha' }, regra, ' Furação das terças no padrão da fábrica (50 × 60 abaixo de 200 mm; 100 × 60 acima)'),
      el('label', { class: 'linha' }, substituir, ' Substituir os desenhos de detalhamento anteriores'));
    if (await this.dialogo({ titulo: 'Detalhar peças e conjuntos', corpo, ok: 'Detalhar' }) !== 'ok') return;
    const escolhidos = grupos.map(([k]) => k).filter(k => caixas[k].checked);
    if (!escolhidos.length) return;
    this.dica('Detalhando as peças do projeto…');
    try {
      if (this.doc.tamanho && this.nomeDesenho) await this.salvar({ avisar: false });
      const j = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar`, { grupos: escolhidos, regra_tercas: regra.checked, rotular: true, substituir: substituir.checked });
      const tercas = Object.keys(j.regra_tercas || {}).length;
      this.aviso(`Detalhamento: ${j.pecas} peças em ${j.posicoes} posições e ${j.conjuntos} conjuntos, ${j.peso_total} kg; ${j.desenhos.length} desenho(s)` + (tercas ? `, furação de fábrica em ${tercas} posições` : '') + '. Os desenhos estão em Desenho → Abrir desenho do projeto.', 'info', 15000);
      if (j.desenhos.length) await this.abrirDesenho(j.desenhos[0].nome);
    } catch (e) { this.aviso(`Não foi possível detalhar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  // -------------------------------------------------------------- avisos
  aviso(conteudo, tipo = 'info', duracao = 6000) {
    const caixa = el('div', { class: 'aviso', 'data-tipo': tipo, role: tipo === 'erro' ? 'alert' : 'status' });
    caixa.append(typeof conteudo === 'string' ? document.createTextNode(conteudo) : conteudo);
    caixa.append(el('button', { type: 'button', title: 'fechar', texto: '×', onclick: () => caixa.remove() }));
    this.el.avisos.append(caixa);
    if (duracao) setTimeout(() => caixa.remove(), duracao);
  }

  // ---------------------------------------------------------------- tema
  _aplicarTema(t) {
    if (t === 'claro' || t === 'escuro') document.documentElement.setAttribute('data-tema', t);
    this.tela.escuro = (document.documentElement.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro')) === 'escuro';
    this.tela.pedirQuadro();
  }
  _alternarTema() {
    const atual = document.documentElement.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
    const novo = atual === 'escuro' ? 'claro' : 'escuro';
    try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* privado */ }
    this._aplicarTema(novo);
  }
}

const evInfo = (ev) => ({ shiftKey: ev.shiftKey, ctrlKey: ev.ctrlKey, altKey: ev.altKey, button: ev.button });
const slug = (s) => String(s || '').replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().toLowerCase().replace(/[\s_-]+/g, '-').slice(0, 60).replace(/^-+|-+$/g, '') || 'desenho';
function lerTema() { try { return localStorage.getItem(CHAVE_TEMA); } catch { return null; } }

const cad = new CAD();
cad.iniciar();
