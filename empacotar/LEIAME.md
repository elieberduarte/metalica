# Empacotamento do Metálica

Gera o programa instalável para Windows a partir do mesmo código de `sistema/`. Não existe
uma versão "site" e outra "software": o desenvolvimento continua com `python app.py`, e
este roteiro só embrulha o resultado.

```bash
pip install pyinstaller
winget install JRSoftware.InnoSetup
python empacotar/construir.py
```

| Saída | O que é |
|---|---|
| `%TEMP%\metalica-build\dist\Metalica\Metalica.exe` | o programa, em pasta, com o Python e as bibliotecas dentro (cerca de 85 MB). Fica fora do projeto: dentro do OneDrive a construção falha com "acesso negado", porque ele trava arquivos enquanto sincroniza |
| `empacotar/saida/Metalica-<versão>-instalador.exe` | o instalador (cerca de 30 MB) |

## O que muda no programa instalado

- **Janela própria.** Abre o Edge ou o Chrome em modo aplicativo, sem abas nem barra de
  endereço, com perfil separado do navegador do usuário. Fechar a janela encerra o programa.
  Um segundo clique no atalho mostra a instância que já está aberta em vez de subir outra.
- **Dados em `Documentos\Metálica`.** A pasta de instalação não aceita escrita. Ali ficam
  os projetos, os modelos do editor, os arquivos gerados e o registro `metalica.log`.
  `--dados pasta` ou a variável `METALICA_DADOS` mudam o lugar. A desinstalação não apaga.
- **Porta livre.** Usa a 8765 se estiver livre, senão a que o sistema indicar.
- **Versão e impressão digital no memorial.** A capa imprime, por exemplo,
  `Metálica 0.1.0 · núcleo c4aafb88c97b`. A impressão é o SHA-256 dos fontes de `nucleo/`,
  calculada aqui no empacotamento (no executável os fontes não existem). Ver `sistema/versao.py`.

## Para lançar uma versão

1. Mude `VERSAO` em `sistema/versao.py`.
2. Rode os testes: `python -m pytest sistema/testes -q`.
3. Rode `python empacotar/construir.py`.
4. Anote a impressão do núcleo que o roteiro imprime: é ela que confere um memorial contestado.

## O que vai junto que não é código

`web/`, `dados/perfis.json`, `saida/memorial.css` e `manual/lib/paged.polyfill.js` (a
paginação do memorial, que no desenvolvimento é achada na pasta do manual). Os módulos
procuram esses arquivos por caminho relativo ao próprio `__file__`, então o roteiro repete
a estrutura de pastas dentro do pacote. Recurso novo lido do disco precisa entrar na lista
`dados` de `construir.py`, senão funciona no desenvolvimento e falha no instalado.

## Ainda não feito

Assinatura de código (o Windows mostra "editor desconhecido" na instalação), atualização
automática, chave de licença e ícone próprio (`empacotar/metalica.ico`, se existir, é usado).
