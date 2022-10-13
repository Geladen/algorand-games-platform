from beaker.client.application_client import ApplicationClient
from config import player, platform_id, berluscoin_id
from algorand import client, indexer
from algosdk.future.transaction import wait_for_confirmation
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
from game_platform.game_platform import GamePlatform
from morra import interact_morra
from base64 import b64encode

def _create_platform():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc)
    sp = client.suggested_params()
    
    appclient.create()
    res = appclient.call(GamePlatform.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient.app_addr, 210000), signer=player.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    print(asset, appclient.app_id)

def interact_platform():
    while True:
        print("\nChoose your action!")
        print("1. Opt into platform")
        print("2. Swap berluscoin")
        print("3. Create game")
        print("4. Join game")
        print("0. Quit")
        choice = int(input("> "))
        if choice == 1:
            interact_opt()
        elif choice == 2:
            interact_swap()
        elif choice == 3:
            interact_create()
        elif choice == 4:
            interact_join()
        else:
            break
        
def interact_opt():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    if not(any(application['id'] == platform_id for application in client.account_info(player.pk)["apps-local-state"])):
        print("Joining the platform...", end=" ", flush=True)
        appclient.opt_in(player.pk)
        print("Done!")
    else:
        print("Platform already joined.")
        
def interact_swap():
    appclient = ApplicationClient(client, GamePlatform(), signer=player.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    amt = int(input("\nHow many berluscoin do you want to buy? "))
    
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

def interact_create():
    print("\nWhat game do you want to create?")
    print("1. Sa murra")
    choice = int(input("> ")) 
    
    if choice == 1:
        app_id = interact_morra.interact_create()
        interact_morra.interact_play(app_id)
    elif choice == 2:
        pass

def interact_join():
    txns = indexer.search_transactions(application_id=platform_id, limit=500)['transactions']
    games = {}
    for txn in txns:
        if 'local-state-delta' not in txn:
            continue
        deltas = [(ld['address'], ld['delta']) for ld in txn['local-state-delta']]
        deltas = [(a,v) for a,d in deltas for v in d]
        values = {(d['value']['uint'], a) for (a,d) in deltas if d['key'] == b64encode(b'current_game').decode()}
        games.update(values)
    games = [(g, games[g]) for g in sorted(list(set(games.keys())), reverse=True)]
        
    print("Choose your game:")
    for i, (game, _acc) in enumerate(games):
        print(f"{i+1}. {game}")
    choice = int(input('> '))
    
    app_id, challenger = games[choice-1]
    print(challenger, app_id, player.pk)
    interact_morra.interact_join(challenger, app_id)
    interact_morra.interact_play(app_id)
