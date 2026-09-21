// Registro das ferramentas do editor.
//
// A importação é dinâmica e tolerante: uma ferramenta que ainda não existe (ou que
// quebrou ao carregar) não derruba o editor, só não aparece na barra. Isso permite
// que o núcleo e as ferramentas sejam desenvolvidos em paralelo.

const ARQUIVOS = [
  // navegação e seleção
  ['./selecionar.js', 'navegacao'],
  // desenho
  ['./linha.js', 'desenho'],
  ['./retangulo.js', 'desenho'],
  ['./circulo.js', 'desenho'],
  ['./poligono.js', 'desenho'],
  ['./arco.js', 'desenho'],
  // edição
  ['./pushpull.js', 'edicao'],
  ['./offset.js', 'edicao'],
  ['./mover.js', 'edicao'],
  ['./girar.js', 'edicao'],
  ['./escalar.js', 'edicao'],
  ['./copiar.js', 'edicao'],
  // medição
  ['./medir.js', 'medicao'],
  ['./cotar.js', 'medicao'],
  ['./secao.js', 'medicao'],
  // estrutura
  ['./barra.js', 'estrutura'],
  ['./chapa.js', 'estrutura'],
];

/**
 * Carrega todas as ferramentas disponíveis.
 * Cada módulo deve exportar, como `default` ou como exportação nomeada, uma ou mais
 * classes que estendem `Ferramenta`.
 */
export async function carregarFerramentas() {
  const encontradas = [];
  const falhas = [];
  for (const [arquivo, grupo] of ARQUIVOS) {
    try {
      const mod = await import(arquivo);
      for (const exportado of Object.values(mod)) {
        if (typeof exportado === 'function' && exportado.id && exportado.nome) {
          if (!exportado.grupo || exportado.grupo === 'edicao') {
            try { exportado.grupo = exportado.grupo || grupo; } catch { /* estático */ }
          }
          encontradas.push(exportado);
        }
      }
    } catch (e) {
      falhas.push({ arquivo, erro: String(e && e.message || e) });
    }
  }
  // sem duplicatas, mantendo a ordem de declaração
  const vistas = new Set();
  const lista = encontradas.filter(f => !vistas.has(f.id) && vistas.add(f.id));
  if (falhas.length) {
    console.info('Ferramentas não carregadas:', falhas);
  }
  return { ferramentas: lista, falhas };
}

export const GRUPOS = [
  ['navegacao', 'Navegação'],
  ['desenho', 'Desenho'],
  ['edicao', 'Edição'],
  ['medicao', 'Medição'],
  ['estrutura', 'Estrutura'],
];
