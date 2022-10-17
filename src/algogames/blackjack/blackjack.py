from typing import Final
from pyteal import *
from beaker import *
from pytealext import Max, Min
from algorand import client
from config import fee_holder, skull_id

action_timeout = 10

state_init = 0
state_poor = 1
state_wait = 2
state_distribute = 3
state_distribute_act = 4
state_player = 5
state_hit_act = 6
state_bank = 7
state_stand_act = 8
state_finish = 9
state_push = 10

"""
States
"""
# Configuring
# Contract created
INIT = Int(state_init) 
# Contract address initialized without stake
POOR = Int(state_poor)
# Creator decided the stake and is waiting for the bank
WAIT = Int(state_wait)

# Play
# Phase in which the first 3 cards are given (2 to the player, 1 to the bank)
DISTRIBUTE = Int(state_distribute)
DISTRIBUTE_ACT = Int(state_distribute_act)
# State in which the player can decide if to hit or to stand
PLAYER = Int(state_player)
# State in which the bank must reveal the card that the player will draw
HIT_ACT = Int(state_hit_act)
# State in which the player can only stand
BANK = Int(state_bank)
# State in which the bank must reveal the card that they will draw
STAND_ACT = Int(state_stand_act)

# End of the game
# Someone won (specified by winner)
FINISH = Int(state_finish)
# Draw
PUSH = Int(state_push)

"""
Other params
"""
WINNING_SCORE = Int(2)
TIMEOUT = Int(action_timeout)

class Blackjack(Application):
    asset: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    player: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    fee_holder: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    bank: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    stake: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    
    nonce: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    request: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    
    cards: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    last_card: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    cards_left: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    
    player_cards: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    player_min_total: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    player_max_total: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    bank_cards: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    bank_min_total: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    bank_max_total: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
        
    state: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    action_timer: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)

    winner: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes) 

    fee_amount: Final[AccountStateValue] = AccountStateValue(TealType.uint64) 

    @internal(TealType.none)
    def win_player(self):
        """
        Makes the player the winner of the game
        """
        return Seq(
            self.state.set(FINISH),
            self.winner.set(Global.creator_address())
        )
    @internal(TealType.none)
    def win_bank(self):        
        """
        Makes the bank the winner of the game
        """
        return Seq(
            self.state.set(FINISH),
            self.winner.set(self.bank.get())
        )
    @internal(TealType.none)
    def push(self):
        """
        Makes the game a draw
        """
        return Seq(
            self.state.set(PUSH),
        )
    @internal(TealType.uint64)
    def pop_card(self, pos, pop_id):
        """
        Remove a card from the deck and returns its ID
        pos: index of the card to be popped in the remaining card array
        pop_id: id that encodes why the card has been popped (0 unpopped, 1 player, 2 bank)
        """
        i = ScratchVar(TealType.uint64)
        j = ScratchVar(TealType.uint64)
        return Seq(
            For(Seq(i.store(Int(0)), j.store(Int(0))), j.load() <= pos, i.store(i.load() + Int(1))).Do(Seq(
                If(GetByte(self.cards.get(), i.load()) == Int(0)).Then(
                    j.store(j.load() + Int(1))
                )
            )),
            i.store(i.load() - Int(1)),
            self.cards.set(SetByte(self.cards.get(), i.load(), pop_id)),
            self.cards_left.set(self.cards_left.get() - Int(1)),
            self.last_card.set(i.load()),
            
            i.load(),
        )
    @internal(TealType.uint64)
    def sig_to_card_pos(self, sig: abi.DynamicBytes):
        """
        Get the card position corresponding to a signature
        sig: signature by the bank of a request
        """
        return Seq(
            Btoi(BytesMod(sig.get(), Extract(Itob(self.cards_left.get()), Int(7), Int(1)))),
        )
    @internal(TealType.uint64)
    def card_value(self, id):
        """
        Get a card value from its ID
        id: ID of the card of which the value will be returned
        """
        return Seq(
            Min(id % Int(13) + Int(1), Int(10))
        )
    @internal(TealType.none)
    def give_card_to_bank(self, pos):
        """
        Give a card to the bank
        pos: index of the card to be popped in the remaining card array
        """
        card = ScratchVar(TealType.uint64)
        min_value = ScratchVar(TealType.uint64)
        max_value = ScratchVar(TealType.uint64)
        return Seq(
            card.store(self.pop_card(pos, Int(2))),
            self.bank_cards.set(self.bank_cards.get() + Int(1)),
            min_value.store(self.card_value(card.load())),
            max_value.store(If(min_value.load() == Int(1)).Then(Int(11)).Else(min_value.load())),
            self.bank_min_total.set(self.bank_min_total.get() + min_value.load()),
            self.bank_max_total.set(self.bank_max_total.get() + max_value.load()),
        )
    @internal(TealType.none)
    def give_card_to_player(self, pos):
        """
        Give a card to the player
        pos: index of the card to be popped in the remaining card array
        """
        card = ScratchVar(TealType.uint64)
        min_value = ScratchVar(TealType.uint64)
        max_value = ScratchVar(TealType.uint64)
        return Seq(
            card.store(self.pop_card(pos, Int(1))),
            self.player_cards.set(self.player_cards.get() + Int(1)),
            min_value.store(self.card_value(card.load())),
            max_value.store(If(min_value.load() == Int(1)).Then(Int(11)).Else(min_value.load())),
            self.player_min_total.set(self.player_min_total.get() + min_value.load()),
            self.player_max_total.set(self.player_max_total.get() + max_value.load()),
        )
    @internal(TealType.none)
    def give_funds_back(self):
        """
        Give the funds back to the bank and the player
        """
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_amount: self.stake.get(),
                TxnField.asset_receiver: Global.creator_address(),
            }),
            InnerTxnBuilder.Next(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: self.asset.get(),
                TxnField.asset_close_to: self.bank.get(),
            }),
            InnerTxnBuilder.Next(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.Payment,
                TxnField.close_remainder_to: Global.creator_address(),
            }),
            InnerTxnBuilder.Submit(),
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

        
    @create
    def create(self, asset: abi.Asset, bank: abi.Account, fee_holder: abi.Account):
        """
        Callable to create the contract
        asset: asset that will be staked
        bank: address of the bank
        fee_holder: address that will receive the fees
        """
        return Seq(
            self.asset.set(asset.asset_id()),
            self.bank.set(bank.address()),
            self.fee_holder.set(fee_holder.address()),
            self.cards.set(Bytes(b"\x00"*52)),
            self.cards_left.set(Int(52)),
            self.nonce.set(Int(0)),
            
            self.state.set(INIT),
        )
    
    @external
    def init(self, txn: abi.PaymentTransaction, asset: abi.Asset):
        """
        Callable by the creator to initialize the application account
        txn: transaction that pays the minimum balance + fees of the contract
        asset: reference to self.asset (used to enable AssetTransfer InnerTxn)
        """
        return Seq(
            Assert(
                self.state.get() == INIT,
                Txn.sender() == Global.creator_address(),
                txn.get().amount() == Int(1000000),
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
        fee_amount: denominator of what will be paid as fee if the player wins
        """
        return Seq(
            Assert(
                self.state.get() == POOR,
                Txn.sender() == Global.creator_address(),
                
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
            self.give_funds_caller(Int(0)),
        )
        
    @internal
    def join_server(self, txn: abi.AssetTransferTransaction, fee_amount: abi.Uint64):
        """
        Callable by the bank to join the game
        txn: transaction that pays the stake
        fee_amount: denominator of what will be paid as fee if the bank wins
        """
        return Seq(
            Assert(
                self.state.get() == WAIT,
                
                txn.get().sender() == self.bank.get(),
                txn.get().xfer_asset() == self.asset.get(),
                txn.get().asset_receiver() == Global.current_application_address(),
                txn.get().asset_amount() == self.stake.get(),
            ),

            self.fee_amount.set(fee_amount.get()),

            self.state.set(DISTRIBUTE),
            self.action_timer.set(Global.round()), 
        )
        
    @external
    def distribute_req(self, request: abi.DynamicBytes):
        """
        Callable by the player to randomly choose a card to distribute in the initial phase.
        request: JSON containing a (`nonce` = self.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
        """
        return Seq(
            Assert(
                self.state.get() == DISTRIBUTE,
                
                Txn.sender() == Global.creator_address(),
                JsonRef.as_uint64(request.get(), Bytes("nonce")) == self.nonce.get(),
                JsonRef.as_uint64(request.get(), Bytes("app")) == Global.current_application_id(),
            ),
            
            self.request.set(request.get()),
            self.nonce.set(self.nonce.get() + Int(1)),

            self.state.set(DISTRIBUTE_ACT),
            self.action_timer.set(Global.round()),
        )
        
    @external
    def distribute_act(self, sig: abi.DynamicBytes):
        """
        Callable by the bank to specify what card will be distributed. The first two times 
        the  card will be given to the player, while the third time the card will be given
        to the bank. 
        sig: signature of self.request by self.bank
        """
        return Seq(
            OpUp(OpUpMode.OnCall).maximize_budget(Int(5000)),
            Assert(
                self.state.get() == DISTRIBUTE_ACT,
                Ed25519Verify(self.request.get(), sig.get(), self.bank.get()),
            ),
            
            If(self.player_cards.get() < Int(2)).Then(
                self.give_card_to_player(self.sig_to_card_pos(sig)),
            ).Else(
                self.give_card_to_bank(self.sig_to_card_pos(sig)),
            ),
            
            # If distribution finished and player has blackjack (player cannot hit)
            If(And(self.bank_cards.get() == Int(1), self.player_max_total.get() == Int(21))).Then(
                self.state.set(BANK),
            # If distribution finished and player does not have (player can hit)
            ).ElseIf(And(self.bank_cards.get() == Int(1), self.player_max_total.get() != Int(21))).Then(
                self.state.set(PLAYER),
            # If distribution has not finished (continue distributing)
            ).Else(
                self.state.set(DISTRIBUTE),
            ),
            
            self.action_timer.set(Global.round()),
        )
        
    @external
    def hit_req(self, request: abi.DynamicBytes):
        """
        Callable by the player to randomly choose a card to draw.
        request: JSON containing a (`nonce` = self.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
        """
        return Seq(
            Assert(
                self.state.get() == PLAYER,
                
                Txn.sender() == Global.creator_address(),
                JsonRef.as_uint64(request.get(), Bytes("nonce")) == self.nonce.get(),
                JsonRef.as_uint64(request.get(), Bytes("app")) == Global.current_application_id(),
            ),
            
            self.request.set(request.get()),
            self.nonce.set(self.nonce.get() + Int(1)),

            self.state.set(HIT_ACT),
            self.action_timer.set(Global.round()),
        )
    
    @external
    def hit_act(self, sig: abi.DynamicBytes):
        """
        Callable by the bank to specify what card will be drawn by the player.
        sig: signature of self.request by self.bank
        """
        return Seq(
            OpUp(OpUpMode.OnCall).maximize_budget(Int(5000)),
            Assert(
                self.state.get() == HIT_ACT,
                Ed25519Verify(self.request.get(), sig.get(), self.bank.get()),
            ),
            
            self.give_card_to_player(self.sig_to_card_pos(sig)),
            
            # If player busted and does not have aces worth 11 (bank wins)
            If(And(self.player_max_total.get() > Int(21), self.player_max_total.get() == self.player_min_total.get())).Then(
                self.state.set(FINISH),
                self.winner.set(self.bank.get()),
            # If player busted BUT has at least one ace worth 11 (make ace worth one)
            ).ElseIf(And(self.player_max_total.get() > Int(21), self.player_max_total.get() != self.player_min_total.get())).Then(
                self.state.set(PLAYER),
                self.player_max_total.set(self.player_max_total.get() - Int(10)),
            # If a player reached 21 (cannot hit again)
            ).ElseIf(self.player_max_total.get() == Int(21)).Then(
                self.state.set(BANK),
            # If a player is below 21 (can hit again)
            ).Else(
                self.state.set(PLAYER),
            ),
            
            self.action_timer.set(Global.round()),
        )
        
    @external
    def stand_req(self, request: abi.DynamicBytes):
        """
        Callable by the player to randomly choose a card to let the bank draw.
        request: JSON containing a (`nonce` = self.nonce), a (`app` = Global.current_application_id()) and a random `nonce_p`
        """
        return Seq(
            Assert(
                Or(
                    self.state.get() == PLAYER,
                    self.state.get() == BANK,
                ),
                
                Txn.sender() == Global.creator_address(),
                JsonRef.as_uint64(request.get(), Bytes("nonce")) == self.nonce.get(),
                JsonRef.as_uint64(request.get(), Bytes("app")) == Global.current_application_id(),
            ),
            
            self.request.set(request.get()),
            self.nonce.set(self.nonce.get() + Int(1)),
            
            self.state.set(STAND_ACT),
            self.action_timer.set(Global.round()),
        )
    
    @external
    def stand_act(self, sig: abi.DynamicBytes):
        """
        Callable by the bank to specify what card will be drawn by the bank.
        sig: signature of self.request by self.bank
        """
        return Seq(
            OpUp(OpUpMode.OnCall).maximize_budget(Int(5000)),
            Assert(
                self.state.get() == STAND_ACT,
                Ed25519Verify(self.request.get(), sig.get(), self.bank.get()),
            ),
            
            self.give_card_to_bank(self.sig_to_card_pos(sig)),
            
            # If bank busted and does not have aces worth 11 (player wins)
            If(And(self.bank_max_total.get() > Int(21), self.bank_max_total.get() == self.bank_min_total.get())).Then(Seq(
                self.state.set(FINISH),
                self.winner.set(Global.creator_address()),
            # If bank busted BUT has at least one ace worth 11 (make ace worth one)
            )).ElseIf(And(self.bank_max_total.get() > Int(21), self.bank_max_total.get() != self.bank_min_total.get())).Then(
                self.state.set(BANK),
                self.bank_max_total.set(self.bank_max_total.get() - Int(10))
            # If bank reached a hand worth at least 17 (game is over)
            ).ElseIf(self.bank_max_total.get() >= Int(17)).Then(
                # If bank's total is higher than player (bank wins)
                If(self.bank_max_total.get() > self.player_max_total.get()).Then(
                    self.win_bank(),
                # If bank's total is higher than player (player wins)
                ).ElseIf(self.bank_max_total.get() < self.player_max_total.get()).Then(
                    self.win_player(),
                # If bank's total is the same as player
                ).Else(
                    # If player has black jack (player wins)
                    If(And(self.player_max_total.get() == Int(21), self.player_cards.get() == Int(2), self.bank_cards.get() != Int(2))).Then(
                        self.win_player(),
                    # If bank has black jack (bank wins)
                    ).ElseIf(And(self.player_max_total.get() == Int(21), self.player_cards.get() != Int(2), self.bank_cards.get() == Int(2))).Then(
                        self.win_bank(),
                    # If neither has black jack (push/draw)
                    ).Else(
                        self.push(),
                    )
                )
            # If bank has not reached 17 yet (continue drawing cards)
            ).Else(
                self.state.set(BANK),
            ),
            
            self.action_timer.set(Global.round()),
        )
        
    @internal
    def finish(self):
        """
        Callable by the winner to get all the funds
        """
        return Seq(
            Assert(
                self.winner.get() == Txn.sender()
            ),
            
            If(self.winner.get() == self.bank.get()).Then(
                self.give_funds_caller(Int(0))
            ).Else(
                self.give_funds_caller(Int(1))
            )
        )

    @external
    def forfeit(self):
        """
        Callable by either the bank or the player if the other stops interacting.
        """
        return Seq(
            Assert(Or(
                And(
                    Or(
                        self.state.get() == PLAYER,
                        self.state.get() == BANK,
                    ), 
                    Txn.sender() == self.bank.get(),
                ),
                And(
                    Or(
                        self.state.get() == HIT_ACT,
                        self.state.get() == STAND_ACT,
                    ),
                    Txn.sender() == Global.creator_address(),
                ),
                self.action_timer.get() + TIMEOUT <= Global.round(),
            )),
            self.state.set(FINISH),
            self.winner.set(Txn.sender())
        )
        
    @opt_in
    def opt_in(self, txn: abi.AssetTransferTransaction, fee_amount: abi.Uint64):
        """
        Routes the opt-in methods (define_stake and join_server)
        txn: transaction that pays the stake
        fee_amount: denominator of what will be paid as fee if the joining player wins
        """
        return If(self.state.get() == POOR).Then(
                self.define_stake(txn, fee_amount)
            ).ElseIf(self.state.get() == WAIT).Then(
                self.join_server(txn, fee_amount)
            ).Else(
                Err()
            )
    @delete
    def delete(self, asset: abi.Asset, other: abi.Account, fee_holder: abi.Account):
        """
        Routes the finish, cancel and push methods
        creator: reference to opponent's address, if existing (used to enable InnerTxn)
        fee_holder: reference to self.fee_holder (used to enable InnerTxn)
        asset: reference to self.asset (used to enable InnerTxn)
        """
        return Seq(
            Assert(
                asset.asset_id() == self.asset.get(),
                If(Txn.sender() == Global.creator_address()).Then(other.address() == self.bank.get()).Else(other.address() == Global.creator_address()),
                fee_holder.address() == self.fee_holder.get(),
            ),
            If(self.state.get() == FINISH).Then(
                self.finish()
            ).ElseIf(self.state.get() == WAIT).Then(
                self.cancel()
            ).ElseIf(self.state.get() == PUSH).Then(
                self.give_funds_back()
            ).Else(
                Err()
            )
        )
        
from base64 import b64decode
approval_binary = b64decode(client.compile(Blackjack().approval_program)["result"])
clear_binary = b64decode(client.compile(Blackjack().clear_program)["result"])
