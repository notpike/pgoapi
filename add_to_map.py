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
import pprint
import logging
import requests
import argparse
import getpass
import threading
from Queue import Queue
from secrets import bearer, endpoint, qfile, username, password, useraccs
from flask import Flask
app = Flask(__name__)


# add directory of this file to PATH, so that the package will be found
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# import Pokemon Go API lib
from pgoapi import pgoapi
from pgoapi import utilities as util

# other stuff
from google.protobuf.internal import encoder
from geopy.geocoders import GoogleV3
from s2sphere import Cell, CellId, LatLng


q = Queue()
NEUTRAL = 0
BLUE = 1
RED = 2
YELLOW = 3

log = logging.getLogger(__name__)

#def get_pos_by_name(location_name):
#    geolocator = GoogleV3()
#    loc = geolocator.geocode(location_name)
#
#    log.info('Your given location: %s', loc.address.encode('utf-8'))
#    log.info('lat/long/alt: %s %s %s', loc.latitude, loc.longitude, loc.altitude)
#    
#    return (loc.latitude, loc.longitude, loc.altitude)

def get_cell_ids(lat, long, radius = 10):
    origin = CellId.from_lat_lng(LatLng.from_degrees(lat, long)).parent(15)
    walk = [origin.id()]
    right = origin.next()
    left = origin.prev()

    # Search around provided radius
    for i in range(radius):
        walk.append(right.id())
        walk.append(left.id())
        right = right.next()
        left = left.prev()

    # Return everything
    return sorted(walk)
    
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
    #parser.add_argument("-a", "--auth_service", help="Auth Service ('ptc' or 'google')",
        #required=required("auth_service"))
    #parser.add_argument("-u", "--username", help="Username", required=required("username"))
    #parser.add_argument("-p", "--password", help="Password")
    parser.add_argument("-l", "--location", help="Location", required=required("location"))
    parser.add_argument("-d", "--debug", help="Debug Mode", action='store_true')
    parser.add_argument("-t", "--test", help="Only parse the specified location", action='store_true')
    parser.set_defaults(DEBUG=False, TEST=False)
    config = parser.parse_args()

    # Passed in arguments shoud trump
    for key in config.__dict__:
        if key in load and config.__dict__[key] == None:
            config.__dict__[key] = load[key]

    #if config.__dict__["password"] is None:
        #log.info("Secure Password Input (if there is no password prompt, use --password <pw>):")
        #config.__dict__["password"] = getpass.getpass()
    config.auth_service = "ptc"
    config.__dict__["password"] = password
    config.__dict__["username"] = username

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
    
    #position = get_pos_by_name(config.location)
    location = config.location
    if config.test:
        return
    #get_location(config.username, config.password, location, False)



def get_location(user, psswd, location,pokeOnly):
    splitloc = location.split(",")
    position = (float(splitloc[0]), float(splitloc[1]), 0)
    # instantiate pgoapi 
    api = pgoapi.PGoApi()
    
    # provide player position on the earth
    api.set_position(*position)
    
    if not api.login('ptc', user,psswd):
        return

    # chain subrequests (methods) into one RPC call
    
    # get player profile call
    # ----------------------
    #api.get_player()
    
    # get inventory call
    # ----------------------
    #api.get_inventory()
    
    # get map objects call
    # repeated fields (e.g. cell_id and since_timestamp_ms in get_map_objects) can be provided over a list
    # ----------------------
    cell_ids = get_cell_ids(position[0], position[1])
    timestamps = [0,] * len(cell_ids)
    api.get_map_objects(latitude = util.f2i(position[0]), longitude = util.f2i(position[1]), since_timestamp_ms = timestamps, cell_id = cell_ids)

    # spin a fort 
    # ----------------------
    #fortid = '<your fortid>'
    #lng = <your longitude>
    #lat = <your latitude>
    #api.fort_search(fort_id=fortid, fort_latitude=lat, fort_longitude=lng, player_latitude=f2i(position[0]), player_longitude=f2i(position[1]))
    
    # release/transfer a pokemon and get candy for it
    # ----------------------
    #api.release_pokemon(pokemon_id = <your pokemonid>)
    
    # get download settings call
    # ----------------------
    #api.download_settings(hash="05daf51635c82611d1aac95c0b051d3ec088a930")
    
    # execute the RPC call
    response_dict = api.call()
    handleMapResp(response_dict["responses"]["GET_MAP_OBJECTS"],pokeOnly)
    api.get_map_objects(latitude = util.f2i(position[0]), longitude = util.f2i(position[1]), since_timestamp_ms = timestamps, cell_id = cell_ids)
    response_dict = api.call()
    handleMapResp(response_dict["responses"]["GET_MAP_OBJECTS"],pokeOnly)

    
    # alternative:
    # api.get_player().get_inventory().get_map_objects().download_settings(hash="05daf51635c82611d1aac95c0b051d3ec088a930").call()

def handleMapResp(respdict,pokeOnly):
    pokemonsJSON = json.load(
        open("pokenames.json"))
    bulk = []
    for cell in respdict["map_cells"]:
        if "forts" in cell:
            for fort in cell["forts"]:
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
                if not pokeOnly:
                    bulk.append(createItem(props["type"], fort["id"], p, props))
            
        if "wild_pokemons" in cell:
            for pokemon in cell["wild_pokemons"]:
                pokeid = pokemon["pokemon_data"]["pokemon_id"]
                pokename = pokemonsJSON[str(pokeid)]
                f = {
                  "id": "wild%s" % pokemon["encounter_id"],
                  "type": "wild",
                  "pokemonNumber": pokeid,
                  "TimeTillHiddenMs": pokemon["time_till_hidden_ms"],
                  "WillDisappear": pokemon["time_till_hidden_ms"] + cell["current_timestamp_ms"],
                  "title": "Wild %s" %pokename,
                  "marker-color": "FF0000"
                  }
                p = {"type": "Point", "coordinates": [pokemon["longitude"], pokemon["latitude"]]}

                bulk.append(createItem("pokemon", pokemon["encounter_id"], p, f))
                print("Added %s" % pokemon["encounter_id"])
    dumpToMap(bulk)
    return

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

skipQueue=True
def updateQueueFile():
    global skipQueue
    size = q.qsize()
    print("updating queue with %s"% size)
    if skipQueue:
        return
    try:
        f = open(qfile, "w+")
        f.write("%s" % size)
        f.close()
    except:
        skipQueue = True
def working():
    while True:
        item,pokeOnly = q.get()
        print("Getting location for %s" % item)
        get_location(username,password,item, pokeOnly)
        updateQueueFile()

def working_acct(user):
    while True:
        item,pokeOnly = q.get()
        print("Getting location for %s" % item)
        get_location(user,password,item,pokeOnly)
        updateQueueFile()

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
    q.put(("%s,%s"%(float(lat),float(lon)), True))
    updateQueueFile()
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
    q.put(("%s,%s"%(float(lat),float(lon)), False))
    updateQueueFile()
    return "Queue is %s"% q.qsize()

if __name__ == '__main__':
    main()
    for acct in useraccs:
        print(acct)
        t = threading.Thread(target=working_acct, args=(acct,))
        t.daemon = True
        t.start()
    app.run(host="0.0.0.0")

# vim: set sw=4 ts=4 expandtab : #
