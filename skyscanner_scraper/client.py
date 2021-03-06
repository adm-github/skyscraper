# -*- coding: utf-8 -*-
#  client.py
#  skyscraper
#  
#  Created by Antonin Lacombe on 2013-05-23.
#  Copyright 2013 Antonin Lacombe. All rights reserved.
#
import re 
import json
import requests
from django.db import models
from skyscanner_scraper import parsers
from bs4 import BeautifulSoup

URL_DATE_FORMAT = "%y%m%d"

class SkyscannerClient(object):
    search_page = "/flights"
    
    """a simple skyscanner http client"""
    def __init__(self, host='www.skyscanner.net', port='80'):
        super(SkyscannerClient, self).__init__()
        self.host = host
        self.port = port
        self.url = "http://%s:%s" % (self.host, self.port)
        self.session = requests.session()
        
    def get(self, url_path, headers={}):
        """simple get"""
        url = "%s%s" % (self.url, url_path)        
        return self.session.get(url, headers=headers)
    
    def _format_date(self, date):
        """return a well formated date for the url"""
        if date:
            return date.strftime(URL_DATE_FORMAT)
        return ""
        
    def _get_flights_page(self, short_from, short_to, depart_date, return_date):
        """
        method to forge the search request and return the response
        """
        dep_date = self._format_date(depart_date)
        ret_date = self._format_date(return_date)
        search_path = "%s/%s/%s/%s/%s/" % (self.search_page, short_from, short_to, dep_date, ret_date)
        return self.get(search_path)
    
    def _get_session_key(self, flights_page):
        """
        look for the session key in the flights page
        """
        soup = BeautifulSoup(flights_page.content)
        for script in soup.find_all("script", {"type":"text/javascript"}):
            if "SessionKey" in script.text:
                #we have found the good script close, now use re to extract the dict
                import ipdb
                ipdb.set_trace
                js_object = re.search('{(.*)}', script.text).group().encode('utf-8')
                js_object_dict = json.loads(js_object)
                return js_object_dict.get("Query", {}).get("SessionKey", "")
    
    def _get_routedate_v20(self, session_key):
        """
        call the /dataservices/routedate/v2.0/session_key api and return the result
        """
        url_path = "/dataservices/routedate/v2.0/%s?full=true" % (session_key)
        headers = {
            "Host":self.host,
            "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:21.0) Gecko/20100101 Firefox/21.0",
            "Accept":"application/json",
            "X-Requested-With":"XMLHttpRequest",
            "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
        }
        response = self.get(url_path, headers)
        return json.loads(response.content)
        
    def get_stations(self, city_name):
        """
        return some statins instance from the city_name
        use the autosuggest (dataservices/geo/1.0/autosuggest) ajax call to get the right place
        """
        url_path = "/dataservices/geo/v1.0/autosuggest/uk/fr/%s" % (city_name)
        headers = {
            "Host":self.host,
            "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:21.0) Gecko/20100101 Firefox/21.0",
            "Accept":"application/json",
            "X-Requested-With":"XMLHttpRequest",
            "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
        }
        response = self.get(url_path, headers)
        station_info_list = json.loads(response.content)
        station_list = list()
        for station_info in station_info_list:
            station, created = models.get_model("skyscanner_scraper", "Station").objects.get_or_create(
                code=station_info["PlaceId"],
                defaults={
                    'name':station_info["PlaceNameEn"],
                }
            )
            if not station in station_list:
                station_list.append(station)
        return station_list
        
        
    def get_flights(self, short_from, short_to, depart_date, return_date):
        """
        get all the informations to make a request and return a list of flight objects
        """
        #get the flight page
        flight_page = self._get_flights_page(short_from, short_to, depart_date, return_date)
        #extract the session key
        session_key = self._get_session_key(flight_page)
        #then call the api to get a json
        try:
            route_date_dict = self._get_routedate_v20(session_key)
        except ValueError, e:
            raise Exception('No result can be found')
        
        #instanciate a parser
        route_date_parser = parsers.RouteDateParser(route_date_dict)
        query_flight, flights = route_date_parser.parse()
        return query_flight, flights
        