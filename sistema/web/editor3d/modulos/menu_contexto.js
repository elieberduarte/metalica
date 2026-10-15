// Menu do botão direito (14/10): o clique com o botão direito (sem arrastar — arrastado continua sendo o pan) abre, no
// lugar do cursor, as ações da peça ou da seleção, como no SketchUp e no Revit. Na peça fora da seleção, ela passa a ser
// a seleção antes (o SketchUp faz assim). No vazio: mostrar as ocultas, selecionar tudo, enquadrar.
//
// "Ocultar" é só da vista (documento.ocultasAMao, conferido em documento.aparece): o modelo gravado, a lista de materiais
// e o IFC não mudam — e não briga com o "Colorir por", que troca o conjunto dele (ocultosNaVista) inteiro.

import { quadroDaMalha } from '../ferramentas/_malha_perfil.js';
import { caixaNaSelecao, definirCaixaDeCorte } from './caixa_corte.js';

const ARRASTO = 5;   // px: mais que isso entre apertar e soltar é pan, não clique

export function ligarMenuDeContexto(editor) {
  const alvo = editor && editor.el && editor.el.canvas;
  if (!alvo) return;
  let desce = null;
  alvo.addEventListener('pointerdown', (ev) => { if (ev.button === 2) desce = [ev.clientX, ev.clientY]; }, { capture: true });
  alvo.addEventListener('contextmenu', (ev) => {
    const d = desce;
    desce = null;
    if (d && Math.hypot(ev.clientX - d[0], ev.clientY - d[1]) > ARRASTO) return;
    ev.preventDefault();
    abrirMenuDeContexto(editor, ev.clientX, ev.clientY);
  });
}

/** Fecha o menu de contexto aberto, se houver. */
export function fecharMenuDeContexto() {
  const m = document.querySelector('.menu-contexto');
  if (m) m.remove();
}

/** As ocultas à mão (só da vista). */
function ocultas(doc) {
  if (!doc.ocultasAMao) doc.ocultasAMao = new Set();
  return doc.ocultasAMao;
}

/** Oculta as peças `ids` só na vista (Alt+H na seleção). */
export function ocultarNaVista(editor, ids) {
  const doc = editor.documento;
  if (!ids.length) { editor.dica('Selecione o que ocultar.'); return 0; }
  const o = ocultas(doc);
  for (const i of ids) o.add(i);
  editor.selecao.limpar();
  doc.notificarAparencia();
  editor.dica(`${ids.length} peça(s) oculta(s) na vista (o modelo não muda) — Alt+Shift+H ou botão direito no vazio: "Mostrar ocultas"`);
  return ids.length;
}

/** Traz de volta as ocultas à mão (Alt+Shift+H). */
export function mostrarOcultas(editor) {
  const doc = editor.documento;
  const n = doc.ocultasAMao ? doc.ocultasAMao.size : 0;
  if (!n) { editor.dica('Nenhuma peça oculta.'); return 0; }
  doc.ocultasAMao.clear();
  doc.notificarAparencia();
  editor.dica(`${n} peça(s) oculta(s) de volta à vista.`);
  return n;
}

/** Os itens do menu para o que está sob (x, y) na tela: [{rotulo, tecla, fazer, desligado}] ou '-' (separador). */
export function itensDoMenu(editor, x, y) {
  const doc = editor.documento, sel = editor.selecao;
  const r = editor.el.canvas.getBoundingClientRect();
  const sob = sel.sob(x - r.left, y - r.top);
  if (sob && sob.id && !sel.ids.has(sob.id)) sel.definir([sob.id]);
  const ids = [...sel.ids];
  const ents = ids.map(i => doc.get(i)).filter(Boolean);
  const nOcultas = doc.ocultasAMao ? doc.ocultasAMao.size : 0;
  const ferramenta = (id) => () => editor.ativarFerramenta(id);
  const itens = [];
  if (ents.length) {
    const e = ents[0];
    const titulo = ents.length > 1 ? `${ents.length} peças selecionadas`
      : (e.atributos && e.atributos.marcas && e.atributos.marcas.posicao ? `${e.atributos.marcas.posicao} · ` : '') + (e.perfil || e.nome || e.tipo);
    itens.push({ titulo });
    const perfil = ents.some(q => q.tipo === 'barra' || quadroDaMalha(q));
    itens.push(
      { rotulo: 'Selecionar semelhantes', fazer: () => { sel.semelhantes(e.id); editor.dica('Selecionados os objetos semelhantes.'); } },
      { rotulo: 'Zoom na seleção', fazer: () => editor.camera.zoomSelecao(ids) },
      { rotulo: editor._isolamento ? 'Voltar ao modelo' : 'Isolar', tecla: 'Alt+I', fazer: () => (editor._isolamento ? editor.sairDoIsolamento() : editor.isolarSelecao()) },
      { rotulo: 'Caixa de corte na seleção', fazer: () => caixaNaSelecao(editor) },
      { rotulo: 'Ocultar', tecla: 'Alt+H', fazer: () => ocultarNaVista(editor, ids) },
      '-',
      { rotulo: 'Mover', tecla: 'M', fazer: ferramenta('mover') },
      { rotulo: 'Copiar', tecla: 'K', fazer: ferramenta('copiar') },
      { rotulo: 'Girar', tecla: 'Q', fazer: ferramenta('girar') },
      { rotulo: 'Espelhar', tecla: 'W', fazer: ferramenta('espelhar') },
    );
    // a modelagem pela seleção (modulos/modelagem.js, do outro lado da divisão): copiar a peça para os outros eixos
    if (typeof editor.dialogoCopiarParaEixos === 'function') itens.push({ rotulo: 'Copiar para os eixos…', fazer: () => editor.dialogoCopiarParaEixos() });
    // a chapa: a tela de edição no 2D (sozinha ou com as peças em volta; o Concluir atualiza o 3D — pedido do usuário,
    // 15/10) e as alças de vértice, de lado e de furo no próprio 3D (a ferramenta Editar chapa)
    const ch = ents.length === 1 && (ents[0].tipo === 'chapa' || (ents[0].atributos && ents[0].atributos.tipo_ifc === 'IfcPlate')) ? ents[0] : null;
    if (ch && editor.projeto && typeof editor.abrirChapaNo2D === 'function') {
      itens.push({ rotulo: 'Editar chapa no 2D', fazer: () => editor.abrirChapaNo2D(ch, 'isolada') },
                 { rotulo: 'Editar chapa no 2D, no local', fazer: () => editor.abrirChapaNo2D(ch, 'local') });
    }
    if (ents.some(q => q.tipo === 'chapa')) itens.push({ rotulo: 'Alças da chapa no 3D', fazer: ferramenta('editar_chapa') });
    if (perfil) itens.push({ rotulo: 'Virar perfil', tecla: 'V', fazer: ferramenta('virar') },
                           { rotulo: 'Encaixar ponta', fazer: ferramenta('encaixar') });
    itens.push('-', { rotulo: 'Apagar', tecla: 'Del', fazer: () => editor.apagarSelecao() });
  } else {
    itens.push({ titulo: 'Modelo' },
      { rotulo: 'Selecionar tudo', tecla: 'Ctrl+A', fazer: () => sel.tudo() },
      { rotulo: 'Zoom na extensão', fazer: () => editor.camera.zoomExtensao() });
  }
  if (editor.cena && editor.cena.caixaCorte) {
    itens.push('-', { rotulo: 'Tirar a caixa de corte', fazer: () => { definirCaixaDeCorte(editor, null); editor.dica('Caixa de corte tirada: o modelo inteiro de volta.'); } });
  }
  if (nOcultas) {
    itens.push('-', { rotulo: `Mostrar ocultas (${nOcultas})`, tecla: 'Alt+Shift+H', fazer: () => mostrarOcultas(editor) });
  }
  return itens;
}

export function abrirMenuDeContexto(editor, x, y) {
  fecharMenuDeContexto();
  const itens = itensDoMenu(editor, x, y);
  const caixa = document.createElement('div');
  caixa.className = 'menu aberto menu-contexto';
  const lista = document.createElement('div');
  lista.className = 'menu-lista';
  lista.style.position = 'fixed';
  lista.style.left = `${x}px`;
  lista.style.top = `${y}px`;
  lista.style.minWidth = '210px';
  for (const it of itens) {
    if (it === '-') { lista.appendChild(document.createElement('hr')); continue; }
    if (it.titulo) {
      const t = document.createElement('div');
      t.className = 'menu-titulo';
      t.textContent = it.titulo;
      lista.appendChild(t);
      continue;
    }
    const b = document.createElement('button');
    b.type = 'button';
    const a = document.createElement('span');
    a.textContent = it.rotulo;
    b.appendChild(a);
    if (it.tecla) { const k = document.createElement('kbd'); k.textContent = it.tecla; b.appendChild(k); }
    b.addEventListener('click', (ev) => { ev.stopPropagation(); fecharMenuDeContexto(); it.fazer(); });
    lista.appendChild(b);
  }
  caixa.appendChild(lista);
  document.body.appendChild(caixa);
  // não sai da tela: perto da borda, abre para o outro lado
  const r = lista.getBoundingClientRect();
  if (r.right > innerWidth - 4) lista.style.left = `${Math.max(4, x - r.width)}px`;
  if (r.bottom > innerHeight - 4) lista.style.top = `${Math.max(4, y - r.height)}px`;
  const fora = (ev) => {
    if (ev.type === 'keydown' && ev.key !== 'Escape') return;
    if (ev.type === 'pointerdown' && caixa.contains(ev.target)) return;
    fecharMenuDeContexto();
    document.removeEventListener('pointerdown', fora, true);
    document.removeEventListener('keydown', fora, true);
    removeEventListener('wheel', fora, true);
  };
  setTimeout(() => {
    document.addEventListener('pointerdown', fora, true);
    document.addEventListener('keydown', fora, true);
    addEventListener('wheel', fora, true);
  }, 0);
  return caixa;
}
