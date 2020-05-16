import sc2reader
from sc2reader.engine.plugins import APMTracker, SelectionTracker
from consts import SEASONS, STARTING_DATE, WEEKS
from setup_replays import find_team, replay_directory, teams_file
import os
import re
import string
import traceback
from datetime import datetime
from datetime import timedelta
from collections import Counter

import cea_team_name_parser

sc2reader.engine.register_plugin(APMTracker())

UNKNOWN_TEAM = "TEAM_NOT_KNOWN"
counts = Counter()

class PlayerObject:
  def __init__(self, name, season, team):
    self.name = name
    self.wins = 0
    self.rating = 1000
    self.games = []
    self.teams = {season : team}

  losses = property(fget=lambda self: len(self.games) - self.wins)

  def addTeam(self, season, team):
    self.teams[season] = team

  @property
  def race(self):
    race_counter = Counter([game.race for game in self.games])
    return race_counter.most_common(1)[0][0]

  @property
  def mostRecentTeam(self):
    return self.teams[sorted(list(self.teams.keys()))[0]]


  def addGames(self, game):
    self.games.append(game)
    if game.win:
      self.wins += 1



class GameObject:

  """ Struct containing information about a game, given 1 player.

  Attributes:
      duration (int): Length of the game in seconds
      opponent (str): Name of the opponent
      race (str): Selected race
  """

  def __init__(self, opponent, race, win, duration):
    self.opponent = opponent
    self.race = race
    self.win = win
    # self.mmr = mmr
    # self.opponent_mmr = opponent_mmr
    # self.apm = apm
    self.duration = duration

def print_dictionary(player_dictionary):
  # sorted by number of wins, then by winrate
  num_columns = 2
  sorted_player_dict = sorted(player_dictionary.items(), key=lambda item: (  # teams_dict[item[1].name.lower()],
      item[1].wins - item[1].losses, len(item[1].games),  -1 * (len(item[1].games) - item[1].wins)))
  for i in range(len(sorted_player_dict)):
    key = sorted_player_dict[i][0]
    value = sorted_player_dict[i][1]
    print("%d : %d %s %s" % (value.wins, value.losses,
                             value.mostRecentTeam + " " + value.name, value.race))



def calculate_elo(directory, players, teams, aliases, season):
  # Using mypq, load the replay file
  matcher = re.compile(r'\.SC2Replay$', re.IGNORECASE)
  replays = [file for file in os.listdir(directory) if matcher.search(file)]
  print("Found %d replays to scan" % len(replays))

  for replay in replays:
    try:
      replay_file = sc2reader.load_replay(os.path.join(directory,replay), load_level=2)
      player_list = replay_file.players
      player_names = [player_list[0].name,
                      player_list[1].name]
      # print(player_list[0].avg_apm)
      #print(replay_file.winner.players[0] == player_list[0])

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i] in aliases:
            player_names[i] = aliases[player_names[i].lower()]
      
      # Ignore it
      if replay_file.winner is None:
        continue

      # Add them to the player list if they're not there
      for index, player in enumerate(player_list):
        if player.name not in players:
          players[player.name] = PlayerObject(player.name,
                season, find_team(teams, player.name))
        else:
          players[player.name].addTeam(season, find_team(teams, player.name))

        gameObject = GameObject(opponent=player_names[1-index],
          race = player.pick_race,
          win=replay_file.winner.players[0] == player,
          duration=replay_file.real_length)
        players[player.name].addGames(gameObject)
    except:
      print("Error processing replay: %s" % replay)
      traceback.print_exc()

if __name__ == "__main__":
  players = {}

  for season in reversed(range(len(SEASONS))):
    teams, aliases = cea_team_name_parser.init_dictionary(teams_file(season))
    calculate_elo(replay_directory(season), players,
                    teams, aliases, season)
  print_dictionary(players)
  #print(players)
