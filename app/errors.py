# стандартные ошибки (если будет нужно логирование)

class GetDataError(ValueError):
    default_message = "Ошибка сбора данных"

    def __init__(self, message: str = None, field: str = None):
        self.field = field
        self.message = message or self.default_message
        super().__init__(self.message)


class EditDataError(ValueError):
    default_message = "Ошибка обработки данных"

    def __init__(self, message: str = None, field: str = None):
        self.field = field
        self.message = message or self.default_message
        super().__init__(self.message)


class InputValidationError(ValueError):
    default_message = "Неверная ссылка!"

    def __init__(self, message: str = None, field: str = None):
        self.field = field
        self.message = message or self.default_message
        super().__init__(self.message)
