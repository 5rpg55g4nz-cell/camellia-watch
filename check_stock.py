import json
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

now = datetime.now(ZoneInfo("Asia/Tokyo"))

result = {
    "checked_at": now.isoformat(),
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
        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="ja-JP",
            timezone_id="Asia/Tokyo"
        )

        page.goto(
            config["url"],
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        print("PAGE TITLE:", page.title())
        print("PAGE URL:", page.url())

        fields = page.locator(
            "input, select, button, a"
        ).evaluate_all("""
            elements => elements
              .filter(e => e.getClientRects().length)
              .map(e => ({
                tag: e.tagName,
                type: e.type,
                id: e.id,
                name: e.name,
                value: e.value,
                text: e.innerText,
                placeholder: e.placeholder,
                options: e.tagName === 'SELECT'
                  ? Array.from(e.options).map(o => ({
                      text: o.text,
                      value: o.value
                    }))
                  : []
              }))
        """)

        print(json.dumps(
            fields,
            ensure_ascii=False,
            indent=2
        ))

        page.screenshot(
            path="booking-page.png",
            full_page=True
        )

        result["message"] = (
            "予約ページ取得済み・空席未照会"
        )

        browser.close()

except Exception as e:
    result["status"] = "error"
    result["message"] = str(e)
    print("ERROR:", e)

with open("stock.json", "w", encoding="utf-8") as f:
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
