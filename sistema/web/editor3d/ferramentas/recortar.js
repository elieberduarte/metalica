// Recortar (F8 do levantamento de 14/10 — o "Part cut / Fitting" do Tekla, o "Coping" do Advance): o recorte de
// encaixe da mesa onde a viga chega no pilar ou na outra viga, e o chanfro de ponta para a solda.
//
// 1. Clique na barra a recortar, perto da ponta.
// 2. Clique na peça em que ela encaixa: a ferramenta acha onde a peça invade a seção dela perto da ponta e faz o
//    recorte de cima e/ou de baixo, com a folga do painel (10 mm). Ou digite "comprimento;altura" (mm) para o lado do
//    painel, ou "ch10" para um chanfro de 10 mm a 45° naquele lado. Delete tira os recortes da ponta.
// O recorte vai em `recortes` da barra ({ponta, lado, comprimento, altura}) — o 3D, o IFC (bloco tirado), o peso e o
// detalhamento o levam; o chanfro é um plano a mais em `cortes_*` (como o Encaixar). Ctrl+Z desfaz.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
import { baseDaBarra } from '../nucleo/documento.js';

const LADOS = [['cima', 'em cima'], ['baixo', 'embaixo'], ['esquerda', 'à esquerda'], ['direita', 'à direita']];
const DIR = { cima: [0, 1], baixo: [0, -1], esquerda: [1, 0], direita: [-1, 0] };

function noPoligono(p, poli) {
  let dentro = false;
  for (let i = 0, n = poli.length; i < n; i++) {
    const [x1, y1] = poli[i], [x2, y2] = poli[(i + 1) % n];
    if ((y1 > p[1]) !== (y2 > p[1]) && p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1)) dentro = !dentro;
  }
  return dentro;
}

/** A seção do perfil com os vazios: {ext, furos} em [x, y]. */
export function secaoComVazios(cena, perfil) {
  try {
    const f = cena._secaoDoPerfil(perfil);
    const e = f.extractPoints(12);
    return { ext: e.shape.map(p => [p.x, p.y]), furos: (e.holes || []).map(h => h.map(p => [p.x, p.y])) };
  } catch { return null; }
}

/** O ponto (no mundo) está dentro da barra `b` (a seção dela ao longo do eixo)? */
function dentroDaBarra(b, sec, q) {
  const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
  const r = C.sub(q, b.inicio);
  const z = C.dot(r, t);
  if (z < (b.recorte_inicio || 0) - 0.01 || z > C.dist(b.inicio, b.fim) - (b.recorte_fim || 0) + 0.01) return false;
  const p = [C.dot(r, u), C.dot(r, v)];
  return noPoligono(p, sec.ext) && !sec.furos.some(h => noPoligono(p, h));
}

/**
 * Os recortes que a ponta `ponta` da barra `a` precisa para encaixar na barra `b`: a parte de `b` que invade a metade
 * de cima (e a de baixo) da seção de `a` perto da ponta, com `folga`. [{ponta, lado, comprimento, altura}].
 */
export function recortesPelaPeca(a, ponta, b, secA, secB, folga = 10) {
  const L = C.dist(a.inicio, a.fim);
  const { t, u, v } = baseDaBarra(a.inicio, a.fim, a.rotacao || 0);
  const xs = secA.ext.map(p => p[0]), ys = secA.ext.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const ym = (y0 + y1) / 2;
  const noMundo = (x, y, z) => C.add(a.inicio, C.add(C.mul(u, x), C.add(C.mul(v, y), C.mul(t, z))));
  const amostrasX = [x0 + 0.5, (x0 + x1) / 2, x1 - 0.5, x0 + (x1 - x0) * 0.25, x0 + (x1 - x0) * 0.75];
  const ocupa = (y, z) => amostrasX.some(x => dentroDaBarra(b, secB, noMundo(x, y, z)));
  const alcance = Math.min(L - 1, 800);
  const passo = 2;
  const out = [];
  for (const [lado, faixa] of [['cima', [ym, y1]], ['baixo', [y0, ym]]]) {
    // a distância (a partir da ponta) até onde `b` aparece nessa metade, e a altura que ela ocupa
    let zMin = null, yLim = null;
    for (let d = 0; d <= alcance; d += passo) {
      const z = ponta === 'fim' ? L - d : d;
      for (let y = faixa[0]; y <= faixa[1] + 1e-9; y += passo) {
        if (!ocupa(y, z)) continue;
        zMin = d;
        if (lado === 'cima') yLim = yLim === null ? y : Math.min(yLim, y);
        else yLim = yLim === null ? y : Math.max(yLim, y);
      }
    }
    if (zMin === null) continue;
    const altura = lado === 'cima' ? y1 - yLim + folga : yLim - y0 + folga;
    if (altura >= y1 - y0 - 1) continue;                     // tiraria a seção inteira: não é recorte
    out.push({ ponta, lado, comprimento: Math.round((zMin + folga) * 10) / 10, altura: Math.round(altura * 10) / 10 });
  }
  return out;
}

/** O plano do chanfro de `a` mm a 45° no lado `lado` da ponta, no formato de `cortes_*` ({normal, ponto} no mundo,
 *  o ponto relativo ao nó). */
export function planoDoChanfro(b, ponta, lado, a, secA) {
  const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
  const [dx, dy] = DIR[lado];
  const m = Math.max(...secA.ext.map(p => p[0] * dx + p[1] * dy));    // a face daquele lado
  const sinal = ponta === 'fim' ? 1 : -1;
  const n = C.normalizar(C.add(C.add(C.mul(u, dx), C.mul(v, dy)), C.mul(t, sinal)));
  const ponto = C.add(C.mul(u, dx * (m - a)), C.mul(v, dy * (m - a)));
  return { normal: n.map(x => Math.round(x * 1e6) / 1e6), ponto: ponto.map(x => Math.round(x * 1e4) / 1e4) };
}

export class FerramentaRecortar extends Ferramenta {
  static id = 'recortar';
  static nome = 'Recortar';
  static atalho = 'Shift+R';
  static grupo = 'estrutura';
  static dica = 'Clique na barra a recortar, perto da ponta';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 7h12v4h6v6H3Z"/><path d="M15 7v4" stroke-dasharray="2 1.5"/><path d="M15 11h6" stroke-dasharray="2 1.5"/></svg>`;
  static lado = 'cima';
  static folga = 10;

  ativar() { this.barra = null; this.ponta = null; this.dica(FerramentaRecortar.dica); this.medida(''); }
  desativar() { this.limparPrevia(); }

  cancelar() {
    if (this.barra) { this.barra = null; this.limparPrevia(); this.selecao.limpar(); this.dica(FerramentaRecortar.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  teclaDeValor(k) { return !!this.barra && /^[0-9cC]$/.test(k); }

  painel(raiz, el) {
    const F = this.constructor;
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Recortar' }),
                   el('span', { texto: this.barra ? `ponta ${this.ponta === 'inicio' ? 'do início' : 'do fim'}` : 'escolha a barra' })));
    const g = el('div', { class: 'campos' });
    const s = el('select', { title: 'O lado do recorte digitado ("comprimento;altura") e do chanfro ("ch10")' });
    for (const [v, t] of LADOS) s.append(el('option', { value: v, texto: t }));
    s.value = F.lado;
    s.addEventListener('change', () => { F.lado = s.value; });
    const f = el('input', { type: 'number', min: '0', step: '1', value: String(F.folga), style: 'width:5em',
                            title: 'Folga do recorte automático, em volta da peça em que a barra encaixa (mm)' });
    f.addEventListener('change', () => { F.folga = Math.max(0, +f.value || 0); });
    g.append(el('label', { texto: 'Lado' }), s, el('label', { texto: 'Folga (mm)' }), f);
    raiz.append(g);
    raiz.append(el('p', { class: 'nota', texto: 'Clique na peça em que a barra encaixa: o recorte sai sozinho (de cima e/ou de baixo). Ou digite "comprimento;altura" para o lado escolhido, "ch10" para chanfro de 10 mm a 45°; Delete tira os recortes da ponta.' }));
  }

  _sob(p) {
    const t = p && p.tela;
    const s = t ? this.editor.selecao.sob(t[0], t[1]) : null;
    return s && s.entidade ? { e: s.entidade, ponto: s.ponto } : null;
  }

  _secao(perfil) { return secaoComVazios(this.editor && this.editor.cena, perfil); }

  /** Aplica os recortes `novos` na ponta (troca os do mesmo lado). */
  _aplicar(b, novos, rotulo) {
    const ficam = (b.recortes || []).filter(r => !(r.ponta === this.ponta && novos.some(n => n.lado === r.lado)));
    const campos = C.marcarParaConferir(b, { recortes: ficam.concat(novos) });
    this.executar(C.cmdAlterar(b.id, campos, rotulo));
    this.dica(`${rotulo}: ${novos.map(n => `${n.lado} ${formatar(n.comprimento)} × ${formatar(n.altura)}`).join(' · ')} — clique em outra barra (Ctrl+Z desfaz)`);
    this.barra = null;
    this.selecao.limpar();
    this.limparPrevia();
  }

  onMover(p) {
    if (!this.barra) return;
    this.limparPrevia();
    const sob = this._sob(p);
    const b = this.documento.get(this.barra);
    if (!sob || !b || sob.e.id === b.id || sob.e.tipo !== 'barra') return;
    const recs = recortesPelaPeca(b, this.ponta, sob.e, this._secao(b.perfil), this._secao(sob.e.perfil), this.constructor.folga);
    if (!recs.length) { this.medida('nenhuma invasão perto da ponta'); return; }
    this.medida(recs.map(r => `${r.lado} ${formatar(r.comprimento)} × ${formatar(r.altura)}`).join(' · '));
    // a prévia: as caixas dos recortes na ponta
    const sec = this._secao(b.perfil);
    const xs = sec.ext.map(q => q[0]), ys = sec.ext.map(q => q[1]);
    const X0 = Math.min(...xs), X1 = Math.max(...xs), Y0 = Math.min(...ys), Y1 = Math.max(...ys);
    const L = C.dist(b.inicio, b.fim);
    const { t, u, v } = baseDaBarra(b.inicio, b.fim, b.rotacao || 0);
    const P = (x, y, z) => C.add(b.inicio, C.add(C.mul(u, x), C.add(C.mul(v, y), C.mul(t, z))));
    const g = C.grupo();
    for (const r of recs) {
      const ya = r.lado === 'cima' ? Y1 - r.altura : Y0, yb = r.lado === 'cima' ? Y1 : Y0 + r.altura;
      const za = this.ponta === 'fim' ? L - r.comprimento : 0, zb = this.ponta === 'fim' ? L : r.comprimento;
      for (const z of [za, zb]) g.add(C.gLinha([P(X0, ya, z), P(X1, ya, z), P(X1, yb, z), P(X0, yb, z)], '#c2410c', { fechada: true }));
      for (const [x, y] of [[X0, ya], [X1, ya], [X1, yb], [X0, yb]]) g.add(C.gLinha([P(x, y, za), P(x, y, zb)], '#c2410c'));
    }
    this.previa(g);
  }

  onPonto(p) {
    const sob = this._sob(p);
    if (!this.barra) {
      if (!sob || sob.e.tipo !== 'barra') { this.dica('Clique numa barra (perfil do catálogo), perto da ponta a recortar'); return; }
      if (!C.editavel(this.editor, sob.e)) { this.dica(C.DICA_BLOQUEADA); return; }
      this.barra = sob.e.id;
      this.ponta = C.dist(sob.ponto, sob.e.inicio) <= C.dist(sob.ponto, sob.e.fim) ? 'inicio' : 'fim';
      this.selecao.definir([sob.e.id]);
      this.dica('Clique na peça em que ela encaixa (recorte automático) · ou digite "comprimento;altura" ou "ch10" · Delete tira os recortes · Esc volta');
      if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
      return;
    }
    const b = this.documento.get(this.barra);
    if (!sob || sob.e.id === this.barra || sob.e.tipo !== 'barra') { this.dica('Clique na OUTRA barra, a em que esta encaixa'); return; }
    const recs = recortesPelaPeca(b, this.ponta, sob.e, this._secao(b.perfil), this._secao(sob.e.perfil), this.constructor.folga);
    if (!recs.length) { this.dica('Essa peça não invade a seção perto da ponta: nada a recortar (estenda a barra até ela antes?)'); return; }
    this._aplicar(b, recs, 'Recorte de encaixe');
  }

  onValor(texto) {
    if (!this.barra) return false;
    const b = this.documento.get(this.barra);
    const t = String(texto).trim().toLowerCase();
    const ch = t.match(/^ch\s*(.+)$/);
    if (ch) {
      const a = paraMilimetros(ch[1]);
      if (!(a > 0)) return false;
      const k = this.ponta === 'inicio' ? 'cortes_inicio' : 'cortes_fim';
      const plano = planoDoChanfro(b, this.ponta, this.constructor.lado, a, this._secao(b.perfil));
      // a ponta reta continua: o chanfro soma ao que ela já tem (sem plano, a ponta é o nó)
      const antes = (b[k] || []).length ? b[k] : [{ normal: C.normalizar(C.mul(C.sub(b.fim, b.inicio), this.ponta === 'fim' ? 1 : -1)), ponto: [0, 0, 0] }];
      this.executar(C.cmdAlterar(b.id, C.marcarParaConferir(b, { [k]: antes.concat([plano]) }), 'Chanfro de ponta'));
      this.dica(`Chanfro de ${formatar(a)} a 45° ${LADOS.find(l => l[0] === this.constructor.lado)[1]} — clique em outra barra (Ctrl+Z desfaz)`);
      this.barra = null;
      this.selecao.limpar();
      return true;
    }
    const m = t.split(/[;x×]/).map(paraMilimetros);
    if (m.length !== 2 || !m.every(v => v > 0)) return false;
    this._aplicar(b, [{ ponta: this.ponta, lado: this.constructor.lado, comprimento: m[0], altura: m[1] }], 'Recorte');
    return true;
  }

  onTecla(ev) {
    if (this.barra && (ev.key === 'Delete' || ev.key === 'Backspace')) {
      const b = this.documento.get(this.barra);
      this.executar(C.cmdAlterar(b.id, { recortes: (b.recortes || []).filter(r => r.ponta !== this.ponta) }, 'Tirar os recortes da ponta'));
      this.dica('Recortes da ponta tirados (o chanfro sai pelo Delete do Encaixar). Clique em outra barra');
      this.barra = null;
      this.selecao.limpar();
      return true;
    }
    return false;
  }
}

export default FerramentaRecortar;
