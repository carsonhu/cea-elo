import sc2reader
from sc2reader.engine.plugins import APMTracker, SelectionTracker
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
import trueskill
from elo import EloRating
from datetime import datetime
from datetime import timedelta
from collections import Counter, deque

import cea_team_name_parser

sc2reader.engine.register_plugin(APMTracker())

UNKNOWN_TEAM = "TEAM_NOT_KNOWN"
EXTRA_GAMES_FILE = "extra_games.csv"
K=80
counts = Counter()



class PlayerObject:
  def __init__(self, name, season, team):
    self.name = name
    self.wins = 0
    self.rating = 1000
    self.glicko = glicko2.Player()
    # long term glicko rating
    self.glicko_longterm = glicko2.Player()
    self.trueskill = trueskill.Rating()
    self.peak_rating = 1000
    self.games = []
    self.teams = {season : team}


  losses = property(fget=lambda self: len(self.games) - self.wins)
  mmr = property(fget=lambda self: max(game.mmr for game in self.games))

  def setRating(self, rating):
    self.rating = rating
    if rating > self.peak_rating:
      self.peak_rating = rating

  def addTeam(self, season, team):
    self.teams[season] = team

  @property
  def race(self):
    race_counter = Counter([game.race for game in self.games])
    return race_counter.most_common(1)[0][0]

  @property
  def opponents_beaten(self):
    return [game.opponent for game in self.games if game.win]

  @property
  def opponents_lost_to(self):
    return [game.opponent for game in self.games if not game.win]

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

  def __init__(self, opponent, race, mmr, win, duration,
               season, glicko_longterm, opp_glicko_longterm):
    self.opponent = opponent
    self.race = race
    self.mmr = mmr
    self.win = win
    self.glicko_rating = glicko_longterm.getRating()
    self.glicko_rd = glicko_longterm.getRd()
    self.opp_glicko_rating = opp_glicko_longterm.getRating()
    self.opp_glicko_rd = opp_glicko_longterm.getRd()
    # self.mmr = mmr
    # self.opponent_mmr = opponent_mmr
    # self.apm = apm
    self.duration = duration
    self.season = season

def print_dictionary(player_dictionary):
  # sorted by number of wins, then by winrate
  with open("ratings.txt", mode='w') as file_object:
    sorted_player_dict = sorted(player_dictionary.items(), key=lambda item: (  # teams_dict[item[1].name.lower()],
        item[1].rating, item[1].wins - item[1].losses, len(item[1].games),  -1 * (len(item[1].games) - item[1].wins)), reverse=True)
    table_data = []
    table_data.append(["Rank", "Elo", "W", "L", "Player", "Race", "Peak Rating"])
    for i in range(len(sorted_player_dict)):
      key = sorted_player_dict[i][0]
      value = sorted_player_dict[i][1]
      table_data.append([str(i+1) + ".", int(value.rating), value.wins, value.losses, value.mostRecentTeam + " " + value.name, value.race, int(value.peak_rating)])
    for row in table_data:
    	print("{: <5} {: <5} {: >5} : {:<10} {: <40} {: <10} {: <10}".format(*row), file=file_object)
      # print('{0:d}  {1:5} : {2}  {3}  {4}'.format(int(value.rating), value.wins, value.losses,value.mostRecentTeam + " " + value.name, value.race))
    #  print("%d : %d %s %s , %d" % (value.rating, value.wins, value.losses,
    #                           value.mostRecentTeam + " " + value.name, value.race))

# Add in extra games
# Games is 2d array: each one has [date, player1, player2, win]
def input_extra_elo(players, games, current_date, season):
  while games[0][0] and current_date > datetime.strptime(games[0][0], "%m/%d/%Y"):
    # Note: doesn't resolve aliases
    player_names = [games[0][1].lower(), games[0][2].lower()]
    for index, player in enumerate(player_names):
      gameObject = GameObject(opponent=player_names[1-index], race="", mmr=0,
                              win=games[0][3].lower() == player,
                              duration=0, season=season,
                              glicko_longterm = players[player].glicko_longterm,
                              opp_glicko_longterm = players[player_names[1 - index]].glicko_longterm)
      players[player].addGames(gameObject)

    winner = games[0][3].lower() == player_names[0]
    update_rating(players[player_names[0]], players[player_names[1]], winner)
    #A,B = EloRating(players[player_names[0]].rating, players[player_names[1]].rating, K, games[0][3].lower() == player_names[0])
    #players[player_names[0]].setRating(A)
    #players[player_names[1]].setRating(B)

    games.popleft()

def update_rating(player1, player2, win):
  
  # Update Elo rating
  A,B = EloRating(player1.rating, player2.rating, K, win)
  player1.rating = A
  player2.rating = B

  # Update Glicko-2 rating
  player1.glicko.update_player([player2.glicko.getRating()], [player2.glicko.getRd()], [win])
  player2.glicko.update_player([player1.glicko.getRating()], [player1.glicko.getRd()], [not win])

  # Update Trueskill rating

  winner, loser = trueskill.rate_1vs1(player1.trueskill, player2.trueskill) if win == 1 else trueskill.rate_1vs1(player2.trueskill, player1.trueskill)
  player1.trueskill = winner if win else loser
  player2.trueskill = loser if win else winner

def update_glicko_longterm(players):
    """Updates Longterm Glicko ratings
    
    Args:
        players (Dict<Player>[String]): Dictionary of players: key is player
            name (lowercase), value is PlayerObject
    """

    # Iterate through seasons in reverse order (oldest to newest)
    for season in reversed(range(len(SEASONS))):
      for player in players.values():
        # First, gather all the glicko ratings in their games
        opp_ratings = []
        opp_rds = []
        win = []
        for game in player.games:
            if game.season == season:
              opp_ratings.append(game.opp_glicko_rating)
              opp_rds.append(game.opp_glicko_rd)
              win.append(game.win)
        if not opp_ratings:
          player.glicko_longterm.did_not_compete()
        else:
          player.glicko_longterm.update_player(opp_ratings, opp_rds, win)




def load_value(replay_filename, value):
  """Gets values from replay file
  
  Args:
      replay_filename (Replay): Replay
      value (String): Key to get from replay. (I.e MMR)
  
  Returns:
      TYPE: Description
  """
  archive = mpyq.MPQArchive(replay_filename)
  jsondata = archive.read_file("replay.gamemetadata.json").decode("utf-8")
  obj = json.loads(jsondata)

  mmrs = [0,0]
  for i in [0,1]:
    mmrs[i] = 0 if value not in obj['Players'][i] else obj['Players'][i][value]
  return mmrs


def calculate_elo(directory, players, teams, aliases, season, games):
  # Using mypq, load the replay file
  matcher = re.compile(r'\.SC2Replay$', re.IGNORECASE)
  replays = [file for file in os.listdir(directory) if matcher.search(file)]
  print("Found %d replays to scan" % len(replays))

  for replay in replays:
    try:
      replay_filename = os.path.join(directory, replay)
      replay_file = sc2reader.load_replay(replay_filename, load_level=2)
      player_list = replay_file.players
      player_names = [player_list[0].name,
                      player_list[1].name]
      player_mmrs = load_value(replay_filename, 'MMR')
      # print(dir(replay_file))

      input_extra_elo(players, games, replay_file.date, season)

      # print(player_list[0].avg_apm)
      #print(replay_file.winner.players[0] == player_list[0])

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i] in aliases:
            player_names[i] = aliases[player_names[i].lower()].lower()
        else:
          player_names[i] = player_names[i].lower()
      
      # Ignore it
      if replay_file.winner is None:
        continue
      # Add them to the player list if they're not there
      for index, player in enumerate(player_list):
        player_name = player_names[index]
        if player_name not in players:
          players[player_name] = PlayerObject(player.name,
                season, find_team(teams, player.name))
        else:
          players[player_name].addTeam(season, find_team(teams, player.name))

      # Loop again to add the games
      for index, player in enumerate(player_list):
        player_name = player_names[index]
        gameObject = GameObject(opponent=player_names[1-index],
          race = player.pick_race,
          mmr = player_mmrs[index],
          win=replay_file.winner.players[0] == player,
          duration=replay_file.real_length,
          season=season,
          glicko_longterm=players[player_name].glicko_longterm,
          opp_glicko_longterm=players[player_names[1 - index]].glicko_longterm)
        players[player_name].addGames(gameObject)

      winner = replay_file.winner.players[0] == player_list[0]

      update_rating(players[player_names[0]], players[player_names[1]], winner)

    except:
      print("Error processing replay: %s" % replay)
      traceback.print_exc()

def make_csv(player_dictionary):
  csv_arr = []
  headers_arr = ["Team Name", "Name", "Wins", "Losses", "Elo (avg=1000)", "Trueskill Rating (avg=25)", "Peak MMR", "Race",
                "Players Defeated", "Players Lost To"]
  with open("cea_season_stats.csv", "w", newline='') as my_csv:
    csvWriter = csv.writer(my_csv, delimiter=',')
    csvWriter.writerow(headers_arr)
    for key, value in player_dictionary.items():
      new_entry = []
      # Name
      new_entry.append(value.mostRecentTeam)
      new_entry.append(value.name)

      # Wins
      new_entry.append(int(value.wins))

      # Losses
      new_entry.append(int(value.losses))

      # Elo
      new_entry.append(int(value.rating))

      # Glicko-2
      # new_entry.append("{} ± {}".format(int(value.glicko.getRating()), int(value.glicko.getRd())) )

      # Trueskill Rating

      new_entry.append("{:.2f} ± {:.1f}".format(value.trueskill.mu, value.trueskill.sigma))

      # MMR
      new_entry.append(int(value.mmr))

      # Race
      new_entry.append(value.race)
      # APM
      # new_entry.append(int(value.apm))

      # Retrieve list of opponents beaten / lost to, with MMR differential.
      def opponent_func(opponents_list, descending):
        new_opponents_list = [opp_nickname for opp_nickname in opponents_list]
        new_opponents_list = sorted(new_opponents_list, key=lambda item: (
            player_dictionary[item].rating), reverse=descending)
        new_opponents_list = [player_dictionary[opponent].name for opponent in new_opponents_list]
        return new_opponents_list

      opponents_beaten = opponent_func(value.opponents_beaten, True)
      opponents_lost_to = opponent_func(value.opponents_lost_to, False)

      # Biggest win
      # new_entry.append("" if not opponents_beaten else opponents_beaten[0])

      # Biggest loss
      # new_entry.append("" if not opponents_lost_to else opponents_lost_to[0])

      # Opponents beaten / lost to
      new_entry.append(" ; ".join(opponents_beaten))
      new_entry.append(" ; ".join(opponents_lost_to))

      csvWriter.writerow(new_entry)
      csv_arr.append(new_entry)
  print("Done creating CSV");

if __name__ == "__main__":
  players = {}
  extra_games = cea_team_name_parser.init_extra_games(EXTRA_GAMES_FILE)

  # Instantiate Trueskill
  trueskill.setup(draw_probability=0)

  # Iterate seasons descending from oldest to newest
  for season in reversed(range(len(SEASONS))):
  #for season in [2,1]:
    teams, aliases = cea_team_name_parser.init_dictionary(teams_file(season))
    calculate_elo(replay_directory(season), players,
                    teams, aliases, season, extra_games)

  # Input extra elo for newest season
  input_extra_elo(players, extra_games, datetime.today(), 0)     
  # input_extra_elo(players, extra_games, datetime(2019, 5, 8, 0), 1)     
  # print_dictionary(players)
  # update_glicko_longterm(players)
  make_csv(players)
  #print(players)
