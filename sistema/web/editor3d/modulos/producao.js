// Métodos do editor 3D: a informação de produção feita à mão — numerar, conjunto, solda e converter em peça.
//
// Onda 1 da análise de 14/10/2026 (Projeto/ANALISES/Editor-3D/Ferramentas-que-faltam-editor-3D-2026-10-14.pdf): o
// detalhamento lê a marca de posição, a de conjunto e a solda de cada peça, e até aqui só os geradores escreviam isso —
// a peça desenhada à mão saía solta, sem elevação de conjunto e sem solda. Decisões do usuário (14/10): numerar só
// quando ele pede, travando a numeração depois da emissão; conjunto é comando próprio (o Agrupar só organiza a tela);
// solda à mão só onde ele quiser, o resto o detalhamento deduz.
//
// A conta mora no servidor (nucleo3d/producao.py), com o mesmo critério de "peça igual" do detalhamento; aqui só a
// seleção, os diálogos e o comando de desfazer (uma entrada por ação). O conjunto feito aqui grava `marcas.instancia`
// (uma por cópia) e `marcas.principal`; a solda fica gravada nas peças das duas posições, pela posição da outra
// (`atributos.soldas = {"P12": {tipo, perna, lados, local, intermitente…}}`).

import { el, numero } from '../editor.js';
import { clonar, criar, comprimentoDaBarra } from '../nucleo/documento.js';
import { Comando, ComandoAlterar, ComandoAdicionar, ComandoRemover, ComandoComposto } from '../nucleo/comandos.js';

const TIPOS_PECA = new Set(['IfcBeam', 'IfcColumn', 'IfcMember', 'IfcPlate', 'IfcPlateStandardCase',
  'IfcMemberStandardCase', 'IfcBeamStandardCase', 'IfcColumnStandardCase']);

const ACABAMENTOS = [['', '—'], ['pintura', 'pintura'], ['galvanizado a fogo', 'galvanizado a fogo'],
  ['sem acabamento', 'sem acabamento']];

const NOME_TIPO_SOLDA = { filete: 'filete', penetracao: 'penetração' };
const NOME_LOCAL = { fabrica: 'fábrica', obra: 'obra', nenhuma: 'sem solda' };
const NOME_ENCONTRO = { T: 'em T', 'sobreposição': 'sobreposta', contorno: 'em volta' };

/** A entidade vira posição no detalhamento? (barra, chapa, sólido de aço com tipo de peça; não cota, guia nem furo) */
export function ehPecaDeProducao(e) {
  if (!e) return false;
  const a = e.atributos || {};
  if (a.tipo === 'cota' || a.tipo === 'construcao' || a.furo) return false;
  if (e.tipo === 'barra' || e.tipo === 'chapa') return true;
  return e.tipo === 'solido' && TIPOS_PECA.has(a.tipo_ifc);
}

const marcasDe = (e) => (e && e.atributos && e.atributos.marcas) || {};

function novaInstancia() {
  return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/** Um documento só com estas entidades, para as contas que não precisam do modelo inteiro. */
function documentoDe(ents) {
  return { nome: 'seleção', unidade: 'mm', entidades: ents.map(e => clonar(e)), camadas: {}, materiais: {},
           projeto: {}, metadados: {} };
}

/** Os atributos com o "patch" do servidor (valor null apaga o campo). */
function comPatch(atributos, patch) {
  const a = clonar(atributos || {});
  for (const [k, v] of Object.entries(patch || {})) {
    if (v === null) delete a[k];
    else a[k] = v;
  }
  return a;
}

/** Guarda e volta um campo de documento.metadados (a trava da numeração). */
class ComandoMetadado extends Comando {
  constructor(chave, valor, rotulo) { super(rotulo); this.chave = chave; this.valor = valor; this.antes = undefined; }
  aplicar(doc) {
    if (this.antes === undefined) this.antes = clonar(doc.metadados[this.chave] ?? null);
    doc.metadados[this.chave] = clonar(this.valor);
    doc.notificar([], 'alterar');
  }
  desfazer(doc) {
    if (this.antes === null) delete doc.metadados[this.chave];
    else doc.metadados[this.chave] = clonar(this.antes);
    doc.notificar([], 'alterar');
  }
  ids() { return []; }
}

export class MetodosProducao {
  _pecasDaSelecao() { return this.selecao.entidades.filter(ehPecaDeProducao); }

  numeracaoTravada() {
    const n = this.documento.metadados && this.documento.metadados.numeracao;
    return !!(n && n.travada);
  }

  /** O comando que leva as respostas do servidor (e o que o editor já decidiu, `base`) aos atributos. */
  _comandoDeAtributos(patches, base, rotulo) {
    const mud = {};
    const ids = new Set([...Object.keys(base || {}), ...Object.keys(patches || {})]);
    for (const id of ids) {
      const e = this.documento.get(id);
      if (!e) continue;
      const inicio = base && base[id] ? base[id] : e.atributos;
      mud[id] = { atributos: comPatch(inicio, patches && patches[id]) };
    }
    return Object.keys(mud).length ? new ComandoAlterar(mud, rotulo) : null;
  }

  /** O modelo inteiro para o servidor, com os atributos de `base` no lugar dos atuais. */
  _jsonCom(base) {
    const json = this.documento.paraJSON();
    if (base) for (const ent of json.entidades) if (base[ent.id]) ent.atributos = clonar(base[ent.id]);
    return json;
  }

  async _numerarNoServidor(base, opcoes = {}) {
    this.dica('Numerando: comparando as peças pelo critério do detalhamento…');
    return this.api.numerar(this._jsonCom(base), opcoes);
  }

  _relatorioDaNumeracao(r, titulo) {
    const z = r.resumo || {};
    const partes = [`${z.posicoes} posições e ${z.conjuntos} conjuntos no modelo`];
    if ((z.posicoes_novas || []).length) partes.push(`novas: ${z.posicoes_novas.slice(0, 10).join(', ')}${z.posicoes_novas.length > 10 ? '…' : ''}`);
    if ((z.separadas || []).length) partes.push(`${z.separadas.length} peça(s) mudaram e ganharam marca própria`);
    if ((r.avisos || []).length) {
      const corpo = el('div', {},
        el('p', { texto: `${titulo}: ${partes.join('; ')}.` }),
        el('ul', {}, ...r.avisos.slice(0, 40).map(t => el('li', { texto: t }))));
      this.dialogo({ titulo, corpo, ok: null });
    } else {
      this.aviso(`${titulo}: ${partes.join('; ')}.`, 'info', 9000);
    }
  }

  // ---------------------------------------------------------------- numerar

  /** Editar → Numerar peças: marca de posição e de conjunto para o que não tem; separa a peça que mudou. */
  async numerarPecas() {
    if (!this.documento.tamanho) { this.aviso('O modelo está vazio.', 'atencao'); return; }
    let r;
    try { r = await this._numerarNoServidor(null); } catch (e) { this.aviso(`Não foi possível numerar: ${e.message}`, 'erro', 0); return; }
    const cmd = this._comandoDeAtributos(r.mudancas, null, 'Numerar peças');
    if (!cmd) { this.aviso('Nada a numerar: todas as peças têm marca e continuam iguais às outras da posição.', 'info', 7000); return; }
    this.executar(cmd);
    this._relatorioDaNumeracao(r, 'Numerar peças');
  }

  /** Editar → Renumerar tudo: P1, P2… e M1, M2… do zero (recusado com a numeração travada). */
  async renumerarTudo() {
    if (this.numeracaoTravada()) {
      this.aviso('A numeração está travada (projeto emitido): renumerar mudaria as marcas das pranchas já entregues. Destrave em Editar → Numeração travada, se for o caso.', 'atencao', 0);
      return;
    }
    const corpo = el('p', { texto: 'Todas as marcas de posição e de conjunto do modelo serão refeitas a partir de P1 e M1 (as mais numerosas primeiro). Desenhos e pranchas já gerados ficam com as marcas antigas até gerar de novo. Ctrl+Z desfaz.' });
    if (await this.dialogo({ titulo: 'Renumerar tudo', corpo, ok: 'Renumerar' }) !== 'ok') return;
    let r;
    try { r = await this._numerarNoServidor(null, { compactar: true }); } catch (e) { this.aviso(`Não foi possível renumerar: ${e.message}`, 'erro', 0); return; }
    const cmd = this._comandoDeAtributos(r.mudancas, null, 'Renumerar tudo');
    if (cmd) this.executar(cmd);
    this._relatorioDaNumeracao(r, 'Renumerar tudo');
  }

  /** Editar → Numeração travada: liga/desliga a trava (o projeto emitido não renumera). */
  alternarTravaDaNumeracao() {
    const travar = !this.numeracaoTravada();
    const valor = travar ? { travada: true, data: new Date().toISOString().slice(0, 10) } : { travada: false };
    this.executar(new ComandoMetadado('numeracao', valor, travar ? 'Travar a numeração' : 'Destravar a numeração'));
    this.aviso(travar ? 'Numeração travada: Numerar continua dando marca às peças novas, mas "Renumerar tudo" fica bloqueado.'
                      : 'Numeração destravada.', 'info', 7000);
  }

  // ---------------------------------------------------------------- conjunto

  /** A barra mais comprida (ou a peça maior) — a sugestão de peça principal. */
  _principalSugerida(pecas) {
    const ja = pecas.find(e => marcasDe(e).principal);
    if (ja) return ja;
    const barras = pecas.filter(e => e.tipo === 'barra');
    const tam = (e) => {
      if (e.tipo === 'barra') return comprimentoDaBarra(e);
      const c = this.documento.caixaDe(e);
      return c ? Math.max(c[1][0] - c[0][0], c[1][1] - c[0][1], c[1][2] - c[0][2]) : 0;
    };
    return (barras.length ? barras : pecas).reduce((m, e) => (tam(e) > tam(m) ? e : m));
  }

  _rotuloPeca(e) {
    const m = marcasDe(e);
    const perfil = e.tipo === 'barra' ? e.perfil : e.tipo === 'chapa' ? `CH ${numero(e.espessura || 0, 2)}` : (m.perfil || e.nome || 'sólido');
    const tam = e.tipo === 'barra' ? ` · ${numero(comprimentoDaBarra(e))} mm` : '';
    return `${m.posicao ? m.posicao + ' — ' : ''}${perfil}${tam}`;
  }

  /** Editar → Criar conjunto: as peças selecionadas numa montagem de fábrica, com a peça principal. */
  async criarConjunto() {
    const pecas = this._pecasDaSelecao().filter(e => this.documento.editavel(e));
    if (pecas.length < 2) {
      this.dica('Selecione as peças da montagem (duas ou mais): a viga com as chapas de topo, o pilar com a placa de base.');
      return;
    }
    const sugerida = this._principalSugerida(pecas);
    const lista = el('div', { class: 'lista-principal' });
    for (const e of pecas) {
      const r = el('input', { type: 'radio', name: 'principal', value: e.id, checked: e === sugerida });
      lista.append(el('label', { style: 'display:block;margin:.15em 0' }, r, ' ', this._rotuloPeca(e)));
    }
    const corpo = el('div', {},
      el('p', { texto: `${pecas.length} peças viram um conjunto (a marca M sai igual para as cópias com as mesmas peças). Escolha a peça principal — a que orienta a elevação na prancha:` }),
      lista,
      el('p', { class: 'explica', texto: 'As peças que já estavam em outro conjunto saem dele. Peças sem marca de posição recebem marca agora.' }));
    if (await this.dialogo({ titulo: 'Criar conjunto', corpo, ok: 'Criar' }) !== 'ok') return;
    const escolhida = (lista.querySelector('input:checked') || {}).value || sugerida.id;
    const inst = novaInstancia();
    const base = {};
    for (const e of pecas) {
      const a = clonar(e.atributos || {});
      const m = { ...(a.marcas || {}), instancia: inst, conjunto: '' };
      if (e.id === escolhida) m.principal = true; else delete m.principal;
      a.marcas = m;
      base[e.id] = a;
    }
    await this._aplicarConjunto(base, 'Criar conjunto', (doc) => {
      const marca = marcasDe(doc.get(escolhida)).conjunto;
      this.dica(`Conjunto ${marca} com ${pecas.length} peças (principal: ${this._rotuloPeca(doc.get(escolhida))}).`);
    });
  }

  async _aplicarConjunto(base, rotulo, depois) {
    let r;
    try { r = await this._numerarNoServidor(base); } catch (e) { this.aviso(`Não foi possível ${rotulo.toLowerCase()}: ${e.message}`, 'erro', 0); return; }
    const cmd = this._comandoDeAtributos(r.mudancas, base, rotulo);
    if (!cmd) return;
    this.executar(cmd);
    if (depois) depois(this.documento);
    if ((r.avisos || []).length) this._relatorioDaNumeracao(r, rotulo);
  }

  /** Editar → Acrescentar ao conjunto: as peças soltas da seleção entram no conjunto (feito no editor) das outras. */
  async acrescentarAoConjunto() {
    const pecas = this._pecasDaSelecao().filter(e => this.documento.editavel(e));
    const insts = [...new Set(pecas.map(e => marcasDe(e).instancia).filter(Boolean))];
    if (insts.length !== 1) {
      this.dica(insts.length ? 'A seleção tem peças de mais de um conjunto: selecione uma peça do conjunto e as que vão entrar nele.'
                             : 'Selecione uma peça de um conjunto feito no editor (Criar conjunto) e as peças que vão entrar nele.');
      return;
    }
    const novas = pecas.filter(e => marcasDe(e).instancia !== insts[0]);
    if (!novas.length) { this.dica('Todas as peças selecionadas já estão nesse conjunto.'); return; }
    const base = {};
    for (const e of novas) {
      const a = clonar(e.atributos || {});
      a.marcas = { ...(a.marcas || {}), instancia: insts[0], conjunto: '' };
      delete a.marcas.principal;
      base[e.id] = a;
    }
    await this._aplicarConjunto(base, 'Acrescentar ao conjunto', () => this.dica(`${novas.length} peça(s) acrescentada(s) ao conjunto.`));
  }

  /** Editar → Tirar do conjunto: as peças selecionadas voltam a ser soltas (cada posição o conjunto dela). */
  async tirarDoConjunto(todasDaCopia = false) {
    let pecas = this._pecasDaSelecao().filter(e => this.documento.editavel(e));
    if (todasDaCopia) {
      const insts = new Set(pecas.map(e => marcasDe(e).instancia).filter(Boolean));
      pecas = [...this.documento.entidades.values()].filter(e => insts.has(marcasDe(e).instancia) && this.documento.editavel(e));
    }
    pecas = pecas.filter(e => marcasDe(e).instancia || marcasDe(e).conjunto);
    if (!pecas.length) { this.dica(todasDaCopia ? 'Selecione uma peça do conjunto feito no editor a desfazer.' : 'Selecione as peças a tirar do conjunto.'); return; }
    const base = {};
    for (const e of pecas) {
      const a = clonar(e.atributos || {});
      const m = { ...(a.marcas || {}), conjunto: '' };
      delete m.instancia; delete m.principal;
      a.marcas = m;
      base[e.id] = a;
    }
    await this._aplicarConjunto(base, todasDaCopia ? 'Desfazer conjunto' : 'Tirar do conjunto',
      () => this.dica(`${pecas.length} peça(s) fora do conjunto — cada uma volta ao conjunto da própria posição.`));
  }

  /** A peça selecionada passa a ser a principal da cópia do conjunto em que está. */
  definirPrincipal() {
    const pecas = this._pecasDaSelecao();
    const e = pecas.length === 1 ? pecas[0] : null;
    const inst = e && marcasDe(e).instancia;
    if (!inst) { this.dica('Selecione uma peça (só uma) de um conjunto feito no editor.'); return; }
    const mud = {};
    for (const x of this.documento.entidades.values()) {
      const m = marcasDe(x);
      if (m.instancia !== inst) continue;
      const quer = x.id === e.id;
      if (!!m.principal === quer) continue;
      const a = clonar(x.atributos || {});
      if (quer) a.marcas.principal = true; else delete a.marcas.principal;
      mud[x.id] = { atributos: a };
    }
    if (Object.keys(mud).length) this.executar(new ComandoAlterar(mud, 'Peça principal do conjunto'));
    this.dica(`${this._rotuloPeca(e)} é a peça principal do conjunto.`);
  }

  /** As peças da mesma cópia do conjunto (ou da mesma marca de conjunto, nos que vieram dos geradores). */
  selecionarConjunto(e) {
    const m = marcasDe(e);
    const ids = [...this.documento.entidades.values()].filter(x => {
      const mx = marcasDe(x);
      return m.instancia ? mx.instancia === m.instancia : (m.conjunto && mx.conjunto === m.conjunto);
    }).map(x => x.id);
    if (ids.length) this.selecao.definir(ids);
  }

  // ---------------------------------------------------------------- solda

  /** Editar → Soldar: onde as peças selecionadas se encostam, o tipo, a perna, os lados e o local da solda. */
  async soldarSelecao() {
    const pecas = this._pecasDaSelecao();
    if (pecas.length < 2) { this.dica('Selecione as peças a soldar (duas ou mais que se encostam).'); return; }
    let pares;
    try {
      this.dica('Procurando onde as peças se encostam…');
      pares = (await this.api.contatos(documentoDe(pecas))).pares || [];
    } catch (e) { this.aviso(`Não foi possível medir os encontros: ${e.message}`, 'erro', 0); return; }
    if (!pares.length) { this.aviso('As peças selecionadas não se encostam (folga de até 1 mm): não há onde soldar.', 'atencao', 8000); return; }
    // a solda se grava pela posição da outra peça: quem não tem marca recebe agora
    const semMarca = pecas.filter(e => !marcasDe(e).posicao);
    let base = null, patches = {};
    if (semMarca.length) {
      try {
        const r = await this._numerarNoServidor(null);
        patches = r.mudancas || {};
      } catch (e) { this.aviso(`Não foi possível dar marca às peças: ${e.message}`, 'erro', 0); return; }
      base = {};
      for (const [id, p] of Object.entries(patches)) base[id] = comPatch(this.documento.get(id).atributos, p);
    }
    const marcasAgora = (e) => ((base && base[e.id]) ? base[e.id].marcas || {} : marcasDe(e));
    const porId = new Map(pecas.map(e => [e.id, e]));
    // o diálogo
    const linhas = el('div', { class: 'pares-solda' });
    const marcados = [];
    for (const p of pares) {
      const a = porId.get(p.a), b = porId.get(p.b);
      const c0 = p.cordoes[0];
      const caixa = el('input', { type: 'checkbox', checked: true });
      marcados.push([caixa, p]);
      linhas.append(el('label', { style: 'display:block;margin:.15em 0' }, caixa,
        ` ${marcasAgora(a).posicao || this._rotuloPeca(a)} × ${marcasAgora(b).posicao || this._rotuloPeca(b)} — ${NOME_ENCONTRO[c0.tipo] || c0.tipo}, ${numero(p.comprimento)} mm` +
        (c0.lados === 2 ? ' (dos dois lados)' : '') + ` · perna mínima ${numero(p.perna, 1)} mm`));
    }
    const pernaMin = Math.max(...pares.map(p => p.perna));
    const tipo = this._lista([['filete', 'filete'], ['penetracao', 'penetração']], 'filete', () => {});
    const perna = el('input', { type: 'number', step: '0.5', min: '0', value: pernaMin });
    const lados = this._lista([['auto', 'como o encontro'], ['1', 'um lado'], ['2', 'dos dois lados']], 'auto', () => {});
    const local = this._lista([['fabrica', 'fábrica'], ['obra', 'obra (campo)'], ['nenhuma', 'sem solda (só encostada ou aparafusada)']], 'fabrica', () => {});
    const inter = el('input', { type: 'checkbox' });
    const trecho = el('input', { type: 'number', step: '5', min: '0', value: 50, style: 'width:5em' });
    const passo = el('input', { type: 'number', step: '5', min: '0', value: 150, style: 'width:5em' });
    const campos = el('div', { class: 'campos' },
      el('label', { texto: 'Tipo' }), tipo,
      el('label', { texto: 'Perna (mm)' }), perna,
      el('label', { texto: 'Lados' }), lados,
      el('label', { texto: 'Local' }), local,
      el('label', { texto: 'Intermitente' }), el('span', {}, inter, ' trecho ', trecho, ' a cada ', passo, ' mm'));
    const corpo = el('div', {}, el('p', { texto: 'Encontros achados entre as peças selecionadas:' }), linhas, campos,
      el('p', { class: 'explica', texto: `A perna mínima é a da NBR 8800 (Tabela 11) pela peça menos espessa. A solda vale para as duas posições em todo o modelo (todas as cópias do conjunto); "sem solda" tira a solda que o detalhamento deduziria ali.` }));
    if (await this.dialogo({ titulo: 'Soldar peças', corpo, ok: 'Soldar' }) !== 'ok') return;
    const escolhidos = marcados.filter(([c]) => c.checked).map(([, p]) => p);
    if (!escolhidos.length) return;
    const def = { tipo: tipo.value, perna: parseFloat(String(perna.value).replace(',', '.')) || 0, local: local.value,
                  data: new Date().toISOString().slice(0, 10) };
    if (def.local !== 'nenhuma' && !(def.perna > 0)) { this.aviso('A perna da solda precisa ser maior que zero.', 'atencao'); return; }
    if (inter.checked) {
      const l = parseFloat(trecho.value) || 0, s = parseFloat(passo.value) || 0;
      if (!(l > 0 && l < s)) { this.aviso('Solda intermitente: o trecho precisa ser menor que o passo.', 'atencao'); return; }
      def.intermitente = { l, passo: s };
    }
    // a definição nas peças das duas posições, pela posição da outra
    const novos = base ? { ...base } : {};
    const atr = (e) => { if (!novos[e.id]) novos[e.id] = clonar(e.atributos || {}); return novos[e.id]; };
    const pecasDaPosicao = (pos) => [...this.documento.entidades.values()].filter(x => ehPecaDeProducao(x) &&
      (((base && base[x.id]) ? (base[x.id].marcas || {}).posicao : marcasDe(x).posicao) === pos));
    for (const p of escolhidos) {
      const a = porId.get(p.a), b = porId.get(p.b);
      const pa = marcasAgora(a).posicao, pb = marcasAgora(b).posicao;
      if (!pa || !pb) continue;
      const c0 = p.cordoes[0];
      const d = { ...def, forma: c0.tipo, comprimento: p.comprimento, p0: c0.p0, p1: c0.p1,
                  lados: lados.value === 'auto' ? (c0.lados || 1) : Number(lados.value) };
      for (const x of pecasDaPosicao(pa)) { const ax = atr(x); ax.soldas = { ...(ax.soldas || {}), [pb]: d }; }
      for (const x of pecasDaPosicao(pb)) { const ax = atr(x); ax.soldas = { ...(ax.soldas || {}), [pa]: d }; }
    }
    const cmd = this._comandoDeAtributos({}, novos, `Soldar ${escolhidos.length} encontro(s)`);
    if (cmd) this.executar(cmd);
    this.dica(`${escolhidos.length} encontro(s): ${def.local === 'nenhuma' ? 'sem solda' : `${NOME_TIPO_SOLDA[def.tipo]} ${numero(def.perna, 1)} mm, ${NOME_LOCAL[def.local]}`}. Vale para todas as peças dessas posições.`);
  }

  /** Tira a solda definida entre a posição da peça e `outraPos` (em todas as peças das duas posições). */
  removerSolda(e, outraPos) {
    const pos = marcasDe(e).posicao;
    const mud = {};
    for (const x of this.documento.entidades.values()) {
      const s = x.atributos && x.atributos.soldas;
      if (!s) continue;
      const px = marcasDe(x).posicao;
      const chave = px === pos ? outraPos : px === outraPos ? pos : null;
      if (!chave || !(chave in s)) continue;
      const a = clonar(x.atributos);
      delete a.soldas[chave];
      if (!Object.keys(a.soldas).length) delete a.soldas;
      mud[x.id] = { atributos: a };
    }
    if (Object.keys(mud).length) this.executar(new ComandoAlterar(mud, `Tirar a solda ${pos} × ${outraPos}`));
  }

  // ---------------------------------------------------------------- converter em peça

  /** Editar → Converter em chapa: o sólido desenhado à mão (retângulo empurrado) vira Chapa paramétrica. */
  async converterEmChapa() {
    const sol = this.selecao.entidades.filter(e => e.tipo === 'solido' && !this._ehParafuso(e) && this.documento.editavel(e) &&
      !['cota', 'construcao'].includes((e.atributos || {}).tipo));
    if (!sol.length) { this.dica('Selecione o sólido a converter (o retângulo empurrado, a placa desenhada à mão).'); return; }
    let r;
    try { r = await this.api.converterChapa(documentoDe(sol), sol.map(e => e.id)); } catch (e) { this.aviso(`Não foi possível converter: ${e.message}`, 'erro', 0); return; }
    const novas = Object.values(r.chapas || {}).map(d => criar(d));
    if (novas.length) {
      this.selecao.limpar();
      this.executar(new ComandoComposto([new ComandoRemover(novas.map(c => c.id)), new ComandoAdicionar(novas)],
        `Converter ${novas.length} sólido(s) em chapa`));
      this.selecao.definir(novas.map(c => c.id));
    }
    const recusadas = Object.entries(r.recusadas || {});
    if (recusadas.length) {
      this.aviso(`${novas.length} convertida(s); ${recusadas.length} não: ${recusadas.slice(0, 4).map(([id, m]) => `${this.documento.get(id)?.nome || id} (${m})`).join('; ')}.` +
                 ' Uma face solta (sem espessura) precisa ser empurrada antes (Empurrar/Puxar).', 'atencao', 0);
    } else {
      this.dica(`${novas.length} sólido(s) agora são chapas: espessura, aço e furos no painel; Numerar dá a marca.`);
    }
  }

  // ---------------------------------------------------------------- painel

  /** O grupo "Produção" do painel de propriedades: marca, conjunto, solda, fase e acabamento editáveis. */
  _painelProducao(raiz, ents) {
    const pecas = ents.filter(ehPecaDeProducao);
    if (!pecas.length) return;
    const um = pecas.length === 1 ? pecas[0] : null;
    const g = this._grupo(raiz, 'Produção');
    // tipo × instância, como no Revit: a mudança vale para a seleção, para a posição inteira ou para o conjunto inteiro
    const escopo = this.escopoProducao || 'selecao';
    const idsDoEscopo = () => {
      if (escopo === 'selecao') return pecas.map(e => e.id);
      const chaves = new Set(pecas.map(e => marcasDe(e)[escopo === 'posicao' ? 'posicao' : 'conjunto']).filter(Boolean));
      const campo = escopo === 'posicao' ? 'posicao' : 'conjunto';
      const fora = [...this.documento.entidades.values()].filter(x => ehPecaDeProducao(x) && chaves.has(marcasDe(x)[campo])).map(x => x.id);
      return fora.length ? fora : pecas.map(e => e.id);
    };
    const selEscopo = this._lista([['selecao', 'só as selecionadas'], ['posicao', 'todas da mesma posição'], ['conjunto', 'todo o conjunto']],
      escopo, v => { this.escopoProducao = v; this._agendarPaineis('props'); });
    selEscopo.title = 'A quem vale a mudança dos campos abaixo (posição, nome, fase, acabamento) — como tipo × instância do Revit';
    g.append(el('label', { texto: 'Aplicar a' }), selEscopo);
    const comumM = (k) => { const v = marcasDe(pecas[0])[k]; return pecas.every(e => marcasDe(e)[k] === v) ? v : undefined; };
    const comumA = (k) => { const v = (pecas[0].atributos || {})[k]; return pecas.every(e => (e.atributos || {})[k] === v) ? v : undefined; };
    const mudarMarca = (k, v, rotulo, extra = {}) => this.alterarEntidades(idsDoEscopo(), (e) => {
      const a = clonar(e.atributos || {});
      a.marcas = { ...(a.marcas || {}) };
      if (v) a.marcas[k] = v; else delete a.marcas[k];
      Object.assign(a, extra);
      return { atributos: a };
    }, rotulo);
    const mudarAtributo = (k, v, rotulo) => this.alterarEntidades(idsDoEscopo(), (e) => {
      const a = clonar(e.atributos || {});
      if (v) a[k] = v; else delete a[k];
      return { atributos: a };
    }, rotulo);
    const vazio = (i, v) => { if (v === undefined) i.placeholder = 'vários'; return i; };

    const pos = comumM('posicao');
    g.append(el('label', { texto: 'Posição' }), vazio(this._texto(pos || '', v =>
      mudarMarca('posicao', v, v ? `Marca ${v}` : 'Tirar a marca', { marca_a_conferir: true })), pos));
    const nomeP = comumM('nome_projeto');
    g.append(el('label', { texto: 'Nome de produção', title: 'Fixa o nome que sai na prancha (S.T.1, CH7…) no lugar do que o detalhamento daria' }),
      vazio(this._texto(nomeP || '', v => mudarMarca('nome_projeto', v, v ? `Nome de produção ${v}` : 'Nome de produção automático')), nomeP));

    // conjunto
    const conj = comumM('conjunto'), inst = comumM('instancia');
    let txtConj = conj || '—';
    if (inst) {
      const n = [...this.documento.entidades.values()].filter(x => marcasDe(x).instancia === inst).length;
      txtConj = `${conj || '(numerar)'} · ${n} peças nesta cópia`;
    } else if (conj) {
      const n = [...this.documento.entidades.values()].filter(x => marcasDe(x).conjunto === conj).length;
      txtConj = `${conj} · ${n} peças${n === pecas.length ? '' : ' (todas as cópias)'}`;
    }
    const vc = el('span', { class: 'valor clicavel', texto: txtConj, title: 'Clique: selecionar o conjunto' });
    vc.addEventListener('click', () => this.selecionarConjunto(pecas[0]));
    g.append(el('label', { texto: 'Conjunto' }), vc);
    if (um && marcasDe(um).instancia) {
      const ck = el('input', { type: 'checkbox', checked: !!marcasDe(um).principal, disabled: !!marcasDe(um).principal });
      ck.addEventListener('change', () => this.definirPrincipal());
      g.append(el('label', { texto: 'Peça principal' }), el('span', {}, ck));
    }
    const botoes = el('div', { class: 'acoes-painel', style: 'grid-column:1/-1' });
    const botao = (texto, fn, titulo) => botoes.append(el('button', { type: 'button', class: 'mini', texto, title: titulo, onclick: fn }));
    if (pecas.length >= 2) botao('Criar conjunto…', () => this.criarConjunto(), 'As peças selecionadas numa montagem de fábrica, com a peça principal');
    if (pecas.some(e => marcasDe(e).instancia || marcasDe(e).conjunto) && pecas.length < this.documento.tamanho) {
      if (pecas.some(e => marcasDe(e).instancia)) botao('Tirar do conjunto', () => this.tirarDoConjunto(), 'As peças selecionadas saem do conjunto');
    }
    if (pecas.length >= 2) botao('Soldar…', () => this.soldarSelecao(), 'Onde as peças se encostam: tipo, perna, lados, fábrica ou obra');
    if (pecas.some(e => !marcasDe(e).posicao || (e.atributos || {}).marca_a_conferir)) {
      botao('Numerar', () => this.numerarPecas(), 'Dá a marca de posição e de conjunto às peças sem marca (e separa as que mudaram)');
    }
    if (botoes.childNodes.length) g.append(botoes);

    // solda definida nesta peça
    if (um && um.atributos && um.atributos.soldas && Object.keys(um.atributos.soldas).length) {
      for (const [outra, d] of Object.entries(um.atributos.soldas)) {
        const txt = d.local === 'nenhuma' ? 'sem solda'
          : `${NOME_TIPO_SOLDA[d.tipo] || d.tipo} ${numero(d.perna || 0, 1)} mm${d.lados === 2 ? ' (2 lados)' : ''}` +
            (d.intermitente ? ` ${d.intermitente.l}-${d.intermitente.passo}` : '') + ` · ${NOME_LOCAL[d.local] || d.local}`;
        const linha = el('span', { class: 'valor' }, `${txt} `,
          el('button', { type: 'button', class: 'mini', texto: '×', title: `Tirar a solda com ${outra}`, onclick: () => this.removerSolda(um, outra) }));
        g.append(el('label', { texto: `Solda × ${outra}` }), linha);
      }
    }
    // fase e acabamento
    const fase = comumA('fase');
    g.append(el('label', { texto: 'Fase / lote' }), vazio(this._texto(fase || '', v => mudarAtributo('fase', v, v ? `Fase ${v}` : 'Sem fase')), fase));
    g.append(el('label', { texto: 'Acabamento' }),
      this._lista(ACABAMENTOS, comumA('acabamento') ?? '', v => mudarAtributo('acabamento', v, v ? `Acabamento: ${v}` : 'Sem acabamento')));
    // as propriedades do usuário (os parâmetros compartilhados do Revit): campos livres, no mesmo "Aplicar a"
    const chavesU = [...new Set(pecas.flatMap(e => Object.keys((e.atributos && e.atributos.props_usuario) || {})))].sort();
    const mudarPropU = (k, v, rotulo) => this.alterarEntidades(idsDoEscopo(), (e) => {
      const a = clonar(e.atributos || {});
      const pu = { ...(a.props_usuario || {}) };
      if (v) pu[k] = v; else delete pu[k];
      if (Object.keys(pu).length) a.props_usuario = pu; else delete a.props_usuario;
      return { atributos: a };
    }, rotulo);
    for (const k of chavesU) {
      const v0 = (pecas[0].atributos.props_usuario || {})[k];
      const igual = pecas.every(e => ((e.atributos && e.atributos.props_usuario) || {})[k] === v0);
      g.append(el('label', { texto: k, title: 'Propriedade do usuário — apague o valor para tirar' }),
        vazio(this._texto(igual ? (v0 || '') : '', v => mudarPropU(k, v, v ? `${k}: ${v}` : `Tirar ${k}`)), igual ? v0 : undefined));
    }
    const maisU = el('button', { type: 'button', class: 'mini', texto: '+ propriedade', title: 'Um campo livre (fornecedor, nota fiscal, observação…) — vai na ficha, na tabela, no Colorir por e no IFC' });
    maisU.addEventListener('click', async () => {
      const nomeK = el('input', { type: 'text', placeholder: 'Fornecedor', style: 'width:100%' });
      const valorK = el('input', { type: 'text', placeholder: 'Gerdau', style: 'width:100%' });
      const corpo = el('div', { class: 'campos' }, el('label', { texto: 'Propriedade' }), nomeK, el('label', { texto: 'Valor' }), valorK);
      if (await this.dialogo({ titulo: 'Nova propriedade', corpo, ok: 'Acrescentar' }) !== 'ok') return;
      const k = nomeK.value.trim(), v = valorK.value.trim();
      if (!k || !v) { this.aviso('Dê o nome e o valor da propriedade.', 'atencao'); return; }
      mudarPropU(k, v, `${k}: ${v}`);
    });
    g.append(el('span'), maisU);
    if (um && um.tipo === 'chapa' && !marcasDe(um).posicao && this.projeto) {
      g.append(el('span', { class: 'explica', style: 'grid-column:1/-1',
        texto: 'Para editar a chapa no 2D (furos, contorno), numere primeiro: Editar → Numerar peças.' }));
    }
  }
}
