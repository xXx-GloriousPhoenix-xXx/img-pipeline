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

# Поддержка нескольких ключей:
# В .env можно задать либо один ключ:   GEMINI_API_KEY=key1
# либо несколько через запятую:         GEMINI_API_KEY=key1,key2,key3
# либо нумерованные:                    GEMINI_API_KEY_1=key1
#                                       GEMINI_API_KEY_2=key2
def load_api_keys():
    keys = []

    # 1. Нумерованные переменные GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...
    i = 1
    while True:
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1

    # 2. Основная переменная (один ключ или несколько через запятую)
    main = os.environ.get("GEMINI_API_KEY", "").strip()
    if main:
        for k in main.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)

    return keys

API_KEYS = load_api_keys()

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]

DELAY_BETWEEN_REQUESTS = 5
DELAY_AFTER_ALL_KEYS_EXHAUSTED = 90
MAX_RETRIES = 5

PROMPT = """На зображенні знаходиться питання тесту та кілька варіантів відповіді (зазвичай у вигляді таблиці Excel).

Твоє завдання:
1. Витягни точний текст питання (він зазвичай у верхній частині або в стовпці B першого рядка).
2. Витягни всі варіанти відповідей з их номерами.
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


def call_api_with_fallback(image_path):
    """
    Перебирает все комбинации (ключ × модель).
    Порядок: для каждого ключа пробуем все модели по очереди.
    429 → следующая модель на том же ключе → если все модели 429 → следующий ключ.
    Если все ключи и модели исчерпаны → ждём и повторяем с начала.
    """
    if not API_KEYS:
        print("\n    [ERR] Нет доступных API ключей!")
        return None

    payload_dict = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": get_mime_type(image_path),
                                 "data": encode_image(image_path)}},
                {"text": PROMPT}
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json"
        }
    }
    payload = json.dumps(payload_dict).encode("utf-8")

    # exhausted[key_idx] = set of model indices that вернули 429 для этого ключа
    exhausted = {i: set() for i in range(len(API_KEYS))}

    retries = 0
    while retries < MAX_RETRIES:

        made_any_attempt = False

        for key_idx, api_key in enumerate(API_KEYS):
            for model_idx, model_name in enumerate(MODELS):

                if model_idx in exhausted[key_idx]:
                    continue  # эта модель уже выдала 429 для этого ключа

                made_any_attempt = True
                api_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={api_key}"
                )
                req = urllib.request.Request(
                    api_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                key_label = f"key[{key_idx + 1}/{len(API_KEYS)}]"
                print(f"\n    Пробуем {key_label} + {model_name} ...", end=" ", flush=True)

                try:
                    with urllib.request.urlopen(req) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                        print("OK")
                        return text

                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8")

                    if e.code == 429:
                        print(f"429 (лимит)")
                        exhausted[key_idx].add(model_idx)
                        time.sleep(2)
                        continue  # следующая модель / ключ
                    elif e.code == 404:
                        print(f"404 (модель недоступна — пропускаем)")
                        exhausted[key_idx].add(model_idx)
                        continue
                    else:
                        print(f"HTTP {e.code}: {body[:150]}")
                        return None  # не лимитная ошибка — смысла повторять нет

                except Exception as err:
                    print(f"ERR: {err}")
                    return None

        if not made_any_attempt:
            # Все комбинации ключ+модель истощены — ждём и сбрасываем счётчики
            retries += 1
            if retries < MAX_RETRIES:
                print(
                    f"\n    [!] Все ключи и модели исчерпали лимит. "
                    f"Ждём {DELAY_AFTER_ALL_KEYS_EXHAUSTED}с "
                    f"(попытка {retries}/{MAX_RETRIES})..."
                )
                time.sleep(DELAY_AFTER_ALL_KEYS_EXHAUSTED)
                # Сбрасываем exhausted — лимиты могли обновиться
                exhausted = {i: set() for i in range(len(API_KEYS))}
        # else: был хотя бы один attempt (всё в 429), но не все исчерпаны —
        # продолжаем внешний while без инкремента retries

    print("\n    [ERR] Достигнут максимум попыток.")
    return None


def extract_qa_from_image(image_path):
    try:
        text = call_api_with_fallback(image_path)
        if not text:
            return None

        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    except json.JSONDecodeError:
        print(f"\n    [JSON] Невалидный JSON — пропускаем")
        return None
    except Exception as e:
        print(f"\n    [ERR] {e}")
        return None


def format_output(data, question_num=None):
    prefix = f"{question_num}. " if question_num is not None else ""
    lines = [f'{prefix}"{data["question"]}"']
    correct = data.get("correct_num")
    for ans in data["answers"]:
        marker = " +" if ans["num"] == correct else ""
        lines.append(f'{ans["num"]}. {ans["text"]}{marker}')
    return "\n".join(lines)


def append_to_file(text, output_file):
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

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(args.output):
        open(args.output, "w", encoding="utf-8").close()
        print(f"Создан файл: {args.output}")

    if not API_KEYS:
        print("Ошибка: API ключи не найдены!")
        print("Добавьте в .env один из вариантов:")
        print("  GEMINI_API_KEY=key1,key2,key3")
        print("  GEMINI_API_KEY_1=key1")
        print("  GEMINI_API_KEY_2=key2")
        return

    print(f"Загружено API ключей: {len(API_KEYS)}")

    if not os.path.exists(INPUT_DIR):
        print(f"Папка {INPUT_DIR} не найдена!")
        return

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
        print(f"[{idx}/{total}] {filename}", end="", flush=True)

        data = extract_qa_from_image(img_path)

        if not data or not data.get("question") or not data.get("answers"):
            print(" → ПРОПУЩЕНО")
            failed.append(filename)
        else:
            formatted = format_output(data, question_num=num)
            append_to_file(formatted, args.output)
            print(f" → OK — {data['question'][:55]}...")

        if idx < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\n{'='*45}")
    print(f"Готово! Обработано: {total - len(failed)}/{total} → {args.output}")
    if failed:
        print(f"Пропущено ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()