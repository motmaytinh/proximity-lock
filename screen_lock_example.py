from ubuntu_screenlock import UbuntuScreenLock, StatusCheckError, LockFailedError

try:
    locker = UbuntuScreenLock()

    if not locker.is_locked():
        locker.lock()
except StatusCheckError as e:
    print(f"Could not check lock status: {e}")
except LockFailedError as e:
    print(f"Failed to lock screen: {e}")
