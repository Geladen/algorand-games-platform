from beaker.client.application_client import ApplicationClient
from algosdk.atomic_transaction_composer import TransactionWithSigner
import algosdk

from morra import interact_morra
from morra.morra import SaMurra, approval_binary as morra_ab, clear_binary as morra_cb
from algogames.platform.game_platform import GamePlatform
from algogames.algorand import client, sp, xavier, alice, bob

def interact():
    xavier_appclient = ApplicationClient(client=client, app=GamePlatform(), signer=xavier.acc)
    
    # CREATE
    app_id, app_acc, tx_id = xavier_appclient.create()
    print("platform_create", tx_id, app_id)
    
    alice_appclient = ApplicationClient(client=client, app=GamePlatform(), signer=alice.acc, app_id=app_id)
    bob_appclient = ApplicationClient(client=client, app=GamePlatform(), signer=bob.acc, app_id=app_id)
    
    res = xavier_appclient.call(GamePlatform.init, xavier.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(xavier.pk, sp, app_acc, 210000), signer=xavier.acc))
    berluscoin = res.tx_info["inner-txns"][0]["asset-index"]
    print("platform_init", res.tx_id, berluscoin)
    
    res = alice_appclient.opt_in(alice.pk)
    print("platform_optin", res)
    
    # PLAY
    res = alice_appclient.call(GamePlatform.new_game, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.ApplicationCreateTxn(
        sender=alice.pk, 
        sp=sp, 
        on_complete=algosdk.future.transaction.OnComplete.NoOpOC, 
        approval_program=morra_ab, 
        clear_program=morra_cb, 
        global_schema=SaMurra().app_state.schema(),
        local_schema=SaMurra().acct_state.schema(),
        foreign_assets=[berluscoin],
        app_args=[b'S\xff\x1a\x06', b'\x00'],
    ), signer=alice.acc))
    print("new_game", res.tx_id)

    for acc in [alice, bob]:
        res = algosdk.future.transaction.wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(
            sender=acc.pk,
            receiver=acc.pk,
            amt=0,
            sp=sp,
            index=berluscoin,
        ).sign(acc.sk)), 4)
        print("optin_asset", "XXXX")
        
    res = alice_appclient.call(GamePlatform.swap, alice.pk, asset=berluscoin, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(
        sender=alice.pk,
        sp=sp,
        receiver=app_acc,
        amt=3,
    ), signer=alice.acc))
    print("swap_1", res.tx_id)
    
    bob_appclient.call(GamePlatform.swap, bob.pk, asset=berluscoin, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(
        sender=bob.pk,
        sp=sp,
        receiver=app_acc,
        amt=3,
    ), signer=bob.acc))
    print("swap_2", res.tx_id)
    
    morra_app_id = alice_appclient.get_account_state()["current_game"]
    morra_app_acc = algosdk.logic.get_application_address(morra_app_id)
    
    interact_morra.play_morra(morra_app_id, morra_app_acc, berluscoin, alice, bob)
    
    res = alice_appclient.call(GamePlatform.win_game, alice.pk, app=morra_app_id)
    print("win_game", res.tx_id)

    interact_morra.win_morra(morra_app_id, berluscoin, alice, bob)
    
    # STATE
    print(alice_appclient.get_application_state())
    print(alice_appclient.get_account_state())
    