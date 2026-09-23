// Mapa de esforços: onde estão os maiores esforços, momentos, cargas e deslocamentos.
//
// Duas leituras ao mesmo tempo, a partir do JSON de `POST /api/modelo/analise`:
//
//   1. a peça inteira pintada pelo valor do seu elemento (aproveitamento, M, V ou N),
//      pela cor que entra na cena pelo `_corDe` — o mesmo ponto por onde material e
//      camada já passavam, e por isso a seleção continua azul por cima;
//   2. os desenhos do pórtico — as fitas de M, V e N, a deformada e as cargas em setas —
//      num grupo próprio da cena, no espírito do grupo `previa`, mas separado dele
//      (`editor.ativarFerramenta` limpa a prévia a cada troca de ferramenta).
//
// O que é desenhado aqui nunca entra no documento: não é entidade, logo não aparece na
// árvore, na lista de material nem no IFC, e não entra no raycast da seleção (a cena só
// oferece como alvo o que está em `objetos`).
//
// A classe nasce desligada: construir, e mesmo chamar `definirDados`, não muda nada na
// cena. Quem liga é o botão do painel, por `ligar()`; `desligar()` devolve a cena ao
// estado anterior — cores normais de volta, grupo esvaziado e descartado, seleção e
// realce intactos. Ligar e desligar em sequência não acumula objeto nem material: todo
// desenho passa por `_limparDesenhos`, que descarta geometria, material e textura.
//
// Unidades: o pórtico e a deformada vêm em milímetros, como o documento; os esforços em
// kN e kN·m. O grupo vive dentro de `cena.raiz`, que já carrega a escala mm → m.

import * as THREE from 'three';
import { ESCALA, misturar } from './cena.js';

/**
 * Chave do elemento de uma entidade: `atributos.elemento` no galpão gerado; no modelo
 * importado do IFC o cálculo verifica por posição, e a chave é a marca (`marcas.posicao`).
 */
export function elementoDaEntidade(ent) {
  const at = (ent && ent.atributos) || {};
  return at.elemento || (at.marcas && at.marcas.posicao) || null;
}

/** Grandezas que têm diagrama ao longo da barra. */
export const GRANDEZAS_DE_DIAGRAMA = ['M', 'V', 'N'];

/** Teto fixo da escala de aproveitamento. Acima de 1,0 já é reprovação; 1,2 dá margem
 *  para mostrar o quanto passou sem espremer toda a faixa útil embaixo. */
export const APROVEITAMENTO_MAX = 1.2;

/**
 * Aproveitamento: verde até 0,7, amarelo perto de 0,9, laranja em 1,0 e vermelho acima.
 * As posições são valores de aproveitamento, não frações da rampa. O salto curto entre
 * 1,00 e 1,02 é de propósito: passar de 1,0 tem de aparecer como uma virada, e não como
 * mais um tom de laranja.
 */
const RAMPA_APROVEITAMENTO = [
  [0.00, '#1a8a4b'], [0.45, '#3f9f3f'], [0.70, '#93bd2c'],
  [0.88, '#e9bb23'], [1.00, '#ef8a1d'], [1.02, '#df4f27'], [1.20, '#a5121f'],
];

/**
 * M, V e N: de 0 ao maior valor em módulo. A sequência anda por matiz e mantém a
 * luminosidade no meio da faixa, para nenhum degrau sumir — nem o escuro no tema escuro,
 * nem o claro no tema claro.
 */
const RAMPA_ESFORCO = [
  [0.00, '#4a6ad4'], [0.25, '#2aa6bd'], [0.50, '#57b449'],
  [0.72, '#e3ae28'], [0.88, '#e67828'], [1.00, '#cd2f35'],
];

/** Cor de cada desenho. Não use o azul da seleção (#1f7ae0) em nada disto. */
const CORES_DESENHO = {
  M: '#7b4bd8', V: '#0e9f6e', N: '#e07b1f',
  deformada: '#d94f70', carga: '#0e7490', referencia: '#8a94a6',
};

/** Altura da maior fita, em fração do tamanho do pórtico. */
const ALTURA_FITA = 0.16;
/** Exagero da deformada quando o servidor não sugere um. */
const EXAGERO_PADRAO = 40;

// --------------------------------------------------------------- vetores (mm)

const somar = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const subtrair = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const escalarVet = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const cruzar = (a, b) => [a[1] * b[2] - a[2] * b[1],
                          a[2] * b[0] - a[0] * b[2],
                          a[0] * b[1] - a[1] * b[0]];
const comprimento = (a) => Math.hypot(a[0], a[1], a[2]);

function normalizado(a, padrao = [0, 0, 1]) {
  if (!Array.isArray(a) || a.length < 3) return padrao.slice();
  const n = comprimento(a);
  return n > 1e-9 ? [a[0] / n, a[1] / n, a[2] / n] : padrao.slice();
}

const entre = (v, min, max) => Math.max(min, Math.min(max, v));
const finito = (v) => Number.isFinite(Number(v));
const ponto3 = (p) => Array.isArray(p) && p.length >= 3 && p.every(finito);

/** Ponto a uma fração `s` do eixo da barra. */
const aoLongo = (ini, fim, s) => [
  ini[0] + (fim[0] - ini[0]) * s,
  ini[1] + (fim[1] - ini[1]) * s,
  ini[2] + (fim[2] - ini[2]) * s,
];

/** Número em português, com as casas que o valor merece. */
function numero(v, casas = 1) {
  return Number(v).toLocaleString('pt-BR',
    { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/** Cor de uma rampa no valor `v` (as posições da rampa são valores, não frações). */
function amostrarRampa(rampa, v) {
  const x = entre(v, rampa[0][0], rampa[rampa.length - 1][0]);
  for (let i = 1; i < rampa.length; i++) {
    const [p0, c0] = rampa[i - 1], [p1, c1] = rampa[i];
    if (x <= p1) {
      const k = p1 > p0 ? (x - p0) / (p1 - p0) : 0;
      return misturar(c0, c1, k);
    }
  }
  return rampa[rampa.length - 1][1];
}

// ==================================================================== a classe

export class MapaDeEsforcos {
  /**
   * @param cena       a Cena (pinta as peças e hospeda os desenhos)
   * @param camera     a Camera (reservada para ajustes por zoom; pode ser null)
   * @param documento  o Documento, para casar elemento com peça
   */
  constructor(cena, camera, documento) {
    this.cena = cena;
    this.camera = camera || null;
    this.documento = documento || (cena && cena.documento) || null;

    this.dados = null;
    this.combinacao = 'envoltoria';
    this.grandeza = 'aproveitamento';
    this.camadas = { diagramas: true, deformada: false, cargas: false };
    this.fatorDeformada = null;        // null: usa a escala sugerida pelo servidor
    // Em quantos pórticos repetir o desenho. Um só, por padrão: ver `_xsDesenhados`.
    // Zero desenha em todos.
    this.limitePorticos = 1;

    this.ligado = false;
    this.grupo = null;                 // só existe enquanto ligado
    this._porElemento = new Map();     // nome do elemento -> registro da análise
    this._barras = new Map();          // rótulo da barra -> registro do pórtico
    this._faixa = null;                // faixa da grandeza atual, durante a pintura
    this._tipicas = [];                // peças típicas desenhadas no último desenho
    this._desinscrever = null;
  }

  // ------------------------------------------------------------------ dados

  /** JSON da rota de análise. Sem ligar, nada muda na cena. */
  definirDados(payload) {
    this.dados = payload && typeof payload === 'object' ? payload : null;
    this._porElemento = new Map();
    this._barras = new Map();
    this._tamanho = null;              // a régua dos desenhos vem do pórtico novo
    if (this.dados) {
      for (const [nome, el] of Object.entries(this.dados.elementos || {})) {
        // a chave vence o campo `nome` do verbete (no modelo importado ele é o nome de produção)
        if (el && typeof el === 'object') this._porElemento.set(nome, { ...el, nome });
      }
      for (const b of ((this.dados.portico || {}).barras || [])) {
        if (b && b.rotulo && ponto3(b.ini) && ponto3(b.fim)) this._barras.set(b.rotulo, b);
      }
    }
    // A combinação e a grandeza escolhidas antes podem não existir nos dados novos.
    if (!this.combinacoes.some(c => c.chave === this.combinacao)) {
      const lista = this.combinacoes;
      this.combinacao = lista.length ? lista[0].chave : 'envoltoria';
    }
    if (!this.grandezas.some(g => g.chave === this.grandeza)) this.grandeza = 'aproveitamento';
    if (this.ligado) this.atualizar();
    return this;
  }

  /** Há dados? */
  get pronto() { return !!(this.dados && this._porElemento.size); }

  /** Combinações oferecidas pelo servidor. */
  get combinacoes() {
    const lista = (this.dados && this.dados.combinacoes) || [];
    return lista.filter(c => c && c.chave);
  }

  /** Grandezas oferecidas pelo servidor. */
  get grandezas() {
    const lista = (this.dados && this.dados.grandezas) || [];
    return lista.filter(g => g && g.chave);
  }

  /** Informação de serviço (deslocamento e seu limite), quando vier. */
  get servico() { return (this.dados && this.dados.servico) || null; }

  definirCombinacao(chave) {
    if (!chave) return this;
    this.combinacao = String(chave);
    if (this.ligado) this.atualizar();
    return this;
  }

  definirGrandeza(chave) {
    if (!chave) return this;
    this.grandeza = String(chave);
    if (this.ligado) this.atualizar();
    return this;
  }

  /** Liga ou desliga cada desenho. `porticos` limita em quantos pórticos desenhar. */
  definirCamadas(camadas = {}) {
    for (const k of ['diagramas', 'deformada', 'cargas']) {
      if (k in camadas) this.camadas[k] = !!camadas[k];
    }
    if ('porticos' in camadas && finito(camadas.porticos)) {
      this.limitePorticos = Math.max(0, Math.floor(Number(camadas.porticos)));
    }
    if (this.ligado) this.atualizar();
    return this;
  }

  /** Exagero da deformada. `null` volta para a escala sugerida pelo servidor. */
  definirEscalaDeformada(fator) {
    const f = Number(fator);
    this.fatorDeformada = Number.isFinite(f) && f > 0 ? f : null;
    if (this.ligado) this.atualizar();
    return this;
  }

  /** Exagero em uso agora. */
  escalaDeformada() {
    if (this.fatorDeformada) return this.fatorDeformada;
    const reg = this._deformadaAtual();
    const s = reg && Number(reg.escala_sugerida);
    return Number.isFinite(s) && s > 0 ? s : EXAGERO_PADRAO;
  }

  // ------------------------------------------------------- faixa, cor, valor

  /**
   * Faixa da grandeza atual. O aproveitamento tem escala fixa de 0 a 1,2, para a cor de
   * uma peça querer dizer sempre a mesma coisa; M, V e N vão de 0 ao maior valor em
   * módulo entre os elementos — é o que pinta as peças, e é o que a legenda mostra.
   */
  faixa() {
    const unidades = (this.dados && this.dados.unidades) || {};
    if (this.grandeza === 'aproveitamento') {
      return { min: 0, max: APROVEITAMENTO_MAX, unidade: '', percentual: true };
    }
    let max = 0;
    for (const el of this._porElemento.values()) {
      const v = this._valorDoElemento(el);
      if (v !== null) max = Math.max(max, v);
    }
    return { min: 0, max: max || 1, unidade: unidades[this.grandeza] || '', percentual: false };
  }

  /** Cor de uma posição de 0 a 1 dentro da faixa. A legenda usa exatamente isto. */
  cores(n) {
    const k = entre(finito(n) ? Number(n) : 0, 0, 1);
    return this.grandeza === 'aproveitamento'
      ? amostrarRampa(RAMPA_APROVEITAMENTO, k * APROVEITAMENTO_MAX)
      : amostrarRampa(RAMPA_ESFORCO, k);
  }

  /** Valor da grandeza atual para uma entidade do documento, ou null. */
  valorDaEntidade(ent) {
    if (!ent || !this.pronto) return null;
    const nome = elementoDaEntidade(ent);
    if (!nome) return null;
    return this._valorDoElemento(this._porElemento.get(nome));
  }

  /**
   * Os maiores da grandeza atual, do maior para o menor.
   *
   * A lista é por elemento, não por peça: num galpão os dezoito pilares são o mesmo
   * elemento verificado uma vez, e repetir dezoito linhas iguais esconderia a viga. Vai
   * junto o id de uma peça representativa (e `ids` com todas), para o painel poder
   * selecionar ou dar zoom no que a linha aponta.
   */
  ranking(n = 10) {
    if (!this.pronto) return [];
    const porElemento = this._entidadesPorElemento();
    const linhas = [];
    for (const el of this._porElemento.values()) {
      const valor = this._valorDoElemento(el);
      if (valor === null) continue;
      const ents = porElemento.get(el.nome) || [];
      const primeira = ents[0] || null;
      const aprov = Number(el.aproveitamento);
      linhas.push({
        id: primeira ? primeira.id : '',
        ids: ents.map(e => e.id),
        marca: (primeira && primeira.atributos && (primeira.atributos.marca ||
                (primeira.atributos.marcas && primeira.atributos.marcas.posicao))) || el.marca || el.nome || '',
        rotulo: el.nome_producao || el.nome || '',
        elemento: el.nome,
        perfil: el.perfil || '',
        valor,
        aproveitamento: Number.isFinite(aprov) ? aprov : null,
        ok: el.ok !== false,
        governa: el.governa || '',
        pecas: ents.length,
      });
    }
    linhas.sort((a, b) => b.valor - a.valor);
    return n > 0 ? linhas.slice(0, n) : linhas;
  }

  _valorDoElemento(el) {
    if (!el) return null;
    if (this.grandeza === 'aproveitamento') {
      const v = Number(el.aproveitamento);
      return Number.isFinite(v) ? v : null;
    }
    const valores = el.valores || {};
    // Sem a combinação pedida, a envoltória é a resposta honesta: é o pior caso.
    const reg = valores[this.combinacao] || valores.envoltoria || null;
    const v = reg ? Number(reg[this.grandeza]) : NaN;
    return Number.isFinite(v) ? Math.abs(v) : null;      // o mapa lê módulo
  }

  /** Cor de uma peça, ou null quando ela não tem valor (a cena a deixa cinza). */
  _corDaEntidade(ent) {
    const v = this.valorDaEntidade(ent);
    if (v === null) return null;
    const f = this._faixa || this.faixa();
    const n = f.max > f.min ? (v - f.min) / (f.max - f.min) : 0;
    return this.cores(n);
  }

  /** Peças do documento agrupadas pelo nome do elemento em `atributos.elemento`. */
  _entidadesPorElemento() {
    const mapa = new Map();
    if (!this.documento) return mapa;
    for (const ent of this.documento.entidades.values()) {
      const nome = elementoDaEntidade(ent);
      if (!nome) continue;
      if (!mapa.has(nome)) mapa.set(nome, []);
      mapa.get(nome).push(ent);
    }
    return mapa;
  }

  // ------------------------------------------------------- ligar e desligar

  /** Pinta as peças e desenha. Só daqui em diante a cena muda. */
  ligar() {
    if (this.ligado) return this;
    this.ligado = true;
    this._montarGrupo();
    this._ouvirDocumento();
    this.atualizar();
    return this;
  }

  /** Devolve a cena ao estado anterior. */
  desligar() {
    if (!this.ligado) return this;
    this.ligado = false;
    if (this._desinscrever) { this._desinscrever(); this._desinscrever = null; }
    // Primeiro as cores: `definirCorPorValor(null)` já repinta tudo e reaplica o realce
    // da seleção, então nada fica azul-esverdeado por engano.
    if (this.cena) this.cena.definirCorPorValor(null);
    this._descartarGrupo();
    this._faixa = null;
    if (this.cena) this.cena.pedirQuadro();
    return this;
  }

  /** Refaz cores e desenhos com o estado atual. Desligado, não faz nada. */
  atualizar() {
    if (!this.ligado || !this.cena) return this;
    this._montarGrupo();
    this._faixa = this.pronto ? this.faixa() : null;
    this.cena.definirCorPorValor(this.pronto ? (ent) => this._corDaEntidade(ent) : null);
    this._desenhar();
    this.cena.pedirQuadro();
    return this;
  }

  /** Solta tudo: usado se o editor descartar o mapa. */
  descartar() {
    this.desligar();
    this.dados = null;
    this._porElemento = new Map();
    this._barras = new Map();
  }

  // ------------------------------------------------------- grupo de desenhos

  _montarGrupo() {
    if (!this.cena || !this.cena.raiz) return;
    if (!this.grupo) {
      this.grupo = new THREE.Group();
      this.grupo.name = 'mapa-esforcos';
      this.grupo.userData.temporario = true;   // não é entidade do documento
    }
    // `cena.reconstruirTudo` preserva só o grupo de prévia; o nosso precisa voltar.
    if (this.grupo.parent !== this.cena.raiz) this.cena.raiz.add(this.grupo);
  }

  _descartarGrupo() {
    if (!this.grupo) return;
    this._limparDesenhos();
    if (this.grupo.parent) this.grupo.parent.remove(this.grupo);
    this.grupo = null;
  }

  /** Esvazia o grupo descartando geometria, material e textura de rótulo. */
  _limparDesenhos() {
    if (!this.grupo) return;
    const geometrias = new Set(), materiais = new Set();
    for (const filho of this.grupo.children.slice()) {
      this.grupo.remove(filho);
      filho.traverse(o => {
        if (o.geometry) geometrias.add(o.geometry);
        if (o.material) {
          for (const m of (Array.isArray(o.material) ? o.material : [o.material])) materiais.add(m);
        }
      });
    }
    // Materiais e geometrias são compartilhados entre desenhos: o Set descarta uma vez.
    for (const g of geometrias) if (g.dispose) g.dispose();
    for (const m of materiais) {
      if (m.map && m.map.dispose) m.map.dispose();
      if (m.dispose) m.dispose();
    }
  }

  _ouvirDocumento() {
    if (this._desinscrever || !this.documento) return;
    this._desinscrever = this.documento.aoMudar(({ acao }) => {
      if (!this.ligado) return;
      // Modelo trocado: a cena refez a raiz e levou o nosso grupo junto.
      if (acao === 'tudo') this.atualizar();
      else this._montarGrupo();
    });
  }

  // ------------------------------------------------------------- os desenhos

  _desenhar() {
    this._limparDesenhos();
    this._tipicas = [];
    if (!this.pronto || !this.grupo) return;
    const xs = this._xsDesenhados();
    if (!xs.length) return;
    try {
      if (this.camadas.diagramas) this._desenharDiagramas(xs);
      if (this.camadas.deformada) this._desenharDeformada(xs);
      if (this.camadas.cargas) this._desenharCargas(xs);
      if (this.camadas.diagramas || this.camadas.deformada || this.camadas.cargas) {
        this._rotularPorticos(xs);
      }
    } catch (e) {
      // Um dado torto não pode derrubar o editor: o mapa fica sem desenho e avisa.
      console.warn('mapa de esforços: desenho interrompido —', e);
    }
  }

  /**
   * Em quais posições x repetir o desenho do pórtico.
   *
   * O pórtico vem descrito uma vez, no plano x = 0, e se repete em cada x de
   * `portico.xs_mm` — num galpão de 40 m são nove, todos iguais. Por padrão desenhamos
   * num só, o primeiro, e o rótulo diz qual é ("Pórtico 1 · x = 0,0 m").
   *
   * A razão é de leitura, e apareceu na conferência por captura: o diagrama é uma
   * figura plana, e é de frente para o pórtico que ele se lê. Nessa vista as cópias se
   * projetam exatamente umas sobre as outras — três pórticos davam três fitas empilhadas
   * e três rótulos sobrepostos, sem acrescentar nada, já que os pórticos são iguais.
   *
   * `definirCamadas({porticos: 3})` volta a espalhar pelo comprimento (primeiro, meio e
   * último); `{porticos: 0}` desenha em todos.
   */
  _xsDesenhados() {
    const xs = (((this.dados || {}).portico || {}).xs_mm || [])
      .map(Number).filter(Number.isFinite);
    if (!xs.length) return [0];
    const lim = this.limitePorticos;
    if (!lim || xs.length <= lim) return xs;
    if (lim === 1) return [xs[0]];
    const saida = [];
    for (let i = 0; i < lim; i++) saida.push(xs[Math.round(i * (xs.length - 1) / (lim - 1))]);
    return [...new Set(saida)];
  }

  /**
   * Quais pórticos estão sendo desenhados, para o painel poder dizê-lo em palavras:
   * [{indice (1 é o primeiro), x_mm}]. Sem isto o usuário vê três diagramas e não sabe
   * de onde eles saíram.
   */
  porticosDesenhados() {
    if (!this.pronto) return [];
    const todos = (((this.dados || {}).portico || {}).xs_mm || []).map(Number);
    return this._xsDesenhados().map(x => ({
      indice: todos.findIndex(t => Math.abs(t - x) < 1) + 1,
      x_mm: x,
    }));
  }

  /**
   * As peças típicas desenhadas agora (terça, longarina), para o painel poder dizer o
   * que está mostrando: [{elemento, marca, id, modelo, vao_m, caso, grandeza, valor}].
   * Vazio quando a camada de diagramas está desligada.
   */
  pecasTipicasDesenhadas() { return this._tipicas.map(t => ({ ...t })); }

  /**
   * Qual pórtico está em exibição, acima da cumeeira.
   *
   * Com mais de um, vai **um resumo só**, sobre o primeiro. A razão é a projeção: de
   * frente para o pórtico — a vista em que o diagrama se lê — todos os pórticos caem no
   * mesmo ponto da tela. Um nome por pórtico virava uma pilha de nove caixas ilegíveis
   * no meio da imagem; e guardar só as duas pontas não resolve, porque essas duas se
   * sobrepõem exatamente uma à outra. A lista completa continua em
   * `porticosDesenhados()`, que é por onde o painel a mostra em texto.
   */
  _rotularPorticos(xs) {
    const todos = (((this.dados || {}).portico || {}).xs_mm || []).map(Number);
    if (todos.length <= 1 || !xs.length) return;
    const alto = this._pontoMaisAlto();
    const cor = this._cor(CORES_DESENHO.referencia);
    // Bem acima da cumeeira: no meio do telhado o rótulo caía em cima das cotas de
    // pico da viga.
    const acima = 0.18 * this._tamanhoDoPortico();
    const indice = (x) => todos.findIndex(t => Math.abs(t - x) < 1) + 1;
    const texto = xs.length === 1
      ? `Pórtico ${indice(xs[0]) || '—'} · x = ${numero(xs[0] / 1000, 1)} m`
      : `${xs.length} pórticos · x = ${numero(xs[0] / 1000, 1)} a ` +
        `${numero(xs[xs.length - 1] / 1000, 1)} m`;
    this.grupo.add(this._rotulo(texto, [alto[0] + xs[0], alto[1], alto[2] + acima], cor));
  }

  /** Ponto mais alto do pórtico (a cumeeira), no plano x = 0. */
  _pontoMaisAlto() {
    let melhor = [0, 0, 0];
    for (const b of this._barras.values()) {
      for (const p of [b.ini, b.fim]) if (ponto3(p) && p[2] > melhor[2]) melhor = p;
    }
    return melhor;
  }

  /** Maior dimensão do pórtico em mm (vão ou altura): a régua de todos os desenhos. */
  _tamanhoDoPortico() {
    if (this._tamanho) return this._tamanho;
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    const engolir = (p) => {
      if (!ponto3(p)) return;
      for (let i = 0; i < 3; i++) {
        if (p[i] < min[i]) min[i] = p[i];
        if (p[i] > max[i]) max[i] = p[i];
      }
    };
    for (const b of this._barras.values()) { engolir(b.ini); engolir(b.fim); }
    for (const n of (((this.dados || {}).portico || {}).nos || [])) engolir(n && n.p);
    const dx = max[0] - min[0], dy = max[1] - min[1], dz = max[2] - min[2];
    // tesoura importada pode estar no plano x·z: a régua é a maior dimensão do desenho
    this._tamanho = Number.isFinite(dy) ? Math.max(dx, dy, dz, 1000) : 10000;
    return this._tamanho;
  }

  // ---- diagramas de M, V e N ----

  /**
   * Séries de uma barra para uma grandeza, na combinação atual.
   * Uma combinação simples traz `M`; a envoltória traz `M_max` e `M_min`.
   */
  _seriesDaBarra(barra, grandeza) {
    const d = (barra.diagramas || {})[this.combinacao] || {};
    const s = (d.s || []).map(Number);
    const saida = [];
    for (const [campo, nome] of [[grandeza, ''], [grandeza + '_max', 'máx'],
                                 [grandeza + '_min', 'mín']]) {
      const v = d[campo];
      if (!Array.isArray(v) || v.length !== s.length || s.length < 2) continue;
      // Amostra torta (null, NaN) invalidaria a geometria inteira: fora.
      const pares = s.map((x, i) => [Number(x), Number(v[i])])
                     .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
      if (pares.length < 2) continue;
      saida.push({ nome, s: pares.map(p => entre(p[0], 0, 1)), v: pares.map(p => p[1]) });
    }
    return saida;
  }

  /** Maior valor em módulo entre todas as barras, para as fitas compartilharem escala. */
  _picoDoDiagrama(grandeza) {
    let pico = 0;
    for (const barra of this._barras.values()) {
      for (const serie of this._seriesDaBarra(barra, grandeza)) {
        for (const v of serie.v) pico = Math.max(pico, Math.abs(v));
      }
    }
    return pico;
  }

  _desenharDiagramas(xs) {
    // Na leitura por aproveitamento não há diagrama de aproveitamento: mostramos o
    // momento, que é o que costuma governar o pórtico.
    const g = GRANDEZAS_DE_DIAGRAMA.includes(this.grandeza) ? this.grandeza : 'M';
    const pico = this._picoDoDiagrama(g);
    if (!pico) return;
    const escala = ALTURA_FITA * this._tamanhoDoPortico() / pico;
    const unidade = ((this.dados.unidades || {})[g]) || '';
    const cor = this._cor(CORES_DESENHO[g]);

    const posicoes = [], linhas = [], rotulos = [];
    for (const dx of xs) {
      const primeiro = dx === xs[0];
      for (const barra of this._barras.values()) {
        for (const serie of this._seriesDaBarra(barra, g)) {
          this._fitaDaSerie(barra, serie, escala, dx, posicoes, linhas);
          // O texto do pico só no primeiro pórtico: repetir a mesma cota em cada
          // pórtico é o que transforma a tela num emaranhado.
          if (!primeiro) continue;
          const i = indiceDoPico(serie.v);
          // Só o pico que significa alguma coisa ganha texto: cotar também as séries
          // pequenas encheria o pórtico de números e esconderia justamente os grandes.
          if (i < 0 || Math.abs(serie.v[i]) < pico * 0.25) continue;
          const p = this._pontoDaFita(barra, serie, i, escala, dx);
          const nrm = normalizado(barra.normal);
          // Afasta o texto da borda da fita, no sentido em que a fita cresceu: colado
          // nela, o número do máximo e o do mínimo se encavalavam no joelho.
          const recuo = 0.045 * this._tamanhoDoPortico() * Math.sign(serie.v[i] || 1);
          rotulos.push({
            texto: `${numero(serie.v[i], 1)} ${unidade}`.trim(),
            p: somar(p, escalarVet(nrm, recuo)),
          });
        }
      }
    }
    if (posicoes.length) this.grupo.add(this._malha(posicoes, cor, 0.3));
    if (linhas.length) this.grupo.add(this._linhas(linhas, cor, 0.95));
    for (const r of rotulos) this.grupo.add(this._rotulo(r.texto, r.p, cor));
    this._desenharTipicas(xs, g, unidade);
  }

  /**
   * O diagrama das peças que não estão no pórtico — terça e longarina.
   *
   * O servidor manda em `elementos[nome].diagrama` o esforço de uma peça isolada (uma
   * viga biapoiada de um vão). Desenhamos numa **peça típica por elemento**, uma no
   * desenho inteiro, junto ao primeiro pórtico em exibição: são 272 terças iguais, e
   * desenhar todas apagaria o galpão.
   *
   * Duas coisas dizem, sem ler o rótulo, que esta fita está noutra régua que a do
   * pórtico: ela é bem menor (um décimo do pórtico, contra um sexto) e o contorno é
   * tracejado. As duas escalas têm de ser diferentes mesmo — 6 kN·m de uma terça na
   * régua dos 273 kN·m de um pilar seriam um risco invisível —, e é justamente por isso
   * que a diferença precisa estar à vista.
   */
  _desenharTipicas(xs, grandeza, unidade) {
    const comDiagrama = [];
    for (const el of this._porElemento.values()) {
      const serie = this._serieTipica(el.diagrama, grandeza);
      if (serie) comDiagrama.push({ el, serie });
    }
    if (!comDiagrama.length) return;
    let pico = 0;
    for (const { serie } of comDiagrama) {
      for (const v of serie.v) pico = Math.max(pico, Math.abs(v));
    }
    if (!pico) return;

    const tam = this._tamanhoDoPortico();
    const escala = 0.10 * tam / pico;        // régua própria, menor que a do pórtico
    const cor = this._cor(CORES_DESENHO[grandeza]);
    const porElemento = this._entidadesPorElemento();
    const posicoes = [], linhas = [];

    // Uma peça típica por elemento no desenho inteiro, no primeiro pórtico em exibição
    // — e não uma por pórtico. Ela é típica porque representa todas: repetir a mesma
    // fita de terça em três ou nove vãos não acrescenta nada e multiplica o rótulo, que
    // na vista de frente se sobrepunha e atravessava a tela.
    const dx = xs[0];
    for (const { el, serie } of comDiagrama) {
      const peca = this._pecaTipica(porElemento.get(el.nome), dx);
      if (!peca) continue;
      // A fita sai perpendicular à peça, no plano vertical que a contém.
      const barra = { ini: peca.inicio, fim: peca.fim,
                      normal: this._perpendicularVertical(subtrair(peca.fim, peca.inicio)) };
      this._fitaDaSerie(barra, serie, escala, 0, posicoes, linhas);

      const i = indiceDoPico(serie.v);
      if (i < 0) continue;
      const d = el.diagrama;
      const marca = (peca.atributos && peca.atributos.marca) || '';
      // Na cena, só de que peça é a fita e quanto vale o pico. O modelo, o vão e o caso
      // que governa vivem no painel, em `pecasTipicasDesenhadas()` — repeti-los aqui
      // fazia o rótulo mais comprido da tela.
      const texto = `${el.nome}${marca ? ' ' + marca : ''} típica · ` +
                    `${grandeza} ${numero(serie.v[i], 1)} ${unidade}`.trim();
      const p = this._pontoDaFita(barra, serie, i, escala, 0);
      this.grupo.add(this._rotulo(texto, somar(p, escalarVet(barra.normal, 0.03 * tam)), cor));

      this._tipicas.push({
        elemento: el.nome, marca, id: peca.id,
        modelo: d.modelo || '', caso: d.caso || '',
        vao_m: finito(d.vao_m) ? Number(d.vao_m) : null,
        grandeza, unidade, valor: serie.v[i],
        x_mm: (peca.inicio[0] + peca.fim[0]) / 2,
      });
    }
    if (posicoes.length) this.grupo.add(this._malha(posicoes, cor, 0.18));
    if (linhas.length) this.grupo.add(this._linhasTracejadas(linhas, cor, 0.9));
  }

  /** Série do diagrama de uma peça típica. Sem a grandeza (N), não há o que desenhar. */
  _serieTipica(diagrama, grandeza) {
    if (!diagrama || typeof diagrama !== 'object') return null;
    const s = (diagrama.s || []).map(Number);
    const v = diagrama[grandeza];
    if (!Array.isArray(v) || v.length !== s.length || s.length < 2) return null;
    const pares = s.map((x, i) => [Number(x), Number(v[i])])
                   .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
    if (pares.length < 2) return null;
    return { nome: '', s: pares.map(p => entre(p[0], 0, 1)), v: pares.map(p => p[1]) };
  }

  /**
   * A peça do elemento mais próxima do pórtico desenhado — para o usuário ver o
   * diagrama da terça junto com o do pórtico, e não no outro extremo do galpão.
   * Empate (as terças de um mesmo vão) fica com a mais alta, que é a menos escondida.
   */
  _pecaTipica(lista, dx) {
    let melhor = null, perto = Infinity, alto = -Infinity;
    for (const ent of (lista || [])) {
      if (!ponto3(ent.inicio) || !ponto3(ent.fim)) continue;
      const cx = Math.abs((ent.inicio[0] + ent.fim[0]) / 2 - dx);
      const cz = (ent.inicio[2] + ent.fim[2]) / 2;
      if (cx < perto - 1 || (cx <= perto + 1 && cz > alto)) {
        melhor = ent; perto = Math.min(perto, cx); alto = cz;
      }
    }
    return melhor;
  }

  /**
   * Perpendicular à peça, no plano vertical que a contém, apontando para cima: é o que
   * faz a fita de uma terça sair perpendicular à peça em vez de deitada na horizontal.
   * Para uma peça vertical o plano é indefinido, e aí serve qualquer horizontal.
   */
  _perpendicularVertical(direcao) {
    const t = normalizado(direcao);
    const u = subtrair([0, 0, 1], escalarVet(t, t[2]));     // z menos a parte ao longo de t
    return comprimento(u) < 1e-6 ? [0, 1, 0] : normalizado(u);
  }

  /** Ponto da borda da fita na amostra `i`. */
  _pontoDaFita(barra, serie, i, escala, dx) {
    const base = aoLongo(barra.ini, barra.fim, serie.s[i]);
    const nrm = normalizado(barra.normal);
    return [base[0] + dx + nrm[0] * serie.v[i] * escala,
            base[1] + nrm[1] * serie.v[i] * escala,
            base[2] + nrm[2] * serie.v[i] * escala];
  }

  /**
   * Fita de uma série: a faixa entre o eixo da barra e a curva do valor, mais o
   * contorno e os traços de cota de tantas em tantas amostras — o desenho de diagrama
   * que o projetista conhece do papel. A `normal` da barra é a direção do positivo.
   */
  _fitaDaSerie(barra, serie, escala, dx, posicoes, linhas) {
    const n = serie.s.length;
    const base = [], topo = [];
    for (let i = 0; i < n; i++) {
      const p = aoLongo(barra.ini, barra.fim, serie.s[i]);
      p[0] += dx;
      base.push(p);
      topo.push(this._pontoDaFita(barra, serie, i, escala, dx));
    }
    for (let i = 0; i < n - 1; i++) {
      posicoes.push(...base[i], ...topo[i], ...topo[i + 1]);
      posicoes.push(...base[i], ...topo[i + 1], ...base[i + 1]);
      linhas.push(...topo[i], ...topo[i + 1]);           // contorno da curva
    }
    linhas.push(...base[0], ...topo[0]);                 // fechamento nas pontas
    linhas.push(...base[n - 1], ...topo[n - 1]);
    const passo = Math.max(1, Math.round(n / 12));       // traços de cota
    for (let i = passo; i < n - 1; i += passo) linhas.push(...base[i], ...topo[i]);
  }

  // ---- deformada ----

  _deformadaAtual() {
    const todas = (this.dados && this.dados.deformada) || {};
    if (todas[this.combinacao]) return todas[this.combinacao];
    // A envoltória não tem deformada própria: mostramos a da primeira combinação que
    // tiver, que é melhor do que não mostrar nada.
    const chaves = Object.keys(todas);
    return chaves.length ? todas[chaves[0]] : null;
  }

  _desenharDeformada(xs) {
    const reg = this._deformadaAtual();
    if (!reg || !Array.isArray(reg.barras) || !reg.barras.length) return;
    const fator = this.escalaDeformada();
    const cor = this._cor(CORES_DESENHO.deformada);
    const corRef = this._cor(CORES_DESENHO.referencia);
    const referencia = [], faixa = [];

    for (const dx of xs) {
      const primeiro = dx === xs[0];
      for (const item of reg.barras) {
        const barra = this._barras.get(item && item.rotulo);
        if (!barra) continue;
        const { base, pontos } = this._pontosDeformados(barra, item, fator, dx);
        if (pontos.length < 2) continue;
        this.grupo.add(this._linha(pontos, cor, 1));
        // Faixa entre o eixo original e o deslocado. Uma linha de um pixel se perde em
        // cima do modelo — e o que se quer ver é justamente o afastamento entre os dois,
        // que como área aparece mesmo de longe.
        for (let i = 0; i < pontos.length - 1; i++) {
          faixa.push(...base[i], ...pontos[i], ...pontos[i + 1]);
          faixa.push(...base[i], ...pontos[i + 1], ...base[i + 1]);
        }
        referencia.push(...somar(barra.ini, [dx, 0, 0]), ...somar(barra.fim, [dx, 0, 0]));
        if (!primeiro) continue;
        const marca = this._marcaDoTopo(barra, item, pontos);
        if (marca) this.grupo.add(this._rotulo(marca.texto, marca.p, cor));
      }
    }
    if (faixa.length) this.grupo.add(this._malha(faixa, cor, 0.22));
    // Eixo original em traço apagado: sem ele, com a estrutura pintada por valor, não
    // se enxerga de onde a deformada saiu.
    if (referencia.length) this.grupo.add(this._linhas(referencia, corRef, 0.45));
  }

  /** Pontos do eixo original e do eixo deslocado, amostra a amostra. */
  _pontosDeformados(barra, item, fator, dx) {
    const s = (item.s || []).map(Number);
    const d = item.d || [];
    const base = [], pontos = [];
    for (let i = 0; i < s.length; i++) {
      if (!Number.isFinite(s[i]) || !ponto3(d[i])) continue;
      const p = aoLongo(barra.ini, barra.fim, entre(s[i], 0, 1));
      p[0] += dx;
      base.push(p);
      pontos.push([p[0] + d[i][0] * fator,
                   p[1] + d[i][1] * fator,
                   p[2] + d[i][2] * fator]);
    }
    return { base, pontos };
  }

  /**
   * Cota do deslocamento do topo do pilar — o número que decide o estado limite de
   * serviço. Quando o servidor manda `servico.deslocamento`, é esse valor que aparece,
   * com o limite ao lado; senão, o deslocamento horizontal da própria deformada.
   */
  _marcaDoTopo(barra, item, pontos) {
    const ehPilar = /pilar/i.test(barra.rotulo || '') || /pilar/i.test(barra.elemento || '');
    if (!ehPilar) return null;
    const d = item.d || [];
    let melhor = -1, maior = -1;
    for (let i = 0; i < d.length; i++) {
      if (!ponto3(d[i])) continue;
      const h = Math.hypot(d[i][0], d[i][1]);          // o que importa é o horizontal
      if (h > maior) { maior = h; melhor = i; }
    }
    if (melhor < 0 || maior <= 0) return null;
    const serv = (this.servico && this.servico.deslocamento) || null;
    const u = (this.dados.unidades || {}).u || 'cm';
    let texto = `Δ topo ${numero(maior / 10, 1)} ${u}`;   // mm -> cm
    if (serv && finito(serv.u_cm)) {
      texto = `Δ topo ${numero(serv.u_cm, 1)} ${u}`;
      if (finito(serv.limite_cm)) {
        texto += ` (lim. ${numero(serv.limite_cm, 1)} ${u}`;
        texto += serv.criterio ? ` — ${serv.criterio})` : ')';
      }
    }
    // Joga a cota para fora do galpão: no topo do pilar ela disputava lugar com o valor
    // da carga e com o pico do momento no joelho, que moram todos nessa mesma altura.
    const i = Math.min(melhor, pontos.length - 1);
    const tam = this._tamanhoDoPortico();
    const fora = Math.sign((barra.ini[1] || 0) - this._pontoMaisAlto()[1]) || 1;
    return { texto, p: somar(pontos[i], [0, fora * 0.07 * tam, 0.04 * tam]) };
  }

  // ---- cargas ----

  _cargasAtuais() {
    const todas = (this.dados && this.dados.cargas) || {};
    const lista = todas[this.combinacao] || null;
    if (Array.isArray(lista)) return lista;
    const chaves = Object.keys(todas);
    return chaves.length && Array.isArray(todas[chaves[0]]) ? todas[chaves[0]] : [];
  }

  /**
   * Para onde a carga aponta: o `eixo` da carga, no sentido do sinal de q.
   *
   * O `eixo` é unitário e já vem nas coordenadas do editor, inclusive no caso
   * `perpendicular` — que é o **oposto** da `normal` dos diagramas, porque a normal
   * aponta para a face tracionada pelo momento positivo e a carga perpendicular
   * positiva empurra para o outro lado. Como o servidor resolve isso, aqui não se
   * interpreta nome de direção nem descrição: o desenho é `q · eixo`, e pronto.
   *
   * A leitura pela `descricao` fica só como reserva, para um payload antigo sem `eixo`
   * (naquele formato os eixos vinham nomeados no quadro plano, onde `global_y` é a
   * vertical do modelo).
   */
  _direcaoDaCarga(carga, barra) {
    const sinal = Number(carga.q_kN_m) < 0 ? -1 : 1;
    if (ponto3(carga.eixo) && comprimento(carga.eixo) > 1e-6) {
      return escalarVet(normalizado(carga.eixo), sinal);
    }
    const VERTICAL = [0, 0, 1], HORIZONTAL = [0, 1, 0];
    const dito = String(carga.descricao || carga.rotulo || '').toLowerCase();
    const letra = String(carga.direcao || '').trim().toLowerCase().slice(-1);
    let base;
    if (dito.includes('vertical')) base = VERTICAL;
    else if (dito.includes('horizontal')) base = HORIZONTAL;
    else if (letra === 'y') base = VERTICAL;
    else if (letra === 'x') base = HORIZONTAL;
    else base = normalizado(barra.normal);
    return escalarVet(normalizado(base), sinal);
  }

  _desenharCargas(xs) {
    const lista = this._cargasAtuais().filter(c => c && this._barras.get(c.barra) &&
                                                   finito(c.q_kN_m) && Number(c.q_kN_m) !== 0);
    if (!lista.length) return;
    const qmax = Math.max(...lista.map(c => Math.abs(Number(c.q_kN_m))));
    const tam = this._tamanhoDoPortico();
    const unidade = (this.dados.unidades || {}).q || 'kN/m';
    const cor = this._cor(CORES_DESENHO.carga);
    const segmentos = [], rotulos = [];

    for (const dx of xs) {
      const primeiro = dx === xs[0];
      for (const carga of lista) {
        const barra = this._barras.get(carga.barra);
        const q = Number(carga.q_kN_m);
        const dir = this._direcaoDaCarga(carga, barra);
        // Comprimento da seta: um mínimo para ser vista, mais a parte proporcional.
        const alcance = tam * (0.03 + 0.055 * (Math.abs(q) / (qmax || 1)));
        const eixo = normalizado(subtrair(barra.fim, barra.ini));
        const L = comprimento(subtrair(barra.fim, barra.ini));
        const n = entre(Math.round(L / 1200), 4, 10);
        const cabeca = Math.min(alcance * 0.32, tam * 0.014);
        let primeiroRabo = null, ultimoRabo = null;

        for (let i = 0; i <= n; i++) {
          const p = aoLongo(barra.ini, barra.fim, i / n);
          p[0] += dx;
          const rabo = subtrair(p, escalarVet(dir, alcance));
          segmentos.push(...rabo, ...p);                       // haste
          // Ponta em V, no plano da haste com o eixo da barra: duas linhas bastam, e
          // ficam nítidas em qualquer zoom (um cone viraria borrão e peso).
          for (const lado of [1, -1]) {
            const braco = somar(escalarVet(dir, -cabeca * 0.9),
                                escalarVet(eixo, lado * cabeca * 0.45));
            segmentos.push(...p, ...somar(p, braco));
          }
          if (i === 0) primeiroRabo = rabo;
          if (i === n) ultimoRabo = rabo;
        }
        if (primeiroRabo && ultimoRabo) segmentos.push(...primeiroRabo, ...ultimoRabo);
        if (!primeiro || !primeiroRabo) continue;
        const meio = escalarVet(somar(primeiroRabo, ultimoRabo), 0.5);
        // A descrição já vem pronta em português ("vertical", "horizontal", "vertical,
        // por projeção horizontal"): só a primeira palavra cabe ao lado do valor.
        const dito = String(carga.descricao || carga.rotulo || '').split(',')[0].trim();
        rotulos.push({
          texto: `${numero(Math.abs(q), 2)} ${unidade}${dito ? ' · ' + dito : ''}`,
          p: subtrair(meio, escalarVet(dir, tam * 0.02)),
        });
      }
    }
    if (segmentos.length) this.grupo.add(this._linhas(segmentos, cor, 0.95));
    for (const r of rotulos) this.grupo.add(this._rotulo(r.texto, r.p, cor));
  }

  // ------------------------------------------------------ fábricas de desenho
  //
  // Tudo com `depthTest: false` e `renderOrder` alto: o mapa é uma leitura sobreposta,
  // e com telha e fechamento no modelo o diagrama ficaria escondido dentro do galpão.

  /** Ajusta uma cor de desenho ao tema, para não sumir no fundo. */
  _cor(cor) {
    return this.cena && this.cena.escuro ? misturar(cor, '#f2f6ff', 0.24) : cor;
  }

  _malha(posicoes, cor, opacidade) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(posicoes, 3));
    g.computeVertexNormals();
    const m = new THREE.MeshBasicMaterial({
      color: new THREE.Color(cor), transparent: true, opacity: opacidade,
      side: THREE.DoubleSide, depthTest: false, depthWrite: false,
    });
    const malha = new THREE.Mesh(g, m);
    malha.renderOrder = 900;
    malha.raycast = () => {};
    return malha;
  }

  _linhas(posicoes, cor, opacidade) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(posicoes, 3));
    const m = new THREE.LineBasicMaterial({
      color: new THREE.Color(cor), transparent: true, opacity: opacidade,
      depthTest: false, depthWrite: false,
    });
    const obj = new THREE.LineSegments(g, m);
    obj.renderOrder = 950;
    obj.raycast = () => {};
    return obj;
  }

  /** Como `_linhas`, mas tracejada: é o contorno da fita que está noutra escala. */
  _linhasTracejadas(posicoes, cor, opacidade) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(posicoes, 3));
    const tam = this._tamanhoDoPortico();
    const m = new THREE.LineDashedMaterial({
      color: new THREE.Color(cor), transparent: true, opacity: opacidade,
      depthTest: false, depthWrite: false,
      dashSize: tam * 0.006, gapSize: tam * 0.004,
    });
    const obj = new THREE.LineSegments(g, m);
    obj.computeLineDistances();
    obj.renderOrder = 950;
    obj.raycast = () => {};
    return obj;
  }

  _linha(pontos, cor, opacidade) {
    const pos = [];
    for (const p of pontos) pos.push(p[0], p[1], p[2]);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    const m = new THREE.LineBasicMaterial({
      color: new THREE.Color(cor), transparent: true, opacity: opacidade,
      depthTest: false, depthWrite: false,
    });
    const obj = new THREE.Line(g, m);
    obj.renderOrder = 950;
    obj.raycast = () => {};
    return obj;
  }

  /**
   * Texto na cena, como sprite sem atenuação de tamanho: o modelo está em milímetros e
   * o zoom varia muito, então o rótulo tem de ter tamanho de tela. Como o grupo mora
   * dentro de `cena.raiz`, que já escala mm → m, a escala do sprite é compensada por
   * 1/ESCALA — o mesmo cuidado que `editor.previa()` toma com os rótulos das prévias.
   */
  _rotulo(texto, posicao, cor) {
    const escuro = !!(this.cena && this.cena.escuro);
    const k = 2;                                  // desenha no dobro e deixa filtrar
    const cv = document.createElement('canvas');
    const fonte = `600 ${12 * k}px system-ui, "Segoe UI", sans-serif`;
    const medida = cv.getContext('2d');
    medida.font = fonte;
    cv.width = Math.max(2, Math.ceil(medida.measureText(texto).width) + 14 * k);
    cv.height = 20 * k;
    const ctx = cv.getContext('2d');
    ctx.font = fonte;
    ctx.fillStyle = escuro ? 'rgba(14,19,26,0.86)' : 'rgba(255,255,255,0.9)';
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.strokeStyle = cor;
    ctx.lineWidth = 1.4 * k;
    ctx.strokeRect(0.7 * k, 0.7 * k, cv.width - 1.4 * k, cv.height - 1.4 * k);
    ctx.fillStyle = cor;
    ctx.textBaseline = 'middle';
    ctx.fillText(texto, 7 * k, cv.height / 2);

    const tex = new THREE.CanvasTexture(cv);
    tex.minFilter = THREE.LinearFilter;
    tex.colorSpace = THREE.SRGBColorSpace;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, transparent: true, depthTest: false, sizeAttenuation: false }));
    const h = 0.019;                              // ~23 px de altura na tela
    sp.scale.set(h * (cv.width / cv.height), h, 1).multiplyScalar(1 / ESCALA);
    sp.position.set(posicao[0], posicao[1], posicao[2]);
    sp.renderOrder = 999;
    sp.raycast = () => {};
    return sp;
  }
}

/** Índice do maior valor em módulo de uma série. */
function indiceDoPico(v) {
  let idx = -1, maior = 0;
  for (let i = 0; i < v.length; i++) {
    if (Math.abs(v[i]) > maior) { maior = Math.abs(v[i]); idx = i; }
  }
  return idx;
}

export default MapaDeEsforcos;
