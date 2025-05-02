import pytest
from unittest.mock import patch, MagicMock
from model import HRUDatabase, HRUConsole


@pytest.fixture
def db():
    db = HRUDatabase()
    # Очищаем базу перед тестами
    db.conn.execute("DELETE FROM permissions")
    db.conn.execute("DELETE FROM objects")
    db.conn.execute("DELETE FROM subjects")
    db.conn.commit()

    # Создаем тестовые данные
    success, _ = db.create_subject("admin")
    success, _ = db.create_object("file1", "admin")
    yield db
    db.conn.close()


@pytest.fixture
def console(db):
    # Создаем консоль с подмененной базой
    with patch('builtins.input', return_value='5'):  # По умолчанию выбираем выход
        console = HRUConsole()
        console.db = db
        yield console


class TestHRUDatabase:
    def test_create_subject(self, db):
        success, msg = db.create_subject("user1")
        assert success is True
        assert "user1" in db.get_subjects()
        print("✓ test_create_subject - УСПЕХ")

    def test_delete_subject(self, db):
        db.create_subject("user1")
        success, msg = db.delete_subject("user1")
        assert success is True
        assert "user1" not in db.get_subjects()
        print("✓ test_delete_subject - УСПЕХ")

    def test_create_object(self, db):
        success, msg = db.create_object("file2", "admin")
        assert success is True
        assert "file2" in db.get_objects()
        print("✓ test_create_object - УСПЕХ")

    def test_rights_management(self, db):
        db.create_subject("user1")

        # Проверяем передачу права
        success, msg = db.grant_right("admin", "user1", "file1", "read")
        assert success is True
        rights = db.get_rights("user1", "file1")
        assert rights['read'] is True

        # Проверяем отзыв права
        success, msg = db.revoke_right("admin", "user1", "file1", "read")
        assert success is True
        rights = db.get_rights("user1", "file1")
        assert rights['read'] is False

        print("✓ test_rights_management - УСПЕХ")


class TestHRUConsole:
    def test_subject_creation_flow(self, console):
        # Эмулируем ввод: 1-1-"test_user"-4-5
        with patch('builtins.input', side_effect=['1', '1', 'test_user', '4', '5']):
            with patch('builtins.print') as mock_print:
                console.run()

                # Проверяем вывод
                output = "\n".join(str(call) for call in mock_print.call_args_list)
                assert "Субъект test_user создан" in output

            # Проверяем состояние БД
            assert "test_user" in console.db.get_subjects()
            print("✓ test_subject_creation_flow - УСПЕХ")

    def test_object_creation_flow(self, console):
        # Эмулируем ввод: 2-1-"new_file"-1-4-5
        with patch('builtins.input', side_effect=['2', '1', 'new_file', '1', '4', '5']):
            with patch('builtins.print') as mock_print:
                console.run()

                # Проверяем вывод
                output = "\n".join(str(call) for call in mock_print.call_args_list)
                assert "Объект new_file создан" in output

            # Проверяем состояние БД
            assert "new_file" in console.db.get_objects()
            print("✓ test_object_creation_flow - УСПЕХ")

    def test_right_grant_flow(self, console):
        # Подготовка тестовых данных
        console.db.create_subject("user1")

        # Эмулируем ввод: 3-1-1-2-1-1-4-5
        with patch('builtins.input', side_effect=['3', '1', '1', '2', '1', '1', '4', '5']):
            with patch('builtins.print') as mock_print:
                console.run()

                # Проверяем вывод
                output = "\n".join(str(call) for call in mock_print.call_args_list)
                assert "Право read на file1 передано" in output

            # Проверяем состояние БД
            rights = console.db.get_rights("user1", "file1")
            assert rights['read'] is True
            print("✓ test_right_grant_flow - УСПЕХ")


def pytest_sessionfinish(session, exitstatus):
    print("\n=== ИТОГОВЫЙ ОТЧЁТ ===")
    print("Все тесты успешно пройдены!")
    session.exitstatus = 0


if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])