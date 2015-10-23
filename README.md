# makomakorin_bot

This is the code that runs my Twitter bot, located at:

https://twitter.com/makomakorin_bot

API keys have been stripped out and images are not included.

makomakorin_bot runs on Python 3 and uses the tweepy library to interact with Twitter. The script is hosted on Heroku and tweets every hour on the dot. In addition, the script checks for new followers every 20 minutes and will attempt to follow back new followers. I wrote a function to automatically unfollow followers who are no longer following the bot, but its functionality is disabled by default in the script.

I used herokupostgres to store the queue of random images instead of keeping the queue in memory. This is done because Heroku worker dynos are cycled every 24 hours. Using a persistent database allows the current random queue to be maintained in between cycles, rather than having a brand new queue generated every time the script is restarted.

There is a special tweeting mode only on August 29 (Japan Standard Time) which tweets images from a separate queue at 4 times the regular frequency.
