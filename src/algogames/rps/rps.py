from typing import Final
from pyteal import *
from beaker import *
from algorand import client

action_timeout = 10

INIT = Int(0)
POOR = Int(1)
WAIT = Int(2)
COMMIT = Int(3)
REVEAL = Int(4)
FINISH = Int(5)

WINNING_SCORE = Int(2)
TIMEOUT = Int(action_timeout)

ROCK = Bytes('rock')
PAPER = Bytes('paper')
SCISSORS = Bytes('scissors')

class RPS(Application):
    stake: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    challenger: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    asset: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    fee_holder: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    
    state: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    action_count: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    
    action_timer: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)

    winner: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes) 

    player_state: Final[AccountStateValue] = AccountStateValue(TealType.uint64) 
    player_commit: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    player_hand: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    player_score: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    
    @create
    def create(self, asset: abi.Asset, fee_holder: abi.Account):
        return Seq(
            self.state.set(INIT),
            self.action_count.set(Int(0)),
            self.asset.set(asset.asset_id()),
            self.fee_holder.set(fee_holder.address()),
        )
        
    @external
    def init(self, txn: abi.PaymentTransaction, asset: abi.Asset):
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == INIT,
                txn.get().amount() == Int(210000),
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_amount: Int(0),
            }),
            InnerTxnBuilder.Submit(),
            
            self.state.set(POOR),
        )
        
    @internal
    def define_stake(self, txn: abi.AssetTransferTransaction):
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == POOR,
                
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
            ),
            
            self.stake.set(txn.get().asset_amount()),

            self.state.set(WAIT),
        )        
        
    @internal
    def join(self, txn: abi.AssetTransferTransaction):
        return Seq(
            Assert(
                self.state.get() == WAIT,
                
                txn.get().sender() != Global.creator_address(),
                
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
                txn.get().asset_amount() == self.stake.get(),
            ),
            
            self.challenger.set(Txn.sender()),  
            self.action_timer.set(Global.round()), 
            self.state.set(COMMIT)   
        )

    @internal
    def cancel(self):
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == WAIT,
            ),
            self.empty_account_caller(Int(0))
        )

    @external
    def commit(self, commit: abi.DynamicBytes):
        return Seq(
            Assert(
                self.player_state.get() != COMMIT,
                App.optedIn(Txn.sender(), Global.current_application_id()),
                self.state.get() == COMMIT,
            ),
            
            self.player_commit.set(commit.get()),
            self.player_state.set(COMMIT),

            If(self.action_count.get() == Int(1)).Then(Seq(
                self.state.set(REVEAL),
                self.action_count.set(Int(0)),
                self.action_timer.set(Global.round())
            )).Else( 
                self.action_count.set(Int(1)),            
            )
        )
    
    @external
    def reveal(self, reveal: abi.String, other: abi.Account):
        return Seq(
            Assert(
                App.optedIn(Txn.sender(), Global.current_application_id()),
                self.state.get() == REVEAL,
                self.player_state != REVEAL,
                self.player_commit.get() == Sha256(reveal.get()),
                If(Txn.sender() == Global.creator_address()).Then(other.address() == self.challenger.get()).Else(other.address() == Global.creator_address())
            ),
            
            self.player_state.set(REVEAL),
            
            self.player_hand.set(JsonRef.as_string(reveal.get(), Bytes("hand"))),
            Assert(Or(
                    self.player_hand.get() == ROCK,
                    self.player_hand.get() == PAPER,
                    self.player_hand.get() == SCISSORS
                )
            ),
            
            If(self.action_count.get() == Int(1)).Then(Seq(
                self.action_count.set(Int(0)),

                If(Or(  
                        And(self.player_hand.get() == ROCK,
                            self.player_hand[other.address()].get() == SCISSORS),
                        And(self.player_hand.get() == SCISSORS,
                            self.player_hand[other.address()].get() == PAPER),
                        And(self.player_hand.get() == PAPER,
                            self.player_hand[other.address()].get() == ROCK))).Then(
                    self.player_score.set(self.player_score.get() + Int(1))
                ).ElseIf(Or(
                        And(self.player_hand.get() == SCISSORS,
                            self.player_hand[other.address()].get() == ROCK),
                        And(self.player_hand.get() == PAPER,
                            self.player_hand[other.address()].get() == SCISSORS),
                        And(self.player_hand.get() == ROCK,
                            self.player_hand[other.address()].get() == PAPER))).Then(
                    self.player_score[other.address()].set(self.player_score[other.address()].get() + Int(1))
                ),
                
                If(self.player_score.get() >= WINNING_SCORE).Then(Seq(
                    self.state.set(FINISH),
                    self.winner.set(Txn.sender()),
                )).ElseIf(self.player_score[other.address()].get() >= WINNING_SCORE).Then(Seq(
                    self.state.set(FINISH),
                    self.winner.set(other.address()),
                )).Else(
                    self.state.set(COMMIT),
                    self.action_timer.set(Global.round())
                )
            )).Else(
                self.action_count.set(Int(1)),            
            )
        )
        
    @internal
    def finish(self):
        return Seq(
            Assert(
                self.winner.get() == Txn.sender()
            ),
            self.empty_account_caller(Int(1))
        )

    @external
    def forfeit(self):
        return Seq(
            Assert(Or(
                And(
                    self.state.get() == COMMIT,
                    self.action_timer.get() + TIMEOUT <= Global.round(),
                    self.player_state.get() == COMMIT),
                And(
                    self.state.get() == REVEAL,
                    self.action_timer.get() + TIMEOUT <= Global.round(),
                    self.player_state.get() == REVEAL)
            )),
            self.state.set(FINISH),
            self.winner.set(Txn.sender())
        )
        
    @internal(TealType.none)
    def empty_account_caller(self, fee):
        return Seq(
            InnerTxnBuilder.Begin(),
            If(fee).Then(Seq(
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: self.asset.get(),
                    TxnField.asset_amount: self.stake.get()/Int(100//2),
                    TxnField.asset_receiver: self.fee_holder.get(),
                }),
                InnerTxnBuilder.Next(),
            )),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_close_to: Txn.sender(),
            }),
            InnerTxnBuilder.Next(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.Payment,
                TxnField.close_remainder_to: Global.creator_address(),
            }),
            InnerTxnBuilder.Submit(),
        )

        
    @opt_in
    def opt_in(self, txn: abi.AssetTransferTransaction):
        return If(self.state.get() == POOR).Then(
                self.define_stake(txn)
            ).ElseIf(self.state.get() == WAIT).Then(
                self.join(txn)
            ).Else(
                Err()
            )
    
    @delete
    def delete(self, asset: abi.Asset, creator: abi.Account, fee_holder: abi.Account):
        return If(self.state.get() == FINISH).Then(
                self.finish()
            ).ElseIf(self.state.get() == WAIT).Then(
                self.cancel()
            ).Else(
                Err()
            )
        
from base64 import b64decode
approval_binary = b64decode(client.compile(RPS().approval_program)["result"])
clear_binary = b64decode(client.compile(RPS().clear_program)["result"])