from email.message import EmailMessage
from pathlib import Path

import yaml

from sneek.main import is_good_deal, select_new
from sneek.notify import build_report
from sneek.matching import is_basketball, size_matches
from sneek.sources import google_shopping, newsletter_mail, shopify

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())
A = CFG["size_aliases"]


def test_size_matching():
    for ok in ["16", "US 16", "M 16 / W 17.5", "Black / 16", "EU 50.5", "50,5", "UK 15", "51 1/3", "US16"]:
        assert size_matches(ok, A), ok
    for bad in ["16.5", "15", "116", "EU 16", "6", "50", "51 2/3", "UK 15 1/2 ", "16cm", "US 15.5"]:
        assert not size_matches(bad, A), bad


def test_basketball_detection():
    kw, ex = CFG["basketball_keywords"], CFG["exclude_keywords"]
    assert is_basketball("Nike LeBron XXII", kw, ex)
    assert is_basketball("Puma MB.04 Sneaker", kw, ex)
    assert is_basketball("Running Shoe basketball", kw, ex)
    assert not is_basketball("Nike LeBron XXII (GS)", kw, ex)
    assert not is_basketball("Spalding Basketball Ball", kw, ex)
    assert not is_basketball("Air Jordan Hoodie", kw, ex)
    assert not is_basketball("Nike Pegasus 41", kw, ex)


PRODUCTS = [
    {   # gut: reduziert, Größe 16 verfügbar
        "title": "Nike Sabrina 2", "handle": "sabrina-2", "product_type": "Footwear", "tags": [],
        "options": [{"name": "Color"}, {"name": "Size"}],
        "variants": [
            {"id": 1, "option1": "Black", "option2": "15", "available": True, "price": "60.00", "compare_at_price": "130.00"},
            {"id": 2, "option1": "Black", "option2": "16", "available": True, "price": "60.00", "compare_at_price": "130.00"},
            {"id": 3, "option1": "Black", "option2": "16.5", "available": True, "price": "60.00", "compare_at_price": "130.00"},
        ],
    },
    {   # Größe 16 ausverkauft
        "title": "Adidas AE 1", "handle": "ae1", "tags": ["basketball"], "options": ["Size"],
        "variants": [{"id": 4, "option1": "16", "available": False, "price": "50", "compare_at_price": "120"}],
    },
    {   # kein Basketballschuh
        "title": "Nike Pegasus", "handle": "peg", "tags": [], "options": ["Size"],
        "variants": [{"id": 5, "option1": "16", "available": True, "price": "50", "compare_at_price": "140"}],
    },
]


def test_shopify_parsing():
    deals = shopify.deals_from_products(PRODUCTS, "https://www.example-shop.com", CFG)
    assert len(deals) == 1
    d = deals[0]
    assert d.size == "16" and d.price == 60 and d.discount_percent == 53.8
    assert d.url == "https://www.example-shop.com/products/sabrina-2?variant=2"
    assert d.source == "shopify:example-shop.com"
    assert is_good_deal(d, CFG)


def test_google_parsing_and_filter():
    res = [
        {"title": "Nike GT Cut 3", "source": "Zalando", "extracted_price": 70, "extracted_old_price": 180, "product_link": "u1"},
        {"title": "Nike GT Cut 3", "source": "Snipes", "extracted_price": 150, "extracted_old_price": 180, "product_link": "u2"},
        {"title": "Nike GT Cut 3", "source": "Kickz", "extracted_price": 150, "product_link": "u3"},
    ]
    deals = [d for d in google_shopping.deals_from_results(res, CFG) if is_good_deal(d, CFG)]
    assert [d.url for d in deals] == ["u1"]


def test_lounge_mail():
    m = EmailMessage()
    m["Subject"] = "Nike Basketball – bis zu -70%"
    m["From"] = "news@zalando-lounge.de"
    m["Message-ID"] = "<abc@x>"
    m.set_content('Jetzt shoppen: <a href="https://www.zalando-lounge.de/campaigns/ZZO1">hier</a> bis zu -70 %')
    mcfg = CFG["sources"]["newsletter_mail"]
    lounge, best = mcfg["clubs"]
    d = newsletter_mail.deal_from_message(m, lounge, mcfg["keywords"])
    assert d and "ZZO1" in d.url and d.extra["max_pct"] == 70 and is_good_deal(d, CFG)

    m2 = EmailMessage()
    m2["Subject"] = "Bettwäsche bis zu -60%"
    m2.set_content("Kissen und Decken")
    assert newsletter_mail.deal_from_message(m2, lounge, mcfg["keywords"]) is None

    m3 = EmailMessage()
    m3["Subject"] = "Neu: Jordan & adidas Sneaker"
    m3.set_content('<a href="https://www.bestsecret.com/campaign/123">Zur Aktion</a> -60%')
    d3 = newsletter_mail.deal_from_message(m3, best, mcfg["keywords"])
    assert d3 and d3.url.endswith("/campaign/123") and d3.source.startswith("BestSecret")


def test_dedupe_and_price_drop():
    deals = shopify.deals_from_products(PRODUCTS, "https://s.com", CFG)
    state = {}
    assert len(select_new(deals, state)) == 1
    assert select_new(deals, state) == []          # schon gemeldet
    deals[0].price = 50
    assert len(select_new(deals, state)) == 1      # weiter gefallen -> erneut melden


def test_report():
    deals = shopify.deals_from_products(PRODUCTS, "https://s.com", CFG)
    subject, html = build_report(deals, deals, ["x.com: HTTP 403"], CFG)
    assert "1 neue" in subject and "Nike Sabrina 2" in html and "NEU" in html and "x.com" in html
    subject, html = build_report([], [], [], CFG)
    assert "keine Deals" in subject


def test_rating_and_focus():
    from sneek.models import Deal
    from sneek.rating import rate
    kobe = Deal("google:Nike", "Nike Kobe 6 Protro", "https://www.nike.com/x", 90, 190, "€")
    meh = Deal("google:randomshop", "Some Hoop Shoe", "https://random.example/x", 150, 250, "€")
    rk, rm = rate(kobe), rate(meh)
    assert rk["modell"] == 10 and rk["gesamt"] > rm["gesamt"]
    assert all(1 <= v <= 10 for v in rk.values())
    cfg = dict(CFG)
    kobe.extra["focus"] = True          # 52 % -> ok; 25 % Kobe auch ok (Schwelle 20)
    kobe.price = 142
    assert is_good_deal(kobe, cfg)
    subject, html = build_report([kobe], [kobe], [], cfg)
    assert "Kobe" in subject and "Kobe-Radar" in html and "nike.com" in html


def test_direct_link():
    from sneek.sources.google_shopping import direct_link
    assert direct_link({"link": "https://www.zalando.de/p1", "product_link": "https://www.google.com/shopping/product/1"}) == "https://www.zalando.de/p1"
    assert direct_link({"link": "https://www.google.com/url?url=https://www.snipes.com/p2&sa=x"}) == "https://www.snipes.com/p2"
    assert direct_link({"product_link": "https://www.google.com/shopping/product/1"}).startswith("https://www.google.com")


def test_store_link():
    from sneek.sources.google_shopping import store_link
    data = {"product_results": {"stores": [
        {"name": "Google", "link": "https://www.google.com/x"},
        {"name": "eBay", "link": "https://www.ebay.de/itm/1"},
        {"name": "Basket4Ballers", "link": "https://www.basket4ballers.com/de/kobe"},
    ]}}
    assert store_link(data, "Basket4Ballers") == "https://www.basket4ballers.com/de/kobe"
    assert store_link(data, "Unbekannt") == "https://www.ebay.de/itm/1"
    assert store_link({}, "x") == ""


class _Resp:
    def __init__(self, ok=True, js=None, text="", status=200):
        self.ok, self._js, self.text, self.status_code = ok, js, text, status

    def json(self):
        if self._js is None:
            raise ValueError
        return self._js


def test_verify_shopify(monkeypatch):
    from sneek import verify
    from sneek.models import Deal
    js = {"variants": [
        {"option1": "15", "available": True, "price": 5000, "compare_at_price": 18000},
        {"option1": "16", "available": True, "price": 9900, "compare_at_price": 18000},
    ]}
    monkeypatch.setattr(verify.requests, "get", lambda url, **k: _Resp(js=js) if url.endswith(".js") else _Resp(False))
    d = Deal("google:Shop", "Nike Kobe 6", "https://shop.example/products/kobe-6?variant=1", 50, 180)
    r = verify.verify(d, A)
    assert (r.status, r.price, r.old_price) == ("ok", 99.0, 180.0)   # nicht 50 € der Größe 15!
    js["variants"][1]["available"] = False
    assert verify.verify(d, A).status == "sold_out"


def test_verify_jsonld(monkeypatch):
    import json as _j
    from sneek import verify
    from sneek.models import Deal
    ld = {"@type": "ProductGroup", "name": "Nike LeBron 16", "hasVariant": [
        {"@type": "Product", "size": "EU 45", "offers": {"price": "59.99", "availability": "https://schema.org/InStock"}},
        {"@type": "Product", "size": "EU 47.5", "offers": {"price": "59.99", "availability": "https://schema.org/InStock"}},
        {"@type": "Product", "size": "EU 49.5", "offers": {"price": "64.99", "availability": "https://schema.org/InStock"}},
        {"@type": "Product", "size": "EU 50.5", "offers": {"price": "89.99", "availability": "https://schema.org/InStock"}},
    ]}
    html = f'<script type="application/ld+json">{_j.dumps(ld)}</script>'
    monkeypatch.setattr(verify.requests, "get", lambda url, **k: _Resp(False) if url.endswith(".js") else _Resp(text=html))
    d = Deal("google:Shop", "Nike LeBron 16", "https://shop.example/lebron-16.html", 59.99, 160)
    r = verify.verify(d, A)
    assert (r.status, r.price) == ("ok", 89.99)
    ld["hasVariant"][3]["offers"]["availability"] = "https://schema.org/OutOfStock"
    html2 = f'<script type="application/ld+json">{_j.dumps(ld)}</script>'
    monkeypatch.setattr(verify.requests, "get", lambda url, **k: _Resp(False) if url.endswith(".js") else _Resp(text=html2))
    assert verify.verify(d, A).status == "sold_out"


def test_resellers_flagged():
    from sneek.models import Deal
    from sneek.verify import is_reseller
    assert is_reseller(Deal("google:GOAT", "x", "https://www.google.com/x"))
    assert is_reseller(Deal("google:Lyst.com DE", "x", "https://www.google.com/x"))
    assert not is_reseller(Deal("google:BSTN Store", "x", "https://www.bstn.com/x"))


def test_stockx_exact_size():
    from sneek.sources import marketplaces as mp
    def var(size, amounts, base="us m"):
        return {"traits": {"size": size}, "sizeChart": {"baseType": base},
                "market": {"priceLevels": {"edges": [{"node": {"amount": str(a)}} for a in amounts]}}}
    search = {"data": {"browse": {"results": {"edges": [
        {"node": {"title": "Nike Kobe 6 Protro Sail All-Star", "urlKey": "nike-kobe-6-protro-sail",
                  "variants": [var("15", []), var("16", [])]}},
        {"node": {"title": "Nike Kobe 6 Protro Kids", "urlKey": "x", "variants": [var("5", [])]}}]}}}}
    nodes = mp.products_from_search(search)
    assert [mp.has_size(n, "16") for n in nodes] == [True, False]
    asks = {"data": {"product": {"variants": [var("15", [499, 520]), var("16", [460, 450]), var("16", [90], "us w")]}}}
    price, others = mp.size_prices(asks, "16")
    assert price == 450 and others == [499, 90]   # US-W-16 zählt nicht als US 16
