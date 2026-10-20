// Metálica no celular — as telas de consulta.
//
// Tudo sai do pacote do projeto: `dados/projetos.json` (a lista) e, por projeto,
// `dados/<slug>/manifesto.json` e os arquivos que ele lista. É o mesmo formato na rede do PC
// (o programa entrega na hora, celular/servidor.py) e na cópia guardada para a obra. Só
// consulta: nenhuma tela grava nada.

const DADOS = 'dados/';
const q = new URLSearchParams(location.search);
let OFFLINE = q.get('offline') === '1';         // sem rede: a resposta veio da cópia guardada (ou ?offline=1 no protótipo)
let copiaDe = null;                               // de quando é a cópia mostrada
const COPIA_OK = 'serviceWorker' in navigator && window.isSecureContext;     // a cópia para a obra pede HTTPS (ou localhost)
if (COPIA_OK) navigator.serviceWorker.register('sw.js', { scope: './' }).catch(() => {});

const $ = (s, el = document) => el.querySelector(s);
const tela = $('#tela');
const folha = $('#folha');
const nf = (v, casas = 0) => (v == null || v === '' ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const kg = v => (v >= 10000 ? nf(v / 1000, 1) + ' t' : nf(v, v < 10 ? 2 : 1) + ' kg');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const dataHora = iso => { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); };

// ------------------------------------------------------------------ instalar
// O "Instalar" do próprio app, com o logo e o nome — e não o atalho genérico do menu do Chrome.
// O Chrome só oferece a instalação em conexão segura (HTTPS); fora dela o cartão explica o que
// falta e ensina o atalho, que já sai com o logo (o manifesto e os ícones saem sem a chave).
let pedidoInstalar = null;
// ------------------------------------------------------------------ tema
// O do aparelho, até a pessoa escolher no botão do topo — aí vale a escolha, guardada no aparelho
// (o CSS lê data-tema no <html>). O 3D aberto acompanha as duas trocas sem recarregar.
const ESCURO = window.matchMedia('(prefers-color-scheme: dark)');
const TEMA = 'metalica-tema';
let temaEscolhido = (() => { try { return localStorage.getItem(TEMA); } catch (e) { return null; } })();
const escuro = () => (temaEscolhido === 'claro' || temaEscolhido === 'escuro' ? temaEscolhido === 'escuro' : ESCURO.matches);
/** Chamado no fim do arquivo (o 3D, `visor`, só existe depois daqui) e a cada troca. */
function aplicarTema() {
  const raiz = document.documentElement;
  if (temaEscolhido === 'claro' || temaEscolhido === 'escuro') raiz.dataset.tema = temaEscolhido;
  else delete raiz.dataset.tema;
  raiz.toggleAttribute('data-escuro', escuro());          // o ícone do botão
  if (visor && visor.piso) visor.definirTema(escuro());
}
ESCURO.addEventListener('change', aplicarTema);
document.getElementById('tema').onclick = () => {
  temaEscolhido = escuro() ? 'claro' : 'escuro';
  try { localStorage.setItem(TEMA, temaEscolhido); } catch (e) { /* sem armazenamento: vale até fechar */ }
  aplicarTema();
};
const INSTALADO = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
const IPHONE = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const DISPENSA = 'metalica-instalar-dispensado';
// escolhas pequenas guardadas no aparelho (a apresentação do 3D, 20/10); sem armazenamento, vale o padrão
const lerPreferencia = (k, padrao) => { try { return localStorage.getItem('pref.' + k) ?? padrao; } catch (e) { return padrao; } };
const gravarPreferencia = (k, v) => { try { localStorage.setItem('pref.' + k, v); } catch (e) { /* sem armazenamento: vale até fechar */ } };
const dispensado = () => { try { return localStorage.getItem(DISPENSA) === '1'; } catch (e) { return false; } };
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); pedidoInstalar = e; mostrarInstalar(); });
window.addEventListener('appinstalled', () => { pedidoInstalar = null; mostrarInstalar(); });

function cartaoInstalar() {
  if (INSTALADO() || dispensado()) return '';
  const APP = 'Abre como aplicativo, com o logo na tela inicial e sem a barra do navegador.';
  const cab = (titulo, sub = APP) => `<div class="instalar-cab"><img src="lib/icone-192.png" alt=""><div><b>${titulo}</b>
    <div class="mais-fraco">${sub}</div></div></div>`;
  if (pedidoInstalar) {
    return `<div class="cartao instalar">${cab('Instalar o Metálica')}
      <div class="instalar-botoes"><button class="botao" data-instalar="nao">Agora não</button>
      <button class="botao forte" data-instalar="sim">Instalar</button></div></div>`;
  }
  if (IPHONE) {
    return `<div class="cartao instalar">${cab('Pôr o Metálica na tela inicial')}
      <p class="instalar-passos">Toque em <b>Compartilhar</b> (o quadrado com a seta, embaixo) e depois em <b>Adicionar à Tela de Início</b>.</p>
      <div class="instalar-botoes"><button class="botao" data-instalar="nao">Entendi</button></div></div>`;
  }
  if (!window.isSecureContext) {
    /* Sem HTTPS o atalho abre no Chrome, com a barra — prometer "aplicativo" aqui seria mentira. */
    return `<div class="cartao instalar">${cab('Pôr o Metálica na tela inicial', 'Um toque no logo abre a lista de projetos.')}
      <p class="instalar-passos">No menu <b>⋮</b> do Chrome, <b>Adicionar à tela inicial</b> → <b>Criar atalho</b>: o atalho sai com o logo.
      Para instalar como aplicativo de verdade — e guardar os projetos para abrir na obra sem rede —, ligue a
      <b>Conexão segura (HTTPS)</b> no computador, em <i>Acesso pelo celular</i>.</p>
      <div class="instalar-botoes"><button class="botao" data-instalar="nao">Entendi</button></div></div>`;
  }
  return '';
}

function mostrarInstalar() {
  const el = $('#instalar');
  if (!el) return;
  el.innerHTML = cartaoInstalar();
  el.querySelectorAll('[data-instalar]').forEach(b => {
    b.onclick = async () => {
      if (b.dataset.instalar === 'sim' && pedidoInstalar) {
        const pedido = pedidoInstalar;
        pedidoInstalar = null;
        await pedido.prompt();
        await pedido.userChoice.catch(() => null);
      } else {
        try { localStorage.setItem(DISPENSA, '1'); } catch (e) { /* sem armazenamento: some só nesta visita */ }
      }
      el.innerHTML = '';
    };
  });
}

class SemPar extends Error {}
// Na nuvem (servicos/celular, 20/10) o celular não fala com o PC: o selo, a falta de rede e o "não liberado" dizem isso
let NUVEM = false;
class Preparando extends Error { constructor(info) { super('preparando'); this.info = info || {}; } }

async function buscar(url) {
  let r;
  try { r = await fetch(url, { credentials: 'same-origin' }); }
  catch (e) { throw new Error('sem conexão com o computador'); }
  if (r.headers.get('X-Metalica-Nuvem')) NUVEM = true;
  if (r.status === 401) throw new SemPar('aparelho não pareado');
  const copia = r.headers.get('X-Metalica-Copia');
  if (copia) { OFFLINE = true; if (copia !== '1') copiaDe = copia; }
  else if (!url.includes('?v=')) { OFFLINE = q.get('offline') === '1'; copiaDe = null; }
  if (r.status === 202) throw new Preparando(await r.json().catch(() => ({})));
  if (!r.ok) { const j = await r.json().catch(() => null); throw new Error((j && j.erro) || ('erro ' + r.status)); }
  return r;
}

// Só o que não muda fica guardado na memória da tela: os arquivos do pacote, pela versão (SHA-1)
// do manifesto. A lista e o manifesto vêm sempre do computador (projeto corrigido aparece ao voltar).
const cache = new Map();
async function json(caminho, versao) {
  if (!versao) return (await buscar(DADOS + caminho)).json();
  const chave = caminho + '?v=' + versao;
  if (!cache.has(chave)) cache.set(chave, buscar(DADOS + chave).then(r => r.json()).catch(e => { cache.delete(chave); throw e; }));
  return cache.get(chave);
}
/** URL de um arquivo do pacote com a versão dele (o navegador guarda e revalida pelo SHA-1). */
function arquivo(m, nome) {
  const a = (m.arquivos || []).find(x => x.nome === nome);
  return `${DADOS}${encodeURIComponent(m.projeto.slug)}/${nome}` + (a ? '?v=' + a.sha1.slice(0, 12) : '');
}
const versaoDe = (m, nome) => { const a = (m.arquivos || []).find(x => x.nome === nome); return a ? a.sha1.slice(0, 12) : 'x'; };

let estadoPC = null;
async function lerEstadoPC() {
  if (estadoPC !== null) return estadoPC;
  try { estadoPC = await (await buscar('api/estado')).json(); } catch (e) { if (e instanceof SemPar) throw e; estadoPC = false; }
  if (estadoPC && estadoPC.nuvem) NUVEM = true;
  return estadoPC;
}

function diag(chave, valor) {
  try { const d = JSON.parse(sessionStorage.getItem('diag') || '{}'); d[chave] = valor; sessionStorage.setItem('diag', JSON.stringify(d)); } catch (e) { /* sem armazenamento */ }
}
function lerDiag() { try { return JSON.parse(sessionStorage.getItem('diag') || '{}'); } catch (e) { return {}; } }

let visor = null;            // o 3D aberto (um por vez: o celular não guarda dois modelos)
let visorSlug = null;

function topo(titulo, sub, voltar) {
  $('#titulo').textContent = titulo;
  $('#subtitulo').textContent = sub || '';
  $('#voltar').hidden = !voltar;
  $('#voltar').onclick = voltar || null;
}

function conexao(manifestoGerado) {
  const c = $('#conexao');
  const pc = estadoPC && estadoPC.computador;
  if (OFFLINE) {
    c.className = 'chip offline';
    c.textContent = 'Sem rede · cópia ' + (copiaDe ? dataHora(copiaDe).slice(0, 5) : manifestoGerado ? dataHora(manifestoGerado).slice(0, 5) : '');
  } else {
    c.className = 'chip';
    // curto (20/10): o nome da obra precisa do espaço do cabeçalho; o computador e a hora do envio vão no toque
    c.textContent = NUVEM ? 'Nuvem' : 'No PC';
  }
  c.onclick = () => {
    abrirFolha(`<div class="ficha"><div class="nome">${OFFLINE ? 'Sem rede' : NUVEM ? 'Pela nuvem' : 'Ligado ao computador' + (pc ? ' ' + esc(pc) : '')}</div>
      <p class="fraco">${OFFLINE
        ? (NUVEM ? 'Você está vendo a cópia guardada no aparelho. Com internet de novo, o celular baixa sozinho só os projetos que mudaram.'
                 : 'Você está vendo a cópia guardada no aparelho. Quando voltar à rede do escritório, o celular baixa sozinho só os projetos que mudaram.')
        : NUVEM ? `O computador do escritório${pc ? ' (' + esc(pc) + ')' : ''} envia as obras para a nuvem quando elas mudam${estadoPC && estadoPC.enviado ? ' — último envio em ' + esc(dataHora(estadoPC.enviado)) : ''}. Funciona de qualquer lugar com internet, com o computador ligado ou não.`
        : 'O celular lê os projetos direto do programa no computador, pela rede Wi-Fi. Projeto importado ou corrigido no PC aparece aqui ao atualizar.'}</p>
      ${estadoPC ? `<p class="mais-fraco">Este aparelho: ${esc(estadoPC.aparelho)} · programa ${esc(estadoPC.programa)}</p>` : ''}
      <p class="mais-fraco">Só consulta: nada do que você faz aqui altera o projeto.</p>
      <div class="acoes"><button class="botao forte" id="atualizar">Atualizar</button><button class="botao" id="ir-diag">Diagnóstico</button></div></div>`);
    $('#atualizar').onclick = () => { fecharFolha(); rota(); };
    $('#ir-diag').onclick = () => { fecharFolha(); location.hash = '#/diagnostico'; };
  };
}

function abas(slug, ativa) {
  const nav = $('#abas');
  nav.hidden = !slug;
  document.body.classList.toggle('sem-abas', !slug);
  for (const b of nav.querySelectorAll('button')) {
    b.classList.toggle('ativa', b.dataset.aba === ativa);
    b.onclick = () => { location.hash = `#/p/${encodeURIComponent(slug)}/${b.dataset.aba}`; };
  }
}

function abrirFolha(html) {
  $('#folha-corpo').innerHTML = html;
  folha.hidden = false;
}
function fecharFolha() { folha.hidden = true; }
folha.querySelector('.alca').onclick = fecharFolha;

// ------------------------------------------------------------------ roteiro

async function rota() {
  fecharFolha();
  const partes = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  document.body.classList.remove('tela-cheia');
  clearTimeout(rota.espera);
  fecharLeitor();
  try {
    if (!OFFLINE) await lerEstadoPC();
    if (partes[0] === 'p' && partes[1]) await telaProjeto(partes[1], partes[2] || 'modelo', partes[3] || '');
    else if (partes[0] === 'leitor' && partes[1]) await telaLeitor(partes[1], partes[2], +(partes[3] || 1));
    else if (partes[0] === 'diagnostico') await telaDiagnostico();
    else await telaLista();
  } catch (e) {
    if (e instanceof SemPar) return telaSemPar();
    if (e instanceof Preparando) return telaPreparando(partes[1], e.info);
    abas(null);
    tela.innerHTML = NUVEM ? `<div class="vazio"><b>Não foi possível abrir</b>${esc(e.message || e)}<br><br>
      Confira a internet deste aparelho. Sem internet, abrem só os projetos já guardados nele.<br><br>
      <button class="botao forte" onclick="location.reload()">Tentar de novo</button></div>` : `<div class="vazio"><b>Não foi possível abrir</b>${esc(e.message || e)}<br><br>
      Confira se o computador está ligado, com o <i>Acesso pelo celular</i> ligado, e na mesma rede Wi-Fi deste
      aparelho (a rede de visitantes costuma separar os aparelhos). Computador em suspensão também some da rede.<br><br>
      <button class="botao forte" onclick="location.reload()">Tentar de novo</button></div>`;
  }
}
window.addEventListener('hashchange', rota);

function telaSemPar() {
  liberar3D();
  topo('Metálica', '', null);
  abas(null);
  tela.innerHTML = NUVEM ? `<div class="vazio"><b>Este aparelho não está liberado</b>
    Entre de novo com a chave da sua licença (ou leia o QR code no computador). Se a vaga deste celular foi liberada
    na tela de licenças, ele precisa entrar de novo.<br><br><button class="botao forte" onclick="location.replace('/celular/')">Entrar</button></div>`
    : `<div class="vazio"><b>Este aparelho não está ligado ao computador</b>
    No computador, abra <i>Projetos → Celular</i> (Acesso pelo celular) e leia o QR code com a câmera deste aparelho.</div>`;
}

function telaPreparando(slug, info) {
  liberar3D();
  topo('Preparando…', '', () => { location.hash = '#/'; });
  abas(null);
  const pct = Math.round((info.progresso || 0) * 100);
  tela.innerHTML = `<div class="vazio"><b>Preparando o projeto no computador</b>
    Na primeira vez o computador monta o pacote do celular (o 3D leve, os quantitativos e as pranchas).
    Projetos grandes levam até um minuto.
    <div class="barra" style="margin:18px auto 6px;max-width:240px"><i style="width:${Math.max(pct, 4)}%"></i></div>
    <span class="mais-fraco">${info.situacao === 'na fila' ? 'na fila' : pct + '%'}</span></div>`;
  rota.espera = setTimeout(rota, 2000);
}

// ------------------------------------------------------------------ lista de projetos

async function telaLista() {
  liberar3D();
  topo('Metálica', 'Projetos', null);
  abas(null);
  const idx = await json('projetos.json');
  conexao(idx.projetos[0] && idx.projetos[0].gerado);
  diag('projetos', idx.projetos.length);
  const guardados = lerGuardados();
  if (!OFFLINE) sincronizar(idx.projetos.filter(p => guardados[p.slug]).map(p => p.slug));
  const projetos = idx.projetos.slice().sort((a, b) => String(b.alterado).localeCompare(String(a.alterado)));
  tela.innerHTML = `<div id="instalar"></div><div class="busca"><input type="search" placeholder="Buscar projeto" aria-label="Buscar projeto"></div>
    ${OFFLINE ? '<div class="aviso-topo">Sem rede: estes são os projetos guardados no aparelho.</div>' : ''}
    <div class="lista-cartoes"></div>`;
  const lista = $('.lista-cartoes');
  const desenhar = filtro => {
    const f = (filtro || '').toLowerCase();
    lista.innerHTML = projetos.filter(p => !f || (p.nome + ' ' + p.slug + ' ' + (p.cliente || '')).toLowerCase().includes(f)).map(p => {
      const n = p.numeros || {};
      return `<a class="cartao toque projeto" href="#/p/${encodeURIComponent(p.slug)}/modelo" style="display:block;color:inherit;text-decoration:none">
        <div class="linha"><div class="nome">${esc(p.nome || p.slug)}</div>${p.revisao ? `<span class="etiqueta">${esc(p.revisao)}</span>` : ''}</div>
        <div class="mais-fraco">alterado ${dataHora(p.alterado)}</div>
        ${p.numeros ? `<div class="numeros"><span><b>${n.peso_kg ? kg(n.peso_kg) : '—'}</b> aço</span><span><b>${nf(n.pecas)}</b> peças</span>
          <span><b>${nf(n.pranchas)}</b> pranchas</span></div>` : ''}
        <div class="etiquetas" data-slug="${esc(p.slug)}">${OFFLINE ? (guardados[p.slug] ? `<span class="etiqueta ok">no aparelho · ${dataHora(guardados[p.slug].gerado).slice(0, 5)}</span>` : '<span class="etiqueta">não guardado no aparelho</span>')
          : guardados[p.slug] && COPIA_OK ? `<span class="etiqueta ok">guardado para a obra</span>${p.atual === false ? '<span class="etiqueta aviso">mudou no PC</span>' : ''}`
          : p.bytes ? `<span class="etiqueta">${nf(p.bytes / 1048576, 1)} MB para a obra</span>${p.atual === false ? '<span class="etiqueta aviso">mudou no PC</span>' : ''}`
          : '<span class="etiqueta">prepara ao abrir</span>'}</div>
      </a>`;
    }).join('') || '<div class="vazio"><b>Nenhum projeto</b>Nada com esse nome.</div>';
  };
  desenhar('');
  $('.busca input').oninput = e => desenhar(e.target.value);
  mostrarInstalar();
}

// ------------------------------------------------------------------ projeto

async function telaProjeto(slug, aba, extra) {
  const m = await json(`${slug}/manifesto.json`);
  const p = m.projeto;
  topo(p.nome || slug, m.atualizando ? 'atualizando no computador…'
    : [p.revisao, 'pacote de ' + dataHora(m.gerado)].filter(Boolean).join(' · '), () => { location.hash = '#/'; });
  if (m.atualizando) vigiarAtualizacao(slug, m.gerado);
  if (!OFFLINE && !m.atualizando) guardarProjeto(slug, m);
  conexao(m.gerado);
  abas(slug, aba);
  if (aba !== 'modelo') liberar3D();
  if (aba === 'modelo') return telaModelo(slug, m, extra === 'medir');
  if (aba === 'quantitativos') return telaQuantitativos(slug, m);
  if (aba === 'resumos') return telaResumos(slug, m);
  if (aba === 'pranchas') return telaPranchas(slug, m);
}

/** O computador está refazendo o pacote: confere de tempos em tempos e, pronto, avisa. */
function vigiarAtualizacao(slug, gerado) {
  clearTimeout(vigiarAtualizacao.t);
  vigiarAtualizacao.t = setTimeout(async () => {
    if (!location.hash.includes(encodeURIComponent(slug)) && !location.hash.includes(slug)) return;
    try {
      const m = await json(`${slug}/manifesto.json`);
      if (m.atualizando) return vigiarAtualizacao(slug, gerado);
      if (m.gerado !== gerado) {
        $('#subtitulo').textContent = 'versão nova pronta';
        abrirFolha(`<div class="ficha"><div class="nome">O projeto mudou no computador</div>
          <p class="fraco">A versão nova está pronta.</p><div class="acoes"><button class="botao forte" id="recarregar">Abrir a versão nova</button></div></div>`);
        $('#recarregar').onclick = () => { fecharFolha(); liberar3D(); rota(); };
      }
    } catch (e) { /* fora da rede: tenta na próxima */ }
  }, 4000);
}

// ------------------------------------------------------------------ Modelo 3D

function liberar3D() {
  if (visor) { visor.descartar(); visor = null; visorSlug = null; }
}

/** A situação da cobertura retrátil escolhida no celular, por projeto (sem escolha: a gravada no PC). */
const coberturaVista = {};

async function telaModelo(slug, m, medir, camera) {
  document.body.classList.add('tela-cheia');
  /* A cobertura retrátil (19/10): o pacote leva as duas situações prontas (saida/pacote_celular.py) — no PC "ver
   * aberta/retraída" grava o modelo, aqui só se troca o arquivo que o 3D lê. */
  const cm = m.cobertura_movel;
  const situacao = cm ? (cm.situacoes[coberturaVista[slug]] ? coberturaVista[slug] : cm.atual) : null;
  const arqs = cm ? cm.situacoes[situacao] : { modelo: 'modelo3d.mcel', pecas: 'pecas.json' };
  if (!m.arquivos.some(a => a.nome === 'modelo3d.mcel')) {
    tela.innerHTML = '<div class="vazio" style="padding-top:120px"><b>Sem modelo 3D</b>Este projeto ainda não tem modelo.</div>';
    return;
  }
  tela.innerHTML = `<div class="palco"><canvas></canvas>
    <div class="carregando"><div>Abrindo o 3D…<div class="progresso"><i></i></div><div class="mais-fraco" id="baixado"></div></div></div>
    <div class="palco-topo"><div class="contagem" hidden></div></div>
    <div class="ferramentas" hidden>
      <button data-f="camadas" aria-label="Camadas"><svg viewBox="0 0 24 24"><path d="M12 3l9 5-9 5-9-5z M3 13l9 5 9-5 M3 17.5l9 5 9-5"/></svg></button>
      <button data-f="vistas" aria-label="Vistas"><svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button>
      <button data-f="maquete" aria-label="Maquete na mesa (realidade aumentada)"><svg viewBox="0 0 24 24"><path d="M3 8V3h5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5"/><path d="M12 6.5l4.5 2.5v5.5L12 17l-4.5-2.5V9z M7.5 9L12 11.5 16.5 9 M12 11.5V17"/></svg></button>
      <button data-f="buscar" aria-label="Buscar peça"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg></button>
      <button data-f="apresentacao" aria-label="Apresentação (sol e sombras)"><svg viewBox="0 0 24 24"><path d="M5 9l5-3 5 3v5l-5 3-5-3z"/><path d="M10 17l9 2.5-4-5.5" opacity=".55"/><circle cx="19" cy="5" r="2"/></svg></button>
      <button data-f="arestas" class="ligado" aria-label="Arestas"><svg viewBox="0 0 24 24"><path d="M4 7l8-4 8 4v10l-8 4-8-4z"/></svg></button>
      <button data-f="enquadrar" aria-label="Enquadrar"><svg viewBox="0 0 24 24"><path d="M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5"/></svg></button>
    </div></div>`;
  // o nome debaixo de cada ícone da barra (usuário, 20/10: "não entendi o que são esses botões")
  const ROTULOS = { camadas: 'Camadas', vistas: 'Vistas', maquete: 'Maquete', buscar: 'Buscar', apresentacao: 'Sol', arestas: 'Arestas', enquadrar: 'Enquadrar' };
  for (const b of tela.querySelectorAll('.ferramentas button')) {
    if (ROTULOS[b.dataset.f]) b.insertAdjacentHTML('beforeend', `<span class="rotulo">${ROTULOS[b.dataset.f]}</span>`);
  }
  const { Visor3D } = await import('../visor3d/visor3d.js');
  liberar3D();
  const canvas = $('.palco canvas');
  /* O tema do APARELHO, como o resto das telas (o CSS segue prefers-color-scheme). O visor nascia com o
   * fundo claro de fábrica e nunca ouvia o tema: o 3D ficava claro no celular escuro (19/10). */
  visor = new Visor3D(canvas, { maxPixelRatio: 2, fundo: escuro() ? '#0e131a' : '#f4f6fa' });
  visorSlug = slug;
  const v = visor;
  const t0 = performance.now();
  v.urlModelo = arquivo(m, arqs.modelo);          // a maquete da realidade aumentada relê o mesmo arquivo
  // e, na cobertura retrátil, a maquete leva também a outra situação (usuário, 20/10: "ter a visualização do modelo
  // aberto e fechado na maquete")
  const ROTULO_SITUACAO = { aberta: 'Aberta', retraida: 'Retraída' };
  v.situacaoRA = cm ? { rotulo: ROTULO_SITUACAO[situacao] || situacao } : null;
  v.outrasSituacoesRA = cm ? Object.keys(cm.situacoes).filter(k => k !== situacao).map(k => ({ rotulo: ROTULO_SITUACAO[k] || k,
    modelo: arquivo(m, cm.situacoes[k].modelo), pecas: () => json(`${slug}/${cm.situacoes[k].pecas}`, versaoDe(m, cm.situacoes[k].pecas)) })) : [];
  const tempos = await v.carregar(v.urlModelo, (f, txt) => {
    $('.progresso i').style.width = Math.round(f * 100) + '%';
    $('#baixado').textContent = txt;
  });
  if (v !== visor) return;          // trocou de tela no meio
  v.definirTema(escuro());          // depois de carregar: o piso se acomoda à caixa do modelo
  // apresentação (20/10, para mostrar ao cliente): sol e sombras, ligada de saída; a escolha fica guardada no aparelho
  v.ligarApresentacao(lerPreferencia('apresentacao', '1') === '1', 2048);
  // a posição do sol, escolhida em Vistas e guardada por obra (20/10)
  const SOL = await import('../visor3d/sol.js');
  SOL.definirSol(v, SOL.lerSol('sol:' + slug));
  v.definirFichas(await json(`${slug}/${arqs.pecas}`, versaoDe(m, arqs.pecas)));
  // como no modo ver do PC (20/10): os sistemas (metálica, pré-moldado…) e o desenho do piso (planta, eixos, níveis)
  const { gruposDeSistema } = await import('../visor3d/sistemas.js');
  v.sistemas = gruposDeSistema(v);
  PISO_NOMES = (await import('../visor3d/referencia.js')).PARTES_PISO;
  if (m.referencia) {
    try { await v.definirReferencia(await json(`${slug}/${m.referencia}`, versaoDe(m, m.referencia))); }
    catch (e) { /* sem o desenho do piso, o resto abre igual */ }
  }
  if (v !== visor) return;
  aplicarCamadas(v, slug);          // as camadas que a pessoa desligou neste projeto continuam desligadas
  if (Object.keys(coresEscolhidas(slug)).length) aplicarCores(v, slug);    // e as cores que ela escolheu
  if (camera) {                     // trocou a situação da cobertura: a vista fica onde estava
    v.camera.position.copy(camera.posicao);
    v.controles.target.copy(camera.alvo);
    v.controles.update();
    v.pedirQuadro();
  }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));     // os números do quadro já com as camadas
  diag('ultimo3d', { slug, nome: m.projeto.nome, ms: Math.round(performance.now() - t0), ...tempos, ...v.numeros(),
                     mb: Math.round(((m.arquivos.find(a => a.nome === arqs.modelo) || {}).bytes || 0) / 104857.6) / 10 });
  $('.carregando').remove();
  $('.ferramentas').hidden = false;
  $('[data-f="apresentacao"]').classList.toggle('ligado', !!v.apresentacao);
  const contagem = $('.contagem');
  contagem.hidden = false;
  contagem.textContent = `${nf(v.nPecas)} peças`;
  window.visor = v;
  if (medir) setTimeout(() => medirFluidez(v), 300);

  // toque: um toque escolhe a peça, dois toques giram em volta dela
  let ini = null, ultimo = 0;
  canvas.addEventListener('pointerdown', e => { ini = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  canvas.addEventListener('pointerup', e => {
    if (!ini) return;
    const mexeu = Math.hypot(e.clientX - ini.x, e.clientY - ini.y) > 8 || performance.now() - ini.t > 400;
    ini = null;
    if (mexeu) return;
    const r = canvas.getBoundingClientRect();
    const id = v.escolher(e.clientX - r.left, e.clientY - r.top);
    const agora = performance.now();
    if (id >= 0 && agora - ultimo < 320) v.centrarEm(id);
    ultimo = agora;
    v.selecionar(id);
    if (id >= 0) mostrarFicha(v, id); else fecharFolha();
  });

  for (const b of tela.querySelectorAll('.ferramentas button')) {
    b.onclick = () => {
      const f = b.dataset.f;
      if (f === 'arestas') { b.classList.toggle('ligado'); v.ligarArestas(b.classList.contains('ligado')); }
      else if (f === 'apresentacao') {
        b.classList.toggle('ligado');
        const sim = b.classList.contains('ligado');
        gravarPreferencia('apresentacao', sim ? '1' : '0');
        v.ligarApresentacao(sim, 2048);
      }
      else if (f === 'enquadrar') v.enquadrar('iso');
      else if (f === 'camadas') folhaCamadas(v);
      else if (f === 'maquete') abrirMaquete(v, null, m.projeto.nome);      // o atalho da realidade aumentada (usuário, 20/10)
      else if (f === 'vistas') {
        /* A cobertura retrátil mora aqui, junto das vistas (pedido do usuário, 19/10: "para não precisar criar um
         * menu novo só para isso") — e só no projeto que tem uma. */
        abrirFolha(`<div class="nome">Vistas</div><div class="etiquetas" style="margin-top:12px">
          ${['iso:Perspectiva', 'topo:Planta', 'frente:Frente', 'lado:Lateral'].map(x => { const [k, t] = x.split(':'); return `<button class="botao" data-v="${k}">${t}</button>`; }).join('')}</div>
          ${cm ? `<div class="nome" style="margin-top:16px">Cobertura retrátil</div><div class="etiquetas cobertura" style="margin-top:12px">
            ${[['aberta', 'Aberta'], ['retraida', 'Retraída']].map(([k, t]) => `<button class="botao${k === situacao ? ' forte' : ''}" data-s="${k}">${t}</button>`).join('')}</div>` : ''}
          <div class="nome" style="margin-top:16px">Sol</div>${SOL.controlesDoSol(SOL.lerSol('sol:' + slug))}
          <div class="nome" style="margin-top:16px">Realidade aumentada</div>
          <p class="mais-fraco dica-cor">A obra como está na tela (camadas e cores), em maquete na mesa, pela câmera.</p>
          <button class="botao forte" id="ra-obra">Maquete na mesa</button>`);
        $('#ra-obra').onclick = () => abrirMaquete(v, null, m.projeto.nome);
        // mexer no sol liga a apresentação (o sol só aparece nela) e guarda a escolha para esta obra
        SOL.ligarControlesDoSol(folha, SOL.lerSol('sol:' + slug), s => {
          if (!v.apresentacao) {
            v.ligarApresentacao(true, 2048);
            gravarPreferencia('apresentacao', '1');
            $('[data-f="apresentacao"]').classList.add('ligado');
          }
          SOL.definirSol(v, s);
          SOL.gravarSol('sol:' + slug, s);
        });
        folha.querySelectorAll('[data-v]').forEach(x => x.onclick = () => { v.enquadrar(x.dataset.v); fecharFolha(); });
        folha.querySelectorAll('[data-s]').forEach(x => x.onclick = () => {
          fecharFolha();
          if (x.dataset.s === situacao) return;
          coberturaVista[slug] = x.dataset.s;
          telaModelo(slug, m, false, { posicao: v.camera.position.clone(), alvo: v.controles.target.clone() });
        });
      }
      else if (f === 'buscar') folhaBuscar(v);
    };
  }
}

/** Gira o modelo uma volta inteira em 4 s e conta os quadros (a fluidez no aparelho). */
function medirFluidez(v) {
  abrirFolha('<div class="ficha"><div class="nome">Medindo a fluidez…</div><p class="fraco">Não toque na tela por 4 segundos.</p></div>');
  const alvo = v.controles.target.clone(), pos = v.camera.position.clone().sub(alvo);
  v._movendo(true);                              // como o dedo girando: resolução de movimento, sem arestas
  const t0 = performance.now();
  let quadros = 0, pior = 0, ult = t0;
  const passo = agora => {
    const t = (agora - t0) / 4000;
    const a = Math.min(t, 1) * Math.PI * 2, c = Math.cos(a), s = Math.sin(a);
    v.camera.position.set(alvo.x + pos.x * c - pos.y * s, alvo.y + pos.x * s + pos.y * c, alvo.z + pos.z);
    v.camera.lookAt(alvo);
    v.renderer.render(v.cena, v.camera);
    quadros++;
    pior = Math.max(pior, agora - ult);
    ult = agora;
    if (t < 1) requestAnimationFrame(passo);
    else {
      v._movendo(false);
      const qps = Math.round(quadros / ((agora - t0) / 1000));
      diag('fluidez', { qps, pior_ms: Math.round(pior), quando: new Date().toISOString() });
      abrirFolha(`<div class="ficha"><div class="nome">${qps} quadros por segundo</div>
        <p class="fraco">${qps >= 40 ? 'Fluido.' : qps >= 20 ? 'Usável: gira com pequenos saltos.' : 'Pesado: os parafusos com menos facetas e as peças pequenas que somem de longe vão ajudar.'}
        Pior quadro: ${Math.round(pior)} ms.</p><div class="acoes"><button class="botao forte" id="ir-diag2">Ver o diagnóstico</button></div></div>`);
      $('#ir-diag2').onclick = () => { fecharFolha(); location.hash = '#/diagnostico'; };
    }
  };
  requestAnimationFrame(passo);
}

function mostrarFicha(v, i) {
  const f = v.fichas[i];
  const cam = v.cabecalho.camadas[f.c] || {};
  const linhas = [
    ['Perfil', f.p], ['Camada', cam.nome], ['Material', f.m], ['Peso', f.kg ? kg(f.kg) : null],
    ['Posição', f.pos], ['Conjunto', f.cj], ['Marca', f.mc],
  ].filter(x => x[1]);
  abrirFolha(`<div class="ficha"><div class="nome">${esc(f.n || 'Peça sem nome')}</div>
    <dl>${linhas.map(([k, val]) => `<dt>${k}</dt><dd>${esc(val)}</dd>`).join('')}</dl>
    <div class="acoes"><button class="botao forte" id="centrar">Girar em volta</button><button class="botao" id="na-mesa">Na mesa</button>
      <button class="botao" id="soltar">Fechar</button></div></div>`);
  $('#centrar').onclick = () => v.centrarEm(i);
  $('#na-mesa').onclick = async () => {
    const { conjuntoDa } = await import('./maquete.js');
    const c = conjuntoDa(v, i);
    abrirMaquete(v, c.ids, c.nome);
  };
  $('#soltar').onclick = () => { v.selecionar(-1); fecharFolha(); };
}

/** A maquete na mesa (realidade aumentada, 20/10: "mostrar com a câmera a peça no mundo real... tipo uma maquete"):
 *  montada no aparelho a partir do 3D aberto — `ids` (o conjunto da ficha) ou o que está à vista — e aberta na câmera
 *  pelo AR Quick Look no iPhone e pela realidade aumentada do Chrome no Android (maquete.js). */
let maqueteAnterior = [];
async function abrirMaquete(v, ids, nome) {
  const titulo = `<div class="nome">Maquete: ${esc(nome || 'obra')}</div>`;
  const andamento = (texto) => abrirFolha(`<div class="ficha">${titulo}<p class="fraco">${texto}</p><div class="progresso"><i id="ra-barra"></i></div></div>`);
  andamento('Montando a maquete…');
  try {
    const M = await import('./maquete.js');
    maqueteAnterior.forEach(g => M.descartar(g)); maqueteAnterior = [];
    const como = await M.comoAbrir(), android = como === 'webxr';
    // o Android desenha a obra quase inteira, com as arestas e todas as camadas (para ligar e desligar na câmera); o
    // .usdz do iPhone é texto e leva menos, só o que está à vista (maquete.js, LIMITES)
    const opcoes = { limite: M.LIMITES[como] || M.LIMITES.quicklook, arestas: android, todas: android && !ids,
                     aoAndar: f => { const b = $('#ra-barra'); if (b) b.style.width = Math.round(f * 100) + '%'; } };
    const r = await M.montarMaquete(v, await (await fetch(v.urlModelo)).arrayBuffer(), { ...opcoes, ids });
    if (!r.pecas) { abrirFolha(`<div class="ficha">${titulo}<p class="fraco">Não há peças à vista para a maquete: ligue as camadas em Camadas.</p></div>`); return; }
    // a cobertura retrátil (usuário, 20/10): a outra situação no mesmo quadro — a parte fixa fica no lugar ao trocar
    const situacoes = [{ rotulo: v.situacaoRA ? v.situacaoRA.rotulo : '', r }];
    for (const s of v.outrasSituacoesRA || []) {
      andamento(`Montando a maquete ${s.rotulo.toLowerCase()}…`);
      const fichas = (await s.pecas()).pecas, buf2 = await (await fetch(s.modelo)).arrayBuffer();
      const w = M.visorDaOutra(v, fichas, M.lerCabecalho(buf2).camadas);
      let ids2 = null;
      if (ids) { const pos = new Map(fichas.map((f, j) => [f.id, j])); ids2 = ids.map(i => pos.get(v.fichas[i].id)).filter(j => j !== undefined); }
      situacoes.push({ rotulo: s.rotulo, r: await M.montarMaquete(w, buf2, { ...opcoes, ids: ids2, quadro: r.quadro }) });
    }
    // os eixos, os níveis e o arquitetônico, na câmera do Android (o .usdz não leva linhas)
    const piso = android && !ids ? await M.pisoDaMaquete(v._dadosReferencia, r.quadro, v.cabecalho.origem, v._caixaModelo) : null;
    // as cotas principais (comprimento, largura e altura totais) — também no conjunto (a tesoura)
    const cotas = android ? M.cotasDaMaquete(r) : null;
    maqueteAnterior = situacoes.map(s => s.r.grupo).concat(piso ? [piso] : [], cotas ? [cotas] : []);
    window.ultimaMaquete = { pecas: r.pecas, triangulos: r.triangulos, arestas: r.arestas, deFora: r.deFora, simplificadas: r.simplificadas,
                             escala: r.escala, medidas: r.medidas, como, situacoes: situacoes.map(s => s.rotulo), camadas: r.camadas.length,
                             piso: piso ? piso.userData.partes : [], cotas: cotas ? cotas.userData.textos : [] };
    const m = r.medidas.map(x => x.toFixed(1).replace('.', ',')).join(' × ');
    abrirFolha(`<div class="ficha">${titulo}<p class="fraco">${nf(r.pecas)} peças · escala 1:${nf(r.escala)} · ${m} m na obra${r.deFora
        ? `<br>${nf(r.deFora)} peças pequenas ficaram de fora (parafusos, porcas, arruelas…)` : ''}${r.simplificadas
        ? `<br>${nf(r.simplificadas)} peças pesadas vão só com a forma de fora (lajes alveolares, blocos…), para a maquete abrir leve` : ''}${
        situacoes.length > 1 && android ? `<br>${situacoes.map(s => s.rotulo).join(' e ')}: troque na câmera` : ''}${
        android ? `<br>Na câmera, o botão Camadas liga e desliga as camadas${ids ? '' : ', os eixos, os níveis'} e as cotas` : ''}</p>
      <div class="acoes" id="ra-acoes"></div>
      <p class="mais-fraco dica-cor">${como ? 'Aponte a câmera para uma mesa ou o chão, com boa luz, e mova o celular devagar até ela achar a superfície.'
        : 'Este aparelho ou navegador não abre realidade aumentada. No iPhone, use o Safari; no Android, o Chrome (com o "Google Play Services para RA") pela nuvem ou por conexão segura.'}</p></div>`);
    const acoes = $('#ra-acoes'), fechar = document.createElement('button');
    fechar.className = 'botao'; fechar.textContent = 'Fechar'; fechar.onclick = fecharFolha;
    if (como === 'quicklook') {
      // o Quick Look não aceita botões nossos: um link por situação (Abrir aberta / Abrir retraída)
      acoes.textContent = 'Preparando o arquivo…';
      const links = [];
      window.ultimaMaquete.bytes = 0;
      for (const s of situacoes) {
        const blob = await M.usdz(s.r.grupo);
        window.ultimaMaquete.bytes += blob.size;
        links.push(M.linkQuickLook(blob, situacoes.length > 1 ? `Abrir ${s.rotulo.toLowerCase()}` : 'Abrir na câmera'));
      }
      maqueteAnterior.forEach(g => M.descartar(g)); maqueteAnterior = [];     // o Quick Look abre os arquivos; as malhas não são mais usadas
      acoes.textContent = '';
      acoes.append(...links);
    } else if (como === 'webxr') {
      const abrir = document.createElement('button');
      abrir.className = 'botao forte'; abrir.textContent = 'Abrir na câmera';
      const desligadas = [
        ...r.camadas.filter(c => !c.ligada).map(c => 'camada:' + c.nome),
        ...r.sistemas.filter(s => !s.ligado).map(s => 'sistema:' + s.chave),
        ...(piso ? piso.userData.partes.filter(k => v._partesOcultas && v._partesOcultas.has(k)).map(k => 'piso:' + k) : []),
      ];
      const camadas = { camadas: r.camadas, sistemas: r.sistemas, desligadas,
                        partes: (piso ? piso.userData.partes.map(k => [k, ...(PISO_NOMES[k] || [k, '#999'])]) : [])
                          .concat(cotas ? [['cotas', 'Cotas principais', '#1f5fbf']] : []) };
      abrir.onclick = async () => {
        fecharFolha();
        try {
          await M.abrirWebXR({ situacoes: situacoes.map(s => ({ rotulo: s.rotulo, grupo: s.r.grupo })), piso, cotas, camadas, escala: r.escala,
                               sol: v._luz ? v._luz.uSol.value.toArray() : null,         // o sol da obra (Vistas): a sombra cai como no 3D
                               aoSair: () => { maqueteAnterior.forEach(g => M.descartar(g)); maqueteAnterior = []; } });
        } catch (e) { abrirFolha(`<div class="ficha">${titulo}<p class="fraco">A câmera não abriu: ${esc(e.message || e)}</p></div>`); }
      };
      acoes.append(abrir);
    }
    acoes.append(fechar);
  } catch (e) {
    abrirFolha(`<div class="ficha">${titulo}<p class="fraco">Não deu para montar a maquete: ${esc(e.message || e)}</p></div>`);
  }
}

// As camadas ligadas e desligadas, por projeto e pelo NOME da camada (19/10): ficavam só no 3D aberto, e trocar
// aberta/retraída, sair e voltar ou reabrir o projeto religava tudo — a lona desligada voltava. Pelo nome, e não pela
// posição: as duas situações da cobertura não trazem as camadas necessariamente na mesma ordem.
const CAMADAS = 'metalica-camadas:';
const camadasNaMemoria = {};
function camadasEscolhidas(slug) {
  if (!camadasNaMemoria[slug]) {
    try { camadasNaMemoria[slug] = JSON.parse(localStorage.getItem(CAMADAS + slug)) || {}; } catch (e) { camadasNaMemoria[slug] = {}; }
  }
  return camadasNaMemoria[slug];
}
function lembrarCamada(slug, nome, visivel) {
  const c = camadasEscolhidas(slug);
  c[nome] = visivel;
  try { localStorage.setItem(CAMADAS + slug, JSON.stringify(c)); } catch (e) { /* sem armazenamento: vale até fechar */ }
}
function aplicarCamadas(v, slug) {
  const c = camadasEscolhidas(slug);
  v.cabecalho.camadas.forEach((cam, i) => {
    if (typeof c[cam.nome] === 'boolean' && (v.visivelCamada[i] !== false) !== c[cam.nome]) v.mostrarCamada(i, c[cam.nome]);
  });
  for (const n of v.partesReferencia()) if (c['piso:' + n] === false) v.mostrarParteReferencia(n, false);
  for (const g of v.sistemas || []) if (c['sistema:' + g.chave] === false) v.ocultarSistema(g.ids, true);
}

// A cor de cada camada e de cada sistema, trocada no quadradinho da folha Camadas (usuário, 20/10: "alterar a cor da
// layer também, isso fica só na versão dele"): guardada só neste aparelho, por obra, pelo nome da camada ou a chave do
// sistema; uma peça na camada e no sistema pintados fica com a cor escolhida por último
const CORES = 'metalica-cores:';
const coresNaMemoria = {};
function coresEscolhidas(slug) {
  if (!coresNaMemoria[slug]) {
    try { coresNaMemoria[slug] = JSON.parse(localStorage.getItem(CORES + slug)) || {}; } catch (e) { coresNaMemoria[slug] = {}; }
  }
  return coresNaMemoria[slug];
}
function lembrarCor(slug, chave, hex) {
  const c = coresEscolhidas(slug);
  delete c[chave];                  // a escolhida por último vai para o fim e pinta por cima
  if (hex) c[chave] = hex;
  try { localStorage.setItem(CORES + slug, JSON.stringify(c)); } catch (e) { /* sem armazenamento: vale até fechar */ }
}
function esquecerCores(slug) {
  coresNaMemoria[slug] = {};
  try { localStorage.removeItem(CORES + slug); } catch (e) { /* sem armazenamento */ }
}
/** As cores do modelo (pelo material) e, por cima, as escolhidas neste aparelho. */
function aplicarCores(v, slug) {
  v.corBase.set(v.corMaterial);
  for (const [chave, hex] of Object.entries(coresEscolhidas(slug))) {
    const ids = chave.startsWith('sistema:') ? ((v.sistemas || []).find(g => g.chave === chave.slice(8)) || {}).ids || []
      : chave.startsWith('camada:') ? idsDaCamada(v, chave.slice(7)) : [];
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    for (const i of ids) { v.corBase[i * 3] = r; v.corBase[i * 3 + 1] = g; v.corBase[i * 3 + 2] = b; }
  }
  v._repintar();
}
/** O quadradinho com a cor que as peças do grupo têm no 3D (usuário, 20/10: "a layer está com a bolinha de uma cor e no
 *  modelo está outra"): antes era a cor da camada no arquivo, quase sempre cinza, e o 3D pinta pelo material. A cor mais
 *  comum entre as peças, clareada como no tema claro do visor; grupo com mais de uma cor mostra as principais lado a lado.
 *  Devolve [o fundo do quadradinho, a cor de base para o seletor]. */
const CLAREAR_NO_CLARO = 0.45;     // o mesmo do visor3d.js
function corNoModelo(v, ids) {
  if (!ids.length) return null;
  const conta = new Map(), cb = v.corBase, passo = Math.max(1, Math.floor(ids.length / 5000));
  for (let k = 0; k < ids.length; k += passo) { const i = ids[k] * 3, c = (cb[i] << 16) | (cb[i + 1] << 8) | cb[i + 2]; conta.set(c, (conta.get(c) || 0) + 1); }
  const k0 = v.escuro ? 0 : CLAREAR_NO_CLARO, tot = Math.ceil(ids.length / passo);
  const hex = (c, claro) => '#' + [16, 8, 0].map(s => { const x = (c >> s) & 255; return Math.trunc(claro ? x + (255 - x) * k0 : x).toString(16).padStart(2, '0'); }).join('');
  const prim = [...conta].sort((a, b) => b[1] - a[1]).filter(([, n], j) => j === 0 || n / tot >= 0.05).slice(0, 3);
  const fundo = prim.length === 1 ? hex(prim[0][0], true)
    : `linear-gradient(90deg, ${prim.map(([c], j) => `${hex(c, true)} ${j * 100 / prim.length}% ${(j + 1) * 100 / prim.length}%`).join(', ')})`;
  return [fundo, hex(prim[0][0], false)];
}
function idsDaCamada(v, nome) {
  const cams = v.cabecalho.camadas, n = Math.min(v.fichas.length, v.nPecas), ids = [];
  for (let i = 0; i < n; i++) if ((cams[v.fichas[i].c] || {}).nome === nome) ids.push(i);
  return ids;
}
function pintarQuadradinhos(v) {
  folha.querySelectorAll('.camada i.cor').forEach(el => {
    const chave = el.dataset.cor;
    const ids = chave.startsWith('sistema:') ? ((v.sistemas || []).find(g => g.chave === chave.slice(8)) || {}).ids || [] : idsDaCamada(v, chave.slice(7));
    const cor = corNoModelo(v, ids);
    if (cor) { el.style.background = cor[0]; el.dataset.base = cor[1]; }
  });
}
let seletorCor = null;
function escolherCor(v, el) {
  if (!seletorCor) {
    seletorCor = document.createElement('input');
    seletorCor.type = 'color';
    seletorCor.id = 'seletor-cor';
    Object.assign(seletorCor.style, { position: 'fixed', left: '50%', bottom: '40%', width: '1px', height: '1px', opacity: '0', border: '0', padding: '0' });
    document.body.appendChild(seletorCor);
  }
  const chave = el.dataset.cor;
  seletorCor.value = /^#[0-9a-f]{6}$/i.test(el.dataset.base || '') ? el.dataset.base : '#8a94a6';
  seletorCor.oninput = seletorCor.onchange = () => {
    lembrarCor(visorSlug, chave, seletorCor.value);
    aplicarCores(v, visorSlug);
    pintarQuadradinhos(v);          // a peça da camada é também do sistema: os dois quadradinhos acompanham
    $('#cores-originais').hidden = false;
  };
  try { seletorCor.showPicker(); } catch (e) { seletorCor.click(); }
}

let PISO_NOMES = {};                 // os nomes das partes do piso: os do modo ver do PC (referencia.js, lido ao abrir o 3D)

/** As camadas como no painel do modo ver do PC (20/10, "na tela do mobile não aparecem as mesmas camadas que aparecem no
 *  sistema"): No piso (planta, eixos, níveis), Sistema (metálica, pré-moldado…, quando há mais de um) e as do Modelo. */
function folhaCamadas(v) {
  const cams = v.cabecalho.camadas, cores = coresEscolhidas(visorSlug);
  // o quadradinho da camada e do sistema troca a cor e mostra a das peças no 3D (o do piso não: são as linhas do desenho)
  const linha = (tipo, k, cor, nome, n, ligada, chaveCor) => `<div class="camada" data-tipo="${tipo}" data-k="${esc(k)}">${chaveCor
      ? `<i class="cor" data-cor="${esc(chaveCor)}" role="button" aria-label="Trocar a cor de ${esc(nome)}"></i>`
      : `<i style="background:${esc(cor)}"></i>`}
    <span>${esc(nome)}${n != null ? `<br><span class="mais-fraco">${nf(n)} peças</span>` : ''}</span><div class="chave ${ligada ? 'ligada' : ''}"></div></div>`;
  const ocultasPiso = (v._partesOcultas || new Set());
  const piso = v.partesReferencia();
  const sistemas = (v.sistemas || []).length >= 2 ? v.sistemas : [];
  const secoes = [];
  if (piso.length) secoes.push('<div class="titulo-secao">No piso</div>' + piso.map(n => { const [nome, cor] = PISO_NOMES[n] || [n, '#999'];
    return linha('piso', n, cor, nome, null, !ocultasPiso.has(n)); }).join(''));
  if (sistemas.length) secoes.push('<div class="titulo-secao">Sistema</div>' + sistemas.map(g =>
    linha('sistema', g.chave, g.cor, g.nome, g.n, !g.ids.some(i => v.ocultasSistema.has(i)), 'sistema:' + g.chave)).join(''));
  const modelo = cams.map((c, i) => c.pecas ? linha('camada', i, c.cor, c.nome, c.pecas, v.visivelCamada[i] !== false, 'camada:' + c.nome) : '').join('');
  secoes.push((secoes.length ? '<div class="titulo-secao">Modelo</div>' : '') + modelo);
  abrirFolha(`<div class="nome">Camadas</div><div style="margin-top:6px">${secoes.join('')}</div>
    <p class="mais-fraco dica-cor">Toque no quadradinho para trocar a cor. A cor fica só neste aparelho.</p>
    <button class="botao" id="cores-originais" ${Object.keys(cores).length ? '' : 'hidden'}>Voltar às cores do modelo</button>`);
  pintarQuadradinhos(v);
  folha.querySelectorAll('.camada i.cor').forEach(el => el.onclick = (ev) => { ev.stopPropagation(); escolherCor(v, el); });
  $('#cores-originais').onclick = () => { esquecerCores(visorSlug); aplicarCores(v, visorSlug); folhaCamadas(v); };
  folha.querySelectorAll('.camada').forEach(el => el.onclick = () => {
    const k = el.dataset.k, ch = el.querySelector('.chave');
    ch.classList.toggle('ligada');
    const sim = ch.classList.contains('ligada');
    if (el.dataset.tipo === 'piso') { v.mostrarParteReferencia(k, sim); lembrarCamada(visorSlug, 'piso:' + k, sim); }
    else if (el.dataset.tipo === 'sistema') {
      const g = v.sistemas.find(x => x.chave === k);
      if (g) v.ocultarSistema(g.ids, !sim);
      lembrarCamada(visorSlug, 'sistema:' + k, sim);
    } else { v.mostrarCamada(+k, sim); lembrarCamada(visorSlug, cams[+k].nome, sim); }
  });
}

function folhaBuscar(v) {
  abrirFolha(`<div class="nome">Buscar peça</div><div class="busca" style="position:static;margin:8px 0;padding:0;background:none">
    <input type="search" placeholder="marca, perfil ou nome" aria-label="Buscar peça"></div><div id="achadas"></div>`);
  const ent = folha.querySelector('input');
  ent.focus();
  ent.oninput = () => {
    const t = ent.value.trim().toLowerCase();
    const out = [];
    if (t.length >= 2) {
      for (let i = 0; i < v.fichas.length && out.length < 40; i++) {
        const f = v.fichas[i];
        if ((f.n + ' ' + f.p + ' ' + (f.pos || '') + ' ' + (f.mc || '')).toLowerCase().includes(t)) out.push(i);
      }
    }
    $('#achadas').innerHTML = out.map(i => `<div class="camada" data-i="${i}"><span>${esc(v.fichas[i].n)}<br><span class="mais-fraco">${esc(v.fichas[i].p)}</span></span></div>`).join('')
      || (t.length >= 2 ? '<div class="mais-fraco">Nenhuma peça.</div>' : '');
    $('#achadas').querySelectorAll('[data-i]').forEach(el => el.onclick = () => {
      const i = +el.dataset.i;
      v.selecionar(i); v.centrarEm(i); mostrarFicha(v, i);
    });
  };
}

// ------------------------------------------------------------------ Quantitativos

async function telaQuantitativos(slug, m) {
  if (!m.arquivos.some(a => a.nome === 'quantitativos.json')) {
    tela.innerHTML = '<div class="vazio"><b>Sem quantitativos</b>O detalhamento deste projeto ainda não foi feito no computador.</div>';
    return;
  }
  const qt = await json(`${slug}/quantitativos.json`, versaoDe(m, 'quantitativos.json'));
  const t = qt.totais || {};
  const grupos = [
    ['posicoes', 'Posições', qt.posicoes], ['perfis', 'Perfis', qt.perfis], ['chapas', 'Chapas', qt.chapas],
    ['conjuntos', 'Conjuntos', qt.conjuntos], ['telhas', 'Telhas', qt.telhas], ['acessorios', 'Parafusos e acessórios', qt.acessorios],
  ].filter(g => g[2] && g[2].length);
  let atual = grupos[0][0], filtro = '', limite = 120;
  tela.innerHTML = `<div class="grade-num">
      <div class="cartao"><b>${kg(t.peso || 0)}</b><span>peso total</span></div>
      <div class="cartao"><b>${nf(t.pecas)}</b><span>peças</span></div>
      <div class="cartao"><b>${nf(t.posicoes)}</b><span>posições</span></div>
      <div class="cartao"><b>${nf(t.conjuntos)}</b><span>conjuntos</span></div></div>
    <div class="segmentos">${grupos.map(g => `<button data-g="${g[0]}">${g[1]} <span class="mais-fraco">${g[2].length}</span></button>`).join('')}</div>
    <div class="busca"><input type="search" placeholder="Buscar por marca, nome ou perfil" aria-label="Buscar"></div>
    <div class="lista-cartoes" id="itens"></div><div id="mais"></div>
    <p class="mais-fraco" style="text-align:center">Lista de materiais de ${esc(qt.gerado || '—')}</p>`;
  const desenhar = () => {
    tela.querySelectorAll('.segmentos button').forEach(b => b.classList.toggle('ativa', b.dataset.g === atual));
    const lista = grupos.find(g => g[0] === atual)[2];
    const f = filtro.toLowerCase();
    const filtrada = lista.filter(x => !f || JSON.stringify(x).toLowerCase().includes(f));
    $('#itens').innerHTML = filtrada.slice(0, limite).map(x => cartaoQuant(atual, x)).join('') ||
      '<div class="vazio"><b>Nada encontrado</b></div>';
    $('#mais').innerHTML = filtrada.length > limite ? `<button class="botao" style="width:100%;margin-bottom:12px">Mostrar mais (${filtrada.length - limite})</button>` : '';
    const bm = $('#mais button');
    if (bm) bm.onclick = () => { limite += 200; desenhar(); };
  };
  tela.querySelectorAll('.segmentos button').forEach(b => b.onclick = () => { atual = b.dataset.g; limite = 120; desenhar(); });
  $('.busca input').oninput = e => { filtro = e.target.value; limite = 120; desenhar(); };
  desenhar();
}

function cartaoQuant(tipo, x) {
  if (tipo === 'posicoes') {
    const nome = x.nome && x.nome !== x.marca ? x.nome : '';
    const dim = [x.comprimento && nf(x.comprimento) + ' mm', x.largura && x.classe === 'Chapa' ? '× ' + nf(x.largura) : '', x.espessura && x.classe === 'Chapa' ? '# ' + nf(x.espessura, 1) : ''].filter(Boolean).join(' ');
    return `<div class="cartao"><div class="linha"><div><span class="marca">${esc(nome || x.marca)}</span> ${nome ? `<span class="mais-fraco">${esc(x.marca)}</span>` : ''}</div>
      <div class="num"><b>${nf(x.quantidade)}×</b></div></div>
      <div class="fraco">${esc(x.perfil)}${dim ? ' · ' + dim : ''}</div>
      <div class="linha mais-fraco" style="margin-top:4px"><span>${esc(x.material || '')}</span><span class="num">${kg(x.peso || 0)} un · <b>${kg(x.peso_total || 0)}</b></span></div>
      ${x.furos || x.parafusos ? `<div class="etiquetas">${x.furos ? `<span class="etiqueta">${esc(x.furos)}</span>` : ''}${x.parafusos ? `<span class="etiqueta">${esc(x.parafusos)}</span>` : ''}</div>` : ''}
      ${x.conjuntos && x.conjuntos.length ? `<div class="mais-fraco" style="margin-top:6px">em ${esc(x.conjuntos.slice(0, 8).join(', '))}${x.conjuntos.length > 8 ? '…' : ''}</div>` : ''}</div>`;
  }
  if (tipo === 'perfis') {
    const b = x.barras || {};
    const plano = (b.plano || []).slice(0, 30);
    return `<details class="cartao"><summary><div class="linha"><div class="nome" style="font-size:15px">${esc(x.perfil)}</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.comprimento_m, 1)} m${b.quantidade ? ` · ${nf(b.quantidade)} barras de ${nf((b.comprimento || 0) / 1000)} m` : ''}${b.sob_medida_pecas ? ` · ${nf(b.sob_medida_pecas)} sob medida` : ''}</div>
      ${b.aproveitamento != null ? `<div class="barra"><i style="width:${Math.min(100, b.aproveitamento)}%"></i></div><div class="mais-fraco">aproveitamento ${nf(b.aproveitamento, 1)}%${plano.length ? ' · toque para o plano de corte' : ''}</div>` : ''}</summary>
      ${plano.length ? `<div class="plano">${plano.map(pl => `<div><b>${nf(pl.barras)}×</b> ${pl.sob_medida ? 'sob medida · ' : ''}${esc((pl.cortes || []).map(c => `${c.qtd || c.quantidade || 1}× ${c.nome || ''} ${nf(c.comprimento)}`).join(' + '))} <span class="mais-fraco">sobra ${nf(pl.sobra)}</span></div>`).join('')}</div>` : ''}</details>`;
  }
  if (tipo === 'chapas') {
    return `<div class="cartao"><div class="linha"><div class="nome" style="font-size:15px">Chapa # ${nf(x.espessura, 2)} mm</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.area_m2, 2)} m² · ${esc(x.material || '')}</div></div>`;
  }
  if (tipo === 'conjuntos') {
    return `<details class="cartao"><summary><div class="linha"><div><span class="marca">${esc(x.nome || x.marca)}</span> <span class="mais-fraco">${esc(x.marca)}</span></div><div class="num"><b>${nf(x.instancias)}×</b></div></div>
      <div class="fraco">${esc(x.categoria || '')} · ${nf(x.pecas_unidade)} peças por unidade</div></summary>
      <div class="plano">${esc(x.composicao_texto || '')}</div></details>`;
  }
  if (tipo === 'telhas') {
    return `<div class="cartao"><div class="linha"><div class="nome" style="font-size:15px">${esc(x.perfil)}</div><div class="num"><b>${kg(x.peso || 0)}</b></div></div>
      <div class="fraco">${nf(x.pecas)} peças · ${nf(x.comprimento_m, 1)} m · ${nf(x.area_m2, 1)} m²</div></div>`;
  }
  return `<div class="cartao"><div class="linha"><div>${esc(x.nome)}</div><div class="num"><b>${nf(x.quantidade)}</b></div></div></div>`;
}

// ------------------------------------------------------------------ Resumos

async function telaResumos(slug, m) {
  const temNum = m.arquivos.some(a => a.nome === 'resumo-numeros.json');
  const rn = temNum ? await json(`${slug}/resumo-numeros.json`, versaoDe(m, 'resumo-numeros.json')) : null;
  const temQt = m.arquivos.some(a => a.nome === 'quantitativos.json');
  const qt = temQt ? await json(`${slug}/quantitativos.json`, versaoDe(m, 'quantitativos.json')) : null;
  const n = (rn && rn.numeros) || {}, d = (rn && rn.dimensoes) || {};
  const cats = (qt && qt.totais && qt.totais.categorias) || [];
  let html = '';
  if (rn) {
    html += `<div class="grade-num">
      <div class="cartao"><b>${kg(n.total || 0)}</b><span>total da obra</span></div>
      <div class="cartao"><b>${kg(n.peso_aco || 0)}</b><span>aço</span></div>
      <div class="cartao"><b>${nf(n.kg_m2, 1)}</b><span>kg/m²</span></div>
      <div class="cartao"><b>${nf(d.area_m2, 0)} m²</b><span>área</span></div>
      <div class="cartao"><b>${nf(n.tesouras)}</b><span>tesouras</span></div>
      <div class="cartao"><b>${nf(n.m2_telhas, 0)} m²</b><span>telhas</span></div>
      <div class="cartao"><b>${nf(n.parafusos)}</b><span>parafusos</span></div>
      <div class="cartao"><b>${nf(n.inclinacao, 1)}°</b><span>inclinação</span></div></div>`;
    if (d.eixos || d.comprimento_total) html += `<div class="cartao"><div class="nome" style="font-size:15px">Dimensões</div>
      <div class="fraco">Eixos ${esc(d.eixos || '—')} · comprimento ${nf((d.comprimento_total || 0) / 1000, 2)} m · apoio a ${nf((d.nivel_apoio || 0) / 1000, 2)} m</div></div>`;
  } else if (qt) {
    html += `<div class="grade-num"><div class="cartao"><b>${kg(qt.totais.peso || 0)}</b><span>peso total</span></div>
      <div class="cartao"><b>${nf(qt.totais.pecas)}</b><span>peças</span></div></div>`;
  }
  if (cats.length) {
    html += `<div class="titulo-secao">Peso por grupo</div><div class="cartao">${cats.map(c => `<div style="margin:6px 0 10px">
      <div class="linha"><span>${esc(c.titulo || c.categoria)}</span><span class="num fraco">${kg(c.peso)} · ${nf(c.pct, 1)}%</span></div>
      <div class="barra"><i style="width:${Math.min(100, c.pct)}%"></i></div></div>`).join('')}</div>`;
  }
  html += '<div class="titulo-secao">Documentos</div>';
  html += (m.resumos || []).map(r => `<a class="cartao toque documento" href="#/leitor/${encodeURIComponent(slug)}/${encodeURIComponent(r.arquivo)}/1">
      <div class="icone-doc">PDF</div><div><div class="nome" style="font-size:15px">${esc(r.titulo)}</div><div class="mais-fraco">${esc(r.arquivo)}</div></div></a>`).join('')
    || '<div class="cartao fraco">Os resumos em PDF ainda não foram emitidos no computador.</div>';
  tela.innerHTML = html || '<div class="vazio"><b>Sem resumos</b>O detalhamento deste projeto ainda não foi feito.</div>';
}

// ------------------------------------------------------------------ Pranchas

async function telaPranchas(slug, m) {
  const fl = m.pranchas || [];
  if (!fl.length) {
    tela.innerHTML = '<div class="vazio"><b>Sem pranchas</b>As pranchas deste projeto ainda não foram montadas no CAD do computador.</div>';
    return;
  }
  const leitor = pg => `#/leitor/${encodeURIComponent(slug)}/pranchas.pdf/${pg}`;
  tela.innerHTML = `<div class="linha" style="margin-bottom:12px"><span class="fraco">${fl.length} folhas · desenho de ${dataHora(m.fontes && m.fontes.pranchas)}</span>
      <a class="botao" href="${arquivo(m, 'pranchas.pdf')}" target="_blank" style="text-decoration:none">PDF inteiro</a></div>
    <div class="folhas">${fl.map(f => `<a href="${leitor(f.pagina)}">
      <img loading="lazy" src="${arquivo(m, f.miniatura)}" alt="Prancha ${f.numero}">
      <div><b>${String(f.numero).padStart(2, '0')}</b>${esc(f.titulo)} <span class="mais-fraco">${esc(f.formato)}</span></div></a>`).join('')}</div>`;
}

// ------------------------------------------------------------------ cópia para a obra
// Cada projeto aberto na rede fica guardado no aparelho (o pacote inteiro: 3D, quantitativos, resumos e
// pranchas). Na volta à rede, a lista confere o manifesto de cada guardado e baixa só os arquivos que
// mudaram (pela versão SHA-1 no endereço); as versões velhas saem da cópia. Quem guarda as respostas é
// o trabalhador de fundo (sw.js); aqui só se pede o que falta.

function lerGuardados() { try { return JSON.parse(localStorage.getItem('guardados') || '{}'); } catch (e) { return {}; } }
function gravarGuardados(g) { try { localStorage.setItem('guardados', JSON.stringify(g)); } catch (e) { /* sem armazenamento */ } }

/** Na primeira visita, a lista e o estado foram pedidos antes de o trabalhador de fundo assumir a
 *  página (e não ficaram guardados): assumida, pede de novo para a cópia ter os dois. */
let aquecida = null;
function aquecerCopia() {
  if (!COPIA_OK) return Promise.resolve();
  if (!aquecida) aquecida = (async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise(r => { navigator.serviceWorker.addEventListener('controllerchange', r, { once: true }); setTimeout(r, 5000); });
    }
    if (!navigator.serviceWorker.controller) { aquecida = null; return; }
    await Promise.all(['dados/projetos.json', 'api/estado'].map(u => fetch(u, { credentials: 'same-origin' }).then(r => r.arrayBuffer()).catch(() => {})));
  })();
  return aquecida;
}

const emSincronia = new Set();
async function guardarProjeto(slug, m) {
  if (!COPIA_OK || emSincronia.has(slug)) return;
  await aquecerCopia();
  const g = lerGuardados();
  if (g[slug] && g[slug].gerado === m.gerado && g[slug].completo) return;
  emSincronia.add(slug);
  try {
    await navigator.serviceWorker.ready;
    const cache = await caches.open('metalica-dados-1');
    const urls = (m.arquivos || []).map(a => new URL(arquivo(m, a.nome), location.href).href);
    let feitos = 0;
    for (const u of urls) {
      if (!(await cache.match(u))) {
        const r = await fetch(u, { credentials: 'same-origin' });       // o trabalhador de fundo guarda
        if (!r.ok) throw new Error('erro ' + r.status);
        await r.arrayBuffer();
      }
      feitos++;
      const el = document.querySelector(`.etiquetas[data-slug="${CSS.escape(slug)}"]`);
      if (el) el.innerHTML = `<span class="etiqueta">guardando ${feitos} de ${urls.length}</span>`;
    }
    // as versões velhas do projeto saem da cópia
    const prefixo = new URL(`${DADOS}${encodeURIComponent(slug)}/`, location.href).href;
    const atuais = new Set(urls);
    for (const pedido of await cache.keys()) {
      if (pedido.url.startsWith(prefixo) && pedido.url.includes('?v=') && !atuais.has(pedido.url)) await cache.delete(pedido);
    }
    const g2 = lerGuardados();
    g2[slug] = { gerado: m.gerado, completo: true, nome: m.projeto.nome, bytes: m.bytes };
    gravarGuardados(g2);
    const el = document.querySelector(`.etiquetas[data-slug="${CSS.escape(slug)}"]`);
    if (el) el.innerHTML = '<span class="etiqueta ok">guardado para a obra</span>';
  } catch (e) {
    /* sem rede no meio: fica para a próxima */
  } finally {
    emSincronia.delete(slug);
  }
}

async function sincronizar(slugs) {
  await aquecerCopia();
  for (const s of slugs) {
    try { const m = await json(`${s}/manifesto.json`); if (!m.atualizando && !OFFLINE) await guardarProjeto(s, m); }
    catch (e) { /* preparando no computador ou fora da rede: fica para a próxima */ }
  }
}

// ------------------------------------------------------------------ leitor de PDF (pranchas e resumos)
// O Chrome do Android não mostra PDF dentro da página (o iPhone mostra): o leitor é o pdf.js, que
// vai junto com as telas (lib/), funciona sem internet e é igual nos dois. A folha é desenhada na
// escala do zoom; durante o gesto de dois dedos ela só estica (CSS) e, ao soltar, é redesenhada
// nítida. O tamanho da imagem tem teto (o Safari recusa canvas acima de ~16 milhões de pixels).

const MAX_PIXELS = 14e6;
let leitorAtual = null;

function fecharLeitor() {
  if (!leitorAtual) return;
  leitorAtual.fechar();
  leitorAtual = null;
}

async function telaLeitor(slug, nome, pagina) {
  liberar3D();
  const m = await json(`${slug}/manifesto.json`);
  conexao(m.gerado);
  const titulo = nome === 'pranchas.pdf' ? 'Pranchas' : ((m.resumos || []).find(r => r.arquivo === nome) || {}).titulo || nome;
  topo(titulo, m.projeto.nome, () => { history.length > 1 ? history.back() : (location.hash = `#/p/${encodeURIComponent(slug)}/pranchas`); });
  abas(null);
  document.body.classList.add('tela-cheia');
  tela.innerHTML = `<div class="leitor"><div class="folha-pdf" id="rolagem"><div id="pagina-pdf"><canvas></canvas></div></div>
    <div class="leitor-barra">
      <button class="botao" id="pg-ant" aria-label="Folha anterior">‹</button>
      <span id="pg-num" class="num">—</span>
      <button class="botao" id="pg-prox" aria-label="Próxima folha">›</button>
      <span style="flex:1"></span>
      <button class="botao" id="zoom-menos" aria-label="Diminuir">−</button>
      <button class="botao" id="zoom-mais" aria-label="Aumentar">+</button>
    </div><div class="carregando-pdf" id="carregando-pdf">Abrindo…</div></div>`;
  const pdfjs = await import('./lib/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = new URL('./lib/pdf.worker.min.mjs', location.href).href;
  const doc = await pdfjs.getDocument({ url: new URL(arquivo(m, nome), location.href).href, withCredentials: true }).promise;
  const rolagem = $('#rolagem'), caixa = $('#pagina-pdf'), canvas = caixa.querySelector('canvas');
  const estado = { pg: Math.min(Math.max(pagina || 1, 1), doc.numPages), zoom: 1, base: 1, desenhando: null, vivo: true };
  leitorAtual = { fechar: () => { estado.vivo = false; doc.destroy(); } };

  async function desenhar(centro) {
    const pg = await doc.getPage(estado.pg);
    if (!estado.vivo) return;
    const v1 = pg.getViewport({ scale: 1 });
    estado.base = rolagem.clientWidth / v1.width;                     // zoom 1 = folha na largura da tela
    const escalaCss = estado.base * estado.zoom;
    const dpr = window.devicePixelRatio || 1;
    let escala = escalaCss * dpr;
    const px = v1.width * v1.height * escala * escala;
    if (px > MAX_PIXELS) escala *= Math.sqrt(MAX_PIXELS / px);
    const vp = pg.getViewport({ scale: escala });
    const antes = centro || { x: 0.5, y: 0.5 };
    if (estado.desenhando) { try { estado.desenhando.cancel(); } catch (e) { /* já acabou */ } }
    const novo = document.createElement('canvas');
    novo.width = Math.floor(vp.width); novo.height = Math.floor(vp.height);
    novo.style.width = Math.floor(v1.width * escalaCss) + 'px';
    novo.style.height = Math.floor(v1.height * escalaCss) + 'px';
    const tarefa = pg.render({ canvasContext: novo.getContext('2d'), viewport: vp, background: '#ffffff' });
    estado.desenhando = tarefa;
    try { await tarefa.promise; } catch (e) { return; }
    if (!estado.vivo) return;
    caixa.style.transform = '';
    caixa.replaceChildren(novo);
    rolagem.scrollLeft = antes.x * novo.clientWidth - rolagem.clientWidth / 2;
    rolagem.scrollTop = antes.y * novo.clientHeight - rolagem.clientHeight / 2;
    $('#pg-num').textContent = `${estado.pg} de ${doc.numPages}` + (estado.zoom > 1.01 ? ` · ${Math.round(estado.zoom * 100)}%` : '');
    $('#carregando-pdf').hidden = true;
    diag('ultimo_pdf', { nome, folhas: doc.numPages, px: novo.width + '×' + novo.height });
  }
  function centroAtual() {
    const c = caixa.firstElementChild;
    if (!c || !c.clientWidth) return { x: 0.5, y: 0.5 };
    return { x: (rolagem.scrollLeft + rolagem.clientWidth / 2) / c.clientWidth, y: (rolagem.scrollTop + rolagem.clientHeight / 2) / c.clientHeight };
  }
  function zoomPara(z, centro) {
    estado.zoom = Math.min(Math.max(z, 1), 12);
    desenhar(centro || centroAtual());
  }
  $('#zoom-mais').onclick = () => zoomPara(estado.zoom * 1.6);
  $('#zoom-menos').onclick = () => zoomPara(estado.zoom / 1.6);
  $('#pg-ant').onclick = () => { if (estado.pg > 1) { estado.pg--; estado.zoom = 1; desenhar(); } };
  $('#pg-prox').onclick = () => { if (estado.pg < doc.numPages) { estado.pg++; estado.zoom = 1; desenhar(); } };

  // dois dedos: estica na hora (CSS) e redesenha nítido ao soltar; dois toques: aproxima ou volta
  let gesto = null, ultimoToque = 0;
  rolagem.addEventListener('touchstart', e => {
    if (e.touches.length === 2) {
      const [a, b] = e.touches;
      const r = rolagem.getBoundingClientRect();
      const mx = (a.clientX + b.clientX) / 2 - r.left, my = (a.clientY + b.clientY) / 2 - r.top;
      const c = caixa.firstElementChild;
      gesto = { d0: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY), k: 1,
                cx: (rolagem.scrollLeft + mx) / c.clientWidth, cy: (rolagem.scrollTop + my) / c.clientHeight, mx, my };
      caixa.style.transformOrigin = `${rolagem.scrollLeft + mx}px ${rolagem.scrollTop + my}px`;
      e.preventDefault();
    } else if (e.touches.length === 1) {
      const agora = performance.now();
      if (agora - ultimoToque < 300) {
        const r = rolagem.getBoundingClientRect(), c = caixa.firstElementChild;
        const t = e.touches[0];
        const centro = { x: (rolagem.scrollLeft + t.clientX - r.left) / c.clientWidth, y: (rolagem.scrollTop + t.clientY - r.top) / c.clientHeight };
        zoomPara(estado.zoom > 1.5 ? 1 : 3, centro);
        e.preventDefault();
      }
      ultimoToque = agora;
    }
  }, { passive: false });
  rolagem.addEventListener('touchmove', e => {
    if (!gesto || e.touches.length !== 2) return;
    const [a, b] = e.touches;
    gesto.k = Math.min(Math.max(Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) / gesto.d0, 1 / estado.zoom), 12 / estado.zoom);
    caixa.style.transform = `scale(${gesto.k})`;
    e.preventDefault();
  }, { passive: false });
  rolagem.addEventListener('touchend', e => {
    if (!gesto || e.touches.length) return;
    const g = gesto;
    gesto = null;
    if (Math.abs(g.k - 1) > 0.03) zoomPara(estado.zoom * g.k, { x: g.cx, y: g.cy });
    else caixa.style.transform = '';
  });
  await desenhar();
}

// ------------------------------------------------------------------ diagnóstico
// Os números lidos no próprio aparelho, para o teste em celular de verdade (sem cabo nem computador).

async function telaDiagnostico() {
  liberar3D();
  topo('Diagnóstico', 'deste aparelho', () => { location.hash = '#/'; });
  abas(null);
  const d = lerDiag();
  let gl = '—', texMax = '—';
  try {
    const c = document.createElement('canvas').getContext('webgl2');
    const ext = c && c.getExtension('WEBGL_debug_renderer_info');
    gl = c ? (ext ? c.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'WebGL 2') : 'sem WebGL 2';
    if (c) texMax = c.getParameter(c.MAX_TEXTURE_SIZE);
  } catch (e) { gl = 'erro: ' + e.message; }
  let armaz = '—';
  try { const e = await navigator.storage.estimate(); armaz = `${nf((e.usage || 0) / 1048576, 1)} MB usados de ${nf((e.quota || 0) / 1048576, 0)} MB`; } catch (e) { /* sem a API */ }
  const u = d.ultimo3d, fl = d.fluidez;
  const linhas = [
    ['Aparelho', navigator.userAgent],
    ['Tela', `${screen.width} × ${screen.height} · ${window.innerWidth} × ${window.innerHeight} na página · ${window.devicePixelRatio}×`],
    ['Placa de vídeo', gl], ['Textura máxima', texMax],
    ['Memória do aparelho', navigator.deviceMemory ? navigator.deviceMemory + ' GB (aprox.)' : 'o navegador não informa'],
    ['Armazenamento', armaz],
    ['Cópia para a obra', COPIA_OK ? `${Object.keys(lerGuardados()).length} projeto(s) guardado(s)` + (OFFLINE ? ' · sem rede agora' : '') : 'indisponível: precisa de conexão segura (HTTPS)'],
    ['Instalado na tela inicial', (window.matchMedia('(display-mode: standalone)').matches || navigator.standalone) ? 'sim' : 'não'],
    ['Computador', estadoPC ? `${estadoPC.computador} · programa ${estadoPC.programa}` : (OFFLINE ? 'sem rede' : '—')],
    ['Último 3D', u ? `${u.nome}: ${nf(u.pecas)} peças, ${nf(u.mb, 1)} MB · aberto em ${nf(u.ms / 1000, 1)} s (baixar ${nf(u.baixar / 1000, 1)} s, montar ${nf(u.montar / 1000, 1)} s) · ${nf(u.triangulos)} triângulos` : 'nenhum aberto nesta sessão'],
    ['Fluidez', fl ? `${fl.qps} quadros/s · pior quadro ${fl.pior_ms} ms` : 'não medida'],
    ['Último PDF', d.ultimo_pdf ? `${d.ultimo_pdf.nome}: ${d.ultimo_pdf.folhas} folhas · imagem ${d.ultimo_pdf.px}` : '—'],
  ];
  tela.innerHTML = `<div class="cartao ficha"><dl>${linhas.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>
    ${u ? `<button class="botao forte" id="medir" style="width:100%;margin-bottom:10px">Medir a fluidez com o ${esc(u.nome)}</button>` : ''}
    <p class="mais-fraco">Para o teste: abra o Bella Casa (ou o maior projeto), meça a fluidez e mande um print desta tela.</p>`;
  const b = $('#medir');
  if (b) b.onclick = () => { location.hash = `#/p/${encodeURIComponent(u.slug)}/modelo/medir`; };
}

aplicarTema();
rota();
