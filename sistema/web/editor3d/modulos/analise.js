// Métodos do editor 3D: Cálculo da estrutura, mapa de esforços e painel da análise.
//
// Saíram de editor.js (que tinha quase 5 mil linhas) sem mudar o corpo: esta classe só
// guarda os métodos, e editor.js os copia para Editor.prototype (aplicarMetodos).

import { $, GRANDEZAS_PADRAO, RAMPA_APROVEITAMENTO, RAMPA_ESFORCOS, ROTA_ANALISE, corDaRampa, el, listarEmPortugues, metros, numero } from '../editor.js';

export class MetodosAnalise {
  /**
   * "Calcular estrutura": na primeira vez roda a análise no servidor; nas seguintes só
   * mostra ou esconde o que já foi calculado. Nada de esforços aparece na cena antes de
   * o usuário pedir.
   */
  async alternarAnalise() {
    if (this._calculando) return false;
    if (this.analise) { this._mostrarAnalise(!this.analiseEstado.ligado); return true; }
    return this.calcularEstrutura();
  }

  /** Pede os esforços ao servidor. `forcar` refaz mesmo havendo resultado guardado. */
  async calcularEstrutura({ forcar = false } = {}) {
    if (this._calculando) return false;
    if (this.analise && !forcar) { this._mostrarAnalise(true); return true; }
    if (!this._dadosGalpao) {
      if (this.projeto) return this._calcularProjetoImportado({ forcar });
      this.aviso('Este modelo não veio de um galpão dimensionado, então não há esforços ' +
                 'para calcular. Use Arquivo → Gerar do galpão dimensionado… e tente de novo.',
                 'atencao');
      return false;
    }
    this._calculando = true;
    this._atualizarBotaoCalcular();
    this.dica('Calculando os esforços da estrutura…');
    const geracao = ++this._geracaoAnalise;
    let payload = null, motivo = '';
    try {
      const resposta = await fetch(ROTA_ANALISE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ dados: this._dadosGalpao }),
      });
      const texto = await resposta.text();
      try { payload = texto ? JSON.parse(texto) : null; } catch { payload = null; }
      if (!resposta.ok || (payload && payload.erro)) {
        motivo = (payload && payload.erro) || `${resposta.status} ${resposta.statusText}`;
        payload = null;
      }
    } catch {
      motivo = 'o servidor não respondeu — ele ainda está no ar?';
    }
    this._calculando = false;
    if (geracao !== this._geracaoAnalise) return false;      // trocaram o modelo no meio
    if (!payload || !payload.elementos) {
      this._atualizarBotaoCalcular();
      this.aviso('Não foi possível calcular os esforços: ' +
                 (motivo || 'o servidor respondeu sem resultados.'), 'erro');
      this.dica('Análise indisponível.');
      return false;
    }
    // O módulo de desenho vem antes da primeira pintura: senão o painel nasce com a
    // escala de reserva e sem a linha dos pórticos, e só se corrige no repinte seguinte.
    await this._carregarMapa();
    return this.aplicarAnalise(payload);
  }

  /** Guarda um resultado de análise e o põe na tela. Público: a verificação usa. */
  aplicarAnalise(payload, { mostrar = true } = {}) {
    if (!payload || !payload.elementos) return false;
    this.analise = payload;
    const combos = payload.combinacoes || [];
    const inicial = combos.find(c => c.chave === 'envoltoria') || combos[0];
    this.analiseEstado = {
      combinacao: inicial ? inicial.chave : 'envoltoria',
      grandeza: 'aproveitamento',
      // `porticos` é em quantos pórticos repetir o desenho — ver `_camadasAnalise`.
      camadas: { diagramas: true, deformada: false, cargas: false, porticos: 1 },
      exagero: 50,
      ligado: false,
    };
    this._carregarMapa().then(() => {
      if (this.analise !== payload) return;      // o modelo já mudou desde o pedido
      this._aplicarAoMapa();
      this._agendarPaineis('analise');
    });
    if (!mostrar) { this._atualizarBotaoCalcular(); return true; }
    this._mostrarAnalise(true);
    const n = Object.keys(payload.elementos).length;
    const pior = this._piorAproveitamento();
    this.dica(`Análise pronta: ${numero(n)} elemento(s)` +
              (pior ? ` — pior aproveitamento ${numero(pior * 100, 0)} %.` : '.'));
    return true;
  }

  // ------------------------------------------- cálculo do modelo importado (IFC)

  /**
   * "Calcular estrutura" num projeto que veio de IFC: o servidor monta o modelo de
   * cálculo a partir dos sólidos (tesouras, terças, cargas) e devolve o mesmo mapa do
   * galpão. Os parâmetros (vento, sobrecarga, apoios) vêm de um diálogo; `trocas` refaz
   * o cálculo com outros perfis de cálculo e traz a comparação com o anterior.
   */
  async _calcularProjetoImportado({ forcar = false, trocas = null } = {}) {
    if (this._calculando) return false;
    if (this.analise && !forcar && !trocas) { this._mostrarAnalise(true); return true; }
    let corpo;
    if (trocas) {
      corpo = { trocas, comparar: true };
    } else {
      const par = await this._dialogoParametrosCalculo();
      if (!par) return false;
      corpo = { parametros: par };
    }
    this._calculando = true;
    this._atualizarBotaoCalcular();
    this.dica('Calculando a estrutura do modelo importado…');
    const parar = this._acompanharProgresso('Cálculo: ');
    const geracao = ++this._geracaoAnalise;
    let r = null;
    try {
      r = await this.api.calcularProjeto(this.projeto, corpo);
    } catch (e) {
      this.aviso(`Não foi possível calcular a estrutura: ${e.message}`, 'erro', 0);
    } finally {
      parar();
      this._calculando = false;
    }
    if (geracao !== this._geracaoAnalise) return false;
    if (!r || !r.elementos) {
      this._atualizarBotaoCalcular();
      this.dica('Cálculo indisponível.');
      return false;
    }
    await this._carregarMapa();
    const antes = r.antes;
    delete r.antes;
    this.aplicarAnalise(r);
    const res = r.resumo || {};
    const rep = res.reprovadas || [];
    const n = Object.keys(r.elementos).length;
    this.dica(`Cálculo pronto: ${numero(n)} posições verificadas, ${rep.length} reprovada(s)` +
              (res.pior_aproveitamento ? `, pior aproveitamento ${numero(res.pior_aproveitamento * 100, 0)} %.` : '.'));
    for (const t of (r.avisos || []).filter(a => !/fora do modelo/.test(a)).slice(0, 3)) this.aviso(t, 'atencao', 12000);
    if (antes) this._mostrarComparacao(antes, r, trocas);
    return true;
  }

  /**
   * "Dimensionar": o servidor calcula, escolhe em cada posição o perfil mais leve do
   * catálogo que passa (repetindo até a escolha se repetir), troca os perfis nas barras
   * do modelo do projeto — o anterior vai para o histórico — e grava o cálculo novo. Aqui:
   * gravar o que está aberto, pedir os parâmetros, mostrar o que mudou e reabrir.
   */
  async dimensionarEstrutura() {
    if (this._calculando) return false;
    if (!this.projeto) {
      this.aviso('Dimensionar trabalha no modelo de um projeto: abra o modelo pela tela de projetos.', 'atencao');
      return false;
    }
    const par = await this._dialogoParametrosCalculo({
      titulo: 'Dimensionar a estrutura', ok: 'Dimensionar',
      nota: 'Em cada posição verificada entra o perfil mais leve do catálogo (séries padrão) que passa na barra e na ligação; ' +
            'o banzo leva um perfil só por linha, e a tesoura segue as regras da fábrica do galpão (parede de 2 mm, esbeltez). ' +
            'Os perfis trocam no modelo, e o modelo atual fica no histórico. Leva de meio minuto a alguns minutos.' });
    if (!par) return false;
    try {
      const s = await this.api.salvarModeloDoProjeto(this.projeto, this.documento.paraJSON(), this._modeloAlterado);
      if (s && s.alterado) this._modeloAlterado = s.alterado;
    } catch (e) {
      this.aviso(`Não foi possível gravar o modelo antes de dimensionar: ${e.message}`, 'erro', 0);
      return false;
    }
    this._calculando = true;
    this._atualizarBotaoCalcular();
    this.dica('Dimensionando a estrutura…');
    const parar = this._acompanharProgresso('Dimensionamento: ');
    let r = null;
    try {
      r = await this.api.dimensionarProjeto(this.projeto, { parametros: par, aplicar: true });
    } catch (e) {
      this.aviso(`Não foi possível dimensionar: ${e.message}`, 'erro', 0);
    } finally {
      parar();
      this._calculando = false;
      this._atualizarBotaoCalcular();
    }
    if (!r) { this.dica(''); return false; }
    const pct = (v) => (v === null || v === undefined) ? '—' : `${numero(v * 100, 0)} %`;
    const corpo = el('div', {});
    const mud = r.mudancas || [];
    const ap = r.aplicado || {};
    const antes = r.peso_antes_kg, depois = r.peso_depois_kg;
    corpo.append(el('p', { class: 'explica', texto:
      (mud.length ? `${mud.length} posição(ões) trocaram de perfil` + (ap.barras ? ` (${numero(ap.barras)} barra(s) no modelo)` : '') : 'Nenhuma posição precisou trocar de perfil') +
      (antes != null && depois != null ? `; peso das peças verificadas ${numero(antes, 0)} → ${numero(depois, 0)} kg` : '') +
      `. Reprovadas: ${(r.reprovadas_antes || []).length} antes, ${(r.reprovadas || []).length} depois.` +
      (r.convergiu === false ? ' A escolha não se repetiu nas rodadas permitidas: ficou a última — dimensione de novo para confirmar.' : '') }));
    if (mud.length) {
      const lista = el('div', { class: 'lista-linhas comparacao dimensionamento' });
      for (const x of mud) {
        lista.append(el('div', { class: 'linha', title: `${x.de} → ${x.para}` },
          el('span', { class: 'marca', texto: x.marca }),
          el('span', { class: 'nome', texto: `${x.tipo || ''} · ${x.de} → ${x.para}` }),
          el('span', { class: 'contagem', texto: `${pct(x.aproveitamento_antes)} → ` }),
          el('span', { class: 'aprov', dados: { ok: x.ok ? '1' : '' }, texto: pct(x.aproveitamento) }),
          el('span', { class: 'contagem delta', texto: `${x.delta_kg > 0 ? '+' : ''}${numero(x.delta_kg, 0)} kg` })));
      }
      corpo.append(lista);
    }
    const pend = r.pendentes || [];
    if (pend.length) {
      corpo.append(el('p', { class: 'explica atencao', texto: `Ficaram como estavam (${pend.length}): ` +
        pend.map(x => `${x.marca} ${x.perfil} (${pct(x.aproveitamento)})`).join(', ') + ' — ' + pend[0].motivo + '.' }));
    }
    const sem = r.sem_solucao || [];
    if (sem.length) {
      corpo.append(el('p', { class: 'explica atencao', texto: `Continuam reprovadas (${sem.length}): nenhum perfil das séries padrão passa, e ficou o que chegou mais perto — ` +
        sem.map(x => `${x.marca} ${x.tipo} ${x.perfil} (${pct(x.aproveitamento)})`).join(', ') + '. Mude a solução (outro sistema, mais peças, mais travamento) nessas posições.' }));
    }
    const so = Object.entries(ap.so_calculo || {});
    if (so.length) {
      corpo.append(el('p', { class: 'explica', texto: `${so.length} posição(ões) do IFC (sólidos) ficaram só como perfil de cálculo: troque no 3D com Trocar perfil.` }));
    }
    this.dica('Dimensionamento pronto.');
    const acao = await this.dialogo({ titulo: 'Dimensionamento', corpo, ok: ap.barras ? 'Abrir o modelo com os perfis novos' : 'Fechar' });
    if (ap.barras && acao === 'ok') location.reload();
    else if (r.calculo && r.calculo.elementos) { await this._carregarMapa(); this.aplicarAnalise(r.calculo); }
    return true;
  }

  /**
   * "← Desenho 2D": volta ao desenho de onde se veio. O CAD manda o nome (`desenho=` na
   * URL); vindo de outro lugar, vale o desenho do CAD que abriu esta página, e sem nenhum
   * dos dois o CAD abre o primeiro desenho do projeto.
   */
  _ligarVoltaAoDesenho(s) {
    const a = document.getElementById('link-desenho');
    if (!a || !s) return;
    let nome = this.parametros.get('desenho') || '';
    if (!nome) {
      try {
        const ref = document.referrer ? new URL(document.referrer) : null;
        if (ref && ref.origin === location.origin && ref.pathname === '/cad') nome = ref.searchParams.get('desenho') || '';
      } catch { nome = ''; }
    }
    a.href = `/cad?projeto=${encodeURIComponent(s)}` + (nome ? `&desenho=${encodeURIComponent(nome)}` : '');
    a.hidden = false;
  }

  /** Cálculo gravado no projeto (calculo.json): entra como análise pronta, sem ligar o mapa. */
  async _carregarCalculoGravado(s) {
    let r = null;
    try { r = await this.api.calculoDoProjeto(s); } catch { r = null; }
    if (!r || !r.calculo || !r.calculo.elementos || this.projeto !== s) return;
    r.calculo.parametros = r.calculo.parametros || r.parametros || {};
    this.aplicarAnalise(r.calculo, { mostrar: false });
    this.dica(`Projeto aberto. Há um cálculo gravado${r.quando ? ` (${r.quando})` : ''}: "Mostrar análise" o traz de volta; "Recalcular" refaz.`);
  }

  /** Diálogo dos parâmetros do cálculo: vento, cargas, apoios, aços. Devolve null se cancelado. */
  async _dialogoParametrosCalculo({ titulo = 'Calcular a estrutura do modelo importado', ok = 'Calcular', nota = '' } = {}) {
    let g;
    try { g = await this.api.geometriaParaCalculo(this.projeto); }
    catch (e) { this.aviso(`Não foi possível ler o modelo para o cálculo: ${e.message}`, 'erro', 0); return null; }
    if (!g.detalhado) {
      this.aviso('Gere o detalhamento primeiro (Detalhamentos → Detalhar peças e conjuntos): é ele que ' +
                 'classifica tesouras, terças e contraventamentos para o cálculo (o modelo gerado de um desenho 2D dispensa: o papel das barras já diz).', 'atencao', 0);
      return null;
    }
    if (!g.tesouras) {
      this.aviso('O nomeador não encontrou tesouras neste modelo (conjuntos de treliça com banzos e ' +
                 'diagonais). O cálculo do modelo importado começa pelas tesouras.', 'atencao', 0);
      return null;
    }
    const padrao = { ...(g.padrao || {}), ...(g.parametros || {}) };
    if (padrao.altura_beiral == null) padrao.altura_beiral = g.cota_apoio_m;
    if (padrao.telha == null) padrao.telha = g.telha_kN_m2;
    const entradas = {};
    const grade = el('div', { class: 'campos' });
    const num = (k, rot, titulo = '') => {
      entradas[k] = el('input', { type: 'text', value: padrao[k] == null ? '' : String(padrao[k]).replace('.', ','),
                                  title: titulo, placeholder: titulo ? 'auto' : '' });
      grade.append(el('label', { texto: rot, title: titulo }), entradas[k]);
    };
    const sel = (k, rot, opcoes) => {
      const atual = padrao[k] == null ? '' : String(padrao[k]);
      const lista = opcoes.some(o => (Array.isArray(o) ? o[0] : o) === atual) || !atual ? opcoes : [[atual, atual], ...opcoes];
      entradas[k] = this._lista(lista, atual, () => {});
      grade.append(el('label', { texto: rot }), entradas[k]);
    };
    grade.append(el('h4', { texto: 'Vento (NBR 6123)', style: 'grid-column:1/-1;margin:.2em 0 0' }));
    num('v0', 'V₀ (m/s)');
    sel('categoria', 'Categoria do terreno', [['I', 'I — mar, lago'], ['II', 'II — campo aberto'], ['III', 'III — subúrbio, fazendas'], ['IV', 'IV — cidade, industrial'], ['V', 'V — centro de cidade']]);
    sel('classe', 'Classe', [['A', 'A — até 20 m'], ['B', 'B — 20 a 50 m'], ['C', 'C — mais de 50 m']]);
    sel('aberturas', 'Fechamento', [['duas faces opostas', 'fechado, duas faces permeáveis'], ['quatro faces permeáveis', 'quatro faces permeáveis (aberto)'], ['estanque', 'estanque']]);
    num('altura_beiral', 'Altura do beiral (m)', 'acima do solo; o modelo dá a cota do apoio');
    grade.append(el('h4', { texto: 'Cargas', style: 'grid-column:1/-1;margin:.4em 0 0' }));
    num('telha', 'Telha (kN/m²)', 'peso da telha por m² de cobertura');
    num('sobrecarga', 'Sobrecarga (kN/m²)', 'NBR 8800: mínimo 0,25 kN/m²');
    num('carga_extra', 'Permanente extra (kN/m²)', 'forro, instalações, tubulação pendurada');
    grade.append(el('h4', { texto: 'Travamentos e apoios', style: 'grid-column:1/-1;margin:.4em 0 0' }));
    num('correntes', 'Correntes por vão de terça', 'vazio = contadas no modelo (barras curtas que encostam na terça)');
    num('trava_inferior', 'Travamento do banzo inferior (m)', 'espaçamento dos travamentos laterais; vazio = os lidos no modelo (nenhum = banzo inteiro)');
    num('correntes_longarina', 'Correntes por vão de longarina', 'linhas de correntes das longarinas de fechamento; vazio = 1');
    sel('apoio', 'Apoios da tesoura', [['rotulado', 'rotulados nos dois lados'], ['movel', 'rotulado + móvel']]);
    grade.append(el('h4', { texto: 'Aços e critérios', style: 'grid-column:1/-1;margin:.4em 0 0' }));
    const acos = (this.catalogo && this.catalogo.acos && this.catalogo.acos.length) ? this.catalogo.acos
      : ['CIVIL 300', 'CIVIL 350', 'CF-26 (NBR 6650)', 'ASTM A36', 'ASTM A572 Gr.50'];
    sel('aco_frio', 'Aço dos formados a frio', acos.map(a => [a, a]));
    sel('aco_laminado', 'Aço dos laminados', acos.map(a => [a, a]));
    const parafusos = (this.catalogo && this.catalogo.parafusos && this.catalogo.parafusos.length) ? this.catalogo.parafusos
      : ['ASTM A307', 'ASTM A325', 'ISO 4.6', 'ISO 8.8'];
    const eletrodos = (this.catalogo && this.catalogo.eletrodos && this.catalogo.eletrodos.length) ? this.catalogo.eletrodos
      : ['E60XX', 'E70XX'];
    sel('parafuso', 'Parafusos das chapas de nó', parafusos.map(a => [a, a]));
    sel('eletrodo', 'Eletrodo das soldas', eletrodos.map(a => [a, a]));
    num('flecha_tesoura', 'Flecha da tesoura L/', '');
    num('flecha_terca', 'Flecha da terça L/', '');
    const corpo = el('div', {},
      el('p', { class: 'explica', texto: `O modelo tem ${g.tesouras} tesoura(s) (${(g.conjuntos || []).join(', ')}), ` +
        `vão ${numero(g.vao_m, 2)} m, inclinação ${numero(g.inclinacao_graus, 1)}°, apoio na cota ${numero(g.cota_apoio_m, 2)} m, ` +
        `${numero(g.barras)} barras com perfil reconhecido. O peso próprio e a telha são medidos do modelo; ` +
        'as tesouras viram pórticos planos (apoiadas no topo dos pilares do modelo), as terças vigas entre tesouras; pilares, ' +
      'longarinas, contraventamentos e correntes pelos modelos simples do galpão. Vento pela NBR 6123 nas tabelas de galpão de duas águas.' }),
      grade);
    for (const t of (g.avisos || []).slice(0, 3)) corpo.append(el('p', { class: 'explica', texto: t }));
    if (nota) corpo.prepend(el('p', { class: 'explica', texto: nota }));
    if (await this.dialogo({ titulo, corpo, ok }) !== 'ok') return null;
    const par = {};
    const numeros = ['v0', 'altura_beiral', 'telha', 'sobrecarga', 'carga_extra', 'correntes', 'trava_inferior', 'correntes_longarina', 'flecha_tesoura', 'flecha_terca'];
    for (const [k, e] of Object.entries(entradas)) {
      const v = String(e.value ?? '').trim();
      if (numeros.includes(k)) {
        const n = parseFloat(v.replace(',', '.'));
        par[k] = v === '' || !isFinite(n) ? null : n;
      } else {
        par[k] = v;
      }
    }
    return par;
  }

  /** Perfis usados no cálculo e os do catálogo, para o seletor de troca. */
  _opcoesDePerfilDeCalculo(atual) {
    const doProjeto = new Set();
    for (const info of Object.values((this.analise && this.analise.elementos) || {})) if (info.perfil) doProjeto.add(info.perfil);
    const s = el('select');
    s.append(el('option', { value: atual, texto: `${atual} (atual)`, selected: true }));
    const g1 = el('optgroup', { label: 'Perfis deste projeto' });
    for (const p of [...doProjeto].sort()) if (p !== atual) g1.append(el('option', { value: p, texto: p }));
    if (g1.children.length) s.append(g1);
    const porTipo = new Map();
    for (const p of (this.catalogo && this.catalogo.perfis) || []) {
      if (doProjeto.has(p.nome)) continue;
      if (!porTipo.has(p.tipo)) porTipo.set(p.tipo, el('optgroup', { label: `Catálogo · ${p.tipo}` }));
      porTipo.get(p.tipo).append(el('option', { value: p.nome, texto: `${p.nome} · ${numero(p.massa, 1)} kg/m` }));
    }
    for (const g of porTipo.values()) s.append(g);
    return s;
  }

  /** Bloco "Perfil de cálculo" da peça selecionada (só no modelo importado). */
  _blocoTrocaPerfil(marca, info) {
    const caixa = el('div', { class: 'campos' });
    const atual = info.perfil || '';
    const s = this._opcoesDePerfilDeCalculo(atual);
    s.title = 'Refaz o cálculo com este perfil na posição (todas as peças da marca) e mostra o que mudou';
    s.addEventListener('change', () => { if (s.value && s.value !== atual) this._trocarPerfil(marca, s.value); });
    caixa.append(el('label', { texto: 'Perfil de cálculo' }), s);
    const outro = el('input', { type: 'text', placeholder: 'ou nome de fábrica: U100X50X3.04, C150X75X20X2.25…',
                                title: 'Enter aplica' });
    outro.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && outro.value.trim()) { ev.preventDefault(); this._trocarPerfil(marca, outro.value.trim()); }
    });
    caixa.append(el('label', { texto: '' }), outro);
    const trocas = (this.analise.parametros && this.analise.parametros.trocas) || {};
    if (trocas[marca]) {
      caixa.append(el('label', { texto: 'No modelo' }),
        el('span', { class: 'valor' }, el('button', { type: 'button', texto: 'Voltar ao perfil do modelo',
          title: 'Tira a troca desta posição e recalcula',
          onclick: () => this._trocarPerfil(marca, null) })));
    }
    return caixa;
  }

  /**
   * "No lugar dela": perfis do catálogo verificados **nos esforços desta posição**, com o
   * aproveitamento que teriam e quanto mudariam no peso da estrutura. O servidor faz a
   * triagem com o cálculo já gravado (responde em décimos de segundo); clicar num deles
   * aplica a troca, e aí sim o cálculo inteiro é refeito.
   */
  _blocoAlternativas(marca) {
    const caixa = el('div', { class: 'grupo-campos' },
      el('h4', { texto: 'No lugar dela' }),
      el('div', { class: 'vazio', texto: 'Procurando no catálogo…' }));
    this.api.alternativasDePerfil(this.projeto, marca, 10).then((r) => {
      if (!caixa.isConnected) return;
      caixa.replaceChildren(el('h4', { texto: 'No lugar dela' }));
      const lista = (r && r.alternativas) || [];
      if (!lista.length) {
        caixa.append(el('div', { class: 'vazio', texto: 'Nada no catálogo serve para esta posição.' }));
        return;
      }
      const passam = lista.filter(a => a.ok).length;
      const comLig = lista.some(a => a.ligacao);
      caixa.append(el('p', { class: 'analise-descricao', texto:
        (passam ? `${numero(passam)} de ${numero(lista.length)} passam nos esforços atuais` +
                  (comLig ? ' — na barra e na ligação dela. ' : '. ')
                : 'Nenhum passa nos esforços atuais; os primeiros são os que chegam mais perto. ') +
        `A posição tem ${numero(r.comprimento_total_m, 1)} m no modelo (${numero(r.peso_kg, 0)} kg).` +
        (r.ligacao ? ` Ligação atual (${r.ligacao.chave}, ${r.ligacao.tipo}): ${numero(r.ligacao.aproveitamento * 100, 0)} %.` : '') }));
      const linhas = el('div', { class: 'lista-linhas' });
      for (const a of lista) {
        const dp = a.delta_peso_kg;
        const lig = a.ligacao;
        const linha = el('div', { class: 'linha',
          title: `${a.governa || ''}${a.norma ? ' · ' + a.norma : ''} · ${a.massa} kg/m · ` +
                 `${a.origem === 'tabela' ? 'tabela de fabricante' : 'calculado'}` +
                 (lig ? ` · ligação ${numero(lig.aproveitamento * 100, 0)} % (${lig.governa || ''})` : '') +
                 ' — clique para aplicar e recalcular',
          onclick: () => this._trocarPerfil(marca, a.nome) },
          el('span', { class: 'nome', texto: a.nome }),
          el('span', { class: 'contagem',
                       texto: dp === null || dp === undefined ? '—'
                              : `${dp > 0 ? '+' : ''}${numero(dp, 0)} kg` }),
          el('span', { class: 'aprov', dados: { ok: (a.ok_barra ?? a.ok) ? '1' : '' },
                       texto: `${numero(a.aproveitamento * 100, 0)} %` }));
        if (lig) {
          linha.append(el('span', { class: 'aprov', dados: { ok: lig.ok ? '1' : '' },
                                    title: 'ligação (chapa de nó ou solda no banzo) com este perfil',
                                    texto: `lig. ${numero(lig.aproveitamento * 100, 0)} %` }));
        }
        linhas.append(linha);
      }
      caixa.append(linhas);
      caixa.append(el('p', { class: 'analise-descricao', texto: r.aviso || '' }));
    }).catch((e) => {
      if (!caixa.isConnected) return;
      caixa.replaceChildren(el('h4', { texto: 'No lugar dela' }),
        el('div', { class: 'vazio', texto: `Não foi possível levantar as alternativas: ${e.message}` }));
    });
    return caixa;
  }

  async _trocarPerfil(marca, perfil) {
    const trocas = { ...((this.analise && this.analise.parametros && this.analise.parametros.trocas) || {}) };
    if (perfil) trocas[marca] = perfil; else delete trocas[marca];
    return this._calcularProjetoImportado({ trocas });
  }

  /** O que mudou entre o cálculo anterior e o atual (troca de perfil). */
  _mostrarComparacao(antes, r, trocas) {
    const linhas = [];
    for (const [marca, el_] of Object.entries(r.elementos || {})) {
      const a = antes[marca] || {};
      const a0 = typeof a.aproveitamento === 'number' ? a.aproveitamento : null;
      const a1 = typeof el_.aproveitamento === 'number' ? el_.aproveitamento : null;
      const mudouPerfil = a.perfil && a.perfil !== el_.perfil;
      const delta = a0 !== null && a1 !== null ? a1 - a0 : 0;
      if (!mudouPerfil && Math.abs(delta) < 0.005) continue;
      linhas.push({ marca, nome: el_.nome || '', perfil0: a.perfil || '', perfil1: el_.perfil || '', a0, a1, delta, mudouPerfil });
    }
    linhas.sort((x, y) => (y.mudouPerfil - x.mudouPerfil) || Math.abs(y.delta) - Math.abs(x.delta));
    const corpo = el('div', {});
    const pct = (v) => v === null ? '—' : `${numero(v * 100, 0)} %`;
    if (!linhas.length) {
      corpo.append(el('p', { class: 'explica', texto: 'Nenhuma peça mudou de aproveitamento.' }));
    } else {
      const lista = el('div', { class: 'lista-linhas comparacao' });
      for (const l of linhas.slice(0, 40)) {
        lista.append(el('div', { class: 'linha', title: l.mudouPerfil ? `${l.perfil0} → ${l.perfil1}` : l.perfil1 },
          el('span', { class: 'marca', texto: l.marca }),
          el('span', { class: 'nome', texto: (l.nome ? `${l.nome} · ` : '') + (l.mudouPerfil ? `${l.perfil0} → ${l.perfil1}` : l.perfil1) }),
          el('span', { class: 'contagem', texto: `${pct(l.a0)} → ` }),
          el('span', { class: 'aprov', dados: { ok: l.a1 !== null && l.a1 <= 1 ? '1' : '' }, texto: pct(l.a1) })));
      }
      corpo.append(el('p', { class: 'explica', texto: `${linhas.length} posição(ões) mudaram (as vizinhas mudam pela redistribuição dos esforços na tesoura).` }), lista);
    }
    const rep = (r.resumo && r.resumo.reprovadas) || [];
    corpo.append(el('p', { class: 'explica', texto: rep.length ? `Continuam reprovadas: ${rep.join(', ')}.` : 'Todas as posições verificadas passam.' }));
    this.dialogo({ titulo: 'Troca de perfil de cálculo: o que mudou', corpo, ok: 'Fechar' });
  }

  /** Resumo, avisos, trocas e não verificadas do cálculo do modelo importado. */
  _blocoResumoCalculo(a) {
    const caixa = el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Cálculo do modelo importado' }));
    const res = a.resumo || {};
    const v = res.vento || {};
    const campos = el('div', { class: 'campos' });
    const linha = (rot, txt) => { if (txt) campos.append(el('label', { texto: rot }), el('span', { class: 'valor quebra', texto: txt })); };
    linha('Tesouras', `${numero(res.tesouras)} (${numero(res.tipos_de_tesoura)} tipo(s)) · vão ${numero(res.vao_m, 2)} m · ${numero(res.inclinacao_graus, 1)}°`);
    linha('Terças', `${numero(res.tercas)} posição(ões)`);
    linha('Cargas', `telha ${numero(res.telha_kN_m2, 3)} · sobrecarga ${numero(res.sobrecarga_kN_m2, 2)}` +
                    (res.carga_extra_kN_m2 ? ` · extra ${numero(res.carga_extra_kN_m2, 2)}` : '') + ' kN/m²');
    if (res.peso_verificado_kg) linha('Peso verificado', `${numero(res.peso_verificado_kg, 0)} kg (barras e terças do cálculo)`);
    if (v.V0) linha('Vento', `V₀ ${numero(v.V0)} m/s · cat. ${v.categoria || ''}${v.classe || ''} · q ${numero(v.q, 3)} kN/m² · h ${numero(v.h, 2)} m`);
    const rep = res.reprovadas || [];
    campos.append(el('label', { texto: 'Reprovadas' }),
      el('span', { class: 'valor' }, el('span', { class: 'aprov', dados: { ok: rep.length ? '' : '1' },
        texto: rep.length ? `${rep.length}: ${rep.join(', ')}` : 'nenhuma' })));
    const ligs = a.ligacoes || [];
    if (ligs.length) {
      const lr = res.ligacoes_reprovadas || [];
      campos.append(el('label', { texto: 'Ligações' }),
        el('span', { class: 'valor' }, el('span', { class: 'aprov', dados: { ok: lr.length ? '' : '1' },
          texto: `${numero(ligs.length)} verificadas · ${lr.length ? `${lr.length} reprovada(s): ${lr.join(', ')}` : 'todas passam'}` +
                 (res.pior_ligacao ? ` · pior ${numero(res.pior_ligacao * 100, 0)} %` : '') })));
    }
    caixa.append(campos);
    caixa.append(el('div', { class: 'acoes-linha' },
      el('button', { type: 'button', class: 'mini', texto: 'Resultado em tela…',
        title: 'Abre o resultado completo numa tela: todas as peças com a conta de cada verificação, ligações, cargas e vento',
        onclick: () => this._abrirResultadoDaAnalise() }),
      el('button', { type: 'button', class: 'mini',
        texto: 'Dimensionar: o perfil mais leve que passa…',
        title: 'Escolhe, em cada posição, o perfil mais leve do catálogo que passa e troca no modelo',
        onclick: () => this.dimensionarEstrutura() })));
    if (ligs.length) caixa.append(this._blocoLigacoes(ligs));
    const trocas = (a.parametros && a.parametros.trocas) || {};
    const ts = Object.entries(trocas);
    if (ts.length) {
      const lista = el('div', { class: 'lista-linhas' });
      for (const [marca, perfil] of ts) {
        lista.append(el('div', { class: 'linha', title: 'perfil de cálculo diferente do modelo' },
          el('span', { class: 'marca', texto: marca }),
          el('span', { class: 'nome', texto: `→ ${perfil}` }),
          el('button', { type: 'button', texto: '✕', title: 'desfazer a troca', onclick: () => this._trocarPerfil(marca, null) })));
      }
      caixa.append(el('p', { class: 'analise-descricao', texto: 'Perfis de cálculo trocados (o sólido do modelo continua o de fábrica):' }), lista);
    }
    const avisos = a.avisos || [];
    if (avisos.length) {
      const d = el('details', {}, el('summary', { texto: `${avisos.length} aviso(s) do cálculo` }));
      for (const t of avisos) d.append(el('p', { class: 'analise-descricao', texto: t }));
      caixa.append(d);
    }
    const nv = res.nao_verificadas || [];
    if (nv.length) {
      const d = el('details', {}, el('summary', { texto: `${nv.length} posição(ões) não verificadas` }));
      d.append(el('p', { class: 'analise-descricao', texto: 'Consoles de apoio, suportes e peças sem papel reconhecido (pilar sem tesoura em cima, por exemplo).' }));
      const lista = el('div', { class: 'lista-linhas' });
      for (const x of nv.slice(0, 60)) {
        lista.append(el('div', { class: 'linha' }, el('span', { class: 'marca', texto: x.marca }),
          el('span', { class: 'nome', texto: `${x.nome ? x.nome + ' · ' : ''}${x.tipo} · ${x.perfil}` }),
          el('span', { class: 'contagem', texto: `${x.pecas}×` })));
      }
      d.append(lista);
      caixa.append(d);
    }
    return caixa;
  }

  /**
   * Ligações verificadas do modelo importado: uma linha por (chapa ou banzo × barra), com o
   * pior esforço entre todos os nós. Clique seleciona as peças (chapa e barras) no modelo,
   * duplo clique enquadra — o mesmo gesto do ranking.
   */
  _blocoLigacoes(ligs) {
    const ordem = [...ligs].sort((x, y) => (y.aproveitamento || 0) - (x.aproveitamento || 0));
    const d = el('details', {}, el('summary', { texto: `${numero(ligs.length)} ligação(ões) verificadas` }));
    const tipos = {};
    for (const x of ligs) tipos[x.tipo] = (tipos[x.tipo] || 0) + 1;
    const descr = Object.entries(tipos).map(([t, n]) => `${numero(n)} ${t}`).join(', ');
    d.append(el('p', { class: 'analise-descricao', texto:
      `Chapa de nó lida do modelo (espessura, contorno e furos); sem chapa sobre a barra, a solda dela no banzo. ${descr}. ` +
      'Ordem do pior aproveitamento para o melhor.' }));
    const lista = el('div', { class: 'lista-linhas' });
    for (const x of ordem.slice(0, 80)) {
      const det = x.tipo === 'parafusada'
        ? `${x.n_parafusos}× ${x.diametro}`
        : `perna ${numero(x.perna_mm, 1)} mm · ${numero(x.sobreposicao_mm, 0)} mm` + (x.angulo_graus ? ` · ${numero(x.angulo_graus, 0)}°` : '');
      const linha = el('div', { class: 'linha',
        title: `${x.governa || ''}${x.norma ? ' · ' + x.norma : ''} · N ${numero(x.N_kN, 1)} kN (${x.caso || ''}) · ` +
               `${x.nos} nó(s) em ${(x.tesouras || []).length} tesoura(s) — clique seleciona, duplo clique enquadra` });
      linha.append(
        el('span', { class: 'marca', texto: x.chave }),
        el('span', { class: 'nome', texto: `${x.tipo} · ${x.tipo_barra} ${x.perfil} · ${det}` }),
        el('span', { class: 'contagem', texto: `${numero(x.N_kN, 1)} kN` }),
        el('span', { class: 'aprov', dados: { ok: x.ok ? '1' : '' }, texto: `${numero(x.aproveitamento * 100, 0)} %` }));
      const ids = x.ids || [];
      linha.addEventListener('click', (ev) => { if (!ev.target.closest('button, input')) this._clicarRanking(ids, ev); });
      linha.addEventListener('dblclick', (ev) => { if (ids.length) this.camera.zoomSelecao(ids); });
      lista.append(linha);
    }
    d.append(lista);
    return d;
  }

  /** Liga ou desliga o mapa: cores e desenhos na cena, painel na coluna da direita. */
  _mostrarAnalise(ligado) {
    if (!this.analise) return;
    this.analiseEstado.ligado = !!ligado;
    if (ligado && this.corPor && this.corPor !== 'padrao') {
      // o mapa e a cor por grupo usam a mesma pintura: vale o que foi pedido por último
      this.corPor = 'padrao';
      this._coresGrupo = null;
      this._agendarPaineis('camadas');
    }
    this._comMapa(m => (ligado ? m.ligar() : m.desligar()));
    this.el.painelAnalise.hidden = !ligado;
    // Camadas e materiais cedem altura enquanto a análise está na tela: a coluna inteira
    // cabe na janela, e o painel recém-pedido não nasce cortado (regra em editor.css).
    this.el.paineis.toggleAttribute('data-analise', !!ligado);
    if (ligado) {
      // A coluna da direita é alta: sem rolar, o painel nasceria abaixo da dobra e quem
      // apertou "Calcular estrutura" não veria o resultado que pediu. Quem rola é o
      // desenho do painel: aqui o corpo ainda está vazio, e não haveria aonde rolar.
      this._rolarAteAnalise = true;
      this._agendarPaineis('analise');
    } else {
      this.el.analise.replaceChildren();
      this._linhasRanking = [];
      this.dica('Mapa de esforços oculto. O modelo voltou às cores normais.');
    }
    this._atualizarBotaoCalcular();
    this._sujo = true;
  }

  _limparAnalise() {
    this._geracaoAnalise++;
    if (this.analise) {
      this._comMapa(m => m.desligar());
      this.analise = null;
      this.analiseEstado = null;
      this._linhasRanking = [];
      if (this.el.painelAnalise) this.el.painelAnalise.hidden = true;
      if (this.el.paineis) this.el.paineis.removeAttribute('data-analise');
      if (this.el.analise) this.el.analise.replaceChildren();
      this._sujo = true;
    }
    this._atualizarBotaoCalcular();
  }

  _atualizarBotaoCalcular() {
    const ligado = !!(this.analiseEstado && this.analiseEstado.ligado);
    const rotulo = this._calculando ? 'Calculando…'
                 : ligado ? 'Ocultar análise'
                 : this.analise ? 'Mostrar análise' : 'Calcular estrutura';
    const b = this.el.calcular;
    if (b) {
      b.textContent = rotulo;
      b.disabled = this._calculando;
      b.setAttribute('aria-pressed', String(ligado));
    }
    const m = this.el.menuCalcular;
    if (m) {
      m.replaceChildren(rotulo, el('kbd', { texto: 'F9' }));
      m.disabled = this._calculando;
    }
  }

  /**
   * O desenho dos esforços mora em nucleo/analise3d.js. O import é tolerante porque o
   * painel — lista, legenda e serviço — vale por si: sem o módulo faltam só as cores na
   * cena e os diagramas.
   */
  async _carregarMapa() {
    if (this.mapa || this._mapaTentado) return this.mapa;
    this._mapaTentado = true;
    try {
      const modulo = await import('../nucleo/analise3d.js');
      if (modulo && modulo.MapaDeEsforcos) {
        this.mapa = new modulo.MapaDeEsforcos(this.cena, this.camera, this.documento);
      }
    } catch (e) {
      this._faltaMapa = String(e && e.message || e);
    }
    return this.mapa;
  }

  /** Chama o módulo de desenho sem deixar que um erro dele derrube o painel. */
  _comMapa(fn, padrao = null) {
    if (!this.mapa) return padrao;
    try { return fn(this.mapa); }
    catch (e) { this._faltaMapa = String(e && e.message || e); return padrao; }
  }

  _aplicarAoMapa() {
    const est = this.analiseEstado;
    if (!this.analise || !est) return;
    this._comMapa((m) => {
      m.definirDados(this.analise);
      m.definirCombinacao(est.combinacao);
      m.definirGrandeza(est.grandeza);
      m.definirCamadas({ ...est.camadas });
      m.definirEscalaDeformada(est.exagero);
      if (est.ligado) m.ligar(); else m.desligar();
    });
  }

  // ------------------------------------------------------------ painel

  _painelAnalise() {
    const raiz = this.el.analise;
    if (!raiz) return;
    raiz.replaceChildren();
    this._linhasRanking = [];
    const a = this.analise;
    if (!a) { raiz.append(el('div', { class: 'vazio', texto: 'Nenhuma análise calculada.' })); return; }
    const est = this.analiseEstado;
    const grandezas = (a.grandezas && a.grandezas.length) ? a.grandezas : GRANDEZAS_PADRAO;
    const combos = a.combinacoes || [];
    const atual = combos.find(c => c.chave === est.combinacao);
    const grandeza = grandezas.find(g => g.chave === est.grandeza) || grandezas[0];
    const faixa = this._faixaAnalise();

    raiz.append(el('div', { class: 'resumo-selecao' },
      el('strong', { texto: (atual && atual.nome) || 'Envoltória' }),
      el('span', { texto: faixa.percentual ? 'S/R em %'
                        : `${grandeza.nome}${faixa.unidade ? ` · ${faixa.unidade}` : ''}` })));

    const campos = el('div', { class: 'campos' });
    campos.append(el('label', { texto: 'Grandeza' }),
      this._lista(grandezas.map(g => [g.chave, g.nome]), est.grandeza, (v) => {
        est.grandeza = v;
        this._comMapa(m => m.definirGrandeza(v));
        this._agendarPaineis('analise');
        this._sujo = true;
      }));
    campos.append(el('label', { texto: 'Combinação' }), this._listaCombinacoes(combos, est));
    raiz.append(campos);
    if (atual && atual.descricao) {
      raiz.append(el('p', { class: 'analise-descricao', texto: atual.descricao }));
    }

    raiz.append(this._legendaAnalise(faixa));
    raiz.append(this._rankingAnalise(faixa));

    // Detalhe da peça selecionada: fica num nó próprio para o clique na lista poder
    // atualizá-lo sem refazer o painel inteiro (e sem fechar os seletores).
    this.el.detalheAnalise = el('div', { class: 'grupo-campos' });
    raiz.append(this.el.detalheAnalise);
    this._atualizarDetalheAnalise();

    raiz.append(this._camadasAnalise(est));
    raiz.append(this._servicoAnalise(a));
    if (a.origem === 'ifc') raiz.append(this._blocoResumoCalculo(a));

    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: 'Recalcular',
      title: 'Roda a análise de novo — use depois de mexer no modelo ou no dimensionamento',
      onclick: () => this.calcularEstrutura({ forcar: true }) }));
    acoes.append(el('button', { type: 'button', texto: 'Ocultar',
      title: 'Tira as cores e os desenhos da cena (F9)',
      onclick: () => this._mostrarAnalise(false) }));
    raiz.append(acoes);

    if (this._mapaTentado && !this.mapa) {
      raiz.append(el('p', { class: 'analise-descricao', texto:
        'O módulo de desenho não respondeu: a lista e a legenda funcionam, mas a cena ' +
        'fica sem as cores e sem os diagramas.' }));
    }

    // Só ao abrir: rolar a cada redesenho puxaria a coluna enquanto o usuário mexe nos
    // seletores.
    if (this._rolarAteAnalise) {
      this._rolarAteAnalise = false;
      this.el.painelAnalise.scrollIntoView({ block: 'start' });
    }
  }

  /** Select de combinações, com as últimas separadas das de serviço. */
  _listaCombinacoes(combos, est) {
    const s = el('select');
    const usados = new Set();
    for (const [tipo, rotulo] of [['envoltoria', ''], ['ultima', 'Combinações últimas'],
                                  ['servico', 'Combinações de serviço']]) {
      const desta = combos.filter(c => (c.tipo || 'ultima') === tipo);
      if (!desta.length) continue;
      const destino = rotulo ? el('optgroup', { label: rotulo }) : s;
      for (const c of desta) {
        usados.add(c.chave);
        destino.append(el('option', { value: c.chave, texto: c.nome || c.chave,
                                      title: c.descricao || '',
                                      selected: c.chave === est.combinacao }));
      }
      if (destino !== s) s.append(destino);
    }
    for (const c of combos.filter(c => !usados.has(c.chave))) {    // tipo novo não some
      s.append(el('option', { value: c.chave, texto: c.nome || c.chave,
                              selected: c.chave === est.combinacao }));
    }
    s.addEventListener('change', () => {
      est.combinacao = s.value;
      this._comMapa(m => m.definirCombinacao(s.value));
      this._agendarPaineis('analise');
      this._sujo = true;
    });
    return s;
  }

  /**
   * Faixa contínua de cores com os extremos e a unidade. As cores vêm do módulo de
   * desenho sempre que ele existe, para legenda e cena nunca divergirem.
   */
  _legendaAnalise(faixa) {
    const paradas = [];
    for (let i = 0; i <= 20; i++) paradas.push(this._corDaEscala(i / 20));
    const barra = el('div', { class: 'escala-cores',
                              style: `background:linear-gradient(90deg,${paradas.join(',')})` });
    if (faixa.percentual) {
      // O 100 % é a leitura que interessa: dali para cima a peça pede mais do que resiste.
      const t = (1 - faixa.min) / ((faixa.max - faixa.min) || 1);
      if (t > 0.03 && t < 0.97) {
        barra.append(el('span', { class: 'escala-marca', dados: { rotulo: '100 %' },
                                  style: `left:${(t * 100).toFixed(1)}%` }));
      }
    }
    return el('div', { class: 'grupo-campos escala' }, barra,
      el('div', { class: 'escala-extremos' },
        el('span', { texto: this._formatarValor(faixa.min, faixa) }),
        el('span', { class: 'unidade', texto: faixa.percentual ? '%' : (faixa.unidade || '') }),
        el('span', { texto: this._formatarValor(faixa.max, faixa) })));
  }

  /** As dez peças mais solicitadas na grandeza e na combinação escolhidas. */
  _rankingAnalise(faixa) {
    const caixa = el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Mais solicitadas' }));
    const itens = this._ordenarPorEsforco(10);
    if (!itens.length) {
      caixa.append(el('div', { class: 'vazio', texto: 'Sem valores nesta combinação.' }));
      return caixa;
    }
    const lista = el('div', { class: 'lista-linhas' });
    for (const item of itens) {
      const ids = item.ids || (item.id ? [item.id] : []);
      const ap = typeof item.aproveitamento === 'number' ? item.aproveitamento : null;
      // O ranking do módulo de desenho não repete `no_portico`; o verbete do elemento tem.
      const info = (this.analise.elementos || {})[item.elemento] || {};
      const fora = (item.no_portico === undefined ? info.no_portico : item.no_portico) === false;
      const linha = el('div', { class: 'linha',
        title: `${item.elemento || ''}${ids.length ? ` · ${ids.length} peça(s) no modelo` : ''}` +
               (fora ? ' · fora do modelo do pórtico: o valor não muda entre combinações' : '') +
               ' — clique seleciona, duplo clique enquadra' });
      const t = faixa.max === faixa.min ? 1 : (item.valor - faixa.min) / (faixa.max - faixa.min);
      linha.append(
        el('span', { class: 'amostra', style: `background:${this._corDaEscala(t)}` }),
        el('span', { class: 'marca', texto: item.marca || '—' }),
        el('span', { class: 'nome', texto: (info.nome ? `${info.nome} · ${info.tipo || ''}`.replace(/ · $/, '') : (item.elemento || '')) + (fora ? ' *' : '') }),
        el('span', { class: 'contagem', texto: this._formatarValor(item.valor, faixa) }));
      if (!faixa.percentual) {
        linha.append(el('span', { class: 'aprov', dados: { ok: ap !== null && ap <= 1 ? '1' : '' },
          texto: ap === null ? '—' : `${numero(ap * 100, 0)} %` }));
      }
      linha.addEventListener('click', (ev) => {
        if (ev.target.closest('button, input')) return;
        this._clicarRanking(ids, ev);
      });
      linha.addEventListener('dblclick', (ev) => {
        if (ev.target.closest('button, input') || !ids.length) return;
        this.camera.zoomSelecao(ids);
      });
      lista.append(linha);
      this._linhasRanking.push({ el: linha, ids });
    }
    caixa.append(lista);
    if (itens.some(i => i.no_portico === false)) {
      caixa.append(el('p', { class: 'analise-descricao',
        texto: '* fora do modelo do pórtico: mesmo valor em todas as combinações.' }));
    }
    return caixa;
  }

  /** Interruptores das camadas, onde desenhá-las, e o exagero da deformada. */
  _camadasAnalise(est) {
    const caixa = el('div', { class: 'grupo-campos' }, el('h4', { texto: 'Desenhos na cena' }));
    const lista = el('div', { class: 'lista-linhas' });
    for (const [chave, rotulo] of [['diagramas', 'Diagramas M/V/N'],
                                   ['deformada', 'Deformada'], ['cargas', 'Cargas em setas']]) {
      lista.append(this._interruptor(rotulo, !!est.camadas[chave], (v) => {
        est.camadas[chave] = v;
        this._comMapa(m => m.definirCamadas({ ...est.camadas }));
        // Diagramas liberam o seletor de pórticos; deformada, o campo de exagero.
        if (chave === 'diagramas' || chave === 'deformada') this._agendarPaineis('analise');
        this._sujo = true;
      }));
    }
    caixa.append(lista);

    // Os pórticos são iguais, e por isso a cena desenha num só. Sem dizer isto aqui, quem
    // olha o modelo conclui que os outros oito ficaram sem esforço.
    const campos = el('div', { class: 'campos' });
    const onde = this._lista([['1', '1 pórtico'], ['3', '3 pórticos (pontas e meio)'],
                              ['0', 'todos']],
      String(est.camadas.porticos ?? 1), (v) => {
        est.camadas.porticos = Number(v);
        this._comMapa(m => m.definirCamadas({ ...est.camadas }));
        this._agendarPaineis('analise');      // atualiza a linha do que está em exibição
        this._sujo = true;
      });
    onde.disabled = !est.camadas.diagramas;   // sem diagrama não há o que repetir
    campos.append(el('label', { texto: 'Desenhar em' }), onde);
    caixa.append(campos);

    if (est.camadas.deformada) {
      const exagero = el('div', { class: 'campos' });
      exagero.append(el('label', { texto: 'Exagero' }),
        this._num(est.exagero, (v) => {
          est.exagero = Math.max(1, v);
          this._comMapa(m => m.definirEscalaDeformada(est.exagero));
          this._sujo = true;
        }, { passo: 10, unidade: 'vezes o deslocamento real' }));
      caixa.append(exagero);
    }

    const emExibicao = this._textoPorticos(est);
    if (emExibicao) caixa.append(el('p', { class: 'analise-descricao', texto: emExibicao }));
    const tipicas = this._nomesTipicos();
    if (tipicas.length && est.camadas.diagramas) {
      caixa.append(el('p', { class: 'analise-descricao', texto:
        `${listarEmPortugues(tipicas)}: o diagrama sai numa peça típica de cada elemento, ` +
        'não em todas as peças iguais.' }));
    }
    return caixa;
  }

  /** Em que pórticos o desenho está aparecendo, em palavras. */
  _textoPorticos(est) {
    const c = est.camadas;
    if (!c.diagramas && !c.deformada && !c.cargas) return '';
    const desenhados = this._comMapa(m => m.porticosDesenhados(), []) || [];
    if (!desenhados.length) return '';
    const total = (((this.analise || {}).portico || {}).xs_mm || []).length;
    if (desenhados.length === 1) {
      const p = desenhados[0];
      return `Em exibição: pórtico ${p.indice} (x = ${metros(p.x_mm, 1)} m)` +
             (total > 1 ? `, dos ${total} iguais.` : '.');
    }
    // Com todos ligados, listar os nove números não diz nada que "todos" não diga.
    if (total && desenhados.length >= total) {
      return `Em exibição: todos os ${total} pórticos, iguais entre si.`;
    }
    return `Em exibição: pórticos ${listarEmPortugues(desenhados.map(p => String(p.indice)))}` +
           (total ? ` dos ${total}` : '') + ', todos iguais.';
  }

  /**
   * Elementos cujo diagrama sai sobre uma peça típica — terça e longarina são centenas
   * de peças iguais, e desenhar em todas não diria mais. O módulo informa quando sabe;
   * enquanto não souber, os próprios dados denunciam quem tem diagrama próprio.
   */
  _nomesTipicos() {
    const doMapa = this._comMapa(m => (typeof m.pecasTipicasDesenhadas === 'function'
      ? m.pecasTipicasDesenhadas() : null), null);
    if (Array.isArray(doMapa)) {
      const nomes = doMapa.map(p => (typeof p === 'string' ? p : (p && (p.elemento || p.nome))))
        .filter(Boolean).map(String);
      return [...new Set(nomes)];
    }
    return Object.entries(((this.analise || {}).elementos) || {})
      .filter(([, info]) => info && info.diagrama).map(([nome]) => nome);
  }

  _interruptor(rotulo, ligado, aoMudar) {
    const caixa = el('input', { type: 'checkbox' });
    caixa.checked = !!ligado;
    caixa.addEventListener('change', () => aoMudar(caixa.checked));
    return el('label', { class: 'linha interruptor' }, caixa, el('span', { class: 'nome', texto: rotulo }));
  }

  /** Deslocamento do topo contra o limite da norma, em barra de proporção. */
  _servicoAnalise(a) {
    const d = a.servico && a.servico.deslocamento;
    const caixa = el('div', { class: 'grupo-campos' });
    if (!d) return caixa;
    const razao = typeof d.razao === 'number' ? d.razao
                : (d.limite_cm ? d.u_cm / d.limite_cm : 0);
    const atende = razao <= 1;
    // Duas casas fixas nos dois: comparar "1,99" com "2" faria o limite parecer outro.
    const cm = (v) => Number(v).toLocaleString('pt-BR',
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const rente = razao > 0.95 && razao < 1.05;     // rente ao limite, a casa decimal diz
    caixa.append(el('h4', { texto: 'Serviço' }),
      el('div', { class: 'servico-linha' },
        el('span', { texto: d.rotulo || 'Deslocamento do topo' }),
        el('strong', { class: atende ? 'bom' : 'ruim', texto: `${cm(d.u_cm)} cm` })),
      el('div', { class: 'barra-servico' },
        el('span', { class: 'preenche', dados: { ok: atende ? '1' : '' },
                     style: `width:${Math.min(100, Math.max(0, razao * 100)).toFixed(1)}%` })),
      el('div', { class: 'servico-linha dim' },
        el('span', { texto: `limite ${cm(d.limite_cm)} cm` +
                            (d.criterio ? ` · ${d.criterio}` : '') }),
        el('span', { texto: `${numero(razao * 100, rente ? 1 : 0)} % do limite` })));
    return caixa;
  }

  /**
   * O que governa a peça selecionada. Mostra a verificação (Sd/Rd e norma) e, separado,
   * os esforços que dimensionaram a peça — que não são os da combinação em exibição.
   */
  _atualizarDetalheAnalise() {
    const caixa = this.el.detalheAnalise;
    if (!caixa) return;
    caixa.replaceChildren();
    const escolhido = this._elementoSelecionado();
    if (!escolhido) {
      caixa.append(el('h4', { texto: 'Peça selecionada' }),
        el('div', { class: 'vazio', texto: 'Clique numa peça da lista ou do modelo.' }));
      return;
    }
    const { nome, info, marca } = escolhido;
    caixa.append(el('h4', { texto: `Peça selecionada · ${marca || nome}` }));
    const campos = el('div', { class: 'campos' });
    const linha = (rotulo, texto, titulo) => {
      if (!texto) return;
      campos.append(el('label', { texto: rotulo }),
                    el('span', { class: 'valor quebra', title: titulo || texto, texto }));
    };
    linha('Elemento', info.titulo || nome);
    if (info.perfil) linha('Perfil', info.perfil + (info.n > 1 ? ` (${info.n} peças geminadas)` : ''));
    if (typeof info.aproveitamento === 'number') {
      campos.append(el('label', { texto: 'S/R' }),
        el('span', { class: 'valor' },
          el('span', { class: 'aprov', dados: { ok: info.aproveitamento <= 1 ? '1' : '' },
                       texto: `${numero(info.aproveitamento * 100, 0)} %` })));
    }
    linha('Governa', info.governa);
    if (typeof info.Sd === 'number' && typeof info.Rd === 'number') {
      linha('Sd / Rd', `${numero(info.Sd, 0)} / ${numero(info.Rd, 0)}` +
                       (info.unidade ? ` ${info.unidade}` : ''));
    }
    linha('Norma', info.norma);
    const dim = info.dimensionamento;
    if (dim) {
      const u = this.analise.unidades || {};
      const partes = [];
      for (const [chave, rotulo] of [['M', 'M'], ['V', 'V'], ['N', 'N']]) {
        if (typeof dim[chave] === 'number') {
          partes.push(`${rotulo} ${numero(dim[chave], 1)}${u[chave] ? ' ' + u[chave] : ''}`);
        }
      }
      if (partes.length) linha('Dimensionou', partes.join(' · '));
      if (dim.caso) linha('Caso', dim.caso);
      if (dim.Lx_cm) linha('Comprimentos', `Lx ${numero(dim.Lx_cm, 0)} cm · Ly ${numero(dim.Ly_cm, 0)} cm`);
      if (dim.vao_m) linha('Vão da terça', `${numero(dim.vao_m, 2)} m · largura ${numero(dim.largura_m, 2)} m` +
                                            (typeof dim.correntes === 'number' ? ` · ${dim.correntes} corrente(s)` : ''));
    }
    caixa.append(campos);
    if (this.analise.origem === 'ifc' && this.projeto) {
      caixa.append(this._blocoTrocaPerfil(nome, info));
      if (info.entrada) caixa.append(this._blocoAlternativas(nome));
    }
  }

  /** Primeiro elemento analisado que está na seleção. */
  _elementoSelecionado() {
    const a = this.analise;
    if (!a) return null;
    for (const ent of this.selecao.entidades) {
      const at = ent.atributos || {};
      const chave = at.elemento || (at.marcas && at.marcas.posicao);
      const info = chave && a.elementos[chave];
      if (info) return { nome: chave, info, marca: at.marca || (at.marcas && at.marcas.posicao) || ent.nome || '' };
    }
    return null;
  }

  // ------------------------------------------------------------ dados

  /** Extremos da escala. Vêm do módulo de desenho quando ele existe. */
  _faixaAnalise() {
    const est = this.analiseEstado, a = this.analise;
    const doMapa = this._comMapa(m => m.faixa());
    if (doMapa && typeof doMapa.min === 'number' && typeof doMapa.max === 'number' &&
        isFinite(doMapa.min) && isFinite(doMapa.max)) {
      return doMapa;
    }
    const percentual = est.grandeza === 'aproveitamento';
    let min = Infinity, max = -Infinity;
    for (const info of Object.values((a && a.elementos) || {})) {
      const v = this._valorDoElemento(info, est.combinacao, est.grandeza);
      if (v === null) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (!isFinite(min)) { min = 0; max = 1; }
    if (percentual) min = 0;                     // aproveitamento se lê a partir do zero
    if (max <= min) max = min + 1;
    return { min, max, unidade: percentual ? '' : this._unidadeDe(est.grandeza), percentual };
  }

  _unidadeDe(grandeza) {
    const a = this.analise || {};
    if (a.unidades && a.unidades[grandeza]) return a.unidades[grandeza];
    const g = (a.grandezas || GRANDEZAS_PADRAO).find(x => x.chave === grandeza);
    return (g && g.unidade) || '';
  }

  /** Valor de um elemento na combinação e na grandeza escolhidas; `null` se não houver. */
  _valorDoElemento(info, combinacao, grandeza) {
    if (!info) return null;
    if (grandeza === 'aproveitamento') {
      return typeof info.aproveitamento === 'number' ? info.aproveitamento : null;
    }
    const valores = info.valores || {};
    const daComb = valores[combinacao] || valores.envoltoria;
    const v = daComb ? daComb[grandeza] : undefined;
    return typeof v === 'number' && isFinite(v) ? v : null;
  }

  _piorAproveitamento() {
    let pior = 0;
    for (const info of Object.values((this.analise && this.analise.elementos) || {})) {
      if (typeof info.aproveitamento === 'number') pior = Math.max(pior, info.aproveitamento);
    }
    return pior;
  }

  /** Ranking do módulo de desenho quando existe; senão, montado aqui pelos dados. */
  _ordenarPorEsforco(n) {
    const doMapa = this._comMapa(m => m.ranking(n));
    if (Array.isArray(doMapa) && doMapa.length) return doMapa;
    const est = this.analiseEstado, a = this.analise;
    if (!a || !est) return [];
    // As peças do modelo agrupadas por elemento: é `atributos.elemento` que liga a
    // resposta do servidor às entidades desenhadas.
    const noModelo = new Map();
    for (const ent of this.documento.entidades.values()) {
      const at = ent.atributos || {};
      const chave = at.elemento || (at.marcas && at.marcas.posicao);
      if (!chave) continue;
      let reg = noModelo.get(chave);
      if (!reg) noModelo.set(chave, reg = { marca: '', ids: [] });
      reg.ids.push(ent.id);
      if (!reg.marca) reg.marca = at.marca || (at.marcas && at.marcas.posicao) || '';
    }
    const itens = [];
    for (const [nome, info] of Object.entries(a.elementos)) {
      const valor = this._valorDoElemento(info, est.combinacao, est.grandeza);
      if (valor === null) continue;
      const reg = noModelo.get(nome);
      itens.push({ ids: reg ? reg.ids : [], marca: reg ? reg.marca : '', elemento: nome,
                   valor, aproveitamento: info.aproveitamento, no_portico: info.no_portico });
    }
    itens.sort((x, y) => Math.abs(y.valor) - Math.abs(x.valor));
    return itens.slice(0, n);
  }

  _corDaEscala(t) {
    const n = Math.min(1, Math.max(0, isFinite(t) ? t : 0));
    const doMapa = this._comMapa(m => m.cores(n));
    if (typeof doMapa === 'string' && /^#[0-9a-f]{3,8}$/i.test(doMapa)) return doMapa;
    const est = this.analiseEstado;
    return corDaRampa(est && est.grandeza === 'aproveitamento'
      ? RAMPA_APROVEITAMENTO : RAMPA_ESFORCOS, n);
  }

  _formatarValor(v, faixa) {
    if (typeof v !== 'number' || !isFinite(v)) return '—';
    if (faixa && faixa.percentual) return `${numero(v * 100, 0)} %`;
    const m = Math.abs(v);
    return numero(v, m >= 100 ? 0 : m >= 10 ? 1 : 2);
  }

  _clicarRanking(ids, ev) {
    if (!ids || !ids.length) { this.dica('Esta peça não está no modelo aberto.'); return; }
    if (ev && ev.shiftKey) this.selecao.somar(ids);
    else this.selecao.definir(ids);
  }

  /** Depois de a seleção mudar: marca as linhas e refaz o detalhe da peça. */
  _aposSelecaoAnalise() {
    for (const linha of (this._linhasRanking || [])) {
      linha.el.toggleAttribute('data-marcada', linha.ids.some(id => this.selecao.tem(id)));
    }
    this._atualizarDetalheAnalise();
  }
}
