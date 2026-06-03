import os
import re

# Используем прямые слэши, чтобы Windows и Python не ругались на escape-последовательности
SOURCE_DIR = "./result/batches" 
DEST_PATH = "./result/merged.txt"

def extract_numbers(filename):
    """Извлекает n и m из чистого имени файла batch-n-m.txt для правильной сортировки."""
    match = re.match(r"batch-(\d+)-(\d+)\.txt", filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return (float('inf'), float('inf'))

def process_and_merge():
    if not os.path.exists(SOURCE_DIR):
        print(f"Ошибка: Папка '{SOURCE_DIR}' не найдена!")
        return

    files = [f for f in os.listdir(SOURCE_DIR) if f.startswith('batch-') and f.endswith('.txt')]
    
    if not files:
        print(f"В папке '{SOURCE_DIR}' не найдено файлов, начинающихся на 'batch-'")
        return

    files.sort(key=extract_numbers)
    
    global_question_counter = 1
    output_blocks = []
    
    for filename in files:
        print(f"Обработка файла: {filename}")
        full_path = os.path.join(SOURCE_DIR, filename)
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Улучшенный split: делим по переносам строк перед кавычкой или маркером
        blocks = re.split(r'(?=\n(?:\"|\-\d+\-))', content.strip())
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
                
            # Проверяем маркер пропуска (например, "-7-")
            missing_match = re.match(r'^-(\d+)-$', block)
            if missing_match:
                missing_num = int(missing_match.group(1))
                if global_question_counter < missing_num:
                    global_question_counter = missing_num
                output_blocks.append(f"-{missing_num}-")
                global_question_counter += 1
                continue
                
            # Проверяем, есть ли уже нумерация у вопроса
            numbered_match = re.match(r'^(\d+)\.\s*\"', block)
            
            if numbered_match:
                current_num = int(numbered_match.group(1))
                global_question_counter = current_num
                output_blocks.append(block)
            else:
                if block.startswith('"'):
                    formatted_block = f"{global_question_counter}. {block}"
                    output_blocks.append(formatted_block)
                else:
                    output_blocks.append(block)
            
            global_question_counter += 1

    # Гарантируем, что папка назначения существует
    os.makedirs(os.path.dirname(DEST_PATH), exist_ok=True)

    # Записываем строго с фиксированным двойным переносом между блоками
    with open(DEST_PATH, 'w', encoding='utf-8') as out_f:
        out_f.write("\n\n".join(output_blocks))
        
    print(f"\nГотово! Файл успешно сохранен в: {DEST_PATH}")

def find_questions_without_answers(filename):
    """Функция поиска вопросов без знака '+'"""
    if not os.path.exists(filename):
        print(f"Ошибка: Файл '{filename}' не найден для проверки.")
        return

    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

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

    if unanswered_questions:
        print(f"\nНайдено вопросов без отмеченного ответа: {len(unanswered_questions)}")
        print(f"Номера: {unanswered_questions}")
    else:
        print("\nВезет! Во всех вопросах есть правильный ответ.")

if __name__ == "__main__":
    process_and_merge()
    # Теперь вызываем проверку по корректному пути переменной DEST_PATH
    find_questions_without_answers(DEST_PATH)