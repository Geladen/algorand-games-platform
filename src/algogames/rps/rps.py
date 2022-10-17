from typing import Final
from pyteal import *
from beaker import *
from algorand import client

action_timeout = 10

state_init = 0
state_poor = 1
state_wait = 2
state_commit = 3
state_reveal = 4
state_finish = 5

INIT = Int(state_init)
POOR = Int(state_poor)
WAIT = Int(state_wait)
COMMIT = Int(state_commit)
REVEAL = Int(state_reveal)
FINISH = Int(state_finish)

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
    fee_amount: Final[AccountStateValue] = AccountStateValue(TealType.uint64)
    
    @create
    def create(self, asset: abi.Asset, fee_holder: abi.Account):
        """
        Callable to create the contract
        asset: asset that will be staked
        fee_holder: address that will receive the fees
        """
        return Seq(
            self.state.set(INIT),
            self.action_count.set(Int(0)),
            self.asset.set(asset.asset_id()),
            self.fee_holder.set(fee_holder.address())
        )
        
    @external
    def init(self, txn: abi.PaymentTransaction, asset: abi.Asset):
        """
        Callable by the creator to initialize the application account
        txn: transaction that pays the minimum balance + fees of the contract
        asset: reference to self.asset (used to enable InnerTxn)
        """
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == INIT,
                txn.get().amount() == Int(210000),
                asset.asset_id() == self.asset.get(),
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
    def define_stake(self, txn: abi.AssetTransferTransaction, fee_amount: abi.Uint64):
        """
        Callable by the creator to define the stake of the game
        txn: transaction that pays (and specifies) the stake
        fee_amount: denominator of what will be paid as fee if the creator wins
        """
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == POOR,
                
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
            ),
            
            self.stake.set(txn.get().asset_amount()),
            self.fee_amount.set(fee_amount.get()),

            self.state.set(WAIT),
        )        
        
    @internal
    def cancel(self):
        """
        Callable by the creator if the bank failed to join, to cancel the game
        """
        return Seq(
            Assert(
                Txn.sender() == Global.creator_address(),
                self.state.get() == WAIT,
            ),
            self.give_funds_caller(Int(0))
        )
        
    @internal
    def join(self, txn: abi.AssetTransferTransaction, fee_amount: abi.Uint64):
        """
        Callable by a second player to join the game
        txn: transaction that pays the stake
        fee_amount: denominator of what will be paid as fee if the joining player wins
        """
        return Seq(
            Assert(
                self.state.get() == WAIT,
                
                txn.get().sender() != Global.creator_address(),
                
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
                txn.get().asset_amount() == self.stake.get()
            ),
            
            self.challenger.set(Txn.sender()),  
            self.action_timer.set(Global.round()), 
            self.fee_amount.set(fee_amount.get()),
            self.state.set(COMMIT)   
        )

    @external
    def commit(self, commit: abi.DynamicBytes):
        """
        Callable by each player to commit their move.
        commit: sha256 hash of a JSON containing a `hand` ("rock", "paper", "scissors") and a random `nonce`.
        """
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
        """
        Callable by each player to reveal their move.
        """
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
        """
        Callable by the winner to get the money.
        """
        return Seq(
            Assert(
                self.winner.get() == Txn.sender()
            ),
            self.give_funds_caller(Int(1))
        )

    @external
    def forfeit(self):
        """
        Callable by either player when the other one stops interacting.
        """
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
    def give_funds_caller(self, pay_fee):
        """
        Give all the funds to the caller 
        pay_fee: specifies if a part of the funds will be paid as fee
        """
        return Seq(
            InnerTxnBuilder.Begin(),
            If(pay_fee).Then(Seq(
                InnerTxnBuilder.SetFields({
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: self.asset.get(),
                    TxnField.asset_amount: self.stake.get() / self.fee_amount.get(),
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
    def opt_in(self, txn: abi.AssetTransferTransaction, fee_amount: abi.Uint64):
        """
        Routes the opt-in methods (define_stake and join)
        txn: transaction that pays the stake
        fee_amount: denominator of what will be paid as fee if the joining player wins
        """
        return If(self.state.get() == POOR).Then(
                self.define_stake(txn, fee_amount)
            ).ElseIf(self.state.get() == WAIT).Then(
                self.join(txn, fee_amount)
            ).Else(
                Err()
            )
    
    @delete
    def delete(self, asset: abi.Asset, creator: abi.Account, fee_holder: abi.Account):
        """
        Routes the finish and cancel methods
        creator: reference to Global.creator_address() (used to enable InnerTxn)
        fee_holder: reference to self.fee_holder (used to enable InnerTxn)
        asset: reference to self.asset (used to enable InnerTxn)
        """
        return Seq(
            Assert(
                asset.asset_id() == self.asset.get(),
                creator.address() == Global.creator_address(),
                fee_holder.address() == self.fee_holder.get(),
            ),
            If(self.state.get() == FINISH).Then(
                self.finish()
            ).ElseIf(self.state.get() == WAIT).Then(
                self.cancel()
            ).Else(
                Err()
            )
        )
        
from base64 import b64decode
approval_binary = b64decode(client.compile(RPS().approval_program)["result"])
clear_binary = b64decode(client.compile(RPS().clear_program)["result"])
