# Compatibility exceptions module for vendored twelvedata package.

class TwelveDataError(Exception):
    pass

class InvalidApiKeyError(TwelveDataError):
    pass

class BadRequestError(TwelveDataError):
    pass

class InternalServerError(TwelveDataError):
    pass
