# Contrato do editor 3D no navegador

Complementa `GUIA_3D.md`. Define como o código JavaScript do editor é organizado, para
que o núcleo e as ferramentas possam ser escritos em paralelo sem colidir.

## Arquivos

```
web/editor3d/
├── editor.html          página do editor (barra de ferramentas, painéis, canvas)
├── editor.css           estilo do editor
├── editor.js            ponto de entrada: monta tudo e liga os eventos
├── nucleo/
│   ├── documento.js     espelho do Documento de nucleo3d/modelo.py, em JS
│   ├── comandos.js      pilha de undo/redo e os comandos básicos
│   ├── cena.js          Three.js: cena, luzes, grade, eixos, reconstrução do modelo
│   ├── camera.js        câmeras, navegação, vistas padrão, perspectiva/ortográfica
│   ├── selecao.js       raycast, seleção simples e por janela, destaque
│   ├── inferencia.js    snap e inferência de pontos, eixos e planos
│   └── api.js           conversa com o servidor (/api/modelo/*)
└── ferramentas/
    ├── base.js          classe Ferramenta e o registro
    ├── selecionar.js  mover.js  girar.js  escalar.js  copiar.js
    ├── linha.js  retangulo.js  circulo.js  poligono.js  arco.js
    ├── pushpull.js  offset.js
    ├── medir.js  cotar.js  secao.js
    └── barra.js  chapa.js       (ferramentas estruturais)
```

## Documento no navegador (`nucleo/documento.js`)

Espelha o contrato de `nucleo3d/modelo.py`. Mesmos nomes de campo, mesmas unidades
(milímetro, grau, Z para cima).

```js
const doc = new Documento();
doc.add({ tipo:'barra', nome:'P1', inicio:[0,0,0], fim:[0,0,6000],
          perfil:'W 530×85,0', papel:'pilar', camada:'Estrutura' });
doc.get(id); doc.remover(id); doc.porTipo('barra'); doc.porCamada('Terças');
doc.caixa(); doc.paraJSON(); Documento.deJSON(obj);
doc.aoMudar(fn);        // avisa a cena para reconstruir o que mudou
```

O documento é a única fonte de verdade. A cena Three.js é derivada dele; nenhuma
ferramenta guarda estado geométrico próprio entre um clique e outro sem passar por aqui.

## Comandos e undo/redo (`nucleo/comandos.js`)

Toda alteração passa por um comando. É o que dá undo confiável.

```js
class Comando {
  constructor(rotulo) { this.rotulo = rotulo; }
  aplicar(doc) {}       // executa
  desfazer(doc) {}      // desfaz exatamente
}
editor.executar(new ComandoAdicionar(entidades));
editor.desfazer();  editor.refazer();
```

Comandos prontos que o núcleo oferece: `ComandoAdicionar`, `ComandoRemover`,
`ComandoAlterar` (guarda antes/depois de campos), `ComandoTransformar`,
`ComandoComposto` (agrupa vários numa entrada só de undo).

## Ferramenta (`ferramentas/base.js`)

Cada ferramenta é uma máquina de estados simples que recebe eventos já tratados: o
núcleo entrega o ponto 3D com snap resolvido, não coordenadas de tela.

```js
export class Ferramenta {
  static id = 'linha';
  static nome = 'Linha';
  static atalho = 'L';
  static icone = '<svg …>';       // 24×24, traço de 1.5, currentColor
  static dica = 'Clique para o primeiro ponto';

  ativar(editor) {}               // entrou na ferramenta
  desativar() {}                  // saiu: limpe pré-visualizações
  onPonto(p, ev) {}               // clique, com p = {ponto:[x,y,z], entidade, face, tipoSnap}
  onMover(p, ev) {}               // mouse se movendo, mesmo formato
  onTecla(ev) {}                  // teclado; devolva true se consumiu
  onValor(texto) {}               // o usuário digitou uma medida e deu Enter
  cancelar() {}                   // Esc
}
```

Contexto disponível em `this.editor`: `documento`, `cena`, `camera`, `selecao`,
`inferencia`, `executar(cmd)`, `previa(objeto3d)` (desenho temporário que o núcleo
apaga sozinho), `dica(texto)`, `medida(texto)` (a caixa de medidas do canto),
`catalogo` (perfis e materiais vindos do servidor).

**Entrada numérica**: como no SketchUp, o usuário pode digitar a medida durante a
operação e confirmar com Enter — `onValor` recebe o texto. Aceite `3000`, `3,5m`,
`350cm`, e para retângulo `2000;1000`.

## Inferência (`nucleo/inferencia.js`)

Devolve, para a posição do mouse, o ponto 3D mais provável, com o tipo:
`extremidade`, `meio`, `centro`, `interseccao`, `sobre_aresta`, `sobre_face`,
`eixo_x`, `eixo_y`, `eixo_z`, `paralelo`, `perpendicular`, `plano_base`.
Cada tipo tem cor e glifo próprios, como no SketchUp. Travar eixo com as setas do
teclado e com Shift.

## Interface

Barra de ferramentas vertical à esquerda com ícones e atalho no tooltip. Painéis à
direita: propriedades da seleção, camadas, materiais, análise e estrutura do modelo.
Barra inferior: dica da ferramenta e caixa de medidas. Visual sóbrio, mesma paleta do
restante do sistema (azul `#0b3d91`), tema claro e escuro por `prefers-color-scheme`.

Atalhos: espaço=selecionar, L=linha, R=retângulo, C=círculo, P=push/pull, M=mover,
Q=girar, E=escalar, O=offset, T=medir, D=cotar, X=seção, B=barra, H=chapa,
Ctrl+Z/Y=undo/redo, Ctrl+C/V=copiar/colar, Del=apagar, Esc=cancelar,
1..6=vistas padrão, 7=isométrica, Z=zoom extensão, F9=calcular estrutura.

## Mapa de esforços (`nucleo/analise3d.js`)

Não fica ligado sozinho: nasce do botão **Calcular estrutura** (F9, também em Ver). O
botão pede `/api/modelo/analise`, guarda o resultado e acende o painel "Análise";
apertado de novo, esconde tudo e devolve as cores normais — reexibir não recalcula.

O painel escolhe a grandeza (aproveitamento S/R, M, V ou N) e a combinação (envoltória
ou uma das combinações, últimas e de serviço separadas), mostra a legenda da escala, as
dez peças mais solicitadas, os dados da peça selecionada e o deslocamento de serviço
contra o limite. Na cena, `MapaDeEsforcos` pinta cada peça pelo valor (entra pelo
`_corDe` da cena, por `definirCorPorValor`) e desenha, quando ligados: as fitas dos
diagramas de M, V e N no pórtico com os picos cotados, a deformada com fator de
exagero, e as cargas da combinação em setas com o valor em kN/m. Os desenhos vivem num
grupo próprio da cena — não entram no documento, na árvore, na lista de material nem
no IFC.

As peças casam com o cálculo pelo nome do elemento (`atributos.elemento`), o mesmo que
`de_projeto.py` grava em cada peça e que `nucleo3d/mapa_esforcos.py` usa como chave.

**Onde os diagramas são desenhados.** Os pórticos do galpão são todos iguais e recebem
a mesma carga, então a fita nasce num só — o painel tem um seletor ("1 pórtico", "3
pórticos, pontas e meio", "todos") e diz qual está em exibição, porque quem olha a cena
não tem como adivinhar essa limitação. Terça e longarina não fazem parte do modelo de
pórtico plano: são verificadas como viga biapoiada entre apoios, e o mapa publica esse
diagrama próprio em `elementos[nome].diagrama`, desenhado sobre uma **peça típica** de
cada elemento — desenhar nas 272 terças seria ruído. Contraventamento não tem fita: só
trabalha à tração, e uma faixa de normal constante não diria nada além do número que já
está na cor e no quadro.

## Servidor

```
GET  /api/modelo/catalogo      perfis com dimensões e seções prontas para desenhar
POST /api/modelo/malha         documento → malhas (vértices/faces) para a cena
POST /api/modelo/ifc/exportar  documento → arquivo IFC, devolve url
POST /api/modelo/ifc/importar  arquivo IFC → documento + relatório de importação
POST /api/modelo/salvar        grava o documento em projetos/<nome>.modelo.json
GET  /api/modelo/abrir/<nome>  carrega documento salvo
POST /api/modelo/do-galpao     gera o modelo 3D do galpão dimensionado
POST /api/modelo/analise       mapa de esforços: aproveitamentos, diagramas,
                               deformada, cargas e deslocamento de serviço
```

A malha das barras e chapas vem do Python (`nucleo3d/geometria.py`), que é quem sabe
gerar a seção correta de cada perfil. O navegador só desenha e edita o eixo, o perfil e
a posição; quando algo muda, pede a malha de novo. Sólidos livres são tesselados no
próprio navegador, porque são editados a cada movimento do mouse.

## Regra de verificação

Um editor 3D que não foi visto funcionando não está pronto. Suba o servidor, abra o
editor no Chrome headless, tire capturas e **olhe as imagens** com a ferramenta Read,
em cada ferramenta e nos dois temas. Corrija e repita.
