// Barra estrutural: dois cliques definem o eixo, o perfil vem do painel.
//
// É a ferramenta que diferencia este editor de um modelador genérico: o que sai
// daqui não é um sólido, é uma `Barra` com perfil de catálogo, aço e papel — o
// desenho, o peso e o tipo IFC saem disso. Durante o traçado a seção aparece em
// prévia nas duas pontas; as setas cima/baixo trocam o perfil sem sair da
// ferramenta; ao terminar um segmento, o próximo começa do ponto final, para
// lançar um pórtico inteiro sem recomeçar.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';
// os papéis do núcleo (os que o detalhamento usa: banzo, montante, diagonal, corrente…), não uma cópia daqui
import { baseDaBarra, PAPEIS } from '../nucleo/documento.js';

export class FerramentaBarra extends Ferramenta {
  static id = 'barra';
  static nome = 'Barra';
  static atalho = 'B';
  static grupo = 'estrutura';
  static dica = 'Clique no início da barra';
  //: rotação da seção (°) das próximas barras — a boca do U, a aba da cantoneira
  static rotacao = 0;
  //: ponto de inserção (F6, 14/10): o que fica na linha dos cliques — na altura (eixo, face de cima, meio, face de baixo)
  //: e na largura (eixo, face esquerda, meio, face direita; esquerda olhando do 1º clique para o 2º), mais os afastamentos
  //: em mm (para cima e para a esquerda). A terça pela face de baixo sobre o banzo, a viga pelo topo no nível.
  static insercao = { altura: 'eixo', largura: 'eixo', da: 0, dl: 0 };
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 4.5h6M7 4.5v15M4 19.5h6"/><path d="M14 8.5h6M17 8.5v7M14 15.5h6"/><path d="M10.5 12h3" stroke-dasharray="2 1.5"/></svg>`;

  ativar() {
    this.inicio = null;
    this.atual = null;
    this.eixo = null;
    this.dica(this.dicaComPerfil('Clique no início da barra'));
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  // ------------------------------------------------------------- painel

  get perfis() { return C.perfisDoCatalogo(this.editor); }

  get perfilAtivo() {
    const e = this.editor || {};
    if (e.perfilAtivo) return e.perfilAtivo;
    const l = this.perfis;
    return l.length ? l[0].nome : 'W 310×38,7';
  }

  set perfilAtivo(nome) {
    if (!this.editor) return;
    if (typeof this.editor.definirPerfilAtivo === 'function') this.editor.definirPerfilAtivo(nome);
    else this.editor.perfilAtivo = nome;
  }

  get registroDoPerfil() {
    return this.perfis.find(p => p.nome === this.perfilAtivo) || null;
  }

  get acoAtivo() { return (this.editor && this.editor.acoAtivo) || 'ASTM A572 Gr.50'; }
  get papelAtivo() { return (this.editor && this.editor.papelAtivo) || 'viga'; }

  /** O papel da barra de `a` a `b`: o escolhido; sem escolha (o "viga" de partida), a barra em pé é pilar — o pilar
   *  desenhado com B, ↑ e 3000 saía "viga" e ia assim para o cálculo e o detalhamento (teste de fluxo, 15/10). */
  papelPara(a, b) {
    const p = this.papelAtivo;
    if (p !== 'viga' || (this.editor && this.editor._papelEscolhido) || !a || !b) return p;
    const L = C.dist(a, b);
    return L > 1e-6 && Math.abs(b[2] - a[2]) / L > 0.95 ? 'pilar' : p;
  }

  get rotacaoAtiva() { return this.constructor.rotacao || 0; }

  get insercao() { return { altura: 'eixo', largura: 'eixo', da: 0, dl: 0, ...(this.constructor.insercao || {}) }; }

  /**
   * O eixo da barra para a linha clicada de `a` a `b`: a seção (na base da barra, com a rotação) é levada para que o
   * ponto escolhido dela fique na linha, mais os afastamentos. O modelo continua guardando o eixo do perfil — o cálculo, o
   * IFC e o detalhamento leem a barra como sempre. {a, b, desloc}.
   */
  eixoDaInsercao(a, b) {
    const ins = this.insercao;
    if (ins.altura === 'eixo' && ins.largura === 'eixo' && !ins.da && !ins.dl) return { a, b, desloc: [0, 0, 0] };
    if (C.iguais(a, b, 1e-6)) return { a, b, desloc: [0, 0, 0] };
    const contorno = C.secaoDoPerfil(this.registroDoPerfil, this.editor && this.editor.cena, this.perfilAtivo);
    const xs = contorno.map(q => q[0]), ys = contorno.map(q => q[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    // u aponta para a esquerda de quem anda do 1º clique para o 2º (u = z × t); v para cima
    const refL = { eixo: 0, esquerda: x1, meio: (x0 + x1) / 2, direita: x0 }[ins.largura] || 0;
    const refA = { eixo: 0, cima: y1, meio: (y0 + y1) / 2, baixo: y0 }[ins.altura] || 0;
    const { u, v } = baseDaBarra(a, b, this.rotacaoAtiva);
    const desloc = C.add(C.mul(u, -refL + (ins.dl || 0)), C.mul(v, -refA + (ins.da || 0)));
    return { a: C.add(a, desloc), b: C.add(b, desloc), desloc };
  }

  dicaComPerfil(texto) {
    const rot = this.rotacaoAtiva ? ` · ${this.rotacaoAtiva}°` : '';
    return `${texto} — ${this.perfilAtivo} · ${this.papelAtivo}${rot} (perfil, papel e rotação no painel; ↑↓ os perfis do modelo antes do 1º clique, depois ↑ trava Z)`;
  }

  /** Perfis que o modelo já usa, do mais comum para o menos. */
  _usadosNoModelo() {
    const cont = new Map();
    for (const e of this.documento.entidades.values()) if (e.tipo === 'barra' && e.perfil) cont.set(e.perfil, (cont.get(e.perfil) || 0) + 1);
    return [...cont].sort((a, b) => b[1] - a[1]);
  }

  trocarPerfil(passo) {
    // ↑↓ percorre os perfis que o modelo já usa (o catálogo inteiro são ~5.200: andar nele de um em um não serve)
    const usados = this._usadosNoModelo().map(([n]) => ({ nome: n }));
    const l = usados.length >= 2 ? usados : this.perfis;
    if (!l.length) return;
    let i = l.findIndex(p => p.nome === this.perfilAtivo);
    if (i < 0) i = passo > 0 ? -1 : 0;
    i = (i + passo + l.length) % l.length;
    this.perfilAtivo = l[i].nome;
    this.desenhar();
    this.dica(this.dicaComPerfil(this.inicio ? 'Clique no fim da barra' : 'Clique no início da barra'));
  }

  // ------------------------------------------------------------- painel

  painel(raiz, el) {
    const ed = this.editor;
    raiz.append(el('div', { class: 'resumo-selecao' }, el('strong', { texto: 'Barra a lançar' }),
                   el('span', { texto: `${this.perfilAtivo} · ${this.papelAtivo} · ${this.rotacaoAtiva}°` })));
    const g = el('div', { class: 'campos' });
    const aoTrocar = () => { this.desenhar(); this.dica(this.dicaComPerfil(this.inicio ? 'Clique no fim da barra' : 'Clique no início da barra')); };
    if (typeof ed._buscaPerfil === 'function') {
      g.append(el('label', { texto: 'Perfil' }), ed._buscaPerfil(this.perfilAtivo, n => { this.perfilAtivo = n; aoTrocar(); }));
    }
    const lista = (opcoes, atual, fn, titulo) => {
      const s = el('select', { title: titulo });
      for (const o of opcoes) s.append(el('option', { value: String(o), texto: String(o) }));
      s.value = String(atual);
      s.addEventListener('change', () => fn(s.value));
      return s;
    };
    const acos = [...new Set([...((ed.catalogo && ed.catalogo.acos) || []), this.acoAtivo])];
    g.append(el('label', { texto: 'Papel' }), lista(PAPEIS, this.papelAtivo, v => { ed.papelAtivo = v; ed._papelEscolhido = true; aoTrocar(); }, 'Papel estrutural (vai para o cálculo e o detalhamento)'),
             el('label', { texto: 'Aço' }), lista(acos, this.acoAtivo, v => { ed.acoAtivo = v; }, 'Aço da barra'),
             el('label', { texto: 'Rotação (°)' }),
             lista([0, 90, 180, 270], [0, 90, 180, 270].includes(this.rotacaoAtiva) ? this.rotacaoAtiva : 0,
                   v => { this.constructor.rotacao = +v; aoTrocar(); },
                   'Giro da seção no próprio eixo: a boca do U, a aba da cantoneira (o Virar perfil muda depois)'));
    raiz.append(g);
    // o ponto de inserção: o que fica na linha dos cliques
    const ins = this.constructor.insercao = { ...this.insercao };
    const opc = (pares, atual, fn, titulo) => {
      const s = el('select', { title: titulo });
      for (const [v, t] of pares) s.append(el('option', { value: v, texto: t }));
      s.value = atual;
      s.addEventListener('change', () => fn(s.value));
      return s;
    };
    const num_ = (chave, titulo) => {
      const i = el('input', { type: 'number', step: '1', value: String(ins[chave] || 0), title: titulo, style: 'width:5em' });
      i.addEventListener('change', () => { ins[chave] = +i.value || 0; aoTrocar(); });
      return i;
    };
    const gi = el('div', { class: 'campos' });
    gi.append(el('label', { texto: 'Na altura' }),
              opc([['eixo', 'eixo do perfil'], ['cima', 'face de cima na linha'], ['meio', 'meio da altura na linha'], ['baixo', 'face de baixo na linha']],
                  ins.altura, v => { ins.altura = v; aoTrocar(); }, 'O que fica na linha dos cliques, na altura da seção (a terça sobre o banzo: face de baixo)'),
              el('label', { texto: 'Na largura' }),
              opc([['eixo', 'eixo do perfil'], ['esquerda', 'face esquerda na linha'], ['meio', 'meio da largura na linha'], ['direita', 'face direita na linha']],
                  ins.largura, v => { ins.largura = v; aoTrocar(); }, 'O que fica na linha dos cliques, na largura (esquerda olhando do 1º clique para o 2º)'),
              el('label', { texto: 'Afastamentos (mm)' }),
              el('span', {}, '↑ ', num_('da', 'Afastamento para cima (na altura da seção), mm'), '  ← ', num_('dl', 'Afastamento para a esquerda (na largura), mm')));
    raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Ponto de inserção' }), gi));
    const usados = this._usadosNoModelo().slice(0, 12);
    if (usados.length) {
      const box = el('div', { class: 'acoes' });
      for (const [n, k] of usados) {
        box.append(el('button', { type: 'button', texto: `${n} (${k})`, title: 'Lançar com este perfil, como os que já estão no modelo',
          onclick: () => { this.perfilAtivo = n; aoTrocar(); } }));
      }
      raiz.append(el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Já usados no modelo' }), box));
    }
  }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    this.atual = this.resolver(p.ponto);
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    const q = this.resolver(p.ponto);
    if (!this.inicio) {
      this.inicio = q;
      C.ancorar(this.editor, q);
      this.dica(this.dicaComPerfil('Clique no fim da barra ou digite o comprimento'));
      this.desenhar();
      return;
    }
    if (C.iguais(this.inicio, q, 1)) return;
    this.criar(this.inicio, q);
  }

  onValor(texto) {
    const t = String(texto).trim().toLowerCase();
    const papel = t === 'terca' ? 'terça' : t;
    if (PAPEIS.includes(papel)) {
      if (this.editor) { this.editor.papelAtivo = papel; this.editor._papelEscolhido = true; }
      this.dica(this.dicaComPerfil(this.inicio ? 'Clique no fim da barra' : 'Clique no início da barra'));
      return true;
    }
    if (!this.inicio) return false;
    const d = paraMilimetros(t);
    if (!isFinite(d) || d <= 0) return false;
    let dir = this.eixo ? C.EIXOS[this.eixo].vetor
            : (this.atual && !C.iguais(this.atual, this.inicio, 1e-6))
              ? C.sub(this.atual, this.inicio) : null;
    if (!dir) return false;
    dir = C.normalizar(dir);
    // o mouse precisa estar claramente do lado de trás (1 mm): parado sobre a âncora, o resto numérico mandava o pilar para baixo (fluxo, 15/10)
    if (this.eixo && this.atual && C.dot(C.sub(this.atual, this.inicio), dir) < -1) dir = C.mul(dir, -1);
    this.criar(this.inicio, C.add(this.inicio, C.mul(dir, d)));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    // depois do 1º clique as setas travam o eixo, como em toda ferramenta (↑ Z para o pilar, ↓ solta); antes dele, ↑↓
    // percorrem os perfis do modelo (teste de fluxo, 15/10: o pilar não saía na vertical e o ↑ trocava o perfil)
    if (this.inicio && (ev.key === 'ArrowUp' || ev.key === 'ArrowDown')) { C.teclaDeEixo(this, ev); this.desenhar(); return true; }
    if (ev.key === 'ArrowUp') { this.trocarPerfil(+1); return true; }
    if (ev.key === 'ArrowDown') { this.trocarPerfil(-1); return true; }
    // ← e → travam X e Y (convenção da inferência do núcleo)
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') { C.teclaDeEixo(this, ev); this.desenhar(); return true; }
    if (ev.key === 'PageUp' || ev.key === 'PageDown') {
      // papel estrutural, sem sair da ferramenta
      const i = PAPEIS.indexOf(this.papelAtivo);
      const j = (i + (ev.key === 'PageUp' ? 1 : -1) + PAPEIS.length) % PAPEIS.length;
      if (this.editor) { this.editor.papelAtivo = PAPEIS[j]; this.editor._papelEscolhido = true; }
      this.dica(this.dicaComPerfil('Papel: ' + PAPEIS[j]));
      return true;
    }
    if (ev.key === 'Enter') { this.reiniciar(); this.dica(this.dicaComPerfil('Clique no início da barra')); return true; }
    return false;
  }

  cancelar() {
    if (this.inicio) { this.reiniciar(); this.dica(this.dicaComPerfil('Clique no início da barra')); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  resolver(ponto) {
    if (!this.inicio || !this.eixo) return C.copiar(ponto);
    return C.projetarNoEixo(this.inicio, ponto, this.eixo);
  }

  /** Referencial da seção: o mesmo triedro da barra criada (`baseDaBarra`, com a rotação) — antes o limiar do vertical
   *  era outro (0,98 × 0,9) e a prévia de uma barra quase vertical saía girada em relação à peça. */
  referencial(a, b) {
    const { t, u, v } = baseDaBarra(a, b, this.rotacaoAtiva);
    return { d: t, ey: u, ez: v };
  }

  criar(a, b) {
    const ei = this.eixoDaInsercao(a, b);
    const ent = {
      tipo: 'barra', id: C.novoId('b'),
      nome: '', camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura',
      material: '', visivel: true, bloqueada: false, grupo: '',
      inicio: C.copiar(ei.a), fim: C.copiar(ei.b),
      perfil: this.perfilAtivo, rotacao: this.rotacaoAtiva,
      papel: this.papelPara(ei.a, ei.b), aco: this.acoAtivo,
      recorte_inicio: 0, recorte_fim: 0, atributos: {},
    };
    this.executar(C.cmdAdicionar(ent, 'Criar barra'));
    // continua do ponto final, como a ferramenta de linha
    this.inicio = C.copiar(b);
    C.ancorar(this.editor, b);
    this.atual = null;
    this.limparPrevia();
    this.medida(`${formatar(C.dist(a, b))} · ${this.perfilAtivo}`);
    this.dica(this.dicaComPerfil('Continue a partir do fim, ou Enter/Esc para parar'));
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.inicio = null; this.atual = null; this.eixo = null;
    this.limparPrevia();
    this.medida('');
  }

  /** Contorno da seção transportado para uma estação do eixo. */
  secaoEm(ponto, ref, contorno) {
    return contorno.map(([u, v]) => C.add(ponto, C.add(C.mul(ref.ey, u), C.mul(ref.ez, v))));
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.inicio) g.add(C.gPonto(this.inicio, C.CORES.estrutura));
    if (!this.inicio || !this.atual) {
      if (this.atual) g.add(C.gPonto(this.atual, C.CORES.estrutura));
      this.previa(g);
      return;
    }
    const a = this.inicio, b = this.atual;
    if (C.iguais(a, b, 1e-6)) { this.previa(g); return; }
    const ref = this.referencial(a, b);
    const contorno = C.secaoDoPerfil(this.registroDoPerfil, this.editor && this.editor.cena, this.perfilAtivo);
    const ei = this.eixoDaInsercao(a, b);
    const sa = this.secaoEm(ei.a, ref, contorno);
    const sb = this.secaoEm(ei.b, ref, contorno);
    const cor = this.eixo ? C.EIXOS[this.eixo].cor : C.CORES.estrutura;
    g.add(C.gLinha(sa, cor, { fechada: true }));
    g.add(C.gLinha(sb, cor, { fechada: true }));
    for (let i = 0; i < sa.length; i++) g.add(C.gLinha([sa[i], sb[i]], cor));
    // o corpo do perfil, translúcido (as faces ao longo dele): a peça "cheia" enquanto desenha, como no Tekla
    const n = sa.length;
    g.add(C.gSuperficie([...sa, ...sb], sa.map((_, i) => [i, (i + 1) % n, n + (i + 1) % n, n + i]), cor, 0.22));
    g.add(C.gLinha([a, b], C.CORES.desenho, { tracejada: true }));
    if (C.comp(ei.desloc) > 0.5) g.add(C.gLinha([ei.a, ei.b], C.CORES.guia, { tracejada: true }));   // o eixo do perfil
    const L = C.dist(a, b);
    const reg = this.registroDoPerfil;
    const peso = reg && reg.massa
      ? `  ·  ${(reg.massa * L / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kg`
      : '';
    const papel = this.papelPara(a, b);
    const texto = `${formatar(L)}  ·  ${this.perfilAtivo}  ·  ${papel}${papel !== this.papelAtivo ? ' (em pé)' : ''}${peso}`;
    this.medida(texto);
    g.add(C.gRotulo(texto, C.meio(a, b), '#4b5563'));
    this.previa(g);
  }
}

export default FerramentaBarra;
