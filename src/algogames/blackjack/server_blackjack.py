from beaker.client.application_client import ApplicationClient
from beaker2 import call_nosend, finalize, opt_in_nosend
from game_platform.game_platform import GamePlatform, get_fee
from utils import try_get_creator, try_get_global, try_get_local, trysend
from algorand import client
from blackjack.blackjack import Blackjack, state_wait, state_hit_act, state_stand_act, state_distribute_act, state_finish
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk
import codecs
from config import platform_id, skull_id, fee_holder

bank = fee_holder

def interact_blackjack(app_id):
    appclient_platform = ApplicationClient(client=client, app=Blackjack(), app_id=platform_id, signer=bank.acc)
    appclient_blackjack = ApplicationClient(client=client, app=Blackjack(), app_id=app_id, signer=bank.acc)
    
    appclient_blackjack.build()
    
    sp = client.suggested_params()
    creator = try_get_creator(appclient_blackjack.app_id)
    stake, global_state, request, winner = try_get_global(["stake", "state", "request", "winner"], appclient_blackjack.app_id)
        
    if global_state == state_wait:
        appclient_platform.call(GamePlatform.buy, fee_holder.pk, asset=skull_id, txn=TransactionWithSigner(
            algosdk.future.transaction.PaymentTxn(fee_holder.pk, sp, appclient_platform.app_addr, stake), 
            fee_holder.acc
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
        trysend(lambda: appclient_blackjack.delete(bank.pk, asset=skull_id, other=creator, fee_holder=fee_holder.pk))
