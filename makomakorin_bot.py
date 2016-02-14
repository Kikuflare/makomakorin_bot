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
TWEET_MEDIA = True
FOLLOW_BACK = True
UNFOLLOW = False

# Number of users to get
NUM_FOLLOWERS = 50
NUM_FOLLOWING = 50

# Time intervals for various functions
TWEET_TIME = 3600   # 1 hours
FOLLOW_TIME = 1200  # 20 minutes
LOOP_DELAY = 60     # 1 minute

"""
Number of entries to keep in recent queue table
It is best to keep this value less than half of the total number of unique files

DO NOT SET THIS VALUE HIGHER THAN THE TOTAL NUMBER OF UNIQUE FILES
"""
RECENT_LIMIT = 96

auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
auth.secure = True

api = tweepy.API(auth)

# Directories containing media files
media_dir = os.path.join(os.getcwd(), 'media')
birthday_dir = os.path.join(os.getcwd(), 'birthday')

"""
TWITTER API RATE LIMITS
https://dev.twitter.com/rest/public/rate-limits

                                        User auth                       App auth
Title               Resource family     Requests / 15-min window        Requests / 15-min window
GET followers/list      followers               15                              30
GET friends/list        friends                 15                              30
GET friendships/show    friendships             180                             15
"""

def main():
    while BOT_ENABLED:
        """
        Tweet a media file and follow back new followers. Files should be tweeted every
        hour on minute 0, while new followers should be followed back every 20 minutes
        at minute 10, 30, and 50.
        """

        # Get current minute
        minute = datetime.datetime.now().minute

        # Tweet a new media file if current time is on the 0 minute
        if (TWEET_MEDIA and minute % 60 == 0) and (count_rows('queue') > 0) and (not is_birthday()):
            filepath = None
            while filepath is None:
                # This while loop is just to ensure that the file from the queue actually exists
                # in the file system. We will grab the next file in the queue if it doesn't
                filepath = get_first_row('queue')
                delete_row('queue', filepath)
                if not os.path.isfile(filepath):
                    filepath = None
            tweet_media(filepath)

            # Push the tweeted file into the table of recent tweets, and remove the oldest entries
            # from the table until the limit is reached
            insert_recent(filepath)
            row_count = count_rows('recent_queue')
            if row_count > RECENT_LIMIT:
                for i in range(row_count - RECENT_LIMIT):
                    delete_oldest_row('recent_queue', 'timestamp')

        # Birthday girl mode! Tweet at 15 minute intervals instead of 1 hour intervals
        if (TWEET_MEDIA and minute % 15 == 0) and (count_rows('birthday_queue') > 0) and is_birthday():
            filepath = get_first_row('birthday_queue')
            delete_row('birthday_queue', filepath)
            tweet_media(filepath)

        # Automatically follow back followers
        if FOLLOW_BACK and (minute + 10) % 20 == 0:
            follow_back()

        # Remove from follow list if the user is no longer following this account
        if UNFOLLOW and minute % 20 == 0:
            unfollow_users()

        # If there are no files left in the queue, add new files to the queue
        if count_rows('queue') == 0:
            # requeue('queue', 'standard')
            smart_queue()

        if count_rows('birthday_queue') == 0:
            requeue('birthday_queue', 'birthday')

        # Try to align next loop to be as close to HH:MM:00 as possible
        time.sleep(LOOP_DELAY - datetime.datetime.now().second)


def tweet_media(filepath):
    # Takes an absolute file path to a media file and posts a tweet with the file.
    try:
        # api.update_with_media(filepath) # This is the old method

        # This uploads the file and receives a media_id value
        ids = []
        uploaded = api.media_upload(filepath)
        ids.append(uploaded['media_id'])

        # Use the media_id value to tweet the file
        api.update_status(media_ids=ids)

        print("Tweeted file {}".format(os.path.basename(filepath)))

    except tweepy.error.TweepError as error:
        if error.response is not None:
            if error.response.status_code == 429:
                print("Could not tweet file. Request limit reached.")
            elif error.response.status_code == 500:
                print("Could not tweet file. Twitter server error.")
                tweet_media(filepath) # Server error is likely temporary, try tweeting again
            elif error.response.status_code == 503:
                print("Could not tweet file. Service unavailable.")
                tweet_media(filepath) # Server error is likely temporary, try tweeting again
            else:
                print("Could not tweet file. Error status code {}".format(error.response.status_code))
        else:
            print("Something went very wrong. Reason: {}".format(error.reason))

    except TypeError as error:
        print("Could not tweet file. Uploading failed.")


def follow_back():
    """
    Retrieves a follower list of length NUM_FOLLOWERS and checks with the database to see if a
    follow request has been sent to the user in the past. If not, send the user a follow request.
    The old strategy was to retrieve the latest followers and do a quick check to see if we were
    already following them. However, because protected accounts can decline a follow request,
    some users would be sent another follow request even after declining one in the past. Our
    solution is to keep a database of sent requests and to only ever send one request per user.
    Now, users with protected accounts have one chance to accept, and users who unfollow and
    follow again will not be sent a second follow request.
    """
    try:
        # items() returns an iterator object. Copy the items from the iterator
        # into a regular list of followers.
        followersIterator = tweepy.Cursor(api.followers).items(NUM_FOLLOWERS)
        followers = [follower for follower in followersIterator]

        # Check if a follow request has already been sent, if not, then send a follow request
        for follower in followers:
            if not request_sent(follower.id):
                try:
                    # Send the follow request
                    follower.follow()
                    update_request_sent(follower.id, follower.screen_name)
                    print("Follow request sent to {}".format(follower.screen_name))

                except tweepy.error.TweepError as error:
                    if error.response is not None:
                        if error.response.status_code == 403:
                            # This error can occur if a previous follow request is sent to a protected account,
                            # and the request is still pending approval by the user. It can also occur if the
                            # user is blocking the account.
                            print("Could not follow user {}. {}".format(follower.screen_name, error.reason))
                        elif error.response.status_code == 429:
                            print("Could not follow user. Request limit reached.")
                        else:
                            print("Could not follow user. Error status code {}".format(error.response.status_code))

    except tweepy.error.TweepError as error:
        if error.response is not None:
            if error.response.status_code == 429:
                print("Could not follow user. Request limit reached.")
            elif error.response.status_code == 500:
                print("Could not follow user. Twitter server error.")
            elif error.response.status_code == 503:
                print("Could not follow user. Service unavailable.")
            else:
                print("Could not follow user. Error status code {}".format(error.response.status_code))
        else:
            print("Something went very wrong. Reason: {}".format(error.reason))


def unfollow_users():
    """
    Retrieves a follower and following list and checks if there are any users on the following
    list that are not on the follower list. If such a user is found, the user is unfollowed.
    
    Don't use this function. I'm still trying to figure out a way to do this efficiently and
    reliably with large numbers of followers/friends.
    """    
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
        if error.response is not None:
            if error.response.status_code == 429:
                print("Could not retrieve follower list. Request limit reached.")
            elif error.response.status_code == 500:
                print("Could not follow user. Twitter server error.")
            elif error.response.status_code == 503:
                print("Could not follow user. Service unavailable.")
            else:
                print("Could not follow user. Error status code {}".format(error.response.status_code))
        else:
            print("Something went very wrong. Reason: {}".format(error.reason))


# Randomly adds media files to the queue database
def requeue(tablename, set):
    filepaths = []

    if set == 'standard':
        for root, directories, filenames in os.walk(media_dir):
            for filename in filenames:
                filepaths.append(os.path.join(root,filename))

    if set == 'birthday':
        for root, directories, filenames in os.walk(birthday_dir):
            for filename in filenames:
                filepaths.append(os.path.join(root,filename))

    random.shuffle(filepaths)

    conn = create_connection()
    cur = conn.cursor()

    for filepath in filepaths:
        cur.execute("INSERT INTO {} (filepath) VALUES ('{}')".format(tablename, filepath))

    conn.commit()
    cur.close()
    conn.close()
    print("File queue shuffled.")


"""
Randomly adds files to the queue database. However, this algorithm will attempt
to ensure that the most recently posted files will not appear at the front of
the queue.

The most recently posted files are kept in a table called recent_queue. The table
length, at maximum, should be equal to the constant RECENT_LIMIT defined near the
beginning of this script.

Valid files are drawn from the pool by excluding the recent files. This list is
then shuffled, and a certain number (up to RECENT_LIMIT) of those files are
selected to be placed at the start of the new queue. The remaining files are
mixed with the recent files to form the rest of the new queue.

NOTE:
Why do we create a temp2 list with the recent files instead of using recent_queue?
This is because it is possible for recent_queue to contain files that are no
longer in the regular file pool. This method ensures that no dead files are put
into the queue.
"""
def smart_queue():
    new_queue = []

    # Fetch a list of the most recent files posted
    recent_queue = [row[0] for row in get_table_contents("recent_queue")]

    # Generate a list of files for the next queue
    file_pool = []
    for root, directories, filenames in os.walk(media_dir):
        for filename in filenames:
            file_pool.append(os.path.join(root,filename))

    # Split the files into two groups, shuffle the first group
    temp = [row for row in file_pool if row not in recent_queue]
    temp2 = [row for row in file_pool if row in recent_queue] # SEE NOTE IN THE COMMENT ABOVE
    random.shuffle(temp)

    # Determine how many files to place at the front
    end = len(temp) if len(temp) < RECENT_LIMIT else RECENT_LIMIT
    for i in range(end):
        new_queue.append(temp.pop())

    # Form the rest of the queue, and shuffle again
    temp = temp + temp2
    random.shuffle(temp)

    # Finish creating the queue
    new_queue = new_queue + temp

    # Push the queue to the table
    conn = create_connection()
    cur = conn.cursor()

    for filepath in new_queue:
        cur.execute("INSERT INTO queue (filepath) VALUES ('{}')".format(filepath))

    conn.commit()
    cur.close()
    conn.close()
    print("File queue shuffled.")


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

    cur.execute("SELECT filepath FROM {} LIMIT 1".format(tablename))

    row = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return row


# Delete the first row in the table
def delete_first_row(tablename):
    conn = create_connection()
    cur = conn.cursor()

    cur.execute("SELECT filepath FROM {} LIMIT 1".format(tablename))
    row = cur.fetchone()[0]
    cur.execute("DELETE FROM {} WHERE filepath = ('{}')".format(tablename, row))

    conn.commit()
    cur.close()
    conn.close()


"""
Delete oldest row in the table

Takes tablename and fieldname strings. fieldname is the name of the column
in the table called tablename which the function uses to order by date.
Therefore, the column should be of an appropriate date type that can be ordered.

Do not call this function on a table without a date field.
"""
def delete_oldest_row(tablename, fieldname):
    conn = create_connection()
    cur = conn.cursor()

    cur.execute("""DELETE FROM {0}
                   WHERE {1}
                   IN (SELECT {1}
                       FROM {0}
                       ORDER BY {1}
                       ASC
                       LIMIT 1)""".format(tablename, fieldname))

    conn.commit()
    cur.close()
    conn.close()


# Delete a single row in the table
def delete_row(tablename, id):
    conn = create_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM {} WHERE filepath = ('{}')".format(tablename, id))

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


"""
Insert entry into the recent_queue table. Each row should have a path to an file
and a timestamp of when the insertion occurred.

The timestamp is provided by Python's datetime module and the timezone is dependent on
the system which the script runs on.
"""
def insert_recent(entry):
    conn = create_connection()
    cur = conn.cursor()

    timestamp = str(datetime.datetime.now())

    cur.execute("INSERT INTO recent_queue (filepath, timestamp) VALUES ('{}','{}')".format(entry, timestamp))

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

    return japan_time.month == 8 and japan_time.day == 29


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


# Push the id and screen name of the follower to the list of sent requests
def update_request_sent(id, screen_name):
    conn = create_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO request_sent (id, screen_name) VALUES ('{}','{}')".format(id, screen_name))

    conn.commit()
    cur.close()
    conn.close()


# Get all rows and columns of a table
def get_table_contents(table_name):
    conn = create_connection()
    cur = conn.cursor()

    entries = []

    cur.execute("SELECT * FROM {}".format(table_name))

    for row in cur.fetchall():
        entries.append(row)

    conn.commit()
    cur.close()
    conn.close()

    return entries


if __name__ == "__main__":
    main()