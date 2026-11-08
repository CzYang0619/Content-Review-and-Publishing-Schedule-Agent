import hashlib
import json
from datetime import datetime


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_request(req):
    required = ("request_id", "material_id", "requested_at", "channel", "hard_requirement")
    missing = [key for key in required if key not in req or req[key] is None or req[key] == ""]
    if missing:
        raise ValueError("Missing request fields: " + ", ".join(missing))
    for key in ("request_id", "material_id", "channel"):
        if not isinstance(req[key], str) or not req[key].strip():
            raise ValueError(key + " must be a nonempty string")
    if type(req["hard_requirement"]) is not bool:
        raise ValueError("hard_requirement must be boolean")
    slot(req["requested_at"])
    if req.get("confirmed_at"):
        slot(req["confirmed_at"])


def slot(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 28800:
        raise ValueError("Use explicit +08:00 timezone")
    if dt.minute or dt.second or dt.microsecond:
        raise ValueError("Only whole-hour, one-hour slots are supported")
    if dt.isoformat() != value:
        raise ValueError("Use canonical ISO format, e.g. 2026-11-10T18:00:00+08:00")
    return dt


def review(material, rules):
    missing = [key for key in rules["required_fields"] if not material.get(key)]
    risks = []
    if missing:
        risks.append({"code": "MISSING_METADATA", "fields": missing})
    if material.get("copyright") not in (None, "", "cleared"):
        risks.append({"code": "COPYRIGHT_NOT_CLEARED"})
    for term in rules["blocked_terms"]:
        if term in material.get("title", ""):
            risks.append({"code": "BLOCKED_CLAIM", "term": term})
    blocked = any(x["code"] != "MISSING_METADATA" for x in risks)
    return {"status": "blocked" if blocked else "needs_info" if missing else "passed", "risks": risks}
