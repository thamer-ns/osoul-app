"""Compatibility shim.

Some deployments or older code may reference `financial_analysis.init`.
This file re-exports the public API from `financial_analysis` package.
"""

from .__init__ import *  # noqa: F401,F403
