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
export function acompanhar({ url = '', tarefa = 'tarefa', rotulo = '', onde = null, dica = null } = {}) {
  _injetarEstilo();
  if (url) ATIVAS.set(url, (ATIVAS.get(url) || 0) + 1);       // a vigilância das chamadas não põe outra barra
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
      pct.textContent = (f.modo === 'estimada' ? '~' : '') + `${v} %`;
      barra.setAttribute('aria-valuenow', String(v));
    }
    const etapa = (ultimoP && ultimoP.etapa) || '';
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
    }
    if (!vivo) return;
    desenhar();
    timer = setTimeout(tique, TIQUE_MS);
  };
  desenhar();
  timer = setTimeout(tique, 250);
  return (ok = true) => {
    if (!vivo) return;
    vivo = false;
    clearTimeout(timer);
    if (url) { const n = (ATIVAS.get(url) || 1) - 1; if (n > 0) ATIVAS.set(url, n); else ATIVAS.delete(url); }
    if (ok) _guardar(tarefa, (performance.now() - inicio) / 1000);
    barra.remove();
  };
}

// ------------------------------------------------------------------ a vigilância das chamadas
// O padrão sem esforço: toda chamada ao servidor (/api/…) que demora mais que ESPERA_MS ganha a barra sozinha — no
// rodapé da tela, quando ela tem a linha de dica, senão flutuando embaixo —, com a etapa que o servidor conta para o
// projeto e a estimativa pela duração da mesma tarefa, no mesmo projeto, da última vez. Instalada em toda página pelo
// vivo.js; a tela que já acompanha a tarefa (acompanhar) não ganha uma segunda barra.

/** url do andamento → quantos acompanhamentos explícitos estão abertos */
const ATIVAS = new Map();
const ESPERA_MS = 1200;
/** As consultas que a própria barra e o sinal de vida fazem: nunca viram tarefa. */
const NUNCA = /\/(progresso|vivo|fechou|versao|lento)(\?|$)|\/desenhos-vivos(\?|$)|\/conferencia\/progresso/;
/** O nome da tarefa na barra, pelo último pedaço da rota. */
const ROTULOS = {
  'detalhar': 'Detalhando', 'detalhar-premoldado': 'Pré-moldado', 'detalhar-posicao': 'Detalhe da peça',
  'importar-ifc': 'Importando o modelo', 'importar-pacote': 'Importando o projeto', 'importar-dxf': 'Lendo o DXF',
  'importar-pdf': 'Lendo o PDF', 'resumos': 'Resumos da obra', 'materiais': 'Lista de materiais', 'pdf': 'Gerando o PDF',
  'dxf': 'Gerando o DXF', 'pranchas': 'Montando as pranchas', 'pranchas-das-folhas': 'Pranchas das folhas',
  'analise-estrutural': 'Análise estrutural', 'esforcos': 'Esforços e verificação', 'calcular': 'Calculando',
  'dimensionar': 'Dimensionando', 'memorial': 'Memorial', 'conferencia': 'Conferindo', 'aplicar-pecas': 'Aplicando no 3D',
  'aplicar-furos': 'Aplicando os furos', 'aplicar-3d': 'Aplicando no 3D', 'aplicar-trocas': 'Aplicando as trocas', 'trocar-grupos': 'Trocando os perfis por grupo', 'regras-trelica': 'Corrigindo pelas regras das tesouras', 'reanalisar': 'Reanalisando a estrutura',
  'vista2d': 'Gerando a vista', 'gerar-3d': 'Gerando o 3D', 'montar-pela-planta': 'Montando pela planta',
  'projeto-2d': 'Projeto recebido', 'varrer': 'Identificação', 'reconhecer': 'Reconhecendo', 'arquitetonico': 'Arquitetônico', 'exportar': 'Exportando',
  'imagens': 'Imagens 3D', 'cantos': 'Cantos', 'multidobras-3d': 'Multidobras', 'cobertura-movel': 'Cobertura móvel',
  'ler': 'Lendo os quadros', 'revisao': 'Revisão da original', 'estrutura': 'Lançando a estrutura', '3d': 'Gerando o 3D',
  'do3d': 'Planta pelo 3D', 'apoios': 'Verificando os apoios', 'numerar': 'Numerando', 'atualizar-pecas': 'Atualizando as peças',
  'planta-cargas': 'Planta de cargas', 'comparacao-pdf': 'Quadro de comparação', 'pecas-pdf': 'PDF das peças',
};

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
  let rotulo = 'Processando';
  for (let i = partes.length - 1; i >= 0; i--) if (ROTULOS[partes[i]]) { rotulo = ROTULOS[partes[i]]; break; }
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
      if (t.progresso && ATIVAS.get(t.progresso)) return;          // a tela já acompanha esta tarefa
      parar = acompanhar({ url: t.progresso, tarefa: t.tarefa, rotulo: t.rotulo, onde: _rodape() });
    }, ESPERA_MS);
    const fim = (ok) => { clearTimeout(espera); if (parar) parar(ok); };
    return original(entrada, opcoes).then((r) => { fim(r.ok); return r; }, (e) => { fim(false); throw e; });
  };
}

if (typeof window !== 'undefined') window.metalicaProgresso = { acompanhar, fracaoDaBarra, tarefaDaChamada, vigiarChamadas };
