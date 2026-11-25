#!/usr/bin/env python3
"""Collect public TikTok Shop US listing data into data/products.json.

Reads the server-rendered category pages (the same JSON the page hydrates
from) and keeps the fields the site shows: title, price, rating, review
count, units sold, seller, canonical URL.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "products.json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)
BASE = "https://shop.tiktok.com/us/c"
ROUTE_KEY = "(region)/c/(category_name)/(category_id)/page"
DELAY_SECONDS = 1.5

# Top-level categories the site covers. Health, food and pre-owned are left
# out on purpose: listings there lean on claims we can't check.
TOP_CATEGORIES = {
    "601450": "beauty-personal-care",
    "601739": "phones-electronics",
    "605248": "fashion-accessories",
    "600001": "home-supplies",
    "600024": "kitchenware",
    "603014": "sports-outdoor",
    "604206": "toys-hobbies",
    "601755": "computers-office-equipment",
    "604579": "tools-hardware",
    "602118": "pet-supplies",
    "600154": "textiles-soft-furnishings",
    "801928": "books-magazines-audio",
}


def fetch(slug: str, category_id: str) -> dict | None:
    url = f"{BASE}/{slug}/{category_id}"
    html = subprocess.run(
        ["curl", "-sS", "-m", "30", "-L", "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9", url],
        capture_output=True,
        text=True,
    ).stdout
    match = re.search(
        r'<script type="application/json" id="__MODERN_ROUTER_DATA__">(.*?)</script>', html, re.S
    )
    if not match:
        print(f"  no router data: {url}", file=sys.stderr)
        return None
    return json.loads(match.group(1))["loaderData"].get(ROUTE_KEY)


def product_list(page: dict) -> list[dict]:
    for component in page["page_config"]["components_map"]:
        data = component.get("component_data")
        if isinstance(data, dict) and "categoryProductsData" in data:
            return data["categoryProductsData"].get("productList") or []
    return []


def to_number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(raw: dict, top_slug: str, sub_slug: str | None) -> dict | None:
    price = raw.get("product_price_info") or {}
    rate = raw.get("rate_info") or {}
    url = (raw.get("seo_url") or {}).get("canonical_url")
    sale = to_number(price.get("sale_price_decimal"))
    if not url or sale is None or price.get("currency_name") != "USD":
        return None
    images = (raw.get("image") or {}).get("url_list") or []
    return {
        "id": raw["product_id"],
        "title": raw["title"].strip(),
        "url": url,
        "price": sale,
        "list_price": to_number(price.get("origin_price_decimal")),
        "price_from": price.get("price_prefix") == "From",
        "rating": to_number(rate.get("score")),
        "reviews": int(to_number(rate.get("review_count")) or 0),
        "sold": int((raw.get("sold_info") or {}).get("sold_count") or 0),
        "shop": (raw.get("seller_info") or {}).get("shop_name") or "",
        "category": top_slug,
        "subcategory": sub_slug,
        "image": images[0] if images else None,
    }


def main() -> None:
    products: dict[str, dict] = {}
    subcategories: list[tuple[str, str, str]] = []
    category_names: dict[str, str] = {}

    for category_id, slug in TOP_CATEGORIES.items():
        page = fetch(slug, category_id)
        time.sleep(DELAY_SECONDS)
        if not page:
            continue
        for node in page["category_hierarchy"]:
            info = node["self"]
            if info["category_id"] == category_id:
                category_names[slug] = info["category_name"]
                for child in node.get("children") or []:
                    child_info = child["self"]
                    category_names[child_info["category_name_en"]] = child_info["category_name"]
                    subcategories.append((slug, child_info["category_name_en"], child_info["category_id"]))
        for raw in product_list(page):
            item = normalize(raw, slug, None)
            if item:
                products.setdefault(item["id"], item)
        print(f"{slug}: {len(products)} total", file=sys.stderr)

    for top_slug, sub_slug, sub_id in subcategories:
        page = fetch(sub_slug, sub_id)
        time.sleep(DELAY_SECONDS)
        if not page:
            continue
        for raw in product_list(page):
            item = normalize(raw, top_slug, sub_slug)
            if not item:
                continue
            known = products.get(item["id"])
            if known is None:
                products[item["id"]] = item
            elif known["subcategory"] is None and known["category"] == top_slug:
                known["subcategory"] = sub_slug
        print(f"{top_slug}/{sub_slug}: {len(products)} total", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "category_names": category_names,
                "products": sorted(products.values(), key=lambda p: p["id"]),
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"wrote {len(products)} products to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
