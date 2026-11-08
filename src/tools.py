import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from .domain import canonical, fingerprint, review, slot


class ToolError(Exception):
    pass


class Tools:
    """Trusted business boundary; model output never establishes approval or persistence."""

    def __init__(self, req, world, db):
        self.req, self.world = req, world
        self.read = None
        self.checked = None
        self.queried = set()
        self.calls = {}
        self.db = str(db)
        Path(self.db).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, channel TEXT NOT NULL, at TEXT NOT NULL, confirmed INTEGER NOT NULL)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS confirmed_slot ON drafts(channel, at) WHERE confirmed=1")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def existing(self):
        with self.connect() as conn:
            row = conn.execute("SELECT fingerprint, payload FROM drafts WHERE request_id=?", (self.req["request_id"],)).fetchone()
        if row:
            if row[0] != fingerprint(self.req):
                raise ToolError("IDEMPOTENCY_KEY_CONFLICT")
            return json.loads(row[1])

    def occupied(self, at, conn=None):
        external = any(x["at"] == at and x["channel"] == self.req["channel"] for x in self.world["schedule"])
        if conn is not None:
            row = conn.execute("SELECT 1 FROM drafts WHERE channel=? AND at=? AND confirmed=1", (self.req["channel"], at)).fetchone()
        else:
            with self.connect() as connection:
                row = connection.execute("SELECT 1 FROM drafts WHERE channel=? AND at=? AND confirmed=1", (self.req["channel"], at)).fetchone()
        return external or bool(row)

    def execute(self, name, args):
        allowed = {"read_material": {"supplement"}, "check_rules": set(), "query_slots": {"start_at"}, "save_draft": {"suggested_at"}}
        if name not in allowed or not isinstance(args, dict) or set(args) - allowed[name]:
            raise ToolError("INVALID_TOOL_OR_ARGUMENTS")
        self.calls[name] = self.calls.get(name, 0) + 1
        fail = self.world.get("failures", {}).get(name)
        if fail == "always" or (fail == "once" and self.calls[name] == 1):
            raise ToolError("INJECTED_" + name.upper() + "_FAILURE")
        if name == "read_material":
            if type(args.get("supplement", False)) is not bool:
                raise ToolError("supplement must be boolean")
            material = dict(self.world["materials"].get(self.req["material_id"], {}))
            if not material:
                raise ToolError("MATERIAL_NOT_FOUND")
            if args.get("supplement"):
                material.update(self.world.get("supplements", {}).get(self.req["material_id"], {}))
            self.read, self.checked = material, None
            return {"material": material, "supplement_checked": bool(args.get("supplement"))}
        if name == "check_rules":
            if self.read is None:
                raise ToolError("READ_MATERIAL_FIRST")
            self.checked = review(self.read, self.world["rules"])
            return self.checked
        if name == "query_slots":
            start = slot(args.get("start_at", self.req["requested_at"]))
            slots = []
            for i in range(3):
                at = (start + timedelta(hours=i)).isoformat()
                self.queried.add(at)
                slots.append({"at": at, "available": not self.occupied(at)})
            return {"slots": slots, "reserved": False}
        return self.save(args.get("suggested_at"))

    def save(self, at):
        slot(at)
        if not self.checked or self.checked["status"] != "passed":
            raise ToolError("REVIEW_NOT_PASSED")
        if at not in self.queried:
            raise ToolError("QUERY_SLOT_FIRST")
        changed = at != self.req["requested_at"]
        confirmed = not changed or self.req.get("confirmed_at") == at
        if changed and self.req["hard_requirement"] and not confirmed:
            # A proposal may be stored, but it cannot replace the requested time.
            confirmation = "pending_hard_requirement_change"
        else:
            confirmation = "confirmed" if confirmed else "pending"
        payload = {"draft_id": "draft_" + uuid.uuid4().hex[:12], "requested_at": self.req["requested_at"], "suggested_at": at, "confirmation_status": confirmation, "saved": True, "published": False, "reserved": confirmed}
        # Recheck under write transaction, including other confirmed drafts.
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT fingerprint,payload FROM drafts WHERE request_id=?", (self.req["request_id"],)).fetchone()
            if previous:
                if previous[0] != fingerprint(self.req):
                    raise ToolError("IDEMPOTENCY_KEY_CONFLICT")
                return {**json.loads(previous[1]), "duplicate": True, "availability_revalidated": False}
            if self.occupied(at, conn):
                raise ToolError("SLOT_CONFLICT_AT_SAVE")
            conn.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?)", (payload["draft_id"], self.req["request_id"], fingerprint(self.req), canonical(payload), self.req["channel"], at, int(confirmed)))
        return {**payload, "duplicate": False}

    def count(self):
        with self.connect() as conn:
            return conn.execute("SELECT count(*) FROM drafts").fetchone()[0]
