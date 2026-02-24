# coding: utf-8

class TwelveDataError(Exception):
    """Base exception for Twelvedata SDK compatibility."""


class InvalidApiKeyError(TwelveDataError):
    pass


class BadRequestError(TwelveDataError):
    pass


class InternalServerError(TwelveDataError):
    pass
