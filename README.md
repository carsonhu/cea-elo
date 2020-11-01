# CEA-ELO
Tracking statistics for the Starcraft 2 Corporate Esports Association league.

# How to use the repository
1. Clone the repo somewhere onto your computer.
2. Install the dependencies.
```
pip install -r requirements.txt 
```

## To download replays from the replay repo.
```
python download_replays.py
```
The replay organizer only downloads replays it hasn't seen before. To (re)download all replays for the season, use:
```
python download_replays.py --r true
```

## To rename replays.
```
python setup_replays.py
```
There'll be some errors due to a few broken SC2 Replay files, but you can ignore that or remove them.

Errors may pop up due to a missing team name corresponding to a player.
In the event of a missing team name, update cea_names.csv by adding the player name to their corresponding team.

## To generate a stats spreadsheet for the season.
```
python calculate_elo.py
```
