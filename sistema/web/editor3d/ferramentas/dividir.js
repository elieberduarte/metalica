// Dividir barra (F7 do levantamento de 14/10 — o "Split" do Tekla): a emenda.
//
// Passe o mouse na barra: o ponto da divisão anda de 5 em 5 mm a partir da ponta mais perto, com a distância às duas
// pontas. Clique para dividir ali; digite a distância da ponta mais perto ("3000") ou "/3" para três partes iguais.
// Cada pedaço é uma barra com o mesmo perfil, rotação, papel e aço; o primeiro guarda o id da original (o que aponta
// para ela continua valendo), o corte e o recorte da ponta ficam no pedaço daquela ponta, e os marcadores de furo vão
// para o pedaço onde estão. A peça com marca fica com a marca a conferir (o Numerar separa). Unir: Estrutura › Unir peças.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

/** Os pedaços da barra `b` divididos nas distâncias `cortes` (mm a partir do início, crescentes): [{inicio, fim, ...}]. */
export function pedacosDaBarra(b, cortes) {
  const d = C.normalizar(C.sub(b.fim, b.inicio));
  const L = C.dist(b.inicio, b.fim);
  const s = [0, ...cortes.filter(x => x > 1 && x < L - 1).sort((x, y) => x - y), L];
  const out = [];
  for (let i = 0; i + 1 < s.length; i++) {
    if (s[i + 1] - s[i] < 1) continue;
    const p = {
      inicio: C.add(b.inicio, C.mul(d, s[i])).map(x => Math.round(x * 100) / 100),
      fim: C.add(b.inicio, C.mul(d, s[i + 1])).map(x => Math.round(x * 100) / 100),
      s0: s[i], s1: s[i + 1],
      cortes_inicio: i === 0 ? (b.cortes_inicio || []) : [],
      recorte_inicio: i === 0 ? (b.recorte_inicio || 0) : 0,
      cortes_fim: i + 2 === s.length ? (b.cortes_fim || []) : [],
      recorte_fim: i + 2 === s.length ? (b.recorte_fim || 0) : 0,
    };
    out.push(p);
  }
  return out;
}

export class FerramentaDividir extends Ferramenta {
  static id = 'dividir';
  static nome = 'Dividir barra';
  static atalho = 'Shift+D';
  static grupo = 'estrutura';
  static dica = 'Clique na barra onde ela se divide · digite a distância da ponta mais perto ou "/3" para partes iguais';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 12h7M14 12h7"/><path d="M12 5v14" stroke-dasharray="2 2"/><path d="M3 9v6M21 9v6"/></svg>`;

  ativar() { this.sob = null; this.dica(FerramentaDividir.dica); this.medida(''); }
  desativar() { this.limparPrevia(); }
  cancelar() { this.limparPrevia(); C.voltarParaSelecao(this.editor); }

  _barraSob(p) {
    const t = p && p.tela;
    const s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    const e = s && s.entidade;
    return e && e.tipo === 'barra' ? { e, ponto: p.tipoSnap && p.tipoSnap !== 'sobre_face' && p.entidade === e.id ? p.ponto : s.ponto } : null;
  }

  /** A distância (do início) do ponto da divisão: a projeção no eixo, de 5 em 5 mm a partir da ponta mais perto. */
  _distancia(b, ponto) {
    const d = C.normalizar(C.sub(b.fim, b.inicio));
    const L = C.dist(b.inicio, b.fim);
    let s = Math.max(0, Math.min(L, C.dot(C.sub(ponto, b.inicio), d)));
    if (s <= L - s) s = Math.round(s / 5) * 5; else s = L - Math.round((L - s) / 5) * 5;
    return s;
  }

  onMover(p) {
    this.limparPrevia();
    const sob = this._barraSob(p);
    this.sob = sob;
    if (!sob) return;
    const b = sob.e, L = C.dist(b.inicio, b.fim);
    const s = this._distancia(b, sob.ponto);
    const q = C.add(b.inicio, C.mul(C.normalizar(C.sub(b.fim, b.inicio)), s));
    this.previa(C.grupo(C.gPonto(q, '#c2410c'),
                        C.gRotulo(`${formatar(s)} | ${formatar(L - s)}`, q, '#c2410c')));
    this.medida(`${formatar(Math.min(s, L - s))} da ponta`);
  }

  onPonto(p) {
    const sob = this._barraSob(p);
    if (!sob) { this.dica('Clique numa barra (perfil do catálogo) onde ela se divide'); return; }
    this.dividir(sob.e, [this._distancia(sob.e, sob.ponto)]);
  }

  onValor(texto) {
    const t = String(texto).trim();
    const b = (this.sob && this.sob.e) || (C.idsSelecionados(this.editor).map(id => this.documento.get(id)).find(e => e && e.tipo === 'barra'));
    if (!b) { this.dica('Passe o mouse na barra (ou selecione-a) e digite de novo'); return true; }
    const L = C.dist(b.inicio, b.fim);
    const m = t.match(/^[/÷]\s*(\d+)$/);
    if (m) {
      const n = parseInt(m[1], 10);
      if (n < 2 || n > 100) { this.dica('Partes iguais: de /2 a /100'); return true; }
      this.dividir(b, Array.from({ length: n - 1 }, (_, i) => (L * (i + 1)) / n));
      return true;
    }
    const v = paraMilimetros(t);
    if (!isFinite(v) || v <= 0 || v >= L) return false;
    // da ponta mais perto do mouse
    const s = this.sob && this.sob.e.id === b.id ? this._distancia(b, this.sob.ponto) : 0;
    this.dividir(b, [s <= L / 2 ? v : L - v]);
    return true;
  }

  dividir(b, cortes) {
    if (!C.editavel(this.editor, b)) { this.dica(C.DICA_BLOQUEADA); return; }
    const pedacos = pedacosDaBarra(b, cortes);
    if (pedacos.length < 2) { this.dica('O ponto cai na ponta da barra: escolha um ponto no meio dela'); return; }
    const marcada = b.atributos && b.atributos.marcas && (b.atributos.marcas.posicao || b.atributos.marcas.conjunto);
    const atr = (extra) => ({ ...(b.atributos || {}), ...(marcada ? { marca_a_conferir: true } : {}), ...extra });
    const cmds = [];
    const ids = [b.id];
    const novas = [];
    pedacos.forEach((p, i) => {
      const campos = { inicio: p.inicio, fim: p.fim, cortes_inicio: p.cortes_inicio, cortes_fim: p.cortes_fim,
                       recorte_inicio: p.recorte_inicio, recorte_fim: p.recorte_fim, atributos: atr({ emenda_de: b.id }) };
      if (i === 0) { cmds.push(C.cmdAlterar(b.id, campos, 'Dividir barra')); return; }
      const c = C.clonarEntidade(b, 'b');
      Object.assign(c, campos);
      novas.push(c);
      ids.push(c.id);
    });
    if (novas.length) cmds.push(C.cmdAdicionar(novas, 'Dividir barra'));
    // os marcadores de furo da barra: cada um vai para o pedaço onde está
    const d = C.normalizar(C.sub(b.fim, b.inicio));
    for (const m of this.documento.entidades.values()) {
      const f = m.atributos && m.atributos.furo;
      if (!f || f.peca !== b.id || !Array.isArray(f.ponto)) continue;
      const s = C.dot(C.sub(f.ponto, b.inicio), d);
      const i = Math.max(0, pedacos.findIndex(p => s >= p.s0 - 0.5 && s <= p.s1 + 0.5));
      if (ids[i] !== b.id) cmds.push(C.cmdAlterar(m.id, { atributos: { ...m.atributos, furo: { ...f, peca: ids[i] } } }, 'Furo no pedaço'));
    }
    this.executar(C.cmdComposto(cmds, pedacos.length > 2 ? `Dividir em ${pedacos.length}` : 'Dividir barra'));
    this.limparPrevia();
    this.dica(`Dividida em ${pedacos.length}: ${pedacos.map(p => formatar(p.s1 - p.s0)).join(' + ')} (Ctrl+Z desfaz; Estrutura › Unir peças junta de volta)`);
  }
}

export default FerramentaDividir;
