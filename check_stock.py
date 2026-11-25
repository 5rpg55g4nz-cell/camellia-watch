import json
import re
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

result = {
    "checked_at": datetime.now(
        ZoneInfo("Asia/Tokyo")
    ).isoformat(),
    "departure_date": config["departure_date"],
    "departure": config["departure"],
    "destination": config["destination"],
    "adults": config["adults"],
    "status": "unknown",
    "available": None,
    "rooms": [],
    "message": "空席未確認"
}

page = None

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
                "height": 1000
            }
        )

        page.set_default_timeout(15000)

        try:
            page.goto(
                config["url"],
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(2000)

            print("PAGE TITLE:", page.title())
            print("PAGE URL:", page.url)

            # 片道を選択
            radios = page.locator(
                'input[name="oufuku"]'
            )

            selected = False

            for radio in radios.all():
                label = radio.evaluate("""
                    e => Array.from(e.labels || [])
                        .map(l => l.innerText)
                        .join(' ')
                """)

                print(
                    "RADIO:",
                    radio.get_attribute("value"),
                    label
                )

                if "片道" in label and "往復" not in label:
                    radio.check()
                    selected = True
                    break

            if not selected:
                label = page.get_by_text(
                    "片道", exact=True
                )

                if label.count() == 1:
                    label.click()
                    checked = page.locator(
                        'input[name="oufuku"]:checked'
                    )

                    selected = checked.count() == 1

            if not selected:
                raise RuntimeError(
                    "片道選択を確認できません"
                )

            # 博多 → 釜山
            route = page.locator(
                'select[name="ow"]'
            )

            route.select_option("1")

            if route.input_value() != "1":
                raise RuntimeError(
                    "航路選択エラー"
                )

            print("ROUTE: HAKATA -> BUSAN")

            # 出発日
            date_field = page.locator(
                'input[name="ow_date"]'
            )

            date = datetime.strptime(
                config["departure_date"],
                "%Y-%m-%d"
            )

            if date_field.is_editable():
                date_field.fill(
                    date.strftime("%Y/%m/%d")
                )
                date_field.press("Tab")
            else:
                applied = date_field.evaluate(
                    """(e, d) => {
                        const $ = window.jQuery;
                        if ($ && $.fn.datepicker &&
                            $(e).hasClass('hasDatepicker')) {
                            $(e).datepicker(
                                'setDate',
                                new Date(
                                    d.year,
                                    d.month - 1,
                                    d.day
                                )
                            );
                            $(e).trigger('change');
                            return true;
                        }
                        return false;
                    }""",
                    {
                        "year": date.year,
                        "month": date.month,
                        "day": date.day
                    }
                )

                if not applied:
                    date_field.click()
                    raise RuntimeError(
                        "カレンダー操作の追加解析が必要"
                    )

            date_value = date_field.input_value()

            print("DATE:", date_value)

            normalized = re.sub(
                r"[^0-9]", "", date_value
            )

            if normalized != date.strftime("%Y%m%d"):
                raise RuntimeError(
                    "出発日を確認できません: "
                    + date_value
                )

            # 片道であることを追加確認
            return_date = page.locator(
                'input[name="rt_date"]'
            )

            if (
                return_date.is_visible()
                and return_date.is_enabled()
                and return_date.is_editable()
            ):
                raise RuntimeError(
                    "復路入力欄が有効です"
                )

            # 人数確認
            number = page.locator(
                'input[name="number"]'
            )

            if number.input_value() != str(
                config["adults"]
            ):
                if number.is_editable():
                    number.fill(
                        str(config["adults"])
                    )
                    number.press("Tab")

            if number.input_value() != str(
                config["adults"]
            ):
                raise RuntimeError(
                    "人数を確認できません"
                )

            print("PASSENGERS:", number.input_value())

            page.screenshot(
                path="booking-page.png",
                full_page=True
            )

            # 空席検索のみ実行
            search = page.get_by_role(
                "button",
                name="検索",
                exact=True
            )

            search.click()

            page.wait_for_timeout(5000)

            print("RESULT URL:", page.url)
            print("RESULT TITLE:", page.title())

            # 検索結果の解析用ログ
            for i, frame in enumerate(page.frames):
                print("FRAME:", i)

                text = frame.locator(
                    "body"
                ).inner_text()

                print("RESULT TEXT:")
                print(text[:20000])

                controls = frame.locator(
                    "input, select, button, a"
                ).evaluate_all("""
                    elements => elements
                        .filter(e => e.getClientRects().length)
                        .map(e => ({
                            tag: e.tagName,
                            type: e.type || "",
                            id: e.id || "",
                            name: e.name || "",
                            text: e.innerText || "",
                            disabled: !!e.disabled,
                            options: e.tagName === 'SELECT'
                                ? Array.from(e.options).map(o => ({
                                    text: o.text,
                                    value: o.value,
                                    disabled: o.disabled
                                }))
                                : []
                        }))
                """)

                print(json.dumps(
                    controls,
                    ensure_ascii=False,
                    indent=2
                ))

            result["message"] = (
                "検索ボタン操作済み・空席判定未検証"
            )

        finally:
            if page is not None:
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
        "stock.json",
        "w",
        encoding="utf-8"
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
