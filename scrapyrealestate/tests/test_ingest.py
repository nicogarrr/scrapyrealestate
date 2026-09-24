from scrapyrealestate.ingest import listing_key, numeric_price


def test_numeric_price_handles_spanish_price_text():
    assert numeric_price("99.999 €") == 99999
    assert numeric_price("100.000,50 €") == 100000
    assert numeric_price(75000) == 75000
    assert numeric_price("A consultar") is None


def test_listing_key_is_scoped_by_source():
    assert listing_key({"site": "fotocasa", "id": "123"}) == "fotocasa:123"
    assert listing_key({"site": "pisoscom", "id": "123"}) == "pisoscom:123"
    assert listing_key({"site": "fotocasa", "id": "123"}) != listing_key(
        {"site": "pisoscom", "id": "123"}
    )


def test_listing_key_falls_back_to_normalized_href():
    key = listing_key({"site": "habitaclia", "id": "", "href": "/inmueble/abc/?x=1"})
    assert key == listing_key({"site": "habitaclia", "id": "", "href": "/inmueble/abc/?x=2"})
    assert key.startswith("habitaclia:")
