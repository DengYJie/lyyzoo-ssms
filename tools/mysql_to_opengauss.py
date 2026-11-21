#!/usr/bin/env python3
"""Convert a MySQL mysqldump file into an openGauss B-mode import script.

openGauss B + Dolphin needs MySQL client directives removed, foreign keys
deferred until all tables exist, and MySQL 8's utf8mb3 aliases mapped to utf8.
Data literals are copied verbatim. The result is one transaction that refuses
to run on a non-empty public schema.

Statements are found with a quote/comment aware scanner because the dump holds
single-line hex BLOBs of several hundred kilobytes and values containing ';'.

Usage: python tools/mysql_to_opengauss.py --input dump.sql --output import.sql
Exit:  0 converted, 2 input problem, 3 unsupported SQL construct.
"""

import argparse
import re
import sys

PROG = "mysql_to_opengauss.py"


class ConvertError(Exception):
    def __init__(self, message, exit_code=3):
        Exception.__init__(self, message)
        self.exit_code = exit_code


def skip_quoted(sql, i):
    """Return the index past the quoted token at i (backslash and doubled quotes)."""
    quote = sql[i]
    j = i + 1
    while j < len(sql):
        if sql[j] == "\\":
            j += 2
        elif sql[j] == quote:
            if sql[j + 1:j + 2] != quote:
                return j + 1
            j += 2  # doubled quote stays inside the literal
        else:
            j += 1
    raise ConvertError("line %d: unterminated %s quote"
                       % (sql.count("\n", 0, i) + 1, quote), 2)


def scan_group(sql, i):
    """Return the index of the ')' matching the '(' at i, skipping quoted text."""
    depth = 0
    while i < len(sql):
        c = sql[i]
        if c in "'`":
            i = skip_quoted(sql, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ConvertError("unbalanced parentheses in %r" % sql[:60], 2)


def split_statements(text):
    """Split a dump into (line, sql) pairs, dropping comments and blanks."""
    statements = []
    buf = []
    i = 0
    line = 1
    start = None
    while i < len(text):
        c = text[i]

        if c in "'`":
            if start is None:
                start = line
            end = skip_quoted(text, i)
            buf.append(text[i:end])
            line += text.count("\n", i, end)
            i = end
            continue

        if c == '"':
            raise ConvertError(
                "line %d: double-quoted text is unexpected; mysqldump emits "
                "single-quoted strings" % line)

        # "--" only opens a comment before whitespace or end of line, so data
        # such as a--b stays data.
        if (text.startswith("--", i)
                and text[i + 2:i + 3] in ("", " ", "\t", "\r", "\n")) or c == "#":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue

        if text.startswith("/*", i):
            if not text.startswith("/*!", i):
                end = text.find("*/", i + 2)
                if end < 0:
                    raise ConvertError("line %d: unterminated comment" % line, 2)
                line += text.count("\n", i, end + 2)
                i = end + 2
                continue
            # The server would execute the /*! body, so unwrap it as a statement.
            end = text.find("*/", i + 3)
            if end < 0:
                raise ConvertError("line %d: unterminated /*! comment" % line, 2)
            if start is None:
                start = line
            buf.append(" " + re.sub(r"^\d{5,6}", "", text[i + 3:end]) + " ")
            line += text.count("\n", i, end + 2)
            i = end + 2
            continue

        if c == ";":
            sql = "".join(buf).strip()
            if sql:
                statements.append((start or line, sql))
            buf = []
            start = None
            i += 1
            continue

        if start is None and not c.isspace():
            start = line
        if c == "\n":
            line += 1
        buf.append(c)
        i += 1

    sql = "".join(buf).strip()
    if sql:
        statements.append((start or line, sql))
    return statements


def split_definitions(body):
    """Split a CREATE TABLE body on commas outside nesting and quotes."""
    parts = []
    depth = 0
    i = 0
    begin = 0
    while i < len(body):
        c = body[i]
        if c in "'`":
            i = skip_quoted(body, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[begin:i].strip())
            begin = i + 1
        i += 1
    parts.append(body[begin:].strip())
    return [part for part in parts if part]


CREATE_HEAD = re.compile(
    r"(?is)^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(`[^`]+`|[A-Za-z0-9_$]+)\s*\(")
CREATE_TABLE = re.compile(r"(?is)^CREATE\s+TABLE\b")
INSERT_TARGET = re.compile(r"(?is)^INSERT\s+INTO\s+(`[^`]+`|[A-Za-z0-9_$]+)")
FOREIGN_KEY = re.compile(
    r"(?is)^(?:CONSTRAINT\s+(?:`[^`]+`|[A-Za-z0-9_$]+)\s+)?FOREIGN\s+KEY\s*\(")
UTF8_ALIAS = re.compile(
    r"(?i)(\b(?:CHARACTER\s+SET|CHARSET|COLLATE)\s*(?:=\s*)?)utf8mb3(?=_|\b)")

# Session/DDL noise the dump carries and openGauss does not need.
SKIPPED = re.compile(
    r"(?is)^(SET|LOCK\s+TABLES|UNLOCK\s+TABLES|USE|DROP\s+TABLE"
    r"|ALTER\s+TABLE(?=\s+(?:\S+\s+)?(?:DISABLE|ENABLE)\s+KEYS\b))\b")
SKIPPED_LABELS = {"LOCK TABLES": "LOCK", "UNLOCK TABLES": "UNLOCK"}


def convert_create_table(sql, line):
    """Return (create_sql, [(table_ref, constraint)], table_name).

    The body is re-emitted from its definitions, which is how named foreign keys
    are lifted out for replay after the data.
    """
    # An unsupported collation silently falls back to case-sensitive defaults.
    parts = []
    start = i = 0
    while i < len(sql):
        if sql[i] in "'`":
            end = skip_quoted(sql, i)
            parts.append(UTF8_ALIAS.sub(r"\1utf8", sql[start:i]))
            parts.append(sql[i:end])
            start = i = end
        else:
            i += 1
    parts.append(UTF8_ALIAS.sub(r"\1utf8", sql[start:]))
    sql = "".join(parts)
    match = CREATE_HEAD.match(sql)
    if not match:
        raise ConvertError(
            "line %d: CREATE TABLE without a definition list: %r" % (line, sql[:60]))
    table_ref = match.group(1)
    begin = match.end() - 1
    close = scan_group(sql, begin)

    kept = []
    foreign_keys = []
    for definition in split_definitions(sql[begin + 1:close]):
        if FOREIGN_KEY.match(definition):
            foreign_keys.append((table_ref, definition))
        elif re.search(r"(?is)\bREFERENCES\b", definition):
            raise ConvertError(
                "line %d: column level REFERENCES in %s is unsupported; make it a "
                "table level FOREIGN KEY" % (line, table_ref))
        else:
            kept.append(definition)
    if not kept:
        raise ConvertError("line %d: table %s has no columns" % (line, table_ref))

    tail = sql[close + 1:].strip()
    create_sql = sql[:begin].rstrip() + " (\n  " + ",\n  ".join(kept) + "\n)"
    return (create_sql + " " + tail if tail else create_sql) + ";", \
        foreign_keys, table_ref.strip("`")


def count_rows(sql, line):
    """Count the row tuples after VALUES, ignoring text inside quotes."""
    depth = rows = 0
    seen = False
    i = 0
    while i < len(sql):
        if sql[i] in "'`":
            i = skip_quoted(sql, i)
            continue
        if (sql[i:i + 6].upper() == "VALUES"
                and not sql[i - 1:i].isalnum() and not sql[i + 6:i + 7].isalnum()):
            seen = True
            i += 6
            continue
        if seen:
            if sql[i] == "(":
                rows += 1 if depth == 0 else 0
                depth += 1
            elif sql[i] == ")":
                depth -= 1
        i += 1
    if not seen:
        raise ConvertError(
            "line %d: INSERT without a VALUES list is unsupported; load its rows "
            "as VALUES" % line)
    if rows == 0:
        raise ConvertError("line %d: INSERT has no row tuples" % line)
    return rows


TEMPLATE = """\
-- openGauss B-mode import generated by tools/{prog}; re-run, do not edit.
-- {tables} tables, {rows} rows, {foreign_keys} foreign keys deferred until after the data.

\\set ON_ERROR_STOP on

BEGIN;

SET client_encoding TO 'UTF8';
SET LOCAL search_path TO public;

-- Fail before the first DDL rather than leave a half-built schema.
-- pg_tables counts base tables, so the Dolphin helper views do not trip it.
DO $$
DECLARE
    existing_count integer;
    first_table text;
BEGIN
    SELECT count(*), min(tablename) INTO existing_count, first_table
      FROM pg_tables WHERE schemaname = 'public';
    IF existing_count > 0 THEN
        RAISE EXCEPTION 'target schema public is not empty: %, first table %',
            existing_count, first_table;
    END IF;
END;
$$;

-- Table structure, foreign keys removed.
{creates}

-- Row data.
{data}

-- Foreign keys, now that every table and row exists.
{alters}

COMMIT;
"""


def convert(text):
    """Return (script_text, summary) for a dump already decoded as UTF-8."""
    statements = split_statements(text)
    if not statements:
        raise ConvertError("no SQL statements found in the input", 2)

    creates, data, foreign_keys, tables = [], [], [], []
    rows_per_table, dropped = {}, {}

    for line, sql in statements:
        skip = SKIPPED.match(sql)
        if skip:
            head = skip.group(1).upper()
            label = SKIPPED_LABELS.get(head, head)
            dropped[label] = dropped.get(label, 0) + 1
            continue

        if CREATE_TABLE.match(sql):
            create_sql, keys, name = convert_create_table(sql, line)
            creates.append(create_sql)
            foreign_keys.extend(keys)
            if name not in tables:
                tables.append(name)
            continue

        insert = INSERT_TARGET.match(sql)
        if insert:
            table = insert.group(1).strip("`")
            rows_per_table[table] = rows_per_table.get(table, 0) + count_rows(sql, line)
            data.append(sql + ";")
            continue

        raise ConvertError("line %d: unsupported statement %r" % (line, sql[:60]))

    if not creates:
        raise ConvertError("no CREATE TABLE statement found in the input", 2)
    for _, definition in foreign_keys:
        if not re.match(r"(?is)^CONSTRAINT\b", definition):
            raise ConvertError(
                "unnamed FOREIGN KEY %r cannot be replayed with ALTER TABLE; name "
                "the constraint in the dump" % definition[:60])

    total = sum(rows_per_table.values())
    script = TEMPLATE.format(
        prog=PROG, tables=len(creates), rows=total, foreign_keys=len(foreign_keys),
        creates="\n".join(creates), data="\n".join(data),
        alters="\n".join("ALTER TABLE %s ADD %s;" % pair for pair in foreign_keys))
    return script, {"tables": tables, "rows_per_table": rows_per_table,
                    "rows": total, "foreign_keys": len(foreign_keys),
                    "dropped": dropped}


def main(argv=None):
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True, help="MySQL mysqldump output")
    parser.add_argument("--output", required=True, help="import script for gsql")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "rb") as handle:
            raw = handle.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ConvertError(
                "%s is not valid UTF-8 (%s); re-export with "
                "--default-character-set=utf8mb4" % (args.input, exc), 2)
        script, summary = convert(text)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(script)
    except ConvertError as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return exc.exit_code
    except OSError as exc:
        sys.stderr.write("%s: %s\n" % (PROG, exc))
        return 2

    out = ["%s: %s -> %s" % (PROG, args.input, args.output),
           "  %d tables, %d rows, %d foreign keys"
           % (len(summary["tables"]), summary["rows"], summary["foreign_keys"])]
    out.extend("    %-24s %d" % (t, summary["rows_per_table"].get(t, 0))
               for t in summary["tables"])
    dropped = ", ".join("%s x%d" % item for item in sorted(summary["dropped"].items()))
    out.append("  dropped: %s" % (dropped or "nothing"))
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
