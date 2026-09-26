// Métodos do editor 3D: Painel de propriedades, camadas, busca de peças e cor por grupo.
//
// Saíram de editor.js (que tinha quase 5 mil linhas) sem mudar o corpo: esta classe só
// guarda os métodos, e editor.js os copia para Editor.prototype (aplicarMetodos).

import { PAPEIS, areaDaChapa, comprimentoDaBarra, direcaoDaBarra, escalar, somar } from '../nucleo/documento.js';
import { lerPerfil } from '../nucleo/trocar_perfil.js';
import { $, ComandoAparencia, contarPor, corDeGrupo, corHex, dimensoesPrincipais, el, metros, normalizarBusca, numero, ponto3, uniao, volumeDe } from '../editor.js';

export class MetodosPaineis {
  // ---------------------------------------------------------- propriedades

  _painelPropriedades() {
    const raiz = this.el.props;
    const foco = document.activeElement;
    if (foco && raiz.contains(foco) && (foco.tagName === 'INPUT' || foco.tagName === 'SELECT') &&
        foco.type !== 'checkbox') {
      this._propsPendente = true;
      return;
    }
    this._propsPendente = false;
    raiz.replaceChildren();
    const ents = this.selecao.entidades;
    // ferramenta com opções (o parafuso a lançar): no topo do painel
    if (this.ativa && typeof this.ativa.painel === 'function') {
      try { this.ativa.painel(raiz, el); } catch (e) { console.error('painel da ferramenta:', e); }
      if (!ents.length) return;
    }
    if (!ents.length) { this._propsPadroes(raiz); return; }

    const ids = ents.map(e => e.id);
    const um = ents.length === 1 ? ents[0] : null;
    const tipos = contarPor(ents, e => e.tipo);
    const nomeTipo = { barra: 'Barra', chapa: 'Chapa', solido: 'Sólido', grupo: 'Grupo' };
    const titulo = um ? (um.nome || nomeTipo[um.tipo] || um.tipo)
                      : `${ents.length} objetos`;
    const sub = um ? `${nomeTipo[um.tipo] || um.tipo} · ${um.id}`
                   : [...tipos].map(([t, n]) => `${n} ${nomeTipo[t] || t}`).join(' · ');
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: titulo }),
                   el('span', { texto: sub })));

    const comum = (campo) => {
      const v = ents[0][campo];
      return ents.every(e => JSON.stringify(e[campo]) === JSON.stringify(v)) ? v : undefined;
    };
    const aplicar = (campos, rotulo) => this.alterarEntidades(ids, campos, rotulo);

    // --- gerais ---
    const g = el('div', { class: 'campos' });
    if (um) {
      g.append(el('label', { texto: 'Nome' }), this._texto(um.nome || '', v =>
        aplicar({ nome: v }, 'Renomear')));
    }
    g.append(el('label', { texto: 'Camada' }),
      this._lista([...this.documento.camadas.keys()], comum('camada'),
                  v => aplicar({ camada: v }, `Mover para a camada ${v}`)));
    g.append(el('label', { texto: 'Material' }),
      this._lista([['', 'pela camada'], ...[...this.documento.materiais.keys()].map(m => [m, m])],
                  comum('material'), v => aplicar({ material: v }, v ? `Aplicar ${v}` : 'Material pela camada')));
    raiz.append(g);

    const todas = (t) => ents.every(e => e.tipo === t);

    if (todas('barra')) {
      const gb = this._grupo(raiz, 'Barra');
      gb.append(el('label', { texto: 'Perfil' }),
        this._buscaPerfil(comum('perfil'), (nome) => aplicar({ perfil: nome }, `Trocar perfil para ${nome}`)));
      gb.append(el('label', { texto: 'Aço' }),
        this._lista(uniao(this.catalogo.acos, ents.map(e => e.aco)), comum('aco'),
                    v => aplicar({ aco: v }, `Aço ${v}`)));
      gb.append(el('label', { texto: 'Papel' }),
        this._lista(uniao(PAPEIS, ents.map(e => e.papel)), comum('papel'),
                    v => aplicar({ papel: v }, `Papel ${v}`)));
      gb.append(el('label', { texto: 'Rotação (°)' }),
        this._num(comum('rotacao'), v => aplicar({ rotacao: v }, 'Girar seção'), { passo: 15 }));
      const massaTotal = ents.reduce((s, e) => s + this._massaBarra(e), 0);
      if (um) {
        gb.append(el('label', { texto: 'Comprimento' }),
          this._num(Math.round(comprimentoDaBarra(um) * 10) / 10, v => {
            if (!(v > 0)) { this.aviso('O comprimento precisa ser positivo.', 'atencao'); return; }
            const fim = somar(um.inicio, escalar(direcaoDaBarra(um), v));
            aplicar({ fim }, 'Alterar comprimento');
          }, { unidade: 'mm' }));
        gb.append(el('label', { texto: 'Recorte início' }),
          this._num(um.recorte_inicio || 0, v => aplicar({ recorte_inicio: v }, 'Recorte no início')));
        gb.append(el('label', { texto: 'Recorte fim' }),
          this._num(um.recorte_fim || 0, v => aplicar({ recorte_fim: v }, 'Recorte no fim')));
        gb.append(el('label', { texto: 'Início' }), el('span', { class: 'valor', texto: ponto3(um.inicio) }));
        gb.append(el('label', { texto: 'Fim' }), el('span', { class: 'valor', texto: ponto3(um.fim) }));
      } else {
        const total = ents.reduce((s, e) => s + comprimentoDaBarra(e), 0);
        gb.append(el('label', { texto: 'Comprimento' }), el('span', { class: 'valor', texto: `${metros(total)} m no total` }));
      }
      gb.append(el('label', { texto: 'Massa' }),
        el('span', { class: 'valor', texto: massaTotal ? `${numero(massaTotal, 1)} kg` : '—' }));
    }

    if (todas('chapa')) {
      const gc = this._grupo(raiz, 'Chapa');
      gc.append(el('label', { texto: 'Espessura' }),
        this._num(comum('espessura'), v => {
          if (!(v > 0)) { this.aviso('A espessura precisa ser positiva.', 'atencao'); return; }
          aplicar({ espessura: v }, `Espessura ${numero(v, 1)} mm`);
        }, { unidade: 'mm' }));
      gc.append(el('label', { texto: 'Aço' }),
        this._lista(uniao(this.catalogo.acos, ents.map(e => e.aco)), comum('aco'),
                    v => aplicar({ aco: v }, `Aço ${v}`)));
      gc.append(el('label', { texto: 'Centrada' }),
        this._lista([['sim', 'sim — cresce para os dois lados'], ['nao', 'não — cresce para a normal']],
                    comum('centrada') === undefined ? undefined : (comum('centrada') === false ? 'nao' : 'sim'),
                    v => aplicar({ centrada: v === 'sim' }, 'Posição da espessura')));
      const massa = ents.reduce((s, e) => s + areaDaChapa(e) * (e.espessura || 0) * 7.85e-6, 0);
      if (um) {
        gc.append(el('label', { texto: 'Área' }), el('span', { class: 'valor', texto: `${numero(areaDaChapa(um) / 1e6, 4)} m²` }));
        gc.append(el('label', { texto: 'Furos' }), el('span', { class: 'valor', texto: String((um.furos || []).length) }));
        gc.append(el('label', { texto: 'Origem' }), el('span', { class: 'valor', texto: ponto3(um.origem) }));
      }
      gc.append(el('label', { texto: 'Massa' }), el('span', { class: 'valor', texto: `${numero(massa, 1)} kg` }));
    }

    const marcasDe = (e) => (e && e.atributos && e.atributos.marcas) || null;
    if (um && (um.tipo === 'solido' || marcasDe(um))) {
      // peça importada de IFC (sólido, ou chapa já convertida em paramétrica): marcas,
      // nome de produção com a quantidade; no sólido, dimensões pelos eixos e massa
      const a = um.atributos || {}, marcas = a.marcas || {};
      if (marcas.posicao || marcas.conjunto || marcas.perfil || a.tipo_ifc) {
        const gi = this._grupo(raiz, 'Peça (IFC)');
        const linha = (rotulo, valor, acao) => {
          const v = el('span', { class: 'valor' + (acao ? ' clicavel' : ''), texto: String(valor), title: acao ? 'Clique: selecionar todas com o mesmo valor' : undefined });
          if (acao) v.addEventListener('click', acao);
          gi.append(el('label', { texto: rotulo }), v);
        };
        // o que o detalhamento escreve no título da célula: "S.T.2 – 49x (P13)"
        const chaveQtd = marcas.nome ? ['nome', marcas.nome] : marcas.posicao ? ['posicao', marcas.posicao] : null;
        if (chaveQtd) {
          const iguaisQtd = [...this.documento.entidades.values()].filter(e => { const m = marcasDe(e); return m && m[chaveQtd[0]] === chaveQtd[1]; }).map(e => e.id);
          const titulo = `${marcas.nome || marcas.posicao} – ${String(iguaisQtd.length).padStart(2, '0')}x` + (marcas.nome && marcas.posicao ? `  (${marcas.posicao})` : '');
          const t = el('div', { class: 'titulo-peca clicavel', texto: titulo, title: 'Quantidade no modelo — clique para selecionar todas',
            style: 'grid-column:1/-1;font-weight:600;font-size:1.05em;margin:.1em 0 .3em;cursor:pointer' });
          t.addEventListener('click', () => this.selecao.definir(iguaisQtd));
          gi.append(t);
        }
        // o nome e a quantidade vêm antes dos campos de edição (na chapa o grupo dela é longo)
        const caixa = gi.parentElement, primeiro = raiz.querySelector('.grupo-campos');
        if (caixa && primeiro && primeiro !== caixa) primeiro.before(caixa);
        if (marcas.posicao) {
          const iguais = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao === marcas.posicao).map(e => e.id);
          linha('Posição', `${marcas.posicao}  (${iguais.length} iguais)`, () => this.selecao.definir(iguais));
        }
        if (marcas.conjunto) {
          const doConj = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.conjunto === marcas.conjunto).map(e => e.id);
          linha('Conjunto', `${marcas.conjunto}  (${doConj.length} peças)`, () => this.selecao.definir(doConj));
        }
        // nome de produção dado pelo detalhamento (S.T.1, T.C.2-A…), quando já existe
        if (marcas.nome) {
          const mesmos = [...this.documento.entidades.values()].filter(e => e.atributos && e.atributos.marcas && e.atributos.marcas.nome === marcas.nome).map(e => e.id);
          linha('Nome', `${marcas.nome}  (${mesmos.length} peças)`, () => this.selecao.definir(mesmos));
        }
        if (marcas.nome_conjunto && marcas.nome_conjunto !== marcas.nome) linha('Nome do conjunto', marcas.nome_conjunto);
        if (marcas.perfil) {
          linha('Perfil', marcas.perfil);
          // perfil do projeto (o do IFC) e cada troca, com a data
          const trocas = (um.atributos && um.atributos.trocas_de_perfil) || [];
          const original = marcas.perfil_original || marcas.perfil_anterior;
          if (original && original !== marcas.perfil) linha('Perfil original', original);
          for (const t of trocas) {
            const dia = String(t.data || '').slice(0, 10).split('-').reverse().join('/');
            linha('Troca de perfil', `${dia}  ${t.de} → ${t.para}`);
          }
          if (lerPerfil(marcas.perfil)) {
            gi.append(el('span'), el('button', { type: 'button', class: 'mini', texto: 'Trocar perfil…',
              title: 'Troca o perfil desta peça, da posição inteira ou de todas com este perfil — a malha 3D muda de seção e os desenhos saem com o perfil novo',
              onclick: () => this.dialogoTrocarPerfil([um.id]) }));
          }
        }
        if (a.tipo_ifc) linha('Tipo IFC', a.tipo_ifc);
        if (um.tipo === 'solido' && this._ehParafuso(um)) {
          gi.append(el('span'), el('button', { type: 'button', class: 'mini', texto: 'Trocar parafuso…',
            title: 'Troca o diâmetro, o comprimento e a classe deste parafuso (ou de todos iguais a ele) — a peça 3D muda no mesmo lugar, e os furos abertos pelo editor acompanham o diâmetro',
            onclick: () => this.dialogoTrocarParafuso([um.id]) }));
        }
        if (um.tipo === 'solido') {
          const dims = dimensoesPrincipais(um);
          if (dims) {
            linha('Comprimento', `${numero(dims[0], 0)} mm`);
            linha('Seção (envolvente)', `${numero(dims[1], 0)} × ${numero(dims[2], 1)} mm`);
          }
          linha('Massa', `${numero(volumeDe(um) * 7.85e-6, 2)} kg`);
        }
      }
    }
    if (um && um.tipo === 'solido') {
      const gs = this._grupo(raiz, 'Sólido');
      gs.append(el('label', { texto: 'Vértices' }), el('span', { class: 'valor', texto: String((um.vertices || []).length) }));
      gs.append(el('label', { texto: 'Faces' }), el('span', { class: 'valor', texto: String((um.faces || []).length) }));
      gs.append(el('label', { texto: 'Volume' }), el('span', { class: 'valor', texto: `${numero(volumeDe(um) / 1e9, 4)} m³` }));
      if (um.origem_ifc) gs.append(el('label', { texto: 'GlobalId' }), el('span', { class: 'valor', texto: um.origem_ifc }));
    } else if (ents.length > 1 && ents.every(e => e.tipo === 'solido')) {
      const gs = this._grupo(raiz, 'Sólidos');
      const massa = ents.reduce((s, e) => s + volumeDe(e) * 7.85e-6, 0);
      gs.append(el('label', { texto: 'Massa' }), el('span', { class: 'valor', texto: `${numero(massa, 1)} kg no total` }));
      const perfisSel = new Set(ents.map(e => e.atributos && e.atributos.marcas && e.atributos.marcas.perfil).filter(Boolean));
      if (perfisSel.size === 1 && lerPerfil([...perfisSel][0])) {
        gs.append(el('span'), el('button', { type: 'button', class: 'mini', texto: 'Trocar perfil…',
          title: 'Troca o perfil das peças selecionadas (a malha 3D muda de seção)', onclick: () => this.dialogoTrocarPerfil(ents.map(e => e.id)) }));
      }
      if (ents.every(e => this._ehParafuso(e))) {
        gs.append(el('span'), el('button', { type: 'button', class: 'mini', texto: 'Trocar parafuso…',
          title: 'Troca o diâmetro, o comprimento e a classe dos parafusos selecionados', onclick: () => this.dialogoTrocarParafuso(ents.map(e => e.id)) }));
      }
      const pos = new Set(ents.map(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao).filter(Boolean));
      if (pos.size) gs.append(el('label', { texto: 'Posições' }), el('span', { class: 'valor', texto: [...pos].slice(0, 12).join(', ') + (pos.size > 12 ? ' …' : '') }));
    }

    const acoes = el('div', { class: 'acoes-painel' });
    const botao = (texto, fn, titulo) => acoes.append(el('button', { type: 'button', texto, title: titulo, onclick: fn }));
    botao('Zoom', () => this.camera.zoomSelecao(ids), 'Enquadrar a seleção');
    if (!this._isolamento) botao('Isolar', () => this.isolarSelecao(), 'Mostra só a seleção para editar; "Voltar ao modelo" traz o resto de volta');
    if (um) botao('Semelhantes', () => this.selecao.semelhantes(um.id), 'Mesmo tipo e mesmo perfil');
    botao('Mesma camada', () => this.selecao.porCamada(ents[0].camada));
    if (comum('perfil')) botao('Mesmo perfil', () => this.selecao.porPerfil(comum('perfil')));
    const posSel = new Set(ents.map(e => e.atributos && e.atributos.marcas && e.atributos.marcas.posicao).filter(Boolean));
    if (this.projeto && posSel.size && posSel.size <= 30) {
      botao('Atualizar peça', () => this.atualizarPecas([...posSel]),
            'Leva os furos das barras às chapas e aos parafusos desta ligação e redesenha só estas peças nos desenhos de detalhamento, sem gerar tudo de novo');
    }
    botao('Apagar', () => this.apagarSelecao(), 'Del');
    raiz.append(acoes);
  }

  /** Sem seleção: os padrões que as ferramentas de desenho usam, e o resumo do modelo. */
  _propsPadroes(raiz) {
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Nada selecionado' }),
                   el('span', { texto: 'padrões de desenho' })));
    const g = el('div', { class: 'campos' });
    g.append(el('label', { texto: 'Perfil' }),
      this._buscaPerfil(this.perfilAtivo, n => { this.definirPerfilAtivo(n); this.dica(`Perfil ativo: ${n}`); }));
    g.append(el('label', { texto: 'Aço' }),
      this._lista(uniao(this.catalogo.acos, [this.acoAtivo]), this.acoAtivo, v => { this.acoAtivo = v; }));
    g.append(el('label', { texto: 'Papel' }),
      this._lista(PAPEIS, this.papelAtivo, v => { this.papelAtivo = v; }));
    g.append(el('label', { texto: 'Camada' }),
      this._lista([...this.documento.camadas.keys()], this.camadaAtiva,
                  v => { this.camadaAtiva = v; this._agendarPaineis('camadas'); }));
    raiz.append(g);

    const est = this.documento.estatisticas();
    const massa = this.documento.barras.reduce((s, e) => s + this._massaBarra(e), 0) +
      this.documento.chapas.reduce((s, e) => s + areaDaChapa(e) * (e.espessura || 0) * 7.85e-6, 0) +
      (this.documento.solidos || []).reduce((s, e) => s + (Number((e.atributos || {}).peso_kg) || 0), 0);
    const gm = this._grupo(raiz, 'Modelo');
    const linha = (r, v) => gm.append(el('label', { texto: r }), el('span', { class: 'valor', texto: v }));
    linha('Objetos', numero(est.entidades));
    linha('Barras', numero(est.barras));
    linha('Chapas', numero(est.chapas));
    linha('Sólidos', numero(est.solidos));
    linha('Aço estimado', massa ? `${numero(massa / 1000, 2)} t` : '—');
  }

  _massaBarra(b) {
    const p = this.cena.perfil(b.perfil);
    if (p && p.massa) return p.massa * comprimentoDaBarra(b) / 1000;
    // perfil que o editor não traz (dobrado de fábrica, do catálogo dos fornecedores): o
    // peso que o gerador do modelo gravou na peça
    return Number((b.atributos || {}).peso_kg) || 0;
  }

  _grupo(raiz, titulo) {
    const g = el('div', { class: 'campos' });
    raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: titulo }), g));
    return g;
  }

  _texto(valor, aoMudar) {
    const i = el('input', { type: 'text', value: valor, spellcheck: 'false' });
    i.addEventListener('change', () => aoMudar(i.value.trim()));
    i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') i.blur(); });
    return i;
  }

  _num(valor, aoMudar, { passo = 'any', unidade = '' } = {}) {
    const i = el('input', { type: 'number', step: passo, title: unidade });
    if (valor === undefined) i.placeholder = 'vários';
    else i.value = Math.round(Number(valor) * 1000) / 1000;
    i.addEventListener('change', () => {
      const v = parseFloat(String(i.value).replace(',', '.'));
      if (isFinite(v)) aoMudar(v);
    });
    i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') i.blur(); });
    return i;
  }

  /** Select; `opcoes` é lista de valores ou de pares [valor, rótulo]. */
  _lista(opcoes, valor, aoMudar) {
    const s = el('select');
    if (valor === undefined) s.append(el('option', { value: '', texto: '— vários —', selected: true, disabled: true }));
    for (const o of opcoes) {
      const [v, r] = Array.isArray(o) ? o : [o, o];
      s.append(el('option', { value: v, texto: r, selected: valor !== undefined && v === (valor ?? '') }));
    }
    s.addEventListener('change', () => aoMudar(s.value));
    return s;
  }

  /** Campo de perfil com busca no catálogo. */
  _buscaPerfil(valor, aoEscolher) {
    const caixa = el('div', { class: 'busca-perfil' });
    const entrada = el('input', { type: 'search', value: valor ?? '', spellcheck: 'false',
                                  placeholder: valor === undefined ? 'vários — buscar…' : 'buscar perfil…' });
    const lista = el('div', { class: 'lista-perfis', role: 'listbox' });
    let achados = [], marcado = 0;
    const desenhar = () => {
      lista.replaceChildren();
      achados.forEach((p, i) => {
        const dim = p.tipo === 'L' ? `${numero(p.bf, 1)}×${numero(p.tw, 2)}`
                  : p.tipo === 'tubo' ? `Ø${numero(p.d, 1)}×${numero(p.tw, 2)}`
                  : `${numero(p.d, 0)}×${numero(p.bf, 0)}`;
        lista.append(el('button', {
          type: 'button', class: i === marcado ? 'ativo' : '',
          onmousedown: (ev) => { ev.preventDefault(); escolher(p.nome); },
        }, el('span', { texto: p.nome }), el('span', { class: 'dim', texto: `${dim} · ${numero(p.massa, 1)} kg/m` })));
      });
    };
    const filtrar = () => {
      const q = normalizarBusca(entrada.value);
      const todos = this.catalogo.perfis || [];
      achados = (q ? todos.filter(p => normalizarBusca(p.nome).includes(q)) : todos).slice(0, 40);
      marcado = 0;
      desenhar();
    };
    const escolher = (nome) => {
      entrada.value = nome;
      lista.replaceChildren();
      entrada.blur();
      aoEscolher(nome);
    };
    entrada.addEventListener('focus', () => { entrada.select(); filtrar(); });
    entrada.addEventListener('input', filtrar);
    entrada.addEventListener('blur', () => setTimeout(() => {
      lista.replaceChildren();
      if (valor !== undefined && !achados.some(p => p.nome === entrada.value)) entrada.value = valor;
    }, 120));
    entrada.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown') { marcado = Math.min(achados.length - 1, marcado + 1); desenhar(); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp') { marcado = Math.max(0, marcado - 1); desenhar(); ev.preventDefault(); }
      else if (ev.key === 'Enter') { ev.preventDefault(); if (achados[marcado]) escolher(achados[marcado].nome); }
      else if (ev.key === 'Escape') { lista.replaceChildren(); entrada.blur(); }
    });
    caixa.append(entrada, lista);
    return caixa;
  }

  // --------------------------------------------------------------- camadas

  _painelCamadas() {
    const raiz = this.el.camadas;
    raiz.replaceChildren();
    raiz.append(this._seletorCorPor());
    const cont = this.documento.contagemPorCamada();
    const lista = el('div', { class: 'lista-linhas' });
    const olho = (vis) => vis
      ? '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3" opacity=".45"/><path d="M3 13L13 3" stroke="currentColor" stroke-width="1.3"/></svg>';
    const cadeado = (b) => b
      ? '<svg width="13" height="13" viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" fill="currentColor"/><path d="M5 7V5a3 3 0 0 1 6 0v2" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>'
      : '<svg width="13" height="13" viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/><path d="M5 7V5a3 3 0 0 1 5.6-1.5" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/></svg>';
    for (const [nome, c] of this.documento.camadas) {
      const linha = el('div', { class: 'linha', title: 'Clique: camada ativa · duplo clique: selecionar o que está nela' });
      if (c.visivel === false) linha.dataset.oculta = '';
      if (nome === this.camadaAtiva) linha.dataset.ativa = '';
      const vis = el('button', { type: 'button', class: 'alternador', 'aria-pressed': String(c.visivel !== false),
        title: c.visivel === false ? 'Mostrar' : 'Ocultar',
        onclick: () => this.executar(new ComandoAparencia('camadas', nome, { visivel: c.visivel === false },
                                     `${c.visivel === false ? 'Mostrar' : 'Ocultar'} camada ${nome}`)) });
      vis.innerHTML = olho(c.visivel !== false);
      const cor = el('input', { type: 'color', value: corHex(c.cor), title: 'Cor da camada' });
      cor.addEventListener('change', () => this.executar(
        new ComandoAparencia('camadas', nome, { cor: cor.value }, `Cor da camada ${nome}`)));
      const rotulo = el('span', { class: 'nome', texto: nome });
      linha.addEventListener('click', (ev) => {
        if (ev.target.closest('button, input')) return;
        this.camadaAtiva = nome;
        this._agendarPaineis('camadas', 'props');
        this.dica(`Camada ativa: ${nome}`);
      });
      linha.addEventListener('dblclick', (ev) => {
        if (ev.target.closest('button, input')) return;
        this.selecao.porCamada(nome, ev.shiftKey);
      });
      const trava = el('button', { type: 'button', class: 'alternador', 'aria-pressed': String(!!c.bloqueada),
        title: c.bloqueada ? 'Desbloquear' : 'Bloquear',
        onclick: () => this.executar(new ComandoAparencia('camadas', nome, { bloqueada: !c.bloqueada },
                                     `${c.bloqueada ? 'Desbloquear' : 'Bloquear'} camada ${nome}`)) });
      trava.innerHTML = cadeado(!!c.bloqueada);
      linha.append(vis, cor, rotulo, el('span', { class: 'contagem', texto: numero(cont.get(nome) || 0) }), trava);
      lista.append(linha);
    }
    raiz.append(lista);
    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: '+ Nova camada', onclick: () => this._novaCamada() }));
    acoes.append(el('button', { type: 'button', texto: 'Mostrar todas', onclick: () => {
      for (const [nome, c] of this.documento.camadas) {
        if (c.visivel === false) this.executar(new ComandoAparencia('camadas', nome, { visivel: true }, 'Mostrar todas'));
      }
    } }));
    raiz.append(acoes);
  }

  // ------------------------------------------------------------ pesquisa de peças

  /**
   * Campo de pesquisa do topo: procura em nome, posição, conjunto, perfil, camada, tipo
   * IFC e GlobalId; várias palavras são "e". Os resultados saem agrupados por posição
   * (marca da peça) — ou por nome, quando não há marca — com a contagem e a cor do
   * grupo. Clique seleciona o grupo, duplo clique enquadra, Enter seleciona tudo.
   */
  /**
   * Peças achadas na busca: selecionadas e em destaque — o resto do modelo esmaece, para
   * se ver onde elas estão no projeto (o mesmo do "Ver no 3D"). Esc, ou limpar a busca,
   * devolve o modelo. `enquadrar` aproxima a câmera delas.
   */
  _destacarEncontradas(ids, enquadrar = false) {
    if (!ids || !ids.length) return;
    this.selecao.definir(ids);
    this.cena.destacar(ids);
    this._destaqueAtivo = true;
    if (enquadrar) this.camera.zoomSelecao(ids);
    this.dica(`${ids.length} peça(s) em destaque; o resto do modelo está esmaecido. Esc devolve o modelo · duplo clique no resultado enquadra.`);
  }

  _ligarBusca() {
    const campo = document.getElementById('busca-campo');
    const caixa = document.getElementById('busca-resultados');
    if (!campo || !caixa) return;
    let timer = null, ativo = -1, grupos = [];
    const fechar = () => { caixa.hidden = true; ativo = -1; };
    const render = () => {
      const termo = campo.value.trim();
      caixa.replaceChildren();
      if (!termo) { fechar(); return; }
      const r = this.pesquisarPecas(termo);
      grupos = r.grupos;
      caixa.hidden = false;
      const cabeca = el('div', { class: 'cabeca' },
        el('span', { texto: r.total ? `${numero(r.total)} peça(s) em ${numero(grupos.length)} grupo(s)` : 'Nada encontrado' }));
      if (r.total) {
        cabeca.append(el('button', { type: 'button', texto: 'Selecionar tudo', onclick: () => { this._destacarEncontradas(r.ids, true); fechar(); } }));
      }
      caixa.append(cabeca);
      if (!r.total) { caixa.append(el('div', { class: 'nada', texto: 'Tente parte do nome, a posição (P12), o conjunto (M2) ou o perfil.' })); return; }
      grupos.slice(0, 80).forEach((g, i) => {
        const item = el('div', { class: 'item', title: 'Clique: selecionar · duplo clique: enquadrar' },
          el('span', { class: 'amostra', style: `background:${g.cor}` }),
          el('span', { class: 'nome' }, g.chave, el('small', { texto: g.detalhe })),
          el('span', { class: 'contagem', texto: numero(g.ids.length) }));
        item.addEventListener('click', (ev) => {
          const ids = ev.shiftKey ? [...new Set([...this.selecao.ids, ...g.ids])] : g.ids;
          this._destacarEncontradas(ids); ativo = i; realcar();
        });
        item.addEventListener('dblclick', () => this._destacarEncontradas(g.ids, true));
        caixa.append(item);
      });
      if (grupos.length > 80) caixa.append(el('div', { class: 'nada', texto: `… e mais ${grupos.length - 80} grupo(s): refine a pesquisa.` }));
    };
    const realcar = () => { [...caixa.querySelectorAll('.item')].forEach((e, i) => e.classList.toggle('ativo', i === ativo)); };
    campo.addEventListener('input', () => {
      clearTimeout(timer); timer = setTimeout(render, 160);
      // limpou a busca (o × do campo): o modelo volta inteiro
      if (!campo.value.trim() && this._destaqueAtivo) { this._destaqueAtivo = false; this.cena.destacar(null); }
    });
    campo.addEventListener('focus', () => { if (campo.value.trim()) render(); });
    campo.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        campo.value = ''; fechar(); campo.blur();
        if (this._destaqueAtivo) { this._destaqueAtivo = false; this.cena.destacar(null); this.selecao.definir([]); }
        return;
      }
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        ev.preventDefault();
        if (!grupos.length) return;
        ativo = (ativo + (ev.key === 'ArrowDown' ? 1 : -1) + grupos.length) % grupos.length;
        this._destacarEncontradas(grupos[ativo].ids); realcar();
        const e = caixa.querySelectorAll('.item')[ativo]; if (e) e.scrollIntoView({ block: 'nearest' });
        return;
      }
      if (ev.key === 'Enter') {
        ev.preventDefault();
        const ids = ativo >= 0 && grupos[ativo] ? grupos[ativo].ids : grupos.flatMap(g => g.ids);
        if (ids.length) this._destacarEncontradas(ids, true);
        fechar();
      }
    });
    document.addEventListener('click', (ev) => { if (!ev.target.closest('#busca-pecas')) fechar(); });
    document.addEventListener('keydown', (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'f') { ev.preventDefault(); campo.focus(); campo.select(); }
    });
  }

  /** Peças cujo texto casa com todas as palavras do termo; agrupadas por posição ou nome. */
  pesquisarPecas(termo) {
    const palavras = termo.toLowerCase().split(/\s+/).filter(Boolean);
    const grupos = new Map();
    let total = 0;
    const ids = [];
    for (const ent of this.documento.entidades.values()) {
      const a = ent.atributos || {}, m = a.marcas || {};
      const texto = [ent.nome, m.posicao, m.conjunto, m.nome, m.nome_conjunto, m.perfil, ent.perfil, ent.camada, a.tipo_ifc, ent.origem_ifc, ent.papel]
        .filter(Boolean).join(' ').toLowerCase();
      if (!palavras.every(p => texto.includes(p))) continue;
      total++; ids.push(ent.id);
      const chave = m.posicao || ent.nome || ent.tipo;
      let g = grupos.get(chave);
      if (!g) {
        const detalhe = [m.perfil && m.perfil !== chave ? m.perfil : (ent.perfil || ''), m.conjunto ? `conj. ${m.conjunto}` : '', ent.camada].filter(Boolean).join(' · ');
        g = { chave, detalhe, ids: [], cor: '#7d8a9e' };
        grupos.set(chave, g);
      }
      g.ids.push(ent.id);
    }
    const lista = [...grupos.values()].sort((x, y) => y.ids.length - x.ids.length || String(x.chave).localeCompare(String(y.chave), 'pt-BR', { numeric: true }));
    const cores = this._coresGrupo;
    for (const g of lista) {
      const ent = this.documento.entidades.get(g.ids[0]);
      const chaveCor = this._chaveDeGrupo(ent, this.corPor || 'padrao');
      if (cores && chaveCor != null && cores.has(chaveCor)) g.cor = cores.get(chaveCor);
    }
    return { total, ids, grupos: lista };
  }

  // ------------------------------------------------------------ cor por grupo

  /** Chave de agrupamento de uma entidade no modo pedido, ou null quando não tem. */
  _chaveDeGrupo(ent, modo) {
    const marcas = (ent.atributos && ent.atributos.marcas) || {};
    switch (modo) {
      case 'conjunto': return marcas.conjunto || null;
      case 'posicao': return marcas.posicao || null;
      case 'perfil': return ent.perfil || marcas.perfil || ent.nome || null;
      case 'tipo': return (ent.atributos && ent.atributos.tipo_ifc) || ent.papel || ent.tipo || null;
      default: return null;
    }
  }

  /**
   * Pinta o modelo por grupo (conjunto de montagem, posição, perfil ou tipo IFC), com
   * uma cor por chave. Entra pela mesma porta do mapa de esforços, `definirCorPorValor`,
   * então liga-se um ou outro: pedir um grupo esconde a análise, e mostrar a análise
   * volta este seletor ao padrão. A paleta é atribuída na ordem em que as chaves
   * aparecem e fica guardada, para a legenda e a cena concordarem.
   */
  _aplicarCorPor() {
    const modo = this.corPor || 'padrao';
    if (modo === 'padrao') {
      this._coresGrupo = null;
      if (!(this.analiseEstado && this.analiseEstado.ligado)) this.cena.definirCorPorValor(null);
      return;
    }
    if (this.analiseEstado && this.analiseEstado.ligado) this._mostrarAnalise(false);
    const cores = new Map();
    this._coresGrupo = cores;
    this.cena.definirCorPorValor((ent) => {
      const chave = this._chaveDeGrupo(ent, modo);
      if (chave == null) return null;
      if (!cores.has(chave)) cores.set(chave, corDeGrupo(cores.size));
      return cores.get(chave);
    });
  }

  _seletorCorPor() {
    const modo = this.corPor || 'padrao';
    const opcoes = [['padrao', 'camada e material'], ['conjunto', 'conjunto de montagem'],
                    ['posicao', 'posição (marca da peça)'], ['perfil', 'perfil'], ['tipo', 'tipo IFC']];
    const sel = el('select', { title: 'Pinta cada peça pela cor do grupo a que pertence' },
      ...opcoes.map(([v, t]) => el('option', { value: v, texto: t, selected: v === modo ? 'selected' : undefined })));
    sel.value = modo;
    sel.addEventListener('change', () => {
      this.corPor = sel.value;
      this._aplicarCorPor();
      this._agendarPaineis('camadas');
      this.dica(sel.value === 'padrao' ? 'Cores de camada e material.'
                                       : `Peças pintadas por ${opcoes.find(o => o[0] === sel.value)[1]}.`);
    });
    const caixa = el('div', { class: 'cor-por' }, el('label', { texto: 'Colorir por' }), sel);
    if (modo === 'padrao') return caixa;

    // legenda: uma linha por grupo, com contagem; clique seleciona, duplo clique enquadra
    const grupos = new Map();
    for (const ent of this.documento.entidades.values()) {
      const chave = this._chaveDeGrupo(ent, modo);
      if (chave == null) continue;
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(ent.id);
    }
    const cores = this._coresGrupo || new Map();
    const chaves = [...grupos.keys()].sort((a, b) =>
      String(a).localeCompare(String(b), 'pt-BR', { numeric: true }));
    const lista = el('div', { class: 'lista-linhas legenda-grupos' });
    const LIMITE = 400;
    for (const chave of chaves.slice(0, LIMITE)) {
      if (!cores.has(chave)) cores.set(chave, corDeGrupo(cores.size));
      const ids = grupos.get(chave);
      const linha = el('div', { class: 'linha', title: 'Clique: selecionar o grupo · Shift: somar · duplo clique: enquadrar' },
        el('span', { class: 'amostra', style: `background:${cores.get(chave)}` }),
        el('span', { class: 'nome', texto: String(chave) }),
        el('span', { class: 'contagem', texto: numero(ids.length) }));
      linha.addEventListener('click', (ev) => (ev.shiftKey ? this.selecao.somar(ids) : this.selecao.definir(ids)));
      linha.addEventListener('dblclick', () => { this.selecao.definir(ids); this.camera.zoomSelecao(ids); });
      lista.append(linha);
    }
    const semGrupo = this.documento.entidades.size - [...grupos.values()].reduce((s, v) => s + v.length, 0);
    caixa.append(el('div', { class: 'nota-grupos', texto:
      `${numero(grupos.size)} grupo(s)` + (semGrupo ? ` · ${numero(semGrupo)} peça(s) sem ${modo} ficam em cinza` : '') +
      (chaves.length > LIMITE ? ` · legenda mostra os ${LIMITE} primeiros` : '') }), lista);
    return caixa;
  }
}
