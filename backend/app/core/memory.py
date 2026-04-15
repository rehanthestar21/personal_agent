import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

from app.config import Settings

logger = logging.getLogger("vertex.memory")

DB_PATH = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "data" / "vertex_memory.db"
SEED_FILE = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "data" / "personal_context.md"

EXTRACT_PROMPT = """You are a memory extraction system. Given a conversation between a user and their AI assistant, extract important facts, preferences, and information worth remembering long-term.

Return a JSON array of memory objects. Each object has:
- "fact": a concise statement of the fact (one sentence)
- "category": one of "preference", "fact", "project", "person", "habit", "goal", "event"

Only extract genuinely useful information. Skip small talk and transient requests.
If there's nothing worth remembering, return an empty array [].

Conversation:
{conversation}

Respond ONLY with the JSON array, nothing else."""


class MemoryStore:
    """SQLite-backed long-term memory that persists across restarts."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._db_path = DB_PATH
        self._init_db()
        self._load_seed_if_needed()

    def _init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'fact',
                source TEXT NOT NULL DEFAULT 'conversation',
                created_at REAL NOT NULL,
                UNIQUE(fact)
            )
        """)
        conn.commit()
        conn.close()
        logger.info("[memory] database initialized at %s", self._db_path)

    def _load_seed_if_needed(self):
        conn = sqlite3.connect(str(self._db_path))
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE source = 'seed'").fetchone()[0]

        if count > 0:
            logger.info("[memory] seed already loaded (%d facts)", count)
            conn.close()
            return

        if not SEED_FILE.exists():
            logger.info("[memory] no seed file found at %s", SEED_FILE)
            conn.close()
            return

        seed_text = SEED_FILE.read_text()
        lines = seed_text.strip().split("\n")
        facts = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if len(line) > 10 and ":" in line:
                facts.append(line)
            elif len(line) > 20:
                facts.append(line)

        now = time.time()
        inserted = 0
        for fact in facts:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO memories (fact, category, source, created_at) VALUES (?, ?, ?, ?)",
                    (fact, "seed", "seed", now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        conn.close()
        logger.info("[memory] loaded %d seed facts from personal_context.md", inserted)

    def get_all_memories(self, limit: int = 100) -> list[dict]:
        conn = sqlite3.connect(str(self._db_path))
        rows = conn.execute(
            "SELECT fact, category, source FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"fact": r[0], "category": r[1], "source": r[2]} for r in rows]

    def search_memories(self, query: str, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(str(self._db_path))
        words = query.lower().split()
        if not words:
            return self.get_all_memories(limit)

        conditions = " OR ".join(["LOWER(fact) LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        params.append(limit)

        rows = conn.execute(
            f"SELECT fact, category, source FROM memories WHERE {conditions} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        conn.close()
        return [{"fact": r[0], "category": r[1], "source": r[2]} for r in rows]

    def get_memory_summary(self, max_chars: int = 3000) -> str:
        memories = self.get_all_memories(limit=150)
        if not memories:
            return ""

        lines = []
        total = 0
        for m in memories:
            line = m["fact"]
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)

        return "\n".join(lines)

    def add_memory(self, fact: str, category: str = "fact") -> bool:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "INSERT OR IGNORE INTO memories (fact, category, source, created_at) VALUES (?, ?, ?, ?)",
                (fact, category, "conversation", time.time()),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    async def extract_and_store(self, conversation: str):
        """Background: extract facts from a conversation and store them."""
        try:
            response = await self._client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "user", "content": EXTRACT_PROMPT.format(conversation=conversation)},
                ],
                max_completion_tokens=500,
            )

            content = response.choices[0].message.content or "[]"
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]

            facts = json.loads(content)
            stored = 0
            for f in facts:
                if isinstance(f, dict) and "fact" in f:
                    if self.add_memory(f["fact"], f.get("category", "fact")):
                        stored += 1
                        logger.info("[memory] stored: %s", f["fact"])

            if stored:
                logger.info("[memory] extracted %d new facts from conversation", stored)

        except Exception as e:
            logger.error("[memory] extraction failed: %s", e)
