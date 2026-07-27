# Osoli V4 Release Notes

This release applies the V4 engineering audit and adds persistent signed login sessions.

## Authentication

- A normal browser refresh no longer treats the asynchronous cookie component's warm-up state as a missing session.
- Valid signed sessions are restored after the browser cookie snapshot becomes ready.
- "Keep me signed in for 30 days" is enabled by default on the login form.
- Explicit logout still deletes the session cookie and clears authentication state.
- Persistent-session behavior is covered by `tests/test_persistent_login.py`.

## Analytics and data integrity

- Only completed candles are used by signal generation and backtesting.
- Non-finite values are removed before JSON persistence.
- RLS, divergence confirmation timing, and connected volume-profile value areas are corrected.
- Missing previous close no longer appears as a false 0% daily change.
- Stored fallback prices are marked stale and retain source lineage.
- Portfolio speculative exposure is weighted by market value.
- Database reads no longer hold an unused raw connection while SQLAlchemy performs the query.

The source was first validated by the atomic audit workflow before this documentation commit was added to trigger the repository's standard quality workflow on the final source tree.
