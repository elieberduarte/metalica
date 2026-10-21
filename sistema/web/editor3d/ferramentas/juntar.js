// Juntar pontas: duas barras que não se encontram passam a se encontrar num ponto só, cortadas em meia-esquadria — o
// Fillet (raio 0) do AutoCAD, no 3D (usuário, 21/10: "criar uma ferramenta similar a essa [Estender] para 'juntar' as
// peças, seria algo similar ao fillet do AutoCAD, porém no 3D, onde ela ligue as peças no ponto médio entre as duas";
// depois: "já fazer o recorte automático dos perfis/barras/tubos").
//
// 1. Clique na primeira barra.
// 2. Clique na segunda: a ponta de cada uma mais perto do encontro vai até ele — o ponto em que os eixos se cruzam ou,
//    quando os eixos não se cruzam de verdade (o banzo e o montante com os eixos em planos diferentes), o meio do
//    segmento mais curto entre os dois eixos. Cada barra estica ou apara o que precisar, e as duas pontas são cortadas
//    no plano que divide o ângulo entre elas (a meia-esquadria do canto de um quadro: o U contra o U, o tubo contra o
//    tubo), numa entrada só do desfazer. Com Ctrl no segundo clique, só junta, sem cortar.
// Com duas barras já selecionadas ao abrir a ferramenta, Enter junta as duas (Ctrl+Enter sem o corte).
// O corte vai em `cortes_inicio`/`cortes_fim`, o mesmo formato do Encaixar (o 3D, o IFC, o peso e a lista de corte já
// contam com ele); os cortes que a ponta tinha saem (eram relativos ao nó antigo). Barras quase em linha (menos de ~12°
// entre elas) só juntam: a meia-esquadria ficaria comprida demais. A peça com marca fica com a marca a conferir (o
// Numerar separa). Ctrl+Z desfaz as duas de uma vez.

import { Ferramenta, formatar } from './base.js';
import * as C from './_comum.js';
// o corteValido vem do Encaixar (que puxa a cena e o three): carregado de lado, para o módulo valer sozinho nos testes
let _corteValido = null;
import('./encaixar.js').then(m => { _corteValido = m.corteValido; }).catch(() => {});

const r2 = (x) => Math.round(x * 100) / 100;
const r4 = (x) => Math.round(x * 1e4) / 1e4;

/** O plano (ponto P, normal n) gravado na ponta `ponta` da barra, no formato do Encaixar: a normal para dentro da peça. */
function planoNaPonta(barra, ponta, P, n) {
  const no = ponta === 'inicio' ? barra.inicio : barra.fim, outro = ponta === 'inicio' ? barra.fim : barra.inicio;
  const d = C.normalizar(C.sub(outro, no));
  if (Math.abs(C.dot(n, d)) < 0.1) return null;                      // quase paralelo à barra: não corta
  if (C.dot(C.sub(outro, P), n) < 0) n = C.mul(n, -1);
  return { normal: n.map(r4), ponto: C.sub(P, no).map(r4) };
}

/**
 * O ponto de encontro dos eixos das barras `a` e `b`: o cruzamento ou, com os eixos desencontrados, o meio do segmento
 * mais curto entre eles. Devolve {ponto, afastamento} (afastamento = a distância entre os eixos ali) ou null (paralelas).
 */
export function pontoDeJuncao(a, b) {
  const d = C.normalizar(C.sub(a.fim, a.inicio)), e = C.normalizar(C.sub(b.fim, b.inicio));
  const w = C.sub(a.inicio, b.inicio);
  const b_ = C.dot(d, e), dd = C.dot(d, w), ee = C.dot(e, w);
  const den = 1 - b_ * b_;
  if (!(den > 1e-6)) return null;                                      // paralelas
  const s = (b_ * ee - dd) / den, r = (ee - b_ * dd) / den;
  const pa = C.add(a.inicio, C.mul(d, s)), pb = C.add(b.inicio, C.mul(e, r));
  return { ponto: C.mul(C.add(pa, pb), 0.5), afastamento: C.dist(pa, pb) };
}

/**
 * O que cada barra ganha para a ponta mais perto do encontro ir até ele, cortada em meia-esquadria (`cortar`):
 * {ponto, afastamento, normal, barras: [{id, ponta, fixo, antes, novo, dL, campos}, …]}; `normal` é a do plano da
 * meia-esquadria (null sem corte). null quando as barras são paralelas ou uma delas viraria do avesso (o encontro fica
 * atrás da ponta que não anda). `valido(barraCortada)` recusa o corte que a cena não consegue desenhar.
 */
export function juncao(a, b, { cortar = true, valido = null } = {}) {
  const j = pontoDeJuncao(a, b);
  if (!j) return null;
  const barras = [];
  for (const bar of [a, b]) {
    const ponta = C.dist(bar.inicio, j.ponto) <= C.dist(bar.fim, j.ponto) ? 'inicio' : 'fim';
    const fixo = ponta === 'inicio' ? bar.fim : bar.inicio, antes = ponta === 'inicio' ? bar.inicio : bar.fim;
    if (C.dot(C.sub(j.ponto, fixo), C.sub(antes, fixo)) <= 0 || C.dist(fixo, j.ponto) < 1) return null;
    const novo = j.ponto.map(r2);
    barras.push({ id: bar.id, ponta, fixo, antes, novo, dL: C.dist(fixo, j.ponto) - C.dist(fixo, antes),
                  campos: { [ponta]: novo, [`cortes_${ponta}`]: [], [`recorte_${ponta}`]: 0 }, original: bar });
  }
  // a meia-esquadria: o plano pelo encontro que divide o ângulo entre as duas barras (a normal é a diferença das
  // direções com que cada uma chega ao encontro); barras quase em linha não cortam
  let normal = null;
  if (cortar) {
    const dA = C.normalizar(C.sub(j.ponto, barras[0].fixo)), dB = C.normalizar(C.sub(j.ponto, barras[1].fixo));
    const n = C.sub(dA, dB);
    if (C.comp(n) > 0.2) {
      normal = C.normalizar(n);
      for (const r of barras) {
        const movida = { ...r.original, [r.ponta]: r.novo, cortes_inicio: [], cortes_fim: [], recorte_inicio: 0, recorte_fim: 0 };
        const plano = planoNaPonta(movida, r.ponta, j.ponto, normal);
        if (!plano) { normal = null; break; }
        const campos = { ...r.campos, [`cortes_${r.ponta}`]: [plano] };
        const cortada = { ...movida, ...campos };
        if (valido && !valido(cortada)) { normal = null; break; }
        r.campos = campos;
        r.cortada = cortada;
      }
      if (!normal) for (const r of barras) { r.campos = { [r.ponta]: r.novo, [`cortes_${r.ponta}`]: [], [`recorte_${r.ponta}`]: 0 }; delete r.cortada; }
    }
  }
  return { ...j, normal, barras };
}

export class FerramentaJuntar extends Ferramenta {
  static id = 'juntar';
  static nome = 'Juntar pontas';
  static atalho = 'J';
  static grupo = 'estrutura';
  static dica = 'Clique na primeira barra e na segunda: as pontas se encontram no cruzamento dos eixos, cortadas em meia-esquadria (Ctrl: sem o corte) — o Fillet do AutoCAD, no 3D';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 20h9"/><path d="M12 20V7"/><path d="M12 4v3" stroke-dasharray="1.5 1.5"/><path d="M15 20h4" stroke-dasharray="1.5 1.5"/><circle cx="12" cy="20" r="1.4"/><path d="M20 3l-6 6"/><path d="M15.5 9H14V7.5"/></svg>`;

  ativar() {
    this.primeira = null;
    this.par = null;
    const sel = C.idsSelecionados(this.editor).map(id => this.documento.get(id)).filter(e => e && e.tipo === 'barra');
    if (sel.length === 2 && C.editavel(this.editor, sel[0]) && C.editavel(this.editor, sel[1]) && this._juncao(sel[0], sel[1])) {
      this.par = [sel[0].id, sel[1].id];
      this._previa(this._juncao(sel[0], sel[1]));
      this.dica('Enter junta as duas barras selecionadas no encontro dos eixos, em meia-esquadria (Ctrl+Enter: sem o corte) · ou clique na primeira barra');
      return;
    }
    this.dica(FerramentaJuntar.dica);
    this.medida('');
  }

  desativar() { this.limparPrevia(); }

  cancelar() {
    if (this.primeira || this.par) { this.primeira = null; this.par = null; this.limparPrevia(); this.selecao.limpar(); this.medida(''); this.dica(FerramentaJuntar.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  /** A barra sob o cursor (pelo pixel; sem pixel, pela entidade do ponto). */
  _barraSob(p) {
    const t = p && p.tela;
    const s = t && this.editor.selecao && typeof this.editor.selecao.sob === 'function' ? this.editor.selecao.sob(t[0], t[1]) : null;
    let e = s && (s.entidade || this.documento.get(s.id));
    if ((!e || e.tipo !== 'barra') && p && p.entidade) e = this.documento.get(p.entidade);
    return e && e.tipo === 'barra' ? e : null;
  }

  _juncao(a, b, ev) {
    const cena = this.editor && this.editor.cena;
    const valido = cena && typeof cena._secaoDoPerfil === 'function' && _corteValido ? (bar) => _corteValido(cena, bar) : null;
    return juncao(a, b, { cortar: !(ev && ev.ctrlKey), valido });
  }

  _previa(j) {
    this.limparPrevia();
    if (!j) return;
    const g = C.grupo(C.gPonto(j.ponto, '#0a8f3c'));
    for (const b of j.barras) {
      g.add(C.gLinha([b.fixo, b.novo], '#0a8f3c', { tracejada: true }));
      g.add(C.gRotulo(`${b.dL >= 0 ? 'estica' : 'apara'} ${formatar(Math.abs(b.dL))}`, C.mul(C.add(b.antes, b.novo), 0.5), '#0a8f3c'));
    }
    if (j.normal) {
      // o plano da meia-esquadria, no encontro
      const u = C.perpendicular(j.normal), v = C.cross(j.normal, u), s = 150;
      const q = (x, y) => C.add(j.ponto, C.add(C.mul(u, x), C.mul(v, y)));
      g.add(C.gPoligono([q(-s, -s), q(s, -s), q(s, s), q(-s, s)], C.CORES.face, 0.25));
    }
    const desenc = j.afastamento > 1 ? ` · eixos a ${formatar(j.afastamento)} um do outro: encontro no meio` : '';
    this.medida(`${j.barras.map(b => `${b.dL >= 0 ? '+' : '−'}${formatar(Math.abs(b.dL))}`).join('  ·  ')}${j.normal ? ' · meia-esquadria' : ' · sem corte'}${desenc}`);
    this.previa(g);
  }

  onMover(p, ev) {
    if (!this.primeira) return;
    const b = this._barraSob(p);
    const a = this.documento.get(this.primeira);
    if (!b || !a || b.id === a.id) { this.limparPrevia(); this.medida(''); return; }
    const j = this._juncao(a, b, ev);
    if (!j) { this.limparPrevia(); this.dica('Essa barra corre paralela à primeira (ou uma delas viraria do avesso): escolha outra'); return; }
    this._previa(j);
  }

  onPonto(p, ev) {
    const b = this._barraSob(p);
    if (!this.primeira) {
      if (!b) { this.dica('Clique numa barra (perfil do catálogo)'); return; }
      if (!C.editavel(this.editor, b)) { this.dica(C.DICA_BLOQUEADA); return; }
      this.par = null;
      this.primeira = b.id;
      this.selecao.definir([b.id]);
      this.dica('Agora clique na segunda barra: as pontas mais perto do encontro vão até ele, em meia-esquadria (Ctrl: sem o corte) · Esc volta');
      return;
    }
    if (!b || b.id === this.primeira) { this.dica('Clique na OUTRA barra'); return; }
    if (!C.editavel(this.editor, b)) { this.dica(C.DICA_BLOQUEADA); return; }
    this._juntar(this.documento.get(this.primeira), b, ev);
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.par) {
      const [a, b] = this.par.map(id => this.documento.get(id));
      if (a && b) this._juntar(a, b, ev);
      return true;
    }
    return false;
  }

  _juntar(a, b, ev) {
    const j = this._juncao(a, b, ev);
    if (!j) { this.dica('Não dá para juntar essas duas (paralelas, ou uma delas viraria do avesso): escolha outra'); return; }
    const cmds = j.barras.map(r => C.cmdAlterar(r.id, C.marcarParaConferir(this.documento.get(r.id), r.campos), 'Juntar pontas'));
    this.executar(C.cmdComposto(cmds, 'Juntar pontas'));
    this.limparPrevia();
    this.primeira = null;
    this.par = null;
    this.selecao.limpar();
    this.medida('');
    const desenc = j.afastamento > 1 ? ` (os eixos estavam a ${formatar(j.afastamento)} um do outro: encontro no meio)` : '';
    const corte = j.normal ? ', em meia-esquadria' : (ev && ev.ctrlKey ? ', sem corte' : ', sem corte (quase em linha)');
    this.dica(`Juntadas${corte}${desenc}. Clique na próxima barra (Ctrl+Z desfaz as duas; Delete no Encaixar tira o corte)`);
  }
}

export default FerramentaJuntar;
