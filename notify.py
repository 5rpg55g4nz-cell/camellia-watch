import json
import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

with open("stock.json", encoding="utf-8") as f:
    data = json.load(f)

topic = os.environ.get("NTFY_TOPIC", "")
url = "https://www.camellia-line.co.jp/rs/?country=1"

if not topic:
    raise RuntimeError("NTFY_TOPIC is missing")

if (
    data.get("departure_date") != "2026-12-27"
    or data.get("departure") != "博多"
    or data.get("destination") != "釜山"
    or data.get("adults") != 2
    or data.get("status") != "candidate"
):
    print("NO NOTIFICATION: Conditions not met")
    raise SystemExit(0)

checked = datetime.fromisoformat(data["checked_at"])
now = datetime.now(ZoneInfo("Asia/Tokyo"))

if not timedelta(0) <= now - checked <= timedelta(minutes=5):
    print("NO NOTIFICATION: Stale data")
    raise SystemExit(0)

rooms = [
    room for room in data.get("rooms", [])
    if room.get("status") == "candidate"
    and room.get("selected") == 2
]

if not rooms:
    print("NO NOTIFICATION: No eligible cabins")
    raise SystemExit(0)

lines = [
    "2026年12月27日（日）",
    "博多 → 釜山",
    "片道・大人2名",
    "",
    "大人2名分の空席候補を検知しました。",
    ""
]

for room in rooms:
    lines.append(room.get("name") or "客室")

    lines.append(
        "表示運賃：" + str(
            room.get("price") or "不明"
        )
    )

    remaining = room.get("remaining")

    if remaining is not None:
        unit = (
            "人"
            if room.get("remaining_unit") == "people"
            else "室"
        )

        lines.append(
            f"残り：{remaining}{unit}"
        )

    lines.append("")

lines.extend([
    "確認時刻：" + checked.astimezone(
        ZoneInfo("Asia/Tokyo")
    ).strftime("%Y/%m/%d %H:%M:%S"),
    "",
    "公式予約画面で大人2名を選択できました。",
    "最終的な予約可否は公式サイトで確認してください。",
    "",
    url
])

response = requests.post(
    "https://ntfy.sh/" + topic,
    data="\n".join(lines).encode("utf-8"),
    headers={
        "Title": "Camellia Watch - Vacancy Alert",
        "Priority": "urgent",
        "Tags": "ship,bell",
        "Click": url
    },
    timeout=20
)

if not response.ok:
    raise RuntimeError(
        f"Notification failed: HTTP {response.status_code}"
    )

print("NOTIFICATION SENT")
