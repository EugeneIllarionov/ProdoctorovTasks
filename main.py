import json
import sys
import time
import timeit
from jsonschema import validate, ValidationError
from datetime import datetime
from pathlib import Path
import requests


class Program:
    users_url = r'https://json.medrating.org/users'
    todos_url = r'https://json.medrating.org/todos'

    users_local = r'test_data/users.json'
    todos_local = r'test_data/todos.json'

    def __init__(self):
        self.check_folders()
        self.todo_schema = self.simple_json_load(r'test_data/todo.schema')
        self.user_schema = self.simple_json_load(r'test_data/user.schema')
        self._warnings = list()

    def save_warnings(self):
        fname = rf'warnings/{datetime.now().strftime("%Y.%m.%d %H %M")}.txt'
        file = Path(fname)
        if file.exists():
            return

        with file.open('w', encoding='utf-8') as file:
            file.write('/n'.join(self._warnings))

    @staticmethod
    def save_errors(errors):
        fname = rf'errors/{datetime.now().strftime("%Y.%m.%d %H %M")}.txt'
        file = Path(fname)
        if file.exists():
            return

        with file.open('w', encoding='utf-8') as file:
            file.write('/n'.join(errors))

    @staticmethod
    def simple_json_load(fname):
        with open(fname) as json_file:
            return json.load(json_file)

    def simple_validate(self, json, schema):
        valid_data = list()
        wrong_data = list()
        for num, element in enumerate(json):
            try:
                validate(instance=element, schema=schema)
                valid_data.append(element)
            except ValidationError as err:
                self._warnings.append(f'schema validation error on element: {element}\nError:{err}\n')
                wrong_data.append(element)
        return valid_data, wrong_data

    @staticmethod
    def check_folders():
        """
        create tasks and tasks/warnings, tasks/errors folders if not exist
        """
        Path("tasks").mkdir(parents=True, exist_ok=True)
        Path("warnings").mkdir(parents=True, exist_ok=True)
        Path("errors").mkdir(parents=True, exist_ok=True)

    # get user _todo names by filter json file
    @staticmethod
    def get_user_todo_names(user_id: int, todo_list: list) -> (list, list):

        completed_todo, uncompleted_todo = list(), list()

        for todo in todo_list:
            if int(todo["userId"]) == user_id:
                title = todo["title"]
                if len(title) > 48:
                    title = f'{title[:48]}...'
                if todo["completed"] is True:
                    completed_todo.append(title)
                else:
                    uncompleted_todo.append(title)
        return completed_todo, uncompleted_todo

    # get user _todo names by request with params
    def get_user_todo_names_request(self, user_id):
        user_id = str(user_id)

        try:
            completed_todo = requests.get(self.todos_url, params={"userId": user_id, "completed": 'true'}).json()
            completed_todo = self.simple_validate(completed_todo, self.todo_schema)[0]
            completed_todo = [f'{todo["title"][:48]}...' if len(todo["title"]) > 48
                              else todo["title"] for todo in completed_todo]

            uncompleted_todo = requests.get(self.todos_url, params={"userId": user_id, "completed": 'false'}).json()
            uncompleted_todo = self.simple_validate(uncompleted_todo, self.todo_schema)[0]
            uncompleted_todo = [f'{todo["title"][:48]}...' if len(todo["title"]) > 48
                                else todo["title"] for todo in uncompleted_todo]

        except requests.exceptions.RequestException as e:
            self.save_errors(str(e))
            raise SystemExit(e)
        return completed_todo, uncompleted_todo

    @classmethod
    def create_text_report(cls, user, user_todo):
        nl = '\n'
        completed_todo, uncompleted_todo = user_todo
        report = f'Отчёт для {user["company"]["name"]}.\n' \
                 f'{user["name"]} <{user["email"]}> {datetime.now().strftime("%d.%m.%Y %H:%M")}\n' \
                 f'Всего задач: {len(completed_todo) + len(uncompleted_todo)}\n\n' \
                 f'Завершённые задачи({len(completed_todo)}):\n' \
                 f'{nl.join(completed_todo)}' \
                 f'\n\n' \
                 f'Оставшиеся задачи ({len(uncompleted_todo)}):\n' \
                 f'{nl.join(uncompleted_todo)}'

        return report

    @staticmethod
    def rename_old_report(file):
        if file.exists():
            created_time = file.stat().st_mtime
            created_datetime = datetime.fromtimestamp(created_time).strftime("%Y-%m-%dT%H-%M")
            old_file_name = fr'{file.parent}\old_{file.stem}_{created_datetime}.txt'
            if not Path(old_file_name).exists():
                file.rename(old_file_name)
                return old_file_name

    # only two request run, filter todo_list on the client side
    def run(self, mode='local'):
        """
        There are 3 types: local, less_requests, normal.
        the number of requests to the server depends on the type
        local - no request to server use local test data
        normal - request with filter to search user _todo(many requests)
        less_requests - only two request, filter the result on client
        """
        if mode == 'local':
            users = self.simple_json_load(self.users_local)
            todos = self.simple_json_load(self.todos_local)
            todos = self.simple_validate(todos, self.todo_schema)[0]
        elif mode == 'less_requests':
            try:
                users = requests.get(self.users_url).json()
                todos = requests.get(self.todos_url).json()
            except requests.exceptions.RequestException as e:
                self.save_errors(str(e))
                raise SystemExit(e)
            todos = self.simple_validate(todos, self.todo_schema)[0]
        elif mode == 'normal':
            try:
                users = requests.get(self.users_url).json()
            except requests.exceptions.RequestException as e:
                self.save_errors(str(e))
                raise SystemExit(e)
        else:
            raise ValueError("mode must be one of: local, less_requests, normal")
        users = self.simple_validate(users, self.user_schema)[0]

        for user in users:
            if mode == 'normal':
                user_todo = self.get_user_todo_names_request(user["id"])
            else:
                user_todo = self.get_user_todo_names(user["id"], todos)

            # create text of report
            report = self.create_text_report(user, user_todo)

            file = Path(fr'tasks/{user["username"]}.txt')

            # if file already exist, rename in in format old_{file.stem}_{created_datetime}.txt'
            old_file = self.rename_old_report(file)

            # create new file with report
            try:
                with file.open('w', encoding='utf-8') as file:
                    file.write(report)
            except EnvironmentError as err:
                self._warnings.append(f'failed to save {file};\n Error: {err}\n')
                if file.exists():
                    file.unlink()
                if old_file is not None:
                    Path(old_file).rename(str(file))

        self.save_warnings()


def main():
    program = Program()

    mode = 'local'  # берутся локальные тестовые данные
    mode = 'normal'  # на одного пользователя два запроса с фильтром _todo
    mode = 'less_requests'  # вариант в котором за два запроса получается полный списк пользователей и заданий

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    runtime = timeit.Timer(lambda: program.run(mode=mode)).timeit(1)
    print(f'runtime {runtime:.3f}s')


if __name__ == '__main__':
    main()
