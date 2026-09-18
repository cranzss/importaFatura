# Faturas de exemplo

Coloque as faturas reais usadas durante o desenvolvimento dentro de
`samples/private/`.

Essa pasta está declarada no `.gitignore`. Portanto, seus PDFs não serão
incluídos em commits do Git.

Como proteção adicional, o `.gitignore` ignora arquivos PDF em qualquer pasta
do projeto, inclusive variações como `.pdf`, `.PDF` e `.Pdf`. Isso reduz o risco
de uma fatura ser versionada caso seja colocada fora de `samples/private/`.

Se futuramente precisarmos versionar um PDF sintético, devemos criar uma exceção
específica no `.gitignore` somente depois de revisar o arquivo e confirmar que ele
não possui dados reais. Não use inclusão forçada para contornar essa proteção.

Sugestão de nomes:

- `samples/private/inter.pdf`
- `samples/private/mercado-pago.pdf`

Antes de compartilhar o projeto, execute `git status` e confirme que nenhum
documento financeiro aparece na lista de arquivos versionados.

## Inspecionando uma fatura

O inspetor oculta por padrão o nome do arquivo, o hash, os totais, os cartões,
as transações e o texto bruto das páginas:

```powershell
python examples/inspect_pdf.py samples/private/inter.pdf
```

Para uma depuração que realmente precise desses dados, autorize explicitamente
a saída sensível:

```powershell
python examples/inspect_pdf.py samples/private/inter.pdf --show-sensitive-data
```

O texto bruto de uma página exige a mesma autorização:

```powershell
python examples/inspect_pdf.py samples/private/inter.pdf --show-sensitive-data --page 4
```

Use o modo sensível somente em um terminal privado. O conteúdo pode permanecer
no histórico de rolagem, em logs, capturas de tela ou gravações do terminal.
