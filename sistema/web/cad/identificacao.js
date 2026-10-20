// Identificação para modelagem (20/10/2026, o usuário: "a primeira importação poderia ser somente a leitura … ao clicar em
// identificação para modelagem o sistema faz uma varredura no desenho e tenta identificar essa planta de locação, nessa o
// usuário pode fazer os ajustes, corrigir os eixos e níveis … após esse ponto fechado aí parte para a identificação das
// tesouras … pede para o usuário posicionar nos eixos corretos … depois as terças … o usuário pede para montar o modelo 3D,
// isso sem mudar o projeto originalmente importado"). Escolhas dele: um painel de etapas na Montagem; uma varredura só
// (nucleo3d/identificacao.varrer), que preenche todas as etapas como sugestão; confirmação em ordem.
//
// O painel fica ao lado da folha (na Montagem e no Original, para ir e voltar conferindo). Cada etapa mostra o que a
// varredura achou e leva às ferramentas que já existem: os eixos e os níveis da Implantação (implantacao.js), a elevação de
// cada eixo, a folha no Original. O estado (a varredura e as etapas confirmadas) fica em metadados.montagem.identificacao.
//
// Os métodos entram na classe Montagem (montagem.js), como os de implantacao.js.

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}
async function pedir(rota, corpo) {
  const r = await fetch(rota, corpo === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) });
  const t = await r.text();
  let d = null; try { d = JSON.parse(t); } catch { /* texto */ }
  if (!r.ok || (d && d.erro)) throw new Error((d && (d.erro || d.mensagem)) || t || r.statusText);
  return d;
}
const metros = (mm) => (Math.abs(mm) / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cotaNivel = (z) => (z > 0 ? '+' : z < 0 ? '−' : '±') + metros(z);

/** As etapas, na ordem em que se confirmam. */
export const ETAPAS = [
  ['locacao', 'Locação: eixos e níveis'],
  ['tesouras', 'Tesouras nos eixos'],
  ['tercas', 'Terças'],
  ['contraventos', 'Contraventos e outras peças'],
];

export class MetodosIdentificacao {
  /** O estado da identificação: o da Montagem aberta, ou o guardado quando o Original está na tela. */
  _ident() { return (this.ativa && this.m && this.m.identificacao) || this._identCache || null; }

  _guardarIdent(dados) {
    this._identCache = dados;
    if (this.ativa && this.m) { this.m.identificacao = dados; this._gravar(); }
  }

  /** Abre o painel (na Montagem) e, na primeira vez, varre o Original. */
  async abrirIdentificacao() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    this._identAberta = true;
    this._painelIdent().hidden = false;
    if (!this._ident() || !this._ident().varredura) await this.varrerIdentificacao();
    else this._desenharIdent();
  }

  async varrerIdentificacao() {
    const p = this._painelIdent();
    p.querySelector('.ident-corpo').replaceChildren(el('div', { class: 'explica', texto: 'Varrendo o Original: folhas, planta de locação, eixos, níveis, tesouras…' }));
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/varrer`, { original: (this.m && this.m.original) || this.original });
    } catch (e) {
      p.querySelector('.ident-corpo').replaceChildren(el('div', { class: 'erro', texto: 'Não foi possível varrer o Original: ' + e.message }));
      return;
    }
    const antes = this._ident() || {};
    this._guardarIdent({ varredura: r, etapas: antes.etapas || {}, quando: new Date().toISOString() });
    this._desenharIdent();
  }

  _painelIdent() {
    if (this.painelIdent) return this.painelIdent;
    this.painelIdent = el('aside', { class: 'painel-leitura painel-ident', id: 'painel-ident', hidden: true },
      el('div', { class: 'painel-leitura-topo' }, el('b', {}, 'Identificação para modelagem'),
        el('span', {},
          el('button', { type: 'button', class: 'ident-varrer', title: 'Varre o Original de novo (as etapas confirmadas ficam)', onclick: () => this.varrerIdentificacao() }, 'Varrer de novo'),
          el('button', { type: 'button', class: 'quadro-tirar', title: 'Fechar (Desenho › Identificação para modelagem abre de novo)',
            onclick: () => { this._identAberta = false; this.painelIdent.hidden = true; } }, '×'))),
      el('div', { class: 'explica', texto: 'O Original não é mexido. Confira e acerte cada etapa, na ordem; o modelo 3D é montado no fim.' }),
      el('div', { class: 'ident-corpo' }));
    this.palco.append(this.painelIdent);
    return this.painelIdent;
  }

  /** A etapa está liberada (as anteriores confirmadas)? */
  _liberada(nome) {
    const et = (this._ident() || {}).etapas || {};
    for (const [k] of ETAPAS) { if (k === nome) return true; if (et[k] !== 'confirmada') return false; }
    return true;
  }

  _desenharIdent() {
    const p = this._painelIdent();
    const id = this._ident();
    const corpo = p.querySelector('.ident-corpo');
    if (!id || !id.varredura) { corpo.replaceChildren(); return; }
    const v = id.varredura, et = id.etapas || {};
    const botao = (texto, fazer, attrs = {}) => el('button', { type: 'button', ...attrs, onclick: async (ev) => { ev.stopPropagation(); await fazer(); } }, texto);
    const ver = (caixa, rot = 'Ver') => caixa ? botao(rot, () => this._verNoOriginal(caixa), { class: 'ident-ver', title: 'Mostra no Original' }) : null;
    const etapa = (nome, titulo, ...filhos) => {
      const conf = et[nome] === 'confirmada', livre = this._liberada(nome);
      return el('section', { class: 'ident-etapa' + (conf ? ' confirmada' : '') + (livre ? '' : ' bloqueada'), 'data-etapa': nome },
        el('h4', {}, el('span', { class: 'ident-num', texto: String(ETAPAS.findIndex(([k]) => k === nome) + 1) }), ' ', titulo,
          el('span', { class: 'ident-estado', texto: conf ? 'confirmada ✓' : livre ? 'a conferir' : 'depois da anterior' })),
        ...filhos);
    };
    const avisos = (lista) => (lista && lista.length ? el('ul', { class: 'ident-avisos' }, ...lista.map(a => el('li', { texto: a }))) : null);

    // 1. locação
    const L = v.locacao || {}, E = L.eixos || {};
    const nomes = (lst) => [...(lst || [])].map(x => x.nome).sort((a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true })).join(', ') || '—';
    const vaos = (lst) => { const ps = (lst || []).map(x => x.pos).sort((a, b) => a - b); return ps.slice(1).map((q, i) => metros(q - ps[i])).join(' · '); };
    const gravados = this._eixosDaObra && this._eixosDaObra();
    const temEixos = !!(gravados && (gravados.numeros || []).length && (gravados.letras || []).length);
    const sec1 = etapa('locacao', ETAPAS[0][1],
      L.caixa ? el('div', { class: 'ident-linha' }, el('span', { texto: L.folha ? `Folha ${L.folha} — ${L.titulo}` : L.titulo }), ver(L.caixa))
        : el('div', { class: 'ident-linha atencao', texto: 'Não achei a planta de locação sozinho: marque-a no Original.' }),
      (E.numeros || []).length || (E.letras || []).length ? el('div', { class: 'ident-linha' },
        el('span', {}, el('b', { texto: 'Eixos sugeridos: ' }), `${nomes(E.numeros)} (vãos ${vaos(E.numeros) || '—'}) · ${nomes(E.letras)} (vãos ${vaos(E.letras) || '—'})`)) : null,
      el('div', { class: 'ident-linha' }, el('span', {}, el('b', { texto: 'Níveis escritos: ' }),
        (L.niveis || []).length ? L.niveis.map(n => cotaNivel(n.cota)).join(' · ') : 'nenhum no projeto')),
      avisos(E.avisos),
      temEixos ? el('div', { class: 'ident-linha ok', texto: `Gravados na Implantação: ${nomes(gravados.numeros)} e ${nomes(gravados.letras)}.` }) : null,
      el('div', { class: 'ident-botoes' },
        (E.numeros || []).length || (E.letras || []).length ? botao('Conferir e gravar os eixos…', () => this._conferirEixosIdent(), { class: 'primario' }) : null,
        botao(L.caixa ? 'Marcar outra área…' : 'Marcar a planta de locação…', () => this._marcarLocacaoIdent(), { title: 'No Original: dois cliques em volta da planta com os eixos' }),
        botao('Níveis…', () => this._niveisIdent()),
        botao('Confirmar a locação ✓', () => this._confirmarIdent('locacao'), { class: 'ident-confirmar', disabled: temEixos ? undefined : true,
          title: temEixos ? 'Fecha a etapa: as tesouras vão para estes eixos' : 'Grave os eixos primeiro (Conferir e gravar os eixos…)' })));

    // 2. tesouras
    const livreT = this._liberada('tesouras');
    const linhasT = (v.tesouras || []).map(t => el('div', { class: 'ident-tesoura' },
      el('div', { class: 'ident-linha' }, el('span', {}, el('b', { texto: t.tipo }),
        t.eixos.length ? ` nos eixos ${t.eixos.join(', ')}` : ' — não está na locação'), ver(t.vista && t.vista.caixa)),
      t.vista ? el('div', { class: 'ident-sub', texto: `vista: folha ${t.vista.folha} (${t.vista.mostra || t.vista.titulo})` +
        (t.folhas.length > 1 ? ` · também nas folhas ${t.folhas.slice(1).map(f => f.folha).join(', ')}` : '') }) : null,
      livreT && t.eixos.length ? el('div', { class: 'ident-botoes' }, ...t.eixos.slice(0, 6).map(n => botao(`Elevação ${n}`, () => this.abrirElevacao(n, 'numero'),
        { title: `Abre a elevação do eixo ${n}: cole ali a tesoura ${t.tipo} copiada da folha ${t.vista ? t.vista.folha : ''} (Copiar no Original, Ctrl+V por 2 pontos)` }))) : null));
    const sec2 = etapa('tesouras', ETAPAS[1][1],
      linhasT.length ? linhasT : el('div', { class: 'explica', texto: 'Nenhuma tesoura achada pelos títulos (T1, T2…).' }),
      livreT ? el('div', { class: 'explica', texto: 'Por enquanto: Ver mostra a vista no Original; copie a tesoura e cole na elevação de cada eixo (Ctrl+V por 2 pontos). O posicionamento automático vem na próxima etapa do sistema.' }) : null,
      livreT ? el('div', { class: 'ident-botoes' }, botao('Confirmar as tesouras ✓', () => this._confirmarIdent('tesouras'), { class: 'ident-confirmar' })) : null);

    // 3 e 4. terças, contraventos e o resto: as folhas achadas
    const folhas = (lst) => (lst || []).map(f => el('div', { class: 'ident-linha' }, el('span', { texto: `Folha ${f.folha} — ${f.titulo}` }), ver(f.caixa)));
    const sec3 = etapa('tercas', ETAPAS[2][1], ...folhas(v.tercas),
      el('div', { class: 'explica', texto: 'A leitura das terças sobre os eixos gravados vem na próxima etapa do sistema.' }));
    const sec4 = etapa('contraventos', ETAPAS[3][1], ...folhas(v.contraventos), ...folhas(v.outras));
    const montar = el('section', { class: 'ident-etapa ident-montar' },
      el('h4', {}, 'Montar o modelo 3D'),
      el('div', { class: 'explica', texto: 'Com as etapas confirmadas, o modelo 3D sai do que foi identificado; o Original fica para as conferências.' }),
      el('div', { class: 'ident-botoes' }, botao('Montar o modelo 3D', () => {}, { class: 'primario', disabled: true, title: 'Vem na próxima etapa do sistema' })));
    corpo.replaceChildren(sec1, sec2, sec3, sec4, montar);
  }

  async _verNoOriginal(caixa) {
    await this._gravarJa();
    if (this.cad.nomeDesenho !== ((this.m && this.m.original) || this.original)) await this.ir('original');
    // com folga à direita, do tamanho do painel: a folha fica à vista ao lado dele, não embaixo
    const [[x0, y0], [x1, y1]] = caixa;
    const larg = (this.cad.tela && this.cad.tela.canvas && this.cad.tela.canvas.clientWidth) || 1200;
    const painel = this.painelIdent && !this.painelIdent.hidden ? this.painelIdent.offsetWidth + 30 : 0;
    const k = painel ? Math.min(1.5, painel / Math.max(300, larg - painel)) : 0;
    this.cad.tela.enquadrar([[x0, y0], [x1 + (x1 - x0) * k, y1]]);
    this.cad.dica('No Original (só leitura). A aba Montagem volta à folha da montagem; o painel continua aberto.');
  }

  /** Os eixos sugeridos no diálogo da Implantação (o mesmo do "Ler de uma área"): o usuário confere os vãos e grava. */
  async _conferirEixosIdent() {
    if (!this.ativa) await this.ir('montagem');
    const E = (((this._ident() || {}).varredura || {}).locacao || {}).eixos || {};
    await this.dialogoEixos({ numeros: E.numeros || [], letras: E.letras || [], avisos: E.avisos || [] });
    this._desenharIdent();
  }

  /** O projeto sem folha com carimbo (ou a folha errada): o usuário marca a planta de locação no Original. */
  async _marcarLocacaoIdent() {
    await this._gravarJa();
    await this.ir('original');
    if (this.cad.nomeDesenho === 'montagem') return;
    const caixa = await this._marcarArea('Locação: marque a planta com os eixos — dois cantos ou uma janela em volta dela · Esc cancela');
    let r = null;
    if (caixa) {
      try {
        r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/varrer`, { original: this.cad.nomeDesenho, caixa });
      } catch (e) { this.cad.aviso('Não consegui ler os eixos dessa área: ' + e.message, 'atencao', 12000); }
    }
    await this.ir('montagem');
    if (!r) return;
    const id = this._ident() || { varredura: {}, etapas: {} };
    const loc = { ...(id.varredura.locacao || {}), folha: null, titulo: 'a área marcada no Original', caixa: r.caixa, eixos: r.eixos };
    this._guardarIdent({ ...id, varredura: { ...id.varredura, locacao: loc } });
    this._desenharIdent();
    if ((r.eixos.numeros || []).length || (r.eixos.letras || []).length) await this._conferirEixosIdent();
  }

  /** Os níveis: os escritos no projeto entram como sugestão (se o projeto ainda não tem níveis) e o diálogo abre. */
  async _niveisIdent() {
    if (!this.ativa) await this.ir('montagem');
    const sug = ((((this._ident() || {}).varredura || {}).locacao || {}).niveis) || [];
    const atuais = await this._niveis();
    if (sug.length && atuais.length <= 1) {
      const lista = [{ nome: '±0,00', z: 0 }, ...sug.filter(n => n.cota !== 0).map(n => ({ nome: `Nível ${cotaNivel(n.cota)}`, z: n.cota }))];
      try { await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/niveis`, { niveis: lista }); } catch (e) { this.cad.aviso('Não gravei os níveis sugeridos: ' + e.message, 'atencao'); }
    }
    await this.editarNiveis();
    this._desenharIdent();
  }

  _confirmarIdent(nome) {
    if (!this.ativa) { this.cad.aviso('Volte à Montagem para confirmar a etapa.', 'atencao'); return; }
    const id = this._ident();
    this._guardarIdent({ ...id, etapas: { ...(id.etapas || {}), [nome]: 'confirmada' } });
    this._desenharIdent();
  }
}
