import algosdk
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner
from beaker.client.application_client import ApplicationClient
import json
from hashlib import sha256
from src.algogames.beaker2 import call_nosend, create_nosend, opt_in_nosend, finalize
from src.algogames.morra.morra import SaMurra
from src.algogames.game_platform.game_platform import GamePlatform
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
    accounts = [Account.generate() for _ in range(n)]
    
    for acc in accounts:
        fund_algo(funder, acc, 2000000)
        
    return accounts

def cant(f):
    with pytest.raises(Exception): f()


def test_morra_win_alice():
    xavier, alice, bob = init_env(3)
    
    # Create platform    
    xavier_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=xavier.acc)
    app_id_platform, app_acc_platform, _ = xavier_appclient_platform.create()
    res = xavier_appclient_platform.call(GamePlatform.init, xavier.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(xavier.pk, sp, app_acc_platform, 210000), signer=xavier.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    
    # Opt into platform
    alice_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=alice.acc, app_id=app_id_platform)
    alice_appclient_platform.opt_in(alice.pk)
    bob_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=bob.acc, app_id=app_id_platform)
    bob_appclient_platform.opt_in(bob.pk)
    
    # Buy some berluscoin
    for (acc, acc_appclient_platform) in [(alice, alice_appclient_platform), (bob, bob_appclient_platform)]:
        opt_in_asset(acc, asset)
        acc_appclient_platform.call(GamePlatform.swap, acc.pk, asset=asset, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(acc.pk, sp, app_acc_platform, 3), signer=acc.acc))
        
    # Create new morra game
    alice_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc)
    finalize(alice_appclient_platform, call_nosend(alice_appclient_platform, GamePlatform.new_game, alice.pk, 
        txn=create_nosend(alice_appclient_morra, alice.pk, asset=asset)))
    app_id_morra = alice_appclient_platform.get_account_state()["current_game"]
    app_acc_morra = algosdk.logic.get_application_address(app_id_morra)
    
    # Initialize morra game
    alice_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc, app_id=app_id_morra)
    alice_appclient_morra.call(SaMurra.init, alice.pk, asset=asset, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc_morra, 210000), signer=alice.acc))
    alice_appclient_morra.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc_morra, 2, asset), signer=alice.acc))
    
    # Join morra game
    bob_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=bob.acc, app_id=app_id_morra)
    finalize(bob_appclient_platform, call_nosend(bob_appclient_platform, GamePlatform.join_game, bob.pk, challenger=alice.pk, 
        txn=opt_in_nosend(bob_appclient_morra, bob.pk, 
        txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc_morra, 2, asset), signer=bob.acc))))
    
    # Play
    alice_appclient_morra.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}).encode()).digest())
    bob_appclient_morra.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}).encode()).digest())
    
    alice_appclient_morra.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}))
    bob_appclient_morra.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}))
    
    bob_appclient_morra.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}).encode()).digest())
    alice_appclient_morra.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}).encode()).digest())
    
    bob_appclient_morra.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}))
    alice_appclient_morra.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}))

    # Win    
    alice_appclient_platform.call(GamePlatform.win_game, alice.pk, app=app_id_morra)
    alice_appclient_morra.delete(alice.pk, asset=asset, creator=alice.pk)

def tesasdt_morra_win_bob():
    xavier, alice, bob = init_env(3)
    
    # Create platform    
    xavier_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=xavier.acc)
    app_id_platform, app_acc_platform, _ = xavier_appclient_platform.create()
    res = xavier_appclient_platform.call(GamePlatform.init, xavier.pk, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(xavier.pk, sp, app_acc_platform, 210000), signer=xavier.acc))
    asset = res.tx_info["inner-txns"][0]["asset-index"]
    
    # Opt into platform
    alice_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=alice.acc, app_id=app_id_platform)
    alice_appclient_platform.opt_in(alice.pk)
    bob_appclient_platform = ApplicationClient(client=client, app=GamePlatform(), signer=bob.acc, app_id=app_id_platform)
    bob_appclient_platform.opt_in(bob.pk)
    
    # Buy some berluscoin
    for (acc, acc_appclient_platform) in [(alice, alice_appclient_platform), (bob, bob_appclient_platform)]:
        opt_in_asset(acc, asset)
        acc_appclient_platform.call(GamePlatform.swap, acc.pk, asset=asset, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(acc.pk, sp, app_acc_platform, 3), signer=acc.acc))
        
    # Create new morra game
    alice_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc)
    finalize(alice_appclient_platform,call_nosend(alice_appclient_platform, GamePlatform.new_game, alice.pk, 
        txn=create_nosend(alice_appclient_morra, alice.pk, asset=asset)))
    app_id_morra = alice_appclient_platform.get_account_state()["current_game"]
    app_acc_morra = algosdk.logic.get_application_address(app_id_morra)
    
    # Initialize morra game
    alice_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=alice.acc, app_id=app_id_morra)
    alice_appclient_morra.call(SaMurra.init, alice.pk, asset=asset, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(alice.pk, sp, app_acc_morra, 210000), signer=alice.acc))
    alice_appclient_morra.opt_in(alice.pk, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(alice.pk, sp, app_acc_morra, 2, asset), signer=alice.acc))
    
    # Join morra game
    bob_appclient_morra = ApplicationClient(client=client, app=SaMurra(), signer=bob.acc, app_id=app_id_morra)
    finalize(bob_appclient_platform, call_nosend(bob_appclient_platform, GamePlatform.join_game, bob.pk, challenger=alice.pk, 
        txn=opt_in_nosend(bob_appclient_morra, bob.pk, 
        txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(bob.pk, sp, app_acc_morra, 2, asset), signer=bob.acc))))
    
    # Play
    alice_appclient_morra.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 6, "hand": 1, "nonce": 1462867421}).encode()).digest())
    bob_appclient_morra.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 3, "hand": 2, "nonce": 7347342978432}).encode()).digest())
    
    alice_appclient_morra.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 6, "hand": 1, "nonce": 1462867421}))
    bob_appclient_morra.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 3, "hand": 2, "nonce": 7347342978432}))
    
    bob_appclient_morra.call(SaMurra.commit, bob.pk, commit=sha256(json.dumps({"guess": 5, "hand": 4, "nonce": 7347342978432}).encode()).digest())
    alice_appclient_morra.call(SaMurra.commit, alice.pk, commit=sha256(json.dumps({"guess": 7, "hand": 1, "nonce": 1462867421}).encode()).digest())
    
    bob_appclient_morra.call(SaMurra.reveal, bob.pk, other=algosdk.encoding.decode_address(alice.pk), reveal=json.dumps({"guess": 5, "hand": 4, "nonce": 7347342978432}))
    alice_appclient_morra.call(SaMurra.reveal, alice.pk, other=algosdk.encoding.decode_address(bob.pk), reveal=json.dumps({"guess": 7, "hand": 1, "nonce": 1462867421}))

    # Win    
    bob_appclient_platform.call(GamePlatform.win_game, bob.pk, app=app_id_morra)
    bob_appclient_morra.delete(bob.pk, asset=asset, creator=alice.pk)
