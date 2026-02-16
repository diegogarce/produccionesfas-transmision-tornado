import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import pymysql
import traceback

from app.db import create_db_connection
from app.services.redis_cache import get_redis_cache


def start_poll(
    event_id: int,
    question: str,
    options: List[str],
    duration_minutes: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Start a new poll: MySQL insert, Redis live state and init counts."""
    try:
        r = get_redis_cache()
        if not r:
            return None

        db = create_db_connection()
        cursor = db.cursor()

        close_at = None
        if duration_minutes:
            close_at_utc = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            close_at = close_at_utc.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            "INSERT INTO polls (event_id, question, options, close_at) VALUES (%s, %s, %s, %s)",
            (event_id, question, json.dumps(options), close_at)
        )
        poll_id = cursor.lastrowid

        # Initialize counts hash to 0
        pipe = r.pipeline()
        for i in range(len(options)):
            pipe.hset(f"poll:votes:{poll_id}:counts", str(i), "0")
        pipe.execute()

        # Set live poll data
        live_data = {
            "poll_id": poll_id,
            "question": question,
            "options": options,
            "close_at": close_at,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        r.set(f"poll:live:{event_id}", json.dumps(live_data))

        return live_data
    except Exception as e:
        print(f"[PollService] Error starting poll: {e}")
        traceback.print_exc()
        return None
    finally:
        if 'db' in locals() and db:
            db.close()


def vote(
    event_id: int,
    option_index: int,
    user_id: int
) -> Optional[Dict[str, Any]]:
    """Process vote atomically, return update or None if invalid/expired/dupe."""

    try:
        r = get_redis_cache()
        if not r:
            return None

        live_key = f"poll:live:{event_id}"
        live_json = r.get(live_key)
        if not live_json:
            return None

        poll_data: Dict[str, Any] = json.loads(live_json)
        poll_id = poll_data["poll_id"]
        options = poll_data.get("options") or []

        # Validate option index against current options
        try:
            option_index = int(option_index)
        except (TypeError, ValueError):
            return None
        if option_index < 0 or option_index >= len(options):
            return None

        # Check close time
        close_at_str = poll_data.get("close_at")
        if close_at_str:
            close_at = datetime.strptime(close_at_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > close_at:
                return None

        voted_key = f"poll:voted:{poll_id}"
        counts_key = f"poll:votes:{poll_id}:counts"

        # Atomic vote in Redis: only increment counts if this user hasn't voted.
        lua = """
        if redis.call('SADD', KEYS[1], ARGV[1]) == 1 then
            redis.call('HINCRBY', KEYS[2], ARGV[2], 1)
            return 1
        end
        return 0
        """
        try:
            added = r.eval(lua, 2, voted_key, counts_key, str(user_id), str(option_index))
        except Exception:
            # Fallback (non-atomic) if eval is blocked
            if r.sismember(voted_key, str(user_id)):
                return None
            pipe = r.pipeline()
            pipe.sadd(voted_key, str(user_id))
            pipe.hincrby(counts_key, str(option_index), 1)
            pipe.execute()
            added = 1

        if int(added or 0) != 1:
            return None

        # Persist individual vote history in MySQL (best-effort; Redis remains source for live counts).
        try:
            db2 = create_db_connection()
            cur2 = db2.cursor()
            cur2.execute(
                "INSERT IGNORE INTO poll_votes (poll_id, event_id, user_id, option_index) VALUES (%s, %s, %s, %s)",
                (poll_id, event_id, user_id, option_index),
            )
        except Exception:
            pass
        finally:
            try:
                if 'db2' in locals() and db2:
                    db2.close()
            except Exception:
                pass

        # Fetch updated results
        counts = r.hgetall(counts_key)
        total_votes = sum(int(v) for v in counts.values())
        results = {int(k): int(v) for k, v in counts.items()}

        return {
            "poll_id": poll_id,
            "results": results,
            "total_votes": total_votes
        }
    except Exception as e:
        print(f"[PollService] Error processing vote: {e}")
        traceback.print_exc()
        return None


def get_live_poll(event_id: int) -> Optional[Dict[str, Any]]:
    """Get current live poll with results, check expiry."""

    try:
        r = get_redis_cache()
        if not r:
            return None

        live_key = f"poll:live:{event_id}"
        live_json = r.get(live_key)
        if not live_json:
            return None

        poll_data: Dict[str, Any] = json.loads(live_json)
        poll_id = poll_data["poll_id"]

        # Check expiry
        close_at_str = poll_data.get("close_at")
        if close_at_str:
            close_at = datetime.strptime(close_at_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > close_at:
                return None

        counts_key = f"poll:votes:{poll_id}:counts"
        counts = r.hgetall(counts_key)
        total_votes = sum(int(v or 0) for v in counts.values())
        results = {int(k): int(v or 0) for k, v in counts.items()}

        poll_data["results"] = results
        poll_data["total_votes"] = total_votes

        return poll_data
    except Exception as e:
        print(f"[PollService] Error getting live poll: {e}")
        return None


def close_poll(event_id: int) -> Optional[Dict[str, Any]]:
    """Flush results to MySQL, cleanup Redis, return final data."""

    try:
        r = get_redis_cache()
        if not r:
            return None

        live_key = f"poll:live:{event_id}"
        live_json = r.get(live_key)
        if not live_json:
            return None

        poll_data: Dict[str, Any] = json.loads(live_json)
        poll_id = poll_data["poll_id"]
        options = poll_data["options"]
        question = poll_data["question"]

        counts_key = f"poll:votes:{poll_id}:counts"
        counts = r.hgetall(counts_key)
        results = {int(k): int(v or 0) for k, v in counts.items()}
        total_votes = sum(results.values())

        # Flush to MySQL
        db = create_db_connection()
        cursor = db.cursor()

        for opt_idx, vote_count in results.items():
            cursor.execute(
                "INSERT INTO poll_results (poll_id, option_index, votes) VALUES (%s, %s, %s)",
                (poll_id, opt_idx, vote_count)
            )

        # Best-effort: mark as closed (only if schema has status)
        try:
            cursor.execute("UPDATE polls SET status = 'closed' WHERE id = %s", (poll_id,))
        except Exception:
            pass

        # Cleanup Redis
        r.delete(live_key)
        r.delete(counts_key)
        r.delete(f"poll:voted:{poll_id}")

        return {
            "poll_id": poll_id,
            "question": question,
            "options": options,
            "results": results,
            "total_votes": total_votes
        }
    except Exception as e:
        print(f"[PollService] Error closing poll: {e}")
        traceback.print_exc()
        return None
    finally:
        if 'db' in locals() and db:
            db.close()


def list_polls(event_id: int) -> List[Dict[str, Any]]:
    """List pre-created polls for event."""

    try:
        db = create_db_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, question, options, created_at, close_at, status FROM polls WHERE event_id = %s ORDER BY created_at DESC", (event_id,))
        polls = cursor.fetchall()
        for p in polls:
            p['options'] = json.loads(p['options'])
        return polls
    except Exception as e:
        print(f"[PollService] Error listing polls: {e}")
        return []
    finally:
        if 'db' in locals() and db:
            db.close()


def get_poll_by_id(poll_id: int) -> Optional[Dict[str, Any]]:
    try:
        db = create_db_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, event_id, question, options, status FROM polls WHERE id = %s", (poll_id,))
        poll = cursor.fetchone()
        if poll and poll.get("options"):
            poll["options"] = json.loads(poll["options"])
        return poll
    except Exception as e:
        print(f"[PollService] Error getting poll by id: {e}")
        return None
    finally:
        if 'db' in locals() and db:
            db.close()


def create_poll(event_id: int, question: str, options: List[str], status: str = 'draft') -> Optional[int]:
    """Create pre-poll in MySQL (no live)."""

    try:
        db = create_db_connection()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO polls (event_id, question, options, status) VALUES (%s, %s, %s, %s)",
            (event_id, question, json.dumps(options), status)
        )
        return cursor.lastrowid
    except Exception as e:
        print(f"[PollService] Error creating poll: {e}")
        return None
    finally:
        if 'db' in locals() and db:
            db.close()


def update_poll_status(poll_id: int, status: str) -> bool:
    """Update poll status (draft, published, closed)."""
    try:
        db = create_db_connection()
        cursor = db.cursor()
        cursor.execute("UPDATE polls SET status = %s WHERE id = %s", (status, poll_id))
        return True
    except Exception as e:
        print(f"[PollService] Error updating poll status: {e}")
        return False
    finally:
        if 'db' in locals() and db:
            db.close()


def update_poll_content(poll_id: int, question: str, options: List[str]) -> bool:
    try:
        db = create_db_connection()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE polls SET question = %s, options = %s WHERE id = %s",
            (question, json.dumps(options), poll_id)
        )
        return True
    except Exception as e:
        print(f"[PollService] Error updating poll content: {e}")
        return False
    finally:
        if 'db' in locals() and db:
            db.close()


def get_poll_results(poll_id: int) -> Optional[Dict[str, Any]]:
    try:
        db = create_db_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT question, options FROM polls WHERE id = %s", (poll_id,))
        poll = cursor.fetchone()
        if not poll:
            return None
        options = json.loads(poll["options"]) if poll.get("options") else []

        cursor.execute(
            "SELECT option_index, votes FROM poll_results WHERE poll_id = %s ORDER BY option_index ASC",
            (poll_id,)
        )
        rows = cursor.fetchall()
        total_votes = sum(int(r.get("votes") or 0) for r in rows)
        results = []
        for row in rows:
            idx = int(row.get("option_index") or 0)
            option_label = options[idx] if idx < len(options) else f"Opción {idx + 1}"
            results.append({
                "option": option_label,
                "votes": int(row.get("votes") or 0),
                "option_index": idx
            })
        return {
            "poll_id": poll_id,
            "question": poll.get("question"),
            "results": results,
            "total_votes": total_votes
        }
    except Exception as e:
        print(f"[PollService] Error getting poll results: {e}")
        return None
    finally:
        if 'db' in locals() and db:
            db.close()


def launch_poll(event_id: int, poll_id: int, duration_minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Launch pre-created poll: set close_at, Redis live, init counts."""

    try:
        r = get_redis_cache()
        if not r:
            return None

        db = create_db_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        poll_row = None
        try:
            cursor.execute(
                "SELECT question, options, status FROM polls WHERE id = %s AND event_id = %s",
                (poll_id, event_id)
            )
            poll_row = cursor.fetchone()
        except Exception:
            # Backward compatibility if DB wasn't migrated (no status column)
            cursor.execute(
                "SELECT question, options FROM polls WHERE id = %s AND event_id = %s",
                (poll_id, event_id)
            )
            poll_row = cursor.fetchone()

        if not poll_row:
            return None

        if poll_row.get("status") and poll_row.get("status") != "published":
            return None

        question = poll_row['question']
        options = json.loads(poll_row['options'])

        close_at = None
        if duration_minutes:
            close_at_utc = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            close_at = close_at_utc.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("UPDATE polls SET close_at = %s WHERE id = %s", (close_at, poll_id))

        # Init counts
        pipe = r.pipeline()
        for i in range(len(options)):
            pipe.hset(f"poll:votes:{poll_id}:counts", str(i), "0")
        pipe.execute()

        live_data = {
            "poll_id": poll_id,
            "question": question,
            "options": options,
            "close_at": close_at,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        r.set(f"poll:live:{event_id}", json.dumps(live_data))

        return live_data
    except Exception as e:
        print(f"[PollService] Error launching poll: {e}")
        traceback.print_exc()
        return None
    finally:
        if 'db' in locals() and db:
            db.close()
