"""Container entry point, including platforms that provide a dynamic PORT."""

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, server_header=False)


if __name__ == "__main__":
    main()
