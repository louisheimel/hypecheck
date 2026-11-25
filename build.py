#!/usr/bin/env python3
"""Generate the static site into docs/ from data/products.json."""
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
BASE = "/hypecheck"
SITE_URL = "https://louisheimel.github.io" + BASE
SITE_NAME = "Hype Check"
REPO_URL = "https://github.com/louisheimel/hypecheck"

# A product needs this much public feedback before it can appear anywhere.
MIN_REVIEWS = 25
MIN_RATING = 4.5
# Review-weighted rating: a listing's score is pulled toward PRIOR_RATING
# until it has well over PRIOR_WEIGHT reviews.
PRIOR_RATING = 4.5
PRIOR_WEIGHT = 50

# Listings the site never shows: consumables and remedies whose claims reviews
# can't verify, weapons, alcohol-themed and adult items, and chance-based sales.
EXCLUDED_SUBCATEGORIES = {
    "dog-cat-food",
    "dog-cat-healthcare",
    "farm-animal-poultry-supplies",
    "feminine-care",
    "eye-ear-care",
    "special-personal-care",
}
EXCLUDED_TERMS = re.compile(
    r"supplement|vitamin|peptide|glp-1|insulin|salmon oil|water additive|itch relief|intimate"
    r"|\btreats?\b|jerky"
    r"|pocket knife|camping knife|tactical|master key"
    r"|drinking game|shot glass|cigarette|sexy|per break|bat break",
    re.IGNORECASE,
)
# Sellers prepend sale tags such as 【Black Friday】 to listing titles.
PROMO_TAG = re.compile(
    r"【[^】]*】|^\s*\[(?:christmas gift|without logo)\]|^\s*(?:black friday!|christmas gift|xmas)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    intro: str
    categories: tuple[str, ...] = ()
    max_price: float | None = None
    min_rating: float = MIN_RATING
    min_reviews: int = MIN_REVIEWS
    by_sold: bool = False
    limit: int = 15


GUIDES = (
    Guide(
        slug="gifts-under-25",
        title="Gifts under $25 with 4.7 stars or better",
        intro=(
            "Every pick here costs $25 or less and holds a 4.7-star average across at least "
            "100 buyer reviews. Ranked by review-weighted rating, so a 4.9 from 2,000 buyers "
            "beats a 5.0 from 30."
        ),
        max_price=25,
        min_rating=4.7,
        min_reviews=100,
        limit=20,
    ),
    Guide(
        slug="stocking-stuffers-under-10",
        title="Stocking stuffers under $10",
        intro=(
            "Small, cheap and well reviewed: everything on this list is $10 or less with at "
            "least a 4.6-star average."
        ),
        max_price=10,
        min_rating=4.6,
        limit=20,
    ),
    Guide(
        slug="most-bought",
        title="Most-bought products that still hold 4.6 stars",
        intro=(
            "Sorted by units sold. Popularity alone is easy to manufacture, so each product "
            "also needs a 4.6-star average from at least 200 reviews to make the list."
        ),
        min_rating=4.6,
        min_reviews=200,
        by_sold=True,
        limit=20,
    ),
    Guide(
        slug="beauty",
        title="Beauty and personal care worth the hype",
        intro="Makeup, skincare, hair and grooming listings with the strongest review records.",
        categories=("beauty-personal-care",),
    ),
    Guide(
        slug="kitchen",
        title="Kitchen gear buyers keep rating highly",
        intro="Cookware, gadgets, drinkware and storage, ranked by review-weighted rating.",
        categories=("kitchenware",),
    ),
    Guide(
        slug="home",
        title="Home and bedding upgrades",
        intro="Organizers, decor, cleaning tools and soft furnishings with proven reviews.",
        categories=("home-supplies", "textiles-soft-furnishings"),
    ),
    Guide(
        slug="tech",
        title="Phone, audio and desk tech",
        intro="Chargers, cases, earbuds and computer accessories that buyers rate well.",
        categories=("phones-electronics", "computers-office-equipment"),
    ),
    Guide(
        slug="toys-and-games",
        title="Toys, games and hobby kits",
        intro="Plush, puzzles, building sets and craft kits with strong buyer ratings.",
        categories=("toys-hobbies",),
    ),
    Guide(
        slug="pets",
        title="Pet supplies",
        intro="Toys, grooming tools, beds and feeders for dogs and cats.",
        categories=("pet-supplies",),
    ),
    Guide(
        slug="sports-outdoors",
        title="Sports and outdoor gear",
        intro="Fitness, camping and outdoor listings ranked by review-weighted rating.",
        categories=("sports-outdoor",),
    ),
    Guide(
        slug="accessories",
        title="Fashion accessories",
        intro="Bags, hats, hair accessories and small wearables with strong reviews.",
        categories=("fashion-accessories",),
    ),
    Guide(
        slug="tools",
        title="Tools and hardware",
        intro="Hand tools, organizers and workshop gear that buyers rate highly.",
        categories=("tools-hardware",),
    ),
    Guide(
        slug="books",
        title="Books",
        intro="Books with the strongest buyer ratings, from picture books to hobby handbooks.",
        categories=("books-magazines-audio",),
    ),
)


def score(product: dict) -> float:
    reviews = product["reviews"]
    return (reviews * product["rating"] + PRIOR_WEIGHT * PRIOR_RATING) / (reviews + PRIOR_WEIGHT)


def eligible(product: dict) -> bool:
    return (
        product["rating"] is not None
        and product["rating"] >= MIN_RATING
        and product["reviews"] >= MIN_REVIEWS
        and product["subcategory"] not in EXCLUDED_SUBCATEGORIES
        and not EXCLUDED_TERMS.search(product["title"])
    )


def select(guide: Guide, products: list[dict]) -> list[dict]:
    picks = [
        p
        for p in products
        if p["rating"] >= guide.min_rating
        and p["reviews"] >= guide.min_reviews
        and (not guide.categories or p["category"] in guide.categories)
        and (guide.max_price is None or p["price"] <= guide.max_price)
    ]
    if guide.by_sold:
        picks.sort(key=lambda p: (p["sold"], score(p)), reverse=True)
    else:
        picks.sort(key=lambda p: (score(p), p["sold"]), reverse=True)
    return picks[: guide.limit]


def short_title(title: str) -> str:
    """Listing titles are keyword lists; keep the leading product name."""
    title = PROMO_TAG.sub("", title).strip()
    head = re.split(r"\s[-–—|]\s|,\s|:\s|\s\(", title, maxsplit=1)[0].strip()
    if len(head) < 18:
        head = title
    if len(head) > 80:
        head = head[:80].rsplit(" ", 1)[0] + "…"
    return head


def compact(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M".replace(".0M", "M")
    if count >= 1_000:
        return f"{count / 1_000:.1f}K".replace(".0K", "K")
    return str(count)


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def pick_item(product: dict, category_names: dict[str, str]) -> str:
    category = category_names.get(product["subcategory"] or product["category"], "")
    meta = " · ".join(escape(part) for part in (product["shop"], category) if part)
    price = ("from " if product["price_from"] else "") + money(product["price"])
    was = ""
    if product["list_price"] and product["list_price"] > product["price"]:
        was = f"<s>{money(product['list_price'])}</s>"
    return f"""<li class="pick">
<div>
<h3 title="{escape(product['title'])}">{escape(short_title(product['title']))}</h3>
<p class="meta">{meta}</p>
<p class="stats"><span class="stars">★ {product['rating']:.1f}</span> · {product['reviews']:,} reviews · {compact(product['sold'])} sold</p>
</div>
<div class="buy">
<span class="price">{price}{was}</span>
<a class="button" href="{escape(product['url'])}" rel="sponsored nofollow noopener" target="_blank">View on TikTok Shop</a>
</div>
</li>"""


def page(title: str, description: str, path: str, body: str) -> str:
    canonical = f"{SITE_URL}{path}"
    full_title = f"{title} | {SITE_NAME}" if title != SITE_NAME else title
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(full_title)}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{canonical}">
<link rel="stylesheet" href="{BASE}/style.css">
</head>
<body>
<header class="site-header">
<div class="wrap">
<a class="wordmark" href="{BASE}/">Hype<span>Check</span></a>
<nav>
<a href="{BASE}/#guides">Guides</a>
<a href="{BASE}/about/">How we pick</a>
<a href="{BASE}/disclosure/">Affiliate disclosure</a>
</nav>
</div>
</header>
<main>
<div class="wrap">
{body}
</div>
</main>
<footer class="site-footer">
<div class="wrap">
<p>{SITE_NAME} is independent. It is not affiliated with, endorsed by or sponsored by TikTok. TikTok and TikTok Shop are trademarks of their owner.</p>
<p>Some links are affiliate links: we may earn a commission if you buy through them, at no extra cost to you. <a href="{BASE}/disclosure/">Disclosure</a> · <a href="{BASE}/privacy/">Privacy</a> · <a href="{BASE}/about/">How we pick</a> · <a href="{REPO_URL}/issues">Contact</a></p>
</div>
</footer>
</body>
</html>
"""


def write(path: str, html: str) -> None:
    target = OUT / path.strip("/") / "index.html" if path != "/" else OUT / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html)


def main() -> None:
    data = json.loads((ROOT / "data" / "products.json").read_text())
    category_names = data["category_names"]
    checked = datetime.fromisoformat(data["fetched_at"])
    checked_text = f"{checked:%B} {checked.day}, {checked.year}"
    products = [p for p in data["products"] if eligible(p)]

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / ".nojekyll").write_text("")
    shutil.copy(ROOT / "static" / "style.css", OUT / "style.css")

    freshness = (
        f'<p class="note">Affiliate disclosure: we may earn a commission if you buy through links '
        f"on this page. Prices, ratings and sold counts were checked on {checked_text} and change "
        f"often; the listing always has the current numbers.</p>"
    )

    pages = ["/", "/about/", "/disclosure/", "/privacy/"]
    guide_cards = []
    for guide in GUIDES:
        picks = select(guide, products)
        if len(picks) < 5:
            continue
        path = f"/guides/{guide.slug}/"
        pages.append(path)
        low = min(p["price"] for p in picks)
        guide_cards.append(
            f'<li><a class="guide-card" href="{BASE}{path}"><strong>{escape(guide.title)}</strong>'
            f"<small>{len(picks)} picks · from {money(low)}</small></a></li>"
        )
        items = "\n".join(pick_item(p, category_names) for p in picks)
        write(
            path,
            page(
                guide.title,
                guide.intro,
                path,
                f"<h1>{escape(guide.title)}</h1>\n<p class=\"lede\">{escape(guide.intro)}</p>\n"
                f"{freshness}\n<ol class=\"picks\">\n{items}\n</ol>\n"
                f'<p class="note">How the ranking works: <a href="{BASE}/about/">How we pick</a>.</p>',
            ),
        )

    top = sorted(products, key=lambda p: (score(p), p["sold"]), reverse=True)[:10]
    top_items = "\n".join(pick_item(p, category_names) for p in top)
    home_description = (
        "TikTok Shop finds filtered by the reviews: products ranked by public rating, "
        "review count and units sold, with price caps for gift budgets."
    )
    write(
        "/",
        page(
            SITE_NAME,
            home_description,
            "/",
            f"""<h1>TikTok Shop finds, filtered by the reviews</h1>
<p class="lede">Viral is not the same as good. {SITE_NAME} ranks TikTok Shop products by what buyers said after the box arrived: star rating weighted by how many people left a review.</p>
<p class="lede">{len(products):,} listings currently clear the bar of {MIN_RATING} stars from at least {MIN_REVIEWS} reviews.</p>
{freshness}
<h2 id="guides">Guides</h2>
<ul class="guide-grid">
{chr(10).join(guide_cards)}
</ul>
<h2>Highest rated right now</h2>
<ol class="picks">
{top_items}
</ol>""",
        ),
    )

    write(
        "/about/",
        page(
            "How we pick",
            f"How {SITE_NAME} ranks TikTok Shop products: public review data, minimum thresholds and a review-weighted rating.",
            "/about/",
            f"""<div class="prose">
<h1>How we pick</h1>
<p class="lede">{SITE_NAME} is an independent list of TikTok Shop US products, ranked only by public review data.</p>
<h2>Where the numbers come from</h2>
<p>Price, star rating, review count, units sold and seller name are read from TikTok Shop's public category pages. They are TikTok Shop's own numbers, not ours. The date they were last checked is shown on every page.</p>
<h2>The bar a product has to clear</h2>
<p>A listing needs at least {MIN_REVIEWS} buyer reviews and a {MIN_RATING}-star average before it can appear anywhere on this site. Individual guides raise that bar or add a price cap, and say so at the top.</p>
<h2>How the ranking works</h2>
<p>Products are ordered by a review-weighted rating. Each listing's average is blended with a neutral {PRIOR_RATING}-star baseline worth {PRIOR_WEIGHT} reviews, so a 5.0 from 30 buyers does not outrank a 4.9 from 2,000. Ties go to the listing with more units sold. The one exception is the most-bought guide, which sorts by units sold.</p>
<h2>What this site does not do</h2>
<ul>
<li>We do not buy or test the products. This is a filter over public feedback, not a hands-on review.</li>
<li>Commission never changes a rank. See the <a href="{BASE}/disclosure/">affiliate disclosure</a>.</li>
<li>We leave out food, supplements and remedies for people or pets, where reviews can't verify the claims, along with weapons, alcohol-themed and adult items, and chance-based "break" sales.</li>
<li>Prices and stock change quickly. The TikTok Shop listing is always the source of truth.</li>
</ul>
<h2>Contact</h2>
<p>Corrections and questions: <a href="{REPO_URL}/issues">open an issue on GitHub</a>. The code that builds this site is public in the same repository.</p>
</div>""",
        ),
    )

    write(
        "/disclosure/",
        page(
            "Affiliate disclosure",
            f"{SITE_NAME} may earn a commission when you buy through links on this site.",
            "/disclosure/",
            f"""<div class="prose">
<h1>Affiliate disclosure</h1>
<p class="lede">Some links on this site are affiliate links. If you click one and buy, {SITE_NAME} may earn a commission from the seller. You pay the same price either way.</p>
<p>Commission does not decide what appears here or in what order. Rank comes only from the public review data described on <a href="{BASE}/about/">How we pick</a>, and that page applies to every product whether or not its link earns anything.</p>
<p>Product links are marked <code>rel="sponsored"</code> so search engines treat them as commercial links.</p>
<p>{SITE_NAME} is not affiliated with, endorsed by or sponsored by TikTok.</p>
</div>""",
        ),
    )

    write(
        "/privacy/",
        page(
            "Privacy",
            f"{SITE_NAME} sets no cookies and runs no analytics or advertising scripts.",
            "/privacy/",
            f"""<div class="prose">
<h1>Privacy</h1>
<p class="lede">This site sets no cookies and runs no analytics, advertising or tracking scripts. It has no accounts, forms or comments, so it collects nothing from you directly.</p>
<h2>Hosting</h2>
<p>The site is served by GitHub Pages. GitHub logs visitor IP addresses for security purposes, as described in the <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub privacy statement</a>.</p>
<h2>Outbound links</h2>
<p>Product links take you to TikTok Shop. Affiliate links may pass through a tracking redirect run by an affiliate network, which records the click so a later purchase can be credited. TikTok Shop and the affiliate network apply their own privacy policies once you leave this site.</p>
<h2>Contact</h2>
<p>Questions: <a href="{REPO_URL}/issues">open an issue on GitHub</a>.</p>
</div>""",
        ),
    )

    (OUT / "404.html").write_text(
        page(
            "Page not found",
            "That page does not exist.",
            "/404.html",
            f'<h1>Page not found</h1>\n<p class="lede">That page does not exist. <a href="{BASE}/">Back to the guides</a>.</p>',
        )
    )
    lastmod = checked.date().isoformat()
    urls = "\n".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{lastmod}</lastmod></url>" for p in pages)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'
    )
    print(f"built {len(pages)} pages from {len(products)} qualifying products")


if __name__ == "__main__":
    main()
