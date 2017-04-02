# makomakorin_bot

###### 2017-04-02 UPDATE:
Changed again.
https://github.com/Kikugumo/imas765probot-v2

###### 2016-02-29 UPDATE:
makomakorin_bot now runs on the imas765probot code. As such, this codebase is to be considered deprecated. Please view the new code at:  
https://github.com/Kikugumo/imas765probot


## About

This is the code that used to run my Twitter bot, located at:

https://twitter.com/makomakorin_bot

API keys have been stripped out and images are not included.

makomakorin_bot runs on Python 3 and uses a modified version of the tweepy library to interact with Twitter. The script is hosted on Heroku and tweets every hour on the dot. In addition, the script checks for new followers every 20 minutes and will attempt to follow back new followers.

I used herokupostgres to store the queue of random images instead of keeping the queue in memory. This is done because Heroku worker dynos are cycled every 24 hours. Using a persistent database allows the current random queue to be maintained in between cycles, rather than having a brand new queue generated every time the script is restarted.

There is a special tweeting mode only on August 29 (Japan Standard Time) which tweets images from a separate queue at 4 times the regular frequency.
