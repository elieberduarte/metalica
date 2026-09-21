// Barra estrutural: dois cliques definem o eixo, o perfil vem do painel.
//
// É a ferramenta que diferencia este editor de um modelador genérico: o que sai
// daqui não é um sólido, é uma `Barra` com perfil de catálogo, aço e papel — o
// desenho, o peso e o tipo IFC saem disso. Durante o traçado a seção aparece em
// prévia nas duas pontas; as setas cima/baixo trocam o perfil sem sair da
// ferramenta; ao terminar um segmento, o próximo começa do ponto final, para
// lançar um pórtico inteiro sem recomeçar.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

const PAPEIS = ['pilar', 'viga', 'terça', 'contraventamento', 'longarina', 'barra'];

export class FerramentaBarra extends Ferramenta {
  static id = 'barra';
  static nome = 'Barra';
  static atalho = 'B';
  static grupo = 'estrutura';
  static dica = 'Clique no início da barra';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 4.5h6M7 4.5v15M4 19.5h6"/><path d="M14 8.5h6M17 8.5v7M14 15.5h6"/><path d="M10.5 12h3" stroke-dasharray="2 1.5"/></svg>`;

  ativar() {
    this.inicio = null;
    this.atual = null;
    this.eixo = null;
    this.dica(this.dicaComPerfil('Clique no início da barra'));
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  // ------------------------------------------------------------- painel

  get perfis() { return C.perfisDoCatalogo(this.editor); }

  get perfilAtivo() {
    const e = this.editor || {};
    if (e.perfilAtivo) return e.perfilAtivo;
    const l = this.perfis;
    return l.length ? l[0].nome : 'W 310×38,7';
  }

  set perfilAtivo(nome) {
    if (!this.editor) return;
    if (typeof this.editor.definirPerfilAtivo === 'function') this.editor.definirPerfilAtivo(nome);
    else this.editor.perfilAtivo = nome;
  }

  get registroDoPerfil() {
    return this.perfis.find(p => p.nome === this.perfilAtivo) || null;
  }

  get acoAtivo() { return (this.editor && this.editor.acoAtivo) || 'ASTM A572 Gr.50'; }
  get papelAtivo() { return (this.editor && this.editor.papelAtivo) || 'viga'; }

  dicaComPerfil(texto) {
    return `${texto} — ${this.perfilAtivo} · ${this.papelAtivo} (↑↓ troca o perfil)`;
  }

  trocarPerfil(passo) {
    const l = this.perfis;
    if (!l.length) return;
    let i = l.findIndex(p => p.nome === this.perfilAtivo);
    if (i < 0) i = 0;
    i = (i + passo + l.length) % l.length;
    this.perfilAtivo = l[i].nome;
    this.desenhar();
    this.dica(this.dicaComPerfil(this.inicio ? 'Clique no fim da barra' : 'Clique no início da barra'));
  }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    this.atual = this.resolver(p.ponto);
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    const q = this.resolver(p.ponto);
    if (!this.inicio) {
      this.inicio = q;
      C.ancorar(this.editor, q);
      this.dica(this.dicaComPerfil('Clique no fim da barra ou digite o comprimento'));
      this.desenhar();
      return;
    }
    if (C.iguais(this.inicio, q, 1)) return;
    this.criar(this.inicio, q);
  }

  onValor(texto) {
    const t = String(texto).trim().toLowerCase();
    const mp = t.match(/^(pilar|viga|ter[çc]a|contraventamento|longarina|barra)$/);
    if (mp) {
      if (this.editor) this.editor.papelAtivo = mp[1] === 'terca' ? 'terça' : mp[1];
      this.dica(this.dicaComPerfil(this.inicio ? 'Clique no fim da barra' : 'Clique no início da barra'));
      return true;
    }
    if (!this.inicio) return false;
    const d = paraMilimetros(t);
    if (!isFinite(d) || d <= 0) return false;
    let dir = this.eixo ? C.EIXOS[this.eixo].vetor
            : (this.atual && !C.iguais(this.atual, this.inicio, 1e-6))
              ? C.sub(this.atual, this.inicio) : null;
    if (!dir) return false;
    dir = C.normalizar(dir);
    if (this.eixo && this.atual && C.dot(C.sub(this.atual, this.inicio), dir) < 0) dir = C.mul(dir, -1);
    this.criar(this.inicio, C.add(this.inicio, C.mul(dir, d)));
    return true;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (ev.key === 'ArrowUp') { this.trocarPerfil(+1); return true; }
    if (ev.key === 'ArrowDown') { this.trocarPerfil(-1); return true; }
    // ← e → travam X e Y (convenção da inferência do núcleo); ↑ e ↓ ficam para o perfil
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') { C.teclaDeEixo(this, ev); this.desenhar(); return true; }
    if (ev.key === 'PageUp' || ev.key === 'PageDown') {
      // papel estrutural, sem sair da ferramenta
      const i = PAPEIS.indexOf(this.papelAtivo);
      const j = (i + (ev.key === 'PageUp' ? 1 : -1) + PAPEIS.length) % PAPEIS.length;
      if (this.editor) this.editor.papelAtivo = PAPEIS[j];
      this.dica(this.dicaComPerfil('Papel: ' + PAPEIS[j]));
      return true;
    }
    if (ev.key === 'Enter') { this.reiniciar(); this.dica(this.dicaComPerfil('Clique no início da barra')); return true; }
    return false;
  }

  cancelar() {
    if (this.inicio) { this.reiniciar(); this.dica(this.dicaComPerfil('Clique no início da barra')); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- interno

  resolver(ponto) {
    if (!this.inicio || !this.eixo) return C.copiar(ponto);
    return C.projetarNoEixo(this.inicio, ponto, this.eixo);
  }

  /** Referencial da seção: eixo local Y horizontal, Z completando o triedro. */
  referencial(a, b) {
    const d = C.normalizar(C.sub(b, a));
    const ref = Math.abs(d[2]) > 0.98 ? [1, 0, 0] : [0, 0, 1];   // como baseDaBarra
    const ey = C.normalizar(C.cross(ref, d));
    const ez = C.normalizar(C.cross(d, ey));
    return { d, ey, ez };
  }

  criar(a, b) {
    const ent = {
      tipo: 'barra', id: C.novoId('b'),
      nome: '', camada: (this.editor && this.editor.camadaAtiva) || 'Estrutura',
      material: '', visivel: true, bloqueada: false, grupo: '',
      inicio: C.copiar(a), fim: C.copiar(b),
      perfil: this.perfilAtivo, rotacao: 0,
      papel: this.papelAtivo, aco: this.acoAtivo,
      recorte_inicio: 0, recorte_fim: 0, atributos: {},
    };
    this.executar(C.cmdAdicionar(ent, 'Criar barra'));
    // continua do ponto final, como a ferramenta de linha
    this.inicio = C.copiar(b);
    C.ancorar(this.editor, b);
    this.atual = null;
    this.limparPrevia();
    this.medida(`${formatar(C.dist(a, b))} · ${this.perfilAtivo}`);
    this.dica(this.dicaComPerfil('Continue a partir do fim, ou Enter/Esc para parar'));
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.inicio = null; this.atual = null; this.eixo = null;
    this.limparPrevia();
    this.medida('');
  }

  /** Contorno da seção transportado para uma estação do eixo. */
  secaoEm(ponto, ref, contorno) {
    return contorno.map(([u, v]) => C.add(ponto, C.add(C.mul(ref.ey, u), C.mul(ref.ez, v))));
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    if (this.inicio) g.add(C.gPonto(this.inicio, C.CORES.estrutura));
    if (!this.inicio || !this.atual) {
      if (this.atual) g.add(C.gPonto(this.atual, C.CORES.estrutura));
      this.previa(g);
      return;
    }
    const a = this.inicio, b = this.atual;
    if (C.iguais(a, b, 1e-6)) { this.previa(g); return; }
    const ref = this.referencial(a, b);
    const contorno = C.secaoDoPerfil(this.registroDoPerfil, this.editor && this.editor.cena, this.perfilAtivo);
    const sa = this.secaoEm(a, ref, contorno);
    const sb = this.secaoEm(b, ref, contorno);
    const cor = this.eixo ? C.EIXOS[this.eixo].cor : C.CORES.estrutura;
    g.add(C.gLinha(sa, cor, { fechada: true }));
    g.add(C.gLinha(sb, cor, { fechada: true }));
    for (let i = 0; i < sa.length; i++) g.add(C.gLinha([sa[i], sb[i]], cor));
    g.add(C.gLinha([a, b], C.CORES.desenho, { tracejada: true }));
    const L = C.dist(a, b);
    const reg = this.registroDoPerfil;
    const peso = reg && reg.massa
      ? `  ·  ${(reg.massa * L / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kg`
      : '';
    const texto = `${formatar(L)}  ·  ${this.perfilAtivo}  ·  ${this.papelAtivo}${peso}`;
    this.medida(texto);
    g.add(C.gRotulo(texto, C.meio(a, b), '#4b5563'));
    this.previa(g);
  }
}

export default FerramentaBarra;
