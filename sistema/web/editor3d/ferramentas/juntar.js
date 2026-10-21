// Juntar pontas: duas barras que não se encontram passam a se encontrar num ponto só — o Fillet (raio 0) do AutoCAD,
// no 3D (usuário, 21/10: "criar uma ferramenta similar a essa [Estender] para 'juntar' as peças, seria algo similar ao
// fillet do AutoCAD, porém no 3D, onde ela ligue as peças no ponto médio entre as duas").
//
// 1. Clique na primeira barra.
// 2. Clique na segunda: a ponta de cada uma mais perto do encontro vai até ele — o ponto em que os eixos se cruzam ou,
//    quando os eixos não se cruzam de verdade (o banzo e o montante com os eixos em planos diferentes), o meio do
//    segmento mais curto entre os dois eixos. Cada barra estica ou apara o que precisar, numa entrada só do desfazer.
// Com duas barras já selecionadas ao abrir a ferramenta, Enter junta as duas.
// Os cortes no ângulo das pontas que andaram saem (eram relativos ao nó antigo); o Encaixar refaz, se precisar. A peça
// com marca fica com a marca a conferir (o Numerar separa). Ctrl+Z desfaz as duas de uma vez.

import { Ferramenta, formatar } from './base.js';
import * as C from './_comum.js';

const r2 = (x) => Math.round(x * 100) / 100;

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
 * O que cada barra ganha para a ponta mais perto do encontro ir até ele: [{id, ponta, fixo, antes, novo, dL}, …] com o
 * ponto e o afastamento; null quando as barras são paralelas ou uma delas viraria do avesso (o encontro fica atrás da
 * ponta que não anda).
 */
export function juncao(a, b) {
  const j = pontoDeJuncao(a, b);
  if (!j) return null;
  const barras = [];
  for (const bar of [a, b]) {
    const ponta = C.dist(bar.inicio, j.ponto) <= C.dist(bar.fim, j.ponto) ? 'inicio' : 'fim';
    const fixo = ponta === 'inicio' ? bar.fim : bar.inicio, antes = ponta === 'inicio' ? bar.inicio : bar.fim;
    if (C.dot(C.sub(j.ponto, fixo), C.sub(antes, fixo)) <= 0 || C.dist(fixo, j.ponto) < 1) return null;
    barras.push({ id: bar.id, ponta, fixo, antes, novo: j.ponto.map(r2), dL: C.dist(fixo, j.ponto) - C.dist(fixo, antes) });
  }
  return { ...j, barras };
}

export class FerramentaJuntar extends Ferramenta {
  static id = 'juntar';
  static nome = 'Juntar pontas';
  static atalho = 'J';
  static grupo = 'estrutura';
  static dica = 'Clique na primeira barra e na segunda: as pontas se encontram no cruzamento dos eixos (o Fillet do AutoCAD, no 3D)';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 20h9"/><path d="M12 20V7"/><path d="M12 4v3" stroke-dasharray="1.5 1.5"/><path d="M15 20h4" stroke-dasharray="1.5 1.5"/><circle cx="12" cy="20" r="1.4"/><path d="M20 3l-6 6"/><path d="M15.5 9H14V7.5"/></svg>`;

  ativar() {
    this.primeira = null;
    this.par = null;
    const sel = C.idsSelecionados(this.editor).map(id => this.documento.get(id)).filter(e => e && e.tipo === 'barra');
    if (sel.length === 2 && C.editavel(this.editor, sel[0]) && C.editavel(this.editor, sel[1]) && juncao(sel[0], sel[1])) {
      this.par = [sel[0].id, sel[1].id];
      this._previa(juncao(sel[0], sel[1]));
      this.dica('Enter junta as duas barras selecionadas no encontro dos eixos · ou clique na primeira barra');
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

  _previa(j) {
    this.limparPrevia();
    if (!j) return;
    const g = C.grupo(C.gPonto(j.ponto, '#0a8f3c'));
    for (const b of j.barras) {
      g.add(C.gLinha([b.fixo, b.novo], '#0a8f3c', { tracejada: true }));
      g.add(C.gRotulo(`${b.dL >= 0 ? 'estica' : 'apara'} ${formatar(Math.abs(b.dL))}`, C.mul(C.add(b.antes, b.novo), 0.5), '#0a8f3c'));
    }
    const desenc = j.afastamento > 1 ? ` · eixos a ${formatar(j.afastamento)} um do outro: encontro no meio` : '';
    this.medida(`${j.barras.map(b => `${b.dL >= 0 ? '+' : '−'}${formatar(Math.abs(b.dL))}`).join('  ·  ')}${desenc}`);
    this.previa(g);
  }

  onMover(p) {
    if (!this.primeira) return;
    const b = this._barraSob(p);
    const a = this.documento.get(this.primeira);
    if (!b || !a || b.id === a.id) { this.limparPrevia(); this.medida(''); return; }
    const j = juncao(a, b);
    if (!j) { this.limparPrevia(); this.dica('Essa barra corre paralela à primeira (ou uma delas viraria do avesso): escolha outra'); return; }
    this._previa(j);
  }

  onPonto(p) {
    const b = this._barraSob(p);
    if (!this.primeira) {
      if (!b) { this.dica('Clique numa barra (perfil do catálogo)'); return; }
      if (!C.editavel(this.editor, b)) { this.dica(C.DICA_BLOQUEADA); return; }
      this.par = null;
      this.primeira = b.id;
      this.selecao.definir([b.id]);
      this.dica('Agora clique na segunda barra: as pontas mais perto do encontro vão até ele · Esc volta');
      return;
    }
    if (!b || b.id === this.primeira) { this.dica('Clique na OUTRA barra'); return; }
    if (!C.editavel(this.editor, b)) { this.dica(C.DICA_BLOQUEADA); return; }
    this._juntar(this.documento.get(this.primeira), b);
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'Enter' && this.par) {
      const [a, b] = this.par.map(id => this.documento.get(id));
      if (a && b) this._juntar(a, b);
      return true;
    }
    return false;
  }

  _juntar(a, b) {
    const j = juncao(a, b);
    if (!j) { this.dica('Não dá para juntar essas duas (paralelas, ou uma delas viraria do avesso): escolha outra'); return; }
    const cmds = j.barras.map(r => {
      const ent = this.documento.get(r.id);
      const campos = { [r.ponta]: r.novo, [`cortes_${r.ponta}`]: [], [`recorte_${r.ponta}`]: 0 };
      return C.cmdAlterar(r.id, C.marcarParaConferir(ent, campos), 'Juntar pontas');
    });
    this.executar(C.cmdComposto(cmds, 'Juntar pontas'));
    this.limparPrevia();
    this.primeira = null;
    this.par = null;
    this.selecao.limpar();
    this.medida('');
    const desenc = j.afastamento > 1 ? ` (os eixos estavam a ${formatar(j.afastamento)} um do outro: encontro no meio)` : '';
    this.dica(`Juntadas${desenc}. Clique na próxima barra (Ctrl+Z desfaz as duas; o Encaixar corta as pontas no ângulo, se precisar)`);
  }
}

export default FerramentaJuntar;
