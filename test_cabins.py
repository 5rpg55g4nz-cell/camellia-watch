import json
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        locale="ja-JP",
        timezone_id="Asia/Tokyo"
    )

    page.set_default_timeout(15000)

    page.goto(
        config["url"],
        wait_until="domcontentloaded"
    )

    page.locator(
        'input[name="oufuku"][value="1"]'
    ).check()

    page.locator(
        'select[name="ow"]'
    ).select_option("1")

    page.locator(
        'input[name="ow_date"]'
    ).click()

    page.locator(
        '#set_calendar '
        'dd.enable[data-ymd="2026-12-15"]:visible'
    ).click()

    number = page.locator(
        'input[name="number"]'
    )

    if number.input_value() != "2":
        number.fill("2")
        number.press("Tab")

    page.get_by_role(
        "button", name="検索", exact=True
    ).click()

    page.wait_for_url(
        "**/idv/reservation**",
        timeout=30000
    )

    page.locator(
        "table.table01 tr.plan"
    ).first.wait_for(state="attached")

    print("TAB CONTROLS:")

    controls = page.locator(
        "a, button, li, [role=tab]"
    ).evaluate_all("""
        elements => elements
          .filter(e =>
            e.getClientRects().length &&
            /等室|等寝台|その他|特等|pill/.test(
              e.outerHTML
            )
          )
          .map(e => ({
            text: e.innerText,
            html: e.outerHTML.slice(0, 5000)
          }))
    """)

    print(json.dumps(
        controls,
        ensure_ascii=False,
        indent=2
    ))

    print("PRIVATE CABINS:")

    cabins = page.locator(
        'tr.plan[data-pill="pill-32"],'
        'tr.plan[data-pill="pill-other"]'
    ).evaluate_all("""
        rows => rows.map(row => ({
            id: row.dataset.trplan,
            group: row.dataset.pill,
            visible: !!row.getClientRects().length,
            html: row.outerHTML
        }))
    """)

    print(json.dumps(
        cabins,
        ensure_ascii=False,
        indent=2
    ))

    page.screenshot(
        path="booking-page.png",
        full_page=True
    )

    browser.close()
