# Naoko - A CyTube bot

There is no mumble, irc, webserver, repl or any of that. 

## Requirements
- Naoko was developed using Python 2.7.2
- Naoko requires a registered CyTube account, and most functionality does not
  work properly without being a moderator.

## Usage

```sh
    git clone git://github.com/karloor/kbot.git
    cd kbot 
    python naoko/naoko.py --room <room> --name <botname> --pass <password>
```

Edit the included `naoko.conf.template` file to control the settings. And use
`--help` to get usage help. 

Use the `$help` command to get a list of commands and their usage. 

## Original history
### History by Desuwa 
With Synchtube's demise, our small animu community survived in IRC, waiting for
a suitable replacement. Due to the work involved none of us were going to start
our own replacement site. With CyTube being open source, actively developed, and
not directly tied to any particular Synchtube room it seemed the obvious choice.

The process of porting Naoko to CyTube is ongoing with her most important
functionality already reimplemented.

### History by Falaina 
This is just a small explanation on how this code relates to the bot that used
to be in the synchtube animu room.

I used to run a bot named "Denshi" in the animu synchtube room. Denshi was
written in node.js and was written while I was learning the synchtube protocol.
As a result Denshi's source is, in all honesty, a complete mess. I used random
node.js modules to do silly things and hardcoded paths and values. I probably
will not release that source code as it's so shoddy I don't want my named
attached to it; additionally it'd be relatively hard to get working on any
machine that wasn't her original VPS.

The code in this repository was the beginning of my attempt to rewrite Denshi in
Python with minimal use of external libraries so it could be more easily used by
others. I didn't get much farther than having it connect and print information.
I've decided to release it as it should allow anyone with some knowledge of
Python to program a working bot without worrying too much about the socket-level
details. In its current state it isn't very useful though.

I encourage anyone to fork this and make a more useful base bot for other
channels to use, as I don't have the time to do much other than small bug fixes
on this base.
