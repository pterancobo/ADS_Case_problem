# -*- coding: utf-8 -*-
"""sktime_model.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/github/pterancobo/ADS_Case_problem/blob/main/sktime_model.ipynb
"""

# !pip install sktime
# !pip install mlflow

# Commented out IPython magic to ensure Python compatibility.
# Imports
import sktime
from sktime.forecasting.model_selection import temporal_train_test_split
from sktime.forecasting.base import ForecastingHorizon
from sktime.forecasting.theta import ThetaForecaster
from sktime.performance_metrics.forecasting import mean_absolute_percentage_error as mape, mean_absolute_error as mae
from sktime.utils.plotting import plot_series
from sktime.forecasting.naive import NaiveForecaster
from sktime.forecasting.theta import ThetaForecaster
from sktime.forecasting.trend import STLForecaster
from sktime.forecasting.ets import AutoETS
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, PowerTransformer, RobustScaler

from sktime.forecasting.compose import TransformedTargetForecaster
from sktime.transformations.series.adapt import TabularToSeriesAdaptor
from sktime.transformations.series.detrend import Deseasonalizer, Detrender
from sktime.forecasting.exp_smoothing import ExponentialSmoothing
from sktime.forecasting.model_selection import ForecastingGridSearchCV
from sktime.performance_metrics.forecasting import MeanSquaredError

from sktime.forecasting.base import ForecastingHorizon
from sktime.split import (
    ExpandingWindowSplitter,
    SingleWindowSplitter,
    SlidingWindowSplitter,
)
from sktime.utils.plotting import plot_windows

import mlflow
import sys

# %matplotlib inline
import numpy as np
import matplotlib.pyplot as plt

from google.colab import drive
drive.mount('/content/drive')

# variables
ARTIFACT_PATH = "model"
experiment_name = "train_experiment"

# To sync results with repo

from google.colab import drive
from os.path import join
root = '/content/drive/MyDrive'     # default for the drive

GIT_USERNAME = "pterancobo"
GIT_TOKEN = "replacebyacesstoken"
GIT_REPOSITORY = "ADS_Case_problem"

google_drive_path = join(root, GIT_REPOSITORY, 'data/' )

# !mkdir "{google_drive_path}"     # in case we haven't created it already

GIT_PATH = f"https://{GIT_TOKEN}@github.com/{GIT_USERNAME}/{GIT_REPOSITORY}.git"

try:
  !git clone "{GIT_PATH}"
except:
  pass

# !rsync -aP --exclude=data/ "{google_drive_path}"/*  ./

# build a pipeline that can run on mlflow
"comments are use for debugging"

def pipeline():
  mlflow.set_experiment(experiment_name)
  # 1 load data

  url =  sys.argv[1]
  # url = 'https://github.com/pterancobo/ADS_Case_problem/blob/main/data/train.csv?raw=true'
  raw_df = pd.read_csv(url).dropna() # remove na values, as there is empty stuff at the end

  # raw_df.head() # explore data to see what it looks like

  # 2 Preprocess data to make it compliant with sktime
  clean_df = raw_df.rename(columns={"Unnamed: 0":"date","y":"value"})
  clean_df['date'] = pd.to_datetime(clean_df['date'], format='%d.%m.%y')
  clean_df['date'] = pd.PeriodIndex(clean_df['date'], freq="M")
  clean_df = clean_df.set_index("date")

  # 3 Process data
  train_df, test_df = temporal_train_test_split(clean_df, train_size = .95)

  # define forecasting horizon fh: (array with dates over which we will make predictions)
  fh = ForecastingHorizon(test_df.index, is_relative=False).to_relative(cutoff=train_df.index[-1])
  cv = SingleWindowSplitter(fh=fh, window_length=len(train_df) )

  # look if the cross validation window looks good
  plot_windows(cv=cv, y= train_df)

  # Using grid search we can fit multiple forecasters to find the best one
  forecaster = TransformedTargetForecaster(
    steps=[
        ("detrender", Detrender()),
        ("deseasonalizer", Deseasonalizer()),
        ("scaler", TabularToSeriesAdaptor(RobustScaler())),
        ("minmax2", TabularToSeriesAdaptor(MinMaxScaler((1, 10)))),
        ("forecaster", NaiveForecaster()),
    ]
  )
  gscv = ForecastingGridSearchCV(
    forecaster=forecaster,
    param_grid=[
        {
            "scaler__transformer__with_scaling": [True, False],
            "forecaster": [NaiveForecaster()],
            "forecaster__strategy": ["drift", "last", "mean"],
            "forecaster__sp": [1, 4, 6, 12], # quarterly, bimensual, mensual
        },
        {
            "scaler__transformer__with_scaling": [True, False],
            "forecaster": [STLForecaster(), ThetaForecaster(), ExponentialSmoothing(),AutoETS(auto=True)],
            "forecaster__sp": [1, 4, 6, 12],
        }
    ],
    cv=cv,
    scoring=MeanSquaredError(square_root=True),
  )

  # train models
  gscv.fit(train_df)

  """
  Next lines only for debugging
  gscv.cv_results_.head()

  gscv.best_params_
  gscv.best_forecaster_
  """

  # 4 Post process

  # now make predictions on the forecasting horizon
  pred_df = gscv.predict(fh=fh)

  # Log parameters and metrics
  mlflow.log_params(gscv.best_params_)
  model_uri = mlflow.get_artifact_uri(ARTIFACT_PATH)

  # Plot and track mlflow image
  fig = plot_series(train_df, test_df, pred_df, labels=["train", "test", "pred"])
  mlflow.log_figure(fig, 'y.png')

  # generate a new period as required in the problem
  exam_fh = fh = ForecastingHorizon(pd.PeriodIndex(pd.date_range("2021-03", periods=12, freq="M")), is_relative=False)
  exam_pred_df = gscv.predict(fh=exam_fh)
  fig = plot_series(train_df, test_df, exam_pred_df, labels=["train", "test", "exam_pred"])

  # save csv in the same format as the original csv
  exam_pred_df.to_csv(f'{google_drive_path}exam_forecast.csv')

  # push to data folder in repo
  try:
    !rsync -aP --exclude=data/ "{google_drive_path}"/*  ./
  except:
    pass


  if __name__ == "__main__":
    pipeline()