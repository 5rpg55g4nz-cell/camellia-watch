import json
import re
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

target = datetime.strptime(
    config["departure_date"], "%Y-%m-%d"
)

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


def check_date(field):
    value = field.input_value()
    print("SELECTED DATE:", value)

    digits = re.sub(r"[^0-9]", "", value)

    return digits == target.strftime("%Y%m%d")


def calendar_debug(page):
    print("CALENDAR DEBUG START")

    items = page.locator(
        "input, button, a, td, th, select, "
        "[data-date], [aria-label]"
    ).evaluate_all("""
        elements => elements
          .filter(e =>
              e.getClientRects().length &&
              getComputedStyle(e).visibility
                  !== 'hidden'
          )
          .slice(0, 350)
          .map(e => ({
              tag: e.tagName,
              text: (e.innerText || '').trim(),
              id: e.id || '',
              class: String(e.className || ''),
              name: e.name || '',
              title: e.title || '',
              date: e.getAttribute('data-date'),
              aria: e.getAttribute('aria-label'),
              disabled: !!e.disabled,
              readonly: !!e.readOnly
          }))
    """)

    print(json.dumps(
        items, ensure_ascii=False, indent=2
    ))

    print("CALENDAR DEBUG END")


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

        page.set_default_timeout(10000)

        try:
            page.goto(
                config["url"],
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(2000)

            print("PAGE TITLE:", page.title())
            print("PAGE URL:", page.url)

            # 片道
            one_way = page.locator(
                'input[name="oufuku"][value="1"]'
            )

            one_way.check()

            if not one_way.is_checked():
                raise RuntimeError(
                    "片道選択エラー"
                )

            print("TRIP: ONE WAY")

            # 博多から釜山
            route = page.locator(
                'select[name="ow"]'
            )

            route.select_option("1")

            if route.input_value() != "1":
                raise RuntimeError(
                    "航路選択エラー"
                )

            print("ROUTE: HAKATA -> BUSAN")

            # カレンダーを開く
            date_field = page.locator(
                'input[name="ow_date"]'
            )

            date_field.click()
            page.wait_for_timeout(1000)

            page.screenshot(
                path="booking-page.png",
                full_page=True
            )

            calendar_debug(page)

            # 日付選択候補
            selectors = [
                f'[data-date="{target:%Y-%m-%d}"]',
                f'[data-date="{target:%Y/%m/%d}"]',
                f'[aria-label="{target:%Y-%m-%d}"]',
                f'[title="{target:%Y-%m-%d}"]'
            ]

            found = False

            for selector in selectors:
                candidates = page.locator(
                    selector + ":visible"
                )

                if candidates.count() == 1:
                    item = candidates.first

                    if item.is_enabled():
                        try:
                            item.click(timeout=2000)
                            page.wait_for_timeout(500)

                            if check_date(date_field):
                                found = True
                                break

                        except Exception:
                            pass

            # Flatpickr形式の場合
            if not found:
                calendar = page.locator(
                    ".flatpickr-calendar.open"
                )

                if calendar.count() == 1:
                    for attempt in range(4):

                        month = calendar.locator(
                            ".flatpickr-monthDropdown-months"
                        )

                        year = calendar.locator(
                            ".cur-year"
                        )

                        if (
                            month.count() == 1
                            and year.count() == 1
                        ):
                            current_month = int(
                                month.input_value()
                            ) + 1

                            current_year = int(
                                year.input_value()
                            )

                            if (
                                current_year == target.year
                                and current_month == target.month
                            ):
                                day = calendar.locator(
                                    ".flatpickr-day"
                                    ":not(.prevMonthDay)"
                                    ":not(.nextMonthDay)"
                                    ":not(.flatpickr-disabled)"
                                ).filter(
                                    has_text=re.compile(
                                        f"^{target.day}$"
                                    )
                                )

                                if day.count() == 1:
                                    day.click()
                                    found = check_date(
                                        date_field
                                    )

                                break

                            if (
                                current_year,
                                current_month
                            ) > (
                                target.year,
                                target.month
                            ):
                                break

                            calendar.locator(
                                ".flatpickr-next-month"
                            ).click()

                            page.wait_for_timeout(400)

                        else:
                            break

            if not found:
                raise RuntimeError(
                    "カレンダーの構造確認が必要"
                )

            print("DATE: VERIFIED")

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

            if number.input_value() != str(
                config["adults"]
            ):
                raise RuntimeError(
                    "人数設定エラー"
                )

            print("PASSENGERS:", number.input_value())

            # 検索直前の再確認
            if not one_way.is_checked():
                raise RuntimeError(
                    "片道の再確認に失敗"
                )

            if route.input_value() != "1":
                raise RuntimeError(
                    "航路の再確認に失敗"
                )

            if not check_date(date_field):
                raise RuntimeError(
                    "日付の再確認に失敗"
                )

            # 空席照会のみ実行
            search = page.get_by_role(
                "button",
                name="検索",
                exact=True
            )

            search.click()

            page.wait_for_timeout(5000)

            print("RESULT URL:", page.url)
            print("RESULT TITLE:", page.title())

            print("RESULT TEXT START")
            print(
                page.locator("body")
                .inner_text()[:20000]
            )
            print("RESULT TEXT END")

            calendar_debug(page)

            result["message"] = (
                "検索実行済み・空席判定未検証"
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
