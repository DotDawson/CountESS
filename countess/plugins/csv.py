from typing import Optional

import dask.dataframe as dd
import numpy as np
import pandas as pd  # type: ignore
import csv

from countess.core.parameters import BooleanParam, ChoiceParam, LEVELS
from countess.core.plugins import DaskInputPlugin
from countess.utils.dask import merge_dask_dataframes

VERSION = "0.0.1"


class LoadCsvPlugin(DaskInputPlugin):
    """Load CSV files"""

    name = "CSV Load"
    title = "Load from CSV"
    description = "Loads columns from CSV files and merges them into the data"
    version = VERSION

    file_types = [("CSV", "*.csv"), ("TSV", "*.tsv")]

    parameters = {
        "header": BooleanParam("CSV file has header?", True),
        "join_how": ChoiceParam("Join Direction", choices=[]),
    }

    def prerun(self, ddf: Optional[dd.DataFrame]) -> dd.DataFrame:
        join_how_param = self.parameters['join_how']

        if ddf is not None:
            join_how_param.choices = ["left", "right", "inner", "outer"]
        else:
            join_how_param.choices = ["N/A"]
            join_how_param.value = "N/A"

        return super().prerun(ddf)

    def read_file_to_dataframe(self, file_param, column_suffix='', row_limit=None):
       
        columns = []
        records = []
        with open(file_param["filename"].value, "r") as fh:
            csv_reader = csv.reader(fh)
            for n, row in enumerate(csv_reader):
                if n == 0 and self.parameters['header'].value:
                    columns = row
                else:
                    while len(row) > len(columns):
                        columns.append(f"column_%d" % len(columns))
                    records.append(row)
                if n > row_limit:
                    break

        if column_suffix:
            columns = [ f"{c}_{column_suffix}" for c in columns ]

        return pd.DataFrame.from_records(records, columns=columns, index=columns[0])

    def combine_dfs(self, df0, dfs):
        """Lookup CSV records in with a left join"""

        combined_df = merge_dask_dataframes(dfs)
        if df0 is not None:
            return df0.merge(combined_df, how=self.parameters['join_how'].value)
        else:
            return combined_df
