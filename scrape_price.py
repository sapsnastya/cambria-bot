import os
import re
import json
from playwright.sync_api import sync_playwright
import requests

URL = "https://trade.aspecta.ai/projects/usdt/Cambria"
STATE_FILE = "last_price.json"

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Після діагностичного запуску встановіть цей індекс на номер
# правильної ціни зі списку, який бот надішле вам у Telegram.
# 0 = перше знайдене число, 1 = друге, і т.д.
PRICE_INDEX = int(os.environ.get("PRICE_INDEX") or "0")

# true -> бот лише покаже ВСІ знайдені числа й нічого не збереже
DIAGNOSTIC = os.environ.get("DIAGNOSTIC", "false").lower() == "true"


def fetch_rendered_text():
    """Відкриває сторінку у справжньому (headless) браузері й чекає,
    поки JavaScript домалює вміст, після чого повертає весь текст сторінки."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        # додатковий запас часу, щоб React встиг домалювати ціну
        page.wait_for_timeout(6000)
        text = page.inner_text("body")
        browser.close()
    return text


def extract_price_candidates(text):
    """Знаходить у тексті сторінки всі числа у форматі ціни ($1.23, $0.0041 і т.д.)."""
    return re.findall(r"\$\s?\d[\d,]*\.?\d*", text)


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    resp.raise_for_status()


def load_last_price():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("price")
    return None


def save_price(price: str):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"price": price}, f, ensure_ascii=False)


def main():
    text = fetch_rendered_text()
    candidates = extract_price_candidates(text)

    if not candidates:
        send_telegram(
            "⚠️ Не вдалося знайти жодної ціни на сторінці Cambria. "
            "Можливо, сайт змінив структуру, або сторінка не завантажилась."
        )
        return

    if DIAGNOSTIC:
        numbered = "\n".join(f"{i}: {v}" for i, v in enumerate(candidates[:25]))
        send_telegram(
            "🔍 Діагностика. Ось усі знайдені на сторінці числа з $:\n\n"
            f"{numbered}\n\n"
            "Порівняйте з тим, що бачите на сайті, і повідомте номер правильної ціни."
        )
        return

    if PRICE_INDEX >= len(candidates):
        send_telegram(
            f"⚠️ PRICE_INDEX={PRICE_INDEX}, але на сторінці знайдено лише "
            f"{len(candidates)} чисел. Запустіть діагностичний режим ще раз."
        )
        return

    current_price = candidates[PRICE_INDEX]
    last_price = load_last_price()

    if last_price is None:
        save_price(current_price)
        send_telegram(f"✅ Бот запущено. Поточна ціна Cambria: {current_price}")
        return

    if current_price != last_price:
        send_telegram(
            f"🔔 Ціна Cambria змінилась!\n"
            f"Було: {last_price}\n"
            f"Стало: {current_price}"
        )
        save_price(current_price)
    # якщо ціна не змінилась - нічого не надсилаємо


if __name__ == "__main__":
    main()
