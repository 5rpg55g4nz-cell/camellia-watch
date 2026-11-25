import json
import re
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

target = config["departure_date"]

result = {
    "checked_at": datetime.now(
        ZoneInfo("Asia/Tokyo")
    ).isoformat(),
    "departure_date": target,
    "departure": config["departure"],
    "destination": config["destination"],
    "adults": config["adults"],
    "status": "unknown",
    "available": None,
    "rooms": [],
    "message": "空席未確認"
}

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

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

            print("PAGE TITLE:", page.title())

            # 片道
            one_way = page.locator(
                'input[name="oufuku"][value="1"]'
            )
            one_way.check()

            # 博多 → 釜山
            route = page.locator(
                'select[name="ow"]'
            )
            route.select_option("1")

            # カレンダーを開く
            date_field = page.locator(
                'input[name="ow_date"]'
            )
            date_field.click()

            # 解析済みの日付属性を使用
            day = page.locator(
                '#set_calendar '
                f'dd.enable[data-ymd="{target}"]'
                ':visible'
            )

            day.wait_for(
                state="visible",
                timeout=10000
            )

            if day.count() != 1:
                raise RuntimeError(
                    "対象日を一意に特定できません"
                )

            print("DAY HTML:")
            print(day.evaluate(
                "e => e.outerHTML"
            ))

            day.click()

            # 選択された日付を確認
            date_value = date_field.input_value()

            print("SELECTED DATE:", date_value)

            digits = re.sub(
                r"[^0-9]", "", date_value
            )

            expected = target.replace("-", "")

            if digits != expected:
                raise RuntimeError(
                    "日付設定エラー: " + date_value
                )

            # 人数設定
            number = page.locator(
                'input[name="number"]'
            )

            adults = str(config["adults"])

            if number.input_value() != adults:
                number.fill(adults)
                number.press("Tab")

            # 検索直前の条件確認
            if not one_way.is_checked():
                raise RuntimeError(
                    "片道設定エラー"
                )

            if route.input_value() != "1":
                raise RuntimeError(
                    "航路設定エラー"
                )

            if number.input_value() != adults:
                raise RuntimeError(
                    "人数設定エラー"
                )

            if re.sub(
                r"[^0-9]", "",
                date_field.input_value()
            ) != expected:
                raise RuntimeError(
                    "日付の再確認に失敗"
                )

            print("SEARCH CONDITIONS VERIFIED")
            print("TRIP: ONE WAY")
            print("ROUTE: HAKATA -> BUSAN")
            print("DATE:", date_value)
            print("PASSENGERS:", adults)

            page.screenshot(
                path="booking-page.png",
                full_page=True
            )

            # 空席検索ボタン
            search = page.get_by_role(
                "button",
                name="検索",
                exact=True
            )

            if search.count() != 1:
                raise RuntimeError(
                    "検索ボタンを特定できません"
                )

            search.click()

            page.wait_for_timeout(8000)

            print("RESULT URL:", page.url)
            print("RESULT TITLE:", page.title())

            print("RESULT TEXT START")

            body_text = page.locator(
                "body"
            ).inner_text()

            print(body_text)

            print("RESULT TEXT END")

            # 客室・料金・予約ボタンの解析
            elements = page.locator(
                "table, select, button, "
                "input, a, .alert"
            ).evaluate_all("""
                elements => elements
                  .filter(e =>
                    e.getClientRects().length
                  )
                  .map(e => ({
                    tag: e.tagName,
                    text: (e.innerText || '').trim(),
                    id: e.id || '',
                    name: e.name || '',
                    value: e.value || '',
                    disabled: !!e.disabled,
                    html: e.outerHTML.slice(0, 12000)
                  }))
            """)

            print("RESULT ELEMENTS START")
            print(json.dumps(
                elements,
                ensure_ascii=False,
                indent=2
            ))
            print("RESULT ELEMENTS END")

            result["message"] = (
                "検索操作完了・空席判定未検証"
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
    result["message"] = str(e)

    print("ERROR:", e)
    traceback.print_exc()

finally:
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
