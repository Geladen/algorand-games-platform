import json
import random
import algosdk
import codecs
from algosdk.atomic_transaction_composer import TransactionWithSigner
from hashlib import sha256
from beaker.client.application_client import ApplicationClient
from beaker2 import call_nosend, opt_in_nosend, finalize
from time import sleep
from algorand import client
from config import player, skull_id, platform_id, fee_holder
from morra.morra import SaMurra, action_timeout, state_init, state_poor, state_wait, state_commit, state_reveal, state_finish
from game_platform.game_platform import GamePlatform, get_fee, min_stake
from utils import ask_choice, ask_number, ask_choice, fetch_secret, is_opted, store_secret, try_get_creator, try_get_global, trysend, try_get_local

def interact_morra(app_id=0):
    appclient_platform = ApplicationClient(client=client, app=SaMurra(), app_id=platform_id, signer=player.acc)
    appclient_morra = ApplicationClient(client=client, app=SaMurra(), app_id=app_id, signer=player.acc)
    revealed = False
    
    while True:
        round = client.status()['last-round']
        sp = client.suggested_params()
        puntazzi = try_get_local("puntazzi", appclient_platform.app_id)
        creator = try_get_creator(appclient_morra.app_id)
        winner, action_timer, challenger, global_state = try_get_global(["winner", "action_timer", "challenger", "state"], appclient_morra.app_id)
        player_state, your_hand, your_guess = try_get_local(["player_state", "player_hand", "player_guess"], appclient_morra.app_id)
        if challenger:
            challenger = algosdk.encoding.encode_address(codecs.decode(challenger.encode(), 'hex'))
            other = creator if challenger == player.pk else challenger
            other_hand, other_guess = try_get_local(["player_hand", "player_guess"], appclient_morra.app_id, other)
            
        if revealed and global_state != state_reveal:
            revealed = False
            total = your_hand + other_hand
            print(f"Your hand: {your_hand}, Challenger hand: {other_hand}, Total: {total}")
            print(f"Your guess: {your_guess}, Challenger guess: {other_guess}")
            if total == your_guess and total != other_guess:
                print("You won the round!")
            elif total != your_guess and total == other_guess:
                print("Challenger won the round!")
            else:
                print("Draw")
                
        if appclient_morra.app_id == 0:
            print("Creating morra game...", end=" ", flush=True)
            app_id, _, _ = trysend(lambda: appclient_morra.create(player.pk, asset=skull_id, fee_holder=fee_holder.pk))
            print("Done!")
        elif global_state == state_init:
            print("Initializing game...", end=" ", flush=True)
            trysend(lambda: appclient_morra.call(SaMurra.init, player.pk, asset=skull_id, 
                txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient_morra.app_addr, 210000), signer=player.acc)))
            print("Done!")
        elif global_state == state_poor:
            stake = ask_number("How much do you want to stake?", range=[min_stake, None])
            fee_amount = get_fee(puntazzi)
            print("Sending stake...", end=" ", flush=True)
            trysend(lambda: finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.new_game, player.pk, game="morra", app=appclient_morra.app_id, 
                txn=opt_in_nosend(appclient_morra, player.pk, fee_amount=fee_amount, 
                txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_morra.app_addr, stake, skull_id), signer=player.acc)))))
            print("Done!")
        elif global_state == state_wait and player.pk == creator:
            print("Waiting for players...")
            sleep(5)
        elif global_state == state_wait and player.pk != creator:
            stake = try_get_global('stake', appclient_morra.app_id)
            choice = ask_choice(f"Stake is {stake}. Join?", ["y", "N"])
            if choice == "n":
                return 
            fee_amount = get_fee(puntazzi)
            print("Joining game...", end=" ", flush=True)
            trysend(lambda: finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.join_game, player.pk, challenger=creator, app=appclient_morra.app_id,
                txn=opt_in_nosend(appclient_morra, player.pk, fee_amount=fee_amount, 
                txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_morra.app_addr, stake, skull_id), signer=player.acc)))))
            print("Done!")
        elif not is_opted(player.pk, appclient_morra.app_id):
            print("You are not playing this game.")
            return 
        elif global_state == state_commit and player_state != state_commit:
            hand = ask_number("What is your hand?")
            guess = ask_number("What is your guess?", skip_line=False)
            nonce = random.randint(0, 2**64-1)
            secret = json.dumps({"guess": guess, "hand": hand, "nonce": nonce})
            store_secret(secret, appclient_morra.app_id, player.pk)
            print("Sending commit...", end=" ", flush=True)
            trysend(lambda: appclient_morra.call(SaMurra.commit, player.pk, commit=sha256(secret.encode()).digest()))
            print("Done!")
        elif global_state == state_commit and player_state == state_commit:
            print("Waiting for other player to commit...")
            if action_timer + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_morra.call(SaMurra.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
        elif global_state == state_reveal and player_state != state_reveal:
            if "secret" not in vars() or secret is None:
                secret = fetch_secret(appclient_morra.app_id, player.pk)
            print("Revealing your choice...", end=" ", flush=True)
            trysend(lambda: appclient_morra.call(SaMurra.reveal, player.pk, other=other, reveal=secret))
            print("Done!")
            revealed=True
        elif global_state == state_reveal and player_state == state_reveal:
            print("Waiting for other player to reveal...")
            if action_timer + action_timeout <= round:
                print("Player inactive, reporting...", end=" ", flush=True)
                trysend(lambda: appclient_morra.call(SaMurra.forfeit, player.pk))
                print("Done!")
            else:
                sleep(3)
            revealed=True
        elif global_state == state_finish and winner == codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You won the game!")
            print("Registering win...", end=" ", flush=True)
            trysend(lambda: appclient_platform.call(GamePlatform.win_game, player.pk, challenger=other, app=appclient_morra.app_id))
            print("Getting money...", end=" ", flush=True)
            trysend(lambda: appclient_morra.delete(player.pk, asset=skull_id, creator=creator, fee_holder=fee_holder.pk))
            print("Done!")
            return
        elif global_state == state_finish and winner != codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You lost :(")
            return
        else:
            print("NO ACTION")
            sleep(3)
