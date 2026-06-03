import os
import re

SOURCE_DIR = "./result/batches" 
DEST_PATH = "./result/merged.txt"

def extract_numbers(filename):
    """Извлекает n и m из чистого имени файла batch-n-m.txt для правильной сортировки."""
    # os.listdir возвращает только имя файла, например "batch-1-2.txt"
    match = re.match(r"batch-(\d+)-(\d+)\.txt", filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return (float('inf'), float('inf'))

def process_and_merge():
    # Проверяем, существует ли папка
    if not os.path.exists(SOURCE_DIR):
        print(f"Ошибка: Папка '{SOURCE_DIR}' не найдена!")
        return

    # Находим файлы в нужной папке
    files = [f for f in os.listdir(SOURCE_DIR) if f.startswith('batch-') and f.endswith('.txt')]
    
    if not files:
        print(f"В папке '{SOURCE_DIR}' не найдено файлов, начинающихся на 'batch-' и с расширением '.txt'")
        return

    # Сортируем их по n и m
    files.sort(key=extract_numbers)
    
    global_question_counter = 1
    output_lines = []
    
    for filename in files:
        print(f"Обработка файла: {filename}")
        # Читаем файл, склеивая путь к папке и имя файла
        full_path = os.path.join(SOURCE_DIR, filename)
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Разбиваем файл на блоки по вопросам или маркерам пропусков
        blocks = re.split(r'(?=\n(?:\"|\-\d+\-))', content.strip())
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
                
            # Проверяем маркер пропуска (например, "-10-")
            missing_match = re.match(r'^-(\d+)-$', block)
            if missing_match:
                missing_num = int(missing_match.group(1))
                if global_question_counter < missing_num:
                    global_question_counter = missing_num
                output_lines.append(f"\n-{missing_num}-\n")
                # Здесь убираем прибавление счетчика в конце цикла для пропуска,
                # чтобы следующий вопрос стал именно missing_num + 1
                global_question_counter += 1
                continue
                
            # Проверяем, есть ли уже нумерация у вопроса
            numbered_match = re.match(r'^(\d+)\.\s*\"', block)
            
            if numbered_match:
                current_num = int(numbered_match.group(1))
                global_question_counter = current_num
                output_lines.append(block)
            else:
                if block.startswith('"'):
                    formatted_block = f"{global_question_counter}. {block}"
                    output_lines.append(formatted_block)
                else:
                    output_lines.append(block)
            
            global_question_counter += 1

    # Записываем результат в итоговый файл рядом со скриптом
    with open(DEST_PATH, 'w', encoding='utf-8') as out_f:
        out_f.write("\n\n".join(output_lines))
        
    print("\nГотово!")

if __name__ == "__main__":
    process_and_merge()