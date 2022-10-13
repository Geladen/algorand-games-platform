from hashlib import sha256
import json
import random
from beaker.client.application_client import ApplicationClient
from utils import trysend
from game_platform.game_platform import GamePlatform
from algorand import client
from morra.morra import SaMurra, action_timeout
from beaker2 import create_nosend, call_nosend, opt_in_nosend, finalize
from time import sleep
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
import codecs
from config import player, berluscoin_id, platform_id

def interact_create():
    appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=player.acc, app_id=platform_id)
    
    stake = int(input("\nHow much do you want to stake? "))
    
    sp = client.suggested_params()
    
    print("Creating morra game...", end=" ", flush=True)
    appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=player.acc)
    finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.new_game, player.pk, txn=create_nosend(appclient_morra, player.pk, asset=berluscoin_id)))
    app_id_morra = appclient_platform.get_account_state()["current_game"]
    
    appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=player.acc, app_id=app_id_morra)
    print("Initializing game...", end=" ", flush=True)
    appclient_morra.call(SaMurra.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient_morra.app_addr, 210000), signer=player.acc), asset=berluscoin_id)
    appclient_morra.opt_in(player.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_morra.app_addr, stake, berluscoin_id), signer=player.acc))
    print("Done!")
    
    return app_id_morra

def interact_join(challenger, app_id):
    appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=player.acc, app_id=platform_id)
    appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=player.acc, app_id=app_id)
    if (any(application['id'] == app_id for application in client.account_info(player.pk)["apps-local-state"])):
        print("Already joined.")
        return
    
    sp = client.suggested_params()
    stake = appclient_morra.get_application_state()['stake']
    finalize(appclient_morra, call_nosend(appclient_platform, GamePlatform.join_game, player.pk, challenger=challenger, 
        txn=opt_in_nosend(appclient_morra, player.pk, 
        txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_morra.app_addr, stake, berluscoin_id), signer=player.acc))))
    
def interact_play(app_id):
    appclient_morra = ApplicationClient(client=client, app=SaMurra(), app_id=app_id, signer=player.acc)
    appclient_platform = ApplicationClient(client=client, app=SaMurra(), app_id=platform_id, signer=player.acc)
    revealed = False
    
    while True:
        round = client.status()['last-round']
        try:
            global_state = appclient_morra.get_application_state()
            local_state = appclient_morra.get_account_state()
            creator = client.application_info(app_id)['params']['creator']
            if 'challenger' in global_state:
                challenger = algosdk.encoding.encode_address(codecs.decode(global_state['challenger'].encode(), 'hex'))
                other = creator if challenger == player.pk else challenger
                other_appclient = ApplicationClient(client=client, app=SaMurra(), app_id=app_id, sender=other)
            
            if revealed and global_state["state"] != 4:
                revealed = False
                other_state = other_appclient.get_account_state()
                your_hand = local_state['player_hand']
                other_hand = other_state['player_hand']
                your_guess = local_state['player_guess']
                other_guess = other_state['player_guess']
                total = your_hand + other_hand
                print(f"Your hand: {your_hand}, Challenger hand: {other_hand}, Total: {total}")
                print(f"Your guess: {your_guess}, Challenger guess: {other_guess}")
                if total == your_guess and total != other_guess:
                    print("You won the round!")
                elif total != your_guess and total == other_guess:
                    print("Challenger won the round!")
                else:
                    print("Draw")
        except algosdk.error.AlgodHTTPError as e:
            if "application does not exist" in str(e):
                print("Game is over. ")
                return
            else:
                raise e
            
        if global_state["state"] == 2:
            print("Waiting for players...")
            sleep(5)
        elif global_state["state"] == 3 and ("player_state" not in local_state or local_state["player_state"] != 3):
            hand = int(input("What is your hand? "))
            guess = int(input("What is your guess? "))
            nonce = random.randint(0, 2**64-1)
            print("Sending commit...", end=" ", flush=True)
            trysend(lambda: appclient_morra.call(SaMurra.commit, player.pk, commit=sha256(json.dumps({"guess": guess, "hand": hand, "nonce": nonce}).encode()).digest()))
            print("Done!")
        elif global_state["state"] == 3 and ("player_state" not in local_state or local_state["player_state"] == 3):
            print("Waiting for other player to commit...")
            if global_state["action_timer"] + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_morra.call(SaMurra.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
        elif global_state["state"] == 4 and local_state["player_state"] != 4:
            print("Revealing your choice...", end=" ", flush=True)
            trysend(lambda: appclient_morra.call(SaMurra.reveal, player.pk, other=other, reveal=json.dumps({"guess": guess, "hand": hand, "nonce": nonce})))
            print("Done!")
            revealed=True
        elif global_state["state"] == 4 and local_state["player_state"] == 4:
            print("Waiting for other player to reveal...")
            if global_state["action_timer"] + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_morra.call(SaMurra.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
        elif global_state["state"] == 5 and global_state["winner"] == codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You won the game!")
            print("Registering win...", end=" ", flush=True)
            trysend(lambda: appclient_platform.call(GamePlatform.win_game, player.pk, app=app_id))
            print("Getting money...", end=" ", flush=True)
            trysend(lambda: appclient_morra.delete(player.pk, asset=berluscoin_id, creator=creator))
            print("Done!")
            return
        elif global_state["state"] == 5 and global_state["winner"] != codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You lost :(")
            return
        else:
            print("DEBUG:")
            print(global_state)
            print(local_state)
            sleep(3)
