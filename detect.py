import re
from pathlib import Path

# Указываем путь к файлу, который нужно проверить
FILE_TO_CHECK = Path("./result/merged.txt")

def find_questions_without_answers():
    if not FILE_TO_CHECK.exists():
        print(f"Ошибка: Файл '{FILE_TO_CHECK}' не найден. Сначала запустите merge.py!")
        return

    with open(FILE_TO_CHECK, 'r', encoding='utf-8') as f:
        content = f.read()

    # Делим файл на блоки, каждый из которых начинается с "Номер. "Вопрос""
    question_blocks = re.split(r'(?=\n\d+\.\s*\")', content)
    unanswered_questions = []

    for block in question_blocks:
        block = block.strip()
        if not block:
            continue

        # Извлекаем номер вопроса
        match_num = re.match(r'^(\d+)\.', block)
        if match_num:
            q_num = match_num.group(1)
            
            # Если в блоке вопроса нет знака '+', значит ответ не отмечен
            if '+' not in block:
                unanswered_questions.append(int(q_num))

    # Сортируем номера по порядку
    unanswered_questions.sort()

    # Выводим результат
    if unanswered_questions:
        print(f"\nВнимание! Найдено вопросов без отмеченного ответа: {len(unanswered_questions)}")
        print(f"Номера вопросов: {unanswered_questions}")
    else:
        print("\nПроверка пройдена! Во всех вопросах успешно найдены ответы с плюсом (+).")

if __name__ == "__main__":
    find_questions_without_answers()