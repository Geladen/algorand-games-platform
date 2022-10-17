# Group 2
[Cuncu Emanuele](https://github.com/Geladen)

[Pettinau Roberto](https://github.com/petitnau)

[Pusceddu Daniele](https://github.com/danielepusceddu)

# algorand-games-platform
Project for International School on Algorand Smart Contracts.

# Usage

1. Clone the repository
2. Install all the required python modules
```
pip install -r requirements.txt
```
3. Interact with the platform:
```
python src/algogames/main.py [id player]
```

4. To run tests, it is also possible to run
```
bash test.sh
```

# Goal of the Project

This project aims to bring a games / gambling platform to the blockchain where games are also on chain. Players will be able to bet Algorand Skull Coin 'SKULL' (platform ASAs) to play against other players in 1-on-1 matches. The platform in this first version contains 3 games: Morra, Rock-Paper-Scissors, Blackjack. The tokens of the platform can be bought and sold with an exchange rate of 1 Algo = 1000000 SKULL. From a business point of view, a fee system has been implemented on winnings, which can be reduced based on the amount of SKULLs played all time. Smart contracts that shape the platform and games cannot be updated in a way that ensures the safety of users' funds within contracts.

Roadmap:

  1. Implement the Morra game (First goal)
  2. Build the decentralized platform
  3. Implement platform-game interaction
  4. Implement a second game (Rock-Paper-Scissors)
  6. Develop a loyalty system based on the earned points
  7. Implement a second game (BlackJack)

# Smart Contract Specifications

## Game Platform

The owner of the platform creates the smart contract by deciding the address of the fee_holder to whom the fees that players will pay on wins will go. The platform creates an internal asset the Algorand Skull Coin with the maximum possible supply, and manages the basic functionality of exchanging Algos and SKULL with a ratio of 1 Algo = 1000000 SKULL. Furthermore, through the platform it is possible to create new games / participate in pre-established games. Based on the number and quantity of SKULLs won, players can get points called puntazzi, which through a step system allow you to obtain a reduction on the fees to be paid in case of victory in the games.

The contract interacts with n actors: the players

To start using the platform the only requirement is that the player has enough algo to buy SKULLs.

`create(fee_holder)` This function is intended to create the contract. The creator of the platform specifies the address in which to deposit all earnings from fees

`init(txn)` This function can only be called by the creator of the contract and is intended to initialize the platform. The creator must send a transaction to pay the minimum balance of the contract account. This operation also creates the new SKULL asset.

`buy(txn, asset)` Players can call this method to buy a quantity of SKULLs correspondent to the amount of ALGOs sent

`sell(txn)` Players can call this method to sell some SKULLs.

`opt_in(username)` This function can be called by any user to opt-in to the platform, with a username it will be saved in the local state of the platform

`new_game(game, txn, app)` This function allows the user to create a new match and register it in the platform, to check that the game is valid it verifies that the bytes of the approval and of the clear program are correct, together with the parameters that the contract is using.

`join_game(challenger, txn, app)` This feature allows a player to participate in an existing game as a challenger.

`win_game(challenger, app)` This function can only be called by the winner of a game, the function checks that the player is actually the winner of a valid game, if so, it increases the player's points according to the formula: **staked SKULLs / 100** saving them in the local state of the application 


## Morra and Rock-Paper-Scissors

The two contracts are extremely similar, so they will be explained together highlighting the differences.

The owner of the match creates the smart contract and decides the amount of SKULLs to bet. From now on, any other user can join the game until a challenger is found. The challenger will have to deposit the amount of SKULL decided by the creator. Now, each player has to choose a number from 0 to 5 which will represent the amount of fingers he decided to pick and a second number from the interval between 0 and 10 as his guess. Then each platyer have to send to the contract the digest obtained from the SHA256 hash function. The next phase is to reveal the players' plays, the players send their decisions as plain text on which the contract recalculates the digest of SHA256 to verify their correctness. Once the plays have been received, the contract will recognize the winning player and award him a point. The player who reaches 2 points first wins.

The two smart contracts were developed as finite state automata
The contract interacts with 2 actors: The Owner and the Challenger

Requirements: both players must have enough SKULLs to start the game

Functions:

`create(asset, fee_holder)` The match organizer must call this function to create the smart contract and set the asset to be used in the match and the account that will receive the payout fees.

`init(txn, asset)` Must be called by contract creator to initialize the application, must receive a transaction in which contract fees are paid

`opt_in(txn, fee_amount)` This function must be called by both players to opt in to the contract, and based on the contract status it routs between the internal functions: join and define_stake

`define_stake(txn, fee_amount)` This function can only be called by the creator of the contract and is intended to define the stake of the game. The transaction specifies the stake amount and pays for it. In addition, the fee_amount that he must pay in case of a win is saved in the player's local state.

`join(txn, fee_amount)` It can be called by any player other than the creator of the contract and is intended to enter the game as a challenger. To join the game it will be necessary to send the stake with a transaction and specify the fee_amount to be paid in case of a win

`commit(commit)` This function must be called by both players to indicate their moves, these are passed in the commit parameter in the form of digest of SHA256 of a JSON of the following type:
In the morra contract the JSON has this format: `{"guess": guess, "hand": hand, "nonce": nonce}`,
In the Rock-Paper-Scissors contract the JSON has this format: `{"hand": hand, "nonce": nonce}`.
The random nonce has the purpose of guaranteeing the secrecy of the commit avoiding brute force attacks.

`reveal(reveal, other)` This function must be called by both players to reveal their move. The player when calling the function must provide as a parameter a reveal that corresponds to the JSON on which he has calculated the hash function SHA256 sent previously. The function will check that the hash of the JSON is the same as the one provided during the commit phase, if so it will also check that it respects the rules of the game, i.e. that 0 <= hand <= 5 and 0 <= guess <= 10 in the case of morra, and hand == "rock", "paper", or "scissors" in the case of rps. 
When the function is called for the second time it awards a point to the winner in the contract status and in case he has reached the two points it marks him as the winner of the match.

`forfeit()` It can be called by both players, as a guarantee in case the opponent does not want to reveal their choice or stops playing. The function checks that 10 rounds have passed since the last state change and if so if the opponent has not interacted for the last 10 rounds then the caller of the function is set as the winner in the contract state

`delete(asset, creator, fee_holder)` This function must be called by both players to delete the contract, and based on the contract status it routs between the internal functions: cancel and finish

`cancel()` It can only be called by the creator of the contract and is intended to cancel the game in case you are unable to find a challenger.

`finish()` It can only be called by the winner, and has the aim of sending the SKULLs to the winner from whom a percentage of the fee is subtracted and sent to the address of the fee_holder

## Blackjack

The protocol for the blackjack game can be summarized as follows:

1. The contract initializes an array of cards (implemented as a bytestring of 52 0s)
2. Every time that the player wants someone to draw a card, they must provide a random number
3. The bank provides a deterministic signature of this random number
4. The contract calculates the signature modulo the number of cards remaining `i`, and picks the `i`-th non picked card from the array of cards
5. After picking a card in position `i`, the `i`-th byte in the array of cards is set to 1 if the card was picked by the player, and 2 if it was picked by the bank.

Note that the first two cards are given to the user, and the third card is given to the bank. At this point the player can pick cards until he reaches 21 or busts, and after that, the cards are given to the bank. Note that the user has no way to predict what card will be chosen (as they do not know the private key of the bank), and the bank has no way to influence what card will be chosen, as they must provide a (deterministic) signature of the data provided by the user. 


`create(asset, bank, fee_holder)` This function can only be called by the game creator to create the contract. Requires to specify the game asset, the fee_hoolder to which the fees of any winnings will go and the address of the bank which will be saved in the contract status

`init()` Must be called by the contract creator to initialize the application, must receive a transaction in which the contract creation fees are paid

`distribute_req(req)` Is called by the player to continue the initial distribution of the cards. The first two cards will be given to the user; the third one will be given to the bank. The user supplies a request of the form of a JSON with the format `{"nonce": nonce, "nonce_p": nonce_p, "app": app}`, where `nonce` is an increasing number, `app` is the id of the application, and `nonce_p` is a random number chosen by the player.

`hit_act(sig)` Is called by the bank to give a card to the player. Can be called only after a hit_req. To be called, the bank must sign the request made in the `hit_req` function. This signature will be used to decide on what car will be picked. 

`hit_req(req)` Is called by the player to draw a card. The user supplies a request of the form of a JSON with the format `{"nonce": nonce, "nonce_p": nonce_p, "app": app}`, where `nonce` is an increasing number, `app` is the id of the application, and `nonce_p` is a random number chosen by the player.

`hit_act(sig)` Is called by the bank to give a card to the player. Can be called only after a hit_req. To be called, the bank must sign the request made in the `hit_req` function. This signature will be used to decide on what car will be picked.

`stand_req(req)` Is called by the player to let the bank draw a card. The user supplies a request of the form of a JSON with the format `{"nonce": nonce, "nonce_p": nonce_p, "app": app}`, where `nonce` is an increasing number, `app` is the id of the application, and `nonce_p` is a random number chosen by the player.

`stand_act(sig)` Is called by the bank to give a card to himself. Can be called only after a stand_req. To be called, the bank must sign the request made in the `stand_req` function. This signature will be used to decide on what car will be picked. 

`forfeit()` It can be called by both the player and the bank, as a guarantee in case the opponent does not want to reveal their choice or stops playing. The function checks that 10 rounds have passed since the last state change and if so if the opponent has not interacted for the last 10 rounds then the caller of the function is set as the winner in the contract state

`opt_in(txn, fee_amount)` This function must be called by the player and the bank to opt in to the contract. Based on the state of the contract it routes between the internal functions: join_server and define_stake

`delete(asset, creator, fee_holder)` This function must be called by the player or the bank to delete the contract. Based on the state of the contract it routes between the internal functions: cancel, finish and give_funds_back


# State of the Art

We have not found many projects similar to ours in the Algorand ecosystem, we report below the main platforms / implementations:
Algo-Casino is a platform that brings classic casino games of poker, blackjack and others to the algorithm ecosystem. To play it is necessary to have the CHIP asset. In addition to the classic games it also offers a DEFI service.

Regarding implementations similar to ours, this [article](https://developer.algorand.org/solutions/morra-game-using-reach/) explains an implementation of morra. As in our case the game is implemented for 2 players in 1v1 games. The main difference is the programming language with which it was developed: Reach. Using pyteal and Beaker we believe that development has been facilitated by familiarity with python and the result is more understandable code with the same functionality.


# Technical Challenges

In our development of this project we encountered numerous problems with the Beaker framework. 

The game platform, in multiple cases, requires the user to pass an application call when calling a method of the contract. This application call itself, often takes as parameters additional transactions. To our knowledge, the Beaker framework does not allow the use of its ApplicationClient methods to construct application calls that must be passed as parameters to other application calls. We therefore extended the beaker library (although in a hacky fashion to not slow down development) to support these use cases, adding a `nosend` version of the corresponding `create`, `call`, `opt-in` and `delete` calls, together with a `finalize` function to submit the created application calls.

Furthermore, we found out (by trial error, as the documentation is still very partial) that it is not possible to have more than one `opt_in`/`delete` method per contract. Although this seems like a design decision, we found this limit overly restrictive, and we think that it has impacted the tidiness of our implementation. 

For what concerns the contract themselves, most of the challenge in this project was making the game platform and the games communicate smoothly. To make our implementation cleaner, an obvious next step in our implementation would consist in creating a base contract for all the games that implements the interface needed to enable that communication, as currently a lot of code is replicated between contracts.

Lastly, we would've liked to use the new opcodes `block` and `vrf_verify` for the implementation of the blackjack contract, but we quickly found ourselves lost, although we're sure that if we had dedicated more time to it, we would've figured it out.
