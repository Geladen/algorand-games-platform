from hashlib import sha256
import json
import random
from beaker.client.application_client import ApplicationClient
from utils import ask_number, ask_string, ask_choice, try_get_global, trysend
from game_platform.game_platform import GamePlatform
from algorand import client
from rps.rps import RPS, action_timeout
from beaker2 import create_nosend, call_nosend, opt_in_nosend, finalize
from time import sleep
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
import beaker
import codecs
from config import player, berluscoin_id, platform_id

def interact_create():
    appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=player.acc, app_id=platform_id)
    
    sp = client.suggested_params()
    
    try:
        print("Creating rps game...", end=" ", flush=True)
        appclient_rps = ApplicationClient(client=client, app=RPS(), signer=player.acc)
        finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.new_game, player.pk, game="rps", txn=create_nosend(appclient_rps, player.pk, asset=berluscoin_id)))
        app_id_rps = appclient_platform.get_account_state()["current_game"]
    
        appclient_rps = ApplicationClient(client=client, app=RPS(), signer=player.acc, app_id=app_id_rps)
        print("Initializing game...", end=" ", flush=True)
        appclient_rps.call(RPS.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient_rps.app_addr, 210000), signer=player.acc), asset=berluscoin_id)
        print("Done!")
    
        stake = ask_number("How much do you want to stake?")    
        print("Sending stake...", end=" ", flush=True)
        appclient_rps.opt_in(player.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_rps.app_addr, stake, berluscoin_id), signer=player.acc))
        print("Done!")
    except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
        if "underflow" in str(e):
            print("Not enough berluscoin.")
            return None
        elif "balance" in str(e) and "below min" in str(e):
            print("Not enough ALGOs.")
            return None
        elif f"has not opted in to app {platform_id}" in str(e):
            print("Platform not joined.")
            return None
        else:
            raise e
        
    return app_id_rps

def interact_join(challenger, app_id):
    appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=player.acc, app_id=platform_id)
    appclient_rps = ApplicationClient(client=client, app=RPS(), signer=player.acc, app_id=app_id)
    if (any(application['id'] == app_id for application in client.account_info(player.pk)["apps-local-state"])):
        print("Already joined.")
        return True
    
    try:
        sp = client.suggested_params()
        stake = try_get_global('stake', app_id)
        if stake is None:
            print("Stake not yet defined.")
            return False
        choice = ask_choice(f"Stake is {stake}. Join?", ["y", "N"])
        if choice == False:
            return False
        print("Joining game...", end=" ", flush=True)
        finalize(appclient_rps, call_nosend(appclient_platform, GamePlatform.join_game, player.pk, challenger=challenger, 
            txn=opt_in_nosend(appclient_rps, player.pk, 
            txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_rps.app_addr, stake, berluscoin_id), signer=player.acc))))
        print("Done!")
        return True
    except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
        if "underflow" in str(e) or f"missing from {player.pk}"  in str(e):
            print("Not enough berluscoin.")
            return False
        if "application does not exist"  in str(e):
            print("Game is over.")
            return False
        else:
            raise e
        
def interact_play(app_id):
    appclient_rps = ApplicationClient(client=client, app=RPS(), app_id=app_id, signer=player.acc)
    appclient_platform = ApplicationClient(client=client, app=RPS(), app_id=platform_id, signer=player.acc)
    revealed = False
    
    while True:
        round = client.status()['last-round']
        try:
            global_state = appclient_rps.get_application_state()
            local_state = appclient_rps.get_account_state()
            creator = client.application_info(app_id)['params']['creator']
            if 'challenger' in global_state:
                challenger = algosdk.encoding.encode_address(codecs.decode(global_state['challenger'].encode(), 'hex'))
                other = creator if challenger == player.pk else challenger
            
            if revealed and global_state["state"] != 4:
                revealed = False
                other_state = appclient_rps.get_account_state(other)
                your_hand = local_state['player_hand']
                other_hand = other_state['player_hand']
                print(f"Your hand: {your_hand}, Challenger hand: {other_hand}")
                if ((your_hand == 'rock' and other_hand == 'scissors') 
                    or (your_hand == 'scissors' and other_hand == 'paper')
                    or (your_hand == 'paper' and other_hand == 'rock')):
                    print("You won the round!")
                elif ((your_hand == 'scissors' and other_hand == 'rock') 
                    or (your_hand == 'paper' and other_hand == 'scissors')
                    or (your_hand == 'rock' and other_hand == 'paper')):
                    print("Challenger won the round!")
                else:
                    print("Draw")
        except (algosdk.error.AlgodHTTPError, beaker.client.logic_error.LogicException) as e:
            if "application does not exist" in str(e):
                print("Game is over.")
                return
            elif "account application info not found" in str(e):
                print("You are not playing this game.")
                return
            else:
                raise e
            
        if global_state["state"] == 2:
            print("Waiting for players...")
            sleep(5)
        elif global_state["state"] == 3 and ("player_state" not in local_state or local_state["player_state"] != 3):
            hand = ask_string("What do you play? (rock/paper/scissors)", lambda x: x=='rock' or x=='paper' or x=='scissors')
            nonce = random.randint(0, 2**64-1)
            print("Sending commit...", end=" ", flush=True)
            trysend(lambda: appclient_rps.call(RPS.commit, player.pk, commit=sha256(json.dumps({"hand": hand, "nonce": nonce}).encode()).digest()))
            print("Done!")
        elif global_state["state"] == 3 and ("player_state" not in local_state or local_state["player_state"] == 3):
            print("Waiting for other player to commit...")
            if global_state["action_timer"] + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_rps.call(RPS.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
        elif global_state["state"] == 4 and local_state["player_state"] != 4:
            print("Revealing your choice...", end=" ", flush=True)
            trysend(lambda: appclient_rps.call(RPS.reveal, player.pk, other=other, reveal=json.dumps({"hand": hand, "nonce": nonce})))
            print("Done!")
            revealed=True
        elif global_state["state"] == 4 and local_state["player_state"] == 4:
            print("Waiting for other player to reveal...")
            if global_state["action_timer"] + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_rps.call(RPS.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
        elif global_state["state"] == 5 and global_state["winner"] == codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You won the game!")
            print("Registering win...", end=" ", flush=True)
            trysend(lambda: appclient_platform.call(GamePlatform.win_game, player.pk, challenger=other, app=app_id))
            print("Getting money...", end=" ", flush=True)
            trysend(lambda: appclient_rps.delete(player.pk, asset=berluscoin_id, creator=creator))
            print("Done!")
            return
        elif global_state["state"] == 5 and global_state["winner"] != codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You lost :(")
            return
        elif global_state["state"] == 0:
            sp = client.suggested_params()
            print("Initializing game...", end=" ", flush=True)
            trysend(lambda: appclient_rps.call(RPS.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient_rps.app_addr, 210000), signer=player.acc), asset=berluscoin_id))
            print("Done!")
        elif global_state["state"] == 1:
            sp = client.suggested_params()
            stake = ask_number("How much do you want to stake?")
            print("Sending stake...", end=" ", flush=True)
            trysend(lambda: appclient_rps.opt_in(player.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_rps.app_addr, stake, berluscoin_id), signer=player.acc)))
            print("Done!")
        else:
            print("DEBUG:")
            print(global_state)
            print(local_state)
            sleep(3)
