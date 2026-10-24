// A linha de comando do CAD 2D, como a do AutoCAD (usuário, 24/10: "ter esse menu de comandos" — a imagem do AutoCAD com
// "TR" digitado e a do CADCraft com a lista que aparece; DECISÃO: valem os atalhos do AutoCAD). A caixa do rodapé (#medida)
// recebe o comando e as medidas: a letra digitada no desenho vai para ela, a lista mostra os comandos que começam com o
// texto (o atalho do AutoCAD, o nome em inglês e o nome em português), e Enter ou espaço executa. O que não é comando
// vai para a ferramenta (a medida, "4x3", "M16"…), como antes.

/** Os comandos de cada ferramenta: os atalhos do AutoCAD (acad.pgp) primeiro, depois o nome em inglês. As ferramentas
 *  só deste programa ficam com as duas letras que já tinham, e as duas letras de antes que não brigam com o AutoCAD
 *  continuam valendo (DN, DR, DO, DB, DQ, QB, AL, CH); o DI é o DIST do AutoCAD (a cota de diâmetro é DDI). */
export const ATALHOS = {
  linha: ['L', 'LINE'], polilinha: ['PL', 'PLINE'], retangulo: ['REC', 'RECTANG'], circulo: ['C', 'CIRCLE'], arco: ['A', 'ARC'],
  texto: ['T', 'DT', 'MT', 'TEXT'], chamada: ['LE', 'MLD', 'LEADER'],
  cota: ['DLI', 'DAL', 'D', 'DIM'], cota_continua: ['DCO', 'DC', 'DIMCONTINUE'], cota_angular: ['DAN', 'DN', 'DIMANGULAR'],
  cota_raio: ['DRA', 'DR', 'DIMRADIUS'], cota_diametro: ['DDI', 'DIMDIAMETER'], cota_ordenada: ['DOR', 'DO', 'DIMORDINATE'],
  cota_base: ['DBA', 'DB', 'DIMBASELINE'], cota_rapida: ['QDIM', 'DQ'], mover_cota: ['MOVERCOTA'],
  esticar: ['S', 'STRETCH'], hachura: ['H', 'BH', 'HATCH'], mover: ['M', 'MOVE'], copiar: ['CO', 'CP', 'COPY'],
  girar: ['RO', 'ROTATE'], escalar: ['SC', 'SCALE'], espelhar: ['MI', 'MIRROR'], copiar_propriedades: ['MA', 'MATCHPROP'],
  apagar: ['E', 'ERASE'], explodir: ['X', 'EXPLODE'], juntar: ['J', 'JOIN'], aparar: ['TR', 'TRIM'], estender: ['EX', 'EXTEND'],
  concordar: ['F', 'FILLET'], chanfro: ['CHA', 'CH', 'CHAMFER'], quebrar: ['BR', 'QB', 'BREAK'], alongar: ['LEN', 'AL', 'LENGTHEN'],
  matriz: ['AR', 'ARRAY'], offset: ['O', 'OFFSET'], dividir: ['DIV', 'DIVIDE'], medir: ['DI', 'DIST', 'MEA', 'MEASUREGEOM'],
  zoom_janela: ['ZW'], grade_furos: ['GF'], simbolo_solda: ['SD'], balao_marca: ['BM'], simbolo_nivel: ['NV'],
  chamada_detalhe: ['CD'], nuvem_revisao: ['REVCLOUD', 'NR'], corte: ['CORTE'],
};

/** Os comandos que não são ferramenta: o que fazem no CAD. */
const EXTRAS = [
  { atalhos: ['Z', 'ZOOM', 'ZE'], nome: 'Zoom no desenho todo', fazer: (cad) => cad.tela.enquadrar() },
  { atalhos: ['ZP'], nome: 'Zoom anterior', fazer: (cad) => cad.zoomAnterior() },
  { atalhos: ['FROM', 'FRO'], nome: 'A partir de (base + deslocamento)', transparente: true, fazer: (cad) => cad.comecarFrom() },
  { atalhos: ['U', 'UNDO'], nome: 'Desfazer (Ctrl+Z)', fazer: (cad) => cad.desfazer() },
  { atalhos: ['REDO'], nome: 'Refazer (Ctrl+Y)', fazer: (cad) => cad.refazer() },
  { atalhos: ['PLOT', 'PRINT'], nome: 'Imprimir (Ctrl+P)', fazer: (cad) => cad.dialogoImprimir() },
  { atalhos: ['QSAVE', 'SAVE'], nome: 'Salvar (Ctrl+S)', fazer: (cad) => cad.salvar() },
  { atalhos: ['REVISOES', 'REV'], nome: 'Revisões das pranchas…', fazer: (cad) => cad.dialogoRevisoes() },
  { atalhos: ['LA', 'LAYER'], nome: 'Camadas (o painel)', fazer: () => {
    const p = document.querySelector('.painel[data-painel="camadas"]');
    if (p) { p.classList.remove('fechado'); p.scrollIntoView({ block: 'nearest' }); }
  } },
];

const semAcento = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();

/** A tabela dos comandos do CAD: {atalhos, nome, ferramenta | fazer}. */
export function tabelaDeComandos(ferramentas) {
  const out = [];
  for (const F of ferramentas) {
    const at = ATALHOS[F.id];
    if (at) out.push({ atalhos: at, nome: F.nome, ferramenta: F.id });
  }
  return out.concat(EXTRAS);
}

/** O comando com o atalho (ou o nome em inglês) exatamente igual ao texto; senão null. */
export function comandoExato(tabela, texto) {
  const t = semAcento(texto).trim();
  if (!t) return null;
  return tabela.find(c => c.atalhos.includes(t)) || null;
}

/**
 * Os comandos para a lista, na ordem do AutoCAD: o atalho igual ao texto primeiro, depois os atalhos que começam com
 * ele (os mais curtos antes), depois o nome em português que tem o texto ("apar" acha o Aparar).
 */
export function buscarComandos(tabela, texto, max = 8) {
  const t = semAcento(texto).trim();
  if (!t || /[^A-Z]/.test(t.replace(/\s/g, ''))) return [];
  const pontos = [];
  for (const c of tabela) {
    let melhor = Infinity, pelo = '';
    for (const a of c.atalhos) {
      if (a === t) { melhor = 0; pelo = a; break; }
      if (a.startsWith(t) && 1 + a.length / 100 < melhor) { melhor = 1 + a.length / 100; pelo = a; }
    }
    if (melhor === Infinity && t.length >= 3 && semAcento(c.nome).includes(t)) { melhor = 3; pelo = c.atalhos[0]; }
    if (melhor < Infinity) pontos.push({ c, melhor, pelo });
  }
  pontos.sort((x, y) => x.melhor - y.melhor);
  return pontos.slice(0, max).map(p => ({ ...p.c, pelo: p.pelo }));
}

/** O rótulo da linha da lista: "TR (TRIM)" ou "Z (ZOOM)" — o atalho e o nome em inglês, como no CADCraft. */
export function rotuloDoComando(c) {
  const ingles = c.atalhos.find(a => a.length > 3 && a !== c.pelo);
  return ingles && ingles !== c.pelo ? `${c.pelo} (${ingles})` : c.pelo;
}

/**
 * A lista que abre em cima da caixa enquanto se digita. `cad.el.medida` é a caixa. Devolve {atualizar, mover, escolhida,
 * fechar}: o teclado (cad.js) chama `mover(±1)` nas setas e `escolhida()` no Enter.
 */
export function instalarLista(cad, tabela) {
  const caixa = cad.el.medida;
  const lista = document.createElement('ul');
  lista.className = 'lista-comandos';
  lista.hidden = true;
  caixa.closest('label, .medidas, footer').append(lista);
  let itens = [], i = -1;
  const pintar = () => {
    lista.replaceChildren(...itens.map((c, k) => {
      const li = document.createElement('li');
      li.className = k === i ? 'on' : '';
      const a = document.createElement('b'); a.textContent = rotuloDoComando(c);
      const n = document.createElement('span'); n.textContent = c.nome;
      li.append(a, n);
      // o clique na lista executa (o mousedown não tira o foco da caixa antes da hora)
      li.addEventListener('mousedown', (ev) => { ev.preventDefault(); caixa.value = c.pelo; cad.executarLinhaDeComando(); });
      return li;
    }));
    lista.hidden = !itens.length;
  };
  const api = {
    atualizar() { itens = buscarComandos(tabela, caixa.value); i = itens.length ? 0 : -1; pintar(); },
    mover(d) { if (!itens.length) return false; i = (i + d + itens.length) % itens.length; pintar(); return true; },
    escolhida() { return !lista.hidden && i >= 0 ? itens[i] : null; },
    fechar() { itens = []; i = -1; pintar(); },
  };
  caixa.addEventListener('input', () => api.atualizar());
  caixa.addEventListener('blur', () => api.fechar());
  return api;
}
