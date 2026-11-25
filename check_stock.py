import json
import re
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

target = config["departure_date"]
adults = config["adults"]
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

            page.locator(
                "table.table01 tr.plan"
            ).first.wait_for(state="attached")

            text = page.locator("body").inner_text()

            if target not in text or "博多発" not in text:
                raise RuntimeError("検索結果の日付・航路不一致")

            passenger_count = page.locator(
                "#renumber"
            ).input_value()

            if passenger_count != str(adults):
                raise RuntimeError("検索結果の人数不一致")

            # 非表示の客室プランも取得
            rows = page.locator(
                "table.table01 tr.plan"
            )

            plans = rows.evaluate_all("""
                rows => rows.map(row => {
                    const cells = Array.from(row.cells);
                    const rc = row.querySelector(
                        'input.room-charge'
                    );

                    return {
                        id: row.dataset.trplan || '',
                        name: row.querySelector(
                            '.plan-name'
                        )?.textContent.trim() || '',
                        room: cells[2]?.textContent.trim() || '',
                        price: cells[3]?.textContent.trim() || '',
                        availability: cells[4]?.textContent.trim() || '',
                        room_charge: rc?.value || '',
                        room_count: rc?.dataset.roomnum || '',
                        min_capacity: rc?.dataset.mincapa || '',
                        capacity: rc?.dataset.capa || '',
                        html: row.outerHTML
                    };
                })
            """)

            if not plans:
                raise RuntimeError("客室情報を取得できません")

            for plan in plans:
                availability = plan["availability"]

                if "売り切れ" in availability:
                    status = "sold_out"

                elif "ご指定の人数では" in availability:
                    status = "ineligible"

                else:
                    # 予約可能な画面の構造は
                    # 未検証のため推測しない
                    status = "unknown"

                room = {
                    "id": plan["id"],
                    "name": plan["name"],
                    "room": plan["room"],
                    "price": plan["price"],
                    "status": status,
                    "availability": availability,
                    "room_charge": plan["room_charge"],
                    "room_count": plan["room_count"],
                    "min_capacity": plan["min_capacity"],
                    "capacity": plan["capacity"]
                }

                result["rooms"].append(room)

                print(json.dumps(
                    room,
                    ensure_ascii=False,
                    indent=2
                ))

                if status == "unknown":
                    print("UNVERIFIED PLAN HTML:")
                    print(plan["html"])

            expected_ids = {
                "161", "157", "162", "163",
                "164", "166", "167"
            }

            found_ids = {
                room["id"]
                for room in result["rooms"]
            }

            if (
                expected_ids.issubset(found_ids)
                and all(
                    room["status"] in (
                        "sold_out", "ineligible"
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
                result["available"] = None
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

if result["status"] == "error":
    raise SystemExit(1)
