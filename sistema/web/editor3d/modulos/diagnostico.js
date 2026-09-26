// Métodos do editor 3D: Diagnóstico de desempenho, sombras e os ganchos dos verificadores.
//
// Saíram de editor.js (que tinha quase 5 mil linhas) sem mudar o corpo: esta classe só
// guarda os métodos, e editor.js os copia para Editor.prototype (aplicarMetodos).

import { VISTAS } from '../nucleo/camera.js';
import { PESADOS } from '../nucleo/cena.js';
import { PAPEIS, escalar } from '../nucleo/documento.js';
import { $, el, mover, numero } from '../editor.js';

export class MetodosDiagnostico {
  // ---------------------------------------------------------------- análise

  /**
   * Ver → Diagnóstico de desempenho: mede o que custa cada parte na **máquina do
   * usuário** — quadros por segundo reais, chamadas de desenho, custo de escolher uma
   * peça com o cursor e qual placa de vídeo o navegador está usando. É o que diz se a
   * lentidão está no desenho, na escolha ou no vídeo (aceleração desligada).
   */
  async dialogoDesempenho() {
    this.dica('Medindo o desempenho…');
    const cena = this.cena, r = cena.renderizador;
    // 1. quadros por segundo: desenha de verdade, contando o intervalo entre quadros
    const medirFPS = (n = 40) => new Promise((ok) => {
      const t = [];
      let i = 0;
      const passo = () => {
        cena.desenhar(this.camera.ativa);
        t.push(performance.now());
        if (++i < n) requestAnimationFrame(passo);
        else {
          const dt = [];
          for (let k = 1; k < t.length; k++) dt.push(t[k] - t[k - 1]);
          dt.sort((a, b) => a - b);
          ok({ mediana: dt[Math.floor(dt.length / 2)] || 0, pior: dt[dt.length - 1] || 0 });
        }
      };
      requestAnimationFrame(passo);
    });
    const fps = await medirFPS();
    // 2. escolha de peça pelo cursor, no meio da tela e ao redor
    const t0 = performance.now();
    let achou = 0, n = 0;
    for (let x = 0.3; x <= 0.7; x += 0.1) {
      for (let y = 0.3; y <= 0.7; y += 0.1) {
        const p = this.selecao.sob(this.camera.largura * x, this.camera.altura * y);
        if (p) achou++;
        n++;
      }
    }
    const escolha = (performance.now() - t0) / Math.max(n, 1);
    // 3. placa de vídeo que o navegador está usando
    let placa = 'desconhecida';
    try {
      const gl = r.getContext();
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      if (ext) placa = String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) || '');
      else placa = String(gl.getParameter(gl.RENDERER) || '');
    } catch { /* sem informação da placa */ }
    const macio = /swiftshader|software|llvmpipe|basic render/i.test(placa);
    const info = r.info.render;
    const linhas = [
      ['Quadros por segundo', `${numero(1000 / Math.max(fps.mediana, 0.001), 0)} (pior quadro ${numero(fps.pior, 0)} ms)`],
      ['Chamadas de desenho', `${numero(info.calls)} · ${numero(info.triangles)} triângulos · ${numero(info.lines)} linhas`],
      ['Escolher peça no cursor', `${numero(escolha, 1)} ms`],
      ['Peças no modelo', `${numero(this.documento.tamanho)}${cena.emLote ? ` · desenho em lote (${cena.lote.blocos.length} blocos)` : ' · um objeto por peça'}`],
      ['Sombras', cena.sombrasAtivas ? 'ligadas' : 'desligadas'],
      ['Modo', cena.modo.replace('_', ' com ')],
      ['Vídeo', placa || 'desconhecida'],
    ];
    const campos = el('div', { class: 'campos' });
    for (const [rot, val] of linhas) {
      campos.append(el('label', { texto: rot }), el('span', { class: 'valor quebra', texto: val }));
    }
    const corpo = el('div', {}, campos);
    if (macio) {
      corpo.append(el('p', { class: 'explica', texto:
        'A aceleração de vídeo está desligada no navegador: o modelo é desenhado pelo processador, ' +
        'e é por isso que a navegação fica pesada. Em Configurações do Edge/Chrome → Sistema, ligue ' +
        '"Usar aceleração de hardware quando disponível" e reabra o programa.' }));
    } else if (1000 / Math.max(fps.mediana, 0.001) < 25) {
      corpo.append(el('p', { class: 'explica', texto:
        'Menos de 25 quadros por segundo. Tente o modo "Sombreado" (sem arestas) no alto à direita, ' +
        'oculte as camadas que não estiver usando (Telhas costuma ser a mais pesada) e confira em ' +
        'Ver → Sombras se elas estão desligadas.' }));
    }
    // O que travou a tela desde que o programa abriu (operações medidas em cena.js)
    if (PESADOS.length) {
      const por = new Map();
      for (const p of PESADOS) {
        const r = por.get(p.nome) || { n: 0, total: 0, pior: 0 };
        r.n++; r.total += p.ms; r.pior = Math.max(r.pior, p.ms);
        por.set(p.nome, r);
      }
      const ordenado = [...por.entries()].sort((a, b) => b[1].total - a[1].total).slice(0, 5);
      const lista = el('div', { class: 'lista-linhas' });
      for (const [nome, r] of ordenado) {
        lista.append(el('div', { class: 'linha' },
          el('span', { class: 'nome', texto: nome }),
          el('span', { class: 'contagem', texto: `${r.n}× · pior ${numero(r.pior, 0)} ms` })));
      }
      corpo.append(el('h4', { texto: 'Travadas desde que o programa abriu' }), lista);
    }
    const texto = linhas.map(([a, b]) => `${a}: ${b}`).join('\n') +
      (PESADOS.length ? '\nTravadas: ' + PESADOS.map(p => `${p.nome} ${p.ms} ms`).join(' · ') : '');
    corpo.append(el('p', { class: 'explica' },
      el('button', { type: 'button', texto: 'Copiar os números',
        onclick: () => { navigator.clipboard.writeText(texto).then(() => this.dica('Números copiados.')); } })));
    this.dica('Diagnóstico pronto.');
    await this.dialogo({ titulo: 'Diagnóstico de desempenho', corpo, ok: 'Fechar' });
  }

  /** Ver → Sombras: liga ou desliga a sombra do sol (escolha do usuário vale até trocar de modelo). */
  alternarSombras() {
    const ligadas = this.cena.definirSombras(!this.cena.sombrasAtivas);
    this._atualizarMenuSombras();
    this.dica(ligadas ? 'Sombras ligadas.' : 'Sombras desligadas: o modelo é desenhado uma vez só por quadro.');
    this._sujo = true;
  }

  _atualizarMenuSombras() {
    const b = document.getElementById('menu-sombras');
    if (!b) return;
    const ligadas = this.cena.sombrasAtivas;
    b.replaceChildren(`Sombras ${ligadas ? '✓' : '—'}`);
    b.setAttribute('aria-pressed', String(ligadas));
  }

  // ------------------------------------------------------------ verificação

  /** Parâmetros de URL usados nas capturas automáticas (e úteis para depurar). */
  _aplicarParametrosDeTeste() {
    const p = this.parametros;
    const sel = p.get('sel');
    if (sel) {
      if (PAPEIS.includes(sel)) this.selecao.porPapel(sel);
      else if (['barra', 'chapa', 'solido'].includes(sel)) this.selecao.porTipo(sel);
      else this.selecao.porCamada(sel);
    }
    const vista = p.get('vista');
    if (vista && VISTAS[vista]) this.camera.vista(vista);
    if (p.get('orto') === '1') this.el.projecao.click();
    const f = p.get('ferramenta');
    if (f) this.ativarFerramenta(f);
    // O cursor simulado, com ?teste=1, é aplicado no congelamento da captura, depois
    // de a câmera assentar; sem ele, aos 3 s.
    if (p.get('mouse') && p.get('teste') !== '1') setTimeout(() => this._simularMouse(p.get('mouse')), 3000);
    if (p.get('ciclo') === '1') setTimeout(() => this._cicloDeFerramentas(), 2500);
    if (p.get('abrirMenu')) {
      const m = document.querySelector(`.menu[data-menu="${p.get('abrirMenu')}"]`);
      if (m) m.classList.add('aberto');
    }
    if (p.get('teste') === '1') {
      setTimeout(() => this._congelarParaCaptura(), Number(p.get('captura')) || 7000);
    }
  }

  /**
   * Só para captura automática. No Chrome headless o relógio virtual corre à frente
   * do swiftshader, que rasteriza em tempo real: a captura sai antes de o quadro
   * pesado ficar pronto. Aqui desenhamos um quadro síncrono, lemos o buffer (o
   * toDataURL espera a GPU terminar) e o pomos como imagem sob as camadas de snap e
   * avisos. É exatamente o que o WebGL produziu; só o compositor fica de fora.
   */
  _congelarParaCaptura() {
    this.camera.concluirAnimacao();
    if (this.parametros.get('mouse')) this._simularMouse(this.parametros.get('mouse'));
    this.cena.desenhar(this.camera.ativa);
    const img = el('img', { src: this.el.canvas.toDataURL('image/png'), alt: '' });
    img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
    this.el.canvas.after(img);
    document.body.dataset.capturado = '1';
  }

  /**
   * Simula o cursor parado num ponto, para conferir o glifo do snap na captura.
   * `extremidade` mira 4 px ao lado do topo do primeiro pilar: a inferência precisa
   * preferir a extremidade à aresta e à face que estão logo ali.
   */
  _simularMouse(mouse) {
    const r = this.el.canvas.getBoundingClientRect();
    let mx, my;
    if (mouse === 'extremidade') {
      const b = this.documento.barras.find(e => e.papel === 'pilar') || this.documento.barras[0];
      if (!b) return;
      const t = this.camera.paraTela(b.fim);
      mx = t[0] + 4; my = t[1] + 3;
    } else {
      [mx, my] = mouse.split(',').map(Number);
    }
    this._processarMovimento({ clientX: r.left + mx, clientY: r.top + my, buttons: 0 });
    this._sujo = true;
  }

  /**
   * Teste de integração (?ciclo=1): passa por todas as ferramentas com o mouse e o
   * teclado de verdade — pelos mesmos manipuladores de evento do uso normal — e no
   * fim desfaz tudo. O resultado vai para body[data-ciclo]: erros por ferramenta e se
   * o documento voltou exatamente ao tamanho original.
   */
  async _cicloDeFerramentas() {
    const esperar = (ms) => new Promise(ok => setTimeout(ok, ms));
    const c = this.el.canvas;
    const r = c.getBoundingClientRect();
    this.camera.concluirAnimacao();
    this.camera.permitirNavegacao(false);     // o OrbitControls rejeita ponteiro sintético
    const tela = (q) => { const t = this.camera.paraTela(q); return [t[0], t[1]]; };
    const b = this.documento.barras[0];
    const pontos = [
      b ? tela(b.fim) : [r.width * 0.4, r.height * 0.4],
      b ? tela(b.inicio) : [r.width * 0.45, r.height * 0.5],
      [r.width * 0.5, r.height * 0.55],
      [r.width * 0.62, r.height * 0.62],
    ];
    const ponteiro = (tipo, [x, y]) => c.dispatchEvent(new PointerEvent(tipo, {
      clientX: r.left + x, clientY: r.top + y, button: 0, buttons: tipo === 'pointerup' ? 0 : 1,
      pointerId: 1, pointerType: 'mouse', bubbles: true, cancelable: true }));
    const mover = ([x, y]) => this._processarMovimento({ clientX: r.left + x, clientY: r.top + y, buttons: 0 });
    const tecla = (key) => document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    const antes = this.documento.tamanho;
    const relatorio = {};
    for (const id of this.ferramentas.keys()) {
      const e0 = (window.__errosEditor || []).length;
      const a0 = (this._registroErros || []).length;
      // As de edição precisam de algo selecionado para ter o que editar.
      if (['mover', 'girar', 'escalar', 'copiar', 'offset'].includes(id) && b) this.selecao.definir([b.id]);
      else this.selecao.limpar();
      this.ativarFerramenta(id);
      for (const [i, q] of pontos.entries()) {
        mover(q); await esperar(15);
        if (i < 3) { ponteiro('pointerdown', q); ponteiro('pointerup', q); await esperar(15); }
      }
      c.dispatchEvent(new MouseEvent('dblclick', {
        clientX: r.left + pontos[3][0], clientY: r.top + pontos[3][1], bubbles: true }));
      this.el.medida.value = '1500';
      this._enviarValor();
      tecla('Escape'); tecla('Escape');
      await esperar(15);
      relatorio[id] = {
        erros: (window.__errosEditor || []).slice(e0),
        avisosDeErro: (this._registroErros || []).slice(a0),
        objetos: this.documento.tamanho,
      };
    }
    this.ativarFerramenta('selecionar');
    const operacoes = this.pilha.feitos.length;
    while (this.pilha.podeDesfazer) this.pilha.desfazer();
    document.body.dataset.ciclo = JSON.stringify({
      antes, operacoes, depoisDeDesfazer: this.documento.tamanho, ferramentas: relatorio });
    this.camera.permitirNavegacao(true);
  }

  /** Estado da câmera e da cena, para depurar uma tela vazia sem abrir o DevTools. */
  diagnostico() {
    const r = (v) => Math.round(v * 1000) / 1000;
    const cam = this.camera.ativa, alvo = this.camera.alvo;
    const ruins = [];
    for (const [id, obj] of this.cena.objetos) {
      const m = obj.getObjectByName('malha');
      const g = m && m.geometry;
      if (!g) continue;
      if (!g.boundingSphere) g.computeBoundingSphere();
      const soma = obj.matrix.elements.reduce((s, x) => s + x, 0);
      if (!isFinite(g.boundingSphere.radius) || !isFinite(soma)) {
        const e = this.documento.get(id);
        ruins.push(`${e ? e.tipo : '?'}:${e && (e.nome || e.id)}`);
      }
    }
    const info = this.cena.renderizador.info.render;
    return {
      camera: [r(cam.position.x), r(cam.position.y), r(cam.position.z)],
      alvo: [r(alvo.x), r(alvo.y), r(alvo.z)], distancia: r(this.camera.distancia),
      passoGrade: this.cena._gradePasso, desenhos: info.calls, triangulos: info.triangles,
      contextoPerdido: this.cena.renderizador.getContext().isContextLost(),
      nRuins: ruins.length, ruins: ruins.slice(0, 8),
    };
  }

  _publicarErros() {
    let mostrados = 0;
    const publicar = () => {
      const erros = window.__errosEditor || [];
      // Com ?teste=1 os erros aparecem na tela, para ficarem na própria captura.
      if (this.parametros.get('teste') === '1') {
        for (; mostrados < erros.length; mostrados++) this.aviso(erros[mostrados], 'erro', 0);
      }
      document.body.dataset.erros = JSON.stringify(erros);
      try { document.body.dataset.diag = JSON.stringify(this.diagnostico()); }
      catch (e) { document.body.dataset.diag = 'falhou: ' + e.message; }
      document.body.dataset.objetos = String(this.documento.tamanho);
      document.body.dataset.malhas = String(this.cena.objetos.size);
      document.body.dataset.ferramentas = [...this.ferramentas.keys()].join(',');
      document.body.dataset.servidor = this.cena.usarServidor ? 'sim' : 'nao';
    };
    publicar();
    // Em modelo grande esta publicação (para os verificadores de tela) percorre todas as
    // peças: de meio em meio segundo ela própria vira peso.
    setInterval(publicar, this.documento.tamanho > 1500 ? 5000 : 500);
  }
}
