import json
import random
import algosdk
import codecs
from beaker.client.application_client import ApplicationClient
from beaker2 import call_nosend, opt_in_nosend, finalize
from time import sleep
from utils import ask_number, ask_string, is_opted, try_get_creator, try_get_global, trysend, try_get_local
from game_platform.game_platform import GamePlatform, get_fee, min_stake
from algorand import client
from blackjack.blackjack import Blackjack, state_init, state_poor, state_wait, state_player, state_hit_act, state_bank, state_stand_act, state_finish, state_push, state_distribute, state_distribute_act
from algosdk.atomic_transaction_composer import TransactionWithSigner
from config import player, skull_id, platform_id, fee_holder
from blackjack import server_blackjack

def get_cards(cards: str, player: int):
    return [i for i, c in enumerate(cards) if ord(c) == player]

def get_card_value(id: int):
    vals = [1,2,3,4,5,6,7,8,9,10,"Jack","Queen","King"] 
    val = vals[id%13]
    suites = ["hearts", "diamonds", "clubs", "spades"]
    suite = suites[id//13]
    return f"{val} of {suite}"


def interact_blackjack(app_id=0):
    appclient_platform = ApplicationClient(client=client, app=Blackjack(), app_id=platform_id, signer=player.acc)
    appclient_blackjack = ApplicationClient(client=client, app=Blackjack(), app_id=app_id, signer=player.acc)
    revealed = False
    
    while True:
        round = client.status()['last-round']
        sp = client.suggested_params()
        puntazzi = try_get_local("puntazzi", appclient_platform.app_id)
        creator = try_get_creator(appclient_blackjack.app_id)
        winner, action_timer, global_state, nonce, bank, last_card, cards = try_get_global(["winner", "action_timer", "state", "nonce", "bank", "last_card", "cards"], appclient_blackjack.app_id)
        if appclient_blackjack.app_id:
            print(appclient_blackjack.get_application_state())
        if cards:
            print(cards)
            print(f"Your hand: {', '.join(map(get_card_value, get_cards(cards, 1)))}")
            print(f"Bank hand: {', '.join(map(get_card_value, get_cards(cards, 2)))}")
        server_blackjack.interact_blackjack(appclient_blackjack.app_id)
        
        if appclient_blackjack.app_id == 0:
            print("Creating blackjack game...", end=" ", flush=True)
            app_id, _, _ = trysend(lambda: appclient_blackjack.create(player.pk, asset=skull_id, fee_holder=fee_holder.pk, bank=fee_holder.pk))
            print("Done!")
        elif global_state == state_init:
            print("Initializing game...", end=" ", flush=True)
            trysend(lambda: appclient_blackjack.call(Blackjack.init, player.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(player.pk, sp, appclient_blackjack.app_addr, 1000000), signer=player.acc), asset=skull_id))
            print("Done!")
        elif global_state == state_poor:
            stake = ask_number("How much do you want to stake?", range=[min_stake, None])
            fee_amount = get_fee(puntazzi)
            print("Sending stake...", end=" ", flush=True)
            trysend(lambda: finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.new_game, player.pk, game="blackjack", app=appclient_blackjack.app_id, 
                txn=opt_in_nosend(appclient_blackjack, player.pk, fee_amount=fee_amount, 
                txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(player.pk, sp, appclient_blackjack.app_addr, stake, skull_id), signer=player.acc)))))
            print("Done!")
        elif global_state == state_wait and player.pk == creator:
            print("Waiting for players...")
        elif not is_opted(player.pk, appclient_blackjack.app_id):
            print("You are not playing this game.")
            return 
        elif revealed and (global_state == state_player or global_state == state_bank or global_state == state_distribute):
            revealed = False
            print(f"Uncovered card: {get_card_value(last_card)}")
        elif global_state == state_player:
            choice = ask_string("Do you want to hit or stand? (hit/stand)", lambda x: x=='hit' or x=='stand')
            nonce_p = random.randint(0, 2**64-1)
            fun = Blackjack.stand_req if choice == 'stand' else Blackjack.hit_req
            print("Sending request...", end=" ", flush=True)
            trysend(lambda: appclient_blackjack.call(fun, player.pk, request=json.dumps({"nonce": nonce, "nonce_p": nonce_p, "app": appclient_blackjack.app_id}).encode()))
            print("Done!")
            revealed = True
        elif global_state == state_hit_act or global_state == state_stand_act or global_state == state_distribute_act:
            print("Waiting for dealer to serve...")
            # if action_timer + action_timeout <= round:
            #     print("Player inactive, reporting...", end=" ", flush=True)
            #     trysend(lambda: appclient_blackjack.call(Blackjack.forfeit, player.pk))
            #     print("Done!")
            # else:
            #     sleep(3)
            sleep(3)
        elif global_state == state_bank or global_state == state_distribute:
            nonce_p = random.randint(0, 2**64-1)
            print("Choosing card for bank...", end=" ", flush=True)
            fun = Blackjack.stand_req if global_state == state_bank else Blackjack.distribute_req
            trysend(lambda: appclient_blackjack.call(fun, player.pk, request=json.dumps({"nonce": nonce, "nonce_p": nonce_p, "app": appclient_blackjack.app_id}).encode()))
            print("Done!")
            revealed = True
        elif global_state == state_finish and winner == codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You won the game!")
            print("Registering win...", end=" ", flush=True)
            trysend(lambda: appclient_platform.call(GamePlatform.win_game, player.pk, challenger=fee_holder.pk, app=appclient_blackjack.app_id))
            print("Getting money...", end=" ", flush=True)
            trysend(lambda: appclient_blackjack.delete(player.pk, asset=skull_id, other=fee_holder.pk, fee_holder=fee_holder.pk))
            print("Done!")
            return
        elif global_state == state_finish and winner != codecs.encode(algosdk.encoding.decode_address(player.pk), 'hex').decode():
            print("You lost :(")
            return
        elif global_state == state_push:
            print("Draw.")
            print("Getting money...", end=" ", flush=True)
            trysend(lambda: appclient_blackjack.delete(player.pk, asset=skull_id, other=fee_holder.pk, fee_holder=fee_holder.pk))
            print("Done!")
            return
        else:
            print("NO ACTION")
            sleep(3)
