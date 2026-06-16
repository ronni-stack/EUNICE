"""EUNICE v0.8 — Authentication + Device/User Identity"""
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import API_KEY

security = HTTPBearer(auto_error=False)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key. Set it in Settings.")
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Wrong API key. Check Settings and try again.")
    return credentials.credentials


def get_current_user(request: Request) -> str:
    """
    Resolve user_id from request.
    Priority:
      1. X-EUNICE-Device-ID / X-EUNICE-User-ID header
      2. device_id field in JSON body (if already parsed by caller, not available here)
      3. Fallback to 'ronny' for backward compatibility
    """
    user_id = request.headers.get("X-EUNICE-Device-ID") or request.headers.get("X-EUNICE-User-ID")
    if user_id:
        return user_id.strip()
    return "ronny"
