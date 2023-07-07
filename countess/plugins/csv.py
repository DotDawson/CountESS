import csv
from io import StringIO
from typing import Any, Optional

import pandas as pd

from countess import VERSION
from countess.core.parameters import (
    ArrayParam,
    BooleanParam,
    ChoiceParam,
    DataTypeOrNoneChoiceParam,
    FileSaveParam,
    MultiParam,
    StringParam,
)
from countess.core.plugins import PandasBasePlugin, PandasInputPlugin

# XXX it would be better to do the same this Regex Tool does and get the user to assign
# data types to each column



def maybe_number(x):
    """CSV is never clear on if something is actually a number so ... try it I guess ..."""
    try:
        return int(x)
    except ValueError:
        pass

    try:
        return float(x)
    except ValueError:
        pass

    return x


def clean_row(row):
    return [maybe_number(x) for x in row]


class LoadCsvPlugin(PandasInputPlugin):
    """Load CSV files"""

    name = "CSV Load"
    description = "Loads data from CSV or similar delimited text files and assigns types to columns"
    link = "https://countess-project.github.io/CountESS/plugins/#csv-reader"
    version = VERSION

    file_types = [
        ("CSV", "*.csv *.csv.gz *.csv.bz2"),
        ("TSV", "*.tsv *.tsv.gz *.tsv.bz2"),
        ("TXT", "*.txt *.txt.gz *.txt.bz2"),
    ]

    parameters = {
        "delimiter": ChoiceParam("Delimiter", ",", choices=[",", ";", "TAB", "|", "WHITESPACE"]),
        "quoting": ChoiceParam("Quoting", "None", choices=["None", "Double-Quote", "Quote with Escape"]),
        "comment": ChoiceParam("Comment", "None", choices=["None", "#", ";"]),
        "header": BooleanParam("CSV file has header row?", True),
        "filename_column": StringParam("Filename Column", ""),
        "columns": ArrayParam(
            "Columns",
            MultiParam(
                "Column",
                {
                    "name": StringParam("Column Name", ""),
                    "type": DataTypeOrNoneChoiceParam("Column Type"),
                    "index": BooleanParam("Index?", False),
                },
            ),
        ),
    }

    def read_file_to_dataframe(self, file_params, logger, row_limit=None):
        filename = file_params["filename"].value

        print(f"read_file_to_dataframe {filename}")

        options = {
            "header": 0 if self.parameters["header"].value else None,
        }
        if row_limit is not None:
            options["nrows"] = row_limit

        index_col_numbers = []

        if len(self.parameters["columns"]):
            options["names"] = []
            options["dtype"] = {}
            options["usecols"] = []

            for n, pp in enumerate(self.parameters["columns"]):
                options["names"].append(pp["name"].value or f"column_{n}")
                if not pp["type"].is_none():
                    if pp["index"].value:
                        index_col_numbers.append(len(options["usecols"]))
                    options["usecols"].append(n)
                    options["dtype"][n] = pp["type"].get_selected_type()

        delimiter = self.parameters["delimiter"].value
        if delimiter == "TAB":
            options["delimiter"] = "\t"
        elif delimiter == "WHITESPACE":
            options["delim_whitespace"] = True
        else:
            options["delimiter"] = delimiter

        quoting = self.parameters["quoting"].value
        if quoting == "None":
            options["quoting"] = csv.QUOTE_NONE
        elif quoting == "Double-Quote":
            options["quotechar"] = '"'
            options["doublequote"] = True
        elif quoting == "Quote with Escape":
            options["quotechar"] = '"'
            options["doublequote"] = False
            options["escapechar"] = "\\"

        comment = self.parameters["comment"].value
        if comment != "None":
            options["comment"] = comment

        # XXX pd.read_csv(index_col=) is half the speed of pd.read_csv().set_index()

        df = pd.read_csv(filename, **options)

        while len(df.columns) > len(self.parameters["columns"]):
            self.parameters["columns"].add_row()

        if self.parameters["header"].value:
            for n, col in enumerate(df.columns):
                if not self.parameters["columns"][n]["name"].value:
                    self.parameters["columns"][n]["name"].value = str(col)

        filename_column = self.parameters["filename_column"].value
        if filename_column:
            df[filename_column] = filename

        if index_col_numbers:
            df = df.set_index([df.columns[n] for n in index_col_numbers])

        print(f"read_file_to_dataframe {df}")
        return df


class SaveCsvPlugin(PandasBasePlugin):
    name = "CSV Save"
    description = "Save data as CSV or similar delimited text files"
    link = "https://countess-project.github.io/CountESS/plugins/#csv-writer"
    version = VERSION

    file_types = [("CSV", "*.csv"), ("TSV", "*.tsv"), ("TXT", "*.txt")]

    parameters = {
        "header": BooleanParam("CSV header row?", True),
        "filename": FileSaveParam("Filename", file_types=file_types),
        "delimiter": ChoiceParam("Delimiter", ",", choices=[",", ";", "TAB", "|", "SPACE"]),
        "quoting": BooleanParam("Quote all Strings", False),
    }

    def run(
        self,
        data: Any,
        logger,
        row_limit: Optional[int] = None,
    ):
        assert isinstance(self.parameters["filename"], StringParam)

        filename = self.parameters["filename"].value
        sep = self.parameters["delimiter"].value
        if sep == "TAB":
            sep = "\t"
        elif sep == "SPACE":
            sep = " "

        has_named_index = (data.index.name is not None) or (hasattr(data.index, "names") and data.index.names[0] is not None)

        options = {
            "header": self.parameters["header"].value,
            "index": has_named_index,
            "sep": sep,
            "quoting": csv.QUOTE_NONNUMERIC if self.parameters["quoting"].value else csv.QUOTE_MINIMAL,
        }

        if row_limit is None:
            data.to_csv(filename, **options)
            return None
        else:
            buf = StringIO()
            data.to_csv(buf, **options)
            return buf.getvalue()
