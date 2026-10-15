// Guia rápido das ferramentas (15/10, pedido do usuário: "um acesso rápido para o usuário conferir todas as ferramentas
// de edição disponíveis, os atalhos, como usar … acho que nem todas as ferramentas estão nesse menu lateral").
//
// Abre com F1 (no 3D) ou pelo menu ? › Guia rápido das ferramentas. Lista cada ferramenta registrada, por grupo, com o
// atalho, o como usar e o aviso das que não estão à vista na barra lateral; um clique na linha abre a ferramenta. Depois,
// os comandos de modelar pela seleção (que ficam nos menus) e as teclas que valem em todas as ferramentas. A busca filtra.

import { GRUPOS } from '../ferramentas/indice.js';

//: como usar, curto — o passo a passo de cada ferramenta (a dica dela fica de reserva)
const COMO = {
  selecionar: 'Clique escolhe; Shift soma, Ctrl alterna. Arrastar da esquerda para a direita pega o que está inteiro dentro; da direita para a esquerda, também o que encosta. Duplo clique: os semelhantes (Shift + duplo clique também); na chapa, o duplo clique abre a edição dela no 2D. Tab, com o mouse parado, passa para a peça de trás. Na barra selecionada, arraste as alças das pontas para esticar.',
  linha: 'Clique ponto a ponto; digite o comprimento a qualquer momento (as setas travam o eixo). Fechar no ponto inicial faz a face; Enter ou duplo clique terminam.',
  retangulo: 'Clique um canto e o outro, ou digite "largura;altura". Logo depois, outra medida corrige o retângulo.',
  circulo: 'Clique o centro e digite o raio. "24s" muda o número de lados. Logo depois, outro raio corrige.',
  poligono: 'Centro e raio, como o círculo; "6s" o número de lados; Tab alterna inscrito/circunscrito.',
  arco: 'Clique o início e o fim (ou digite a corda) e depois o bojo, ou digite a flecha. "12s" o número de segmentos.',
  plano: 'Clique numa face (a água da cobertura, a fachada) e o ponto solto passa a cair no plano dela. Z volta ao chão.',
  mover: 'Selecione, clique a origem e o destino, ou digite a distância (as setas travam o eixo). Ctrl copia; depois da cópia, "*5" repete e "/3" divide. Logo depois, outra distância corrige.',
  copiar: 'Com a seleção, clique a referência e cada clique cola uma cópia medida dela; ou digite a distância ou "dx;dy;dz".',
  girar: 'Selecione; ↑ trava o giro na horizontal; clique o centro, a direção de 0° e o ângulo (ou digite). Ctrl copia; "*4" o array radial. Logo depois, outro ângulo corrige.',
  escalar: 'Selecione e clique numa alça da caixa: canto escala por igual, meio de face só naquele eixo. Digite o fator ("2") ou a medida final.',
  espelhar: 'Selecione; dois cliques dão o plano vertical do espelho (X, Y ou Z: pelo centro). Sai a cópia espelhada; Ctrl move em vez de copiar.',
  pushpull: 'Clique numa face e mova, ou digite a distância. Na chapa: a face de cima muda a espessura, o lado estica. Na barra: a ponta. Duplo clique repete a última; logo depois, outra distância corrige.',
  offset: 'Clique numa face e mova para dentro ou para fora, ou digite a distância: sai o contorno paralelo.',
  medir: 'Clique dois pontos para a medida com ΔX/ΔY/ΔZ; Enter cria a linha-guia. Começando numa aresta, a guia é paralela a ela: digite o afastamento. O painel apaga as guias.',
  cotar: 'Clique dois pontos e afaste; ou um clique numa aresta já cota a aresta inteira. A cota fica presa às peças e acompanha quando elas mudam.',
  secao: 'X, Y ou Z: o plano de corte pelo meio do modelo (ou clique numa face). Digite para deslocar; Tab inverte; Delete tira; G gera o desenho do corte.',
  barra: 'Clique o início e o fim (ou digite o comprimento); a barra continua da ponta. Antes do 1º clique ↑↓ trocam o perfil; depois, ↑ trava Z (pilar). O painel tem perfil, papel, rotação e o ponto de inserção.',
  chapa: 'Clique na face (o plano) e o canto oposto, ou digite "largura;altura". Depois: um número muda a espessura e "40;60" põe um furo a 40×60 do canto.',
  parafuso: 'Clique na face onde entra: o comprimento sai da pega, nos comprimentos comerciais. O painel tem diâmetro, classe e o padrão (linhas × colunas). Com parafusos selecionados: "Recalcular pela pega".',
  furo: 'Clique na face: o furo atravessa só aquela parede. Digite o diâmetro ("17,5") ou o parafuso ("M16").',
  virar: 'Clique no perfil: gira 90° no próprio eixo (pelo meio da seção); Shift ao contrário, Ctrl 180°. Digite o passo (45).',
  encaixar: 'Clique na barra e na face em que a ponta deve encostar: corta em ângulo ou estica até ela. Shift soma o plano (bico); Delete tira os cortes.',
  estender: 'Clique na barra (perto da ponta) e na outra barra: a ponta vai até a face dela (Shift: até o eixo). Digite a folga antes do 2º clique.',
  dividir: 'Passe o mouse e clique para dividir ali; ou digite a distância da ponta ("3000") ou "/3" para partes iguais.',
  recortar: 'Clique na barra perto da ponta e na peça em que ela encaixa: sai o recorte da mesa. Ou digite "comprimento;altura"; "ch10" faz o chanfro.',
  enrijecedor: 'Um clique na alma do perfil: as chapas entre as mesas, dos dois lados. Digite a distância da ponta.',
  editar_chapa: 'As alças da chapa no 3D (o botão direito na chapa também tem "Editar chapa no 2D"). Com a chapa escolhida: clique num vértice e onde ele vai (ou "dx;dy"); o meio do lado cria um vértice; o furo também anda. "ch20" chanfra, "r30" arredonda.',
};

//: os comandos de modelar pela seleção, que ficam nos menus (a ação do editor e o como usar)
const COMANDOS = [
  ['modelar-pilares', 'Pilares nos eixos', 'Pilares nos cruzamentos dos eixos gravados, da base ao topo pelos níveis.'],
  ['modelar-bases', 'Bases nos pilares dos eixos', 'Placa de base e chumbadores nos pilares dos eixos.'],
  ['modelar-viga', 'Viga entre pilares', 'Selecione os pilares: a viga entre eles, na altura escolhida.'],
  ['modelar-trelica', 'Treliça entre banzos', 'Selecione os dois banzos: montantes e diagonais (Warren, Pratt, Howe) com o encaixe.'],
  ['modelar-tercas', 'Terças por espaçamento', 'Selecione as tesouras ou vigas: as terças distribuídas pelo espaçamento.'],
  ['modelar-contravento', 'Contraventamento em X', 'Selecione dois pilares ou tesouras: o X entre eles.'],
  ['modelar-longarinas', 'Longarinas de fechamento', 'As longarinas de fechamento entre os pilares.'],
  ['modelar-correntes', 'Correntes entre terças', 'As correntes (e o tirante de cumeeira) entre as terças.'],
  ['modelar-mao-francesa', 'Mão-francesa', 'A mão-francesa entre a terça e a tesoura.'],
  ['copiar-para-eixos', 'Copiar para os eixos', 'A seleção copiada para os outros eixos (também no botão direito).'],
];

//: as teclas que valem em todas as ferramentas
const TECLAS = [
  ['Espaço', 'volta à Seleção'], ['Esc', 'cancela o passo / solta a ferramenta'],
  ['digitar um número', 'a medida, a qualquer momento (e logo depois de terminar, corrige o último)'],
  ['→  ←  ↑', 'travam o eixo X, Y e Z (↓ solta)'], ['Shift', 'trava o eixo ou a aresta que o snap mostra'],
  ['parar o mouse num canto', 'o ponto fica lembrado: depois o snap alinha com ele (e com dois: o X de um e o Y do outro)'],
  ['botão direito', 'o menu da peça: semelhantes, zoom, isolar, caixa de corte, ocultar, mover…'],
  ['Tab (na Seleção)', 'a peça de trás, com o mouse parado'],
  ['Alt+H  /  Alt+Shift+H', 'oculta a seleção / mostra as ocultas'], ['Alt+I', 'isola a seleção (de novo: volta ao modelo)'],
  ['Alt+C  /  Alt+P  /  Alt+T', 'seleciona pela camada / pelo perfil / pelo tipo da primeira'],
  ['1 a 7', 'vistas: topo, frente, trás, esquerda, direita, inferior, isométrica'],
  ['Alt+1 a Alt+9  /  Alt+0', 'vai à vista salva / salva a vista'],
  ['Ctrl+Z  /  Ctrl+Y', 'desfaz / refaz'], ['Ctrl+S', 'grava agora'], ['Ctrl+C  /  Ctrl+V', 'copia / cola'],
  ['Ctrl+A', 'seleciona tudo'], ['Delete', 'apaga a seleção'], ['F9', 'calcula a estrutura'], ['Ctrl+K', 'busca'], ['F1', 'este guia'],
];

const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** A ferramenta está à vista na barra lateral (o botão existe e aparece sem rolar a barra)? */
function naBarra(doc, id) {
  const b = doc.querySelector(`#barra-ferramentas [data-id="${id}"]`);
  if (!b || !b.offsetParent) return false;
  // o que a barra mostra sem rolar (numa janela baixa ela rola, e as do fim ficam escondidas)
  const r = b.getBoundingClientRect(), caixa = doc.querySelector('#barra-ferramentas').getBoundingClientRect();
  const baixo = Math.min(caixa.bottom, doc.defaultView.innerHeight || caixa.bottom);
  return r.height > 0 && r.top >= Math.max(0, caixa.top) - 1 && r.bottom <= baixo + 1;
}

function el(doc, tag, props = {}, ...filhos) {
  const e = doc.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'texto') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const f of filhos) if (f) e.append(f);
  return e;
}

/** Abre o guia (ou fecha, se já está aberto). */
export function abrirGuiaFerramentas(editor) {
  const doc = document;
  const velho = doc.getElementById('guia-ferramentas');
  if (velho) { velho.remove(); return null; }
  const fundo = el(doc, 'div', { id: 'guia-ferramentas', class: 'guia-fundo' });
  const caixa = el(doc, 'div', { class: 'guia-caixa', role: 'dialog', 'aria-label': 'Guia rápido das ferramentas' });
  const busca = el(doc, 'input', { type: 'search', placeholder: 'buscar (ex.: parafuso, esticar, eixo, cota)…', class: 'guia-busca' });
  const corpo = el(doc, 'div', { class: 'guia-corpo' });
  const fechar = () => { fundo.remove(); doc.removeEventListener('keydown', tecla, true); };
  const tecla = (ev) => { if (ev.key === 'Escape' || ev.key === 'F1') { ev.preventDefault(); ev.stopPropagation(); fechar(); } };
  caixa.append(
    el(doc, 'div', { class: 'guia-cab' },
      el(doc, 'b', { texto: 'Guia rápido das ferramentas' }),
      el(doc, 'span', { class: 'guia-sub', texto: 'clique numa ferramenta para usar · F1 abre e fecha' }),
      el(doc, 'button', { type: 'button', texto: 'Fechar (Esc)', onclick: fechar })),
    busca, corpo);
  fundo.append(caixa);
  fundo.addEventListener('mousedown', (ev) => { if (ev.target === fundo) fechar(); });

  const ferramentas = [...(editor.ferramentas ? editor.ferramentas.values() : [])];
  const preencher = () => {
    const q = norm(busca.value);
    corpo.replaceChildren();
    const casa = (...t) => !q || norm(t.join(' ')).includes(q);
    let fora = 0;
    for (const [grupo, rotulo] of GRUPOS) {
      const lista = ferramentas.filter(F => (F.grupo || 'edicao') === grupo && casa(F.nome, F.atalho, COMO[F.id], F.dica, rotulo));
      if (!lista.length) continue;
      corpo.append(el(doc, 'h4', { texto: rotulo }));
      for (const F of lista) {
        const visivel = naBarra(doc, F.id);
        if (!visivel) fora++;
        const linha = el(doc, 'button', { type: 'button', class: 'guia-linha', title: 'Usar esta ferramenta', onclick: () => { fechar(); editor.ativarFerramenta(F.id); } },
          el(doc, 'span', { class: 'guia-icone', html: F.icone || '' }),
          el(doc, 'span', { class: 'guia-nome' }, el(doc, 'b', { texto: F.nome }),
            visivel ? null : el(doc, 'small', { class: 'guia-fora', texto: 'fora da barra lateral' })),
          el(doc, 'kbd', { texto: F.atalho || '—' }),
          el(doc, 'span', { class: 'guia-como', texto: COMO[F.id] || F.dica || '' }));
        linha.dataset.id = F.id;
        corpo.append(linha);
      }
    }
    const cmds = COMANDOS.filter(([acao, nome, como]) => doc.querySelector(`[data-acao="${acao}"]`) && casa(nome, como, 'modelar seleção'));
    if (cmds.length) {
      corpo.append(el(doc, 'h4', { texto: 'Modelar pela seleção (comandos)' }));
      for (const [acao, nome, como] of cmds) {
        corpo.append(el(doc, 'button', { type: 'button', class: 'guia-linha', title: 'Abrir este comando',
          onclick: () => { fechar(); const b = doc.querySelector(`[data-acao="${acao}"]`); if (b) b.click(); } },
          el(doc, 'span', { class: 'guia-icone', texto: '▸' }),
          el(doc, 'span', { class: 'guia-nome' }, el(doc, 'b', { texto: nome + '…' })),
          el(doc, 'kbd', { texto: '—' }),
          el(doc, 'span', { class: 'guia-como', texto: como })));
      }
    }
    const teclas = TECLAS.filter(([k, o]) => casa(k, o, 'tecla atalho'));
    if (teclas.length) {
      corpo.append(el(doc, 'h4', { texto: 'Teclas que valem em todas as ferramentas' }));
      const t = el(doc, 'div', { class: 'guia-teclas' });
      for (const [k, o] of teclas) t.append(el(doc, 'kbd', { texto: k }), el(doc, 'span', { texto: o }));
      corpo.append(t);
    }
    if (fora && !q) {
      corpo.prepend(el(doc, 'p', { class: 'guia-aviso', texto: `${fora} ferramenta(s) não cabem na barra lateral nesta tela: use por aqui, pelo atalho ou pelo menu do botão direito.` }));
    }
    if (!corpo.children.length) corpo.append(el(doc, 'p', { class: 'guia-aviso', texto: 'Nada com essa busca.' }));
  };
  busca.addEventListener('input', preencher);
  busca.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { const p = corpo.querySelector('.guia-linha'); if (p) p.click(); }
    ev.stopPropagation();
  });
  doc.body.append(fundo);
  doc.addEventListener('keydown', tecla, true);
  preencher();
  busca.focus();
  return fundo;
}

/** F1 abre o guia (e o deixa para a barra de cima chamar: window.abrirGuiaFerramentas). */
export function ligarGuia(editor) {
  window.abrirGuiaFerramentas = () => abrirGuiaFerramentas(editor);
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'F1' || document.getElementById('guia-ferramentas')) return;
    ev.preventDefault();
    abrirGuiaFerramentas(editor);
  });
  estilo();
}

function estilo() {
  if (document.getElementById('guia-ferramentas-css')) return;
  const s = document.createElement('style');
  s.id = 'guia-ferramentas-css';
  s.textContent = `
.guia-fundo { position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,.35); display: flex; align-items: flex-start; justify-content: center; padding: 5vh 16px; }
.guia-caixa { background: var(--painel, #fff); color: var(--texto, #111); border: 1px solid var(--borda, #ccc); border-radius: 10px; box-shadow: var(--sombra-menu, 0 8px 30px rgba(0,0,0,.3));
  width: min(980px, 100%); max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; }
.guia-cab { display: flex; align-items: baseline; gap: 12px; padding: 12px 16px 6px; }
.guia-cab b { font-size: 15px; } .guia-sub { color: var(--texto3, #888); font-size: 12px; flex: 1; }
.guia-cab button { background: none; border: 1px solid var(--borda, #ccc); color: inherit; border-radius: 6px; padding: 3px 10px; cursor: pointer; }
.guia-busca { margin: 4px 16px 8px; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--borda, #ccc); background: var(--campo-fundo, transparent); color: inherit; font-size: 13px; }
.guia-corpo { overflow-y: auto; padding: 0 16px 16px; }
.guia-corpo h4 { margin: 14px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--texto3, #888); }
.guia-linha { display: grid; grid-template-columns: 26px 190px 70px 1fr; gap: 10px; align-items: start; width: 100%; text-align: left;
  background: none; border: 0; border-radius: 6px; padding: 6px 6px; color: inherit; cursor: pointer; font-size: 12.5px; }
.guia-linha:hover { background: var(--azul-fraco, #e8f0fe); }
.guia-icone svg { width: 20px; height: 20px; } .guia-nome small { display: block; color: #d97706; font-size: 11px; }
.guia-linha kbd, .guia-teclas kbd { font-family: var(--mono, monospace); font-size: 11.5px; justify-self: start; }
.guia-como { color: var(--texto2, inherit); line-height: 1.35; }
.guia-teclas { display: grid; grid-template-columns: 210px 1fr; gap: 5px 12px; font-size: 12.5px; padding: 4px 6px; }
.guia-aviso { margin: 8px 0 0; padding: 7px 10px; border-radius: 6px; background: var(--azul-fraco, #fff7e6); font-size: 12.5px; }
@media (max-width: 700px) { .guia-linha { grid-template-columns: 26px 1fr 60px; } .guia-como { grid-column: 2 / -1; } .guia-teclas { grid-template-columns: 1fr; } }
`;
  document.head.append(s);
}
