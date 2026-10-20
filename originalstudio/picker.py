import json
import sys


def main():
    import tkinter
    from tkinter import filedialog

    window = tkinter.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(parent=window, title="拾序 · 选择素材目录", mustexist=True)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"path": selected or None}, ensure_ascii=False))
    finally:
        window.destroy()


if __name__ == "__main__":
    main()
