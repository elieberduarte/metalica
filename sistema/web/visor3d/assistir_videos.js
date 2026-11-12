// Os vídeos da obra, assistidos dentro do sistema (usuário, 12/11: "quero assistir dentro do sistema" — antes só tocava o
// vídeo recém-gravado, na janela do Exportar; os de antes ficavam na pasta cenas/ e abriam pelo 📁). A janela lista os MP4 da
// pasta cenas/ da obra (o mais novo primeiro, com a hora, a duração e o tamanho) e toca o escolhido ao lado.
//
// O vídeo vem inteiro do servidor e toca da memória (blob): o servidor do programa não responde por partes (Range), e sem
// isso o <video> não pula no tempo; com o blob a barra do player anda para qualquer ponto.

const ESTILO = `
#videos-fundo { position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; background: rgba(15, 22, 32, .45); }
#videos-caixa { width: min(1100px, calc(100vw - 32px)); height: min(680px, calc(100vh - 32px)); display: flex; flex-direction: column;
  background: var(--painel); color: var(--texto); border: 1px solid var(--borda); border-radius: 10px; box-shadow: 0 12px 40px rgba(0,0,0,.35); overflow: clip; }
#videos-caixa > header { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--borda); flex: none; }
#videos-caixa > header b { flex: 1; font-size: 15px; }
#videos-caixa > header button { border: 0; background: none; font-size: 18px; padding: 0 6px; }
#videos-caixa .videos-corpo { display: grid; grid-template-columns: 280px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); flex: 1 1 0; min-height: 0; }
#videos-lista { overflow: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; border-right: 1px solid var(--borda); }
#videos-lista button { text-align: left; display: flex; flex-direction: column; gap: 2px; padding: 7px 9px; border: 1px solid var(--borda);
  border-radius: 6px; background: var(--painel); color: var(--texto); cursor: pointer; }
#videos-lista button:hover { border-color: var(--azul2, #1f5fbf); }
#videos-lista button.sel { border-color: var(--azul2, #1f5fbf); box-shadow: 0 0 0 1px var(--azul2, #1f5fbf); }
#videos-lista button b { font-weight: 600; font-size: 12.5px; overflow-wrap: anywhere; }
#videos-lista button small, #videos-caixa .fraco { color: var(--texto2); font-size: 11.5px; }
#videos-palco { display: flex; align-items: center; justify-content: center; background: #000; min-width: 0; min-height: 0; position: relative; }
#videos-player { max-width: 100%; max-height: 100%; width: 100%; height: 100%; background: #000; }
#videos-palco .vazio { color: #c9d2dd; font-size: 13px; padding: 20px; text-align: center; }
#videos-caixa > footer { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-top: 1px solid var(--borda); flex: none; }
#videos-situacao { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12.5px; }
@media (max-width: 700px) { #videos-caixa .videos-corpo { grid-template-columns: minmax(0, 1fr); grid-template-rows: 160px minmax(0, 1fr); }
  #videos-lista { border-right: 0; border-bottom: 1px solid var(--borda); } }
`;

/**
 * ctx: {
 *   api: o endereço das rotas das cenas (…/terreno/cenas)
 *   abrirPasta(nome): abre a pasta cenas/ no Explorador com o arquivo selecionado (Promise)
 * }
 */
export function ligarVideos(ctx) {
  if (!document.getElementById('videos-estilo')) {
    const s = document.createElement('style'); s.id = 'videos-estilo'; s.textContent = ESTILO; document.head.append(s);
  }
  let fundo = null, url = null, lista = [], vez = 0;
  const estado = window.videosCenas = { aberta: false, videos: 0, tocando: null, erro: null };

  function situacao(txt) { if (fundo) fundo.querySelector('#videos-situacao').textContent = txt || ''; }

  function soltar() {
    const v = fundo && fundo.querySelector('#videos-player');
    if (v) { v.pause(); v.removeAttribute('src'); v.load(); }
    if (url) { URL.revokeObjectURL(url); url = null; }
    estado.tocando = null;
  }

  function fechar() {
    vez++;
    soltar();
    if (fundo) { fundo.remove(); fundo = null; }
    estado.aberta = false;
  }

  async function tocar(nome) {
    const minha = ++vez, v = lista.find(x => x.nome === nome);
    if (!fundo || !v) return;
    for (const b of fundo.querySelectorAll('#videos-lista button')) b.classList.toggle('sel', b.dataset.nome === nome);
    soltar();
    const palco = fundo.querySelector('#videos-palco');
    palco.innerHTML = '<div class="vazio">Carregando o vídeo…</div>';
    fundo.querySelector('#videos-mostrar').disabled = false;
    situacao(`Carregando ${nome} (${mb(v.bytes)})…`);
    try {
      const r = await fetch(`${ctx.api}/videos/${encodeURIComponent(nome)}`, { cache: 'no-store' });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.erro || `erro ${r.status}`);
      }
      const blob = new Blob([await r.arrayBuffer()], { type: 'video/mp4' });
      if (minha !== vez || !fundo) return;                   // outro vídeo escolhido (ou a janela fechada) no meio
      url = URL.createObjectURL(blob);
      palco.innerHTML = '';
      const el = document.createElement('video');
      el.id = 'videos-player'; el.controls = true; el.muted = true; el.autoplay = true; el.playsInline = true; el.src = url;
      palco.append(el);
      estado.tocando = nome; estado.erro = null;
      situacao(`${nome} · ${quando(v.em)}${v.segundos ? ' · ' + duracao(v.segundos) : ''} · ${mb(v.bytes)}`);
      el.play().catch(() => {});                              // sem o autoplay liberado, o botão ▶ do player
    } catch (e) {
      if (minha !== vez || !fundo) return;
      estado.erro = e.message;
      palco.innerHTML = `<div class="vazio">O vídeo não abriu: ${esc(e.message)}</div>`;
      situacao('O vídeo não abriu: ' + e.message);
    }
  }

  async function carregarLista(escolher) {
    const caixa = fundo.querySelector('#videos-lista');
    caixa.innerHTML = '<span class="fraco">Procurando os vídeos…</span>';
    try {
      const r = await fetch(`${ctx.api}/videos`, { cache: 'no-store' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.erro) throw new Error(j.erro || `erro ${r.status}`);
      lista = j.videos || [];
    } catch (e) {
      caixa.innerHTML = `<span class="fraco">A lista não veio: ${esc(e.message)}</span>`;
      return;
    }
    if (!fundo) return;
    estado.videos = lista.length;
    if (!lista.length) {
      caixa.innerHTML = '<span class="fraco">Nenhum vídeo gravado nesta obra ainda.</span>';
      fundo.querySelector('#videos-palco').innerHTML = '<div class="vazio">Para fazer um: Exportar… › Vídeo MP4, com duas cenas do 3D ou mais.</div>';
      situacao('');
      return;
    }
    caixa.innerHTML = lista.map(v => `<button type="button" data-nome="${esc(v.nome)}" title="${esc(v.nome)}"><b>${esc(v.nome.replace(/\.mp4$/i, ''))}</b>`
      + `<small>${quando(v.em)}${v.segundos ? ' · ' + duracao(v.segundos) : ''} · ${mb(v.bytes)}</small></button>`).join('');
    const alvo = lista.find(v => v.nome === escolher) || lista[0];
    tocar(alvo.nome);
  }

  /** Abre a janela; `nome` = o vídeo que já começa tocando (sem = o mais novo). */
  function abrir(nome) {
    if (fundo) { carregarLista(nome); return; }
    fundo = document.createElement('div');
    fundo.id = 'videos-fundo';
    fundo.innerHTML = `<div id="videos-caixa" role="dialog" aria-label="Vídeos da obra">
      <header><b>Vídeos da obra</b><button type="button" id="videos-x" title="Fechar (Esc)">×</button></header>
      <div class="videos-corpo"><div id="videos-lista"></div><div id="videos-palco"></div></div>
      <footer><span id="videos-situacao"></span>
        <button type="button" id="videos-mostrar" disabled title="Abre a pasta cenas da obra com este vídeo selecionado">📁 Mostrar na pasta</button>
        <button type="button" id="videos-fechar">Fechar</button></footer></div>`;
    document.body.append(fundo);
    estado.aberta = true;
    fundo.querySelector('#videos-x').onclick = fechar;
    fundo.querySelector('#videos-fechar').onclick = fechar;
    fundo.querySelector('#videos-mostrar').onclick = () => {
      const sel = fundo.querySelector('#videos-lista button.sel');
      ctx.abrirPasta(sel ? sel.dataset.nome : '').catch(e => situacao('A pasta não abriu: ' + e.message));
    };
    fundo.querySelector('#videos-lista').addEventListener('click', (ev) => {
      const b = ev.target.closest('button[data-nome]');
      if (b && !b.classList.contains('sel')) tocar(b.dataset.nome);
    });
    // as teclas ficam na janela (o espaço do player não pode chegar aos atalhos da tela das Cenas)
    fundo.addEventListener('keydown', (ev) => { ev.stopPropagation(); if (ev.key === 'Escape') fechar(); });
    fundo.addEventListener('pointerdown', (ev) => { if (ev.target === fundo) fechar(); });
    fundo.querySelector('#videos-fechar').focus();
    carregarLista(nome);
  }

  return { abrir, fechar, aberta: () => !!fundo };
}

const nf = (v, c = 0) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const mb = (b) => (b < 1048576 ? `${nf(Math.max(1, b / 1024))} KB` : `${nf(b / 1048576, b < 10485760 ? 1 : 0)} MB`);
function duracao(s) {
  s = Math.round(s);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
}
function quando(iso) {
  const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso || '');
  return m ? `${m[3]}/${m[2]} ${m[4]}h${m[5]}` : '';
}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
