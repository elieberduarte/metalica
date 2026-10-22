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
    // as marcas das peças (posição, conjunto, id): o 2D do projeto do IFC acha o detalhe por elas (29/09)
    const posicoes = new Set(), conjuntos = new Set(), idsSel = [];
    // a estrutura lançada na planta (origem_2d) e as peças do galpão pré-moldado (marca@eixo): o 2D acha o
    // elemento ou o pilar nas plantas dele (R5, 30/09)
    const origem2d = new Set(), pm = new Set();
    // a planta do desenho de onde cada peça veio (origem.fonte_2d) ou, no modelo montado antes de 22/10, o papel e a
    // camada dela — a tela de fora acha o deslocamento daquela planta (a terça vai à planta das terças)
    const fontes = new Map();
    const eixos = [];                 // [[x, y], [x, y], fonte] das barras: o 2D acende a linha da peça
    for (const id of lista) {
      const e = this.documento.get(id);
      if (!e) continue;
      const mk = (e.atributos && e.atributos.marcas) || {};
      if (mk.posicao) posicoes.add(String(mk.posicao));
      if (mk.conjunto) conjuntos.add(String(mk.conjunto));
      const at = e.atributos || {};
      if (at.origem_2d) origem2d.add(String(at.origem_2d));
      if (at.pre_moldado && at.peca && at.eixo) pm.add(`${at.peca}@${at.eixo}`);
      if (idsSel.length < 200) idsSel.push(id);
      for (const p of pontosDe(e)) {
        if (!p) continue;
        x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]);
      }
      const o = (e.atributos && e.atributos.origem) || {};
      const kf = o.fonte_2d ? String(o.fonte_2d) : `?${e.papel || ''}|${e.camada || ''}`;
      fontes.set(kf, (fontes.get(kf) || 0) + 1);
      if (e.tipo === 'barra' && e.inicio && e.fim && eixos.length < 60) eixos.push([e.inicio.slice(0, 2), e.fim.slice(0, 2), kf]);
      const pc = pecaDe(e);
      if (pc) { pecas.add(pc); nomes.add(String(o.planta || pc.split('#')[0]).replace(/ \(tesoura de cima\)$/, '')); }
    }
    const caixa = isFinite(x0) ? [[x0, y0], [x1, y1]] : null;
    try {
      window.parent.postMessage({ metalica: 'sel3d', n: lista.length, caixa, nomes: [...nomes], pecas: [...pecas],
        fontes: [...fontes.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).map(x => x[0]), eixos,
        marcas: { posicoes: [...posicoes].slice(0, 50), conjuntos: [...conjuntos].slice(0, 50), ids: idsSel,
                  origem2d: [...origem2d].slice(0, 200), pm: [...pm].slice(0, 200) } }, location.origin);
    } catch (e) { /* idem */ }
  }

  /** {nome}: as peças do bloco (todas as cópias); {caixa}: as que têm o meio dentro dela, em planta */
  _selecionarDaDivisao(pedido) {
    // clicou fora no 2D (a seleção dele ficou vazia): a daqui sai também, e o destaque com ela (06/10)
    if (pedido.limpar) {
      this._daDivisao = true;
      try { if (this.selecao.ids.size) this.selecao.definir([]); } finally { this._daDivisao = false; }
      return;
    }
    let ids = [];
    if (pedido.destacar) {
      // a peça do detalhamento (posicao:, conjunto: ou ids:), como o Ver no 3D, sem o aviso comprido
      this._daDivisao = true;
      try {
        const n = this._destacar(pedido.destacar, true);
        this.dica(n ? `${n} peça(s) do 2D em destaque no 3D.` : 'Essa seleção do 2D não tem peça no modelo.');
      } finally { this._daDivisao = false; }
      return;
    }
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
