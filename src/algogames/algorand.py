import os
import algosdk
from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk.v2client.algod import AlgodClient

class Account:
    def __init__(self, sk):
        self.sk = sk
        self.pk = algosdk.account.address_from_private_key(sk)
        self.acc = AccountTransactionSigner(sk)
    def __str__(self):
        return self.pk
    @staticmethod
    def generate():
        return Account(algosdk.account.generate_account()[0])
    
print(os.environ["ALGOD_BASE_SERVER"]+":"+os.environ["ALGOD_PORT"])
address = os.environ["ALGOD_BASE_SERVER"]+((":"+os.environ["ALGOD_PORT"]) if os.environ["ALGOD_PORT"] else "")
client = AlgodClient(os.environ["ALGOD_TOKEN"], address)
sp = client.suggested_params()

funder = Account("UK0dU93ANF1kTXNM0GBDIbmDfn8+U5lLqiRwycoTUn0ZJ6xDdkEf+OE+mr8HqeaGHsAgs5jwwhOSDPAM/GfaJg==")
# alice = Account("oQKvXVRWZyavpsOUiz0P+uBDBSu6Wr286xU2Zq00k3y2yh150dl7ggN0+iVATCrkLjlblu6QA9yd85Sbeu//0g==")
# bob = Account("4jvgBR6On0AXddbWrHNwW8eMuT05+zAYJTC/uCCjhqBDP501Eplyo6paQnBnO1/ut1IneqRIX2Foa4yUpHF1LA==")
 