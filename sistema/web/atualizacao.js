// Botão "Atualizar" nas telas de trabalho: quando há versão mais nova publicada, aparece
// ao lado do botão Tema. Ao clicar, a tela grava o que estiver pendente
// (window.__antesDeAtualizar, que o editor 3D e o CAD definem), o servidor baixa e roda o
// instalador, e o programa fecha e reabre NA MESMA TELA (o servidor guarda o caminho).
// Só no programa instalado, na janela própria; sem internet, nada aparece.
(function () {
  async function json(url, corpo) {
    const r = await fetch(url, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(corpo) } : undefined);
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  function el(tag, attrs, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'texto') e.textContent = v; else if (k === 'onclick') e.addEventListener('click', v); else e.setAttribute(k, v); }
    for (const f of filhos) if (f) e.append(f);
    return e;
  }
  // Todas as janelas do programa gravam antes de atualizar: a que clicou pergunta quem
  // tem trabalho aberto (canal entre janelas do mesmo endereço), pede para gravar e espera
  // cada uma confirmar. Antes só a janela do clique gravava, e engolindo a falha.
  const canal = ('BroadcastChannel' in window) ? new BroadcastChannel('metalica-gravar') : null;
  const EU = Math.random().toString(36).slice(2);
  if (canal) {
    canal.onmessage = async (ev) => {
      const m = ev.data || {};
      if (m.de === EU || typeof window.__antesDeAtualizar !== 'function') return;
      if (m.tipo === 'quem') canal.postMessage({ tipo: 'eu', para: m.de, de: EU, tela: document.title || location.pathname });
      if (m.tipo === 'atualizando') { veu(m.versao); esperarVoltar(m.atual); }
      if (m.tipo === 'gravar' && m.para === EU) {
        try { await window.__antesDeAtualizar(); canal.postMessage({ tipo: 'gravado', para: m.de, de: EU, ok: true }); }
        catch (e) { canal.postMessage({ tipo: 'gravado', para: m.de, de: EU, ok: false, erro: String(e && e.message || e), tela: document.title || location.pathname }); }
      }
    };
  }
  function veu(versaoNova) {
    document.body.append(el('div', { id: 'veu-atualizacao', style: 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(10,16,26,.82);color:#fff;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px' },
      el('div', {}, el('div', { style: 'font-size:22px;font-weight:600;margin-bottom:8px', texto: `Instalando a versão ${versaoNova}…` }),
                    el('div', { texto: 'Esta janela volta sozinha para onde estava quando a instalação terminar (uns 20 segundos). Se não voltar em dois minutos, abra o Metálica pelo atalho.' }))));
  }
  // O servidor novo responde na mesma porta: quando a versão muda, a tela recarrega no
  // mesmo lugar — é a mesma janela de antes, não uma nova (o programa reaberto vê o sinal
  // de vida dela e não abre outra).
  function esperarVoltar(versaoAtual) {
    const inicio = Date.now();
    const t = setInterval(async () => {
      if (Date.now() - inicio > 5 * 60 * 1000) { clearInterval(t); return; }
      try {
        const r = await fetch('/api/versao', { cache: 'no-store' });
        const v = await r.json();
        if (v && v.versao && v.versao !== versaoAtual) { clearInterval(t); location.reload(); }
      } catch (e) { /* ainda instalando */ }
    }, 2000);
  }
  async function gravarTodasAsJanelas() {
    if (typeof window.__antesDeAtualizar === 'function') await window.__antesDeAtualizar();     // esta janela
    if (!canal) return;
    const outras = new Map();
    const ouvir = (ev) => { const m = ev.data || {}; if (m.para === EU && m.tipo === 'eu') outras.set(m.de, m.tela); };
    canal.addEventListener('message', ouvir);
    canal.postMessage({ tipo: 'quem', de: EU });
    await new Promise(r => setTimeout(r, 800));
    canal.removeEventListener('message', ouvir);
    if (!outras.size) return;
    const falhas = [];
    await new Promise((resolve) => {
      const faltam = new Set(outras.keys());
      const fim = setTimeout(() => { for (const j of faltam) falhas.push(`${outras.get(j)}: não respondeu`); resolve(); }, 120000);
      const resp = (ev) => {
        const m = ev.data || {};
        if (m.para !== EU || m.tipo !== 'gravado' || !faltam.has(m.de)) return;
        faltam.delete(m.de);
        if (!m.ok) falhas.push(`${m.tela || outras.get(m.de)}: ${m.erro}`);
        if (!faltam.size) { clearTimeout(fim); canal.removeEventListener('message', resp); resolve(); }
      };
      canal.addEventListener('message', resp);
      for (const j of outras.keys()) canal.postMessage({ tipo: 'gravar', para: j, de: EU });
    });
    if (falhas.length) throw new Error('outra janela não gravou — ' + falhas.join('; '));
  }

  async function verificar() {
    let v, a;
    try { v = await json('/api/versao'); if (!v.janela || !v.instalado) return; a = await json('/api/atualizacao'); } catch { return; }
    if (!a || !a.nova || !a.arquivo || document.getElementById('btn-atualizar')) return;
    const tema = document.getElementById('btn-tema');
    if (!tema) return;
    const botao = el('button', { type: 'button', id: 'btn-atualizar', class: tema.className || 'botao',
                                 title: `Versão ${a.ultima} disponível (esta é a ${a.atual}). Salva o trabalho, instala e reabre nesta mesma tela.`,
                                 texto: `Atualizar → ${a.ultima}` });
    botao.style.cssText = 'border-color:#e6bb52;color:#e6bb52;font-weight:600';
    botao.addEventListener('click', async () => {
      if (!window.confirm(`Instalar a versão ${a.ultima} agora?\n\nO trabalho aberto é gravado antes; o programa fecha e reabre nesta mesma tela (leva uns 20 segundos).`)) return;
      botao.disabled = true; botao.textContent = 'Gravando…';
      try {
        try { await gravarTodasAsJanelas(); } catch (e) {
          // não gravou: a atualização não segue (antes seguia e a edição se perdia)
          botao.disabled = false; botao.textContent = `Atualizar → ${a.ultima}`;
          window.alert('A atualização foi cancelada porque o trabalho aberto não pôde ser gravado: ' + e.message + '\n\nGrave de novo (ou feche o que não precisa) e tente outra vez.');
          return;
        }
        botao.textContent = 'Baixando…';
        const r = await json('/api/atualizacao/instalar', { reabrir: location.pathname + location.search });
        veu(r.versao);
        esperarVoltar(a.atual);
        if (canal) canal.postMessage({ tipo: 'atualizando', de: EU, versao: r.versao, atual: a.atual });
      } catch (e) {
        botao.disabled = false; botao.textContent = `Atualizar → ${a.ultima}`;
        window.alert('Não foi possível atualizar: ' + e.message);
      }
    });
    tema.before(botao);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(verificar, 1500)); else setTimeout(verificar, 1500);
  setInterval(verificar, 15 * 60 * 1000);
  // a tela fica aberta o dia inteiro: pergunta também quando a janela volta ao foco
  // (no máximo a cada 5 minutos; o servidor guarda a resposta do GitHub)
  let ultimaVez = Date.now();
  window.addEventListener('focus', () => { if (Date.now() - ultimaVez > 5 * 60 * 1000) { ultimaVez = Date.now(); verificar(); } });
})();
