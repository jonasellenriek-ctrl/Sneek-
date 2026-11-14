from email.message import EmailMessage
from pathlib import Path

import yaml

from sneek.main import is_good_deal, select_new
from sneek.matching import is_basketball, size_matches
from sneek.sources import google_shopping, shopify, zalando_lounge_mail

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
    d = zalando_lounge_mail.deal_from_message(m, CFG["sources"]["zalando_lounge_mail"])
    assert d and "ZZO1" in d.url and d.extra["max_pct"] == 70 and is_good_deal(d, CFG)

    m2 = EmailMessage()
    m2["Subject"] = "Bettwäsche bis zu -60%"
    m2.set_content("Kissen und Decken")
    assert zalando_lounge_mail.deal_from_message(m2, CFG["sources"]["zalando_lounge_mail"]) is None


def test_dedupe_and_price_drop():
    deals = shopify.deals_from_products(PRODUCTS, "https://s.com", CFG)
    state = {}
    assert len(select_new(deals, state)) == 1
    assert select_new(deals, state) == []          # schon gemeldet
    deals[0].price = 50
    assert len(select_new(deals, state)) == 1      # weiter gefallen -> erneut melden
