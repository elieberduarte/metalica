# Guia de desenvolvimento — módulo 3D e IFC

Extensão do sistema de dimensionamento: um modelador 3D no navegador, com as ferramentas
principais do SketchUp, objetos estruturais que sabem o que são, e interoperabilidade
IFC nos dois sentidos.

Leia antes: `GUIA_SISTEMA.md` (princípios, estilo, unidades do núcleo de cálculo) e
`nucleo3d/modelo.py` (o contrato do documento 3D, já pronto).

## Divisão de responsabilidades

| Camada | Onde | Faz |
|---|---|---|
| Documento 3D | `nucleo3d/modelo.py` | entidades, camadas, materiais, serialização (PRONTO) |
| Geometria | `nucleo3d/geometria.py` | seções de perfil, extrusão, tesselação, operações |
| Conversão | `nucleo3d/de_projeto.py` | gera o modelo 3D do galpão dimensionado |
| IFC | `ifc/exportar.py`, `ifc/importar.py` | escreve e lê IFC4 |
| Visualização | `web/editor3d/*.js` | cena, câmera, seleção, materiais |
| Ferramentas | `web/editor3d/ferramentas/*.js` | desenho e edição |
| Servidor | `app.py` | rotas `/api/modelo/*` |

Python faz o trabalho pesado de geometria e IFC; o navegador faz interação e desenho.
O documento viaja como JSON entre os dois.

## Unidades e eixos (obrigatório)

- **Milímetro** e **grau** em todo o módulo 3D. O núcleo de cálculo usa kN e cm; a
  conversão acontece só em `de_projeto.py`.
- **Z para cima.** X ao longo do comprimento do galpão, Y no sentido do vão. É a
  convenção dos desenhos e a que o IFC recebe sem rotação adicional.
- Ângulos em graus na interface e no documento; radianos só dentro das contas.

## Contrato do documento (resumo)

```python
from nucleo3d.modelo import Documento, Barra, Chapa, Solido, Grupo, Camada, Material

doc = Documento(nome="Galpão")
doc.add(Barra(nome="P1", inicio=(0,0,0), fim=(0,0,6000),
              perfil="W 530×85,0", papel="pilar", camada="Estrutura"))
doc.add(Chapa(origem=(0,0,6000), eixo_x=(1,0,0), eixo_y=(0,0,1),
              contorno=[(0,0),(214,0),(214,760),(0,760)], espessura=16))
doc.add(Solido(vertices=[...], faces=[[0,1,2,3], ...]))

doc.barras, doc.chapas, doc.solidos      # listas por tipo
doc.caixa()                              # ((xmin,ymin,zmin), (xmax,ymax,zmax))
doc.dict() / Documento.de_dict(d)        # serialização JSON
```

`Barra.papel` (pilar, viga, terça, contraventamento, longarina) define o tipo IFC.
`Entidade.atributos` é um dicionário livre para o que cada módulo precisar guardar.

## Biblioteca 3D

Three.js r160 já está vendorizado em `web/lib/`, com os imports reescritos para
caminhos locais. **Não use CDN**: o app funciona offline.

```html
<script type="importmap">
{"imports": {"three": "./lib/three.module.js"}}
</script>
<script type="module">
import * as THREE from './lib/three.module.js';
import { OrbitControls } from './lib/OrbitControls.js';
import { TransformControls } from './lib/TransformControls.js';
</script>
```

Disponíveis: `three.module.js`, `OrbitControls.js`, `TransformControls.js`,
`BufferGeometryUtils.js`, `Line2.js`, `LineGeometry.js`, `LineMaterial.js`,
`LineSegments2.js`, `LineSegmentsGeometry.js`.

## Princípios

1. **O documento é a verdade.** Toda ferramenta edita o documento; a cena 3D é
   reconstruída a partir dele. Nada de estado escondido no Three.js.
2. **Undo/redo por comando.** Toda alteração passa por um comando com `aplicar()` e
   `desfazer()`. Nenhuma ferramenta altera o documento diretamente.
3. **Precisão antes de aparência.** Coordenadas em ponto flutuante de dupla precisão no
   documento; a conversão para float32 acontece só na hora de desenhar.
4. **Falha explícita.** Geometria inválida (contorno aberto, barra de comprimento zero,
   perfil fora do catálogo) levanta `ErroDeDados` com mensagem em português.
5. **IFC de verdade.** O arquivo exportado precisa abrir em BIMcollab ZOOM, Solibri,
   FreeCAD ou usBIM. Sintaxe STEP correta, GlobalId válido (22 caracteres base64 IFC),
   hierarquia espacial completa e unidades declaradas.

## Estilo

Português nos nomes de domínio, como no restante do sistema. JavaScript moderno, módulos
ES, sem framework. Comentários explicam o porquê, não o quê.

## Testes

`testes/test_3d_*.py` para Python. Para o JavaScript, teste pelo navegador em modo
headless com capturas de tela (o Chrome está em
`C:\Program Files\Google\Chrome\Application\chrome.exe`), conferindo as imagens com a
ferramenta Read. Um editor 3D que não foi visto funcionando não está pronto.
