import pandas as pd
import os
from glob import glob
from datetime import datetime, timedelta
from tqdm import tqdm
import matplotlib.pyplot as plt
from extraction.extractionvalues import *
from extraction.airportvalues import *
from extraction.weather import fetch_weather_data

import numpy as np


def extractData(
    start: datetime = None,
    end: datetime = None,
    folderName: str = "data",
    marketSegments: list = marketSegments,
):
    """extract raw data from eurocontrol data and converts it into a pandas dataframe

    Args:
        start (datetime, optional): start time to extract data. Defaults to None.
        end (datetime, optional): final date to extract data. Defaults to None.
        folderName (str, optional): foldername to take data from. Defaults to "data".
        marketSegments ([type], optional): list of market segments to consider default is commercial scheduled. Defaults to marketSegments.

    Raises:
        ValueError: date needs to be between start of 2015 and end of 2019

    Returns:
        pd.DataFrame: complete pandas flights dataframe
    """

    # Basic input validation
    if start is None and end is None:
        start = datetime(2015, 1, 1)
        end = datetime(2019, 12, 31)
    if start.year < 2015 or start.year > 2019:
        raise ValueError(f"Incorrect start date (start between 2015 and 2019) {start}")
    if end.year < 2015 or end.year > 2019:
        raise ValueError(f"Incorrect end date (end between 2015 and 2019) {end}")
    if end.year < start.year:
        raise ValueError(f"Entered end before start ({start} > {end})")

    years = list(range(start.year, end.year + 1))
    listOfFiles = []
    for year in years:
        # Dank file selection https://pynative.com/python-glob/
        listOfFiles.extend(glob(f"{folderName}/{year}/*/Flights_2*.csv*"))

    finalData = pd.DataFrame()

    for file in tqdm(listOfFiles):
        # read, filter and process csv
        P = pd.read_csv(file)

        # Datetime format
        dform = "%d-%m-%Y %H:%M:%S"

        P = (
            P.query("`ICAO Flight Type` == 'S'")
            .query("`STATFOR Market Segment` in @marketSegments")
            .rename(columns={"FILED OFF BLOCK TIME": "FiledOBT"})
            .rename(columns={"FILED ARRIVAL TIME": "FiledAT"})
            .rename(columns={"ACTUAL OFF BLOCK TIME": "ActualOBT"})
            .rename(columns={"ACTUAL ARRIVAL TIME": "ActualAT"})
            .rename(columns={"STATFOR Market Segment": "FlightType"})
            .rename(columns={"ADEP Latitude": "ADEPLat"})
            .rename(columns={"ADEP Longitude": "ADEPLong"})
            .rename(columns={"ADES Latitude": "ADESLat"})
            .rename(columns={"ADES Longitude": "ADESLong"})
            .rename(columns={"AC Type": "ACType"})
            .rename(columns={"AC Type": "ACType"})
            .rename(columns={"AC Operator": "ACOperator"})
            .rename(columns={"ECTRL ID": "ECTRLID"})
            .rename(columns={"Actual Distance Flown (nm)": "ActualDistanceFlown"})
            .drop(["AC Registration"], axis=1)
            .drop(["Requested FL"], axis=1)
            .drop(["ICAO Flight Type"], axis=1)
            .assign(FiledOBT=lambda x: pd.to_datetime(x.FiledOBT, format=dform))
            .assign(FiledAT=lambda x: pd.to_datetime(x.FiledAT, format=dform))
            .assign(ActualOBT=lambda x: pd.to_datetime(x.ActualOBT, format=dform))
            .assign(ActualAT=lambda x: pd.to_datetime(x.ActualAT, format=dform))
            .query("ADES != ADEP")
        )
        finalData = finalData.append(P, ignore_index=True)

    # finalData = finalData.
    finalData = (
        finalData.sort_values(by=["ECTRLID"])
        .drop_duplicates("ECTRLID")
        .reset_index(drop=True)
    )

    return finalData


def calculateDelays(P: pd.DataFrame, delayTypes: list = ["arrival", "departure"]):
    """ " calculate delay for both arrival and departure in minutes

    Args:
        P (pd.DataFrame): Pandas flights dataframe
        delayTypes (list, list): arrival and departure times. Defaults to ["arrival", "departure"].

    Returns:
        pd.DataFrame: Pandas flights dataframe with delays
    """
    if "arrival" in delayTypes:
        P = P.assign(
            ArrivalDelay=lambda x: (x.ActualAT - x.FiledAT).astype("timedelta64[m]")
        )
    if "departure" in delayTypes:
        P = P.assign(
            DepartureDelay=lambda x: (x.ActualOBT - x.FiledOBT).astype("timedelta64[m]")
        )

    P = P.query(
        "ArrivalDelay < 90 & ArrivalDelay > -30 & DepartureDelay < 90 & DepartureDelay > -30 "
    )

    return P


def filterAirports(P: pd.DataFrame, airports: list):
    """Filter pandas airport arrivals and departures to a list of airports

    Args:
        P (pd.DataFrame): Pandas flights dataframe
        airports (list): list of airports to keep

    Returns:
        pd.DataFrame: filtered flights dataframe
    """

    P = P.query("`ADEP` in @airports | `ADES` in @airports")
    return P


def linearRegressionFormat(P: pd.DataFrame, airports: list = ICAOTOP50):
    """Converts a complete extracted dataframe into the format used for linear regression

    Args:
        P (pd.DataFrame): complete unfiltered pandas dataframe
        airports (list, optional): list of airports. Defaults to ICAOTOP25.

    Returns:
        pd.DataFrame: filtered pandas dataframe in LR format
    """
    columns = [
        "ADEP",
        "ADES",
        "FiledOBT",
        "FiledAT",
        "ACType",
        "ACOperator",
        "ArrivalDelay",
        "DepartureDelay",
        "ADEPLat",
        "ADEPLong",
        "ADESLat",
        "ADESLong",
    ]
    P = filterAirports(P, airports)
    P = calculateDelays(P)
    P = P.loc[:, columns]
    P["month"] = P["FiledAT"].dt.month
    P["weekday"] = P["FiledAT"].dt.weekday
    P["filedATminutes"] = P["FiledAT"].dt.hour * 60 + P["FiledAT"].dt.minute
    P["filedOBTminutes"] = P["FiledOBT"].dt.hour * 60 + P["FiledOBT"].dt.minute

    # P = P.drop(["FiledOBT", "FiledAT"], axis=1)

    return P


def saveToCSV(P: pd.DataFrame, saveFolder: str = "LRData"):
    """Convert the flights dataframe to a CSV

    Args:
        P (pd.DataFrame): Pandas flights dataframe
        saveFolder (str): name folder to save the CSV file in. Defaults to "LRData".
    """

    if not os.path.exists(saveFolder):
        os.mkdir(os.path.join(saveFolder))
    P.to_csv(f"{saveFolder}/LRDATA.csv")


def readLRDATA(saveFolder: str = "LRData", fileName: str = "LRDATA.csv"):
    """Read data from a flights dataframe in linear regression format

    Args:
        saveFolder (str, optional): folder where data is saved. Defaults to "LRData".
        fileName (str, optional): filename of the dataset. Defaults to "LRDATA.csv".

    Returns:
        pd.Dataframe: flights dataframe in linear regression format
    """
    fullfilename = f"{saveFolder}/{fileName}"
    P = pd.read_csv(fullfilename, header=0, index_col=0)
    return P


def generalFilterAirport(
    start: datetime,
    end: datetime,
    airport: str,
    saveFolder: str = "filteredData",
    forceRegenerateData: bool = False,
    startDefault=datetime(2018, 1, 1),
    endDefault=datetime(2019, 12, 31),
):
    """Generate all the flights for a single airport, save and return as dataframe

    Args:
        start (datetime): start date to filter for. Dates are inclusive.
        end (datetime): end date to filter for. Dates are inclusive.
        airport (str): ICAO code for the airport
        saveFolder (str, optional): target save folder. Defaults to "filteredData".
        forceRegenerateData (bool, optional): force regeneration of data even if it had already been generated. Defaults to False.
        startDefault (datetime, optinoal): start date for the csv
        endDefault (datetime, optinoal): end date for the csv

    Returns:
        pd.DataFrame: Dataframe with all flights for selected filters
    """
    file = f"{saveFolder}/general{airport}.csv"
    dform = "%Y-%m-%d %H:%M:%S"
    if not os.path.exists(saveFolder):
        os.makedirs(saveFolder)

    # For the first cold run it generates data for all dates to prevent problems
    if not os.path.exists(file) or forceRegenerateData:
        print(f"Generating {airport} airport data from {startDefault} to {endDefault}")
        P = extractData(startDefault, endDefault)
        P = P.query("`ADES` == @airport | `ADEP` == @airport")
        P = calculateDelays(P)
        P.to_csv(file)
    else:
        P = pd.read_csv(file, header=0, index_col=0)
        # Condvert datetime strings to actual datetime objects
        P = (
            P.assign(FiledOBT=lambda x: pd.to_datetime(x.FiledOBT, format=dform))
            .assign(FiledAT=lambda x: pd.to_datetime(x.FiledAT, format=dform))
            .assign(ActualOBT=lambda x: pd.to_datetime(x.ActualOBT, format=dform))
            .assign(ActualAT=lambda x: pd.to_datetime(x.ActualAT, format=dform))
        )

    # Actual date filter.
    # Does NOT include flights that departed the night before but arrived within the filter
    P = P.query("`FiledOBT` >= @start & `FiledAT` < @end")

    return P


def generateNNdata(
    airport: str,
    timeslotLength: int = 15,
    GNNFormat: bool = False,
    disableWeather: bool = True,
    saveFolder: str = "NNData",
    catagoricalFlightDuration: bool = False,
    forceRegenerateData: bool = False,
    start: datetime = datetime(2018, 1, 1),
    end: datetime = datetime(2019, 12, 31),
    startDefault=datetime(2018, 1, 1),
    endDefault=datetime(2019, 12, 31),
    availableMonths: list = [3, 6, 9, 12],
):
    """Aggregates all flights at a single airport by a certain timeslot.

    Args:
        airport (str): ICAO code for a single airport
        timeslotLength (int, optional): length to aggregate flights for in minutes. Defaults to 15 minutes.
        GNNFormat: (bool, optional): returns the data in format used for GNN model (Pagg, Y, T). Defaults to False
        disableWeather: (bool, optional): disables weather features:\
             (["timeslot", "visibility", "windspeed",\
               "temperature", "frozenprecip", \
               "surfaceliftedindex", "cape"]). Defaults to True.
        saveFolder (str, optional): folder to save data in. Defaults to "NNData".
        catagoricalFlightDelay (bool, optional): If false, flight delay is presented as average.\
             If True it is generated as bins from 0-3, 3-6 and >6. Defaults to False.
        forceRegenerateData (bool, optional): force regeneration of data even if it had already been generated. Defaults to False.
        start (datetime, optional): start date to filter for.
        end (datetime, optional): end date to filter for.
        startDefault (datetime, optinoal): start date to generate full data. Defaults to datetime(2019, 1, 31)
        endDefault (datetime, optinoal): end date to generate full data. Defaults to datetime(2019, 12, 31)
        availableMonths (list, optional): list of months available in \
            eurocontrol. Defaults to [March, June, September, December]
    Returns:
        pd.Dataframe: pandas dataframe with aggregate flight data, unscaled.
    """
    filename = f"{saveFolder}/{airport}_{timeslotLength}m.csv"

    dform = "%Y-%m-%d %H:%M:%S"
    if not os.path.exists(saveFolder):
        os.makedirs(saveFolder)

    if not os.path.exists(filename) or forceRegenerateData:
        print(
            f"Generating NN data for {airport} with a timeslot length of {timeslotLength} minutes"
        )
        P = generalFilterAirport(startDefault, endDefault, airport)

        # Temporary untill weather is added:
        numRunways = 0
        numGates = 0

        ### Data preparation for agg function
        # Are flights arriving or departing?
        P["arriving"] = P.ADES == airport
        P["departing"] = P.ADEP == airport

        # Is it a low cost flight?
        P["lowcost"] = P.FlightType != "Traditional Scheduled"

        # Planned Flight Duration (PFD) in minutes
        P["PFD"] = P["FiledAT"] - P["FiledOBT"]
        P["PFD"] = (
            P["PFD"].dt.components["hours"] * 60 + P["PFD"].dt.components["minutes"]
        )

        # Flight duration for arriving airplanes
        P.loc[(P.arriving == False), "departuresFlightDuration"] = P.PFD
        P.loc[(P.arriving == True), "arrivalsFlightDuration"] = P.PFD

        P["departuresFlightDuration0to3"] = P.departuresFlightDuration < 3 * 60
        P["departuresFlightDuration3to6"] = (P.departuresFlightDuration >= 3 * 60) & (
            P.departuresFlightDuration < 6 * 60
        )
        P["departuresFlightDuration6orMore"] = P.departuresFlightDuration >= 6 * 60

        P["arrivalsFlightDuration0to3"] = P.arrivalsFlightDuration < 3 * 60
        P["arrivalsFlightDuration3to6"] = (P.arrivalsFlightDuration >= 3 * 60) & (
            P.arrivalsFlightDuration < 6 * 60
        )
        P["arrivalsFlightDuration6orMore"] = P.arrivalsFlightDuration >= 6 * 60

        # Delay metrics for arriving and departing airports
        P.loc[(P.arriving == True), "arrivalsDepartureDelay"] = P.DepartureDelay
        P.loc[(P.arriving == True), "arrivalsArrivalDelay"] = P.ArrivalDelay
        P.loc[(P.arriving == False), "departuresDepartureDelay"] = P.DepartureDelay
        P.loc[(P.arriving == False), "departuresArrivalDelay"] = P.ArrivalDelay

        # Collect the time at which the flights are meant to be at the airport
        P.loc[(P.arriving == True), "timeAtAirport"] = P.FiledAT
        P.loc[(P.arriving == False), "timeAtAirport"] = P.FiledOBT

        # This creates a new index to ensure that we have no gaps in the timeslots later
        def daterange(start_date, end_date):
            delta = timedelta(minutes=timeslotLength)
            while start_date < end_date:
                if start_date.month in availableMonths:
                    # Only yields the months for which we have
                    # data specified in the argument availableMonths
                    yield start_date
                start_date += delta

        denseDateIndex = daterange(startDefault, endDefault)

        # Functionality for airports outside of the top50
        if airport in list(airport_dict.keys()):
            airportCapacity = airport_dict[airport]["capacity"]
        else:
            airportCapacity = 60  # this is a common value

        weatherData = fetch_weather_data(airport, timeslotLength)

        ### get aggregate features for rolling window
        Pagg = (
            P.groupby(
                [
                    pd.Grouper(key="timeAtAirport", freq=f"{timeslotLength}min"),
                ]
            )
            .agg(
                {
                    "departing": "sum",
                    "arriving": "sum",
                    "lowcost": "mean",
                    "arrivalsFlightDuration": "mean",
                    "arrivalsDepartureDelay": "mean",
                    "arrivalsArrivalDelay": "mean",
                    "departuresFlightDuration": "mean",
                    "departuresDepartureDelay": "mean",
                    "departuresArrivalDelay": "mean",
                    "departuresFlightDuration0to3": "mean",
                    "departuresFlightDuration3to6": "mean",
                    "departuresFlightDuration6orMore": "mean",
                    "arrivalsFlightDuration0to3": "mean",
                    "arrivalsFlightDuration3to6": "mean",
                    "arrivalsFlightDuration6orMore": "mean",
                }
            )
            # This ensure that there are no timeslot gaps
            # at the start and end of the dataframe
            .reindex(denseDateIndex, fill_value=0)
            # Engineering some features
            .assign(planes=lambda x: x.arriving - x.departing)
            .assign(runways=lambda x: numRunways)
            .assign(gates=lambda x: numGates)
            .assign(
                capacityFilled=lambda x: (x.arriving + x.departing) / airportCapacity
            )
            .assign(weekend=lambda x: x.index.weekday >= 5)
            .assign(winter=lambda x: (x.index.month > 11) | (x.index.month < 3))
            .assign(spring=lambda x: (x.index.month > 2) & (x.index.month < 6))
            .assign(summer=lambda x: (x.index.month > 5) & (x.index.month < 9))
            .assign(autumn=lambda x: (x.index.month > 8) & (x.index.month < 12))
            .assign(night=lambda x: (x.index.hour >= 0) & (x.index.hour < 6))
            .assign(morning=lambda x: (x.index.hour >= 6) & (x.index.hour < 12))
            .assign(afternoon=lambda x: (x.index.hour >= 12) & (x.index.hour < 18))
            .assign(evening=lambda x: (x.index.hour >= 18) & (x.index.hour <= 23))
            .drop(["runways", "gates"], axis=1)  # Temp measure until we add weather
            .reset_index()
            .rename(columns={"timeAtAirport": "timeslot"})
            # Add weather data
            .merge(weatherData, how="left", on="timeslot", validate="1:m")
            .fillna(0)
        )

        # turn boolean columns into 1 and 0
        boolCols = Pagg.columns[Pagg.dtypes.eq(bool)]
        Pagg.loc[:, boolCols] = Pagg.loc[:, boolCols].astype(int)

        # there are two ways the team wanted the flight
        # duration in bins of 3 hours or as an average,
        # here the data gets augmented based on the chase
        if catagoricalFlightDuration:
            Pagg = Pagg.drop(
                ["departuresFlightDuration", "arrivalsFlightDuration"], axis=1
            )
        else:
            Pagg = Pagg.drop(
                [
                    "departuresFlightDuration0to3",
                    "departuresFlightDuration3to6",
                    "departuresFlightDuration6orMore",
                    "arrivalsFlightDuration0to3",
                    "arrivalsFlightDuration3to6",
                    "arrivalsFlightDuration6orMore",
                ],
                axis=1,
            )

        Pagg.to_csv(filename)

    else:
        Pagg = pd.read_csv(filename, header=0, index_col=0)
        Pagg = Pagg.assign(timeslot=lambda x: pd.to_datetime(x.timeslot, format=dform))

    Pagg = Pagg.query("`timeslot` >= @start & `timeslot` < @end")

    if disableWeather:
        Pagg = Pagg.drop(
            [
                "visibility",
                "windspeed",
                "temperature",
                "frozenprecip",
                "surfaceliftedindex",
                "cape",
            ],
            axis=1,
        )

    if GNNFormat and catagoricalFlightDuration:
        raise ValueError("GNNFormat and catagoricalFlightDuration are not compatible")

    if GNNFormat:
        Y = Pagg.loc[:, ["arrivalsArrivalDelay", "departuresDepartureDelay"]]
        T = Pagg.loc[:, ["timeslot"]]
        Pagg = Pagg.drop(
            [
                "arrivalsArrivalDelay",
                "departuresDepartureDelay",
                "departuresArrivalDelay",
                "timeslot",
            ],
            axis=1,
        )
        return Pagg, Y, T
    else:
        return Pagg


def generateNNdataMultiple(
    airports: list,
    timeslotLength: int = 15,
    GNNFormat: bool = False,
    disableWeather: bool = True,
    saveFolder: str = "NNData",
    forceRegenerateData: bool = False,
    start: datetime = datetime(2018, 1, 1),
    end: datetime = datetime(2019, 12, 31),
):
    """Generates NN data for many airports and results all as a dict

    Args:
        airports (list): list of ICAO airport codes
        timeslotLength (int, optional): length to aggregate flights for in minutes. Defaults to 15 minutes.
        GNNFormat: (bool, optional): returns the data in format used for GNN model (Pagg, Y, T). Defaults to False
        disableWeather: (bool, optional): disables weather features:\
                        (["timeslot", "visibility", "windspeed",\
                        "temperature", "frozenprecip", \
                        "surfaceliftedindex", "cape"]). Defaults to True.
        saveFolder (str, optional): folder to save data in. Defaults to "NNData".
        forceRegenerateData (bool, optional): force regeneration of data even if it had already been generated. Defaults to False.
        start (datetime, optional): start date to filter for.
        end (datetime, optional): end date to filter for.

    Returns:
        dict: dictionary of NN data dataframes
    """
    dataDict = {}
    for airport in tqdm(airports):
        result = generateNNdata(
            airport,
            timeslotLength,
            GNNFormat,
            disableWeather,
            saveFolder,
            forceRegenerateData,
            start=start,
            end=end,
        )
        if GNNFormat:
            result = {"X": result[0], "Y": result[1], "T": result[2]}

        dataDict[airport] = result

    return dataDict


def show_heatmap(P: pd.DataFrame, dtkey: str = None):
    """Shows a heatmap of correlations for a pandas df

    Args:
        P (pd.DataFrame): pandas data
        dtkey (str, optional): dt column name for removal. Defaults to None.
    """

    if dtkey is not None:
        P = P.drop([dtkey], axis=1)

    plt.matshow(P.corr(), cmap="RdBu_r", vmin=-1, vmax=1)
    plt.xticks(range(P.shape[1]), P.columns, fontsize=12, rotation=-30)
    plt.gca().xaxis.tick_bottom()
    plt.yticks(range(P.shape[1]), P.columns, fontsize=14)

    cb = plt.colorbar()
    cb.ax.tick_params(labelsize=14)
    plt.title("Feature Correlation Heatmap", fontsize=14)


def show_raw_visualization(P: pd.DataFrame, date_time_key="timeslot"):
    """Show features of an NN dataframe over time

    Args:
        data (pd.dataFrame): pandas dataframe in NN format
        date_time_key (str, optional): column that provides datetime. Defaults to "timeslot".
    """
    ncols = 3
    time_data = P[date_time_key]
    feature_keys = P.columns
    fig, axes = plt.subplots(
        nrows=(len(feature_keys) + ncols - 1) // ncols,
        ncols=ncols,
        figsize=(20, 15),
        dpi=70,
        sharex=True,
    )
    for i in range(len(feature_keys)):
        key = feature_keys[i]
        c = plotcolors[i % (len(plotcolors))]
        t_data = P[key]
        t_data.index = time_data
        t_data.head()
        ax = t_data.plot(
            ax=axes[i // ncols, i % ncols],
            color=c,
            title=key,
            rot=25,
        )
        # ax.legend(key)
        ax.grid()
    plt.tight_layout()


def generateKeplerData(
    airports: list = ICAOTOP10,
    start: datetime = datetime(2019, 3, 1),
    end: datetime = datetime(2019, 4, 1),
    timeslotLength: int = 60,
    availableMonths: list = [3, 6, 9, 12],
    predictions: list = [],
    actual: list = [],
):
    """Function to generate the data for the Kepler gl demo

    Args:
        airports (list, optional): airports to generate data for. Defaults to ICAOTOP10.
        start (datetime, optional): start date of the data, should be same as in ST-GCN. Defaults to datetime(2019, 3, 1).
        end (datetime, optional): end date of the data, should be the same as in the ST-GCN. Defaults to datetime(2019, 4, 1).
        timeslotLength (int, optional): lenght of one timeslot in minutes. Defaults to 60.
        availableMonths (list, optional): months of data available. Defaults to [3, 6, 9, 12].
        predictions (list, optional): Predicted labels. Defaults to [].
        actual (list, optional): Real labels. Defaults to [].

    Returns:
        pd.DataFrame: dataframe will all data ready for the Kepler gl

    """
    airports_data = pd.DataFrame() # Dataframe for data of all the airports
    flights_all = pd.DataFrame() # Dataframe for all flight data
    for airport in tqdm(airports):

        P = generalFilterAirport(start, end, airport)
        P["lowcost"] = P.FlightType != "Traditional Scheduled"
        P["Traditional Scheduled"] = P.FlightType == "Traditional Scheduled"

        # Are flights arriving or departing?
        P["arriving"] = P.ADES == airport
        P["departing"] = P.ADEP == airport

        # Collect the time at which the flights are meant to be at the airport
        P.loc[(P.arriving == True), "Timeslot"] = P.FiledAT
        P.loc[(P.arriving == False), "Timeslot"] = P.FiledOBT

        P.loc[(P.arriving == False), "departuresDepartureDelay"] = P.DepartureDelay
        P.loc[(P.arriving == True), "arrivalsArrivalDelay"] = P.ArrivalDelay

        flights_data = P.copy()
        flights_data = flights_data.drop(
            [
                "ECTRLID",
                "FiledOBT",
                "FiledAT",
                "ActualOBT",
                "ActualDistanceFlown",
                "arriving",
                "departing",
                "ArrivalDelay",
                "DepartureDelay",
                "departuresDepartureDelay",
                "arrivalsArrivalDelay",
                "ActualAT",
                "ACType",
                "ACOperator",
                "FlightType",
                "Traditional Scheduled",
                "lowcost",
            ],
            axis=1,
        )

        flights_all = flights_all.append(flights_data)

        # This creates a new index to ensure that we have no gaps in the timeslots later
        def daterange(start_date, end_date):
            delta = timedelta(minutes=timeslotLength)
            while start_date < end_date:
                if start_date.month in availableMonths:
                    # Only yields the months for which we have
                    # data specified in the argument availableMonths
                    yield start_date
                start_date += delta

        denseDateIndex = daterange(start, end)

        P = P.query("`ADEP` in @airports & `ADES` in @airports")
        Pagg = (
            P.groupby(
                [
                    pd.Grouper(key="Timeslot", freq=f"{timeslotLength}min"),
                ]
            )
            .agg(
                {
                    "departing": "sum",
                    "arriving": "sum",
                    "Traditional Scheduled": "sum",
                    "lowcost": "sum",
                }
            )
            # This ensure that there are no timeslot gaps
            # at the start and end of the dataframe
            .reindex(denseDateIndex, fill_value=0)
            # Engineering some features
            .reset_index()
            .rename(
                columns={
                    "departing": "Total # Departing flights",
                    "arriving": "Total # Arriving flights",
                    "lowcost": "# Lowcost flights",
                    "Traditional Scheduled": "# Traditional flights",
                }
            )
            .round(2)
            .fillna(0)
            .query("`Timeslot` >= @start & `Timeslot` < @end")
            .assign(airport=lambda x: airport)
        )
        # Generate lists to capture arrival delay, departure delay and error
        airport_idx = airports.index(airport)
        pred_arrival = [np.round(x[airport_idx][0], 1) for x in predictions]
        pred_departing = [np.round(x[airport_idx][1], 1) for x in predictions]
        mean_error = []

        for i in range(0, len(predictions)):
            error =  round((abs(predictions[i][airport_idx][0] - actual[i][airport_idx][0]) + abs(predictions[i][airport_idx][1] -actual[i][airport_idx][1]))/2)
            mean_error.append(error)

        # Add calculations to dataframe
        Pagg["Arrival delay"] = pred_arrival
        Pagg["Departure delay"] = pred_departing
        Pagg["Error"] = mean_error
        airports_data = airports_data.append(Pagg)

    # Create folder for data
    if not os.path.exists("keplerData"):
        os.makedirs("keplerData")

    flights_all = flights_all.assign(airport=lambda x: x.ADES).query(
        "`ADEP` in @airports & `ADES` in @airports"
    )

    final = airports_data.merge(flights_all, how="left", on=["airport", "Timeslot"]) 
    final["ADESLat"] = final["airport"].apply(lambda x: airport_dict[x]["latitude"])
    final["ADESLong"] = final["airport"].apply(lambda x: airport_dict[x]["longitude"])
    final.to_csv(
        f"keplerData/Total_ICAOTOP{len(airports)}_{timeslotLength}m_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    )

    return final


if __name__ == "__main__":
    pass
