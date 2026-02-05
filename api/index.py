from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
import httpx

# Create the main app
app = FastAPI(title="ObeyTriceWithRice API")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Configuration
API_CONFIG = {
    "clash": {
        "base_url": "https://api.clash.gg/affiliates/detailed-summary/v2",
        "auth_token": os.environ.get("CLASH_API_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoicGFzcyIsInNjb3BlIjoiYWZmaWxpYXRlcyIsInVzZXJJZCI6MzYxNTM5MSwiaWF0IjoxNzYyMDgzNjU2LCJleHAiOjE5MTk4NzE2NTZ9.f5xbD1m3bgMlgAsjzh2-IcdMOFpNvumTGbCYHxSSS14"),
        "cookie": "let-me-in=top-secret-cookie-do-not-share",
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
        "start_date": os.environ.get("CSBATTLE_START_DATE", "2026-02-01 00:00:00"),
        "end_date": os.environ.get("CSBATTLE_END_DATE", "2026-02-18 20:30:00"),
        "fetch_end_date": "2026-02-05 23:59:59",
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

async def fetch_clash_data() -> Dict[str, Any]:
    config = API_CONFIG["clash"]
    try:
        now = datetime.now(timezone.utc)
        start_date = now.replace(day=1).strftime("%Y-%m-%d")
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
            
            if now.month == 12:
                end_of_month = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
            else:
                end_of_month = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
            
            return {
                "site_id": "clash",
                "site_name": "Clash.gg",
                "users": users,
                "prize_pool": config["prize_pool"],
                "currency": config["currency"],
                "prizes": config["prizes"],
                "countdown_end": end_of_month.isoformat(),
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

async def fetch_csbattle_data() -> Dict[str, Any]:
    config = API_CONFIG["csbattle"]
    
    try:
        start_date = config.get("start_date", "2026-02-01 00:00:00")
        fetch_end_date = config.get("fetch_end_date", "2026-02-05 23:59:59")
        countdown_end_date = config.get("end_date", "2026-02-18 20:30:00")
        
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
                countdown_end = datetime.strptime(countdown_end_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
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
                "last_updated": datetime.now(timezone.utc).isoformat()
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
