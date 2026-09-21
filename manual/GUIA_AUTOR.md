# GUIA DE AUTORIA – Manual Prático de Estruturas Metálicas

Você está escrevendo capítulos de um **manual didático completo em português do Brasil** sobre estruturas
metálicas (aço), que vai do zero absoluto até o nível avançado. O público é misto: iniciantes (serralheiros,
técnicos, estudantes, compradores, engenheiros de outras áreas) e profissionais que querem aprofundar.
O tom é **prático, claro e progressivo**: explique o "porquê" com linguagem simples, depois traga a
técnica, as normas e os números. Sempre que possível dê **valores usuais, regras de bolso, tabelas e exemplos
numéricos resolvidos passo a passo**.

O manual será montado a partir de fragmentos HTML (um arquivo por capítulo) e impresso em PDF (A4) com o
CSS de `estilo.css` (leia-o para conhecer as classes). Figuras são **SVG desenhados por você, inline**, ou
gráficos PNG gerados com matplotlib. Não use imagens externas nem URLs.

## Arquivos
- Escreva cada capítulo em `capitulos/capNN_slug.html` (NN com dois dígitos, ex.: `cap07_dimensionamento.html`).
- O arquivo é um **fragmento**: sem `<html>`, `<head>`, `<body>`, sem `<style>` e sem `<script>`.
- Codificação UTF-8. Use entidades apenas quando necessário (`&lt;`, `&amp;`).
- PNGs do matplotlib vão em `fig/capNN_nome.png` e são referenciados como `<img src="fig/capNN_nome.png">`
  (largura ≥ 1600 px, dpi 200, fundo branco, fontes Arial, rótulos em português).
- Grave os arquivos com um script Python ou com a ferramenta Write (evite heredoc no shell com textos longos).

## Estrutura obrigatória de cada capítulo
```html
<h1 class="cap"><small>Capítulo 7</small>Dimensionamento de elementos</h1>
<div class="objetivos"><div class="tit">O que você vai aprender neste capítulo</div>
<ul><li>...</li><li>...</li></ul></div>

<h2>7.1 Título da seção <span class="nivel b">Básico</span></h2>
<p>...</p>
<h3>7.1.1 Subseção</h3>
...
<div class="resumo"><div class="tit">Resumo do capítulo</div><ul><li>...</li></ul></div>
```
- Numere seções `N.k` e subseções `N.k.j` no próprio texto do título.
- Marque o nível de cada `<h2>` com `<span class="nivel b">Básico</span>`, `<span class="nivel i">Intermediário</span>`
  ou `<span class="nivel a">Avançado</span>`.
- Termine com `<div class="resumo">` (pontos-chave) e, quando fizer sentido, uma lista `<ul class="chk">` de verificação.

## Elementos disponíveis (use exatamente estas classes)
- **Figura**:
```html
<figure class="fig p75">
  <svg viewBox="0 0 700 320" xmlns="http://www.w3.org/2000/svg" font-family="Arial, Helvetica, sans-serif" font-size="13">
    ...
  </svg>
  <figcaption><b>Figura 7.3</b> – Curva de flambagem da NBR 8800 (χ × λ<sub>0</sub>).</figcaption>
</figure>
```
  Classes de largura: `p60`, `p75`, `p90` ou nenhuma (100 %). Duas figuras lado a lado:
  `<div class="fig-row"> <figure class="fig">…</figure> <figure class="fig">…</figure> </div>`.
- **Tabela**:
```html
<table class="tab"><caption>Tabela 7.2 – Coeficientes de ponderação γ</caption>
<thead><tr><th>Coluna</th><th>Coluna</th></tr></thead>
<tbody><tr><td class="l">texto à esquerda</td><td class="c">centrado</td></tr></tbody></table>
```
  Use `class="tab small"` para tabelas extensas.
- **Fórmula** (HTML simples, sem LaTeX/MathML):
```html
<div class="formula">N<sub>t,Rd</sub> = A<sub>g</sub> · f<sub>y</sub> / γ<sub>a1</sub><span class="n">(7.1)</span></div>
<ul class="onde"><li>A<sub>g</sub> = área bruta da seção (cm²)</li><li>f<sub>y</sub> = resistência ao escoamento (kN/cm²)</li></ul>
```
  Use caracteres Unicode: · × √ ≤ ≥ ≈ π λ χ γ σ τ φ Δ ² ³. Para frações, escreva com "/".
- **Caixas**: `<div class="box"><div class="tit">Conceito</div><p>…</p></div>`; variantes `box dica`, `box atencao`,
  `box norma` (citação de norma), `box exemplo` (exemplo resolvido, com passos em `<div class="passo">`).
- **Quebra de página forçada**: `<div class="quebra"></div>` (use raramente).

## Regras para os desenhos SVG (MUITO IMPORTANTE)
1. `viewBox` com largura 600 a 800 e altura proporcional ao conteúdo (não deixe espaço vazio).
2. **IDs únicos em todo o manual**: todo `id` de `<pattern>`, `<marker>`, `<linearGradient>` deve ter o prefixo do
   capítulo e da figura, ex.: `id="h7_3"` (hachura), `id="s7_3"` (seta). Nunca reutilize `id` entre figuras.
3. Paleta: contorno `#333` (stroke-width 1.5 a 2), aço `#d9dee7` (preenchimento) ou hachura 45°, destaque azul
   `#0b3d91`, cargas/forças vermelho `#c0392b`, cotas e linhas de chamada `#555` (stroke-width 1), soldas `#7a3e00`
   (preenchimento `#e0a86a`), parafusos `#444`, concreto `#c8c8c8` com pontilhado, linhas ocultas `stroke-dasharray="4 3"`.
4. Hachura padrão de corte de aço:
   `<pattern id="h7_3" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#8a94a6" stroke-width="1"/></pattern>`
5. Seta de cota/força: `<marker id="s7_3" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#333"/></marker>`
   e use `marker-end="url(#s7_3)"` / `marker-start="url(#s7_3)"`.
6. Textos: `font-size` 12–15 (dentro do viewBox), `text-anchor="middle"` quando centralizado; rótulos em português;
   símbolos com Unicode (ex.: "ø", "t<tspan baseline-shift="sub" font-size="9">f</tspan>").
7. Desenhe com **precisão geométrica** (perfis com mesas paralelas, furos circulares, filetes de solda triangulares,
   linhas de cota com pequenas extensões). Prefira desenhos esquemáticos limpos a "arte". Sempre inclua cotas ou rótulos
   que ensinem algo (nomes das partes: mesa, alma, enrijecedor, chapa de topo, etc.).
8. Cada figura deve ter legenda numerada `Figura N.k – …` em ordem crescente dentro do capítulo. Tabelas idem (`Tabela N.k`).
9. Mínimo de **8 figuras** por capítulo (capítulos técnicos: 10 a 16). Não repita a mesma figura com pequenas variações.
10. O SVG deve ser válido (feche todas as tags, não use `&` solto, use `&amp;`).

## Conteúdo técnico – referências a adotar
- Normas brasileiras: NBR 8800:2008 (aço laminado/soldado – estados-limites), NBR 14762:2010 (perfis formados a frio),
  NBR 8681:2003 (ações e segurança), NBR 6120:2019 (cargas), NBR 6123:1988/2023 (vento), NBR 7007 (aços para perfis),
  NBR 6323 (galvanização), NBR 14323 (incêndio), NBR 5884 (perfis soldados), NBR 15980 (perfis laminados),
  NBR 16239 (tubos), NBR 5000/5004/6650 (chapas). Internacionais: AISC 360, AWS D1.1, ASTM A36/A572/A588/A325/A490/A307,
  ISO 12944, ISO 8501-1, SSPC, EN 1090.
- Valores de referência: E = 200 000 MPa; G = 77 000 MPa; ν = 0,3; ρ = 7 850 kg/m³; α = 1,2×10⁻⁵ /°C.
  ASTM A36: fy = 250 MPa, fu = 400 MPa. A572 Gr.50: 345/450. A588 / CSN COR 420 / USI-SAC 350: 345/485 (patinável).
  NBR 7007 MR250: 250/400; AR350: 350/450; AR350 COR: 350/485. Formados a frio: CF-26 (260/410), ZAR-230/280 galvanizados.
  Parafusos: ASTM A307 fub = 415 MPa; A325 825 MPa (d ≤ 24 mm), 725 MPa (d > 24); A490 1035 MPa; ISO 8.8 800 MPa; 10.9 1000 MPa.
  Eletrodos: E60XX fw = 415 MPa; E70XX 485 MPa. Coeficientes NBR 8800: γa1 = 1,10 (escoamento), γa2 = 1,35 (ruptura),
  γw1 = 1,10 (metal base), γw2 = 1,35 (metal da solda). Curva de flambagem NBR 8800: χ = 0,658^(λ0²) para λ0 ≤ 1,5;
  χ = 0,877/λ0² para λ0 > 1,5. Deslocamentos limites (Anexo C): vigas de piso L/350, vigas de cobertura L/250, terças L/180,
  pilares H/300 (deslocamento horizontal em edifícios) e H/400 entre pisos.
- Unidades SI: kN, kN·m, MPa (ou kN/cm²), mm/cm/m. Mostre a conversão quando útil (1 kN/cm² = 10 MPa; 1 kgf ≈ 10 N).
- Seja **tecnicamente correto**. Se um valor variar por fabricante, diga "valor típico" e dê a faixa. Não invente normas.

## Extensão e ritmo
- Cada capítulo: entre 2 500 e 5 000 palavras de texto corrido (capítulos de cálculo podem ser maiores), 8–16 figuras,
  3–8 tabelas, e nos capítulos de cálculo pelo menos 2 exemplos resolvidos completos (`box exemplo`) com números reais.
- Progrida do básico ao avançado dentro do capítulo. Inclua "regras de bolso" em `box dica` e alertas em `box atencao`.
- Faça referências cruzadas simples em texto ("ver Capítulo 9").

## Verificação obrigatória antes de terminar
1. Rode (na pasta `manual`): `PYTHONIOENCODING=utf-8 python build.py --pdf --png --only capNN --out build/capNN`
   (substitua `capNN` pelo prefixo do seu arquivo; pode passar `--only` várias vezes para vários capítulos).
2. Abra as imagens em `build/capNN/png/` com a ferramenta Read e **olhe todas as páginas**: figuras cortadas, textos
   sobrepostos, SVG deformado, tabelas estouradas, caixas vazias, legendas fora de ordem. Corrija e repita até ficar limpo.
3. Verifique que não há `id` duplicado: `grep -o 'id="[^"]*"' capitulos/capNN_*.html | sort | uniq -d` deve retornar vazio.
4. Informe no relatório final: arquivos criados, número de figuras/tabelas/exemplos por capítulo e o que ficou pendente.
