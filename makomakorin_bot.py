import tweepy
import os
import random
import time
import datetime
import psycopg2
from urllib.parse import urlparse
from pytz import timezone

SCREEN_NAME = ''
CONSUMER_KEY = ''
CONSUMER_SECRET = ''
ACCESS_TOKEN = ''
ACCESS_TOKEN_SECRET = ''
DATABASE_URL = ''

# Parsed database url
PARSED_URL = urlparse(DATABASE_URL)

# Set to True to enable, False to disable
BOT_ENABLED = True
TWEET_IMAGES = True
FOLLOW_BACK = True
UNFOLLOW = False

# Number of users to get
NUM_FOLLOWERS = 50
NUM_FOLLOWING = 50

# Time intervals for various functions
TWEET_TIME = 3600   # 1 hours
FOLLOW_TIME = 1200  # 20 minutes
LOOP_DELAY = 60     # 1 minute

auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
auth.secure = True

api = tweepy.API(auth)

# Directories containing images
image_dir = os.path.join(os.getcwd(), 'images')
birthday_dir = os.path.join(os.getcwd(), 'birthday')

"""
TWITTER API RATE LIMITS
https://dev.twitter.com/rest/public/rate-limits

                                        User auth                   App auth
Title               Resource family     Requests / 15-min window        Requests / 15-min window
GET followers/list      followers               15                              30
GET friends/list        friends                 15                              30
"""

def main():
    while BOT_ENABLED:
        # Tweet an image and follow back new followers. Images should be tweeted every
        # hour on minute 0, while new followers should be followed back every 20 minutes
        # at minute 0, 20, and 40.
        # Get current minute
        minute = datetime.datetime.now().minute
        
        # Tweet a new image if current time is on the 0 minute
        if (TWEET_IMAGES and minute % 60 == 0) and (count_rows('queue') > 0) and (not is_birthday()):
            image = get_first_row('queue')
            delete_row('queue', image)
            tweet_images(image)
        
        # Birthday girl mode! Tweet at 15 minute intervals instead of 1 hour intervals
        if (TWEET_IMAGES and minute % 15 == 0) and (count_rows('birthday_queue') > 0) and is_birthday():
            image = get_first_row('birthday_queue')
            delete_row('birthday_queue', image)
            tweet_images(image)
        
        # Automatically follow back followers
        if FOLLOW_BACK and minute % 20 == 0:
            follow_back()
            
        # Remove from follow list if the user is no longer following this account
        if UNFOLLOW and minute % 20 == 0:
            unfollow_users()
            
        # If there are no images left in the queue, add new images to the queue
        if count_rows('queue') == 0:
            rebuild_database('queue', 'standard')
            
        if count_rows('birthday_queue') == 0:
            rebuild_database('birthday_queue', 'birthday')
          
        # Try to align next loop to be as close to HH:MM:00 as possible
        time.sleep(LOOP_DELAY - datetime.datetime.now().second)
   

def tweet_images(image):
    # Takes an absolute file path to an image and posts a tweet with the image.
    try:
        api.update_with_media(image)
        print("Tweeted image {}".format(os.path.basename(image)))
        
    except tweepy.error.TweepError as error:
        if error.response.status_code == 429:
            print("Could not tweet image. Request limit reached.")
        else:
            print("Could not locate file. Image not tweeted.")

            
def follow_back():
    # Retrieves a follower list of length NUM_FOLLOWERS and checks with the database to
    # see if a follow request has been sent to the user in the past. If not, send the user
    # a follow request.
    try:
        # items() returns an iterator object. Copy the items from the iterator
        # into a regular list of followers.
        followersIterator = tweepy.Cursor(api.followers).items(NUM_FOLLOWERS)
        followers = [follower for follower in followersIterator]
        
        # Check if the follower is in the friends list, if not, then send them a follow request
        for follower in followers:
            if not request_sent(follower.id):
                try:
                    # Send the follow request
                    follower.follow()
                    print("Follow request sent to {}".format(follower.screen_name))
                
                except tweepy.error.TweepError as error:
                    if error.response.status_code == 403:
                        # This error can occur if a previous follow request is sent to a protected account,
                        # and the request is still pending approval by the user. It can also occur if the
                        # user is blocking the account.
                        print("Could not follow user {}. {}".format(follower.screen_name, error.reason))
                    if error.response.status_code == 429:
                        print("Could not follow user {}. {}".format(follower.screen_name, "Request limit reached."))
                
    except tweepy.error.TweepError as error:
        if error.response.status_code == 429:
            print("Could not retrieve follower list. Request limit reached.")

        
def unfollow_users():
    # Retrieves a follower and following list and checks if there are any users on the
    # following list that are not on the follower list. If such a user is found, the
    # user is unfollowed.      
    try:
        friendsIterator = tweepy.Cursor(api.friends).items()
        followersIterator = tweepy.Cursor(api.followers).items()
        
        friends = [friend for friend in friendsIterator]
        followers = [follower for follower in followersIterator]
            
        for friend in friends:
            is_following = False
            
            for follower in followers:
                if friend.id == follower.id:
                    # Follower is still following, so do not unfollow
                    is_following = True
                    break
            
            if not is_following:
                try:
                    # Send the follow request
                    friend.unfollow()
                    print("Unfollowed {}.".format(friend.screen_name))
                
                except tweepy.error.TweepError as error:
                    if error.response.status_code == 403:
                        print("Could not follow user {}. {}".format(follower.screen_name, error.reason))
                    if error.response.status_code == 429:
                        print("Could not follow user {}. {}".format(follower.screen_name, "Request limit reached."))
                    
    except tweepy.error.TweepError as error:
        if error.response.status_code == 429:
            print("Could not retrieve follower list. Request limit reached.")            

            
# Randomly adds images to the queue database
def rebuild_database(tablename, set):
    images = []
    
    if set == 'standard':
        for root, directories, filenames in os.walk(image_dir):
            for filename in filenames:
                images.append(os.path.join(root,filename))
            
    if set == 'birthday':
        for root, directories, filenames in os.walk(birthday_dir):
            for filename in filenames:
                images.append(os.path.join(root,filename))
    
    random.shuffle(images)
    
    conn = create_connection()
    cur = conn.cursor()
    
    for image in images:
        cur.execute("INSERT INTO {} (image) VALUES ('{}')".format(tablename, image))
        
    conn.commit()
    cur.close()
    conn.close()
    print("Image queue shuffled.")

# Counts the number of rows in the table, returns count as an integer
def count_rows(tablename):
    conn = create_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT count(*) FROM {}".format(tablename))
    
    count = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    return count
    
# Returns the first row in the table
def get_first_row(tablename):
    conn = create_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT image FROM {} LIMIT 1".format(tablename))
    
    row = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    return row
    
def delete_row(tablename, id):
    conn = create_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM {} WHERE image = ('{}')".format(tablename, id))
    
    conn.commit()
    cur.close()
    conn.close()
    
# Delete all rows in the table, resulting in a valid, but empty table
def clear_table(tablename):
    conn = create_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM {}".format(tablename))
    
    conn.commit()
    cur.close()
    conn.close()
    
# Helper function for creating a connection to the database
def create_connection():
    return psycopg2.connect(database=PARSED_URL.path[1:],
                            user=PARSED_URL.username,
                            password=PARSED_URL.password,
                            host=PARSED_URL.hostname,
                            port=PARSED_URL.port)
                            
# Check if it's her birthday. August 29th, Japan Standard Time!
def is_birthday():
    japan_time = datetime.datetime.now(timezone('Asia/Tokyo'))
            
    if japan_time.month == 8 and japan_time.day == 29:
        return True
    else:
        return False

# Check if the given id is in the database
def request_sent(id):
    conn = create_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM request_sent WHERE id={}".format(id))
    
    status = cur.fetchone() is not None
    
    conn.commit()
    cur.close()
    conn.close()
    
    return status
        
            
if __name__ == "__main__":
    main()