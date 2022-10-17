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
python main.py [id player]
```

To run tests, it is also possible to run
```
bash test.sh
```

# Goal of the Project

This project aims to bring a gaming / gambling platform to the blockchain in order to make it decentralized. Players will be able to bet platform tokens to play against other players in 1 vs 1 matches. The first available game will be Morra. The tokens of the platform will also have the usefulness of acting as loyalty points to increase game winnings or receive game badges.

Roadmap:

  1. Implement the Morra game (First goal)
  2. Build the decentralized platform
  3. Develop a loyalty system based on the platform's tokens
  4. Add more games ()

# Smart Contract Specifications
Requirements, Use cases, Functions ...

Morra:
The owner of the match creates the smart contract and decides the amount of SKULLs to bet. From now on, any other user can join the game until a challenger is found. The challenger will have to deposit the amount of SKULL decided by the creator. Now each player must make his own play (the number of fingers [0-5] and their prediction on the total [0-10]), sending it to the contract in the form of a digest of the SHA256 hash function calculated on his play. The next phase is to reveal the players' plays, the players send their decisions as plain text on which the contract recalculates the digest of SHA256 to verify their correctness. Once the plays have been received, the contract will recognize the winning player and award him a point. The player who reaches 2 points first wins.

The contract interacts with 2 actors: The Owner and the Challenger

Requirements: both players must have enough SKULLs to start the game

Functions:

`create(asset, fee_holder)` The match organizer must call this function to create the smart contract and set the asset to be used in the match and the account that will receive the payout fees.

`init(txn, asset)` 

`define_stake(txn, fee_amount)` This function can only be called by the creator of the contract and is intended to define the stake of the game. The transaction specifies the stake amount and pays for it. In addition, the fee_amount that he must pay in case of a win is saved in the player's local state.

`cancel()` It can only be called by the creator of the contract and is intended to cancel the game in case you are unable to find a challenger.

`join(txn, fee_amount)` It can be called by any player other than the creator of the contract and is intended to enter the game as a challenger. To join the game it will be necessary to send the stake with a transaction and specify the fee_amount to be paid in case of a win

`commit(commit)` this function must be called by both players to indicate their moves, these are passed in the commit parameter in the form of hash256 of a JSON of the following type:
`{"guess": guess, "hand": hand, "nonce": nonce}`. The random nonce has the purpose of guaranteeing the secrecy of the commit avoiding brute force attacks.

`reveal(reveal, other)` this function must be called by both players to reveal their move. The player when calling the function must provide as a parameter a reveal that corresponds to the JSON on which he has calculated the function hash256 sent previously. The function will check that the hash of the JSON is the same as the one provided during the commit phase, if so it will also check that it respects the rules of the game, i.e. that 0 <= hand <= 5 and 0 <= guess <= 10. 
When the function is called for the second time it awards a point to the winner in the contract status and in case he has reached the two points it marks him as the winner of the match.

`opt_in(txn, fee_amount)`

`delete(asset, creator, fee_holder)`

`forfeit()` It can be called by both players, as a guarantee in case the opponent does not want to reveal their choice or stops playing. The function checks that 10 Rounds have passed since the last state change and if so if the opponent has not interacted for the last 10 rounds then the caller of the function is set as the winner in the contract state

# State of the Art

The most important time implementation is this [https://developer.algorand.org/solutions/morra-game-using-reach/](https://developer.algorand.org/solutions/morra-game-using-reach/) in Reach. We will develop it using Beaker to observe the differences. 

# Technical Challenges

In our development of this project we encountered numerous problems with the Beaker framework. 

The game platform, in multiple cases, requires the user to pass an application call when calling a method of the contract. This application call itself, often takes as parameters additional transactions. To our knowledge, the Beaker framework does not allow the use of its ApplicationClient methods to construct application calls that must be passed as parameters to other application calls. We therefore extended the beaker library (although in a hacky fashion to not slow down development) to support these use cases, adding a `nosend` version of the corresponding `create`, `call`, `opt-in` and `delete` calls, together with a `finalize` function to submit the created application calls.

Furthermore, we found out (by trial error, as the documentation is still very partial) that it is not possible to have more than one `opt_in`/`delete` method per contract. Although this seems like a design decision, we found this limit overly restrictive, and we think that it has impacted the tidiness of our implementation. 

For what concerns the contract themselves, most of the challenge in this project was making the game platform and the games communicate smoothly. To make our implementation cleaner, an obvious next step in our implementation would consist in creating a base contract for all the games that implements the interface needed to enable that communication, as currently a lot of code is replicated between contracts.

Lastly, we would've liked to use the new opcodes `block` and `vrf_verify` for the implementation of the blackjack contract, but we quickly found ourselves lost, although we're sure that if we had dedicated more time to it, we would've figured it out.
