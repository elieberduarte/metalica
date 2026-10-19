// Métodos do editor 3D: Modelo → Reanalisar estrutura (19/10/2026).
//
// O modelo antigo pelas regras de hoje, sem remontar (nucleo3d/reanalise.py): o usuário, no CD Bom Dia — "pegar esse
// tipo de erro de concepção que já corrigimos em outros modelos" (tocos soltos, diagonal pendurada, diagonal passando do
// banzo, peça repetida, peça da treliça fora da regra). Primeiro a prévia, regra por regra, com as peças clicáveis; o
// usuário marca o que corrigir e aplica numa entrada só de desfazer. O que não se corrige sozinho fica listado para
// conferir (os grupos de peças iguais se escolhem de uma vez).

import { el } from '../editor.js';

export class MetodosReanalise {
  /** A prévia: o modelo como está vai ao servidor, que devolve o que cada regra muda (nada muda ainda). */
  async reanalisarEstrutura() {
    if (!this.documento.tamanho) { this.aviso('O modelo está vazio.', 'atencao'); return; }
    this._fecharReanalise();
    this._painelReanalise = el('div', { class: 'painel-apoios painel-reanalise' },
      el('div', { class: 'painel-apoios-titulo' }, el('strong', { texto: 'Reanalisar estrutura' })),
      el('div', { class: 'painel-apoios-corpo' },
        el('p', { texto: 'Passando o modelo pelas regras de hoje — nada muda antes de você aplicar. A barra embaixo mostra a etapa.' })));
    (this.el.palco || document.body).append(this._painelReanalise);
    const r = await this._pedirReanalise(null);
    if (!r) { this._fecharReanalise(); return; }
    this._mostrarReanalise(r);
  }

  /** A assinatura do modelo agora: o último comando da pilha e o tamanho dela (o que mudou desde a prévia). */
  _assinaturaDoModelo() {
    const p = this.pilha || {};
    const f = p.feitos || [];
    return { ultimo: f[f.length - 1] || null, feitos: f.length, desfeitos: (p.desfeitos || []).length };
  }

  /** O pedido ao servidor. A conexão que cai no meio (o servidor do modo dev reinicia a cada .py salvo: no CD Bom Dia,
   *  19/10, "Failed to fetch" depois de 40 s) não é erro da conta: espera o servidor voltar e pede de novo (até 3 vezes). */
  async _pedirReanalise(quais) {
    const url = this.projeto ? `/api/projetos/${encodeURIComponent(this.projeto)}/reanalisar` : '/api/modelo/reanalisar';
    const assinatura = this._assinaturaDoModelo();
    const corpo = JSON.stringify({ documento: this.documento.paraJSON(), ...(quais ? { quais } : {}) });
    for (let tentativa = 1; ; tentativa++) {
      let resp;
      try {
        resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: corpo });
      } catch (e) {                                          // a conexão caiu: o servidor saiu do ar no meio
        if (tentativa >= 3 || !(await this._esperarServidor())) {
          this.aviso(`Reanalisar estrutura: o servidor não respondeu (${e.message}). Tente de novo.`, 'erro', 0);
          return null;
        }
        this.dica('O servidor reiniciou no meio da conta — refazendo a reanálise…');
        continue;
      }
      try {
        const r = await resp.json();
        if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
        r._assinatura = assinatura;
        r._quais = quais;
        return r;
      } catch (e) {
        this.aviso(`Reanalisar estrutura: ${e.message}`, 'erro', 0);
        return null;
      }
    }
  }

  /** Espera o servidor voltar (até 90 s); true se voltou. */
  async _esperarServidor(limiteMs = 90000) {
    const t0 = Date.now();
    this.dica('O servidor saiu do ar no meio da conta — esperando ele voltar…');
    while (Date.now() - t0 < limiteMs) {
      await new Promise(ok => setTimeout(ok, 1000));
      try { if ((await fetch('/api/versao', { cache: 'no-store' })).ok) return true; } catch (e) { /* ainda fora do ar */ }
    }
    return false;
  }

  _fecharReanalise() {
    if (this._painelReanalise) { this._painelReanalise.remove(); this._painelReanalise = null; }
  }

  _verPecas(ids, texto) {
    const vivos = (ids || []).filter(id => this.documento.entidades.has(id));
    if (!vivos.length) { this.aviso('Essas peças não estão mais no modelo.', 'atencao'); return; }
    this.selecao.definir(vivos);
    this.cena.destacar(vivos);
    this._destaqueAtivo = true;
    this.camera.zoomSelecao(vivos);
    this.dica(`${texto} — ${vivos.length} peça(s) selecionada(s). Delete apaga; Esc limpa a seleção.`);
  }

  _listaDeAchados(regra) {
    const ul = el('ul');
    for (const a of regra.achados || []) {
      ul.append(el('li', { texto: a.texto, title: 'Selecionar e enquadrar', onclick: () => this._verPecas(a.ids, a.texto) }));
    }
    if (regra.mais) ul.append(el('li', { class: 'mais', texto: `… e mais ${regra.mais.toLocaleString('pt-BR')}` }));
    return ul;
  }

  /** O painel da prévia (`aplicado`: depois de aplicar, só o que ficou para conferir). */
  _mostrarReanalise(r, aplicado = false) {
    this._fecharReanalise();
    const regras = r.regras || [];
    const corrige = regras.filter(g => g.tipo === 'corrige');
    const aponta = regras.filter(g => g.tipo === 'aponta' && g.n);
    const marcadas = new Set(corrige.filter(g => g.n).map(g => g.chave));
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    const nCorrige = corrige.reduce((s, g) => s + g.n, 0);
    const botaoAplicar = el('button', { type: 'button', class: 'aplicar-reanalise', onclick: () => this._aplicarReanalise(r, [...marcadas]) });
    const atualizarBotao = () => {
      const n = corrige.filter(g => marcadas.has(g.chave)).reduce((s, g) => s + g.n, 0);
      botaoAplicar.textContent = n ? `Aplicar as marcadas (${n.toLocaleString('pt-BR')})` : 'Nada marcado';
      botaoAplicar.disabled = !n;
    };
    if (!aplicado) {
      corpo.append(el('p', { texto: nCorrige
        ? `${nCorrige.toLocaleString('pt-BR')} correção(ões) em ${(r.resumo?.pecas || 0).toLocaleString('pt-BR')} peças, pelas regras de hoje. ` +
          'As edições do 3D ficam; peça bloqueada não é tocada. Clique num item para ver a peça. Ctrl+Z desfaz tudo de uma vez.'
        : 'Nada a corrigir: o modelo já está dentro das regras de hoje.' }));
      corpo.append(el('div', { class: 'reanalise-secao', texto: 'Corrige' }));
      for (const g of corrige) {
        if (!g.n) {
          corpo.append(el('div', { class: 'reanalise-ok', texto: `✓ ${g.titulo}: nada a corrigir` }));
          continue;
        }
        const caixa = el('input', { type: 'checkbox', checked: true, title: 'Marcar para aplicar',
          onclick: (ev) => ev.stopPropagation(),
          onchange: (ev) => { if (ev.target.checked) marcadas.add(g.chave); else marcadas.delete(g.chave); atualizarBotao(); } });
        const det = el('details', { open: false });
        det.append(el('summary', {}, caixa, ` ${g.titulo} (${g.n.toLocaleString('pt-BR')})`));
        det.append(el('div', { class: 'reanalise-expl', texto: g.explicacao }));
        det.append(el('button', { type: 'button', class: 'reanalise-sel', texto: 'Selecionar todas',
          onclick: () => this._verPecas((g.achados || []).flatMap(a => a.ids.slice(0, 1)), g.titulo) }));
        det.append(this._listaDeAchados(g));
        corpo.append(det);
      }
      atualizarBotao();
      if (nCorrige) corpo.append(el('div', { class: 'reanalise-acoes' }, botaoAplicar));
    } else {
      corpo.append(el('p', { texto: 'Aplicado. Ctrl+Z desfaz tudo de uma vez. O que segue não muda sozinho — confira com o projeto:' }));
    }
    if (aponta.length) {
      corpo.append(el('div', { class: 'reanalise-secao', texto: 'Para conferir (não muda sozinho)' }));
      for (const g of aponta) {
        const det = el('details', { open: false });
        det.append(el('summary', { texto: `${g.titulo} (${g.n.toLocaleString('pt-BR')})` }));
        det.append(el('div', { class: 'reanalise-expl', texto: g.explicacao }));
        if (g.chave === 'apoios') {
          det.append(el('button', { type: 'button', class: 'reanalise-sel', texto: 'Abrir no Verificar apoios',
            onclick: () => { this._fecharReanalise(); this.verificarApoios(); } }));
        }
        if ((g.grupos || []).length) {
          // as peças iguais juntas (perfil e tamanho): a escora de projeto se reconhece pelo grupo grande e repetido
          const ul = el('ul', { class: 'reanalise-grupos' });
          for (const gr of g.grupos) {
            ul.append(el('li', { texto: `${gr.grupo} (${gr.n.toLocaleString('pt-BR')})`, title: 'Selecionar o grupo inteiro',
              onclick: () => this._verPecas(gr.ids, gr.grupo) }));
          }
          det.append(ul);
        } else {
          det.append(this._listaDeAchados(g));
        }
        corpo.append(det);
      }
    }
    this._painelReanalise = el('div', { class: 'painel-apoios painel-reanalise' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: 'Reanalisar estrutura' }),
        el('button', { type: 'button', texto: 'Analisar de novo', onclick: () => this.reanalisarEstrutura() }),
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharReanalise() })),
      corpo);
    (this.el.palco || document.body).append(this._painelReanalise);
  }

  /** Aplica as regras marcadas numa entrada de desfazer. Se o modelo mudou depois da prévia, ou só parte das regras foi
   *  marcada, o servidor refaz a conta com o modelo de agora (as regras dependem umas das outras). */
  async _aplicarReanalise(previa, quais) {
    let r = previa;
    const todas = (previa.regras || []).filter(g => g.tipo === 'corrige' && g.n).map(g => g.chave);
    const a0 = previa._assinatura || {};
    const a1 = this._assinaturaDoModelo();
    const mudou = a0.ultimo !== a1.ultimo || a0.feitos !== a1.feitos || a0.desfeitos !== a1.desfeitos;
    if (mudou || quais.length !== todas.length) {
      this.dica('Reanalisando só com as regras marcadas…');
      r = await this._pedirReanalise(quais);
      if (!r) return;
    }
    if (!Object.keys(r.alterar || {}).length && !(r.remover || []).length && !(r.novas || []).length) {
      this.aviso('Reanalisar estrutura: nada a mudar.', 'info');
      this._mostrarReanalise(r, true);
      return;
    }
    this.dica(`Aplicando as correções em ${(Object.keys(r.alterar || {}).length + (r.remover || []).length).toLocaleString('pt-BR')} peça(s)…`);
    await this._numerarAsNovas(r);                       // a peça que mudou de perfil fica com a marca conferida
    const cmd = this._comandoDaLigacao(r, 'Reanalisar estrutura');
    if (cmd) this.executar(cmd);
    // o carimbo: com que versão das regras o modelo passou (o modelo antigo se reconhece por ele)
    this.documento.metadados = { ...(this.documento.metadados || {}), reanalise: r.carimbo };
    const z = r.resumo || {};
    this.aviso(`Reanalisar estrutura: ${(z.alteradas || 0).toLocaleString('pt-BR')} peça(s) corrigida(s), ` +
      `${(z.removidas || 0).toLocaleString('pt-BR')} tirada(s). Ctrl+Z desfaz.`, 'info', 15000);
    this._mostrarReanalise(r, true);
  }
}
