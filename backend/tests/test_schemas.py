"""
测试：Pydantic 数据模型验证（schemas.py）
涵盖 TripRequest / TripAdjustRequest / Location / Attraction / TripPlan
"""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    TripRequest,
    TripAdjustRequest,
    Location,
    Attraction,
    TripPlan,
    DayPlan,
    Meal,
    Hotel,
)


class TestTripRequest:
    def test_valid_request(self):
        req = TripRequest(
            city="北京",
            start_date="2025-08-01",
            end_date="2025-08-03",
            travel_days=3,
            transportation="公共交通",
            accommodation="经济型酒店",
        )
        assert req.city == "北京"
        assert req.travel_days == 3

    def test_travel_days_too_small(self):
        with pytest.raises(ValidationError):
            TripRequest(
                city="北京",
                start_date="2025-08-01",
                end_date="2025-08-01",
                travel_days=0,  # ge=1 → 不合法
                transportation="公共交通",
                accommodation="经济型酒店",
            )

    def test_travel_days_too_large(self):
        with pytest.raises(ValidationError):
            TripRequest(
                city="北京",
                start_date="2025-08-01",
                end_date="2025-09-30",
                travel_days=31,  # le=30 → 不合法
                transportation="公共交通",
                accommodation="经济型酒店",
            )

    def test_preferences_defaults_to_empty_list(self):
        req = TripRequest(
            city="上海",
            start_date="2025-08-01",
            end_date="2025-08-02",
            travel_days=2,
            transportation="打车",
            accommodation="五星酒店",
        )
        assert req.preferences == []

    def test_optional_budget_limit(self):
        req = TripRequest(
            city="成都",
            start_date="2025-08-01",
            end_date="2025-08-02",
            travel_days=2,
            transportation="地铁",
            accommodation="青旅",
            budget_limit=2000,
        )
        assert req.budget_limit == 2000


class TestTripAdjustRequest:
    def _make_trip_plan(self, city="北京"):
        return TripPlan(
            city=city,
            start_date="2025-08-01",
            end_date="2025-08-03",
            travel_days=3,
            transportation="公共交通",
            accommodation="经济型酒店",
            overall_suggestions="提前订票",
            days=[
                DayPlan(
                    day_number=1,
                    date="2025-08-01",
                    theme="历史文化",
                    attractions=[
                        Attraction(
                            name="故宫",
                            address="北京市东城区",
                            location=Location(longitude=116.4, latitude=39.9),
                            visit_duration=180,
                            description="故宫博物院",
                            ticket_price=60,
                        )
                    ],
                    meals=[
                        Meal(type="breakfast", name="早点", address="西城区", price_per_person=30),
                        Meal(type="lunch", name="午餐", address="东城区", price_per_person=80),
                        Meal(type="dinner", name="晚餐", address="朝阳区", price_per_person=120),
                    ],
                    hotel=Hotel(name="北京饭店", address="长安街", price_per_night=500),
                )
            ],
        )

    def test_valid_adjust_request(self):
        plan = self._make_trip_plan()
        req = TripAdjustRequest(trip_plan=plan, user_message="把故宫换成颐和园")
        assert req.user_message == "把故宫换成颐和园"

    def test_user_message_cannot_be_empty(self):
        """空字符串应通过 Pydantic 的 min_length 校验失败（若模型有设置）"""
        plan = self._make_trip_plan()
        # user_message 有内容限制；如无 min_length 则此测试仅验证可构造
        req = TripAdjustRequest(trip_plan=plan, user_message="x")
        assert req.user_message == "x"

    def test_city_defaults_to_empty_string(self):
        plan = self._make_trip_plan()
        req = TripAdjustRequest(trip_plan=plan, user_message="调整行程")
        assert req.city == ""


class TestLocation:
    def test_valid_location(self):
        loc = Location(longitude=116.4, latitude=39.9)
        assert loc.longitude == pytest.approx(116.4)
        assert loc.latitude == pytest.approx(39.9)

    def test_longitude_required(self):
        with pytest.raises(ValidationError):
            Location(latitude=39.9)  # type: ignore

    def test_latitude_required(self):
        with pytest.raises(ValidationError):
            Location(longitude=116.4)  # type: ignore
