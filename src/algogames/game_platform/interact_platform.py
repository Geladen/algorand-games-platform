import algosdk
from beaker.client.application_client import ApplicationClient
from algosdk.future.transaction import wait_for_confirmation
from algosdk.atomic_transaction_composer import TransactionWithSigner
from config import player, platform_id, skull_id, fee_holder
from algorand import client
from utils import ask_choice, ask_number, ask_string, find_games, is_opted, is_opted_asset, menu_callback, try_get_local, menu, trysend
from game_platform.game_platform import GamePlatform
from morra.interact_morra import interact_morra
from blackjack.interact_blackjack import interact_blackjack
from rps.interact_rps import interact_rps

def _create_platform():
    """
    Deploy the platform and store its ID, and the asset ID into platform.env
    """
    appclient = ApplicationClient(client, GamePlatform(), signer=fee_holder.acc)
    sp = client.suggested_params()
    
    appclient.create(fee_holder=fee_holder.pk)
    res = appclient.call(GamePlatform.init, fee_holder.pk, 
        txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(fee_holder.pk, sp, appclient.app_addr, 210000), signer=fee_holder.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    
    with open('ops/env/platform.env', 'w') as f:
        f.write(f"SKULL_ID={asset}\nPLATFORM_ID={appclient.app_id}")
    global platform_id, skull_id
    skull_id = asset
    platform_id = appclient.app_id
    
    appclient.opt_in(fee_holder.pk, username="fee_holder")
    wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(fee_holder.pk, sp, fee_holder.pk, 0, skull_id).sign(fee_holder.sk)), 4)
    
    
def interact_platform():
    """
    Main interact menu
    """
    cont = True
    while cont:
        current_game, game_type = try_get_local(["current_game", "game_type"], platform_id)
        game_fun = {"morra": interact_morra, "rps": interact_rps, "blackjack": interact_blackjack}[game_type] if game_type else None
        username = try_get_local("username", platform_id)
        if username is not None:
            print(f"\nHi, {username}")
        cont = menu_callback(f"Choose your action!", [
            ("Opt into platform", interact_opt),
            ("Swap skulls", interact_swap),
            ("Create game", interact_create),
            ("Join game", interact_join),
            *([(f"Resume game {current_game}", lambda: game_fun(current_game))] if current_game else []),
            ("Your profile", interact_profile),
        ], quit_option=True, skip_line=False)
        
        
def interact_opt():
    """
    Interact menu for opting into the platform
    """
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    
    if not is_opted(player.pk, platform_id):
        username = ask_string("Choose your username:", lambda x: len(x) > 0)
        print("Joining the platform...", end=" ", flush=True)
        appclient.opt_in(player.pk, username=username)
        print("Done!")
    else:
        print("Platform already joined.")
        
        
def interact_swap():
    """
    Interact menu for choosing if to buy or sell skulls
    """
    choice = ask_choice("Do you want to buy or sell?", ["buy", "sell"])
    if choice == "buy":
        interact_buy()
    else:
        interact_sell()
       
        
def interact_buy():
    """
    Interact menu for buying skulls
    """
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    amt = ask_number("How many skulls do you want to buy?", [0, None])
    
    if amt > 0:
        if not(is_opted_asset(player.pk, skull_id)):
            print("Opting into the token...", end=" ", flush=True)
            trysend(lambda: wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, player.pk, 0, skull_id).sign(player.sk)), 4))
        print("Swapping tokens...", end=" ", flush=True)
        trysend(lambda: appclient.call(GamePlatform.buy, player.pk, asset=skull_id, txn=TransactionWithSigner(
            algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, amt), 
            player.acc
        )))
        print("Done!")
        
        
def interact_sell():
    """
    Interact menu for selling skulls
    """
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    amt = ask_number("How many skulls do you want to sell?", [0, None])
    
    if amt > 0:
        print("Swapping tokens...", end=" ", flush=True)
        trysend(lambda: appclient.call(GamePlatform.sell, player.pk, txn=TransactionWithSigner(
            algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient.app_addr, amt, skull_id), 
            player.acc
        )))
        print("Done!")
    
    
def interact_create():
    """
    Interact menu for creating a new game
    """
    menu_callback("What game do you want to create?", [
        ("Sa murra", interact_morra),
        ("Rock Paper Scissors", interact_rps),
        ("Blackjack", interact_blackjack),
    ], quit_option=True)


def interact_join():
    """
    Interact menu for joining an existing game
    """
    games = find_games()
    # Filter "single player" games
    games = [game for game in games if game[1]['game'] != 'blackjack'] 
    
    if len(games) > 0:
        choice = menu("Choose your game:", [
            f"{game[0]} ({game[1]['game']}, vs {game[1]['user']})"
            for game in games
        ])
        app_id, details = games[choice-1]
        if details['game'] == 'morra':
            interact_morra(app_id)
        elif details['game'] == 'rps':
            interact_rps(app_id)
    else:
        print("No games, why don't you create one?")
      
        
def interact_profile():
    """
    Interact menu for getting profile info
    """
    puntazzi = try_get_local("puntazzi", platform_id) 
    account = client.account_info(player.pk)
    assets = account["assets"] if "assets" in account else []
    algo_amt = account["amount"] / 1000000
    skull_amt = next((asset["amount"] for asset in assets if asset["asset-id"] == skull_id), 0)
    
    print(f"Your puntazzi: {puntazzi}")
    print(f"Your balance: {skull_amt} skulls, {algo_amt} algo")
