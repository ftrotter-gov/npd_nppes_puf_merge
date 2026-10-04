#!/usr/bin/env python3
"""
Compatibility shim for the ``inlaw`` package (https://pypi.org/project/inlaw/).

Two upstream issues in inlaw 0.1.0 need to be worked around so that the
Step40 tests can use InLaw as documented:

1. Packaging: the wheel ships its modules under a generic top level ``src``
   package rather than ``inlaw``, so the documented ``from inlaw import InLaw``
   raises ModuleNotFoundError. We locate the classes wherever they happen to
   live.

2. Great Expectations 1.x API drift: ``InLaw.sql_to_gx_df()`` calls
   ``context.sources.pandas_default`` which was removed in GX 1.0 (it is now
   ``context.data_sources.pandas_default``). In addition GX 1.x returns a
   ``Batch`` object whose expectations are run via ``batch.validate(...)``
   rather than the legacy ``expect_*`` convenience methods.

This module re-exports ``InLaw``, ``DBTable`` and ``InlawError`` and patches
``sql_to_gx_df`` so that the returned object once again supports the
``gx_df.expect_column_values_to_be_between(...)`` style used throughout the
InLaw documentation.
"""
from __future__ import annotations

import pandas as pd
import sqlalchemy

# ---------------------------------------------------------------------------
# 1. Import InLaw regardless of which package name the wheel installed under.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depends on how inlaw was installed
    from inlaw import InLaw, DBTable  # type: ignore
    from inlaw import InlawError  # type: ignore
except ImportError:  # inlaw 0.1.0 installs as the top level "src" package
    from src.inlaw import InLaw, InlawError  # type: ignore
    from src.dbtable import DBTable  # type: ignore

import great_expectations as gx
from great_expectations import expectations as gxe


__all__ = ["InLaw", "DBTable", "InlawError", "GXValidatorAdapter"]


class GXValidatorAdapter:
    """
    Adapts a Great Expectations 1.x ``Batch`` to the legacy validator API.

    Only the handful of expectations this project needs are mapped. Each
    method accepts the same keyword arguments as the legacy API and returns the
    native GX ``ExpectationValidationResult`` (so ``.success`` and ``.result``
    behave exactly as the InLaw docs describe).
    """

    _EXPECTATION_MAP = {
        "expect_column_values_to_be_between": gxe.ExpectColumnValuesToBeBetween,
        "expect_column_values_to_be_unique": gxe.ExpectColumnValuesToBeUnique,
        "expect_column_values_to_not_be_null": gxe.ExpectColumnValuesToNotBeNull,
        "expect_column_values_to_be_null": gxe.ExpectColumnValuesToBeNull,
        "expect_column_values_to_be_in_set": gxe.ExpectColumnValuesToBeInSet,
        "expect_table_row_count_to_equal": gxe.ExpectTableRowCountToEqual,
        "expect_table_row_count_to_be_between": gxe.ExpectTableRowCountToBeBetween,
    }

    def __init__(self, batch):
        self._batch = batch

    def __getattr__(self, name):
        expectation_class = self._EXPECTATION_MAP.get(name)
        if expectation_class is None:
            raise AttributeError(
                f"{type(self).__name__} does not map the GX expectation {name!r}. "
                f"Available: {sorted(self._EXPECTATION_MAP)}"
            )

        def _run(**kwargs):
            return self._batch.validate(expectation_class(**kwargs))

        return _run


def _sql_to_gx_df(*, sql: str, engine):
    """GX 1.x compatible replacement for ``InLaw.sql_to_gx_df``."""
    try:
        with engine.connect() as connection:
            pandas_df = pd.read_sql_query(sqlalchemy.text(sql), connection)

        context = gx.get_context(mode="ephemeral")
        batch = context.data_sources.pandas_default.read_dataframe(pandas_df)
        return GXValidatorAdapter(batch)
    except Exception as exc:  # mirror upstream error semantics
        raise RuntimeError(f"Failed to execute SQL and create GX DataFrame: {exc}")


def _to_gx_dataframe(sql: str, engine):
    """Legacy positional-argument alias, as provided by upstream InLaw."""
    return _sql_to_gx_df(sql=sql, engine=engine)


# ---------------------------------------------------------------------------
# 2. Patch the upstream class in place so InLaw.run_all() keeps working.
# ---------------------------------------------------------------------------
InLaw.sql_to_gx_df = staticmethod(_sql_to_gx_df)  # type: ignore[assignment]
InLaw.to_gx_dataframe = staticmethod(_to_gx_dataframe)  # type: ignore[assignment]
