from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import Config
from app.models.schemas import User, UserInDB, TokenData

# Password context for hashing
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    test_hash = pwd_context.hash("test_password")
    pwd_context.verify("test_password", test_hash)
except Exception as e:
    print(f"Warning: bcrypt error - {str(e)}. Using fallback scheme")
    pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, Config.JWT_SECRET_KEY, algorithm=Config.ALGORITHM)


def _get_user_manager():
    """Lazy import to avoid circular dependency."""
    from app.services.user_manager import UserManager

    if not hasattr(_get_user_manager, "_instance"):
        _get_user_manager._instance = UserManager()
    return _get_user_manager._instance


def set_user_manager(manager):
    """Allow main app to inject the shared UserManager instance."""
    _get_user_manager._instance = manager


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, Config.JWT_SECRET_KEY, algorithms=[Config.ALGORITHM]
        )
        username: str = payload.get("sub")
        is_host: bool = payload.get("is_host", False)
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, is_host=is_host)
    except JWTError:
        raise credentials_exception

    try:
        user_manager = _get_user_manager()
        if token_data.username == Config.HOST_USERNAME:
            user = UserInDB(
                username=Config.HOST_USERNAME,
                hashed_password=get_password_hash("__placeholder__"),
                is_host=True,
                email="admin@example.com",
            )
        else:
            user = user_manager.get_user(username=token_data.username)

        if user is None:
            raise credentials_exception

        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            is_host=user.is_host or token_data.is_host,
        )
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_user_optional(
    token: str = Depends(oauth2_scheme_optional),
) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, Config.JWT_SECRET_KEY, algorithms=[Config.ALGORITHM]
        )
        username: str = payload.get("sub")
        is_host: bool = payload.get("is_host", False)
        if username is None:
            return None
        token_data = TokenData(username=username, is_host=is_host)
    except (JWTError, Exception):
        return None

    try:
        user_manager = _get_user_manager()
        if token_data.username == Config.HOST_USERNAME:
            user = UserInDB(
                username=Config.HOST_USERNAME,
                hashed_password=get_password_hash("__placeholder__"),
                is_host=True,
                email="admin@example.com",
            )
        else:
            user = user_manager.get_user(username=token_data.username)

        if user is None:
            return None

        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            is_host=user.is_host or token_data.is_host,
        )
    except Exception:
        return None


async def get_host_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_host and current_user.username != Config.HOST_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as host admin",
        )
    return current_user
