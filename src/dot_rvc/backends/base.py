from typing import Protocol


class Backend(Protocol):
    name: str

    def read_state(self) -> dict:
        """Return the control state documented in docs/EXTENDING.md."""
        ...

    def write_setting(self, key: str, value: int | float | bool) -> None:
        """Request one change, raising BridgeError on failure/unknown outcome."""
        ...
