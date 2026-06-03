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

# Список доступных моделей для ротации (от быстрой/дешевой к более мощным)
MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

DELAY_BETWEEN_REQUESTS = 5
DELAY_AFTER_429 = 90
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
    Делает запрос к API. Если ловит 429, переключается на следующую модель.
    Если все модели исчерпаны, ждет DELAY_AFTER_429 и пробует снова с первой модели.
    """
    payload_dict = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": get_mime_type(image_path),
                                 "data": encode_image(image_path)}},
                {"text": PROMPT}
            ]
        }],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}
    }
    
    # Чтобы гарантировать JSON от Gemini 2.5/1.5, просим structured output
    payload_dict["generationConfig"]["responseMimeType"] = "application/json"
    
    payload = json.dumps(payload_dict).encode("utf-8")

    current_model_idx = 0
    retries = 0

    while retries < MAX_RETRIES:
        model_name = MODELS[current_model_idx]
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        
        req = urllib.request.Request(
            f"{api_url}?key={GEMINI_API_KEY}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()
                
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            
            # Если поймали лимит запросов (Rate Limit)
            if e.code == 429:
                print(f"\n    [HTTP 429] На модели {model_name} закончился лимит.")
                
                # Переходим к следующей модели в списке
                if current_model_idx < len(MODELS) - 1:
                    current_model_idx += 1
                    print(f"    Переключаемся на следующую модель: {MODELS[current_model_idx]}...")
                    time.sleep(2) # небольшая пауза перед переключением
                    continue
                else:
                    # Если все модели из списка выдали 429
                    retries += 1
                    current_model_idx = 0 # Сбрасываем на первую модель для следующей попытки
                    if retries < MAX_RETRIES:
                        print(f"    [!] Все модели исчерпали лимит. Ожидаем {DELAY_AFTER_429} секунд (Попытка {retries}/{MAX_RETRIES})...")
                        time.sleep(DELAY_AFTER_429)
                    continue
            else:
                # Другие HTTP ошибки (например, 400, 403, 500) не завязаны на лимиты — выходим
                print(f"\n    [HTTP {e.code}] {body[:200]}")
                return None
        except Exception as e:
            print(f"\n    [ERR в call_api] {e}")
            return None
            
    print("\n    [ERR] Достигнут максимум попыток. Не удалось получить ответ.")
    return None


def extract_qa_from_image(image_path):
    try:
        text = call_api_with_fallback(image_path)
        if not text:
            return None
            
        # Очищаем от возможных markdown-тегов (хотя responseMimeType должен вернуть чистый JSON)
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    except json.JSONDecodeError:
        print(f"\n    [JSON] Модель вернула невалидный JSON — пропускаем")
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

    if not GEMINI_API_KEY:
        print("Ошибка: GEMINI_API_KEY не задан!")
        print("Создайте .env файл с: GEMINI_API_KEY=ваш_ключ")
        return

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
        print(f"  [{idx}/{total}] {filename} ...", end=" ", flush=True)

        data = extract_qa_from_image(img_path)

        if not data or not data.get("question") or not data.get("answers"):
            print("ПРОПУЩЕНО")
            failed.append(filename)
        else:
            formatted = format_output(data, question_num=num)
            append_to_file(formatted, args.output)
            print(f"OK — {data['question'][:55]}...")

        if idx < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\n{'='*45}")
    print(f"Готово! Обработано: {total - len(failed)}/{total} → {args.output}")
    if failed:
        print(f"Пропущено ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()