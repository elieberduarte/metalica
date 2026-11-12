// A cena: a estrutura encaixada numa foto do local, para apresentação (usuário, 26/10: "quando tenho uma foto precisava
// criar uma opção de conseguir colocar a estrutura na foto… 'criar cena', para poder encaixar certinho o 3D na imagem;
// isso seria só para apresentação"). Guardada no projeto (saida/cenas.py); o projeto em si não muda.
//
// O caminho: a foto (Nova cena) → os pares de pontos (um clique na foto e o mesmo ponto no 3D: uma peça, ou o chão da
// imagem do terreno — os cantos da quadra, um meio-fio) → Encaixar (encaixe.js acha a câmera da foto) → o ajuste fino
// (lente, rolar, opacidade do 3D) → Salvar cena (os pontos saem da tela; Editar cena os traz) → Salvar imagem (a foto com o
// 3D, na pasta cenas/ da obra).
//
// Duas vistas no mesmo palco: a FOTO (a foto parada, o 3D transparente por cima pela câmera da cena; os cliques marcam a
// foto) e o 3D (o modelo com o terreno, girando como no modo ver; o clique marca o ponto do modelo).
//
// A TELA DAS CENAS (11/11, amostra-4 aprovada: "a tela de tratamento, criação, exportação, renderização das cenas"): esta
// página é a de todas as cenas da obra — as do 3D (tipo "3d", as mesmas das abas do modo ver, cenas3d.js) e as pela foto.
// À esquerda os cartões com a miniatura e a situação do render; no palco, a cena do 3D com o QUADRO da imagem na proporção
// dela (fora dele, escurecido: é o que não sai) e a lente da cena; à direita o tratamento — enquadramento, o que aparece,
// estilo (cores, arestas, fundo), luz. A lente gravada (camera.fov) é a do quadro: a tela abre a dela para o quadro caber.

import * as THREE from 'three';
import { Visor3D, SOMBRA_GLSL, LUZES_MAX } from './visor3d.js';
import { Terreno } from './terreno.js';
import { encaixar } from './encaixe.js';
import { SOL_PADRAO, definirSol, controlesDoSol, ligarControlesDoSol } from './sol.js';
import { ligarExportar } from './exportar_cenas.js';
import { ligarVideos } from './assistir_videos.js';
import { Figuras, TIPOS_FIGURA, arvoresDoFundo } from './figuras_cena.js';
import { linhaDoTempo, caminhoContinuo, cameraEntre, anguloEntre, GravadorMp4 } from './video_cenas.js';

const $ = s => document.querySelector(s);
const q = new URLSearchParams(location.search);
const PROJETO = q.get('projeto') || '';
const API_3D = `/api/projetos/${encodeURIComponent(PROJETO)}/3d-leve`;
const API = `/api/projetos/${encodeURIComponent(PROJETO)}/terreno/cenas`;
const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const escuro = () => document.documentElement.getAttribute('data-tema') === 'escuro' ||
  (!document.documentElement.getAttribute('data-tema') && matchMedia('(prefers-color-scheme: dark)').matches);

let visor = null, terreno = null, cena = null, modo = 'foto', marcando = null, camera3d = null, rolar = 0, giroBase = null;
let situacaoAberta = null, sistemas = [], situacaoProjeto = null;
let selecionado = null, arrasto = null, tempoAjuste = 0, quadroAjuste = 0;
let tempoLente = 0, tempoOpac = 0, tempoCamadas = 0;
const foto = $('#foto'), tela = $('#tela'), marcas = $('#marcas'), palco = $('#palco');
const ehFoto = () => !!cena && cena.tipo !== '3d';
const eh3d = () => !!cena && cena.tipo === '3d';
let todasCenas = [];                                        // a lista da esquerda (as do 3D e as da foto)

function aviso(txt) { $('#aviso').textContent = txt || ''; }

/** O acesso rápido ao arquivo (usuário, 11/11: "preciso que os render feito tenha um acesso rápido a pasta para encontrar o
 *  arquivo"): a pasta cenas da obra no Explorador, com o arquivo selecionado. */
const mostrarNaPasta = (nome) => pedir(`${API}/mostrar`, { nome: nome || '' });
function avisoComPasta(txt, nome) {
  aviso(txt + ' ');
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'mostrar-pasta'; b.textContent = '📁 Mostrar na pasta';
  b.title = 'Abre a pasta cenas da obra com o arquivo selecionado';
  b.onclick = () => mostrarNaPasta(nome).catch(e => aviso('A pasta não abriu: ' + e.message));
  $('#aviso').append(b);
}

async function pedir(url, corpo, binario) {
  const r = await fetch(url, binario ? { method: 'POST', body: binario.dados,
    headers: { 'Content-Type': 'application/octet-stream', 'X-Nome-Arquivo': encodeURIComponent(binario.nome) } }
    : corpo !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) }
      : { cache: 'no-store' });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
  return j;
}

// ------------------------------------------------------------------ abrir o modelo

async function abrir() {
  if (!PROJETO) { aviso('Nenhum projeto na URL.'); return; }
  // dentro do quadro do 3D (o botão Cenas do modo ver), volta ao modo ver do quadro; na janela inteira (o menu Cenas › Cenas
  // da obra…), à área de trabalho do projeto com o 3D — antes ia ao modo ver solto, sem a barra de cima, e o Cenas dele
  // voltava aqui: um laço sem saída para a tela inicial (usuário, 28/10)
  $('#voltar').onclick = () => {
    const p = encodeURIComponent(PROJETO);
    saindoDaPagina = true;
    location.href = window.top !== window ? `/visor3d/ver3d.html?projeto=${p}` : `/dividida?projeto=${p}&vista=3d`;
  };
  try {                                                     // o nome da obra no alto
    const j = await (await fetch(`/api/projetos/${encodeURIComponent(PROJETO)}`, { cache: 'no-store' })).json();
    $('#titulo-obra').textContent = (j.projeto || j).nome || PROJETO;
  } catch (e) { $('#titulo-obra').textContent = PROJETO; }
  // a cobertura retrátil na situação da cena (aberta ou retraída): o 3D leve dela. Sem a cena pedida, a última da foto
  // (como antes) ou a primeira do 3D
  const todas = (await pedir(API)).cenas || [], cenas = soDeFoto(todas);
  const escolhida = todas.find(c => c.id === q.get('cena')) || cenas[cenas.length - 1] || todas[0] || null;
  situacaoAberta = (escolhida && escolhida.situacao) || null;
  const url3d = situacaoAberta ? `${API_3D}/${situacaoAberta}` : API_3D;
  let r;
  for (;;) {
    r = await fetch(url3d, { cache: 'no-cache' });
    if (r.status !== 202) break;
    $('#carregando').textContent = 'Preparando o modelo 3D…';
    await new Promise(res => setTimeout(res, 800));
  }
  if (!r.ok) { $('#carregando').textContent = 'Este projeto ainda não tem modelo 3D.'; return; }
  const versao = r.headers.get('X-Versao-3D') || '';
  const buf = await r.arrayBuffer();
  visor = new Visor3D(tela, { mouse: true, arestas: true, maxPixelRatio: 2, transparente: true, fundo: escuro() ? '#1a212c' : '#e4eaf2' });
  window.visor = visor;
  visor.leveAoGirar = false;
  await visor.carregar(buf);
  const rf = await fetch(`${url3d}/pecas?v=${encodeURIComponent(versao)}`);
  if (rf.ok) visor.definirFichas(await rf.json());
  const { gruposDeSistema } = await import('./sistemas.js');
  sistemas = visor.fichas ? gruposDeSistema(visor) : [];
  visor.definirTema(escuro());
  visor.ligarApresentacao(true, 4096);                    // no PC: a sombra mais fina (o celular fica nos 2048)
  visor._recorteSombra = recorteDaCena;
  telaFina.hidden = true;
  tela.after(telaFina);
  const pedirQuadro = visor.pedirQuadro.bind(visor);
  visor.pedirQuadro = () => { aoPedirQuadro(); pedirQuadro(); };
  terreno = new Terreno(visor, PROJETO, { abrirPainel: () => {}, corpo: () => null, situacao: aviso, palco,
                                          painelAtual: () => null, aoMudar: () => {}, chaveLigado: null });
  try { await terreno.carregar(); } catch (e) { /* sem o terreno: os pontos só nas peças */ }
  $('#carregando').remove();
  ligarControles();
  await coberturaRetratil();
  await carregarMarcas();
  await listar(escolhida ? escolhida.id : null);
  window.cenaPronta = true;
  requestAnimationFrame(desenharMarcas);
}

// ------------------------------------------------------------------ as cenas

// as cenas do 3D (tipo "3d", 11/11: cenas3d.js no modo ver) e as da foto na mesma lista do servidor e nesta tela (11/11:
// "a ferramenta de cenas não estão se conversando, as cenas criadas não aparecem aqui"; a tela das Cenas, amostra-4)
const soDeFoto = (lista) => (lista || []).filter(c => c.tipo !== '3d');

/** A situação da imagem da cena no cartão: o render (feito, velho — mais velho que a cena —, ou nenhum). */
function situacaoDoRender(c) {
  const data = (s) => s ? `${s.slice(8, 10)}/${s.slice(5, 7)}` : '';
  if (!c.render_em) return '<span>sem render</span>';
  return c.render_em < (c.alterada || '') ? `<span class="velho" title="A cena mudou depois do render">render velho</span>`
    : `<span class="ok">render ${data(c.render_em)} ✓</span>`;
}

function miniaturaDe(c) {
  if (c.miniatura) return `${API}/${encodeURIComponent(c.id)}/miniatura.jpg?v=${encodeURIComponent(c.miniatura)}`;
  return c.tipo === '3d' ? '' : `${API}/${encodeURIComponent(c.id)}/foto.jpg?v=${encodeURIComponent(c.alterada || '')}`;
}

function desenharCartoes() {
  $('#cartoes').innerHTML = todasCenas.map(c => {
    const mini = miniaturaDe(c);
    return `<button type="button" class="cartao-cena${cena && cena.id === c.id ? ' ativa' : ''}" data-cena="${esc(c.id)}">
      <span class="mini"${mini ? ` style="background-image:url('${esc(mini)}')"` : ''}></span>
      <span><b title="${esc(c.nome)}">${esc(c.nome)}</b><small><span class="tipo">${c.tipo === '3d' ? '3D' : '📷 foto'}</span>
        ${c.tipo === '3d' ? esc(c.proporcao || '16:9') + ' · ' : ''}${situacaoDoRender(c)}</small></span></button>`;
  }).join('') || '<p class="dica">Nenhuma cena ainda: arrume a vista e grave (+ Nova cena pela vista), ou comece por uma foto do local.</p>';
}

async function listar(escolher) {
  todasCenas = (await pedir(API)).cenas || [];
  const cenas = soDeFoto(todasCenas);
  $('#lista').innerHTML = todasCenas.map(c => `<option value="${esc(c.id)}">${esc(c.nome)}</option>`).join('')
    || '<option value="">(nenhuma cena: comece pela foto)</option>';
  const id = escolher && todasCenas.some(c => c.id === escolher) ? escolher : ((cenas[cenas.length - 1] || todasCenas[0] || {}).id);
  if (id) { $('#lista').value = id; await abrirCena(id); }
  else { sairDaCena(); cena = null; $('#corpo').hidden = true; $('#corpo3d').hidden = true; foto.hidden = true; mostrarModo('3d'); desenharCamadas(); mostrarSol(); mostrarMarca(); }
  desenharCartoes();
  mostrarBotoes();
}

/** Recarrega só os cartões (a situação do render, a miniatura, o nome), sem trocar de cena. */
async function atualizarCartoes() {
  try { todasCenas = (await pedir(API)).cenas || []; } catch (e) { return; }
  desenharCartoes();
}

async function abrirCena(id, { recarregar = true } = {}) {
  const nova = await pedir(`${API}/${encodeURIComponent(id)}`);
  if ((nova.situacao || null) !== situacaoAberta) {          // a outra situação da cobertura: o 3D dela
    if (!recarregar) return false;                          // (o lote do Exportar: pula a cena e segue)
    location.href = `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(id)}`;
    return;
  }
  if (eh3d() || nova.tipo === '3d') sairDaCena();
  cena = nova;
  desfeitos.length = refeitos.length = 0;                   // o histórico é de uma cena só
  history.replaceState(null, '', `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(id)}`);
  $('#lista').value = id;
  desenharCartoes();
  mostrarBotoes();
  if (nova.tipo === '3d') { abrirCena3d(); return; }
  $('#corpo3d').hidden = true;
  foto.hidden = false;
  foto.src = `${API}/${encodeURIComponent(id)}/foto.jpg?v=${encodeURIComponent(cena.alterada || '')}`;
  try { await foto.decode(); } catch (e) { aviso('A foto não abriu.'); }
  atualizarTexturaFoto();
  desenho = null; contornoSel = null; document.body.classList.remove('desenhando');
  $('#corpo').hidden = false;
  rolar = 0;
  giroBase = null;
  $('#opacidade').value = cena.opacidade ?? 1;
  aplicarCamera();
  mostrarModo('foto');
  desenharPares();
  desenharCamadas();
  marcarSituacao();
  mostrarTamanhos();
  mostrarSol();
  mostrarConcluida();
  desenharContornos();
  mostrarMarca();
}

// ------------------------------------------------------------------ a cena do 3D na tela das Cenas (11/11)

const PROPORCOES = { '16:9': 16 / 9, '4:3': 4 / 3, '3:4': 3 / 4, 'A3': 420 / 297, 'livre': null };
const FOV_PADRAO = 45;
// os AMBIENTES (11/11, amostra-6 aprovada: "criar umas cenas noturnas… opções de fundos diferentes"): o céu (de cima até o
// horizonte, onde o chão começa na cor `piso`), a luz do 3D (visor.definirAmbiente: o céu e o chão nas faces, a cor e a força
// do sol, as arestas) e, de noite, as luzes automáticas (refletores em volta e a luz interna: [força dos refletores, da
// interna]). "ceu" é o Dia de antes (a luz padrão, as linhas do piso).
const AMBIENTES = {
  ceu: { nome: 'Dia', ceu: ['#8fb8de', '#dfe9f3'], piso: '#dfe9f3', luzChao: 1 },
  entardecer: { nome: 'Entardecer', ceu: ['#3f5687', '#c98a7a', '#f3c48c'], piso: '#e9c6a0', solAltura: 9, luzChao: 1,
                luz: { ambCeu: [0.62, 0.60, 0.74], ambChao: [0.66, 0.50, 0.40], ambK: 0.62, solCor: [1.0, 0.68, 0.40], solK: 0.95, pisoAmb: 0.95, aresta: 0.9 } },
  nublado: { nome: 'Nublado', ceu: ['#aeb8c4', '#e4e7eb'], piso: '#e1e3e6', luzChao: 1,
             luz: { ambCeu: [0.92, 0.93, 0.95], ambChao: [0.80, 0.80, 0.80], ambK: 0.92, solCor: [1, 1, 1], solK: 0.18 } },
  estudio: { nome: 'Estúdio', ceu: ['#f7f8fa', '#e3e6ea'], radial: true, piso: '#e6e8eb', luzChao: 1,
             luz: { ambCeu: [0.86, 0.87, 0.90], ambChao: [0.70, 0.70, 0.72], ambK: 0.82, solCor: [1, 1, 1], solK: 0.45 } },
  'noite-azul': { nome: 'Noite azul', ceu: ['#0d1a36', '#28467a', '#6b7fa6'], piso: '#3c4a66', noite: [1.6, 1.3], luzChao: 1,
                  luz: { ambCeu: [0.26, 0.31, 0.48], ambChao: [0.16, 0.16, 0.22], ambK: 0.75, solCor: [0.55, 0.62, 0.9], solK: 0.12, pisoAmb: 0.75, aresta: 0.45 } },
  noite: { nome: 'Noite', ceu: ['#03050b', '#0b1222', '#1a2338'], estrelas: true, piso: '#121826', noite: [2.2, 1.8], luzChao: 1,
           luz: { ambCeu: [0.09, 0.11, 0.17], ambChao: [0.05, 0.05, 0.07], ambK: 0.8, solCor: [0.55, 0.65, 0.95], solK: 0.08, pisoAmb: 0.6, aresta: 0.25 } },
};
const LUZ_PADRAO = { refletores: true, interna: true, forca_ref: 1, forca_int: 1, cor: 'quente' };
const luzesDaCena = () => ({ ...LUZ_PADRAO, ...((cena && cena.luzes) || {}) });
const ambienteDaCena = () => (eh3d() ? AMBIENTES[cena.fundo || 'ceu'] || null : null);
// o ENTORNO (12/11, amostra-8 aprovada: as 4 + a calçada ajustável + o pátio desenhado): o chão em volta (visor.definirEntorno)
const ENTORNOS = { liso: 0, grama: 1, patio: 2, concreto: 3, terra: 4, terreno: 0 };
const ENTORNO_NOME = { liso: 'chão liso', grama: 'grama', patio: 'pátio', concreto: 'concreto', terra: 'terra', terreno: 'terreno real' };
const entornoDaCena = () => ({ tipo: 'liso', calcada: 4, patio: null, ...((cena && cena.entorno) || {}) });
const paraMundo = (p) => { const o = visor.cabecalho.origem; return [p[0] - o[0], p[1] - o[1], (p[2] || 0) - o[2]]; };
const paraProjeto = (p) => { const o = visor.cabecalho.origem; return [p[0] + o[0], p[1] + o[1], p[2] + o[2]]; };
const NOME_LUZ = { poste: 'Poste', refletor: 'Refletor', luminaria: 'Luminária' };
// as figuras (12/11, amostra-9 aprovada: "os dois, por cena"; árvores do fundo em 3 densidades; postas como as luzes): pessoas,
// veículos e árvores no chão. O estilo "auto" é a maquete branca no Estúdio e nos fundos lisos, colorido nos outros
const FIGURAS_MAX = 60;
const figurasDaCena = () => ({ estilo: 'auto', itens: [], ...((cena && cena.figuras) || {}) });
const estiloDasFiguras = () => {
  const e = figurasDaCena().estilo;
  return e !== 'auto' ? e : ['estudio', 'branco', 'transparente'].includes(cena.fundo || 'ceu') ? 'neutro' : 'cor';
};
let fovCena = FOV_PADRAO, vistaMudou = false, quadroAtual = null, tempoMini = 0, ouvindoVista = false;

/** Os botões que dependem da cena (a imagem e o render). */
function mostrarBotoes() {
  const pode = !!cena && (eh3d() || !!cena.camera);
  $('#salvar-imagem').disabled = $('#renderizar').disabled = !pode || renderizando;
  $('#render-tamanho').disabled = !cena;
  $('#exportar').disabled = !todasCenas.length || renderizando;
  $('#copiar-ajustes').disabled = $('#copiar-3d').disabled = !cena || todasCenas.length < 2;
  $('#copiar-ajustes').hidden = !ehFoto();                // a cena do 3D: no ⋯ ao lado do nome
}

/** Saindo de uma cena do 3D (para a da foto ou nenhuma): o estilo de sempre de volta. */
function sairDaCena() {
  if (!eh3d() || !visor) return;
  visor.definirAmbiente(null);                              // a luz de sempre
  visor.definirEntorno(null, false);                        // o piso de sempre
  desenharObjetosDasLuzes(null);
  desenharFiguras(true);
  pararDeColocar();
  $('#ceu').hidden = true;
  visor.pintarPor('material');
  visor.ligarArestas(true);
  document.body.classList.remove('fundo-transparente');
  visor.definirTema(escuro());
  if (terreno && terreno.grupo) terreno.grupo.visible = true;
  visor.camera.fov = FOV_PADRAO;
  visor.camera.updateProjectionMatrix();
  $('#quadro').hidden = $('#barra-palco').hidden = true;
}

function abrirCena3d() {
  foto.hidden = true;
  $('#corpo').hidden = true;
  $('#corpo3d').hidden = false;
  desenho = null; contornoSel = null; document.body.classList.remove('desenhando', 'concluida');
  tirarParedes();
  chaoSombra && (chaoSombra.visible = false);
  mostrarModo('3d');
  aplicarVistaDaCena();
  aplicarEstilo3d();
  desenharCamadas();
  marcarSituacao();
  mostrarTamanhos();
  mostrarSol();
  mostrarPainel3d();
  mostrarMarca();
  // a cena feita no modo ver ainda sem miniatura, ou mudada por fora dela (Copiar ajustes de outra cena)
  if (!cena.miniatura || (cena.alterada && cena.miniatura < cena.alterada)) agendarMiniatura(300);
}

/** O quadro da imagem no palco (centrado: a tela inteira é o 3D e o quadro é o recorte do meio) e a lente da tela que
 *  mostra no quadro o que a lente da cena mostra na imagem. */
function ajustarQuadro() {
  const q3 = $('#quadro'), barra = $('#barra-palco');
  if (!eh3d() || modo !== '3d' || !visor) { q3.hidden = barra.hidden = true; quadroAtual = null; return; }
  const W = palco.clientWidth, H = palco.clientHeight, lado = 24, alto = 60;    // embaixo, a barra das vistas
  const p = PROPORCOES[cena.proporcao || '16:9'] || (W - 2 * lado) / (H - 2 * alto);
  let qw = W - 2 * lado, qh = qw / p;
  if (qh > H - 2 * alto) { qh = H - 2 * alto; qw = qh * p; }
  qw = Math.max(40, Math.round(qw)); qh = Math.max(30, Math.round(qh));
  quadroAtual = { x: Math.round((W - qw) / 2), y: Math.round((H - qh) / 2), w: qw, h: qh, p: qw / qh };
  Object.assign(q3.style, { left: quadroAtual.x + 'px', top: quadroAtual.y + 'px', width: qw + 'px', height: qh + 'px' });
  $('#quadro-rotulo').textContent = `Quadro da imagem · ${cena.proporcao || '16:9'} · lente ${nf(fovCena, 0)}°`;
  q3.hidden = barra.hidden = false;
  const t = Math.tan(fovCena * Math.PI / 360) * H / qh;
  visor.camera.fov = Math.min(170, Math.atan(t) * 360 / Math.PI);
  visor.camera.updateProjectionMatrix();
  visor.pedirQuadro();
  ceuDaTela();
  desenharPreviaMarca();
}

/** A câmera da cena no visor (a posição e o alvo; a lente pelo quadro). */
function aplicarVistaDaCena() {
  const c = cena.camera || {};
  fovCena = +c.fov || FOV_PADRAO;
  if (c.posicao && c.alvo) visor.definirCamera({ posicao: c.posicao, alvo: c.alvo });
  ajustarQuadro();
  marcarVista(false);
  if (!ouvindoVista) {                                      // girar/andar/aproximar: a vista mudou (Atualizar grava)
    ouvindoVista = true;
    visor.controles.addEventListener('change', () => { if (eh3d() && !renderizando && !refinando) { marcarVista(true); ceuDaTela(); } });
  }
}

function marcarVista(mudou) {
  vistaMudou = mudou;
  $('#atualizar-vista').classList.toggle('pendente', mudou);
  $('#desfazer-vista').disabled = !mudou;
}

/** A câmera de agora como a da cena (mm do projeto, a lente do quadro). */
function cameraDaTela() {
  const c = visor.lerCamera();
  return { posicao: c.posicao, alvo: c.alvo, fov: Math.round(fovCena * 100) / 100, projecao: 'perspectiva' };
}

function pintarComo(modo3d) {
  if (modo3d === 'sistema' && sistemas.length) {
    visor.pintarPor('perfil');                              // zera as cores; depois a de cada sistema
    const c = document.createElement('canvas').getContext('2d');
    for (const s of sistemas) {
      c.fillStyle = '#000'; c.fillStyle = s.cor || '#888';
      const h = String(c.fillStyle), rr = parseInt(h.slice(1, 3), 16), gg = parseInt(h.slice(3, 5), 16), bb = parseInt(h.slice(5, 7), 16);
      for (const i of s.ids) { visor.corBase[i * 3] = rr; visor.corBase[i * 3 + 1] = gg; visor.corBase[i * 3 + 2] = bb; }
    }
    visor._repintar();
  } else visor.pintarPor(['camada', 'perfil'].includes(modo3d) ? modo3d : 'material');
}

/** As luzes de noite, postas sozinhas (amostra-6, "automáticas + ajuste"): refletores em volta das peças à vista, a meia
 *  altura e 2,5 m para fora, um a cada ~11 m (até 8 por lado), e a luz interna numa grade de ~15 m a 42 % da altura. A
 *  força de cada grupo é a do ambiente vezes a da cena (0–3); a cor, quente ou branca. */
/** Onde fica a luz de cada uma posta à mão (mundo): o poste com o braço para o prédio, a 7,7 m; o refletor 1,5 m para fora da
 *  parede; a luminária 0,6 m abaixo do ponto. `dir` = para fora do prédio, no plano. */
function geometriaDaLuz(m) {
  const cx = visor.caixaVisivel(), c = cx.getCenter(new THREE.Vector3()), p = paraMundo(m.p);
  let dx = p[0] - c.x, dy = p[1] - c.y; const d = Math.hypot(dx, dy) || 1; dx /= d; dy /= d;
  if (m.tipo === 'poste') return { p, dir: [dx, dy], luz: [p[0] - dx * 1350, p[1] - dy * 1350, p[2] + 7600] };
  if (m.tipo === 'refletor') return { p, dir: [dx, dy], luz: [p[0] + dx * 1500, p[1] + dy * 1500, p[2]] };
  return { p, dir: [dx, dy], luz: [p[0], p[1], p[2] - 600] };
}

function luzesDoAmbiente(amb) {
  if (!amb || !amb.noite || !visor) return [];
  const lz = luzesDaCena(), cx = visor.caixaVisivel(), a = cx.min, b = cx.max, h = Math.max(1000, b.z - a.z);
  const quente = lz.cor === 'branca' ? [1, 0.95, 0.88] : [1, 0.80, 0.55], dentro = lz.cor === 'branca' ? [1, 0.97, 0.94] : [1, 0.93, 0.82];
  const out = [];
  for (const m of lz.mao || []) {                           // as postas à mão primeiro (12/11, amostra-8)
    const gm = geometriaDaLuz(m), k = { poste: [2.4, 16000], refletor: [2.0, 12000], luminaria: [1.8, 12000] }[m.tipo] || [2, 12000];
    out.push({ p: gm.luz, alcance: k[1], cor: m.tipo === 'luminaria' ? dentro : quente, forca: k[0] * (m.forca ?? 1) });
  }
  if (lz.refletores && lz.forca_ref > 0) {
    const f = amb.noite[0] * lz.forca_ref, z = a.z + 0.5 * h, fora = 2500;
    const lado = (de, ate) => { const n = Math.min(7, Math.max(1, Math.round((ate - de) / 11000))); return Array.from({ length: n + 1 }, (_, i) => de + i * (ate - de) / n); };
    const xs = lado(a.x, b.x), ys = lado(a.y, b.y);
    const alcance = Math.max(11000, (b.x - a.x) / (xs.length - 1 || 1), (b.y - a.y) / (ys.length - 1 || 1));
    for (const x of xs) out.push({ p: [x, a.y - fora, z], alcance, cor: quente, forca: f }, { p: [x, b.y + fora, z], alcance, cor: quente, forca: f });
    for (const y of ys.slice(1, -1)) out.push({ p: [a.x - fora, y, z], alcance, cor: quente, forca: f }, { p: [b.x + fora, y, z], alcance, cor: quente, forca: f });
  }
  if (lz.interna && lz.forca_int > 0) {
    const f = amb.noite[1] * lz.forca_int, z = a.z + 0.42 * h, resto = Math.max(1, LUZES_MAX - out.length);
    let nx = Math.max(1, Math.round((b.x - a.x) / 15000)), ny = Math.max(1, Math.round((b.y - a.y) / 15000));
    while (nx * ny > resto) { if (nx >= ny) nx--; else ny--; }
    const alcance = Math.max(12000, (b.x - a.x) / nx, (b.y - a.y) / ny);
    for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++)
      out.push({ p: [a.x + (i + 0.5) * (b.x - a.x) / nx, a.y + (j + 0.5) * (b.y - a.y) / ny, z], alcance, cor: dentro, forca: f });
  }
  return out.slice(0, LUZES_MAX);
}

/** O céu do ambiente em g (w × h) para a câmera `cam` (a lente e a proporção da imagem): o degradê de cima até o
 *  HORIZONTE — um ponto do chão muito longe na direção do olhar —, onde o chão começa na mesma cor; o estúdio é um degradê
 *  redondo; a noite tem estrelas (sempre as mesmas, o tamanho pela imagem). */
function pintarCeu(g, w, h, amb, cam) {
  let grad;
  if (amb.radial) grad = g.createRadialGradient(w / 2, h * 0.45, 0.03 * w, w / 2, h * 0.45, 0.75 * w);
  else {
    const alvo = visor.controles.target, dx = alvo.x - cam.position.x, dy = alvo.y - cam.position.y, d = Math.hypot(dx, dy);
    let yh = 0;                                             // olhando reto para baixo: o chão cobre tudo
    if (d > 1e-6) {
      const pz = visor.piso ? visor.piso.position.z : 0;
      const p = new THREE.Vector3(cam.position.x + dx / d * 1e9, cam.position.y + dy / d * 1e9, pz).project(cam);
      yh = (1 - (p.y + 1) / 2) * h;
    }
    grad = g.createLinearGradient(0, 0, 0, Math.max(10, yh));
  }
  amb.ceu.forEach((c, i) => grad.addColorStop(i / (amb.ceu.length - 1), c));
  g.fillStyle = grad; g.fillRect(0, 0, w, h);
  if (amb.estrelas) {
    let sd = 7; const r = () => (sd = (sd * 16807) % 2147483647) / 2147483647;
    const k = Math.sqrt(w * h) / 1200, n = Math.min(2000, Math.round(260 * w * h / (1600 * 900)));
    for (let i = 0; i < n; i++) {
      const a = 0.25 + 0.6 * r(), t = (r() < 0.08 ? 1.6 : 0.9) * Math.max(1, k);
      g.fillStyle = `rgba(255,255,255,${a})`; g.fillRect(r() * w, r() * h * 0.5, t, t);
    }
  }
}

/** O céu da tela, atrás do 3D (o canvas do visor é vazado): o mesmo do render, pela câmera da tela. */
function ceuDaTela() {
  const cv = $('#ceu'), amb = modo === '3d' ? ambienteDaCena() : null;
  if (!amb || !visor) { cv.hidden = true; return; }
  const W = palco.clientWidth, H = palco.clientHeight;
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  cv.hidden = false;
  visor.camera.updateMatrixWorld();
  pintarCeu(cv.getContext('2d'), W, H, amb, visor.camera);
}

/** O fundo da cena do 3D: céu (degradê, o piso se perde no horizonte), branco (sem as linhas do piso), transparente (sem
 *  fundo nem piso: PNG) ou o terreno (a imagem do lugar, quando a obra tem). */
/** Os postes, refletores e luminárias postos à mão, no 3D (aparecem na imagem; de noite a cabeça acende). */
let grupoDasLuzes = null;
function desenharObjetosDasLuzes(amb) {
  // no grupo extras do visor (12/11): o poste faz sombra no chão, como as figuras
  if (grupoDasLuzes) { visor.extras.remove(grupoDasLuzes); grupoDasLuzes.traverse(o => { if (o.geometry) o.geometry.dispose(); }); grupoDasLuzes = null; }
  const mao = eh3d() ? luzesDaCena().mao || [] : [];
  if (!mao.length) return;
  const g = grupoDasLuzes = new THREE.Group();
  const escuro_ = new THREE.MeshBasicMaterial({ color: 0x2c3138 }), cabeca = new THREE.MeshBasicMaterial({ color: amb && amb.noite ? 0xfff1c9 : 0xd8dde3 });
  for (const m of mao) {
    const gm = geometriaDaLuz(m), [x, y, z] = gm.p, ang = Math.atan2(-gm.dir[1], -gm.dir[0]);
    if (m.tipo === 'poste') {
      const haste = new THREE.Mesh(new THREE.CylinderGeometry(70, 90, 8000, 10), escuro_); haste.rotation.x = Math.PI / 2; haste.position.set(x, y, z + 4000);
      const braco = new THREE.Mesh(new THREE.BoxGeometry(1400, 80, 80), escuro_); braco.rotation.z = ang;
      braco.position.set(x - gm.dir[0] * 700, y - gm.dir[1] * 700, z + 7950);
      const cab = new THREE.Mesh(new THREE.BoxGeometry(650, 450, 160), cabeca); cab.rotation.z = ang;
      cab.position.set(x - gm.dir[0] * 1350, y - gm.dir[1] * 1350, z + 7860);
      g.add(haste, braco, cab);
    } else if (m.tipo === 'refletor') {
      const r = new THREE.Mesh(new THREE.BoxGeometry(300, 500, 300), cabeca); r.rotation.z = ang; r.position.set(x + gm.dir[0] * 200, y + gm.dir[1] * 200, z); g.add(r);
    } else {
      const l = new THREE.Mesh(new THREE.CylinderGeometry(250, 250, 80, 16), cabeca); l.rotation.x = Math.PI / 2; l.position.set(x, y, z - 100); g.add(l);
    }
  }
  visor.extras.add(g);
  visor._sombraSuja = true;
}

/** As figuras da cena (pessoas, veículos, árvores postas) e as árvores do fundo (Entorno, num ambiente com chão), no estilo
 *  da cena. Só refaz quando algo mudou (o painel chama a cada passo do controle). As árvores do fundo saem pela câmera
 *  GRAVADA da cena (girar a tela não as muda; Atualizar a vista as refaz). */
let figuras = null, chaveFiguras = '';
function desenharFiguras(tirar = false) {
  if (!visor || !visor.extras) return;
  figuras = figuras || new Figuras(visor);
  const amb = !tirar && eh3d() ? ambienteDaCena() : null, en = eh3d() ? entornoDaCena() : {};
  const itens = !tirar && eh3d() ? figurasDaCena().itens : [];
  const arv = amb && en.tipo !== 'terreno' ? +en.arvores || 0 : 0, cam = (cena && cena.camera) || {};
  const chave = JSON.stringify([itens, arv && [en.patio, cam.posicao], arv, !tirar && eh3d() && estiloDasFiguras()]);
  if (chave === chaveFiguras) return;
  chaveFiguras = chave;
  const lista = itens.map(f => ({ ...f, p: paraMundo(f.p) }));
  if (arv) {
    const cx = visor.caixaVisivel(), olho = cam.posicao ? paraMundo(cam.posicao) : null;
    lista.push(...arvoresDoFundo([[cx.min.x, cx.min.y], [cx.max.x, cx.max.y]],
                                 en.patio ? en.patio.map(q => paraMundo([q[0], q[1], 0]).slice(0, 2)) : null, olho, arv, zDoChao()));
  }
  figuras.desenhar(lista, lista.length ? estiloDasFiguras() : 'cor');
}

/** O chão do entorno (o piso desenhado: grama, pátio, concreto, terra), pelo ambiente; sem ambiente, o piso de sempre. */
function aplicarEntorno(amb) {
  const en = entornoDaCena(), chao = amb ? ENTORNOS[en.tipo] || 0 : 0;
  if (!chao) { visor.definirEntorno(null, false); return; }
  const cx = visor.caixaVisivel();
  visor.definirEntorno({ chao, caixa: [[cx.min.x, cx.min.y], [cx.max.x, cx.max.y]], calcada: en.tipo === 'concreto' ? 0 : (+en.calcada || 0) * 1000,
                         patio: en.patio ? en.patio.map(q => paraMundo([q[0], q[1], 0]).slice(0, 2)) : null, luz: amb.luzChao ?? 1 }, false);
}

function aplicarFundo() {
  const f = cena.fundo || 'ceu', u = visor.piso && visor.piso.material.uniforms, amb = AMBIENTES[f];
  visor.definirTema(escuro());                              // o piso e o fundo do tema; depois o da cena
  document.body.classList.toggle('fundo-transparente', f === 'transparente');
  if (terreno && terreno.grupo) terreno.grupo.visible = f === 'terreno' || (!!amb && entornoDaCena().tipo === 'terreno');
  if (visor.piso) visor.piso.visible = f !== 'transparente';
  visor.definirAmbiente(amb && amb.luz ? { ...amb.luz, luzes: luzesDoAmbiente(amb) } : null, false);
  aplicarEntorno(amb);
  desenharObjetosDasLuzes(amb);
  desenharFiguras();
  if (amb) {                                                // o céu atrás (#ceu), o chão na cor do horizonte
    visor.cena.background = null;
    // sem as linhas de 10 m do piso em nenhum ambiente (usuário, 12/11: "essas linhas do piso para as cenas não precisa existir")
    if (u) { u.uFundo.value.setStyle(amb.piso, THREE.LinearSRGBColorSpace); u.uAlfa.value = 0; }
  } else if (f === 'branco') {
    visor.cena.background = new THREE.Color().setStyle('#ffffff', THREE.LinearSRGBColorSpace);
    if (u) { u.uFundo.value.setStyle('#ffffff', THREE.LinearSRGBColorSpace); u.uAlfa.value = 0; }
  } else if (f === 'transparente') visor.cena.background = null;
  ceuDaTela();
  visor.pedirQuadro();
}

function aplicarEstilo3d() {
  pintarComo(cena.pintar || 'material');
  visor.ligarArestas(cena.arestas !== false);
  aplicarFundo();
  aplicarCamadas();
}

/** O resumo de cada seção do painel (12/11, amostra-7): o que está escolhido, na barra dela. */
function resumirPainel() {
  if (!cena) return;
  const pos = (id, t) => { const el = document.getElementById(id); if (el) el.textContent = t; };
  const m = marcaDaCena(), emp = (marcaInfo.empresas || []).find(e => e.id === m.empresa);
  pos('res-marca', m.empresa === 'sem' || !temLogo(m.empresa) ? 'sem' : `${(emp && emp.nome) || 'Hermes'} · ${{ A: 'logo', B: 'placa', C: 'faixa' }[m.jeito] || m.jeito} · ${m.canto === 'esq' ? 'esquerda' : 'direita'}`);
  if (!eh3d()) return;
  pos('res-quadro', `${cena.proporcao || '16:9'} · lente ${nf(fovCena, 0)}°`);
  const desl = new Set(desligadasAgora()), cams = (visor && visor.cabecalho.camadas) || [];
  const sl = sistemas.filter(s => !desl.has('sistema:' + s.chave)).length, cl = cams.filter(c => !desl.has('camada:' + c.nome)).length;
  pos('res-aparece', (sistemas.length > 1 ? `${sl === sistemas.length ? sl : sl + ' de ' + sistemas.length} sistemas · ` : '') +
      `${cl === cams.length ? cl : cl + ' de ' + cams.length} camadas`);
  const f = cena.fundo || 'ceu', amb = AMBIENTES[f], s = solDaCena(), lz = luzesDaCena();
  const luzes = amb && amb.noite ? (lz.refletores || lz.interna ? ' · luzes acesas' : ' · luzes apagadas') : '';
  const ent = amb && entornoDaCena().tipo !== 'liso' ? ' · ' + ENTORNO_NOME[entornoDaCena().tipo] : '';
  pos('res-ambiente', `${amb ? amb.nome : { branco: 'fundo branco', transparente: 'transparente', terreno: 'terreno' }[f] || f}${ent}${luzes}${amb && amb.noite ? '' : s.ligado ? ` · sol ${nf(s.altura, 0)}°` : ' · sem sol'}`);
  const fi = figurasDaCena().itens, conta = (g) => fi.filter(f => (TIPOS_FIGURA[f.tipo] || {}).grupo === g).length;
  const partes = [['gente', 'pessoa', 'pessoas'], ['veiculo', 'veículo', 'veículos'], ['verde', 'árvore', 'árvores']]
    .map(([g, um, varios]) => { const n = conta(g); return n ? `${n} ${n === 1 ? um : varios}` : ''; }).filter(Boolean);
  if (amb && +entornoDaCena().arvores) partes.push('árvores no fundo');
  pos('res-figuras', partes.join(' · ') || 'nenhuma');
  pos('res-estilo', `cores por ${cena.pintar && cena.pintar !== 'editor' ? cena.pintar : 'material'} · ${cena.arestas === false ? 'sem arestas' : 'arestas finas'}`);
}

function mostrarPainel3d() {
  $('#cena-nome').value = cena.nome || '';
  const marcar = (sel, v) => { for (const b of document.querySelectorAll(`${sel} button`)) b.classList.toggle('ligado', b.dataset.v === v); };
  marcar('#proporcao', cena.proporcao || '16:9');
  marcar('#pintar3d', cena.pintar && cena.pintar !== 'editor' ? cena.pintar : 'material');
  marcar('#arestas3d', cena.arestas === false ? '0' : '1');
  marcar('#fundo3d', cena.fundo || 'ceu');
  marcar('#ambiente3d', cena.fundo || 'ceu');
  const amb = AMBIENTES[cena.fundo || 'ceu'], lz = luzesDaCena();
  $('#luzes3d').hidden = !(amb && amb.noite);
  $('#luz-ref').checked = lz.refletores; $('#luz-int').checked = lz.interna;
  $('#luz-ref-forca').value = lz.forca_ref; $('#luz-int-forca').value = lz.forca_int;
  $('#luz-ref-forca').disabled = !lz.refletores; $('#luz-int-forca').disabled = !lz.interna;
  marcar('#luz-cor', lz.cor);
  const en = entornoDaCena();
  marcar('#entorno3d', en.tipo);
  const bt = document.querySelector('#entorno3d [data-v=terreno]');
  bt.disabled = !(terreno && terreno.malha);
  bt.title = bt.disabled ? 'A obra ainda não tem o terreno (modo ver › Terreno)' : 'A imagem do lugar (modo ver › Terreno)';
  $('#calcada-linha').hidden = !['grama', 'patio', 'terra'].includes(en.tipo);
  $('#calcada').value = en.calcada; $('#calcada-val').textContent = nf(en.calcada, en.calcada % 1 ? 1 : 0) + ' m';
  $('#patio-linha').hidden = en.tipo !== 'patio';
  $('#patio-volta').disabled = !en.patio;
  $('#arvores-linha').hidden = !amb || en.tipo === 'terreno';
  marcar('#arvores3d', String(en.arvores || 0));
  marcar('#figuras-estilo', figurasDaCena().estilo);
  desenharListaFiguras();
  desenharLuzesMao();
  $('#lente3d').value = fovCena; $('#lente3d-val').textContent = nf(fovCena, 0) + '°';
  const pai = document.querySelector('#pintar3d [data-v=sistema]');
  pai.hidden = sistemas.length < 2;
  resumirPainel();
}

/** A miniatura do cartão: a cena do 3D pequena (como no render, sem o quadro), gravada no servidor. */
function agendarMiniatura(espera = 1200) {
  clearTimeout(tempoMini);
  tempoMini = setTimeout(() => gerarMiniatura().catch(e => console.warn('miniatura da cena', e)), espera);
}

async function gerarMiniatura() {
  if (!eh3d() || renderizando || !quadroAtual) return;
  const id = cena.id, p = quadroAtual.p, w = 320, h = Math.max(60, Math.round(320 / p));
  // a vista GRAVADA da cena (a da tela pode ter girado sem "Atualizar"); depois, a da tela de volta
  const tela0 = visor.lerCamera(), c = cena.camera || {};
  if (vistaMudou && c.posicao && c.alvo) visor.definirCamera({ posicao: c.posicao, alvo: c.alvo });
  let img;
  try { img = await imagemDaCena3d(w, h, 1, null, false); }
  finally { if (vistaMudou) { visor.definirCamera(tela0); marcarVista(true); } }
  const jpg = document.createElement('canvas');             // o JPEG não tem transparência: o vazado vai sobre o branco
  jpg.width = w; jpg.height = h;
  const g = jpg.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0);
  const blob = await new Promise(res => jpg.toBlob(res, 'image/jpeg', 0.85));
  const r = await pedir(`${API}/${encodeURIComponent(id)}/miniatura`, undefined, { dados: blob, nome: 'miniatura.jpg' });
  const cartao = todasCenas.find(x => x.id === id);
  if (cartao) { cartao.miniatura = r.miniatura; desenharCartoes(); }
  if (cena && cena.id === id) cena.miniatura = r.miniatura;
}

/** A imagem da cena do 3D em w × h: a lente da cena, o quadro inteiro; o céu pintado antes (o degradê da tela se repetiria
 *  em cada bloco do render) e o 3D por cima. Devolve a tela com a lente do quadro. */
async function imagemDaCena3d(w, h, ss = 1, aoBloco = null, comMarca = true, ceu = null) {
  // `ceu(g, w, h, cam)`: o fundo pintado por quem chama (o vídeo, no meio de um trecho entre dois ambientes)
  const amb = ambienteDaCena(), fundoAntes = visor.cena.background, pintar = ceu || (amb ? (g, w_, h_, cam) => pintarCeu(g, w_, h_, amb, cam) : null);
  visor.camera.fov = fovCena;
  if (pintar) visor.cena.background = null;
  try {
    const img = await montarImagem(w, h, ss, aoBloco, { comFoto: false, frente: false,
      antes: pintar ? (g) => {                              // o céu do ambiente pela câmera da imagem (a lente e a proporção dela)
        const cam = visor.camera.clone(); cam.fov = fovCena; cam.aspect = w / h; cam.clearViewOffset();
        cam.updateProjectionMatrix(); cam.updateMatrixWorld(); pintar(g, w, h, cam);
      } : null });
    if (comMarca) await marcaNaImagem(img);                // a marca d'água
    return img;
  } finally {
    visor.cena.background = fundoAntes;
    ajustarQuadro();
  }
}

// ------------------------------------------------------------------ o vídeo das cenas (12/11)
// (usuário: "fiz uma sequência de cenas… usar ela como ref. e o sistema ir passeando por elas como se fosse uma câmera se
// movimentando"; aprovado: para em cada cena, o visual muda suave no caminho, na janela Exportar). A câmera anda em arco
// de uma cena à outra (video_cenas.js); no meio do trecho a cena de chegada é aberta (as camadas, as figuras, o estilo trocam
// ali); a luz, o céu, o chão e o sol passam de um ambiente ao outro durante o trecho. A marca d'água é a da 1ª cena.
const LUZ_DO_VISOR = { ambCeu: [0.76, 0.81, 0.90], ambChao: [0.58, 0.56, 0.54], ambK: 0.7, solCor: [1.0, 0.97, 0.92], solK: 0.66, pisoAmb: 1, aresta: 1 };

/** O ambiente de uma cena (a luz, as luzes de noite, o sol, o céu, a cor do chão) sem abri-la. */
function visualDaCena(c) {
  const salva = cena; cena = c;
  try {
    const amb = eh3d() ? ambienteDaCena() : null;
    return { amb, fundo: c.fundo || 'ceu', luz: { ...LUZ_DO_VISOR, ...((amb && amb.luz) || {}) }, luzes: amb ? luzesDoAmbiente(amb) : [],
             sol: solDaCena(), piso: amb ? amb.piso : null };
  } finally { cena = salva; }
}

/** O fundo de uma cena na imagem (o céu do ambiente; o branco nos fundos lisos). */
function pintarFundoDe(v, g, w, h, cam) {
  if (v.amb) pintarCeu(g, w, h, v.amb, cam);
  else { g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h); }
}

/** Põe na tela o visual entre a cena A e a B (k de 0 a 1): a luz e as luzes da noite, o chão, o sol; devolve o céu misturado. */
function misturarVisual(A, B, k) {
  const l = (a, b) => Array.isArray(a) ? a.map((v, i) => v + (b[i] - v) * k) : a + (b - a) * k;
  const luz = Object.fromEntries(Object.keys(LUZ_DO_VISOR).map(c => [c, l(A.luz[c], B.luz[c])]));
  const luzes = [...A.luzes.map(x => ({ ...x, forca: x.forca * (1 - k) })), ...B.luzes.map(x => ({ ...x, forca: x.forca * k }))]
    .filter(x => x.forca > 1e-3).sort((a, b) => b.forca - a.forca).slice(0, LUZES_MAX);
  visor.definirAmbiente({ ...luz, luzes }, false);
  const u = visor.piso && visor.piso.material.uniforms;
  if (u && A.piso && B.piso) u.uFundo.value.setStyle(A.piso, THREE.LinearSRGBColorSpace).lerp(new THREE.Color().setStyle(B.piso, THREE.LinearSRGBColorSpace), k);
  if (A.sol.ligado && B.sol.ligado) definirSol(visor, { direcao: anguloEntre(A.sol.direcao, B.sol.direcao, k), altura: A.sol.altura + (B.sol.altura - A.sol.altura) * k });
  return (g, w, h, cam) => {
    pintarFundoDe(A, g, w, h, cam);
    g.save(); g.globalAlpha = k; pintarFundoDe(B, g, w, h, cam); g.restore();
  };
}

/** A abertura e o fechamento do vídeo (12/11, amostra-12: "conseguimos fechar o vídeo com o logo da empresa?"; depois: "não
 *  colocaria esse texto… gostaria de ver o vídeo por dentro do sistema… as outras opções de fechamento e abertura escolher lá
 *  por dentro também, para comparar lado a lado"): o logo da empresa da marca d'água — A no fundo branco; B sobre a vista
 *  desfocada e escurecida (o logo claro); C numa faixa branca embaixo, a obra à vista. `texto`: o nome da obra e "Estrutura
 *  metálica · imagem ilustrativa" (desligado). Sem logo (a marca "sem" ou a empresa sem cadastro): null. */
async function cartaoDoVideo(w, h, marca, jeito, vista, texto = false) {
  if (!['A', 'B', 'C'].includes(jeito) || !marca || marca.empresa === 'sem' || !temLogo(marca.empresa)) return null;
  let logo;
  try { logo = await logoDa(marca.empresa, jeito === 'B' ? 'claro' : 'cor'); } catch (e) { return null; }
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  const g = cv.getContext('2d'), r = logo.naturalWidth / logo.naturalHeight || 3;
  g.imageSmoothingQuality = 'high';
  const obra = ($('#titulo-obra').textContent || '').trim().toUpperCase(), linha = 'Estrutura metálica · imagem ilustrativa';
  const caber = (mw, mh) => { let lw = mw, lh = lw / r; if (lh > mh) { lh = mh; lw = lh * r; } return [lw, lh]; };
  const letra = (peso, k) => `${peso} ${Math.round(h * k)}px "Segoe UI", system-ui, sans-serif`;
  if (jeito === 'C') {                                      // a faixa embaixo, a obra continua à vista
    if (vista) g.drawImage(vista, 0, 0, w, h); else { g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h); }
    const fh = h * 0.2;
    g.fillStyle = 'rgba(255,255,255,.93)'; g.fillRect(0, h - fh, w, fh);
    const [lw, lh] = caber(w * 0.27, fh * 0.42);
    if (!texto) { g.drawImage(logo, (w - lw) / 2, h - fh / 2 - lh / 2, lw, lh); return cv; }
    const x0 = w * 0.04;
    g.drawImage(logo, x0, h - fh / 2 - lh / 2, lw, lh);
    const xs = x0 + lw + w * 0.03;
    g.strokeStyle = '#c8cdd4'; g.lineWidth = Math.max(1, h * 0.002);
    g.beginPath(); g.moveTo(xs, h - fh + fh * 0.2); g.lineTo(xs, h - fh * 0.2); g.stroke();
    g.textAlign = 'left'; g.textBaseline = 'middle';
    g.fillStyle = '#28303c'; g.font = letra(600, 0.037); g.fillText(obra, xs + w * 0.02, h - fh / 2 - h * 0.022);
    g.fillStyle = '#78808c'; g.font = letra(400, 0.026); g.fillText(linha, xs + w * 0.02, h - fh / 2 + h * 0.026);
    return cv;
  }
  if (jeito === 'B' && vista) {                             // sobre a obra: a vista desfocada e escurecida
    g.filter = `blur(${Math.max(2, Math.round(h * 0.006))}px)`; g.drawImage(vista, 0, 0, w, h); g.filter = 'none';
    g.fillStyle = 'rgba(12,18,28,.65)'; g.fillRect(0, 0, w, h);
  } else { g.fillStyle = jeito === 'B' ? '#1b2330' : '#ffffff'; g.fillRect(0, 0, w, h); }
  const [lw, lh] = caber(w * 0.47, h * 0.115), cy = texto ? h * 0.44 : h * 0.5;
  g.drawImage(logo, (w - lw) / 2, cy - lh / 2, lw, lh);
  if (texto) {
    g.textAlign = 'center'; g.textBaseline = 'top';
    g.fillStyle = jeito === 'B' ? '#ffffff' : '#3c4652'; g.font = letra(600, 0.037); g.fillText(obra, w / 2, cy + lh / 2 + h * 0.046);
    g.fillStyle = jeito === 'B' ? '#c8d0da' : '#828a96'; g.font = letra(400, 0.026); g.fillText(linha, w / 2, cy + lh / 2 + h * 0.097);
  }
  return cv;
}
const FECHO_SUMIR = 1, FECHO_FICAR = 3, ABERTURA_FICAR = 2, ABERTURA_SUMIR = 1;   // s
const suaveFecho = (t) => t * t * (3 - 2 * t);

/** Passa de uma imagem à outra em `segundos` (o quadro do meio misturado), no gravador. */
async function dissolver(gravador, de, para, segundos, fps, cancelado, aoAndar) {
  const w = de.width, h = de.height, mistura = document.createElement('canvas'); mistura.width = w; mistura.height = h;
  const g = mistura.getContext('2d'), n = Math.max(1, Math.round(segundos * fps));
  for (let k = 1; k <= n; k++) {
    if (cancelado()) throw new Error('cancelado');
    g.globalAlpha = 1; g.drawImage(de, 0, 0);
    g.globalAlpha = suaveFecho(k / n); g.drawImage(para, 0, 0);
    await gravador.quadro(mistura);
    if (aoAndar) await aoAndar(k, n);
  }
  return n;
}

/** O vídeo das cenas `ids` (as do 3D, nessa ordem): o lado maior `lado` na proporção da 1ª cena, `porTrecho` segundos de uma
 *  cena à outra, `parada` segundos parado em cada uma; `aoAndar(f, total, texto)` a cada quadro; `cancelado()` para. Devolve o
 *  MP4 (Blob) e os números. */
async function videoDasCenas({ ids, lado = 1920, fps = 30, porTrecho = 3, parada = 0, ss = 1, fecho = 'A', abertura = 'nenhuma', texto = false,
                               aoAndar = null, cancelado = () => false }) {
  if (fecho === true) fecho = 'A'; else if (fecho === false) fecho = 'nenhum';
  const lista = ids.map(id => todasCenas.find(c => c.id === id)).filter(c => c && c.tipo === '3d' && c.camera && c.camera.posicao && c.camera.alvo);
  if (lista.length < 2) throw new Error('escolha duas cenas do 3D ou mais');
  const voltar = cena && cena.id;
  if (!(await abrirCena(lista[0].id, { recarregar: false }))) {
    if (!cena || cena.id !== lista[0].id) throw new Error(`a cena ${lista[0].nome} é da outra situação da cobertura`);
  }
  let [w, h] = tamanho3d(lado); w -= w % 2; h -= h % 2;
  // sem parada (o padrão, 12/11: "como se fosse um drone sobrevoando a estrutura"): uma curva só, na velocidade constante
  const marca = marcaDaCena(), linha = parada > 0 ? linhaDoTempo(lista.length, { porTrecho, parada, fps })
    : caminhoContinuo(lista.map(c => c.camera), { porTrecho, fps });
  const gravador = await GravadorMp4.abrir(w, h, fps);
  const visuais = new Map();                                 // o visual de cada cena, lido uma vez (com a cena dela)
  const visual = (c) => { if (!visuais.has(c.id)) visuais.set(c.id, visualDaCena(cena && cena.id === c.id ? cena : c)); return visuais.get(c.id); };
  const t0 = performance.now();
  let aberta = lista[0].id, img = null, quadros = 0;
  renderizando = true; mostrarBotoes();
  const quadroDoVoo = async (q) => {
    const A = lista[q.i], B = lista[q.j];
    const chegando = q.k >= 0.5 ? B : A;                     // as camadas, as figuras e o estilo trocam no meio do trecho
    if (chegando.id !== aberta) {
      if (!(await abrirCena(chegando.id, { recarregar: false }))) { if (!cena || cena.id !== chegando.id) throw new Error(`a cena ${chegando.nome} é da outra situação da cobertura`); }
      aberta = chegando.id;
      renderizando = true;
    }
    const cam = q.cam || cameraEntre(A.camera, B.camera, q.k);
    visor.definirCamera({ posicao: cam.posicao, alvo: cam.alvo });
    fovCena = cam.fov;
    let ceu = null;
    if (q.i !== q.j && q.k > 0 && q.k < 1) ceu = misturarVisual(visual(A), visual(B), q.k);
    const quadro = await imagemDaCena3d(w, h, ss, null, false, ceu);
    await desenharMarca(quadro, marca);
    return quadro;
  };
  try {
    // a abertura (opção): o cartão parado e depois ele some na primeira vista do voo
    let abriu = false;
    if (abertura && abertura !== 'nenhuma') {
      const primeira = await quadroDoVoo(linha.quadro(0));
      const sem = document.createElement('canvas'); sem.width = w; sem.height = h;   // o cartão sobre a vista sem a marca do canto
      sem.getContext('2d').drawImage(await imagemDaCena3d(w, h, ss, null, false, null), 0, 0);
      const cartao = await cartaoDoVideo(w, h, marca, abertura, sem, texto);
      if (cartao) {
        await gravador.quadro(cartao, Math.round(ABERTURA_FICAR * fps));
        quadros += Math.round(ABERTURA_FICAR * fps);
        quadros += await dissolver(gravador, cartao, primeira, ABERTURA_SUMIR, fps, cancelado, aoAndar && ((k, n) => aoAndar(k, n, 'abertura com o logo')));
        abriu = true;
      }
    }
    for (let f = 0; f < linha.total; f++) {
      if (cancelado()) throw new Error('cancelado');
      const q = linha.quadro(f), A = lista[q.i], B = lista[q.j];
      if (q.parado && img) { await gravador.quadro(img); quadros++; continue; }
      img = await quadroDoVoo(q);
      await gravador.quadro(img); quadros++;
      if (aoAndar) await aoAndar(f + 1, linha.total, q.i === q.j ? lista[q.i].nome : `${A.nome} → ${B.nome}`);
    }
    // o fechamento: a última vista some no cartão, que fica parado (B e C feitos sobre a última vista, sem a marca do canto)
    let fechou = false;
    if (fecho && fecho !== 'nenhum' && img) {
      const ultima = fecho === 'A' ? null : await imagemDaCena3d(w, h, ss, null, false, null);
      const cartao = await cartaoDoVideo(w, h, marca, fecho, ultima, texto);
      if (cartao) {
        quadros += await dissolver(gravador, img, cartao, FECHO_SUMIR, fps, cancelado, aoAndar && ((k, n) => aoAndar(k, n, 'fechamento com o logo')));
        await gravador.quadro(cartao, Math.round(FECHO_FICAR * fps));
        quadros += Math.round(FECHO_FICAR * fps);
        fechou = true;
      }
    }
    const mp4 = await gravador.fim();
    return { mp4, w, h, fps, quadros, segundos: quadros / fps, demorou: (performance.now() - t0) / 1000, cenas: lista.length, fecho: fechou, abertura: abriu };
  } catch (e) { gravador.cancelar(); throw e; }
  finally {
    renderizando = false;
    if (voltar && (!cena || cena.id !== voltar)) await abrirCena(voltar, { recarregar: false }).catch(() => {});
    else if (eh3d()) { aplicarEstilo3d(); aplicarSol(); aplicarVistaDaCena(); }
    mostrarBotoes();
  }
}

/** Uma caixa de texto da tela (o prompt do navegador trava os testes e o quadro): o texto ou null. */
function pedirTexto(titulo, valor) {
  return new Promise((fim) => {
    const fundo = document.createElement('div');
    fundo.id = 'caixa-cena';
    fundo.style.cssText = 'position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.25)';
    fundo.innerHTML = `<div style="width:min(360px,calc(100vw - 32px));padding:14px 16px;background:var(--painel);border:1px solid var(--borda);border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.3)">
      <b>${esc(titulo)}</b><input type="text" value="${esc(valor)}" style="width:100%;box-sizing:border-box;margin:10px 0;padding:6px 8px;font:13px var(--sans)">
      <div class="linha"><button type="button" class="forte" data-r="ok">OK</button><button type="button" data-r="nao">Cancelar</button></div></div>`;
    document.body.append(fundo);
    const campo = fundo.querySelector('input');
    const sair = (sim) => { fundo.remove(); fim(sim ? campo.value.trim() || null : null); };
    fundo.querySelector('[data-r=ok]').onclick = () => sair(true);
    fundo.querySelector('[data-r=nao]').onclick = () => sair(false);
    fundo.onkeydown = (ev) => { ev.stopPropagation(); if (ev.key === 'Enter') sair(true); else if (ev.key === 'Escape') sair(false); };
    campo.focus(); campo.select();
  });
}

/** A cena nova pela vista de agora: a câmera (a lente do quadro 16:9 na primeira), as camadas, o sol e o estilo de agora. */
async function novaCena3d(nome) {
  if (!visor) return null;
  if (nome === undefined) {
    nome = await pedirTexto('Nova cena pela vista', `Cena ${todasCenas.filter(c => c.tipo === '3d').length + 1}`);
    if (nome === null) return null;
  }
  let fov = fovCena;
  if (!eh3d()) {                                            // de fora de uma cena: o que se vê na tela cabe no quadro 16:9
    const W = palco.clientWidth, H = palco.clientHeight, qh = Math.min(H - 120, (W - 48) / (16 / 9));
    fov = Math.atan(Math.tan(visor.camera.fov * Math.PI / 360) * qh / H) * 360 / Math.PI;
  }
  const base = eh3d() ? { pintar: cena.pintar, arestas: cena.arestas, fundo: cena.fundo, proporcao: cena.proporcao } : { proporcao: '16:9', fundo: 'ceu' };
  const c = visor.lerCamera();
  try {
    const nova = await pedir(`${API}/nova-3d`, { nome, ...base, camera: { posicao: c.posicao, alvo: c.alvo, fov, projecao: 'perspectiva' },
      desligadas: desligadasAgora(), sol: solDaCena(), situacao: situacaoAberta });
    await listar(nova.id);
    aviso(`Cena ${nova.nome} gravada (também nas abas do modo ver).`);
    return nova;
  } catch (e) { aviso('A cena não foi gravada: ' + e.message); return null; }
}

async function atualizarVista() {
  if (!eh3d()) return;
  lembrar();
  try {
    await gravar({ camera: cameraDaTela() });
    marcarVista(false);
    desenharFiguras();                                      // as árvores do fundo pela vista nova
    agendarMiniatura(200);
    atualizarCartoes();
    aviso('A cena ficou com esta vista.');
  } catch (e) { aviso('A vista não foi gravada: ' + e.message); }
}

/** Uma mudança de estilo/enquadramento da cena do 3D: na tela já, gravada logo depois (o valor de agora). */
let tempo3d = 0;
function mudar3d(campos, tipo) {
  lembrar(tipo || null);
  Object.assign(cena, campos);
  aplicarEstilo3d();
  ajustarQuadro();
  mostrarPainel3d();
  clearTimeout(tempo3d);
  const valor = JSON.parse(JSON.stringify(campos));
  tempo3d = setTimeout(() => gravar(valor).then(() => { agendarMiniatura(); atualizarCartoes(); })
    .catch(e => aviso('Não foi gravado: ' + e.message)), tipo ? 500 : 0);
}

let menuCartao = null;
function fecharMenuCartao() { if (menuCartao) { menuCartao.remove(); menuCartao = null; } }
function menuDoCartao(c, el) {
  fecharMenuCartao();
  menuCartao = document.createElement('div');
  menuCartao.id = 'menu-cartao';
  const ordem = todasCenas.map(x => x.id), k = ordem.indexOf(c.id);
  const mover = async (d) => {
    const j = k + d; if (j < 0 || j >= ordem.length) return;
    [ordem[k], ordem[j]] = [ordem[j], ordem[k]];
    try { todasCenas = (await pedir(`${API}/ordem`, { ids: ordem })).cenas; desenharCartoes(); } catch (e) { aviso('Não deu: ' + e.message); }
  };
  const itens = [['Renomear…', async () => {
      const nome = await pedirTexto('Renomear a cena', c.nome);
      if (!nome || nome === c.nome) return;
      await pedir(`${API}/${encodeURIComponent(c.id)}`, { nome });
      if (cena && cena.id === c.id) { cena.nome = nome; mostrarPainel3d(); }
      atualizarCartoes();
    }]];
  if (c.tipo === '3d') itens.push(['Duplicar', async () => {
    const campos = ['camera', 'desligadas', 'pintar', 'arestas', 'planta', 'piso_oculto', 'sol', 'situacao', 'guarda', 'proporcao', 'fundo',
                    'luzes', 'entorno', 'figuras', 'marca'];
    const copia = Object.fromEntries(campos.filter(f => c[f] !== undefined).map(f => [f, c[f]]));
    try { const n = await pedir(`${API}/nova-3d`, { ...copia, nome: c.nome + ' (cópia)' }); await listar(n.id); } catch (e) { aviso('Não deu: ' + e.message); }
  }]);
  itens.push(['Copiar ajustes para outras cenas…', () => copiarAjustes(c)]);
  if (c.render_arquivo || c.imagem_arquivo) {
    const nome = c.render_arquivo || c.imagem_arquivo;
    itens.push([c.render_arquivo ? 'Mostrar o render na pasta' : 'Mostrar a imagem na pasta',
                () => mostrarNaPasta(nome).catch(e => aviso('A pasta não abriu: ' + e.message))]);
  }
  itens.push(['Mover para cima', () => mover(-1)], ['Mover para baixo', () => mover(1)], ['Apagar…', () => apagarCena(c)]);
  for (const [t, fazer] of itens) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = t; b.dataset.acao = t;
    b.onclick = () => { fecharMenuCartao(); fazer(); };
    menuCartao.append(b);
  }
  document.body.append(menuCartao);
  const r = el.getBoundingClientRect();
  menuCartao.style.left = `${r.right - 20}px`;
  menuCartao.style.top = `${Math.min(r.top, innerHeight - menuCartao.offsetHeight - 8)}px`;
  setTimeout(() => addEventListener('pointerdown', function fora(ev) {
    if (menuCartao && !menuCartao.contains(ev.target)) { fecharMenuCartao(); removeEventListener('pointerdown', fora, true); }
  }, true), 0);
}

// ------------------------------------------------------------------ copiar ajustes para outras cenas (11/11)
// (usuário: "quando ajusto as configurações em uma cena poderia já fazer o ajuste para outras ou ter a opção de copiar de uma
// cena para (sol, terreno...)"): a janela marca O QUE (o sol, o ambiente — céu, noite, terreno… e as luzes —, as camadas,
// o estilo, o enquadramento, a marca d'água) e PARA QUAIS cenas; o servidor copia (…/cenas/copiar). A vista (a posição da
// câmera) de cada uma fica. Na cena da foto só vale o que ela tem.
const GRUPOS_COPIA = [['sol', 'Luz — o sol e a sombra', true], ['ambiente', 'Ambiente — o céu, a noite, o terreno… e as luzes da noite', true],
                      ['figuras', 'Pessoas, veículos e árvores postas', false],
                      ['camadas', 'O que aparece — as camadas e os sistemas', false], ['estilo', 'Estilo — as cores e as arestas', false],
                      ['enquadramento', 'Enquadramento — a proporção e a lente', false], ['marca', 'Marca d\'água', false]];
const SO_3D = new Set(['ambiente', 'figuras', 'estilo', 'enquadramento']);

function copiarAjustes(origem) {
  if (!origem) return;
  const outras = todasCenas.filter(c => c.id !== origem.id);
  if (!outras.length) { aviso('Não há outra cena para receber os ajustes.'); return; }
  const fundo = document.createElement('div');
  fundo.id = 'caixa-copiar';
  fundo.style.cssText = 'position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.25)';
  const marca = (v, t, sim, extra = '') => `<label style="display:flex;gap:6px;align-items:baseline;line-height:1.6"><input type="checkbox" value="${esc(v)}"${sim ? ' checked' : ''}${extra}> <span>${t}</span></label>`;
  fundo.innerHTML = `<div style="width:min(460px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;padding:14px 16px;background:var(--painel);border:1px solid var(--borda);border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.3)">
    <b>Copiar os ajustes de “${esc(origem.nome)}”</b>
    <p class="titulo-secao" style="margin-top:10px">O quê</p><div id="copiar-grupos">${GRUPOS_COPIA.map(([v, t, sim]) => marca(v, t + (SO_3D.has(v) ? ' <small style="color:var(--texto2)">(só cenas do 3D)</small>' : ''), sim)).join('')}</div>
    <p class="titulo-secao" style="margin-top:10px">Para quais cenas</p>
    ${marca('*todas', '<b>Todas as outras</b>', true)}
    <div id="copiar-cenas" style="margin-left:18px">${outras.map(c => marca(c.id, `${esc(c.nome)} <small style="color:var(--texto2)">${c.tipo === '3d' ? '3D' : 'foto'}</small>`, true)).join('')}</div>
    <p class="dica" style="margin:8px 0">A vista de cada cena (de onde se olha) não muda. O render já feito delas fica marcado como velho.</p>
    <div class="linha"><button type="button" class="forte" data-r="ok">Copiar</button><button type="button" data-r="nao">Cancelar</button></div></div>`;
  document.body.append(fundo);
  const todas = fundo.querySelector('input[value="*todas"]'), caixas = [...fundo.querySelectorAll('#copiar-cenas input')];
  todas.onchange = () => caixas.forEach(c => { c.checked = todas.checked; });
  caixas.forEach(c => { c.onchange = () => { todas.checked = caixas.every(x => x.checked); }; });
  const sair = () => fundo.remove();
  fundo.querySelector('[data-r=nao]').onclick = sair;
  fundo.onkeydown = (ev) => { ev.stopPropagation(); if (ev.key === 'Escape') sair(); };
  fundo.querySelector('[data-r=ok]').onclick = async () => {
    const grupos = [...fundo.querySelectorAll('#copiar-grupos input:checked')].map(i => i.value);
    const para = caixas.filter(c => c.checked).map(c => c.value);
    if (!grupos.length || !para.length) { aviso('Marque o que copiar e para quais cenas.'); return; }
    sair();
    try {
      if (cena && cena.id === origem.id) { clearTimeout(tempo3d); await gravar(Object.fromEntries(['sol', 'fundo', 'luzes', 'desligadas', 'pintar', 'arestas', 'proporcao', 'marca'].filter(k => cena[k] !== undefined).map(k => [k, cena[k]]))); }
      const r = await pedir(`${API}/copiar`, { de: origem.id, para, grupos });
      todasCenas = r.cenas || todasCenas; desenharCartoes();
      if (cena && r.copiadas.includes(cena.id)) await abrirCena(cena.id);   // a aberta recebeu: a tela com o que foi gravado
      window.ultimaCopiaCenas = r.copiadas;
      aviso(`Ajustes copiados para ${r.copiadas.length} ${r.copiadas.length === 1 ? 'cena' : 'cenas'}.`);
    } catch (e) { aviso('Os ajustes não foram copiados: ' + e.message); }
  };
}

async function apagarCena(c) {
  const texto = c.tipo === '3d' ? `Apagar a cena "${c.nome}"? (o modelo não muda; a imagem salva na pasta cenas fica)`
    : `Apagar a cena "${c.nome}"? A foto e os pontos saem do projeto (a imagem salva na pasta cenas fica).`;
  if (!confirm(texto)) return;
  try {
    await pedir(`${API}/${encodeURIComponent(c.id)}/apagar`, {});
    if (cena && cena.id === c.id) { sairDaCena(); cena = null; }
    aviso('Cena apagada.');
    await listar();
  } catch (err) { aviso('A cena não foi apagada: ' + err.message); }
}

function ligar3d() {
  $('#cartoes').onclick = (e) => {
    const b = e.target.closest('.cartao-cena');
    if (!b || renderizando) return;
    cancelar();
    if (!cena || cena.id !== b.dataset.cena) abrirCena(b.dataset.cena).catch(err => aviso('A cena não abriu: ' + err.message));
  };
  $('#cartoes').oncontextmenu = (e) => {
    const b = e.target.closest('.cartao-cena');
    if (!b) return;
    e.preventDefault();
    const c = todasCenas.find(x => x.id === b.dataset.cena);
    if (c) menuDoCartao(c, b);
  };
  $('#nova-3d').onclick = () => novaCena3d();
  $('#apagar-3d').onclick = () => { $('#menu-mais').hidden = true; if (cena) apagarCena(cena); };
  $('#copiar-3d').onclick = () => { $('#menu-mais').hidden = true; if (cena) copiarAjustes(cena); };
  $('#mais-cena').onclick = (ev) => { ev.stopPropagation(); $('#menu-mais').hidden = !$('#menu-mais').hidden; };
  addEventListener('pointerdown', (ev) => { if (!ev.target.closest('#menu-mais, #mais-cena')) $('#menu-mais').hidden = true; });
  // a seção aberta fica a mesma de uma cena para outra (e de uma vez para outra, no navegador)
  const CHAVE_SECAO = 'cena.secaoAberta';
  let aberta = 'sec-ambiente';
  try { aberta = localStorage.getItem(CHAVE_SECAO) || aberta; } catch (e) { /* sem o navegador guardar */ }
  const sec = document.getElementById(aberta); if (sec) sec.open = true;
  for (const d of document.querySelectorAll('details.secao')) d.addEventListener('toggle', () => {
    if (d.open) try { localStorage.setItem(CHAVE_SECAO, d.id); } catch (e) { /* idem */ }
  });
  $('#copiar-ajustes').onclick = () => cena && copiarAjustes(cena);
  $('#cena-nome').onchange = async () => {
    const nome = $('#cena-nome').value.trim();
    if (!eh3d() || !nome || nome === cena.nome) return;
    try { await gravar({ nome }); atualizarCartoes(); } catch (e) { aviso('O nome não foi gravado: ' + e.message); }
  };
  $('#cena-nome').onkeydown = (e) => { if (e.key === 'Enter') e.target.blur(); };
  const opcoes = (sel, campo, conv = v => v) => {
    $(sel).onclick = (e) => {
      const b = e.target.closest('button[data-v]');
      if (!b || !eh3d() || b.disabled) return;
      mudar3d({ [campo]: conv(b.dataset.v) });
    };
  };
  opcoes('#proporcao', 'proporcao');
  opcoes('#pintar3d', 'pintar');
  opcoes('#arestas3d', 'arestas', v => v === '1');
  // o ambiente ou o fundo liso (11/11, amostra-6): o entardecer abaixa o sol (sombra comprida); voltar ao dia com o sol
  // muito baixo o sobe para o padrão
  const escolherFundo = (e) => {
    const b = e.target.closest('button[data-v]');
    if (!b || !eh3d() || b.disabled) return;
    const f = b.dataset.v, amb = AMBIENTES[f], sol = solDaCena(), campos = { fundo: f };
    if (amb && amb.solAltura && sol.altura > 20) campos.sol = { ...sol, altura: amb.solAltura };
    else if (f === 'ceu' && sol.altura < 15) campos.sol = { ...sol, altura: SOL_PADRAO.altura };
    mudar3d(campos);
    if (campos.sol) { mostrarSol(); aplicarSol(); }
  };
  $('#fundo3d').onclick = escolherFundo;
  $('#ambiente3d').onclick = escolherFundo;
  const mudarLuzes = (mud, tipo) => { if (eh3d()) mudar3d({ luzes: { ...luzesDaCena(), ...mud } }, tipo); };
  $('#luz-ref').onchange = () => mudarLuzes({ refletores: $('#luz-ref').checked });
  $('#luz-int').onchange = () => mudarLuzes({ interna: $('#luz-int').checked });
  $('#luz-ref-forca').oninput = () => mudarLuzes({ forca_ref: +$('#luz-ref-forca').value }, 'luz-ref');
  $('#luz-int-forca').oninput = () => mudarLuzes({ forca_int: +$('#luz-int-forca').value }, 'luz-int');
  $('#luz-cor').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b) mudarLuzes({ cor: b.dataset.v }); };
  // o entorno (12/11, amostra-8)
  const mudarEntorno = (mud, tipo) => { if (eh3d()) mudar3d({ entorno: { ...entornoDaCena(), ...mud } }, tipo); };
  $('#entorno3d').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b && !b.disabled) mudarEntorno({ tipo: b.dataset.v }); };
  $('#calcada').oninput = () => { $('#calcada-val').textContent = nf(+$('#calcada').value, 1) + ' m'; mudarEntorno({ calcada: +$('#calcada').value }, 'calcada'); };
  $('#patio-desenhar').onclick = () => comecarAColocar({ tipo: 'patio' });
  $('#patio-volta').onclick = () => mudarEntorno({ patio: null });
  $('#arvores3d').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b) mudarEntorno({ arvores: +b.dataset.v }); };
  // as figuras (12/11, amostra-9): o estilo; o tipo e os cliques no chão (até Esc); girar, mover e tirar na lista
  const mudarFiguras = (mud) => { if (eh3d()) mudar3d({ figuras: { ...figurasDaCena(), ...mud } }); };
  $('#figuras-estilo').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b) mudarFiguras({ estilo: b.dataset.v }); };
  for (const b of document.querySelectorAll('.bt-figuras button')) b.onclick = () => comecarAColocar({ tipo: b.dataset.tipo, figura: true });
  $('#figuras-lista').onclick = (e) => {
    const b = e.target.closest('button[data-r]'), it = e.target.closest('.item-luz');
    if (!b || !it) return;
    const i = +it.dataset.i, itens = [...figurasDaCena().itens];
    if (b.dataset.r === 'tirar') { itens.splice(i, 1); mudarFiguras({ itens }); }
    else if (b.dataset.r === 'girar') { itens[i] = { ...itens[i], giro: ((+itens[i].giro || 0) + 45) % 360 }; mudarFiguras({ itens }); }
    else comecarAColocar({ tipo: itens[i].tipo, figura: true, i });
  };
  $('#figuras-tirar').onclick = () => { if (figurasDaCena().itens.length) { mudarFiguras({ itens: [] }); aviso('As figuras saíram da cena (↶ desfaz).'); } };
  // as luzes postas à mão: o tipo, depois o clique no 3D
  for (const b of document.querySelectorAll('.bt-luzes button')) b.onclick = () => comecarAColocar({ tipo: b.dataset.tipo });
  $('#luzes-mao').onclick = (e) => {
    const b = e.target.closest('button[data-r]'), it = e.target.closest('.item-luz');
    if (!b || !it) return;
    const i = +it.dataset.i, mao = [...(luzesDaCena().mao || [])];
    if (b.dataset.r === 'tirar') { mao.splice(i, 1); mudarLuzes({ mao }); }
    else comecarAColocar({ tipo: mao[i].tipo, i });
  };
  $('#luzes-mao').oninput = (e) => {
    const it = e.target.closest('.item-luz');
    if (!it || e.target.type !== 'range') return;
    const mao = (luzesDaCena().mao || []).map((m, k) => k === +it.dataset.i ? { ...m, forca: +e.target.value } : m);
    mudarLuzes({ mao }, 'luz-mao-' + it.dataset.i);
  };
  palco.addEventListener('pointerdown', (ev) => { if (colocando && eh3d() && !ev.target.closest('#barra-palco')) { ev.stopPropagation(); ev.preventDefault(); colocarEm(ev); } }, true);
  addEventListener('keydown', (ev) => { if (colocando && ev.key === 'Escape') { pararDeColocar(); aviso('Cancelado.'); } });
  $('#lente3d').oninput = () => {
    if (!eh3d()) return;
    lembrar('lente3d');
    fovCena = +$('#lente3d').value;
    $('#lente3d-val').textContent = nf(fovCena, 0) + '°';
    ajustarQuadro();
    cena.camera = { ...(cena.camera || {}), fov: fovCena };
    clearTimeout(tempo3d);
    tempo3d = setTimeout(() => gravar({ camera: cameraDaTela() }).then(() => { marcarVista(false); agendarMiniatura(); })
      .catch(e => aviso('A lente não foi gravada: ' + e.message)), 600);
  };
  for (const b of document.querySelectorAll('#barra-palco [data-vista]')) b.onclick = () => { visor.enquadrar(b.dataset.vista); marcarVista(true); };
  $('#atualizar-vista').onclick = () => atualizarVista();
  $('#desfazer-vista').onclick = () => { if (eh3d()) { aplicarVistaDaCena(); aviso('A vista da cena de volta.'); } };
  $('#btn-desfazer').onclick = () => desfazer();
  $('#btn-refazer').onclick = () => refazer();
}

// ------------------------------------------------------------------ a marca d'água (11/11)
// Aprovada na amostra-3: B — o logo em cor numa placa branca translúcida no canto de baixo — é o padrão; A (o logo claro
// solto) e C (a faixa com o nome da obra) na hora. A empresa é a do projeto (a do carimbo das pranchas; sem = Hermes),
// trocável, ou "sem". Sai em TODA imagem (Salvar imagem e Renderizar), nas cenas do 3D e nas da foto. Os tamanhos são
// frações de √(largura × altura): a prévia na tela e a imagem de 8.000 px ficam iguais.

let marcaInfo = { padrao: 'principal', empresas: [] };
const logosMarca = new Map();

async function carregarMarcas() {
  try { marcaInfo = await pedir(`${API}/marca`); } catch (e) { /* sem empresas: a principal */ }
}

function marcaDaCena() {
  return { empresa: marcaInfo.padrao || 'principal', jeito: 'B', canto: 'dir', ...((cena && cena.marca) || {}) };
}

/** A empresa tem logo para a marca? (a lista do servidor diz; sem a lista, tenta) */
function temLogo(empresa) {
  const e = (marcaInfo.empresas || []).find(x => x.id === empresa);
  return e ? e.logo !== false : !(marcaInfo.empresas || []).length;
}

/** O logo como imagem (o SVG sem largura ganha a do viewBox: o navegador o desenharia com 300 × 150). */
async function logoDa(empresa, tom) {
  const chave = empresa + '/' + tom;
  if (logosMarca.has(chave)) return logosMarca.get(chave);
  const promessa = (async () => {
    const r = await fetch(`${API}/marca/${encodeURIComponent(empresa)}/${tom}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erro || `erro ${r.status}`);
    let blob = await r.blob();
    if (/svg/.test(blob.type)) {
      let txt = await blob.text();
      const vb = /viewBox\s*=\s*"([^"]+)"/.exec(txt);
      if (vb && !/<svg[^>]*\swidth=/.test(txt)) {
        const [, , w, h] = vb[1].trim().split(/[\s,]+/).map(Number);
        txt = txt.replace(/<svg/, `<svg width="${1000}" height="${Math.round(1000 * h / w)}"`);
      }
      blob = new Blob([txt], { type: 'image/svg+xml' });
    }
    const img = new Image();
    img.src = URL.createObjectURL(blob);
    await img.decode();
    return img;
  })();
  logosMarca.set(chave, promessa);                          // a falha também fica: não se pede de novo a cada prévia
  return promessa;
}

/** O tamanho do logo [w, h] na marca A ou B para o logo de proporção `r` (largura/altura) e a base √(W × H). A altura tem
 *  teto perto da do logo comprido da Hermes (7,7 : 1, 0,026 da base): o logo mais "quadrado" (a DEZN, ~3,3 : 1) saía com a placa
 *  2,4 vezes mais alta (usuário, 12/11: "pode diminuir a altura desse quadro para ficar no mesmo padrão da Hermes"). */
function medidaDoLogo(jeito, r, base) {
  const [mw, mh] = jeito === 'B' ? [base * 0.2, base * 0.028] : [base * 0.22, base * 0.031];
  let w = mw, h = w / r;
  if (h > mh) { h = mh; w = h * r; }
  return [w, h];
}

/** Desenha a marca `m` no canvas inteiro (a imagem pronta ou a prévia). */
async function desenharMarca(cv, m) {
  if (!m || m.empresa === 'sem' || !temLogo(m.empresa)) return;
  const logo = await logoDa(m.empresa, m.jeito === 'B' ? 'cor' : 'claro');
  const g = cv.getContext('2d'), W = cv.width, H = cv.height, base = Math.sqrt(W * H);
  const r = logo.naturalWidth / logo.naturalHeight || 3, esq = m.canto === 'esq', marg = base * 0.025;
  const caber = (mw, mh) => { let w = mw, h = w / r; if (h > mh) { h = mh; w = h * r; } return [w, h]; };
  g.save();
  if (m.jeito === 'C') {
    const fh = Math.max(base * 0.075, 24);
    const grad = g.createLinearGradient(0, H - fh, 0, H);
    grad.addColorStop(0, 'rgba(10,14,20,.55)'); grad.addColorStop(1, 'rgba(10,14,20,.78)');
    g.fillStyle = grad; g.fillRect(0, H - fh, W, fh);
    const [lw, lh] = caber(W * 0.25, fh * 0.36);
    g.drawImage(logo, esq ? marg : W - marg - lw, H - fh / 2 - lh / 2, lw, lh);
    const xt = esq ? W - marg : marg, mes = new Date().toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }).replace(' de ', '/');
    g.textAlign = esq ? 'right' : 'left';
    g.fillStyle = '#fff'; g.font = `600 ${Math.round(fh * 0.26)}px "Segoe UI", system-ui, sans-serif`;
    g.fillText(($('#titulo-obra').textContent || '').toUpperCase(), xt, H - fh * 0.5);
    g.fillStyle = '#c9d1db'; g.font = `${Math.round(fh * 0.19)}px "Segoe UI", system-ui, sans-serif`;
    g.fillText(`Imagem ilustrativa · ${mes}`, xt, H - fh * 0.2);
  } else if (m.jeito === 'B') {
    const [lw, lh] = medidaDoLogo('B', r, base);
    const pad = Math.max(lh * 0.3, base * 0.008), pw = lw + 2 * pad, ph = lh + 2 * pad;
    const x = esq ? marg : W - marg - pw, y = H - marg - ph;
    g.shadowColor = 'rgba(0,0,0,.25)'; g.shadowBlur = base * 0.006;
    g.fillStyle = 'rgba(255,255,255,.82)';
    g.beginPath(); g.roundRect(x, y, pw, ph, pad * 0.8); g.fill();
    g.shadowColor = 'transparent'; g.shadowBlur = 0;
    g.drawImage(logo, x + pad, y + pad, lw, lh);
  } else {
    const [lw, lh] = medidaDoLogo('A', r, base);
    g.globalAlpha = 0.88; g.shadowColor = 'rgba(0,0,0,.55)'; g.shadowBlur = base * 0.004; g.shadowOffsetY = base * 0.001;
    g.drawImage(logo, esq ? marg : W - marg - lw, H - marg - lh, lw, lh);
  }
  g.restore();
}

/** A marca da cena na imagem pronta; sem o logo (empresa sem cadastro), a imagem sai sem ela e a tela avisa. */
async function marcaNaImagem(cv) {
  const m = marcaDaCena();
  if (m.empresa !== 'sem' && !temLogo(m.empresa)) { aviso("Sem a marca d'água: a empresa não tem logo cadastrado (Comercial › Empresa)."); return; }
  try { await desenharMarca(cv, m); }
  catch (e) { aviso('A imagem saiu sem a marca d\'água: ' + e.message); }
}

/** A prévia da marca por cima do quadro (cena do 3D) ou da foto. */
let quadroMarca = 0;
function desenharPreviaMarca() {
  cancelAnimationFrame(quadroMarca);
  quadroMarca = requestAnimationFrame(async () => {
    const cv = $('#marca-previa');
    const r = eh3d() && quadroAtual ? quadroAtual : (ehFoto() && modo === 'foto' ? retanguloFoto() : null);
    const m = marcaDaCena();
    if (!r || m.empresa === 'sem' || !temLogo(m.empresa)) { cv.hidden = true; return; }
    const dpr = window.devicePixelRatio || 1;
    Object.assign(cv.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
    cv.width = Math.round(r.w * dpr); cv.height = Math.round(r.h * dpr);
    cv.hidden = false;
    try { await desenharMarca(cv, marcaDaCena()); } catch (e) { cv.hidden = true; }
  });
}

function mostrarMarca() {
  $('#marca-bloco').hidden = !cena;
  if (!cena) { $('#marca-previa').hidden = true; return; }
  const m = marcaDaCena();
  const emps = (marcaInfo.empresas || []).length ? marcaInfo.empresas : [{ id: 'principal', nome: 'Hermes' }];
  $('#marca-empresa').innerHTML = emps.map(e => `<button type="button" data-v="${esc(e.id)}"${e.logo === false ? ' disabled title="Sem logo cadastrado (Comercial › Empresa)"' : ''}>${esc(e.nome)}</button>`).join('')
    + '<button type="button" data-v="sem">sem</button>';
  const marcar = (sel, v) => { for (const b of document.querySelectorAll(`${sel} button`)) b.classList.toggle('ligado', b.dataset.v === v); };
  marcar('#marca-empresa', m.empresa); marcar('#marca-jeito', m.jeito); marcar('#marca-canto', m.canto);
  desenharPreviaMarca();
  resumirPainel();
}

let tempoMarca = 0;
function mudarMarca(campos) {
  if (!cena) return;
  lembrar('marca');
  cena.marca = { ...marcaDaCena(), ...campos };
  mostrarMarca();
  const marca = cena.marca;
  clearTimeout(tempoMarca);
  tempoMarca = setTimeout(() => gravar({ marca }).catch(e => aviso('A marca não foi gravada: ' + e.message)), 300);
}

function ligarMarca() {
  for (const [sel, campo] of [['#marca-empresa', 'empresa'], ['#marca-jeito', 'jeito'], ['#marca-canto', 'canto']]) {
    $(sel).onclick = (e) => { const b = e.target.closest('button[data-v]'); if (b && !b.disabled) mudarMarca({ [campo]: b.dataset.v }); };
  }
}

// ------------------------------------------------------------------ camadas e cobertura retrátil
// (usuário, 26/10: "essa imagem interagir com as camadas, poder abrir a quadra, colocar e tirar a lona") — gravadas na cena:
// a imagem salva sai como está na tela

// Sem cena (antes da foto), as camadas ligam e desligam no 3D do mesmo jeito (usuário, 05/11): ficam lembradas por projeto
// neste navegador e a cena nova começa com elas.
const CHAVE_SOLTAS = 'cena.camadas.' + PROJETO;
let soltas = [];
try { soltas = JSON.parse(localStorage.getItem(CHAVE_SOLTAS) || '[]'); if (!Array.isArray(soltas)) soltas = []; } catch (e) { soltas = []; }
const desligadasAgora = () => (cena ? cena.desligadas || [] : soltas);

function desenharCamadas() {
  if (!visor) return;
  arrumarPainel();                                          // com a cena, no lugar de sempre; sem ela, logo abaixo da lista
  const desl = new Set(desligadasAgora()), cams = visor.cabecalho.camadas || [];
  const linha = (chave, nome, cor, ligada) => `<label><input type="checkbox" data-chave="${esc(chave)}" ${ligada ? 'checked' : ''}>
    ${cor ? `<i style="background:${esc(cor)}"></i>` : ''}<span>${esc(nome)}</span></label>`;
  let html = '';
  if (sistemas.length > 1) html += '<div class="grupo">Sistema</div>' + sistemas.map(s => linha('sistema:' + s.chave, s.nome, s.cor, !desl.has('sistema:' + s.chave))).join('');
  html += '<div class="grupo">Camadas</div>' + cams.map(c => linha('camada:' + c.nome, c.nome, c.cor, !desl.has('camada:' + c.nome))).join('');
  $('#camadas').innerHTML = html;
  aplicarCamadas();
}

function aplicarCamadas() {
  const desl = new Set(desligadasAgora());
  resumirPainel();
  (visor.cabecalho.camadas || []).forEach((c, i) => {
    const ligada = !desl.has('camada:' + c.nome);
    if ((visor.visivelCamada[i] !== false) !== ligada) visor.mostrarCamada(i, ligada);
  });
  for (const s of sistemas) visor.ocultarSistema(s.ids, desl.has('sistema:' + s.chave));
  if (modo === 'foto' && visor.piso) visor.piso.visible = false;
  visor._sombraSuja = true;
  visor.pedirQuadro();
}

async function coberturaRetratil() {
  let pj = {};
  try { const j = await (await fetch(`/api/projetos/${encodeURIComponent(PROJETO)}`, { cache: 'no-store' })).json(); pj = j.projeto || j; }
  catch (e) { return; }
  if (!((pj.analise_parametros || {}).cobertura_movel || pj.cobertura_movel_vista)) return;
  situacaoProjeto = pj.cobertura_movel_vista || null;
  $('#cobertura').hidden = false;
  for (const b of document.querySelectorAll('#cobertura button')) {
    b.onclick = async () => {
      if (!cena || b.dataset.situacao === (situacaoAberta || situacaoProjeto)) return;
      aviso('Abrindo a cobertura ' + b.textContent.toLowerCase() + '…');
      await gravar({ situacao: b.dataset.situacao });
      location.href = `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(cena.id)}`;
    };
  }
}

function marcarSituacao() {
  const atual = situacaoAberta || situacaoProjeto;
  for (const b of document.querySelectorAll('#cobertura button')) b.classList.toggle('ligado', b.dataset.situacao === atual);
}

// ------------------------------------------------------------------ as duas vistas

/** O retângulo da foto no palco (contida, no meio). */
function retanguloFoto() {
  const W = palco.clientWidth, H = palco.clientHeight, [fw, fh] = cena ? cena.px : [W, H];
  const s = Math.min(W / fw, H / fh), w = Math.round(fw * s), h = Math.round(fh * s);
  return { x: Math.round((W - w) / 2), y: Math.round((H - h) / 2), w, h };
}

function posicionar(el, r) { Object.assign(el.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' }); }

function mostrarModo(m) {
  if (modo === '3d' && m === 'foto' && visor) camera3d = { pos: visor.camera.position.clone(), q: visor.camera.quaternion.clone(),
                                                          fov: visor.camera.fov, alvo: visor.controles.target.clone() };
  modo = m;
  document.body.classList.toggle('modo-3d', m === '3d');
  $('#ver').textContent = m === '3d' ? 'Ver a foto' : 'Ver o 3D';
  $('#ver').disabled = !ehFoto();
  if (!visor) return;
  if (m === 'foto' && ehFoto()) {
    const r = retanguloFoto();
    posicionar(foto, r); posicionar(tela, r); posicionar(telaFina, r); posicionar(marcas, r); posicionar(svgFrente, r);
    visor.cena.background = null;
    if (visor.piso) visor.piso.visible = false;
    if (terreno && terreno.grupo) terreno.grupo.visible = false;
    visor.controles.enabled = false;
    tela.style.pointerEvents = 'none';
    tela.style.opacity = String(cena.opacidade ?? 1);
    tela.style.visibility = cena.camera ? 'visible' : 'hidden';   // antes do encaixe, o 3D não tem onde ficar na foto
    visor.redimensionar();
    atualizarChaoSombra();
    aplicarCamera();
  } else {
    const r = { x: 0, y: 0, w: palco.clientWidth, h: palco.clientHeight };
    posicionar(tela, r); posicionar(marcas, r);
    visor.definirTema(escuro());                      // o fundo e o piso de volta
    if (visor.piso) visor.piso.visible = true;
    if (terreno && terreno.grupo) terreno.grupo.visible = true;
    visor.controles.enabled = true;
    tela.style.pointerEvents = 'auto';
    tela.style.opacity = '1';
    tela.style.visibility = 'visible';
    visor.redimensionar();
    atualizarChaoSombra();
    if (eh3d()) aplicarFundo();                             // a cena do 3D: a câmera é a dela (aplicarVistaDaCena)
    else if (camera3d) {
      visor.camera.position.copy(camera3d.pos); visor.camera.quaternion.copy(camera3d.q); visor.camera.fov = camera3d.fov;
      visor.controles.target.copy(camera3d.alvo); visor.camera.updateProjectionMatrix();
    } else visor.enquadrar('iso');
    visor.pedirQuadro();
  }
  ajustarQuadro();
  desenharFrenteSvg();
  desenharPreviaMarca();
}

/** A câmera da cena no visor (na vista da foto): a posição e o giro gravados (mm do projeto), o rolar e a lente. */
function aplicarCamera() {
  if (!visor || !ehFoto() || !cena.camera || modo !== 'foto') { atualizarFaixas(); if (visor) atualizarParedes(); return; }
  const o = visor.cabecalho.origem, c = cena.camera;
  visor.camera.position.set(c.posicao[0] - o[0], c.posicao[1] - o[1], c.posicao[2] - o[2]);
  giroBase = new THREE.Quaternion(...c.giro);
  visor.camera.quaternion.copy(giroBase).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rolar * Math.PI / 180));
  visor.camera.fov = c.fov;
  const dist = visor.camera.position.distanceTo(visor._esferaModelo.center);
  visor.camera.near = Math.max(10, dist / 5000);
  visor.camera.far = Math.max(1e6, dist * 20);
  visor.camera.updateProjectionMatrix();
  visor.camera.updateMatrixWorld();
  visor.pedirQuadro();                       // a sombra não depende da câmera (recorteDaCena): não se refaz a cada quadro
  atualizarFaixas();
  atualizarParedes();                        // as paredes do que fica na frente seguem a câmera
}

function atualizarFaixas() {
  const c = ehFoto() && cena.camera;
  $('#lente').disabled = $('#rolar').disabled = !c;
  if (c) { $('#lente').value = c.fov; $('#lente-val').textContent = nf(c.fov, 1) + '°'; }
  else $('#lente-val').textContent = '—';
  $('#rolar').value = rolar; $('#rolar-val').textContent = nf(rolar, 1) + '°';
  $('#opacidade-val').textContent = nf((+$('#opacidade').value) * 100) + ' %';
  $('#erro').textContent = c && c.erro_px != null ? `encaixe com erro de ${nf(c.erro_px, 1)} px` : '';
}

// ------------------------------------------------------------------ os pares de pontos

function desenharPares() {
  const pares = (cena && cena.pares) || [];
  // cada ponto se refaz depois da cena montada (usuário, 26/10: "não consigo… excluir/editar os pontos de vínculo da imagem
  // com o 3D"): a foto de novo, o 3D de novo, ou apagar — e o encaixe se refaz
  $('#pares').innerHTML = pares.map((p, i) => `<div class="par${i === selecionado ? ' sel' : ''}" data-escolher="${i}"><b>${i + 1}</b>
      <span>${p.modelo ? '<em class="ok">foto · 3D ✓</em>' : '<em class="falta">falta o 3D</em>'}</span>
      <button type="button" data-acao="foto" data-i="${i}" title="Marcar de novo o ponto ${i + 1} na foto">foto</button>
      <button type="button" data-acao="3d" data-i="${i}" title="Marcar de novo o ponto ${i + 1} no 3D">3D</button>
      <button type="button" data-acao="apagar" data-i="${i}" title="Apagar o ponto ${i + 1}">✕</button></div>`).join('')
    || '<p class="dica">Nenhum ponto ainda.</p>';
  const completos = pares.filter(p => p.modelo).length;
  $('#encaixar').disabled = completos < 4;
  $('#encaixar').title = completos < 4 ? `faltam ${4 - completos} ponto(s) completos` : '';
}

/** Grava `campos` na cena. A cena da tela é a que vale: os campos entram nela antes de ir ao servidor, e a resposta só traz
 *  o que é do servidor (a hora) — uma resposta que chegasse depois de outra mudança na tela a desfazia (27/10: o sol
 *  mexido logo depois de um Ctrl+Z voltava ao de antes). */
async function gravar(campos) {
  const id = cena.id;
  Object.assign(cena, JSON.parse(JSON.stringify(campos)));
  const r = await pedir(`${API}/${encodeURIComponent(id)}`, campos);
  if (cena && cena.id === id) cena.alterada = r.alterada;
  if (eh3d() && Object.keys(campos).some(k => k !== 'nome')) agendarMiniatura();   // a miniatura acompanha a cena
  desenharPares();
  atualizarFaixas();
  $('#salvar-cena').disabled = !cena.camera;
}

// ------------------------------------------------------------------ o sol da cena
// (usuário, 27/10: "poderia ter as opções de mudar a posição das sombras aqui na composição da cena"): os mesmos controles
// do modo ver e do celular (sol.js), gravados na cena — cada foto tem a hora dela

let tempoSol = 0;
const CHAO_PADRAO = 0.5;
// Sem cena (antes da foto), o sol mexe no 3D da tela do mesmo jeito (usuário, 05/11: "não consigo mexer no sol da cena" —
// na tela sem cena o sol nem aparecia, e o mudarSol saía calado): lembrado por projeto e a cena nova começa com ele.
const CHAVE_SOL_SOLTO = 'cena.sol.' + PROJETO;
let solSolto = null;
try { solSolto = JSON.parse(localStorage.getItem(CHAVE_SOL_SOLTO) || 'null'); if (!solSolto || typeof solSolto !== 'object') solSolto = null; }
catch (e) { solSolto = null; }
function solDaCena() { return { ligado: true, ...SOL_PADRAO, chao: CHAO_PADRAO, ...((cena ? cena.sol : solSolto) || {}) }; }

/** O sol e as camadas valem com ou sem cena: sem ela, logo abaixo da lista das cenas; com ela, no lugar deles no corpo. */
function arrumarPainel() {
  if (eh3d()) { $('#lugar-sol-3d').append($('#sol-bloco')); $('#lugar-camadas-3d').append($('#camadas-caixa')); }
  else if (cena) { $('#lugar-sol').append($('#sol-bloco')); $('#lugar-camadas').append($('#camadas-caixa')); }
  else { $('#corpo3d').before($('#sol-bloco')); $('#corpo3d').before($('#camadas-caixa')); }
}

function mostrarSol() {
  const s = solDaCena();
  arrumarPainel();
  $('#sol').checked = s.ligado;
  $('#sol-caixa').hidden = !s.ligado;
  $('#sol-caixa').innerHTML = controlesDoSol(s) +
    `<label class="faixa so-cena">Sombra no chão <input type="range" id="sombra-chao" min="0" max="1" step="0.05" value="${s.chao}">
      <span id="sombra-chao-val">${nf(s.chao * 100)} %</span></label>
    <span class="info" title="A direção gira o sol em volta da obra; a altura vai do nascer (baixo, sombras compridas) ao meio-dia (alto).${ehFoto() ? ' A sombra no chão cai no plano dos pontos do chão (a quadra); 0 % a desliga.' : ''}">ⓘ como o sol funciona</span>`;
  for (const el of $('#sol-caixa').querySelectorAll('.so-cena')) el.hidden = !ehFoto();   // a sombra no chão é a da foto
  // só a direção e a altura: o resto (a sombra no chão) pode ter mudado depois de os controles nascerem
  ligarControlesDoSol($('#sol-caixa'), s, (novo) => { lembrar('sol'); mudarSol({ direcao: novo.direcao, altura: novo.altura, ligado: true }); });
  $('#sombra-chao').oninput = () => {
    lembrar('chao');
    $('#sombra-chao-val').textContent = nf(+$('#sombra-chao').value * 100) + ' %';
    mudarSol({ chao: +$('#sombra-chao').value });
  };
  aplicarSol();
}

function aplicarSol() {
  const s = solDaCena();
  resumirPainel();
  visor.ligarApresentacao(s.ligado, 4096);
  definirSol(visor, s);
  atualizarChaoSombra();
  visor.pedirQuadro();
}

// ------------------------------------------------------------------ a sombra no chão da foto
// (usuário, 27/10: "tem como fazer as sombras 'interagir' com o chão da quadra?"): um chão invisível no plano do chão da cena
// (o mesmo dos pontos marcados no chão) que só escurece onde cai a sombra da estrutura — a foto aparece por baixo. Só na
// vista da foto: no 3D o piso já recebe a sombra. Fica fora da raiz do modelo, então não faz sombra (_desenharSombra).

let chaoSombra = null;

function atualizarChaoSombra() {
  if (!visor || !visor._luz) return;
  if (!chaoSombra) {
    chaoSombra = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShaderMaterial({
      uniforms: { ...visor._luz, uForca: { value: CHAO_PADRAO } },
      vertexShader: `varying vec3 vMundo;
        void main() { vec4 m = modelMatrix * vec4(position, 1.0); vMundo = m.xyz; gl_Position = projectionMatrix * viewMatrix * m; }`,
      fragmentShader: `varying vec3 vMundo;
        uniform float uForca;
        ${SOMBRA_GLSL}
        void main() {
          if (uTemSombra < 0.5) discard;
          float a = (1.0 - luzDoSol(vMundo, vec3(0.0, 0.0, 1.0))) * uForca;
          if (a < 0.004) discard;
          gl_FragColor = vec4(0.0, 0.0, 0.0, a);
        }`,
      transparent: true, depthWrite: false }));
    chaoSombra.raycast = () => {};
    visor.cena.add(chaoSombra);
  }
  const cx = visor._caixaModelo, c = cx.getCenter(new THREE.Vector3()), lado = Math.max(cx.getSize(new THREE.Vector3()).length(), 10000) * 20;
  chaoSombra.position.set(c.x, c.y, zDoChao());
  chaoSombra.scale.set(lado, lado, 1);
  const s = solDaCena();
  chaoSombra.material.uniforms.uForca.value = s.chao;
  chaoSombra.visible = modo === 'foto' && ehFoto() && s.ligado && s.chao > 0;
  visor.pedirQuadro();
}

/** O recorte da sombra na cena: a obra inteira e o comprido da sombra do sol baixo (a do visor segue o alvo do girar,
 *  que na vista da foto não anda, e cortava a sombra comprida no chão). */
function recorteDaCena() {
  const cx = visor.caixaVisivel(), z0 = zDoChao();
  const raioObra = Math.max(cx.getSize(new THREE.Vector3()).length() / 2, 1000) * 1.15;
  const alt = Math.max(solDaCena().altura, 8) * Math.PI / 180;
  const raio = Math.min(raioObra + Math.max(cx.max.z - z0, 0) / Math.tan(alt), raioObra * 4);
  return { c: cx.getCenter(new THREE.Vector3()).setZ(z0), raio, raioObra: raio };
}

/** A sombra de um bloco da imagem (usuário, 27/10: "as sombras nessa imagem ficaram bastante pixelizadas, mesmo após a
 *  renderização"): a imagem da sombra inteira só para o que aparece no bloco — o chão e a obra que os raios da câmera
 *  pelo bloco alcançam —, na vista do sol. O recorte da cena inteira (a obra e a sombra comprida do sol baixo) passa de
 *  100 m: cada pixel da sombra com 3–5 cm, um degrau no chão perto da câmera; um bloco da frente pega poucos metros. */
const _luzBloco = new THREE.OrthographicCamera();
_luzBloco.up.set(0, 0, 1);
function recorteDoBloco() {
  const base = recorteDaCena(), cam = visor.camera, z0 = zDoChao();
  _luzBloco.position.copy(base.c).addScaledVector(visor._luz.uSol.value, base.raioObra * 2);
  _luzBloco.lookAt(base.c);
  _luzBloco.updateMatrixWorld();
  const cx = visor.caixaVisivel(), ray = new THREE.Raycaster(), N = 8, p = new THREE.Vector3();
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  const juntar = (q) => {
    p.copy(q).applyMatrix4(_luzBloco.matrixWorldInverse);
    x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y);
  };
  cam.updateMatrixWorld();
  for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
    ray.setFromCamera(new THREE.Vector2(-1 + 2 * i / N, -1 + 2 * j / N), cam);   // com o deslocamento do bloco
    const o = ray.ray.origin, d = ray.ray.direction;
    let tChao = Infinity;
    if (d.z < -1e-9) {
      tChao = (z0 - o.z) / d.z;
      const q = ray.ray.at(tChao, new THREE.Vector3());
      if (Math.hypot(q.x - base.c.x, q.y - base.c.y) <= base.raio) juntar(q);
    }
    let t0 = 0, t1 = tChao;                                 // o trecho do raio dentro da caixa da obra, até o chão
    for (const e of ['x', 'y', 'z']) {
      if (Math.abs(d[e]) < 1e-12) { if (o[e] < cx.min[e] || o[e] > cx.max[e]) t1 = -1; continue; }
      const a = (cx.min[e] - o[e]) / d[e], b = (cx.max[e] - o[e]) / d[e];
      t0 = Math.max(t0, Math.min(a, b)); t1 = Math.min(t1, Math.max(a, b));
    }
    if (t0 < t1 && Number.isFinite(t1)) { juntar(ray.ray.at(t0, new THREE.Vector3())); juntar(ray.ray.at(t1, new THREE.Vector3())); }
  }
  if (!(x1 > x0 && y1 > y0)) return base;                    // o bloco só de céu: a sombra de sempre
  const m = Math.max(x1 - x0, y1 - y0) * 0.04 + 50;
  const janela = { l: Math.max(-base.raio, x0 - m), r: Math.min(base.raio, x1 + m), b: Math.max(-base.raio, y0 - m), t: Math.min(base.raio, y1 + m) };
  if (!(janela.r > janela.l && janela.t > janela.b)) return base;
  return { ...base, janela };
}

function mudarSol(mud) {
  if (!cena) {                                              // antes da foto: só o 3D da tela (e a cena nova começa assim)
    solSolto = { ...solDaCena(), ...mud };
    try { localStorage.setItem(CHAVE_SOL_SOLTO, JSON.stringify(solSolto)); } catch (e) { /* sem o navegador lembrar */ }
    $('#sol-caixa').hidden = !solSolto.ligado;
    aplicarSol();
    return;
  }
  cena.sol = { ...solDaCena(), ...mud };
  $('#sol-caixa').hidden = !cena.sol.ligado;
  aplicarSol();
  clearTimeout(tempoSol);
  const sol = cena.sol;                                     // o valor de agora: até gravar, outra resposta pode trocar a cena
  tempoSol = setTimeout(() => gravar({ sol }).catch(e => aviso('O sol não foi gravado: ' + e.message)), 500);
}

// ------------------------------------------------------------------ desfazer e refazer
// (usuário, 27/10: "mexi na posição da lente sem querer, e o ctrl z não faz ela voltar para a posição anterior"): o retrato
// do que se mexe na cena (os pontos, a câmera com a lente e o rolar, a opacidade, as camadas, o sol) antes de cada mudança.
// Um gesto é um passo: arrastar uma faixa, as setas seguidas num ponto, arrastar o ponto. Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z)
// aqui, e as setas ↶ ↷ da barra de cima (barra_unica.js) chamam o mesmo

const desfeitos = [], refeitos = [];
let ultimaMudanca = { tipo: null, t: 0 };

// a cena do 3D (11/11): o retrato é a câmera, as camadas, o sol e o estilo/enquadramento
const CAMPOS_3D = ['camera', 'desligadas', 'sol', 'pintar', 'arestas', 'fundo', 'proporcao', 'marca', 'luzes', 'entorno', 'figuras'];

function retrato() {
  if (eh3d()) return JSON.parse(JSON.stringify(Object.fromEntries(CAMPOS_3D.map(k => [k, cena[k] ?? null]))));
  const r = JSON.parse(JSON.stringify({ pares: cena.pares || [], camera: cena.camera || null, opacidade: cena.opacidade ?? 1,
                                        desligadas: cena.desligadas || [], sol: cena.sol || null, frente: cena.frente || [],
                                        marca: cena.marca || null }));
  if (r.camera && rolar && giroBase)                        // o rolar ainda fora do giro gravado
    r.camera.giro = giroBase.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rolar * Math.PI / 180)).toArray();
  return r;
}

/** Antes de mudar a cena. `tipo` junta o mesmo gesto num passo só (o mesmo tipo com menos de 1,5 s entre um e outro). */
function lembrar(tipo = null) {
  if (!cena) return;
  const agora = performance.now(), mesmo = tipo && tipo === ultimaMudanca.tipo && agora - ultimaMudanca.t < 1500;
  ultimaMudanca = { tipo, t: agora };
  if (mesmo) return;
  desfeitos.push(retrato());
  if (desfeitos.length > 100) desfeitos.shift();
  refeitos.length = 0;
}

async function voltarA(de, para, texto) {
  if (!cena) return;
  if (!de.length) { aviso(texto === 'Desfeito' ? 'Nada para desfazer.' : 'Nada para refazer.'); return; }
  cancelar();
  [tempoAjuste, tempoSol, tempoLente, tempoOpac, tempoCamadas, tempoCobre, tempo3d].forEach(clearTimeout);
  para.push(retrato());
  const r = de.pop();
  ultimaMudanca = { tipo: null, t: 0 };
  if (eh3d()) {
    const campos = Object.fromEntries(Object.entries(r).filter(([, v]) => v !== null));
    Object.assign(cena, r);
    for (const k of Object.keys(r)) if (r[k] === null) delete cena[k];
    aplicarVistaDaCena();
    aplicarEstilo3d();
    desenharCamadas();
    mostrarSol();
    mostrarPainel3d();
    mostrarMarca();
    try { await gravar({ ...campos, marca: r.marca, luzes: r.luzes, entorno: r.entorno }); agendarMiniatura(); aviso(texto + '.'); }
    catch (e) { aviso(texto + ' na tela, mas não gravado: ' + e.message); }
    return;
  }
  Object.assign(cena, r);
  if (!r.sol) delete cena.sol;
  if (!r.marca) delete cena.marca;
  rolar = 0;
  if (selecionado !== null && selecionado >= cena.pares.length) selecionado = null;
  $('#opacidade').value = cena.opacidade;
  desenharPares();
  desenharCamadas();
  mostrarSol();
  if (contornoSel !== null && contornoSel >= cena.frente.length) contornoSel = null;
  desenharContornos();
  mostrarModo(modo);
  mostrarMarca();
  try {
    await gravar({ pares: cena.pares, camera: cena.camera, opacidade: cena.opacidade, desligadas: cena.desligadas,
                   sol: r.sol || { ligado: true, ...SOL_PADRAO }, frente: cena.frente, marca: r.marca });
    aplicarCamera();
    aviso(texto + '.');
  } catch (e) { aviso(texto + ' na tela, mas não gravado: ' + e.message); }
}

const desfazer = () => voltarA(desfeitos, refeitos, 'Desfeito');
const refazer = () => voltarA(refeitos, desfeitos, 'Refeito');

// ------------------------------------------------------------------ a cena pronta
// (usuário, 27/10: "crie a opção salvar cena após a conclusão, para não ficar aparecendo essas bolinhas na tela, caso seja
// necessário editar ter um para editar cena, daí elas reaparecem"): pronta, a cena fica só a foto com o 3D — sem as marcas,
// sem os pontos e o encaixe no painel; a opacidade, o sol, as camadas e a imagem continuam

function mostrarConcluida() {
  const pronta = !!(cena && cena.concluida);
  document.body.classList.toggle('concluida', pronta);
  $('#edicao').hidden = pronta;
  $('#pronta').hidden = !pronta;
  $('#salvar-cena').disabled = !(cena && cena.camera);
  $('#salvar-cena').title = cena && cena.camera ? 'Terminar o encaixe: os pontos saem da tela (Editar cena traz de volta)'
    : 'Encaixe a cena antes de salvar (4 pontos ou mais)';
  if (pronta) { cancelar(); arrasto = null; selecionado = null; if (modo !== 'foto') mostrarModo('foto'); }
}

async function concluir(pronta) {
  if (!cena) return;
  if (pronta && !cena.camera) { aviso('Encaixe a cena antes de salvar (4 pontos ou mais).'); return; }
  clearTimeout(tempoAjuste); clearTimeout(tempoSol);        // o ajuste fino e o sol ainda por gravar vão junto
  const campos = { concluida: pronta };
  if (pronta) Object.assign(campos, { pares: cena.pares, camera: cena.camera });
  if (cena.sol) campos.sol = cena.sol;
  await gravar(campos);
  mostrarConcluida();
  aviso(pronta ? 'Cena salva: os pontos saíram da tela. Para mexer neles, Editar cena.' : 'Editando: os pontos de volta na foto.');
}

function comecarPonto() {
  if (!ehFoto()) return;
  marcando = { etapa: 'foto' };
  mostrarModo('foto');
  aviso('Clique o ponto na foto (Esc cancela).');
}

function marcarNo3d(i) {
  marcando = { etapa: '3d', i };
  document.body.classList.add('marcando-3d');
  mostrarModo('3d');
  aviso(`Agora clique o mesmo ponto ${i + 1} no 3D: uma peça ou o chão (gire com o botão esquerdo arrastando; Esc cancela).`);
}

function cancelar() {
  marcando = null;
  if (desenho) pararContorno();
  document.body.classList.remove('marcando-3d');
  aviso('');
}

/** O ponto do 3D sob o clique (mm do projeto): a peça, ou o chão da imagem do terreno (sem terreno, o pé do modelo). */
/** O chão da cena (coordenadas do visor): o da imagem do terreno, ou o pé do modelo. Os pontos do chão e a sombra no chão. */
function zDoChao() {
  const o = visor.cabecalho.origem;
  return terreno && Number.isFinite(terreno.zChao) && terreno.malha ? terreno.zChao - o[2] : visor._caixaModelo.min.z;
}

function pontoDo3d(x, y) {
  const achado = visor.pontoEm(x, y);
  if (achado) return achado.ponto;
  const o = visor.cabecalho.origem, z = zDoChao();
  const ndc = new THREE.Vector2(x / tela.clientWidth * 2 - 1, -(y / tela.clientHeight) * 2 + 1);
  const raio = new THREE.Raycaster();
  visor.camera.updateMatrixWorld();
  raio.setFromCamera(ndc, visor.camera);
  const p = new THREE.Vector3();
  if (!raio.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), -z), p)) return null;
  return [p.x + o[0], p.y + o[1], p.z + o[2]];
}

// ------------------------------------------------------------------ o encaixe

async function fazerEncaixe() {
  const pares = cena.pares.filter(p => p.modelo);
  if (pares.length < 4) return;
  const o = visor.cabecalho.origem;
  const atual = cena.camera ? { posicao: new THREE.Vector3(cena.camera.posicao[0] - o[0], cena.camera.posicao[1] - o[1], cena.camera.posicao[2] - o[2]),
                                giro: new THREE.Quaternion(...cena.camera.giro), fov: cena.camera.fov } : null;
  const c = encaixar(pares.map(p => ({ u: p.foto[0], v: p.foto[1], X: [p.modelo[0] - o[0], p.modelo[1] - o[1], p.modelo[2] - o[2]] })),
                     cena.px[0], cena.px[1], atual);
  if (!c) return;
  rolar = 0;
  await gravar({ camera: { posicao: [c.posicao.x + o[0], c.posicao.y + o[1], c.posicao.z + o[2]], giro: c.giro.toArray(), fov: c.fov,
                           erro_px: c.erro_px } });
  if (marcando) { aplicarCamera(); return; }               // a pessoa já começou outro ponto: a vista fica onde está
  mostrarModo('foto');
  aviso(c.erro_px <= 15 ? `Encaixado: erro médio de ${nf(c.erro_px, 1)} px na foto.`
    : `Encaixado com erro de ${nf(c.erro_px, 0)} px: confira os pontos (um deles pode estar trocado) ou marque mais.`);
}

// ------------------------------------------------------------------ o ajuste fino de um ponto na foto
// (usuário, 26/10: "habilite um ajuste fino dos pontos, por ex. se quisesse movimentar esse segundo ponto um pouco para cima
// ou para o lado"): o ponto escolhido (clique na marca ou na linha dele) anda arrastado ou pelas setas (1 px da tela; Shift,
// 10), e o encaixe acompanha na hora (o rápido, a partir da câmera de agora); grava ao soltar e depois das setas

function escolherPonto(i) {
  selecionado = i;
  desenharPares();
  if (i !== null) aviso(`Ponto ${i + 1}: arraste na foto ou use as setas (Shift = 10×). Esc solta.`);
}

function encaixeRapido() {
  if (!cena || !cena.camera) return;
  const pares = cena.pares.filter(p => p.modelo);
  if (pares.length < 4) return;
  const o = visor.cabecalho.origem;
  const atual = { posicao: new THREE.Vector3(cena.camera.posicao[0] - o[0], cena.camera.posicao[1] - o[1], cena.camera.posicao[2] - o[2]),
                  giro: new THREE.Quaternion(...cena.camera.giro), fov: cena.camera.fov };
  const c = encaixar(pares.map(p => ({ u: p.foto[0], v: p.foto[1], X: [p.modelo[0] - o[0], p.modelo[1] - o[1], p.modelo[2] - o[2]] })),
                     cena.px[0], cena.px[1], atual, { rapido: true });
  if (!c) return;
  cena.camera = { posicao: [c.posicao.x + o[0], c.posicao.y + o[1], c.posicao.z + o[2]], giro: c.giro.toArray(), fov: c.fov, erro_px: c.erro_px };
  rolar = 0;
  aplicarCamera();
}

function moverPonto(i, u, v) {
  lembrar('ponto' + i);
  cena.pares[i] = { ...cena.pares[i], foto: [Math.min(1, Math.max(0, u)), Math.min(1, Math.max(0, v))] };
  cancelAnimationFrame(quadroAjuste);
  quadroAjuste = requestAnimationFrame(encaixeRapido);
  clearTimeout(tempoAjuste);
}

function gravarAjuste(espera = 0) {
  clearTimeout(tempoAjuste);
  tempoAjuste = setTimeout(async () => {
    try { await gravar({ pares: cena.pares, camera: cena.camera }); }
    catch (e) { aviso('O ajuste não foi gravado: ' + e.message); }
  }, espera);
}

/** O ponto da foto mais perto do (x, y) da tela (px dentro da foto), até 16 px; ou null. */
function pontoPerto(x, y) {
  const w = marcas.clientWidth, h = marcas.clientHeight;
  let melhor = null, dist = 16;
  (cena.pares || []).forEach((p, i) => { const d = Math.hypot(p.foto[0] * w - x, p.foto[1] * h - y); if (d < dist) { dist = d; melhor = i; } });
  return melhor;
}

/** Depois de mudar os pontos: o encaixe de novo com 4 ou mais completos; com menos, a câmera de antes fica (avisado). */
async function reencaixar(texto = '') {
  const completos = (cena.pares || []).filter(p => p.modelo).length;
  if (completos >= 4) { await fazerEncaixe(); if (texto) aviso(texto + ' ' + $('#aviso').textContent); }
  else { mostrarModo('foto'); aviso(`${texto} Com ${completos} ponto(s) completos o encaixe fica o de antes: marque ${4 - completos} para refazer.`.trim()); }
}

// ------------------------------------------------------------------ o que fica na frente da estrutura
// (usuário, 27/10: "nessa foto por exemplo a estrutura está atrás desse alambrado, como fazer para o sistema entender isso…
// apenas no renderizar para não consumir muito processamento"): o contorno clicado na foto vira uma parede de pé no 3D, na
// linha em que a borda de baixo dele toca o chão da cena (o mesmo dos pontos e da sombra no chão). A parede pinta a própria
// foto por cima do que está ATRÁS dela (o teste de profundidade): o que está na frente continua na frente. `cobre` é quanto
// da foto vai por cima — 1 a tela fechada, 0,7 a translúcida, 0,3 a malha. Só no Salvar imagem e no Renderizar; na tela,
// com "Ver na tela". Sem chão sob a borda de baixo (o contorno no céu), cobre tudo o que está dentro dele.

const COBERTURAS = [[1, 'Tela fechada'], [0.7, 'Tela translúcida'], [0.3, 'Malha / alambrado']];
let desenho = null, contornoSel = null, arrastoCanto = null, verFrente = false, paredes = [], texFoto = null, quadroParedes = 0;
let tempoCobre = 0;
const svgFrente = $('#frente-svg');

/** Os cantos da borda de baixo do contorno: os que não têm nada do contorno abaixo deles na foto. */
function bordaDeBaixo(pts) {
  const n = pts.length, base = [];
  for (let k = 0; k < n; k++) {
    const [u, v] = pts[k];
    let embaixo = false;
    for (let i = 0; i < n && !embaixo; i++) {
      const j = (i + 1) % n;
      if (i === k || j === k) continue;
      const a = pts[i], b = pts[j];
      if (Math.abs(a[0] - b[0]) < 1e-9) embaixo = Math.abs(a[0] - u) < 1e-9 && Math.max(a[1], b[1]) > v + 1e-6;
      else if (u >= Math.min(a[0], b[0]) && u <= Math.max(a[0], b[0])) embaixo = a[1] + (u - a[0]) * (b[1] - a[1]) / (b[0] - a[0]) > v + 1e-6;
    }
    if (!embaixo) base.push(k);
  }
  return base;
}

/** O raio da câmera da cena pelo ponto (u, v) da foto (a câmera sem o deslocamento dos blocos do render). */
function raioDaFoto(u, v) {
  const r = new THREE.Raycaster();
  r.setFromCamera(new THREE.Vector2(u * 2 - 1, 1 - v * 2), visor.camera);
  return r.ray;
}

/** A parede do contorno: as posições (coordenadas do visor) dos cantos, os triângulos e se cobre tudo (sem chão). */
function geometriaDoContorno(f) {
  const cam = visor.camera, pts = f.pontos, z0 = zDoChao();
  cam.updateMatrixWorld();
  const chao = new THREE.Plane(new THREE.Vector3(0, 0, 1), -z0), alcance = cam.far * 0.5;
  const pes = [];
  for (const k of bordaDeBaixo(pts).sort((a, b) => pts[a][0] - pts[b][0])) {
    const p = new THREE.Vector3(), ray = raioDaFoto(...pts[k]);
    if (ray.intersectPlane(chao, p) && p.distanceTo(ray.origin) < alcance) pes.push(p);
  }
  let plano = null;
  if (pes.length) {
    const a = pes[0], b = pes[pes.length - 1], d = new THREE.Vector3(b.x - a.x, b.y - a.y, 0);
    if (d.length() >= 200) plano = new THREE.Plane().setFromNormalAndCoplanarPoint(d.cross(new THREE.Vector3(0, 0, 1)).normalize(), a);
    else {                                                  // uma árvore, um poste: a parede de frente para a câmera
      const m = pes.reduce((s, p) => s.add(p), new THREE.Vector3()).divideScalar(pes.length);
      const n = new THREE.Vector3(m.x - cam.position.x, m.y - cam.position.y, 0);
      if (n.length() > 1) plano = new THREE.Plane().setFromNormalAndCoplanarPoint(n.normalize(), m);
    }
  }
  const pos = [];
  let tudo = !plano;
  if (plano) {
    for (const [u, v] of pts) {
      const p = new THREE.Vector3(), ray = raioDaFoto(u, v);
      if (!ray.intersectPlane(plano, p) || p.distanceTo(ray.origin) > alcance) { tudo = true; break; }
      pos.push(p);
    }
  }
  if (tudo) {                                               // logo na frente da câmera: cobre tudo o que está dentro
    pos.length = 0;
    for (const [u, v] of pts) { const ray = raioDaFoto(u, v); pos.push(ray.at(cam.near * 2, new THREE.Vector3())); }
  }
  const tri = THREE.ShapeUtils.triangulateShape(pts.map(([u, v]) => new THREE.Vector2(u, -v)), []);
  return { pos, tri, tudo };
}

const _db = new THREE.Vector2();
function materialDaParede(cobre) {
  return new THREE.ShaderMaterial({
    uniforms: { tFoto: { value: texFoto }, uCobre: { value: cobre }, uTela: { value: new THREE.Vector4() }, uBuf: { value: new THREE.Vector2() } },
    vertexShader: 'void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    // o pixel da foto inteira sob este pixel: uTela = a imagem inteira (largura, altura) e o canto do bloco (x, y de cima)
    fragmentShader: `uniform sampler2D tFoto; uniform float uCobre; uniform vec4 uTela; uniform vec2 uBuf;
      void main() {
        vec2 p = vec2(uTela.z + gl_FragCoord.x, uTela.w + uBuf.y - gl_FragCoord.y);
        gl_FragColor = vec4(texture2D(tFoto, vec2(p.x / uTela.x, 1.0 - p.y / uTela.y)).rgb, uCobre);
      }`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide });
}

function tirarParedes() {
  for (const m of paredes) { visor.cena.remove(m); m.geometry.dispose(); m.material.dispose(); }
  paredes = [];
}

/** As paredes no visor, pela câmera de agora (a vista da foto). Devolve quantas cobrem tudo (sem chão). */
function montarParedes() {
  tirarParedes();
  if (!visor || !cena || !cena.camera || !texFoto || modo !== 'foto') return 0;
  let semChao = 0;
  for (const [i, f] of (cena.frente || []).entries()) {
    const { pos, tri, tudo } = geometriaDoContorno(f);
    if (!tri.length) continue;
    semChao += tudo ? 1 : 0;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos.flatMap(p => [p.x, p.y, p.z]), 3));
    geo.setIndex(tri.flat());
    const m = new THREE.Mesh(geo, materialDaParede(f.cobre ?? 1));
    m.renderOrder = 10;                                     // depois da estrutura e da sombra no chão
    m.userData.contorno = i;
    m.frustumCulled = false;
    m.raycast = () => {};
    m.onBeforeRender = (renderer, _cena, camera) => {     // o bloco do render (setViewOffset) ou a tela inteira
      const u = m.material.uniforms, db = renderer.getDrawingBufferSize(_db), v = camera.view;
      if (v && v.enabled) { const k = db.x / v.width; u.uTela.value.set(v.fullWidth * k, v.fullHeight * k, v.offsetX * k, v.offsetY * k); }
      else u.uTela.value.set(db.x, db.y, 0, 0);
      u.uBuf.value.copy(db);
    };
    visor.cena.add(m);
    paredes.push(m);
  }
  visor.pedirQuadro();
  return semChao;
}

/** Na tela, só com "Ver na tela" (a imagem salva e o render sempre as montam). */
function atualizarParedes() {
  cancelAnimationFrame(quadroParedes);
  if (verFrente && modo === 'foto') montarParedes(); else if (paredes.length) { tirarParedes(); visor.pedirQuadro(); }
}

/** A foto como textura da parede. Por uma cópia num canvas: a <img> direto subia preta (o three lê o tamanho dela na tela,
 *  não o da foto, e o envio à placa falhava). */
function atualizarTexturaFoto() {
  if (texFoto) texFoto.dispose();
  texFoto = null;
  if (!visor || !foto.naturalWidth) return;
  const k = Math.min(1, Math.min(visor.renderer.capabilities.maxTextureSize, 8192) / Math.max(foto.naturalWidth, foto.naturalHeight));
  const cv = document.createElement('canvas');
  cv.width = Math.round(foto.naturalWidth * k); cv.height = Math.round(foto.naturalHeight * k);
  cv.getContext('2d').drawImage(foto, 0, 0, cv.width, cv.height);
  texFoto = new THREE.CanvasTexture(cv);
  texFoto.minFilter = texFoto.magFilter = THREE.LinearFilter;
  texFoto.generateMipmaps = false;
  texFoto.needsUpdate = true;
}

function desenharContornos() {
  const lista = (cena && cena.frente) || [];
  const semChao = cena && cena.camera && visor && modo === 'foto'
    ? lista.map(f => f.pontos.length >= 3 && geometriaDoContorno(f).tudo) : [];
  $('#contornos').innerHTML = lista.map((f, i) => {
    // os tipos são atalhos; a faixa dá o meio-termo (usuário, 27/10: "preciso que tenha um controle do nível de opacidade
    // do fundo/frente")
    const tipo = COBERTURAS.find(c => Math.abs(c[0] - f.cobre) < 0.001);
    return `<div class="contorno${i === contornoSel ? ' sel' : ''}" data-contorno="${i}"><b>${i + 1}</b>
      <select data-i="${i}" aria-label="O que é o contorno ${i + 1}">${tipo ? '' : '<option value="" selected>Sob medida</option>'}${COBERTURAS.map(c => `<option value="${c[0]}" ${c === tipo ? 'selected' : ''}>${c[1]}</option>`).join('')}</select>
      <button type="button" data-apagar="${i}" title="Apagar o contorno ${i + 1}">✕</button></div>
      <label class="faixa" title="Quanto a foto (o alambrado) cobre a estrutura atrás dele: 100 % some, 5 % quase não muda">Opacidade da frente
        <input type="range" data-cobre="${i}" min="0.05" max="1" step="0.05" value="${f.cobre}"><span>${nf(f.cobre * 100)} %</span></label>
      ${semChao[i] ? '<div class="aviso-contorno">A borda de baixo não chega no chão: cobre tudo o que está dentro do contorno.</div>' : ''}`;
  }).join('');
  $('#frente-ver').checked = verFrente;
  desenharFrenteSvg();
}

function desenharFrenteSvg() {
  const w = marcas.clientWidth, h = marcas.clientHeight;
  const mostrar = modo === 'foto' && cena && (desenho || !verFrente);
  if (!mostrar) { svgFrente.innerHTML = ''; return; }
  svgFrente.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const xy = p => `${(p[0] * w).toFixed(1)},${(p[1] * h).toFixed(1)}`;
  let html = ((cena && cena.frente) || []).map((f, i) => {
    const c = f.pontos.map(p => [p[0] * w, p[1] * h]), meio = c.reduce((s, p) => [s[0] + p[0] / c.length, s[1] + p[1] / c.length], [0, 0]);
    return `<polygon class="${i === contornoSel ? 'sel' : ''}" points="${f.pontos.map(xy).join(' ')}"/>` +
      f.pontos.map((p, k) => `<circle data-c="${i}" data-k="${k}" cx="${(p[0] * w).toFixed(1)}" cy="${(p[1] * h).toFixed(1)}" r="5"/>`).join('') +
      `<circle cx="${meio[0].toFixed(1)}" cy="${meio[1].toFixed(1)}" r="9" style="pointer-events:none;fill:#ffd400"/><text x="${meio[0].toFixed(1)}" y="${meio[1].toFixed(1)}">${i + 1}</text>`;
  }).join('');
  if (desenho && desenho.length) {
    html += `<polyline points="${desenho.map(xy).join(' ')}"/>` +
      desenho.map((p, k) => `<circle class="${k === 0 ? 'primeiro' : ''}" cx="${(p[0] * w).toFixed(1)}" cy="${(p[1] * h).toFixed(1)}" r="${k === 0 ? 7 : 4}" style="pointer-events:none"/>`).join('');
  }
  svgFrente.innerHTML = html;
}

function comecarContorno() {
  if (!cena) return;
  if (!cena.camera) { aviso('Encaixe a cena antes: o contorno precisa saber onde fica o chão.'); return; }
  cancelar();
  mostrarModo('foto');
  desenho = [];
  document.body.classList.add('desenhando');
  desenharFrenteSvg();
  aviso('Clique os cantos do contorno na foto, com a borda de baixo no chão. Clique no primeiro ponto ou Enter fecha; Backspace volta um; Esc cancela.');
}

function pararContorno() {
  desenho = null;
  document.body.classList.remove('desenhando');
  desenharFrenteSvg();
}

async function fecharContorno() {
  if (!desenho) return;
  if (desenho.length < 3) { aviso('O contorno precisa de 3 pontos ou mais.'); return; }
  lembrar();
  const frente = ((cena.frente || []).concat([{ pontos: desenho, cobre: 0.7 }]));
  pararContorno();
  contornoSel = frente.length - 1;
  try {
    await gravar({ frente });
    aviso(`Contorno ${frente.length} gravado (tela translúcida: troque na lista). Ele vale na imagem salva e no render; "Ver na tela" mostra como fica.`);
  } catch (e) { aviso('O contorno não foi gravado: ' + e.message); }
  desenharContornos();
  atualizarParedes();
}

/** Grava a lista de contornos de agora (depois de mexer num canto, no tipo, ou apagar). */
async function gravarFrente(texto) {
  desenharContornos();
  atualizarParedes();
  try { await gravar({ frente: cena.frente || [] }); if (texto) aviso(texto); }
  catch (e) { aviso('Os contornos não foram gravados: ' + e.message); }
}

function ligarFrente() {
  $('#novo-contorno').onclick = comecarContorno;
  $('#frente-ver').onchange = () => { verFrente = $('#frente-ver').checked; desenharFrenteSvg(); atualizarParedes(); };
  // a faixa: a parede na tela muda junto (com "Ver na tela"); grava ao parar
  $('#contornos').addEventListener('input', (e) => {
    const f = e.target.closest('input[data-cobre]');
    if (!f || !cena) return;
    const i = +f.dataset.cobre, v = +f.value;
    lembrar('cobre' + i);
    cena.frente[i].cobre = v;
    f.nextElementSibling.textContent = nf(v * 100) + ' %';
    for (const m of paredes) if (m.userData.contorno === i) m.material.uniforms.uCobre.value = v;
    visor.pedirQuadro();
    const frente = JSON.parse(JSON.stringify(cena.frente));  // o valor de agora (como o sol)
    clearTimeout(tempoCobre);
    tempoCobre = setTimeout(() => gravar({ frente }).catch(err => aviso('Os contornos não foram gravados: ' + err.message)), 500);
  });
  $('#contornos').onchange = (e) => {
    if (e.target.closest('input[data-cobre]')) { desenharContornos(); return; }    // o tipo acompanha a faixa
    const s = e.target.closest('select[data-i]');
    if (!s || !cena || s.value === '') return;
    lembrar();
    cena.frente[+s.dataset.i].cobre = +s.value;
    gravarFrente();
  };
  $('#contornos').onclick = (e) => {
    const b = e.target.closest('button[data-apagar]');
    if (b && cena) {
      lembrar();
      cena.frente.splice(+b.dataset.apagar, 1);
      contornoSel = null;
      gravarFrente(`Contorno ${+b.dataset.apagar + 1} apagado.`);
      return;
    }
    const l = e.target.closest('[data-contorno]');
    if (l && !e.target.closest('select')) { contornoSel = +l.dataset.contorno === contornoSel ? null : +l.dataset.contorno; desenharContornos(); }
  };
  // desenhando: cada clique, um canto; perto do primeiro, fecha
  svgFrente.addEventListener('click', (e) => {
    if (!desenho) return;
    const r = svgFrente.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    if (desenho.length >= 3 && Math.hypot(desenho[0][0] * r.width - x, desenho[0][1] * r.height - y) < 10) { fecharContorno(); return; }
    desenho.push([Math.min(1, Math.max(0, x / r.width)), Math.min(1, Math.max(0, y / r.height))]);
    desenharFrenteSvg();
  });
  // um canto pego e arrastado
  svgFrente.addEventListener('pointerdown', (e) => {
    const c = e.target.closest('circle[data-c]');
    if (!c || desenho || e.button !== 0 || !cena) return;
    arrastoCanto = { c: +c.dataset.c, k: +c.dataset.k };
    contornoSel = arrastoCanto.c;
    e.preventDefault();
  });
  addEventListener('pointermove', (e) => {
    if (!arrastoCanto) return;
    const r = svgFrente.getBoundingClientRect();
    lembrar(`canto${arrastoCanto.c}-${arrastoCanto.k}`);
    cena.frente[arrastoCanto.c].pontos[arrastoCanto.k] = [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
                                                          Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
    desenharFrenteSvg();
    if (verFrente) { cancelAnimationFrame(quadroParedes); quadroParedes = requestAnimationFrame(montarParedes); }
  });
  addEventListener('pointerup', () => { if (!arrastoCanto) return; arrastoCanto = null; gravarFrente(); });
}

// ------------------------------------------------------------------ a imagem pronta

/** A foto com o 3D por cima, num canvas de w × h. O 3D sai em blocos (camera.setViewOffset): qualquer tamanho, sem passar
 *  do que a placa de vídeo desenha de uma vez; cada bloco `ss` vezes maior e reduzido (supersampling — as terças finas
 *  sem serrilhado nem moiré). `aoBloco(i, n)` depois de cada bloco. */
async function montarImagem(w, h, ss = 1, aoBloco = null, { comFoto = true, frente = true, bloco = 2048, antes = null } = {}) {
  const saida = document.createElement('canvas');
  saida.width = w; saida.height = h;
  const g = saida.getContext('2d');
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  if (comFoto) g.drawImage(foto, 0, 0, w, h);
  if (antes) antes(g);                                      // o fundo da cena do 3D (o céu), antes do 3D
  const r = visor.renderer, dpr = r.getPixelRatio(), cam = visor.camera, gl = r.getContext();
  const lado = Math.min(bloco, gl.getParameter(gl.MAX_RENDERBUFFER_SIZE), r.capabilities.maxTextureSize);
  const B = Math.max(128, Math.floor(lado / ss)), blocos = [];
  for (let y = 0; y < h; y += B) for (let x = 0; x < w; x += B) blocos.push([x, y, Math.min(B, w - x), Math.min(B, h - y)]);
  r.setPixelRatio(1);
  cam.aspect = w / h;
  cam.updateProjectionMatrix();
  if (frente) montarParedes();                              // o que fica na frente: sempre na imagem (aplicarCamera devolve a tela)
  g.globalAlpha = comFoto ? +$('#opacidade').value : 1;
  visor._recorteSombra = recorteDoBloco;                    // a sombra refeita para cada bloco, só com o que ele mostra
  // o afastamento da sombra ao longo da normal (contra as manchas) igual em todos os blocos, o da cena inteira: o de cada
  // janela deslocava a borda da sombra de um jeito por bloco, e ela fazia dente na emenda
  const desloc = 1.5 * 2 * recorteDaCena().raio * visor._luz.uTexel.value;
  try {
    for (let k = 0; k < blocos.length; k++) {
      const [x, y, bw, bh] = blocos[k];
      r.setSize(bw * ss, bh * ss, false);
      cam.setViewOffset(w * ss, h * ss, x * ss, y * ss, bw * ss, bh * ss);
      if (visor.apresentacao) { visor._desenharSombra(); visor._luz.uDesloc.value = desloc; }
      r.render(visor.cena, cam);
      g.drawImage(r.domElement, 0, 0, bw * ss, bh * ss, x, y, bw, bh);     // na mesma tarefa: o quadro ainda está lá
      if (aoBloco) await aoBloco(k + 1, blocos.length);
    }
  } finally {
    visor._recorteSombra = recorteDaCena;
    if (visor.apresentacao) visor._sombraSuja = true;       // a da tela de volta (a cena inteira)
    cam.clearViewOffset();
    r.setPixelRatio(dpr);
    visor.redimensionar();
    aplicarCamera();
  }
  return saida;
}

// ------------------------------------------------------------------ a tela parada, como o render
// (usuário, 28/10, print da tela da cena: "a sombra continua pixelizada"): o render já saía limpo, a tela não — ela desenha
// a cena de uma vez, com a imagem da sombra da cena inteira. Parada a câmera (meio segundo sem pedir quadro), a tela é
// refeita como o render, em blocos de 256 px com a sombra de cada um, num canvas por cima (#tela-fina); qualquer quadro
// pedido (a lente, o sol, as camadas, o encaixe, o tamanho da janela) a tira na hora, e o 3D de sempre volta até parar.

const telaFina = document.createElement('canvas');
telaFina.id = 'tela-fina';
let tempoFino = 0, refinando = false;

function esconderFino() {
  clearTimeout(tempoFino);
  if (!telaFina.hidden) {
    telaFina.hidden = true;
    if (modo === 'foto' && cena) tela.style.visibility = cena.camera && !renderizando ? 'visible' : 'hidden';
  }
}

/** O visor pediu um quadro: a tela mudou. Os quadros pedidos pelo próprio refino não contam. */
function aoPedirQuadro() {
  if (refinando) return;
  esconderFino();
  tempoFino = setTimeout(refinarTela, 500);
}

async function refinarTela() {
  if (modo !== 'foto' || !cena || !cena.camera || !visor.apresentacao || renderizando || arrasto || arrastoCanto || desenho) return;
  if (document.hidden) { tempoFino = setTimeout(refinarTela, 1000); return; }
  refinando = true;
  try {
    const camada = await montarImagem(tela.width, tela.height, 1, null, { comFoto: false, frente: verFrente, bloco: Math.round(256 * visor.renderer.getPixelRatio()) });
    telaFina.width = camada.width; telaFina.height = camada.height;
    telaFina.getContext('2d').drawImage(camada, 0, 0);
    telaFina.style.opacity = tela.style.opacity;
    telaFina.hidden = false;
    tela.style.visibility = 'hidden';                       // a de sempre por baixo dobraria a sombra no chão
  } catch (e) { console.warn('refino da tela', e); }
  finally { refinando = false; }
}

async function enviarImagem(saida, nome, tipo, qualidade) {
  const blob = await new Promise(res => saida.toBlob(res, tipo, qualidade));
  const j = await pedir(`${API}/${encodeURIComponent(cena.id)}/imagem`, undefined, { dados: blob, nome });
  window.ultimaImagemCena = j;
  return j;
}

async function salvarImagem() {
  if (eh3d()) {                                             // a cena do 3D como está: Full HD, sem o refino
    const [w, h] = tamanho3d(1920), png = true;
    try {
      const saida = await imagemDaCena3d(w, h, 1);
      aviso('Salvando a imagem…');
      const j = await enviarImagem(saida, png ? 'cena.png' : 'cena.jpg', png ? 'image/png' : 'image/jpeg', 0.92);
      avisoComPasta(`Imagem salva na pasta cenas da obra: ${j.nome} (${nf(w)} × ${nf(h)} px).`, j.nome);
      atualizarCartoes();
    } catch (e) { aviso('A imagem não foi salva: ' + e.message); }
    return;
  }
  if (!cena || !cena.camera) { aviso('Encaixe a cena antes de salvar a imagem.'); return; }
  mostrarModo('foto');
  const k = Math.min(1, 4096 / Math.max(...cena.px)), w = Math.round(cena.px[0] * k), h = Math.round(cena.px[1] * k);
  const saida = await montarImagem(w, h);
  await marcaNaImagem(saida);
  aviso('Salvando a imagem…');
  try {
    const j = await enviarImagem(saida, 'cena.png', 'image/png');
    avisoComPasta(`Imagem salva na pasta cenas da obra: ${j.nome} (${w} × ${h} px).`, j.nome);
    atualizarCartoes();
  } catch (e) { aviso('A imagem não foi salva: ' + e.message); }
}

// ------------------------------------------------------------------ renderizar
// (usuário, 27/10: "ficou excelente, porém a resolução ainda é meio baixa… depois de definida a cena com as sombras etc.
// ter uma opção para 'renderizar' a imagem"): a foto do WhatsApp vem com 1.200 × 1.600 e a imagem salva tinha o tamanho
// dela — as terças de 1–2 px serrilhavam. O render sai 2×–4× maior que a foto (a foto ampliada suave; o 3D desenhado
// nesse tamanho, em blocos, com supersampling 2×) e a sombra em 8192 em vez de 4096. JPEG 95 % (o PNG de 5.000 px passa
// de 40 MB).

const LADO_RENDER_MAX = 8000;                               // o lado maior da imagem renderizada (memória do navegador)
let renderizando = false;

/** A cena do 3D: o lado maior da imagem (Full HD, 4K, A3 a 300 dpi) na proporção do quadro. */
const LADOS_3D = [[1920, 'Full HD'], [3840, '4K'], [4961, 'A3 300 dpi']];
function tamanho3d(lado) {
  const p = PROPORCOES[cena.proporcao || '16:9'] || (quadroAtual ? quadroAtual.p : 16 / 9);
  return p >= 1 ? [lado, Math.round(lado / p)] : [Math.round(lado * p), lado];
}

function mostrarTamanhos() {
  if (!cena) return;
  if (eh3d()) {
    const antes = $('#render-tamanho').value;
    $('#render-tamanho').innerHTML = LADOS_3D.map(([l, t]) => { const [w, h] = tamanho3d(l); return `<option value="L${l}">${t} — ${nf(w)} × ${nf(h)} px</option>`; }).join('');
    $('#render-tamanho').value = LADOS_3D.some(([l]) => 'L' + l === antes) ? antes : 'L3840';
    return;
  }
  const [fw, fh] = cena.px, opcoes = [];
  for (const m of [2, 3, 4]) if (Math.max(fw, fh) * m <= LADO_RENDER_MAX) opcoes.push(m);
  if (!opcoes.length) opcoes.push(LADO_RENDER_MAX / Math.max(fw, fh));
  const antes = $('#render-tamanho').value;
  $('#render-tamanho').innerHTML = opcoes.map(m => `<option value="${m}">${m >= 1 && Number.isInteger(m) ? m + '× — ' : ''}${nf(fw * m)} × ${nf(fh * m)} px</option>`).join('');
  $('#render-tamanho').value = opcoes.map(String).includes(antes) ? antes : String(opcoes[Math.min(1, opcoes.length - 1)]);
}

/** Troca a imagem da sombra por uma maior só durante o render; devolve como estava. */
function sombraDoRender() {
  const r = visor.renderer, luz = visor._luz, antes = visor._alvoSombra;
  const lado = r.capabilities.maxTextureSize >= 16384 ? 8192 : 0;     // 8192² de profundidade: só placa com folga
  if (!visor.apresentacao || !antes || !lado || lado <= antes.width) return () => {};
  const alvo = new THREE.WebGLRenderTarget(lado, lado, { depthBuffer: true });
  alvo.depthTexture = new THREE.DepthTexture(lado, lado);
  const texel = luz.uTexel.value;
  visor._alvoSombra = alvo; luz.uTexel.value = 1 / lado;
  let devolvida = false;
  return () => {
    if (devolvida) return;
    devolvida = true;
    visor._alvoSombra = antes; luz.uTexel.value = texel;
    visor._desenharSombra();                                // a de antes de volta no shader antes de soltar a grande
    alvo.depthTexture.dispose(); alvo.dispose();
    visor.pedirQuadro();
  };
}

/** O render da cena do 3D: o lado escolhido na proporção do quadro, supersampling 2×, a sombra maior; o fundo
 *  transparente sai em PNG, o resto em JPEG 95 %. */
async function renderizar3d() {
  const lado = +String($('#render-tamanho').value || 'L3840').slice(1) || 3840, [w, h] = tamanho3d(lado);
  const png = (cena.fundo || 'ceu') === 'transparente';
  renderizando = true; mostrarBotoes();
  const t0 = performance.now(), devolver = sombraDoRender();
  try {
    const saida = await imagemDaCena3d(w, h, 2, async (i, n) => {
      aviso(`Renderizando ${nf(w)} × ${nf(h)} px: bloco ${i} de ${n}…`);
      await new Promise(res => setTimeout(res, 0));
    });
    devolver();
    aviso('Gravando a imagem renderizada…');
    const j = await enviarImagem(saida, png ? 'render.png' : 'render.jpg', png ? 'image/png' : 'image/jpeg', 0.95);
    avisoComPasta(`Imagem renderizada na pasta cenas da obra: ${j.nome} (${nf(w)} × ${nf(h)} px, ${nf((performance.now() - t0) / 1000, 1)} s).`
      + (vistaMudou ? ' A vista da tela não está gravada na cena: o render saiu com ela (Atualizar a cena guarda).' : ''), j.nome);
    atualizarCartoes();
  } catch (e) { devolver(); aviso('O render não saiu: ' + e.message); }
  finally { renderizando = false; mostrarBotoes(); ajustarQuadro(); }
}

async function renderizar() {
  if (renderizando) return;
  if (eh3d()) { cancelar(); await renderizar3d(); return; }
  if (!cena || !cena.camera) { aviso('Encaixe a cena antes de renderizar.'); return; }
  renderizando = true;
  $('#renderizar').disabled = $('#salvar-imagem').disabled = true;
  cancelar();
  mostrarModo('foto');
  const m = +$('#render-tamanho').value, w = Math.round(cena.px[0] * m), h = Math.round(cena.px[1] * m);
  const t0 = performance.now();
  tela.style.visibility = 'hidden';                         // os blocos passando pela tela não piscam na vista
  const devolver = sombraDoRender();
  try {
    const saida = await montarImagem(w, h, 2, async (i, n) => {
      aviso(`Renderizando ${nf(w)} × ${nf(h)} px: bloco ${i} de ${n}…`);
      await new Promise(res => setTimeout(res, 0));
    });
    devolver();
    await marcaNaImagem(saida);
    mostrarModo('foto');
    aviso('Gravando a imagem renderizada…');
    const j = await enviarImagem(saida, 'render.jpg', 'image/jpeg', 0.95);
    avisoComPasta(`Imagem renderizada na pasta cenas da obra: ${j.nome} (${nf(w)} × ${nf(h)} px, ${nf((performance.now() - t0) / 1000, 1)} s).`, j.nome);
    atualizarCartoes();
  } catch (e) {
    devolver();
    aviso('O render não saiu: ' + e.message);
  } finally {
    mostrarModo('foto');
    renderizando = false;
    $('#renderizar').disabled = $('#salvar-imagem').disabled = false;
  }
}

// ------------------------------------------------------------------ pôr as luzes e o pátio com o clique no 3D (12/11)

let colocando = null;                                       // {tipo: 'poste'|'refletor'|'luminaria'|'patio', i (mover), p0 (o 1º canto)}
const DICAS_COLOCAR = { poste: 'Clique no chão onde fica o poste.', refletor: 'Clique na parede onde fica o refletor.',
                        luminaria: 'Clique no teto (ou na peça) onde fica a luminária.', patio: 'Clique no chão: o primeiro canto do pátio.' };

function comecarAColocar(c) {
  if (!eh3d()) return;
  colocando = c;
  document.body.classList.add('colocando-luz');
  for (const b of document.querySelectorAll('.bt-luzes button')) b.classList.toggle('ligado', !c.figura && b.dataset.tipo === c.tipo && c.i === undefined);
  for (const b of document.querySelectorAll('.bt-figuras button')) b.classList.toggle('ligado', !!c.figura && b.dataset.tipo === c.tipo && c.i === undefined);
  const nome = c.figura && (TIPOS_FIGURA[c.tipo] || {}).nome;
  const dica = c.figura ? (c.i !== undefined ? `Clique no chão: o novo lugar de ${nome.toLowerCase()}.` : `Clique no chão para pôr: ${nome.toLowerCase()}. Cada clique põe mais uma.`)
                        : DICAS_COLOCAR[c.tipo];
  const el = c.figura ? $('#dica-figura') : $('#dica-luz');
  $('#dica-luz').hidden = $('#dica-figura').hidden = true;
  el.hidden = c.tipo === 'patio';
  el.textContent = dica + ' (Esc termina)';
  aviso(dica + ' (Esc termina)');
}

function pararDeColocar() {
  colocando = null;
  document.body.classList.remove('colocando-luz');
  for (const b of document.querySelectorAll('.bt-luzes button, .bt-figuras button')) b.classList.remove('ligado');
  for (const id of ['dica-luz', 'dica-figura']) { const d = document.getElementById(id); if (d) d.hidden = true; }
}

/** O giro de uma figura posta (graus): a pessoa olhando para a câmera, com um desvio; o veículo de frente para o prédio, no
 *  eixo mais perto (estacionado); a árvore, qualquer. */
function giroDaFigura(tipo, p, semente) {
  const r = ((semente * 9301 + 49297) % 233280) / 233280, w = paraMundo(p);
  const grupo = (TIPOS_FIGURA[tipo] || {}).grupo;
  if (grupo === 'gente') {
    const cam = visor.camera.position;
    return Math.round((Math.atan2(cam.y - w[1], cam.x - w[0]) * 180 / Math.PI + (r - 0.5) * 120 + 360) % 360);
  }
  if (grupo === 'veiculo') {
    const c = visor.caixaVisivel().getCenter(new THREE.Vector3()), dx = c.x - w[0], dy = c.y - w[1];
    return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 0 : 180) : (dy > 0 ? 90 : 270);
  }
  return Math.round(r * 360);
}

/** A lista das figuras postas no painel: o nome e o número, girar 45° (↻), mover (📍) e tirar (✕). */
function desenharListaFiguras() {
  const itens = figurasDaCena().itens, conta = {};
  $('#figuras-lista').innerHTML = itens.map((f, i) => {
    conta[f.tipo] = (conta[f.tipo] || 0) + 1;
    return `<div class="item-luz item-figura" data-i="${i}"><span>${(TIPOS_FIGURA[f.tipo] || {}).nome || f.tipo} ${conta[f.tipo]}</span>
      <button type="button" data-r="girar" title="Girar 45°">↻</button><button type="button" data-r="mover" title="Mudar de lugar (clique no chão)">📍</button><button type="button" data-r="tirar" title="Tirar">✕</button></div>`;
  }).join('');
  $('#figuras-tirar').disabled = !itens.length;
}

function colocarFigura(x, y, c) {
  const p = pontoNoChao(x, y);
  if (!p) { aviso('Clique no chão.'); return; }
  const fg = figurasDaCena(), itens = [...fg.itens], q = p.map(v => Math.round(v));
  if (c.i !== undefined) {
    itens[c.i] = { ...itens[c.i], p: q };
    pararDeColocar();
    mudar3d({ figuras: { ...fg, itens } });
    aviso(`${TIPOS_FIGURA[c.tipo].nome}: mudou de lugar.`);
    return;
  }
  if (itens.length >= FIGURAS_MAX) { aviso(`Até ${FIGURAS_MAX} figuras por cena.`); pararDeColocar(); return; }
  const semente = itens.reduce((m, f) => Math.max(m, f.semente || 0), 0) + 1;
  itens.push({ tipo: c.tipo, p: q, giro: giroDaFigura(c.tipo, q, semente), semente });
  mudar3d({ figuras: { ...fg, itens } });
  aviso(`Pôs: ${TIPOS_FIGURA[c.tipo].nome.toLowerCase()} (${itens.length} na cena). Clique para pôr mais; Esc termina.`);
}

/** O ponto do chão sob o mouse (o plano do chão, mm do projeto). */
function pontoNoChao(x, y) {
  const o = visor.cabecalho.origem, z = zDoChao();
  const ndc = new THREE.Vector2(x / tela.clientWidth * 2 - 1, -(y / tela.clientHeight) * 2 + 1);
  const raio = new THREE.Raycaster();
  visor.camera.updateMatrixWorld();
  raio.setFromCamera(ndc, visor.camera);
  const p = new THREE.Vector3();
  return raio.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), -z), p) ? [p.x + o[0], p.y + o[1], p.z + o[2]] : null;
}

function colocarEm(ev) {
  const r = tela.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top, c = colocando;
  if (c.figura) { colocarFigura(x, y, c); return; }
  const lz = luzesDaCena(), mao = [...(lz.mao || [])];
  if (c.tipo === 'patio') {
    const p = pontoNoChao(x, y);
    if (!p) return;
    if (!c.p0) { colocando = { ...c, p0: p }; aviso('Agora o canto oposto do pátio. (Esc cancela)'); return; }
    pararDeColocar();
    mudar3d({ entorno: { ...entornoDaCena(), tipo: 'patio', patio: [[c.p0[0], c.p0[1]], [p[0], p[1]]] } });
    aviso('Pátio desenhado.');
    return;
  }
  let p;
  if (c.tipo === 'poste') p = pontoNoChao(x, y);
  else { const a = visor.pontoEm(x, y); p = a && a.ponto; }
  if (!p) { aviso(c.tipo === 'poste' ? 'Clique no chão.' : 'Clique numa peça do modelo (a parede, o teto).'); return; }
  if (c.i !== undefined) mao[c.i] = { ...mao[c.i], p: p.map(v => Math.round(v)) };
  else {
    if (mao.length >= 20) { aviso('Até 20 luzes postas à mão por cena.'); pararDeColocar(); return; }
    mao.push({ tipo: c.tipo, p: p.map(v => Math.round(v)), forca: 1 });
  }
  pararDeColocar();
  mudar3d({ luzes: { ...lz, mao } });
  aviso(c.i !== undefined ? `${NOME_LUZ[c.tipo]} mudado de lugar.` : `${NOME_LUZ[c.tipo]} posto.` + (ambienteDaCena() && ambienteDaCena().noite ? '' : ' Acende nos ambientes de noite.'));
}

/** A lista das luzes postas à mão no painel: o nome, a força, mover (📍) e tirar (✕). */
function desenharLuzesMao() {
  const mao = luzesDaCena().mao || [], conta = {};
  $('#luzes-mao').innerHTML = mao.map((m, i) => {
    conta[m.tipo] = (conta[m.tipo] || 0) + 1;
    return `<div class="item-luz" data-i="${i}"><span>${NOME_LUZ[m.tipo] || m.tipo} ${conta[m.tipo]}</span>
      <input type="range" min="0" max="3" step="0.1" value="${m.forca ?? 1}" aria-label="Força">
      <button type="button" data-r="mover" title="Mudar de lugar (clique no 3D)">📍</button><button type="button" data-r="tirar" title="Tirar esta luz">✕</button></div>`;
  }).join('');
}

// ------------------------------------------------------------------ Renderizar e exportar (amostra-5, exportar_cenas.js)

/** O tamanho da imagem da cena aberta para o lado escolhido na janela: 'tela' (o quadro como está na tela; na foto, a foto
 *  até 4.096 px, como o Salvar imagem) ou o lado maior em px (na foto, a proporção dela). */
function tamanhoExportar(lado) {
  if (eh3d()) {
    if (lado !== 'tela') return tamanho3d(+lado || 1920);
    const k = window.devicePixelRatio || 1, q3 = quadroAtual || { w: 1280, h: 720 };
    return [Math.round(q3.w * k), Math.round(q3.h * k)];
  }
  if (!cena || !cena.px) return [0, 0];
  const maior = Math.max(...cena.px);
  const k = lado === 'tela' ? Math.min(1, 4096 / maior) : Math.min(+lado || 1920, LADO_RENDER_MAX) / maior;
  return [Math.round(cena.px[0] * k), Math.round(cena.px[1] * k)];
}

/** A imagem da cena aberta para a janela (a prévia e o lote): a marca d'água junto; refinada = a sombra maior. */
async function imagemParaExportar({ lado, ss = 1, refinada = false, aoBloco = null }) {
  const [w, h] = tamanhoExportar(lado);
  if (!w || !h) throw new Error('a cena não tem tamanho');
  if (ehFoto() && !cena.camera) throw new Error('a foto ainda não está encaixada');
  cancelar();
  renderizando = true; mostrarBotoes();
  const devolver = refinada ? sombraDoRender() : () => {};
  try {
    if (eh3d()) return await imagemDaCena3d(w, h, ss, aoBloco, true);
    mostrarModo('foto');
    tela.style.visibility = 'hidden';                       // os blocos passando pela tela não piscam na vista
    const saida = await montarImagem(w, h, ss, aoBloco);
    await marcaNaImagem(saida);
    return saida;
  } finally {
    devolver();
    renderizando = false;
    if (ehFoto()) mostrarModo('foto');
    mostrarBotoes();
  }
}

function textoDaMarca() {
  if (!cena) return '';
  const m = marcaDaCena();
  if (m.empresa === 'sem' || !temLogo(m.empresa)) return 'Sem marca d\'água.';
  const e = marcaInfo.empresas.find(x => x.id === m.empresa) || {};
  const jeito = { A: 'A · logo no canto', B: 'B · logo na placa', C: 'C · faixa com o nome da obra' }[m.jeito] || m.jeito;
  return `${e.nome || m.empresa} · ${jeito} · canto ${m.canto === 'esq' ? 'esquerdo' : 'direito'}`;
}

let exportar = null;
function ligarExportarCenas() {
  exportar = ligarExportar({
    cenas: () => todasCenas,
    atual: () => cena,
    abrir: async (id) => { const r = await abrirCena(id, { recarregar: false }); await new Promise(res => requestAnimationFrame(res)); return r; },
    podeRender: (c) => (c && c.tipo !== '3d' && !c.camera ? 'a foto ainda não está encaixada' : ''),
    tamanho: tamanhoExportar,
    imagem: imagemParaExportar,
    transparente: () => eh3d() && (cena.fundo || 'ceu') === 'transparente',
    marca: textoDaMarca,
    enviar: (blob, nome) => pedir(`${API}/${encodeURIComponent(cena.id)}/imagem`, undefined, { dados: blob, nome }),
    enviarPdf: (blob, nome) => pedir(`${API}/pdf`, undefined, { dados: blob, nome }),
    video: (o) => videoDasCenas(o),
    cartao: (jeito, vista, texto) => cartaoDoVideo(vista.width, vista.height, marcaDaCena(), jeito, vista, texto),
    enviarVideo: (blob, nome) => pedir(`${API}/video`, undefined, { dados: blob, nome }),
    abrirPasta: (nome) => mostrarNaPasta(nome),
    terminou: () => atualizarCartoes(),
    nomeObra: () => $('#titulo-obra').textContent,
  });
  $('#exportar').onclick = () => exportar.abrir();
  $('#pasta-cenas').onclick = () => mostrarNaPasta('').catch(e => aviso('A pasta não abriu: ' + e.message));
  // os vídeos já gravados, assistidos aqui (usuário, 12/11: "quero assistir dentro do sistema")
  const videos = ligarVideos({ api: API, abrirPasta: (nome) => mostrarNaPasta(nome) });
  $('#videos-cenas').onclick = () => videos.abrir();
}

// ------------------------------------------------------------------ os controles

function ligarControles() {
  $('#nova').onclick = () => $('#arquivo').click();
  $('#arquivo').onchange = async () => {
    const f = $('#arquivo').files[0]; $('#arquivo').value = '';
    if (!f) return;
    aviso(`Enviando ${f.name} (${nf(f.size / 1048576, 1)} MB)…`);
    try {
      const c = await pedir(`${API}/nova`, undefined, { dados: f, nome: f.name });
      const comeco = {};                                    // começa com as camadas e o sol de agora
      if (soltas.length) comeco.desligadas = soltas;
      if (solSolto) comeco.sol = solDaCena();
      if (Object.keys(comeco).length) await pedir(`${API}/${encodeURIComponent(c.id)}`, comeco);
      aviso(''); await listar(c.id); comecarPonto();
    }
    catch (e) { aviso('A foto não entrou: ' + e.message); }
  };
  $('#lista').onchange = () => { if ($('#lista').value) abrirCena($('#lista').value); };
  ligar3d();
  $('#novo-ponto').onclick = comecarPonto;
  $('#ver').onclick = () => { cancelar(); mostrarModo(modo === '3d' ? 'foto' : '3d'); };
  $('#encaixar').onclick = () => { cancelar(); lembrar(); fazerEncaixe().catch(e => aviso('O encaixe falhou: ' + e.message)); };
  $('#salvar-imagem').onclick = () => salvarImagem();
  $('#renderizar').onclick = () => renderizar();
  ligarExportarCenas();
  $('#salvar-cena').onclick = () => concluir(true).catch(e => aviso('A cena não foi salva: ' + e.message));
  $('#editar').onclick = () => concluir(false).catch(e => aviso('Não deu: ' + e.message));
  $('#apagar').onclick = () => cena && apagarCena(cena);
  $('#pares').onclick = async (e) => {
    const b = e.target.closest('button[data-acao]');
    if (!b || !cena) return;
    const i = +b.dataset.i;
    try {
      if (b.dataset.acao === '3d') marcarNo3d(i);
      else if (b.dataset.acao === 'foto') {
        marcando = { etapa: 'foto', i };
        mostrarModo('foto');
        aviso(`Clique de novo o ponto ${i + 1} na foto (Esc cancela).`);
      } else if (b.dataset.acao === 'apagar') {
        cancelar();
        lembrar();
        const pares = cena.pares.slice(); pares.splice(i, 1);
        await gravar({ pares });
        await reencaixar(`Ponto ${i + 1} apagado.`);
      }
    } catch (err) { aviso('Não deu: ' + err.message); }
  };
  $('#lente').oninput = () => {
    if (!cena || !cena.camera) return;
    lembrar('lente');
    cena.camera.fov = +$('#lente').value; aplicarCamera();
    const camera = { ...cena.camera };                      // o valor de agora (como o sol)
    clearTimeout(tempoLente); tempoLente = setTimeout(() => gravar({ camera }), 600);
  };
  $('#rolar').oninput = () => {
    if (!cena || !cena.camera) return;
    lembrar('rolar');
    rolar = +$('#rolar').value; aplicarCamera();
    clearTimeout(tempoLente);
    tempoLente = setTimeout(() => {                       // o rolar entra no giro gravado
      if (!cena || !cena.camera || !giroBase) return;
      const g = giroBase.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rolar * Math.PI / 180));
      rolar = 0;
      gravar({ camera: { ...cena.camera, giro: g.toArray() } }).then(aplicarCamera);
    }, 800);
  };
  $('#opacidade').oninput = () => {
    lembrar('opacidade');
    tela.style.opacity = telaFina.style.opacity = modo === 'foto' ? $('#opacidade').value : '1'; atualizarFaixas();
    clearTimeout(tempoOpac); tempoOpac = setTimeout(() => gravar({ opacidade: +$('#opacidade').value }), 600);
  };
  $('#sol').onchange = () => { lembrar(); mudarSol({ ligado: $('#sol').checked }); };
  $('#camadas').onchange = (e) => {
    const c = e.target.closest('input[data-chave]');
    if (!c) return;
    if (!cena) {                                            // antes da foto: só o 3D da tela (e a cena nova começa assim)
      const s = new Set(soltas);
      if (c.checked) s.delete(c.dataset.chave); else s.add(c.dataset.chave);
      soltas = [...s];
      try { localStorage.setItem(CHAVE_SOLTAS, JSON.stringify(soltas)); } catch (err) { /* sem o navegador lembrar */ }
      aplicarCamadas();
      return;
    }
    lembrar();
    const desl = new Set(cena.desligadas || []);
    if (c.checked) desl.delete(c.dataset.chave); else desl.add(c.dataset.chave);
    cena.desligadas = [...desl];
    aplicarCamadas();
    const desligadas = cena.desligadas;                    // o valor de agora (como o sol)
    clearTimeout(tempoCamadas); tempoCamadas = setTimeout(() => gravar({ desligadas }), 500);
  };
  ligarFrente();
  ligarMarca();
  addEventListener('keydown', (e) => {
    if (desenho) {                                          // desenhando um contorno: as teclas são dele
      const ctrlZ = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z';
      if (e.key === 'Enter') { e.preventDefault(); fecharContorno(); return; }
      if (e.key === 'Backspace' || ctrlZ) { e.preventDefault(); desenho.pop(); desenharFrenteSvg(); return; }
      if (e.key === 'Escape') { pararContorno(); aviso('Contorno cancelado.'); return; }
    }
    const el = document.activeElement || {}, digitando = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && /^(text|search|number)$/.test(el.type));
    if ((e.ctrlKey || e.metaKey) && !e.altKey && /^[zy]$/i.test(e.key) && !digitando) {
      e.preventDefault();
      if (e.key.toLowerCase() === 'y' || e.shiftKey) refazer(); else desfazer();
      return;
    }
    if (e.key === 'Escape') { cancelar(); if (selecionado !== null) escolherPonto(null); return; }
    const setas = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!setas || selecionado === null || modo !== 'foto' || marcando || !cena || cena.concluida || /INPUT|SELECT|TEXTAREA/.test((document.activeElement || {}).tagName || '')) return;
    e.preventDefault();
    const k = e.shiftKey ? 10 : 1, p = cena.pares[selecionado].foto;
    moverPonto(selecionado, p[0] + setas[0] * k / marcas.clientWidth, p[1] + setas[1] * k / marcas.clientHeight);
    gravarAjuste(600);
  });
  // escolher o ponto pela linha dele na lista (fora dos botões)
  $('#pares').addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    const l = e.target.closest('[data-escolher]');
    if (l) { mostrarModo('foto'); escolherPonto(+l.dataset.escolher === selecionado ? null : +l.dataset.escolher); }
  });
  // na foto: pegar a marca e arrastar
  marcas.addEventListener('pointerdown', (e) => {
    if (modo !== 'foto' || marcando || !cena || cena.concluida || e.button !== 0) return;
    const r = marcas.getBoundingClientRect(), i = pontoPerto(e.clientX - r.left, e.clientY - r.top);
    if (i === null) { if (selecionado !== null) escolherPonto(null); return; }
    escolherPonto(i);
    arrasto = { i, dx: cena.pares[i].foto[0] * r.width - (e.clientX - r.left), dy: cena.pares[i].foto[1] * r.height - (e.clientY - r.top) };
    marcas.setPointerCapture(e.pointerId);
    marcas.style.cursor = 'grabbing';
    e.preventDefault();
  });
  marcas.addEventListener('pointermove', (e) => {
    const r = marcas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    if (!arrasto) { if (modo === 'foto' && !marcando && cena) marcas.style.cursor = pontoPerto(x, y) !== null ? 'grab' : ''; return; }
    moverPonto(arrasto.i, (x + arrasto.dx) / r.width, (y + arrasto.dy) / r.height);
  });
  const soltar = () => { if (!arrasto) return; arrasto = null; marcas.style.cursor = ''; encaixeRapido(); gravarAjuste(0); };
  marcas.addEventListener('pointerup', soltar);
  marcas.addEventListener('pointercancel', soltar);
  addEventListener('resize', () => mostrarModo(modo));

  // o clique na foto: o ponto novo
  marcas.addEventListener('click', async (e) => {
    if (modo !== 'foto' || !marcando || marcando.etapa !== 'foto') return;
    const r = marcas.getBoundingClientRect();
    const u = (e.clientX - r.left) / r.width, v = (e.clientY - r.top) / r.height;
    if (u < 0 || u > 1 || v < 0 || v > 1) return;
    lembrar();
    if (marcando.i !== undefined) {                          // o ponto de antes, de novo na foto
      const i = marcando.i, pares = cena.pares.slice();
      pares[i] = { ...pares[i], foto: [u, v] };
      cancelar();
      await gravar({ pares });
      await reencaixar(`Ponto ${i + 1} marcado de novo na foto.`);
      return;
    }
    const pares = (cena.pares || []).concat([{ foto: [u, v] }]);
    await gravar({ pares });
    marcarNo3d(pares.length - 1);
    marcando.novo = true;                                   // o ponto novo inteiro (foto e 3D) é um passo só
  });
  // o clique no 3D (sem arrastar): o ponto do modelo
  let desce = null;
  tela.addEventListener('pointerdown', (e) => { desce = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  tela.addEventListener('pointerup', async (e) => {
    if (!desce || !marcando || marcando.etapa !== '3d' || modo !== '3d') return;
    const parado = Math.hypot(e.clientX - desce.x, e.clientY - desce.y) < 5 && performance.now() - desce.t < 700;
    desce = null;
    if (!parado || e.button !== 0) return;
    const r = tela.getBoundingClientRect(), p = pontoDo3d(e.clientX - r.left, e.clientY - r.top);
    if (!p) { aviso('Nada nesse ponto: clique numa peça ou no chão.'); return; }
    if (!marcando.novo) lembrar();
    const i = marcando.i, pares = cena.pares.slice();
    pares[i] = { ...pares[i], modelo: p };
    cancelar();
    await gravar({ pares });
    const completos = pares.filter(x => x.modelo).length;
    if (completos >= 4) { await reencaixar(); }
    else { mostrarModo('foto'); aviso(`Ponto ${i + 1} marcado. Faltam ${4 - completos} para encaixar.`); }
  });
}

// ------------------------------------------------------------------ as marcas (a cada quadro)

const _v = new THREE.Vector3();
function desenharMarcas() {
  requestAnimationFrame(desenharMarcas);
  if (!visor || !cena || cena.concluida) { if (marcas._html) { marcas.innerHTML = ''; marcas._html = ''; } return; }
  const w = marcas.clientWidth, h = marcas.clientHeight, o = visor.cabecalho.origem, html = [];
  const naTela = (X) => {
    _v.set(X[0] - o[0], X[1] - o[1], X[2] - o[2]).project(visor.camera);
    return _v.z < 1 && _v.z > -1 ? [(_v.x + 1) / 2 * w, (1 - _v.y) / 2 * h] : null;
  };
  (cena.pares || []).forEach((p, i) => {
    if (modo === 'foto') {
      html.push(`<div class="marca foto${p.modelo ? ' feito' : ''}${i === selecionado ? ' sel' : ''}" style="left:${p.foto[0] * w}px;top:${p.foto[1] * h}px">${i + 1}</div>`);
      if (p.modelo && cena.camera) { const s = naTela(p.modelo); if (s) html.push(`<div class="marca proj" style="left:${s[0]}px;top:${s[1]}px"></div>`); }
    } else if (p.modelo) {
      const s = naTela(p.modelo);
      if (s) html.push(`<div class="marca modelo" style="left:${s[0]}px;top:${s[1]}px">${i + 1}</div>`);
    }
  });
  const novo = html.join('');
  if (novo !== marcas._html) { marcas.innerHTML = novo; marcas._html = novo; }
}

window.cenaApi = { estado: () => ({ modo, marcando, cena, selecionado, desenho, paredes: paredes.length, fina: !telaFina.hidden,
                                    fovCena, quadro: quadroAtual, vistaMudou, cenas: todasCenas.map(c => c.id) }), mostrarModo, pontoDo3d, fazerEncaixe,
                   concluir, desfazer, refazer, geometriaDoContorno, bordaDeBaixo, montarImagem, abrirCena, novaCena3d, imagemDaCena3d, cameraDaTela,
                   exportar: () => exportar, tamanhoExportar, medidaDoLogo, videoDasCenas, cartaoDoVideo };
// saindo da página (o ← 3D antes de o 3D terminar de chegar): o pedido cortado pela troca de página não é erro
let saindoDaPagina = false;
addEventListener('beforeunload', () => { saindoDaPagina = true; });
addEventListener('pagehide', () => { saindoDaPagina = true; });
abrir().catch(e => { if (saindoDaPagina) return; aviso('A cena não abriu: ' + e.message); console.error(e); });
