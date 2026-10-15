// Enrijecedor (F10 do levantamento de 14/10 — o "Stiffener" do Tekla/Advance): um clique na alma do perfil e saem as
// chapas entre as mesas, dos dois lados da alma (no U, do lado das mesas), com o chanfro do canto para a solda passar.
//
// Passe o mouse na barra: a posição anda de 5 em 5 mm a partir da ponta mais perto, com a distância às pontas. Clique
// para pôr ali, ou digite a distância da ponta mais perto. O painel tem a espessura (a padrão é a da alma arredondada
// para a chapa comercial acima, no mínimo 6,3), o chanfro do canto (20 mm) e o recuo da borda da mesa (0 = rente).
// A alma, as mesas e as bordas saem da própria seção do perfil (o I, o W, o H, o U laminado ou dobrado).

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
import { baseDaBarra } from '../nucleo/documento.js';

const ESPESSURAS = [6.3, 8, 9.5, 12.5, 16, 19, 22.4, 25];

/** Onde a reta (horizontal: y = k; vertical: x = k) corta o polígono: os trechos de dentro, [[a, b], …]. */
export function trechosDentro(pts, vertical, k) {
  const ts = [];
  for (let i = 0; i < pts.length; i++) {
    const A = pts[i], B = pts[(i + 1) % pts.length];
    const a = vertical ? A[0] : A[1], b = vertical ? B[0] : B[1];
    if ((a > k) === (b > k)) continue;
    const s = (k - a) / (b - a);
    ts.push(vertical ? A[1] + s * (B[1] - A[1]) : A[0] + s * (B[0] - A[0]));
  }
  ts.sort((x, y) => x - y);
  const out = [];
  for (let i = 0; i + 1 < ts.length; i += 2) out.push([ts[i], ts[i + 1]]);
  return out;
}

/**
 * A geometria do enrijecedor de um lado da alma, no plano da seção (x = largura, y = altura da seção): {x0, x1, y0, y1}
 * (x0 na face da alma, x1 na borda da mesa menos o recuo; y0 e y1 nas faces de dentro das mesas), ou null quando
 * desse lado não há mesa (as costas do U).
 */
export function vaoDoEnrijecedor(pts, lado, recuo = 0) {
  const ys = pts.map(p => p[1]), xs = pts.map(p => p[0]);
  const ym = (Math.min(...ys) + Math.max(...ys)) / 2;
  const alma = trechosDentro(pts, false, ym);                         // a linha do meio corta só a alma
  if (alma.length !== 1) return null;
  const [wa, wb] = alma[0];
  const face = lado > 0 ? wb : wa;
  const borda = lado > 0 ? Math.max(...xs) : Math.min(...xs);
  if (Math.abs(borda - face) < 10) return null;                       // não há mesa desse lado
  // as faces de dentro das mesas, na vertical do meio do vão
  const xm = (face + borda) / 2;
  const mesas = trechosDentro(pts, true, xm);
  if (mesas.length < 2) return null;
  const y0 = mesas[0][1], y1 = mesas[mesas.length - 1][0];
  if (y1 - y0 < 10) return null;
  const x1 = borda - lado * recuo;
  return { x0: face, x1, y0, y1, tw: wb - wa };
}

/** O contorno do enrijecedor (no plano da seção, o x a partir da face da alma) com o chanfro nos dois cantos da alma. */
export function contornoDoEnrijecedor(v, lado, chanfro) {
  const L = Math.abs(v.x1 - v.x0), c = Math.max(0, Math.min(chanfro, L / 2 - 1, (v.y1 - v.y0) / 2 - 1));
  // em coordenadas locais da chapa: u a partir da alma para fora, v na altura
  return [[0, v.y0 + c], [c, v.y0], [L, v.y0], [L, v.y1], [c, v.y1], [0, v.y1 - c]];
}

export class FerramentaEnrijecedor extends Ferramenta {
  static id = 'enrijecedor';
  static nome = 'Enrijecedor';
  static atalho = 'Shift+H';
  static grupo = 'estrutura';
  static dica = 'Clique na barra (perfil I, H ou U) onde vai o enrijecedor · digite a distância da ponta mais perto';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 4h16M4 20h16M12 4v16"/><path d="M12 7.5l2.5-3.5h4v16h-4L12 16.5Z" fill="currentColor" fill-opacity=".25"/></svg>`;
  static espessura = null;     // null: a da alma, arredondada para a comercial acima
  static chanfro = 20;
  static recuo = 0;
  static lados = 'dois';

  ativar() { this.sob = null; this.dica(FerramentaEnrijecedor.dica); this.medida(''); }
  desativar() { this.limparPrevia(); }
  cancelar() { this.limparPrevia(); C.voltarParaSelecao(this.editor); }

  painel(raiz, el) {
    const F = this.constructor;
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Enrijecedor' }),
                   el('span', { texto: `${F.espessura ? formatar(F.espessura, 1) : 'espessura da alma'} · chanfro ${formatar(F.chanfro)}` })));
    const g = el('div', { class: 'campos' });
    const num = (chave, titulo, vazio) => {
      const i = el('input', { type: 'number', min: '0', step: '0.5', value: F[chave] == null ? '' : String(F[chave]), placeholder: vazio || '',
                              title: titulo, style: 'width:6em' });
      i.addEventListener('change', () => { F[chave] = i.value === '' ? null : Math.max(0, +i.value || 0); });
      return i;
    };
    const s = el('select', { title: 'Dos dois lados da alma ou só do lado clicado' });
    s.append(el('option', { value: 'dois', texto: 'dos dois lados' }), el('option', { value: 'um', texto: 'só do lado clicado' }));
    s.value = F.lados;
    s.addEventListener('change', () => { F.lados = s.value; });
    g.append(el('label', { texto: 'Espessura (mm)' }), num('espessura', 'Espessura da chapa (vazio: a da alma, na comercial acima)', 'a da alma'),
             el('label', { texto: 'Chanfro do canto' }), num('chanfro', 'O canto na alma com a mesa, chanfrado para a solda passar (mm)'),
             el('label', { texto: 'Recuo da borda' }), num('recuo', 'Quanto o enrijecedor fica para dentro da borda da mesa (mm; 0 = rente)'),
             el('label', { texto: 'Lados' }), s);
    raiz.append(g);
  }

  _barraSob(p) {
    const t = p && p.tela;
    const s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    const e = s && s.entidade;
    return e && e.tipo === 'barra' ? { e, ponto: s.ponto } : null;
  }

  _secao(perfil) {
    const cena = this.editor && this.editor.cena;
    if (!cena || (typeof cena.perfil === 'function' && !cena.perfil(perfil))) return null;
    return C.secaoDoPerfil(null, cena, perfil);
  }

  /** A posição (do início) de 5 em 5 mm a partir da ponta mais perto. */
  _s(b, ponto) {
    const d = C.normalizar(C.sub(b.fim, b.inicio)), L = C.dist(b.inicio, b.fim);
    let s = Math.max(0, Math.min(L, C.dot(C.sub(ponto, b.inicio), d)));
    return s <= L - s ? Math.round(s / 5) * 5 : L - Math.round((L - s) / 5) * 5;
  }

  /** As chapas do enrijecedor na posição `s` da barra (lado clicado: o sinal do ponto na largura da seção). */
  chapas(b, s, ladoClicado) {
    const pts = this._secao(b.perfil);
    if (!pts) return { erro: `${b.perfil}: a seção do perfil não está no banco do editor` };
    const F = this.constructor;
    const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
    const o = C.add(b.inicio, C.mul(t, s));
    const lados = F.lados === 'um' ? [ladoClicado] : [1, -1];
    const out = [];
    for (const lado of lados) {
      const vao = vaoDoEnrijecedor(pts, lado, F.recuo || 0);
      if (!vao) continue;
      let e = F.espessura;
      if (!e) e = ESPESSURAS.find(x => x >= vao.tw - 0.01) || Math.ceil(vao.tw);
      const contorno = contornoDoEnrijecedor(vao, lado, F.chanfro || 0);
      // a chapa no plano da seção: o x dela sai da face da alma para fora (u·lado), o y é o da seção (v)
      const origem = C.add(o, C.mul(u, vao.x0));
      out.push({
        tipo: 'chapa', id: C.novoId('ch'), nome: `ENRIJECEDOR ${formatar(Math.abs(vao.x1 - vao.x0))}×${formatar(vao.y1 - vao.y0)}×${formatar(e, 1)}`,
        camada: 'Chapas', material: '', visivel: true, bloqueada: false, grupo: b.grupo || '',
        origem, eixo_x: C.mul(u, lado), eixo_y: v,
        contorno,                                      // no plano dela: do mesmo jeito dos dois lados
        espessura: e, centrada: true, furos: [], aco: b.aco || 'ASTM A36',
        atributos: { criado_no_editor: true, enrijecedor_de: b.id,
                     ...(b.atributos && b.atributos.marcas && b.atributos.marcas.conjunto ? { marcas: { conjunto: b.atributos.marcas.conjunto } } : {}) },
      });
    }
    if (!out.length) return { erro: 'Desse perfil não sai enrijecedor (sem mesas dos dois lados da alma desse lado)' };
    return { chapas: out };
  }

  onMover(p) {
    this.limparPrevia();
    const sob = this._barraSob(p);
    this.sob = sob;
    if (!sob) return;
    const b = sob.e, L = C.dist(b.inicio, b.fim);
    const s = this._s(b, sob.ponto);
    const { u } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
    const lado = C.dot(C.sub(sob.ponto, b.inicio), u) >= 0 ? 1 : -1;
    const r = this.chapas(b, s, lado);
    if (r.erro) { this.medida(r.erro); return; }
    const g = C.grupo();
    for (const ch of r.chapas) {
      const pts = ch.contorno.map(([x, y]) => C.add(ch.origem, C.add(C.mul(ch.eixo_x, x), C.mul(ch.eixo_y, y))));
      g.add(C.gPoligono(pts, '#c2410c', 0.35));
      g.add(C.gLinha(pts, '#c2410c', { fechada: true }));
    }
    g.add(C.gRotulo(`${formatar(s)} | ${formatar(L - s)} · ${r.chapas.length} chapa(s) ${formatar(r.chapas[0].espessura, 1)} mm`,
                    r.chapas[0].origem, '#c2410c'));
    this.medida(`${formatar(Math.min(s, L - s))} da ponta`);
    this.previa(g);
  }

  onPonto(p) {
    const sob = this._barraSob(p);
    if (!sob) { this.dica('Clique numa barra (perfil I, H ou U), onde vai o enrijecedor'); return; }
    const { u } = baseDaBarra(sob.e.inicio, sob.e.fim, sob.e.rotacao || 0);
    const lado = C.dot(C.sub(sob.ponto, sob.e.inicio), u) >= 0 ? 1 : -1;
    this.colocar(sob.e, this._s(sob.e, sob.ponto), lado);
  }

  onValor(texto) {
    const v = paraMilimetros(texto);
    const b = this.sob && this.sob.e;
    if (!b || !(v > 0)) return false;
    const L = C.dist(b.inicio, b.fim);
    if (v >= L) return false;
    const s0 = this._s(b, this.sob.ponto);
    const { u } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
    const lado = C.dot(C.sub(this.sob.ponto, b.inicio), u) >= 0 ? 1 : -1;
    this.colocar(b, s0 <= L / 2 ? v : L - v, lado);
    return true;
  }

  colocar(b, s, lado) {
    const r = this.chapas(b, s, lado);
    if (r.erro) { this.dica(r.erro); return; }
    this.executar(C.cmdAdicionar(r.chapas, 'Enrijecedor'));
    this.limparPrevia();
    this.dica(`Enrijecedor: ${r.chapas.length} chapa(s) ${r.chapas[0].nome.replace('ENRIJECEDOR ', '')} a ${formatar(s)} do início (Ctrl+Z desfaz)`);
  }
}

export default FerramentaEnrijecedor;
