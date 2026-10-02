// Editar chapa (pedido do usuário, 02/10): "selecionar a chapa no 2D ou 3D e ter um menu de edição, com as opções de
// editar no local — vendo como a peça interage com os elementos ao redor para pegar alguma referência — e o ambiente de
// edição, só a peça, para mudar furos, tamanhos, recortes; quando terminar, o 3D e o 2D ficam exatamente iguais".
//
// O ambiente é o desenho "Detalhe – <marca>" da chapa paramétrica (os furos na camada FURO, o contorno que o Esticar
// muda), gerado pelo servidor com `edicao` — e, "no local", com as peças em volta cortadas no plano da chapa na camada
// REFERENCIA, travada. A faixa de cima diz o que está sendo editado; Concluir leva furos e contorno a todas as chapas da
// posição no modelo 3D (o "Aplicar furos e tamanho ao modelo 3D", com os parafusos andando junto), e o detalhamento se
// refaz; Cancelar volta sem levar nada.
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

export class MetodosEdicaoChapaCAD {
  /** A chapa da seleção (célula de detalhamento ou detalhe de posição): {marca, nome} ou null. */
  _chapaDaSelecao() {
    if ((this.doc.metadados || {}).edicao) return null;              // já está editando
    const ents = [...this.tela.selecao].map(id => this.doc.get(id)).filter(Boolean);
    const marcas = [...new Set(ents.map(e => (e.atributos || {}).posicao).filter(Boolean))];
    if (marcas.length !== 1 || /\s\/\s/.test(marcas[0])) return null;   // uma posição só (não as fundidas "P1 / P2")
    const a = (ents.find(e => (e.atributos || {}).posicao === marcas[0]) || {}).atributos || {};
    if (a.classe !== 'chapa' && !(this.doc.metadados || {}).detalhe_posicao) return null;
    return { marca: marcas[0], nome: a.nome || marcas[0] };
  }

  /** Os botões "Editar isolada" e "Editar no local" para o painel de propriedades (vazio se a seleção não é chapa). */
  _botoesEditarChapa() {
    const ch = this._chapaDaSelecao();
    if (!ch || !this.projeto) return [];
    return [
      el('button', { type: 'button', class: 'editar-chapa', texto: 'Editar isolada',
        title: `Abre ${ch.nome} sozinha para mudar furos, tamanho e contorno; Concluir leva a todas as chapas ${ch.marca} do 3D`,
        onclick: () => this.editarChapa(ch.marca, 'isolada') }),
      el('button', { type: 'button', class: 'editar-chapa', texto: 'Editar no local',
        title: `Abre ${ch.nome} com as peças em volta (cortadas no plano dela, só como referência) para medir e encaixar`,
        onclick: () => this.editarChapa(ch.marca, 'local') }),
    ];
  }

  /** Gera o ambiente de edição da chapa e abre nele; ao concluir ou cancelar, volta a `voltar` (este desenho). */
  async editarChapa(marca, modo, voltar) {
    if (!this.projeto) return;
    if (this._temPendente && this._temPendente() && !(await this._gravarOuConfirmar('Editar a chapa mesmo assim'))) return;
    this.dica(`Abrindo a edição de ${marca}${modo === 'local' ? ' no local' : ''}…`);
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar-posicao`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ marca, edicao: true, modo }),
      }).then(async x => { const j = await x.json(); if (!x.ok || j.erro) throw new Error(j.erro || x.statusText); return j; });
      this._voltarEdicao = voltar || this.nomeDesenho || null;
      await this.abrirDesenho(r.nome);
      if (!r.editavel) this.aviso(`${marca} não é chapa paramétrica: os furos deste desenho não voltam ao 3D.`, 'atencao', 10000);
    } catch (e) { this.aviso(`Não foi possível abrir a edição de ${marca}: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** A faixa EDITANDO no alto do desenho, quando o desenho aberto é o ambiente de edição (some nos outros). */
  _atualizarFaixaEdicao() {
    const ed = (this.doc && this.doc.metadados || {}).edicao;
    if (this._faixaEdicao) { this._faixaEdicao.remove(); this._faixaEdicao = null; }
    document.documentElement.classList.toggle('editando-chapa', !!ed);
    if (!ed) return;
    if (this._voltarEdicao === undefined) this._voltarEdicao = this.parametros.get('voltar') || null;
    const local = ed.modo === 'local';
    this._faixaEdicao = el('div', { class: 'faixa-edicao' },
      el('div', { class: 'faixa-edicao-titulo' },
        el('strong', { texto: `EDITANDO ${ed.nome}` }),
        el('span', { texto: ` (${ed.marca}) · ${ed.quantidade} peça${ed.quantidade === 1 ? '' : 's'} no modelo · ${local ? 'no local' : 'isolada'}` })),
      el('div', { class: 'faixa-edicao-dica', texto: 'Furos: camada FURO (mover, apagar, desenhar círculo) · tamanho: Esticar · contorno: os vértices' +
        (local ? ' · em cinza, as peças em volta (só referência, travadas)' : '') }),
      el('label', { class: 'faixa-edicao-opcao', title: 'Cada furo novo sem parafuso recebe a cópia do parafuso (com porca e arruela) de um furo da mesma chapa, em todas as chapas da posição' },
        this._copiarParafusos = el('input', { type: 'checkbox', checked: true }), ' copiar parafusos nos furos novos'),
      el('div', { class: 'faixa-edicao-botoes' },
        el('button', { type: 'button', class: 'primario', texto: 'Concluir', title: `Leva furos e contorno a todas as ${ed.quantidade} chapas ${ed.marca} do 3D e refaz o detalhamento`,
          onclick: () => this.concluirEdicaoChapa() }),
        el('button', { type: 'button', texto: 'Cancelar', title: 'Volta sem levar nada ao 3D', onclick: () => this.cancelarEdicaoChapa() })));
    (document.getElementById('palco') || document.body).append(this._faixaEdicao);
  }

  async concluirEdicaoChapa() {
    const ed = (this.doc.metadados || {}).edicao;
    if (!ed) return;
    this.dica(`Levando ${ed.nome} ao modelo 3D…`);
    try {
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/aplicar-furos`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ desenho: this.doc.paraJSON(), marca: ed.marca,
                               copiar_parafusos: !!(this._copiarParafusos && this._copiarParafusos.checked) }),
      }).then(async x => { const j = await x.json(); if (!x.ok || j.erro) throw new Error(j.erro || x.statusText); return j; });
      this._autosavePendente = false;
      if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
      this._editado = false;
      const msg = `${ed.nome}: ${r.furos || 0} furo(s)${r.contornos ? ' e o contorno' : ''} em ${r.chapas || 0} chapa(s) do 3D` +
        (r.parafusos ? `, ${r.parafusos} parafuso(s) movidos junto` : '') +
        (r.parafusos_copiados ? `, ${r.parafusos_copiados} peça(s) de parafuso copiadas nos furos novos` : '') +
        (r.espelhadas ? `; ${r.espelhadas} chapa(s) do outro lado do prédio receberam a edição espelhada` : '') +
        (r.padrao_maquina ? `; furos na terça levados ao padrão da máquina em ${r.padrao_maquina} chapa(s)` : '') +
        '. O detalhamento se refaz sozinho em seguida.';
      await this._sairDaEdicao(r.nome);
      this.aviso(msg, 'info', 12000);
    } catch (e) { this.aviso(`Não foi possível concluir: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  async cancelarEdicaoChapa() {
    const ed = (this.doc.metadados || {}).edicao;
    if (!ed) return;
    if (this._editado && await this.dialogo({ titulo: 'Cancelar a edição', corpo: el('p', { texto: `Sair sem levar a ${ed.nome} ao 3D? O que foi mudado neste desenho fica só nele.` }),
      ok: 'Sair sem levar', cancelar: 'Continuar editando' }) !== 'ok') return;
    this._autosavePendente = false;
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    this._editado = false;
    await this._sairDaEdicao();
    this.dica(`Edição de ${ed.nome} cancelada: nada foi ao 3D.`);
  }

  /** Volta para onde a edição começou (o desenho de antes, ou o 3D); sem para onde voltar, fica no detalhe — o
   *  regenerado pelo Concluir (`regenerado`), ou este, que deixa de ser ambiente de edição. */
  async _sairDaEdicao(regenerado) {
    const voltar = this._voltarEdicao;
    this._voltarEdicao = undefined;
    if (voltar === '__3d__') { (window.metalicaNavegar || ((u) => { location.href = u; }))(this.urlDoEditor()); return; }
    if (voltar && voltar !== this.nomeDesenho) { await this.abrirDesenho(voltar); return; }
    if (regenerado) { await this.abrirDesenho(regenerado); return; }
    if (this.doc.metadados) delete this.doc.metadados.edicao;
    this._atualizarFaixaEdicao();
  }
}
