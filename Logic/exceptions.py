class KeyNotFound(Exception):
    def __init__(self):
        self.code = -99
        self.message = 'Key not found!'


class WrongRequest(Exception):
    def __init__(self, message):
        self.code = -100
        self.message = message


class NoResponse(Exception):
    def __init__(self):
        self.code = -101
        self.message = 'No response!'


class UnknownTypeData(Exception):
    def __init__(self, message):
        self.code = -102
        self.message = message


class WrongActionBasedOnState(Exception):
    def __init__(self):
        self.code = -103
        self.message = 'Wrong action!'
