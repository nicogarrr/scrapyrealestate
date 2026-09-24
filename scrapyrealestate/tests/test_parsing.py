import pytest

from scrapyrealestate.parsing import (
    append_url_fragment,
    extract_fotocasa_items,
    extract_listing_id,
    format_price,
    has_elevator_filter,
)


def test_extract_listing_id_prefers_current_pisos_id():
    href = "/comprar/piso-aranjuez_centro-65098413759.100200/"
    assert extract_listing_id("pisoscom", href) == "65098413759.100200"


def test_extract_listing_id_prefers_current_pisos_underscore_id():
    href = "/comprar/piso-ablanedo_riosa-50016420678_500957/"
    assert extract_listing_id("pisoscom", href) == "50016420678_500957"


def test_extract_listing_id_handles_absolute_pisos_url():
    href = "https://www.pisos.com/comprar/piso-jove-65874948488_106100/"
    assert extract_listing_id("pisoscom", href) == "65874948488_106100"


def test_extract_listing_id_uses_numeric_fotocasa_id():
    assert extract_listing_id("fotocasa", "https://www.fotocasa.es/es/comprar/vivienda/x/189937271/d") == "189937271"


def test_extract_listing_id_falls_back_to_stable_url_digest():
    href = "/comprar/casa_foo/"
    first = extract_listing_id("habitaclia", href)
    second = extract_listing_id("habitaclia", href)
    assert first == second
    assert first.startswith("habitaclia:")


def test_fotocasa_prefers_results_v2_items():
    payload = {
        "initialSearch": {
            "result": {
                "realEstates": [{"propertyId": 1}],
                "resultsV2": {"items": [{"propertyId": 2}, {"propertyId": 3}]},
            }
        }
    }
    assert [item["propertyId"] for item in extract_fotocasa_items(payload)] == [2, 3]


def test_fotocasa_falls_back_to_legacy_real_estates():
    payload = {"initialSearch": {"result": {"realEstates": [{"propertyId": 4}]}}}
    assert [item["propertyId"] for item in extract_fotocasa_items(payload)] == [4]


def test_format_price_does_not_append_monthly_suffix_to_sale():
    assert format_price("99.999 €", "buy") == "99.999 €"
    assert format_price("99.999 €", "rent") == "99.999 €/mes"


def test_elevator_filter_is_detected_in_url():
    assert has_elevator_filter("/ascensor/hasta-100000")
    assert has_elevator_filter("?feature=ascensor")
    assert not has_elevator_filter("todas-las-zonas")


@pytest.mark.parametrize(
    ("url", "fragment", "expected"),
    [
        ("https://example.test/path", "foo", "https://example.test/path/foo"),
        ("https://example.test/path/", "foo", "https://example.test/path/foo"),
        ("https://example.test/path?a=1", "foo", "https://example.test/path?a=1&foo"),
    ],
)
def test_append_url_fragment_preserves_existing_query(url, fragment, expected):
    assert append_url_fragment(url, fragment) == expected
