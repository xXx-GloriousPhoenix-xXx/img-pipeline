import os
import re
from pathlib import Path

SOURCE_DIR = Path("./result/batches")
DEST_PATH = Path("./result/merged.txt")

def extract_numbers(filename):
    """Извлекает n и m из имени файла batch-n-m.txt для правильной сортировки."""
    match = re.match(r"batch-(\d+)-(\d+)\.txt", filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return (float('inf'), float('inf'))

def process_and_merge():
    if not SOURCE_DIR.exists():
        print(f"Ошибка: Папка '{SOURCE_DIR}' не найдена!")
        return

    # Читаем только файлы, подходящие под маску
    files = [f for f in os.listdir(SOURCE_DIR) if f.startswith('batch-') and f.endswith('.txt')]
    
    if not files:
        print(f"В папке '{SOURCE_DIR}' не найдено файлов 'batch-*.txt'")
        return

    # Сортируем по числам n и m
    files.sort(key=extract_numbers)
    
    global_question_counter = 1
    output_blocks = []
    
    for filename in files:
        print(f"Обработка файла: {filename}")
        file_path = SOURCE_DIR / filename
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Делим текст на блоки (вопросы или маркеры пропусков)
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

    # Создаем папку result, если её нет
    DEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Сохраняем с красивыми двойными переносами между вопросами
    with open(DEST_PATH, 'w', encoding='utf-8') as out_f:
        out_f.write("\n\n".join(output_blocks))
        
    print(f"\nСлияние завершено! Файл сохранен в: {DEST_PATH}")

if __name__ == "__main__":
    process_and_merge()