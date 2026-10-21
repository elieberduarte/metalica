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
//
// Etapa 4 (contraventos e outras peças): "Lançar contraventos e vigas" lê as plantas de contraventamento e a locação
// (identificacao.outras_pecas): os contraventos no plano do banzo de cima ou do de baixo, cada ponta na cota do banzo da
// tesoura do eixo dela (inclinados como o telhado); agulhamentos e correntes no plano das terças; o perfil pela legenda de
// cores; as vigas das folhas de viga onde a locação marca a sigla — a treliçada (VC) pelo desenho da folha dela, como a
// tesoura, mas atravessada; a simples (VT) no plano do banzo de baixo. Lançar de novo troca as lançadas antes.
//
// Fase 5 (montar): a Implantação já leva o 3D junto a cada gravação (só as peças dela). "Montar o modelo 3D" fecha:
// o que está no modelo e não veio da identificação (o 3D desmontado do caminho antigo, peças à mão) vai para o histórico
// — com a pergunta, dizendo quantas —, o modelo passa a ser o identificado (/estrutura/3d sem sincronia, marco no
// histórico) e o 3D abre.
//
// Fase 6 (vínculo): a ida já existia (a gravação da Implantação leva o 3D); a volta "Trazer do 3D o que mudou" usa a do
// menu Estrutura, que agora entende a Montagem (de_planta_estrutura.montagem_do_modelo: ao real, a volta, de volta ao
// papel do quadro).

import { criar } from './nucleo/desenho2d.js';
import { ComandoAdicionar, ComandoAlterar, ComandoComposto, ComandoRemover } from './nucleo/comandos.js';

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
  ['apoios', 'Apoios: chapas e chumbadores'],
  ['suportes', 'Suportes das terças'],
  ['chapas', 'Emendas e ligações das tesouras'],
  ['aletas', 'Aletas e castanhas dos contraventos'],
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
    const livre4 = this._liberada('contraventos');
    const nOutras = this.ativa ? [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'outra').length : (id.outras || {}).n || 0;
    const resO = id.outras || {};
    const sec4 = etapa('contraventos', ETAPAS[3][1], ...folhas(v.contraventos), ...folhas(v.outras),
      nOutras ? el('div', { class: 'ident-linha ok', texto: `${nOutras} peça(s) lançada(s) na Implantação` + (resO.resumo ? ` (${resO.resumo})` : '') + '.' }) : null,
      avisos(resO.avisos),
      livre4 ? el('div', { class: 'ident-botoes' },
        botao(nOutras ? 'Lançar de novo' : 'Lançar contraventos e vigas', () => this._lancarOutrasIdent(), { class: nOutras ? '' : 'primario',
          title: 'Contraventos e correntes das plantas de contraventamento e as vigas (VC, VT) onde a locação marca, nos eixos gravados' }),
        botao('Confirmar ✓', () => this._confirmarIdent('contraventos'), { class: 'ident-confirmar', disabled: nOutras ? undefined : true })) : null);
    const livre5 = this._liberada('apoios');
    const nApoios = this.ativa ? [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'apoio' && (e.atributos || {}).elemento === 'chapa').length : (id.apoios || {}).n || 0;
    const resA = id.apoios || {};
    const sec5 = etapa('apoios', ETAPAS[4][1],
      el('div', { class: 'explica', texto: 'As chapas de apoio (PB, CB) e os chumbadores pela locação dos chumbadores e o detalhe do projeto, nos pilares da Implantação; o topo do pilar que recebe tesoura desce a espessura da CB (a PB embutida rente a ele).' }),
      nApoios ? el('div', { class: 'ident-linha ok', texto: `${nApoios} chapa(s) lançada(s)` + (resA.resumo ? ` — apoios ${resA.resumo}` : '') + '.' }) : null,
      avisos(resA.avisos),
      livre5 ? el('div', { class: 'ident-botoes' },
        botao(nApoios ? 'Lançar de novo' : 'Lançar os apoios', () => this._lancarApoiosIdent(), { class: nApoios ? '' : 'primario',
          title: 'Lê a locação dos chumbadores, as chapas e o detalhe e lança nos pilares da Implantação' }),
        botao('Confirmar ✓', () => this._confirmarIdent('apoios'), { class: 'ident-confirmar', disabled: nApoios ? undefined : true })) : null);
    const livre6 = this._liberada('suportes');
    const nSup = this.ativa ? [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca' && (e.atributos || {}).suporte).length : (id.suportes || {}).n || 0;
    const resS = id.suportes || {};
    const sec6 = etapa('suportes', ETAPAS[5][1],
      el('div', { class: 'explica', texto: 'O suporte das terças do projeto (a cantoneira, os furos, a folga entre as pontas) em cada terça lançada: o 3D põe um em cada cruzamento com o banzo de cima e fura a terça e o suporte.' }),
      nSup ? el('div', { class: 'ident-linha ok', texto: `${resS.marca || 'Suporte'} em ${nSup} terça(s)` + (resS.resumo ? ` — ${resS.resumo}` : '') + '.' }) : null,
      avisos(resS.avisos),
      livre6 ? el('div', { class: 'ident-botoes' },
        botao(nSup ? 'Pôr de novo' : 'Pôr os suportes nas terças', () => this._suportesIdent(), { class: nSup ? '' : 'primario',
          title: 'Lê o suporte das terças nas folhas do projeto e põe nas terças da Implantação' }),
        botao('Confirmar ✓', () => this._confirmarIdent('suportes'), { class: 'ident-confirmar', disabled: nSup ? undefined : true })) : null);
    const livre7 = this._liberada('chapas');
    const tesTrel = this.ativa ? [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && !(e.atributos || {}).identificacao) : [];
    const nCh = this.ativa ? tesTrel.filter(e => (e.atributos || {}).chapas).length : (id.chapas || {}).n || 0;
    const resC = id.chapas || {};
    const sec7 = etapa('chapas', ETAPAS[6][1],
      el('div', { class: 'explica', texto: 'As chapas da emenda da cumeeira (uma em cada meia-tesoura, aparafusadas) e as de ligação (nos montantes onde as vigas VC e VT chegam) pelo detalhe do projeto, em cada tesoura pelo tipo dela; o 3D faz as chapas, os parafusos da emenda, o montante de cada metade e os furos nas vigas.' }),
      nCh ? el('div', { class: 'ident-linha ok', texto: `Chapas em ${nCh} tesoura(s)` + (resC.resumo ? ` — ${resC.resumo}` : '') + '.' }) : null,
      avisos(resC.avisos),
      livre7 ? el('div', { class: 'ident-botoes' },
        botao(nCh ? 'Pôr de novo' : 'Pôr as chapas nas tesouras', () => this._chapasIdent(), { class: nCh ? '' : 'primario',
          title: 'Lê as chapas da emenda e das ligações nas folhas do projeto e põe em cada tesoura da Implantação pelo tipo' }),
        botao('Confirmar ✓', () => this._confirmarIdent('chapas'), { class: 'ident-confirmar', disabled: nCh ? undefined : true })) : null);
    const livre8 = this._liberada('aletas');
    const nAl = this.ativa ? tesTrel.filter(e => (e.atributos || {}).aletas).length : (id.aletas || {}).n || 0;
    const resAl = id.aletas || {};
    const sec8 = etapa('aletas', ETAPAS[7][1],
      el('div', { class: 'explica', texto: 'As aletas dos contraventos pelo detalhe do projeto, em cada tesoura pelo tipo dela: o 3D põe uma em cada ponta de contravento que chega no banzo (em pé, perpendicular à barra, o furo na ponta dela) e a barra passa a aleta até as porcas, no comprimento de corte do projeto.' }),
      nAl ? el('div', { class: 'ident-linha ok', texto: `Aletas em ${nAl} tesoura(s)` + (resAl.resumo ? ` — ${resAl.resumo}` : '') + '.' }) : null,
      avisos(resAl.avisos),
      livre8 ? el('div', { class: 'ident-botoes' },
        botao(nAl ? 'Pôr de novo' : 'Pôr as aletas nas tesouras', () => this._aletasIdent(), { class: nAl ? '' : 'primario',
          title: 'Lê as aletas dos contraventos na folha do projeto e põe em cada tesoura da Implantação pelo tipo' }),
        botao('Confirmar ✓', () => this._confirmarIdent('aletas'), { class: 'ident-confirmar', disabled: nAl ? undefined : true })) : null);
    const podeMontar = et.locacao === 'confirmada' && et.tesouras === 'confirmada';
    const faltamEt = ETAPAS.filter(([k]) => et[k] !== 'confirmada').map(([, r]) => r.toLowerCase());
    const montado = id.montado;
    const montar = el('section', { class: 'ident-etapa ident-montar' + (montado ? ' confirmada' : '') },
      el('h4', {}, 'Montar o modelo 3D', montado ? el('span', { class: 'ident-estado', texto: `montado ✓ (${montado.pecas} peças)` }) : null),
      el('div', { class: 'explica', texto: 'O 3D acompanha a Implantação a cada gravação. Montar deixa o modelo só com o que foi identificado (o resto vai para o histórico) e abre o 3D; o Original fica para as conferências.' }),
      podeMontar && faltamEt.length ? el('div', { class: 'ident-sub', texto: `ainda não confirmadas: ${faltamEt.join(', ')} (dá para montar assim e voltar depois)` }) : null,
      el('div', { class: 'ident-botoes' }, botao(montado ? 'Montar de novo e abrir o 3D' : 'Montar o modelo 3D', () => this._montarIdent(),
        { class: 'primario', disabled: podeMontar ? undefined : true, title: podeMontar ? 'O modelo do projeto passa a ser o identificado' : 'Confirme a locação e as tesouras primeiro' }),
        montado ? botao('Trazer do 3D o que mudou', () => this.cad.atualizarPlantaPelo3D(),
          { title: 'O que foi mudado no 3D (peça movida, comprimento, cota) volta para a Implantação; a peça apagada lá vira aviso' }) : null),
      montado ? el('div', { class: 'ident-sub', texto: 'Vinculados: o que muda na Implantação vai para o 3D a cada gravação; o que muda no 3D volta por "Trazer do 3D o que mudou".' }) : null);
    corpo.replaceChildren(sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8, montar);
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
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/tesoura`, { original, caixa: t.vista.caixa, tipo: t.tipo });
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
    // o desenho já lido no servidor (as pontas como o projeto) e os perfis da folha de marcas: a origem dele, do Original
    // para a elevação pelo mesmo ponto de referência da colagem (o Original em mm)
    const d = r.desenho;
    const desenho = d && d.barras && d.barras.length >= 3
      ? { ...d, n: d.barras.length, raio: null, origem: [uMeio + (d.origem[0] - r.ref[0]), z + (d.origem[1] - r.ref[1])] } : null;
    const lancou = await this.tesouraDaElevacao(q, { marca: t.tipo, eixos: t.eixos.length ? t.eixos : [eixo], desenho, perfis: r.perfis || null });
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

  /** Fase 5: o modelo 3D só com o identificado (o resto vai para o histórico, com a pergunta) e o 3D aberto. */
  async _montarIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    clearTimeout(this._timer); this._timer = null;
    await this.cad.salvar({ avisar: false });
    const p = encodeURIComponent(this.cad.projeto);
    let ents = [];
    try {
      const d = await pedir(`/api/projetos/${p}/modelo`);
      const doc = (d && d.documento) || d || {};
      ents = Array.isArray(doc.entidades) ? doc.entidades : Object.values(doc.entidades || {});
    } catch { ents = []; }
    const daqui = (e) => ((e.atributos || {}).planta === this.cad.nomeDesenho);
    const outras = ents.filter(e => !daqui(e));
    if (outras.length) {
      const corpo = el('div', {},
        el('div', { class: 'explica', texto: `O modelo 3D do projeto tem ${outras.length.toLocaleString('pt-BR')} peça(s) que não vieram da identificação (do caminho antigo, de outra planta ou feitas à mão no 3D). Montar deixa o modelo só com o identificado (${ents.length - outras.length} peça(s) agora); as outras ficam no histórico do projeto e voltam por Arquivo › Versões anteriores do modelo…` }));
      if (await this.cad.dialogo({ titulo: 'Montar o modelo 3D', corpo, ok: 'Montar' }) !== 'ok') return;
    }
    let r;
    try {
      r = await pedir(`/api/projetos/${p}/estrutura/3d`, { desenho: this.cad.nomeDesenho, sincronizar: false });
    } catch (e) { this.cad.aviso('Não foi possível montar o 3D: ' + e.message, 'erro', 0); return; }
    const n = (r && (r.entrou || (r.estatisticas || {}).entidades || r.pecas)) || (ents.length - outras.length);
    this._guardarIdent({ ...this._ident(), montado: { quando: new Date().toISOString(), pecas: n, tirou: outras.length } });
    await this.cad.salvar({ avisar: false });
    this._desenharIdent();
    this.cad.aviso(`Modelo 3D montado pelo identificado: ${n} peça(s)${outras.length ? `; ${outras.length} antiga(s) foram para o histórico` : ''}.`, 'info', 12000);
    (window.metalicaNavegar || ((u) => { location.href = u; }))(this.cad.urlDoEditor());
  }

  /** Etapa 4: contraventos, correntes e vigas lançados na Implantação, nos eixos gravados. */
  async _lancarOutrasIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    const id = this._ident(), v = id.varredura;
    const qi = this._quadroImplantacao();
    if (!qi || !qi.mapa) { this.cad.aviso('Falta a Implantação com os eixos.', 'atencao'); return; }
    const apoio = await this._apoioIdent();
    if (apoio == null) return;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/outras`, {
        original: this.m.original || this.original, locacao: v.locacao, folhas: v.folhas, apoio,
        tesouras: (v.tesouras || []).filter(t => t.vista && t.eixos.length).map(t => ({ tipo: t.tipo, eixos: t.eixos, caixa: t.vista.caixa })) });
    } catch (e) { this.cad.aviso('Não consegui ler os contraventos e as vigas: ' + e.message, 'erro', 0); return; }
    const novas = [];
    for (const b of r.barras || []) {
      novas.push(criar({ tipo: 'linha', camada: 'ESTRUTURA', a: this._paraPapel(qi, [b.g_a, b.p_a]), b: this._paraPapel(qi, [b.g_b, b.p_b]),
        atributos: { elemento: 'viga', material: 'aco', papel: b.papel, identificacao: 'outra', marca: b.marca || b.papel, quadro: qi.id,
          secao: { perfil: b.perfil || 'Barra redonda ø 1/2"', aco: 'ASTM A36' }, nivel_topo: b.z_a, nivel_fim: b.z_b, alinhamento: 'eixo', plano: b.plano } }));
    }
    for (const t of r.trelicas || []) {
      novas.push(criar({ tipo: 'linha', camada: 'ESTRUTURA', a: this._paraPapel(qi, [t.g_a, t.p]), b: this._paraPapel(qi, [t.g_b, t.p]),
        atributos: { elemento: 'trelica', material: 'aco', identificacao: 'outra', marca: t.marca, quadro: qi.id, familia_eixo: 'letra',
          perfis: { banzo_sup: t.perfil, banzo_inf: t.perfil, diagonal: t.perfil_alma }, cantoneira: 'simples', aco: 'ASTM A572 Gr.50',
          nivel_base: t.z_base, acima_do_nivel: 0, eixos: t.eixos, u: t.u,
          desenho: { barras: t.desenho.barras, vao: t.desenho.vao, altura: t.desenho.altura, raio_banzo_sup: null } } }));
    }
    if (!novas.length) { this.cad.aviso('Nenhum contravento nem viga lidos: ' + (r.avisos || []).join(' '), 'atencao', 0); return; }
    const antes = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'outra').map(e => e.id);
    const cmds = [];
    if (antes.length) cmds.push(new ComandoRemover(antes, 'Peças lançadas antes'));
    cmds.push(new ComandoAdicionar(novas, `Contraventos e vigas (${novas.length})`));
    if (!this.cad.doc.camadas.has('ESTRUTURA') && this.cad._garantirCamadaEstrutura) this.cad._garantirCamadaEstrutura();
    this.cad.executar(cmds.length > 1 ? new ComandoComposto(cmds, `Contraventos e vigas (${novas.length})`) : cmds[0]);
    const resumo = Object.entries(r.resumo || {}).sort((a, b) => a[0].localeCompare(b[0], 'pt-BR', { numeric: true })).map(([m, n]) => `${n} ${m}`).join(', ');
    this._guardarIdent({ ...this._ident(), outras: { n: novas.length, resumo, avisos: r.avisos || [] } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`${novas.length} peça(s) lançada(s) na Implantação: ${resumo}. O 3D acompanha a planta; Ctrl+Z desfaz.`, (r.avisos || []).length ? 'atencao' : 'info', 14000);
    this._desenharIdent();
  }

  /** Etapa 5: as chapas de apoio (PB embutida no topo do pilar, CB por cima onde a tesoura apoia), os furos e os
   *  chumbadores lançados na Implantação; o topo do pilar que recebe tesoura desce a espessura da CB (21/10/2026). */
  async _lancarApoiosIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    const qi = this._quadroImplantacao();
    if (!qi || !qi.mapa) { this.cad.aviso('Falta a Implantação com os eixos.', 'atencao'); return; }
    const apoio = await this._apoioIdent();
    if (apoio == null) return;
    await this.cad.salvar({ avisar: false });
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/apoios-tesouras`, {
        original: this.m.original || this.original, apoio, montagem: this.cad.nomeDesenho });
    } catch (e) { this.cad.aviso('Não consegui ler os apoios: ' + e.message, 'erro', 0); return; }
    const aps = r.apoios || [];
    if (!aps.length) { this.cad.aviso('Nenhum apoio lido: ' + (r.avisos || []).join(' '), 'atencao', 0); return; }
    const P = (x, y) => this._paraPapel(qi, [x, y]);
    const s = qi.escala || 1;
    const quadrado = (cx, cy, B, H) => [P(cx - B / 2, cy - H / 2), P(cx + B / 2, cy - H / 2), P(cx + B / 2, cy + H / 2), P(cx - B / 2, cy + H / 2)];
    const novas = [], pilares = {};
    for (const a of aps) {
      const [cx, cy] = a.centro, pb = a.pb, cb = a.cb;
      const base = { identificacao: 'apoio', apoio: a.marca, pilar: a.pilar, quadro: qi.id };
      // a PB embutida rente ao topo do pilar: debaixo da CB onde a tesoura apoia, senão no topo do próprio pilar
      // o topo da PB pelo projeto (a V12 do Hangar: a PB sobre o pilar e a CB numa folga acima dela); antes, embutida rente
      const topoPB = a.topo_pb != null ? a.topo_pb : (cb ? apoio - cb.espessura : a.nivel_topo_pilar);
      novas.push(criar({ tipo: 'polilinha', camada: 'ESTRUTURA', fechada: true, vertices: quadrado(cx, cy, pb.largura, pb.altura),
        atributos: { ...base, elemento: 'chapa', material: 'aco', marca: pb.marca, espessura: pb.espessura, nivel_topo: topoPB, aco: 'ASTM A36' } }));
      if (cb) {
        novas.push(criar({ tipo: 'polilinha', camada: 'ESTRUTURA', fechada: true, vertices: quadrado(cx, cy, cb.largura, cb.altura),
          atributos: { ...base, elemento: 'chapa', material: 'aco', marca: cb.marca, espessura: cb.espessura, nivel_topo: apoio, aco: 'ASTM A36' } }));
        pilares[a.pilar_id] = a.topo_pilar;
      }
      const ch = a.chumbadores || {};
      for (const f of pb.furos || []) {
        const c = P(cx + f.dx, cy + f.dy);
        novas.push(criar({ tipo: 'circulo', camada: 'ESTRUTURA', centro: c, raio: f.diametro / 2 / s,
          atributos: { ...base, elemento: 'furo', diametro: f.diametro, chapa: pb.marca, marca: `${pb.marca}-F` } }));
        if (ch.diametro && ch.comprimento) {
          novas.push(criar({ tipo: 'circulo', camada: 'ESTRUTURA', centro: c, raio: ch.diametro / 2 / s,
            atributos: { ...base, elemento: 'parafuso', papel: 'chumbador', diametro: ch.diametro, comprimento: ch.comprimento,
              bitola: ch.texto, marca: `CH ${a.marca}`, nivel_topo: typeof topoPB === 'number' ? topoPB - pb.espessura : topoPB } }));
        }
      }
    }
    const antes = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'apoio').map(e => e.id);
    const cmds = [];
    if (antes.length) cmds.push(new ComandoRemover(antes, 'Apoios lançados antes'));
    cmds.push(new ComandoAdicionar(novas, `Apoios (${aps.length})`));
    const mud = {};
    for (const [id, topo] of Object.entries(pilares)) {
      const e = this.cad.doc.get(id);
      if (e && topo != null && (e.atributos || {}).nivel_topo !== topo) mud[id] = { atributos: { ...(e.atributos || {}), nivel_topo: topo } };
    }
    if (Object.keys(mud).length) cmds.push(new ComandoAlterar(mud, 'Topo dos pilares sob as tesouras'));
    if (!this.cad.doc.camadas.has('ESTRUTURA') && this.cad._garantirCamadaEstrutura) this.cad._garantirCamadaEstrutura();
    this.cad.executar(new ComandoComposto(cmds, `Apoios (${aps.length})`));
    const resumo = Object.entries(r.resumo || {}).map(([m, n]) => `${n} ${m}`).join(', ');
    this._guardarIdent({ ...this._ident(), apoios: { n: novas.filter(e => (e.atributos || {}).elemento === 'chapa').length, resumo, avisos: r.avisos || [] } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`${aps.length} apoio(s) lançado(s) na Implantação (${resumo}); ${Object.keys(mud).length} pilar(es) com o topo na face de baixo da CB. O 3D acompanha a planta; Ctrl+Z desfaz.`,
      (r.avisos || []).length ? 'atencao' : 'info', 16000);
    this._desenharIdent();
  }

  /** Etapa 6: o suporte das terças do projeto (ST1 no Hangar) em cada terça lançada; o 3D faz um em cada cruzamento
   *  com o banzo de cima, fura a terça e o suporte e deixa a folga entre as pontas (21/10/2026). */
  async _suportesIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/suportes-tercas`, { original: this.m.original || this.original });
    } catch (e) { this.cad.aviso('Não consegui ler o suporte das terças: ' + e.message, 'erro', 0); return; }
    const sups = Object.values(r.suportes || {});
    const st = sups.find(s => /^ST/i.test(s.marca)) || sups[0];
    if (!st) { this.cad.aviso('O projeto não escreve o suporte das terças.', 'atencao', 0); return; }
    const tercas = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).identificacao === 'terca');
    if (!tercas.length) { this.cad.aviso('Lance as terças primeiro (etapa 3).', 'atencao'); return; }
    const mud = {};
    for (const e of tercas) mud[e.id] = { atributos: { ...(e.atributos || {}), suporte: st } };
    this.cad.executar(new ComandoAlterar(mud, `Suporte ${st.marca} nas terças`));
    const outros = sups.filter(s => s !== st).map(s => `${s.marca} (${s.quantidade} pç, ${s.texto}) fica para as terças laterais, ainda não lançadas`);
    const fur = st.furos || [];
    const resumo = `${st.texto}, ${fur.length} furo(s)${fur.length ? ` Ø${fur[0].d}` : ''}` + (st.folga ? `, folga de ${st.folga} mm entre as pontas` : '');
    const avs = [...(r.avisos || []), ...outros, ...(st.a_definir ? [`${st.marca}: ${st.a_definir} — apontamento ao projetista`] : [])];
    this._guardarIdent({ ...this._ident(), suportes: { n: tercas.length, marca: st.marca, resumo, avisos: avs } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`${st.marca} nas ${tercas.length} terças (${resumo}). O 3D põe um em cada cruzamento com o banzo de cima; Ctrl+Z desfaz.`, avs.length ? 'atencao' : 'info', 16000);
    this._desenharIdent();
  }

  /** Etapa 7: as chapas da emenda da cumeeira e das ligações (CE/CL no Hangar) em cada tesoura pelo tipo dela (a T2-A
   *  leva as da T2); o 3D faz as chapas na junta e nos montantes onde as vigas chegam (21/10/2026). */
  async _chapasIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/chapas-tesouras`, { original: this.m.original || this.original });
    } catch (e) { this.cad.aviso('Não consegui ler as chapas das tesouras: ' + e.message, 'erro', 0); return; }
    const chs = Object.values(r.chapas || {});
    const tes = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && !(e.atributos || {}).identificacao);
    if (!tes.length) { this.cad.aviso('Ponha as tesouras nos eixos primeiro (etapa 2).', 'atencao'); return; }
    const tipo = (marca) => ((String(marca || '').match(/^T\d+/i) || [''])[0]).toUpperCase();
    if (r.emendas) {
      // a emenda por tipo de tesoura (a V12 do Hangar: a chapa em cada banzo da T2, o U em pé da T1 e da T3) e a chapa da
      // ponta da VC (CV1)
      const mud = {};
      const sem = new Set();
      for (const e of tes) {
        const a = e.atributos || {};
        const em = r.emendas[tipo(a.marca)] || null;
        if (!em && !r.ligacao_vc) { sem.add(a.marca); continue; }
        mud[e.id] = { atributos: { ...a, chapas: { emenda_v12: em, ligacao_vc: r.ligacao_vc || null } } };
      }
      if (!Object.keys(mud).length) { this.cad.aviso('Nenhuma emenda do projeto é das tesouras lançadas.', 'atencao', 0); return; }
      this.cad.executar(new ComandoAlterar(mud, 'Emendas das tesouras'));
      const resumo = Object.entries(r.emendas).sort().map(([k, x]) => `${k}: ${String(x.texto || '').split(' / ')[0]}`).join('; ')
        + (r.ligacao_vc ? `; ${r.ligacao_vc.texto}` : '');
      const avs = [...(r.avisos || []), ...[...sem].map(m => `${m}: o projeto não tem emenda para este tipo`)];
      this._guardarIdent({ ...this._ident(), chapas: { n: Object.keys(mud).length, resumo, avisos: avs } });
      await this.cad.salvar({ avisar: false });
      this.cad.aviso(`Emendas em ${Object.keys(mud).length} tesoura(s): ${resumo}. O 3D faz a emenda na junta e a chapa onde a VC chega; Ctrl+Z desfaz.`,
        avs.length ? 'atencao' : 'info', 16000);
      this._desenharIdent();
      return;
    }
    const doTipo = (marca, papel) => chs.find(c => c.papel === papel && c.tesoura && tipo(c.tesoura) === tipo(marca)) || null;
    const mud = {};
    const sem = new Set();
    const usadas = new Set();
    for (const e of tes) {
      const a = e.atributos || {};
      const emenda = doTipo(a.marca, 'emenda');
      const ligacao = doTipo(a.marca, 'ligacao');
      if (!emenda && !ligacao) { sem.add(a.marca); continue; }
      if (emenda) usadas.add(emenda.marca);
      if (ligacao) usadas.add(ligacao.marca);
      mud[e.id] = { atributos: { ...a, chapas: { emenda, ligacao, parafusos_emenda: r.parafusos_emenda || null } } };
    }
    if (!Object.keys(mud).length) { this.cad.aviso('Nenhuma chapa do projeto é das tesouras lançadas.', 'atencao', 0); return; }
    this.cad.executar(new ComandoAlterar(mud, 'Chapas das tesouras'));
    const resumo = chs.filter(c => usadas.has(c.marca)).map(c => `${c.marca} (${c.tesoura}, #${c.espessura} ${c.largura}×${c.altura})`).join(', ')
      + (r.parafusos_emenda ? `; emenda com ${r.parafusos_emenda.n} parafusos ${r.parafusos_emenda.texto}` : '');
    const avs = [...(r.avisos || []), ...[...sem].map(m => `${m}: o projeto não tem chapa de emenda nem de ligação para este tipo`),
      ...chs.filter(c => !usadas.has(c.marca)).map(c => `${c.marca} (${c.tesoura || 'sem tesoura'}) não casou com nenhuma tesoura lançada`)];
    this._guardarIdent({ ...this._ident(), chapas: { n: Object.keys(mud).length, resumo, avisos: avs } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`Chapas em ${Object.keys(mud).length} tesoura(s): ${resumo}. O 3D põe a emenda na junta e as ligações onde as vigas chegam; Ctrl+Z desfaz.`,
      avs.length ? 'atencao' : 'info', 16000);
    this._desenharIdent();
  }

  /** Etapa 8: as aletas dos contraventos (AC no Hangar) em cada tesoura pelo tipo dela; o 3D põe uma em cada ponta de
   *  contravento que chega no banzo e a barra fica com o comprimento de corte do projeto (21/10/2026). */
  async _aletasIdent() {
    if (!this.ativa) await this.ir('montagem');
    if (!this.ativa) return;
    let r;
    try {
      r = await pedir(`/api/projetos/${encodeURIComponent(this.cad.projeto)}/identificacao/aletas-contraventos`, { original: this.m.original || this.original });
    } catch (e) { this.cad.aviso('Não consegui ler as aletas dos contraventos: ' + e.message, 'erro', 0); return; }
    const als = Object.values(r.aletas || {});
    const tes = [...this.cad.doc.entidades.values()].filter(e => (e.atributos || {}).elemento === 'trelica' && !(e.atributos || {}).identificacao);
    if (!tes.length) { this.cad.aviso('Ponha as tesouras nos eixos primeiro (etapa 2).', 'atencao'); return; }
    const tipo = (marca) => ((String(marca || '').match(/^T\d+/i) || [''])[0]).toUpperCase();
    if (r.castanha) {
      // a castanha no lugar da aleta (a V12 do Hangar): a mesma em todas as tesouras; o 3D a põe em cada ponta de contravento
      // do banzo em que ela está definida
      const ca = r.castanha;
      const mud = {};
      for (const e of tes) mud[e.id] = { atributos: { ...(e.atributos || {}), aletas: { castanha: ca, contraventos: r.contraventos || {} } } };
      this.cad.executar(new ComandoAlterar(mud, 'Castanhas dos contraventos'));
      const resumo = `${ca.marca} - ${ca.quantidade} pç (castanha: ${ca.peca.perfil} L=${ca.peca.comprimento} + ${ca.aba.perfil} L=${ca.aba.comprimento}`
        + `${ca.parafuso ? `, parafuso ${ca.parafuso.texto} no banzo` : ''})`;
      const avs = [...(r.avisos || [])];
      this._guardarIdent({ ...this._ident(), aletas: { n: tes.length, resumo, avisos: avs } });
      await this.cad.salvar({ avisar: false });
      this.cad.aviso(`Castanhas em ${tes.length} tesoura(s): ${resumo}. Ctrl+Z desfaz.`, avs.length ? 'atencao' : 'info', 16000);
      this._desenharIdent();
      return;
    }
    const mud = {};
    const usadas = new Set();
    for (const e of tes) {
      const a = e.atributos || {};
      const aleta = als.find(x => x.tesoura && tipo(x.tesoura) === tipo(a.marca));
      if (!aleta) continue;
      usadas.add(aleta.marca);
      mud[e.id] = { atributos: { ...a, aletas: { aleta, contraventos: r.contraventos || {} } } };
    }
    if (!Object.keys(mud).length) { this.cad.aviso('Nenhuma aleta do projeto é das tesouras lançadas.', 'atencao', 0); return; }
    this.cad.executar(new ComandoAlterar(mud, 'Aletas dos contraventos'));
    const resumo = als.filter(x => usadas.has(x.marca)).map(x => `${x.marca} (${x.tesoura}, #${x.espessura} ${x.largura}×${x.altura})`).join(', ')
      + (r.rosca ? `; ${r.rosca.texto.toLowerCase()}` : '');
    const avs = [...(r.avisos || []), ...als.filter(x => !usadas.has(x.marca)).map(x => `${x.marca} (${x.tesoura || 'sem tesoura'}) não casou com nenhuma tesoura lançada`)];
    this._guardarIdent({ ...this._ident(), aletas: { n: Object.keys(mud).length, resumo, avisos: avs } });
    await this.cad.salvar({ avisar: false });
    this.cad.aviso(`Aletas em ${Object.keys(mud).length} tesoura(s): ${resumo}. O 3D põe uma em cada ponta de contravento; Ctrl+Z desfaz.`, avs.length ? 'atencao' : 'info', 16000);
    this._desenharIdent();
  }

  _confirmarIdent(nome) {
    if (!this.ativa) { this.cad.aviso('Volte à Montagem para confirmar a etapa.', 'atencao'); return; }
    const id = this._ident();
    this._guardarIdent({ ...id, etapas: { ...(id.etapas || {}), [nome]: 'confirmada' } });
    this._desenharIdent();
  }
}
