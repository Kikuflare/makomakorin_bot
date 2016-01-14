# makomakorin_bot

###### 2016-01-13 UPDATE:
Many significant changes. Modified tweepy files are included with this build to support video/mp4 files because the official tweepy API still does not allow video upload. Most of the changes I based off of user fitnr's changes to api.py in [his fork](https://github.com/fitnr/tweepy/blob/master/tweepy/api.py) with some tweaking of my own.

I also introduced a new algorithm to queue files. The most recently posted files are recorded in a table up to a user defined limit (I have it set to 96 hours) and those files are taken into account when generating a new queue. This algorithm ensures that the most recently posted files will not appear at the start of the queue, but are still randomly scattered in the rest of the queue. I did this because I don't like seeing the same files only a few days apart. There will now be at minimum a 96 hour cooldown for all files.

The images folder was renamed media to better reflect the posted content. Some postgreSQL queries have been updated due to changes in table names.

## About

This is the code that runs my Twitter bot, located at:

https://twitter.com/makomakorin_bot

API keys have been stripped out and images are not included.

makomakorin_bot runs on Python 3 and uses a modified version of the tweepy library to interact with Twitter. The script is hosted on Heroku and tweets every hour on the dot. In addition, the script checks for new followers every 20 minutes and will attempt to follow back new followers.

I used herokupostgres to store the queue of random images instead of keeping the queue in memory. This is done because Heroku worker dynos are cycled every 24 hours. Using a persistent database allows the current random queue to be maintained in between cycles, rather than having a brand new queue generated every time the script is restarted.

There is a special tweeting mode only on August 29 (Japan Standard Time) which tweets images from a separate queue at 4 times the regular frequency.
