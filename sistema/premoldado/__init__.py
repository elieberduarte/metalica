# -*- coding: utf-8 -*-
"""Pré-moldado de concreto — o módulo irmão da estrutura metálica, no mesmo programa.

Mesmos conceitos da parte metálica: a entrada da obra (dados), o dimensionamento peça a peça
com a memória de cálculo em passos (nucleo.base: Resultado, Verificacao, Passo), o modelo 3D
(nucleo3d), a lista de peças e o memorial. As normas:

* ABNT NBR 6118:2023 (+ emenda 1:2026) — concreto armado: materiais, flexão, cisalhamento,
  pilares e efeitos de 2ª ordem (`concreto`, `nbr6118`);
* ABNT NBR 9062:2017 — pré-moldado: ligações (consolos, dentes, cálices, apoios),
  situações transitórias (içamento, transporte, montagem), estabilidade (`nbr9062`);
* o galpão pré-moldado (`galpao`): pilares engastados em cálice, vigas de cobertura,
  terças, fechamento.

Unidades internas: cm, kN, kN·cm (como a parte metálica); tensões em kN/cm² (1 kN/cm² = 10 MPa).

Em desenvolvimento: só aparece no modo dev (ainda fora da versão publicada).
"""
