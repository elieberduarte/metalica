# Guia de desenvolvimento — Sistema de dimensionamento de estruturas metálicas

Sistema em Python que dimensiona e detalha galpões industriais em aço conforme as normas
brasileiras, com interface web local. Entrega memorial de cálculo em PDF, desenhos DXF,
pranchas em PDF e lista de material.

## Princípios inegociáveis

1. **Nada de número mágico.** Toda fórmula vem de um item de norma, citado no código e na
   memória de cálculo. Quando a norma não cobre o caso, diga isso explicitamente na observação
   da verificação, em vez de inventar um critério.
2. **Memória de cálculo é parte do resultado.** Cada verificação registra os passos com fórmula
   simbólica, a mesma fórmula com números e o resultado. O memorial em PDF é montado a partir
   desses passos, então ele nunca diverge do que foi calculado.
3. **A favor da segurança em caso de dúvida.** Se uma propriedade é estimada (J sem os raios de
   concordância, por exemplo), a estimativa tem que ser conservadora e estar documentada.
4. **Falha explícita.** Entrada inconsistente levanta `ErroDeDados` com mensagem em português
   dizendo o que está errado e qual a faixa aceitável. Nunca devolva resultado silencioso e errado.
5. **Validação contra o manual.** O manual em `../manual/` tem exemplos resolvidos e conferidos.
   Todo módulo tem testes que reproduzem esses exemplos dentro de 1 %.

## Unidades (obrigatório)

| Grandeza | Unidade interna | Observação |
|---|---|---|
| Força | kN | |
| Momento | kN·cm | kN·m só na interface e nos relatórios |
| Tensão | kN/cm² | 1 kN/cm² = 10 MPa |
| Comprimento | cm | mm só no catálogo de perfis, na interface e nos desenhos |
| Área | cm² | |
| Carga distribuída | kN/cm | kN/m na interface |

As dimensões do catálogo de perfis (`Perfil.d`, `.bf`, `.tw`, `.tf`) estão em **mm**, como nos
catálogos dos fabricantes. As propriedades de seção (`.A`, `.Ix`, `.Wx`, `.Zx`, `.rx`, `.J`, `.Cw`)
estão em **cm**. Converta explicitamente; não confie na memória.

## Estrutura do projeto

```
sistema/
├── nucleo/
│   ├── base.py         Verificacao, Resultado, Passo, constantes, fmt()   [PRONTO]
│   ├── materiais.py    aços, parafusos, eletrodos, concreto               [PRONTO]
│   ├── perfis.py       catálogo (banco(), perfil(nome), classe Perfil)    [PRONTO]
│   ├── nbr8800.py      barras de aço laminado/soldado
│   ├── nbr14762.py     perfis formados a frio (terças e longarinas)
│   ├── cargas.py       NBR 6120, NBR 6123 (vento), NBR 8681 (combinações)
│   ├── analise.py      pórtico plano e treliça pelo método da rigidez
│   ├── ligacoes.py     parafusos, soldas e ligações típicas
│   ├── bases.py        placa de base, chumbadores, chave de cisalhamento
│   └── galpao.py       orquestrador do galpão completo
├── saida/              memorial PDF, DXF, pranchas, lista de material
├── web/                interface (HTML + JS puro, sem framework)
├── dados/              perfis.json e o extrator
├── testes/             test_*.py (pytest ou unittest puro)
└── app.py              servidor web local
```

## Contratos já disponíveis

```python
from .base import (Verificacao, Resultado, Passo, ErroDeDados, fmt,
                   E, G, NU, RHO, ALFA, GAMA_A1, GAMA_A2, GAMA_W2, GAMA_C)
from . import materiais as mat
from .perfis import perfil, banco, Perfil
```

**Verificacao** — resultado de um estado-limite:

```python
v = Verificacao("Compressão — flambagem por flexão", norma="NBR 8800:2008, item 5.3.3",
                Sd=190.0, Rd=891.0, unidade="kN")
v.passo("Carga crítica de Euler",
        formula="N<sub>e</sub> = π²·E·I / (KL)²",
        conta="π²·20 000·12 258 / 1 200²",
        valor=fmt(1681, 0, "kN"),
        norma="item 5.3.3.2")
v.razao   # 0.213   Sd/Rd
v.ok      # True
v.folga   # 78.7 (%)
```

**Resultado** — agrupa as verificações de um elemento:

```python
r = Resultado("Pilar P1", perfil="W 360×44,6", material="ASTM A572 Gr.50")
r.add(v)
r.razao      # a maior razão entre as verificações
r.ok         # todas passaram
r.critica    # a Verificacao que governa
r.dados      # dict livre com o que o memorial e os desenhos precisarem
```

Guarde em `r.dados` tudo que outro módulo possa precisar (χ, λ0, Lb, Mrd, esforços, geometria
adotada). O memorial e os desenhos leem daí.

**Perfil** — propriedades principais:

```python
p = perfil("W 360×51")        # aceita "W 360x51", "W 360×51,0"
p.d, p.bf, p.tw, p.tf         # mm
p.A, p.Ix, p.Wx, p.Zx, p.rx   # cm
p.Iy, p.Wy, p.Zy, p.ry
p.J, p.Cw                     # cm⁴, cm⁶
p.Aw                          # área de cisalhamento, cm²
p.h_alma                      # altura livre da alma, mm
p.esbeltez_mesa               # b/t da mesa comprimida
p.esbeltez_alma               # h/tw
p.fechado, p.bissimetrico
banco().candidatos("I", "W", altura_min=300, altura_max=400)   # lista para busca
```

**Materiais**:

```python
a = mat.aco("ASTM A572 Gr.50")     # a.fy = 34.5, a.fu = 45.0 (kN/cm²)
pf = mat.parafuso("ASTM A325")     # pf.fub = 82.5
d, Ab, Ae = mat.diametro('3/4"')   # cm, cm², cm²
el = mat.eletrodo("E70XX")         # el.fw = 48.5
c = mat.concreto(0.25)             # fck em kN/cm²; c.fcd
mat.PROTENSAO["ASTM A325"]['3/4"'] # 125 kN
mat.perna_minima(t_cm), mat.perna_maxima(t_cm)
```

## Estilo do código

- Português nos nomes de função, variáveis de domínio e mensagens; siga a notação da norma nas
  variáveis de fórmula (`Nc_Rd`, `lambda_0`, `chi`, `Mpl`, `Lb`, `Cb`).
- Docstring de cada função citando o item da norma.
- Type hints nos parâmetros públicos.
- Sem dependências externas além de `pymupdf` (já instalado) e da biblioteca padrão. Nada de
  numpy, scipy ou pandas: a análise matricial usa listas e Gauss escrito à mão.
- Funções puras sempre que possível: recebem dados, devolvem `Verificacao` ou `Resultado`.

## Testes

Um arquivo por módulo em `testes/`, executável com `python -m pytest testes/ -q` e também com
`python testes/test_xxx.py`. Cada teste que reproduz um exemplo do manual cita o capítulo e o
número do exemplo no nome ou no comentário. Tolerância padrão de 1 % contra o manual; se divergir
mais, investigue: pode ser erro do módulo ou do manual. Se for do manual, relate, não "ajuste" o
teste para passar.

## Como rodar

```bash
cd sistema
PYTHONIOENCODING=utf-8 python -m pytest testes/ -q
PYTHONIOENCODING=utf-8 python app.py          # sobe a interface em http://localhost:8765
```
