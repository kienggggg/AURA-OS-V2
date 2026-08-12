class Editor:
    """Trình soạn thảo có undo/redo.

    Sau khi undo rồi làm một hành động MỚI, nhánh redo cũ phải bị BỎ HẲN.
    """

    def __init__(self) -> None:
        self.text = ""
        self.history: list[str] = []
        self.future: list[str] = []

    def type(self, chunk: str) -> None:
        self.history.append(self.text)
        self.text += chunk

    def undo(self) -> None:
        if self.history:
            self.text = self.history.pop()

    def redo(self) -> None:
        if self.future:
            self.text = self.future.pop()
