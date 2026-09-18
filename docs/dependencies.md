# Dependências e segurança

Este projeto separa a declaração das dependências do travamento das versões.

## Qual é o papel de cada arquivo?

- `pyproject.toml` é a fonte que editamos manualmente. Ele declara quais
  bibliotecas o projeto aceita e os intervalos de versões compatíveis.
- `requirements.lock` fixa as versões usadas para executar a aplicação.
- `requirements-dev.lock` fixa as dependências da aplicação e também as
  ferramentas de teste e auditoria usadas durante o desenvolvimento.

Os arquivos `.lock` também registram os hashes dos pacotes. Durante a
instalação, `--require-hashes` faz o instalador rejeitar um arquivo que não
corresponda a um dos hashes aprovados.

Os lockfiles são gerados automaticamente. Não os edite manualmente.

## Como regenerar os lockfiles

Execute os comandos na raiz do projeto depois de alterar uma dependência no
`pyproject.toml`:

```powershell
uv pip compile pyproject.toml --universal --python-version 3.12 --generate-hashes --output-file requirements.lock
uv pip compile pyproject.toml --extra test --extra security --universal --python-version 3.12 --generate-hashes --output-file requirements-dev.lock
```

Depois de regenerar os arquivos, execute os testes e a auditoria antes de
aceitar a atualização.

## Como instalar o ambiente de desenvolvimento

Com o ambiente virtual já criado na pasta `.venv`:

```powershell
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements-dev.lock
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
```

O primeiro comando instala exatamente as versões e os arquivos registrados no
lockfile. O segundo instala o próprio projeto em modo editável, sem tentar
resolver novamente suas dependências.

## Como executar a auditoria

Com as dependências de desenvolvimento instaladas:

```powershell
.venv\Scripts\pip-audit.exe --require-hashes -r requirements.lock
.venv\Scripts\pip-audit.exe --require-hashes -r requirements-dev.lock
```

A auditoria verifica se as versões travadas possuem vulnerabilidades públicas
conhecidas. Um resultado limpo não garante que todo o projeto seja seguro: ele
não substitui revisão de código, testes, proteção dos PDFs e atualização
periódica das dependências.
