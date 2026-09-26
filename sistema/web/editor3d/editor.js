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
import { Cena, MODOS, ESCALA, PESADOS, medir } from './nucleo/cena.js';
import { lerPerfil, nomeDoPerfil, trocarSecao, BITOLAS } from './nucleo/trocar_perfil.js';
import { Camera, VISTAS } from './nucleo/camera.js';
import { Selecao } from './nucleo/selecao.js';
import { Inferencia } from './nucleo/inferencia.js';
import { api, ErroServidor } from './nucleo/api.js';
import { carregarFerramentas, GRUPOS } from './ferramentas/indice.js';
import { Ferramenta, formatar } from './ferramentas/base.js';
import { tamanhoDoFixador, quadroDoParafuso, geometriaDoParafuso, nomeDoParafuso, furoDoParafuso,
         DIAMETROS as DIAMETROS_PARAFUSO, CLASSES as CLASSES_PARAFUSO } from './ferramentas/parafuso.js';
import { refazerFurosEditor } from './ferramentas/_furar.js';
import { MetodosCantosEixos } from './modulos/cantos_eixos.js';
import { MetodosPaineis } from './modulos/paineis.js';
import { MetodosTrocaDePecas } from './modulos/troca_de_pecas.js';
import { MetodosAnalise } from './modulos/analise.js';
import { MetodosDiagnostico } from './modulos/diagnostico.js';
import { MetodosLancamento } from './modulos/lancamento.js';

/** Copia os métodos das classes dos módulos para a classe (getters e setters também). */
function aplicarMetodos(alvo, ...fontes) {
  for (const F of fontes) {
    for (const k of Object.getOwnPropertyNames(F.prototype)) {
      if (k === 'constructor') continue;
      if (Object.prototype.hasOwnProperty.call(alvo.prototype, k)) throw new Error(`método repetido no editor: ${k}`);
      Object.defineProperty(alvo.prototype, k, Object.getOwnPropertyDescriptor(F.prototype, k));
    }
  }
}

const CHAVE_TEMA = 'galpao.tema';               // a mesma da interface principal
const CHAVE_GALPAO = 'galpao.estado.v1';        // dados do galpão dimensionado
const CHAVE_ULTIMO = 'galpao.editor.ultimo';    // nome do último modelo salvo no servidor
const ATRASO_AUTOSAVE = 4000;                   // ms de sossego antes de gravar no servidor
const TECLAS_VISTA = ['topo', 'frente', 'tras', 'esquerda', 'direita', 'inferior', 'isometrica'];
const ARRASTO_MIN = 4;                          // pixels até um clique virar arrasto
const ABREVIACOES = { navegacao: 'Nav', desenho: 'Des', edicao: 'Edi', medicao: 'Med', estrutura: 'Estr' };

// Rota da análise de esforços. Mora aqui, e não em nucleo/api.js, porque é o editor que
// decide o que fazer quando ela não responde: o painel simplesmente não aparece.
export const ROTA_ANALISE = '/api/modelo/analise';

/** Grandezas do seletor quando o servidor não manda a própria lista. */
export const GRANDEZAS_PADRAO = [
  { chave: 'aproveitamento', nome: 'Aproveitamento (S/R)', unidade: '', percentual: true },
  { chave: 'M', nome: 'Momento fletor', unidade: 'kN·m' },
  { chave: 'V', nome: 'Esforço cortante', unidade: 'kN' },
  { chave: 'N', nome: 'Força normal', unidade: 'kN' },
];

// Rampas de reserva da legenda, para quando o módulo de desenho não estiver no ar.
// São sequenciais e de luminosidade crescente: leem igual no tema claro e no escuro.
export const RAMPA_ESFORCOS = ['#2c6fbb', '#3fa9c9', '#7ec97a', '#f2c24a', '#e8743b', '#c0392b'];
export const RAMPA_APROVEITAMENTO = ['#2f9e5f', '#8dc63f', '#f2c24a', '#e8743b', '#c0392b'];

// Cores de grupo (conjunto, posição, perfil): vinte tons de saturação média, que se
// distinguem entre si e do azul da seleção nos dois temas. A partir da 21ª, `corDeGrupo`
// gera tons novos pelo ângulo de ouro, em três faixas de claridade: um modelo com 160
// posições tem 160 cores diferentes, e vizinhas na ordem ficam longe no matiz.
const PALETA_GRUPOS = ['#d94a4a', '#2f9e5f', '#3d6fd6', '#e08a1e', '#8e44ad', '#17a2b8',
  '#c2185b', '#7cb342', '#f4c20d', '#6d4c41', '#00897b', '#5c6bc0', '#ef6c00', '#4db6ac',
  '#ad1457', '#9e9d24', '#1e88e5', '#e64a19', '#546e7a', '#8d6e63'];
export function corDeGrupo(i) {
  if (i < PALETA_GRUPOS.length) return PALETA_GRUPOS[i];
  const k = i - PALETA_GRUPOS.length;
  const h = (k * 137.508) % 360;
  const faixa = k % 3;
  const s = [72, 58, 80][faixa], l = [48, 62, 36][faixa];
  return `hsl(${h.toFixed(1)}, ${s}%, ${l}%)`;
}

export const $ = (sel, raiz = document) => raiz.querySelector(sel);

/** Cria um elemento com atributos e filhos, sem innerHTML para dados do usuário. */
/** Mesmo nome de arquivo que `projetos.slug` dá a um desenho 2D (espelho de cad.js). */
const slugDesenho = (s) => String(s || '').replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().toLowerCase().replace(/[\s_-]+/g, '-').slice(0, 60).replace(/^-+|-+$/g, '') || 'desenho';

export function el(tag, attrs = {}, ...filhos) {
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

export const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', {
  maximumFractionDigits: casas, minimumFractionDigits: 0 });
export const metros = (mm, casas = 2) => (mm / 1000).toLocaleString('pt-BR', {
  minimumFractionDigits: casas, maximumFractionDigits: casas });
export const ponto3 = (p) => p ? `${numero(p[0])}; ${numero(p[1])}; ${numero(p[2])}` : '—';
export const normalizarBusca = (s) => String(s || '').toLowerCase().normalize('NFD')
  .replace(/[̀-ͯ]/g, '').replace(/[×*]/g, 'x').replace(/[\s,.]/g, '');

// ----------------------------------------------------- comando de aparência

/** Altera uma camada ou um material (cor, visibilidade, bloqueio), com desfazer. */
export class ComandoAparencia extends Comando {
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
    this.cena = new Cena(this.el.canvas, this.documento, { api, escuro: this.escuro,
                                                          semLote: this.parametros.get('lote') === '0' });
    this.camera = new Camera(this.el.canvas, this.cena);
    this.selecao = new Selecao(this.documento, this.cena, this.camera);
    this.camera.idsSelecionados = () => [...this.selecao.ids];    // pivô da órbita
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
    const pedidoNaUrl = !!(this.projeto || this.parametros.get('galpao') === '1' || this.parametros.get('exemplo') || this.parametros.get('abrir'));
    if (this.projeto) await this._abrirProjeto();
    else if (this.parametros.get('galpao') === '1') await this._carregarGalpaoDaInterface();
    else if (this.parametros.get('exemplo')) this.carregarExemplo();
    else if (this.parametros.get('abrir')) await this.abrirModelo(this.parametros.get('abrir'));
    if (this.projeto) this._carregarReferencia();
    if (this.projeto && this.parametros.get('lancar') === '1') {
      const url = new URL(location.href); url.searchParams.delete('lancar'); history.replaceState(null, '', url);
      setTimeout(() => this.dialogoLancar(), 300);
    }
    if (this.parametros.get('destacar')) this._destacar(this.parametros.get('destacar'));
    else if (!pedidoNaUrl) {
      // Só sem pedido na URL volta ao último modelo (o documento é gravado no servidor a
      // cada mudança, então atualizar a página não pode jogar o trabalho fora). Com um
      // projeto na URL, este passo abria o modelo antigo por cima do projeto recém-aberto.
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

  /**
   * Enquanto uma operação longa roda no servidor (detalhar, importar IFC), mostra a
   * etapa corrente na linha de dica. Devolve a função que para de acompanhar.
   */
  _acompanharProgresso(prefixo = '') {
    if (!this.projeto) return () => {};
    const url = `/api/projetos/${encodeURIComponent(this.projeto)}/progresso`;
    const timer = setInterval(async () => {
      try {
        const p = await (await fetch(url, { cache: 'no-store' })).json();
        if (p && p.etapa) this.dica(`${prefixo}${p.etapa}${p.ha_s >= 3 ? ` (${Math.round(p.ha_s)} s)` : ''}`);
      } catch { /* servidor ocupado ou fora: tenta de novo no próximo tique */ }
    }, 700);
    return () => clearInterval(timer);
  }

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
    this._agendarPaineis('props');          // a ferramenta pode ter opções no painel (Parafuso)
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

  // ------------------------------------------------------ edição isolada

  /** Chapa: o que define a peça (contorno, furos, espessura), para saber se mudou. */
  _retratoChapa(e) {
    return e && e.tipo === 'chapa' ? JSON.stringify([e.contorno, e.furos, e.espessura]) : null;
  }

  /**
   * Edita a seleção sozinha no 3D: o resto do modelo some (também para seleção e snap),
   * a câmera enquadra a peça e as ferramentas trabalham só nela. "Voltar ao modelo" traz
   * tudo de volta; chapa mudada pode ser levada às peças iguais da mesma posição.
   */
  isolarSelecao() {
    const ids = [...this.selecao.ids];
    if (!ids.length) { this.dica('Selecione a peça que quer editar isolada.'); return; }
    const manter = new Set(ids);
    this.documento.foraDoIsolamento = new Set([...this.documento.entidades.keys()].filter(i => !manter.has(i)));
    this._isolamento = { ids, antes: new Map(ids.map(i => [i, this._retratoChapa(this.documento.get(i))])) };
    this.cena.repintarTudo();
    this.camera.zoomSelecao(ids);
    const nomes = ids.map(i => { const e = this.documento.get(i); const m = (e && e.atributos && e.atributos.marcas) || {}; return m.nome || m.posicao || (e && e.nome) || i; });
    const txt = `Editando isolado: ${[...new Set(nomes)].slice(0, 4).join(', ')}${nomes.length > 4 ? ' …' : ''}`;
    this._faixaIsolamento = el('div', { class: 'faixa-isolamento' },
      el('span', { texto: txt }),
      el('button', { type: 'button', texto: 'Voltar ao modelo', onclick: () => this.sairDoIsolamento() }));
    (this.el.palco || document.body).append(this._faixaIsolamento);
    this._agendarPaineis('props');
  }

  async sairDoIsolamento() {
    const iso = this._isolamento;
    if (!iso) return;
    this._isolamento = null;
    this.documento.foraDoIsolamento = null;
    if (this._faixaIsolamento) { this._faixaIsolamento.remove(); this._faixaIsolamento = null; }
    this.cena.repintarTudo();
    this.camera.zoomSelecao(iso.ids);
    this._agendarPaineis('props');
    // chapa mudada durante a edição: oferecer a mesma chapa às peças iguais (mesma posição)
    const mud = {}, rotulos = [];
    for (const id of iso.ids) {
      const e = this.documento.get(id);
      if (!e || e.tipo !== 'chapa' || this._retratoChapa(e) === iso.antes.get(id)) continue;
      const pos = ((e.atributos || {}).marcas || {}).posicao;
      if (!pos) continue;
      const iguais = [...this.documento.entidades.values()].filter(o => o.id !== id && o.tipo === 'chapa' && !iso.ids.includes(o.id)
        && ((o.atributos || {}).marcas || {}).posicao === pos);
      if (!iguais.length) continue;
      rotulos.push(`${((e.atributos || {}).marcas || {}).nome || pos} (${iguais.length} iguais)`);
      for (const o of iguais) mud[o.id] = { contorno: clonar(e.contorno), furos: clonar(e.furos), espessura: e.espessura };
    }
    if (!Object.keys(mud).length) return;
    const corpo = el('div', { class: 'explica', texto: `A chapa mudou durante a edição: ${rotulos.join(', ')}. Aplicar a mesma chapa (contorno, furos e espessura) às outras peças da mesma posição? Os parafusos delas não se movem — ajuste pelo detalhe da peça se for preciso.` });
    if (await this.dialogo({ titulo: 'Levar às peças iguais', corpo, ok: 'Aplicar às iguais', cancelar: 'Só esta' }) !== 'ok') return;
    this.executar(new ComandoAlterar(mud, 'Chapa editada isolada → peças iguais'));
    this.aviso(`${Object.keys(mud).length} peça(s) atualizadas como a editada. Ctrl+Z desfaz.`, 'info', 8000);
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
    this._atualizarMenuSombras();
    if (this.cena.sombrasDesligadasPeloTamanho && !this._avisouLeve) {
      this._avisouLeve = true;
      // Modelo grande abre leve: sem sombra do sol e sem as arestas de cada peça (num IFC
      // de milhares de peças elas são centenas de milhares de linhas, e viram um borrão).
      // Os dois voltam num clique, e o aviso diz onde.
      if (this.cena.emLote && this.cena.modo === 'sombreado_arestas') this.definirModo('sombreado');
      this.aviso(`Modelo grande (${numero(this.documento.tamanho)} peças): aberto no modo leve — sem sombra e ` +
                 'sem as arestas das peças. Os botões ao lado de "Perspectiva" voltam ao sombreado com arestas; ' +
                 'Ver → Sombras liga a sombra. Ver → Diagnóstico de desempenho mede a sua máquina.',
                 'info', 15000);
    }
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
        if (this._modeloNaoAbriu) throw new Error('o modelo do projeto não abriu nesta tela; nada foi gravado, para não sobrescrevê-lo — recarregue (F5)');
        // Ctrl+S junto com a gravação automática: espera ela terminar (senão a segunda
        // gravação levava a data velha e dava o falso "gravado por outra tela")
        if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
        const t0 = Date.now();
        while (this._autosalvando && Date.now() - t0 < 120000) await new Promise(r => setTimeout(r, 200));
        const versao = this._versaoEdicao || 0;
        const s = await this.api.salvarModeloDoProjeto(this.projeto, this.documento.paraJSON(), this._modeloAlterado);
        if (s && s.alterado) this._modeloAlterado = s.alterado;
        if ((this._versaoEdicao || 0) === versao) this._autosavePendente = false;
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
    this._versaoEdicao = (this._versaoEdicao || 0) + 1;
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
    if (this.projeto && this._modeloNaoAbriu) return;          // não grava por cima do que não abriu
    this._autosavePendente = false;
    this._autosalvando = true;
    const nome = this.el.nome.value.trim() || this.documento.nome || 'modelo';
    try {
      // Preparar o JSON de um modelo de milhares de peças custa segundos e trava a tela:
      // fica medido, para o diagnóstico poder apontá-lo.
      const json = medir('preparar a gravação automática', () => this.documento.paraJSON());
      if (this.projeto) {
        const s = await this.api.salvarModeloDoProjeto(this.projeto, json, this._modeloAlterado);
        if (s && s.alterado) this._modeloAlterado = s.alterado;
      } else {
        const r = await this.api.salvar(json, nome);
        this._lembrar(r.salvo || nome);
      }
    } catch (e) {
      this.dica(`Gravação automática falhou: ${e.message}`);
      this._autosavePendente = true;           // continua por gravar (antes a marca sumia e a edição ficava sem gravar)
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
    this._ligarVoltaAoDesenho(s);
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
    try { modelo = await this.api.modeloDoProjeto(s); } catch (e) {
      // não abrir não é "não ter modelo": nada de gerar do galpão nem gravar a tela vazia
      // por cima do modelo.json que existe
      this._modeloNaoAbriu = e.message || 'erro';
      this.aviso(`O modelo do projeto não abriu: ${e.message}. Nada será gravado nesta tela, para não sobrescrevê-lo — recarregue (F5) para tentar de novo.`, 'erro', 0);
      return;
    }
    this._modeloAlterado = modelo && modelo.alterado ? modelo.alterado : null;
    if (modelo && modelo.aberto_por && modelo.aberto_por.maquina) {
      const a = modelo.aberto_por;
      const ha = a.ha_s >= 60 ? `${Math.round(a.ha_s / 60)} min` : `${a.ha_s} s`;
      this.aviso(`Este projeto está aberto em "${a.maquina}"${a.usuario ? ` (${a.usuario})` : ''} há ${ha}. Se as duas máquinas gravarem, a segunda recebe "recarregue" e perde o que fez desde então: combine quem edita.`, 'atencao', 0);
    }

    if (modelo && modelo.documento) {
      try { this.carregarDocumento(modelo.documento, { autosalvar: false }); } catch (e) {
        this._modeloNaoAbriu = e.message || 'erro';
        this.aviso(`O modelo do projeto não pôde ser montado na tela: ${e.message}. Nada será gravado nesta tela, para não sobrescrevê-lo.`, 'erro', 0);
        return;
      }
      if (dados) {                      // é o que "Calcular estrutura" analisa
        this._dadosGalpao = dados;
        this._atualizarBotaoCalcular();
      } else {
        this._carregarCalculoGravado(s); // modelo importado: o cálculo fica em calculo.json
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
        const pararImp = this._acompanharProgresso('Importando: ');
        try { r = await this.api.importarIFCNoProjeto(this.projeto, arquivo); } finally { pararImp(); }
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

  /**
   * "Abrir o CAD 2D do projeto": vai direto ao detalhamento completo quando ele existe
   * (é o desenho de trabalho); senão ao CAD do projeto sem desenho.
   */
  async _abrirCADDoProjeto() {
    if (!this.projeto) { this._abrirCAD(); return; }
    let alvo = null;
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`);
      const desenhos = r.ok ? await r.json() : [];
      const d = (Array.isArray(desenhos) ? desenhos : []).find(x => x.nome === 'detalhamento-completo');
      if (d) alvo = d.nome;
    } catch { /* sem lista: abre o CAD do projeto */ }
    this._abrirCAD(alvo);
  }

  /** Tela do resultado da análise (o último cálculo gravado do projeto). */
  _abrirResultadoDaAnalise() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para ver o resultado da análise.', 'atencao'); return; }
    this._irPara(`/analise?projeto=${encodeURIComponent(this.projeto)}`);
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
   * Histórico do modelo do projeto: as gravações anteriores (marcos das operações que
   * mudam peças e uma cópia a cada 10 min); escolher uma volta o modelo a ela — a atual
   * vai para o histórico antes, então dá para desfazer o próprio restauro.
   */
  async dialogoRestaurarModelo() {
    if (!this.projeto) { this.aviso('Restaurar precisa de um projeto aberto.', 'atencao'); return; }
    let lista = [];
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/historico`);
      lista = (await r.json()).historico || [];
    } catch (e) { this.aviso(`Não foi possível ler o histórico: ${e.message}`, 'erro', 0); return; }
    if (!lista.length) { this.aviso('Este projeto ainda não tem gravações anteriores no histórico (elas começam a ser guardadas ao gravar o modelo).', 'info', 8000); return; }
    let escolhido = null;
    const opcoes = el('div', { class: 'lista-opcoes' });
    for (const h of lista) {
      const r = el('input', { type: 'radio', name: 'hist' });
      r.addEventListener('change', () => { if (r.checked) escolhido = h.arquivo; });
      const quando = h.quando ? h.quando.replace('T', ' ') : h.arquivo;
      opcoes.append(el('label', { class: 'linha' }, r, ` ${quando}  ·  ${String(h.mb).replace('.', ',')} MB${h.marco ? '  ·  marco (furos, detalhamento…)' : ''}`));
    }
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Gravações anteriores do modelo 3D deste projeto. Escolha uma para voltar a ela: o modelo atual vai para o histórico antes, então dá para desfazer. Os desenhos 2D não mudam; gere o detalhamento de novo depois.' }),
      opcoes);
    if (await this.dialogo({ titulo: 'Restaurar modelo anterior', corpo, ok: 'Restaurar' }) !== 'ok' || !escolhido) return;
    this.dica('Restaurando…');
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/restaurar-modelo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ arquivo: escolhido }),
      });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      this._autosavePendente = false;
      window.location.reload();
    } catch (e) { this.aviso(`Não foi possível restaurar: ${e.message}`, 'erro', 0); this.dica(''); }
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
    const pararDet = this._acompanharProgresso(`Detalhe de ${marca}: `);
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
    finally { pararDet(); }
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
    this.aviso(`${ids.length} peça(s) ${[...marcas].join(', ')} em destaque; o resto do modelo está esmaecido. Esc limpa a seleção e devolve o modelo; Detalhamentos volta ao CAD.`, 'info', 14000);
    const url = new URL(location.href); url.searchParams.delete('destacar'); history.replaceState(null, '', url);
  }

  /** Navega na mesma janela depois de gravar o que estiver pendente do autosave. */
  async _irPara(url) {
    try { await this.gravarConfirmado(); } catch (e) {
      const corpo = el('div', { class: 'explica', texto: `Não foi possível gravar o modelo: ${e.message}. Sair perde o que não foi gravado.` });
      if (await this.dialogo({ titulo: 'Modelo não gravado', corpo, ok: 'Sair mesmo assim' }) !== 'ok') return;
      this._autosavePendente = false;
    }
    window.location.href = url;
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
    await this.gravarConfirmado();
  }

  /**
   * Grava o que está pendente e só volta quando gravou (ou lança o erro): espera a
   * gravação automática em curso — ela saía na hora e a gravação "antes de" não esperava
   * — e não engole a falha. Usado pelo Atualizar, pelas vistas e pelas saídas da tela.
   */
  async gravarConfirmado() {
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    const t0 = Date.now();
    while (this._autosalvando) {
      if (Date.now() - t0 > 120000) throw new Error('a gravação automática em curso não terminou');
      await new Promise(r => setTimeout(r, 200));
    }
    if (!this._autosavePendente || !this.documento.tamanho) return;
    if (this.projeto && this._modeloNaoAbriu) throw new Error('o modelo do projeto não abriu nesta tela; nada foi gravado, para não sobrescrevê-lo');
    this._autosalvando = true;
    const versao = this._versaoEdicao || 0;
    try {
      const json = this.documento.paraJSON();
      if (this.projeto) {
        const s = await this.api.salvarModeloDoProjeto(this.projeto, json, this._modeloAlterado);
        if (s && s.alterado) this._modeloAlterado = s.alterado;
      } else {
        const nome = this.el.nome.value.trim() || this.documento.nome || 'modelo';
        const r = await this.api.salvar(json, nome);
        this._lembrar(r.salvo || nome);
      }
      if ((this._versaoEdicao || 0) === versao) this._autosavePendente = false;
    } finally {
      this._autosalvando = false;
      if (this._autosavePendente) this._agendarAutosave();
    }
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

  async dialogoDetalharPecas() {
    if (!this.projeto) { this.aviso('Abra o modelo por um projeto (gerenciador) para detalhar.', 'atencao'); return; }
    const grupos = [['tesouras', 'Tesouras (com as barras e chapas delas)'], ['conjuntos', 'Conjuntos (vigas, pilares e outros)'], ['tercas', 'Terças (com suportes e chapas)'], ['contraventamentos', 'Contraventamentos (com tirantes e peças de ponta)'], ['agulhamentos', 'Agulhamentos'], ['extras', 'Extras (perfil de forro, de fechamento, barras soltas)'], ['telhas', 'Telhas'], ['chaparias', 'Chaparias (todas as chapas, 1:10)'], ['localizacao', 'Planta de localização (marcas no lugar de montagem, com os eixos)'], ['chumbacao', 'Planta de chumbação (chumbadores e chapas de base nos eixos)'], ['completo', 'Desenho completo (tudo num desenho só, 1:25)']];
    const caixas = {};
    const grade = el('div', { class: 'campos' });
    for (const [k, r] of grupos) { caixas[k] = el('input', { type: 'checkbox', checked: 'checked' }); grade.append(el('label', { texto: r }), caixas[k]); }
    const regra = el('input', { type: 'checkbox', checked: 'checked' });
    // os nomes ao lado de cada barra da tesoura atrapalhavam quem gabarita a treliça e mede
    // peça a peça: saem desligados, e quem quiser liga
    const rotular = el('input', { type: 'checkbox' });
    const converter = el('input', { type: 'checkbox', checked: 'checked' });
    const substituir = el('input', { type: 'checkbox', checked: 'checked' });
    grade.append(el('label', { texto: 'Furação das terças no padrão da fábrica', title: 'Terça com menos de 200 mm: furos a 50 mm na vertical e 60 na horizontal; com 200 mm ou mais: 100 × 60. Vale para os suportes com a mesma furação.' }), regra,
                 el('label', { texto: 'Rotular posições nos conjuntos', title: 'Escreve o nome de cada barra ao lado dela na elevação da tesoura. Desligado por padrão: a fábrica gabarita a tesoura e mede peça a peça.' }), rotular,
                 el('label', { texto: 'Chapas planas viram chapas paramétricas no 3D', title: 'Furos e tamanho da chapa ficam editáveis no desenho. Desligado, a chapa continua o sólido que veio do IFC.' }), converter,
                 el('label', { texto: 'Substituir os desenhos de detalhamento anteriores' }), substituir);
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: 'Cada posição (marca de peça do IFC) vira uma célula com título "P12 – 112x", perfil ou chapa, contorno, furos e cotas; as peças iguais são contadas, não repetidas. Cada conjunto (marca de montagem) vira uma elevação com a cadeia de cotas dos nós e a lista de perfis. Sai também o romaneio em detalhamento/romaneio.csv.' }),
      grade);
    if (await this.dialogo({ titulo: 'Detalhar peças e conjuntos', corpo, ok: 'Detalhar e abrir' }) !== 'ok') return;
    const escolhidos = grupos.map(([k]) => k).filter(k => caixas[k].checked);
    if (!escolhidos.length) return;
    this.dica('Detalhando as peças do projeto…');
    this.aviso('Detalhando: analisando cada posição e conjunto do modelo. A etapa corrente aparece na linha de baixo.', 'info', 8000);
    const parar = this._acompanharProgresso('Detalhando: ');
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
                 (tercas ? `; furação de fábrica aplicada em ${tercas} posições` : '') + `. Lista de materiais em Detalhamentos → Lista de materiais.` +
                 (j.avisos && j.avisos.length ? ` ${j.avisos.length} aviso(s) no relatório.` : ''), 'info', 15000);
      parar();
      this.dica('Detalhamento pronto.');
      if (j.desenhos.length) this._abrirCAD(j.desenhos[0].nome);
    } catch (e) { parar(); this.aviso(`Não foi possível detalhar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** Só as peças pedidas: furos das barras nas chapas e nos parafusos, e as células delas
   *  redesenhadas nos desenhos de detalhamento (rota /atualizar-pecas). */
  async atualizarPecas(marcas) {
    if (!this.projeto || !marcas.length) return;
    this.aviso(`Atualizando ${marcas.slice(0, 6).join(', ')}${marcas.length > 6 ? '…' : ''}: furos das barras e desenhos destas peças.`, 'info', 6000);
    const parar = this._acompanharProgresso('Atualizando: ');
    try {
      await this._gravarAntesDeGerar();
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/atualizar-pecas`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify({ marcas }) });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      parar();
      const partes = [];
      if (j.furos_barras) partes.push(`${j.furos_barras} furo(s) movidos nas barras ${j.barras.join(', ')}`);
      partes.push(j.desenhos.length ? `redesenhadas em ${j.desenhos.join(', ')}` : 'nenhum desenho de detalhamento tinha estas peças');
      if (j.detalhes.length) partes.push(`refeito ${j.detalhes.join(', ')}`);
      this.aviso(`${j.pecas.join(', ')}: ${partes.join('; ')}. A elevação das tesouras e conjuntos só muda gerando o detalhamento de novo.`, 'info', 15000);
      if (j.furos_barras) await this._abrirProjeto();            // os furos novos na malha 3D
    } catch (e) { parar(); this.aviso(`Não foi possível atualizar: ${e.message}`, 'erro', 0); }
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
      'restaurar-modelo': () => this.dialogoRestaurarModelo(),
      desfazer: () => this.desfazer(),
      refazer: () => this.refazer(),
      'selecionar-tudo': () => this.selecao.tudo(),
      'inverter-selecao': () => this.selecao.inverter(),
      apagar: () => this.apagarSelecao(),
      'zoom-extensao': () => this.camera.zoomExtensao(),
      'zoom-selecao': () => this.camera.zoomSelecao([...this.selecao.ids]),
      'mapa-esforcos': () => this.alternarAnalise(),
      dimensionar: () => this.dimensionarEstrutura(),
      sombras: () => this.alternarSombras(),
      desempenho: () => this.dialogoDesempenho(),
      'desenho-corte': () => this.gerarDesenhoDoCorte(),
      'desenho-selecao': () => this.dialogoVistasDaSelecao(),
      'detalhar-pecas': () => this.dialogoDetalharPecas(),
      'cantos-redondos': () => this.dialogoCantosRedondos(),
      'eixos-obra': () => this.dialogoEixos(),
      'lancar-estrutura': () => this.dialogoLancar(),
      'memorial-lancamento': () => this.memorialDoLancamento(),
      'planta-lancamento': () => this._irPara(`/cad?projeto=${encodeURIComponent(this.projeto || '')}&desenho=${encodeURIComponent('planta-de-lançamento')}`),
      referencia: () => this.alternarReferencia(),
      'abrir-cad': () => this._abrirCADDoProjeto(),
      'materiais': () => this._abrirMateriais(),
      'resultado-analise': () => this._abrirResultadoDaAnalise(),
      'excluir-desenhos': () => this._excluirDesenhos(),
      isolar: () => (this._isolamento ? this.sairDoIsolamento() : this.isolarSelecao()),
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
    const refino = c.usarServidor && !c.emLote;
    this.el.servidor.textContent = (refino ? 'malhas: servidor' : 'malhas: locais') + (c.emLote ? ' · lote' : '');
    this.el.servidor.title = refino
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

}

// os métodos que moram nos módulos (web/editor3d/modulos/)
aplicarMetodos(Editor, MetodosCantosEixos, MetodosPaineis, MetodosTrocaDePecas, MetodosAnalise, MetodosDiagnostico, MetodosLancamento);

// ================================================================= apoio

export function contarPor(lista, chave) {
  const m = new Map();
  for (const x of lista) { const k = chave(x); m.set(k, (m.get(k) || 0) + 1); }
  return m;
}

export function uniao(a, b) {
  const s = new Set();
  for (const x of (a || [])) if (x) s.add(x);
  for (const x of (b || [])) if (x) s.add(x);
  return [...s];
}

export function corHex(c) {
  return /^#[0-9a-f]{6}$/i.test(String(c)) ? c : '#8a94a6';
}

/** "a", "a e b", "a, b e c" — listas curtas no meio de uma frase. */
export function listarEmPortugues(itens) {
  const l = (itens || []).filter(Boolean);
  if (l.length <= 1) return l.join('');
  return `${l.slice(0, -1).join(', ')} e ${l[l.length - 1]}`;
}

/** Cor de uma rampa de paradas hexadecimais, com `t` de 0 a 1. */
export function corDaRampa(rampa, t) {
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

export function volumeDe(s) {
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
export function dimensoesPrincipais(s) {
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
export function mover(ent, d) {
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
// o botão "Atualizar" (web/atualizacao.js) grava o modelo antes de instalar
window.__antesDeAtualizar = () => editor.gravarConfirmado();
// fechar a janela com edição por gravar avisa (o navegador pergunta se quer sair)
window.addEventListener('beforeunload', (e) => {
  if ((editor._autosavePendente || editor._autosalvando) && !(editor.projeto && editor._modeloNaoAbriu)) { e.preventDefault(); e.returnValue = ''; }
});
editor.iniciar().catch((e) => {
  console.error('o editor não conseguiu iniciar:', e);
  editor.aviso(`O editor não conseguiu iniciar: ${e.message}`, 'erro', 0);
});
