
from hashlib import sha256
import json
from beaker.client.application_client import ApplicationClient
from algosdk.atomic_transaction_composer import AccountTransactionSigner, TransactionWithSigner
from algosdk.v2client.algod import AlgodClient
import algosdk

from morra import SaMurra, berluscoin

if __name__ == "__main__":
    client = AlgodClient('', 'https://node.testnet.algoexplorerapi.io')
    sp = client.suggested_params()
    
    skb = "UK0dU93ANF1kTXNM0GBDIbmDfn8+U5lLqiRwycoTUn0ZJ6xDdkEf+OE+mr8HqeaGHsAgs5jwwhOSDPAM/GfaJg=="
    pkb = algosdk.account.address_from_private_key(skb)
    accb = AccountTransactionSigner(skb)
    
    sk1 = "oQKvXVRWZyavpsOUiz0P+uBDBSu6Wr286xU2Zq00k3y2yh150dl7ggN0+iVATCrkLjlblu6QA9yd85Sbeu//0g=="
    pk1 = algosdk.account.address_from_private_key(sk1)
    acc1 = AccountTransactionSigner(sk1)
    
    sk2 = "4jvgBR6On0AXddbWrHNwW8eMuT05+zAYJTC/uCCjhqBDP501Eplyo6paQnBnO1/ut1IneqRIX2Foa4yUpHF1LA=="
    pk2 = algosdk.account.address_from_private_key(sk2)
    acc2 = AccountTransactionSigner(sk2)
    
    if False:
        berluscoin = algosdk.future.transaction.wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetCreateTxn(
            sender=pkb,
            sp=sp,
            total=10**16,
            decimals=0,
            default_frozen=False,
        ).sign(skb)), 4)['asset-index']
        
        for (pk, sk) in [(pk1, sk1), (pk2, sk2)]:
            res = algosdk.future.transaction.wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(
                sender=pk,
                receiver=pk,
                amt=0,
                sp=sp,
                index=berluscoin,
            ).sign(sk)), 4)
            print(res)
            res = algosdk.future.transaction.wait_for_confirmation(client, client.send_transaction(algosdk.future.transaction.AssetTransferTxn(
                sender=pkb,
                receiver=pk,
                amt=100,
                sp=sp,
                index=berluscoin,
            ).sign(skb)), 4)
            print(res)
    
    appclient1 = ApplicationClient(client=client, app=SaMurra(), signer=acc1)
    
    # CREATE
    app_id, app_acc, tx_id = appclient1.create()
    print(app_id)
    print(tx_id)
    
    res = appclient1.call(SaMurra.init, pk1, txn=TransactionWithSigner(algosdk.future.transaction.PaymentTxn(pk1, sp, app_acc, 210000), signer=acc1), asset=berluscoin)
    print(res.tx_id)
    
    appclient2 = ApplicationClient(client=client, app=SaMurra(), signer=acc2, app_id=app_id)
    
    # JOIN 
    res = appclient1.opt_in(pk1, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(pk1, sp, app_acc, 2, berluscoin), signer=acc1))
    print(res)
    res = appclient2.opt_in(pk2, txn=TransactionWithSigner(algosdk.future.transaction.AssetTransferTxn(pk2, sp, app_acc, 2, berluscoin), signer=acc2))
    print(res)
    
    # COMMIT
    res = appclient1.call(SaMurra.commit, pk1, commit=sha256(json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}).encode()).digest())
    print(res.tx_id)
    res = appclient2.call(SaMurra.commit, pk2, commit=sha256(json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}).encode()).digest())
    print(res.tx_id)
    
    # REVEAL
    res = appclient1.call(SaMurra.reveal, pk1, other=algosdk.encoding.decode_address(pk2), reveal=json.dumps({"guess": 3, "hand": 1, "nonce": 1462867421}))
    print(res.tx_id)
    res = appclient2.call(SaMurra.reveal, pk2, other=algosdk.encoding.decode_address(pk1), reveal=json.dumps({"guess": 6, "hand": 2, "nonce": 7347342978432}))
    print(res.tx_id)
    
    # COMMIT
    res = appclient2.call(SaMurra.commit, pk2, commit=sha256(json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}).encode()).digest())
    print(res.tx_id)
    res = appclient1.call(SaMurra.commit, pk1, commit=sha256(json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}).encode()).digest())
    print(res.tx_id)
    
    # REVEAL
    res = appclient2.call(SaMurra.reveal, pk2, other=algosdk.encoding.decode_address(pk1), reveal=json.dumps({"guess": 7, "hand": 4, "nonce": 7347342978432}))
    print(res.tx_id)
    res = appclient1.call(SaMurra.reveal, pk1, other=algosdk.encoding.decode_address(pk2), reveal=json.dumps({"guess": 5, "hand": 1, "nonce": 1462867421}))
    print(res.tx_id)
    
    # FINISH
    res = appclient1.delete(pk1, asset=berluscoin)
    print(res)
    
    # STATE
    print(appclient1.get_application_state())
    print(appclient1.get_account_state())
    print(appclient2.get_account_state())
    