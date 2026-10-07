// CAD 2D: a planta de lançamento (menu Lançamento).
//
// O arquitetônico do cliente entra como referência travada (camadas "ARQ ", cinza: aparece
// e dá snap, mas não se seleciona), a malha de eixos vai para a camada EIXO com bolinhas e
// cotas, e "Gravar eixos no projeto" lê as linhas da camada EIXO (nucleo3d/lancamento.py).
// Depois, "Lançar estrutura no 3D" leva ao editor com o diálogo de lançamento aberto.
//
// Os métodos são copiados para a classe do CAD (cad.js); as duas ferramentas daqui não têm
// botão na barra: o menu as chama.

import { criar, dist, transformar, transladar } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoSubstituir, ComandoComposto } from './nucleo/comandos.js';
import { eixosCopiados } from './nucleo/malha.js';
import { Ferramenta, paraMilimetros } from './ferramentas.js';

export const DESENHO_LANCAMENTO = 'planta-de-lançamento';
const PREFIXO_ARQ = 'ARQ ';
const $ = (s, r = document) => r.querySelector(s);
const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1).replace('.', ','));
const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

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

async function postar(rota, corpo) {
  let r;
  try {
    r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo || {}) });
  } catch (e) { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}

function base64DoArquivo(arquivo) {
  return new Promise((ok, erro) => {
    const r = new FileReader();
    r.onerror = () => erro(new Error('não foi possível ler o arquivo.'));
    r.onload = () => { const s = String(r.result || ''); ok(s.slice(s.indexOf(',') + 1)); };
    r.readAsDataURL(arquivo);
  });
}

// ------------------------------------------------------------ ferramentas sem botão

/** Calibrar: dois pontos de uma medida conhecida do arquitetônico; o CAD pergunta a medida
 *  real e escala tudo o que está nas camadas "ARQ " em volta do primeiro ponto. */
export class Calibrar extends Ferramenta {
  static id = 'calibrar'; static nome = 'Calibrar escala do arquitetônico'; static grupo = 'lancamento';
  static dica = 'Calibrar: clique no primeiro ponto de uma medida conhecida do arquitetônico (uma cota, a largura de um vão) · Esc sai';
  reiniciar() { super.reiniciar(); this.a = null; }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Clique no segundo ponto da medida conhecida'); return; }
    const a = this.a, d = dist(a, p);
    this.editor.ativarFerramenta('selecionar');
    if (d >= 1) this.editor.calibrarArquitetonico(a, d);
  }
  onMover(p) {
    if (!this.a) return;
    this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.a, b: p })]);
    this.editor.medida(`${fmt(dist(this.a, p))} mm no desenho`);
  }
}

/** Um clique no desenho devolve o ponto (com snap) a quem pediu (`editor._aoPegarPonto`). */
export class PegarPonto extends Ferramenta {
  static id = 'pegar-ponto'; static nome = 'Pegar ponto'; static grupo = 'lancamento';
  reiniciar() { super.reiniciar(); this.dica(this.editor._dicaPegarPonto || 'Clique no ponto · Esc cancela'); }
  cancelar() { const f = this.editor._aoPegarPonto; this.editor._aoPegarPonto = null; super.cancelar(); if (f) f(null); }
  onPonto(p) {
    const f = this.editor._aoPegarPonto;
    this.editor._aoPegarPonto = null;
    this.editor.ativarFerramenta('selecionar');
    if (f) f(p);
  }
}

// ------------------------------------------------------------ eixo, um por vez

// o eixo da malha (Malha de eixos…): a linha na camada EIXO com `atributos.malha` e o nome; a bolinha e o nome além da
// ponta `a` (nucleo3d/lancamento.py: o raio da bolinha é 5 mm de papel, o nome tem 4 mm)
const ehEixo = (e) => !!(e && e.tipo === 'linha' && e.atributos && e.atributos.malha && e.atributos.eixo && dist(e.a, e.b) > 1e-6);
const dirEixo = (e) => { const L = dist(e.a, e.b); return [(e.b[0] - e.a[0]) / L, (e.b[1] - e.a[1]) / L]; };
const normalEixo = (e) => { const u = dirEixo(e); return [-u[1], u[0]]; };
const ladoDoEixo = (e, q) => { const n = normalEixo(e); return (q[0] - e.a[0]) * n[0] + (q[1] - e.a[1]) * n[1]; };
const paralelosEixos = (x, y) => { const u = dirEixo(x), v = dirEixo(y); return Math.abs(u[0] * v[1] - u[1] * v[0]) < 0.02; };
const RAIO_BOLINHA = 5, ALTURA_NOME = 4;

/** "6000", "3x6000", "6000 6000 7500", "3x6m" → [6000, 6000, …] (mm), ou null */
export function lerVaos(texto) {
  const saida = [];
  for (const parte of String(texto || '').trim().split(/[\s;]+/).filter(Boolean)) {
    const m = parte.match(/^(\d+)\s*[x×*]\s*(.+)$/i);
    const n = m ? parseInt(m[1], 10) : 1;
    const v = paraMilimetros(m ? m[2] : parte);
    if (!(v > 0) || !(n > 0) || n > 200) return null;
    for (let i = 0; i < n; i++) saida.push(v);
  }
  return saida.length ? saida : null;
}

/**
 * Eixo: lança os eixos um por vez (07/10, o usuário: "não tem como lançar um único eixo e ir posicionando enquanto a
 * ferramenta estiver ativa"). Clique num eixo da malha: o seguinte, paralelo, vai com o cursor — clique para pôr, ou
 * digite o vão (6000, 3x6000, 6000 6000 7500) para pôr do lado do cursor; cada eixo novo é a referência do próximo.
 * Clique no vazio: dois pontos fazem um eixo solto (o primeiro da família: 1 ou A). O eixo novo é uma "cópia" do de
 * referência pelo `eixosCopiados` (nucleo/malha.js): o nome na sequência, a bolinha, o nome e a cota até o vizinho;
 * além do último, a cadeia de cotas cresce e os eixos que cruzam esticam. Enter ou Esc termina.
 */
export class Eixo extends Ferramenta {
  static id = 'eixo'; static nome = 'Eixo (um por vez)'; static grupo = 'lancamento';
  static dica = 'Eixo: clique num eixo da malha para lançar o seguinte paralelo a ele, ou dois pontos no vazio para um eixo novo · Esc sai';
  reiniciar() { super.reiniciar(); this.ref = null; this.a = null; }

  _eixoSob(ev) {
    if (!ev || !ev.px || !this.editor.tela.sob) return null;
    const e = this.editor.tela.sob(ev.px);
    const ent = !e ? null : (typeof e === 'object' ? (e.tipo ? e : this.doc.entidades.get(e.id)) : this.doc.entidades.get(e));
    if (ehEixo(ent)) return ent;
    // a bolinha ou o nome do eixo: o eixo deles
    const nome = ent && ent.atributos && (ent.atributos.bolinha || ent.atributos.nome_eixo) ? String(ent.atributos.eixo) : '';
    return nome ? [...this.doc.entidades.values()].find(x => ehEixo(x) && String(x.atributos.eixo) === nome) || null : null;
  }

  _dicaRef() {
    this.dica(`Eixo ${this.ref.atributos.eixo} de referência: clique onde vai o próximo (paralelo) ou digite o vão — 6000, 3x6000, 6000 6000 7500 — ` +
              'do lado do cursor · Enter/Esc termina');
  }

  onPonto(p, ev) {
    if (this.ref) { this._paralelo(ladoDoEixo(this.ref, p)); return; }
    if (!this.a) {
      const e = this._eixoSob(ev);
      if (e) { this.ref = e; this._dicaRef(); return; }
      this.a = p; this.editor.snap.ultimo = p;
      this.dica('Eixo novo: clique no outro ponto (ou digite o comprimento) · Esc cancela');
      return;
    }
    if (dist(this.a, p) < 1) return;
    this._solto(this.a, p);
  }

  onMover(p) {
    if (this.ref) {
      const s = ladoDoEixo(this.ref, p), n = normalEixo(this.ref);
      const linha = criar({ tipo: 'linha', camada: this.ref.camada, a: [this.ref.a[0] + n[0] * s, this.ref.a[1] + n[1] * s],
                            b: [this.ref.b[0] + n[0] * s, this.ref.b[1] + n[1] * s] });
      this.editor.previa([linha]);
      this.editor.medida(`${fmt(Math.abs(s))} mm do eixo ${this.ref.atributos.eixo}`);
      return;
    }
    if (this.a) {
      this.editor.previa([criar({ tipo: 'linha', camada: 'EIXO', a: this.a, b: p })]);
      this.editor.medida(`${fmt(dist(this.a, p))} mm`);
    }
  }

  onValor(t) {
    if (this.ref) {
      const vaos = lerVaos(t);
      if (!vaos) { this.dica('Vão não entendido: use 6000, 3x6000 ou 6000 6000 7500'); return; }
      const cursor = this.editor.tela.cursor;
      const sinal = cursor && ladoDoEixo(this.ref, cursor) < 0 ? -1 : 1;
      for (const v of vaos) if (!this._paralelo(sinal * v)) break;
      return;
    }
    if (this.a) {
      const c = paraMilimetros(t), cursor = this.editor.tela.cursor || [this.a[0] + 1, this.a[1]];
      if (!(c > 0)) return;
      const an = Math.atan2(cursor[1] - this.a[1], cursor[0] - this.a[0]);
      this._solto(this.a, [this.a[0] + c * Math.cos(an), this.a[1] + c * Math.sin(an)]);
    }
  }

  onTecla(ev) { if (ev.key === 'Enter') { this.reiniciar(); return true; } return false; }

  /** o eixo paralelo ao de referência a `s` mm (lado medido); vira a referência do próximo */
  _paralelo(s) {
    if (Math.abs(s) < 1) return false;
    const o = this.ref, n = normalEixo(o);
    const copia = criar({ ...o, id: undefined, a: [o.a[0] + n[0] * s, o.a[1] + n[1] * s], b: [o.b[0] + n[0] * s, o.b[1] + n[1] * s],
                          atributos: { ...(o.atributos || {}) } });
    this._lancar(copia, o);
    return true;
  }

  /** o eixo de `a` a `b`: com eixos paralelos no desenho, entra na família deles (o nome na sequência); sem, começa
   *  uma (1, ou A quando os eixos que ele cruza são numerados) com a bolinha e o nome além de `a` */
  _solto(a, b) {
    const linha = criar({ tipo: 'linha', camada: 'EIXO', a, b, atributos: { malha: true, eixo: '?' } });
    const eixos = [...this.doc.entidades.values()].filter(ehEixo);
    const familia = eixos.filter(e => paralelosEixos(e, linha));
    if (familia.length) {
      const o = familia.reduce((m, e) => (Math.abs(ladoDoEixo(e, a)) < Math.abs(ladoDoEixo(m, a)) ? e : m));
      this._lancar(criar({ ...linha, id: undefined, atributos: { ...(o.atributos || {}) } }), o);
      return;
    }
    const usados = new Set(eixos.map(e => String(e.atributos.eixo)));
    const letras = eixos.length > 0 && eixos.every(e => /^\d+$/.test(String(e.atributos.eixo)));
    let nome;
    if (letras) { let k = 0; do { nome = String.fromCharCode(65 + k++); } while (usados.has(nome) && k < 26); }
    else { let k = 1; while (usados.has(String(k))) k++; nome = String(k); }
    const u = dirEixo(linha), r = RAIO_BOLINHA * (this.doc.escala || 100);
    const centro = [a[0] - u[0] * r, a[1] - u[1] * r];
    const novas = [
      criar({ tipo: 'linha', camada: 'EIXO', a, b, atributos: { malha: true, eixo: nome } }),
      criar({ tipo: 'circulo', camada: 'EIXO', centro, raio: r, atributos: { eixo: nome, bolinha: true } }),
      criar({ tipo: 'texto', camada: 'EIXO', posicao: centro, texto: nome, altura: ALTURA_NOME, alinhamento: 'centro', vertical: 'meio', angulo: 0,
              atributos: { eixo: nome, nome_eixo: true } }),
    ];
    this.editor.executar(new ComandoAdicionar(novas, `Eixo ${nome}`));
    this.a = null;
    this.ref = this.doc.entidades.get(novas[0].id) || novas[0];
    this.editor.previa([]);
    this._dicaRef();
  }

  /** a cota da malha entre o eixo `o` e o paralelo `c`: das pontas `a` (as das bolinhas), um pouco para dentro */
  _cotaEntre(o, c) {
    const E = this.doc.escala || 100, u = dirEixo(o), r = RAIO_BOLINHA * E;
    const s = ladoDoEixo(o, c.a), n = normalEixo(o);
    const p1 = o.a, p2 = [o.a[0] + n[0] * s, o.a[1] + n[1] * s];      // o pé do eixo novo, na altura da ponta do original
    const d = [p2[0] - p1[0], p2[1] - p1[1]], L = Math.hypot(d[0], d[1]) || 1;
    const esq = [-d[1] / L, d[0] / L];                                  // a esquerda do sentido p1 → p2
    const deslocamento = ((u[0] * esq[0] + u[1] * esq[1]) * 3 * r) / E;  // 3 raios para dentro, em mm de papel
    return criar({ tipo: 'cota', camada: 'COTA', modo: 'alinhada', p1, p2, deslocamento, atributos: { malha: true } });
  }

  /** já há cota da malha entre eixos desta família (paralelos a `o`)? Então a cadeia cresce pelo eixosCopiados */
  _temCadeia(o) {
    const lados = [...this.doc.entidades.values()].filter(e => ehEixo(e) && paralelosEixos(e, o)).map(e => ladoDoEixo(o, e.a));
    const noEixo = (q) => lados.some(l => Math.abs(ladoDoEixo(o, q) - l) < 1);
    return [...this.doc.entidades.values()].some(k => k.tipo === 'cota' && k.atributos && k.atributos.malha
      && noEixo(k.p1) && noEixo(k.p2) && Math.abs(ladoDoEixo(o, k.p1) - ladoDoEixo(o, k.p2)) > 1);
  }

  /** acrescenta o eixo `copia` (com o que o eixosCopiados cria e troca) e o deixa como referência */
  _lancar(copia, original) {
    const r = eixosCopiados(this.doc, [copia], [original]);
    const rot = `Eixo ${copia.atributos.eixo}`;
    // a família começou por um eixo solto (sem a cadeia de cotas da malha para crescer): a primeira cota, entre o eixo
    // de referência e o novo, perto da ponta da bolinha; dali em diante a cadeia cresce pelo eixosCopiados
    if (!r.novas.some(x => x.tipo === 'cota') && !r.trocas.some(x => x.tipo === 'cota') && !this._temCadeia(original)) {
      r.novas.push(this._cotaEntre(original, copia));
    }
    const add = new ComandoAdicionar([copia, ...r.novas], rot);
    this.editor.executar(r.trocas.length ? new ComandoComposto([add, new ComandoSubstituir(r.trocas)], rot) : add);
    this.a = null;
    this.ref = this.doc.entidades.get(copia.id) || copia;
    this.editor.previa([]);
    this._dicaRef();
  }
}

// ------------------------------------------------------------ métodos do CAD

export class MetodosLancamentoCAD {
  _registrarFerramentasDoLancamento() {
    for (const F of [Calibrar, PegarPonto, Eixo]) this.ferramentas.set(F.id, new F(this));
  }

  /** A ferramenta Eixo (um por vez): o botão rápido da barra PLANTA e o menu Lançamento. */
  ativarEixoUnico() {
    if (this.doc.camadas && !this.doc.camadas.has('EIXO')) {
      this.doc.camadas.set('EIXO', { nome: 'EIXO', cor: '#d33a3a', visivel: true, bloqueada: false, tipo_linha: 'DASHDOT', espessura: 0.18 });
    }
    this.ativarFerramenta('eixo');
  }

  /** Um ponto clicado no desenho (null se Esc). */
  _pegarPonto(dica) {
    return new Promise((resolver) => {
      this._dicaPegarPonto = dica;
      this._aoPegarPonto = resolver;
      this.ativarFerramenta('pegar-ponto');
    });
  }

  /**
   * Arquitetônico do cliente → Planta de lançamento. DXF: a unidade (pelo arquivo ou
   * informada); PDF vetorial: a escala 1:N (pelas cotas, ou informada). Os eixos e notas
   * que já estavam na planta ficam.
   */
  async importarArquitetonico(arquivo) {
    if (!arquivo) return;
    if (!this.projeto) { this.aviso('O arquitetônico precisa de um projeto aberto.', 'atencao'); return; }
    const pdf = /\.pdf$/i.test(arquivo.name);
    if (!pdf && /\.dwg$/i.test(arquivo.name)) { this.aviso('DWG não é lido: no CAD de origem, salve como DXF.', 'atencao', 0); return; }
    const unidade = el('select', {}, ...[['auto', 'pelo arquivo ($INSUNITS), senão mm'], ['1', 'milímetro'], ['10', 'centímetro'], ['1000', 'metro'], ['25.4', 'polegada']]
      .map(([v, t]) => el('option', { value: v, texto: t })));
    const escala = el('input', { type: 'text', value: '', placeholder: 'pelas cotas (ex.: 100)' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `"${arquivo.name}" (${numero(arquivo.size / 1024, 0)} kB) vira a referência da Planta de lançamento, em milímetro real: camadas "ARQ …" em cinza e travadas (aparecem e dão snap, mas não se selecionam). O desenho é trazido para perto da origem. Depois: Malha de eixos… (ou desenhe as linhas na camada EIXO), Gravar eixos no projeto e Lançar estrutura no 3D.` }),
      pdf ? el('label', {}, 'Escala do PDF, 1:', escala) : el('label', {}, 'Unidade do arquivo', unidade),
      el('div', { class: 'explica', texto: pdf ? 'PDF exportado do CAD (vetorial). Sem escala informada, ela sai das cotas escritas; confira depois com Calibrar escala.'
        : 'Arquitetônico costuma vir em centímetro ou metro com a unidade errada no arquivo: confira a largura na resposta e, se precisar, Calibrar escala.' }));
    if (await this.dialogo({ titulo: 'Arquitetônico do cliente', corpo, ok: 'Importar' }) !== 'ok') return;
    // a planta atual (se aberta) é gravada antes: o servidor mantém os eixos dela
    if (this.nomeDesenho === DESENHO_LANCAMENTO && this._temPendente()) {
      try { await this.gravarConfirmado(); } catch (e) { this.aviso(`Não foi possível gravar a planta antes: ${e.message}`, 'erro', 0); return; }
    }
    const parar = this._acompanharProgresso('Arquitetônico: ');
    this.dica('Lendo o arquitetônico…');
    let r;
    try {
      const n = parseFloat(String(escala.value).replace(',', '.'));
      r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/arquitetonico`, {
        arquivo: arquivo.name, tipo: pdf ? 'pdf' : 'dxf', conteudo_b64: await base64DoArquivo(arquivo),
        fator: !pdf && unidade.value !== 'auto' ? parseFloat(unidade.value) : null, escala: pdf && isFinite(n) && n > 0 ? n : null,
      });
    } catch (e) { parar(); this.dica(''); this.aviso(`Não foi possível importar o arquitetônico: ${e.message}`, 'erro', 0); return; }
    parar();
    this.nomeDesenho = null;                  // a planta foi regravada pelo servidor: abre a nova
    await this.abrirDesenho(r.desenho);
    this.tela.enquadrar();
    const s = r.resumo || {};
    this.aviso(`Arquitetônico na Planta de lançamento: ${numero(s.entidades)} objetos em ${(s.camadas || []).length} camada(s), ` +
      `${numero(s.largura_m, 2)} × ${numero(s.altura_m, 2)} m (${s.escala}, ${s.fonte_escala}). Confira uma medida com Medir (U); ` +
      'se não bater, Lançamento → Calibrar escala.', 'info', 16000);
    for (const a of s.avisos || []) this.aviso(a, 'atencao', 0);
    // o tamanho que não parece de obra: o DXF do Docas veio em centímetro com o cabeçalho dizendo milímetro e a planta
    // entrou com 8,2 m — os eixos foram lançados nela e o pilar de 35 × 70 cm ficou enorme (07/10)
    const maior = Math.max(Number(s.largura_m) || 0, Number(s.altura_m) || 0);
    if (maior > 0 && (maior < 15 || maior > 2000)) {
      this.aviso(`A planta entrou com ${numero(maior, 2)} m no lado maior — ${maior < 15 ? 'pequena demais para uma obra: o arquivo deve estar em centímetro (×10) ou metro (×1000)' : 'grande demais: o arquivo deve estar em outra unidade'}. ` +
        'Antes de lançar os eixos, confira uma cota com Medir e use Lançamento → Calibrar escala (ou importe de novo escolhendo a unidade).', 'atencao', 0);
    }
  }

  /** Depois dos dois pontos da ferramenta Calibrar: pergunta a medida real e escala a referência. */
  async calibrarArquitetonico(a, d) {
    // o arquitetônico importado (camadas "ARQ …"); sem ele, o desenho inteiro — o PDF aberto como desenho comum vem na
    // medida do papel, com os eixos junto, e não havia como calibrar (quadra Kaefer, 06/10)
    const todas = [...this.doc.entidades.values()];
    const arq = todas.filter(e => String(e.camada).startsWith(PREFIXO_ARQ));
    const tudo = !arq.length;
    // o que foi desenhado por cima do arquitetônico (os eixos, as cotas da malha, os elementos lançados) vai junto por
    // padrão: o DXF do Docas veio em centímetro com o cabeçalho dizendo milímetro, a planta entrou 10× menor e os eixos
    // foram lançados nela (07/10) — escalar só a planta deixava os eixos para trás
    const porCima = tudo ? [] : todas.filter(e => !String(e.camada).startsWith(PREFIXO_ARQ));
    const ents = tudo ? todas : arq;
    if (!ents.length) { this.aviso('O desenho está vazio: nada para calibrar.', 'atencao'); return; }
    const real = el('input', { type: 'text', value: '', placeholder: 'ex.: 6000, 6m, 600cm' });
    const junto = el('input', { type: 'checkbox', checked: porCima.length ? true : undefined });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `A distância clicada mede ${fmt(d)} mm no desenho. Quanto ela mede na obra? ${tudo ? `O desenho inteiro (${numero(ents.length)} objetos, eixos e cotas junto) é escalado em volta do primeiro ponto — ele não tem arquitetônico importado.` : `Todo o arquitetônico (${numero(ents.length)} objetos) é escalado em volta do primeiro ponto.`}` }),
      el('label', {}, 'Medida real', real),
      porCima.length ? el('label', { class: 'opcao-linha', style: 'flex-direction: row; align-items: flex-start; gap: 6px; line-height: 1.4' }, junto,
        ` Escalar junto o que foi desenhado por cima (${numero(porCima.length)} objetos: eixos, cotas da malha, elementos lançados) — pilares, fundações e bolinhas mudam só de lugar, sem mudar de tamanho`) : null);
    if (await this.dialogo({ titulo: 'Calibrar escala do arquitetônico', corpo, ok: 'Escalar' }) !== 'ok') return;
    const alvo = paraMilimetros(real.value);
    if (!alvo || alvo <= 0) { this.aviso('Medida real não entendida: use 6000, 6m ou 600cm.', 'atencao'); return; }
    const k = alvo / d;
    const f = (p) => [a[0] + (p[0] - a[0]) * k, a[1] + (p[1] - a[1]) * k];
    const novas = ents.map(e => transformar(e, f, (x) => x, k));
    if (porCima.length && junto.checked) {
      // o tamanho real (o pilar 35 × 70, a bolinha de 5 mm de papel) fica; muda o lugar
      const soLugar = (e) => { const at = e.atributos || {}; return ['pilar', 'fundacao', 'consolo'].includes(at.elemento) || at.bolinha; };
      const centro = (e) => {
        const at = e.atributos || {};
        if (Array.isArray(at.centro)) return at.centro;
        if (e.centro) return e.centro;
        const pts = e.vertices || (e.a ? [e.a, e.b] : e.posicao ? [e.posicao] : []);
        return pts.length ? [pts.reduce((s_, q) => s_ + q[0], 0) / pts.length, pts.reduce((s_, q) => s_ + q[1], 0) / pts.length] : null;
      };
      // a bolinha e o nome do eixo vão com a ponta do eixo deles (a mesma folga de papel além dela); o rótulo do elemento
      // (P1) vai com o elemento
      const eixoDe = new Map(porCima.filter(ehEixo).map(e => [String(e.atributos.eixo), e]));
      const desloc = new Map();
      const mover = (_e, de) => { const para = f(de); return [para[0] - de[0], para[1] - de[1]]; };
      for (const e of porCima) {
        const at = e.atributos || {};
        if ((at.bolinha || at.nome_eixo) && eixoDe.has(String(at.eixo))) {
          const x = eixoDe.get(String(at.eixo)), q = e.centro || e.posicao;
          desloc.set(e.id, mover(e, dist(q, x.a) <= dist(q, x.b) ? x.a : x.b));
        } else if (soLugar(e)) {
          const c = centro(e);
          if (c) desloc.set(e.id, mover(e, c));
        }
      }
      for (const e of porCima) {
        const at = e.atributos || {};
        const d = desloc.get(e.id) || (at.rotulo_de && desloc.get(at.rotulo_de));
        if (d) {
          const n = transladar(e, d);
          if (Array.isArray(at.centro)) n.atributos = { ...n.atributos, centro: [at.centro[0] + d[0], at.centro[1] + d[1]] };
          novas.push(n);
        } else novas.push(transformar(e, f, (x) => x, k));
      }
    }
    const cmd = new ComandoSubstituir(novas, `Calibrar arquitetônico (×${fmt(k * 1000) / 1000})`);
    cmd.semTrava = true;                          // o arquitetônico fica na camada travada: a calibração é do programa
    this.executar(cmd);
    this.tela.enquadrar();
    this.aviso(`${tudo ? 'Desenho' : 'Arquitetônico'} escalado ${k.toLocaleString('pt-BR', { maximumFractionDigits: 4 })}×: a medida agora é ${fmt(alvo)} mm. Ctrl+Z desfaz.`, 'info', 9000);
  }

  /** Malha de eixos: vãos entre os eixos numerados (pórticos) e entre os com letra (filas de pilares). */
  async dialogoMalha(valores = {}) {
    if (!this.projeto) { this.aviso('A malha de eixos precisa de um projeto aberto.', 'atencao'); return; }
    const v = { x: '0', y: '0', numeros: '5x6000', letras: '15000', angulo: '0', primeiro: '1', letra: 'A', ...valores };
    const x = el('input', { type: 'text', value: v.x }), y = el('input', { type: 'text', value: v.y });
    const numeros = el('input', { type: 'text', value: v.numeros, placeholder: '5x6000 ou 6000 6000 7500' });
    const letras = el('input', { type: 'text', value: v.letras, placeholder: '15000 ou 2x10m' });
    const angulo = el('input', { type: 'text', value: v.angulo });
    const primeiro = el('input', { type: 'text', value: v.primeiro }), letra = el('input', { type: 'text', value: v.letra });
    let pegar = false;
    const botaoPegar = el('button', { type: 'button', texto: 'Pegar no desenho', onclick: () => { pegar = true; $('#dialogo-cancelar').click(); } });
    const corpo = el('div', { class: 'grade-malha' },
      el('div', { class: 'explica', texto: 'Os eixos numerados são as linhas dos pórticos (1, 2, 3… ao longo do galpão); os com letra, as filas de pilares (A, B… atravessadas). Vãos como 5x6000, 6000 6000 7500 ou 3x6m. A origem é o cruzamento do primeiro número com a primeira letra.' }),
      el('label', {}, 'Origem X (mm)', x), el('label', {}, 'Origem Y (mm)', y), botaoPegar,
      el('label', {}, 'Vãos entre os eixos numerados', numeros),
      el('label', {}, 'Vãos entre os eixos com letra', letras),
      el('label', {}, 'Primeiro número', primeiro), el('label', {}, 'Primeira letra', letra),
      el('label', {}, 'Ângulo da malha (graus)', angulo));
    const r = await this.dialogo({ titulo: 'Malha de eixos', corpo, ok: 'Desenhar a malha' });
    const lidos = { x: x.value, y: y.value, numeros: numeros.value, letras: letras.value, angulo: angulo.value, primeiro: primeiro.value, letra: letra.value };
    if (pegar) {
      const p = await this._pegarPonto('Clique na origem da malha: o cruzamento do primeiro eixo numerado com o primeiro com letra (o centro do pilar do canto) · Esc cancela');
      if (p) { lidos.x = fmt(p[0]); lidos.y = fmt(p[1]); }
      return this.dialogoMalha(lidos);
    }
    if (r !== 'ok') return;
    const num = (s) => parseFloat(String(s).replace(',', '.')) || 0;
    let m;
    try {
      m = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento/malha`, {
        origem: [num(lidos.x), num(lidos.y)], vaos_numeros: lidos.numeros, vaos_letras: lidos.letras,
        angulo: num(lidos.angulo), escala: this.doc.escala, primeiro_numero: parseInt(lidos.primeiro, 10) || 1,
        primeira_letra: String(lidos.letra || 'A').trim().toUpperCase() || 'A' });
    } catch (e) { this.aviso(`Não foi possível montar a malha: ${e.message}`, 'erro', 0); return; }
    for (const [nome, c] of Object.entries(m.camadas || {})) if (!this.doc.camadas.has(nome)) this.doc.camadas.set(nome, { nome, cor: c.cor, visivel: true, bloqueada: false, tipo_linha: c.tipo_linha || 'CONTINUOUS', espessura: c.espessura || 0.18 });
    const novas = (m.entidades || []).map(e => criar({ ...e, id: undefined }));
    this.executar(new ComandoAdicionar(novas, `Malha de eixos (${novas.length})`));
    this.tela.enquadrar();
    this.aviso('Malha desenhada na camada EIXO (Ctrl+Z desfaz). Ajuste o que precisar — mova, apague ou desenhe linhas na camada EIXO — e use Lançamento → Gravar eixos no projeto.', 'info', 12000);
  }

  /** Lê os eixos da camada EIXO deste desenho e grava no projeto. */
  async gravarEixos() {
    if (!this.projeto) { this.aviso('Gravar eixos precisa de um projeto aberto.', 'atencao'); return; }
    let r;
    try {
      r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/lancamento/eixos`, { desenho: this.doc.paraJSON() });
    } catch (e) { this.aviso(`Não foi possível ler os eixos: ${e.message}`, 'erro', 0); return false; }
    const ex = r.eixos, g = r.geometria;
    this.aviso(`Eixos gravados no projeto: ${ex.numeros.map(e => e.nome).join(', ')} e ${ex.letras.map(e => e.nome).join(', ')}` +
      (g ? ` — vão ${numero(g.vao / 1000, 2)} m, ${g.espacamentos.length} vão(s) entre pórticos, ${numero(g.comprimento / 1000, 2)} m de comprimento.` : '.') +
      ' Agora: Lançamento → Lançar estrutura no 3D.', 'info', 16000);
    for (const a of r.avisos || []) this.aviso(a, 'atencao', 0);
    return true;
  }

  /** Grava a planta, grava os eixos e abre o 3D com o diálogo Lançar estrutura. */
  async lancarNo3D() {
    if (!this.projeto) return;
    if (!(await this.gravarEixos())) return;
    await this._sairPara(`/editor?projeto=${encodeURIComponent(this.projeto)}&lancar=1`);
  }

  /** Abre a planta de lançamento (ou avisa que ainda não há). */
  async abrirPlantaDeLancamento() {
    const lista = await this._listaDesenhos();
    if (lista.some(d => d.nome === DESENHO_LANCAMENTO)) { await this.abrirDesenho(DESENHO_LANCAMENTO); return; }
    this.aviso('O projeto ainda não tem planta de lançamento: use Lançamento → Arquitetônico do cliente (DXF/PDF)…', 'atencao', 0);
  }
}
