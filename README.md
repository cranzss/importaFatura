# Fatura Parser

Aplicação Python que extrai dados de faturas de cartão em PDF e produz um JSON
padronizado, validado e pronto para alimentar dashboards de gastos.

Este repositório contém o primeiro MVP do motor de importação. A interface web
e o dashboard serão construídos em etapas futuras sobre o contrato JSON já
definido.

## Estado atual

| Emissor | Detecção | Extração completa |
| --- | --- | --- |
| Inter | Sim | Sim |
| Mercado Pago | Sim | Sim |

O parser do Inter atualmente extrai:

- Informações gerais da fatura, como vencimento, total e pagamento mínimo.
- Resumos separados para cada cartão encontrado.
- Transações, valores, datas, parcelas e tipos contábeis.
- Validação entre o total declarado e a soma das transações.
- Metadados técnicos para identificar a origem do JSON.

O parser do Mercado Pago entrega o mesmo contrato, incluindo pagamentos gerais
sem cartão e inferência do ano quando a transação informa apenas dia e mês.

## Como o processamento funciona

```mermaid
flowchart LR
    PDF["Fatura em PDF"] --> EXTRACT["pdf_extractor.py<br/>extrai texto e metadados"]
    EXTRACT --> DETECT["issuer_detector.py<br/>identifica o emissor"]
    DETECT --> PARSER["parsers/inter.py<br/>interpreta os campos"]
    PARSER --> VALIDATE["validation.py<br/>reconcilia os valores"]
    VALIDATE --> RESULT["StatementParseResult<br/>modelo completo"]
    RESULT --> JSON["JSON padronizado"]
```

O `statement_parser.py` coordena essas etapas. Os Models do Pydantic garantem
que cada bloco respeite o formato esperado antes da geração do JSON.

## Requisitos

- Python 3.12 ou superior.
- PowerShell para executar os exemplos abaixo no Windows.
- `uv` recomendado para instalar exatamente as dependências travadas.

## Preparando o ambiente

Na raiz do projeto:

```powershell
py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements-dev.lock
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
```

O primeiro comando cria um ambiente isolado. O segundo instala as versões e os
hashes registrados no lockfile. O terceiro instala este projeto em modo
editável, permitindo alterar o código sem reinstalá-lo a cada mudança.

## Gerando o JSON

Coloque a fatura real dentro de `samples/private/`. Essa pasta é ignorada pelo
Git.

```powershell
.venv\Scripts\fatura-parser.exe samples/private/inter.pdf
```

Por padrão, o JSON será criado em `output/inter.json`. Para escolher outro
caminho:

```powershell
.venv\Scripts\fatura-parser.exe samples/private/inter.pdf --output output/minha-fatura.json
```

Para um PDF protegido, solicite a senha de forma oculta:

```powershell
.venv\Scripts\fatura-parser.exe samples/private/inter.pdf --password-prompt
```

O exportador bloqueia por padrão resultados com divergências ou avisos. A opção
`--allow-warnings` existe somente para gerar um arquivo destinado à revisão
manual.

## Inspecionando a extração

O inspetor mostra informações técnicas e oculta os dados financeiros por
padrão:

```powershell
.venv\Scripts\python.exe examples/inspect_pdf.py samples/private/inter.pdf
```

Para exibir o conteúdo completo, incluindo uma página específica:

```powershell
.venv\Scripts\python.exe examples/inspect_pdf.py samples/private/inter.pdf --show-sensitive-data --page 4
```

Use o modo sensível apenas em um terminal privado. A saída pode permanecer no
histórico, em logs ou em capturas de tela.

## Executando os testes

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes criam PDFs e documentos sintéticos em memória. Nenhuma fatura real é
necessária ou deve ser adicionada às fixtures.

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `src/fatura_parser/` | Código principal da biblioteca e da CLI. |
| `src/fatura_parser/parsers/` | Regras específicas de cada emissor. |
| `tests/` | Testes automatizados com dados sintéticos. |
| `examples/` | Inspetor didático e exemplo do JSON final. |
| `docs/` | Contrato JSON e gerenciamento de dependências. |
| `samples/private/` | PDFs reais locais, sempre ignorados pelo Git. |
| `output/` | JSONs gerados localmente, também ignorados pelo Git. |

## Segurança e privacidade

- PDFs são ignorados globalmente pelo `.gitignore`.
- PDFs reais e JSONs gerados não devem ser enviados ao GitHub.
- Senhas de PDFs são solicitadas por uma entrada oculta.
- A quantidade e o tamanho das páginas processadas possuem limites.
- A gravação do JSON é atômica para evitar arquivos parciais.
- Dependências são travadas com versões e hashes e podem ser auditadas.
- Dados completos só são mostrados pelo inspetor após autorização explícita.

Antes de qualquer commit, confira `git status` e confirme que nenhum documento
financeiro está listado.

## Documentação complementar

- [Contrato do JSON](docs/json-contract.md)
- [Dependências e auditoria de segurança](docs/dependencies.md)
- [Uso seguro das faturas locais](samples/README.md)

## Próximas etapas

- Ampliar as fixtures sintéticas para novas versões de fatura.
- Construir a API que receberá os PDFs.
- Criar o dashboard com visualização por cartão, banco e período.
