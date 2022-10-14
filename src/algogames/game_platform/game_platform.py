from typing import Final
from pyteal import *
from beaker import *
from morra.morra import approval_binary as morra_ab, clear_binary as morra_cb

class GamePlatform(Application):
    berluscoin: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)

    username: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    current_game: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    game_time: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    game_type: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    puntazzi: Final[AccountStateValue] = AccountStateValue(TealType.uint64)

    @create
    def create(self):
        return Seq()
        
    @external
    def init(self, txn: abi.PaymentTransaction):
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
                TxnField.config_asset_name: Bytes("Berluscoin"),
                TxnField.config_asset_unit_name: Bytes("FRZIT"),
            }),
            InnerTxnBuilder.Submit(),
            
            self.berluscoin.set(InnerTxn.created_asset_id()),            
        )
        
    @external
    def swap(self, txn: abi.PaymentTransaction, asset: abi.Asset):
        return Seq(
            Assert(
                txn.get().receiver() == Global.current_application_address(),
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_amount: txn.get().amount(),
                TxnField.xfer_asset: self.berluscoin.get(),
                TxnField.asset_receiver: txn.get().sender(),
            }),
            InnerTxnBuilder.Submit()
        )
        
    @opt_in
    def opt_in(self, username: abi.String):
        return Seq(
            self.username.set(username.get())
        )
        
    @external
    def new_game(self, txn: abi.ApplicationCallTransaction):
        return Seq(
            Assert(
                txn.get().approval_program() == Bytes(morra_ab),
                txn.get().clear_state_program() == Bytes(morra_cb),
            ),
            self.current_game.set(GeneratedID(txn.index())),
            self.game_time.set(Global.latest_timestamp()),
            self.game_type.set(Int(0))
        )

    @external
    def join_game(self, challenger: abi.Account, txn: abi.ApplicationCallTransaction):
        return Seq(
            Assert(
                txn.get().application_id() == self.current_game[challenger.address()].get(),
                txn.get().on_completion() == OnComplete.OptIn,
            ),
            self.current_game.set(self.current_game[challenger.address()].get()),
            self.game_time.set(self.game_time[challenger.address()].get()),
            self.game_type.set(self.game_type[challenger.address()].get()),
        )
        
    @external
    def win_game(self, challenger: abi.Account, app: abi.Application):
        return Seq(
            Assert(
                challenger.address() != Txn.sender(),
                self.current_game[challenger.address()].get() == self.current_game.get(),
                App.globalGetEx(self.current_game.get(), Bytes("winner")).outputReducer(lambda value, _: value) == Txn.sender(),
            ),
            self.current_game.set(Int(0)),
            self.current_game[challenger.address()].set(Int(0)),
            self.puntazzi.set(self.puntazzi.get() + Int(1)),
        )
