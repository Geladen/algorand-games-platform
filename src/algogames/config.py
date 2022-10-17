from algorand import Account
import os
import sys

# DET2YQ3WIEP7RYJ6TK7QPKPGQYPMAIFTTDYMEE4SBTYAZ7DH3ITKNU7QIM
alice = Account("UK0dU93ANF1kTXNM0GBDIbmDfn8+U5lLqiRwycoTUn0ZJ6xDdkEf+OE+mr8HqeaGHsAgs5jwwhOSDPAM/GfaJg==")
# IM7Z2NISTFZKHKS2IJYGOO27523VEJ32UREF6YLINOGJJJDROUWHTGWNWE
bob = Account("4jvgBR6On0AXddbWrHNwW8eMuT05+zAYJTC/uCCjhqBDP501Eplyo6paQnBnO1/ut1IneqRIX2Foa4yUpHF1LA==")

#W3FB26OR3F5YEA3U7ISUATBK4QXDSW4W52IAHXE56OKJW6XP77JDP45ODE
fee_holder = Account("oQKvXVRWZyavpsOUiz0P+uBDBSu6Wr286xU2Zq00k3y2yh150dl7ggN0+iVATCrkLjlblu6QA9yd85Sbeu//0g==")

arg = int(sys.argv[1]) if len(sys.argv) >= 2 and sys.argv[1].isnumeric() else 0
match arg:
    case 1:
        player = alice
    case 2:
        player = bob 
    case _:
        player = bob

skull_id = int(os.environ['SKULL_ID']) if 'SKULL_ID' in os.environ else None
platform_id = int(os.environ['PLATFORM_ID']) if 'PLATFORM_ID' in os.environ else None
