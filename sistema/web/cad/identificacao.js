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
//
// Fase 3 (tesouras): "Colar nos eixos…" pega o desenho da tesoura na folha da vista geral (o servidor acha o grupo de
// barras: identificacao.tesoura_da_folha), cola na elevação do primeiro eixo sugerido em tamanho real — centrado entre os
// eixos com letra, o apoio no nível de apoio, sem esticar — e abre o "Tesoura…" da elevação com a marca e os eixos
// sugeridos marcados; o usuário confere os perfis e lança.
//
// Fase 4 (terças): "Lançar as terças" lê a planta de terças (identificacao.tercas_da_planta: a malha dela casada com a da
// locação, a cota de cada terça pelo corte dela na vista da tesoura, a marca e o perfil pela tabela das folhas de
// terças) e lança cada peça na Implantação como viga de aço com papel "terça", apoiada pela face de baixo; o 3D vem junto
// pela planta. Lançar de novo troca as terças lançadas antes.

import { criar } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoComposto, ComandoRemover } from './nucleo/comandos.js';

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
    const lancadas = (this.ativa && this.m && this.m.tipos) || this._tiposCache || {};
    if (this.ativa && this.m) this._tiposCache = this.m.tipos || {};
    const linhasT = (v.tesouras || []).map(t => {
      const lanc = lancadas[t.tipo];
      return el('div', { class: 'ident-tesoura' + (lanc ? ' lancada' : ''), 'data-tipo': t.tipo },
        el('div', { class: 'ident-linha' }, el('span', {}, el('b', { texto: t.tipo }),
          t.eixos.length ? ` nos eixos ${t.eixos.join(', ')}` : ' — não está na locação', lanc ? el('span', { class: 'ident-ok', texto: ' · lançada ✓' }) : null),
          ver(t.vista && t.vista.caixa)),
        t.vista ? el('div', { class: 'ident-sub', texto: `vista: folha ${t.vista.folha} (${t.vista.mostra || t.vista.titulo})` +
          (t.folhas.length > 1 ? ` · também nas folhas ${t.folhas.slice(1).map(f => f.folha).join(', ')}` : '') }) : null,
        livreT && t.vista ? el('div', { class: 'ident-botoes' },
          botao(t.eixos.length ? `${lanc ? 'Colar de novo' : 'Colar'} nos eixos ${t.eixos.join(', ')}…` : 'Colar numa elevação…', () => this._colarTesouraIdent(t),
            { class: lanc ? '' : 'primario', title: `Cola a ${t.tipo} da folha ${t.vista.folha} na elevação do eixo ${t.eixos[0] || '(escolha)'}, em tamanho real, e abre o Tesoura… com os eixos marcados` }),
          lanc && t.eixos.length ? botao(`Elevação ${t.eixos[0]}`, () => this.abrirElevacao(t.eixos[0], 'numero')) : null) : null);
    });
    const faltam = (v.tesouras || []).filter(t => t.eixos.length && !lancadas[t.tipo]).map(t => t.tipo);
    const sec2 = etapa('tesouras', ETAPAS[1][1],
      linhasT.length ? linhasT : el('div', { class: 'explica', texto: 'Nenhuma tesoura achada pelos títulos (T1, T2…).' }),
      livreT ? el('div', { class: 'explica', texto: 'Colar põe a tesoura na elevação do primeiro eixo, em tamanho real, centrada entre os eixos com letra e no nível de apoio; no Tesoura… confira os perfis e os eixos e lance.' }) : null,
      livreT ? el('div', { class: 'ident-botoes' }, botao('Confirmar as tesouras ✓', () => this._confirmarIdent('tesouras'), { class: 'ident-confirmar',
        title: faltam.length ? `Ainda não lançadas: ${faltam.join(', ')} (dá para confirmar assim mesmo)` : 'Fecha a etapa' })) : null);

    // 3 e 4. terças, contraventos e o resto: as folhas achadas
    const folhas = (lst) => (lst || []).map(f => el('div', { class: 'ident-linha' }, el('span', { texto: `Folha ${f.folha} — ${f.titulo}` }), ver(f.caixa)));
    const planta = this._plantaDeTercas(v);
    const livre3 = this._liberada('tercas');
    const nTercas = this.ativa ? [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca').length : (id.tercas || {}).n || 0;
    const resT = id.tercas || {};
    const sec3 = etapa('tercas', ETAPAS[2][1], ...folhas(v.tercas),
      planta ? el('div', { class: 'ident-sub', texto: `a planta: folha ${planta.folha}; perfil, marca e comprimento pela tabela das folhas de terças` }) : el('div', { class: 'ident-linha atencao', texto: 'Nenhuma folha com PLANTA DE TERÇAS no título.' }),
      nTercas ? el('div', { class: 'ident-linha ok', texto: `${nTercas} terça(s) lançada(s) na Implantação` + (resT.resumo ? ` (${resT.resumo})` : '') + '.' }) : null,
      avisos(resT.avisos),
      livre3 && planta ? el('div', { class: 'ident-botoes' },
        botao(nTercas ? 'Lançar de novo' : 'Lançar as terças nos eixos', () => this._lancarTercasIdent(), { class: nTercas ? '' : 'primario',
          title: 'Lê a planta de terças, põe cada peça nos eixos gravados, na cota do corte dela na vista da tesoura, e lança na Implantação' }),
        botao('Confirmar as terças ✓', () => this._confirmarIdent('tercas'), { class: 'ident-confirmar', disabled: nTercas ? undefined : true })) : null);
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

  /** O nível do apoio das tesouras: o nível do projeto com "apoio" no nome; senão a pergunta (uma vez), que vira nível. */
  async _apoioIdent() {
    const niveis = await this._niveis();
    const ap = niveis.find(n => /apoio/i.test(n.nome));
    if (ap) return ap.z;
    const id = this._ident() || {};
    const alto = [...niveis].sort((a, b) => b.z - a.z)[0];
    const campo = el('input', { type: 'text', value: alto && alto.z ? String(alto.z) : '', placeholder: 'ex.: 6000', spellcheck: 'false' });
    campo.addEventListener('keydown', ev => ev.stopPropagation());
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Em que cota as tesouras apoiam (o topo dos pilares, a chapa de apoio)? O projeto não escreve esse nível. Ele vira o nível "Apoio das tesouras" do projeto (muda depois em Níveis…).' }),
      el('label', {}, 'Apoio das tesouras (mm) ', campo));
    if (await this.cad.dialogo({ titulo: 'Nível do apoio das tesouras', corpo, ok: 'Gravar' }) !== 'ok') return null;
    const z = parseFloat(String(campo.value).replace(',', '.'));
    if (!isFinite(z)) { this.cad.aviso('A cota não foi entendida: use mm (6000).', 'atencao'); return null; }
    const lista = [...niveis.map(n => ({ nome: n.nome, z: n.z })), { nome: 'Apoio das tesouras', z }];
    if (!lista.some(n => n.z === 0)) lista.push({ nome: '±0,00', z: 0 });
    await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/niveis`, { niveis: lista });
    this.cad._niveisProjeto = null;
    this._niveisCache = await this._niveis();
    await this.refazerQuadrosDaObra();
    if (typeof this._renovarCaixasNiveis === 'function') this._renovarCaixasNiveis();
    this._guardarIdent({ ...id, apoio: z });
    return z;
  }

  /** Fase 3: a tesoura da folha da vista geral colada na elevação do primeiro eixo e o Tesoura… com os eixos sugeridos. */
  async _colarTesouraIdent(t) {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    const z = await this._apoioIdent();
    if (z == null) return;
    const original = this.m.original || this.original;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/tesoura`, { original, caixa: t.vista.caixa });
    } catch (e) { this.cad.aviso(`Não consegui pegar a ${t.tipo} da folha ${t.vista.folha}: ${e.message}`, 'erro', 0); return; }
    if (!(r.entidades || []).length) { this.cad.aviso(`A folha ${t.vista.folha} não tem o desenho da ${t.tipo}: ${(r.avisos || []).join(' ')}`, 'atencao', 0); return; }
    // a elevação do primeiro eixo sugerido (sem eixo na locação: o primeiro numerado — o usuário marca os eixos no Tesoura…)
    const eixo = t.eixos[0] || ((this._familia('numero')[0] || {}).nome);
    if (!eixo) { this.cad.aviso('Grave os eixos da locação primeiro.', 'atencao'); return; }
    const q = await this.abrirElevacao(eixo, 'numero');
    const cruz = this._cruzamDaElevacao(q);
    const us = cruz.map(c => c.u);
    const uMeio = us.length ? (Math.min(...us) + Math.max(...us)) / 2 : r.largura / 2;
    const vao = us.length > 1 ? Math.max(...us) - Math.min(...us) : null;
    // a cópia como a do Ctrl+C no Original (um ponto de referência: o meio de baixo), colada em tamanho real
    this._prepararCopia(r.entidades.map(e => criar(e)));
    this._copiaPendente.kOrig = r.escala_original || 100;
    this._copiaPendente.desenho = original;
    this._guardarCopia([r.ref]);
    this._colar([this._paraPapel(q, [uMeio, z])], false);
    const sobra = vao != null ? (r.largura - vao) / 2 : null;
    const casa = sobra == null ? '' : Math.abs(sobra) < 5 ? `, o mesmo vão dos eixos ${cruz[0].nome}–${cruz[cruz.length - 1].nome}`
      : `; entre ${cruz[0].nome} e ${cruz[cruz.length - 1].nome} há ${metros(vao)} m — centrada, ${metros(Math.abs(sobra))} m ${sobra > 0 ? 'para fora' : 'para dentro'} de cada lado (confira no projeto)`;
    this.cad.aviso(`${t.tipo} da folha ${t.vista.folha} colada na Elevação ${eixo}: ${r.barras} barras, ${metros(r.largura)} m × ${metros(r.altura)} m${casa}. Confira no Tesoura… e lance.`, sobra && Math.abs(sobra) > 5 ? 'atencao' : 'info', 16000);
    const lancou = await this.tesouraDaElevacao(q, { marca: t.tipo, eixos: t.eixos.length ? t.eixos : [eixo] });
    if (lancou) this._tiposCache = this.m.tipos || {};
    this._desenharIdent();
  }

  /** A folha da planta de terças: a com PLANTA no título (as outras de terças são detalhes de peça). */
  _plantaDeTercas(v) {
    const fs = (v.tercas || []).filter(f => f.caixa);
    return fs.find(f => /PLANTA/i.test(f.titulo)) || null;
  }

  /** Fase 4: as terças da planta de terças lançadas na Implantação, nos eixos gravados. */
  async _lancarTercasIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    const id = this._ident(), v = id.varredura, planta = this._plantaDeTercas(v);
    const qi = this._quadroImplantacao();
    if (!planta || !qi || !qi.mapa) { this.cad.aviso('Falta a planta de terças ou a Implantação com os eixos.', 'atencao'); return; }
    const apoio = await this._apoioIdent();
    if (apoio == null) return;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/tercas`, {
        original: this.m.original || this.original, caixa: planta.caixa, locacao: v.locacao, folhas: v.folhas, apoio,
        tesouras: (v.tesouras || []).filter(t => t.vista && t.eixos.length).map(t => ({ tipo: t.tipo, eixos: t.eixos, caixa: t.vista.caixa })) });
    } catch (e) { this.cad.aviso('Não consegui ler a planta de terças: ' + e.message, 'erro', 0); return; }
    const pecas = (r.pecas || []).filter(pc => pc.g_a != null && pc.g_b != null);
    if (!pecas.length) { this.cad.aviso('Nenhuma terça lida na planta: ' + (r.avisos || []).join(' '), 'atencao', 0); return; }
    const novas = pecas.map(pc => criar({ tipo: 'linha', camada: 'ESTRUTURA', a: this._paraPapel(qi, [pc.g_a, pc.p]), b: this._paraPapel(qi, [pc.g_b, pc.p]),
      atributos: { elemento: 'viga', material: 'aco', papel: 'terça', identificacao: 'terca', marca: pc.marca || 'T.C', quadro: qi.id,
        secao: { perfil: pc.perfil || 'U 127×50×2,25 (FF)', aco: 'ASTM A36' }, nivel_topo: pc.z_pe != null ? pc.z_pe : apoio, alinhamento: 'base',
        eixos: [pc.eixo_a, pc.eixo_b], u: pc.u } }));
    const antes = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca').map(e => e.id);
    const cmds = [];
    if (antes.length) cmds.push(new ComandoRemover(antes, 'Terças lançadas antes'));
    cmds.push(new ComandoAdicionar(novas, `Terças (${novas.length})`));
    if (!this.cad.doc.camadas.has('ESTRUTURA') && this.cad._garantirCamadaEstrutura) this.cad._garantirCamadaEstrutura();
    this.cad.executar(cmds.length > 1 ? new ComandoComposto(cmds, `Terças (${novas.length})`) : cmds[0]);
    const cont = {};
    for (const pc of pecas) cont[pc.marca || '?'] = (cont[pc.marca || '?'] || 0) + 1;
    const resumo = Object.entries(cont).sort((a, b) => a[0].localeCompare(b[0], 'pt-BR', { numeric: true })).map(([m, n]) => `${n} ${m}`).join(', ');
    this._guardarIdent({ ...this._ident(), tercas: { n: novas.length, resumo, avisos: r.avisos || [] } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`${novas.length} terça(s) lançada(s) na Implantação: ${resumo}. O 3D acompanha a planta; Ctrl+Z desfaz.`, (r.avisos || []).length ? 'atencao' : 'info', 14000);
    this._desenharIdent();
  }

  _confirmarIdent(nome) {
    if (!this.ativa) { this.cad.aviso('Volte à Montagem para confirmar a etapa.', 'atencao'); return; }
    const id = this._ident();
    this._guardarIdent({ ...id, etapas: { ...(id.etapas || {}), [nome]: 'confirmada' } });
    this._desenharIdent();
  }
}
