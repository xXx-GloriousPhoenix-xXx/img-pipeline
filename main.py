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
    i = 1
    while True:
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1
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


# ---------------------------------------------------------------------------
# Глобальный курсор — указывает на текущий рабочий слот (ключ × модель).
# Продвигается вперёд только при 429/404.
# При успехе остаётся на месте — следующий запрос стартует с того же слота.
# Если прошёл полный круг без единого успеха — скрипт завершает работу.
# ---------------------------------------------------------------------------
_cursor = {"key": 0, "model": 0}


def _advance_cursor():
    """Сдвигает курсор на следующий слот (по кругу)."""
    _cursor["model"] += 1
    if _cursor["model"] >= len(MODELS):
        _cursor["model"] = 0
        _cursor["key"] += 1
    if _cursor["key"] >= len(API_KEYS):
        _cursor["key"] = 0


def call_api_with_fallback(image_path):
    """
    Начинает с текущей позиции курсора.
    429/404 → курсор сдвигается, пробуем следующий слот.
    Успех   → курсор остаётся, возвращаем результат.
    Если прошли все слоты по кругу без успеха → возвращаем None и завершаем.
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

    total_slots = len(API_KEYS) * len(MODELS)

    for attempt in range(total_slots):
        key_idx    = _cursor["key"]
        model_idx  = _cursor["model"]
        api_key    = API_KEYS[key_idx]
        model_name = MODELS[model_idx]
        key_label  = f"key[{key_idx + 1}/{len(API_KEYS)}]"

        print(f"\n    Пробуем {key_label} + {model_name} ...", end=" ", flush=True)

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

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                print("OK")
                return text  # курсор НЕ сдвигаем

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")

            if e.code == 429:
                print("429 (лимит)")
                _advance_cursor()
                time.sleep(2)
            elif e.code == 404:
                print("404 (модель недоступна)")
                _advance_cursor()
            else:
                print(f"HTTP {e.code}: {body[:150]}")
                return None  # не лимитная ошибка — дальше нет смысла

        except Exception as err:
            print(f"ERR: {err}")
            return None

    print("\n    [ERR] Все ключи и модели исчерпали лимит — завершение работы.")
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
    total_slots = len(API_KEYS) * len(MODELS)
    print(f"Всего слотов (ключ × модель): {total_slots}")

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

        if data is None:
            # None от call_api означает либо фатальную ошибку, либо все слоты исчерпаны
            print(" → ОСТАНОВКА")
            failed.append(filename)
            break  # прекращаем обработку — продолжать нет смысла

        if not data.get("question") or not data.get("answers"):
            print(" → ПРОПУЩЕНО (пустой ответ)")
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
        print(f"Пропущено/остановлено ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()