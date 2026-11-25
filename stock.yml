name: Camellia Watch

on:
  workflow_dispatch:
  schedule:
    - cron: '2-59/5 * * * *'

permissions:
  contents: write

concurrency:
  group: camellia-watch
  cancel-in-progress: false

jobs:
  check-stock:
    runs-on: ubuntu-latest
    timeout-minutes: 8

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Check monitoring period
        id: period
        run: |
          TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)
          if [[ "$TODAY" > "2026-12-26" ]]; then
            echo "active=false" >> "$GITHUB_OUTPUT"
          else
            echo "active=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Setup Python
        if: steps.period.outputs.active == 'true'
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install dependencies
        if: steps.period.outputs.active == 'true'
        run: pip install -r requirements.txt

      - name: Install Chromium
        if: steps.period.outputs.active == 'true'
        run: python -m playwright install --with-deps chromium

      - name: Check availability
        id: stock
        if: steps.period.outputs.active == 'true'
        run: python check_stock.py

      - name: Save stock data
        if: always() && steps.period.outputs.active == 'true'
        run: |
          if [ -f stock.json ]; then
            git config user.name "Camellia Watch"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add stock.json
            if ! git diff --cached --quiet; then
              git commit -m "Update availability"
              git push
            fi
          fi

      - name: Upload debug files
        if: always() && steps.period.outputs.active == 'true'
        uses: actions/upload-artifact@v4
        with:
          name: camellia-debug
          path: |
            booking-page.png
            stock.json
          retention-days: 1
