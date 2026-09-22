// Ponto de entrada do editor 3D: monta o núcleo, carrega catálogo e ferramentas, e
// liga mouse, teclado, menus e painéis.
//
// Contrato com as ferramentas (ver GUIA_EDITOR3D.md e ferramentas/base.js): o editor
// entrega a elas pontos já resolvidos pela inferência, nunca coordenadas de tela, e
// toda alteração do documento passa por `executar(comando)`.
//
// Semântica do mouse, no espírito do SketchUp:
//   * ferramentas de clique (linha, retângulo, mover...) recebem `onPonto` ao
//     pressionar o botão; se o usuário arrastar e soltar, recebem outro `onPonto` no
//     ponto em que soltou — arrastar desenha, como no SketchUp;
//   * ferramentas que tratam arrasto (as que sobrescrevem `onSoltar`, como a de
//     seleção) recebem `onPonto` num clique parado e `onSoltar` ao fim de um arrasto;
//   * durante o arrasto, `onMover` recebe `ev.arrasto = {de:[x,y], para:[x,y]}`.
// O botão esquerdo é sempre da ferramenta; direito e do meio são da câmera.

import { Documento, criar, clonar, comprimentoDaBarra, direcaoDaBarra, areaDaChapa,
         PAPEIS, somar, escalar } from './nucleo/documento.js';
import { Pilha, Comando, ComandoAdicionar, ComandoRemover, ComandoAlterar }
  from './nucleo/comandos.js';
import { Cena, MODOS, ESCALA } from './nucleo/cena.js';
import { Camera, VISTAS } from './nucleo/camera.js';
import { Selecao } from './nucleo/selecao.js';
import { Inferencia } from './nucleo/inferencia.js';
import { api, ErroServidor } from './nucleo/api.js';
import { carregarFerramentas, GRUPOS } from './ferramentas/indice.js';
import { Ferramenta, formatar } from './ferramentas/base.js';

const CHAVE_TEMA = 'galpao.tema';               // a mesma da interface principal
const CHAVE_GALPAO = 'galpao.estado.v1';        // dados do galpão dimensionado
const CHAVE_ULTIMO = 'galpao.editor.ultimo';    // nome do último modelo salvo no servidor
const ATRASO_AUTOSAVE = 4000;                   // ms de sossego antes de gravar no servidor
const TECLAS_VISTA = ['topo', 'frente', 'tras', 'esquerda', 'direita', 'inferior', 'isometrica'];
const ARRASTO_MIN = 4;                          // pixels até um clique virar arrasto
const ABREVIACOES = { navegacao: 'Nav', desenho: 'Des', edicao: 'Edi', medicao: 'Med', estrutura: 'Estr' };

// Rota da análise de esforços. Mora aqui, e não em nucleo/api.js, porque é o editor que
// decide o que fazer quando ela não responde: o painel simplesmente não aparece.
const ROTA_ANALISE = '/api/modelo/analise';

/** Grandezas do seletor quando o servidor não manda a própria lista. */
const GRANDEZAS_PADRAO = [
  { chave: 'aproveitamento', nome: 'Aproveitamento (S/R)', unidade: '', percentual: true },
  { chave: 'M', nome: 'Momento fletor', unidade: 'kN·m' },
  { chave: 'V', nome: 'Esforço cortante', unidade: 'kN' },
  { chave: 'N', nome: 'Força normal', unidade: 'kN' },
];

// Rampas de reserva da legenda, para quando o módulo de desenho não estiver no ar.
// São sequenciais e de luminosidade crescente: leem igual no tema claro e no escuro.
const RAMPA_ESFORCOS = ['#2c6fbb', '#3fa9c9', '#7ec97a', '#f2c24a', '#e8743b', '#c0392b'];
const RAMPA_APROVEITAMENTO = ['#2f9e5f', '#8dc63f', '#f2c24a', '#e8743b', '#c0392b'];

// Cores de grupo (conjunto, posição, perfil): vinte tons de saturação média, que se
// distinguem entre si e do azul da seleção nos dois temas. A partir da 21ª, `corDeGrupo`
// gera tons novos pelo ângulo de ouro, em três faixas de claridade: um modelo com 160
// posições tem 160 cores diferentes, e vizinhas na ordem ficam longe no matiz.
const PALETA_GRUPOS = ['#d94a4a', '#2f9e5f', '#3d6fd6', '#e08a1e', '#8e44ad', '#17a2b8',
  '#c2185b', '#7cb342', '#f4c20d', '#6d4c41', '#00897b', '#5c6bc0', '#ef6c00', '#4db6ac',
  '#ad1457', '#9e9d24', '#1e88e5', '#e64a19', '#546e7a', '#8d6e63'];
function corDeGrupo(i) {
  if (i < PALETA_GRUPOS.length) return PALETA_GRUPOS[i];
  const k = i - PALETA_GRUPOS.length;
  const h = (k * 137.508) % 360;
  const faixa = k % 3;
  const s = [72, 58, 80][faixa], l = [48, 62, 36][faixa];
  return `hsl(${h.toFixed(1)}, ${s}%, ${l}%)`;
}

const $ = (sel, raiz = document) => raiz.querySelector(sel);

/** Cria um elemento com atributos e filhos, sem innerHTML para dados do usuário. */
/** Mesmo nome de arquivo que `projetos.slug` dá a um desenho 2D (espelho de cad.js). */
const slugDesenho = (s) => String(s || '').replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().toLowerCase().replace(/[\s_-]+/g, '-').slice(0, 60).replace(/^-+|-+$/g, '') || 'desenho';

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'dados') for (const [dk, dv] of Object.entries(v)) e.dataset[dk] = dv;
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) {
    e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return e;
}

const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', {
  maximumFractionDigits: casas, minimumFractionDigits: 0 });
const metros = (mm, casas = 2) => (mm / 1000).toLocaleString('pt-BR', {
  minimumFractionDigits: casas, maximumFractionDigits: casas });
const ponto3 = (p) => p ? `${numero(p[0])}; ${numero(p[1])}; ${numero(p[2])}` : '—';
const normalizarBusca = (s) => String(s || '').toLowerCase().normalize('NFD')
  .replace(/[̀-ͯ]/g, '').replace(/[×*]/g, 'x').replace(/[\s,.]/g, '');

// ----------------------------------------------------- comando de aparência

/** Altera uma camada ou um material (cor, visibilidade, bloqueio), com desfazer. */
class ComandoAparencia extends Comando {
  constructor(colecao, nome, depois, rotulo) {
    super(rotulo);
    this.colecao = colecao;             // 'camadas' ou 'materiais'
    this.nome = nome;
    this.depois = { ...depois };
    this.antes = undefined;
  }
  aplicar(doc) {
    const mapa = doc[this.colecao];
    const atual = mapa.get(this.nome);
    if (this.antes === undefined) this.antes = atual ? { ...atual } : null;
    if (atual) Object.assign(atual, this.depois);
    else mapa.set(this.nome, { nome: this.nome, ...this.depois });
    doc.notificarAparencia();
  }
  desfazer(doc) {
    const mapa = doc[this.colecao];
    if (this.antes) mapa.set(this.nome, { ...this.antes });
    else mapa.delete(this.nome);
    doc.notificarAparencia();
  }
}

// ====================================================================== editor

export class Editor {
  constructor() {
    this.el = {
      canvas: $('#canvas3d'), palco: $('#palco'), snap: $('#camada-snap'),
      retangulo: $('#retangulo-selecao'), barra: $('#barra-ferramentas'),
      props: $('#painel-propriedades'), camadas: $('#painel-camadas'),
      materiais: $('#painel-materiais'), arvore: $('#painel-arvore'),
      dica: $('#dica'), trava: $('#trava'), medida: $('#medida'),
      servidor: $('#estado-servidor'), avisos: $('#avisos'),
      nome: $('#nome-modelo'), modos: $('#modos-exibicao'),
      projecao: $('#btn-projecao'), tema: $('#btn-tema'),
      analise: $('#painel-analise'), painelAnalise: $('.painel[data-painel="analise"]'),
      paineis: $('#paineis'),
      calcular: $('#btn-calcular'), menuCalcular: $('#menu-calcular'),
      vistas: $('#vistas-rapidas'), contagem: $('#carimbo-contagem'),
      extensao: $('#carimbo-extensao'), historico: $('#historico-undo'),
      dialogo: $('#dialogo'), dialogoTitulo: $('#dialogo-titulo'),
      dialogoCorpo: $('#dialogo-corpo'), dialogoOk: $('#dialogo-ok'),
      dialogoCancelar: $('#dialogo-cancelar'), arquivoIfc: $('#arquivo-ifc'),
    };
    this.parametros = new URLSearchParams(location.search);

    // --- estado que as ferramentas leem ---
    this.api = api;
    this.catalogo = { perfis: [], materiais: [], acos: [], camadas: [] };
    this.perfilAtivo = 'W 310×38,7';
    this.acoAtivo = 'ASTM A572 Gr.50';
    this.papelAtivo = 'viga';
    this.parafusoAtivo = '3/4"';
    this.camadaAtiva = 'Estrutura';
    this.planoTrabalho = { origem: [0, 0, 0], normal: [0, 0, 1] };
    this.areaTransferencia = null;

    // --- núcleo ---
    this._aplicarTemaInicial();
    this.documento = new Documento('Modelo');
    this.pilha = new Pilha(this.documento, 200);
    this.cena = new Cena(this.el.canvas, this.documento, { api, escuro: this.escuro });
    this.camera = new Camera(this.el.canvas, this.cena);
    this.selecao = new Selecao(this.documento, this.cena, this.camera);
    this.inferencia = new Inferencia(this.documento, this.cena, this.camera,
                                     this.selecao, this.el.snap);

    this.ferramentas = new Map();      // id -> classe
    this.atalhos = new Map();          // tecla -> id
    this.ativa = null;
    this.idAtiva = '';

    this._sujo = true;
    this._baixo = null;                // estado do botão esquerdo
    this._ultimoMouse = null;
    this._textoMedida = '';
    this._ramosAbertos = new Set();
    this._paineisPendentes = new Set();

    // --- análise de esforços ---
    this.analise = null;            // resposta de /api/modelo/analise
    this.analiseEstado = null;      // grandeza, combinação, camadas e exagero escolhidos
    this.mapa = null;               // MapaDeEsforcos, quando o módulo de desenho existir
    this._geracaoAnalise = 0;       // descarta a resposta de um modelo já trocado
    this._linhasRanking = [];
    this._dadosGalpao = null;       // dados que geraram o modelo: é o que a rota analisa
    this._calculando = false;
  }

  // O renderizador fica na cena; as ferramentas o procuram aqui.
  get renderizador() { return this.cena.renderizador; }
  get renderer() { return this.cena.renderizador; }

  // ------------------------------------------------------------- partida

  async iniciar() {
    this.cena.aoDesenhar = () => { this._sujo = true; };
    this.cena.aoRepintar = () => this.selecao.reaplicar();
    // Textos das cotas: HTML por cima do canvas, abaixo do snap e dos avisos.
    this.el.rotulos = el('div', { class: 'camada-rotulos', 'aria-hidden': 'true' });
    this.el.snap.before(this.el.rotulos);
    this._spansRotulo = new Map();
    // A câmera mexeu (órbita, zoom, amortecimento, transição de vista): o ponto sob o
    // cursor mudou. Refaz a inferência no próximo quadro, para o glifo do snap e a
    // prévia da ferramenta acompanharem a vista em vez de ficarem para trás.
    this.camera.aoMover = () => {
      this._sujo = true;
      if (this._rafCamera || !this._ultimoMouse) return;
      this._rafCamera = requestAnimationFrame(() => {
        this._rafCamera = null;
        this._reprocessarMouse();
      });
    };

    this.documento.aoMudar((ev) => this._aposMudanca(ev));
    this.pilha.aoMudar(() => this._atualizarMenuEditar());
    this.selecao.aoMudar(() => {
      if (this._destaqueAtivo && this.selecao.ids.size === 0) { this._destaqueAtivo = false; this.cena.destacar(null); }
      this._agendarPaineis('props', 'arvore');
      this._atualizarCarimbo();
      this._aposSelecaoAnalise();
    });

    this.el.canvas.addEventListener('webglcontextlost', (ev) => {
      ev.preventDefault();
      (window.__errosEditor || []).push('contexto WebGL perdido');
      this.aviso('O contexto gráfico (WebGL) foi perdido — o navegador liberou a placa de ' +
                 'vídeo. Recarregue a página para voltar a desenhar.', 'erro', 0);
    });

    this._ligarRedimensionamento();
    this._ligarMouse();
    this._ligarTeclado();
    this._ligarMenus();
    this._ligarPaineis();
    this._montarModos();
    this._montarVistasRapidas();
    this._laco();

    this.dica('Carregando catálogo e ferramentas…');
    await Promise.all([this._carregarCatalogo(), this._carregarFerramentas()]);
    this.ativarFerramenta('selecionar');

    const modo = this.parametros.get('modo');
    if (modo) this.definirModo(modo);

    this.projeto = this.parametros.get('projeto') || null;
    if (this.projeto) await this._abrirProjeto();
    else if (this.parametros.get('galpao') === '1') await this._carregarGalpaoDaInterface();
    else if (this.parametros.get('exemplo')) this.carregarExemplo();
    else if (this.parametros.get('abrir')) await this.abrirModelo(this.parametros.get('abrir'));
    if (this.parametros.get('destacar')) this._destacar(this.parametros.get('destacar'));
    else {
      // Sem pedido na URL, volta ao último modelo: o documento é gravado no servidor
      // a cada mudança, então atualizar a página não pode jogar o trabalho fora.
      let ultimo = null;
      try { ultimo = localStorage.getItem(CHAVE_ULTIMO); } catch { ultimo = null; }
      if (ultimo) await this.abrirModelo(ultimo, { avisarErro: false });
    }

    this._aplicarParametrosDeTeste();
    this._agendarPaineis('props', 'camadas', 'materiais', 'arvore');
    this._atualizarCarimbo();
    this._atualizarMenuEditar();
    document.body.dataset.pronto = '1';
    this._publicarErros();
  }

  async _carregarCatalogo() {
    try {
      const cat = await this.api.catalogo();
      this.catalogo = { ...cat, perfis: cat.perfis || [] };
      this.cena.definirCatalogo(this.catalogo);
      if (this.catalogo.perfis.length &&
          !this.catalogo.perfis.some(p => p.nome === this.perfilAtivo)) {
        this.perfilAtivo = this.catalogo.perfis[0].nome;
      }
      this.cena.reconstruirTudo();
    } catch (e) {
      this.aviso(`Catálogo de perfis indisponível: ${e.message}. As barras serão ` +
                 'desenhadas com uma seção genérica.', 'atencao');
    }
  }

  async _carregarFerramentas() {
    const { ferramentas, falhas } = await carregarFerramentas();
    for (const F of ferramentas) {
      this.ferramentas.set(F.id, F);
      const tecla = F.atalho === 'Espaço' ? ' ' : String(F.atalho || '').toLowerCase();
      if (tecla && !this.atalhos.has(tecla)) this.atalhos.set(tecla, F.id);
    }
    if (!this.ferramentas.has('selecionar')) {
      this.aviso('A ferramenta de seleção não carregou; o editor fica só com navegação.', 'erro');
    }
    this.falhasFerramentas = falhas;
    this._montarBarra();
  }

  // ------------------------------------------------- contexto das ferramentas

  executar(cmd) {
    if (!cmd) return null;
    try {
      return this.pilha.executar(cmd);
    } catch (e) {
      console.error('comando falhou:', e);
      this.aviso(`Não foi possível ${String(cmd.rotulo || 'alterar').toLowerCase()}: ` +
                 (e && e.message || e), 'erro');
      return null;
    }
  }

  desfazer() {
    const c = this.pilha.desfazer();
    this.dica(c ? `Desfeito: ${c.rotulo}` : 'Nada para desfazer.');
    return c;
  }

  refazer() {
    const c = this.pilha.refazer();
    this.dica(c ? `Refeito: ${c.rotulo}` : 'Nada para refazer.');
    return c;
  }

  /** Desenho temporário da ferramenta, em milímetros. O núcleo apaga sozinho. */
  previa(obj) {
    if (!obj) return obj;
    // Rótulos em sprite sem atenuação têm tamanho de tela; a escala mm→m da raiz
    // os deixaria mil vezes menores, então compensamos aqui.
    obj.traverse(o => {
      if (o.isSprite && o.material && o.material.sizeAttenuation === false &&
          !o.userData.escalaCompensada) {
        o.scale.multiplyScalar(1 / ESCALA);
        o.userData.escalaCompensada = true;
      }
    });
    this.cena.addPrevia(obj);
    return obj;
  }

  limparPrevia() { this.cena.limparPrevia(); }

  dica(texto) { this.el.dica.textContent = texto || ''; }

  /** Caixa de medidas: o que a ferramenta está medindo agora. */
  medida(texto) {
    this._textoMedida = texto ? String(texto) : '';
    if (document.activeElement !== this.el.medida) this.el.medida.value = this._textoMedida;
    // Operação encerrada: a próxima não deve herdar a âncora de eixo da anterior.
    if (!texto && this.idAtiva !== 'selecionar') this.inferencia.limparAncora();
  }

  definirPerfilAtivo(nome) {
    if (!nome) return;
    this.perfilAtivo = nome;
    if (this.selecao.vazia) this._agendarPaineis('props');
  }

  /** Janela de seleção na tela; `null` apaga. */
  retanguloSelecao(de, para, modo = 'dentro') {
    const r = this.el.retangulo;
    if (!de || !para) { r.hidden = true; return; }
    r.hidden = false;
    r.dataset.modo = modo;
    r.style.left = Math.min(de[0], para[0]) + 'px';
    r.style.top = Math.min(de[1], para[1]) + 'px';
    r.style.width = Math.abs(para[0] - de[0]) + 'px';
    r.style.height = Math.abs(para[1] - de[1]) + 'px';
  }

  cursor(tipo) {
    const t = tipo || 'default';
    this.el.palco.dataset.cursor = (t === 'cruz' || t === 'crosshair') ? 'cruz' : '';
    this.el.canvas.style.cursor = (t === 'cruz' || t === 'crosshair' || t === 'default') ? '' : t;
  }

  descreverEntidade(ent) {
    if (!ent) return '';
    if (ent.tipo === 'barra') {
      return `${ent.nome || 'Barra'} · ${ent.perfil} · ${formatar(comprimentoDaBarra(ent))} · ${ent.papel}`;
    }
    if (ent.tipo === 'chapa') {
      return `${ent.nome || 'Chapa'} · ${numero(ent.espessura, 1)} mm · ` +
             `${numero(areaDaChapa(ent) / 1e6, 3)} m²`;
    }
    if (ent.tipo === 'solido') {
      return `${ent.nome || 'Sólido'} · ${(ent.faces || []).length} faces · ` +
             `${(ent.vertices || []).length} vértices`;
    }
    return ent.nome || ent.tipo;
  }

  // ------------------------------------------------------------ ferramentas

  ativarFerramenta(id) {
    const Classe = this.ferramentas.get(id);
    if (!Classe) {
      if (id) this.dica(`Ferramenta "${id}" ainda não está disponível.`);
      return false;
    }
    if (this.ativa) {
      this._chamar('desativar');
      this.cena.limparPrevia();
    }
    this.inferencia.limparAncora();
    this.inferencia.limpar();
    this.inferencia.ativa = true;
    this.retanguloSelecao(null);
    this._textoMedida = '';
    this.el.medida.value = '';
    this.idAtiva = id;
    this.cursor(id === 'selecionar' ? 'default' : 'cruz');
    this.dica(Classe.dica || Classe.nome);
    try {
      this.ativa = new Classe(this);
      this.ativa.ativar(this);
    } catch (e) {
      console.error(`ferramenta ${id} falhou ao ativar:`, e);
      this.aviso(`A ferramenta ${Classe.nome} falhou ao iniciar: ${e.message}`, 'erro');
    }
    for (const b of this.el.barra.querySelectorAll('.ferramenta')) {
      b.setAttribute('aria-pressed', String(b.dataset.id === id));
    }
    this._atualizarTrava();
    return true;
  }

  // Nomes alternativos que as ferramentas procuram para voltar à seleção.
  usarFerramenta(id) { return this.ativarFerramenta(id); }

  _chamar(metodo, ...args) {
    const f = this.ativa;
    if (!f || typeof f[metodo] !== 'function') return undefined;
    try {
      return f[metodo](...args);
    } catch (e) {
      console.error(`ferramenta ${this.idAtiva}.${metodo}:`, e);
      this.aviso(`Erro na ferramenta ${this.idAtiva}: ${e.message}`, 'erro');
      return undefined;
    }
  }

  _trataArrasto() {
    const f = this.ativa;
    return !!f && typeof f.onSoltar === 'function' &&
           f.onSoltar !== Ferramenta.prototype.onSoltar;
  }

  _montarBarra() {
    const barra = this.el.barra;
    barra.replaceChildren();
    const porGrupo = new Map(GRUPOS.map(([g]) => [g, []]));
    for (const F of this.ferramentas.values()) {
      const g = porGrupo.has(F.grupo) ? F.grupo : 'edicao';
      porGrupo.get(g).push(F);
    }
    const balao = el('div', { class: 'balao-flutuante', hidden: true });
    document.body.append(balao);
    for (const [g, rotulo] of GRUPOS) {
      const lista = porGrupo.get(g);
      if (!lista || !lista.length) continue;
      // A barra tem 46 px: o nome inteiro do grupo não cabe, vai abreviado.
      barra.append(el('div', { class: 'grupo-rotulo', title: rotulo,
                               texto: ABREVIACOES[g] || rotulo.slice(0, 4) }));
      for (const F of lista) {
        const b = el('button', {
          type: 'button', class: 'ferramenta', 'aria-pressed': 'false',
          'aria-label': F.atalho ? `${F.nome} (${F.atalho})` : F.nome,
          dados: { id: F.id },
          onclick: () => this.ativarFerramenta(F.id),
        });
        b.innerHTML = F.icone || `<span style="font-size:11px;font-weight:600">${
          String(F.nome).slice(0, 2)}</span>`;
        b.addEventListener('mouseenter', () => {
          balao.replaceChildren(F.nome);
          if (F.atalho) balao.append(el('kbd', { texto: F.atalho }));
          if (F.dica) balao.append(el('small', { texto: F.dica }));
          const r = b.getBoundingClientRect();
          balao.style.left = (r.right + 8) + 'px';
          balao.style.top = (r.top + r.height / 2) + 'px';
          balao.hidden = false;
        });
        b.addEventListener('mouseleave', () => { balao.hidden = true; });
        barra.append(b);
      }
    }
  }

  // ------------------------------------------------------------------ mouse

  _local(ev) {
    const r = this.el.canvas.getBoundingClientRect();
    return [ev.clientX - r.left, ev.clientY - r.top];
  }

  /** Evento para a ferramenta: os campos do DOM mais o arrasto, quando houver. */
  _evento(ev, extra = {}) {
    return {
      type: ev.type, button: ev.button, buttons: ev.buttons,
      clientX: ev.clientX, clientY: ev.clientY, detail: ev.detail,
      shiftKey: !!ev.shiftKey, ctrlKey: !!ev.ctrlKey, altKey: !!ev.altKey,
      metaKey: !!ev.metaKey, original: ev, arrasto: null, arrastando: false,
      preventDefault: () => ev.preventDefault && ev.preventDefault(),
      stopPropagation: () => ev.stopPropagation && ev.stopPropagation(),
      ...extra,
    };
  }

  _resolver(x, y, ev) {
    const p = this.inferencia.resolver(x, y, ev);
    this._atualizarTrava();
    return p;
  }

  _ligarMouse() {
    const c = this.el.canvas;

    c.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      if (document.activeElement && document.activeElement !== document.body &&
          document.activeElement !== this.el.medida) document.activeElement.blur();
      this._fecharMenus();
      try { c.setPointerCapture(ev.pointerId); } catch { /* sem captura */ }
      const [x, y] = this._local(ev);
      this._baixo = { x, y, arrastou: false };
      if (!this._trataArrasto()) {
        const p = this._resolver(x, y, ev);
        this._confirmarPonto(p, this._evento(ev));
      }
    });

    c.addEventListener('pointermove', (ev) => {
      this._movPendente = ev;
      if (this._rafMov) return;
      this._rafMov = requestAnimationFrame(() => {
        this._rafMov = null;
        const e = this._movPendente;
        this._movPendente = null;
        if (e) this._processarMovimento(e);
      });
    });

    c.addEventListener('pointerup', (ev) => {
      if (ev.button !== 0 || !this._baixo) return;
      try { c.releasePointerCapture(ev.pointerId); } catch { /* já solta */ }
      const [x, y] = this._local(ev);
      const b = this._baixo;
      this._baixo = null;
      if (Math.hypot(x - b.x, y - b.y) > ARRASTO_MIN) b.arrastou = true;
      const arrasto = b.arrastou ? { de: [b.x, b.y], para: [x, y] } : null;
      const p = this._resolver(x, y, ev);
      const e = this._evento(ev, { arrasto });
      if (this._trataArrasto()) {
        if (b.arrastou) this._chamar('onSoltar', p, e);
        else this._confirmarPonto(p, e);
      } else if (b.arrastou) {
        // Arrastar numa ferramenta de clique: o ponto em que soltou é o segundo clique.
        this._confirmarPonto(p, e);
      }
      this._sujo = true;
    });

    c.addEventListener('dblclick', (ev) => {
      const [x, y] = this._local(ev);
      this._chamar('onDuploClique', this._resolver(x, y, ev), this._evento(ev));
    });

    c.addEventListener('pointerleave', () => {
      this._ultimoMouse = null;          // fora do canvas não há o que reinferir
      this.inferencia.limpar();
      this.selecao.realcarSobre(null);
    });
  }

  _confirmarPonto(p, ev) {
    // A âncora vai antes: se a ferramenta encerrar a operação dentro do onPonto
    // (e zerar a caixa de medidas), a limpeza dela prevalece.
    if (this.idAtiva !== 'selecionar') this.inferencia.definirAncora(p.ponto);
    this._chamar('onPonto', p, ev);
  }

  _processarMovimento(ev) {
    const [x, y] = this._local(ev);
    this._ultimoMouse = {
      clientX: ev.clientX, clientY: ev.clientY, shiftKey: ev.shiftKey,
      ctrlKey: ev.ctrlKey, altKey: ev.altKey, metaKey: ev.metaKey,
      buttons: ev.buttons, type: 'pointermove',
    };
    if (ev.buttons & 6) { this.inferencia.limpar(); return; }   // navegando
    let arrasto = null;
    if (this._baixo && (ev.buttons & 1)) {
      if (Math.hypot(x - this._baixo.x, y - this._baixo.y) > ARRASTO_MIN) this._baixo.arrastou = true;
      if (this._baixo.arrastou) arrasto = { de: [this._baixo.x, this._baixo.y], para: [x, y] };
    }
    const p = this._resolver(x, y, ev);
    if (this.idAtiva !== 'selecionar' && this.inferencia.ativa) this.inferencia.desenhar(p);
    else this.inferencia.limpar();
    this._chamar('onMover', p, this._evento(ev, { arrasto, arrastando: !!arrasto }));
  }

  /** Refaz o último movimento — depois de uma tecla mudar trava ou estado. */
  _reprocessarMouse() {
    if (this._ultimoMouse) this._processarMovimento({ ...this._ultimoMouse, buttons: 0 });
  }

  _atualizarTrava() {
    this.el.trava.textContent = this.inferencia.descricaoTrava;
  }

  // ---------------------------------------------------------------- teclado

  _ligarTeclado() {
    document.addEventListener('keydown', (ev) => this._teclaBaixo(ev));
    document.addEventListener('keyup', (ev) => {
      if (this.inferencia.onTecla(ev)) { this._atualizarTrava(); this._reprocessarMouse(); }
    });

    const m = this.el.medida;
    m.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); this._enviarValor(); }
      else if (ev.key === 'Escape') {
        ev.preventDefault();
        m.value = this._textoMedida;
        m.blur();
      }
      ev.stopPropagation();          // o que se digita aqui não é atalho
    });
    m.addEventListener('focus', () => m.select());
    m.addEventListener('blur', () => { if (!m.value.trim()) m.value = this._textoMedida; });
  }

  _teclaBaixo(ev) {
    const alvo = ev.target;
    const tag = alvo && alvo.tagName;
    if (this.el.dialogo.open) return;
    if ((tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') && alvo !== this.el.medida) {
      if (ev.key === 'Escape') alvo.blur();
      return;
    }
    const ctrl = ev.ctrlKey || ev.metaKey;
    const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;

    // 1. Combinações com Ctrl.
    if (ctrl) {
      const acoes = {
        z: () => (ev.shiftKey ? this.refazer() : this.desfazer()),
        y: () => this.refazer(),
        c: () => this.copiar(),
        v: () => this.colar(),
        a: () => this.selecao.tudo(),
        s: () => this.salvar(),
      };
      if (acoes[k]) { ev.preventDefault(); acoes[k](); }
      return;
    }

    // 2. Medida digitada durante a operação, sem precisar clicar na caixa.
    const operando = this._textoMedida && this.idAtiva !== 'selecionar';
    if (operando && !ev.altKey && /^[0-9.,;\-]$/.test(ev.key)) {
      ev.preventDefault();
      this.el.medida.focus();
      this.el.medida.value = ev.key;
      return;
    }

    // 3. A ferramenta tem a primeira palavra.
    if (this._chamar('onTecla', ev) === true) {
      ev.preventDefault();
      this._reprocessarMouse();
      return;
    }

    // 4. Travamento de eixo (setas e Shift).
    if (this.idAtiva !== 'selecionar' && this.inferencia.onTecla(ev)) {
      ev.preventDefault();
      this._atualizarTrava();
      this._reprocessarMouse();
      return;
    }

    // 5. Atalhos globais.
    if (ev.key === 'Escape') {
      this._fecharMenus();
      this._chamar('cancelar');
      this.inferencia.limparAncora();
      this._atualizarTrava();
      return;
    }
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); this.apagarSelecao(); return; }
    // F9, e não uma letra: letra solta já é atalho de ferramenta.
    if (ev.key === 'F9') { ev.preventDefault(); this.alternarAnalise(); return; }
    if (ev.altKey) return;
    if (/^[1-7]$/.test(ev.key)) { ev.preventDefault(); this.camera.vista(TECLAS_VISTA[+ev.key - 1]); return; }
    if (k === 'z' && !this.atalhos.has('z')) { this.camera.zoomExtensao(); return; }
    const id = this.atalhos.get(k);
    if (id) { ev.preventDefault(); this.ativarFerramenta(id); }
  }

  _enviarValor() {
    const m = this.el.medida;
    const texto = m.value.trim();
    m.blur();
    if (!texto || texto === this._textoMedida) { m.value = this._textoMedida; return; }
    const r = this._chamar('onValor', texto);
    if (r === false) {
      const nome = this.ativa ? this.ativa.constructor.nome : 'ativa';
      this.aviso(`"${texto}" não foi aceito pela ferramenta ${nome}.`, 'atencao', 4500);
      m.value = this._textoMedida;
    } else if (document.activeElement !== m) {
      m.value = this._textoMedida;
    }
    this._reprocessarMouse();
  }

  // ------------------------------------------------------ edição global

  apagarSelecao() {
    const ids = [...this.selecao.ids];
    if (!ids.length) { this.dica('Nada selecionado para apagar.'); return; }
    const livres = ids.filter(i => this.documento.editavel(this.documento.get(i)));
    if (livres.length < ids.length) {
      this.aviso(`${ids.length - livres.length} objeto(s) em camada bloqueada não foram apagados.`, 'atencao');
    }
    if (!livres.length) return;
    this.selecao.limpar();
    this.executar(new ComandoRemover(livres));
  }

  copiar() {
    const ids = [...this.selecao.ids];
    if (!ids.length) { this.dica('Selecione o que copiar.'); return; }
    const entidades = ids.map(i => clonar(this.documento.get(i))).filter(Boolean);
    const caixa = this.documento.caixa(ids);
    this.areaTransferencia = { entidades, base: caixa[0] };
    this.dica(`${entidades.length} objeto(s) copiado(s). Ctrl+V para colar.`);
  }

  colar() {
    const at = this.areaTransferencia;
    if (!at || !at.entidades || !at.entidades.length) { this.dica('Área de transferência vazia.'); return; }
    if (this.ferramentas.has('copiar')) {
      // A ferramenta Copiar copia a seleção ao entrar; sem seleção, ela cola.
      this.selecao.limpar();
      this.ativarFerramenta('copiar');
      return;
    }
    const novas = at.entidades.map(e => {
      const c = clonar(e);
      delete c.id;
      return mover(criar(c), [1000, 1000, 0]);
    });
    this.executar(new ComandoAdicionar(novas, `Colar ${novas.length} objeto(s)`));
    this.selecao.definir(novas.map(e => e.id));
  }

  /** Altera os mesmos campos em várias entidades, numa entrada só de desfazer. */
  alterarEntidades(ids, campos, rotulo) {
    const mud = {};
    let bloqueadas = 0;
    for (const id of ids) {
      const e = this.documento.get(id);
      if (!e) continue;
      if (!this.documento.editavel(e)) { bloqueadas++; continue; }
      mud[id] = typeof campos === 'function' ? campos(e) : campos;
    }
    if (bloqueadas) this.aviso(`${bloqueadas} objeto(s) bloqueado(s) não foram alterados.`, 'atencao');
    if (Object.keys(mud).length) this.executar(new ComandoAlterar(mud, rotulo));
  }

  definirModo(modo) {
    this.cena.definirModo(modo);
    for (const b of this.el.modos.querySelectorAll('button')) {
      b.setAttribute('aria-pressed', String(b.dataset.modo === this.cena.modo));
    }
  }

  // --------------------------------------------------------- documento

  _aposMudanca({ acao }) {
    this.selecao.podar();
    if (acao === 'tudo' || acao === 'aparencia') {
      this._agendarPaineis('props', 'camadas', 'materiais', 'arvore');
    } else {
      this._agendarPaineis('props', 'arvore', 'camadas', 'materiais');
    }
    this._atualizarCarimbo();
    this._sujo = true;
    this._agendarAutosave();
  }

  /** Troca o documento inteiro (abrir, importar, gerar do galpão). */
  carregarDocumento(json, { enquadrar = true, autosalvar = true } = {}) {
    // A análise é de um modelo só: trocar o documento a invalida. Quem gera do galpão
    // repõe os dados logo em seguida; modelo aberto ou importado fica sem o que calcular.
    this._limparAnalise();
    this._dadosGalpao = null;
    const novo = Documento.deJSON(json);
    this.selecao.limpar();
    this.documento.substituirPor(novo);
    this.pilha.limpar();
    this.el.nome.value = this.documento.nome || 'Modelo';
    if (!this.documento.camadas.has(this.camadaAtiva)) {
      this.camadaAtiva = this.documento.camadas.keys().next().value || 'Estrutura';
    }
    if (enquadrar) this.camera.vista('isometrica', this.documento.caixa());
    this._agendarPaineis('props', 'camadas', 'materiais', 'arvore');
    if (autosalvar) {
      this._agendarAutosave();
    } else {
      // `substituirPor` avisa "tudo mudou" e agendaria uma gravação do que acabou de
      // vir do servidor; cancela, senão a primeira mudança de verdade espera na fila
      this._autosavePendente = false;
      if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    }
    return this.documento;
  }

  carregarExemplo(dados = {}) {
    const d = { vao: 20, comprimento: 40, pe_direito: 6, espacamento_porticos: 5,
                inclinacao: 10, ...dados };
    this.carregarDocumento(modeloDeExemplo(d, this.catalogo.perfis || []));
    const est = this.documento.estatisticas();
    this.dica(`Modelo de exemplo (não dimensionado): galpão ${numero(d.vao)} × ${numero(d.comprimento)} m ` +
              `— ${est.barras} barras e ${est.chapas} chapas.`);
  }

  // ------------------------------------------------------ arquivo e servidor

  async salvar(nome = null) {
    const n = nome || this.el.nome.value.trim() || this.documento.nome || 'modelo';
    this.documento.nome = n;
    try {
      if (this.projeto && !nome) {
        const s = await this.api.salvarModeloDoProjeto(this.projeto, this.documento.paraJSON(), this._modeloAlterado);
        if (s && s.alterado) this._modeloAlterado = s.alterado;
        this.aviso(`Modelo salvo no projeto (${s.entidades} objetos).`, 'info');
        return;
      }
      const r = await this.api.salvar(this.documento.paraJSON(), n);
      this._lembrar(r.salvo || n);
      this.aviso(`Modelo salvo: projetos/modelos/${r.salvo} (${r.entidades} objetos).`, 'info');
    } catch (e) {
      this.aviso(`Não foi possível salvar: ${e.message}`, 'erro');
    }
  }

  async salvarComo() {
    const campo = el('input', { value: this.el.nome.value || 'Modelo', spellcheck: 'false' });
    const corpo = el('div', { class: 'campos' }, el('label', { texto: 'Nome do modelo' }), campo);
    if (await this.dialogo({ titulo: 'Salvar como', corpo, ok: 'Salvar' }) !== 'ok') return;
    const nome = campo.value.trim();
    if (!nome) return;
    this.el.nome.value = nome;
    await this.salvar(nome);
  }

  async abrirModelo(nome, { avisarErro = true } = {}) {
    try {
      const r = await this.api.abrir(nome);
      // o que acabou de vir do servidor não precisa voltar para lá
      this.carregarDocumento(r.documento, { autosalvar: false });
      this._lembrar(nome);
      this.dica(`Modelo "${nome}" aberto.`);
    } catch (e) {
      if (avisarErro) this.aviso(`Não foi possível abrir "${nome}": ${e.message}`, 'erro');
      else this.dica(`O último modelo ("${nome}") não está mais no servidor.`);
    }
  }

  // ------------------------------------------------------------ gravação automática

  /** Guarda o nome (já em forma de arquivo) do modelo a reabrir na próxima visita. */
  _lembrar(nome) {
    const n = String(nome || '').replace(/\.modelo\.json$/, '');
    try { if (n) localStorage.setItem(CHAVE_ULTIMO, n); } catch { /* janela privativa */ }
  }

  /** Agenda a gravação no servidor depois de um intervalo sem mudanças. */
  _agendarAutosave() {
    this._autosavePendente = true;
    if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
    this._autosaveTimer = setTimeout(() => this._autosalvar(), ATRASO_AUTOSAVE);
  }

  /**
   * Grava o documento em projetos/modelos/<nome>.modelo.json, o mesmo arquivo do
   * botão Salvar, e anota o nome para a próxima abertura. Uma gravação por vez: se o
   * modelo mudar no meio, outra é agendada quando esta terminar. Falha em silêncio na
   * barra de dica, porque não é o usuário que pediu.
   */
  async _autosalvar() {
    this._autosaveTimer = null;
    if (this._autosalvando) { this._agendarAutosave(); return; }
    if (!this._autosavePendente || !this.documento.tamanho) return;
    this._autosavePendente = false;
    this._autosalvando = true;
    const nome = this.el.nome.value.trim() || this.documento.nome || 'modelo';
    try {
      if (this.projeto) {
        const s = await this.api.salvarModeloDoProjeto(this.projeto, this.documento.paraJSON(), this._modeloAlterado);
        if (s && s.alterado) this._modeloAlterado = s.alterado;
      } else {
        const r = await this.api.salvar(this.documento.paraJSON(), nome);
        this._lembrar(r.salvo || nome);
      }
    } catch (e) {
      this.dica(`Gravação automática falhou: ${e.message}`);
      if (/outra tela|recarregue/i.test(e.message || '')) {
        // modelo mais novo no servidor: parar de insistir e avisar com destaque
        this._autosavePendente = false;
        this.aviso(`Este modelo foi alterado por outra tela (por exemplo, "Aplicar furos" no CAD) depois de aberto aqui. Recarregue a página (F5) para ver a versão atual; as suas edições desde então não foram gravadas.`, 'erro', 0);
      }
    } finally {
      this._autosalvando = false;
      if (this._autosavePendente) this._agendarAutosave();
    }
  }

  async dialogoAbrir() {
    let lista = [];
    try { lista = await this.api.lista(); }
    catch (e) { this.aviso(`Não foi possível listar os modelos: ${e.message}`, 'erro'); return; }
    let escolhido = null;
    const corpo = el('div', { class: 'lista-modelos' });
    if (!lista.length) corpo.append(el('p', { class: 'explica', texto: 'Nenhum modelo salvo ainda.' }));
    for (const m of lista) {
      corpo.append(el('button', {
        type: 'button',
        onclick: () => { escolhido = m.nome; this.el.dialogo.close('ok'); },
      }, el('span', { texto: m.nome }), el('span', { class: 'dim', texto: `${numero(m.tamanho_kb, 1)} kB` })));
    }
    const r = await this.dialogo({ titulo: 'Abrir modelo', corpo, ok: null });
    if (r === 'ok' && escolhido) await this.abrirModelo(escolhido);
  }

  async novo() {
    if (this.documento.tamanho) {
      const r = await this.dialogo({
        titulo: 'Novo modelo',
        corpo: el('p', { class: 'explica', texto: 'O modelo atual será fechado. O que não foi salvo se perde.' }),
        ok: 'Começar do zero',
      });
      if (r !== 'ok') return;
    }
    this.carregarDocumento({ nome: 'Modelo', entidades: [] }, { enquadrar: false });
    this.camera.enquadrar([[-2000, -2000, 0], [22000, 22000, 9000]]);
    this.dica('Modelo novo.');
  }

  /** Dimensiona o galpão no servidor e carrega o modelo 3D que sai dele. */
  async gerarDoGalpao(dados) {
    this.dica('Dimensionando o galpão e gerando o modelo 3D…');
    let r;
    try {
      r = await this.api.doGalpao(dados);
    } catch (e) {
      const msg = e instanceof ErroServidor ? e.message : String(e && e.message || e);
      this.aviso(`O servidor não conseguiu gerar o modelo 3D do galpão: ${msg}`, 'erro', 0);
      this.dica('Modelo do galpão indisponível. Você pode desenhar à mão ou usar Arquivo → Modelo de exemplo.');
      return false;
    }
    if (!r || !r.documento) {
      this.aviso('O servidor respondeu sem documento 3D.', 'erro', 0);
      return false;
    }
    this.carregarDocumento(r.documento);
    // Guarda o que gerou o modelo: é isto que "Calcular estrutura" manda analisar. O
    // cálculo em si só acontece quando o usuário pedir.
    this._dadosGalpao = dados;
    this._atualizarBotaoCalcular();
    const avisos = (r.avisos || []).map(textoDe);
    const erros = (r.erros || []).map(textoDe);
    for (const t of erros.slice(0, 4)) this.aviso(t, 'erro', 0);
    for (const t of avisos.slice(0, 4)) this.aviso(t, 'atencao', 12000);
    const est = r.estatisticas || this.documento.estatisticas();
    const resto = [];
    if (erros.length) resto.push(`${erros.length} erro(s) de dimensionamento`);
    if (avisos.length) resto.push(`${avisos.length} aviso(s)`);
    this.dica(`Galpão carregado: ${est.barras} barras, ${est.chapas} chapas` +
              (resto.length ? ` — ${resto.join(', ')}.` : '.'));
    return true;
  }

  /**
   * Abre o editor dentro de um projeto (?projeto=<slug>): o modelo é o modelo.json da
   * pasta do projeto, e a gravação automática escreve nele.
   *
   * Projeto de galpão sem modelo ainda gera um a partir do dimensionamento. Com modelo
   * salvo, abre o salvo — que pode ter edições feitas à mão — e, se o dimensionamento
   * mudou depois, avisa e oferece gerar de novo em vez de sobrescrever calado.
   */
  async _abrirProjeto() {
    const s = this.projeto;
    const dim = document.getElementById('link-dimensionamento');
    let projeto = null;
    try {
      projeto = (await this.api.projeto(s)).projeto;
    } catch (e) {
      this.aviso(`Projeto "${s}" não encontrado: ${e.message}`, 'erro', 0);
      this.projeto = null;
      if (dim) dim.hidden = true;
      return;
    }
    document.title = `${projeto.nome || s} — Editor 3D`;
    if (dim) {
      dim.href = '/dimensionar?projeto=' + encodeURIComponent(s);
      dim.hidden = projeto.tipo !== 'galpao';
    }
    const dados = (projeto.dados && typeof projeto.dados === 'object') ? projeto.dados : null;
    let modelo = null;
    try { modelo = await this.api.modeloDoProjeto(s); } catch { modelo = null; }
    this._modeloAlterado = modelo && modelo.alterado ? modelo.alterado : null;

    if (modelo && modelo.documento) {
      this.carregarDocumento(modelo.documento, { autosalvar: false });
      if (dados) {                      // é o que "Calcular estrutura" analisa
        this._dadosGalpao = dados;
        this._atualizarBotaoCalcular();
      }
      this.dica(`Projeto "${projeto.nome || s}" aberto.`);
      const gerado = this.documento.projeto || {};
      const mudou = dados && ['vao', 'comprimento', 'pe_direito', 'espacamento_porticos', 'inclinacao',
                              'com_misula', 'base_rotulada', 'espacamento_tercas']
        .some(k => k in gerado && String(gerado[k]) !== String(dados[k]));
      if (mudou) {
        const botao = el('button', { type: 'button', texto: 'Gerar de novo' });
        botao.addEventListener('click', async () => {
          if (await this.gerarDoGalpao(dados)) this.dica('Modelo refeito a partir do dimensionamento atual.');
        });
        this.aviso(el('span', {}, 'O dimensionamento mudou depois que este modelo foi gerado. ' +
          'Gerar de novo descarta as edições feitas à mão. ', botao), 'atencao', 0);
      }
      return;
    }
    if (dados) { await this.gerarDoGalpao(dados); return; }
    this.dica(projeto.tipo === 'ifc'
      ? 'Projeto sem modelo: use IFC → Importar IFC… para trazer o arquivo.'
      : 'Projeto sem dimensionamento ainda: preencha os dados em Dimensionamento, ou desenhe à mão.');
  }

  async _carregarGalpaoDaInterface() {
    let dados = null;
    try {
      const bruto = localStorage.getItem(CHAVE_GALPAO);
      dados = bruto ? JSON.parse(bruto) : null;
    } catch { dados = null; }
    if (!dados || typeof dados !== 'object') {
      this.aviso('Nenhum galpão dimensionado foi encontrado neste navegador. Dimensione um ' +
                 'galpão na interface principal e use o botão "Modelo 3D" de novo.', 'atencao', 0);
      this.dica('Editor vazio: não havia galpão dimensionado para carregar.');
      return;
    }
    await this.gerarDoGalpao(dados);
  }

  async dialogoGalpao() {
    let salvo = {};
    try { salvo = JSON.parse(localStorage.getItem(CHAVE_GALPAO) || '{}') || {}; } catch { salvo = {}; }
    const campos = [
      ['vao', 'Vão (m)', 20], ['comprimento', 'Comprimento (m)', 40],
      ['pe_direito', 'Pé-direito (m)', 6], ['espacamento_porticos', 'Entre pórticos (m)', 5],
      ['inclinacao', 'Inclinação (%)', 10],
    ];
    const entradas = {};
    const grade = el('div', { class: 'campos' });
    for (const [k, rot, padrao] of campos) {
      entradas[k] = el('input', { type: 'number', step: 'any', value: salvo[k] ?? padrao });
      grade.append(el('label', { texto: rot }), entradas[k]);
    }
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: 'O servidor dimensiona o galpão e devolve pilares, vigas, ' +
        'terças, contraventamento e chapas já com os perfis calculados. Os demais dados (vento, ' +
        'cargas, aços) vêm do que está salvo na interface principal.' }), grade);
    if (await this.dialogo({ titulo: 'Gerar do galpão dimensionado', corpo, ok: 'Gerar' }) !== 'ok') return;
    const dados = { ...salvo };
    for (const [k] of campos) dados[k] = parseFloat(String(entradas[k].value).replace(',', '.'));
    await this.gerarDoGalpao(dados);
  }

  async exportarIFC() {
    if (!this.documento.tamanho) { this.dica('O modelo está vazio.'); return; }
    this.dica('Exportando IFC…');
    try {
      const r = await this.api.exportarIFC(this.documento.paraJSON(),
                                           this.el.nome.value || this.documento.nome,
                                           this.projeto ? { projeto: this.projeto } : {});
      const a = r.arquivo || {};
      const conteudo = el('span', {}, `IFC exportado (${r.entidades} objetos): `,
        el('a', { href: a.url, download: a.nome || true, texto: a.nome || 'baixar' }),
        a.tamanho_kb ? ` · ${numero(a.tamanho_kb, 1)} kB` : '');
      this.aviso(conteudo, 'info', 0);
      this.dica('IFC exportado.');
    } catch (e) {
      this.aviso(`Não foi possível exportar o IFC: ${e.message}`, 'erro', 0);
    }
  }

  async _arquivoEscolhido(arquivo) {
    if (!arquivo) return;
    const modo = this._modoArquivo || 'importar';
    this.dica(`${modo === 'importar' ? 'Importando' : 'Lendo'} ${arquivo.name}…`);
    try {
      if (modo === 'detalhar') {
        await this._detalharIFC(arquivo);
        return;
      }
      if (modo === 'inspecionar') {
        const r = await this.api.inspecionarIFC(arquivo);
        const pre = el('pre', { style: 'font:12px var(--mono);white-space:pre-wrap;margin:0' },
                       JSON.stringify(r, null, 2).slice(0, 8000));
        await this.dialogo({ titulo: `Conteúdo de ${arquivo.name}`, corpo: pre, ok: null });
        return;
      }
      let r;
      if (this.projeto) {
        r = await this.api.importarIFCNoProjeto(this.projeto, arquivo);
        const m = await this.api.modeloDoProjeto(this.projeto);
        this._modeloAlterado = m && m.alterado ? m.alterado : null;
        this.carregarDocumento(m.documento, { autosalvar: false });
      } else {
        r = await this.api.importarIFC(arquivo);
        this.carregarDocumento(r.documento);
      }
      const e = r.estatisticas || this.documento.estatisticas();
      this.aviso(`${arquivo.name}: ${e.entidades} objetos importados ` +
                 `(${e.barras} barras, ${e.chapas} chapas, ${e.solidos} sólidos).`, 'info', 9000);
      this.dica(`${arquivo.name} importado.`);
      const rel = r.relatorio || {};
      for (const t of (rel.avisos || rel.ignorados || []).slice(0, 3)) this.aviso(textoDe(t), 'atencao');
    } catch (e) {
      this.aviso(`Não foi possível ${modo === 'importar' ? 'importar' : 'ler'} ${arquivo.name}: ${e.message}`, 'erro', 0);
    }
  }

  /** Detalhamento para produção: mostra o resumo, os links dos arquivos e as peças
   *  com ressalva. O arquivo pode ter dezenas de megabytes, então avisa que demora. */
  async _detalharIFC(arquivo) {
    this.dica(`Detalhando as peças de ${arquivo.name}… (um arquivo grande leva um minuto)`);
    const r = await this.api.detalharIFC(arquivo, this.projeto);
    const arq = r.arquivos || {};
    const link = (chave, rotulo) => arq[chave]
      ? el('a', { href: arq[chave].url, download: arq[chave].nome || true, texto: rotulo })
      : el('span', { texto: rotulo });
    const classes = Object.entries(r.por_classe || {}).map(([c, n]) => `${c}: ${n}`).join(' · ');
    const corpo = el('div', {},
      el('p', {}, `${numero(r.posicoes)} posições, ${numero(r.pecas)} peças, ` +
                  `${numero(r.peso_total_kg, 1)} kg. ${classes}`),
      el('p', {}, 'Arquivos: ', link('dxf', 'DXF de produção'), ' · ',
                  link('romaneio', 'romaneio (CSV)'), ' · ', link('relatorio', 'relatório (JSON)')),
      el('p', { class: 'nota' }, 'O DXF é único, em milímetro e 1:1: camadas ACO e FURO ' +
        'têm a geometria de corte; COTA e TEXTO, a anotação; AUXILIAR, a moldura das células.'));
    const ressalvas = r.com_ressalva || [];
    if (ressalvas.length) {
      const lista = el('ul', { style: 'max-height:40vh;overflow:auto;font:12px var(--mono);padding-left:1.2em' },
        ...ressalvas.map(p => el('li', {}, el('b', { texto: `${p.marca} ${p.perfil}` }),
                                          ': ' + (p.observacoes || []).join('; '))));
      corpo.append(el('p', {}, el('b', { texto: `${ressalvas.length} posição(ões) com ressalva` }),
                                ' — confira antes de mandar cortar:'), lista);
    }
    const acessorios = Object.entries(r.acessorios || {});
    if (acessorios.length) {
      corpo.append(el('p', { class: 'nota' }, 'Só no romaneio: ' +
        acessorios.map(([n, q]) => `${n} ×${q}`).join(', ')));
    }
    await this.dialogo({ titulo: `Detalhamento de ${arquivo.name}`, corpo, ok: null });
    this.dica(`Detalhamento de ${arquivo.name} pronto: ${numero(r.posicoes)} posições.`);
  }

  // ------------------------------------------------------------ desenho 2D

  /** Troca para a tela do CAD 2D na mesma janela (o link "Modelo 3D" do CAD traz de volta). */
  _abrirCAD(desenho = null) {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para gerar desenhos 2D.', 'atencao'); return; }
    const url = `/cad?projeto=${encodeURIComponent(this.projeto)}` + (desenho ? `&desenho=${encodeURIComponent(desenho)}` : '');
    this._irPara(url);
  }

  /** Tela da lista de materiais do projeto (romaneio, perfis, chapas, conjuntos). */
  _abrirMateriais() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para ver a lista de materiais.', 'atencao'); return; }
    this._irPara(`/materiais?projeto=${encodeURIComponent(this.projeto)}`);
  }

  async _excluirDesenhos() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador).', 'atencao'); return; }
    let lista = [];
    try { lista = await (await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`)).json(); } catch { lista = []; }
    await this.dialogoExcluirDesenhos(Array.isArray(lista) ? lista : []);
    this._listarDesenhosNoMenu();
  }

  /** Um desenho só, pelo × ao lado dele no menu. */
  async _excluirUmDesenho(nome, titulo) {
    const corpo = el('div', {}, el('p', {}, `Excluir o desenho "${titulo || nome}"? Ele vai para a pasta .lixeira dos dados.`));
    if (await this.dialogo({ titulo: 'Excluir desenho', corpo, ok: 'Excluir' }) !== 'ok') return;
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(nome)}/excluir`, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: '{}' });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      this.aviso(`Desenho "${titulo || nome}" excluído.`, 'info', 6000);
    } catch (e) { this.aviso(`Não foi possível excluir: ${e.message}`, 'erro'); }
    this._listarDesenhosNoMenu();
  }

  /**
   * Diálogo com a lista dos desenhos do projeto em caixas; os marcados vão para a
   * lixeira da pasta de dados (.lixeira), de onde dá para recuperar à mão.
   */
  async dialogoExcluirDesenhos(lista, { atual = null } = {}) {
    if (!lista.length) { this.aviso('O projeto não tem desenhos para excluir.', 'atencao'); return []; }
    const caixas = new Map();
    const opcoes = el('div', { class: 'lista-opcoes', style: 'max-height:45vh;overflow:auto' });
    for (const d of lista) {
      const c = el('input', { type: 'checkbox' });
      caixas.set(d.nome, c);
      opcoes.append(el('label', { class: 'linha' }, c, ` ${d.titulo || d.nome}`,
        el('small', { texto: `  ${(d.entidades || 0).toLocaleString('pt-BR')} objetos · ${(d.vistas || []).length} vista(s) · ${d.alterado ? d.alterado.replace('T', ' ').slice(0, 16) : ''}` })));
    }
    const marcar = (teste) => { for (const d of lista) caixas.get(d.nome).checked = teste(d); };
    const atalhos = el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin:8px 0' },
      el('button', { type: 'button', onclick: () => marcar(d => /^detalhamento/i.test(d.nome)) }, 'Marcar detalhamentos'),
      el('button', { type: 'button', onclick: () => marcar(d => /^prancha(-\d+)?$/i.test(d.nome)) }, 'Marcar pranchas'),
      el('button', { type: 'button', onclick: () => marcar(() => true) }, 'Marcar todos'),
      el('button', { type: 'button', onclick: () => marcar(() => false) }, 'Desmarcar'));
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Os desenhos marcados saem do projeto e vão para a pasta .lixeira dos dados (dá para recuperar à mão). Depois, "Detalhar peças e conjuntos…" gera tudo de novo.' }),
      atalhos, opcoes);
    if (await this.dialogo({ titulo: 'Excluir desenhos do projeto', corpo, ok: 'Excluir marcados' }) !== 'ok') return [];
    const nomes = lista.map(d => d.nome).filter(n => caixas.get(n).checked);
    if (!nomes.length) return [];
    const excluidos = [];
    for (const n of nomes) {
      try {
        const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(n)}/excluir`, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: '{}' });
        const j = await r.json();
        if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
        excluidos.push(n);
      } catch (e) { this.aviso(`Não foi possível excluir "${n}": ${e.message}`, 'erro'); }
    }
    if (excluidos.length) this.aviso(`${excluidos.length} desenho(s) excluído(s)${excluidos.includes(atual) ? ' — inclusive o que estava aberto' : ''}.`, 'info', 8000);
    return excluidos;
  }

  /**
   * Detalhe de uma peça (duplo clique no 3D): o servidor gera "Detalhe – P77" — chapa
   * plana vira chapa paramétrica no modelo, com os furos editáveis no desenho — e o
   * CAD abre nele. O modelo é recarregado ao voltar, então nada fica desatualizado.
   */
  async abrirDetalheDaPeca(ent) {
    const marca = ent && ent.atributos && ent.atributos.marcas && ent.atributos.marcas.posicao;
    if (!marca) { this.aviso('Esta peça não tem marca de posição.', 'atencao'); return; }
    this.dica(`Gerando o detalhe de ${marca}…`);
    try {
      await this._gravarAntesDeGerar();
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar-posicao`, {
        // a peça clicada é a referência: o desenho sai na orientação em que ela está
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ marca, referencia: ent.id }),
      });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      window.location.href = `/cad?projeto=${encodeURIComponent(this.projeto)}&desenho=${encodeURIComponent(j.nome)}`;
    } catch (e) { this.aviso(`Não foi possível abrir o detalhe de ${marca}: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /**
   * `destacar=posicao:P77,P12` ou `conjunto:M2` na URL (vindo do "Ver no 3D" do CAD):
   * seleciona as peças com essa marca e enquadra a câmera nelas.
   */
  _destacar(spec) {
    const m = /^(posicao|conjunto):(.+)$/.exec(String(spec || ''));
    if (!m) return;
    const chave = m[1];
    const marcas = new Set(m[2].split(',').map(s => s.trim()).filter(Boolean));
    const ids = [...this.documento.entidades.values()]
      .filter(e => e.atributos && e.atributos.marcas && marcas.has(String(e.atributos.marcas[chave])))
      .map(e => e.id);
    if (!ids.length) { this.aviso(`Nenhuma peça com ${chave} ${[...marcas].join(', ')} no modelo.`, 'atencao'); return; }
    this.selecao.definir(ids);
    this.cena.destacar(ids);
    this._destaqueAtivo = true;
    this.camera.zoomSelecao(ids);
    // as malhas do servidor chegam depois: enquadra de novo quando a cena já as tem
    setTimeout(() => { if (this.selecao.ids.size === ids.length) { this.camera.zoomSelecao(ids); this.cena.destacar(ids); } }, 1500);
    this.aviso(`${ids.length} peça(s) ${[...marcas].join(', ')} em destaque; o resto do modelo está esmaecido. Esc limpa a seleção e devolve o modelo; Desenho 2D volta ao CAD.`, 'info', 14000);
    const url = new URL(location.href); url.searchParams.delete('destacar'); history.replaceState(null, '', url);
  }

  /** Navega na mesma janela depois de gravar o que estiver pendente do autosave. */
  _irPara(url) {
    this._gravarAntesDeGerar().catch(() => {}).then(() => { window.location.href = url; });
  }

  /**
   * Desenhos 2D já gravados no projeto, no fim do menu Desenho 2D: cada corte ou
   * conjunto de vistas é um arquivo em desenhos-2d/, e reabrir não gera nada de novo.
   */
  async _listarDesenhosNoMenu() {
    const lista = document.querySelector('.menu[data-menu="desenho2d"] .menu-lista');
    if (!lista) return;
    let bloco = lista.querySelector('.desenhos-salvos');
    if (!bloco) { bloco = el('div', { class: 'desenhos-salvos' }); lista.append(el('hr'), bloco); }
    if (!this.projeto) { bloco.replaceChildren(el('div', { class: 'menu-nota', texto: 'Desenhos salvos: abra o modelo por um projeto.' })); return; }
    bloco.replaceChildren(el('div', { class: 'menu-nota', texto: 'Desenhos salvos…' }));
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`);
      const desenhos = await r.json();
      if (!r.ok || desenhos.erro) throw new Error(desenhos.erro || r.statusText);
      if (!desenhos.length) { bloco.replaceChildren(el('div', { class: 'menu-nota', texto: 'Nenhum desenho salvo neste projeto ainda.' })); return; }
      bloco.replaceChildren(el('div', { class: 'menu-nota', texto: `Desenhos salvos (${desenhos.length}) — abrir no CAD:` }),
        ...desenhos.map(d => el('div', { class: 'desenho-salvo' },
          el('button', { type: 'button', 'data-desenho': d.nome,
            title: `${(d.vistas || []).join(', ') || 'sem vistas'} · ${d.kb >= 1024 ? (d.kb / 1024).toFixed(1) + ' MB' : Math.round(d.kb) + ' kB'} · ${d.alterado ? d.alterado.replace('T', ' ').slice(0, 16) : ''}` },
            el('span', { texto: d.titulo || d.nome }),
            el('small', { texto: `${(d.entidades || 0).toLocaleString('pt-BR')} objetos · ${(d.vistas || []).length} vista(s)` })),
          el('button', { type: 'button', class: 'excluir', 'data-excluir': d.nome, 'data-titulo': d.titulo || d.nome, title: 'Excluir este desenho (vai para a lixeira)', texto: '×' }))));
    } catch (e) {
      bloco.replaceChildren(el('div', { class: 'menu-nota', texto: `Não foi possível listar os desenhos: ${e.message}` }));
    }
  }

  async _pedirVista(corpo) {
    const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/vista2d`, {
      method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo),
    });
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }

  async _gravarAntesDeGerar() {
    // a vista é feita do modelo.json do projeto: o que está por gravar vai antes
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    if (this._autosavePendente) await this._autosalvar();
  }

  /**
   * Corte 2D do plano de seção: manda ao servidor o plano (origem e normal, em mm do
   * documento), com a profundidade de vista pedida, e abre o CAD no desenho gerado.
   */
  async gerarDesenhoDoCorte(plano = null) {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para gerar desenhos 2D.', 'atencao'); return; }
    const secao = this.ferramentas.get('secao');
    const p = plano || (secao && secao.constructor.ultimo);
    if (!p) { this.aviso('Não há plano de corte. Use a ferramenta Seção (X): clique numa face ou tecle X, Y ou Z.', 'atencao'); this.ativarFerramenta('secao'); return; }
    const nome = el('input', { type: 'text', value: `Corte ${String.fromCharCode(65 + Math.min(25, this._cortesGerados || 0))}` });
    const prof = el('input', { type: 'number', step: 'any', value: '1500' });
    const rot = el('input', { type: 'checkbox', checked: 'checked' });
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: 'O que o plano atravessa sai como seção hachurada; o que está além, até a profundidade, sai projetado. O lado visível é o da seta da ferramenta Seção.' }),
      el('div', { class: 'campos' }, el('label', { texto: 'Nome do desenho' }), nome,
        el('label', { texto: 'Profundidade de vista (mm)' }), prof, el('label', { texto: 'Rotular peças cortadas' }), rot));
    if (await this.dialogo({ titulo: 'Gerar desenho 2D do corte', corpo, ok: 'Gerar e abrir' }) !== 'ok') return;
    this.dica('Gravando o modelo e gerando o corte…');
    try {
      await this._gravarAntesDeGerar();
      const profundidade = parseFloat(prof.value);
      const j = await this._pedirVista({
        vista: { origem: [...p.origem], normal: [...p.normal], profundidade: isFinite(profundidade) && profundidade > 0 ? profundidade : null,
                 cortar: true, rotular: rot.checked, nome: nome.value.trim() || 'Corte', tipo: 'corte' },
        desenho: nome.value.trim() || 'Corte',
      });
      this._cortesGerados = (this._cortesGerados || 0) + 1;
      const v = j.vista || {};
      this.aviso(`Corte gerado: ${v.pecas_cortadas || 0} peça(s) cortada(s), ${v.pecas_projetadas || 0} projetada(s). Abrindo o CAD…`, 'info', 6000);
      this._abrirCAD(j.nome);
    } catch (e) {
      this.aviso(`Não foi possível gerar o corte: ${e.message}`, 'erro', 0);
    }
  }

  /**
   * Detalhamento para produção: uma célula por posição (peças iguais contadas uma vez)
   * e a elevação de cada conjunto, em desenhos por grupo, mais o romaneio.
   */
  async dialogoDetalharPecas() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para detalhar.', 'atencao'); return; }
    const grupos = [['chapas', 'Chapas'], ['barras', 'Barras e terças'], ['tirantes', 'Tirantes e barras redondas'], ['telhas', 'Telhas'], ['conjuntos', 'Conjuntos (tesouras, vigas, pilares)'], ['localizacao', 'Planta de localização (marcas no lugar de montagem)']];
    const caixas = {};
    const grade = el('div', { class: 'campos' });
    for (const [k, r] of grupos) { caixas[k] = el('input', { type: 'checkbox', checked: 'checked' }); grade.append(el('label', { texto: r }), caixas[k]); }
    const regra = el('input', { type: 'checkbox', checked: 'checked' });
    const rotular = el('input', { type: 'checkbox', checked: 'checked' });
    const converter = el('input', { type: 'checkbox', checked: 'checked' });
    const substituir = el('input', { type: 'checkbox', checked: 'checked' });
    grade.append(el('label', { texto: 'Furação das terças no padrão da fábrica', title: 'Terça com menos de 200 mm: furos a 50 mm na vertical e 60 na horizontal; com 200 mm ou mais: 100 × 60. Vale para os suportes com a mesma furação.' }), regra,
                 el('label', { texto: 'Rotular posições nos conjuntos' }), rotular,
                 el('label', { texto: 'Substituir os desenhos de detalhamento anteriores' }), substituir);
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: 'Cada posição (marca de peça do IFC) vira uma célula com título "P12 – 112x", perfil ou chapa, contorno, furos e cotas; as peças iguais são contadas, não repetidas. Cada conjunto (marca de montagem) vira uma elevação com a cadeia de cotas dos nós e a lista de perfis. Sai também o romaneio em detalhamento/romaneio.csv.' }),
      grade);
    if (await this.dialogo({ titulo: 'Detalhar peças e conjuntos', corpo, ok: 'Detalhar e abrir' }) !== 'ok') return;
    const escolhidos = grupos.map(([k]) => k).filter(k => caixas[k].checked);
    if (!escolhidos.length) return;
    this.dica('Detalhando as peças do projeto…');
    this.aviso('Detalhando: analisando cada posição e conjunto do modelo. Pode levar alguns segundos.', 'info', 8000);
    try {
      await this._gravarAntesDeGerar();
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ grupos: escolhidos, regra_tercas: regra.checked, rotular: rotular.checked, substituir: substituir.checked, converter: converter.checked }),
      });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      const tercas = Object.keys(j.regra_tercas || {}).length;
      this.aviso(`Detalhamento: ${j.pecas} peças em ${j.posicoes} posições e ${j.conjuntos} conjuntos, ${j.peso_total} kg. ${j.desenhos.length} desenho(s) gerado(s)` +
                 (tercas ? `; furação de fábrica aplicada em ${tercas} posições` : '') + `. Lista de materiais em Desenho 2D → Lista de materiais.` +
                 (j.avisos && j.avisos.length ? ` ${j.avisos.length} aviso(s) no relatório.` : ''), 'info', 15000);
      this.dica('Detalhamento pronto.');
      if (j.desenhos.length) this._abrirCAD(j.desenhos[0].nome);
    } catch (e) { this.aviso(`Não foi possível detalhar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** Vistas ortográficas só das peças selecionadas (ou do modelo inteiro), num desenho. */
  async dialogoVistasDaSelecao() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para gerar desenhos 2D.', 'atencao'); return; }
    const ids = [...this.selecao.ids];
    const nome = el('input', { type: 'text', value: ids.length ? 'Detalhe' : 'Vistas gerais' });
    const caixas = {};
    const grade = el('div', { class: 'campos' }, el('label', { texto: 'Nome do desenho' }), nome);
    for (const [k, r] of [['frente', 'Frente'], ['topo', 'Planta (topo)'], ['esquerda', 'Lateral esquerda'], ['direita', 'Lateral direita'], ['tras', 'Trás']]) {
      caixas[k] = el('input', { type: 'checkbox', checked: (k === 'frente' || k === 'topo' || k === 'esquerda') ? 'checked' : undefined });
      grade.append(el('label', { texto: r }), caixas[k]);
    }
    const substituir = el('input', { type: 'checkbox' });
    grade.append(el('label', { texto: 'Substituir desenho existente com este nome', title: 'Desmarcado, as vistas são acrescentadas ao lado do que o desenho já tem' }), substituir);
    const existe = el('p', { class: 'explica aviso-existe', texto: '' });
    // desenho com este nome já existe? então substituir é o padrão, senão as vistas
    // se acumulam ao lado das anteriores a cada clique
    const existentes = new Map();
    fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`).then(r => r.json()).then(lista => {
      if (Array.isArray(lista)) for (const d of lista) existentes.set(d.nome, d);
      conferir();
    }).catch(() => {});
    const conferir = () => {
      const d = existentes.get(slugDesenho(nome.value));
      substituir.checked = !!d;
      existe.textContent = d ? `Já existe "${d.titulo || d.nome}" com ${(d.vistas || []).length} vista(s) e ${(d.entidades || 0).toLocaleString('pt-BR')} objetos: será substituído (o anterior vai para a lixeira). Desmarque para acrescentar ao lado.` : '';
    };
    nome.addEventListener('input', conferir);
    const corpo = el('div', {}, el('p', { class: 'explica', texto: ids.length
      ? `${ids.length} peça(s) selecionada(s): as vistas saem só delas, lado a lado num desenho novo.`
      : 'Nada selecionado: as vistas saem do modelo inteiro (camadas ocultas ficam de fora). Fica pesado: para detalhar, selecione antes a tesoura ou o pórtico.' }), grade, existe);
    if (await this.dialogo({ titulo: 'Vistas 2D', corpo, ok: 'Gerar e abrir' }) !== 'ok') return;
    const escolhidas = Object.entries(caixas).filter(([, c]) => c.checked).map(([k]) => k);
    if (!escolhidas.length) return;
    this.dica('Gerando as vistas…');
    try {
      await this._gravarAntesDeGerar();
      const desenho = nome.value.trim() || 'Vistas';
      // todas num pedido só: o desenho é gravado uma vez, no fim
      const j = await this._pedirVista({ vistas: escolhidas.map(k => ({ padrao: k, entidades: ids.length ? ids : null, rotular: false })), desenho, substituir: substituir.checked });
      const n = (j.vistas || []).reduce((s, v) => s + (v.pecas_projetadas || 0), 0);
      this.aviso(`${escolhidas.length} vista(s) gerada(s), ${n} peça(s) projetada(s). Abrindo o CAD…`, 'info', 6000);
      this._abrirCAD(j.nome || desenho);
    } catch (e) { this.aviso(`Não foi possível gerar as vistas: ${e.message}`, 'erro', 0); }
  }

  // ------------------------------------------------------------ interface

  _ligarMenus() {
    const acoes = {
      novo: () => this.novo(),
      abrir: () => this.dialogoAbrir(),
      salvar: () => this.salvar(),
      'salvar-como': () => this.salvarComo(),
      exemplo: () => this.carregarExemplo(),
      'do-galpao': () => this.dialogoGalpao(),
      'importar-ifc': () => { this._modoArquivo = 'importar'; this.el.arquivoIfc.click(); },
      'inspecionar-ifc': () => { this._modoArquivo = 'inspecionar'; this.el.arquivoIfc.click(); },
      'detalhar-ifc': () => { this._modoArquivo = 'detalhar'; this.el.arquivoIfc.click(); },
      'exportar-ifc': () => this.exportarIFC(),
      desfazer: () => this.desfazer(),
      refazer: () => this.refazer(),
      'selecionar-tudo': () => this.selecao.tudo(),
      'inverter-selecao': () => this.selecao.inverter(),
      apagar: () => this.apagarSelecao(),
      'zoom-extensao': () => this.camera.zoomExtensao(),
      'zoom-selecao': () => this.camera.zoomSelecao([...this.selecao.ids]),
      'mapa-esforcos': () => this.alternarAnalise(),
      'desenho-corte': () => this.gerarDesenhoDoCorte(),
      'desenho-selecao': () => this.dialogoVistasDaSelecao(),
      'detalhar-pecas': () => this.dialogoDetalharPecas(),
      'abrir-cad': () => this._abrirCAD(),
      'materiais': () => this._abrirMateriais(),
      'excluir-desenhos': () => this._excluirDesenhos(),
    };
    document.addEventListener('click', (ev) => {
      const botaoMenu = ev.target.closest('.menu-botao');
      if (botaoMenu) {
        const menu = botaoMenu.parentElement;
        const aberto = menu.classList.contains('aberto');
        this._fecharMenus();
        if (!aberto) { menu.classList.add('aberto'); if (menu.dataset.menu === 'desenho2d') this._listarDesenhosNoMenu(); }
        return;
      }
      const excluir = ev.target.closest('[data-excluir]');
      if (excluir) { ev.stopPropagation(); this._fecharMenus(); this._excluirUmDesenho(excluir.dataset.excluir, excluir.dataset.titulo); return; }
      const desenho = ev.target.closest('[data-desenho]');
      if (desenho) { this._fecharMenus(); this._abrirCAD(desenho.dataset.desenho); return; }
      const acao = ev.target.closest('[data-acao]');
      if (acao && acoes[acao.dataset.acao]) {
        this._fecharMenus();
        acoes[acao.dataset.acao]();
        return;
      }
      const vista = ev.target.closest('[data-vista]');
      if (vista) { this._fecharMenus(); this.camera.vista(vista.dataset.vista); return; }
      if (!ev.target.closest('.menu')) this._fecharMenus();
    });
    // Com um menu aberto, passar o mouse sobre outro troca, como numa barra de menus.
    for (const m of document.querySelectorAll('.menu')) {
      m.addEventListener('mouseenter', () => {
        if (document.querySelector('.menu.aberto') && !m.classList.contains('aberto')) {
          this._fecharMenus();
          m.classList.add('aberto');
          if (m.dataset.menu === 'desenho2d') this._listarDesenhosNoMenu();
        }
      });
    }

    this.el.arquivoIfc.addEventListener('change', () => {
      const f = this.el.arquivoIfc.files && this.el.arquivoIfc.files[0];
      this.el.arquivoIfc.value = '';
      this._arquivoEscolhido(f);
    });
    this.el.nome.addEventListener('change', () => {
      this.documento.nome = this.el.nome.value.trim() || 'Modelo';
    });
    this._ligarBusca();
    this.el.projecao.addEventListener('click', () => {
      this.camera.alternarProjecao();
      this.el.projecao.textContent = this.camera.projecao === 'perspectiva' ? 'Perspectiva' : 'Ortográfica';
    });
    this.el.calcular.addEventListener('click', () => this.alternarAnalise());
    this.el.tema.addEventListener('click', () => this.alternarTema());
  }

  _fecharMenus() {
    for (const m of document.querySelectorAll('.menu.aberto')) m.classList.remove('aberto');
  }

  _atualizarMenuEditar() {
    const d = $('[data-acao="desfazer"]'), r = $('[data-acao="refazer"]');
    d.disabled = !this.pilha.podeDesfazer;
    r.disabled = !this.pilha.podeRefazer;
    d.textContent = this.pilha.podeDesfazer ? `Desfazer: ${this.pilha.rotuloDesfazer}` : 'Desfazer';
    r.textContent = this.pilha.podeRefazer ? `Refazer: ${this.pilha.rotuloRefazer}` : 'Refazer';
    d.append(el('kbd', { texto: 'Ctrl+Z' }));
    r.append(el('kbd', { texto: 'Ctrl+Y' }));
    const h = this.el.historico;
    h.replaceChildren();
    const itens = this.pilha.historico(12);
    if (!itens.length) h.append(el('div', { class: 'vazio', style: 'padding:3px 9px', texto: 'nada ainda' }));
    for (const it of itens) {
      h.append(el('button', {
        type: 'button', title: `Desfazer até aqui (${it.passos} passo(s))`,
        onclick: () => { this._fecharMenus(); this.pilha.desfazerAte(it.passos); },
      }, it.rotulo));
    }
  }

  _montarModos() {
    const icones = {
      sombreado: '<path d="M8 2l5.5 3v6L8 14l-5.5-3V5z" fill="currentColor" opacity=".75"/>',
      sombreado_arestas: '<path d="M8 2l5.5 3v6L8 14l-5.5-3V5z" fill="currentColor" opacity=".45" stroke="currentColor" stroke-width="1.2"/><path d="M2.5 5L8 8l5.5-3M8 8v6" fill="none" stroke="currentColor" stroke-width="1.2"/>',
      arestas: '<path d="M8 2l5.5 3v6L8 14l-5.5-3V5zM2.5 5L8 8l5.5-3M8 8v6" fill="none" stroke="currentColor" stroke-width="1.2"/>',
      raiox: '<path d="M8 2l5.5 3v6L8 14l-5.5-3V5z" fill="currentColor" opacity=".18" stroke="currentColor" stroke-width="1.2"/><path d="M2.5 5L8 8l5.5-3M8 8v6" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="1.5 1.5"/>',
    };
    for (const [modo, rotulo] of MODOS) {
      const b = el('button', {
        type: 'button', title: rotulo, 'aria-label': rotulo, dados: { modo },
        'aria-pressed': String(modo === this.cena.modo),
        onclick: () => this.definirModo(modo),
      });
      b.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16">${icones[modo]}</svg>`;
      this.el.modos.append(b);
    }
  }

  _montarVistasRapidas() {
    const itens = [['topo', 'Topo'], ['frente', 'Frente'], ['esquerda', 'Esq.'], ['direita', 'Dir.'],
                   ['tras', 'Trás'], ['inferior', 'Inf.'], ['isometrica', 'Iso'], ['extensao', 'Ext.']];
    for (const [v, rot] of itens) {
      const tecla = TECLAS_VISTA.indexOf(v) + 1;
      this.el.vistas.append(el('button', {
        type: 'button', texto: rot,
        title: v === 'extensao' ? 'Zoom na extensão (Z)' : `${VISTAS[v].rotulo} (${tecla})`,
        onclick: () => (v === 'extensao' ? this.camera.zoomExtensao() : this.camera.vista(v)),
      }));
    }
  }

  _ligarRedimensionamento() {
    const ajustar = () => {
      const w = this.el.palco.clientWidth, h = this.el.palco.clientHeight;
      if (!w || !h) return;
      this.cena.redimensionar(w, h);
      this.camera.redimensionar(w, h);
      this._sujo = true;
    };
    new ResizeObserver(ajustar).observe(this.el.palco);
    ajustar();
  }

  _laco() {
    const quadro = () => {
      requestAnimationFrame(quadro);
      const mexeu = this.camera.atualizar();        // amortecimento da órbita
      if (mexeu || this._sujo) {
        this._sujo = false;
        this.cena.desenhar(this.camera.ativa);
        this._atualizarRotulos();
      }
    };
    requestAnimationFrame(quadro);
  }

  /** Reposiciona os textos das cotas depois de cada quadro. Reaproveita os spans. */
  _atualizarRotulos() {
    const vistos = new Set();
    const w = this.camera.largura, h = this.camera.altura;
    // o texto some junto com a cota quando ela fica do lado cortado pela seção
    const corte = this.cena.planoCorte;
    const cortado = (p) => !!corte && (
      (p[0] - corte.origem[0]) * corte.normal[0] + (p[1] - corte.origem[1]) * corte.normal[1]
      + (p[2] - corte.origem[2]) * corte.normal[2] < 0);
    for (const [id, r] of this.cena.rotulos) {
      const ent = this.documento.get(id);
      if (!ent || !this.documento.aparece(ent) || cortado(r.ponto)) continue;
      const t = this.camera.paraTela(r.ponto);
      let span = this._spansRotulo.get(id);
      if (!span) {
        span = el('span', { class: 'rotulo-cota' });
        this.el.rotulos.append(span);
        this._spansRotulo.set(id, span);
      }
      if (span.textContent !== r.texto) span.textContent = r.texto;
      span.hidden = t[2] > 1 || t[0] < -80 || t[1] < -40 || t[0] > w + 80 || t[1] > h + 40;
      span.style.transform = `translate(${t[0].toFixed(1)}px, ${t[1].toFixed(1)}px) translate(-50%, -125%)`;
      span.dataset.selecionado = this.selecao.tem(id) ? '1' : '';
      vistos.add(id);
    }
    for (const [id, span] of this._spansRotulo) {
      if (!vistos.has(id)) { span.remove(); this._spansRotulo.delete(id); }
    }
  }

  // ------------------------------------------------------------------ tema

  _aplicarTemaInicial() {
    let tema = this.parametros.get('tema');
    if (!tema) { try { tema = localStorage.getItem(CHAVE_TEMA); } catch { tema = null; } }
    if (tema === 'claro' || tema === 'escuro') document.documentElement.setAttribute('data-tema', tema);
    this._consulta = matchMedia('(prefers-color-scheme: dark)');
    this._consulta.addEventListener('change', () => {
      if (!document.documentElement.hasAttribute('data-tema')) this.cena.aplicarTema(this.escuro);
    });
  }

  get escuro() {
    const t = document.documentElement.getAttribute('data-tema');
    return t ? t === 'escuro' : !!(this._consulta && this._consulta.matches);
  }

  alternarTema() {
    const novo = this.escuro ? 'claro' : 'escuro';
    document.documentElement.setAttribute('data-tema', novo);
    try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* janela privativa */ }
    this.cena.aplicarTema(this.escuro);
  }

  // --------------------------------------------------------------- avisos

  aviso(conteudo, tipo = 'info', duracao = undefined) {
    if (tipo === 'erro') {
      (this._registroErros || (this._registroErros = [])).push(
        conteudo instanceof Node ? conteudo.textContent : String(conteudo));
    }
    const caixa = el('div', { class: 'aviso', dados: { tipo }, role: tipo === 'erro' ? 'alert' : 'status' });
    caixa.append(conteudo instanceof Node ? conteudo : el('span', { texto: conteudo }));
    caixa.append(el('button', { type: 'button', 'aria-label': 'Fechar', texto: '×',
                                onclick: () => caixa.remove() }));
    this.el.avisos.append(caixa);
    while (this.el.avisos.children.length > 5) this.el.avisos.firstElementChild.remove();
    const t = duracao !== undefined ? duracao : tipo === 'erro' ? 16000 : tipo === 'atencao' ? 9000 : 5000;
    if (t > 0) setTimeout(() => caixa.remove(), t);
    return caixa;
  }

  /** Diálogo modal; devolve 'ok' ou 'cancelar'. `ok: null` esconde o botão. */
  dialogo({ titulo, corpo, ok = 'Confirmar', cancelar = 'Cancelar' }) {
    const d = this.el.dialogo;
    this.el.dialogoTitulo.textContent = titulo;
    this.el.dialogoCorpo.replaceChildren();
    if (corpo) this.el.dialogoCorpo.append(corpo);
    this.el.dialogoOk.hidden = !ok;
    if (ok) this.el.dialogoOk.textContent = ok;
    this.el.dialogoCancelar.textContent = ok ? cancelar : 'Fechar';
    return new Promise((resolver) => {
      const fim = () => {
        d.removeEventListener('close', fim);
        resolver(d.returnValue === 'ok' ? 'ok' : 'cancelar');
      };
      d.addEventListener('close', fim);
      d.returnValue = '';
      d.showModal();
      const primeiro = this.el.dialogoCorpo.querySelector('input, select, button');
      if (primeiro) primeiro.focus();
    });
  }

  // ================================================================ painéis

  _ligarPaineis() {
    for (const s of document.querySelectorAll('.painel')) {
      $('.cabecalho', s).addEventListener('click', () => s.toggleAttribute('data-fechado'));
    }
    // Não redesenha o painel enquanto o usuário digita nele; espera sair do campo.
    this.el.props.addEventListener('focusout', () => {
      setTimeout(() => { if (this._propsPendente) this._agendarPaineis('props'); }, 0);
    });
  }

  _agendarPaineis(...quais) {
    for (const q of quais) this._paineisPendentes.add(q);
    if (this._timerPaineis) return;
    this._timerPaineis = setTimeout(() => {
      this._timerPaineis = null;
      const p = this._paineisPendentes;
      this._paineisPendentes = new Set();
      try {
        if (p.has('props')) this._painelPropriedades();
        if (p.has('camadas')) this._painelCamadas();
        if (p.has('materiais')) this._painelMateriais();
        if (p.has('arvore')) this._painelArvore();
        if (p.has('analise')) this._painelAnalise();
      } catch (e) {
        console.error('painel falhou:', e);
      }
      this._atualizarServidor();
    }, 40);
  }

  _atualizarServidor() {
    const c = this.cena;
    this.el.servidor.textContent = c.usarServidor ? 'malhas: servidor' : 'malhas: locais';
    this.el.servidor.title = c.usarServidor
      ? 'As seções de barras e chapas vêm de nucleo3d/geometria.py.'
      : `Seções montadas no navegador. Motivo: ${c.avisoServidor || '—'}`;
  }

  _atualizarCarimbo() {
    const n = this.documento.tamanho;
    const s = this.selecao.tamanho;
    this.el.contagem.textContent = `${numero(n)} objeto${n === 1 ? '' : 's'}` +
      (s ? ` · ${numero(s)} selecionado${s === 1 ? '' : 's'}` : '');
    if (!n) { this.el.extensao.textContent = '—'; return; }
    const [a, b] = this.documento.caixa();
    this.el.extensao.textContent =
      `${metros(b[0] - a[0])} × ${metros(b[1] - a[1])} × ${metros(b[2] - a[2])} m`;
  }

  // ---------------------------------------------------------- propriedades

  _painelPropriedades() {
    const raiz = this.el.props;
    const foco = document.activeElement;
    if (foco && raiz.contains(foco) && (foco.tagName === 'INPUT' || foco.tagName === 'SELECT') &&
        foco.type !== 'checkbox') {
      this._propsPendente = true;
      return;
    }
    this._propsPendente = false;
    raiz.replaceChildren();
    const ents = this.selecao.entidades;
    if (!ents.length) { this._propsPadroes(raiz); return; }

    const ids = ents.map(e => e.id);
    const um = ents.length === 1 ? ents[0] : null;
    const tipos = contarPor(ents, e => e.tipo);
    const nomeTipo = { barra: 'Barra', chapa: 'Chapa', solido: 'Sólido', grupo: 'Grupo' };
    const titulo = um ? (um.nome || nomeTipo[um.tipo] || um.tipo)
                      : `${ents.length} objetos`;
    const sub = um ? `${nomeTipo[um.tipo] || um.tipo} · ${um.id}`
                   : [...tipos].map(([t, n]) => `${n} ${nomeTipo[t] || t}`).join(' · ');
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: titulo }),
                   el('span', { texto: sub })));

    const comum = (campo) => {
      const v = ents[0][campo];
      return ents.every(e => JSON.stringify(e[campo]) === JSON.stringify(v)) ? v : undefined;
    };
    const aplicar = (campos, rotulo) => this.alterarEntidades(ids, campos, rotulo);

    // --- gerais ---
    const g = el('div', { class: 'campos' });
    if (um) {
      g.append(el('label', { texto: 'Nome' }), this._texto(um.nome || '', v =>
        aplicar({ nome: v }, 'Renomear')));
    }
    g.append(el('label', { texto: 'Camada' }),
      this._lista([...this.documento.camadas.keys()], comum('camada'),
                  v => aplicar({ camada: v }, `Mover para a camada ${v}`)));
    g.append(el('label', { texto: 'Material' }),
      this._lista([['', 'pela camada'], ...[...this.documento.materiais.keys()].map(m => [m, m])],
                  comum('material'), v => aplicar({ material: v }, v ? `Aplicar ${v}` : 'Material pela camada')));
    raiz.append(g);

    const todas = (t) => ents.every(e => e.tipo === t);

    if (todas('barra')) {
      const gb = this._grupo(raiz, 'Barra');
      gb.append(el('label', { texto: 'Perfil' }),
        this._buscaPerfil(comum('perfil'), (nome) => aplicar({ perfil: nome }, `Trocar perfil para ${nome}`)));
      gb.append(el('label', { texto: 'Aço' }),
        this._lista(uniao(this.catalogo.acos, ents.map(e => e.aco)), comum('aco'),
                    v => aplicar({ aco: v }, `Aço ${v}`)));
      gb.append(el('label', { texto: 'Papel' }),
        this._lista(uniao(PAPEIS, ents.map(e => e.papel)), comum('papel'),
                    v => aplicar({ papel: v }, `Papel ${v}`)));
      gb.append(el('label', { texto: 'Rotação (°)' }),
        this._num(comum('rotacao'), v => aplicar({ rotacao: v }, 'Girar seção'), { passo: 15 }));
      const massaTotal = ents.reduce((s, e) => s + this._massaBarra(e), 0);
      if (um) {
        gb.append(el('label', { texto: 'Comprimento' }),
          this._num(Math.round(comprimentoDaBarra(um) * 10) / 10, v => {
            if (!(v > 0)) { this.aviso('O comprimento precisa ser positivo.', 'atencao'); return; }
            const fim = somar(um.inicio, escalar(direcaoDaBarra(um), v));
            aplicar({ fim }, 'Alterar comprimento');
          }, { unidade: 'mm' }));
        gb.append(el('label', { texto: 'Recorte início' }),
          this._num(um.recorte_inicio || 0, v => aplicar({ recorte_inicio: v }, 'Recorte no início')));
        gb.append(el('label', { texto: 'Recorte fim' }),
          this._num(um.recorte_fim || 0, v => aplicar({ recorte_fim: v }, 'Recorte no fim')));
        gb.append(el('label', { texto: 'Início' }), el('span', { class: 'valor', texto: ponto3(um.inicio) }));
        gb.append(el('label', { texto: 'Fim' }), el('span', { class: 'valor', texto: ponto3(um.fim) }));
      } else {
        const total = ents.reduce((s, e) => s + comprimentoDaBarra(e), 0);
        gb.append(el('label', { texto: 'Comprimento' }), el('span', { class: 'valor', texto: `${metros(total)} m no total` }));
      }
      gb.append(el('label', { texto: 'Massa' }),
        el('span', { class: 'valor', texto: massaTotal ? `${numero(massaTotal, 1)} kg` : '—' }));
    }

    if (todas('chapa')) {
      const gc = this._grupo(raiz, 'Chapa');
      gc.append(el('label', { texto: 'Espessura' }),
        this._num(comum('espessura'), v => {
          if (!(v > 0)) { this.aviso('A espessura precisa ser positiva.', 'atencao'); return; }
          aplicar({ espessura: v }, `Espessura ${numero(v, 1)} mm`);
        }, { unidade: 'mm' }));
      gc.append(el('label', { texto: 'Aço' }),
        this._lista(uniao(this.catalogo.acos, ents.map(e => e.aco)), comum('aco'),
                    v => aplicar({ aco: v }, `Aço ${v}`)));
      gc.append(el('label', { texto: 'Centrada' }),
        this._lista([['sim', 'sim — cresce para os dois lados'], ['nao', 'não — cresce para a normal']],
                    comum('centrada') === undefined ? undefined : (comum('centrada') === false ? 'nao' : 'sim'),
                    v => aplicar({ centrada: v === 'sim' }, 'Posição da espessura')));
      const massa = ents.reduce((s, e) => s + areaDaChapa(e) * (e.espessura || 0) * 7.85e-6, 0);
      if (um) {
        gc.append(el('label', { texto: 'Área' }), el('span', { class: 'valor', texto: `${numero(areaDaChapa(um) / 1e6, 4)} m²` }));
        gc.append(el('label', { texto: 'Furos' }), el('span', { class: 'valor', texto: String((um.furos || []).length) }));
        gc.append(el('label', { texto: 'Origem' }), el('span', { class: 'valor', texto: ponto3(um.origem) }));
      }
      gc.append(el('label', { texto: 'Massa' }), el('span', { class: 'valor', texto: `${numero(massa, 1)} kg` }));
    }

    if (um && um.tipo === 'solido') {
      // peça importada de IFC: marcas, dimensões pelos eixos principais e massa
      const a = um.atributos || {}, marcas = a.marcas || {};
      if (marcas.posicao || marcas.conjunto || marcas.perfil || a.tipo_ifc) {
        const gi = this._grupo(raiz, 'Peça (IFC)');
        const linha = (rotulo, valor, acao) => {
          const v = el('span', { class: 'valor' + (acao ? ' clicavel' : ''), texto: String(valor), title: acao ? 'Clique: selecionar todas com o mesmo valor' : undefined });
          if (acao) v.addEventListener('click', acao);
          gi.append(el('label', { texto: rotulo }), v);
        };
        if (marcas.posicao) {
          const iguais = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao === marcas.posicao).map(e => e.id);
          linha('Posição', `${marcas.posicao}  (${iguais.length} iguais)`, () => this.selecao.definir(iguais));
        }
        if (marcas.conjunto) {
          const doConj = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.conjunto === marcas.conjunto).map(e => e.id);
          linha('Conjunto', `${marcas.conjunto}  (${doConj.length} peças)`, () => this.selecao.definir(doConj));
        }
        // nome de produção dado pelo detalhamento (S.T.1, T.C.2-A…), quando já existe
        if (marcas.nome) {
          const mesmos = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.nome === marcas.nome).map(e => e.id);
          linha('Nome', `${marcas.nome}  (${mesmos.length} peças)`, () => this.selecao.definir(mesmos));
        }
        if (marcas.nome_conjunto && marcas.nome_conjunto !== marcas.nome) linha('Nome do conjunto', marcas.nome_conjunto);
        if (marcas.perfil) linha('Perfil', marcas.perfil);
        if (a.tipo_ifc) linha('Tipo IFC', a.tipo_ifc);
        const dims = dimensoesPrincipais(um);
        if (dims) {
          linha('Comprimento', `${numero(dims[0], 0)} mm`);
          linha('Seção (envolvente)', `${numero(dims[1], 0)} × ${numero(dims[2], 1)} mm`);
        }
        linha('Massa', `${numero(volumeDe(um) * 7.85e-6, 2)} kg`);
      }
      const gs = this._grupo(raiz, 'Sólido');
      gs.append(el('label', { texto: 'Vértices' }), el('span', { class: 'valor', texto: String((um.vertices || []).length) }));
      gs.append(el('label', { texto: 'Faces' }), el('span', { class: 'valor', texto: String((um.faces || []).length) }));
      gs.append(el('label', { texto: 'Volume' }), el('span', { class: 'valor', texto: `${numero(volumeDe(um) / 1e9, 4)} m³` }));
      if (um.origem_ifc) gs.append(el('label', { texto: 'GlobalId' }), el('span', { class: 'valor', texto: um.origem_ifc }));
    } else if (ents.length > 1 && ents.every(e => e.tipo === 'solido')) {
      const gs = this._grupo(raiz, 'Sólidos');
      const massa = ents.reduce((s, e) => s + volumeDe(e) * 7.85e-6, 0);
      gs.append(el('label', { texto: 'Massa' }), el('span', { class: 'valor', texto: `${numero(massa, 1)} kg no total` }));
      const pos = new Set(ents.map(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao).filter(Boolean));
      if (pos.size) gs.append(el('label', { texto: 'Posições' }), el('span', { class: 'valor', texto: [...pos].slice(0, 12).join(', ') + (pos.size > 12 ? ' …' : '') }));
    }

    const acoes = el('div', { class: 'acoes-painel' });
    const botao = (texto, fn, titulo) => acoes.append(el('button', { type: 'button', texto, title: titulo, onclick: fn }));
    botao('Zoom', () => this.camera.zoomSelecao(ids), 'Enquadrar a seleção');
    if (um) botao('Semelhantes', () => this.selecao.semelhantes(um.id), 'Mesmo tipo e mesmo perfil');
    botao('Mesma camada', () => this.selecao.porCamada(ents[0].camada));
    if (comum('perfil')) botao('Mesmo perfil', () => this.selecao.porPerfil(comum('perfil')));
    botao('Apagar', () => this.apagarSelecao(), 'Del');
    raiz.append(acoes);
  }

  /** Sem seleção: os padrões que as ferramentas de desenho usam, e o resumo do modelo. */
  _propsPadroes(raiz) {
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Nada selecionado' }),
                   el('span', { texto: 'padrões de desenho' })));
    const g = el('div', { class: 'campos' });
    g.append(el('label', { texto: 'Perfil' }),
      this._buscaPerfil(this.perfilAtivo, n => { this.definirPerfilAtivo(n); this.dica(`Perfil ativo: ${n}`); }));
    g.append(el('label', { texto: 'Aço' }),
      this._lista(uniao(this.catalogo.acos, [this.acoAtivo]), this.acoAtivo, v => { this.acoAtivo = v; }));
    g.append(el('label', { texto: 'Papel' }),
      this._lista(PAPEIS, this.papelAtivo, v => { this.papelAtivo = v; }));
    g.append(el('label', { texto: 'Camada' }),
      this._lista([...this.documento.camadas.keys()], this.camadaAtiva,
                  v => { this.camadaAtiva = v; this._agendarPaineis('camadas'); }));
    raiz.append(g);

    const est = this.documento.estatisticas();
    const massa = this.documento.barras.reduce((s, e) => s + this._massaBarra(e), 0) +
      this.documento.chapas.reduce((s, e) => s + areaDaChapa(e) * (e.espessura || 0) * 7.85e-6, 0);
    const gm = this._grupo(raiz, 'Modelo');
    const linha = (r, v) => gm.append(el('label', { texto: r }), el('span', { class: 'valor', texto: v }));
    linha('Objetos', numero(est.entidades));
    linha('Barras', numero(est.barras));
    linha('Chapas', numero(est.chapas));
    linha('Sólidos', numero(est.solidos));
    linha('Aço estimado', massa ? `${numero(massa / 1000, 2)} t` : '—');
  }

  _massaBarra(b) {
    const p = this.cena.perfil(b.perfil);
    return p && p.massa ? p.massa * comprimentoDaBarra(b) / 1000 : 0;
  }

  _grupo(raiz, titulo) {
    const g = el('div', { class: 'campos' });
    raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: titulo }), g));
    return g;
  }

  _texto(valor, aoMudar) {
    const i = el('input', { type: 'text', value: valor, spellcheck: 'false' });
    i.addEventListener('change', () => aoMudar(i.value.trim()));
    i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') i.blur(); });
    return i;
  }

  _num(valor, aoMudar, { passo = 'any', unidade = '' } = {}) {
    const i = el('input', { type: 'number', step: passo, title: unidade });
    if (valor === undefined) i.placeholder = 'vários';
    else i.value = Math.round(Number(valor) * 1000) / 1000;
    i.addEventListener('change', () => {
      const v = parseFloat(String(i.value).replace(',', '.'));
      if (isFinite(v)) aoMudar(v);
    });
    i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') i.blur(); });
    return i;
  }

  /** Select; `opcoes` é lista de valores ou de pares [valor, rótulo]. */
  _lista(opcoes, valor, aoMudar) {
    const s = el('select');
    if (valor === undefined) s.append(el('option', { value: '', texto: '— vários —', selected: true, disabled: true }));
    for (const o of opcoes) {
      const [v, r] = Array.isArray(o) ? o : [o, o];
      s.append(el('option', { value: v, texto: r, selected: valor !== undefined && v === (valor ?? '') }));
    }
    s.addEventListener('change', () => aoMudar(s.value));
    return s;
  }

  /** Campo de perfil com busca no catálogo. */
  _buscaPerfil(valor, aoEscolher) {
    const caixa = el('div', { class: 'busca-perfil' });
    const entrada = el('input', { type: 'search', value: valor ?? '', spellcheck: 'false',
                                  placeholder: valor === undefined ? 'vários — buscar…' : 'buscar perfil…' });
    const lista = el('div', { class: 'lista-perfis', role: 'listbox' });
    let achados = [], marcado = 0;
    const desenhar = () => {
      lista.replaceChildren();
      achados.forEach((p, i) => {
        const dim = p.tipo === 'L' ? `${numero(p.bf, 1)}×${numero(p.tw, 2)}`
                  : p.tipo === 'tubo' ? `Ø${numero(p.d, 1)}×${numero(p.tw, 2)}`
                  : `${numero(p.d, 0)}×${numero(p.bf, 0)}`;
        lista.append(el('button', {
          type: 'button', class: i === marcado ? 'ativo' : '',
          onmousedown: (ev) => { ev.preventDefault(); escolher(p.nome); },
        }, el('span', { texto: p.nome }), el('span', { class: 'dim', texto: `${dim} · ${numero(p.massa, 1)} kg/m` })));
      });
    };
    const filtrar = () => {
      const q = normalizarBusca(entrada.value);
      const todos = this.catalogo.perfis || [];
      achados = (q ? todos.filter(p => normalizarBusca(p.nome).includes(q)) : todos).slice(0, 40);
      marcado = 0;
      desenhar();
    };
    const escolher = (nome) => {
      entrada.value = nome;
      lista.replaceChildren();
      entrada.blur();
      aoEscolher(nome);
    };
    entrada.addEventListener('focus', () => { entrada.select(); filtrar(); });
    entrada.addEventListener('input', filtrar);
    entrada.addEventListener('blur', () => setTimeout(() => {
      lista.replaceChildren();
      if (valor !== undefined && !achados.some(p => p.nome === entrada.value)) entrada.value = valor;
    }, 120));
    entrada.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown') { marcado = Math.min(achados.length - 1, marcado + 1); desenhar(); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp') { marcado = Math.max(0, marcado - 1); desenhar(); ev.preventDefault(); }
      else if (ev.key === 'Enter') { ev.preventDefault(); if (achados[marcado]) escolher(achados[marcado].nome); }
      else if (ev.key === 'Escape') { lista.replaceChildren(); entrada.blur(); }
    });
    caixa.append(entrada, lista);
    return caixa;
  }

  // --------------------------------------------------------------- camadas

  _painelCamadas() {
    const raiz = this.el.camadas;
    raiz.replaceChildren();
    raiz.append(this._seletorCorPor());
    const cont = this.documento.contagemPorCamada();
    const lista = el('div', { class: 'lista-linhas' });
    const olho = (vis) => vis
      ? '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3" opacity=".45"/><path d="M3 13L13 3" stroke="currentColor" stroke-width="1.3"/></svg>';
    const cadeado = (b) => b
      ? '<svg width="13" height="13" viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" fill="currentColor"/><path d="M5 7V5a3 3 0 0 1 6 0v2" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>'
      : '<svg width="13" height="13" viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/><path d="M5 7V5a3 3 0 0 1 5.6-1.5" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/></svg>';
    for (const [nome, c] of this.documento.camadas) {
      const linha = el('div', { class: 'linha', title: 'Clique: camada ativa · duplo clique: selecionar o que está nela' });
      if (c.visivel === false) linha.dataset.oculta = '';
      if (nome === this.camadaAtiva) linha.dataset.ativa = '';
      const vis = el('button', { type: 'button', class: 'alternador', 'aria-pressed': String(c.visivel !== false),
        title: c.visivel === false ? 'Mostrar' : 'Ocultar',
        onclick: () => this.executar(new ComandoAparencia('camadas', nome, { visivel: c.visivel === false },
                                     `${c.visivel === false ? 'Mostrar' : 'Ocultar'} camada ${nome}`)) });
      vis.innerHTML = olho(c.visivel !== false);
      const cor = el('input', { type: 'color', value: corHex(c.cor), title: 'Cor da camada' });
      cor.addEventListener('change', () => this.executar(
        new ComandoAparencia('camadas', nome, { cor: cor.value }, `Cor da camada ${nome}`)));
      const rotulo = el('span', { class: 'nome', texto: nome });
      linha.addEventListener('click', (ev) => {
        if (ev.target.closest('button, input')) return;
        this.camadaAtiva = nome;
        this._agendarPaineis('camadas', 'props');
        this.dica(`Camada ativa: ${nome}`);
      });
      linha.addEventListener('dblclick', (ev) => {
        if (ev.target.closest('button, input')) return;
        this.selecao.porCamada(nome, ev.shiftKey);
      });
      const trava = el('button', { type: 'button', class: 'alternador', 'aria-pressed': String(!!c.bloqueada),
        title: c.bloqueada ? 'Desbloquear' : 'Bloquear',
        onclick: () => this.executar(new ComandoAparencia('camadas', nome, { bloqueada: !c.bloqueada },
                                     `${c.bloqueada ? 'Desbloquear' : 'Bloquear'} camada ${nome}`)) });
      trava.innerHTML = cadeado(!!c.bloqueada);
      linha.append(vis, cor, rotulo, el('span', { class: 'contagem', texto: numero(cont.get(nome) || 0) }), trava);
      lista.append(linha);
    }
    raiz.append(lista);
    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: '+ Nova camada', onclick: () => this._novaCamada() }));
    acoes.append(el('button', { type: 'button', texto: 'Mostrar todas', onclick: () => {
      for (const [nome, c] of this.documento.camadas) {
        if (c.visivel === false) this.executar(new ComandoAparencia('camadas', nome, { visivel: true }, 'Mostrar todas'));
      }
    } }));
    raiz.append(acoes);
  }

  // ------------------------------------------------------------ pesquisa de peças

  /**
   * Campo de pesquisa do topo: procura em nome, posição, conjunto, perfil, camada, tipo
   * IFC e GlobalId; várias palavras são "e". Os resultados saem agrupados por posição
   * (marca da peça) — ou por nome, quando não há marca — com a contagem e a cor do
   * grupo. Clique seleciona o grupo, duplo clique enquadra, Enter seleciona tudo.
   */
  _ligarBusca() {
    const campo = document.getElementById('busca-campo');
    const caixa = document.getElementById('busca-resultados');
    if (!campo || !caixa) return;
    let timer = null, ativo = -1, grupos = [];
    const fechar = () => { caixa.hidden = true; ativo = -1; };
    const render = () => {
      const termo = campo.value.trim();
      caixa.replaceChildren();
      if (!termo) { fechar(); return; }
      const r = this.pesquisarPecas(termo);
      grupos = r.grupos;
      caixa.hidden = false;
      const cabeca = el('div', { class: 'cabeca' },
        el('span', { texto: r.total ? `${numero(r.total)} peça(s) em ${numero(grupos.length)} grupo(s)` : 'Nada encontrado' }));
      if (r.total) {
        cabeca.append(el('button', { type: 'button', texto: 'Selecionar tudo', onclick: () => { this.selecao.definir(r.ids); this.camera.zoomSelecao(r.ids); fechar(); } }));
      }
      caixa.append(cabeca);
      if (!r.total) { caixa.append(el('div', { class: 'nada', texto: 'Tente parte do nome, a posição (P12), o conjunto (M2) ou o perfil.' })); return; }
      grupos.slice(0, 80).forEach((g, i) => {
        const item = el('div', { class: 'item', title: 'Clique: selecionar · duplo clique: enquadrar' },
          el('span', { class: 'amostra', style: `background:${g.cor}` }),
          el('span', { class: 'nome' }, g.chave, el('small', { texto: g.detalhe })),
          el('span', { class: 'contagem', texto: numero(g.ids.length) }));
        item.addEventListener('click', (ev) => { ev.shiftKey ? this.selecao.somar(g.ids) : this.selecao.definir(g.ids); ativo = i; realcar(); });
        item.addEventListener('dblclick', () => { this.selecao.definir(g.ids); this.camera.zoomSelecao(g.ids); });
        caixa.append(item);
      });
      if (grupos.length > 80) caixa.append(el('div', { class: 'nada', texto: `… e mais ${grupos.length - 80} grupo(s): refine a pesquisa.` }));
    };
    const realcar = () => { [...caixa.querySelectorAll('.item')].forEach((e, i) => e.classList.toggle('ativo', i === ativo)); };
    campo.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(render, 160); });
    campo.addEventListener('focus', () => { if (campo.value.trim()) render(); });
    campo.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') { campo.value = ''; fechar(); campo.blur(); return; }
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        ev.preventDefault();
        if (!grupos.length) return;
        ativo = (ativo + (ev.key === 'ArrowDown' ? 1 : -1) + grupos.length) % grupos.length;
        this.selecao.definir(grupos[ativo].ids); realcar();
        const e = caixa.querySelectorAll('.item')[ativo]; if (e) e.scrollIntoView({ block: 'nearest' });
        return;
      }
      if (ev.key === 'Enter') {
        ev.preventDefault();
        const ids = ativo >= 0 && grupos[ativo] ? grupos[ativo].ids : grupos.flatMap(g => g.ids);
        if (ids.length) { this.selecao.definir(ids); this.camera.zoomSelecao(ids); }
        fechar();
      }
    });
    document.addEventListener('click', (ev) => { if (!ev.target.closest('#busca-pecas')) fechar(); });
    document.addEventListener('keydown', (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'f') { ev.preventDefault(); campo.focus(); campo.select(); }
    });
  }

  /** Peças cujo texto casa com todas as palavras do termo; agrupadas por posição ou nome. */
  pesquisarPecas(termo) {
    const palavras = termo.toLowerCase().split(/\s+/).filter(Boolean);
    const grupos = new Map();
    let total = 0;
    const ids = [];
    for (const ent of this.documento.entidades.values()) {
      const a = ent.atributos || {}, m = a.marcas || {};
      const texto = [ent.nome, m.posicao, m.conjunto, m.nome, m.nome_conjunto, m.perfil, ent.perfil, ent.camada, a.tipo_ifc, ent.origem_ifc, ent.papel]
        .filter(Boolean).join(' ').toLowerCase();
      if (!palavras.every(p => texto.includes(p))) continue;
      total++; ids.push(ent.id);
      const chave = m.posicao || ent.nome || ent.tipo;
      let g = grupos.get(chave);
      if (!g) {
        const detalhe = [m.perfil && m.perfil !== chave ? m.perfil : (ent.perfil || ''), m.conjunto ? `conj. ${m.conjunto}` : '', ent.camada].filter(Boolean).join(' · ');
        g = { chave, detalhe, ids: [], cor: '#7d8a9e' };
        grupos.set(chave, g);
      }
      g.ids.push(ent.id);
    }
    const lista = [...grupos.values()].sort((x, y) => y.ids.length - x.ids.length || String(x.chave).localeCompare(String(y.chave), 'pt-BR', { numeric: true }));
    const cores = this._coresGrupo;
    for (const g of lista) {
      const ent = this.documento.entidades.get(g.ids[0]);
      const chaveCor = this._chaveDeGrupo(ent, this.corPor || 'padrao');
      if (cores && chaveCor != null && cores.has(chaveCor)) g.cor = cores.get(chaveCor);
    }
    return { total, ids, grupos: lista };
  }

  // ------------------------------------------------------------ cor por grupo

  /** Chave de agrupamento de uma entidade no modo pedido, ou null quando não tem. */
  _chaveDeGrupo(ent, modo) {
    const marcas = (ent.atributos && ent.atributos.marcas) || {};
    switch (modo) {
      case 'conjunto': return marcas.conjunto || null;
      case 'posicao': return marcas.posicao || null;
      case 'perfil': return ent.perfil || marcas.perfil || ent.nome || null;
      case 'tipo': return (ent.atributos && ent.atributos.tipo_ifc) || ent.papel || ent.tipo || null;
      default: return null;
    }
  }

  /**
   * Pinta o modelo por grupo (conjunto de montagem, posição, perfil ou tipo IFC), com
   * uma cor por chave. Entra pela mesma porta do mapa de esforços, `definirCorPorValor`,
   * então liga-se um ou outro: pedir um grupo esconde a análise, e mostrar a análise
   * volta este seletor ao padrão. A paleta é atribuída na ordem em que as chaves
   * aparecem e fica guardada, para a legenda e a cena concordarem.
   */
  _aplicarCorPor() {
    const modo = this.corPor || 'padrao';
    if (modo === 'padrao') {
      this._coresGrupo = null;
      if (!(this.analiseEstado && this.analiseEstado.ligado)) this.cena.definirCorPorValor(null);
      return;
    }
    if (this.analiseEstado && this.analiseEstado.ligado) this._mostrarAnalise(false);
    const cores = new Map();
    this._coresGrupo = cores;
    this.cena.definirCorPorValor((ent) => {
      const chave = this._chaveDeGrupo(ent, modo);
      if (chave == null) return null;
      if (!cores.has(chave)) cores.set(chave, corDeGrupo(cores.size));
      return cores.get(chave);
    });
  }

  _seletorCorPor() {
    const modo = this.corPor || 'padrao';
    const opcoes = [['padrao', 'camada e material'], ['conjunto', 'conjunto de montagem'],
                    ['posicao', 'posição (marca da peça)'], ['perfil', 'perfil'], ['tipo', 'tipo IFC']];
    const sel = el('select', { title: 'Pinta cada peça pela cor do grupo a que pertence' },
      ...opcoes.map(([v, t]) => el('option', { value: v, texto: t, selected: v === modo ? 'selected' : undefined })));
    sel.value = modo;
    sel.addEventListener('change', () => {
      this.corPor = sel.value;
      this._aplicarCorPor();
      this._agendarPaineis('camadas');
      this.dica(sel.value === 'padrao' ? 'Cores de camada e material.'
                                       : `Peças pintadas por ${opcoes.find(o => o[0] === sel.value)[1]}.`);
    });
    const caixa = el('div', { class: 'cor-por' }, el('label', { texto: 'Colorir por' }), sel);
    if (modo === 'padrao') return caixa;

    // legenda: uma linha por grupo, com contagem; clique seleciona, duplo clique enquadra
    const grupos = new Map();
    for (const ent of this.documento.entidades.values()) {
      const chave = this._chaveDeGrupo(ent, modo);
      if (chave == null) continue;
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(ent.id);
    }
    const cores = this._coresGrupo || new Map();
    const chaves = [...grupos.keys()].sort((a, b) =>
      String(a).localeCompare(String(b), 'pt-BR', { numeric: true }));
    const lista = el('div', { class: 'lista-linhas legenda-grupos' });
    const LIMITE = 400;
    for (const chave of chaves.slice(0, LIMITE)) {
      if (!cores.has(chave)) cores.set(chave, corDeGrupo(cores.size));
      const ids = grupos.get(chave);
      const linha = el('div', { class: 'linha', title: 'Clique: selecionar o grupo · Shift: somar · duplo clique: enquadrar' },
        el('span', { class: 'amostra', style: `background:${cores.get(chave)}` }),
        el('span', { class: 'nome', texto: String(chave) }),
        el('span', { class: 'contagem', texto: numero(ids.length) }));
      linha.addEventListener('click', (ev) => (ev.shiftKey ? this.selecao.somar(ids) : this.selecao.definir(ids)));
      linha.addEventListener('dblclick', () => { this.selecao.definir(ids); this.camera.zoomSelecao(ids); });
      lista.append(linha);
    }
    const semGrupo = this.documento.entidades.size - [...grupos.values()].reduce((s, v) => s + v.length, 0);
    caixa.append(el('div', { class: 'nota-grupos', texto:
      `${numero(grupos.size)} grupo(s)` + (semGrupo ? ` · ${numero(semGrupo)} peça(s) sem ${modo} ficam em cinza` : '') +
      (chaves.length > LIMITE ? ` · legenda mostra os ${LIMITE} primeiros` : '') }), lista);
    return caixa;
  }

  async _novaCamada() {
    const campo = el('input', { value: '', placeholder: 'ex.: Mezanino', spellcheck: 'false' });
    const cor = el('input', { type: 'color', value: '#5b7db1' });
    const corpo = el('div', { class: 'campos' }, el('label', { texto: 'Nome' }), campo,
                     el('label', { texto: 'Cor' }), cor);
    if (await this.dialogo({ titulo: 'Nova camada', corpo, ok: 'Criar' }) !== 'ok') return;
    const nome = campo.value.trim();
    if (!nome) return;
    if (this.documento.camadas.has(nome)) { this.aviso(`A camada "${nome}" já existe.`, 'atencao'); return; }
    this.executar(new ComandoAparencia('camadas', nome,
      { cor: cor.value, visivel: true, bloqueada: false }, `Nova camada ${nome}`));
    this.camadaAtiva = nome;
    this._agendarPaineis('camadas', 'props');
  }

  // ------------------------------------------------------------- materiais

  _painelMateriais() {
    const raiz = this.el.materiais;
    raiz.replaceChildren();
    const usos = contarPor(this.documento.lista, e => e.material || '');
    const lista = el('div', { class: 'lista-linhas' });
    const aplicar = (nome) => {
      if (this.selecao.vazia) { this.dica('Selecione objetos para aplicar o material.'); return; }
      this.alterarEntidades([...this.selecao.ids], { material: nome },
                            nome ? `Aplicar ${nome}` : 'Material pela camada');
    };
    const pelaCamada = el('div', { class: 'linha', title: 'Clique para aplicar à seleção' },
      el('span', { class: 'amostra', style: 'background:linear-gradient(135deg,#4b5563 50%,#0b3d91 50%)' }),
      el('span', { class: 'nome', texto: 'Pela camada' }),
      el('span', { class: 'contagem', texto: numero(usos.get('') || 0) }));
    pelaCamada.addEventListener('click', () => aplicar(''));
    lista.append(pelaCamada);
    for (const [nome, m] of this.documento.materiais) {
      const linha = el('div', { class: 'linha', title: `Clique para aplicar à seleção${m.aco ? ' · ' + m.aco : ''}` });
      const cor = el('input', { type: 'color', value: corHex(m.cor), title: 'Cor do material' });
      cor.addEventListener('change', () => this.executar(
        new ComandoAparencia('materiais', nome, { cor: cor.value }, `Cor de ${nome}`)));
      const op = el('input', { class: 'opacidade', type: 'number', min: '5', max: '100', step: '5',
                              value: Math.round((m.opacidade ?? 1) * 100), title: 'Opacidade (%)' });
      op.addEventListener('change', () => {
        const v = Math.min(100, Math.max(5, parseFloat(op.value) || 100)) / 100;
        this.executar(new ComandoAparencia('materiais', nome, { opacidade: v }, `Opacidade de ${nome}`));
      });
      linha.addEventListener('click', (ev) => { if (!ev.target.closest('input')) aplicar(nome); });
      linha.append(cor, el('span', { class: 'nome', texto: nome }),
                   el('span', { class: 'contagem', texto: numero(usos.get(nome) || 0) }), op);
      lista.append(linha);
    }
    raiz.append(lista);
  }

  // ---------------------------------------------------------------- análise

  /**
   * "Calcular estrutura": na primeira vez roda a análise no servidor; nas seguintes só
   * mostra ou esconde o que já foi calculado. Nada de esforços aparece na cena antes de
   * o usuário pedir.
   */
  async alternarAnalise() {
    if (this._calculando) return false;
    if (this.analise) { this._mostrarAnalise(!this.analiseEstado.ligado); return true; }
    return this.calcularEstrutura();
  }

  /** Pede os esforços ao servidor. `forcar` refaz mesmo havendo resultado guardado. */
  async calcularEstrutura({ forcar = false } = {}) {
    if (this._calculando) return false;
    if (this.analise && !forcar) { this._mostrarAnalise(true); return true; }
    if (!this._dadosGalpao) {
      this.aviso('Este modelo não veio de um galpão dimensionado, então não há esforços ' +
                 'para calcular. Use Arquivo → Gerar do galpão dimensionado… e tente de novo.',
                 'atencao');
      return false;
    }
    this._calculando = true;
    this._atualizarBotaoCalcular();
    this.dica('Calculando os esforços da estrutura…');
    const geracao = ++this._geracaoAnalise;
    let payload = null, motivo = '';
    try {
      const resposta = await fetch(ROTA_ANALISE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ dados: this._dadosGalpao }),
      });
      const texto = await resposta.text();
      try { payload = texto ? JSON.parse(texto) : null; } catch { payload = null; }
      if (!resposta.ok || (payload && payload.erro)) {
        motivo = (payload && payload.erro) || `${resposta.status} ${resposta.statusText}`;
        payload = null;
      }
    } catch {
      motivo = 'o servidor não respondeu — ele ainda está no ar?';
    }
    this._calculando = false;
    if (geracao !== this._geracaoAnalise) return false;      // trocaram o modelo no meio
    if (!payload || !payload.elementos) {
      this._atualizarBotaoCalcular();
      this.aviso('Não foi possível calcular os esforços: ' +
                 (motivo || 'o servidor respondeu sem resultados.'), 'erro');
      this.dica('Análise indisponível.');
      return false;
    }
    // O módulo de desenho vem antes da primeira pintura: senão o painel nasce com a
    // escala de reserva e sem a linha dos pórticos, e só se corrige no repinte seguinte.
    await this._carregarMapa();
    return this.aplicarAnalise(payload);
  }

  /** Guarda um resultado de análise e o põe na tela. Público: a verificação usa. */
  aplicarAnalise(payload) {
    if (!payload || !payload.elementos) return false;
    this.analise = payload;
    const combos = payload.combinacoes || [];
    const inicial = combos.find(c => c.chave === 'envoltoria') || combos[0];
    this.analiseEstado = {
      combinacao: inicial ? inicial.chave : 'envoltoria',
      grandeza: 'aproveitamento',
      // `porticos` é em quantos pórticos repetir o desenho — ver `_camadasAnalise`.
      camadas: { diagramas: true, deformada: false, cargas: false, porticos: 1 },
      exagero: 50,
      ligado: false,
    };
    this._carregarMapa().then(() => {
      if (this.analise !== payload) return;      // o modelo já mudou desde o pedido
      this._aplicarAoMapa();
      this._agendarPaineis('analise');
    });
    this._mostrarAnalise(true);
    const n = Object.keys(payload.elementos).length;
    const pior = this._piorAproveitamento();
    this.dica(`Análise pronta: ${numero(n)} elemento(s)` +
              (pior ? ` — pior aproveitamento ${numero(pior * 100, 0)} %.` : '.'));
    return true;
  }

  /** Liga ou desliga o mapa: cores e desenhos na cena, painel na coluna da direita. */
  _mostrarAnalise(ligado) {
    if (!this.analise) return;
    this.analiseEstado.ligado = !!ligado;
    if (ligado && this.corPor && this.corPor !== 'padrao') {
      // o mapa e a cor por grupo usam a mesma pintura: vale o que foi pedido por último
      this.corPor = 'padrao';
      this._coresGrupo = null;
      this._agendarPaineis('camadas');
    }
    this._comMapa(m => (ligado ? m.ligar() : m.desligar()));
    this.el.painelAnalise.hidden = !ligado;
    // Camadas e materiais cedem altura enquanto a análise está na tela: a coluna inteira
    // cabe na janela, e o painel recém-pedido não nasce cortado (regra em editor.css).
    this.el.paineis.toggleAttribute('data-analise', !!ligado);
    if (ligado) {
      // A coluna da direita é alta: sem rolar, o painel nasceria abaixo da dobra e quem
      // apertou "Calcular estrutura" não veria o resultado que pediu. Quem rola é o
      // desenho do painel: aqui o corpo ainda está vazio, e não haveria aonde rolar.
      this._rolarAteAnalise = true;
      this._agendarPaineis('analise');
    } else {
      this.el.analise.replaceChildren();
      this._linhasRanking = [];
      this.dica('Mapa de esforços oculto. O modelo voltou às cores normais.');
    }
    this._atualizarBotaoCalcular();
    this._sujo = true;
  }

  _limparAnalise() {
    this._geracaoAnalise++;
    if (this.analise) {
      this._comMapa(m => m.desligar());
      this.analise = null;
      this.analiseEstado = null;
      this._linhasRanking = [];
      if (this.el.painelAnalise) this.el.painelAnalise.hidden = true;
      if (this.el.paineis) this.el.paineis.removeAttribute('data-analise');
      if (this.el.analise) this.el.analise.replaceChildren();
      this._sujo = true;
    }
    this._atualizarBotaoCalcular();
  }

  _atualizarBotaoCalcular() {
    const ligado = !!(this.analiseEstado && this.analiseEstado.ligado);
    const rotulo = this._calculando ? 'Calculando…'
                 : ligado ? 'Ocultar análise'
                 : this.analise ? 'Mostrar análise' : 'Calcular estrutura';
    const b = this.el.calcular;
    if (b) {
      b.textContent = rotulo;
      b.disabled = this._calculando;
      b.setAttribute('aria-pressed', String(ligado));
    }
    const m = this.el.menuCalcular;
    if (m) {
      m.replaceChildren(rotulo, el('kbd', { texto: 'F9' }));
      m.disabled = this._calculando;
    }
  }

  /**
   * O desenho dos esforços mora em nucleo/analise3d.js. O import é tolerante porque o
   * painel — lista, legenda e serviço — vale por si: sem o módulo faltam só as cores na
   * cena e os diagramas.
   */
  async _carregarMapa() {
    if (this.mapa || this._mapaTentado) return this.mapa;
    this._mapaTentado = true;
    try {
      const modulo = await import('./nucleo/analise3d.js');
      if (modulo && modulo.MapaDeEsforcos) {
        this.mapa = new modulo.MapaDeEsforcos(this.cena, this.camera, this.documento);
      }
    } catch (e) {
      this._faltaMapa = String(e && e.message || e);
    }
    return this.mapa;
  }

  /** Chama o módulo de desenho sem deixar que um erro dele derrube o painel. */
  _comMapa(fn, padrao = null) {
    if (!this.mapa) return padrao;
    try { return fn(this.mapa); }
    catch (e) { this._faltaMapa = String(e && e.message || e); return padrao; }
  }

  _aplicarAoMapa() {
    const est = this.analiseEstado;
    if (!this.analise || !est) return;
    this._comMapa((m) => {
      m.definirDados(this.analise);
      m.definirCombinacao(est.combinacao);
      m.definirGrandeza(est.grandeza);
      m.definirCamadas({ ...est.camadas });
      m.definirEscalaDeformada(est.exagero);
      if (est.ligado) m.ligar(); else m.desligar();
    });
  }

  // ------------------------------------------------------------ painel

  _painelAnalise() {
    const raiz = this.el.analise;
    if (!raiz) return;
    raiz.replaceChildren();
    this._linhasRanking = [];
    const a = this.analise;
    if (!a) { raiz.append(el('div', { class: 'vazio', texto: 'Nenhuma análise calculada.' })); return; }
    const est = this.analiseEstado;
    const grandezas = (a.grandezas && a.grandezas.length) ? a.grandezas : GRANDEZAS_PADRAO;
    const combos = a.combinacoes || [];
    const atual = combos.find(c => c.chave === est.combinacao);
    const grandeza = grandezas.find(g => g.chave === est.grandeza) || grandezas[0];
    const faixa = this._faixaAnalise();

    raiz.append(el('div', { class: 'resumo-selecao' },
      el('strong', { texto: (atual && atual.nome) || 'Envoltória' }),
      el('span', { texto: faixa.percentual ? 'S/R em %'
                        : `${grandeza.nome}${faixa.unidade ? ` · ${faixa.unidade}` : ''}` })));

    const campos = el('div', { class: 'campos' });
    campos.append(el('label', { texto: 'Grandeza' }),
      this._lista(grandezas.map(g => [g.chave, g.nome]), est.grandeza, (v) => {
        est.grandeza = v;
        this._comMapa(m => m.definirGrandeza(v));
        this._agendarPaineis('analise');
        this._sujo = true;
      }));
    campos.append(el('label', { texto: 'Combinação' }), this._listaCombinacoes(combos, est));
    raiz.append(campos);
    if (atual && atual.descricao) {
      raiz.append(el('p', { class: 'analise-descricao', texto: atual.descricao }));
    }

    raiz.append(this._legendaAnalise(faixa));
    raiz.append(this._rankingAnalise(faixa));

    // Detalhe da peça selecionada: fica num nó próprio para o clique na lista poder
    // atualizá-lo sem refazer o painel inteiro (e sem fechar os seletores).
    this.el.detalheAnalise = el('div', { class: 'grupo-campos' });
    raiz.append(this.el.detalheAnalise);
    this._atualizarDetalheAnalise();

    raiz.append(this._camadasAnalise(est));
    raiz.append(this._servicoAnalise(a));

    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: 'Recalcular',
      title: 'Roda a análise de novo — use depois de mexer no modelo ou no dimensionamento',
      onclick: () => this.calcularEstrutura({ forcar: true }) }));
    acoes.append(el('button', { type: 'button', texto: 'Ocultar',
      title: 'Tira as cores e os desenhos da cena (F9)',
      onclick: () => this._mostrarAnalise(false) }));
    raiz.append(acoes);

    if (this._mapaTentado && !this.mapa) {
      raiz.append(el('p', { class: 'analise-descricao', texto:
        'O módulo de desenho não respondeu: a lista e a legenda funcionam, mas a cena ' +
        'fica sem as cores e sem os diagramas.' }));
    }

    // Só ao abrir: rolar a cada redesenho puxaria a coluna enquanto o usuário mexe nos
    // seletores.
    if (this._rolarAteAnalise) {
      this._rolarAteAnalise = false;
      this.el.painelAnalise.scrollIntoView({ block: 'start' });
    }
  }

  /** Select de combinações, com as últimas separadas das de serviço. */
  _listaCombinacoes(combos, est) {
    const s = el('select');
    const usados = new Set();
    for (const [tipo, rotulo] of [['envoltoria', ''], ['ultima', 'Combinações últimas'],
                                  ['servico', 'Combinações de serviço']]) {
      const desta = combos.filter(c => (c.tipo || 'ultima') === tipo);
      if (!desta.length) continue;
      const destino = rotulo ? el('optgroup', { label: rotulo }) : s;
      for (const c of desta) {
        usados.add(c.chave);
        destino.append(el('option', { value: c.chave, texto: c.nome || c.chave,
                                      title: c.descricao || '',
                                      selected: c.chave === est.combinacao }));
      }
      if (destino !== s) s.append(destino);
    }
    for (const c of combos.filter(c => !usados.has(c.chave))) {    // tipo novo não some
      s.append(el('option', { value: c.chave, texto: c.nome || c.chave,
                              selected: c.chave === est.combinacao }));
    }
    s.addEventListener('change', () => {
      est.combinacao = s.value;
      this._comMapa(m => m.definirCombinacao(s.value));
      this._agendarPaineis('analise');
      this._sujo = true;
    });
    return s;
  }

  /**
   * Faixa contínua de cores com os extremos e a unidade. As cores vêm do módulo de
   * desenho sempre que ele existe, para legenda e cena nunca divergirem.
   */
  _legendaAnalise(faixa) {
    const paradas = [];
    for (let i = 0; i <= 20; i++) paradas.push(this._corDaEscala(i / 20));
    const barra = el('div', { class: 'escala-cores',
                              style: `background:linear-gradient(90deg,${paradas.join(',')})` });
    if (faixa.percentual) {
      // O 100 % é a leitura que interessa: dali para cima a peça pede mais do que resiste.
      const t = (1 - faixa.min) / ((faixa.max - faixa.min) || 1);
      if (t > 0.03 && t < 0.97) {
        barra.append(el('span', { class: 'escala-marca', dados: { rotulo: '100 %' },
                                  style: `left:${(t * 100).toFixed(1)}%` }));
      }
    }
    return el('div', { class: 'grupo-campos escala' }, barra,
      el('div', { class: 'escala-extremos' },
        el('span', { texto: this._formatarValor(faixa.min, faixa) }),
        el('span', { class: 'unidade', texto: faixa.percentual ? '%' : (faixa.unidade || '') }),
        el('span', { texto: this._formatarValor(faixa.max, faixa) })));
  }

  /** As dez peças mais solicitadas na grandeza e na combinação escolhidas. */
  _rankingAnalise(faixa) {
    const caixa = el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Mais solicitadas' }));
    const itens = this._ordenarPorEsforco(10);
    if (!itens.length) {
      caixa.append(el('div', { class: 'vazio', texto: 'Sem valores nesta combinação.' }));
      return caixa;
    }
    const lista = el('div', { class: 'lista-linhas' });
    for (const item of itens) {
      const ids = item.ids || (item.id ? [item.id] : []);
      const ap = typeof item.aproveitamento === 'number' ? item.aproveitamento : null;
      // O ranking do módulo de desenho não repete `no_portico`; o verbete do elemento tem.
      const info = (this.analise.elementos || {})[item.elemento] || {};
      const fora = (item.no_portico === undefined ? info.no_portico : item.no_portico) === false;
      const linha = el('div', { class: 'linha',
        title: `${item.elemento || ''}${ids.length ? ` · ${ids.length} peça(s) no modelo` : ''}` +
               (fora ? ' · fora do modelo do pórtico: o valor não muda entre combinações' : '') +
               ' — clique seleciona, duplo clique enquadra' });
      const t = faixa.max === faixa.min ? 1 : (item.valor - faixa.min) / (faixa.max - faixa.min);
      linha.append(
        el('span', { class: 'amostra', style: `background:${this._corDaEscala(t)}` }),
        el('span', { class: 'marca', texto: item.marca || '—' }),
        el('span', { class: 'nome', texto: (item.elemento || '') + (fora ? ' *' : '') }),
        el('span', { class: 'contagem', texto: this._formatarValor(item.valor, faixa) }));
      if (!faixa.percentual) {
        linha.append(el('span', { class: 'aprov', dados: { ok: ap !== null && ap <= 1 ? '1' : '' },
          texto: ap === null ? '—' : `${numero(ap * 100, 0)} %` }));
      }
      linha.addEventListener('click', (ev) => {
        if (ev.target.closest('button, input')) return;
        this._clicarRanking(ids, ev);
      });
      linha.addEventListener('dblclick', (ev) => {
        if (ev.target.closest('button, input') || !ids.length) return;
        this.camera.zoomSelecao(ids);
      });
      lista.append(linha);
      this._linhasRanking.push({ el: linha, ids });
    }
    caixa.append(lista);
    if (itens.some(i => i.no_portico === false)) {
      caixa.append(el('p', { class: 'analise-descricao',
        texto: '* fora do modelo do pórtico: mesmo valor em todas as combinações.' }));
    }
    return caixa;
  }

  /** Interruptores das camadas, onde desenhá-las, e o exagero da deformada. */
  _camadasAnalise(est) {
    const caixa = el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Desenhos na cena' }));
    const lista = el('div', { class: 'lista-linhas' });
    for (const [chave, rotulo] of [['diagramas', 'Diagramas M/V/N'],
                                   ['deformada', 'Deformada'], ['cargas', 'Cargas em setas']]) {
      lista.append(this._interruptor(rotulo, !!est.camadas[chave], (v) => {
        est.camadas[chave] = v;
        this._comMapa(m => m.definirCamadas({ ...est.camadas }));
        // Diagramas liberam o seletor de pórticos; deformada, o campo de exagero.
        if (chave === 'diagramas' || chave === 'deformada') this._agendarPaineis('analise');
        this._sujo = true;
      }));
    }
    caixa.append(lista);

    // Os pórticos são iguais, e por isso a cena desenha num só. Sem dizer isto aqui, quem
    // olha o modelo conclui que os outros oito ficaram sem esforço.
    const campos = el('div', { class: 'campos' });
    const onde = this._lista([['1', '1 pórtico'], ['3', '3 pórticos (pontas e meio)'],
                              ['0', 'todos']],
      String(est.camadas.porticos ?? 1), (v) => {
        est.camadas.porticos = Number(v);
        this._comMapa(m => m.definirCamadas({ ...est.camadas }));
        this._agendarPaineis('analise');      // atualiza a linha do que está em exibição
        this._sujo = true;
      });
    onde.disabled = !est.camadas.diagramas;   // sem diagrama não há o que repetir
    campos.append(el('label', { texto: 'Desenhar em' }), onde);
    caixa.append(campos);

    if (est.camadas.deformada) {
      const exagero = el('div', { class: 'campos' });
      exagero.append(el('label', { texto: 'Exagero' }),
        this._num(est.exagero, (v) => {
          est.exagero = Math.max(1, v);
          this._comMapa(m => m.definirEscalaDeformada(est.exagero));
          this._sujo = true;
        }, { passo: 10, unidade: 'vezes o deslocamento real' }));
      caixa.append(exagero);
    }

    const emExibicao = this._textoPorticos(est);
    if (emExibicao) caixa.append(el('p', { class: 'analise-descricao', texto: emExibicao }));
    const tipicas = this._nomesTipicos();
    if (tipicas.length && est.camadas.diagramas) {
      caixa.append(el('p', { class: 'analise-descricao', texto:
        `${listarEmPortugues(tipicas)}: o diagrama sai numa peça típica de cada elemento, ` +
        'não em todas as peças iguais.' }));
    }
    return caixa;
  }

  /** Em que pórticos o desenho está aparecendo, em palavras. */
  _textoPorticos(est) {
    const c = est.camadas;
    if (!c.diagramas && !c.deformada && !c.cargas) return '';
    const desenhados = this._comMapa(m => m.porticosDesenhados(), []) || [];
    if (!desenhados.length) return '';
    const total = (((this.analise || {}).portico || {}).xs_mm || []).length;
    if (desenhados.length === 1) {
      const p = desenhados[0];
      return `Em exibição: pórtico ${p.indice} (x = ${metros(p.x_mm, 1)} m)` +
             (total > 1 ? `, dos ${total} iguais.` : '.');
    }
    // Com todos ligados, listar os nove números não diz nada que "todos" não diga.
    if (total && desenhados.length >= total) {
      return `Em exibição: todos os ${total} pórticos, iguais entre si.`;
    }
    return `Em exibição: pórticos ${listarEmPortugues(desenhados.map(p => String(p.indice)))}` +
           (total ? ` dos ${total}` : '') + ', todos iguais.';
  }

  /**
   * Elementos cujo diagrama sai sobre uma peça típica — terça e longarina são centenas
   * de peças iguais, e desenhar em todas não diria mais. O módulo informa quando sabe;
   * enquanto não souber, os próprios dados denunciam quem tem diagrama próprio.
   */
  _nomesTipicos() {
    const doMapa = this._comMapa(m => (typeof m.pecasTipicasDesenhadas === 'function'
      ? m.pecasTipicasDesenhadas() : null), null);
    if (Array.isArray(doMapa)) {
      const nomes = doMapa.map(p => (typeof p === 'string' ? p : (p && (p.elemento || p.nome))))
        .filter(Boolean).map(String);
      return [...new Set(nomes)];
    }
    return Object.entries(((this.analise || {}).elementos) || {})
      .filter(([, info]) => info && info.diagrama).map(([nome]) => nome);
  }

  _interruptor(rotulo, ligado, aoMudar) {
    const caixa = el('input', { type: 'checkbox' });
    caixa.checked = !!ligado;
    caixa.addEventListener('change', () => aoMudar(caixa.checked));
    return el('label', { class: 'linha interruptor' }, caixa, el('span', { class: 'nome', texto: rotulo }));
  }

  /** Deslocamento do topo contra o limite da norma, em barra de proporção. */
  _servicoAnalise(a) {
    const d = a.servico && a.servico.deslocamento;
    const caixa = el('div', { class: 'grupo-campos' });
    if (!d) return caixa;
    const razao = typeof d.razao === 'number' ? d.razao
                : (d.limite_cm ? d.u_cm / d.limite_cm : 0);
    const atende = razao <= 1;
    // Duas casas fixas nos dois: comparar "1,99" com "2" faria o limite parecer outro.
    const cm = (v) => Number(v).toLocaleString('pt-BR',
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const rente = razao > 0.95 && razao < 1.05;     // rente ao limite, a casa decimal diz
    caixa.append(el('h4', { texto: 'Serviço' }),
      el('div', { class: 'servico-linha' },
        el('span', { texto: 'Deslocamento do topo' }),
        el('strong', { class: atende ? 'bom' : 'ruim', texto: `${cm(d.u_cm)} cm` })),
      el('div', { class: 'barra-servico' },
        el('span', { class: 'preenche', dados: { ok: atende ? '1' : '' },
                     style: `width:${Math.min(100, Math.max(0, razao * 100)).toFixed(1)}%` })),
      el('div', { class: 'servico-linha dim' },
        el('span', { texto: `limite ${cm(d.limite_cm)} cm` +
                            (d.criterio ? ` · ${d.criterio}` : '') }),
        el('span', { texto: `${numero(razao * 100, rente ? 1 : 0)} % do limite` })));
    return caixa;
  }

  /**
   * O que governa a peça selecionada. Mostra a verificação (Sd/Rd e norma) e, separado,
   * os esforços que dimensionaram a peça — que não são os da combinação em exibição.
   */
  _atualizarDetalheAnalise() {
    const caixa = this.el.detalheAnalise;
    if (!caixa) return;
    caixa.replaceChildren();
    const escolhido = this._elementoSelecionado();
    if (!escolhido) {
      caixa.append(el('h4', { texto: 'Peça selecionada' }),
        el('div', { class: 'vazio', texto: 'Clique numa peça da lista ou do modelo.' }));
      return;
    }
    const { nome, info, marca } = escolhido;
    caixa.append(el('h4', { texto: `Peça selecionada · ${marca || nome}` }));
    const campos = el('div', { class: 'campos' });
    const linha = (rotulo, texto, titulo) => {
      if (!texto) return;
      campos.append(el('label', { texto: rotulo }),
                    el('span', { class: 'valor quebra', title: titulo || texto, texto }));
    };
    linha('Elemento', nome);
    if (info.perfil) linha('Perfil', info.perfil);
    if (typeof info.aproveitamento === 'number') {
      campos.append(el('label', { texto: 'S/R' }),
        el('span', { class: 'valor' },
          el('span', { class: 'aprov', dados: { ok: info.aproveitamento <= 1 ? '1' : '' },
                       texto: `${numero(info.aproveitamento * 100, 0)} %` })));
    }
    linha('Governa', info.governa);
    if (typeof info.Sd === 'number' && typeof info.Rd === 'number') {
      linha('Sd / Rd', `${numero(info.Sd, 0)} / ${numero(info.Rd, 0)}` +
                       (info.unidade ? ` ${info.unidade}` : ''));
    }
    linha('Norma', info.norma);
    const dim = info.dimensionamento;
    if (dim) {
      const u = this.analise.unidades || {};
      const partes = [];
      for (const [chave, rotulo] of [['M', 'M'], ['V', 'V'], ['N', 'N']]) {
        if (typeof dim[chave] === 'number') {
          partes.push(`${rotulo} ${numero(dim[chave], 1)}${u[chave] ? ' ' + u[chave] : ''}`);
        }
      }
      if (partes.length) linha('Dimensionou', partes.join(' · '));
      if (dim.caso) linha('Caso', dim.caso);
    }
    caixa.append(campos);
  }

  /** Primeiro elemento analisado que está na seleção. */
  _elementoSelecionado() {
    const a = this.analise;
    if (!a) return null;
    for (const ent of this.selecao.entidades) {
      const at = ent.atributos || {};
      const info = at.elemento && a.elementos[at.elemento];
      if (info) return { nome: at.elemento, info, marca: at.marca || ent.nome || '' };
    }
    return null;
  }

  // ------------------------------------------------------------ dados

  /** Extremos da escala. Vêm do módulo de desenho quando ele existe. */
  _faixaAnalise() {
    const est = this.analiseEstado, a = this.analise;
    const doMapa = this._comMapa(m => m.faixa());
    if (doMapa && typeof doMapa.min === 'number' && typeof doMapa.max === 'number' &&
        isFinite(doMapa.min) && isFinite(doMapa.max)) {
      return doMapa;
    }
    const percentual = est.grandeza === 'aproveitamento';
    let min = Infinity, max = -Infinity;
    for (const info of Object.values((a && a.elementos) || {})) {
      const v = this._valorDoElemento(info, est.combinacao, est.grandeza);
      if (v === null) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (!isFinite(min)) { min = 0; max = 1; }
    if (percentual) min = 0;                     // aproveitamento se lê a partir do zero
    if (max <= min) max = min + 1;
    return { min, max, unidade: percentual ? '' : this._unidadeDe(est.grandeza), percentual };
  }

  _unidadeDe(grandeza) {
    const a = this.analise || {};
    if (a.unidades && a.unidades[grandeza]) return a.unidades[grandeza];
    const g = (a.grandezas || GRANDEZAS_PADRAO).find(x => x.chave === grandeza);
    return (g && g.unidade) || '';
  }

  /** Valor de um elemento na combinação e na grandeza escolhidas; `null` se não houver. */
  _valorDoElemento(info, combinacao, grandeza) {
    if (!info) return null;
    if (grandeza === 'aproveitamento') {
      return typeof info.aproveitamento === 'number' ? info.aproveitamento : null;
    }
    const valores = info.valores || {};
    const daComb = valores[combinacao] || valores.envoltoria;
    const v = daComb ? daComb[grandeza] : undefined;
    return typeof v === 'number' && isFinite(v) ? v : null;
  }

  _piorAproveitamento() {
    let pior = 0;
    for (const info of Object.values((this.analise && this.analise.elementos) || {})) {
      if (typeof info.aproveitamento === 'number') pior = Math.max(pior, info.aproveitamento);
    }
    return pior;
  }

  /** Ranking do módulo de desenho quando existe; senão, montado aqui pelos dados. */
  _ordenarPorEsforco(n) {
    const doMapa = this._comMapa(m => m.ranking(n));
    if (Array.isArray(doMapa) && doMapa.length) return doMapa;
    const est = this.analiseEstado, a = this.analise;
    if (!a || !est) return [];
    // As peças do modelo agrupadas por elemento: é `atributos.elemento` que liga a
    // resposta do servidor às entidades desenhadas.
    const noModelo = new Map();
    for (const ent of this.documento.entidades.values()) {
      const at = ent.atributos || {};
      if (!at.elemento) continue;
      let reg = noModelo.get(at.elemento);
      if (!reg) noModelo.set(at.elemento, reg = { marca: '', ids: [] });
      reg.ids.push(ent.id);
      if (!reg.marca && at.marca) reg.marca = at.marca;
    }
    const itens = [];
    for (const [nome, info] of Object.entries(a.elementos)) {
      const valor = this._valorDoElemento(info, est.combinacao, est.grandeza);
      if (valor === null) continue;
      const reg = noModelo.get(nome);
      itens.push({ ids: reg ? reg.ids : [], marca: reg ? reg.marca : '', elemento: nome,
                   valor, aproveitamento: info.aproveitamento, no_portico: info.no_portico });
    }
    itens.sort((x, y) => Math.abs(y.valor) - Math.abs(x.valor));
    return itens.slice(0, n);
  }

  _corDaEscala(t) {
    const n = Math.min(1, Math.max(0, isFinite(t) ? t : 0));
    const doMapa = this._comMapa(m => m.cores(n));
    if (typeof doMapa === 'string' && /^#[0-9a-f]{3,8}$/i.test(doMapa)) return doMapa;
    const est = this.analiseEstado;
    return corDaRampa(est && est.grandeza === 'aproveitamento'
      ? RAMPA_APROVEITAMENTO : RAMPA_ESFORCOS, n);
  }

  _formatarValor(v, faixa) {
    if (typeof v !== 'number' || !isFinite(v)) return '—';
    if (faixa && faixa.percentual) return `${numero(v * 100, 0)} %`;
    const m = Math.abs(v);
    return numero(v, m >= 100 ? 0 : m >= 10 ? 1 : 2);
  }

  _clicarRanking(ids, ev) {
    if (!ids || !ids.length) { this.dica('Esta peça não está no modelo aberto.'); return; }
    if (ev && ev.shiftKey) this.selecao.somar(ids);
    else this.selecao.definir(ids);
  }

  /** Depois de a seleção mudar: marca as linhas e refaz o detalhe da peça. */
  _aposSelecaoAnalise() {
    for (const linha of (this._linhasRanking || [])) {
      linha.el.toggleAttribute('data-marcada', linha.ids.some(id => this.selecao.tem(id)));
    }
    this._atualizarDetalheAnalise();
  }

  // ----------------------------------------------------------------- árvore

  _painelArvore() {
    const raiz = this.el.arvore;
    const rolagem = raiz.scrollTop;
    raiz.replaceChildren();
    if (!this.documento.tamanho) {
      raiz.append(el('div', { class: 'vazio', style: 'padding:6px', texto:
        'Modelo vazio. Desenhe com as ferramentas à esquerda, ou use Arquivo → Gerar do galpão / Modelo de exemplo.' }));
      return;
    }
    const arvore = el('div', { class: 'arvore' });
    const porCamada = new Map();
    for (const e of this.documento.entidades.values()) {
      if (!porCamada.has(e.camada)) porCamada.set(e.camada, []);
      porCamada.get(e.camada).push(e);
    }
    const glifos = { barra: '│', chapa: '▭', solido: '◆', grupo: '▣' };
    for (const [nome, c] of this.documento.camadas) {
      const ents = porCamada.get(nome);
      if (!ents || !ents.length) continue;
      const ramo = el('div', { class: 'ramo' });
      if (this._ramosAbertos.has(nome)) ramo.dataset.aberto = '';
      const nsel = ents.filter(e => this.selecao.tem(e.id)).length;
      const titulo = el('button', { type: 'button', class: 'titulo',
        title: 'Clique abre/fecha · duplo clique seleciona a camada',
        onclick: () => {
          if (this._ramosAbertos.has(nome)) this._ramosAbertos.delete(nome);
          else this._ramosAbertos.add(nome);
          this._agendarPaineis('arvore');
        },
        ondblclick: (ev) => this.selecao.porCamada(nome, ev.shiftKey),
      }, el('span', { class: 'ponto', style: `background:${c.cor}` }),
         el('span', { texto: nome }),
         el('span', { class: 'contagem', texto: nsel ? `${nsel}/${ents.length}` : String(ents.length) }));
      ramo.append(titulo);
      if (this._ramosAbertos.has(nome)) {
        const folhas = el('div', { class: 'folhas' });
        const ordem = { barra: 0, chapa: 1, solido: 2, grupo: 3 };
        ents.sort((a, b) => (ordem[a.tipo] ?? 9) - (ordem[b.tipo] ?? 9) ||
                            String(a.nome).localeCompare(String(b.nome), 'pt-BR', { numeric: true }));
        const LIMITE = 400;
        for (const e of ents.slice(0, LIMITE)) {
          const detalhe = e.tipo === 'barra' ? e.perfil
                        : e.tipo === 'chapa' ? `${numero(e.espessura, 1)} mm`
                        : e.tipo === 'solido' ? `${(e.faces || []).length} faces` : '';
          folhas.append(el('button', {
            type: 'button', class: 'folha', 'aria-selected': String(this.selecao.tem(e.id)),
            title: this.descreverEntidade(e),
            onclick: (ev) => this.selecao.clicar(e.id, ev),
            ondblclick: () => this.camera.zoomSelecao([e.id]),
          }, el('span', { class: 'glifo', texto: glifos[e.tipo] || '·' }),
             el('span', { texto: e.nome || e.tipo }),
             el('span', { class: 'detalhe', texto: detalhe })));
        }
        if (ents.length > LIMITE) {
          folhas.append(el('div', { class: 'vazio', style: 'padding:2px 6px',
                                    texto: `+ ${ents.length - LIMITE} objetos (selecione pela camada)` }));
        }
        ramo.append(folhas);
      }
      arvore.append(ramo);
    }
    raiz.append(arvore);
    raiz.scrollTop = rolagem;
  }

  // ------------------------------------------------------------ verificação

  /** Parâmetros de URL usados nas capturas automáticas (e úteis para depurar). */
  _aplicarParametrosDeTeste() {
    const p = this.parametros;
    const sel = p.get('sel');
    if (sel) {
      if (PAPEIS.includes(sel)) this.selecao.porPapel(sel);
      else if (['barra', 'chapa', 'solido'].includes(sel)) this.selecao.porTipo(sel);
      else this.selecao.porCamada(sel);
    }
    const vista = p.get('vista');
    if (vista && VISTAS[vista]) this.camera.vista(vista);
    if (p.get('orto') === '1') this.el.projecao.click();
    const f = p.get('ferramenta');
    if (f) this.ativarFerramenta(f);
    // O cursor simulado, com ?teste=1, é aplicado no congelamento da captura, depois
    // de a câmera assentar; sem ele, aos 3 s.
    if (p.get('mouse') && p.get('teste') !== '1') setTimeout(() => this._simularMouse(p.get('mouse')), 3000);
    if (p.get('ciclo') === '1') setTimeout(() => this._cicloDeFerramentas(), 2500);
    if (p.get('abrirMenu')) {
      const m = document.querySelector(`.menu[data-menu="${p.get('abrirMenu')}"]`);
      if (m) m.classList.add('aberto');
    }
    if (p.get('teste') === '1') {
      setTimeout(() => this._congelarParaCaptura(), Number(p.get('captura')) || 7000);
    }
  }

  /**
   * Só para captura automática. No Chrome headless o relógio virtual corre à frente
   * do swiftshader, que rasteriza em tempo real: a captura sai antes de o quadro
   * pesado ficar pronto. Aqui desenhamos um quadro síncrono, lemos o buffer (o
   * toDataURL espera a GPU terminar) e o pomos como imagem sob as camadas de snap e
   * avisos. É exatamente o que o WebGL produziu; só o compositor fica de fora.
   */
  _congelarParaCaptura() {
    this.camera.concluirAnimacao();
    if (this.parametros.get('mouse')) this._simularMouse(this.parametros.get('mouse'));
    this.cena.desenhar(this.camera.ativa);
    const img = el('img', { src: this.el.canvas.toDataURL('image/png'), alt: '' });
    img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
    this.el.canvas.after(img);
    document.body.dataset.capturado = '1';
  }

  /**
   * Simula o cursor parado num ponto, para conferir o glifo do snap na captura.
   * `extremidade` mira 4 px ao lado do topo do primeiro pilar: a inferência precisa
   * preferir a extremidade à aresta e à face que estão logo ali.
   */
  _simularMouse(mouse) {
    const r = this.el.canvas.getBoundingClientRect();
    let mx, my;
    if (mouse === 'extremidade') {
      const b = this.documento.barras.find(e => e.papel === 'pilar') || this.documento.barras[0];
      if (!b) return;
      const t = this.camera.paraTela(b.fim);
      mx = t[0] + 4; my = t[1] + 3;
    } else {
      [mx, my] = mouse.split(',').map(Number);
    }
    this._processarMovimento({ clientX: r.left + mx, clientY: r.top + my, buttons: 0 });
    this._sujo = true;
  }

  /**
   * Teste de integração (?ciclo=1): passa por todas as ferramentas com o mouse e o
   * teclado de verdade — pelos mesmos manipuladores de evento do uso normal — e no
   * fim desfaz tudo. O resultado vai para body[data-ciclo]: erros por ferramenta e se
   * o documento voltou exatamente ao tamanho original.
   */
  async _cicloDeFerramentas() {
    const esperar = (ms) => new Promise(ok => setTimeout(ok, ms));
    const c = this.el.canvas;
    const r = c.getBoundingClientRect();
    this.camera.concluirAnimacao();
    this.camera.permitirNavegacao(false);     // o OrbitControls rejeita ponteiro sintético
    const tela = (q) => { const t = this.camera.paraTela(q); return [t[0], t[1]]; };
    const b = this.documento.barras[0];
    const pontos = [
      b ? tela(b.fim) : [r.width * 0.4, r.height * 0.4],
      b ? tela(b.inicio) : [r.width * 0.45, r.height * 0.5],
      [r.width * 0.5, r.height * 0.55],
      [r.width * 0.62, r.height * 0.62],
    ];
    const ponteiro = (tipo, [x, y]) => c.dispatchEvent(new PointerEvent(tipo, {
      clientX: r.left + x, clientY: r.top + y, button: 0, buttons: tipo === 'pointerup' ? 0 : 1,
      pointerId: 1, pointerType: 'mouse', bubbles: true, cancelable: true }));
    const mover = ([x, y]) => this._processarMovimento({ clientX: r.left + x, clientY: r.top + y, buttons: 0 });
    const tecla = (key) => document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    const antes = this.documento.tamanho;
    const relatorio = {};
    for (const id of this.ferramentas.keys()) {
      const e0 = (window.__errosEditor || []).length;
      const a0 = (this._registroErros || []).length;
      // As de edição precisam de algo selecionado para ter o que editar.
      if (['mover', 'girar', 'escalar', 'copiar', 'offset'].includes(id) && b) this.selecao.definir([b.id]);
      else this.selecao.limpar();
      this.ativarFerramenta(id);
      for (const [i, q] of pontos.entries()) {
        mover(q); await esperar(15);
        if (i < 3) { ponteiro('pointerdown', q); ponteiro('pointerup', q); await esperar(15); }
      }
      c.dispatchEvent(new MouseEvent('dblclick', {
        clientX: r.left + pontos[3][0], clientY: r.top + pontos[3][1], bubbles: true }));
      this.el.medida.value = '1500';
      this._enviarValor();
      tecla('Escape'); tecla('Escape');
      await esperar(15);
      relatorio[id] = {
        erros: (window.__errosEditor || []).slice(e0),
        avisosDeErro: (this._registroErros || []).slice(a0),
        objetos: this.documento.tamanho,
      };
    }
    this.ativarFerramenta('selecionar');
    const operacoes = this.pilha.feitos.length;
    while (this.pilha.podeDesfazer) this.pilha.desfazer();
    document.body.dataset.ciclo = JSON.stringify({
      antes, operacoes, depoisDeDesfazer: this.documento.tamanho, ferramentas: relatorio });
    this.camera.permitirNavegacao(true);
  }

  /** Estado da câmera e da cena, para depurar uma tela vazia sem abrir o DevTools. */
  diagnostico() {
    const r = (v) => Math.round(v * 1000) / 1000;
    const cam = this.camera.ativa, alvo = this.camera.alvo;
    const ruins = [];
    for (const [id, obj] of this.cena.objetos) {
      const m = obj.getObjectByName('malha');
      const g = m && m.geometry;
      if (!g) continue;
      if (!g.boundingSphere) g.computeBoundingSphere();
      const soma = obj.matrix.elements.reduce((s, x) => s + x, 0);
      if (!isFinite(g.boundingSphere.radius) || !isFinite(soma)) {
        const e = this.documento.get(id);
        ruins.push(`${e ? e.tipo : '?'}:${e && (e.nome || e.id)}`);
      }
    }
    const info = this.cena.renderizador.info.render;
    return {
      camera: [r(cam.position.x), r(cam.position.y), r(cam.position.z)],
      alvo: [r(alvo.x), r(alvo.y), r(alvo.z)], distancia: r(this.camera.distancia),
      passoGrade: this.cena._gradePasso, desenhos: info.calls, triangulos: info.triangles,
      contextoPerdido: this.cena.renderizador.getContext().isContextLost(),
      nRuins: ruins.length, ruins: ruins.slice(0, 8),
    };
  }

  _publicarErros() {
    let mostrados = 0;
    const publicar = () => {
      const erros = window.__errosEditor || [];
      // Com ?teste=1 os erros aparecem na tela, para ficarem na própria captura.
      if (this.parametros.get('teste') === '1') {
        for (; mostrados < erros.length; mostrados++) this.aviso(erros[mostrados], 'erro', 0);
      }
      document.body.dataset.erros = JSON.stringify(erros);
      try { document.body.dataset.diag = JSON.stringify(this.diagnostico()); }
      catch (e) { document.body.dataset.diag = 'falhou: ' + e.message; }
      document.body.dataset.objetos = String(this.documento.tamanho);
      document.body.dataset.malhas = String(this.cena.objetos.size);
      document.body.dataset.ferramentas = [...this.ferramentas.keys()].join(',');
      document.body.dataset.servidor = this.cena.usarServidor ? 'sim' : 'nao';
    };
    publicar();
    setInterval(publicar, 500);
  }
}

// ================================================================= apoio

function contarPor(lista, chave) {
  const m = new Map();
  for (const x of lista) { const k = chave(x); m.set(k, (m.get(k) || 0) + 1); }
  return m;
}

function uniao(a, b) {
  const s = new Set();
  for (const x of (a || [])) if (x) s.add(x);
  for (const x of (b || [])) if (x) s.add(x);
  return [...s];
}

function corHex(c) {
  return /^#[0-9a-f]{6}$/i.test(String(c)) ? c : '#8a94a6';
}

/** "a", "a e b", "a, b e c" — listas curtas no meio de uma frase. */
function listarEmPortugues(itens) {
  const l = (itens || []).filter(Boolean);
  if (l.length <= 1) return l.join('');
  return `${l.slice(0, -1).join(', ')} e ${l[l.length - 1]}`;
}

/** Cor de uma rampa de paradas hexadecimais, com `t` de 0 a 1. */
function corDaRampa(rampa, t) {
  const x = Math.min(1, Math.max(0, t)) * (rampa.length - 1);
  const i = Math.min(rampa.length - 2, Math.floor(x));
  return misturarHex(rampa[i], rampa[i + 1], x - i);
}

function misturarHex(a, b, t) {
  const ler = (c) => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const [r1, g1, b1] = ler(a), [r2, g2, b2] = ler(b);
  const canal = (u, v) => Math.round(u + (v - u) * t).toString(16).padStart(2, '0');
  return `#${canal(r1, r2)}${canal(g1, g2)}${canal(b1, b2)}`;
}

function textoDe(x) {
  if (x == null) return '';
  if (typeof x === 'string') return x;
  return x.mensagem || x.texto || x.descricao || JSON.stringify(x);
}

function volumeDe(s) {
  let v = 0;
  const p = s.vertices || [];
  for (const f of (s.faces || [])) {
    for (let i = 1; i < f.length - 1; i++) {
      const a = p[f[0]], b = p[f[i]], c = p[f[i + 1]];
      if (!a || !b || !c) continue;
      v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) +
            a[2] * (b[0] * c[1] - b[1] * c[0])) / 6;
    }
  }
  return Math.abs(v);
}

/**
 * Extensões de um sólido ao longo dos seus eixos principais (covariância dos vértices,
 * Jacobi 3×3), da maior para a menor: [comprimento, altura, espessura]. É a mesma conta do
 * detalhamento em Python, para o painel dizer o comprimento da peça importada.
 */
function dimensoesPrincipais(s) {
  const P = s.vertices || [];
  const n = P.length;
  if (n < 4) return null;
  const c = [0, 0, 0];
  for (const p of P) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  c[0] /= n; c[1] /= n; c[2] /= n;
  const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of P) {
    const d = [p[0] - c[0], p[1] - c[1], p[2] - c[2]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) A[i][j] += d[i] * d[j];
  }
  const V = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let it = 0; it < 60; it++) {
    let p = 0, q = 1, m = Math.abs(A[0][1]);
    if (Math.abs(A[0][2]) > m) { p = 0; q = 2; m = Math.abs(A[0][2]); }
    if (Math.abs(A[1][2]) > m) { p = 1; q = 2; m = Math.abs(A[1][2]); }
    if (m < 1e-9) break;
    const th = 0.5 * Math.atan2(2 * A[p][q], A[q][q] - A[p][p]);
    const co = Math.cos(th), si = Math.sin(th);
    for (let k = 0; k < 3; k++) { const akp = A[k][p], akq = A[k][q]; A[k][p] = co * akp - si * akq; A[k][q] = si * akp + co * akq; }
    for (let k = 0; k < 3; k++) { const apk = A[p][k], aqk = A[q][k]; A[p][k] = co * apk - si * aqk; A[q][k] = si * apk + co * aqk; }
    for (let k = 0; k < 3; k++) { const vkp = V[k][p], vkq = V[k][q]; V[k][p] = co * vkp - si * vkq; V[k][q] = si * vkp + co * vkq; }
  }
  const ordem = [0, 1, 2].sort((i, j) => A[j][j] - A[i][i]);
  return ordem.map(i => {
    const e = [V[0][i], V[1][i], V[2][i]];
    let lo = Infinity, hi = -Infinity;
    for (const p of P) { const t = (p[0] - c[0]) * e[0] + (p[1] - c[1]) * e[1] + (p[2] - c[2]) * e[2]; if (t < lo) lo = t; if (t > hi) hi = t; }
    return hi - lo;
  });
}

/** Translada uma entidade (usado só no colar de reserva). */
function mover(ent, d) {
  const t = (p) => [p[0] + d[0], p[1] + d[1], p[2] + d[2]];
  if (ent.tipo === 'barra') { ent.inicio = t(ent.inicio); ent.fim = t(ent.fim); }
  else if (ent.tipo === 'chapa' || ent.tipo === 'grupo') ent.origem = t(ent.origem);
  else if (ent.tipo === 'solido') ent.vertices = (ent.vertices || []).map(t);
  return ent;
}

// ------------------------------------------------------ modelo de exemplo

/**
 * Galpão de duas águas montado no navegador, com perfis plausíveis do catálogo.
 * NÃO é dimensionado: serve para testar o editor e para quando o gerador do
 * servidor (nucleo3d/de_projeto.py) não estiver disponível. Dados em metros e %,
 * como em DadosGalpao; o documento sai em milímetros.
 */
export function modeloDeExemplo(d, perfis) {
  const V = d.vao * 1000, L = d.comprimento * 1000, H = d.pe_direito * 1000;
  const i = (d.inclinacao || 10) / 100;
  const escolher = (tipo, alvo, campo = 'd') => {
    const l = perfis.filter(p => p.tipo === tipo && p[campo]);
    if (!l.length) return null;
    return l.reduce((m, p) => (Math.abs(p[campo] - alvo) < Math.abs(m[campo] - alvo) ? p : m));
  };
  const pPilar = escolher('I', 410), pViga = escolher('I', 360);
  const pTerca = escolher('Ue', 200), pLong = escolher('Ue', 150);
  const pCv = escolher('tubo', 60) || escolher('L', 64, 'bf');
  const nome = (p, reserva) => (p ? p.nome : reserva);
  const dim = (p, campo, reserva) => (p && p[campo]) || reserva;

  const ents = [];
  const barra = (reg) => ents.push({ tipo: 'barra', aco: 'ASTM A572 Gr.50', ...reg });
  const chapa = (reg) => ents.push({ tipo: 'chapa', aco: 'ASTM A36', camada: 'Chapas', papel: undefined, ...reg });

  const nPort = Math.max(2, Math.round(L / (d.espacamento_porticos * 1000)) + 1);
  const passo = L / (nPort - 1);
  const zCume = H + (V / 2) * i;
  const dPilar = dim(pPilar, 'd', 400), bPilar = dim(pPilar, 'bf', 180);
  const dViga = dim(pViga, 'd', 350), bViga = dim(pViga, 'bf', 170);
  const dTerca = dim(pTerca, 'd', 200), dLong = dim(pLong, 'd', 150);

  for (let k = 0; k < nPort; k++) {
    const x = k * passo, n = k + 1;
    for (const [lado, y] of [['A', 0], ['B', V]]) {
      barra({ nome: `P${n}${lado}`, inicio: [x, y, 0], fim: [x, y, H], perfil: nome(pPilar, 'W 410×46,1'),
              papel: 'pilar', rotacao: 90, camada: 'Estrutura' });
      barra({ nome: `V${n}${lado}`, inicio: [x, y, H], fim: [x, V / 2, zCume], perfil: nome(pViga, 'W 360×32,9'),
              papel: 'viga', camada: 'Estrutura' });
      // Chapa de base: horizontal, face de cima no nível zero, quatro chumbadores.
      const B = bPilar + 120, C = dPilar + 160, t = 25;
      chapa({ nome: `CB${n}${lado}`, origem: [x - B / 2, y - C / 2, -t / 2], eixo_x: [1, 0, 0], eixo_y: [0, 1, 0],
              contorno: [[0, 0], [B, 0], [B, C], [0, C]], espessura: t,
              furos: [[45, 45], [B - 45, 45], [B - 45, C - 45], [45, C - 45]].map(([fx, fy]) => ({ x: fx, y: fy, diametro: 27 })) });
      // Chapa de ligação viga-pilar, vertical, na face interna do pilar.
      const yFace = lado === 'A' ? dPilar / 2 : V - dPilar / 2;
      const w = bViga + 50, h = dViga * 1.7;
      chapa({ nome: `CL${n}${lado}`, origem: [x - w / 2, yFace, H - h * 0.72], eixo_x: [1, 0, 0], eixo_y: [0, 0, 1],
              contorno: [[0, 0], [w, 0], [w, h], [0, h]], espessura: 22,
              furos: [0.15, 0.38, 0.62, 0.85].flatMap(f => [[30, f * h], [w - 30, f * h]])
                .map(([fx, fy]) => ({ x: fx, y: fy, diametro: 22 })) });
    }
    // Emenda de cumeeira.
    const wc = bViga + 50, hc = dViga * 1.5;
    chapa({ nome: `CC${n}`, origem: [x - wc / 2, V / 2, zCume - hc * 0.6], eixo_x: [1, 0, 0], eixo_y: [0, 0, 1],
            contorno: [[0, 0], [wc, 0], [wc, hc], [0, hc]], espessura: 19 });
  }

  // Terças: vão a vão, sobre as vigas.
  const nTercas = Math.max(3, Math.ceil((V / 2) / 1600) + 1);
  const subir = dViga / 2 + dTerca / 2;
  let nt = 0;
  for (const lado of [0, 1]) {
    for (let j = 0; j < nTercas; j++) {
      const f = 0.03 + 0.94 * j / (nTercas - 1);
      const y = lado === 0 ? f * V / 2 : V - f * V / 2;
      const z = H + f * (zCume - H) + subir;
      for (let k = 0; k < nPort - 1; k++) {
        barra({ nome: `T${++nt}`, inicio: [k * passo, y, z], fim: [(k + 1) * passo, y, z],
                perfil: nome(pTerca, 'Ue 200×75×20×2,65'), papel: 'terça', camada: 'Terças', aco: 'CF-26' });
      }
    }
  }

  // Longarinas de fechamento lateral.
  let nl = 0;
  const afastar = dPilar / 2 + dLong / 2;
  for (const y of [-afastar, V + afastar]) {
    for (let z = 1500; z < H - 300; z += 1500) {
      for (let k = 0; k < nPort - 1; k++) {
        barra({ nome: `LG${++nl}`, inicio: [k * passo, y, z], fim: [(k + 1) * passo, y, z],
                perfil: nome(pLong, 'Ue 150×60×20×2,25'), papel: 'longarina', rotacao: 90,
                camada: 'Fechamento', aco: 'CF-26' });
      }
    }
  }

  // Contraventamento em X nos vãos das pontas: cobertura e paredes.
  let nc = 0;
  const cv = (a, b) => barra({ nome: `CV${++nc}`, inicio: a, fim: b, perfil: nome(pCv, 'TR 60,3×3,6'),
                               papel: 'contraventamento', camada: 'Contraventamento' });
  for (const k of [0, nPort - 2]) {
    const x0 = k * passo, x1 = (k + 1) * passo;
    for (const [yb, yc] of [[0, V / 2], [V, V / 2]]) {
      cv([x0, yb, H], [x1, yc, zCume]);
      cv([x0, yc, zCume], [x1, yb, H]);
    }
    for (const y of [0, V]) {
      cv([x0, y, 300], [x1, y, H - 300]);
      cv([x0, y, H - 300], [x1, y, 300]);
    }
  }

  return {
    nome: `Galpão ${numero(d.vao)} × ${numero(d.comprimento)} m (exemplo)`,
    unidade: 'mm', entidades: ents,
    metadados: { origem: 'modelo de exemplo do editor — não dimensionado' },
  };
}

// ================================================================ partida

const editor = new Editor();
window.editor = editor;                // útil no console do navegador
editor.iniciar().catch((e) => {
  console.error('o editor não conseguiu iniciar:', e);
  editor.aviso(`O editor não conseguiu iniciar: ${e.message}`, 'erro', 0);
});
