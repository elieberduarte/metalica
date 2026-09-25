// Furo: fura a peça onde o projeto não furou — no molde da ferramenta Parafuso.
//
// Clique na face onde vai o furo: ele fica perpendicular a ela, atravessando só aquela
// parede (a mesa, a alma, a chapa). O diâmetro fica no painel de propriedades enquanto a
// ferramenta está ativa — com os diâmetros que o modelo já usa a um clique —, e também dá
// para digitar ("14", "17,5", ou o parafuso: "M12" = furo de 13).
//
// Os eixos da face (linha de centro ao longo da peça e a atravessada), o rótulo com as
// distâncias às bordas e o eixo da peça de baixo são os mesmos da ferramenta Parafuso: o
// furo prende neles do mesmo jeito.
//
// Na chapa paramétrica (a desenhada no editor) o furo entra na própria chapa (`furos`),
// como a ferramenta Chapa faz. Na peça do IFC e na barra o furo é um marcador: um cilindro
// escuro na camada Furos, tipo IfcOpeningElement, com `atributos.furo = {d, ponto, eixo,
// profundidade}`. O detalhamento lê o marcador como lê o parafuso colocado no 3D — a barra
// e a chapa ganham o furo no desenho —, mas ele não é parafuso: não entra em lista nenhuma
// nem no IFC exportado.

import { FerramentaParafuso, prisma, tamanhoDoFixador } from './parafuso.js';
import * as C from './_comum.js';

//: diâmetros usuais de furo (parafuso + 1 mm, e os oblongos da terça abertos por broca)
const DIAMETROS = [9, 11, 13, 14, 15, 17.5, 18, 20, 22, 24, 26, 28];
const num = (x) => String(Math.round(x * 10) / 10);

/** Lê "14", "17,5", "Ø14" ou "M12" (o furo do parafuso: d + 1) → diâmetro do furo. */
export function lerDiametroDoFuro(texto) {
  const t = String(texto || '').toUpperCase().replace(',', '.').replace(/\s+/g, '');
  let m = t.match(/^M(\d+(?:\.\d+)?)$/);
  if (m) return +m[1] + 1;
  m = t.match(/^[ØO]?(\d+(?:\.\d+)?)(?:MM)?$/);
  if (m) return +m[1];
  return null;
}

export class FerramentaFuro extends FerramentaParafuso {
  static id = 'furo';
  static nome = 'Furo';
  static atalho = 'F';
  static grupo = 'estrutura';
  static dica = 'Clique na face onde vai o furo · o diâmetro está no painel de propriedades';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<rect x="3" y="6" width="18" height="12" rx="1"/><circle cx="12" cy="12" r="3.2"/><path d="M12 3v2M12 19v2"/></svg>`;
  //: o último diâmetro vale para a próxima vez que a ferramenta abrir
  static diametro = null;
  static eixos = true;

  ativar() {
    this._caixas = new Map();
    // o tamanho herdado só serve à sonda da peça de baixo (o alcance do eixo)
    this.tamanho = { d: 12, L: 40, classe: '' };
    this.diametro = this.constructor.diametro || 14;
    this._atualizarDica();
  }

  get rotuloAtual() { return `Ø${num(this.diametro)}`; }

  get nomeAtual() { return `FURO ${this.rotuloAtual}`; }

  _atualizarDica() {
    this.dica(`Furo ${this.rotuloAtual}: clique na face onde ele vai (o diâmetro está no painel de propriedades)`);
    this.medida(this.rotuloAtual);
  }

  _definir(d) {
    this.diametro = d;
    this.constructor.diametro = d;
    this._atualizarDica();
  }

  onValor(texto) {
    const d = lerDiametroDoFuro(texto);
    if (!d || !(d > 0) || d > 200) { this.dica('Diâmetro do furo em mm (14, 17,5) ou o parafuso (M12 = furo de 13)'); return true; }
    this._definir(d);
    if (this.editor._agendarPaineis) this.editor._agendarPaineis('props');
    return true;
  }

  /** Diâmetros de furo que o modelo já usa: chapas paramétricas, furos marcados e os
   *  parafusos (d + 1), do mais comum para o menos: {d, n, origem}. */
  _usadosNoModelo() {
    const cont = new Map();
    const ents = this.documento && this.documento.entidades;
    if (!ents) return [];
    const soma = (d, origem) => {
      if (!(d > 0)) return;
      const k = num(d);
      const r = cont.get(k) || { d: +k, n: 0, origem };
      r.n++;
      cont.set(k, r);
    };
    for (const e of ents.values()) {
      if (e.tipo === 'chapa') { for (const f of (e.furos || [])) soma(f.diametro, 'furo de chapa'); continue; }
      if (e.tipo !== 'solido') continue;
      if (e.atributos && e.atributos.furo) soma(e.atributos.furo.d, 'furo marcado');
      else if (/^BOLT/.test(e.nome || '')) { const t = tamanhoDoFixador(e); if (t) soma(t.d + 1, 'parafuso + 1 mm'); }
    }
    return [...cont.values()].sort((a, b) => b.n - a.n).slice(0, 12);
  }

  /** Opções no painel de propriedades (chamado pelo editor). */
  painel(raiz, el) {
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Furo a fazer' }),
                   el('span', { texto: this.rotuloAtual })));
    const g = el('div', { class: 'campos' });
    const inD = el('input', { type: 'number', min: '3', step: '0.5', value: String(this.diametro), title: 'Diâmetro do furo, mm' });
    inD.addEventListener('change', () => { const d = +inD.value; if (d > 0) this._definir(d); });
    const selD = el('select', { title: 'Diâmetros usuais (parafuso + 1 mm)' });
    selD.append(el('option', { value: '', texto: 'usuais…' }));
    for (const d of DIAMETROS) selD.append(el('option', { value: String(d), texto: `Ø${num(d)}` }));
    selD.addEventListener('change', () => { if (selD.value) { this._definir(+selD.value); inD.value = selD.value; } });
    const eixos = el('input', { type: 'checkbox', title: 'Linhas de centro da face sob o cursor; o furo prende nelas e mostra a distância às bordas' });
    eixos.checked = !!this.constructor.eixos;
    eixos.addEventListener('change', () => { this.constructor.eixos = eixos.checked; this.limparPrevia(); });
    g.append(el('label', { texto: 'Diâmetro (mm)' }), inD,
             el('label', { texto: 'Usuais' }), selD,
             el('label', { texto: 'Eixos da face' }), el('span', {}, eixos, ' mostrar e prender'));
    raiz.append(g);
    const usados = this._usadosNoModelo();
    if (usados.length) {
      const box = el('div', { class: 'acoes' });
      for (const u of usados) {
        box.append(el('button', { type: 'button', texto: `Ø${num(u.d)} (${u.n})`, title: `${u.origem}: usar este diâmetro`,
          onclick: () => { this._definir(u.d); this.editor._agendarPaineis('props'); } }));
      }
      raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Já usados no modelo' }), box));
    }
    raiz.append(el('p', { class: 'nota', texto: 'Na chapa desenhada no editor o furo entra na própria chapa; na peça do IFC e na barra fica um marcador (camada Furos) que o detalhamento lê como furo — ele não conta como parafuso.' }));
  }

  /** Espessura da parede furada: a camada de vértices da peça logo atrás da face. */
  _profundidade(ent, ponto, n) {
    if (!ent) return 10;
    if (ent.tipo === 'chapa') return ent.espessura || 10;
    const pts = C.pontosDaEntidade(ent);
    let melhor = null;
    for (const q of pts) {
      const t = C.dot(C.sub(ponto, q), n);
      if (t > 0.5 && (melhor === null || t < melhor)) melhor = t;
    }
    return melhor ? Math.min(melhor, 60) : 10;
  }

  /** Cilindro do furo: entra pela face em `ponto` (normal `n`) e atravessa a parede. */
  geometria(ponto, n, prof = 10) {
    const u = C.normalizar(n);
    return prisma(C.add(ponto, C.mul(u, 0.3)), C.mul(u, -1), this.diametro / 2, 16, prof + 0.6);
  }

  onMover(p) {
    this.limparPrevia();
    if (!p || !p.entidade) return;
    const n = this.normalDoPonto(p);
    if (!n) return;
    const { ponto, extra } = this.ajustar(p, n);
    const alvo = this.documento.get(p.entidade);
    const g = this.geometria(ponto, n, this._profundidade(alvo, ponto, n));
    this.previa(C.grupo(C.gMalha(g.vertices, g.faces, '#1f2430', 0.85),
                        C.gRotulo(this.rotuloAtual, C.add(ponto, C.mul(n, 30))), ...extra));
  }

  onPonto(p) {
    if (!p || !p.entidade) { this.dica('Clique numa face de uma peça (barra, chapa, perfil)'); return; }
    const n = this.normalDoPonto(p);
    if (!n) { this.dica('Não deu para saber a face: clique no meio de uma face plana'); return; }
    const { ponto } = this.ajustar(p, n);
    const d = this.diametro;
    const alvo = this.documento.get(p.entidade);
    if (alvo && alvo.tipo === 'chapa') {
      // chapa paramétrica: o furo entra na própria chapa (é o que o IFC e a lista leem)
      const rel = C.sub(ponto, alvo.origem);
      const furos = (alvo.furos || []).map(f => ({ ...f }));
      furos.push({ x: C.dot(rel, alvo.eixo_x), y: C.dot(rel, alvo.eixo_y), diametro: d });
      this.executar(C.cmdAlterar(alvo.id, { furos }, 'Furar chapa'));
    } else {
      const prof = this._profundidade(alvo, ponto, n);
      const g = this.geometria(ponto, n, prof);
      const ent = {
        tipo: 'solido', id: C.novoId('furo'), nome: this.nomeAtual, camada: 'Furos', material: 'Cor #1f2430',
        visivel: true, bloqueada: false, grupo: '',
        vertices: g.vertices, faces: g.faces, arestas_vivas: [],
        atributos: {
          tipo_ifc: 'IfcOpeningElement', exportar: false, criado_no_editor: true,
          furo: { d, ponto: C.copiar(ponto), eixo: C.mul(C.normalizar(n), -1), profundidade: prof, peca: alvo ? alvo.id : null },
        },
      };
      this.executar(C.cmdAdicionar(ent, 'Furo'));
    }
    this.dica(`Furo ${this.rotuloAtual} feito · clique no próximo, ou troque o diâmetro no painel (Esc sai)`);
  }
}

export default FerramentaFuro;
