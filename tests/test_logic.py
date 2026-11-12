from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.inventory import Facility, PricingRuleIn, SeasonalConfig, UnitCreate
from app.services.pricing import quote_stay


def rule(weekday="100", weekend="150", seasonal=None):
    cfg = SeasonalConfig.model_validate(seasonal or {})
    return SimpleNamespace(weekday_price=Decimal(weekday), weekend_price=Decimal(weekend), currency="USD",
                           seasonal_price_json=cfg.model_dump(mode="json"))


def test_weekday_weekend_split():
    # Thu 2026-11-12 (weekday), Fri 13, Sat 14 (weekend nights), Sun 15 out
    q = quote_stay(rule(), date(2026, 11, 12), date(2026, 11, 15))
    assert [n.day_type for n in q.nights] == ["WEEKDAY", "WEEKEND", "WEEKEND"]
    assert q.total == Decimal("400.00")


def test_holiday_percent_and_flat_stack():
    s = {"rules": [
        {"name": "Xmas", "category": "HOLIDAY", "start_date": "2026-12-24", "end_date": "2026-12-26",
         "kind": "SURCHARGE_PERCENT", "value": "25"},
        {"name": "Fee", "start_date": "2026-12-25", "end_date": "2026-12-25", "kind": "SURCHARGE_FLAT", "value": "10"}]}
    q = quote_stay(rule(seasonal=s), date(2026, 12, 24), date(2026, 12, 26))   # Thu, Fri
    assert q.nights[0].price == Decimal("125.00")
    assert q.nights[1].price == Decimal("197.50")   # 150*1.25 + 10


def test_override_highest_priority_wins():
    s = {"rules": [
        {"name": "low", "start_date": "2026-11-12", "end_date": "2026-11-12", "kind": "OVERRIDE", "value": "300", "priority": 1},
        {"name": "high", "start_date": "2026-11-12", "end_date": "2026-11-12", "kind": "OVERRIDE", "value": "500", "priority": 9}]}
    assert quote_stay(rule(seasonal=s), date(2026, 11, 12), date(2026, 11, 13)).total == Decimal("500.00")


def test_invalid_stay():
    with pytest.raises(Exception):
        quote_stay(rule(), date(2026, 11, 12), date(2026, 11, 12))


@pytest.mark.parametrize("data", [
    {"name": "AC", "icon": "javascript:alert(1)", "type": "svg"},
    {"name": "AC", "icon": "http://x.com/a.svg", "type": "svg"},
    {"name": "AC", "icon": "Wind!", "type": "lucide"}])
def test_bad_icons_rejected(data):
    with pytest.raises(ValidationError):
        Facility(**data)


def test_good_icons_and_duplicates():
    Facility(name="A", icon="https://cdn.x.com/a.svg", type="svg")
    Facility(name="B", icon="fa-solid fa-wind", type="fontawesome")
    with pytest.raises(ValidationError):
        UnitCreate(unit_name="x", type="ROOM", facilities=[
            {"name": "AC", "icon": "wind"}, {"name": "ac", "icon": "wind"}])


def test_referral_cookie_roundtrip_and_tamper():
    from app.core.security import open_referral, seal_referral
    tok = seal_referral("t1", "p1")
    assert open_referral(tok, 100) == {"t": "t1", "p": "p1"}
    assert open_referral(tok[:-4] + "AAAA", 100) is None
    assert open_referral("garbage", 100) is None


def test_hold_key_parse():
    from uuid import uuid4
    from app.services.holds import hold_key, parse_hold_key
    t, b = uuid4(), uuid4()
    assert parse_hold_key(hold_key(t, b)) == (t, b)
    assert parse_hold_key("other:x:y") is None


def test_app_boots_and_docs_generate():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.api_docs import build_module_docs
    paths = app.openapi()["paths"]
    assert "/api/v1/bookings/hold" in paths and "/go/{vanity_code}" in paths
    d = build_module_docs(app, "bookings", "http://x")
    hold = next(e for e in d.endpoints if e.path == "/api/v1/bookings/hold")
    assert "bookings:create" in hold.required_scopes
    assert "curl" in hold.snippets and "X-API-KEY" in hold.snippets["curl"]
    assert TestClient(app).get("/api/v1/properties").status_code == 401   # middleware guard
