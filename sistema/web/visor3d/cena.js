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

import * as THREE from 'three';
import { Visor3D } from './visor3d.js';
import { Terreno } from './terreno.js';
import { encaixar } from './encaixe.js';

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
const foto = $('#foto'), tela = $('#tela'), marcas = $('#marcas'), palco = $('#palco');

function aviso(txt) { $('#aviso').textContent = txt || ''; }

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
  $('#voltar').onclick = () => { location.href = `/visor3d/ver3d.html?projeto=${encodeURIComponent(PROJETO)}`; };
  // a cobertura retrátil na situação da cena (aberta ou retraída): o 3D leve dela
  const { cenas } = await pedir(API);
  const escolhida = cenas.find(c => c.id === q.get('cena')) || cenas[cenas.length - 1] || null;
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
  visor.ligarApresentacao(true, 2048);
  terreno = new Terreno(visor, PROJETO, { abrirPainel: () => {}, corpo: () => null, situacao: aviso, palco,
                                          painelAtual: () => null, aoMudar: () => {}, chaveLigado: null });
  try { await terreno.carregar(); } catch (e) { /* sem o terreno: os pontos só nas peças */ }
  $('#carregando').remove();
  ligarControles();
  await coberturaRetratil();
  await listar(escolhida ? escolhida.id : null);
  window.cenaPronta = true;
  requestAnimationFrame(desenharMarcas);
}

// ------------------------------------------------------------------ as cenas

async function listar(escolher) {
  const { cenas } = await pedir(API);
  const sel = $('#lista');
  sel.innerHTML = cenas.length ? cenas.map(c => `<option value="${esc(c.id)}">${esc(c.nome)}</option>`).join('')
    : '<option value="">(nenhuma cena: comece pela foto)</option>';
  const id = escolher && cenas.some(c => c.id === escolher) ? escolher : (cenas[cenas.length - 1] || {}).id;
  if (id) { sel.value = id; await abrirCena(id); } else { cena = null; $('#corpo').hidden = true; foto.hidden = true; mostrarModo('3d'); }
}

async function abrirCena(id) {
  const nova = await pedir(`${API}/${encodeURIComponent(id)}`);
  if ((nova.situacao || null) !== situacaoAberta) {          // a outra situação da cobertura: o 3D dela
    location.href = `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(id)}`;
    return;
  }
  cena = nova;
  history.replaceState(null, '', `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(id)}`);
  foto.hidden = false;
  foto.src = `${API}/${encodeURIComponent(id)}/foto.jpg?v=${encodeURIComponent(cena.alterada || '')}`;
  try { await foto.decode(); } catch (e) { aviso('A foto não abriu.'); }
  $('#corpo').hidden = false;
  rolar = 0;
  giroBase = null;
  $('#opacidade').value = cena.opacidade ?? 1;
  aplicarCamera();
  mostrarModo('foto');
  desenharPares();
  desenharCamadas();
  marcarSituacao();
  mostrarConcluida();
}

// ------------------------------------------------------------------ camadas e cobertura retrátil
// (usuário, 26/10: "essa imagem interagir com as camadas, poder abrir a quadra, colocar e tirar a lona") — gravadas na cena:
// a imagem salva sai como está na tela

function desenharCamadas() {
  if (!visor || !cena) return;
  const desl = new Set(cena.desligadas || []), cams = visor.cabecalho.camadas || [];
  const linha = (chave, nome, cor, ligada) => `<label><input type="checkbox" data-chave="${esc(chave)}" ${ligada ? 'checked' : ''}>
    ${cor ? `<i style="background:${esc(cor)}"></i>` : ''}<span>${esc(nome)}</span></label>`;
  let html = '';
  if (sistemas.length > 1) html += '<div class="grupo">Sistema</div>' + sistemas.map(s => linha('sistema:' + s.chave, s.nome, s.cor, !desl.has('sistema:' + s.chave))).join('');
  html += '<div class="grupo">Camadas</div>' + cams.map(c => linha('camada:' + c.nome, c.nome, c.cor, !desl.has('camada:' + c.nome))).join('');
  $('#camadas').innerHTML = html;
  aplicarCamadas();
}

function aplicarCamadas() {
  const desl = new Set((cena && cena.desligadas) || []);
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
  $('#ver').disabled = !cena;
  if (!visor) return;
  if (m === 'foto' && cena) {
    const r = retanguloFoto();
    posicionar(foto, r); posicionar(tela, r); posicionar(marcas, r);
    visor.cena.background = null;
    if (visor.piso) visor.piso.visible = false;
    if (terreno && terreno.grupo) terreno.grupo.visible = false;
    visor.controles.enabled = false;
    tela.style.pointerEvents = 'none';
    tela.style.opacity = String(cena.opacidade ?? 1);
    tela.style.visibility = cena.camera ? 'visible' : 'hidden';   // antes do encaixe, o 3D não tem onde ficar na foto
    visor.redimensionar();
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
    if (camera3d) {
      visor.camera.position.copy(camera3d.pos); visor.camera.quaternion.copy(camera3d.q); visor.camera.fov = camera3d.fov;
      visor.controles.target.copy(camera3d.alvo); visor.camera.updateProjectionMatrix();
    } else visor.enquadrar('iso');
    visor.pedirQuadro();
  }
}

/** A câmera da cena no visor (na vista da foto): a posição e o giro gravados (mm do projeto), o rolar e a lente. */
function aplicarCamera() {
  if (!visor || !cena || !cena.camera || modo !== 'foto') { atualizarFaixas(); return; }
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
  visor._sombraSuja = true;
  visor.pedirQuadro();
  atualizarFaixas();
}

function atualizarFaixas() {
  const c = cena && cena.camera;
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

async function gravar(campos) {
  cena = await pedir(`${API}/${encodeURIComponent(cena.id)}`, campos);
  desenharPares();
  atualizarFaixas();
  $('#salvar-cena').disabled = !cena.camera;
}

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
  clearTimeout(tempoAjuste);                                // o ajuste fino ainda por gravar vai junto
  const campos = { concluida: pronta };
  if (pronta) Object.assign(campos, { pares: cena.pares, camera: cena.camera });
  await gravar(campos);
  mostrarConcluida();
  aviso(pronta ? 'Cena salva: os pontos saíram da tela. Para mexer neles, Editar cena.' : 'Editando: os pontos de volta na foto.');
}

function comecarPonto() {
  if (!cena) return;
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
  document.body.classList.remove('marcando-3d');
  aviso('');
}

/** O ponto do 3D sob o clique (mm do projeto): a peça, ou o chão da imagem do terreno (sem terreno, o pé do modelo). */
function pontoDo3d(x, y) {
  const achado = visor.pontoEm(x, y);
  if (achado) return achado.ponto;
  const o = visor.cabecalho.origem;
  const z = terreno && Number.isFinite(terreno.zChao) && terreno.malha ? terreno.zChao - o[2] : visor._caixaModelo.min.z;
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

// ------------------------------------------------------------------ a imagem pronta

async function salvarImagem() {
  if (!cena || !cena.camera) { aviso('Encaixe a cena antes de salvar a imagem.'); return; }
  mostrarModo('foto');
  const k = Math.min(1, 4096 / Math.max(...cena.px)), w = Math.round(cena.px[0] * k), h = Math.round(cena.px[1] * k);
  const saida = document.createElement('canvas');
  saida.width = w; saida.height = h;
  const g = saida.getContext('2d');
  g.drawImage(foto, 0, 0, w, h);
  const r = visor.renderer, dpr = r.getPixelRatio();
  r.setPixelRatio(1); r.setSize(w, h, false);
  visor.camera.aspect = w / h; visor.camera.updateProjectionMatrix();
  if (visor.apresentacao) visor._desenharSombra();
  r.render(visor.cena, visor.camera);
  g.globalAlpha = +$('#opacidade').value;
  g.drawImage(r.domElement, 0, 0, w, h);
  r.setPixelRatio(dpr);
  visor.redimensionar();
  aviso('Salvando a imagem…');
  const blob = await new Promise(res => saida.toBlob(res, 'image/png'));
  try {
    const j = await pedir(`${API}/${encodeURIComponent(cena.id)}/imagem`, undefined, { dados: blob, nome: 'cena.png' });
    aviso(`Imagem salva na pasta cenas da obra: ${j.nome} (${w} × ${h} px).`);
    window.ultimaImagemCena = j;
  } catch (e) { aviso('A imagem não foi salva: ' + e.message); }
}

// ------------------------------------------------------------------ os controles

function ligarControles() {
  $('#nova').onclick = () => $('#arquivo').click();
  $('#arquivo').onchange = async () => {
    const f = $('#arquivo').files[0]; $('#arquivo').value = '';
    if (!f) return;
    aviso(`Enviando ${f.name} (${nf(f.size / 1048576, 1)} MB)…`);
    try { const c = await pedir(`${API}/nova`, undefined, { dados: f, nome: f.name }); aviso(''); await listar(c.id); comecarPonto(); }
    catch (e) { aviso('A foto não entrou: ' + e.message); }
  };
  $('#lista').onchange = () => { if ($('#lista').value) abrirCena($('#lista').value); };
  $('#novo-ponto').onclick = comecarPonto;
  $('#ver').onclick = () => { cancelar(); mostrarModo(modo === '3d' ? 'foto' : '3d'); };
  $('#encaixar').onclick = () => { cancelar(); fazerEncaixe().catch(e => aviso('O encaixe falhou: ' + e.message)); };
  $('#salvar-imagem').onclick = () => salvarImagem();
  $('#salvar-cena').onclick = () => concluir(true).catch(e => aviso('A cena não foi salva: ' + e.message));
  $('#editar').onclick = () => concluir(false).catch(e => aviso('Não deu: ' + e.message));
  $('#apagar').onclick = async () => {
    if (!cena || !confirm(`Apagar a cena "${cena.nome}"? A foto e os pontos saem do projeto (a imagem salva na pasta cenas fica).`)) return;
    try { await pedir(`${API}/${encodeURIComponent(cena.id)}/apagar`, {}); aviso('Cena apagada.'); await listar(); }
    catch (err) { aviso('A cena não foi apagada: ' + err.message); }
  };
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
        const pares = cena.pares.slice(); pares.splice(i, 1);
        await gravar({ pares });
        await reencaixar(`Ponto ${i + 1} apagado.`);
      }
    } catch (err) { aviso('Não deu: ' + err.message); }
  };
  let tempoLente = 0;
  $('#lente').oninput = () => {
    if (!cena || !cena.camera) return;
    cena.camera.fov = +$('#lente').value; aplicarCamera();
    clearTimeout(tempoLente); tempoLente = setTimeout(() => gravar({ camera: cena.camera }), 600);
  };
  $('#rolar').oninput = () => {
    rolar = +$('#rolar').value; aplicarCamera();
    clearTimeout(tempoLente);
    tempoLente = setTimeout(() => {                       // o rolar entra no giro gravado
      if (!cena || !cena.camera || !giroBase) return;
      const g = giroBase.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rolar * Math.PI / 180));
      rolar = 0;
      gravar({ camera: { ...cena.camera, giro: g.toArray() } }).then(aplicarCamera);
    }, 800);
  };
  let tempoOpac = 0;
  $('#opacidade').oninput = () => {
    tela.style.opacity = modo === 'foto' ? $('#opacidade').value : '1'; atualizarFaixas();
    clearTimeout(tempoOpac); tempoOpac = setTimeout(() => gravar({ opacidade: +$('#opacidade').value }), 600);
  };
  $('#sol').onchange = () => { visor.ligarApresentacao($('#sol').checked, 2048); visor.pedirQuadro(); };
  let tempoCamadas = 0;
  $('#camadas').onchange = (e) => {
    const c = e.target.closest('input[data-chave]');
    if (!c || !cena) return;
    const desl = new Set(cena.desligadas || []);
    if (c.checked) desl.delete(c.dataset.chave); else desl.add(c.dataset.chave);
    cena.desligadas = [...desl];
    aplicarCamadas();
    clearTimeout(tempoCamadas); tempoCamadas = setTimeout(() => gravar({ desligadas: cena.desligadas }), 500);
  };
  addEventListener('keydown', (e) => {
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

window.cenaApi = { estado: () => ({ modo, marcando, cena, selecionado }), mostrarModo, pontoDo3d, fazerEncaixe, concluir };
abrir().catch(e => { aviso('A cena não abriu: ' + e.message); console.error(e); });
