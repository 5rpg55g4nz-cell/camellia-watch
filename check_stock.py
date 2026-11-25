import json
import os
import re
import traceback
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

target = config["departure_date"]
adults = int(config["adults"])
timezone = ZoneInfo("Asia/Tokyo")

result = {
    "checked_at": None,
    "departure_date": target,
    "departure": config["departure"],
    "destination": config["destination"],
    "adults": adults,
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

            day = page.locator(
                '#set_calendar '
                f'dd.enable[data-ymd="{target}"]'
                ':visible'
            )
            day.wait_for(state="visible")
            day.click()

            number = page.locator(
                'input[name="number"]'
            )

            if number.input_value() != str(adults):
                number.fill(str(adults))
                number.press("Tab")

            if not one_way.is_checked():
                raise RuntimeError("片道設定エラー")

            if route.input_value() != "1":
                raise RuntimeError("航路設定エラー")

            if date_field.input_value() != target:
                raise RuntimeError("日付設定エラー")

            if number.input_value() != str(adults):
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
            rows.first.wait_for(state="attached")

            text = page.locator("body").inner_text()

            if target not in text or "博多発" not in text:
                raise RuntimeError("検索結果不一致")

            if page.locator(
                "#renumber"
            ).input_value() != str(adults):
                raise RuntimeError("検索人数不一致")

            plans = rows.evaluate_all("""
                rows => rows.map(row => {
                    const cells = Array.from(row.cells);

                    const rc = row.querySelector(
                        'input.room-charge'
                    );

                    const adult = row.querySelector(
                        'input.ui-spinner-input[data-kbn="1"]'
                    );

                    const up = adult?.parentElement
                        ?.querySelector('.ui-spinner-up');

                    return {
                        id: row.dataset.trplan || '',
                        name: row.querySelector(
                            '.plan-name'
                        )?.textContent.trim() || '',
                        room: cells[2]?.textContent.trim() || '',
                        price: cells[3]?.textContent.trim() || '',
                        availability: cells[4]?.textContent.trim() || '',
                        people: rc?.dataset.peoplenum ?? null,
                        room_count: rc?.dataset.roomnum ?? null,
                        capacity: rc?.dataset.capa ?? null,
                        min_capacity: rc?.dataset.mincapa ?? null,
                        room_charge: rc?.value ?? null,
                        max_adults: adult?.getAttribute(
                            'aria-valuemax'
                        ) ?? null,
                        enabled: !!adult && !adult.disabled &&
                            adult.getAttribute('aria-disabled') !== 'true' &&
                            !!up &&
                            !up.classList.contains('ui-state-disabled') &&
                            up.getAttribute('aria-disabled') !== 'true'
                    };
                })
            """)

            if not plans:
                raise RuntimeError("客室情報を取得できません")

            for plan in plans:
                availability = plan["availability"]

                people = integer(plan["people"])
                room_count = integer(plan["room_count"])
                capacity = integer(plan["capacity"])
                minimum = integer(plan["min_capacity"])
                max_adults = integer(plan["max_adults"])

                status = "unknown"
                remaining = None

                if "売り切れ" in availability:
                    status = "sold_out"

                elif "ご指定の人数では" in availability:
                    status = "ineligible"

                elif people is not None:
                    remaining = people

                    if people < adults:
                        status = "insufficient"

                    elif (
                        max_adults is not None
                        and max_adults >= adults
                        and plan["enabled"]
                    ):
                        status = "candidate"

                elif (
                    room_count is not None
                    and capacity is not None
                    and minimum is not None
                ):
                    remaining = room_count

                    if room_count == 0:
                        status = "sold_out"

                    elif minimum > adults:
                        status = "ineligible"

                    elif room_count * capacity < adults:
                        status = "insufficient"

                    elif (
                        capacity >= adults
                        and max_adults is not None
                        and max_adults >= adults
                        and plan["enabled"]
                    ):
                        status = "candidate"

                # 実際の人数選択操作で確認
                if status == "candidate":
                    row = rows.locator(
                        "xpath=self::*"
                    ).filter(
                        has=page.locator(
                            f'input.ui-spinner-input'
                            f'[data-plan="{plan["id"]}"]'
                            '[data-kbn="1"]'
                        )
                    )

                    if row.count() == 1 and row.is_visible():
                        field = row.locator(
                            'input.ui-spinner-input[data-kbn="1"]'
                        ).first

                        up = field.locator(
                            "xpath=.."
                        ).locator(".ui-spinner-up")

                        down = field.locator(
                            "xpath=.."
                        ).locator(".ui-spinner-down")

                        initial = integer(
                            field.input_value()
                        ) or 0

                        try:
                            if initial == 0:
                                for _ in range(adults):
                                    up.click(timeout=3000)

                                selected = integer(
                                    field.input_value()
                                )

                                if selected == adults:
                                    status = "available"

                        except Exception:
                            status = "unknown"

                        finally:
                            for _ in range(adults):
                                value = integer(
                                    field.input_value()
                                ) or 0

                                if value <= initial:
                                    break

                                down.click(timeout=3000)

                    if status == "candidate":
                        status = "unknown"

                room = {
                    "id": plan["id"],
                    "name": plan["name"],
                    "room": plan["room"],
                    "price": plan["price"],
                    "status": status,
                    "remaining": remaining,
                    "remaining_unit": (
                        "people" if people is not None
                        else "rooms"
                    ),
                    "room_charge": plan["room_charge"],
                    "capacity": capacity,
                    "min_capacity": minimum
                }

                result["rooms"].append(room)

                print(json.dumps(
                    room,
                    ensure_ascii=False
                ))

            available_rooms = [
                room for room in result["rooms"]
                if room["status"] == "available"
            ]

            expected_ids = {
                "161", "157", "162", "163",
                "164", "166", "167"
            }

            found_ids = {
                room["id"]
                for room in result["rooms"]
            }

            if available_rooms:
                result["status"] = "available"
                result["available"] = True
                result["message"] = (
                    f"大人{adults}名の人数選択を確認"
                )

            elif (
                expected_ids.issubset(found_ids)
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
                    "空席判定に追加確認が必要"
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
        timezone
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

# 本番対象の空席を確認した場合のみ通知
topic = os.environ.get("NTFY_TOPIC", "")

if (
    topic
    and target == "2026-12-27"
    and adults == 2
    and result["status"] == "available"
    and result["available"] is True
):
    lines = [
        "2026年12月27日（日）",
        "博多 → 釜山",
        "片道・大人2名",
        "",
        "予約画面で人数選択を確認しました。",
        ""
    ]

    for room in result["rooms"]:
        if room["status"] == "available":
            lines.append(room["name"])
            lines.append(
                "表示運賃：" + room["price"]
            )

    lines.extend([
        "",
        "確認時刻：",
        result["checked_at"],
        "",
        config["url"]
    ])

    response = requests.post(
        "https://ntfy.sh/" + topic,
        data="\n".join(lines).encode("utf-8"),
        headers={
            "Title": "Camellia Watch - AVAILABLE",
            "Priority": "urgent",
            "Tags": "ship,bell",
            "Click": config["url"]
        },
        timeout=20
    )

    if not response.ok:
        raise RuntimeError("通知送信エラー")

    print("NOTIFICATION SENT")

if result["status"] == "error":
    raise SystemExit(1)
