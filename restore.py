import re
from pathlib import Path

# Налаштування шляхів до файлів
MERGED_FILE = Path("./result/merged.txt")
ABSENT_FILE = Path("./result/restore/absent.txt")
OUTPUT_FILE = Path("./result/restored.txt")  # Новий файл, щоб не затерти оригінал випадково

def load_absent_questions():
    """Зчитує absent.txt і повертає словник {номер_питання: повний_текст_блоку}"""
    if not ABSENT_FILE.exists():
        print(f"Помилка: Файл із відсутніми питаннями '{ABSENT_FILE}' не знайдено!")
        return {}

    with open(ABSENT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ділимо файл на блоки, кожен з яких починається з "Номер. "Вопрос""
    blocks = re.split(r'(?=\n\d+\.\s*\")', "\n" + content.strip())
    questions_dict = {}

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Знаходимо номер запитання на початку блоку
        match_num = re.match(r'^(\d+)\.', block)
        if match_num:
            q_num = int(match_num.group(1))
            questions_dict[q_num] = block

    return questions_dict

def restore_questions():
    if not MERGED_FILE.exists():
        print(f"Помилка: Файл '{MERGED_FILE}' не знайдено! Спочатку запустіть merge.py")
        return

    # Завантажуємо питання для вставки
    absent_questions = load_absent_questions()
    if not absent_questions:
        print("Нічого відновлювати. Перевірте вміст absent.txt.")
        return

    print(f"Завантажено питань для відновлення: {len(absent_questions)} шт. (Номери: {list(absent_questions.keys())})")

    with open(MERGED_FILE, 'r', encoding='utf-8') as f:
        merged_content = f.read()

    # Ділимо merged.txt на блоки (питання або заглушки), зберігаючи саму розмітку розділення
    # Розділяємо через re.split, використовуючи групи, щоб не загубити самі маркери
    blocks = re.split(r'(?=\n(?:\"|\-\d+\-|\d+\.\s*\"))', merged_content.strip())
    
    restored_blocks = []
    restored_count = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Перевіряємо, чи є поточний блок заглушкою типу -7- чи -10-
        missing_match = re.match(r'^-(\d+)-$', block)
        if missing_match:
            q_num = int(missing_match.group(1))
            
            # Якщо для цієї заглушки є питання у словнику — вставляємо його
            if q_num in absent_questions:
                restored_blocks.append(absent_questions[q_num])
                restored_count += 1
                print(f"Успішно відновлено питання №{q_num}")
            else:
                # Якщо питання в absent.txt не знайшлося, залишаємо заглушку як є
                restored_blocks.append(block)
                print(f"⚠️ Попередження: Заглушка -{q_num}- знайдена в merged.txt, але для неї немає тексту в absent.txt")
        else:
            # Якщо це звичайне питання, просто залишаємо його без змін
            restored_blocks.append(block)

    # Зберігаємо результат у новий файл (або можете змінити OUTPUT_FILE на MERGED_FILE, якщо хочете перезаписати оригінал)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        out_f.write("\n\n".join(restored_blocks))

    print(f"\nГотово! Відновлено питань: {restored_count}. Результат збережено у: {OUTPUT_FILE}")

if __name__ == "__main__":
    restore_questions()