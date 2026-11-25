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

    scripts = {}

    def capture(response):
        try:
            if response.request.resource_type == "script":
                scripts[response.url] = response.text()
        except Exception:
            pass

    page.on("response", capture)

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

    date_field = page.locator(
        'input[name="ow_date"]'
    )

    date_field.click()

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

    assert date_field.input_value() == "2026-12-15"
    assert number.input_value() == "2"

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

    print("BOOKING BUTTONS:")

    buttons = page.locator(
        'button[data-next="passenger"]'
    ).evaluate_all("""
        items => items.map(e => ({
            html: e.outerHTML,
            disabled: e.disabled,
            visible: !!e.getClientRects().length
        }))
    """)

    print(json.dumps(
        buttons,
        ensure_ascii=False,
        indent=2
    ))

    print("FORM STRUCTURE:")

    forms = page.locator("form").evaluate_all("""
        forms => forms.map(f => ({
            action: f.getAttribute('action'),
            method: f.getAttribute('method'),
            id: f.id,
            fields: Array.from(
                f.querySelectorAll('input, select')
            ).map(e => ({
                name: e.name,
                type: e.type
            }))
        }))
    """)

    print(json.dumps(
        forms,
        ensure_ascii=False,
        indent=2
    ))

    print("RELATED JAVASCRIPT:")

    keys = [
        "btn-submit",
        "passenger",
        "room-charge",
        "peoplenum"
    ]

    for url, source in scripts.items():
        matches = [k for k in keys if k in source]

        if not matches:
            continue

        print("SCRIPT:", url)

        for key in matches:
            start = source.find(key)

            print("KEY:", key)
            print(source[
                max(0, start - 1000):
                start + 2500
            ])

    print("READ-ONLY TEST COMPLETE")
    print("NO BOOKING SUBMITTED")

    browser.close()
