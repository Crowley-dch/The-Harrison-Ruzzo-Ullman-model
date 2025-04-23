import sys
import sqlite3
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTabWidget, QTableWidget,
                             QTableWidgetItem, QMessageBox, QComboBox, QGroupBox)


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


class HRUGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = HRUDatabase()
        self.init_ui()
        self.update_lists()

    def init_ui(self):
        self.setWindowTitle('Модель HRU (Харрисона-Руззо-Ульмана)')
        self.setGeometry(100, 100, 800, 600)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.create_subject_tab()
        self.create_object_tab()
        self.create_rights_tab()
        self.create_view_tab()

        self.update_lists()

    def create_subject_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Управление субъектами")

        group_create = QGroupBox("Создать субъект")
        layout_create = QVBoxLayout()
        group_create.setLayout(layout_create)

        self.subject_name_input = QLineEdit()
        self.subject_name_input.setPlaceholderText("Имя субъекта")
        layout_create.addWidget(self.subject_name_input)

        btn_create = QPushButton("Создать")
        btn_create.clicked.connect(self.create_subject)
        layout_create.addWidget(btn_create)

        layout.addWidget(group_create)

        group_delete = QGroupBox("Удалить субъект")
        layout_delete = QVBoxLayout()
        group_delete.setLayout(layout_delete)

        self.subject_delete_combo = QComboBox()
        layout_delete.addWidget(self.subject_delete_combo)

        btn_delete = QPushButton("Удалить")
        btn_delete.clicked.connect(self.delete_subject)
        layout_delete.addWidget(btn_delete)

        layout.addWidget(group_delete)

    def create_object_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Управление объектами")

        group_create = QGroupBox("Создать объект")
        layout_create = QVBoxLayout()
        group_create.setLayout(layout_create)

        self.object_name_input = QLineEdit()
        self.object_name_input.setPlaceholderText("Имя объекта")
        layout_create.addWidget(self.object_name_input)

        self.object_owner_combo = QComboBox()
        layout_create.addWidget(QLabel("Владелец:"))
        layout_create.addWidget(self.object_owner_combo)

        btn_create = QPushButton("Создать")
        btn_create.clicked.connect(self.create_object)
        layout_create.addWidget(btn_create)

        layout.addWidget(group_create)

        group_delete = QGroupBox("Удалить объект")
        layout_delete = QVBoxLayout()
        group_delete.setLayout(layout_delete)

        self.object_delete_combo = QComboBox()
        layout_delete.addWidget(self.object_delete_combo)

        self.object_deleter_combo = QComboBox()
        layout_delete.addWidget(QLabel("Субъект, удаляющий объект:"))
        layout_delete.addWidget(self.object_deleter_combo)

        btn_delete = QPushButton("Удалить")
        btn_delete.clicked.connect(self.delete_object)
        layout_delete.addWidget(btn_delete)

        layout.addWidget(group_delete)

    def create_rights_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Управление правами")

        group_grant = QGroupBox("Передать право")
        layout_grant = QVBoxLayout()
        group_grant.setLayout(layout_grant)

        self.grantor_combo = QComboBox()
        layout_grant.addWidget(QLabel("Кто передает (владелец):"))
        layout_grant.addWidget(self.grantor_combo)

        self.recipient_combo = QComboBox()
        layout_grant.addWidget(QLabel("Кому передается:"))
        layout_grant.addWidget(self.recipient_combo)

        self.object_grant_combo = QComboBox()
        layout_grant.addWidget(QLabel("Объект:"))
        layout_grant.addWidget(self.object_grant_combo)

        self.right_combo = QComboBox()
        self.right_combo.addItems(['read', 'write', 'own'])
        layout_grant.addWidget(QLabel("Право:"))
        layout_grant.addWidget(self.right_combo)

        btn_grant = QPushButton("Передать право")
        btn_grant.clicked.connect(self.grant_right)
        layout_grant.addWidget(btn_grant)

        layout.addWidget(group_grant)

        group_revoke = QGroupBox("Отозвать право")
        layout_revoke = QVBoxLayout()
        group_revoke.setLayout(layout_revoke)

        self.revoker_combo = QComboBox()
        layout_revoke.addWidget(QLabel("Кто отзывает (владелец):"))
        layout_revoke.addWidget(self.revoker_combo)

        self.target_combo = QComboBox()
        layout_revoke.addWidget(QLabel("У кого отзывается:"))
        layout_revoke.addWidget(self.target_combo)

        self.object_revoke_combo = QComboBox()
        layout_revoke.addWidget(QLabel("Объект:"))
        layout_revoke.addWidget(self.object_revoke_combo)

        self.right_revoke_combo = QComboBox()
        self.right_revoke_combo.addItems(['read', 'write', 'own'])
        layout_revoke.addWidget(QLabel("Право:"))
        layout_revoke.addWidget(self.right_revoke_combo)

        btn_revoke = QPushButton("Отозвать право")
        btn_revoke.clicked.connect(self.revoke_right)
        layout_revoke.addWidget(btn_revoke)

        layout.addWidget(group_revoke)

    def create_view_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Просмотр прав")

        self.view_mode = QComboBox()
        self.view_mode.addItems(["Права субъекта", "Права на объект"])
        self.view_mode.currentIndexChanged.connect(self.update_view)
        layout.addWidget(self.view_mode)

        self.view_selector = QComboBox()
        layout.addWidget(self.view_selector)

        self.rights_table = QTableWidget()
        self.rights_table.setColumnCount(4)
        self.rights_table.setHorizontalHeaderLabels(["Имя", "Чтение", "Запись", "Владение"])
        self.rights_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.rights_table)

        btn_refresh = QPushButton("Обновить")
        btn_refresh.clicked.connect(self.update_view)
        layout.addWidget(btn_refresh)

    def update_lists(self):
        subjects = self.db.get_subjects()

        self.subject_delete_combo.clear()
        self.subject_delete_combo.addItems(subjects)

        self.object_owner_combo.clear()
        self.object_owner_combo.addItems(subjects)

        self.grantor_combo.clear()
        self.grantor_combo.addItems(subjects)

        self.recipient_combo.clear()
        self.recipient_combo.addItems(subjects)

        self.revoker_combo.clear()
        self.revoker_combo.addItems(subjects)

        self.target_combo.clear()
        self.target_combo.addItems(subjects)

        self.object_deleter_combo.clear()
        self.object_deleter_combo.addItems(subjects)

        objects = self.db.get_objects()

        self.object_delete_combo.clear()
        self.object_delete_combo.addItems(objects)

        self.object_grant_combo.clear()
        self.object_grant_combo.addItems(objects)

        self.object_revoke_combo.clear()
        self.object_revoke_combo.addItems(objects)

        self.update_view_selector()

    def update_view_selector(self):
        self.view_selector.clear()
        if self.view_mode.currentIndex() == 0:  # Права субъекта
            self.view_selector.addItems(self.db.get_subjects())
        else:  
            self.view_selector.addItems(self.db.get_objects())

    def update_view(self):
        self.update_view_selector()

        if self.view_mode.currentIndex() == 0:  # Права субъекта
            subject = self.view_selector.currentText()
            rights = self.db.get_rights(subject_name=subject)

            self.rights_table.setRowCount(len(rights))
            for i, right in enumerate(rights):
                self.rights_table.setItem(i, 0, QTableWidgetItem(right['object']))
                self.rights_table.setItem(i, 1, QTableWidgetItem("✓" if right['read'] else "✗"))
                self.rights_table.setItem(i, 2, QTableWidgetItem("✓" if right['write'] else "✗"))
                self.rights_table.setItem(i, 3, QTableWidgetItem("✓" if right['own'] else "✗"))
        else:
            object_name = self.view_selector.currentText()
            rights = self.db.get_rights(object_name=object_name)

            self.rights_table.setRowCount(len(rights))
            for i, right in enumerate(rights):
                self.rights_table.setItem(i, 0, QTableWidgetItem(right['subject']))
                self.rights_table.setItem(i, 1, QTableWidgetItem("✓" if right['read'] else "✗"))
                self.rights_table.setItem(i, 2, QTableWidgetItem("✓" if right['write'] else "✗"))
                self.rights_table.setItem(i, 3, QTableWidgetItem("✓" if right['own'] else "✗"))

    def create_subject(self):
        name = self.subject_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите имя субъекта")
            return

        success, message = self.db.create_subject(name)
        if success:
            self.subject_name_input.clear()
            self.update_lists()
        QMessageBox.information(self, "Результат", message)

    def delete_subject(self):
        name = self.subject_delete_combo.currentText()
        if not name:
            return

        reply = QMessageBox.question(
            self, 'Подтверждение',
            f"Вы уверены, что хотите удалить субъект {name}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            success, message = self.db.delete_subject(name)
            if success:
                self.update_lists()
            QMessageBox.information(self, "Результат", message)

    def create_object(self):
        name = self.object_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите имя объекта")
            return

        owner = self.object_owner_combo.currentText()
        if not owner:
            QMessageBox.warning(self, "Ошибка", "Выберите владельца")
            return

        success, message = self.db.create_object(name, owner)
        if success:
            self.object_name_input.clear()
            self.update_lists()
        QMessageBox.information(self, "Результат", message)

    def delete_object(self):
        object_name = self.object_delete_combo.currentText()
        subject_name = self.object_deleter_combo.currentText()
        if not object_name or not subject_name:
            return

        reply = QMessageBox.question(
            self, 'Подтверждение',
            f"Вы уверены, что хотите удалить объект {object_name}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            success, message = self.db.delete_object(object_name, subject_name)
            if success:
                self.update_lists()
            QMessageBox.information(self, "Результат", message)

    def grant_right(self):
        grantor = self.grantor_combo.currentText()
        recipient = self.recipient_combo.currentText()
        object_name = self.object_grant_combo.currentText()
        right = self.right_combo.currentText()

        if not all([grantor, recipient, object_name]):
            QMessageBox.warning(self, "Ошибка", "Заполните все поля")
            return

        success, message = self.db.grant_right(grantor, recipient, object_name, right)
        if success:
            self.update_view()
        QMessageBox.information(self, "Результат", message)

    def revoke_right(self):
        revoker = self.revoker_combo.currentText()
        target = self.target_combo.currentText()
        object_name = self.object_revoke_combo.currentText()
        right = self.right_revoke_combo.currentText()

        if not all([revoker, target, object_name]):
            QMessageBox.warning(self, "Ошибка", "Заполните все поля")
            return

        success, message = self.db.revoke_right(revoker, target, object_name, right)
        if success:
            self.update_view()
        QMessageBox.information(self, "Результат", message)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = HRUGUI()
    window.show()
    sys.exit(app.exec_())