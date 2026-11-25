import json
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

            page.wait_for_timeout(2000)

            print("PAGE TITLE:", page.title())
            print("PAGE URL:", page.url)

            one_way = page.locator(
                'input[name="oufuku"][value="1"]'
            )
            one_way.check()

            route = page.locator(
                'select[name="ow"]'
            )
            route.select_option("1")

            print("ONE WAY:", one_way.is_checked())
            print("ROUTE:", route.input_value())

            date_field = page.locator(
                'input[name="ow_date"]'
            )

            print("DATE INPUT HTML:")
            print(date_field.evaluate(
                "e => e.outerHTML"
            ))

            print("DATE BEFORE:", date_field.input_value())

            date_field.click()
            page.wait_for_timeout(2000)

            print("VISIBLE PAGE TEXT START")
            print(page.locator("body").inner_text())
            print("VISIBLE PAGE TEXT END")

            # カレンダーの親要素を取得
            buttons = page.locator(
                ".btn-next.next:visible"
            )

            print("CALENDAR NEXT BUTTONS:", buttons.count())

            for i, button in enumerate(buttons.all()):
                print("CALENDAR HTML START:", i)

                html = button.evaluate("""
                    e => {
                        let node = e;
                        for (let i = 0; i < 4; i++) {
                            if (node.parentElement) {
                                node = node.parentElement;
                            }
                        }
                        return node.outerHTML;
                    }
                """)

                print(html[:60000])
                print("CALENDAR HTML END")

            # 日付候補の要素を取得
            candidates = page.locator("body *").evaluate_all("""
                elements => elements
                  .filter(e =>
                    e.getClientRects().length &&
                    getComputedStyle(e).visibility
                      !== 'hidden' &&
                    e.children.length === 0 &&
                    /^\\d{1,2}$/.test(
                      (e.textContent || '').trim()
                    )
                  )
                  .slice(0, 200)
                  .map(e => ({
                      text: e.textContent.trim(),
                      html: e.outerHTML,
                      parent: e.parentElement
                        ? e.parentElement.outerHTML
                            .slice(0, 1500)
                        : ''
                  }))
            """)

            print("DAY ELEMENTS START")
            print(json.dumps(
                candidates,
                ensure_ascii=False,
                indent=2
            ))
            print("DAY ELEMENTS END")

            # カレンダー関連ライブラリの確認
            libraries = page.evaluate("""
                () => ({
                    jquery: typeof window.jQuery,
                    datepicker: !!(
                        window.jQuery &&
                        window.jQuery.fn.datepicker
                    ),
                    flatpickr: typeof window.flatpickr,
                    scripts: Array.from(
                        document.scripts
                    ).map(s => s.src).filter(Boolean)
                })
            """)

            print("LIBRARIES:")
            print(json.dumps(
                libraries,
                ensure_ascii=False,
                indent=2
            ))

            result["message"] = (
                "カレンダー詳細解析完了・空席未照会"
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
