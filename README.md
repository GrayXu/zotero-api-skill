Zotero Skill
============

This skill provides a compact Zotero API CLI for downloading, reading, searching,
creating, and updating items.

Paths and usage
---------------
Run from the repo root:

- `python zotero-skill/scripts/zotero_cli.py --help`
- `./zotero-skill/scripts/zotero_cli.py --help`

Environment variables
---------------------
- `ZOTERO_USER`: Zotero user ID
- `ZOTERO_API_KEY`: Zotero API key

You can override them with `--user` / `--api-key`.

Common commands
---------------
Download all items (skip attachments by default):
```bash
python zotero-skill/scripts/zotero_cli.py download --output-dir ./output
```

Fetch a single item:
```bash
python zotero-skill/scripts/zotero_cli.py get --key ABCD1234
```

Search:
```bash
python zotero-skill/scripts/zotero_cli.py search --query "transformer retrieval" --limit 10
```

Create (data-only JSON):
```bash
python zotero-skill/scripts/zotero_cli.py create --input ./new_item.json --data-only
```

Update (full item JSON or data-only):
```bash
python zotero-skill/scripts/zotero_cli.py update --key ABCD1234 --input ./item.json
```

Input formats
-------------
- `create`/`update` support:
  - full items (with a top-level `data` field)
  - data-only objects (use `--data-only`)
  - `create` also accepts arrays of objects
