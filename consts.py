"""Constants to be used for the current season. Not sure how coding in python
works, but this is essentially the setup file. Currently it has some unused variables,
and is only being used by download_replays.py.

Attributes:
    CURRENT_SEASON (str): Current season; At the start of a new CEA season
    					  rename this to something new, like SeasonFall2020.
	STARTING_DATE (str): date of the 1st game
    TEAMS_FILE (str): Teams file for the current season. Create the csv in the
    				  season folder.
    CURRENT_SEASON_NAME (str): Current season name. Must match replay vault.
    ID_DICT_JSON (str): Dictionary containing info on which replays have
    					already been downloaded.
    URL (str): URL of the replay vault.
"""

# Current season; At the start of a new CEA season, rename this to something
# new, whether it be Season [N=1] or Fall2020.
SEASONS = ["Spring2021", "Fall2020", "Spring2020","Fall2019","Spring2019"]

CURRENT_SEASON = "Spring2021"

# CSV containing Team->Player information.
TEAMS_FILE = "cea_names.csv"

# Starting date of the season, YYYYMMDD format.
STARTING_DATE = ["20210213", "20200912",
"20200221", "20190917", "2019316"]

# Number of round robin weeks
WEEKS = [8, 9,9,7,9]

# Used in download_replays.py to download replays from the replay vault.
# This is equal to whatever's in the header.
CURRENT_SEASON_NAME = ["Spring 2021", "Fall 2020",
"Spring 2020", "Fall 2019", "Spring 2019"]

ID_DICT_JSON = "data/" + CURRENT_SEASON + "_id_dict.json"
URL = 'https://cea.gg/pages/replay-vault'
