// As cenas do 3D no modo ver, como as cenas do SketchUp (usuário, 11/11: "Não tem a opção de criar cena, não tem uma
// opção para salvar cena, renderizar, colocar isso em uma prancha… preciso que crie esse tipo de situação"; aprovado nas
// amostras de Projeto/BRIEFINGS/imagens/cenas-3d/: abas no rodapé + o painel do botão Cenas).
//
//   · as abas no rodapé: uma por cena, na ordem gravada; clicar anda a câmera até a cena e aplica as camadas e o estilo
//     dela; "+ Cena" grava a vista atual com nome. Botão direito na aba: renomear, atualizar com a vista atual, mover,
//     apagar. PageUp/PageDown: a cena anterior/seguinte; Alt+1…9 vai à cena n; Alt+0 grava uma nova (como no editor);
//   · a cena por foto (cena.html) é uma aba a mais (📷): clicar abre a página dela;
//   · o painel Cenas (botão Cenas da barra): a lista, a cena nova pela vista atual ou pela foto, e a cena escolhida —
//     nome, o que ela guarda (câmera; camadas, sistemas e piso; estilo: Pintar, arestas e sol), Atualizar, Apagar.
//
// Os dados ficam no projeto, junto das cenas por foto (saida/cenas.py, `tipo: "3d"`). O que se lê e se aplica da tela
// (camadas, Pintar, sol…) é do ver3d.js (`estado` e `aplicar`, passados em ligarCenas3d); aqui só a câmera.

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// a cena que espera o modo ver abrir: o 3D da outra situação da cobertura, ou a cena do 3D escolhida na página da foto
const CHAVE_PENDENTE = 'metalica.cena3dPendente';
const CHAVE_ABRIR = 'metalica.cenas3dAbrir';          // o painel Cenas pedido pelo menu da barra de cima

export function ligarCenas3d(ctx) {
  const { visor, projeto } = ctx;
  const API = `/api/projetos/${encodeURIComponent(projeto)}/terreno/cenas`;
  let cenas = [];
  let ativa = null;                                   // id da cena aplicada por último (a aba em destaque)
  let animacao = 0;

  async function pedir(url, corpo) {
    const r = await fetch(url, corpo === undefined ? { cache: 'no-store' }
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
    return j;
  }
  const falhou = (e) => { ctx.situacao(`Cenas: ${e.message || e}`); };

  /** A caixa de pergunta da tela (o prompt/confirm do navegador trava o quadro da área de trabalho): com `valor`, pede um
   *  texto e devolve ele (ou null); sem, devolve true/false. Enter confirma, Esc cancela. */
  function caixa({ titulo, texto = '', valor, ok = 'OK' }) {
    return new Promise((fim) => {
      const fundo = document.createElement('div');
      fundo.id = 'caixa-cena';
      fundo.innerHTML = `<div class="caixa" role="dialog" aria-label="${esc(titulo)}"><b>${esc(titulo)}</b>
        ${texto ? `<p>${esc(texto)}</p>` : ''}${valor !== undefined ? `<input type="text" value="${esc(valor)}">` : ''}
        <div class="botoes-cena"><button type="button" class="forte" data-r="ok">${esc(ok)}</button><button type="button" data-r="nao">Cancelar</button></div></div>`;
      document.body.append(fundo);
      const campo = fundo.querySelector('input');
      const sair = (sim) => { fundo.remove(); fim(valor !== undefined ? (sim ? campo.value.trim() || null : null) : !!sim); };
      fundo.querySelector('[data-r=ok]').onclick = () => sair(true);
      fundo.querySelector('[data-r=nao]').onclick = () => sair(false);
      fundo.onpointerdown = (ev) => { if (ev.target === fundo) sair(false); };
      fundo.onkeydown = (ev) => { ev.stopPropagation(); if (ev.key === 'Enter') sair(true); else if (ev.key === 'Escape') sair(false); };
      if (campo) { campo.focus(); campo.select(); } else fundo.querySelector('[data-r=ok]').focus();
    });
  }

  // ---------------------------------------------------------------- as abas

  const abas = document.createElement('div');
  abas.id = 'abas-cenas';
  abas.setAttribute('role', 'tablist');
  document.body.append(abas);

  function desenharAbas() {
    abas.replaceChildren();
    cenas.forEach((c, k) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'aba-cena' + (c.tipo === '3d' ? '' : ' aba-foto') + (c.id === ativa ? ' ativa' : '');
      b.dataset.cena = c.id;
      b.textContent = (c.tipo === '3d' ? '' : '📷 ') + c.nome;
      b.title = c.tipo === '3d'
        ? `Ir para a cena${k < 9 ? ` (Alt+${k + 1})` : ''} · botão direito: renomear, atualizar, mover, apagar`
        : 'Cena pela foto do local: abre a página dela · botão direito: mover, apagar';
      b.onclick = () => irPara(c);
      b.oncontextmenu = (ev) => { ev.preventDefault(); menuDaAba(c, b); };
      abas.append(b);
    });
    const mais = document.createElement('button');
    mais.type = 'button';
    mais.className = 'aba-cena aba-mais';
    mais.textContent = '+ Cena';
    mais.title = 'Gravar a vista atual como uma cena (Alt+0)';
    mais.onclick = () => novaCena();
    abas.append(mais);
  }

  async function carregar() {
    try { cenas = (await pedir(API)).cenas || []; } catch (e) { cenas = []; }
    if (ativa && !cenas.some(c => c.id === ativa)) ativa = null;
    desenharAbas();
    if (ctx.painelAtual() === 'cenas') painel();
  }

  // ---------------------------------------------------------------- ir para uma cena

  /** A câmera anda até a da cena em ~0,6 s (o alvo e a posição juntos, suave no começo e no fim). */
  function andarCamera(cam, instantaneo) {
    cancelAnimationFrame(animacao);
    const de = visor.lerCamera();
    const para = { posicao: cam.posicao, alvo: cam.alvo, fov: cam.fov || de.fov };
    const fim = () => { visor.camera.fov = para.fov; visor.camera.updateProjectionMatrix(); visor.definirCamera(para); };
    if (instantaneo || matchMedia('(prefers-reduced-motion: reduce)').matches) { fim(); return; }
    const t0 = performance.now(), dur = 600;
    const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
    const passo = (agora) => {
      const u = Math.min(1, (agora - t0) / dur), t = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      if (u >= 1) { fim(); return; }
      visor.camera.fov = de.fov + (para.fov - de.fov) * t;
      visor.camera.updateProjectionMatrix();
      visor.definirCamera({ posicao: mix(de.posicao, para.posicao, t), alvo: mix(de.alvo, para.alvo, t) });
      animacao = requestAnimationFrame(passo);
    };
    animacao = requestAnimationFrame(passo);
  }

  function irPara(c, instantaneo = false) {
    if (!c) return;
    if (c.tipo !== '3d') {                         // a cena por foto: a página dela (no mesmo quadro)
      location.href = `/visor3d/cena.html?projeto=${encodeURIComponent(projeto)}&cena=${encodeURIComponent(c.id)}`;
      return;
    }
    // a outra situação da cobertura retrátil: o 3D dela abre de novo e a cena se aplica depois
    if (c.situacao && c.situacao !== ctx.cobertura() && ctx.trocarCobertura) {
      try { sessionStorage.setItem(CHAVE_PENDENTE, JSON.stringify({ projeto, id: c.id })); } catch (e) { /* sem armazenamento */ }
      if (ctx.trocarCobertura(c.situacao)) return;
    }
    ativa = c.id;
    const g = c.guarda || {};
    if (g.camera !== false && c.camera) andarCamera(c.camera, instantaneo);
    ctx.aplicar(c);
    desenharAbas();
    if (ctx.painelAtual() === 'cenas') painel();
    ctx.situacao(`Cena ${c.nome}.`);
  }

  // ---------------------------------------------------------------- criar, atualizar, renomear, mover, apagar

  async function novaCena(nome) {
    if (nome === undefined) {
      nome = await caixa({ titulo: 'Nova cena', texto: 'Grava a vista atual: a câmera, as camadas, o Pintar, as arestas e o sol.',
        valor: `Cena ${cenas.filter(c => c.tipo === '3d').length + 1}`, ok: 'Gravar' });
      if (nome === null) return null;
    }
    try {
      const c = await pedir(`${API}/nova-3d`, { nome: String(nome).trim(), ...ctx.estado() });
      ativa = c.id;
      await carregar();
      ctx.situacao(`Cena ${c.nome} gravada: a aba fica no rodapé.`);
      return c;
    } catch (e) { falhou(e); return null; }
  }

  async function atualizar(c) {
    try {
      const n = await pedir(`${API}/${encodeURIComponent(c.id)}`, ctx.estado());
      ativa = n.id;
      await carregar();
      ctx.situacao(`Cena ${n.nome} atualizada com a vista atual.`);
      return n;
    } catch (e) { falhou(e); return null; }
  }

  async function gravarCampos(c, campos) {
    try { await pedir(`${API}/${encodeURIComponent(c.id)}`, campos); await carregar(); } catch (e) { falhou(e); }
  }

  async function renomear(c) {
    const nome = await caixa({ titulo: 'Renomear a cena', valor: c.nome, ok: 'Renomear' });
    if (!nome || nome === c.nome) return;
    await gravarCampos(c, { nome });
  }

  async function mover(c, passo) {
    const ids = cenas.map(x => x.id), k = ids.indexOf(c.id), j = k + passo;
    if (k < 0 || j < 0 || j >= ids.length) return;
    [ids[k], ids[j]] = [ids[j], ids[k]];
    try { cenas = (await pedir(`${API}/ordem`, { ids })).cenas; desenharAbas(); if (ctx.painelAtual() === 'cenas') painel(); } catch (e) { falhou(e); }
  }

  async function apagar(c, perguntar = true) {
    if (perguntar && !(await caixa({ titulo: 'Apagar a cena', texto: `Apagar a cena "${c.nome}"? O modelo não muda.`, ok: 'Apagar' }))) return;
    try {
      await pedir(`${API}/${encodeURIComponent(c.id)}/apagar`, {});
      if (ativa === c.id) ativa = null;
      await carregar();
      ctx.situacao(`Cena ${c.nome} apagada.`);
    } catch (e) { falhou(e); }
  }

  // o menu do botão direito na aba
  let menu = null;
  function fecharMenu() { if (menu) { menu.remove(); menu = null; } }
  function menuDaAba(c, aba) {
    fecharMenu();
    menu = document.createElement('div');
    menu.id = 'menu-cena';
    const itens = (c.tipo === '3d' ? [['Ir para a cena', () => irPara(c)], ['Atualizar com a vista atual', () => atualizar(c)],
      ['Renomear…', () => renomear(c)]] : [['Abrir a cena', () => irPara(c)]])
      .concat([['Mover para a esquerda', () => mover(c, -1)], ['Mover para a direita', () => mover(c, +1)], ['Apagar…', () => apagar(c)]]);
    for (const [texto, fazer] of itens) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = texto;
      b.dataset.acao = texto;
      b.onclick = () => { fecharMenu(); fazer(); };
      menu.append(b);
    }
    document.body.append(menu);
    const r = aba.getBoundingClientRect();
    menu.style.left = `${Math.min(r.left, innerWidth - menu.offsetWidth - 8)}px`;
    menu.style.top = `${r.top - menu.offsetHeight - 4}px`;
    setTimeout(() => document.addEventListener('pointerdown', function fora(ev) {
      if (menu && !menu.contains(ev.target)) { fecharMenu(); document.removeEventListener('pointerdown', fora, true); }
    }, true), 0);
  }

  // ---------------------------------------------------------------- o painel Cenas

  const GUARDA = [['camera', 'Câmera (posição, alvo e lente)'], ['camadas', 'Camadas, sistemas e a planta no piso'],
    ['estilo', 'Estilo: Pintar, arestas, sol e sombra']];

  function painel() {
    const atual = cenas.find(c => c.id === ativa && c.tipo === '3d');
    const lista = cenas.length ? cenas.map(c => `<label class="linha-lista linha-cena${c.id === ativa ? ' ativa' : ''}" data-ir="${esc(c.id)}">
        <span>${c.tipo === '3d' ? '🎬' : '📷'} ${esc(c.nome)}</span><em>${c.tipo === '3d' ? '3D' : 'foto'}</em></label>`).join('')
      : '<p class="dica">Nenhuma cena ainda. Arrume a vista (câmera, camadas, Pintar, sol) e grave.</p>';
    const detalhe = atual ? `<p class="titulo-secao">Cena escolhida</p>
      <input type="text" id="cena-nome" value="${esc(atual.nome)}" aria-label="Nome da cena">
      <p class="titulo-secao">A cena guarda</p>
      ${GUARDA.map(([k, t]) => `<label class="linha-lista"><input type="checkbox" data-guarda="${k}" ${(atual.guarda || {})[k] !== false ? 'checked' : ''}><span>${t}</span></label>`).join('')}
      <div class="botoes-cena"><button type="button" class="forte" id="cena-atualizar">Atualizar com a vista atual</button>
        <button type="button" id="cena-apagar">Apagar</button></div>
      <p class="dica">Gravada em ${esc((atual.alterada || '').replace('T', ' ').slice(0, 16))}. Renderizar e pôr na prancha vêm nas próximas etapas.</p>` : '';
    ctx.abrirPainel('cenas', 'Cenas', `<div class="botoes-cena"><button type="button" class="forte" id="cena-nova">+ Nova cena pela vista atual</button>
        <button type="button" id="cena-foto" title="A estrutura encaixada numa foto do local">📷 Nova cena pela foto…</button>
        <button type="button" id="cena-tela" title="Criar, tratar (enquadramento, estilo, fundo, luz), renderizar e exportar as cenas">Abrir a tela das Cenas…</button></div>
      <p class="titulo-secao">Cenas da obra</p>${lista}${detalhe}
      <p class="dica">As cenas ficam nas abas do rodapé: um clique vai até a cena. Botão direito na aba: renomear, atualizar, mover, apagar.
        PageUp/PageDown: a anterior/seguinte.</p>`);
    const corpo = document.querySelector('#painel-corpo');
    corpo.querySelector('#cena-nova').onclick = () => novaCena();
    corpo.querySelector('#cena-foto').onclick = () => { location.href = `/visor3d/cena.html?projeto=${encodeURIComponent(projeto)}`; };
    // a tela das Cenas (11/11, amostra-4) na janela inteira: três colunas não cabem no quadro do 3D da área de trabalho
    corpo.querySelector('#cena-tela').onclick = () => {
      const url = `/visor3d/cena.html?projeto=${encodeURIComponent(projeto)}${ativa ? `&cena=${encodeURIComponent(ativa)}` : ''}`;
      try { window.top.location.href = url; } catch (e) { location.href = url; }
    };
    corpo.querySelectorAll('[data-ir]').forEach(el => { el.onclick = () => irPara(cenas.find(c => c.id === el.dataset.ir)); });
    if (atual) {
      const nome = corpo.querySelector('#cena-nome');
      nome.onchange = () => { if (nome.value.trim() && nome.value.trim() !== atual.nome) gravarCampos(atual, { nome: nome.value.trim() }); };
      nome.onkeydown = (ev) => { if (ev.key === 'Enter') nome.blur(); };
      corpo.querySelectorAll('input[data-guarda]').forEach(cb => { cb.onchange = () => gravarCampos(atual, { guarda: { [cb.dataset.guarda]: cb.checked } }); });
      corpo.querySelector('#cena-atualizar').onclick = () => atualizar(atual);
      corpo.querySelector('#cena-apagar').onclick = () => apagar(atual);
    }
  }

  function alternarPainel() {
    if (ctx.painelAtual() === 'cenas') ctx.fecharPainel(); else painel();
  }

  // ---------------------------------------------------------------- teclado

  document.addEventListener('keydown', (ev) => {
    const t = ev.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA')) return;
    const so3d = cenas.filter(c => c.tipo === '3d');              // a de foto troca de página: fica fora do PageUp/PageDown
    if ((ev.key === 'PageDown' || ev.key === 'PageUp') && so3d.length) {
      ev.preventDefault();
      const k = so3d.findIndex(c => c.id === ativa);
      const j = ev.key === 'PageDown' ? (k + 1) % so3d.length : (k <= 0 ? so3d.length - 1 : k - 1);
      irPara(so3d[j]);
      return;
    }
    const m = ev.altKey && !ev.ctrlKey && !ev.metaKey && !ev.shiftKey && /^(?:Digit|Numpad)([0-9])$/.exec(ev.code || '');
    if (!m) return;
    ev.preventDefault();
    const n = +m[1];
    if (n === 0) { novaCena(); return; }
    if (cenas[n - 1]) irPara(cenas[n - 1]);
    else ctx.situacao(cenas.length ? `Não há cena ${n}: a obra tem ${cenas.length}.` : 'Nenhuma cena: Alt+0 grava a vista atual.');
  });

  // ---------------------------------------------------------------- abrir

  const pronto = carregar().then(() => {
    // a cena pedida antes de o 3D da outra situação da cobertura abrir
    let p = null;
    try { p = JSON.parse(sessionStorage.getItem(CHAVE_PENDENTE) || 'null'); sessionStorage.removeItem(CHAVE_PENDENTE); } catch (e) { p = null; }
    if (p && p.projeto === projeto) irPara(cenas.find(c => c.id === p.id), true);
    // o menu Cenas da barra de cima pediu o painel (ou a cena nova) antes de o modo ver estar pronto (barra_unica.js)
    let pedido = null;
    try { pedido = JSON.parse(sessionStorage.getItem(CHAVE_ABRIR) || 'null'); sessionStorage.removeItem(CHAVE_ABRIR); } catch (e) { pedido = null; }
    if (pedido && pedido.projeto === projeto) { if (pedido.nova) novaCena(); else painel(); }
  });

  const api = { carregar, irPara, novaCena, atualizar, apagar, mover, renomear, alternarPainel, painel, pronto,
    lista: () => cenas.map(c => ({ ...c })), ativa: () => ativa };
  window.cenas3d = api;                              // os verificadores e a barra única
  return api;
}
