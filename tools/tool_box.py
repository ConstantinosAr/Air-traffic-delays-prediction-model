from re import L
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import OrdinalEncoder
from sklearn.model_selection import KFold
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import get_scorer
from sklearn.svm import SVR
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt

import sys

# sys.path.append(".")
# from extraction.extract import readLRDATA


# Define type of sklearn models for type hints
# sklearnModel = np.union[
#     SVR, RandomForestRegressor, KNeighborsRegressor, LinearRegression
# ]
def filtering_data_onehot(
    filename: str,
    start: datetime = datetime(2015, 12, 31),
    end: datetime = datetime(2015, 12, 31),
):
    dform = "%Y-%m-%d %H:%M:%S"

    df = pd.read_csv(filename, header=0, index_col=0)
    df = df.assign(FiledOBT=lambda x: pd.to_datetime(x.FiledOBT, format=dform))
    df = data_filter(df, start, end)
    new_df = df.drop(["FiledOBT", "FiledAT", "ACType", "ArrivalDelay", "DepartureDelay"], axis=1)

    new_df3 = pd.get_dummies(new_df, columns=new_df.columns[:5])
    encoded_array = new_df3.to_numpy()
    scaler = MinMaxScaler()
    X_scaled_array = scaler.fit_transform(encoded_array)
    y = df["ArrivalDelay"].to_numpy()

    pd.DataFrame((new_df3)).to_csv(
        "tools/finaldf.csv", header=True, index=False
    )

    pd.DataFrame((X_scaled_array)).to_csv(
        "tools/xdata.csv", header=False, index=False
    )
    pd.DataFrame((y)).to_csv("tools/ydata.csv", header=False, index=False)

    return y, X_scaled_array


def filtering_data_ordinal_enc(
    filename: str = "LRData/LRDATA.csv",
    start: datetime = datetime(2019, 1, 1),
    end: datetime = datetime(2019, 12, 31),
):
    dform = "%Y-%m-%d %H:%M:%S"

    df = pd.read_csv(filename, header=0, index_col=0)
    df = df.assign(FiledOBT=lambda x: pd.to_datetime(x.FiledOBT, format=dform))
    df = data_filter(df, start, end)
    new_df = df.drop(["FiledOBT", "FiledAT"], axis=1)
    new_df2 = new_df.drop(["ArrivalDelay", "DepartureDelay"], axis=1)

    new_df3 = new_df2.to_numpy()
    to_be_enc = new_df3[:, :6]

    enc = OrdinalEncoder()

    encoded_part = enc.fit_transform(to_be_enc)
    encoded_array = np.concatenate((encoded_part, new_df3[:, 6:]), axis=1)
    # print(f"Encoded array = {encoded_array}")
    scaler = MinMaxScaler()
    X_scaled_array = scaler.fit_transform(encoded_array)
    y = df["ArrivalDelay"].to_numpy()

    pd.DataFrame((X_scaled_array)).to_csv("tools/xdata.csv", header=False, index=False)
    pd.DataFrame((y)).to_csv("tools/ydata.csv", header=False, index=False)

    # print(X_scaled_array)
    print("-------------Data filtering Done-----------------")
    # pd.DataFrame(scaled_array).to_csv("scaled_2016_encoded_data.txt", header=False, index=False)

    return X_scaled_array, y


def get_data():
    X = np.genfromtxt("tools/xdata.csv", delimiter=",")
    y = np.genfromtxt("tools/ydata.csv", delimiter=",")

    return X, y


def data_filter(P: pd.DataFrame, start: datetime, end: datetime):
    P = P.query("FiledOBT <= @end & FiledOBT >= @start ")
    return P


def parameter_search(
    model,
    parameters: dict,
    X_train: np.array,
    y_train: np.array,
    score_string: str = "neg_mean_squared_error",
    n_folds: int = 5,
):
    """Optimizes parameters of model using cross-validation.

    Args:
        model (sklearnModel): sklearn regression model
        parameters (dict): dictionary containing the to tune parameters
        X_train (np.array): training data
        y_train (np.array): training labels
        score_string (str, optional): defines the to use score function. Get strings from https://scikit-learn.org/stable/modules/model_evaluation.html#scoring-parameter. Defaults to "neg_mean_squared_error".
        n_folds (int, optional): number of folds to use for cros-validation. Defaults to 5.

    Returns:
        dict: optimal parameters for model
    """

    cv = KFold(n_splits=n_folds, random_state=42, shuffle=True)
    grid_search = GridSearchCV(
        model, parameters, cv=cv, n_jobs=-1, verbose=4, scoring=score_string,
    ).fit(X_train, y_train)

    print("grid search", grid_search)
    print("best params", grid_search.bestparams)
    print("refit time", grid_search.refittime)
    df = pd.DataFrame(grid_search.cvresults)
    y_values = df.to_numpy()[:, -3]
    plt.plot(parameters['n_neighbors'], y_values * -1)
    ymin = np.max(y_values)
    plt.scatter(16, ymin * -1, color = 'red')
    plt.xlabel('K')
    plt.ylabel('MSE')
    plt.show()

    best_parameters = grid_search.bestparams
    return best_parameters


def split_into_folds(X: np.array, y: np.array, n_folds: int):
    """Splits the data into n amount of folds.
       Used in double_cross_validation.

    Args:
        X (np.array): Training data
        y (np.array): labels corresponding to training data
        n_folds (int): amount of folds

    Returns:
        tuple(list, list): [description]
    """
    interval = len(y) // n_folds
    return (
        [X[i * interval : (i + 1) * interval] for i in range(n_folds)],
        [y[i * interval : (i + 1) * interval] for i in range(n_folds)],
    )


def double_cross_validation(
    model,
    parameters: dict,
    X_train: np.array,
    y_train: np.array,
    score_string: str = "neg_mean_squared_error",
    inner_folds: int = 3,
    outer_folds: int = 10,
    print_performance: bool = True,
):
    """Tunes and evaluates the performance of a model using double (nested) cross-validation.

    Args:
        model (sklearnModel): sklearn model
        parameters (dict): dictionary with model name and dict as key with in that all hyper-parameters
        X_train (np.array): Training + test data
        y_train (np.array): labels corresponding to training data
        score_func (function): which score function should be used to calculate the score of the model
        inner_folds (int, optional): amount of inner folds used for nested cross validation. Defaults to 3.
        outer_folds (int, optional): amount of outer folds used for nested cross validation. Defaults to 10.
        print_performance (bool, optional): Choose if python should print best performing perameters for each model. Defaults to True.

    Returns:
        performance_score, st_dev, best_parameters [type]: [description]
    """

    scores = []
    best_parameters = {}

    X_folds, y_folds = split_into_folds(X_train, y_train, n_folds=outer_folds)
    for i, (X_fold_test, y_fold_test) in enumerate(zip(X_folds, y_folds)):
        # Split the data up into test fold and training data
        X_fold_train = np.concatenate(
            [X_folds[k] for k in range(outer_folds) if k != i]
        )
        y_fold_train = np.concatenate(
            [y_folds[k] for k in range(outer_folds) if k != i]
        )

        # Perform inner cross validation to tune the model
        grid_search = GridSearchCV(
            model,
            parameters,
            cv=KFold(n_splits=inner_folds),
            shuffle=True,
            scoring=score_string,
            n_jobs=-1,
        )
        grid_search.fit(X_fold_train, y_fold_train)
        best_model, hyperparameters = (
            grid_search.best_estimator_,
            grid_search.best_params_,
        )

        # Evaluate model
        predictions = best_model.predict(X_fold_test)
        score_func = get_scorer(score_string)._score_func
        score = score_func(y_fold_test, predictions)
        scores.append(score)

        # If best_model performs better than any previously found model, we update best_parameters.
        # The if/else statements are necessary, because we need to be able to know whether a high outcome or a low
        # outcome of score_func is desirable. For accuracy_score, a high value is desired, while for log_loss a low
        # value is more ideal.
        if score_func([1, 2], [1, 2]) > score_func([1, 2], [2, 1]):
            if score == max(scores):
                best_parameters = hyperparameters
        else:
            if score == min(scores):
                best_parameters = hyperparameters

    performance_score = np.mean(scores)
    st_dev = np.std(scores)

    if print_performance:
        print(
            f'{score_func.__name__.replace("_", " ")}: {round(performance_score, 3)}, st_dev: {round(st_dev, 5)}'
        )
        print(f"Tuned parameters: {best_parameters}")

    return best_parameters, performance_score, st_dev

filtering_data_onehot('./LRDATA/LRDATA.csv', datetime(2019, 1, 1), datetime(2019, 4, 1))