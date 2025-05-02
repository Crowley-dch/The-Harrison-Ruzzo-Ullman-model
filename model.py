import sqlite3

class HRUDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('hru_model.db')
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES subjects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permissions (
                subject_id INTEGER NOT NULL,
                object_id INTEGER NOT NULL,
                read INTEGER DEFAULT 0,
                write INTEGER DEFAULT 0,
                own INTEGER DEFAULT 0,
                PRIMARY KEY (subject_id, object_id),
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (object_id) REFERENCES objects(id)
            )
        ''')

        self.conn.commit()

    def create_subject(self, name):
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
            self.conn.commit()
            return True, f"Субъект {name} создан"
        except sqlite3.IntegrityError:
            return False, f"Субъект {name} уже существует"

    def delete_subject(self, name):
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM subjects WHERE name=?", (name,))
        subject = cursor.fetchone()
        if not subject:
            return False, f"Субъект {name} не существует"

        cursor.execute("SELECT id FROM subjects WHERE id != ? LIMIT 1", (subject[0],))
        new_owner = cursor.fetchone()

        if new_owner:
            cursor.execute(
                "UPDATE objects SET owner_id=? WHERE owner_id=?",
                (new_owner[0], subject[0])
            )
            cursor.execute(
                "UPDATE permissions SET own=1 WHERE object_id IN (SELECT id FROM objects WHERE owner_id=?)",
                (new_owner[0],)
            )

        cursor.execute("DELETE FROM subjects WHERE id=?", (subject[0],))
        self.conn.commit()
        return True, f"Субъект {name} удален"

    def create_object(self, object_name, owner_name):
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM subjects WHERE name=?", (owner_name,))
        owner = cursor.fetchone()
        if not owner:
            return False, f"Субъект-владелец {owner_name} не существует"

        try:
            cursor.execute(
                "INSERT INTO objects (name, owner_id) VALUES (?, ?)",
                (object_name, owner[0])
            )
            object_id = cursor.lastrowid

            cursor.execute(
                """INSERT INTO permissions 
                   (subject_id, object_id, read, write, own) 
                   VALUES (?, ?, ?, ?, ?)""",
                (owner[0], object_id, 1, 1, 1)
            )

            self.conn.commit()
            return True, f"Объект {object_name} создан с владельцем {owner_name}"
        except sqlite3.IntegrityError:
            return False, f"Объект {object_name} уже существует"

    def delete_object(self, object_name, subject_name):
        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT o.id FROM objects o
               JOIN permissions p ON o.id = p.object_id
               JOIN subjects s ON p.subject_id = s.id
               WHERE o.name = ? AND s.name = ? AND p.own = 1""",
            (object_name, subject_name)
        )
        if not cursor.fetchone():
            return False, "Нет прав на удаление объекта или объект не существует"

        cursor.execute("DELETE FROM permissions WHERE object_id = (SELECT id FROM objects WHERE name = ?)",
                       (object_name,))
        cursor.execute("DELETE FROM objects WHERE name=?", (object_name,))
        self.conn.commit()
        return True, f"Объект {object_name} удален"

    def grant_right(self, grantor_name, recipient_name, object_name, right):
        if right not in ['read', 'write', 'own']:
            return False, "Некорректное право"

        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT 1 FROM permissions p
               JOIN subjects s1 ON p.subject_id = s1.id
               JOIN subjects s2 ON s2.name = ?
               JOIN objects o ON p.object_id = o.id AND o.name = ?
               WHERE s1.name = ? AND p.own = 1""",
            (recipient_name, object_name, grantor_name)
        )
        if not cursor.fetchone():
            return False, "Нет прав на передачу или субъект/объект не существует"

        cursor.execute(
            """SELECT 1 FROM permissions p
               JOIN subjects s ON p.subject_id = s.id
               JOIN objects o ON p.object_id = o.id
               WHERE s.name = ? AND o.name = ?""",
            (recipient_name, object_name)
        )

        if cursor.fetchone():
            cursor.execute(
                f"""UPDATE permissions SET {right} = 1
                    WHERE subject_id = (SELECT id FROM subjects WHERE name = ?)
                    AND object_id = (SELECT id FROM objects WHERE name = ?)""",
                (recipient_name, object_name)
            )
        else:
            cursor.execute(
                f"""INSERT INTO permissions 
                    (subject_id, object_id, {right})
                    VALUES (
                        (SELECT id FROM subjects WHERE name = ?),
                        (SELECT id FROM objects WHERE name = ?),
                        1
                    )""",
                (recipient_name, object_name)
            )

        self.conn.commit()
        return True, f"Право {right} на {object_name} передано от {grantor_name} к {recipient_name}"

    def revoke_right(self, revoker_name, target_name, object_name, right):
        if right not in ['read', 'write', 'own']:
            return False, "Некорректное право"

        cursor = self.conn.cursor()

        cursor.execute(
            """SELECT 1 FROM permissions p
               JOIN subjects s1 ON p.subject_id = s1.id
               JOIN subjects s2 ON s2.name = ?
               JOIN objects o ON p.object_id = o.id AND o.name = ?
               WHERE s1.name = ? AND p.own = 1""",
            (target_name, object_name, revoker_name)
        )
        if not cursor.fetchone():
            return False, "Нет прав на отзыв или субъект/объект не существует"

        if right == 'own':
            cursor.execute(
                """SELECT COUNT(*) FROM permissions p
                   JOIN objects o ON p.object_id = o.id
                   WHERE o.name = ? AND p.own = 1""",
                (object_name,)
            )
            if cursor.fetchone()[0] <= 1:
                return False, "Нельзя отозвать последнее право владения"

        cursor.execute(
            f"""UPDATE permissions SET {right} = 0
                WHERE subject_id = (SELECT id FROM subjects WHERE name = ?)
                AND object_id = (SELECT id FROM objects WHERE name = ?)""",
            (target_name, object_name)
        )

        self.conn.commit()
        return True, f"Право {right} на {object_name} отозвано у {target_name}"

    def get_subjects(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM subjects ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def get_objects(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM objects ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def get_rights(self, subject_name=None, object_name=None):
        cursor = self.conn.cursor()

        if subject_name and object_name:
            cursor.execute(
                """SELECT p.read, p.write, p.own
                   FROM permissions p
                   JOIN subjects s ON p.subject_id = s.id
                   JOIN objects o ON p.object_id = o.id
                   WHERE s.name = ? AND o.name = ?""",
                (subject_name, object_name)
            )
            result = cursor.fetchone()
            if not result:
                return None
            return {
                'read': bool(result[0]),
                'write': bool(result[1]),
                'own': bool(result[2])
            }
        elif subject_name:
            cursor.execute(
                """SELECT o.name, p.read, p.write, p.own
                   FROM permissions p
                   JOIN subjects s ON p.subject_id = s.id
                   JOIN objects o ON p.object_id = o.id
                   WHERE s.name = ?""",
                (subject_name,)
            )
            return [
                {
                    'object': row[0],
                    'read': bool(row[1]),
                    'write': bool(row[2]),
                    'own': bool(row[3])
                }
                for row in cursor.fetchall()
            ]
        elif object_name:
            cursor.execute(
                """SELECT s.name, p.read, p.write, p.own
                   FROM permissions p
                   JOIN subjects s ON p.subject_id = s.id
                   JOIN objects o ON p.object_id = o.id
                   WHERE o.name = ?""",
                (object_name,)
            )
            return [
                {
                    'subject': row[0],
                    'read': bool(row[1]),
                    'write': bool(row[2]),
                    'own': bool(row[3])
                }
                for row in cursor.fetchall()
            ]
        else:
            return None

    def display_rights(self, subject_name=None, object_name=None):
        rights = self.get_rights(subject_name, object_name)
        if rights is None:
            print("Нет данных для отображения")
            return

        if subject_name and object_name:
            print(f"\nПрава субъекта {subject_name} на объект {object_name}:")
            print(f"Чтение: {'Да' if rights['read'] else 'Нет'}")
            print(f"Запись: {'Да' if rights['write'] else 'Нет'}")
            print(f"Владение: {'Да' if rights['own'] else 'Нет'}")
        elif subject_name:
            print(f"\nВсе права субъекта {subject_name}:")
            print("{:<20} {:<10} {:<10} {:<10}".format("Объект", "Чтение", "Запись", "Владение"))
            for right in rights:
                print("{:<20} {:<10} {:<10} {:<10}".format(
                    right['object'],
                    'Да' if right['read'] else 'Нет',
                    'Да' if right['write'] else 'Нет',
                    'Да' if right['own'] else 'Нет'
                ))
        elif object_name:
            print(f"\nВсе права на объект {object_name}:")
            print("{:<20} {:<10} {:<10} {:<10}".format("Субъект", "Чтение", "Запись", "Владение"))
            for right in rights:
                print("{:<20} {:<10} {:<10} {:<10}".format(
                    right['subject'],
                    'Да' if right['read'] else 'Нет',
                    'Да' if right['write'] else 'Нет',
                    'Да' if right['own'] else 'Нет'
                ))

class HRUConsole:
    def __init__(self):
        self.db = HRUDatabase()
        self.run()

    def display_menu(self):
        print("\nМеню HRU модели:")
        print("1. Управление субъектами")
        print("2. Управление объектами")
        print("3. Управление правами")
        print("4. Просмотр прав")
        print("5. Выход")

    def run(self):
        while True:
            self.display_menu()
            choice = input("Выберите пункт меню: ")

            if choice == '1':
                self.manage_subjects()
            elif choice == '2':
                self.manage_objects()
            elif choice == '3':
                self.manage_rights()
            elif choice == '4':
                self.view_rights()
            elif choice == '5':
                print("Выход из программы")
                break
            else:
                print("Неверный выбор. Попробуйте снова.")

    def manage_subjects(self):
        while True:
            print("\nУправление субъектами:")
            print("1. Создать субъект")
            print("2. Удалить субъект")
            print("3. Список всех субъектов")
            print("4. Назад")

            choice = input("Выберите действие: ")

            if choice == '1':
                name = input("Введите имя нового субъекта: ").strip()
                if name:
                    success, message = self.db.create_subject(name)
                    print(message)
                else:
                    print("Имя субъекта не может быть пустым")
            elif choice == '2':
                subjects = self.db.get_subjects()
                if not subjects:
                    print("Нет субъектов для удаления")
                    continue

                print("Доступные субъекты:")
                for i, subject in enumerate(subjects, 1):
                    print(f"{i}. {subject}")

                try:
                    num = int(input("Выберите номер субъекта для удаления: "))
                    if 1 <= num <= len(subjects):
                        success, message = self.db.delete_subject(subjects[num-1])
                        print(message)
                    else:
                        print("Неверный номер")
                except ValueError:
                    print("Введите число")
            elif choice == '3':
                subjects = self.db.get_subjects()
                if subjects:
                    print("\nСписок субъектов:")
                    for subject in subjects:
                        print(subject)
                else:
                    print("Нет субъектов")
            elif choice == '4':
                break
            else:
                print("Неверный выбор")

    def manage_objects(self):
        while True:
            print("\nУправление объектами:")
            print("1. Создать объект")
            print("2. Удалить объект")
            print("3. Список всех объектов")
            print("4. Назад")

            choice = input("Выберите действие: ")

            if choice == '1':
                name = input("Введите имя нового объекта: ").strip()
                if not name:
                    print("Имя объекта не может быть пустым")
                    continue

                subjects = self.db.get_subjects()
                if not subjects:
                    print("Нет субъектов. Сначала создайте хотя бы одного субъекта.")
                    continue

                print("Доступные владельцы:")
                for i, subject in enumerate(subjects, 1):
                    print(f"{i}. {subject}")

                try:
                    num = int(input("Выберите номер владельца: "))
                    if 1 <= num <= len(subjects):
                        success, message = self.db.create_object(name, subjects[num-1])
                        print(message)
                    else:
                        print("Неверный номер")
                except ValueError:
                    print("Введите число")
            elif choice == '2':
                objects = self.db.get_objects()
                if not objects:
                    print("Нет объектов для удаления")
                    continue

                print("Доступные объекты:")
                for i, obj in enumerate(objects, 1):
                    print(f"{i}. {obj}")

                try:
                    num = int(input("Выберите номер объекта для удаления: "))
                    if not (1 <= num <= len(objects)):
                        print("Неверный номер")
                        continue

                    object_name = objects[num-1]
                    subjects = self.db.get_subjects()
                    print("Доступные субъекты для удаления:")
                    for i, subject in enumerate(subjects, 1):
                        print(f"{i}. {subject}")

                    num_subj = int(input("Выберите номер субъекта, который удаляет объект: "))
                    if 1 <= num_subj <= len(subjects):
                        success, message = self.db.delete_object(object_name, subjects[num_subj-1])
                        print(message)
                    else:
                        print("Неверный номер")
                except ValueError:
                    print("Введите число")
            elif choice == '3':
                objects = self.db.get_objects()
                if objects:
                    print("\nСписок объектов:")
                    for obj in objects:
                        print(obj)
                else:
                    print("Нет объектов")
            elif choice == '4':
                break
            else:
                print("Неверный выбор")

    def manage_rights(self):
        while True:
            print("\nУправление правами:")
            print("1. Передать право")
            print("2. Отозвать право")
            print("3. Назад")

            choice = input("Выберите действие: ")

            if choice == '1':
                self.grant_right()
            elif choice == '2':
                self.revoke_right()
            elif choice == '3':
                break
            else:
                print("Неверный выбор")

    def grant_right(self):
        subjects = self.db.get_subjects()
        if len(subjects) < 2:
            print("Нужно как минимум 2 субъекта для передачи прав")
            return

        objects = self.db.get_objects()
        if not objects:
            print("Нет объектов для управления правами")
            return

        print("Выберите владельца, который передает право:")
        for i, subject in enumerate(subjects, 1):
            print(f"{i}. {subject}")

        try:
            num_grantor = int(input("Номер владельца: "))
            if not (1 <= num_grantor <= len(subjects)):
                print("Неверный номер")
                return

            print("Выберите получателя права:")
            for i, subject in enumerate(subjects, 1):
                if i != num_grantor:
                    print(f"{i}. {subject}")

            num_recipient = int(input("Номер получателя: "))
            if not (1 <= num_recipient <= len(subjects)) or num_recipient == num_grantor:
                print("Неверный номер")
                return

            print("Выберите объект:")
            for i, obj in enumerate(objects, 1):
                print(f"{i}. {obj}")

            num_object = int(input("Номер объекта: "))
            if not (1 <= num_object <= len(objects)):
                print("Неверный номер")
                return

            print("Выберите право:")
            print("1. Чтение (read)")
            print("2. Запись (write)")
            print("3. Владение (own)")

            num_right = int(input("Номер права: "))
            if num_right == 1:
                right = 'read'
            elif num_right == 2:
                right = 'write'
            elif num_right == 3:
                right = 'own'
            else:
                print("Неверный номер")
                return

            grantor = subjects[num_grantor-1]
            recipient = subjects[num_recipient-1]
            object_name = objects[num_object-1]

            success, message = self.db.grant_right(grantor, recipient, object_name, right)
            print(message)
        except ValueError:
            print("Введите число")

    def revoke_right(self):
        subjects = self.db.get_subjects()
        if len(subjects) < 2:
            print("Нужно как минимум 2 субъекта для отзыва прав")
            return

        objects = self.db.get_objects()
        if not objects:
            print("Нет объектов для управления правами")
            return

        print("Выберите владельца, который отзывает право:")
        for i, subject in enumerate(subjects, 1):
            print(f"{i}. {subject}")

        try:
            num_revoker = int(input("Номер владельца: "))
            if not (1 <= num_revoker <= len(subjects)):
                print("Неверный номер")
                return

            print("Выберите субъекта, у которого отзывается право:")
            for i, subject in enumerate(subjects, 1):
                if i != num_revoker:
                    print(f"{i}. {subject}")

            num_target = int(input("Номер субъекта: "))
            if not (1 <= num_target <= len(subjects)) or num_target == num_revoker:
                print("Неверный номер")
                return

            print("Выберите объект:")
            for i, obj in enumerate(objects, 1):
                print(f"{i}. {obj}")

            num_object = int(input("Номер объекта: "))
            if not (1 <= num_object <= len(objects)):
                print("Неверный номер")
                return

            print("Выберите право для отзыва:")
            print("1. Чтение (read)")
            print("2. Запись (write)")
            print("3. Владение (own)")

            num_right = int(input("Номер права: "))
            if num_right == 1:
                right = 'read'
            elif num_right == 2:
                right = 'write'
            elif num_right == 3:
                right = 'own'
            else:
                print("Неверный номер")
                return

            revoker = subjects[num_revoker-1]
            target = subjects[num_target-1]
            object_name = objects[num_object-1]

            success, message = self.db.revoke_right(revoker, target, object_name, right)
            print(message)
        except ValueError:
            print("Введите число")

    def view_rights(self):
        while True:
            print("\nПросмотр прав:")
            print("1. Права конкретного субъекта")
            print("2. Права на конкретный объект")
            print("3. Права субъекта на объект")
            print("4. Назад")

            choice = input("Выберите действие: ")

            if choice == '1':
                subjects = self.db.get_subjects()
                if not subjects:
                    print("Нет субъектов")
                    continue

                print("Выберите субъект:")
                for i, subject in enumerate(subjects, 1):
                    print(f"{i}. {subject}")

                try:
                    num = int(input("Номер субъекта: "))
                    if 1 <= num <= len(subjects):
                        self.db.display_rights(subject_name=subjects[num-1])
                    else:
                        print("Неверный номер")
                except ValueError:
                    print("Введите число")
            elif choice == '2':
                objects = self.db.get_objects()
                if not objects:
                    print("Нет объектов")
                    continue

                print("Выберите объект:")
                for i, obj in enumerate(objects, 1):
                    print(f"{i}. {obj}")

                try:
                    num = int(input("Номер объекта: "))
                    if 1 <= num <= len(objects):
                        self.db.display_rights(object_name=objects[num-1])
                    else:
                        print("Неверный номер")
                except ValueError:
                    print("Введите число")
            elif choice == '3':
                subjects = self.db.get_subjects()
                if not subjects:
                    print("Нет субъектов")
                    continue

                objects = self.db.get_objects()
                if not objects:
                    print("Нет объектов")
                    continue

                print("Выберите субъект:")
                for i, subject in enumerate(subjects, 1):
                    print(f"{i}. {subject}")

                num_subj = int(input("Номер субъекта: "))
                if not (1 <= num_subj <= len(subjects)):
                    print("Неверный номер")
                    continue

                print("Выберите объект:")
                for i, obj in enumerate(objects, 1):
                    print(f"{i}. {obj}")

                num_obj = int(input("Номер объекта: "))
                if 1 <= num_obj <= len(objects):
                    self.db.display_rights(
                        subject_name=subjects[num_subj-1],
                        object_name=objects[num_obj-1]
                    )
                else:
                    print("Неверный номер")
            elif choice == '4':
                break
            else:
                print("Неверный выбор")

if __name__ == '__main__':
    HRUConsole()