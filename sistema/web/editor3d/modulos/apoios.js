// Métodos do editor 3D: Ver → Verificar apoios.
//
// As regras de qualquer estrutura, conferidas no servidor (nucleo3d/apoios.py): nenhuma
// peça voando, treliça apoiada em pilar ou em outra peça, terça apoiada nas pontas e sobre
// os nós, pilar com o que carregar, viga apoiada nas duas pontas. O painel lista os
// achados por regra; clicar num achado seleciona as peças e enquadra a câmera nelas.

import { el } from '../editor.js';

const REGRAS = [
  ['voando', 'Peças voando (sem ligação até a base)'],
  ['ponta_sem_apoio', 'Ponta de treliça sem apoio'],
  ['ponta_em_diagonal', 'Ponta de treliça ligada em diagonal, não num nó'],
  ['terca_sem_apoio', 'Terça sem apoio'],
  ['terca_em_balanco', 'Terça passando do último apoio'],
  ['viga_sem_apoio', 'Viga com a ponta sem apoio'],
  ['pilar_sem_carga', 'Pilar sem peça em cima'],
  ['trelica_dentro', 'Treliça passando por dentro de outra'],
  ['plano_sem_contravento', 'Telhado sem contravento no plano'],
  ['pilar_fora_da_linha', 'Pilar fora da linha da peça que carrega'],
  ['pilar_fora_do_eixo', 'Pilar fora do eixo (locação × eixos — conferir com o projeto)'],
  ['terca_fora_do_no', 'Terça fora do nó da treliça'],
  // a conferência do 3D (nucleo3d/conferencia_3d.py, 12/10/2026)
  ['repetida', 'Peça repetida (duas no mesmo lugar)'],
  ['choque', 'Peças se atravessando'],
  ['telha_degrau', 'Telha: degrau entre chapas vizinhas'],
  ['telha_dobra', 'Telha: dobra na caída (terça fora da reta)'],
  // as regras de posição das peças da treliça (nucleo3d/regras_trelica.py, 16/10/2026)
  ['posicao_trelica', 'Peça da treliça fora da regra (boca do U, lado da cantoneira, encaixe, degrau, nó fora do eixo, terça torcida)'],
  // as regras da cobertura (nucleo3d/conferencia_3d.cobertura, 19/10/2026)
  ['cobertura_borda_aberta', 'Cobertura: borda de telhado aberta (sem calha, rufo nem fechamento)'],
  ['cobertura_sem_rufo', 'Cobertura: telha encostada na parede sem rufo'],
  ['cobertura_choque', 'Cobertura: calha ou rufo atravessando peça'],
  // a cobertura sem fresta nem buraco (COB-01 do catálogo sistema/testes/REGRAS.md, 21/10/2026)
  ['cobertura_buraco', 'Cobertura: buraco (telhado sem telha, calha nem rufo)'],
  ['cobertura_fresta', 'Cobertura: fresta entre chapas'],
];

export class MetodosApoios {
  async verificarApoios() {
    if (!this.documento.tamanho) { this.aviso('O modelo está vazio.', 'atencao'); return; }
    this.dica('Conferindo os apoios…');
    let r;
    try {
      r = await this.api.apoios(this.documento.paraJSON(), this._eixosRef);
    } catch (e) {
      this.aviso(`Não foi possível conferir os apoios: ${e.message}`, 'erro');
      return;
    }
    this._mostrarApoios(r);
  }

  /** As peças das treliças fora das regras de montagem (posicao_trelica): o modelo inteiro passa pelas regras no servidor
   *  (nucleo3d/regras_trelica.corrigir_modelo) — sem remontar, com as edições do 3D mantidas — numa entrada de desfazer,
   *  e o Verificar apoios roda de novo (17/10: os modelos antigos acusavam até serem remontados). */
  async corrigirPelasRegras() {
    this.dica('Corrigindo pelas regras das tesouras…');
    let r;
    try {
      const resp = await fetch('/api/modelo/regras-trelica', { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ documento: this.documento.paraJSON() }) });
      r = await resp.json();
      if (!resp.ok || r.erro) throw new Error(r.erro || resp.statusText);
    } catch (e) { this.aviso(`Corrigir pelas regras: ${e.message}`, 'erro', 0); return; }
    const s = r.resumo || {};
    if (!Object.keys(r.alterar || {}).length && !(r.remover || []).length) {
      this.aviso('Corrigir pelas regras: o modelo já está dentro das regras das tesouras.', 'info');
      return;
    }
    await this._numerarAsNovas(r);                    // a peça que mudou de perfil (ponta, topo do painel) é conferida
    const cmd = this._comandoDaLigacao(r, 'Corrigir pelas regras das tesouras');
    if (cmd) this.executar(cmd);
    this.aviso(`Corrigir pelas regras: ${s.pecas || 0} peça(s) — ${s.giradas || 0} girada(s), ${s.reclassificadas || 0} reclassificada(s), ` +
      `${s.recuadas || 0} recuada(s) da platibanda, ${s.encaixadas || 0} encaixada(s) no banzo` +
      (s.trechos_tirados ? `, ${s.trechos_tirados} trecho(s) dentro do banzo tirado(s)` : '') + '. Ctrl+Z desfaz.' +
      ((r.avisos || []).length ? ' ' + r.avisos.join('; ') + '.' : ''), (r.avisos || []).length ? 'atencao' : 'info', 15000);
    await this.verificarApoios();
  }

  _fecharApoios() {
    if (this._painelApoios) { this._painelApoios.remove(); this._painelApoios = null; }
  }

  _mostrarApoios(r) {
    this._fecharApoios();
    const achados = r.achados || [];
    const z = r.resumo || {};
    const verAchado = (a) => {
      const ids = (a.ids || []).filter(id => this.documento.entidades.has(id));
      if (!ids.length) { this.aviso('As peças desse achado não estão mais no modelo.', 'atencao'); return; }
      this.selecao.definir(ids);
      this.cena.destacar(ids);
      this._destaqueAtivo = true;
      this.camera.zoomSelecao(ids);
      this.dica(`${a.texto} — (${a.ponto.map(v => (v / 1000).toFixed(2)).join('; ')}) m. Esc limpa a seleção.`);
    };
    const corpo = el('div', { class: 'painel-apoios-corpo' });
    const cabeca = el('p', {
      texto: achados.length
        ? `${achados.length.toLocaleString('pt-BR')} achado(s) em ${(z.pecas || 0).toLocaleString('pt-BR')} peças. ` +
          `Pontas de treliça apoiadas: ${z.pontas_apoiadas || 0} de ${z.pontas_trelica || 0}; terças sem nada a apontar: ` +
          `${z.tercas_ok || 0} de ${z.tercas || 0}.`
        : 'Nenhum achado: toda peça chega à base, as treliças e vigas apoiam nas pontas e as terças nos nós.',
    });
    corpo.append(cabeca);
    for (const [regra, titulo] of REGRAS) {
      const lista = achados.filter(a => a.regra === regra);
      if (!lista.length) continue;
      const det = el('details', { open: !['terca_fora_do_no', 'pilar_fora_do_eixo'].includes(regra) && lista.length <= 40 });
      det.append(el('summary', { texto: `${titulo} (${lista.length})` }));
      const ul = el('ul');
      for (const a of lista.slice(0, 400)) {
        ul.append(el('li', { texto: a.texto, title: 'Selecionar e enquadrar', onclick: () => verAchado(a) }));
      }
      if (lista.length > 400) ul.append(el('li', { class: 'mais', texto: `… e mais ${lista.length - 400}` }));
      det.append(ul);
      corpo.append(det);
    }
    this._painelApoios = el('div', { class: 'painel-apoios' },
      el('div', { class: 'painel-apoios-titulo' },
        el('strong', { texto: 'Verificar apoios' }),
        el('button', { type: 'button', texto: 'Conferir de novo', onclick: () => this.verificarApoios() }),
        achados.some(a => a.regra === 'posicao_trelica')
          ? el('button', { type: 'button', class: 'corrigir-regras', texto: 'Corrigir pelas regras',
                           title: 'Gira, encaixa e recua as peças das treliças pelas regras de montagem das tesouras, no modelo como está (sem remontar). Ctrl+Z desfaz.',
                           onclick: () => this.corrigirPelasRegras() })
          : null,
        el('button', { type: 'button', texto: '×', title: 'Fechar', onclick: () => this._fecharApoios() })),
      corpo);
    (this.el.palco || document.body).append(this._painelApoios);
  }
}
