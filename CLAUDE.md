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
