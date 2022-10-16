import algosdk
from algosdk.atomic_transaction_composer import TransactionWithSigner
from beaker.client.application_client import ApplicationClient
import json
from hashlib import sha256
from src.algogames.rps.rps import RPS
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
    accounts = [Account.generate() for _ in range(n+1)]
    xavier, *others = accounts
    
    for acc in accounts:
        fund_algo(funder, acc, 10000000)
    asset, _ = create_asset(xavier)
    for acc in others:
        opt_in_asset(acc, asset)
        fund_asset(xavier, acc, asset, 500)
        
    return others+[asset]

def cant(f):
    with pytest.raises(Exception): f()

def test_rps_cancel():
    alice, _, charlie, asset = init_env(3)
    
    alice_appclient = ApplicationClient(client=client, app=RPS(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=charlie.pk)
    alice_appclient.call(RPS.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk, fee_holder=charlie.pk)

def test_rps_succesfull():
    alice, bob, charlie, asset = init_env(3)
        
    alice_appclient = ApplicationClient(client=client, app=RPS(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=charlie.pk)

    bob_appclient = ApplicationClient(client=client, app=RPS(), signer=bob.acc, app_id=app_id)
    charlie_appclient = ApplicationClient(client=client, app=RPS(), signer=charlie.acc, app_id=app_id)
    
    alice_appclient.call(RPS.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    bob_appclient.opt_in(bob.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc, 100, asset), signer=bob.acc), fee_amount=20)
    cant(lambda: charlie_appclient.opt_in(charlie.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(charlie.pk, sp, app_acc, 2, asset), signer=charlie.acc)))
    
    alice_appclient.call(RPS.commit, alice.pk, commit=sha256(json.dumps({"hand": "rock", "nonce": 1462867421}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "scissors", "nonce": 7347342978432}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    alice_appclient.call(RPS.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"hand": "rock", "nonce": 1462867421}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"hand": "scissors", "nonce": 7347342978432}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "rock", "nonce": 7347342978432}).encode()).digest())
    alice_appclient.call(RPS.commit, alice.pk, commit=sha256(json.dumps({"hand": "paper", "nonce": 1462867421}).encode()).digest())
    
    bob_appclient.call(RPS.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"hand": "rock", "nonce": 7347342978432}))
    alice_appclient.call(RPS.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"hand": "paper", "nonce": 1462867421}))
    
    alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk, fee_holder=charlie.pk)

def test_rps_forfeit_commit():
    alice, bob, charlie, asset = init_env(3)
        
    alice_appclient = ApplicationClient(client=client, app=RPS(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=charlie.pk)

    bob_appclient = ApplicationClient(client=client, app=RPS(), signer=bob.acc, app_id=app_id)
    charlie_appclient = ApplicationClient(client=client, app=RPS(), signer=charlie.acc, app_id=app_id)
    
    alice_appclient.call(RPS.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    bob_appclient.opt_in(bob.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc, 100, asset), signer=bob.acc), fee_amount=20)
    cant(lambda: charlie_appclient.opt_in(charlie.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(charlie.pk, sp, app_acc, 2, asset), signer=charlie.acc)))
    
    alice_appclient.call(RPS.commit, alice.pk, commit=sha256(json.dumps({"hand": "rock", "nonce": 1462867421}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "scissors", "nonce": 7347342978432}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    alice_appclient.call(RPS.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"hand": "rock", "nonce": 1462867421}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"hand": "scissors", "nonce": 7347342978432}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "paper", "nonce": 7347342978432}).encode()).digest())
    for _ in range(7):
        alice_appclient.fund(0, alice.pk)
        cant(lambda: bob_appclient.call(RPS.forfeit, bob.pk))
    alice_appclient.fund(0, alice.pk)
    bob_appclient.call(RPS.forfeit, bob.pk, asset=asset, creator=alice.pk)
    bob_appclient.delete(bob.pk, asset=asset, creator=alice.pk, fee_holder=charlie.pk)
    
def test_rps_forfeit_reveal():
    alice, bob, charlie, asset = init_env(3)
        
    alice_appclient = ApplicationClient(client=client, app=RPS(), signer=alice.acc)
    
    app_id, app_acc, _ = alice_appclient.create(asset=asset, fee_holder=charlie.pk)

    bob_appclient = ApplicationClient(client=client, app=RPS(), signer=bob.acc, app_id=app_id)
    charlie_appclient = ApplicationClient(client=client, app=RPS(), signer=charlie.acc, app_id=app_id)
    
    alice_appclient.call(RPS.init, alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc, 210000), signer=alice.acc), asset=asset)
    alice_appclient.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc, 100, asset), signer=alice.acc), fee_amount=20)
    bob_appclient.opt_in(bob.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc, 100, asset), signer=bob.acc), fee_amount=20)
    cant(lambda: charlie_appclient.opt_in(charlie.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(charlie.pk, sp, app_acc, 2, asset), signer=charlie.acc)))
    
    alice_appclient.call(RPS.commit, alice.pk, commit=sha256(json.dumps({"hand": "rock", "nonce": 1462867421}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "scissors", "nonce": 7347342978432}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    alice_appclient.call(RPS.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"hand": "rock", "nonce": 1462867421}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    bob_appclient.call(RPS.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"hand": "scissors", "nonce": 7347342978432}))
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    bob_appclient.call(RPS.commit, bob.pk, commit=sha256(json.dumps({"hand": "paper", "nonce": 7347342978432}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    alice_appclient.call(RPS.commit, alice.pk, commit=sha256(json.dumps({"hand": "rock", "nonce": 1462867421}).encode()).digest())
    cant(lambda: alice_appclient.delete(alice.pk, asset=asset, creator=alice.pk))
    
    bob_appclient.call(RPS.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"hand": "paper", "nonce": 7347342978432}))
    for _ in range(7):
        alice_appclient.fund(0, alice.pk)
        cant(lambda: bob_appclient.call(RPS.forfeit, bob.pk))
    alice_appclient.fund(0, alice.pk)
    bob_appclient.call(RPS.forfeit, bob.pk, asset=asset)
    bob_appclient.delete(bob.pk, asset=asset, creator=alice.pk, fee_holder=charlie.pk)
