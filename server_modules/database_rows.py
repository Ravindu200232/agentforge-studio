"""What the database panel shows beyond its command monitors: a few rows of one table or collection, and the Atlas
cluster behind the MongoDB connection.

Rows are read the same way the monitors read everything else: a Supabase table through the Supabase command line
tool (`db query --linked`, the account's token in its environment), a MongoDB collection through the project's own
driver (`scripts/mongo-inspect.mjs`, the connection string in its environment). A table or collection is named by the
person, so its name is checked before it goes anywhere: an identifier, quoted, never text spliced into a query.

Whatever comes back is masked before it leaves: a field whose name says it holds a credential (a password hash, a
token, a key) shows as `<masked>`, and any value that is one of the project's own credentials, or looks like one, is
hidden the way command output is.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from typing import Any

from . import cli_monitor, config, secrets_guard

SAMPLE = 20
COUNT_CAP = 10_000
TIMEOUT = 90
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")
COLLECTION = re.compile(r"^[^$\x00]{1,120}$")
SENSITIVE = re.compile(r"(pass(word|wd)?|secret|token|hash|salt|otp|api[_-]?key|private|credential)", re.IGNORECASE)


def _mask(value: Any, key: str, masked: set[str], hidden: list[str]) -> Any:
    if key and SENSITIVE.search(key) and value is not None and not isinstance(value, (dict, list)):
        masked.add(key)
        return "<masked>"
    if isinstance(value, dict):
        return {k: _mask(v, str(k), masked, hidden) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(item, "", masked, hidden) for item in value]
    if isinstance(value, str):
        for secret in hidden:
            if secret and len(secret) >= 6:
                value = value.replace(secret, "<hidden>")
        return secrets_guard.mask(value)
    return value


def _masked_rows(rows: list, hidden: list[str]) -> tuple[list, list[str]]:
    masked: set[str] = set()
    clean = [_mask(row, "", masked, hidden) for row in rows if isinstance(row, dict)]
    return clean, sorted(masked)


def _json_in(text: str) -> Any:
    """The JSON object a tool printed, with whatever progress lines it printed around it."""
    start = text.find("{")
    while start >= 0:
        try:
            return json.JSONDecoder().raw_decode(text[start:])[0]
        except ValueError:
            start = text.find("{", start + 1)
    raise ValueError("the command did not answer with JSON")


def _quoted(name: str, what: str) -> str:
    if not IDENTIFIER.match(name or ""):
        raise ValueError(f"{name!r} is not a {what} name")
    return f'"{name}"'


# --- Supabase ----------------------------------------------------------------------------------

def _supabase_sql(schema: str, table: str) -> str:
    target = f"{_quoted(schema, 'schema')}.{_quoted(table, 'table')}"
    # Both names passed the identifier check, so they hold no quote of either kind.
    return (
        "select json_build_object("
        "'columns', (select coalesce(json_agg(json_build_object('name', column_name, 'type', data_type, "
        "'nullable', is_nullable = 'YES') order by ordinal_position), '[]'::json) "
        f"from information_schema.columns where table_schema = '{schema}' and table_name = '{table}'), "
        f"'rows', (select coalesce(json_agg(t), '[]'::json) from (select * from {target} limit {SAMPLE}) t), "
        f"'total', (select count(*) from (select 1 from {target} limit {COUNT_CAP + 1}) c)"
        ") as sample;"
    )


def _supabase_rows(project: str, schema: str, table: str) -> dict[str, Any]:
    from . import supabase_connect

    row = supabase_connect.record(project)
    if not row:
        raise ValueError("this project has no Supabase project yet")
    sql = _supabase_sql(schema or "public", table)
    folder = config.record_dir(project) / "database"
    folder.mkdir(parents=True, exist_ok=True)
    query = folder / f"rows-{uuid.uuid4().hex[:8]}.sql"
    query.write_text(sql, encoding="utf-8")
    env, hidden = cli_monitor._set_environment("supabase", project)  # noqa: SLF001
    try:
        done = subprocess.run(
            [supabase_connect._tool(), "db", "query", "--linked", "--project-ref", row["ref"], "-o", "json",  # noqa: SLF001
             "-f", str(query)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
            stdin=subprocess.DEVNULL, cwd=str(folder), env={**os.environ, "NO_COLOR": "1", **env},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Supabase did not answer within {TIMEOUT} seconds") from exc
    finally:
        query.unlink(missing_ok=True)
    output = (done.stdout or "") + "\n" + (done.stderr or "")
    if done.returncode != 0:
        raise ValueError(cli_monitor._mask(output.strip(), hidden)[-400:] or "the Supabase CLI refused that query")  # noqa: SLF001
    answer = _json_in(done.stdout or "")
    sample = ((answer.get("rows") or [{}])[0] or {}).get("sample") or {}
    rows, masked = _masked_rows(sample.get("rows") or [], hidden)
    total = int(sample.get("total") or 0)
    return {"source": "supabase", "schema": schema or "public", "table": table, "limit": SAMPLE,
            "columns": sample.get("columns") or [], "rows": rows, "masked": masked,
            "total": total, "more": total > COUNT_CAP}


# --- MongoDB -----------------------------------------------------------------------------------

def _mongodb_rows(project: str, database: str, collection: str) -> dict[str, Any]:
    if not COLLECTION.match(collection or "") or collection.startswith("system."):
        raise ValueError(f"{collection!r} is not a collection name")
    if database and not re.match(r"^[A-Za-z0-9_.\- ]{1,64}$", database):
        raise ValueError(f"{database!r} is not a database name")
    if not cli_monitor.mongodb_uri():
        raise ValueError("no MongoDB connection string is saved yet")
    env, hidden = cli_monitor._set_environment("mongodb", project)  # noqa: SLF001
    node = cli_monitor.cli_signin._where("node")  # noqa: SLF001
    if not node:
        raise ValueError("Node.js is not installed on this computer")
    try:
        done = subprocess.run(
            [node, str(cli_monitor.SCRIPTS / "mongo-inspect.mjs"), "rows"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **env, "INSPECT_DATABASE": database or "", "INSPECT_COLLECTION": collection,
                 "INSPECT_LIMIT": str(SAMPLE)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"MongoDB did not answer within {TIMEOUT} seconds") from exc
    lines = [line for line in (done.stdout or "").splitlines() if line.strip().startswith("{")]
    if not lines:
        raise ValueError(cli_monitor._mask((done.stderr or "the read did not finish")[-300:], hidden))  # noqa: SLF001
    answer = json.loads(lines[-1])
    if not answer.get("ok"):
        raise ValueError(str(answer.get("message") or "the collection could not be read"))
    rows, masked = _masked_rows(answer.get("rows") or [], hidden)
    return {"source": "mongodb", "database": answer.get("database", database), "collection": collection,
            "limit": SAMPLE, "columns": [{"name": name} for name in answer.get("columns") or []],
            "rows": rows, "masked": sorted({*masked, *(answer.get("masked") or [])}),
            "total": answer.get("total"), "more": False}


def sample(project: str, body: dict[str, Any]) -> dict[str, Any]:
    """A few rows of the table or collection `body` names."""
    source = str(body.get("source") or "")
    if source == "supabase":
        return _supabase_rows(project, str(body.get("schema") or "public"), str(body.get("table") or ""))
    if source == "mongodb":
        return _mongodb_rows(project, str(body.get("database") or ""), str(body.get("collection") or ""))
    raise ValueError("choose a table or a collection first")


# --- the Atlas cluster -------------------------------------------------------------------------

def _host(connection: str) -> str:
    return re.sub(r"^[a-z+]+://(?:[^@/]*@)?", "", str(connection or "")).split("/")[0]


def atlas() -> dict[str, Any]:
    """The Atlas cluster this studio provisioned, its network access list and its database users (names only)."""
    from . import mongo_connect

    state = mongo_connect.status()
    answer: dict[str, Any] = {"connected": state["connected"], "org": state["org"], "cluster": None,
                              "access": [], "users": []}
    group = str(config.setting(mongo_connect.GROUP_ID_SETTING) or "")
    name = str(config.setting(mongo_connect.CLUSTER_NAME_SETTING) or "")
    if not state["connected"] or not group or not name:
        return answer
    try:
        cluster = mongo_connect._api("GET", f"/groups/{group}/clusters/{name}")  # noqa: SLF001
        # Atlas answers in one of two shapes: `replicationSpecs[].regionConfigs[]`, or the older
        # `providerSettings` (which shared M0/M2 clusters still come back in).
        region = ((cluster.get("replicationSpecs") or [{}])[0].get("regionConfigs") or [{}])[0]
        legacy = cluster.get("providerSettings") or {}
        answer["cluster"] = {
            "name": cluster.get("name", name), "state": cluster.get("stateName", ""),
            "version": cluster.get("mongoDBVersion", ""), "type": cluster.get("clusterType", ""),
            "tier": (region.get("electableSpecs") or {}).get("instanceSize") or legacy.get("instanceSizeName", ""),
            "provider": region.get("backingProviderName") or legacy.get("backingProviderName")
                        or region.get("providerName") or legacy.get("providerName", ""),
            "region": region.get("regionName") or legacy.get("regionName", ""), "paused": bool(cluster.get("paused")),
            "backup": bool(cluster.get("backupEnabled") or cluster.get("providerBackupEnabled")),
            "disk_gb": cluster.get("diskSizeGB"), "created": cluster.get("createDate", ""),
            "host": _host((cluster.get("connectionStrings") or {}).get("standardSrv", "") or cluster.get("srvAddress", "")),
        }
        answer["access"] = [{"entry": row.get("cidrBlock") or row.get("ipAddress") or row.get("awsSecurityGroup", ""),
                             "comment": row.get("comment", "")}
                            for row in mongo_connect._api("GET", f"/groups/{group}/accessList").get("results", [])]  # noqa: SLF001
        answer["users"] = [{"name": row.get("username", ""),
                            "roles": [f"{r.get('roleName')}@{r.get('databaseName')}" for r in row.get("roles") or []]}
                           for row in mongo_connect._api("GET", f"/groups/{group}/databaseUsers").get("results", [])]  # noqa: SLF001
    except ValueError as exc:
        answer["error"] = str(exc)[:300]
    return answer
