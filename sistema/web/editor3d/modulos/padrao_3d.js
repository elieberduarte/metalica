// O 3D é a peça (regra combinada com o usuário, 02/10): as regras de fábrica (furação da máquina, oblongos, suporte
// de terça no passo da máquina, furo da terça no furo da chapa) vão para o modelo, e o desenho só mostra o 3D. A
// atualização automática dos desenhos grava o modelo sozinha — menos com este editor aberto, que perderia a edição:
// aí o servidor deixa o padrão pendente e esta faixa oferece "Aplicar no 3D". O editor avisa que está aberto pelo
// mesmo pedido (desenhos-vivos?editor=1), a cada poucos segundos.

import { el } from '../editor.js';

const INTERVALO = 10000;

export class MetodosPadrao3D {
  /** Começa o sinal de "editor aberto" e a conferência do padrão pendente (só em projeto). */
  _iniciarSinalDoEditor() {
    if (!this.projeto || this._sinalEditor) return;
    const tique = () => this._sinalDoEditor().catch(() => {});
    tique();
    this._sinalEditor = setInterval(tique, INTERVALO);
  }

  async _sinalDoEditor() {
    const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos-vivos?editor=1`);
    if (!r.ok) return;
    const e = await r.json();
    this._mostrarPendente3D((e && e.pendente_3d) || {});
  }

  _mostrarPendente3D(p) {
    const pos = p.posicoes || [];
    if (!pos.length) { if (this._faixaPadrao) { this._faixaPadrao.remove(); this._faixaPadrao = null; } return; }
    const texto = `O 3D está fora do padrão de fábrica em ${pos.length} posição(ões): ${pos.slice(0, 8).join(', ')}` +
      `${pos.length > 8 ? '…' : ''}. Os desenhos mostram o 3D como está; as pranchas só saem depois de aplicar.`;
    if (this._faixaPadrao) { this._faixaPadrao.querySelector('span').textContent = texto; return; }
    const botao = el('button', { texto: 'Aplicar no 3D', title: 'Grava a sua edição, aplica o padrão de fábrica no modelo e recarrega' });
    botao.style.cssText = 'background:#fff;color:#92400e;border:0;border-radius:4px;padding:4px 10px;font-weight:600;cursor:pointer';
    botao.addEventListener('click', () => this.aplicarPadraoNo3D());
    const f = el('div', { class: 'faixa-padrao-3d' }, el('span', { texto }), botao);
    f.style.cssText = 'position:fixed;left:50%;top:64px;transform:translateX(-50%);z-index:50;display:flex;gap:12px;' +
      'align-items:center;max-width:80vw;background:#b45309;color:#fff;padding:6px 12px;border-radius:6px;' +
      'font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.25)';
    document.body.append(f);
    this._faixaPadrao = f;
  }

  /** Grava o que está pendente aqui, manda o servidor aplicar o padrão no modelo e recarrega o modelo. */
  async aplicarPadraoNo3D() {
    if (!this.projeto) return;
    try {
      this.dica('Gravando a sua edição e aplicando o padrão de fábrica no 3D…');
      if (this._autosavePendente || this._autosalvando) await this.salvar();
      const r = await fetch(`/api/projetos/${encodeURIComponent(this.projeto)}/desenhos-vivos/aplicar-3d`, {
        method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: '{}',
      });
      const j = await r.json();
      if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
      const m = await this.api.modeloDoProjeto(this.projeto);
      this._modeloAlterado = m && m.alterado ? m.alterado : null;
      this.carregarDocumento(m.documento, { enquadrar: false, autosalvar: false });
      this._mostrarPendente3D({});
      this.aviso(j.mudou ? `Padrão de fábrica aplicado no 3D: ${(j.posicoes || []).join(', ')}. Os desenhos se refazem em seguida.`
                         : 'O 3D já estava no padrão de fábrica.', 'info', 12000);
      this.dica('');
    } catch (e) { this.aviso(`Não foi possível aplicar no 3D: ${e.message}`, 'erro', 0); this.dica(''); }
  }
}
