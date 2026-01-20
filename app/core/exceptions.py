class CustomException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class OpenAIException(CustomException):
    pass

class STTException(CustomException):
    pass
