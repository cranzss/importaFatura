# Contrato JSON das faturas

## Objetivo

Este documento define o formato padronizado produzido pelos parsers de fatura.
O mesmo formato será utilizado pelo Inter, Mercado Pago e por futuros emissores.

O contrato separa quatro conceitos:

1. O arquivo PDF utilizado como fonte.
2. Os dados gerais da fatura.
3. Os cartões e seus subtotais.
4. As transações encontradas no documento.

## Princípios

- Valores monetários são representados em centavos inteiros.
- Datas usam o padrão ISO `YYYY-MM-DD`.
- Compras e encargos que aumentam a fatura possuem valor positivo.
- Pagamentos, créditos e estornos possuem valor negativo.
- Uma transação informa explicitamente se participa do total da fatura atual.
- Dados pessoais que não ajudam o dashboard não são incluídos.
- Incertezas e diferenças de valores são informadas, nunca ocultadas.

## Estrutura principal

| Campo | Descrição |
| --- | --- |
| `schema_version` | Versão deste contrato JSON. |
| `parser` | Identifica o parser e sua versão. |
| `source` | Metadados técnicos do PDF de origem. |
| `statement` | Datas e totais gerais da fatura. |
| `cards` | Cartões encontrados e seus subtotais. |
| `transactions` | Movimentações extraídas do documento. |
| `validation` | Resultado da reconciliação dos valores. |

## Identificação dos cartões

Cada cartão recebe um `card_id` estável dentro do emissor. Inicialmente, ele será
formado pelo emissor e pelos quatro últimos dígitos, como `inter:1234`.

O campo `card_last_four` permite apresentar nomes amigáveis na interface, como
"Inter final 1234", sem armazenar o número completo do cartão.

Se dois cartões do mesmo emissor tiverem os mesmos quatro últimos dígitos, o
parser deverá emitir um aviso de ambiguidade em vez de unir os dados em silêncio.

O subtotal de cada cartão fica em `declared_total_cents`. A soma desses subtotais
deve ser igual a `statement.declared_total_cents` quando o documento informar os
subtotais.

## Transações

Cada item de `transactions` contém:

| Campo | Descrição |
| --- | --- |
| `transaction_id` | Identificador determinístico para detectar duplicidades. |
| `card_id` | Cartão ao qual a movimentação pertence. |
| `date` | Data normalizada da movimentação. |
| `date_inferred` | Indica se alguma parte da data foi deduzida pelo parser. |
| `description` | Descrição original apresentada na fatura. |
| `amount_cents` | Valor com sinal, representado em centavos. |
| `type` | Classificação contábil inicial da movimentação. |
| `included_in_statement_total` | Indica se o valor compõe a fatura atual. |
| `installment` | Parcela atual e quantidade total, quando aplicável. |
| `source_page` | Página do PDF usada para auditoria. |

### Tipos iniciais

| Tipo | Uso |
| --- | --- |
| `purchase` | Compra comum ou parcelada. |
| `payment` | Pagamento de uma fatura anterior. |
| `refund` | Estorno ou devolução. |
| `fee` | Tarifa cobrada pelo emissor. |
| `interest` | Juros ou encargos financeiros. |
| `tax` | Tributos como IOF. |
| `cash_advance` | Saque ou operação equivalente. |
| `other` | Linha válida que ainda não possui classificação específica. |

`type` não representa a categoria do dashboard. Por exemplo, uma compra em um
restaurante terá `type: "purchase"`; sua categoria "Alimentação" será adicionada
em uma etapa posterior do sistema.

## Regra de reconciliação

O total calculado considera somente transações com
`included_in_statement_total: true`:

```text
computed_total_cents = soma de amount_cents das transações incluídas
difference_cents = declared_total_cents - computed_total_cents
reconciled = difference_cents == 0
```

Pagamentos anteriores podem aparecer no histórico com valor negativo, mas usam
`included_in_statement_total: false` e não alteram o total da fatura atual.

### Avisos de validação

Cada item de `validation.warnings` possui:

| Campo | Descrição |
| --- | --- |
| `code` | Código estável em letras maiúsculas, como `TOTAL_MISMATCH`. |
| `message` | Explicação legível do problema encontrado. |
| `source_page` | Página relacionada ao aviso, ou `null` para toda a fatura. |

Avisos representam problemas não fatais. O parser ainda pode devolver o JSON,
mas o resultado deve ser revisado antes de alimentar análises definitivas.

## Privacidade

O JSON não deve conter nome do titular, CPF, endereço, QR Code, código de barras,
número completo do cartão ou caminho absoluto do PDF.

O nome simples do arquivo e seu hash SHA-256 são mantidos para auditoria e
detecção de importações repetidas.

Um exemplo completo e fictício está em `examples/statement.example.json`.
