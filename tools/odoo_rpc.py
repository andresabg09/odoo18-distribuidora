#!/usr/bin/env python3
"""Small Odoo JSON-RPC client with a safety catch: reads are free, writes are a DRY RUN unless --apply.

Credentials are never stored in the repo: they come from environment variables.

    ODOO_URL      https://odoo.example.com        (scheme and host only)
    ODOO_DB       my_database
    ODOO_UID      numeric id of the user that owns the key
    ODOO_API_KEY  API key (Odoo -> Preferences -> Account Security)

Reads (always pass the fields you need):
    odoo_rpc.py search_read sale.order '[["state","=","sale"]]' name,amount_total --limit 5
    odoo_rpc.py search_count stock.picking '[["state","=","assigned"]]'
    odoo_rpc.py read product.product 42 name,free_qty,qty_available
    odoo_rpc.py fields_get product.template --attrs string,type
    odoo_rpc.py module my_custom_module            # installed state and version of a module

Writes change the database. By default they only PRINT what they would do:
    odoo_rpc.py write stock.picking 123 '{"note":"x"}'            # dry run
    odoo_rpc.py write stock.picking 123 '{"note":"x"}' --apply    # really runs
    odoo_rpc.py create res.partner '{"name":"Test"}' --apply
    odoo_rpc.py call stock.picking 123 action_cancel --apply      # business method
    odoo_rpc.py write product.public.category 7 '{"name":"Care"}' --context '{"lang":"es_419"}' --apply

There is deliberately no "delete" (unlink) and no private (_underscore) methods: to remove something you
archive it (write active=False) or cancel it with its business method.
"""
import argparse
import json
import os
import sys
import urllib.request

READ_METHODS = {"search_read", "search_count", "read", "fields_get", "name_search", "get_views"}
FORBIDDEN_METHODS = {"unlink"}


def _env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing environment variable {name}.")
    return value


def call(model, method, args, kwargs=None, allow_write=False):
    if method in FORBIDDEN_METHODS or method.startswith("_"):
        sys.exit(f'Method "{method}" is not allowed (no delete, no private methods).')
    if method not in READ_METHODS and not allow_write:
        sys.exit(f'Method "{method}" is not a read: it only runs with --apply.')
    url = _env("ODOO_URL").rstrip("/") + "/jsonrpc"
    payload = {"jsonrpc": "2.0", "method": "call", "id": 1, "params": {
        "service": "object", "method": "execute_kw",
        "args": [_env("ODOO_DB"), int(_env("ODOO_UID")), _env("ODOO_API_KEY"), model, method, args, kwargs or {}],
    }}
    request = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)
    if data.get("error"):
        error = data["error"].get("data", {}).get("message") or data["error"].get("message")
        sys.exit(f"Odoo returned an error: {error}")
    return data.get("result")


def _ids(text):
    ids = json.loads(text)
    return ids if isinstance(ids, list) else [ids]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", help="search_read | search_count | read | fields_get | name_search | module | write | create | call")
    parser.add_argument("model", help='model (e.g. sale.order) or, with "module", the technical module name')
    parser.add_argument("arg", nargs="?", default="[]", help="JSON domain (search_*), ids (read/write/call) or text (name_search)")
    parser.add_argument("fields", nargs="?", default="", help="comma-separated fields (reads), JSON values (write) or method name (call)")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--order", default=None)
    parser.add_argument("--attrs", default="string,type")
    parser.add_argument("--apply", action="store_true", help="really execute a write (without it, it is a dry run)")
    parser.add_argument("--context", default="{}", help='JSON context, e.g. {"lang":"es_419"}')
    opts = parser.parse_args()

    fields = [f for f in opts.fields.split(",") if f]
    context = json.loads(opts.context)
    ctx_kwargs = {"context": context} if context else {}

    if opts.action == "module":
        result = call("ir.module.module", "search_read", [[["name", "=", opts.model]]],
                      {"fields": ["name", "state", "latest_version", "installed_version", "write_date"]})
    elif opts.action == "search_read":
        kwargs = {"fields": fields, "limit": opts.limit, **ctx_kwargs}
        if opts.order:
            kwargs["order"] = opts.order
        result = call(opts.model, "search_read", [json.loads(opts.arg)], kwargs)
    elif opts.action == "search_count":
        result = call(opts.model, "search_count", [json.loads(opts.arg)])
    elif opts.action == "read":
        result = call(opts.model, "read", [_ids(opts.arg)], {"fields": fields, **ctx_kwargs})
    elif opts.action == "fields_get":
        result = call(opts.model, "fields_get", [], {"attributes": opts.attrs.split(",")})
    elif opts.action == "name_search":
        result = call(opts.model, "name_search", [opts.arg], {"limit": opts.limit})
    elif opts.action in ("write", "create", "call"):
        if opts.action == "write":
            method, args = "write", [_ids(opts.arg), json.loads(opts.fields)]
        elif opts.action == "create":
            method, args = "create", [json.loads(opts.arg)]
        else:
            method, args = opts.fields, [_ids(opts.arg)]
            if not method:
                sys.exit("Missing the method name (e.g. action_cancel).")
        if not opts.apply:
            print("DRY RUN (nothing was changed). Add --apply to execute:")
            print(json.dumps({"model": opts.model, "method": method, "args": args, "kwargs": ctx_kwargs},
                             ensure_ascii=False, indent=1))
            return
        result = call(opts.model, method, args, ctx_kwargs, allow_write=True)
    else:
        sys.exit(f"Unknown action: {opts.action}")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
