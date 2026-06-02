import os
import re
import base64
import json
import time
import argparse
import urllib.request
import urllib.error


def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

INPUT_DIR = "./media"
OUTPUT_FILE = "./data.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

DELAY_BETWEEN_REQUESTS = 5  # секунд между запросами (≈12 RPM, лимит 15)
DELAY_AFTER_429 = 90        # секунд ожидания после rate limit
MAX_RETRIES = 5             # максимум попыток на один файл

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


def call_api(image_path):
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": get_mime_type(image_path),
                                 "data": encode_image(image_path)}},
                {"text": PROMPT}
            ]
        }],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_URL}?key={GEMINI_API_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def fix_truncated_json(text):
    """Пытается починить обрезанный JSON — закрывает незакрытые структуры."""
    text = re.sub(r',\s*$', '', text.rstrip())
    opens = text.count('{') - text.count('}')
    arrays = text.count('[') - text.count(']')
    text += ']' * arrays + '}' * opens
    return text


def extract_qa_from_image(image_path):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            text = call_api(image_path)
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            if e.code == 429:
                print(f"\n    [429] Rate limit — ждём {DELAY_AFTER_429}с "
                      f"(попытка {attempt}/{MAX_RETRIES})", end="", flush=True)
                for _ in range(DELAY_AFTER_429):
                    time.sleep(1)
                    print(".", end="", flush=True)
                print()
            elif e.code == 503:
                wait = 15 * attempt
                print(f"\n    [503] Перегружен — ждём {wait}с "
                      f"(попытка {attempt}/{MAX_RETRIES})...", flush=True)
                time.sleep(wait)
            else:
                print(f"\n    [HTTP {e.code}] {body[:150]}")
                return None

        except json.JSONDecodeError:
            print(f"\n    [JSON] Обрезан — пробуем починить...", end=" ", flush=True)
            try:
                text2 = call_api(image_path)
                text2 = re.sub(r"^```json\s*", "", text2)
                text2 = re.sub(r"\s*```$", "", text2)
                result = json.loads(fix_truncated_json(text2))
                print("OK")
                return result
            except Exception:
                print(f"не удалось (попытка {attempt}/{MAX_RETRIES})")
            if attempt >= MAX_RETRIES:
                return None

        except Exception as e:
            print(f"\n    [ERR] {e}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    print(f"\n    Все {MAX_RETRIES} попытки исчерпаны")
    return None


def format_output(data):
    lines = [f'"{data["question"]}"']
    correct = data.get("correct_num")
    for ans in data["answers"]:
        marker = " +" if ans["num"] == correct else ""
        lines.append(f'{ans["num"]}. {ans["text"]}{marker}')
    return "\n".join(lines)


def append_to_file(text, output_file):
    """Дописывает один результат в файл сразу после получения."""
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")


def main():
    parser = argparse.ArgumentParser(description="Извлечение вопросов из изображений через Gemini")
    parser.add_argument("-f", "--from", dest="from_num", type=int, default=None,
                        metavar="N", help="начать с image N (включительно)")
    parser.add_argument("-t", "--to", dest="to_num", type=int, default=None,
                        metavar="N", help="закончить на image N (включительно)")
    parser.add_argument("-o", "--output", type=str, default=OUTPUT_FILE,
                        metavar="FILE", help=f"файл вывода (по умолчанию: {OUTPUT_FILE})")
    args = parser.parse_args()

    # Создаём файл (и папку) если не существует
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(args.output):
        open(args.output, "w", encoding="utf-8").close()
        print(f"Создан файл: {args.output}")

    if not GEMINI_API_KEY:
        print("Ошибка: GEMINI_API_KEY не задан!")
        print("Создайте .env файл с: GEMINI_API_KEY=ваш_ключ")
        return

    if not os.path.exists(INPUT_DIR):
        print(f"Папка {INPUT_DIR} не найдена!")
        return

    # Собираем и фильтруем файлы по диапазону
    image_files = []
    for f in os.listdir(INPUT_DIR):
        if f.startswith("image") and f.lower().endswith((".jpeg", ".jpg", ".png")):
            match = re.search(r"image(\d+)", f)
            if match:
                n = int(match.group(1))
                if (args.from_num is None or n >= args.from_num) and \
                   (args.to_num   is None or n <= args.to_num):
                    image_files.append((n, f))
    image_files.sort()

    if not image_files:
        print("Нет файлов, подходящих под указанный диапазон")
        return

    total = len(image_files)
    range_str = f"image{image_files[0][0]} → image{image_files[-1][0]}"
    print(f"Файлов к обработке: {total} ({range_str})")
    print(f"Вывод: {args.output}")
    print(f"Задержка между запросами: {DELAY_BETWEEN_REQUESTS}с\n")

    failed = []

    for idx, (num, filename) in enumerate(image_files, 1):
        img_path = os.path.join(INPUT_DIR, filename)
        print(f"  [{idx}/{total}] {filename} ...", end=" ", flush=True)

        data = extract_qa_from_image(img_path)

        if not data or not data.get("question") or not data.get("answers"):
            print("ПРОПУЩЕНО")
            failed.append(filename)
        else:
            formatted = format_output(data)
            append_to_file(formatted, args.output)  # ← сразу пишем в файл
            print(f"OK — {data['question'][:55]}...")

        if idx < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\n{'='*45}")
    print(f"Готово! Обработано: {total - len(failed)}/{total} → {args.output}")
    if failed:
        print(f"Пропущено ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()