from typing import Final
from pyteal import *
from beaker import *
from morra.morra import approval_binary as morra_ab, clear_binary as morra_cb

class GamePlatform(Application):
    berluscoin: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)

    current_game: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
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
    def opt_in(self):
        return Seq()
        
    @external
    def new_game(self, txn: abi.ApplicationCallTransaction):
        return Seq(
            Assert(
                txn.get().approval_program() == Bytes(morra_ab),
                txn.get().clear_state_program() == Bytes(morra_cb),
            ),
            self.current_game.set(GeneratedID(txn.index()))
        )

    @external
    def join_game(self, challenger: abi.Account, txn: abi.ApplicationCallTransaction):
        return Seq(
            Assert(
                txn.get().application_id() == self.current_game[challenger.address()].get(),
                txn.get().on_completion() == OnComplete.OptIn,
            ),
            self.current_game.set(self.current_game[challenger.address()].get()),
        )
        
    @external
    def win_game(self, app: abi.Application):
        return Seq(
            Assert(
                App.globalGetEx(self.current_game.get(), Bytes("winner")).outputReducer(lambda value, _: value) == Txn.sender(),
            ),
            self.current_game.set(Int(0)),
            self.puntazzi.set(self.puntazzi.get() + Int(1)),
        )
