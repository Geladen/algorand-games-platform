from typing import Callable
from beaker.client.application_client import ApplicationClient
from utils import ask_number, ask_string, find_games, is_opted, menu_callback, try_get_platform, menu
from config import player, platform_id, berluscoin_id
from algorand import client, indexer
from algosdk.future.transaction import wait_for_confirmation
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
from game_platform.game_platform import GamePlatform
from morra import interact_morra
from base64 import b64encode
import codecs

def _create_platform():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc)
    sp = client.suggested_params()
    
    appclient.create()
    res = appclient.call(GamePlatform.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, 210000), signer=player.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    print(asset, appclient.app_id)

def interact_platform():
    cont = True
    while cont:
        current_game = try_get_platform("current_game")
        username = try_get_platform("username")
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
        username = ask_string("Choose your username: ", lambda x: len(x) > 0)
        print("Joining the platform...", end=" ", flush=True)
        appclient.opt_in(player.pk, username=username)
        print("Done!")
    else:
        print("Platform already joined.")
        
def interact_swap():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    amt = ask_number("How many berluscoin do you want to buy? ", [0, None])
    
    if amt > 0:
        if not(any(asset['asset-id'] == berluscoin_id for asset in client.account_info(player.pk)["assets"])):
            print("Opting into the token...", end=" ", flush=True)
            wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, player.pk, 0, berluscoin_id).sign(player.sk)), 4)
        print("Swapping tokens...", end=" ", flush=True)
        appclient.call(GamePlatform.swap, player.pk, asset=berluscoin_id, txn=TransactionWithSigner(
            algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, amt), 
            player.acc
        ))    
        print("Done!")

def interact_create_and_play(create: Callable[[], int], play: Callable[[int], None]):
    app_id = create()
    if app_id:
        print(f"Game {app_id} created!")
        play(app_id)

def interact_create():
    menu_callback("What game do you want to create?", [
        ("Sa murra", lambda: interact_create_and_play(interact_morra.interact_create, interact_morra.interact_play)),
    ])

def interact_join():
    games = find_games()
    
    if len(games) > 0:
        choice = menu("Choose your game:", [
            f"{game[0]} ({game[1]['game']}, vs {game[1]['user']})"
            for game in games
        ])
        
        app_id, details = games[choice-1]
        joined = interact_morra.interact_join(details["addr"], app_id)
        if joined:
            interact_morra.interact_play(app_id)
    else:
        print("No games, why don't you create one?")
        
def interact_profile():
    puntazzi = try_get_platform("puntazzi") 
    puntazzi = 0 if puntazzi is None else puntazzi
    print(f"Your puntazzi: {puntazzi}")
