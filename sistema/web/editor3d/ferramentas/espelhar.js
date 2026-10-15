// Espelhar (F9 do levantamento de 14/10): a seleção refletida num plano — a treliça do outro lado do eixo, a ligação
// do lado oposto.
//
// Selecione e clique dois pontos: o espelho é o plano vertical que passa por eles (o eixo da obra numa planta). Ou tecle
// X, Y ou Z: o plano com essa normal pelo centro da seleção. Por padrão sai a cópia espelhada; com Ctrl, a original vai
// para o outro lado (sem cópia).
//
// A barra espelhada guarda o perfil: o giro da seção é refeito para a seção ficar espelhada de verdade — o I e o U
// (simétricos no eixo da alma) e a cantoneira de abas iguais (simétrica na diagonal: gira 90°). A seção sem simetria
// (cantoneira de abas desiguais, Z) não espelha: o espelhado seria outra peça, que o catálogo não tem — ela fica de
// fora, com aviso. A chapa vira do lado certo (a face que crescia para fora continua para fora); o sólido tem as faces
// refeitas. A peça espelhada fica com a marca a conferir (a espelhada é marca própria, regra da leva 2).

import { Ferramenta } from './base.js';
import * as C from './_comum.js';
import { baseDaBarra } from '../nucleo/documento.js';

const LADOS = { cima: [0, 1], baixo: [0, -1], esquerda: [1, 0], direita: [-1, 0] };

/** O plano do espelho {p, n}: reflexão de pontos e de direções. */
export function refletor(plano) {
  const n = C.normalizar(plano.n), p = plano.p;
  return {
    fp: (q) => C.sub(q, C.mul(n, 2 * C.dot(C.sub(q, p), n))),
    fv: (v) => C.sub(v, C.mul(n, 2 * C.dot(v, n))),
  };
}

/**
 * O ângulo φ (graus) de uma reta de simetria da seção pela origem dela (0 = o eixo x da seção), ou null quando a seção
 * não é simétrica em nenhuma (abas desiguais, Z). Confere as retas de 0°, 90°, 45° e 135°, com 0,5 mm de folga.
 */
export function simetriaDaSecao(pts) {
  if (!pts || pts.length < 3) return null;
  const distSeg = (q, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
    const t = L2 > 0 ? Math.max(0, Math.min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2)) : 0;
    return Math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy);
  };
  const naBorda = (q) => {
    let m = Infinity;
    for (let i = 0; i < pts.length; i++) m = Math.min(m, distSeg(q, pts[i], pts[(i + 1) % pts.length]));
    return m < 0.5;
  };
  for (const phi of [0, 90, 45, 135]) {
    const a = 2 * phi * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    if (pts.every(([x, y]) => naBorda([x * c + y * s, x * s - y * c]))) return phi;
  }
  return null;
}

/**
 * Os campos da entidade espelhada no plano: {campos} ou {erro}. `secao(perfil)` dá o contorno [[x, y]] da seção.
 */
export function camposEspelhados(ent, plano, secao) {
  const { fp, fv } = refletor(plano);
  const campos = C.camposTransformados(ent, fp, fv);
  // a cota espelhada se solta das peças: na barra refletida o ponto preso cairia do outro lado da seção (F20)
  const ct = campos.atributos && campos.atributos.cota;
  if (ct && ct.refs) campos.atributos = { ...campos.atributos, cota: { ...ct, refs: null } };
  if (ent.tipo === 'barra') {
    const pts = secao(ent.perfil);
    if (!pts) return { erro: `${ent.perfil}: a seção do perfil não está no banco do editor — não dá para saber se ela é simétrica` };
    const phi = simetriaDaSecao(pts);
    if (phi === null) return { erro: `${ent.perfil}: a seção não tem simetria — a espelhada seria outra peça` };
    // camposTransformados leva a largura (u) para a imagem dela; com a reflexão, a altura (v) sai invertida — a seção
    // fica refletida no eixo x dela, o que é a seção girada de −2φ quando ela é simétrica na reta φ
    const r0 = campos.rotacao !== undefined ? campos.rotacao : (ent.rotacao || 0);
    let r = ((r0 - 2 * phi) % 360 + 360) % 360;
    r = Math.round(r * 1e6) / 1e6;
    campos.rotacao = r >= 360 ? r - 360 : r;
    // os recortes de encaixe: o lado de cada um vai para onde a reflexão o levou
    if ((ent.recortes || []).length) {
      const b0 = baseDaBarra(ent.inicio, ent.fim, ent.rotacao || 0);
      const b1 = baseDaBarra(campos.inicio, campos.fim, campos.rotacao);
      campos.recortes = ent.recortes.map(rc => {
        const [dx, dy] = LADOS[rc.lado] || [0, 1];
        const w = fv(C.add(C.mul(b0.u, dx), C.mul(b0.v, dy)));
        const x = C.dot(w, b1.u), y = C.dot(w, b1.v);
        const lado = Math.abs(x) > Math.abs(y) ? (x > 0 ? 'esquerda' : 'direita') : (y > 0 ? 'cima' : 'baixo');
        return { ...rc, lado };
      });
    }
  } else if (ent.tipo === 'chapa') {
    // a reflexão troca a mão dos eixos: o y da chapa (e o do contorno e dos furos) vira, e a normal continua a imagem da
    // de antes — a chapa que crescia para fora da face continua crescendo para fora
    campos.eixo_y = C.mul(campos.eixo_y, -1);
    campos.contorno = (campos.contorno || []).map(([u, v]) => [u, -v]).reverse();
    campos.furos = (campos.furos || []).map(f => ({ ...f, y: -(f.y || 0) }));
  } else if (ent.tipo === 'solido') {
    campos.faces = (ent.faces || []).map(f => f.slice().reverse());
  }
  const m = ent.atributos && ent.atributos.marcas;
  if (m && (m.posicao || m.conjunto)) {
    campos.atributos = { ...(campos.atributos || ent.atributos), marca_a_conferir: true, espelhada_de: ent.id };
  }
  return { campos };
}

export class FerramentaEspelhar extends Ferramenta {
  static id = 'espelhar';
  static nome = 'Espelhar';
  static atalho = 'W';
  static grupo = 'edicao';
  static dica = 'Selecione e clique dois pontos do espelho (plano vertical) · ou tecle X, Y ou Z · Ctrl move em vez de copiar';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 3v18" stroke-dasharray="2 2"/><path d="M9 7 4 17h5Z"/><path d="M15 7l5 10h-5Z"/></svg>`;

  ativar() {
    this.ids = C.idsSelecionados(this.editor);
    this.a = null; this.atual = null; this.mover = false; C.descartarFantasma(this._fantasma); this._fantasma = null;
    this.dica(this.ids.length ? FerramentaEspelhar.dica : 'Nada selecionado: selecione o que espelhar e chame a ferramenta de novo');
    this.medida('');
  }

  desativar() { C.desancorar(this.editor); this.limparPrevia(); }

  cancelar() {
    if (this.a) { this.a = null; C.desancorar(this.editor); this.limparPrevia(); this.dica(FerramentaEspelhar.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  /** A seção real do perfil (null quando o editor só tem a provisória: o retângulo enganaria a simetria). */
  _secao(perfil) {
    const cena = this.editor && this.editor.cena;
    if (!cena || (typeof cena.perfil === 'function' && !cena.perfil(perfil))) return null;
    return C.secaoDoPerfil(null, cena, perfil);
  }

  _planoPorDois(a, b) {
    const d = C.sub(b, a);
    const h = [d[0], d[1], 0];
    if (C.comp(h) < 1e-6) return null;                               // pontos na mesma vertical
    return { p: a, n: C.normalizar([-h[1], h[0], 0]) };
  }

  _centro() {
    const c = C.caixaDe(this.documento, this.ids);
    return c.centro;
  }

  onMover(p, ev) {
    if (!p || !this.ids.length) return;
    this.mover = !!(ev && ev.ctrlKey);
    if (!this.a) return;
    this.atual = C.copiar(p.ponto);
    const plano = this._planoPorDois(this.a, this.atual);
    this.desenhar(plano);
  }

  onPonto(p, ev = {}) {
    if (!p) return;
    this.ids = C.idsSelecionados(this.editor);
    if (!this.ids.length) { this.dica('Selecione o que espelhar antes.'); return; }
    if (!this.a) {
      this.a = C.copiar(p.ponto);
      C.ancorar(this.editor, this.a);
      this.dica('Clique o segundo ponto do espelho (o plano vertical por eles) · Ctrl move em vez de copiar');
      return;
    }
    const plano = this._planoPorDois(this.a, p.ponto);
    if (!plano) { this.dica('Os dois pontos estão na mesma vertical: escolha um segundo ponto ao lado'); return; }
    this.aplicar(plano, !!(ev && ev.ctrlKey));
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown' || !this.ids.length) return false;
    const k = String(ev.key || '').toLowerCase();
    const n = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }[k];
    if (!n || ev.ctrlKey || ev.altKey) return false;
    this.aplicar({ p: this._centro(), n }, !!ev.shiftKey);
    return true;
  }

  aplicar(plano, mover) {
    const ents = this.ids.map(id => this.documento.get(id)).filter(Boolean);
    const { pecas, bloqueadas } = C.pecasParaTransformar(this.documento, ents, !mover);
    const novos = [], alteracoes = [], fora = [];
    const mapa = new Map();
    for (const e of pecas) {
      const r = camposEspelhados(e, plano, (n) => this._secao(n));
      if (r.erro) { fora.push(r.erro); continue; }
      if (mover) { alteracoes.push(C.cmdAlterar(e.id, r.campos, 'Espelhar')); continue; }
      const c = C.clonarEntidade(e);
      Object.assign(c, r.campos);
      mapa.set(e.id, c.id);
      novos.push(c);
    }
    C.religarMarcadores(novos, mapa);
    const cmds = mover ? alteracoes : (novos.length ? [C.cmdAdicionar(novos, 'Espelhar (cópia)')] : []);
    if (cmds.length) this.executar(C.cmdComposto(cmds, mover ? 'Espelhar' : 'Espelhar (cópia)'));
    C.avisarBloqueadas(this.editor, bloqueadas);
    if (fora.length) this.editor.aviso(`${fora.length} peça(s) não espelhada(s): ${[...new Set(fora)].slice(0, 3).join('; ')}`, 'atencao');
    if (!mover && novos.length) this.selecao.definir(novos.map(c => c.id));
    this.a = null; C.descartarFantasma(this._fantasma); this._fantasma = null; C.desancorar(this.editor); this.limparPrevia();
    this.dica(`${mover ? 'Espelhada(s)' : 'Cópia espelhada de'} ${mover ? alteracoes.length : novos.length} peça(s) (Ctrl+Z desfaz)`);
  }

  desenhar(plano) {
    this.limparPrevia();
    if (!plano) return;
    const { fp, fv } = refletor(plano);
    const g = C.grupo();
    // o espelho: um retângulo vertical pelo plano
    const c = this.a, t = C.normalizar(C.cross(plano.n, [0, 0, 1]));
    const s = 3000;
    const q = (a, b) => C.add(c, C.add(C.mul(t, a), [0, 0, b]));
    g.add(C.gPoligono([q(-s, -s / 3), q(s, -s / 3), q(s, s), q(-s, s)], C.CORES.face || '#7aa7f0', 0.12));
    // a própria peça, translúcida, refletida (o fantasma); a silhueta só para a que não tem objeto próprio
    const chave = this.ids.join('|');
    if (!this._fantasma || this._fantasma.chave !== chave) { C.descartarFantasma(this._fantasma); this._fantasma = { chave, ...C.fantasmaDe(this.editor, this.ids) }; }
    C.posicionarFantasma(this._fantasma, fp, fv);
    g.add(this._fantasma.obj);
    for (const id of this.ids) {
      if (this._fantasma.ids.has(id)) continue;
      const e = this.documento.get(id);
      if (!e) continue;
      const pts = C.pontosDaEntidade(e).map(fp);
      if (pts.length === 2) g.add(C.gLinha(pts, C.CORES.ok));
      else if (pts.length >= 3) g.add(C.gLinha(pts, C.CORES.ok, { fechada: e.tipo === 'chapa' }));
    }
    this.medida(this.mover ? 'espelhar (mover)' : 'espelhar (cópia)');
    this.previa(g);
  }
}

export default FerramentaEspelhar;
