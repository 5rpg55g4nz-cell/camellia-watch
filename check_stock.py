import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

TARGET = config["departure_date"]
ADULTS = int(config["adults"])
TZ = ZoneInfo("Asia/Tokyo")

GROUPS = [
    "pill-40",
    "pill-33",
    "pill-32",
    "pill-31",
    "pill-other"
]

result = {
    "checked_at": None,
    "departure_date": TARGET,
    "departure": "博多",
    "destination": "釜山",
    "adults": ADULTS,
    "status": "unknown",
    "available": None,
    "rooms": [],
    "message": "空席未確認"
}


def integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={
                "width": 1280,
                "height": 1100
            }
        )

        page.set_default_timeout(15000)

        try:
            page.goto(
                config["url"],
                wait_until="domcontentloaded",
                timeout=60000
            )

            one_way = page.locator(
                'input[name="oufuku"][value="1"]'
            )
            one_way.check()

            route = page.locator(
                'select[name="ow"]'
            )
            route.select_option("1")

            date_field = page.locator(
                'input[name="ow_date"]'
            )
            date_field.click()

            page.locator(
                '#set_calendar dd.enable'
                f'[data-ymd="{TARGET}"]:visible'
            ).click()

            number = page.locator(
                'input[name="number"]'
            )

            if number.input_value() != str(ADULTS):
                number.fill(str(ADULTS))
                number.press("Tab")

            if not one_way.is_checked():
                raise RuntimeError("片道設定エラー")

            if route.input_value() != "1":
                raise RuntimeError("航路設定エラー")

            if date_field.input_value() != TARGET:
                raise RuntimeError("日付設定エラー")

            if number.input_value() != str(ADULTS):
                raise RuntimeError("人数設定エラー")

            page.get_by_role(
                "button",
                name="検索",
                exact=True
            ).click()

            page.wait_for_url(
                "**/idv/reservation**",
                timeout=30000
            )

            rows = page.locator(
                "table.table01 tr.plan"
            )

            rows.first.wait_for(
                state="attached"
            )

            text = page.locator("body").inner_text()

            if TARGET not in text or "博多発" not in text:
                raise RuntimeError("検索結果不一致")

            if page.locator(
                "#renumber"
            ).input_value() != str(ADULTS):
                raise RuntimeError("人数不一致")

            expected_rows = rows.count()
            checked_groups = []

            for group in GROUPS:

                tab = page.locator(
                    f"li.pill.{group} a:visible"
                )

                if tab.count() != 1:
                    print("TAB NOT FOUND:", group)
                    continue

                tab.click()

                page.locator(
                    f"li.pill.{group}.active"
                ).wait_for(state="visible")

                checked_groups.append(group)

                group_rows = page.locator(
                    f'tr.plan[data-pill="{group}"]:visible'
                )

                for row in group_rows.all():

                    info = row.evaluate("""
                        row => {
                            const rc = row.querySelector(
                                'input.room-charge'
                            );

                            return {
                                id: row.dataset.trplan,
                                name: row.querySelector(
                                    '.plan-name'
                                )?.textContent.trim(),
                                price: row.cells[3]
                                    ?.textContent.trim(),
                                availability: row.cells[4]
                                    ?.innerText.trim(),
                                people: rc?.dataset.peoplenum,
                                rooms: rc?.dataset.roomnum,
                                capacity: rc?.dataset.capa,
                                minimum: rc?.dataset.mincapa
                            };
                        }
                    """)

                    people = integer(info.get("people"))
                    rooms = integer(info.get("rooms"))
                    capacity = integer(info.get("capacity"))
                    minimum = integer(info.get("minimum"))

                    availability = (
                        info.get("availability") or ""
                    )

                    status = "unknown"
                    selected = 0

                    if "売り切れ" in availability:
                        status = "sold_out"

                    elif "ご指定の人数では" in availability:
                        status = "ineligible"

                    elif (
                        people is not None
                        and people < ADULTS
                    ):
                        status = "insufficient"

                    elif rooms == 0:
                        status = "sold_out"

                    elif (
                        minimum is not None
                        and minimum > ADULTS
                    ):
                        status = "ineligible"

                    elif (
                        capacity is not None
                        and capacity < ADULTS
                    ):
                        if (
                            rooms is not None
                            and rooms * capacity < ADULTS
                        ):
                            status = "insufficient"

                    else:

                        stock_verified = (
                            people is not None
                            and people >= ADULTS
                        ) or (
                            rooms is not None
                            and rooms >= 1
                            and capacity is not None
                            and capacity >= ADULTS
                            and minimum is not None
                            and minimum <= ADULTS
                        )

                        fields = row.locator(
                            'input.ui-spinner-input'
                            '[data-kbn="1"]:visible'
                        )

                        if (
                            stock_verified
                            and fields.count() == 1
                        ):

                            field = fields.first

                            maximum = integer(
                                field.get_attribute(
                                    "aria-valuemax"
                                )
                            ) or 0

                            initial = integer(
                                field.input_value()
                            ) or 0

                            up = field.locator(
                                "xpath=.."
                            ).locator(".ui-spinner-up")

                            down = field.locator(
                                "xpath=.."
                            ).locator(".ui-spinner-down")

                            if (
                                maximum >= ADULTS
                                and initial == 0
                                and field.is_enabled()
                            ):

                                try:
                                    for _ in range(ADULTS):
                                        up.click(timeout=3000)

                                    selected = integer(
                                        field.input_value()
                                    ) or 0

                                    if selected == ADULTS:
                                        status = "candidate"

                                except Exception as e:
                                    print(
                                        "SELECTION ERROR:", e
                                    )

                                finally:
                                    for _ in range(ADULTS):

                                        current = integer(
                                            field.input_value()
                                        ) or 0

                                        if current <= initial:
                                            break

                                        down.click(
                                            timeout=3000
                                        )

                                    if (
                                        integer(
                                            field.input_value()
                                        ) or 0
                                    ) != initial:
                                        raise RuntimeError(
                                            "人数リセット失敗"
                                        )

                    room = {
                        "id": info.get("id"),
                        "name": info.get("name"),
                        "room": info.get("name"),
                        "price": info.get("price"),
                        "group": group,
                        "status": status,
                        "selected": selected,
                        "remaining": (
                            people if people is not None
                            else rooms
                        ),
                        "remaining_unit": (
                            "people"
                            if people is not None
                            else "rooms"
                        ),
                        "capacity": capacity
                    }

                    result["rooms"].append(room)

                    print(json.dumps(
                        room,
                        ensure_ascii=False
                    ))

            candidates = [
                room for room in result["rooms"]
                if room["status"] == "candidate"
            ]

            complete = (
                len(checked_groups) == len(GROUPS)
                and len(result["rooms"]) == expected_rows
            )

            if candidates:
                result["status"] = "candidate"
                result["available"] = None
                result["message"] = (
                    "残席あり・大人2名の選択成功。"
                    "最終予約可否は未確認"
                )

            elif (
                complete
                and result["rooms"]
                and all(
                    room["status"] in (
                        "sold_out",
                        "ineligible",
                        "insufficient"
                    )
                    for room in result["rooms"]
                )
            ):
                result["status"] = "sold_out"
                result["available"] = False
                result["message"] = (
                    "大人2名で予約可能なプランなし"
                )

            else:
                result["status"] = "unknown"
                result["message"] = (
                    "空席状況を完全には確認できません"
                )

        finally:
            try:
                page.screenshot(
                    path="booking-page.png",
                    full_page=True
                )
            except Exception:
                pass

            browser.close()

except Exception as e:
    result["status"] = "error"
    result["available"] = None
    result["message"] = str(e)
    traceback.print_exc()

finally:
    result["checked_at"] = datetime.now(
        TZ
    ).isoformat()

    with open(
        "stock.json", "w", encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))

if result["status"] == "error":
    raise SystemExit(1)
