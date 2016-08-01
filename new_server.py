#!/usr/bin/env python
"""
pgoapi - Pokemon Go API
Copyright (c) 2016 tjado <https://github.com/tejado>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
OR OTHER DEALINGS IN THE SOFTWARE.

Author: tjado <https://github.com/tejado>
"""

import os
import re
import sys
import json
import time
import struct
import random
import logging
import requests
import argparse
import threading
from Queue import Queue
from secrets import bearer, endpoint, username, password, useraccs, do_lots, default_position
from flask import Flask
app = Flask(__name__)

from pgoapi import PGoApi
from pgoapi.utilities import f2i, h2f

from google.protobuf.internal import encoder
from geopy.geocoders import GoogleV3
from s2sphere import Cell, CellId, LatLng

NEUTRAL = 0
BLUE = 1
RED = 2
YELLOW = 3
log = logging.getLogger(__name__)
q = Queue()

def get_pos_by_name(location_name):
    geolocator = GoogleV3()
    loc = geolocator.geocode(location_name)

    log.info('Your given location: %s', loc.address.encode('utf-8'))
    log.info('lat/long/alt: %s %s %s', loc.latitude, loc.longitude, loc.altitude)

    return (loc.latitude, loc.longitude, loc.altitude)

def get_cellid(lat, long):
    origin = CellId.from_lat_lng(LatLng.from_degrees(lat, long)).parent(15)
    walk = [origin.id()]

    # 10 before and 10 after
    next = origin.next()
    prev = origin.prev()
    for i in range(10):
        walk.append(prev.id())
        walk.append(next.id())
        next = next.next()
        prev = prev.prev()
    return sorted(walk)
    #return ''.join(map(encode, sorted(walk)))

def encode(cellid):
    output = []
    encoder._VarintEncoder()(output.append, cellid)
    return ''.join(output)

def init_config():
    parser = argparse.ArgumentParser()
    config_file = "config.json"

    # If config file exists, load variables from json
    load   = {}
    if os.path.isfile(config_file):
        with open(config_file) as data:
            load.update(json.load(data))

    # Read passed in Arguments
    required = lambda x: not x in load
    parser.add_argument("-a", "--auth_service", help="Auth Service ('ptc' or 'google')",
        required=required("auth_service"))
    parser.add_argument("-u", "--username", help="Username", required=required("username"))
    parser.add_argument("-p", "--password", help="Password", required=required("password"))
    parser.add_argument("-l", "--location", help="Location", required=required("location"))
    parser.add_argument("-d", "--debug", help="Debug Mode", action='store_true')
    parser.add_argument("-t", "--test", help="Only parse the specified location", action='store_true')
    parser.set_defaults(DEBUG=False, TEST=False)
    config = parser.parse_args()

    # Passed in arguments shoud trump
    for key in config.__dict__:
        if key in load and config.__dict__[key] == None:
            config.__dict__[key] = load[key]

    if config.auth_service not in ['ptc', 'google']:
      log.error("Invalid Auth service specified! ('ptc' or 'google')")
      return None

    return config

def main():
    # log settings
    # log format
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(module)10s] [%(levelname)5s] %(message)s')
    # log level for http request class
    logging.getLogger("requests").setLevel(logging.WARNING)
    # log level for main pgoapi class
    logging.getLogger("pgoapi").setLevel(logging.INFO)
    # log level for internal pgoapi class
    logging.getLogger("rpc_api").setLevel(logging.INFO)

    config = init_config()
    if not config:
        return

    if config.debug:
        logging.getLogger("requests").setLevel(logging.DEBUG)
        logging.getLogger("pgoapi").setLevel(logging.DEBUG)
        logging.getLogger("rpc_api").setLevel(logging.DEBUG)

    splitloc = config.location.split(",")
    position = (float(splitloc[0]), float(splitloc[1]), 0)
    if config.test:
        return

    # instantiate pgoapi
    api = PGoApi()

    # provide player position on the earth
    api.set_position(*position)

    if not api.login(config.auth_service, config.username, config.password):
        return

    # chain subrequests (methods) into one RPC call

    # get player profile call
    # ----------------------
    #api.get_player()

    # execute the RPC call
    #response_dict = api.call()
    #print('Response dictionary: \n\r{}'.format(json.dumps(response_dict, indent=2)))
    #find_poi(api, position[0], position[1])
def make_api(user, passwd):
    api = PGoApi()

    # provide player position on the earth
    api.set_position(*default_position)

    if not api.login('ptc', user, passwd):
        return
    return api

def find_poi(api, lat, lng, pokeOnly):
    poi = {'pokemons': {}, 'forts': {}}
    step_size = 0.0010
    step_limit = 1
    if pokeOnly:
        step_limit = 49
    coords = generate_spiral(lat, lng, step_size, step_limit)
    for coord in coords:
        time.sleep(0.3)
        lat = coord['lat']
        lng = coord['lng']
        api.set_position(lat, lng, 0)

        cellid = get_cellid(lat, lng)
        print("Getting %s %s"% (lat, lng))
        timestamp = [0,] * len(cellid)

        api.get_map_objects(latitude=f2i(lat), longitude=f2i(lng), since_timestamp_ms=timestamp, cell_id=cellid)

        response_dict = api.call()
        if response_dict['responses']['GET_MAP_OBJECTS']['status'] == 1:
            for map_cell in response_dict['responses']['GET_MAP_OBJECTS']['map_cells']:
                if 'forts' in map_cell:
                    for fort in map_cell['forts']:
                        poi["forts"][fort["id"]] = fort
                if 'wild_pokemons' in map_cell:
                    for pokemon in map_cell['wild_pokemons']:
                        poi['pokemons'][pokemon["encounter_id"]] = pokemon

        # time.sleep(0.51)
    bulk=[]
    for fortid in poi["forts"]:
        fort = poi["forts"][fortid]
        props = {
            "id": fort["id"],
            "LastModifiedMs": fort["last_modified_timestamp_ms"]
            }

        p = {"type": "Point", "coordinates": [fort["longitude"],fort["latitude"]]}
        if "type" in fort:
          props["marker-symbol"] = "circle"
          props["title"] = "PokeStop"
          props["type"] = "pokestop"
          props["lure"] = "lure_info" in fort
        else:
          props["marker-symbol"] = "town-hall"
          props["marker-size"] = "large"
          props["type"] = "gym"

        if "owned_by_team" in fort:
           if fort["owned_by_team"] == BLUE:
             props["marker-color"] = "0000FF"
             props["title"] = "Blue Gym"
           elif fort["owned_by_team"] == RED:
             props["marker-color"] = "FF0000"
             props["title"] = "Red Gym"
           elif fort["owned_by_team"] == YELLOW:
             props["marker-color"] = "FF0000"
             props["title"] = "Yellow Gym"
        else:
            if "lure_info" in fort:
                print("This should have lure info")
                print(fort)
                props["lure"] = True
                props["lure_info"] = fort["lure_info"]
                t = createItem(props["type"], fort["id"], p, props)
                print(t)
            props["marker-color"] = "808080"
        if pokeOnly == False:
            bulk.append(createItem(props["type"], fort["id"], p, props))
            print("adding pokestop")
    
    pokemonsJSON = json.load(
        open("pokenames.json"))
    print("made big")
    for encounter in poi["pokemons"]:
        pokemon = poi["pokemons"][encounter]
        pokeid = pokemon["pokemon_data"]["pokemon_id"]
        pokename = pokemonsJSON[str(pokeid)]
        f = {
          "id": "wild%s" % pokemon["encounter_id"],
          "type": "wild",
          "pokemonNumber": pokeid,
          "TimeTillHiddenMs": pokemon["time_till_hidden_ms"],
          "WillDisappear": pokemon["time_till_hidden_ms"] + int(time.time()*1000),
          "title": "Wild %s" %pokename,
          "marker-color": "FF0000"
          }
        p = {"type": "Point", "coordinates": [pokemon["longitude"], pokemon["latitude"]]}

        if pokeOnly:
            bulk.append(createItem("pokemon", pokemon["encounter_id"], p, f))
    print('POI dictionary: \n\r{}'.format(json.dumps(bulk, indent=2)))
    print(time.time())
    dumpToMap(bulk)
    print(time.time())
    print('Open this in a browser to see the path the spiral search took:')
    print_gmaps_dbug(coords)

def get_key_from_pokemon(pokemon):
    return '{}-{}'.format(pokemon['spawnpoint_id'], pokemon['pokemon_data']['pokemon_id'])

def print_gmaps_dbug(coords):
    url_string = 'http://maps.googleapis.com/maps/api/staticmap?size=400x400&path='
    for coord in coords:
        url_string += '{},{}|'.format(coord['lat'], coord['lng'])
    print(url_string[:-1])

def generate_spiral(starting_lat, starting_lng, step_size, step_limit):
    coords = [{'lat': starting_lat, 'lng': starting_lng}]
    steps,x,y,d,m = 1, 0, 0, 1, 1
    rlow = 0.0
    rhigh = 0.0005

    while steps < step_limit:
        while 2 * x * d < m and steps < step_limit:
            x = x + d
            steps += 1
            lat = x * step_size + starting_lat + random.uniform(rlow, rhigh)
            lng = y * step_size + starting_lng + random.uniform(rlow, rhigh)
            coords.append({'lat': lat, 'lng': lng})
#DOUBLE IT UP
            coords.append({'lat': lat, 'lng': lng})
        while 2 * y * d < m and steps < step_limit:
            y = y + d
            steps += 1
            lat = x * step_size + starting_lat + random.uniform(rlow, rhigh)
            lng = y * step_size + starting_lng + random.uniform(rlow, rhigh)
            coords.append({'lat': lat, 'lng': lng})
#DOUBLE IT UP
            coords.append({'lat': lat, 'lng': lng})

        d = -1 * d
        m = m + 1
    return coords

def createItem(dataType, uid, location, properties=None):
    item = {"type":dataType, "uid":uid,"location":location,"properties":properties}
    return item

def dumpToMap(data):
    if bearer == "":
        return
    if len(data) == 0:
        return
    headers = {"Authorization" : "Bearer %s" % bearer}
    r = requests.post("%s/api/push/mapobject/bulk" % endpoint, json = data, headers = headers)
    print("Successfully sent!")

@app.route("/")
def retQueue():
  size = q.qsize()
  return "%s" % size

prevreq = []
@app.route('/addPokemon/<lat>/<lon>')
def addPokemon(lat,lon):
    global prevreq
    if (lat,lon) in prevreq:
        print("They suck")
        return "You suck"
    if abs(float(lon)) > 180:
        return "Too big!"
    if len(prevreq) >=20:
        prevreq.pop()
    prevreq.append((lat,lon))
    #for nlat, nlon in get_surrounding(float(lat),float(lon)):
    q.put(((float(lat),float(lon)), True))
    return "Queue is %s"% q.qsize()

@app.route('/addToQueue/<lat>/<lon>')
def addToQueue(lat,lon):
    global prevreq
    if (lat,lon) in prevreq:
        print("They suck")
        return "You suck"
    if abs(float(lon)) > 180:
        return "Too big!"
    if len(prevreq) >=20:
        prevreq.pop()
    prevreq.append((lat,lon))
    q.put(((float(lat),float(lon)), False))
    return "Queue is %s"% q.qsize()

def worker(user, passwd):
    api = make_api(user, passwd)
    print("%s logged in" % user)
    while True:
        position, pokeOnly = q.get()
        try:
            find_poi(api, position[0], position[1], pokeOnly)
        except Exception as e:
            print(e)
            api = make_api(user, passwd)
            q.put((position, pokeOnly))
if __name__ == '__main__':
    for acct in useraccs:
        t = threading.Thread(target=worker, args=(acct,password))
        t.daemon = True
        t.start()
    app.run(host="0.0.0.0", port=5000)
