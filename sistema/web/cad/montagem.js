// A Montagem do projeto recebido — etapa 1 da leitura por quadros (plano de 01/10/2026,
// Projeto/Leitura-por-quadros-plano-2026-10-01.pdf).
//
// O DXF do cliente fica na Original (a planta de lançamento, intocada). A Montagem é outro desenho do
// projeto ("montagem", em mm de papel, escala 1) com os QUADROS tipados onde o operador põe cada parte do
// projeto: locação, terças, posição das tesouras, elevações, corte, uma tesoura por quadro (com nome) e os
// detalhes de ligação. Cada quadro tem a sua escala; o tamanho se ajusta pela alça do canto e os outros se
// movem e se acomodam (decisão do usuário, 01/10). Os quadros ficam em `metadados.montagem` do desenho; o
// que for posto dentro de um quadro (etapa 2) leva `atributos.quadro` e anda com ele.
//
// Embaixo do palco, as abas Original | Montagem | Pranchas trocam o desenho aberto.
//
// Etapa 2 (Original → quadro): na Original, "Enviar área para quadro…" marca um retângulo (pega tudo o que
// está dentro, inclusive as camadas travadas do cliente) e copia para o quadro escolhido, reduzido à escala
// dele (textos e cotas proporcionais; a cota guarda o valor real escrito). O quadro cresce se o desenho não
// couber (os outros se acomodam). A cópia guarda de onde veio (o desenho, a área, quando) — é o que a
// revisão vai comparar quando chegar um DXF novo — e confere a escala pelas cotas copiadas: o número escrito
// × a medida no desenho do cliente.
//
// Módulo à parte, pendurado no CAD já aberto (window.cad): desenha os quadros pelo gancho
// `tela.aoDesenhar` e põe os controles (título, escala, nome, alça, "+ corte tesoura") por cima do canvas.

import { DESENHO_LANCAMENTO } from './lancamento.js';
import { transformar, pontosDe, caixaDe, valorCota, novoId as idEntidade } from './nucleo/desenho2d.js';
import { Ferramenta } from './ferramentas.js';

export const DESENHO_MONTAGEM = 'montagem';
export const FOLGA = 25;                 // mm de papel entre os quadros
export const MINIMO = [140, 100];        // o menor quadro (mm de papel)

/** Os tipos de quadro: rótulo, escala inicial, tamanho inicial (mm de papel) e a linha da folha. */
export const TIPOS = {
  locacao:       { rotulo: 'Locação', escala: 100, w: 420, h: 297, linha: 0, cor: '#ca8a04', diz: 'pilares, eixos e cotas → chumbadores' },
  tercas:        { rotulo: 'Posição das terças', escala: 100, w: 420, h: 297, linha: 0, cor: '#ca8a04', diz: 'linhas das terças, siglas e a lista' },
  tesouras_pos:  { rotulo: 'Posição das tesouras', escala: 100, w: 420, h: 297, linha: 0, cor: '#ca8a04', diz: 'marcas T01, T02… e quantidades' },
  elev_frontal:  { rotulo: 'Elevação frontal', escala: 50, w: 297, h: 210, linha: 1, cor: '#0e7490', diz: 'vista frontal' },
  elev_lateral:  { rotulo: 'Elevação lateral', escala: 50, w: 297, h: 210, linha: 1, cor: '#0e7490', diz: 'vista lateral' },
  elev_fundos:   { rotulo: 'Fundos', escala: 50, w: 297, h: 210, linha: 1, cor: '#0e7490', diz: 'vista de fundos' },
  corte:         { rotulo: 'Corte transversal', escala: 50, w: 297, h: 210, linha: 1, cor: '#0e7490', diz: 'cotas transversais: base, topo, níveis, inclinação' },
  tesoura:       { rotulo: 'Tesoura', escala: 25, w: 297, h: 210, linha: 2, cor: '#16a34a', diz: 'o recorte de um tipo de tesoura, com a legenda de perfis', varios: true },
  ligacoes:      { rotulo: 'Detalhes de ligação', escala: 10, w: 420, h: 297, linha: 3, cor: '#2563eb', diz: 'os detalhes do projeto (referência); a escolha no banco vem depois' },
};
export const ESCALAS = [1, 2, 5, 10, 20, 25, 50, 75, 100, 125, 200, 250, 500];
const ORDEM = ['locacao', 'tercas', 'tesouras_pos', 'elev_frontal', 'elev_lateral', 'elev_fundos', 'corte', 'tesoura', 'ligacoes'];

let _seq = 0;
const novoId = () => 'q' + Date.now().toString(36) + (_seq++).toString(36);

/** A montagem de um projeto novo: um quadro de cada tipo e uma tesoura sem nome. */
export function montagemPadrao(original = DESENHO_LANCAMENTO) {
  const quadros = ORDEM.map((tipo) => {
    const t = TIPOS[tipo];
    return { id: novoId(), tipo, nome: tipo === 'tesoura' ? '' : t.rotulo, escala: t.escala, w: t.w, h: t.h, x: 0, y: 0 };
  });
  const m = { versao: 1, original, quadros };
  arrumar(m);
  return m;
}

/**
 * Acomoda os quadros: as linhas de cima para baixo (plantas, elevações e corte, tesouras, ligações), cada
 * linha da esquerda para a direita, a FOLGA entre eles; a altura de uma linha é a do maior quadro dela.
 * `x, y` é o canto de cima à esquerda (y para cima, como no CAD). Devolve {id: [dx, dy]} do que andou, e
 * em `m.vaga` o lugar do "+ corte tesoura" (depois da última tesoura).
 */
export function arrumar(m) {
  const linhas = new Map();
  for (const q of m.quadros) {
    const l = (TIPOS[q.tipo] || TIPOS.tesoura).linha;
    if (!linhas.has(l)) linhas.set(l, []);
    linhas.get(l).push(q);
  }
  const andou = {};
  let topo = 0;
  const tesTam = TIPOS.tesoura;
  for (const l of [...new Set([...linhas.keys(), tesTam.linha])].sort((a, b) => a - b)) {
    const qs = linhas.get(l) || [];
    let x = 0, alt = 0;
    for (const q of qs) {
      const dx = x - (q.x || 0), dy = topo - (q.y || 0);
      if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) andou[q.id] = [dx, dy];
      q.x = x; q.y = topo;
      x += q.w + FOLGA;
      alt = Math.max(alt, q.h);
    }
    if (l === tesTam.linha) {
      // o "+ corte tesoura" sempre no tamanho padrão (não no da última, que pode ter crescido muito)
      const w = tesTam.w, h = tesTam.h;
      m.vaga = { x, y: topo, w, h };
      alt = Math.max(alt, h);
    }
    topo -= alt + FOLGA;
  }
  return andou;
}

/** Margens dentro do quadro (mm de papel): a faixa do título em cima. */
export const MARGEM = { lado: 8, topo: 20, baixo: 10 };
const teto5 = (v) => Math.ceil(v / 5) * 5;

/**
 * Copia `ents` (do desenho do cliente, escala `kOriginal`) para o quadro `quadroId` da montagem `mont`
 * (o JSON do desenho "montagem"), na escala `escala` do quadro. `camadas` = {nome: camada} das usadas.
 * Mexe em `mont` e devolve o resumo {copiados, cresceu, conferencia, caixa}.
 */
export function copiarParaQuadro(mont, quadroId, ents, { escala, kOriginal = 1, camadas = {}, substituir = true, origem = {} } = {}) {
  const m = mont.metadados.montagem;
  const q = m.quadros.find(x => x.id === quadroId);
  if (!q) throw new Error('quadro não encontrado');
  if (!ents.length) throw new Error('nenhum objeto dentro da área');
  const s = Number(escala) || q.escala;
  const pts = ents.flatMap(e => pontosDe(e));
  const [[bx0, by0], [bx1, by1]] = caixaDe(pts);
  if (substituir) mont.entidades = mont.entidades.filter(e => (e.atributos || {}).quadro !== q.id);
  // o quadro cresce se o desenho não cabe (na escala do quadro)
  const wc = (bx1 - bx0) / s, hc = (by1 - by0) / s;
  const w0 = q.w, h0 = q.h;
  // a escala em que o desenho caberia no tamanho de agora do quadro (para o aviso)
  const cabe = ESCALAS.find(e => (bx1 - bx0) / e <= q.w - 2 * MARGEM.lado && (by1 - by0) / e <= q.h - MARGEM.topo - MARGEM.baixo) || null;
  q.escala = s;
  if (wc > q.w - 2 * MARGEM.lado) q.w = teto5(wc + 2 * MARGEM.lado);
  if (hc > q.h - MARGEM.topo - MARGEM.baixo) q.h = teto5(hc + MARGEM.topo + MARGEM.baixo);
  const andou = arrumar(m);
  for (const [i, e] of mont.entidades.entries()) {
    const d = andou[(e.atributos || {}).quadro];
    if (d) mont.entidades[i] = transformar(e, (p) => [p[0] + d[0], p[1] + d[1]]);
  }
  // o desenho no canto de cima à esquerda do quadro, abaixo do título
  const f = (p) => [q.x + MARGEM.lado + (p[0] - bx0) / s, q.y - MARGEM.topo - (by1 - p[1]) / s];
  const fator = kOriginal / s;                // o que é mm de papel (texto, cota, hachura) fica proporcional
  const conf = { cotas: 0, batem: 0, fatores: [] };
  for (const e of ents) {
    const n = transformar(e, f, (a) => a, 1 / s);
    n.id = idEntidade();
    if (n.altura != null && (n.tipo === 'texto' || n.tipo === 'cota' || n.tipo === 'chamada')) n.altura = n.altura * fator;
    if (n.tipo === 'cota') {
      n.deslocamento = (n.deslocamento || 0) * fator;
      const medida = valorCota(e);
      const escrito = parseFloat(String(e.texto ?? '').replace(/\./g, '').replace(',', '.'));
      if (e.texto == null || e.texto === '') n.texto = String(Math.round(medida));
      if (isFinite(escrito) && escrito > 0 && medida > 1e-6) {
        conf.cotas++;
        const r = escrito / medida;
        conf.fatores.push(r);
        if (Math.abs(r - 1) <= 0.02 || Math.abs(escrito - medida) <= 1.5) conf.batem++;
      }
      n.atributos = { ...(n.atributos || {}), medida_real: Math.round(medida * 10) / 10 };
    }
    if (n.tipo === 'hachura' && n.espacamento) n.espacamento = n.espacamento * fator;
    n.atributos = { ...(n.atributos || {}), quadro: q.id, da_original: e.id };
    mont.entidades.push(n);
  }
  mont.camadas = mont.camadas || {};
  for (const [nome, c] of Object.entries(camadas)) {
    if (!mont.camadas[nome]) mont.camadas[nome] = { ...c, bloqueada: false, visivel: true };
  }
  // a escala pelas cotas: a maioria bate, ou um fator comum (o DXF em cm, em m) para avisar
  let sugestao = null;
  if (conf.cotas && conf.batem < conf.cotas / 2) {
    const ord = [...conf.fatores].sort((a, b) => a - b), med = ord[Math.floor(ord.length / 2)];
    for (const k of [10, 100, 1000, 0.1, 0.01, 0.001, 2, 0.5, 5, 0.2]) if (Math.abs(med / k - 1) < 0.03) { sugestao = k; break; }
  }
  q.conferencia = { cotas: conf.cotas, batem: conf.batem, fator: sugestao };
  q.fonte = { ...origem, caixa: [[bx0, by0], [bx1, by1]], entidades: ents.length, em: new Date().toISOString().slice(0, 16) };
  return { copiados: ents.length, cresceu: q.w !== w0 || q.h !== h0, cabe, conferencia: q.conferencia, quadro: q };
}

const $ = (s, r = document) => r.querySelector(s);
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
async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  const t = await r.text();
  let d = null; try { d = JSON.parse(t); } catch { /* texto */ }
  if (!r.ok) throw new Error((d && (d.erro || d.mensagem)) || t || r.statusText);
  return d;
}

/** Na Original: o retângulo da área a mandar para um quadro (dois cliques, ou arrastando). */
class EnviarArea extends Ferramenta {
  static id = 'enviar-quadro'; static nome = 'Enviar área para quadro'; static grupo = 'montagem';
  static dica = 'Marque a área a levar para um quadro da Montagem: o primeiro canto (ou arraste) · Esc cancela';
  reiniciar() { super.reiniciar(); this.a = null; this.editor.tela.regiao = null; }
  desativar() { super.desativar(); this.editor.tela.regiao = null; this.editor.tela.pedirQuadro(); }
  onPonto(p) {
    if (!this.a) { this.a = p; this.dica('Agora o canto oposto da área · Esc cancela'); return; }
    this._fim(p);
  }
  onMover(p) { if (this.a) { this.editor.tela.regiao = [this.a, p]; } }
  onSoltar(p, ev) {
    const de = ev && ev.arrasto ? this.editor.tela.paraMundo(ev.arrasto.de) : null;
    if (de) { this.a = de; this._fim(p); }
  }
  _fim(p) {
    const a = this.a;
    this.a = null;
    this.editor.tela.regiao = [a, p];
    const caixa = [[Math.min(a[0], p[0]), Math.min(a[1], p[1])], [Math.max(a[0], p[0]), Math.max(a[1], p[1])]];
    window.montagem.enviarArea(caixa).finally(() => { this.editor.tela.regiao = null; this.editor.tela.pedirQuadro(); });
  }
}

class Montagem {
  constructor(cad) {
    this.cad = cad;
    this.palco = $('#palco');
    this.camada = el('div', { class: 'montagem-quadros', id: 'montagem-quadros' });
    this.abas = el('div', { class: 'abas-projeto', id: 'abas-projeto', hidden: true, role: 'tablist', 'aria-label': 'Etapas do projeto recebido' },
      el('button', { type: 'button', 'data-aba': 'original', title: 'O DXF do cliente como chegou (a planta de lançamento): só leitura, a fonte dos quadros', onclick: () => this.ir('original') }, 'Original'),
      el('button', { type: 'button', 'data-aba': 'montagem', title: 'A folha com os quadros: locação, terças, tesouras, elevações, corte e ligações — é o que o programa lê', onclick: () => this.ir('montagem') }, 'Montagem'),
      el('button', { type: 'button', 'data-aba': 'pranchas', title: 'As pranchas do projeto, geradas depois do 3D', onclick: () => this.ir('pranchas') }, 'Pranchas'),
      this.botaoEnviar = el('button', { type: 'button', class: 'enviar-quadro', hidden: true, id: 'btn-enviar-quadro',
        title: 'Marque uma área da planta do cliente e escolha o quadro da Montagem para onde ela vai (copiada, na escala do quadro)',
        onclick: () => this.cad.ativarFerramenta('enviar-quadro') }, 'Enviar área para quadro…'));
    cad.ferramentas.set('enviar-quadro', new EnviarArea(cad));
    this.palco.append(this.camada, this.abas);
    this.desenhos = [];
    this.arrasto = null;
    // os quadros por cima do desenho
    const antes = cad.tela.aoDesenhar;
    cad.tela.aoDesenhar = () => { if (antes) antes(); this.desenhar(); };
    // trocou o desenho: as abas e os quadros acompanham
    const carregar = cad.carregar.bind(cad);
    cad.carregar = (json, op) => {
      const r = carregar(json, op);
      // a montagem abre com a folha inteira dos quadros na tela (o CAD enquadraria só o conteúdo)
      if (this.ativa && !(op && op.enquadrar === false)) this.enquadrar();
      this.aoTrocar();
      return r;
    };
    window.addEventListener('pointermove', (ev) => this._mover(ev));
    window.addEventListener('pointerup', (ev) => this._soltar(ev));
    // o CAD já abriu o desenho antes de a montagem se pendurar nele (F5 com ?desenho=montagem)
    if (this.ativa) this.enquadrar();
    this.aoTrocar();
  }

  get ativa() { return !!(this.cad.nomeDesenho === DESENHO_MONTAGEM && this.m); }
  get m() { return (this.cad.doc.metadados || {}).montagem || null; }

  async _lista(recarregar = false) {
    if (!this.cad.projeto) return [];
    if (recarregar || !this._listou) {
      try { this.desenhos = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/desenhos`); } catch { this.desenhos = []; }
      this._listou = true;
    }
    return this.desenhos;
  }

  async aoTrocar() {
    const lista = await this._lista(true);
    const nomes = new Set(lista.map(d => d.nome));
    const temProjetoRecebido = nomes.has(DESENHO_LANCAMENTO) || nomes.has(DESENHO_MONTAGEM);
    this.abas.hidden = !this.cad.projeto || !temProjetoRecebido;
    const atual = this.cad.nomeDesenho === DESENHO_MONTAGEM ? 'montagem'
      : this.cad.nomeDesenho === ((this.m && this.m.original) || DESENHO_LANCAMENTO) ? 'original'
      : /^pranchas/.test(this.cad.nomeDesenho || '') ? 'pranchas' : '';
    for (const b of this.abas.querySelectorAll('button[data-aba]')) b.classList.toggle('on', b.dataset.aba === atual);
    this.naOriginal = atual === 'original';
    this.botaoEnviar.hidden = !this.naOriginal;
    this.mOriginal = null;
    if (this.naOriginal && nomes.has(DESENHO_MONTAGEM)) {
      try { this.mOriginal = (await pedir(this._urlMontagem())).desenho.metadados.montagem || null; } catch { this.mOriginal = null; }
    }
    // a montagem antiga sem quadros (ou criada por outro caminho): ganha a padrão
    if (this.cad.nomeDesenho === DESENHO_MONTAGEM && !this.m) {
      this.cad.doc.metadados = { ...(this.cad.doc.metadados || {}), montagem: montagemPadrao() };
      this._gravar();
    }
    this.cad.tela.pedirQuadro();
  }

  /** Troca de aba (abre o desenho; a Montagem que não existe é criada com os quadros padrão). */
  async ir(aba) {
    if (this.ativa) await this._gravarJa();
    const lista = await this._lista(true);
    const nomes = new Set(lista.map(d => d.nome));
    if (aba === 'original') {
      const nome = (this.m && this.m.original) || DESENHO_LANCAMENTO;
      if (!nomes.has(nome)) { this.cad.aviso('Este projeto ainda não tem a planta do cliente. Comece por "Novo a partir do arquitetônico" na tela inicial.', 'atencao'); return; }
      await this.cad.abrirDesenho(nome);
    } else if (aba === 'montagem') {
      if (!nomes.has(DESENHO_MONTAGEM)) {
        const m = montagemPadrao(nomes.has(DESENHO_LANCAMENTO) ? DESENHO_LANCAMENTO : '');
        await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/desenhos/${encodeURIComponent(DESENHO_MONTAGEM)}`,
          { desenho: { nome: 'Montagem', unidade: 'mm', escala: 1, camadas: {}, entidades: [], vistas: [], metadados: { montagem: m } } });
      }
      await this.cad.abrirDesenho(DESENHO_MONTAGEM);
      this.cad.dica('Montagem: ponha em cada quadro a parte do projeto que ele pede. A alça no canto de baixo ajusta o tamanho (os outros se acomodam); a escala e o nome da tesoura ficam no título.');
    } else {
      const pr = lista.filter(d => /^pranchas/.test(d.nome)).sort((a, b) => (a.alterado < b.alterado ? 1 : -1))[0];
      if (!pr) { this.cad.aviso('As pranchas saem depois do 3D (menu Produção › Pranchas). Ainda não há pranchas neste projeto.', 'info'); return; }
      await this.cad.abrirDesenho(pr.nome);
    }
  }

  _urlMontagem() { return `/api/projetos/${encodeURIComponent(this.cad.projeto)}/desenhos/${encodeURIComponent(DESENHO_MONTAGEM)}`; }

  /** A montagem do projeto (o JSON do desenho), criada com os quadros padrão se ainda não existe. */
  async _montagemJSON() {
    try { return (await pedir(this._urlMontagem())).desenho; } catch {
      return { nome: 'Montagem', unidade: 'mm', escala: 1, camadas: {}, entidades: [], vistas: [], metadados: { montagem: montagemPadrao(this.cad.nomeDesenho) } };
    }
  }

  /** Os objetos da Original dentro da caixa (inteiros dentro), inclusive os das camadas travadas do cliente. */
  _naArea(caixa) {
    const [[x0, y0], [x1, y1]] = caixa;
    const dentro = (p) => p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
    return this.cad.doc.naRegiao(caixa).filter(e => this.cad.doc.visivel(e) && pontosDe(e).every(dentro));
  }

  /** Marcou a área na Original: escolhe o quadro e copia. */
  async enviarArea(caixa) {
    const ents = this._naArea(caixa);
    if (!ents.length) { this.cad.aviso('Nada inteiro dentro dessa área. Marque a área envolvendo o desenho todo.', 'atencao'); this.cad.ativarFerramenta('selecionar'); return; }
    const mont = await this._montagemJSON();
    const m = mont.metadados.montagem;
    const rotulo = (q) => (TIPOS[q.tipo] || TIPOS.tesoura).rotulo + (q.tipo === 'tesoura' ? ' ' + (q.nome || '(sem nome)') : '');
    const selQ = el('select', { id: 'enviar-quadro-destino' },
      m.quadros.map(q => el('option', { value: q.id }, rotulo(q) + (q.fonte ? '  · já tem desenho' : ''))),
      el('option', { value: '+tesoura' }, '+ nova tesoura…'));
    const nome = el('input', { id: 'enviar-quadro-nome', placeholder: 'T03', size: 8, spellcheck: 'false', hidden: true });
    const selE = el('select', { id: 'enviar-quadro-escala' }, ESCALAS.map(e => el('option', { value: e }, '1:' + e)));
    const subst = el('input', { type: 'checkbox', id: 'enviar-quadro-substituir', checked: true });
    const sincronizar = () => {
      const q = m.quadros.find(x => x.id === selQ.value);
      nome.hidden = selQ.value !== '+tesoura';
      selE.value = String(q ? q.escala : TIPOS.tesoura.escala);
    };
    selQ.addEventListener('change', sincronizar);
    // o primeiro quadro ainda vazio é a sugestão
    const vazio = m.quadros.find(q => !q.fonte);
    if (vazio) selQ.value = vazio.id;
    sincronizar();
    const corpo = el('div', { class: 'enviar-quadro-dialogo' },
      el('div', { class: 'explica', texto: `${ents.length.toLocaleString('pt-BR')} objetos nesta área. Eles vão copiados para o quadro, na escala dele; a planta do cliente não muda.` }),
      el('label', {}, 'Quadro ', selQ), nome,
      el('label', {}, 'Escala do desenho no quadro ', selE),
      el('label', { class: 'linha' }, subst, ' substituir o que já está no quadro'));
    if (await this.cad.dialogo({ titulo: 'Enviar área para quadro', corpo, ok: 'Enviar' }) !== 'ok') { this.cad.ativarFerramenta('selecionar'); return; }
    let quadroId = selQ.value;
    if (quadroId === '+tesoura') {
      const ult = [...m.quadros].reverse().find(q => q.tipo === 'tesoura');
      const q = { id: novoId(), tipo: 'tesoura', nome: (nome.value || '').trim().toUpperCase(), escala: Number(selE.value), w: TIPOS.tesoura.w, h: TIPOS.tesoura.h, x: 0, y: 0 };
      m.quadros.splice(ult ? m.quadros.indexOf(ult) + 1 : m.quadros.length, 0, q);
      quadroId = q.id;
    }
    const camadas = {};
    for (const e of ents) { const c = this.cad.doc.camadas.get(e.camada); if (c) camadas[e.camada] = { ...c }; }
    const lista = await this._lista(true);
    const orig = lista.find(d => d.nome === this.cad.nomeDesenho) || {};
    let r;
    try {
      r = copiarParaQuadro(mont, quadroId, ents, { escala: Number(selE.value), kOriginal: this.cad.doc.escala, camadas, substituir: subst.checked,
        origem: { desenho: this.cad.nomeDesenho, alterado: orig.alterado || '' } });
      await pedir(this._urlMontagem(), { desenho: mont });
    } catch (e) { this.cad.aviso('Não foi possível enviar para o quadro: ' + e.message, 'erro', 0); this.cad.ativarFerramenta('selecionar'); return; }
    this.mOriginal = mont.metadados.montagem;
    const c = r.conferencia;
    const confTxt = !c.cotas ? 'sem cota com número para conferir a escala'
      : c.batem >= c.cotas / 2 ? `escala conferida: ${c.batem} de ${c.cotas} cotas batem`
      : c.fator ? `ATENÇÃO: as cotas escritas são ${c.fator}× a medida do desenho — o DXF parece estar noutra unidade`
      : `ATENÇÃO: só ${c.batem} de ${c.cotas} cotas batem com a medida do desenho`;
    this.cad.aviso(`${r.copiados.toLocaleString('pt-BR')} objetos no quadro ${rotulo(r.quadro)} (1:${r.quadro.escala})${r.cresceu ? `, que cresceu para caber${r.cabe ? ` (em 1:${r.cabe} caberia no tamanho que tinha)` : ''}` : ''} · ${confTxt}.`,
      c.cotas && c.batem < c.cotas / 2 ? 'atencao' : 'info', 12000);
    this.cad.ativarFerramenta('selecionar');
    this.cad.tela.pedirQuadro();
  }

  /** Enquadra a folha inteira dos quadros. */
  enquadrar() {
    const m = this.m;
    if (!m || !m.quadros.length) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const q of [...m.quadros, m.vaga].filter(Boolean)) {
      x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x + q.w); y1 = Math.max(y1, q.y); y0 = Math.min(y0, q.y - q.h);
    }
    this.cad.tela.enquadrar([[x0, y0], [x1, y1]]);
  }

  // ------------------------------------------------------------------ desenho
  desenhar() {
    this.camada.hidden = !this.ativa;
    if (!this.ativa) { this.camada.replaceChildren(); this._areasNaOriginal(); return; }
    const tela = this.cad.tela, ctx = tela.ctx, m = this.m;
    const ret = (q) => {
      const a = tela.paraTela([q.x, q.y]), b = tela.paraTela([q.x + q.w, q.y - q.h]);
      return [a[0], a[1], b[0] - a[0], b[1] - a[1]];
    };
    ctx.save();
    for (const q of m.quadros) {
      const t = TIPOS[q.tipo] || TIPOS.tesoura;
      const [x, y, w, h] = ret(q);
      ctx.fillStyle = t.cor + '0d';
      ctx.fillRect(x, y, w, h);
      ctx.setLineDash([7, 4]); ctx.lineWidth = 1.6; ctx.strokeStyle = t.cor;
      ctx.strokeRect(x, y, w, h);
    }
    if (m.vaga) {
      const [x, y, w, h] = ret(m.vaga);
      ctx.setLineDash([4, 4]); ctx.lineWidth = 1; ctx.strokeStyle = '#94a3b8';
      ctx.strokeRect(x, y, w, h);
    }
    ctx.restore();
    this._controles(ret);
  }

  /** Na Original: o contorno de cada área já mandada para um quadro, com o nome dele. */
  _areasNaOriginal() {
    if (!this.naOriginal || !this.mOriginal) return;
    const tela = this.cad.tela, ctx = tela.ctx;
    ctx.save();
    ctx.font = '600 11.5px "Segoe UI", sans-serif';
    for (const q of this.mOriginal.quadros) {
      if (!q.fonte || !q.fonte.caixa || q.fonte.desenho !== this.cad.nomeDesenho) continue;
      const t = TIPOS[q.tipo] || TIPOS.tesoura;
      const [[x0, y0], [x1, y1]] = q.fonte.caixa;
      const a = tela.paraTela([x0, y1]), b = tela.paraTela([x1, y0]);
      ctx.setLineDash([6, 4]); ctx.lineWidth = 1.4; ctx.strokeStyle = t.cor;
      ctx.strokeRect(a[0] - 3, a[1] - 3, b[0] - a[0] + 6, b[1] - a[1] + 6);
      ctx.fillStyle = t.cor;
      ctx.fillText('→ ' + t.rotulo + (q.tipo === 'tesoura' && q.nome ? ' ' + q.nome : ''), a[0], a[1] - 7);
    }
    ctx.restore();
  }

  /** Título (tipo, escala, nome), alça de tamanho e o "+ corte tesoura", por cima do canvas. */
  _controles(ret) {
    const m = this.m;
    const vivos = new Set();
    for (const q of m.quadros) {
      const t = TIPOS[q.tipo] || TIPOS.tesoura;
      const [x, y, w, h] = ret(q);
      let c = this.camada.querySelector(`[data-quadro="${q.id}"]`);
      if (!c) {
        const escala = el('select', { class: 'quadro-escala', title: 'A escala do desenho dentro deste quadro: o programa lê em milímetros reais por ela',
          onchange: (ev) => { q.escala = Number(ev.target.value); this._gravar(); } },
          ESCALAS.map(e => el('option', { value: e }, '1:' + e)));
        const nome = q.tipo === 'tesoura'
          ? el('input', { class: 'quadro-nome', placeholder: 'T01', value: q.nome || '', spellcheck: 'false', size: 7,
              title: 'O nome desta tesoura (o da marca na planta): vale mais que o título do desenho',
              onchange: (ev) => { q.nome = ev.target.value.trim().toUpperCase(); ev.target.value = q.nome; this._gravar(); this.cad.tela.pedirQuadro(); },
              onkeydown: (ev) => { ev.stopPropagation(); if (ev.key === 'Enter') ev.target.blur(); } })
          : null;
        const tirar = q.tipo === 'tesoura'
          ? el('button', { type: 'button', class: 'quadro-tirar', title: 'Tirar este quadro de tesoura', onclick: () => this.tirar(q.id) }, '×')
          : null;
        c = el('div', { class: 'quadro-titulo', 'data-quadro': q.id, 'data-tipo': q.tipo, style: `--cor:${t.cor}`, title: t.diz },
          el('b', {}, t.rotulo), nome ? ' · ' : null, nome, ' · ', escala, tirar);
        const alca = el('div', { class: 'quadro-alca', 'data-alca': q.id, title: 'Arraste para ajustar o tamanho do quadro: os outros se acomodam',
          onpointerdown: (ev) => this._pegar(ev, q) });
        this.camada.append(c, alca);
      }
      const sel = c.querySelector('select');
      if (document.activeElement !== sel) sel.value = String(q.escala);
      c.style.left = (x + 4) + 'px'; c.style.top = (y + 4) + 'px';
      c.style.maxWidth = Math.max(60, w - 8) + 'px';
      c.hidden = w < 60 || h < 24;
      const alca = this.camada.querySelector(`[data-alca="${q.id}"]`);
      alca.style.left = (x + w - 9) + 'px'; alca.style.top = (y + h - 9) + 'px';
      const tam = this.camada.querySelector(`[data-tamanho="${q.id}"]`) || this.camada.appendChild(el('div', { class: 'quadro-tamanho', 'data-tamanho': q.id }));
      tam.textContent = `${Math.round(q.w)} × ${Math.round(q.h)}`;
      tam.style.left = (x + w - 4) + 'px'; tam.style.top = (y + h - 4) + 'px';
      tam.hidden = w < 120 || h < 50;
      vivos.add(q.id);
    }
    for (const n of [...this.camada.querySelectorAll('[data-quadro],[data-alca],[data-tamanho]')]) {
      const id = n.dataset.quadro || n.dataset.alca || n.dataset.tamanho;
      if (!vivos.has(id)) n.remove();
    }
    let mais = this.camada.querySelector('.quadro-mais');
    if (!mais) mais = this.camada.appendChild(el('button', { type: 'button', class: 'quadro-mais', title: 'Mais um quadro de tesoura: um para cada tipo de tesoura do projeto', onclick: () => this.maisTesoura() }, '+ corte tesoura'));
    const [x, y, w, h] = ret(m.vaga);
    Object.assign(mais.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
  }

  // ------------------------------------------------------------------ edição
  maisTesoura() {
    const t = TIPOS.tesoura;
    const ult = [...this.m.quadros].reverse().find(q => q.tipo === 'tesoura');
    const q = { id: novoId(), tipo: 'tesoura', nome: '', escala: ult ? ult.escala : t.escala, w: ult ? ult.w : t.w, h: ult ? ult.h : t.h, x: 0, y: 0 };
    const i = this.m.quadros.lastIndexOf(ult);
    if (i >= 0) this.m.quadros.splice(i + 1, 0, q); else this.m.quadros.push(q);
    this._reacomodar();
    this.cad.dica('Quadro de tesoura novo: dê o nome dela no título (o da marca na planta).');
    setTimeout(() => { const n = this.camada.querySelector(`[data-quadro="${q.id}"] input`); if (n) n.focus(); }, 50);
  }

  async tirar(id) {
    const q = this.m.quadros.find(x => x.id === id);
    if (!q) return;
    const dentro = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).quadro === id);
    if (this.m.quadros.filter(x => x.tipo === 'tesoura').length <= 1 && !dentro.length) {
      this.cad.dica('Fica pelo menos um quadro de tesoura.');
      return;
    }
    const corpo = el('div', { class: 'explica', texto: `Tirar o quadro da tesoura ${q.nome || '(sem nome)'}${dentro.length ? ` e os ${dentro.length} objetos dentro dele` : ''}?` });
    if (await this.cad.dialogo({ titulo: 'Tirar quadro', corpo, ok: 'Tirar' }) !== 'ok') return;
    this.cad.doc.lote(() => { for (const e of dentro) this.cad.doc.remover(e.id); });
    this.m.quadros = this.m.quadros.filter(x => x.id !== id);
    this._reacomodar();
  }

  _pegar(ev, q) {
    ev.preventDefault(); ev.stopPropagation();
    this.arrasto = { q, w0: q.w, h0: q.h, p0: this.cad.tela.paraMundo(this._px(ev)), antes: this.m.quadros.map(x => ({ id: x.id, x: x.x, y: x.y })) };
    document.body.classList.add('arrastando-quadro');
  }

  _px(ev) { const r = this.cad.el.canvas.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }

  _mover(ev) {
    if (!this.arrasto) return;
    const a = this.arrasto, p = this.cad.tela.paraMundo(this._px(ev));
    const passo = 5;
    a.q.w = Math.max(MINIMO[0], Math.round((a.w0 + (p[0] - a.p0[0])) / passo) * passo);
    a.q.h = Math.max(MINIMO[1], Math.round((a.h0 - (p[1] - a.p0[1])) / passo) * passo);
    arrumar(this.m);
    this.cad.tela.pedirQuadro();
  }

  _soltar() {
    if (!this.arrasto) return;
    const a = this.arrasto;
    this.arrasto = null;
    document.body.classList.remove('arrastando-quadro');
    // o que está dentro dos quadros que andaram anda junto (o arrumar já mudou x, y: compara com o início)
    const desl = {};
    for (const s of a.antes) {
      const q = this.m.quadros.find(x => x.id === s.id);
      if (q && (q.x !== s.x || q.y !== s.y)) desl[q.id] = [q.x - s.x, q.y - s.y];
    }
    this._moverConteudo(desl);
    this._gravar();
  }

  _reacomodar() {
    const andou = arrumar(this.m);
    this._moverConteudo(andou);
    this._gravar();
    this.cad.tela.pedirQuadro();
  }

  /** O que foi posto num quadro (atributos.quadro) acompanha o quadro que andou. */
  _moverConteudo(desl) {
    const ids = Object.keys(desl || {});
    if (!ids.length) return;
    const doc = this.cad.doc;
    doc.lote(() => {
      for (const e of [...doc.entidades.values()]) {
        const d = desl[(e.atributos || {}).quadro];
        if (!d) continue;
        const n = transformar(e, (p) => [p[0] + d[0], p[1] + d[1]]);
        const { id, ...campos } = n;
        doc.alterar(id, campos);
      }
    });
  }

  /** Grava a montagem logo (o desenho dela pode estar vazio, e a gravação de troca de desenho do CAD não
   *  grava desenho vazio): marca como editado e grava em seguida, juntando as mudanças de um instante. */
  _gravar() {
    if (!this.ativa) return;
    this.cad._editado = true;
    this.cad._versaoEdicao = (this.cad._versaoEdicao || 0) + 1;
    clearTimeout(this._timer);
    this._timer = setTimeout(() => { this._timer = null; this.cad.salvar({ avisar: false }); }, 400);
  }

  async _gravarJa() {
    if (!this._timer) return;
    clearTimeout(this._timer); this._timer = null;
    await this.cad.salvar({ avisar: false });
  }
}

function iniciar() {
  if (!window.cad || document.body.dataset.pronto !== '1') { setTimeout(iniciar, 120); return; }
  if (window.montagem) return;
  window.montagem = new Montagem(window.cad);
}
iniciar();
