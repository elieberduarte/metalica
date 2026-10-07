// O quadrinho da escala, no canto de baixo à direita do desenho (07/10, pedido do usuário: na área de trabalho a barra
// de cima do CAD — a do "Escala 1:" — fica escondida e a escala sumia da vista). Mostra a escala do desenho, com o
// seletor ligado ao de cima (trocar aqui é trocar lá: a mesma pergunta do que fazer com o já desenhado), e a régua
// gráfica, que acompanha o zoom: uma barra de comprimento redondo (1 m, 5 m, 10 m…) na medida da tela.

import { UNIDADES, definirUnidade, unidadeAtual } from './ferramentas.js';
import { ComandoAlterar } from './nucleo/comandos.js';

const COMPRIMENTOS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000];
const rotulo = (mm) => (mm >= 1000 ? `${String(mm / 1000).replace('.', ',')} m` : mm >= 10 ? `${String(mm / 10).replace('.', ',')} cm` : `${mm} mm`);

const ESTILO = `
.rodape-escala { position: absolute; right: 10px; bottom: 10px; display: flex; align-items: center; gap: 12px;
  font-family: var(--mono); font-size: 11px; color: var(--texto3);
  background: color-mix(in srgb, var(--painel) 78%, transparent); border: 1px solid var(--borda);
  border-radius: var(--raio-p); padding: 3px 9px; user-select: none; }
.rodape-escala label { display: inline-flex; align-items: center; gap: 4px; }
.rodape-escala select { font: inherit; color: var(--texto2); background: transparent; border: 1px solid var(--borda);
  border-radius: 3px; padding: 0 2px; }
.rodape-escala .regua { display: inline-flex; align-items: center; gap: 6px; }
.rodape-escala .mais { font: inherit; font-size: 13px; line-height: 1; color: var(--texto2); background: none; border: 1px solid var(--borda);
  border-radius: 3px; padding: 0 5px; cursor: pointer; }
.rodape-escala .lista { position: absolute; right: 0; bottom: calc(100% + 6px); min-width: 300px; display: flex; flex-direction: column;
  background: var(--painel); border: 1px solid var(--borda-forte); border-radius: var(--raio); box-shadow: var(--sombra-menu);
  padding: 6px; font-family: "Segoe UI", system-ui, sans-serif; font-size: 12.5px; color: var(--texto); z-index: 30; }
.rodape-escala .lista[hidden] { display: none; }
.rodape-escala .lista .info { padding: 4px 8px 6px; color: var(--texto2); line-height: 1.45; border-bottom: 1px solid var(--borda); margin-bottom: 4px; }
.rodape-escala .lista button { text-align: left; background: none; border: 0; color: var(--texto); padding: 6px 8px; border-radius: 4px; cursor: pointer; font: inherit; }
.rodape-escala .lista button:hover { background: var(--painel2); }
.rodape-escala .regua i { display: inline-block; height: 6px; border: 1px solid var(--texto3); border-top: 0;
  background: linear-gradient(90deg, var(--texto3) 0 50%, transparent 50% 100%) bottom / 100% 2px no-repeat; }
`;

export function instalarRodapeEscala(cad) {
  const palco = document.getElementById('palco');
  const original = document.getElementById('escala');
  if (!palco || !original || !cad.tela || document.getElementById('rodape-escala')) return;
  if (!document.getElementById('estilo-rodape-escala')) {
    const st = document.createElement('style');
    st.id = 'estilo-rodape-escala';
    st.textContent = ESTILO;
    document.head.append(st);
  }
  const sel = document.createElement('select');
  sel.title = 'Escala em que o desenho será impresso (a mesma do topo): define o tamanho de textos, cotas e hachuras';
  sel.addEventListener('change', () => { original.value = sel.value; original.dispatchEvent(new Event('change')); });
  const rotuloEscala = document.createElement('label');
  rotuloEscala.append('Escala 1:', sel);
  // a unidade das medidas (07/10): separada da escala — o desenho é sempre em mm; muda o número digitado sem unidade,
  // as medidas mostradas e o número das cotas novas
  const selUn = document.createElement('select');
  selUn.title = 'Unidade das medidas: o número digitado sem unidade (475 = 4,75 m em cm), as medidas que as ferramentas mostram e o número das cotas novas. Não muda o desenho nem a escala de impressão';
  for (const u of Object.keys(UNIDADES)) { const o = document.createElement('option'); o.value = u; o.textContent = u; selUn.append(o); }
  selUn.addEventListener('change', () => trocarUnidade(selUn.value));
  const rotuloUn = document.createElement('label');
  rotuloUn.append('Medidas em', selUn);
  const barra = document.createElement('i');
  const texto = document.createElement('span');
  const regua = document.createElement('span');
  regua.className = 'regua';
  regua.title = 'Régua gráfica: o comprimento da barra na medida da tela (acompanha o zoom)';
  regua.append(barra, texto);
  const caixa = document.createElement('div');
  caixa.id = 'rodape-escala';
  caixa.className = 'rodape-escala';
  // ⋯: o resto do que é de escala, à mão (07/10: "acesso rápido à informação das escalas, ajustar a escala, escala atual")
  const lista = document.createElement('div');
  lista.className = 'lista';
  lista.hidden = true;
  const info = document.createElement('div');
  info.className = 'info';
  const item = (rot, dica, fazer) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = rot; b.title = dica;
    b.addEventListener('click', () => { lista.hidden = true; fazer(); });
    return b;
  };
  const ferramenta = (id) => () => { if (cad.ferramentas && cad.ferramentas.has(id)) cad.ativarFerramenta(id); };
  lista.append(info,
    item('Calibrar a escala da planta…', 'Dois cliques numa medida conhecida (uma cota, um vão) e a medida real: a planta importada é escalada (os eixos e os elementos podem ir junto)', ferramenta('calibrar')),
    item('Ajustar cotas e eixos à escala', 'Todas as cotas, os balões e os nomes dos eixos feitos aqui no tamanho da escala atual (com seleção, só nela); o importado não muda', () => cad.ajustarAEscala && cad.ajustarAEscala()),
    item('Ajustar cotas ao desenho em volta', 'Clique numa cota (ou selecione várias antes): o texto e as pontas tomam o tamanho do desenho em volta', ferramenta('ajustar_cota')),
    item('Enquadrar tudo', 'Zoom para ver o desenho inteiro', () => cad.tela.enquadrar()));
  const mais = document.createElement('button');
  mais.type = 'button'; mais.className = 'mais'; mais.textContent = '⋯'; mais.title = 'Escala: informações e ajustes';
  mais.addEventListener('click', (ev) => { ev.stopPropagation(); lista.hidden = !lista.hidden; atualizar(); });
  document.addEventListener('click', (ev) => { if (!caixa.contains(ev.target)) lista.hidden = true; });
  caixa.append(rotuloEscala, rotuloUn, regua, mais, lista);

  const da = () => ((cad.doc && cad.doc.metadados) || {}).unidade_medidas || 'mm';
  // as cotas feitas aqui sem texto escrito e sem a escala de prancha: o número delas na unidade
  const cotasParaUnidade = (u) => {
    const m = {}, k = 1 / UNIDADES[u];
    for (const e of cad.doc.entidades.values()) {
      if (e.tipo !== 'cota' || (e.atributos && e.atributos.origem) || (e.texto != null && e.texto !== '')) continue;
      const esc = e.escala || 1;
      if (Math.abs(esc - k) > 1e-9 && Object.values(UNIDADES).some(f => Math.abs(esc * f - 1) < 1e-9)) m[e.id] = { escala: k === 1 ? null : k };
    }
    return m;
  };
  function trocarUnidade(u) {
    if (!cad.doc) return;
    const meta = cad.doc.metadados || (cad.doc.metadados = {});
    meta.unidade_medidas = u;
    definirUnidade(u);
    if (typeof cad._agendarAutosave === 'function') cad._agendarAutosave();
    cad.dica(`Medidas em ${u}: o número digitado sem unidade vale ${u}, as ferramentas mostram em ${u} e as cotas novas saem em ${u}. O desenho e a escala de impressão não mudam.`);
    const m = cotasParaUnidade(u), n = Object.keys(m).length;
    if (n) {
      const bt = document.createElement('button');
      bt.type = 'button'; bt.className = 'sec'; bt.textContent = `Passar as ${n} cota(s) para ${u}`;
      bt.addEventListener('click', () => { const av = bt.closest('.aviso'); if (av) av.remove(); cad.executar(new ComandoAlterar(m, `Cotas em ${u}`)); });
      const sp = document.createElement('span');
      sp.append(`${n} cota(s) já desenhada(s) mostram outra unidade. `, bt);
      cad.aviso(sp, 'info', 15000);
    }
    atualizar();
  }
  palco.append(caixa);

  let opcoes = '';
  const atualizar = () => {
    // as opções do seletor de cima (a escala do DXF importado entra como opção nova)
    if (original.innerHTML !== opcoes) { opcoes = original.innerHTML; sel.innerHTML = opcoes; }
    if (sel.value !== original.value) sel.value = original.value;
    if (unidadeAtual() !== da()) definirUnidade(da());            // o desenho aberto manda (cada um grava a sua)
    if (selUn.value !== unidadeAtual()) selUn.value = unidadeAtual();
    const mmpp = cad.tela.mmPorPixel;
    if (!(mmpp > 0)) return;
    const L = COMPRIMENTOS.find(c => c / mmpp >= 50) || COMPRIMENTOS[COMPRIMENTOS.length - 1];
    barra.style.width = `${Math.round(Math.min(L / mmpp, 220))}px`;
    texto.textContent = rotulo(L);
    const E = parseFloat(original.value) || cad.doc.escala || 1;
    info.textContent = `Escala do desenho 1:${String(E).replace('.', ',')} — 1 mm na folha impressa = ${String(E).replace('.', ',')} mm na obra; ` +
      `textos, cotas e bolinhas saem nesse tamanho. Na tela agora: 1 pixel = ${mmpp >= 10 ? Math.round(mmpp) : mmpp.toFixed(1).replace('.', ',')} mm. ` +
      'Para trocar a escala de impressão, use o seletor "Escala 1:"; para a planta que veio com a medida errada, Calibrar. ' +
      `Medidas em ${unidadeAtual()}: é a unidade do número digitado sem unidade, das medidas mostradas e das cotas novas (o desenho é sempre em mm; 475cm, 4,75m e 4750mm valem em qualquer unidade).`;
    // os botões do rodapé do desenho (Original, Montagem… Nova revisão do DXF) passam por baixo quando a tela é estreita:
    // o quadrinho sobe uma linha
    // pelos botões que aparecem, não pela faixa inteira (ela ocupa a largura toda e o quadrinho subia sempre)
    const abas = document.getElementById('abas-projeto');
    caixa.style.bottom = '10px';
    if (abas && !abas.hidden) {
      const c = caixa.getBoundingClientRect();
      const bs = [...abas.querySelectorAll('button')].filter(b => !b.hidden).map(b => b.getBoundingClientRect()).filter(r => r.width);
      const direita = bs.length ? Math.max(...bs.map(r => r.right)) : -Infinity;
      if (direita > c.left - 8) caixa.style.bottom = `${Math.round(Math.max(...bs.map(r => r.height)) + 18)}px`;
    }
  };
  const antes = cad.tela.aoDesenhar;
  cad.tela.aoDesenhar = () => { if (antes) antes(); atualizar(); };
  original.addEventListener('change', atualizar);
  atualizar();
}
