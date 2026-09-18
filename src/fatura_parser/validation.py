from fatura_parser.models import (
    CardSummary,
    StatementInfo,
    Transaction,
    ValidationInfo,
    ValidationWarning,
)


def build_validation_info(
    statement: StatementInfo,
    cards: list[CardSummary],
    transactions: list[Transaction],
) -> ValidationInfo:
    """Reconcile extracted transactions with statement and card totals."""
    included_transactions = [
        transaction
        for transaction in transactions
        if transaction.included_in_statement_total
    ]

    computed_total_cents = sum(
        transaction.amount_cents
        for transaction in included_transactions
    )

    difference_cents = (
        statement.declared_total_cents
        - computed_total_cents
    )

    warnings: list[ValidationWarning] = []

    if difference_cents != 0:
        warnings.append(
            ValidationWarning(
                code="TOTAL_MISMATCH",
                message=(
                    "Declared statement total differs from the computed "
                    f"total by {difference_cents} cents."
                ),
                source_page=None,
            )
        )

    computed_total_by_card: dict[str, int] = {}
    for transaction in included_transactions:
        if transaction.card_id is None:
            continue

        computed_total_by_card[transaction.card_id] = (
            computed_total_by_card.get(transaction.card_id, 0)
            + transaction.amount_cents
        )

    for card in cards:
        computed_card_total_cents = computed_total_by_card.get(
            card.card_id,
            0,
        )
        card_difference_cents = (
            card.declared_total_cents
            - computed_card_total_cents
        )

        if card_difference_cents != 0:
            warnings.append(
                ValidationWarning(
                    code="CARD_TOTAL_MISMATCH",
                    message=(
                        f"Declared total for {card.card_id} differs from "
                        "the computed total by "
                        f"{card_difference_cents} cents."
                    ),
                    source_page=None,
                )
            )

    return ValidationInfo(
        transaction_count=len(transactions),
        included_transaction_count=len(included_transactions),
        computed_total_cents=computed_total_cents,
        declared_total_cents=statement.declared_total_cents,
        difference_cents=difference_cents,
        reconciled=difference_cents == 0,
        warnings=warnings,
    )
