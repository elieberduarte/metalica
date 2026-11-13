// A barra de andamento das tarefas demoradas — o padrão de todas as telas (pedido do usuário, 16/10/2026: "criar barras
// de processo para todas as tarefas que têm esses processamentos em segundo plano, análises, verificações,
// detalhamentos… tornar isso um padrão do sistema").
// A flutuante segue o tema da tela (--painel/--texto/--borda): a variável de antes (--fundo2) não existia em tela
// nenhuma e ela saía escura no tema claro, com o texto escuro do tema por cima (Mercado, 19/10)
//
// Enquanto o servidor trabalha, a tela pergunta o andamento (GET …/progresso: {etapa, fracao?, ha_s, desde_s}) e a barra
// mostra, nesta ordem de preferência:
//   1. a fração que o servidor conta (a etapa "i de n", o laço das peças);
//   2. sem ela, a estimativa pelo tempo que a mesma tarefa levou da última vez neste computador (até 95 %, com "~");
//   3. na primeira vez, o "(i de n)" da etapa corrente, quando o servidor o diz (fracao_etapa);
//   4. sem nada disso, a barra correndo (sem número).
// O texto da etapa e o tempo decorrido ficam ao lado. Ao terminar, a duração fica guardada para a próxima estimativa.
//
// Uso:   const parar = acompanhar({ url, tarefa: 'detalhar', rotulo: 'Detalhando', onde: elementoDoRodape, dica });
//        … await a chamada …;  parar();            // parar(false) quando falhou: a duração não é guardada
//
// A tarefa de um projeto (a url é …/api/projetos/<s>/progresso) ganha o botão "Cancelar" na barra (usuário, 11/11: "Não
// consigo cancelar um processo quando está em andamento, preciso que crie um botão para fazer esse cancelamento"):
// confirma, pede POST …/cancelar e o servidor para a tarefa no próximo passo, antes de gravar (o projeto fica como
// estava); a que já está gravando termina sozinha, inteira. A chamada da tarefa volta com 409 {cancelada: true}.

const CHAVE = 'metalica.duracao.';
const TIQUE_MS = 600;

let _estilo = false;
function _injetarEstilo() {
  if (_estilo || typeof document === 'undefined') return;
  _estilo = true;
  const s = document.createElement('style');
  s.id = 'estilo-barra-progresso';
  s.textContent = `
.barra-andamento { display: inline-flex; align-items: center; gap: 8px; flex: 0 1 auto; min-width: 0; font-size: 12px; }
.barra-andamento-trilho { position: relative; width: 180px; height: 8px; border-radius: 4px; flex: 0 0 auto;
  background: rgba(127,127,127,.28); overflow: hidden; }
.barra-andamento-cheio { position: absolute; left: 0; top: 0; bottom: 0; width: 0; border-radius: 4px;
  background: var(--azul2, #1f6fd0); transition: width .5s ease; }
.barra-andamento[data-modo="estimada"] .barra-andamento-cheio { opacity: .75; }
.barra-andamento[data-modo="correndo"] .barra-andamento-cheio { width: 35% !important; transition: none;
  animation: barra-andamento-corre 1.3s ease-in-out infinite; }
@keyframes barra-andamento-corre { from { left: -35%; } to { left: 100%; } }
.barra-andamento-pct { font-family: var(--mono, ui-monospace, monospace); font-size: 11px; min-width: 38px; opacity: .8; }
.barra-andamento-texto { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.barra-andamento-cancelar { font: inherit; font-size: 11.5px; font-weight: 600; padding: 1px 9px; border-radius: 5px; cursor: pointer;
  border: 1px solid #c0392b; color: #c0392b; background: transparent; flex: 0 0 auto; }
.barra-andamento-cancelar:hover:not(:disabled) { background: #c0392b; color: #fff; }
.barra-andamento-cancelar:disabled { opacity: .6; cursor: default; }
.dlg-cancelar-tarefa { border: 1px solid var(--borda-forte, #9aa8c0); border-radius: 8px; padding: 14px 16px; max-width: 460px;
  background: var(--painel, #fff); color: var(--texto, #1b2433); box-shadow: 0 6px 22px rgba(0,0,0,.25); font-size: 13px; }
.dlg-cancelar-tarefa::backdrop { background: rgba(16,24,40,.35); }
.dlg-cancelar-tarefa p { margin: 0 0 12px; line-height: 1.45; }
.dlg-cancelar-tarefa .bts { display: flex; gap: 8px; justify-content: flex-end; }
.dlg-cancelar-tarefa .perigo { background: #c0392b; border-color: #c0392b; color: #fff; font-weight: 600; }
.barra-andamento.flutuante { position: fixed; left: 50%; bottom: 14px; transform: translateX(-50%); z-index: 9999;
  max-width: min(720px, calc(100vw - 32px)); padding: 8px 14px; border-radius: 8px;
  background: var(--painel, #1c2430); color: var(--texto, #e8edf3); border: 1px solid var(--borda, transparent);
  box-shadow: 0 4px 18px rgba(16,32,60,.22); }
@media (prefers-reduced-motion: reduce) { .barra-andamento[data-modo="correndo"] .barra-andamento-cheio { animation: none; left: 0; } }
`;
  document.head.appendChild(s);
}

function _ler(tarefa) {
  try { const v = Number(localStorage.getItem(CHAVE + tarefa)); return v > 0 ? v : 0; } catch (e) { return 0; }
}
function _guardar(tarefa, s) {
  try { localStorage.setItem(CHAVE + tarefa, String(Math.round(s * 10) / 10)); } catch (e) { /* sem armazenamento */ }
}

/** O que a barra mostra agora: {modo: 'servidor'|'estimada'|'correndo', fracao}. Exportada para o teste. */
export function fracaoDaBarra(p, decorrido, ultima) {
  if (p && typeof p.fracao === 'number' && isFinite(p.fracao)) {
    return { modo: 'servidor', fracao: Math.max(0, Math.min(1, p.fracao)) };
  }
  if (ultima > 0) return { modo: 'estimada', fracao: Math.min(0.95, decorrido / ultima) };
  // a primeira vez: o "(i de n)" da etapa corrente (anda dentro da etapa; a próxima recomeça)
  if (p && typeof p.fracao_etapa === 'number' && isFinite(p.fracao_etapa)) {
    return { modo: 'etapa', fracao: Math.max(0, Math.min(1, p.fracao_etapa)) };
  }
  return { modo: 'correndo', fracao: null };
}

function _tempo(s) {
  if (s < 60) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')} s`;
}

/**
 * Mostra a barra e acompanha a tarefa; devolve parar(ok = true).
 * @param url     GET do andamento (…/progresso); sem ela, só a estimativa pelo tempo
 * @param tarefa  nome estável da tarefa (a estimativa pela última duração é por ele)
 * @param rotulo  o que aparece antes da etapa ("Detalhando")
 * @param onde    elemento depois do qual a barra entra (a linha de dica do rodapé); sem ele, a barra flutua embaixo
 * @param dica    função(texto) que também recebe a linha (o rodapé do editor e do CAD), opcional
 */
export function acompanhar({ url = '', tarefa = 'tarefa', rotulo = '', onde = null, dica = null, andamento = null } = {}) {
  // `andamento`: () => {etapa, fracao} de uma tarefa da própria tela (a montagem do modelo grande no editor 3D, 03/11),
  // no lugar da consulta à `url` do servidor
  _injetarEstilo();
  const naTela = { url, generica: rotulo === GENERICO, parar: null };
  if (!naTela.generica) for (const b of [...NA_TELA]) if (b.generica) b.parar(false);   // a tarefa com nome tira a da consulta
  NA_TELA.add(naTela);                                           // a vigilância das chamadas não põe outra barra
  const ultima = _ler(tarefa);
  const inicio = performance.now();
  const cheio = document.createElement('span'); cheio.className = 'barra-andamento-cheio';
  const trilho = document.createElement('span'); trilho.className = 'barra-andamento-trilho'; trilho.appendChild(cheio);
  const pct = document.createElement('span'); pct.className = 'barra-andamento-pct';
  const texto = document.createElement('span'); texto.className = 'barra-andamento-texto';
  const barra = document.createElement('span');
  barra.className = 'barra-andamento' + (onde ? '' : ' flutuante');
  barra.setAttribute('role', 'progressbar');
  barra.setAttribute('aria-label', rotulo || 'Andamento');
  barra.dataset.tarefa = tarefa;
  barra.append(trilho, pct);
  if (!dica) barra.append(texto);              // sem a linha de dica, o texto da etapa vai na própria barra
  // o Cancelar da tarefa do projeto (11/11)
  const projeto = projetoDaUrl(url);
  let botao = null;
  if (projeto) {
    botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'barra-andamento-cancelar';
    botao.textContent = 'Cancelar';
    botao.title = 'Para a tarefa no próximo passo; o projeto fica como estava';
    botao.onclick = async () => {
      const decorrido = (performance.now() - inicio) / 1000;
      botao.disabled = true;
      const r = await pedirCancelar(projeto, { rotulo, etapa: (ultimoP && ultimoP.etapa) || '', desde_s: decorrido });
      if (!r) { botao.disabled = false; return; }
      mostrarCancelamento(botao, r);
    };
    barra.append(botao);
  }
  if (onde && onde.parentNode) onde.after(barra); else document.body.appendChild(barra);
  let vivo = true, timer = null, ultimoP = null;

  const desenhar = () => {
    const decorrido = (performance.now() - inicio) / 1000;
    const f = fracaoDaBarra(ultimoP, decorrido, ultima);
    barra.dataset.modo = f.modo;
    if (f.fracao === null) { pct.textContent = ''; barra.removeAttribute('aria-valuenow'); }
    else {
      const v = Math.round(f.fracao * 100);
      cheio.style.width = `${v}%`;
      // a estimada com "≈": o "~" na letra pequena do rodapé parecia um sinal de menos ("−28 %", Sesi Chapecó, 03/11)
      pct.textContent = (f.modo === 'estimada' ? '≈' : '') + `${v} %`;
      barra.setAttribute('aria-valuenow', String(v));
    }
    const etapa = (ultimoP && ultimoP.etapa) || '';
    // o botão segue o servidor também depois de apertado: "cancelando…" vira "terminando de gravar…" quando a tarefa
    // entra na gravação (D03, causa 3: ficava "cancelando…" até o fim e a tela depois abria o resultado)
    if (botao && estadoDoCancelar(ultimoP, botao.textContent) !== null) mostrarCancelamento(botao, ultimoP);
    const linha = `${rotulo ? rotulo + (etapa ? ': ' : '…') : ''}${etapa}${decorrido >= 3 ? ` · ${_tempo(decorrido)}` : ''}`;
    texto.textContent = linha;
    barra.title = linha;
    if (dica) dica(linha);
  };
  const tique = async () => {
    if (!vivo) return;
    if (url) {
      try {
        const r = await fetch(url, { cache: 'no-store' });
        if (r.ok) { const p = await r.json(); if (vivo && p && (p.etapa || typeof p.fracao === 'number')) ultimoP = p; }
      } catch (e) { /* servidor ocupado ou reiniciando: tenta no próximo tique */ }
    } else if (typeof andamento === 'function') {
      try { const p = andamento(); if (p && (p.etapa || typeof p.fracao === 'number')) ultimoP = p; } catch (e) { /* a tela decide */ }
    }
    if (!vivo) return;
    desenhar();
    timer = setTimeout(tique, TIQUE_MS);
  };
  desenhar();
  timer = setTimeout(tique, 250);
  naTela.parar = (ok = true) => {
    if (!vivo) return;
    vivo = false;
    clearTimeout(timer);
    NA_TELA.delete(naTela);
    if (ok) _guardar(tarefa, (performance.now() - inicio) / 1000);
    barra.remove();
    const recado = recadoDoFim(botao ? botao.textContent : '', ultimoP);
    if (recado) _recado(recado);
  };
  return naTela.parar;
}

// ------------------------------------------------------------------ o Cancelar (11/11)

/** O projeto da url do andamento (…/api/projetos/<s>/progresso), ou '' (a tarefa sem projeto não tem Cancelar). */
export function projetoDaUrl(url) {
  const m = _caminho(url || '').match(/^\/api\/projetos\/([^/]+)\/progresso$/);
  return m ? decodeURIComponent(m[1]) : '';
}

/** O botão depois do pedido: "cancelando…", ou a tarefa já gravava e termina sozinha. */
/** O que o botão Cancelar deve passar a dizer com o andamento `p` do servidor, ou null (fica como está):
 *  'cancelando' (o cancelamento foi pedido, de qualquer tela) ou 'terminando' (pedido, mas a tarefa já grava). */
export function estadoDoCancelar(p, textoAtual = '') {
  if (!p || !p.cancelando) return null;
  if (p.gravando) return textoAtual === 'terminando de gravar…' ? null : 'terminando';
  return textoAtual === 'cancelando…' || textoAtual === 'terminando de gravar…' ? null : 'cancelando';
}

/** O recado do fim quando o cancelamento foi pedido mas a tarefa já gravava: ela terminou, o resultado ficou. '' sem recado. */
export function recadoDoFim(textoDoBotao, p) {
  return textoDoBotao === 'terminando de gravar…' || (textoDoBotao === 'cancelando…' && p && p.gravando)
    ? 'A tarefa já estava gravando quando o cancelamento foi pedido: terminou, para o projeto não ficar pela metade, e o resultado ficou.'
    : '';
}

function _recado(texto) {
  _injetarEstilo();
  const r = document.createElement('div');
  r.className = 'barra-andamento flutuante barra-andamento-recado';
  r.setAttribute('role', 'status');
  r.textContent = texto;
  document.body.appendChild(r);
  setTimeout(() => r.remove(), 9000);           // sai sozinho (TEL-01)
}

function mostrarCancelamento(botao, r) {
  botao.disabled = true;
  if (r.gravando) {
    botao.textContent = 'terminando de gravar…';
    botao.title = 'A tarefa já estava gravando no projeto: termina sozinha, para o projeto não ficar pela metade';
  } else {
    botao.textContent = 'cancelando…';
    botao.title = 'A tarefa para no próximo passo; o projeto fica como estava';
  }
}

/** Pergunta "Cancelar a tarefa?" e, com o sim, pede ao servidor. Devolve a resposta {cancelando, gravando, onde}, ou null
 *  (o usuário desistiu ou o pedido falhou). Usada também pelo cartão da tela Projetos. */
export async function pedirCancelar(projeto, { rotulo = '', etapa = '', desde_s = 0, nome = '' } = {}) {
  _injetarEstilo();
  const oQue = rotulo && rotulo !== GENERICO ? rotulo : 'A tarefa';
  const sim = await _confirmar(`${oQue}${nome ? ' de ' + nome : ''}${desde_s >= 3 ? ', há ' + _tempo(desde_s) : ''}` +
    `${etapa ? ' (' + etapa + ')' : ''}.`);
  if (!sim) return null;
  try {
    const r = await fetch(`/api/projetos/${encodeURIComponent(projeto)}/cancelar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || r.statusText);
    return d;
  } catch (e) {
    try { alert('Não foi possível cancelar: ' + e.message); } catch (e2) { /* sem janela */ }
    return null;
  }
}

/** O diálogo acabou de fechar no clique: o clique seguinte (o 2º do clique duplo, até `ms`) que cair onde ele estava não
 *  chega ao que está atrás — o cartão de baixo abria outro projeto e, no 3D, começava uma seleção por janela (D09 do
 *  usuario-desastrado, 13/11). Só no retângulo do diálogo (com 4 px de folga) e só nesse tempo: um clique noutro ponto da
 *  tela, ou dentro de outro diálogo aberto, passa. */
export function segurarCliqueAtras(ret, ms = 400) {
  if (!ret || !(ret.width > 0) || !(ret.height > 0) || typeof window === 'undefined') return;
  const ate = performance.now() + ms, F = 4;
  const TIPOS = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'dblclick', 'contextmenu'];
  const dentro = (ev) => ev.clientX >= ret.left - F && ev.clientX <= ret.right + F && ev.clientY >= ret.top - F && ev.clientY <= ret.bottom + F;
  const engolir = (ev) => {
    if (performance.now() > ate) { soltar(); return; }
    if (!dentro(ev)) return;
    if (ev.target && ev.target.closest && ev.target.closest('dialog[open]')) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
  };
  const soltar = () => { for (const t of TIPOS) window.removeEventListener(t, engolir, true); };
  for (const t of TIPOS) window.addEventListener(t, engolir, true);
  setTimeout(soltar, ms + 50);
}

function _confirmar(descricao) {
  return new Promise((pronto) => {
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg-cancelar-tarefa';
    const p = document.createElement('p');
    const b = document.createElement('b'); b.textContent = 'Cancelar a tarefa?';
    p.append(b, document.createElement('br'), descricao, document.createElement('br'),
      'O projeto volta como estava. Se ela já estiver gravando, termina sozinha, para nada ficar pela metade.');
    const continuar = document.createElement('button'); continuar.type = 'button'; continuar.textContent = 'Continuar a tarefa';
    const cancelar = document.createElement('button'); cancelar.type = 'button'; cancelar.className = 'perigo'; cancelar.textContent = 'Cancelar a tarefa';
    const bts = document.createElement('div'); bts.className = 'bts'; bts.append(continuar, cancelar);
    dlg.append(p, bts);
    document.body.appendChild(dlg);
    const fechar = (v) => {
      segurarCliqueAtras(dlg.getBoundingClientRect());     // o 2º clique do clique duplo não cai no cartão de baixo (D09)
      try { dlg.close(); } catch (e) { /* já fechado */ }
      dlg.remove(); pronto(v);
    };
    continuar.addEventListener('click', () => fechar(false));
    cancelar.addEventListener('click', () => fechar(true));
    dlg.addEventListener('cancel', (ev) => { ev.preventDefault(); fechar(false); });
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
    continuar.focus();
  });
}

// ------------------------------------------------------------------ a vigilância das chamadas
// O padrão sem esforço: toda chamada ao servidor (/api/…) que demora mais que ESPERA_MS ganha a barra sozinha — no
// rodapé da tela, quando ela tem a linha de dica, senão flutuando embaixo —, com a etapa que o servidor conta para o
// projeto e a estimativa pela duração da mesma tarefa, no mesmo projeto, da última vez. Instalada em toda página pelo
// vivo.js; a tela que já acompanha a tarefa (acompanhar) não ganha uma segunda barra.

/** As barras na tela, {url do andamento, generica, parar}: uma barra por vez (TEL-01, 03/11/2026 — com a máquina
 *  ocupada, o peso, o catálogo e a malha passavam de 1,2 s no meio do Detalhar e ganhavam um "Processando…" ao lado,
 *  duas ou três barras no rodapé, a do peso repetindo a etapa do Detalhar). */
const NA_TELA = new Set();
const ESPERA_MS = 1200;
/** O rótulo da chamada que não é uma tarefa com nome (uma consulta). */
const GENERICO = 'Processando';
/** As consultas que a própria barra e o sinal de vida fazem: nunca viram tarefa. */
const NUNCA = /\/(progresso|vivo|fechou|versao|lento|cancelar)(\?|$)|\/desenhos-vivos(\?|$)|\/conferencia\/progresso/;
/** O nome da tarefa na barra, pelo último pedaço da rota. */
const ROTULOS = {
  'detalhar': 'Detalhando', 'detalhar-premoldado': 'Pré-moldado', 'detalhar-posicao': 'Detalhe da peça',
  'importar-ifc': 'Importando o modelo', 'importar-pacote': 'Importando o projeto', 'importar-dxf': 'Lendo o DXF', 'colar-autocad': 'Colando do AutoCAD',
  'importar-pdf': 'Lendo o PDF', 'resumos': 'Resumos da obra', 'materiais': 'Lista de materiais', 'pdf': 'Gerando o PDF', 'video': 'Gravando o vídeo',
  'dxf': 'Gerando o DXF', 'imprimir': 'Imprimindo as pranchas', 'folhas': 'Lendo as folhas', 'pranchas': 'Montando as pranchas', 'telhas-fornecedor': 'Gerando as telhas para o fornecedor', 'pranchas-das-folhas': 'Pranchas das folhas',
  'analise-estrutural': 'Análise estrutural', 'esforcos': 'Esforços e verificação', 'calcular': 'Calculando',
  'dimensionar': 'Dimensionando', 'memorial': 'Memorial', 'conferencia': 'Conferindo', 'aplicar-pecas': 'Aplicando no 3D',
  'aplicar-furos': 'Aplicando os furos', 'aplicar-3d': 'Aplicando no 3D', 'aplicar-trocas': 'Aplicando as trocas', 'trocar-grupos': 'Trocando os perfis por grupo', 'regras-trelica': 'Corrigindo pelas regras das tesouras', 'explodir-criterio': 'Explodindo com critério', 'reanalisar': 'Reanalisando a estrutura',
  'vista2d': 'Gerando a vista', 'gerar-3d': 'Gerando o 3D', 'montar-pela-planta': 'Montando pela planta',
  'projeto-2d': 'Projeto recebido', 'varrer': 'Identificação', 'reconhecer': 'Reconhecendo', 'arquitetonico': 'Arquitetônico', 'exportar': 'Exportando',
  'imagens': 'Imagens 3D', 'cantos': 'Cantos', 'multidobras-3d': 'Multidobras', 'cobertura-movel': 'Cobertura móvel',
  'ler': 'Lendo os quadros', 'revisao': 'Revisão da original', 'estrutura': 'Lançando a estrutura', '3d': 'Gerando o 3D',
  'do3d': 'Planta pelo 3D', 'apoios': 'Verificando os apoios', 'numerar': 'Numerando', 'atualizar-pecas': 'Atualizando as peças',
  'planta-cargas': 'Planta de cargas', 'comparacao-pdf': 'Quadro de comparação', 'pecas-pdf': 'PDF das peças',
  'baixar-imagem': 'Baixando a imagem do terreno', 'buscar-endereco': 'Procurando o endereço',
  'importar-imagem': 'Enviando a imagem do terreno', 'imagem': 'Gravando a imagem da cena', 'posicionar-imagem': 'Pondo a imagem do terreno no lugar',
  'proposta-pdf': 'Gerando a proposta', 'contrato-docs': 'Gerando o contrato',
  'camadas-quantidade': 'Quantidade das camadas', 'apontar': 'Apontando', 'apontar-varios': 'Apontando os itens escolhidos',
  'historico': 'Lendo os apontamentos do item', 'estornar': 'Estornando o apontamento',
  'enviar': 'Enviando a obra', 'apoios-tesouras': 'Lendo os apoios e os chumbadores', 'suportes-tercas': 'Lendo o suporte das terças', 'chapas-tesouras': 'Lendo as chapas das tesouras', 'aletas-contraventos': 'Lendo as aletas dos contraventos',
};

/** A rota que é tarefa só num método: a gravação do modelo (a do editor, que no modelo grande leva minutos, aparecia como
 *  "Processando", Sesi Chapecó, 03/11); o GET do mesmo modelo é a leitura. */
const ROTULOS_DO_METODO = { 'POST modelo': 'Gravando o modelo' };

function _caminho(url) {
  try { return new URL(url, location.href).pathname; } catch (e) { return String(url || '').split('?')[0]; }
}

/** {projeto, tarefa, rotulo, progresso} da chamada; null se não é tarefa (fora de /api/ ou uma consulta da barra). */
export function tarefaDaChamada(url, metodo = 'GET') {
  const c = _caminho(url);
  if (!c.startsWith('/api/') || NUNCA.test(c)) return null;
  const m = c.match(/^\/api\/projetos\/([^/]+)\/(.+)$/);
  const projeto = m ? decodeURIComponent(m[1]) : '';
  // a rota sem o projeto e sem o nome do desenho: a mesma tarefa em desenhos diferentes estima pelo mesmo tempo
  const rota = (m ? m[2] : c.slice(5)).replace(/^desenhos\/[^/]+\//, 'desenhos/*/');
  const partes = rota.split('/').filter(Boolean);
  let rotulo = ROTULOS_DO_METODO[`${String(metodo).toUpperCase()} ${rota}`] || GENERICO;
  if (rotulo === GENERICO) for (let i = partes.length - 1; i >= 0; i--) if (ROTULOS[partes[i]]) { rotulo = ROTULOS[partes[i]]; break; }
  return { projeto, rotulo, tarefa: `${projeto || '-'}|${String(metodo).toUpperCase()} ${rota}`,
           progresso: m ? `/api/projetos/${m[1]}/progresso` : '' };
}

function _rodape() {
  return document.querySelector('.rodape #dica') || document.querySelector('.rodape .dica') || null;
}

/** Instala a vigilância em window.fetch (uma vez por página). */
export function vigiarChamadas() {
  if (typeof window === 'undefined' || window.__metalicaVigiaChamadas || typeof window.fetch !== 'function') return;
  window.__metalicaVigiaChamadas = true;
  const original = window.fetch.bind(window);
  window.fetch = function (entrada, opcoes) {
    const url = typeof entrada === 'string' ? entrada : (entrada && entrada.url) || String(entrada || '');
    const metodo = (opcoes && opcoes.method) || (entrada && typeof entrada === 'object' && entrada.method) || 'GET';
    const t = tarefaDaChamada(url, metodo);
    if (!t) return original(entrada, opcoes);
    let parar = null;
    const espera = setTimeout(() => {
      const outras = [...NA_TELA];
      if (t.progresso && outras.some((b) => b.url === t.progresso)) return;   // a etapa deste projeto já está na tela
      if (t.rotulo === GENERICO && outras.length) return;          // a consulta não põe barra ao lado de outra
      parar = acompanhar({ url: t.progresso, tarefa: t.tarefa, rotulo: t.rotulo, onde: _rodape() });
    }, ESPERA_MS);
    const fim = (ok) => { clearTimeout(espera); if (parar) parar(ok); };
    return original(entrada, opcoes).then((r) => { fim(r.ok); return r; }, (e) => { fim(false); throw e; });
  };
}

if (typeof window !== 'undefined') window.metalicaProgresso = { acompanhar, fracaoDaBarra, tarefaDaChamada, vigiarChamadas, pedirCancelar, projetoDaUrl, segurarCliqueAtras, estadoDoCancelar, recadoDoFim };
