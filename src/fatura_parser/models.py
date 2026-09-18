"""Validated models used by every statement parser."""

from datetime import date as Date
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
    TypeAdapter,
)

from fatura_parser.enums import Issuer, TransactionType


def _validate_supported_card_id(card_id: str) -> None:
    """Raise an error when a card identifier uses an unknown issuer."""
    issuer_value = card_id.split(":", maxsplit=1)[0]
    Issuer(issuer_value)


class SourceInfo(BaseModel):
    """Technical metadata about the PDF used as the parsing source."""

    model_config = ConfigDict(extra="forbid", strict=True)

    issuer: Issuer
    filename: str = Field(min_length=1)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: PositiveInt

    @field_validator("filename")
    @classmethod
    def ensure_filename_is_a_simple_pdf_name(cls, value: str) -> str:
        """Prevent local paths from leaking into the exported JSON."""
        if "/" in value or "\\" in value:
            raise ValueError("filename must not contain a path")

        if not value.lower().endswith(".pdf"):
            raise ValueError("filename must use the .pdf extension")

        filename_stem = value[:-4]
        if not filename_stem.strip():
            raise ValueError("filename must have a name before the extension")

        return value


class ParserInfo(BaseModel):
    """Identity and version of the bank-specific parser used."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: Issuer
    version: str = Field(
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
    )


class StatementInfo(BaseModel):
    """Dates and declared totals that apply to the whole statement."""

    model_config = ConfigDict(extra="forbid", strict=True)

    due_date: Date
    closing_date: Date | None = None
    currency: Literal["BRL"]
    declared_total_cents: int
    minimum_payment_cents: NonNegativeInt | None = None

    @model_validator(mode="after")
    def ensure_dates_and_totals_are_consistent(self) -> Self:
        """Reject impossible date order and minimum payment values."""
        if self.closing_date is not None and self.closing_date > self.due_date:
            raise ValueError("closing_date cannot be after due_date")

        payable_total_cents = max(self.declared_total_cents, 0)
        if (
            self.minimum_payment_cents is not None
            and self.minimum_payment_cents > payable_total_cents
        ):
            raise ValueError("minimum payment cannot be greater than payable total")

        return self


class ValidationWarning(BaseModel):
    """Non-fatal issue that should be visible to users and developers."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1)
    source_page: PositiveInt | None = None

    @field_validator("message")
    @classmethod
    def ensure_message_is_not_blank(cls, value: str) -> str:
        """Require a human-readable explanation for every warning."""
        if not value.strip():
            raise ValueError("warning message cannot be blank")

        return value


class ValidationInfo(BaseModel):
    """Auditable reconciliation between extracted and declared values."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transaction_count: NonNegativeInt
    included_transaction_count: NonNegativeInt
    computed_total_cents: int
    declared_total_cents: int
    difference_cents: int
    reconciled: bool
    warnings: list[ValidationWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_reconciliation_is_consistent(self) -> Self:
        """Keep counts, difference, and reconciliation flag mathematically valid."""
        if self.included_transaction_count > self.transaction_count:
            raise ValueError(
                "included transaction count cannot exceed total transaction count"
            )

        expected_difference = (
            self.declared_total_cents - self.computed_total_cents
        )
        if self.difference_cents != expected_difference:
            raise ValueError("difference does not match declared minus computed total")

        expected_reconciled = expected_difference == 0
        if self.reconciled != expected_reconciled:
            raise ValueError("reconciled flag does not match the total difference")

        return self


class CardSummary(BaseModel):
    """Declared subtotal for one card found in a statement."""

    model_config = ConfigDict(extra="forbid", strict=True)

    card_id: str = Field(pattern=r"^[a-z][a-z0-9_]*:\d{4}$")
    card_last_four: str = Field(pattern=r"^\d{4}$")
    declared_total_cents: int

    @model_validator(mode="after")
    def ensure_card_id_is_consistent(self) -> Self:
        """Require a supported issuer and matching display digits."""
        _validate_supported_card_id(self.card_id)

        if not self.card_id.endswith(f":{self.card_last_four}"):
            raise ValueError("card_id must end with card_last_four")

        return self


class Installment(BaseModel):
    """Installment information extracted from a transaction description."""

    model_config = ConfigDict(extra="forbid", strict=True)

    current: PositiveInt
    total: PositiveInt

    @model_validator(mode="after")
    def ensure_current_does_not_exceed_total(self) -> Self:
        """Reject impossible values such as installment 7 of 6."""
        if self.current > self.total:
            raise ValueError("current installment cannot be greater than total")

        return self


_CREDIT_TYPES = frozenset(
    {
        TransactionType.PAYMENT,
        TransactionType.REFUND,
    }
)

_CHARGE_TYPES = frozenset(
    {
        TransactionType.PURCHASE,
        TransactionType.FEE,
        TransactionType.INTEREST,
        TransactionType.TAX,
        TransactionType.CASH_ADVANCE,
    }
)


class Transaction(BaseModel):
    """One financial movement extracted from a statement."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transaction_id: str = Field(min_length=1)
    card_id: str | None = Field(
        pattern=r"^[a-z][a-z0-9_]*:\d{4}$",
    )
    date: Date
    date_inferred: bool
    description: str = Field(min_length=1)
    amount_cents: int
    type: TransactionType
    included_in_statement_total: bool
    installment: Installment | None = None
    source_page: PositiveInt

    @field_validator("transaction_id", "description")
    @classmethod
    def ensure_required_text_is_not_blank(cls, value: str) -> str:
        """Reject identifiers and descriptions made only of whitespace."""
        if not value.strip():
            raise ValueError("text cannot be blank")

        return value

    @model_validator(mode="after")
    def ensure_financial_rules_are_consistent(self) -> Self:
        """Validate card reference, amount sign, and installment usage."""
        if self.card_id is not None:
            _validate_supported_card_id(self.card_id)

        if self.card_id is None and self.included_in_statement_total:
            raise ValueError(
                "cardless transaction cannot be included in statement total"
            )

        if self.amount_cents == 0:
            raise ValueError("transaction amount cannot be zero")

        if self.type in _CREDIT_TYPES and self.amount_cents > 0:
            raise ValueError("credit transactions must have a negative amount")

        if self.type in _CHARGE_TYPES and self.amount_cents < 0:
            raise ValueError("charge transactions must have a positive amount")

        if self.installment is not None and self.type is not TransactionType.PURCHASE:
            raise ValueError("only purchases can have installment information")

        return self


class StatementParseResult(BaseModel):
    """Complete, validated, and serializable result of one PDF import."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1.0"]
    parser: ParserInfo
    source: SourceInfo
    statement: StatementInfo
    cards: list[CardSummary] = Field(min_length=1)
    transactions: list[Transaction]
    validation: ValidationInfo

    @model_validator(mode="after")
    def ensure_nested_models_are_consistent(self) -> Self:
        """Validate relationships and totals across the complete result."""
        if self.parser.name is not self.source.issuer:
            raise ValueError("parser name must match the source issuer")

        card_ids = [card.card_id for card in self.cards]
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("card ids must be unique")

        expected_card_prefix = f"{self.source.issuer.value}:"
        if any(
            not card_id.startswith(expected_card_prefix) for card_id in card_ids
        ):
            raise ValueError("every card must belong to the source issuer")

        declared_card_total = sum(
            card.declared_total_cents for card in self.cards
        )
        if declared_card_total != self.statement.declared_total_cents:
            raise ValueError("card subtotals must match the declared statement total")

        transaction_ids = [
            transaction.transaction_id for transaction in self.transactions
        ]
        if len(set(transaction_ids)) != len(transaction_ids):
            raise ValueError("transaction ids must be unique")

        known_card_ids = set(card_ids)
        if any(
            transaction.card_id is not None
            and transaction.card_id not in known_card_ids
            for transaction in self.transactions
        ):
            raise ValueError(
                "every card-linked transaction must reference a known card"
            )

        if any(
            transaction.source_page > self.source.page_count
            for transaction in self.transactions
        ):
            raise ValueError("transaction source page must exist in the PDF")

        if any(
            warning.source_page is not None
            and warning.source_page > self.source.page_count
            for warning in self.validation.warnings
        ):
            raise ValueError("warning source page must exist in the PDF")

        actual_transaction_count = len(self.transactions)
        included_transactions = [
            transaction
            for transaction in self.transactions
            if transaction.included_in_statement_total
        ]
        actual_included_count = len(included_transactions)
        actual_computed_total = sum(
            transaction.amount_cents for transaction in included_transactions
        )

        if self.validation.transaction_count != actual_transaction_count:
            raise ValueError("validation transaction count does not match the list")

        if self.validation.included_transaction_count != actual_included_count:
            raise ValueError("validation included count does not match the list")

        if self.validation.computed_total_cents != actual_computed_total:
            raise ValueError("validation computed total does not match transactions")

        if (
            self.validation.declared_total_cents
            != self.statement.declared_total_cents
        ):
            raise ValueError("validation declared total does not match the statement")

        return self
