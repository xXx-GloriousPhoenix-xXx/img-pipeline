import os
import re
import base64
import json
import time
import urllib.request
import urllib.error


def load_dotenv(path=".env"):
    """Загружает переменные из .env файла (без сторонних библиотек)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

REQUESTS_PER_MINUTE = 10   # чуть меньше лимита для надёжности
BATCH_SIZE = 10             # обрабатываем по 14 картинок
PAUSE_BETWEEN_BATCHES = 70  # секунд паузы между батчами

PROMPT = """На зображенні знаходиться питання тесту та кілька варіантів відповіді (зазвичай у вигляді таблиці Excel).

Твоє завдання:
1. Витягни точний текст питання (він зазвичай у верхній частині або в стовпці B першого рядка).
2. Витягни всі варіанти відповідей з їх номерами.
3. Визнач правильну відповідь — вона зазвичай позначена червоною цифрою праворуч (у стовпці "Номер Вашої відповіді"), яка збігається з номером правильного варіанту.

Поверни результат СТРОГО у форматі JSON без будь-яких додаткових пояснень:
{
  "question": "Текст питання",
  "answers": [
    {"num": 1, "text": "Відповідь 1"},
    {"num": 2, "text": "Відповідь 2"}
  ],
  "correct_num": 2
}

Важливо:
- Текст має бути мовою оригіналу (українська/англійська).
- correct_num — це номер правильної відповіді (червона цифра на зображенні).
- Якщо правильна відповідь не визначена — постав null.
- Жодного тексту крім JSON."""


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    return "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"


def extract_qa_from_image(image_path, retries=3):
    image_data = encode_image(image_path)
    mime_type = get_mime_type(image_path)

    payload = json.dumps({
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_data}},
                    {"text": PROMPT}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 1024,
        }
    }).encode("utf-8")

    url = f"{API_URL}?key={GEMINI_API_KEY}"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                text = re.sub(r"^```json\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                return json.loads(text)

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            # 429 = rate limit — ждём и повторяем
            if e.code == 429:
                wait = 60 * attempt
                print(f"\n  [429] Rate limit. Ждём {wait}с (попытка {attempt}/{retries})...", end=" ")
                time.sleep(wait)
            else:
                print(f"\n  HTTP Error {e.code}: {body[:200]}")
                return None
        except Exception as e:
            print(f"\n  Ошибка: {e}")
            if attempt < retries:
                time.sleep(5)

    return None


def format_output(data):
    lines = [f'"{data["question"]}"']
    correct = data.get("correct_num")
    for ans in data["answers"]:
        marker = " +" if ans["num"] == correct else ""
        lines.append(f'{ans["num"]}. {ans["text"]}{marker}')
    return "\n".join(lines)


def main():
    if not GEMINI_API_KEY:
        print("Ошибка: переменная окружения GEMINI_API_KEY не задана!")
        print("Запустите: export GEMINI_API_KEY=your_key_here")
        print("Получить ключ бесплатно: https://aistudio.google.com")
        return

    if not os.path.exists(INPUT_DIR):
        print(f"Папка {INPUT_DIR} не найдена!")
        return

    # Собираем файлы
    image_files = []
    for f in os.listdir(INPUT_DIR):
        if f.startswith("image") and f.lower().endswith((".jpeg", ".jpg", ".png")):
            match = re.search(r"image(\d+)", f)
            if match:
                image_files.append((int(match.group(1)), f))
    image_files.sort()

    if not image_files:
        print("Нет файлов вида image*.jpeg в ./media")
        return

    total = len(image_files)
    batches = [image_files[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)
    eta_minutes = (total_batches - 1) * PAUSE_BETWEEN_BATCHES // 60 + 1

    print(f"Найдено файлов: {total}")
    print(f"Батчей: {total_batches} по {BATCH_SIZE} шт.")
    print(f"Примерное время: ~{eta_minutes} мин.\n")

    results = []
    failed = []

    for batch_idx, batch in enumerate(batches, 1):
        print(f"── Батч {batch_idx}/{total_batches} ({len(batch)} файлов) ──")

        for num, filename in batch:
            img_path = os.path.join(INPUT_DIR, filename)
            print(f"  {filename} ...", end=" ", flush=True)

            data = extract_qa_from_image(img_path)
            time.sleep(6)  # ~10 запросов/мин внутри батча

            if not data or not data.get("question") or not data.get("answers"):
                print("ПРОПУЩЕНО")
                failed.append(filename)
                continue

            formatted = format_output(data)
            results.append(formatted)
            print(f"OK — {data['question'][:55]}...")

        # Пауза между батчами (кроме последнего)
        if batch_idx < total_batches:
            print(f"\n  Пауза {PAUSE_BETWEEN_BATCHES}с перед следующим батчем", end="")
            for _ in range(PAUSE_BETWEEN_BATCHES):
                time.sleep(1)
                print(".", end="", flush=True)
            print()

    # Записываем результат
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join(results))
        if results:
            f.write("\n")

    print(f"\n{'='*40}")
    print(f"Готово! Записано: {len(results)}/{total} вопросов → {OUTPUT_FILE}")
    if failed:
        print(f"Пропущено ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()