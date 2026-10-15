// Métodos do editor 3D: o lado BIM — a informação do modelo à mão, como num Revit (pedido do usuário, 14/10/2026:
// "intuitiva de usar e modelar como o SketchUp e versátil e moderna cheia de informações como um Revit").
//
//   · ficha ao passar o mouse: parado sobre uma peça (com a ferramenta Selecionar), a marca, o perfil, o comprimento,
//     o peso, o conjunto, a fase, a ligação e as soldas dela — sem clicar;
//   · etiquetas: a marca de cada peça escrita no 3D (Ver → Etiquetas), como as tags do Revit;
//   · vistas salvas: a câmera, o corte, as cores por propriedade e os grupos ocultos guardados com nome numa faixa
//     de abas embaixo da tela, como as cenas do SketchUp e as vistas do Revit — gravadas no modelo;
//   · tabela de peças ao vivo: o quantitativo por posição, perfil, conjunto, fase, papel ou acabamento, com totais,
//     filtro, clique para selecionar e CSV — e ela se refaz quando o modelo muda (o "schedule" do Revit).

import { el, numero, volumeDe } from '../editor.js';
import { clonar, areaDaChapa, comprimentoDaBarra } from '../nucleo/documento.js';
import { Comando } from '../nucleo/comandos.js';
import { definirCaixaDeCorte } from './caixa_corte.js';

const RHO = 7.85e-6;          // kg/mm³
const LIMITE_ETIQUETAS = 700;

const marcasDe = (e) => (e && e.atributos && e.atributos.marcas) || {};

/** Guarda e volta documento.metadados.vistas (as vistas salvas entram no desfazer e na gravação do modelo). */
class ComandoVistas extends Comando {
  constructor(vistas, rotulo) { super(rotulo); this.novas = clonar(vistas); this.antes = undefined; }
  aplicar(doc) {
    if (this.antes === undefined) this.antes = clonar(doc.metadados.vistas || []);
    doc.metadados.vistas = clonar(this.novas);
    doc.notificar([], 'alterar');
  }
  desfazer(doc) { doc.metadados.vistas = clonar(this.antes); doc.notificar([], 'alterar'); }
  ids() { return []; }
}

export class MetodosBIM {
  /** Chamado uma vez, quando a câmera está pronta: a ficha do mouse e o acompanhamento das etiquetas. */
  _iniciarBIM() {
    const canvas = this.el.canvas;
    if (!canvas || this._bimIniciado) return;
    this._bimIniciado = true;
    const antes = this.camera.aoMover;
    this.camera.aoMover = () => { if (antes) antes(); this._agendarEtiquetas(); this._esconderFicha(); };
    canvas.addEventListener('pointermove', (ev) => this._fichaAoMover(ev));
    canvas.addEventListener('pointerleave', () => this._esconderFicha());
    canvas.addEventListener('pointerdown', () => this._esconderFicha());
    this.selecao.aoMudar(() => this._agendarEtiquetas(true));
    setTimeout(() => this._desenharVistas(), 0);
  }

  /** Depois de cada mudança do documento (editor._aposMudanca): etiquetas, tabela e abas das vistas em dia. */
  _aposMudancaBIM() {
    this._agendarEtiquetas(true);
    if (this._painelTabela) this._agendarTabela();
    if (this._painelSequencia) { clearTimeout(this._timerSequencia); this._timerSequencia = setTimeout(() => this._desenharSequencia(), 500); }
    this._desenharVistas();
  }

  // ---------------------------------------------------------------- ficha ao passar o mouse

  _esconderFicha() {
    clearTimeout(this._timerFicha);
    if (this._ficha) this._ficha.hidden = true;
  }

  _fichaAoMover(ev) {
    this._esconderFicha();
    if (ev.buttons || this.idAtiva !== 'selecionar' || this.fichaDesligada) return;
    const r = this.el.canvas.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    this._timerFicha = setTimeout(() => this._mostrarFicha(x, y), 380);
  }

  _mostrarFicha(x, y) {
    let s = null;
    try { s = this.selecao.sob(x, y); } catch (e) { s = null; }
    const e = s && this.documento.get(s.id);
    if (!e) return;
    const linhas = this.fichaDaPeca(e);
    if (!linhas.length) return;
    if (!this._ficha) {
      this._ficha = el('div', { class: 'ficha-peca' });
      this._ficha.style.cssText = 'position:absolute;z-index:40;pointer-events:none;max-width:320px;padding:6px 9px;border-radius:6px;' +
        'background:var(--painel, #1f2937);color:var(--texto, #f9fafb);box-shadow:0 2px 10px rgba(0,0,0,.3);font-size:12px;line-height:1.45;' +
        'border:1px solid rgba(127,127,127,.35)';
      (this.el.palco || document.body).append(this._ficha);
    }
    this._ficha.replaceChildren(...linhas.map(([k, v], i) => i === 0
      ? el('div', { style: 'font-weight:600;font-size:13px;margin-bottom:2px', texto: v })
      : el('div', {}, el('span', { style: 'opacity:.7', texto: `${k}: ` }), v)));
    const w = (this.el.palco || document.body).clientWidth;
    this._ficha.style.left = `${Math.min(x + 16, w - 330)}px`;
    this._ficha.style.top = `${y + 18}px`;
    this._ficha.hidden = false;
  }

  /** A ficha de uma peça: [[rótulo, valor], …], a primeira linha é o título. */
  fichaDaPeca(e) {
    const a = e.atributos || {};
    const m = marcasDe(e);
    const out = [];
    const titulo = [m.nome || m.posicao, e.tipo === 'barra' ? e.perfil : (m.perfil || e.nome)].filter(Boolean).join(' — ');
    out.push(['', titulo || e.nome || e.tipo]);
    if (m.posicao) out.push(['Posição', m.posicao + (m.nome && m.nome !== m.posicao ? ` (${m.nome})` : '')]);
    if (e.tipo === 'barra') {
      out.push(['Perfil', `${e.perfil}${e.papel ? ' · ' + e.papel : ''}`]);
      out.push(['Comprimento', `${numero(comprimentoDaBarra(e))} mm`]);
    } else if (e.tipo === 'chapa') {
      out.push(['Chapa', `${numero(e.espessura || 0, 2)} mm · ${numero(areaDaChapa(e) / 1e6, 3)} m² · ${(e.furos || []).length} furo(s)`]);
    } else if (a.parafuso) {
      out.push(['Parafuso', `M${numero(a.parafuso.d)} × ${numero(a.parafuso.L)} ${a.parafuso.classe || ''}`]);
    }
    const peso = this.pesoDaPeca(e);
    if (peso) out.push(['Peso', `${numero(peso, 1)} kg`]);
    if (m.conjunto) out.push(['Conjunto', m.conjunto + (m.principal ? ' (peça principal)' : '')]);
    if (a.fase) out.push(['Fase', a.fase]);
    if (a.acabamento) out.push(['Acabamento', a.acabamento]);
    if (e.aco || e.material) out.push(['Aço', e.aco || e.material]);
    if (a.ligacao) out.push(['Ligação', (this._tiposLig || []).find(t => t.id === a.ligacao.tipo)?.nome || a.ligacao.tipo]);
    if (a.detalhe_usuario) out.push(['Detalhe', a.detalhe_usuario.nome]);
    const sold = a.soldas ? Object.keys(a.soldas).length : 0;
    if (sold) out.push(['Soldas', `com ${Object.keys(a.soldas).join(', ')}`]);
    for (const [k, v] of Object.entries(a.props_usuario || {})) out.push([k, v]);
    if (a.marca_a_conferir) out.push(['Atenção', 'mudou depois de copiada — Numerar']);
    out.push(['Camada', e.camada || '—']);
    return out;
  }

  pesoDaPeca(e) {
    try {
      if (e.tipo === 'barra') return this._massaBarra(e);
      if (e.tipo === 'chapa') return areaDaChapa(e) * (e.espessura || 0) * RHO;
      if (e.tipo === 'solido' && e.faces && e.faces.length) return volumeDe(e) * RHO;
    } catch (err) { /* sem peso */ }
    return 0;
  }

  // ---------------------------------------------------------------- etiquetas

  alternarEtiquetas() {
    this.etiquetasLigadas = !this.etiquetasLigadas;
    if (!this.etiquetasLigadas) {
      if (this._camadaEtiquetas) { this._camadaEtiquetas.remove(); this._camadaEtiquetas = null; }
      this.dica('Etiquetas desligadas.');
      return;
    }
    this._agendarEtiquetas(true);
    this.dica('Etiquetas: a marca de cada peça (com seleção, só as selecionadas; sem marca, Editar → Numerar peças).');
  }

  _agendarEtiquetas(refazer = false) {
    if (!this.etiquetasLigadas) return;
    if (refazer) this._etiquetasSujas = true;
    if (this._rafEtiquetas) return;
    this._rafEtiquetas = requestAnimationFrame(() => { this._rafEtiquetas = null; this._desenharEtiquetas(); });
  }

  _centroDe(e) {
    if (e.tipo === 'barra') return [(e.inicio[0] + e.fim[0]) / 2, (e.inicio[1] + e.fim[1]) / 2, (e.inicio[2] + e.fim[2]) / 2];
    const c = this.documento.caixaDe(e);
    return c ? [(c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2, (c[0][2] + c[1][2]) / 2] : null;
  }

  _desenharEtiquetas() {
    if (!this._camadaEtiquetas) {
      this._camadaEtiquetas = el('div', { class: 'camada-etiquetas' });
      this._camadaEtiquetas.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:30';
      (this.el.palco || document.body).append(this._camadaEtiquetas);
      this._etiquetasSujas = true;
    }
    if (this._etiquetasSujas) {
      this._etiquetasSujas = false;
      const sel = this.selecao.ids.size ? this.selecao.ids : null;
      const ocultos = this.documento.ocultosNaVista || null;
      const fora = this.documento.foraDoIsolamento || null;
      const itens = [];
      for (const e of this.documento.entidades.values()) {
        if (sel && !sel.has(e.id)) continue;
        if ((ocultos && ocultos.has(e.id)) || (fora && fora.has(e.id))) continue;
        const m = marcasDe(e);
        const txt = m.nome || m.posicao;
        if (!txt || (e.atributos && e.atributos.parafuso)) continue;
        const c = this._centroDe(e);
        if (c) itens.push({ txt, c });
        if (itens.length >= LIMITE_ETIQUETAS) break;
      }
      this._etiquetas = itens;
      this._camadaEtiquetas.replaceChildren(...itens.map(it => {
        const s = el('span', { texto: it.txt });
        s.style.cssText = 'position:absolute;transform:translate(-50%,-50%);padding:0 4px;border-radius:3px;font:600 11px Arial,sans-serif;' +
          'background:rgba(255,255,255,.85);color:#1e3a8a;border:1px solid #93c5fd;white-space:nowrap';
        it.el = s;
        return s;
      }));
    }
    const w = this.el.canvas.clientWidth, h = this.el.canvas.clientHeight;
    for (const it of this._etiquetas || []) {
      const [x, y, z] = this.camera.paraTela(it.c);
      const ve = z < 1 && x > -40 && y > -20 && x < w + 40 && y < h + 20;
      it.el.style.display = ve ? '' : 'none';
      if (ve) { it.el.style.left = `${x}px`; it.el.style.top = `${y}px`; }
    }
  }

  // ---------------------------------------------------------------- vistas salvas

  _estadoDaVista(nome) {
    const cam = this.camera;
    return {
      nome,
      camera: { posicao: cam.ativa.position.toArray(), alvo: cam.controles.target.toArray(), projecao: cam.projecao,
                zoom: cam.ortografica.zoom },
      corte: this.cena.planoCorte ? clonar(this.cena.planoCorte) : null,
      caixa: this.cena.caixaCorte ? clonar(this.cena.caixaCorte) : null,     // a caixa de corte (modulos/caixa_corte.js)
      cor_por: this.corPor || 'padrao',
      ocultos: this._gruposOcultos ? [...this._gruposOcultos] : [],
    };
  }

  async salvarVista() {
    const nome = el('input', { type: 'text', value: `Vista ${(this.documento.metadados.vistas || []).length + 1}`, style: 'width:100%' });
    const corpo = el('div', {}, el('label', { texto: 'Nome da vista' }), nome,
      el('p', { class: 'explica', texto: 'Guarda o enquadramento, a projeção, o corte (Seção ou caixa de corte), as cores por propriedade e os grupos ocultos. Fica gravada no modelo, numa aba embaixo da tela.' }));
    if (await this.dialogo({ titulo: 'Salvar vista', corpo, ok: 'Salvar' }) !== 'ok') return;
    const v = this._estadoDaVista(nome.value.trim() || 'Vista');
    const lista = (this.documento.metadados.vistas || []).filter(x => x.nome !== v.nome).concat([v]);
    this.executar(new ComandoVistas(lista, `Salvar a vista ${v.nome}`));
    this._desenharVistas();
  }

  irParaVista(v) {
    if (!v) return;
    const THREE_ = this.camera.ativa.position.constructor;
    if (v.camera.projecao && v.camera.projecao !== this.camera.projecao) this.camera.definirProjecao(v.camera.projecao);
    if (v.camera.projecao === 'ortografica' && v.camera.zoom) { this.camera.ortografica.zoom = v.camera.zoom; this.camera.ortografica.updateProjectionMatrix(); }
    this.camera.irPara(new THREE_(...v.camera.posicao), new THREE_(...v.camera.alvo));
    this.cena.definirPlanoCorte(v.corte || null);
    definirCaixaDeCorte(this, v.caixa || null);
    if ((v.cor_por || 'padrao') !== (this.corPor || 'padrao')) { this.corPor = v.cor_por || 'padrao'; this._aplicarCorPor(); }
    this._ocultarGrupos(new Set(v.ocultos || []));
    this._agendarPaineis('camadas');
    this.dica(`Vista ${v.nome}.`);
  }

  apagarVista(nome) {
    const lista = (this.documento.metadados.vistas || []).filter(x => x.nome !== nome);
    this.executar(new ComandoVistas(lista, `Apagar a vista ${nome}`));
    this._desenharVistas();
  }

  /** Alt+1…Alt+9: a vista salva n (na ordem das abas); Alt+0: salvar a vista. As teclas 1–7 sozinhas são as vistas
   *  padrão e o Ctrl+número é do navegador (pedido do usuário, 15/10). Pelo código da tecla: o Alt muda o ev.key em
   *  alguns teclados. Devolve true quando tratou. */
  atalhoDeVista(ev) {
    const m = /^(?:Digit|Numpad)([0-9])$/.exec(ev.code || '');
    if (!m || ev.ctrlKey || ev.metaKey || ev.shiftKey) return false;
    const n = +m[1];
    if (n === 0) { this.salvarVista(); return true; }
    const vistas = (this.documento.metadados && this.documento.metadados.vistas) || [];
    if (!vistas[n - 1]) { this.dica(vistas.length ? `Não há vista ${n}: o modelo tem ${vistas.length} (Alt+1 a Alt+${vistas.length}).` : 'Nenhuma vista salva: Alt+0 salva a vista atual.'); return true; }
    this.irParaVista(vistas[n - 1]);
    return true;
  }

  _desenharVistas() {
    const vistas = (this.documento && this.documento.metadados && this.documento.metadados.vistas) || [];
    if (!vistas.length) { if (this._barraVistas) { this._barraVistas.remove(); this._barraVistas = null; } return; }
    if (!this._barraVistas) {
      this._barraVistas = el('div', { class: 'barra-vistas' });
      this._barraVistas.style.cssText = 'position:absolute;left:12px;bottom:34px;z-index:35;display:flex;gap:4px;flex-wrap:wrap;max-width:70%';
      (this.el.palco || document.body).append(this._barraVistas);
    }
    this._barraVistas.replaceChildren(...vistas.map((v, i) => {
      const b = el('button', { type: 'button', texto: v.nome, title: `Ir para a vista${i < 9 ? ` (Alt+${i + 1})` : ''} · botão direito: apagar` });
      b.style.cssText = 'padding:3px 10px;border-radius:12px;border:1px solid rgba(127,127,127,.5);background:var(--painel, #fff);' +
        'color:inherit;font-size:12px;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.15)';
      b.addEventListener('click', () => this.irParaVista(v));
      b.addEventListener('contextmenu', async (ev) => {
        ev.preventDefault();
        if (await this.dialogo({ titulo: 'Apagar vista', corpo: el('p', { texto: `Apagar a vista "${v.nome}"?` }), ok: 'Apagar' }) === 'ok') this.apagarVista(v.nome);
      });
      return b;
    }));
  }

  // ---------------------------------------------------------------- sequência de montagem (o "4D")

  /** As fases do modelo em ordem natural, com as peças e o peso de cada uma. */
  fasesDoModelo() {
    const fases = new Map();
    for (const e of this.documento.entidades.values()) {
      const f = e.atributos && e.atributos.fase;
      if (!f) continue;
      if (!fases.has(f)) fases.set(f, { fase: f, ids: [], peso: 0 });
      const g = fases.get(f);
      g.ids.push(e.id);
      g.peso += this.pesoDaPeca(e);
    }
    return [...fases.values()].sort((a, b) => String(a.fase).localeCompare(String(b.fase), 'pt-BR', { numeric: true }));
  }

  abrirSequencia() {
    if (this._painelSequencia) { this._fecharSequencia(); return; }
    this._sequencia = { ate: null, semFase: true };
    this._painelSequencia = el('div', { class: 'painel-apoios painel-sequencia' });
    this._painelSequencia.style.maxWidth = '420px';
    (this.el.palco || document.body).append(this._painelSequencia);
    const fases = this.fasesDoModelo();
    if (fases.length) this._sequencia.ate = fases.length - 1;
    this._desenharSequencia();
  }

  _fecharSequencia() {
    clearInterval(this._tocandoSequencia);
    this._tocandoSequencia = null;
    if (this._painelSequencia) { this._painelSequencia.remove(); this._painelSequencia = null; }
    this._sequencia = null;
    // as cores e os grupos ocultos de antes
    this._aplicarCorPor();
    this._ocultarGrupos(this._gruposOcultos || new Set());
  }

  /** Mostra o modelo até a fase `ate`: as depois somem, a atual em laranja, as de antes em cinza. */
  _aplicarSequencia() {
    const s = this._sequencia;
    if (!s) return;
    const fases = this.fasesDoModelo();
    const ordem = new Map(fases.map((f, i) => [f.fase, i]));
    const ate = s.ate == null ? fases.length - 1 : s.ate;
    const ocultos = new Set();
    for (const e of this.documento.entidades.values()) {
      const f = e.atributos && e.atributos.fase;
      if (f ? ordem.get(f) > ate : !s.semFase) ocultos.add(e.id);
    }
    this.documento.ocultosNaVista = ocultos.size ? ocultos : null;
    this.cena.definirCorPorValor((e) => {
      const f = e.atributos && e.atributos.fase;
      if (!f) return '#cbd5e1';
      const i = ordem.get(f);
      return i === ate ? '#f59e0b' : '#8b95a5';
    });
    this.documento.notificarAparencia();
  }

  _desenharSequencia() {
    const p = this._painelSequencia;
    if (!p) return;
    const s = this._sequencia;
    const fases = this.fasesDoModelo();
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    if (!fases.length) {
      corpo.append(el('p', { texto: 'Nenhuma peça tem fase ainda. Selecione as peças da primeira etapa de montagem no 3D e use o campo abaixo — ou o campo Fase / lote do painel Produção.' }));
    } else {
      const ate = s.ate == null ? fases.length - 1 : Math.min(s.ate, fases.length - 1);
      s.ate = ate;
      const faixa = el('input', { type: 'range', min: 0, max: fases.length - 1, step: 1, value: ate, style: 'width:100%' });
      faixa.addEventListener('input', () => { s.ate = Number(faixa.value); this._aplicarSequencia(); this._desenharSequencia(); });
      const passo = (d) => { s.ate = Math.max(0, Math.min(fases.length - 1, s.ate + d)); this._aplicarSequencia(); this._desenharSequencia(); };
      const tocar = el('button', { type: 'button', texto: this._tocandoSequencia ? '■ parar' : '▶ tocar' });
      tocar.addEventListener('click', () => {
        if (this._tocandoSequencia) { clearInterval(this._tocandoSequencia); this._tocandoSequencia = null; this._desenharSequencia(); return; }
        s.ate = 0; this._aplicarSequencia();
        this._tocandoSequencia = setInterval(() => {
          if (!this._sequencia || s.ate >= fases.length - 1) { clearInterval(this._tocandoSequencia); this._tocandoSequencia = null; this._desenharSequencia(); return; }
          s.ate += 1; this._aplicarSequencia(); this._desenharSequencia();
        }, 1200);
        this._desenharSequencia();
      });
      const semFase = el('input', { type: 'checkbox', checked: s.semFase });
      semFase.addEventListener('change', () => { s.semFase = semFase.checked; this._aplicarSequencia(); });
      const atual = fases[ate];
      const acum = fases.slice(0, ate + 1).reduce((t, f) => t + f.peso, 0);
      corpo.append(
        el('div', { style: 'display:flex;gap:6px;align-items:center;margin-bottom:4px' },
          el('button', { type: 'button', texto: '◀', title: 'Fase anterior', onclick: () => passo(-1) }), faixa,
          el('button', { type: 'button', texto: '▶', title: 'Próxima fase', onclick: () => passo(1) }), tocar),
        el('p', { texto: `Até ${atual.fase} (${ate + 1} de ${fases.length}): ${numero(atual.ids.length)} peça(s) nesta fase, ${numero(acum / 1000, 2)} t montadas até aqui.` }),
        el('label', { style: 'display:block' }, semFase, ' mostrar as peças sem fase (em cinza claro)'));
      const ul = el('ul');
      fases.forEach((f, i) => {
        const li = el('li', { texto: `${f.fase} — ${numero(f.ids.length)} peça(s), ${numero(f.peso, 0)} kg`, title: 'Clique: ir até esta fase · duplo clique: selecionar as peças dela',
          style: i === ate ? 'font-weight:600;color:#b45309' : (i > ate ? 'opacity:.55' : '') });
        li.addEventListener('click', () => { s.ate = i; this._aplicarSequencia(); this._desenharSequencia(); });
        li.addEventListener('dblclick', () => this.selecao.definir(f.ids));
        ul.append(li);
      });
      corpo.append(ul);
    }
    // pôr as peças selecionadas numa fase (montar a sequência clicando no 3D)
    const nomeFase = el('input', { type: 'text', placeholder: 'Etapa 1', style: 'width:8em' });
    const por = el('button', { type: 'button', texto: 'pôr a seleção nesta fase' });
    por.addEventListener('click', () => {
      const v = nomeFase.value.trim();
      const ids = [...this.selecao.ids];
      if (!v || !ids.length) { this.dica('Selecione as peças no 3D e escreva o nome da fase.'); return; }
      this.alterarEntidades(ids, (e) => ({ atributos: { ...clonar(e.atributos || {}), fase: v } }), `Fase ${v}`);
      const fs = this.fasesDoModelo();
      s.ate = Math.max(0, fs.findIndex(f => f.fase === v));
      this._aplicarSequencia();
      this._desenharSequencia();
    });
    corpo.append(el('div', { style: 'display:flex;gap:6px;align-items:center;margin-top:6px' }, nomeFase, por));
    p.replaceChildren(
      el('div', { class: 'painel-apoios-titulo' }, el('strong', { texto: 'Sequência de montagem' }),
        el('button', { type: 'button', texto: '×', title: 'Fechar (volta as cores de antes)', onclick: () => this._fecharSequencia() })),
      corpo);
    this._aplicarSequencia();
  }

  // ---------------------------------------------------------------- árvore do modelo por propriedade

  /** O seletor do topo da árvore: por camada (como era) ou pela organização de produção, como o navegador do Revit. */
  _seletorArvore() {
    const modo = this.arvorePor || 'camada';
    const sel = el('select', { title: 'Como a árvore organiza as peças' });
    for (const [v, t] of [['camada', 'camada'], ['conjunto', 'conjunto → posição'], ['perfil', 'perfil → posição'],
                          ['fase', 'fase → conjunto'], ['papel', 'papel → perfil']]) {
      sel.append(el('option', { value: v, texto: t, selected: v === modo }));
    }
    sel.addEventListener('change', () => { this.arvorePor = sel.value; this._agendarPaineis('arvore'); });
    return el('div', { class: 'cor-por', style: 'margin:2px 4px 6px' }, el('label', { texto: 'Organizar por' }), sel);
  }

  _arvorePorPropriedade(raiz) {
    const modo = this.arvorePor;
    const m_ = (e) => marcasDe(e);
    const parafuso = (e) => !!(e.atributos && e.atributos.parafuso) || /BOLT|PARAFUSO/i.test(e.nome || '');
    const perfil = (e) => (e.tipo === 'barra' ? e.perfil : e.tipo === 'chapa' ? `CH ${numero(e.espessura || 0, 2)}` : (m_(e).perfil || e.nome || e.tipo));
    const niveis = {
      conjunto: [(e) => parafuso(e) ? 'parafusos' : (m_(e).conjunto || '(sem conjunto)'), (e) => m_(e).posicao || '(sem marca)'],
      perfil: [(e) => parafuso(e) ? 'parafusos' : perfil(e), (e) => m_(e).posicao || '(sem marca)'],
      fase: [(e) => (e.atributos && e.atributos.fase) || '(sem fase)', (e) => m_(e).conjunto || '(sem conjunto)'],
      papel: [(e) => parafuso(e) ? 'parafuso' : (e.papel || e.tipo), (e) => perfil(e)],
    }[modo];
    if (!niveis) return;
    const arv = new Map();
    for (const e of this.documento.entidades.values()) {
      const a = e.atributos || {};
      if (a.tipo === 'cota' || a.tipo === 'construcao' || e.tipo === 'grupo') continue;
      const k1 = niveis[0](e), k2 = niveis[1](e);
      if (!arv.has(k1)) arv.set(k1, new Map());
      const sub = arv.get(k1);
      if (!sub.has(k2)) sub.set(k2, []);
      sub.get(k2).push(e);
    }
    this._ramosBIM = this._ramosBIM || new Set();
    const ord = (a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true });
    const arvore = el('div', { class: 'arvore' });
    const ramoDe = (caminho, rotulo, ids, filhos) => {
      const ramo = el('div', { class: 'ramo' });
      const aberto = this._ramosBIM.has(caminho);
      if (aberto) ramo.dataset.aberto = '';
      const nsel = ids.filter(i => this.selecao.tem(i)).length;
      ramo.append(el('button', { type: 'button', class: 'titulo', title: 'Clique abre/fecha · duplo clique seleciona tudo daqui',
        onclick: () => { if (aberto) this._ramosBIM.delete(caminho); else this._ramosBIM.add(caminho); this._agendarPaineis('arvore'); },
        ondblclick: (ev) => { if (ev.shiftKey) this.selecao.somar(ids); else this.selecao.definir(ids); } },
        el('span', { texto: String(rotulo) }),
        el('span', { class: 'contagem', texto: nsel ? `${nsel}/${ids.length}` : String(ids.length) })));
      if (aberto) ramo.append(filhos());
      return ramo;
    };
    for (const k1 of [...arv.keys()].sort(ord)) {
      const sub = arv.get(k1);
      const ids1 = [...sub.values()].flat().map(e => e.id);
      arvore.append(ramoDe(`${modo}|${k1}`, k1, ids1, () => {
        const folhas = el('div', { class: 'folhas' });
        for (const k2 of [...sub.keys()].sort(ord)) {
          const ents = sub.get(k2);
          folhas.append(ramoDe(`${modo}|${k1}|${k2}`, `${k2}`, ents.map(e => e.id), () => {
            const f2 = el('div', { class: 'folhas' });
            for (const e of ents.slice(0, 300)) {
              f2.append(el('button', { type: 'button', class: 'folha', 'aria-selected': String(this.selecao.tem(e.id)),
                title: this.descreverEntidade(e), onclick: (ev) => this.selecao.clicar(e.id, ev),
                ondblclick: () => this.camera.zoomSelecao([e.id]) },
                el('span', { texto: m_(e).nome || m_(e).posicao || e.nome || e.tipo }),
                el('span', { class: 'detalhe', texto: e.tipo === 'barra' ? `${numero(comprimentoDaBarra(e))} mm` : perfil(e) })));
            }
            if (ents.length > 300) f2.append(el('div', { class: 'vazio', style: 'padding:2px 6px', texto: `+ ${ents.length - 300} (duplo clique no ramo seleciona todas)` }));
            return f2;
          }));
        }
        return folhas;
      }));
    }
    raiz.append(arvore);
  }

  // ---------------------------------------------------------------- tabela de peças ao vivo

  abrirTabela() {
    if (this._painelTabela) { this._painelTabela.remove(); this._painelTabela = null; return; }
    this._tabelaPor = this._tabelaPor || 'posicao';
    this._painelTabela = el('div', { class: 'painel-apoios painel-tabela' });
    this._painelTabela.style.maxWidth = '640px';
    (this.el.palco || document.body).append(this._painelTabela);
    this._desenharTabela();
  }

  _agendarTabela() {
    clearTimeout(this._timerTabela);
    this._timerTabela = setTimeout(() => this._desenharTabela(), 700);
  }

  /** As linhas da tabela: [{chave, ids, qtd, comprimento (mm), peso (kg), perfis}] e o total. */
  linhasDaTabela(por) {
    const grupos = new Map();
    for (const e of this.documento.entidades.values()) {
      const a = e.atributos || {};
      if (a.tipo === 'cota' || a.tipo === 'construcao' || a.furo) continue;
      if (e.tipo === 'grupo') continue;
      const m = marcasDe(e);
      const parafuso = !!a.parafuso || /BOLT|PARAFUSO/i.test(e.nome || '');
      let chave;
      switch (por) {
        case 'perfil': chave = parafuso ? 'parafusos' : (e.tipo === 'barra' ? e.perfil : e.tipo === 'chapa' ? `CH ${numero(e.espessura || 0, 2)}` : (m.perfil || e.nome || 'sólido')); break;
        case 'conjunto': chave = m.conjunto || (parafuso ? 'parafusos' : '(sem conjunto)'); break;
        case 'fase': chave = a.fase || '(sem fase)'; break;
        case 'papel': chave = parafuso ? 'parafuso' : (e.papel || e.tipo); break;
        case 'acabamento': chave = a.acabamento || '(sem acabamento)'; break;
        default:
          if (por.startsWith('u:')) { chave = (a.props_usuario || {})[por.slice(2)] || `(sem ${por.slice(2)})`; break; }
          chave = parafuso ? (e.nome || 'parafuso') : (m.posicao || '(sem marca)');
      }
      if (!grupos.has(chave)) grupos.set(chave, { chave, ids: [], qtd: 0, comprimento: 0, peso: 0, perfis: new Set() });
      const g = grupos.get(chave);
      g.ids.push(e.id); g.qtd += 1;
      if (e.tipo === 'barra') g.comprimento += comprimentoDaBarra(e);
      if (!parafuso) g.peso += this.pesoDaPeca(e);
      g.perfis.add(e.tipo === 'barra' ? e.perfil : (m.perfil || (e.tipo === 'chapa' ? `CH ${numero(e.espessura || 0, 2)}` : e.nome || e.tipo)));
    }
    const linhas = [...grupos.values()].sort((a, b) => String(a.chave).localeCompare(String(b.chave), 'pt-BR', { numeric: true }));
    const total = linhas.reduce((t, g) => ({ qtd: t.qtd + g.qtd, comprimento: t.comprimento + g.comprimento, peso: t.peso + g.peso }),
      { qtd: 0, comprimento: 0, peso: 0 });
    return { linhas, total };
  }

  _desenharTabela() {
    const p = this._painelTabela;
    if (!p) return;
    const por = this._tabelaPor;
    const filtro = (this._filtroTabela || '').toLowerCase();
    const { linhas, total } = this.linhasDaTabela(por);
    const visiveis = filtro ? linhas.filter(g => `${g.chave} ${[...g.perfis].join(' ')}`.toLowerCase().includes(filtro)) : linhas;
    const sel = el('select');
    const chavesU = [...new Set([...this.documento.entidades.values()].flatMap(e => Object.keys((e.atributos && e.atributos.props_usuario) || {})))].sort();
    for (const [v, t] of [['posicao', 'posição'], ['perfil', 'perfil'], ['conjunto', 'conjunto'], ['fase', 'fase'], ['papel', 'papel'], ['acabamento', 'acabamento'],
                          ...chavesU.map(k => [`u:${k}`, k])]) {
      sel.append(el('option', { value: v, texto: t, selected: v === por }));
    }
    sel.addEventListener('change', () => { this._tabelaPor = sel.value; this._desenharTabela(); });
    const busca = el('input', { type: 'search', placeholder: 'filtrar…', value: this._filtroTabela || '', style: 'width:9em' });
    busca.addEventListener('input', () => { this._filtroTabela = busca.value; clearTimeout(this._timerBusca); this._timerBusca = setTimeout(() => this._desenharTabela(), 250); });
    const csv = el('button', { type: 'button', texto: 'CSV', title: 'Baixar a tabela para o Excel' });
    csv.addEventListener('click', () => this._baixarTabela(por, visiveis));
    const tabela = el('table', { class: 'tabela-pecas', style: 'width:100%;border-collapse:collapse;font-size:12px' });
    const cab = el('tr', {}, ...['Grupo', 'Qtd', 'Perfil', 'Comprimento (m)', 'Peso (kg)'].map(t => el('th', { texto: t, style: 'text-align:left;border-bottom:1px solid rgba(127,127,127,.4);padding:2px 4px' })));
    tabela.append(cab);
    for (const g of visiveis.slice(0, 1500)) {
      const tr = el('tr', { title: 'Clique: selecionar · Shift: somar · duplo clique: enquadrar', style: 'cursor:pointer' },
        el('td', { texto: String(g.chave), style: 'padding:1px 4px' }),
        el('td', { texto: numero(g.qtd), style: 'padding:1px 4px' }),
        el('td', { texto: [...g.perfis].slice(0, 3).join(', ') + (g.perfis.size > 3 ? '…' : ''), style: 'padding:1px 4px' }),
        el('td', { texto: g.comprimento ? numero(g.comprimento / 1000, 2) : '—', style: 'padding:1px 4px' }),
        el('td', { texto: g.peso ? numero(g.peso, 1) : '—', style: 'padding:1px 4px' }));
      tr.addEventListener('click', (ev) => { if (ev.shiftKey) this.selecao.somar(g.ids); else this.selecao.definir(g.ids); });
      tr.addEventListener('dblclick', () => { this.selecao.definir(g.ids); this.camera.zoomSelecao(g.ids); });
      tabela.append(tr);
    }
    tabela.append(el('tr', { style: 'font-weight:600' }, el('td', { texto: `Total (${numero(visiveis.length)} grupos)` }),
      el('td', { texto: numero(filtro ? visiveis.reduce((s, g) => s + g.qtd, 0) : total.qtd) }), el('td'),
      el('td', { texto: numero((filtro ? visiveis.reduce((s, g) => s + g.comprimento, 0) : total.comprimento) / 1000, 2) }),
      el('td', { texto: numero(filtro ? visiveis.reduce((s, g) => s + g.peso, 0) : total.peso, 1) })));
    p.replaceChildren(
      el('div', { class: 'painel-apoios-titulo' }, el('strong', { texto: 'Tabela de peças' }), el('span', { texto: ' por ' }), sel, busca, csv,
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this.abrirTabela() })),
      el('div', { class: 'painel-apoios-corpo', style: 'max-height:55vh;overflow:auto' },
        el('p', { class: 'explica', texto: 'Ao vivo: muda junto com o modelo. Peso das barras pelo perfil, das chapas pela área e dos sólidos pelo volume; parafusos contados à parte.' }),
        tabela));
  }

  _baixarTabela(por, linhas) {
    const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
    const corpo = [['Grupo (' + por + ')', 'Quantidade', 'Perfis', 'Comprimento (m)', 'Peso (kg)'].map(esc).join(';')]
      .concat(linhas.map(g => [g.chave, g.qtd, [...g.perfis].join(', '), (g.comprimento / 1000).toFixed(2).replace('.', ','),
        g.peso.toFixed(1).replace('.', ',')].map(esc).join(';')));
    const blob = new Blob(['﻿' + corpo.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = el('a', { href: URL.createObjectURL(blob), download: `tabela-de-pecas-${por}.csv` });
    document.body.append(a); a.click(); a.remove();
  }
}
