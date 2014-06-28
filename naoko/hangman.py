# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
import random

words = open('naoko/words').readlines()

class GameException(Exception): 
    def __init__(self, message):
        self.message = message

class Game:
    def __init__(self, minmax_guesses = 8, guess_margin = 4):
        self.minmax_guesses = minmax_guesses  # minimum max guesses
        self.guess_margin   = guess_margin    # extra guesses over num chars in word
        self.reset_game()

    def reset_game(self): 
        self.word    = ""
        self.guesses = set()
        self.max_guesses = 0 

    def has_started(self):
        return self.word != ""

    def has_won(self):
        return set(self.word).issubset(self.guesses)

    def has_lost(self):
        return len(self.guesses) >= self.max_guesses

    def game_status(self):
        if not self.has_started():
            return "not started" 
        elif self.has_won(): 
            return "won"
        elif self.has_lost(): 
            return "lost"
        else: 
            return "in progress" 
    
    def start_game(self): 
        if self.has_started():
            raise GameException("There's a game already going.")
        self.word        = random.sample(words,1)[0].strip()
        self.max_guesses = max(self.minmax_guesses, 
                            len(set(self.word)) + self.guess_margin)
        return self.word

    def guess(self, guess): 
        guess = guess.decode('ascii','ignore').lower().strip()
        if not self.has_started():
            raise GameException("No game going at the moment.")

        if not set(guess).issubset(set('abcdefghijklmnopqrstuvwxyz')):
            raise GameException("Err... you can guess only letters.")

        if len(guess) > 1: 
            if guess == self.word: 
                self.guesses.update(set(guess))
                return
            else: 
                raise GameException("Nope, '{}' is not the word.".format(guess))

        if guess in self.guesses: 
            raise GameException("'{}' has already been guessed.".format(guess)) 
            
        self.guesses.add(guess)

    def print_guessed(self): 
        str = ""
        for i in self.word:
            if i in self.guesses:
                str+=i
            else:
                str+="-"
        return str.strip()
            
