// Métodos do editor 3D: a tela dividida (/dividida) — o Desenho 2D de um lado, este 3D do outro.
//
// A seleção daqui vai para a tela de fora (a caixa em planta das peças e o nome da treliça de
// origem), que enquadra o 2D na planta ou na elevação dela. O que se seleciona no 2D volta como
// um pedido: as peças do bloco de uma elevação ("TESOURA 16"), ou as que caem numa caixa da planta
// (em mm do modelo). Fora da tela dividida nada disto roda.

import { pecaDe, eixoDoSolido } from '../nucleo/esqueleto.js';

/** os pontos (mm) de uma peça, para a caixa em planta */
function pontosDe(ent) {
  if (ent.tipo === 'barra' && ent.inicio && ent.fim) return [ent.inicio, ent.fim];
  if (ent.tipo === 'solido') return eixoDoSolido(ent);
  return [];
}

export class MetodosDivisao {
  _ligarDivisao() {
    if (window.parent === window) return;
    this.selecao.aoMudar((ids) => this._avisarDivisao(ids));
    window.addEventListener('message', (ev) => {
      if (ev.origin !== location.origin || !ev.data || ev.data.metalica !== 'selecionar3d') return;
      this._selecionarDaDivisao(ev.data);
    });
    try { window.parent.postMessage({ metalica: 'pronto3d' }, location.origin); } catch (e) { /* sem a tela de fora */ }
  }

  _avisarDivisao(ids) {
    if (this._daDivisao) return;
    const lista = [...(ids || [])].slice(0, 5000);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const nomes = new Set(), pecas = new Set();
    for (const id of lista) {
      const e = this.documento.get(id);
      if (!e) continue;
      for (const p of pontosDe(e)) {
        if (!p) continue;
        x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]);
      }
      const o = (e.atributos && e.atributos.origem) || {};
      const pc = pecaDe(e);
      if (pc) { pecas.add(pc); nomes.add(String(o.planta || pc.split('#')[0]).replace(/ \(tesoura de cima\)$/, '')); }
    }
    const caixa = isFinite(x0) ? [[x0, y0], [x1, y1]] : null;
    try {
      window.parent.postMessage({ metalica: 'sel3d', n: lista.length, caixa, nomes: [...nomes], pecas: [...pecas] }, location.origin);
    } catch (e) { /* idem */ }
  }

  /** {nome}: as peças do bloco (todas as cópias); {caixa}: as que têm o meio dentro dela, em planta */
  _selecionarDaDivisao(pedido) {
    let ids = [];
    if (pedido.nome) {
      const alvo = String(pedido.nome);
      for (const e of this.documento.entidades.values()) {
        const o = (e.atributos && e.atributos.origem) || {};
        const pl = String(o.planta || '').replace(/ \(tesoura de cima\)$/, '');
        if (pl === alvo && pecaDe(e)) ids.push(e.id);
      }
    } else if (pedido.caixa) {
      const [[x0, y0], [x1, y1]] = pedido.caixa;
      const folga = pedido.folga ?? 300;
      for (const e of this.documento.entidades.values()) {
        const pts = pontosDe(e);
        if (!pts.length) continue;
        const mx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        const my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
        if (mx >= x0 - folga && mx <= x1 + folga && my >= y0 - folga && my <= y1 + folga) ids.push(e.id);
      }
      // o que pega uma barra de treliça pega o bloco dela
      const blocos = new Set();
      for (const id of ids) for (const i of this.blocoDe(id)) blocos.add(i);
      ids = [...blocos];
    }
    this._daDivisao = true;
    try {
      if (!ids.length) {
        this.selecao.limpar ? this.selecao.limpar() : this.selecao.definir([]);
        this.dica(pedido.nome ? `Nenhuma peça de ${pedido.nome} no modelo.` : 'Nenhuma peça do modelo nessa região.');
        return;
      }
      this.selecao.definir(ids);
      this.cena.destacar(ids);
      this._destaqueAtivo = true;
      this.camera.zoomSelecao(ids);
      this.dica(pedido.nome ? `${pedido.nome}: ${ids.length} barra(s) em destaque.` : `${ids.length} peça(s) da região escolhida no 2D.`);
    } finally {
      this._daDivisao = false;
    }
  }
}
