import subprocess
from typing import Optional
from datetime import datetime
from .exceptions import LockFailedError, StatusCheckError

class UbuntuScreenLock:
    """
    A class to manage screen locking on Ubuntu systems, optimized for Wayland.

    Example usage:
        >>> from ubuntu_screenlock import UbuntuScreenLock
        >>> locker = UbuntuScreenLock()
        >>> if not locker.is_locked():
        ...     locker.lock()
    """

    def __init__(self):
        self.lock_methods = [
            ["dbus-send", "--session", "--dest=org.gnome.ScreenSaver", "--type=method_call", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.Lock"],
            ["loginctl", "lock-session"]
        ]

        self.status_methods = [
            self._check_via_loginctl,
            self._check_via_dbus
        ]

    def is_locked(self) -> bool:
        """
        Check if the screen is currently locked.

        Returns:
            bool: True if screen is locked, False if unlocked

        Raises:
            StatusCheckError: If unable to determine lock status
        """
        # First check if there's no active graphical session
        if not self._has_active_graphical_session():
            print(f"[{datetime.now()}] No active graphical session found - considering as locked")
            return True

        for method in self.status_methods:
            try:
                return method()
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"[{datetime.now()}] Status check failed for {method.__name__}: {e}")
                continue

        raise StatusCheckError("Could not determine screen lock status")

    def lock(self) -> None:
        """
        Lock the screen immediately.

        Raises:
            LockFailedError: If screen locking fails
        """
        for method in self.lock_methods:
            try:
                print(f"[{datetime.now()}] Trying lock method: {method}")
                if "loginctl" in method[0]:
                    session_id = self._get_current_session_id()
                    if session_id:
                        subprocess.run(["loginctl", "lock-session", session_id], check=True)
                        print(f"[{datetime.now()}] Locked using loginctl with session {session_id}")
                        return
                    else:
                        print(f"[{datetime.now()}] No session ID found for loginctl")
                        continue
                else:
                    subprocess.run(method, check=True)
                    print(f"[{datetime.now()}] Locked using {method[0]}")
                    return
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"[{datetime.now()}] Failed lock method {method}: {e}")
                continue

        raise LockFailedError("All screen lock methods failed")

    def _has_active_graphical_session(self) -> bool:
        """Check if there's an active graphical session for the current user"""
        try:
            username = subprocess.getoutput("whoami")
            output = subprocess.check_output(
                ["loginctl", "list-sessions", "--no-legend"]
            ).decode().splitlines()

            for line in output:
                parts = line.split()
                if len(parts) >= 8 and parts[2] == username:
                    # Check if this is a graphical session (seat0) and class is 'user'
                    if parts[3] == "seat0" and parts[5] == "user":
                        # Additional check to see if the session is active
                        session_id = parts[0]
                        session_info = subprocess.check_output(
                            ["loginctl", "show-session", session_id]
                        ).decode()

                        # Check if it's an active session
                        if "Active=yes" in session_info:
                            return True

            print(f"[{datetime.now()}] No active graphical session found for user {username}")
            return False

        except Exception as e:
            print(f"[{datetime.now()}] Could not check for active graphical session: {e}")
            # If we can't determine, assume there is a session to avoid false positives
            return True

    def _get_current_session_id(self) -> Optional[str]:
        """Get the current session ID for the active graphical session"""
        try:
            output = subprocess.check_output(
                ["loginctl", "list-sessions", "--no-legend"]
            ).decode().splitlines()
            username = subprocess.getoutput("whoami")
            for line in output:
                parts = line.split()
                if len(parts) >= 8 and parts[2] == username and parts[3] == "seat0":
                    return parts[0]
            print(f"[{datetime.now()}] No graphical session found for user {username}")
        except Exception as e:
            print(f"[{datetime.now()}] Could not retrieve session ID: {e}")
        return None

    def _check_via_loginctl(self) -> bool:
        """Check lock status using loginctl"""
        try:
            sessions = subprocess.check_output(
                ["loginctl", "list-sessions", "--no-legend"]
            ).decode().splitlines()

            if not sessions:
                return False

            session_id = self._get_current_session_id()
            if not session_id:
                return False

            output = subprocess.check_output(
                ["loginctl", "show-session", session_id]
            ).decode()

            return "LockedHint=yes" in output
        except subprocess.CalledProcessError as e:
            print(f"[{datetime.now()}] loginctl check failed: {e}")
            raise

    def _check_via_dbus(self) -> bool:
        """Check lock status using D-Bus for GNOME/Wayland"""
        try:
            output = subprocess.check_output(
                ["dbus-send", "--session", "--dest=org.gnome.ScreenSaver", "--print-reply",
                 "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.GetActive"],
                stderr=subprocess.PIPE
            ).decode()
            return "boolean true" in output.lower()
        except subprocess.CalledProcessError as e:
            print(f"[{datetime.now()}] D-Bus status check failed: {e}")
            raise
