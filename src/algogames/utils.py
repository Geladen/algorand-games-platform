from typing import Callable, List, Tuple
from algorand import client, indexer
from config import platform_id, player, skull_id
from beaker.client.application_client import ApplicationClient
from game_platform.game_platform import GamePlatform
import codecs
import beaker
import algosdk

def find_games():
    accs = indexer.accounts(application_id=platform_id)["accounts"]
    games = {}
    for acc in accs:
        for ls in acc["apps-local-state"]:
            if "key-value" in ls and ls["id"] == platform_id:
                current_game = next((kv["value"]["uint"] for kv in ls["key-value"] if codecs.decode(kv["key"].encode(), "base64").decode() == "current_game"), None)
                game_time = next((kv["value"]["uint"] for kv in ls["key-value"] if codecs.decode(kv["key"].encode(), "base64").decode() == "game_time"), None)
                game_type = next((kv["value"]["bytes"] for kv in ls["key-value"] if codecs.decode(kv["key"].encode(), "base64").decode() == "game_type"), None)
                username = next((kv["value"]["bytes"] for kv in ls["key-value"] if codecs.decode(kv["key"].encode(), "base64").decode() == "username"), None)
                if current_game:
                    games[current_game] = { 
                        "addr": acc["address"], 
                        "time": game_time, 
                        "game": codecs.decode(game_type.encode(), 'base64').decode(), 
                        "user": codecs.decode(username.encode(), 'base64').decode() 
                    }
                        
    games = [(g, games[g]) for g in sorted(list(set(games.keys())), reverse=True)]
    return games

def try_get_local(keys: List[str] | str, app_id: int, account=player.pk):
    if type(keys) is str:
        keys = [keys]
    try:
        appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=app_id)
        if is_opted(account, app_id):
            local_state = appclient.get_account_state(account)
            res = [local_state[key] if key in local_state else None for key in keys] 
        else:
            res = [None for _ in keys]
        return res[0] if len(keys) == 1 else res
            
    except algosdk.error.AlgodHTTPError as e:
        if "account application info not found" in str(e):
            res = [None for _ in keys]
            return res[0] if len(keys) == 1 else res
        else:
            raise e
        
def try_get_global(keys: List[str] | str, app_id: int):
    if type(keys) is str:
        keys = [keys]
    try:
        appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=app_id)
        global_state = appclient.get_application_state()
        res =  [global_state[key] if key in global_state else None for key in keys]
        return res[0] if len(keys) == 1 else res
    except algosdk.error.AlgodHTTPError as e:
        if "application does not exist" in str(e):
            res = [None for _ in keys]
            return res[0] if len(keys) == 1 else res
        else: 
            raise e
    
def try_get_creator(app_id):
    try:
        res = client.application_info(app_id)['params']['creator']
        return res
    except algosdk.error.AlgodHTTPError as e:
        if "application does not exist" in str(e):
            return None
        else: 
            raise e
        
def is_opted(account, app_id):
    account_info = client.account_info(account)
    return any(application['id'] == app_id for application in account_info["apps-local-state"])

def is_opted_asset(account, asset_id):
    account_info = client.account_info(account)
    return any(asset['asset-id'] == asset_id for asset in account_info["assets"])

def trysend(f):
    try:
        return f()
    except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
        if ("underflow" in str(e)) or (f"asset {skull_id} missing from" in str(e)):
            print("Not enough skulls.")
            return None
        elif ("tried to spend" in str(e)) or ("balance" in str(e) and "below min" in str(e)):
            print("Not enough ALGOs.")
            return None
        elif f"has not opted in to app {platform_id}" in str(e):
            print("Platform not joined.")
            return None
        elif "application does not exist"  in str(e):
            print("Game is over.")
            return False
        else:
            raise e

def ask_string(query: str, valid: Callable[[str], bool], skip_line=True):
    first = True
    while True:
        pre = "\n" if first and skip_line else ""
        choice = input(f"{pre}{query} ")
        first = False
        if valid(choice): 
            break
        
    return choice

def ask_choice(query: str, choices=List[str], skip_line=True):
    first = True
    while True:
        pre = "\n" if first and skip_line else ""
        choice = input(f"{pre}{query} ({'/'.join(choices)}) ")
        first = False
        if choice.lower() in [choice.lower() for choice in choices]:
            break
    return choice.lower()

def ask_number(query: str, range: Tuple[int|None, int|None]=None, skip_line=True):
    first = True
    while True:
        pre = "\n" if first and skip_line else ""
        choice = input(f"{pre}{query} ")
        first = False
        if not choice.lstrip('-+').isnumeric(): 
            continue
        choice = int(choice)
        if (range is None): 
            break
        if (range[0] is None or range[0] <= choice) and (range[1] is None or choice <= range[1]): 
            break
        
    return choice

def menu(query: str, options: List[str], zero_option=None, skip_line=True):
    if len(options) == 0 and not zero_option:
        return None
    pre = "\n" if skip_line else ""
    print(f"{pre}{query}")
    for i, option in enumerate(options):
        print(f"{i+1}. {option}")
    if zero_option is not None:
        print(f"0. {zero_option}")
        
    range = (0, len(options)) if zero_option else (1, len(options))
    return ask_number(">", range=range)
        
def menu_callback(query: str, options: List[Tuple[str, Callable[[], None]]], quit_option=False, skip_line=True):
    choice = menu(query, [option[0] for option in options], zero_option="Quit" if quit_option else None, skip_line=skip_line)
    
    if choice is None:
        return True
    elif choice == 0:
        return False
    else:
        options[choice-1][1]()
        return True
    