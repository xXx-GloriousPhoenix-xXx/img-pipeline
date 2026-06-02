import os
import re
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"F:\\Programmes\\Tesseract\\Installed\\tesseract.exe"

INPUT_DIR = "./media"
OUTPUT_FILE = "./test.txt"

def extract_text_from_image(image_path):
    """Извлекает текст из картинки с помощью OCR."""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang='ukr+eng')
    return text.strip()

def parse_question_and_answers(text):
    """
    Парсит текст:
    - первая строка или блок до пустой строки - вопрос
    - остальное - строки вида "номер | ответ" или "номер. ответ"
    - правильный ответ помечен знаком '+'
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return None, None, None

    # Вопрос — до первой пустой строки, но у нас пустые уже удалены,
    # поэтому берём первую строку как вопрос.
    question = lines[0]

    # Находим строки с ответами (начиная со второй строки)
    answer_lines = lines[1:]
    answers = []
    correct_answer_text = None

    for line in answer_lines:
        # Ищем номер ответа и сам ответ
        # Поддерживает форматы: "1 | Ответ" или "1. Ответ"
        match = re.match(r'^\s*(\d+)\s*[\.|]\s*(.+)$', line)
        if not match:
            continue

        num = int(match.group(1))
        answer_full = match.group(2).strip()

        # Проверяем, есть ли пометка правильного ответа (+ в любом месте)
        if '+' in answer_full:
            correct_answer_text = answer_full.replace('+', '').strip()
            # Убираем + из выводимого варианта
            answer_clean = answer_full.replace('+', '').strip()
        else:
            answer_clean = answer_full

        answers.append((num, answer_clean))

    # Если правильный ответ не найден, берём последний вариант как правильный (опционально)
    # Но лучше явно отмечать '+'
    if correct_answer_text is None and answers:
        correct_answer_text = answers[-1][1]

    return question, answers, correct_answer_text

def format_output(question, answers, correct_answer):
    """Форматирует в нужный вид:
    "Вопрос"
    1. Ответ 1
    2. Ответ 2
    3. Ответ 3 +
    """
    lines = [f'"{question}"']
    for num, ans in answers:
        if ans == correct_answer:
            lines.append(f"{num}. {ans} +")
        else:
            lines.append(f"{num}. {ans}")
    return "\n".join(lines)

def main():
    # Убедимся, что папка существует
    if not os.path.exists(INPUT_DIR):
        print(f"Папка {INPUT_DIR} не найдена!")
        return

    # Находим все файлы image{n}.jpeg
    image_files = []
    for f in os.listdir(INPUT_DIR):
        if f.startswith("image") and f.lower().endswith((".jpeg", ".jpg")):
            # Извлекаем номер для сортировки
            match = re.search(r'image(\d+)', f)
            if match:
                num = int(match.group(1))
                image_files.append((num, f))

    image_files.sort()  # сортируем по номеру

    if not image_files:
        print("Нет файлов вида image*.jpeg в ./media")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_f:
        for num, filename in image_files:
            img_path = os.path.join(INPUT_DIR, filename)
            print(f"Обработка: {filename}")

            # 1. Распознаём текст
            text = extract_text_from_image(img_path)
            if not text:
                print(f"  Предупреждение: не удалось извлечь текст из {filename}")
                continue

            # 2. Парсим вопрос и ответы
            question, answers, correct = parse_question_and_answers(text)
            if not question or not answers:
                print(f"  Предупреждение: не удалось распарсить {filename}")
                print(f"  Текст: {text[:200]}")
                continue

            # 3. Форматируем и записываем
            formatted = format_output(question, answers, correct)
            out_f.write(formatted + "\n\n")
            print(f"  Добавлено: {question[:50]}...")

    print(f"\nГотово! Результат в {OUTPUT_FILE}")

if __name__ == "__main__":
    main()