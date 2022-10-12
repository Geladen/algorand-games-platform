import algosdk
from algosdk.atomic_transaction_composer import TransactionWithSigner
from beaker.client.application_client import ApplicationClient
import json
from hashlib import sha256
from src.algogames.morra.morra import SaMurra
import pytest

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
    accounts = [Account.generate() for _ in range(n+1)]
    xavier, *others = accounts
    
    for acc in accounts:
        fund_algo(funder, acc, 1000000)
    asset, _ = create_asset(xavier)
    for acc in others:
        opt_in_asset(acc, asset)
        fund_asset(xavier, acc, asset, 5)
        
    return others+[asset]

def cant(f):
    with pytest.raises(Exception): f()

def test_morra_cancel():
    alice, asset = init_env(1)
    
    alice_appclient = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset)
    alice_appclient.call(SaMurra.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 2, asset), signer=alice.acc))
    alice_appclient.delete(alice.pk, asset=asset)

def test_morra_succesfull():
    alice, bob, charlie, asset = init_env(3)
        
    alice_appclient = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset)

    bob_appclient = ApplicationClient(client=client, app=SaMurra(), signer=bob.acc, app_id=app_id)
    charlie_appclient = ApplicationClient(client=client, app=SaMurra(), signer=charlie.acc, app_id=app_id)
    
    alice_appclient.call(SaMurra.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 2, asset), signer=alice.acc))
    bob_appclient.opt_in(bob.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc, 2, asset), signer=bob.acc))
    cant(lambda: charlie_appclient.opt_in(charlie.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(charlie.pk, sp, app_acc, 2, asset), signer=charlie.acc)))
    
    alice_appclient.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}).encode()).digest())
    bob_appclient.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}).encode()).digest())
    
    alice_appclient.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}))
    bob_appclient.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset))
    
    bob_appclient.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}).encode()).digest())
    alice_appclient.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}).encode()).digest())
    
    bob_appclient.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}))
    alice_appclient.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}))
    
    alice_appclient.delete(alice.pk, asset=asset)