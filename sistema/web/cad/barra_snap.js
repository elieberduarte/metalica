// Os botões do snap no rodapé, como a barra de status do AutoCAD (usuário, 25/10: "no autocad tem a ferramenta snap (F3)
// que pode habilitar e desabilitar isso, e configurar quais pontos de snap o sistema quer buscar"): SNAP liga e desliga
// o snap de objeto (F3) e a setinha abre a lista dos tipos; ORTO (F8), POLAR (F10) e RASTR. (F11) ao lado. Os mesmos
// estados do painel SNAP da direita (cad._painelSnap redesenha os dois).

/** Os tipos do snap de objeto, na ordem da lista do AutoCAD: [chave em snap.ativos, rótulo, dica]. */
export const TIPOS_SNAP = [
  ['extremidade', 'Extremidade', 'As pontas das linhas e dos arcos e os vértices das polilinhas (ENDpoint)'],
  ['meio', 'Meio', 'O meio de cada trecho (MIDpoint)'],
  ['centro', 'Centro', 'O centro do círculo e do arco (CENter)'],
  ['centro_geometrico', 'Centro geométrico', 'O centro da área da polilinha fechada: a chapa, o furo oblongo, o recorte (GCEn)'],
  ['no', 'Nó', 'A marca de ponto do Dividir (NODe)'],
  ['quadrante', 'Quadrante', 'Os pontos a 0°, 90°, 180° e 270° do círculo e do arco (QUAdrant)'],
  ['interseccao', 'Interseção', 'Onde dois objetos se cruzam (INTersection)'],
  ['extensao', 'Extensão', 'A continuação da linha: pare o cursor na ponta e siga adiante (EXTension)'],
  ['insercao', 'Inserção', 'O ponto de inserção do bloco e do texto (INSertion)'],
  ['perpendicular', 'Perpendicular', 'O pé da perpendicular a partir do último ponto (PERpendicular)'],
  ['tangente', 'Tangente', 'O ponto de tangência no círculo e no arco a partir do último ponto (TANgent)'],
  ['sobre', 'Sobre a linha', 'O ponto do objeto mais perto do cursor (NEArest)'],
  ['paralelo', 'Paralelo', 'Paralelo a uma linha: pare o cursor sobre ela e siga do último ponto (PARallel)'],
  ['grade', 'Grade', 'Os nós da grade (F9)'],
];

const ESTILO = `
.barra-snap { display: inline-flex; align-items: center; gap: 2px; margin-left: 12px; position: relative; user-select: none; }
.barra-snap button { font: 600 10.5px var(--mono); letter-spacing: .3px; color: var(--texto3); background: transparent;
  border: 1px solid var(--borda); border-radius: 3px; padding: 1px 6px; cursor: pointer; }
.barra-snap button.on { color: var(--texto); background: color-mix(in srgb, var(--campo-foco) 30%, transparent); border-color: var(--campo-foco); }
.barra-snap button.seta { padding: 1px 3px; margin-left: -3px; border-left: 0; border-radius: 0 3px 3px 0; }
.barra-snap .menu-snap { position: absolute; left: 0; bottom: calc(100% + 6px); z-index: 30; min-width: 220px;
  background: var(--painel); border: 1px solid var(--borda-forte); border-radius: var(--raio); box-shadow: var(--sombra-menu);
  padding: 4px 0; font: 12.5px "Segoe UI", system-ui, sans-serif; color: var(--texto); }
.barra-snap .menu-snap[hidden] { display: none; }
.barra-snap .menu-snap label { display: flex; align-items: center; gap: 8px; padding: 3px 12px; cursor: pointer; }
.barra-snap .menu-snap label:hover { background: var(--painel2); }
.barra-snap .menu-snap hr { border: 0; border-top: 1px solid var(--borda); margin: 4px 0; }
.barra-snap .menu-snap .acoes { display: flex; gap: 6px; padding: 2px 12px 4px; }
.barra-snap .menu-snap .acoes button { font: 12px "Segoe UI", system-ui, sans-serif; color: var(--texto2); letter-spacing: 0; }
.snaps label.apagado { opacity: .45; }
.snaps label.snap-objeto { grid-column: 1 / -1; font-weight: 600; }
`;

/** Põe os botões no rodapé, antes da linha de comando; cad._barraSnap() os acerta pelo estado do snap. */
export function instalarBarraSnap(cad) {
  const rodape = document.querySelector('footer.rodape');
  if (!rodape || document.getElementById('barra-snap')) return;
  if (!document.getElementById('estilo-barra-snap')) {
    const st = document.createElement('style');
    st.id = 'estilo-barra-snap'; st.textContent = ESTILO;
    document.head.append(st);
  }
  const caixa = document.createElement('span');
  caixa.className = 'barra-snap'; caixa.id = 'barra-snap';
  const botao = (rotulo, dica, aoClicar) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = rotulo; b.title = dica;
    b.addEventListener('click', (ev) => { ev.preventDefault(); aoClicar(); b.blur(); });
    caixa.append(b);
    return b;
  };
  const snap = cad.snap;
  const bSnap = botao('SNAP', 'Snap de objeto: liga e desliga (F3). A setinha escolhe os pontos', () => cad.definirSnap({ objeto: !snap.objeto }));
  const bSeta = botao('▾', 'Os pontos do snap de objeto', () => { menu.hidden = !menu.hidden; if (!menu.hidden) montarMenu(); });
  bSeta.classList.add('seta');
  const bOrto = botao('ORTO', 'Só horizontal e vertical (F8)', () => cad.definirOrto(!snap.orto));
  const bPolar = botao('POLAR', 'Rastreamento polar (F10)', () => cad.definirRastreamento({ polar: !snap.ativos.polar }));
  const bRastr = botao('RASTR.', 'Rastreamento dos pontos adquiridos: as guias horizontal e vertical (F11)', () => cad.definirRastreamento({ rastreamento: !snap.ativos.rastreamento }));
  const menu = document.createElement('div');
  menu.className = 'menu-snap'; menu.hidden = true;
  caixa.append(menu);

  function montarMenu() {
    menu.replaceChildren();
    for (const [k, r, dica] of TIPOS_SNAP) {
      const l = document.createElement('label'); l.title = dica;
      const c = document.createElement('input'); c.type = 'checkbox'; c.checked = !!snap.ativos[k]; c.dataset.snap = k;
      c.addEventListener('change', () => { cad.definirSnap({ ativos: { [k]: c.checked } }); c.blur(); });
      l.append(c, r);
      menu.append(l);
    }
    menu.append(document.createElement('hr'));
    const acoes = document.createElement('div'); acoes.className = 'acoes';
    const todos = (v) => Object.fromEntries(TIPOS_SNAP.filter(([k]) => k !== 'grade').map(([k]) => [k, v]));
    for (const [r, v] of [['Marcar todos', true], ['Desmarcar todos', false]]) {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = r;
      b.addEventListener('click', () => { cad.definirSnap({ ativos: todos(v) }); montarMenu(); });
      acoes.append(b);
    }
    menu.append(acoes);
  }
  // fora do menu, fecha (como os outros menus do CAD)
  document.addEventListener('mousedown', (ev) => { if (!menu.hidden && !caixa.contains(ev.target)) menu.hidden = true; }, true);
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && !menu.hidden) { menu.hidden = true; ev.stopPropagation(); } }, true);

  const medidas = rodape.querySelector('.medidas');
  rodape.insertBefore(caixa, medidas || null);
  cad._barraSnap = () => {
    bSnap.classList.toggle('on', !!snap.objeto);
    bOrto.classList.toggle('on', !!snap.orto);
    bPolar.classList.toggle('on', !!snap.ativos.polar);
    bRastr.classList.toggle('on', !!snap.ativos.rastreamento);
    if (!menu.hidden) for (const c of menu.querySelectorAll('input[data-snap]')) c.checked = !!snap.ativos[c.dataset.snap];
  };
  cad._barraSnap();
}
