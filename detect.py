import re
from pathlib import Path

FILE_TO_CHECK = Path("./result/merged.txt")

def analyze_file():
    if not FILE_TO_CHECK.exists():
        print(f"Ошибка: Файл '{FILE_TO_CHECK}' не найден!")
        return

    with open(FILE_TO_CHECK, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Ищем полностью отсутствующие вопросы (-7-, -10-)
    missing_matches = re.findall(r'^-(\d+)-$', content, re.MULTILINE)
    missing_questions = sorted([int(num) for num in missing_matches])

    # 2. Ищем вопросы без отмеченного правильного ответа (+)
    question_blocks = re.split(r'(?=\n\d+\.\s*\")', content)
    unanswered_questions = []

    for block in question_blocks:
        block = block.strip()
        if not block:
            continue

        match_num = re.match(r'^(\d+)\.', block)
        if match_num:
            q_num = match_num.group(1)
            if '+' not in block:
                unanswered_questions.append(int(q_num))
    
    unanswered_questions.sort()

    # Вывод итогового отчета
    print("="*50)
    print("ОТЧЕТ ПО АНАЛИЗУ ТЕСТОВ")
    print("="*50)
    
    if missing_questions:
        print(f"❌ Вообще отсутствуют в базе ({len(missing_questions)} шт):")
        print(f"   {missing_questions}\n")
    else:
        print("✅ Все вопросы присутствуют в структуре файла.\n")

    if unanswered_questions:
        print(f"⚠️ Вопросы без отмеченного от '+' (всего {len(unanswered_questions)} шт):")
        print(f"   {unanswered_questions}")
    else:
        print("✅ Во всех существующих вопросах проставлены правильные ответы!")
    print("="*50)

if __name__ == "__main__":
    analyze_file()