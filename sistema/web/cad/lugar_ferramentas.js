// Onde fica cada ferramenta do CAD 2D (DECISÃO do usuário, 25/10, opção "Cotas e símbolos em cima": a barra da esquerda
// passava da altura da tela, e sobravam o espaço da barra de cima, entre os menus e o 2D | 3D, e o pé da coluna da
// direita):
//   • em cima, em linha, no espaço livre da barra: as cotas e os símbolos — na área de trabalho, na barra única de fora
//     (o CAD põe a faixa lá; some na vista só 3D); no CAD sozinho, no topo dele, depois do nome do desenho. O que não
//     cabe (a tela estreita) volta para a esquerda, do fim para o começo;
//   • na direita, embaixo dos elementos da disciplina: Medir, Dividir, Criar bloco, Inserir bloco;
//   • na esquerda: Nav, desenho e edição; os botões baixam (24 px) quando não cabem e, se ainda não couber, duas colunas.
// Com a faixa de ferramentas da área (Ver › Tela, web/faixa_ferramentas.js) fica tudo nas colunas, como antes: a faixa
// aciona os botões delas.

export const TOPO = [
  ['cotas', 'Cot', ['cota', 'cota_continua', 'cota_base', 'cota_angular', 'cota_raio', 'cota_diametro', 'cota_ordenada', 'cota_rapida', 'mover_cota', 'chamada']],
  ['simbolos', 'Sím', ['simbolo_solda', 'balao_marca', 'simbolo_nivel', 'chamada_detalhe', 'nuvem_revisao', 'grade_furos']],
];
export const DIREITA = [['Med', ['medir', 'dividir']], ['Blo', ['criar_bloco', 'inserir_bloco']]];

/** A faixa de ferramentas da área está ligada (Ver › Tela): as colunas ficam como antes. */
export function comFaixa() {
  try { return localStorage.getItem('metalica.ferramentas') === 'faixa' && document.documentElement.classList.contains('barra-unica'); } catch { return false; }
}

/** Os grupos da coluna da esquerda: [chave, rótulo, [classes]] — sem as da direita; as de cima no fim, nos grupos delas
 *  (aparecem só quando não cabem em cima). Com a faixa, os grupos de antes. */
export function gruposDaEsquerda(FERRAMENTAS, GRUPOS) {
  if (comFaixa()) return GRUPOS.map(([g, r]) => [g, r, FERRAMENTAS.filter(f => f.grupo === g)]);
  const fora = new Set([...TOPO.flatMap(t => t[2]), ...DIREITA.flatMap(d => d[1])]);
  const porId = new Map(FERRAMENTAS.map(f => [f.id, f]));
  const grupos = GRUPOS.map(([g, r]) => [g, r, FERRAMENTAS.filter(f => f.grupo === g && !fora.has(f.id))]).filter(g => g[2].length);
  for (const [g, r, ids] of TOPO) grupos.push([`topo-${g}`, r, ids.map(i => porId.get(i)).filter(Boolean)]);
  return grupos;
}

const ESTILO_TOPO = `
.ferramentas-topo { display: flex; align-items: center; flex: 1 1 0; min-width: 0; overflow: hidden; gap: 0; margin: 0 6px; height: 100%; }
.ferramentas-topo .ft-grupo { display: flex; align-items: center; gap: 1px; padding: 0 5px; flex-shrink: 0; }
.ferramentas-topo .ft-grupo + .ft-grupo { border-left: 1px solid rgba(255,255,255,.22); }
.ferramentas-topo .ft-bt { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 27px; padding: 0;
  background: transparent; color: #e2e8f0; border: 1px solid transparent; border-radius: 5px; cursor: pointer; flex-shrink: 0; }
.ferramentas-topo .ft-bt svg { width: 18px; height: 18px; pointer-events: none; }
.ferramentas-topo .ft-bt:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.22); }
.ferramentas-topo .ft-bt[aria-pressed="true"] { background: #fff; color: #0b3d91; border-color: #fff; }
.ferramentas-topo .ft-bt[hidden], .ferramentas-topo .ft-grupo[hidden] { display: none; }
body.v-3d .ferramentas-topo { display: none; }
/* a barra de etapas (web/etapas.js) ordena a linha da área pelo order: os menus são o 3, a vista o 5 */
.area-topo .ferramentas-topo { order: 4; }
`;

/** Põe as cotas e os símbolos na barra de cima (a de fora, na área de trabalho) e mede o que cabe. */
export function instalarTopo(cad) {
  if (comFaixa()) return;
  let alvo = document, depois = document.querySelector('header.topo .nome-modelo');
  try {
    const p = window.parent;
    if (p !== window && document.documentElement.classList.contains('barra-unica') && p.document.getElementById('menus-unicos')) {
      alvo = p.document; depois = alvo.getElementById('menus-unicos');
    }
  } catch { /* outra origem: no topo daqui */ }
  if (!depois) return;
  const janela = alvo.defaultView;
  if (!alvo.getElementById('estilo-ferramentas-topo')) {
    const st = alvo.createElement('style'); st.id = 'estilo-ferramentas-topo'; st.textContent = ESTILO_TOPO;
    alvo.head.append(st);
  }
  const velha = alvo.getElementById('ferramentas-2d-topo');
  if (velha) velha.remove();                                   // a de uma carga anterior do 2D
  const faixa = alvo.createElement('div');
  faixa.id = 'ferramentas-2d-topo'; faixa.className = 'ferramentas-topo';
  faixa.setAttribute('role', 'toolbar'); faixa.setAttribute('aria-label', 'Cotas e símbolos do desenho 2D');
  const botoes = [];
  for (const [g, rotulo, ids] of TOPO) {
    const grupo = alvo.createElement('span');
    grupo.className = 'ft-grupo'; grupo.dataset.grupo = g;
    for (const id of ids) {
      const f = cad.ferramentas.get(id), orig = cad.el.barra.querySelector(`.ferramenta[data-ferramenta="${id}"]`);
      if (!f || !orig) continue;
      const b = alvo.createElement('button');
      b.type = 'button'; b.className = 'ft-bt'; b.dataset.ferramentaTopo = id; b.title = orig.title;
      b.setAttribute('aria-pressed', 'false');
      b.innerHTML = f.constructor.icone || '';
      b.addEventListener('click', () => { cad.ativarFerramenta(id); try { window.focus(); } catch { /* */ } });
      grupo.append(b);
      botoes.push({ id, b, orig, grupo: g });
    }
    if (grupo.children.length) faixa.append(grupo);
  }
  depois.after(faixa);

  /** o que cabe fica em cima; o resto volta para a esquerda (do fim para o começo, para a ordem não embaralhar) */
  const medir = () => {
    for (const x of botoes) x.b.hidden = false;
    for (const g of faixa.children) g.hidden = false;
    const visivel = faixa.offsetParent !== null || janela.getComputedStyle(faixa).display !== 'none';
    const limite = faixa.getBoundingClientRect().right;
    let corta = !visivel;
    for (const x of botoes) {
      if (!corta && x.b.getBoundingClientRect().right > limite + 0.5) corta = true;
      x.b.hidden = corta;
    }
    for (const g of faixa.children) g.hidden = ![...g.children].some(b => !b.hidden);
    for (const x of botoes) x.orig.hidden = !x.b.hidden;
    for (const [g] of TOPO) {
      const r = cad.el.barra.querySelector(`.grupo-rotulo[data-grupo="topo-${g}"]`);
      if (r) r.hidden = !botoes.some(x => x.grupo === g && x.b.hidden);
    }
    ajustarColuna(cad.el.barra, true);
  };
  let pedido = 0;
  const pedir = () => { if (!pedido) pedido = janela.requestAnimationFrame(() => { pedido = 0; medir(); }); };
  try { new janela.ResizeObserver(pedir).observe(faixa); } catch { janela.addEventListener('resize', pedir); }
  // a vista só 3D esconde a faixa: o corpo da área troca de classe (v-2d, v-3d, v-ambos)
  try { new janela.MutationObserver(pedir).observe(alvo.body, { attributes: true, attributeFilter: ['class'] }); } catch { /* */ }
  if (alvo !== document) window.addEventListener('pagehide', () => faixa.remove());
  cad._marcarTopo = (id) => { for (const x of botoes) x.b.setAttribute('aria-pressed', String(x.id === id)); };
  medir();
}

/** As ferramentas da direita, embaixo dos elementos da disciplina (estrutura.js chama a cada troca de disciplina:
 *  os mesmos botões, sem os recriar). */
export function prepararDireita(cad, criarBotao) {
  if (comFaixa()) return;
  const nos = [];
  for (const [rotulo, ids] of DIREITA) {
    const r = document.createElement('div');
    r.className = 'grupo-rotulo'; r.textContent = rotulo;
    nos.push(r);
    for (const id of ids) { const b = criarBotao(id); if (b) nos.push(b); }
  }
  cad._anexarNaDireita = (barra) => { barra.append(...nos); ajustarColuna(barra, false); };
  if (cad.el.barraDisciplina && cad.el.barraDisciplina.children.length) cad._anexarNaDireita(cad.el.barraDisciplina);
}

/** A coluna cabe na altura: botões de 34 px; se não, de 24 px; se ainda não (e `duas` pode), duas colunas de 34 px e,
 *  por último, duas de 24 px com os rótulos dos grupos num traço. */
export function ajustarColuna(barra, duas) {
  if (!barra || barra.offsetParent === null) return;
  const niveis = duas ? [[], ['compacta'], ['duas-colunas'], ['duas-colunas', 'compacta']] : [[], ['compacta']];
  for (const n of niveis) {
    barra.classList.remove('compacta', 'duas-colunas');
    barra.classList.add(...n);
    if (barra.scrollHeight <= barra.clientHeight + 1) return;
  }
}

/** Acompanha a altura das duas colunas (a janela que muda de tamanho). */
export function vigiarColunas(cad) {
  if (comFaixa()) return;
  let pedido = 0;
  const pedir = () => {
    if (pedido) return;
    pedido = requestAnimationFrame(() => { pedido = 0; ajustarColuna(cad.el.barra, true); ajustarColuna(cad.el.barraDisciplina, false); });
  };
  try { new ResizeObserver(pedir).observe(cad.el.palco); } catch { window.addEventListener('resize', pedir); }
}
