class ScreenLockError(Exception):
    """Base exception for screen lock related errors"""
    pass

class LockFailedError(ScreenLockError):
    """Raised when screen locking fails"""
    pass

class StatusCheckError(ScreenLockError):
    """Raised when unable to determine lock status"""
    pass
