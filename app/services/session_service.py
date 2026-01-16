import redis
import json
import uuid
from app.config import REDIS_CONFIG

# Initialize Redis connection
# In production, you might want to handle connection errors gracefully
try:
    redis_client = redis.Redis(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=REDIS_CONFIG["db"],
        decode_responses=True # Automatically decode bytes to strings
    )
except Exception as e:
    print(f"Warning: Could not connect to Redis: {e}")
    redis_client = None

SESSION_TTL = 300  # 5 minutes in seconds

def create_session(data: dict) -> str:
    """
    Creates a new session in Redis with the given data.
    Returns the generated session_id.
    """
    if not redis_client:
        return None
        
    session_id = str(uuid.uuid4())
    key = f"session:{session_id}"
    
    # Store as JSON string
    redis_client.setex(key, SESSION_TTL, json.dumps(data))
    
    return session_id

def get_session(session_id: str) -> dict:
    """
    Retrieves session data from Redis.
    Returns None if not found or expired.
    """
    if not redis_client or not session_id:
        return None
        
    key = f"session:{session_id}"
    data_str = redis_client.get(key)
    
    if data_str:
        # Extend TTL on access (sliding expiration) - optional but recommended
        redis_client.expire(key, SESSION_TTL) 
        try:
            return json.loads(data_str)
        except json.JSONDecodeError:
            return None
    return None

def update_session(session_id: str, data: dict):
    """
    Updates existing session data.
    """
    if not redis_client or not session_id:
        return
        
    key = f"session:{session_id}"
    if redis_client.exists(key):
        redis_client.setex(key, SESSION_TTL, json.dumps(data))

def delete_session(session_id: str):
    """
    Deletes a session from Redis.
    """
    if not redis_client or not session_id:
        return
        
    key = f"session:{session_id}"
    redis_client.delete(key)
