import sc2reader
from consts import SEASONS, STARTING_DATE, WEEKS
from setup_replays import find_team, replay_directory, teams_file
import os
import re
import string
import json
import csv
import glicko2
import mpyq
import traceback
import time
import trueskill
from elo import EloRating
from datetime import datetime
from datetime import timedelta
from collections import Counter, deque
from bs4 import BeautifulSoup, Tag
import requests

import cea_team_name_parser

def getRankedFTW(players):
  playersDict = {}
  for key, value in players.items():
    time.sleep(0.1)
    #print('/'.join(value.split('/')[:-2]))
    rUrl = "http://www.rankedftw.com/search/?name=" + value
    print(rUrl)
    response = requests.get(rUrl)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    href_tags = soup.find_all("a", {"class": "team"}, href = True)
    #print(href_tags)
    ftwUrl = ""
    for tag in href_tags:
      if tag.text.strip() == "1v1":
        ftwUrl = "http://www.rankedftw.com" + tag.get('href') + "rankings/"
    
      #if '1v1' in tag.get('href'):
      #  ftwUrl = "http://www.rankedftw.com" + tag.get('href') + "/ranking/"
    print(ftwUrl)
    response2 = requests.get(ftwUrl)
    response2.encoding = 'utf-8'
    soup2 = BeautifulSoup(response2.text, 'html.parser')
    asdf = json.loads(soup2.get_text())
    playersDict[key] = asdf
    return playersDict


def getPlayerProfiles(directory, players, teams, aliases, season):
  # Using mypq, load the replay file
  matcher = re.compile(r'\.SC2Replay$', re.IGNORECASE)
  replays = [file for file in os.listdir(directory)
             if matcher.search(file)]
  print("Found %d replays to scan" % len(replays))
  for replay in replays:
    try:
      replay_filename = os.path.join(directory, replay)
      replay_file = sc2reader.load_replay(replay_filename, load_level=2)
      archive = mpyq.MPQArchive(replay_filename)
      jsondata = archive.read_file("replay.gamemetadata.json").decode("utf-8")
      obj = json.loads(jsondata)
      player_list = replay_file.players
      player_names = [player_list[0].name,
                      player_list[1].name]

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i] in aliases:
            player_names[i] = aliases[player_names[i].lower()].lower()
        else:
          player_names[i] = player_names[i].lower()
      
          getURL = lambda i : 0 if 'url' not in dir(replay_file.players[i]) else replay_file.players[i].url
          players[player_names[0]] = '/'.join(getURL(0).split('/')[:-2])
          players[player_names[1]] = getURL(1)
    except:
      print("Error processing replay: %s" % replay)
      traceback.print_exc() 

if __name__ == "__main__":
  # This is a dictionary which will track player name -> json
  # players = {}
  # for season in reversed(range(len(SEASONS))):
  #     teams, aliases = cea_team_name_parser.init_dictionary(teams_file(season))
  #     getPlayerProfiles(replay_directory(season), players,
  #                   teams, aliases, season)
  
  testPlayers = {'gyalgatine': 
    'http://us.battle.net/sc2/en/profile/454026/1/Gyalgatine/'}
  playersDict = getRankedFTW(testPlayers)
  with open('playerMMR.json', 'w') as fp:
    json.dump(playersDict, fp)
