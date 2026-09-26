// CAD 2D: ponto de entrada. Monta tela, ferramentas, painéis, snap e a conversa com o
// projeto (desenhos em <projeto>/desenhos-2d/, gravados sozinhos a cada mudança).
//
// Mouse: botão esquerdo é da ferramenta; do meio ou direito arrasta a vista; roda dá
// zoom no cursor. Shift trava orto. Esc cancela; Enter e espaço confirmam/repetem.

import { Desenho2D, clonar, valorCota, pontosDe, criar, segmentosDe, dist, maisProximoSeg } from './nucleo/desenho2d.js';
import { Pilha, ComandoRemover, ComandoAlterar, ComandoAparencia, ComandoAdicionar, ComandoComposto } from './nucleo/comandos.js';
import { Tela, formatarMm } from './nucleo/tela.js';
import { Snap } from './nucleo/snap.js';
import { FERRAMENTAS, GRUPOS, Ferramenta } from './ferramentas.js';
import { MetodosLancamentoCAD, DESENHO_LANCAMENTO } from './lancamento.js';

const CHAVE_TEMA = 'galpao.tema';
const ATRASO_AUTOSAVE = 3000;
const ARRASTO_MIN = 4;
const $ = (s, r = document) => r.querySelector(s);

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) { if (f === null || f === undefined || f === false) continue; e.append(f.nodeType ? f : document.createTextNode(String(f))); }
  return e;
}

async function pedir(rota, opcoes = {}) {
  let r;
  try { r = await fetch(rota, opcoes); } catch (e) { throw new Error('não foi possível falar com o servidor — ele ainda está no ar?'); }
  const texto = await r.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
  if (!r.ok || (dados && dados.erro)) throw new Error((dados && dados.erro) || `${r.status} ${r.statusText}`);
  return dados;
}
const postar = (rota, corpo) => pedir(rota, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo || {}) });
/** Arquivo → base64 (sem o prefixo data:), para mandar ao servidor sem perder bytes. */
function base64DoArquivo(arquivo) {
  return new Promise((ok, erro) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).replace(/^data:[^,]*,/, ''));
    r.onerror = () => erro(r.error || new Error('não foi possível ler o arquivo'));
    r.readAsDataURL(arquivo);
  });
}
const TIPOS_VISTA = { planta: 'planta', trelica: 'tesoura/treliça', elevacao: 'elevação/pórtico', lateral: 'fachada lateral', detalhe: 'detalhe' };
const tipoDeVista = (t) => TIPOS_VISTA[t] || 'vista';
const textoEscala = (v) => {
  const f = Number(v.fator || 1);
  const de = { cotas: 'pelas cotas', titulo: 'pelo título', padrao: 'a conferir', informado: 'informada', cm: 'desenho em cm' }[v.fator_origem] || '';
  return (f >= 2 && Number.isInteger(Math.round(f * 100) / 100) ? `1:${Math.round(f)}` : `${Math.round(f * 1000) / 1000} mm/unidade`) + (de ? ` (${de})` : '');
};
const numero = (v, casas = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

class CAD {
  constructor() {
    this.parametros = new URLSearchParams(location.search);
    this.projeto = this.parametros.get('projeto') || null;
    this.nomeDesenho = this.parametros.get('desenho') || null;
    this.doc = new Desenho2D();
    this.pilha = new Pilha(this.doc);
    this.tela = new Tela($('#canvas2d'), this.doc);
    this.snap = new Snap(this.tela);
    this.camadaAtiva = 'VISTA';
    this.alturaTexto = 2.5;
    this.ferramentas = new Map();
    this.ferramenta = null;
    this._autosavePendente = false;
    this._autosaveTimer = null;
    this._salvando = false;
    this._paineisPendentes = new Set();
    this.el = {
      palco: $('#palco'), canvas: $('#canvas2d'), dica: $('#dica'), medida: $('#medida'), avisos: $('#avisos'),
      barra: $('#barra-ferramentas'), props: $('#painel-propriedades'), camadas: $('#painel-camadas'),
      snap: $('#painel-snap'), vistas: $('#painel-vistas'), nome: $('#nome-desenho'), escala: $('#escala'),
      contagem: $('#carimbo-contagem'), coord: $('#carimbo-coord'), estadoSalvo: $('#estado-salvo'),
    };
  }

  // ------------------------------------------------------------- início
  async iniciar() {
    this._aplicarTema(this.parametros.get('tema') || lerTema());
    this.tela.escuro = document.documentElement.getAttribute('data-tema') === 'escuro' ||
      (!document.documentElement.getAttribute('data-tema') && matchMedia('(prefers-color-scheme: dark)').matches);
    this._montarFerramentas();
    this._ligarMouse();
    this._ligarTeclado();
    this._ligarMenus();
    this._ligarPaineis();
    this.doc.aoMudar((ev) => this._aposMudanca(ev));
    this.pilha.aoMudar(() => this._atualizarMenuEditar());
    new ResizeObserver(() => this.tela.redimensionar()).observe(this.el.palco);
    this.tela.redimensionar();
    this.ativarFerramenta('selecionar');

    if (this.projeto) {
      $('#link-editor').href = this.urlDoEditor();
      try {
        const p = (await pedir('/api/projetos/' + encodeURIComponent(this.projeto))).projeto;
        this.tituloProjeto = p.nome || this.projeto;
      } catch (e) { this.aviso(`Projeto "${this.projeto}" não encontrado: ${e.message}`, 'erro', 0); this.projeto = null; }
    } else {
      $('#link-editor').hidden = true;
      this.aviso('Sem projeto: o desenho fica só nesta janela. Abra pelo gerenciador para gravar no projeto.', 'atencao', 0);
    }
    const pedirArquitetonico = this.projeto && this.parametros.get('arquitetonico') === '1';
    if (pedirArquitetonico) {
      // projeto novo "a partir do arquitetônico": abre (ou cria) a planta e pede o arquivo
      const url = new URL(location.href); url.searchParams.delete('arquitetonico'); history.replaceState(null, '', url);
      if (!this.nomeDesenho) this.nomeDesenho = DESENHO_LANCAMENTO;
    }
    if (this.projeto && this.nomeDesenho && !(pedirArquitetonico && !(await this._listaDesenhos()).some(d => d.nome === this.nomeDesenho))) await this.abrirDesenho(this.nomeDesenho);
    else if (this.projeto) {
      const lista = await this._listaDesenhos();
      if (lista.length) await this.abrirDesenho(lista[0].nome);
      else this.dica('Desenho novo. Use "Vistas do modelo" para trazer uma vista do 3D, ou desenhe à mão.');
    }
    if (pedirArquitetonico) {
      // o seletor de arquivo só abre com um clique do usuário: o botão do diálogo é esse clique
      setTimeout(async () => {
        const corpo = el('div', {}, el('div', { class: 'explica', texto: 'Projeto a partir do arquitetônico. O caminho: (1) o DXF ou PDF da planta do cliente vira a referência, travada e em cinza; (2) Malha de eixos… desenha os eixos por cima dela; (3) Gravar eixos no projeto; (4) Lançar estrutura no 3D monta e dimensiona o galpão nos eixos.' }));
        if (await this.dialogo({ titulo: 'Arquitetônico do cliente', corpo, ok: 'Escolher o arquivo (DXF ou PDF)…' }) === 'ok') $('#arquivo-arquitetonico').click();
      }, 200);
    }
    try { if (localStorage.getItem('cad.orto') === '1') this.snap.orto = true; } catch { /* sem armazenamento */ }
    this._agendarPaineis('props', 'camadas', 'snap', 'vistas');
    this._atualizarCarimbo();
    document.body.dataset.pronto = '1';
    window.cad = this;
    // o botão "Atualizar" (web/atualizacao.js) grava o desenho antes de instalar — e
    // espera confirmar: falhou, a atualização não segue
    window.__antesDeAtualizar = () => this.gravarConfirmado();
    // fechar a janela com edição por gravar avisa (o navegador pergunta se quer sair)
    window.addEventListener('beforeunload', (e) => {
      if (this.projeto && (this._editado || this._salvando) && !this._desenhoBloqueado()) { e.preventDefault(); e.returnValue = ''; }
    });
    // "Modelo 3D" grava o pendente antes de sair (antes ia direto e perdia os últimos segundos)
    const link3d = $('#link-editor');
    if (link3d) link3d.addEventListener('click', (ev) => {
      if (!this.projeto || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      ev.preventDefault();
      this._sairPara(link3d.href);
    });
  }

  // ---------------------------------------------------------- documento
  carregar(json, { enquadrar = true } = {}) {
    const novo = Desenho2D.deJSON(json);
    this.selecionar([]);
    this.doc.substituirPor(novo);
    this.pilha.limpar();
    this.el.nome.value = this.doc.nome || 'Desenho';
    this._refletirEscala();
    if (enquadrar) this.tela.enquadrar();
    this._autosavePendente = false;
    this._editado = false;
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    this._agendarPaineis('props', 'camadas', 'vistas');
    document.title = `${this.doc.nome} — Desenho 2D`;
  }

  async abrirDesenho(nome) {
    // trocar de desenho grava antes o que ainda não foi (eram 3 s, ou 15 s em desenho grande, perdidos)
    if (this.nomeDesenho && this.nomeDesenho !== nome && this._temPendente()) {
      if (!(await this._gravarOuConfirmar('Abrir o outro desenho mesmo assim'))) return;
    }
    try {
      const r = await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(nome)}`);
      this.nomeDesenho = nome;
      this._naoAbriu = null;
      this.carregar(r.desenho);
      const url = new URL(location.href); url.searchParams.set('desenho', nome); history.replaceState(null, '', url);
      const link3d = $('#link-editor');
      if (link3d && this.projeto) link3d.href = this.urlDoEditor();       // o 3D sabe voltar a este desenho
      this.dica(`Desenho "${this.doc.nome}" aberto: ${numero(this.doc.tamanho)} objetos, escala 1:${this.doc.escala}.`);
    } catch (e) {
      // o desenho não veio: nada é gravado com o nome dele, senão a tela vazia (ou o que se
      // desenhasse nela) ia por cima do arquivo que existe
      if (this.nomeDesenho === nome || !this.nomeDesenho) { this.nomeDesenho = nome; this._naoAbriu = nome; }
      this.aviso(`Não foi possível abrir "${nome}": ${e.message}. Nada será gravado com esse nome nesta tela — recarregue (F5) para tentar de novo.`, 'erro', 0);
    }
  }

  _desenhoBloqueado() { return !!(this._naoAbriu && this._naoAbriu === this.nomeDesenho); }

  _temPendente() { return !!(this._editado || this._salvando || this._autosaveTimer || this._autosavePendente); }

  /**
   * Grava o desenho e só volta quando gravou (ou lança o erro): espera a gravação que já
   * estiver em curso — o `salvar` da gravação automática sai na hora nesse caso — e não
   * engole a falha. É o que o Atualizar, a troca de desenho e as saídas da tela usam.
   */
  async gravarConfirmado({ forcar = false } = {}) {
    if (!this.projeto) return null;
    if (this._desenhoBloqueado()) throw new Error(`o desenho "${this.nomeDesenho}" não abriu nesta tela; nada foi gravado, para não sobrescrevê-lo`);
    if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
    const t0 = Date.now();
    while (this._salvando) {
      if (Date.now() - t0 > 90000) throw new Error('a gravação em curso não terminou');
      await new Promise(r => setTimeout(r, 150));
    }
    if (!forcar && !this._editado && !this._autosavePendente) return null;
    if (!this.doc.tamanho && !forcar) return null;
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || this.doc.nome || 'desenho');
    this.doc.nome = this.el.nome.value.trim() || this.doc.nome;
    this._salvando = true;
    this.el.estadoSalvo.textContent = 'gravando…';
    const versao = this._versaoEdicao || 0;
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}`, { desenho: this.doc.paraJSON() });
      this.el.estadoSalvo.textContent = 'gravado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      if ((this._versaoEdicao || 0) === versao) this._editado = false;
      this._autosavePendente = false;
      return r;
    } catch (e) {
      this.el.estadoSalvo.textContent = 'não foi possível gravar';
      throw e;
    } finally {
      this._salvando = false;
    }
  }

  /** Grava o pendente; falhou, pergunta se segue mesmo assim. Devolve se pode seguir. */
  async _gravarOuConfirmar(rotuloSeguir) {
    try { await this.gravarConfirmado(); return true; } catch (e) {
      const corpo = el('div', { class: 'explica', texto: `Não foi possível gravar o desenho "${this.nomeDesenho}": ${e.message}. Seguir perde o que não foi gravado.` });
      if (await this.dialogo({ titulo: 'Desenho não gravado', corpo, ok: rotuloSeguir }) !== 'ok') return false;
      this._editado = false;
      return true;
    }
  }

  /** Sai para outra tela depois de gravar o pendente (e esperar a gravação em curso). */
  async _sairPara(url) {
    if (this._temPendente() && !this._desenhoBloqueado() && !(await this._gravarOuConfirmar('Sair mesmo assim'))) return false;
    this._editado = false;
    location.href = url;
    return true;
  }

  async _listaDesenhos() {
    try { return await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos`); } catch { return []; }
  }

  async salvar({ avisar = true } = {}) {
    if (!this.projeto) { if (avisar) this.aviso('Sem projeto aberto: nada para gravar.', 'atencao'); return; }
    if (this._desenhoBloqueado()) {
      if (avisar) this.aviso(`O desenho "${this.nomeDesenho}" não abriu nesta tela: nada foi gravado, para não sobrescrevê-lo. Recarregue (F5).`, 'erro', 0);
      return;
    }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || this.doc.nome || 'desenho');
    this.doc.nome = this.el.nome.value.trim() || this.doc.nome;
    if (this._salvando) { this._autosavePendente = true; return; }
    this._salvando = true;
    this.el.estadoSalvo.textContent = 'gravando…';
    const versao = this._versaoEdicao || 0;
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}`, { desenho: this.doc.paraJSON() });
      if ((this._versaoEdicao || 0) === versao) this._editado = false;
      this.el.estadoSalvo.textContent = 'gravado às ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      if (avisar) this.aviso(`Desenho salvo no projeto (${numero(r.entidades)} objetos).`, 'info');
    } catch (e) {
      this.el.estadoSalvo.textContent = 'não foi possível gravar';
      if (avisar) this.aviso(`Não foi possível salvar: ${e.message}`, 'erro', 0);
    } finally {
      this._salvando = false;
      if (this._autosavePendente) { this._autosavePendente = false; this._agendarAutosave(); }
    }
  }

  /**
   * Volta para a tela de onde o desenho foi aberto (o modelo 3D, a lista de desenhos…).
   * O que está pendente de gravação é gravado antes — `fechar` avisa que salvou; o
   * Voltar simples também grava o pendente, para nada se perder na troca de tela.
   */
  async voltar(fechar) {
    if (this.nomeDesenho && this.doc.tamanho && !this._desenhoBloqueado() && (fechar || this._temPendente())) {
      // espera a gravação em curso e confirma; falhou, pergunta antes de sair
      try {
        await this.gravarConfirmado({ forcar: !!fechar });
        if (fechar) this.aviso('Desenho salvo no projeto.', 'info');
      } catch (e) {
        const corpo = el('div', { class: 'explica', texto: `Não foi possível gravar o desenho: ${e.message}. Sair perde o que não foi gravado.` });
        if (await this.dialogo({ titulo: 'Desenho não gravado', corpo, ok: 'Sair mesmo assim' }) !== 'ok') return;
      }
    }
    this._editado = false;
    const mesmaOrigem = document.referrer && new URL(document.referrer).origin === location.origin;
    if (mesmaOrigem && history.length > 1) { history.back(); return; }
    location.href = this.projeto ? this.urlDoEditor() : '/';
  }

  /** O editor 3D deste projeto, levando o nome do desenho para o "← Desenho 2D" de lá. */
  urlDoEditor(extra = '') {
    return `/editor?projeto=${encodeURIComponent(this.projeto)}` +
      (this.nomeDesenho ? `&desenho=${encodeURIComponent(this.nomeDesenho)}` : '') + extra;
  }

  _agendarAutosave() {
    this._editado = true;
    this._versaoEdicao = (this._versaoEdicao || 0) + 1;
    if (!this.projeto) return;
    if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
    // desenho enorme (modelo inteiro): serializar 100 MB trava a tela por um instante,
    // então espera mais, para uma sequência de edições gravar uma vez só
    const atraso = this.doc.tamanho > 100000 ? ATRASO_AUTOSAVE * 5 : ATRASO_AUTOSAVE;
    this._autosaveTimer = setTimeout(() => { this._autosaveTimer = null; this.salvar({ avisar: false }); }, atraso);
  }

  async exportarDXF() {
    if (!this.doc.tamanho) { this.dica('O desenho está vazio.'); return; }
    if (!this.projeto) { this.aviso('Exportar DXF precisa de um projeto aberto.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || 'desenho');
    this.dica('Gerando o DXF…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/dxf`, { desenho: this.doc.paraJSON(), escala: this.doc.escala });
      const a = r.arquivo || {};
      this.aviso(el('span', {}, `DXF gerado (${numero(r.entidades)} objetos, 1:${this.doc.escala}): `,
        el('a', { href: a.url, download: a.nome || true, texto: a.nome || 'baixar' }), a.tamanho_kb ? ` · ${numero(a.tamanho_kb, 1)} kB` : ''), 'info', 0);
      this.dica('DXF exportado.');
    } catch (e) { this.aviso(`Não foi possível exportar: ${e.message}`, 'erro', 0); }
  }

  async exportarPDF() {
    if (!this.doc.tamanho) { this.dica('O desenho está vazio.'); return; }
    if (!this.projeto) { this.aviso('Exportar PDF precisa de um projeto aberto.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || 'desenho');
    this.dica('Gerando o PDF…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/pdf`, { desenho: this.doc.paraJSON() });
      const a = r.arquivo || {};
      this.aviso(el('span', {}, 'PDF gerado: ', el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: a.nome || 'abrir' }), a.tamanho_kb ? ` · ${numero(a.tamanho_kb, 0)} kB` : ''), 'info', 0);
      this.dica('PDF exportado.');
      window.open(a.url, '_blank');
    } catch (e) { this.aviso(`Não foi possível gerar o PDF: ${e.message}`, 'erro', 0); }
  }

  /** Um PDF com todas as pranchas do projeto (as de nome "Prancha NN"), em ordem. */
  async pdfDasPranchas() {
    if (!this.projeto) { this.aviso('Precisa de um projeto aberto.', 'atencao'); return; }
    const lista = (await this._listaDesenhos()).filter(d => /^prancha-\d+$/i.test(d.nome))
      .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { numeric: true }));
    if (!lista.length) { this.aviso('O projeto não tem pranchas ainda: Desenho → Montar pranchas…', 'atencao'); return; }
    if (this.nomeDesenho && lista.some(d => d.nome === this.nomeDesenho)) await this.salvar({ avisar: false });
    this.dica(`Gerando o PDF de ${lista.length} prancha(s)…`);
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(lista[0].nome)}/pdf`, { desenhos: lista.map(d => d.nome), titulo: 'pranchas' });
      const a = r.arquivo || {};
      this.aviso(el('span', {}, `PDF com ${r.paginas} página(s): `, el('a', { href: a.url, target: '_blank', rel: 'noopener', texto: a.nome || 'abrir' }), a.tamanho_kb ? ` · ${numero(a.tamanho_kb, 0)} kB` : ''), 'info', 0);
      this.dica('PDF das pranchas exportado (pasta pranchas/ do projeto).');
      window.open(a.url, '_blank');
    } catch (e) { this.aviso(`Não foi possível gerar o PDF: ${e.message}`, 'erro', 0); }
  }

  async inserirVista(definicao, titulo) {
    if (!this.projeto) { this.aviso('Inserir vista precisa de um projeto com modelo 3D.', 'atencao'); return; }
    if (!this.nomeDesenho) this.nomeDesenho = slug(this.el.nome.value || titulo || 'desenho');
    this.dica(`Gerando a vista "${titulo}" do modelo… (um modelo grande leva alguns segundos)`);
    try {
      // grava o estado atual primeiro, para a vista entrar em cima do que já existe
      if (this.doc.tamanho) await this.salvar({ avisar: false });
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/vista2d`, { vista: definicao, desenho: this.nomeDesenho, titulo: this.el.nome.value || titulo });
      await this.abrirDesenho(this.nomeDesenho);
      const v = r.vista || {};
      this.aviso(`Vista "${titulo}" inserida: ${v.pecas_cortadas || 0} peça(s) cortada(s), ${v.pecas_projetadas || 0} projetada(s), ${numero(v.largura)} × ${numero(v.altura)} mm.` +
                 (v.avisos && v.avisos.length ? ` ${v.avisos.length} aviso(s).` : ''), 'info', 9000);
    } catch (e) { this.aviso(`Não foi possível gerar a vista: ${e.message}`, 'erro', 0); this.dica('Vista não gerada.'); }
  }

  _aposMudanca({ acao }) {
    this.tela.pedirQuadro();
    this._podarSelecao();
    this._agendarPaineis('props', acao === 'aparencia' || acao === 'tudo' ? 'camadas' : null, acao === 'tudo' ? 'vistas' : null);
    this._atualizarCarimbo();
    this._agendarAutosave();
  }

  executar(cmd) { this.pilha.executar(cmd); }
  desfazer() { const c = this.pilha.desfazer(); if (c) this.dica(`Desfeito: ${c.rotulo}`); }
  refazer() { const c = this.pilha.refazer(); if (c) this.dica(`Refeito: ${c.rotulo}`); }

  // ------------------------------------------------------------ seleção
  selecionar(ids) {
    this.tela.selecao = new Set(ids.filter(id => this.doc.get(id)));
    this.tela.pedirQuadro();
    this._agendarPaineis('props');
    this._atualizarCarimbo();
  }
  alternarSelecao(id) { const s = new Set(this.tela.selecao); s.has(id) ? s.delete(id) : s.add(id); this.selecionar([...s]); }
  _podarSelecao() { const antes = this.tela.selecao.size; this.tela.selecao = new Set([...this.tela.selecao].filter(id => this.doc.get(id))); if (this.tela.selecao.size !== antes) this._agendarPaineis('props'); }
  apagarSelecao() { if (this.tela.selecao.size) this.executar(new ComandoRemover([...this.tela.selecao])); }
  /**
   * Abre o modelo 3D com as peças do que está selecionado em destaque: a posição
   * (P77 → as 18 chapas) ou, sem posição, o conjunto; sem seleção, a posição do
   * desenho de detalhe aberto. O editor recebe `destacar=posicao:P77` na URL.
   */
  verNo3D() {
    if (!this.projeto) { this.aviso('Ver no 3D precisa de um projeto aberto.', 'atencao'); return; }
    const ents = [...this.tela.selecao].map(id => this.doc.get(id)).filter(Boolean);
    // célula de peças fundidas ou conjuntos iguais: "M5 / M7 / M8" são três marcas do modelo
    const separar = (v) => String(v).split(/\s*\/\s*/).filter(Boolean);
    const posicoes = [...new Set(ents.flatMap(e => (e.atributos || {}).posicao ? separar(e.atributos.posicao) : []))];
    const conjuntos = [...new Set(ents.flatMap(e => (e.atributos || {}).conjunto ? separar(e.atributos.conjunto) : []))];
    let alvo = null;
    if (posicoes.length) alvo = 'posicao:' + posicoes.slice(0, 20).join(',');
    else if (conjuntos.length) alvo = 'conjunto:' + conjuntos.slice(0, 20).join(',');
    else {
      const meta = (this.doc.metadados || {}).detalhe_posicao;
      if (meta && meta.marca) alvo = 'posicao:' + meta.marca;
    }
    if (!alvo) { this.aviso('Selecione uma peça do detalhamento (título, contorno ou furo) para vê-la no 3D.', 'atencao'); return; }
    this._sairPara(this.urlDoEditor(`&destacar=${encodeURIComponent(alvo)}`));
  }

  /** As linhas da mesma peça desta (contorno, abas, linha oculta de uma barra no
   *  detalhe): mesma origem no 3D, mesma célula e mesmo grupo de cópia, e **ligadas** —
   *  cada uma com uma ponta sobre outra da peça. Pela proximidade só, duas barras da mesma
   *  origem que se encontram no mesmo nó (a cópia espelhada da ponta da tesoura) eram
   *  pegas juntas. Cota, texto e linha sem origem são só eles. */
  pecaDe(id) {
    const e = this.doc.get(id);
    const a = (e && e.atributos) || {};
    if (!e || !a.origem || e.tipo === 'cota' || e.tipo === 'texto' || e.tipo === 'chamada') return [id];
    const candidatas = [];
    for (const o of this.doc.entidades.values()) {
      const b = o.atributos || {};
      if (b.origem !== a.origem || (b.conjunto || '') !== (a.conjunto || '') || (b.detalhe || '') !== (a.detalhe || '')) continue;
      if ((b.grupo_copia || '') !== (a.grupo_copia || '')) continue;      // a cópia é outra peça
      if (o.tipo === 'cota' || o.tipo === 'texto') continue;
      if (!this.doc.visivel(o)) continue;
      candidatas.push(o);
    }
    if (candidatas.length <= 1) return [id];
    const tol = 1.0;                                     // mm do modelo
    const pontos = new Map(candidatas.map(o => [o.id, pontosDe(o)]));
    const segs = new Map(candidatas.map(o => [o.id, segmentosDe(o)]));
    const encosta = (p, oid) => {
      for (const [s, t] of segs.get(oid)) if (dist(p, maisProximoSeg(p, s, t)) <= tol) return true;
      return false;
    };
    const ligadas = (x, y) => pontos.get(x).some(p => encosta(p, y)) || pontos.get(y).some(p => encosta(p, x));
    const na = new Set([id]), fila = [id];
    while (fila.length) {
      const x = fila.pop();
      for (const o of candidatas) {
        if (na.has(o.id) || !ligadas(x, o.id)) continue;
        na.add(o.id);
        fila.push(o.id);
      }
    }
    return [...na];
  }

  selecionarMesmaPeca() {
    const origens = new Set([...this.tela.selecao].map(id => (this.doc.get(id).atributos || {}).origem).filter(Boolean));
    if (!origens.size) { this.dica('Selecione um objeto que veio do modelo 3D.'); return; }
    this.selecionar([...this.doc.entidades.values()].filter(e => origens.has((e.atributos || {}).origem)).map(e => e.id));
  }

  // ------------------------------------------------------- ferramentas
  _montarFerramentas() {
    const barra = this.el.barra;
    for (const [grupo, rotulo] of GRUPOS) {
      barra.append(el('div', { class: 'grupo-rotulo', texto: rotulo }));
      for (const F of FERRAMENTAS.filter(f => f.grupo === grupo)) {
        this.ferramentas.set(F.id, new F(this));
        const b = el('button', { type: 'button', class: 'ferramenta', 'data-ferramenta': F.id, 'aria-pressed': 'false',
          title: `${F.nome}${F.atalho ? ` (${F.atalho === ' ' ? 'espaço · depois de Esc, espaço volta à ferramenta anterior' : F.atalho.toUpperCase()})` : ''}`, html: F.icone || '' });
        b.addEventListener('click', () => this.ativarFerramenta(F.id));
        barra.append(b);
      }
    }
    this._registrarFerramentasDoLancamento();
  }

  ativarFerramenta(id) {
    const f = this.ferramentas.get(id);
    if (!f) return;
    // ao voltar para "selecionar" (Esc), a ferramenta que estava em uso fica guardada:
    // espaço a chama de novo, sem procurar o botão
    if (this.ferramenta && this.ferramenta.constructor.id !== 'selecionar' && id === 'selecionar') this.ferramentaAnterior = this.ferramenta.constructor.id;
    if (this.ferramenta) this.ferramenta.desativar();
    this.ferramenta = f;
    this.previa([]);
    for (const b of this.el.barra.querySelectorAll('.ferramenta')) b.setAttribute('aria-pressed', String(b.dataset.ferramenta === id));
    f.ativar();
  }

  previa(entidades) { this.tela.previa = entidades || []; this.tela.pedirQuadro(); }
  dica(t) { this.el.dica.textContent = t || ''; }

  /**
   * Enquanto uma operação longa roda no servidor (detalhar, importar IFC), mostra a
   * etapa corrente na linha de dica. Devolve a função que para de acompanhar.
   */
  _acompanharProgresso(prefixo = '') {
    if (!this.projeto) return () => {};
    const url = `/api/projetos/${encodeURIComponent(this.projeto)}/progresso`;
    const timer = setInterval(async () => {
      try {
        const p = await (await fetch(url, { cache: 'no-store' })).json();
        if (p && p.etapa) this.dica(`${prefixo}${p.etapa}${p.ha_s >= 3 ? ` (${Math.round(p.ha_s)} s)` : ''}`);
      } catch { /* servidor ocupado ou fora: tenta de novo no próximo tique */ }
    }, 700);
    return () => clearInterval(timer);
  }

  medida(t) { if (document.activeElement !== this.el.medida) this.el.medida.placeholder = t || 'digite e Enter'; }

  // ------------------------------------------------------------- mouse
  _ligarMouse() {
    const c = this.el.canvas;
    let arrastoVista = null, pressao = null;
    const px = (ev) => { const r = c.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    c.addEventListener('contextmenu', (ev) => ev.preventDefault());
    c.addEventListener('pointerdown', (ev) => {
      c.setPointerCapture(ev.pointerId);
      if (ev.button === 1 || ev.button === 2) { arrastoVista = px(ev); this.el.palco.dataset.arrastando = '1'; return; }
      if (ev.button === 0) {
        pressao = { px: px(ev), movido: false, capturado: false };
        // a ferramenta pode tomar o arrasto para si (a alça de uma cota, na Selecionar)
        if (this.ferramenta && this.ferramenta.onPressionar) {
          const s = this.snap.resolver(pressao.px, { orto: ev.shiftKey });
          pressao.capturado = !!this.ferramenta.onPressionar(s.ponto, { ...evInfo(ev), px: pressao.px });
        }
      }
    });
    c.addEventListener('pointermove', (ev) => {
      const p = px(ev);
      if (arrastoVista) { this.tela.arrastar([p[0] - arrastoVista[0], p[1] - arrastoVista[1]]); arrastoVista = p; return; }
      const s = this.snap.resolver(p, { orto: ev.shiftKey });
      this.tela.cursor = s.ponto; this.tela.snap = s.tipo ? s : null;
      this.el.coord.textContent = `x ${formatarMm(s.ponto[0])}  y ${formatarMm(s.ponto[1])}`;
      if (pressao && !pressao.movido && Math.hypot(p[0] - pressao.px[0], p[1] - pressao.px[1]) > ARRASTO_MIN) pressao.movido = true;
      if (pressao && pressao.capturado) {
        if (this.ferramenta) this.ferramenta.onMover(s.ponto, { ...evInfo(ev), px: p });
        this.tela.pedirQuadro();
        return;
      }
      if (pressao && pressao.movido && this.ferramenta && this.ferramenta.onSoltar !== Ferramenta.prototype.onSoltar) {
        this.tela.retangulo = [pressao.px, p];
      }
      if (!pressao || !pressao.movido) {
        this.tela.realce = this.ferramenta && this.ferramenta.constructor.id === 'selecionar' ? (this.tela.sob(p) || {}).id || null : null;
        if (this.ferramenta) this.ferramenta.onMover(s.ponto, { ...evInfo(ev), px: p });
      }
      this.tela.pedirQuadro();
    });
    c.addEventListener('pointerup', (ev) => {
      const p = px(ev);
      if (arrastoVista) { arrastoVista = null; delete this.el.palco.dataset.arrastando; return; }
      if (!pressao) return;
      const s = this.snap.resolver(p, { orto: ev.shiftKey });
      if (pressao.capturado) {
        // arrastou a alça: solta onde está; só clicou: a alça fica presa ao cursor até o próximo clique
        if (this.ferramenta) this.ferramenta.onPonto(s.ponto, { ...evInfo(ev), px: p, semMover: !pressao.movido });
      } else if (pressao.movido && this.tela.retangulo) {
        this.tela.retangulo = null;
        if (this.ferramenta) this.ferramenta.onSoltar(s.ponto, { ...evInfo(ev), px: p, arrasto: { de: pressao.px, para: p } });
      } else if (this.ferramenta) {
        this.ferramenta.onPonto(s.ponto, { ...evInfo(ev), px: p });
      }
      pressao = null;
      this.tela.pedirQuadro();
    });
    c.addEventListener('wheel', (ev) => { ev.preventDefault(); this.tela.zoom(ev.deltaY < 0 ? 1.15 : 1 / 1.15, px(ev)); }, { passive: false });
    c.addEventListener('dblclick', (ev) => { if (ev.button === 1) this.tela.enquadrar(); });
    c.addEventListener('pointerleave', () => { this.tela.cursor = null; this.tela.snap = null; this.tela.pedirQuadro(); });
  }

  // ----------------------------------------------------------- teclado
  _ligarTeclado() {
    // Ctrl tocado sozinho (apertou e soltou sem outra tecla): no Mover e no Girar liga ou
    // desliga a cópia, como no SketchUp. Ctrl+Z, Ctrl+S… não contam como toque.
    let ctrlSozinho = false;
    document.addEventListener('keydown', (ev) => { ctrlSozinho = ev.key === 'Control' && !ev.repeat ? true : (ev.key === 'Control' ? ctrlSozinho : false); }, true);
    document.addEventListener('keyup', (ev) => {
      if (ev.key !== 'Control') return;
      const tocou = ctrlSozinho;
      ctrlSozinho = false;
      if (tocou && this.ferramenta && this.ferramenta.alternarCopia) this.ferramenta.alternarCopia();
    });
    this.el.canvas.addEventListener('pointerdown', () => { ctrlSozinho = false; }, true);
    document.addEventListener('keydown', (ev) => {
      // com um diálogo aberto, Del, Ctrl+Z e os atalhos são dele, não do desenho por trás
      if (document.querySelector('dialog[open]')) return;
      const alvo = ev.target;
      const emCampo = alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'SELECT' || alvo.tagName === 'TEXTAREA');
      if (emCampo && alvo !== this.el.medida) return;
      if (alvo === this.el.medida) {
        if (ev.key === 'Enter') { ev.preventDefault(); const v = this.el.medida.value.trim(); this.el.medida.value = ''; if (v && this.ferramenta) this.ferramenta.onValor(v); this.el.canvas.focus(); }
        if (ev.key === 'Escape') { this.el.medida.value = ''; this.el.canvas.focus(); }
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); ev.shiftKey ? this.refazer() : this.desfazer(); return; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y') { ev.preventDefault(); this.refazer(); return; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') { ev.preventDefault(); this.salvar(); return; }
      if (ev.key === 'Escape') { if (this.ferramenta) { this.ferramenta.cancelar(); } this.selecionar([]); if (this.ferramenta.constructor.id !== 'selecionar') this.ativarFerramenta('selecionar'); return; }
      if (ev.key === 'F8') { ev.preventDefault(); this.definirOrto(!this.snap.orto); return; }
      if (this.ferramenta && this.ferramenta.onTecla(ev)) { ev.preventDefault(); return; }
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
      if (ev.key === ' ' && this.ferramenta && this.ferramenta.constructor.id === 'selecionar' && this.ferramentaAnterior) {
        ev.preventDefault(); this.ativarFerramenta(this.ferramentaAnterior); return;
      }
      if (ev.key.toLowerCase() === 'z') { this.tela.enquadrar(); return; }
      // número ou sinal digitado no canvas vai para a caixa de medidas
      if (/^[-0-9.,@<]$/.test(ev.key)) { this.el.medida.focus(); return; }
      for (const F of FERRAMENTAS) if (F.atalho && ev.key === F.atalho) { ev.preventDefault(); this.ativarFerramenta(F.id); return; }
    });
  }

  // ------------------------------------------------------------- menus
  _ligarMenus() {
    const acoes = {
      abrir: () => this.dialogoAbrir(),
      novo: () => this.dialogoNovo(),
      'excluir-desenhos': () => this.dialogoExcluir(),
      'aplicar-furos': () => this.aplicarFuros(),
      'aplicar-pecas': () => this.aplicarPecas(),
      'ajustar-tamanho': () => this.ajustarTamanho(),
      'ver-3d': () => this.verNo3D(),
      salvar: () => this.salvar(),
      'exportar-dxf': () => this.exportarDXF(),
      'exportar-pdf': () => this.exportarPDF(),
      'pdf-pranchas': () => this.pdfDasPranchas(),
      'abrir-pasta': () => this.projeto && postar(`/api/projetos/${encodeURIComponent(this.projeto)}/abrir-pasta`, { sub: 'desenhos-2d' }).catch(e => this.aviso(e.message, 'erro')),
      corte: () => this.dialogoCorte(),
      estilos: () => this.dialogoEstilos(),
      detalhar: () => this.dialogoDetalhar(),
      'peca-catalogo': () => this.dialogoPeca(),
      'gerar-3d': () => this.dialogoGerar3D(),
      pranchas: () => this.dialogoPranchas(),
      'importar-dxf': () => $('#arquivo-dxf').click(),
      arquitetonico: () => $('#arquivo-arquitetonico').click(),
      'planta-lancamento': () => this.abrirPlantaDeLancamento(),
      calibrar: () => this.ativarFerramenta('calibrar'),
      malha: () => this.dialogoMalha(),
      'gravar-eixos': () => this.gravarEixos(),
      'lancar-3d': () => this.lancarNo3D(),
      'projeto-2d': () => $('#arquivo-projeto-2d').click(),
      reconhecer: () => this.reconhecerPecas(),
      desfazer: () => this.desfazer(), refazer: () => this.refazer(),
      'selecionar-tudo': () => this.selecionar([...this.doc.entidades.keys()].filter(id => this.doc.visivel(this.doc.get(id)))),
      apagar: () => this.apagarSelecao(),
      materiais: async () => {
        if (!this.projeto) { this.aviso('A lista de materiais precisa de um projeto aberto.', 'atencao'); return; }
        await this._sairPara(`/materiais?projeto=${encodeURIComponent(this.projeto)}`);
      },
      'selecionar-peca': () => this.selecionarMesmaPeca(),
      'zoom-extensao': () => this.tela.enquadrar(),
      'zoom-selecao': () => { const c = this.doc.caixa(this.tela.selecao); if (c) this.tela.enquadrar(c, 0.2); },
      grade: () => { this.tela.grade = !this.tela.grade; this.tela.pedirQuadro(); },
      orto: () => this.definirOrto(!this.snap.orto),
    };
    document.addEventListener('click', (ev) => {
      const botaoMenu = ev.target.closest('.menu-botao');
      if (botaoMenu) { const m = botaoMenu.parentElement; const aberto = m.classList.contains('aberto'); this._fecharMenus(); if (!aberto) { m.classList.add('aberto'); if (m.dataset.menu === 'desenho') this._listarDesenhosNoMenu(); } return; }
      const excluir = ev.target.closest('[data-excluir]');
      if (excluir) { ev.stopPropagation(); this._fecharMenus(); this._excluirUmDesenho(excluir.dataset.excluir, excluir.dataset.titulo); return; }
      const salvo = ev.target.closest('[data-desenho]');
      if (salvo) { this._fecharMenus(); this.abrirDesenho(salvo.dataset.desenho); return; }
      const item = ev.target.closest('[data-acao], [data-vista]');
      if (item) {
        this._fecharMenus();
        if (item.dataset.vista) this.inserirVista({ padrao: item.dataset.vista }, item.textContent.trim());
        else if (acoes[item.dataset.acao]) acoes[item.dataset.acao]();
        return;
      }
      if (!ev.target.closest('.menu')) this._fecharMenus();
    });
    $('#btn-salvar').addEventListener('click', () => this.salvar());
    $('#btn-voltar').addEventListener('click', (ev) => { ev.preventDefault(); this.voltar(false); });
    $('#btn-fechar').addEventListener('click', () => this.voltar(true));
    $('#btn-dxf').addEventListener('click', () => this.exportarDXF());
    $('#arquivo-dxf').addEventListener('change', () => {
      const f = $('#arquivo-dxf').files && $('#arquivo-dxf').files[0];
      $('#arquivo-dxf').value = '';
      if (f && /\.pdf$/i.test(f.name)) this.importarPDF(f); else this.importarDXF(f);
    });
    $('#arquivo-arquitetonico').addEventListener('change', () => { const f = $('#arquivo-arquitetonico').files && $('#arquivo-arquitetonico').files[0]; $('#arquivo-arquitetonico').value = ''; this.importarArquitetonico(f); });
    $('#arquivo-projeto-2d').addEventListener('change', () => { const f = $('#arquivo-projeto-2d').files && $('#arquivo-projeto-2d').files[0]; $('#arquivo-projeto-2d').value = ''; this.projetoRecebido(f); });
    $('#btn-tema').addEventListener('click', () => this._alternarTema());
    this.el.nome.addEventListener('change', () => { this.doc.nome = this.el.nome.value.trim() || 'Desenho'; document.title = `${this.doc.nome} — Desenho 2D`; this._agendarAutosave(); });
    this.el.escala.addEventListener('change', () => { this.doc.escala = parseFloat(this.el.escala.value) || 20; this.doc.notificar([], 'aparencia'); this.dica(`Escala 1:${this.doc.escala}: textos, cotas e hachuras redimensionados.`); });
  }
  _fecharMenus() { for (const m of document.querySelectorAll('.menu.aberto')) m.classList.remove('aberto'); }
  _atualizarMenuEditar() {
    const m = $('#menu-editar');
    m.querySelector('[data-acao="desfazer"]').disabled = !this.pilha.podeDesfazer;
    m.querySelector('[data-acao="refazer"]').disabled = !this.pilha.podeRefazer;
  }
  _refletirEscala() {
    const s = this.el.escala;
    if (![...s.options].some(o => parseFloat(o.value) === this.doc.escala)) s.append(el('option', { value: String(this.doc.escala), texto: String(this.doc.escala) }));
    s.value = String(this.doc.escala);
  }

  // ----------------------------------------------------------- painéis
  /** DXF escolhido no seletor: pergunta unidade e posição, manda ao servidor, insere como comando. */
  async importarDXF(arquivo) {
    if (!arquivo) return;
    if (!this.projeto) { this.aviso('Importar DXF precisa de um projeto aberto.', 'atencao'); return; }
    const b64 = await base64DoArquivo(arquivo);
    const unidade = el('select', {}, ...[['auto', 'pelo arquivo ($INSUNITS), senão mm'], ['1', 'milímetro'], ['10', 'centímetro'], ['1000', 'metro'], ['25.4', 'polegada']]
      .map(([v, t]) => el('option', { value: v, texto: t })));
    const x = el('input', { type: 'number', step: 'any', value: '0' });
    const y = el('input', { type: 'number', step: 'any', value: '0' });
    const prefixo = el('input', { type: 'text', value: '', placeholder: 'ex.: DXF-' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `"${arquivo.name}" (${numero(arquivo.size / 1024, 0)} kB). O desenho vem para a escala deste (1:${this.doc.escala}): a altura dos textos do arquivo vira altura de papel dividida pela escala. Cotas do DXF entram como linhas e textos, como o CAD de origem as desenhou. DWG não é lido: salve como DXF no CAD de origem.` }),
      el('label', {}, 'Unidade do arquivo', unidade),
      el('label', {}, 'Inserir em X (mm)', x), el('label', {}, 'Inserir em Y (mm)', y),
      el('label', {}, 'Prefixo para as camadas do arquivo (opcional)', prefixo));
    if (await this.dialogo({ titulo: 'Importar DXF', corpo, ok: 'Importar' }) !== 'ok') return;
    this.dica('Lendo o DXF…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/importar-dxf`, {
        conteudo_b64: b64, escala: this.doc.escala, fator: unidade.value === 'auto' ? null : parseFloat(unidade.value),
        deslocamento: [parseFloat(x.value) || 0, parseFloat(y.value) || 0], prefixo_camada: prefixo.value,
      });
      for (const [nome, c] of Object.entries(r.camadas || {})) if (!this.doc.camadas.has(nome)) this.doc.camadas.set(nome, { nome, cor: c.cor, visivel: true, bloqueada: false, tipo_linha: c.tipo_linha || 'CONTINUOUS', espessura: c.espessura || 0.25 });
      const ents = (r.entidades || []).map(e => ({ ...e, id: undefined }));
      if (!ents.length) { this.aviso('O DXF não trouxe nada que o CAD leia.', 'atencao'); return; }
      const novas = ents.map(e => criar(e));
      this.executar(new ComandoAdicionar(novas, `Importar DXF (${ents.length})`));
      this.selecionar(novas.map(e => e.id));
      this.tela.enquadrar();
      const ig = Object.entries(r.resumo.por_tipo || {}).filter(([k]) => k.startsWith('ignorado')).map(([k, v]) => `${k.slice(9)} ×${v}`);
      this.aviso(`DXF importado: ${numero(r.resumo.entidades)} objetos, ${(r.resumo.camadas_novas || []).length} camada(s) nova(s), fator ${r.resumo.fator} mm/unidade.` + (ig.length ? ` Fora: ${ig.join(', ')}.` : ''), 'info', 12000);
      this.dica('DXF importado; Ctrl+Z desfaz.');
    } catch (e) { this.aviso(`Não foi possível importar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** PDF vetorial escolhido no seletor: entra em mm de papel (a escala de cada vista o
   *  Reconhecer descobre pelas cotas). */
  async importarPDF(arquivo) {
    if (!arquivo) return;
    if (!this.projeto) { this.aviso('Importar PDF precisa de um projeto aberto.', 'atencao'); return; }
    const x = el('input', { type: 'number', step: 'any', value: '0' });
    const y = el('input', { type: 'number', step: 'any', value: '0' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `"${arquivo.name}" (${numero(arquivo.size / 1024, 0)} kB). O PDF exportado do CAD traz as linhas e os textos de verdade; entram em milímetro de papel, uma página ao lado da outra. PDF digitalizado (imagem) não tem o que ler. Depois use "Reconhecer peças pelos perfis escritos" para achar as barras e a escala de cada vista.` }),
      el('label', {}, 'Inserir em X (mm)', x), el('label', {}, 'Inserir em Y (mm)', y));
    if (await this.dialogo({ titulo: 'Importar PDF', corpo, ok: 'Importar' }) !== 'ok') return;
    this.dica('Lendo o PDF…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/importar-pdf`, {
        conteudo_b64: await base64DoArquivo(arquivo), escala: this.doc.escala,
        deslocamento: [parseFloat(x.value) || 0, parseFloat(y.value) || 0],
      });
      for (const [nome, c] of Object.entries(r.camadas || {})) if (!this.doc.camadas.has(nome)) this.doc.camadas.set(nome, { nome, cor: c.cor, visivel: true, bloqueada: false, tipo_linha: c.tipo_linha || 'CONTINUOUS', espessura: c.espessura || 0.25 });
      const ents = (r.entidades || []).map(e => ({ ...e, id: undefined }));
      for (const a of r.resumo.avisos || []) this.aviso(a, 'atencao', 0);
      if (!ents.length) { this.aviso('O PDF não trouxe linhas nem textos que o CAD leia.', 'atencao'); return; }
      const novas = ents.map(e => criar(e));
      this.executar(new ComandoAdicionar(novas, `Importar PDF (${ents.length})`));
      this.selecionar(novas.map(e => e.id));
      this.tela.enquadrar();
      this.aviso(`PDF importado: ${numero(r.resumo.entidades)} objetos em ${(r.resumo.paginas || []).length} página(s), em mm de papel.`, 'info', 12000);
      this.dica('PDF importado; Ctrl+Z desfaz.');
    } catch (e) { this.aviso(`Não foi possível importar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** Liga os perfis escritos às linhas e põe as peças na camada PEÇAS RECONHECIDAS. */
  async reconhecerPecas() {
    if (!this.projeto) { this.aviso('Reconhecer precisa de um projeto aberto.', 'atencao'); return; }
    if (!this.doc.tamanho) { this.aviso('O desenho está vazio: importe o DXF ou o PDF do projeto antes.', 'atencao'); return; }
    const parar = this._acompanharProgresso('Reconhecendo: ');
    let r;
    try {
      r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho || 'desenho')}/reconhecer`, { desenho: this.doc.paraJSON() });
    } catch (e) { parar(); this.aviso(`Não foi possível reconhecer: ${e.message}`, 'erro', 0); return; }
    parar();
    for (const [nome, c] of Object.entries(r.camadas || {})) if (!this.doc.camadas.has(nome)) this.doc.camadas.set(nome, { nome, cor: c.cor, visivel: true, bloqueada: false, tipo_linha: c.tipo_linha || 'CONTINUOUS', espessura: c.espessura || 0.5 });
    const novas = (r.entidades || []).map(e => criar(e));
    const cmds = [];
    const remover = (r.remover || []).filter(id => this.doc.get(id));
    if (remover.length) cmds.push(new ComandoRemover(remover));
    if (novas.length) cmds.push(new ComandoAdicionar(novas));
    if (cmds.length) this.executar(new ComandoComposto(cmds, `Reconhecer peças (${novas.length})`));
    this.doc.metadados = { ...(this.doc.metadados || {}), reconhecimento: r.reconhecimento };
    this.tela.pedirQuadro();
    const res = r.resumo || {};
    const lista = el('ul', { class: 'lista-avisos' });
    for (const v of r.vistas || []) {
      lista.append(el('li', { texto: `${v.titulo || 'Vista ' + v.id} — ${tipoDeVista(v.tipo)}, ${v.barras} barra(s), escala ${textoEscala(v)}` + (v.eixos && v.eixos.length ? `, eixos ${v.eixos.map(e => e.rotulo).join(' ')}` : '') }));
    }
    const perfis = Object.entries(res.perfis || {}).sort((a, b) => b[1] - a[1]).map(([n, q]) => `${q}× ${n}`).join(' · ');
    const semPerfil = Object.entries(res.sem_perfil || {}).sort((a, b) => b[1] - a[1]).map(([p, q]) => `${q} ${p}`).join(', ');
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `${res.barras || 0} barra(s) reconhecida(s) em ${res.vistas || 0} vista(s)` + (res.a_conferir ? `; ${res.a_conferir} herdaram o perfil da camada e estão em PEÇAS A CONFERIR (rosa)` : '') + '. As peças estão em linhas novas por cima do desenho — apague, desenhe ou mude a peça (Peça do catálogo…) do que estiver errado antes de gerar o 3D.' }),
      lista,
      el('div', { class: 'explica', texto: perfis || '' }),
      ...(semPerfil ? [el('div', { class: 'explica', texto: `Sem perfil escrito, reconhecidas só pela forma (${semPerfil}): o perfil de cada papel é escolhido ao gerar o modelo 3D.` })] : []),
      ...(r.textos_sem_linha || []).length ? [el('div', { class: 'explica', texto: `Perfis escritos sem linha achada (${r.textos_sem_linha.length}): ` + r.textos_sem_linha.slice(0, 12).map(t => t.texto).join(' · ') })] : [],
      ...(r.avisos || []).map(a => el('div', { class: 'explica atencao', texto: a })));
    const acao = await this.dialogo({ titulo: 'Peças reconhecidas', corpo, ok: novas.length ? 'Gerar o modelo 3D…' : 'OK' });
    if (acao === 'ok' && novas.length) this.dialogoGerar3D();
  }

  /** Projeto recebido: DXF/PDF → desenho + peças + modelo 3D + IFC, numa ida ao servidor. */
  async projetoRecebido(arquivo) {
    if (!arquivo) return;
    if (!this.projeto) { this.aviso('Abra ou crie um projeto antes (o modelo 3D e o IFC ficam nele).', 'atencao'); return; }
    const modo = el('select');
    modo.append(el('option', { value: 'substituir', texto: 'substituir o modelo 3D do projeto (o atual vai para o histórico)' }));
    modo.append(el('option', { value: 'acrescentar', texto: 'acrescentar ao modelo 3D do projeto' }));
    const ifc = el('input', { type: 'checkbox', checked: 'checked' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `"${arquivo.name}" (${numero(arquivo.size / 1024, 0)} kB). O sistema lê as vistas (planta, tesoura, pórtico, fachada), a escala de cada uma pelas cotas, os eixos e os perfis escritos junto das barras; monta as tesouras nos eixos da planta e sobe as terças para a cobertura. O desenho fica gravado no projeto, com as peças numa camada própria, para conferir e corrigir.` }),
      el('label', {}, 'Modelo 3D', modo),
      el('label', { class: 'linha' }, ifc, ' Gravar o IFC do modelo gerado'));
    if (await this.dialogo({ titulo: 'Projeto recebido → modelo 3D', corpo, ok: 'Ler o projeto' }) !== 'ok') return;
    const parar = this._acompanharProgresso('Projeto recebido: ');
    let r;
    try {
      r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/projeto-2d`, {
        arquivo: arquivo.name, conteudo_b64: await base64DoArquivo(arquivo), modo: modo.value, ifc: ifc.checked,
      });
    } catch (e) { parar(); this.aviso(`Não foi possível ler o projeto: ${e.message}`, 'erro', 0); this.dica(''); return; }
    parar();
    this.dica('');
    await this.abrirDesenho(r.desenho);
    const res = r.resumo || {};
    const g = r.gerado || {};
    const lista = el('ul', { class: 'lista-avisos' });
    for (const v of r.vistas || []) lista.append(el('li', { texto: `${v.titulo || 'Vista ' + v.id} — ${tipoDeVista(v.tipo)}, ${v.barras} barra(s), escala ${textoEscala(v)}` }));
    const papeis = Object.entries(res.papeis || {}).map(([n, q]) => `${q} ${n}`).join(', ');
    const itens = [
      el('div', { class: 'explica', texto: r.modelo
        ? `Modelo 3D: ${numero(g.barras || 0)} barra(s), ${g.posicoes || 0} posição(ões), ${g.conjuntos || 0} conjunto(s), ${numero(g.peso_kg || 0)} kg. No desenho: ${res.barras || 0} peça(s) reconhecida(s) (${papeis}).`
        : 'Nenhuma peça foi reconhecida: o modelo 3D não foi gerado. Veja os avisos abaixo.' }),
      lista,
    ];
    if (r.ifc) itens.push(el('div', { class: 'explica' }, 'IFC: ', el('a', { href: r.ifc.url, download: r.ifc.nome, texto: `${r.ifc.nome} (${numero(r.ifc.tamanho_kb, 0)} kB)` })));
    if (res.a_conferir) itens.push(el('div', { class: 'explica atencao', texto: `${res.a_conferir} peça(s) herdaram o perfil da camada (sem texto junto): estão em PEÇAS A CONFERIR, em rosa.` }));
    const semPerfil = Object.entries(r.sem_perfil || {});
    if (semPerfil.length) {
      const pp = r.perfis_padrao || {};
      itens.push(el('div', { class: 'explica atencao', texto: `${semPerfil.reduce((s, [, q]) => s + q, 0)} peça(s) reconhecida(s) só pela forma, sem perfil escrito, entraram no 3D com o perfil padrão de cada papel: ` + semPerfil.map(([p, q]) => `${q} ${p} → ${pp[p] || '?'}`).join('; ') + '. Para trocar, no CAD use Vistas do modelo → Gerar modelo 3D do desenho… (um perfil por papel) ou, no 3D, Trocar perfil.' }));
    }
    // o aviso do servidor sobre as peças sem perfil já foi dito acima, com os perfis usados
    for (const a of r.avisos || []) if (!(semPerfil.length && /só pela forma/.test(a))) itens.push(el('div', { class: 'explica atencao', texto: a }));
    const acao = await this.dialogo({ titulo: 'Projeto recebido', corpo: el('div', {}, ...itens), ok: r.modelo ? 'Abrir o modelo 3D' : 'OK' });
    if (acao === 'ok' && r.modelo) location.href = this.urlDoEditor();
  }

  /** Várias vistas reconhecidas: cada uma no seu lugar (a montagem sugerida, editável). */
  async _dialogoGerar3DVistas(montagens) {
    const num = (v, t, larg = '7em') => el('input', { type: 'number', step: 'any', value: String(v), title: t || '', style: `width:${larg}` });
    const linhas = [];
    const tabela = el('div', { class: 'montagens' });
    const vec = (v) => (v || []).map(x => Math.round(x * 1000) / 1000).join('; ');
    const lerVec = (s) => s.split(/[;\s]+/).filter(Boolean).map(x => parseFloat(x.replace(',', '.')) || 0);
    for (const m of montagens) {
      const usar = el('input', { type: 'checkbox', ...(m.usar !== false ? { checked: 'checked' } : {}) });
      const fator = num(m.fator, 'mm do modelo por unidade do desenho (PDF: o denominador da escala, 50 para 1:50)');
      const u = el('input', { type: 'text', value: vec(m.u), title: 'Para onde vai o X do desenho no modelo (vetor x; y; z)', style: 'width:9em' });
      const v = el('input', { type: 'text', value: vec(m.v), title: 'Para onde vai o Y do desenho no modelo (vetor x; y; z)', style: 'width:9em' });
      const origens = el('textarea', { rows: String(Math.min(4, Math.max(1, (m.origens || []).length))), title: 'Onde o ponto base da vista cai no modelo, uma cópia por linha: x; y; z (mm)', style: 'width:16em' });
      origens.value = (m.origens || []).map(o => o.map(x => Math.round(x)).join('; ')).join('\n');
      const cob = el('input', { type: 'checkbox', ...(m.cobertura ? { checked: 'checked' } : {}), title: 'A altura de cada ponto sai do banzo superior da tesoura (planta de cobertura)' });
      linhas.push({ m, usar, fator, u, v, origens, cob });
      tabela.append(el('fieldset', { class: 'montagem' },
        el('legend', {}, usar, ` ${m.titulo || 'Vista ' + m.vista} (${tipoDeVista(m.tipo)})`),
        el('div', { class: 'campos' },
          el('label', { texto: 'Escala (fator)' }), fator,
          el('label', { texto: 'X do desenho →' }), u,
          el('label', { texto: 'Y do desenho →' }), v,
          el('label', { texto: `Origens (${(m.origens || []).length})` }), origens,
          el('label', { texto: 'Sobe até a cobertura' }), cob)));
    }
    const modo = el('select');
    modo.append(el('option', { value: 'substituir', texto: 'substituir o modelo do projeto' }));
    modo.append(el('option', { value: 'acrescentar', texto: 'acrescentar ao modelo do projeto' }));
    const ifc = el('input', { type: 'checkbox', checked: 'checked' });
    // peças reconhecidas só pela forma (sem perfil escrito): um perfil por papel
    const rec = (this.doc.metadados || {}).reconhecimento || {};
    const semPerfil = Object.entries(rec.sem_perfil || {}).sort((a, b) => b[1] - a[1]);
    const perfisEscolhidos = rec.perfis || {};
    const camposPerfil = [];
    let blocoPerfis = null;
    if (semPerfil.length) {
      const grade = el('div', { class: 'campos' });
      const sugestoes = el('datalist', { id: 'perfis-por-papel' });
      grade.append(sugestoes);
      for (const [papel, q] of semPerfil) {
        const campo = el('input', { type: 'text', value: perfisEscolhidos[papel] || (rec.perfis_padrao || {})[papel] || '', list: 'perfis-por-papel', spellcheck: 'false', style: 'width:16em', title: 'Nome do perfil como no catálogo (W 250 x 32,7; Ue 150x60x20x2,00; U 100x50#12; L 2"x1/8"; Barra redonda 1/2")' });
        camposPerfil.push({ papel, campo });
        grade.append(el('label', { texto: `${papel} (${q})` }), campo);
      }
      fetch('/api/catalogo/pecas?q=x&limite=400').then(r => r.json()).then(d => {
        for (const it of (d.itens || [])) sugestoes.append(el('option', { value: it.nome }));
      }).catch(() => {});
      blocoPerfis = el('fieldset', { class: 'montagem' },
        el('legend', { texto: 'Perfil das peças reconhecidas só pela forma' }),
        el('div', { class: 'explica', texto: 'O desenho não tem o perfil escrito nessas peças: diga o perfil de cada papel (nome do catálogo). Dá para trocar depois, peça a peça, no 3D.' }),
        grade);
    }
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Cada vista reconhecida entra no espaço por uma montagem: o ponto base da vista vai para cada origem (uma cópia por linha — as tesouras de todos os eixos saem de uma vista só), o X e o Y do desenho seguem os vetores. A montagem abaixo foi sugerida pelos eixos da planta; confira antes de gerar.' }),
      tabela,
      ...(blocoPerfis ? [blocoPerfis] : []),
      el('div', { class: 'campos' }, el('label', { texto: 'Modelo' }), modo),
      el('label', { class: 'linha' }, ifc, ' Gravar também o IFC'));
    if (await this.dialogo({ titulo: 'Gerar modelo 3D das vistas', corpo, ok: 'Gerar' }) !== 'ok') return;
    const novas = linhas.map(({ m, usar, fator, u, v, origens, cob }) => ({
      ...m, usar: usar.checked, fator: parseFloat(fator.value) || 1, u: lerVec(u.value), v: lerVec(v.value), cobertura: cob.checked,
      origens: origens.value.split('\n').map(l => lerVec(l)).filter(o => o.length).map(o => [o[0] || 0, o[1] || 0, o[2] || 0]),
    }));
    const perfis = {};
    for (const { papel, campo } of camposPerfil) if (campo.value.trim()) perfis[papel] = campo.value.trim();
    this.doc.metadados = { ...(this.doc.metadados || {}), reconhecimento: { ...(this.doc.metadados.reconhecimento || {}), montagens: novas, perfis } };
    await this.salvar({ avisar: false });
    this.dica('Gerando o modelo 3D…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/gerar-3d`, {
        montagens: novas, modo: modo.value, ifc: ifc.checked, perfis,
      });
      const g = r.gerado || {};
      const itens = [el('div', { class: 'explica', texto: `Modelo 3D gerado: ${numero(g.barras || 0)} barra(s), ${g.posicoes || 0} posição(ões), ${g.conjuntos || 0} conjunto(s), ${numero(g.peso_kg || 0)} kg. O modelo anterior foi guardado no histórico.` })];
      if (r.ifc) itens.push(el('div', { class: 'explica' }, 'IFC: ', el('a', { href: r.ifc.url, download: r.ifc.nome, texto: `${r.ifc.nome} (${numero(r.ifc.tamanho_kb, 0)} kB)` })));
      this.dica('Modelo 3D gerado.');
      if (await this.dialogo({ titulo: 'Modelo 3D gerado', corpo: el('div', {}, ...itens), ok: 'Abrir o modelo 3D' }) === 'ok') location.href = this.urlDoEditor();
    } catch (e) { this.aviso(`Não foi possível gerar o modelo: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  _ligarPaineis() {
    for (const cab of document.querySelectorAll('.painel .cabecalho')) cab.addEventListener('click', () => cab.closest('.painel').classList.toggle('fechado'));
  }
  _agendarPaineis(...quais) {
    for (const q of quais) if (q) this._paineisPendentes.add(q);
    if (this._rafPaineis) return;
    this._rafPaineis = requestAnimationFrame(() => {
      this._rafPaineis = null;
      const p = this._paineisPendentes; this._paineisPendentes = new Set();
      if (p.has('props')) this._painelProps();
      if (p.has('camadas')) this._painelCamadas();
      if (p.has('snap')) this._painelSnap();
      if (p.has('vistas')) this._painelVistas();
    });
  }

  _painelProps() {
    const raiz = this.el.props; raiz.replaceChildren();
    const ids = [...this.tela.selecao];
    if (!ids.length) {
      const g = el('div', { class: 'props' });
      g.append(el('label', { texto: 'Camada ativa' }), this._seletorCamada(this.camadaAtiva, (v) => { this.camadaAtiva = v; }));
      const alt = el('input', { type: 'number', step: '0.5', min: '1', value: this.alturaTexto, title: 'Altura de texto e cota, em mm no papel' });
      alt.addEventListener('change', () => { this.alturaTexto = parseFloat(alt.value) || 2.5; });
      g.append(el('label', { texto: 'Texto (mm)' }), alt);
      g.append(el('div', { class: 'origem', texto: `${numero(this.doc.tamanho)} objetos no desenho · nada selecionado` }));
      raiz.append(g); return;
    }
    const ents = ids.map(id => this.doc.get(id));
    const g = el('div', { class: 'props' });
    const tipos = new Set(ents.map(e => e.tipo));
    this._linhaPeca(g, ents);
    g.append(el('label', { texto: 'Seleção' }), el('div', { texto: ids.length === 1 ? ents[0].tipo : `${ids.length} objetos (${[...tipos].join(', ')})` }));
    // comprimento do traço (polilinha, linha, arco, círculo); com vários, a soma
    const compr = (e) => {
      if (e.tipo === 'linha') return Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1]);
      if (e.tipo === 'polilinha') {
        const v = e.vertices || []; let s = 0;
        for (let i = 1; i < v.length; i++) s += Math.hypot(v[i][0] - v[i - 1][0], v[i][1] - v[i - 1][1]);
        if (e.fechada && v.length > 2) s += Math.hypot(v[0][0] - v[v.length - 1][0], v[0][1] - v[v.length - 1][1]);
        return s;
      }
      if (e.tipo === 'arco') { const d = (((e.fim - e.inicio) % 360) + 360) % 360 || 360; return e.raio * d * Math.PI / 180; }
      if (e.tipo === 'circulo') return 2 * Math.PI * e.raio;
      return null;
    };
    const comps = ents.map(compr).filter(v => v !== null);
    if (comps.length && !(ids.length === 1 && ents[0].tipo === 'linha')) {
      const total = comps.reduce((s, v) => s + v, 0);
      g.append(el('label', { texto: comps.length > 1 ? 'Comprimento (soma)' : 'Comprimento' }), el('div', { texto: formatarMm(total) + ' mm' }));
    }
    const camadas = new Set(ents.map(e => e.camada));
    g.append(el('label', { texto: 'Camada' }), this._seletorCamada(camadas.size === 1 ? ents[0].camada : '', (v) => {
      const m = {}; for (const id of ids) m[id] = { camada: v }; this.executar(new ComandoAlterar(m, 'Trocar camada'));
    }, camadas.size !== 1));
    if (ids.length === 1) {
      const e = ents[0];
      const campo = (rotulo, chave, tipo = 'text', extra = {}) => {
        const i = el('input', { type: tipo, value: e[chave] ?? '', ...extra });
        i.addEventListener('change', () => { const v = tipo === 'number' ? parseFloat(i.value.replace(',', '.')) : i.value; if (tipo === 'number' && !isFinite(v)) return; this.executar(new ComandoAlterar({ [e.id]: { [chave]: v } }, `Alterar ${rotulo}`)); });
        g.append(el('label', { texto: rotulo }), i);
      };
      if (e.tipo === 'texto' || e.tipo === 'chamada') { campo('Texto', 'texto'); campo('Altura (mm)', 'altura', 'number', { step: '0.5' }); }
      if (e.tipo === 'texto') campo('Ângulo', 'angulo', 'number', { step: '15' });
      if (e.tipo === 'cota') {
        g.append(el('label', { texto: 'Valor' }), el('div', { texto: formatarMm(valorCota(e)) + ' mm' }));
        campo('Texto (vazio = medida)', 'texto'); campo('Deslocamento', 'deslocamento', 'number', { step: '1' });
        const modo = el('select', {}, ...['alinhada', 'h', 'v'].map(m => el('option', { value: m, texto: m, selected: e.modo === m ? 'selected' : undefined })));
        modo.addEventListener('change', () => this.executar(new ComandoAlterar({ [e.id]: { modo: modo.value } }, 'Modo da cota')));
        g.append(el('label', { texto: 'Modo' }), modo);
      }
      if (e.tipo === 'circulo' || e.tipo === 'arco') campo('Raio', 'raio', 'number', { step: '1' });
      if (e.tipo === 'linha') g.append(el('label', { texto: 'Comprimento' }), el('div', { texto: formatarMm(Math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])) + ' mm' }));
      if (e.tipo === 'hachura') {
        const pad = el('select', {}, ...['aco', 'concreto', 'solido'].map(m => el('option', { value: m, texto: m, selected: e.padrao === m ? 'selected' : undefined })));
        pad.addEventListener('change', () => this.executar(new ComandoAlterar({ [e.id]: { padrao: pad.value } }, 'Padrão da hachura')));
        g.append(el('label', { texto: 'Padrão' }), pad); campo('Espaçamento', 'espacamento', 'number', { step: '0.5' }); campo('Ângulo', 'angulo', 'number', { step: '15' });
      }
      const a = e.atributos || {};
      if (a.origem) {
        g.append(el('div', { class: 'origem' }, el('b', { texto: 'Do modelo 3D: ' }), [a.posicao && `posição ${a.posicao}`, a.conjunto && `conjunto ${a.conjunto}`, a.perfil, a.nome].filter(Boolean).join(' · ')));
      }
    } else {
      const a = ents.map(e => (e.atributos || {}).posicao).filter(Boolean);
      if (a.length) g.append(el('div', { class: 'origem' }, el('b', { texto: 'Peças: ' }), [...new Set(a)].slice(0, 12).join(', ')));
    }
    const botoes = el('div', { class: 'botoes' },
      el('button', { type: 'button', texto: 'Zoom', onclick: () => { const c = this.doc.caixa(this.tela.selecao); if (c) this.tela.enquadrar(c, 0.25); } }),
      el('button', { type: 'button', texto: 'Mesma peça', onclick: () => this.selecionarMesmaPeca() }),
      el('button', { type: 'button', texto: 'Ver no 3D', title: 'Abre o modelo 3D com as peças desta posição (ou conjunto) selecionadas e enquadradas', onclick: () => this.verNo3D() }),
      el('button', { type: 'button', texto: 'Apagar', onclick: () => this.apagarSelecao() }));
    g.append(botoes);
    raiz.append(g);
  }

  _seletorCamada(atual, aoMudar, varios = false) {
    const s = el('select', {}, varios ? el('option', { value: '', texto: '— várias —' }) : null,
      ...[...this.doc.camadas.keys()].map(n => el('option', { value: n, texto: n, selected: n === atual ? 'selected' : undefined })));
    s.addEventListener('change', () => { if (s.value) aoMudar(s.value); });
    return s;
  }

  _painelCamadas() {
    const raiz = this.el.camadas; raiz.replaceChildren();
    const cont = new Map();
    for (const e of this.doc.entidades.values()) cont.set(e.camada, (cont.get(e.camada) || 0) + 1);
    const lista = el('div', { class: 'lista-linhas' });
    const olho = (v) => v ? '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3" opacity=".45"/><path d="M3 13L13 3" stroke="currentColor" stroke-width="1.3"/></svg>';
    for (const [nome, c] of this.doc.camadas) {
      const linha = el('div', { class: 'linha', title: 'Clique: camada ativa · duplo clique: selecionar o que está nela' });
      if (c.visivel === false) linha.dataset.oculta = '';
      if (nome === this.camadaAtiva) linha.dataset.ativa = '';
      const vis = el('button', { type: 'button', class: 'alternador', html: olho(c.visivel !== false), title: c.visivel === false ? 'Mostrar' : 'Ocultar',
        onclick: () => this.executar(new ComandoAparencia(nome, { visivel: c.visivel === false })) });
      const cor = el('input', { type: 'color', value: c.cor, title: 'Cor da camada' });
      cor.addEventListener('change', () => this.executar(new ComandoAparencia(nome, { cor: cor.value })));
      linha.addEventListener('click', (ev) => { if (ev.target.closest('button, input')) return; this.camadaAtiva = nome; this._agendarPaineis('camadas', 'props'); this.dica(`Camada ativa: ${nome}`); });
      linha.addEventListener('dblclick', (ev) => { if (ev.target.closest('button, input')) return; this.selecionar([...this.doc.entidades.values()].filter(e => e.camada === nome).map(e => e.id)); });
      linha.append(vis, cor, el('span', { class: 'nome', texto: nome }), el('span', { class: 'contagem', texto: numero(cont.get(nome) || 0) }));
      lista.append(linha);
    }
    raiz.append(lista);
    const acoes = el('div', { class: 'acoes-painel' });
    acoes.append(el('button', { type: 'button', texto: '+ Nova camada', onclick: async () => {
      const n = await this.perguntar('Nova camada', 'Nome', ''); if (!n) return;
      const nome = n.trim().toUpperCase(); if (this.doc.camadas.has(nome)) { this.camadaAtiva = nome; return; }
      this.doc.camadas.set(nome, { nome, cor: '#5b7db1', visivel: true, bloqueada: false, tipo_linha: 'CONTINUOUS', espessura: 0.25 });
      this.camadaAtiva = nome; this.doc.notificar([], 'aparencia');
    } }));
    acoes.append(el('button', { type: 'button', texto: 'Mostrar todas', onclick: () => { for (const [n, c] of this.doc.camadas) if (c.visivel === false) this.executar(new ComandoAparencia(n, { visivel: true })); } }));
    raiz.append(acoes);
  }

  _painelSnap() {
    const raiz = this.el.snap; raiz.replaceChildren();
    const g = el('div', { class: 'snaps' });
    const rot = { extremidade: 'Extremidade', meio: 'Meio', centro: 'Centro', interseccao: 'Interseção', perpendicular: 'Perpendicular', sobre: 'Sobre a linha', grade: 'Grade' };
    for (const [k, r] of Object.entries(rot)) {
      const c = el('input', { type: 'checkbox', checked: this.snap.ativos[k] ? 'checked' : undefined });
      c.addEventListener('change', () => { this.snap.ativos[k] = c.checked; });
      g.append(el('label', {}, c, r));
    }
    const orto = el('input', { type: 'checkbox', checked: this.snap.orto ? 'checked' : undefined });
    orto.addEventListener('change', () => this.definirOrto(orto.checked));
    g.append(el('label', { title: 'Só horizontal e vertical ao desenhar e mover (F8 alterna; Shift segurado liga na hora)' }, orto, 'Orto (F8)'));
    raiz.append(g);
  }

  /** Orto fixo: linhas, movimentos e cópias só na horizontal/vertical. Fica gravado para os próximos desenhos. */
  definirOrto(ligado) {
    this.snap.orto = !!ligado;
    try { localStorage.setItem('cad.orto', this.snap.orto ? '1' : '0'); } catch { /* sem armazenamento */ }
    this.dica(`Orto ${this.snap.orto ? 'ligado: só horizontal e vertical (F8 desliga)' : 'desligado (F8 liga; Shift segurado trava na hora)'}`);
    this._agendarPaineis('snap');
  }

  _painelVistas() {
    const raiz = this.el.vistas; raiz.replaceChildren();
    if (!this.doc.vistas.length) { raiz.append(el('div', { class: 'nada', texto: 'Nenhuma vista do modelo neste desenho. Use o menu "Vistas do modelo".' })); return; }
    for (const v of this.doc.vistas) {
      const item = el('div', { class: 'vista-item', title: 'Clique para enquadrar' },
        el('div', { class: 't', texto: v.nome || v.tipo }),
        el('div', { class: 's', texto: `${v.tipo || 'corte'} · ${v.pecas_cortadas || 0} cortadas, ${v.pecas_projetadas || 0} projetadas · ${numero(v.largura)} × ${numero(v.altura)} mm` + (v.profundidade ? ` · prof. ${numero(v.profundidade)} mm` : '') }));
      item.addEventListener('click', () => { const c = v.canto || [0, 0]; this.tela.enquadrar([[c[0], c[1]], [c[0] + (v.largura || 1), c[1] + (v.altura || 1)]], 0.1); });
      raiz.append(item);
    }
  }

  _atualizarCarimbo() {
    this.el.contagem.textContent = `${numero(this.doc.tamanho)} objetos` + (this.tela.selecao.size ? ` · ${numero(this.tela.selecao.size)} selecionados` : '');
  }

  // ------------------------------------------------------------ diálogos
  dialogo({ titulo, corpo, ok = 'OK' }) {
    return new Promise((resolver) => {
      const d = $('#dialogo');
      $('#dialogo-titulo').textContent = titulo;
      $('#dialogo-corpo').replaceChildren(corpo);
      $('#dialogo-ok').textContent = ok; $('#dialogo-ok').hidden = ok === null;
      const fechar = (v) => { d.querySelector('form').onsubmit = null; $('#dialogo-cancelar').onclick = null; d.oncancel = null; d.close(); resolver(v); };
      d.querySelector('form').onsubmit = (ev) => { ev.preventDefault(); fechar('ok'); };
      $('#dialogo-cancelar').onclick = () => fechar(null);
      d.oncancel = (ev) => { ev.preventDefault(); fechar(null); };
      d.showModal();
      const primeiro = corpo.querySelector && corpo.querySelector('input, select, button');
      if (primeiro) primeiro.focus();
    });
  }

  async perguntar(titulo, rotulo, valor = '') {
    const i = el('input', { type: 'text', value: valor, spellcheck: 'false' });
    const corpo = el('div', {}, el('label', {}, rotulo, i));
    const r = await this.dialogo({ titulo, corpo });
    return r === 'ok' ? i.value : null;
  }

  async dialogoAbrir() {
    if (!this.projeto) return;
    const lista = await this._listaDesenhos();
    const caixa = el('div', { class: 'lista-abrir' });
    if (!lista.length) caixa.append(el('div', { class: 'explica', texto: 'Este projeto ainda não tem desenhos 2D.' }));
    let escolhido = null;
    for (const d of lista) {
      const b = el('button', { type: 'button' }, d.titulo || d.nome, el('small', { texto: `${numero(d.entidades)} objetos · 1:${d.escala} · ${(d.vistas || []).join(', ') || 'sem vistas'} · ${d.alterado.replace('T', ' ')}` }));
      // fecha pelo "cancelar" do diálogo, que resolve a promessa (o close() direto a deixava pendurada)
      b.addEventListener('click', () => { escolhido = d.nome; $('#dialogo-cancelar').click(); });
      caixa.append(b);
    }
    await this.dialogo({ titulo: 'Abrir desenho do projeto', corpo: caixa, ok: null });
    if (escolhido) await this.abrirDesenho(escolhido);
  }

  /** Desenhos salvos do projeto dentro do menu Desenho: abrir com um clique, × exclui. */
  async _listarDesenhosNoMenu() {
    const bloco = $('#desenhos-salvos');
    if (!bloco) return;
    if (!this.projeto) { bloco.replaceChildren(); return; }
    bloco.replaceChildren(el('div', { class: 'menu-nota', texto: 'Desenhos salvos…' }));
    const lista = await this._listaDesenhos();
    if (!lista.length) { bloco.replaceChildren(el('div', { class: 'menu-nota', texto: 'Nenhum desenho salvo neste projeto ainda.' })); return; }
    bloco.replaceChildren(el('div', { class: 'menu-nota', texto: `Desenhos salvos (${lista.length}):` }),
      ...lista.map(d => el('div', { class: 'desenho-salvo' + (d.nome === this.nomeDesenho ? ' atual' : '') },
        el('button', { type: 'button', 'data-desenho': d.nome, title: `${(d.vistas || []).join(', ') || 'sem vistas'} · ${d.alterado ? d.alterado.replace('T', ' ').slice(0, 16) : ''}` },
          el('span', { texto: d.titulo || d.nome }),
          el('small', { texto: `${numero(d.entidades || 0)} objetos · 1:${d.escala || '?'}` })),
        el('button', { type: 'button', class: 'excluir', 'data-excluir': d.nome, 'data-titulo': d.titulo || d.nome, title: 'Excluir este desenho (vai para a lixeira)', texto: '×' }))));
  }

  async _excluirUmDesenho(nome, titulo) {
    const corpo = el('div', {}, el('p', {}, `Excluir o desenho "${titulo || nome}"? Ele vai para a pasta .lixeira dos dados.`));
    if (await this.dialogo({ titulo: 'Excluir desenho', corpo, ok: 'Excluir' }) !== 'ok') return;
    try {
      await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(nome)}/excluir`, {});
      this.aviso(`Desenho "${titulo || nome}" excluído.`, 'info', 6000);
      if (nome === this.nomeDesenho) {
        this._autosavePendente = false;
        if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
        const resto = await this._listaDesenhos();
        if (resto.length) await this.abrirDesenho(resto[0].nome);
        else { this.nomeDesenho = null; this.carregar({ nome: 'Desenho', escala: 20 }); }
      }
    } catch (e) { this.aviso(`Não foi possível excluir: ${e.message}`, 'erro'); }
  }

  /**
   * Furos do detalhe de uma chapa (camada FURO) → chapas paramétricas da posição no
   * modelo 3D. O servidor regrava o modelo e regenera o detalhe, que é reaberto.
   */
  /** A posição da chapa em foco: a do detalhe aberto, ou a da seleção num desenho geral. */
  _marcaEmFoco() {
    const meta = (this.doc.metadados || {}).detalhe_posicao;
    if (meta && meta.marca) return { marca: meta.marca, editavel: !!meta.editavel, detalhe: true };
    const geral = (this.doc.metadados || {}).detalhamento || {};
    const ents = [...this.tela.selecao].map(id => this.doc.get(id)).filter(Boolean);
    const marcas = [...new Set(ents.map(e => (e.atributos || {}).posicao).filter(Boolean))];
    if (marcas.length !== 1) return null;
    return { marca: marcas[0], editavel: (geral.editaveis || []).includes(marcas[0]), detalhe: false };
  }

  _contornoDe(marca) {
    let melhor = null, area = -1;
    for (const e of this.doc.entidades.values()) {
      const a = e.atributos || {};
      // o contorno da chapa fica na camada VISTA (desenhos antigos) ou CHAPAS (camada por tipo de peça)
      if (e.tipo !== 'polilinha' || !e.fechada || (e.camada !== 'VISTA' && e.camada !== 'CHAPAS') || a.detalhe !== 'posicao' || String(a.posicao) !== marca || 'furo' in a) continue;
      const v = e.vertices; let s = 0;
      for (let i = 0; i < v.length; i++) { const p = v[i], q = v[(i + 1) % v.length]; s += p[0] * q[1] - q[0] * p[1]; }
      if (Math.abs(s) > area) { area = Math.abs(s); melhor = e; }
    }
    return melhor;
  }

  /** Comprimento × altura do contorno da chapa em foco; os furos ficam onde estão. */
  async ajustarTamanho() {
    const foco = this._marcaEmFoco();
    if (!foco) { this.aviso('Selecione a chapa (contorno, furo ou título) cujo tamanho vai mudar.', 'atencao'); return; }
    const cont = this._contornoDe(foco.marca);
    if (!cont) { this.aviso(`Não achei o contorno da chapa ${foco.marca} neste desenho.`, 'atencao'); return; }
    const xs = cont.vertices.map(p => p[0]), ys = cont.vertices.map(p => p[1]);
    const x0 = Math.min(...xs), y0 = Math.min(...ys), L0 = Math.max(...xs) - x0, H0 = Math.max(...ys) - y0;
    const L = el('input', { type: 'number', step: 'any', value: String(Math.round(L0 * 100) / 100) });
    const H = el('input', { type: 'number', step: 'any', value: String(Math.round(H0 * 100) / 100) });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: `Chapa ${foco.marca}: o contorno é esticado a partir do canto inferior esquerdo; os furos não se movem. Depois use "Aplicar furos e tamanho ao modelo 3D".` }),
      el('label', { class: 'linha' }, 'Comprimento (mm) ', L), el('label', { class: 'linha' }, 'Altura (mm) ', H));
    if (await this.dialogo({ titulo: 'Ajustar tamanho da chapa', corpo, ok: 'Ajustar' }) !== 'ok') return;
    const nL = parseFloat(String(L.value).replace(',', '.')), nH = parseFloat(String(H.value).replace(',', '.'));
    if (!(nL > 0) || !(nH > 0) || !(L0 > 0) || !(H0 > 0)) { this.aviso('Medidas inválidas.', 'atencao'); return; }
    const vertices = cont.vertices.map(([x, y]) => [Math.round((x0 + (x - x0) * nL / L0) * 1000) / 1000, Math.round((y0 + (y - y0) * nH / H0) * 1000) / 1000]);
    this.executar(new ComandoAlterar({ [cont.id]: { vertices } }, 'Ajustar tamanho'));
    this.aviso(`Contorno de ${foco.marca}: ${formatarMm(nL)} × ${formatarMm(nH)} mm. As cotas atualizam ao aplicar no modelo 3D.`, 'info', 8000);
  }

  /**
   * Furos (camada FURO) e contorno da chapa em foco → chapas paramétricas da posição
   * no modelo 3D. Detalhe aberto pelo 3D: regenerado inteiro; desenho geral: só a
   * célula. O servidor regrava o modelo e o desenho, que é reaberto.
   */
  /** O conjunto (célula) da seleção: o `conjunto` das linhas selecionadas, um só. */
  _conjuntoEmFoco() {
    const ents = [...this.tela.selecao].map(id => this.doc.get(id)).filter(Boolean);
    const conjs = [...new Set(ents.map(e => (e.atributos || {}).conjunto).filter(Boolean))];
    return conjs.length === 1 ? conjs[0] : null;
  }

  /** As barras movidas/espelhadas/esticadas/copiadas/apagadas nas elevações vão para o 3D. */
  async aplicarPecas() {
    if (!this.projeto || !this.nomeDesenho) { this.aviso('Abra um desenho de detalhamento do projeto.', 'atencao'); return; }
    const celulas = (this.doc.vistas || []).filter(v => v.tipo === 'conjunto').length;
    if (!celulas) { this.aviso('Este desenho não tem elevações de conjunto (tesouras): abra o detalhamento de tesouras, de conjuntos ou o completo.', 'atencao'); return; }
    const corpo = el('div', {}, el('p', {}, `Levar para o modelo 3D o que mudou nas elevações dos conjuntos deste desenho: barras movidas ou espelhadas são movidas no 3D, esticadas têm a ponta movida, cópias viram peças novas e barras apagadas saem do modelo — em todas as tesouras de cada tipo. O modelo anterior vai para o histórico. Em seguida os outros desenhos de detalhamento (o completo, os conjuntos…) são gerados de novo a partir do 3D corrigido; este fica como você o deixou. Leva um pouco.`));
    if (await this.dialogo({ titulo: 'Aplicar peças das elevações ao modelo 3D', corpo, ok: 'Aplicar' }) !== 'ok') return;
    this.dica('Comparando o desenho com o modelo…');
    const parar = this._acompanharProgresso ? this._acompanharProgresso('Aplicando: ') : () => {};
    try {
      if (this.doc.tamanho && this.nomeDesenho) await this.salvar({ avisar: false });
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/aplicar-pecas`, { desenho: this.doc.paraJSON() });
      parar(); this.dica('');
      const t = r.total || {};
      const mudou = Object.keys(r.celulas || {});
      if (!mudou.length) { this.aviso('Nada mudou nas elevações em relação ao modelo 3D.' + ((r.avisos || []).length ? ' ' + r.avisos.join(' · ') : ''), 'info', 10000); return; }
      const reg = (r.regenerados || []).length;
      this.aviso(`${mudou.join(', ')}: ${t.movidas} barra(s) movidas, ${t.esticadas} esticada(s), ${t.copiadas} nova(s), ${t.apagadas} apagada(s) no modelo 3D (em todas as instâncias).` +
                 (reg ? ` ${reg} desenho(s) de detalhamento gerados de novo a partir do 3D corrigido; este ficou como você o deixou.` : ' O próximo Detalhar já sai com a correção.') +
                 ((r.avisos || []).length ? ` Avisos: ${r.avisos.join(' · ')}` : ''), 'info', 20000);
    } catch (e) { parar(); this.aviso(`Não foi possível aplicar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  async aplicarFuros() {
    if (!this.projeto || !this.nomeDesenho) { this.aviso('Abra um desenho de detalhamento do projeto.', 'atencao'); return; }
    const foco = this._marcaEmFoco();
    if (!foco) { this.aviso('Selecione a chapa (contorno, furo ou título) cujos furos vão para o modelo 3D, ou abra o detalhe dela pelo 3D (duplo clique).', 'atencao'); return; }
    if (!foco.editavel) { this.aviso(`A chapa ${foco.marca} não é paramétrica neste desenho: gere o detalhamento de novo (as chapas planas viram paramétricas) ou abra a peça pelo 3D.`, 'atencao'); return; }
    const corpo = el('div', {}, el('p', {}, `Levar os furos da camada FURO e o contorno de ${foco.marca} deste desenho para todas as chapas ${foco.marca} do modelo 3D? ${foco.detalhe ? 'O detalhe' : 'A célula'} é regenerad${foco.detalhe ? 'o' : 'a'} em seguida.`));
    if (await this.dialogo({ titulo: 'Aplicar furos e tamanho ao modelo 3D', corpo, ok: 'Aplicar' }) !== 'ok') return;
    this.dica('Aplicando no modelo…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/aplicar-furos`, { desenho: this.doc.paraJSON(), marca: foco.marca });
      this._autosavePendente = false;
      if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
      await this.abrirDesenho(r.nome);
      const vinc = (r.vinculadas || []).length;
      const b3 = r.barras3d || {};
      const ign = (b3.ignoradas || []).length;
      if (!r.chapas && r.marcas) {
        // barra: furação guardada no projeto e furos movidos na malha 3D
        this.aviso(`${r.furos} furo(s) da alma de ${r.marca} guardados como furação da posição` +
                   (b3.barras ? ` e movidos em ${b3.barras} barra(s) no modelo 3D` : '') +
                   (ign ? `; ${ign} barra(s) ficaram como estavam no 3D (furo novo, apagado ou deslocado demais)` : '') +
                   '; desenho regenerado. Furo novo ou apagado vale só no desenho e na lista.', 'info', 14000);
        return;
      }
      this.aviso(`${r.furos} furo(s)${r.contornos ? ' e o contorno' : ''} aplicados em ${r.chapas} chapa(s) ${r.marca} do modelo 3D${r.parafusos ? `, ${r.parafusos} parafuso(s) movidos junto` : ''}; desenho regenerado.` +
                 (vinc ? ` Furação de ${vinc} terça(s) ajustada junto (${r.vinculadas.slice(0, 6).join(', ')}${vinc > 6 ? '…' : ''})` +
                         (b3.barras ? `, ${b3.furos} furo(s) movidos em ${b3.barras} terça(s) no 3D` : '') +
                         ': gere o desenho de barras e terças de novo.' : ''), 'info', 14000);
    } catch (e) { this.aviso(`Não foi possível aplicar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  async dialogoExcluir() {
    if (!this.projeto) { this.aviso('Excluir desenhos precisa de um projeto aberto.', 'atencao'); return; }
    const lista = await this._listaDesenhos();
    const excluidos = await this.dialogoExcluirDesenhos(lista, { atual: this.nomeDesenho });
    if (excluidos.includes(this.nomeDesenho)) {
      // o desenho aberto foi embora: não pode ser regravado pelo autosave
      this._autosavePendente = false;
      if (this._autosaveTimer) { clearTimeout(this._autosaveTimer); this._autosaveTimer = null; }
      const resto = (await this._listaDesenhos());
      if (resto.length) await this.abrirDesenho(resto[0].nome);
      else { this.nomeDesenho = null; this.carregar({ nome: 'Desenho', escala: 20 }); const url = new URL(location.href); url.searchParams.delete('desenho'); history.replaceState(null, '', url); }
    }
  }

  /**
   * Diálogo com a lista dos desenhos do projeto em caixas; os marcados vão para a
   * lixeira da pasta de dados (.lixeira), de onde dá para recuperar à mão.
   */
  async dialogoExcluirDesenhos(lista, { atual = null } = {}) {
    if (!lista.length) { this.aviso('O projeto não tem desenhos para excluir.', 'atencao'); return []; }
    const caixas = new Map();
    const opcoes = el('div', { class: 'lista-opcoes', style: 'max-height:45vh;overflow:auto' });
    for (const d of lista) {
      const c = el('input', { type: 'checkbox' });
      caixas.set(d.nome, c);
      opcoes.append(el('label', { class: 'linha' }, c, ` ${d.titulo || d.nome}`,
        el('small', { texto: `  ${(d.entidades || 0).toLocaleString('pt-BR')} objetos · ${(d.vistas || []).length} vista(s) · ${d.alterado ? d.alterado.replace('T', ' ').slice(0, 16) : ''}` })));
    }
    const marcar = (teste) => { for (const d of lista) caixas.get(d.nome).checked = teste(d); };
    const atalhos = el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin:8px 0' },
      el('button', { type: 'button', onclick: () => marcar(d => /^detalhamento/i.test(d.nome)) }, 'Marcar detalhamentos'),
      el('button', { type: 'button', onclick: () => marcar(d => /^prancha(-\d+)?$/i.test(d.nome)) }, 'Marcar pranchas'),
      el('button', { type: 'button', onclick: () => marcar(() => true) }, 'Marcar todos'),
      el('button', { type: 'button', onclick: () => marcar(() => false) }, 'Desmarcar'));
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Os desenhos marcados saem do projeto e vão para a pasta .lixeira dos dados (dá para recuperar à mão). Depois, "Detalhar peças e conjuntos…" gera tudo de novo.' }),
      atalhos, opcoes);
    if (await this.dialogo({ titulo: 'Excluir desenhos do projeto', corpo, ok: 'Excluir marcados' }) !== 'ok') return [];
    const nomes = lista.map(d => d.nome).filter(n => caixas.get(n).checked);
    if (!nomes.length) return [];
    const excluidos = [];
    for (const n of nomes) {
      try {
        const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(n)}/excluir`, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: '{}' });
        const j = await r.json();
        if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
        excluidos.push(n);
      } catch (e) { this.aviso(`Não foi possível excluir "${n}": ${e.message}`, 'erro'); }
    }
    if (excluidos.length) this.aviso(`${excluidos.length} desenho(s) excluído(s)${excluidos.includes(atual) ? ' — inclusive o que estava aberto' : ''}.`, 'info', 8000);
    return excluidos;
  }

  async dialogoNovo() {
    const lista = this.projeto ? await this._listaDesenhos() : [];
    const nome = await this.perguntar('Novo desenho', 'Nome', 'Desenho ' + (lista.length + 1));
    if (!nome) return;
    // nome que já existe no projeto: gravar o desenho novo apagaria o que está nele
    const existente = lista.find(d => d.nome === slug(nome) || (d.titulo || '') === nome.trim());
    if (existente) {
      const corpo = el('div', { class: 'explica', texto: `Já existe o desenho "${existente.titulo || existente.nome}" neste projeto; um desenho novo com esse nome apagaria o que está nele. Escolha outro nome, ou abra o existente.` });
      if (await this.dialogo({ titulo: 'Nome já usado', corpo, ok: 'Abrir o existente' }) === 'ok') await this.abrirDesenho(existente.nome);
      return;
    }
    if (this.nomeDesenho && this._temPendente() && !(await this._gravarOuConfirmar('Criar mesmo assim'))) return;
    this._naoAbriu = null;
    this.nomeDesenho = slug(nome);
    this.carregar({ nome, escala: 20 });
    const url = new URL(location.href); url.searchParams.set('desenho', this.nomeDesenho); history.replaceState(null, '', url);
    this._agendarAutosave();
  }

  /**
   * Aplica estilos a um conjunto de entidades (ou ao desenho inteiro): altura dos textos e
   * cotas, terminador das cotas (seta, bola, traco) e padrão/espaçamento/ângulo das
   * hachuras. `opcoes`: {altura, terminador, padrao, espacamento, angulo} — o que vier
   * vazio não muda. Com `ids` nulo vale para todas as entidades, e o desenho guarda o
   * padrão em metadados.estilo (as cotas sem terminador próprio usam o do desenho).
   */
  aplicarEstilos(opcoes, ids = null) {
    const alvo = ids ? ids.map(id => this.doc.get(id)).filter(Boolean) : [...this.doc.entidades.values()];
    const mud = {};
    const alt = opcoes.altura != null && isFinite(opcoes.altura) && opcoes.altura > 0 ? +opcoes.altura : null;
    for (const e of alvo) {
      const m = {};
      if (alt && (e.tipo === 'texto' || e.tipo === 'cota' || e.tipo === 'chamada')) m.altura = alt;
      if (opcoes.terminador && e.tipo === 'cota') m.terminador = opcoes.terminador === 'padrao' ? null : opcoes.terminador;
      if (e.tipo === 'hachura') {
        if (opcoes.padrao) m.padrao = opcoes.padrao;
        if (opcoes.espacamento != null && isFinite(opcoes.espacamento) && opcoes.espacamento > 0) m.espacamento = +opcoes.espacamento;
        if (opcoes.angulo != null && isFinite(opcoes.angulo)) m.angulo = +opcoes.angulo;
      }
      if (Object.keys(m).length) mud[e.id] = m;
    }
    if (!ids) {
      const estilo = { ...((this.doc.metadados || {}).estilo || {}) };
      if (alt) { estilo.texto = alt; this.alturaTexto = alt; }
      if (opcoes.terminador && opcoes.terminador !== 'padrao') estilo.terminador = opcoes.terminador;
      if (opcoes.padrao) estilo.hachura = opcoes.padrao;
      this.doc.metadados = { ...(this.doc.metadados || {}), estilo };
    }
    const n = Object.keys(mud).length;
    if (n) this.executar(new ComandoAlterar(mud, 'Estilos do desenho'));
    else this._aposMudanca({ acao: 'aparencia' });
    return n;
  }

  async dialogoEstilos() {
    const sel = [...this.tela.selecao];
    const estilo = ((this.doc.metadados || {}).estilo || {});
    const campos = {
      escopo: el('select', {}, ...[[sel.length ? 'selecao' : 'todos', sel.length ? `Seleção (${sel.length} objeto(s))` : 'Todo o desenho'], [sel.length ? 'todos' : 'selecao', sel.length ? 'Todo o desenho' : 'Seleção (nada selecionado)']].map(([v, t]) => el('option', { value: v, texto: t }))),
      altura: el('input', { type: 'number', step: '0.5', min: '0.5', value: String(estilo.texto || this.alturaTexto || 2.5), placeholder: 'mm no papel' }),
      terminador: el('select', {}, ...[['', 'manter'], ['seta', 'Seta'], ['bola', 'Bola (ponto)'], ['traco', 'Traço oblíquo']].map(([v, t]) => el('option', { value: v, texto: t, selected: (estilo.terminador || 'seta') === v && v ? 'selected' : undefined }))),
      padrao: el('select', {}, ...[['', 'manter'], ['aco', 'Aço (linhas a 45°)'], ['concreto', 'Concreto'], ['solido', 'Sólido']].map(([v, t]) => el('option', { value: v, texto: t }))),
      espacamento: el('input', { type: 'number', step: '0.5', min: '0.5', placeholder: 'manter (mm no papel)' }),
      angulo: el('input', { type: 'number', step: '15', placeholder: 'manter (graus)' }),
      mudarAltura: el('input', { type: 'checkbox' }),
    };
    campos.terminador.value = '';
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Como os estilos do AutoCAD: a altura vale para textos, cotas e chamadas; o terminador para as cotas; padrão, espaçamento e ângulo para as hachuras. Com "todo o desenho", a altura vira a altura padrão dos textos novos e o terminador o das cotas novas.' }),
      el('label', {}, 'Aplicar a', campos.escopo),
      el('label', {}, el('span', {}, campos.mudarAltura, ' Altura de texto e cota (mm)'), campos.altura),
      el('label', {}, 'Terminador das cotas', campos.terminador),
      el('label', {}, 'Padrão das hachuras', campos.padrao),
      el('label', {}, 'Espaçamento da hachura (mm)', campos.espacamento),
      el('label', {}, 'Ângulo da hachura (°)', campos.angulo));
    if (await this.dialogo({ titulo: 'Estilos do desenho', corpo, ok: 'Aplicar' }) !== 'ok') return;
    const opcoes = {
      altura: campos.mudarAltura.checked ? parseFloat(campos.altura.value) : null,
      terminador: campos.terminador.value || null,
      padrao: campos.padrao.value || null,
      espacamento: campos.espacamento.value ? parseFloat(campos.espacamento.value) : null,
      angulo: campos.angulo.value ? parseFloat(campos.angulo.value) : null,
    };
    const ids = campos.escopo.value === 'selecao' ? sel : null;
    const n = this.aplicarEstilos(opcoes, ids);
    this.aviso(n ? `Estilos aplicados em ${n} objeto(s).` : 'Nada a mudar com essas opções.', 'info');
  }

  async dialogoCorte() {
    const campos = {
      eixo: el('select', {}, ...[['y', 'Corte transversal (plano perpendicular a Y, olhando para +Y)'], ['-y', 'Corte transversal olhando para −Y'], ['x', 'Corte longitudinal (perpendicular a X, olhando para +X)'], ['-x', 'Corte longitudinal olhando para −X'], ['z', 'Corte horizontal (planta, olhando para baixo)']].map(([v, t]) => el('option', { value: v, texto: t }))),
      posicao: el('input', { type: 'number', step: 'any', value: '0', placeholder: 'mm' }),
      profundidade: el('input', { type: 'number', step: 'any', value: '1500', placeholder: 'mm' }),
      nome: el('input', { type: 'text', value: 'Corte A' }),
    };
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Posição é a coordenada do plano ao longo do eixo (mm). A profundidade limita o que aparece além do corte. Para posicionar o plano vendo o modelo, use a ferramenta Seção no Modelo 3D.' }),
      el('label', {}, 'Direção', campos.eixo), el('label', {}, 'Posição do plano (mm)', campos.posicao),
      el('label', {}, 'Profundidade de vista (mm)', campos.profundidade), el('label', {}, 'Nome da vista', campos.nome));
    if (await this.dialogo({ titulo: 'Corte por plano', corpo, ok: 'Gerar' }) !== 'ok') return;
    const eixo = campos.eixo.value, pos = parseFloat(campos.posicao.value) || 0;
    const normal = { y: [0, 1, 0], '-y': [0, -1, 0], x: [1, 0, 0], '-x': [-1, 0, 0], z: [0, 0, -1] }[eixo];
    const origem = eixo.endsWith('y') ? [0, pos, 0] : eixo.endsWith('x') ? [pos, 0, 0] : [0, 0, pos];
    const prof = parseFloat(campos.profundidade.value);
    await this.inserirVista({ origem, normal, acima: eixo === 'z' ? [0, 1, 0] : null, profundidade: isFinite(prof) && prof > 0 ? prof : null, cortar: true, nome: campos.nome.value, tipo: 'corte' }, campos.nome.value);
  }

  /** Detalhamento de peças e conjuntos do projeto (mesma rota do editor 3D); abre o primeiro desenho aqui. */
  /** Peça do catálogo que a seleção representa (dela ou herdada da camada). */
  _pecaDe(ent) {
    const dela = ent && ent.atributos && ent.atributos.peca;
    if (dela && dela.perfil) return { ...dela, herdada: false };
    const porCamada = (this.doc.metadados && this.doc.metadados.pecas_por_camada) || {};
    const c = porCamada[ent && ent.camada];
    return c && c.perfil ? { ...c, herdada: true } : null;
  }

  /** Linha "Peça" no painel de propriedades, com o que fazer para mudá-la. */
  _linhaPeca(g, ents) {
    const pecas = ents.map(e => this._pecaDe(e));
    const nomes = new Set(pecas.map(p => (p ? p.perfil : '')));
    const texto = nomes.size > 1 ? '— várias —'
      : (pecas[0] ? `${pecas[0].perfil}${pecas[0].herdada ? ' (da camada)' : ''}` : 'sem peça (anotação)');
    const b = el('button', { type: 'button', class: 'mini', texto: 'Peça…',
      title: 'Escolher a peça do catálogo desta seleção', onclick: () => this.dialogoPeca() });
    g.append(el('label', { texto: 'Peça' }), el('div', { class: 'linha-peca' },
      el('span', { texto, title: pecas[0] ? `${pecas[0].papel || 'barra'} · ${pecas[0].aco || 'aço padrão'}` : '' }), b));
  }

  /**
   * Diz que peça do catálogo as linhas representam. Sem seleção, vale para a camada
   * ativa — é como se desenha uma tesoura inteira: uma camada por tipo de peça.
   */
  async dialogoPeca() {
    const ids = [...this.tela.selecao];
    const alvoCamada = !ids.length;
    const camada = this.camadaAtiva;
    let fams = [];
    try { fams = (await pedir('/api/catalogo/pecas')).familias || []; }
    catch (e) { this.aviso(`Catálogo indisponível: ${e.message}`, 'erro'); return; }
    // barras e chapas: a polilinha fechada com chapa vira chapa de nó no 3D
    const barras = fams.filter(f => f.peca === 'barra' || f.peca === 'chapa');
    const atual = alvoCamada
      ? ((this.doc.metadados && this.doc.metadados.pecas_por_camada) || {})[camada]
      : this._pecaDe(this.doc.get(ids[0]));
    const selFam = el('select');
    for (const f of barras) selFam.append(el('option', { value: f.familia, texto: f.nome }));
    const selPerfil = el('select');
    const busca = el('input', { type: 'search', placeholder: 'buscar: 150x60, W 310, 3/8…', spellcheck: 'false' });
    const selPapel = el('select');
    for (const p of ['banzo', 'diagonal', 'montante', 'terça', 'longarina', 'viga', 'pilar',
                     'contraventamento', 'tirante', 'corrente', 'barra', 'chapa']) {
      selPapel.append(el('option', { value: p, texto: p }));
    }
    const selAco = el('select');
    try {
      const cat = await pedir('/api/catalogo');
      for (const a of (cat.acos || [])) selAco.append(el('option', { value: a.nome, texto: a.nome }));
    } catch { selAco.append(el('option', { value: '', texto: 'padrão' })); }
    const rot = el('input', { type: 'number', step: '15', value: '0', title: 'Giro da seção em torno do eixo da barra' });
    const carregar = async () => {
      const q = busca.value.trim();
      const rota = `/api/catalogo/pecas?familia=${encodeURIComponent(selFam.value)}` +
                   (q ? `&q=${encodeURIComponent(q)}` : '') + '&limite=400';
      let itens = [];
      try { itens = (await pedir(rota)).itens || []; } catch { itens = []; }
      selPerfil.replaceChildren();
      for (const i of itens) {
        selPerfil.append(el('option', { value: i.nome,
          texto: `${i.nome} · ${numero(i.massa || 0, 2)} kg/m` }));
      }
      if (atual && atual.perfil && itens.some(i => i.nome === atual.perfil)) selPerfil.value = atual.perfil;
    };
    const ehChapa = () => (fams.find(f => f.familia === selFam.value) || {}).peca === 'chapa';
    const ajustarPapel = () => {
      if (ehChapa()) { selPapel.value = 'chapa'; selPapel.disabled = true; }
      else { if (selPapel.value === 'chapa') selPapel.value = 'banzo'; selPapel.disabled = false; }
    };
    selFam.addEventListener('change', () => { ajustarPapel(); carregar(); });
    let t = null;
    busca.addEventListener('input', () => { clearTimeout(t); t = setTimeout(carregar, 180); });
    if (atual) {
      if (atual.papel) selPapel.value = atual.papel;
      if (atual.aco) selAco.value = atual.aco;
      if (atual.rotacao) rot.value = String(atual.rotacao);
      const fam = barras.find(f => (atual.perfil || '').startsWith(f.familia === 'I' ? 'W' : f.familia));
      if (fam) selFam.value = fam.familia;
    }
    ajustarPapel();
    await carregar();
    const campos = el('div', { class: 'campos' },
      el('label', { texto: 'Família' }), selFam,
      el('label', { texto: 'Buscar' }), busca,
      el('label', { texto: 'Perfil' }), selPerfil,
      el('label', { texto: 'Papel' }), selPapel,
      el('label', { texto: 'Aço' }), selAco,
      el('label', { texto: 'Giro da seção (°)' }), rot);
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: alvoCamada
        ? `Nada selecionado: a peça vale para tudo o que está (e for desenhado) na camada ${camada}.`
        : `${ids.length} objeto(s) selecionado(s).` }),
      campos,
      el('div', { class: 'explica', texto: 'Cada linha com peça vira uma barra no 3D, com perfil, aço, papel e marcas de posição e conjunto — como uma peça vinda de IFC. Escolhendo uma chapa, a polilinha fechada vira a chapa de nó, e os círculos dentro dela viram os furos.' }));
    const r = await this.dialogo({ titulo: alvoCamada ? `Peça da camada ${camada}` : 'Peça do catálogo', corpo, ok: 'Aplicar' });
    if (r !== 'ok' || !selPerfil.value) return;
    const peca = { perfil: selPerfil.value, papel: selPapel.value, aco: selAco.value || '',
                   rotacao: parseFloat(rot.value) || 0 };
    if (alvoCamada) {
      const meta = { ...(this.doc.metadados || {}) };
      meta.pecas_por_camada = { ...(meta.pecas_por_camada || {}), [camada]: peca };
      this.doc.metadados = meta;
      this.doc.notificar([], 'aparencia');
      this._agendarAutosave();
      this.dica(`Camada ${camada}: ${peca.perfil}.`);
    } else {
      const mudancas = {};
      for (const id of ids) {
        const e = this.doc.get(id);
        mudancas[id] = { atributos: { ...(e.atributos || {}), peca } };
      }
      this.executar(new ComandoAlterar(mudancas, `Peça ${peca.perfil}`));
      this.dica(`${ids.length} objeto(s): ${peca.perfil}.`);
    }
    this._agendarPaineis('props');
  }

  /** Gera o modelo 3D deste desenho (uma tesoura desenhada vira as oito do galpão). */
  async dialogoGerar3D() {
    if (!this.projeto) { this.aviso('Gerar o 3D precisa de um projeto aberto.', 'atencao'); return; }
    if (!this.nomeDesenho) { this.aviso('Salve o desenho antes de gerar o modelo.', 'atencao'); return; }
    if (this.doc.tamanho) await this.salvar({ avisar: false });
    const montagens = ((this.doc.metadados || {}).reconhecimento || {}).montagens;
    if (montagens && montagens.length) return this._dialogoGerar3DVistas(montagens);
    let info;
    try {
      info = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/gerar-3d`, { conferir: true });
    } catch (e) { this.aviso(`Não foi possível ler o desenho: ${e.message}`, 'erro', 0); return; }
    if (!info.barras) {
      this.aviso('Nenhuma linha deste desenho tem peça do catálogo. Use "Peça do catálogo…" ' +
                 'na seleção ou na camada antes de gerar o modelo.', 'atencao', 0);
      return;
    }
    const selPlano = el('select');
    for (const p of info.planos) selPlano.append(el('option', { value: p.chave, texto: p.nome }));
    const num = (v, t) => el('input', { type: 'number', step: 'any', value: String(v), title: t });
    const rep = num(1, 'Quantas cópias do desenho, uma por conjunto');
    const esp = num(5000, 'Distância entre as cópias, em mm');
    const ox = num(0, 'Onde o ponto (0,0) do desenho cai no modelo, em mm');
    const oy = num(0, '');
    const oz = num(0, '');
    const conj = el('input', { type: 'text', value: 'M', title: 'Prefixo da marca de conjunto: M1, M2…' });
    const modo = el('select');
    modo.append(el('option', { value: 'acrescentar', texto: 'acrescentar ao modelo do projeto' }));
    modo.append(el('option', { value: 'substituir', texto: 'substituir o modelo do projeto' }));
    const perfis = Object.entries(info.perfis || {}).map(([n, q]) => `${q}× ${n}`).join(' · ');
    const corpo = el('div', {},
      el('div', { class: 'explica', texto:
        `${info.barras} barra(s) em ${info.com_peca} objeto(s) com peça, ${numero(info.comprimento_m, 1)} m no total. ` +
        `${info.anotacao} objeto(s) sem peça ficam de fora (cotas, textos, eixos).` }),
      el('div', { class: 'explica', texto: perfis }),
      el('div', { class: 'campos' },
        el('label', { texto: 'Plano' }), selPlano,
        el('label', { texto: 'Cópias' }), rep,
        el('label', { texto: 'Espaçamento (mm)' }), esp,
        el('label', { texto: 'Origem X (mm)' }), ox,
        el('label', { texto: 'Origem Y (mm)' }), oy,
        el('label', { texto: 'Origem Z (mm)' }), oz,
        el('label', { texto: 'Conjunto' }), conj,
        el('label', { texto: 'Modelo' }), modo),
      el('div', { class: 'explica', texto:
        'Cada cópia é um conjunto de montagem (M1, M2…) e cada peça ganha a marca da posição (P1, P2…), ' +
        'como num modelo vindo de IFC: dá para detalhar, listar materiais, calcular e exportar IFC.' }));
    if (await this.dialogo({ titulo: 'Gerar modelo 3D do desenho', corpo, ok: 'Gerar' }) !== 'ok') return;
    this.dica('Gerando o modelo 3D…');
    try {
      const r = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos/${encodeURIComponent(this.nomeDesenho)}/gerar-3d`, {
        plano: selPlano.value, repeticoes: parseInt(rep.value, 10) || 1,
        espacamento: parseFloat(esp.value) || 5000,
        origem: [parseFloat(ox.value) || 0, parseFloat(oy.value) || 0, parseFloat(oz.value) || 0],
        conjunto: conj.value.trim() || 'M', modo: modo.value,
      });
      const g = r.gerado || {};
      this.aviso(`Modelo 3D gerado: ${g.barras} barras em ${g.posicoes} posições, ${r.modelo.entidades} objetos no modelo. ` +
                 'Abra o Modelo 3D para ver; o modelo anterior foi guardado no histórico.', 'info', 15000);
      this.dica('Modelo 3D gerado.');
    } catch (e) {
      this.aviso(`Não foi possível gerar o modelo: ${e.message}`, 'erro', 0);
      this.dica('');
    }
  }

  async dialogoDetalhar() {
    if (!this.projeto) { this.aviso('Detalhar precisa de um projeto aberto.', 'atencao'); return; }
    const grupos = [['tesouras', 'Tesouras (com as barras e chapas delas)'], ['conjuntos', 'Conjuntos (vigas, pilares e outros)'], ['tercas', 'Terças (com suportes e chapas)'], ['contraventamentos', 'Contraventamentos (com tirantes e peças de ponta)'], ['agulhamentos', 'Agulhamentos'], ['extras', 'Extras (perfil de forro, de fechamento, barras soltas)'], ['telhas', 'Telhas'], ['chaparias', 'Chaparias (todas as chapas, 1:10)'], ['localizacao', 'Planta de localização (marcas no lugar de montagem)'], ['completo', 'Desenho completo (tudo num desenho só, 1:25)']];
    const caixas = {};
    const lista = el('div', { class: 'lista-opcoes' });
    for (const [k, r] of grupos) { caixas[k] = el('input', { type: 'checkbox', checked: 'checked' }); lista.append(el('label', { class: 'linha' }, caixas[k], ' ' + r)); }
    const regra = el('input', { type: 'checkbox', checked: 'checked' });
    const substituir = el('input', { type: 'checkbox', checked: 'checked' });
    const converter = el('input', { type: 'checkbox', checked: 'checked' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Uma célula por posição (as peças iguais são contadas, não repetidas) e a elevação de cada conjunto, com cotas de fabricação e lista de perfis. Gera um desenho por grupo e a lista de materiais.' }),
      lista,
      el('label', { class: 'linha' }, regra, ' Furação das terças no padrão da fábrica (50 × 60 abaixo de 200 mm; 100 × 60 acima)'),
      el('label', { class: 'linha' }, converter, ' Chapas planas viram chapas paramétricas no 3D (furos e tamanho editáveis no desenho)'),
      el('label', { class: 'linha' }, substituir, ' Substituir os desenhos de detalhamento anteriores'));
    if (await this.dialogo({ titulo: 'Detalhar peças e conjuntos', corpo, ok: 'Detalhar' }) !== 'ok') return;
    const escolhidos = grupos.map(([k]) => k).filter(k => caixas[k].checked);
    if (!escolhidos.length) return;
    this.dica('Detalhando as peças do projeto…');
    const parar = this._acompanharProgresso('Detalhando: ');
    try {
      if (this.doc.tamanho && this.nomeDesenho) await this.salvar({ avisar: false });
      const j = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/detalhar`, { grupos: escolhidos, regra_tercas: regra.checked, rotular: true, substituir: substituir.checked, converter: converter.checked });
      parar();
      const tercas = Object.keys(j.regra_tercas || {}).length;
      this.aviso(`Detalhamento: ${j.pecas} peças em ${j.posicoes} posições e ${j.conjuntos} conjuntos, ${j.peso_total} kg; ${j.desenhos.length} desenho(s)` + (tercas ? `, furação de fábrica em ${tercas} posições` : '') + '. Os desenhos estão em Desenho → Abrir desenho do projeto; a lista de materiais em Vistas do modelo → Lista de materiais.', 'info', 15000);
      if (j.desenhos.length) await this.abrirDesenho(j.desenhos[0].nome);
    } catch (e) { parar(); this.aviso(`Não foi possível detalhar: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  /** Pranchas com carimbo a partir dos desenhos do projeto (rota /pranchas); abre a primeira. */
  async dialogoPranchas() {
    if (!this.projeto) { this.aviso('Montar pranchas precisa de um projeto aberto.', 'atencao'); return; }
    if (this.doc.tamanho && this.nomeDesenho) await this.salvar({ avisar: false });
    const lista = (await this._listaDesenhos()).filter(d => !/^prancha(-\d+)?$/i.test(d.nome));
    if (!lista.length) { this.aviso('O projeto ainda não tem desenhos: gere cortes, vistas ou o detalhamento primeiro.', 'atencao'); return; }
    let projeto = {};
    try { projeto = (await pedir(`/api/projetos/${encodeURIComponent(this.projeto)}`)).projeto || {}; } catch { /* sem dados */ }
    const caixas = new Map();
    const opcoes = el('div', { class: 'lista-opcoes' });
    for (const d of lista) {
      // o "completo" repete as células dos grupos em 1:25: não entra por padrão
      const c = el('input', { type: 'checkbox', checked: (/^detalhamento/.test(d.nome) && !/completo/.test(d.nome)) || d.nome === this.nomeDesenho ? 'checked' : undefined });
      caixas.set(d.nome, c);
      opcoes.append(el('label', { class: 'linha' }, c, ` ${d.titulo || d.nome}`, el('small', { texto: `  ${numero(d.entidades || 0)} objetos · 1:${d.escala || '?'}` })));
    }
    const formato = el('select', {}, ...['A0', 'A1', 'A2', 'A3', 'A4'].map(f => el('option', { value: f, texto: f, selected: f === 'A1' ? 'selected' : undefined })));
    const campos = {
      obra: el('input', { type: 'text', value: projeto.nome || '' }),
      cliente: el('input', { type: 'text', value: projeto.cliente || '' }),
      responsavel: el('input', { type: 'text', value: projeto.responsavel || '' }),
      revisao: el('input', { type: 'text', value: '00' }),
      data: el('input', { type: 'text', value: '', placeholder: 'mês / ano de hoje' }),
      titulo: el('input', { type: 'text', value: 'Prancha', title: 'Nome base das pranchas: Prancha 01, 02, …' }),
    };
    const substituir = el('input', { type: 'checkbox', checked: 'checked' });
    const indice = el('input', { type: 'checkbox', checked: 'checked' });
    // peças selecionadas neste desenho: as posições/conjuntos das entidades marcadas
    const chavesSel = new Set();
    for (const id of this.tela.selecao) {
      const e = this.doc.get(id), a = (e && e.atributos) || {};
      if (a.detalhe === 'posicao' && a.posicao) chavesSel.add(a.posicao);
      else if (a.detalhe === 'conjunto' && a.conjunto) chavesSel.add(a.conjunto);
    }
    const soSelecao = el('input', { type: 'checkbox', checked: chavesSel.size ? 'checked' : undefined, disabled: chavesSel.size ? undefined : 'disabled' });
    const corpo = el('div', {},
      el('div', { class: 'explica', texto: 'Cada posição ou conjunto dos desenhos de detalhamento vira uma vista na escala do próprio desenho; cortes e vistas entram inteiros. O que não cabe na escala desce para a seguinte, com nota; o que não cabe na folha vai para a prancha seguinte. Cada prancha traz a tabela das posições que contém.' }),
      el('div', { class: 'explica', texto: 'Desenhos de origem:' }), opcoes,
      el('label', { class: 'linha', title: 'Selecione no desenho as células que quer na prancha (clique na peça, Shift soma) antes de abrir este diálogo' }, soSelecao,
         chavesSel.size ? ` Deste desenho, só as ${chavesSel.size} peça(s) selecionada(s): ${[...chavesSel].slice(0, 8).join(', ')}${chavesSel.size > 8 ? '…' : ''}` : ' Deste desenho, só as peças selecionadas (nada selecionado)'),
      el('label', {}, 'Formato da folha', formato),
      el('label', {}, 'Obra', campos.obra), el('label', {}, 'Cliente', campos.cliente),
      el('label', {}, 'Projetista', campos.responsavel), el('label', {}, 'Data (mês / ano)', campos.data), el('label', {}, 'Revisão', campos.revisao),
      el('label', {}, 'Nome base', campos.titulo),
      el('label', { class: 'linha' }, indice, ' Prancha 01 de índice: relação das pranchas e tabela de todas as posições com a prancha de cada uma'),
      el('label', { class: 'linha' }, substituir, ' Substituir as pranchas anteriores com este nome'));
    if (await this.dialogo({ titulo: 'Montar pranchas', corpo, ok: 'Montar' }) !== 'ok') return;
    const escolhidos = [...caixas].filter(([, c]) => c.checked).map(([n]) => n);
    if (!escolhidos.length) { this.aviso('Escolha ao menos um desenho.', 'atencao'); return; }
    this.dica('Montando as pranchas…');
    try {
      const desenhos = escolhidos.map(n => (soSelecao.checked && chavesSel.size && n === this.nomeDesenho) ? { nome: n, chaves: [...chavesSel] } : n);
      const j = await postar(`/api/projetos/${encodeURIComponent(this.projeto)}/pranchas`, {
        desenhos, formato: formato.value, titulo: campos.titulo.value, substituir: substituir.checked, indice: indice.checked,
        carimbo: { obra: campos.obra.value, cliente: campos.cliente.value, responsavel: campos.responsavel.value, revisao: campos.revisao.value, data: campos.data.value },
      });
      this.aviso(`${j.pranchas.length} prancha(s) ${j.formato} montada(s): ${j.pranchas.map(p => p.titulo).join(', ')}. Abra as outras em Desenho → Abrir desenho do projeto; Exportar DXF grava cada uma em papel 1:1.`, 'info', 15000);
      if (j.pranchas.length) await this.abrirDesenho(j.pranchas[0].nome);
    } catch (e) { this.aviso(`Não foi possível montar as pranchas: ${e.message}`, 'erro', 0); this.dica(''); }
  }

  // -------------------------------------------------------------- avisos
  aviso(conteudo, tipo = 'info', duracao = 6000) {
    const caixa = el('div', { class: 'aviso', 'data-tipo': tipo, role: tipo === 'erro' ? 'alert' : 'status' });
    caixa.append(typeof conteudo === 'string' ? document.createTextNode(conteudo) : conteudo);
    caixa.append(el('button', { type: 'button', title: 'fechar', texto: '×', onclick: () => caixa.remove() }));
    this.el.avisos.append(caixa);
    if (duracao) setTimeout(() => caixa.remove(), duracao);
  }

  // ---------------------------------------------------------------- tema
  _aplicarTema(t) {
    if (t === 'claro' || t === 'escuro') document.documentElement.setAttribute('data-tema', t);
    this.tela.escuro = (document.documentElement.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro')) === 'escuro';
    this.tela.pedirQuadro();
  }
  _alternarTema() {
    const atual = document.documentElement.getAttribute('data-tema') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');
    const novo = atual === 'escuro' ? 'claro' : 'escuro';
    try { localStorage.setItem(CHAVE_TEMA, novo); } catch { /* privado */ }
    this._aplicarTema(novo);
  }
}

const evInfo = (ev) => ({ shiftKey: ev.shiftKey, ctrlKey: ev.ctrlKey, altKey: ev.altKey, button: ev.button });
const slug = (s) => String(s || '').replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().toLowerCase().replace(/[\s_-]+/g, '-').slice(0, 60).replace(/^-+|-+$/g, '') || 'desenho';
function lerTema() { try { return localStorage.getItem(CHAVE_TEMA); } catch { return null; } }

// os métodos da planta de lançamento (menu Lançamento) moram em lancamento.js
for (const k of Object.getOwnPropertyNames(MetodosLancamentoCAD.prototype)) {
  if (k === 'constructor') continue;
  if (Object.prototype.hasOwnProperty.call(CAD.prototype, k)) throw new Error(`método repetido no CAD: ${k}`);
  Object.defineProperty(CAD.prototype, k, Object.getOwnPropertyDescriptor(MetodosLancamentoCAD.prototype, k));
}

const cad = new CAD();
cad.iniciar();
