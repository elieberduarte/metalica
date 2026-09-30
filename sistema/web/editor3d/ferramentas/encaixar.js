// Encaixar: a ponta da barra cortada (ou esticada) no plano de uma face — o "Fit" do Tekla, para
// ajustar à mão o que a regra automática do encaixe (nucleo3d/alma_na_face.encaixar) deixou passar.
//
// 1. Clique na barra a ajustar.
// 2. Clique na face em que ela deve encostar: a ponta mais perto dessa face é cortada no plano
//    dela (a meia-esquadria). Se a barra não chega até a face, ela é esticada até lá.
//    Com Shift, o plano é somado aos que a ponta já tem (o bico: a face do banzo e a do
//    montante), e a ferramenta continua na mesma barra para a próxima face.
// Del (com a barra escolhida) tira os cortes das duas pontas: a barra volta reta, de nó a nó.
//
// O corte vai em `cortes_inicio`/`cortes_fim` (o ponto relativo ao nó da ponta, nos eixos do
// mundo), o mesmo formato da regra automática: o 3D, o IFC, o peso e a lista de corte já contam
// com ele, e o desfazer (Ctrl+Z) volta.

import { Ferramenta } from './base.js';
import * as C from './_comum.js';
import { alturasDeCorte, prismaCortado } from '../nucleo/cena.js';
import { baseDaBarra } from '../nucleo/documento.js';

const r4 = (x) => Math.round(x * 1e4) / 1e4;

/** O corte fica de pé nesta barra? (a malha não some em ponto nenhum) */
export function corteValido(cena, barra) {
  try {
    const [f0, f1] = alturasDeCorte(barra, baseDaBarra(barra.inicio, barra.fim, barra.rotacao));
    return !!prismaCortado(cena._secaoDoPerfil(barra.perfil), f0, f1);
  } catch (e) {
    return false;
  }
}

/**
 * Os campos que a barra ganha com o plano (ponto P, normal n) na ponta mais perto dele.
 * `somar` junta aos planos que a ponta já tem. Devolve {campos, ponta} ou null (o plano é
 * quase paralelo à barra e não corta ponta nenhuma).
 */
export function encaixeNaFace(barra, P, n, somar = false) {
  const d = C.normalizar(C.sub(barra.fim, barra.inicio));
  n = C.normalizar(n);
  if (Math.abs(C.dot(n, d)) < 0.1) return null;
  // a ponta mais perto do plano (pela distância do nó a ele)
  const dI = Math.abs(C.dot(C.sub(barra.inicio, P), n));
  const dF = Math.abs(C.dot(C.sub(barra.fim, P), n));
  const ponta = dI <= dF ? 'inicio' : 'fim';
  const no = ponta === 'inicio' ? barra.inicio : barra.fim;
  const outro = ponta === 'inicio' ? barra.fim : barra.inicio;
  // a normal aponta para dentro da peça (para o lado do outro nó)
  if (C.dot(C.sub(outro, P), n) < 0) n = C.mul(n, -1);
  const plano = { normal: n.map(r4), ponto: C.sub(P, no).map(r4) };
  const chave = ponta === 'inicio' ? 'cortes_inicio' : 'cortes_fim';
  const antes = somar ? (barra[chave] || []) : [];
  return {
    ponta,
    campos: { [chave]: [...antes.map(c => ({ normal: [...c.normal], ponto: [...c.ponto] })), plano],
              [ponta === 'inicio' ? 'recorte_inicio' : 'recorte_fim']: 0 },
  };
}

export class FerramentaEncaixar extends Ferramenta {
  static id = 'encaixar';
  static nome = 'Encaixar ponta';
  static atalho = '';
  static grupo = 'estrutura';
  static dica = 'Clique na barra a ajustar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 20h18"/><path d="M3 16.5h18" stroke-dasharray="2 2"/><path d="M6 16.5 15 4l3.5 2.5-7.2 10"/></svg>`;

  ativar() {
    this.barra = null;
    this.dica(FerramentaEncaixar.dica);
    this.medida('');
  }

  desativar() { this.cancelar(); }

  cancelar() {
    this.barra = null;
    this.limparPrevia();
    this.selecao.limpar();
    this.dica(FerramentaEncaixar.dica);
  }

  /** O que está de verdade sob o cursor (a face do clique, sem o snap puxar para outra peça). */
  _sob(p) {
    const t = p && p.tela;
    return t ? this.editor.selecao.sob(t[0], t[1]) : null;
  }

  onMover(p) {
    if (!this.barra) return;
    this.limparPrevia();
    const alvo = this._sob(p);
    if (!alvo || alvo.id === this.barra) return;
    const b = this.documento.get(this.barra);
    const r = b && encaixeNaFace(b, alvo.ponto, alvo.normal);
    if (!r) return;
    const no = r.ponta === 'inicio' ? b.inicio : b.fim;
    // a prévia: o nó que vai para a face e o plano do corte
    const n = C.normalizar(alvo.normal), u = C.perpendicular(n), v = C.cross(n, u), s = 120;
    const Q = alvo.ponto;
    const q = (a, c) => C.add(Q, C.add(C.mul(u, a), C.mul(v, c)));
    this.previa(C.grupo(C.gPoligono([q(-s, -s), q(s, -s), q(s, s), q(-s, s)], C.CORES.face, 0.25),
                        C.gPonto(no, '#ff5a1f')));
  }

  onPonto(p, ev = {}) {
    const alvo = this._sob(p);
    if (!this.barra) {
      const e = alvo && this.documento.get(alvo.id);
      if (!e || e.tipo !== 'barra') { this.dica('Clique numa barra (perfil) para ajustar a ponta dela'); return; }
      this.barra = e.id;
      this.selecao.definir([e.id]);
      this.dica(`${e.nome || e.perfil}: clique na face em que a ponta deve encostar (Shift soma o plano: o bico) · Del tira os cortes · Esc sai`);
      return;
    }
    if (!alvo || alvo.id === this.barra) {
      const e = alvo && this.documento.get(alvo.id);
      if (alvo && alvo.id === this.barra) { this.dica('Essa é a própria barra: clique na face da outra peça'); return; }
      if (!e) { this.dica('Clique numa face de outra peça'); return; }
    }
    const b = this.documento.get(this.barra);
    const somar = !!(ev && ev.shiftKey);
    const r = encaixeNaFace(b, alvo.ponto, alvo.normal, somar);
    if (!r) { this.dica('Essa face corre ao longo da barra: não corta a ponta. Escolha a face em que ela chega'); return; }
    if (!corteValido(this.cena, { ...b, ...r.campos })) {
      this.dica('Esse corte comeria a peça inteira: escolha outra face');
      return;
    }
    this.executar(C.cmdAlterar(b.id, r.campos, somar ? 'Encaixar ponta (bico)' : 'Encaixar ponta'));
    this.limparPrevia();
    const quantos = r.campos[r.ponta === 'inicio' ? 'cortes_inicio' : 'cortes_fim'].length;
    if (somar) {
      this.dica(`Ponta com ${quantos} plano(s). Shift + clique soma outro; clique sem Shift troca; Esc termina`);
    } else {
      this.barra = null;
      this.selecao.limpar();
      this.dica('Ponta encaixada. Clique na próxima barra (Ctrl+Z desfaz)');
    }
  }

  onTecla(ev) {
    if (this.barra && (ev.key === 'Delete' || ev.key === 'Backspace')) {
      this.executar(C.cmdAlterar(this.barra, { cortes_inicio: [], cortes_fim: [] }, 'Tirar os cortes das pontas'));
      this.dica('Cortes tirados: a barra está reta de nó a nó. Clique na face para encaixar de novo, ou Esc');
      return true;
    }
    return false;
  }
}
