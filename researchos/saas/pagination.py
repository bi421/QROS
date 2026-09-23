"""Shared public-list pagination, filtering, and sorting contract."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
SORT_ORDERS = frozenset({"asc", "desc"})


class PaginationParameterError(ValueError):
    """Client supplied an invalid list parameter."""

    def __init__(self, message: str, *, code: str = "INVALID_PAGINATION") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ListQuery:
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    sort_by: str = "created_at"
    sort_order: str = "desc"
    status: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def parse_list_query(
    *,
    page: str = "1",
    page_size: str = "20",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    status: str | None = None,
    allowed_sort_fields: frozenset[str],
) -> ListQuery:
    try:
        parsed_page = int(page)
    except (TypeError, ValueError) as exc:
        raise PaginationParameterError("page must be a positive integer") from exc
    try:
        parsed_page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise PaginationParameterError("page_size must be an integer") from exc

    if parsed_page < 1:
        raise PaginationParameterError("page must be >= 1")
    if parsed_page_size < 1 or parsed_page_size > MAX_PAGE_SIZE:
        raise PaginationParameterError(
            f"page_size must be between 1 and {MAX_PAGE_SIZE}"
        )

    normalized_sort = sort_by.strip()
    if normalized_sort not in allowed_sort_fields:
        raise PaginationParameterError(
            f"invalid sort field: {normalized_sort}",
            code="INVALID_SORT",
        )

    normalized_order = sort_order.strip().lower()
    if normalized_order not in SORT_ORDERS:
        raise PaginationParameterError(
            "sort_order must be 'asc' or 'desc'",
            code="INVALID_SORT_ORDER",
        )

    normalized_status = status.strip() if status is not None else None
    return ListQuery(
        page=parsed_page,
        page_size=parsed_page_size,
        sort_by=normalized_sort,
        sort_order=normalized_order,
        status=normalized_status or None,
    )


def pagination_envelope(
    *,
    data: list[object],
    page: int,
    page_size: int,
    total: int,
) -> dict[str, object]:
    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        },
    }


__all__ = [
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ListQuery",
    "PaginationParameterError",
    "pagination_envelope",
    "parse_list_query",
]
