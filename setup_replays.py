import sc2reader
from consts import SEASONS, STARTING_DATE, WEEKS
import os
import re
import string
import shutil
import traceback
from datetime import datetime
from datetime import timedelta
from collections import Counter

import cea_team_name_parser

UNKNOWN_TEAM = "TEAM_NOT_KNOWN"
counts = Counter()

def replay_directory(season):
	return "UploadHere/" + SEASONS[season]
def teams_file(season):
	return "data/cea_names/" + SEASONS[season] + "_cea_names.csv"

def define_cea_date_ranges(season):
  """Starts with preseason, March 16 2019 12:00.

  Returns:
      Array: Array containing the dates of each CEA week
  """
  num_weeks = 14
  weeks = []

  weeks.append(datetime.strptime(STARTING_DATE[season]+"12",'%Y%m%d%H'))
  d = timedelta(days=7)
  for i in range(1,num_weeks):
    weeks.append(weeks[0] + d * i)
  return weeks

def get_date_played(weeks, date_of_game):
  """Calculates the week the game was played, given the date of the replay
  
  Args:
      weeks (Array[datetime]): dates of CEA weeks
      date_of_game (datetime): date replay was played
  
  Returns:
      String: week game was played
  """
  weeks = [abs(week - date_of_game) for week in weeks]
  min_index = weeks.index(min(weeks))
  rounds = ['Round1', 'GapWeek', 'Round2', 'Round3', 'Round4', 'Round5', 'Round6']
  if min_index == 0:
    return 'Preseason'
  elif min_index < WEEKS[season]:
    return 'Week' + str(min_index)
  else:
    return rounds[min_index - WEEKS[season]]

def find_team(teams, name):
  """tries to find the team for a player
  if it can't be determined, returns UNNKNOWN_TEAM
  
  Args:
      teams (dict): dict with key = player, value = team
      name (string): name of player to find
  """
  if name.lower() in teams:
    return teams[name.lower()]
  else:
    return UNKNOWN_TEAM

def identify_unknown_players(matchup_dictionary, team_dictionary):
  """ Identifies unknown players in the teams file. If a player whose team is
  known matches up against a player whose team is unknown, then we can obtain
  the unknown player's team by checking the team matchups.
  Prints out potential errors (instances in which a team faced multiple
  opponents)
  and suggests the proper team for players whose team is unknown.
  
  Args:
      matchup_dictionary (dict): dict with key = Week played, value =
        dict<string,list> of key = team, and value = opponents played that week
      team_dictionary (dict): dict with key = player, value = team
  """
  with open('errors.txt', mode='w') as file_object:
    for week in matchup_dictionary.keys():
      for team, opponents in matchup_dictionary[week].items():
        if team == UNKNOWN_TEAM:
          continue
        opponent_teams = [find_team(teams,opponent) for opponent in set(opponents)]
        team_counter = Counter(opponent_teams)

        # If the team faced more than 2 opponents, that's not supposed to happen.
        if len(team_counter) >= 2 + int(UNKNOWN_TEAM in team_counter):
          print("Potential error in teams file: In {0}, {1} faced multiple teams:".format(week,team), file=file_object)
          print('Players: ', *["{0} {1}".format(find_team(teams, i), i) for i in set(opponents)], sep='\n\t',file=file_object)
        # If the team faced 2 opponents, and one was UNKNOWN_TEAM, then we know what team they faced.
        elif UNKNOWN_TEAM in team_counter and len(team_counter) == 2:
          # Get the team that is not UNKNOWN_TEAM: everyone belongs to that team.
          opponent_team = next(team for team in opponent_teams if team != UNKNOWN_TEAM )
          for opponent in set(opponents):
            if find_team(teams, opponent) == UNKNOWN_TEAM:
              print("Suggested team for {0}: {1};\n \t {2} faced {3} in {4}".format(opponent, opponent_team, opponent_team, team, week))
     

def copy_into_path(original, copyname, path):
  """copies into a new location, making the folders if necessary and stops if the file's already there
  
  Args:
      original (string): the file to copy
      copyname (string): the filename to use for the new location
      path (list of string): parts of the path at which to put the copy
  """
  path = os.path.join(*path).replace(" ", "_")
  os.makedirs(path, exist_ok=True) # makes the directories if necessary
  path = os.path.join(path, copyname.replace(" ", "_") + ".SC2Replay")
  if not os.path.isfile(path):
    counts['replay copies organized'] += 1
    shutil.copyfile(original, path)
  else:
    counts['replay copies already existed'] += 1
    

def organize_replays(directory, output_directory, teams, aliases, season):
  # Using mypq, load the replay file
  matcher = re.compile(r'\.SC2Replay$', re.IGNORECASE)
  replays = [file for file in os.listdir(directory) if matcher.search(file)]
  print("Found %d replays to scan" % len(replays))

  week_time = define_cea_date_ranges(season)

  # Windows has to close the file before moving them, so
  # files must be stored in a dictionary.
  renamed_files = {}

  # 2 dimensional dictionary that stores matchups per week.
  # KEY 1: Week, VALUE 1: Dictionary<string,list>
  # ex: matchup_dictionary['Week1']['Microsoft Macrohard']
  matchup_dictionary = {}

  for replay in replays:
    try:
      replay_file = sc2reader.load_replay(os.path.join(directory,replay), load_level=2)
      player_list = replay_file.players
      player_names = [player_list[0].name,
                      player_list[1].name]

      # resolve aliases for players who play under several accounts
      for i in range(len(player_names)):
        if player_names[i].lower() in aliases:
            player_names[i] = aliases[player_names[i].lower()]

      player_races = [player_list[0].play_race, player_list[1].play_race]
      player_teams = [find_team(teams, player_names[0]), find_team(teams, player_names[1])]

      week_played = get_date_played(week_time, replay_file.date)

      # Updates the Matchup Dictionary
      if week_played not in matchup_dictionary:
        matchup_dictionary[week_played] = {}
      matchup_dictionary[week_played].setdefault(player_teams[0], []).append(player_names[1])
      matchup_dictionary[week_played].setdefault(player_teams[1], []).append(player_names[0])


      # Keep naming consistent by always putting players alphabetized by team
      if player_teams[1] < player_teams[0]:
        player_races = [player_races[1], player_races[0]]
        player_names = [player_names[1], player_names[0]]
        player_teams = [player_teams[1], player_teams[0]]
      
      map_name = replay_file.map_name
      # don't continue for unknown players so they can be fixed
      if UNKNOWN_TEAM in player_teams:
        print("Couldn't find the team for one of the players. Here's what we know:")
        print("\t%s" % map_name)
        print("\t%s: %s (%s)" % (player_teams[0], player_names[0], player_races[0]))
        print("\t%s: %s (%s)" % (player_teams[1], player_names[1], player_races[1]))
        continue

      src = os.path.join(directory, replay)
        
      # rename the original to avoid name conflicts and make it clear what's been processed
      to_rename = "-".join([
        SEASONS[season], week_played,
        player_teams[0], player_teams[1],
        player_names[0], player_names[1],
        player_races[0], player_races[1],
        map_name]).replace(" ","_") + ".SC2Replay"
      dst = os.path.join(output_directory, to_rename)
      if src.lower() != dst.lower():
        counts['replays processed'] += 1
        os.makedirs(output_directory, exist_ok=True)
        renamed_files[src] = dst
      else:
        counts['replays were already processed'] += 1

    except:
      print("Error processing replay: %s" % replay)
      traceback.print_exc()
  for key, value in renamed_files.items():
      shutil.move(key, value)     
  for count_name, count in sorted(counts.items()):
    print(count, count_name) 
  # Identify players who are not recognized
  identify_unknown_players(matchup_dictionary, teams)          

if __name__ == "__main__":
  season = 0
  teams, aliases = cea_team_name_parser.init_dictionary(teams_file(season))
  organize_replays(replay_directory(season), replay_directory(season), 
                   teams, aliases, season)


