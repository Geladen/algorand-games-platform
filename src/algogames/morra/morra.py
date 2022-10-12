from typing import Final
from pyteal import *
from beaker import *
from algorand import client
# A player creates the contract and decides the stake
# A second player joins the match sending the stake

INIT = Int(0)
POOR = Int(1)
WAIT = Int(2)
COMMIT = Int(3)
REVEAL = Int(4)
FINISH = Int(5)

# COMMIT_DURATION = Int(15)
# REVEAL_DURATION = Int(15)
WINNING_SCORE = Int(2)
TIMEOUT = Int(10)

class SaMurra(Application):
    stake: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    challenger: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    asset: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    
    state: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    action_count: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    
    action_timer: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)

    winner: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes) 

    player_state: Final[AccountStateValue] = AccountStateValue(TealType.uint64) 
    player_commit: Final[AccountStateValue] = AccountStateValue(TealType.bytes)
    player_guess: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    player_hand: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    player_score: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    
    @create
    def create(self, asset: abi.Asset):
        return Seq(
            self.state.set(INIT),
            self.action_count.set(Int(0)),
            self.asset.set(asset.asset_id())
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
            self.empty_account(Global.creator_address())
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
        guessedSelf = ScratchVar(TealType.uint64)
        guessedOther = ScratchVar(TealType.uint64)
        return Seq(
            Assert(
                App.optedIn(Txn.sender(), Global.current_application_id()),
                self.state.get() == REVEAL,
                self.player_state != REVEAL,
                self.player_commit.get() == Sha256(reveal.get()),
                If(Txn.sender() == Global.creator_address()).Then(other.address() == self.challenger.get()).Else(other.address() == Global.creator_address())
            ),
            
            self.player_guess.set(JsonRef.as_uint64(reveal.get(), Bytes("guess"))),
            self.player_state.set(REVEAL),
            Assert(
                self.player_guess.get() >= Int(0),
                self.player_guess.get() <= Int(10),
            ),
            
            self.player_hand.set(JsonRef.as_uint64(reveal.get(), Bytes("hand"))),
            Assert(
                self.player_hand.get() >= Int(0),
                self.player_hand.get() <= Int(5),
            ),
            
            If(self.action_count.get() == Int(1)).Then(Seq(
                self.action_count.set(Int(0)),
                
                guessedSelf.store(self.player_guess.get() == self.player_hand.get() + self.player_hand[other.address()].get()),
                guessedOther.store(self.player_guess[other.address()].get() == self.player_hand.get() + self.player_hand[other.address()].get()),

                If(And(guessedSelf.load(), Not(guessedOther.load()))).Then(
                    self.player_score.set(self.player_score.get() + Int(1))
                ).ElseIf(And(Not(guessedSelf.load()), guessedOther.load())).Then(
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
                self.player_score.get() >= WINNING_SCORE
            ),
            self.empty_account(Txn.sender())
        )

    @internal
    def forfeit(self):
        return Seq(
            Assert(Or(
                And(
                    self.state.get() == COMMIT,
                    self.action_timer.get() + TIMEOUT > Global.round(),
                    self.player_state.get() == COMMIT),
                And(
                    self.state.get() == REVEAL,
                    self.action_timer.get() + TIMEOUT > Global.round(),
                    self.player_state.get() == REVEAL)
            )),
            self.empty_account(Txn.sender())
        )
        
    @internal
    def empty_account(self, to: abi.String):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_close_to: to.get(),
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
                Reject()
            )
    
    @delete
    def delete(self, asset: abi.Asset):
        return If(self.state.get() == FINISH).Then(
                self.finish()
            ).ElseIf(self.state.get() == COMMIT or self.state.get() == REVEAL).Then(
                self.forfeit()
            ).ElseIf(self.state.get() == WAIT).Then(
                self.cancel()
            ).Else(
                Reject()
            )
        
from base64 import b64decode
approval_binary = b64decode(client.compile(SaMurra().approval_program)["result"])
clear_binary = b64decode(client.compile(SaMurra().clear_program)["result"])
