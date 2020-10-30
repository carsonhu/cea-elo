"""Download replays from the CEA Replay Repository.
Saves records of which links have been downloaded in data/ folder.
Usage: python download_replays.py
If you want to redownload all replays,
  python download_replays.py --r True

And pip install whatever packages you need.

TODO: combine this into one script with replay_organizer.py.
Also TODO: Write a setup file so that people don't have to pip install everything.
"""
import argparse
import requests
import shutil
import json
import time
from consts import SEASONS, URL
from drive_downloader import GoogleDriveDownloader as gdd
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

# TODO: Automatically find this using the relevant tab.
id_dict_json = lambda season : "data/" + SEASONS[season] + "_id_dict.json"
# Directory where uploaded replays are stored.
replay_directory = lambda season: "UploadHere/" + SEASONS[season] + "/"

def update_json(id_dict, dict_json):
  """Updates the json file which checks which files have been downloaded.

  Args:
      id_dict (DICT): Dictionary with url ID as key, 1 as value
  """
  j = json.dumps(id_dict)
  f = open(dict_json, 'w')
  print(j, file=f)
  f.close()

def get_url_list(season):
  driver = webdriver.Chrome(ChromeDriverManager().install())
  driver.get('https://cea.gg/pages/replay-vault')

  time.sleep(5)

  html = driver.execute_script("return document.getElementsByTagName('html')[0].innerHTML")
  soup = BeautifulSoup(html, 'html.parser')
  games_list = soup.find_all("div", {"class": "shogun-accordion"})
  starcraft_html = ""
  for game in games_list:
    game_title = game.find_all("h4", {"class": "shogun-accordion-title"})
    if game_title[0].text.strip() == "Starcraft 2":
      starcraft_html = game
  if not starcraft_html:
    return "Error: Starcraft 2 replays could not be found."

  # The first tab body would apply to the entire Starcraft 2 tab.
  season_tabs = starcraft_html.find_all("div", {"class": "shogun-tabs-body"})
  #print(season_tabs)

  # Get HTML associated with current season number.
  current_season_html = season_tabs[season + 1]
  current_season_links = current_season_html.find_all('a')
  return current_season_links

def download_replays(redownload, season):
  links = get_url_list(season)
  print(links)
  try:
    with open(id_dict_json(season), 'r') as f:
      id_dict = json.load(f)
  except:
    print("Could not open %s" % id_dict_json(season))
    id_dict = {}
  # Use an empty dict if redownloading all replays
  if redownload:
    id_dict = {}

  count = 0
  for link in links:
    count += 1
    drive_id = link.get('href').split("=")[-1]
    #print(drive_id)
    if drive_id not in id_dict:
      id_dict[drive_id] = 1
      gdd.download_file_from_google_drive(
          file_id=drive_id, dest_path=replay_directory(season)
          + "temp_dir" + '.zip', new_file_name=str(count) + " ",
          unzip=True)      
  update_json(id_dict, id_dict_json(season))

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description='Download Replays from CEA Replay Repository')
  parser.add_argument('--r', type=bool, dest='redownload', default=False,
                      help='True/False: Whether to redownload all replays')
  args = parser.parse_args()
  #print(get_url_list(1))
  # for i in range(len(SEASONS)):
  #    download_replays(args.redownload, i)
  download_replays(args.redownload, 0)