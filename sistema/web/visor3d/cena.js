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
import { Visor3D, SOMBRA_GLSL } from './visor3d.js';
import { Terreno } from './terreno.js';
import { encaixar } from './encaixe.js';
import { SOL_PADRAO, definirSol, controlesDoSol, ligarControlesDoSol } from './sol.js';

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
  // dentro do quadro do 3D (o botão Cenas do modo ver), volta ao modo ver do quadro; na janela inteira (o menu Cenas › Cenas
  // da obra…), à área de trabalho do projeto com o 3D — antes ia ao modo ver solto, sem a barra de cima, e o Cenas dele
  // voltava aqui: um laço sem saída para a tela inicial (usuário, 28/10)
  $('#voltar').onclick = () => {
    const p = encodeURIComponent(PROJETO);
    location.href = window.top !== window ? `/visor3d/ver3d.html?projeto=${p}` : `/dividida?projeto=${p}&vista=3d`;
  };
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
  desfeitos.length = refeitos.length = 0;                   // o histórico é de uma cena só
  history.replaceState(null, '', `?projeto=${encodeURIComponent(PROJETO)}&cena=${encodeURIComponent(id)}`);
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
    if (camera3d) {
      visor.camera.position.copy(camera3d.pos); visor.camera.quaternion.copy(camera3d.q); visor.camera.fov = camera3d.fov;
      visor.controles.target.copy(camera3d.alvo); visor.camera.updateProjectionMatrix();
    } else visor.enquadrar('iso');
    visor.pedirQuadro();
  }
  desenharFrenteSvg();
}

/** A câmera da cena no visor (na vista da foto): a posição e o giro gravados (mm do projeto), o rolar e a lente. */
function aplicarCamera() {
  if (!visor || !cena || !cena.camera || modo !== 'foto') { atualizarFaixas(); if (visor) atualizarParedes(); return; }
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

/** Grava `campos` na cena. A cena da tela é a que vale: os campos entram nela antes de ir ao servidor, e a resposta só traz
 *  o que é do servidor (a hora) — uma resposta que chegasse depois de outra mudança na tela a desfazia (27/10: o sol
 *  mexido logo depois de um Ctrl+Z voltava ao de antes). */
async function gravar(campos) {
  const id = cena.id;
  Object.assign(cena, JSON.parse(JSON.stringify(campos)));
  const r = await pedir(`${API}/${encodeURIComponent(id)}`, campos);
  if (cena && cena.id === id) cena.alterada = r.alterada;
  desenharPares();
  atualizarFaixas();
  $('#salvar-cena').disabled = !cena.camera;
}

// ------------------------------------------------------------------ o sol da cena
// (usuário, 27/10: "poderia ter as opções de mudar a posição das sombras aqui na composição da cena"): os mesmos controles
// do modo ver e do celular (sol.js), gravados na cena — cada foto tem a hora dela

let tempoSol = 0;
const CHAO_PADRAO = 0.5;
function solDaCena() { return { ligado: true, ...SOL_PADRAO, chao: CHAO_PADRAO, ...((cena && cena.sol) || {}) }; }

function mostrarSol() {
  const s = solDaCena();
  $('#sol').checked = s.ligado;
  $('#sol-caixa').hidden = !s.ligado;
  $('#sol-caixa').innerHTML = controlesDoSol(s) +
    `<label class="faixa">Sombra no chão <input type="range" id="sombra-chao" min="0" max="1" step="0.05" value="${s.chao}">
      <span id="sombra-chao-val">${nf(s.chao * 100)} %</span></label>
    <p class="dica">A direção gira o sol em volta da obra; a altura vai do nascer (baixo, sombras compridas) ao meio-dia (alto).
      A sombra no chão cai no plano dos pontos do chão (a quadra); 0 % a desliga.</p>`;
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
  chaoSombra.visible = modo === 'foto' && !!cena && s.ligado && s.chao > 0;
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
  if (!cena) return;
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

function retrato() {
  const r = JSON.parse(JSON.stringify({ pares: cena.pares || [], camera: cena.camera || null, opacidade: cena.opacidade ?? 1,
                                        desligadas: cena.desligadas || [], sol: cena.sol || null, frente: cena.frente || [] }));
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
  [tempoAjuste, tempoSol, tempoLente, tempoOpac, tempoCamadas, tempoCobre].forEach(clearTimeout);
  para.push(retrato());
  const r = de.pop();
  ultimaMudanca = { tipo: null, t: 0 };
  Object.assign(cena, r);
  if (!r.sol) delete cena.sol;
  rolar = 0;
  if (selecionado !== null && selecionado >= cena.pares.length) selecionado = null;
  $('#opacidade').value = cena.opacidade;
  desenharPares();
  desenharCamadas();
  mostrarSol();
  if (contornoSel !== null && contornoSel >= cena.frente.length) contornoSel = null;
  desenharContornos();
  mostrarModo(modo);
  try {
    await gravar({ pares: cena.pares, camera: cena.camera, opacidade: cena.opacidade, desligadas: cena.desligadas,
                   sol: r.sol || { ligado: true, ...SOL_PADRAO }, frente: cena.frente });
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
async function montarImagem(w, h, ss = 1, aoBloco = null, { comFoto = true, frente = true, bloco = 2048 } = {}) {
  const saida = document.createElement('canvas');
  saida.width = w; saida.height = h;
  const g = saida.getContext('2d');
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  if (comFoto) g.drawImage(foto, 0, 0, w, h);
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
  if (!cena || !cena.camera) { aviso('Encaixe a cena antes de salvar a imagem.'); return; }
  mostrarModo('foto');
  const k = Math.min(1, 4096 / Math.max(...cena.px)), w = Math.round(cena.px[0] * k), h = Math.round(cena.px[1] * k);
  const saida = await montarImagem(w, h);
  aviso('Salvando a imagem…');
  try {
    const j = await enviarImagem(saida, 'cena.png', 'image/png');
    aviso(`Imagem salva na pasta cenas da obra: ${j.nome} (${w} × ${h} px).`);
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

function mostrarTamanhos() {
  if (!cena) return;
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

async function renderizar() {
  if (renderizando) return;
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
    mostrarModo('foto');
    aviso('Gravando a imagem renderizada…');
    const j = await enviarImagem(saida, 'render.jpg', 'image/jpeg', 0.95);
    aviso(`Imagem renderizada na pasta cenas da obra: ${j.nome} (${nf(w)} × ${nf(h)} px, ${nf((performance.now() - t0) / 1000, 1)} s).`);
  } catch (e) {
    devolver();
    aviso('O render não saiu: ' + e.message);
  } finally {
    mostrarModo('foto');
    renderizando = false;
    $('#renderizar').disabled = $('#salvar-imagem').disabled = false;
  }
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
  $('#encaixar').onclick = () => { cancelar(); lembrar(); fazerEncaixe().catch(e => aviso('O encaixe falhou: ' + e.message)); };
  $('#salvar-imagem').onclick = () => salvarImagem();
  $('#renderizar').onclick = () => renderizar();
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
    if (!c || !cena) return;
    lembrar();
    const desl = new Set(cena.desligadas || []);
    if (c.checked) desl.delete(c.dataset.chave); else desl.add(c.dataset.chave);
    cena.desligadas = [...desl];
    aplicarCamadas();
    const desligadas = cena.desligadas;                    // o valor de agora (como o sol)
    clearTimeout(tempoCamadas); tempoCamadas = setTimeout(() => gravar({ desligadas }), 500);
  };
  ligarFrente();
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

window.cenaApi = { estado: () => ({ modo, marcando, cena, selecionado, desenho, paredes: paredes.length, fina: !telaFina.hidden }), mostrarModo, pontoDo3d, fazerEncaixe,
                   concluir, desfazer, refazer, geometriaDoContorno, bordaDeBaixo, montarImagem };
abrir().catch(e => { aviso('A cena não abriu: ' + e.message); console.error(e); });
