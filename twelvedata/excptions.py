#excptions.py
diff --git a/twelvedata/exceptions.py b/twelvedata/exceptions.py
new file mode 100644
index 0000000000000000000000000000000000000000..9c0d95092a374742837b0ee2868c41661b855305
--- /dev/null
+++ b/twelvedata/exceptions.py
@@ -0,0 +1,20 @@
+# coding: utf-8
+"""Compatibility module.
+
+The vendored SDK historically shipped `excptions.py` (typo) while internal
+imports use `exceptions.py`. Keep both paths working.
+"""
+
+from .excptions import (  # noqa: F401
+    TwelveDataError,
+    BadRequestError,
+    InternalServerError,
+    InvalidApiKeyError,
+)
+
+__all__ = (
+    "TwelveDataError",
+    "BadRequestError",
+    "InternalServerError",
+    "InvalidApiKeyError",
+)

__all__ = (
    "TwelveDataError",
    "BadRequestError",
    "InternalServerError",
    "InvalidApiKeyError",
)


class TwelveDataError(RuntimeError):
    pass


class BadRequestError(TwelveDataError):
    pass


class InternalServerError(TwelveDataError):
    pass


class InvalidApiKeyError(TwelveDataError):
    pass
