import os

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from keel.domain.errors import InvalidPasswordError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# Library defaults (Argon2id) in production. Tests set this so the suite does
# not spend a full hash on every sign-in. Do not set it on a server.
if os.environ.get("KEEL_FAST_PASSWORD_HASH") == "1":
    _hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
else:
    _hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("keel-dummy-password-not-a-secret")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except VerificationError:
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def burn_password_check(password: str) -> None:
    """Spend a hash verification so a missing user is not cheaper to probe."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except VerificationError:
        return


def validate_password(password: str, username: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"A password must be at least {MIN_PASSWORD_LENGTH} characters.",
            limit=MIN_PASSWORD_LENGTH,
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"A password may be at most {MAX_PASSWORD_LENGTH} characters.",
            limit=MAX_PASSWORD_LENGTH,
        )
    if password.casefold() == username.strip().casefold():
        raise InvalidPasswordError("A password must not match the username.")
