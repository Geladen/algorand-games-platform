from beaker.client.application_client import ApplicationClient
from beaker2 import call_nosend, finalize, opt_in_nosend
from game_platform.game_platform import GamePlatform, get_fee
from utils import try_get_creator, try_get_global, try_get_local, trysend
from algorand import Account, client
from blackjack.blackjack import Blackjack, state_wait, state_hit_act, state_stand_act, state_distribute_act, state_finish
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.future.transaction import wait_for_confirmation
from config import platform_id, skull_id, fee_holder
import algosdk
import codecs
import json

def create_account(player):
    acc = Account(algosdk.account.generate_account()[0])
    with open("src/algogames/blackjack/accounts.json", "r") as f:
        accs = json.load(f)
    accs[player] = acc.sk
    with open("src/algogames/blackjack/accounts.json", "w") as f:
        json.dump(accs, f)
    
    appclient_fee_holder = ApplicationClient(client, GamePlatform(), signer=fee_holder.acc, app_id=platform_id)
    appclient = ApplicationClient(client, GamePlatform(), signer=acc.acc, app_id=platform_id)
    sp = client.suggested_params()
    
    appclient_fee_holder.fund(1000000, acc.pk)
    appclient.opt_in(acc.pk, username="bank")
    wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(acc.pk, sp, acc.pk, 0, skull_id).sign(acc.sk)), 4)
    
    return acc.pk
    
def load_account(player):
    with open("src/algogames/blackjack/accounts.json") as f:
        accs = json.load(f)
    if player in accs:
        return Account(accs[player])
    

# Function that mocks the interactions executed by the bank. In a real implementation, the user would not have access to this logic, 
# or more specifically, to the private key of the bank account.
def interact_blackjack(app_id, player):
    bank = load_account(player)
    
    appclient_platform = ApplicationClient(client=client, app=Blackjack(), app_id=platform_id, signer=bank.acc)
    appclient_blackjack = ApplicationClient(client=client, app=Blackjack(), app_id=app_id, signer=bank.acc)
    
    appclient_blackjack.build()
    
    sp = client.suggested_params()
    creator = try_get_creator(appclient_blackjack.app_id)
    stake, global_state, request, winner = try_get_global(["stake", "state", "request", "winner"], appclient_blackjack.app_id)
        
    if global_state == state_wait:
        appclient_platform.call(GamePlatform.buy, bank.pk, asset=skull_id, txn=TransactionWithSigner(
            algosdk.future.transaction.PaymentTxn(bank.pk, sp, appclient_platform.app_addr, stake), 
            bank.acc
        ))
        puntazzi = try_get_local("puntazzi", appclient_platform.app_id)
        fee_amount = get_fee(puntazzi)
        trysend(lambda: finalize(appclient_platform, call_nosend(appclient_platform, GamePlatform.join_game, bank.pk, challenger=creator, app=appclient_blackjack.app_id,
            txn=opt_in_nosend(appclient_blackjack, bank.pk, fee_amount=fee_amount,
            txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bank.pk, sp, appclient_blackjack.app_addr, stake, skull_id), signer=bank.acc)))))
    elif global_state == state_hit_act or global_state == state_stand_act or global_state == state_distribute_act:
        funs = {state_hit_act: Blackjack.hit_act, state_stand_act: Blackjack.stand_act, state_distribute_act: Blackjack.distribute_act}
        fun = funs[global_state]
        appclient_blackjack.call(fun, bank.pk, sig=algosdk.logic.teal_sign_from_program(bank.sk, request.encode(), appclient_blackjack.approval_binary))
    elif global_state == state_finish and winner == codecs.encode(algosdk.encoding.decode_address(bank.pk), 'hex').decode():
        trysend(lambda: appclient_platform.call(GamePlatform.win_game, bank.pk, challenger=creator, app=appclient_blackjack.app_id))
        trysend(lambda: appclient_blackjack.delete(bank.pk, asset=skull_id, other=creator, fee_holder=fee_holder.pk))
