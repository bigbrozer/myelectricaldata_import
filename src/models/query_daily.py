import json
import logging
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from config import DAILY_MAX_DAYS, URL
from dependencies import daterange
from init import CONFIG, DB
from models.query import Query, error_response
from models.stat import Stat



class Daily:
    """
    The 'Daily' class represents a daily data retrieval and manipulation process for a specific usage point. It provides methods for fetching, resetting, deleting, and blacklisting daily data.

    Attributes:
        config (dict): The configuration settings.
        db (object): The database object.
        url (str): The base URL for API requests.
        max_daily (int): The maximum number of days to retrieve data for.
        date_format (str): The format of dates.
        date_detail_format (str): The format of detailed dates.
        headers (dict): The headers for API requests.
        usage_point_id (str): The ID of the usage point.
        usage_point_config (object): The configuration settings for the usage point.
        contract (object): The contract associated with the usage point.
        daily_max_days (int): The maximum number of days for daily data.
        max_days_date (datetime): The maximum date for retrieving data.
        activation_date (datetime): The activation date for retrieving data.
        measure_type (str): The type of measurement (consumption or production).
        base_price (float): The base price for the measurement type.

    Methods:
        run(begin, end):
            Retrieves and stores daily data for a specified date range.

        get():
            Retrieves and returns all available daily data for the usage point.

        reset(date=None):
            Resets the daily data for the usage point, optionally for a specific date.

        delete(date=None):
            Deletes the daily data for the usage point, optionally for a specific date.

        fetch(date):
            Fetches and returns the daily data for a specific date.

        blacklist(date, action):
            Adds or removes a date from the blacklist for the usage point.

    Note:
        The 'Daily' class relies on the 'Query' class for making API requests and the 'Stat' class for retrieving additional statistics.

    Example usage:
        headers = {"Authorization": "Bearer token"}
        usage_point_id = "1234567890"
        daily = Daily(headers, usage_point_id)
        data = daily.get()
        for item in data:
            print(item)
    """

    def __init__(self, headers, usage_point_id, measure_type="consumption"):
        self.config = CONFIG
        self.db = DB
        self.url = URL
        self.max_daily = 1095
        self.date_format = "%Y-%m-%d"
        self.date_detail_format = "%Y-%m-%d %H:%M:%S"
        self.headers = headers
        self.usage_point_id = usage_point_id
        self.usage_point_config = self.db.get_usage_point(self.usage_point_id)
        self.contract = self.db.get_contract(self.usage_point_id)
        self.daily_max_days = int(DAILY_MAX_DAYS)
        self.max_days_date = datetime.utcnow() - timedelta(days=self.daily_max_days)
        if (
            measure_type == "consumption"
            and hasattr(self.usage_point_config, "consumption_max_date")
            and self.usage_point_config.consumption_max_date != ""
            and self.usage_point_config.consumption_max_date is not None
        ):
            self.activation_date = self.usage_point_config.consumption_max_date
        elif (
            measure_type == "production"
            and hasattr(self.usage_point_config, "production_max_date")
            and self.usage_point_config.production_max_date != ""
            and self.usage_point_config.production_max_date is not None
        ):
            self.activation_date = self.usage_point_config.production_max_date
        elif (
            hasattr(self.contract, "last_activation_date")
            and self.contract.last_activation_date != ""
            and self.contract.last_activation_date is not None
        ):
            self.activation_date = self.contract.last_activation_date
        else:
            self.activation_date = self.max_days_date
        self.measure_type = measure_type
        self.base_price = 0
        if measure_type == "consumption":
            if hasattr(self.usage_point_config, "consumption_price_base"):
                self.base_price = self.usage_point_config.consumption_price_base
        else:
            if hasattr(self.usage_point_config, "production_price"):
                self.base_price = self.usage_point_config.production_price

    def run(self, begin, end):
        begin_str = begin.strftime(self.date_format)
        end_str = end.strftime(self.date_format)
        logging.info(f"Récupération des données : {begin_str} => {end_str}")
        endpoint = f"daily_{self.measure_type}/{self.usage_point_id}/start/{begin_str}/end/{end_str}"
        # if begin < now() - timedelta(days=7):
        if hasattr(self.usage_point_config, "cache") and self.usage_point_config.cache:
            endpoint += "/cache"
        try:
            current_data = self.db.get_daily(self.usage_point_id, begin, end, self.measure_type)
            if not current_data["missing_data"]:
                logging.info(" => Toutes les données sont déjà en cache.")
                output = []
                for date, data in current_data["date"].items():
                    output.append({"date": date, "value": data["value"]})
                return output
            else:
                logging.info(f" Chargement des données depuis MyElectricalData {begin_str} => {end_str}")
                data = Query(endpoint=f"{self.url}/{endpoint}/", headers=self.headers).get()
                if data is None or data.status_code != 200:
                    return error_response(data)
                blacklist = 0
                max_histo = datetime.combine(datetime.now(), datetime.max.time()) - timedelta(days=1)
                meter_reading = json.loads(data.text)["meter_reading"]
                interval_reading = meter_reading["interval_reading"]
                interval_reading_tmp = {}
                for interval_reading_data in interval_reading:
                    interval_reading_tmp[interval_reading_data["date"]] = interval_reading_data["value"]
                for single_date in daterange(begin, end):
                    if single_date < max_histo:
                        if single_date.strftime(self.date_format) in interval_reading_tmp:
                            # FOUND
                            self.db.insert_daily(
                                usage_point_id=self.usage_point_id,
                                date=datetime.combine(single_date, datetime.min.time()),
                                value=interval_reading_tmp[single_date.strftime(self.date_format)],
                                blacklist=blacklist,
                                measurement_direction=self.measure_type,
                            )
                        else:
                            # NOT FOUND
                            self.db.daily_fail_increment(
                                usage_point_id=self.usage_point_id,
                                date=datetime.combine(single_date, datetime.min.time()),
                                measurement_direction=self.measure_type,
                            )
                return interval_reading
        except Exception as e:
            logging.exception(e)
            logging.error(e)

    def get(self):
        """Fetch (and cache) the daily data, from today back to the activation / max history date."""
        end = datetime.combine((datetime.now() + timedelta(days=2)), datetime.max.time())
        begin = datetime.combine(end - relativedelta(days=self.max_daily), datetime.min.time())
        finish = True
        result = []
        while finish:
            if self.max_days_date > begin:
                # Max day reached
                begin = self.max_days_date
                finish = False
                response = self.run(begin, end)
            elif self.activation_date and self.activation_date > begin:
                # Activation date reached
                begin = self.activation_date
                finish = False
                response = self.run(begin, end)
            else:
                response = self.run(begin, end)
                begin = begin - relativedelta(days=self.max_daily)
                end = end - relativedelta(days=self.max_daily)
            if response is None:
                response = {
                    "error": True,
                    "description": "MyElectricalData est indisponible.",
                }
            if isinstance(response, list):
                result = [*result, *response]
            elif response.get("error"):
                if response.get("exit"):
                    finish = False
                logging.error("Echec de la récupération des données.")
                logging.error(f' => {response["description"]}')
                logging.error(f" => {begin.strftime(self.date_format)} -> {end.strftime(self.date_format)}")
                if response.get("status_code") in (400, 409):
                    finish = False
                    logging.error("Arrêt de la récupération des données suite à une erreur.")
                    logging.error(
                        f"Prochain lancement à {datetime.now() + timedelta(seconds=self.config.get('cycle') or 0)}"
                    )
        return result

    def reset(self, date=None):
        if date is not None:
            date = datetime.strptime(date, self.date_format)
        self.db.reset_daily(self.usage_point_id, date, self.measure_type)
        return True

    def delete(self, date=None):
        if date is not None:
            date = datetime.strptime(date, self.date_format)
        self.db.delete_daily(self.usage_point_id, date, self.measure_type)
        return True

    def fetch(self, date):
        if date is not None:
            date = datetime.strptime(date, self.date_format)
        result = self.run(
            datetime.combine(date - timedelta(days=2), datetime.min.time()),
            datetime.combine(date + timedelta(days=2), datetime.min.time()),
        )
        if not isinstance(result, list):
            return {
                "error": True,
                "notif": (result or {}).get("description", "MyElectricalData est indisponible."),
                "fail_count": self.db.get_daily_fail_count(self.usage_point_id, date, self.measure_type),
            }
        for item in result:
            if date.strftime(self.date_format) in item["date"]:
                item["hc"] = Stat(self.usage_point_id, self.measure_type).get_daily(date, "hc")
                item["hp"] = Stat(self.usage_point_id, self.measure_type).get_daily(date, "hp")
                return item
        return {
            "error": True,
            "notif": f"Aucune donnée n'est disponible chez Enedis sur cette date ({date})",
            "fail_count": self.db.get_daily_fail_count(self.usage_point_id, date, self.measure_type),
        }

    def blacklist(self, date, action):
        if date is not None:
            date = datetime.strptime(date, self.date_format)
        self.db.blacklist_daily(self.usage_point_id, date, action, self.measure_type)
        return True
