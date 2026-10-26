// Ferramentas do CAD 2D.
//
// Cada ferramenta é uma máquina de estados que recebe pontos já resolvidos pelo snap
// (em milímetro), nunca coordenadas de tela. Toda alteração passa por `editor.executar`.
// Medida digitada (`onValor`): "1500", "1,5m", "150cm", "@30" (ângulo), e para
// retângulo "2000;1000". Esc cancela, Enter/espaço confirma ou repete.

import { criar, dist, meio, transladar, transformar, clonar, pontosDe, segmentosDe, intersecaoSeg, maisProximoSeg, dentroDe, pontosCota, pontosArco, caixaDe, CAMADAS_PADRAO, filhosDoBloco,
  distanciaEntidade, ramosDaChamada, fracaoNaChamada } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoRemover, ComandoSubstituir, ComandoComposto, ComandoAlterar } from './nucleo/comandos.js';
import { acompanharMalha, eixosCopiados } from './nucleo/malha.js';
import { medidaDaCotaEspecial } from './nucleo/cota_especial.js';
import { simboloSolda, simboloBalao, simboloNivel, simboloDetalhe, textoDoNivel, simboloPonto, pontosDaDivisao, simboloNuvem } from './nucleo/simbolos.js';

// A unidade das medidas (07/10, o usuário: "ajustei a escala do desenho para cm para trabalhar com todas as medidas em
// cm"). O desenho é sempre em milímetro e a "Escala 1:" é a de impressão; a unidade muda só o número digitado sem
// unidade, as medidas que as ferramentas mostram e o número das cotas novas. Gravada no desenho (metadados.unidade_medidas).
export const UNIDADES = { mm: 1, cm: 10, m: 1000 };
let unidadeMedidas = 'mm';
export function definirUnidade(nome) { unidadeMedidas = UNIDADES[nome] ? nome : 'mm'; }
export const unidadeAtual = () => unidadeMedidas;
export const fatorDaUnidade = () => UNIDADES[unidadeMedidas];
/** mm → o número na unidade das medidas, com vírgula: 4750 → "475" (cm), "4,75" (m) */
export function naUnidade(mm) {
  const casas = unidadeMedidas === 'm' ? 3 : 1, k = 10 ** casas;
  return String(Math.round(mm / UNIDADES[unidadeMedidas] * k) / k).replace('.', ',');
}
/** A medida (mm) na unidade das medidas, com o nome dela: "1.300 mm", "130 cm", "1,3 m". */
const medidaComUnidade = (mm) => (unidadeMedidas === 'mm' ? `${fmt(mm)} mm` : `${naUnidade(mm)} ${unidadeMedidas}`);
/** Só o número (o Δx do Medir), na unidade das medidas. */
const numeroNaUnidade = (mm) => (unidadeMedidas === 'mm' ? fmt(mm) : naUnidade(mm));
/** O texto da caixa MEDIDAS na unidade das medidas: os números até o último "mm" ("4.750 mm", "35 × 70 mm", "R 120 · corda 300 mm")
 *  convertidos; ângulo (30°), nome de eixo ("A:", "do eixo 1", depois do mm) e fator (×2) ficam. */
export function textoNaUnidade(t) {
  const s = String(t || '');
  const fim = s.lastIndexOf(' mm');
  if (unidadeMedidas === 'mm' || fim < 0) return s;
  const ate = s.slice(0, fim).replace(/(^|[\s(])(-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?)(?![\d,.]|\s*[°:])/g,
    (m0, pre, num) => pre + naUnidade(parseFloat(num.replace(/\.(?=\d{3})/g, '').replace(',', '.'))));
  return ate.replace(/ mm(?![a-z])/g, ' ' + unidadeMedidas) + ' ' + unidadeMedidas + s.slice(fim + 3);
}

export function paraMilimetros(texto) {
  let t = String(texto || '').trim().toLowerCase().replace(/\s+(?=(mm|cm|m)$)/, '');
  // ponto de milhar ("1.500", "12.000 mm", "1.500,5"): no Brasil a vírgula é a decimal
  const semUnidade = t.replace(/(mm|cm|m)$/, '');
  const unidade = t.slice(semUnidade.length);
  if (semUnidade.includes(',') && semUnidade.includes('.')) t = semUnidade.replace(/\./g, '') + unidade;
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(semUnidade) && (unidade === '' || unidade === 'mm')) t = semUnidade.replace(/\./g, '') + unidade;
  t = t.replace(',', '.');
  const m = t.match(/^(-?\d+(?:\.\d+)?)\s*(mm|cm|m)?$/);
  if (!m) return null;
  const v = parseFloat(m[1]);
  return m[2] === 'm' ? v * 1000 : m[2] === 'cm' ? v * 10 : m[2] === 'mm' ? v : v * UNIDADES[unidadeMedidas];   // sem unidade: a das medidas
}

const ang = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
const polar = (a, angulo, d) => [a[0] + d * Math.cos(angulo), a[1] + d * Math.sin(angulo)];
const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1).replace('.', ','));
const valorDaCota = (c) => (c.modo === 'h' ? Math.abs(c.p2[0] - c.p1[0]) : c.modo === 'v' ? Math.abs(c.p2[1] - c.p1[1]) : dist(c.p1, c.p2));
const ESCALAS_COTA = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150, 200, 250, 500];
/** Quanto o número escrito da cota vale por mm desenhado: 1 no desenho comum; na prancha, a escala da célula (a
 *  cota "858" de uma tesoura em 1:25 mede 34,3 mm no papel). Pela proporção escrito ÷ medido, encostada na escala
 *  padrão mais perto — a cota da prancha editada continua em mm da peça (pedido do usuário, 01/10: "quando faço um
 *  ajuste de cota na prancha ele muda todo o valor"). */
function fatorDaCota(c) {
  if (c.escala > 0) return c.escala;                 // a escala escolhida na cota
  const escrito = parseFloat(String(c.texto ?? '').replace(',', '.'));
  const medido = valorDaCota(c);
  if (!(escrito > 0) || !(medido > 1e-6)) return 1;
  const r = escrito / medido;
  const perto = ESCALAS_COTA.reduce((m, s) => (Math.abs(s / r - 1) < Math.abs(m / r - 1) ? s : m), 1);
  return Math.abs(perto / r - 1) < 0.04 ? perto : r;
}
/** O número da cota escrita depois de mexer nela (`antes` é a cota como estava): na mesma proporção. */
function textoNovoDaCota(antes, nova) {
  return String(Math.round(valorDaCota(nova) * fatorDaCota(antes)));
}

export class Ferramenta {
  static id = 'base'; static nome = 'Ferramenta'; static atalho = ''; static grupo = 'desenho'; static dica = '';
  constructor(editor) { this.editor = editor; }
  get doc() { return this.editor.doc; }
  get camada() { return this.editor.camadaAtiva; }
  ativar() { this.reiniciar(); }
  desativar() { this.editor.previa([]); this.editor.snap.ultimo = null; }
  reiniciar() { this.editor.previa([]); this.editor.snap.ultimo = null; this.dica(this.constructor.dica); this.editor.medida(''); }
  cancelar() { this.reiniciar(); }
  onPonto(p, ev) {}
  onMover(p, ev) {}
  onValor(texto) {}
  onTecla(ev) { return false; }
  onSoltar(p, ev) {}
  /** Ctrl+Z no meio da ferramenta: devolva true se desfez um passo dela (o ponto clicado), sem mexer no desenho. */
  desfazerPasso() { return false; }
  /** Depois de um Ctrl+Z que desfez um comando do desenho (`c`), a ferramenta acerta o estado dela. */
  aposDesfazer(c) {}
  /** Os trechos já fixados do objeto que está sendo desenhado ([[a, b], …]): o snap os enxerga como linhas (os vértices
   *  da polilinha em andamento — usuário, 25/10: "ela não reconhece os nós para se ligar"). */
  trechosEmAndamento() { return []; }
  dica(t) { this.editor.dica(t); }
  novaEntidade(reg) { return criar({ ...reg, camada: reg.camada || this.camada }); }
}

/** Os trechos entre pontos seguidos. */
const trechosDe = (pts) => pts.slice(1).map((q, i) => [pts[i], q]);

// ------------------------------------------------------------ selecionar

/** Deslocamento (mm de papel) que põe a linha da cota `c` passando por `p`. */
function deslocamentoPara(c, p, escala) {
  let [x1, y1] = c.p1, [x2, y2] = c.p2;
  if (c.modo === 'h') y2 = y1; else if (c.modo === 'v') x2 = x1;
  const dx = x2 - x1, dy = y2 - y1, k = Math.hypot(dx, dy) || 1;
  let desl = (-(dy / k) * (p[0] - x1) + (dx / k) * (p[1] - y1)) / escala;
  if (Math.abs(desl) < 2) desl = desl < 0 ? -2 : 2;
  return desl;
}

export class Selecionar extends Ferramenta {
  static id = 'selecionar'; static nome = 'Selecionar'; static atalho = ' '; static grupo = 'navegacao';
  static dica = 'Clique seleciona (a peça inteira; Alt+clique, só a linha) · Shift soma · Ctrl alterna · arraste uma janela (com Shift ou Ctrl, soma) · Del apaga · arraste as alças (pontas das linhas, vértices, cotas; o meio da linha a move — no eixo da malha, com a bolinha e as cotas)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 3l14 8-6 2-3 6z"/></svg>';
  reiniciar() { this._soltarAlca(); super.reiniciar(); }

  // ---- alças: na cota, a do meio leva a linha de cota e as das pontas o ponto medido; na
  // linha e na polilinha, a alça leva aquela ponta (ou vértice) até o novo ponto
  onPressionar(p, ev) {
    if (this.alca) return true;               // alça já presa ao cursor: este clique a solta
    const a = this.editor.tela.alcaSob(ev.px);
    if (!a) return false;
    this._pegarAlca(a);
    this._recemPega = true;                   // o soltar deste mesmo clique não conta
    return true;
  }
  _pegarAlca(a) {
    this.alca = a;
    this.editor.tela.alcaQuente = a;
    this.editor.snap.ignorar = new Set([a.id]);
    const e = this.doc.get(a.id);
    if (e && e.tipo === 'arco') {
      this.dica(a.parte === 'curva' ? 'Leve o meio do arco: a flecha muda e as pontas ficam (o snap pega o ponto por onde ele deve passar) · Esc cancela'
        : 'Leve a ponta do arco: ela anda na mesma curva, encurtando ou alongando (o snap pega a interseção) · Esc cancela');
      return;
    }
    if (e && e.tipo === 'chamada') {
      this.dica(a.parte === 'texto' ? 'Leve o texto da chamada para onde ele fica legível — a linha acompanha, a seta fica · Esc cancela'
        : a.parte.startsWith('ramo') ? 'Leve a ponta desta seta até o ponto apontado — ela continua saindo do mesmo ponto da linha · Esc cancela'
        : 'Leve a ponta da seta até o ponto apontado (extremidade, interseção…) · Esc cancela');
      return;
    }
    if (e && e.tipo === 'cota_especial') {
      this.dica(e.modo === 'angular' ? 'Leve o arco do ângulo para onde ele fica (o lado do ângulo segue o cursor) · Esc cancela'
        : e.modo === 'ordenada' ? 'Leve o número da ordenada (a chamada acompanha) · Esc cancela' : 'Leve o número: a seta corre pelo círculo · Esc cancela');
      return;
    }
    if (a.parte === 'meio') {
      const eixo = this._eixoDaMalha(e);
      this.editor.snap.ultimo = a.ponto;
      if (eixo) {
        const n = this._normalDoEixo(eixo);
        this.editor.snap.direcoes = [n];
        this.dica(`Leve o eixo ${eixo.atributos.eixo} para a nova posição (anda atravessado; a bolinha e as cotas da malha acompanham) · digite a distância a mover · Esc cancela`);
      } else this.dica('Leve a linha para a nova posição · digite a distância a mover · Esc cancela');
      return;
    }
    if (e && e.tipo !== 'cota') {
      // a outra ponta do trecho fica fixa: o snap segue a continuação dele (a ponta anda
      // reta, esticando ou encurtando a linha) e pega extremidades, interseções…
      const fixo = this._vizinhoFixo(e, a.parte);
      if (fixo) {
        const d = dist(fixo, a.ponto);
        this.editor.snap.ultimo = fixo;
        this.editor.snap.direcoes = d > 1e-6 ? [[(a.ponto[0] - fixo[0]) / d, (a.ponto[1] - fixo[1]) / d]] : [];
      }
      this.dica('Leve a ponta até o novo ponto (extremidade, interseção…); perto da continuação ela segue reta · digite o comprimento · Esc cancela');
      return;
    }
    this.dica(a.parte === 'texto' ? 'Leve o número da cota para onde ele fica legível · Esc cancela'
      : a.parte === 'linha'
      ? 'Leve a linha de cota até a posição (o snap pega a linha de outra cota) · Esc cancela'
      : 'Leve o ponto de referência da cota até o novo ponto (extremidade, interseção…) · Esc cancela');
  }
  _soltarAlca() {
    this.alca = null;
    this.editor.tela.alcaQuente = null;
    this.editor.snap.ignorar = new Set();
    this.editor.snap.ultimo = null;
    this.editor.snap.direcoes = [];
  }
  /** A outra ponta do trecho da alça (fica parada enquanto a alça anda). */
  _vizinhoFixo(e, parte) {
    if (e.tipo === 'linha') return parte === 'a' ? e.b : e.a;
    if (e.tipo === 'polilinha') {
      const i = Number(parte.slice(1)), n = e.vertices.length;
      if (n < 2) return null;
      if (i > 0) return e.vertices[i - 1];
      return e.fechada ? e.vertices[n - 1] : e.vertices[1];
    }
    if (e.tipo === 'chamada' && parte.startsWith('ramo')) { const r = ramosDaChamada(e)[Number(parte.slice(4))]; return r ? r[0] : null; }
    return null;
  }
  /** A linha do eixo da malha (Lançamento → Malha de eixos: camada EIXO, com o nome do eixo), ou null. */
  _eixoDaMalha(e) {
    const a = (e && e.atributos) || {};
    return e && e.tipo === 'linha' && a.malha && a.eixo && dist(e.a, e.b) > 1e-6 ? e : null;
  }
  _normalDoEixo(e) {
    const L = dist(e.a, e.b);
    return [-(e.b[1] - e.a[1]) / L, (e.b[0] - e.a[0]) / L];
  }
  /**
   * A alça do meio levada a `p`: a linha anda inteira. No eixo da malha (pedido do usuário, 06/10: "mover só
   * selecionando o meio da malha e ela ajuste as cotas"), só atravessado, e vão junto a bolinha e o nome dele, as
   * pontas das cotas da malha que estão no eixo (a medida muda; a que corre ao longo dele vai inteira) e, se ele é o
   * último daquele lado, as pontas dos eixos que o cruzam (com as bolinhas), para a folga além dele continuar a mesma.
   */
  _movidas(p) {
    const e = this.doc.get(this.alca.id);
    if (!e || e.tipo !== 'linha') return [];
    const m = this.alca.ponto;
    const eixo = this._eixoDaMalha(e);
    let d = [p[0] - m[0], p[1] - m[1]];
    if (eixo) { const n = this._normalDoEixo(eixo), s = d[0] * n[0] + d[1] * n[1]; d = [n[0] * s, n[1] * s]; }
    if (Math.hypot(d[0], d[1]) < 1e-6) return [];
    const nova = transladar(e, d);
    return eixo ? [nova, ...acompanharMalha(this.doc, [nova])] : [nova];
  }
  /** A medida durante o arrasto do eixo: quanto andou e a distância aos vizinhos de cada lado. */
  _medidaDoEixo(p) {
    const e = this.doc.get(this.alca.id), eixo = this._eixoDaMalha(e);
    const m = this.alca.ponto;
    if (!eixo) { this.editor.medida(`${fmt(dist(m, p))} mm`); return; }
    const n = this._normalDoEixo(eixo);
    const s = (p[0] - m[0]) * n[0] + (p[1] - m[1]) * n[1];
    const u = [n[1], -n[0]];
    const viz = [];
    for (const x of this.doc.entidades.values()) {
      if (x.id === eixo.id || !this._eixoDaMalha(x)) continue;
      const L = dist(x.a, x.b);
      if (Math.abs(((x.b[0] - x.a[0]) * u[1] - (x.b[1] - x.a[1]) * u[0]) / L) >= 0.02) continue;
      viz.push([(x.a[0] - eixo.a[0]) * n[0] + (x.a[1] - eixo.a[1]) * n[1] - s, x.atributos.eixo]);
    }
    const ant = viz.filter(v => v[0] < 0).sort((a, b) => b[0] - a[0])[0], dep = viz.filter(v => v[0] > 0).sort((a, b) => a[0] - b[0])[0];
    const partes = [`moveu ${fmt(Math.abs(s))} mm`];
    if (ant) partes.push(`${ant[1]}: ${fmt(-ant[0])} mm`);
    if (dep) partes.push(`${dep[1]}: ${fmt(dep[0])} mm`);
    this.editor.medida(partes.join(' · '));
  }
  /** A entidade da alça com a ponta levada a `p` (linha, polilinha ou cota). */
  _editada(p) {
    const e = this.doc.get(this.alca.id);
    if (!e) return null;
    if (this.alca.parte === 'meio') return this._movidas(p)[0] || null;
    if (e.tipo === 'linha') {
      const nova = { ...e, [this.alca.parte]: [p[0], p[1]] };
      return dist(nova.a, nova.b) < 1e-6 ? null : criar(nova);
    }
    if (e.tipo === 'polilinha') {
      const i = Number(this.alca.parte.slice(1));
      const vertices = e.vertices.map((v, k) => (k === i ? [p[0], p[1]] : v));
      return criar({ ...e, vertices });
    }
    if (e.tipo === 'arco') return arcoPelaAlca(e, this.alca.parte, p);
    if (e.tipo === 'cota_especial') {
      // a posição do número (e do arco do ângulo); no raio e no diâmetro, a seta vai para o ponto do círculo na direção dela
      const n = { ...e, posicao: [p[0], p[1]] };
      if (e.modo === 'raio' || e.modo === 'diametro') {
        const R = dist(e.centro, e.p1), d = dist(e.centro, p);
        if (d > 1e-9) n.p1 = [e.centro[0] + (p[0] - e.centro[0]) / d * R, e.centro[1] + (p[1] - e.centro[1]) / d * R];
      }
      return criar(n);
    }
    if (e.tipo === 'chamada') {
      if (this.alca.parte === 'alvo') return criar({ ...e, alvo: [p[0], p[1]] });
      if (this.alca.parte.startsWith('ramo')) {
        const i = Number(this.alca.parte.slice(4));
        return criar({ ...e, ramos: (e.ramos || []).map((r, j) => (j === i ? { ...r, alvo: [p[0], p[1]] } : r)) });
      }
      // o meio do texto vai para o cursor: a posição (o joelho da linha) sai dele, do lado em que o
      // texto fica (à direita da seta, o texto sai para a direita)
      const k = this.doc.escala, h = (e.altura || 2.5) * k;
      const w = Math.max(h, (e.texto || '').length * h * 0.65);
      const s = p[0] >= e.alvo[0] ? 1 : -1;
      return criar({ ...e, posicao: [p[0] - s * (9.5 * k + w / 2), p[1] - 0.8 * k - h / 2] });
    }
    return this._cotaEditada(p);
  }
  _cotaEditada(p) {
    const c = this.doc.get(this.alca.id);
    if (!c) return null;
    const k = this.doc.escala;
    // a alça do texto leva só o número; a da linha leva a linha (e o número volta ao meio dela)
    if (this.alca.parte === 'texto') return criar({ ...c, texto_pos: [p[0], p[1]] });
    if (this.alca.parte === 'linha') return criar({ ...c, deslocamento: deslocamentoPara(c, p, k), texto_pos: null });
    // muda o ponto medido e mantém a linha de cota onde estava
    const pc = pontosCota(c, k);
    const naLinha = pc.length === 4 ? pc[this.alca.parte === 'p1' ? 2 : 3] : null;
    const nova = { ...c, [this.alca.parte]: [p[0], p[1]] };
    if (dist(nova.p1, nova.p2) < 1e-6) return null;
    if (naLinha) nova.deslocamento = deslocamentoPara(nova, naLinha, k);
    // cota com o valor escrito (as do detalhamento, arredondadas ao mm): o texto acompanha a medida nova
    if (nova.texto != null && /^\s*\d+(?:[.,]\d+)?\s*$/.test(String(nova.texto))) nova.texto = textoNovoDaCota(c, nova);
    return criar(nova);
  }
  onMover(p) {
    if (!this.alca) return;
    if (this.alca.parte === 'meio') { this.editor.previa(this._movidas(p)); this._medidaDoEixo(p); return; }
    const c = this._editada(p);
    this.editor.previa(c ? [c] : []);
    if (!c) return;
    if (c.tipo === 'cota') {
      // a cota na unidade das medidas (escala 1/10 em cm): a medida real, que a caixa mostra na unidade
      const fc = fatorDaCota(this.doc.get(this.alca.id) || c);
      this.editor.medida(`${fmt(valorDaCota(c) * (Math.abs(fc * UNIDADES[unidadeMedidas] - 1) < 1e-9 ? 1 : fc))} mm`);
    }
    else if (c.tipo === 'arco') { const g = geometriaDoArco(c); this.editor.medida(`R ${fmt(c.raio)} · corda ${fmt(g.corda)} · flecha ${fmt(g.flecha)} mm`); }
    else {
      const fixo = this._vizinhoFixo(this.doc.get(this.alca.id), this.alca.parte);
      if (fixo) this.editor.medida(`${fmt(dist(fixo, p))} mm`);
    }
  }
  /** Comprimento digitado: a ponta vai na direção do cursor (ou da própria linha), a essa
   *  distância da outra ponta do trecho. */
  onValor(t) {
    if (!this.alca) return;
    const e = this.doc.get(this.alca.id);
    if (this.alca.parte === 'meio') {
      // a distância a mover, para o lado do cursor (no eixo da malha, atravessado)
      const v = paraMilimetros(t), m = this.alca.ponto;
      if (!e || v == null || v <= 0) return;
      const alvo = this.editor.tela.cursor || m;
      let dir = [alvo[0] - m[0], alvo[1] - m[1]];
      const eixo = this._eixoDaMalha(e);
      if (eixo) { const n = this._normalDoEixo(eixo); const s = dir[0] * n[0] + dir[1] * n[1]; dir = s < 0 ? [-n[0], -n[1]] : n; }
      const L = Math.hypot(dir[0], dir[1]);
      if (L < 1e-6) return;
      this._recemPega = false;
      this.onPonto([m[0] + dir[0] / L * v, m[1] + dir[1] / L * v], {});
      return;
    }
    const fixo = e && e.tipo !== 'cota' ? this._vizinhoFixo(e, this.alca.parte) : null;
    const v = paraMilimetros(t);
    if (!fixo || v == null || v <= 0) return;
    const alvo = this.editor.tela.cursor || this.alca.ponto;
    let dx = alvo[0] - fixo[0], dy = alvo[1] - fixo[1];
    if (Math.hypot(dx, dy) < 1e-6) { dx = this.alca.ponto[0] - fixo[0]; dy = this.alca.ponto[1] - fixo[1]; }
    const n = Math.hypot(dx, dy) || 1;
    this._recemPega = false;
    this.onPonto([fixo[0] + dx / n * v, fixo[1] + dy / n * v], {});
  }
  cancelar() { this._soltarAlca(); super.cancelar(); }

  onPonto(p, ev) {
    if (this.alca) {
      if (ev.semMover && this._recemPega) { this._recemPega = false; return; }   // clicou na alça: agora ela segue o cursor
      this._recemPega = false;
      if (this.alca.parte === 'meio') {
        const novas = this._movidas(p);
        const eixo = this._eixoDaMalha(this.doc.get(this.alca.id));
        const selecao = [...this.editor.tela.selecao];
        this._soltarAlca();
        this.editor.previa([]);
        if (novas.length) this.editor.executar(new ComandoSubstituir(novas, eixo ? `Mover o eixo ${eixo.atributos.eixo}` : 'Mover a linha'));
        this.editor.selecionar(selecao);
        this.dica(this.constructor.dica);
        return;
      }
      const c = this._editada(p);
      const id = this.alca.id;
      const selecao = [...this.editor.tela.selecao];
      this._soltarAlca();
      this.editor.previa([]);
      if (c) this.editor.executar(new ComandoSubstituir([c], c.tipo === 'cota' ? 'Ajustar cota' : c.tipo === 'arco' ? 'Ajustar o arco' : 'Esticar a ponta'));
      this.editor.selecionar(c && c.tipo !== 'cota' ? selecao : [id]);
      this.dica(this.constructor.dica);
      return;
    }
    const e = this.editor.tela.sob(ev.px);
    if (!e) { if (!ev.shiftKey && !ev.ctrlKey) this.editor.selecionar([]); return; }
    // a peça do detalhamento é feita de várias linhas (contorno, abas, linha oculta): o
    // clique pega a peça inteira, como um bloco — girar ou mover não deixa resquício.
    // Alt+clique pega só a linha.
    const ids = ev.altKey ? [e.id] : this.editor.pecaDe(e.id);
    if (ev.ctrlKey) { for (const id of ids) this.editor.alternarSelecao(id); }
    else if (ev.shiftKey) this.editor.selecionar([...this.editor.tela.selecao, ...ids]);
    else this.editor.selecionar(ids);
  }
  onSoltar(p, ev) {
    if (!ev.arrasto) return;
    const ids = this.editor.tela.naJanela(ev.arrasto.de, ev.arrasto.para);
    // Shift ou Ctrl: a janela soma à seleção (com o Ctrl ela trocava a seleção — pedido de 01/10)
    this.editor.selecionar(ev.shiftKey || ev.ctrlKey ? [...this.editor.tela.selecao, ...ids] : ids);
  }
  onTecla(ev) {
    if (ev.key === 'Delete' || ev.key === 'Backspace') { this.editor.apagarSelecao(); return true; }
    if (ev.key.toLowerCase() === 'a' && (ev.ctrlKey || ev.metaKey)) { this.editor.selecionarTudo(); return true; }
    return false;
  }
}

// --------------------------------------------------------------- desenho

/**
 * Direções que o snap passa a seguir a partir de um ponto: a do trecho que acabou de ser
 * desenhado (para continuar reto) e, no primeiro ponto, a da linha existente de onde a
 * nova parte. É o "tracking" dos CADs: o cursor gruda na continuação (e na perpendicular)
 * quando passa perto dela, sem travar como o orto.
 *
 * As linhas que passam pelo ponto valem no primeiro ponto e nos seguintes. A tolerância é de dois pixels (no máximo
 * 0,5 mm): o ponto vem do snap, em cima da linha. Com 0,5 mm fixo, na prancha (em mm de papel, onde 0,5 mm é um
 * perfil inteiro) entravam dezenas de linhas de chapa em volta, e das quatro primeiras ficava de fora justo o banzo de
 * onde a linha nova saía (usuário, 22/10, ME Sooro: "não está fazendo a continuação do ângulo da linha existente").
 * As mais compridas primeiro (a peça antes do detalhe), sem repetir direção.
 */
function direcoesEm(editor, p, anterior) {
  const dirs = [];
  const add = (a, b, peso) => { const d = dist(a, b); if (d > 1e-6) dirs.push([(b[0] - a[0]) / d, (b[1] - a[1]) / d, peso]); };
  if (anterior) add(anterior, p, Infinity);
  const tol = Math.min(0.5, 2 * (editor.tela ? editor.tela.mmPorPixel : 0.25));
  for (const e of editor.doc.naRegiao([[p[0] - tol, p[1] - tol], [p[0] + tol, p[1] + tol]])) {
    if (!editor.doc.visivel(e) || e.tipo === 'texto' || e.tipo === 'hachura') continue;
    for (const [s, t] of segmentosDe(e)) {
      const L = dist(s, t);
      if (dist(p, s) < tol) add(t, s, L); else if (dist(p, t) < tol) add(s, t, L);
      // o ponto no meio de uma linha também dá a guia: ao longo dela e, com a perpendicular, o "subir reto" dela até
      // outra linha ou um arco (06/10: do banzo de baixo ao arco de cima)
      else if ((e.tipo === 'linha' || e.tipo === 'polilinha') && dist(p, maisProximoSeg(p, s, t)) < tol) add(s, t, L);
    }
  }
  dirs.sort((x, y) => y[2] - x[2]);
  const unicas = [];
  for (const d of dirs) {
    // a mesma reta (dos dois sentidos): a guia já cobre os dois lados
    if (unicas.some(u => Math.abs(u[0] * d[1] - u[1] * d[0]) < 1e-3)) continue;
    unicas.push([d[0], d[1]]);
    if (unicas.length === 4) break;
  }
  return unicas;
}

export class Linha extends Ferramenta {
  static id = 'linha'; static nome = 'Linha'; static atalho = 'l'; static dica = 'Clique no primeiro ponto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20 20 4"/><circle cx="4" cy="20" r="1.5"/><circle cx="20" cy="4" r="1.5"/></svg>';
  reiniciar() { super.reiniciar(); this.ultimo = null; this.feitas = 0; this.editor.snap.direcoes = []; }
  onPonto(p) {
    if (this.ultimo && dist(p, this.ultimo) < 1e-6) return;
    if (this.ultimo) { this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'linha', a: this.ultimo, b: p })], 'Linha')); this.feitas = (this.feitas || 0) + 1; }
    this.editor.snap.direcoes = direcoesEm(this.editor, p, this.ultimo);
    this.ultimo = p; this.editor.snap.ultimo = p;
    this.dica('Próximo ponto, ou digite o comprimento · Enter/Esc termina · o cursor gruda na continuação da linha anterior');
  }
  onMover(p) {
    if (!this.ultimo) return;
    this.editor.previa([criar({ tipo: 'linha', camada: this.camada, a: this.ultimo, b: p })]);
    this.editor.medida(`${fmt(dist(this.ultimo, p))} mm  ∠ ${fmt(ang(this.ultimo, p) * 180 / Math.PI)}°`);
  }
  onValor(t) {
    if (!this.ultimo) return;
    const alvo = this.editor.tela.cursor || this.ultimo;
    const m = t.match(/^(.*?)(?:<|@)(-?\d+(?:[.,]\d+)?)$/);         // "1500<30" ou "1500@30"
    const comp = paraMilimetros(m ? m[1] : t);
    if (comp == null) return;
    const a = m ? parseFloat(m[2].replace(',', '.')) * Math.PI / 180 : ang(this.ultimo, alvo);
    this.onPonto(polar(this.ultimo, a, comp));
  }
  onTecla(ev) { if (ev.key === 'Enter' || ev.key === ' ') { this.reiniciar(); return true; } return false; }
  // só o primeiro ponto dado: o Ctrl+Z desiste dele (antes desfazia o objeto anterior do desenho)
  desfazerPasso() { if (this.ultimo && !this.feitas) { this.reiniciar(); return true; } return false; }
  /** O Ctrl+Z tirou o último trecho: a próxima linha sai da ponta de antes (saía da ponta apagada — teste de fluxo, 15/10). */
  aposDesfazer(c) {
    const e = (c && c.entidades || [])[0];
    if (!this.ultimo || !this.feitas || !e || e.tipo !== 'linha' || dist(e.b, this.ultimo) > 1e-6) return;
    this.feitas--;
    this.ultimo = e.a; this.editor.snap.ultimo = e.a;
    this.editor.snap.direcoes = direcoesEm(this.editor, e.a, null);
    this.onMover(this.editor.tela.cursor || e.a);
  }
}

export class Polilinha extends Linha {
  static id = 'polilinha'; static nome = 'Polilinha'; static atalho = 'p'; static dica = 'Clique nos vértices · Enter termina · C fecha';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 18l6-10 5 7 7-9"/></svg>';
  reiniciar() { super.reiniciar(); this.pontos = []; }
  trechosEmAndamento() { return trechosDe(this.pontos || []); }
  onPonto(p) {
    if (this.pontos.length && dist(p, this.pontos[this.pontos.length - 1]) < 1e-6) return;
    this.editor.snap.direcoes = direcoesEm(this.editor, p, this.ultimo);
    this.pontos.push(p); this.ultimo = p; this.editor.snap.ultimo = p;
    this.editor.previa([criar({ tipo: 'polilinha', camada: this.camada, vertices: this.pontos })]);
    this.dica(`${this.pontos.length} vértice(s) · próximo ponto ou comprimento · Enter termina · C fecha`);
  }
  onMover(p) {
    if (!this.pontos.length) return;
    this.editor.previa([criar({ tipo: 'polilinha', camada: this.camada, vertices: [...this.pontos, p] })]);
    this.editor.medida(`${fmt(dist(this.ultimo, p))} mm`);
  }
  terminar(fechar) {
    if (this.pontos.length >= 2) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'polilinha', vertices: this.pontos, fechada: fechar && this.pontos.length > 2 })], 'Polilinha'));
    this.reiniciar();
  }
  onTecla(ev) {
    if (ev.key === 'Enter' || ev.key === ' ') { this.terminar(false); return true; }
    // o C é a opção "fechar" desde o 1º vértice: com menos de 3 ele abria o Círculo e os pontos se perdiam
    if (ev.key.toLowerCase() === 'c' && !ev.ctrlKey && !ev.altKey && !ev.metaKey && this.pontos.length) {
      if (this.pontos.length > 2) this.terminar(true); else this.dica('C fecha a polilinha com 3 vértices ou mais');
      return true;
    }
    return false;
  }
  /** Duplo clique termina, como no AutoCAD (o 2º clique do duplo, no mesmo lugar, não vira vértice). */
  onDuploClique() {
    const n = this.pontos.length;
    if (n >= 2) {
      const [a, b] = [this.pontos[n - 2], this.pontos[n - 1]];
      const z = this.editor.tela.vp ? this.editor.tela.vp.z : 1;
      if (dist(a, b) * z < 3) this.pontos.pop();
    }
    this.terminar(false);
    return true;
  }
  desfazerPasso() {
    if (!this.pontos.length) return false;
    this.pontos.pop();
    this.ultimo = this.pontos.length ? this.pontos[this.pontos.length - 1] : null;
    this.editor.snap.ultimo = this.ultimo;
    if (!this.pontos.length) { this.reiniciar(); return true; }
    this.onMover(this.editor.tela.cursor || this.ultimo);
    this.dica(`${this.pontos.length} vértice(s) · próximo ponto ou comprimento · Enter termina · C fecha`);
    return true;
  }
  aposDesfazer() {}
}

export class Retangulo extends Ferramenta {
  static id = 'retangulo'; static nome = 'Retângulo'; static atalho = 'r'; static dica = 'Clique no primeiro canto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="6" width="16" height="12"/></svg>';
  reiniciar() { super.reiniciar(); this.a = null; }
  _ret(a, b) { return criar({ tipo: 'polilinha', camada: this.camada, vertices: [a, [b[0], a[1]], b, [a[0], b[1]]], fechada: true }); }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica('Canto oposto, ou digite largura;altura'); return; }
    this.editor.executar(new ComandoAdicionar([this._ret(this.a, p)], 'Retângulo'));
    this.reiniciar();
  }
  onMover(p) { if (this.a) { this.editor.previa([this._ret(this.a, p)]); this.editor.medida(`${fmt(Math.abs(p[0] - this.a[0]))} × ${fmt(Math.abs(p[1] - this.a[1]))} mm`); } }
  onValor(t) {
    if (!this.a) return;
    const partes = t.split(/[;x]/);
    const [w, h] = partes.map(paraMilimetros);
    if (w == null || h == null) return;
    // o retângulo vai para o lado do cursor, como a Linha com o comprimento e o Retângulo do 3D; com sinal, vale o sinal
    const cur = this.editor.tela.cursor || this.a;
    const sx = /^\s*-/.test(partes[0]) ? 1 : (cur[0] >= this.a[0] ? 1 : -1);
    const sy = /^\s*-/.test(partes[1] || '') ? 1 : (cur[1] >= this.a[1] ? 1 : -1);
    this.onPonto([this.a[0] + sx * w, this.a[1] + sy * h]);
  }
  desfazerPasso() { if (!this.a) return false; this.reiniciar(); return true; }
}

export class Circulo extends Ferramenta {
  static id = 'circulo'; static nome = 'Círculo'; static atalho = 'c'; static dica = 'Clique no centro';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1"/></svg>';
  reiniciar() { super.reiniciar(); this.c = null; }
  onPonto(p) {
    if (!this.c) { this.c = p; this.editor.snap.ultimo = p; this.dica('Ponto do raio, ou digite o raio (D+valor para diâmetro)'); return; }
    const r = dist(this.c, p);
    if (r > 1e-6) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'circulo', centro: this.c, raio: r })], 'Círculo'));
    this.reiniciar();
  }
  onMover(p) { if (this.c) { this.editor.previa([criar({ tipo: 'circulo', camada: this.camada, centro: this.c, raio: dist(this.c, p) })]); this.editor.medida(`R ${fmt(dist(this.c, p))}  Ø ${fmt(2 * dist(this.c, p))}`); } }
  onValor(t) {
    if (!this.c) return;
    const diam = /^d/i.test(t.trim());
    const v = paraMilimetros(t.replace(/^d/i, ''));
    if (v == null) return;
    this.onPonto([this.c[0] + (diam ? v / 2 : v), this.c[1]]);
  }
  // com o centro dado, o D começa o diâmetro ("d500", como a dica promete): antes abria a Cota
  onTecla(ev) {
    if (this.c && ev.key.toLowerCase() === 'd' && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      const m = this.editor.el.medida; m.value = 'd'; m.focus(); return true;
    }
    return false;
  }
  desfazerPasso() { if (!this.c) return false; this.reiniciar(); return true; }
}

export class ArcoTresPontos extends Ferramenta {
  static id = 'arco'; static nome = 'Arco'; static atalho = 'a'; static dica = 'Arco por três pontos: início';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 18a10 10 0 0 1 16 0"/></svg>';
  reiniciar() { super.reiniciar(); this.pts = []; }
  _arco(a, b, c) {
    // círculo pelos três pontos
    const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
    if (Math.abs(d) < 1e-9) return null;
    const ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d;
    const uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d;
    const centro = [ux, uy], r = dist(centro, a);
    const g = (p) => ((Math.atan2(p[1] - uy, p[0] - ux) * 180 / Math.PI) + 360) % 360;
    let a0 = g(a), a1 = g(c), am = g(b);
    // o arco vai de a até c passando por b: escolhe o sentido que contém b
    const dentro = (x, i, f) => (f >= i ? x >= i && x <= f : x >= i || x <= f);
    if (!dentro(am, a0, a1)) [a0, a1] = [a1, a0];
    return criar({ tipo: 'arco', camada: this.camada, centro, raio: r, inicio: a0, fim: a1 });
  }
  onPonto(p) {
    this.pts.push(p); this.editor.snap.ultimo = p;
    if (this.pts.length === 1) this.dica('Ponto do arco (no meio)');
    else if (this.pts.length === 2) this.dica('Ponto final');
    else { const e = this._arco(...this.pts); if (e) this.editor.executar(new ComandoAdicionar([e], 'Arco')); this.reiniciar(); }
  }
  onMover(p) {
    if (this.pts.length === 1) this.editor.previa([criar({ tipo: 'linha', camada: this.camada, a: this.pts[0], b: p })]);
    else if (this.pts.length === 2) { const e = this._arco(this.pts[0], this.pts[1], p); if (e) this.editor.previa([e]); }
  }
  desfazerPasso() {
    if (!this.pts.length) return false;
    this.pts.pop();
    if (!this.pts.length) { this.reiniciar(); return true; }
    this.editor.snap.ultimo = this.pts[this.pts.length - 1];
    this.dica('Ponto do arco (no meio)');
    this.onMover(this.editor.tela.cursor || this.pts[0]);
    return true;
  }
}

export class Texto extends Ferramenta {
  static id = 'texto'; static nome = 'Texto'; static atalho = 't'; static dica = 'Clique onde o texto começa';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 6h14M12 6v13"/></svg>';
  async onPonto(p) {
    const texto = await this.editor.perguntar('Texto', 'Conteúdo', '');
    if (texto == null || !texto.trim()) return;
    this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'texto', camada: 'TEXTO', posicao: p, texto: texto.trim(), altura: this.editor.alturaTexto })], 'Texto'));
  }
}

/** Texto de várias linhas (o MTEXT do AutoCAD, 24/10): o clique é o canto de cima à esquerda; o texto numa caixa de
 *  várias linhas (Enter quebra a linha, Ctrl+Enter grava). As linhas ficam no mesmo texto, 1,6 altura uma da outra. */
export class TextoVariasLinhas extends Ferramenta {
  static id = 'texto_mt'; static nome = 'Texto de várias linhas'; static dica = 'Clique o canto de cima à esquerda do texto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 5h12M10 5v6"/><path d="M4 14h16M4 18h12M4 22h14" stroke-width="1.2"/></svg>';
  async onPonto(p) {
    const caixa = document.createElement('textarea');
    caixa.rows = 6; caixa.style.width = '100%'; caixa.style.minWidth = '420px'; caixa.spellcheck = false;
    caixa.dataset.campo = 'mtext';
    caixa.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && ev.ctrlKey) { ev.preventDefault(); caixa.closest('form').requestSubmit(); }
    });
    const corpo = document.createElement('div');
    const dica = document.createElement('div'); dica.className = 'explica'; dica.textContent = 'Enter quebra a linha · Ctrl+Enter grava';
    corpo.append(caixa, dica);
    if (await this.editor.dialogo({ titulo: 'Texto de várias linhas', corpo, ok: 'Gravar' }) !== 'ok') return;
    const texto = caixa.value.replace(/\r/g, '').replace(/\s+$/, '');
    if (!texto.trim()) return;
    this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'texto', camada: 'TEXTO', posicao: p, texto, altura: this.editor.alturaTexto, vertical: 'topo' })], 'Texto de várias linhas'));
  }
}

export class Chamada extends Ferramenta {
  static id = 'chamada'; static nome = 'Chamada'; static atalho = 'h'; static dica = 'Clique no ponto apontado';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 18l8-8h8"/><circle cx="4" cy="18" r="1.3"/></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; }
  async onPonto(p) {
    if (!this.alvo) { this.alvo = p; this.editor.snap.ultimo = p; this.dica('Posição do texto'); return; }
    const texto = await this.editor.perguntar('Chamada', 'Texto da chamada', '');
    if (texto != null && texto.trim()) this.editor.executar(new ComandoAdicionar([this.novaEntidade({ tipo: 'chamada', camada: 'TEXTO', alvo: this.alvo, posicao: p, texto: texto.trim(), altura: this.editor.alturaTexto })], 'Chamada'));
    this.reiniciar();
  }
  onMover(p) { if (this.alvo) this.editor.previa([criar({ tipo: 'chamada', camada: 'TEXTO', alvo: this.alvo, posicao: p, texto: '…', altura: this.editor.alturaTexto })]); }
  desfazerPasso() { if (!this.alvo) return false; this.reiniciar(); return true; }
}

/** Seta a mais na chamada (usuário, 26/10, ME Sooro: "criar essa opção de puxar mais de uma seta da mesma linha de
 *  chamada" — o MLEADEREDIT › Adicionar do AutoCAD): o 1º clique, na linha da chamada, marca de onde a seta sai; cada
 *  clique seguinte é uma seta nova saindo desse ponto, até o Enter ou o Esc. A seta a mais acompanha a chamada (mover,
 *  girar, copiar, o texto arrastado: ela sai sempre do mesmo ponto da linha) e tem a alça dela na ponta. */
export class SetaChamada extends Ferramenta {
  static id = 'seta_chamada'; static nome = 'Seta a mais na chamada'; static atalho = 'mle';
  static dica = 'Seta a mais: clique na linha da chamada, no ponto de onde a seta nova sai';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l7 6h10"/><path d="M6.5 12L5 20"/><circle cx="3" cy="9" r="1.3"/><circle cx="5" cy="20" r="1.3"/></svg>';
  reiniciar() { super.reiniciar(); this.chamada = null; this.de = null; }
  /** a chamada sob o clique (a linha, o traço, o texto); a que já está selecionada ganha das outras */
  _chamadaSob(p) {
    const tela = this.editor.tela, t = 8 * tela.mmPorPixel, m = t + 12 * this.doc.escala;
    let melhor = null, dm = Infinity;
    for (const e of this.doc.naRegiao([[p[0] - m, p[1] - m], [p[0] + m, p[1] + m]])) {
      if (e.tipo !== 'chamada' || !this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      const d = distanciaEntidade(p, e, this.doc.escala) - (tela.selecao.has(e.id) ? t : 0);
      if (d < t && d < dm) { dm = d; melhor = e; }
    }
    return melhor;
  }
  _origem(e) { return ramosDaChamada({ ...e, ramos: [{ de: this.de, alvo: e.alvo }] })[0][0]; }
  onPonto(p) {
    if (!this.chamada) {
      const e = this._chamadaSob(p);
      if (!e) { this.dica('Seta a mais: clique em cima da linha de uma chamada (entre a seta e o texto)'); return; }
      this.chamada = e.id; this.de = fracaoNaChamada(e, p);
      this.editor.snap.ultimo = this._origem(e);
      this.editor.selecionar([e.id]);
      this.dica('Clique onde fica a ponta da seta nova · Enter ou Esc termina');
      return;
    }
    const e = this.doc.get(this.chamada);
    if (!e) { this.reiniciar(); return; }
    if (dist(this._origem(e), p) < 1e-6) return;
    this.editor.executar(new ComandoAlterar({ [e.id]: { ramos: [...(e.ramos || []), { de: this.de, alvo: [p[0], p[1]] }] } }, 'Seta a mais na chamada'));
    this.editor.previa([]);
    this.dica('Seta posta · clique a próxima (sai do mesmo ponto) · Enter ou Esc termina');
  }
  onMover(p) {
    const e = this.chamada && this.doc.get(this.chamada);
    if (!e) return;
    this.editor.previa([criar({ tipo: 'chamada', camada: e.camada, alvo: e.alvo, posicao: e.posicao, texto: '', altura: e.altura, ramos: [{ de: this.de, alvo: [p[0], p[1]] }] })]);
    this.editor.medida(`${fmt(dist(this._origem(e), p))} mm`);
  }
  onTecla(ev) { if ((ev.key === 'Enter' || ev.key === ' ') && this.chamada) { this.reiniciar(); return true; } return false; }
  desfazerPasso() { if (!this.chamada) return false; this.reiniciar(); return true; }
  aposDesfazer() { if (this.chamada && !this.doc.get(this.chamada)) this.reiniciar(); }
}

/**
 * Cota. Modo linear (o padrão, como a cota linear do AutoCAD): dois pontos quaisquer — não precisam
 * estar alinhados — e a posição do mouse escolhe a medida: com o mouse acima ou abaixo dos pontos, a
 * horizontal; ao lado deles, a vertical (pedido do usuário, 28/09). H e V fixam uma delas, A faz a
 * alinhada (a distância em linha reta) e L volta ao linear.
 */
/** As setas do teclado travam a medida num eixo (pedido do usuário, 23/10: "as [cotas] quando são diagonais às vezes
 *  apresentam uma dificuldade para medir no plano … se ele não bloquear automaticamente eu uso a seta do teclado e travo
 *  em um eixo"): ← → horizontal, ↑ ↓ vertical; a mesma seta de novo solta (volta ao automático). Devolve o modo novo
 *  ('h', 'v' ou null) ou undefined quando a tecla não é seta. */
function travaPelaSeta(ev, atual) {
  const eixo = { ArrowLeft: 'h', ArrowRight: 'h', ArrowUp: 'v', ArrowDown: 'v' }[ev.key];
  if (!eixo || ev.ctrlKey || ev.metaKey || ev.altKey) return undefined;
  return atual === eixo ? null : eixo;
}
const NOME_DA_TRAVA = { h: 'horizontal (← →)', v: 'vertical (↑ ↓)' };

export class Cota extends Ferramenta {
  static id = 'cota'; static nome = 'Cota'; static atalho = 'd'; static dica = 'Primeiro ponto da cota · o mouse escolhe: acima/abaixo horizontal, ao lado vertical, entre os pontos alinhada · H/V/A fixa · L volta ao automático';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 16V8M20 16V8M4 12h16"/><path d="M7 10l-3 2 3 2M17 10l3 2-3 2"/></svg>';
  reiniciar() { super.reiniciar(); this.p1 = null; this.p2 = null; this._f = undefined; this.modo = this.modo || 'linear'; this.dica(`Primeiro ponto da cota · modo: ${Cota.NOMES[this.modo]} (setas ← → / ↑ ↓ travam no eixo; L/H/V/A troca) · tamanho: ${this.padrao ? 'padrão (P volta ao automático)' : 'pelo desenho em volta (P fixa o padrão)'}`); }
  static NOMES = { linear: 'linear', h: 'horizontal', v: 'vertical', alinhada: 'alinhada' };
  desfazerPasso() {
    if (this.p2) { this.p2 = null; this._f = undefined; this.editor.snap.ultimo = this.p1; this.editor.previa([]); this.dica('Segundo ponto'); return true; }
    if (this.p1) { this.reiniciar(); return true; }
    return false;
  }
  /** O tamanho que a cota toma do desenho em volta (pedido do usuário, 07/10: "as cotas não se adaptam ao modelo
   *  importado"): a altura típica (a mediana) dos textos e das cotas que estão perto, em mm de papel, dividida pela
   *  altura padrão — o fator que vai na cota e multiplica o texto, a ponta e os afastamentos juntos. Sem pelo menos
   *  três vizinhos, ou com a tecla P (padrão), 1. */
  static fatorLocal(doc, p1, p2, padrao = 2.5) {
    const k = doc.escala || 1, comp = dist(p1, p2);
    const R = Math.max(1.5 * comp, 60 * k), m = meio(p1, p2);
    const hs = [];
    for (const e of doc.naRegiao([[m[0] - R, m[1] - R], [m[0] + R, m[1] + R]])) {
      if (!e) continue;
      if (e.tipo === 'texto' && (e.texto || '').trim() && e.altura > 0) hs.push(e.altura);
      else if (e.tipo === 'cota' && e.altura > 0) hs.push(e.altura * (e.fator || 1));
    }
    if (hs.length < 3) return null;
    hs.sort((a, b) => a - b);
    const med = hs[Math.floor(hs.length / 2)];
    const f = Math.round(Math.min(4, Math.max(0.1, med / padrao)) * 100) / 100;
    return Math.abs(f - 1) < 0.05 ? null : f;
  }
  /** No linear, a medida que a posição do mouse pede: fora da faixa dos pontos em y (acima ou
   *  abaixo) é a horizontal; fora da faixa em x (ao lado) é a vertical; nos dois, a mais afastada.
   *  Com o mouse entre os dois pontos (dentro da caixa deles) e os pontos fora de prumo e de nível,
   *  é a alinhada — a cota inclinada (pedido do usuário, 28/09). */
  static modoLinear(p1, p2, p3) {
    const ax = Math.abs(p2[0] - p1[0]), ay = Math.abs(p2[1] - p1[1]);
    if (!p3) return ax >= ay ? 'h' : 'v';
    const fx = Math.max(Math.min(p1[0], p2[0]) - p3[0], p3[0] - Math.max(p1[0], p2[0]), 0);
    const fy = Math.max(Math.min(p1[1], p2[1]) - p3[1], p3[1] - Math.max(p1[1], p2[1]), 0);
    if (fx === 0 && fy === 0) {
      const inclinada = Math.min(ax, ay) > 0.05 * Math.max(ax, ay);
      return inclinada ? 'alinhada' : (ax >= ay ? 'h' : 'v');
    }
    return fy >= fx ? 'h' : 'v';
  }
  _cota(p1, p2, p3) {
    let desl = 10;
    const modo = this.modo === 'linear' ? Cota.modoLinear(p1, p2, p3) : this.modo;
    if (p3) {
      let [x1, y1] = p1, [x2, y2] = p2;
      if (modo === 'h') y2 = y1; else if (modo === 'v') x2 = x1;
      const dx = x2 - x1, dy = y2 - y1, c = Math.hypot(dx, dy) || 1;
      desl = (-(dy / c) * (p3[0] - x1) + (dx / c) * (p3[1] - y1)) / this.doc.escala;
      if (Math.abs(desl) < 2) desl = desl < 0 ? -2 : 2;
    }
    const casas = ((this.doc.metadados || {}).estilo || {}).casas;            // as casas padrão do desenho (Estilos)
    // na prancha, a escala da célula em que a cota é feita: o número sai em mm da peça (pedido do usuário, 01/10)
    // fora dela, a unidade das medidas: em cm, o número é a medida ÷ 10 (07/10)
    const escala = (this.editor.escalaNoPonto ? this.editor.escalaNoPonto(p1) : null) || (unidadeMedidas !== 'mm' ? 1 / UNIDADES[unidadeMedidas] : null);
    if (this._f === undefined) this._f = this.padrao ? null : Cota.fatorLocal(this.doc, p1, p2, this.editor.alturaTexto || 2.5);
    const fator = this._f;
    if (fator && Math.abs(desl) < 2 * fator) desl = desl < 0 ? -2 * fator : 2 * fator;
    return criar({ tipo: 'cota', camada: 'COTA', modo, p1, p2, deslocamento: desl, altura: this.editor.alturaTexto, casas: casas ?? null,
                   ...(escala ? { escala } : {}), ...(fator ? { fator } : {}) });
  }
  onPonto(p) {
    if (!this.p1) { this.p1 = p; this.editor.snap.ultimo = p; this.dica('Segundo ponto'); return; }
    if (!this.p2) {
      if (dist(p, this.p1) < 1e-6) return;
      this.p2 = p; this.editor.snap.ultimo = null; this._f = undefined;
      this._cota(this.p1, this.p2, null);
      this.dica(`Posição da linha de cota · entre os pontos: alinhada · acima ou abaixo: horizontal · ao lado: vertical (A/H/V fixa) · tamanho ${this._f ? `× ${String(this._f).replace('.', ',')} (pelo desenho em volta; P fixa o padrão)` : 'padrão'}`);
      return;
    }
    const nova = this._cota(this.p1, this.p2, p);
    this.editor.executar(new ComandoAdicionar([nova], 'Cota'));
    this.editor.ultimaCota = nova.id;           // a Cota contínua sai dela
    this.reiniciar();
  }
  onMover(p) {
    if (this.p1 && !this.p2) this.editor.previa([criar({ tipo: 'linha', camada: 'COTA', a: this.p1, b: p })]);
    else if (this.p2) this.editor.previa([this._cota(this.p1, this.p2, p)]);
  }
  onTecla(ev) {
    const trava = travaPelaSeta(ev, this.modo === 'h' || this.modo === 'v' ? this.modo : null);
    if (trava !== undefined) {
      this.modo = trava || 'linear';
      this.dica(trava ? `Cota travada na ${NOME_DA_TRAVA[trava]} · a mesma seta solta` : 'Cota no automático: o mouse escolhe (horizontal, vertical ou alinhada)');
      if (this.p2) this.onMover(this.editor.tela.cursor || this.p2);
      return true;
    }
    const k = ev.key.toLowerCase();
    if (k === 'h' || k === 'v' || k === 'a' || k === 'l') {
      this.modo = k === 'a' ? 'alinhada' : k === 'l' ? 'linear' : k;
      this.dica(`Modo: ${Cota.NOMES[this.modo]}`);
      if (this.p2) this.onMover(this.editor.tela.cursor || this.p2);
      return true;
    }
    if (k === 'p') {
      this.padrao = !this.padrao; this._f = undefined;
      this.dica(this.padrao ? 'Tamanho da cota: padrão (P volta a acompanhar o desenho em volta)' : 'Tamanho da cota: pelo desenho em volta (P fixa o padrão)');
      if (this.p2) this.onMover(this.editor.tela.cursor || this.p2);
      return true;
    }
    return false;
  }
}

/**
 * Ajusta o tamanho das cotas que já existem ao desenho em volta delas (o mesmo critério da ferramenta Cota: a altura
 * típica dos textos e cotas vizinhos): selecione as cotas antes ou clique em cada uma. Útil depois de importar um
 * desenho feito em outra escala — as cotas novas já nascem no tamanho dele (07/10).
 */
export class AjustarCota extends Ferramenta {
  static id = 'ajustar_cota'; static nome = 'Ajustar cotas ao desenho'; static grupo = 'edicao';
  static dica = 'Clique numa cota (ou selecione várias antes): o texto, as pontas e os afastamentos tomam o tamanho do desenho em volta';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 14V8M13 14V8M3 11h10"/><path d="M15 6l6 6M21 6v6h-6"/><path d="M16 18h5M18.5 15.5v5"/></svg>';
  reiniciar() {
    super.reiniciar();
    const ids = [...this.editor.tela.selecao].filter(id => (this.doc.get(id) || {}).tipo === 'cota');
    if (ids.length) this._aplicar(ids);
    this.dica(this.constructor.dica);
  }
  _aplicar(ids) {
    const mud = {};
    for (const id of ids) {
      const c = this.doc.get(id);
      if (!c || c.tipo !== 'cota') continue;
      const outros = { ...this.doc, naRegiao: (r) => this.doc.naRegiao(r).filter(e => e && e.id !== id), escala: this.doc.escala };
      const f = Cota.fatorLocal(outros, c.p1, c.p2, c.altura || 2.5);
      if ((f || null) !== (c.fator || null)) mud[id] = { fator: f };
    }
    const n = Object.keys(mud).length;
    if (n) this.editor.executar(new ComandoAlterar(mud, `Ajustar ${n} cota(s) ao desenho`));
    this.dica(n ? `${n} cota(s) ajustada(s) ao desenho em volta` : 'As cotas já estão no tamanho do desenho em volta');
  }
  onPonto(p, ev) {
    const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
    if (e && e.tipo === 'cota') this._aplicar([e.id]);
    else this.dica('Clique numa cota');
  }
}

/**
 * Move a linha de cota sem mexer nos pontos medidos: clique na cota (ou selecione várias)
 * e depois onde a linha deve ficar. Com várias cotas paralelas selecionadas, todas vão
 * para a mesma linha — é como se alinha uma fila de cotas de uma vez. O ponto clicado
 * aceita o snap, inclusive o da linha de outra cota.
 */
export class MoverCota extends Ferramenta {
  static id = 'mover_cota'; static nome = 'Mover linha de cota'; static atalho = 'j'; static grupo = 'edicao';
  static dica = 'Clique na cota (ou selecione várias antes) e depois onde a linha de cota deve ficar';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20V4M20 20V4"/><path d="M4 9h16" stroke-dasharray="3 2"/><path d="M4 15h16"/><path d="M7 13l-3 2 3 2M17 13l3 2-3 2"/><path d="M12 9v6M10.5 11l1.5-2 1.5 2"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.ids = [...this.editor.tela.selecao].filter(id => (this.doc.get(id) || {}).tipo === 'cota');
    this.dica(this.ids.length ? `${this.ids.length} cota(s): clique onde a linha de cota deve ficar` : this.constructor.dica);
  }
  _desloc(c, p3) {
    let [x1, y1] = c.p1, [x2, y2] = c.p2;
    if (c.modo === 'h') y2 = y1; else if (c.modo === 'v') x2 = x1;
    const dx = x2 - x1, dy = y2 - y1, k = Math.hypot(dx, dy) || 1;
    let desl = (-(dy / k) * (p3[0] - x1) + (dx / k) * (p3[1] - y1)) / this.doc.escala;
    if (Math.abs(desl) < 2) desl = desl < 0 ? -2 : 2;
    return desl;
  }
  _novas(p3) {
    return this.ids.map(id => this.doc.get(id)).filter(Boolean).map(c => criar({ ...c, deslocamento: this._desloc(c, p3) }));
  }
  onPonto(p, ev) {
    if (!this.ids.length) {
      const e = this.editor.tela.sob(ev.px);
      if (e && e.tipo === 'cota') { this.editor.selecionar([e.id]); this.ids = [e.id]; this.dica('Agora clique onde a linha de cota deve ficar (o snap pega a linha de outra cota)'); }
      else this.dica('Clique numa cota');
      return;
    }
    this.editor.executar(new ComandoSubstituir(this._novas(p), 'Mover linha de cota'));
    this.editor.selecionar([]);
    this.reiniciar();
  }
  onMover(p) { if (this.ids.length) this.editor.previa(this._novas(p)); }
}

/**
 * Cota contínua — o DIMCONTINUE do AutoCAD (pedido do usuário, 22/10, ME Sooro: "Criar dimcontinue"). Sai da última
 * cota feita (ou da selecionada, ou da que se clica): cada clique faz a próxima cota da corrente, do fim da anterior
 * até o ponto, na mesma linha de cota e no mesmo estilo (modo, tamanho, fator, terminador, casas, folga, escala — na
 * cota do detalhamento, com o número escrito, a escala que o número dela tem). Clicando numa cota, a corrente sai da
 * chamada mais perto do clique. Enter escolhe outra cota de onde continuar; Esc termina; Ctrl+Z desfaz a última e a
 * corrente volta para a anterior (até a cota de onde saiu, que o Ctrl+Z seguinte tira, se foi a última feita).
 */
export class CotaContinua extends Ferramenta {
  static id = 'cota_continua'; static nome = 'Cota contínua (DCO)'; static atalho = 'dc';
  static dica = 'Clique na cota de onde a corrente continua';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 16V8M11 16V8M21 16V8M3 12h18"/><path d="M5 10.5 3.5 12 5 13.5M9 10.5l1.5 1.5L9 13.5M13 10.5 11.5 12l1.5 1.5M19 10.5l1.5 1.5-1.5 1.5"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.cadeia = [];                         // [{base, inicio}] — a de cima é a de onde sai a próxima
    this.trava = null;                        // 'h' / 'v' pelas setas: as próximas nesse eixo
    const sel = [...this.editor.tela.selecao].map(id => this.doc.get(id)).filter(e => e && e.tipo === 'cota');
    const ultima = this.editor.ultimaCota ? this.doc.get(this.editor.ultimaCota) : null;
    const base = sel.length === 1 ? sel[0] : (!sel.length && ultima && ultima.tipo === 'cota' ? ultima : null);
    if (base) this._partirDe(base, base.p2);
    else this.dica(this.constructor.dica);
  }
  get _atual() { return this.cadeia[this.cadeia.length - 1] || null; }
  _partirDe(base, inicio) {
    this.cadeia.push({ base, inicio });
    this.editor.snap.ultimo = inicio;
    this.editor.selecionar([base.id]);
    this.dica(`Próximo ponto da corrente (sai do fim da cota ${formatarCota(base)}) · Enter escolhe outra cota · Esc termina`);
  }
  /** A cota da corrente até `p`: do início, na linha de cota da base, no estilo dela. */
  _nova(p) {
    const { base: b, inicio } = this._atual;
    if (dist(inicio, p) < 1e-6) return null;
    const k = this.doc.escala;
    const fc = fatorDaCota(b);
    const escala = b.escala || (Math.abs(fc - 1) > 1e-9 ? fc : null);
    const c = criar({ tipo: 'cota', camada: b.camada, modo: this.trava || b.modo, p1: [inicio[0], inicio[1]], p2: [p[0], p[1]], deslocamento: b.deslocamento,
      altura: b.altura, fator: b.fator, terminador: b.terminador, casas: b.casas, folga: b.folga, escala });
    if (valorDaCota(c) < 1e-6) return null;
    // a linha de cota nova passa pela ponta da linha da base que fica no início: a mesma linha
    const pc = pontosCota(b, k);
    const naLinha = pc.length === 4 ? (dist(inicio, b.p1) <= dist(inicio, b.p2) ? pc[2] : pc[3]) : null;
    if (naLinha) c.deslocamento = deslocamentoPara(c, naLinha, k);
    return c;
  }
  onPonto(p, ev) {
    if (!this._atual) {
      const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
      if (!e || e.tipo !== 'cota') { this.dica('Clique numa cota (a corrente sai da chamada mais perto do clique) · Esc termina'); return; }
      this._partirDe(e, dist(p, e.p1) < dist(p, e.p2) ? e.p1 : e.p2);
      return;
    }
    const c = this._nova(p);
    if (!c) return;
    this.editor.previa([]);
    this.editor.executar(new ComandoAdicionar([c], 'Cota contínua'));
    this.editor.ultimaCota = c.id;
    this._partirDe(c, c.p2);
  }
  onMover(p) {
    if (!this._atual) return;
    const c = this._nova(p);
    this.editor.previa(c ? [c] : []);
    if (c) this.editor.medida(`${fmt(valorDaCota(c) * (c.escala || 1))} mm`);
  }
  onTecla(ev) {
    const trava = travaPelaSeta(ev, this.trava);
    if (trava !== undefined) {
      this.trava = trava;
      this.dica(trava ? `Corrente travada na ${NOME_DA_TRAVA[trava]} · a mesma seta solta` : 'Corrente no modo da cota de onde sai');
      if (this._atual) this.onMover(this.editor.tela.cursor || this._atual.inicio);
      return true;
    }
    if (ev.key === 'Enter' || ev.key === ' ') {
      this.cadeia = []; this.editor.previa([]); this.editor.snap.ultimo = null; this.editor.selecionar([]);
      this.dica('Clique na cota de onde a nova corrente continua · Esc termina');
      return true;
    }
    return false;
  }
  /** O Ctrl+Z tirou a última cota da corrente: a próxima sai da anterior. */
  aposDesfazer(c) {
    const e = (c && c.entidades || [])[0];
    const a = this._atual;
    if (!a || !e || e.id !== a.base.id) return;
    this.cadeia.pop();
    const ant = this._atual;
    if (!ant) { this.editor.previa([]); this.dica(this.constructor.dica); return; }
    this.editor.snap.ultimo = ant.inicio;
    this.editor.ultimaCota = ant.base.id;
    this.onMover(this.editor.tela.cursor || ant.inicio);
  }
}
const formatarCota = (c) => fmt(valorDaCota(c) * fatorDaCota(c));

/** O estilo de uma cota nova feita em `p` (as mesmas contas da ferramenta Cota): a altura do texto do desenho, as casas
 *  do estilo, a escala da célula da prancha (o número em mm da peça) e o fator pelo desenho em volta. */
function estiloDeCotaNova(editor, p1, p2) {
  const doc = editor.doc;
  const casas = ((doc.metadados || {}).estilo || {}).casas;
  const escala = (editor.escalaNoPonto ? editor.escalaNoPonto(p1) : null) || (unidadeMedidas !== 'mm' ? 1 / UNIDADES[unidadeMedidas] : null);
  const fator = Cota.fatorLocal(doc, p1, p2 || p1, editor.alturaTexto || 2.5);
  return { altura: editor.alturaTexto, casas: casas ?? null, ...(escala ? { escala } : {}), ...(fator ? { fator } : {}) };
}

/** A base das cotas angular, de raio, de diâmetro e ordenada: cria a cota pela posição do cursor e a grava no clique. */
class FerramentaCotaEspecial extends Ferramenta {
  static grupo = 'edicao';
  _nova(posicao) { return null; }
  onMover(p) { const c = this._nova(p); this.editor.previa(c ? [c] : []); if (c) this.editor.medida(medidaDaCotaEspecial(c)); }
  _gravar(p, rotulo) {
    const c = this._nova(p);
    if (!c) return false;
    this.editor.previa([]);
    this.editor.executar(new ComandoAdicionar([c], rotulo));
    this.editor.ultimaCota = c.id;
    return true;
  }
}

/**
 * Cota angular (D N, o DIMANGULAR): clique nas duas linhas (o lado de cada uma é o do clique) — ou, fora de uma linha, o
 * vértice e um ponto em cada lado — e depois onde passa o arco: o ângulo é o do setor em que o cursor está.
 */
export class CotaAngular extends FerramentaCotaEspecial {
  static id = 'cota_angular'; static nome = 'Cota angular'; static atalho = 'dn';
  static dica = 'Cota angular: clique na primeira linha (ou fora dela: o vértice e um ponto em cada lado)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20h16M4 20L16 6"/><path d="M12 20a8 8 0 0 0-2.6-5.9"/></svg>';
  reiniciar() { super.reiniciar(); this.l1 = null; this.pts = []; this.geo = null; }
  _nova(posicao) {
    if (!this.geo) return null;
    const g = this.geo;
    return criar({ tipo: 'cota_especial', modo: 'angular', camada: 'COTA', centro: g.centro, p1: g.p1, p2: g.p2, posicao: [posicao[0], posicao[1]],
      ...estiloDeCotaNova(this.editor, g.centro, g.p1) });
  }
  onPonto(p, ev) {
    if (this.geo) { if (this._gravar(p, 'Cota angular')) this.reiniciar(); return; }
    const m = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;
    if (!this.pts.length) {
      const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
      if (e && e.tipo === 'linha') {
        if (!this.l1) { this.l1 = { e, p: m }; this.dica('Agora a segunda linha'); return; }
        if (e.id === this.l1.e.id) { this.dica('Clique numa segunda linha, diferente da primeira'); return; }
        const V = intersecaoRetas(this.l1.e.a, this.l1.e.b, e.a, e.b);
        if (!V) { this.dica('As linhas são paralelas: não há ângulo entre elas'); this.l1 = null; return; }
        const r1 = ladoDoCanto(this.l1.e, this.l1.p, V), r2 = ladoDoCanto(e, m, V);
        const ponto = (r) => (dist(r.ponta, V) > 1e-6 ? r.ponta : [V[0] + r.d[0], V[1] + r.d[1]]);
        this.geo = { centro: V, p1: ponto(r1), p2: ponto(r2) };
        this.dica('Onde passa o arco (o ângulo é o do setor do cursor) · Esc cancela');
        return;
      }
      if (this.l1) { this.dica('Clique na segunda linha'); return; }
    }
    this.pts.push([p[0], p[1]]);
    this.editor.snap.ultimo = this.pts[0];
    if (this.pts.length === 3) { this.geo = { centro: this.pts[0], p1: this.pts[1], p2: this.pts[2] }; this.dica('Onde passa o arco · Esc cancela'); }
    else this.dica(this.pts.length === 1 ? 'Um ponto no primeiro lado' : 'Um ponto no segundo lado');
  }
}

/** Cota de raio (D R) e de diâmetro (D I): clique no círculo ou no arco e depois onde fica o número (dentro dele, sobre a
 *  linha; fora, numa chamada). O raio de um furo dá o Ø do furo. */
export class CotaRaio extends FerramentaCotaEspecial {
  static id = 'cota_raio'; static nome = 'Cota de raio'; static atalho = 'dr'; static modo = 'raio';
  static dica = 'Clique no círculo ou no arco';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="13" r="7"/><path d="M11 13l5-5"/><path d="M14 8h2v2"/></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; }
  _nova(posicao) {
    if (!this.alvo) return null;
    const C = this.alvo.centro, R = this.alvo.raio, d = dist(C, posicao);
    const u = d > 1e-9 ? [(posicao[0] - C[0]) / d, (posicao[1] - C[1]) / d] : [1, 0];
    return criar({ tipo: 'cota_especial', modo: this.constructor.modo, camada: 'COTA', centro: [C[0], C[1]], p1: [C[0] + u[0] * R, C[1] + u[1] * R],
      posicao: [posicao[0], posicao[1]], ...estiloDeCotaNova(this.editor, C, C) });
  }
  onPonto(p, ev) {
    if (this.alvo) { if (this._gravar(p, this.constructor.nome)) this.reiniciar(); return; }
    const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
    if (!e || (e.tipo !== 'circulo' && e.tipo !== 'arco')) { this.dica('Clique num círculo ou num arco'); return; }
    this.alvo = e;
    this.dica('Onde fica o número (dentro: sobre a linha; fora: numa chamada) · Esc cancela');
  }
}
export class CotaDiametro extends CotaRaio {
  static id = 'cota_diametro'; static nome = 'Cota de diâmetro'; static atalho = 'di'; static modo = 'diametro';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="7"/><path d="M7 17L17 7"/></svg>';
}

/**
 * Cota ordenada (D O, o DIMORDINATE): a distância do ponto à origem em x ou em y — a furação medida de uma borda.
 * Clique no ponto medido e depois onde fica o número: a chamada que sobe ou desce mede o x, a que vai para o lado mede o
 * y (X / Y fixam). O: clique a origem (fica gravada no desenho; sem ela, 0,0). Fica na ferramenta para o próximo ponto.
 */
export class CotaOrdenada extends FerramentaCotaEspecial {
  static id = 'cota_ordenada'; static nome = 'Cota ordenada'; static atalho = 'do';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20h16M4 20V4"/><path d="M10 20v-9M15 20v-13"/></svg>';
  get origem() { const o = (this.doc.metadados || {}).origem_ordenada; return Array.isArray(o) ? o : [0, 0]; }
  reiniciar() {
    super.reiniciar(); this.p1 = null; this.pedeOrigem = false;
    this.dica(`Cota ordenada: clique no ponto medido · origem em ${fmt(this.origem[0])}; ${fmt(this.origem[1])} (O muda) · X / Y fixam o eixo${this.eixoFixo ? ` (fixo: ${this.eixoFixo})` : ''}`);
  }
  _nova(posicao) {
    if (!this.p1) return null;
    const dx = Math.abs(posicao[0] - this.p1[0]), dy = Math.abs(posicao[1] - this.p1[1]);
    const eixo = this.eixoFixo || (dy >= dx ? 'x' : 'y');
    return criar({ tipo: 'cota_especial', modo: 'ordenada', camada: 'COTA', centro: [...this.origem], p1: this.p1, posicao: [posicao[0], posicao[1]], eixo,
      ...estiloDeCotaNova(this.editor, this.p1, this.p1) });
  }
  onPonto(p) {
    if (this.pedeOrigem) {
      this.doc.metadados = { ...(this.doc.metadados || {}), origem_ordenada: [p[0], p[1]] };
      this.reiniciar(); this.dica(`Origem da ordenada em ${fmt(p[0])}; ${fmt(p[1])} · clique no ponto medido`); return;
    }
    if (!this.p1) { this.p1 = [p[0], p[1]]; this.editor.snap.ultimo = this.p1; this.dica('Onde fica o número (para cima/baixo: o x; para o lado: o y)'); return; }
    if (this._gravar(p, 'Cota ordenada')) { const eixo = this.eixoFixo; this.reiniciar(); this.eixoFixo = eixo; }
  }
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    if (k === 'o') { this.pedeOrigem = true; this.p1 = null; this.editor.previa([]); this.dica('Clique a origem das ordenadas (a borda, o furo de referência)'); return true; }
    if (k === 'x' || k === 'y') { this.eixoFixo = this.eixoFixo === k ? null : k; this.dica(this.eixoFixo ? `Eixo fixo: ${k}` : 'Eixo pelo cursor'); if (this.p1 && this.editor.tela.cursor) this.onMover(this.editor.tela.cursor); return true; }
    return false;
  }
}

/** O espaçamento entre as linhas de cota empilhadas (linha de base), em mm de papel × o fator: a DIMDLI do AutoCAD com a
 *  folga para o número de 2,5. */
const PASSO_LINHA_DE_BASE = 7;

/** A linha de cota da cota `c` empurrada `passo` mm de papel para fora (para o lado contrário aos pontos medidos). */
function linhaEmpurrada(c, k, passo) {
  const pc = pontosCota(c, k);
  if (pc.length < 4) return null;
  let [x1, y1] = c.p1;
  const dx = pc[2][0] - x1, dy = pc[2][1] - y1, L = Math.hypot(dx, dy) || 1;
  return [pc[2][0] + dx / L * passo * k * (c.fator || 1), pc[2][1] + dy / L * passo * k * (c.fator || 1)];
}

/**
 * Cota por linha de base (D B, o DIMBASELINE): todas as cotas saem do mesmo ponto — a primeira chamada da cota de onde se
 * parte (a última feita, a selecionada ou a clicada) — e cada uma numa linha de cota mais para fora. É a furação medida de
 * uma borda. Enter escolhe outra cota de partida; Esc termina; Ctrl+Z volta a anterior.
 */
export class CotaBase extends Ferramenta {
  static id = 'cota_base'; static nome = 'Cota por linha de base'; static atalho = 'db'; static grupo = 'edicao';
  static dica = 'Clique na cota de onde a linha de base sai';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20V6M10 20v-6M16 20V10M21 20V4"/><path d="M4 16h6M4 12h12M4 8h17"/></svg>';
  reiniciar() {
    super.reiniciar(); this.base = null; this.ultima = null; this.feitas = [];
    const sel = [...this.editor.tela.selecao].map(id => this.doc.get(id)).filter(e => e && e.tipo === 'cota');
    const u = this.editor.ultimaCota ? this.doc.get(this.editor.ultimaCota) : null;
    const b = sel.length === 1 ? sel[0] : (!sel.length && u && u.tipo === 'cota' ? u : null);
    if (b) this._partirDe(b, b.p1); else this.dica(this.constructor.dica);
  }
  _partirDe(c, ponto) {
    this.base = c; this.ultima = c; this.ponto = ponto;
    this.editor.snap.ultimo = ponto; this.editor.selecionar([c.id]);
    this.dica('Próximo ponto medido a partir da base · Enter escolhe outra cota · Esc termina');
  }
  _nova(p) {
    if (!this.base || dist(this.ponto, p) < 1e-6) return null;
    const b = this.base, k = this.doc.escala;
    const fc = fatorDaCota(b), escala = b.escala || (Math.abs(fc - 1) > 1e-9 ? fc : null);
    const c = criar({ tipo: 'cota', camada: b.camada, modo: b.modo, p1: [this.ponto[0], this.ponto[1]], p2: [p[0], p[1]], deslocamento: b.deslocamento,
      altura: b.altura, fator: b.fator, terminador: b.terminador, casas: b.casas, folga: b.folga, escala });
    if (valorDaCota(c) < 1e-6) return null;
    const q = linhaEmpurrada(this.ultima, k, PASSO_LINHA_DE_BASE);
    if (q) c.deslocamento = deslocamentoPara(c, q, k);
    return c;
  }
  onPonto(p, ev) {
    if (!this.base) {
      const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
      if (!e || e.tipo !== 'cota') { this.dica('Clique numa cota (a base é a chamada mais perto do clique)'); return; }
      this._partirDe(e, dist(p, e.p1) <= dist(p, e.p2) ? e.p1 : e.p2);
      return;
    }
    const c = this._nova(p);
    if (!c) return;
    this.editor.previa([]);
    this.editor.executar(new ComandoAdicionar([c], 'Cota por linha de base'));
    this.editor.ultimaCota = c.id;
    this.feitas.push(this.ultima); this.ultima = c;
    this.editor.selecionar([c.id]);
  }
  onMover(p) { const c = this._nova(p); this.editor.previa(c ? [c] : []); if (c) this.editor.medida(`${fmt(valorDaCota(c) * (c.escala || 1))} mm`); }
  onTecla(ev) { if (ev.key === 'Enter' || ev.key === ' ') { this.base = null; this.editor.previa([]); this.editor.selecionar([]); this.dica('Clique na cota de onde a nova linha de base sai'); return true; } return false; }
  aposDesfazer(c) {
    const e = (c && c.entidades || [])[0];
    if (this.ultima && e && e.id === this.ultima.id && this.feitas.length) this.ultima = this.feitas.pop();
  }
}

/** Os pontos que a cota rápida mede de um objeto: as pontas e os vértices, o centro dos círculos (o furo), o centro e as
 *  pontas do arco. */
function pontosDeMedida(e) {
  if (e.tipo === 'linha') return [e.a, e.b];
  if (e.tipo === 'polilinha') return e.vertices;
  if (e.tipo === 'circulo') return [e.centro];
  if (e.tipo === 'arco') { const pa = pontosArco(e, 2); return [e.centro, pa[0], pa[pa.length - 1]]; }
  return [];
}

/**
 * Cota rápida (D Q, o QDIM): os objetos selecionados (ou os de uma janela) cotados de uma vez pelos pontos deles — as
 * bordas e o centro de cada furo, sem repetir. O cursor escolhe a direção (acima ou abaixo: as medidas em x; ao lado: em
 * y) e onde fica a linha. C: em cadeia (contínua, o padrão); B: da linha de base; O: ordenadas a partir do primeiro ponto.
 */
export class CotaRapida extends Ferramenta {
  static id = 'cota_rapida'; static nome = 'Cota rápida (furação)'; static atalho = 'dq'; static grupo = 'edicao';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h18"/><path d="M3 4v4M9 4v4M15 4v4M21 4v4"/><circle cx="9" cy="15" r="2"/><circle cx="15" cy="15" r="2"/><rect x="3" y="11" width="18" height="9" rx="1"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.tipoCota = this.tipoCota || 'continua';
    this.ents = [...this.editor.tela.selecao].map(id => this.doc.get(id)).filter(e => e && pontosDeMedida(e).length);
    this.dica(this.ents.length ? this._dicaPronta() : 'Cota rápida: arraste uma janela em volta dos objetos (ou selecione antes)');
  }
  _dicaPronta() { return `${this.ents.length} objeto(s): leve o cursor para cima/baixo (medidas em x) ou para o lado (em y) e clique onde fica a linha · C cadeia · B linha de base · O ordenadas (agora: ${({ continua: 'cadeia', base: 'linha de base', ordenada: 'ordenadas' })[this.tipoCota]})`; }
  onSoltar(p, ev) {
    if (!ev.arrasto || this.ents.length) return;
    const ids = this.editor.tela.naJanela(ev.arrasto.de, ev.arrasto.para);
    this.ents = ids.map(id => this.doc.get(id)).filter(e => e && pontosDeMedida(e).length);
    this.editor.selecionar(this.ents.map(e => e.id));
    this.dica(this.ents.length ? this._dicaPronta() : 'Nada para cotar na janela');
  }
  _cotas(cursor) {
    if (!this.ents.length) return [];
    const pts = this.ents.flatMap(pontosDeMedida);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const q of pts) { x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]); }
    const fx = Math.max(x0 - cursor[0], cursor[0] - x1, 0), fy = Math.max(y0 - cursor[1], cursor[1] - y1, 0);
    const emX = fy >= fx;                                              // acima/abaixo: as medidas em x
    const i = emX ? 0 : 1, j = emX ? 1 : 0;
    const doLado = cursor[j] >= (emX ? (y0 + y1) / 2 : (x0 + x1) / 2);   // a linha acima (ou à direita) dos pontos
    // um ponto por coordenada: o mais perto da linha de cota (a chamada mais curta)
    const tol = 1e-3 * Math.max(x1 - x0, y1 - y0, 1);
    const porValor = [];
    for (const q of [...pts].sort((a, b) => a[i] - b[i])) {
      const u = porValor[porValor.length - 1];
      if (u && Math.abs(q[i] - u[i]) <= tol) { if (doLado ? q[j] > u[j] : q[j] < u[j]) porValor[porValor.length - 1] = q; }
      else porValor.push(q);
    }
    if (porValor.length < 2) return [];
    const k = this.doc.escala, modo = emX ? 'h' : 'v';
    const est = estiloDeCotaNova(this.editor, porValor[0], porValor[porValor.length - 1]);
    const linear = (a, b) => criar({ tipo: 'cota', camada: 'COTA', modo, p1: [a[0], a[1]], p2: [b[0], b[1]], deslocamento: 10, ...est });
    if (this.tipoCota === 'ordenada') {
      const o = porValor[0];
      return porValor.slice(1).map(q => criar({ tipo: 'cota_especial', modo: 'ordenada', camada: 'COTA', centro: [o[0], o[1]], p1: [q[0], q[1]],
        posicao: emX ? [q[0], cursor[1]] : [cursor[0], q[1]], eixo: emX ? 'x' : 'y', ...est }));
    }
    const out = [];
    if (this.tipoCota === 'base') {
      let linha = emX ? [porValor[0][0], cursor[1]] : [cursor[0], porValor[0][1]];
      porValor.slice(1).forEach((q, n) => {
        const c = linear(porValor[0], q);
        c.deslocamento = deslocamentoPara(c, linha, k);
        if (n + 1 < porValor.length - 1) linha = linhaEmpurrada(c, k, PASSO_LINHA_DE_BASE) || linha;
        out.push(c);
      });
      return out;
    }
    for (let n = 1; n < porValor.length; n++) {
      const c = linear(porValor[n - 1], porValor[n]);
      c.deslocamento = deslocamentoPara(c, emX ? [porValor[n][0], cursor[1]] : [cursor[0], porValor[n][1]], k);
      out.push(c);
    }
    return out;
  }
  onMover(p) { const cs = this._cotas(p); this.editor.previa(cs); if (cs.length) this.editor.medida(`${cs.length} cota(s)`); }
  onPonto(p, ev) {
    if (!this.ents.length) { this.dica('Arraste uma janela em volta dos objetos a cotar'); return; }
    const cs = this._cotas(p);
    if (!cs.length) { this.dica('Os objetos não têm dois pontos diferentes nessa direção'); return; }
    this.editor.previa([]);
    this.editor.executar(new ComandoAdicionar(cs, `Cota rápida (${cs.length})`));
    this.editor.ultimaCota = cs[cs.length - 1].id;
    this.editor.selecionar([]);
    this.ents = [];
    this.dica(`${cs.length} cota(s) feita(s) · arraste outra janela ou Esc`);
  }
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    const t = { c: 'continua', b: 'base', o: 'ordenada' }[k];
    if (!t) return false;
    this.tipoCota = t;
    this.dica(this.ents.length ? this._dicaPronta() : 'Cota rápida: arraste uma janela em volta dos objetos');
    if (this.editor.tela.cursor) this.onMover(this.editor.tela.cursor);
    return true;
  }
}

/**
 * Colar o que veio de fora (o Ctrl+C do AutoCAD, 23/10): os objetos presos ao cursor pelo ponto de base; o clique solta.
 * Enter cola nas coordenadas de origem (o PASTEORIG do AutoCAD); "x;y" digitado põe o ponto de base ali. Muitos objetos
 * vão na prévia só pela caixa deles (mover milhares a cada movimento do mouse travaria a tela).
 */
export class ColarObjetos extends Ferramenta {
  static id = 'colar_autocad'; static nome = 'Colar do AutoCAD'; static grupo = 'oculta';
  static dica = 'Clique onde fica o ponto de base · Enter: nas coordenadas do AutoCAD · digite x;y · Esc cancela';
  /** `ents`: as entidades a colar (já criadas, nas coordenadas de origem); `base`: o ponto que vai no cursor. */
  preparar(ents, base, rotulo = 'Colar do AutoCAD') {
    this.ents = ents; this.base = base; this.rotulo = rotulo;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const e of ents) for (const p of pontosDe(e)) { if (p[0] < x0) x0 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[0] > x1) x1 = p[0]; if (p[1] > y1) y1 = p[1]; }
    this.caixa = isFinite(x0) ? [[x0, y0], [x1, y1]] : null;
  }
  reiniciar() { super.reiniciar(); if (this.ents) this.dica(`${this.ents.length} objeto(s): ${this.constructor.dica}`); }
  _deslocadas(d) { return this.ents.map(e => transladar(e, d)); }
  onMover(p) {
    if (!this.ents) return;
    const d = [p[0] - this.base[0], p[1] - this.base[1]];
    if (this.ents.length <= 1500 || !this.caixa) { this.editor.previa(this._deslocadas(d)); return; }
    const [[x0, y0], [x1, y1]] = this.caixa;
    this.editor.previa([criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true,
      vertices: [[x0 + d[0], y0 + d[1]], [x1 + d[0], y0 + d[1]], [x1 + d[0], y1 + d[1]], [x0 + d[0], y1 + d[1]]] })]);
  }
  _colar(d) {
    if (!this.ents) return;
    const novas = this._deslocadas(d);
    this.ents = null;
    this.editor.previa([]);
    this.editor.executar(new ComandoAdicionar(novas, `${this.rotulo} (${novas.length})`));
    this.editor.ativarFerramenta('selecionar');
    this.editor.selecionar(novas.map(e => e.id));
    this.editor.dica(`${novas.length} objeto(s) colado(s) · Ctrl+Z desfaz`);
  }
  onPonto(p) { if (this.ents) this._colar([p[0] - this.base[0], p[1] - this.base[1]]); }
  onValor(t) {
    const m = String(t || '').replace(/^@/, '').split(/[;]/);
    if (m.length !== 2) return;
    const x = paraMilimetros(m[0]), y = paraMilimetros(m[1]);
    if (x == null || y == null) return;
    this._colar([x - this.base[0], y - this.base[1]]);
  }
  onTecla(ev) { if (ev.key === 'Enter' && this.ents) { this._colar([0, 0]); return true; } return false; }
  cancelar() { this.ents = null; super.cancelar(); }
}

/**
 * Esticar — o "empurrar/puxar" do SketchUp no 2D. Dois jeitos:
 *  • clique numa aresta (a ponta de uma terça, o lado de uma chapa): ela anda na
 *    perpendicular a ela mesma, e tudo o que encosta nas duas pontas dela vai junto — as
 *    arestas vizinhas esticam e as cotas presas ali mudam de valor;
 *  • arraste uma janela: cada ponto dentro dela (vértices, pontas de linha, pontos de
 *    cota) anda; o resto fica — o STRETCH do AutoCAD.
 * Depois, o ponto de destino (ou digite a distância; na aresta, positivo afasta para o
 * lado do cursor). Furos e textos só andam quando estão dentro da janela.
 */
export class Esticar extends Ferramenta {
  static id = 'esticar'; static nome = 'Esticar (empurrar/puxar)'; static atalho = 's'; static grupo = 'edicao';
  static dica = 'Clique na aresta a empurrar/puxar, ou arraste uma janela sobre o que vai esticar';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="7" width="11" height="10"/><path d="M14 7v10" stroke-width="2.4"/><path d="M17 12h5M19.5 9.5 22 12l-2.5 2.5"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.dentro = null;          // (ponto) => bool: o que anda
    this.regiao = null;          // caixa para buscar entidades
    this.normal = null;          // aresta: o deslocamento fica na perpendicular dela
    this.base = null;
  }
  _pegarAresta(p, ev) {
    const tela = this.editor.tela, e = tela.sob(ev.px);
    if (!e) { this.dica('Clique numa aresta, ou arraste uma janela'); return false; }
    // o elemento que se estica pela ponta (a viga da Estrutura, que é a linha do eixo com a largura só na tela): o
    // clique perto da ponta leva aquela ponta, ao longo do eixo — antes a linha inteira era a "aresta" e andava de
    // lado (06/10, "estou tentando estender a viga até o fim")
    const ponta = typeof this.editor._pontaParaEsticar === 'function' ? this.editor._pontaParaEsticar(e, p) : null;
    if (ponta) {
      const tol = Math.max(0.5, 2 * tela.mmPorPixel), q = ponta.ponto;
      this.dentro = (x) => dist(x, q) <= tol;
      this.regiao = [[q[0] - tol, q[1] - tol], [q[0] + tol, q[1] + tol]];
      this.normal = ponta.direcao;
      this.base = q; this.editor.snap.ultimo = q;
      this.editor.previa(ponta.aresta ? [criar({ tipo: 'linha', camada: this.camada, a: ponta.aresta[0], b: ponta.aresta[1] })] : []);
      this.dica('Leve a ponta até a nova posição (anda no eixo dela), ou digite quanto esticar · Esc cancela');
      return true;
    }
    let melhor = null, dm = Infinity;
    for (const [s, t] of segmentosDe(e)) {
      const q = maisProximoSeg(p, s, t), d = dist(q, p);
      if (d < dm) { dm = d; melhor = [s, t]; }
    }
    if (!melhor) return false;
    const [s, t] = melhor, L = dist(s, t) || 1;
    const tol = Math.max(0.5, 2 * tela.mmPorPixel);
    // anda tudo o que termina SOBRE a aresta, não só nas pontas dela: as linhas internas do
    // perfil (a aba, a dobra) chegam no meio da aresta da ponta da barra
    this.dentro = (q) => dist(q, maisProximoSeg(q, s, t)) <= tol;
    this.regiao = [[Math.min(s[0], t[0]) - tol, Math.min(s[1], t[1]) - tol], [Math.max(s[0], t[0]) + tol, Math.max(s[1], t[1]) + tol]];
    this.normal = [-(t[1] - s[1]) / L, (t[0] - s[0]) / L];
    // direção do movimento: a das linhas que chegam na aresta, quando são todas paralelas
    // (o eixo de uma barra cuja ponta é um corte inclinado — a diagonal da tesoura);
    // senão a perpendicular da aresta. Andar na perpendicular de um corte inclinado
    // entortava a barra.
    const eixo = this._eixoDasVizinhas(s, t, tol, (e.atributos || {}).origem || null);
    if (eixo) this.normal = eixo;
    this.base = p; this.editor.snap.ultimo = p;
    this.editor.previa([criar({ tipo: 'linha', camada: this.camada, a: s, b: t })]);
    this.dica('Leve a aresta até a nova posição, ou digite a distância · Esc cancela');
    return true;
  }
  /** Direção das linhas que têm uma ponta sobre a aresta s–t e seguem para fora dela: só
   *  as da mesma peça (`origem`), quando a aresta é de uma peça — a barra vizinha que chega
   *  no mesmo nó não conta —, e, se ainda houver direções diferentes, a que soma mais
   *  comprimento (±2°). null se não há vizinhas. Antes, qualquer linha não paralela fazia a
   *  aresta andar na perpendicular dela, e o corte inclinado entortava a barra. */
  _eixoDasVizinhas(s, t, tol, origem = null) {
    const lo = [Math.min(s[0], t[0]) - tol, Math.min(s[1], t[1]) - tol], hi = [Math.max(s[0], t[0]) + tol, Math.max(s[1], t[1]) + tol];
    const naAresta = (q) => dist(q, maisProximoSeg(q, s, t)) <= tol;
    const dirs = [];
    for (const e of this.doc.naRegiao([lo, hi])) {
      if (!this.doc.visivel(e) || (e.tipo !== 'linha' && e.tipo !== 'polilinha')) continue;
      if (origem && (e.atributos || {}).origem !== origem) continue;
      for (const [a, b] of segmentosDe(e)) {
        const ia = naAresta(a), ib = naAresta(b);
        if (ia === ib) continue;                        // a própria aresta, ou longe dela
        const [p0, p1] = ia ? [a, b] : [b, a];
        const n = dist(p0, p1);
        if (n > 1e-6) dirs.push([(p1[0] - p0[0]) / n, (p1[1] - p0[1]) / n, n]);
      }
    }
    if (!dirs.length) return null;
    // agrupa as paralelas (±2°) e fica com o grupo de mais comprimento
    const cos2 = Math.cos(2 * Math.PI / 180);
    const grupos = [];
    for (const d of dirs) {
      const g = grupos.find(x => Math.abs(d[0] * x.d[0] + d[1] * x.d[1]) > cos2);
      if (g) g.soma += d[2]; else grupos.push({ d: [d[0], d[1]], soma: d[2] });
    }
    grupos.sort((x, y) => y.soma - x.soma);
    return grupos[0].d;
  }
  onSoltar(p, ev) {
    if (!ev.arrasto || this.dentro) return;
    const tela = this.editor.tela;
    const a = tela.paraMundo(ev.arrasto.de), b = tela.paraMundo(ev.arrasto.para);
    const x0 = Math.min(a[0], b[0]), x1 = Math.max(a[0], b[0]), y0 = Math.min(a[1], b[1]), y1 = Math.max(a[1], b[1]);
    this.dentro = (q) => q[0] >= x0 && q[0] <= x1 && q[1] >= y0 && q[1] <= y1;
    this.regiao = [[x0, y0], [x1, y1]];
    this.normal = null;
    this.editor.previa([criar({ tipo: 'polilinha', camada: this.camada, vertices: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], fechada: true })]);
    this.dica('Ponto base do esticamento');
  }
  _desloc(p) {
    let d = [p[0] - this.base[0], p[1] - this.base[1]];
    if (this.normal) { const k = d[0] * this.normal[0] + d[1] * this.normal[1]; d = [this.normal[0] * k, this.normal[1] * k]; }
    return d;
  }
  /** Cópias das entidades afetadas, com os pontos de dentro deslocados de `d`. */
  _novas(d) {
    const mv = (q) => (this.dentro(q) ? [q[0] + d[0], q[1] + d[1]] : q);
    const [lo, hi] = this.regiao;
    const fora = [];
    for (const e of this.doc.naRegiao([lo, hi])) {
      if (!this.doc.visivel(e)) continue;
      const c = clonar(e);
      let mudou = false;
      const trocar = (campo) => { const v = mv(c[campo]); if (v !== c[campo]) { c[campo] = v; mudou = true; } };
      if (e.tipo === 'linha') { trocar('a'); trocar('b'); }
      else if (e.tipo === 'polilinha') { c.vertices = c.vertices.map(q => { const v = mv(q); if (v !== q) mudou = true; return v; }); }
      else if (e.tipo === 'cota') { trocar('p1'); trocar('p2'); if (c.texto_pos) trocar('texto_pos'); }
      else if (e.tipo === 'circulo' || e.tipo === 'arco') { trocar('centro'); }
      else if (e.tipo === 'texto') { trocar('posicao'); }
      else if (e.tipo === 'chamada') {
        trocar('alvo'); trocar('posicao');
        if (c.ramos) c.ramos = c.ramos.map(r => { const v = mv(r.alvo); if (v !== r.alvo) mudou = true; return { ...r, alvo: v }; });
      }
      else if (e.tipo === 'hachura') { c.contornos = c.contornos.map(ct => ct.map(q => { const v = mv(q); if (v !== q) mudou = true; return v; })); }
      if (mudou) {
        // cota com o valor escrito (as do detalhamento): o número acompanha a medida nova
        if (c.tipo === 'cota' && c.texto != null && /^\s*\d+(?:[.,]\d+)?\s*$/.test(String(c.texto))) c.texto = textoNovoDaCota(e, c);
        fora.push(criar(c));
      }
    }
    return fora;
  }
  onPonto(p, ev) {
    if (!this.dentro) { this._pegarAresta(p, ev); return; }
    if (!this.base) { this.base = p; this.editor.snap.ultimo = p; this.dica('Ponto de destino, ou digite a distância'); return; }
    const novas = this._novas(this._desloc(p));
    if (novas.length) this.editor.executar(new ComandoSubstituir(novas, 'Esticar'));
    this.reiniciar();
  }
  onMover(p) {
    if (!this.dentro || !this.base) return;
    const d = this._desloc(p);
    this.editor.previa(this._novas(d));
    this.editor.medida(`${fmt(Math.hypot(d[0], d[1]))} mm`);
  }
  onValor(t) {
    if (!this.dentro || !this.base) return;
    const v = paraMilimetros(t);
    if (v == null) { this.dica('Medida não entendida: 500, 50cm ou 0,5m'); return; }
    const alvo = this.editor.tela.cursor || this.base;
    let dir = this.normal || [alvo[0] - this.base[0], alvo[1] - this.base[1]];
    if (this.normal) { const k = (alvo[0] - this.base[0]) * dir[0] + (alvo[1] - this.base[1]) * dir[1]; if (k < 0) dir = [-dir[0], -dir[1]]; }
    const n = Math.hypot(dir[0], dir[1]) || 1;
    this.onPonto([this.base[0] + dir[0] / n * v, this.base[1] + dir[1] / n * v], {});
  }
}

export class Hachura extends Ferramenta {
  static id = 'hachura'; static nome = 'Hachura'; static atalho = 'g'; static dica = 'Clique dentro de um contorno fechado';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="4" width="16" height="16"/><path d="M4 12l8-8M4 20L20 4M12 20l8-8"/></svg>';
  onPonto(p) {
    const cand = [...this.doc.entidades.values()].filter(e => e.tipo === 'polilinha' && e.fechada && e.vertices.length >= 3 && this.doc.visivel(e) && dentroDe(p, e.vertices));
    if (!cand.length) { this.dica('Nenhum contorno fechado aqui: desenhe uma polilinha fechada (C) primeiro'); return; }
    cand.sort((a, b) => Math.abs(area(a.vertices)) - Math.abs(area(b.vertices)));
    // dois cliques no mesmo contorno empilhavam duas hachuras iguais (lixo invisível)
    if ([...this.doc.entidades.values()].some(h => h.tipo === 'hachura' && (h.atributos || {}).contorno === cand[0].id)) { this.dica('Este contorno já tem hachura'); return; }
    this.editor.executar(new ComandoAdicionar([criar({ tipo: 'hachura', camada: 'HACHURA', contornos: [cand[0].vertices.map(v => [...v])], padrao: 'aco', atributos: { contorno: cand[0].id } })], 'Hachura'));
  }
}
const area = (pts) => pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + (p[0] * q[1] - q[0] * p[1]); }, 0) / 2;

// ---------------------------------------------------------------- edição

class Transformadora extends Ferramenta {
  /** Ferramentas que agem sobre a seleção: se não há, o primeiro clique seleciona. */
  static grupo = 'edicao';
  reiniciar() { super.reiniciar(); this.base = null; this.modoCopia = false; this.editor.snap.direcoes = []; this.ids = [...this.editor.tela.selecao]; this.dica(this.ids.length ? this._comCopia(this.constructor.dica) : 'Selecione os objetos primeiro (clique ou janela) e depois use a ferramenta'); }
  /** Mover e Girar: um toque no Ctrl liga/desliga a cópia (o original fica), como no SketchUp. */
  get aceitaCopia() { return false; }
  alternarCopia() {
    if (!this.aceitaCopia) return;
    this.modoCopia = !this.modoCopia;
    this.dica(this._comCopia(this._dicaAtual || this.constructor.dica));
    this.editor.tela.pedirQuadro();
  }
  _comCopia(t) {
    this._dicaAtual = String(t).replace(/ · (cópia|Ctrl: cópia).*$/, '');
    if (!this.aceitaCopia) return this._dicaAtual;
    return this._dicaAtual + (this.modoCopia ? ' · (cópia) Ctrl: mover o original' : ' · Ctrl: cópia');
  }
  copiaAgora(ev) { return this.aceitaCopia && (!!this.modoCopia !== !!(ev && ev.ctrlKey)); }
  // o que está em camada travada sai da operação (a regra do trava_pecas.js): o Remover/Alterar já eram barrados, mas a
  // cópia (Copiar, Espelhar, Ctrl) passava e criava cópias dentro da camada travada (teste de fluxo, 15/10)
  selecionadas() { return this.ids.map(id => this.doc.get(id)).filter(e => e && !(this.doc.bloqueada && this.doc.bloqueada(e))); }
  /** A base dada: o snap passa a oferecer a guia de 0° e 90° a partir dela (como na Linha) — a distância digitada com o
   *  cursor quase na vertical saía torta. */
  _guiasDaBase(p) { this.editor.snap.ultimo = p; this.editor.snap.direcoes = [[1, 0], [0, 1]]; }
  /** Sem seleção, a janela seleciona (a dica manda "clique ou janela"); com seleção, não há janela. */
  querJanela() { return !this.ids.length; }
  onSoltar(p, ev) {
    if (this.ids.length || !ev || !ev.arrasto) { this.onPonto(p, ev); return; }
    const ids = this.editor.tela.naJanela(ev.arrasto.de, ev.arrasto.para);
    if (ids.length) { this.editor.selecionar(ids); this.ids = ids; this.dica(this._comCopia(this.constructor.dica)); }
  }
  onPonto(p, ev) {
    if (!this.ids.length) {
      const e = this.editor.tela.sob(ev.px);
      // a peça inteira, como na Selecionar (Alt: só a linha)
      if (e) { const ids = ev.altKey ? [e.id] : this.editor.pecaDe(e.id); this.editor.selecionar(ids); this.ids = ids; this.dica(this._comCopia(this.constructor.dica)); }
      return;
    }
    this.passo(p, ev);
  }
}

/** Cópia de uma entidade com identidade nova e grupo de cópia próprio (todas as linhas
 *  copiadas na mesma operação levam o mesmo grupo: continuam sendo "a peça inteira"). */
function copiaDe(e, grupo) {
  return { ...e, id: undefined, atributos: { ...(e.atributos || {}), grupo_copia: grupo } };
}
const novoGrupoCopia = () => 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

/** As cópias criadas (com identidade nova). A cópia de um elemento da estrutura (pilar, viga… do menu Estrutura) ganha
 *  a marca seguinte (P2, P3…) e o rótulo dele, copiado junto, passa a ser o dela — as cópias saíam todas "P1", com o
 *  centro do original, e o Gerar 3D empilhava os pilares num ponto só (06/10). `originais`: as entidades de origem, na
 *  ordem de `novas`. */
function criarCopias(editor, novas, grupo, originais) {
  const copias = novas.map(e => criar(copiaDe(e, grupo)));
  // a cópia de um eixo da malha é um eixo novo (nome seguinte, bolinha, cotas): nucleo/malha.js
  const malha = eixosCopiados(editor.doc, copias, originais);
  copias.trocas = malha.trocas;
  if (typeof editor._proximaMarca === 'function') renumerarElementos(editor, copias, originais);
  const extra = malha.novas;
  if (extra.length) { const trocas = copias.trocas; copias.push(...extra); copias.trocas = trocas; }
  return copias;
}

/** O comando das cópias: acrescenta; com os eixos novos, troca também o que eles esticam (cotas, eixos que cruzam). */
function comandoDasCopias(copias, rotulo) {
  const add = new ComandoAdicionar(copias, rotulo);
  return copias.trocas && copias.trocas.length ? new ComandoComposto([add, new ComandoSubstituir(copias.trocas)], rotulo) : add;
}

function renumerarElementos(editor, copias, originais) {
  const usadas = new Set([...editor.doc.entidades.values()].map(e => (e.atributos || {}).marca).filter(Boolean));
  copias.forEach((c, i) => {
    const a = c.atributos || {};
    if (!a.elemento || !a.marca) return;
    const pref = String(editor._proximaMarca(a.elemento)).replace(/\d+$/, '');
    let n = 1;
    while (usadas.has(pref + n)) n++;
    const marca = pref + n, antiga = a.marca;
    usadas.add(marca);
    c.atributos = { ...a, marca };
    delete c.atributos.centro;                     // a posição é a do desenho (o 3D a tira do contorno)
    const orig = originais && originais[i];
    for (const r of copias) {
      const ra = r.atributos || {};
      if (!orig || ra.rotulo_de !== orig.id) continue;
      r.atributos = { ...ra, rotulo_de: c.id };
      if (r.tipo === 'texto' && r.texto === antiga) r.texto = marca;
    }
  });
}

export class Mover extends Transformadora {
  static id = 'mover'; static nome = 'Mover'; static atalho = 'm'; static dica = 'Ponto base do deslocamento';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/></svg>';
  copiar = false;
  get aceitaCopia() { return !this.copiar; }
  passo(p, ev) {
    if (!this.base) { this.base = p; this._guiasDaBase(p); this.dica(this._comCopia('Ponto de destino, ou digite a distância (ou dx;dy)')); return; }
    const d = [p[0] - this.base[0], p[1] - this.base[1]];
    const novas = this.selecionadas().map(e => transladar(e, d));
    if (!this.copiar && this.copiaAgora(ev)) {
      // Mover com Ctrl: a cópia vai para o destino, o original fica; a cópia fica selecionada
      const grupo = novoGrupoCopia();
      const copias = criarCopias(this.editor, novas, grupo, this.selecionadas());
      this.editor.executar(comandoDasCopias(copias, 'Copiar'));
      this.editor.selecionar(copias.map(c => c.id));
      this.reiniciar();
      return;
    }
    if (this.copiar) {
      const grupo = novoGrupoCopia();
      const copias = criarCopias(this.editor, novas, grupo, this.selecionadas());
      const cmd = comandoDasCopias(copias, 'Copiar');
      this.editor.executar(cmd);
      // o ponto base continua o mesmo: cada novo destino é medido da referência
      // original (como no AutoCAD), e a seleção copiada é sempre a original
      this.dica('Próximo destino, medido do mesmo ponto base (Esc termina)');
    } else {
      this.editor.executar(new ComandoSubstituir([...novas, ...this._cotasLigadas(d)], 'Mover'));
      this.reiniciar();
    }
  }
  /**
   * Cotas associativas: movendo furos (camada FURO), a cota horizontal cujo ponto está
   * na coluna do furo anda em x, e a vertical cuja linha é a do furo anda em y — desde
   * que todos os furos daquela coluna/linha estejam sendo movidos.
   */
  _cotasLigadas(d) {
    const sel = new Set(this.ids);
    const centro = (e) => e.tipo === 'circulo' ? e.centro
      : e.tipo === 'polilinha' ? (() => { const xs = e.vertices.map(q => q[0]), ys = e.vertices.map(q => q[1]); return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]; })()
      : null;
    if (!this.selecionadas().some(e => e.camada === 'FURO' && centro(e))) return [];
    const furos = [];
    for (const e of this.doc.entidades.values()) {
      if (e.camada !== 'FURO' || (e.tipo !== 'circulo' && e.tipo !== 'polilinha')) continue;
      const c = centro(e); if (c) furos.push({ id: e.id, c, pos: (e.atributos || {}).posicao || null });
    }
    const out = [];
    for (const e of this.doc.entidades.values()) {
      if (e.tipo !== 'cota' || sel.has(e.id) || (e.modo !== 'h' && e.modo !== 'v')) continue;
      const pe = (e.atributos || {}).posicao || null;
      const k = e.modo === 'h' ? 0 : 1;
      const p1 = e.p1.slice(), p2 = e.p2.slice();
      let mudou = false;
      for (const p of [p1, p2]) {
        const ali = furos.filter(f => (!pe || !f.pos || f.pos === pe) && Math.abs(f.c[k] - p[k]) < 0.05);
        if (!ali.length || !ali.every(f => sel.has(f.id))) continue;
        p[k] += d[k]; mudou = true;
      }
      if (mudou) out.push(criar({ ...e, p1, p2 }));
    }
    return out;
  }
  onMover(p, ev) {
    if (!this.base) return;
    const d = [p[0] - this.base[0], p[1] - this.base[1]];
    const copia = this.copiar || this.copiaAgora(ev);
    this.editor.previa([...this.selecionadas().map(e => transladar(e, d)), ...(copia ? [] : this._cotasLigadas(d))]);
    this.editor.medida(`${fmt(dist(this.base, p))} mm  ∠ ${fmt(ang(this.base, p) * 180 / Math.PI)}°${copia && !this.copiar ? '  (cópia)' : ''}`);
  }
  onValor(t) {
    if (!this.base) return;
    // "500;300" (ou "@500;300"): o deslocamento em x e y, como o "largura;altura" do Retângulo
    const xy = String(t).trim().match(/^@?\s*([^;]+);\s*([^;]+)$/);
    if (xy) {
      const dx = paraMilimetros(xy[1]), dy = paraMilimetros(xy[2]);
      if (dx != null && dy != null) { this.passo([this.base[0] + dx, this.base[1] + dy], {}); return; }
    }
    const alvo = this.editor.tela.cursor || this.base;
    const m = t.match(/^(.*?)(?:<|@)(-?\d+(?:[.,]\d+)?)$/);
    const comp = paraMilimetros(m ? m[1] : t);
    if (comp == null) { this.dica('Medida não entendida: 1500, 1,5m, 1500@30 ou 500;300'); return; }
    this.passo(polar(this.base, m ? parseFloat(m[2].replace(',', '.')) * Math.PI / 180 : ang(this.base, alvo), comp), {});
  }
}

export class Copiar extends Mover {
  static id = 'copiar'; static nome = 'Copiar'; static atalho = 'o'; static dica = 'Ponto base da cópia';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="8" y="8" width="12" height="12"/><path d="M4 16V4h12"/></svg>';
  copiar = true;
}

export class Girar extends Transformadora {
  static id = 'girar'; static nome = 'Girar'; static atalho = 'q'; static dica = 'Centro de rotação';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4h-4"/></svg>';
  reiniciar() { super.reiniciar(); this.ref = null; }
  get aceitaCopia() { return true; }
  /** Gira a seleção; em modo cópia (Ctrl), gira uma cópia e o original fica. */
  _aplicar(theta, ev) {
    const giradas = this._girar(theta);
    if (this.copiaAgora(ev)) {
      const grupo = novoGrupoCopia();
      const copias = criarCopias(this.editor, giradas, grupo, this.selecionadas());
      this.editor.executar(comandoDasCopias(copias, 'Girar cópia'));
      this.editor.selecionar(copias.map(c => c.id));
    } else {
      this.editor.executar(new ComandoSubstituir(giradas, 'Girar'));
    }
    this.reiniciar();
  }
  _girar(theta) {
    const c = this.base, co = Math.cos(theta), si = Math.sin(theta);
    const f = (p) => [c[0] + (p[0] - c[0]) * co - (p[1] - c[1]) * si, c[1] + (p[0] - c[0]) * si + (p[1] - c[1]) * co];
    return this.selecionadas().map(e => transformar(e, f, (a) => a + theta * 180 / Math.PI));
  }
  passo(p, ev) {
    if (!this.base) { this.base = p; this._guiasDaBase(p); this.dica(this._comCopia('Ponto de referência do ângulo, ou digite o ângulo em graus')); return; }
    if (!this.ref) { this.ref = p; this.dica(this._comCopia('Novo ângulo')); return; }
    this._aplicar(ang(this.base, p) - ang(this.base, this.ref), ev);
  }
  onMover(p, ev) {
    if (this.base && this.ref) { const th = ang(this.base, p) - ang(this.base, this.ref); this.editor.previa(this._girar(th)); this.editor.medida(`${fmt(th * 180 / Math.PI)}°${this.copiaAgora(ev) ? '  (cópia)' : ''}`); }
    else if (this.base) this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.base, b: p })]);
  }
  onValor(t) {
    if (!this.base) return;
    const g = parseFloat(t.replace(',', '.'));
    if (!isFinite(g)) { this.dica('Ângulo não entendido: digite os graus (90, -45, 22,5)'); return; }
    this._aplicar(g * Math.PI / 180, {});
  }
}

/**
 * Escala — o SCALE do AutoCAD (pedido do usuário, 06/10: "alterar a escala com referência"): selecione, clique no ponto
 * base e digite o fator (2, 0,5) e Enter; ou R (referência): dois cliques numa medida conhecida do desenho e a medida
 * que ela deve ter (digitada — 5050, 5,05m, 505cm — ou clicada a partir do primeiro ponto). O que é de papel (altura do
 * texto, da cota, espaçamento da hachura) fica como está, como no Calibrar.
 */
export class Escalar extends Transformadora {
  /** A Escala pergunta antes de escalar o que está em camada travada (calibrar o desenho do cliente): ela vê todas. */
  todasSelecionadas() { return this.ids.map(id => this.doc.get(id)).filter(Boolean); }
  static id = 'escalar'; static nome = 'Escala (fator ou referência)'; static atalho = '';
  static dica = 'Ponto base da escala (ou já digite o fator e Enter: a base é o centro da seleção) · R: por referência';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="10" height="10"/><path d="M9 11V5h10v10h-6"/><path d="M13 11l6-6M15 5h4v4"/></svg>';
  reiniciar() { super.reiniciar(); this.modo = 'fator'; this.r1 = null; this.r2 = null; }
  _escalar(k) {
    const c = this.base;
    const f = (p) => [c[0] + (p[0] - c[0]) * k, c[1] + (p[1] - c[1]) * k];
    return this.todasSelecionadas().map(e => transformar(e, f, (a) => a, k));
  }
  async _aplicar(k) {
    if (!(k > 0) || !isFinite(k)) { this.dica('Fator inválido: tem de ser maior que zero'); return; }
    if (Math.abs(k - 1) < 1e-4) {
      // a medida digitada é a que o desenho já tem (06/10: a cota "1800" da quadra é em cm, e 1800 deu ×1)
      this.editor.aviso('Fator 1: nada muda — a medida digitada é a mesma do desenho. Se as cotas do projeto estão em centímetros, digite com a unidade: 1800cm ou 18m.', 'atencao', 12000);
      this.reiniciar();
      return;
    }
    const sel = this.todasSelecionadas();
    const cmd = new ComandoSubstituir(this._escalar(k), `Escala ×${String(Math.round(k * 10000) / 10000).replace('.', ',')}`);
    const travadas = sel.filter(e => this.doc.bloqueada && this.doc.bloqueada(e)).length;
    if (travadas) {
      // escalar o desenho do cliente (camadas travadas) é calibrar: pergunta, e com o sim a trava não barra (como o
      // Calibrar escala) — antes a escala parava em "Camada travada" (06/10)
      const corpo = document.createElement('div');
      corpo.className = 'explica';
      corpo.textContent = `${travadas} dos ${sel.length} objeto(s) selecionados estão em camadas travadas (o desenho do cliente). ` +
        'Escalar tudo, também os travados? Eles continuam travados depois.';
      if (await this.editor.dialogo({ titulo: 'Escala em camadas travadas', corpo, ok: 'Escalar tudo' }) !== 'ok') { this.reiniciar(); return; }
      cmd.semTrava = true;
    }
    if (this.editor.executar(cmd) === null) { this.reiniciar(); return; }
    this.editor.aviso(`Escala ×${k.toLocaleString('pt-BR', { maximumFractionDigits: 4 })} aplicada em ${cmd.novas.length} objeto(s). Ctrl+Z desfaz.`, 'info', 6000);
    this.reiniciar();
  }
  _referencia() {
    this.modo = 'referencia'; this.r1 = null; this.r2 = null;
    this.dica('Referência: clique no primeiro ponto de uma medida conhecida');
  }
  passo(p) {
    if (!this.base) { this.base = p; this.editor.snap.ultimo = p; this.dica('Digite o fator e Enter · R: por referência (uma medida conhecida)'); return; }
    if (this.modo !== 'referencia') return;
    if (!this.r1) { this.r1 = p; this.editor.snap.ultimo = p; this.dica('Referência: clique no segundo ponto da medida conhecida'); return; }
    if (!this.r2) {
      if (dist(this.r1, p) < 1e-6) return;
      this.r2 = p; this.editor.snap.ultimo = this.r1;
      this.dica(`A referência mede ${fmt(dist(this.r1, p))} no desenho: digite a medida nova (5050, 5,05m, 505cm) e Enter, ou clique o ponto a partir do primeiro`);
      return;
    }
    const nova = dist(this.r1, p);
    if (nova > 1e-6) this._aplicar(nova / dist(this.r1, this.r2));
  }
  onMover(p) {
    if (!this.base) return;
    if (this.modo === 'referencia') {
      if (this.r1 && !this.r2) {
        this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.r1, b: p })]);
        this.editor.medida(`referência ${fmt(dist(this.r1, p))}`);
      } else if (this.r2) {
        const k = dist(this.r1, p) / dist(this.r1, this.r2);
        if (k > 1e-6) { this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.r1, b: p }), ...this._escalar(k)]); this.editor.medida(`${fmt(dist(this.r1, p))} · ×${String(Math.round(k * 1000) / 1000).replace('.', ',')}`); }
      }
      return;
    }
    this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.base, b: p })]);
  }
  /** Sem o ponto base clicado, o centro do que está selecionado (digitar o fator direto, sem clicar — 06/10). */
  _baseNoCentro() {
    if (this.base || !this.ids.length) return !!this.base;
    const ps = this.selecionadas().flatMap(e => pontosDe(e));
    if (!ps.length) return false;
    const xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
    this.base = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
    return true;
  }
  onValor(t) {
    if (!this._baseNoCentro()) return;
    const txt = String(t).trim();
    if (/^r(ef(er[eê]ncia)?)?$/i.test(txt)) { this._referencia(); return; }
    if (this.modo === 'referencia') {
      if (!this.r2) return;
      const nova = paraMilimetros(txt);
      if (nova > 0) this._aplicar(nova / dist(this.r1, this.r2));
      else this.dica('Medida não entendida: use 5050, 5,05m ou 505cm');
      return;
    }
    const k = parseFloat(txt.replace(',', '.'));
    this._aplicar(k);
  }
  onTecla(ev) {
    if (this.ids.length && this.modo === 'fator' && !ev.ctrlKey && !ev.metaKey && !ev.altKey && (ev.key === 'r' || ev.key === 'R')) {
      if (!this.base && !this._baseNoCentro()) return false;
      this._referencia(); return true;
    }
    return false;
  }
}

export class Espelhar extends Transformadora {
  static id = 'espelhar'; static nome = 'Espelhar'; static atalho = 'i'; static dica = 'Primeiro ponto do eixo de espelho';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v18" stroke-dasharray="3 2"/><path d="M4 8l5 4-5 4zM20 8l-5 4 5 4z"/></svg>';
  _espelhar(a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1;
    const f = (p) => { const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2; const q = [a[0] + t * dx, a[1] + t * dy]; return [2 * q[0] - p[0], 2 * q[1] - p[1]]; };
    const angEixo = Math.atan2(dy, dx) * 180 / Math.PI;
    return this.selecionadas().map(e => transformar(e, f, (g) => 2 * angEixo - g, 1, true));
  }
  passo(p) {
    if (!this.base) { this.base = p; this._guiasDaBase(p); this.dica('Segundo ponto do eixo'); return; }
    if (dist(p, this.base) < 1e-6) return;
    const novas = this._espelhar(this.base, p);
    const grupo = novoGrupoCopia();
    this.editor.executar(comandoDasCopias(criarCopias(this.editor, novas, grupo, this.selecionadas()), 'Espelhar'));
    this.reiniciar();
  }
  onMover(p) { if (this.base) this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.base, b: p }), ...this._espelhar(this.base, p)]); }
}

/**
 * Copiar propriedades — o MATCHPROP (MA) do AutoCAD (pedido do usuário, 28/09): clique no objeto de
 * origem (ou selecione-o antes) e depois em cada objeto que recebe; Esc termina. Vão a camada e o
 * estilo do tipo: na cota a altura, o terminador e as casas decimais; no texto e na chamada a altura;
 * na hachura o padrão, o espaçamento e o ângulo. Atalho: M e logo depois A (M sozinho é Mover).
 */
export class CopiarPropriedades extends Ferramenta {
  static id = 'copiar_propriedades'; static nome = 'Copiar propriedades (MA)'; static atalho = ''; static grupo = 'edicao';
  static dica = 'Clique no objeto de origem (o que tem as propriedades certas)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 4l6 6-8 8H6v-6z"/><path d="M4 20h6"/></svg>';
  // na cota, o estilo dela inteiro: o tamanho (altura e fator, que leva a ponta e os afastamentos), o terminador, as
  // casas e a folga do número (22/10); a escala não, que muda o número medido
  static CAMPOS = { cota: ['altura', 'fator', 'terminador', 'casas', 'folga'], cota_especial: ['altura', 'fator', 'terminador', 'casas', 'folga'], texto: ['altura'], chamada: ['altura'], hachura: ['padrao', 'espacamento', 'angulo'] };
  reiniciar() {
    super.reiniciar();
    const sel = [...this.editor.tela.selecao];
    this.fonte = sel.length === 1 ? this.doc.get(sel[0]) : null;
    this.dica(this.fonte ? `Origem: ${this.fonte.tipo} na camada ${this.fonte.camada}. Clique nos objetos que recebem (ou arraste uma caixa) · Esc termina` : this.constructor.dica);
  }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (!e) { this.dica(this.fonte ? 'Clique num objeto para receber as propriedades · Esc termina' : this.constructor.dica); return; }
    if (!this.fonte) {
      this.fonte = e;
      this.editor.selecionar([e.id]);
      this.dica(`Origem: ${e.tipo} na camada ${e.camada}. Agora clique nos objetos que recebem (ou arraste uma caixa) · Esc termina`);
      return;
    }
    if (e.id === this.fonte.id) return;
    this._aplicar([e]);
  }
  /** Caixa de seleção (janela ou cruzamento, como na Selecionar): todos os objetos dela recebem
   *  as propriedades de uma vez (pedido do usuário, 28/09). */
  onSoltar(p, ev) {
    if (!ev.arrasto) return;
    if (!this.fonte) { this.dica('Clique primeiro no objeto de origem; depois a caixa passa as propriedades dele'); return; }
    const alvos = this.editor.tela.naJanela(ev.arrasto.de, ev.arrasto.para)
      .filter(id => id !== this.fonte.id).map(id => this.doc.get(id)).filter(Boolean);
    if (!alvos.length) { this.dica('Nenhum objeto na caixa · Esc termina'); return; }
    this._aplicar(alvos);
  }
  _aplicar(alvos) {
    const novos = alvos.filter(e => !this.doc.bloqueada(e)).map(e => {
      const m = { camada: this.fonte.camada };
      if (e.tipo === this.fonte.tipo) for (const k of CopiarPropriedades.CAMPOS[e.tipo] || []) m[k] = clonar(this.fonte[k] ?? null);
      else if ((e.tipo === 'texto' || e.tipo === 'chamada' || e.tipo === 'cota') && this.fonte.altura) m.altura = this.fonte.altura;
      return criar({ ...clonar(e), ...m });
    });
    if (!novos.length) return;
    this.editor.executar(new ComandoSubstituir(novos, 'Copiar propriedades'));
    const o = novos.length === 1 ? novos[0].tipo : `${novos.length} objetos`;
    this.dica(`Propriedades copiadas para ${o}. Clique em outro objeto ou arraste uma caixa · Esc termina`);
  }
}

export class Apagar extends Ferramenta {
  static id = 'apagar'; static nome = 'Apagar'; static atalho = 'e'; static grupo = 'edicao'; static dica = 'Clique no objeto para apagar (ou selecione e Del)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>';
  ativar() { super.ativar(); if (this.editor.tela.selecao.size) this.editor.apagarSelecao(); }
  onPonto(p, ev) { const e = this.editor.tela.sob(ev.px); if (e) this.editor.executar(new ComandoRemover([e.id])); }
}

/**
 * Ferramenta que age na seleção (ou, sem seleção, no que for clicado) e volta para a
 * Selecionar: a base de Explodir e Juntar.
 */
class SobreSelecao extends Ferramenta {
  static grupo = 'edicao';
  ativar() {
    super.ativar();
    const ids = [...this.editor.tela.selecao];
    if (ids.length) { this.aplicar(ids); this._voltarComAviso(); }
  }
  /** Volta à Selecionar sem perder o que a ferramenta disse ("4 linhas soltas", "Nada para explodir"): o reiniciar da
   *  Selecionar reescrevia a dica na hora. */
  _voltarComAviso() {
    const msg = this.editor.el && this.editor.el.dica ? this.editor.el.dica.textContent : '';
    this.editor.ativarFerramenta('selecionar');
    if (msg) { this.editor.dica(msg); this.editor.aviso(msg, 'info', 6000); }
  }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (!e) return;
    this.aplicar(ev.altKey ? [e.id] : this.editor.pecaDe(e.id));
  }
  aplicar(ids) {}
}

/** Linha solta, sem o vínculo de peça: a origem vai para `origem_explodida` (o Juntar a
 *  devolve) e os atributos de peça saem. */
function soltaDePeca(atributos) {
  const a = { ...(atributos || {}) };
  if (a.origem) { a.origem_explodida = a.origem; delete a.origem; }
  delete a.nos_chanfro; delete a.chanfro;
  return a;
}

export class Explodir extends SobreSelecao {
  static id = 'explodir'; static nome = 'Explodir (em linhas)'; static atalho = 'b';
  static dica = 'Clique na peça (ou selecione antes): vira linhas soltas, editáveis uma a uma · Juntar (W) volta';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 12h5M15 12h5M12 4v5M12 15v5M6 6l3 3M18 6l-3 3M6 18l3-3M18 18l-3-3"/></svg>';
  aplicar(ids) {
    const remover = [], novas = [];
    for (const id of ids) {
      const e = this.doc.get(id);
      // a travada fica como está (a polilinha ficava e ganhava as linhas soltas por cima)
      if (!e || !this.doc.visivel(e) || this.doc.bloqueada(e)) continue;
      if (e.tipo === 'polilinha') {
        const vs = e.vertices, n = vs.length;
        const segs = [];
        for (let i = 0; i + 1 < n; i++) segs.push([vs[i], vs[i + 1]]);
        if (e.fechada && n > 2) segs.push([vs[n - 1], vs[0]]);
        for (const [a, b] of segs) {
          if (dist(a, b) < 1e-6) continue;
          novas.push(criar({ tipo: 'linha', camada: e.camada, a: [...a], b: [...b], atributos: soltaDePeca(e.atributos) }));
        }
        remover.push(id);
      } else if (e.tipo === 'linha' && (e.atributos || {}).origem) {
        novas.push(criar({ ...clonar(e), id: undefined, atributos: soltaDePeca(e.atributos) }));
        remover.push(id);
      } else if (e.tipo === 'bloco') {
        // a inserção do bloco (24/10): as entidades dela, soltas (o bloco de dentro continua bloco, como no AutoCAD)
        for (const f of filhosDoBloco(e)) novas.push(criar({ ...clonar(f), id: undefined }));
        remover.push(id);
      }
    }
    if (!remover.length) { this.dica('Nada para explodir: só blocos, polilinhas e linhas de peça viram objetos soltos'); return; }
    this.editor.executar(new ComandoComposto([new ComandoRemover(remover), new ComandoAdicionar(novas)], `Explodir ${remover.length} objeto(s)`));
    this.editor.selecionar(novas.map(e => e.id));
    this.dica(`${novas.length} linha(s) soltas · Juntar (W) volta a juntar`);
  }
}

export class Juntar extends SobreSelecao {
  static id = 'juntar'; static nome = 'Juntar (join)'; static atalho = 'w';
  static dica = 'Selecione as linhas (janela ou Shift+clique) e escolha Juntar: as que se tocam viram polilinha; se vieram da mesma peça, voltam a ser a peça';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 18 10 8l5 7 5-9"/><circle cx="10" cy="8" r="1.6" fill="currentColor"/><circle cx="15" cy="15" r="1.6" fill="currentColor"/></svg>';
  onPonto(p, ev) {
    // um clique solto só acrescenta à seleção; juntar é com a seleção feita
    const e = this.editor.tela.sob(ev.px);
    if (e) this.editor.selecionar([...this.editor.tela.selecao, e.id]);
  }
  onTecla(ev) {
    if (ev.key === 'Enter') { this.aplicar([...this.editor.tela.selecao]); return true; }
    return false;
  }
  aplicar(ids) {
    const tol = 0.5;
    const pecas = ids.map(id => this.doc.get(id)).filter(e => e && (e.tipo === 'linha' || e.tipo === 'polilinha') && this.doc.visivel(e) && !this.doc.bloqueada(e));
    if (pecas.length < 2) { this.dica('Selecione duas ou mais linhas que se tocam e tecle Enter'); return; }
    // cada objeto vira uma cadeia de pontos; as cadeias que se tocam pelas pontas emendam
    let cadeias = pecas.map(e => ({ pts: e.tipo === 'linha' ? [e.a, e.b] : [...e.vertices], fechada: e.tipo === 'polilinha' && !!e.fechada, fontes: [e] }));
    const perto = (a, b) => dist(a, b) <= tol;
    let emendou = true;
    while (emendou) {
      emendou = false;
      for (let i = 0; i < cadeias.length && !emendou; i++) {
        const c = cadeias[i];
        if (c.fechada) continue;
        for (let j = i + 1; j < cadeias.length && !emendou; j++) {
          const d = cadeias[j];
          if (d.fechada) continue;
          const a0 = c.pts[0], a1 = c.pts[c.pts.length - 1], b0 = d.pts[0], b1 = d.pts[d.pts.length - 1];
          let pts = null;
          if (perto(a1, b0)) pts = c.pts.concat(d.pts.slice(1));
          else if (perto(a1, b1)) pts = c.pts.concat([...d.pts].reverse().slice(1));
          else if (perto(a0, b1)) pts = d.pts.concat(c.pts.slice(1));
          else if (perto(a0, b0)) pts = [...d.pts].reverse().concat(c.pts.slice(1));
          if (!pts) continue;
          const fechada = pts.length > 3 && perto(pts[0], pts[pts.length - 1]);
          if (fechada) pts = pts.slice(0, -1);
          cadeias[i] = { pts, fechada, fontes: c.fontes.concat(d.fontes) };
          cadeias.splice(j, 1);
          emendou = true;
        }
      }
    }
    const juntadas = cadeias.filter(c => c.fontes.length > 1);
    if (!juntadas.length) { this.dica('Nenhuma ponta encosta em outra (tolerância 0,5 mm): nada juntado'); return; }
    const remover = [], novas = [];
    for (const c of juntadas) {
      const base = c.fontes[0];
      const origens = new Set(c.fontes.map(f => (f.atributos || {}).origem || (f.atributos || {}).origem_explodida || ''));
      const atr = { ...(base.atributos || {}) };
      delete atr.origem_explodida;
      // todas da mesma peça: voltam a ser a peça (seleção, Mesma peça, Ver no 3D)
      if (origens.size === 1 && [...origens][0]) atr.origem = [...origens][0];
      else delete atr.origem;
      novas.push(criar({ tipo: 'polilinha', camada: base.camada, vertices: c.pts.map(q => [...q]), fechada: c.fechada, atributos: atr }));
      for (const f of c.fontes) remover.push(f.id);
    }
    this.editor.executar(new ComandoComposto([new ComandoRemover(remover), new ComandoAdicionar(novas)], `Juntar ${remover.length} objeto(s)`));
    this.editor.selecionar(novas.map(e => e.id));
    this.dica(`${remover.length} objeto(s) juntados em ${novas.length} polilinha(s)`);
  }
  ativar() {
    Ferramenta.prototype.ativar.call(this);
    const ids = [...this.editor.tela.selecao];
    if (ids.length > 1) { this.aplicar(ids); this._voltarComAviso(); }
  }
}

export class Aparar extends Ferramenta {
  static id = 'aparar'; static nome = 'Aparar (trim)'; static atalho = 'tr'; static grupo = 'edicao'; static dica = 'Clique no trecho da linha a remover (corta nas interseções com outras linhas)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6h16M4 18h16M12 3v18" stroke-dasharray="4 2"/><path d="M9 9l6 6"/></svg>';
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    // o trecho que sai é o do MOUSE, não o do snap: clicando ao lado de uma interseção, o snap levava o ponto para ela e
    // saía o trecho do outro lado (teste de fluxo, 15/10)
    const q = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;
    if (e && e.tipo === 'arco') { this._apararArco(e, q); return; }
    if (e && e.tipo === 'circulo') { this._apararCirculo(e, q); return; }
    if (e && e.tipo === 'polilinha') { this._apararPolilinha(e, q); return; }
    if (!e || e.tipo !== 'linha') { this.dica('Aparar funciona em linhas, polilinhas, arcos e círculos: clique no trecho a remover'); return; }
    const outros = [...this.doc.entidades.values()].filter(o => o.id !== e.id && this.doc.visivel(o));
    const cortes = [];
    for (const o of outros) cortes.push(...cortesComEntidade(e.a, e.b, o));
    const L = dist(e.a, e.b), ts = cortes.map(c => dist(e.a, c) / L).filter(t => t > 1e-6 && t < 1 - 1e-6).sort((a, b) => a - b);
    // só os cortes do meio contam: a linha que só encosta numa outra pela ponta saía apagada inteira
    if (!ts.length) { this.dica('A linha não cruza nenhuma outra'); return; }
    const tp = dist(e.a, maisProximoSeg(q, e.a, e.b)) / L;
    const limites = [0, ...ts, 1];
    let i = 0;
    while (i < limites.length - 1 && !(tp >= limites[i] && tp <= limites[i + 1])) i++;
    const at = (t) => [e.a[0] + t * (e.b[0] - e.a[0]), e.a[1] + t * (e.b[1] - e.a[1])];
    const restantes = [];
    if (limites[i] > 1e-6) restantes.push(criar({ ...e, id: undefined, a: e.a, b: at(limites[i]) }));
    if (limites[i + 1] < 1 - 1e-6) restantes.push(criar({ ...e, id: undefined, a: at(limites[i + 1]), b: e.b }));
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar(restantes)], 'Aparar'));
  }
  /** O trecho do arco entre os dois cortes em volta do clique sai; os cortes são as interseções da curva com o resto. */
  _apararArco(e, p) {
    const span = vaoDoArco(e);
    const rel = (q) => (((Math.atan2(q[1] - e.centro[1], q[0] - e.centro[0]) * 180 / Math.PI - e.inicio) % 360) + 360) % 360;
    const outros = [...this.doc.entidades.values()].filter(o => o.id !== e.id && this.doc.visivel(o));
    const ts = [];
    for (const o of outros) for (const q of cortesNoCirculo(e.centro, e.raio, o)) { const t = rel(q); if (t > 1e-6 && t < span - 1e-6) ts.push(t); }
    if (!ts.length) { this.dica('O arco não cruza nenhuma outra linha'); return; }
    ts.sort((a, b) => a - b);
    const tp = Math.min(span, rel(p));
    const lim = [0, ...ts, span];
    let i = 0;
    while (i < lim.length - 1 && !(tp >= lim[i] && tp <= lim[i + 1])) i++;
    const restantes = [];
    if (lim[i] > 1e-6) restantes.push(criar({ ...e, id: undefined, inicio: e.inicio, fim: e.inicio + lim[i] }));
    if (lim[i + 1] < span - 1e-6) restantes.push(criar({ ...e, id: undefined, inicio: e.inicio + lim[i + 1], fim: e.inicio + span }));
    for (const r of restantes) { r.inicio = ((r.inicio % 360) + 360) % 360; r.fim = ((r.fim % 360) + 360) % 360; }
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar(restantes)], 'Aparar'));
  }
  /** Círculo: sai o trecho entre os dois cortes em volta do clique; fica um arco (precisa de dois cortes, como no TRIM). */
  _apararCirculo(e, p) {
    const n = (g) => ((g % 360) + 360) % 360;
    const ang = (q) => n(Math.atan2(q[1] - e.centro[1], q[0] - e.centro[0]) * 180 / Math.PI);
    const outros = [...this.doc.entidades.values()].filter(o => o.id !== e.id && this.doc.visivel(o));
    const as = [];
    for (const o of outros) for (const q of cortesNoCirculo(e.centro, e.raio, o)) {
      const g = ang(q);
      if (!as.some(x => Math.abs(x - g) < 1e-6 || Math.abs(Math.abs(x - g) - 360) < 1e-6)) as.push(g);
    }
    if (as.length < 2) { this.dica('O círculo precisa ser cortado em dois pontos para aparar um trecho'); return; }
    as.sort((a, b) => a - b);
    const g = ang(p);
    const depois = as.find(x => x > g) ?? as[0];
    const antes = [...as].reverse().find(x => x < g) ?? as[as.length - 1];
    const arco = criar({ ...e, id: undefined, tipo: 'arco', inicio: depois, fim: antes });
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar([arco])], 'Aparar'));
  }
  /** Polilinha: os cortes pelo comprimento ao longo dela; sai o trecho entre os dois em volta do clique. Na aberta ficam
   *  os pedaços das duas pontas; na fechada, um pedaço só, de corte a corte, dando a volta. */
  _apararPolilinha(e, p) {
    const segs = segmentosDe(e);
    if (!segs.length) return;
    const S = [0];
    for (const [a, b] of segs) S.push(S[S.length - 1] + dist(a, b));
    const T = S[S.length - 1];
    if (T < 1e-9) return;
    const outros = [...this.doc.entidades.values()].filter(o => o.id !== e.id && this.doc.visivel(o));
    const cortes = [];
    segs.forEach(([a, b], k) => {
      for (const o of outros) for (const x of cortesComEntidade(a, b, o)) cortes.push(S[k] + dist(a, x));
    });
    const fechada = !!(e.fechada && e.vertices.length > 2);
    const unicos = [];
    for (const c of cortes.sort((a, b) => a - b)) {
      const cc = fechada ? ((c % T) + T) % T : c;
      if (!fechada && (cc < 1e-6 || cc > T - 1e-6)) continue;
      if (!unicos.some(u => Math.abs(u - cc) < 1e-6 || (fechada && Math.abs(Math.abs(u - cc) - T) < 1e-6))) unicos.push(cc);
    }
    unicos.sort((a, b) => a - b);
    if (fechada ? unicos.length < 2 : !unicos.length) { this.dica(fechada ? 'O contorno precisa ser cortado em dois pontos para aparar um trecho' : 'A polilinha não cruza nenhuma outra'); return; }
    // o ponto do clique ao longo da polilinha (pelo segmento mais perto)
    let k0 = 0, dmin = Infinity;
    segs.forEach(([a, b], k) => { const d = dist(p, maisProximoSeg(p, a, b)); if (d < dmin) { dmin = d; k0 = k; } });
    const sp = S[k0] + dist(segs[k0][0], maisProximoSeg(p, segs[k0][0], segs[k0][1]));
    const pontoEm = (x) => {
      let k = 0;
      while (k < segs.length - 1 && x > S[k + 1]) k++;
      const [a, b] = segs[k], L = (S[k + 1] - S[k]) || 1, t = Math.max(0, Math.min(1, (x - S[k]) / L));
      return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    };
    // os pontos da polilinha de `de` a `ate` (de < ate), com os vértices do meio
    const trecho = (de, ate) => {
      const out = [pontoEm(de)];
      for (let k = 1; k < segs.length; k++) if (S[k] > de + 1e-6 && S[k] < ate - 1e-6) out.push(segs[k][0]);
      out.push(pontoEm(ate));
      return out;
    };
    const nova = (vs) => criar({ ...e, id: undefined, vertices: vs, fechada: false });
    const restantes = [];
    if (!fechada) {
      const lim = [0, ...unicos, T];
      let i = 0;
      while (i < lim.length - 1 && !(sp >= lim[i] && sp <= lim[i + 1])) i++;
      if (lim[i] > 1e-6) restantes.push(nova(trecho(0, lim[i])));
      if (lim[i + 1] < T - 1e-6) restantes.push(nova(trecho(lim[i + 1], T)));
    } else {
      // o corte logo depois do clique e o logo antes; fica o caminho de "depois" até "antes", dando a volta
      const depois = unicos.find(x => x > sp) ?? unicos[0];
      const antes = [...unicos].reverse().find(x => x < sp) ?? unicos[unicos.length - 1];
      const vs = depois < antes ? trecho(depois, antes) : [...trecho(depois, T), ...trecho(0, antes).slice(1)];
      restantes.push(nova(vs));
    }
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), new ComandoAdicionar(restantes)], 'Aparar'));
  }
}

/** o ângulo do arco (graus, de `inicio` a `fim` no sentido anti-horário) */
function vaoDoArco(e) { let s = e.fim - e.inicio; while (s <= 0) s += 360; while (s > 360) s -= 360; return s; }

/** a corda e a flecha do arco (mm) */
function geometriaDoArco(e) {
  const s = vaoDoArco(e) * Math.PI / 180;
  return { corda: 2 * e.raio * Math.sin(s / 2), flecha: e.raio * (1 - Math.cos(s / 2)) };
}

/** O arco com a alça `parte` levada a `p`: a ponta (a0 / a1) anda na mesma curva; o meio ('curva') faz o arco pelos
 *  três pontos (as pontas ficam). null quando não dá arco (três pontos alinhados, ponta sobre a outra). */
function arcoPelaAlca(e, parte, p) {
  const ang = (q, c) => ((Math.atan2(q[1] - c[1], q[0] - c[0]) * 180 / Math.PI) % 360 + 360) % 360;
  const pt = (g) => [e.centro[0] + e.raio * Math.cos(g * Math.PI / 180), e.centro[1] + e.raio * Math.sin(g * Math.PI / 180)];
  if (parte === 'a0' || parte === 'a1') {
    if (dist(p, e.centro) < 1e-6) return null;
    const g = ang(p, e.centro);
    const nova = { ...e, [parte === 'a0' ? 'inicio' : 'fim']: g };
    if (vaoDoArco(nova) < 1e-4 || vaoDoArco(nova) > 359.9) return null;
    return criar(nova);
  }
  const P0 = pt(e.inicio), P2 = pt(e.fim);
  const c = centroPorTresPontos(P0, p, P2);
  if (!c) return null;
  const r = dist(c, P0), a0 = ang(P0, c), a1 = ang(p, c), a2 = ang(P2, c);
  const dentro = (x, de, ate) => { const s = ((ate - de) % 360 + 360) % 360, t = ((x - de) % 360 + 360) % 360; return t <= s; };
  return criar(dentro(a1, a0, a2) ? { ...e, centro: c, raio: r, inicio: a0, fim: a2 } : { ...e, centro: c, raio: r, inicio: a2, fim: a0 });
}

function centroPorTresPontos(a, b, c) {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
  if (Math.abs(d) < 1e-9) return null;
  const a2 = a[0] * a[0] + a[1] * a[1], b2 = b[0] * b[0] + b[1] * b[1], c2 = c[0] * c[0] + c[1] * c[1];
  return [(a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d, (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d];
}

/** Os pontos onde o círculo (centro `c`, raio `r`) cruza a entidade `o` (linhas e polilinhas pelos segmentos; arcos e
 *  círculos pela curva). */
function cortesNoCirculo(c, r, o) {
  if (o.tipo === 'texto' || o.tipo === 'hachura') return [];
  if (o.tipo === 'circulo' || o.tipo === 'arco') {
    const d = dist(c, o.centro);
    if (d < 1e-9 || d > r + o.raio || d < Math.abs(r - o.raio)) return [];
    const a = (r * r - o.raio * o.raio + d * d) / (2 * d), h = Math.sqrt(Math.max(0, r * r - a * a));
    const ux = (o.centro[0] - c[0]) / d, uy = (o.centro[1] - c[1]) / d, m = [c[0] + ux * a, c[1] + uy * a];
    const qs = [[m[0] - uy * h, m[1] + ux * h], [m[0] + uy * h, m[1] - ux * h]];
    return o.tipo === 'arco' ? qs.filter(q => noTrechoDoArco(o, q)) : qs;
  }
  const out = [];
  for (const [s, t] of segmentosDe(o)) out.push(...intersecaoLinhaCirculo(s, t, c, r));
  return out;
}

/** Os pontos onde o segmento a–b cruza a entidade `o`: no arco e no círculo, pela curva (os trechos de 10° do
 *  desenho do arco ficavam até 20 cm abaixo do banzo curvo, e o Aparar cortava ali — 06/10); no resto, pelos
 *  segmentos. */
function cortesComEntidade(a, b, o) {
  if (o.tipo === 'circulo') return intersecaoLinhaCirculo(a, b, o.centro, o.raio);
  if (o.tipo === 'arco') return intersecaoLinhaCirculo(a, b, o.centro, o.raio).filter(q => noTrechoDoArco(o, q));
  if (o.tipo === 'texto' || o.tipo === 'hachura') return [];
  const out = [];
  for (const [s, t] of segmentosDe(o)) { const x = intersecaoSeg(a, b, s, t); if (x) out.push(x); }
  return out;
}

/** o ponto `q` do círculo do arco está no trecho dele (de `inicio` a `fim`, anti-horário) */
function noTrechoDoArco(o, q) {
  const n = (x) => ((x % 360) + 360) % 360;
  const ang = n(Math.atan2(q[1] - o.centro[1], q[0] - o.centro[0]) * 180 / Math.PI), a0 = n(o.inicio), a1 = n(o.fim), tol = 1e-6;
  return a1 >= a0 ? ang >= a0 - tol && ang <= a1 + tol : ang >= a0 - tol || ang <= a1 + tol;
}

function intersecaoLinhaCirculo(a, b, c, r) {
  const d = [b[0] - a[0], b[1] - a[1]], f = [a[0] - c[0], a[1] - c[1]];
  const A = d[0] * d[0] + d[1] * d[1], B = 2 * (f[0] * d[0] + f[1] * d[1]), C = f[0] * f[0] + f[1] * f[1] - r * r;
  let disc = B * B - 4 * A * C;
  if (disc < 0) return [];
  disc = Math.sqrt(disc);
  return [(-B - disc) / (2 * A), (-B + disc) / (2 * A)].filter(t => t >= 0 && t <= 1).map(t => [a[0] + t * d[0], a[1] + t * d[1]]);
}

/** Interseção de duas retas (não segmentos), ou null se paralelas. */
function intersecaoRetas(a, b, c, d) {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  return [a[0] + t * r[0], a[1] + t * r[1]];
}

export class Estender extends Ferramenta {
  static id = 'estender'; static nome = 'Estender (extend)'; static atalho = 'n'; static grupo = 'edicao';
  static dica = 'Clique perto da ponta da linha a estender: ela vai até a primeira linha, arco ou círculo que encontrar';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4v16"/><path d="M20 12H8" stroke-dasharray="3 2"/><path d="M14 12h6M17 9l3 3-3 3"/></svg>';
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (e && (e.tipo === 'polilinha' || e.tipo === 'hachura')) {
      // chapa, contorno de peça: o lado clicado anda — é o Esticar (S), com a aresta já pega
      this.editor.ativarFerramenta('esticar');
      const f = this.editor.ferramenta;
      if (f && f._pegarAresta && f._pegarAresta(p, ev)) {
        this.editor.dica('Contorno (chapa): leve o lado até a nova posição, ou digite quanto estender · Esc cancela');
      }
      return;
    }
    if (e && e.tipo === 'arco') { this._estenderArco(e, p); return; }
    if (!e || e.tipo !== 'linha') { this.dica('Estender funciona em linhas e arcos: clique perto da ponta a estender'); return; }
    // a ponta mais perto do clique é a que anda; a direção é a da própria linha
    const inverte = dist(p, e.a) < dist(p, e.b);
    const fixo = inverte ? e.b : e.a, ponta = inverte ? e.a : e.b;
    const L = dist(fixo, ponta) || 1, d = [(ponta[0] - fixo[0]) / L, (ponta[1] - fixo[1]) / L];
    const longe = [ponta[0] + d[0] * 1e6, ponta[1] + d[1] * 1e6];
    let melhor = null;
    for (const o of this.doc.entidades.values()) {
      if (o.id === e.id || !this.doc.visivel(o) || o.tipo === 'texto' || o.tipo === 'hachura') continue;
      const cand = cortesComEntidade(ponta, longe, o);
      for (const x of cand) {
        const dx = dist(ponta, x);
        if (dx > 0.05 && (!melhor || dx < melhor.d)) melhor = { x, d: dx };
      }
    }
    if (!melhor) { this.dica('Nada nessa direção para a linha chegar'); return; }
    const nova = criar({ ...e, a: inverte ? melhor.x : e.a, b: inverte ? e.b : melhor.x });
    this.editor.executar(new ComandoSubstituir([nova], 'Estender'));
    this.dica(`Estendida ${medidaComUnidade(melhor.d)} · próxima linha (Esc sai)`);
  }
  /** A ponta do arco mais perto do clique segue pela mesma curva até a primeira linha, arco ou círculo. */
  _estenderArco(e, p) {
    const pt = (g) => [e.centro[0] + e.raio * Math.cos(g * Math.PI / 180), e.centro[1] + e.raio * Math.sin(g * Math.PI / 180)];
    const peloFim = dist(p, pt(e.fim)) <= dist(p, pt(e.inicio));
    const span = vaoDoArco(e), livre = 360 - span;
    const ang = (q) => (Math.atan2(q[1] - e.centro[1], q[0] - e.centro[0]) * 180 / Math.PI);
    let melhor = null;
    for (const o of this.doc.entidades.values()) {
      if (o.id === e.id || !this.doc.visivel(o)) continue;
      for (const q of cortesNoCirculo(e.centro, e.raio, o)) {
        // quanto a ponta anda (graus) até lá, no sentido de fora do arco
        const d = peloFim ? (((ang(q) - e.fim) % 360) + 360) % 360 : (((e.inicio - ang(q)) % 360) + 360) % 360;
        if (d > 1e-6 && d < livre - 1e-6 && (!melhor || d < melhor)) melhor = d;
      }
    }
    if (!melhor) { this.dica('Nada nessa direção para o arco chegar'); return; }
    const n = (g) => ((g % 360) + 360) % 360;
    const nova = criar(peloFim ? { ...e, fim: n(e.fim + melhor) } : { ...e, inicio: n(e.inicio - melhor) });
    this.editor.executar(new ComandoSubstituir([nova], 'Estender'));
    this.dica(`Arco estendido ${medidaComUnidade(e.raio * melhor * Math.PI / 180)} na curva · próxima (Esc sai)`);
  }
}

export class Concordar extends Ferramenta {
  static id = 'concordar'; static nome = 'Concordar (fillet)'; static atalho = 'k'; static grupo = 'edicao';
  static dica = 'Fillet: clique na primeira linha, depois na segunda · digite o raio antes (0 = canto vivo)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20V10a6 6 0 0 1 6-6h10"/></svg>';
  reiniciar() { super.reiniciar(); this.primeira = null; this.raio = this.raio || 0; this.dica(`Fillet R ${fmt(this.raio)}: clique na primeira linha (digite outro raio se quiser)`); }
  onValor(t) { const v = paraMilimetros(t); if (v != null && v >= 0) { this.raio = v; this.dica(`Raio ${fmt(v)}: clique na primeira linha`); } }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (!e || e.tipo !== 'linha') { this.dica('Concordar funciona entre duas linhas'); return; }
    // o lado que fica é o do MOUSE: o snap levava o clique para o próprio encontro e o lado caía na direção a→b
    p = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;
    if (!this.primeira) { this.primeira = { e, p }; this.dica('Agora a segunda linha'); return; }
    if (e.id === this.primeira.e.id) { this.dica('Clique numa segunda linha, diferente da primeira'); return; }
    const res = this._concordar(this.primeira.e, this.primeira.p, e, p, this.raio);
    if (!res) { this.dica('As linhas são paralelas ou o raio não cabe'); this.primeira = null; return; }
    const cmd = new ComandoComposto([new ComandoSubstituir(res.linhas, 'Concordar'),
      ...(res.arco ? [new ComandoAdicionar([res.arco])] : [])], 'Concordar');
    this.editor.executar(cmd);
    this.primeira = null;
    this.dica(`Feito · próxima concordância com R ${fmt(this.raio)} (Esc sai)`);
  }
  /**
   * As duas retas se cruzam em P. De cada linha fica o lado em que o usuário clicou; o
   * canto é aparado (ou estendido) até P com raio zero, ou até os pontos de tangência do
   * arco de raio R, que fica do lado dos cliques.
   */
  _concordar(e1, p1, e2, p2, R) {
    const P = intersecaoRetas(e1.a, e1.b, e2.a, e2.b);
    if (!P) return null;
    const lado = (e, pc) => {
      // direção unitária de P para o lado clicado, e a ponta que fica desse lado
      const q = maisProximoSeg(pc, e.a, e.b);
      let d = [q[0] - P[0], q[1] - P[1]], n = Math.hypot(d[0], d[1]);
      if (n < 1e-6) { d = [e.b[0] - e.a[0], e.b[1] - e.a[1]]; n = Math.hypot(d[0], d[1]); }
      d = [d[0] / n, d[1] / n];
      const ponta = ((e.a[0] - P[0]) * d[0] + (e.a[1] - P[1]) * d[1]) >= ((e.b[0] - P[0]) * d[0] + (e.b[1] - P[1]) * d[1]) ? e.a : e.b;
      return { d, ponta };
    };
    const l1 = lado(e1, p1), l2 = lado(e2, p2);
    if (R <= 1e-6) {
      return { linhas: [criar({ ...e1, a: P, b: l1.ponta }), criar({ ...e2, a: P, b: l2.ponta })], arco: null };
    }
    const cosT = l1.d[0] * l2.d[0] + l1.d[1] * l2.d[1];
    const theta = Math.acos(Math.max(-1, Math.min(1, cosT)));          // ângulo entre os lados
    if (theta < 1e-3 || Math.PI - theta < 1e-3) return null;
    const t = R / Math.tan(theta / 2);                                  // P → ponto de tangência
    const T1 = [P[0] + l1.d[0] * t, P[1] + l1.d[1] * t], T2 = [P[0] + l2.d[0] * t, P[1] + l2.d[1] * t];
    // o arco tem de caber: a ponta guardada precisa passar do ponto de tangência
    for (const [l, T] of [[l1, T1], [l2, T2]]) if (dist(P, l.ponta) < t - 1e-6) return null;
    let bx = l1.d[0] + l2.d[0], by = l1.d[1] + l2.d[1];
    const nb = Math.hypot(bx, by); bx /= nb; by /= nb;
    const C = [P[0] + bx * R / Math.sin(theta / 2), P[1] + by * R / Math.sin(theta / 2)];
    const g = (q) => ((Math.atan2(q[1] - C[1], q[0] - C[0]) * 180 / Math.PI) + 360) % 360;
    // o arco vai de T1 a T2 pelo lado de P (o lado côncavo): escolhe o sentido que contém P
    const am = g(P);
    let a0 = g(T1), a1 = g(T2);
    const dentro = (x, i, f) => (f >= i ? x >= i && x <= f : x >= i || x <= f);
    if (!dentro(am, a0, a1)) [a0, a1] = [a1, a0];
    const arco = criar({ tipo: 'arco', camada: e1.camada, centro: C, raio: R, inicio: a0, fim: a1 });
    return { linhas: [criar({ ...e1, a: T1, b: l1.ponta }), criar({ ...e2, a: T2, b: l2.ponta })], arco };
  }
}

/** O lado de uma linha que fica num canto em P: a direção de P para o lado clicado e a ponta desse lado (do Concordar). */
function ladoDoCanto(e, pc, P) {
  const q = maisProximoSeg(pc, e.a, e.b);
  let d = [q[0] - P[0], q[1] - P[1]], n = Math.hypot(d[0], d[1]);
  if (n < 1e-6) { d = [e.b[0] - e.a[0], e.b[1] - e.a[1]]; n = Math.hypot(d[0], d[1]); }
  d = [d[0] / n, d[1] / n];
  const ponta = ((e.a[0] - P[0]) * d[0] + (e.a[1] - P[1]) * d[1]) >= ((e.b[0] - P[0]) * d[0] + (e.b[1] - P[1]) * d[1]) ? e.a : e.b;
  return { d, ponta };
}

/** O canto da polilinha no vértice `i` trocado pelo chanfro (d1 no trecho de antes, d2 no de depois), ou null quando um
 *  dos trechos é curto demais. Devolve os dois pontos novos. */
function chanfroNoVertice(vs, i, fechada, d1, d2) {
  const n = vs.length;
  const ant = i > 0 ? vs[i - 1] : (fechada ? vs[n - 1] : null), dep = i < n - 1 ? vs[i + 1] : (fechada ? vs[0] : null);
  if (!ant || !dep) return null;
  const V = vs[i], L1 = dist(V, ant), L2 = dist(V, dep);
  if (L1 < 1e-9 || L2 < 1e-9 || d1 > L1 + 1e-6 || d2 > L2 + 1e-6) return null;
  const u1 = [(ant[0] - V[0]) / L1, (ant[1] - V[1]) / L1], u2 = [(dep[0] - V[0]) / L2, (dep[1] - V[1]) / L2];
  if (Math.abs(u1[0] * u2[1] - u1[1] * u2[0]) < 1e-6) return null;               // trechos alinhados: não há canto
  return [[V[0] + u1[0] * d1, V[1] + u1[1] * d1], [V[0] + u2[0] * d2, V[1] + u2[1] * d2]];
}

/**
 * Chanfro (o CHAMFER do AutoCAD; pedido do usuário, 23/10, na rodada das ferramentas que faltam): o recorte de canto de
 * enrijecedor e de chapa de ligação (a passagem de solda 20 × 20) e o chanfro de solda. Entre duas linhas — de cada uma
 * fica o lado clicado e o canto vira a linha do chanfro — ou no canto de uma polilinha (o vértice mais perto do clique);
 * com P, todos os cantos da polilinha clicada. Distâncias: "20" (as duas iguais) ou "20;30" (a primeira e a segunda).
 */
export class Chanfro extends Ferramenta {
  static id = 'chanfro'; static nome = 'Chanfro (chamfer)'; static atalho = 'ch'; static grupo = 'edicao';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20V11l7-7h9"/></svg>';
  reiniciar() {
    super.reiniciar(); this.primeira = null;
    if (this.d1 == null) { this.d1 = 20; this.d2 = 20; }
    this.dica(`Chanfro ${fmt(this.d1)} × ${fmt(this.d2)}${this.todos ? ' em todos os cantos' : ''}: clique na primeira linha ou no canto da polilinha · digite "20" ou "20;30" · P: todos os cantos da polilinha (${this.todos ? 'ligado' : 'desligado'})`);
  }
  onValor(t) {
    const m = String(t || '').split(';');
    const a = paraMilimetros(m[0]), b = m.length > 1 ? paraMilimetros(m[1]) : a;
    if (a == null || b == null || a < 0 || b < 0) return;
    this.d1 = a; this.d2 = b; this.primeira = null; this.reiniciar();
  }
  onTecla(ev) {
    if (ev.key.toLowerCase() === 'p' && !ev.ctrlKey && !ev.altKey && !ev.metaKey) { this.todos = !this.todos; this.reiniciar(); return true; }
    return false;
  }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    p = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;        // o lado que fica é o do mouse, não o do snap
    if (!e || (e.tipo !== 'linha' && e.tipo !== 'polilinha')) { this.dica('O chanfro vai entre duas linhas ou no canto de uma polilinha'); return; }
    if (this.doc.bloqueada(e)) { this.dica(`A camada ${e.camada} está travada`); return; }
    if (e.tipo === 'polilinha' && !this.primeira) { this._naPolilinha(e, p); return; }
    if (e.tipo !== 'linha') { this.dica('A segunda também tem de ser uma linha'); return; }
    if (!this.primeira) { this.primeira = { e, p }; this.dica('Agora a segunda linha'); return; }
    if (e.id === this.primeira.e.id) { this.dica('Clique numa segunda linha, diferente da primeira'); return; }
    const res = this._entreLinhas(this.primeira.e, this.primeira.p, e, p);
    this.primeira = null;
    if (!res) { this.dica('As linhas são paralelas ou o chanfro não cabe nelas'); return; }
    this.editor.executar(new ComandoComposto([new ComandoSubstituir(res.linhas, 'Chanfro'), ...(res.nova ? [new ComandoAdicionar([res.nova])] : [])], 'Chanfro'));
    this.dica(`Feito · próximo chanfro ${fmt(this.d1)} × ${fmt(this.d2)} (Esc sai)`);
  }
  _entreLinhas(e1, p1, e2, p2) {
    const P = intersecaoRetas(e1.a, e1.b, e2.a, e2.b);
    if (!P) return null;
    const l1 = ladoDoCanto(e1, p1, P), l2 = ladoDoCanto(e2, p2, P);
    if (Math.abs(l1.d[0] * l2.d[1] - l1.d[1] * l2.d[0]) < 1e-6) return null;
    if (this.d1 <= 1e-9 && this.d2 <= 1e-9) return { linhas: [criar({ ...e1, a: P, b: l1.ponta }), criar({ ...e2, a: P, b: l2.ponta })], nova: null };
    const T1 = [P[0] + l1.d[0] * this.d1, P[1] + l1.d[1] * this.d1], T2 = [P[0] + l2.d[0] * this.d2, P[1] + l2.d[1] * this.d2];
    if (dist(P, l1.ponta) < this.d1 - 1e-6 || dist(P, l2.ponta) < this.d2 - 1e-6) return null;
    return { linhas: [criar({ ...e1, a: T1, b: l1.ponta }), criar({ ...e2, a: T2, b: l2.ponta })],
             nova: criar({ tipo: 'linha', camada: e1.camada, a: T1, b: T2, ...(e1.tipo_linha ? { tipo_linha: e1.tipo_linha } : {}), ...(e1.espessura != null ? { espessura: e1.espessura } : {}) }) };
  }
  _naPolilinha(e, p) {
    const vs = e.vertices, n = vs.length;
    let quais;
    if (this.todos) quais = vs.map((_, i) => i);
    else {
      let m = -1, dm = Infinity;
      vs.forEach((v, i) => { const d = dist(v, p); if (d < dm && (e.fechada || (i > 0 && i < n - 1))) { dm = d; m = i; } });
      quais = m >= 0 ? [m] : [];
    }
    const novos = [];
    let feitos = 0;
    vs.forEach((v, i) => {
      const c = quais.includes(i) ? chanfroNoVertice(vs, i, e.fechada, this.d1, this.d2) : null;
      if (c) { novos.push(...c); feitos++; } else novos.push(v);
    });
    if (!feitos) { this.dica('Nenhum canto da polilinha comporta esse chanfro'); return; }
    this.editor.executar(new ComandoSubstituir([criar({ ...e, vertices: novos })], feitos > 1 ? `Chanfro em ${feitos} cantos` : 'Chanfro'));
    this.dica(`${feitos} canto(s) chanfrado(s) ${fmt(this.d1)} × ${fmt(this.d2)} · Esc sai`);
  }
}

/** Ponto de `e` mais perto de `p` e o parâmetro dele (linha: 0–1 de a a b; polilinha: o comprimento desde o 1º vértice;
 *  arco/círculo: o ângulo em graus). */
function ondeNa(e, p) {
  if (e.tipo === 'linha') {
    const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], l2 = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p[0] - e.a[0]) * dx + (p[1] - e.a[1]) * dy) / l2));
    return { t, q: [e.a[0] + dx * t, e.a[1] + dy * t] };
  }
  if (e.tipo === 'polilinha') {
    const vs = e.fechada ? [...e.vertices, e.vertices[0]] : e.vertices;
    let s = 0, melhor = null;
    for (let i = 1; i < vs.length; i++) {
      const a = vs[i - 1], b = vs[i], L = dist(a, b);
      const q = maisProximoSeg(p, a, b), d = dist(q, p);
      if (!melhor || d < melhor.d) melhor = { d, q, t: s + dist(a, q) };
      s += L;
    }
    return melhor ? { t: melhor.t, q: melhor.q } : null;
  }
  if (e.tipo === 'arco' || e.tipo === 'circulo') {
    const g = ((Math.atan2(p[1] - e.centro[1], p[0] - e.centro[0]) * 180 / Math.PI) + 360) % 360;
    return { t: g, q: [e.centro[0] + e.raio * Math.cos(g * Math.PI / 180), e.centro[1] + e.raio * Math.sin(g * Math.PI / 180)] };
  }
  return null;
}

/** O trecho da polilinha (aberta) entre os comprimentos s0 e s1, desde o 1º vértice. */
function trechoDaPolilinha(vs, s0, s1) {
  const out = [];
  let s = 0;
  const em = (a, b, L, x) => [a[0] + (b[0] - a[0]) * (x - s) / L, a[1] + (b[1] - a[1]) * (x - s) / L];
  for (let i = 1; i < vs.length; i++) {
    const a = vs[i - 1], b = vs[i], L = dist(a, b);
    if (L < 1e-12) continue;
    if (s + L >= s0 && s <= s1) {
      if (!out.length) out.push(s0 > s ? em(a, b, L, s0) : a);
      if (s + L <= s1) out.push(b); else { out.push(em(a, b, L, s1)); break; }
    }
    s += L;
  }
  return out;
}

/**
 * Quebrar (o BREAK do AutoCAD; atalho Q B): clique no objeto (o primeiro ponto da quebra) e depois no segundo ponto —
 * o trecho entre eles sai; Enter depois do primeiro quebra ali (em duas). Linha, polilinha, arco e círculo (no
 * círculo sai o trecho anti-horário do primeiro ao segundo ponto, e ele vira um arco).
 */
export class Quebrar extends Ferramenta {
  static id = 'quebrar'; static nome = 'Quebrar (break)'; static atalho = 'qb'; static grupo = 'edicao';
  static dica = 'Clique no objeto no primeiro ponto da quebra · depois o segundo ponto (Enter: quebra só no primeiro)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 12h7M14 12h7"/><path d="M10 9l2 6M12 9l2 6"/></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; this.p1 = null; }
  onPonto(p, ev) {
    if (!this.alvo) {
      const e = this.editor.tela.sob(ev.px);
      if (!e || !['linha', 'polilinha', 'arco', 'circulo'].includes(e.tipo)) { this.dica('Clique numa linha, polilinha, arco ou círculo'); return; }
      if (this.doc.bloqueada(e)) { this.dica(`A camada ${e.camada} está travada`); return; }
      this.alvo = e; this.p1 = ondeNa(e, p);
      this.editor.snap.ultimo = this.p1.q;
      this.dica('Segundo ponto da quebra (Enter: quebra só neste ponto) · Esc cancela');
      return;
    }
    this._quebrar(ondeNa(this.alvo, p));
  }
  onTecla(ev) { if (ev.key === 'Enter' && this.alvo) { this._quebrar(this.p1); return true; } return false; }
  _quebrar(p2) {
    const e = this.alvo, p1 = this.p1;
    this.reiniciar();
    if (!p2) return;
    const so = Math.abs(p2.t - p1.t) < 1e-9;                           // a quebra num ponto só
    let novas = [];
    if (e.tipo === 'linha') {
      const [t0, t1] = [Math.min(p1.t, p2.t), Math.max(p1.t, p2.t)];
      const P = (t) => [e.a[0] + (e.b[0] - e.a[0]) * t, e.a[1] + (e.b[1] - e.a[1]) * t];
      if (t0 > 1e-9) novas.push(criar({ ...e, id: undefined, a: e.a, b: P(t0) }));
      if (t1 < 1 - 1e-9) novas.push(criar({ ...e, id: undefined, a: P(t1), b: e.b }));
    } else if (e.tipo === 'polilinha') {
      const vs = e.vertices;
      const anel = e.fechada ? [...vs, vs[0]] : vs;
      const L = anel.reduce((s, v, i) => s + (i ? dist(anel[i - 1], v) : 0), 0);
      if (e.fechada) {
        // a fechada vira uma aberta: do segundo ponto, dando a volta, até o primeiro (sai o trecho entre eles); quebrada
        // num ponto só, abre ali e fica inteira
        const [ini, fim] = so ? [p1.t, p1.t + L] : p2.t >= p1.t ? [p2.t, p1.t + L] : [p2.t, p1.t];
        const dobro = [...anel, ...vs.slice(1), vs[0]];
        const pts = trechoDaPolilinha(dobro, ini, fim);
        if (pts.length >= 2) novas.push(criar({ ...e, id: undefined, vertices: pts, fechada: false }));
      } else {
        const [s0, s1] = [Math.min(p1.t, p2.t), Math.max(p1.t, p2.t)];
        const a = trechoDaPolilinha(anel, 0, s0), b = trechoDaPolilinha(anel, s1, Infinity);
        if (a.length >= 2 && s0 > 1e-9) novas.push(criar({ ...e, id: undefined, vertices: a, fechada: false }));
        if (b.length >= 2 && s1 < L - 1e-9) novas.push(criar({ ...e, id: undefined, vertices: b, fechada: false }));
      }
    } else if (e.tipo === 'arco') {
      const n = (g) => ((g % 360) + 360) % 360;
      const rel = (g) => n(g - e.inicio), varre = n(e.fim - e.inicio) || 360;
      const [r0, r1] = [Math.min(rel(p1.t), rel(p2.t)), Math.max(rel(p1.t), rel(p2.t))].map(x => Math.min(x, varre));
      if (r0 > 1e-6) novas.push(criar({ ...e, id: undefined, inicio: e.inicio, fim: n(e.inicio + r0) }));
      if (varre - r1 > 1e-6) novas.push(criar({ ...e, id: undefined, inicio: n(e.inicio + r1), fim: e.fim }));
    } else if (e.tipo === 'circulo') {
      if (so) { this.dica('O círculo precisa de dois pontos para quebrar (vira um arco)'); return; }
      // sai o trecho anti-horário do primeiro ao segundo ponto: fica o arco do segundo ao primeiro
      novas.push(criar({ tipo: 'arco', camada: e.camada, atributos: e.atributos, centro: e.centro, raio: e.raio, inicio: p2.t, fim: p1.t,
        ...(e.tipo_linha ? { tipo_linha: e.tipo_linha } : {}), ...(e.espessura != null ? { espessura: e.espessura } : {}) }));
    }
    novas = novas.filter(Boolean);
    this.editor.executar(new ComandoComposto([new ComandoRemover([e.id]), ...(novas.length ? [new ComandoAdicionar(novas)] : [])], 'Quebrar'));
    this.dica(`Quebrado em ${novas.length} parte(s) · clique em outro objeto ou Esc`);
  }
}

/**
 * Alongar (o LENGTHEN do AutoCAD; atalho A L): digite quanto ("500" alonga, "-200" encurta) ou o comprimento total
 * ("t3000") e clique perto da ponta que anda. Linha, arco (pelo comprimento do arco) e polilinha aberta (o trecho da
 * ponta clicada).
 */
export class Alongar extends Ferramenta {
  static id = 'alongar'; static nome = 'Alongar (lengthen)'; static atalho = 'al'; static grupo = 'edicao';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 12h12"/><path d="M15 12h6" stroke-dasharray="2 2"/><path d="M18 9l3 3-3 3"/></svg>';
  reiniciar() {
    super.reiniciar();
    if (this.delta == null && this.total == null) this.delta = 100;
    this.dica(`${this.total != null ? `Comprimento total ${fmt(this.total)}` : `Alongar ${this.delta >= 0 ? '+' : ''}${fmt(this.delta)}`}: clique perto da ponta que anda · digite quanto alonga ("500", "-200") · T: o comprimento total`);
  }
  onValor(t) {
    const s = String(t || '').trim().toLowerCase();
    const total = s.startsWith('t') || (this.modoTotal && !s.startsWith('d'));
    const v = paraMilimetros(s.replace(/^[td]/, ''));
    if (v != null && total && v > 0) { this.total = v; this.delta = null; }
    else if (v != null && !total) { this.delta = v; this.total = null; }
    this.modoTotal = false;
    this.reiniciar();
  }
  /** T: o próximo número é o comprimento total; D: o quanto alonga — como as opções do LENGTHEN (a letra digitada não
   *  vai para a caixa MEDIDAS, que só aceita números: o "t" abriria o Texto). */
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey || ev.altKey || ev.metaKey || (k !== 't' && k !== 'd')) return false;
    this.modoTotal = k === 't';
    this.dica(this.modoTotal ? 'Digite o comprimento total e Enter · depois clique perto da ponta que anda' : 'Digite quanto alonga ("500", ou "-200" para encurtar) e Enter');
    return true;
  }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    p = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;
    if (!e || !['linha', 'arco', 'polilinha'].includes(e.tipo) || (e.tipo === 'polilinha' && (e.fechada || e.vertices.length < 2))) {
      this.dica('Clique perto da ponta de uma linha, arco ou polilinha aberta'); return;
    }
    if (this.doc.bloqueada(e)) { this.dica(`A camada ${e.camada} está travada`); return; }
    const nova = this._alongada(e, p);
    if (!nova) { this.dica('Assim o objeto ficaria sem comprimento'); return; }
    this.editor.executar(new ComandoSubstituir([nova], 'Alongar'));
    this.reiniciar();
  }
  _alongada(e, p) {
    if (e.tipo === 'linha') {
      const L = dist(e.a, e.b), novoL = this.total != null ? this.total : L + this.delta;
      if (!(novoL > 1e-6) || L < 1e-9) return null;
      const daB = dist(p, e.b) < dist(p, e.a);
      const fixo = daB ? e.a : e.b, anda = daB ? e.b : e.a;
      const u = [(anda[0] - fixo[0]) / L, (anda[1] - fixo[1]) / L];
      const q = [fixo[0] + u[0] * novoL, fixo[1] + u[1] * novoL];
      return criar(daB ? { ...e, b: q } : { ...e, a: q });
    }
    if (e.tipo === 'arco') {
      const n = (g) => ((g % 360) + 360) % 360, varre = n(e.fim - e.inicio) || 360;
      const L = e.raio * varre * Math.PI / 180, novoL = this.total != null ? this.total : L + this.delta;
      const novoVarre = novoL / e.raio * 180 / Math.PI;
      if (!(novoVarre > 1e-6) || novoVarre >= 360) return null;
      const pt = (g) => [e.centro[0] + e.raio * Math.cos(g * Math.PI / 180), e.centro[1] + e.raio * Math.sin(g * Math.PI / 180)];
      const noFim = dist(p, pt(e.fim)) < dist(p, pt(e.inicio));
      return criar(noFim ? { ...e, fim: n(e.inicio + novoVarre) } : { ...e, inicio: n(e.fim - novoVarre) });
    }
    const vs = e.vertices.map(v => [v[0], v[1]]), k = vs.length;
    const noFim = dist(p, vs[k - 1]) < dist(p, vs[0]);
    const [anda, fixo] = noFim ? [k - 1, k - 2] : [0, 1];
    const Lt = vs.reduce((s, v, i) => s + (i ? dist(vs[i - 1], v) : 0), 0);
    const delta = this.total != null ? this.total - Lt : this.delta;
    const Ls = dist(vs[fixo], vs[anda]), novoLs = Ls + delta;
    if (!(novoLs > 1e-6) || Ls < 1e-9) return null;
    const u = [(vs[anda][0] - vs[fixo][0]) / Ls, (vs[anda][1] - vs[fixo][1]) / Ls];
    vs[anda] = [vs[fixo][0] + u[0] * novoLs, vs[fixo][1] + u[1] * novoLs];
    return criar({ ...e, vertices: vs });
  }
}

/** Zoom janela (Z W no AutoCAD): dois cantos (ou um arrasto) e a vista vai para eles; volta à ferramenta de antes. */
export class ZoomJanela extends Ferramenta {
  static id = 'zoom_janela'; static nome = 'Zoom janela'; static atalho = 'zw'; static grupo = 'navegacao';
  static dica = 'Zoom janela: o primeiro canto (ou arraste a janela) · Esc cancela';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="6"/><path d="M14.5 14.5L20 20"/><path d="M7.5 10h5M10 7.5v5"/></svg>';
  reiniciar() { super.reiniciar(); this.c1 = null; }
  _ir(a, b) {
    this.editor.previa([]);
    if (Math.abs(b[0] - a[0]) > 1e-9 && Math.abs(b[1] - a[1]) > 1e-9) this.editor.tela.enquadrar([[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])]], 0);
    this.editor.ativarFerramenta('selecionar');
    this.editor.dica('Zoom janela feito · Z P volta à vista de antes');
  }
  onPonto(p, ev) {
    const m = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p;
    if (!this.c1) { this.c1 = m; this.dica('O outro canto'); return; }
    this._ir(this.c1, m);
  }
  onSoltar(p, ev) { if (ev && ev.arrasto) this._ir(this.editor.tela.paraMundo(ev.arrasto.de), this.editor.tela.paraMundo(ev.arrasto.para)); }
  onMover(p, ev) {
    if (!this.c1) return;
    const m = ev && ev.px ? this.editor.tela.paraMundo(ev.px) : p, a = this.c1;
    this.editor.previa([criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true, vertices: [a, [m[0], a[1]], m, [a[0], m[1]]] })]);
  }
}

/** Copiar com ponto de base (Ctrl+Shift+C, o COPYBASE do AutoCAD): clique o ponto de base e a seleção vai para a área
 *  de transferência do programa (o Ctrl+V cola presa ao cursor por esse ponto, neste ou em outro desenho). */
export class CopiarBase extends Ferramenta {
  static id = 'copiar_base'; static nome = 'Copiar com ponto de base'; static grupo = 'oculta';
  static dica = 'Clique o ponto de base da cópia · Esc cancela';
  onPonto(p) { this.editor.copiarSelecao(p); this.editor.ativarFerramenta('selecionar'); }
}

/** O ponto e a direção (graus) a `s` do começo de uma linha, polilinha ou arco; e o comprimento dela. */
function caminhoDe(e) {
  if (e.tipo === 'linha') {
    const L = dist(e.a, e.b), g = Math.atan2(e.b[1] - e.a[1], e.b[0] - e.a[0]) * 180 / Math.PI;
    return { L, em: (s) => ({ p: [e.a[0] + (e.b[0] - e.a[0]) * s / L, e.a[1] + (e.b[1] - e.a[1]) * s / L], g }) };
  }
  if (e.tipo === 'arco') {
    const n = (a) => ((a % 360) + 360) % 360, varre = n(e.fim - e.inicio) || 360, L = e.raio * varre * Math.PI / 180;
    return { L, em: (s) => { const a = e.inicio + s / L * varre; return { p: [e.centro[0] + e.raio * Math.cos(a * Math.PI / 180), e.centro[1] + e.raio * Math.sin(a * Math.PI / 180)], g: a + 90 }; } };
  }
  const vs = e.fechada ? [...e.vertices, e.vertices[0]] : e.vertices;
  const trechos = [];
  let L = 0;
  for (let i = 1; i < vs.length; i++) { const l = dist(vs[i - 1], vs[i]); if (l > 1e-9) { trechos.push([vs[i - 1], vs[i], L, l]); L += l; } }
  return { L, em: (s) => {
    const t = trechos.find(([, , s0, l]) => s <= s0 + l + 1e-9) || trechos[trechos.length - 1];
    const [a, b, s0, l] = t, u = Math.max(0, Math.min(1, (s - s0) / l));
    return { p: [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u], g: Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI };
  } };
}

/**
 * Matriz (A R, o ARRAY do AutoCAD; pedido do usuário, 23/10, na lista das ferramentas que faltam: "furação de chapa e
 * barra, montantes, chumbadores"). Com a seleção:
 *  - retangular (o padrão): "4x3" (colunas × linhas) e o cursor dá o espaçamento, do canto da seleção até ele — ou "500;300";
 *  - polar (P): clique o centro; "6" cópias em volta (360°) ou "6;180" (o ângulo total); R gira (ou não) as cópias;
 *  - por caminho (C): clique a linha, polilinha ou arco; "8" cópias de ponta a ponta ou "@500" de passo; A alinha ao caminho.
 * O original fica; Enter ou o clique grava; cada cópia é uma peça (como as do Copiar).
 */
export class Matriz extends Transformadora {
  static id = 'matriz'; static nome = 'Matriz (array)'; static atalho = 'ar';
  static dica = 'Matriz retangular: digite colunas x linhas (ex.: 4x3) e leve o cursor ao lugar da segunda cópia · P polar · C caminho';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="5" height="5"/><rect x="10" y="3" width="5" height="5" stroke-dasharray="2 1"/><rect x="17" y="3" width="4" height="5" stroke-dasharray="2 1"/><rect x="3" y="10" width="5" height="5" stroke-dasharray="2 1"/><rect x="10" y="10" width="5" height="5" stroke-dasharray="2 1"/><circle cx="12" cy="19" r="2"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.modo = this.modo || 'retangular';
    if (!this.nx) { this.nx = 3; this.ny = 1; this.n = 6; this.angTotal = 360; this.girar = true; this.alinhar = true; }
    this.centro = null; this.caminho = null; this.passoFixo = null; this.esp = null;
    if (this.ids.length) this._dicaDoModo();
  }
  _caixa() { return this.doc.caixa(new Set(this.ids)); }
  _dicaDoModo() {
    const d = {
      retangular: `Matriz retangular ${this.nx} × ${this.ny}: leve o cursor ao lugar da segunda cópia e clique (ou "dx;dy" e Enter) · digite "4x3" para mudar · P polar · C caminho`,
      polar: this.centro ? `Matriz polar: ${this.n} em ${fmt(this.angTotal)}° (digite "6" ou "6;180") · R ${this.girar ? 'gira' : 'não gira'} as cópias · Enter ou clique grava` : 'Matriz polar: clique o centro',
      caminho: this.caminho ? `Matriz por caminho: ${this.passoFixo ? `passo ${fmt(this.passoFixo)}` : `${this.n} cópias de ponta a ponta`} (digite "8" ou "@500") · A ${this.alinhar ? 'alinha' : 'não alinha'} ao caminho · Enter ou clique grava` : 'Matriz por caminho: clique na linha, polilinha ou arco',
    }[this.modo];
    this.dica(d);
  }
  /** As cópias (sem o original): [entidades transformadas] por posição. */
  _posicoes(cursor) {
    const ents = this.selecionadas();
    if (!ents.length) return [];
    const cx = this._caixa();
    const out = [];
    if (this.modo === 'retangular') {
      const base = cx ? cx[0] : [0, 0];
      let dx, dy;
      if (this.esp) [dx, dy] = this.esp;
      else if (cursor) { dx = this.nx > 1 ? cursor[0] - base[0] : 0; dy = this.ny > 1 ? cursor[1] - base[1] : 0; if (this.nx > 1 && this.ny === 1) dy = 0; if (this.ny > 1 && this.nx === 1) dx = 0; }
      else return [];
      for (let j = 0; j < this.ny; j++) for (let i = 0; i < this.nx; i++) if (i || j) out.push(ents.map(e => transladar(e, [i * dx, j * dy])));
      return out;
    }
    if (this.modo === 'polar') {
      if (!this.centro) return [];
      const c = this.centro, total = this.angTotal, n = Math.max(2, this.n);
      const passo = Math.abs(total - 360) < 1e-9 ? 360 / n : total / (n - 1);
      for (let i = 1; i < n; i++) {
        const th = passo * i * Math.PI / 180, co = Math.cos(th), si = Math.sin(th);
        const rot = (p) => [c[0] + (p[0] - c[0]) * co - (p[1] - c[1]) * si, c[1] + (p[0] - c[0]) * si + (p[1] - c[1]) * co];
        if (this.girar) out.push(ents.map(e => transformar(e, rot, (a) => a + passo * i)));
        else {
          // sem girar: cada cópia só anda, o centro da seleção vai para o lugar girado
          const m = cx ? [(cx[0][0] + cx[1][0]) / 2, (cx[0][1] + cx[1][1]) / 2] : c, q = rot(m);
          out.push(ents.map(e => transladar(e, [q[0] - m[0], q[1] - m[1]])));
        }
      }
      return out;
    }
    if (!this.caminho) return [];
    const cam = caminhoDe(this.caminho);
    if (!(cam.L > 1e-9)) return [];
    const m = cx ? [(cx[0][0] + cx[1][0]) / 2, (cx[0][1] + cx[1][1]) / 2] : [0, 0];
    const g0 = cam.em(0).g;
    const ss = [];
    if (this.passoFixo) for (let s = 0; s <= cam.L + 1e-6 && ss.length < 2000; s += this.passoFixo) ss.push(s);
    else { const n = Math.max(2, this.n); for (let i = 0; i < n; i++) ss.push(cam.L * i / (n - 1)); }
    for (const s of ss) {
      const { p, g } = cam.em(s);
      const th = (this.alinhar ? g - g0 : 0) * Math.PI / 180, co = Math.cos(th), si = Math.sin(th);
      const f = (q) => [p[0] + (q[0] - m[0]) * co - (q[1] - m[1]) * si, p[1] + (q[0] - m[0]) * si + (q[1] - m[1]) * co];
      out.push(ents.map(e => transformar(e, f, (a) => a + (this.alinhar ? g - g0 : 0))));
    }
    return out;
  }
  _previa(cursor) {
    const pos = this._posicoes(cursor);
    const n = pos.reduce((s, x) => s + x.length, 0);
    // muitas: a prévia leva só as caixas de cada cópia
    this.editor.previa(n <= 3000 ? pos.flat() : pos.slice(0, 400).map(x => { const c = caixaDe(x.flatMap(pontosDe)); return c ? criar({ tipo: 'polilinha', camada: 'AUXILIAR', fechada: true, vertices: [c[0], [c[1][0], c[0][1]], c[1], [c[0][0], c[1][1]]] }) : null; }).filter(Boolean));
    this.editor.medida(`${pos.length} cópia(s)`);
  }
  _gravar(cursor) {
    const pos = this._posicoes(cursor);
    if (!pos.length) return;
    const total = pos.reduce((s, x) => s + x.length, 0);
    if (total > 20000) { this.dica(`São ${numeroBr(total)} objetos: diminua a matriz`); return; }
    const originais = this.selecionadas();
    const copias = [];
    let trocas = [];
    for (const novas of pos) { const c = criarCopias(this.editor, novas, novoGrupoCopia(), originais); copias.push(...c); if (c.trocas) trocas = trocas.concat(c.trocas); }
    copias.trocas = trocas;
    this.editor.previa([]);
    this.editor.executar(comandoDasCopias(copias, `Matriz (${pos.length} cópias)`));
    this.editor.ativarFerramenta('selecionar');
    this.editor.dica(`Matriz ${this.modo}: ${pos.length} cópia(s) · Ctrl+Z desfaz`);
  }
  onMover(p) { if (this.ids.length && !(this.modo === 'caminho' && !this.caminho)) this._previa(p); }
  passo(p, ev) {
    if (this.modo === 'polar' && !this.centro) { this.centro = [p[0], p[1]]; this._dicaDoModo(); this._previa(p); return; }
    if (this.modo === 'caminho' && !this.caminho) {
      const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
      if (!e || !['linha', 'polilinha', 'arco'].includes(e.tipo)) { this.dica('Clique na linha, polilinha ou arco do caminho'); return; }
      this.caminho = e; this._dicaDoModo(); this._previa(p); return;
    }
    this._gravar(p);
  }
  onValor(t) {
    const s = String(t || '').trim().toLowerCase().replace(/\s+/g, '');
    const m = s.match(/^(\d+)[x×*](\d+)$/);
    if (m && this.modo === 'retangular') { this.nx = Math.max(1, +m[1]); this.ny = Math.max(1, +m[2]); this.esp = null; this._dicaDoModo(); return; }
    if (this.modo === 'retangular') {
      const pr = s.split(';');
      if (pr.length === 2) { const a = paraMilimetros(pr[0]), b = paraMilimetros(pr[1]); if (a != null && b != null) { this.esp = [a, b]; this._gravar(null); } return; }
      const n = parseInt(s, 10); if (n > 0 && String(n) === s) { this.nx = n; this.ny = 1; this.esp = null; this._dicaDoModo(); }
      return;
    }
    if (this.modo === 'caminho' && s.startsWith('@')) { const v = paraMilimetros(s.slice(1)); if (v > 0) this.passoFixo = v; this._dicaDoModo(); this._previa(this.editor.tela.cursor); return; }
    const pr = s.split(';'), n = parseInt(pr[0], 10);
    if (n >= 2) { this.n = n; this.passoFixo = null; }
    if (pr.length > 1) { const a = parseFloat(pr[1].replace(',', '.')); if (a > 0 && a <= 360) this.angTotal = a; }
    this._dicaDoModo(); this._previa(this.editor.tela.cursor);
  }
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    if (ev.key === 'Enter') { if (this.modo !== 'retangular' || this.esp) this._gravar(this.editor.tela.cursor); else this._gravar(this.editor.tela.cursor); return true; }
    const modo = { r: this.modo === 'polar' ? null : 'retangular', p: 'polar', c: 'caminho' }[k];
    if (k === 'r' && this.modo === 'polar' && this.centro) { this.girar = !this.girar; this._dicaDoModo(); this._previa(this.editor.tela.cursor); return true; }
    if (k === 'a' && this.modo === 'caminho') { this.alinhar = !this.alinhar; this._dicaDoModo(); this._previa(this.editor.tela.cursor); return true; }
    if (modo) { this.modo = modo; this.centro = null; this.caminho = null; this.esp = null; this.editor.previa([]); this._dicaDoModo(); return true; }
    return false;
  }
}
const numeroBr = (n) => Number(n).toLocaleString('pt-BR');

/** O diâmetro do furo pelo que se digita: "22" (o furo), "M16" (o parafuso métrico + 1,5 mm de folga — a regra dos furos
 *  sem cota) ou "5/8" (polegada + 1,5). */
function diametroDoFuro(t) {
  const s = String(t || '').trim().toLowerCase().replace(',', '.').replace(/["”]/g, '');
  let m = s.match(/^m(\d+(?:\.\d+)?)$/);
  if (m) return +m[1] + 1.5;
  m = s.match(/^(\d+)\/(\d+)$/);
  if (m && +m[2]) return Math.round((+m[1] / +m[2]) * 25.4 * 1000) / 1000 + 1.5;
  m = s.match(/^(?:d|ø)?(\d+(?:\.\d+)?)$/);
  return m ? +m[1] : null;
}

/**
 * Grade de furos (G F; pedido do usuário, 23/10: "hoje cada furo é um clique"): linhas × colunas de furos na camada
 * FURO, com os passos. Digite o Ø ("22"), ou o parafuso ("M16", "5/8" — o furo sai com 1,5 mm de folga), a grade
 * ("2x2", linhas × colunas) e os passos ("50;60": entre colunas; entre linhas). O cursor leva o primeiro furo (C: o
 * centro da grade). Fica na ferramenta para a próxima grade.
 */
export class GradeFuros extends Ferramenta {
  static id = 'grade_furos'; static nome = 'Grade de furos'; static atalho = 'gf'; static grupo = 'desenho';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="16" rx="1"/><circle cx="8" cy="9" r="1.8"/><circle cx="16" cy="9" r="1.8"/><circle cx="8" cy="15" r="1.8"/><circle cx="16" cy="15" r="1.8"/></svg>';
  reiniciar() {
    super.reiniciar();
    if (!this.d) { this.d = 17.5; this.linhas = 2; this.colunas = 2; this.px = 60; this.py = 50; this.pelo = 'primeiro'; }
    this.dica(`Grade de furos Ø${fmt(this.d)} · ${this.linhas} × ${this.colunas} · passos ${fmt(this.px)} × ${fmt(this.py)} · clique onde fica o ${this.pelo === 'centro' ? 'centro da grade' : 'primeiro furo (embaixo à esquerda)'} · digite "M16", "22", "2x3" ou "60;50" · C: pelo ${this.pelo === 'centro' ? 'primeiro furo' : 'centro'}`);
  }
  _furos(p) {
    const ox = this.pelo === 'centro' ? (this.colunas - 1) * this.px / 2 : 0, oy = this.pelo === 'centro' ? (this.linhas - 1) * this.py / 2 : 0;
    const out = [];
    for (let j = 0; j < this.linhas; j++) for (let i = 0; i < this.colunas; i++) {
      out.push(criar({ tipo: 'circulo', camada: 'FURO', centro: [p[0] - ox + i * this.px, p[1] - oy + j * this.py], raio: this.d / 2 }));
    }
    return out;
  }
  onMover(p) { this.editor.previa(this._furos(p)); this.editor.medida(`${this.linhas * this.colunas} furo(s) Ø${fmt(this.d)}`); }
  onPonto(p) {
    const furos = this._furos(p);
    if (!this.doc.camadas.has('FURO')) this.doc.camadas.set('FURO', { nome: 'FURO', cor: '#1f5fbf', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.25 });
    this.editor.executar(new ComandoAdicionar(furos, `Grade de furos (${furos.length})`));
    this.dica(`${furos.length} furo(s) Ø${fmt(this.d)} · clique a próxima grade ou Esc`);
  }
  onValor(t) {
    const s = String(t || '').trim().toLowerCase().replace(/\s+/g, '');
    const g = s.match(/^(\d+)[x×*](\d+)$/);
    if (g) { this.linhas = Math.max(1, +g[1]); this.colunas = Math.max(1, +g[2]); this.reiniciar(); return; }
    const pr = s.split(';');
    if (pr.length === 2) { const a = paraMilimetros(pr[0]), b = paraMilimetros(pr[1]); if (a > 0 && b > 0) { this.px = a; this.py = b; } this.reiniciar(); return; }
    const d = diametroDoFuro(s);
    if (d > 0) { this.d = d; this.reiniciar(); }
  }
  onTecla(ev) {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    // as letras do "M16" não chegam à caixa MEDIDAS (só números): o M começa o parafuso métrico
    if (k === 'm') { this.editor.el && this.editor.el.medida && (this.editor.el.medida.value = 'M', this.editor.el.medida.focus()); return true; }
    if (k === 'c') { this.pelo = this.pelo === 'centro' ? 'primeiro' : 'centro'; this.reiniciar(); if (this.editor.tela.cursor) this.onMover(this.editor.tela.cursor); return true; }
    return false;
  }
}

// ------------------------------------------------------------ símbolos à mão (nucleo/simbolos.js)

/** A camada do símbolo, com a cor e a espessura padrão, quando o desenho ainda não a tem. */
function garantirCamada(doc, nome) {
  if (doc.camadas.has(nome)) return;
  const p = CAMADAS_PADRAO.find(c => c[0] === nome) || [nome, '#16202e', 'CONTINUOUS', 0.25];
  doc.camadas.set(nome, { nome, cor: p[1], visivel: true, bloqueada: false, tipo_linha: p[2], espessura: p[3] });
}
/** "6", "6-100", "6-50-150" (com - ; : / ou x entre os números) → os números. */
const numerosDe = (t) => String(t || '').trim().split(/\s*[-;:/x×]\s*/i).map(s => parseFloat(s.replace(',', '.'))).filter(v => isFinite(v) && v > 0);
/** O nível digitado em metros ("+5,00", "5", "-0,15", "±0,00") → mm; null se não é número. */
function nivelDigitado(t) {
  const v = parseFloat(String(t || '').trim().replace('±', '').replace('−', '-').replace(',', '.'));
  return isFinite(v) ? Math.round(v * 1000) : null;
}

export class SimboloSolda extends Ferramenta {
  static id = 'simbolo_solda'; static nome = 'Símbolo de solda (AWS)'; static atalho = 'sd'; static grupo = 'simbolos';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 20l6-8h12"/><path d="M13 12l3-4v4"/><path d="M3 20l.5-3M3 20l3-1.5"/></svg>';
  static LADOS = { seta: 'lado da seta', outro: 'outro lado', ambos: 'os dois lados' };
  reiniciar() {
    super.reiniciar();
    this.alvo = null;
    if (!this.cfg) this.cfg = { perna: 6, comprimento: 0, intermitente: null, lado: 'seta', forma: 'filete', contorno: false, campo: false, cauda: '' };
    this._dica();
  }
  _dica() {
    const c = this.cfg;
    const quanto = c.intermitente ? `${fmt(c.intermitente[0])}-${fmt(c.intermitente[1])} (intermitente)` : c.comprimento ? fmt(c.comprimento) : 'contínua';
    const opcoes = `${c.forma === 'penetracao' ? 'penetração' : `filete ${fmt(c.perna)}`} · ${quanto} · ${SimboloSolda.LADOS[c.lado]}${c.contorno ? ' · todo o contorno' : ''}${c.campo ? ' · de campo' : ''}${c.cauda ? ` · cauda "${c.cauda}"` : ''}`;
    this.dica(`Solda ${opcoes} · ${this.alvo ? 'clique onde começa a linha de referência' : 'clique no cordão (a ponta da seta)'} · digite "6", "6-100" ou "6-50-150" · L lado · F filete/penetração · O todo o contorno · B campo · T cauda`);
  }
  _regs(ref) { return simboloSolda({ alvo: this.alvo, ref, ...this.cfg }, this.doc.escala || 1, this.editor.alturaTexto).map(criar); }
  onPonto(p) {
    if (!this.alvo) { this.alvo = p; this.editor.snap.ultimo = p; this._dica(); return; }
    const regs = this._regs(p);
    garantirCamada(this.doc, 'SOLDA');
    this.editor.executar(new ComandoAdicionar(regs, 'Símbolo de solda'));
    this.alvo = null; this.editor.previa([]); this.editor.snap.ultimo = null;
    this._dica();
  }
  onMover(p) { if (this.alvo) this.editor.previa(this._regs(p)); }
  onValor(t) {
    const n = numerosDe(t);
    if (!n.length) return;
    this.cfg.perna = n[0];
    this.cfg.comprimento = n.length === 2 ? n[1] : 0;
    this.cfg.intermitente = n.length >= 3 ? [n[1], n[2]] : null;
    this._depoisDeMudar();
  }
  _depoisDeMudar() { this._dica(); if (this.alvo && this.editor.tela.cursor) this.onMover(this.editor.tela.cursor); }
  onTecla(ev) {
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    const k = ev.key.toLowerCase(), c = this.cfg;
    if (k === 'l') c.lado = { seta: 'outro', outro: 'ambos', ambos: 'seta' }[c.lado];
    else if (k === 'f') c.forma = c.forma === 'filete' ? 'penetracao' : 'filete';
    else if (k === 'o') c.contorno = !c.contorno;
    else if (k === 'b') c.campo = !c.campo;
    else if (k === 't') {
      this.editor.perguntar('Cauda da solda', 'Nota na cauda (ex.: TÍP., E70XX; vazio tira)', c.cauda).then(t => { if (t != null) { c.cauda = t.trim(); this._depoisDeMudar(); } });
      return true;
    } else return false;
    this._depoisDeMudar();
    return true;
  }
  desfazerPasso() { if (!this.alvo) return false; this.alvo = null; this.editor.previa([]); this._dica(); return true; }
}

export class BalaoMarca extends Ferramenta {
  static id = 'balao_marca'; static nome = 'Balão de marca'; static atalho = 'bm'; static grupo = 'simbolos';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="15" cy="9" r="6"/><path d="M10.8 13.2L4 20"/><path d="M13 11V7h2.5a1.4 1.4 0 010 2.8H13"/></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; this.sugestao = ''; this.dica('Balão de marca: clique na peça (a ponta da seta) · depois onde fica o balão · a marca vem da peça clicada; "4x V1" põe a quantidade'); }
  /** A marca da peça do detalhamento clicada (atributos da linha). */
  _marcaSob(ev) {
    const e = ev && ev.px ? this.editor.tela.sob(ev.px) : null;
    const a = (e && e.atributos) || {};
    return String(a.marca || a.posicao || a.nome || '');
  }
  _regs(centro, marca, quantidade = '') { return simboloBalao({ alvo: this.alvo, centro, marca, quantidade }, this.doc.escala || 1, this.editor.alturaTexto).map(criar); }
  async onPonto(p, ev) {
    if (!this.alvo) {
      this.alvo = p; this.sugestao = this._marcaSob(ev); this.editor.snap.ultimo = p;
      this.dica(`Clique onde fica o balão${this.sugestao ? ` (marca ${this.sugestao}, da peça clicada)` : ''}`);
      return;
    }
    const t = await this.editor.perguntar('Balão de marca', 'Marca (ex.: V1; "4x V1" com a quantidade)', this.sugestao || this.ultima || '');
    if (t != null && t.trim()) {
      const s = t.trim();
      const m = s.match(/^(\d+)\s*[x×]\s*(.+)$/i) || s.match(/^(.+?)\s+(\d+)\s*[x×]$/i);
      const [marca, qtd] = !m ? [s, ''] : /^\d+$/.test(m[1]) ? [m[2].trim(), m[1]] : [m[1].trim(), m[2]];
      garantirCamada(this.doc, 'TEXTO');
      this.editor.executar(new ComandoAdicionar(this._regs(p, marca, qtd), `Balão ${marca}`));
      this.ultima = marca;
    }
    this.reiniciar();
  }
  onMover(p) { if (this.alvo) this.editor.previa(this._regs(p, this.sugestao || this.ultima || '?')); }
  desfazerPasso() { if (!this.alvo) return false; this.reiniciar(); return true; }
}

export class SimboloNivel extends Ferramenta {
  static id = 'simbolo_nivel'; static nome = 'Nível (▽ +5,00)'; static atalho = 'nv'; static grupo = 'simbolos';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 16l3-5H1z" transform="translate(2 0)"/><path d="M2 16h20"/><path d="M12 11h7"/></svg>';
  reiniciar() { super.reiniciar(); this._dica(); }
  _dica() {
    this.dica(this.pedindoRef ? 'Clique o ponto de referência (o piso, a cota 0,00…) e diga o nível dele'
      : this.ref ? `Nível pela referência (${textoDoNivel(this.ref.valor)}): clique os pontos · digite um nível (m) para fixar · R outra referência`
      : `Nível ${this.valor != null ? textoDoNivel(this.valor) : ''}: digite o nível em metros ("5", "+5,20", "-0,15") e clique · R: os níveis pela altura, a partir de um ponto de referência`);
  }
  /** O nível no ponto: pela referência (a diferença de altura, na escala da célula da prancha) ou o digitado. */
  _valorEm(p) {
    if (!this.ref) return this.valor;
    const k = (this.editor.escalaNoPonto && this.editor.escalaNoPonto(p)) || 1;
    return this.ref.valor + (p[1] - this.ref.y) * k;
  }
  _regs(p, v) { return simboloNivel({ ponto: p, valor: v }, this.doc.escala || 1, this.editor.alturaTexto).map(criar); }
  async onPonto(p) {
    let v;
    if (this.pedindoRef) {
      const t = await this.editor.perguntar('Nível de referência', 'Nível deste ponto, em metros', '+0,00');
      v = nivelDigitado(t);
      if (v == null) return;
      this.ref = { y: p[1], valor: v }; this.pedindoRef = false;
    } else {
      v = this._valorEm(p);
      if (v == null) { v = nivelDigitado(await this.editor.perguntar('Nível', 'Nível, em metros (ex.: +5,00)', '')); if (v == null) return; this.valor = v; }
    }
    garantirCamada(this.doc, 'TEXTO');
    this.editor.executar(new ComandoAdicionar(this._regs(p, v), `Nível ${textoDoNivel(v)}`));
    this._dica();
  }
  onMover(p) { const v = this.pedindoRef ? null : this._valorEm(p); this.editor.previa(v == null ? [] : this._regs(p, v)); }
  onValor(t) { const v = nivelDigitado(t); if (v == null) return; this.valor = v; this.ref = null; this.pedindoRef = false; this._dica(); }
  onTecla(ev) {
    if (ev.ctrlKey || ev.altKey || ev.metaKey || ev.key.toLowerCase() !== 'r') return false;
    this.pedindoRef = true; this.editor.previa([]); this._dica();
    return true;
  }
  cancelar() { this.pedindoRef = false; super.cancelar(); }
}

export class ChamadaDetalhe extends Ferramenta {
  static id = 'chamada_detalhe'; static nome = 'Chamada de detalhe'; static atalho = 'cd'; static grupo = 'simbolos';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="15" r="5" stroke-dasharray="2 1.6"/><path d="M12 12l3-3"/><circle cx="18" cy="6" r="4"/><path d="M14 6h8"/></svg>';
  reiniciar() { super.reiniciar(); this.centro = null; this.raio = null; this.dica('Chamada de detalhe: clique no meio do trecho detalhado · depois o tamanho do círculo (ou digite o raio) · depois onde fica a bolha'); }
  /** O número seguinte aos das chamadas de detalhe do desenho. */
  _proximo() {
    let n = 0;
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (a.simbolo_tipo === 'detalhe') n = Math.max(n, parseInt((a.params || {}).numero, 10) || 0);
    }
    return String(n + 1);
  }
  _regs(bolha, numero, prancha) { return simboloDetalhe({ centro: this.centro, raio: this.raio, bolha, numero, prancha }, this.doc.escala || 1, this.editor.alturaTexto).map(criar); }
  async onPonto(p) {
    if (!this.centro) { this.centro = p; this.editor.snap.ultimo = p; this.dica('O tamanho do círculo: clique na borda ou digite o raio'); return; }
    if (this.raio == null) { this.raio = Math.max(dist(this.centro, p), 1); this.dica('Clique onde fica a bolha'); return; }
    const t = await this.editor.perguntar('Chamada de detalhe', 'Detalhe (ex.: 1; "1/03" com a prancha)', this._proximo());
    if (t != null && t.trim()) {
      const [numero, prancha = ''] = t.trim().split('/').map(s => s.trim());
      garantirCamada(this.doc, 'TEXTO');
      this.editor.executar(new ComandoAdicionar(this._regs(p, numero, prancha), `Chamada do detalhe ${numero}`));
    }
    this.reiniciar();
  }
  onMover(p) {
    if (!this.centro) return;
    if (this.raio == null) { this.editor.previa([criar({ tipo: 'circulo', camada: 'TEXTO', centro: this.centro, raio: Math.max(dist(this.centro, p), 1), tipo_linha: 'DASHED' })]); return; }
    this.editor.previa(this._regs(p, this._proximo(), ''));
  }
  onValor(t) {
    if (!this.centro || this.raio != null) return;
    const r = paraMilimetros(t);
    if (r > 0) { this.raio = r; this.dica('Clique onde fica a bolha'); }
  }
  desfazerPasso() {
    if (this.raio != null) { this.raio = null; this.dica('O tamanho do círculo: clique na borda ou digite o raio'); return true; }
    if (this.centro) { this.reiniciar(); return true; }
    return false;
  }
}

/** Nuvem de revisão (o REVCLOUD do AutoCAD; usuário, 24/10: "nuvem + triângulo"): o retângulo por dois cantos (P: o
 *  contorno por pontos, Enter fecha), depois o clique do △ com o número da revisão — o da prancha clicada (o "REV." do
 *  carimbo dela), ou o digitado; Enter ou espaço sem triângulo. O número digitado antes do contorno é o tamanho do arco
 *  (mm de papel). */
export class NuvemRevisao extends Ferramenta {
  static id = 'nuvem_revisao'; static nome = 'Nuvem de revisão'; static grupo = 'simbolos';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M5 9a2 2 0 013-2 2 2 0 014 0 2 2 0 014 0 2 2 0 013 2 2 2 0 010 4 2 2 0 01-3 2 2 2 0 01-4 0 2 2 0 01-4 0 2 2 0 01-3-2 2 2 0 010-4z"/><path d="M18 21l2.5-4 2.5 4z"/></svg>';
  reiniciar() {
    super.reiniciar();
    this.pts = []; this.contorno = null; this.rev = '';
    if (!this.arco) { this.arco = 6; this.modo = 'retangulo'; }
    this._dica();
  }
  _dica() {
    if (this.contorno) { this.dica(`Clique onde fica o triângulo da revisão ${this.rev || '?'} · digite outro número · Enter ou espaço: sem triângulo`); return; }
    this.dica(this.modo === 'poligono'
      ? `Nuvem pelo contorno: clique os pontos · Enter fecha · R: por retângulo · arco ${fmt(this.arco)} mm (digite para trocar)`
      : `Nuvem de revisão: ${this.pts.length ? 'o outro canto' : 'clique um canto do que mudou'} · P: pelo contorno · arco ${fmt(this.arco)} mm (digite para trocar)`);
  }
  /** A revisão da prancha no ponto: o "REV. 02" do número da prancha (o carimbo), na folha em que o ponto cai. */
  _revisaoNoPonto(p) {
    const m = this.doc.metadados || {};
    let numero = null;
    if (m.pranchas) {
      const f = m.pranchas.find(f => f.origem && f.tamanho && p[0] >= f.origem[0] && p[0] <= f.origem[0] + f.tamanho[0] && p[1] >= f.origem[1] && p[1] <= f.origem[1] + f.tamanho[1]);
      if (!f) return '';
      numero = f.numero;
    } else if (!m.prancha) return '';
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      if (e.tipo !== 'texto' || a.campo !== 'prancha' || (numero != null && a.prancha_numero !== numero)) continue;
      const r = String(e.texto || '').match(/REV\.\s*0*(\d+)/);
      return r && r[1] !== '0' ? r[1] : '';          // na REV. 00 (a emissão) ainda não há o que nuvear: o △ começa no 1
    }
    return '';
  }
  _retangulo(a, b) { return [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]]; }
  trechosEmAndamento() { return this.modo === 'poligono' && !this.contorno ? trechosDe(this.pts || []) : []; }
  _regs(vertices, delta) {
    return simboloNuvem({ vertices, arco: this.arco, delta, revisao: this.rev || '1' }, this.doc.escala || 1, this.editor.alturaTexto).map(criar);
  }
  _fecharContorno(vertices, p) {
    this.contorno = vertices; this.pts = [];
    this.rev = this._revisaoNoPonto(p) || this.rev || '1';
    this.editor.snap.ultimo = null;
    this._dica();
  }
  _gravar(delta) {
    garantirCamada(this.doc, 'TEXTO');
    this.editor.executar(new ComandoAdicionar(this._regs(this.contorno, delta), `Nuvem de revisão${delta ? ` (△${this.rev})` : ''}`));
    const modo = this.modo, arco = this.arco;
    this.reiniciar(); this.modo = modo; this.arco = arco; this._dica();
  }
  onPonto(p) {
    if (this.contorno) { this._gravar(p); return; }
    if (this.modo === 'retangulo') {
      if (!this.pts.length) { this.pts = [p]; this.editor.snap.ultimo = p; this._dica(); return; }
      if (Math.abs(p[0] - this.pts[0][0]) < 1e-6 || Math.abs(p[1] - this.pts[0][1]) < 1e-6) return;
      this._fecharContorno(this._retangulo(this.pts[0], p), p);
      return;
    }
    // pelo contorno: o clique no primeiro ponto também fecha
    if (this.pts.length >= 3 && dist(p, this.pts[0]) < 1e-6) { this._fecharContorno(this.pts, p); return; }
    this.pts.push(p); this.editor.snap.ultimo = p;
  }
  onMover(p) {
    if (this.contorno) { this.editor.previa(this._regs(this.contorno, p)); return; }
    if (!this.pts.length) return;
    const v = this.modo === 'retangulo' ? this._retangulo(this.pts[0], p) : [...this.pts, p];
    if (v.length >= 3) this.editor.previa(this._regs(v, null));
  }
  onValor(t) {
    if (this.contorno) { const r = String(t || '').trim(); if (r) { this.rev = r; this._dica(); } return; }
    const v = parseFloat(String(t || '').replace(',', '.'));
    if (v > 0) { this.arco = v; this._dica(); }
  }
  onTecla(ev) {
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
    const k = ev.key.toLowerCase();
    if (this.contorno && (ev.key === 'Enter' || ev.key === ' ')) { this._gravar(null); return true; }
    if (!this.contorno && this.modo === 'poligono' && ev.key === 'Enter' && this.pts.length >= 3) { this._fecharContorno(this.pts, this.pts[this.pts.length - 1]); return true; }
    if (!this.contorno && !this.pts.length && (k === 'p' || k === 'r')) { this.modo = k === 'p' ? 'poligono' : 'retangulo'; this._dica(); return true; }
    return false;
  }
  desfazerPasso() {
    if (this.contorno) { this.contorno = null; this.editor.previa([]); this._dica(); return true; }
    if (this.pts.length) { this.pts.pop(); this.editor.previa([]); this._dica(); return true; }
    return false;
  }
}

// ------------------------------------------------------------ blocos (web/cad/blocos.js; usuário, 24/10)

const ICONE_BLOCO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 8l8-4 8 4-8 4z"/><path d="M4 8v8l8 4 8-4V8M12 12v8"/></svg>';

/** Criar bloco (B / BLOCK): com a seleção feita, o clique é o ponto de base; o nome e as opções no diálogo. */
export class CriarBloco extends Ferramenta {
  static id = 'criar_bloco'; static nome = 'Criar bloco'; static grupo = 'edicao';
  static icone = ICONE_BLOCO.replace('</svg>', '<path d="M18 2v4M16 4h4"/></svg>');
  ativar() {
    super.ativar();
    this.ids = [...this.editor.tela.selecao];
    if (!this.ids.length) {
      this.editor.aviso('Criar bloco: selecione antes o que vai nele (clique ou janela) e B de novo.', 'atencao', 6000);
      queueMicrotask(() => this.editor.ativarFerramenta('selecionar'));
      return;
    }
    this.dica(`Criar bloco com ${this.ids.length} objeto(s): clique o ponto de base (o snap vale)`);
  }
  async onPonto(p) {
    if (!this.ids || !this.ids.length) return;
    const ids = this.ids; this.ids = [];
    await this.editor.criarBloco(ids, p);
    this.editor.ativarFerramenta('selecionar');
  }
}

/** Inserir bloco (I / INSERT): a escolha na lista (os do desenho e os da biblioteca) e o bloco preso ao cursor; R gira
 *  90°, E espelha, um número digitado é o ângulo e "x2" a escala. Fica para a próxima inserção até Esc. */
export class InserirBloco extends Ferramenta {
  static id = 'inserir_bloco'; static nome = 'Inserir bloco'; static grupo = 'edicao'; static icone = ICONE_BLOCO;
  ativar() { super.ativar(); this.nome = null; this.angulo = 0; this.escala = [1, 1]; this._escolher(); }
  async _escolher() {
    const nome = await this.editor.escolherBloco();
    if (this.editor.ferramenta !== this) return;
    if (!nome) { this.editor.ativarFerramenta('selecionar'); return; }
    this.nome = nome; this._dica();
    if (this.editor.tela.cursor) this.onMover(this.editor.tela.cursor);
  }
  _dica() {
    this.dica(`Bloco "${this.nome}" · ângulo ${fmt(this.angulo)}° · escala ${fmt(Math.abs(this.escala[0]))}${this.escala[0] < 0 ? ' espelhado' : ''} · clique onde fica o ponto de base · R gira 90° · E espelha · digite o ângulo ou "x2" (escala) · Esc sai`);
  }
  _insercao(p) { return criar({ tipo: 'bloco', nome: this.nome, posicao: [p[0], p[1]], escala: [...this.escala], angulo: this.angulo, camada: this.camada }); }
  onMover(p) { if (this.nome) this.editor.previa([this._insercao(p)]); }
  onPonto(p) {
    if (!this.nome) return;
    const e = this._insercao(p);
    this.editor.executar(new ComandoAdicionar([e], `Inserir o bloco ${this.nome}`));
  }
  onValor(t) {
    const s = String(t || '').trim().replace(',', '.');
    const m = s.match(/^[x*×]\s*(\d+(?:\.\d+)?)$/i);
    if (m && +m[1] > 0) { const v = +m[1]; this.escala = [Math.sign(this.escala[0]) * v, v]; }
    else if (isFinite(parseFloat(s))) this.angulo = ((parseFloat(s) % 360) + 360) % 360;
    else return;
    this._dica();
    if (this.editor.tela.cursor) this.onMover(this.editor.tela.cursor);
  }
  onTecla(ev) {
    if (ev.ctrlKey || ev.altKey || ev.metaKey || !this.nome) return false;
    const k = ev.key.toLowerCase();
    if (k === 'r') this.angulo = (this.angulo + 90) % 360;
    else if (k === 'e') this.escala = [-this.escala[0], this.escala[1]];
    else return false;
    this._dica();
    if (this.editor.tela.cursor) this.onMover(this.editor.tela.cursor);
    return true;
  }
}

/** Dividir (o DIVIDE do AutoCAD; usuário, 24/10: "marca de ponto"): a linha, o arco, o círculo ou a polilinha em N partes
 *  iguais, com uma marca de ponto (cruz na AUXILIAR) em cada divisão — o snap pega o meio dela. */
export class Dividir extends Ferramenta {
  static id = 'dividir'; static nome = 'Dividir (divide)'; static grupo = 'edicao';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 14h18"/><path d="M8 11.5v5M12 11.5v5M16 11.5v5"/></svg>';
  static TIPOS = new Set(['linha', 'arco', 'circulo', 'polilinha']);
  ativar() {
    super.ativar();
    // com um objeto já selecionado, ele é o que se divide (como o "Select object" do AutoCAD)
    const sel = [...this.editor.tela.selecao].map(id => this.doc.get(id)).filter(e => e && Dividir.TIPOS.has(e.tipo));
    if (sel.length === 1) this._escolher(sel[0]);
  }
  reiniciar() { super.reiniciar(); this.alvo = null; this.dica('Dividir: clique na linha, arco, círculo ou polilinha a dividir'); }
  _escolher(e) {
    this.alvo = e;
    this.editor.selecionar([e.id]);
    this.dica(`Em quantas partes? Digite e Enter (ex.: 5)${this.n ? ` · a prévia mostra ${this.n}, a última` : ''}`);
    if (this.n) this.editor.previa(this._marcas(this.n));
  }
  _marcas(n) {
    const k = this.doc.escala || 1;
    return pontosDaDivisao(this.alvo, n).flatMap(p => simboloPonto(p, k)).map(criar);
  }
  onPonto(p, ev) {
    const e = this.editor.tela.sob(ev.px);
    if (e && Dividir.TIPOS.has(e.tipo)) this._escolher(e);
  }
  onValor(t) {
    const n = parseInt(String(t || '').trim(), 10);
    if (!this.alvo || !(n >= 2)) return;
    this.n = n;
    const marcas = this._marcas(n);
    if (!marcas.length) return;
    if (!this.doc.camadas.has('AUXILIAR')) {
      const c = CAMADAS_PADRAO.find(x => x[0] === 'AUXILIAR');
      this.doc.camadas.set('AUXILIAR', { nome: 'AUXILIAR', cor: c[1], visivel: true, bloqueada: false, tipo_linha: c[2], espessura: c[3] });
    }
    this.editor.executar(new ComandoAdicionar(marcas, `Dividir em ${n}`));
    this.reiniciar();
    this.editor.selecionar([]);
    this.dica(`Dividido em ${n} (${marcas.length / 2} marca(s)) · clique no próximo objeto ou Esc`);
  }
  desfazerPasso() { if (!this.alvo) return false; this.reiniciar(); return true; }
}

export class Offset extends Ferramenta {
  static id = 'offset'; static nome = 'Offset (paralela)'; static atalho = 'f'; static grupo = 'edicao'; static dica = 'Offset: clique na linha, arco, círculo ou polilinha; depois do lado desejado (ou digite a distância e clique o lado)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 8h16M4 16h16" /></svg>';
  reiniciar() { super.reiniciar(); this.alvo = null; this.distancia = null; }
  onPonto(p, ev) {
    if (!this.alvo) { const e = this.editor.tela.sob(ev.px); if (e && (e.tipo === 'linha' || e.tipo === 'circulo' || e.tipo === 'polilinha' || e.tipo === 'arco')) { this.alvo = e; this.dica(this.distancia != null ? `Distância ${fmt(this.distancia)}: clique do lado desejado` : 'Lado (clique) ou distância (digite)'); } return; }
    const n = this._paralela(p, this.distancia);
    if (n) this.editor.executar(new ComandoAdicionar([n], 'Offset'));
    // a distância digitada vale para os próximos offsets, até Esc
    const d = this.distancia;
    this.reiniciar();
    this.distancia = d;
    if (d != null) this.dica(`Offset ${fmt(d)}: clique na próxima linha (Esc sai)`);
  }
  onValor(t) { const v = paraMilimetros(t); if (v != null) { this.distancia = v; this.dica(`Distância ${fmt(v)}: clique do lado desejado`); } }
  onMover(p) { if (this.alvo) { const n = this._paralela(p, this.distancia); if (n) this.editor.previa([n]); } }
  _paralela(p, dfix) {
    const e = this.alvo;
    if (e.tipo === 'circulo' || e.tipo === 'arco') { const d = dfix ?? Math.abs(dist(p, e.centro) - e.raio); const r = dist(p, e.centro) > e.raio ? e.raio + d : e.raio - d; return r > 0 ? criar({ ...e, id: undefined, raio: r }) : null; }
    if (e.tipo === 'linha') {
      const dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L;
      const lado = Math.sign((p[0] - e.a[0]) * nx + (p[1] - e.a[1]) * ny) || 1;
      const d = (dfix ?? Math.abs((p[0] - e.a[0]) * nx + (p[1] - e.a[1]) * ny)) * lado;
      return criar({ ...e, id: undefined, a: [e.a[0] + nx * d, e.a[1] + ny * d], b: [e.b[0] + nx * d, e.b[1] + ny * d] });
    }
    // polilinha: desloca cada vértice pela bissetriz das normais (bom para contornos simples). O lado é o do segmento
    // mais perto do clique (antes o sinal pela área e pelo "dentro" saía invertido, e a aberta era tratada como fechada:
    // o último vértice se ligava ao primeiro — teste de fluxo, 15/10)
    const v = e.vertices, n = v.length, out = [];
    const fechada = !!(e.fechada && n > 2);
    let sMin = null, dMin = Infinity;
    for (const [a, b] of segmentosDe(e)) { const dd = distSegP(p, a, b); if (dd < dMin) { dMin = dd; sMin = [a, b]; } }
    if (!sMin) return null;
    const nn = normal(sMin[0], sMin[1]);
    const lado = Math.sign((p[0] - sMin[0][0]) * nn[0] + (p[1] - sMin[0][1]) * nn[1]) || 1;
    const d = (dfix ?? dMin) * lado;
    for (let i = 0; i < n; i++) {
      const prev = v[(i - 1 + n) % n], cur = v[i], next = v[(i + 1) % n];
      // nas pontas da aberta vale a normal do único segmento que chega nelas
      const n1 = !fechada && i === 0 ? normal(cur, next) : normal(prev, cur);
      const n2 = !fechada && i === n - 1 ? n1 : normal(cur, next);
      let bx = n1[0] + n2[0], by = n1[1] + n2[1];
      const l = Math.hypot(bx, by) || 1;
      const cosHalf = Math.max(0.2, (n1[0] * bx + n1[1] * by) / l);
      out.push([cur[0] + (bx / l) * d / cosHalf, cur[1] + (by / l) * d / cosHalf]);
    }
    return criar({ ...e, id: undefined, vertices: out });
  }
}
const normal = (a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1; return [-dy / L, dx / L]; };
const distSegP = (p, a, b) => dist(p, maisProximoSeg(p, a, b));

export class Medir extends Ferramenta {
  static id = 'medir'; static nome = 'Medir'; static atalho = 'u'; static grupo = 'medicao'; static dica = 'Primeiro ponto';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 17L17 3l4 4L7 21z"/><path d="M8 12l2 2M11 9l2 2M14 6l2 2"/></svg>';
  reiniciar() { super.reiniciar(); this.a = null; this.dica(`Primeiro ponto${this.trava ? ` · travado na ${NOME_DA_TRAVA[this.trava]}` : ' · as setas travam num eixo'}`); }
  /** O segundo ponto no eixo travado pelas setas (a medida só na horizontal ou só na vertical). */
  _travado(p) { return !this.a || !this.trava ? p : this.trava === 'h' ? [p[0], this.a[1]] : [this.a[0], p[1]]; }
  onPonto(p) {
    if (!this.a) { this.a = p; this.editor.snap.ultimo = p; this.dica(`Segundo ponto${this.trava ? ` · travado na ${NOME_DA_TRAVA[this.trava]}` : ' · as setas travam num eixo'}`); return; }
    p = this._travado(p);
    this.editor.aviso(`Distância: ${medidaComUnidade(dist(this.a, p))}  ·  Δx ${numeroNaUnidade(p[0] - this.a[0])}  Δy ${numeroNaUnidade(p[1] - this.a[1])}  ·  ∠ ${fmt(ang(this.a, p) * 180 / Math.PI)}°`);
    this.reiniciar();
  }
  onMover(p) { if (this.a) { p = this._travado(p); this.editor.previa([criar({ tipo: 'linha', camada: 'AUXILIAR', a: this.a, b: p })]); this.editor.medida(`${fmt(dist(this.a, p))} mm`); } }
  onTecla(ev) {
    const trava = travaPelaSeta(ev, this.trava);
    if (trava === undefined) return false;
    this.trava = trava;
    this.dica(trava ? `Medida travada na ${NOME_DA_TRAVA[trava]} · a mesma seta solta` : 'Medida livre');
    if (this.a) this.onMover(this.editor.tela.cursor || this.a);
    return true;
  }
}


// ------------------------------------------------------------ corte (marcar e gerar)

/** A vista do modelo (com referência 2D) que contém o ponto do papel, ou null. */
function vistaDoPonto(doc, p) {
  for (const v of doc.vistas || []) {
    const c = v.canto || [0, 0];
    if (!v.ref2d || !v.origem || !v.normal) continue;
    if (p[0] >= c[0] - 1 && p[0] <= c[0] + (v.largura || 0) + 1 && p[1] >= c[1] - 1 && p[1] <= c[1] + (v.altura || 0) + 1) return v;
  }
  return null;
}
const _n3 = (a) => { const L = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / L, a[1] / L, a[2] / L]; };
const _x3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
/** (u, v, w) da vista, como `nucleo2d.vistas.Vista.eixos`. */
function eixosDaVista(vista) {
  const w = _n3(vista.normal);
  let acima = vista.acima || (Math.abs(w[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0]);
  acima = _n3(acima);
  const u = _n3(_x3(w, acima));
  return { u, v: _n3(_x3(u, w)), w };
}
/** Ponto do papel → 3D no plano da vista: dot(q − origem, u) = X − canto_x + ref2d[0] (idem v). */
function para3d(vista, p) {
  const { u, v } = eixosDaVista(vista);
  const c = vista.canto || [0, 0];
  const lu = p[0] - c[0] + vista.ref2d[0], lv = p[1] - c[1] + vista.ref2d[1];
  return [0, 1, 2].map(i => vista.origem[i] + u[i] * lu + v[i] * lv);
}

/**
 * Corte: marca a linha de corte no desenho (linha, setas para o lado que se olha e as
 * bolinhas com o nome nas pontas, como 1-1, 2-2) e gera a vista do corte no modelo 3D
 * pela planta em que a linha foi desenhada. Três cliques: começo, fim e o lado para onde
 * se olha. Precisa de um desenho com vista do modelo (planta de localização, de chumbação,
 * vista inserida pelo CAD) — é por ela que a linha do papel vira o plano no 3D.
 */
export class Corte extends Ferramenta {
  static id = 'corte'; static nome = 'Corte (marcar e gerar)'; static atalho = 'y'; static grupo = 'desenho';
  static dica = 'Corte: clique no começo da linha de corte (numa planta do modelo)';
  static icone = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 11h16"/><path d="M6 11v5M18 11v5"/><path d="M4 14l2 2 2-2M16 14l2 2 2-2"/><circle cx="4" cy="8" r="2"/><circle cx="20" cy="8" r="2"/></svg>';
  reiniciar() { super.reiniciar(); this.p1 = null; this.p2 = null; }

  _nome() {
    const usados = new Set();
    for (const e of this.doc.entidades.values()) if (e.atributos && e.atributos.marca_corte) usados.add(String(e.atributos.marca_corte));
    let n = 1;
    while (usados.has(String(n))) n++;
    return String(n);
  }

  /** As entidades da marca: linha, setas e bolinhas com o nome. */
  _marcas(p1, p2, lado, nome) {
    const esc = this.doc.escala;
    const L = dist(p1, p2) || 1;
    const d = [(p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L];
    let nrm = [-d[1], d[0]];
    if (lado && ((lado[0] - p1[0]) * nrm[0] + (lado[1] - p1[1]) * nrm[1]) < 0) nrm = [-nrm[0], -nrm[1]];
    const atr = { marca_corte: nome };
    const cam = 'CORTES';
    const h = this.editor.alturaTexto || 2.5;
    const seta = 8 * esc, r = 4 * esc, ponta = 2.2 * esc;
    const ents = [criar({ tipo: 'linha', camada: cam, a: p1, b: p2, atributos: atr })];
    for (const [ponta0, fora] of [[p1, [-d[0], -d[1]]], [p2, d]]) {
      const fim = [ponta0[0] + nrm[0] * seta, ponta0[1] + nrm[1] * seta];
      ents.push(criar({ tipo: 'linha', camada: cam, a: ponta0, b: fim, atributos: atr }));
      // ponta de seta no lado que se olha
      for (const s of [1, -1]) {
        ents.push(criar({ tipo: 'linha', camada: cam, a: fim, b: [fim[0] - nrm[0] * ponta + s * d[0] * ponta * 0.8, fim[1] - nrm[1] * ponta + s * d[1] * ponta * 0.8], atributos: atr }));
      }
      const c = [ponta0[0] + fora[0] * (r + 2 * esc), ponta0[1] + fora[1] * (r + 2 * esc)];
      ents.push(criar({ tipo: 'circulo', camada: cam, centro: c, raio: r, atributos: atr }));
      ents.push(criar({ tipo: 'texto', camada: cam, posicao: [c[0], c[1] - 0.35 * h * esc], texto: nome, altura: h, alinhamento: 'centro', atributos: atr }));
    }
    return ents;
  }

  async onPonto(p) {
    if (!this.p1) { this.p1 = p; this.editor.snap.ultimo = p; this.dica('Fim da linha de corte'); return; }
    if (!this.p2) { if (dist(p, this.p1) < 1e-6) return; this.p2 = p; this.editor.snap.ultimo = null; this.dica('Clique do lado para onde se olha'); return; }
    const p1 = this.p1, p2 = this.p2, lado = p;
    const nome = this._nome();
    this.editor.executar(new ComandoAdicionar(this._marcas(p1, p2, lado, nome), `Corte ${nome}`));
    this.reiniciar();
    const vista = vistaDoPonto(this.doc, p1);
    if (!vista) {
      this.editor.aviso(`Corte ${nome}-${nome} marcado. Para gerar a vista, a linha tem de estar sobre uma vista do modelo com referência (planta de localização ou de chumbação gerada nesta versão, ou vista inserida pelo CAD).`, 'atencao', 12000);
      return;
    }
    const { w } = eixosDaVista(vista);
    if (Math.abs(w[2]) < 0.9) { this.editor.aviso(`Corte ${nome}-${nome} marcado; a vista só é gerada a partir de uma planta (vista de cima).`, 'atencao', 10000); return; }
    const prof = await this.editor.perguntar(`Corte ${nome}-${nome}`, 'Gerar a vista do corte no modelo — profundidade de vista (mm); vazio cancela', '3000');
    if (prof == null || !String(prof).trim()) return;
    const q1 = para3d(vista, p1), q2 = para3d(vista, p2), q3 = para3d(vista, lado);
    const d3 = [q2[0] - q1[0], q2[1] - q1[1], 0];
    let n3 = _n3(_x3(d3, [0, 0, 1]));
    if ((q3[0] - q1[0]) * n3[0] + (q3[1] - q1[1]) * n3[1] < 0) n3 = [-n3[0], -n3[1], 0];
    const pf = parseFloat(String(prof).replace(',', '.'));
    await this.editor.inserirVista({ origem: q1, normal: n3, acima: [0, 0, 1], profundidade: isFinite(pf) && pf > 0 ? pf : null, cortar: true,
                                     nome: `Corte ${nome}-${nome}`, tipo: 'corte' }, `Corte ${nome}-${nome}`);
  }

  onMover(p) {
    if (this.p1 && !this.p2) this.editor.previa([criar({ tipo: 'linha', camada: 'CORTES', a: this.p1, b: p })]);
    else if (this.p2) this.editor.previa(this._marcas(this.p1, this.p2, p, '?'));
  }
}

export const FERRAMENTAS = [Selecionar, ZoomJanela, Linha, Polilinha, Retangulo, Circulo, ArcoTresPontos, Texto, TextoVariasLinhas, Cota, CotaContinua, CotaBase, CotaRapida, CotaAngular, CotaRaio, CotaDiametro, CotaOrdenada, AjustarCota, Chamada, SetaChamada, Corte, Hachura,
  GradeFuros, SimboloSolda, BalaoMarca, SimboloNivel, ChamadaDetalhe, NuvemRevisao, CriarBloco, InserirBloco, Mover, Copiar, Girar, Espelhar, Escalar, Matriz, Esticar, Offset, Aparar, Estender, Quebrar, Alongar, Concordar, Chanfro, Explodir, Juntar, Dividir, MoverCota, CopiarPropriedades, Apagar, Medir];
export const GRUPOS = [['navegacao', 'Nav'], ['desenho', 'Des'], ['simbolos', 'Sím'], ['edicao', 'Edi'], ['medicao', 'Med']];
