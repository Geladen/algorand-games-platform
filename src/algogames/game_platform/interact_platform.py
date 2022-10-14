from typing import Callable
from beaker.client.application_client import ApplicationClient
from utils import ask_choice, ask_number, ask_string, find_games, is_opted, menu_callback, try_get_local, menu
from config import player, platform_id, berluscoin_id
from algorand import client, indexer
from algosdk.future.transaction import wait_for_confirmation
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
from game_platform.game_platform import GamePlatform
from morra import interact_morra
from rps import interact_rps
import beaker

def _create_platform():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc)
    sp = client.suggested_params()
    
    appclient.create()
    res = appclient.call(GamePlatform.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, 210000), signer=player.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    
    with open('ops/env/platform.env', 'w') as f:
        f.write(f"BERLUSCOIN_ID={asset}\nPLATFORM_ID={appclient.app_id}")
    global platform_id, berluscoin_id
    berluscoin_id = asset
    platform_id = appclient.app_id
    
def interact_platform():
    cont = True
    while cont:
        current_game = try_get_local("current_game", platform_id)
        username = try_get_local("username", platform_id)
        if username is not None:
            print(f"\nHi, {username}")
        cont = menu_callback(f"Choose your action!", [
            ("Opt into platform", interact_opt),
            ("Swap berluscoin", interact_swap),
            ("Create game", interact_create),
            ("Join game", interact_join),
            *([(f"Resume game {current_game}", lambda: interact_morra.interact_play(current_game))] if current_game else []),
            ("Your profile", interact_profile),
        ], quit_option=True, skip_line=False)
        
def interact_opt():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    
    if not is_opted(player.pk, platform_id):
        username = ask_string("Choose your username:", lambda x: len(x) > 0)
        print("Joining the platform...", end=" ", flush=True)
        appclient.opt_in(player.pk, username=username)
        print("Done!")
    else:
        print("Platform already joined.")
        
def interact_swap():
    choice = ask_choice("Do you want to buy or sell?", ["buy", "sell"])
    if choice == "buy":
        interact_buy()
    else:
        interact_sell()
        
def interact_buy():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    try:
        amt = ask_number("How many berluscoin do you want to buy?", [0, None])
        
        if amt > 0:
            if not(any(asset['asset-id'] == berluscoin_id for asset in client.account_info(player.pk)["assets"])):
                print("Opting into the token...", end=" ", flush=True)
                wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, player.pk, 0, berluscoin_id).sign(player.sk)), 4)
            print("Swapping tokens...", end=" ", flush=True)
            appclient.call(GamePlatform.buy, player.pk, asset=berluscoin_id, txn=TransactionWithSigner(
                algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, amt), 
                player.acc
            ))
            print("Done!")
    except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
        if ("tried to spend" in str(e)) or ("balance" in str(e) and "below min" in str(e)):
            print("Not enough ALGOs.")
            return None
        else:
            raise e
        
def interact_sell():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    amt = ask_number("How many berluscoin do you want to sell?", [0, None])
    
    try:
        if amt > 0:
            print("Swapping tokens...", end=" ", flush=True)
            appclient.call(GamePlatform.sell, player.pk, txn=TransactionWithSigner(
                algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient.app_addr, amt, berluscoin_id), 
                player.acc
            ))
            print("Done!")
    except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
        if ("underflow" in str(e)) or (f"asset {berluscoin_id} missing from" in str(e)):
            print("Not enough berluscoin.")
            return None
        elif ("tried to spend" in str(e)) or ("balance" in str(e) and "below min" in str(e)):
            print("Not enough ALGOs.")
            return None
        else:
            raise e
        
def interact_create_and_play(create: Callable[[], int], play: Callable[[int], None]):
    app_id = create()
    if app_id:
        print(f"Game {app_id} created!")
        play(app_id)

def interact_create():
    menu_callback("What game do you want to create?", [
        ("Sa murra", lambda: interact_create_and_play(interact_morra.interact_create, interact_morra.interact_play)),
        ("Rock Paper Scissors", lambda: interact_create_and_play(interact_rps.interact_create, interact_rps.interact_play)),
    ])

def interact_join():
    games = find_games()
    
    if len(games) > 0:
        choice = menu("Choose your game:", [
            f"{game[0]} ({game[1]['game']}, vs {game[1]['user']})"
            for game in games
        ])
        
        app_id, details = games[choice-1]
        if details['game'] == 'morra':
            join, play = interact_morra.interact_join, interact_morra.interact_play
        elif details['game'] == 'rps':
            join, play = interact_rps.interact_join, interact_rps.interact_play
            
        joined = join(details["addr"], app_id)
        if joined:
            play(app_id)
    else:
        print("No games, why don't you create one?")
        
def interact_profile():
    puntazzi = try_get_local("puntazzi", platform_id) 
    puntazzi = 0 if puntazzi is None else puntazzi
    account = client.account_info(player.pk)
    assets = account["assets"] if "assets" in account else []
    algo_amt = account["amount"]/1000000
    berluscoin_amt = next((asset["amount"] for asset in assets if asset["asset-id"] == berluscoin_id), 0)
    print(f"Your puntazzi: {puntazzi}")
    print(f"Your balance: {berluscoin_amt} berluscoin, {algo_amt} algo")
