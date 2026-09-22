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
        if (typeof window.__antesDeAtualizar === 'function') { try { await window.__antesDeAtualizar(); } catch (e) { console.warn('gravação antes de atualizar:', e); } }
        botao.textContent = 'Baixando…';
        const r = await json('/api/atualizacao/instalar', { reabrir: location.pathname + location.search });
        const veu = el('div', { style: 'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(10,16,26,.82);color:#fff;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px' },
          el('div', {}, el('div', { style: 'font-size:22px;font-weight:600;margin-bottom:8px', texto: `Instalando a versão ${r.versao}…` }),
                        el('div', { texto: 'O programa fecha e reabre sozinho nesta mesma tela. Se não voltar em um minuto, abra o Metálica pelo atalho.' })));
        document.body.append(veu);
      } catch (e) {
        botao.disabled = false; botao.textContent = `Atualizar → ${a.ultima}`;
        window.alert('Não foi possível atualizar: ' + e.message);
      }
    });
    tema.before(botao);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(verificar, 1500)); else setTimeout(verificar, 1500);
  setInterval(verificar, 30 * 60 * 1000);
})();
