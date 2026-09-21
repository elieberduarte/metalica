# Manual Prático de Estruturas Metálicas — arquivos do projeto

O PDF pronto fica em **`build/Manual_Estruturas_Metalicas.pdf`**.

## Como o manual é gerado

O manual é escrito em fragmentos HTML (um por capítulo) e impresso em PDF A4 pelo Chrome, usando a
biblioteca Paged.js para paginar, gerar cabeçalhos, rodapés e os números de página do sumário. A
impressão é comandada pelo protocolo de depuração do Chrome e só dispara depois que a paginação
termina, senão o PDF sai truncado. No fim o build grava os metadados e os 211 marcadores de navegação.

```
manual/
├── build.py            gera o HTML único e o PDF (chame este)
├── printpdf.py         imprime pelo Chrome esperando a paginação terminar
├── marcadores.py       grava os marcadores de navegação no PDF
├── verifica.py         checagens automáticas (ids duplicados, numeração, SVG válido)
├── estilo.css          estilo de impressão (páginas, figuras, tabelas, caixas)
├── capa.html           capa
├── apresentacao.html   apresentação, trilhas de leitura e convenções
├── capitulos/          cap01…cap17 (o conteúdo)
├── fig/                gráficos PNG gerados com matplotlib
├── lib/                paged.polyfill.js (cópia local, para o build não depender da internet)
└── build/              saída: manual.html, PDF e PNGs de conferência
```

## Comandos

Na pasta `manual`:

```bash
# PDF completo
PYTHONIOENCODING=utf-8 python build.py --pdf

# PDF de um ou mais capítulos, em pasta separada, com PNG de cada página
PYTHONIOENCODING=utf-8 python build.py --pdf --png --only cap07 --out build/teste

# checagens automáticas
PYTHONIOENCODING=utf-8 python verifica.py
```

Opções do `build.py`: `--pdf` gera o PDF, `--png` salva cada página como imagem para conferência,
`--only capNN` monta só os capítulos indicados (pode repetir), `--out pasta` escolhe onde gravar.

## Para editar o conteúdo

Edite os arquivos em `capitulos/` e rode o build de novo. As regras de formatação (classes de figura,
tabela, caixas de dica, atenção, norma e exemplo, padrão dos desenhos SVG) estão em `GUIA_AUTOR.md`.
O `MAPA_CAPITULOS.md` lista o assunto de cada capítulo e serve para conferir as referências cruzadas.

## Requisitos

Python 3 com `websocket-client` (usado na impressão), `pymupdf` (marcadores e PNGs de conferência) e
`matplotlib` (só para regerar os gráficos). O Google Chrome precisa estar instalado no caminho padrão do Windows; se estiver em outro
lugar, ajuste a variável `CHROME` no começo do `printpdf.py`.
