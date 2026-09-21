// Chapa: contorno no plano, espessura e furos de parafuso.
//
// Três passos, na ordem em que se detalha uma ligação:
//   1. contorno — cliques no plano da face apontada (ou no plano de trabalho);
//      Enter, duplo clique ou clique no primeiro ponto fecham o contorno;
//   2. espessura — digite (12,7 / 16 / 0,5") ou Enter aceita a corrente;
//   3. furos — cada clique dentro da chapa põe um furo com o diâmetro do
//      parafuso ativo; digite o nome do parafuso ('3/4"', 'M20') para trocar;
//      Enter ou Esc encerram.
// A chapa é uma entidade paramétrica `Chapa`: contorno em coordenadas do plano,
// espessura e furos, que é o que o IFC e a lista de materiais precisam.

import { Ferramenta, paraMilimetros, formatar } from './base.js';
import * as C from './_comum.js';

export class FerramentaChapa extends Ferramenta {
  static id = 'chapa';
  static nome = 'Chapa';
  static atalho = 'H';
  static grupo = 'estrutura';
  static dica = 'Clique no primeiro ponto do contorno da chapa';
  static icone = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 7.5 10 4l11 4.5-7 3.5Z"/><path d="M3 7.5v3l11 4.5v-3"/><path d="M14 12v3l7-3.5v-3"/><circle cx="8.6" cy="7.2" r="1"/><circle cx="15.4" cy="9.2" r="1"/></svg>`;

  ativar() {
    this.passo = 'contorno';
    this.plano = null;
    this.pontos = [];
    this.atual = null;
    this.eixo = null;
    this.chapaId = null;
    this.dica(FerramentaChapa.dica);
    this.medida('');
  }

  desativar() { this.reiniciar(); }

  get espessura() { return this.constructor.espessura || 12.7; }
  set espessura(v) { this.constructor.espessura = v; }

  get parafuso() {
    const e = this.editor || {};
    return e.parafusoAtivo || this.constructor.parafuso || '3/4"';
  }

  set parafuso(nome) {
    this.constructor.parafuso = nome;
    if (this.editor) this.editor.parafusoAtivo = nome;
  }

  get diametroFuro() {
    const l = C.parafusosDoCatalogo(this.editor);
    const a = l.find(p => p.nome === this.parafuso);
    // furo padrão: diâmetro do parafuso + 1,5 mm (NBR 8800, furo padrão)
    return (a ? a.d : 19.05) + 1.5;
  }

  // ------------------------------------------------------------- eventos

  onMover(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (this.passo === 'contorno') {
      this.atual = this.resolver(this.plano ? C.noPlano(this.editor, p, this.plano) : p.ponto);
    } else if (this.passo === 'furos') {
      this.atual = C.noPlano(this.editor, p, this.plano);
    }
    this.desenhar();
  }

  onPonto(p) {
    C.sincronizarEixo(this);
    if (!p) return;
    if (this.passo === 'contorno') return this.pontoDoContorno(p);
    if (this.passo === 'espessura') { this.fecharEspessura(this.espessura); return; }
    if (this.passo === 'furos') return this.furarEm(C.noPlano(this.editor, p, this.plano));
  }

  onDuploClique() {
    if (this.passo === 'contorno') this.fecharContorno();
  }

  onValor(texto) {
    const t = String(texto).trim();
    if (this.passo === 'contorno') {
      if (!this.pontos.length) return false;
      const d = paraMilimetros(t);
      if (!isFinite(d) || d <= 0 || !this.atual) return false;
      const base = this.pontos[this.pontos.length - 1];
      const dir = C.sub(this.atual, base);
      if (C.comp(dir) < 1e-6) return false;
      this.acrescentar(C.add(base, C.mul(C.normalizar(dir), d)));
      return true;
    }
    if (this.passo === 'espessura') {
      const e = paraMilimetros(t);
      if (!isFinite(e) || e <= 0) return false;
      this.fecharEspessura(e);
      return true;
    }
    if (this.passo === 'furos') {
      const nomes = C.parafusosDoCatalogo(this.editor).map(p => p.nome);
      const achado = nomes.find(n => n.toLowerCase() === t.toLowerCase());
      if (achado) {
        this.parafuso = achado;
        this.dica(`Furos de ${achado} (ø ${formatar(this.diametroFuro, 1)}) — clique para furar`);
        return true;
      }
      return false;
    }
    return false;
  }

  onTecla(ev) {
    if (ev.type && ev.type !== 'keydown') return false;
    if (this.passo === 'contorno') {
      if (C.teclaDeEixo(this, ev)) { this.desenhar(); return true; }
      if (ev.key === 'Enter') { this.fecharContorno(); return true; }
      return false;
    }
    if (ev.key === 'Enter') {
      if (this.passo === 'espessura') { this.fecharEspessura(this.espessura); return true; }
      if (this.passo === 'furos') { this.concluir(); return true; }
    }
    return false;
  }

  cancelar() {
    if (this.passo === 'furos') { this.concluir(); return; }
    if (this.passo === 'espessura') { this.passo = 'contorno'; this.desenhar(); return; }
    if (this.pontos.length) { this.reiniciar(); this.dica(FerramentaChapa.dica); return; }
    C.voltarParaSelecao(this.editor);
  }

  // ------------------------------------------------------------- contorno

  resolver(ponto) {
    if (!this.pontos.length) return C.copiar(ponto);
    const q = this.plano ? C.projetarNoPlano(this.plano, ponto) : C.copiar(ponto);
    return this.eixo ? C.projetarNoEixo(this.pontos[this.pontos.length - 1], q, this.eixo) : q;
  }

  pontoDoContorno(p) {
    if (!this.pontos.length) {
      this.plano = C.planoDoPonto(this.editor, p);
      this.plano.origem = C.copiar(p.ponto);
      this.pontos.push(C.copiar(p.ponto));
      C.ancorar(this.editor, p.ponto);
      this.dica('Clique nos demais pontos — Enter ou duplo clique fecham o contorno');
      this.desenhar();
      return;
    }
    const q = this.resolver(C.noPlano(this.editor, p, this.plano));
    if (this.pontos.length >= 3 && C.iguais(this.pontos[0], q, 1.0)) { this.fecharContorno(); return; }
    if (C.iguais(this.pontos[this.pontos.length - 1], q, 0.5)) return;
    this.acrescentar(q);
  }

  acrescentar(q) {
    this.pontos.push(q);
    C.ancorar(this.editor, q);
    this.desenhar();
  }

  fecharContorno() {
    if (this.pontos.length < 3) { this.dica('A chapa precisa de pelo menos três pontos.'); return; }
    this.passo = 'espessura';
    this.atual = null;
    this.dica(`Espessura da chapa: digite o valor (atual ${formatar(this.espessura, 1)}) ou Enter`);
    this.medida(formatar(this.espessura, 1));
    this.desenhar();
  }

  // ------------------------------------------------------------- entidade

  contorno2d() {
    const pts = this.pontos.map(p => C.para2d(this.plano, p));
    return C.areaAssinada(pts) >= 0 ? pts : pts.reverse();
  }

  fecharEspessura(e) {
    this.espessura = e;
    const ent = {
      tipo: 'chapa', id: C.novoId('ch'),
      nome: '', camada: (this.editor && this.editor.camadaAtiva) || 'Chapas',
      material: '', visivel: true, bloqueada: false, grupo: '',
      origem: C.copiar(this.plano.origem),
      eixo_x: C.copiar(this.plano.ex), eixo_y: C.copiar(this.plano.ey),
      contorno: this.contorno2d(), espessura: e, centrada: true, furos: [],
      aco: (this.editor && this.editor.acoAtivo) || 'ASTM A36',
      atributos: {},
    };
    this.chapaId = ent.id;
    this.furos = [];
    this.executar(C.cmdAdicionar(ent, 'Criar chapa'));
    this.passo = 'furos';
    this.dica(`Chapa de ${formatar(e, 1)} criada — clique para furar com ${this.parafuso}, ` +
              'Enter ou Esc encerram');
    this.medida('');
    this.desenhar();
  }

  furarEm(ponto) {
    if (!this.chapaId) return;
    const uv = C.para2d(this.plano, ponto);
    if (!C.dentroDoContorno(this.contorno2d(), uv)) {
      this.dica('O furo precisa cair dentro do contorno da chapa.');
      return;
    }
    this.furos.push({ x: uv[0], y: uv[1], diametro: this.diametroFuro,
                      parafuso: this.parafuso });
    this.executar(C.cmdAlterar(this.chapaId, { furos: this.furos.map(f => ({ ...f })) },
                               'Furar chapa'));
    this.dica(`${this.furos.length} furo(s) de ${this.parafuso} — Enter ou Esc encerram`);
    this.desenhar();
  }

  concluir() {
    this.reiniciar();
    this.dica(FerramentaChapa.dica);
  }

  reiniciar() {
    C.desancorar(this.editor);
    this.passo = 'contorno';
    this.pontos = [];
    this.atual = null;
    this.plano = null;
    this.eixo = null;
    this.chapaId = null;
    this.furos = [];
    this.limparPrevia();
    this.medida('');
  }

  // ------------------------------------------------------------- prévia

  circulo(centro2d, raio, n = 16) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      pts.push(C.para3d(this.plano, centro2d[0] + raio * Math.cos(a),
                                    centro2d[1] + raio * Math.sin(a)));
    }
    return pts;
  }

  desenhar() {
    this.limparPrevia();
    const g = C.grupo();
    for (const p of this.pontos) g.add(C.gPonto(p, C.CORES.cota));

    if (this.passo === 'contorno') {
      const lista = this.atual ? this.pontos.concat([this.atual]) : this.pontos;
      if (lista.length >= 2) g.add(C.gLinha(lista, C.CORES.cota));
      if (lista.length >= 3) {
        g.add(C.gPoligono(lista, C.CORES.cota, 0.18));
        g.add(C.gLinha([lista[lista.length - 1], lista[0]], C.CORES.guia, { tracejada: true }));
      }
      if (this.pontos.length && this.atual) {
        const d = C.dist(this.pontos[this.pontos.length - 1], this.atual);
        this.medida(formatar(d) + (this.eixo ? '  eixo ' + C.EIXOS[this.eixo].nome : ''));
      }
    } else if (this.plano && this.pontos.length >= 3) {
      // contorno fechado, com a espessura mostrada nas duas faces
      const e = this.espessura / 2;
      const nrm = this.plano.normal;
      const face1 = this.pontos.map(p => C.add(p, C.mul(nrm, e)));
      const face2 = this.pontos.map(p => C.sub(p, C.mul(nrm, e)));
      g.add(C.gPoligono(face1, C.CORES.cota, 0.22));
      g.add(C.gLinha(face1, C.CORES.cota, { fechada: true }));
      g.add(C.gLinha(face2, C.CORES.cota, { fechada: true }));
      for (let i = 0; i < face1.length; i++) g.add(C.gLinha([face1[i], face2[i]], C.CORES.cota));
      for (const f of (this.furos || [])) {
        g.add(C.gLinha(this.circulo([f.x, f.y], f.diametro / 2), C.CORES.aviso, { fechada: true }));
      }
      if (this.passo === 'furos' && this.atual) {
        const uv = C.para2d(this.plano, this.atual);
        g.add(C.gLinha(this.circulo(uv, this.diametroFuro / 2), C.CORES.desenho, { fechada: true }));
        this.medida(`furo ø ${formatar(this.diametroFuro, 1)} · ${this.parafuso}`);
      }
    }
    this.previa(g);
  }
}

FerramentaChapa.espessura = 12.7;
FerramentaChapa.parafuso = '3/4"';

export default FerramentaChapa;
