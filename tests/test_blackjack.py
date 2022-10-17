import algosdk
from algosdk.atomic_transaction_composer import TransactionWithSigner
from beaker.client.application_client import ApplicationClient
import json
from hashlib import sha256
from src.algogames.blackjack.blackjack import Blackjack
import pytest
from src.algogames.config import fee_holder

from src.algogames.algorand import Account, client, sp, funder

def create_asset(creator):
    tx_id = client.send_transaction(algosdk.future.transaction.AssetCreateTxn(
        sender=creator.pk,
        sp=sp,
        total=10**16,
        decimals=0,
        default_frozen=False,
    ).sign(creator.sk))
    asset_id = algosdk.future.transaction.wait_for_confirmation(client, tx_id, 4)['asset-index']
    return asset_id, tx_id

def opt_in_asset(acc, asset):
    tx_id = client.send_transaction(algosdk.future.transaction.AssetTransferTxn(
        sender=acc.pk,
        receiver=acc.pk,
        amt=0,
        sp=sp,
        index=asset,
    ).sign(acc.sk))
    algosdk.future.transaction.wait_for_confirmation(client, tx_id, 4)
    return tx_id

def fund_asset(funder, funded, asset, amount):
    tx_id = client.send_transaction(algosdk.future.transaction.AssetTransferTxn(
        sender=funder.pk,
        receiver=funded.pk,
        amt=amount,
        sp=sp,
        index=asset,
    ).sign(funder.sk))
    algosdk.future.transaction.wait_for_confirmation(client, tx_id, 4)
    return tx_id

def fund_algo(funder, funded, amount):
    tx_id = client.send_transaction(algosdk.future.transaction.PaymentTxn(
        sender=funder.pk,
        receiver=funded.pk,
        amt=amount,
        sp=sp,
    ).sign(funder.sk))
    algosdk.future.transaction.wait_for_confirmation(client, tx_id, 4)
    return tx_id

def init_env(n):
    global berluscoin_id
    accounts = [Account.generate() for _ in range(n+1)]
    xavier, *others = accounts
    
    for acc in accounts:
        fund_algo(funder, acc, 10000000)
    asset, _ = create_asset(xavier)
    for acc in others:
        opt_in_asset(acc, asset)
        fund_asset(xavier, acc, asset, 500)
        
    berluscoin_id = asset
    return others+[asset]

def cant(f):
    with pytest.raises(Exception): f()

def test_blackjack_cancel():
    alice, bob, asset = init_env(2)
    
    alice_appclient = ApplicationClient(client=client, app=Blackjack(), signer=alice.acc)
    
    _, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=bob.pk, bank=bob.pk)
    alice_appclient.call(Blackjack.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 1000000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    alice_appclient.delete(alice.pk, asset=asset, other=bob.pk, fee_holder=bob.pk)

def test_blackjack_succesful():
    alice, bob, asset = init_env(2)
        
    alice_appclient = ApplicationClient(client=client, app=Blackjack(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=bob.pk, bank=bob.pk)

    bob_appclient = ApplicationClient(client=client, app=Blackjack(), signer=bob.acc, app_id=app_id)
    
    alice_appclient.call(Blackjack.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 1000000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, 
        txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    bob_appclient.opt_in(bob.pk,
        txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc, 100, asset), signer=bob.acc), fee_amount=20)
    
    for i in range(0,3):
        req = json.dumps({"nonce": i, "nonce_p": 100-i, "app": alice_appclient.app_id}).encode()
        alice_appclient.call(Blackjack.distribute_req, alice.pk, request=req)
        bob_appclient.call(Blackjack.distribute_act, bob.pk, sig=algosdk.logic.teal_sign_from_program(bob.sk, req, alice_appclient.approval_binary))
        print(alice_appclient.get_application_state())
    for i in range(3,4):
        req = json.dumps({"nonce": i, "nonce_p": 100-i, "app": alice_appclient.app_id}).encode()
        alice_appclient.call(Blackjack.hit_req, alice.pk, request=req)
        bob_appclient.call(Blackjack.hit_act, bob.pk, sig=algosdk.logic.teal_sign_from_program(bob.sk, req, alice_appclient.approval_binary))
        print(alice_appclient.get_application_state())
    for i in range(4,9):
        req = json.dumps({"nonce": i, "nonce_p": 100-i, "app": alice_appclient.app_id}).encode()
        alice_appclient.call(Blackjack.stand_req, alice.pk, request=req)
        bob_appclient.call(Blackjack.stand_act, bob.pk, sig=algosdk.logic.teal_sign_from_program(bob.sk, req, alice_appclient.approval_binary))
        print(alice_appclient.get_application_state())
        
    assert False
