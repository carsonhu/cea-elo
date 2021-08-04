"""Calculate a player's Zero Number
"""
from queue import PriorityQueue
import operator

def zeroNumber(player_dictionary):
    #maxPlayer = max(player_dictionary.keys(), key=(lambda key: player_dictionary[key].trueskill.mu))
    # temporarily just setting it to zero instead of max player
    maxPlayer = "zero"
    # then we do a BFS
    q = PriorityQueue()
    discovered = set(maxPlayer)
    player_dictionary[maxPlayer].zeroNumber = 0
    q.put((0,maxPlayer))
    while q.queue:
        v = q.get()[1]
        for player in player_dictionary[v].opponents_lost_to:
            player_dictionary[player].zeroNumber = min(player_dictionary[v].zeroNumber + 1, 
                                                       player_dictionary[player].zeroNumber)
            if player not in discovered:
                discovered.add(player)
                q.put((player_dictionary[player].zeroNumber, player))
    return maxPlayer