import os


def load_credential(path: str, key: str) -> str:
    full_path = os.path.expanduser(path)
    with open(full_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.strip().split("=", 1)[1]
    raise ValueError(f"{key} not found in {full_path}")
