"""Calculate various statistics for the CEA playerbase, and stores in a spreadsheet.

Attributes:
    counts (Counter): counting number of games
    EXTRA_GAMES_FILE (str): File to be used if we need to input extra games
    K (int): K-value used for elo ratings.
"""
import csv
import json
import os
import re
import string
import sys
import traceback
from datetime import datetime
from datetime import timedelta
from collections import Counter, deque
import mpyq
import sc2reader
import trueskill
import glicko2
import cea_team_name_parser
from sc2reader.engine.plugins import APMTracker, SelectionTracker # unused
from consts import SEASONS, STARTING_DATE, WEEKS
from setup_replays import find_team, replay_directory, teams_file
from zeroNumber import zeroNumber
from elo import EloRating

sc2reader.engine.register_plugin(APMTracker())

UNKNOWN_TEAM = "TEAM_NOT_KNOWN"
EXTRA_GAMES_FILE = "extra_games.csv"
# K is used for elo.
K=80
counts = Counter()

class PlayerObject:
  def __init__(self, name, season, team):
    self.name = name
    self.aliases = set()
    self.wins = 0
    self.rating = 1000
    self.glicko = glicko2.Player()
    # long term glicko rating
    self.glicko_longterm = glicko2.Player()
    self.trueskill = trueskill.Rating()
    self.peak_rating = 1000
    self.games = []
    self.teams = {season : team}
    self.zeroNumber = sys.maxsize


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
    # self.apm = apm
    self.duration = duration
    self.season = season
    
# Add in extra games
# Games is 2d array: each one has [date, player1, player2, win]
def input_extra_elo(players, games, current_date, season):
  """Add in extra games.
  
  Args:
      players (Array[PlayerObject]): array of the 2 players
      games (str[n,4]): Each column is [date, player1, player2, win].
        Each row is a game.
      current_date (datetime): current date. don't process games after date.
      season (int): season. 0 is most recent
  """
  while games and games[0][0] and current_date > datetime.strptime(games[0][0], "%m/%d/%Y"):
    # ISSUE: doesn't resolve aliases, doesn't work if player has not already been processed.
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

    games.popleft()

def update_rating(player1, player2, win):
  """Update player ratings after a game
  
  Args:
      player1 (PlayerObject): 
      player2 (PlayerObject): 
      win (bool): whether player 1 won
  """
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
  def myFunc(replay):
    replay_file = sc2reader.load_replay(os.path.join(directory, replay), load_level=2)
    return replay_file.date
  replays = [file for file in os.listdir(directory) if matcher.search(file)]
  replays.sort(key=myFunc)
  print("Found %d replays to scan" % len(replays))

  for replay in replays:
    try:
      replay_filename = os.path.join(directory, replay)
      replay_file = sc2reader.load_replay(replay_filename, load_level=2)
      player_list = replay_file.players
      player_names = [player_list[0].name,
                      player_list[1].name]
      player_mmrs = load_value(replay_filename, 'MMR')

      input_extra_elo(players, games, replay_file.date, season)

      # ignore 2v2
      if len(replay_file.players) > 2:
        continue

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i].lower() in aliases:
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

  # calculate zero number
  maxPlayer = zeroNumber(player_dictionary)
  headers_arr = ["Team Name", "Name", "Wins", "Losses", "Elo (avg=1000)", "Trueskill Rating (avg=25)", "Peak MMR", maxPlayer + " Number", "Race",
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

      # zero number
      zeroNum = int(value.zeroNumber) if value.zeroNumber < sys.maxsize else ''
      new_entry.append(zeroNum)

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
  #for season in [3]:
    teams, aliases = cea_team_name_parser.init_dictionary(teams_file(season))
    calculate_elo(replay_directory(season), players,
                    teams, aliases, season, extra_games)

  # Input extra elo for newest season
  input_extra_elo(players, extra_games, datetime.today(), 0)     


  make_csv(players)
