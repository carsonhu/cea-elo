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
import xlsxwriter
import pandas as pd
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

  def isActive(self):
    return 0 in self.teams

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

  def __init__(self, opponent, race, opponent_race, map_name, mmr, win, duration,
               season, glicko_longterm, opp_glicko_longterm):
    self.opponent = opponent
    self.race = race
    self.opponent_race = opponent_race
    self.mmr = mmr
    self.win = win
    self.map = map_name
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
      # add them in if not in there
      if player not in players:
        players[player] = PlayerObject(player,
                season, find_team(teams, player))
    for index, player in enumerate(player_names):
      gameObject = GameObject(opponent=player_names[1-index], race="", opponent_race="", map_name="", mmr=0,
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
        print(replay)
        continue

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i].lower() in aliases:
            player_names[i] = aliases[player_names[i].lower()].lower()
        else:
          player_names[i] = player_names[i].lower()
      
      # Ignore it
      if replay_file.winner is None:
        print(replay)
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
          opponent_race=player_list[1-index].pick_race,
          map_name = replay_file.map_name,
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

def writeProfile(value, workbook, player_dictionary):
  if value.name not in workbook.sheetnames:
    sheet_name = value.name
  else:
    sheet_name = value.name + ' 1'
  playerWorksheet = workbook.add_worksheet(sheet_name)
  main_sheet = "Main"
  playerWorksheet.write_url(0, 0, f"internal:'{main_sheet}'!A1", string='Back to Main Sheet')
  playerWorksheet.write(0, 1, 'Player Name')
  playerWorksheet.write(1, 1, value.name)
  playerWorksheet.set_column(1, 1, max(len('Player Name'), len(value.name))+1)
  playerWorksheet.write(0, 2, 'Teams')
  playerWorksheet.set_column(2, 2, 20)
  playerWorksheet.set_column(3, 4, 12)
  playerWorksheet.write(0, 4, 'Games')
  playerWorksheet.write(0, 5, 'Opponent Team')
  playerWorksheet.set_column(5, 5, 15)
  playerWorksheet.write(0, 6, 'Opponent')
  playerWorksheet.set_column(6, 6, 15)
  playerWorksheet.write(0, 7, 'Player Race')
  playerWorksheet.set_column(7, 7, 8)
  playerWorksheet.write(0, 8, 'Opponent Race')
  playerWorksheet.set_column(8, 8, 8)
  playerWorksheet.write(0, 9, 'Match Result')
  playerWorksheet.set_column(9, 9, 6)
  playerWorksheet.write(0, 10, 'Map')
  playerWorksheet.set_column(10, 10, 20)
  playerWorksheet.write(0, 12, 'Records')
  playerWorksheet.set_column(12, 12, 25)

  index = 1
  for season, team in value.teams.items():
    startIndex = 2
    playerWorksheet.write(index, startIndex, team)
    playerWorksheet.write(index, startIndex + 1, SEASONS[season])
    index += 1
  indexGame = 1
  for game in value.games:
    win = "Win" if game.win else "Loss"
    startIndex = 4
    playerWorksheet.write(indexGame, startIndex, SEASONS[game.season])
    if game.season in player_dictionary[game.opponent].teams:
      oppTeam = player_dictionary[game.opponent].teams[game.season]
    else:
      oppTeam = "UNKOWN_TEAM"
    playerWorksheet.write(indexGame, startIndex + 1, oppTeam)
    playerWorksheet.write(indexGame, startIndex + 2, player_dictionary[game.opponent].name)
    playerWorksheet.write(indexGame, startIndex + 3, game.race)
    playerWorksheet.write(indexGame, startIndex + 4, game.opponent_race)
    playerWorksheet.write(indexGame, startIndex + 5, win)
    playerWorksheet.write(indexGame, startIndex + 6, game.map)
    indexGame += 1

  # For Player Records
  opponentsBeaten = Counter(value.opponents_beaten)
  opponentsLostTo = Counter(value.opponents_lost_to)
  indexRecord = 1

  for opponent in set(value.opponents_beaten + value.opponents_lost_to):
    count = 0
    startIndex = 12
    if opponent in opponentsBeaten:
      count += opponentsBeaten[opponent]
    if opponent in opponentsLostTo:
      count += opponentsLostTo[opponent]
    if count >= 2:
      playerWorksheet.write(indexRecord, startIndex, player_dictionary[opponent].name)
      playerWorksheet.write(indexRecord, startIndex+1, "{0}:{1}".format(opponentsBeaten[opponent], opponentsLostTo[opponent]))
      indexRecord += 1

  return sheet_name

def write_profiles(player_dictionary):
  workbook = xlsxwriter.Workbook('cea_season_stats.xlsx')
  index = 0
  for key, value in player_dictionary.items():
    writeProfile(value, workbook, player_dictionary)
    index +=1
  workbook.close()

def make_csv(player_dictionary):
  # calculate zero number
  maxPlayer = zeroNumber(player_dictionary)
  headers_arr = ["Team Name", "Name", "Wins", "Losses", "Elo (avg=1000)", "Trueskill Rating (avg=25)", "Peak MMR", maxPlayer + " Number", "Active", "Race",
                "Players Defeated", "Players Lost To"]
  workbook = xlsxwriter.Workbook('cea_season_stats.xlsx')
  worksheet1 = workbook.add_worksheet("Main")
  worksheet1.write_row(0, 0, headers_arr)
  worksheet1.freeze_panes(1, 0)
  worksheet1.autofilter('A1:L9999')
  index = 0
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

    new_entry.append("Yes" if value.isActive() else "No")

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

    worksheet1.write_row(index + 1, 0, new_entry)
    playerSheet = writeProfile(value, workbook, player_dictionary)
    worksheet1.write_url(index + 1, 1, f"internal:'{playerSheet}'!A1", string=value.name)
    index += 1
  worksheet1.conditional_format('E2:E9999', {'type': '3_color_scale'})
  print("Done creating CSV")
  workbook.close()

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
  #write_profiles(players)
