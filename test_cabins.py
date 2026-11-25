import json
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

TARGET = "2026-12-15"
ADULTS = 2

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        viewport={"width": 1280, "height": 1100}
    )

    page.set_default_timeout(15000)

    page.goto(
        config["url"],
        wait_until="domcontentloaded",
        timeout=60000
    )

    one_way = page.locator(
        'input[name="oufuku"][value="1"]'
    )
    one_way.check()

    route = page.locator('select[name="ow"]')
    route.select_option("1")

    date_field = page.locator(
        'input[name="ow_date"]'
    )
    date_field.click()

    page.locator(
        f'#set_calendar dd.enable'
        f'[data-ymd="{TARGET}"]:visible'
    ).click()

    number = page.locator(
        'input[name="number"]'
    )

    if number.input_value() != str(ADULTS):
        number.fill(str(ADULTS))
        number.press("Tab")

    assert one_way.is_checked()
    assert route.input_value() == "1"
    assert date_field.input_value() == TARGET
    assert number.input_value() == str(ADULTS)

    page.get_by_role(
        "button", name="検索", exact=True
    ).click()

    page.wait_for_url(
        "**/idv/reservation**",
        timeout=30000
    )

    rows = page.locator("table.table01 tr.plan")
    rows.first.wait_for(state="attached")

    text = page.locator("body").inner_text()

    if TARGET not in text or "博多発" not in text:
        raise RuntimeError("検索結果不一致")

    if page.locator("#renumber").input_value() != "2":
        raise RuntimeError("人数不一致")

    groups = [
        "pill-40",
        "pill-33",
        "pill-32",
        "pill-31",
        "pill-other"
    ]

    for group in groups:

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

        print("ACTIVE TAB:", group)

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
                            ?.textContent.trim(),
                        people: rc?.dataset.peoplenum,
                        rooms: rc?.dataset.roomnum,
                        capacity: rc?.dataset.capa,
                        minimum: rc?.dataset.mincapa
                    };
                }
            """)

            info["group"] = group
            info["status"] = "unknown"

            availability = info.get(
                "availability", ""
            ) or ""

            if "売り切れ" in availability:
                info["status"] = "sold_out"

            elif "ご指定の人数では" in availability:
                info["status"] = "ineligible"

            elif (
                info.get("rooms") is not None
                and info.get("capacity") is not None
                and info.get("minimum") is not None
                and (
                    int(info["capacity"]) < ADULTS
                    or int(info["minimum"]) > ADULTS
                )
            ):
                info["status"] = "ineligible"

            elif (
                info.get("people") is not None
                and int(info["people"]) < ADULTS
            ):
                info["status"] = "insufficient"

            elif (
                info.get("rooms") is not None
                and int(info["rooms"]) == 0
            ):
                info["status"] = "sold_out"

            else:
                fields = row.locator(
                    'input.ui-spinner-input'
                    '[data-kbn="1"]:visible'
                )

                if fields.count() == 1:

                    field = fields.first

                    maximum = int(
                        field.get_attribute(
                            "aria-valuemax"
                        ) or "0"
                    )

                    up = field.locator(
                        "xpath=.."
                    ).locator(".ui-spinner-up")

                    down = field.locator(
                        "xpath=.."
                    ).locator(".ui-spinner-down")

                    initial = int(
                        field.input_value() or "0"
                    )

                    if (
                        maximum >= ADULTS
                        and initial == 0
                        and field.is_enabled()
                    ):
                        try:
                            for _ in range(ADULTS):
                                up.click(timeout=3000)

                            selected = int(
                                field.input_value() or "0"
                            )

                            info["selected"] = selected

                            if selected == ADULTS:
                                info["status"] = (
                                    "two_adults_selected"
                                )

                        except Exception as e:
                            info["error"] = str(e)

                        finally:
                            for _ in range(ADULTS):
                                current = int(
                                    field.input_value() or "0"
                                )

                                if current <= initial:
                                    break

                                down.click(timeout=3000)

                            if int(
                                field.input_value() or "0"
                            ) != initial:
                                raise RuntimeError(
                                    "人数のリセット失敗"
                                )

            results.append(info)

            print(json.dumps(
                info,
                ensure_ascii=False
            ))

    page.screenshot(
        path="booking-page.png",
        full_page=True
    )

    browser.close()

print("FINAL RESULTS:")

print(json.dumps(
    results,
    ensure_ascii=False,
    indent=2
))

confirmed = [
    room for room in results
    if room["status"] == "two_adults_selected"
]

print("CONFIRMED PLANS:", len(confirmed))

for room in confirmed:
    print(room["name"], room["price"])
