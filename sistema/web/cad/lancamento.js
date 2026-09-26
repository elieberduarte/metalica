// CAD 2D: a planta de lançamento (menu Lançamento).
//
// O arquitetônico do cliente entra como referência travada (camadas "ARQ ", cinza: aparece
// e dá snap, mas não se seleciona), a malha de eixos vai para a camada EIXO com bolinhas e
// cotas, e "Gravar eixos no projeto" lê as linhas da camada EIXO (nucleo3d/lancamento.py).
// Depois, "Lançar estrutura no 3D" leva ao editor com o diálogo de lançamento aberto.
//
// Os métodos são copiados para a classe do CAD (cad.js); as duas ferramentas daqui não têm
// botão na barra: o menu as chama.

import { criar, dist, transformar } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoSubstituir } from './nucleo/comandos.js';
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

// ------------------------------------------------------------ métodos do CAD

export class MetodosLancamentoCAD {
  _registrarFerramentasDoLancamento() {
    for (const F of [Calibrar, PegarPonto]) this.ferramentas.set(F.id, new F(this));
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
  }

  /** Depois dos dois pontos da ferramenta Calibrar: pergunta a medida real e escala a referência. */
  async calibrarArquitetonico(a, d) {
    const ents = [...this.doc.entidades.values()].filter(e => String(e.camada).startsWith(PREFIXO_ARQ));
    if (!ents.length) { this.aviso('O desenho não tem arquitetônico (camadas "ARQ …"): importe primeiro.', 'atencao'); return; }
    const real = el('input', { type: 'text', value: '', placeholder: 'ex.: 6000, 6m, 600cm' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `A distância clicada mede ${fmt(d)} mm no desenho. Quanto ela mede na obra? Todo o arquitetônico (${numero(ents.length)} objetos) é escalado em volta do primeiro ponto; os eixos e o resto do desenho ficam como estão.` }),
      el('label', {}, 'Medida real', real));
    if (await this.dialogo({ titulo: 'Calibrar escala do arquitetônico', corpo, ok: 'Escalar' }) !== 'ok') return;
    const alvo = paraMilimetros(real.value);
    if (!alvo || alvo <= 0) { this.aviso('Medida real não entendida: use 6000, 6m ou 600cm.', 'atencao'); return; }
    const k = alvo / d;
    const f = (p) => [a[0] + (p[0] - a[0]) * k, a[1] + (p[1] - a[1]) * k];
    const novas = ents.map(e => transformar(e, f, (x) => x, k));
    this.executar(new ComandoSubstituir(novas, `Calibrar arquitetônico (×${fmt(k * 1000) / 1000})`));
    this.tela.enquadrar();
    this.aviso(`Arquitetônico escalado ${k.toLocaleString('pt-BR', { maximumFractionDigits: 4 })}×: a medida agora é ${fmt(alvo)} mm. Ctrl+Z desfaz.`, 'info', 9000);
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
      el('label', {}, 'Ângulo da malha (graus)', angulo),
      el('label', {}, 'Primeiro número', primeiro), el('label', {}, 'Primeira letra', letra));
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
