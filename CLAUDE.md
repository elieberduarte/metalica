# Metálica — regras do projeto

## Toda correção de defeito ganha um teste de regressão

Defeito corrigido não pode voltar. Ao corrigir qualquer erro:

1. Escrever o teste que **falha sem a correção e passa com ela** — pytest em `sistema/testes/test_*.py`
   quando é conta do servidor; verificador em `sistema/testes/verificadores/verif_*.py` (Chrome sem
   janela, eventos de verdade) quando é tela. Conferir desfazendo a correção e vendo o teste falhar.
2. Rodar o teste **na forma de modelo em que o defeito apareceu**, não só no modelo de exemplo
   (piso longe do z = 0, modelo muito grande ou muito pequeno, importado de outro programa…).
   Situação nova → mais uma entrada no teste (ex.: `SITUACOES` em `verif_camera_modelos.py`).
3. Acrescentar uma linha em `sistema/testes/REGRESSOES.md`: data, o que o usuário viu, commit, teste.

A correção sem o teste não está pronta. Os testes entram sozinhos no `antes_de_publicar.py` e na
conferência da noite.

## Toda tarefa demorada mostra a barra de andamento

Padrão do sistema (16/10): `sistema/web/progresso.js`, instalado em toda página pelo `vivo.js`.

- **Na tela, nada a fazer**: toda chamada `fetch` a `/api/…` que demora mais de 1,2 s ganha a barra sozinha (no
  rodapé, se a tela tem a linha de dica; senão flutuando), com a etapa do servidor e a estimativa pela duração da
  mesma tarefa no mesmo projeto. Tarefa nova: pôr o rótulo dela em `ROTULOS` (progresso.js), pelo fim da rota.
- **No servidor, dar o andamento**: `_progresso(s, "etapa…")` a cada etapa; `_progresso(s, etapa, fracao=0.4)` quando
  a tarefa sabe quanto andou; ou "(i de n)" / "rodada i de até n" no texto da etapa. Toda rota de projeto já começa
  com uma etapa e a limpa no fim (`_tarefa_padrao`).
- Tarefa que roda sem chamada da tela (em segundo plano): `acompanhar({url, tarefa, rotulo, onde})` de progresso.js.
