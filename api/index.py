from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import httpx
import jwt
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import math
import hashlib

# Create the main app
app = FastAPI(title="ObeyTriceWithRice API")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "rafflemaster")
client = MongoClient(MONGO_URL)
db = client[DB_NAME]
users_collection = db["users"]
settings_collection = db["settings"]
admin_logs_collection = db["admin_logs"]

# Admin Discord IDs (only these can access admin panel)
ADMIN_DISCORD_IDS = ["1397131765939830876", "1299293807287734302"]

# Discord OAuth Config
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "1470012790382264433")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "yjntumx86JMaaHHFBVicV4_m4PsIbzZV")
DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI", "https://trice-web-deploy.preview.emergentagent.com/api/auth/discord/callback")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://trice-web-deploy.preview.emergentagent.com")
JWT_SECRET = os.environ.get("JWT_SECRET", "obeytricewithrice-super-secret-key-2026")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Raffle Configuration (default, can be overridden by settings collection)
RAFFLE_CONFIG = {
    "start_date": "2026-02-01 00:00:00",
    "end_date": "2026-02-28 23:59:59",
    "tickets_per_wager": 20,  # 1 ticket per 20 wagered
    "prize_pool": 500,
    "prizes": [
        {"place": 1, "amount": 200},
        {"place": 2, "amount": 100},
        {"place": 3, "amount": 75},
        {"place": 4, "amount": 50},
        {"place": 5, "amount": 25},
        {"place": 6, "amount": 20},
        {"place": 7, "amount": 15},
        {"place": 8, "amount": 10},
        {"place": 9, "amount": 5}
    ]
}

# API Configuration for leaderboards
API_CONFIG = {
    "clash": {
        "base_url": "https://api.clash.gg/affiliates/detailed-summary/v2",
        "auth_token": os.environ.get("CLASH_API_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoicGFzcyIsInNjb3BlIjoiYWZmaWxpYXRlcyIsInVzZXJJZCI6MzYxNTM5MSwiaWF0IjoxNzYyMDgzNjU2LCJleHAiOjE5MTk4NzE2NTZ9.f5xbD1m3bgMlgAsjzh2-IcdMOFpNvumTGbCYHxSSS14"),
        "cookie": "let-me-in=top-secret-cookie-do-not-share",
        "start_date": "2026-02-02",
        "end_date": "2026-02-16 19:00:00",
        "prize_pool": 700,
        "currency": "gems",
        "prizes": [
            {"place": 1, "amount": 380},
            {"place": 2, "amount": 160},
            {"place": 3, "amount": 80},
            {"place": 4, "amount": 50},
            {"place": 5, "amount": 15},
            {"place": 6, "amount": 10},
            {"place": 7, "amount": 5}
        ]
    },
    "bsite": {
        "url": "https://api.b.site/leaderboard/connect-by-key",
        "api_key": os.environ.get("BSITE_API_KEY", "6959ede1-4887-4b50-9cad-6cb4d5517770"),
        "prize_pool": 800,
        "currency": "usd",
        "prizes": [
            {"place": 1, "amount": 400},
            {"place": 2, "amount": 200},
            {"place": 3, "amount": 100},
            {"place": 4, "amount": 50},
            {"place": 5, "amount": 30},
            {"place": 6, "amount": 15}
        ]
    },
    "csbattle": {
        "url": "https://api.csbattle.com/leaderboards/affiliates",
        "affiliate_id": os.environ.get("CSBATTLE_AFFILIATE_ID", "361eff9a-d63b-4f19-9b31-883c960c020d"),
        "start_date": "2026-02-02 18:30:00",
        "end_date": "2026-02-18 19:30:00",
        "prize_pool": 600,
        "currency": "coins",
        "prizes": [
            {"place": 1, "amount": 300},
            {"place": 2, "amount": 150},
            {"place": 3, "amount": 80},
            {"place": 4, "amount": 40},
            {"place": 5, "amount": 20},
            {"place": 6, "amount": 10}
        ]
    },
    "skinfans": {
        "url": "https://api.skin.fans/public/partnership.get-race",
        "token": os.environ.get("SKINFANS_TOKEN", "eb46a5130b38ecd87c8a3b3206f2c7ae"),
        "prize_pool": 500,
        "currency": "coins",
        "prizes": [
            {"place": 1, "amount": 300},
            {"place": 2, "amount": 120},
            {"place": 3, "amount": 50},
            {"place": 4, "amount": 20},
            {"place": 5, "amount": 10}
        ]
    }
}

# Pydantic models
class LinkedAccounts(BaseModel):
    clash_user_id: Optional[int] = None
    csbattle_uuid: Optional[str] = None
    skinfans_user_id: Optional[int] = None

class UserSettingsUpdate(BaseModel):
    linked_accounts: LinkedAccounts

class AdminUserUpdate(BaseModel):
    linked_accounts: Optional[LinkedAccounts] = None
    bans: Optional[dict] = None

class AdminBanRequest(BaseModel):
    ban_type: str  # "all_sites", "clash", "csbattle", "skinfans", "login"
    reason: Optional[str] = None

class AdminSettingsUpdate(BaseModel):
    raffle_start_date: Optional[str] = None
    raffle_end_date: Optional[str] = None
    raffle_prize_pool: Optional[int] = None
    clash_start_date: Optional[str] = None
    clash_end_date: Optional[str] = None
    csbattle_start_date: Optional[str] = None
    csbattle_end_date: Optional[str] = None

# Helper functions
def get_client_ip(request: Request) -> str:
    """Get client IP from request headers"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"

def get_device_fingerprint(request: Request) -> str:
    """Generate device fingerprint from headers"""
    user_agent = request.headers.get("user-agent", "")
    accept_lang = request.headers.get("accept-language", "")
    accept_enc = request.headers.get("accept-encoding", "")
    combined = f"{user_agent}|{accept_lang}|{accept_enc}"
    return hashlib.md5(combined.encode()).hexdigest()[:16]

def sanitize_username(username: str) -> str:
    try:
        return username.encode('utf-8', errors='replace').decode('utf-8')
    except:
        return "Unknown"

def mask_username(username: str, visible_chars: int = 2) -> str:
    username = sanitize_username(username)
    if len(username) <= visible_chars:
        return username
    return username[:visible_chars] + "*" * min(len(username) - visible_chars, 8)

def create_jwt_token(user_data: dict) -> str:
    payload = {
        "discord_id": user_data["discord_id"],
        "username": user_data["username"],
        "is_admin": user_data["discord_id"] in ADMIN_DISCORD_IDS,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

async def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("auth_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        return None
    
    payload = verify_jwt_token(token)
    if not payload:
        return None
    
    user = users_collection.find_one({"discord_id": payload["discord_id"]})
    if user:
        user["_id"] = str(user["_id"])
        user["is_admin"] = user["discord_id"] in ADMIN_DISCORD_IDS
    return user

async def require_admin(request: Request) -> dict:
    """Require admin access"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["discord_id"] not in ADMIN_DISCORD_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def log_admin_action(admin_id: str, action: str, target_id: str, details: dict = None):
    """Log admin actions for audit"""
    admin_logs_collection.insert_one({
        "admin_id": admin_id,
        "action": action,
        "target_id": target_id,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc)
    })

# Discord OAuth endpoints
@app.get("/api/auth/discord")
async def discord_login():
    """Redirect to Discord OAuth"""
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return RedirectResponse(url=discord_auth_url)

@app.get("/api/auth/discord/callback")
async def discord_callback(code: str, request: Request, response: Response):
    """Handle Discord OAuth callback"""
    # Get client info for tracking
    client_ip = get_client_ip(request)
    device_fp = get_device_fingerprint(request)
    user_agent = request.headers.get("user-agent", "")
    
    try:
        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": DISCORD_CLIENT_ID,
                    "client_secret": DISCORD_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": DISCORD_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if token_response.status_code != 200:
                logger.error(f"Discord token error: {token_response.text}")
                return RedirectResponse(url=f"{FRONTEND_URL}/raffle?error=auth_failed")
            
            token_data = token_response.json()
            access_token = token_data["access_token"]
            
            # Get user info
            user_response = await client.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if user_response.status_code != 200:
                logger.error(f"Discord user error: {user_response.text}")
                return RedirectResponse(url=f"{FRONTEND_URL}/raffle?error=auth_failed")
            
            discord_user = user_response.json()
        
        # Create or update user in database
        discord_id = discord_user["id"]
        username = discord_user["username"]
        avatar_hash = discord_user.get("avatar")
        avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png" if avatar_hash else None
        
        existing_user = users_collection.find_one({"discord_id": discord_id})
        
        # Check if user is login banned
        if existing_user and existing_user.get("bans", {}).get("login_banned"):
            return RedirectResponse(url=f"{FRONTEND_URL}/raffle?error=account_banned")
        
        now = datetime.now(timezone.utc)
        
        if existing_user:
            # Update existing user - add IP/device to arrays if not present
            update_data = {
                "username": username,
                "avatar": avatar_url,
                "user_agent": user_agent,
                "last_login": now,
                "updated_at": now
            }
            
            # Add IP to array if not already present
            users_collection.update_one(
                {"discord_id": discord_id},
                {
                    "$set": update_data,
                    "$addToSet": {
                        "ip_addresses": client_ip,
                        "device_fingerprints": device_fp
                    },
                    "$inc": {"login_count": 1},
                    "$push": {
                        "login_history": {
                            "$each": [{"ip": client_ip, "device": device_fp, "timestamp": now}],
                            "$slice": -50  # Keep last 50 logins
                        }
                    }
                }
            )
        else:
            # Create new user
            users_collection.insert_one({
                "discord_id": discord_id,
                "username": username,
                "avatar": avatar_url,
                "linked_accounts": {
                    "clash_user_id": None,
                    "csbattle_uuid": None,
                    "skinfans_user_id": None
                },
                "cached_wagers": {
                    "clash": 0,
                    "csbattle": 0,
                    "skinfans": 0
                },
                "total_tickets": 0,
                "ip_addresses": [client_ip],
                "device_fingerprints": [device_fp],
                "user_agent": user_agent,
                "login_history": [{"ip": client_ip, "device": device_fp, "timestamp": now}],
                "login_count": 1,
                "bans": {
                    "all_sites": False,
                    "clash": False,
                    "csbattle": False,
                    "skinfans": False,
                    "login_banned": False
                },
                "created_at": now,
                "last_login": now,
                "updated_at": now
            })
        
        # Create JWT token
        jwt_token = create_jwt_token({"discord_id": discord_id, "username": username})
        
        # Redirect with token in URL (frontend will store it)
        redirect_response = RedirectResponse(url=f"{FRONTEND_URL}/raffle?token={jwt_token}")
        redirect_response.set_cookie(
            key="auth_token",
            value=jwt_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7*24*60*60
        )
        return redirect_response
        
    except Exception as e:
        logger.error(f"Discord callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/raffle?error=auth_failed")

@app.get("/api/auth/me")
async def get_me(request: Request):
    """Get current logged-in user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.post("/api/auth/logout")
async def logout(response: Response):
    """Logout user"""
    response.delete_cookie("auth_token")
    return {"message": "Logged out successfully"}

# User settings endpoints
@app.put("/api/user/settings")
async def update_user_settings(settings: UserSettingsUpdate, request: Request):
    """Update user's linked accounts"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    linked = settings.linked_accounts
    current_linked = user.get("linked_accounts", {})
    validation_errors = []
    wagers = {"clash": 0, "csbattle": 0, "skinfans": 0}
    
    # Check if user is trying to CHANGE an already linked ID (not allowed)
    if current_linked.get("clash_user_id") is not None:
        if linked.clash_user_id is not None and linked.clash_user_id != current_linked["clash_user_id"]:
            validation_errors.append("Clash.gg ID is already linked. You cannot change it to a different ID.")
        # Keep the existing ID
        linked.clash_user_id = current_linked["clash_user_id"]
    
    if current_linked.get("csbattle_uuid") is not None:
        if linked.csbattle_uuid is not None and linked.csbattle_uuid != current_linked["csbattle_uuid"]:
            validation_errors.append("CSBattle UUID is already linked. You cannot change it to a different ID.")
        # Keep the existing ID
        linked.csbattle_uuid = current_linked["csbattle_uuid"]
    
    if current_linked.get("skinfans_user_id") is not None:
        if linked.skinfans_user_id is not None and linked.skinfans_user_id != current_linked["skinfans_user_id"]:
            validation_errors.append("Skin.fans ID is already linked. You cannot change it to a different ID.")
        # Keep the existing ID
        linked.skinfans_user_id = current_linked["skinfans_user_id"]
    
    # Return early if trying to change existing IDs
    if validation_errors:
        raise HTTPException(status_code=400, detail={"errors": validation_errors})
    
    # Check for duplicate IDs (prevent same ID being used by multiple users)
    if linked.clash_user_id is not None and current_linked.get("clash_user_id") is None:
        existing = users_collection.find_one({
            "linked_accounts.clash_user_id": linked.clash_user_id,
            "discord_id": {"$ne": user["discord_id"]}
        })
        if existing:
            validation_errors.append(f"Clash.gg User ID {linked.clash_user_id} is already linked to another account")
    
    if linked.csbattle_uuid is not None and current_linked.get("csbattle_uuid") is None:
        existing = users_collection.find_one({
            "linked_accounts.csbattle_uuid": linked.csbattle_uuid,
            "discord_id": {"$ne": user["discord_id"]}
        })
        if existing:
            validation_errors.append(f"CSBattle UUID is already linked to another account")
    
    if linked.skinfans_user_id is not None and current_linked.get("skinfans_user_id") is None:
        existing = users_collection.find_one({
            "linked_accounts.skinfans_user_id": linked.skinfans_user_id,
            "discord_id": {"$ne": user["discord_id"]}
        })
        if existing:
            validation_errors.append(f"Skin.fans User ID {linked.skinfans_user_id} is already linked to another account")
    
    # Return early if duplicate IDs found
    if validation_errors:
        raise HTTPException(status_code=400, detail={"errors": validation_errors})
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        # Validate Clash.gg ID
        if linked.clash_user_id is not None:
            try:
                config = API_CONFIG["clash"]
                url = f"{config['base_url']}/{config['start_date']}"
                response = await http_client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {config['auth_token']}",
                        "Cookie": config["cookie"],
                        "Content-Type": "application/json"
                    }
                )
                data = response.json()
                found = False
                for u in data:
                    if u.get("userId") == linked.clash_user_id:
                        wagers["clash"] = u.get("wagered", 0)
                        found = True
                        break
                if not found:
                    validation_errors.append(f"Clash.gg User ID {linked.clash_user_id} not found in leaderboard")
            except Exception as e:
                logger.error(f"Clash validation error: {e}")
                validation_errors.append("Could not validate Clash.gg ID")
        
        # Validate CSBattle UUID
        if linked.csbattle_uuid is not None:
            try:
                config = API_CONFIG["csbattle"]
                now = datetime.now(timezone.utc)
                response = await http_client.get(
                    f"{config['url']}/{config['affiliate_id']}",
                    params={"from": config["start_date"], "to": now.strftime("%Y-%m-%d %H:%M:%S")},
                    headers={"Content-Type": "application/json"}
                )
                data = response.json()
                users_data = data.get("users", data) if isinstance(data, dict) else data
                found = False
                for u in users_data:
                    if u.get("uuid") == linked.csbattle_uuid:
                        wagers["csbattle"] = u.get("wager", 0)
                        found = True
                        break
                if not found:
                    validation_errors.append(f"CSBattle UUID {linked.csbattle_uuid} not found in leaderboard")
            except Exception as e:
                logger.error(f"CSBattle validation error: {e}")
                validation_errors.append("Could not validate CSBattle UUID")
        
        # Validate Skin.fans ID
        if linked.skinfans_user_id is not None:
            try:
                config = API_CONFIG["skinfans"]
                response = await http_client.get(
                    config["url"],
                    params={"token": config["token"], "v": "1"}
                )
                data = response.json()
                response_data = data.get("response", {}).get("data", data)
                places = response_data.get("race", {}).get("places", [])
                found = False
                for place in places:
                    user_data = place.get("user", {})
                    if user_data.get("id") == linked.skinfans_user_id:
                        wagers["skinfans"] = float(user_data.get("wagered", 0))
                        found = True
                        break
                if not found:
                    validation_errors.append(f"Skin.fans User ID {linked.skinfans_user_id} not found in leaderboard")
            except Exception as e:
                logger.error(f"Skinfans validation error: {e}")
                validation_errors.append("Could not validate Skin.fans ID")
    
    if validation_errors:
        raise HTTPException(status_code=400, detail={"errors": validation_errors})
    
    # Calculate total tickets (1 ticket per 20 wagered)
    total_wagered = wagers["clash"] + wagers["csbattle"] + wagers["skinfans"]
    total_tickets = math.floor(total_wagered / 20)
    
    # Update user
    users_collection.update_one(
        {"discord_id": user["discord_id"]},
        {"$set": {
            "linked_accounts": {
                "clash_user_id": linked.clash_user_id,
                "csbattle_uuid": linked.csbattle_uuid,
                "skinfans_user_id": linked.skinfans_user_id
            },
            "cached_wagers": wagers,
            "total_tickets": total_tickets,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "message": "Settings updated successfully",
        "wagers": wagers,
        "total_tickets": total_tickets
    }

@app.post("/api/user/refresh-tickets")
async def refresh_tickets(request: Request):
    """Refresh user's ticket count from external APIs"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    linked = user.get("linked_accounts", {})
    wagers = {"clash": 0, "csbattle": 0, "skinfans": 0}
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        # Fetch Clash.gg wager
        if linked.get("clash_user_id"):
            try:
                config = API_CONFIG["clash"]
                url = f"{config['base_url']}/{config['start_date']}"
                response = await http_client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {config['auth_token']}",
                        "Cookie": config["cookie"],
                        "Content-Type": "application/json"
                    }
                )
                data = response.json()
                for u in data:
                    if u.get("userId") == linked["clash_user_id"]:
                        wagers["clash"] = u.get("wagered", 0)
                        break
            except Exception as e:
                logger.error(f"Clash refresh error: {e}")
        
        # Fetch CSBattle wager
        if linked.get("csbattle_uuid"):
            try:
                config = API_CONFIG["csbattle"]
                now = datetime.now(timezone.utc)
                response = await http_client.get(
                    f"{config['url']}/{config['affiliate_id']}",
                    params={"from": config["start_date"], "to": now.strftime("%Y-%m-%d %H:%M:%S")},
                    headers={"Content-Type": "application/json"}
                )
                data = response.json()
                users_data = data.get("users", data) if isinstance(data, dict) else data
                for u in users_data:
                    if u.get("uuid") == linked["csbattle_uuid"]:
                        wagers["csbattle"] = u.get("wager", 0)
                        break
            except Exception as e:
                logger.error(f"CSBattle refresh error: {e}")
        
        # Fetch Skin.fans wager
        if linked.get("skinfans_user_id"):
            try:
                config = API_CONFIG["skinfans"]
                response = await http_client.get(
                    config["url"],
                    params={"token": config["token"], "v": "1"}
                )
                data = response.json()
                response_data = data.get("response", {}).get("data", data)
                places = response_data.get("race", {}).get("places", [])
                for place in places:
                    user_data = place.get("user", {})
                    if user_data.get("id") == linked["skinfans_user_id"]:
                        wagers["skinfans"] = float(user_data.get("wagered", 0))
                        break
            except Exception as e:
                logger.error(f"Skinfans refresh error: {e}")
    
    # Calculate total tickets
    total_wagered = wagers["clash"] + wagers["csbattle"] + wagers["skinfans"]
    total_tickets = math.floor(total_wagered / 20)
    
    # Update user
    users_collection.update_one(
        {"discord_id": user["discord_id"]},
        {"$set": {
            "cached_wagers": wagers,
            "total_tickets": total_tickets,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "wagers": wagers,
        "total_tickets": total_tickets
    }

# Raffle endpoints
@app.get("/api/raffle/info")
async def get_raffle_info():
    """Get current raffle info including timeframe"""
    start_date = datetime.strptime(RAFFLE_CONFIG["start_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(RAFFLE_CONFIG["end_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "countdown_end": end_date.isoformat(),
        "tickets_per_wager": RAFFLE_CONFIG["tickets_per_wager"],
        "prize_pool": RAFFLE_CONFIG["prize_pool"],
        "prizes": RAFFLE_CONFIG["prizes"],
        "status": "active" if start_date <= now <= end_date else ("upcoming" if now < start_date else "ended"),
        "total_participants": users_collection.count_documents({"total_tickets": {"$gt": 0}})
    }

@app.get("/api/raffle/leaderboard")
async def get_raffle_leaderboard(limit: int = 10, offset: int = 0):
    """Get raffle leaderboard (top users by tickets)"""
    users = list(users_collection.find(
        {"total_tickets": {"$gt": 0}},
        {"_id": 0, "discord_id": 1, "username": 1, "avatar": 1, "total_tickets": 1}
    ).sort("total_tickets", -1).skip(offset).limit(limit))
    
    total_count = users_collection.count_documents({"total_tickets": {"$gt": 0}})
    
    # Calculate total tickets for win percentage
    pipeline = [
        {"$match": {"total_tickets": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_tickets"}}}
    ]
    total_result = list(users_collection.aggregate(pipeline))
    total_tickets = total_result[0]["total"] if total_result else 0
    
    # Add rank and win percentage
    for i, user in enumerate(users):
        user["rank"] = offset + i + 1
        user["win_chance"] = round((user["total_tickets"] / total_tickets * 100), 2) if total_tickets > 0 else 0
    
    # Get raffle timeframe info
    start_date = datetime.strptime(RAFFLE_CONFIG["start_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(RAFFLE_CONFIG["end_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    
    return {
        "users": users,
        "total_count": total_count,
        "total_tickets": total_tickets,
        "limit": limit,
        "offset": offset,
        "raffle": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "countdown_end": end_date.isoformat(),
            "prize_pool": RAFFLE_CONFIG["prize_pool"]
        }
    }

@app.get("/api/raffle/my-tickets")
async def get_my_tickets(request: Request):
    """Get current user's ticket count and rank"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Get user's rank
    higher_count = users_collection.count_documents({
        "total_tickets": {"$gt": user.get("total_tickets", 0)}
    })
    rank = higher_count + 1
    
    # Calculate total tickets for win percentage
    pipeline = [
        {"$match": {"total_tickets": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_tickets"}}}
    ]
    total_result = list(users_collection.aggregate(pipeline))
    total_tickets = total_result[0]["total"] if total_result else 0
    
    user_tickets = user.get("total_tickets", 0)
    win_chance = round((user_tickets / total_tickets * 100), 2) if total_tickets > 0 else 0
    
    return {
        "tickets": user_tickets,
        "rank": rank,
        "win_chance": win_chance,
        "total_tickets_pool": total_tickets,
        "wagers": user.get("cached_wagers", {}),
        "linked_accounts": user.get("linked_accounts", {})
    }

# Leaderboard endpoints (existing)
async def fetch_clash_data() -> Dict[str, Any]:
    config = API_CONFIG["clash"]
    try:
        now = datetime.now(timezone.utc)
        start_date = config.get("start_date", "2026-02-02")
        url = f"{config['base_url']}/{start_date}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {config['auth_token']}",
                    "Cookie": config["cookie"],
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            sorted_users = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
            
            users = []
            for i, user in enumerate(sorted_users[:10]):
                prize = 0
                for p in config["prizes"]:
                    if p["place"] == i + 1:
                        prize = p["amount"]
                        break
                
                users.append({
                    "rank": i + 1,
                    "username": mask_username(user.get("name", "Unknown")),
                    "avatar": user.get("avatar", ""),
                    "wagered": round(user.get("wagered", 0), 2),
                    "prize": prize
                })
            
            countdown_end = None
            try:
                end_date_str = config.get("end_date", "2026-02-16 19:00:00")
                countdown_end = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
            except:
                pass
            
            return {
                "site_id": "clash",
                "site_name": "Clash.gg",
                "users": users,
                "prize_pool": config["prize_pool"],
                "currency": config["currency"],
                "prizes": config["prizes"],
                "countdown_end": countdown_end,
                "status": "active",
                "last_updated": now.isoformat()
            }
    except Exception as e:
        logger.error(f"Error fetching Clash.gg data: {e}")
        return {
            "site_id": "clash",
            "site_name": "Clash.gg",
            "users": [],
            "prize_pool": config["prize_pool"],
            "currency": config["currency"],
            "prizes": config["prizes"],
            "countdown_end": None,
            "status": "error",
            "message": str(e),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

async def fetch_bsite_data() -> Dict[str, Any]:
    config = API_CONFIG["bsite"]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                config["url"],
                headers={
                    "Content-Type": "application/json",
                    "Referer": "b.site"
                },
                json={"apiKey": config["api_key"]}
            )
            
            data = response.json()
            
            if data.get("maintenance"):
                return {
                    "site_id": "bsite",
                    "site_name": "B.site",
                    "users": [],
                    "prize_pool": config["prize_pool"],
                    "currency": config["currency"],
                    "prizes": config["prizes"],
                    "countdown_end": None,
                    "status": "maintenance",
                    "message": data.get("msg", "B.site is currently under maintenance."),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            
            wagers = data.get("wagers", [])
            leaderboard_rewards = data.get("leaderboard", {}).get("leaderboardRewards", [])
            current_entry = data.get("currentEntry", {})
            
            prize_lookup = {r["place"]: r["winnings"] for r in leaderboard_rewards}
            
            users = []
            for user in wagers[:10]:
                rank = user.get("rank", 0)
                users.append({
                    "rank": rank,
                    "username": user.get("username", "Unknown"),
                    "avatar": user.get("avatar", ""),
                    "wagered": round(user.get("wager", 0), 2),
                    "prize": prize_lookup.get(rank, 0)
                })
            
            countdown_end = None
            if current_entry.get("end"):
                try:
                    end_timestamp = int(current_entry["end"]) / 1000
                    countdown_end = datetime.fromtimestamp(end_timestamp, tz=timezone.utc).isoformat()
                except:
                    pass
            
            return {
                "site_id": "bsite",
                "site_name": "B.site",
                "users": users,
                "prize_pool": data.get("leaderboard", {}).get("config", {}).get("value", config["prize_pool"]),
                "currency": config["currency"],
                "prizes": config["prizes"],
                "countdown_end": countdown_end,
                "status": current_entry.get("status", "active"),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error fetching B.site data: {e}")
        return {
            "site_id": "bsite",
            "site_name": "B.site",
            "users": [],
            "prize_pool": config["prize_pool"],
            "currency": config["currency"],
            "prizes": config["prizes"],
            "countdown_end": None,
            "status": "error",
            "message": "B.site is temporarily unavailable.",
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


# ==================== ADMIN ENDPOINTS ====================

@app.get("/api/admin/check")
async def check_admin(request: Request):
    """Check if current user is admin"""
    user = await get_current_user(request)
    if not user:
        return {"is_admin": False}
    return {"is_admin": user["discord_id"] in ADMIN_DISCORD_IDS}

@app.get("/api/admin/users")
async def admin_get_users(
    request: Request,
    search: str = "",
    page: int = 1,
    limit: int = 20,
    filter_type: str = "all"  # all, banned, with_ids, no_ids
):
    """Get all users (admin only)"""
    await require_admin(request)
    
    # Build query
    query = {}
    if search:
        query["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"discord_id": {"$regex": search, "$options": "i"}}
        ]
    
    if filter_type == "banned":
        query["$or"] = [
            {"bans.all_sites": True},
            {"bans.login_banned": True}
        ]
    elif filter_type == "with_ids":
        query["$or"] = [
            {"linked_accounts.clash_user_id": {"$ne": None}},
            {"linked_accounts.csbattle_uuid": {"$ne": None}},
            {"linked_accounts.skinfans_user_id": {"$ne": None}}
        ]
    elif filter_type == "no_ids":
        query["linked_accounts.clash_user_id"] = None
        query["linked_accounts.csbattle_uuid"] = None
        query["linked_accounts.skinfans_user_id"] = None
    
    skip = (page - 1) * limit
    total = users_collection.count_documents(query)
    
    users = list(users_collection.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit))
    
    # Add linked count
    for user in users:
        linked = user.get("linked_accounts", {})
        user["linked_count"] = sum([
            1 if linked.get("clash_user_id") else 0,
            1 if linked.get("csbattle_uuid") else 0,
            1 if linked.get("skinfans_user_id") else 0
        ])
        user["is_banned"] = (
            user.get("bans", {}).get("all_sites", False) or
            user.get("bans", {}).get("login_banned", False)
        )
    
    return {
        "users": users,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1
    }

@app.get("/api/admin/users/{discord_id}")
async def admin_get_user(discord_id: str, request: Request):
    """Get single user details (admin only)"""
    await require_admin(request)
    
    user = users_collection.find_one({"discord_id": discord_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@app.put("/api/admin/users/{discord_id}")
async def admin_update_user(discord_id: str, update: AdminUserUpdate, request: Request):
    """Update user (admin only)"""
    admin = await require_admin(request)
    
    user = users_collection.find_one({"discord_id": discord_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = {"updated_at": datetime.now(timezone.utc)}
    
    if update.linked_accounts:
        update_data["linked_accounts"] = {
            "clash_user_id": update.linked_accounts.clash_user_id,
            "csbattle_uuid": update.linked_accounts.csbattle_uuid,
            "skinfans_user_id": update.linked_accounts.skinfans_user_id
        }
    
    if update.bans:
        update_data["bans"] = update.bans
    
    users_collection.update_one(
        {"discord_id": discord_id},
        {"$set": update_data}
    )
    
    log_admin_action(admin["discord_id"], "update_user", discord_id, update_data)
    
    return {"message": "User updated successfully"}

@app.post("/api/admin/users/{discord_id}/ban")
async def admin_ban_user(discord_id: str, ban_request: AdminBanRequest, request: Request):
    """Ban user (admin only)"""
    admin = await require_admin(request)
    
    if discord_id == admin["discord_id"]:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")
    
    user = users_collection.find_one({"discord_id": discord_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    bans = user.get("bans", {})
    
    if ban_request.ban_type == "all_sites":
        bans["all_sites"] = True
        bans["clash"] = True
        bans["csbattle"] = True
        bans["skinfans"] = True
    elif ban_request.ban_type == "login":
        bans["login_banned"] = True
    elif ban_request.ban_type in ["clash", "csbattle", "skinfans"]:
        bans[ban_request.ban_type] = True
    else:
        raise HTTPException(status_code=400, detail="Invalid ban type")
    
    bans["banned_by"] = admin["discord_id"]
    bans["banned_at"] = datetime.now(timezone.utc).isoformat()
    bans["ban_reason"] = ban_request.reason or "No reason provided"
    
    users_collection.update_one(
        {"discord_id": discord_id},
        {"$set": {"bans": bans, "updated_at": datetime.now(timezone.utc)}}
    )
    
    log_admin_action(admin["discord_id"], f"ban_{ban_request.ban_type}", discord_id, {"reason": ban_request.reason})
    
    return {"message": f"User banned from {ban_request.ban_type}"}

@app.post("/api/admin/users/{discord_id}/unban")
async def admin_unban_user(discord_id: str, ban_request: AdminBanRequest, request: Request):
    """Unban user (admin only)"""
    admin = await require_admin(request)
    
    user = users_collection.find_one({"discord_id": discord_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    bans = user.get("bans", {})
    
    if ban_request.ban_type == "all_sites":
        bans["all_sites"] = False
        bans["clash"] = False
        bans["csbattle"] = False
        bans["skinfans"] = False
    elif ban_request.ban_type == "login":
        bans["login_banned"] = False
    elif ban_request.ban_type in ["clash", "csbattle", "skinfans"]:
        bans[ban_request.ban_type] = False
    
    users_collection.update_one(
        {"discord_id": discord_id},
        {"$set": {"bans": bans, "updated_at": datetime.now(timezone.utc)}}
    )
    
    log_admin_action(admin["discord_id"], f"unban_{ban_request.ban_type}", discord_id)
    
    return {"message": f"User unbanned from {ban_request.ban_type}"}

@app.delete("/api/admin/users/{discord_id}")
async def admin_delete_user(discord_id: str, request: Request):
    """Delete user (admin only)"""
    admin = await require_admin(request)
    
    if discord_id == admin["discord_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    result = users_collection.delete_one({"discord_id": discord_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    log_admin_action(admin["discord_id"], "delete_user", discord_id)
    
    return {"message": "User deleted successfully"}

@app.post("/api/admin/users/{discord_id}/remove-id/{site}")
async def admin_remove_user_id(discord_id: str, site: str, request: Request):
    """Remove linked ID from user (admin only)"""
    admin = await require_admin(request)
    
    if site not in ["clash", "csbattle", "skinfans"]:
        raise HTTPException(status_code=400, detail="Invalid site")
    
    field_map = {
        "clash": "linked_accounts.clash_user_id",
        "csbattle": "linked_accounts.csbattle_uuid",
        "skinfans": "linked_accounts.skinfans_user_id"
    }
    
    result = users_collection.update_one(
        {"discord_id": discord_id},
        {"$set": {field_map[site]: None, "updated_at": datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    log_admin_action(admin["discord_id"], f"remove_id_{site}", discord_id)
    
    return {"message": f"{site} ID removed successfully"}

# Suspicious (Alt Detection) endpoints
@app.get("/api/admin/suspicious")
async def admin_get_suspicious(request: Request):
    """Get suspicious account groups (same IP or device)"""
    await require_admin(request)
    
    suspicious_groups = []
    
    # Find users sharing IPs
    ip_pipeline = [
        {"$unwind": "$ip_addresses"},
        {"$group": {
            "_id": "$ip_addresses",
            "users": {"$push": {
                "discord_id": "$discord_id",
                "username": "$username",
                "avatar": "$avatar",
                "total_tickets": "$total_tickets"
            }},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    ip_groups = list(users_collection.aggregate(ip_pipeline))
    
    # Find users sharing device fingerprints
    device_pipeline = [
        {"$unwind": "$device_fingerprints"},
        {"$group": {
            "_id": "$device_fingerprints",
            "users": {"$push": {
                "discord_id": "$discord_id",
                "username": "$username",
                "avatar": "$avatar",
                "total_tickets": "$total_tickets"
            }},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    device_groups = list(users_collection.aggregate(device_pipeline))
    
    # Combine and categorize
    seen_pairs = set()
    
    for group in ip_groups:
        user_ids = tuple(sorted([u["discord_id"] for u in group["users"]]))
        if user_ids not in seen_pairs:
            seen_pairs.add(user_ids)
            
            # Check if also same device
            device_match = any(
                set([u["discord_id"] for u in dg["users"]]) == set([u["discord_id"] for u in group["users"]])
                for dg in device_groups
            )
            
            suspicious_groups.append({
                "id": hashlib.md5(str(user_ids).encode()).hexdigest()[:12],
                "type": "ip",
                "risk_level": "high" if device_match else "medium",
                "shared_ip": group["_id"],
                "shared_device": None,
                "users": group["users"],
                "account_count": group["count"]
            })
    
    for group in device_groups:
        user_ids = tuple(sorted([u["discord_id"] for u in group["users"]]))
        # Only add if not already covered by IP groups
        if user_ids not in seen_pairs:
            seen_pairs.add(user_ids)
            suspicious_groups.append({
                "id": hashlib.md5(str(user_ids).encode()).hexdigest()[:12],
                "type": "device",
                "risk_level": "medium",
                "shared_ip": None,
                "shared_device": group["_id"],
                "users": group["users"],
                "account_count": group["count"]
            })
    
    # Sort by risk level (high first) then by account count
    suspicious_groups.sort(key=lambda x: (0 if x["risk_level"] == "high" else 1, -x["account_count"]))
    
    return {
        "groups": suspicious_groups,
        "total_groups": len(suspicious_groups)
    }

@app.post("/api/admin/suspicious/{group_id}/ban-all")
async def admin_ban_suspicious_group(group_id: str, request: Request):
    """Ban all accounts in a suspicious group"""
    admin = await require_admin(request)
    
    # Re-fetch the group to get current user IDs
    suspicious = await admin_get_suspicious(request)
    group = next((g for g in suspicious["groups"] if g["id"] == group_id), None)
    
    if not group:
        raise HTTPException(status_code=404, detail="Suspicious group not found")
    
    banned_count = 0
    for user in group["users"]:
        if user["discord_id"] != admin["discord_id"]:
            users_collection.update_one(
                {"discord_id": user["discord_id"]},
                {"$set": {
                    "bans.all_sites": True,
                    "bans.clash": True,
                    "bans.csbattle": True,
                    "bans.skinfans": True,
                    "bans.banned_by": admin["discord_id"],
                    "bans.banned_at": datetime.now(timezone.utc).isoformat(),
                    "bans.ban_reason": "Alt account detection"
                }}
            )
            banned_count += 1
    
    log_admin_action(admin["discord_id"], "ban_suspicious_group", group_id, {"banned_count": banned_count})
    
    return {"message": f"Banned {banned_count} accounts"}

# Settings endpoints
@app.get("/api/admin/settings")
async def admin_get_settings(request: Request):
    """Get current settings (admin only)"""
    await require_admin(request)
    
    settings = settings_collection.find_one({"_id": "main"})
    
    if not settings:
        # Return defaults
        return {
            "raffle": RAFFLE_CONFIG,
            "leaderboards": {
                "clash": {
                    "start_date": API_CONFIG["clash"]["start_date"],
                    "end_date": API_CONFIG["clash"]["end_date"]
                },
                "csbattle": {
                    "start_date": API_CONFIG["csbattle"]["start_date"],
                    "end_date": API_CONFIG["csbattle"]["end_date"]
                }
            }
        }
    
    return {
        "raffle": settings.get("raffle", RAFFLE_CONFIG),
        "leaderboards": settings.get("leaderboards", {})
    }

@app.put("/api/admin/settings")
async def admin_update_settings(update: AdminSettingsUpdate, request: Request):
    """Update settings (admin only)"""
    admin = await require_admin(request)
    
    settings = settings_collection.find_one({"_id": "main"}) or {"_id": "main"}
    
    if "raffle" not in settings:
        settings["raffle"] = dict(RAFFLE_CONFIG)
    if "leaderboards" not in settings:
        settings["leaderboards"] = {}
    
    # Update raffle settings
    if update.raffle_start_date:
        settings["raffle"]["start_date"] = update.raffle_start_date
    if update.raffle_end_date:
        settings["raffle"]["end_date"] = update.raffle_end_date
    if update.raffle_prize_pool is not None:
        settings["raffle"]["prize_pool"] = update.raffle_prize_pool
    
    # Update leaderboard settings
    if update.clash_start_date or update.clash_end_date:
        if "clash" not in settings["leaderboards"]:
            settings["leaderboards"]["clash"] = {}
        if update.clash_start_date:
            settings["leaderboards"]["clash"]["start_date"] = update.clash_start_date
        if update.clash_end_date:
            settings["leaderboards"]["clash"]["end_date"] = update.clash_end_date
    
    if update.csbattle_start_date or update.csbattle_end_date:
        if "csbattle" not in settings["leaderboards"]:
            settings["leaderboards"]["csbattle"] = {}
        if update.csbattle_start_date:
            settings["leaderboards"]["csbattle"]["start_date"] = update.csbattle_start_date
        if update.csbattle_end_date:
            settings["leaderboards"]["csbattle"]["end_date"] = update.csbattle_end_date
    
    settings["updated_at"] = datetime.now(timezone.utc)
    settings["updated_by"] = admin["discord_id"]
    
    settings_collection.replace_one({"_id": "main"}, settings, upsert=True)
    
    log_admin_action(admin["discord_id"], "update_settings", "main", settings)
    
    return {"message": "Settings updated successfully"}

@app.get("/api/admin/logs")
async def admin_get_logs(request: Request, page: int = 1, limit: int = 50):
    """Get admin action logs"""
    await require_admin(request)
    
    skip = (page - 1) * limit
    total = admin_logs_collection.count_documents({})
    
    logs = list(admin_logs_collection.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit))
    
    # Convert datetime to string
    for log in logs:
        if isinstance(log.get("timestamp"), datetime):
            log["timestamp"] = log["timestamp"].isoformat()
    
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit
    }

async def fetch_csbattle_data() -> Dict[str, Any]:
    config = API_CONFIG["csbattle"]
    
    try:
        start_date = config.get("start_date", "2026-02-02 18:30:00")
        end_date = config.get("end_date", "2026-02-18 19:30:00")
        
        now = datetime.now(timezone.utc)
        fetch_end_date = now.strftime("%Y-%m-%d %H:%M:%S")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config['url']}/{config['affiliate_id']}",
                params={"from": start_date, "to": fetch_end_date},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            
            users_data = data.get("users", data) if isinstance(data, dict) else data
            
            users = []
            sorted_users = sorted(users_data, key=lambda x: x.get("wager", 0), reverse=True)
            
            for i, user in enumerate(sorted_users[:10]):
                prize = 0
                for p in config["prizes"]:
                    if p["place"] == i + 1:
                        prize = p["amount"]
                        break
                
                username = sanitize_username(user.get("username", "Unknown"))
                users.append({
                    "rank": i + 1,
                    "username": username,
                    "avatar": user.get("avatar", ""),
                    "wagered": round(user.get("wager", 0), 2),
                    "prize": prize
                })
            
            countdown_end = None
            try:
                countdown_end = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
            except:
                pass
            
            return {
                "site_id": "csbattle",
                "site_name": "CSBattle",
                "users": users,
                "prize_pool": config["prize_pool"],
                "currency": config["currency"],
                "prizes": config["prizes"],
                "countdown_end": countdown_end,
                "status": "active",
                "last_updated": now.isoformat()
            }
    except Exception as e:
        logger.error(f"Error fetching CSBattle data: {e}")
        return {
            "site_id": "csbattle",
            "site_name": "CSBattle",
            "users": [],
            "prize_pool": config["prize_pool"],
            "currency": config["currency"],
            "prizes": config["prizes"],
            "countdown_end": None,
            "status": "error",
            "message": str(e),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

async def fetch_skinfans_data() -> Dict[str, Any]:
    config = API_CONFIG["skinfans"]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                config["url"],
                params={"token": config["token"], "v": "1"}
            )
            response.raise_for_status()
            data = response.json()
            
            response_data = data.get("response", {}).get("data", data)
            race = response_data.get("race", {})
            places = race.get("places", [])
            
            users = []
            for i, place in enumerate(places[:10]):
                prize = float(place.get("payout", 0))
                user_data = place.get("user", {})
                
                if user_data:
                    users.append({
                        "rank": i + 1,
                        "username": mask_username(user_data.get("name", "Unknown")),
                        "avatar": user_data.get("avatar", ""),
                        "wagered": round(float(user_data.get("wagered", 0)), 2),
                        "prize": prize
                    })
            
            countdown_end = None
            ends_at = race.get("ends_at")
            if ends_at:
                try:
                    countdown_end = datetime.fromtimestamp(ends_at, tz=timezone.utc).isoformat()
                except:
                    pass
            
            return {
                "site_id": "skinfans",
                "site_name": "Skin.fans",
                "users": users,
                "prize_pool": float(race.get("payout", config["prize_pool"])),
                "currency": config["currency"],
                "prizes": config["prizes"],
                "countdown_end": countdown_end,
                "status": "active" if race.get("active") else "ended",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error fetching Skin.fans data: {e}")
        return {
            "site_id": "skinfans",
            "site_name": "Skin.fans",
            "users": [],
            "prize_pool": config["prize_pool"],
            "currency": config["currency"],
            "prizes": config["prizes"],
            "countdown_end": None,
            "status": "error",
            "message": str(e),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

@app.get("/")
async def root():
    return {"message": "ObeyTriceWithRice API", "status": "online"}

@app.get("/api")
async def api_root():
    return {"message": "ObeyTriceWithRice API", "status": "online"}

@app.get("/api/leaderboard/{site_id}")
async def get_leaderboard(site_id: str):
    valid_sites = ["clash", "bsite", "csbattle", "skinfans"]
    if site_id not in valid_sites:
        raise HTTPException(status_code=404, detail=f"Invalid site. Valid sites: {', '.join(valid_sites)}")
    
    fetch_functions = {
        "clash": fetch_clash_data,
        "bsite": fetch_bsite_data,
        "csbattle": fetch_csbattle_data,
        "skinfans": fetch_skinfans_data
    }
    
    data = await fetch_functions[site_id]()
    return data

@app.get("/api/leaderboards")
async def get_all_leaderboards():
    results = {}
    for site_id, fetch_func in [
        ("clash", fetch_clash_data),
        ("bsite", fetch_bsite_data),
        ("csbattle", fetch_csbattle_data),
        ("skinfans", fetch_skinfans_data)
    ]:
        try:
            results[site_id] = await fetch_func()
        except Exception as e:
            results[site_id] = {"site_id": site_id, "error": str(e), "status": "error"}
    
    return results
