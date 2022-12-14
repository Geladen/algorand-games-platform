from typing import Final
from pyteal import *
from beaker import *
from rps.rps import approval_binary as rps_ab, clear_binary as rps_cb
from morra.morra import approval_binary as morra_ab, clear_binary as morra_cb
from blackjack.blackjack import approval_binary as blackjack_ab, clear_binary as blackjack_cb

fee_amounts = [(5000000, 20), (25000000, 33), (500000000, 50), (None, 100)]

min_stake = 100
MIN_STAKE = Int(min_stake)

def get_fee(points):
    return next(x for x in fee_amounts if x[0] is None or x[0] >= points)[1]

def check_fees(fees, points, fee_amount):
    if len(fees) == 0:
        return Int(1)
    elif len(fees) == 1:
        return fee_amount == Int(fees[0][1])
    elif len(fees) > 1:
        return If(points <= Int(fees[0][0])).Then(fee_amount == Int(fees[0][1])).Else(
            check_fees(fees[1:], points, fee_amount)
        )
        
class GamePlatform(Application):
    asset: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    fee_holder: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)

    username: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    current_game: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    game_time: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    game_type: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    puntazzi: Final[AccountStateValue] = AccountStateValue(TealType.uint64)

    @create
    def create(self, fee_holder: abi.Account):
        """
        Callable to create the contract
        fee_holder: address that will receive the game fees
        """
        return Seq(
            self.fee_holder.set(fee_holder.address())
        )
        
    @external
    def init(self, txn: abi.PaymentTransaction):
        """
        Callable by the creator to initialize the application account, and create the SKULL asset
        txn: transaction that pays the minimum balance + fees of the contract
        """
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                txn.get().amount() == Int(210000),
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset_total: Int(10**16),
                TxnField.config_asset_decimals: Int(0),
                TxnField.config_asset_default_frozen: Int(0),
                TxnField.config_asset_name: Bytes("Algorand Skull Coin"),
                TxnField.config_asset_unit_name: Bytes("SKULL"),
            }),
            InnerTxnBuilder.Submit(),
            
            self.asset.set(InnerTxn.created_asset_id()),            
        )
        
    @external
    def buy(self, txn: abi.PaymentTransaction, asset: abi.Asset):
        """
        Callable to buy some SKULLs
        txn: transaction that pays the ALGOs to buy SKULLs
        asset: reference to self.asset (used to enable InnerTxn)
        """
        return Seq(
            Assert(
                txn.get().receiver() == Global.current_application_address(),
                asset.asset_id() == self.asset.get(),
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_amount: txn.get().amount(),
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_receiver: txn.get().sender(),
            }),
            InnerTxnBuilder.Submit()
        )
        
    @external
    def sell(self, txn: abi.AssetTransferTransaction):
        """
        Callable to buy some skulls
        txn: transaction that pays the SKULLs to get back ALGOs
        asset: reference to self.asset (used to enable InnerTxn)
        """
        return Seq(
            Assert(
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.Payment,
                TxnField.amount: txn.get().amount(),
                TxnField.receiver: txn.get().sender(),
            }),
            InnerTxnBuilder.Submit()
        )
        
    @opt_in
    def opt_in(self, username: abi.String):
        """
        Callable to join the platform
        username: the username to assign to the account
        """
        return Seq(
            self.username.set(username.get()),
            self.puntazzi.set(Int(0))
        )
        
    @external
    def new_game(self, game: abi.String, txn: abi.ApplicationCallTransaction, app: abi.Application):
        """
        Callable when creating a new game. Checks that the contract is initialized correctly, and if so, saves
        a reference of it in the local state of the caller, together with its type.
        txn: transaction in which the user opts into the game
        app: reference to txn.application_id
        """
        return Seq(
            Assert(
                app.application_id() == txn.get().application_id(),
                check_fees(fee_amounts, self.puntazzi.get(),  App.localGetEx(txn.get().sender(), txn.get().application_id(), Bytes("fee_amount")).outputReducer(lambda value, _: value)),
                And(
                    App.globalGetEx(txn.get().application_id(), Bytes("fee_holder")).outputReducer(lambda value, _: value) == self.fee_holder.get(),
                    App.globalGetEx(txn.get().application_id(), Bytes("asset")).outputReducer(lambda value, _: value),
                    Or(*[
                        And(
                            game.get() == Bytes(opt[0]),
                            AppParam.approvalProgram(txn.get().application_id()).outputReducer(lambda value, _: value) == Bytes(opt[1]),
                            AppParam.clearStateProgram(txn.get().application_id()).outputReducer(lambda value, _: value) == Bytes(opt[2]),
                            *opt[3],
                        )
                        for opt in [
                            ("morra", morra_ab, morra_cb, []), 
                            ("rps", rps_ab, rps_cb, []), 
                            ("blackjack", blackjack_ab, blackjack_cb, [])
                        ]
                    ])
                ),
                App.globalGetEx(txn.get().application_id(), Bytes("stake")).outputReducer(lambda value, _: value) >= MIN_STAKE
            ),
            self.current_game.set(txn.get().application_id()),
            self.game_time.set(Global.latest_timestamp()),
            self.game_type.set(game.get())
        )

    @external
    def join_game(self, challenger: abi.Account, txn: abi.ApplicationCallTransaction, app: abi.Application):
        """
        Callable when joining an existing game. Checks that the game is an actual valid game (created 
        using the platform) and if so, saves a reference of it in the local state of the caller, together with
        its type.
        challenger: the player who we are playing against
        txn: transaction in which the user opts into the game
        app: reference to txn.application_id
        """
        return Seq(
            Assert(
                app.application_id() == txn.get().application_id(),
                check_fees(fee_amounts, self.puntazzi.get(),  App.localGetEx(txn.get().sender(), txn.get().application_id(), Bytes("fee_amount")).outputReducer(lambda value, _: value)),
                txn.get().application_id() == self.current_game[challenger.address()].get(),
                txn.get().on_completion() == OnComplete.OptIn,
            ),
            self.current_game.set(self.current_game[challenger.address()].get()),
            self.game_time.set(self.game_time[challenger.address()].get()),
            self.game_type.set(self.game_type[challenger.address()].get()),
        )
        
    @external
    def win_game(self, challenger: abi.Account, app: abi.Application):
        """
        Callable when you have won a game. Checks that you have really won the game. If so, it awards points
        based on how much was staked.
        challenger: the player who we are playing against
        app: reference to txn.application_id
        """
        return Seq(
            Assert(
                app.application_id() == self.current_game.get(),
                challenger.address() != Txn.sender(),
                self.current_game[challenger.address()].get() == self.current_game.get(),
                App.globalGetEx(self.current_game.get(), Bytes("winner")).outputReducer(lambda value, _: value) == Txn.sender(),
            ),
            self.puntazzi.set(self.puntazzi.get() + App.globalGetEx(self.current_game.get(), Bytes("stake")).outputReducer(lambda value, _: value) / Int(100)),
            self.current_game.set(Int(0)),
            self.current_game[challenger.address()].set(Int(0)),
        )
