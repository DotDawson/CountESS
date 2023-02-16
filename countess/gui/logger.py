import tkinter as tk
from tkinter import ttk

from typing import Optional

import datetime

from countess.core.logger import Logger

class LoggerTreeview(ttk.Treeview):

    def __init__(self, tk_parent, *a, **k):
        super().__init__(tk_parent, *a, **k)
        self['columns'] = ["name", "message", "row", "col", "detail"]
        self.heading(0, text="name")
        self.heading(1, text="message")
        self.heading(2, text="row")
        self.heading(3, text="column")
        self.heading(4, text="detail")


class LabeledProgressbar(ttk.Progressbar):
    """A progress bar with a label on top of it, the progress bar value can be set in the
    usual way and the label can be set with self.update_label"""
    # see https://stackoverflow.com/a/40348163/90927 for how the styling works.

    style_data = [
        (
            "LabeledProgressbar.trough",
            {
                "children": [
                    ("LabeledProgressbar.pbar", {"side": "left", "sticky": tk.NS}),
                    ("LabeledProgressbar.label", {"sticky": ""}),
                ],
                "sticky": tk.NSEW,
            },
        )
    ]

    def __init__(self, master, *args, **kwargs):
        self.style = ttk.Style(master)
        # make up a new style name so we don't interfere with other LabeledProgressbars
        # and accidentally change their color or label (uses arbitrary object ID)
        self.style_name = f"_id_{id(self)}"
        self.style.layout(self.style_name, self.style_data)
        self.style.configure(self.style_name, background="green")

        kwargs["style"] = self.style_name
        super().__init__(master, *args, **kwargs)

    def update_label(self, s):
        self.style.configure(self.style_name, text=s)


class LoggerFrame(ttk.Frame):

    def __init__(self, tk_parent, *a, **k):
        super().__init__(tk_parent, *a, **k)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.treeview = LoggerTreeview(self)
        self.treeview.grid(row=0, column=0, sticky=tk.NSEW)

        self.scrollbar_x = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.treeview.xview)
        self.scrollbar_x.grid(row=1, column=0, sticky=tk.EW)
        self.treeview.configure(xscrollcommand=self.scrollbar_x.set)

        self.scrollbar_y = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.treeview.yview)
        self.scrollbar_y.grid(row=0, column=1, sticky=tk.NS)
        self.treeview.configure(yscrollcommand=self.scrollbar_y.set)

        self.progress_frame = tk.Frame(self)
        self.progress_frame.grid(row=2, columnspan=2, sticky=tk.EW)
        self.progress_frame.columnconfigure(0, weight=1)

    def get_logger(self, name: str):
        return TreeviewLogger(self.treeview, self.progress_frame, name)


class TreeviewLogger(Logger):

    def __init__(self, treeview: ttk.Treeview, progress_frame: tk.Frame, name: str):
        self.treeview = treeview
        self.progress_bar = LabeledProgressbar(progress_frame, mode="determinate", value=0)
        self.progress_bar.update_label(name)
        self.name = name

    def log(self, level: str, message: str, row: Optional[int] = None, col: Optional[int] = None, detail: Optional[str] = None):
        datetime_now = datetime.datetime.now()
        values=[self.name, message, row or '', col or '', detail or '']
        self.treeview.insert("", "end", None, text=datetime_now.isoformat(), values=values)
    
    def progress(self, a: int, b: int, s: Optional[str] = ''):
        self.progress_bar.grid(sticky=tk.EW)
        if b:
            self.progress_bar.config(mode="determinate", value=100 * a // b)
            self.progress_bar.update_label(f"{self.name}: {s} {a} / {b}")
        else:
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.step(5)
            self.progress_bar.update_label(f"{self.name}: {s} {a}")

    def __del__(self):
        self.progress_bar.after(2500, lambda pbar=self.progress_bar: pbar.destroy())